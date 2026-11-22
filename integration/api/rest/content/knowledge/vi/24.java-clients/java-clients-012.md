# Retry, redirect và giữ an toàn thông tin xác thực

> **Module:** `INTEGRATION_API_REST` — chương **Client Java**. Bài học thiết kế client REST bằng Java 17+ và Spring theo resource, URI, HTTP method/status cùng hợp đồng rõ ràng. Trọng tâm: **retry có giới hạn, redirect có kiểm soát và không làm rò `Authorization`, cookie hoặc token**. Tình huống xuyên suốt là client gọi API đơn hàng và tải báo cáo từ một service khác.

## 1. Ba thao tác tưởng nhỏ nhưng có thể làm sai nghiệp vụ

Giả sử ứng dụng gọi:

~~~http
POST /v1/payments HTTP/1.1
Host: pay.example.test
Authorization: Bearer <access-token>
Idempotency-Key: 811c1372-f881-4827-87ab-698bd3a45169
Content-Type: application/json
Accept: application/json

{"orderId":"ord_42","amount":"250000","currency":"VND"}
~~~

Server đã ghi nhận khoản thanh toán nhưng **response bị mất**. Nếu client tự động gửi lại như một lệnh mới, có thể tạo khoản thanh toán thứ hai. Ngược lại, nếu client luôn ngừng sau timeout, người dùng không biết kết quả thực tế.

Khi `GET /v1/invoices/inv_42/content` trả `302 Location: https://files.example-cdn.test/inv_42.pdf`, việc gửi **Bearer token của `api.example.test`** sang CDN có thể lộ credential. Redirect không giới hạn còn có thể chạm địa chỉ nội bộ.

Hai tình huống này chỉ ra ba nguyên tắc:

1. **Retry không được thay đổi kết quả nghiệp vụ** của một thao tác.
2. **Redirect thay đổi đích đến và có thể thay đổi method/body**; phải đọc status và chính sách trước khi follow.
3. **Credential gắn với origin/audience/quyền cụ thể**, không phải một header được sao chép qua mọi hop.

**Mục tiêu:** phân loại retry, dùng `Idempotency-Key`/`Retry-After`, chặn redirect nguy hiểm và kiểm thử bằng Java `HttpClient`/Spring.

## 2. Retry nghĩa là gì trong hợp đồng HTTP?

Timeout có thể xảy ra **trước commit hoặc sau commit nhưng response mất**; `IOException` không cho client biết chắc kết quả.

~~~mermaid
sequenceDiagram
    participant C as Java client
    participant S as API server
    participant DB as Database
    C->>S: POST /payments (Idempotency-Key: K)
    S->>DB: Commit payment P
    DB-->>S: OK
    Note over S,C: Response 201 bị mất
    C->>S: POST /payments (cùng key K và body)
    S->>S: Tra kết quả K đã hoàn tất
    S-->>C: Trả lại kết quả đã ghi nhận, không tạo P thứ hai
~~~

### 2.1. Safe, idempotent và replay không phải một

| HTTP method | Ngữ nghĩa cơ bản | Gợi ý retry |
|---|---|---|
| `GET`, `HEAD` | Safe theo định nghĩa HTTP, không yêu cầu thay đổi state | Có thể retry khi lỗi **tạm thời**, có hạn mức |
| `PUT` | Idempotent khi request cùng target/representation giữ nguyên | Thường có thể retry, nhưng xét `If-Match`, side effect phụ và body |
| `DELETE` | Idempotent theo **tác động dự kiến** | Retry có thể nhận `404` sau lần xóa đầu; contract quyết định cách hiểu |
| `POST` | Không mặc nhiên idempotent | Chỉ retry an toàn nếu API cung cấp key/dedup hoặc thao tác có bảo đảm riêng |
| `PATCH` | Không mặc nhiên idempotent | Cần biết ngữ nghĩa patch, precondition hoặc dedup rõ ràng |

**Idempotent không đồng nghĩa response giống nhau:** DELETE có thể trả `204` rồi `404`; PUT với `If-Match` có thể trả `412` sau lần commit đầu. Xác định **tác động nghiệp vụ** cần chống nhân đôi, không chỉ số lần gửi HTTP.

### 2.2. `Idempotency-Key` phải được server thực thi

Với thao tác ghi không idempotent như tạo payment, dùng key duy nhất cho **một ý định nghiệp vụ**, giữ nguyên key trên mọi attempt của cùng thao tác. Server phải lưu key với **scope** (tenant, principal/API client, route hoặc operation), fingerprint của request, trạng thái xử lý và kết quả. Khi key bị dùng lại với payload **khác**, trả lỗi xác định, thường `409 Conflict` theo hợp đồng; không tạo thao tác mới.

Chỉ có header `Idempotency-Key` không đủ nếu server chưa hỗ trợ; công bố TTL/replay/in-progress. **Không đổi key sau timeout của cùng ý định**.

### 2.3. Phân biệt retry request với đối soát kết quả

Sau timeout của POST, ưu tiên một trong hai:

1. Retry **cùng key** khi server bảo đảm idempotency.
2. Query trạng thái qua `GET /payments/{id}` hoặc một operation monitor (`202 Accepted` + `Location`) nếu đã có ID/correlation.
3. Nếu không có cơ chế nào, đưa thao tác vào trạng thái **chưa xác định** và đối soát; không tự phát lại payment như một lệnh độc lập.

Exactly-once effect cần cơ chế phía server/DB; client retry đơn thuần không bảo đảm.

## 3. Khi nào nên và không nên retry?

| Kết quả / exception | Có nên retry? | Điều kiện |
|---|---|---|
| `200/201/204` thành công | Không | Kiểm tra contract rồi kết thúc |
| `202 Accepted` | Không gửi lại POST ngay | Theo dõi operation qua `Location`/monitor |
| `408 Request Timeout` | Có thể | Request có thể replay an toàn |
| `429 Too Many Requests` | Có thể | Tôn trọng `Retry-After` và giới hạn chung |
| `500` | Tùy | Chỉ retry khi biết lỗi tạm thời và operation an toàn |
| `502/503/504` | Thường có thể | Backoff, không vượt deadline/quota |
| `401 Unauthorized` | Không retry vô hạn | Có thể refresh token **một lần** nếu flow cho phép |
| `403 Forbidden` | Không | Thiếu quyền thường không tự hết sau một retry |
| `400/404/409/412/422` | Không retry mù | Cần sửa request, trạng thái hoặc giải quyết conflict |
| Timeout/network reset/EOF | Có thể, nhưng outcome mơ hồ | Chỉ replay body/operation an toàn |
| Lỗi TLS certificate, hostname hoặc auth policy | **Không** | Sửa cấu hình/tin cậy, không tắt TLS validation |

`404` có thể tạm thời trong eventual-consistency workflow **nếu contract nói vậy**; `409` đôi khi nghĩa là operation chưa sẵn sàng. Không mặc định retry chúng ngoài hợp đồng.

### 3.1. `Retry-After` và backoff

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 3
Content-Type: application/problem+json

{"type":"about:blank","title":"Too Many Requests","status":429}
~~~

`Retry-After` có thể là **số giây không âm** hoặc **HTTP-date**. Đó là hướng dẫn thời điểm sớm nhất nên thử lại, không phải mệnh lệnh phải thử. Client vẫn cần tổng deadline, attempt limit và quyền hủy. Khi server không gửi header hoặc giá trị lỗi, dùng **exponential backoff có jitter**:

~~~text
base = 200 ms, cap = 2 s
max backoff mỗi lần: 200 ms -> 400 ms -> 800 ms -> 1600 ms
full jitter: random trong [0, max backoff]
attempt tối đa: 4 (1 lần ban đầu + 3 retry)
~~~

Jitter tránh clients retry đồng loạt. Có `Retry-After` hợp lệ thì **không thử sớm hơn**; nếu vượt deadline, kết thúc.

### 3.2. Timeout phải có nhiều tầng

Đặt connect timeout, timeout **mỗi attempt**, deadline **toàn operation**, max attempts/redirects. Kiểm soát cả DNS, TLS, queue và body read; reactive client phải đợi phi chặn, không `Thread.sleep` trên event loop.

### 3.3. Body phải replay được

`BodyPublishers.ofString(...)`/`ofByteArray(...)` thường replay được; `InputStream` một lần, file đã đổi hoặc streaming multipart **không** replay an toàn. Mỗi attempt cần nguồn byte ổn định; file lớn nên dùng resumable upload.

## 4. Redirect: đọc mã trạng thái trước khi theo `Location`

`Location` là URI được server cung cấp, **không mặc nhiên đáng tin cậy như URI gốc**. Client phải phân biệt tạo resource và chuyển hướng:

| Status | Ý nghĩa khi redirect | Lưu ý |
|---|---|---|
| `301 Moved Permanently` | URI đã chuyển lâu dài | Một số client đổi POST thành GET theo thực tiễn; không dựa vào replay body |
| `302 Found` | Chuyển tạm thời | Tương tự, lịch sử client có thể đổi POST thành GET |
| `303 See Other` | Đi đến URI khác bằng **GET** (trừ HEAD) | Hữu ích sau POST để xem kết quả |
| `307 Temporary Redirect` | Chuyển tạm thời, **giữ method và body** | Chỉ follow khi có thể replay body |
| `308 Permanent Redirect` | Chuyển lâu dài, **giữ method và body** | Cần chính sách lưu/cập nhật đích |

`201 Location` chỉ resource mới; `202 Location` có thể chỉ monitor. Cả hai **không phải redirect**.

Ví dụ:

~~~http
HTTP/1.1 303 See Other
Location: /v1/payments/pay_42
Cache-Control: no-store
~~~

`303` gợi ý **GET /v1/payments/pay_42**, không POST lại body; `307/308` giữ POST nên cần xét đích và khả năng replay.

### 4.1. Same-origin khác same-site

**Origin** là scheme, host, port hiệu lực; CDN subdomain hoặc HTTP cùng host vẫn là **khác origin**. Không forward `Authorization`, `Cookie`, `Proxy-Authorization` hoặc API key theo mặc định.

Các chính sách an toàn:

- Giới hạn **số lần redirect**, phát hiện vòng lặp và validate `Location`.
- **Không cho HTTPS → HTTP** nếu chứa dữ liệu/token nhạy cảm.
- Với authenticated API call, chỉ follow **cùng origin** nếu route và audience vẫn phù hợp; cross-origin phải được phép riêng theo contract.
- Nếu response trỏ tới **signed download URL** trên object storage, tạo **request mới không chứa bearer token API**, chỉ gửi những header được ký/được phép.
- Chặn redirect tới địa chỉ nội bộ, link-local, loopback, metadata service hoặc target ngoài allowlist nếu endpoint lấy URI từ input bên ngoài; kiểm tra cả DNS resolution và redirect hops.
- Không log đầy đủ `Location` chứa query signature, token hoặc thông tin cá nhân.

**Không dựa vào mặc định của thư viện để chứng minh credential không bị forward.** Chọn chính sách rõ ràng, kiểm thử bằng mock server ở hai origin và nâng cấp thư viện có regression tests.

## 5. Java 17 `HttpClient`: chủ động kiểm soát redirect

`java.net.http.HttpClient` hỗ trợ `Redirect.NEVER/NORMAL/ALWAYS`. Với Bearer token, ví dụ này **tắt auto-follow**, chỉ GET tới cùng HTTPS origin.

### 5.1. Kiểm tra URI trước từng hop

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.*;

final class RedirectPolicy {
    private final URI trustedOrigin;

    RedirectPolicy(URI trustedOrigin) {
        this.trustedOrigin = trustedOrigin;
        verify(trustedOrigin);
    }

    URI nextGet(URI current, int status, String location) {
        if (!Set.of(301, 302, 303, 307, 308).contains(status)) {
            throw new IllegalArgumentException("Not a redirect");
        }
        if (location == null || location.isBlank()) {
            throw new IllegalArgumentException("Missing Location");
        }
        URI target = current.resolve(URI.create(location));
        verify(target);
        return target;
    }

    void verify(URI target) {
        // Authenticated API GETs chỉ đến một HTTPS origin đã cấu hình.
        if (!"https".equalsIgnoreCase(target.getScheme())
                || target.getHost() == null
                || target.getRawUserInfo() != null
                || target.getRawFragment() != null
                || !target.getHost()
                    .equalsIgnoreCase(trustedOrigin.getHost())
                || effectivePort(target) != effectivePort(trustedOrigin)) {
            throw new SecurityException(
                "Redirect outside trusted API origin");
        }
    }

    private static int effectivePort(URI uri) {
        return uri.getPort() < 0 ? 443 : uri.getPort();
    }
}
~~~

Chính sách chặn chuyển token tới host, scheme hoặc port khác; URI tương đối được resolve theo đích hiện tại. Allowlist đa origin cần **token đúng audience** cho từng origin.

`trustedOrigin` phải từ config tin cậy. Với URL tùy ý phải thêm DNS/IP/redirect SSRF protection; host-string check chưa đủ. Cần thêm allowlist path khi quyền gắn với route.

### 5.2. GET có redirect có giới hạn, không phát tán Bearer

~~~java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.net.http.HttpResponse.BodyHandlers;

final class OrderApiClient {
    private static final int MAX_REDIRECTS = 3;
    private static final int MAX_SMALL_JSON_BYTES = 1024 * 1024;
    private final URI base = URI.create("https://api.example.test/");
    private final RedirectPolicy redirects = new RedirectPolicy(base);
    private final HttpClient http = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();
    private final java.util.function.Supplier<String> accessToken;

    OrderApiClient(
            java.util.function.Supplier<String> accessToken) {
        this.accessToken = accessToken;
    }

    String getSmallJson(String path)
            throws IOException, InterruptedException {
        URI current = base.resolve(path);
        Set<URI> visited = new HashSet<>();

        for (int hop = 0; hop <= MAX_REDIRECTS; hop++) {
            redirects.verify(current);
            if (!visited.add(current)) {
                throw new IOException("Redirect loop");
            }

            HttpRequest request = HttpRequest.newBuilder(current)
                .timeout(Duration.ofSeconds(8))
                .header("Accept", "application/json")
                .header("Authorization",
                    "Bearer " + accessToken.get())
                .GET()
                .build();

            HttpResponse<InputStream> response =
                http.send(request, BodyHandlers.ofInputStream());
            try (InputStream body = response.body()) {
                int code = response.statusCode();
                if (Set.of(301, 302, 303, 307, 308)
                        .contains(code)) {
                    String location = response.headers()
                        .firstValue("Location")
                        .orElseThrow(() ->
                            new IOException("Redirect without Location"));
                    current = redirects.nextGet(
                        current, code, location);
                    continue;
                }
                if (code < 200 || code >= 300) {
                    throw new IOException(
                        "API returned HTTP " + code);
                }
                byte[] bytes = body.readNBytes(
                    MAX_SMALL_JSON_BYTES + 1);
                if (bytes.length > MAX_SMALL_JSON_BYTES) {
                    throw new IOException("Response too large");
                }
                return new String(bytes, StandardCharsets.UTF_8);
            }
        }
        throw new IOException("Too many redirects");
    }
}
~~~

Mỗi hop được kiểm trước khi gắn Bearer; giới hạn 3 hop và phát hiện vòng lặp. Ví dụ chỉ đọc **JSON nhỏ ≤1 MiB**. Production cần kiểm `Content-Type`, tổng deadline và read-idle cancellation; timeout request không thay mọi giới hạn đọc `InputStream`.

Với POST/PUT/PATCH cần policy riêng cho 303/307/308, nguồn body replay và 301/302; không follow HTML login URL khi chờ JSON.

### 5.3. Signed URL là một request khác

Sau khi xác thực URI ký có HTTPS/allowlist/TTL, tạo **request GET mới không có Authorization Bearer của API**, ví dụ `HttpRequest.newBuilder(signedUri).GET().build()`. Signed URL là **bearer capability**, không log query signature và không tắt TLS/hostname verification.

## 6. Java: retry có deadline, backoff và `Retry-After`

Ví dụ sau dùng client **đồng bộ**, phù hợp service Java chạy trên thread thông thường. Retry chỉ áp dụng cho **GET idempotent** và một số lỗi tạm thời; không dùng `Thread.sleep` trong event-loop WebFlux. Để ngắn gọn, đoạn code nhận `URI` đã qua `RedirectPolicy.verify` và **không tự follow 3xx**.

~~~java
import java.io.IOException;
import java.net.ConnectException;
import java.net.URI;
import java.net.http.*;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.concurrent.ThreadLocalRandom;

final class GetRetryPolicy {
    private static final int MAX_ATTEMPTS = 4;
    private static final long MAX_BACKOFF_MS = 2000;
    private final HttpClient client;
    private final java.util.function.Supplier<String> token;

    GetRetryPolicy(HttpClient client,
            java.util.function.Supplier<String> token) {
        if (client.followRedirects() != HttpClient.Redirect.NEVER) {
            throw new IllegalArgumentException(
                "Retry client must not auto-follow redirects");
        }
        this.client = client;
        this.token = token;
    }

    HttpResponse<String> get(URI uri)
            throws IOException, InterruptedException {
        long deadline = System.nanoTime()
            + Duration.ofSeconds(20).toNanos();

        for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
            HttpRequest req = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(6))
                .header("Accept", "application/json")
                .header("Authorization", "Bearer " + token.get())
                .GET().build();

            try {
                // Chỉ minh họa response JSON nhỏ; xem mục 5 để giới hạn
                // bytes và đóng InputStream cho payload lớn.
                HttpResponse<String> res = client.send(
                    req, HttpResponse.BodyHandlers.ofString());
                if (attempt == MAX_ATTEMPTS
                        || !retryableStatus(res.statusCode())) {
                    return res;
                }
                pause(delay(res.headers(), attempt), deadline);
            } catch (HttpTimeoutException | ConnectException ex) {
                if (attempt == MAX_ATTEMPTS) throw ex;
                pause(backoff(attempt), deadline);
            }
        }
        throw new IOException("Retry attempts exhausted");
    }

    private static boolean retryableStatus(int code) {
        return code == 408 || code == 429
            || code == 502 || code == 503 || code == 504;
    }

    private static Duration delay(
            HttpHeaders headers, int attempt) {
        var header = headers.firstValue("Retry-After");
        if (header.isPresent()) {
            String v = header.get().trim();
            try {
                long seconds = Long.parseLong(v);
                if (seconds >= 0) return Duration.ofSeconds(
                    Math.min(seconds, 86400));
            } catch (NumberFormatException ignored) {
                try {
                    Instant when = ZonedDateTime.parse(
                        v, DateTimeFormatter.RFC_1123_DATE_TIME)
                        .toInstant();
                    Duration d = Duration.between(
                        Instant.now(), when);
                    return d.isNegative() ? Duration.ZERO : d;
                } catch (DateTimeParseException invalidDate) {
                    // Header không hợp lệ: fallback vào jitter.
                }
            }
        }
        return backoff(attempt);
    }

    private static Duration backoff(int attempt) {
        long cap = Math.min(MAX_BACKOFF_MS,
            200L * (1L << (attempt - 1)));
        return Duration.ofMillis(
            ThreadLocalRandom.current().nextLong(cap + 1));
    }

    private static void pause(
            Duration delay, long deadlineNanos)
            throws IOException, InterruptedException {
        if (delay.isNegative()
                || delay.toNanos()
                    >= deadlineNanos - System.nanoTime()) {
            throw new IOException("Retry deadline exceeded");
        }
        Thread.sleep(delay.toMillis());
    }
}
~~~

**Không đưa mẫu vào production nguyên xi:** kiểm tra `uri` bằng allowlist/trusted origin **trước** khi gọi; giới hạn kích thước response (`BodyHandlers.ofInputStream()` + counted read), đo tổng deadline cả lúc đọc body, phân loại lỗi mạng. Ví dụ chỉ bắt `HttpTimeoutException`/`ConnectException`, không retry mọi `IOException` (đặc biệt TLS/certificate errors). Với `Retry-After` lớn hơn deadline, phải kết thúc; cách giới hạn phép parse đến một ngày ở trên chỉ bảo đảm **không retry sớm hơn trong deadline 20 giây**, không phải chính sách hạ thời gian chờ của server.

## 7. Tích hợp Spring: policy phải nằm ở HTTP-client boundary

Spring Framework 6.1+ có `RestClient` đồng bộ và `WebClient` reactive; cả hai vẫn cần retry/redirect/credential policy rõ ràng.

### 7.1. `RestClient` với Java HttpClient không tự redirect

~~~java
import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

HttpClient jdk = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(3))
    .followRedirects(HttpClient.Redirect.NEVER)
    .build();

RestClient rest = RestClient.builder()
    .requestFactory(new JdkClientHttpRequestFactory(jdk))
    .baseUrl("https://api.example.test")
    .build();

// Dùng URI và token lấy từ trusted configuration/provider.
// Xử lý 3xx thủ công theo redirect policy, không cài interceptor
// gắn token cho mọi URI tùy ý.
~~~

`RestClient.retrieve()` thường ném exception với 4xx/5xx; dùng `exchange(...)` khi cần kiểm status, `Retry-After` hoặc `Location`. Spring Retry/Resilience4j cần predicate theo method, idempotency và deadline; không retry mọi `RestClientException`.

### 7.2. `WebClient`: retry không chặn event loop

~~~java
import java.time.Duration;
import reactor.util.retry.Retry;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

reactor.netty.http.client.HttpClient netty =
    reactor.netty.http.client.HttpClient.create()
        .followRedirect(false);
WebClient web = WebClient.builder()
    .baseUrl("https://api.example.test")
    .clientConnector(new ReactorClientHttpConnector(netty))
    // Token chỉ gắn vào URI/origin đã qua allowlist.
    .build();

Mono<OrderView> result = web.get()
    .uri("/v1/orders/{id}", "ord_42")
    .accept(org.springframework.http.MediaType.APPLICATION_JSON)
    .retrieve()
    .bodyToMono(OrderView.class)
    .retryWhen(Retry.backoff(3, Duration.ofMillis(200))
        .maxBackoff(Duration.ofSeconds(2))
        .filter(MyClientErrors::isRetryableRead)
        .jitter(0.5));
~~~

`MyClientErrors.isRetryableRead` là predicate ứng dụng: chỉ lỗi mạng tạm thời hoặc 408/429/502/503/504; không 401/403. Skeleton cần `Mono`/`OrderView` và token-scoping config. `Retry.backoff` không tự xử lý `Retry-After`; không `Thread.sleep`/`block()` trên event loop, không retry streaming POST không replay được.

## 8. Credential, cookie và refresh token: giữ đúng phạm vi

| Thông tin | Phạm vi cần kiểm soát | Điều không nên làm |
|---|---|---|
| `Authorization: Bearer ...` | Audience, HTTPS origin, API scope, thời hạn | Copy sang CDN/đối tác khi có 302 |
| `Cookie` | Domain/path, Secure, SameSite và session chính sách | Tự lấy Cookie header rồi forward mọi redirect |
| `Proxy-Authorization` | Proxy đích đã cấu hình | Gửi như header origin-server cho host khác |
| API key / custom auth header | Service/tenant cụ thể | Đặt trong URI query hoặc log raw header |
| Signed URL | Một object/method/TTL do signer quy định | Dùng như public URL, log chữ ký |
| Refresh token | Kênh auth service và storage bảo vệ | Đưa vào resource server request hoặc URL |

Với 401 và OAuth2 refresh flow hợp lệ, **refresh tối đa một lần**, giữ audience; dùng single-flight/token cache chống “refresh storm”. Refresh thất bại thì dừng, không retry 401 vô hạn.

Luôn xác minh TLS/hostname; không dùng `trust-all`. Proxy auth tách khỏi API Bearer; log theo route template, redact `Authorization`/`Cookie`/`Set-Cookie` và signed URL.

## 9. Retry cũng là bảo vệ hạ tầng

Retry hàng loạt có thể khuếch đại sự cố; cần:

- Deadline/attempt/redirect limit và **retry budget**; backoff+jitter, `Retry-After` và concurrency cap.
- Circuit breaker/bulkhead, cancellation propagation, không retry che lỗi capacity.
- Metric attempts, status class, delay, redirect blocked, latency; không log credential.

## 10. OpenAPI và hợp đồng server để client retry đúng

Client không thể tự đoán một POST có được retry an toàn hay không. Hợp đồng API cần nêu **Idempotency-Key**, scope/dedup TTL, mã lỗi, `Retry-After` và resource trạng thái khi xử lý nền.

~~~yaml
openapi: 3.1.0
info: {title: Payment API, version: 1.0.0}
paths:
  /v1/payments:
    post:
      security: [{bearerAuth: []}]
      parameters:
        - name: Idempotency-Key
          in: header
          required: true
          schema: {type: string, minLength: 1, maxLength: 128}
          description: Cùng ý định thanh toán dùng cùng key và body.
      requestBody:
        required: true
        content:
          application/json:
            schema: {type: object}
      responses:
        '201':
          description: Thanh toán đã tạo; replay cùng key không nhân đôi
          headers:
            Location: {schema: {type: string, format: uri-reference}}
        '202':
          description: Đang xử lý; theo dõi operation
        '409':
          description: Cùng key nhưng payload khác / conflict
        '429':
          description: Vượt rate limit
          headers:
            Retry-After: {schema: {type: string}}
        '503':
          description: Dependency tạm thời không khả dụng
          headers:
            Retry-After: {schema: {type: string}}
components:
  securitySchemes:
    bearerAuth: {type: http, scheme: bearer}
~~~

`Retry-After` có thể là số giây hoặc HTTP-date nên schema string chỉ là mô tả giản lược; tài liệu phải nói cách parse/giới hạn. Cần chỉ ra khi cùng key đang **IN_PROGRESS** thì client poll hoặc retry theo cách nào. Không suy đoán từ `Location` của **201/202** rằng đây là redirect.

## 11. Kiểm thử retry, redirect và credential ở HTTP boundary

Unit test `RedirectPolicy` dễ viết, nhưng để chứng minh token không bị lộ phải dùng **hai mock HTTP servers/origins** và quan sát header request thực:

~~~java
// JUnit 5, dùng RedirectPolicy ở mục 5.
@Test
void rejectsCrossOriginAndHttpsDowngrade() {
    URI origin = URI.create("https://api.example.test/");
    RedirectPolicy p = new RedirectPolicy(origin);
    assertThrows(SecurityException.class, () -> p.nextGet(
        origin, 302, "https://evil.example/collect"));
    assertThrows(SecurityException.class, () -> p.nextGet(
        origin, 307, "http://api.example.test/orders"));
    assertEquals(URI.create("https://api.example.test/v1/orders/42"),
        p.nextGet(origin, 303, "/v1/orders/42"));
}
~~~

Ma trận test của client:

| Case | Kỳ vọng |
|---|---|
| GET trả `503` hai lần, sau đó `200` | Đúng ba attempts, backoff và body cuối |
| `429 Retry-After: 3`, deadline còn 1 giây | Không retry sớm, báo hết ngân sách |
| `Retry-After` là HTTP-date hoặc sai cú pháp | Parse được hoặc fallback jitter có kiểm soát |
| POST payment đã commit nhưng response mất | Retry **cùng key/body** hoặc đối soát; một payment logic |
| POST không có idempotency mà timeout | Không phát lại tự động |
| `301/302` sau POST | Không âm thầm đổi method trong client ghi an toàn |
| `303` sau POST | GET resource mới theo policy, không POST body lại |
| `307/308` với body không replay được | Từ chối follow hoặc yêu cầu nguồn replay |
| `302` sang CDN/host ngoài allowlist | Không forward Bearer/cookie/API key |
| Redirect vòng hoặc hơn giới hạn hop | Kết thúc rõ ràng, không loop |
| HTTPS → HTTP hoặc localhost/link-local | Bị chặn theo threat model |
| `401` rồi refresh thành công | Tối đa một refresh, đúng audience |
| `403` hoặc TLS certificate lỗi | Không retry/không bỏ TLS verification |
| Response JSON quá lớn hoặc sai Content-Type | Từ chối parse an toàn; không buffer vô hạn |

Với WireMock/MockWebServer, cấu hình server A trả `302 Location: <origin-B>`, server B ghi lại headers. Xác nhận **không có request tới B** khi policy chỉ cho same-origin; ở luồng signed URL được phép, xác nhận B **không nhận `Authorization` hay `Cookie` từ A**. Test clock/sleeper có thể tiêm vào retry policy để kiểm thời gian mà không chờ thật; tránh test ngẫu nhiên jitter bằng giá trị mili-giây chính xác.

## 12. Bài tập: thanh toán và tải hóa đơn từ Java

**Bối cảnh:** Một service Java/Spring gọi `POST /v1/payments`, nhận `201 Location` hoặc `202`. Sau đó GET hóa đơn có thể trả `303` đến resource xem kết quả hoặc redirect đến signed object-storage URL. API gateway đôi khi trả 429/503, client chạy nhiều instance và dùng OAuth2 Bearer token.

Hãy thiết kế:

1. Chính sách retry theo method/status: GET, PUT có `If-Match`, POST payment, timeout không biết kết quả.
2. Cách tạo/giữ `Idempotency-Key` qua restart và retry; server lưu fingerprint, TTL và kết quả thế nào.
3. Thuật toán backoff có jitter, `Retry-After` dạng giây/ngày HTTP, tổng deadline và max attempts.
4. Java `HttpClient` để `Redirect.NEVER`, kiểm origin/scheme/port, xử lý 303 so với 307/308 và loop.
5. Cách tải signed PDF trên host khác mà **không gửi Bearer token API**, không log query signature.
6. Cách refresh access token sau 401 mà không refresh storm; cách xử lý 403 và TLS error.
7. Ít nhất mười test HTTP gồm commit trước timeout, 429, 503, cross-origin credential leak, malformed Location, SSRF, vòng redirect và body không replay.

**Gợi ý:** payment POST cần **server-side idempotency**, không chỉ retry ở client; `202` thì poll monitor. Redirect 303 có nghĩa GET, còn 307/308 giữ body/method. Chỉ phát Bearer ở origin/audience đúng; signed URL là capability riêng. Đánh giá client theo **tác động nghiệp vụ, request headers đến từng origin và tổng thời gian**, không chỉ status trả về cuối cùng.

## 13. Ghi nhớ

Retry chỉ an toàn khi **operation replay được**, có giới hạn attempt/deadline và phân loại lỗi. Với POST ghi dữ liệu, dùng `Idempotency-Key` có thực thi phía server hoặc đối soát kết quả, không đánh đồng timeout với rollback.

Redirect không chỉ thay URL: `303` chuyển sang GET, `307/308` giữ method/body, và **bất kỳ hop mới nào cũng là một quyết định bảo mật**. Với Java `HttpClient` hoặc Spring, đặt chính sách redirect/token rõ ràng, bảo vệ TLS, giới hạn tài nguyên và kiểm thử qua hai origin để không vô tình tiết lộ credential.

**Thành công của request gửi đi** không luôn đồng nghĩa server trả dữ liệu đúng schema. Sau 2xx, xác minh `Content-Type`, parse/validate DTO và domain invariant; không retry mù khi JSON có kiểu sai. Đối với 401, có thể refresh token **một lần** bên ngoài retry loop và phát lại request an toàn; với 403 không refresh vòng lặp.

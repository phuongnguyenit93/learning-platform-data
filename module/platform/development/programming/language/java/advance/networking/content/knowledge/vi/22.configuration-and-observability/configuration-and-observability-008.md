# Log của HTTP client, debug JSSE và che dữ liệu xác thực khi chẩn đoán

*Java Advance – networking · Nhóm: Cấu hình và quan sát · Java SE 17+*

## 1. Mục tiêu

Khi ứng dụng Java gọi một HTTP API thất bại, việc bật mọi loại log rồi gửi nguyên file ra ngoài có thể làm lộ token, cookie, mật khẩu, signed URL và dữ liệu cá nhân. Cách chẩn đoán đúng là **phân loại vấn đề theo tầng**, chọn độ chi tiết vừa đủ, và **không tạo bản ghi chứa bí mật ngay từ đầu**.

Ba nguồn quan sát quan trọng trong Java 17:

- **Application-level logging:** ứng dụng tự ghi request ID, HTTP method, route template, kết quả, status code, thời gian, error category. Đây là nơi nên định nghĩa allowlist trường dữ liệu.
- **JDK HTTP client logging:** system property `jdk.httpclient.HttpClient.log` bật nhóm sự kiện của `java.net.http.HttpClient`, gửi qua Java Util Logging (JUL), logger `jdk.httpclient.HttpClient`.
- **JSSE debug:** system property `javax.net.debug` cho biết hoạt động TLS/SSL handshake, trust manager, certificate, TLS records, sessions và các sự kiện liên quan ở tầng bảo mật.

**Không được nhầm:** log HTTP client không phải log JSSE, và application logger đã che secret không có nghĩa JDK, reverse proxy, observability SDK hoặc JSSE tự che secret giống vậy.

~~~text
Business request
     |
     +--> Application log (allowlisted fields)
     |       request_id, method, route_template, status, error_class
     |
     +--> java.net.http.HttpClient (Java 17)
     |       -Djdk.httpclient.HttpClient.log=...
     |       JUL logger: jdk.httpclient.HttpClient
     |
     +--> TLS / JSSE (chỉ nếu thực sự dùng HTTPS/TLS)
     |       -Djavax.net.debug=ssl:handshake:trustmanager
     |
     +--> TCP / proxy / DNS / origin server
             Có logs, metrics và quyền truy cập riêng
~~~

**Nguyên tắc:** chẩn đoán mặc định bằng structured logs an toàn; bật verbose diagnostics **trong thời gian ngắn, trên synthetic traffic hoặc môi trường kiểm soát**; xác định đầu ra đi đâu, ai đọc được và khi nào xóa.

## 2. Log mỗi tầng để trả lời đúng câu hỏi

| Công cụ | Có ích khi | Không tự cung cấp |
|---|---|---|
| Application log | Biết request nào, route nào, latency, HTTP status, timeout/body failure | Toàn bộ chi tiết handshake TLS |
| `jdk.httpclient.HttpClient.log` | Quan sát JDK HTTP client channels, requests, errors, headers, HTTP/2 frames | Behavior của mọi HTTP libraries |
| `javax.net.debug` | Điều tra truststore, TLS protocol/cipher, handshake, mTLS, certificate | Business status 404/500 |
| DNS/TCP/network metrics | Host resolution, connection refused, port, retransmits | HTTP body hợp lệ hay không |
| Proxy logs | CONNECT, 407, routing, proxy failures | App logic đã commit thành công |
| Distributed tracing | Liên kết các spans/độ trễ giữa service | Đảm bảo tự che toàn bộ secret |
| Metrics | Error rate, latency percentiles, retry/timeout counts | Request-level raw forensic details |

Ví dụ phân loại:

- `401 Unauthorized` và `403 Forbidden` là HTTP status từ origin, không mặc định là lỗi TLS.
- `407 Proxy Authentication Required` liên quan xác thực với proxy; với HTTPS, lỗi này có thể xảy ra **ở CONNECT trước TLS tới origin**.
- `SSLHandshakeException` thường xảy ra trước HTTP response, nên có thể **không có status code từ origin**.
- `ConnectException`, `UnknownHostException` hoặc connect timeout cần kiểm tra DNS/TCP/proxy; bật JSSE debug không giúp nếu TLS chưa bắt đầu.
- HTTP `500` có thể là response hoàn chỉnh; đừng coi nó tương đương IOException.
- Client nhận headers 200 rồi đọc body bị lỗi là **body failure sau headers**, không phải “toàn bộ request thành công”.

### 2.1. Đề xuất structured fields cho app log

| Trường | Ví dụ | Ý nghĩa |
|---|---|---|
| `event` | `http_client_response` | Loại sự kiện |
| `request_id` | `r-f3a7` | Liên kết các bản ghi, không phải token |
| `method` | `GET` | HTTP method |
| `route_template` | `/users/{id}` | Không cần ghi raw path/query |
| `service` | `billing-api` | Nhãn service đã được allowlist |
| `http_status` | `503` | Chỉ có khi đã nhận HTTP response |
| `phase` | `dns/connect/tls/headers/body` | Giai đoạn xảy ra lỗi |
| `duration_ms` | `244` | Đo latency |
| `attempt` | `2` | Retry attempt |
| `response_bytes` | `512` | Khối lượng body đã nhận |
| `outcome` | `HTTP_5XX` / `TLS_FAILED` | Nhóm trạng thái |
| `tls_protocol` | `TLSv1.3` | Metadata nếu TLS handshake thành công |
| `body_logged` | `false` | Dễ kiểm toán policy không ghi body |

Không sử dụng raw URL hoặc query làm field mặc định. Một request ID do client gửi cũng có thể chứa CR/LF hoặc nội dung giả mạo; cần validate schema/length hoặc cấp ID phía server.

## 3. JDK HttpClient logging: property và logger chính xác

Oracle Java SE 17 *Java Networking* mô tả `jdk.httpclient.HttpClient.log`: thuộc tính có giá trị là **danh sách category ngăn bởi dấu phẩy**, và JDK gửi logs thông qua `java.util.logging` với logger tên **`jdk.httpclient.HttpClient`**, level **INFO**.

~~~text
-Djdk.httpclient.HttpClient.log=errors
~~~

Property này dành cho **HTTP client của JDK (module java.net.http)**, không áp chung cho `HttpURLConnection`, Apache HttpClient, OkHttp, Netty hoặc Spring WebClient. Nếu ứng dụng dùng thư viện khác, phải tra tài liệu logging đúng implementation.

### 3.1. Các category ở Java 17

| Category | Dùng để xem | Rủi ro |
|---|---|---|
| `errors` | Lỗi ở tầng client | Có thể có endpoint/exception metadata |
| `requests` | Sự kiện request/lifecycle | Có thể lộ URI path/query |
| `headers` | HTTP request/response headers | **Có thể chứa Authorization/Cookie/Set-Cookie/token** |
| `frames` | HTTP/2 frames | Nhiều dữ liệu và implementation details |
| `frames:control` | Control frames | Thông tin HTTP/2 settings/goaway |
| `frames:data` | Data frames | High volume, kiểm soát payload/metadata |
| `frames:window` | Window/flow-control events | Hữu ích khi stalls |
| `frames:all` | Toàn bộ loại frames | Rất verbose |
| `ssl` | Client-side SSL/TLS events | Không thay thế JSSE trust diagnostics |
| `trace` | Trace triển khai JDK | Volume cao, format có thể thay đổi |
| `channel` | Channel/connectivity events | Hữu ích về connection lifecycle |

Danh sách tổng quát được tài liệu Java 17 mô tả:

~~~text
errors,requests,headers,frames:control:data:window,ssl,trace,channel
~~~

Có thể thay `frames:control:data:window` bằng `frames:all`. **Không dùng danh sách category của JDK 26/27 rồi giả định Java 17 cũng có mọi mục.**

### 3.2. Cách bật, theo nguyên tắc tăng dần

Khởi đầu hẹp nhất, ví dụ:

~~~bash
java '-Djdk.httpclient.HttpClient.log=errors' -cp out MyHttpApp
~~~

Nếu cần phân biệt request lifecycle và endpoint, có thể thử trong **sandbox chỉ chứa request giả**:

~~~bash
java '-Djdk.httpclient.HttpClient.log=errors,requests' -cp out MyHttpApp
~~~

Khi cần HTTP/2 troubleshooting sâu:

~~~bash
java '-Djdk.httpclient.HttpClient.log=errors,frames:control:window' -cp out MyHttpApp
~~~

`MyHttpApp` là **tên class minh họa**, không phải file code được cung cấp trong bài. Trong production đang chạy OAuth/JWT/cookies, không bật `headers` hoặc log verbose không kiểm soát. Chỉ bật các nhóm nhiều thông tin như `headers`, `frames:all`, `trace` sau đánh giá bảo mật, dùng dữ liệu tổng hợp/synthetic và log sink hạn chế.

**Không được suy rằng JDK đã redact mọi secret trong mọi version**. Một raw URI trong category `requests` cũng đủ làm lộ query `access_token` dù không bật `headers`.

### 3.3. Cấu hình JUL để nhận INFO logs

Property bật category chỉ là một phần. `java.util.logging` còn có logger levels và handlers. File config ví dụ **`client-logging.properties`**:

~~~properties
handlers = java.util.logging.ConsoleHandler
.level = WARNING
jdk.httpclient.HttpClient.level = INFO
java.util.logging.ConsoleHandler.level = INFO
java.util.logging.ConsoleHandler.formatter = java.util.logging.SimpleFormatter
~~~

Lệnh khởi động:

~~~bash
java '-Djava.util.logging.config.file=client-logging.properties' \
     '-Djdk.httpclient.HttpClient.log=errors' \
     -cp out MyHttpApp
~~~

File config trên phải được người học tạo, nằm ở thư mục thích hợp của môi trường thử. `ConsoleHandler` JUL thường ghi ra **stderr**, không phải nội dung HTTP response. Root WARNING không có nghĩa child logger INFO sẽ bị chặn nếu child logger và handler đã nhận level INFO theo JUL hierarchy; cần kiểm tra cấu hình/bridge thực tế.

Nếu project dùng SLF4J, Logback, Log4j2 hoặc cloud logging agent, JUL logs **không mặc định tự xuất hiện trong cùng sink**. Bridge/handler phải cấu hình đúng, tránh vòng lặp bridge, duplicate events và format không kiểm soát. Đừng trông chờ sửa `java.util.logging.config.file` trong runtime làm mọi logger nhận cấu hình mới như khi startup.

### 3.4. Điều gì xảy ra khi bật raw headers?

Đây là **minh họa đã thay bí mật bằng nhãn**, không dùng credential thật:

~~~http
GET /v1/items?access_token=[SENSITIVE] HTTP/1.1
Authorization: Bearer [SENSITIVE]
Cookie: sid=[SENSITIVE]
X-Api-Key: [SENSITIVE]
~~~

JDK có thể ghi những thông tin chi tiết khác nhau tùy phiên bản, protocol và category. Tầng app tự che header không chứng minh internal JUL đã che. Nếu buộc chẩn đoán header, dùng **synthetic request** trong môi trường cô lập và kiểm tra chính log destination, đừng bật raw header logging cho request của người dùng.

## 4. JSSE debug: nguồn dữ liệu khác HTTP client logs

`javax.net.debug` là Java system property cho Java Secure Socket Extension. Nó giúp biết TLS handshake tiến triển tới đâu, chọn protocol/cipher suite, certificate chain nào được nhận, trust manager chấp nhận hay từ chối, có client certificate mTLS hay không.

Các lệnh sau chỉ là mẫu cho **một ứng dụng HTTPS thật được kiểm soát**. Không dùng lệnh JSSE làm cách sửa HTTP 401/404.

~~~bash
java '-Djavax.net.debug=ssl:handshake' -cp out MyHttpsApp
~~~

Để khảo sát certificate trust:

~~~bash
java '-Djavax.net.debug=ssl:handshake:trustmanager' -cp out MyHttpsApp
~~~

Tài liệu Java 17 cho phép các debug option sau `ssl` phân cách bằng dấu hai chấm hoặc dấu phẩy. Output JSSE có thể chứa hostnames, certificate subjects, các algorithms/handshake messages và những thông tin cấu hình nội bộ; cần xử lý như log có sensitivity cao.

### 4.1. Chọn JSSE option theo vấn đề

| Option | Nội dung | Khi nên dùng |
|---|---|---|
| `ssl` | Debug SSL/TLS tổng quát | Test nhỏ |
| `handshake` | Handshake messages | Lỗi negotiate/handshake |
| `trustmanager` | Trust manager và đường dẫn certificate trust | `PKIX path building failed` |
| `keymanager` | Client certificate/key manager selection | Mutual TLS |
| `sslctx` | SSLContext construction | Sai config SSLContext |
| `defaultctx` | Default SSL initialization | Nghi dùng sai default context |
| `session` | TLS session activity | Session reuse |
| `sessioncache` | Session cache trace | Resumption troubleshooting |
| `record` | Record-level TLS traces | Chỉ khi chẩn đoán rất sâu |
| `handshake:data` | Hex dump handshake content | Verbose, có metadata nhạy cảm |
| `handshake:verbose` | Handshake log chi tiết | Test cô lập |
| `record:packet` | Raw encrypted TLS packet metadata/bytes | Tránh trên traffic thực |
| `record:plaintext` | Dump TLS record plaintext trong debug | **Đặc biệt nguy hiểm, có thể lộ nội dung** |
| `all` | Tất cả debug | Không bật mặc định |

Ở Java 17, `javax.net.debug` có thể phát qua cơ chế JSSE debug/System.Logger (thường thấy ở **stderr**), không tự giống một logger JUL `jdk.httpclient.HttpClient` về format và đường đi. Tùy JDK, chi tiết output khác nhau; **đừng viết parser phụ thuộc đúng thứ tự/dòng log TLS**.

### 4.2. Những vấn đề không cần bật JSSE

- `UnknownHostException`: hostname/DNS chưa phân giải.
- `ConnectException` / connect timeout: TCP chưa established.
- Proxy `407` trong CONNECT: proxy authentication có thể bị từ chối **trước khi TLS tới origin**.
- HTTP `401` sau khi nhận response: origin authentication.
- HTTP `429` / `503`: rate limits/overload.
- HTTP body `IOException` sau khi TLS/headers có thể là stream/transport failure, không nhất thiết handshake failure.

Chỉ bật JSSE debug khi lỗi thật sự có tính chất TLS hoặc khi các logs cấp cao chỉ ra handshake/protocol/trust path cần điều tra.

### 4.3. Đọc một số lỗi TLS phổ biến

| Lỗi/triệu chứng | Hướng xem logs | Điều cần xác minh |
|---|---|---|
| `SSLHandshakeException: PKIX path building failed` | `ssl:handshake:trustmanager` | CA/truststore được app dùng, certificate chain, expired CA |
| `No subject alternative names matching` | Handshake + hostname/SAN | Hostname và SAN đúng |
| `Received fatal alert: handshake_failure` | Handshake/KeyManager khi mTLS | TLS versions, cipher suites, peer policy, client cert |
| `protocol_version` | Handshake | Versions được client/server hỗ trợ |
| `certificate_unknown` / `bad_certificate` | Handshake/trust direction | Alert phía nào gửi, certificate nào bị từ chối |
| mTLS không có client certificate | `ssl:handshake:keymanager` | Keystore/private-key identity được cấu hình đúng |
| TLS thành công nhưng HTTP 403 | App HTTP status | Authorization/permissions, không “sửa” TLS |
| Proxy CONNECT trả 407 | HTTP/proxy logs | `Proxy-Authenticate`/credentials cho proxy |

**Không dùng trust-all `X509TrustManager`, tắt hostname verification, chuyển sang TLS versions yếu hay vô hiệu mTLS để làm error biến mất.** Những “fix” đó làm giảm tính xác thực của kết nối. Thay vào đó kiểm tra CA chain, truststore, endpoint identity, cert SAN, thời gian và policy TLS chính thức.

### 4.4. Metadata TLS sau kết nối thành công

Java 17 `HttpResponse.sslSession()` có thể trả `Optional<SSLSession>` nếu response có TLS. Khi đã nhận HTTPS response, có thể lấy **protocol/cipher suite đã thương lượng** như metadata an toàn hơn việc dump toàn bộ handshake:

~~~java
// Trích đoạn, response là HttpResponse<?> của một HTTPS request.
String tlsVersion = response.sslSession()
        .map(session -> session.getProtocol()).orElse("none");
String cipherSuite = response.sslSession()
        .map(session -> session.getCipherSuite()).orElse("none");
~~~

Không mặc định ghi raw certificate chain, session ID, peer principal hoặc private key. Nếu handshake thất bại trước khi có response, `sslSession()` sẽ không cung cấp object từ một response vốn chưa tồn tại.

**Với HTTP plain, `sslSession().isPresent()` thường là false**. Đây là kết quả đúng, không phải JSSE debug hỏng.

## 5. Các loại dữ liệu cần loại khỏi logs

| Nguồn | Thông tin có nguy cơ | Policy |
|---|---|---|
| `Authorization` | Basic credentials, JWT, OAuth access token | Không log giá trị |
| `Proxy-Authorization` | Proxy username/password/token | Không log giá trị |
| `Cookie` | Session ID, CSRF token, hành vi cá nhân | Không log raw |
| `Set-Cookie` | Session cookies | Không log raw |
| `X-Api-Key` / `X-Auth-Token` | API key/custom bearer token | Không log giá trị |
| `X-CSRF-Token` | CSRF/session value | Không log raw |
| `Location` | Signed redirect URL, auth code, token query | Không log raw URL |
| Query `access_token`, `refresh_token`, `id_token` | OAuth/token | Loại cả query khỏi event |
| Query `client_secret`, `password`, `api_key` | Password/API credentials | Loại cả query |
| Query `signature` / `X-Amz-Signature` | Signed URL signature | Loại raw query, path nếu nhạy cảm |
| URI userinfo / path token | `user:pass@host`, reset/invite token | Route template thay raw URI |
| HTTP bodies | Password, OTP, PII, payment data, auth responses | Không log body theo mặc định |
| Exceptions | Exception message có URL/query/headers | Log loại lỗi/phases thay raw message |
| TLS diagnostics | Certificate metadata, internal hostnames | Restrict debug/sink/retention |
| Distributed tracing baggage | User-supplied keys, secrets | Allowlist/validate/truncate |

Đừng quên **custom auth headers và query names riêng của sản phẩm**; denylist vài tên header không đủ. Dùng allowlist fields có xác nhận security để tránh phải dự đoán mọi cách secret có thể được đặt.

### 5.1. Vì sao không ghi URI nguyên văn?

~~~text
https://api.example.test/v1/reset/TOKEN_VALUE?access_token=TOKEN_VALUE
https://user:password@api.example.test/v1/accounts
https://storage.example.test/object?X-Amz-Signature=SIGNED_VALUE
~~~

Đây là các URI **minh họa bằng chuỗi giả**, không phải endpoint thật. Chỉ log một nhãn kiểu `service=account-api` và route template như `/v1/reset/{token}`. Kể cả khi query không chứa token, nó vẫn có thể chứa email, số điện thoại, tên, nội dung tìm kiếm hoặc dữ liệu cá nhân.

Một số HTTP clients loại fragment khỏi network request, nhưng **raw URI trong Java object/logger vẫn có thể bao gồm fragment/user-info**. Đừng mặc định mọi thành phần của URL là dữ liệu công khai.

### 5.2. JWT, prefix/suffix và hashing

JWT là một dạng token có các phần Base64url; payload không được mã hóa chỉ vì nhìn như chuỗi ngẫu nhiên. Đừng log “8 ký tự đầu/cuối” như một phương pháp che đủ an toàn. Token ngắn hoặc có cấu trúc vẫn có thể bị nhận diện, dò hoặc lạm dụng.

Nếu cần nối các sự kiện cùng authentication session, cấp **opaque correlation ID** riêng. Việc dùng HMAC/keyed token fingerprint chỉ nên làm sau review; không lấy raw SHA-256 của token làm giải pháp tự động bảo mật, đặc biệt nếu secret có entropy thấp.

### 5.3. Che trước khi tạo log record

Phản ví dụ:

~~~java
// KHÔNG NÊN: dễ lộ raw query/headers/body/exception.
LOG.info("uri=" + request.uri());
LOG.info("headers=" + request.headers().map());
LOG.info("request=" + request);
LOG.info("body=" + response.body());
LOG.warning("failure=" + exception);
~~~

Mẫu định hướng:

~~~java
// TRÍCH ĐOẠN: các biến safe... được allowlist/validate từ trước.
LOG.info("event=http_response"
    + " request_id=" + safeRequestId
    + " method=" + safeMethod
    + " route=" + approvedRouteTemplate
    + " status=" + httpStatus
    + " body_logged=false");
~~~

Các đoạn trên không phải chương trình độc lập; `LOG` và các biến tương ứng thuộc ứng dụng. Đặc biệt, đừng dùng `Throwable.toString()`, `HttpRequest.toString()` hoặc `HttpHeaders.map().toString()` làm dữ liệu an toàn theo mặc định.

### 5.4. Vì sao redaction ở Formatter/log collector chưa đủ?

~~~text
unsafe request / secret
        |
        v
raw log event
        |
        +-- async queue / backup / alternate handler
        |
        +-- regex redaction --> log file
~~~

Nếu chỉ lọc ở cuối pipeline, raw value **đã đi qua object log** và có thể được capture bởi handler/agent khác. Regex dễ bỏ sót tên header custom, percent-encoded queries, JSON nested fields, multiline values và exception chains. **Tạo event chỉ chứa allowlisted fields trước**; lọc bổ sung ở handler/collector là lớp phòng vệ thứ hai, không thay thế.

### 5.5. Chống log forging

Raw `X-Request-ID`, User-Agent hoặc request URI có thể chứa ký tự `\r`/`\n`, khiến logs xuất hiện dòng giả. Với structured logging:

- Dùng JSON serializer/encoder đáng tin thay vì tự in raw input.
- Validate/giới hạn độ dài ID, enum, route names.
- Escape newline, tab, control characters và ký tự không hợp lệ.
- Không để raw URI hay user ID thành metric label không giới hạn cardinality.
- Tránh in secret vào assertion failure/log test output; chỉ báo boolean/kết quả.

## 6. Demo Java 17+: ứng dụng ghi log an toàn dù request có token giả

Ví dụ chạy **100% trên loopback `127.0.0.1`**: `HttpServer` nhận request HTTP có `Authorization`, `Cookie` và query token **giả/synthetic**. Server kiểm tra credentials giả để chứng minh request đã được gửi đủ, rồi trả HTTP 200.

Ứng dụng **không log** raw URI, headers hay body. Nó chỉ ghi route template và các nhãn `[OMITTED]` / `[REDACTED]`. Để output không phụ thuộc timestamp, demo dùng `java.util.logging.Handler` đơn giản ghi message vào console và `StringBuilder`. **Handler này không tự động redact**; source log an toàn vì ứng dụng chỉ tạo message từ fields cho phép.

**Không chạy demo với flags verbose `-Djdk.httpclient.HttpClient.log=errors,requests,headers` trong môi trường thật**, vì request có các giá trị mô phỏng token để test sự khác nhau giữa app log và internal JDK logging.

Tạo **`SafeHttpDiagnosticsDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.logging.Handler;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;

public class SafeHttpDiagnosticsDemo {
    private static final String FAKE_SECRET = "SYNTHETIC_SECRET_NOT_REAL";
    private static final Logger LOG = Logger.getLogger("training.http.safe");
    private static final StringBuilder CAPTURED = new StringBuilder();

    static final class SafeOutputHandler extends Handler {
        @Override public synchronized void publish(LogRecord record) {
            if (!isLoggable(record)) return;
            String message = record.getMessage();
            CAPTURED.append(message).append('\n');
            System.out.println("APP " + message);
        }
        @Override public void flush() {}
        @Override public void close() {}
    }

    private static String routeLabel(URI uri) {
        // Approved route template; do not log the query or raw user path.
        return "/diag".equals(uri.getPath()) ? "/diag" : "[OTHER_ROUTE]";
    }

    private static void reply(HttpExchange exchange, int status)
            throws IOException {
        byte[] bytes = "OK".getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);
        SafeOutputHandler safeHandler = new SafeOutputHandler();
        safeHandler.setLevel(Level.INFO);
        LOG.addHandler(safeHandler);

        AtomicBoolean sawDemoCredentials = new AtomicBoolean(false);
        HttpServer server = HttpServer.create(new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/diag", exchange -> {
            boolean valid = ("Bearer " + FAKE_SECRET).equals(
                    exchange.getRequestHeaders().getFirst("Authorization"))
                    && ("sid=" + FAKE_SECRET).equals(
                    exchange.getRequestHeaders().getFirst("Cookie"));
            sawDemoCredentials.set(valid);
            reply(exchange, valid ? 200 : 401);
        });
        server.start();
        try {
            URI target = URI.create("http://127.0.0.1:" +
                    server.getAddress().getPort() +
                    "/diag?access_token=" + FAKE_SECRET + "&mode=demo");
            HttpRequest request = HttpRequest.newBuilder(target)
                    .timeout(Duration.ofSeconds(3))
                    .header("Authorization", "Bearer " + FAKE_SECRET)
                    .header("Cookie", "sid=" + FAKE_SECRET)
                    .GET().build();
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3)).build();

            LOG.info("http_request id=demo-001 method=" + request.method()
                    + " route=" + routeLabel(request.uri())
                    + " query=[OMITTED] authorization=[REDACTED]"
                    + " cookie=[REDACTED]");
            HttpResponse<String> response = client.send(
                    request, HttpResponse.BodyHandlers.ofString());
            LOG.info("http_response id=demo-001 status=" + response.statusCode()
                    + " version=" + response.version()
                    + " body=[NOT_LOGGED]");
            System.out.println("CHECK serverSawDemoCredentials="
                    + sawDemoCredentials.get());
            System.out.println("CHECK appLogContainsSecret="
                    + CAPTURED.toString().contains(FAKE_SECRET));
            System.out.println("CHECK tlsSessionPresent="
                    + response.sslSession().isPresent());
        } finally {
            server.stop(0);
            LOG.removeHandler(safeHandler);
        }
    }
}
~~~

Biên dịch/chạy với **JDK 17 trở lên**; `jdk.httpserver` là module dành cho local test server:

~~~bash
javac --release 17 --add-modules jdk.httpserver SafeHttpDiagnosticsDemo.java
java --add-modules jdk.httpserver SafeHttpDiagnosticsDemo
~~~

**Stdout chính xác đã kiểm chứng khi biên dịch `--release 17` và chạy trên OpenJDK 24:**

~~~text
APP http_request id=demo-001 method=GET route=/diag query=[OMITTED] authorization=[REDACTED] cookie=[REDACTED]
APP http_response id=demo-001 status=200 version=HTTP_1_1 body=[NOT_LOGGED]
CHECK serverSawDemoCredentials=true
CHECK appLogContainsSecret=false
CHECK tlsSessionPresent=false
~~~

### 6.1. Giải nghĩa output

| Dòng | Kết luận |
|---|---|
| `APP http_request ... [OMITTED] ... [REDACTED]` | Log ứng dụng không chứa giá trị query/header của request |
| `APP http_response ... status=200` | Client nhận HTTP 200 và chỉ log metadata |
| `serverSawDemoCredentials=true` | Server thực sự nhận credentials thử nghiệm |
| `appLogContainsSecret=false` | Chuỗi `CAPTURED` của **application logger** không chứa fake token |
| `tlsSessionPresent=false` | HTTP loopback không TLS, do đó không có SSLSession |

**Điểm cần hiểu đúng:** kiểm tra `CAPTURED` không kiểm tra nội dung của reverse proxy, JDK HTTP internal logging, JSSE, OS hoặc external monitoring agent. Mục tiêu của test là chứng minh allowlist tại **application logging boundary**, không tuyên bố toàn bộ hệ thống không bao giờ ghi token.

### 6.2. Vì sao không test JSSE bằng cùng server?

Server của ví dụ là **HTTP plaintext**. Không có `SSLSocket`/TLS handshake nên `javax.net.debug=ssl:handshake` sẽ không tạo TLS handshake cho request này. Muốn kiểm thử JSSE, dùng **HTTPS endpoint hợp lệ do bạn kiểm soát**, với truststore/keystore thử nghiệm và không chứa credential thật. Tuyệt đối không thêm trust-all SSLContext chỉ để ép có một output.

## 7. Quy trình chẩn đoán theo từng bước

### Bước 1: phân loại kết quả ở ứng dụng

Ghi safe fields: `request_id`, `route_template`, `method`, `status` nếu có, `phase`, `elapsed_ms` và `error_category`. Đặc biệt phân biệt:

~~~text
DNS failed -----------> không có HTTP origin response
TCP connect failed ---> không có HTTP origin response
TLS handshake failed -> thường chưa có HTTP origin response
HTTP 401 / 403 -------> có HTTP response thật
HTTP 407 -------------> proxy authentication response
HTTP 503 -------------> server/proxy overload response
HTTP headers received -> body có thể chưa hoàn tất
HTTP body EOF --------> body completed
body IOException -----> body failed dù trước đó có status 200
~~~

### Bước 2: bật HTTP client internal logging hẹp

Nếu request được tạo bởi `java.net.http.HttpClient` của JDK 17, bắt đầu với `errors`. Xác nhận JUL handler nhận INFO. Nếu cần thêm `requests`, hãy kiểm tra URI không có raw tokens/PII hoặc chỉ dùng synthetic traffic. `headers` và `frames:all` chỉ nên bật trong isolated test với log sink hạn chế.

### Bước 3: với lỗi TLS, bật JSSE có mục tiêu

Bắt đầu `ssl:handshake`. Nếu có `PKIX path building failed`, bổ sung `trustmanager`. Nếu lỗi mTLS client certificate selection, cân nhắc `keymanager`. Không bật `record:plaintext` hoặc `all` cho lưu lượng có thông tin thực.

### Bước 4: xử lý đúng nguyên nhân, tắt debug

Sửa CA/truststore, hostname/SAN, mTLS identity, proxy credentials hoặc network route tùy lỗi. Sau khi xác nhận, **khôi phục log flags**, giới hạn retention debug dumps và xóa/chỉnh quyền truy cập theo chính sách, không gửi raw files lên ticket/chat không được phép.

## 8. Kết hợp TLS session metadata với request logs

Sau HTTPS response thành công, Java `HttpResponse.sslSession()` có thể cho biết metadata TLS. Nhưng không dùng `SSLSession.getId()` làm giá trị log mặc định; session identifiers là thông tin cần kiểm soát. Trong event structured logs, chỉ ghi `tls_protocol=TLSv1.3`, `cipher_suite=...` nếu thực sự cần, và xử lý logger field lengths.

**Một kết nối HTTP/2 có thể mang nhiều HTTP requests**, và TLS session có thể được reuse/resume. Không coi mỗi request là một TLS handshake mới, cũng không coi một handshake log là một HTTP request hoàn chỉnh.

Nếu status 200 nhưng `BodyHandlers.ofInputStream()` trả sớm sau headers, application request log nên tách `response_headers_received` và `body_completed`. Đừng giải phóng toàn bộ trace/metrics span ở headers nếu mục tiêu giám sát full body consumption.

## 9. Những sai lầm phổ biến

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| Bật `headers` trong production để tìm lỗi 401 | Có thể lộ token/cookie của nhiều request | Chỉ synthetic traffic, dùng safe auth result metadata |
| App logger có redact nên JDK internal logging chắc an toàn | Hai nguồn log độc lập | Kiểm soát từng handler/sink |
| `jdk.httpclient.HttpClient.log` có hiệu lực với OkHttp/Apache | Đó là property của JDK HttpClient | Kiểm tra HTTP client thực tế |
| Bật `javax.net.debug=all` cho mọi service | Rất nhiều metadata, có thể có dữ liệu nhạy cảm | Bật handshake/trustmanager hẹp |
| Dùng `record:plaintext` để “xem HTTP body” | Lộ ứng dụng plaintext sau TLS | Không dùng với traffic thật |
| Chẩn đoán HTTP 401 bằng JSSE | 401 là response ở HTTP layer | Application HTTP status/credential scope |
| `SSLHandshakeException` mà log status 500 | Thường không có HTTP origin response | Separate network/TLS error category |
| Log raw `HttpRequest.toString()` | URI có thể chứa token/query | Dùng route template và safe fields |
| Log response body cho mọi 4xx | Có thể chứa PII, tokens, internal errors | Log status và approved error code |
| Che 4 ký tự cuối token là an toàn | Prefix có thể nhạy cảm | Bỏ token, dùng correlation ID khác |
| Regex ở Formatter là giải pháp duy nhất | Raw secrets đi qua nhiều logger/sinks trước đó | Allowlist tại source và test sinks |
| Dùng `exception.toString()` mặc định | Có thể chứa raw URL/headers | Log exception class/category đã validate |
| Log `X-Request-ID` nguyên dạng | Có thể chứa CR/LF hoặc rất dài | Validate, normalize, cap length |
| Không tắt verbose logs sau điều tra | Rủi ro rò rỉ và chi phí log | Time-box và khôi phục flags |
| Trust-all để sửa PKIX | Làm mất peer authentication | Sửa truststore/certificate chain |
| Tắt hostname verification để sửa SAN | Tạo rủi ro MITM | Dùng certificate đúng hostname |
| Xem stderr là log an toàn | Container/agents có thể ship stderr ra cloud | Xem toàn bộ ingestion pipeline |
| Đặt status thành SUCCESS khi có headers 200 | Body stream có thể fail sau đó | Log terminal body completion riêng |

## 10. Test cho logging policy

Sử dụng **sentinel values giả** ở nhiều vị trí, sau đó kiểm tra application log capture, JUL output/sinks được kiểm soát, reverse proxy request logs và exported traces:

~~~text
Authorization: Bearer FAKE_TOKEN_A
Proxy-Authorization: Basic FAKE_TOKEN_B
Cookie: sid=FAKE_COOKIE_C
X-Api-Key: FAKE_API_KEY_D
URI: /reset/FAKE_PATH_TOKEN?access_token=FAKE_QUERY_E
Body: {"password":"FAKE_PASSWORD_F"}
~~~

Test fail nếu bất cứ sentinel nào xuất hiện trong log sink không được phép. Không ghi nguyên sentinel vào test failure report; chỉ ghi tên loại dữ liệu hoặc số sự kiện vi phạm.

Ngoài các giá trị thông thường, cần test:

- Header case-insensitive, tên custom header lạ.
- URL-encoded, percent-encoded, fragment, user-info, redirects.
- CR/LF/control characters trong request IDs hoặc headers.
- Nested JSON, arrays, body compression, multipart uploads.
- Exceptions chứa raw URL trong cause chain.
- Logs sinh bởi third-party SDK và auto-instrumentation.
- Tương quan request trace IDs mà không ghi session IDs.
- Retention/export permissions, kể cả log backups và support tickets.

**Không dùng một kết quả kiểm thử `appLogContainsSecret=false` làm chứng nhận tất cả logs đều an toàn**: test này chỉ xét phạm vi `CAPTURED` của ví dụ.

## 11. Chi phí và vận hành debug logs

Verbose HTTP/2 frames, SSL record-level debug hoặc full request logging có thể tạo lượng log rất lớn và tác động CPU, disk, network egress, storage, latency. Một collector đầy queue có thể làm chậm ứng dụng hoặc mất logs. Hơn nữa, log archives được nhân bản qua backups và nhiều hệ thống observability.

Hãy định nghĩa trước:

| Policy | Tối thiểu cần rõ |
|---|---|
| Người được phép bật | Owner/on-call có quyền |
| Phạm vi | Một môi trường/instance/endpoint hoặc synthetic traffic |
| Dữ liệu | Cho phép log những fields/category nào |
| Thời lượng | Khoảng bật tối đa, ngày hết hạn |
| Nơi lưu | Restricted sink, encrypted transfer/storage |
| Quyền truy cập | RBAC, audit log truy cập |
| Retention | Xóa theo policy, kể cả bản sao/bản xuất |
| Volume controls | Sampling, size/line limits, disk quotas |
| Khôi phục | Tắt debug và kiểm tra flags sau incident |

Không gửi nguyên JSSE handshake dump hoặc HTTP headers chứa token vào public issue, chat hay email. Trước khi chia sẻ, chỉ trích xuất **sanitized excerpt** và rà soát nội dung nhạy cảm.

## 12. Checklist thực hành

**Cấu hình:** xác định JDK runtime và client library; thử `jdk.httpclient.HttpClient.log=errors` cùng JUL logger INFO trong sandbox; chỉ dùng `javax.net.debug` cho TLS; đảm bảo flags nằm trong JVM đang chạy ứng dụng.

**Chẩn đoán:** phân biệt HTTP status, proxy 407, DNS/TCP lỗi, TLS handshake failure, body fail. Thu thập correlation ID, phase, status, latency, TLS version nếu có, tuyệt đối không raw secrets.

**Bảo mật:** bỏ query/raw path/token khỏi logs; không in `Authorization`/`Cookie`/`Set-Cookie`/`Proxy-Authorization`; không dùng TLS record plaintext; bảo vệ JUL/JSSE/proxy/observability sinks; chống log forging và data exfiltration.

**Sau xử lý:** tắt verbose flags, kiểm tra output của client đã đúng, không bỏ TLS certificate/hostname checks, chạy redaction tests và tuân retention/debug dump access policy.

## 13. Câu hỏi tự kiểm tra

**1. `jdk.httpclient.HttpClient.log` thuộc API nào?** Chỉ diagnostic của JDK `java.net.http.HttpClient`.

**2. Java 17 sử dụng logger nào và level gì?** JUL `jdk.httpclient.HttpClient`, INFO.

**3. Category Java 17 gồm những gì?** `errors,requests,headers,frames,ssl,trace,channel`; frames có `control,data,window,all`.

**4. Vì sao `headers` nhạy cảm?** Có thể chứa Authorization, Cookie, API keys và signed values.

**5. Vì sao `requests` cũng có rủi ro?** URI có thể chứa tokens hoặc PII trong path/query.

**6. `javax.net.debug` cho biết gì?** TLS/JSSE diagnostics, không phải business HTTP response status.

**7. Khi nghi ngờ PKIX trust failure nên chọn gì?** `ssl:handshake:trustmanager`.

**8. Vì sao tránh `ssl:record:plaintext`?** Có thể lộ plaintext application data.

**9. HTTP proxy 407 có nhất thiết là lỗi JSSE?** Không; đó là proxy authentication và có thể xảy ra trước TLS.

**10. SSLHandshakeException có chắc có HttpResponse.statusCode()?** Không; thường handshake lỗi trước HTTP response.

**11. Nên sửa certificate hostname mismatch như thế nào?** Sửa hostname/SAN/certificate; không tắt verification.

**12. Demo có dùng HTTPS và in JSSE handshake?** Không, dùng HTTP loopback và `tlsSessionPresent=false`.

**13. `appLogContainsSecret=false` chứng minh gì?** Chỉ các app logs do `CAPTURED` giữ không chứa sentinel giả.

**14. Handler `SafeOutputHandler` có tự che secret không?** Không; app code chọn an toàn trước khi log.

**15. Vì sao không log raw `HttpRequest.headers().map()`?** Header map có thể chứa nhiều credential values.

**16. Có nên chỉ dùng regex che ở log collector?** Không; secret có thể đã qua queues/handlers/sinks khác.

**17. Có thể in token prefix rồi hash suffix cho an toàn?** Không mặc định; nên loại token hoặc dùng opaque correlation ID riêng.

**18. Vì sao cần test query/path?** Secrets có thể nằm trong URL thay vì Authorization.

**19. Có thể log Throwable.toString() an toàn?** Không bảo đảm, vì có thể chứa URI/token.

**20. Khi hoàn tất debugging phải làm gì?** Tắt verbose flags, xác minh cấu hình TLS đúng, xử lý log artifacts theo retention/access policy.

## 14. Tài liệu chính thức

- [Oracle Java SE 17 – Java Networking](https://docs.oracle.com/en/java/javase/17/core/java-networking.html): `jdk.httpclient.HttpClient.log`, categories và logger `jdk.httpclient.HttpClient` at INFO.
- [Oracle Java SE 17 – JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): `javax.net.debug`, handshake, trustmanager, session/record debug, TLS diagnostics.
- [Java SE 17 – java.util.logging.Logger](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/Logger.html): JUL logger, levels/handlers.
- [Java SE 17 – java.util.logging.LogManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.logging/java/util/logging/LogManager.html): JUL configuration file.
- [Java SE 17 – HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): send/sendAsync, HTTP client lifecycle.
- [Java SE 17 – HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): `statusCode`, `sslSession`, body timing.
- [Java SE 17 – SSLSession](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLSession.html): `getProtocol`, `getCipherSuite`.
- [Java SE 17 – SSLHandshakeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLHandshakeException.html): TLS handshake failures.
- [Java SE 17 – HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): loopback test HTTP server.
- [OWASP – Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): secrets/PII exclusions, log injection, access control và retention.
- [OWASP – Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): tránh ghi raw session IDs và sử dụng correlation an toàn.

**Kết luận:** **Application-level structured logs với allowlisted fields** là lớp quan sát mặc định. Khi cần, bật `jdk.httpclient.HttpClient.log` để xem hoạt động nội bộ của JDK HTTP client, và `javax.net.debug` để điều tra JSSE/TLS có mục tiêu. **Không ghi raw credentials/URI/bodies**, không tin regex ở cuối pipeline là đủ, không vô hiệu TLS verification, và luôn quản lý phạm vi, quyền truy cập, chi phí và vòng đời debug logs.

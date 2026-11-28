# HMAC với Spring MVC: tích hợp xác thực request trước controller

## 1. Bài toán và mục tiêu

**Spring MVC** cung cấp mô hình xử lý HTTP dựa trên Servlet: request đi qua các filter, được định tuyến đến handler/controller, chuyển đổi dữ liệu đầu vào rồi thực thi nghiệp vụ. Với một API máy–máy, client có thể dùng **HMAC request authentication** thay vì username/password: hai phía chia sẻ một secret; client ký **canonical request** và gửi chữ ký trong HTTP header. Server tái tạo canonical request, tra đúng secret và xác minh.

Thách thức không nằm riêng ở lệnh `Mac.getInstance("HmacSHA256")`. Một tích hợp đúng với Spring MVC phải trả lời được:

- Xác thực nên chạy ở **Servlet filter**, Spring Security filter hay MVC `HandlerInterceptor`?
- Làm thế nào băm đúng **body bytes** mà controller vẫn đọc được `@RequestBody`?
- URI, query, header và body đã đi qua gateway/proxy được canonical hóa thế nào để hai phía ký **cùng một chuỗi byte**?
- Key ID chọn đúng shared secret nào khi có nhiều client và nhiều key version?
- Timestamp/nonce được kiểm tra và ghi nhận ra sao để chống replay ở nhiều instance?
- Sau HMAC thành công, ai quyết định client có quyền gọi endpoint, thao tác trên resource hoặc tenant nào?
- Trả lỗi 401, 403, 413 và lỗi hạ tầng như thế nào mà không lộ thông tin bí mật?

Ví dụ: đối tác `partner-a` gọi `POST /api/hmac/orders` để tạo đơn hàng. Nếu HMAC đúng nhưng body bị filter đọc mất, `@RequestBody` sẽ gặp lỗi. Nếu HMAC đúng nhưng controller tin `X-Tenant-Id` tự khai, một đối tác có thể truy cập tenant khác. Nếu nonce chỉ lưu trong bộ nhớ của một instance, một request hợp lệ có thể bị phát lại sang instance khác.

**Mục tiêu bài học:** tích hợp HMAC vào vòng đời Spring MVC một cách nhất quán: *xác minh trước nghiệp vụ, bảo toàn dữ liệu request, dựng danh tính đáng tin cậy và phân quyền độc lập*. Các ví dụ dùng **Java 17, Spring MVC trên Jakarta Servlet và Spring Security 6**; phần mã minh họa những ranh giới chính chứ không thay thế toàn bộ cấu hình production.

## 2. Luồng HTTP request trong ứng dụng Spring MVC

Một ứng dụng Spring Boot 3 dùng Spring MVC và Spring Security có luồng điển hình:

~~~mermaid
sequenceDiagram
    participant C as HMAC Client
    participant P as Proxy / Gateway
    participant F as Servlet & Security Filters
    participant A as HMAC Authentication
    participant M as DispatcherServlet
    participant H as MVC Controller
    participant S as Business Service
    C->>P: HTTP request + keyId + timestamp + nonce + HMAC
    P->>F: Forward request theo hợp đồng
    F->>F: Giới hạn và giữ raw body bytes
    F->>A: Credential lookup + canonical request
    A->>A: HMAC, trạng thái key, timestamp, nonce
    alt Xác thực thất bại
        A-->>C: 401 / lỗi phù hợp
    else Xác thực thành công
        A->>F: Principal đã xác thực
        F->>M: Tiếp tục filter chain
        M->>H: HandlerMapping + @RequestBody
        H->>S: Phân quyền và xử lý nghiệp vụ
        S-->>C: HTTP response
    end
~~~

Thứ tự quan trọng:

1. **Filter/FilterChain** chạy trước `DispatcherServlet`. Spring Security thường dùng `FilterChainProxy` và các `SecurityFilterChain` để xử lý xác thực, phân quyền.
2. **`DispatcherServlet`** chọn handler qua `HandlerMapping`; các `HandlerInterceptor` chạy trong cơ chế MVC quanh handler.
3. **`HttpMessageConverter`** đọc body cho tham số `@RequestBody`, thường sau khi chọn handler và trước lúc gọi phương thức controller.
4. **Controller/service** xử lý logic nghiệp vụ. Lúc này `Authentication` trong `SecurityContext` phải phản ánh danh tính đã xác thực, không phải header người gửi tự khai.

Như vậy, vị trí thích hợp nhất để thực thi **điều kiện bắt buộc trước mọi nghiệp vụ** thường là filter trong Spring Security chain. MVC controller có thể đọc principal đã xác thực và gọi lớp authorization nghiệp vụ, nhưng không nên là nơi đầu tiên quyết định HMAC có đúng không.

## 3. Chọn điểm tích hợp: Filter, Interceptor, Advice hay Controller?

| Cơ chế | Chạy ở đâu | Phù hợp với HMAC? | Cảnh báo |
| --- | --- | --- | --- |
| Servlet `Filter` | Trước `DispatcherServlet` | Có, khi tự xây cơ chế xác thực | Phải tự tích hợp security context và lỗi |
| `OncePerRequestFilter` trong Spring Security | Trong `SecurityFilterChain` | **Đề xuất cho servlet API HMAC** | Cần xử lý body và exception đúng thứ tự |
| `AuthenticationManager` + `AuthenticationProvider` | Được filter gọi | Có, giúp tách logic xác thực khỏi HTTP adapter | Không tự đọc request, không tự set context nếu custom filter gọi |
| MVC `HandlerInterceptor` | Sau khi MVC chọn handler | Hữu ích cho quan sát/log/thông tin handler | Không nên là ranh giới HMAC duy nhất |
| `RequestBodyAdvice` | Quanh `HttpMessageConverter` | Hỗ trợ kiểm soát payload ở tầng chuyển đổi | Không thay thế filter xác thực trước handler |
| `@ControllerAdvice` | Chuyển exception sang response | Dùng cho lỗi MVC nghiệp vụ | Không chắc bắt được lỗi filter chạy trước MVC |
| Controller `@PostMapping` | Khi đã vào handler | Đọc principal, thực thi nghiệp vụ | Không tự tin header HMAC làm danh tính |
| `WebFilter` của Spring WebFlux | Trong reactive stack | Phù hợp **WebFlux**, không phải Spring MVC Servlet | Không trộn API Servlet với `ServerWebExchange` |

### Vì sao không chỉ dùng HandlerInterceptor?

`HandlerInterceptor.preHandle` chạy trong vòng đời Spring MVC. Nó có thể thấy handler đã chọn, nhưng vẫn ở **sau Servlet filters**, và thường không phải nơi phù hợp để đọc request body trước `@RequestBody`. Nếu chỉ bảo vệ một tập controller bằng interceptor, những đường đi không qua mapping tương ứng hoặc endpoint do framework khác xử lý có thể bị bỏ sót.

Một `HandlerInterceptor` cũng không tự động trở thành một phần của cơ chế `AuthenticationManager`/Spring Security authorization. Có thể tự tích hợp nhưng sẽ tăng rủi ro sai sót. Nên đặt bước xác thực HMAC trong `SecurityFilterChain`, còn interceptor dùng cho việc cần biết handler cụ thể **sau khi xác thực**, không coi interceptor là lớp bảo vệ duy nhất.

## 4. Hợp đồng HMAC: canonical request phải được cố định

Ví dụ request cho một API JSON:

~~~http
POST /api/hmac/orders?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-a
X-Key-Id: partner-a-k4
X-Tenant-Id: tenant-a
X-Timestamp: 2026-11-28T04:00:00Z
X-Nonce: c5c1db08-a6be-48f0-9ef7-9d8726a1ef40
X-Signature: <base64-hmac-sha256>

{"orderId":"o-101","amount":125000}
~~~

Giá trị chữ ký ở trên chỉ là **placeholder**. Trong hợp đồng ví dụ `HMAC-REQUEST-V1`, hai bên thống nhất:

- Method: chữ hoa theo request HTTP thực tế.
- Target: **path + raw query** theo quy tắc canonical URI đã công bố.
- `Content-Type`: chính xác `application/json` đối với endpoint này.
- Client ID, key ID, tenant đích, timestamp, nonce: các chuỗi chuẩn, không cho duplicate header.
- Body digest: SHA-256 hex lowercase của **body bytes mà endpoint nhận theo hợp đồng**, kể cả body rỗng.
- Mỗi trường là một dòng UTF-8, phân tách bởi `LF` (`0x0A`), **không thêm `LF` cuối cùng** trong ví dụ.

Chuỗi canonical mẫu:

~~~text
HMAC-REQUEST-V1
POST
/api/hmac/orders?currency=VND
application/json
partner-a
partner-a-k4
tenant-a
2026-11-28T04:00:00Z
c5c1db08-a6be-48f0-9ef7-9d8726a1ef40
<sha256-hex-cua-raw-body>
~~~

Dòng cuối phải thay bằng digest thực tế khi tạo vector kiểm thử. Công thức:

\[
\text{bodyHash} = \operatorname{HexLower}\!\left(\operatorname{SHA256}(\text{bodyBytes})\right)
\]

\[
\text{signature} =
\operatorname{Base64}\!\left(\operatorname{HMAC\mbox{-}SHA256}
(K_{\text{partner-a-k4}},\operatorname{UTF8}(\text{canonicalRequest}))\right)
\]

Đây là **một hợp đồng ký minh họa**, không phải quy tắc mặc định do Spring MVC hay Spring Security cung cấp. Khi triển khai, phải đặc tả riêng phần URI/query (thứ tự tham số, percent-encoding, ký tự Unicode, slash, dấu `?`, tham số trùng), header (trùng tên/giá trị, khoảng trắng, case) và framing/body.

### Không ký đối tượng Java thay cho bytes HTTP

Hai JSON dưới đây có thể biểu diễn cùng dữ liệu nhưng bytes khác nhau:

~~~json
{"orderId":"o-101","amount":125000}
~~~

~~~json
{
  "orderId": "o-101",
  "amount": 125000
}
~~~

Nếu hợp đồng ký **raw body bytes**, hai JSON phải cho body hash khác nhau. Không deserialize bằng Jackson rồi serialize lại để tính HMAC, trừ khi hai phía thực sự thống nhất một chuẩn canonical JSON riêng. `HttpMessageConverter` chỉ nên chuyển body thành DTO **sau khi** request được xác thực; dữ liệu để ký phải lấy từ body gốc đúng theo hợp đồng.

### Không nhập nhằng giữa integrity và authorization

Việc `X-Tenant-Id: tenant-a` nằm trong HMAC khiến việc **sửa tenant trên đường truyền** bị phát hiện. Tuy vậy, client đã sở hữu secret vẫn có thể **tự ký** một request `tenant-b`. Server phải tra registry và kiểm tra principal có quyền với tenant B hay không. Chữ ký đúng chỉ là điều kiện xác thực.

## 5. Ranh giới dữ liệu ở proxy/gateway

Ở phía client, URL có thể là `https://api.example.test/api/hmac/orders`, nhưng reverse proxy đổi route thành `/orders` trước khi chuyển cho Spring MVC. Nếu client ký `/api/hmac/orders` còn verifier lấy `request.getRequestURI()` là `/orders`, HMAC sẽ sai.

Các lựa chọn rõ ràng:

1. **Xác minh tại gateway** trước khi rewrite, rồi truyền một danh tính/context đã xác thực cho service qua kênh đáng tin (mTLS hoặc assertion/token nội bộ có chữ ký).
2. **Xác minh trong ứng dụng Spring MVC** với URI được bảo toàn đúng theo hợp đồng ký, hoặc lấy original target do **gateway tin cậy** tạo qua một kênh đã xác thực, có chính sách chống header spoofing.
3. **Đổi hợp đồng ký** để cả client và server dùng cùng một canonical target ổn định, bất kể route nội bộ; việc thay đổi hợp đồng cần version, rollout và test tương thích.

Tuyệt đối không tin trực tiếp `X-Original-URI`, `X-Forwarded-Host` hoặc `X-Authenticated-Tenant` do client bên ngoài gửi. Gateway phải **xóa giá trị không tin cậy rồi thiết lập lại** nếu có truyền metadata nội bộ.

### Kiểm thử proxy bắt buộc

| Thay đổi qua proxy | Điều phải kiểm tra |
| --- | --- |
| Rewrite path | Verifier dùng đúng target được hợp đồng ký quy định |
| Đổi thứ tự query parameter | Quy tắc canonicalization nhất quán hoặc từ chối dạng mơ hồ |
| Decode `%2F`, chuẩn hóa dot segment | Không tự ý biến target thành tài nguyên khác |
| Chuyển HTTP/1.1 ↔ HTTP/2 | Không để signed header biến nghĩa hoặc duplicate bất đồng |
| Thay `Host` / `Forwarded` | Chỉ sử dụng giá trị được chứng thực qua trust boundary |
| Nén/giải nén body | Hai phía đồng ý ký bytes nén hay bytes sau giải nén |
| Thêm `Content-Type` hoặc đổi charset | Signed headers không bị sửa ngầm sau ký |
| Thay body JSON/line ending | Body hash phải phản ánh bytes endpoint thực sự nhận |

Lỗi do khác biệt canonical request qua gateway là **SIGNATURE_MISMATCH**, chưa phải bằng chứng secret bị lộ. Không giải quyết bằng cách bỏ bớt những trường ảnh hưởng đến bảo mật khỏi chữ ký mà chưa đánh giá lại ranh giới tin cậy.

## 6. Bảo toàn request body cho @RequestBody

Servlet body là stream. Nếu HMAC filter gọi `request.getInputStream().readAllBytes()`, stream gốc có thể đến EOF; khi `HttpMessageConverter` của Spring MVC đọc body cho `@RequestBody`, controller có thể nhận body rỗng hoặc lỗi chuyển đổi.

**`ContentCachingRequestWrapper` không tự giải quyết trường hợp này**. Nó cache những bytes *đã được đọc*, nhưng việc wrap không tự động đọc, và cache không đảm bảo `getInputStream()` của wrapper được rewind cho lần đọc thứ hai.

Với **JSON nhỏ, xử lý Servlet đồng bộ**, có thể capture body một lần với giới hạn kích thước và tạo `HttpServletRequestWrapper` cung cấp stream mới từ byte buffer cho mỗi lượt đọc. Ví dụ rút gọn:

~~~java
import jakarta.servlet.ReadListener;
import jakarta.servlet.ServletInputStream;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;

import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

final class ReplayableRequest extends HttpServletRequestWrapper {

    private final byte[] bytes;

    private ReplayableRequest(HttpServletRequest request, byte[] bytes) {
        super(request);
        this.bytes = bytes.clone();
    }

    static ReplayableRequest capture(
            HttpServletRequest source,
            int maxBodyBytes
    ) throws IOException {
        if (maxBodyBytes < 0 || maxBodyBytes >= Integer.MAX_VALUE - 1) {
            throw new IllegalArgumentException("Invalid maxBodyBytes");
        }

        // Chỉ đọc tối đa giới hạn + 1 byte, không readAllBytes()
        // trên stream có kích thước không tin cậy.
        byte[] buffered =
            source.getInputStream().readNBytes(maxBodyBytes + 1);

        if (buffered.length > maxBodyBytes) {
            throw new BodyTooLargeException();
        }
        return new ReplayableRequest(source, buffered);
    }

    byte[] bodySnapshot() {
        return bytes.clone();
    }

    @Override
    public ServletInputStream getInputStream() {
        var delegate = new ByteArrayInputStream(bytes);

        return new ServletInputStream() {
            @Override
            public int read() {
                return delegate.read();
            }

            @Override
            public int read(byte[] target, int offset, int length) {
                return delegate.read(target, offset, length);
            }

            @Override
            public boolean isFinished() {
                return delegate.available() == 0;
            }

            @Override
            public boolean isReady() {
                // Chỉ phù hợp với request Servlet đồng bộ.
                return true;
            }

            @Override
            public void setReadListener(ReadListener listener) {
                throw new UnsupportedOperationException(
                    "Implement a separate non-blocking adapter");
            }
        };
    }

    @Override
    public BufferedReader getReader() throws IOException {
        String encoding = getCharacterEncoding();
        Charset charset = encoding == null
            ? StandardCharsets.UTF_8
            : Charset.forName(encoding);

        return new BufferedReader(
            new InputStreamReader(getInputStream(), charset));
    }

    @Override
    public int getContentLength() {
        return bytes.length;
    }

    @Override
    public long getContentLengthLong() {
        return bytes.length;
    }

    static final class BodyTooLargeException extends IOException {}
}
~~~

**Giới hạn của mẫu:** đây là wrapper đồng bộ dành cho endpoint JSON nhỏ; `setReadListener` không hỗ trợ non-blocking Servlet I/O, không dùng trực tiếp cho streaming/async, multipart lớn hoặc WebFlux. Với form URL-encoded, `getParameterMap()` có thể kích hoạt parser tiêu thụ body trước filter; phải kiểm soát thứ tự hoặc xây chiến lược riêng. Với multipart, boundary/metadata part và file bytes là một phần của raw body; không tự tái tạo multipart trước khi ký.

Dù đã giới hạn `maxBodyBytes`, vẫn cần giới hạn ở ingress/container, timeout, rate limit và concurrency limit. Nếu mỗi request buffer 1 MiB và có hàng nghìn request đồng thời, áp lực heap/GC vẫn lớn. Không tin hoàn toàn `Content-Length` do client khai; phải giới hạn **số bytes thực tế đọc**. Khi vượt ngưỡng, từ chối **413 Content Too Large** thay vì tính HMAC trên body bị cắt.

## 7. Tạo canonical request từ dữ liệu tin cậy

Cách tổ chức tốt là **HTTP adapter** tạo bằng chứng ký bất biến rồi chuyển cho bộ xác thực. Ví dụ:

~~~java
record SignedRequestEvidence(
    String method,
    String canonicalTarget,
    String contentType,
    String clientId,
    String keyId,
    String requestedTenantId,
    String timestamp,
    String nonce,
    String signatureBase64,
    byte[] bodyBytes
) {}
~~~

Lớp adapter phải kiểm tra **giới hạn và cú pháp** trước khi xây record. Không để caller tự gửi `canonicalRequest` dạng chuỗi rồi được server tin dùng.

Đối với hợp đồng ví dụ ở phần 4, một builder có thể trông như sau:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

final class CanonicalHmacV1 {

    static byte[] encode(SignedRequestEvidence r) {
        String digest;
        try {
            digest = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256")
                    .digest(r.bodyBytes()));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }

        String value = String.join("\n",
            "HMAC-REQUEST-V1",
            r.method(),
            r.canonicalTarget(),
            r.contentType(),
            r.clientId(),
            r.keyId(),
            r.requestedTenantId(),
            r.timestamp(),
            r.nonce(),
            digest
        );
        return value.getBytes(StandardCharsets.UTF_8);
    }
}
~~~

### Adapter bắt buộc phát hiện header mơ hồ

`request.getHeader("X-Key-Id")` thường chỉ trả giá trị đầu tiên và có thể che khuất duplicate header. Một helper kiểm tra đúng một giá trị:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import java.util.Collections;
import java.util.List;
import org.springframework.security.authentication.BadCredentialsException;

final class SignedHeaderReader {

    static String exactlyOne(
            HttpServletRequest request, String headerName) {
        List<String> values =
            Collections.list(request.getHeaders(headerName));

        if (values.size() != 1
                || values.get(0) == null
                || values.get(0).isBlank()
                || values.get(0).contains(",")
                || values.get(0).contains("\r")
                || values.get(0).contains("\n")) {
            throw new BadCredentialsException(
                "authentication_failed");
        }
        return values.get(0);
    }
}
~~~

Helper này chủ đích dùng cho **các header một giá trị** theo hợp đồng ký; nếu một hợp đồng cho phép dấu phẩy là ký tự hợp lệ, cần parser đúng ngữ nghĩa header đó thay vì áp dụng máy móc quy tắc trên. Hợp đồng cũng nên đặt giới hạn độ dài và format riêng cho client ID, key ID, tenant, timestamp, nonce, signature. Khi gateway ghép duplicate header thành một chuỗi có dấu phẩy, adapter phải từ chối các giá trị không chuẩn.

### Về canonical target

Trong ví dụ đơn giản, có thể lấy:

~~~java
String path = request.getRequestURI();
String query = request.getQueryString();
String target = query == null ? path : path + "?" + query;
~~~

Đây mới là **cách trích xuất**, không tự động bảo đảm canonicalization. Ứng dụng cần quy định yêu cầu đối với URL encode, context path, proxy rewrite, query trùng, `//`, dot segment và các biến thể `%2f`/`%2F`. Với hợp đồng chỉ cho phép target ở một tập endpoint chuẩn, hãy **từ chối** đầu vào mơ hồ. Không dùng dữ liệu `X-Original-URI` do client tự gửi để thay thế target.

## 8. Xác minh HMAC, credential và replay

Một service xác thực cần chọn đúng credential, không thử nhiều secret cho cùng request. Giả sử registry lưu:

| key ID | client | owner tenant | trạng thái | secret_ref |
| --- | --- | --- | --- | --- |
| `partner-a-k3` | partner-a | tenant-a | REVOKED | vault/a/k3 |
| `partner-a-k4` | partner-a | tenant-a | ACTIVE | vault/a/k4 |
| `partner-b-k1` | partner-b | tenant-b | ACTIVE | vault/b/k1 |

Khi request khai `X-Key-Id: partner-a-k4`, server **chỉ dùng secret K4**, kể cả khi K3 còn nằm trong registry. Nếu K4 sai chữ ký, không fallback K3 hoặc key “mới nhất”.

Một phép so sánh HMAC tối giản:

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

final class HmacSha256Verifier {

    static boolean matches(
            byte[] secret,
            byte[] canonicalBytes,
            String signatureBase64) {
        if (secret == null || secret.length == 0
                || canonicalBytes == null || signatureBase64 == null
                || signatureBase64.length() > 128) {
            return false;
        }

        final byte[] received;
        try {
            received = Base64.getDecoder().decode(signatureBase64);
        } catch (IllegalArgumentException e) {
            return false;
        }

        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            byte[] expected = mac.doFinal(canonicalBytes);

            return received.length == expected.length
                && MessageDigest.isEqual(received, expected);
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException(
                "Cryptographic provider failure", e);
        }
    }
}
~~~

Secret nên được tạo bằng CSPRNG và lưu trong secret manager; chỉ đọc khi cần, kiểm soát quyền và không đưa vào log. Nếu secret manager trả bản sao `byte[]` chỉ thuộc quyền sở hữu của caller, có thể xóa mảng sau khi sử dụng; không xóa mảng đang được cache/chia sẻ ngoài phạm vi sở hữu. HMAC key **không được suy ra từ client ID hay key version**.

### Các điều kiện để request được xác thực

1. Header và cấu trúc HTTP đúng hợp đồng, không mơ hồ.
2. Credential tồn tại, thuộc client/tenant khai báo theo mô hình, trạng thái ACTIVE và `validFrom <= serverNow < expiresAt`; client/tenant không DISABLED.
3. Trạng thái thu hồi đủ mới: nếu registry/vault không thể chứng minh credential còn hợp lệ, **fail closed**.
4. HMAC so sánh đúng trên **canonical bytes** tạo từ request thực tế.
5. Timestamp có định dạng chuẩn và trong cửa sổ chấp nhận, ví dụ ±5 phút theo đồng hồ server.
6. Nonce được ghi **nguyên tử nếu chưa tồn tại** trong kho dùng chung giữa các verifier; việc ghi nonce thực hiện **sau khi chữ ký HMAC đúng**.
7. Nếu thành công, trả principal đã xác thực và authority **do server quyết định**, không lấy role từ header.

Replay key có thể là `(credentialId, nonce)`, TTL phải đủ bao phủ toàn bộ thời gian request có thể còn nằm trong cửa sổ timestamp. Nếu một request có timestamp ở phía tương lai vẫn có thể hợp lệ nhiều phút nữa, TTL chỉ tính từ thời điểm nhận mà quá ngắn có thể cho phép replay sau khi nonce hết hạn. Sử dụng cơ chế insert-if-absent nguyên tử của Redis/DB phù hợp, không dùng `HashSet` riêng ở mỗi instance.

**Replay protection không thay thế idempotency nghiệp vụ**: hai request có nonce khác nhau nhưng cùng ý nghĩa tạo đơn hàng vẫn có thể cần `Idempotency-Key` và các ràng buộc nghiệp vụ phù hợp.

## 9. Filter xác thực HMAC trong SecurityFilterChain

Một lớp `OncePerRequestFilter` làm nhiệm vụ giao tiếp với Servlet request, lưu body và gọi `AuthenticationManager`/service xác thực. Dưới đây là cấu trúc để tập trung vào tích hợp; kiểu `HmacHttpExtractor` và `HmacRequestAuthenticator` là **hợp đồng của ứng dụng**, được triển khai bằng các quy tắc đã mô tả.

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.web.filter.OncePerRequestFilter;

interface HmacHttpExtractor {
    SignedRequestEvidence extract(ReplayableRequest request)
        throws AuthenticationException;
}

interface HmacRequestAuthenticator {
    // Có thể được triển khai thông qua AuthenticationManager và
    // AuthenticationProvider; trả Authentication đã xác thực.
    Authentication authenticate(SignedRequestEvidence evidence)
        throws AuthenticationException;
}

final class HmacMvcFilter extends OncePerRequestFilter {
    private final HmacHttpExtractor extractor;
    private final HmacRequestAuthenticator authenticator;
    private final AuthenticationEntryPoint entryPoint;

    HmacMvcFilter(
            HmacHttpExtractor extractor,
            HmacRequestAuthenticator authenticator,
            AuthenticationEntryPoint entryPoint) {
        this.extractor = extractor;
        this.authenticator = authenticator;
        this.entryPoint = entryPoint;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        ReplayableRequest wrapped;
        Authentication authentication;

        try {
            wrapped = ReplayableRequest.capture(request, 1024 * 1024);
            SignedRequestEvidence evidence =
                extractor.extract(wrapped);
            authentication = authenticator.authenticate(evidence);

            if (authentication == null
                    || !authentication.isAuthenticated()) {
                throw new BadCredentialsException(
                    "authentication_failed");
            }

        } catch (ReplayableRequest.BodyTooLargeException ex) {
            SecurityContextHolder.clearContext();
            response.sendError(413);
            return;

        } catch (AuthenticationException ex) {
            SecurityContextHolder.clearContext();
            entryPoint.commence(request, response, ex);
            return;
        }

        SecurityContext securityContext =
            SecurityContextHolder.createEmptyContext();
        securityContext.setAuthentication(authentication);
        SecurityContextHolder.setContext(securityContext);

        try {
            // Controller được đọc lại đúng bytes đã ký.
            chain.doFilter(wrapped, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

**Phạm vi của ví dụ:** HmacMvcFilter giả định ứng dụng Servlet đồng bộ, endpoint JSON có body nhỏ và `extractor` xây đầy đủ canonical target/header/body theo hợp đồng ký. `authenticator` phải tạo principal/authorities từ registry sau khi xác minh chữ ký và replay; không được trả một token authenticated chỉ vì header có key ID. Với async dispatch cần thiết kế vòng đời `SecurityContext` và wrapper phù hợp; ví dụ trên không bao quát non-blocking I/O.

Vì filter tự chạy **trước** một số filter xử lý exception của Spring Security, `AuthenticationException` ném trực tiếp tại đây không chắc được `ExceptionTranslationFilter` ở phía sau bắt. Ví dụ đã chủ động gọi `AuthenticationEntryPoint`. Các lỗi hạ tầng đọc secret/replay store phải được chuyển thành phản hồi phù hợp **mà không cho request đi tiếp**. Khi dùng `AbstractAuthenticationProcessingFilter` thay vì `OncePerRequestFilter`, có thể dùng success/failure handlers của framework.

## 10. Cấu hình Spring Security 6 cho đường API HMAC

Ví dụ một `SecurityFilterChain` dành riêng cho `/api/hmac/**`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
class HmacMvcSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain hmacApiChain(
            HttpSecurity http,
            HmacHttpExtractor extractor,
            HmacRequestAuthenticator authenticator)
            throws Exception {

        AuthenticationEntryPoint entryPoint =
            new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED);

        var hmacFilter = new HmacMvcFilter(
            extractor, authenticator, entryPoint);

        return http
            .securityMatcher("/api/hmac/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .exceptionHandling(exceptions -> exceptions
                .authenticationEntryPoint(entryPoint))
            .authorizeHttpRequests(authz -> authz
                .anyRequest().authenticated())
            .addFilterBefore(
                hmacFilter,
                UsernamePasswordAuthenticationFilter.class)
            .build();
    }
}
~~~

Những interface riêng của ứng dụng cần có bean/implementation; mã là cấu hình minh họa và còn cần một chain khác nếu ứng dụng phục vụ endpoint không dùng HMAC.

**CSRF:** chỉ vô hiệu hóa CSRF trong chain API máy–máy stateless, xác thực từng request bằng HMAC và **không dùng cookie/session trình duyệt** cho cùng đường xác thực. Không vô hiệu hóa CSRF bừa cho ứng dụng web có login bằng cookie.

**Filter registration:** tránh đăng ký cùng `HmacMvcFilter` hai lần: một lần như Servlet filter toàn cục và một lần trong `SecurityFilterChain`. Nếu filter chạy lặp, lần đầu có thể ghi nonce rồi lần hai báo replay. Nếu Spring Boot tự đăng ký bean `Filter`, cần kiểm tra/điều chỉnh đăng ký để filter chỉ chạy ở vị trí chủ đích.

`.anyRequest().authenticated()` chỉ yêu cầu principal được xác thực, **không phải cấp mọi quyền**. Endpoint cần kiểm tra quyền cụ thể sau đó.

## 11. Spring MVC controller lấy danh tính tin cậy

Một controller có thể nhận principal được Spring Security thiết lập qua `@AuthenticationPrincipal`, còn payload từ `@RequestBody`:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

record OrderInput(
    @NotBlank String orderId,
    @Positive long amount
) {}

record OrderResult(
    String orderId,
    String status
) {}

record HmacPrincipal(
    String clientId,
    String ownerTenantId,
    String credentialId
) {}

interface OrderPolicy {
    void requireCreatePermission(
        HmacPrincipal principal,
        String targetTenantId,
        String orderId
    );
}

interface OrderService {
    OrderResult create(
        String effectiveTenantId,
        OrderInput body
    );
}

@RestController
@RequestMapping("/api/hmac/orders")
final class OrderController {
    private final OrderPolicy policy;
    private final OrderService orders;

    OrderController(OrderPolicy policy, OrderService orders) {
        this.policy = policy;
        this.orders = orders;
    }

    @PostMapping
    ResponseEntity<OrderResult> create(
            @AuthenticationPrincipal HmacPrincipal principal,
            @RequestHeader("X-Tenant-Id") String requestedTenant,
            @Valid @RequestBody OrderInput body) {

        // Principal được lấy từ SecurityContext, không phải
        // X-Client-Id hoặc role do người gọi tự khai.
        policy.requireCreatePermission(
            principal, requestedTenant, body.orderId());

        OrderResult result = orders.create(requestedTenant, body);
        return ResponseEntity.ok(result);
    }
}
~~~

Ví dụ này **đòi hỏi rõ ràng** `OrderPolicy.requireCreatePermission(...)` kiểm tra rằng `requestedTenant` chính là tenant đã nằm trong canonical request được xác minh, có quyền theo principal/action/resource, và trả về tenant hiệu lực tin cậy trước khi `orders.create` được gọi. Trong sản phẩm thực tế, an toàn hơn là chuyển `effectiveTenantId` từ **authenticated/authorized tenant context**, không đọc lại trực tiếp header ở controller. Nếu không thể chứng minh việc đối chiếu đó, đoạn controller phải được sửa để không dùng `requestedTenant` làm tenant truy vấn.

Một phiên bản chặt chẽ hơn cho multi-tenant là để policy trả tenant đã được xác nhận:

~~~java
String effectiveTenant =
    tenantAuthorization.requireAuthorizedTenant(
        principal, requestedTenant, "CREATE_ORDER", body.orderId());

OrderResult result = orders.create(effectiveTenant, body);
~~~

Trong đó `tenantAuthorization` cần đối chiếu tenant đã được **ký trong request** với tenant header/path, đồng thời kiểm tra grant và trạng thái tenant. Chỉ dựa vào việc HMAC hợp lệ không đủ để authorize tenant B bằng secret của tenant A.

### Cảnh báo về dữ liệu ràng buộc ở MVC

- `@RequestBody` và validation chạy sau filter; nếu HMAC sai, không được gọi controller hoặc ghi dữ liệu.
- Nếu body có field `tenantId`, phải so với effective tenant đã được policy quyết định; không dùng field đó để chọn database.
- Nếu resource ID nằm trong path (`/orders/{id}`), xác định resource owner trước khi ghi và kiểm tra tenant tương ứng, tránh IDOR chéo tenant.
- DTO chỉ kiểm tra cú pháp và ràng buộc trường, không thay thế authentication hoặc authorization.
- Dữ liệu từ `@RequestHeader`, `@PathVariable` hay `@RequestParam` vẫn là input của client; chỉ được dùng cho quyết định bảo mật theo hợp đồng ký và policy.

## 12. Xử lý lỗi theo đúng tầng Spring Security và Spring MVC

| Tình huống | Tầng phát hiện | Hướng phản hồi |
| --- | --- | --- |
| Header HMAC thiếu/trùng/sai format | Filter/extractor | 401 hoặc lỗi cú pháp theo hợp đồng, không lộ thông tin |
| Key ID không tồn tại, chữ ký sai | Authenticator/provider | 401 chung |
| Key REVOKED/EXPIRED, client DISABLED | Authenticator/provider | 401 chung |
| Timestamp quá cũ/tương lai, nonce trùng | Authenticator/replay guard | 401 chung |
| Body vượt giới hạn trước xác thực | Filter/ingress | **413** |
| Secret manager/registry/nonce store lỗi | Hạ tầng xác thực | Fail closed; 503/401 theo policy và alert |
| HMAC đúng nhưng thiếu quyền endpoint/tenant | Authorization | Thường **403**, có thể che tài nguyên theo policy |
| `@Valid` thất bại trên body đã xác thực | MVC validation | 400 theo hợp đồng |
| JSON không đọc/parse được sau xác thực | `HttpMessageConverter` | 400 theo hợp đồng |
| Controller ném lỗi nghiệp vụ | Service/MVC handler | Mã nghiệp vụ riêng, không coi là lỗi HMAC |

`@ControllerAdvice` hữu ích cho lỗi từ controller, validation và MVC. Nhưng exception ném trong security filter trước `DispatcherServlet` **không chắc** được `@ControllerAdvice` xử lý. Tương tự, `ExceptionTranslationFilter` không tự bắt exception ném **trước khi** nó được gọi trong chain; custom filter cần cơ chế thất bại phù hợp.

Không gửi phản hồi cụ thể như “Key K4 đã tồn tại nhưng bị revoke” cho bên không tin cậy, vì có thể tạo oracle dò credential. Log/audit nội bộ có thể ghi mã nguyên nhân hữu hạn và correlation ID, không ghi secret, signature, body nhạy cảm hay canonical request đầy đủ.

## 13. Kiểm thử qua MockMvc và HTTP thật

Một bộ test chỉ gọi `HmacSha256Verifier.matches(...)` là chưa đủ. Với Spring MVC phải kiểm tra rằng **filter thực sự chạy**, controller nhận body gốc và SecurityContext có principal đúng.

### Ma trận test tích hợp

| Test ID | Kịch bản | Kết quả mong đợi |
| --- | --- | --- |
| MVC-01 | HMAC đúng, body JSON hợp lệ | Controller đọc đúng body, xử lý theo quyền |
| MVC-02 | HMAC sai | 401, controller không được gọi |
| MVC-03 | Thay đổi một byte body sau khi ký | HMAC sai, không có side effect |
| MVC-04 | JSON khác whitespace/thứ tự field | Digest khác nếu ký raw bytes |
| MVC-05 | Body rỗng / `{}` | Hash riêng từng trường hợp, theo policy endpoint |
| MVC-06 | Body lớn hơn giới hạn 1 byte | 413, không đọc vô hạn |
| MVC-07 | Header key ID hoặc tenant trùng | Từ chối input mơ hồ |
| MVC-08 | Key ID đúng nhưng secret của key khác | 401, không fallback |
| MVC-09 | Credential REVOKED, HMAC vẫn đúng | Từ chối trước nghiệp vụ |
| MVC-10 | Client/tenant DISABLED | Từ chối dù credential ACTIVE |
| MVC-11 | Timestamp ngoài cửa sổ | Từ chối |
| MVC-12 | Nonce cũ trên cùng instance | Từ chối replay |
| MVC-13 | Nonce trùng qua hai gateway/instance | Chỉ một request được chấp nhận |
| MVC-14 | HMAC đúng nhưng thiếu quyền resource | 403/response theo policy, không đổi dữ liệu |
| MVC-15 | Client A ký request tenant B không có grant | Từ chối authorization, không lộ dữ liệu B |
| MVC-16 | Proxy rewrite path, query hoặc content encoding | Kết quả đúng hợp đồng canonical |
| MVC-17 | Header `X-Original-URI` giả mạo | Không dùng làm nguồn ký tin cậy |
| MVC-18 | Hai request liên tiếp cùng thread | Không rò principal/SecurityContext |
| MVC-19 | Filter bị đăng ký hai lần | Test phát hiện và sửa; nonce không bị ghi hai lần |
| MVC-20 | Controller có `@Valid @RequestBody` | HMAC chạy trước validation, body vẫn đọc được |
| MVC-21 | Registry/replay store mất kết nối | Fail closed, có alert và không gọi nghiệp vụ |
| MVC-22 | Grant/credential vừa thu hồi nhưng cache stale | Tuân thủ yêu cầu freshness đã định |

### Một kiểm thử MockMvc mẫu

Có thể dùng `@SpringBootTest` và `@AutoConfigureMockMvc` để test qua security chain thật. Bộ fixture phải có secret test, clock cố định, signer độc lập và nonce store reset đúng cách:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class HmacMvcIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    IndependentTestSigner signer; // Fixture do dự án định nghĩa.

    @Test
    void validHmacPreservesBodyForMvcController() throws Exception {
        byte[] body = "{\"orderId\":\"o-101\",\"amount\":125000}"
            .getBytes(StandardCharsets.UTF_8);

        // Fixture ký ĐÚNG bytes được gửi bằng hợp đồng HMAC-REQUEST-V1.
        String signature = signer.sign(
            "POST", "/api/hmac/orders?currency=VND",
            "application/json",
            "partner-a", "partner-a-k4", "tenant-a",
            "2026-11-28T04:00:00Z",
            "nonce-mvc-001", body);

        mvc.perform(post("/api/hmac/orders")
                .queryParam("currency", "VND")
                .contentType(MediaType.APPLICATION_JSON)
                .header("X-Client-Id", "partner-a")
                .header("X-Key-Id", "partner-a-k4")
                .header("X-Tenant-Id", "tenant-a")
                .header("X-Timestamp", "2026-11-28T04:00:00Z")
                .header("X-Nonce", "nonce-mvc-001")
                .header("X-Signature", signature)
                .content(body))
            .andExpect(status().isOk());

        // Ngoài HTTP 200 phải assert OrderService nhận đúng DTO/bytes,
        // principal/tenant và DB chỉ có thay đổi được phép.
    }
}
~~~

`IndependentTestSigner` là **fixture cần tự hiện thực**, không phải class có sẵn của Spring. Test cũng cần cố định đồng hồ server trùng timestamp minh họa hoặc tạo timestamp trong cửa sổ cho phép; nếu chạy trực tiếp với đồng hồ thực, test sẽ thất bại vì dữ liệu thời gian đã cũ. `queryParam` và cách `MockMvc` tạo `getQueryString()` cần được so với contract bytes; signer độc lập phải dùng target đúng như request thực.

**Không chỉ mock authenticator trả thành công rồi kết luận HMAC đã được tích hợp đúng.** Ít nhất một nhóm test phải chạy `AuthenticationManager`, HMAC verifier, credential registry và replay guard thật với dữ liệu test. Nhóm khác cần gọi qua ingress/gateway thật để bắt sự khác biệt rewrite và forwarded header mà MockMvc không tái hiện đầy đủ.

## 14. Vận hành: key rotation, cache và nhiều instance

Trong thực tế, client có thể giữ nhiều key version ACTIVE trong thời gian xoay khóa. Registry phải định danh mỗi secret bằng key ID/version bất biến, theo dõi trạng thái và hiệu lực thời gian. **Mỗi request chỉ được xác minh bằng secret được chỉ định**, không fallback khi signature mismatch.

Khi secret nghi lộ, đánh dấu credential **REVOKED** và lan truyền trạng thái đến mọi verifier. Chỉ cập nhật database không bảo đảm node đang cache `ACTIVE` đã dừng chấp nhận request. Cần revision/event invalidation, giới hạn thời gian stale và chính sách fail closed khi không chứng minh freshness. Nếu cam kết “mọi request bắt đầu sau commit revoke đều bị chặn”, phải dùng cơ chế trạng thái đủ mới/đọc thẩm quyền ở điểm xác thực hoặc từ chối khi không thể xác minh; pub/sub bất đồng bộ + TTL không tự chứng minh cam kết này.

Với multi-client/multi-tenant, ngoài key state còn phải xét **client disabled, tenant disabled và grant đích**. Một principal đã có HMAC hợp lệ không được dùng key của tenant A để truy cập tenant B nếu thiếu quyền. Downstream chỉ tin tenant context đã xác thực, không đọc header tự khai làm nguồn chọn database.

### Chỉ số giám sát phù hợp

| Tín hiệu | Mục đích |
| --- | --- |
| Authentication success/failure theo route và gateway | Theo dõi sức khỏe tích hợp |
| `SIGNATURE_MISMATCH` theo contract/route | Phát hiện lỗi canonicalization hoặc secret/config |
| Replay detected và lỗi nonce store | Phát hiện replay, sự cố hạ tầng |
| Request theo key version đang ACTIVE | Đo tiến độ rotation |
| Độ trễ cập nhật REVOKED/DISABLED tới từng verifier | Đo cửa sổ chấp nhận key cũ |
| Tỷ lệ 413 và body-size distribution | Phòng ngừa memory/DoS |
| Authorization denied sau xác thực thành công | Phân biệt thiếu quyền với sai chữ ký |
| Lỗi proxy rewrite/forwarded metadata | Kiểm soát tính nhất quán qua gateway |

Log chi tiết phải có quyền truy cập và retention phù hợp; không ghi secret, body nhạy cảm, signature hoặc canonical request chứa dữ liệu cá nhân. Tránh đưa key ID/tenant ID có cardinality lớn vào nhãn metric tổng hợp.

## 15. Bài tập thực hành và tiêu chí hoàn thành

### Tình huống

Một ứng dụng Spring MVC đặt HMAC logic trong `HandlerInterceptor`. `preHandle` đọc hết request body để tính SHA-256, sau đó controller `@PostMapping` dùng `@RequestBody`. Ingress rewrite `/api/hmac/orders` thành `/orders`; interceptor dựng canonical target từ URI sau rewrite. Nonce lưu bằng `HashSet` theo JVM. Controller đọc `X-Tenant-Id` rồi dùng trực tiếp làm điều kiện truy vấn. Khi K3 bị REVOKED, một gateway vẫn giữ snapshot K3=ACTIVE trong cache 60 giây.

Hãy giải thích:

1. Vì sao `HandlerInterceptor` không phải nơi tốt nhất để triển khai duy nhất cơ chế HMAC?
2. Vì sao controller có thể nhận body rỗng dù chữ ký HMAC đã xác minh thành công?
3. Làm thế nào đảm bảo canonical target khớp khi ingress rewrite?
4. Tại sao nonce `HashSet` không chống replay giữa các instance?
5. HMAC đúng với secret tenant A có đủ quyền truy cập tenant B không?
6. Với K3 REVOKED nhưng cache stale, cần cơ chế nào để đáp ứng thời gian thu hồi đã cam kết?
7. Khi registry/vault/replay store lỗi, hệ thống có được bỏ qua HMAC để tiếp tục nghiệp vụ không?

**Gợi ý giải:** dùng Spring Security filter ở điểm xác thực trước MVC; capture raw body có giới hạn và chuyển replayable wrapper cho downstream; quy định canonical target ở trust boundary gateway; nonce phải được ghi nguyên tử trong kho dùng chung; authorization kiểm tra principal–tenant–action–resource; thu hồi cần freshness và fail closed; phụ trợ xác thực lỗi không được dẫn đến fail open.

### Checklist triển khai

Trước khi coi tích hợp Spring MVC là hoàn chỉnh, cần chứng minh:

- HMAC filter được áp dụng đúng endpoint, chạy đúng một lần trong chain đã định.
- Canonical contract xác định byte của method/URI/header/body và quy tắc proxy nhất quán; có vector ký độc lập.
- Filter không làm mất `@RequestBody`; body bytes được giới hạn và được tái sử dụng đúng.
- Credential lookup trỏ tới đúng secret/version và trạng thái đủ mới, kể cả client/tenant bị khóa.
- HMAC được so sánh an toàn về timing; timestamp/nonce chống replay hoạt động toàn cụm.
- Filter tạo `SecurityContext` và principal server-side đáng tin; dọn sau request.
- Controller và service dùng **effective tenant đã qua phân quyền**, không tin header hoặc body tự khai làm quyền.
- 401, 403, 413 và lỗi hạ tầng có response nhất quán, không tiết lộ secret.
- Unit, contract, MockMvc và gateway E2E có negative test về body, canonical URI, replay, thu hồi, IDOR và filter order.
- Metrics/audit cho phép điều tra mà không lưu shared secret hay dữ liệu nhạy cảm.

**HMAC với Spring MVC không chỉ là một phép tính mật mã trong controller.** Đây là một ranh giới xác thực phải được đặt đúng trước luồng MVC, bảo toàn raw request bytes và canonical contract qua gateway, tạo principal từ credential đã xác minh, chống replay và dành riêng quyết định quyền truy cập cho authorization. Khi những trách nhiệm này được tách bạch và kiểm thử xuyên các tầng, ứng dụng Spring MVC có thể xác thực nhiều client bằng HMAC mà vẫn kiểm soát được key rotation, tenant isolation và sự cố vận hành.

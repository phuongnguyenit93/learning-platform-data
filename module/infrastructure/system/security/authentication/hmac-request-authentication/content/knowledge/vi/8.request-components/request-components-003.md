# Path trong HTTP request và hợp đồng ký HMAC

> **Chương:** Request components  
> **Đề bài:** Path  
> **Phạm vi:** Thiết kế xác thực HTTP request bằng HMAC với shared secret và canonical request gồm phương thức, URI, các header và/hoặc body theo hợp đồng ký. Bài học tập trung vào **path**: cách nhận diện, biểu diễn, đưa path vào chữ ký, tránh sai lệch khi qua proxy/gateway, kiểm thử và ranh giới giữa xác thực với phân quyền.

## 1. Path là gì và tại sao phải quan tâm khi ký HTTP request?

**Path** là thành phần đường dẫn trong URI, dùng để định vị tài nguyên trong phạm vi một authority. Ví dụ:

~~~text
https://api.example.test/v1/payments/order-123?include=receipt#details
|------ scheme -----|----- authority -----|---- path ----|--- query ---|fragment

Path:     /v1/payments/order-123
Query:    include=receipt
Fragment: details
~~~

Trong thực tế, path thường quyết định API endpoint hoặc tài nguyên được thao tác: `/v1/payments` biểu diễn tập hợp thanh toán, còn `/v1/payments/order-123` có thể định danh một thanh toán cụ thể. **HTTP method + path** thường tham gia chọn hành động; tuy nhiên định tuyến thực tế cũng có thể phụ thuộc host, method, version và những thông tin khác.

**Fragment** (phần sau ký tự `#` trong URI ví dụ trên) được xử lý phía client và **không thuộc HTTP request target thông thường**; không dựa vào fragment để xác thực HTTP request.

Giả sử đối tác được quyền gọi:

~~~http
POST /v1/payments HTTP/1.1
Host: api.example.test
Content-Type: application/json

{"orderId":"order-123","amount":150000}
~~~

Nếu hệ thống chỉ ký body mà bỏ qua method và path, một request có thể bị chuyển sang endpoint khác mà MAC body vẫn đúng. Ví dụ, cùng body có thể được gửi đến `POST /v1/refunds` hoặc đến một tenant khác. Đưa path và method vào **canonical request** giúp chữ ký ràng buộc với đúng mục tiêu HTTP đã được lựa chọn khi ký.

Nói cách khác, với HMAC:

\[
T = \operatorname{HMAC\text{-}SHA256}(K,\operatorname{CanonicalRequest}(R)).
\]

Nếu path là một thành phần của `CanonicalRequest(R)`, thay path sau khi ký sẽ làm thay đổi dữ liệu đưa vào HMAC. Bên nhận tính lại tag và phát hiện không khớp, với điều kiện **sender và receiver diễn giải path nhất quán**.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **path**, **query**, **fragment**, **authority**, **request target** và path template của router.
2. Giải thích sự khác nhau giữa **raw/encoded path**, path đã decode, path đã normalize và path sau khi gateway rewrite.
3. Thiết kế hợp đồng ký bảo vệ path cùng method, query, header và body theo quy tắc byte rõ ràng.
4. Thu thập đúng path ở điểm xác minh trên Java Servlet/Spring hoặc API gateway, đồng thời kiểm soát các dạng path nhập nhằng.
5. Kiểm thử tampering, percent-encoding, dot-segment, slash, path prefix, routing, key rotation và replay.
6. Phân biệt **xác thực request đã ký** với **phân quyền đối với tài nguyên được định tuyến**.

## 2. Path xuất hiện ở đâu trên HTTP/1.1 và HTTP/2?

### 2.1. HTTP/1.1: request target

Trong một request HTTP/1.1 thông thường đến origin server, phần sau method và trước phiên bản HTTP là **request target** ở dạng *origin-form*:

~~~http
GET /v1/orders/order-123?expand=items HTTP/1.1
Host: api.example.test
~~~

Ở đây:

~~~text
Method:           GET
Request target:   /v1/orders/order-123?expand=items
Path:             /v1/orders/order-123
Query:            expand=items
Authority:        api.example.test  (từ Host)
~~~

Path và query là **hai thành phần khác nhau**. Dấu `?` phân cách path với query, còn dấu `&` và `=` trong query thường được ứng dụng diễn giải thành cặp tham số. Tuy nhiên, ở tầng ký HMAC, chính byte chuỗi URI theo hợp đồng mới quyết định chữ ký.

Trong một số trường hợp HTTP/1.1, proxy nhận request target **absolute-form**, chẳng hạn:

~~~http
GET https://api.example.test/v1/orders/order-123 HTTP/1.1
~~~

Ứng dụng API phải xác định rõ **điểm xác minh** nhận dạng request target nào. Hợp đồng ký chỉ dùng origin-form thì receiver nên từ chối dạng ngoài hợp đồng hoặc kiểm tra phép chuyển đổi ở proxy đáng tin; không âm thầm cắt chuỗi URL bằng cách suy đoán.

### 2.2. HTTP/2 và HTTP/3: pseudo-header

Với HTTP/2, thông tin mục tiêu thường nằm trong pseudo-header `:path`, ví dụ:

~~~text
:method = POST
:scheme = https
:authority = api.example.test
:path = /v1/payments?currency=VND
~~~

HTTP/3 cũng sử dụng cơ chế pseudo-header HTTP với những quy tắc giao thức tương ứng. Khi gateway đổi HTTP/2/3 sang HTTP/1.1 hoặc framework ánh xạ pseudo-header thành URI ứng dụng, dữ liệu có thể đã được diễn giải hoặc rewrite. **Không giả định giá trị path nhìn thấy ở backend luôn bằng nguyên chuỗi mà sender ký ở edge.**

### 2.3. Path trong URI khác path trong router

| Khái niệm | Ví dụ | Bản chất |
|---|---|---|
| **Raw path** | `/v1/files/a%2Fb` | Chuỗi đường dẫn encoded ở điểm nhận; `%2F` vẫn là ba ký tự biểu diễn |
| Decoded path | `/v1/files/a/b` | Kết quả sau một bước percent-decode; có thể thay đổi ranh giới segment |
| Normalized path | `/v1/a` thay cho `/v1/x/../a` | Đường dẫn sau quy tắc loại dot-segment hoặc normalize |
| Effective routed path | `/payments/123` sau khi bỏ prefix `/public` | Đường dẫn mà backend router thực tế sử dụng |
| Route template | `/v1/payments/{paymentId}` | Mẫu cấu hình route, **không phải** URI được client truyền |
| Filesystem path | `C:\data\reports` hoặc `/var/log/...` | Đường dẫn hệ điều hành; không đồng nhất với HTTP URI path |

Không dùng route template như `/v1/payments/{paymentId}` để thay thế path thật khi ký; giá trị `paymentId` cụ thể là thành phần có ý nghĩa an ninh. Bên cạnh đó, **path có thể chọn tài nguyên**, nhưng cơ chế phân quyền vẫn phải xác định ai sở hữu tài nguyên đó.

## 3. Những biểu diễn path dễ gây sai chữ ký

### 3.1. Percent-encoding và Unicode

Trong URI, ký tự có thể được thể hiện bằng dạng percent-encoded theo byte:

~~~text
/v1/documents/a%20b     # path có biểu diễn percent-encoded của khoảng trắng
/v1/files/a%2Fb         # encoded slash
/v1/files/a/b           # slash là dấu phân tách segment
/v1/users/%E1%BA%A1    # bytes UTF-8 percent-encoded, minh họa chữ 'ạ'
~~~

**`%2F` và ký tự `/` có thể tạo khác biệt phân đoạn** trong bộ định tuyến hoặc tầng proxy. Dù một số biến thể URI có thể được xem tương đương theo các quy tắc chuẩn hóa, trong **hợp đồng ký raw path**, các chuỗi byte khác nhau dẫn tới dữ liệu ký khác nhau.

Không áp dụng `URLDecoder.decode` cho HTTP path theo thói quen. `URLDecoder` của Java được thiết kế cho *application/x-www-form-urlencoded* và có quy tắc biến `+` thành khoảng trắng; dấu `+` trong path URI không mặc định đồng nghĩa khoảng trắng. Muốn chấp nhận encoded path, phải có đặc tả rõ về percent-encoding, Unicode/UTF-8, việc decode một lần và ranh giới segment.

### 3.2. Dot-segment và slash

~~~text
/v1/payments/./123
/v1/payments/tmp/../123
/v1/payments//123
/v1/payments/123/
/v1/payments/123
~~~

Proxy, servlet container hoặc router có thể xử lý các chuỗi trên khác nhau. Một tầng có thể xem `/a/../b` như `/b`; tầng khác có thể từ chối. **Nếu một tầng kiểm tra chữ ký trên path A còn tầng khác xử lý tài nguyên theo path B, chính sách an ninh có thể bị lệch.**

Đối với API nhạy cảm, một hợp đồng thực dụng là **từ chối dạng path nhập nhằng**: dot-segment, encoded slash hoặc backslash, nhiều slash liên tiếp, semicolon path parameter nếu ứng dụng không hỗ trợ, percent-encoding sai và các kiểu double-encoding. Một ứng dụng cần hỗ trợ chúng phải định nghĩa **chuẩn hóa duy nhất, có thể kiểm thử được** xuyên tất cả tầng.

### 3.3. Khác biệt chữ hoa/thường và ký tự kết thúc

Không mặc định path phân biệt hay không phân biệt chữ hoa/thường trên mọi server. Ví dụ:

~~~text
/v1/Payments       != /v1/payments
/v1/payments       != /v1/payments/
/v1/payments?id=1  != /v1/payments?id=1&
~~~

Nếu hợp đồng ký raw target thì ba cặp trên khác byte, dù router thực tế có thể định tuyến cùng handler. HMAC không tự quyết định tương đương URI; **hợp đồng ký phải quyết định điều đó**.

### 3.4. Rủi ro double decode

Ví dụ đường dẫn chứa `%252F`. Sau một lần percent-decode, nó có thể thành `%2F`; sau lần decode tiếp, thành `/`. Nếu gateway decode một lần còn backend decode thêm một lần, đối tượng định tuyến có thể thay đổi. Chỉ ký path gốc mà không kiểm soát cách xử lý downstream chưa đủ để bảo vệ một hệ thống có đường decode không nhất quán.

## 4. Path phải được ký theo hợp đồng nào?

Không có một quy tắc canonical hóa path duy nhất áp dụng cho **mọi** HMAC API. Một số giao thức giữ nguyên raw path; một số có phép mã hóa/sắp xếp riêng; ví dụ AWS Signature Version 4 có những quy tắc canonical URI cụ thể. Các bên phải dùng **đúng hợp đồng đã thỏa thuận**, không trộn quy tắc của nhà cung cấp A với hệ thống B.

### 4.1. Ba lựa chọn thiết kế

| Chiến lược | Cách xác định path được ký | Ưu điểm | Rủi ro/cần chú ý |
|---|---|---|---|
| **Ký raw path** | Dùng nguyên encoded path tại điểm xác minh | Đơn giản về byte, không mất chi tiết biểu diễn | Dễ mismatch nếu proxy normalize/rewrite |
| Ký path đã canonical hóa | Hai bên dùng cùng phép chuẩn hóa được mô tả chính xác | Có thể chấp nhận một số dạng URI tương đương | Cực dễ bất đồng về percent-encoding, reserved chars, dot-segment và Unicode |
| Ký target theo endpoint sau routing | Dùng biểu diễn do hệ thống định tuyến xác định | Có thể phù hợp giao thức nội bộ đã kiểm soát | Phải chứng minh sender và verifier cùng biết representation, tránh thay tài nguyên ở downstream |

**Đối với bài này, chọn hợp đồng minh họa `hmac-v1-path`: ký đúng raw origin-form request target (encoded path + query) tại ranh giới receiver, đồng thời chỉ chấp nhận các path có dạng đơn giản, không nhập nhằng.** Nhờ vậy path được bảo vệ, query cũng được bảo vệ và ví dụ có thể tự triển khai bằng JDK.

### 4.2. Quy ước chi tiết của hmac-v1-path

| Thành phần | Quy tắc của hợp đồng minh họa |
|---|---|
| Algorithm | HMAC-SHA-256 với secret riêng cho mỗi client/audience, khuyến nghị 32 byte CSPRNG |
| Version | Dòng đầu literal `hmac-v1-path` |
| Method | Dòng method, giữ đúng token như sender ký (ví dụ `POST`) |
| **Request target** | Origin-form: `/path` hoặc `/path?rawQuery`; **giữ nguyên toàn chuỗi** |
| **Path được phép** | Ví dụ chỉ nhận `/v1/payments` hoặc `/v1/payments/{id}` với ID từ tập `[A-Za-z0-9_-]` (1–64 ký tự), không có percent-encoding trong path |
| Query | Nếu có, giữ nguyên thứ tự và raw encoding; parser nghiệp vụ vẫn phải từ chối query trùng/không hợp lệ khi gây nhập nhằng |
| Content-Type | Một giá trị duy nhất hoặc vắng mặt; trim hai đầu, lowercase với `Locale.ROOT` |
| Client ID và key ID | Hai dòng lần lượt từ `X-Client-Id`, `X-Key-Id`, được ký |
| Timestamp | Một dòng Unix epoch seconds thập phân canonical từ `X-Timestamp` |
| Nonce | Một dòng Base64URL không padding của 16–32 byte ngẫu nhiên từ CSPRNG |
| Body | Một dòng lowercase hex SHA-256 của **raw body bytes** |
| Line separator | LF (`\n`), không có LF cuối cùng; không có CR/LF trong giá trị trường |
| Signature | HMAC-SHA-256 đủ 32 byte, Base64URL không padding trong `X-Signature` |

Việc chỉ cho phép một grammar path nhỏ là **quyết định của ví dụ** để tránh nhập nhằng, không phải chuẩn HTTP chung. API thực cần thêm path động, Unicode hoặc percent-encoding phải mở rộng hợp đồng kèm test và quy tắc routing tương thích.

### 4.3. Canonical request cụ thể

Giả sử sender gửi:

~~~http
POST /v1/payments/order-123?include=receipt HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: merchant-17
X-Key-Id: key-2026-11
X-Timestamp: 1795824000
X-Nonce: b75sZVQmhTBcfnX-bNbGqw
X-Signature: <hmac-base64url>

{"amount":150000}
~~~

Canonical text có **chín dòng**:

~~~text
hmac-v1-path
POST
/v1/payments/order-123?include=receipt
application/json
merchant-17
key-2026-11
1795824000
b75sZVQmhTBcfnX-bNbGqw
<sha256-hex-cua-raw-body>
~~~

Các chuỗi trong `<...>` là **chỗ giữ chỗ**, không phải giá trị digest/HMAC thật. Dòng cuối phải là digest tính từ **đúng bytes UTF-8** của `{"amount":150000}` trong ví dụ. Nếu method, path, query, body hoặc metadata được ký thay đổi, receiver sẽ tính tag khác. Secret **không** được gửi trong request.

Lưu ý: `Host` không xuất hiện trong canonical text minh họa. Do đó khóa phải được **ràng buộc đúng dịch vụ/host/audience** trong key store và routing đáng tin. Hệ thống hỗ trợ một secret ở nhiều host nên cân nhắc đưa audience hoặc authority đáng tin vào các thành phần được ký theo hợp đồng.

## 5. Receiver lấy path thế nào cho chính xác?

### 5.1. Vị trí xác minh quyết định nguồn dữ liệu

~~~mermaid
sequenceDiagram
    participant C as Sender
    participant G as Proxy / API Gateway
    participant V as HMAC verifier
    participant R as Router / Controller
    C->>C: Ký method + raw target + headers + body digest
    C->>G: POST /external/v1/payments/order-123
    G->>G: Có thể rewrite /external thành rỗng
    G->>V: Request target có thể đã thay đổi
    V->>V: Rebuild canonical request và so MAC
    V->>R: Principal đã xác thực + request
    R->>R: Route và kiểm tra quyền theo tài nguyên thật
~~~

Nếu sender ký `/external/v1/payments/order-123` mà gateway chuyển backend sang `/v1/payments/order-123`, MAC theo hợp đồng raw target sẽ sai. Hai cách thiết kế phổ biến:

1. **Xác minh tại edge trước khi rewrite**, sau đó chuyển principal đã xác thực qua kết nối nội bộ được bảo vệ.
2. **Chuyển original request target từ proxy đáng tin tới verifier** theo một cơ chế và header nội bộ được kiểm soát, đồng thời vẫn kiểm tra rằng tài nguyên downstream được xử lý đúng với đối tượng đã xác minh.

Không tin header `X-Original-URI`, `X-Forwarded-Uri` hoặc `X-Forwarded-*` do internet client tự đưa vào. Nếu proxy tạo metadata đáng tin, nó phải xóa giá trị client tự khai, thiết lập giá trị mới và bảo vệ kết nối proxy → backend (ví dụ mTLS, network policy và authentication nội bộ).

### 5.2. Java Servlet/Spring: khác biệt giữa các getter

Trong Servlet, các API thường gặp:

| Servlet API | Trả về gì về mặt khái niệm? | Có thể dùng trực tiếp ký? |
|---|---|---|
| `getRequestURI()` | URI path ứng dụng nhìn thấy, không bao gồm query string | **Ứng viên** lấy path, nhưng cần kiểm tra container/proxy có biến đổi từ raw target chưa |
| `getQueryString()` | Query string nếu có, không bao gồm dấu `?` | Dùng cùng path nếu contract ký raw target tại điểm ứng dụng |
| `getServletPath()` | Phần path ánh xạ tới servlet | **Không thay** request target gốc |
| `getPathInfo()` | Thông tin path bổ sung theo mapping, có thể đã decode theo container | **Không mặc định** dùng làm raw path để ký |
| `getRequestURL()` | URL do container dựng, thường gồm scheme/host/path, không gồm query | **Không phải** raw request target |

Ví dụ lắp origin-form target **tại ranh giới Servlet**:

~~~java
String pathAtServlet = request.getRequestURI();
String rawQueryAtServlet = request.getQueryString();
String targetAtServlet = pathAtServlet
        + (rawQueryAtServlet == null ? "" : "?" + rawQueryAtServlet);
~~~

Đây chỉ là **ứng viên cho input verifier**. Nó không chứng minh `targetAtServlet` giống byte request-target mà client gửi trước gateway. Cần kiểm chứng trên đúng server, servlet container, Spring filter chain, routing và proxy của hệ thống; đặc biệt với encoded slash, path parameter, path traversal, Unicode và HTTP/2.

Không dùng `URLDecoder.decode(request.getRequestURI(), UTF_8)` một cách máy móc. Việc decode hoặc normalize nên diễn ra đúng **một chỗ được đặc tả rõ**, hoặc bị từ chối ở ranh giới xác thực đối với các mẫu path không được phép.

### 5.3. Thời điểm kiểm tra path so với routing

**Path được ký** và **path mà router dùng để chọn controller** phải có ngữ nghĩa nhất quán. Nếu chữ ký được xác minh trên path gốc nhưng gateway hoặc framework định tuyến tới endpoint khác do normalize, việc bảo vệ path có thể mất ý nghĩa.

Ví dụ:

~~~text
Sender ký:   /v1/files/a%2Fb
Verifier đọc: /v1/files/a%2Fb
Router hiểu:  /v1/files/a/b
~~~

Chữ ký có thể đúng trên chuỗi gốc, nhưng handler nhận **hai segment** thay vì một ID chứa slash. Nếu controller hoặc authorization dùng ID đã decode mà không có quy tắc thống nhất, có thể xảy ra truy cập nhầm tài nguyên. Vì thế, ngoài việc ký path, hệ thống phải **thống nhất phép diễn giải/route và phân quyền đối với tài nguyên cuối cùng**.

## 6. Java 17: bảo vệ path trong canonical request

Đoạn mã dưới đây minh họa contract `hmac-v1-path` với Java 17+. Để tránh nhập nhằng, ví dụ chỉ nhận path của thanh toán dưới dạng:

~~~text
/v1/payments
/v1/payments/order-123
~~~

Không cho phép percent-encoding trong path, dot-segment, backslash, slash kép hoặc dấu `;`. Query vẫn được ký dưới dạng raw string; adapter thật phải kiểm tra cú pháp query và quy tắc tham số trùng theo contract API.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Locale;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacPathDemo {
    private HmacPathDemo() {}

    public record Request(
            String method,
            String rawTarget,
            String contentType,
            String clientId,
            String keyId,
            String timestamp,
            String nonce,
            byte[] body) {}

    public static String validatedPath(String rawTarget) {
        if (rawTarget == null || rawTarget.length() > 8192
                || !rawTarget.startsWith("/")
                || rawTarget.indexOf('#') >= 0) {
            throw new IllegalArgumentException("Invalid request target");
        }
        for (int i = 0; i < rawTarget.length(); i++) {
            char c = rawTarget.charAt(i);
            if (c < 0x21 || c > 0x7E || c == '\\') {
                throw new IllegalArgumentException("Invalid target character");
            }
        }
        int queryAt = rawTarget.indexOf('?');
        String rawPath = queryAt < 0
                ? rawTarget : rawTarget.substring(0, queryAt);

        // Grammar của endpoint minh họa: path không chứa %, dot, ;...
        if (!rawPath.matches("/v1/payments(?:/[A-Za-z0-9_-]{1,64})?")) {
            throw new IllegalArgumentException("Path outside contract");
        }
        return rawPath;
    }

    public static byte[] canonicalBytes(Request r)
            throws GeneralSecurityException {
        if (r == null || r.body() == null) {
            throw new IllegalArgumentException("Request/body missing");
        }
        validatedPath(r.rawTarget());
        String bodyHex = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(r.body()));
        String contentType = r.contentType() == null ? ""
                : safeLine(r.contentType()).trim().toLowerCase(Locale.ROOT);
        String canonical = String.join("\n",
                "hmac-v1-path",
                safeLine(r.method()),
                r.rawTarget(), // Ký cả raw path lẫn query.
                contentType,
                safeLine(r.clientId()),
                safeLine(r.keyId()),
                safeLine(r.timestamp()),
                safeLine(r.nonce()),
                bodyHex);
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    public static byte[] computeHmac(byte[] secret, byte[] message)
            throws GeneralSecurityException {
        if (secret == null || secret.length != 32 || message == null) {
            throw new IllegalArgumentException("Invalid key/message");
        }
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(message);
    }

    public static String sign(Request r, byte[] secret)
            throws GeneralSecurityException {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(computeHmac(secret, canonicalBytes(r)));
    }

    // Chỉ kiểm tra HMAC, chưa kiểm tra timestamp, nonce, key status.
    public static boolean verifyMac(Request r, byte[] secret, String sig)
            throws GeneralSecurityException {
        if (sig == null || sig.length() != 43) return false;
        final byte[] received;
        try {
            received = Base64.getUrlDecoder().decode(sig);
        } catch (IllegalArgumentException ex) {
            return false;
        }
        if (received.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                          .encodeToString(received).equals(sig)) {
            return false;
        }
        byte[] expected = computeHmac(secret, canonicalBytes(r));
        return MessageDigest.isEqual(expected, received);
    }

    private static String safeLine(String value) {
        if (value == null || value.indexOf('\r') >= 0
                || value.indexOf('\n') >= 0) {
            throw new IllegalArgumentException("Invalid canonical field");
        }
        return value;
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        byte[] secret = new byte[32];
        new SecureRandom().nextBytes(secret); // Khóa test tại runtime.
        byte[] body = "{\"amount\":150000}".getBytes(StandardCharsets.UTF_8);
        Request r = new Request(
                "POST",
                "/v1/payments/order-123?include=receipt",
                "application/json",
                "merchant-17",
                "key-2026-11",
                "1795824000",
                "b75sZVQmhTBcfnX-bNbGqw",
                body);

        String sig = sign(r, secret);
        if (!verifyMac(r, secret, sig)) {
            throw new AssertionError("Unmodified path must verify");
        }
        Request tampered = new Request(
                r.method(), "/v1/payments/order-999?include=receipt",
                r.contentType(), r.clientId(), r.keyId(),
                r.timestamp(), r.nonce(), r.body());
        if (verifyMac(tampered, secret, sig)) {
            throw new AssertionError("Changed path must fail MAC");
        }
        System.out.println("PASS path-bound HMAC test");
    }
}
~~~

Lưu thành `HmacPathDemo.java` rồi chạy:

~~~bash
javac HmacPathDemo.java
java HmacPathDemo
~~~

Kết quả kỳ vọng: `PASS path-bound HMAC test`. Ví dụ chứng minh **chữ ký thay đổi khi ID trong path thay đổi** và kiểm tra phần đường dẫn qua grammar đơn giản.

**Giới hạn cố ý của đoạn mã:**

- `verifyMac` chỉ là lõi mật mã, **không phải authentication filter hoàn chỉnh**: chưa kiểm tra timestamp trong cửa sổ, nonce đã dùng, trạng thái key, audience hay authorization.
- Bộ kiểm tra query ở trên chỉ giới hạn ký tự và chiều dài chung của target; **chưa định nghĩa đầy đủ cách parse query**, percent-encoding trong query hoặc tham số lặp. Endpoint production phải kiểm tra thêm theo contract.
- `Request.body` là mảng byte có thể thay đổi qua tham chiếu; adapter cần snapshot/copy buffer và giới hạn body trước khi xác minh, tránh request bị sửa giữa bước ký và xử lý nghiệp vụ.
- Việc pattern path cho phép một ID không chứng minh ID thuộc quyền sở hữu của client. **Authorization** vẫn phải tra tài nguyên thực.
- Secret sinh trong `main` chỉ phục vụ thử nghiệm; production phải được cấp/tra từ secret manager, không tạo secret mới mỗi lần verify.
- Timestamp trong ví dụ là số cố định để có dữ liệu ký lặp lại; **không dùng nó thay kiểm tra thời gian thực**.

## 7. Những lỗi bảo mật khi ký path không đúng

### 7.1. Không ký path

Nếu chỉ ký body, một attacker có thể chuyển request đến URI khác mà tag body không đổi:

~~~text
Original: POST /v1/payments      Body: {"amount":150000}
Modified: POST /v1/refunds       Body: {"amount":150000}
~~~

Nếu ứng dụng vẫn chấp nhận MAC vì method/path không nằm trong dữ liệu ký, mục tiêu của chữ ký không còn gắn với endpoint. Phòng vệ: **ký method + path/target + các trường quan trọng**, và áp dụng authorization.

### 7.2. Ký một path, xử lý một path khác

~~~text
Sender ký:      /v1/a%2Fb
Verifier kiểm:  /v1/a%2Fb
Router xử lý:   /v1/a/b
~~~

HMAC có thể xác nhận chuỗi đã ký, nhưng router có thể hiểu khác. Kiểm soát cần thiết là **một chính sách parse/normalize được thống nhất** tại gateway/verifier/router, hoặc từ chối path không thuộc grammar cho phép.

### 7.3. Ký route template thay cho path thật

~~~text
Sai:  HMAC("GET\n/v1/payments/{id}\n...")
Đúng: HMAC("GET\n/v1/payments/order-123\n...")
~~~

Nếu ký template thay vì path cụ thể, hai tài nguyên khác nhau có thể cùng chuỗi ký. Điều này loại bỏ ràng buộc quan trọng giữa tag và resource ID. Template có thể dùng trong router, nhưng phải đưa **path thực** vào signing contract.

### 7.4. Không ràng buộc dịch vụ/audience

Một MAC được ký cho `/v1/payments` trên một host có thể được thử lại trên host khác nếu cả hai dùng cùng secret và canonical text không bao gồm audience/authority. Phòng vệ: **tách secret theo dịch vụ/môi trường**, tra khóa ràng buộc audience ở server, hoặc ký thêm audience/authority ổn định được xác định đáng tin theo hợp đồng.

### 7.5. Không phân quyền theo tài nguyên cuối cùng

HMAC hợp lệ chỉ xác nhận **client nắm secret**. Nếu client ký `GET /v1/payments/order-999`, API vẫn phải xác định `order-999` có thuộc tenant của client hay không. Nếu không, hệ thống có lỗi **Broken Object Level Authorization (BOLA)** dù chữ ký HMAC chính xác.

## 8. Kiểm thử Path: từ unit test đến gateway

### 8.1. Test hợp đồng ký từng byte

| Test | Thay đổi/đầu vào | Kết quả với hmac-v1-path |
|---|---|---|
| Happy path | `POST /v1/payments/order-123`, secret đúng | MAC khớp |
| Đổi ID | `order-123` → `order-999`, giữ chữ ký | MAC không khớp |
| Đổi endpoint | `/v1/payments` → `/v1/refunds` | Path bị reject theo grammar; không xác thực |
| Đổi method | `POST` → `GET` | MAC không khớp |
| Đổi query | `?include=receipt` → `?include=details` | MAC không khớp vì ký raw target |
| Đảo query | `?a=1&b=2` → `?b=2&a=1` | MAC không khớp |
| Encoded slash | `/v1/payments/a%2Fb` | Reject path vì ví dụ không cho percent-encoding |
| Dot-segment | `/v1/payments/../refunds` | Reject path |
| Double slash | `/v1/payments//order-1` | Reject path |
| Trailing slash | `/v1/payments/order-1/` | Reject theo grammar minh họa |
| Semicolon | `/v1/payments/order-1;v=2` | Reject theo grammar minh họa |
| Backslash | `/v1/payments\order-1` | Reject |
| Path không bắt đầu bằng slash | `v1/payments` | Reject origin-form |
| Absolute URL | `https://api.example.test/v1/payments` | Reject, không thuộc origin-form |
| Fragment trong target | `/v1/payments#x` | Reject |
| Khác body/header đã ký | Giữ path, đổi body/`Content-Type` | MAC không khớp theo contract |

**Chú ý về cách test:** test negative cho dạng path bị từ chối nên kiểm tra **lý do ở tầng validation** hoặc trạng thái reject; không giả định tất cả sẽ trả “MAC không khớp”. Khi path bị reject trước khi tính MAC, đó là hành vi chủ đích.

### 8.2. Test parse/normalize xuyên nhiều tầng

Gửi request qua **cấu hình thật của gateway, reverse proxy, service mesh, servlet container và router** với các biến thể:

~~~text
/v1/payments/order-1
/v1/payments/order-1/
/v1/payments//order-1
/v1/payments/%2e%2e/order-1
/v1/payments/%252e%252e/order-1
/v1/payments/order-1;version=1
/v1/payments/order-1?b=2&a=1
~~~

Nếu tuyến edge chặn trước backend, test phải ghi nhận việc bị chặn. Nếu request đến verifier, so sánh raw target tại **đúng điểm kiểm tra MAC** với expected test vector. Nếu đến router, xác minh handler và resource ID thực sự được xử lý. Không để các tầng có hai cách hiểu URI mà đều tuyên bố “đã verify thành công”.

### 8.3. Test host, path prefix và nhiều version API

| Tình huống | Câu hỏi cần trả lời |
|---|---|
| Gateway thêm hoặc bỏ prefix `/api` | Sender ký path trước hay sau rewrite? |
| Backend có route `/v1` và `/v2` | Có ký đủ version path để tránh lẫn endpoint? |
| Host A và Host B dùng cùng path | Secret/audience có tách đúng không? |
| Path match phân biệt hoa/thường | Verifier và router có cùng cách diễn giải không? |
| Spring Security so path khác router | Có điểm lệch trong authorization matcher không? |
| HTTP/2 đến edge, HTTP/1.1 đến backend | `:path` có được chuyển sang request target nhất quán không? |

Trong hệ thống Spring, cần kiểm thử chính sách security matcher với **effective route thật**, không chỉ test URL từ Postman. Cấu hình filter order, forwarded headers và reverse proxy ảnh hưởng tới giá trị mà các lớp quan sát.

### 8.4. Test nonce và key rotation cùng path

Path đã được ký vẫn **không bảo đảm tính mới**: một bản sao request hợp lệ có thể được gửi lại. Receiver phải kiểm tra timestamp và nonce độc lập với HMAC:

~~~text
Kiểm tra thời gian: now - 300 <= signedTimestamp <= now + 300
Xác minh MAC với secret đúng client/keyId/audience
Reserve nonce: insert-if-absent nguyên tử theo namespace(clientId,keyId)
TTL nonce: đủ che phủ thời gian timestamp có thể còn hợp lệ
Sau đó mới tạo authenticated principal.
~~~

Với cửa sổ ±300 giây, TTL khoảng 600 giây tính từ lần nhận đầu là một ví dụ phù hợp khi dùng nonce store phân tán. Không dùng “GET rồi SET” vì hai request đồng thời có thể cùng lọt qua. Nếu nonce store lỗi, verifier phải **fail closed** theo chính sách; không được bỏ kiểm tra replay chỉ vì MAC đúng.

| Ca test | Kết quả |
|---|---|
| Request cùng path/MAC/nonce gửi lại | Lần hai bị reject do replay |
| Request cùng path, nonce mới, MAC tính lại | Có thể xác thực nếu timestamp/key hợp lệ |
| Chữ ký đúng với key `REVOKED` | Reject dù path đúng |
| Key `VERIFY_ONLY` đã quá hạn chuyển tiếp | Reject |
| Client dùng key ID thuộc merchant khác | Không tra nhầm secret/principal |
| Replay đồng thời qua hai node | Tối đa một lượt reserve nonce thành công |
| Path hợp lệ nhưng resource khác tenant | Xác thực có thể pass, authorization phải deny |

## 9. Authentication không thay thế authorization trên path

Ví dụ request:

~~~http
GET /v1/payments/order-999 HTTP/1.1
X-Client-Id: merchant-17
X-Key-Id: key-2026-11
X-Timestamp: 1795824000
X-Nonce: b75sZVQmhTBcfnX-bNbGqw
X-Signature: <hmac-base64url>
~~~

Giả sử MAC và timestamp/nonce đều hợp lệ:

~~~text
Authentication:
  principal = merchant-17
  signedPath = /v1/payments/order-999
  signature = valid

Authorization:
  action = payments:read
  resource = order-999
  resource.owner = merchant-42
  principal = merchant-17
  decision = DENY
~~~

Receiver xác thực được **ai đang nắm khóa**, còn authorization kiểm tra **ai có quyền đối với tài nguyên cuối cùng**. Ký đúng path giúp phát hiện sửa ID sau khi ký; nó **không** chứng minh ID đó thuộc sở hữu principal. Handler phải áp dụng chính sách quyền hạn ở tầng domain/data, thường với nguyên tắc ít quyền nhất và kiểm tra ownership/tenant.

Khi cần retry tạo resource, timestamp/nonce mới và chữ ký mới có thể hợp lệ nhưng thao tác có thể bị thực hiện lặp. Đối với API có side effect, bổ sung cơ chế **idempotency key** ở tầng nghiệp vụ, đồng thời ký idempotency key nếu nó ảnh hưởng tới quyết định xử lý.

## 10. Hướng dẫn thiết kế triển khai thực tế

Một checklist thiết kế path trong HMAC request authentication:

1. **Chốt hợp đồng ký:** raw origin-form target hay canonical path; method, query, header/body nào được ký; charset, delimiter, algorithm, signature encoding.
2. **Chọn điểm verify:** ở edge hay backend; xác định gateway/container có rewrite, normalize hoặc decode path trước đó không.
3. **Hạn chế path nhập nhằng:** định nghĩa route grammar, percent-encoding và dot-segment; từ chối dạng ngoài hợp đồng.
4. **Ký path thật:** không dùng route template; ký cả phần query ảnh hưởng nghiệp vụ và ràng buộc audience bằng secret riêng hoặc trường ký rõ ràng.
5. **Lấy dữ liệu từ nguồn đáng tin:** không tin client-defined forwarding headers; tránh raw path bị mất trước adapter.
6. **Dùng HMAC chuẩn:** `Mac.getInstance("HmacSHA256")`, `init` với shared secret được tra đúng key ID, tính lại canonical bytes, so tag bằng `MessageDigest.isEqual`.
7. **Chống replay:** timestamp có giới hạn; nonce ngẫu nhiên, duy nhất, lưu nguyên tử trong kho chia sẻ giữa các node; fail closed.
8. **Quản lý khóa:** key ID, rotation, overlap ngắn có kiểm soát, revoke; không dùng secret chung giữa tenant/môi trường.
9. **Phân quyền theo tài nguyên thực:** sau khi verify, kiểm tra route/action/owner/tenant; không dựa riêng vào MAC để cấp mọi quyền.
10. **Kiểm thử end-to-end:** bao phủ percent-encoding, slash, dot-segment, query order, header/body, proxy rewrite, HTTP/2, concurrency và các trạng thái khóa.

Theo dõi metric chữ ký sai theo route/version, sự cố raw target mismatch, duplicate header, key lookup, timestamp skew và replay rejection. Log chỉ nên chứa request ID, client/key ID đã xử lý an toàn và mã lỗi phân loại; **không log shared secret, expected HMAC hoặc body nhạy cảm**.

## 11. Câu hỏi thực hành

**Bài 1 — Phân tách URI:** Với `https://shop.example.test/api/v1/items/A%2FB?expand=price#summary`, hãy xác định scheme, authority, raw path, query và fragment. Thành phần nào không được gửi trong request target HTTP thông thường?

**Bài 2 — Ký path hay route template:** Hai request `GET /v1/payments/order-100` và `GET /v1/payments/order-200` cùng khớp route `/v1/payments/{id}`. Tại sao ký template tạo rủi ro? Hãy viết một test đổi ID rồi giữ nguyên chữ ký.

**Bài 3 — Path qua gateway:** Sender ký `/external/v1/payments`, gateway rewrite thành `/v1/payments`. Hãy thiết kế vị trí verify và cơ chế bảo vệ raw target mà không tin header do client tự khai.

**Bài 4 — Percent-encoding:** API có route cho ID tài liệu `a/b`. Hãy phân tích sự khác biệt giữa `/docs/a%2Fb` và `/docs/a/b` khi client, proxy và router dùng các quy tắc decode khác nhau. Nếu hệ thống không thực sự cần encoded slash thì nên chọn chính sách gì?

**Bài 5 — Query và path:** Theo hợp đồng ký raw target, đảo query `?a=1&b=2` thành `?b=2&a=1` có ảnh hưởng HMAC không? Vì sao cần kiểm tra tham số query trùng dù raw target đã được ký?

**Bài 6 — Authorization:** Merchant A tạo chữ ký HMAC hợp lệ cho `GET /v1/payments/order-of-merchant-B`. Bước nào phải từ chối và điều kiện kiểm tra tài nguyên là gì?

**Bài 7 — Replay và khóa:** Một request path đúng, MAC đúng nhưng timestamp nằm ngoài cửa sổ; một request khác dùng key bị revoke. Từng yêu cầu phải bị từ chối ở bước nào, dù path đã được ký?

## 12. Kết luận

**Path là thành phần quyết định tài nguyên HTTP**, nên cần được ràng buộc vào chữ ký HMAC cùng method và những phần còn lại của request có ảnh hưởng nghiệp vụ. Vấn đề khó không nằm ở phép HMAC mà ở việc hai phía có đưa vào nó **cùng byte path/target** hay không, đặc biệt qua percent-encoding, routing, proxy rewrite và sự khác biệt giữa raw path với decoded/normalized path. Một thiết kế an toàn cần **signing contract rõ ràng, nguồn raw target đáng tin, chính sách normalize nhất quán, key rotation, timestamp/nonce chống replay, kiểm thử gateway và authorization đối với tài nguyên cuối cùng**.

**Tài liệu tham khảo:**

- [RFC 3986 — Uniform Resource Identifier (URI): Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986): path, percent-encoding, dot-segment và cấu trúc URI.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): URI target, request semantics và các thành phần HTTP.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): request line, request target và intermediary behavior.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): pseudo-header `:path`, `:method` và `:authority`.
- [Java Servlet API — HttpServletRequest](https://jakarta.ee/specifications/servlet/6.0/apidocs/jakarta.servlet/jakarta/servlet/http/httpservletrequest): `getRequestURI`, `getQueryString`, `getServletPath` và `getPathInfo`; cần đối chiếu phiên bản Servlet đang dùng.
- [RFC 2104 — HMAC](https://www.rfc-editor.org/rfc/rfc2104): cơ chế keyed-hash message authentication.
- [RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421): một chuẩn ký thành phần HTTP; hợp đồng `hmac-v1-path` của bài chỉ là ví dụ minh họa, không mặc nhiên tuân thủ RFC 9421.

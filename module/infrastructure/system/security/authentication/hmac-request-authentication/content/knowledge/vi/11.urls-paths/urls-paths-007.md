# Double slash trong URL/path: ảnh hưởng đến canonical request và HMAC

> **Chương:** URL và path  
> **Chủ đề:** Double slash  
> **Phạm vi module:** Xác thực HTTP request bằng HMAC với shared secret và canonical request gồm method, URI, header hoặc body theo hợp đồng ký. Bài học phân tích dấu gạch chéo kép trong path, cách các tầng HTTP xử lý nó, phương án canonical hóa/từ chối, kiểm thử qua gateway và các biện pháp bảo vệ bổ sung như timestamp/nonce, key rotation và authorization.

## 1. Double slash là gì?

**Double slash** thường chỉ hai ký tự slash liên tiếp (`//`). Khi xuất hiện **bên trong HTTP path**, chúng tạo một vị trí **segment rỗng** giữa hai dấu phân cách:

~~~text
/v1/orders/123        # path thông thường
/v1//orders/123       # double slash giữa v1 và orders
/v1/orders//123       # double slash giữa orders và 123
//v1/orders/123       # double slash ngay đầu path
/v1/orders/123//      # double slash ở cuối path
~~~

Theo cú pháp URI, path gồm các segment được ngăn bởi `/`. Trong path `/v1//orders`, giữa hai dấu slash liên tiếp có một **segment rỗng**. Việc hai URL được ứng dụng coi là tương đương, khác route hay không hợp lệ **phụ thuộc vào hợp đồng API và cách các thành phần xử lý URI**; không thể khẳng định mọi server tự động rút `//` thành `/`.

Đối với HTTP request authentication, đây là một ranh giới bảo mật:

~~~text
Client ký:    GET /v1//orders/123
Verifier ký:  GET /v1//orders/123
Router dùng:  GET /v1/orders/123      (nếu đã merge slash)
~~~

Mặc dù phép HMAC kiểm tra đúng byte mà verifier nhìn thấy, **ngữ nghĩa tài nguyên ở router có thể khác ngữ nghĩa được verifier phê duyệt**. Ở chiều ngược lại, nếu client ký `/v1//orders/123` nhưng proxy xóa slash kép trước khi request đến verifier, chữ ký sẽ không khớp.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Nhận biết `//` **trong path**, dấu `//` của cú pháp URL và dấu slash trong query.
2. Giải thích **raw path**, **normalized path**, path sau rewrite và path mà router thực sự dùng.
3. Chọn chính sách **giữ nguyên**, **từ chối** hoặc **chuẩn hóa có kiểm soát** đối với double slash khi ký HMAC.
4. Thiết kế canonical request bao gồm method, target, header/body digest và metadata xác thực.
5. Viết bộ kiểm thử Java 17 để phát hiện slash kép và chứng minh chữ ký bị ràng buộc vào path thực.
6. Phát hiện cấu hình proxy/gateway, cache và framework gây lệch đường định tuyến hoặc sai chữ ký.
7. Giải thích vì sao anti-replay, key rotation và phân quyền vẫn cần thiết kể cả khi HMAC path đúng.

## 2. Phải phân biệt các dấu // ở những vị trí khác nhau

Không phải mọi chuỗi `//` trong một URL đều là double slash **của path**.

### 2.1. Hai slash sau scheme không thuộc path

~~~text
https://api.example.test/v1/orders/123
     ^^
     Dấu // sau scheme, mở phần authority
~~~

Trong URL trên:

~~~text
scheme    = https
authority = api.example.test
path      = /v1/orders/123
query     = absent
~~~

`https://` có hai slash là bình thường; **không** được dùng kiểm tra kiểu `rawUrl.contains("//")` rồi kết luận path không hợp lệ. Khi kiểm tra path, phải **parse đúng ranh giới giữa scheme, authority, path và query** (hoặc lấy đúng raw target ở ranh giới HTTP đã chọn).

### 2.2. Dấu // ngay đầu một URI reference

Trong ngữ cảnh **URI reference**, một chuỗi bắt đầu bằng `//` có thể mang nghĩa *network-path reference*:

~~~text
//other.example.test/collect
~~~

Khi được resolve tương đối theo base URI, ví dụ `https://api.example.test/x`, chuỗi này có thể chỉ tới authority `other.example.test`. Nó **không giống** path tương đối `/collect`.

Tuy nhiên, trong một **HTTP request target origin-form**, những ký tự bắt đầu bằng `//` cũng có thể xuất hiện như một path chứa segment rỗng, tùy parsing và HTTP stack. Nguy cơ nằm ở việc **một tầng coi đó là path, tầng khác coi đó là authority**.

Ví dụ không an toàn khi ứng dụng tạo redirect bằng cách ghép dữ liệu do client kiểm soát vào header `Location` mà không xác nhận target:

~~~text
Client nhập:  //other.example.test/collect
Ứng dụng:     Location: //other.example.test/collect
Trình duyệt:  Có thể điều hướng tới authority other.example.test
~~~

Đây là một kiểu rủi ro **open redirect** riêng khi dùng URL reference, không phải bằng chứng rằng mọi path có double slash đều trở thành redirect. Hãy kiểm soát URL redirect theo whitelist/allowlist và parser đúng bối cảnh.

### 2.3. Dấu // bên trong query

~~~text
GET /v1/orders?next=https://example.test/a HTTP/1.1
                    ^^^^^^^^
~~~

Trong chuỗi trên, `//` thuộc **giá trị query**, không phải path. Một signing contract có thể cho phép hoặc yêu cầu percent-encode thành:

~~~text
GET /v1/orders?next=https%3A%2F%2Fexample.test%2Fa HTTP/1.1
~~~

**Không** áp quy tắc “path có `//` thì reject” lên toàn bộ request target mà không tách path khỏi query. Việc chấp nhận URL chứa trong query còn cần kiểm soát SSRF/open redirect tại tầng nghiệp vụ nếu server sẽ tải hoặc điều hướng theo URL đó.

### 2.4. Dấu / đã percent-encode

~~~text
/v1/files/a%2Fb       # encoded slash trong path
/v1/files/a/b         # slash thực: hai segment
/v1/files/a%252Fb     # encoded percent; dễ thành %2F nếu decode một lần
~~~

`%2F`, `%2f`, `/` và `%252F` **khác byte trên đường truyền**. Nếu proxy percent-decode rồi server decode thêm lần nữa, một slash có thể xuất hiện sau khi HMAC đã được kiểm tra trên dạng khác. Hợp đồng ký path phải định nghĩa rõ cho phép gì, decode mấy lần và route nhận giá trị nào.

## 3. Double slash trong mô hình nhiều tầng

~~~mermaid
sequenceDiagram
    participant C as HTTP Client
    participant E as CDN / WAF / Gateway
    participant V as HMAC Verifier
    participant R as Router / Controller
    participant A as Authorization
    C->>C: Ký GET /v1//orders/123
    C->>E: GET /v1//orders/123 + HMAC
    E->>E: Có thể merge //, rewrite hoặc reject
    E->>V: Request target theo cấu hình edge
    V->>V: Validate path và canonical request
    V->>V: So sánh HMAC, timestamp, nonce
    V->>R: Principal và request đã verify
    R->>R: Route dựa trên path thực tế
    R->>A: action/resource/tenant
    A-->>R: Allow hoặc deny
~~~

Đối với mỗi tầng, cần biết **byte/biểu diễn nào** được quan sát:

| Tầng | Có thể thấy | Câu hỏi an ninh |
|---|---|---|
| Client SDK | URL do ứng dụng dựng | Dữ liệu nào đã được ký? Có encode path trước khi gửi không? |
| CDN/WAF | Request target ở edge | Có rút slash kép hoặc chặn trước origin không? |
| API Gateway | Target trước/sau rewrite | HMAC được xác minh trước hay sau rewrite? |
| Reverse proxy | Target theo rule `location`/`proxy_pass` | Đường tới upstream có khác target client gửi không? |
| Servlet container | URI sau khi qua proxy/container | `getRequestURI()` phản ánh biểu diễn nào? |
| Router framework | Path dùng để match handler | Router có tự collapse `//` hay chuyển hướng? |
| Authorization | Tài nguyên/tenant sau routing | Quyền được kiểm tra theo ID tài nguyên thực hay path đã ký khác? |

Không có một hành vi mặc định duy nhất cho mọi phiên bản Nginx, Envoy, Spring, Servlet container hay CDN. **Phải kiểm tra cấu hình và kiểm thử trên đúng tuyến triển khai**, không suy diễn rằng tất cả luôn giữ nguyên hoặc luôn chuẩn hóa slash.

### 3.1. Phân biệt raw path và effective path

~~~text
Received raw path:      /v1//orders/123
Proxy normalized path:  /v1/orders/123
Backend routing path:   /orders/123   (nếu còn strip prefix /v1)
Handler template:       /orders/{id}
Resolved resource ID:   123
~~~

Các chuỗi này phục vụ mục đích khác nhau. HMAC ký **một biểu diễn đã được hợp đồng xác định**, không phải tự động ký route template hoặc giá trị ID cuối cùng. Nếu route có prefix rewrite, phải bảo đảm phương thức xác minh và phân quyền không hiểu sai request.

### 3.2. Vì sao một request có thể vượt qua kiểm tra sai?

Giả sử policy chỉ bảo vệ `/v1/admin`, nhưng một thành phần xem `/v1//admin` là path khác và cho qua, trong khi router phía sau normalize thành `/v1/admin`. Khi đó một đường **kiểm tra path trước normalize, xử lý path sau normalize** có thể tạo ra lỗ hổng bypass policy.

Ký HMAC không tự khắc phục tình huống này nếu policy hoặc key lookup gắn với path khác route thực tế. Cần:

- Một **thứ tự xử lý thống nhất** cho validation, authentication, route và authorization.
- Từ chối các dạng path mơ hồ ở cùng một **trust boundary**, hoặc chuẩn hóa đúng một lần theo hợp đồng.
- Authorization dựa trên **principal và resource cuối cùng**, không chỉ match một chuỗi path sơ bộ.

## 4. Ba chiến lược đối với double slash trong signing contract

### 4.1. Chiến lược A — Ký raw path nguyên vẹn

~~~text
GET /v1/orders/123      -> HMAC trên "/v1/orders/123"
GET /v1//orders/123     -> HMAC trên "/v1//orders/123"
~~~

**Ưu điểm:** byte gốc được bảo vệ; nếu attacker thêm hoặc xóa slash sau ký thì tag không khớp.

**Điểm cần bảo đảm:** receiver có quyền truy cập biểu diễn **thực sự đã được sender ký**, và router không diễn giải path đó thành tài nguyên khác ngoài chính sách đã xác minh. Ký raw path phù hợp khi hạ tầng thống nhất cách chuyển request target và biết rõ rewrite/normalization xảy ra ở đâu.

### 4.2. Chiến lược B — Từ chối double slash trong path

~~~text
/v1/orders/123       -> cho phép (nếu match route grammar)
/v1//orders/123      -> reject
//v1/orders/123      -> reject
/v1/orders//123      -> reject
~~~

**Ưu điểm:** giảm số cách biểu diễn cùng tài nguyên; ít nguy cơ bất đồng proxy và router.

**Chi phí:** client cần tạo path đúng dạng; những endpoint thật sự có path chứa segment rỗng phải thiết kế riêng. Dùng **grammar path rõ ràng** còn tốt hơn chỉ tìm chuỗi `//`, vì có thể chặn đồng thời dot-segment, backslash, encoded slash và dạng khác không được hỗ trợ.

**Bài học này chọn chiến lược B** cho ví dụ HMAC bên dưới: chỉ cho phép hai route mẫu `/v1/orders` và `/v1/orders/{id}`, với `id` giới hạn trong chữ ASCII, chữ số, `_`, `-`. Đây là quy tắc minh họa của API, **không phải điều kiện bắt buộc của mọi HTTP server**.

### 4.3. Chiến lược C — Canonical hóa slash kép thành slash đơn

~~~text
Input:     /v1//orders///123
Canonical: /v1/orders/123
~~~

Chỉ nên sử dụng nếu **hợp đồng ký quy định chính xác phép biến đổi**, cả sender và receiver cùng dùng, và **mọi tầng xử lý tài nguyên đều hiểu cùng một nghĩa**. Nếu router hoặc policy phân biệt segment rỗng, việc collapse slash khiến hai request khác nghĩa có cùng canonical bytes.

**Cẩn trọng:** một vài thư viện URI có hàm `normalize()`, nhưng không được giả định cách xử lý slash kép, dot-segment, percent-encoding hay Unicode sẽ trùng với signing contract của bạn. Phải có fixture độc lập và kiểm thử end-to-end.

### 4.4. Bảng quyết định

| Điều kiện thực tế | Hướng phù hợp |
|---|---|
| API JSON/REST không cần segment rỗng | **Reject double slash** ở path, quy định route grammar |
| API tương tác với đối tác có quy tắc ký raw request target | Giữ đúng raw target và tuân theo hợp đồng đã ký, kiểm tra proxy |
| API bắt buộc chấp nhận nhiều biểu diễn URI tương đương | Canonical hóa được đặc tả chặt, test parser/routing và fixtures |
| Gateway tự động rewrite trước backend | Verify tại edge trước rewrite hoặc dùng trusted original target |
| Các tầng không thể thống nhất cách hiểu path | Fail closed; không “sửa tạm” bằng cách bỏ một thành phần khỏi chữ ký |

## 5. Phân tách path khỏi query trước khi kiểm tra double slash

Trong HTTP/1.1 origin-form, request target thường là:

~~~text
/path/to/resource?rawQuery
~~~

Việc kiểm tra `//` **phải áp dụng cho phần path**:

~~~text
Target: /v1/orders/123?next=https%3A%2F%2Fexample.test%2Fa
Path:   /v1/orders/123
Query:  next=https%3A%2F%2Fexample.test%2Fa

Double slash trong path: KHÔNG
~~~

Nếu client thực sự gửi slash thô ở query:

~~~text
/v1/orders/123?value=one//two
~~~

thì đó vẫn **không phải double slash trong path**. Hợp đồng về **query** có thể chấp nhận, canonical hóa hoặc từ chối dấu slash thô riêng. Đừng trộn các quyết định này.

### 5.1. Không lấy URI đã decode để tìm slash kép

Ví dụ:

~~~text
Raw path:       /v1/files/a%2F%2Fb
Decoded path:   /v1/files/a//b
~~~

Kiểm tra `contains("//")` **trên decoded path** phát hiện hai slash, nhưng **đã quá muộn để biết chính xác raw representation**. Nếu hợp đồng cấm encoded slash, cần kiểm tra nó **trước khi decode**; nếu hợp đồng cho encoded slash trong ID, phải bảo đảm router không phân đoạn lại ID theo slash đã giải mã.

### 5.2. Không dùng URLDecoder như parser raw path

Java `URLDecoder` chủ yếu phục vụ dữ liệu form-urlencoded, trong đó `+` được chuyển thành khoảng trắng. HTTP path và query RFC 3986 không tự động áp dụng toàn bộ form semantics. Vì thế:

~~~java
// Không làm một cách máy móc trước khi ký path:
String decoded = URLDecoder.decode(rawTarget, StandardCharsets.UTF_8);
~~~

Thay vào đó, xác định **raw target** từ thành phần HTTP đáng tin, kiểm tra grammar cho phép, rồi ký **đúng representation đã thỏa thuận**. Nếu cần decode cho business handler, thực hiện theo cùng chính sách đã thống nhất, không decode thêm sau khi verifier đã phê duyệt route.

## 6. Hợp đồng minh họa hmac-slash-v1

Để tránh nhập nhằng, bài này định nghĩa hợp đồng riêng **`hmac-slash-v1`**:

| Thành phần | Quy tắc minh họa |
|---|---|
| Algorithm | HMAC-SHA-256, key 32 byte ngẫu nhiên được cấp riêng cho client/audience |
| Version | Dòng đầu literal `hmac-slash-v1` |
| Method | HTTP method chính xác (ví dụ `GET`), không đổi sau khi verify |
| Raw request target | Origin-form `/v1/orders` hoặc `/v1/orders/{id}` với raw query tùy chọn |
| **Path grammar** | Không chấp nhận `//`, dot-segment, backslash, percent-encoded path, semicolon hoặc trailing slash; ID khớp `[A-Za-z0-9_-]{1,64}` |
| Raw query | Chỉ nhận cặp ASCII unreserved/percent-escape theo grammar riêng; ký nguyên thứ tự; endpoint phải có chính sách duplicate rõ |
| `Content-Type` | Một giá trị hoặc vắng mặt; trim hai đầu rồi lowercase theo `Locale.ROOT` |
| Client ID | `X-Client-Id`, được ký |
| Key ID | `X-Key-Id`, được ký |
| Timestamp | `X-Timestamp` theo Unix epoch seconds canonical, được ký |
| Nonce | `X-Nonce` Base64URL không padding của 16–32 byte CSPRNG, được ký |
| Body digest | SHA-256 của **raw request body bytes**, hex chữ thường |
| Ngăn dòng | LF (`\n`), không thêm LF cuối |
| Signature | HMAC đủ 32 byte, encode Base64URL không padding trong `X-Signature` |

**Đây là hợp đồng ứng dụng để học tập**, không mặc định tương thích RFC 9421, AWS SigV4 hoặc giao thức của bên thứ ba. Nếu hợp đồng đối tác cho phép slash kép, **không được tự đổi quy tắc ký**; cần làm đúng hợp đồng hoặc thống nhất phiên bản mới.

### 6.1. Một request hợp lệ

~~~http
GET /v1/orders/order-42?view=summary HTTP/1.1
Host: api.example.test
X-Client-Id: merchant-17
X-Key-Id: key-2026-11
X-Timestamp: 1795824000
X-Nonce: b75sZVQmhTBcfnX-bNbGqw
X-Signature: <base64url-hmac-tag>

~~~

Nếu request body rỗng, digest SHA-256 là:

~~~text
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

Canonical request gồm chín dòng, trong đó dòng thứ tư (`Content-Type`) rỗng:

~~~text
hmac-slash-v1
GET
/v1/orders/order-42?view=summary

merchant-17
key-2026-11
1795824000
b75sZVQmhTBcfnX-bNbGqw
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

Chuỗi `<base64url-hmac-tag>` là **chỗ giữ chỗ**, không phải chữ ký đã tính. Trong chương trình thực, secret được lookup từ kho theo `(clientId, keyId, audience)`; tuyệt đối không gửi secret trong HTTP request.

### 6.2. Vì sao không chỉ thay // bằng / rồi ký?

Nếu sender ký:

~~~text
GET /v1//orders/order-42
~~~

nhưng verifier tự sửa thành:

~~~text
GET /v1/orders/order-42
~~~

thì chữ ký sẽ không tương thích với sender đã ký raw target. Ngay cả khi hai bên đều collapse, router vẫn có thể hiểu một số biến thể khác nhau hoặc gateway có thể redirect trước verify. Trong hợp đồng bài này, **reject input** thay vì normalize, để không tạo thêm cách biểu diễn cùng một tài nguyên.

## 7. Java 17: phát hiện và từ chối double slash trước khi tính HMAC

Đoạn mã hoàn chỉnh dưới đây mô phỏng ranh giới ký HMAC, tập trung vào **kiểm tra path trên raw origin-form target**. Nó không yêu cầu Spring hay thư viện ngoài JDK 17.

### 7.1. Mã nguồn

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Locale;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class DoubleSlashHmacDemo {
    private static final String ALGORITHM = "HmacSHA256";
    private static final String VERSION = "hmac-slash-v1";

    private DoubleSlashHmacDemo() {}

    public record Request(
            String method, String rawTarget, String contentType,
            String clientId, String keyId,
            String timestamp, String nonce, byte[] body) {
        public Request {
            if (body == null) {
                throw new IllegalArgumentException("Missing body bytes");
            }
            body = body.clone(); // Snapshot, tránh caller thay mảng byte.
        }
        @Override
        public byte[] body() {
            return body.clone();
        }
    }

    private static boolean unreserved(char c) {
        return (c >= 'A' && c <= 'Z')
                || (c >= 'a' && c <= 'z')
                || (c >= '0' && c <= '9')
                || c == '-' || c == '.' || c == '_' || c == '~';
    }

    // Query ở ví dụ được ký RAW; đây chỉ là validator ký tự,
    // không thay cho parser nghiệp vụ và chính sách duplicate.
    private static void validateRawQuery(String rawQuery) {
        if (rawQuery == null) return;
        if (rawQuery.isEmpty() || rawQuery.length() > 256) {
            throw new IllegalArgumentException("Invalid query size");
        }
        for (int i = 0; i < rawQuery.length(); i++) {
            char c = rawQuery.charAt(i);
            if (unreserved(c) || c == '&' || c == '=') continue;
            if (c == '%' && i + 2 < rawQuery.length()) {
                char hi = rawQuery.charAt(i + 1);
                char lo = rawQuery.charAt(i + 2);
                if (hi < 128 && lo < 128
                        && Character.digit(hi, 16) >= 0
                        && Character.digit(lo, 16) >= 0) {
                    i += 2;
                    continue;
                }
            }
            throw new IllegalArgumentException("Query outside contract");
        }
    }

    public static String validatedRawPath(String rawTarget) {
        if (rawTarget == null || rawTarget.isEmpty()
                || rawTarget.length() > 2048
                || !rawTarget.startsWith("/")
                || rawTarget.indexOf('#') >= 0
                || rawTarget.indexOf('\\') >= 0) {
            throw new IllegalArgumentException("Invalid request target");
        }
        // ASCII printable only: không chấp nhận raw control/Unicode.
        for (int i = 0; i < rawTarget.length(); i++) {
            char c = rawTarget.charAt(i);
            if (c < 0x21 || c > 0x7E) {
                throw new IllegalArgumentException("Invalid target character");
            }
        }

        int question = rawTarget.indexOf('?');
        String path = question < 0
                ? rawTarget : rawTarget.substring(0, question);
        String query = question < 0
                ? null : rawTarget.substring(question + 1);

        // Double slash chỉ kiểm tra PATH, không tìm trên full URL.
        if (path.contains("//")) {
            throw new IllegalArgumentException("Double slash in path");
        }
        // Cho phép /v1/orders và /v1/orders/{id} ở ví dụ này.
        if (!path.matches("/v1/orders(?:/[A-Za-z0-9_-]{1,64})?")) {
            throw new IllegalArgumentException("Path outside route grammar");
        }
        validateRawQuery(query);
        return path;
    }

    private static String line(String field, int max) {
        if (field == null || field.isEmpty() || field.length() > max
                || field.chars().anyMatch(c -> c < 0x21 || c > 0x7E)) {
            throw new IllegalArgumentException("Invalid signed field");
        }
        return field;
    }

    private static String safeContentType(String contentType) {
        if (contentType == null) return "";
        if (contentType.length() > 128
                || contentType.indexOf('\r') >= 0
                || contentType.indexOf('\n') >= 0) {
            throw new IllegalArgumentException("Invalid Content-Type");
        }
        return contentType.trim().toLowerCase(Locale.ROOT);
    }

    public static byte[] canonicalBytes(Request request)
            throws GeneralSecurityException {
        if (request == null) {
            throw new IllegalArgumentException("Missing request");
        }
        if (!line(request.method(), 12)
                .matches("GET|POST|HEAD|PUT|PATCH|DELETE")) {
            throw new IllegalArgumentException("Unsupported method");
        }
        validatedRawPath(request.rawTarget());
        String clientId = line(request.clientId(), 64);
        String keyId = line(request.keyId(), 64);
        String timestamp = line(request.timestamp(), 20);
        String nonce = line(request.nonce(), 43);
        if (!clientId.matches("[A-Za-z0-9_-]+")
                || !keyId.matches("[A-Za-z0-9_-]+")
                || !timestamp.matches("[1-9][0-9]{0,18}")) {
            throw new IllegalArgumentException("Invalid metadata");
        }
        final byte[] nonceBytes;
        try {
            nonceBytes = Base64.getUrlDecoder().decode(nonce);
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException("Invalid nonce encoding", ex);
        }
        if (nonceBytes.length < 16 || nonceBytes.length > 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(nonceBytes).equals(nonce)) {
            throw new IllegalArgumentException("Invalid nonce size");
        }

        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(request.body());
        String bodyHex = HexFormat.of().formatHex(digest);
        String canonical = String.join("\n",
                VERSION,
                request.method(),
                request.rawTarget(), // Raw path + raw query theo hợp đồng.
                safeContentType(request.contentType()),
                clientId,
                keyId,
                timestamp,
                nonce,
                bodyHex);
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] hmac(byte[] key, byte[] message)
            throws GeneralSecurityException {
        if (key == null || key.length != 32 || message == null) {
            throw new IllegalArgumentException("Invalid key/message");
        }
        Mac mac = Mac.getInstance(ALGORITHM);
        mac.init(new SecretKeySpec(key, ALGORITHM));
        return mac.doFinal(message);
    }

    public static String sign(Request request, byte[] key)
            throws GeneralSecurityException {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(hmac(key, canonicalBytes(request)));
    }

    // Chỉ kiểm tra MAC; clock, nonce store, key status ở receiver.
    public static boolean verifyMac(Request request, byte[] key,
                                    String signature)
            throws GeneralSecurityException {
        if (signature == null || signature.length() != 43) {
            return false;
        }
        final byte[] received;
        try {
            received = Base64.getUrlDecoder().decode(signature);
        } catch (IllegalArgumentException ex) {
            return false;
        }
        if (received.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(received).equals(signature)) {
            return false;
        }
        byte[] expected = hmac(key, canonicalBytes(request));
        return MessageDigest.isEqual(expected, received);
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        byte[] key = new byte[32];
        new SecureRandom().nextBytes(key); // Chỉ key demo.
        byte[] nonceRandom = new byte[16];
        new SecureRandom().nextBytes(nonceRandom);
        String nonce = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(nonceRandom);
        String timestamp = Long.toString(Instant.now().getEpochSecond());
        Request original = new Request(
                "GET", "/v1/orders/order-42?view=summary",
                null, "merchant-17", "key-2026-11",
                timestamp, nonce, new byte[0]);

        String signature = sign(original, key);
        require(verifyMac(original, key, signature), "Valid path");

        Request changed = new Request(
                "GET", "/v1/orders/order-99?view=summary",
                null, original.clientId(), original.keyId(),
                timestamp, nonce, new byte[0]);
        require(!verifyMac(changed, key, signature),
                "Path tampering must fail MAC");

        Request changedMethod = new Request(
                "POST", original.rawTarget(), null,
                original.clientId(), original.keyId(),
                timestamp, nonce, new byte[0]);
        require(!verifyMac(changedMethod, key, signature),
                "Method tampering must fail MAC");

        String[] badTargets = {
                "/v1//orders/order-42",
                "//v1/orders/order-42",
                "/v1/orders//order-42",
                "/v1/orders/order-42//",
                "/v1/orders/../order-42",
                "/v1/orders/a%2Fb",
                "/v1/orders/order-42/",
                "https://api.example.test/v1/orders/order-42"
        };
        for (String target : badTargets) {
            try {
                validatedRawPath(target);
                throw new AssertionError("Should reject " + target);
            } catch (IllegalArgumentException expected) {
                // PASS: request target nằm ngoài hợp đồng.
            }
        }

        // Hai slash encoded nằm trong QUERY, không phải trong path.
        Request queryWithSlashes = new Request(
                "GET", "/v1/orders/order-42?next=%2F%2F",
                null, original.clientId(), original.keyId(),
                timestamp, nonce, new byte[0]);
        require(verifyMac(queryWithSlashes, key,
                sign(queryWithSlashes, key)), "Encoded query slashes");
        System.out.println("PASS double-slash HMAC/path tests");
    }
}
~~~

Lưu thành `DoubleSlashHmacDemo.java` rồi chạy với JDK 17+:

~~~bash
javac DoubleSlashHmacDemo.java
java DoubleSlashHmacDemo
~~~

Kết quả mong đợi:

~~~text
PASS double-slash HMAC/path tests
~~~

### 7.2. Giải thích thiết kế

- `validatedRawPath` tách path khỏi query trước khi tìm `//`. Vì thế `next=%2F%2F` **không** bị hiểu nhầm là double slash trong path.
- Regex path giới hạn route được hỗ trợ, nên chặn luôn encoded slash trong path, dot-segment, semicolon, slash kép và trailing slash không mong muốn.
- `canonicalBytes` đưa **đúng request method và raw target** vào HMAC. Thay path hoặc method sau ký khiến tag khác.
- `Mac.getInstance("HmacSHA256")` lấy implementation HMAC chuẩn; `Mac.init` nạp key. Không tự băm `secret || message` bằng SHA-256.
- `MessageDigest.isEqual` đối chiếu **raw HMAC tag bytes** sau Base64URL decode/validation. `String.equals` trong code chỉ kiểm tra định dạng encoding canonical.
- `Request` sao chép mảng body để giảm nguy cơ caller sửa raw body sau khi tạo record. Adapter HTTP vẫn phải giới hạn dung lượng trước khi nạp body.

**Giới hạn cố ý:** đây là ví dụ **crypto + path validation**, không phải server production. Nó chưa kiểm tra signed header bị trùng, giá trị query duplicate, cấu trúc query theo nghiệp vụ, timestamp hợp lệ với thời gian hiện tại, nonce đã được dùng, audience/key status và quyền truy cập. `safeContentType` cũng chỉ xử lý biểu diễn chuỗi, không thay thế HTTP header parser. Những phần này thuộc request receiver và policy bên ngoài.

### 7.3. Tại sao không dùng contains("//") trên raw URL đầy đủ?

~~~java
// KHÔNG LÀM: "https://" tự nó chứa hai slash.
boolean reject = fullUrl.contains("//");

// TỐT HƠN: lấy request target tại ranh giới đáng tin,
// tách path khỏi query, validate theo grammar path.
String path = validatedRawPath(rawTarget);
~~~

Đoạn thứ hai chỉ đúng nếu `rawTarget` đã được lấy từ nguồn HTTP được kiểm soát và gateway không thay đổi nó ngoài hợp đồng. Nếu chỉ có một URI đã normalize thì **không thể khôi phục chắc chắn raw bytes ban đầu** chỉ bằng hàm string.

## 8. Lấy raw path đúng vị trí trong Java/Spring

### 8.1. Các API của Servlet

Trong ứng dụng Servlet hoặc Spring MVC dùng Servlet API:

| API | Giá trị khái niệm | Chú ý |
|---|---|---|
| `request.getRequestURI()` | URI path mà container đang quan sát, không có query | Có thể đã qua proxy hoặc quy tắc container |
| `request.getQueryString()` | Query được container cung cấp, không có dấu `?` | Cần ghép đúng theo signing contract |
| `request.getServletPath()` | Phần URI ánh xạ tới servlet | Không tự coi là raw target client gửi |
| `request.getPathInfo()` | Path info theo servlet mapping | Có thể liên quan xử lý/decoding theo container |
| `request.getRequestURL()` | URL do container dựng từ request | Không phải origin-form raw target |

Ví dụ lắp target theo dữ liệu **Servlet đã nhận**:

~~~java
String pathAtServlet = request.getRequestURI();
String rawQueryAtServlet = request.getQueryString();
String targetAtServlet = pathAtServlet
        + (rawQueryAtServlet == null ? "" : "?" + rawQueryAtServlet);

// Kiểm tra tại đây trước khi canonicalize.
String path = DoubleSlashHmacDemo.validatedRawPath(targetAtServlet);
~~~

**Cảnh báo:** `targetAtServlet` không nhất thiết trùng với byte request target **ban đầu ở edge**, vì reverse proxy, HTTP server hoặc servlet container có thể đã rewrite, decode hoặc từ chối slash kép. Với API bắt buộc ký raw target từ internet, cách an toàn hơn là **verify tại edge trước normalization** hoặc dùng original-target metadata do proxy đáng tin cung cấp qua kênh nội bộ bảo vệ.

Không tin `X-Original-URI`, `X-Forwarded-*` do client tự đưa vào. Proxy phải strip các giá trị bên ngoài và set lại metadata từ request nó thực sự nhận.

### 8.2. Spring routing và security matcher

Nếu Spring Security matcher được cấu hình để bảo vệ `/v1/orders/**`, cần kiểm thử trực tiếp:

~~~text
/v1/orders/123
/v1//orders/123
/v1/orders//123
/v1/orders/%2e%2e/admin
/v1/orders/a%2Fb
~~~

Mục tiêu là bảo đảm filter xác thực và authorization **nhận cùng tài nguyên** mà router thực sự xử lý. Một matcher chỉ chặn một cách viết path nhưng router normalize thành cùng handler có thể tạo lỗ hổng bypass. Không dựa vào kết quả test controller trực tiếp mà bỏ qua gateway/servlet/security filter chain.

### 8.3. HTTP/2 và HTTP/3

Trong HTTP/2/3, path và query thường nằm ở pseudo-header `:path`. Một gateway chuyển tiếp HTTP/1.1 có thể tạo request line mới. Bộ test cần xác định **giá trị method, :path và target sau chuyển đổi** được đưa vào canonical request thế nào.

Các trường hợp edge tự trả redirect, 301/308, chặn 400 hoặc rewrite path trước khi verify phải được kiểm thử theo mục tiêu cụ thể của API. Không coi mọi response 404 là “đã từ chối an toàn” nếu route khác vẫn có thể được gọi theo path normalized.

## 9. Liên hệ double slash với key rotation, replay và phân quyền

### 9.1. Đúng path không đồng nghĩa đúng principal

Một verifier cần tra secret theo **(clientId, keyId, audience)**, không chỉ theo path hoặc key ID toàn cục:

~~~text
clientId = merchant-17
keyId    = key-2026-11
audience = payments-api-production
path     = /v1/orders/order-42
~~~

Sau lookup, kiểm tra trạng thái:

| Key state | Ý nghĩa | Xử lý |
|---|---|---|
| `ACTIVE` | Key hiện được phép verify | Có thể tính HMAC |
| `VERIFY_ONLY` | Key cũ trong cửa sổ chuyển tiếp | Verify theo deadline; giới hạn overlap |
| `REVOKED` | Key đã thu hồi | Từ chối dù HMAC đúng |
| Không thuộc client/audience | Có thể là nhầm key hoặc cố giả danh | Từ chối; không thử secret tenant khác |

Mỗi lần tính HMAC phải `Mac.init` bằng secret của key record tương ứng; `mac.reset()` không chuyển sang khóa mới. Secret nên đủ entropy, được cấp qua secret manager/KMS và xoay vòng có kiểm soát.

### 9.2. HMAC không chống replay

Giả sử attacker ghi lại request hợp lệ:

~~~text
GET /v1/orders/order-42?view=summary
X-Client-Id: merchant-17
X-Key-Id: key-2026-11
X-Timestamp: 1795824000
X-Nonce: b75sZVQmhTBcfnX-bNbGqw
X-Signature: <valid-tag>
~~~

Việc giữ nguyên path, query, timestamp, nonce và HMAC không làm bản sao trở nên mới. Nếu receiver chỉ tính lại HMAC, cả bản gốc và bản phát lại có thể có MAC đúng.

Chính sách minh họa:

~~~text
now - 300 <= signedTimestamp <= now + 300
MAC đúng với secret được tra theo client/key/audience
nonceScope = (clientId, keyId, nonce)
reserve nonce atomically, TTL che phủ toàn bộ cửa sổ
~~~

Ví dụ kho Redis chung giữa các verifier có thể sử dụng thao tác tương đương `SET nonceKey 1 NX EX 600`; không dùng GET rồi SET vì có race. Chỉ reserve nonce **sau** khi MAC đúng để tránh request giả chiếm nonce thật. Nếu nonce store unavailable và chống replay là bắt buộc, **fail closed**.

Đối với request có side effect, một retry với nonce mới có thể vẫn gây tác động lặp; **idempotency** là cơ chế nghiệp vụ khác chống replay. Path ký đúng không thay thế idempotency.

### 9.3. Xác thực khác phân quyền với path đã normalize

Ví dụ client `merchant-17` có secret thật và ký:

~~~text
GET /v1/orders/order-99
~~~

MAC có thể đúng vì client tự ký request. Nhưng `order-99` thuộc merchant `merchant-42`:

~~~text
authentication:
    principal = merchant-17
    signedPath = /v1/orders/order-99
    hmac = valid

authorization:
    action = orders:read
    resource = order-99
    owner = merchant-42
    decision = DENY
~~~

Đây là **Broken Object Level Authorization** nếu server cho phép truy cập chỉ vì HMAC đúng. Cần kiểm tra ownership/tenant theo resource cuối cùng **sau khi định tuyến và chuẩn hóa được kiểm soát**. Nếu matcher bảo vệ một path nhưng router xử lý path khác, lỗi authorization có thể xuất hiện dù checksum/chữ ký không có vấn đề.

## 10. Kiểm thử double slash theo nhiều tầng

### 10.1. Unit test path validation

| Input path/target | Kỳ vọng theo hmac-slash-v1 | Lý do |
|---|---|---|
| `/v1/orders` | Accept | Endpoint tập hợp |
| `/v1/orders/order-42` | Accept | ID hợp lệ |
| `/v1/orders/order-42?view=summary` | Accept nếu query đúng grammar | Query tách khỏi path |
| `/v1//orders/order-42` | Reject | Slash kép trong path |
| `//v1/orders/order-42` | Reject | Slash kép đầu path |
| `/v1/orders//order-42` | Reject | Slash kép trước ID |
| `/v1/orders/order-42//` | Reject | Slash kép cuối |
| `/v1/orders/order-42/` | Reject | Trailing slash ngoài route grammar |
| `/v1/orders/../order-42` | Reject | Dot-segment |
| `/v1/orders/%2F` | Reject | Encoded slash ở path bị cấm |
| `/v1/orders/order%252F42` | Reject | Percent encoding ở path bị cấm |
| `/v1/orders\order-42` | Reject | Backslash |
| `https://api.example.test/v1/orders` | Reject | Không phải origin-form request target |
| `/v1/orders/order-42?next=%2F%2F` | Accept nếu query đúng grammar | Slash encoded trong query, không phải path |
| `/v1/orders/order-42?x=//` | Reject theo **quy tắc query**, không do path | Query của ví dụ không cho raw slash |

**Phân biệt loại reject:** một số trường hợp bị từ chối ngay ở edge HTTP parser, một số ở path grammar, một số ở HMAC hoặc business validation. Test nên ghi nhận **đúng ranh giới** từ chối; không giả định tất cả trả cùng một exception/status.

### 10.2. Test chữ ký

| Thao tác sau khi ký | Kỳ vọng |
|---|---|
| Dùng nguyên method/target/body/signed headers/key | MAC khớp |
| Thay `/v1/orders/order-42` thành `/v1/orders/order-99` | MAC không khớp |
| Chèn slash kép vào path rồi giữ tag cũ | Reject path **trước** khi tính MAC |
| Thay `GET` thành `POST` | MAC không khớp |
| Đổi query `view=summary` thành `view=full` | MAC không khớp |
| Thêm header quan trọng đã được contract ký | MAC không khớp |
| Thay raw body bytes | MAC không khớp |
| Sử dụng secret hoặc key ID của tenant khác | Không tạo principal sai, MAC không được chấp nhận |
| Signature sai Base64URL hoặc không đủ 32 byte | Reject |

Với một hợp đồng **cho phép ký slash kép**, ca “chèn `//`” cần kỳ vọng MAC **không khớp** thay vì reject. Kỳ vọng luôn phải theo chính sách chính thức, không theo giả định của bộ test.

### 10.3. Integration test qua gateway

Chạy request qua đường đi thực:

~~~text
Client
  -> WAF/CDN (nếu có)
  -> reverse proxy/API gateway
  -> HTTP server / Servlet container
  -> HMAC verifier/filter
  -> router/controller
  -> authorization/business
~~~

Với từng test path, cần quan sát:

1. **Raw target ở edge** có còn nguyên không?
2. Proxy **redirect**, **reject** hay **forward**? Nếu forward, target đã đổi chưa?
3. **Target mà HMAC verifier thực sự ký** là gì?
4. **Handler cuối cùng** và **resource ID** là gì?
5. **Authorization** đã kiểm tra đúng principal/resource/tenant chưa?
6. **Response status** thuộc chính sách nào? Có redirect ngoài ý muốn không?

Đặc biệt, thử cả HTTP/1.1 và HTTP/2, slash kép ở đầu/giữa/cuối, encoded slash, dot-segment, query chứa encoded URL, duplicate query/signed headers và gateway rewrite prefix.

### 10.4. Test replay, concurrency và rotation

| Tình huống | Kỳ vọng |
|---|---|
| Request hợp lệ với path đúng, nonce mới | Có thể được xác thực |
| Gửi lại nguyên request trong cửa sổ | Replay bị chặn |
| Hai node nhận cùng nonce đồng thời | Tối đa một atomic reserve thành công |
| Timestamp ở ngoài cửa sổ | Reject dù HMAC đúng |
| Nonce store unavailable | Fail closed |
| Key `VERIFY_ONLY` hết hạn | Reject |
| Key `REVOKED` | Reject dù path và HMAC đúng |
| Path được ký đúng nhưng resource thuộc tenant khác | Authorization từ chối |

Không dùng `Thread.sleep` kéo dài để kiểm tra timestamp hoặc expiration; dùng `Clock` được tiêm vào và kho nonce phù hợp để test ranh giới. Unit test in-memory chỉ chứng minh logic đơn node, chưa chứng minh tính nguyên tử phân tán.

## 11. Kỹ thuật chẩn đoán và quan sát vận hành

Nếu một request HMAC thất bại khi đi qua proxy, có thể chẩn đoán theo các bước:

1. **Xác minh test vector thuật toán** HMAC-SHA-256 độc lập (ví dụ RFC 4231) trước khi nghi ngờ provider.
2. **So sánh canonical bytes bằng fixture test** tại sender và verifier; phân biệt method, raw target, signed header và body digest.
3. **Đối chiếu target theo từng ranh giới** gateway/container/filter bằng payload không nhạy cảm, không log raw secret hoặc thông tin cá nhân.
4. **Kiểm tra normalization**: slash kép, dot-segment, percent-encoding, query order và prefix rewrite.
5. **Kiểm tra key lookup** theo client ID, key ID, audience; nhận diện key rotation/revocation.
6. **Kiểm tra timestamp/nonce**: clock skew, duplicate nonce và atomic reserve.
7. **Kiểm tra route và authorization**: HMAC đúng vẫn có thể bị 403 vì resource không thuộc quyền.

Các metric hữu ích: `invalid_target`, `double_slash_rejected`, `invalid_signature`, `stale_timestamp`, `replayed_nonce`, `key_not_allowed`, `permission_denied`. Không nên trả về chi tiết key existence hoặc expected signature cho người dùng ngoài internet.

### 11.1. Mã HTTP thường gặp

| Tình huống | Phản hồi tham khảo |
|---|---|
| Path ngoài grammar, slash kép bị cấm | 400 Bad Request hoặc phản hồi validation tương đương |
| Chữ ký không hợp lệ | 401 Unauthorized theo hợp đồng xác thực |
| Principal đúng nhưng không có quyền tài nguyên | 403 Forbidden, đôi khi 404 để hạn chế lộ thông tin |
| Body quá lớn | 413 Content Too Large |
| Nonce store bắt buộc không sẵn sàng | 503 Service Unavailable hoặc trạng thái lỗi hạ tầng phù hợp |

Không cần công khai phân biệt “key không tồn tại” và “signature sai” nếu điều đó hỗ trợ dò danh tính/key ID. Tại nội bộ, log an toàn có thể giữ mã lý do và trace ID.

## 12. Sai lầm thường gặp

1. **Kiểm tra `fullUrl.contains("//")`:** chặn nhầm `https://` hoặc query trong khi bỏ qua ranh giới URI.
2. **Tự động collapse slash trước HMAC mà không có hợp đồng:** sender và receiver ký khác byte.
3. **Chỉ ký route template:** `/v1/orders/{id}` không ràng buộc chữ ký với `order-42`.
4. **Ký raw path nhưng router normalize theo cách khác:** policy và handler hiểu hai tài nguyên khác nhau.
5. **Tưởng `%2F` và `/` luôn tương đương:** decoding có thể làm thay đổi segment hoặc dẫn đến double decoding.
6. **Tin `X-Original-URI` do client khai:** có thể cho phép client giả metadata dùng để tính HMAC.
7. **Chỉ test controller:** không phát hiện gateway merge slash, CDN redirect hoặc servlet filter bypass.
8. **Không ràng buộc audience:** cùng secret và canonical target có thể bị thử lại ở dịch vụ khác.
9. **Tưởng HMAC đúng đồng nghĩa chống replay:** cần timestamp/nonce và shared atomic store.
10. **Tưởng HMAC đúng đồng nghĩa được phép truy cập:** cần authorization cho resource cuối cùng.

## 13. Bài tập thực hành

**Bài 1 — Nhận diện dấu slash:** Với ba chuỗi `https://api.example.test/v1/orders`, `/v1//orders` và `/v1/orders?next=https://x.test/a`, hãy chỉ ra chuỗi nào có **double slash trong path**. Vì sao kiểm tra toàn chuỗi bằng `contains("//")` là sai?

**Bài 2 — Path vs query:** Hãy viết code tách path/query của origin-form target. Test với `/v1/orders/order-42?next=%2F%2F` và `/v1//orders/order-42?view=full`.

**Bài 3 — Ký raw path:** Sender ký `GET /v1/orders/order-42`, attacker sửa thành `GET /v1//orders/order-42`. Hãy mô tả kết quả nếu hợp đồng **reject slash kép**, và kết quả nếu hợp đồng **cho phép mọi raw path**.

**Bài 4 — Gateway rewrite:** Client ký `/external/v1/orders/123`, gateway bỏ prefix và gộp slash. Bạn sẽ verify ở edge hay ở backend? Nếu verify ở backend, metadata nguồn nào có thể tin và phải bảo vệ như thế nào?

**Bài 5 — Encoded slash:** So sánh `/files/a%2Fb`, `/files/a/b` và `/files/a%252Fb`. Hãy nêu cách một lần decode và hai lần decode có thể thay đổi route; chọn chính sách nếu API không cần ID chứa slash.

**Bài 6 — Security matcher:** Spring Security bảo vệ `/v1/admin/**` nhưng proxy hoặc router biến `/v1//admin/x` thành `/v1/admin/x`. Hãy thiết kế integration test chứng minh policy không bị bypass.

**Bài 7 — Key rotation/replay:** Một request path chuẩn, MAC đúng nhưng key đã `REVOKED` hoặc nonce đã dùng. Ở giai đoạn nào phải từ chối? Vì sao normalize path không giải quyết hai vấn đề này?

**Bài 8 — Quyền tài nguyên:** Client A ký đúng `GET /v1/orders/order-of-client-B`. Hãy phân biệt điều gì authentication kiểm chứng và điều gì authorization phải từ chối.

## 14. Kết luận

**Double slash trong HTTP path** thường biểu diễn **segment rỗng**, nhưng cách các gateway, router và framework xử lý nó có thể khác nhau. Đây là vấn đề quan trọng đối với HMAC request authentication vì **HMAC chỉ bảo vệ chính xác chuỗi byte đã ký**, không tự bảo đảm các tầng downstream hiểu path giống nhau. Một API không cần segment rỗng có thể **từ chối slash kép ở ranh giới đáng tin**; API phải hỗ trợ những dạng phức tạp hơn cần mô tả chính xác canonicalization và kiểm thử toàn tuyến. Dù lựa chọn nào, hãy ký method và URI đúng hợp đồng, kiểm tra proxy/gateway, ràng buộc secret với client/audience, chống replay bằng timestamp/nonce, quản lý key rotation và **phân quyền theo tài nguyên cuối cùng**.

**Tài liệu tham khảo:**

- [RFC 3986 — URI Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986): path segments, percent-encoding, authority và network-path references.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): target URI, request semantics và methods.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): request target, origin-form và request-line.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): pseudo-header `:path` và `:method`.
- [RFC 2104 — HMAC](https://www.rfc-editor.org/rfc/rfc2104): cơ chế keyed-hash authentication.
- [Java SE 17 — javax.crypto.Mac](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): cách tính HMAC-SHA-256 bằng JCA.
- [RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421): tham khảo chuẩn ký các thành phần HTTP. Hợp đồng `hmac-slash-v1` chỉ minh họa và **không tự nhận tương thích RFC 9421**.

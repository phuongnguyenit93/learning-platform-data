# Header order: thứ tự header trong canonical request dùng HMAC

HTTP cho phép bên gửi, proxy và thư viện HTTP biểu diễn nhiều **header field** theo các thứ tự khác nhau. Tuy nhiên, **HMAC-SHA256** xác thực **một dãy byte cụ thể**: đổi vị trí hai dòng trong canonical request thì byte đầu vào thay đổi và chữ ký thường thay đổi theo. Vì vậy, khi thiết kế HMAC request authentication, phải phân biệt rõ **thứ tự header trên đường truyền (wire order)** và **thứ tự header được chọn để ký (canonical order)**.

Bài **Header order** thuộc chương **Header canonicalization** trong module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**. Module xây dựng xác thực HTTP request bằng shared secret và canonical request chứa method, URI, các header hoặc body theo hợp đồng ký. Việc chọn thứ tự header ảnh hưởng trực tiếp tới khả năng client và verifier tính cùng chữ ký, nhất là khi đi qua proxy/gateway, chuyển đổi HTTP/1.1 ↔ HTTP/2, xử lý header trùng, timestamp/nonce và giai đoạn key rotation.

**Kết luận định hướng:** Với các header đơn trị đã được allowlist, nên quy định **một thứ tự canonical cố định**, độc lập với thứ tự các dòng header khi nhận. Tuyệt đối không tự ý **sắp xếp các giá trị của header lặp** nếu thứ tự giá trị có ý nghĩa; trường hợp khó chuẩn hóa nên được từ chối hoặc phải có hợp đồng ký riêng. Header hợp lệ về chữ ký cũng chưa thay thế kiểm tra phân quyền.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích vì sao thứ tự các **header khác tên** thường không quyết định HTTP semantics, nhưng byte canonical dùng HMAC lại phụ thuộc thứ tự.
2. Phân biệt thứ tự field name với thứ tự **nhiều field line cùng tên**, và giải thích vì sao tùy tiện gộp/sort duplicate có thể làm sai nghĩa.
3. Thiết kế danh sách signed headers cố định, chuẩn hóa **tên** về chữ thường ASCII và dựng canonical theo **thứ tự đã công bố**.
4. Từ chối signed header trùng/mơ hồ, header bị gộp ngoài contract, giá trị có CR/LF, và dữ liệu bị proxy rewrite.
5. Thực hành Java 17 sử dụng `Mac`, `MessageDigest`, `HttpRequest` để ký và verify dù các header độc lập bị đảo vị trí.
6. Kết hợp header order với timestamp/nonce, body digest, key rotation, trust boundary và authorization.

## 2. Hai loại “thứ tự” cần tách bạch

### 2.1. Thứ tự header field line trên HTTP request

Hai request sau có thể mang cùng thông tin ứng dụng:

~~~http
POST /v1/payments?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-42
X-Timestamp: 1795831200
X-Nonce: 00112233445566778899aabbccddeeff
Content-Length: 33

{"orderId":"ord-1","amount":1000}
~~~

~~~http
POST /v1/payments?currency=VND HTTP/1.1
X-Nonce: 00112233445566778899aabbccddeeff
X-Timestamp: 1795831200
X-Client-Id: partner-42
Content-Length: 33
Host: api.example.test
Content-Type: application/json

{"orderId":"ord-1","amount":1000}
~~~

Ở ví dụ, **đầu mục khác tên** được thay đổi thứ tự. `Content-Length` chỉ để minh họa framing; không phải đầu vào của hợp đồng ký được trình bày dưới đây. Với các trường khác tên, hệ thống không nên dựa vào thứ tự vị trí khi chúng được truyền qua nhiều HTTP hop.

Điều này **không có nghĩa mọi thứ tự header đều vô nghĩa**. Trong HTTP field model, **thứ tự các giá trị thuộc nhiều field line cùng tên có thể quan trọng**; khi được phép gộp chúng thành danh sách, việc gộp phải giữ nguyên thứ tự các giá trị. Một số field, đặc biệt `Set-Cookie` trong response, còn có quy tắc đặc biệt và không nên áp một phép gộp chung. Không thể từ câu “header order không quan trọng” suy ra “có thể sort tất cả header và value tùy ý”.

### 2.2. Thứ tự trong chuỗi canonical HMAC

Nếu hai phía tạo hai chuỗi sau:

~~~text
content-type:application/json
x-client-id:partner-42
x-timestamp:1795831200
~~~

~~~text
x-timestamp:1795831200
content-type:application/json
x-client-id:partner-42
~~~

thì byte UTF-8 của chúng **khác nhau**, dù các cặp tên/giá trị giống hệt. Vì vậy:

~~~text
HMAC_SHA256(secret, canonicalA) != HMAC_SHA256(secret, canonicalB)
~~~

trong trường hợp thông thường. Không phải HMAC bị lỗi; **hai phía đã ký hai thông điệp khác nhau**.

| Khái niệm | Thực chất | Quy tắc triển khai |
| --- | --- | --- |
| Wire header order | Vị trí các field line trong HTTP message | Không dùng làm thứ tự HMAC cho các header độc lập. |
| Header name canonicalization | Ví dụ `X-Timestamp` → `x-timestamp` | Định nghĩa cách chuẩn hóa tên, kiểm tra tên ASCII hợp lệ. |
| Signed header set | Danh sách tên header bắt buộc nằm trong chữ ký | Lấy từ **hợp đồng và policy server**, không để client tự ý giảm phạm vi ký. |
| Canonical header order | Vị trí các dòng name:value trong canonical string | Cố định trong hợp đồng hoặc sort theo quy tắc chính xác đã thống nhất. |
| Header value order | Thứ tự các phần tử trong header đa trị | Giữ ngữ nghĩa gốc; không tự sort, trộn hoặc gộp không đúng field. |
| Pseudo-header order | Metadata HTTP/2, HTTP/3 như `:method`, `:path` | Tuân theo yêu cầu protocol; không coi là header tùy ý của ứng dụng. |

## 3. Vì sao cần canonical order?

Tưởng tượng client gửi request có:

~~~text
X-Key-Id: key-2026-11
Content-Type: application/json
X-Client-Id: partner-42
~~~

Client duyệt map header theo thứ tự thêm vào và ký. Verifier lại dùng một map khác duyệt theo thứ tự:

~~~text
Content-Type: application/json
X-Client-Id: partner-42
X-Key-Id: key-2026-11
~~~

Khi hai bên nối các dòng mà **không quy định thứ tự**, chữ ký có thể khác dù không có tấn công. Tệ hơn, một proxy được phép sắp xếp lại các field line khiến việc xác minh thất bại ngẫu nhiên. Tạo canonical order khắc phục tính không xác định này.

Có hai cách hợp lệ khi áp dụng nhất quán:

1. **Fixed order**: hợp đồng phiên bản V1 chỉ rõ thứ tự từng signed header, ví dụ `content-type` rồi `x-client-id` rồi `x-content-sha256`, v.v.
2. **Sort theo quy tắc xác định**: chuẩn hóa header name thành ASCII lowercase, sắp xếp tên theo thứ tự từ điển dựa trên **byte ASCII**, sau đó dựng dòng canonical theo tên đã sort.

Với một tập header cố định, hai cách có thể tạo ra cùng kết quả, nhưng **không được giả định chúng luôn tương đương**: thứ tự một danh sách định trước có thể khác thứ tự lexicographic. Cần công bố một quy tắc duy nhất và có test vectors để ngăn hai implementation tự diễn giải.

### 3.1. Vì sao tránh lặp tùy ý các trường?

Một số giao thức dùng signed-header-list như:

~~~text
signed-headers:content-type;x-client-id;x-content-sha256;x-key-id;x-nonce;x-timestamp
~~~

Danh sách này phải do **hợp đồng** xác định hoặc được server kiểm tra theo **allowlist bắt buộc**, gồm cả thứ tự. Nếu client được gửi:

~~~text
signed-headers:x-timestamp
~~~

và verifier vì “tương thích” mà chỉ xác minh timestamp, thì client/proxy có thể đổi method, URI hoặc body không được ký. Vấn đề **scope ký** nguy hiểm hơn việc đảo thứ tự header.

**Quy ước bài này:** signed headers là một tập **cố định**, có tên ASCII lowercase và thứ tự lexical ascending. Không có negotiation tự do từ client; server tự dựng và bắt buộc đúng tập đó.

## 4. Hợp đồng ký HMAC-HEADER-ORDER-V1

Với endpoint tạo thanh toán, ví dụ định nghĩa:

| Thành phần | Quy tắc |
| --- | --- |
| Version | `HMAC-HEADER-ORDER-V1`, literal duy nhất |
| Method | `POST` chính xác, phân biệt hoa/thường |
| Request target | Raw path + raw query theo đúng request được xử lý |
| Audience | `payments-api` từ policy verifier |
| Signed header set | Chính xác **6 header** ở bảng dưới, không thiếu/không trùng |
| Signed name | Chữ thường ASCII từ tên field |
| Header value | **Một** giá trị đã kiểm tra; không CR/LF/HTAB hoặc SP ở đầu/cuối trong contract minh họa |
| Dòng header canonical | `name:value`, không có SP sau dấu `:` |
| Thứ tự | Sort **ASCII lexicographic ascending** trên tên chữ thường |
| Delimiter | LF (byte `0A`), **không** có LF cuối |
| Body | SHA-256 của đúng body bytes, hex chữ thường |
| Signature | HMAC-SHA256, tag đầy đủ 32 byte, Base64 chuẩn có padding |

### 4.1. Danh sách header được ký và thứ tự chuẩn

| Vị trí | Tên canonical | Giá trị ví dụ | Vì sao ký? |
| ---: | --- | --- | --- |
| 1 | `content-type` | `application/json` | Bảo vệ cách diễn giải body. |
| 2 | `x-client-id` | `partner-42` | Ràng buộc danh tính client/key lookup. |
| 3 | `x-content-sha256` | `<64-hex-lowercase>` | Ràng buộc body bytes. |
| 4 | `x-key-id` | `key-2026-11` | Chọn đúng phiên bản shared secret. |
| 5 | `x-nonce` | `<32-hex-lowercase>` | Chống replay khi server claim nonce. |
| 6 | `x-timestamp` | `<unix-epoch-seconds>` | Kiểm tra cửa sổ thời gian. |

`content-type` đứng trước `x-*`; trong nhóm `x-*`, `x-client-id` trước `x-content-sha256` vì ký tự `l` của `client` đứng trước `o` của `content`. Sort theo **tên canonical**, không sort theo giá trị và không sort theo vị trí header trên wire.

### 4.2. Dữ liệu canonical hoàn chỉnh

~~~text
HMAC-HEADER-ORDER-V1
POST
/v1/payments?currency=VND
audience:payments-api
signed-headers:content-type;x-client-id;x-content-sha256;x-key-id;x-nonce;x-timestamp
content-type:application/json
x-client-id:partner-42
x-content-sha256:<64-hex-lowercase>
x-key-id:key-2026-11
x-nonce:<32-hex-lowercase>
x-timestamp:<unix-epoch-seconds>
~~~

Các chuỗi `<...>` là placeholder, không được ký nguyên văn. Client điền giá trị thực, nối đúng thứ tự và tính:

~~~text
bodyHash       = lowerHex(SHA256(actualBodyBytes))
canonicalBytes = UTF8(joinWithLF(canonicalLines))
tagBytes       = HMAC_SHA256(sharedSecretBytes, canonicalBytes)
signatureB64   = Base64_standard_padded(tagBytes)
~~~

Hợp đồng này **không** đưa `X-Signature` vào danh sách signed headers (tránh vòng tự ký). Những header do HTTP stack thêm tự động như `Content-Length`, `User-Agent` hoặc `Connection` không được đưa vào chữ ký nếu hợp đồng không chỉ định. Nhưng **không ký** một trường có ảnh hưởng bảo mật có thể tạo lỗ hổng: mọi header quyết định route, quyền, nội dung giải mã, tenant hoặc method override phải được ký hoặc bị hệ thống từ chối/kiểm soát độc lập.

### 4.3. Thứ tự dòng signature và thứ tự trong HTTP không bắt buộc trùng

Client có thể đặt header `X-Timestamp` ở đầu HTTP message và `Content-Type` ở gần cuối. Verifier vẫn dùng thứ tự **6 dòng cố định như bảng**. Đây là ưu điểm của canonical order: không bị phụ thuộc thứ tự hiển thị của field line qua các hop.

HMAC chỉ bảo vệ những trường đã ký với **giá trị mà verifier thực sự dùng**. Nếu gateway thêm `Content-Encoding: gzip`, sửa `Host` hay đổi raw URI trước verify, tính ổn định của header order không tự giải quyết khác biệt representation. Cần thiết kế trust boundary và ràng buộc cả method, URI/body/audience.

## 5. Header trùng tên: không được tự gộp hoặc sort value

### 5.1. Các header khác tên và header cùng tên không giống nhau

Ví dụ hai field line có cùng tên:

~~~http
X-Client-Id: partner-42
x-client-id: partner-99
~~~

Tên field HTTP **không phân biệt hoa/thường**, nên đây là **hai lần xuất hiện của cùng header name**. Một số thư viện giữ danh sách hai giá trị; thư viện khác có thể gộp hoặc lấy giá trị đầu/cuối. Nếu signer/verifier chọn khác nhau, có thể xảy ra **header ambiguity** và sai lệch identity/authorization.

**Chính sách bài này:** với mỗi signed header trong 6 tên bắt buộc, chỉ chấp nhận **chính xác một field line và một giá trị**. Không chấp nhận repeated field, kể cả cùng giá trị:

~~~http
X-Timestamp: 1795831200
x-timestamp: 1795831200
~~~

Trên một số HTTP stack, hai field line có thể được gộp trước khi ứng dụng nhận. Khi đó code ứng dụng chỉ nhìn thấy một string không có nghĩa đầu vào gốc đã thực sự đơn trị. Cần đặt strict validation **tại parser/ingress có khả năng quan sát** số field line, hoặc sử dụng parser được cấu hình reject duplicate security-sensitive fields ngay từ đầu.

### 5.2. Cấm “sort mọi value” như một thuật toán chuẩn hóa chung

Xét một field đa trị mà thứ tự có ý nghĩa:

~~~http
Accept: application/json
Accept: text/plain
~~~

Trong những field có cấu trúc list, nhiều field line cùng tên đôi khi có thể gộp thành danh sách, nhưng **không tự hoán đổi thứ tự các giá trị**; thứ tự có thể ảnh hưởng ưu tiên hoặc ngữ nghĩa do field định nghĩa. Một phương án ký list-valued header phải nói rõ **cú pháp list, cách gộp, xử lý quoted strings, whitespace và thứ tự**. Chỉ sort field **names** không tạo quyền sort field **values**.

Các field như `Set-Cookie` (response) hoặc `Cookie` (request) càng cần tuân theo quy tắc riêng, không thể dùng chung hàm `String.join(",")` cho mọi header. Nếu không thực sự cần ký chúng, tốt hơn là thiết kế signed set đơn trị rõ ràng, tránh nhập nhằng.

### 5.3. CR/LF, whitespace và parser differential

Một số khác biệt nhỏ có thể làm canonical sai:

| Tình huống | Nguy cơ | Chính sách minh họa |
| --- | --- | --- |
| `Content-Type` / `content-type` | Cùng field name nhưng khác case ở wire | Lowercase **tên** thành `content-type`. |
| `Content-Type: application/json` / `Content-Type:application/json` | Whitespace cú pháp có thể được parser xử lý khác nhau | Chấp nhận giá trị đã parse không có SP ngoài, dựng `content-type:application/json`. |
| Value `application/json ` với SP cuối | Client/server có thể trim khác nhau | Reject nếu SP thực sự là một phần của value được quan sát theo contract. |
| Hai `x-nonce` hoặc `x-timestamp` | Một hop lấy giá trị đầu, hop khác lấy cuối | Reject duplicate tại trust boundary. |
| CR/LF trong value | Header injection, nhập nhằng dòng | Reject, không ghép vào canonical. |
| HTAB hoặc obs-fold | Khác biệt giữa parser, dễ tạo request smuggling | Reject cho signed fields của hợp đồng. |
| Header value `a,b` so với hai field `a`, `b` | Có thể mang ngữ nghĩa khác đối với từng field | Không chấp nhận dạng đa trị cho signed headers trong bài. |
| Header không ký điều khiển nghiệp vụ | Proxy có thể thay mà HMAC vẫn đúng | Ký, cấm hoặc kiểm soát nó độc lập. |

HTTP header values có nhiều quy tắc cú pháp riêng. Hợp đồng **một giá trị ASCII với không SP/HTAB thừa** ở đây chỉ áp dụng cho **6 header đã chọn**, không được tự suy ra rằng mọi HTTP header value đều phải được xử lý như vậy.

## 6. HTTP/1.1, HTTP/2/3 và proxy: thứ tự có thể thay đổi ở đâu?

~~~mermaid
flowchart LR
    A["Client: headers theo thứ tự A"] --> B["Proxy HTTP/2 hoặc gateway"]
    B --> C["Backend: headers theo thứ tự B"]
    C --> D["Parse và kiểm tra signed headers"]
    D --> E["Sắp xếp canonical names cố định"]
    E --> F["HMAC verify và replay checks"]
~~~

Đối với HTTP/2/HTTP/3, `:method`, `:path`, `:authority` là **pseudo-headers** có vị trí và cú pháp riêng theo protocol, không được tự hiểu như các header ứng dụng thông thường. Khi dịch sang HTTP/1.1, gateway có thể tạo request line và `Host` từ các pseudo-header. Việc tên header HTTP/2 được truyền dưới dạng chữ thường **không** có nghĩa giá trị method `POST` cũng cần đổi chữ thường.

Tuy nhiên, với signed headers đơn trị, verifier vẫn phải dựng **cùng canonical order** độc lập với thứ tự do HTTP/1.1 request line, HTTP/2 header block hay framework map cung cấp.

| Tình huống | Điều gì có thể xảy ra? | Biện pháp |
| --- | --- | --- |
| Reverse proxy đổi thứ tự field line khác tên | HMAC sai nếu lấy thứ tự wire | Sort/fixed order trên signed names. |
| Proxy hạ case tên header | `X-Nonce` thành `x-nonce` | Quy định lowercase **header name**, không thay value. |
| Proxy gộp duplicate field line | Mất thông tin số lần xuất hiện và thứ tự value | Từ chối security-sensitive duplicate ở ingress đáng tin trước gộp. |
| HTTP/2 → HTTP/1.1 chuyển `:authority`/`:path` | Host/route/raw URI có thể bị rewrite | Xác định rõ method/raw URI/audience ở trust boundary. |
| Gateway trim/normalize header value | Giá trị được ký có thể khác | Phân định parser và contract value normalization. |
| Gateway thêm `X-Verified: true` | Backend có thể tin sai danh tính | Xóa header từ nguồn ngoài; hop gateway→backend có xác thực, chặn bypass. |
| Proxy nén/giải nén body | SHA-256 body bytes khác | Ràng buộc Content-Encoding hoặc reject transform không được hợp đồng cho phép. |
| Proxy sửa header không được ký nhưng dùng để route | Chuyển client tới tài nguyên khác | Bổ sung vào signed scope hoặc cấm sử dụng dữ liệu đó để quyết định bảo mật. |

**Điểm then chốt:** Thứ tự canonical không thay thế quyết định về **những field nào phải ký** và **server đọc chúng ở đâu**. Nếu client ký giá trị `X-Timestamp` nhưng backend thực thi theo một trường `X-Effective-Timestamp` không ký thì vẫn có lỗ hổng, dù danh sách đã sort đúng.

## 7. Java 17: ký header không phụ thuộc thứ tự trên wire

Ví dụ Java 17 sau triển khai trực tiếp hợp đồng **HMAC-HEADER-ORDER-V1** và mô phỏng một verifier. Dữ liệu mô phỏng là `List<Header>` giữ được **thứ tự và trường trùng** để minh họa. Đây không phải parser HTTP production; trong hệ thống thật, phải bắt duplicate tại ingress trước khi HTTP library gộp chúng.

Hàm `canonical(...)` không duyệt list theo thứ tự đầu vào. Nó:

1. Chuyển tên signed header về lowercase bằng `Locale.ROOT`, chỉ cho phép tập tên **đã định nghĩa**.
2. Reject duplicate signed header dù tên khác case.
3. Kiểm tra các giá trị đúng format; đặc biệt body digest phải khớp với **body bytes thực nhận**.
4. Dựng dòng `signed-headers` và các dòng `name:value` theo **SIGNED_ORDER** bất biến.
5. HMAC trên **byte UTF-8** của canonical string.

### 7.1. Chương trình đầy đủ

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HeaderOrderHmacExample {
    private static final String METHOD = "POST";
    private static final String TARGET = "/v1/payments?currency=VND";
    private static final String AUDIENCE = "payments-api";
    private static final String CLIENT_ID = "partner-42";
    private static final String KEY_ID = "key-2026-11";
    private static final SecureRandom RNG = new SecureRandom();
    private static final List<String> SIGNED_ORDER = List.of(
        "content-type",
        "x-client-id",
        "x-content-sha256",
        "x-key-id",
        "x-nonce",
        "x-timestamp"
    );

    record Header(String name, String value) {}

    record SignedRequest(
        String method, String rawTarget,
        List<Header> headers, byte[] body, String signature
    ) {}

    // Chỉ dùng để chứng minh replay trong một JVM, chưa có TTL.
    static final class DemoNonceStore {
        private final Set<String> seen = ConcurrentHashMap.newKeySet();

        boolean claim(String clientId, String nonce) {
            return seen.add(clientId + ":" + nonce);
        }
    }

    static Map<String, String> checkedHeaders(List<Header> lines) {
        if (lines == null) {
            throw new IllegalArgumentException("Thiếu HTTP headers");
        }
        Map<String, String> signed = new HashMap<>();
        for (Header line : lines) {
            if (line == null || line.name() == null ||
                line.value() == null) {
                throw new IllegalArgumentException("Header null");
            }

            String name = line.name().toLowerCase(Locale.ROOT);
            // Demo từ chối header điều khiển biến đổi nội dung/method.
            if (name.equals("content-encoding") ||
                name.equals("x-http-method-override")) {
                throw new IllegalArgumentException(
                    "Header không được phép với contract"
                );
            }
            if (!SIGNED_ORDER.contains(name)) {
                // Other HTTP headers được xử lý theo policy của ingress.
                // Không ngầm tin chúng khi route/authorize.
                continue;
            }
            String value = line.value();
            if (value.isEmpty() ||
                value.charAt(0) == ' ' ||
                value.charAt(value.length() - 1) == ' ' ||
                value.indexOf('\t') >= 0 ||
                value.indexOf('\r') >= 0 ||
                value.indexOf('\n') >= 0) {
                throw new IllegalArgumentException(
                    "Signed header value không canonical"
                );
            }
            // putIfAbsent phân biệt duplicate kể cả X-NONCE/x-nonce.
            if (signed.putIfAbsent(name, value) != null) {
                throw new IllegalArgumentException(
                    "Duplicate signed header: " + name
                );
            }
        }
        if (signed.size() != SIGNED_ORDER.size()) {
            throw new IllegalArgumentException(
                "Thiếu một hoặc nhiều signed headers"
            );
        }
        if (!"application/json".equals(signed.get("content-type")) ||
            !CLIENT_ID.equals(signed.get("x-client-id")) ||
            !KEY_ID.equals(signed.get("x-key-id")) ||
            !signed.get("x-content-sha256").matches("[0-9a-f]{64}") ||
            !signed.get("x-nonce").matches("[0-9a-f]{32}") ||
            !signed.get("x-timestamp").matches("[1-9][0-9]{0,18}")) {
            throw new IllegalArgumentException(
                "Signed header sai format/policy"
            );
        }
        return signed;
    }

    static String sha256Hex(byte[] body)
            throws GeneralSecurityException {
        return HexFormat.of().formatHex(
            MessageDigest.getInstance("SHA-256").digest(body)
        );
    }

    static String canonical(String method, String rawTarget,
            List<Header> headerLines, byte[] body)
            throws GeneralSecurityException {
        if (!METHOD.equals(method) || !TARGET.equals(rawTarget) ||
            body == null) {
            throw new IllegalArgumentException(
                "Method/URI/body không đúng contract"
            );
        }
        Map<String, String> headers = checkedHeaders(headerLines);
        String actualBodyHash = sha256Hex(body);
        if (!actualBodyHash.equals(headers.get("x-content-sha256"))) {
            throw new IllegalArgumentException("Body hash không khớp");
        }

        StringBuilder text = new StringBuilder();
        text.append("HMAC-HEADER-ORDER-V1\n")
            .append(method).append('\n')
            .append(rawTarget).append('\n')
            .append("audience:").append(AUDIENCE).append('\n')
            .append("signed-headers:")
            .append(String.join(";", SIGNED_ORDER));
        // Không dùng thứ tự xuất hiện của headerLines.
        for (String name : SIGNED_ORDER) {
            text.append('\n').append(name).append(':')
                .append(headers.get(name));
        }
        return text.toString(); // Không có LF ở cuối.
    }

    static byte[] hmac(byte[] secret, String canonical)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(canonical.getBytes(StandardCharsets.UTF_8));
    }

    static SignedRequest sign(byte[] secret, Clock clock)
            throws GeneralSecurityException {
        byte[] body = "{\"orderId\":\"ord-123\",\"amount\":50000}"
            .getBytes(StandardCharsets.UTF_8);
        String bodyHash = sha256Hex(body);
        byte[] nonceBytes = new byte[16];
        RNG.nextBytes(nonceBytes);
        String nonce = HexFormat.of().formatHex(nonceBytes);
        String timestamp = Long.toString(
            clock.instant().getEpochSecond()
        );

        // Thứ tự list cố ý KHÔNG theo alphabet.
        List<Header> lines = List.of(
            new Header("X-Timestamp", timestamp),
            new Header("X-Nonce", nonce),
            new Header("Content-Type", "application/json"),
            new Header("X-Key-Id", KEY_ID),
            new Header("X-Content-SHA256", bodyHash),
            new Header("X-Client-Id", CLIENT_ID)
        );
        String text = canonical(METHOD, TARGET, lines, body);
        String signature = Base64.getEncoder().encodeToString(
            hmac(secret, text)
        );
        return new SignedRequest(
            METHOD, TARGET, lines, body, signature
        );
    }

    static boolean verify(SignedRequest request, byte[] secret,
            Clock clock, DemoNonceStore nonces)
            throws GeneralSecurityException {
        if (request == null || request.signature() == null) {
            return false;
        }
        final String text;
        final Map<String, String> headers;
        try {
            headers = checkedHeaders(request.headers());
            text = canonical(
                request.method(), request.rawTarget(),
                request.headers(), request.body()
            );
        } catch (IllegalArgumentException invalid) {
            return false;
        }

        final long timestamp;
        try {
            timestamp = Long.parseLong(headers.get("x-timestamp"));
        } catch (NumberFormatException overflow) {
            return false;
        }
        long now = clock.instant().getEpochSecond();
        // Window demo: quá khứ tối đa 300 s, tương lai tối đa 60 s.
        if (timestamp < now - 300 || timestamp > now + 60) {
            return false;
        }

        final byte[] supplied;
        try {
            supplied = Base64.getDecoder().decode(request.signature());
        } catch (IllegalArgumentException badBase64) {
            return false;
        }
        if (supplied.length != 32 ||
            !Base64.getEncoder().encodeToString(supplied)
                .equals(request.signature())) {
            return false;
        }
        byte[] expected = hmac(secret, text);
        if (!MessageDigest.isEqual(expected, supplied)) {
            return false;
        }
        // Claim nonce sau khi MAC hợp lệ; production dùng store chung có TTL.
        return nonces.claim(
            headers.get("x-client-id"), headers.get("x-nonce")
        );
    }

    public static void main(String[] args) throws Exception {
        byte[] secret = new byte[32];
        RNG.nextBytes(secret); // Secret test trong một tiến trình.
        Clock fixed = Clock.fixed(
            Instant.parse("2026-11-28T02:00:00Z"), ZoneOffset.UTC
        );
        SignedRequest request = sign(secret, fixed);

        // Tạo HttpRequest với đúng các header theo thứ tự client có.
        URI uri = URI.create(
            "https://api.example.test" + request.rawTarget()
        );
        HttpRequest.Builder builder = HttpRequest.newBuilder(uri)
            .POST(HttpRequest.BodyPublishers.ofByteArray(request.body()));
        for (Header h : request.headers()) {
            builder.header(h.name(), h.value());
        }
        HttpRequest httpRequest = builder
            .header("X-Signature", request.signature())
            .build(); // Không gửi ra mạng trong ví dụ.

        // Wire-order đảo ngược, signature không đổi vì canonical order cố định.
        List<Header> reversed = new ArrayList<>(request.headers());
        Collections.reverse(reversed);
        SignedRequest reordered = new SignedRequest(
            request.method(), request.rawTarget(), reversed,
            request.body(), request.signature()
        );
        if (!verify(request, secret, fixed, new DemoNonceStore()) ||
            !verify(reordered, secret, fixed, new DemoNonceStore())) {
            throw new AssertionError("Đảo header order phải vẫn hợp lệ");
        }

        // Header trùng bị reject kể cả khác chữ hoa/thường.
        List<Header> duplicated = new ArrayList<>(request.headers());
        duplicated.add(new Header(
            "x-nonce", checkedHeaders(request.headers()).get("x-nonce")
        ));
        SignedRequest duplicateRequest = new SignedRequest(
            request.method(), request.rawTarget(), duplicated,
            request.body(), request.signature()
        );
        if (verify(duplicateRequest, secret, fixed, new DemoNonceStore())) {
            throw new AssertionError("Duplicate signed header phải bị từ chối");
        }

        // Đổi giá trị header đã ký nhưng giữ tag cũ.
        List<Header> modified = new ArrayList<>();
        for (Header h : request.headers()) {
            modified.add(h.name().equalsIgnoreCase("X-Client-Id")
                ? new Header(h.name(), "partner-attacker")
                : h);
        }
        SignedRequest tampered = new SignedRequest(
            request.method(), request.rawTarget(), modified,
            request.body(), request.signature()
        );
        if (verify(tampered, secret, fixed, new DemoNonceStore())) {
            throw new AssertionError("Thay signed header phải bị từ chối");
        }

        DemoNonceStore replay = new DemoNonceStore();
        if (!verify(request, secret, fixed, replay) ||
            verify(request, secret, fixed, replay)) {
            throw new AssertionError("Replay phải bị từ chối");
        }
        System.out.println("PASS: " + httpRequest.method()
            + ", canonical header order/duplicate/tampering/replay");
    }
}
~~~

### 7.2. Những điều ví dụ cố ý chưa xử lý

- `List<Header>` mô phỏng raw field lines để bắt duplicate, nhưng `java.net.http.HttpRequest` và server frameworks có thể chuẩn hóa/ghép header. **Server production** phải quyết định chặn duplicate tại ingress/parser có khả năng thấy field lines gốc; sau khi đã gộp, ứng dụng khó chứng minh sự đơn trị.
- Hàm `checkedHeaders` chấp nhận các header ngoài signed set để minh họa sự tồn tại của HTTP metadata. Không được dùng bất kỳ header **không ký** nào để quyết định route, identity, tenant, content decoding hay authorization mà không có kiểm soát phù hợp.
- Ví dụ reject `Content-Encoding` và `X-HTTP-Method-Override` vì body và method có hợp đồng cố định. Nếu một ứng dụng hỗ trợ chúng, phải đưa nội dung/ý nghĩa bảo mật vào phạm vi ký và chính sách parser.
- `DemoNonceStore` dùng chung trong một JVM, **không có TTL**; production phải có shared atomic store với TTL đến hết cửa sổ timestamp và bảo đảm hoạt động giữa các replica.
- Client và verifier trong ví dụ dùng cùng secret ngẫu nhiên để test. Production cần secret manager, tra khóa theo client ID + key ID, kiểm tra audience, trạng thái active/revoked, ngày hết hạn và rotation.
- `TARGET` và `METHOD` cố định cho một endpoint để minh họa; một API thật cần canonical raw URI/query trên request đã nhận, kiểm tra route, parser/encoding, body bytes và authorization.

## 8. Thứ tự field và kiểm tra byte HMAC

**Không được đồng nhất “đúng thứ tự field” với “chắc chắn chữ ký đúng”.** Còn nhiều nguyên nhân làm byte canonical lệch:

| Nguyên nhân | Ví dụ | Khắc phục |
| --- | --- | --- |
| Khác thứ tự signed names | Client sort lexical; verifier theo thứ tự map | Cố định `SIGNED_ORDER` bằng contract và test. |
| Khác chữ hoa/thường của **name** | `X-Key-Id` vs `x-key-id` | Dùng ASCII lowercase cho tên canonical. |
| Khác **value** | `application/json` vs `application/json; charset=utf-8` | Phải định nghĩa policy value chính xác, không tự coi tương đương. |
| Thừa SP sau dấu `:` | `x-client-id: partner-42` vs `x-client-id:partner-42` | Canonical line không có SP sau `:`. |
| LF và CRLF | Một bên dùng LF, bên kia CRLF | Nối dòng đúng một byte LF, không lấy newline OS. |
| Có LF cuối | Một bên thêm xuống dòng sau header cuối | Contract định nghĩa **không có** LF cuối. |
| Body JSON serialize lại | Whitespace hoặc thứ tự JSON field khác | SHA-256 trên đúng body bytes client gửi. |
| URI rewrite | Proxy decode `%2F` thành `/` hoặc reorder query | Ký đúng raw target và verify tại trust boundary. |
| Key ID sai | Verifier chọn secret khác | Ràng buộc key ID trong canonical và key store. |
| Timestamp/nonce bị sửa | HMAC không khớp | Đưa cả hai field vào signed set và thực thi replay checks. |

### 8.1. Chiến lược debug an toàn

Khi HMAC không khớp giữa client/server, đừng log nguyên secret hoặc body thanh toán. Trong môi trường test với dữ liệu giả, có thể so sánh:

1. Contract version, method và raw URI.
2. **Danh sách signed names** theo thứ tự; xác nhận cả hai cùng định nghĩa và không có duplicate.
3. Từng giá trị đã ký sau parser, độ dài chuỗi và byte UTF-8, có hay không whitespace/delimiter bất thường.
4. SHA-256 của body bytes thực gửi/nhận, cùng Content-Type và Content-Encoding policy.
5. Key ID/audience, timestamp/nonce, kết quả Base64 decode và **độ dài tag 32 byte**.

Ở production, log có kiểm soát những thông tin không nhạy cảm như request ID, mã lỗi, version và **danh sách tên header**. Giá trị header nhạy cảm, chữ ký và digest của dữ liệu bí mật cũng có thể cần được hạn chế trong log; không xuất dữ liệu bí mật để “debug nhanh”.

## 9. Replay, key rotation và authorization không phụ thuộc header order

### 9.1. Timestamp và nonce

Nếu một proxy chụp lại request hợp lệ rồi phát lại nguyên bản trong thời gian cho phép, **HMAC và canonical order vẫn đúng**. Để chống replay:

1. Ký `x-timestamp` và `x-nonce` trong canonical theo thứ tự cố định.
2. Server kiểm tra timestamp dựa trên **server clock** với một cửa sổ đã định, ví dụ quá khứ tối đa 300 giây và tương lai tối đa 60 giây.
3. **Sau khi HMAC hợp lệ**, claim nonce nguyên tử trong store chia sẻ giữa replica; nonce trùng phải bị từ chối.
4. TTL nonce phải bao phủ toàn bộ khoảng thời gian request còn được chấp nhận, kể cả trường hợp timestamp đi trước đồng hồ server trong ngưỡng cho phép.

Đối với thao tác có side effect như `POST /v1/payments`, retry **nonce mới** có thể tạo một chữ ký hợp lệ cho cùng nghiệp vụ. Cần **idempotency key** được ký và xử lý nguyên tử trong tầng nghiệp vụ để ngăn giao dịch trùng.

### 9.2. Key rotation

Đừng dùng thứ tự các header trên wire để chọn key. Verifier phải lấy đúng `x-client-id` và `x-key-id` **đơn trị**, tra key store theo cặp identity/key ID và kiểm tra **thuật toán, audience, thời hạn, trạng thái thu hồi**. Trong giai đoạn rotation, server có thể cho phép key cũ/mới trong một cửa sổ chuyển đổi rõ ràng nhưng vẫn áp dụng **cùng hợp đồng canonical** hoặc version được quy định theo key.

Không tự thử mọi key với mọi thuật toán và mọi thứ tự header cho tới khi có một chữ ký khớp. Cách “fallback” đó vừa tốn tài nguyên, vừa có nguy cơ tạo đường downgrade, chấp nhận những representation không rõ ràng.

### 9.3. Xác thực khác phân quyền

HMAC đúng chứng minh request phù hợp với secret và những byte **đã ký**; không chứng minh client được phép dùng mọi tenant, resource hoặc action. Backend vẫn phải:

- Ràng buộc identity đã xác thực với tenant, roles/scopes và resource.
- Dùng đúng method/URI/body đã được ký và xác minh khi định tuyến.
- Từ chối client có chữ ký hợp lệ nhưng vượt quyền.

Việc sort header đúng cách không thể sửa một lỗi **authorization** hoặc một **header không ký** được backend tin nhầm là danh tính.

## 10. Ma trận kiểm thử header order

Tạo client và verifier test có shared secret riêng. Kiểm tra đơn vị trong một JVM trước, sau đó kiểm thử tích hợp thực tế qua HTTP/1.1, HTTP/2 và gateway. Với test replay, giữ nguyên nonce; test độc lập khác cần nonce mới.

| Ca kiểm thử | Đầu vào/thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Happy path | Đủ 6 signed headers, body/URI/method đúng | Canonical và tag khớp; tiếp tục freshness/nonce/authorization. |
| Đảo wire order | Đảo tất cả field line khác tên | **Cùng canonical HMAC**, nếu giá trị/meaning không đổi. |
| Header name khác case | `X-Nonce` thay bằng `x-nonce` | Dựng cùng tên canonical; không đổi tag. |
| Đảo canonical order sai hợp đồng | Verifier ký theo thứ tự map tùy ý | Test phải thất bại; sửa implementation theo `SIGNED_ORDER`. |
| Thiếu signed header | Bỏ `x-key-id` hoặc `x-content-sha256` | Reject, không tự loại khỏi signed set. |
| Duplicate khác case | `X-Timestamp` và `x-timestamp` | Reject tại ingress/parser; không tùy chọn value đầu/cuối. |
| Duplicate giống giá trị | Hai `X-Nonce` trùng nhau | Reject theo single-value contract. |
| Gộp value | Một header `x-client-id: partner-42, partner-99` | Reject vì sai format/identity policy. |
| Value OWS | SP cuối hoặc HTAB bên trong header được ký | Reject theo hợp đồng minh họa. |
| CRLF injection | Chèn newline vào signed value | Parser hoặc validation reject trước verify. |
| Trường không ký điều khiển method | Thêm `X-HTTP-Method-Override: DELETE` | Reject, không để thay effective method. |
| Content encoding không cho phép | Thêm `Content-Encoding: gzip` | Reject, không chuyển đổi body âm thầm. |
| Body sửa sau khi ký | Thay JSON amount | SHA-256/body hash và HMAC mismatch. |
| URI sửa sau khi ký | Thay query `currency=VND` | HMAC mismatch hoặc reject route. |
| HTTP/1.1 ↔ HTTP/2 | Field name viết thường và field order có thể đổi | Cùng canonical cho dữ liệu đã ký; pseudo-header được xử lý theo contract. |
| Header từ proxy không tin | Client đặt `X-Verified: true` | Không bypass xác minh/authorization. |
| Key rotation | Key ID active, overlap, revoked | Chọn đúng secret theo policy; key revoked bị từ chối. |
| Replay tuần tự | Gửi lại cùng signature/timestamp/nonce | Request sau bị từ chối dù HMAC đúng. |
| Replay song song | Hai replica nhận cùng nonce | Tối đa một atomic claim thành công. |
| Thiếu quyền | HMAC hợp lệ nhưng tenant khác | Authentication có thể PASS, **authorization DENY**. |

### Câu hỏi tự kiểm tra

1. Vì sao hai request có cùng tập **header khác tên** nhưng khác thứ tự wire vẫn nên tạo cùng HMAC trong hợp đồng bài này?
2. Khác biệt giữa **sort header names** và **sort các value của repeated header** là gì?
3. Hai field line `X-Client-Id` và `x-client-id` có phải hai tên khác nhau không? Vì sao verifier cần reject duplicate?
4. Nếu client gửi danh sách signed headers chỉ có `x-timestamp` và server chấp nhận, kẻ tấn công có thể tác động đến những trường nào không được ký?
5. Trong HTTP/2, `:method` và `:path` nên được đưa vào canonical như ordinary headers hay theo method/request-target của hợp đồng?
6. HMAC hợp lệ sau khi đảo header order có bảo đảm request không bị replay không? Cần dùng thêm gì?
7. Tại sao một client có chữ ký đúng trên `POST /v1/payments` vẫn có thể bị từ chối khi thanh toán hộ tenant khác?

## 11. Checklist triển khai

- [ ] Xác định rõ **wire header order** khác **canonical header order**; không dựa vào thứ tự duyệt map hoặc field line để ký.
- [ ] Công bố fixed/sorted order và test vectors trong signing contract; cùng thứ tự tại signer/verifier.
- [ ] Chốt **signed header set** bắt buộc, không cho client bỏ field bảo mật; ràng buộc method, raw URI, body digest và audience.
- [ ] Chuẩn hóa **tên header** thành ASCII lowercase; không tự chuẩn hóa value sai với semantics của field.
- [ ] Với signed headers đơn trị, reject duplicate case-insensitive, field bị gộp mơ hồ, CR/LF, HTAB và OWS ngoài contract tại ingress.
- [ ] Không sort/gộp repeated values một cách chung chung; field đa trị nếu cần ký phải có contract riêng bảo toàn thứ tự và cách parse.
- [ ] Định nghĩa một delimiter LF, không LF cuối, encoding UTF-8 và định dạng name:value chính xác.
- [ ] HTTP/1.1, HTTP/2/3 và proxy/gateway phải dẫn tới cùng dữ liệu đã ký; pseudo-headers/authority/path có xử lý riêng.
- [ ] Secret được quản lý theo client ID/key ID, audience, thời hạn và rotation; không fallback qua nhiều key/algorithm/ordering.
- [ ] Timestamp và nonce nằm trong signed set; nonce store chung nguyên tử có TTL; idempotency bảo vệ side effect.
- [ ] Backend chỉ tin identity qua ranh giới xác thực và thực thi **authorization** theo method, tenant và tài nguyên.
- [ ] Kiểm thử reorder, duplicate, HTTP protocol translation, body/URI rewrite, replay, key rotation và đường bypass gateway.

**Ghi nhớ:** **Header order** trong xác thực HMAC là **thứ tự byte của signed header lines trong canonical request**, không phải thứ tự ngẫu nhiên mà HTTP stack nhận được. Quy định danh sách tên được ký, sort tên theo một quy tắc thống nhất, từ chối header trùng/mơ hồ và bảo toàn ý nghĩa giá trị. Một canonical order chính xác giúp chữ ký ổn định qua proxy, nhưng bảo mật còn cần phạm vi ký đầy đủ, secret an toàn, timestamp/nonce, quản lý key và phân quyền.

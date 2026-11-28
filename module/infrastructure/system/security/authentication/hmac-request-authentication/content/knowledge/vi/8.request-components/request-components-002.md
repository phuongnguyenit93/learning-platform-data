# Request target: Ràng buộc URI được gọi vào chữ ký HMAC

Trong HTTP, **request target** là phần request dùng để chỉ ra **đích mà client muốn truy cập**. Với API thông thường, ta gặp đường dẫn và chuỗi truy vấn như `/v1/orders/42?view=full`. Khi xác thực HTTP request bằng HMAC, request target phải được xác định **chính xác và thống nhất** giữa bên ký (client) và bên xác minh (server hoặc API gateway). Một khác biệt về byte, chẳng hạn đổi `%2F` thành `/` hoặc đảo thứ tự query, có thể làm chữ ký không khớp. Nguy hiểm hơn, nếu bộ xác minh và backend **diễn giải request target khác nhau**, chữ ký có thể bảo vệ một đích trong khi hệ thống thực thi một đích khác.

Đây là bài **Request target** thuộc chương **Request components** của module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Ta sẽ tập trung vào việc xác định, ký, xác minh và xử lý request target qua proxy/gateway trong giao thức HMAC với shared secret và canonical request chứa method, URI, header hoặc body theo hợp đồng ký. Timestamp/nonce chống replay, key rotation và phân biệt xác thực với phân quyền được đặt trong mối liên hệ trực tiếp với đích request.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **request target** với URL đầy đủ, path, query, fragment, `Host` và đích định tuyến sau proxy.
2. Nhận biết các dạng request-target của HTTP/1.1 và vai trò `:path` trong HTTP/2/HTTP/3; xác định dạng nào được API HMAC cho phép.
3. Xây dựng hợp đồng canonical request ràng buộc **raw path + raw query** với HTTP method, các header quan trọng, body digest và audience.
4. Giải thích lỗi chữ ký do percent-encoding, tham số trùng, URI normalization và rewrite ở gateway, đồng thời nhận diện rủi ro khi nơi xác minh hiểu URI khác nơi thực thi.
5. Thực hành xây và xác minh chữ ký HMAC-SHA256 trong Java 17 với request target gốc do lớp HTTP tin cậy cung cấp.

## 2. Request target nằm ở đâu trong một HTTP request?

Xét request HTTP/1.1:

```http
POST /v1/orders/42?include=items&lang=vi HTTP/1.1
Host: api.example.test
Content-Type: application/json

{"status":"confirmed"}
```

Request line có ba phần:

| Thành phần | Giá trị | Ý nghĩa |
| --- | --- | --- |
| HTTP method | `POST` | Hành động yêu cầu thực hiện. |
| **Request target** | `/v1/orders/42?include=items&lang=vi` | Đích trong request line, bao gồm đường dẫn và query theo dạng được dùng. |
| HTTP version | `HTTP/1.1` | Phiên bản giao thức trên kết nối hiện tại. |

`Host: api.example.test` là header chỉ định authority/virtual host ở HTTP/1.1, **không phải một phần của request target dạng origin-form** trong ví dụ này. URL hoàn chỉnh mà client thường nghĩ tới là `https://api.example.test/v1/orders/42?include=items&lang=vi`, nhưng `https://` và `api.example.test` không xuất hiện bên trong request target origin-form.

### Path, query và fragment

Với request target `/v1/orders/42?include=items&lang=vi`:

- **Path** là `/v1/orders/42`; dấu `/` phân cách các path segment.
- **Query** là chuỗi **sau dấu `?` đầu tiên**, ở đây `include=items&lang=vi`. Dấu `&`, `=` thường dùng để biểu diễn tham số theo quy ước ứng dụng, nhưng tại tầng URI chúng là ký tự trong raw query.
- **Fragment** là phần sau `#` trong một URL dùng ở client; fragment không được gửi như một phần HTTP request target. Ví dụ trình duyệt mở `/docs#section2` thông thường gửi request cho `/docs`, không gửi `#section2` cho server.

Trong hợp đồng ký HMAC, phải nói rõ **có đưa dấu `?` hay không** và giữ nguyên chuỗi query nào. `/v1/orders`, `/v1/orders?` và `/v1/orders?x=` là **ba raw request target khác nhau**. Nếu hợp đồng ký raw target, không được tự ý gộp chúng lại chỉ vì code ứng dụng coi một số trường hợp có ý nghĩa tương đương.

## 3. Các dạng request-target trong HTTP

Trong HTTP/1.1 có nhiều dạng request-target. Nếu hệ thống chấp nhận không rõ ràng, bộ xác minh rất dễ ký sai vị trí hoặc tái tạo sai dữ liệu.

| Dạng HTTP/1.1 | Ví dụ | Hoàn cảnh thường gặp | Chính sách cho API HMAC minh họa |
| --- | --- | --- | --- |
| **Origin-form** | `/v1/orders?limit=20` | Request gửi tới origin server thông thường. | **Chấp nhận và ký raw path + query**, theo quy tắc V1. |
| **Absolute-form** | `https://api.example.test/v1/orders?limit=20` | Request gửi tới forward proxy. | Từ chối ở endpoint V1 này, trừ khi có hợp đồng hỗ trợ riêng. |
| **Authority-form** | `api.example.test:443` | Request `CONNECT` để tạo tunnel. | Không thuộc API nghiệp vụ V1; từ chối. |
| **Asterisk-form** | `*` | `OPTIONS *`, hướng đến máy chủ nói chung. | Không thuộc API nghiệp vụ V1; từ chối. |

Trong HTTP/2 và HTTP/3, request không có request line theo cùng dạng HTTP/1.1. Đường dẫn và query của request thông thường được biểu diễn bằng pseudo-header `:path`; các pseudo-header `:method`, `:scheme` và `:authority` cung cấp thêm thông tin. Lớp xác minh HMAC phải xây dữ liệu ký từ **giá trị giao thức đáng tin cậy** mà HTTP stack nhận được, theo hợp đồng đã công bố. Không giả định rằng nối tùy ý `:scheme + "://" + :authority + :path` sẽ tạo cùng dữ liệu ký mà client dùng trong một hợp đồng origin-form.

Trong ví dụ của bài, **V1 chỉ hỗ trợ các request thông thường có dạng raw origin-form**; gateway nhận HTTP/2 phải ánh xạ `:path` tới đúng biểu diễn ký được thống nhất, trước khi sửa đường dẫn. Những dạng khác cần phiên bản/chính sách riêng, không mặc nhiên chuyển về một dạng và tiếp tục xác minh.

## 4. “Raw” request target khác đường dẫn đã chuẩn hóa

Các thành phần HTTP có thể diễn giải đường dẫn cùng query theo nhiều cách. “Raw” trong hợp đồng này nghĩa là **giữ nguyên biểu diễn URI được nhận tại điểm xác minh đáng tin cậy**, đặc biệt giữ nguyên percent-encoding và thứ tự query; không tự decode, gộp, sắp xếp hay serialize lại trước khi ký.

| Hai biểu diễn | Có cùng raw target không? | Điều cần làm |
| --- | --- | --- |
| `/v1/items?a=1&b=2` và `/v1/items?b=2&a=1` | Không | Hợp đồng ký raw query giữ đúng thứ tự, kể cả khi ứng dụng diễn giải ra cùng map. |
| `/v1/items?tag=a&tag=b` và `/v1/items?tag=b&tag=a` | Không | Giữ thứ tự; quyết định rõ cách backend xử lý tham số trùng. |
| `/v1/a%2Fb` và `/v1/a/b` | Không | `%2F` có thể bị một tầng decode thành `/`; chính sách an toàn có thể từ chối encoded slash. |
| `/v1/a%2fb` và `/v1/a%2Fb` | Không | Hai chuỗi khác byte dù percent-escape có thể biểu diễn cùng octet. |
| `/v1/./orders` và `/v1/orders` | Không | Một số tầng có thể xóa dấu chấm đoạn path. Cần xử lý nhất quán hoặc từ chối dấu chấm đoạn. |
| `/v1/items?q=a+b` và `/v1/items?q=a%20b` | Không | Trong query form-encoded, `+` thường mang nghĩa khoảng trắng; raw bytes vẫn khác. |
| `/v1/items?x=` và `/v1/items?x` | Không | Không được tự biến query thành map rồi dựng lại nếu hợp đồng ký raw query. |
| `/v1/items` và `/v1/items?` | Không | Phải thống nhất giữ hoặc từ chối empty query delimiter; V1 minh họa giữ nguyên. |

### Vì sao chỉ hash “parsed parameters” là chưa đủ?

Giả sử client ký `/transfer?to=alice&to=bob`. Một framework có thể chọn tham số `to` **đầu tiên**, framework khác chọn **cuối cùng**, framework khác nữa trả cả hai. Nếu gateway ký đối tượng map đã parse nhưng backend quyết định đích chuyển tiền theo một quy tắc khác, **dữ liệu được xác thực không còn ràng buộc rõ nghĩa vụ đang thực thi**.

Tương tự, một route có path `/users/%2e%2e/admin` có thể được một tầng coi là ký tự đã mã hóa, tầng khác decode rồi giải quyết `..`. Không có “chuẩn hóa” tự phát nào an toàn trên mọi proxy/framework. Với path nhạy cảm, hợp đồng nên **quy định dạng duy nhất được chấp nhận**, từ chối các dạng nhập nhằng và kiểm thử đúng tổ hợp gateway/backend đang chạy.

**Nguyên tắc:** Request target được ký phải gắn với **cùng resource và cùng cách diễn giải** mà lớp định tuyến/ứng dụng thực thi. Việc HMAC hợp lệ không ngăn được lỗi phân tích URI nếu bộ xác minh và handler dùng hai cách diễn giải khác nhau.

## 5. Request target trong canonical request HMAC

HMAC-SHA256 xác minh byte của message. Ví dụ V1 dưới đây là một **hợp đồng minh họa** dành cho API JSON, không phải chuẩn chung cho mọi HTTP API:

| Thành phần đưa vào chuỗi ký | Quy tắc V1 |
| --- | --- |
| Version và audience | Hai dòng cố định: `HMAC-SHA256-V1` và `orders-api-prod`. |
| Method | Method viết hoa từ request thực nhận, ví dụ `POST`. |
| **Request target** | Raw origin-form: `/path` cộng `?rawQuery` nếu có, giữ nguyên byte/biểu diễn đã chấp nhận. |
| Content type | Header đã xác minh: `content-type:application/json`. V1 từ chối giá trị khác và header trùng. |
| Key ID | `x-key-id:<keyId>`, dùng để tra đúng secret đang ACTIVE. |
| Timestamp | `x-timestamp:<UTC ISO-8601>`, được ký và kiểm tra trong cửa sổ cho phép. |
| Nonce | `x-nonce:<random nonce>`, được ký, ghi nhận một lần. |
| Body digest | `sha256:<hex chữ thường của SHA-256 trên raw body bytes>`. |
| Nối dòng | UTF-8, mỗi dòng phân cách bằng LF (`\n`), **không có LF cuối**. |
| Wire signature | `X-Signature: v1=<Base64 chuẩn có padding của full 32-byte HMAC>`. |

Request:

```http
POST /v1/orders?channel=partner&currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: partner-a-202611
X-Timestamp: 2026-11-28T02:00:00Z
X-Nonce: xAr7CQJgX0C34prB8gYbVw
X-Signature: v1=<BASE64_HMAC>

{"sku":"BK-42","quantity":2}
```

Canonical string (dòng cuối được thay bằng giá trị SHA-256 thực tế khi chạy):

```text
HMAC-SHA256-V1
orders-api-prod
POST
/v1/orders?channel=partner&currency=VND
content-type:application/json
x-key-id:partner-a-202611
x-timestamp:2026-11-28T02:00:00Z
x-nonce:xAr7CQJgX0C34prB8gYbVw
sha256:<LOWERCASE_HEX_SHA256_OF_RAW_BODY_BYTES>
```

Trong ví dụ này, **toàn bộ raw target là một dòng duy nhất**, không tách query thành map, không sắp xếp tham số và không thêm scheme/Host ngầm. Chữ ký được tạo bằng:

\[
\operatorname{Base64}\big(\operatorname{HMAC\mbox{-}SHA256}(K,\operatorname{UTF8}(C))\big)
\]

Với `K` là shared secret lấy từ credential tương ứng và `C` là canonical string sau khi thay digest body. Hai giá trị `<...>` chỉ là placeholder; chúng **không** phải digest hoặc chữ ký dùng được.

### Có phải luôn ký cả Host, scheme và port?

Không có câu trả lời chung cho mọi giao thức, nhưng **phạm vi nhận dạng dịch vụ phải được ràng buộc**. Trong V1, ta dùng audience cố định `orders-api-prod` bên trong chuỗi ký, đồng thời gateway kiểm tra Host/authority, môi trường và định tuyến từ nguồn tin cậy. Nếu API phục vụ nhiều tenant dựa trên host, hoặc chữ ký có thể dùng ở nhiều virtual host, hợp đồng còn phải ràng buộc host/tenant có ý nghĩa nghiệp vụ (ví dụ ký authority đã chuẩn hóa theo quy tắc rõ ràng). Chỉ ký raw path trong khi bỏ qua host/tenant có thể gây **cross-service replay** khi dùng chung secret.

Scheme có thể biến đổi từ HTTPS ở client thành HTTP nội bộ sau TLS termination; không tự ký scheme backend nhìn thấy nếu client ký scheme công khai. Phần nào được ký phải gắn với ngữ nghĩa tin cậy và có quy tắc ổn định qua các tầng.

## 6. Java 17: tạo canonical request từ raw target

Đoạn Java sau minh họa phần mật mã và **kiểm tra request target dạng origin-form** trong một hợp đồng V1 có chủ ý chặt chẽ. Nó nhận raw target do HTTP adapter/gateway **đáng tin cậy** cung cấp; không tự đọc một header như `X-Original-URI` do client gửi để thay thế giá trị này.

Policy V1 minh họa **từ chối** path có dấu `//`, các path segment `.` hoặc `..`, và các percent escape có thể biểu diễn dấu `/`, dấu `\` hoặc `.` trong **path**. Đây là quy tắc **chọn cho API ví dụ** nhằm tránh một số trường hợp rewrite/route traversal; không được hiểu là mọi API hay mọi chuẩn URI đều bắt buộc từ chối các biểu diễn đó.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Locale;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class RequestTargetHmacV1 {
    private static final String ALGORITHM = "HmacSHA256";
    private static final String AUDIENCE = "orders-api-prod";
    private static final String PREFIX = "v1=";

    private RequestTargetHmacV1() {}

    private static boolean hex(char ch) {
        return ch >= '0' && ch <= '9'
                || ch >= 'a' && ch <= 'f'
                || ch >= 'A' && ch <= 'F';
    }

    /**
     * Bắt buộc origin-form, các ký tự URI đã được percent-encode khi cần.
     * Chỉ kiểm tra phần path để xử lý dấu chấm/encoded slash của V1.
     * HTTP adapter còn phải giới hạn độ dài, header và ngữ nghĩa routing.
     */
    public static void validateRawTarget(String rawTarget) {
        if (rawTarget == null || !rawTarget.startsWith("/")
                || rawTarget.length() > 4096) {
            throw new IllegalArgumentException("Invalid origin-form target");
        }

        for (int i = 0; i < rawTarget.length(); i++) {
            char ch = rawTarget.charAt(i);
            // V1 yêu cầu ASCII hiển thị, không có fragment hoặc backslash.
            if (ch < 0x21 || ch > 0x7e || ch == '#'
                    || ch == '\\') {
                throw new IllegalArgumentException("Invalid target byte");
            }
            if (ch == '%') {
                if (i + 2 >= rawTarget.length()
                        || !hex(rawTarget.charAt(i + 1))
                        || !hex(rawTarget.charAt(i + 2))) {
                    throw new IllegalArgumentException("Invalid percent escape");
                }
                i += 2;
            }
        }

        int question = rawTarget.indexOf('?');
        String path = question < 0
                ? rawTarget : rawTarget.substring(0, question);
        if (path.startsWith("//") || path.contains("//")) {
            throw new IllegalArgumentException("Ambiguous path separators");
        }

        for (String segment : path.split("/", -1)) {
            if (segment.equals(".") || segment.equals("..")) {
                throw new IllegalArgumentException("Dot segment forbidden");
            }
        }

        String lowerPath = path.toLowerCase(Locale.ROOT);
        if (lowerPath.contains("%2f") || lowerPath.contains("%5c")
                || lowerPath.contains("%2e")) {
            throw new IllegalArgumentException("Encoded path delimiter/dot");
        }
    }

    public static byte[] canonicalBytes(
            String method, String rawTarget, String keyId,
            String timestamp, String nonce, byte[] rawBody)
            throws GeneralSecurityException {
        if (!"POST".equals(method) && !"PUT".equals(method)) {
            throw new IllegalArgumentException("Method not allowed");
        }
        validateRawTarget(rawTarget);
        if (keyId == null || !keyId.matches("[A-Za-z0-9_-]{1,80}")
                || timestamp == null
                || !timestamp.matches("[0-9TZ:.-]{20,40}")
                || nonce == null
                || !nonce.matches("[A-Za-z0-9_-]{22,128}")
                || rawBody == null) {
            throw new IllegalArgumentException("Invalid signed fields");
        }

        byte[] digest = MessageDigest.getInstance("SHA-256").digest(rawBody);
        String bodyHash = HexFormat.of().formatHex(digest);
        String canonical = String.join("\n",
                "HMAC-SHA256-V1",
                AUDIENCE,
                method,
                rawTarget,
                "content-type:application/json",
                "x-key-id:" + keyId,
                "x-timestamp:" + timestamp,
                "x-nonce:" + nonce,
                "sha256:" + bodyHash);
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    private static byte[] mac(byte[] secret, byte[] canonicalBytes)
            throws GeneralSecurityException {
        // Quy tắc cấp credential production do hệ thống quản lý khóa áp dụng.
        if (secret == null || secret.length < 32) {
            throw new IllegalArgumentException("Invalid HMAC credential");
        }
        Mac mac = Mac.getInstance(ALGORITHM);
        mac.init(new SecretKeySpec(secret, ALGORITHM));
        return mac.doFinal(canonicalBytes);
    }

    public static String sign(byte[] secret, byte[] canonicalBytes)
            throws GeneralSecurityException {
        return PREFIX + Base64.getEncoder()
                .encodeToString(mac(secret, canonicalBytes));
    }

    public static boolean verify(
            byte[] secret, byte[] canonicalBytes, String signature)
            throws GeneralSecurityException {
        if (signature == null || !signature.startsWith(PREFIX)) {
            return false;
        }
        String encoded = signature.substring(PREFIX.length());
        byte[] supplied;
        try {
            supplied = Base64.getDecoder().decode(encoded);
        } catch (IllegalArgumentException ex) {
            return false;
        }
        if (supplied.length != 32
                || !Base64.getEncoder().encodeToString(supplied)
                          .equals(encoded)) {
            return false;
        }
        byte[] expected = mac(secret, canonicalBytes);
        return MessageDigest.isEqual(expected, supplied);
    }

    public static void main(String[] args) throws Exception {
        // Secret cố định chỉ phục vụ minh họa/test; production dùng CSPRNG.
        byte[] testSecret = new byte[32];
        java.util.Arrays.fill(testSecret, (byte) 0x4a);
        byte[] body = "{\"sku\":\"BK-42\",\"quantity\":2}"
                .getBytes(StandardCharsets.UTF_8);

        byte[] signed = canonicalBytes(
                "POST", "/v1/orders?a=1&b=2", "partner-a-202611",
                "2026-11-28T02:00:00Z", "xAr7CQJgX0C34prB8gYbVw", body);
        String signature = sign(testSecret, signed);
        if (!verify(testSecret, signed, signature)) {
            throw new AssertionError("Expected valid signature");
        }

        // Chỉ đổi thứ tự query là đã đổi dữ liệu ký.
        byte[] reordered = canonicalBytes(
                "POST", "/v1/orders?b=2&a=1", "partner-a-202611",
                "2026-11-28T02:00:00Z", "xAr7CQJgX0C34prB8gYbVw", body);
        if (verify(testSecret, reordered, signature)) {
            throw new AssertionError("Reordered query was accepted");
        }

        try {
            validateRawTarget("/v1/%2e%2e/admin");
            throw new AssertionError("Encoded dot path was accepted");
        } catch (IllegalArgumentException expected) {
            // Đúng chính sách path nghiêm ngặt của V1 minh họa.
        }
        System.out.println("Request-target HMAC checks passed.");
    }
}
```

**Giới hạn của ví dụ:** Đây là phần lõi canonicalization/HMAC, **chưa phải middleware production**. Hàm `canonicalBytes` giả định HTTP adapter đã xác minh thực tế `Content-Type: application/json` là header duy nhất được phép, trích xuất chính xác key ID/timestamp/nonce, giữ được raw body bytes và giới hạn kích thước. Regex timestamp chỉ kiểm tra hình thức cơ bản, **không kiểm tra thời gian hợp lệ**; lớp xác thực phải parse thời gian thật và đối chiếu đồng hồ server. Hàm chưa xử lý registry, nonce store, phân quyền, hoặc sự khác biệt provider/HSM. Validator cũng không thay thế bảo vệ chống double decoding, request smuggling hay chính sách router/proxy.

Không dùng `java.net.URI.normalize()`, `URLDecoder.decode()`, `getPath()` rồi build lại URI trước khi tính chữ ký V1 nếu hợp đồng yêu cầu **raw target**. Với `java.net.URI`, `getPath()` trả về path đã decode trong khi `getRawPath()` giữ phần encoding; tuy nhiên bản thân HTTP adapter/container có thể đã normalize trước khi dữ liệu tới code, nên việc chỉ đổi sang `getRawPath()` **không bảo đảm** lấy được byte gốc từ client.

## 7. Nơi lấy raw request target trong Java web stack

Không có một API Java HTTP duy nhất bảo đảm mọi cấu hình server trả lại raw target **trước mọi rewrite**. Nơi lấy dữ liệu ký phải được chọn và kiểm thử theo hạ tầng thực tế.

| Điểm xác minh | Nguồn request target cần xem xét | Rủi ro |
| --- | --- | --- |
| **Edge gateway** trước rewrite | Dạng raw target / `:path` mà HTTP listener nhận theo giao thức. | Cần kiểm tra normalization/URI parsing xảy ra trước filter/plugin. |
| Servlet backend (`HttpServletRequest`) | `getRequestURI()` và `getQueryString()` có thể dùng để tiếp cận URI/query tương ứng request được container nhận. | Servlet container, security filter, proxy hoặc framework có thể đã chuyển đổi/normalize; phải test đúng cấu hình. |
| Spring MVC | `HttpServletRequest` ở lớp filter hoặc đối tượng request gốc của framework. | Path matcher/router có thể decode/normalize khác verifier; tránh chỉ ký biến `@PathVariable` hay parsed query map. |
| Reverse proxy → backend | Thông tin gốc do proxy đáng tin cậy chuyển qua kênh đã bảo vệ. | Header `X-Original-URI` do client bên ngoài tự gửi có thể bị giả mạo nếu gateway không xóa. |

Ví dụ ý tưởng dùng Servlet **chỉ khi deployment đã bảo đảm hai API phản ánh target theo hợp đồng**:

```java
// request: jakarta.servlet.http.HttpServletRequest
String rawTarget = request.getRequestURI();
String rawQuery = request.getQueryString();
if (rawQuery != null) {
    rawTarget += "?" + rawQuery;
}
// Phải kiểm thử rawTarget với dữ liệu nhận ở edge, bao gồm %2F và ? rỗng.
RequestTargetHmacV1.validateRawTarget(rawTarget);
```

Đây là ví dụ mảnh mã tích hợp, **không bảo đảm** khôi phục raw target giống byte ban đầu trong mọi container hoặc trước rewrite. Nếu endpoint sử dụng context path/servlet mapping, cần xác nhận cụ thể phần prefix **có thuộc request target mà client đã ký không** và không vô tình cắt bỏ nó. Với HTTP/2, cần kiểm thử ánh xạ `:path` qua server; không giả định luôn có request line HTTP/1.1 tương ứng.

### Quy tắc tin cậy giữa gateway và backend

Giả sử gateway đã xác thực HMAC tại mép mạng rồi chuyển principal `clientId` đến backend. Backend chỉ được tin ngữ cảnh đó khi không thể bị client gọi trực tiếp hoặc tự gắn header giống gateway, kênh nội bộ được bảo vệ và gateway xóa header danh tính tự khai trước khi thêm thông tin đã xác minh. Nếu backend bắt buộc xác minh lần nữa, phải định nghĩa rõ lấy **raw target trước rewrite** từ đâu và cách ràng buộc tính toàn vẹn của thông tin đó.

## 8. Chống replay và key rotation có liên quan gì đến request target?

**HMAC chỉ kiểm tra đúng message được ký.** Client có thể gửi lại nguyên `POST /v1/orders?...`, body và signature nếu không có kiểm soát độ mới. Trong V1, timestamp và nonce được đưa vào canonical request **cùng với request target**; thay một trong các thành phần đó đều làm chữ ký cần tính lại.

Quy trình xác minh đầy đủ:

1. Kiểm tra method, raw request target, header ký và kích thước/định dạng request theo hợp đồng.
2. Dùng `X-Key-Id` tra credential đang hoạt động, đúng audience và môi trường; lấy secret tương ứng.
3. Tự dựng canonical bytes gồm method, **raw target**, timestamp, nonce, header cần ký và digest body; tính HMAC, so sánh tag 32 byte an toàn.
4. Kiểm tra timestamp trong cửa sổ cho phép (ví dụ ±300 giây) và claim cặp `(keyId, nonce)` **nguyên tử** trong kho dùng chung giữa các instance.
5. Chỉ sau các kiểm tra trên mới tạo principal đã xác thực, quyết định phân quyền và thực hiện nghiệp vụ.

Nếu nonce store mất kết nối, API bắt buộc chống replay cần **fail closed**. Khi timestamp có thể nhanh hơn server 300 giây, một request được nhận sớm có thể vẫn hợp lệ sau 600 giây; thời gian lưu nonce phải kéo dài tới khi `timestamp + window` hết hiệu lực, cộng biên an toàn. Khi client retry thao tác tạo đơn hàng, nonce/timestamp cần được thay mới và request ký lại; **idempotency** nghiệp vụ vẫn cần để tránh thực thi hai lần.

Khi **key rotation**, mỗi `keyId` trỏ tới một shared secret phiên bản cụ thể. Ví dụ `partner-a-202611` → secret A và `partner-a-202702` → secret B; cùng `clientId` nhưng secret khác nhau. Server chọn **chính xác** secret theo key ID request khai và policy registry, không thử tất cả secret đến khi MAC trùng. Chữ ký tạo cho raw target của đơn hàng A không được dùng lại cho raw target của đơn hàng B nếu target là một phần đã ký.

## 9. Request target, xác thực và phân quyền

Ba lớp kiểm tra sau trả lời ba câu hỏi khác nhau:

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Authentication** | Request có chữ ký hợp lệ cho **method + request target + các trường đã ký** dưới secret của client A không? | `POST /v1/orders/42` được ký hợp lệ bởi `partner-a`. |
| **Authorization** | Client A **được phép** gọi method và resource đó không? | Có quyền `orders:create` nhưng không có quyền `orders:cancel` nên bị cấm hủy đơn. |
| **Business validation** | Yêu cầu trên resource có thỏa điều kiện nghiệp vụ không? | Đơn đã giao không thể hủy dù client được cấp quyền hủy. |

Nếu chỉ ký body mà không ký request target, attacker biết một chữ ký body có thể thử chuyển cùng body đến endpoint khác; tùy hợp đồng, server có thể không phát hiện sự thay đổi đích. Tương tự, nếu chỉ ký path nhưng bỏ method, chữ ký có thể không ràng buộc `GET` với `DELETE`. Vì vậy khi URL quyết định tài nguyên và hành động, **method và request target thường là thành phần bắt buộc phải ký**.

Request target có thể chứa ID tài nguyên hoặc tenant như `/tenants/a/orders/42`. **Ký đúng giá trị này không tự cấp quyền** đọc/sửa đơn 42. Server vẫn phải kiểm tra principal có quyền trên tenant A và đơn đó, đồng thời bảo đảm giá trị được router dùng chính là giá trị đã được kiểm tra. Lỗi `403 Forbidden` vì thiếu quyền khác với `401 Unauthorized` khi xác thực không hợp lệ.

## 10. Tình huống kiểm thử request target

| Tình huống | Kỳ vọng |
| --- | --- |
| `POST /v1/orders?a=1&b=2` được ký bằng key ACTIVE và dữ liệu hợp lệ. | Xác minh thành công khi server nhận đúng raw target và các trường ký khác. |
| Đổi raw query thành `?b=2&a=1`, giữ nguyên chữ ký. | MAC không khớp, từ chối. |
| Đổi `POST` thành `PUT` nhưng giữ target/body/signature. | MAC không khớp hoặc method bị từ chối theo policy. |
| Đổi `/v1/orders` thành `/v1/orders?`. | Chữ ký raw target khác nhau theo V1. |
| Đổi `q=a+b` thành `q=a%20b` hoặc đổi percent-escape hoa/thường. | Chữ ký phải khác nếu raw target khác byte. |
| Percent escape không hợp lệ, fragment, dấu cách raw hoặc path có `..`. | Validator V1 từ chối trước phép HMAC. |
| Path có `%2F`, `%5C` hoặc `%2E`. | Chính sách V1 minh họa từ chối vì có nguy cơ decode/route nhập nhằng. |
| Query có cùng tham số lặp nhưng framework gateway/backend chọn giá trị khác nhau. | Kiểm thử phát hiện sai khác, áp policy phân tích tham số nhất quán hoặc từ chối ambiguous query. |
| Gateway sửa `/public/v1/orders` thành `/v1/orders` trước khi backend xác minh. | Nếu backend ký target đã rewrite, chữ ký không khớp; cần thay điểm xác minh/hợp đồng. |
| Client gửi header `X-Original-URI` giả. | Không dùng header chưa được proxy tin cậy xác thực để tạo dữ liệu ký. |
| HTTP/2 `:path` tương ứng origin-form đi qua gateway HTTP/1.1. | Test cùng canonical bytes/target mà client ký, bảo toàn query và encoding. |
| Client gửi HTTP/1.1 absolute-form, `CONNECT` authority-form hoặc `OPTIONS *`. | V1 từ chối vì chỉ cho phép origin-form cho nghiệp vụ. |
| Timestamp quá hạn hoặc nonce đã được dùng lại. | Từ chối dù raw target và MAC ban đầu hợp lệ. |
| Key ID đã revoked hoặc key của môi trường khác. | Từ chối dù method và raw target đúng. |
| MAC đúng nhưng client không được quyền truy cập resource trong target. | Authentication có thể thành công; authorization từ chối. |

Nên duy trì **test vector** xuyên các client SDK bằng những dữ liệu không nhạy cảm gồm: method, raw request target, selected headers, timestamp, nonce, raw body bytes, body digest, canonical string UTF-8, test secret, MAC output hex và header signature Base64. Kiểm thử cả tình huống **chữ ký đúng nhưng router xử lý target khác**, vì unit test HMAC trên một chuỗi có sẵn sẽ không phát hiện lỗi này.

## 11. Bài tập thực hành

### Bài 1: Hai query cùng ý nghĩa?

Client gửi `GET /v1/items?sort=price&page=1`; gateway đổi thành `GET /v1/items?page=1&sort=price` trước khi backend xác minh. Nếu hai phía dùng hợp đồng ký raw target thì chuyện gì xảy ra?

**Gợi ý:** Các chuỗi raw target khác byte nên HMAC kỳ vọng khác. Không giải quyết bằng cách tự sắp xếp ở backend ngoài hợp đồng; chọn điểm xác minh trước rewrite hoặc thống nhất một phiên bản canonicalization có kiểm thử.

### Bài 2: Target không chứa host

Client ký `POST /v1/orders` bằng secret dùng chung cho hai host `orders.example.test` và `admin.example.test`; canonical request chỉ chứa path/body, không có audience hoặc host. Có rủi ro gì?

**Gợi ý:** Chữ ký có thể được phát lại ở service/host khác nếu những hệ thống đó chấp nhận cùng secret và hợp đồng. Cần tách secret theo audience/môi trường và ràng buộc host/audience đã tin cậy; kiểm tra định tuyến nhất quán.

### Bài 3: Parser của verifier khác parser của backend

Gateway coi `/accounts/%2e%2e/admin` là một chuỗi path được ký, nhưng backend decode và normalize thành `/admin`. Chữ ký đúng có bảo đảm request chỉ truy cập `/accounts/...` không?

**Gợi ý:** Không. MAC chỉ bảo vệ byte được ký; nếu router thực thi một resource khác sau normalization, kết luận bảo mật bị sai. Phải kiểm tra target thực thi và target được ký có cùng ngữ nghĩa, từ chối path nhập nhằng hoặc thống nhất cách parse.

### Bài 4: HTTP/2 và backend HTTP/1.1

Client HTTP/2 ký `:path = /v1/orders?q=a%2Fb`, gateway chuyển thành request HTTP/1.1 có path `/v1/orders?q=a/b`. Server tính MAC trên target nào sẽ nhận được tag như client?

**Gợi ý:** Chỉ target có biểu diễn đúng hợp đồng ban đầu mới cho cùng canonical bytes. Nếu gateway đã decode query, giá trị khác; server cần xác minh trước chuyển đổi hoặc có cách bảo toàn raw target đáng tin cậy. Không thể lấy chữ ký đúng bằng cách sửa dữ liệu đã ký theo suy đoán.

### Bài 5: Chữ ký đúng nhưng tenant khác

HMAC hợp lệ cho `PUT /tenants/a/orders/42` với principal `partner-a`, nhưng principal chỉ có quyền thao tác tenant B. API có thể cho request đi tiếp không?

**Gợi ý:** Không. Chữ ký xác thực người sở hữu secret và bảo vệ target, còn chính sách phân quyền phải từ chối truy cập tenant A; request target được ký không tự cấp quyền trên resource.

## 12. Ghi nhớ

**Request target là một thành phần cốt lõi của canonical request HMAC vì nó ràng buộc chữ ký với tài nguyên/đích HTTP được gọi.** Trong hợp đồng ký raw origin-form, client và server phải thống nhất chính xác **path, dấu `?`, query, percent-encoding và thứ tự ký tự**. Tính HMAC trên target do parser đã sửa có thể tạo lỗi không khớp; nghiêm trọng hơn, parser của verifier và backend không thống nhất có thể khiến một target được ký nhưng target khác lại được thực thi.

Giải pháp có thể kiểm chứng là **định nghĩa một hợp đồng có phiên bản, xác minh tại ranh giới tin cậy, từ chối đường dẫn nhập nhằng, kiểm thử gateway thực tế** và tiếp tục áp dụng shared-secret policy, timestamp/nonce, key rotation và authorization riêng. Với HTTP request authentication, ký chính xác **nơi request sẽ tới** quan trọng không kém ký **nội dung request**.

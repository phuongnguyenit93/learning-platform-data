# Canonical path

**Canonical path** là biểu diễn đường dẫn HTTP theo một hợp đồng thống nhất để client và server tính **cùng một chuỗi byte** khi ký và xác minh request bằng HMAC. Nếu client ký `/v1/orders/42` nhưng gateway hoặc router chuyển request sang tài nguyên khác, chữ ký có thể thất bại hoặc verifier có thể xác nhận một đường dẫn trong khi handler xử lý đường dẫn khác.

Bài thuộc chương **Canonical request** của mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Trong thiết kế HMAC request authentication với shared secret, canonical path là một phần của canonical request cùng HTTP method, query, signed headers, body digest, timestamp, nonce và audience. HMAC kiểm tra toàn vẹn của những **byte đã ký**; server vẫn phải quản lý key rotation, chống replay và phân quyền trên tài nguyên thật sự được xử lý.

> **Nguyên tắc:** Không tồn tại một phép chuẩn hóa path duy nhất an toàn cho mọi HTTP API. Hãy xác định chính xác những biểu diễn path được chấp nhận, dùng cùng hợp đồng ở client–gateway–verifier–router, và từ chối request mà các thành phần có thể hiểu khác nhau.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt raw path, decoded path, canonical path, query, authority và route được framework thực thi.
2. Giải thích các lỗi từ slash lặp, dot segments, percent-encoding, Unicode và double decoding.
3. Thiết kế canonical path có version, với tập đầu vào được chấp nhận và từ chối rõ ràng.
4. Xây dựng Java validator bảo toàn byte path theo hợp đồng đơn giản.
5. Đưa canonical path vào HMAC request signature cùng method, query, header và body digest.
6. Kiểm chứng path ở ranh giới proxy/gateway và đối chiếu với router thực tế.
7. Tách bảo đảm toàn vẹn đường dẫn khỏi chống replay, key rotation và authorization.

## 2. Path nằm ở đâu trong HTTP request?

Xét request:

~~~http
POST /v1/orders/42?dryRun=false HTTP/1.1
Host: api.example.test
Content-Type: application/json

{"status":"confirmed"}
~~~

| Thành phần | Giá trị | Thuộc canonical path? |
| --- | --- | --- |
| Method | `POST` | Không, là thành phần ký riêng |
| Authority/host | `api.example.test` | Không; có thể bảo vệ bằng audience hoặc authority policy |
| **Path** | `/v1/orders/42` | **Có** |
| Query | `dryRun=false` | Không; ký dưới dạng canonical query |
| Body | JSON `{"status":"confirmed"}` | Không; thường ràng buộc bằng body digest |
| Fragment | `#section` | Không; fragment URL không truyền đến HTTP server như một phần request-target thông thường |

Trong HTTP/1.1, request-target thông thường có **origin-form** `/path?query`. Proxy có thể nhận **absolute-form** như `https://api.example.test/path?query`. HTTP/2 thường biểu diễn path và query trong pseudo-header `:path`. Các dạng `CONNECT host:port` và `OPTIONS *` có ngữ nghĩa khác; contract dành cho REST API có thể không hỗ trợ chúng.

Điều cần thiết là chọn một path logic thống nhất sau khi xử lý đúng dạng request-target, **không biến cả URL hoặc query thành path**.

### 2.1. Raw path khác decoded path

~~~text
Raw path:      /v1/files/a%2Fb
Decoded path:  /v1/files/a/b
~~~

Nếu `%2F` là byte được mã hóa nằm trong một tên file, hai chuỗi trên có thể có số segment và ý nghĩa khác nhau. Nếu router coi `/` là dấu phân tách thì `a/b` không còn là một giá trị segment.

| Nguồn dữ liệu | Điều cần xác minh |
| --- | --- |
| Raw request-target tại biên HTTP | Giữ được biểu diễn URI mà client đã gửi hay chưa |
| `HttpServletRequest.getRequestURI()` | Thường trả path chưa decode theo Servlet API, nhưng vẫn có thể đã chịu rewrite ở proxy/container |
| `java.net.URI.getRawPath()` | Giữ percent escapes của đối tượng URI |
| `java.net.URI.getPath()` | Trả path đã decode, có thể mất thông tin phân biệt |
| Framework route variable | Có thể đã qua decoding, matching, path normalization hoặc context-path processing |

**Không sử dụng route variable đã parse làm bằng chứng rằng byte path nhận được từ Internet có dạng đó.** Cần xác định ranh giới verifier sẽ nhận path ở trạng thái nào.

## 3. Canonical path là quyết định bảo mật

HMAC-SHA256 hoặc HMAC-SHA384 chỉ xử lý byte. Nó không biết `/v1/orders/./42` có tương đương `/v1/orders/42` hay không. Tương đương đó phụ thuộc hợp đồng URI, gateway và router.

Ba nhóm vấn đề cần phân biệt:

- **Cùng tài nguyên, khác byte:** `/users/%7Ealice` và `/users/~alice` có thể dẫn đến cùng resource nhưng tạo HMAC khác nếu hai phía dùng raw path khác nhau.
- **Khác tài nguyên, bị gộp thành cùng canonical path:** verifier tự collapse `//` hoặc chuyển chữ hoa thành chữ thường trong khi router phân biệt các path đó.
- **Verifier và handler hiểu khác nhau:** verifier xác nhận path chứa `%2E%2E` nhưng lớp routing decode thành `..` rồi chuyển tới route khác.

Hai bất biến cần đạt:

**Bất biến 1 — xác minh đúng tài nguyên:** Những request mà router coi là khác hành động/tài nguyên không được vô tình chia sẻ cùng canonical request chỉ vì normalize quá rộng.

**Bất biến 2 — xử lý đúng điều đã xác minh:** Sau bước HMAC, không có phép rewrite ngoài contract biến request sang route hoặc resource khác mà chưa được kiểm soát.

Hợp đồng canonical path phải được kiểm thử cùng HTTP router thật. Chỉ unit test hàm nối chuỗi ký là chưa đủ.

## 4. Các nguồn nhập nhằng thường gặp

### 4.1. Slash lặp và slash cuối

~~~text
/v1/orders/42
/v1//orders/42
/v1/orders/42/
~~~

Một framework có thể gộp chúng thành một route; framework khác coi chúng khác nhau. Nếu API không có nhu cầu hỗ trợ, có thể **từ chối slash lặp** và trailing slash (ngoại trừ root `/`) thay vì âm thầm sửa request.

### 4.2. Dot segments

~~~text
/v1/orders/./42
/v1/orders/../admin
/v1/orders/%2E%2E/admin
~~~

Đường dẫn `.` và `..` có thể bị xử lý theo quy tắc URI dot-segment removal. Encoded dot `%2E` có thể trở thành `.` sau bước decode. Nếu verifier và router dùng thứ tự xử lý khác nhau, request có thể vượt qua một kiểm tra trên path nhưng sau đó đi đến resource khác.

Với API không cần dot segment, hãy từ chối cả dạng literal và các escaped form có thể trở thành dot segments; không chấp nhận nhiều lượt decoding làm `%252E%252E` về sau biến thành `..`.

### 4.3. Percent-encoding

Percent-encoding dùng `%HH` với hai chữ số hex. Những trường hợp đáng chú ý:

| Path | Vấn đề |
| --- | --- |
| `/files/a%2Fb` | Encoded slash có thể thay đổi cấu trúc segment |
| `/files/a%5Cb` | Encoded backslash có thể bị xử lý như separator ở một số thành phần |
| `/users/%7Ealice` | Escaped unreserved character (`~`) có thể được chuẩn hóa |
| `/files/%252F` | Encoded percent có nguy cơ double decoding |
| `/x/%2e%2e/y` | Escaped dot có thể trở thành parent segment |
| `/x/%ZZ` | Invalid percent escape |
| `/x/%00` | Encoded NUL gây rủi ro cho parser và lớp native |

Theo nguyên tắc URI, **unreserved characters** là `A-Z`, `a-z`, `0-9`, `-`, `.`, `_`, `~`. Reserved characters như `/` có ý nghĩa cấu trúc trong path; không tự decode reserved escapes nếu điều đó thay đổi route.

Một contract hỗ trợ encoded path phải quy định chữ hoa/thường của hex, cách decode escaped unreserved, xử lý reserved, UTF-8, escaped percent/dot/slash, và số lần decoding được cho phép. **Thông thường không nên có nhiều lượt percent-decoding.**

### 4.4. Unicode và normalization

Hai chuỗi trông giống nhau có thể có byte Unicode khác nhau: dạng có dấu gộp sẵn (NFC) hoặc chữ cơ sở cộng dấu kết hợp. Khi chuyển thành URI, byte UTF-8 thường được percent-encode.

Nếu API cho phép Unicode path, phải quy định **UTF-8 hợp lệ**, có hay không Unicode normalization (ví dụ NFC), cách escape và so sánh tên resource. Nếu chỉ dùng ID kỹ thuật, một contract ASCII-only thường dễ triển khai và audit hơn.

Không tự lowercase path, dùng `trim()` hay Unicode normalization ở một phía mà phía kia không áp dụng cùng quy tắc.

### 4.5. Dấu chấm phẩy, backslash và chữ hoa/thường

~~~text
/v1/orders;active=true/42
/v1/orders/42
/V1/Orders/42
~~~

Một số framework dùng dấu `;` cho matrix parameters, hoặc có cách xử lý dấu gạch chéo ngược khác nhau. Nhiều router phân biệt chữ hoa/thường của path. Contract cần tuyên bố rõ: cho phép hay từ chối `;`, backslash, khoảng trắng, control characters; **giữ nguyên hay chuyển case**. Với mục tiêu tránh nhập nhằng, nên từ chối các dạng không cần thiết.

### 4.6. Query không phải canonical path

~~~text
/v1/orders?status=open
/v1/orders?status=closed
~~~

Hai request có **cùng path** nhưng query khác. Nếu `status` ảnh hưởng đến dữ liệu, query phải được ký trong **canonical query**; không được bỏ query chỉ vì canonical path giống nhau.

## 5. Chọn chính sách canonicalization

Có hai hướng chính:

| Hướng | Cách xử lý | Lợi ích | Đổi lại |
| --- | --- | --- | --- |
| **Chỉ chấp nhận một dạng chính tắc** | Validate raw path; từ chối biến thể | Hợp đồng rõ, giảm parser differential | Có thể không hỗ trợ Unicode/escaped path |
| **Chuẩn hóa nhiều dạng tương đương** | Parse/normalize thành một path chuẩn | Linh hoạt với nhiều client | Phải chứng minh từng phép decode/encode giống router và gateway |

Bài này minh họa hướng thứ nhất bằng **CanonicalPathV1**. Đây là một contract ví dụ có chủ đích hạn chế; nó không phải tuyên bố rằng mọi HTTP URI phải tuân theo các giới hạn đó.

## 6. Hợp đồng CanonicalPathV1: ASCII unreserved, không percent-encoding

Giả sử một REST API chỉ có resource ID kỹ thuật và route:

~~~text
GET    /v1/orders/42
POST   /v1/orders
DELETE /v1/orders/42
GET    /v1/health
~~~

Quy tắc `CanonicalPathV1`:

1. Bắt buộc có dấu `/` đầu tiên; root `/` hợp lệ.
2. Segment không được rỗng; chỉ cho ASCII `A-Z`, `a-z`, `0-9`, `-`, `.`, `_`, `~`.
3. Không có `//` và không có trailing slash ngoại trừ root.
4. Segment nguyên vẹn `.` hoặc `..` bị từ chối; dấu chấm ở trong segment như `report.v2` được phép.
5. **Từ chối mọi dấu `%`**: V1 không có percent-encoding và không thực hiện URL decoding.
6. Từ chối backslash, dấu `;`, khoảng trắng, control characters, NUL và ký tự không phải ASCII.
7. Query marker `?` hoặc fragment marker `#` không được nằm trong đầu vào của path validator.
8. Path phân biệt chữ hoa/thường; không tự lowercase.
9. Độ dài tối đa ví dụ **2.048 byte ASCII**, kiểm tra trước khi tính HMAC.
10. **Canonical path chính là path đã qua validation**. Không sửa input rồi ký một path mà client không hề gửi.

### 6.1. Ví dụ được chấp nhận và bị từ chối

| Input path | Kết quả V1 | Lý do |
| --- | --- | --- |
| `/` | Chấp nhận | Root |
| `/v1/orders/order-42` | Chấp nhận | Các segment unreserved |
| `/v1/files/report.v2` | Chấp nhận | Dấu chấm trong segment hợp lệ |
| `/V1/Orders` | Chấp nhận về cú pháp | Giữ nguyên case; router có thể trả 404 |
| `/v1/orders/` | Từ chối | Slash cuối |
| `/v1//orders` | Từ chối | Segment rỗng |
| `/v1/./orders` | Từ chối | Segment `.` |
| `/v1/../admin` | Từ chối | Segment `..` |
| `/v1/%2E%2E/admin` | Từ chối | Có percent escape |
| `/v1/files/a%2Fb` | Từ chối | Encoded slash không hỗ trợ |
| `/v1/files/%252Fb` | Từ chối | Double encoding không hỗ trợ |
| `/v1/orders;active=true` | Từ chối | Dấu `;` ngoài tập ký tự |
| `/v1/đơn-hàng` | Từ chối | Unicode ngoài phạm vi V1 |
| `/v1/orders?status=open` | Từ chối nếu đưa nguyên vào path validator | Query phải xử lý riêng |

**Kiểm tra cú pháp không đồng nghĩa route hợp lệ hoặc được phép truy cập.** Một path `/v1/admin` có thể đúng dạng V1 nhưng vẫn bị router trả 404 hoặc authorization trả 403.

### 6.2. Vì sao chọn từ chối thay vì “sửa” path?

Giả sử nhận `/v1/orders/../admin`. Nếu tự loại `..` rồi ký `/v1/admin`, verifier đang biến đổi tài nguyên mà client yêu cầu. Điều này có thể hợp lệ ở một giao thức khác, nhưng trong V1 ta **từ chối rõ ràng**.

Giới hạn quan trọng: Nếu proxy đã sửa `..` thành một path khác trước khi verifier nhìn thấy request, validator phía backend không thể khôi phục byte gốc. Vì thế cần xác định ranh giới nhận raw path và cấu hình gateway phù hợp.

## 7. Khi hệ thống thật cần percent-encoding hoặc Unicode path

Một `CanonicalPathV2` hỗ trợ tên file/Unicode có thể làm theo các bước:

1. Đọc raw path ở biên tin cậy; kiểm tra cú pháp từng `%HH` trước khi decode.
2. Quy định chuẩn hex uppercase khi ký (`%2F` thay vì `%2f`) hoặc từ chối biểu diễn không chính tắc.
3. Có thể chuẩn hóa escaped unreserved thành ký tự literal theo contract.
4. **Không mặc nhiên decode encoded slash/backslash** thành path separators; nếu không cần, từ chối `%2F` và `%5C`.
5. Xử lý escaped dot, percent sign và double encoding sao cho không thể biến thành dot segment sau một lượt decode tiếp theo.
6. Từ chối NUL, control characters và byte UTF-8 không hợp lệ.
7. Nếu có Unicode, quy định rõ UTF-8/NFC hay quy tắc so sánh khác; tái encode thành dạng URI xác định.
8. Đảm bảo verifier và router xử lý cùng representation, không có lượt decoding bổ sung tại tầng sau.
9. Chạy differential tests cho từng cặp biểu diễn tương đương hoặc không tương đương.
10. Version hóa những thay đổi về path parsing/canonicalization thay vì âm thầm đổi code.

Các quy tắc ký tự URI và percent-encoding được mô tả trong **RFC 3986**. Tuy nhiên, lựa chọn có cho encoded slash, Unicode hay matrix parameters trong API cụ thể vẫn là vấn đề của **hợp đồng ứng dụng**, không thể chỉ dựa vào một hàm thư viện chung.

### 7.1. Tránh dùng URLDecoder cho path tùy ý

Trong Java, `java.net.URLDecoder` phục vụ form encoding và xử lý dấu `+` thành space. Điều đó không thể áp đặt lên mọi HTTP URI path:

~~~text
Raw path: /files/a+b
Sau form decoding: /files/a b
~~~

Tương tự, `java.net.URI.normalize()` hoặc `java.nio.file.Path.normalize()` không thay thế cho thiết kế HTTP canonical path. Filesystem path và HTTP URI path là hai loại dữ liệu với quy tắc khác nhau.

## 8. Canonical path trong hợp đồng ký HMAC

HMAC bảo vệ chuỗi byte canonical request. Một hợp đồng minh họa dùng HMAC-SHA256 có thể quy định:

~~~text
HMAC-REQUEST-V1
<UPPERCASE_METHOD>
<CANONICAL_PATH_V1>
<CANONICAL_QUERY>
audience:<SERVICE_ID>
content-type:<CANONICAL_CONTENT_TYPE>
x-key-id:<KEY_ID>
x-timestamp:<UNIX_SECONDS>
x-nonce:<NONCE>
body-sha256:<LOWERCASE_SHA256_HEX>
~~~

Mỗi dòng nối bằng **LF** (`\n`), không có LF cuối; toàn bộ canonical text được mã hóa UTF-8. `X-Signature` là kết quả HMAC, không nằm trong chính chuỗi đã ký.

Hợp đồng quy định độc lập cách canonicalize query, signed headers và body digest. Không dùng cách “ký path là đủ” nếu query/method/body có thể thay đổi tài nguyên hoặc thao tác.

### 8.1. Ví dụ HTTP request

~~~http
POST /v1/orders/order-42?dryRun=false HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: partner-a-k3
X-Timestamp: 1790000000
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <base64url-hmac-sha256>

{"status":"confirmed"}
~~~

Canonical path là `/v1/orders/order-42`. Canonical query, theo quy tắc query ví dụ, là `dryRun=false`. Canonical text:

~~~text
HMAC-REQUEST-V1
POST
/v1/orders/order-42
dryRun=false
audience:orders-api
content-type:application/json
x-key-id:partner-a-k3
x-timestamp:1790000000
x-nonce:6bfb21974a08417199273b09ca49a3ec
body-sha256:<64-hex-characters>
~~~

`<64-hex-characters>` phải thay bằng **SHA-256 thực tế của raw UTF-8 body bytes**. Client dùng secret tương ứng `partner-a-k3`:

~~~text
canonicalBytes = UTF8(canonicalText)
tag = HMAC-SHA256(K_mac, canonicalBytes)
X-Signature = Base64URLWithoutPadding(tag)
~~~

Đổi `order-42` thành `order-43` nhưng giữ tag cũ phải làm chữ ký sai. Nếu client sở hữu secret thật và tạo chữ ký mới cho order 43, server vẫn phải kiểm tra **quyền truy cập order 43**.

## 9. Java 17: xác nhận CanonicalPathV1

Một validator tốt cho V1 giữ nguyên string nếu hợp lệ, thay vì sửa input. Ví dụ:

~~~java
import java.util.regex.Pattern;

public final class CanonicalPathV1 {
    // "/" hoặc các segment ASCII unreserved phân cách bởi một "/".
    private static final Pattern ALLOWED =
            Pattern.compile("/(?:[A-Za-z0-9._~-]+(?:/[A-Za-z0-9._~-]+)*)?");

    private static final int MAX_BYTES = 2048;

    private CanonicalPathV1() {}

    /**
     * rawPath phải được adapter HTTP tách riêng khỏi query,
     * chưa bị router decode/normalize ngoài hợp đồng.
     */
    public static String validate(String rawPath) {
        if (rawPath == null
                || rawPath.length() < 1
                || rawPath.length() > MAX_BYTES
                || !ALLOWED.matcher(rawPath).matches()) {
            throw new IllegalArgumentException("Invalid canonical path");
        }

        if (!rawPath.equals("/")) {
            String[] segments = rawPath.substring(1).split("/", -1);
            for (String segment : segments) {
                if (segment.equals(".") || segment.equals("..")) {
                    throw new IllegalArgumentException("Invalid canonical path");
                }
            }
        }

        // Chỉ ASCII nên số UTF-8 bytes bằng rawPath.length().
        return rawPath;
    }
}
~~~

Ví dụ:

~~~java
CanonicalPathV1.validate("/");                    // hợp lệ
CanonicalPathV1.validate("/v1/orders/order-42");  // hợp lệ
CanonicalPathV1.validate("/v1/files/report.v2");  // hợp lệ

// Các lời gọi sau ném IllegalArgumentException:
CanonicalPathV1.validate("/v1//orders");
CanonicalPathV1.validate("/v1/orders/");
CanonicalPathV1.validate("/v1/../admin");
CanonicalPathV1.validate("/v1/%2E%2E/admin");
CanonicalPathV1.validate("/v1/files/a%2Fb");
CanonicalPathV1.validate("/v1/orders?dryRun=false");
~~~

**Lưu ý:** Input của validator phải là đúng raw path tại ranh giới verifier đã chọn. Nếu gateway đã strip prefix hoặc decode `%2F`, validator không thể chứng minh path nhận từ client ban đầu không bị sửa.

### 9.1. Lấy path từ Servlet adapter

Ví dụ một ứng dụng Servlet:

~~~java
// Giả định gateway/container chưa rewrite ngoài contract.
String rawPath = request.getRequestURI();
String canonicalPath = CanonicalPathV1.validate(rawPath);
String rawQuery = request.getQueryString(); // xử lý riêng
~~~

`getRequestURI()` thường lấy URI chưa gồm query, nhưng cần xác minh behavior của container, context path và proxy đang dùng. Không tự thay nó bằng `getPathInfo()` hoặc route variables có thể đã bị decode/mapping.

### 9.2. Đưa path đã xác nhận vào HMAC

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class SignedCanonicalRequest {
    private SignedCanonicalRequest() {}

    public static byte[] canonicalBytes(
            String method,
            String rawPath,
            String canonicalQuery,
            String contentType,
            String keyId,
            long timestampSeconds,
            String nonce,
            byte[] rawBody) throws GeneralSecurityException {

        String path = CanonicalPathV1.validate(rawPath);
        String bodyHex = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(rawBody));

        // Các thành phần ngoài path phải được validate/encode trước,
        // không cho CR/LF làm nhập nhằng canonical text.
        String text = String.join("\n",
                "HMAC-REQUEST-V1",
                method,
                path,
                canonicalQuery,
                "audience:orders-api",
                "content-type:" + contentType,
                "x-key-id:" + keyId,
                "x-timestamp:" + timestampSeconds,
                "x-nonce:" + nonce,
                "body-sha256:" + bodyHex);

        return text.getBytes(StandardCharsets.UTF_8);
    }

    public static String sign(
            byte[] secret, byte[] canonicalBytes)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        byte[] tag = mac.doFinal(canonicalBytes);
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(tag);
    }

    public static boolean verify(
            byte[] secret, byte[] canonicalBytes,
            String signature) throws GeneralSecurityException {

        if (signature == null ||
                !signature.matches("[A-Za-z0-9_-]{43}")) {
            return false;
        }

        byte[] supplied;
        try {
            supplied = Base64.getUrlDecoder().decode(signature);
        } catch (IllegalArgumentException malformed) {
            return false;
        }

        if (supplied.length != 32 ||
                !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(supplied).equals(signature)) {
            return false;
        }

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        byte[] expected = mac.doFinal(canonicalBytes);
        return MessageDigest.isEqual(expected, supplied);
    }
}
~~~

Đây là **mã minh họa**, không phải một HTTP verifier hoàn chỉnh. `method`, `canonicalQuery`, `contentType`, `keyId`, `nonce` phải được kiểm tra định dạng và chuẩn hóa riêng; cấm CR/LF trong thành phần được đưa vào dạng nhiều dòng. Không nhận secret từ caller, không tự tạo principal sau khi mới validate path và không xử lý nghiệp vụ chỉ vì `verify(...)` trả về `true`.

Trong hệ thống thật, server còn phải kiểm tra trạng thái khóa, timestamp, nonce nguyên tử và authorization. Các request có body lớn cần stream body hash và giới hạn kích thước/timeouts để tránh tiêu tốn tài nguyên.

## 10. Gateway, proxy và ranh giới tin cậy

~~~mermaid
flowchart LR
    C[Client] --> G[Reverse Proxy / API Gateway]
    G --> V[HMAC Verifier]
    V --> R[Router]
    R --> H[Business Handler]
~~~

Các phép biến đổi thường gặp ở gateway:

- Bỏ prefix `/public` trước khi chuyển đến backend.
- Decode `%2F`, `%2E`, bỏ dot segments hoặc collapse `//`.
- Bỏ/thêm trailing slash; xử lý URL case khác nhau.
- Chuyển HTTP/2 `:path` sang HTTP/1.1 request-target.
- Gắn các header `X-Forwarded-Prefix` hoặc `X-Original-URI`.
- Retry request sang node khác.

### 10.1. Xác minh HMAC ở gateway

Gateway có thể xác minh **raw path trước rewrite** rồi truyền principal đã xác thực cho backend. Khi đó:

1. Gateway phải dùng đúng canonical path contract và key record.
2. Gateway xóa các header principal do client tự gửi, rồi thiết lập thông tin nội bộ đáng tin.
3. Kết nối gateway–backend được bảo vệ, backend không cho caller bypass gateway.
4. Mapping giữa signed path và handler sau rewrite phải được kiểm thử; rewrite không được đưa request sang resource ngoài phạm vi đã xác minh.

### 10.2. Xác minh HMAC ở backend

Nếu backend tự xác minh HMAC, gateway cần giữ nguyên các thành phần path đã ký hoặc cung cấp **một mapping được định nghĩa chính xác** mà client/verifier cùng biết.

Ví dụ:

~~~text
Client gọi:         /public/v1/orders/42
Gateway forwarding: /v1/orders/42
~~~

Nếu client ký `/public/v1/orders/42` nhưng verifier sử dụng `/v1/orders/42`, MAC sẽ sai. Không được giải quyết bằng cách tùy tiện thử nhiều prefix đến khi chữ ký khớp.

`X-Original-URI`/`X-Forwarded-Prefix` chỉ có thể được tin nếu do gateway được tin cậy thiết lập, gateway xóa giá trị từ Internet và kênh nội bộ được bảo vệ. Không lấy nguyên header do client khai làm path ký.

### 10.3. Parser differential

~~~text
Client gửi:  /v1/tenants/A/%2E%2E/B/orders/42
Verifier:    xem raw path chứa %2E%2E
Router:      decode rồi chuyển tới /v1/tenants/B/orders/42
~~~

Request như vậy có thể khiến verifier và router bất đồng về resource. Nếu contract là V1, **phải từ chối ở ranh giới chưa decode**. Nếu proxy đã biến đổi trước biên, cần sửa cấu hình/kiến trúc để bảo đảm cùng ranh giới nhận và xử lý.

## 11. Canonical path không thay thế replay protection và authorization

HMAC trên canonical path chỉ bảo vệ byte path đã ký. Một request hợp lệ vẫn có thể bị **gửi lại nguyên vẹn**.

### 11.1. Timestamp và nonce

Hợp đồng nên ký `X-Timestamp` và `X-Nonce` cùng path, method và body digest. Server:

1. Kiểm tra timestamp nằm trong cửa sổ cho phép và được HMAC bảo vệ.
2. Chỉ sau khi MAC hợp lệ, ghi nonce vào **shared replay store** bằng thao tác atomic put-if-absent.
3. Từ chối nonce đã dùng; TTL phải che phủ toàn bộ khoảng thời gian request còn được chấp nhận.
4. Khi store lỗi, thực thi chính sách an toàn đã xác định; với thao tác nhạy cảm nên fail closed.

Ngay cả khi retry tạo nonce/chữ ký mới, thao tác thanh toán hoặc đặt hàng vẫn cần **idempotency** để không thực thi trùng nghiệp vụ.

### 11.2. Key rotation

Một principal có thể được cấp hai key ID trong thời gian chuyển khóa:

~~~text
partner-a-k2 -> secret v2, RETIRING
partner-a-k3 -> secret v3, ACTIVE
~~~

Verifier tra chính xác key ID, kiểm tra trạng thái/audience/algorithm và chọn đúng secret. Không tự thử mọi key với mọi cách chuẩn hóa path để tìm một chữ ký hợp lệ. Nếu phiên bản canonicalization thay đổi, phải **version hóa hợp đồng và kiểm thử di trú**, không âm thầm thay bộ quy tắc ở một phía.

### 11.3. Authentication khác authorization

Một client A có secret thật có thể ký request:

~~~http
DELETE /v1/tenants/tenant-B/orders/42 HTTP/1.1
X-Key-Id: tenant-A-partner-k3
X-Timestamp: 1790000000
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <valid-tag>
~~~

Path có thể đúng chuẩn V1 và HMAC có thể khớp với khóa A. **Không có nghĩa A được xóa đơn hàng của tenant B.** Sau xác thực, backend phải kiểm tra principal, action, tenant và resource dựa trên chính sách/owner phía server. HMAC và canonical path không tự cấp quyền.

## 12. Ma trận kiểm thử canonical path

Kiểm thử cần bao phủ **validator**, **HTTP verifier/router**, và **đường đi thật qua proxy/gateway**.

| Test | Input hoặc thao tác | Kỳ vọng với V1 |
| --- | --- | --- |
| Root | `/` | Chấp nhận |
| Path hợp lệ | `/v1/orders/order-42` | Giữ nguyên |
| Dấu chấm trong segment | `/files/report.v3` | Chấp nhận |
| Trailing slash | `/v1/orders/` | Từ chối |
| Double slash | `/v1//orders` | Từ chối |
| Dot segment | `/v1/./orders` | Từ chối |
| Parent segment | `/v1/../admin` | Từ chối |
| Encoded dot | `/v1/%2E%2E/admin` | Từ chối |
| Encoded slash | `/v1/files/a%2Fb` | Từ chối |
| Encoded backslash | `/v1/files/a%5Cb` | Từ chối |
| Double encoding | `/v1/files/%252Fb` | Từ chối |
| Invalid escape | `/v1/%ZZ` | Từ chối |
| Unicode | `/v1/đơn-hàng` | Từ chối theo V1 |
| Matrix parameters | `/v1/orders;all=true` | Từ chối |
| Backslash | Path chứa ký tự backslash | Từ chối |
| Case khác | `/V1/Orders` | Giữ case, route policy quyết định |
| Path quá dài | Hơn 2.048 byte ASCII | Từ chối |
| Query trong path | `/v1/orders?status=open` | Từ chối; query phải tách riêng |
| Đổi path sau ký | `/orders/42` thành `/orders/43`, giữ tag cũ | HMAC sai |
| Đổi method/query | Giữ tag cũ, sửa method/query đã ký | HMAC sai |
| Đổi body | Sửa một byte raw body | HMAC sai nếu digest được ký |
| Timestamp hết hạn | Request quá cũ | Từ chối freshness |
| Replay | Gửi hai lần request cùng nonce | Từ chối bản trùng |
| Replay đồng thời | Hai node nhận cùng nonce | Tối đa một bản qua atomic nonce gate |
| Key bị thu hồi | Ký đúng với secret cũ | Từ chối |
| Gateway strip prefix | Đường đi ngoài và trong khác nhau | Contract xử lý rõ hoặc từ chối |
| Gateway decode encoded slash | Proxy làm `%2F` thành `/` | Không để input ngoài V1 vượt kiểm tra tại biên |
| Verifier/router mismatch | Verifier và handler nhận route khác | Test phải phát hiện |
| Đúng MAC, sai tenant | Client A tới tenant B | Authorization từ chối |

### 12.1. Differential test giữa các biểu diễn

Các cặp nên được đưa vào test:

~~~text
/a/b     và /a//b
/a/b     và /a/./b
/a/b     và /a/%2e/b
/a/b     và /a%2Fb
/a/b     và /a%252Fb
/a/b     và /A/b
/a/~user và /a/%7Euser
~~~

V1 phải từ chối các dạng có `%`, slash lặp hoặc dot segment; path khác case vẫn là hai chuỗi byte khác nhau. Với V2, mỗi cặp cần một quyết định chuẩn hóa/từ chối **rõ ràng và được kiểm thử tại router**.

### 12.2. Quan sát end-to-end

Trong môi trường thử nghiệm, nên so sánh:

~~~text
Raw request-target tại gateway
    -> Raw path được verifier nhận
    -> Canonical path/bytes đưa vào HMAC
    -> Route và resource ID cuối cùng
    -> Kết quả authorization
~~~

Giám sát nội bộ có thể lưu checksum của canonical bytes và mã lỗi để debug; tránh ghi secret, body nhạy cảm hoặc toàn bộ request còn khả năng replay.

## 13. Tình huống: gateway thay đổi prefix

Đối tác ký và gửi:

~~~http
POST /public/v1/orders/42 HTTP/1.1
Host: api.example.test
X-Key-Id: partner-a-k3
X-Timestamp: 1790000000
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <base64url-tag>
~~~

Gateway rewrite:

~~~text
/public/v1/orders/42 -> /v1/orders/42
~~~

Nếu client ký path ngoài nhưng backend xác minh path trong, tag không khớp. Có hai hướng giải quyết:

**Xác minh trước rewrite:** Gateway xác minh signed path ngoài và truyền principal đáng tin cho backend. Gateway cũng phải bảo đảm mapping tới handler được kiểm soát.

**Xác minh sau rewrite với hợp đồng được định nghĩa:** Client/verifier thống nhất path nào được ký, gateway truyền metadata chỉ từ ranh giới tin cậy, và route cuối cùng phải tương ứng với path đã xác minh. Không lấy header “original path” tự khai từ Internet làm nguồn tin.

Trong cả hai hướng, test các path có `%2F`, `..` và `//` để chứng minh một input ngoài V1 không bị normalize mất dấu vết rồi vô tình được chấp nhận.

## 14. Sai lầm thường gặp

### 14.1. Dùng path đã decode trong verifier nhưng raw path trong signer

**Hậu quả:** Chữ ký sai hoặc verifier/router hiểu tài nguyên khác nhau. **Cách xử lý:** Chọn một biểu diễn path đúng hợp đồng và một ranh giới ký/xác minh rõ ràng.

### 14.2. Thử nhiều cách normalize đến khi MAC khớp

**Hậu quả:** Mở rộng không kiểm soát tập request hợp lệ. **Cách xử lý:** Dùng đúng một canonical path contract theo version; từ chối dạng mơ hồ.

### 14.3. Chỉ ký path, bỏ method/query

**Hậu quả:** Caller đổi hành động hoặc tham số quan trọng mà tag vẫn giữ nguyên. **Cách xử lý:** Ký method, path, query và các signed fields có tác động nghiệp vụ.

### 14.4. Tin X-Original-URI do caller gửi

**Hậu quả:** Verifier ký/xác minh một đường dẫn, backend xử lý đường dẫn khác. **Cách xử lý:** Chỉ tin metadata do proxy được tin cậy thiết lập, xóa input không đáng tin tại biên.

### 14.5. Dùng filesystem normalization cho URI

**Hậu quả:** `Path.normalize()` có thể xử lý khác HTTP URI và router. **Cách xử lý:** Thiết kế riêng URI path contract; filesystem access cần kiểm soát path traversal độc lập.

### 14.6. Coi path đúng chuẩn là được phép truy cập

**Hậu quả:** Client có secret hợp lệ vẫn có thể yêu cầu tài nguyên ngoài phạm vi quyền. **Cách xử lý:** Sau HMAC/freshness, kiểm tra authorization theo principal/action/resource/tenant.

## 15. Bài tập tự thực hành

1. **Phân loại path:** Theo V1, giải thích vì sao `/v1/files/report.v3` hợp lệ nhưng `/v1/./files`, `/v1/%2E%2E/admin` và `/v1/orders/` bị từ chối.
2. **Unit test Java:** Viết test cho `CanonicalPathV1.validate()` với root, case khác, Unicode, escaped slash, dot segments, backslash và path dài.
3. **Golden canonical request:** Dùng request mẫu ở mục 8, tính SHA-256 raw body, tạo canonical bytes UTF-8 rồi kiểm tra client và server thu được cùng byte/signature.
4. **Gateway:** Thiết lập client → gateway rewrite `/public` → backend. Xác minh rằng route cuối cùng tương ứng với path được ký và các biến thể encoded/dot/slash bị từ chối theo V1.
5. **Authorization:** Với principal tenant A gọi `DELETE /v1/tenants/B/orders/42`, phân biệt điều kiện để HMAC đúng và điều kiện buộc phân quyền từ chối.

## 16. Checklist triển khai

- [ ] Contract canonical path có version và tập input được chấp nhận/từ chối rõ ràng.
- [ ] Path được tách khỏi method, authority, query và body.
- [ ] Điểm đọc raw path nằm ở ranh giới tin cậy; hiểu các phép rewrite trước verifier.
- [ ] Có quy tắc cho slash lặp, trailing slash, dot segments, case và semicolon.
- [ ] Có quy tắc cho percent-encoding, encoded slash/dot/percent, double decoding và Unicode.
- [ ] Không âm thầm sửa input trong contract chỉ chấp nhận một dạng chính tắc.
- [ ] Verifier, router và handler sử dụng cùng ý nghĩa route/tài nguyên.
- [ ] HMAC ký cả method, canonical path, query, audience và header/body quan trọng.
- [ ] Key ID và timestamp/nonce được ký; nonce store nguyên tử trên nhiều instance.
- [ ] Key rotation có ID/version rõ ràng, secret được bảo vệ và thu hồi đúng chính sách.
- [ ] TLS bảo vệ kết nối; các header original/forwarded chỉ tin khi do proxy đáng tin thiết lập.
- [ ] Authorization theo principal/action/resource/tenant thực thi trước nghiệp vụ.
- [ ] End-to-end test qua gateway thật so sánh path được ký và handler cuối cùng.

## 17. Câu hỏi tự kiểm tra

1. **Canonical path có phải canonical request không?** Không, nó là một thành phần trong canonical request.
2. **Vì sao `/a%2Fb` không được tự coi là `/a/b`?** Vì encoded slash có thể là dữ liệu trong segment, còn slash literal là dấu phân tách.
3. **Tại sao V1 từ chối `/a/../b`?** Để không thay đổi cấu trúc path trước khi ký và giảm khác biệt với router.
4. **Có nên dùng `URLDecoder` cho mọi URI path không?** Không; nó có quy tắc form encoding như chuyển `+` thành space.
5. **Vì sao canonicalization cần version?** Vì thay đổi escaping hoặc normalization sẽ đổi byte được ký.
6. **HMAC trên path đúng có chống replay không?** Không; cần timestamp, nonce và replay store.
7. **Gateway strip prefix có thể làm gì với HMAC?** Khiến path backend dùng khác path client đã ký.
8. **Path đúng chuẩn và HMAC hợp lệ có đủ quyền truy cập không?** Không; cần authorization theo resource và principal.
9. **Vì sao unit test canonicalizer chưa đủ?** Vì gateway, HTTP parser và router có thể xử lý path khác nhau.
10. **V1 có cho Unicode hoặc `%2F` trong path không?** Không; V1 chỉ nhận ASCII unreserved literal segments.

**Kết luận:** Canonical path quyết định **đúng đường dẫn nào được ràng buộc vào HMAC request signature**. Độ an toàn đến từ một hợp đồng byte rõ ràng, được thực hiện nhất quán giữa signer, verifier, gateway và router. Hãy kiểm thử cả tuyến HTTP thực tế, ký các thành phần request quan trọng và tiếp tục áp dụng chống replay, key management và authorization như những lớp bảo vệ riêng.

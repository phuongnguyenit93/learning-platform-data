# Trailing slash

**Trailing slash** là dấu gạch chéo `/` xuất hiện **ở cuối phần path** của URL, ví dụ `/v1/orders/`. Dấu này có vẻ nhỏ, nhưng trong xác thực HTTP request bằng HMAC nó có thể quyết định **dãy byte nào được ký**, request được router ánh xạ đến handler nào, và gateway có cần redirect hoặc rewrite request hay không.

Hai URL sau có thể được ứng dụng phục vụ giống nhau, cũng có thể biểu thị hai tài nguyên khác nhau:

~~~text
https://api.example.test/v1/orders
https://api.example.test/v1/orders/
~~~

Không nên mặc định chúng tương đương. Trong mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, client và server dùng shared secret tạo và xác minh chữ ký từ **canonical request**, thường bao gồm method, URI/path, query, signed headers và/hoặc body digest. Vì thế, cách xử lý trailing slash là một quyết định cụ thể của **hợp đồng ký**, có liên quan trực tiếp đến proxy/gateway, timestamp/nonce chống replay, key rotation và kiểm tra phân quyền.

> **Nguyên tắc:** Chỉ coi `/orders` và `/orders/` tương đương khi toàn bộ hệ thống, từ điểm ký/xác minh đến router và authorization, **thực sự định nghĩa chúng là cùng một tài nguyên và cùng một thao tác**. Nếu không thể bảo đảm điều đó, hãy giữ nguyên dấu slash trong chữ ký hoặc từ chối một dạng.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Xác định trailing slash trong **path**, phân biệt nó với query, scheme, authority và root path.
2. Giải thích vì sao `/v1/orders` và `/v1/orders/` có thể tạo chữ ký HMAC khác nhau.
3. So sánh ba chính sách: **giữ nguyên**, **chỉ cho một dạng**, và **chuẩn hóa thành một dạng**.
4. Thiết kế quy tắc canonical path có version và bảng đầu vào chấp nhận/từ chối.
5. Phân tích cách redirect, HTTP method, API gateway và framework routing ảnh hưởng tới signed request.
6. Viết Java 17 kiểm tra path và kết hợp kết quả vào canonical request HMAC.
7. Lập kiểm thử từ client tới gateway/verifier/router và phân biệt lỗi chữ ký, lỗi replay với lỗi phân quyền.

## 2. Trailing slash thuộc phần nào của URL?

Xét:

~~~http
GET /v1/orders/?status=open HTTP/1.1
Host: api.example.test
~~~

Các phần tương ứng:

| Thành phần | Giá trị | Có chứa trailing slash không? |
| --- | --- | --- |
| Method | `GET` | Không |
| Authority | `api.example.test` | Không |
| Path | `/v1/orders/` | **Có**, ký tự cuối path là `/` |
| Query | `status=open` | Không, tách riêng sau dấu `?` |
| Fragment | Không có trong request-target | Không |

Với URL `https://api.example.test/v1/orders/?status=open`, dấu `/` **đứng trước dấu `?`** là trailing slash. Nếu query có nội dung như `next=/checkout/`, dấu slash cuối của *giá trị query* không phải trailing slash của path.

### 2.1. Root path là trường hợp đặc biệt

Path gốc `/` chỉ gồm một dấu slash:

~~~text
/               -> root path hợp lệ
/v1/orders      -> không có trailing slash
/v1/orders/     -> có trailing slash
/v1/orders//    -> có slash lặp ở cuối
~~~

Không áp dụng máy móc thao tác “xóa slash cuối” lên `/`, vì kết quả sẽ là chuỗi rỗng. Một path rỗng và root path không nên bị hoán đổi tùy ý mà không có quy tắc ở ranh giới HTTP đã xác định.

Trong HTTP, request-target thường là **origin-form** gồm absolute path cộng query, chẳng hạn `GET /v1/orders/?x=1 HTTP/1.1`. Một proxy có thể nhận absolute-form chứa cả scheme và authority. HTTP/2 cũng có biểu diễn `:path`. Tất cả các dạng này cần được ánh xạ nhất quán về **path và query riêng biệt** trước bước HMAC.

### 2.2. Một slash thay đổi byte được ký

Nếu canonical request ký trực tiếp path, hai thông điệp chứa:

~~~text
GET
/v1/orders
~~~

và:

~~~text
GET
/v1/orders/
~~~

khác nhau **một byte ASCII 0x2F** ở cuối dòng path. Với cùng khóa, cùng dữ liệu còn lại và thuật toán HMAC-SHA256, tag được kỳ vọng khác nhau hoàn toàn. Nếu client ký request có slash cuối mà server tự bỏ slash trước khi xác minh, chữ ký thường thất bại.

Mục tiêu của canonicalization không phải là làm hai tag giống nhau bằng mọi giá, mà là **xác định rõ byte nào có ý nghĩa** với giao thức và router.

## 3. Vì sao hai path có thể khác tài nguyên?

Cấu trúc URI và quy tắc routing là hai lớp liên quan nhưng khác nhau. Chuẩn URI không bắt mọi ứng dụng coi `/orders` và `/orders/` tương đương. Tùy framework/cấu hình:

| Request path | Cách ứng dụng có thể xử lý |
| --- | --- |
| `/v1/orders` | Handler danh sách đơn hàng |
| `/v1/orders/` | Cùng handler, handler khác, redirect hoặc 404 |
| `/v1/orders/42` | Handler đơn hàng ID 42 |
| `/v1/orders/42/` | Cùng resource, 404 hoặc route khác |
| `/v1/orders//` | Bị từ chối, collapse slash hoặc match đường dẫn khác |

Ví dụ một framework thiết kế route `/v1/orders` là collection và `/v1/orders/` là một endpoint khác (hoặc 404). Nếu verifier tự bỏ slash cuối nhưng router giữ phân biệt hai path, chữ ký cho `/v1/orders` có thể được dùng lại trên request tới `/v1/orders/` khi những thành phần khác trùng nhau.

Một rủi ro quan trọng là **parser differential**: verifier và router sử dụng hai biểu diễn path khác nhau. Bước xác minh HMAC có thể thành công trên biểu diễn đã chuẩn hóa, nhưng handler thực thi theo path gốc và tạo hành vi không dự kiến.

### 3.1. Không nên dựa vào “trình duyệt thường tự sửa”

HTTP client, framework hoặc reverse proxy đôi khi tự thêm/bỏ slash, trả redirect hoặc follow redirect. Hành vi đó **không phải** một hợp đồng mật mã thống nhất. Khi ký HTTP request, những phép biến đổi tự động có thể làm HMAC sai hoặc phát sinh request mới với method/body khác.

Hãy kiểm chứng hành vi thực tế ở **đúng phiên bản gateway, HTTP client và framework** mà hệ thống sử dụng.

## 4. Ba chính sách xử lý trailing slash

### 4.1. Chính sách A: giữ nguyên và phân biệt

Contract quy định:

~~~text
canonicalPath("/v1/orders")  = "/v1/orders"
canonicalPath("/v1/orders/") = "/v1/orders/"
~~~

Dấu slash cuối **thuộc byte được ký**. Hai request cần được ký riêng. Chính sách này phù hợp khi API có chủ đích hỗ trợ cả hai dạng, nhưng phải đảm bảo router và authorization cũng hiểu chúng phù hợp với contract.

Ưu điểm là không biến đổi path trước khi ký; hạn chế nhập nhằng giữa dữ liệu gửi và dữ liệu xác minh. Đổi lại, client phải ký đúng URL được gửi; gateway không thể tùy tiện thêm/bỏ slash.

### 4.2. Chính sách B: chỉ cho một dạng

Contract quy định **root `/` được phép**, còn path khác **không được kết thúc bằng `/`**:

~~~text
/v1/orders   -> chấp nhận
/v1/orders/  -> từ chối
/            -> chấp nhận
~~~

Client cần sử dụng URL chính thức. Verifier **từ chối** đầu vào sai thay vì tự sửa nó. Đây là cách đơn giản, dễ audit cho API server-to-server kiểm soát được client và tài liệu endpoint.

Có thể chọn dạng ngược lại, tức yêu cầu slash cuối với một tập route, nhưng phải giải quyết root và tên tài nguyên/endpoint nhất quán.

### 4.3. Chính sách C: chuẩn hóa tương đương có kiểm soát

Một hợp đồng khác có thể tuyên bố:

~~~text
canonicalPath("/v1/orders")  = "/v1/orders"
canonicalPath("/v1/orders/") = "/v1/orders"
canonicalPath("/")           = "/"
~~~

Đây là lựa chọn có điều kiện: **verifier, router, gateway và authorization phải xem hai request là cùng thao tác trên cùng resource**. Không được tồn tại endpoint riêng hoặc khác scope theo slash cuối.

Quan trọng: nếu cả hai path cùng được chuẩn hóa thành một chuỗi HMAC, **chữ ký có thể được tái sử dụng giữa hai biểu diễn path**. Điều đó chỉ an toàn nếu việc coi chúng cùng ý nghĩa là một quyết định của protocol và tất cả các tầng tuân theo quyết định đó.

### 4.4. Bảng so sánh

| Chính sách | `/orders` | `/orders/` | Rủi ro phải quản lý |
| --- | --- | --- | --- |
| A. Preserve exact | Ký nguyên văn | Ký nguyên văn, tag khác | Client/gateway phải giữ đúng byte |
| B. Reject trailing slash | Chấp nhận | Từ chối | Client phải gọi đúng URL chính thức |
| C. Normalize equivalent | Ký thành `/orders` | Ký thành `/orders` | Phải chứng minh router/handler/permissions thực sự tương đương |

**Khuyến nghị thực hành cho bài học:** Chọn chính sách **B**, từ chối trailing slash trừ root, vì nó thể hiện rõ việc validator không tự thay đổi request. Nếu dự án có yêu cầu tương thích buộc phải giữ cả hai dạng, dùng A hoặc C với bộ test xác nhận hành vi cuối cùng.

## 5. Một hợp đồng canonical path cụ thể: NoTrailingSlashV1

Để viết ví dụ Java và kiểm thử rõ ràng, giả định API chỉ dùng ID kỹ thuật với ký tự ASCII **unreserved**. Định nghĩa:

1. Path phải bắt đầu bằng `/`; root `/` được chấp nhận.
2. Segment không được rỗng; từ chối `//`.
3. Segment nguyên vẹn `.` hoặc `..` bị từ chối.
4. Segment chỉ chứa `A-Z`, `a-z`, `0-9`, `-`, `.`, `_`, `~`.
5. Với path **khác root**, nếu ký tự cuối là `/` thì **từ chối**.
6. **Từ chối mọi percent escape (`%HH`)** trong V1. API này không cần encoded slash, Unicode path hoặc escaped dot; những nhu cầu đó đòi hỏi một contract khác.
7. Từ chối backslash, dấu `;`, khoảng trắng, control characters, query marker `?`, fragment marker `#` và ký tự ngoài ASCII.
8. Giữ nguyên chữ hoa/chữ thường.
9. Độ dài path tối đa ví dụ **2.048 byte**, được kiểm tra trước khi ký.
10. Canonical path = **chính path đã được validate**, không chạy `stripTrailingSlash` rồi mặc nhiên chấp nhận.

### 5.1. Bảng quyết định đầu vào

| Raw path | V1 | Giải thích |
| --- | --- | --- |
| `/` | Chấp nhận | Root là ngoại lệ |
| `/v1/orders` | Chấp nhận | Có một slash phân tách segment |
| `/v1/orders/42` | Chấp nhận | Đúng cấu trúc |
| `/v1/files/report.v2` | Chấp nhận | Dấu chấm nằm trong segment |
| `/v1/orders/` | **Từ chối** | Có trailing slash |
| `/v1/orders/42/` | **Từ chối** | Có trailing slash |
| `/v1/orders//` | **Từ chối** | Slash lặp |
| `//` | **Từ chối** | Không phải root hợp lệ |
| `/v1//orders` | Từ chối | Segment rỗng |
| `/v1/./orders` | Từ chối | Dot segment |
| `/v1/../admin` | Từ chối | Parent segment |
| `/v1/%2Forders` | Từ chối | Không hỗ trợ percent-encoding |
| `/v1/%2E%2E/admin` | Từ chối | Encoded dot |
| `/v1/orders?x=1` | Từ chối nếu đưa cả chuỗi vào validator | Query phải được tách riêng |
| `/V1/Orders` | Chấp nhận về cú pháp | Không đổi chữ hoa/thường |
| `/v1/đơn-hàng` | Từ chối | Unicode path ngoài phạm vi V1 |

V1 là **hợp đồng ví dụ**, không phải chuẩn URL chung của Internet. Một ứng dụng cần Unicode, percent-encoding hoặc path có dấu slash cuối có thể chọn protocol version khác với bộ kiểm thử tương ứng.

## 6. Java 17: validator không tự xóa trailing slash

Ví dụ Java sử dụng regex để nhận một dạng canonical path duy nhất. Regex chỉ dùng ký tự ASCII; kiểm tra segment loại bỏ `.` và `..`.

~~~java
import java.util.regex.Pattern;

public final class NoTrailingSlashPathV1 {
    // "/" hoặc nhiều segment ASCII unreserved phân cách bởi đúng một "/".
    private static final Pattern CANONICAL =
            Pattern.compile("/|/[A-Za-z0-9._~-]+(?:/[A-Za-z0-9._~-]+)*");

    private static final int MAX_PATH_BYTES = 2048;

    private NoTrailingSlashPathV1() {}

    /**
     * Input là raw path đã tách khỏi query ở HTTP adapter tin cậy.
     * Không dùng route variable đã decode/normalize.
     */
    public static String validate(String rawPath) {
        if (rawPath == null
                || rawPath.length() > MAX_PATH_BYTES
                || !CANONICAL.matcher(rawPath).matches()) {
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

        // Vì chỉ nhận ASCII, số ký tự bằng số UTF-8 byte.
        return rawPath;
    }
}
~~~

Những lời gọi sau minh họa behavior:

~~~java
NoTrailingSlashPathV1.validate("/");               // "/"
NoTrailingSlashPathV1.validate("/v1/orders");      // "/v1/orders"
NoTrailingSlashPathV1.validate("/files/report.v2"); // hợp lệ

// Đều ném IllegalArgumentException:
NoTrailingSlashPathV1.validate("/v1/orders/");
NoTrailingSlashPathV1.validate("/v1//orders");
NoTrailingSlashPathV1.validate("/v1/../admin");
NoTrailingSlashPathV1.validate("/v1/%2Forders");
NoTrailingSlashPathV1.validate("/v1/đơn-hàng");
~~~

Không nên thay validation bằng:

~~~java
// VÍ DỤ KHÔNG NÊN DÙNG CHO CONTRACT NÀY:
String canonical = rawPath.endsWith("/")
        ? rawPath.substring(0, rawPath.length() - 1)
        : rawPath;
~~~

Phép cắt đó có thể biến root `/` thành chuỗi rỗng, che giấu việc client gửi path ngoài contract và làm sai khác với router. Với chính sách B, cách đúng là **từ chối request chứa trailing slash ngoài root**.

### 6.1. Java URI và Servlet cần kiểm chứng tại ranh giới

Đối với một đối tượng URI, `getRawPath()` khác `getPath()`: cái thứ nhất giữ percent-encoding, cái thứ hai trả biểu diễn đã decode. Với Servlet:

~~~java
// Minh họa, khi gateway đã được cấu hình theo contract.
String rawPath = request.getRequestURI();
String canonicalPath = NoTrailingSlashPathV1.validate(rawPath);
String rawQuery = request.getQueryString(); // canonicalize riêng
~~~

`getRequestURI()` không gồm query, nhưng nó vẫn có thể phản ánh path **đã được proxy rewrite** hoặc có context path. Trước khi chọn API làm nguồn cho chữ ký, cần test actual gateway/container configuration.

Nếu HTTP adapter đã tự loại slash cuối trước khi validator chạy, không có cách nào để validator phát hiện rằng client ban đầu gửi `/orders/`. Cần di chuyển kiểm tra lên gateway, hoặc thay đổi cách truyền path sao cho dữ liệu tại ranh giới xác minh được định nghĩa tường minh.

## 7. Đưa trailing slash vào canonical HMAC request

Giả sử hợp đồng ký `HMAC-REQUEST-V1` dùng HMAC-SHA256 với shared secret và các dòng sau:

~~~text
HMAC-REQUEST-V1
<HTTP_METHOD>
<CANONICAL_PATH>
<CANONICAL_QUERY>
audience:<SERVICE_ID>
content-type:<CONTENT_TYPE>
x-key-id:<KEY_ID>
x-timestamp:<UNIX_SECONDS>
x-nonce:<NONCE>
body-sha256:<LOWERCASE_SHA256_HEX>
~~~

Dòng được nối bằng **LF** (`\n`), không có LF ở cuối; toàn bộ encode UTF-8. Dữ liệu đầu vào phải được validate không chứa CR/LF phá cấu trúc. Chữ ký `X-Signature` là kết quả HMAC nên không đưa chính nó vào canonical bytes.

### 7.1. Request mẫu

~~~http
POST /v1/orders?source=partner HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Key-Id: partner-a-k3
X-Timestamp: 1790000000
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <base64url-hmac-sha256>

{"orderId":"order-42","status":"paid"}
~~~

Các thành phần:

~~~text
method:         POST
canonical path: /v1/orders
canonical query: source=partner
audience:       orders-api
body digest:    SHA-256(raw JSON bytes)
~~~

Canonical request, sau khi thay hash thực tế:

~~~text
HMAC-REQUEST-V1
POST
/v1/orders
source=partner
audience:orders-api
content-type:application/json
x-key-id:partner-a-k3
x-timestamp:1790000000
x-nonce:6bfb21974a08417199273b09ca49a3ec
body-sha256:<64-hex-characters>
~~~

`<64-hex-characters>` là placeholder, phải được thay bằng digest thật của **chính byte body gửi qua HTTP**. Client tính:

~~~text
canonicalBytes = UTF8(canonicalRequest)
tag = HMAC-SHA256(K_mac_for_partner_a_k3, canonicalBytes)
X-Signature = Base64URLWithoutPadding(tag)
~~~

Trong hợp đồng **NoTrailingSlashV1**, request `POST /v1/orders/` bị từ chối trước khi xác minh chữ ký. Không được âm thầm biến nó thành `/v1/orders`.

### 7.2. Nếu chọn chính sách Preserve Exact

Một hợp đồng khác có thể cho phép cả hai path, nhưng phải giữ nguyên và ký chính xác:

~~~text
POST
/v1/orders

POST
/v1/orders/
~~~

Hai canonical requests khác nhau về path nên không sử dụng cùng tag. Nếu client sửa URL từ một dạng sang dạng kia, cần **tạo chữ ký mới** với đúng path cuối cùng.

### 7.3. Nếu chọn chính sách Normalize Equivalent

Nếu hệ thống đã xác minh rằng hai path **hoàn toàn tương đương về router và quyền**, contract có thể cho phép chúng được canonicalize thành cùng một path. Khi đó phải:

1. Tài liệu hóa chính xác phạm vi được coi tương đương.
2. Bảo đảm verifier và router cùng quyết định equivalence.
3. Không dùng quy tắc này để che các dạng `//`, `..` hoặc encoded slash nếu ngoài contract.
4. Kiểm thử rằng việc thay slash không khiến request tới route, tenant hoặc handler khác.
5. Gắn phiên bản canonicalization vào protocol để tránh thay đổi behavior mà client không biết.

Không nên lựa chọn normalize chỉ vì muốn “giảm lỗi signature” khi chưa kiểm tra route semantics.

## 8. Ví dụ Java: tạo và xác minh chữ ký có path V1

Mã sau minh họa cách dùng path đã được validate để tạo canonical bytes và tính tag. Đây là một **primitive helper**, chưa phải HTTP security filter hoàn chỉnh:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class SignedOrderRequest {
    private SignedOrderRequest() {}

    public static byte[] canonicalBytes(
            String method,
            String rawPath,
            String canonicalQuery,
            String contentType,
            String keyId,
            long timestamp,
            String nonce,
            byte[] rawBody) throws GeneralSecurityException {

        String canonicalPath = NoTrailingSlashPathV1.validate(rawPath);
        String bodyHash = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(rawBody));

        // Các tham số ngoài path phải được validate/encode ở lớp riêng.
        String canonical = String.join("\n",
                "HMAC-REQUEST-V1",
                method,
                canonicalPath,
                canonicalQuery,
                "audience:orders-api",
                "content-type:" + contentType,
                "x-key-id:" + keyId,
                "x-timestamp:" + timestamp,
                "x-nonce:" + nonce,
                "body-sha256:" + bodyHash);

        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    public static String sign(byte[] secret, byte[] canonicalBytes)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));

        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(mac.doFinal(canonicalBytes));
    }

    public static boolean verify(
            byte[] secret, byte[] canonicalBytes, String signature)
            throws GeneralSecurityException {

        if (signature == null
                || !signature.matches("[A-Za-z0-9_-]{43}")) {
            return false;
        }

        byte[] supplied;
        try {
            supplied = Base64.getUrlDecoder().decode(signature);
        } catch (IllegalArgumentException malformed) {
            return false;
        }

        if (supplied.length != 32
                || !Base64.getUrlEncoder().withoutPadding()
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

**Giới hạn cố ý của ví dụ:**

- `canonicalQuery`, `method`, `contentType`, `keyId` và `nonce` phải đã được validate/chuẩn hóa, không chứa CR/LF hay byte mơ hồ trước khi nối chuỗi.
- Chưa có key registry: secret phải được server tra theo **đúng key ID đang hiệu lực**, không nhận từ HTTP request.
- Chưa có kiểm tra timestamp, nonce store, quyền truy cập, body limit, HTTP parser hoặc proxy behavior.
- `verify` chỉ kiểm tra MAC; không cho business handler chạy nếu chưa hoàn thành **freshness, replay và authorization**.
- Hash body phải dùng raw bytes được gửi/nhận tại ranh giới ký đã định nghĩa; không parse rồi serialize JSON tùy tiện.

## 9. Redirect và trailing slash: điểm dễ gây lỗi

Nhiều web framework và server có thể trả redirect từ `/orders` sang `/orders/` hoặc ngược lại để thống nhất URL. Điều này có thể tiện cho trình duyệt, nhưng có ảnh hưởng lớn tới signed HTTP requests.

~~~mermaid
sequenceDiagram
    participant C as Signed HTTP Client
    participant G as Gateway / Router
    participant V as HMAC Verifier

    C->>G: POST /v1/orders/ + signature của path có slash
    G-->>C: Redirect sang /v1/orders
    C->>V: Request mới sang /v1/orders
    Note over C,V: Phải ký lại đúng method/path/body/metadata mới
    V->>V: HMAC + timestamp/nonce + authorization
~~~

### 9.1. Redirect tạo ra request mới

Một client có thể tự động follow redirect và gửi **một HTTP request khác**. Nếu request cũ ký path `/v1/orders/` nhưng request mới gửi `/v1/orders`, chữ ký cũ không còn đúng theo chính sách preserve exact.

Nếu ứng dụng chọn redirect như một phần protocol, client nên **xác định URL đích cuối cùng, tạo timestamp/nonce phù hợp và ký lại request mới**. Không đơn giản chuyển tiếp chữ ký cũ, đặc biệt khi request có body hoặc được gửi tới một authority khác.

### 9.2. HTTP status code có thể ảnh hưởng method/body

| Redirect | Ngữ nghĩa quan trọng với signed requests |
| --- | --- |
| `301` / `302` | Một số client có hành vi chuyển `POST` sang `GET` khi follow; cần kiểm tra client cụ thể |
| `303` | Thường dẫn sang `GET` cho request tiếp theo |
| `307` / `308` | Được định nghĩa để giữ HTTP method khi redirect; việc tái gửi body phụ thuộc khả năng client và policy |

Dù method được giữ, **URL path đã thay đổi** vẫn cần chữ ký hợp lệ cho request đích. Với `POST` thanh toán, việc tự động retry sau redirect còn có thể dẫn đến **lặp nghiệp vụ** nếu request trước đã được xử lý.

### 9.3. Không chuyển credential tùy tiện sang đích khác

Nếu redirect sang host/scheme khác, client phải kiểm soát việc gửi `Authorization`, `X-Key-Id` và `X-Signature` đến đích mới. Không follow redirect đến một origin không được tin cậy kèm credential hoặc thông điệp nhạy cảm. HMAC không mã hóa body; HTTPS/TLS vẫn cần bảo vệ kết nối.

Với API server-to-server, một thực hành đơn giản là **không dựa vào redirect để sửa trailing slash**. Client gọi URL chính thức và ký đúng request đó. Với request sai contract, verifier có thể từ chối rõ ràng thay vì redirect trước/sau bước xác thực theo hành vi khó kiểm soát.

## 10. Proxy/gateway: request được ký và request được xử lý có giống nhau không?

~~~mermaid
flowchart LR
    C[Client] --> G[Reverse proxy / API gateway]
    G --> V[HMAC verifier]
    V --> R[Router]
    R --> H[Business handler]
~~~

Những phép biến đổi thường gặp:

- Proxy tự thêm hoặc bỏ trailing slash.
- Proxy bỏ prefix `/public` hoặc `/api`.
- Framework redirect tới route có slash theo mặc định.
- Proxy gộp `//` hoặc xử lý dot segments.
- Load balancer chuyển sang instance khác với cấu hình router khác.
- Client tự follow redirect rồi gửi method/body khác request ban đầu.

### 10.1. Xác minh ở gateway

Gateway có thể xác minh path **nguyên bản ở biên**, rồi rewrite có kiểm soát để chuyển đến backend. Khi đó cần:

1. Xác minh HMAC trên canonical path được hợp đồng xác định.
2. Đảm bảo mapping path ngoài → route nội bộ là duy nhất và không bị người dùng thao túng.
3. Truyền principal đã xác thực qua kết nối nội bộ đáng tin; xóa header principal do client tự khai.
4. Không cho backend bị truy cập trực tiếp để bỏ qua kiểm tra tại gateway.
5. Kiểm thử method, body, query, path và authorization với các biến thể slash.

### 10.2. Xác minh ở backend

Nếu verifier đặt trong backend, proxy phải giữ nguyên representation theo hợp đồng hoặc cung cấp một mapping rõ ràng. Ví dụ:

~~~text
Client gọi:        /public/v1/orders/
Gateway chuyển:    /v1/orders
Verifier nhận:     /v1/orders
~~~

Nếu contract yêu cầu ký path ngoài, backend không thể tự suy ra path gốc chỉ từ path đã rewrite. Không tin `X-Original-URI` hoặc `X-Forwarded-Prefix` từ Internet; chỉ có thể sử dụng metadata do một proxy được tin cậy thiết lập, sau khi đã xóa giá trị tự khai và bảo vệ kênh nội bộ.

### 10.3. Nguy cơ khác nhau giữa verifier và router

Giả sử verifier dùng hàm `removeTrailingSlash` trước khi ký, nhưng router có các endpoint:

~~~text
POST /v1/orders   -> tạo đơn hàng
POST /v1/orders/  -> endpoint quản trị cũ
~~~

Khi đó **cùng một canonical path có thể dẫn đến hai hành động khác nhau**. Nếu handler thứ hai có quyền khác, đây là ranh giới xác thực bị thiết kế sai. Cần sửa policy path, loại route nhập nhằng hoặc xác minh theo đúng dạng mà router thực thi. Không chọn normalization C khi hai route thực sự khác ý nghĩa.

## 11. Trailing slash, timestamp/nonce và key rotation

### 11.1. Chữ ký đúng không ngăn replay

Dù canonical path hoàn hảo, attacker vẫn có thể phát lại **nguyên vẹn request đã ký**. Vì vậy contract HMAC nên ký `X-Timestamp` và `X-Nonce`. Verifier:

1. Kiểm tra timestamp trong cửa sổ được phép.
2. Tái tạo canonical request và so sánh HMAC đúng key.
3. **Chỉ sau khi MAC hợp lệ**, ghi nonce bằng atomic put-if-absent trong kho dùng chung giữa các instance.
4. Từ chối nonce đã xuất hiện; TTL của nonce phải bao phủ toàn bộ thời gian timestamp còn được chấp nhận.
5. Áp dụng policy fail closed cho API nhạy cảm nếu nonce store mất kết nối.

Một client bị redirect rồi ký lại request mới cần cân nhắc **nonce mới**; nếu lần trước đã vượt replay gate, dùng lại nonce sẽ bị từ chối. Với thanh toán, idempotency nghiệp vụ vẫn cần thiết ngay cả khi request mới có nonce mới.

### 11.2. Key rotation và protocol version

Một client có thể sở hữu:

~~~text
keyId: partner-a-k2 -> secret v2, RETIRING
keyId: partner-a-k3 -> secret v3, ACTIVE
~~~

Mỗi request công bố `keyId`, được HMAC ký cùng các thành phần theo contract. Server tra key record, kiểm tra trạng thái/thuật toán/audience rồi lấy đúng secret. Việc đổi secret **không tự quyết định cách xử lý trailing slash**.

Nếu hệ thống thay đổi canonicalization từ chính sách A sang B hoặc C, nên **version hóa hợp đồng ký** và xác định những key/protocol version nào còn được chấp nhận. Không thử nhiều cách thêm/bỏ slash và nhiều khóa một cách opportunistic đến khi tìm thấy tag đúng.

### 11.3. Authentication không thay authorization

Ví dụ client A ký hợp lệ:

~~~http
DELETE /v1/tenants/tenant-B/orders/42 HTTP/1.1
X-Key-Id: tenant-A-client-k3
X-Timestamp: 1790000000
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <valid-hmac-tag>
~~~

Path không có trailing slash và HMAC có thể đúng. Nhưng principal được gắn với tenant A không tự động có quyền xóa order thuộc tenant B. **Authorization phải kiểm tra principal, action, tenant và resource thực sự được router chọn.**

Ngay cả khi path `/v1/tenants/tenant-B/orders/42/` được normalize thành dạng không slash, việc đó không làm thay đổi quyền của client A.

## 12. Ma trận kiểm thử trailing slash

Bộ kiểm thử cần kiểm tra **cùng một bộ path ở ba điểm**: signer/client, verifier và router/handler sau gateway.

| Ca kiểm thử | Request hoặc tình huống | Kết quả kỳ vọng với NoTrailingSlashV1 |
| --- | --- | --- |
| Root | `GET /` | Path hợp lệ về cú pháp |
| Collection chuẩn | `GET /v1/orders` | Hợp lệ về cú pháp |
| Item chuẩn | `GET /v1/orders/42` | Hợp lệ về cú pháp |
| Slash cuối collection | `GET /v1/orders/` | Từ chối |
| Slash cuối item | `GET /v1/orders/42/` | Từ chối |
| Slash lặp cuối | `GET /v1/orders//` | Từ chối |
| Slash lặp giữa | `GET /v1//orders` | Từ chối |
| Hai slash làm root | `GET //` | Từ chối |
| Path trống | Không có path theo format ứng dụng | Adapter xử lý/từ chối theo contract trước HMAC |
| Dot segment | `/v1/./orders` | Từ chối |
| Parent segment | `/v1/../admin` | Từ chối |
| Encoded slash | `/v1/files/a%2Fb` | Từ chối trong V1 |
| Unicode | `/v1/đơn-hàng` | Từ chối trong V1 |
| Case khác | `/V1/Orders` | Giữ nguyên case; router quyết định route |
| Path dài | Hơn 2.048 byte ASCII | Từ chối trước HMAC |
| Query riêng | `/v1/orders?status=open` | Canonical path hợp lệ là `/v1/orders`; query ký riêng |
| Query có slash cuối | `/v1/orders?next=/done/` | Path không có trailing slash; dấu slash thuộc query value |
| Thay slash sau ký | Ký `/v1/orders`, gửi `/v1/orders/` | Từ chối theo V1; preserve-exact sẽ sai HMAC |
| Thay method | Ký `POST`, gửi `GET` | HMAC sai nếu method được ký |
| Sửa body | Giữ tag, thay raw JSON body | HMAC sai nếu digest body được ký |
| Header signature sai | Dùng tag rỗng hoặc sai Base64URL | Từ chối |
| Timestamp quá cũ | Chữ ký đúng nhưng quá hạn | Từ chối freshness |
| Replay | Hai request cùng nonce | Lần sau bị từ chối |
| Replay đồng thời | Hai node nhận cùng nonce | Tối đa một request qua atomic replay gate |
| Key revoked | Chữ ký đúng với secret cũ đã thu hồi | Từ chối |
| Gateway strip slash | Client gửi `/orders/` nhưng backend nhận `/orders` | Test xác nhận biên đã từ chối dạng không hợp lệ hoặc contract mới có mapping rõ |
| Redirect 301/302 | `POST /orders/` được tự follow | Kiểm tra method/body có bị thay và yêu cầu ký lại request |
| Redirect 307/308 | Redirect giữ method | Dù giữ method, path đích mới vẫn phải được ký đúng |
| Redirect cross-origin | Client tới host khác | Không tự chuyển credential sang origin chưa tin cậy |
| Verifier/router khác nhau | Verifier bỏ slash nhưng router phân biệt | Phải phát hiện và sửa; không chấp nhận hai ý nghĩa dưới một MAC |
| Đúng MAC, sai tenant | Client A gọi tài nguyên tenant B | Authorization từ chối |

### 12.1. Differential tests theo cặp

Nên chạy các cặp:

~~~text
/a/b   vs /a/b/
/a/b   vs /a//b
/      vs //
/a     vs /a/.
/a     vs /a/%2E
/a/b   vs /a%2Fb
/a/b   vs /A/b
~~~

Với V1, những biến thể có slash cuối ngoài root, slash lặp hoặc dấu `%` phải bị từ chối. Với preserve-exact hoặc normalize-equivalent, mỗi cặp cần quy tắc riêng và kiểm chứng **đường đi tới handler cuối cùng**.

### 12.2. Không chỉ unit test canonicalizer

Một test đơn vị Java chỉ thấy chuỗi `rawPath` đã truyền vào. Integration test cần gửi HTTP request qua:

~~~text
Client -> WAF -> Gateway -> HTTP parser -> Verifier -> Router -> Handler
~~~

Tại môi trường kiểm thử có kiểm soát, so sánh **raw request-target**, path sau gateway, canonical bytes tại verifier, handler được chọn và resource ID thực tế. Không log shared secret hoặc dữ liệu nhạy cảm để debug HMAC.

## 13. Tình huống thực tế: tạo đơn hàng và tự động redirect

Một đối tác gọi:

~~~http
POST /partner/orders/ HTTP/1.1
Host: api.example.test
X-Key-Id: partner-a-k3
X-Timestamp: 1790000000
X-Nonce: 6bfb21974a08417199273b09ca49a3ec
X-Signature: <hmac-over-path-with-slash>
Content-Type: application/json

{"orderId":"order-42"}
~~~

Gateway có rule tự redirect sang `/partner/orders`. HTTP client tự follow redirect và **giữ lại chữ ký cũ**.

Khi backend xác minh, chuỗi canonical path là `/partner/orders` trong khi chữ ký đã tính trên `/partner/orders/`: tag không khớp. Nếu client còn thay method theo redirect, canonical method cũng khác.

Cách sửa có hệ thống:

1. Công bố URL chính thức `/partner/orders` trong tài liệu client.
2. Áp dụng NoTrailingSlashV1 tại ranh giới trước khi request bị tự normalize.
3. Client ký **URL sẽ thực sự được gửi**, đồng thời tắt redirect tự động không được kiểm soát đối với signed requests.
4. Nếu hệ thống buộc phải hỗ trợ redirect, client xử lý nó như **request mới**, kiểm tra origin/method/body, tạo timestamp/nonce và ký lại.
5. Backend kiểm tra chống replay, principal, quyền tạo đơn và idempotency của `orderId`.

Không phải lúc nào lỗi signature cũng do secret hoặc thuật toán HMAC sai. Ở tình huống này, lỗi nằm ở **giao thức URL/path giữa client và gateway**.

## 14. Những sai lầm thường gặp

### 14.1. “Slash cuối chỉ là chuyện giao diện URL”

Trong HTTP request signing, slash là một byte của path; nếu nó được ký, thay slash có thể khiến tag thay đổi. **Cần hợp đồng byte rõ ràng.**

### 14.2. “Cứ cắt slash rồi tính HMAC là ổn”

Điều này chỉ đúng nếu server **chủ đích định nghĩa hai path tương đương** và router/authorization cũng xử lý như nhau. Nếu hai path dẫn tới handler khác, chuẩn hóa sẽ tạo nhập nhằng bảo mật.

### 14.3. “Redirect tự động giúp giải quyết canonicalization”

Redirect phát sinh request mới; method, body, authority và URL có thể đổi. Với signed requests, phải kiểm soát re-sign, nonce, idempotency và credential forwarding.

### 14.4. “Gateway đã sửa path nên backend không cần biết”

Nếu backend xác minh HMAC trên path khác client đã ký, chữ ký sai. Nếu gateway xác minh trước rewrite, backend phải tin principal từ một kênh nội bộ bảo vệ và mapping route phải được kiểm thử.

### 14.5. “Đã ký path thì query/body không cần ký”

Nếu query quyết định lọc dữ liệu, tenant hoặc hành động, nó cũng cần nằm trong canonical request. Body digest và các header quan trọng phải được ràng buộc theo hợp đồng.

### 14.6. “HMAC hợp lệ là có quyền thao tác”

HMAC có thể chứng minh bên gọi sở hữu secret, không chứng minh người đó được phép sửa tài nguyên cụ thể. Authorization theo principal/action/resource/tenant là lớp bắt buộc khác.

## 15. Bài tập tự thực hành

1. **Phân loại input.** Với NoTrailingSlashV1, giải thích việc chấp nhận/từ chối `/`, `/a`, `/a/`, `/a//`, `/a/b`, `/a/b/` và `/a?next=/b/`.
2. **Unit test Java.** Viết test cho `NoTrailingSlashPathV1.validate()` bao gồm root, slash lặp, encoded slash, dot segments, Unicode và path quá dài.
3. **Golden canonical request.** Từ request ở mục 7, tính body SHA-256, tạo canonical bytes UTF-8 và HMAC-SHA256. Đổi chỉ một byte path và chứng minh tag cũ không khớp.
4. **Redirect test.** Dùng HTTP client có chế độ tự động follow 301/302/307/308 để so sánh method/body/path cuối cùng và xem khi nào phải ký lại.
5. **Gateway test.** Gửi `/orders` và `/orders/` qua proxy thật, ghi lại raw path, canonical path, route và permission check. Chứng minh verifier/router không hiểu khác nhau.
6. **Authorization.** Với một request có path đúng V1 và HMAC của tenant A hợp lệ nhưng target thuộc tenant B, chỉ rõ vì sao kết quả vẫn phải bị từ chối.

## 16. Checklist triển khai trailing slash

- [ ] Có quyết định rõ: preserve exact, reject trailing slash hay normalize equivalent.
- [ ] Root path `/` được xử lý đúng, không cắt thành path rỗng ngoài ý muốn.
- [ ] Hợp đồng path có version, cách xử lý case/slash lặp/dot segments/percent-encoding được quy định.
- [ ] Canonical path được lấy tại ranh giới HTTP đáng tin, trước rewrite không kiểm soát.
- [ ] HMAC ký path cùng method, query, audience, key ID, timestamp/nonce và header/body quan trọng.
- [ ] Redirect không tự động chuyển chữ ký cũ sang URL khác; xử lý method/body, re-sign và credential forwarding rõ.
- [ ] Gateway và backend có contract rewrite/mapping xác định; không tin `X-Original-URI` từ caller.
- [ ] Verifier và router đồng ý về tài nguyên, handler và quyền khi path có/không slash.
- [ ] Key ID trỏ tới secret đang hiệu lực; key rotation và policy thuật toán do server kiểm soát.
- [ ] Timestamp và nonce được ký; nonce store dùng chung với thao tác nguyên tử và TTL hợp lý.
- [ ] Retry và idempotency xử lý độc lập để không tạo tác động nghiệp vụ lặp.
- [ ] TLS bảo vệ kết nối; không log shared secret hay full signed request nhạy cảm.
- [ ] Authorization xác minh principal, action, resource và tenant sau xác thực.
- [ ] Có differential/integration tests qua proxy và framework thực tế, không chỉ unit test.

## 17. Câu hỏi tự kiểm tra

1. **`/v1/orders` và `/v1/orders/` có mặc nhiên là cùng tài nguyên không?** Không; điều đó do contract và router quyết định.
2. **Slash cuối có thay đổi tag HMAC không?** Có thể, nếu canonical request giữ nguyên path và có ký path.
3. **Vì sao root `/` phải là ngoại lệ khi bỏ slash cuối?** Vì bỏ ký tự duy nhất sẽ tạo path rỗng.
4. **Vì sao không tự chuẩn hóa mọi path thành dạng không slash?** Vì có thể gộp hai route/permission khác nhau thành cùng chữ ký.
5. **Khi client follow redirect, chữ ký cũ có dùng lại được không?** Nếu method/path/body/metadata đã ký thay đổi, phải tạo chữ ký mới phù hợp request mới.
6. **Redirect 307/308 có giải quyết vấn đề chữ ký không?** Không. Chúng giữ method, nhưng path hoặc authority đích vẫn có thể thay đổi.
7. **Vì sao verifier ở backend cần quan tâm rewrite của gateway?** Vì canonical path nhận được có thể khác path client đã ký.
8. **Trailing slash có phải là query không?** Không, trừ khi dấu slash nằm trong giá trị query; path và query là hai thành phần riêng.
9. **HMAC đúng có chống replay không?** Không; cần timestamp, nonce và replay store.
10. **Path đúng contract và HMAC hợp lệ có đủ để xóa dữ liệu tenant khác không?** Không; cần authorization theo principal và resource.

**Kết luận:** Trailing slash là một byte nhỏ nhưng có thể quyết định **nghĩa của HTTP path và dữ liệu được HMAC ký**. Hãy chọn một chính sách rõ ràng, version hóa canonicalization, giữ cho client–gateway–verifier–router thống nhất và kiểm thử redirect/rewrite bằng request thực. Xác thực request còn cần quản lý khóa, chống replay và phân quyền trước khi thực thi nghiệp vụ.

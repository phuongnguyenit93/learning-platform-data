# HEAD request: ngữ nghĩa HTTP và xác thực chữ ký HMAC

> **Chương:** HTTP method  
> **Chủ đề:** HEAD request  
> **Bối cảnh module:** Thiết kế xác thực HTTP request bằng HMAC với shared secret và canonical request chứa phương thức, URI, header hoặc body theo hợp đồng ký. Bài học giải thích cách HEAD khác GET, cách đưa method HEAD vào dữ liệu ký, xác minh chữ ký, timestamp/nonce chống replay, key rotation, kiểm thử qua proxy/gateway và phân biệt authentication với authorization.

## 1. HEAD request là gì?

**HEAD** là một HTTP method yêu cầu server trả về **metadata của tài nguyên như khi xử lý GET**, nhưng **không gửi nội dung (response content/body) trong phản hồi**. Nó hữu ích khi client muốn kiểm tra tài nguyên tồn tại, đọc `ETag` hoặc thời điểm `Last-Modified`, xem loại nội dung, hoặc ước lượng kích thước tải về mà không thực sự tải body.

Ví dụ:

~~~http
HEAD /v1/reports/report-42 HTTP/1.1
Host: api.example.test
Accept: application/pdf
~~~

Server có thể phản hồi:

~~~http
HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Length: 184320
ETag: "report-42-v3"
Last-Modified: Wed, 25 Nov 2026 08:00:00 GMT

~~~

**Quan trọng:** ví dụ trên không có response body. `Content-Length: 184320` ở **HEAD response** biểu thị số byte nội dung mà server *sẽ gửi* nếu xử lý request `GET` tương ứng trong điều kiện phù hợp, **không** phải số byte thực sự truyền trong HEAD response. Server cũng có thể bỏ header này.

Theo HTTP Semantics, HEAD giống GET về ngữ nghĩa truy xuất thông tin, ngoại trừ server **không được sinh response content**. Các header phản hồi thường tương tự GET, nhưng server có thể lược bỏ những trường chỉ xác định được khi thực sự sinh content. Vì thế, không viết test cứng rằng *mọi* response header của HEAD luôn phải trùng từng byte với GET.

### Vì sao HEAD liên quan đến HMAC?

Trong xác thực HTTP bằng **HMAC request signature**, bên gửi ký một **canonical request**, ví dụ:

~~~text
hmac-v1
HEAD
/v1/reports/report-42
...
~~~

Nếu attacker đổi method từ `HEAD` thành `GET` hoặc ngược lại sau khi ký, **chữ ký phải không còn hợp lệ** khi hợp đồng ký bao gồm method. Dù HEAD và GET cùng truy xuất một tài nguyên, chúng **không phải cùng thông điệp được ký**. HEAD không trả body, GET có thể trả tài liệu có dữ liệu nhạy cảm; nhầm lẫn method có thể thay đổi lượng dữ liệu được tiết lộ.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích ngữ nghĩa HEAD, quan hệ với GET, đặc điểm response body và `Content-Length`.
2. Phân biệt **HEAD request body**, **HEAD response body** và **body digest của canonical request**.
3. Xây hợp đồng ký cố định method `HEAD`, path/query, header, timestamp/nonce và body digest.
4. Viết ví dụ Java 17 ký/xác minh HMAC-SHA-256 cho HEAD, thử sai method, URI và body.
5. Thiết kế kiểm thử receiver/gateway khi framework tự ánh xạ HEAD vào GET handler.
6. Áp dụng kiểm tra key rotation, anti-replay và authorization nhất quán với các method khác.

## 2. HEAD và GET: giống gì, khác gì?

| Thuộc tính | GET | HEAD |
|---|---|---|
| Mục tiêu | Lấy representation của tài nguyên | Lấy metadata tương ứng, không tải response content |
| Response body của phản hồi thành công thông thường | Có thể có body | **Không có body** |
| `Content-Type` ở response | Mô tả representation khi có | Có thể mô tả representation của GET tương ứng |
| `Content-Length` ở response | Thường là độ dài response content thực tế (khi có trường) | Nếu được gửi, phản ánh số byte **sẽ** có trong nội dung của GET tương ứng |
| `ETag`, `Last-Modified` | Hữu ích cho cache/conditional request | Cũng hữu ích, nếu server cung cấp |
| HTTP method có tính safe | Có | Có |
| HTTP method có tính idempotent | Có | Có |
| HMAC canonical method | Literal `GET` | Literal **`HEAD`** |
| Có cần authentication/authorization? | Tùy độ nhạy endpoint | **Vẫn cần** khi metadata có thể nhạy cảm |

**Safe method** là method mà client không yêu cầu server thay đổi trạng thái như một mục tiêu nghiệp vụ; hệ thống vẫn có thể ghi log, cập nhật số liệu truy cập hoặc tạo cache. **Idempotent** mô tả hiệu quả dự kiến của nhiều request giống nhau trên trạng thái server, không có nghĩa request không tốn tài nguyên hoặc không cần bảo vệ.

Các gateway, crawler, cache và hệ thống monitoring có thể phát sinh HEAD thường xuyên. Việc coi HEAD là “không đọc dữ liệu gì nên luôn công khai” là sai: chỉ từ status code, header metadata, ETag, Content-Length hoặc thời gian phản hồi, người gọi có thể suy ra tài nguyên tồn tại hay đặc điểm của một tài nguyên riêng tư.

### 2.1. HEAD response không có body, nhưng vẫn có header mô tả tài nguyên

Hai request:

~~~http
GET /v1/reports/report-42 HTTP/1.1
Host: api.example.test
~~~

~~~http
HEAD /v1/reports/report-42 HTTP/1.1
Host: api.example.test
~~~

có thể dẫn tới hai phản hồi:

~~~text
GET:  200 OK + Content-Type: application/pdf
      + Content-Length: 184320 + 184320 byte PDF

HEAD: 200 OK + Content-Type: application/pdf
      + Content-Length: 184320 + KHÔNG có body
~~~

Khi test tích hợp, **không đọc nhầm 184320 byte từ socket của HEAD chỉ vì có Content-Length 184320**. HTTP client/parser phải hiểu quy tắc của HEAD: kết thúc response được xác định theo ngữ nghĩa HEAD, không phải bằng việc chờ đủ số byte theo Content-Length của GET.

Một HEAD response cũng có thể mang status khác 200 (ví dụ 401, 403, 404, 405, 503). Những response đó vẫn không được chứa body theo ngữ nghĩa HEAD. Không giả định mọi HEAD request đều thành công hoặc luôn có ETag.

### 2.2. HEAD request có được gửi body không?

**HEAD request content không có ngữ nghĩa chung được định nghĩa** trong HTTP. Client thông thường **không nên tạo body cho HEAD**; request có content còn có thể bị một số implementation từ chối vì nguy cơ xử lý/framing không nhất quán.

Để giảm mơ hồ, **hợp đồng HMAC minh họa của bài yêu cầu HEAD có request body rỗng**:

- Không gửi request body; nếu có framing với `Content-Length: 0` thì body vẫn là mảng 0 byte.
- Receiver từ chối HEAD có request content khác rỗng; gateway/parser phải nhận diện chính xác framing và giới hạn request size.
- Không tự lấy body của **GET response** để dùng làm **HEAD request body digest**. Đây là hai hướng dữ liệu khác nhau.
- Nếu một giao thức đặc thù thực sự sử dụng HEAD có content, phải có signing contract riêng, mô tả byte content và sự tương thích của mọi intermediary.

Đừng nhầm tính “không có **response** body” của HEAD với việc `SHA-256` của **request** body không cần tính. Theo contract bài này, digest của **request body rỗng** vẫn là một giá trị SHA-256 xác định.

## 3. Cách biểu diễn HTTP HEAD request trong các phiên bản giao thức

### 3.1. HTTP/1.1

Một request thông thường:

~~~http
HEAD /v1/reports/report-42?format=pdf HTTP/1.1
Host: api.example.test
X-Client-Id: partner-17
~~~

Phân tách:

~~~text
Method:           HEAD
Raw path:         /v1/reports/report-42
Raw query:        format=pdf
Request target:   /v1/reports/report-42?format=pdf
Host:             api.example.test
~~~

### 3.2. HTTP/2 và HTTP/3

Ở HTTP/2/3, thông tin tương đương thường được truyền qua pseudo-header:

~~~text
:method    = HEAD
:scheme    = https
:authority = api.example.test
:path      = /v1/reports/report-42?format=pdf
~~~

Khi proxy chuyển HTTP/2 sang HTTP/1.1, framework có thể nhận request đã được chuyển đổi. Nếu hợp đồng ký **raw target**, phải chắc rằng đường dẫn/query tại **điểm kiểm tra HMAC** được xác định đúng. `:path`, `Host`, prefix route hoặc path đã percent-decode không thể được thay thế cho nhau tùy tiện.

### 3.3. Tại sao cần ký cả method và target?

Hãy xét hai request:

~~~text
HEAD /v1/reports/report-42?format=pdf
GET  /v1/reports/report-42?format=pdf
~~~

Ngay cả khi cùng path/query và cùng body rỗng ở phía request, **method khác nhau phải tạo canonical bytes khác nhau**. Nếu server bỏ method khỏi HMAC, attacker có thể phát lại tag của HEAD cho GET; một endpoint trả file có thể tiết lộ nội dung thay vì chỉ metadata.

Tương tự, nếu chỉ ký method mà bỏ path/query, người gọi có thể đổi `report-42` thành `report-99` hoặc tham số `format=pdf` thành giá trị khác mà MAC vẫn khớp. Hợp đồng cần ràng buộc mọi thành phần có ảnh hưởng đến quyết định xử lý.

## 4. Hợp đồng ký minh họa cho HEAD: hmac-head-v1

Bài này dùng một hợp đồng **minh họa do ứng dụng tự định nghĩa**. Đây không phải định dạng bắt buộc của mọi HMAC API, cũng không tự nhận triển khai RFC 9421.

### 4.1. Thành phần và quy tắc

| Dòng canonical | Giá trị | Quy tắc |
|---|---|---|
| 1 | `hmac-head-v1` | Version literal, phân biệt hợp đồng |
| 2 | `HEAD` | Method chữ hoa **chính xác**, không đổi sang GET khi ký |
| 3 | Raw origin-form target | Encoded path + raw query, ví dụ `/v1/reports/report-42?format=pdf` |
| 4 | `Content-Type` của **request** | HEAD trong contract không có request content: biểu diễn bằng **chuỗi rỗng** |
| 5 | `X-Client-Id` | Client ID đã được cấp, được đưa vào chữ ký |
| 6 | `X-Key-Id` | Phiên bản secret được cấp cho client, được ký |
| 7 | `X-Timestamp` | Unix epoch **seconds** dạng thập phân canonical |
| 8 | `X-Nonce` | Base64URL không padding của 16–32 byte CSPRNG |
| 9 | Body digest | Hex chữ thường SHA-256 của **0 byte request content** |

Các dòng nối bằng LF (`\n`), **không có LF cuối**. Chuỗi canonical được chuyển sang **UTF-8 bytes**. Secret là **32 byte ngẫu nhiên** được cấp riêng cho client/audience trong ví dụ. Chữ ký là **HMAC-SHA-256 đầy đủ 32 byte**, encode Base64URL không padding, gửi trong header `X-Signature` (không đưa chính chữ ký vào dữ liệu ký).

Với HEAD không có request content, SHA-256 của 0 byte là:

~~~text
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

Đó là **SHA-256 digest**; không phải HMAC, không phải tag của HEAD response và **không phải SHA-256 của nội dung file PDF** mà GET có thể trả về.

### 4.2. Ví dụ request có ký

~~~http
HEAD /v1/reports/report-42?format=pdf HTTP/1.1
Host: api.example.test
X-Client-Id: partner-17
X-Key-Id: key-2026-11
X-Timestamp: 1795824000
X-Nonce: b75sZVQmhTBcfnX-bNbGqw
X-Signature: <base64url-hmac-sha256>

~~~

Canonical string gồm **9 dòng**; dòng thứ tư dành cho request Content-Type nên **rỗng**:

~~~text
hmac-head-v1
HEAD
/v1/reports/report-42?format=pdf

partner-17
key-2026-11
1795824000
b75sZVQmhTBcfnX-bNbGqw
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
~~~

Không có LF sau dòng cuối. Chuỗi `<base64url-hmac-sha256>` chỉ là chỗ giữ chỗ, không phải signature thật. Key ID là định danh không bí mật để lookup server-side; **shared secret không được truyền trong request**.

### 4.3. Raw target và authority

Trong ví dụ, raw target được ký **nguyên dạng**, bao gồm cả path và query. Hợp đồng không tự sắp xếp query hay decode/encode lại path:

~~~text
/v1/reports/report-42?format=pdf&lang=vi
/v1/reports/report-42?lang=vi&format=pdf
~~~

Hai chuỗi trên **khác byte** và tạo hai HMAC khác nhau theo hợp đồng raw target, dù ứng dụng có thể hiểu chúng tương đương. Nếu muốn ký canonical query đã sort, phải định nghĩa **một hợp đồng khác** và bảo đảm sender/receiver/router đồng ý.

Ví dụ cũng không ký `Host`. Để tránh dùng một request hợp lệ ở dịch vụ khác, **key store phải ràng buộc client và key ID với audience/host/môi trường tin cậy**. Nếu cùng secret được dùng cho nhiều audience, nên tách secret hoặc đưa authority/audience đáng tin vào signing contract.

## 5. Thiết kế request receiver cho HEAD

### 5.1. Luồng xác minh

~~~mermaid
sequenceDiagram
    participant S as HTTP Sender
    participant G as Proxy / Gateway
    participant V as HMAC Verifier
    participant K as Key Store
    participant N as Shared Nonce Store
    participant A as Authorization
    participant R as HEAD Handler
    S->>S: Tạo timestamp, nonce, canonical HEAD request
    S->>S: HMAC-SHA-256(shared secret, canonical bytes)
    S->>G: HEAD request + signed headers
    G->>V: Method HEAD và target theo contract
    V->>V: Validate method, target, headers, framing, body rỗng
    V->>K: Lookup clientId + keyId + audience
    K-->>V: Secret hợp lệ để VERIFY
    V->>V: Kiểm tra timestamp, tái tạo canonical bytes
    V->>V: Tính HMAC, so sánh tag
    V->>N: Reserve nonce atomically + TTL
    N-->>V: Mới / đã dùng
    V->>A: Authenticated principal
    A->>A: Quyền đọc metadata tài nguyên
    A->>R: Cho phép xử lý HEAD
    R-->>S: Status + headers, không có response body
~~~

Các bước có thể khác thứ tự ở phần kiểm tra đầu vào nhưng đều cần hoàn thành **trước khi cấp quyền cho HEAD handler**.

### 5.2. Kiểm tra cú pháp và framing

Receiver cần:

1. Nhận đúng method `HEAD` tại điểm xác minh. Không tự “chuẩn hóa” thành `GET` trước khi tạo canonical string.
2. Từ chối request có nhiều giá trị ở signed headers; không chọn ngẫu nhiên first/last.
3. Kiểm tra request target giới hạn độ dài, percent-encoding, dấu `#`, path prefix, dot-segment và query theo signing contract.
4. **Bảo đảm request content rỗng** theo contract; từ chối framing body không nhất quán, ví dụ body thực có byte dù client tuyên bố HEAD.
5. Kiểm tra client ID, key ID, timestamp, nonce và signature đúng format, giới hạn độ dài trước khi decode.
6. Không tin `X-Original-URI` hoặc `X-HTTP-Method-Override` do client tự đưa vào để quyết định dữ liệu ký.

Một số hệ thống hỗ trợ method override qua `X-HTTP-Method-Override` hoặc tham số `_method`. **Không cho phép một request được verify như HEAD nhưng được thực thi như GET, POST hay DELETE** thông qua cơ chế override ở tầng sau. Nếu hỗ trợ override, signing contract phải bảo vệ đúng **effective method** và toàn bộ đường biến đổi; với API nhạy cảm, thường nên tắt override trên các route ký HMAC.

### 5.3. Key lookup và rotation

Receiver tra secret theo `(clientId, keyId, audience)` rồi kiểm tra thuật toán, thời gian và trạng thái:

| Trạng thái | Ý nghĩa | Kết quả |
|---|---|---|
| `ACTIVE` | Khóa đang có hiệu lực verify | Có thể xác thực |
| `VERIFY_ONLY` | Khóa cũ trong cửa sổ chuyển tiếp được phê duyệt | Verify trước deadline, từ chối sau đó |
| `REVOKED` | Khóa bị thu hồi | Từ chối dù HMAC đúng |
| Key không thuộc client/audience | Bản ghi không hợp lệ cho request | Từ chối; không thử khóa của tenant khác |
| Key không tồn tại | Không có secret được cấp | Từ chối; không fallback sang secret mặc định |

Khi rotate, phía sender chuyển sang ký HEAD bằng key ID mới, receiver có thể tạm verify key cũ trong cửa sổ overlap ngắn rồi revoke. Key mới nên độc lập và đủ entropy, ví dụ 32 byte CSPRNG; không tự derive secret từ tên client hoặc timestamp.

### 5.4. Timestamp và nonce chống replay

HEAD có ngữ nghĩa safe nhưng **vẫn có thể cần chống replay** theo chính sách API. Một HEAD hợp lệ có thể bị phát lại để dò metadata, tăng tải, vượt giới hạn request hoặc gây tác động vận hành; HMAC một mình không phân biệt bản gốc với bản sao.

Ví dụ cửa sổ thời gian:

~~~text
nowSeconds - 300 <= signedTimestamp <= nowSeconds + 300
nonceKey = namespace(clientId, keyId, audience, nonce)
reserve nonce atomically bằng insert-if-absent có TTL
~~~

Với cửa sổ ±5 phút, TTL khoảng 10 phút kể từ khi nonce được nhận lần đầu là một mức minh họa cần kiểm tra theo độ lệch đồng hồ thực tế. Nhiều verifier node phải dùng **kho nonce chia sẻ** với thao tác nguyên tử, chẳng hạn primitive tương đương `SET key 1 NX EX 600` trong Redis.

**Chỉ reserve nonce sau khi MAC đã xác minh đúng**; nếu reserve trước, attacker gửi MAC giả có thể chiếm nonce của một request thật. Nếu nonce store hỏng và anti-replay là yêu cầu bắt buộc, receiver phải **fail closed**, thay vì lặng lẽ xử lý HEAD như request đã xác thực.

### 5.5. Authentication khác authorization đối với HEAD

MAC hợp lệ cho biết người gọi có quyền sử dụng **secret gắn với principal**, không cho biết principal có quyền xem metadata của tài nguyên:

~~~text
authentication:
    principal = partner-17
    signedMethod = HEAD
    signedTarget = /v1/reports/report-42
    hmac = valid

authorization:
    action = reports:metadata:read
    resource = report-42
    resource.owner = partner-42
    principal = partner-17
    decision = DENY
~~~

Thông tin như “tài liệu này có tồn tại không”, kích thước, `ETag`, `Last-Modified` hoặc mã phản hồi `403/404` cũng có thể nhạy cảm. Tầng phân quyền phải kiểm tra **chủ sở hữu, tenant và policy** trước khi trả thông tin. Không “cho phép tất cả HEAD để monitoring hoạt động” trên API có tài nguyên riêng tư.

## 6. Ví dụ Java 17: ký và xác minh HEAD HMAC

Chương trình sau minh họa phần **canonical bytes và MAC** với JDK 17+. Nó cố định method `HEAD`, request body rỗng và raw target dạng đơn giản để tránh lỗi diễn giải. Chương trình cố ý không triển khai HTTP server, key store hay nonce store; các phần đó nằm ở receiver production.

### 6.1. Mã Java hoàn chỉnh

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HeadHmacDemo {
    private HeadHmacDemo() {}

    private static final String ALGORITHM = "HmacSHA256";
    private static final String CONTRACT = "hmac-head-v1";
    private static final String EMPTY_BODY_SHA256 =
            "e3b0c44298fc1c149afbf4c8996fb924"
          + "27ae41e4649b934ca495991b7852b855";

    public record Request(
            String method,
            String rawTarget,
            String clientId,
            String keyId,
            String timestamp,
            String nonce,
            byte[] rawBody) {}

    private static String line(String value, int maxLength) {
        if (value == null || value.isEmpty()
                || value.length() > maxLength
                || value.chars().anyMatch(c -> c < 0x20 || c == 0x7f)) {
            throw new IllegalArgumentException("Invalid signed field");
        }
        return value;
    }

    public static byte[] canonicalBytes(Request request)
            throws GeneralSecurityException {
        if (request == null || request.rawBody() == null) {
            throw new IllegalArgumentException("Missing request body");
        }
        if (!"HEAD".equals(request.method())
                && !"GET".equals(request.method())) {
            throw new IllegalArgumentException("Unsupported method");
        }
        if (request.rawBody().length != 0) {
            throw new IllegalArgumentException(
                    "This demo signs requests with empty body only");
        }
        // Grammar minh họa: không percent-encode path hoặc query.
        // Query được ký theo raw order, không sort.
        if (!line(request.rawTarget(), 2048).matches(
                "/v1/reports(?:/[A-Za-z0-9_-]{1,64})?"
              + "(?:\\?[A-Za-z0-9_=&.-]{1,256})?")) {
            throw new IllegalArgumentException("Target outside contract");
        }
        String clientId = line(request.clientId(), 64);
        String keyId = line(request.keyId(), 64);
        String timestamp = line(request.timestamp(), 20);
        String nonce = line(request.nonce(), 64);
        if (!clientId.matches("[A-Za-z0-9_-]+")
                || !keyId.matches("[A-Za-z0-9_-]+")
                || !timestamp.matches("[1-9][0-9]{0,18}")) {
            throw new IllegalArgumentException("Bad identity or timestamp");
        }
        byte[] decodedNonce;
        try {
            decodedNonce = Base64.getUrlDecoder().decode(nonce);
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException("Bad nonce", ex);
        }
        if (decodedNonce.length < 16 || decodedNonce.length > 32
                || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(decodedNonce).equals(nonce)) {
            throw new IllegalArgumentException("Bad nonce encoding");
        }
        String bodyHash = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256")
                        .digest(request.rawBody()));
        if (!EMPTY_BODY_SHA256.equals(bodyHash)) {
            throw new AssertionError("Empty-body digest mismatch");
        }
        String canonical = String.join("\n",
                CONTRACT,
                request.method(),
                request.rawTarget(),
                "", // HEAD/GET request không có Content-Type trong ví dụ.
                clientId,
                keyId,
                timestamp,
                nonce,
                bodyHash);
        return canonical.getBytes(StandardCharsets.UTF_8);
    }

    public static byte[] hmac(byte[] secret, byte[] data)
            throws GeneralSecurityException {
        if (secret == null || secret.length != 32 || data == null) {
            throw new IllegalArgumentException("Invalid secret/message");
        }
        Mac mac = Mac.getInstance(ALGORITHM);
        mac.init(new SecretKeySpec(secret, ALGORITHM));
        return mac.doFinal(data);
    }

    public static String sign(Request request, byte[] secret)
            throws GeneralSecurityException {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(
                hmac(secret, canonicalBytes(request)));
    }

    public static boolean verifyHead(
            Request request, byte[] secret, String signature)
            throws GeneralSecurityException {
        // Không để chữ ký của GET đi qua tuyến HEAD.
        if (request == null || !"HEAD".equals(request.method())
                || signature == null || signature.length() != 43) {
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
        byte[] expected = hmac(secret, canonicalBytes(request));
        return MessageDigest.isEqual(expected, received);
    }

    private static void require(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }

    public static void main(String[] args)
            throws GeneralSecurityException {
        byte[] secret = new byte[32];
        new SecureRandom().nextBytes(secret); // Key test only.
        byte[] nonceBytes = new byte[16];
        new SecureRandom().nextBytes(nonceBytes);
        String nonce = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(nonceBytes);

        Request head = new Request(
                "HEAD", "/v1/reports/report-42?format=pdf",
                "partner-17", "key-2026-11",
                Long.toString(Instant.now().getEpochSecond()),
                nonce, new byte[0]);

        String signature = sign(head, secret);
        require(verifyHead(head, secret, signature), "HEAD must pass");

        Request changedPath = new Request(
                "HEAD", "/v1/reports/report-99?format=pdf",
                head.clientId(), head.keyId(), head.timestamp(),
                head.nonce(), head.rawBody());
        require(!verifyHead(changedPath, secret, signature),
                "Path change must fail");

        Request changedQuery = new Request(
                "HEAD", "/v1/reports/report-42?format=csv",
                head.clientId(), head.keyId(), head.timestamp(),
                head.nonce(), head.rawBody());
        require(!verifyHead(changedQuery, secret, signature),
                "Query change must fail");

        Request get = new Request(
                "GET", head.rawTarget(), head.clientId(), head.keyId(),
                head.timestamp(), head.nonce(), head.rawBody());
        require(!sign(get, secret).equals(signature),
                "HEAD and GET must have different signatures");
        require(!verifyHead(get, secret, signature),
                "GET must not pass HEAD verifier");

        Request withContent = new Request(
                "HEAD", head.rawTarget(), head.clientId(), head.keyId(),
                head.timestamp(), head.nonce(), new byte[] {1});
        try {
            sign(withContent, secret);
            throw new AssertionError("HEAD body must be rejected");
        } catch (IllegalArgumentException expected) {
            // Pass: contract cấm request content trên HEAD.
        }
        System.out.println("PASS HEAD HMAC method/target/body checks");
    }
}
~~~

Lưu mã thành `HeadHmacDemo.java` rồi chạy với JDK 17+:

~~~bash
javac HeadHmacDemo.java
java HeadHmacDemo
~~~

Kết quả mong đợi:

~~~text
PASS HEAD HMAC method/target/body checks
~~~

### 6.2. Cách đọc code và các giới hạn

Chương trình test hai điều khác nhau:

- **Method binding:** cùng target, secret, nonce, timestamp và request body rỗng nhưng method `HEAD` khác `GET`, nên hai chữ ký HMAC không giống nhau. `verifyHead` chỉ chấp nhận method HEAD.
- **Target binding:** thay path hoặc query mà giữ chữ ký gốc khiến MAC không khớp.

Các kiểm tra định dạng trong code là **quy định đơn giản của ví dụ**, không phải parser HTTP tổng quát. Nó cho phép một số giá trị query đơn giản nhưng chưa có parser nghiệp vụ, chưa kiểm soát duplicate keys và chưa xác minh audience, timestamp/nonce thực sự hợp lệ hoặc mới. Body byte array cũng có thể bị sửa nếu caller giữ tham chiếu; adapter cần giữ immutable snapshot đúng thời điểm.

Đoạn code dùng `String.equals` khi so **biểu diễn Base64URL canonical** của signature và khi kiểm tra tag tạo ở test có khác hay không; để **đối chiếu HMAC thật**, nó dùng `MessageDigest.isEqual(expected, received)` sau khi xác minh tag đúng 32 byte.

**Không dùng `verifyHead` này làm middleware production nguyên trạng.** Trước khi gọi nó, receiver cần tra đúng khóa từ key store, kiểm tra trạng thái/key rotation, giới hạn signed headers và raw target/body, kiểm tra timestamp trong cửa sổ, ghi nonce atomically và sau đó chạy authorization. `main` tạo secret ngẫu nhiên tại runtime để demo, còn hệ thống thật phải nhận shared secret qua kênh cấp phát an toàn.

## 7. Framework và gateway có thể biến đổi HEAD như thế nào?

### 7.1. Một số framework tự ánh xạ HEAD sang GET handler

Ở nhiều web framework, GET route có thể tự động hỗ trợ HEAD. Chẳng hạn Spring MVC có thể xử lý HEAD dựa trên mapping GET và bảo đảm phần response content không được gửi. Việc tái sử dụng **handler** không có nghĩa chữ ký cần được kiểm tra bằng method GET.

Một luồng đúng:

~~~text
Client gửi:       HEAD /v1/reports/report-42
HMAC verifier:    ký/verify literal "HEAD"
Framework router: có thể chọn handler dùng chung cho GET/HEAD
Authorization:   kiểm tra quyền xem metadata report-42
Response:        headers, không có body
~~~

Một luồng nguy hiểm:

~~~text
Client gửi:       HEAD /v1/reports/report-42
Gateway:          rewrite effective method thành GET
Verifier:         dùng "GET" để tạo canonical string
Policy:           bỏ qua method HEAD gốc
~~~

Nếu các tầng dùng khác method cho xác thực, định tuyến và phân quyền, signature có thể không phản ánh hành động thực tế được thực thi. **Chốt rõ điểm lấy method** và tắt method override nếu không có hợp đồng hỗ trợ.

### 7.2. Proxy có thể thay đổi target, header và body

| Tác động tại gateway/proxy | Rủi ro cho HEAD-HMAC | Hướng khắc phục |
|---|---|---|
| Thêm/bỏ prefix path `/public` | Canonical target khác | Verify trước rewrite hoặc dùng original target từ proxy đáng tin |
| Đổi thứ tự query/percent-encoding | Raw target signature khác | Test và áp dụng đúng signing contract |
| Chuyển HTTP/2 sang HTTP/1.1 | Method/`:path`/authority có thể được ánh xạ lại | Test tại điểm HMAC verifier thực tế |
| Tự xử lý HEAD và không forward backend | Bỏ qua authentication/authorization ở backend | Gateway phải tự verify/policy tương đương hoặc forward đúng tuyến |
| Thêm `X-HTTP-Method-Override` | Effective method khác method đã ký | Từ chối override hoặc bảo vệ bằng contract riêng |
| Cache phục vụ HEAD từ metadata GET | Có thể tiết lộ metadata mà backend không kiểm tra quyền cho request hiện tại | Cấu hình cache partition, auth và `Cache-Control` phù hợp |
| Đọc/gom header `Content-Length` không đúng | Nhầm độ dài request với metadata của HEAD response | Phân biệt framing ở từng chiều, test HTTP parser |
| Gateway làm mất signed headers | Receiver không có dữ liệu ký ban đầu | Chuẩn hóa cách chuyển header và xác định vị trí verify |

**Tình huống đặc biệt:** CDN hoặc gateway có thể trực tiếp trả HEAD từ cache hoặc biến HEAD thành truy vấn metadata nội bộ. Nếu ký HMAC ở backend nhưng request không đến backend, **backend sẽ không xác thực request đó**. Cần cấu hình chính sách tại edge sao cho dữ liệu riêng tư không bị lộ qua cache hoặc response headers trước khi authentication hoàn tất.

Không tin `X-Original-URI`, `X-Forwarded-*` hoặc thông tin “client đã xác thực” từ request internet. Proxy đáng tin phải **xóa các header giả mạo do client gửi**, gắn metadata nội bộ mới và bảo vệ kênh proxy → backend, ví dụ bằng authentication nội bộ/mTLS khi phù hợp.

### 7.3. Tương tác với cache

HEAD có thể liên quan đến việc xác minh hoặc cập nhật metadata cache của GET. Tuy nhiên:

- Không dùng kết quả HEAD public để suy ra metadata private của người dùng khác.
- Phân tách cache theo authorization/tenant nếu có dữ liệu cá nhân, hoặc đặt `Cache-Control: private, no-store` phù hợp với chính sách.
- Không dùng chỉ `method + path` làm cache key nếu query/authority và thông tin phân quyền ảnh hưởng representation.
- Không cho cache replay một HEAD response nhạy cảm cho principal khác mà bỏ qua HMAC/authentication.
- Kiểm thử cả hai đường: **cache hit tại edge** và **cache miss đến origin**.

Caching của HEAD không thay thế chính sách authorization hoặc nonce của hợp đồng HMAC.

## 8. Thiết kế kiểm thử HEAD ở nhiều lớp

### 8.1. Unit test ngữ nghĩa method và chữ ký

| Test case | Input/thao tác | Kỳ vọng |
|---|---|---|
| HEAD hợp lệ | Method HEAD, target đúng, key ACTIVE, body rỗng | HMAC đúng |
| Đổi method | Cùng canonical fields, thay HEAD → GET, giữ tag cũ | Xác thực HEAD thất bại |
| Đổi path | `report-42` → `report-99` | MAC không khớp |
| Đổi query | `format=pdf` → `format=csv` | MAC không khớp |
| Đổi client/key ID | Giữ tag, thay signed identity | Không lookup được khóa phù hợp hoặc MAC fail |
| Body có nội dung | HEAD mang request content khác rỗng | Reject theo hợp đồng minh họa |
| Body rỗng | SHA-256 của 0 byte | Khớp digest đã biết |
| Signature sai Base64URL | Sai encoding, thiếu byte, padding không được phép | Reject |
| Content-Type do proxy tự chèn | Request header không khớp quy tắc HEAD | Reject hoặc xử lý theo contract đã đặc tả |
| Signed header lặp | Hai `X-Client-Id` hoặc `X-Signature` | Reject đầu vào mơ hồ |

### 8.2. Integration test response HEAD so với GET

| Test | Điều cần khẳng định |
|---|---|
| HEAD thành công | Response **không có body** |
| HEAD có `Content-Length` | Nếu hiện diện, bằng độ dài nội dung GET tương ứng trong điều kiện so sánh phù hợp; **không** phải số byte body HEAD |
| HEAD có `Content-Type` và `ETag` | Phù hợp metadata tài nguyên nếu được server cung cấp |
| HEAD đến tài nguyên không tồn tại | Status theo ứng dụng, response vẫn không có content |
| HEAD thiếu authentication | Response không lộ metadata riêng tư |
| HEAD đúng HMAC nhưng thiếu authorization | Từ chối tương tự chính sách đọc tài nguyên; không tiết lộ body |
| HEAD đi qua HTTP/2 gateway | Method HEAD và signed target được giữ/diễn giải đúng |
| HEAD xử lý bằng GET handler | HMAC vẫn kiểm tra **HEAD**, handler không gửi content |
| HEAD từ CDN cache hit | Không bỏ qua auth hoặc phân tách cache theo principal phù hợp |
| HEAD được forward đến origin | Header/target tới verifier còn đúng hợp đồng |

**Lưu ý:** Một HEAD có thể thành công nhưng không gửi một số metadata GET khi việc sinh metadata đòi hỏi tạo content; vì vậy nên kiểm tra header bắt buộc theo **hợp đồng API** thay vì buộc tất cả header luôn giống GET từng byte.

### 8.3. Test HTTP framing và method confusion

Các biến thể cần chạy qua **cấu hình gateway/container thực**:

~~~text
HEAD /v1/reports/report-42
GET  /v1/reports/report-42
HEAD /v1/reports/report-42?format=pdf
HEAD /v1/reports/report-42?format=csv
HEAD /external/v1/reports/report-42 (gateway rewrite prefix)
HEAD với Content-Length: 0
HEAD với request body thực có nội dung
HEAD với signed headers bị trùng
HEAD với X-HTTP-Method-Override: GET
~~~

Mục tiêu không chỉ là assert HTTP status, mà phải chứng minh:

1. **HMAC verifier dùng method/target nào?**
2. **Router thực sự gọi handler nào?**
3. **Authorization đánh giá quyền gì?**
4. **Có body nào được gửi trong response HEAD không?**
5. **Cache/gateway có đường bỏ qua xác thực hoặc trả metadata không đúng principal không?**

Nếu GET handler nội bộ tạo file PDF rồi framework chỉ bỏ body ở phút cuối, HEAD vẫn có thể gây chi phí CPU/I/O đáng kể. Điều này không phải lỗi HMAC, nhưng là lý do cần **rate limiting**, chống abuse và endpoint tối ưu metadata nếu hệ thống sử dụng HEAD nhiều.

### 8.4. Test replay và key rotation

| Tình huống | Kỳ vọng |
|---|---|
| HEAD HMAC đúng, timestamp trong cửa sổ, nonce mới | Có thể tạo authenticated principal |
| Replay nguyên HEAD request | Nonce đã dùng, reject theo contract |
| Hai node nhận cùng nonce gần đồng thời | Tối đa một `reserve` atomically thành công |
| Timestamp cũ hơn `now - 300` | Reject |
| Timestamp mới hơn `now + 300` | Reject |
| Nonce store mất kết nối | Fail closed |
| HMAC đúng với key ACTIVE | Có thể verify |
| HMAC đúng với key VERIFY_ONLY đã quá hạn | Reject |
| HMAC đúng với key REVOKED | Reject |
| HEAD HMAC đúng với client A nhưng resource của client B | Authentication có thể pass; authorization phải deny |

Để test timestamp chính xác, dùng clock được tiêm vào thay vì `Thread.sleep`. Để kiểm tra race giữa node, dùng nonce store chia sẻ có thao tác atomic; unit test dùng `HashSet` trong một instance **không chứng minh** khả năng chống replay toàn hệ thống.

## 9. Những hiểu lầm và lỗi triển khai phổ biến

### 9.1. “HEAD không có body nên không cần chữ ký”

Sai. HEAD vẫn mang method, path, query và metadata nhận dạng tài nguyên. Nếu chỉ kiểm tra token chung hoặc bỏ HMAC, request có thể bị dùng để xác định tài nguyên bí mật tồn tại. Một endpoint private phải có authorization phù hợp ngay cả khi response content rỗng.

### 9.2. “HEAD response Content-Length phải bằng 0”

Sai. `Content-Length` trong **HEAD response** (nếu có) mô tả số byte **sẽ được gửi bởi GET tương ứng**, không phải response content thực tế của HEAD. Không dùng giá trị đó làm **request body digest**.

### 9.3. “HEAD có thể dùng chữ ký GET vì cùng URL”

Sai nếu method được ký đúng. `HEAD` và `GET` khác canonical bytes. Phép biến đổi method sau xác thực có thể cho phép truy xuất sai cấp độ hoặc làm verifier và handler hiểu khác hành động.

### 9.4. “HEAD không thay đổi trạng thái nên không cần nonce”

Không nhất thiết. HMAC chỉ chứng minh toàn vẹn/xác thực trong phạm vi secret; replay cũ có thể làm lộ metadata, gây tải hoặc phá vỡ chính sách chống replay của API. Tùy threat model, hệ thống có thể yêu cầu timestamp/nonce thống nhất cho mọi method. Nếu hợp đồng đã yêu cầu, **không tự bỏ qua đối với HEAD**.

### 9.5. “GET được phép thì HEAD mặc định cũng được”

Không phải quy tắc phân quyền phổ quát. Một số hệ thống cho HEAD theo cùng policy đọc của GET; hệ thống khác có policy metadata riêng hoặc không cung cấp HEAD trên route đó. Cần **thiết kế rõ** và kiểm thử cả HEAD lẫn GET, tránh matcher chỉ bảo vệ GET trong khi framework vẫn cho HEAD truy cập handler.

### 9.6. “HMAC đúng thì được xem báo cáo”

Không. HMAC có thể hợp lệ dù client ký đường dẫn đến báo cáo của tenant khác. Authorization phải kiểm tra principal, action và resource ownership, không chỉ MAC hoặc tình trạng khóa ACTIVE.

### 9.7. “Cache sẽ tự bảo vệ HEAD”

Không. CDN có thể trả metadata từ cache mà không đi qua backend; cấu hình cache không phân tách auth có thể làm lộ sự tồn tại hoặc kích thước tài nguyên. Kiểm thử edge cache và chính sách xác thực trước khi gửi response.

## 10. Bài tập vận dụng

**Bài 1 — Đọc response:** Server trả HEAD với `Content-Length: 184320` và không có response body. Hãy giải thích vì sao đây không phải mâu thuẫn; kiểm thử HTTP client thế nào để không chờ 184320 byte?

**Bài 2 — Canonical method:** Viết hai chuỗi canonical theo hợp đồng `hmac-head-v1` chỉ khác dòng method `HEAD` và `GET`, cùng secret và raw target. Vì sao tag phải khác nhau với xác suất áp đảo?

**Bài 3 — Gateway method rewrite:** Client ký HEAD nhưng gateway chuyển request thành GET trước khi verifier. Hãy chỉ ra điểm mất bảo đảm và đề xuất vị trí verify hoặc cơ chế giữ effective method đáng tin.

**Bài 4 — Path và query:** Với request đã ký `HEAD /v1/reports/report-42?format=pdf`, một attacker đổi thành `HEAD /v1/reports/report-42?format=csv`. Nếu HMAC bảo vệ raw target thì kết quả verify là gì?

**Bài 5 — SHA-256 của body rỗng:** Hãy phân biệt ba đại lượng: digest của **HEAD request body rỗng**, HMAC tag của **canonical HEAD request**, và `ETag` của **response representation**. Chúng có bắt buộc giống nhau không?

**Bài 6 — Authorization:** Client A có secret đúng, ký HEAD cho báo cáo của client B. Receiver xác thực thành công. Vì sao response phải tiếp tục qua policy tài nguyên trước khi tiết lộ `ETag` và `Content-Length`?

**Bài 7 — Replay và nhiều node:** Một HEAD đã ký hợp lệ bị gửi lại đồng thời qua hai node. Test nào xác minh kho nonce chặn được request thứ hai? Điều gì xảy ra nếu kho nonce không sẵn sàng?

**Bài 8 — HEAD qua cache:** CDN trả response HEAD từ metadata đã cache, không chuyển request đến backend. Thiết kế nào bảo đảm HMAC và quyền truy cập vẫn được kiểm tra cho mọi client/tenant?

## 11. Checklist triển khai HEAD-HMAC an toàn

1. **Ký literal HEAD:** method được bảo vệ; không cho GET/override dùng chữ ký HEAD.
2. **Bảo vệ target:** ký path và query ảnh hưởng nghiệp vụ theo contract; xử lý gateway rewrite nhất quán.
3. **Phân biệt request/response:** HEAD response không có body; request body rỗng theo contract minh họa; digest 0 byte khác `Content-Length` của GET representation.
4. **Kiểm tra header:** không chấp nhận signed header trùng hoặc framing mơ hồ; giới hạn kích thước request.
5. **Dùng HMAC chuẩn:** `Mac.getInstance("HmacSHA256")`, `init` bằng secret đã cấp, so raw tag bằng `MessageDigest.isEqual`.
6. **Tra khóa đúng audience:** gắn client ID, key ID, môi trường và dịch vụ; có key rotation và revoke.
7. **Chống replay:** timestamp trong cửa sổ, nonce duy nhất, kho nonce chia sẻ/atomic, fail closed.
8. **Kiểm tra phân quyền:** principal được phép đọc metadata của resource/tenant thật.
9. **Kiểm soát gateway/cache:** không phục vụ HEAD private từ cache trước auth; tránh HEAD/GET method confusion.
10. **Test cả tuyến:** unit cryptography, HTTP parser, proxy HTTP/2↔HTTP/1.1, routing, cache, status/header và response không có body.

## 12. Kết luận

**HEAD request** hỏi metadata của tài nguyên mà **không nhận response content**. Điều này không làm HEAD trở thành request luôn công khai, không đồng nghĩa response `Content-Length` bằng 0 và cũng không cho phép dùng chữ ký GET để xác thực HEAD. Trong HMAC request authentication, **method HEAD phải nằm trong canonical request**, cùng target/header/body digest được quy định; receiver kiểm tra shared secret, timestamp/nonce, trạng thái khóa và tính nhất quán sau gateway. Sau authentication, **authorization** vẫn phải bảo vệ metadata tài nguyên. Kiểm thử HEAD cần bao phủ cả response không body, gateway/route GET tự động và cache, vì chính những tầng này có thể làm mất ranh giới bảo mật dù phép HMAC chuẩn.

**Tài liệu tham khảo:**

- [RFC 9110 — HTTP Semantics, Section 9.3.2 HEAD](https://www.rfc-editor.org/rfc/rfc9110#section-9.3.2): định nghĩa HEAD, ngữ nghĩa response/request content.
- [RFC 9110 — Content-Length](https://www.rfc-editor.org/rfc/rfc9110#section-8.6): ý nghĩa Content-Length với HEAD response.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111): cache và cập nhật metadata từ HEAD.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): request line, framing và response semantics.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): pseudo-header method/path/authority.
- [RFC 2104 — HMAC](https://www.rfc-editor.org/rfc/rfc2104): cấu trúc thuật toán HMAC.
- [Java SE 17 — javax.crypto.Mac](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/Mac.html): `getInstance`, `init`, `doFinal`.
- [RFC 9421 — HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421): chuẩn tham khảo về ký các thành phần HTTP. `hmac-head-v1` trong bài là ví dụ học tập, **không** mặc nhiên tuân thủ RFC 9421.

# HTTP method viết hoa trong canonical request dùng HMAC

Trong một giao thức **HMAC request authentication**, client và verifier phải tạo ra **cùng một dãy byte** để tính chữ ký. Dù chỉ chiếm vài ký tự trong HTTP request, **method** là thành phần quan trọng: `GET`, `POST`, `PUT` hay `DELETE` xác định ý nghĩa hành động mà server có thể thực hiện. Nếu method bị đổi nhưng không nằm trong dữ liệu được ký, một chữ ký HMAC hợp lệ có thể bị tái sử dụng cho hành động khác.

Bài **“Method viết hoa”** thuộc chương **HTTP method** của module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**. Module thiết kế xác thực HTTP request bằng **shared secret** và canonical request gồm phương thức, URI, header hoặc body theo hợp đồng ký, kết hợp xác minh chữ ký, chống replay bằng timestamp/nonce, key rotation, kiểm thử proxy/gateway và phân biệt xác thực với phân quyền. Bài học giải thích chính xác khi nào cần viết hoa method, tại sao **không được tự đổi chữ thường thành chữ hoa** tại verifier, và cách bảo vệ method thực sự được router/backend xử lý.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **quy ước viết hoa** các HTTP method chuẩn với **tính phân biệt chữ hoa/chữ thường** của method token theo HTTP semantics.
2. Giải thích vì sao canonical request phải chứa method đã được kiểm tra và phải khớp với method thực sự được xử lý.
3. Xây chính sách allowlist, từ chối `post`/`PoSt` khi endpoint yêu cầu `POST` và không vô tình chấp nhận một extension method khác.
4. Nhận diện rủi ro từ `X-HTTP-Method-Override`, proxy/gateway rewrite, HTTP/2 `:method`, CORS preflight và các framework filter.
5. Viết ví dụ Java 17 ký và kiểm tra method bằng HMAC-SHA256, body digest, timestamp/nonce và so sánh tag an toàn.
6. Thiết kế kiểm thử tampering, case mismatch, replay, key rotation và authorization.

## 2. “Method viết hoa” thực sự nghĩa là gì?

Một HTTP/1.1 request bắt đầu bằng request line:

~~~http
POST /v1/transfers?dryRun=false HTTP/1.1
Host: api.example.test
Content-Type: application/json

{"from":"A","to":"B","amount":250000}
~~~

`POST` là **method token**. Các method phổ biến được định nghĩa bằng tên viết hoa ASCII: `GET`, `HEAD`, `POST`, `PUT`, `DELETE`, `CONNECT`, `OPTIONS`, `TRACE`; nhiều API còn sử dụng `PATCH`. Đây là tên method, **không phải tên header**.

Theo HTTP semantics, **method token phân biệt chữ hoa và chữ thường (case-sensitive)**. Do đó:

~~~text
POST   != post
POST   != PoSt
GET    != get
PATCH  != Patch
~~~

Hệ thống có thể định nghĩa extension method riêng với cách viết khác, nhưng `post` **không tự động là bí danh tiêu chuẩn của `POST`**. Việc một framework hoặc proxy chấp nhận `post` như `POST` là hành vi của implementation/configuration đó, không phải căn cứ để hợp đồng HMAC gộp hai giá trị.

| Dữ liệu | HTTP có phân biệt chữ hoa/thường? | Cách xử lý trong bài |
| --- | --- | --- |
| Method token: `POST` | **Có** | Chỉ chấp nhận dạng chính xác được endpoint allowlist. |
| Method token: `post` | **Có** | Không tự uppercase rồi xem là `POST`; từ chối nếu không được định nghĩa riêng. |
| Header field name: `Content-Type` / `content-type` | **Không** theo quy tắc tên trường HTTP | Hợp đồng có thể chuẩn hóa **tên header** về chữ thường. |
| Header field value: `application/json` | Tùy định nghĩa ngữ nghĩa của field | Không tự áp dụng quy tắc của method vào tất cả header values. |
| Path, query và body | Có quy tắc riêng theo URI/ứng dụng/byte | Không tự lowercase/uppercase vì có thể đổi tài nguyên hay nội dung. |

Vì thế **“canonical method viết hoa”** nên hiểu là: **client phát ra đúng method chuẩn bằng chữ hoa và verifier chỉ chấp nhận token chính xác theo chính sách**. Không phải “verifier lấy mọi chuỗi nhận được rồi gọi `toUpperCase()`”.

### 2.1. Tại sao không gọi toUpperCase một cách mù quáng?

Giả sử verifier làm:

~~~java
// KHÔNG KHUYẾN NGHỊ: có thể làm mất khác biệt của method token.
String canonicalMethod =
    receivedMethod.toUpperCase(java.util.Locale.ROOT);
~~~

Nếu nhận `post` mà vẫn xác minh bằng canonical `POST`, hệ thống có thể chấp nhận một token khác với token client đã thực sự gửi. Nguy hiểm hơn, proxy, gateway và backend có thể định tuyến hoặc phân quyền theo các quy tắc khác nhau: tầng xác minh coi `post` như `POST`, tầng xử lý khác lại coi đó là extension method hoặc route khác.

`Locale.ROOT` giúp phép chuyển chữ hoa mang tính xác định cho một số nghiệp vụ text, nhưng **không** biến việc gộp các HTTP method vốn case-sensitive thành một thiết kế đúng. Đối với API chỉ hỗ trợ các method chuẩn viết hoa, hãy **kiểm tra sự khớp chính xác** và từ chối biến thể khác. Nếu buộc phải hỗ trợ alias vì yêu cầu legacy, cần một hợp đồng giao thức riêng, mapping rõ tại trust boundary, và cùng một method đã được xác minh phải được sử dụng để route, authorize và thực thi.

## 3. Vai trò của method trong chữ ký HMAC

HMAC-SHA256 tính mã xác thực từ shared secret và dãy byte canonical:

~~~text
bodyHash     = lowerHex(SHA256(bodyBytes))
canonical    = JoinWithLF(version, method, requestTarget,
                          signedHeaders, bodyHash)
signatureB64 = Base64(HMAC_SHA256(secretBytes, UTF8(canonical)))
~~~

Nếu canonical **không có method**, hai request sau có thể có cùng HMAC dù hành động khác nhau:

~~~http
GET /v1/orders/42 HTTP/1.1
Host: api.example.test
~~~

~~~http
DELETE /v1/orders/42 HTTP/1.1
Host: api.example.test
~~~

Đối thủ có thể thay `GET` thành `DELETE` khi proxy có quyền sửa request, và nếu các thành phần được ký khác giữ nguyên, chữ ký không thay đổi. Kết quả thực tế còn phụ thuộc router/authorization, nhưng đó là một **lỗ hổng phạm vi ký** cần loại bỏ ngay từ hợp đồng.

Khi method nằm trong canonical, đổi một byte từ `GET` sang `DELETE` làm **dữ liệu HMAC khác**. Đối thủ không biết secret sẽ không thể tạo tag mới hợp lệ theo giả định an toàn của HMAC.

| Trường hợp | Method được ký? | Kết luận |
| --- | --- | --- |
| Chỉ ký body digest | Không | Proxy có thể đổi method mà body/tag vẫn khớp. |
| Ký method nhưng không ký URI | Có, URI không | Có thể đổi route/tài nguyên mà chữ ký vẫn đúng; vẫn không an toàn. |
| Ký method + raw URI + header nghiệp vụ + body digest | Có | Phát hiện thay đổi ở các trường đã ký, nếu verifier nhận cùng representation. |
| Ký đủ nhưng thiếu nonce store | Có | Request nguyên văn vẫn có thể bị replay trong cửa sổ timestamp. |
| Ký đủ nhưng backend thiếu phân quyền | Có | HMAC hợp lệ vẫn có thể thực hiện hành động ngoài quyền được cấp. |

**Phương thức, URI và body phải đi cùng nhau** trong đánh giá an ninh: `DELETE /v1/orders/42` khác `DELETE /v1/orders/43`, và `POST` chuyển tiền với số tiền khác trong body cũng là thao tác khác.

## 4. Cách xác định method trong HTTP/1.1, HTTP/2 và gateway

### 4.1. HTTP/1.1: request line

~~~http
POST /v1/payments?currency=VND HTTP/1.1
Host: api.example.test
~~~

Method là token trước dấu cách đầu tiên của request line. HTTP stack cần parse/validate token theo chuẩn. Tại server Java dùng Servlet, `HttpServletRequest.getMethod()` cung cấp method mà container nhìn thấy, nhưng một **filter/adapter** có thể đã sửa cách trình bày hoặc phương thức có hiệu lực trước khi controller nhận request.

### 4.2. HTTP/2 và HTTP/3: pseudo-header :method

Trong HTTP/2 và HTTP/3, không có request line dạng text `POST /... HTTP/1.1`. Method được mang bởi **pseudo-header `:method`**, chẳng hạn:

~~~text
:method: POST
:scheme: https
:authority: api.example.test
:path: /v1/payments?currency=VND
content-type: application/json
~~~

Tên pseudo-header `:method` viết chữ thường là **tên trường protocol**, còn **giá trị `POST` vẫn là method token và vẫn phân biệt chữ hoa/thường**. Không nhầm quy tắc tên header HTTP/2 phải viết chữ thường với quy tắc chuyển **giá trị method** sang chữ thường.

Gateway chuyển HTTP/2 thành HTTP/1.1 cần bảo đảm:

- Giá trị `:method` truyền thành method được backend hiểu **cùng một nghĩa**.
- `:path` chuyển sang request target phù hợp hợp đồng ký; không tự decode hoặc sắp xếp query gây khác canonical.
- `:authority` và `Host` được xác thực/ràng buộc theo chính sách audience; không tin `X-Forwarded-Host` do bên ngoài tự cung cấp.
- Nếu gateway rewrite hoặc lọc method, điểm verify phải nằm **trước khi** đổi ý nghĩa bảo mật hoặc có cơ chế metadata gốc đáng tin và mapping chặt chẽ.

### 4.3. Method được verify phải là method được thực thi

~~~mermaid
flowchart LR
    C["Client ký POST + URI + headers + body digest"] --> P["Proxy hoặc gateway"]
    P --> V["Verifier HMAC"]
    V --> R["Router / method override filter"]
    R --> B["Backend action"]
    style R fill:#fff2d6,stroke:#c99121,color:#593b00
~~~

Nếu verifier kiểm tra `POST` nhưng một filter **sau verify** biến request thành `DELETE`, backend có thể thực hiện một hành động **không phải hành động đã ký**. Điều này là một dạng **time-of-check/time-of-use gap** trong thiết kế ủy quyền. Đừng chỉ nhìn thứ tự đặt một filter để kết luận an toàn; cần biết vị trí thực hiện method override, routing và authorization trong stack cụ thể.

Thiết kế nên bảo đảm **method thực thi = method được ký và đã verify**, đồng thời route/authorization dựa trên cùng dữ liệu đó. Nếu một proxy không tin cậy đã thay method trước verifier, chữ ký phải sai; nếu proxy thay method sau verifier, cần kênh nội bộ có xác thực và kiểm soát toàn bộ hop để tránh bypass.

## 5. Method override: lỗ hổng thường bị bỏ sót

Một số web framework hoặc ứng dụng legacy hỗ trợ **HTTP method override** qua header hoặc tham số:

~~~http
POST /v1/orders/42 HTTP/1.1
X-HTTP-Method-Override: DELETE
Content-Type: application/json
~~~

Hoặc qua query/form field như `_method=DELETE`. Đây là cơ chế ứng dụng tự định nghĩa, **không** làm đổi method thực tế trên dây từ `POST` thành `DELETE`. Tuy nhiên, nếu router áp dụng override, backend có thể hành xử như nhận DELETE.

Giả sử hệ thống:

1. Client chỉ ký method trên dây là `POST`.
2. Verifier chấp nhận chữ ký `POST`.
3. Một middleware phía sau tin `X-HTTP-Method-Override: DELETE` không được ký và gọi handler xóa.

Kẻ tấn công sửa hoặc thêm override header có thể làm backend thực thi thao tác **không được ràng buộc trong HMAC**.

**Lựa chọn khuyến nghị cho HMAC API mới:** **vô hiệu hóa method override** trên các route được ký, reject các override header/field không được cho phép, chỉ định tuyến theo method HTTP thực nhận đã được xác minh. Nếu vì tương thích bắt buộc hỗ trợ override, phải định nghĩa rõ **wire method + effective method + override value + URI** trong hợp đồng ký, kiểm tra trước khi thực thi và bảo đảm cùng effective method được dùng cho authorization. Không tự tạo “đường tương thích” bằng cách bỏ method khỏi HMAC.

| Vùng rủi ro | Dấu hiệu | Cách phòng vệ |
| --- | --- | --- |
| Override header không ký | `X-HTTP-Method-Override: DELETE` làm thay handler | Disable hoặc reject; nếu hỗ trợ thì đưa hiệu lực và giá trị override vào hợp đồng ký. |
| Override query/form | `_method=PUT` được middleware hiểu nhưng HMAC chỉ ký POST | Không hỗ trợ trên route ký hoặc canonical hóa/verify đúng dữ liệu điều khiển hiệu lực. |
| Proxy/gateway tự đổi method | Client ký `POST`, backend nhận `PATCH` | Verify tại trust boundary thích hợp và kiểm tra method thực thi. |
| Framework filter chạy sai thứ tự | HMAC verify trước nhưng filter sau thay method | Kiểm tra filter chain, đặt routing/authorization dựa trên dữ liệu đã xác minh. |
| Cache hoặc policy không phân biệt method | GET được cho là giống HEAD hoặc POST | Cấu hình cache/policy đúng ngữ nghĩa method; không gộp method trong chữ ký. |

## 6. Hợp đồng canonical request mẫu với method viết hoa

Hợp đồng **HMAC-METHOD-V1** sau chỉ là **ví dụ học tập**, không phải một chuẩn bắt buộc cho mọi dịch vụ:

~~~text
HMAC-METHOD-V1
POST
/v1/payments?currency=VND&dryRun=false
audience:payments-api
x-client-id:partner-42
x-key-id:<key-id>
x-timestamp:<unix-epoch-seconds>
x-nonce:<32-lowercase-hex-characters>
content-type:application/json
x-content-sha256:<64-lowercase-hex-characters>
~~~

Các placeholder `<...>` mô tả nơi điền giá trị thật. Quy ước:

1. **Method:** chỉ `POST` viết hoa ASCII được phép ở route thanh toán của ví dụ. Verifier so sánh **chính xác** `"POST".equals(receivedMethod)`; không gọi `toUpperCase` hoặc `equalsIgnoreCase`.
2. **Raw request target:** raw path + raw query theo đúng request thực gửi; giữ thứ tự query/percent-encoding và xác minh route thực thi tương ứng. `/v1/payments` là route; `currency=VND` và `dryRun=false` ảnh hưởng nghiệp vụ nên nằm trong phạm vi ký.
3. **Audience:** literal `payments-api` chỉ được dùng khi verifier thực sự bảo vệ đúng dịch vụ này; không lấy audience từ header forwarded không xác thực.
4. **Client/key ID:** field đã ký, verifier tra đúng secret theo cặp identity và key ID, kiểm tra audience, thời hạn và key rotation.
5. **Timestamp/nonce:** epoch seconds dạng ASCII thập phân chính tắc và nonce 128 bit ngẫu nhiên dạng 32 hex chữ thường; server kiểm tra freshness và claim nonce nguyên tử.
6. **Content-Type:** đúng `application/json` theo hợp đồng; từ chối các biến thể/duplicate nếu chưa được quy định.
7. **Body hash:** SHA-256 của **body bytes thực gửi**, mã hóa 64 ký tự hex chữ thường; verifier tính lại từ body bytes thực nhận.
8. **Delimiter:** nối các dòng bằng đúng **LF (0x0A)**, **không** thêm LF cuối; canonical string mã hóa **UTF-8**.
9. **Signature:** HMAC-SHA256 trên toàn bộ canonical bytes, tag đầy đủ **32 byte**, gửi bằng **Base64 chuẩn có padding** trong `X-Signature`; không đưa chính `X-Signature` vào dữ liệu ký.

Nếu API cần `GET`, `PUT`, `PATCH` hoặc `DELETE`, có thể dùng cùng một định dạng canonical nhưng **mỗi route cần method allowlist phù hợp**. Ví dụ `GET /v1/orders/42` không được tự động dùng lại chữ ký của `HEAD /v1/orders/42`, dù HEAD có quan hệ ngữ nghĩa với GET. Nếu API hỗ trợ extension method như `PROPFIND`, tên của method phải được đưa vào contract **đúng nguyên dạng** và được allowlist riêng.

### 6.1. Dạng viết hoa không có nghĩa bỏ method khỏi HMAC

Một cách triển khai sai là:

~~~text
if method in {"GET", "POST", "DELETE"} then
    canonical = URI + bodyHash
else
    reject
~~~

Mặc dù có allowlist, `GET` và `DELETE` có thể tạo cùng canonical nếu URI/bodyHash giống nhau. **Validate method và ký method là hai việc khác nhau**, đều cần thiết.

### 6.2. Chuẩn hóa tên header khác chuẩn hóa method

Hợp đồng mẫu sử dụng `x-client-id`, `x-timestamp` và `content-type` trong canonical, dù HTTP client có thể gửi header với chữ hoa đầu từ như `X-Client-Id`. Đây là quy tắc **tên header**; không được suy ra rằng `post` cũng có thể đổi thành `POST`. Header values lại cần chính sách riêng về whitespace, duplicate, CR/LF và content coding.

## 7. Java 17: ký method chính xác và từ chối sửa method

Đoạn Java tự chứa sau dùng **HMAC-SHA256** qua `javax.crypto.Mac`, tạo request bằng `java.net.http.HttpRequest` và kiểm tra kết quả ký trong một tiến trình test. Secret được sinh ngẫu nhiên **chỉ cho ví dụ**, không gửi request ra mạng. Khi triển khai thật, client và server phải nhận **cùng secret được cấp** bằng secret manager và key ID, không tự sinh một secret riêng ở mỗi bên.

### 7.1. Ví dụ signer và verifier

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
import java.util.Base64;
import java.util.HexFormat;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class CanonicalHttpMethodExample {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final String TARGET =
        "/v1/payments?currency=VND&dryRun=false";
    private static final String CONTENT_TYPE = "application/json";
    private static final String CLIENT_ID = "partner-42";
    private static final String KEY_ID = "key-2026-11";
    private static final long PAST_SECONDS = 300;
    private static final long FUTURE_SECONDS = 60;

    // Chỉ ví dụ: một endpoint thanh toán chỉ cho phép POST.
    private static final Set<String> PAYMENT_METHODS = Set.of("POST");

    record SignedRequest(
        String method,
        String rawTarget,
        String clientId,
        String keyId,
        String timestamp,
        String nonce,
        String bodyHash,
        String signature,
        byte[] body
    ) {}

    // Trong production, replay state phải dùng storage chung có TTL.
    static final class DemoNonceStore {
        private final Set<String> seen =
            ConcurrentHashMap.newKeySet();

        boolean claim(String clientId, String nonce) {
            return seen.add(clientId + ":" + nonce);
        }
    }

    static String requirePaymentMethod(String method) {
        // Không đổi case và không dùng equalsIgnoreCase.
        if (method == null || !PAYMENT_METHODS.contains(method)) {
            throw new IllegalArgumentException(
                "Method phải đúng token POST (phân biệt hoa/thường)"
            );
        }
        return method;
    }

    static String sha256Hex(byte[] bytes)
            throws GeneralSecurityException {
        return HexFormat.of().formatHex(
            MessageDigest.getInstance("SHA-256").digest(bytes)
        );
    }

    static byte[] hmacSha256(byte[] secret, byte[] canonicalBytes)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(canonicalBytes);
    }

    static String canonical(String method, String rawTarget,
            String clientId, String keyId,
            String timestamp, String nonce, String bodyHash) {
        requirePaymentMethod(method);
        // Hợp đồng mẫu chỉ chấp nhận một số format/route cố định.
        if (!TARGET.equals(rawTarget) ||
            !CLIENT_ID.equals(clientId) ||
            !KEY_ID.equals(keyId) ||
            timestamp == null ||
            !timestamp.matches("[1-9][0-9]{0,18}") ||
            nonce == null ||
            !nonce.matches("[0-9a-f]{32}") ||
            bodyHash == null ||
            !bodyHash.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("Canonical field không hợp lệ");
        }
        return String.join("\n",
            "HMAC-METHOD-V1",
            method,                 // Dùng token đã được kiểm tra nguyên dạng.
            rawTarget,
            "audience:payments-api",
            "x-client-id:" + clientId,
            "x-key-id:" + keyId,
            "x-timestamp:" + timestamp,
            "x-nonce:" + nonce,
            "content-type:" + CONTENT_TYPE,
            "x-content-sha256:" + bodyHash
        );
    }

    static SignedRequest sign(byte[] secret, Clock clientClock)
            throws GeneralSecurityException {
        byte[] body = "{\"orderId\":\"ord-123\",\"amount\":50000}"
            .getBytes(StandardCharsets.UTF_8);
        String method = requirePaymentMethod("POST");
        String timestamp = Long.toString(
            clientClock.instant().getEpochSecond()
        );
        byte[] randomNonce = new byte[16]; // 128 bit
        RANDOM.nextBytes(randomNonce);
        String nonce = HexFormat.of().formatHex(randomNonce);
        String bodyHash = sha256Hex(body);

        String canonical = canonical(
            method, TARGET, CLIENT_ID, KEY_ID,
            timestamp, nonce, bodyHash
        );
        String signature = Base64.getEncoder().encodeToString(
            hmacSha256(
                secret, canonical.getBytes(StandardCharsets.UTF_8)
            )
        );

        return new SignedRequest(
            method, TARGET, CLIENT_ID, KEY_ID, timestamp,
            nonce, bodyHash, signature, body
        );
    }

    static boolean verify(SignedRequest request, byte[] secret,
            Clock serverClock, DemoNonceStore nonceStore)
            throws GeneralSecurityException {
        // Production phải lấy method từ HTTP parser tại boundary đáng tin.
        // Từ chối thay vì tự uppercase "post" thành "POST".
        if (request == null ||
            !PAYMENT_METHODS.contains(request.method()) ||
            request.body() == null ||
            request.signature() == null) {
            return false;
        }
        final String canonical;
        try {
            String bodyHash = sha256Hex(request.body());
            if (!bodyHash.equals(request.bodyHash())) {
                return false;
            }
            canonical = canonical(
                request.method(), request.rawTarget(),
                request.clientId(), request.keyId(),
                request.timestamp(), request.nonce(), bodyHash
            );
        } catch (IllegalArgumentException badCanonical) {
            return false;
        }
        final long timestampSeconds;
        try {
            timestampSeconds = Long.parseLong(request.timestamp());
        } catch (NumberFormatException badNumber) {
            return false;
        }
        long now = serverClock.instant().getEpochSecond();
        if (timestampSeconds < now - PAST_SECONDS ||
            timestampSeconds > now + FUTURE_SECONDS) {
            return false;
        }

        final byte[] supplied;
        try {
            supplied = Base64.getDecoder().decode(request.signature());
        } catch (IllegalArgumentException badBase64) {
            return false;
        }
        // Full HMAC-SHA256 = 32 byte, không chấp nhận prefix ngắn.
        if (supplied.length != 32 ||
            !Base64.getEncoder().encodeToString(supplied)
                .equals(request.signature())) {
            return false;
        }

        byte[] expected = hmacSha256(
            secret, canonical.getBytes(StandardCharsets.UTF_8)
        );
        if (!MessageDigest.isEqual(expected, supplied)) {
            return false;
        }
        // Chỉ claim nonce SAU khi HMAC hợp lệ.
        return nonceStore.claim(request.clientId(), request.nonce());
    }

    public static void main(String[] args) throws Exception {
        byte[] secret = new byte[32];
        RANDOM.nextBytes(secret); // Chỉ dùng cho test một tiến trình.
        Clock fixed = Clock.fixed(
            Instant.parse("2026-11-28T02:00:00Z"), ZoneOffset.UTC
        );
        SignedRequest request = sign(secret, fixed);

        // HTTP client gửi đúng "POST", không phải "post".
        HttpRequest httpRequest = HttpRequest.newBuilder(
                URI.create("https://api.example.test" + request.rawTarget()))
            .header("Content-Type", CONTENT_TYPE)
            .header("X-Client-Id", request.clientId())
            .header("X-Key-Id", request.keyId())
            .header("X-Timestamp", request.timestamp())
            .header("X-Nonce", request.nonce())
            .header("X-Content-SHA256", request.bodyHash())
            .header("X-Signature", request.signature())
            .POST(HttpRequest.BodyPublishers.ofByteArray(request.body()))
            .build();
        if (!"POST".equals(httpRequest.method())) {
            throw new AssertionError("HTTP client method bị thay đổi");
        }

        if (!verify(request, secret, fixed, new DemoNonceStore())) {
            throw new AssertionError("POST nguyên vẹn phải hợp lệ");
        }
        SignedRequest lower = new SignedRequest(
            "post", request.rawTarget(), request.clientId(),
            request.keyId(), request.timestamp(), request.nonce(),
            request.bodyHash(), request.signature(), request.body()
        );
        if (verify(lower, secret, fixed, new DemoNonceStore())) {
            throw new AssertionError("post phải bị từ chối");
        }
        SignedRequest changed = new SignedRequest(
            "DELETE", request.rawTarget(), request.clientId(),
            request.keyId(), request.timestamp(), request.nonce(),
            request.bodyHash(), request.signature(), request.body()
        );
        if (verify(changed, secret, fixed, new DemoNonceStore())) {
            throw new AssertionError("DELETE phải bị từ chối");
        }

        DemoNonceStore replayStore = new DemoNonceStore();
        if (!verify(request, secret, fixed, replayStore) ||
            verify(request, secret, fixed, replayStore)) {
            throw new AssertionError("Replay phải bị từ chối");
        }
        System.out.println("PASS: POST viết hoa, tampering, replay");
    }
}
~~~

**Các giới hạn cố ý của ví dụ:**

- `SignedRequest` mô phỏng request nhận, chưa phải HTTP parser production. Verifier thật phải lấy **method, raw URI, signed headers và body bytes từ request thực nhận tại trust boundary**; không tin một object hoặc chuỗi canonical do người gọi tự khai báo.
- `canonical` ràng buộc một endpoint cụ thể `POST /v1/payments?currency=VND&dryRun=false` để minh họa strict matching. Với nhiều route, dùng routing/allowlist cấu hình rõ và bảo đảm method được ký chính là method hiệu lực được thực thi.
- `DemoNonceStore` chỉ dùng một JVM, không lưu TTL. Môi trường nhiều replica phải dùng **nonce store chung**, claim nguyên tử và expiry bao phủ toàn bộ cửa sổ timestamp.
- `KEY_ID` được cố định cho dễ đọc; production chọn secret theo **client ID + key ID** và kiểm tra trạng thái active/revoked, audience và thời gian rotation trước khi xác minh.
- Kiểm tra `Content-Type`, duplicate header, method override, Content-Encoding, raw URI ambiguity, body size và trust boundary phải xảy ra khi đọc request thật; ví dụ này tập trung vào **method đúng chữ hoa và chữ ký HMAC**.
- Secret được tạo bằng `SecureRandom` trong test. Client/server production phải dùng **cùng một secret được phân phối an toàn**; không log key hoặc dữ liệu nhạy cảm.

## 8. Kiểm thử sai chữ hoa/chữ thường và các phương thức đặc biệt

### 8.1. Bảng các method thường gặp

| Method chính tắc | Ngữ nghĩa HTTP thông thường | Lưu ý khi HMAC |
| --- | --- | --- |
| `GET` | Lấy biểu diễn tài nguyên; thuộc nhóm safe methods | Ký `GET` chính xác, URI/query và các header cần bảo vệ. Không mặc định body GET có nghĩa thống nhất trên mọi stack. |
| `HEAD` | Tương tự GET nhưng không truyền response content | `HEAD` và `GET` là **hai chuỗi khác nhau**, không dùng chung canonical method. |
| `POST` | Thực hiện xử lý theo ngữ nghĩa endpoint | Dùng nonce và idempotency nếu thao tác có side effect. |
| `PUT` | Thường dùng tạo/thay thế trạng thái tài nguyên; idempotent theo semantics khi triển khai đúng | Ký URI, body và method; phân quyền vẫn cần kiểm tra. |
| `PATCH` | Áp dụng sửa đổi từng phần | Ký method/URI/body và các header về định dạng patch; không mặc định idempotent. |
| `DELETE` | Yêu cầu xóa hoặc hủy trạng thái tài nguyên; idempotent theo semantics nếu triển khai đúng | Phân quyền đặc biệt quan trọng; không được đổi từ GET/POST. |
| `OPTIONS` | Hỏi các lựa chọn giao tiếp; có thể dùng trong CORS preflight | Thường đi qua nhánh policy riêng của gateway, không tự đổi thành method nghiệp vụ. |
| `TRACE`, `CONNECT` | Có ngữ nghĩa giao thức đặc biệt | Chỉ bật khi cần và được policy chấp nhận; không coi là API method mặc định. |

Đặc tính **safe** hoặc **idempotent** của một method không xuất phát từ việc nó viết hoa hay từ chữ ký HMAC. Ví dụ một handler `GET` bị viết sai để gây side effect vẫn có thể gây hậu quả; một `POST` có idempotency key có thể xử lý retry an toàn hơn. Chữ ký không thay logic HTTP semantics và nghiệp vụ.

### 8.2. CORS preflight, HEAD và router

Browser có thể gửi request `OPTIONS` để kiểm tra CORS trước khi thực hiện `POST`. Preflight là **một request khác**, không thể lấy chữ ký của POST rồi dùng cho OPTIONS. Tùy thiết kế, gateway có thể xử lý OPTIONS trong một lớp policy CORS riêng mà không yêu cầu chữ ký client. Nếu chấp nhận OPTIONS không HMAC, route này **không được cấp quyền thực hiện thao tác nghiệp vụ**. Khi xử lý `HEAD`, cũng không dùng lại chữ ký `GET` chỉ vì hai method liên quan ngữ nghĩa.

Trong Java Servlet/Spring, kiểm tra:

- `HttpServletRequest.getMethod()` và routing thực tế có phản ánh đúng method nhận từ network không.
- Có filter, hidden method parameter, method override header, reverse proxy hoặc adapter nào đổi method **trước/sau** điểm HMAC verify không.
- Authorization policy có đánh giá **effective method** và tài nguyên đã được HMAC ràng buộc không.
- Cấu hình handler có tự ánh xạ HEAD qua GET hoặc OPTIONS tự động không; các request không ký có bị giới hạn đúng phạm vi không.

## 9. Replay, key rotation và proxy/gateway

### 9.1. Method đã ký không tự chống replay

~~~mermaid
sequenceDiagram
    participant C as Client
    participant P as Proxy có thể sao chép
    participant V as Verifier
    participant N as Nonce store
    C->>P: POST + URI + timestamp + nonce + HMAC
    P->>V: Chuyển nguyên request hợp lệ
    V->>N: Claim nonce nguyên tử
    N-->>V: Nonce mới
    V-->>P: Chấp nhận nếu được phân quyền
    P->>V: Replay POST nguyên vẹn
    V->>N: Claim cùng nonce
    N-->>V: Đã sử dụng
    V-->>P: Từ chối replay
~~~

Server phải kiểm tra timestamp đã ký còn nằm trong cửa sổ cho phép (ví dụ quá khứ tối đa 300 giây và tương lai tối đa 60 giây theo **chính sách ứng dụng**, không phải mặc định HMAC). Sau khi HMAC hợp lệ, server dùng nonce store **nguyên tử, dùng chung nhiều replica** để từ chối nonce đã dùng, với TTL đủ bao phủ tuổi thọ request.

Một retry của `POST` có **timestamp/nonce mới** vẫn có thể thực hiện cùng giao dịch lần hai. API có side effect cần **idempotency key** được ràng buộc trong canonical và xử lý nguyên tử ở tầng nghiệp vụ.

### 9.2. Key rotation không làm mất ràng buộc method

Trong giai đoạn chuyển key, verifier có thể đồng thời chấp nhận một key ID cũ và một key ID mới theo chính sách thời gian hiệu lực. Với **mỗi key**, phải ghi rõ thuật toán, audience, allowed routes và allowed methods; key ID nằm trong canonical request, nhưng **policy được server quản lý**, không lấy từ lời tự khai của client.

Ví dụ key chỉ được phép tạo thanh toán (`POST /v1/payments`) không được dùng để xóa đơn hàng (`DELETE /v1/orders/42`), ngay cả khi client sở hữu đúng secret và tạo được HMAC-SHA256 hợp lệ trên method DELETE. Đó là kiểm tra **phân quyền**, không phải thất bại của thuật toán HMAC.

### 9.3. Proxy không tin cậy và lỗi diễn giải method

| Sự kiện | Lỗ hổng có thể xảy ra | Cách khắc phục |
| --- | --- | --- |
| Proxy đổi `POST` thành `DELETE` trước verifier | Chữ ký sai nếu method nằm trong canonical | Fail closed, không bỏ method khỏi chữ ký. |
| Proxy gửi `post`, verifier tự uppercase | Tầng verify và router có thể hiểu hai method khác nhau | Reject token không đúng allowlist; không tự case-fold. |
| Middleware áp dụng method override sau HMAC verify | Backend thực thi method chưa được ký | Disable override hoặc bind cả effective method trong contract. |
| HTTP/2 `:method` được gateway đổi sang HTTP/1.1 | Sai lệch method/authority/path ở các hop | Test protocol translation và verify ở boundary tin cậy. |
| Gateway rewrite URI nhưng method giữ nguyên | Canonical/route có thể lệch | Ràng buộc cả raw URI và mapping, không chỉ method. |
| Backend tin `X-Verified: true` từ client/proxy | Có đường bypass HMAC | Ingress xóa header ngoài; xác thực gateway→backend và chặn gọi trực tiếp. |

HMAC không mã hóa request, không xác thực response và không ngăn proxy chặn/giữ request. Dùng **HTTPS tới điểm tin cậy phù hợp**, rate limit, timeout và cơ chế xác thực kênh nội bộ bên cạnh HMAC.

## 10. Ma trận kiểm thử method viết hoa

Với endpoint demo chỉ cho `POST /v1/payments?currency=VND&dryRun=false`, chạy signer/verifier và ghi nhận kết quả:

| Ca thử | Dữ liệu/thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Happy path | `POST` được ký, method/URI/body nguyên vẹn | HMAC hợp lệ, nonce mới và authorization quyết định quyền. |
| Chữ thường | Đổi `POST` thành `post`, giữ chữ ký cũ | **Từ chối**, không tự uppercase. |
| Mixed case | `PoSt` hoặc `Post` | **Từ chối** theo allowlist chính xác. |
| Đổi phương thức | `POST` thành `DELETE` nhưng giữ body và tag | Từ chối do method không được phép và/hoặc chữ ký sai. |
| GET so với HEAD | Cùng URI nhưng ký hai method khác nhau | Canonical khác; không tái sử dụng tag. |
| Ký method nhưng không ký URI | Giữ POST, sửa account ID trong path | Test phải phát hiện lỗi thiết kế; thêm raw URI vào canonical. |
| Body thay đổi | Giữ method, sửa amount sau khi ký | Digest/HMAC không khớp; từ chối. |
| Header override | `POST` cộng `X-HTTP-Method-Override: DELETE` | Từ chối/không áp dụng override trên route ký. |
| Override query | Thêm `_method=DELETE` | Không có quyền đổi effective method; nếu policy dùng query thì query phải được ký và kiểm soát. |
| Header trùng hoặc mơ hồ | Gửi hai `X-Signature` hoặc hai `X-Timestamp` | Từ chối trước khi route khác nhau về cách parse. |
| HTTP/2 → HTTP/1.1 | `:method: POST` sang request line `POST` | Vẫn đúng method và canonical; không tự đổi case. |
| CORS OPTIONS preflight | `OPTIONS` tới endpoint chỉ có POST được ký | Xử lý theo chính sách CORS giới hạn, không thực hiện nghiệp vụ POST. |
| Key rotation | Key ID active, overlap, revoked | Chỉ chấp nhận key đúng hiệu lực/audience/method policy. |
| Replay | Gửi lại POST có cùng HMAC/timestamp/nonce | Từ chối lần sau bằng nonce store dùng chung. |
| Concurrent replay | Hai replica nhận cùng POST/timestamp/nonce | Tối đa một lần claim nonce thành công. |
| Retry có nonce mới | Cùng thao tác thanh toán, chữ ký mới | Idempotency tránh tạo giao dịch lần hai. |
| Client thiếu quyền | Client có secret hợp lệ nhưng gọi method/tài nguyên ngoài scope | Authentication có thể đúng, **authorization từ chối**. |

### Câu hỏi tự đánh giá

1. Theo HTTP semantics, `POST` và `post` có phải cùng method token không? Tại sao API HMAC mới nên reject `post` thay vì tự uppercase?
2. Vì sao canonical đã bảo vệ URI và body hash vẫn cần thêm dòng method?
3. Trong HTTP/2, tại sao `:method` viết chữ thường không có nghĩa giá trị `POST` nên viết chữ thường?
4. Nếu verify HMAC trên `POST` rồi filter đổi effective method thành `DELETE`, hệ thống vi phạm ranh giới tin cậy ở đâu?
5. Một browser gửi `OPTIONS` preflight trước POST. Có thể dùng chữ ký của POST để xác thực OPTIONS không? Cách giới hạn OPTIONS như thế nào?
6. Vì sao HMAC đúng trên `DELETE` không chứng minh client có quyền xóa tài nguyên được yêu cầu?
7. Tại sao signed method, timestamp và nonce vẫn không đủ chống retry giao dịch có nonce mới?

## 11. Checklist triển khai

- [ ] Định nghĩa **allowlist method chính xác** cho từng endpoint, gồm phân biệt chữ hoa/thường; các method chuẩn dùng tên viết hoa như `GET`, `POST`, `PUT`, `DELETE`.
- [ ] Không tự dùng `toUpperCase`/`equalsIgnoreCase` để hợp thức hóa method token không đúng contract.
- [ ] Đưa **method thực thi** vào canonical cùng raw URI/query, các header nghiệp vụ và body hash/bytes theo hợp đồng ký.
- [ ] Kiểm tra thứ tự filter, router, method override và proxy rewrite; không cho effective method đổi sau khi HMAC verify mà không được ràng buộc.
- [ ] Xác minh cùng ngữ nghĩa method trên HTTP/1.1, HTTP/2/HTTP/3 và các gateway chuyển đổi protocol.
- [ ] Method override phải được vô hiệu hóa trên route ký hoặc được đưa vào hợp đồng rõ ràng, xác minh trước khi routing và authorization.
- [ ] Canonical có version, UTF-8, LF, signed fields/headers, key ID, timestamp và nonce được định nghĩa duy nhất.
- [ ] Secret được quản lý/rotate theo client/key ID, audience và method scope; tag HMAC-SHA256 đủ 32 byte theo chính sách.
- [ ] Nonce store dùng chung giữa replica, claim nguyên tử sau HMAC; idempotency bảo vệ thao tác có side effect.
- [ ] Authentication không thay authorization; backend kiểm tra method, scope, tenant, resource và không nhận identity từ proxy chưa xác thực.
- [ ] Có test sửa method case, method override, HTTP/2 translation, proxy rewrite, replay, key rotation và route bypass.

**Ghi nhớ:** Trong HMAC request authentication, **method là token case-sensitive theo HTTP**, còn các method chuẩn thường được viết **chữ hoa ASCII**. Hợp đồng ký an toàn phải **kiểm tra đúng method được phép, ký chính method đó và bảo đảm router thực thi cùng method đã xác minh**. Tự uppercase để “sửa” method, bỏ method khỏi canonical hoặc áp dụng method override sau xác minh đều có thể làm suy yếu bảo vệ. Timestamp/nonce, quản lý khóa và phân quyền là các lớp kiểm soát riêng không thể thay bằng việc viết hoa method.

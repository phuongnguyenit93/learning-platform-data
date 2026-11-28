# Changed path test: kiểm thử HMAC khi đường dẫn HTTP bị thay đổi

## 1. Mục tiêu của bài học

Trong module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, client xác thực HTTP request bằng **HMAC với shared secret**. Hai phía phải thống nhất cách xây dựng **canonical request** từ phương thức HTTP, URI, header hoặc body theo hợp đồng ký. Server xác minh chữ ký, kiểm tra timestamp/nonce chống replay, chọn key version đang hợp lệ khi rotation, sau đó mới xét quyền truy cập.

**Changed path test** là phép kiểm thử bảo đảm rằng chữ ký được tạo cho một đường dẫn HTTP **không thể bị tái sử dụng để xác thực request đến đường dẫn khác**, nếu path nằm trong hợp đồng ký.

Ví dụ client có quyền gửi:

```http
GET /api/orders/42 HTTP/1.1
X-Key-Id: client-test-v1
X-Request-Timestamp: 2026-11-28T03:00:00Z
X-Request-Nonce: nonce-unique-42
X-Signature: <HMAC_cho_GET_/api/orders/42>
```

Sau khi chữ ký được tạo, một bên trung gian thay request target thành:

```http
GET /api/orders/43 HTTP/1.1
X-Key-Id: client-test-v1
X-Request-Timestamp: 2026-11-28T03:00:00Z
X-Request-Nonce: nonce-unique-42
X-Signature: <VAN_GIU_HMAC_cho_GET_/api/orders/42>
```

Nếu hợp đồng ký bảo vệ path, server phải dựng canonical request cho path **thực sự được yêu cầu** và phát hiện chữ ký không khớp. Request bị từ chối **trước khi controller/service thực hiện nghiệp vụ**. Đối với API HMAC stateless, phản hồi thường là `401 Unauthorized` theo error contract.

Bài này giúp người học:

1. Xác định chính xác phần path nằm trong canonical request.
2. Thiết kế **positive control, negative test và mutation test** để chứng minh path được bảo vệ bằng HMAC.
3. Tránh test “đỗ giả” vì nonce bị replay, route không tồn tại hoặc filter chưa được gọi.
4. Phân biệt thay path với thay query, host, context path, percent encoding và gateway rewrite.
5. Viết test trên Java/Spring Security Servlet hoặc Spring WebFlux, sau đó chạy end-to-end qua proxy/gateway.
6. Giữ đúng ranh giới **authentication ≠ authorization**, chống replay và key rotation trong bài test.

## 2. Threat model: tại sao thay một path có thể gây nguy hiểm?

Một HTTP request có thể mang cùng body, cùng key ID và cùng signature nhưng lại đi đến **tài nguyên khác** chỉ vì path được thay:

| Request đã ký | Request bị sửa | Nguy cơ nếu HMAC không bảo vệ path |
| --- | --- | --- |
| `GET /api/orders/42` | `GET /api/orders/43` | Đọc đơn hàng khác |
| `POST /api/payments/preview` | `POST /api/payments/execute` | Từ thao tác xem trước sang thao tác có side effect |
| `POST /api/tenant-a/orders` | `POST /api/tenant-b/orders` | Cross-tenant target confusion |
| `PUT /api/users/101` | `PUT /api/users/102` | Cập nhật sai tài khoản |
| `POST /v1/transfer` | `POST /v2/transfer` | Chuyển sang API version có semantics khác |
| `GET /api/data/export-summary` | `GET /api/data/export-full` | Đổi phạm vi dữ liệu được yêu cầu |

HMAC không chỉ xác minh “client biết shared secret”. Nó cần liên kết chứng cứ mật mã với **request target cụ thể**. Nếu server chỉ ký method + body mà bỏ path, một chữ ký có thể được áp cho những route khác có cùng method và payload. Khi đó việc phân quyền vẫn có thể ngăn nhiều hành vi, nhưng hệ thống đã đánh mất một bảo đảm toàn vẹn quan trọng.

**Không nhầm lẫn hai lớp:**

- **Authentication/message integrity:** path hiện tại có khớp path được client ký không?
- **Authorization:** một client đã được xác thực có quyền đọc/sửa tài nguyên ở path đó không?

Ngay cả khi chữ ký được tạo đúng cho `/api/orders/43`, client vẫn có thể bị trả `403` nếu không được phép truy cập order 43. Ngược lại, quyền đọc order 43 không khiến một chữ ký cũ dành cho order 42 trở thành hợp lệ.

## 3. Hợp đồng ký quyết định path nào được bảo vệ

Không tồn tại một canonical request HMAC phổ quát áp dụng cho mọi API. Trong bài này, ta chọn **một hợp đồng minh họa**:

```text
HMAC-v1
UPPERCASE_METHOD
CANONICAL_REQUEST_TARGET
content-type:LOWERCASE_CONTENT_TYPE_OR_EMPTY
BASE64(SHA256(EXACT_BODY_BYTES))
TIMESTAMP
NONCE
```

Trong thực tế, mỗi dòng được ghép bằng một byte LF (`\n`); chữ `HMAC-v1` là contract/version marker. `CANONICAL_REQUEST_TARGET` bao gồm **path + query** theo quy tắc hợp đồng; không phải tên controller hay pattern `/api/orders/{id}`.

Với `GET /api/orders/42`, body rỗng, không có `Content-Type`, ví dụ chuỗi được ký có dạng:

```text
HMAC-v1
GET
/api/orders/42
content-type:
<BASE64_SHA256_OF_ZERO_BYTES>
2026-11-28T03:00:00Z
nonce-unique-42
```

`<BASE64_SHA256_OF_ZERO_BYTES>` chỉ là placeholder giải thích; test fixture phải tính digest thật từ byte array rỗng. Trong request có body, server phải hash **đúng bytes nhận được**, không deserialize JSON rồi serialize lại nếu hợp đồng ký raw body.

### 3.1. Raw path, decoded path và route pattern khác nhau

Trong Spring MVC và gateway, các API sau có thể biểu diễn path khác nhau:

- `request.getRequestURI()` là URI path như container cung cấp, có thể bao gồm context path.
- `request.getServletPath()` là phần servlet mapping; không mặc nhiên bằng request target công khai.
- `request.getQueryString()` giữ phần query theo representation container quan sát được.
- `@PathVariable String id` chứa giá trị đã được mapping/conversion xử lý.
- `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` có thể cho `/api/orders/{id}`, **không được dùng làm path ký** thay vì path request.
- Trong WebFlux, `exchange.getRequest().getURI().getRawPath()` và `getRawQuery()` cho biểu diễn URI tại thời điểm WebFlux nhìn thấy request, có thể đã được proxy/framework biến đổi.

Nếu client ký `/api/orders/42` nhưng service thay bằng pattern `/api/orders/{id}`, hai target 42 và 43 sẽ có cùng chuỗi pattern. Đây là lỗi canonicalization nghiêm trọng.

### 3.2. Test cần giữ nguyên những thành phần khác

Trong **changed path test thuần túy**, chỉ biến đổi path **sau khi tạo chữ ký**:

| Thành phần | Request A (được ký) | Request B (được gửi) |
| --- | --- | --- |
| Method | `GET` | `GET` |
| Path | `/api/orders/42` | `/api/orders/43` |
| Query | Rỗng | Rỗng |
| Content-Type | Rỗng | Rỗng |
| Body bytes | Rỗng | Rỗng |
| Key ID | `client-test-v1` | Giữ nguyên |
| Timestamp | Còn hiệu lực | Giữ nguyên |
| Nonce | Mới, chưa được gửi | Giữ nguyên |
| Signature | HMAC cho `/api/orders/42` | **Giữ nguyên chữ ký này** |

Không “sửa giúp” signature theo path mới ở negative case; nếu làm vậy, phép thử không còn chứng minh server phát hiện thay path.

## 4. Bộ ba kiểm thử tối thiểu: baseline, mutation và positive control

Một test tốt có ba trường hợp độc lập:

### Case A — Baseline: ký và gửi cùng path

```text
signed_target = /api/orders/42
sent_target   = /api/orders/42
nonce         = fresh-A
signature     = HMAC(signed_target, ...)
expected      = authentication accepted
```

Nếu fixture đủ authority và tài nguyên tồn tại, endpoint có thể trả `200`. Nếu không, test phải có cách quan sát rằng authentication đã thành công, phân biệt với authorization/404.

### Case B — Changed path: chữ ký cũ, target mới

```text
signed_target = /api/orders/42
sent_target   = /api/orders/43
nonce         = fresh-B
signature     = HMAC(signed_target, ...)
expected      = signature mismatch / 401
side effect   = none
```

**Fresh-B chưa từng được dùng trước đó.** Đây là chi tiết quan trọng: nếu dùng lại nonce từ Case A, verifier có thể chặn vì replay và test vẫn thấy `401` dù server bỏ path khỏi canonical request. Một assertion chỉ nhìn mã HTTP sẽ tạo **false positive**.

### Case C — Positive control trên chính path mới

```text
signed_target = /api/orders/43
sent_target   = /api/orders/43
nonce         = fresh-C
signature     = HMAC(signed_target, ...)
expected      = authentication accepted
```

Case C kiểm tra rằng `/api/orders/43` thật sự có handler, security matcher và credential hợp lệ. Nếu path mới không tồn tại hoặc bị deny bởi một policy độc lập, Case B trả `404`/`403` không thể chứng minh HMAC đã bảo vệ path.

**Mỗi case cần một nonce độc lập và timestamp trong cửa sổ.** Đối với trường hợp B, không gửi baseline sử dụng nonce B trước rồi mới gửi mutated request. Nếu cần assert reason, dùng verifier spy/structured security event trong môi trường test để phân biệt `signature_mismatch` với `replay_detected` mà không lộ secret ra response.

## 5. Thiết kế test oracle: thế nào là PASS?

Một negative test không nên coi “bất kỳ status không phải `200`” là PASS. Nên chứng minh bốn tầng:

1. **Đúng dữ liệu đầu vào:** signature thực sự được tạo cho path A nhưng HTTP request gửi đến path B; body/header/method/nonce giữ nguyên.
2. **Đúng security chain:** request đến verifier HMAC thuộc security chain đã định, không bị 404 ở gateway hoặc firewall chặn trước khi verify theo cách che lỗi.
3. **Đúng quyết định:** server phát hiện signature mismatch theo hợp đồng ký; trả `401` hoặc mã auth failure đã được API quy định.
4. **Không có side effect:** controller/service/repository cho tài nguyên B không chạy, nonce không bị đánh dấu “accepted” trước khi signature được xác minh nếu thiết kế yêu cầu verify trước reserve.

Một test mạnh có thể quan sát test-only security outcome:

```text
HTTP status                 = 401
security_reason_internal    = signature_mismatch
authenticated_principal     = absent
orderService.invocations    = 0
nonce_store.reserve_calls   = 0
```

`nonce_store.reserve_calls = 0` chỉ là kỳ vọng đối với **pipeline có verify HMAC trước reserve nonce**, không phải một quy tắc bắt buộc cho mọi kiến trúc. Nếu implementation dùng thứ tự khác nhưng vẫn chống replay an toàn, test cần thay assertion phù hợp; không vì mục tiêu test mà tự áp một thứ tự sai hợp đồng.

### 5.1. Không biến thông tin nội bộ thành response công khai

Để tránh oracle cung cấp thông tin về key ID và tình trạng signature, phản hồi public thường chỉ có:

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json
WWW-Authenticate: HMAC realm="signed-api"

{"type":"about:blank","title":"Unauthorized","status":401}
```

`HMAC` ở `WWW-Authenticate` là **scheme minh họa theo hợp đồng riêng**. Không mặc định có một chuẩn challenge HMAC chung cho tất cả dịch vụ. Lý do cụ thể `signature_mismatch` có thể được log/test trong môi trường tin cậy, không cần công bố cho người gửi.

## 6. Test signer Java: kiểm soát chính xác canonical bytes

Để kiểm thử đáng tin, cần một bộ ký trong test fixture độc lập về dữ liệu đầu vào nhưng tuân theo **cùng đặc tả wire contract**. Không gọi trực tiếp method nội bộ của verifier để “xin” chữ ký mong đợi; cách làm đó có thể khiến cùng một bug canonicalization tồn tại ở cả signer và verifier mà test không phát hiện.

Ví dụ fixture Java 17 cho hợp đồng HMAC-v1 minh họa:

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacTestSigner {

    private final String keyId;
    private final byte[] testSecret;

    public HmacTestSigner(String keyId, byte[] testSecret) {
        this.keyId = keyId;
        this.testSecret = testSecret.clone();
    }

    public SignedRequest sign(
            String method,
            String rawTarget,
            String contentType,
            byte[] rawBody,
            String timestamp,
            String nonce) throws GeneralSecurityException {

        String bodyHash = Base64.getEncoder().encodeToString(
                MessageDigest.getInstance("SHA-256").digest(rawBody));

        // Đây là ví dụ hợp đồng: tên field, newline,
        // query/header rules phải khớp tài liệu API.
        String canonical = String.join("\n",
                "HMAC-v1",
                method.toUpperCase(java.util.Locale.ROOT),
                rawTarget,
                "content-type:" + contentType,
                bodyHash,
                timestamp,
                nonce);

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(testSecret, "HmacSHA256"));
        String signature = Base64.getEncoder().encodeToString(
                mac.doFinal(canonical.getBytes(StandardCharsets.UTF_8)));

        return new SignedRequest(
                keyId, timestamp, nonce, signature);
    }

    public record SignedRequest(
            String keyId,
            String timestamp,
            String nonce,
            String signature) {
    }
}
```

Ở đây `rawTarget` là path cộng query đúng như contract, ví dụ `/api/orders/42` hoặc `/api/orders/42?view=short`. `contentType` là `""` nếu header không có mặt và contract cho phép; nếu là JSON thì cần dùng đúng giá trị header đã được ký. `rawBody` chính là byte array gửi qua HTTP.

Đừng hard-code secret production trong fixture. Test secret phải được cấp từ configuration dành riêng cho test, không log hoặc đưa vào screenshot/ticket. **Độc lập không có nghĩa cố ý dùng canonical format khác:** fixture và server phải tuân theo cùng đặc tả đã công bố, tốt nhất có golden vectors được kiểm tra qua client ở ngôn ngữ khác.

### 6.1. Đặt timestamp và nonce có kiểm soát

Có thể dùng `Clock.fixed(...)` trong unit test để đánh giá cửa sổ thời gian một cách xác định; integration test có thể dùng thời gian hiện tại và nonce độc lập:

```java
String timestamp = Instant.now().toString();
String nonce = "changed-path-" + UUID.randomUUID();
```

Dạng timestamp và nonce phải khớp hợp đồng thật. Nếu server yêu cầu Unix epoch seconds, không dùng ISO-8601 chỉ vì `Instant.toString()` thuận tiện. Với unit test, fake `Clock` và fake nonce store giúp test tái lập được, không phải `Thread.sleep()` rồi mong hết TTL.

Không dùng cùng nonce giữa các case khi muốn chứng minh lỗi do path mutation.

## 7. Test lõi bằng Spring MVC và MockMvc

Trong Spring Boot 3/Spring Security 6 Servlet stack, `MockMvc` có thể chạy request qua `SecurityFilterChain` cùng HMAC filter và controller. Dùng `@SpringBootTest` và `@AutoConfigureMockMvc` để kiểm thử integration; không tắt filters.

Ví dụ giả định có fixture `HmacTestSigner signer`, key test đã được đăng ký trong key store, route `GET /api/orders/{id}` cần HMAC và có service mock/spy để kiểm tra không có side effect. Các import và cấu hình fixture được lược:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ChangedPathHmacMvcIT {

    @Autowired MockMvc mvc;
    @Autowired HmacTestSigner signer;

    @Test
    void changingPathWithoutResigningMustReturn401() throws Exception {
        String timestamp = Instant.now().toString();
        String nonce = "mutated-" + UUID.randomUUID();

        HmacTestSigner.SignedRequest signed = signer.sign(
                "GET",
                "/api/orders/42",  // Path được ký.
                "",
                new byte[0],
                timestamp,
                nonce);

        mvc.perform(get("/api/orders/43")  // Path gửi thật.
                .header("X-Key-Id", signed.keyId())
                .header("X-Request-Timestamp", signed.timestamp())
                .header("X-Request-Nonce", signed.nonce())
                .header("X-Signature", signed.signature()))
                .andExpect(status().isUnauthorized());
    }
}
```

Ví dụ minh họa cấu trúc integration test; `HmacTestSigner` phải được đăng ký làm bean dành riêng cho test hoặc được khởi tạo trong fixture. Endpoint, security matcher, header names và time format phải khớp hợp đồng ứng dụng.

**Kiểm tra thêm:** gắn test-double cho order service/repository, assert nó không được gọi. Nếu dùng Mockito, có thể dùng `verifyNoInteractions(orderService)` sau negative request, nhưng nhớ reset fixture giữa các tests để invocation ở test khác không gây nhiễu.

### 7.1. Baseline và positive control

Với cùng route, hai test bổ sung:

```java
// Case A: ký /42 và gửi /42.
var a = signer.sign("GET", "/api/orders/42", "",
        new byte[0], freshTimestamp(), freshNonce());
var resultA = mvc.perform(get("/api/orders/42")
        .header("X-Key-Id", a.keyId())
        .header("X-Request-Timestamp", a.timestamp())
        .header("X-Request-Nonce", a.nonce())
        .header("X-Signature", a.signature()));
// Với fixture có dữ liệu + quyền đọc, kỳ vọng 200.

// Case C: ký /43 và gửi /43.
var c = signer.sign("GET", "/api/orders/43", "",
        new byte[0], freshTimestamp(), freshNonce());
var resultC = mvc.perform(get("/api/orders/43")
        .header("X-Key-Id", c.keyId())
        .header("X-Request-Timestamp", c.timestamp())
        .header("X-Request-Nonce", c.nonce())
        .header("X-Signature", c.signature()));
// Với fixture có dữ liệu + quyền đọc, kỳ vọng 200.
```

Đây là pseudocode Java có cú pháp gần thực tế; `freshTimestamp()` và `freshNonce()` là helper test chưa triển khai. Thực hành thật cần thêm `andExpect(status().isOk())` và verify service được gọi đúng tài nguyên. Nếu route được cố ý ẩn bằng `404` khi không có quyền, cần seed dữ liệu để positive control chứng minh **authentication đã thành công** một cách không mơ hồ.

### 7.2. Không dùng path sai không khớp matcher

Nếu route gốc là `/api/orders/42` nhưng route mutated thành `/public`, request có thể đi vào security chain khác hoặc route `permitAll`. Test đó hữu ích để tìm bug route bypass, nhưng **không thay thế** changed path test thuần túy giữa hai giá trị `/{id}` trong cùng phạm vi HMAC.

Nên có hai nhóm test riêng:

- **Same protected route family:** `/api/orders/42` → `/api/orders/43` nhằm chứng minh path đã ký.
- **Security boundary mutation:** `/api/orders/42` → `/admin/orders/42`, `/health` hoặc route context khác nhằm chứng minh chain/matcher không bị bypass theo policy.

## 8. Kiểm thử đơn vị canonicalizer: path có thực sự vào MAC input?

Trước integration test, test unit có thể kiểm tra rằng canonicalizer tạo dữ liệu khác khi chỉ thay path.

```java
@Test
void canonicalBytesChangeWhenOnlyPathChanges() {
    CanonicalRequest a = canonicalizer.build(
            "GET", "/api/orders/42", "", new byte[0],
            "2026-11-28T03:00:00Z", "nonce-A");

    CanonicalRequest b = canonicalizer.build(
            "GET", "/api/orders/43", "", new byte[0],
            "2026-11-28T03:00:00Z", "nonce-A");

    assertFalse(Arrays.equals(a.bytes(), b.bytes()));
}
```

`CanonicalRequest` và `canonicalizer` là API ứng dụng giả định, không thuộc JDK. Đây là **test cần thiết nhưng chưa đủ**: hai chuỗi canonical khác nhau không đảm bảo verifier thật sự dùng đúng path khi tính HMAC. Integration test phải thử signature cũ trên path mới.

Một kiểm tra cryptographic độc lập:

```java
byte[] key = testSecret();
String sig42 = signCanonical("GET", "/api/orders/42", key);
String sig43 = signCanonical("GET", "/api/orders/43", key);

assertNotEquals(sig42, sig43);
```

Đoạn này minh họa helper test; không phải API sẵn có. Signature khác nhau là kỳ vọng từ HMAC trên hai thông điệp khác nhau; không cần in chữ ký ra log để quan sát.

## 9. Mutation matrix: thay path theo nhiều cách

Changed path không chỉ là đổi `42` thành `43`. Một số biến thể có thể được framework/proxy chuẩn hóa khác nhau; phải phân loại theo chính sách canonicalization:

| Biến thể | Request gốc | Request mutated | Cần chứng minh |
| --- | --- | --- | --- |
| Thay path variable | `/api/orders/42` | `/api/orders/43` | Chữ ký cũ phải bị từ chối |
| Thay segment cố định | `/api/orders/42` | `/api/users/42` | Không dùng signature của tài nguyên khác |
| Thêm segment | `/api/orders/42` | `/api/orders/42/items` | Request target mới không được dùng signature cũ |
| Bỏ segment | `/api/orders/42/items` | `/api/orders/42` | Không rút gọn path ngoài contract |
| Trailing slash | `/api/orders/42` | `/api/orders/42/` | Chấp nhận hay từ chối phải theo canonical rule |
| Case khác nhau | `/api/Orders/42` | `/api/orders/42` | Không tự lowercase path trừ khi contract nói vậy |
| Duplicate slash | `/api/orders/42` | `/api//orders/42` | Framework/proxy normalization có kiểm soát |
| Percent encoding | `/api/orders/%34%32` | `/api/orders/42` | Raw vs decoded policy phải nhất quán |
| Encoded slash | `/api/files/a%2Fb` | `/api/files/a/b` | Không bypass path segment sau decode |
| Dot segments | `/api/x/../orders/42` | `/api/orders/42` | Canonical normalization hoặc reject từ edge |
| Matrix parameter | `/api/orders/42` | `/api/orders/42;v=2` | Contract/router có thống nhất không |
| API version | `/v1/orders/42` | `/v2/orders/42` | Version path phải được bảo vệ |
| Context path/prefix | `/public/api/orders/42` | `/api/orders/42` | Ký public hay internal target rõ ràng |
| Unicode/UTF-8 | Path đã encode theo policy | Path codepoint/encoding khác | Không suy diễn normalization từ framework |
| Path rỗng/root | `/api/orders/42` | `/` | Không bị chuyển vào anonymous policy ngoài ý muốn |

**Không ép mọi biến thể phải trả đúng `401`.** Servlet container, Spring Security HTTP firewall hoặc gateway có thể từ chối một raw path không hợp lệ bằng `400` trước khi HMAC verifier chạy. Trong trường hợp ấy, test thuộc nhóm **input normalization / routing boundary** và phải ghi rõ stage từ chối. Nếu yêu cầu chứng minh path nằm trong HMAC, chọn hai path hợp lệ cùng security route để verifier chắc chắn nhận request.

### 9.1. Percent encoding có thể tạo false positive/false negative

Ví dụ:

```text
/api/orders/%34%32
/api/orders/42
```

Hai biểu diễn này có thể dẫn đến cùng logical path variable sau URL decoding, nhưng **raw bytes khác nhau**. Có hai cách hợp đồng có thể chọn:

1. **Raw request target signing:** hai chuỗi khác nhau → HMAC khác; reusing signature phải fail.
2. **Canonical decoded-and-reencoded target:** chúng có thể canonicalize thành một chuỗi giống nhau **nếu** contract và firewall cho phép; test phải kiểm tra chính xác quy tắc đó.

Không mặc định trường hợp thứ hai “kém an toàn” hoặc “đúng”; yêu cầu là một hợp đồng canonicalization duy nhất, không mơ hồ, không tạo đường dẫn đến tài nguyên khác ngoài điều đã ký. Nếu server chấp nhận các dạng tương đương, cần kiểm chứng **route thực thi vẫn là cùng tài nguyên** và không xảy ra traversal/bypass.

## 10. Changed path và changed query là hai bài test có liên quan

Path và query đều thuộc request target ở nhiều giao thức HMAC, nhưng nên có test tách biệt.

Ví dụ:

```text
A: /api/orders/42?view=short
B: /api/orders/43?view=short   (changed path)
C: /api/orders/42?view=full    (changed query)
D: /api/orders/42?view=short&admin=true (extra query)
```

Trong changed path test, giữ nguyên query để cô lập tác động. Trong changed query test, giữ nguyên path và đổi một hoặc nhiều parameter. Hợp đồng phải định nghĩa xử lý:

- Thứ tự query parameters, ví dụ `a=1&b=2` và `b=2&a=1`.
- Duplicate keys, ví dụ `role=user&role=admin`.
- Query trống hoặc giá trị rỗng, dấu `?` cuối và dấu `=`.
- Percent encoding, dấu `+` và `%20`.
- Unicode và ký tự chưa encode hợp lệ/không hợp lệ.
- Các query parameter mà gateway thêm hoặc loại bỏ.

Nếu query không được ký theo contract, thay query có thể không gây signature mismatch nhưng vẫn thay hành vi nghiệp vụ. Đó là quyết định thiết kế cần được xem xét trong threat model; không gán kỳ vọng của changed-path test sang changed-query test một cách mù quáng.

## 11. Gateway/proxy rewrite: chữ ký đúng tại client nhưng path khác tại service

Một tình huống triển khai thường gặp:

```text
Client ký:          POST /public/v1/orders/42
Edge gateway nhận:  POST /public/v1/orders/42
Gateway rewrite:    POST /internal/orders/42
Spring Boot nhận:   POST /internal/orders/42
```

Nếu hợp đồng quy định ký **public request target**, verifier tại service cần có cách tin cậy để khôi phục `/public/v1/orders/42` hoặc phải xác minh HMAC ngay tại edge **trước** khi rewrite.

`Forwarded` theo RFC 7239 thường truyền `for`, `by`, `host`, `proto`; **nó không định nghĩa original path/query**. Một số gateway dùng `X-Original-URI` hoặc `X-Forwarded-Prefix` theo quy ước riêng, nhưng các header này có thể bị client giả mạo nếu ingress không làm sạch.

### 11.1. Positive test qua gateway

```text
signed_public_target = /public/v1/orders/42
sent_public_target   = /public/v1/orders/42
gateway_upstream     = /internal/orders/42
expected             = HMAC accepted
```

Test bảo đảm proxy rewrite không làm hỏng phép xác minh, khi canonical policy là public URI.

### 11.2. Negative test thay public path

```text
signed_public_target = /public/v1/orders/42
sent_public_target   = /public/v1/orders/43
gateway_upstream     = /internal/orders/43
signature            = giữ nguyên signature của /42
nonce                = mới, chưa từng dùng
expected             = HMAC rejected before handler
```

Nếu service khôi phục original URI từ ingress, test phải xác nhận **giá trị sau khi ingress sanitize** được dùng. Không cho client tự đặt `X-Original-URI: /public/v1/orders/42` để khiến request gửi đến `/43` được xác thực như `/42`.

### 11.3. Thử giả mạo forwarded/original path

Một ca tấn công quan trọng:

```http
GET /public/v1/orders/43 HTTP/1.1
X-Original-URI: /public/v1/orders/42
X-Forwarded-Host: trusted.example.test
X-Signature: <signature_cho_/public/v1/orders/42>
```

Kết quả an toàn đòi hỏi gateway **loại bỏ hoặc ghi đè** forwarded metadata do client gửi, service chỉ tin metadata từ proxy được cho phép và canonical target trùng **tài nguyên thực sự được route**. Nếu test đi thẳng vào service và tự gắn header trusted, nó chỉ thử logic parse header, **không chứng minh trust boundary**.

### 11.4. Hai mô hình xác minh được phép

| Mô hình | Path ký | Điểm kiểm tra | Yêu cầu test |
| --- | --- | --- | --- |
| **Verify at edge** | Public path client gửi | Gateway trước rewrite | Edge phải reject changed path trước forwarding; identity gửi downstream có trust contract |
| **Verify at service** | Public path hoặc internal target đã công bố | Spring Security ở service | Metadata/path phải được bảo toàn và xác thực nguồn; rewrite không làm thay logical target |

Không “thử lần lượt public path và internal path cho tới khi signature khớp”. Cách đó mở rộng tập thông điệp được chấp nhận và khiến test không thể chứng minh một target duy nhất được bảo vệ.

## 12. Spring MVC: Servlet path, context path và firewall

Trong Spring MVC, `HttpServletRequest` có nhiều getter cùng mang tính chất path. Cần thiết kế verifier và test sao cho chúng dùng đúng contract.

Ví dụ minh họa:

```java
String requestUri = request.getRequestURI();
String servletPath = request.getServletPath();
String query = request.getQueryString();
String contextPath = request.getContextPath();

// Chỉ minh họa dữ liệu container cung cấp.
// Không tự lấy servletPath làm canonical public target.
```

Nếu app chạy dưới context path `/app`, `getRequestURI()` có thể là `/app/api/orders/42`, trong khi `getServletPath()` khác. Nếu reverse proxy tách prefix, path phía client càng khác. Test cần chỉ rõ path nào ký, chứ không tùy tiện thêm hoặc bỏ context path để “làm signature hợp lệ”.

### 12.1. Filter phải chạy trước controller

Ví dụ logic:

```java
final HmacVerification verified;
try {
    verified = hmacVerifier.verify(request);
} catch (AuthenticationException ex) {
    SecurityContextHolder.clearContext();
    authenticationEntryPoint.commence(request, response, ex);
    return; // Không cho controller nhìn thấy path bị thay.
}

// Nếu verifier đọc body, chuyển request wrapper phát lại.
SecurityContextHolder.setContext(
        buildContextFromVerifiedIdentity(verified));
chain.doFilter(verified.requestForChain(), response);
```

Các kiểu `HmacVerification` và helper là thành phần do ứng dụng định nghĩa. Phần filter dùng `OncePerRequestFilter` và phải được nối vào `SecurityFilterChain` đúng scope. `@RestControllerAdvice` không thay thế xử lý lỗi HMAC phát sinh trước `DispatcherServlet`.

### 12.2. Filter firewall có thể từ chối trước HMAC

Spring Security có `StrictHttpFirewall` và servlet container có giới hạn với encoded slash, semicolon, newline, path traversal hoặc URL không hợp lệ. Nếu request bị từ chối ở đây, trạng thái có thể là `400` trước khi HMAC được tính.

Khi chạy mutation matrix:

- Test path hợp lệ `/api/orders/42` → `/api/orders/43` để chứng minh HMAC path binding.
- Test encoded/traversal variants riêng để chứng minh ingress/firewall không nhận target mơ hồ.
- Không nới lỏng firewall chỉ để test nhận được `401`. Nếu một dạng path bị firewall cấm, **từ chối sớm vẫn là kết quả an toàn**.
- Đừng tắt security filters trong `MockMvc`; cấu hình `addFilters=false` có thể làm bài test vô nghĩa.

## 13. Spring WebFlux: WebTestClient và URI thực được gửi

Trong WebFlux, request dùng `ServerWebExchange` và `ServerHttpRequest`. HMAC filter thường được xây bằng `AuthenticationWebFilter`, `ReactiveAuthenticationManager` hoặc custom `WebFilter`.

Ví dụ test minh họa:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ChangedPathHmacWebFluxIT {

    @Autowired WebTestClient client;
    @Autowired HmacTestSigner signer;

    @Test
    void changedPathIsRejected() throws Exception {
        var signed = signer.sign(
                "GET",
                "/api/orders/42",
                "",
                new byte[0],
                Instant.now().toString(),
                "webflux-path-" + UUID.randomUUID());

        client.get()
                .uri(URI.create("/api/orders/43"))
                .header("X-Key-Id", signed.keyId())
                .header("X-Request-Timestamp", signed.timestamp())
                .header("X-Request-Nonce", signed.nonce())
                .header("X-Signature", signed.signature())
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

`HmacTestSigner` là test fixture, không phải API của Spring. Chạy trên `RANDOM_PORT` để kiểm tra cả HTTP codec/router nếu mục tiêu là integration ở mức transport. Với ký raw path chứa percent encoding, nên dùng `URI` và/hoặc raw HTTP client có kiểm soát để tránh test client tự encode lại URI.

### 13.1. Trường hợp WebFlux ký body

Nếu HMAC ký body, test changed path vẫn phải giữ **body bytes** giống hệt:

1. Chuẩn bị `byte[] body` một lần.
2. Ký `method + signedTarget + bodyHash` với body đó.
3. Gửi **cùng byte[] body** tới mutated path.
4. Verifier đọc body có giới hạn từ `Flux<DataBuffer>`, tính hash, xác minh chữ ký và chỉ phát lại body cho handler sau khi thành công.
5. Kiểm tra request bị từ chối không chạy handler và pooled buffer được release.

Không dùng `block()` trong reactive filter và không log raw body, shared secret hay signature. Test thiếu memory limit có thể làm attacker tạo request khổng lồ với path bất kỳ để tốn tài nguyên, ngay cả khi HMAC bị từ chối.

### 13.2. Đường đi reactive không được tạo side effect trước xác thực

Một lỗi có thể xảy ra nếu publisher nghiệp vụ được subscribe trước hoặc ngoài chuỗi authentication. Test changed path nên dùng service spy/đếm invocation, bảo đảm `Mono`/`Flux` downstream không được subscribe khi signature mismatch.

Với WebFlux, kiểm thử bằng `WebTestClient` không tự chứng minh gateway đã giữ raw request target; vẫn cần một bài test qua edge thực.

## 14. Kết hợp changed path với key rotation và chống replay

### 14.1. Fresh nonce là điều kiện của bài test

**Sai:**

```text
1. Gửi /42 với nonce=N, HMAC hợp lệ -> accepted.
2. Gửi /43 với nonce=N, HMAC của /42 -> 401.
3. Kết luận path được ký.
```

Bước 2 có thể bị nonce store chặn vì `N` đã dùng, dù verifier bỏ qua path. Kết luận không được chứng minh.

**Đúng:**

```text
1. Case A: ký /42, gửi /42, nonce=N1 -> accepted.
2. Case B: ký /42, gửi /43, nonce=N2 chưa dùng -> signature mismatch.
3. Case C: ký /43, gửi /43, nonce=N3 chưa dùng -> accepted.
4. Test riêng: replay một request hợp lệ bằng chính nonce của nó
   để chứng minh anti-replay.
```

Nếu HMAC verifier reserve nonce **trước** khi xác thực chữ ký, cân nhắc rủi ro attacker chiếm nonce người dùng hợp lệ bằng request giả. Thiết kế phổ biến là kiểm tra chữ ký và timestamp hợp lệ trước khi atomic reserve; dù triển khai thứ tự nào, test phải cô lập nguyên nhân failure.

### 14.2. Key rotation không được làm mất path binding

Trong giai đoạn rotation, service có thể chấp nhận key v1 và v2 theo policy. Với **mỗi key version còn hợp lệ**, lặp lại:

- Ký `/api/orders/42` bằng v1 rồi gửi đến `/43` → reject.
- Ký `/api/orders/42` bằng v2 rồi gửi đến `/43` → reject.
- Re-sign path `/43` với v1/v2 và nonce mới → authentication có thể được chấp nhận khi version tương ứng còn được phép.
- Key bị revoke → từ chối kể cả khi path và signature đúng.

Không cho verifier “thử mọi key” hoặc “thử nhiều canonical path” không có giới hạn để đạt kết quả khớp. `keyId` chọn credential/version theo chính sách server; HMAC phải liên kết cả client identity và request target phù hợp.

### 14.3. Thay path rồi được xác thực không phải lúc nào cũng là lỗi HMAC

Nếu hệ thống **cố ý không ký path** trong contract, một chữ ký có thể vẫn hợp lệ sau khi path đổi. Khi ấy changed path test nên phát hiện **khoảng trống của hợp đồng ký**, và team phải quyết định tăng trường ký hoặc bổ sung biện pháp an toàn theo threat model. Không gắn nhãn “verifier bug” nếu implementation đúng theo một hợp đồng thiếu path; bug có thể nằm ở thiết kế contract.

Ngược lại, nếu server đã từ chối vì **authorization** của path B, test vẫn chưa chứng minh integrity của path. Cần kiểm tra authn stage độc lập.

## 15. Property-based testing và fuzzing path

Ngoài các path cố định, có thể tự động sinh mutation:

```text
given: valid signing input for canonicalTarget A
when:  mutate exactly one path component to obtain B
and:   keep method, headers, body, timestamp, nonce, signature unchanged
then:  if canonical(B) != canonical(A), verification must reject
       unless request is rejected earlier by transport/firewall
```

Đây là một **property có điều kiện**. Nếu canonicalizer quy định hai raw path khác nhau là tương đương, không được kỳ vọng HMAC khác chỉ vì byte trên wire khác. Quan trọng nhất là **không có hai logical target khác nhau cùng được một chữ ký chấp nhận**.

Các mutation hữu ích:

- Đổi một chữ số trong ID hoặc một segment cố định.
- Thêm/bỏ segment, thêm slash cuối, biến thể chữ hoa/thường.
- Percent encoding và double encoding của dấu `/`, dấu `.`.
- Dot segments `.`/`..`, duplicate slashes và semicolon parameters.
- Unicode với biểu diễn normalization khác nhau.
- Context path, gateway prefix và version prefix.
- Query mutation khi hợp đồng ký toàn request target.
- Path rất dài và số segment nhiều để kiểm tra resource limits.

### 15.1. Tách generator, oracle và transport

Một bộ fuzz test có ba phần:

1. **Generator:** sinh path A hợp lệ và path B mutated.
2. **Oracle:** tính canonical bytes của hai path theo hợp đồng; quyết định chúng khác nhau hay tương đương.
3. **Transport runner:** gửi request ký A đến B qua Servlet/WebFlux/gateway.

Khi một test fail, lưu seed và **dữ liệu giả đã làm sạch** để tái lập. Không lưu shared secret production, raw credential hoặc body chứa dữ liệu cá nhân. Với path bị container reject trước verifier, ghi phân loại “rejected by firewall” thay vì gọi “HMAC signature mismatch”.

## 16. Dữ liệu quan sát và kiểm thử không tạo oracle bảo mật

Để chẩn đoán, có thể ghi audit nội bộ:

```json
{
  "event": "hmac.authentication.rejected",
  "request_id": "test-changed-path-17",
  "route_template": "/api/orders/{id}",
  "canonical_contract_version": "hmac-v1",
  "reason_code": "signature_mismatch",
  "http_status": 401
}
```

Không ghi:

- Shared secret hoặc key bytes, kể cả key version cũ.
- Supplied signature hoặc expected HMAC do server tính.
- Canonical string chứa toàn bộ raw URI/query, header và body nhạy cảm.
- Raw `Authorization`, nonce hoặc dữ liệu cá nhân trong `/api/orders/{id}`.
- Raw key ID do client tự gửi như thể đó là verified principal.

Có thể dùng counter `hmac.requests.rejected` với nhãn hữu hạn `stage="authentication"`, `reason="invalid_signature"`, `route="orders_read"`, không dùng raw path hoặc order ID làm metric tag.

**Phân biệt metric và kết luận test:** counter `invalid_signature` tăng là tín hiệu hữu ích, nhưng test phải còn chứng minh request thật đi vào verifier và không chạy service, vì có thể có retry hoặc nhiều filter cùng tăng counter. Trong môi trường production, không công khai reason chi tiết có thể giúp kẻ tấn công phân biệt key lookup từ signature mismatch.

## 17. Sai lầm phổ biến và cách tránh

| Sai lầm | Vì sao test không đáng tin | Cách sửa |
| --- | --- | --- |
| Ký path A, gửi A thành công, rồi dùng lại nonce trên B | B có thể fail vì replay, không vì path | Dùng nonce mới cho case B |
| Gửi path B chưa đăng ký controller | `404` có thể che lỗi HMAC | Dùng hai path cùng route family và positive control |
| Chỉ assert `status != 200` | `403`/`404`/`500` đều có thể bị nhầm | Assert authn outcome và side effects |
| Re-sign path sau khi mutate ở negative test | Không còn kiểm thử integrity | Giữ nguyên signature của path A |
| Dùng `@PathVariable` làm canonical input | Path pattern/decoded value có thể mất raw representation | Dùng request target theo contract |
| Bỏ query khỏi signing contract nhưng tưởng đã bảo vệ query | Query mutation có thể thay nghiệp vụ | Kiểm thử query riêng, điều chỉnh contract |
| Nới lỏng firewall để buộc encoded path trả `401` | Mở thêm bề mặt request smuggling/traversal | Chấp nhận firewall reject sớm, test binding với path hợp lệ |
| Bỏ qua proxy rewrite trong integration test | Chạy local đúng nhưng public API sai | Test edge/service theo trust boundary |
| Tin `X-Original-URI` do client tự khai | Client có thể giả mạo signed target | Ingress sanitize/overwrite, service chỉ tin proxy hợp lệ |
| Chỉ test một phiên bản key | Rotation có thể làm bỏ qua path binding ở fallback | Lặp test v1/v2/revoked |
| Tắt HMAC filter trong `MockMvc` | Request có thể vào handler không cần signature | Bật full security chain |
| So sánh chữ ký bằng `String.equals` và log cả hai | Có thể rò timing/thông tin nhạy cảm | Decode bytes, dùng comparison an toàn và log reason code |
| Kiểm thử path với body JSON bị serialize lại | Hai biến khác nhau khiến nguyên nhân mơ hồ | Giữ đúng raw body bytes khi đổi path |
| Controller có side effect trước verifier | Một request bị reject vẫn có thể thay đổi dữ liệu | Chặn trong security layer trước handler |
| Dùng secret thật và log header khi test | Rủi ro lộ key | Test credential riêng, audit log đã làm sạch |

## 18. Bài thực hành: viết changed path test hoàn chỉnh

Giả sử API `GET /api/orders/{id}` yêu cầu HMAC-SHA256, body rỗng, path/query nằm trong canonical request; các header gồm key ID, timestamp, nonce và signature. Client có quyền `orders:read` cho tài nguyên test 42 và 43. Server chạy sau một gateway có thể đổi prefix `/public/v1` thành `/api`.

Thực hiện:

1. **Viết tài liệu canonical contract:** nêu rõ raw/canonical path, query, method, signed headers, SHA-256 body và timestamp/nonce encoding. Dùng golden vectors với secret giả.
2. **Tạo signer fixture:** trả header HMAC đúng cho một `signedTarget` được truyền vào; không gọi trực tiếp verifier nội bộ để nhận expected signature.
3. **Baseline:** ký `/api/orders/42`, gửi `/api/orders/42`, nonce mới, assert authentication thành công và trả dữ liệu order 42.
4. **Changed path:** ký `/api/orders/42`, gửi `/api/orders/43` với chữ ký và header không đổi, **nonce khác baseline và chưa dùng**. Assert `401`, internal reason signature mismatch trong test-only instrumentation và service không được gọi.
5. **Positive control:** ký lại chính `/api/orders/43` với nonce mới, gửi `/43` và assert được xác thực; nếu fixture có quyền, nhận đúng order 43.
6. **Authorization control:** dùng HMAC hợp lệ cho path 43 nhưng principal thiếu `orders:read`, assert `403` và không nhầm với `401`.
7. **Mutation matrix:** đổi segment, trailing slash, case, percent encoding, duplicate slash và context path; phân loại chính xác signature mismatch hoặc early HTTP/firewall rejection.
8. **Gateway end-to-end:** ký public path, qua proxy rewrite và assert success; giữ chữ ký path A nhưng gửi public path B và assert reject; thử client tự gắn `X-Original-URI` giả.
9. **Key rotation và replay:** lặp changed path với key version còn active trong overlap, reject revoked key, test duplicate nonce tách biệt; kiểm tra nonce store atomic ở nhiều instance.
10. **Quan sát an toàn:** ghi request ID, route template, contract version, reason code; không log secret, raw signature, expected digest, raw nonce hay body.

### Tiêu chí hoàn thành

Một changed path test đạt yêu cầu khi chứng minh được rằng:

- Signature của **target A** không thể xác thực **target B** nếu canonical target khác theo hợp đồng.
- Cả A và B đều là path hợp lệ trong security policy; B có positive control riêng.
- Negative case dùng nonce mới, không dựa vào replay/404/403 làm bằng chứng thay path.
- Verifier từ chối trước controller hoặc business side effect.
- Percent encoding, context path và gateway rewrite được xử lý theo **một hợp đồng canonicalization duy nhất**, với metadata proxy đã được thiết lập tin cậy.
- Chữ ký hợp lệ vẫn phải qua authorization; key rotation và anti-replay không bị bỏ qua để làm test xanh.

**Kết luận:** Changed path test không chỉ là việc sửa một chuỗi URL và chờ `401`. Nó là phép chứng minh rằng HMAC ràng buộc credential với **đúng HTTP resource target mà hệ thống xử lý**, qua cả client signer, gateway/proxy, Spring Security và controller — đồng thời phân biệt rõ lỗi chữ ký, replay, routing và phân quyền.

# Server capability: năng lực thuật toán của server trong xác thực HMAC

## 1. Bài toán: server hỗ trợ thuật toán nào, và client được dùng thuật toán nào?

Trong module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, HTTP client ký request bằng HMAC với shared secret. Canonical request có thể bao gồm method, URI, signed headers, timestamp, nonce và digest của body theo hợp đồng. Verifier chọn đúng credential/key ID, xác minh chữ ký, chống replay bằng timestamp/nonce, rồi tạo authenticated principal; authorization với tenant/action/resource là bước độc lập.

Khi vận hành lâu dài, hệ thống sẽ cần **algorithm agility**: triển khai suite mới, nâng cấp client SDK, thay đổi canonicalization hoặc key-management policy mà không tạo đường **downgrade**. Chẳng hạn server đang dùng HMAC-SHA256 và muốn bổ sung HMAC-SHA512. Việc JVM có primitive `HmacSHA512` **không đồng nghĩa** request nào khai HmacSHA512 cũng được phép xác thực.

**Server capability** mô tả năng lực kỹ thuật và chính sách chấp nhận các *signing suites* mà verifier có thể xử lý. Nó trả lời:

- Server có triển khai đầy đủ parser, canonicalizer, MAC, body digest và replay policy cho suite này chưa?
- JVM/provider/HSM có thực thi primitive tương ứng không?
- Route hoặc gateway có được phép nhận suite đó không?
- Credential cụ thể có key material/version và grant sử dụng suite không?
- Client có thể biết khả năng hỗ trợ qua metadata hoặc provisioning như thế nào?
- Khi V1 bị loại bỏ, làm sao đảm bảo không có node nào tiếp tục chấp nhận V1?

Một client gửi:

~~~http
POST /api/hmac/orders HTTP/1.1
Content-Type: application/json
X-Client-Id: partner-a
X-Key-Id: partner-a-k4
X-Signing-Suite: hmac-v2-sha512
X-Timestamp: 2026-11-28T04:00:00Z
X-Nonce: 665d2d76-baf9-4208-b2fa-5cb4aac118d1
X-Signature: <base64-mac>

{"orderId":"order-102","amount":250000}
~~~

không được chấp nhận chỉ vì client đề nghị V2. Server phải xác minh **suite ID đã khai là lựa chọn duy nhất được cho phép**, sau đó dùng đúng secret và hợp đồng ký của suite đó.

**Mục tiêu bài học:** thiết kế một capability contract có version, an toàn với downgrade, phù hợp Spring Security 6/Java 17, có cơ chế rollout và kiểm thử client–gateway–backend.

## 2. Phân biệt algorithm, signing suite và server capability

| Thành phần | Ví dụ | Định nghĩa |
| --- | --- | --- |
| Primitive | `HmacSHA256`, `HmacSHA512` | Thuật toán MAC ở JCA/JCE |
| Body digest | `SHA-256`, `SHA-512` | Băm raw body bytes theo hợp đồng |
| Canonical contract | `HMAC-REQUEST-V1` | Byte format chứa method/URI/headers/body hash |
| Signing suite | `hmac-v1-sha256` | Bundle thuật toán, canonicalization, encoding và replay |
| Runtime support | JVM có HmacSHA512 | Năng lực kỹ thuật, chưa phải policy |
| Server enabled | Policy cho phép V2 | Điều kiện cấp cao ở môi trường |
| Route allowed | Orders được dùng V2 | Điều kiện ở một endpoint |
| Credential allowed | K4 có secret V2 và grant | Điều kiện gắn với một danh tính |
| Actually accepted | Một request đã qua MAC, timestamp, nonce | Kết quả xác thực thực |

Một suite nên có **ID cố định** và xác định toàn bộ hợp đồng, ví dụ:

~~~yaml
id: hmac-v2-sha512
macAlgorithm: HmacSHA512
bodyDigestAlgorithm: SHA-512
canonicalContract: HMAC-REQUEST-V2
signatureEncoding: BASE64_RFC4648_PADDED
expectedMacBytes: 64
noncePolicy: TIMESTAMP_AND_ATOMIC_CLAIM
~~~

Đây là **đề xuất giao thức minh họa**, không phải chuẩn HMAC-HTTP phổ quát. HMAC-SHA512 không bắt buộc phải dùng SHA-512 cho body digest: liên kết giữa hai thuật toán là lựa chọn của suite, phải được công bố và kiểm thử chính xác.

**Không** coi tất cả tên algorithm `Mac.getAlgorithms()` trong một provider là danh sách được phép trên Internet. Một primitive vẫn tồn tại ở runtime có thể bị cấm bởi security policy hoặc không phù hợp với hợp đồng ứng dụng.

## 3. Mô hình effective capabilities

Một phương pháp dễ kiểm toán là dùng giao của các tập:

\[
S_{\mathrm{effective}}(route, credential)
= S_{\mathrm{runtime}}
\cap S_{\mathrm{deployed}}
\cap S_{\mathrm{global}}
\cap S_{\mathrm{route}}
\cap S_{\mathrm{credential}}
\]

Trong đó:

- `S_runtime`: primitives chạy được trên provider đã chọn, đã qua self-test.
- `S_deployed`: code của suite có ở mọi verifier có thể nhận request.
- `S_global`: allowlist được policy bảo mật hiện hành cho phép.
- `S_route`: suite route/endpoint này hỗ trợ.
- `S_credential`: credential có grant và key material đúng version/suite.

Request chỉ có thể đi tiếp nếu suite khai báo **thuộc giao này**; sau đó vẫn phải xác minh MAC, timestamp, nonce và principal. Tập client tự đề xuất **không mở rộng** bất kỳ tập nào ở trên.

| Nguồn | V1 SHA256 | V2 SHA512 |
| --- | --- | --- |
| JCA runtime | Có | Có |
| Deployed code | Có | Có |
| Global server policy | Có | Có |
| Route payments | Có | Có |
| Credential partner-a-k4 | Có | **Chưa provision** |
| **Được chấp nhận cho K4** | Có | **Không** |

Việc server công bố `V2 supported` có nghĩa năng lực tổng quát đã sẵn sàng, **không** đồng nghĩa mọi credential có quyền dùng V2.

### Cần phân biệt sáu trạng thái

- `implemented`: có code canonicalizer/verifier.
- `installed`: image/container có provider thích hợp.
- `enabled`: policy môi trường cho phép.
- `advertised`: metadata cho client thấy năng lực.
- `provisioned`: credential có key/grant phù hợp.
- `accepted`: một request cụ thể vượt qua authentication.

Đo lường `accepted` không thể suy từ `advertised`; muốn chứng minh suite đã bị thu hồi, phải thử gửi request ký hợp lệ dưới suite đó và xác nhận bị từ chối.

## 4. Capability discovery không phải cơ chế cấp quyền

Client có thể biết suite server hỗ trợ qua:

1. **Out-of-band onboarding/provisioning:** thông báo suite, key ID/secret và thời gian cutover khi cấp credential.
2. **Capabilities endpoint:** công khai metadata tổng quát hoặc metadata credential-specific qua kênh quản trị đã xác thực.
3. **Versioned SDK/API documentation:** mô tả suite bắt buộc cho API version và mốc deprecation.

Ví dụ một endpoint riêng của sản phẩm:

~~~http
GET /.well-known/example-hmac-capabilities HTTP/1.1
Host: api.example.test
Accept: application/json
~~~

~~~json
{
  "schemaVersion": 1,
  "revision": "r17",
  "issuedAt": "2026-11-28T04:00:00Z",
  "expiresAt": "2026-11-28T04:05:00Z",
  "suites": [
    {
      "id": "hmac-v1-sha256",
      "canonicalContract": "HMAC-REQUEST-V1",
      "status": "deprecated",
      "verificationEndsAt": "2027-03-31T00:00:00Z"
    },
    {
      "id": "hmac-v2-sha512",
      "canonicalContract": "HMAC-REQUEST-V2",
      "status": "preferred"
    }
  ]
}
~~~

Đây là **path/schema minh họa**, không phải một well-known chuẩn bắt buộc trong mọi ứng dụng HMAC. Một response có thể đi kèm `ETag` và `Cache-Control: public, max-age=300` nếu chính sách cho phép.

**Discovery chỉ gợi ý tương thích**, không trả secret, không xác nhận key ID của người lạ có tồn tại và không tuyên bố một client bất kỳ đã được cấp V2. Per-credential grants chỉ nên trả qua management channel có xác thực/authorization hoặc tài liệu provisioning riêng.

### Bảo vệ tính xác thực metadata

Metadata cần HTTPS với kiểm tra certificate đúng. Nếu phát tán ngoại tuyến, qua file/CDN nằm ngoài trust boundary hoặc dùng làm chỉ thị minimum suite lâu dài, có thể cần **metadata signature** và expiry do server policy định nghĩa.

`ETag` là cache validator, **không phải cryptographic signature**. `max-age` chỉ kiểm soát cache HTTP, không chứng minh key đang ACTIVE hay registry đã nhận revocation. Nếu client đã có minimum suite V2 đáng tin, không tự hạ xuống V1 chỉ vì metadata cũ/giả hoặc request V2 nhận 401/503.

## 5. Quy tắc anti-downgrade trong thuật toán HMAC

**Downgrade** là tình huống một request được xác minh bởi suite yếu hơn policy đã lựa chọn, thường do fallback, metadata stale, version header không được ký hoặc verifier thử nhiều thuật toán.

Các yêu cầu bảo mật:

- Client khai **một** suite ID chính xác; verifier không dùng algorithm name tùy ý làm tham số trực tiếp cho `Mac.getInstance`.
- Header `X-Signing-Suite` phải xuất hiện đúng một lần, không chấp nhận duplicate/case ambiguity/comma list.
- Suite ID phải được **ký trong canonical request**.
- Chọn một canonicalizer và một secret/key ID đúng mapping; không `try all supported algorithms`.
- Key V1 bị REVOKED hoặc policy V1 disabled thì MAC V1 đúng cũng phải bị từ chối.
- Client không fallback tự động V2→V1 sau 401/503/timeout.
- Nếu server còn chấp nhận V1 trong overlap có chủ đích, ghi rõ hạn cuối và tập credential nào được phép.
- Secret material của V1/V2 nên độc lập hoặc được derive bằng KDF có domain separation được review.

Ví dụ phản mẫu:

~~~java
// SAI: client điều khiển tên primitive, không qua allowlist.
Mac mac = Mac.getInstance(request.getHeader("X-Mac-Algorithm"));

// SAI: một request được thử nhiều suite đến khi khớp.
for (String algorithm : installedAlgorithms) {
    if (verifyWith(algorithm, request)) {
        return authenticatedPrincipal;
    }
}
~~~

Ngay cả khi cả V1 và V2 đều sử dụng primitives mật mã mạnh, fallback vẫn có thể tạo **algorithm confusion**: signature được diễn giải dưới hợp đồng ký khác và bỏ sót những trường đã ký cần thiết.

### Khi nào V1 hợp lệ trong migration?

Nếu policy và credential thực sự cho phép cả V1/V2, client dùng V1 có thể còn được chấp nhận. `preferred=V2` trong discovery **không** đồng nghĩa `V1 disabled`. Muốn buộc V2, cập nhật **effective server policy** và credential grants, đồng thời bảo đảm mọi gateway/verifier chặn V1.

## 6. Đưa suite ID vào canonical bytes

Một hợp đồng V2 minh họa:

~~~text
REQUEST-SIGNATURE
hmac-v2-sha512
POST
/api/hmac/orders?currency=VND
application/json
partner-a
partner-a-k4
tenant-a
2026-11-28T04:00:00Z
665d2d76-baf9-4208-b2fa-5cb4aac118d1
<lowercase-sha512-hex-of-raw-body>
~~~

Quy tắc ví dụ: các dòng UTF-8 phân cách bằng `LF (0x0A)`, không có LF cuối, `X-Signing-Suite` nằm trong chữ ký thông qua dòng thứ hai. Dòng `REQUEST-SIGNATURE` là domain separator. Body hash tính trên **raw body bytes sau HTTP transfer decoding tại trust boundary đã công bố**, không phải body đã parse rồi serialize lại.

Hai thuộc tính cần version độc lập về mặt triển khai:

- **Primitive algorithm:** `HmacSHA256` ↔ `HmacSHA512` làm thay MAC algorithm/length.
- **Canonicalization contract:** V1 ↔ V2 có thể đổi thứ tự/format signed headers, URI hoặc body digest.

Dùng suite ID để liên kết **một tổ hợp đã kiểm thử**. Không để client phối hợp tự do các headers `X-Mac-Algorithm`, `X-Canonical-Algorithm`, `X-Body-Digest` nếu server không có ma trận hợp lệ rõ.

### Vì sao cần ký timestamp/nonce/key ID?

- Nếu timestamp không được ký, attacker có thể thay mốc thời gian để kéo dài thời hạn request.
- Nếu nonce không được ký, attacker có thể đổi nonce để né replay store.
- Nếu key ID không được ràng buộc, identity/key version confusion có thể xảy ra.
- Nếu body digest chỉ tin header nhưng không kiểm tra body bytes thực, attacker có thể thay body mà signature header vẫn đúng.
- Nếu suite ID không được ký, attacker có thể sửa selector và khai thác ambiguity giữa hai verifier.

Sự tồn tại của digest trong canonical bytes **không tự chứng minh quyền tenant**: authorization là bước độc lập sau authentication.

## 7. Runtime crypto support và startup readiness

Java 17 JCA/JCE có thể được dùng để kiểm tra primitive:

~~~java
import javax.crypto.Mac;
import java.security.GeneralSecurityException;

final class CryptoCapabilityProbe {
    static boolean available(String jcaName) {
        try {
            return Mac.getInstance(jcaName)
                .getMacLength() > 0;
        } catch (GeneralSecurityException ex) {
            return false;
        }
    }
}
~~~

Nhưng `getInstance` **chưa đủ** để coi suite sẵn sàng production. Startup/readiness cần kiểm tra:

- Algorithm `HmacSHA256`/`HmacSHA512` có provider phù hợp.
- `Mac.init` với test key thành công và known-answer vector chính xác.
- Body digest provider `SHA-256`/`SHA-512` hoạt động đúng.
- JCA provider/HSM/FIPS deployment policy cho phép operations đó.
- Suite canonicalizer/HTTP adapters cùng version đã được deploy.
- Credential store có đúng loại key material hoặc HSM handle.
- Mọi pod/gateway nhận route V2 đều có khả năng V2, không chỉ một pod.
- Fail readiness hoặc route restriction nếu một suite **bắt buộc** không được thực thi.

Không bật `HmacSHA1`, `HmacMD5` chỉ vì provider có chúng; một ứng dụng mới nên chọn suites đã được security review và policy approve. HMAC-SHA256/SHA512 là ví dụ hợp lý, nhưng đánh giá còn phụ thuộc threat model và yêu cầu tuân thủ.

## 8. Java 17: registry suite bằng enum hữu hạn

Để không nhận tên thuật toán tùy tiện từ HTTP, thiết kế một allowlist đóng:

~~~java
import java.util.Arrays;

enum SigningSuite {
    V1_SHA256("hmac-v1-sha256",
        "HmacSHA256", "SHA-256", 32, "HMAC-REQUEST-V1"),
    V2_SHA512("hmac-v2-sha512",
        "HmacSHA512", "SHA-512", 64, "HMAC-REQUEST-V2");

    private final String wireId;
    private final String jcaMac;
    private final String bodyDigest;
    private final int macLength;
    private final String canonicalContract;

    SigningSuite(
            String wireId,
            String jcaMac,
            String bodyDigest,
            int macLength,
            String canonicalContract) {
        this.wireId = wireId;
        this.jcaMac = jcaMac;
        this.bodyDigest = bodyDigest;
        this.macLength = macLength;
        this.canonicalContract = canonicalContract;
    }

    String wireId() { return wireId; }
    String jcaMac() { return jcaMac; }
    String bodyDigest() { return bodyDigest; }
    int macLength() { return macLength; }

    static SigningSuite parseExactly(String input) {
        return Arrays.stream(values())
            .filter(s -> s.wireId.equals(input))
            .findFirst()
            .orElse(null);
    }
}
~~~

Với V1 HMAC-SHA256, MAC bytes length = 32, Base64 chuẩn padded thường dài 44 ký tự. V2 HMAC-SHA512 dài 64 bytes, Base64 padded dài 88 ký tự. Kiểm tra **decoded length** và encoding canonical, không chấp nhận signature bị truncate.

Dùng `enum` giúp client không thể yêu cầu `hmac-none`, `HMAC-V2-SHA512` viết sai case hoặc thuật toán bất ngờ mà vẫn được chọn. API phải có quy tắc exact match, không âm thầm `trim`/casefold selector nếu hợp đồng không cho phép.

## 9. Credential policy: runtime support không phải grant

~~~java
import java.util.Set;

record CredentialPolicy(
    String credentialId,
    String ownerClientId,
    boolean active,
    Set<SigningSuite> allowedSuites
) {}

final class EffectiveSuitePolicy {
    private final Set<SigningSuite> deployed;
    private final Set<SigningSuite> globallyAllowed;

    EffectiveSuitePolicy(
            Set<SigningSuite> deployed,
            Set<SigningSuite> globallyAllowed) {
        this.deployed = Set.copyOf(deployed);
        this.globallyAllowed = Set.copyOf(globallyAllowed);
    }

    boolean permits(
            SigningSuite candidate,
            Set<SigningSuite> routeAllowed,
            CredentialPolicy credential) {
        return candidate != null
            && credential != null
            && credential.active()
            && deployed.contains(candidate)
            && globallyAllowed.contains(candidate)
            && routeAllowed.contains(candidate)
            && credential.allowedSuites().contains(candidate);
    }
}
~~~

Các `Set` này phải đến từ **server configuration và credential registry đã tin cậy**, không phải body/header client. Cần kiểm tra thêm client/tenant enabled, key status/expiry, đúng key material và trạng thái registry freshness theo yêu cầu revoke.

Key rotation thay `K3→K4` nhưng có thể giữ suite V1; algorithm migration thay primitive/canonical suite nhưng có thể đồng thời provision K4. Đây là **hai trục khác nhau**: không nhập nhằng key version với signing suite.

## 10. Capability endpoint và cache policy

Một metadata document nên có:

| Field | Ý nghĩa | Kiểm soát |
| --- | --- | --- |
| `schemaVersion` | Version format discovery | Parser allowlist |
| `revision` | Revision server policy/rollout | Không xem là MAC/chữ ký |
| `suites[]` | Suite IDs được quảng bá | Server-defined constants |
| `status` | supported/preferred/deprecated | Có nghĩa rõ, không cấp key grants |
| `issuedAt/expiresAt` | Metadata freshness | TLS/signed distribution nếu cần |
| `verificationEndsAt` | Mốc ngừng verify suite cũ | Policy cần enforce, không chỉ hiển thị |
| `ETag` | HTTP caching | Không phải security credential |
| `documentation` | Tham chiếu canonical contract | Tài liệu có version |

**Lưu ý thứ tự rollout:** chỉ quảng bá V2 ở phạm vi mọi verifier đã hỗ trợ V2, hoặc mô tả chính xác route/cohort/region được hỗ trợ. Nếu Gateway A hỗ trợ V2, B chỉ V1 và load balancer phân phối ngẫu nhiên, response `V2 supported` toàn cục là sai với trải nghiệm client.

Caching:

- Metadata cache 5 phút có thể giúp giảm request discovery.
- Key revoke hoặc emergency disable có thể cần hiệu lực **nhanh hơn** 5 phút.
- Vì vậy verifier không lấy quyết định từ metadata cache của client.
- Khi thay đổi policy, invalidate server-side policy cache và kiểm soát convergence.
- Client đã có minimum suite V2 không fallback V1 chỉ vì discovery lỗi.

Một public endpoint không nên tiết lộ key ID/tenant/client cụ thể được provision suite nào. Khi cần private capability, tạo management endpoint **có xác thực/authorization**.

## 11. Các trường hợp lỗi và HTTP response

| Tình huống | Kết luận nội bộ | Public status tham khảo |
| --- | --- | --- |
| Suite ID không được nhận diện | `UNSUPPORTED_SUITE` | 400/401 theo contract |
| Route không cho phép suite | `ROUTE_SUITE_DENIED` | 400/401 theo contract |
| Credential chưa provision suite | `SUITE_NOT_PROVISIONED` | 401 chung |
| MAC sai dưới suite được phép | `SIGNATURE_MISMATCH` | 401 chung |
| Suite V1 bị disabled cho credential | `SUITE_POLICY_DENIED` | 401 chung |
| Key revoked/expired | `CREDENTIAL_INACTIVE` | 401 chung |
| Timestamp ngoài window | `TIMESTAMP_REJECTED` | 401 chung |
| Nonce đã claim | `REPLAY_DETECTED` | 401 chung |
| Secret/registry/nonce store unavailable | `AUTH_DEPENDENCY_UNAVAILABLE` | 503, fail closed |
| Runtime/HSM không chạy suite bắt buộc | `CRYPTO_RUNTIME_UNAVAILABLE` | 503 và chặn readiness |
| HMAC đúng nhưng không có quyền tenant | `ACCESS_DENIED` | 403/404 theo policy |

Một API có thể dùng generic public response:

~~~http
HTTP/1.1 401 Unauthorized
Content-Type: application/problem+json
Cache-Control: no-store
WWW-Authenticate: HMAC realm="api"

{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required or invalid.",
  "code": "AUTHENTICATION_FAILED"
}
~~~

`WWW-Authenticate: HMAC realm="api"` chỉ phù hợp khi ứng dụng **đã công bố scheme HMAC đó**, không phải một challenge tự có của Spring Security. Public response có thể gom nhiều failure reasons nhằm giảm key/credential enumeration oracle; audit nội bộ giữ reason enum được kiểm soát.

**Không dùng HTTP 426 một cách tùy tiện để yêu cầu chuyển HMAC-SHA512**: 426 liên quan nâng cấp giao thức HTTP, không phải thay signing algorithm riêng của ứng dụng.

## 12. Pipeline server: suite candidate → MAC → nonce → authorization

~~~mermaid
flowchart TD
    A["HTTP request + suite/key headers"] --> B["Bounded parse + reject duplicate"]
    B --> C{"Suite nằm trong allowlist?"}
    C -->|Không| X["Reject, không default"]
    C -->|Có| D["Lookup exact credential key ID"]
    D --> E{"Global/route/credential policy cho phép?"}
    E -->|Không| X
    E -->|Có| F["Dựng canonical bytes theo DUY NHẤT suite này"]
    F --> G{"HMAC đúng với đúng suite secret?"}
    G -->|Không| X
    G -->|Có| H["Timestamp window và atomic nonce claim"]
    H -->|REPLAY| R["Reject replay"]
    H -->|UNKNOWN| U["Fail closed"]
    H -->|FIRST_USE| I["Tạo principal từ registry"]
    I --> J{"Authorization tenant/action/resource?"}
    J -->|Deny| K["403/404"]
    J -->|Allow| L["Controller + business"]
~~~

**Không claim nonce trước khi MAC đúng**, vì người không biết shared secret có thể đoán/quan sát nonce và chiếm trước slot (**nonce poisoning**). **Không** cho business chạy trước khi nonce claim thành công.

Nếu dùng `(credentialId, nonce)` làm replay key, cùng nonce được bảo vệ **xuyên suite** của cùng credential. Nếu dùng `(credentialId, suiteId, nonce)`, phải có threat model cụ thể vì điều đó tạo những namespace replay khác nhau. Nếu key rotation tạo credential ID mới nhưng sản phẩm cần chống reuse theo client xuyên key, phải lựa chọn scope phù hợp từ **principal/registry đáng tin**, không dựa tenant client khai.

Suite là **đầu vào chưa tin cậy trước khi MAC verified**, chỉ được dùng làm candidate selection qua enum allowlist. Nó trở thành phần của authenticated evidence sau khi MAC đã ký suite ID và các bytes có liên quan.

## 13. Java 17: chọn một suite và một secret để verify

Đoạn code sau minh họa **đường MAC-only**. Adapter phải nhận HTTP request thực, chặn duplicate headers, body over-limit, chuẩn hóa raw URI theo contract và lấy các signed values trước khi tạo `HmacProof`.

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Set;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

record HmacProof(
    String suiteId, String keyId,
    String method, String rawTarget,
    String contentType,
    String clientId, String targetTenant,
    String timestamp, String nonce,
    byte[] rawBody, String signatureBase64
) {}

interface CredentialDirectory {
    CredentialPolicy findExact(String keyId);
    byte[] secretFor(String credentialId, SigningSuite suite);
}

final class StrictSuiteMacVerifier {
    private final CredentialDirectory directory;
    private final EffectiveSuitePolicy suitePolicy;
    private final Set<SigningSuite> routeSuites;

    StrictSuiteMacVerifier(
            CredentialDirectory directory,
            EffectiveSuitePolicy suitePolicy,
            Set<SigningSuite> routeSuites) {
        this.directory = directory;
        this.suitePolicy = suitePolicy;
        this.routeSuites = Set.copyOf(routeSuites);
    }

    boolean verifyMac(HmacProof proof) {
        // Các field bắt buộc được adapter kiểm tra format,
        // không null và đến từ chính HTTP request.
        SigningSuite suite =
            SigningSuite.parseExactly(proof.suiteId());
        if (suite == null) return false;

        CredentialPolicy c =
            directory.findExact(proof.keyId());
        if (!suitePolicy.permits(suite, routeSuites, c)) {
            return false;
        }
        if (!c.ownerClientId().equals(proof.clientId())) {
            return false;
        }

        // Phải tìm đúng key material đã provision cho suite.
        byte[] key = directory.secretFor(
            c.credentialId(), suite);
        if (key == null || key.length == 0) {
            return false;
        }

        byte[] canonical = canonical(proof, suite);
        byte[] expected;
        try {
            Mac mac = Mac.getInstance(suite.jcaMac());
            mac.init(new SecretKeySpec(
                key, suite.jcaMac()));
            expected = mac.doFinal(canonical);
        } catch (GeneralSecurityException ex) {
            // Đây là lỗi runtime, không phải sai secret.
            throw new IllegalStateException(
                "crypto_runtime_unavailable", ex);
        }

        // Reject signature sai format, sai độ dài và
        // canonical Base64; không tự thử hex/Base64url.
        byte[] supplied;
        try {
            supplied = Base64.getDecoder().decode(
                proof.signatureBase64());
        } catch (IllegalArgumentException ex) {
            return false;
        }

        if (supplied.length != suite.macLength()) {
            return false;
        }
        if (!Base64.getEncoder().encodeToString(supplied)
                .equals(proof.signatureBase64())) {
            return false;
        }

        return MessageDigest.isEqual(expected, supplied);
    }

    private static byte[] canonical(
            HmacProof p, SigningSuite suite) {
        try {
            byte[] digest = MessageDigest.getInstance(
                suite.bodyDigest()).digest(p.rawBody());

            String canonicalText = String.join("\n",
                "REQUEST-SIGNATURE",
                suite.wireId(),
                p.method(),
                p.rawTarget(),
                p.contentType(),
                p.clientId(),
                p.keyId(),
                p.targetTenant(),
                p.timestamp(),
                p.nonce(),
                HexFormat.of().formatHex(digest));
            return canonicalText.getBytes(
                StandardCharsets.UTF_8);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(
                "digest_runtime_unavailable", ex);
        }
    }
}
~~~

Mã ví dụ nhận các chuỗi đã được adapter kiểm soát và chỉ xây **canonical profile minh họa**. Nó **chưa tự xác minh** key ACTIVE freshness, tenant status, timestamp window, atomic nonce, proxy trust boundary hay body-size limit; `CredentialPolicy.active` chỉ là một phần kiểm tra. Để production-safe, bổ sung:

1. Parse đúng một `X-Signing-Suite` và một `X-Key-Id`, từ chối header duplicate/case ambiguity.
2. Ràng buộc method/URI/Content-Type/tenant, timestamp/nonce vào **raw HTTP bytes đã ký**, có grammar rõ.
3. Enforce body-size limit **trước** tạo array, không tin mỗi `Content-Length`.
4. Lookup đúng key ID, trạng thái key/client/tenant có freshness phù hợp.
5. Tính MAC với **một** suite/key; không fallback nếu thất bại.
6. Sau MAC đúng mới kiểm tra timestamp, atomic nonce claim và tạo principal.
7. Sau authentication, vẫn kiểm tra authorization tenant/action/resource.
8. Với HSM, thay `byte[]` bằng key handle/provider API phù hợp, không bắt buộc xuất secret.

**Không coi `boolean verifyMac` là authentication hoàn chỉnh**. Đây là phần cốt lõi để kiểm tra signature suite selection; hệ thống cần một pipeline xác thực đầy đủ như mục 12.

## 14. Spring Security 6: server capability ở đâu?

Ở Spring MVC/Servlet, triển khai bằng `SecurityFilterChain`, `OncePerRequestFilter` và `AuthenticationManager/AuthenticationProvider`:

~~~text
HTTP request
  -> HMAC route matcher
  -> bounded raw body capture
  -> parse suite/key ID, strict signed-header validation
  -> AuthenticationManager
       -> provider kiểm tra server/route/credential suite policy
       -> one canonicalizer + one HMAC verifier
       -> timestamp + atomic nonce claim
       -> trusted authenticated principal
  -> AuthorizationManager (tenant/action/resource)
  -> Controller / business
~~~

Pseudocode provider:

~~~java
Authentication authenticateHmac(HmacAttempt attempt) {
    SigningSuite suite =
        SigningSuite.parseExactly(attempt.suiteId());
    CredentialPolicy credential =
        registry.findExact(attempt.keyId());

    if (!policy.permits(
            suite, allowedForRoute, credential)) {
        throw new BadCredentialsException(
            "authentication_failed");
    }

    verifyOneSuiteOrThrow(attempt, credential, suite);
    validateTimestamp(attempt.signedTimestamp(), clock);

    // Chỉ ghi nonce SAU MAC hợp lệ.
    nonceStore.claimOrReject(
        credential.credentialId(), attempt.nonce());

    return trustedAuthenticationFromRegistry(credential);
}
~~~

Đây là **pseudocode**: `HmacAttempt`, registry, policy, nonce store, error handler và AuthenticationProvider interface do dự án xây. Nếu filter chạy trước `ExceptionTranslationFilter`, cần `AuthenticationEntryPoint` để map `AuthenticationException` thành response. `@RestControllerAdvice` không tự bắt mọi lỗi ném trước `DispatcherServlet`.

**Không ghi “HMAC valid” khi MAC mới khớp nhưng nonce chưa claim**. Khi replay store unavailable, bắt buộc fail closed và không tạo principal.

### Spring WebFlux

WebFlux dùng `SecurityWebFilterChain`, `ReactiveAuthenticationManager` và `ReactiveSecurityContextHolder`. Body là `Flux<DataBuffer>`: capture có giới hạn, hash raw bytes đúng suite, release pooled buffers khi complete/error/cancel và replay cho downstream. Không gọi Redis/vault blocking trên event loop hoặc tạo `onErrorResume` fallback từ V2 sang V1.

## 15. Rollout V1→V2 theo từng pha an toàn

Server capability migration cần phối hợp **server code, runtime provider, route policy, key provisioning, SDK và gateway**.

| Pha | Hạ tầng | Credential/client | Exit criteria |
| --- | --- | --- | --- |
| 0: baseline | V1 enabled | K3/V1 ACTIVE | Golden V1 + replay regression PASS |
| 1: deploy V2 code | V2 implemented, chưa advertise | Client vẫn dùng V1 | Provider self-test, canonical V2 vectors PASS |
| 2: canary | V2 enabled trên route/cohort kiểm soát | K4/V2 provision cho canary | V2 positive, negative downgrade, authz PASS |
| 3: dual support | V1 + V2 có deadline | Migrating clients giữ hai key grants có thời hạn | Mọi gateway/cohort hỗ trợ đúng |
| 4: prefer V2 | Advertise V2 preferred, V1 deprecated | Client SDK mới chọn V2 | Telemetry về V1 giảm |
| 5: enforce V2 | V1 denied cho credentials đã migrate | K3 V1 revoked/disabled | MAC V1 đúng vẫn bị từ chối |
| 6: retire V1 | Loại khỏi verifier khi hết overlap | Clients chỉ dùng V2 | Không có V1 accepted ở region nào |

Trình tự cần giữ:

1. Triển khai các verifier/proxy **trước** khi quảng bá V2.
2. Provision key/grant suite V2 **trước** khi client được yêu cầu ký V2.
3. Test V2 với signer độc lập, nonce store và authorization thật.
4. Dùng allowlist chính sách để bật có điều kiện, không bật cho mọi client chỉ vì runtime có provider.
5. Có deprecation deadline và thông báo chuyển đổi.
6. Chuyển từ **preferred** sang **required** bằng policy change ở verifier, không chỉ metadata.
7. Đảm bảo rollback code không **âm thầm hồi sinh** suite/key đã bị revoke.

### Rollback policy là quyết định bảo mật

Sau khi V1 bị disable do vulnerability, rollback release không được tự kích hoạt lại V1 vì config cũ. Nếu cần khôi phục V1 phải có phê duyệt, threat assessment và giới hạn thời gian; nếu không đáp ứng minimum security requirement, phải giữ deny dù gây lỗi tương thích ở client cũ.

## 16. Capability consistency qua gateway, region và load balancer

~~~mermaid
flowchart LR
    C["Clients V1/V2"] --> L["Load balancer"]
    L --> G1["Gateway A"]
    L --> G2["Gateway B"]
    G1 --> V1["Verifier A"]
    G2 --> V2["Verifier B"]
    V1 --> R[("Shared nonce store")]
    V2 --> R
    V1 --> P["Backend + authorization"]
    V2 --> P
    M["Capabilities metadata"] -. "Advertises scoped support" .-> C
~~~

Nếu Gateway A đã hỗ trợ V2 nhưng Gateway B chưa hỗ trợ, công bố “V2 supported globally” là **sai** khi client có thể đi vào B ngẫu nhiên.

Các cách kiểm soát:

- Rollout code V2 tới mọi verifier trước khi advertise.
- Route V2 tới cohort/region đã có capability và ghi rõ scope.
- Chặn readiness trên pod không chạy provider/canonicalizer cần thiết.
- Không auto-fallback server khi pod không hỗ trợ suite.
- Test failover và retry qua gateway khác.
- Theo dõi per-region suite policy revision và accepted requests.

Nếu HMAC verify tại gateway rồi backend nhận principal, backend phải kiểm tra mTLS/peer identity hoặc signed internal assertion với issuer, audience, expiry, method/URI và body digest binding. Không tin `X-Authenticated-Client` từ Internet. Nếu gateway claim nonce client, backend **không claim lại chính nonce trên cùng key**; dùng assertion `jti`/internal replay namespace riêng nếu cần.

### Canonicalization qua proxy

V1 và V2 có thể khác cách xử lý query, signed Host hoặc body digest. Khi proxy rewrite `/public/orders` → `/internal/orders`, contract phải xác định raw target ở **điểm verify**. Một endpoint backend dùng `getRequestURI()` sau rewrite không tự biết raw target client ký ban đầu; metadata gốc chỉ được tin từ gateway đã xác thực, không từ `X-Original-URI` client tự khai.

Test từng suite cho duplicate query, `%2F`/`%2f`, `+`/`%20`, Content-Type, gzip, HTTP/1.1↔HTTP/2 và header normalization.

## 17. Key lifecycle, revocation và capability migration

Algorithm migration không thay thế **credential lifecycle**. Một credential có thể đang:

- `ACTIVE` và chỉ cho V1.
- `ACTIVE`, grant cả V1+V2 trong overlap.
- `ACTIVE`, bắt buộc V2; V1 bị deny.
- `EXPIRED`, `REVOKED` hoặc client `DISABLED`: không suite nào được chấp nhận.

Một test matrix:

| Key/policy | Signature | Kết quả |
| --- | --- | --- |
| K4 ACTIVE, V2 only | MAC V2 với secret K4/V2 | Pass nếu timestamp/nonce mới |
| K4 ACTIVE, V2 only | MAC V1 đúng với secret cũ | Reject bởi policy |
| K4 ACTIVE, V2 only | MAC V2 bằng K3/V2 secret | Reject MAC/key mismatch |
| K3 ACTIVE, V1 overlap | MAC V1 đúng | Pass chỉ trong thời hạn |
| K3 REVOKED | MAC V1 đúng bằng K3 | Reject dù MAC toán học đúng |
| K4 ACTIVE nhưng secret manager timeout | Bất kỳ | Fail closed; không dùng default secret |
| Client owner disabled | MAC V2 đúng | Reject theo client state |
| Tenant target không có grant | MAC V2, nonce mới | Authentication có thể pass; authorization deny |

**Không thử secret cũ sau khi MAC sai**: `X-Key-Id` phải tra đúng secret version. Khi rotation, key ID nên không tái sử dụng cho một secret khác. Nếu provision nhiều secrets trong một credential, mapping suite-to-key phải rõ và được review.

Nếu cùng request được ký lại dưới suite khác, nonce scope phải được chọn phù hợp với threat model; không mở namespace mới theo suite một cách tự phát.

## 18. Khả năng thu hồi khẩn cấp một suite

Một tình huống: V1 canonicalizer vô tình không ký một signed header quan trọng. HMAC primitive vẫn mạnh nhưng protocol có lỗi integrity. Cần khả năng **vô hiệu hóa** V1 ở verifier:

1. Xác định client/route/region bị ảnh hưởng.
2. Thay global/route/credential policy để deny V1.
3. Phân phối policy revision tới verifier; áp hạn mức freshness.
4. Kiểm thử một request **có MAC V1 hợp lệ** nhưng bị từ chối sau policy update.
5. Kiểm thử V2 vẫn pass khi credential V2 provision và nonce mới.
6. Thu hồi/rotate key V1 nếu cần.
7. Sửa capability metadata, purge cache/ETag nếu policy yêu cầu.
8. Giám sát mọi gateway/region; alert nếu còn V1 accepted.
9. Rollback application không được tự mở lại suite V1 đã deny.

Một response discovery ngừng hiển thị V1 **không chứng minh** V1 đã bị chặn ở verifier. Tương tự, event revocation được gửi không chứng minh mọi cache đã cập nhật; cần probes và deadline an toàn.

## 19. Monitoring: nhận biết lỗi suite và tiến độ rollout

Các metric logic có thể có:

| Metric | Nhãn hữu hạn | Ý nghĩa |
| --- | --- | --- |
| `hmac.authentication.attempts` | `suite`, `route`, `result`, `reason` | Request HMAC theo suite/outcome |
| `hmac.suite.policy.denied` | `suite`, `route`, `reason` | Suite bị effective policy từ chối |
| `hmac.crypto.selftest` | `suite`, `status` | Provider readiness |
| `hmac.capability.policy_revision` | `region`, `revision_group` | Độ hội tụ của rollout |
| `hmac.credential.provisioning` | `suite`, `stage` | Client đã được cấp key V2 chưa |
| `hmac.replay.claim.result` | `outcome` | Nonce first-use/replay/unknown |
| `hmac.authentication.duration` | `route`, `result` | Chi phí verifier theo traffic |

Dùng `suite` từ enum allowlist, `route` từ route group, không dùng nguyên suite header lạ. Không đặt key ID, client ID, tenant ID, nonce, raw path, signature hoặc secret vào metric labels.

Theo dõi:

- Tỷ lệ accepted V1/V2 và mức giảm traffic V1.
- Số `SUITE_NOT_PROVISIONED` khi client migrate.
- Intermittent 401/503 theo gateway sau rollout V2.
- Crypto self-test failures và pod readiness.
- Key/policy revision stale sau emergency disable.
- Replay spikes, nonce store latency khi nhiều suite cùng active.
- Signature mismatch tăng do canonicalization/version drift.
- HMAC valid nhưng authorization deny: vấn đề quyền, **không phải suite support**.

**Không** ghi metric `component="raw_target"` chỉ vì MAC mismatch; muốn xác định thành phần sai cần test vectors/diagnostics có ground truth. Public error nên tránh tạo oracle về key/grant nội bộ.

## 20. Golden vectors và contract testing qua nhiều SDK

Mỗi suite cần một bộ conformance fixtures độc lập:

| Test artifact | Input | Expected |
| --- | --- | --- |
| Canonicalization | Method/raw URI/headers/body bytes | **Exact canonical UTF-8 bytes** |
| Body digest | Raw body bytes | Exact SHA-256/SHA-512 digest |
| HMAC primitive | Test secret + message | MAC bytes đã soát độc lập |
| Wire encoding | MAC bytes | Base64 canonical có padding |
| HTTP verification | Signed request + registry/Clock/nonce fixture | Pass/reject và internal reason |
| Gateway E2E | Signed request qua proxy thực | Đúng signature/identity/nonce tại trust boundary |

Một vector primitive HMAC-SHA256 được dùng rộng rãi: key 20 bytes `0x0b` và message ASCII `Hi There` cho expected hex:

~~~text
b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7
~~~

Đây là **primitive test**, không phải signature V1 của HTTP request minh họa. V2 HmacSHA512 cần expected MAC khác, được tính và đối chiếu bởi implementation độc lập; không tự tạo expected values bằng chính hàm đang kiểm tra.

### Những biến thể cần kiểm thử

- Cùng raw body nhưng phân chia thành nhiều chunks → cùng digest.
- Query key order, duplicate query, `%2F`, `+`, raw path qua gateway.
- Header name case, signed header OWS, duplicate headers.
- Body JSON whitespace, Unicode, Content-Encoding gzip và bytes rỗng.
- Thay `X-Signing-Suite` nhưng giữ signature → reject.
- Đúng suite nhưng dùng wrong secret/key ID → reject.
- Nonce/timestamp tampering → HMAC mismatch.
- V1 disabled, MAC V1 đúng → reject policy.
- HMAC đúng nhưng tenant không có grant → 403/404 authorization.

Client SDK có thể dùng Java, Go, Python, Node.js; mỗi implementation cần chạy **cùng golden fixtures**, không chỉ roundtrip với một server có chung thư viện canonicalizer.

## 21. JUnit 5: chính sách effective capability

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.EnumSet;
import java.util.Set;
import org.junit.jupiter.api.Test;

class EffectiveSuitePolicyTest {

    private final EffectiveSuitePolicy policy =
        new EffectiveSuitePolicy(
            EnumSet.allOf(SigningSuite.class),
            EnumSet.allOf(SigningSuite.class));

    @Test
    void runtimeSupportDoesNotGrantSuiteToCredential() {
        CredentialPolicy c = new CredentialPolicy(
            "partner-a-k4", "partner-a", true,
            Set.of(SigningSuite.V1_SHA256));

        var routes = EnumSet.allOf(SigningSuite.class);

        assertTrue(policy.permits(
            SigningSuite.V1_SHA256, routes, c));
        assertFalse(policy.permits(
            SigningSuite.V2_SHA512, routes, c));
    }

    @Test
    void routeCanDisableV1DespiteGlobalSupport() {
        CredentialPolicy c = new CredentialPolicy(
            "partner-a-k4", "partner-a", true,
            EnumSet.allOf(SigningSuite.class));

        assertFalse(policy.permits(
            SigningSuite.V1_SHA256,
            Set.of(SigningSuite.V2_SHA512), c));
    }

    @Test
    void revokedCredentialFailsEverySuite() {
        CredentialPolicy c = new CredentialPolicy(
            "partner-a-k4", "partner-a", false,
            EnumSet.allOf(SigningSuite.class));

        assertFalse(policy.permits(
            SigningSuite.V1_SHA256,
            EnumSet.allOf(SigningSuite.class), c));
        assertFalse(policy.permits(
            SigningSuite.V2_SHA512,
            EnumSet.allOf(SigningSuite.class), c));
    }

    @Test
    void rejectsUnknownSuiteWithoutDefault() {
        assertNull(SigningSuite.parseExactly("none"));
        assertNull(SigningSuite.parseExactly("hmac-v1-sha256 "));
        assertNull(SigningSuite.parseExactly("HMAC-V1-SHA256"));
    }
}
~~~

Các tests trên chỉ chứng minh **policy selection**, chưa kiểm tra chữ ký hoặc nonce. Bổ sung integration test qua `SecurityFilterChain` thực có **positive control**: K4/V2 provisioned, V2 request pass; cùng K4 gửi MAC V1 đúng nhưng V1 disabled → reject. Nếu mọi request đều trả 401 do filter hỏng thì negative test đơn lẻ sẽ PASS giả.

### MockMvc test skeleton

~~~java
@Test
void rejectsV1EvenIfV1MacIsCryptographicallyCorrect()
        throws Exception {
    fixtures.provisionKey("partner-a-k4", "v2");
    fixtures.enableRoute("orders", "v2");
    fixtures.useFixedClock("2026-11-28T04:00:00Z");

    var validV2 = independentSigner.signedPost(
        "hmac-v2-sha512", "partner-a-k4",
        "/api/hmac/orders", "{\"orderId\":\"o1\"}");
    mockMvc.perform(validV2)
        .andExpect(status().is2xxSuccessful());

    var validV1MacButDenied = independentSigner.signedPost(
        "hmac-v1-sha256", "partner-a-k4",
        "/api/hmac/orders", "{\"orderId\":\"o2\"}");
    mockMvc.perform(validV1MacButDenied)
        .andExpect(status().isUnauthorized());
}
~~~

Đây là **skeleton**, không phải class biên dịch độc lập: `fixtures`, `independentSigner`, các key và route config là thành phần của dự án. Phải dùng nonce mới cho hai requests; test 401 cần assert internal reason `SUITE_POLICY_DENIED`, không phải `TIMESTAMP_OUT_OF_WINDOW`. Nếu test dùng timestamp tĩnh 2026, verifier phải inject `Clock.fixed` phù hợp.

Với `WebTestClient`, test tương tự qua `SecurityWebFilterChain` và reactive nonce store; kiểm tra cancel/release của `DataBuffer`, không `block()` trên event loop.

## 22. Ma trận kiểm thử server capability

| ID | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| CAP-01 | JCA provider hỗ trợ V1 | MAC/known-answer test PASS |
| CAP-02 | JCA provider không chạy V2 | V2 không advertise/route tới pod lỗi |
| CAP-03 | Global V1+V2, credential chỉ V1 | V1 pass, V2 bị deny |
| CAP-04 | Route chỉ V2, credential có cả V1/V2 | V1 reject |
| CAP-05 | Suite unknown hoặc `none` | Reject, không unsigned mode |
| CAP-06 | Suite viết sai case/whitespace | Reject theo exact grammar |
| CAP-07 | Hai `X-Signing-Suite` headers | Reject duplicate |
| CAP-08 | Đổi suite ID sau ký | Signature mismatch |
| CAP-09 | Suite không nằm trong MAC canonical bytes | Negative test phải phát hiện |
| CAP-10 | MAC đúng V1 nhưng V1 disabled | Reject dù MAC cryptographically valid |
| CAP-11 | V2 đúng secret + nonce mới | Authentication pass |
| CAP-12 | K4 khai V2 nhưng dùng secret K3 | Reject, không fallback |
| CAP-13 | Key K3 REVOKED | Reject ở mọi suite |
| CAP-14 | Client disabled | Reject |
| CAP-15 | Tenant disabled | Reject theo policy |
| CAP-16 | Body digest V1 SHA-256 | 32 bytes/64 lowercase hex |
| CAP-17 | Body digest V2 SHA-512 | 64 bytes/128 lowercase hex |
| CAP-18 | V1 MAC Base64 canonical | MAC 32 bytes |
| CAP-19 | V2 MAC Base64 canonical | MAC 64 bytes |
| CAP-20 | Signature length sai/malformed Base64 | Reject |
| CAP-21 | Thay method/path/query/signed header | MAC mismatch |
| CAP-22 | Thay raw body/timestamp/nonce | MAC mismatch |
| CAP-23 | V2 first-use nonce | Claim nguyên tử thành công |
| CAP-24 | Replay cùng signature/nonce | Reject, không business side effect thứ hai |
| CAP-25 | Nonce reuse V1→V2 | Chặn theo scope đã công bố |
| CAP-26 | Nonce store timeout/UNKNOWN | Fail closed |
| CAP-27 | Secret store unavailable | 503 hoặc dependency error, không fallback |
| CAP-28 | Gateway A/B đều hỗ trợ V2 | V2 pass qua cả hai |
| CAP-29 | Gateway B chưa hỗ trợ V2 | Không advertise V2 global hoặc route đến B |
| CAP-30 | Proxy rewrite canonical path | Test contract external/internal target |
| CAP-31 | Client giả gateway identity header | Không bypass HMAC |
| CAP-32 | HTTP/1.1↔HTTP/2 | Header/raw-target parity theo suite |
| CAP-33 | Public metadata chứa per-client secrets | Test privacy FAIL |
| CAP-34 | Metadata cache stale | Verifier vẫn áp policy mới |
| CAP-35 | Metadata giả yêu cầu hạ suite | Client không hạ minimum |
| CAP-36 | V1 deprecated nhưng còn allowed | Có thể pass trong overlap |
| CAP-37 | V1 disabled sau deadline | Reject trên mọi verifier |
| CAP-38 | Rollback code sau revoke V1 | Không tự bật V1 |
| CAP-39 | V2 được quảng bá nhưng K4 chưa provision | Reject K4/V2 |
| CAP-40 | HSM/provider V2 unavailable | Fail readiness/fail closed |
| CAP-41 | Body lớn vượt size limit | 413, không buffer vô hạn |
| CAP-42 | HMAC valid V2, sai quyền tenant | 403/404, không rò dữ liệu |
| CAP-43 | Unknown credential vs wrong MAC | Public response không tạo oracle rõ |
| CAP-44 | Replay qua region khác | Theo global anti-replay guarantee, không double-accept |
| CAP-45 | HMAC filter đăng ký hai lần | Không false replay chính request |
| CAP-46 | Advertise V2 trước full rollout | Test phát hiện capability inconsistency |
| CAP-47 | Verifier thử nhiều suite/fallback secret | Security test FAIL |
| CAP-48 | Golden vector V2 thiếu | CI release gate chặn |

Các kịch bản CAP-01–20 phù hợp unit/contract; CAP-21–27, 39–45 phù hợp Spring integration; CAP-28–38 và 46 phù hợp gateway/E2E; CAP-02, 26–27, 40 cần fault injection. Không đo lường “support” chỉ bằng một request 2xx.

## 23. Bài tập phân tích capability sai trong rollout

Một nền tảng payment có:

~~~text
Old suite: hmac-v1-sha256
New suite: hmac-v2-sha512
Global server config: both enabled
Gateway A: V1 + V2 deployed
Gateway B: only V1 deployed
Credential partner-a-k4: V2 key NOT provisioned
Credential partner-b-k7: V2 key provisioned
Discovery: advertises V2 preferred for all clients
~~~

Hệ thống xảy ra:

- `partner-a` gửi V2 luôn 401.
- `partner-b` gửi V2 có lúc thành công, có lúc thất bại theo gateway.
- Một SDK tự retry V1 sau khi V2 bị từ chối.
- Một verifier thử secret K3 cũ khi MAC K4 sai và chấp nhận request.
- Ops tắt V1 khỏi discovery nhưng pod cũ vẫn accept V1 có MAC đúng.

Hãy phân tích:

1. Vì sao `runtime supports V2` chưa đủ cho K4?
2. Tại sao discovery global chưa phản ánh tính sẵn sàng thực tế?
3. Thứ tự deploy, provision, canary, advertise, enforce nên như thế nào?
4. Client fallback tự động sau 401/503 nguy hiểm ở điểm nào?
5. Vì sao thử secret K3 sau MAC K4 sai là lỗi key/algorithm confusion?
6. Suite ID phải ràng buộc vào canonical bytes ra sao?
7. Nếu V1/V2 dùng chung credential và nonce, scope replay nên được thiết kế thế nào?
8. Tại sao xóa V1 khỏi metadata chưa chứng minh đã disable V1?
9. Những negative tests nào phát hiện V1 vẫn accepted trên Gateway B?
10. Có nên dùng HTTP 426 để “yêu cầu HMAC mới” không?
11. Monitor nên tách lỗi provider, key provisioning và signature mismatch ra sao?
12. Sau khi V2 MAC/nonce pass nhưng tenant policy deny, đó là authentication hay authorization failure?

**Hướng giải:** capability thực là giao giữa runtime/deployment/policy/route/credential. Provision key V2 và deploy toàn tuyến trước advertisement. Không fallback sau 401. Suite ID được ký, một request chỉ xác minh một suite và một key. Disable phải được thực thi ở verifier chứ không chỉ ở metadata. HMAC đúng vẫn phải qua authorization.

## 24. Checklist triển khai Server capability

- [ ] Mỗi signing suite có ID/version cố định và hợp đồng MAC, body digest, canonical request, encoding.
- [ ] Phân biệt implemented, runtime support, deployed, enabled, advertised, provisioned và accepted.
- [ ] Runtime/provider/HSM self-test bằng known-answer vectors, không chỉ `getInstance`.
- [ ] Effective suite policy = giao global, route, deployment và credential state/grants.
- [ ] Discovery HTTPS hoặc metadata signed đúng trust model, có schemaVersion/revision/expiry.
- [ ] Public metadata không tiết lộ credential existence, key material hoặc tenant grants.
- [ ] Client không tự hạ minimum suite khi timeout/401/metadata stale.
- [ ] Suite header là selector chưa tin cậy, được parse theo exact allowlist.
- [ ] Header duplicate, unknown, empty, malformed Base64 bị từ chối.
- [ ] Suite ID, key ID, timestamp, nonce và body digest được ràng buộc bằng HMAC.
- [ ] Verifier chọn **một** suite và **một** secret theo exact key ID, không fallback.
- [ ] Secret riêng từng suite/key version hoặc KDF có domain separation đã review.
- [ ] Key ACTIVE/REVOKED, client/tenant enabled và freshness policy luôn được kiểm tra.
- [ ] Nonce claim nguyên tử **sau MAC đúng**, scope xuyên version được định nghĩa.
- [ ] Secret manager/Redis/HSM unavailable thì fail closed, không unsigned/weak mode.
- [ ] Authentication valid không đồng nghĩa authorization: kiểm tra tenant/action/resource độc lập.
- [ ] MVC/WebFlux body capture có limit; proxy giữ đúng raw URI/header/body theo suite contract.
- [ ] Mọi gateway/region có suite readiness và policy revision nhất quán trước global advertisement.
- [ ] Nếu gateway verify HMAC, backend xác minh internal mTLS/assertion có request binding.
- [ ] Migration có pha deploy → provision → canary → dual support → enforce → retire.
- [ ] Rollback không tự hồi sinh suite/key đã disabled/revoked.
- [ ] Golden vectors byte-level và HMAC được cross-check độc lập ở nhiều ngôn ngữ.
- [ ] CI chạy selection policy, downgrade, nonce replay, proxy E2E và fault injection.
- [ ] Monitoring nhãn hữu hạn theo suite/route/result/region, không dùng key ID, nonce hoặc signature.
- [ ] Emergency disable có probes xác nhận V1 bị từ chối ở **mọi** verifier.
- [ ] Public error không tạo key/suite enumeration oracle, log không tiết lộ secret/body nhạy cảm.

**Server capability không phải quyền do client quyết định.** Server có thể triển khai nhiều thuật toán HMAC, nhưng chỉ chấp nhận suite cụ thể khi runtime, deployment, route, chính sách và credential cùng cho phép; suite ID phải được bảo vệ bởi chính chữ ký. Algorithm agility an toàn đòi hỏi rollout nhất quán, chống fallback/downgrade, key lifecycle, nonce chống replay và authorization độc lập — cùng bộ conformance tests chứng minh mọi gateway và client đang ký **đúng một hợp đồng đã được công bố**.

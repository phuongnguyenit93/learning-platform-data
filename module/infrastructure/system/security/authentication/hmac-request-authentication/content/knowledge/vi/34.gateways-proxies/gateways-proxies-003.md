# Gateway ký lại request trong xác thực HMAC

## 1. Mục tiêu và ngữ cảnh

Trong module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**, client chứng minh quyền sử dụng một shared secret bằng chữ ký HMAC trên **canonical request**: phương thức HTTP, URI, header và/hoặc body theo hợp đồng ký. Gateway/proxy có thể thay đổi request trước khi chuyển tiếp tới backend. Khi đó chữ ký của client có thể không còn tương ứng với những byte và trường mà backend thực sự nhận được.

Bài học thuộc chương **Gateway và proxy** tập trung vào kỹ thuật **gateway ký lại request** (*gateway re-signing*): sau khi xác thực nguồn gửi và hoàn tất các biến đổi được phép, gateway tạo một chữ ký HMAC mới cho request gửi tới backend bằng **credential riêng của gateway**. Backend xác minh chữ ký mới, kiểm tra chống replay và sử dụng danh tính mà gateway đã xác nhận để phân quyền.

Sau bài học, người học có thể:

- Giải thích vì sao chữ ký client hợp lệ ở gateway có thể không hợp lệ tại backend khi rewrite path/query, đổi body hoặc bổ sung header.
- Thiết kế hai hợp đồng ký và hai ranh giới tin cậy: **client → gateway** và **gateway → backend**.
- Đưa danh tính client/tenant đã xác thực vào các trường **được ký** ở hop nội bộ; chống giả mạo các header này từ Internet.
- Xây dựng hàm ký HMAC-SHA256 cho request sau biến đổi; xác minh ở backend với kiểm tra byte body, timestamp, nonce và audience.
- Xử lý retry, key rotation, đa instance, stream body và kiểm thử end-to-end qua gateway.
- Phân biệt việc gateway chứng thực danh tính với quyết định **authorization** đối với tài nguyên nghiệp vụ.

## 2. Vì sao phải ký lại?

Giả sử đối tác gửi:

```http
POST /api/v1/orders?dryRun=false HTTP/1.1
Host: api.example.test
X-Client-Key-Id: partner-42-k2
X-Client-Timestamp: ...
X-Client-Nonce: ...
X-Client-Signature: ...
Content-Type: application/json

{"sku":"A7","quantity":1}
```

Gateway xác minh chữ ký client dựa trên `POST`, raw path `/api/v1/orders`, raw query `dryRun=false` và digest của body. Sau đó gateway đổi path thành `/internal/orders` và thêm một header định tuyến. Nếu backend dùng raw path mà nó nhận được để xác minh **chữ ký client ban đầu**, canonical request đã khác; chữ ký phải bị từ chối.

Trường hợp body bị gateway chuyển từ `{"sku":"A7","quantity":1}` thành `{"quantity":1,"sku":"A7"}` cũng tương tự: JSON có thể cùng ý nghĩa nhưng SHA-256 của hai chuỗi byte khác nhau. Chữ ký của client không thể mặc nhiên chứng minh tính toàn vẹn của request đã được biến đổi.

Có hai hướng kiến trúc hợp lệ:

| Hướng | Cách xử lý | Khi phù hợp |
|---|---|---|
| **Giữ nguyên end-to-end** | Gateway không thay đổi bất kỳ thành phần nào thuộc hợp đồng ký; backend tự xác minh chữ ký client. | Cần backend tự kiểm tra bằng chứng từ client; có thể bảo toàn nguyên request. |
| **Xác thực tại gateway rồi ký lại** | Gateway xác minh request gốc, thực hiện biến đổi có kiểm soát và ký request **đầu ra** bằng khóa gateway–backend. | Gateway chịu trách nhiệm chuẩn hóa/routing và backend tin cậy gateway như một thực thể xác thực nội bộ. |

Bài này triển khai hướng thứ hai. Việc ký lại **không nối tiếp tính chất toán học của chữ ký cũ**: nó tạo bằng chứng mới rằng một gateway được tin cậy đã gửi đúng request đầu ra. Việc gateway thật sự kiểm tra chữ ký client trước đó là một thuộc tính của **quy trình và ranh giới tin cậy**; backend phải dựa vào credential, chính sách và các claim đã được gateway ký, không suy ra từ chữ ký mới rằng backend đã tự xác thực byte request gốc.

## 3. Luồng hai chặng và ranh giới tin cậy

```mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant R as Kho credential/nonce
    participant B as Backend
    C->>G: Request gốc + HMAC(client)
    G->>R: Lookup client key; kiểm tra timestamp/nonce
    R-->>G: Credential hợp lệ; claim nonce nguyên tử
    G->>G: Xác minh HMAC client + chính sách ingress
    G->>G: Rewrite route/header/body theo cấu hình
    G->>G: Xóa header gateway do client đưa vào
    G->>G: Ký request cuối cùng bằng secret nội bộ
    G->>B: Request đã biến đổi + HMAC(gateway)
    B->>B: Verify body/MAC/audience/timestamp/nonce
    B->>B: Tạo principal + kiểm tra scope/tenant/resource
    B-->>C: Response qua gateway
```

Bốn nguyên tắc thiết kế:

1. **Ingress phải xác thực trước khi ký nội bộ.** Nếu gateway ký hộ bất kỳ request Internet nào mà chưa xác thực/áp dụng policy, backend sẽ thấy request giả mạo như đến từ một gateway hợp lệ.
2. **Hai hop dùng key độc lập.** Secret đối tác gửi đến gateway không được sao chép làm secret gateway → backend. Một gateway có thể có nhiều key dành riêng cho từng backend/audience.
3. **Claim về client phải được gateway xác nhận và đưa vào HMAC mới.** Header client tự khai như `X-Tenant-Id` hoặc `X-Verified-Client-Id` không phải bằng chứng xác thực.
4. **Backend xác thực gateway và phân quyền riêng.** Khóa gateway chứng minh thực thể gateway; danh tính client/tenant trong chữ ký là claim do gateway xác nhận. Backend vẫn kiểm tra client có được thao tác trên resource cụ thể hay không.

Ranh giới tin cậy cần được kiểm soát cả ở mạng: chỉ chấp nhận traffic từ các ingress tin cậy (ví dụ mTLS, network policy, private listener), kiểm soát quyền truy cập secret và các route. HMAC không thay thế TLS.

## 4. Hợp đồng ký của hop gateway → backend

Để tránh hai hệ thống diễn giải khác nhau, cần đặt **phiên bản hợp đồng** và công bố chính xác byte nào được ký. Ví dụ dưới đây là hợp đồng **minh họa tự thiết kế**, tên `HMAC-GW-V1`. Không mặc định đây là chuẩn được Spring Cloud Gateway hoặc Spring Security cung cấp sẵn.

### 4.1. Header gateway tự sinh

| Header gửi tới backend | Ý nghĩa | Kiểm soát |
|---|---|---|
| `X-Gw-Key-Id` | ID credential gateway, dùng để tra secret tương ứng | Gateway sinh; backend chỉ chấp nhận key active và được phép gọi dịch vụ đích |
| `X-Gw-Timestamp` | Unix epoch giây UTC | Lệch giờ theo cửa sổ, ví dụ ±300 giây |
| `X-Gw-Nonce` | 16 byte ngẫu nhiên, Base64URL không padding | Chỉ dùng một lần theo key ID; backend lưu trong kho replay dùng chung |
| `X-Gw-Audience` | Định danh dịch vụ đích logic, ví dụ `orders-service` | Backend phải so bằng giá trị được cấu hình **cục bộ** |
| `X-Verified-Client-Id` | Client mà gateway đã xác thực ở ingress | Lấy từ credential đã xác minh, không lấy từ header tự khai |
| `X-Verified-Tenant-Id` | Tenant đã ràng buộc với credential được xác minh | Kiểm tra quyền truy cập tài nguyên theo tenant |
| `X-Gw-Body-SHA256` | SHA-256 dạng hex chữ thường của **body byte gửi đi** | Backend tính lại từ bytes thực nhận |
| `X-Gw-Signature` | Base64URL không padding của HMAC-SHA256 | So sánh MAC bằng hàm so sánh an toàn |

Mọi header trên phải được **xóa khỏi request đến từ client** trước khi gateway thiết lập giá trị mới. Khi đọc header tại backend, từ chối trường hợp thiếu, trùng giá trị, định dạng bất thường hoặc bị nối nhiều giá trị không theo hợp đồng. Các field tham gia canonical cần ràng buộc cú pháp (ví dụ client/tenant/audience/key ID chỉ chứa `[A-Za-z0-9._-]`) để tránh chèn ký tự xuống dòng và nhầm ranh giới trường.

### 4.2. Canonical request V1

Sử dụng **UTF-8**, mỗi dòng kết thúc bằng **LF** (`\n`), **không có LF cuối**. Các field lần lượt:

```text
HMAC-GW-V1
<HTTP_METHOD_UPPERCASE>
<RAW_PATH>
<RAW_QUERY_OR_EMPTY>
<X-GW-AUDIENCE>
<X-VERIFIED-CLIENT-ID>
<X-VERIFIED-TENANT-ID>
<X-GW-KEY-ID>
<X-GW-TIMESTAMP>
<X-GW-NONCE>
<LOWERCASE_HEX_SHA256_OF_FINAL_BODY_BYTES>
```

Công thức:

```text
bodyDigest = lowercaseHex(SHA256(finalOutboundBodyBytes))
signature  = Base64URL_NoPadding(
               HMAC_SHA256(gatewayBackendSecret, UTF8(canonicalRequest))
             )
```

**Ý nghĩa từng thành phần:**

- **Method:** byte tương ứng với phương thức HTTP thực gửi; `POST` và `GET` khác nhau.
- **Raw path:** path **sau khi rewrite**, trước khi backend nhận, giữ nguyên dạng percent-encoding theo hợp đồng; `/orders/%2F` khác `/orders//`.
- **Raw query:** chuỗi query đúng thứ tự và encoding như truyền đi. Phân biệt `a=1&b=2` với `b=2&a=1`; phân biệt query trống với query có giá trị nếu hệ thống có yêu cầu đó. V1 ở đây quy ước `null` và query rỗng đều thành chuỗi rỗng; phải kiểm thử proxy tuân theo quy ước.
- **Audience:** chống chuyển chữ ký của dịch vụ A sang dịch vụ B nếu nhiều backend chia sẻ một secret hoặc cấu hình route lỗi. Không lấy audience làm quyết định định tuyến từ header client.
- **Client/tenant:** identity claim do gateway xác nhận; bắt buộc đưa vào MAC. Không cho phép backend mặc nhiên tin header chưa ký.
- **Key ID, timestamp, nonce:** giúp tra key, chống phát lại và quản lý thời hạn hợp lệ.
- **Body hash:** gắn chữ ký với byte cuối cùng sau mọi bước sửa body. Body rỗng có SHA-256 bằng `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

Nếu API phụ thuộc `Content-Type`, `Content-Encoding`, tenant scope, idempotency key hoặc một header khác, **phải ký thêm các header đó theo hợp đồng phiên bản mới** hoặc cố định giá trị/kiểm tra nghiêm ngặt tại backend. V1 ở đây chỉ gắn các trường đã liệt kê: thay đổi một header nằm ngoài hợp đồng có thể ảnh hưởng cách backend diễn giải body dù MAC vẫn đúng. Với ví dụ thực hành JSON, yêu cầu gateway gửi `Content-Type: application/json` và backend từ chối định dạng không khớp.

### 4.3. Ví dụ trước và sau rewrite

Client gọi:

```text
GET /public/v1/orders?status=ready%2Fhold HTTP/1.1
X-Client-Key-Id: partner-42-k2
...
```

Gateway xác minh chữ ký client trên request gốc, sau đó định tuyến tới `orders-service` và chuẩn bị request:

```text
GET /internal/orders?status=ready%2Fhold HTTP/1.1
X-Gw-Audience: orders-service
X-Verified-Client-Id: partner-42
X-Verified-Tenant-Id: tenant-acme
X-Gw-Key-Id: edge-orders-k3
X-Gw-Timestamp: 1795800000
X-Gw-Nonce: AbCdEfGhIjKlMnOpQrStUv
X-Gw-Body-SHA256: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
X-Gw-Signature: <base64url của MAC>
```

Canonical mới là:

```text
HMAC-GW-V1
GET
/internal/orders
status=ready%2Fhold
orders-service
partner-42
tenant-acme
edge-orders-k3
1795800000
AbCdEfGhIjKlMnOpQrStUv
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

Dấu `<...>` trong ví dụ là placeholder, không phải chữ ký thật. Timestamp cố định dùng để trình bày; trong request thực tế phải lấy giờ hiện tại. Nếu một bộ lọc phía sau thay `/internal/orders` thành `/v2/internal/orders`, chữ ký ở trên không còn khớp và backend phải trả lỗi xác thực.

## 5. Cài đặt hàm ký bằng Java

Có thể tách logic ký thành một lớp Java thuần, dễ kiểm thử độc lập với Spring Cloud Gateway, Envoy hay NGINX. Đầu vào phải là **ảnh chụp request outbound đã được quyết định cuối cùng**: method, raw path/query, body bytes và audience. Dữ liệu `Caller` phải lấy từ kết quả xác minh của ingress.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Locale;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

record VerifiedCaller(String clientId, String tenantId) {}

record OutboundRequest(
        String method,
        String rawPath,
        String rawQuery,
        String audience,
        byte[] finalBody) {}

record GatewayProof(
        String keyId,
        String timestamp,
        String nonce,
        String audience,
        String verifiedClientId,
        String verifiedTenantId,
        String bodySha256,
        String signature) {}

final class GatewayHmacV1Signer {
    private static final Base64.Encoder BASE64URL =
            Base64.getUrlEncoder().withoutPadding();

    static GatewayProof sign(
            OutboundRequest request,
            VerifiedCaller caller,
            String keyId,
            byte[] secret,
            Clock clock,
            SecureRandom random) {

        requireToken(request.audience());
        requireToken(caller.clientId());
        requireToken(caller.tenantId());
        requireToken(keyId);
        requireRaw(request.rawPath());
        requireRaw(request.rawQuery());

        if (request.rawPath() == null || !request.rawPath().startsWith("/")) {
            throw new IllegalArgumentException("Invalid path");
        }
        if (secret == null || secret.length < 32) {
            throw new IllegalArgumentException("Invalid key material");
        }

        String method = request.method().toUpperCase(Locale.ROOT);
        if (!method.matches("[A-Z]+")) {
            throw new IllegalArgumentException("Invalid method");
        }

        // Snapshot byte body cuối cùng để tránh bị mutate trước khi gửi.
        byte[] body = request.finalBody().clone();

        byte[] nonceBytes = new byte[16];
        random.nextBytes(nonceBytes);
        String nonce = BASE64URL.encodeToString(nonceBytes);
        String timestamp = Long.toString(clock.instant().getEpochSecond());
        String rawQuery = request.rawQuery() == null ? "" : request.rawQuery();

        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(body);
            String hexDigest = HexFormat.of().formatHex(digest);

            String canonical = String.join("\n",
                    "HMAC-GW-V1",
                    method,
                    request.rawPath(),
                    rawQuery,
                    request.audience(),
                    caller.clientId(),
                    caller.tenantId(),
                    keyId,
                    timestamp,
                    nonce,
                    hexDigest);

            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret, "HmacSHA256"));
            byte[] signature = mac.doFinal(
                    canonical.getBytes(StandardCharsets.UTF_8));

            return new GatewayProof(
                    keyId,
                    timestamp,
                    nonce,
                    request.audience(),
                    caller.clientId(),
                    caller.tenantId(),
                    hexDigest,
                    BASE64URL.encodeToString(signature));
        } catch (GeneralSecurityException error) {
            throw new IllegalStateException("HMAC algorithm unavailable", error);
        }
    }

    private static void requireToken(String text) {
        if (text == null || !text.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("Invalid signed identifier");
        }
    }

    private static void requireRaw(String text) {
        if (text == null) {
            return; // Chỉ raw query được phép null; raw path được kiểm tra riêng.
        }
        if (text.indexOf('\r') >= 0 || text.indexOf('\n') >= 0) {
            throw new IllegalArgumentException("CR/LF in request target");
        }
    }
}
```

Trong dự án thật, kiểm tra thêm giới hạn raw URI, yêu cầu canonical request-target chính xác (kể cả percent-encoding), số lượng và độ dài header, và các ký tự điều khiển khác. Không dùng secret hard-code trong mã nguồn; lấy key từ key manager/vault, cấp riêng cho audience và có lịch rotation. Một secret tối thiểu 32 byte ngẫu nhiên là lựa chọn phù hợp cho HMAC-SHA256.

**Cách gọi tại gateway:** sau khi đã có `VerifiedCaller` hợp lệ và đã xác định `OutboundRequest`, gọi `sign` để tạo `GatewayProof`; đặt chính xác tám header trong record lên request outbound; bảo đảm request phát đi sử dụng **cùng method, raw path/query và body bytes** đã truyền vào hàm ký. Đặc biệt, các HTTP client có thể tự re-encode URI hoặc thêm lớp nén/chuyển mã; hãy đối chiếu chữ ký với request thật tới backend.

Trong Spring Cloud Gateway WebFlux, request body là stream reactive có thể chỉ tiêu thụ một lần. Nếu sửa body, cần cơ chế lưu/biến đổi body có giới hạn, quản lý `DataBuffer` đúng lifecycle và cung cấp lại bytes cho luồng forwarding. Không dùng `block()` trong event loop để ký; các thao tác crypto trên byte đã có là đồng bộ ngắn, nhưng truy xuất secret/nonce từ dịch vụ ngoài cần API bất đồng bộ hoặc scheduler phù hợp. Với body lớn hoặc streaming, thiết kế streaming signature/chunk signing riêng thay vì gom toàn bộ vào RAM.

Một ví dụ điều phối ở mức **pseudocode** (vị trí thực tế phụ thuộc cách gateway route và gửi HTTP):

```text
ingress:
  strip mọi X-Gw-*, X-Verified-* do phía ngoài gửi
  verify client HMAC + timestamp + nonce
  resolve clientId, tenantId, scopes từ credential đã xác minh
  kiểm tra route policy và quyền được vào backend
  lưu VerifiedCaller trong context nội bộ đáng tin

outbound, mỗi lần thực sự gửi:
  áp dụng xong path/query rewrite và các thay đổi body/header
  lấy raw request-target cuối cùng và immutable body bytes
  resolve audience, gateway keyId và secret theo route tin cậy
  tạo timestamp và nonce mới cho lần gửi này
  sign(finalRequest, verifiedCaller, keyId, secret)
  set header gateway do hệ thống sinh
  gửi đúng bytes/path/query đã ký tới backend
```

Một lỗi triển khai thường gặp là đặt bước ký trong `GlobalFilter` **trước** các route filter có khả năng thay đổi request. Thứ tự filter đơn thuần chưa đảm bảo byte thực phát đi; cần kiểm tra cả lớp HTTP client, đặc biệt khi có rewrite, filter nén body hoặc retry. Vị trí đúng về mặt ngữ nghĩa là sau biến đổi cuối cùng và trước khi request rời gateway.

## 6. Xác minh tại backend: tin gateway có điều kiện

Backend cần xác minh **tất cả** điều kiện trước khi tạo authentication:

1. Request đến đúng listener/route dành cho gateway tin cậy; có thể yêu cầu mTLS và network policy để hạn chế kẻ khác bắn request trực tiếp.
2. Đọc **một** giá trị hợp lệ cho mỗi header cần ký; giới hạn số byte/độ dài, từ chối trùng và ký tự không hợp lệ; từ chối thiếu dữ liệu.
3. `X-Gw-Audience` phải bằng service ID cấu hình tại backend; không chọn audience theo ý client.
4. `X-Gw-Key-Id` tra được credential gateway **active**, có quyền gọi đúng backend/audience, chưa quá hạn/đã revoke.
5. Timestamp là epoch giây hợp lệ và nằm trong cửa sổ cho phép; nonce có định dạng chính xác, không trùng ở các node.
6. Đọc body có giới hạn; tính lại SHA-256 trên byte nhận được; so sánh với digest đã khai báo.
7. Dựng đúng canonical V1 từ **method/raw URI nhận được** và claim/header đã giới hạn; tính lại HMAC-SHA256 bằng secret đã tra; giải mã Base64URL và so sánh MAC bằng `MessageDigest.isEqual` (không dùng `String.equals` để so chữ ký).
8. Chỉ **sau khi MAC hợp lệ** mới chiếm nonce bằng thao tác atomic. Nonce đã dùng: từ chối replay. Replay store lỗi: fail-closed; không lách kiểm tra.
9. Tạo principal nội bộ có cả gateway identity và verified client/tenant, nguồn gốc `gateway-attested`, rồi thực hiện authorization riêng theo scope, tenant và tài nguyên.

Ví dụ kiểm tra phía backend dưới dạng pseudocode:

```text
function verifyGatewayRequest(httpRequest):
  headers = parseStrictUniqueGatewayHeaders(httpRequest)
  require(headers.audience == THIS_BACKEND_AUDIENCE)

  key = activeGatewayKey(headers.keyId, audience=THIS_BACKEND_AUDIENCE)
  require(key != null && key.canCallThisService)

  require(timestampWithinSkew(headers.timestamp, nowUTC))
  require(validCanonicalNonce(headers.nonce))
  require(validClientAndTenantClaims(headers))

  body = readBodyWithLimit(httpRequest)
  require(constantTimeEqual(sha256(body), hexDecode(headers.bodySha256)))

  canonical = buildHmacGwV1(
      method=httpRequest.actualMethod,
      rawPath=httpRequest.actualRawPath,
      rawQuery=httpRequest.actualRawQuery,
      audience=headers.audience,
      clientId=headers.verifiedClientId,
      tenantId=headers.verifiedTenantId,
      keyId=headers.keyId,
      timestamp=headers.timestamp,
      nonce=headers.nonce,
      bodyDigest=headers.bodySha256
  )
  expectedMac = hmacSha256(key.secret, utf8(canonical))
  claimedMac = strictBase64UrlDecode(headers.signature)
  require(constantTimeEqual(expectedMac, claimedMac))

  require(atomicClaim("gw:" + headers.keyId + ":" + headers.nonce, ttl))
  return GatewayAttestedPrincipal(
      gateway=key.gatewayId,
      client=headers.verifiedClientId,
      tenant=headers.verifiedTenantId
  )
```

Lưu ý: xác minh trên dữ liệu từ `httpRequest.actualRawPath` đòi hỏi server HTTP/proxy nội bộ có thống nhất cách biểu diễn URI. Không parse rồi serialize lại JSON hoặc tự sắp xếp query vì sẽ tạo canonical khác. Nếu backend áp dụng additional proxy rewrite **sau** nơi gateway ký, cần đưa điểm xác minh về trước phép rewrite, hoặc điều chỉnh hợp đồng ký/kiến trúc phù hợp.

Trong Spring WebFlux, có thể tích hợp bước verify trong `WebFilter` hoặc `AuthenticationWebFilter` / `ReactiveAuthenticationManager` của Spring Security. Khi xác thực thành công, đưa security context qua Reactor Context, sau đó để policy `authorizeExchange`, method security hoặc tầng nghiệp vụ kiểm tra quyền. Header client/tenant được HMAC bảo vệ chứng minh **gateway đã khẳng định** giá trị đó, nhưng không có nghĩa tenant được toàn quyền.

### 6.1. Chống replay tại backend

Một thao tác atomic điển hình trên Redis:

```text
SET gw:edge-orders-k3:AbCdEfGhIjKlMnOpQrStUv 1 NX EX 660
```

Với skew ±300 giây, TTL 660 giây cho nonce là một lựa chọn bảo thủ có khoảng đệm. Tất cả backend instance phải dùng chung replay store. Kiểm tra `GET` rồi `SET` riêng rẽ là **không an toàn khi chạy đồng thời**. Key replay nên có namespace theo phiên bản/hop/key ID; chính sách revoke credential vẫn phải được áp dụng trong lookup.

Nếu gateway tự động retry request vì timeout, mỗi **lần gửi mới** phải có timestamp/nonce/signature mới. Việc gửi lại cùng bộ header HMAC sẽ bị backend coi là replay nếu request đầu tiên đã được chấp nhận. Chữ ký mới không thay thế idempotency nghiệp vụ: hai request hợp lệ khác nonce vẫn có thể tạo hai đơn hàng, vì vậy cần cơ chế idempotency riêng cho thao tác không an toàn khi lặp.

## 7. Route rewrite, header forwarding và body transformation

| Biến đổi ở gateway/proxy | Chữ ký client ban đầu | Điều gateway phải ký cho backend |
|---|---|---|
| Rewrite `/api/v1` → `/internal` | Có thể mất hiệu lực vì raw path thay đổi | **Raw path cuối cùng** mà backend nhận |
| Thay đổi thứ tự query, encode khoảng trắng `+`/`%20` | Có thể mất hiệu lực dù tham số logic giống nhau | Chuỗi raw query đúng thứ tự/encoding gửi đi |
| Thêm hoặc xóa `Content-Type`, `Content-Encoding` | Chỉ được bảo vệ nếu nằm trong canonical/policy ingress | Thống nhất policy backend; đưa các header quan trọng vào hợp đồng ký |
| Nén/giải nén, sửa JSON, normalize newline | Digest body cũ không còn đúng | Hash **byte body cuối cùng** |
| Thêm `X-Verified-Client-Id` | Dữ liệu mới không có trong chữ ký client | Claim từ credential đã xác minh, nằm trong MAC gateway |
| Load balancing sang backend khác | Chữ ký không nhất thiết gắn dịch vụ đích | Audience buộc chữ ký vào dịch vụ; key có quyền gọi đúng service |
| HTTP retry bởi gateway | Có thể khiến nonce cũ bị xem là replay | Ký lại từng attempt với nonce mới; giữ idempotency key nghiệp vụ |
| Route từ gateway qua proxy nội bộ thứ hai | Phụ thuộc proxy có đổi request hay không | Bảo đảm proxy thứ hai giữ nguyên các thành phần đã ký, hoặc xác minh/ký lại theo ranh giới tin cậy mới |

### 7.1. Không dựa vào header client tự khai

Một request từ Internet có thể cố tình thêm:

```http
X-Verified-Client-Id: admin
X-Verified-Tenant-Id: tenant-other
X-Gw-Audience: billing-service
X-Gw-Key-Id: trusted-gateway
```

Gateway phải xóa toàn bộ các header **thuộc namespace nội bộ** trước khi thực hiện xác thực và tạo header mới. Không dựa vào `X-Forwarded-For`, `X-Forwarded-Host`, `Forwarded` hoặc một header `X-Original-URI` tùy ý do client gửi để tạo canonical, trừ khi có cấu hình proxy đáng tin và chính sách xóa/ghi đè chuẩn. Tại backend, không nhận yêu cầu thông thường trực tiếp từ Internet kèm các header ký nội bộ.

Khi cần chuyển tiếp địa chỉ IP gốc để audit hay rate limit, coi đó là một claim riêng do gateway xác nhận; nếu backend sử dụng claim để ra quyết định bảo mật, phải đưa vào nội dung được ký hoặc dùng kênh metadata đã xác thực tương đương.

### 7.2. Ai chịu trách nhiệm sửa lỗi canonical mismatch?

Nếu test gateway trực tiếp thành công nhưng qua proxy thất bại, đối chiếu có kiểm soát tại **hai điểm**:

- Canonical ingress do gateway dùng để verify chữ ký client.
- Canonical outbound do gateway dùng để ký và canonical actual ingress do backend dùng để verify.

Ghi lại method, raw path/query, digest body, audience, key ID và các claim có thể công bố **trong môi trường test kiểm soát**. Tránh ghi secret, raw body nhạy cảm, MAC đầy đủ hoặc canonical chứa thông tin cá nhân vào log production. Lưu signature truncation hoặc request ID nếu cần tương quan sự cố; không tiết lộ thông tin dùng tái phát request.

## 8. Key rotation và quản lý credential qua hai hop

Client key và gateway key có **vòng đời độc lập**. Khi đổi khóa, thao tác nên được quản lý theo `keyId` để hai phiên bản tồn tại đồng thời trong khoảng chuyển tiếp:

1. Cấp gateway key ID mới (`edge-orders-k4`) và shared secret mới, giới hạn audience `orders-service` và phạm vi gọi được phép.
2. Backend chấp nhận đồng thời key cũ/mới theo thời hạn đã định. Gateway ký request mới bằng key mới.
3. Theo dõi tỷ lệ request bằng key cũ; kiểm tra retry/canary instance và kho replay trên nhiều node.
4. Revoke key cũ khi chuyển đổi hoàn tất; mọi request dùng key cũ phải bị từ chối kể cả chữ ký MAC đúng.

Nếu client key bị lộ thì rotate/revoke phía ingress. Nếu gateway key bị lộ, **backend** cần revoke ngay key đó và xem xét tác động lên tất cả client/tenant mà gateway được phép đại diện. Không chia sẻ một key cho quá nhiều audience nếu có thể tách riêng.

Secret không được đặt trong URL, log, metrics label, repository hoặc error message. Kho credential cần quy định version, trạng thái active, owner, audience, hạn dùng, quyền truy xuất và chính sách audit. Quản trị rotation phải tính đến instance chưa nhận cập nhật; không thử mọi key trong kho khi `keyId` không hợp lệ.

## 9. Lỗi và quan sát vận hành

| Điểm phát hiện | Tình huống | Hành vi nên có |
|---|---|---|
| Gateway ingress | Chữ ký client sai, timestamp quá hạn, nonce trùng | HTTP 401 chung; không chuyển tiếp backend |
| Gateway policy | Client xác thực hợp lệ nhưng route/service bị cấm | HTTP 403; không ký hộ request bị từ chối |
| Gateway outbound | Không tìm thấy key gateway hoặc key management lỗi | Không phát request chưa được ký; trả lỗi hạ tầng phù hợp |
| Backend verification | Thiếu header, sai audience/MAC/body digest, replay | HTTP 401 hoặc lỗi xác thực theo contract nội bộ; không chạy handler |
| Backend authorization | Gateway/MAC hợp lệ nhưng client không có quyền trên resource | HTTP 403 |
| Gateway/backend | Body vượt giới hạn xử lý an toàn | HTTP 413, không cố gom body vô hạn |
| Backend dependency | Nonce store/credential store lỗi | Fail-closed; phản ánh lỗi hạ tầng (ví dụ 503) và phát cảnh báo |

Cần quan sát: `hmac.client.verify.success/failure`, `hmac.gateway.sign.success/failure`, `hmac.backend.verify.success/failure`, replay rate, mismatched audience, latency của secret store, số request sử dụng key cũ, tỷ lệ 401 theo route và dấu hiệu thay đổi raw path sau deploy proxy. Giới hạn cardinality của metrics: không đưa clientId/nonce/URI tự do làm label không kiểm soát.

## 10. Ma trận kiểm thử end-to-end

Kiểm thử riêng signer/verifier bằng test vector byte chính xác, sau đó chạy qua gateway thực với routing/rewrite. Với bài tập, có thể dùng một client signer độc lập và một mock backend ghi nhận request-target thực tế.

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Client HMAC hợp lệ; gateway rewrite path; ký lại đúng body/route | Backend verify thành công; nhận đúng principal client và tenant |
| Gateway chỉ forward chữ ký client sau rewrite | Backend từ chối vì canonical không khớp hoặc thiếu chữ ký gateway |
| Request Internet tự gắn `X-Verified-Tenant-Id: admin` | Gateway xóa/ghi đè; backend chỉ nhận tenant đã xác minh |
| Đổi một byte body hoặc percent-encoding trên đường tới backend | Backend từ chối chữ ký/digest |
| Thay audience từ `orders-service` sang `billing-service` | Backend từ chối; không lấy service ID từ header để tự route |
| Thay clientId/tenantId nhưng giữ signature gateway | Backend từ chối MAC |
| Ký đúng nhưng client không có quyền truy cập resource tenant khác | Backend trả 403 |
| Hai bản sao cùng key+nonce tới hai backend instance | Tối đa một claim nonce thành công |
| Gateway retry cùng signature sau khi request đầu đã được nhận | Bị xem là replay; retry cần ký mới |
| Retry tạo nonce mới nhưng cùng idempotency key | Auth có thể thành công; nghiệp vụ phải chống thực thi trùng |
| Rotate gateway key theo keyId, revoke key cũ | Key mới thành công, key cũ bị từ chối sau revoke |
| Replay store lỗi hoặc gateway không lấy được secret | Request không được xác thực thành công; đo được lỗi hạ tầng |
| Body rỗng, JSON có whitespace, payload UTF-8 và binary | Chữ ký gắn với byte body thật, không gắn JSON đã parse |
| Gateway nén lại body, thêm proxy nội bộ hoặc normalize URI | Phải ký/verify theo bytes cuối cùng hoặc bị từ chối rõ ràng |

Khi kiểm thử với Spring WebFlux, xác nhận body được đọc/lưu/phát lại đúng một lần về mặt xử lý, `DataBuffer` không bị rò rỉ và không có `block()` trên event loop. Kiểm tra giới hạn kích thước body và concurrency. Đừng chỉ kiểm tra status 200; cần xác nhận handler thực nhận danh tính/tenant đúng và không nhận request khi signature sai.

## 11. Bài tập thực hành

Hãy thiết kế luồng `POST /api/v1/payments` từ client đến gateway rồi đến backend `payments-service` tại `POST /internal/payments`:

1. Client ký request gốc bằng key của chính client, đưa vào method/path/raw query và SHA-256 body. Gateway xác minh và lấy `VerifiedCaller(clientId, tenantId)` từ credential.
2. Gateway rewrite path, giữ nguyên hoặc biến đổi body theo chính sách, xóa các header nội bộ do client gửi, rồi ký outbound theo `HMAC-GW-V1` với key riêng của `payments-service`.
3. Backend xác minh đủ `audience`, digest body, MAC, timestamp, nonce và key active; tạo principal gateway-attested. Policy chỉ cho phép tenant sở hữu payment được xem/sửa payment tương ứng.
4. Thực hiện ba phép thử đối kháng: client thêm `X-Verified-Tenant-Id` giả; proxy đổi `/internal/payments`; gateway gửi lại request cũ đúng nonce. Mỗi trường hợp phải bị chặn tại bước thích hợp.
5. Thử timeout sau khi backend đã xử lý payment: retry bằng nonce mới không được tạo giao dịch thứ hai nếu nghiệp vụ dùng idempotency key được kiểm tra đúng.

### Câu hỏi tự kiểm tra

- Tại sao backend không thể lấy chữ ký gateway làm bằng chứng trực tiếp rằng nó đã thấy nguyên byte request được client ký?
- Vì sao ký lại phải diễn ra **sau** tất cả bước rewrite/body transformation?
- Vì sao gateway phải loại bỏ `X-Gw-*` và `X-Verified-*` từ request Internet?
- Nếu một gateway key bị lộ, những audience và tenant nào có thể bị ảnh hưởng?
- Khi retry, khác biệt giữa **replay prevention** bằng nonce và **business idempotency** là gì?
- Nếu chữ ký HMAC đúng nhưng client thuộc tenant khác tài nguyên đang truy cập, backend trả gì và tại sao?

**Kết quả mong đợi:** người học triển khai được hai chặng xác thực với khóa riêng biệt; gateway chỉ ký lại request của client đã xác minh và sau khi biến đổi cuối; backend kiểm tra chữ ký, chống replay, ràng buộc audience/identity và thực hiện phân quyền cho từng thao tác. 

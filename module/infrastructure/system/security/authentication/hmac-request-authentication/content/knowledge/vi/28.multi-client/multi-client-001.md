# Nhiều client

Một HTTP API dùng **HMAC request authentication** có thể phục vụ một client duy nhất, nhưng trong thực tế thường có **nhiều client độc lập**: các đối tác tích hợp, microservices, thiết bị, jobs hoặc ứng dụng của nhiều tenant cùng gọi một endpoint. Khi đó, yêu cầu không chỉ là “xác minh HMAC đúng” mà còn phải bảo đảm **request được gắn với đúng client**, mỗi client có secret và chính sách riêng, không thể mượn identity/quyền/nonce của client khác.

Bài **Nhiều client** thuộc chương **Multi-client** của mô-đun `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`. Mô-đun hướng dẫn thiết kế xác thực HTTP request bằng HMAC với shared secret và **canonical request** gồm method, URI, signed headers hoặc body theo hợp đồng ký; đồng thời kiểm tra chữ ký, chống replay bằng timestamp/nonce, quản lý key rotation, kiểm thử proxy/gateway và phân biệt **authentication** với **authorization**.

> **Nguyên tắc cốt lõi:** Một request mang `keyId` chỉ **đề nghị** server dùng một credential. Server tra **exact key ID** từ trusted registry, lấy secret và principal/tenant/audience gắn với record đó, tính HMAC trên **canonical bytes của request thực nhận**, rồi mới xác định caller. Không dùng một shared secret cho tất cả clients nếu cần cô lập, không để client tự khai principal có hiệu lực và không cho key ID lạ fallback sang secret của client khác.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích yêu cầu bảo mật khi chuyển HMAC authentication từ một client sang nhiều clients.
2. Phân biệt **client**, **credential**, **key ID**, **shared secret**, **principal**, **tenant**, **audience**, **scope** và **operation ID**.
3. Thiết kế registry **nhiều clients → nhiều credentials**, trong đó mỗi key ID chọn đúng một secret và một principal.
4. Xây dựng hợp đồng HMAC-HTTP-V1 chung mà không ép tất cả clients dùng cùng khóa.
5. Phân tích **cross-client impersonation**, **cross-tenant access**, **credential confusion**, **cross-service replay** và key rotation độc lập.
6. Chọn replay namespace và atomic nonce store để request từ nhiều verifier/nhiều clients không làm rò isolation.
7. Cài đặt Java 17 signer/verifier với `javax.crypto.Mac`, `SecretKeySpec`, `SecureRandom` và `MessageDigest.isEqual`.
8. Thiết kế rate limits, cache, auditing và credential lifecycle theo từng client, không dùng client-supplied labels làm authority.
9. Kiểm thử gateway/proxy, concurrent requests, malformed headers, rotation và registry outages.
10. Phân biệt xác thực client bằng HMAC với **phân quyền theo tenant/resource** và **business idempotency**.

## 2. Từ một client sang nhiều clients

Trong mô hình một client, ứng dụng có thể lưu một secret trong config:

~~~text
API verifier
  secret = K
  verify request MAC using K
~~~

Mô hình này không đủ cho nhiều client độc lập nếu cùng secret được phát cho tất cả:

~~~text
Client A --- shared K ---+
Client B --- shared K ---+---> API
Client C --- shared K ---+
~~~

Với shared K toàn cục, ai có K đều có năng lực tạo HMAC hợp lệ như các clients còn lại. Nếu một client bị compromise, muốn ngừng chấp nhận K có thể khiến **mọi client ngừng hoạt động**. Hơn nữa, tag HMAC không phân biệt ai trong số các bên có secret đã tạo tag.

Mô hình mong muốn:

~~~mermaid
flowchart LR
    A[Client A, key A3, secret KA3] --> G[API gateway]
    B[Client B, key B1, secret KB1] --> G
    C[Client C, key C7, secret KC7] --> G
    G --> V[HMAC verifier cluster]
    V --> R[Trusted credential registry]
    V --> N[Shared nonce replay authority]
    V --> P[Authorization policy]
    P --> X[Business API]
~~~

**Mỗi client có credential riêng**, thậm chí có nhiều keys để rotation. API có thể sử dụng **cùng signing contract** nhưng sẽ tính expected HMAC bằng **secret được chọn theo exact key ID**.

### 2.1. Các câu hỏi thiết kế bắt buộc

- Hệ thống nhận diện client theo application install, organization, partner hay workload identity?
- Một client được sở hữu bao nhiêu credentials? Có cho phép rotation overlap?
- Một secret có được chia sẻ giữa **hai clients** hay **hai environments** không?
- Key ID có unique toàn hệ thống hay unique trong một namespace?
- Một client có được gọi nhiều services/audiences không?
- Principal/tenant/scope được gán bởi ai? Có thể thay đổi mà không cần đổi secret không?
- Nonce uniqueness được áp dụng trong phạm vi nào?
- Có nhiều gateways, pods hoặc regions nào cùng nhận request?
- Nếu registry hoặc nonce store không khả dụng, API fail closed ra sao?
- Khi một client bị revoke, làm sao bảo đảm **clients còn lại không bị ảnh hưởng**?

## 3. Mô hình định danh: không đồng nhất client, key ID và tenant

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Client** | `client-a-service` | Bên đang tích hợp API |
| **Credential** | `client-a-k3` | Một version key có trạng thái/lifecycle riêng |
| **Key ID** | `client-a-k3` | Selector trên HTTP request; **chưa đáng tin** |
| **Shared secret** | Secret bytes của k3 | Vật liệu tính HMAC; không được log |
| **Principal** | `partner-A-app` | Identity được tạo sau authentication |
| **Tenant** | `tenant-A` | Phạm vi dữ liệu/organization |
| **Audience** | `orders-api` | Service mà credential được phép sử dụng |
| **Scope** | `orders:create` | Hành động được policy cho phép |
| **Nonce** | 16 random bytes | One-time request admission trong scope |
| **Operation ID** | `order-create-42` | Business idempotency, không phải nonce |

Một client có thể có **nhiều keys**:

~~~text
client-a-service
  keyId=client-a-k2  status=RETIRING
  keyId=client-a-k3  status=ACTIVE
~~~

Và một tenant có thể có **nhiều client applications**:

~~~text
tenant-A
  partner-A-webhook-consumer: key A3
  partner-A-payment-worker:   key A4
  partner-A-report-job:      key A5
~~~

Không nên lấy tên `keyId` như `tenant-A-admin` rồi suy ra quyền admin bằng cách parse chuỗi. Key ID là một chuỗi selector; **principal, tenant, scopes và audience phải lấy từ trusted credential record/policy**.

### 3.1. Key ID là public selector, không phải bằng chứng identity

Một attacker có thể đoán hoặc nhìn thấy `client-a-k3` mà vẫn không thể tính HMAC mới nếu không biết secret KA3. Nhưng nếu server thấy ID hợp lệ rồi đặt security context trước khi kiểm MAC, attacker có thể mạo principal A.

**Không tạo authenticated principal chỉ từ key ID.**

### 3.2. Credential và principal không phải quan hệ 1:1 bắt buộc

Rotation có thể làm hai credentials k2/k3 cùng ánh xạ tới principal A trong một overlap ngắn. Khi xác minh, mỗi ID vẫn phải chọn **đúng secret/version của chính nó**, không thử tất cả keys của principal.

## 4. Threat model cho HMAC nhiều client

Trong thiết kế đúng, attacker là một bên có thể:

- Gửi HTTP requests tới endpoint.
- Tự khai key ID, timestamp, nonce, route, headers và body.
- Sở hữu **secret hợp lệ của chính client B**.
- Biết key ID của client A nhưng **không** biết secret KA.
- Quan sát log hoặc signed request cũ nếu một boundary bị lộ.
- Tận dụng gateway rewrite, duplicate headers, parser differential hoặc caches lỗi.

Mục tiêu phòng thủ:

1. B chỉ ký được requests dưới **identity B**; không chọn key ID của A rồi dùng secret B.
2. Client A và B không dùng chung key material nếu không có lý do quản lý đặc biệt.
3. Một secret B bị lộ không làm lộ/nới quyền của credential A.
4. Cùng nonce của A và B có thể tồn tại trong namespaces riêng **nếu protocol định nghĩa như vậy**, nhưng nonce trùng dưới cùng credential phải bị chặn.
5. HMAC đúng của B **không** cho quyền truy cập tài nguyên tenant A.
6. Key bị revoke phải bị từ chối dù attacker biết secret và sinh timestamp/nonce mới.
7. Cùng secret không được cho phép cross-service request ngoài audience đã ký và policy.
8. Server không lựa chọn secret bằng client-provided algorithm, principal hoặc signed-header list thiếu mandatory fields.

### 4.1. Tình huống cross-client impersonation

~~~text
Client A:
  keyId = client-a-k3
  secret = KA3

Client B:
  keyId = client-b-k1
  secret = KB1

Attacker controls B and sends:
  X-Key-Id = client-a-k3
  signature = HMAC(KB1, canonicalRequestIncludingAKeyId)
~~~

Verifier phải lookup **client-a-k3**, dùng KA3 để tính expected tag và **reject** vì không khớp. Nếu code thử KB1 khi KA3 sai, attacker có thể khiến request khai key ID A được chấp nhận bằng secret B.

### 4.2. Tình huống cross-tenant authorization

~~~text
Client B signs using its own valid KB1.
Request path: /v1/tenants/tenant-A/orders
HMAC: PASS for client B
Replay: nonce is new
Authorization: MUST REJECT if B lacks rights over tenant-A
~~~

**Authentication** kiểm bằng chứng sở hữu secret B. **Authorization** kiểm B có quyền action/resource/tenant được yêu cầu hay không. Không thể suy ra quyền chỉ vì HMAC hợp lệ.

## 5. Một hợp đồng ký chung, nhiều secrets khác nhau

Một protocol minh họa **HMAC-HTTP-V1** (không phải RFC authentication scheme chung) quy định cùng phương pháp canonicalization cho tất cả clients. Mỗi request chứa:

~~~http
POST /v1/tenants/tenant-A/orders?dryRun=false HTTP/1.1
Host: orders.example.test
Content-Type: application/json
X-Key-Id: client-a-k3
X-Timestamp: 1800000030
X-Nonce: 0123456789abcdef0123456789abcdef
X-Signature: <43-char-base64url-hmac-sha256>

{"orderId":"O42","amount":250000}
~~~

Canonical text minh họa:

~~~text
HMAC-HTTP-V1
POST
/v1/tenants/tenant-A/orders
dryRun=false
audience:orders-api
host:orders.example.test
content-type:application/json
key-id:client-a-k3
timestamp:1800000030
nonce:0123456789abcdef0123456789abcdef
body-sha256:<sha256-lowercase-hex-of-raw-body>
~~~

Quy tắc **ví dụ**:

- Các dòng nối bằng LF và encode UTF-8, **không có LF cuối**.
- Method, path, query và host là request semantics tại **signing boundary đã thỏa thuận**.
- `audience` phải khớp service/credential registry, không tùy ý lấy từ một header không đáng tin.
- `content-type` là đúng một HTTP field đã validate.
- `key-id`, `timestamp`, `nonce` được ký để attacker không đổi credential selector hoặc freshness metadata.
- `body-sha256` là digest server tính từ **raw body bytes thực nhận**.
- Signature là full **HMAC-SHA256 32 byte**, encode Base64URL **không padding**, 43 ký tự.
- HMAC input **không** chứa chính `X-Signature` vì đó là tag đầu ra.
- Query/path percent encoding, Unicode, duplicate query parameters và proxy rewrites phải có chuẩn riêng **được client và server thống nhất**. Không tự ý sort/decode theo framework mặc định.

Trong toàn bài, ví dụ dùng client A/B với cùng **signing protocol**, nhưng:

\[
\operatorname{tag}_A=\operatorname{HMAC}_{KA3}(\operatorname{canonical}(R_A))
\]

\[
\operatorname{tag}_B=\operatorname{HMAC}_{KB1}(\operatorname{canonical}(R_B))
\]

Không có “secret chung của HMAC-HTTP-V1”. Version V1 mô tả **wire contract**, còn secret đến từ credential được chọn.

### 5.1. Tại sao phải ký key ID?

Nếu client gửi `X-Key-Id` không nằm trong canonical signed bytes, việc đổi ID có thể gây key/identity confusion ở các tầng khác nhau, nhất là khi có alias/secret reuse/rotation. Ràng buộc selector vào HMAC, tra exact key record và reject fallback.

### 5.2. Signed audience tránh cross-service reuse

Một key được cấp cho `orders-api` không nên được dùng để ký request cho `payments-api` chỉ vì cùng HMAC algorithm. Audience cần được ràng buộc trong signed request và được registry xác thực, đồng thời router kiểm service/host/path thực tế. Nếu dùng cùng secret xuyên services, rủi ro lan rộng; ưu tiên tách credential theo audience khi phù hợp.

### 5.3. Hợp đồng phải được chia sẻ, không suy đoán

Mọi client SDK và verifier phải dùng **cùng canonicalization version**. Nếu một client gửi JSON được serialize lại, đổi percent encoding hoặc đưa extra whitespace vào signed header trong khi server ký khác, chữ ký có thể không khớp. Đừng chữa mismatch bằng cách thử nhiều canonicalizations đến khi một MAC khớp; hãy version hóa protocol và kiểm thử với independent fixtures.

## 6. Mô hình credential registry cho nhiều client

Một registry có thể chứa:

| Key ID (exact) | Client/principal | Tenant | Audience | Key state | Algorithm |
| --- | --- | --- | --- | --- | --- |
| `client-a-k2` | `client-a-service` | `tenant-A` | `orders-api` | RETIRING | HmacSHA256 |
| `client-a-k3` | `client-a-service` | `tenant-A` | `orders-api` | ACTIVE | HmacSHA256 |
| `client-b-k1` | `client-b-service` | `tenant-B` | `orders-api` | ACTIVE | HmacSHA256 |
| `client-c-k7` | `client-c-worker` | `tenant-C` | `payments-api` | ACTIVE | HmacSHA256 |
| `client-d-k4` | `client-d-job` | `tenant-D` | `orders-api` | REVOKED | HmacSHA256 |

Secret bytes và secret references **không được hiển thị trong bảng thực tế dành cho người dùng**, ngoài metadata cần kiểm soát.

Một ánh xạ logical:

~~~text
keyId -> credential record:
  principalId
  tenantId
  allowedAudience
  allowedAlgorithms/signingVersion
  allowedScopes
  status + notBefore + notAfter + optional verifyUntil
  secretRef/secretBytes
  recordRevision
~~~

### 6.1. Exact lookup, không fallback

~~~text
lookup("client-a-k3") -> record A3
lookup("client-b-k1") -> record B1
lookup("client-a-k999") -> MISSING
registry outage -> UNAVAILABLE (not MISSING)
~~~

Không:

~~~text
lookup unknown -> use first ACTIVE credential
signature mismatch -> try every client secret
lookup key ID by prefix/substring
lookup key ID after unexpected lowercase/trim/percent-decode
choose secret using untrusted X-Tenant-Id or X-Role
~~~

Mỗi key ID nên unique toàn service hoặc thuộc **namespace được định nghĩa rõ** và ràng buộc trong request. Các key IDs dạng `[A-Za-z0-9_-]{1,64}` dễ parse, nhưng production có thể có grammar khác miễn là strict và nhất quán.

### 6.2. Một client có nhiều keys, một key không nên tự đại diện nhiều clients

Trong planned rotation, cùng principal A có thể có k2/k3. Cả hai record phải trỏ đúng secret của mình, có trạng thái và expiry riêng. Tránh một secret bytes bị phát cho B rồi copy cho A: nếu B bị compromise, A cũng bị ảnh hưởng dù key IDs khác.

### 6.3. Registry là nguồn identity, không phải nội dung của key ID

Một attacker khai `client-a-admin-k3` trong request không làm server cấp admin. Chỉ trusted registry có thể ánh xạ key ID sang principal và scopes; authorization vẫn kiểm resource và action.

## 7. Cấp phát và thu hồi credentials riêng theo client

Để vận hành multi-client, cần một vòng đời có ownership rõ cho từng credential:

~~~mermaid
stateDiagram-v2
    [*] --> PROVISIONED
    PROVISIONED --> ACTIVE: authorized activation
    ACTIVE --> RETIRING: planned rotation
    RETIRING --> REVOKED: overlap ends
    ACTIVE --> REVOKED: compromise/revoke
    ACTIVE --> DISABLED: administrative suspension
    DISABLED --> ACTIVE: re-enable only if trusted
    REVOKED --> [*]
~~~

### 7.1. Quy trình onboarding client mới

1. Xác thực tổ chức hoặc workload owner được phép tích hợp.
2. Tạo `clientId` và **new key ID duy nhất**, không tái dùng key ID của client khác.
3. Sinh **independent shared secret** bằng CSPRNG có entropy đủ cao, ví dụ 32 random bytes cho HMAC-SHA256.
4. Gán trusted `principalId`, `tenantId`, audience, allowed actions/scopes và key validity.
5. Lưu secret trong secret manager/KMS theo least privilege, audit access; tránh raw secret trong log/source/issue tracker.
6. Cung cấp secret cho client qua kênh có xác thực và bảo mật; định nghĩa ai có trách nhiệm lưu/rotate.
7. Cấp sample canonical request và independent HMAC test vector để kiểm client SDK.
8. Test request đầu tiên tại đúng gateway/endpoint, timestamp/nonce, HMAC, authorization và logging.
9. Ghi key owner, rotation schedule, emergency contact, revoke mechanism.
10. Kích hoạt credential đúng thời hạn và theo policy.

### 7.2. Không copy secret từ client A sang B

Nếu hai clients cùng secret nhưng mang key IDs khác:

~~~text
client-a-k3 -> shared secret K
client-b-k1 -> same shared secret K
~~~

thì B có thể tính HMAC bằng K cho canonical request khai key ID A. Key ID đã được ký vẫn **không tạo cô lập cryptographic** vì cả hai dùng K; nếu server policy khác nhau theo key ID, attacker biết K có thể cố gắng chuyển identity.

**Key IDs riêng chỉ có ý nghĩa an toàn khi secret material/capabilities cũng được tách biệt đúng.**

### 7.3. Rotation độc lập

Một client A cần rotate key không được gây downtime cho B. Ví dụ:

~~~text
A: client-a-k2 RETIRING (verify until T)
A: client-a-k3 ACTIVE
B: client-b-k1 ACTIVE and unchanged
~~~

Client A sử dụng k3 để ký request mới; verifier vẫn có thể verify k2 trong controlled overlap. Client B không cần thay khóa. Đến T, k2 bị REVOKED nhưng k3/B1 tiếp tục hoạt động.

Nếu secret A bị compromise, không giữ k2/k3 bị lộ chỉ vì overlap thông thường: **emergency revoke** các credentials liên quan và cấp secret mới. Nếu một client bị thu hồi, không vô hiệu hóa các key IDs khác chỉ vì cùng tenant trừ khi policy/nghi vấn phạm vi rộng hơn yêu cầu.

### 7.4. Validity theo server clock

Một contract hợp lý:

\[
\mathrm{validAt}(t) \iff \mathrm{notBefore} \le t < \mathrm{notAfter}
\]

Đối với key RETIRING, áp thêm `t < verifyUntil`. Phải test chính xác biên thời gian, đồng bộ UTC/clock giữa verifier nodes và không chấp nhận key REVOKED chỉ vì signed client timestamp trước revokedAt: client có secret bị lộ có thể tự ký lùi timestamp trong cửa sổ freshness.

## 8. Replay protection khi có nhiều client

HMAC hợp lệ không có nghĩa request chưa từng được nhận. Với multi-client, replay state phải có **namespace nhất quán** và **shared atomic admission** giữa các pods/gateways.

Ví dụ:

~~~text
hmac-replay:v1:orders-api:client-a-k3:0123456789abcdef0123456789abcdef
hmac-replay:v1:orders-api:client-b-k1:0123456789abcdef0123456789abcdef
~~~

Ở đây nonce cùng giá trị text ở A/B nằm trong **hai credential scopes khác nhau**, nên không bị xung đột. Trong cùng credential `client-a-k3`, lần thứ hai dùng nonce cũ phải bị từ chối trong retention window.

### 8.1. Namespace là một phần contract

Một chính sách minh họa:

~~~text
replayKey = "hmac-replay:v1:"
          + trustedAudience + ":" + validatedKeyId + ":" + nonceHex
~~~

- `trustedAudience` do server/credential policy xác định.
- `validatedKeyId` phải được ràng buộc trong chữ ký HMAC.
- `nonceHex` là lowercase hex cho 16 random bytes, đã được ký.
- Không lấy replay namespace từ `X-Tenant` hoặc `X-Client-Id` tùy ý do caller tự khai.
- Không dùng `nonce` làm key duy nhất toàn hệ thống nếu protocol cho phép nhiều credentials độc lập.
- Không thêm route tùy tiện vào replay key nếu contract muốn **nonce one-time trên toàn credential**.
- Nếu dùng namespace theo `principalId` thay vì key ID, phải định nghĩa rotation/cross-key semantics rõ.
- Nếu key ID có ký tự phân cách tùy ý, dùng length-prefixed encoding/hash cấu trúc để tránh collisions.

### 8.2. Atomic claim, không GET rồi SET

Trong Redis minh họa:

~~~redis
SET hmac-replay:v1:orders-api:client-a-k3:0123456789abcdef0123456789abcdef seen NX EX 360
~~~

`NX` + `EX` trong **một lệnh** giúp quyết định absent→present và expiration nguyên tử **trên primary xử lý key**. Không dùng `GET` kiểm missing rồi `SET` vì hai verifier có thể đồng thời thấy key absent.

Tuy nhiên, **atomic trên Redis primary không tự bảo đảm acknowledged write bền vững qua mọi asynchronous replica failover**. Nếu hệ thống yêu cầu chống replay mạnh xuyên failover hoặc multi-region, chọn một replay authority với durability/consistency phù hợp, test failover thực tế và fail closed khi outcome không chắc chắn.

### 8.3. Timestamp freshness và TTL

Cho:

- `A` = tuổi quá khứ tối đa được nhận.
- `F` = mức future skew được cho phép.
- `M` = safety margin cho clock/scheduling/delay.

Freshness:

\[
t_{now}-A \le t_{signed} \le t_{now}+F
\]

Một retention TTL bảo thủ tính từ lúc claim:

\[
\mathrm{nonceTTL} \ge A+F+M
\]

Ví dụ `A=300`, `F=30`, `M=30` giây → TTL 360 giây. Nếu TTL chỉ 300s, request ký timestamp ở mép tương lai có thể vẫn fresh **sau khi nonce entry hết hạn**.

### 8.4. Client time skew không được biến thành policy downgrade

Một client B có clock lệch 10 phút có thể gặp nhiều `STALE`/`TOO_FUTURE`. Không tự nới freshness window một cách không kiểm soát theo giá trị do client gửi. Hãy yêu cầu client đồng bộ clock, ghi metrics per-key về skew đã xác thực, dùng test `Clock.fixed` và có policy chung rõ ràng. Nếu một client đặc biệt cần window khác, phải coi đó là server-side credential/protocol policy có kiểm soát và đánh giá TTL tương ứng.

### 8.5. Replay store không thay business idempotency

Hai requests từ client A có nonces N1/N2 nhưng cùng `orderId=O42` đều có thể vượt replay gate. Nếu nghiệp vụ yêu cầu tạo order không trùng, dùng durable idempotency key theo `principalId + operationId` và transaction. Đừng dựa vào nonce để đảm bảo exactly-once business effects.

## 9. Authorization theo client, tenant, action và resource

Sau HMAC + freshness + nonce admission, server mới thiết lập authenticated principal từ registry:

~~~text
keyId=client-b-k1
verified secret=KB1
trusted principal=client-b-service
trusted tenant=tenant-B
allowed scopes=["orders:create", "orders:read"]
~~~

Request B gọi:

~~~http
POST /v1/tenants/tenant-A/orders HTTP/1.1
X-Key-Id: client-b-k1
X-Timestamp: 1800000030
X-Nonce: fedcba9876543210fedcba9876543210
X-Signature: <valid-B-tag>
~~~

MAC hoàn toàn có thể đúng cho KB1; nonce mới; timestamp fresh. Nhưng policy phải kiểm:

~~~text
authorize(
  trustedPrincipal=client-b-service,
  operation=orders:create,
  requestedTenant=tenant-A,
  resource=/v1/tenants/tenant-A/orders
) -> DENY
~~~

### 9.1. Authentication khác authorization

| Kiểm tra | Kết quả ví dụ |
| --- | --- |
| Key ID B1 FOUND, ACTIVE | Có thể tiếp tục |
| Algorithm/audience khớp | Có thể tiếp tục |
| HMAC tag khớp secret B1 | **Authenticated request from holder of B1** |
| Timestamp/nonce đạt yêu cầu | Request admission mới |
| Scope có orders:create | Có quyền action ở mức tổng quát |
| Tenant-B được phép ghi tenant-A? | **DENY**, trừ khi có delegation chính thức |
| Operation ID đã tồn tại? | Business idempotency theo policy |

Không tin `X-Tenant-Id`/`X-Role` của caller làm nguồn cấp quyền, kể cả khi header nằm trong signed fields: HMAC chỉ chứng minh **caller đã ký yêu cầu** đó, không phải server đã cấp quyền.

### 9.2. Không dùng key ID prefix để xác định tenant

Sai:

~~~java
String tenant = keyId.substring(0, keyId.indexOf('-'));
~~~

Tên key chỉ là chuỗi selector. Một ID có thể đổi cách đặt, một principal có thể quản lý nhiều tenants và cross-tenant delegation có thể tồn tại. Tenant/authorization facts phải đến từ trusted record và policy.

### 9.3. Delegated/cross-tenant access là policy riêng

Một client phục vụ nhiều tenants có thể được cấp một số quyền cross-tenant hợp pháp. HMAC không tự xác nhận delegation; cần trusted grants/consent/token with issuer validation, scopes cụ thể, expiration và audit. Không cho client đơn phương khai `X-On-Behalf-Of: tenant-A` rồi được cấp quyền.

### 9.4. Gateway-authenticated identity phải vượt qua trust boundary

Nếu gateway verify HMAC và thêm `X-Authenticated-Principal`, nó phải strip mọi giá trị do Internet tự gửi trước khi tạo header đáng tin, và backend phải chỉ chấp nhận traffic/context từ gateway được bảo vệ (mTLS hoặc integrity-protected assertion). Không để caller đi trực tiếp vào backend rồi tự khai principal B/A.

## 10. Java 17: chuẩn hóa canonical request cho nhiều clients

Ví dụ Java 17 dưới đây là một contract V1 **giới hạn có chủ ý** để dễ kiểm thử. Production có thể cần URI chuẩn hóa đầy đủ hơn, nhưng phải định nghĩa một version rõ và có independent fixtures, không thử nhiều canonicalizations đến khi MAC khớp.

### 10.1. Request và metadata riêng biệt

~~~java
import java.util.Objects;

public record SignedHttpParts(
        String method,
        String rawPath,
        String rawQuery,
        String host,
        String contentType,
        byte[] rawBody) {

    public SignedHttpParts {
        Objects.requireNonNull(method);
        Objects.requireNonNull(rawPath);
        Objects.requireNonNull(host);
        Objects.requireNonNull(contentType);
        Objects.requireNonNull(rawBody);
        rawBody = rawBody.clone();
    }

    @Override
    public byte[] rawBody() {
        return rawBody.clone();
    }
}
~~~

~~~java
public record SignatureMetadataV1(
        String keyId, long timestampSeconds, String nonceHex) {}
~~~

`SignedHttpParts` là dữ liệu ở **trusted HTTP signing boundary**. Với verifier, adapter phải tạo các thành phần này từ HTTP request **thực nhận**, không chấp nhận canonical string/body hash do client tự gửi và yêu cầu server tin ngay.

### 10.2. Canonicalizer V1 minh họa

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.regex.Pattern;

public final class HmacHttpV1Canonicalizer {
    private static final Pattern KEY_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");
    private static final Pattern NONCE =
            Pattern.compile("[0-9a-f]{32}");
    private static final Pattern PATH =
            Pattern.compile("/v1/tenants/[A-Za-z0-9_-]+/orders");
    private static final Pattern QUERY =
            Pattern.compile("dryRun=(?:true|false)");

    private HmacHttpV1Canonicalizer() {}

    public static byte[] canonicalBytes(
            SignedHttpParts request,
            SignatureMetadataV1 meta)
            throws NoSuchAlgorithmException {

        if (request == null || meta == null
                || meta.keyId() == null
                || !KEY_ID.matcher(meta.keyId()).matches()
                || meta.nonceHex() == null
                || !NONCE.matcher(meta.nonceHex()).matches()
                || meta.timestampSeconds() < 0
                || !"POST".equals(request.method())
                || !PATH.matcher(request.rawPath()).matches()
                || (request.rawQuery() != null
                    && !QUERY.matcher(request.rawQuery()).matches())
                || !"orders.example.test".equals(request.host())
                || !"application/json".equals(request.contentType())
                || request.rawBody().length > 1_048_576) {
            throw new IllegalArgumentException(
                    "Outside HMAC-HTTP-V1 contract");
        }

        String query = request.rawQuery() == null
                ? "" : request.rawQuery();
        String bodyHash = HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256")
                    .digest(request.rawBody()));

        String canonical = String.join("\n",
                "HMAC-HTTP-V1",
                request.method(),
                request.rawPath(),
                query,
                "audience:orders-api",
                "host:" + request.host(),
                "content-type:" + request.contentType(),
                "key-id:" + meta.keyId(),
                "timestamp:" + meta.timestampSeconds(),
                "nonce:" + meta.nonceHex(),
                "body-sha256:" + bodyHash);

        return canonical.getBytes(StandardCharsets.UTF_8);
    }
}
~~~

**Phạm vi giới hạn:** V1 chỉ chấp nhận POST tới `/v1/tenants/{id}/orders`, query vắng hoặc `dryRun=true/false`, host và content-type cố định. Nó chưa hỗ trợ arbitrary RFC 3986 URI, percent encoding, duplicate query names, JSON streaming hay Unicode. Mục tiêu là thể hiện **cùng canonical contract nhưng key ID và secret khác nhau**.

### 10.3. Mọi clients dùng cùng protocol marker

Một caller có key A3 và B1 có thể dùng cùng `HmacHttpV1Canonicalizer` nhưng `SignatureMetadataV1.keyId` khác và **secret để tính tag khác**. Phần `X-Signature` chứa tag đầu ra không nằm trong canonical bytes tạo ra chính tag.

Nếu gateway strip path prefix hoặc thay JSON body bytes, cần verify tại signing boundary thích hợp hoặc xác định mapping đáng tin. Không lấy request-target đã bị router decode nếu handler hiểu semantics khác với bytes được ký.

## 11. Java 17: client signer dùng secret riêng

Một Java client nên chọn credential **thuộc chính client đó**, lấy key ID + secret từ cấu hình an toàn, sinh nonce ngẫu nhiên và ký canonical bytes đúng contract.

### 11.1. Envelope chứa metadata và tag

~~~java
public record SignedEnvelopeV1(
        SignatureMetadataV1 metadata,
        String signatureBase64Url) {}
~~~

~~~java
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.time.Clock;
import java.util.Base64;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class HmacClientSignerV1 {
    private final String keyId;
    private final byte[] secret;
    private final Clock clock;
    private final SecureRandom random;

    public HmacClientSignerV1(
            String keyId, byte[] secret,
            Clock clock, SecureRandom random) {
        if (keyId == null || secret == null || secret.length < 16
                || clock == null || random == null) {
            throw new IllegalArgumentException("Invalid signer setup");
        }
        this.keyId = keyId;
        this.secret = secret.clone();
        this.clock = clock;
        this.random = random;
    }

    public SignedEnvelopeV1 sign(SignedHttpParts request)
            throws GeneralSecurityException {

        byte[] nonce = new byte[16];
        random.nextBytes(nonce);

        var metadata = new SignatureMetadataV1(
                keyId,
                clock.instant().getEpochSecond(),
                HexFormat.of().formatHex(nonce));

        byte[] canonical =
                HmacHttpV1Canonicalizer.canonicalBytes(
                        request, metadata);

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        byte[] tag = mac.doFinal(canonical);

        String encoded = Base64.getUrlEncoder()
                .withoutPadding().encodeToString(tag);
        return new SignedEnvelopeV1(metadata, encoded);
    }
}
~~~

`HmacClientSignerV1` sinh nonce mới cho mỗi request và dùng clock của client. Secret test/production không được in trong log, gửi kèm trong HTTP request hoặc lộ qua exception. Việc clone một array giúp tránh caller sửa bản gốc nhưng không thay một secret manager; production cần quản lý đời sống key trong bộ nhớ và cơ chế rotation an toàn.

### 11.2. Hai client signers với key riêng

~~~java
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

public final class TwoClientsDemo {
    public static void main(String[] args) throws Exception {
        Clock testClock = Clock.fixed(
                Instant.ofEpochSecond(1_800_000_030L),
                ZoneOffset.UTC);

        // Chỉ là fixture, KHÔNG dùng hai literal này làm secret thật.
        byte[] secretA = "test-only-independent-secret-A"
                .getBytes(StandardCharsets.US_ASCII);
        byte[] secretB = "test-only-independent-secret-B"
                .getBytes(StandardCharsets.US_ASCII);

        var clientA = new HmacClientSignerV1(
                "client-a-k3", secretA, testClock, new SecureRandom());
        var clientB = new HmacClientSignerV1(
                "client-b-k1", secretB, testClock, new SecureRandom());

        var requestA = new SignedHttpParts(
                "POST", "/v1/tenants/tenant-A/orders",
                "dryRun=false", "orders.example.test",
                "application/json",
                "{\"orderId\":\"O42\"}".getBytes(StandardCharsets.UTF_8));

        var requestB = new SignedHttpParts(
                "POST", "/v1/tenants/tenant-B/orders",
                "dryRun=false", "orders.example.test",
                "application/json",
                "{\"orderId\":\"O99\"}".getBytes(StandardCharsets.UTF_8));

        SignedEnvelopeV1 a = clientA.sign(requestA);
        SignedEnvelopeV1 b = clientB.sign(requestB);

        System.out.println(a.metadata().keyId());
        System.out.println(b.metadata().keyId());
        // Không log raw signatures/secret trên hệ thống thật.
    }
}
~~~

Mỗi envelope chứa key ID riêng. Dù client A/B cùng ký tại một thời điểm và đều dùng HMAC-SHA256, **tag phải được tính bằng secret riêng và canonical bytes của request riêng**.

### 11.3. Không chọn secret từ request target

Code client không nên có logic:

~~~text
if (path.contains("tenant-A")) useSecret(A)
else useSecret(B)
~~~

Bí mật nào được dùng là quyết định của **client credential configuration**. Nếu một client được cấp quyền phục vụ nhiều tenants, phải có delegation/credential scoping rõ ràng. Không lấy tenant ID từ raw path rồi âm thầm dùng secret của một client khác nếu không được phép.

## 12. Java 17: key registry và chính sách theo client

### 12.1. Lifecycle record có defensive copy

~~~java
public enum KeyStatusV1 {
    PROVISIONED, ACTIVE, RETIRING, DISABLED, REVOKED
}
~~~

~~~java
import java.time.Instant;
import java.util.Objects;

public record ClientCredentialV1(
        String keyId,
        String principalId,
        String tenantId,
        String audience,
        String algorithm,
        KeyStatusV1 status,
        Instant notBefore,
        Instant notAfter,
        Instant verifyUntil,
        byte[] secret) {

    public ClientCredentialV1 {
        Objects.requireNonNull(keyId);
        Objects.requireNonNull(principalId);
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(audience);
        Objects.requireNonNull(algorithm);
        Objects.requireNonNull(status);
        Objects.requireNonNull(notBefore);
        Objects.requireNonNull(notAfter);
        Objects.requireNonNull(secret);

        if (!notBefore.isBefore(notAfter) || secret.length == 0) {
            throw new IllegalArgumentException("Invalid record");
        }
        secret = secret.clone();
    }

    @Override
    public byte[] secret() {
        return secret.clone();
    }
}
~~~

Lưu ý `record` chứa secret thích hợp làm fixture test, **không nên log `record.toString()`** hoặc đưa record vào telemetry. Production có thể chứa `secretRef` và yêu cầu KMS/HSM thực hiện operations trong boundary được bảo vệ; truy vấn secret theo **exact key ID/version**, không dùng “latest secret của tenant”.

### 12.2. Registry có trạng thái MISSING khác UNAVAILABLE

~~~java
import java.util.Optional;

public interface ClientCredentialRegistryV1 {
    /**
     * Empty = exact ID không tồn tại ở nguồn đáng tin.
     * Timeout/partition không được chuyển thành Empty.
     */
    Optional<ClientCredentialV1> findExact(String keyId);
}
~~~

~~~java
public final class RegistryUnavailableV1
        extends RuntimeException {
    public RegistryUnavailableV1(String message) {
        super(message);
    }
}
~~~

Một test registry có thể ném `RegistryUnavailableV1` khi mất nguồn dữ liệu. Server phải **fail closed**, không tạo principal từ key ID trần, không fallback sang secret mặc định hoặc secret của client khác.

### 12.3. Policy key status, audience, algorithm

~~~java
import java.time.Instant;

public final class ClientCredentialPolicyV1 {
    private ClientCredentialPolicyV1() {}

    public static boolean allowsVerify(
            ClientCredentialV1 record,
            String expectedAudience, Instant now) {

        if (record == null || expectedAudience == null || now == null
                || !record.audience().equals(expectedAudience)
                || !"HmacSHA256".equals(record.algorithm())
                || now.isBefore(record.notBefore())
                || !now.isBefore(record.notAfter())) {
            return false;
        }

        return switch (record.status()) {
            case ACTIVE -> true;
            case RETIRING -> record.verifyUntil() != null
                    && now.isBefore(record.verifyUntil());
            case PROVISIONED, DISABLED, REVOKED -> false;
        };
    }
}
~~~

Một key ACTIVE chưa hết hạn vẫn chỉ được verify nếu đúng **audience và algorithm**. Key RETIRING có cutoff. Key REVOKED bị từ chối bất kể HMAC tag đúng hay timestamp client được đặt trước lúc revoke.

## 13. Java 17: replay store contract cho nhiều verifier

Tách replay admission khỏi registry và HMAC để test atomicity rõ ràng:

~~~java
import java.time.Duration;

public interface ReplayStoreV1 {
    enum Claim { NEW, REPLAY, UNKNOWN }

    /**
     * Atomic insert-if-absent with TTL, shared by every verifier
     * that could receive the same signed request.
     */
    Claim claimOnce(String replayKey, Duration ttl);
}
~~~

Production Redis adapter cần semantics tương đương `SET key value NX EX seconds` **trong một thao tác**; duplicate không được reset TTL. Nếu store timeout/failover khiến outcome không chắc, trả `UNKNOWN` và **không xử lý business**.

`ReplayStoreV1` không khẳng định Redis single-primary async replication durable qua mọi failover. Nếu yêu cầu chống double admission mạnh, phải chọn replay authority với consistency/durability phù hợp và kiểm thử acknowledged writes bị mất.

### 13.1. Scope theo key, không chỉ nonce

~~~text
Client A nonce=N, key=client-a-k3:
  hmac-replay:v1:orders-api:client-a-k3:N

Client B nonce=N, key=client-b-k1:
  hmac-replay:v1:orders-api:client-b-k1:N
~~~

Một test phải chứng minh N của A không chặn B khi cùng nonce, nhưng **hai requests cùng ID A3 và nonce N** thì tối đa một được nhận trong retention window. Đây là **contract minh họa**; nếu muốn one-time nonce theo principal, cần version hóa scope và kiểm thử phù hợp.

### 13.2. Không claim nonce trước khi MAC hợp lệ

Nếu attacker khai key ID A và nonce N rồi gửi tag sai, không được claim N vào replay store: attacker có thể poison namespace A để chặn request hợp lệ. Thứ tự đúng: **strict parse → key policy → HMAC → freshness → atomic nonce claim → trusted principal → authorization**.

## 14. Java 17: verifier chọn chính xác secret theo key ID

### 14.1. Authentication result chỉ có principal khi thành công

~~~java
public record VerifiedClientV1(
        String principalId, String tenantId,
        String keyId, String audience) {}
~~~

~~~java
public enum MultiClientOutcomeV1 {
    ACCEPTED, INVALID_REQUEST, UNKNOWN_KEY,
    KEY_NOT_ALLOWED, BAD_SIGNATURE, STALE, REPLAY, UNAVAILABLE
}
~~~

~~~java
public record MultiClientResultV1(
        MultiClientOutcomeV1 outcome,
        VerifiedClientV1 authenticatedClient) {

    public static MultiClientResultV1 reject(
            MultiClientOutcomeV1 outcome) {
        return new MultiClientResultV1(outcome, null);
    }

    public static MultiClientResultV1 accept(
            VerifiedClientV1 client) {
        return new MultiClientResultV1(
                MultiClientOutcomeV1.ACCEPTED, client);
    }
}
~~~

`authenticatedClient` phải null nếu outcome không phải `ACCEPTED`. Internal codes phục vụ test/metrics; response bên ngoài cần hạn chế tiết lộ key existence/status và expected tag.

### 14.2. Full verifier Java 17

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Duration;
import java.util.Base64;
import java.util.Optional;
import java.util.regex.Pattern;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class MultiClientVerifierV1 {
    private static final Pattern TAG =
            Pattern.compile("[A-Za-z0-9_-]{43}");

    private static final long MAX_AGE = 300;
    private static final long MAX_FUTURE = 30;
    private static final Duration NONCE_TTL =
            Duration.ofSeconds(360);

    private final ClientCredentialRegistryV1 registry;
    private final ReplayStoreV1 replayStore;
    private final Clock clock;

    public MultiClientVerifierV1(
            ClientCredentialRegistryV1 registry,
            ReplayStoreV1 replayStore,
            Clock clock) {
        this.registry = registry;
        this.replayStore = replayStore;
        this.clock = clock;
    }

    /**
     * PRECONDITION: HTTP edge rejects duplicate/ambiguous signed
     * headers and makes SignedHttpParts from the received request.
     * Key ID, timestamp, nonce, audience are bound in MAC bytes.
     */
    public MultiClientResultV1 verify(
            SignedHttpParts http,
            SignatureMetadataV1 meta,
            String presentedBase64Url) {

        final byte[] canonical;
        try {
            canonical =
                HmacHttpV1Canonicalizer.canonicalBytes(http, meta);
        } catch (IllegalArgumentException
                 | java.security.NoSuchAlgorithmException bad) {
            return MultiClientResultV1.reject(
                    MultiClientOutcomeV1.INVALID_REQUEST);
        }

        if (presentedBase64Url == null
                || !TAG.matcher(presentedBase64Url).matches()) {
            return MultiClientResultV1.reject(
                    MultiClientOutcomeV1.BAD_SIGNATURE);
        }

        final byte[] presented;
        try {
            presented = Base64.getUrlDecoder()
                    .decode(presentedBase64Url);
            if (presented.length != 32
                    || !Base64.getUrlEncoder().withoutPadding()
                        .encodeToString(presented)
                        .equals(presentedBase64Url)) {
                return MultiClientResultV1.reject(
                        MultiClientOutcomeV1.BAD_SIGNATURE);
            }
        } catch (IllegalArgumentException malformed) {
            return MultiClientResultV1.reject(
                    MultiClientOutcomeV1.BAD_SIGNATURE);
        }

        // ONE exact record. No fallback to another client key.
        final Optional<ClientCredentialV1> found;
        try {
            found = registry.findExact(meta.keyId());
        } catch (RegistryUnavailableV1 unavailable) {
            return MultiClientResultV1.reject(
                    MultiClientOutcomeV1.UNAVAILABLE);
        }

        if (found.isEmpty()) {
            return MultiClientResultV1.reject(
                    MultiClientOutcomeV1.UNKNOWN_KEY);
        }

        ClientCredentialV1 credential = found.get();
        if (!credential.keyId().equals(meta.keyId())
                || !ClientCredentialPolicyV1.allowsVerify(
                    credential, "orders-api", clock.instant())) {
            return MultiClientResultV1.reject(
                    MultiClientOutcomeV1.KEY_NOT_ALLOWED);
        }

        final byte[] expected;
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(
                    credential.secret(), "HmacSHA256"));
            expected = mac.doFinal(canonical);
        } catch (GeneralSecurityException cryptoFailure) {
            return MultiClientResultV1.reject(
                    MultiClientOutcomeV1.UNAVAILABLE);
        }

        if (!MessageDigest.isEqual(expected, presented)) {
            return MultiClientResultV1.reject(
                    MultiClientOutcomeV1.BAD_SIGNATURE);
        }

        long now = clock.instant().getEpochSecond();
        try {
            long oldest = Math.subtractExact(now, MAX_AGE);
            long newest = Math.addExact(now, MAX_FUTURE);
            if (meta.timestampSeconds() < oldest
                    || meta.timestampSeconds() > newest) {
                return MultiClientResultV1.reject(
                        MultiClientOutcomeV1.STALE);
            }
        } catch (ArithmeticException overflow) {
            return MultiClientResultV1.reject(
                    MultiClientOutcomeV1.STALE);
        }

        String nonceKey = "hmac-replay:v1:orders-api:"
                + meta.keyId() + ":" + meta.nonceHex();

        final ReplayStoreV1.Claim claim;
        try {
            claim = replayStore.claimOnce(nonceKey, NONCE_TTL);
        } catch (RuntimeException uncertain) {
            return MultiClientResultV1.reject(
                    MultiClientOutcomeV1.UNAVAILABLE);
        }

        if (claim == ReplayStoreV1.Claim.REPLAY) {
            return MultiClientResultV1.reject(
                    MultiClientOutcomeV1.REPLAY);
        }
        if (claim != ReplayStoreV1.Claim.NEW) {
            return MultiClientResultV1.reject(
                    MultiClientOutcomeV1.UNAVAILABLE);
        }

        return MultiClientResultV1.accept(new VerifiedClientV1(
                credential.principalId(),
                credential.tenantId(),
                credential.keyId(),
                credential.audience()));
    }
}
~~~

### 14.3. Các bất biến của verifier

- Mọi clients dùng **cùng verification pipeline**, không hardcode secret theo client name.
- `keyId` chưa đáng tin; exact lookup phải trả record có ID trùng input.
- Không thử secret của client B nếu tag với secret A mismatch.
- Key status/audience/algorithm/expiry được áp trước khi MAC có thể xác thực.
- Tag strict Base64URL no padding, full 32 bytes và `MessageDigest.isEqual`.
- Nonce key dựa trên signed key ID và trusted audience; atomic claim **sau** HMAC đúng.
- Không tạo `VerifiedClientV1` nếu unknown key, bad tag, stale timestamp hoặc store outage.
- `ACCEPTED` là authentic request admission, **chưa thay authorization**.
- Code minh họa `A=300`, `F=30`, TTL=360s (margin 30s). Cần tinh chỉnh theo clock/retention assumptions thật.
- `MessageDigest.isEqual` không biến toàn key lookup/HTTP parse thành constant-time; tránh tiết lộ key status trong errors và đo timing nếu threat model đòi hỏi.

### 14.4. HTTP adapter production còn phải làm gì?

1. Reject malformed HTTP framing, CR/LF control bytes, parser ambiguity và duplicated signed headers.
2. Bảo đảm mỗi field `X-Key-Id`, `X-Timestamp`, `X-Nonce`, `X-Signature` có đúng một occurrence, case-insensitive header names.
3. Parse timestamp decimal canonical: không leading zero, dấu cộng, overflow hoặc nhầm milliseconds.
4. Không chọn key ID từ hai nguồn mâu thuẫn (`Authorization` vs `X-Key-Id`).
5. Tái dựng body digest từ raw body bytes; không tin client-provided canonical string hoặc hash.
6. Bảo đảm host/authority đến từ trusted signing boundary, không tin `X-Forwarded-Host` caller tự khai.
7. Limit header/body sizes trước khi hash/verify, chống resource exhaustion.
8. Phân biệt internal error codes với generic public errors để tránh key enumeration và secret leaks.

### 14.5. Authorization độc lập

~~~java
public final class TenantOrderPolicyV1 {
    private TenantOrderPolicyV1() {}

    // Chỉ minh họa mô hình 1 client được thao tác 1 tenant.
    public static boolean canCreateOrder(
            VerifiedClientV1 client, String requestedTenant) {
        return client != null
                && client.tenantId().equals(requestedTenant);
    }
}
~~~

Trong production, authorization còn cần action, scope, resource ownership và delegation, không chỉ so tenant string. Client B đã MAC hợp lệ nhưng path tenant A vẫn có thể bị từ chối.

## 15. Giới hạn consistency và dependency của ví dụ

`MultiClientVerifierV1` chỉ tốt bằng registry adapter và replay authority thực tế:

- Stale ACTIVE sau revoke có thể làm verifier nhận credential đã lộ.
- Negative cache cho client mới provision có thể làm chậm activation nhưng không được fallback.
- Registry outage không được biến thành MISSING hoặc default secret.
- Secret manager lookup phải gắn secretRef/version với đúng key ID, không lấy “latest key of client”.
- Replay store per-pod không chặn request gửi qua node khác.
- Redis primary ACK không đồng nghĩa nonce luôn bền vững qua failover.
- Multi-region eventual stores độc lập có thể cùng claim nonce trước replication.
- Token/session phát sinh từ HMAC request có thể cần revoke riêng khi credential compromised.

Các failure modes này đòi hỏi integration/chaos tests trên topology thực, không thể kết luận từ unit test trong một process.

## 16. JUnit 5: kiểm thử cô lập giữa client A và client B

Test quan trọng nhất của multi-client không phải “hai valid clients đều được accept”, mà là **đổi key ID/secret/tenant qua lại phải bị từ chối đúng lớp**. Các snippets dưới đây dùng JUnit Jupiter, Java 17 và các lớp mục 10–15. Đặt mỗi public class/record/enum vào file Java tương ứng nếu dùng trong project thật.

### 16.1. Fake registry và fake replay store

~~~java
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

public final class FakeClientCredentialRegistry
        implements ClientCredentialRegistryV1 {

    private final Map<String, ClientCredentialV1> keys =
            new ConcurrentHashMap<>();
    private volatile boolean unavailable;

    public void put(ClientCredentialV1 key) {
        keys.put(key.keyId(), key);
    }

    public void setUnavailable(boolean value) {
        unavailable = value;
    }

    @Override
    public Optional<ClientCredentialV1> findExact(String id) {
        if (unavailable) {
            throw new RegistryUnavailableV1("Test registry outage");
        }
        return Optional.ofNullable(keys.get(id));
    }
}
~~~

~~~java
import java.time.Duration;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public final class FakeReplayStoreV1 implements ReplayStoreV1 {
    private final Set<String> keys =
            ConcurrentHashMap.newKeySet();
    private volatile boolean unavailable;

    public void setUnavailable(boolean value) {
        unavailable = value;
    }

    public int size() {
        return keys.size();
    }

    @Override
    public Claim claimOnce(String key, Duration ttl) {
        if (unavailable) return Claim.UNKNOWN;
        // Atomic ONLY inside this JVM; NO TTL or failover durability.
        return keys.add(key) ? Claim.NEW : Claim.REPLAY;
    }
}
~~~

**Phạm vi fake:** Map/set trong một JVM giúp test semantics về key namespace và concurrency cục bộ. Nó **không** chứng minh cluster-wide replay, expiry, failover hay Redis durability. Các khả năng đó phải được kiểm thử với shared store thật.

### 16.2. Test fixture với hai secrets độc lập

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

public final class MultiClientVerifierV1Test {
    private static final long EPOCH = 1_800_000_030L;
    private static final Instant NOW = Instant.ofEpochSecond(EPOCH);
    private static final Clock CLOCK =
            Clock.fixed(NOW, ZoneOffset.UTC);

    private static final byte[] SECRET_A =
            "test-only-secret-A-independent"
                .getBytes(StandardCharsets.US_ASCII);
    private static final byte[] SECRET_B =
            "test-only-secret-B-independent"
                .getBytes(StandardCharsets.US_ASCII);

    private static final String NONCE =
            "0123456789abcdef0123456789abcdef";
    private static final String NONCE_TWO =
            "fedcba9876543210fedcba9876543210";

    private FakeClientCredentialRegistry registry;
    private FakeReplayStoreV1 replay;
    private MultiClientVerifierV1 verifier;

    private static ClientCredentialV1 credential(
            String keyId, String principal, String tenant,
            byte[] secret, KeyStatusV1 status) {

        return new ClientCredentialV1(
                keyId, principal, tenant, "orders-api",
                "HmacSHA256", status,
                NOW.minusSeconds(600),
                NOW.plusSeconds(600),
                NOW.plusSeconds(300),
                secret);
    }

    private static SignedHttpParts request(String tenant) {
        return new SignedHttpParts(
                "POST",
                "/v1/tenants/" + tenant + "/orders",
                "dryRun=false",
                "orders.example.test",
                "application/json",
                "{\"orderId\":\"O42\"}"
                    .getBytes(StandardCharsets.UTF_8));
    }

    private static SignatureMetadataV1 meta(
            String keyId, String nonce) {
        return new SignatureMetadataV1(
                keyId, EPOCH, nonce);
    }

    private static String sign(
            SignedHttpParts request,
            SignatureMetadataV1 meta,
            byte[] secret) throws GeneralSecurityException {

        byte[] canonical =
                HmacHttpV1Canonicalizer.canonicalBytes(
                        request, meta);
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(mac.doFinal(canonical));
    }

    @BeforeEach
    void setUp() {
        registry = new FakeClientCredentialRegistry();
        registry.put(credential(
                "client-a-k3", "client-A", "tenant-A",
                SECRET_A, KeyStatusV1.ACTIVE));
        registry.put(credential(
                "client-b-k1", "client-B", "tenant-B",
                SECRET_B, KeyStatusV1.ACTIVE));

        replay = new FakeReplayStoreV1();
        verifier = new MultiClientVerifierV1(
                registry, replay, CLOCK);
    }

    @Test
    void clientAAndBWithOwnSecretsAreAccepted()
            throws Exception {

        var httpA = request("tenant-A");
        var httpB = request("tenant-B");
        var a = meta("client-a-k3", NONCE);
        var b = meta("client-b-k1", NONCE);

        var verifiedA = verifier.verify(
                httpA, a, sign(httpA, a, SECRET_A));
        var verifiedB = verifier.verify(
                httpB, b, sign(httpB, b, SECRET_B));

        assertEquals(MultiClientOutcomeV1.ACCEPTED,
                verifiedA.outcome());
        assertEquals("client-A",
                verifiedA.authenticatedClient().principalId());

        assertEquals(MultiClientOutcomeV1.ACCEPTED,
                verifiedB.outcome());
        assertEquals("client-B",
                verifiedB.authenticatedClient().principalId());

        // Cùng text NONCE, khác key ID -> scope replay độc lập.
        assertEquals(2, replay.size());
    }

    @Test
    void sameClientAndNonceCannotBeAdmittedTwice()
            throws Exception {

        var http = request("tenant-A");
        var a = meta("client-a-k3", NONCE);
        String tag = sign(http, a, SECRET_A);

        assertEquals(MultiClientOutcomeV1.ACCEPTED,
                verifier.verify(http, a, tag).outcome());
        assertEquals(MultiClientOutcomeV1.REPLAY,
                verifier.verify(http, a, tag).outcome());
        assertEquals(1, replay.size());
    }

    @Test
    void clientBSecretCannotImpersonateClientA()
            throws Exception {

        var http = request("tenant-A");
        var claimsA = meta("client-a-k3", NONCE);
        String forgedTag = sign(http, claimsA, SECRET_B);

        var result = verifier.verify(http, claimsA, forgedTag);

        assertEquals(MultiClientOutcomeV1.BAD_SIGNATURE,
                result.outcome());
        assertNull(result.authenticatedClient());
        assertEquals(0, replay.size());
    }

    @Test
    void unknownKeyDoesNotFallBackToClientASecret()
            throws Exception {

        var http = request("tenant-A");
        var unknown = meta("client-a-k99", NONCE);
        String signedWithA = sign(http, unknown, SECRET_A);

        assertEquals(MultiClientOutcomeV1.UNKNOWN_KEY,
                verifier.verify(http, unknown, signedWithA)
                    .outcome());
        assertEquals(0, replay.size());
    }

    @Test
    void clientBHasValidMacButCannotActOnTenantA()
            throws Exception {

        var http = request("tenant-A");
        var b = meta("client-b-k1", NONCE);
        String tag = sign(http, b, SECRET_B);

        var result = verifier.verify(http, b, tag);
        assertEquals(MultiClientOutcomeV1.ACCEPTED,
                result.outcome());

        assertFalse(TenantOrderPolicyV1.canCreateOrder(
                result.authenticatedClient(), "tenant-A"));
    }

    @Test
    void revokingADoesNotDisableB()
            throws Exception {

        registry.put(credential(
                "client-a-k3", "client-A", "tenant-A",
                SECRET_A, KeyStatusV1.REVOKED));

        var httpA = request("tenant-A");
        var a = meta("client-a-k3", NONCE);
        assertEquals(MultiClientOutcomeV1.KEY_NOT_ALLOWED,
                verifier.verify(httpA, a,
                        sign(httpA, a, SECRET_A)).outcome());

        var httpB = request("tenant-B");
        var b = meta("client-b-k1", NONCE_TWO);
        assertEquals(MultiClientOutcomeV1.ACCEPTED,
                verifier.verify(httpB, b,
                        sign(httpB, b, SECRET_B)).outcome());
    }

    @Test
    void invalidSignatureMustNotPoisonReplayStore()
            throws Exception {

        var http = request("tenant-A");
        var a = meta("client-a-k3", NONCE);

        assertEquals(MultiClientOutcomeV1.BAD_SIGNATURE,
                verifier.verify(http, a,
                        sign(http, a, SECRET_B)).outcome());
        assertEquals(0, replay.size());

        assertEquals(MultiClientOutcomeV1.ACCEPTED,
                verifier.verify(http, a,
                        sign(http, a, SECRET_A)).outcome());
    }

    @Test
    void registryOutageMustNotAuthenticate()
            throws Exception {

        registry.setUnavailable(true);
        var http = request("tenant-A");
        var a = meta("client-a-k3", NONCE);

        var result = verifier.verify(
                http, a, sign(http, a, SECRET_A));
        assertEquals(MultiClientOutcomeV1.UNAVAILABLE,
                result.outcome());
        assertNull(result.authenticatedClient());
        assertEquals(0, replay.size());
    }

    @Test
    void replayStoreOutageMustFailClosed()
            throws Exception {

        replay.setUnavailable(true);
        var http = request("tenant-A");
        var a = meta("client-a-k3", NONCE);

        var result = verifier.verify(
                http, a, sign(http, a, SECRET_A));
        assertEquals(MultiClientOutcomeV1.UNAVAILABLE,
                result.outcome());
        assertNull(result.authenticatedClient());
    }
}
~~~

### 16.3. Điều mà bộ test chứng minh

- A và B cùng gửi nonce N **không va nhau** do namespace gồm key ID.
- A gửi lại chính signed request N bị chặn.
- Secret B **không** có thể xác minh request khai key ID A.
- Key ID unknown không được fallback sang một secret hiện có.
- HMAC B đúng **không** cấp quyền trên tenant A.
- A bị revoke không khiến B ngừng xác thực.
- Request MAC sai không chiếm nonce của client hợp lệ.
- Registry/replay store unavailable không tạo principal hoặc chạy business.

### 16.4. Điều mà bộ test chưa chứng minh

- Một fake set trong process không có TTL và không chịu Redis primary failover.
- Unit test không nhìn được duplicate HTTP headers đã bị gateway merge/drop.
- Nó không chứng minh secret manager/KMS permissions đã đúng.
- Nó không chứng minh callback business idempotent qua crash/retries.
- Nó không chứng minh timing side channels không tồn tại.
- Nó không chứng minh đầy đủ canonicalization cho mọi URI hợp lệ.

**STEP 4 là bước soạn tài liệu, chưa chạy JUnit hay QA chuyên môn**. Khi dùng ví dụ trong project thật, tạo các files/package cần thiết, chạy build/tests và bổ sung integration tests theo topology triển khai.

## 17. Test concurrency: cùng nonce của một client

Với một shared replay authority, khi 50 HTTP requests **cùng signed request của client A** đến 50 verifier threads/nodes, yêu cầu là:

~~~text
HMAC verification: all copies have valid MAC
freshness: all copies fresh
atomic nonce claims:
    exactly one NEW under authority guarantee
    all other claims REPLAY or explicit safe failure
business handler:
    at most one execution for that signed request
~~~

Một local fake có thể test atomicity trong JVM:

~~~java
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.ArrayList;

public final class ConcurrentNonceDemo {
    public static void main(String[] args) throws Exception {
        ReplayStoreV1 store = new FakeReplayStoreV1();
        String key = "hmac-replay:v1:orders-api:client-a-k3:nonce-N";
        int n = 30;

        var ready = new CountDownLatch(n);
        var go = new CountDownLatch(1);
        var pool = Executors.newFixedThreadPool(n);

        try {
            var futures = new ArrayList<Future<ReplayStoreV1.Claim>>();
            for (int i = 0; i < n; i++) {
                futures.add(pool.submit(() -> {
                    ready.countDown();
                    go.await();
                    return store.claimOnce(
                            key, Duration.ofSeconds(360));
                }));
            }

            ready.await();
            go.countDown();

            int winners = 0;
            for (var f : futures) {
                if (f.get() == ReplayStoreV1.Claim.NEW) {
                    winners++;
                }
            }

            if (winners != 1) {
                throw new AssertionError(
                        "Expected one nonce winner: " + winners);
            }
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Đây là **unit-level concurrency demonstration**. Production test phải dùng **ít nhất hai verifier processes/containers** cùng Redis/DB authority, gửi request gần đồng thời qua gateway, kiểm cả key namespace A/B, store outage, sharding, replication lag và failover.

## 18. Gateway/proxy khi nhiều clients cùng truy cập

~~~mermaid
sequenceDiagram
    participant A as Client A
    participant B as Client B
    participant G as Shared API gateway
    participant V as Verifier cluster
    participant R as Credential registry
    participant N as Nonce store
    participant S as Orders API

    A->>G: Key A3, HMAC(KA3, request A)
    B->>G: Key B1, HMAC(KB1, request B)
    G->>V: Validated signed HTTP semantics
    V->>R: findExact(keyId), policy, secret
    R-->>V: Exact credential
    V->>V: Rebuild canonical bytes and compare HMAC
    V->>N: Atomic claim audience:keyId:nonce
    N-->>V: NEW / REPLAY / UNKNOWN
    V->>S: Trusted principal after successful admission
    S->>S: Authorize tenant and action, idempotency
~~~

### 18.1. Header multiplicity và scheme confusion

Một gateway có thể nhận:

~~~http
X-Key-Id: client-a-k3
x-key-id: client-b-k1
~~~

Field names HTTP **không phân biệt hoa/thường**. Nếu gateway first-wins còn backend last-wins, hai tầng có thể chọn **hai clients khác nhau**. Không chấp nhận ambiguity: reject duplicate `X-Key-Id`, `Authorization` và mọi signed field quan trọng ở edge **trước khi** proxy merge/drop.

Nếu API cũng hỗ trợ Basic/Bearer, endpoint HMAC phải có **authentication scheme routing policy** rõ, không “thử từng scheme” cho đến khi một cái thành công và không cho client tự nâng principal bằng header do mình đặt.

### 18.2. HTTP/1.1, HTTP/2 và canonical method/URI

Gateway có thể đổi:

- HTTP/2 `:authority` thành Host.
- Path prefix của public API thành internal route.
- Percent-encoded bytes, query order hoặc duplicate query params.
- Header names case và whitespace.
- Body framing hoặc JSON serialization.

Phải xác định signing boundary: verify **trước** những rewrites ảnh hưởng signed semantics, hoặc có một mapping versioned và trusted mà client/server đều hiểu. Không tin `X-Original-URI`, `X-Forwarded-Host` hoặc `X-Authenticated-Client` do Internet tự khai.

### 18.3. Per-client routing và authentication owner

Nếu client A và B được route qua hai backend pools, cả hai pools vẫn phải dùng cùng registry policy/key state cho audience tương ứng. Nếu gateway xác minh HMAC và claim nonce, backend không vô tình claim lại cùng namespace rồi reject request hợp lệ. Cần một **owner của replay admission** và một trust boundary bảo vệ authenticated context.

### 18.4. Gateway retry và idempotency

Gateway có thể gửi request A, timeout và retry nguyên signed request sang verifier khác. Nếu lần đầu đã claim nonce, lần hai là replay và phải reject theo protocol. Client cần operation-status lookup hoặc signed retry với nonce mới và **cùng business idempotency key** để xác định kết quả; không tắt replay gate vì gateway retries.

## 19. Rate limiting, quotas và công bằng tài nguyên

Khi một API có hàng trăm hoặc hàng nghìn clients, một client lỗi hoặc bị compromise có thể chiếm quá nhiều resources. HMAC chỉ xác thực **năng lực dùng secret**, không tự kiểm soát request rate, CPU hash, registry lookups, nonces hay business quotas.

### 19.1. Rate limit trước và sau authentication

| Vị trí | Khóa rate limit | Lưu ý |
| --- | --- | --- |
| **Pre-auth** | Trusted edge source network / connection / coarse route | Không lấy key ID chưa xác minh làm identity duy nhất |
| **Auth parsing** | Global malformed request budget / header-size limits | Chống flood key IDs ngẫu nhiên, tránh high-cardinality state |
| **Post-auth** | Trusted principal ID, credential ID, audience | Rate limit theo client được xác thực |
| **Authorization** | Principal + action/resource/tenant | Phân tách read và write risk |
| **Business** | Tenant, operation, transaction amount | Enforce quotas, fraud/risk controls và idempotency |

Không cho caller gửi `X-Client-Tier: platinum` rồi tự nhận quota cao nếu server chưa xác thực entitlement. Client tier/contract lấy từ server-side policy.

### 19.2. Global limits và per-client limits

Một API cần bảo vệ cả:

- Tổng công suất hệ thống (global cap).
- Mỗi client/credential (fair-share).
- Mỗi tenant/account/resource (tránh một client chiếm tài nguyên chung).
- Endpoint nhạy cảm như payment/order creation (transaction controls).
- Registry/KMS lookup rate và HMAC CPU/buffer allocation.

Nếu `client-a-k3` gửi đột biến 5.000 RPS, không nên làm `client-b-k1` ngừng phục vụ chỉ vì cache/queue chung bị chiếm hết. Có thể dùng isolation pools, per-principal quotas, backpressure và alerting, nhưng phải xem concurrency/throughput trên **topology thật**.

### 19.3. Invalid key ID là đầu vào chưa xác thực

Một attacker có thể gửi hàng triệu key ID ngẫu nhiên, gây cache/registry misses. Không tạo per-key metrics labels/cache entries vô hạn cho mọi raw key ID do Internet khai. Dùng pre-auth size/syntax/rate limits, bounded negative caching và high-cardinality-safe telemetry. Không dùng “mã ID có vẻ đúng” làm bằng chứng client trả phí hay cho quota cao.

### 19.4. Rate limiting không thay revoke

Một key bị lộ vẫn có thể ký requests hợp lệ dưới quota; per-client limits chỉ **giảm blast radius**. Khi xác định credential compromise, cần thu hồi đúng key và thực thi denial theo policy. Không xem “throttle đủ nhỏ” là giải pháp cryptographic authentication.

## 20. Key rotation, compromise và cô lập sự cố từng client

### 20.1. Rotation không ảnh hưởng client khác

Giả sử:

~~~text
A: k2 RETIRING, k3 ACTIVE
B: k1 ACTIVE
C: k7 REVOKED
~~~

Lần lượt:

- k2 hợp lệ **chỉ** nếu trong overlap và đúng secret-v2.
- k3 hợp lệ theo key-v3 và audience/scope.
- B1 không thay đổi khi A rotate.
- C7 không thể dùng để ký request mới ngay cả khi tag đúng dưới secret C7.

Không có vòng lặp “thử tất cả secrets trong tenant” khi request khai A3. Nếu nó có MAC sai, **reject**, không fallback về A2 hoặc B1.

### 20.2. Compromised client A

Khi secret A3 bị lộ, attacker có thể tạo timestamp/nonce mới và HMAC tag hoàn toàn hợp lệ. **Anti-replay không đủ**. Quy trình:

1. Xác định key A3, principal, tenant, audience, actions/permissions.
2. Revoke/disable A3 tại trusted registry; đảm bảo mọi gateways/verifiers nhìn revocation đúng SLA.
3. Nếu cache còn stale ACTIVE, dùng invalidation/version fencing hoặc tạm fail closed trên risk paths.
4. Sinh secret A4 **độc lập**, không chỉ đổi key ID hoặc base64-encode lại A3.
5. Phân phối A4 qua kênh an toàn, sửa nguyên nhân rò secret cũ, kiểm các copies/backups.
6. Test request A4, và test A3 bị reject trên mọi admission path.
7. Đối chiếu các business requests đáng ngờ trong exposure window.
8. Giữ clients B/C không liên quan tiếp tục hoạt động trừ khi threat model cho thấy secret/registry bị compromise rộng hơn.

### 20.3. Key sharing phá cô lập sự cố

Nếu một secret bytes dùng cho client A và B, việc revoke key ID A nhưng vẫn chấp nhận B với **cùng secret** có thể không bảo vệ identity A nếu hệ thống có ID confusion/canonicalization lỗi. Tốt nhất **không tái sử dụng material giữa clients**, đồng thời key ID được ký và ánh xạ exact. Phải có inventory để biết những credentials nào thực sự chia sẻ key material.

### 20.4. Revocation cache consistency

Stale ACTIVE ở một node có thể cho request của revoked client A qua dù B ở node khác đã thấy revoke. Với requirement emergency revoke mạnh, chọn authoritative check, invalidation có version/revision và fail-closed khi state không đáng tin. Đừng tuyên bố “revoke tức thời” nếu replication/caches có propagation delay chưa được kiểm soát.

### 20.5. Không tái sử dụng key ID cho secret mới

Khi rotation, cấp `client-a-k4` chứ không âm thầm đổi bytes sau `client-a-k3` nếu có thể. Secret version trùng key ID trong cached verifier có thể khiến một số nodes xác minh A3 bằng secret cũ, số khác bằng mới; audit và emergency revocation khó kiểm soát.

## 21. Failure semantics và chính sách fail-closed

Một API multi-client có nhiều dependencies: gateway, registry, secret manager, clock sync, replay authority, authorization store. Phải xác định rõ hành vi khi lỗi.

| Sự cố | Hành vi an toàn |
| --- | --- |
| Unknown key ID | Reject; không thử secret khác |
| Key ID sai grammar | Reject trước lookup |
| Duplicate Authorization/Key-ID | Reject HTTP ambiguity |
| Registry `MISSING` | Reject |
| Registry timeout/partition | Fail closed, phân loại UNAVAILABLE nội bộ |
| Secret manager unavailable | Không dùng default/old secret ngoài policy |
| Key revoked/disabled | Reject dù tag đúng |
| Verifier cache stale | Đáp ứng revocation guarantee; không dùng stale vô hạn |
| Algorithm không được cho phép | Reject, không downgrade |
| Signature malformed/truncated | Reject; không so HMAC prefix |
| Server/client clock skew lớn | Reject timestamp ngoài window; cảnh báo/config support |
| Replay store UNKNOWN | Fail closed cho API nhạy cảm |
| Redis eviction trước TTL | Nguy cơ replay; alert/capacity policy |
| Multi-region network partition | Không cho hai authorities độc lập double-admit nếu yêu cầu strong admission |
| Gateway malformed framing | Reject tại HTTP edge |
| Tenant authorization store unavailable | Không mặc định cấp quyền |
| Business response lost | Dùng operation status/idempotent retry, không bỏ replay gate |
| Client quota exhausted | Rate-limit/backpressure theo policy; không cấp quyền khác |
| Key A compromised | Revoke A và các keys liên quan, tránh gián đoạn B nếu không bị ảnh hưởng |

### 21.1. Public errors và internal reason codes

Bên ngoài không nên trả secretRef, expected MAC hoặc “key A tồn tại nhưng chữ ký B không khớp”. Có thể dùng generic unauthorized/invalid-signature semantics theo contract; nội bộ phân loại reason code đã redacted:

~~~text
AUTH_ID_INVALID
AUTH_KEY_UNKNOWN
AUTH_KEY_DISABLED_OR_REVOKED
AUTH_KEY_LOOKUP_UNAVAILABLE
AUTH_MAC_MISMATCH
AUTH_TIMESTAMP_STALE
AUTH_NONCE_REPLAY
AUTH_NONCE_STORE_UNAVAILABLE
AUTHZ_TENANT_DENIED
RATE_LIMIT_EXCEEDED
~~~

Không cần lộ chính xác status/ownership của key ID tới unauthenticated callers. Nhưng nếu mọi lỗi đều bị gộp không phân biệt trong metrics, vận hành sẽ không biết đang gặp compromise, client clock skew hay registry outage.

### 21.2. Timing side-channel và key enumeration

Một unknown key có thể reject nhanh còn known key cần secret lookup và HMAC, tạo timing differences. `MessageDigest.isEqual` giúp so tag byte an toàn hơn nhưng **không biến toàn verifier thành constant-time**. Xem xét threat model, generic error shapes, uniform limits, rate limiting và monitoring để giảm key enumeration; không tự nhận một số benchmark ít mẫu đã chứng minh không có timing leak.

## 22. Quan sát, auditing và capacity theo client

### 22.1. Metrics nên được phân tầng

| Metric | Ý nghĩa |
| --- | --- |
| `hmac_verify_success_total` | Số requests có MAC đúng theo trusted key record |
| `hmac_verify_failure_total` | MAC sai/malformed; có thể tách reason |
| `credential_lookup_error_total` | Registry/secret manager outage |
| `credential_status_reject_total` | Key không ACTIVE/overlap hợp lệ |
| `nonce_claim_new/replay/unknown` | Anti-replay behavior |
| `client_authz_denied_total` | Principal có MAC đúng nhưng thiếu quyền |
| `client_rate_limited_total` | Fairness/quota enforcement |
| `gateway_header_ambiguity_total` | Duplicate/invalid fields |
| `clock_skew_reject_total` | Timestamp freshness issues |
| `key_rotation_lag_seconds` | Còn traffic key cũ sau rollout |
| `revocation_effective_lag_seconds` | Độ trễ trạng thái REVOKED tới mọi verifier |
| `business_idempotency_conflict_total` | Cùng operation khác request/nonce |

### 22.2. Không dùng key ID raw làm label không giới hạn

Raw `X-Key-Id` trước authentication là caller-controlled, có thể tạo hàng triệu distinct values và gây metrics cardinality explosion. Với successful/authenticated requests có thể gắn trusted key/client IDs nếu số lượng được quản lý; các requests chưa xác thực nên aggregate/error-code hoặc dùng safe bounded dimensions.

### 22.3. Không log shared secret hoặc full signed request

Key ID thường không phải secret nhưng có thể tiết lộ đối tác/tenant. Log nên redacted/masked theo policy, chứa correlation ID, trusted principal, route, outcome và incident-supporting metadata. Không log HMAC secret, full raw Authorization, expected tag hoặc sensitive body; một signed request còn hạn có thể bị replay nếu lọt vào chỗ không an toàn và hệ thống chống replay chưa đủ.

### 22.4. Capacity nonce store

Một ước lượng:

\[
\text{activeNonceEntries} \approx
\sum_{c \in \text{clients}}
\mathrm{acceptedRps}_c \times \mathrm{retentionSeconds}_c
\]

Ví dụ tổng 8.000 accepted RPS và TTL 360 giây → khoảng **2.880.000 active nonce entries**, trước overhead của key strings, TTL metadata, replication, persistence, buffers, fragmentation và traffic bursts.

Không giảm TTL dưới freshness window chỉ để tiết kiệm bộ nhớ. Scale/shard đúng keyspace, monitor eviction và kiểm failure behavior theo architecture.

## 23. Ma trận kiểm thử HMAC nhiều client

| Nhóm | Tình huống | Kỳ vọng |
| --- | --- | --- |
| Onboarding | Client A mới được cấp A3 secret riêng | A3 ký đúng, không ảnh hưởng B |
| Onboarding | Hai clients có cùng secret do copy nhầm | Kiểm soát/provisioning phát hiện |
| Identity | Key A3 + secret A3 | Có thể authenticated |
| Identity | Key A3 + secret B1 | MAC mismatch |
| Identity | Key B1 + secret A3 | MAC mismatch |
| Identity | Unknown key ID + tag từ secret A3 | Reject no fallback |
| Identity | Case variant `CLIENT-A-K3` | Exact ID khác hoặc reject |
| Identity | Signed key ID bị sửa, giữ tag | MAC mismatch |
| Identity | Record registry trả ID khác requested | Reject |
| HTTP | Duplicate `X-Key-Id` khác case | Reject tại ingress |
| HTTP | Hai `Authorization` fields | Reject ambiguity |
| HTTP | CRLF/invalid signed header | Reject |
| HTTP | Scheme Basic/Bearer trên HMAC-only endpoint | Reject theo endpoint policy |
| Canonical | Same request + exact secret | Matching tag |
| Canonical | Method/path/query/body đổi | MAC mismatch/contract reject |
| Canonical | Gateway rewrite signed path | Signer/verifier boundary phải nhất quán |
| Canonical | Percent encoding, Unicode, duplicate query keys | Theo strict contract, reject ambiguity |
| Algorithm | Client khai algorithm=none | Không thay policy server |
| Audience | Orders credential gọi payments | Reject |
| Lifecycle | A3 ACTIVE và B1 ACTIVE | Độc lập, không nhầm secret |
| Lifecycle | A2 RETIRING trong overlap | Có thể verify A2 theo cutoff |
| Lifecycle | A2 sau cutoff | Reject |
| Lifecycle | A3 REVOKED với MAC đúng | Reject A3 |
| Lifecycle | A3 revoke nhưng B1 active | B1 tiếp tục hoạt động |
| Lifecycle | Stale ACTIVE sau revoke | Không accept ngoài guarantee |
| Cache | Negative cache ID mới | Activation đúng SLA |
| Cache | Refresh v9 đè REVOKED v10 | Test phát hiện/fence |
| Registry | Outage | Fail closed |
| Secret manager | Missing/timeout | Fail closed, no fallback |
| Replay | A3 nonce N lần đầu | NEW |
| Replay | A3 nonce N lần hai | REPLAY |
| Replay | B1 nonce N khi A3 đã dùng N | NEW trong key-scoped namespace |
| Replay | MAC sai nhưng nonce N mới | Không claim N |
| Replay | Shared store outage/UNKNOWN | Không xử lý business |
| Replay | Hai verifier nodes cùng A3 nonce N | At most one admission theo guarantee |
| Replay | Failover mất acknowledged nonce | Detect limitation, chọn authority phù hợp |
| Time | Timestamp now-A / now+F | Theo inclusive policy |
| Time | Timestamp stale/too future | Reject |
| Authorization | B1 hợp lệ gọi tenant A | Deny |
| Authorization | A3 scope read gọi delete | Deny |
| Idempotency | A3 N1/N2 nhưng cùng orderId | Business dedup theo operationId |
| Quota | A quá limit | Rate-limit A, tránh làm gián đoạn B |
| Gateway | Client-supplied authenticated principal header | Strip/reject spoof |
| Gateway | Backend direct-access bypass | Bị chặn |
| Audit | Unknown ID flood | Metrics bounded cardinality |
| Audit | HMAC secret trong logs | Không bao giờ |
| Incident | A secret compromised | Revoke A, issue new secret, đánh giá B độc lập |

## 24. Tình huống thực tế: ba đối tác dùng chung một Orders API

Một hệ thống phục vụ:

~~~text
Client A (tenant-A): order management system
Client B (tenant-B): third-party checkout
Client C (tenant-C): reporting worker

Public API: orders.example.test
Gateway: G1, G2
Verifier pods: V1, V2, V3
Credential registry: shared managed store
Nonce replay authority: shared atomic store
~~~

Credentials:

~~~text
A3: client-a-k3, secret KA3, audience orders-api, status ACTIVE
B1: client-b-k1, secret KB1, audience orders-api, status ACTIVE
C7: client-c-k7, secret KC7, audience orders-api, status ACTIVE
~~~

### 24.1. Tình huống A và B ký request cùng lúc

~~~text
T1: Client A signs request for tenant-A with A3 + KA3
T2: Client B signs request for tenant-B with B1 + KB1
T3: Both requests reach shared gateway
T4: Verifier selects exact credential by signed key ID
T5: Both HMAC tags match their respective secrets
T6: Replay store claims nonce independently per credential
T7: Authorization allows matching tenant actions
~~~

Đây là **happy path**. API không cần khởi tạo một HTTP endpoint hoàn toàn khác cho mỗi client, nhưng phải tạo principal/security context **độc lập theo mỗi authenticated request**. Tuyệt đối không đặt một mutable `currentClientId` static toàn process rồi dùng chung giữa threads.

### 24.2. B cố ý khai ID của A

B biết secret KB1 nhưng gửi `X-Key-Id: client-a-k3` rồi tính HMAC bằng KB1. Exact lookup chọn KA3, nên tag sai. Verifier **không** thử KB1 dù biết B cũng là client hợp lệ.

Nếu code “thử lần lượt tất cả keys cho tới khi tag khớp”, hệ thống có thể vô tình chấp nhận chữ ký B trong request khai identity A, làm sai audit/principal. Negative test phải phát hiện.

### 24.3. B ký đúng nhưng chọn tenant A

B dùng key B1, secret KB1, timestamp/nonce fresh; canonical path là `/v1/tenants/tenant-A/orders`. Verifier xác thực B thành công nhưng authorization từ chối nếu B không có grant tenant A. Đây là một **403 authorization** theo API contract, không phải lỗi HMAC.

### 24.4. A bị lộ secret còn B vẫn hoạt động

Security team revoke A3, cấp A4 secret độc lập và kiểm tra tất cả gateways/pods không còn nhận A3. Client B dùng B1 vẫn hoạt động. Nếu một old verifier pod chấp nhận A3 do stale cache, cần xử lý consistency/fail-closed; HMAC-SHA256 trên pod đó có thể không sai, nhưng **credential lifecycle policy sai**.

### 24.5. Một client quá tải toàn API

Client A gửi lượng requests vượt quota; hệ thống cần bảo vệ global capacity và tránh A chiếm toàn bộ pool của B/C. Rate limits theo principal sau auth và coarse pre-auth limits hỗ trợ isolation, nhưng không được dùng raw key ID chưa verify làm identity đáng tin.

### 24.6. Những giả định cần kiểm chứng trong production

- Không dùng chung KA3/KB1/KC7.
- Key registry trả đúng record và secret cho mỗi ID.
- Gateway G1/G2 cùng hiểu signed HTTP fields.
- Replay store shared across V1/V2/V3; không lưu nonce per-pod.
- Các clients có thể gửi cùng nonce text trong key-scoped namespaces mà không nhầm.
- HMAC pass chưa mặc định cho phép cross-tenant access.
- Khi A revoke, B/C không bị ngắt do secret coupling hoặc global kill switch sai scope.
- Audit chứa trusted client ID sau xác thực, không lấy identity từ untrusted headers.

## 25. Sai lầm triển khai thường gặp

### 25.1. “Dùng một secret cho mọi client cho dễ quản lý”

Làm tăng blast radius, khó revoke riêng từng client và gây nhầm identity. Nên cấp secrets độc lập theo client/credential boundary.

### 25.2. “Key ID có prefix tenant-A nên đây là principal A”

Tên ID không cấp quyền. Registry và authorization policy quyết định principal/tenant/scopes.

### 25.3. “Nếu signature sai thì thử secret của client khác”

Phá invariant **key ID chọn đúng một secret**, tăng risk identity confusion, tạo timing oracle và làm revocation khó kiểm soát. Exact lookup rồi reject mismatch.

### 25.4. “Header X-Client-Id là identity nếu ký HMAC”

Header value là một assertion do caller tạo. Server có thể ký nó như dữ liệu cần integrity, nhưng authenticated principal phải được lấy từ trusted record của credential đã verify và đối chiếu mọi client ID signed claims theo contract.

### 25.5. “Client nào cũng dùng nonce chung, nhưng nonce map local mỗi pod”

Local cache không chia sẻ, replay có thể lọt khi tới pod khác. Dùng shared atomic store và namespace được định nghĩa rõ.

### 25.6. “Cùng nonce N ở A phải chặn B”

Không theo contract key-scoped của bài. Replay namespace gồm key ID, nên A/B độc lập. Nếu nghiệp vụ yêu cầu global nonce uniqueness, đó là một policy khác cần được công bố/test.

### 25.7. “Redis SET NX EX bảo đảm exactly-once mọi failure”

Single-primary atomicity khác durability khi async replication/failover và khác exactly-once business effects. Phải đánh giá guarantee thật và idempotency riêng.

### 25.8. “Rotation A cần đổi key B để đồng bộ”

Không khi clients dùng credentials độc lập. Hãy rotate/revoke đúng scope; chỉ mở rộng khi có bằng chứng ảnh hưởng registry/shared secrets.

### 25.9. “Secret bị lộ vẫn an toàn nhờ timestamp/nonce”

Attacker có secret có thể ký fresh timestamp và nonce mới. Emergency revoke là biện pháp chính, không chỉ anti-replay.

### 25.10. “HMAC B đúng thì B được sửa order tenant A”

Sai. Authentication của B không thay authorization theo tenant/resource/operation.

### 25.11. “Gateway đã kiểm HMAC nên mọi X-Authenticated-* đều đáng tin”

Không nếu client có thể tự gửi những headers đó hoặc bypass gateway. Strip caller-provided identity headers, bảo vệ internal context và enforce backend trust boundary.

### 25.12. “Client timestamp sai thì cứ nới window không giới hạn”

Làm tăng replay window và nonce storage requirements. Dùng clock sync và policy có version; không tự accept giá trị quá xa tương lai.

### 25.13. “Log toàn bộ Authorization và body để debug”

Có thể làm lộ credentials, MAC tags, signed requests còn hạn hoặc dữ liệu nhạy cảm. Redact ở gateway, server, tracing và exception handling.

### 25.14. “Per-client rate limit đặt theo raw key ID trước HMAC”

Caller có thể giả key ID và tạo unbounded cardinality. Pre-auth limits dùng coarse trusted edge identity, còn per-client quotas nên dùng trusted principal sau auth.

### 25.15. “Client A đã có scope tạo order nên không cần kiểm object owner”

Action scope chưa đủ. Authorization còn cần tenant, account, resource ownership, delegation và business rules.

## 26. Bài tập thực hành

### Bài tập 1 — Thiết kế registry ba clients

Tạo một bảng/trusted registry cho A/B/C gồm key ID unique, secret refs độc lập, principal, tenant, audience, algorithm, status và validity. Vẽ luồng từ signed key ID tới authenticated principal, chỉ ra chỗ không được tin dữ liệu client gửi.

### Bài tập 2 — Cross-client signature test

Dùng A3 và B1 secret khác nhau. Tính HMAC đúng cho A và B, rồi tạo request khai ID A3 nhưng tag dùng secret B1. Test phải trả BAD_SIGNATURE và không tạo principal hoặc claim nonce.

### Bài tập 3 — Nonce namespace

Client A và B dùng nonce N (cùng 16-byte hex). Với namespace `audience:keyId:nonce`, xác minh cả hai có thể được claim lần đầu; gửi lại chính request A sẽ là REPLAY. Giải thích vì sao đây là contract key-scoped, không phải global nonce uniqueness.

### Bài tập 4 — Tenant authorization

Cho B có `orders:create` trong tenant B nhưng gửi request POST tới tenant A. Sau MAC + freshness + nonce pass, authorization phải deny. Nếu B có delegated grant cho tenant A, mô tả evidence nào phải đến từ trusted policy thay vì tự khai header.

### Bài tập 5 — Key rotation độc lập

A2 chuyển RETIRING và A3 ACTIVE, B1 không thay. Test A2 pass chỉ trong overlap, A3 pass, B1 pass, A2 sau cutoff reject và không có fallback secret A2→A3.

### Bài tập 6 — Compromise

Giả định secret A3 bị lộ. Tạo một request mới bằng A3 với timestamp fresh và nonce chưa dùng; chứng minh anti-replay có thể coi là NEW nhưng **status REVOKED** phải khiến request reject. Cấp A4 secret độc lập và xác minh B1 không bị ảnh hưởng.

### Bài tập 7 — Concurrent replay

Dùng hai verifier containers và một Redis/DB replay authority. Gửi 100 copies của cùng request A. Assert tối đa một admission trong guarantee đã công bố. Lặp với cùng nonce nhưng client B khác để kiểm namespace.

### Bài tập 8 — Gateway HTTP/2 downgrade

Gửi requests của A/B qua HTTP/2→HTTP/1.1 gateway, có case-variant duplicated Key-ID/Authorization và proxy path rewrite. Test rejects ambiguity và ký/verify trên cùng request semantics.

### Bài tập 9 — Registry outage

Fake registry ném timeout khi lookup A3. Request phải UNAVAILABLE, không fallback sang B1, không tạo principal và không ghi replay state. Sau đó test B1 khi registry ổn định, bảo đảm B hoạt động bình thường.

### Bài tập 10 — Metrics cardinality

Tạo một client hợp lệ có 10.000 requests và một unauthenticated source gửi 100.000 random key IDs. Thiết kế metrics không có label riêng cho mỗi random key ID, nhưng vẫn thống kê verified per-client requests đúng.

### Bài tập 11 — Business idempotency

Một client A gửi hai signed requests nonce N1/N2, cùng orderId O42. Anti-replay có thể nhận cả hai nhưng business phải enforce unique principal+operationId hoặc transaction tương đương, tránh tạo hai orders.

### Bài tập 12 — Test vectors độc lập

Kiểm HMAC primitive bằng RFC 4231 known-answer vectors, sau đó tạo một canonical request fixture độc lập với implementation signer và so byte-for-byte với verifier. Nếu client và server dùng cùng một canonicalizer sai, happy-path tests có thể vẫn pass; independent fixture giúp phát hiện lỗi protocol.

## 27. Checklist triển khai HMAC nhiều client

- [ ] Mỗi client/trust boundary có credential riêng; không dùng global shared secret tùy tiện.
- [ ] Mỗi rotation tạo key ID riêng và secret material độc lập.
- [ ] Key ID có strict grammar, unique scope rõ và exact-match lookup.
- [ ] Registry record chứa principal, tenant, audience, algorithm, status, validity, secret reference và owner.
- [ ] Key ID, timestamp, nonce và version marker được HMAC ràng buộc trong canonical request.
- [ ] Client/server dùng canonicalization version nhất quán cho method, URI, headers/body.
- [ ] HMAC tag strict Base64URL decode, kiểm đủ bytes, so bằng API thích hợp.
- [ ] Unknown/malformed key ID không fallback sang secret của client khác.
- [ ] Mỗi request chỉ chọn đúng một credential record/secret.
- [ ] Credential status ACTIVE/RETIRING/REVOKED/DISABLED được áp đúng policy.
- [ ] Key rotation/revocation độc lập theo client; cache invalidation có guarantee.
- [ ] Registry/KMS lỗi dẫn đến fail closed; không tạo principal từ input chưa verify.
- [ ] Principal/tenant/scopes lấy từ trusted record và policy server-side.
- [ ] Authorization kiểm action, resource/tenant/object ownership và delegation riêng.
- [ ] Replay namespace version+audience+keyId+nonce không nhập nhằng.
- [ ] Replay claim atomic trên shared authority, TTL bao phủ freshness+future skew+margin.
- [ ] Redis failover/multi-region consistency được đánh giá và kiểm thử thực tế.
- [ ] Nonce chỉ được ghi sau MAC đúng; outcome UNKNOWN không được bypass.
- [ ] Gateway reject duplicate authentication/signed headers, framing ambiguity và controls.
- [ ] Proxy rewrite không thay signed request semantics ngoài contract.
- [ ] Client-supplied identity headers bị strip; internal auth context được bảo vệ.
- [ ] Rate limits/quotas dùng trusted principal sau auth; pre-auth limits chống random key-ID floods.
- [ ] Monitoring theo client không tạo unbounded cardinality từ unauthenticated IDs.
- [ ] Không log secret/full replayable signed request/expected tag.
- [ ] Business idempotency ngăn duplicate operations dù nonce mới.
- [ ] Có tests cross-secret, unknown-key fallback, revoked-key, replay isolation, tenant authorization.
- [ ] Có e2e tests trên nhiều verifier nodes và gateway, gồm failures, clock skew, failover và rotation.

## 28. Câu hỏi tự kiểm tra

1. **Tại sao nhiều clients không nên dùng chung một HMAC secret?** Vì ai có secret cũng có thể tạo tag hợp lệ, phá isolation và tăng blast radius.
2. **Key ID có chứng minh client là ai không?** Không; đó là selector chưa đáng tin.
3. **Verifier chọn secret thế nào?** Exact-match key ID → trusted credential record → đúng secret/version/policy.
4. **HMAC tag A có thể tính bằng secret B không?** Không để xác thực A nếu secrets độc lập và verifier không fallback.
5. **Vì sao key ID phải nằm trong signed metadata?** Chống tráo selector/identity confusion và ràng buộc credential với canonical request.
6. **Một client có thể sở hữu nhiều keys không?** Có, ví dụ rotation overlap, nhưng mỗi ID chọn đúng secret riêng.
7. **Client B dùng HMAC đúng có quyền tenant A không?** Không trừ khi authorization policy có grant thích hợp.
8. **Cùng nonce N ở A/B có nhất thiết trùng replay không?** Không trong contract key-ID-scoped của bài.
9. **Lưu nonce trong local map từng pod có đủ không?** Không nếu request có thể đến pod khác.
10. **SET NX EX trên Redis tự bảo đảm exactly-once qua mọi failover không?** Không; atomic primary khác durable admission qua failover.
11. **Nonce store UNKNOWN thì sao?** Fail closed theo security policy, không chạy business.
12. **Client clock lệch 10 phút nên server tự nới window không?** Không tùy tiện; cần policy và clock sync.
13. **Key A bị revoke có phải revoke B không?** Không mặc định nếu credentials độc lập; đánh giá blast radius và shared dependencies.
14. **Attacker có stolen secret A có bị nonce chặn khi ký request mới không?** Không, nonce mới có thể vượt; revocation cần có hiệu lực.
15. **Gateway đã xác minh HMAC có thể tin header X-Role do client gửi không?** Không; role/grants phải từ trusted policy.
16. **Tại sao không thử tất cả secrets khi HMAC mismatch?** Có thể gây identity confusion và bỏ qua revocation.
17. **Rate limits per-client nên dùng key ID chưa verify không?** Không làm authoritative identity; sau auth dùng trusted principal.
18. **Key registry timeout khác unknown key thế nào?** Timeout không có kết quả đáng tin; cả hai reject nhưng monitoring khác.
19. **Hai valid requests khác nonce cùng orderId có thể tạo hai orders không?** Có nếu business thiếu idempotency.
20. **Một unit test HMAC signer/verifier cùng canonicalizer đủ không?** Không; cần independent fixtures, gateway và multi-node tests.
21. **Tại sao secret của hai clients phải được tách ở cả KMS permissions?** Để hạn chế compromise/unauthorized signing capability cross-client.
22. **Public API trả chi tiết expected HMAC có an toàn không?** Không; tránh leak thông tin và key-existence oracle.
23. **Key ID case-sensitive nhưng HTTP header name case-insensitive có mâu thuẫn không?** Không; hai tầng có quy tắc riêng.
24. **MAC đúng có nghĩa request đã được authorized chưa?** Chưa; còn freshness/replay và authorization.
25. **Khả năng thu hồi một client riêng lẻ phụ thuộc điều gì?** Credentials/secret scopes độc lập, exact lookup và revocation propagation đúng.

## 29. Tài liệu tham khảo

- **RFC 2104 — HMAC: Keyed-Hashing for Message Authentication.** MAC đối xứng với shared secret, vai trò của secret isolation.
- **RFC 4231 — HMAC-SHA-224/256/384/512 Test Vectors.** Known-answer tests cho HMAC primitive.
- **RFC 9110 — HTTP Semantics.** HTTP authentication, fields, method và request-target semantics.
- **RFC 9112 / RFC 9113 — HTTP/1.1 / HTTP/2.** Request framing, header normalization và gateway conversion.
- **RFC 3986 — Uniform Resource Identifier: Generic Syntax.** Path/query/percent encoding khi định nghĩa canonicalization.
- **NIST SP 800-57 Part 1 — Recommendation for Key Management.** Vòng đời key, rotation, compromise và key management policy.
- **OWASP Secrets Management Cheat Sheet.** Per-credential key handling, provisioning, storage, access control và audit.
- **OWASP API Security guidance.** Xác thực, phân quyền và tránh cross-tenant/cross-client access.
- **Java SE 17 API — `javax.crypto.Mac`, `SecretKeySpec`, `MessageDigest.isEqual`, `SecureRandom`, `Clock`.** Primitives Java được sử dụng trong ví dụ.
- **JUnit Jupiter User Guide.** Fixtures và assertions cho negative, boundary, concurrency và integration testing.

**Kết luận:** Để xác thực **nhiều client** bằng HMAC, hãy dùng **một signing contract thống nhất nhưng các credentials và secrets độc lập**, chọn record bằng **exact signed key ID**, ràng buộc audience và canonical HTTP semantics, rồi thực hiện full-tag verification, timestamp/nonce replay protection và trusted principal construction. Điều quan trọng không kém là **authorization theo tenant/resource**, rotation/revocation riêng từng client, quotas, gateway consistency và business idempotency. Chỉ khi những ranh giới này được kiểm thử bằng các tình huống cross-client và failure modes, HMAC mới bảo vệ đúng danh tính từng client thay vì chỉ chứng minh “có ai đó biết một secret của hệ thống”.







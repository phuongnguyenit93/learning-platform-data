# Kích hoạt credential: chuyển HMAC shared secret từ STAGED sang ACTIVE một cách an toàn

**Kích hoạt credential** là bước cho phép một cặp **client identity + key ID + shared secret** bắt đầu được sử dụng để **ký hoặc xác minh** HTTP request trong một phạm vi đã định nghĩa. Credential không trở thành hợp lệ chỉ vì secret đã được sinh, client đã nhận secret hay key ID đã xuất hiện trong registry. Để **ACTIVE**, phải có quyết định lifecycle được ủy quyền, cấu hình scope/algorithm đúng, các verifier cần thiết đã sẵn sàng, thời gian hiệu lực phù hợp và khả năng thu hồi/giám sát.

Bài thuộc chương **Credential lifecycle** của module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**. Trong module, người học thiết kế xác thực HTTP request bằng **HMAC với shared secret**, ký canonical request chứa method, URI, signed headers/body; thực hành xác minh chữ ký, timestamp/nonce chống replay, quản lý key rotation, kiểm thử proxy/gateway và phân biệt **authentication** với **authorization**. Trọng tâm bài này là **quy trình chuyển trạng thái credential sang ACTIVE** mà không mở lỗ hổng do kích hoạt sớm, lệch cấu hình hoặc đánh đồng key tồn tại với key có hiệu lực.

> **Bất biến:** Request dùng credential `STAGED`, `REVOKED`, chưa tới `activeFrom`, đã qua `expiresAt` hoặc không thuộc đúng client/audience **phải bị từ chối**, ngay cả khi người gửi thực sự biết secret và tạo ra HMAC tag đúng. Sự hiện diện của secret không thay thế lifecycle policy.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **provision**, **stage**, **activate**, **retire**, **revoke** và **expire** trong vòng đời HMAC credential.
2. Thiết kế tiêu chí kích hoạt gồm **key material**, principal được ủy quyền, phạm vi client/audience/route, algorithm, key validity, readiness của signer và từng verifier.
3. Hiểu tại sao **activate** phải có điều kiện và **atomic compare-and-set**, tránh hai controller ghi đè trạng thái hoặc vô tình tái kích hoạt key đã revoke.
4. Phân biệt **thời gian kích hoạt do server quyết định** với **timestamp do client ký**, xử lý clock skew và giới hạn key `activeFrom <= serverNow < expiresAt`.
5. Xây dựng rollout **provision-before-use**, overlap key rotation, cách xử lý lỗi đồng bộ replica và quyết định rollback an toàn.
6. Triển khai Java 17 mô phỏng registry, readiness, kiểm tra quyền activation, HMAC-SHA256 request signer/verifier, replay guard và các ca concurrency/negative.
7. Áp dụng audit, monitoring, gateway trust boundary, idempotency và authorization sau khi credential ACTIVE.

## 2. Kích hoạt credential khác tạo secret như thế nào?

Giả sử hệ thống cấp `key-2026-12` cho `partner-42` để thay `key-2026-11`:

~~~text
1) Generate       tạo shared secret B bằng CSPRNG.
2) Provision      lưu key B ở trusted key manager, cấp an toàn cho client.
3) Stage          đăng ký metadata key ID, client, audience, algorithm, validity.
4) Distribute     triển khai đúng key record/policy tới các verifier.
5) Readiness      xác minh signer nhận key, các verifier có thể lookup và
                  policy/route/clock/nonce store đã sẵn sàng.
6) Activate       cho phép VERIFY (và SIGN theo contract) từ thời điểm hợp lệ.
7) Observe        theo dõi traffic, HMAC errors, unknown IDs, replay và clock.
8) Retire/revoke  ngừng key cũ sau overlap hoặc thu hồi khẩn.
~~~

| Khái niệm | Ý nghĩa | Có mặc định được verify HMAC? |
| --- | --- | --- |
| `GENERATED` | Secret đã được tạo, có thể chưa có bản ghi. | **Không**. |
| `PROVISIONED` | Secret được lưu/cấp qua kênh an toàn. | **Không**. |
| `STAGED` | Key record và policy sẵn sàng để thử nghiệm/kiểm tra readiness. | **Không** ở production verification path. |
| **`ACTIVE`** | Quyết định kích hoạt đã commit và server clock nằm trong validity window. | **Có**, nếu scope, HMAC và replay đều đạt. |
| `RETIRING` | Đang giảm dần việc dùng key cũ trong overlap. | Có thể verify trong thời gian còn hiệu lực, tùy contract; không phát hành yêu cầu ký mới bằng key cũ. |
| `REVOKED` | Bị thu hồi bằng policy bảo mật. | **Không**, bất kể timestamp/HMAC. |
| `EXPIRED` | Hết `expiresAt`. Đây có thể là trạng thái **suy ra từ thời gian**, không nhất thiết cần một write lifecycle. | **Không**. |

**Secret tồn tại ≠ credential active ≠ HTTP request authenticated ≠ business action authorized.** Một HTTP request chỉ được xác thực khi verifier dùng **đúng active key** để xác minh **canonical HMAC** và kiểm tra timestamp/nonce; sau đó vẫn phải kiểm tra quyền của client với action/resource.

### 2.1. Vì sao không bật key ngay khi tạo?

Nếu client dùng secret mới trước khi gateway B được deploy, cùng request có thể:

~~~text
Gateway A: key-2026-12 FOUND, ACTIVE, HMAC PASS  -> 200/2xx
Gateway B: key-2026-12 NOT_FOUND hoặc STAGED     -> 401
Gateway C: key-2026-12 không đúng audience      -> 401
~~~

Điều này tạo **lỗi phụ thuộc route**; nguy hiểm hơn, một số team có thể chữa cháy bằng cách thêm `defaultSecret` hoặc thử tất cả key cũ/mới khi lookup thất bại, mở ra đường xác thực sai. Rollout đúng là **staging và propagation trước, kích hoạt sau**.

### 2.2. Activation không phải auto-enrollment

Server không được tạo/activate key chỉ vì client gửi:

~~~http
X-Client-Id: partner-42
X-Key-Id: key-2026-12
~~~

Đây chỉ là **lookup hints chưa đáng tin**. Một admin API hoặc lifecycle controller độc lập phải dùng **workload identity và quyền quản trị đã xác thực** để tạo hoặc kích hoạt key. HTTP request bên ngoài **không** được tự chọn `state=ACTIVE`, secret, algorithm, môi trường hoặc audience.

## 3. State machine và tính đơn điệu của vòng đời

Một mô hình rõ ràng:

~~~mermaid
stateDiagram-v2
    [*] --> GENERATED: CSPRNG / tạo key material
    GENERATED --> STAGED: Provision + metadata + policy
    STAGED --> ACTIVE: Authorized activation + readiness + valid time
    ACTIVE --> RETIRING: Bắt đầu chuyển client sang key mới
    RETIRING --> REVOKED: Thu hồi khẩn
    ACTIVE --> REVOKED: Thu hồi khẩn
    STAGED --> REVOKED: Hủy trước activation
    RETIRING --> EXPIRED: now >= expiresAt
    ACTIVE --> EXPIRED: now >= expiresAt
    STAGED --> EXPIRED: now >= expiresAt
    REVOKED --> [*]: Lưu audit/metadata theo retention
    EXPIRED --> [*]: Lưu audit/metadata theo retention
~~~

Đây là **sơ đồ trạng thái nghiệp vụ**, không quy định phải ghi một bản ghi `EXPIRED` tại đúng mili giây hết hạn. Verifier phải **tính điều kiện thời gian mỗi request**, không trông chờ job nền đánh dấu expired.

### 3.1. Điều kiện cho phép xác minh

~~~text
keyCanVerify(key, verificationContext) =
    key.state IN {ACTIVE, RETIRING}
    AND key.environment == server.environment
    AND key.audience == server.audience
    AND key.clientId == claimedClientId
    AND key.keyId == claimedKeyId
    AND key.algorithm == HmacSHA256
    AND key.activeFrom <= serverVerificationTime
    AND serverVerificationTime < key.expiresAt
    AND key.revoked == false
    AND key.allowedOperation/route phù hợp
~~~

Trong hợp đồng của bài, `RETIRING` vẫn được phép **verify request đã được client ký bằng key cũ** trong overlap. Điều này **không** khuyến nghị signer tiếp tục tạo request mới bằng key cũ.

### 3.2. Không hồi sinh credential đã thu hồi

Một admin không được gọi `activate` để chuyển:

~~~text
REVOKED -> ACTIVE
EXPIRED -> ACTIVE
~~~

nếu không có quy trình cấp mới/đổi key được kiểm soát. Tái sử dụng `keyId` của secret bị revoke làm phức tạp audit, cache và phản ứng sự cố. Cách an toàn là tạo **key version mới với ID mới**, giữ lịch sử key cũ.

### 3.3. Chuyển trạng thái atomic

Giả sử hai deployment controller cùng muốn kích hoạt key:

~~~text
Controller A: đọc state STAGED, version=7
Controller B: đọc state STAGED, version=7
Controller A: CAS(STAGED, version=7 -> ACTIVE, version=8) -> SUCCESS
Controller B: CAS(STAGED, version=7 -> ACTIVE, version=8) -> ALREADY_ACTIVE
~~~

Một conditional write / database transaction / CAS phải quyết định **một lần chuyển trạng thái**; lệnh gọi lặp được **idempotent**. Nếu controller B cố kích hoạt key khác khi bản ghi đã đổi version hoặc bị revoke, phải nhận **CONFLICT/REJECT**, không ghi đè dữ liệu mới.

**Lưu ý:** atomicity của **registry control plane** không tự làm mọi verifier ở các region nhìn thấy state ACTIVE đồng thời. Đây là vấn đề **data-plane consistency** riêng, cần contract activation và readiness/routing tương ứng.

## 4. Metadata, ràng buộc scope và chính sách mật mã

Một bản ghi minh họa:

~~~yaml
# PSEUDOCODE — metadata do hệ thống quản lý, không phải file triển khai thật.
credentialVersion: 1
environment: prod
audience: payments-api
clientId: partner-42
keyId: key-2026-12
secretRef: kms://internal/prod/payments-api/partner-42/key-2026-12
algorithm: HmacSHA256
state: STAGED
activeFrom: "2026-11-28T02:01:00Z"
expiresAt: "2027-01-01T00:00:00Z"
allowedOperations:
  - "POST:/v1/payments"
signerProvisioned: true
requiredVerifierIds:
  - "gateway-a"
  - "gateway-b"
readyVerifierIds: []
~~~

`secretRef` ở ví dụ chỉ là **internal reference**, không phải header để client quyết định đường dẫn KMS. Trường `state` và readiness thuộc **control plane được bảo vệ**, không phải giá trị người dùng có thể yêu cầu trong HTTP.

| Trường | Chốt khi stage/activate | Lỗi nếu bỏ qua |
| --- | --- | --- |
| Environment `prod` | Key không được dùng ở dev/staging. | Lộ một môi trường có thể ảnh hưởng môi trường khác. |
| Audience `payments-api` | Ngăn cross-service use. | API khác dùng nhầm secret hoặc policy. |
| Client ID | Gắn key cho chủ thể cụ thể. | Client A mạo danh bằng ID của B. |
| Key ID | Chọn **đúng** secret và version. | Fallback/mixed key làm rotation khó kiểm soát. |
| Algorithm `HmacSHA256` | Policy server-fixed, full tag 32 byte. | Downgrade/algorithm confusion. |
| Allowed operation | Key dùng cho route/method đã cấp. | Secret bị lạm dụng cho API nhạy cảm khác. |
| `activeFrom` / `expiresAt` | Chuẩn UTC Instant và quy ước inclusive/exclusive. | Chấp nhận trước hoặc sau hiệu lực. |
| State + revision | CAS transition; ngăn race. | Re-activate key bị revoke/cập nhật chồng. |
| Signer provisioned | Client đã sẵn sàng dùng key an toàn. | Key active nhưng client không ký được. |
| Verifier readiness | Các trusted ingress cần thiết đã có key/policy. | Routing ngẫu nhiên tạo 401, vận hành bật fallback. |

**Secret entropy:** với HMAC-SHA256, tạo secret bằng CSPRNG, chẳng hạn 32 byte ngẫu nhiên. Không dùng key ID, UUID công khai, passphrase dễ đoán hoặc timestamp làm secret. Chỉ những workload cần `SIGN`/`VERIFY` mới được sử dụng key/capability, theo access policy.

## 5. Quy trình kích hoạt theo hai pha: chuẩn bị và commit

### 5.1. Pha A — chuẩn bị (STAGED)

1. Controller có workload identity hợp lệ (IAM/OIDC/mTLS/SSO+MFA theo bối cảnh), **không** là HTTP client tự khai `X-Client-Id`.
2. Đọc/đối chiếu metadata với request cấp key đã được duyệt, giới hạn client, audience, environment, route và HMAC algorithm.
3. Sinh/đăng ký secret trong secret manager hoặc KMS/HSM, đặt policy least privilege; client nhận secret qua kênh provisioning xác thực/mã hóa nếu dùng raw-key HMAC.
4. Tạo bản ghi key version **STAGED**, `activeFrom` và `expiresAt` đã được công bố, **không tự bật verify**.
5. Triển khai registry snapshot/key reference và policy tới các verifier sẽ nhận traffic: gateway, pod, shard hoặc region.
6. Mỗi verifier **độc lập chứng minh readiness** qua kênh control plane tin cậy: lookup đúng scoped key, algorithm/route/policy, khả năng truy cập secret manager, time-sync và nonce store. Không dùng request tự gửi `ready=true`.
7. Kiểm tra client signer đã provisioned, API contract/canonical test vectors đã thống nhất, monitoring và phương án rollback/revoke có sẵn.

### 5.2. Pha B — commit ACTIVE

Controller kích hoạt bằng **conditional operation** có phiên bản:

~~~text
activate(locator, expectedVersion, actor, now):
    authenticate and authorize actor for ACTIVATE on locator
    load key record at expectedVersion
    require current state == STAGED
    require signerProvisioned
    require all REQUIRED live verifier readiness attested
    require algorithm/audience/route/expiry/clock policy valid
    require now >= activeFrom and now < expiresAt
    COMMIT state = ACTIVE, version = expectedVersion+1 atomically
    audit transition and publish config/version update
~~~

Lời gọi lặp trên bản ghi đã ACTIVE nên trả **ALREADY_ACTIVE** mà không reset `activeFrom` hoặc thay secret. Nếu state đã `REVOKED`, `EXPIRED` hoặc revision không như mong đợi, trả lỗi thích hợp — **không** tự “sửa” theo yêu cầu client.

### 5.3. Sau commit: kiểm tra data plane

- Gửi **canary signed request** tới các verifier thuộc traffic set, kiểm tra HMAC/freshness/nonce/authorization và HTTP response.
- Theo dõi unknown key ID, key-not-active, signature mismatch, clock skew, latency KMS, nonce claim failure và tỷ lệ request theo gateway/region.
- Không quảng bá key active cho client rộng rãi trước khi các route tiếp nhận key đã sẵn sàng theo SLA.
- Nếu phát hiện một gateway chưa sẵn sàng, đưa nó ra khỏi traffic **theo routing policy** hoặc tạm **dừng client cutover**; không tắt authentication.

### 5.4. Readiness không đồng nghĩa strong consistency

Nhận ACK từ `gateway-a` và `gateway-b` lúc T0 không đảm bảo sau đó không có pod mới với stale config hoặc region mất kết nối khi commit. Hệ thống thật phải xác định **những replica nào đang phục vụ**, phiên bản registry tối thiểu được chấp nhận, sức khỏe của control/data plane và fail-safe routing.

Nếu đặc tả đòi một activation **đồng nhất toàn cục**, dùng authoritative strongly consistent key-state check hoặc deployment/routing barrier phù hợp; chỉ dùng eventual cache với TTL dài mà tuyên bố “đồng bộ tức thì” là không chính xác.

## 6. Thời điểm kích hoạt và timestamp được ký

Credential có hai trục thời gian khác nhau:

~~~text
Credential lifecycle:
    activeFrom <= serverVerificationInstant < expiresAt

Signed request freshness:
    serverNow - P <= signedTimestamp <= serverNow + F
~~~

Ví dụ:

~~~text
activeFrom     = 2026-11-28T02:01:00Z
expiresAt      = 2027-01-01T00:00:00Z
serverNow      = 2026-11-28T02:00:00Z
signedTs       = 2026-11-28T02:00:00Z
HMAC           = VALID

Result         = REJECT (key chưa active dù timestamp fresh)
~~~

**Không dùng `signedTimestamp` do client tự chọn để quyết định key đã active chưa.** Một request có timestamp `02:10` trong tương lai chưa làm key bắt đầu hiệu lực trước `activeFrom` khi server đang ở `02:00`. Ngược lại, server đang ở `02:20` không được nhận key đã revoked chỉ vì request có timestamp `01:00` trước thời điểm revoke.

### 6.1. Có cần yêu cầu signed timestamp sau activeFrom?

Ngoài kiểm tra trạng thái tại **server verification time**, một contract có thể thêm:

~~~text
signedTimestamp >= activeFrom.epochSecond
~~~

để **từ chối request được ký với timestamp trước thời điểm kích hoạt**, dù nó được gửi khi key đã active và freshness vẫn pass. Bài thực hành **chọn thêm kiểm tra này** nhằm thể hiện ranh giới activation rõ ràng. Nếu hệ thống có offline signing hoặc clock skew riêng, phải thiết kế policy này có chủ ý thay vì lặng lẽ bỏ qua.

**Không** lấy signed timestamp làm điều kiện **thay thế** `serverNow >= activeFrom`: attacker có secret chưa được kích hoạt vẫn có thể ký timestamp ở tương lai nằm trong tolerance.

### 6.2. Clock skew và rollback

Nếu `gateway-a` nhanh 45 giây còn `gateway-b` chậm 45 giây, chúng có thể khác nhau về kết quả `activeFrom` gần ranh giới. Cần NTP/clock monitoring, drift threshold và kế hoạch staged rollout; có thể đợi **buffer** trước khi công bố cutover để giảm chênh lệch. Khi clock vượt ngưỡng tin cậy, **fail closed/rút gateway khỏi traffic** theo policy thay vì mở rộng vô hạn freshness window.

Phép tính thời gian dùng `Instant` hoặc epoch seconds với kiểm tra overflow. Không lấy timezone local hoặc `System.nanoTime()` thay epoch seconds.

### 6.3. Ranh giới inclusive/exclusive

| Điều kiện | Biên | Kết quả |
| --- | --- | --- |
| `now == activeFrom` | Biên bắt đầu **inclusive** | Key có thể được verify nếu ACTIVE. |
| `now < activeFrom` | Chưa tới hạn | Deny. |
| `now == expiresAt` | Biên kết thúc **exclusive** | Deny. |
| `now > expiresAt` | Đã hết hạn | Deny. |
| `ts == now-300` | Biên freshness quá khứ **inclusive** | Có thể pass nếu key cũng active. |
| `ts == now+60` | Biên freshness tương lai **inclusive** | Có thể pass nếu key cũng active. |
| `ts < activeFrom` trong contract bài | Timestamp ký trước activation | Deny dù server đã active. |

## 7. HMAC signing contract trong thời gian chuyển trạng thái

Một request minh họa:

~~~http
POST /v1/payments?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-42
X-Key-Id: key-2026-12
X-Timestamp: 1795831260
X-Nonce: 00112233445566778899aabbccddeeff
X-Content-SHA256: <64-lowercase-hex-body-digest>
X-Signature: <base64-full-hmac-sha256-tag>

{"orderId":"ord-123","amount":50000}
~~~

`<...>` là placeholder; `X-Signature` thực tế là Base64 padded của **32 byte HMAC-SHA256**, gồm 44 ký tự. Canonical request **HMAC-CREDENTIAL-ACTIVATION-V1**:

~~~text
HMAC-CREDENTIAL-ACTIVATION-V1
POST
/v1/payments?currency=VND
audience:payments-api
x-client-id:partner-42
x-key-id:key-2026-12
x-timestamp:1795831260
x-nonce:00112233445566778899aabbccddeeff
content-type:application/json
x-content-sha256:<sha256-body-hex>
~~~

Các dòng được nối bằng **LF (0x0A)**, UTF-8 và **không có LF cuối**. Mọi client/verifier phải dùng cùng byte representation:

- Method `POST`, **raw URI/query** và HTTP body bytes thực nhận ở trusted ingress.
- Audience do **server policy** chọn, không lấy từ header client tự khai.
- Client ID và key ID phải là **signed fields**; key ID không được làm lựa chọn thuật toán hay secret không kiểm soát.
- Timestamp và nonce được ký vào cùng transcript; nonce cần entropy từ CSPRNG, không trùng nhau giữa các request mới.
- `Content-Type` và SHA-256 của body bytes thực nhận được ký; không serialize JSON lại một cách tùy ý sau khi xác minh.
- Signature field **không** nằm trong chính canonical (không tự tham chiếu).

### 7.1. Người gửi biết secret nhưng credential STAGED

Client được cấp secret mới trong pha provisioning có thể thử ký request **trước activation**. Verifier vẫn tính được HMAC đúng về mặt toán học nhưng phải **deny theo state**. Đây là mục tiêu bảo mật, không phải lỗi thuật toán.

### 7.2. Key rotation overlap

Trong khoảng chuyển đổi, key cũ `key-2026-11` có thể `ACTIVE/RETIRING` và key mới `key-2026-12` `ACTIVE`. Verifier chọn **đúng key ID mà request ký**; không tự thử lần lượt hai secret để cứu request sử dụng ID chưa active. Nonce store cần namespace **(audience, authenticated clientId, nonce)**, không tách theo key ID, tránh replay cùng nonce qua rotation.

## 8. Activation authority, secret policy và vận hành KMS

**Kích hoạt là thao tác quản trị**, có thể thay đổi khả năng phát sinh side effect với secret mới. Nên tách quyền:

| Role | Vai trò | Điều không được mặc định |
| --- | --- | --- |
| `credential-provisioner` | Sinh/cấp key material, đăng ký `STAGED`. | Không tự kích hoạt production không phê duyệt. |
| `credential-activator` | Kiểm tra readiness/policy rồi commit ACTIVE. | Không cần export raw secret. |
| `client-signer` | Sử dụng key đã được cấp và hiệu lực để ký request. | Không tự đổi activation state ở server. |
| `hmac-verifier` | Chọn đúng active key để verify. | Không tự grant mọi key hoặc bỏ qua readiness. |
| `rotation-controller` | Chuyển đổi key và retire/revoke theo policy. | Không mở lại revoked key bằng default fallback. |
| `security-responder` | Revoke khẩn, điều tra và audit. | Không dùng quyền khẩn cấp thành credential wildcard vĩnh viễn. |

### 8.1. Secret không được lộ trong activation

API activation nhận **key locator + expected version + policy context**; **không** gửi lại raw shared secret trong URL/header/log của request admin. Nếu cần provision secret cho client, dùng **kênh được xác thực/mã hóa riêng**. Key manager kiểm tra principal và scope, không nhận `kid` HTTP làm arbitrary file/KMS path.

Nếu key nằm trong KMS/HSM **non-exportable**, verifier có thể dùng `VerifyMac` thay vì tải raw key. Nếu verifier đã giữ raw HMAC secret, nó **có khả năng tạo MAC** về mặt mật mã dù IAM chỉ đặt tên operation `VERIFY`; phải hiểu giới hạn này khi thiết kế separation of duties.

### 8.2. Lỗi lookup cần phân loại

~~~text
NOT_FOUND      -> unknown key ID; reject authentication
FOUND_STAGED   -> known key but not active; reject
FOUND_ACTIVE   -> check validity/scope; HMAC verify
FOUND_REVOKED  -> reject, never fallback
ACCESS_DENIED  -> verifier workload không có quyền dùng key; fail closed
UNAVAILABLE    -> KMS/registry outage; fail closed, operational error
~~~

Không đổi `UNAVAILABLE` thành “unknown” rồi tự dùng key mặc định. Nếu proxy/backend có cache key hoặc policy, phải có **TTL/invalidation đáp ứng revoke SLA**; một replica giữ ACTIVE trong khi control plane đã revoke là rủi ro cần kiểm thử.

## 9. Java 17: quản lý STAGED → ACTIVE và xác minh HMAC theo key state

Chương trình **`CredentialActivationExample.java`** minh họa:

- Controller có **trusted principal** được phép activate; client signer không tự activate.
- Registry stage key record, nhận readiness từ hai verifier và signer đã được cấp secret.
- `activate` dùng `ConcurrentHashMap.computeIfPresent` để kiểm tra và chuyển **STAGED → ACTIVE** một cách atomic trong **một JVM**, có version và kết quả idempotent.
- Verifier chỉ nhận request nếu `state` và `activeFrom/expiresAt` đúng theo **server clock**; kiểm tra canonical HMAC, timestamp, nonce và key ID.
- Kiểm thử hai controller concurrent, pre-activation, future activation, wrong scope, replay, rotation, revoked/expired, invalid signature và store outage.

**Giới hạn:** Đây là **mô hình unit test trong một JVM**, **không** có shared persistent registry, distributed CAS, KMS, NTP monitoring hoặc nonce store bền vững. `readyReplicas` chỉ mô phỏng assertion từ trusted control plane, không chứng minh mạnh cho cluster. Không dùng trực tiếp làm production gateway.

### 9.1. Mã nguồn đầy đủ

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Base64;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class CredentialActivationExample {
    private static final SecureRandom RNG = new SecureRandom();
    private static final String ENV = "prod";
    private static final String AUD = "payments-api";
    private static final String CLIENT = "partner-42";
    private static final String METHOD = "POST";
    private static final String TARGET = "/v1/payments?currency=VND";
    private static final String TYPE = "application/json";
    private static final String OLD = "key-2026-11";
    private static final String NEW = "key-2026-12";
    private static final String ADMIN =
        "workload:credential-activator-prod";
    private static final Set<String> REQUIRED =
        Set.of("gateway-a", "gateway-b");
    private static final long PAST = 300L;
    private static final long FUTURE = 60L;
    private static final long MARGIN = 10L;

    enum State { STAGED, ACTIVE, RETIRING, REVOKED }
    enum ActivationResult {
        ACTIVATED, ALREADY_ACTIVE, NOT_READY, NOT_YET_TIME,
        EXPIRED, REVOCATION_BLOCKED, VERSION_CONFLICT,
        NOT_FOUND, ACCESS_DENIED, STORE_UNAVAILABLE
    }
    enum VerifyResult {
        ACCEPTED, MALFORMED, OUTSIDE_TIME_WINDOW, UNKNOWN_KEY,
        INACTIVE_KEY, BAD_SIGNATURE, REPLAY, STORE_UNAVAILABLE
    }

    record Locator(String env, String audience,
                   String clientId, String keyId) {}
    record Credential(
        Locator locator, byte[] secret, State state,
        Instant activeFrom, Instant expiresAt,
        boolean signerReady, Set<String> readyReplicas, long version
    ) {}
    record Request(
        String method, String target, String clientId,
        String keyId, String timestamp, String nonce,
        String contentType, String bodyHash,
        String signature, byte[] body
    ) {}

    // Chỉ mô phỏng IAM: principal phải là platform-authenticated identity.
    static boolean authorizedActivator(String actor) {
        return ADMIN.equals(actor);
    }

    // Chỉ bảo đảm atomicity trong một JVM.
    static final class Registry {
        private final ConcurrentHashMap<Locator, Credential> map =
            new ConcurrentHashMap<>();
        private volatile boolean available = true;

        void setAvailable(boolean value) {
            available = value;
        }

        void stage(Locator loc, byte[] secret,
                Instant from, Instant until) {
            if (!ENV.equals(loc.env()) || !AUD.equals(loc.audience())
                || !CLIENT.equals(loc.clientId())
                || !validId(loc.keyId()) || secret == null
                || secret.length < 32 || from == null || until == null
                || !from.isBefore(until)) {
                throw new IllegalArgumentException("Invalid staged key");
            }
            Credential staged = new Credential(
                loc, secret.clone(), State.STAGED, from, until,
                false, Set.of(), 1L);
            if (map.putIfAbsent(loc, staged) != null) {
                throw new IllegalStateException(
                    "Key ID already registered; never reuse");
            }
        }

        // Trusted provisioning controller; caller from control plane.
        void signerProvisioned(Locator loc) {
            map.computeIfPresent(loc, (key, old) ->
                old.state() == State.STAGED
                    ? new Credential(old.locator(), old.secret(),
                        old.state(), old.activeFrom(), old.expiresAt(),
                        true, old.readyReplicas(), old.version())
                    : old);
        }

        void verifierReady(Locator loc, String replica) {
            if (!REQUIRED.contains(replica)) {
                throw new IllegalArgumentException(
                    "Unexpected replica readiness");
            }
            map.computeIfPresent(loc, (key, old) -> {
                if (old.state() != State.STAGED) {
                    return old;
                }
                Set<String> updated = new HashSet<>(
                    old.readyReplicas());
                updated.add(replica);
                return new Credential(
                    old.locator(), old.secret(), old.state(),
                    old.activeFrom(), old.expiresAt(),
                    old.signerReady(), Set.copyOf(updated), old.version());
            });
        }

        ActivationResult activate(String actor, Locator loc,
                long expectedVersion, Instant now) {
            if (!authorizedActivator(actor)) {
                return ActivationResult.ACCESS_DENIED;
            }
            if (!available) {
                return ActivationResult.STORE_UNAVAILABLE;
            }
            AtomicReference<ActivationResult> decision =
                new AtomicReference<>(ActivationResult.NOT_FOUND);
            map.computeIfPresent(loc, (key, old) -> {
                if (old.state() == State.ACTIVE) {
                    decision.set(ActivationResult.ALREADY_ACTIVE);
                    return old;
                }
                if (old.state() == State.REVOKED ||
                    old.state() == State.RETIRING) {
                    decision.set(ActivationResult.REVOCATION_BLOCKED);
                    return old;
                }
                if (old.version() != expectedVersion) {
                    decision.set(ActivationResult.VERSION_CONFLICT);
                    return old;
                }
                if (!old.signerReady() ||
                    !old.readyReplicas().containsAll(REQUIRED)) {
                    decision.set(ActivationResult.NOT_READY);
                    return old;
                }
                if (now.isBefore(old.activeFrom())) {
                    decision.set(ActivationResult.NOT_YET_TIME);
                    return old;
                }
                if (!now.isBefore(old.expiresAt())) {
                    decision.set(ActivationResult.EXPIRED);
                    return old;
                }
                decision.set(ActivationResult.ACTIVATED);
                return new Credential(old.locator(), old.secret(),
                    State.ACTIVE, old.activeFrom(), old.expiresAt(),
                    old.signerReady(), old.readyReplicas(),
                    old.version() + 1);
            });
            return decision.get();
        }

        // Controller sở hữu revoke; demo không triển khai IAM riêng.
        void revoke(Locator loc) {
            map.computeIfPresent(loc, (key, old) ->
                new Credential(old.locator(), old.secret(),
                    State.REVOKED, old.activeFrom(), old.expiresAt(),
                    old.signerReady(), old.readyReplicas(),
                    old.version() + 1));
        }

        void retire(Locator loc) {
            map.computeIfPresent(loc, (key, old) ->
                old.state() == State.ACTIVE
                    ? new Credential(old.locator(), old.secret(),
                        State.RETIRING, old.activeFrom(), old.expiresAt(),
                        old.signerReady(), old.readyReplicas(),
                        old.version() + 1)
                    : old);
        }

        Credential lookup(Locator loc) {
            if (!available) {
                throw new IllegalStateException("Registry unavailable");
            }
            return map.get(loc);
        }
    }

    // Test-only local store. Production: distributed atomic claim + TTL.
    static final class Nonces {
        private final ConcurrentHashMap<String, Long> expiries =
            new ConcurrentHashMap<>();
        boolean claim(String audience, String clientId, String nonce,
                long now, long expiresAt) {
            if (expiresAt <= now) {
                return false;
            }
            String scope =
                audience.length() + ":" + audience +
                clientId.length() + ":" + clientId +
                nonce.length() + ":" + nonce;
            AtomicBoolean created = new AtomicBoolean(false);
            expiries.compute(scope, (key, old) -> {
                if (old != null && old > now) {
                    return old;
                }
                created.set(true);
                return expiresAt;
            });
            return created.get();
        }
    }

    static boolean validId(String value) {
        return value != null &&
            value.matches("[a-z0-9][a-z0-9-]{0,39}");
    }

    static byte[] secret() {
        byte[] bytes = new byte[32];
        RNG.nextBytes(bytes);
        return bytes;
    }

    static String nonce() {
        byte[] bytes = new byte[16];
        RNG.nextBytes(bytes);
        return HexFormat.of().formatHex(bytes);
    }

    static String sha256Hex(byte[] bytes)
            throws GeneralSecurityException {
        return HexFormat.of().formatHex(
            MessageDigest.getInstance("SHA-256").digest(bytes));
    }

    static byte[] mac(byte[] key, String message)
            throws GeneralSecurityException {
        Mac hmac = Mac.getInstance("HmacSHA256");
        hmac.init(new SecretKeySpec(key, "HmacSHA256"));
        return hmac.doFinal(
            message.getBytes(StandardCharsets.UTF_8));
    }

    static Long parseTs(String text) {
        if (text == null || !text.matches("[1-9][0-9]{0,18}")) {
            return null;
        }
        try {
            return Long.parseLong(text);
        } catch (NumberFormatException bad) {
            return null;
        }
    }

    static boolean fresh(long ts, long now) {
        try {
            return ts >= Math.subtractExact(now, PAST)
                && ts <= Math.addExact(now, FUTURE);
        } catch (ArithmeticException overflow) {
            return false;
        }
    }

    static String canonical(Request r, String bodyHash) {
        if (r == null || !METHOD.equals(r.method())
            || !TARGET.equals(r.target())
            || !TYPE.equals(r.contentType())
            || !CLIENT.equals(r.clientId())
            || !validId(r.keyId())
            || parseTs(r.timestamp()) == null
            || r.nonce() == null
            || !r.nonce().matches("[0-9a-f]{32}")
            || bodyHash == null
            || !bodyHash.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException("Invalid canonical");
        }
        return String.join("\n",
            "HMAC-CREDENTIAL-ACTIVATION-V1",
            r.method(), r.target(),
            "audience:" + AUD,
            "x-client-id:" + r.clientId(),
            "x-key-id:" + r.keyId(),
            "x-timestamp:" + r.timestamp(),
            "x-nonce:" + r.nonce(),
            "content-type:" + r.contentType(),
            "x-content-sha256:" + bodyHash);
    }

    static byte[] decodeTag(String encoded) {
        if (encoded == null ||
            !encoded.matches("[A-Za-z0-9+/]{43}=")) {
            return null;
        }
        try {
            byte[] bytes = Base64.getDecoder().decode(encoded);
            if (bytes.length != 32 ||
                !Base64.getEncoder().encodeToString(bytes)
                    .equals(encoded)) {
                return null;
            }
            return bytes;
        } catch (IllegalArgumentException bad) {
            return null;
        }
    }

    // Client demo có secret đã provision và chỉ ký khi được hướng dẫn.
    // Client có thể cố ký trước activation; server vẫn PHẢI từ chối.
    static Request sign(byte[] key, String kid, Clock clock,
            String nonce, byte[] body)
            throws GeneralSecurityException {
        String ts = Long.toString(clock.instant().getEpochSecond());
        String hash = sha256Hex(body);
        Request unsigned = new Request(
            METHOD, TARGET, CLIENT, kid, ts, nonce,
            TYPE, hash, "", body.clone());
        String tag = Base64.getEncoder().encodeToString(
            mac(key, canonical(unsigned, hash)));
        return new Request(
            METHOD, TARGET, CLIENT, kid, ts, nonce,
            TYPE, hash, tag, body.clone());
    }

    static VerifyResult verify(Request r, Registry registry,
            Clock serverClock, Nonces nonces)
            throws GeneralSecurityException {
        if (r == null || r.body() == null ||
            r.body().length > 65536 || !CLIENT.equals(r.clientId()) ||
            !validId(r.keyId())) {
            return VerifyResult.MALFORMED;
        }
        Long ts = parseTs(r.timestamp());
        byte[] supplied = decodeTag(r.signature());
        if (ts == null || supplied == null) {
            return VerifyResult.MALFORMED;
        }
        Instant nowInstant = serverClock.instant();
        long now = nowInstant.getEpochSecond();
        if (!fresh(ts, now)) {
            return VerifyResult.OUTSIDE_TIME_WINDOW;
        }

        final String message;
        try {
            String actualBodyHash = sha256Hex(r.body());
            if (!actualBodyHash.equals(r.bodyHash())) {
                return VerifyResult.BAD_SIGNATURE;
            }
            message = canonical(r, actualBodyHash);
        } catch (IllegalArgumentException bad) {
            return VerifyResult.MALFORMED;
        }
        Locator loc = new Locator(ENV, AUD, r.clientId(), r.keyId());
        final Credential key;
        try {
            key = registry.lookup(loc);
        } catch (IllegalStateException outage) {
            return VerifyResult.STORE_UNAVAILABLE;
        }
        if (key == null) {
            return VerifyResult.UNKNOWN_KEY;
        }
        if (!(key.state() == State.ACTIVE
                || key.state() == State.RETIRING)
            || nowInstant.isBefore(key.activeFrom())
            || !nowInstant.isBefore(key.expiresAt())
            || Instant.ofEpochSecond(ts).isBefore(key.activeFrom())
            || !loc.equals(key.locator())) {
            return VerifyResult.INACTIVE_KEY;
        }
        byte[] expected = mac(key.secret(), message);
        if (expected.length != 32 ||
            !MessageDigest.isEqual(expected, supplied)) {
            return VerifyResult.BAD_SIGNATURE;
        }
        final long nonceExpiry;
        try {
            nonceExpiry = Math.addExact(ts,
                Math.addExact(PAST, MARGIN));
        } catch (ArithmeticException overflow) {
            return VerifyResult.OUTSIDE_TIME_WINDOW;
        }
        return nonces.claim(AUD, r.clientId(), r.nonce(),
                now, nonceExpiry)
            ? VerifyResult.ACCEPTED : VerifyResult.REPLAY;
    }

    static Request tamperBody(Request r, byte[] changed) {
        return new Request(r.method(), r.target(), r.clientId(),
            r.keyId(), r.timestamp(), r.nonce(), r.contentType(),
            r.bodyHash(), r.signature(), changed);
    }

    static Request tamperClient(Request r, String client) {
        return new Request(r.method(), r.target(), client,
            r.keyId(), r.timestamp(), r.nonce(), r.contentType(),
            r.bodyHash(), r.signature(), r.body());
    }

    static void check(boolean predicate, String description) {
        if (!predicate) {
            throw new AssertionError(description);
        }
    }

    static void knownAnswerRfc4231() throws Exception {
        byte[] key = new byte[20];
        Arrays.fill(key, (byte) 0x0b);
        String actual = HexFormat.of().formatHex(mac(key, "Hi There"));
        String expected =
            "b0344c61d8db38535ca8afceaf0bf12" +
            "b881dc200c9833da726e9376c2e32cff7";
        check(actual.equals(expected),
            "RFC 4231 HMAC-SHA256 known-answer");
    }

    public static void main(String[] args) throws Exception {
        knownAnswerRfc4231();
        Clock base = Clock.fixed(
            Instant.parse("2026-11-28T02:00:00Z"), ZoneOffset.UTC);
        Instant t0 = base.instant();
        byte[] oldSecret = secret();
        byte[] newSecret = secret();
        byte[] body =
            "{\"orderId\":\"ord-123\",\"amount\":50000}"
                .getBytes(StandardCharsets.UTF_8);
        Locator oldLoc = new Locator(ENV, AUD, CLIENT, OLD);
        Locator newLoc = new Locator(ENV, AUD, CLIENT, NEW);
        Registry registry = new Registry();

        registry.stage(oldLoc, oldSecret, t0.minusSeconds(1800),
            t0.plusSeconds(86400));
        // Dù key cũ từng được provision, STAGED vẫn từ chối tag đúng.
        Request stagedOld = sign(oldSecret, OLD, base, nonce(), body);
        check(verify(stagedOld, registry, base, new Nonces())
                == VerifyResult.INACTIVE_KEY,
            "STAGED must not accept valid HMAC");

        // Actor không có quyền không thể kích hoạt.
        check(registry.activate("workload:external-client", oldLoc,
                1, t0) == ActivationResult.ACCESS_DENIED,
            "Client cannot self-activate credential");
        check(registry.activate(ADMIN, oldLoc, 1, t0)
                == ActivationResult.NOT_READY,
            "Activation must require readiness");
        registry.signerProvisioned(oldLoc);
        registry.verifierReady(oldLoc, "gateway-a");
        check(registry.activate(ADMIN, oldLoc, 1, t0)
                == ActivationResult.NOT_READY,
            "Every required verifier must be ready");
        registry.verifierReady(oldLoc, "gateway-b");
        check(registry.activate(ADMIN, oldLoc, 2, t0)
                == ActivationResult.VERSION_CONFLICT,
            "Stale CAS version must not overwrite metadata");
        check(registry.activate(ADMIN, oldLoc, 1, t0)
                == ActivationResult.ACTIVATED,
            "Readiness + valid time must activate key");
        check(registry.activate(ADMIN, oldLoc, 1, t0)
                == ActivationResult.ALREADY_ACTIVE,
            "Repeated activation must be idempotent");
        check(verify(stagedOld, registry, base, new Nonces())
                == VerifyResult.ACCEPTED,
            "Same valid HMAC may pass after activation");

        HttpRequest http = HttpRequest.newBuilder(
                URI.create("https://api.example.test" + TARGET))
            .header("Content-Type", stagedOld.contentType())
            .header("X-Client-Id", stagedOld.clientId())
            .header("X-Key-Id", stagedOld.keyId())
            .header("X-Timestamp", stagedOld.timestamp())
            .header("X-Nonce", stagedOld.nonce())
            .header("X-Content-SHA256", stagedOld.bodyHash())
            .header("X-Signature", stagedOld.signature())
            .POST(HttpRequest.BodyPublishers.ofByteArray(stagedOld.body()))
            .build(); // Không gửi network request.
        check(METHOD.equals(http.method()), "HTTP method");

        // Replay: key active không có nghĩa nonce có thể dùng nhiều lần.
        Nonces shared = new Nonces();
        check(verify(stagedOld, registry, base, shared)
                == VerifyResult.ACCEPTED, "First nonce claim");
        check(verify(stagedOld, registry, base, shared)
                == VerifyResult.REPLAY, "Duplicate nonce rejected");

        // Body tamper không được chiếm trước nonce.
        Nonces tamperGuard = new Nonces();
        byte[] changedBody = stagedOld.body().clone();
        changedBody[0] ^= 1;
        check(verify(tamperBody(stagedOld, changedBody), registry,
                base, tamperGuard) == VerifyResult.BAD_SIGNATURE,
            "Tampered body must fail");
        check(verify(stagedOld, registry, base, tamperGuard)
                == VerifyResult.ACCEPTED,
            "Invalid HMAC cannot burn genuine nonce");
        check(verify(tamperClient(stagedOld, "partner-77"), registry,
                base, new Nonces()) == VerifyResult.MALFORMED,
            "Wrong identity must not borrow another client's key");

        // New key: client đã provision nhưng còn STAGED, chưa tới giờ.
        registry.stage(newLoc, newSecret, t0.plusSeconds(60),
            t0.plusSeconds(86400 * 7L));
        registry.signerProvisioned(newLoc);
        registry.verifierReady(newLoc, "gateway-a");
        registry.verifierReady(newLoc, "gateway-b");
        check(registry.activate(ADMIN, newLoc, 1, t0)
                == ActivationResult.NOT_YET_TIME,
            "Cannot activate before activeFrom");
        Request earlyNew = sign(newSecret, NEW, base, nonce(), body);
        check(verify(earlyNew, registry, base, new Nonces())
                == VerifyResult.INACTIVE_KEY,
            "Valid HMAC from future key cannot activate itself");
        Clock atActivation = Clock.offset(base,
            Duration.ofSeconds(60));
        check(registry.activate(ADMIN, newLoc, 1,
                atActivation.instant()) == ActivationResult.ACTIVATED,
            "New key activation at inclusive activeFrom");
        check(verify(earlyNew, registry, atActivation, new Nonces())
                == VerifyResult.INACTIVE_KEY,
            "Signed timestamp before activeFrom rejected by contract");
        Request activeNew = sign(newSecret, NEW, atActivation,
            nonce(), body);
        check(verify(activeNew, registry, atActivation, new Nonces())
                == VerifyResult.ACCEPTED,
            "New key active; full MAC and fresh nonce pass");

        // Key cũ có thể RETIRING trong overlap và vẫn verify.
        registry.retire(oldLoc);
        Request overlapOld = sign(oldSecret, OLD, atActivation,
            nonce(), body);
        check(verify(overlapOld, registry, atActivation, new Nonces())
                == VerifyResult.ACCEPTED,
            "Retiring old key may verify during overlap");
        registry.revoke(oldLoc);
        check(verify(overlapOld, registry, atActivation, new Nonces())
                == VerifyResult.INACTIVE_KEY,
            "Revocation must override valid signature");
        check(registry.activate(ADMIN, oldLoc, 3,
                atActivation.instant())
                == ActivationResult.REVOCATION_BLOCKED,
            "Revoked key must not be resurrected");

        // Expiration is checked on every verify, not via background job.
        Clock afterNewExpiry = Clock.fixed(
            t0.plusSeconds(86400 * 7L), ZoneOffset.UTC);
        Request expiredKeyRequest = sign(newSecret, NEW,
            afterNewExpiry, nonce(), body);
        check(verify(expiredKeyRequest, registry,
                afterNewExpiry, new Nonces())
                == VerifyResult.INACTIVE_KEY,
            "expiresAt is exclusive");

        // Key registry outage is NOT a fallback to old/default secret.
        registry.setAvailable(false);
        check(verify(activeNew, registry, atActivation,
                new Nonces()) == VerifyResult.STORE_UNAVAILABLE,
            "Registry outage must fail closed");
        registry.setAvailable(true);

        // Race: 8 activation controllers contend for a separate key.
        Locator raceLoc = new Locator(
            ENV, AUD, CLIENT, "key-2027-01");
        registry.stage(raceLoc, secret(), t0.minusSeconds(1),
            t0.plusSeconds(7200));
        registry.signerProvisioned(raceLoc);
        registry.verifierReady(raceLoc, "gateway-a");
        registry.verifierReady(raceLoc, "gateway-b");
        ExecutorService pool = Executors.newFixedThreadPool(8);
        CountDownLatch ready = new CountDownLatch(8);
        CountDownLatch go = new CountDownLatch(1);
        List<Future<ActivationResult>> outcomes = new ArrayList<>();
        try {
            for (int i = 0; i < 8; i++) {
                outcomes.add(pool.submit(
                    (Callable<ActivationResult>) () -> {
                        ready.countDown();
                        go.await();
                        return registry.activate(
                            ADMIN, raceLoc, 1, t0);
                    }));
            }
            ready.await();
            go.countDown();
            int activated = 0;
            int alreadyActive = 0;
            for (Future<ActivationResult> outcome : outcomes) {
                switch (outcome.get()) {
                    case ACTIVATED -> activated++;
                    case ALREADY_ACTIVE -> alreadyActive++;
                    default -> throw new AssertionError(
                        "Unexpected concurrent activation outcome");
                }
            }
            check(activated == 1 && alreadyActive == 7,
                "Atomic CAS must commit one activation");
        } finally {
            go.countDown();
            pool.shutdownNow();
        }
        System.out.println(
            "PASS: STAGED/ACTIVE, readiness, CAS, HMAC, replay, rotation");
    }
}
~~~

### 9.2. Các điểm cần nhận ra trong code

**Đầu tiên**, client có thể biết raw secret khi key mới còn `STAGED`:

~~~java
Request earlyNew = sign(newSecret, NEW, base, nonce(), body);
check(verify(earlyNew, registry, base, new Nonces())
        == VerifyResult.INACTIVE_KEY,
    "Valid HMAC from future key cannot activate itself");
~~~

Điều này cho thấy **lifecycle policy không bị vượt qua** chỉ vì HMAC đúng. Kiểm tra `state`, `activeFrom` và `expiresAt` là điều kiện **độc lập** của authentication.

**Tiếp theo**, `activate` quyết định state và revision **bên trong `ConcurrentHashMap.computeIfPresent`**. Khi tám controller cùng gọi, chỉ **một** transition `STAGED→ACTIVE`; các lời gọi còn lại nhận `ALREADY_ACTIVE`. Một local map không thay DB transaction/CAS thật trên nhiều replica.

**Sau cùng**, `verify` lấy key theo `Locator(env,audience,clientId,keyId)`, không thử secret khác nếu không tìm được key; nonce chỉ được claim **sau HMAC khớp**. Key đã revoke bị từ chối trước khi request có thể tác động đến nghiệp vụ.

### 9.3. Giới hạn và mở rộng cho production

- `Registry` chạy trong một JVM, không có persistent store, quorum, leader election hay shared consistency; cần điều kiện atomic trong DB/etcd/conditional key-value store phù hợp.
- `verifierReady` và `signerProvisioned` là lời gọi giả lập; API thật phải **authenticate controller/replica** và xác minh readiness dựa trên phiên bản/policy thực tế.
- `Credential.secret` trong demo là `byte[]`; đây là dữ liệu nhạy cảm và bản ghi Java record không tự zeroize. Production cân nhắc KMS/HSM VerifyMac, secret leases, không log, hạn chế heap dump.
- Chương trình không gọi HTTP network. Cần integration tests với proxy, HTTP/1.1/2, KMS, registry và nonce store trong môi trường phù hợp.
- `Nonces` chỉ được atomic trong một process; chưa có background eviction hay durability. Production dùng shared atomic claim-if-absent, retention đúng với freshness window.
- Trong production, quyền `revoke`/`retire` cần policy riêng; method của demo cố ý không công bố như một admin API thật.
- Mã có scope cố định một client/route để biểu diễn chính sách. Multi-tenant production phải kiểm tra signed method, raw target/query, header/body và scopes thực tế.

## 10. Khi có sự cố activation: fail closed, rollback hay revoke?

### 10.1. Activate xong nhưng gateway B chưa nhìn thấy ACTIVE

Đừng thay thế key lookup bằng **fallback secret** hoặc cho qua request “tạm thời”. Có thể **dừng cutover client**, route traffic tới các gateway đã sẵn sàng nếu an toàn, hoặc sửa propagation/version; yêu cầu cụ thể phụ thuộc consistency SLA.

### 10.2. KMS/secret manager không trả key

Nếu registry trả `UNAVAILABLE`, verifier **không chứng minh được authentication**. Fail closed (HTTP 503 chung nếu phù hợp operation) và cảnh báo. Không dùng một test/default key, không tin `X-Key-Id` và không tự chuyển key `STAGED` thành `ACTIVE`.

### 10.3. Credential kích hoạt sai phạm vi

Ví dụ key cấp cho `partner-42/payments-api` nhưng controller đặt audience `admin-api`. Cần **dừng dùng**, xem lại ACL/policy/incident scope và cấp version mới nếu cần; không chỉ đổi string audience trong record đang dùng mà bỏ qua các request đã ký/cache của các verifier.

### 10.4. Lỗi activation sau khi client đã bắt đầu ký

Nếu key chưa bị lộ nhưng có lỗi triển khai, có thể **dừng signer cutover** và sửa readiness; key cũ `ACTIVE/RETIRING` còn hợp lệ trong overlap nếu policy cho phép. Nếu key **bị lộ hoặc kích hoạt trái phép**, cần **REVOKE** key/version, không đơn giản hạ state rồi tái dùng secret cũ.

### 10.5. Revoke không nên rollback tự động thành ACTIVE

Đừng cho một “rollback deployment” dùng snapshot cũ và **hồi sinh key đã revoke**. Lifecycle controller cần kiểm tra revision và explicit deny/revoke tombstone theo tính nhất quán được yêu cầu.

### 10.6. Activation commit có kết quả không rõ (ambiguous commit)

Controller gửi `activate`, control plane commit nhưng response mạng bị mất. **Không** tạo key thứ hai hay cấp lại secret ngay lập tức. Đọc trạng thái/version từ nguồn authoritative, dùng idempotency của operation và audit transition; nếu state đã ACTIVE với đúng record/conditions thì trả `ALREADY_ACTIVE`. Nếu state không xác định do outage, dừng cutover và reconcile, không tự tuyên bố thành công.

## 11. Gateway/proxy và trust boundary khi kích hoạt

~~~mermaid
sequenceDiagram
    participant C as Client signer
    participant P as Untrusted proxy
    participant G as Trusted gateway
    participant R as Credential registry
    participant N as Shared nonce store
    participant B as Backend
    C->>P: HMAC signed request (client, kid, ts, nonce)
    P->>G: Forward/retry/possible rewrite
    G->>G: Strict parse, reject duplicate security headers
    G->>R: Scoped lookup(client,kid,audience)
    alt Key STAGED / REVOKED / expired
        R-->>G: Deny according to lifecycle
        G-->>C: Generic authentication failure
    else Key ACTIVE + valid clock/scope
        R-->>G: Authorized verify capability
        G->>G: Canonical HMAC + timestamp freshness
        G->>N: Atomic nonce claim after valid HMAC
        alt New nonce
            N-->>G: CREATED
            G->>B: Trusted verified identity and signed request semantics
            B->>B: Authorization + business idempotency
        else Duplicate
            N-->>G: REPLAY
            G-->>C: Reject
        end
    end
~~~

**Các vấn đề cần kiểm thử**:

- Proxy có thể sửa path/query hoặc `Content-Encoding`, khiến gateway verify canonical khác action backend thực thi.
- Hai field lines `X-Key-Id` (khác case) làm hai parser chọn key khác nhau; ingress phải **reject duplicate security headers**.
- Một header do client chèn `X-Verified: true` không thể thay kết quả HMAC; gateway strip identity headers và xác thực hop gateway→backend.
- Không để public client gọi trực tiếp backend bỏ qua gateway verification hoặc kích hoạt key qua endpoint admin không được bảo vệ.
- Với HTTP/2, `:method` và `:path` cần ánh xạ đúng sang signed target/method, không tự đổi query order nếu contract yêu cầu raw representation.
- Nếu key activation state được cache ở gateway, must check **version/policy freshness** và khả năng revoke propagation; một stale ACTIVE không được tồn tại ngoài SLA được chấp nhận.

## 12. Audit, quan sát và thông báo cho client

Một activation audit event không chứa shared secret:

~~~json
{
  "event": "credential_activated",
  "environment": "prod",
  "audience": "payments-api",
  "clientScope": "partner-42",
  "keyId": "key-2026-12",
  "oldState": "STAGED",
  "newState": "ACTIVE",
  "fromVersion": 7,
  "toVersion": 8,
  "actor": "workload:credential-activator-prod",
  "reason": "approved_rotation",
  "readyVerifiers": ["gateway-a", "gateway-b"],
  "requestId": "req-opaque-123"
}
~~~

**Không** đưa raw secret, full signature, authorization header, toàn bộ body, mã truy cập KMS hoặc private key ref nhạy cảm vào audit. Mọi action `STAGE`, `ACTIVATE`, `RETIRE`, `REVOKE` cần dấu thời gian, actor đã xác thực, scope, version và outcome. Audit phải được bảo vệ khỏi chỉnh sửa trái phép theo chính sách.

### 12.1. Monitoring quan trọng

| Metric/event | Tín hiệu |
| --- | --- |
| Unknown/staged key ID requests | Client chuyển key quá sớm hoặc có tấn công enumeration. |
| `ACTIVE` propagation lag theo replica | Gateway nào chưa nhận policy mới. |
| Rotation key usage % | Bao nhiêu traffic đang dùng old/new key. |
| HMAC mismatch sau activation | Secret phân phối sai, canonical drift, proxy rewrite hoặc client bug. |
| Key access `DENY`/KMS timeout | Workload policy lệch hoặc outage. |
| Timestamp skew/outside window | NTP/drift hoặc timestamp unit sai. |
| Nonce conflict/retention errors | Replay, race hoặc nonce store lỗi. |
| Activation CAS conflicts / retries | Nhiều controller tranh chấp hoặc stale metadata. |
| Revoke propagation lag | Rủi ro nhận key đã bị thu hồi. |
| Unauthorized activate attempts | Cố truy cập control plane không được phép. |

Metric labels phải được giới hạn cardinality; không tạo một label trực tiếp cho mọi raw key ID do attacker gửi. Với client-facing error, dùng **lỗi authentication chung** nếu không cần tiết lộ key tồn tại/đang STAGED; hỗ trợ khách hàng qua kênh đã xác thực để kiểm tra rollout.

### 12.2. Công bố activation window cho signer

Client cần biết **key ID mới được phép dùng từ khi nào**, endpoint/audience nào được chấp nhận, **deadline ngừng key cũ**, cách tạo timestamp/nonce/signature, xử lý 401 và retry idempotency. Thông báo qua kênh quản trị xác thực, không qua unauthenticated HTTP response chứa metadata secret registry.

## 13. Ma trận kiểm thử kích hoạt credential

Các test sau kiểm tra state machine và data plane. Ca distributed-readiness/registry failover cần **integration test thực**; ví dụ Java chỉ minh họa logic trong một process.

| Test case | Setup/hành động | Kỳ vọng |
| --- | --- | --- |
| Key mới chỉ GENERATED | Secret tồn tại, chưa có registry record | Không thể verify; reject unknown. |
| Key STAGED, MAC đúng | Client đã có secret, server chưa activate | **Reject** theo lifecycle. |
| Kích hoạt không có quyền | Client cố gọi activate | `ACCESS_DENIED`; state vẫn STAGED. |
| Thiếu signer readiness | Verifiers ready, signer chưa provision | `NOT_READY`. |
| Thiếu một gateway | Signer ready, gateway-a ready, gateway-b chưa | `NOT_READY`. |
| Đủ readiness và đúng giờ | Controller được quyền, version đúng | Một `ACTIVATED`; state thành ACTIVE. |
| Version cũ | Activate với stale expected revision | `VERSION_CONFLICT`. |
| Gọi activate lặp | State đã ACTIVE | `ALREADY_ACTIVE`, không sinh key khác. |
| Tám controller đồng thời | Cùng key, expected version | Một commit, bảy already active trong test local. |
| Kích hoạt trước `activeFrom` | Đủ readiness nhưng serverNow sớm | `NOT_YET_TIME`; không bypass. |
| Verify trước `activeFrom` | HMAC hợp lệ với secret staged | Reject INACTIVE. |
| Verify đúng `activeFrom` | State ACTIVE, timestamp hợp lệ | Có thể pass. |
| Signed timestamp trước `activeFrom` | Request ký trước activation, gửi sau | Reject theo **extra contract** của bài. |
| Verify đúng `expiresAt` | Dùng active key tại instant hết hạn | **Reject**, end exclusive. |
| Key RETIRING | Key cũ trong overlap còn hạn | Có thể verify theo contract. |
| Key REVOKED | HMAC và timestamp đúng | **Reject**, không claim nonce. |
| Re-activate key REVOKED | Controller thử kích hoạt lại ID cũ | `REVOCATION_BLOCKED`, không hồi sinh. |
| Một verifier thiếu key mới | Gateway chưa có record/policy | Fail closed; remediation rollout, không fallback. |
| Registry/KMS outage | Key lookup timeout | Fail closed, không dùng secret mặc định. |
| HMAC body tamper | Proxy sửa body sau ký | Full MAC mismatch, không claim nonce. |
| Header key ID duplicate | Hai `X-Key-Id` case khác nhau | Reject tại ingress. |
| Client sai scope | Key payments dùng cho admin/cross-client | Reject scoped lookup/policy. |
| Replay nguyên request | Key ACTIVE, nonce đã claim | Nonce store reject. |
| Replay qua key rotation | Same client/nonce nhưng new key ID | Reject trong cùng nonce namespace. |
| Retry với nonce mới | Same business request nhưng timestamp/nonce mới | Authentication có thể pass; **idempotency** ngăn side effect lặp. |
| Clock drift giữa gateway | Một node trước activation, node khác sau | Detection, time-sync và traffic policy theo SLA. |
| Active key nhưng thiếu quyền tenant | HMAC và nonce PASS | **Authorization DENY**. |
| Activation đã commit, ACK mất | Controller retry same activation | Reconcile state/version; idempotent `ALREADY_ACTIVE`. |
| Rollback snapshot cũ sau revoke | Deploy old registry image | Không được làm revived credential. |

### Câu hỏi tự đánh giá

1. Vì sao một credential đã được provision và có HMAC tag đúng vẫn chưa nên verify nếu state là `STAGED`?
2. Vì sao cần chứng minh readiness ở **mọi verifier có thể nhận traffic** trước activation? ACK readiness có bảo đảm mọi pod sinh sau đó cũng sẵn sàng không?
3. Sự khác nhau giữa **`activeFrom` của key** và **signed timestamp trong HTTP request** là gì? Vì sao không dùng signed timestamp làm đồng hồ kích hoạt?
4. Kích hoạt key bằng một operation atomic ở registry có đủ bảo đảm mọi region nhìn thấy ACTIVE cùng lúc không?
5. Khi key bị revoke, việc deploy lại một registry snapshot cũ có thể tạo lỗ hổng gì?
6. Client ký lại request với key ID mới nhưng nonce cũ đã claim. Có nên cho qua vì tag HMAC đổi không? Vì sao?
7. Vì sao 401 do key chưa ACTIVE và 401 do HMAC sai có thể cần public error chung, nhưng audit nội bộ vẫn phải phân biệt?
8. Làm sao phối hợp activation với overlap rotation và idempotency business để tránh gián đoạn hoặc double side effect?
9. Với key `activeFrom=02:01:00Z`, request có `ts=02:00:59Z` và server verify lúc `02:01:01Z`, contract bổ sung của bài cho phép hay từ chối?
10. Một controller nhận timeout sau lệnh `activate`. Vì sao không lập tức provision một secret mới hoặc ghi đè state?

## 14. Checklist triển khai production

- [ ] Xác định state machine và quy tắc `GENERATED/PROVISIONED/STAGED/ACTIVE/RETIRING/REVOKED/EXPIRED`; không nhận key STAGED hoặc REVOKED.
- [ ] Có IAM/workload identity cho `PROVISION`, `ACTIVATE`, `ROTATE` và `REVOKE`; HTTP client tự khai không có quyền lifecycle.
- [ ] Sinh secret đủ entropy bằng CSPRNG; cấp riêng từng client/audience/env; lưu qua KMS/secret manager, không trong source hoặc log.
- [ ] Chốt key metadata và signing contract gồm **client ID, key ID, audience, environment, HmacSHA256, route/method và validity window**.
- [ ] Provision key trước khi cho client dùng; phát hành secret/ID qua kênh an toàn và có xác nhận client readiness.
- [ ] Kiểm tra tất cả gateway/verifier có khả năng nhận traffic đã load version/policy đúng; xác nhận nonce store, KMS và NTP sức khỏe tốt.
- [ ] Controller activate qua conditional atomic transition **STAGED → ACTIVE** với expected revision, idempotent retry; không ghi đè REVOKED/EXPIRED.
- [ ] Thời gian policy: `activeFrom <= serverNow < expiresAt`, ngưỡng inclusive/exclusive rõ; kiểm tra trên mỗi request, không chỉ lúc activate.
- [ ] Timestamp và nonce được ký trong canonical; freshness theo `serverNow-P <= signedTs <= serverNow+F`, không dùng signedTs làm server verification clock.
- [ ] Quyết định có áp dụng `signedTs >= activeFrom` hay không, ghi thành API contract và test ranh giới.
- [ ] Ký method, raw URI/query, signed headers, content-type/body digest; reject duplicate security header, parser ambiguity và proxy rewrite.
- [ ] Lookup scoped `(environment,audience,clientId,keyId)`, **không** fallback default secret/try all keys khi unknown, staged hoặc lỗi registry.
- [ ] Strict Base64 full HMAC-SHA256 tag 32 byte, dùng `MessageDigest.isEqual`; chỉ công nhận client identity sau khi tag đúng.
- [ ] Nonce store atomic shared giữa replicas, namespace theo `audience+authenticatedClient+nonce`, TTL đủ `signedTs+P+margin` hoặc `P+F+margin`.
- [ ] Rotation có overlap key cũ/mới và deadline retire, nhưng revoked không được hồi sinh vì rollback config/version.
- [ ] Control/data plane consistency được mô tả rõ: readiness, version barrier, cache invalidation và routing theo SLA, không hứa global instant nếu không có cơ chế.
- [ ] Khi registry/KMS/nonce store unavailable, **fail closed**; không auto-activate hoặc tắt authn để tránh lỗi 401.
- [ ] Lưu audit event `ACTIVATED`/`REVOKED` có actor, scope, revision, timestamps, approval và outcome, **không ghi raw secret/signature**.
- [ ] Monitor unknown/staged key IDs, HMAC mismatch, clock drift, key usage theo rotation, KMS errors, revoked state propagation và unauthorized lifecycle attempts.
- [ ] Sau authentication/replay pass, backend vẫn kiểm tra **authorization theo tenant/action/resource** và idempotency cho nghiệp vụ có side effect.
- [ ] Có unit/integration tests cho unauthorized controller, thiếu readiness, concurrency activation, trước/sau `activeFrom`, expiry, revoke/rollback, multi-region propagation, HTTP proxy và replay.

**Kết luận:** **Kích hoạt credential** là một **quyết định lifecycle có kiểm soát**, không phải sự kiện “secret đã tồn tại”. Chỉ khi **đúng chủ thể quản trị, đúng scope, đủ readiness, đúng thời điểm và atomic transition** thì credential mới trở thành ACTIVE; từ đó mỗi request vẫn phải vượt qua **HMAC trên canonical request, timestamp freshness, atomic nonce claim và key policy**. Sau xác thực, **authorization và idempotency nghiệp vụ** vẫn bắt buộc. Thiết kế activation an toàn giúp rotation không gián đoạn, ngăn key chưa sẵn sàng hoặc đã revoke bị sử dụng và hạn chế blast radius khi có sự cố.

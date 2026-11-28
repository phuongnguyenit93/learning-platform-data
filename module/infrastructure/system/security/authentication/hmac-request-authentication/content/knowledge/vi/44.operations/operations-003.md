# Cấp secret: quy trình vận hành cấp phát shared secret cho HTTP HMAC

## 1. Vấn đề vận hành: secret không chỉ là một chuỗi cấu hình

Trong module `SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION`, client và server chia sẻ một **secret key** để tạo/xác minh chữ ký HMAC trên **canonical HTTP request**. Hợp đồng ký có thể ràng buộc method, URI/query, signed headers, timestamp, nonce và digest của raw body. Verifier dùng đúng secret theo key ID, kiểm tra HMAC, key state và chống replay; sau đó **authorization** riêng mới quyết định client có quyền với tenant/action/resource hay không.

Bài **Cấp secret**, thuộc chương **Operations**, tập trung vào **quy trình cấp phát credential HMAC** trước khi request đầu tiên được chấp nhận. Nếu vận hành kém, một HMAC primitive mạnh vẫn có thể thất bại: secret bị gửi qua email, nhiều đối tác dùng chung một khóa, key version không xác định, môi trường staging dùng khóa production, secret bị in trong log hoặc client chưa hề chứng minh đã nhận đúng secret.

Những câu hỏi cần trả lời:

- Ai được yêu cầu cấp secret và ai phê duyệt?
- Server sinh secret bằng gì, dài bao nhiêu, có độc nhất theo client/môi trường không?
- Key ID khác secret ra sao và được ràng buộc vào identity/tenant/scopes thế nào?
- Làm sao đưa secret đến đúng client mà không lộ qua log, ticket hoặc đường dẫn URL?
- Cấp secret xong có cho request production chạy ngay không?
- Secret được giữ ở đâu phía server và phía client?
- Làm sao kích hoạt, rotate, revoke, audit và xử lý mất secret?
- Làm sao kiểm tra gateway, timestamp/nonce và authorization sau khi cấp?

**Nguyên tắc:** cấp secret thành công chỉ có nghĩa credential đã được tạo/trao đổi an toàn. Nó **không tự chứng minh client đã ký đúng, không cấp quyền tenant**, và không thay thế kiểm soát chống replay.

## 2. Threat model của quá trình cấp secret

Quá trình provisioning là một bề mặt tấn công độc lập với request signing.

| Tác nhân hoặc sai sót | Rủi ro | Biện pháp vận hành |
| --- | --- | --- |
| Người yêu cầu không được phép đại diện đối tác | Cấp khóa cho người không thuộc client | Xác minh danh tính và approval đúng đối tượng |
| Insider đọc ticket/chat/email | Lộ shared secret trước khi dùng | Không đưa secret vào ticket/email; one-time secure retrieval |
| Admin cấp cùng secret cho nhiều client | Mất cách ly, khó revoke một bên | Sinh secret riêng theo credential/client |
| Sinh secret bằng thời gian, UUID hoặc PRNG yếu | Khóa có thể đoán | CSPRNG, entropy đủ mạnh |
| CI/CD in environment variable/command | Lộ qua log, trace, artifact | Secrets manager, masking, secret scanning |
| Gateway/backend chọn sai key ID | Cross-client authentication/confusion | Exact key lookup, ràng buộc owner identity |
| Secret bị copy sang staging | Rò dữ liệu production, blast radius | Khóa độc lập mỗi environment |
| Cache không thấy trạng thái REVOKED | Khóa cũ tiếp tục xác thực | Freshness bound, invalidation, emergency disable |
| Onboarding tự động trust client header | Cấp principal/tenant sai | Bootstrap identity bằng kênh được xác thực |
| Client lưu secret trong mobile/web frontend | Lộ cho người dùng cuối | HMAC shared secret chỉ đặt trong môi trường có khả năng giữ bí mật |

**Shared secret đòi hỏi hai bên giữ bí mật**. Nếu client là browser JavaScript chạy công khai hoặc ứng dụng mobile có mã/thiết bị do người dùng kiểm soát, việc nhúng một secret chung trong app thường **không thể bảo vệ lâu dài**. Với public client, cần cân nhắc OAuth/PKCE hoặc asymmetric keys và threat model khác. HMAC với shared secret phù hợp hơn cho server-to-server, webhook provider hoặc workload có secret storage đáng tin cậy.

## 3. Phân biệt key ID, secret, credential, principal và authorization

| Thành phần | Có phải bí mật? | Nhiệm vụ |
| --- | --- | --- |
| `clientId` | Thường không | Định danh ứng dụng/đối tác yêu cầu |
| `keyId` | Thường không | Chọn đúng key/version ở server |
| `secretBytes` | **Có** | Vật liệu tạo/xác minh HMAC |
| `credentialId` | Metadata nội bộ | ID bản ghi khóa, trạng thái, audit |
| `principal` | Danh tính được xác thực | Được tạo **sau khi HMAC/timestamp/nonce đạt** |
| `ownerTenant` | Metadata đáng tin trong registry | Chủ sở hữu credential |
| `requestedTenant` | Claim từ HTTP | Phải được ký và kiểm tra grant |
| `authority/scope` | Quyền gắn với policy | Quyết định authorization tách biệt |
| `nonce` | Không phải secret nhưng phải độc nhất | Ngăn một bằng chứng HMAC bị phát lại |
| `signingSuite` | Metadata hợp đồng | MAC algorithm, canonicalization, digest, encoding |

Một credential record có thể gồm:

~~~yaml
credentialId: cred-7f31
clientId: partner-a
ownerTenant: tenant-a
keyId: partner-a-prod-k004
environment: production
signingSuite: hmac-v1-sha256
secretRef: vault://hmac/prod/cred-7f31/key
status: PENDING_ACTIVATION
createdAt: 2026-11-28T04:00:00Z
notBefore: 2026-11-28T04:10:00Z
notAfter: 2027-05-28T00:00:00Z
approvedBy: approver-identified-in-audit
~~~

Đây là **schema minh họa**. `secretRef` chỉ là một tham chiếu logic, không có nghĩa secret hiện diện trong YAML và không phải đường dẫn vault chuẩn của một nhà cung cấp cụ thể. Trong file cấu hình source control chỉ nên có **reference** an toàn, không có raw secret.

**Một key ID không nên được tái sử dụng cho một secret khác.** Khi rotate, tạo key ID/version mới, cập nhật registry và audit. Điều đó giúp ký request rõ ràng, thu hồi từng phiên bản và điều tra truy cập.

## 4. Quy trình tổng thể: từ yêu cầu đến kích hoạt

~~~mermaid
flowchart TD
    A["Client owner yêu cầu cấp HMAC credential"] --> B["Xác minh identity + mục đích sử dụng"]
    B --> C{"Approval và entitlement hợp lệ?"}
    C -->|Không| Z["Từ chối, ghi audit lý do"]
    C -->|Có| D["Tạo credential metadata trạng thái PENDING"]
    D --> E["Sinh secret bằng CSPRNG / KMS"]
    E --> F["Lưu secret vào vault/HSM đúng environment"]
    F --> G["Phát hành key ID + one-time retrieval claim"]
    G --> H["Đối tác lấy secret qua trusted channel"]
    H --> I["Proof of possession qua challenge ký HMAC"]
    I --> J{"Challenge HMAC + owner binding đúng?"}
    J -->|Không| K["Không activate; có thể thu hồi"]
    J -->|Có| L["Activate theo notBefore/policy"]
    L --> M["Client ký request với timestamp + nonce"]
    M --> N["Verifier exact key lookup, MAC và anti-replay"]
    N --> O["Authorization tenant/action/resource"]
~~~

Mỗi bước có một actor và dấu vết kiểm toán. **Không** coi việc tạo row trong database là đã hoàn tất cấp phát. Một credential có thể vẫn `PENDING_ACTIVATION` vì client chưa lấy secret hoặc proof of possession chưa pass.

### Tối thiểu một runbook provisioning

1. **Request:** ai, môi trường nào, route nào, mục đích, expected traffic và owner.
2. **Approval:** xác minh identity và quyền yêu cầu, tránh tự cấp cho chính người phê duyệt nếu quy định yêu cầu separation of duties.
3. **Generate:** secret độc lập, ngẫu nhiên, đúng entropy và suite.
4. **Register:** tạo key ID mới, liên kết client/tenant, status ban đầu bị khóa.
5. **Deliver:** gửi secret qua kênh bảo mật dùng một lần cho đúng recipient.
6. **Confirm:** client chứng minh sở hữu secret mà không gửi ngược raw secret.
7. **Activate:** chỉ khi ràng buộc identity, contract và policy đạt.
8. **Test:** ký request sandbox, kiểm tra replay, proxy và 403 tenant.
9. **Audit:** lưu actor/time/policy revision/outcome, **không lưu giá trị secret trong audit**.
10. **Operate:** giám sát, rotation, recovery và revocation.

## 5. Xác minh quyền yêu cầu cấp secret: bootstrap trust

Cấp secret tạo ra **bằng chứng danh tính mới**, nên phải dựa trên một kênh đã đáng tin từ trước (*bootstrap trust*). Không thể cấp secret production chỉ vì một request có header `X-Client-Id: partner-a`: giá trị đó chưa có chữ ký và ai cũng có thể tự khai.

Một số lựa chọn tùy hạ tầng:

- Portal quản trị với SSO/MFA, quyền `CREDENTIAL_CREATE` giới hạn theo tổ chức/client.
- API quản trị bảo vệ bằng mTLS workload identity hoặc OAuth access token với audience và scope riêng.
- Bước onboarding đối tác có xác minh pháp nhân/đại diện và kênh contact chính thức.
- Cơ chế approval hai người cho credential đặc quyền hoặc production.
- Provisioning tự động từ IAM/controller có signed workload identity, không dùng tài khoản shared admin.

**Không dùng chính credential HMAC chưa tồn tại để xác thực yêu cầu cấp credential đầu tiên.** Với rotation, client đang có credential ACTIVE có thể dùng nó để tạo yêu cầu xoay vòng, nhưng vẫn cần policy kiểm soát, proof of identity hiện hành và khả năng khẩn cấp khi khóa cũ đã bị lộ.

### Policy trước khi cấp

| Quyết định | Cần có |
| --- | --- |
| Chủ sở hữu | Client và tenant đáng tin từ hệ thống IAM |
| Môi trường | Dev/staging/production, không dùng chung secret |
| Phạm vi | Route group/API product/scope tối thiểu |
| Suite | Một signing suite đã enabled và tương thích cả hai bên |
| Thời hạn | notBefore/notAfter, rotation cadence, overlap policy |
| Sức chứa | Quota/rate limit/size limit phù hợp |
| Người quản lý | Owner, contact bảo mật, on-call |
| Thu hồi | Ai có quyền revoke, thời hạn hiệu lực |
| Kiểm toán | Ticket/approval ID, immutable audit event |

Mặc định **least privilege**, không cấp wildcard tenant hoặc global admin scope chỉ vì tích hợp nhanh.

## 6. Sinh secret: entropy và CSPRNG

HMAC được thiết kế sử dụng khóa bí mật là **chuỗi byte**. Một lựa chọn thực tế cho HMAC-SHA256 server-to-server là **32 byte ngẫu nhiên (256 bit)** từ CSPRNG, nếu phù hợp security policy và key-generation requirement của hệ thống. HMAC-SHA512 có thể dùng key dài hơn theo chính sách, nhưng **không phải cứ dùng SHA-512 là bắt buộc 64 byte**; điều quan trọng là nguồn entropy và bảo vệ khóa.

**Không dùng:**

- `UUID.randomUUID().toString()` làm HMAC key mặc định (UUID có cấu trúc, không tương đương một khóa ngẫu nhiên 256 bit).
- `System.currentTimeMillis()`, số tuần tự, email, tenant ID hoặc mật khẩu có thể đoán.
- `java.util.Random` hoặc một hash của thời gian làm nguồn entropy.
- Secret mẫu trong tài liệu/copy-paste giữa khách hàng.
- Cùng secret cho `dev`, `staging` và `production`.

### Java 17: tạo byte key bằng SecureRandom

~~~java
import java.security.SecureRandom;
import java.util.Base64;

final class HmacSecretGenerator {
    private final SecureRandom random;

    HmacSecretGenerator(SecureRandom random) {
        this.random = random;
    }

    byte[] generate256BitKey() {
        byte[] raw = new byte[32];  // 256 bits
        random.nextBytes(raw);
        return raw;
    }

    String encodeForOneTimeDelivery(byte[] raw) {
        // Base64 là encoding, KHÔNG phải encryption.
        if (raw == null || raw.length != 32) {
            throw new IllegalArgumentException("Invalid key length");
        }
        return Base64.getEncoder().encodeToString(raw);
    }
}
~~~

Ví dụ dùng `SecureRandom` theo provider đã cấu hình; trong production có thể dùng cloud KMS/HSM generate API hoặc FIPS-approved DRBG theo compliance. `SecureRandom` thread safety và provider lifecycle phải được đánh giá theo deployment nhưng không tự tạo PRNG bằng một seed tự chế.

Nếu dùng Base64, **32 bytes thành 44 ký tự Base64 padded**. Chiều dài chuỗi encoded không phải entropy; không được kết luận 44 ký tự có 44 byte entropy. **Base64 không mã hóa bảo mật**: ai đọc được chuỗi Base64 có thể lấy lại toàn bộ secret.

### Test sinh khóa

- Mỗi lần tạo phải trả đúng độ dài quy định.
- Định dạng Base64 decode trở lại đúng bytes.
- Không trả secret cố định từ source config.
- Không xuất secret vào log, metrics hoặc exception.
- Các credential khác nhau không dùng chung bytes (kiểm tra uniqueness là smoke test, không phải chứng minh entropy).
- KMS/HSM generation failures phải dừng provisioning, không fallback sang nguồn yếu.

## 7. Key material, key ID và cách đặt tên

Một key ID có thể là một opaque random identifier hoặc tên có prefix giúp vận hành:

~~~text
partner-a-prod-k004
partner-a-stg-k002
partner-b-prod-k001
~~~

Những ví dụ trên **không phải security boundary**. Không tin prefix `partner-a` hay `prod` trong header như bằng chứng owner/environment; server phải tra registry và kiểm tra metadata thật.

Khuyến nghị:

- Key ID duy nhất; không tái sử dụng sau revoke.
- Không đưa secret vào key ID.
- Không suy quyền từ key ID string pattern.
- Chỉ bind exact key ID đến **một credential record** có secret reference, suite, client owner và status.
- Có key fingerprint nội bộ nếu cần đối soát, nhưng fingerprint **không đủ thay secret** và không thay verify HMAC.
- Nếu hệ thống multi-region, key IDs và policy revision được đồng bộ nhất quán theo phạm vi chấp nhận.

### Secret per client, environment và purpose

| Cách tổ chức | Tác động |
| --- | --- |
| Một secret cho mọi client | **Không nên:** mất cách ly và khó audit/revoke |
| Một secret cho mỗi client + environment | Phù hợp cho nhiều API server-to-server |
| Một secret cho mỗi credential/key version | Hỗ trợ rotation/overlap rõ ràng |
| Một secret cho mỗi signing suite/key version | Tránh algorithm/key confusion |
| Một secret chia sẻ giữa nhiều microservices | Cần threat model; blast radius lớn |
| Secret tách theo API audience | Có thể giới hạn cross-service replay |

Một mô hình có thể có nhiều credentials cho một client để rotate, nhưng phải có **giới hạn số key ACTIVE cùng lúc** và theo dõi hạn cuối overlap.

## 8. Lưu secret phía server: không dùng file source hoặc plain database

Server cần truy cập vật liệu HMAC để tính lại expected MAC (trừ trường hợp verify qua HSM/key handle phù hợp). Do đó **không thể chỉ lưu một hash một chiều của secret như mật khẩu** rồi tự tính HMAC với nó, trừ khi giao thức đã thay đổi và client cũng dùng đúng hash đó như khóa (khi ấy hash trở thành secret mới).

Một lựa chọn triển khai phổ biến:

~~~text
Credential Registry (metadata)
  keyId: partner-a-prod-k004
  clientId: partner-a
  ownerTenant: tenant-a
  status: PENDING_ACTIVATION
  suite: hmac-v1-sha256
  secretRef: secret-manager://prod/hmac/cred-7f31
  revision: 17

Secret Manager / KMS / HSM
  encrypted key material or non-exportable key handle
  least-privilege IAM policy
  access audit, rotation control, high availability
~~~

Bảo vệ secret storage ở **rest** và **in transit**; tránh để raw secret bị xuất ra cache/snapshot/log. Secret manager phải cho server workload đúng quyền đọc secret của credential đó, không cấp quyền list/read toàn bộ kho cho mọi service.

### Những lỗi phổ biến

- Lưu raw secret trong `application.yml` hoặc git.
- Cho mọi environment dùng chung secret hoặc vault namespace.
- Cho phép operator tra secret của mọi client bằng API debug.
- Sao chép secret vào local Redis cache không mã hóa/không TTL.
- Tắt encryption/TLS trong secret-manager client.
- Dùng một `static final String HMAC_SECRET` global cho mọi tenant.
- Log `SecretKeySpec`, env values hoặc configuration dump.

Với Java, bí mật từng đi qua `String` có thể tồn tại trong heap tới khi GC. `byte[]` có thể xóa sau khi dùng bằng `Arrays.fill(raw, (byte) 0)` nhưng **không bảo đảm** đã xóa mọi bản sao tại JVM, JCA provider, TLS buffer hoặc secret manager SDK. Quản lý lifecycle và giảm bản sao quan trọng hơn việc tuyên bố “zeroization hoàn toàn” trên managed runtime.

## 9. Phân phối secret an toàn tới đúng client

Một shared secret phải đến được cả client và server qua kênh có xác thực và bảo mật.

**Không gửi qua** chat nhóm, email thường, ticket text, file đính kèm công khai, URL query parameters hoặc monitoring dashboard. Chúng dễ bị lưu lại trong lịch sử, log truy cập, backup, browser sync hoặc screenshot.

Một pattern:

1. Admin đã được xác thực yêu cầu tạo credential cho client.
2. Server tạo metadata PENDING và raw secret trong secure key manager.
3. Hệ thống phát hành **one-time retrieval capability** gắn với đúng client/recipient, TTL ngắn và scope giới hạn.
4. Người nhận đăng nhập kênh đã xác thực, mở retrieval endpoint qua TLS, có MFA/mTLS nếu policy yêu cầu.
5. Secret được hiển thị **một lần** hoặc được trả trực tiếp qua kênh mã hóa tới secret manager phía client.
6. Sau retrieval hoặc hết hạn, token retrieval bị thu hồi, không thể dùng lại.
7. Client xác nhận possession bằng challenge HMAC; server activate theo policy.

**One-time token không phải được gửi tự do qua URL.** Nếu token là bearer secret và lộ trong query/referrer/access log, cơ chế one-time có thể bị attacker chiếm trước. Ưu tiên token trong kênh authenticated, short lived, bound to user/session/workload và truyền qua body/authorization header theo thiết kế; chống replay cho chính retrieval token.

### Nếu có client tự tạo secret?

Một số tích hợp chọn **client-generated shared secret** rồi gửi vào server qua kênh quản trị có xác thực. Điều này chỉ chấp nhận nếu có policy kiểm tra entropy, quy trình kiểm soát nguồn tạo và kênh truyền đáng tin. Thường **server-generated** dễ chuẩn hóa/audit hơn. Không mặc định chấp nhận người dùng nhập một password dễ đoán làm HMAC secret.

### Kênh nhận phía client

- Client server-to-server lưu secret vào vault/secret manager của họ, không đưa vào repository.
- Nếu dùng deployment env var, kiểm soát ai có quyền xem process environment/container inspection, CI variables và log; không coi env var là secret manager an toàn tuyệt đối.
- Secret phải đến đúng production workload qua IAM identity đáng tin.
- Không đưa secret vào binary SDK, browser JS bundle, mobile APK hoặc static web content.

## 10. Trạng thái credential và thời điểm kích hoạt

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> PENDING_APPROVAL
    PENDING_APPROVAL --> PENDING_DELIVERY: approved
    PENDING_DELIVERY --> PENDING_ACTIVATION: delivered/retrieved
    PENDING_ACTIVATION --> ACTIVE: proof of possession + policy
    PENDING_ACTIVATION --> REVOKED: timeout/abort
    ACTIVE --> GRACE: planned rotation overlap
    GRACE --> REVOKED: overlap ended
    ACTIVE --> REVOKED: emergency revoke
    ACTIVE --> EXPIRED: notAfter
    GRACE --> EXPIRED: notAfter
    REVOKED --> [*]
    EXPIRED --> [*]
~~~

Đây là một **state machine minh họa**. Tùy ứng dụng có thể dùng `PENDING`/`ACTIVE`/`DISABLED`/`REVOKED`/`EXPIRED`/`GRACE`, nhưng cần định nghĩa rõ **trạng thái nào được verifier phép nhận request**.

| Status | Cho phép verify request nghiệp vụ? | Ghi chú |
| --- | --- | --- |
| REQUESTED / PENDING_APPROVAL | Không | Chưa cấp credential |
| PENDING_DELIVERY | Không | Secret đã tạo nhưng chưa tới đúng người |
| PENDING_ACTIVATION | Không | Chưa chứng minh sở hữu |
| ACTIVE | Có điều kiện | Vẫn phải MAC/timestamp/nonce/authz |
| GRACE | Có điều kiện, đến hạn overlap | Chỉ cho key cũ đúng scope |
| REVOKED | Không | Không tự kích hoạt lại |
| EXPIRED | Không | MAC đúng vẫn bị từ chối |

**Không tự kích hoạt** chỉ vì secret đã được tạo. Có hệ thống không thực hiện proof-of-possession riêng mà kích hoạt bằng thủ tục quản trị được xác nhận; khi đó phải mô tả rõ rủi ro và tiêu chí approval, không bịa rằng server đã chứng minh client sở hữu key.

## 11. Proof of possession: xác nhận bên nhận có secret

Sau khi client lấy key K4, có thể yêu cầu ký một challenge **không thực thi nghiệp vụ**:

~~~text
challengeId: activate-7f31
credentialId: cred-7f31
keyId: partner-a-prod-k004
audience: hmac-activation-service
expiresAt: 2026-11-28T04:15:00Z
serverNonce: 9d5b14ee-32bf-4289-94e0-7f7319a6d1c4
~~~

Server tạo challenge dùng một lần, bind vào đúng credential/client/activation session và channel. Client tính HMAC trên **challenge bytes đã được đặc tả**, gửi key ID và MAC, không gửi lại raw secret.

~~~mermaid
sequenceDiagram
    participant C as Client Workload
    participant M as Management API
    participant V as Secret Manager
    C->>M: Authenticated enrollment + retrieve K4
    M->>V: Secure one-time access to secret
    V-->>C: Secret qua trusted retrieval channel
    C->>M: Request activation challenge
    M-->>C: challengeId + nonce + audience + expiry
    C->>C: HMAC(K4, canonical challenge)
    C->>M: challengeId + proof signature
    M->>M: Verify exact K4, one-time challenge, owner grant
    M-->>C: Activation accepted / rejected
~~~

Khi thiết kế challenge, phải chống:

- Replay chính activation proof.
- Cross-environment challenge: `staging` không activate `production`.
- Cross-client challenge: credential A không activate B.
- Cross-service challenge: chứng cứ activation không phải request MAC nghiệp vụ.
- Hạ cấp suite/algorithm giữa challenge issuance và verification.
- Timing attacks, logging raw proof/secret, expiry bypass.

**Không xem proof-of-possession là cấp quyền tenant.** Nó chỉ chứng minh bên gửi biết K4 tại thời điểm challenge; authorization vẫn đến từ provisioning policy/registry.

## 12. Lỗi provisioning phải fail closed

Nếu secret manager, RNG/KMS, credential registry hoặc audit infrastructure gặp lỗi, provisioning không được “thành công một phần” theo cách làm credential ACTIVE nhưng secret không tồn tại hoặc audit thiếu.

| Lỗi | Hành vi khuyến nghị |
| --- | --- |
| SecureRandom/KMS generate failure | Dừng cấp, không dùng fallback PRNG yếu |
| Lưu vault fail | Giữ credential inactive, cleanup metadata/secret tạm |
| Registry write fail sau tạo secret | Reconcile/orphan cleanup, không phát hành khóa mồ côi |
| One-time retrieval token expired | Thu hồi token, reissue token hoặc regenerate key theo policy |
| Client chưa confirm PoP | Không activate; hết hạn phải revoke/cleanup |
| Audit log unavailable khi policy yêu cầu audit bắt buộc | Fail provisioning hoặc dùng durable queue được đánh giá |
| Secret manager return stale version | Không chuyển ACTIVE khi metadata và key version bất nhất |
| Policy cache chưa cập nhật | Không quảng bá key sẵn sàng khi verifier chưa nhận state |
| Approval bị thu hồi | Không tiếp tục issuance/activation |

Cần có **idempotent provisioning workflow** để retry request không tự tạo nhiều khóa ACTIVE ngoài ý muốn. Một operation ID/approval ID giúp nhận diện retry của **lệnh quản trị**, nhưng vẫn không thay thế nonce cho HTTP HMAC client.

### Tính nguyên tử thực tế

Lưu metadata vào relational DB và secret vào vault thường **không nằm trong một giao dịch ACID duy nhất**. Dùng workflow có trạng thái:

~~~text
PENDING_REQUEST
  -> APPROVED
  -> KEY_MATERIAL_CREATED
  -> VAULT_STORED
  -> RETRIEVAL_READY
  -> ACKNOWLEDGED
  -> ACTIVE
~~~

Một reconciler có thể xử lý thao tác dang dở, thu hồi retrieval token, dọn orphan vault entries hoặc tiếp tục an toàn. **Không mở ACTIVE sớm** để che lỗi distributed transaction.

## 13. Java 17: service cấp credential, tách metadata khỏi secret

Một mô hình triển khai nên tách **credential metadata**, **secret storage** và **delivery authorization**. Class dưới là kiến trúc minh họa cho bước tạo key, chưa phải endpoint hoàn chỉnh.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Arrays;
import java.util.Objects;
import java.util.UUID;

record CredentialRequest(
    String clientId,
    String ownerTenant,
    String environment,
    String signingSuite,
    String approvalId
) {}

record ProvisioningReceipt(
    String credentialId,
    String keyId,
    String state,
    Instant createdAt
) {}

interface CredentialRegistry {
    // Ghi bản ghi inactive, có revision/ownership rõ.
    void createPending(
        String credentialId, String keyId,
        CredentialRequest request,
        String secretRef, Instant createdAt);

    void markDeliveryReady(String credentialId);
}

interface ProtectedSecretStore {
    // Store có encryption, least privilege và audit.
    // Không log hoặc trả secret trong exception.
    String putNew(String credentialId, byte[] secret);

    void revokeOrDeleteOrphan(String secretRef);
}

final class CredentialProvisioningService {
    private final HmacSecretGenerator generator;
    private final ProtectedSecretStore secretStore;
    private final CredentialRegistry registry;
    private final Clock clock;

    CredentialProvisioningService(
            HmacSecretGenerator generator,
            ProtectedSecretStore secretStore,
            CredentialRegistry registry,
            Clock clock) {
        this.generator = Objects.requireNonNull(generator);
        this.secretStore = Objects.requireNonNull(secretStore);
        this.registry = Objects.requireNonNull(registry);
        this.clock = Objects.requireNonNull(clock);
    }

    ProvisioningReceipt prepare(
            CredentialRequest req) {
        // Điều kiện tiên quyết phải làm ở lớp quản trị:
        // - authenticated admin/workload, approved request
        // - authorized owner tenant, environment, suite
        // - idempotency/transaction/recovery policy

        String credentialId = UUID.randomUUID().toString();
        String keyId = "hmac-" + UUID.randomUUID();
        byte[] raw = generator.generate256BitKey();
        String ref = null;

        try {
            ref = secretStore.putNew(credentialId, raw);
            registry.createPending(
                credentialId, keyId, req, ref, clock.instant());

            // Không trả raw secret trong receipt.
            registry.markDeliveryReady(credentialId);
            return new ProvisioningReceipt(
                credentialId, keyId,
                "PENDING_DELIVERY", clock.instant());
        } catch (RuntimeException failure) {
            // Chỉ minh họa compensation, không xóa blindly.
            // Production cần trạng thái workflow và reconciler.
            if (ref != null) {
                try {
                    secretStore.revokeOrDeleteOrphan(ref);
                } catch (RuntimeException cleanupFailure) {
                    // Durable audit/reconciliation thay vì
                    // swallow một secret mồ côi.
                    failure.addSuppressed(cleanupFailure);
                }
            }
            throw failure;
        } finally {
            Arrays.fill(raw, (byte) 0);
        }
    }
}
~~~

**Phân tích tính đúng đắn:**

- `CredentialRequest` được coi là **đã qua approval ở tầng quản trị** trong ví dụ. Không được public hóa `prepare` như một API cho mọi caller chưa xác thực.
- Receipt chỉ có metadata: `keyId` **không phải secret**.
- Secret được giữ riêng ở `ProtectedSecretStore`. Nếu store cần mảng byte lâu hơn call, phải copy có kiểm soát; ví dụ giả định `putNew` đã xử lý đồng bộ.
- `UUID` chỉ dùng cho **opaque IDs**, còn secret được tạo bằng `SecureRandom` riêng, **không** bằng UUID.
- `Arrays.fill` giúp giảm thời gian giữ raw buffer nhưng không xóa chắc mọi bản sao ở JCA/vault client.
- Compensation delete khi registry write fail có thể gây race nếu backend đã sử dụng cùng ref; production phải có **idempotent workflow, trạng thái orphan và reconciler** được thiết kế chặt. Không dùng đoạn mã như một distributed transaction tự bảo đảm atomicity.
- Chưa có one-time delivery, proof-of-possession, optimistic locking, policy revision, audit event và operation idempotency. Những phần này phải được bổ sung trước production.

### Một record không được chứa các field nguy hiểm

~~~java
// Không nên đưa raw secret vào toString() của record
// được controller, logger hoặc debugger ghi tự động:
record UnsafeCredential(String keyId, String rawSecret) {}

// Nên tách response metadata và kênh one-time retrieval.
record PublicCredentialInfo(
    String keyId,
    String signingSuite,
    String status,
    String notAfter
) {}
~~~

Với các admin APIs, mặc định **không serialize secret** trong response thông thường. Endpoint nhận secret một lần cần class riêng, no-store và quyền truy cập chặt; không để generic `GET /credentials/{id}` trả key material.

## 14. Spring Security: bảo vệ issuance API

Đường quản trị cấp secret phải được bảo vệ **bằng identity hiện có**, tách khỏi route HMAC của client. Ví dụ Spring Security 6 Servlet:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain credentialAdminChain(HttpSecurity http)
        throws Exception {
    http
        .securityMatcher("/admin/hmac-credentials/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(
                HttpMethod.POST,
                "/admin/hmac-credentials/**")
            .hasAuthority("HMAC_CREDENTIAL_ADMIN")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()));
    return http.build();
}
~~~

Đây là **một đoạn cấu hình minh họa**, cần thêm order/filter chains cho những routes khác, CSRF policy đúng deployment, scope/audience/issuer checks, approval/workflow enforcement, outbound security headers và access audit. Chỉ `hasAuthority` không thay thế **authorization theo owner tenant/client** trong service.

### Thiết kế management endpoints

| Hành động | HTTP ví dụ | Ai được phép? |
| --- | --- | --- |
| Yêu cầu credential | `POST /admin/hmac-credentials` | Client owner hoặc delegated credential admin |
| Phê duyệt | `POST /admin/hmac-credentials/{id}/approve` | Approver độc lập theo policy |
| Lấy secret một lần | `POST /admin/hmac-credentials/{id}/retrieve` | Recipient đã xác thực/được chỉ định |
| Bắt đầu PoP | `POST /admin/hmac-credentials/{id}/challenge` | Đúng recipient và pending credential |
| Gửi PoP | `POST /admin/hmac-credentials/{id}/activate` | Holder của key và session |
| Tạo rotation | `POST /admin/hmac-credentials/{id}/rotate` | Owner/admin có grant |
| Revoke | `POST /admin/hmac-credentials/{id}/revoke` | Security admin hoặc emergency responder |
| Xem metadata | `GET /admin/hmac-credentials/{id}` | Owner/authorized admin, không chứa secret |

Các route trên là **ví dụ thiết kế**, không phải endpoints mặc định của Spring Boot. Cần bảo vệ authorization ở **cấp record**, chống IDOR: người có `HMAC_CREDENTIAL_ADMIN` theo một tenant không được điều khiển credential tenant khác nếu chưa có grant.

**Không** dùng `GET` cho retrieval one-time nếu nó khiến secret bị preload/cached bởi browser/proxy. Dù dùng POST, response vẫn cần `Cache-Control: no-store`, HTTPS, no raw secret logging và bảo vệ khỏi CSRF nếu dùng cookie session.

## 15. Khi secret đã cấp: request phải được xác thực theo canonical contract

Cấp secret chỉ tạo điều kiện để chạy giao thức. Một hợp đồng ký minh họa:

~~~text
HMAC-REQUEST-V1
POST
/api/hmac/orders?currency=VND
application/json
partner-a
partner-a-prod-k004
2026-11-28T04:20:00Z
4ebf5e86-7378-4e4c-b59c-bdbcbf1956b3
<sha256-hex-cua-raw-body>
~~~

Các dòng trong ví dụ dùng LF/UTF-8, không LF cuối; digest cuối là **placeholder**, chưa phải golden vector. Hợp đồng thật phải quy định method, raw URI/query, signed header duplication/normalization, body bytes, timestamp/nonce, signature encoding và key ID.

Sau khi client lấy K4, một HTTP request hợp lệ cần thỏa:

1. `X-Key-Id` chọn chính xác credential K4; không “thử mọi secret cho đến khi khớp”.
2. Credential state `ACTIVE` và đúng environment/API audience.
3. Server tính `SHA-256(rawBodyBytes)` theo contract, không parse rồi serialize lại JSON.
4. Server dựng canonical bytes **giống client** qua proxy/gateway.
5. HMAC-SHA256 khớp dưới **secret K4**; so sánh MAC bằng API phù hợp.
6. Timestamp nằm trong acceptance window; nonce chưa claim.
7. Replay store claim **nguyên tử sau khi MAC đúng**.
8. Principal được dựng từ **registry đáng tin**, không từ header client tự khai.
9. Authorization kiểm tra quyền tenant/action/resource độc lập.

### Java 17: primitive HMAC tham khảo

~~~java
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

final class HmacRequestCrypto {
    static byte[] compute(byte[] secret, byte[] canonical) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(
                secret, "HmacSHA256"));
            return mac.doFinal(canonical);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException(
                "HMAC-SHA256 unavailable", ex);
        }
    }

    static boolean matches(
            byte[] secret,
            byte[] canonical,
            String signatureBase64) {
        byte[] supplied;
        try {
            supplied = Base64.getDecoder().decode(
                signatureBase64);
        } catch (IllegalArgumentException ex) {
            return false;
        }
        if (supplied.length != 32) return false;

        // Demo profile: yêu cầu Base64 chuẩn có padding.
        if (!Base64.getEncoder().encodeToString(supplied)
                .equals(signatureBase64)) {
            return false;
        }

        return MessageDigest.isEqual(
            compute(secret, canonical), supplied);
    }
}
~~~

Đây chỉ là **helper MAC**, không phải verifier hoàn chỉnh; chưa kiểm tra key status, signed bytes, replay, timeout hoặc authorization. Secret nên được lấy từ secret manager bằng reference của đúng credential và không xuất raw key ra logs. Trong gateway HSM không-exportable-key case, `compute` sẽ cần provider-specific key handle thay vì byte array.

### Key material và MAC output không được nhầm

`X-Signature` là output của HMAC, không phải shared secret. Chữ ký có thể xuất hiện trong HTTP logs và vẫn không cho biết secret nếu thuật toán/key mạnh, nhưng vẫn nên **không log full signature** vì chữ ký cùng timestamp/nonce/body có thể trở thành một signed request replayable khi bị kết hợp với payload.

## 16. Cấp secret mới khi rotate: không ghi đè khóa cũ

**Rotation** là tạo key/version **mới**, đưa cho client, rồi chuyển sang dùng khóa mới theo một overlap window có kiểm soát.

~~~mermaid
sequenceDiagram
    participant A as Credential Admin
    participant V as Vault / Registry
    participant C as Client Workload
    participant S as HMAC Server
    A->>V: Create K5, secret S5, status PENDING
    V-->>A: K5 metadata; secure retrieval ready
    C->>V: Authenticated one-time retrieval K5
    C->>S: Activation challenge signed with S5
    S-->>C: K5 ACTIVE / cutover allowed
    C->>S: API request signed with K5
    S-->>C: 2xx when authz allowed
    A->>V: End overlap, revoke K4
    C->>S: Stale request signed with K4
    S-->>C: Authentication failed
~~~

**Không đổi secret của K4 tại chỗ** khi client vẫn gửi `X-Key-Id: K4`. Nếu K4 trỏ lúc thì S4, lúc thì S5, client không biết khóa nào đang hiệu lực, request ngẫu nhiên 401 và verifier dễ phải thử nhiều secret.

### Cách lập lịch cutover

| Giai đoạn | Server | Client | Kiểm tra |
| --- | --- | --- | --- |
| Chuẩn bị | Tạo K5 PENDING, vault lưu S5 | Chưa đổi | Approval + retrieval test |
| Trao đổi | Delivery K5 an toàn | Lưu S5 vào vault của client | PoP challenge K5 pass |
| Dual-key | K4 ACTIVE, K5 ACTIVE | Canary sử dụng K5, còn fallback K4 nếu policy cho phép | Negative tamper/replay + authz |
| Preferred new | K5 ưu tiên, K4 GRACE | Đa số traffic dùng K5 | Metrics theo key version nội bộ |
| Cutover | K4 REVOKED, K5 ACTIVE | Chỉ K5 | MAC K4 đúng vẫn bị reject |
| Cleanup | Xóa/restrict raw S4 theo retention policy | Xóa S4 khỏi secret manager/client | Audit chứng minh không còn use |

Nếu incident cho thấy **K4 bị lộ**, không sử dụng overlap K4 dài như rotation bình thường. Có thể phải **revoke ngay** và chấp nhận downtime cho client chưa nhận K5, tùy threat model.

### Khi hai key ACTIVE cùng lúc

Verifier chỉ dùng **key ID đã khai**, không thử key K4 nếu request khai K5 nhưng MAC sai. Với credential rotation, principal mapping và authorization scope phải nhất quán; không để K5 được cấp wildcard tenant trong khi K4 chỉ có quyền tenant-a.

## 17. Khi mất secret hoặc lộ secret: thu hồi và phục hồi

Sự kiện đáng nghi bao gồm:

- Secret xuất hiện trong Git commit, CI log, stack trace, support ticket, chat.
- Một tài khoản cloud/secret manager bị truy cập trái phép.
- Partner owner không còn kiểm soát server/CI đã giữ secret.
- Nhiều client bất ngờ dùng cùng key ID/secret.
- Có signed requests từ IP/region bất thường cùng credential.
- Secret xuất hiện trong browser/mobile public bundle.

### Runbook ứng cứu

1. **Triage:** xác định key ID/credential/client/tenant/environment và mức độ ảnh hưởng; không phát tán giá trị secret trong incident ticket.
2. **Contain:** khóa credential bị ảnh hưởng tại verifier/registry; nếu nguy cơ đang diễn ra, **revoke ngay**.
3. **Invalidate:** làm mới cache credential state/policy trên gateway/backend; kiểm tra freshness và fail closed nếu không thể xác định trạng thái.
4. **Replace:** sinh secret **mới** và key ID mới bằng quy trình cấp phát đáng tin; không tái sử dụng secret cũ.
5. **Redis/nonce:** bảo đảm replay guard vẫn hoạt động cho request đang bị gửi lại; không xóa nonce store như một bước “reset khóa” tùy tiện.
6. **Audit:** điều tra access logs, provisioning approvals, retrieval events, credential use và side effects bằng metadata an toàn.
7. **Test:** MAC K4 đúng theo old secret phải **bị reject** trên mọi gateway/node; K5 mới pass nếu đã activate.
8. **Close:** khử secret khỏi các nơi lộ, hạn chế quyền, cải thiện runbook và theo dõi bất thường.

**Không** coi việc xóa secret khỏi Git history là hoàn tất xử lý: nếu secret từng bị lộ, phải **revoke/rotate** dù commit được xóa. Tương tự, không chỉ xóa `X-Key-Id` khỏi discovery/portal; verifier phải từ chối key đó.

### Nếu chính secret manager bị ảnh hưởng

Có thể phải rotate nhiều credentials theo blast radius, khóa IAM access, audit secret reads và đánh giá khả năng attacker đã lấy material. Nếu một microservice có quyền đọc toàn bộ kho HMAC keys, blast radius lớn hơn nhiều so với một principal bị giới hạn theo tenant/client.

## 18. Timestamp, nonce và replay trong ngày đầu vận hành

Provisioning không chỉ kết thúc ở việc secret tồn tại. Một client mới thường gây lỗi do **clock drift**, nonce reuse hoặc canonical URL mismatch.

**Checklist tích hợp request:**

- Đồng bộ NTP/clock đáng tin; timestamp format chuẩn UTC.
- Timestamp và nonce **nằm trong signed bytes**.
- Mỗi HTTP attempt dùng nonce mới có đủ entropy; không dùng timestamp làm nonce.
- Replay store dùng `SET NX + TTL` hoặc primitive atomic tương đương.
- Chỉ claim nonce **sau MAC đúng**; MAC sai không được chiếm nonce.
- TTL bao phủ toàn bộ freshness window, bao gồm timestamp ở biên tương lai.
- Multi-instance/gateway dùng cùng scope replay store theo contract.
- Secret/key ID rotation không tạo replay namespace vô tình mở cửa reuse.
- Retry sau timeout có nonce mới và **business idempotency key** riêng.

Ví dụ Redis:

~~~redis
SET hmac:nonce:v1:<scope-digest> 1 NX PX 660000
~~~

Với freshness window đối xứng `±5 phút`, TTL **11 phút** là một ví dụ có margin đủ cho trường hợp request được claim khi timestamp nằm ở biên tương lai, giả định clock policy tương ứng. Không coi giá trị 660000 là chuẩn cho mọi API; TTL phải được suy từ acceptance window/clock skew của hợp đồng thực.

**Không** triển khai `GET nonce` rồi `SET nonce` — hai request đồng thời có thể cùng qua. Redis timeout/lost ACK phải được xem là **UNKNOWN** và fail closed, không coi request là first-use.

### Retry và idempotency

Một request ký bằng K4/nonce N1 đã được chấp nhận nhưng client timeout có thể đã tạo payment. Client **không nên gửi lại nguyên chữ ký N1** để mong replay guard bỏ qua. Hãy ký request mới với nonce N2 và cùng business idempotency key, để server tránh tạo thanh toán kép. Nonce bảo vệ **authentication evidence**, còn idempotency bảo vệ **business intent**.

## 19. Gateway/proxy: secret được đặt ở đâu?

Có hai kiến trúc chính.

### A. Gateway xác thực HMAC

Gateway có quyền dùng secret của client và kiểm tra canonical request/timestamp/nonce. Backend không nhất thiết cần raw secret client. Tuy nhiên, gateway trở thành một **trust boundary**:

- Gateway phải lưu secret qua IAM/vault thích hợp; không ghi key vào config file.
- Gateway chỉ tạo trusted identity assertion sau khi auth pass.
- Backend kiểm tra gateway peer bằng mTLS/workload identity hoặc signed internal assertion có issuer/audience/expiry/method/target/body binding.
- Không cho client tự gửi `X-Authenticated-Client` hoặc `X-Original-URI` rồi backend tin.
- Nếu gateway đã claim client nonce, backend không claim **lại chính nonce client** trên cùng replay key; cần internal assertion `jti`/anti-replay riêng nếu có.

### B. Backend xác thực HMAC

Gateway forward signed headers/body và raw request target theo contract; backend đọc secret K4 từ trusted storage rồi verify. Gateway không nên rewrite/gzip/normalize những trường đã ký ngoài hợp đồng.

| Biến đổi proxy | Câu hỏi bắt buộc khi provision client |
| --- | --- |
| Public path → internal path | Client ký URI nào, verifier thấy URI nào? |
| HTTP/2 → HTTP/1.1 | Header/canonical request có được bảo toàn? |
| Duplicate signed headers | Proxy có từ chối ambiguity không? |
| Query sort hoặc percent encoding | Raw query có đổi sau ký không? |
| JSON transform | Body digest còn khớp bytes không? |
| gzip decompress | Hợp đồng ký compressed hay decompressed bytes? |
| TLS termination | Trust boundary của forwarded metadata là gì? |

**Kết luận vận hành:** tài liệu phát hành secret nên đi kèm **signing contract đã version hóa**, endpoint public, signing suite, header names, timestamp/nonce policy và cách xử lý proxy. Không chỉ gửi một chuỗi Base64 rồi để client tự đoán cách ký.

## 20. Multi-tenant: cấp secret theo principal nhưng cấp quyền theo policy

Một client có thể có key K4 cho tenant-a nhưng muốn gọi một endpoint phục vụ tenant-b. HMAC hợp lệ chứng minh client sở hữu secret K4; **không chứng minh quyền tenant-b**.

~~~mermaid
flowchart TD
    A["Request K4 và signed tenant=b"] --> B["Lookup K4 từ registry"]
    B --> C["Owner principal=partner-a, ownerTenant=a"]
    C --> D{"MAC, key state, timestamp, nonce đúng?"}
    D -->|Không| X["401 authentication"]
    D -->|Có| E["Trusted principal partner-a"]
    E --> F{"Grant cho tenant-b và resource/action?"}
    F -->|Không| Y["403/404 authorization"]
    F -->|Có| G["Business request được xử lý"]
~~~

**Mẫu sai:** đăng ký credential theo `tenantId` từ header client tự khai rồi đưa `tenantId` thẳng vào `SecurityContext` làm effective tenant. Ngay cả khi tenant header nằm trong HMAC, nó chỉ bảo vệ tính toàn vẹn của **claim do client yêu cầu**, không cấp quyền.

### Provisioning có ảnh hưởng authorization

- Credential record gắn owner client/tenant từ IAM.
- Granted scopes gắn với approval, không từ request body tự khai.
- Quá trình activate không tự thêm quyền cho mọi tenant.
- Khi revoke một credential, request mới không được authenticated.
- Khi grant tenant bị thu hồi, HMAC vẫn có thể toán học đúng nhưng authorization phải deny.
- Audit phân biệt **credential created/activated** với **grant created/removed**.

Key rotation cần giữ scope của client theo policy mới, không vô tình mở rộng vì migration.

## 21. Observability và audit không lộ secret

Một sự kiện audit có thể gồm:

~~~json
{
  "event": "HMAC_CREDENTIAL_ISSUED",
  "credentialId": "cred-7f31",
  "clientId": "partner-a",
  "environment": "production",
  "keyVersion": "k004",
  "suite": "hmac-v1-sha256",
  "approvalId": "approval-981",
  "actor": "authenticated-admin-id",
  "result": "PENDING_DELIVERY",
  "occurredAt": "2026-11-28T04:00:00Z"
}
~~~

**Không** đưa `secretBytes`, one-time retrieval token, expected MAC, vault ciphertext, raw body hoặc canonical request nhạy cảm vào audit event.

Những sự kiện cần ghi có kiểm soát:

1. `CREDENTIAL_REQUESTED`/`APPROVED`/`DENIED`.
2. `SECRET_GENERATED`, `VAULT_STORED`, không chứa value.
3. `ONE_TIME_RETRIEVAL_CREATED`/`CONSUMED`/`EXPIRED`, không chứa bearer token.
4. `PROOF_OF_POSSESSION_PASSED`/`FAILED`.
5. `CREDENTIAL_ACTIVATED`/`ROTATED`/`GRACE_STARTED`.
6. `CREDENTIAL_REVOKED`/`EXPIRED`.
7. `CREDENTIAL_ACCESS_POLICY_CHANGED`.
8. `PROVISIONING_FAILED`/`ORPHAN_RECOVERED`.
9. `SECRET_ACCESS_DENIED`/`UNUSUAL_READ_PATTERN`.

### Metrics low cardinality

| Logic metric | Nhãn gợi ý | Mục tiêu |
| --- | --- | --- |
| `hmac.provisioning.requests` | env, result, step | Tỷ lệ cấp phát thành công |
| `hmac.provisioning.duration` | env, step | Độ trễ từng bước |
| `hmac.credential.state` | env, state, suite | Số credentials theo trạng thái |
| `hmac.secret.retrieval.attempts` | env, result | Phát hiện truy xuất bất thường |
| `hmac.credential.rotation.overlap` | env, suite | Theo dõi keys còn GRACE |
| `hmac.authentication.attempts` | route, suite, result, reason | Theo dõi lỗi sau activation |
| `hmac.replay.claims` | result | Theo dõi chống replay |
| `hmac.secretmanager.errors` | dependency, reason | Incident availability |

Tất cả labels cần thuộc allowlist hữu hạn. **Không dùng** raw secret, key ID, client ID, tenant ID, nonce, signature, retrieval token hoặc request ID làm Prometheus labels vì cardinality/PII và khả năng lộ thông tin.

### Alert có hành động cụ thể

- Số credential PENDING_DELIVERY tăng bất thường hoặc tồn đọng quá SLA.
- Tỷ lệ one-time retrieval thất bại tăng.
- Secret manager/registry không khả dụng trên critical route.
- Key đã REVOKED vẫn có **authentication accepted** trên node nào đó.
- Key GRACE vẫn có traffic gần thời điểm cutover.
- Số lần đọc secret ngoài workload/service identity dự kiến.
- Credential mới ACTIVE nhưng positive synthetic HMAC request liên tục 401.
- Replay rate tăng sau rollout, có thể do client reuse nonce hoặc filter double registration.

Alert phải đi kèm runbook, on-call owner và dữ liệu điều tra **không tiết lộ secret**.

## 22. Runbook vận hành hằng ngày: điểm kiểm soát bắt buộc

| Mốc | Người/đơn vị chịu trách nhiệm | Bằng chứng hoàn thành |
| --- | --- | --- |
| Approval | Client owner + approver theo policy | Approval ID, environment, scope |
| Key generation | Credential service/KMS | Entropy source, key length, unique key ID |
| Vault storage | Secret manager operator | Secret ref, access policy, revision |
| Secure delivery | Client owner/management portal | Retrieval consumed, actor, TTL |
| Activation | HMAC verifier + registry | PoP pass hoặc điều kiện policy tương đương |
| Integration smoke | Client + security test harness | HMAC valid, wrong MAC, replay, authz |
| Rollout | Service on-call | Gateway/backend parity, cache freshness |
| Rotation | Credential owner | K5 pass, K4 grace → revoked |
| Emergency revoke | Security responder | Old key rejected all regions |
| Cleanup | Key-management service | Token/secret retention, orphan reconciliation |

**Mọi bước phải dùng dữ liệu thuộc test/sandbox khi thử trước production.** Không “kiểm thử lại” bằng cách in secret production vào terminal hoặc CI output.

### Một checklist onboarding partner

1. Xác nhận đối tác, môi trường, contact chính thức và owner.
2. Chọn signing contract `HMAC-REQUEST-V1` hoặc suite thực tế, freeze test vectors.
3. Chốt canonical method/URI/query/signed headers/body digest và signature encoding.
4. Cấp key ID và secret **riêng** đúng environment.
5. Trao đổi key material qua secure retrieval; không gửi secret trong ticket.
6. Xác nhận partner đã lưu vào vault và hoàn thành PoP.
7. Kích hoạt credential theo policy, scope tối thiểu, TTL/expiry và rate limits.
8. Chạy signed request positive; server sử dụng đúng key ID và verifier.
9. Chạy wrong-secret, body tamper và replay negative; không có side effects.
10. Chạy tenant authorization negative riêng, không suy quyền từ MAC đúng.
11. Test public gateway/forwarded headers và body transformations.
12. Ghi lịch rotation, revocation contact và incident procedure.

## 23. Bộ kiểm thử vận hành Cấp secret

| ID | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| OPS-01 | Request chưa có admin identity | Không cấp |
| OPS-02 | Admin sai tenant/owner | Deny, không tiết lộ credential |
| OPS-03 | Approval thiếu/expired | Không sinh ACTIVE key |
| OPS-04 | Client đúng tenant, approval đúng | Tạo PENDING metadata |
| OPS-05 | Sinh 32-byte secret bằng CSPRNG | Độ dài/encoding đúng |
| OPS-06 | Hai requests sinh khóa mới | Không reuse secret/key ID |
| OPS-07 | KMS RNG fail | Fail closed, không PRNG yếu |
| OPS-08 | Vault write fail | Không ACTIVE; reconcile orphan |
| OPS-09 | Registry write fail sau vault put | Compensation/audit, không phát hành mồ côi |
| OPS-10 | Retrieval token expired | Không trả secret |
| OPS-11 | Retrieval token dùng lại | Deny, không reveal lần hai |
| OPS-12 | Recipient sai client | Deny, không leak key existence |
| OPS-13 | Retrieval over HTTP/no TLS | Reject tại ingress |
| OPS-14 | Response retrieval cacheable | Test FAIL, phải no-store |
| OPS-15 | Secret xuất hiện trong log/ticket/audit | Test FAIL |
| OPS-16 | Activation PoP đúng | Kích hoạt nếu approval còn hợp lệ |
| OPS-17 | PoP bằng wrong secret | Không activate |
| OPS-18 | PoP challenge reuse | Reject replay |
| OPS-19 | PoP challenge sai environment/audience | Reject |
| OPS-20 | Key còn PENDING được dùng gọi API | 401/deny |
| OPS-21 | Key ACTIVE, signed request đúng | Auth pass với nonce mới |
| OPS-22 | Key ACTIVE, request wrong MAC | 401, không claim nonce |
| OPS-23 | Same signed request replay | Reject; no business side effect |
| OPS-24 | Body/URI/header bị sửa sau ký | Reject canonical mismatch |
| OPS-25 | Key đúng nhưng sai quyền tenant | 403/404; no tenant data leak |
| OPS-26 | K4 và K5 overlap rotation | Exact key ID lookup mỗi version |
| OPS-27 | Client khai K5 nhưng dùng secret K4 | Reject, không fallback |
| OPS-28 | Key K4 REVOKED, MAC vẫn đúng | Reject trên mọi node |
| OPS-29 | Cache stale sau revoke | Fail test về revocation freshness |
| OPS-30 | Secret manager timeout | Fail closed, không default secret |
| OPS-31 | Gateway rewrite external/internal URI | Verify đúng signing contract |
| OPS-32 | Client spoof `X-Authenticated-Client` | Không bypass HMAC |
| OPS-33 | Multi-node nonce store | Atomic claim, chỉ first-use |
| OPS-34 | Two admin retries cùng operation ID | Không tạo 2 ACTIVE credentials |
| OPS-35 | Metadata GET trả raw secret | Test FAIL |
| OPS-36 | Key ID bị tái sử dụng khi rotate | Test FAIL |
| OPS-37 | Secret ở staging được dùng production | Reject |
| OPS-38 | Browser/mobile public code chứa HMAC secret | Test FAIL |
| OPS-39 | K5 cutover thành công, K4 vẫn GRACE quá hạn | Alert và revoke theo policy |
| OPS-40 | One-time token ở URL query/log | Test FAIL |
| OPS-41 | Rotation rollback sau emergency revoke | Không tự kích hoạt key cũ |
| OPS-42 | Authorization grant bị gỡ, MAC vẫn đúng | Authn có thể pass, authz deny |
| OPS-43 | Audit service không khả dụng | Theo audit policy, fail/durable queue, không im lặng |
| OPS-44 | Key ACTIVE nhưng secretRef trỏ tới version khác | Reject/key state reconciliation |
| OPS-45 | Signed request thông qua proxy HTTP/2 | Header/URI/body parity |
| OPS-46 | Attacker thử key ID không tồn tại | Public error không tạo enumeration oracle |
| OPS-47 | Credential đã cấp nhưng client chưa retrieve | Giữ PENDING, expiry/cleanup |
| OPS-48 | Incident revoke K4, provision K5 | K4 deny mọi verifier; K5 chỉ pass khi activate |

**Không dùng một HTTP 401 duy nhất làm chứng cứ tất cả đều đúng**. Các test có positive control cần chứng minh credential thật sự ACTIVE và ký đúng, rồi thay **một biến tại một thời điểm**. Test provisioning tách khỏi test HMAC verifier và authorization, nhưng luồng E2E phải nối tất cả.

## 24. JUnit 5: kiểm tra sinh khóa, policy và không lộ trong receipt

Ví dụ test sinh secret không so sánh secret bằng literal cố định:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.Base64;
import org.junit.jupiter.api.Test;

class HmacSecretGeneratorTest {

    private final HmacSecretGenerator generator =
        new HmacSecretGenerator(new SecureRandom());

    @Test
    void generatesThirtyTwoRandomBytes() {
        byte[] key = generator.generate256BitKey();
        assertEquals(32, key.length);

        String encoded = generator.encodeForOneTimeDelivery(key);
        assertArrayEquals(
            key, Base64.getDecoder().decode(encoded));

        Arrays.fill(key, (byte) 0);
    }

    @Test
    void generatesDistinctKeysForIndependentCredentials() {
        byte[] a = generator.generate256BitKey();
        byte[] b = generator.generate256BitKey();

        assertFalse(Arrays.equals(a, b));
        Arrays.fill(a, (byte) 0);
        Arrays.fill(b, (byte) 0);
    }

    @Test
    void rejectsKeyOfWrongLengthForDelivery() {
        assertThrows(IllegalArgumentException.class,
            () -> generator.encodeForOneTimeDelivery(
                new byte[31]));
    }
}
~~~

**Giới hạn:** test randomness ở đây chỉ phát hiện lỗi hiển nhiên như constant key hoặc sai length. Nó **không chứng minh entropy cryptographic**; cần review nguồn RNG/provider, FIPS compliance và key-generation policy.

### Test receipt không trả secret

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class ProvisioningReceiptTest {

    @Test
    void receiptContainsNoSecretField() {
        ProvisioningReceipt receipt =
            new ProvisioningReceipt(
                "cred-7f31", "partner-a-prod-k004",
                "PENDING_DELIVERY", Instant.EPOCH);

        assertEquals("PENDING_DELIVERY", receipt.state());
        assertEquals("partner-a-prod-k004", receipt.keyId());
        assertEquals(4,
            ProvisioningReceipt.class.getRecordComponents().length);
    }
}
~~~

Trong production, nên kiểm tra **HTTP response serialization** và automatic access logs chứ không chỉ cấu trúc Java record. Một custom serializer hoặc exception message vẫn có thể làm lộ secret.

### Integration test skeleton cho activation

~~~java
// Pseudocode: fixtures/approvalService/provisioningClient
// phải được dự án hiện thực.
@Test
void wrongProofNeverActivatesCredential() {
    var req = fixtures.approvedRequest("partner-a", "production");
    var issued = provisioningClient.prepare(req);

    assertEquals("PENDING_DELIVERY", issued.state());

    var challenge = fixtures.activationChallenge(issued.keyId());
    byte[] wrongKey = fixtures.generateOtherSecret();
    byte[] proof = fixtures.signChallenge(challenge, wrongKey);

    assertThrows(AuthenticationException.class,
        () -> provisioningClient.activate(
            issued.credentialId(), challenge.id(), proof));

    assertEquals("PENDING_ACTIVATION",
        registry.find(issued.credentialId()).status());
}
~~~

Đây là **test khung**, không phải mã biên dịch độc lập. Cần thêm tests concurrency, token one-time atomic consumption, vault errors và recovery workflow. Môi trường E2E nên có mock secret manager hoặc isolated vault tenant; không truy cập secret thật của đối tác.

## 25. Các lỗi vận hành thường gặp và cách sửa

### 25.1. Cấp secret bằng copy-paste mẫu trong wiki

**Sai:** mọi client dùng `change-me-please` hoặc `test-secret`. **Đúng:** CSPRNG sinh secret riêng, độc lập theo credential/environment, không tái sử dụng.

### 25.2. Dùng “mật khẩu admin” làm HMAC shared secret

**Sai:** mật khẩu có entropy thấp, reuse qua nhiều hệ thống. **Đúng:** random byte key đúng key-generation policy, quản lý bằng vault/HSM.

### 25.3. Trả secret qua GET metadata

**Sai:** UI, browser cache, reverse proxy hoặc logs có thể lưu. **Đúng:** one-time retrieval qua trusted authenticated channel, response no-store, không log body.

### 25.4. Secret được cấp là tự động có quyền mọi tenant

**Sai:** nhầm authentication với authorization. **Đúng:** owner principal/tenant từ registry, scopes tối thiểu, grant/resource policy kiểm tra ở mỗi request.

### 25.5. Đưa secret vào `application.yml` rồi commit

**Sai:** source và CI artifacts giữ secret lâu dài. **Đúng:** secretRef/IAM và secret store; nếu đã commit secret thật thì revoke/rotate.

### 25.6. Đổi secret nhưng giữ nguyên key ID

**Sai:** hai phía không biết secret nào thuộc ID đó, có thể phải thử nhiều key. **Đúng:** key ID/version mới và overlap có hạn.

### 25.7. Không có cách revoke khẩn cấp

**Sai:** chỉ có rotation theo lịch, secret lộ vẫn dùng được. **Đúng:** security admin có runbook revoke và kiểm tra mọi gateway/verifier đã cập nhật state.

### 25.8. Lưu một `HMAC_SECRET` global cho tất cả

**Sai:** không cách ly client, không có key lifecycle độc lập. **Đúng:** exact credential/key ID lookup và secret material riêng.

### 25.9. Claim nonce trước khi verify MAC

**Sai:** attacker không cần secret vẫn có thể chiếm nonce người dùng hợp lệ. **Đúng:** MAC đúng rồi mới atomic claim.

### 25.10. Cho gateway tin header identity do client gửi

**Sai:** dễ bypass verifier hoặc gán sai principal. **Đúng:** strip untrusted headers, backend xác minh gateway mTLS/signed assertion.

### 25.11. Không kiểm tra secret storage ở client

**Sai:** client lưu key trong public JavaScript/mobile bundle. **Đúng:** chỉ provision shared secret cho workload có khả năng giữ bí mật.

### 25.12. Cho key cũ tiếp tục ACTIVE vô thời hạn

**Sai:** blast radius tăng, khó đảm bảo rotation. **Đúng:** overlap hạn chế, deadline, monitor và revoke theo policy.

### 25.13. Không phân biệt key delivery và activation

**Sai:** một key chưa tới đúng client đã được phép gửi request. **Đúng:** PENDING/PoP hoặc thủ tục approval tương đương và audit.

### 25.14. Khi vault lỗi, tự dùng default secret

**Sai:** tạo credential không kiểm soát; có thể bỏ qua xác thực. **Đúng:** fail closed và reconcile.

### 25.15. Debug bằng cách in full canonical request và chữ ký

**Sai:** canonical có thể chứa sensitive query/body; signature kết hợp request có thể replay. **Đúng:** log route group, key reference nội bộ được bảo vệ, reason enum, correlation ID, không log secret/raw payload.

## 26. Tình huống thực hành: đối tác nhận secret nhưng request vẫn 401

Một nhóm tích hợp production tạo credential cho `partner-a`:

~~~text
clientId: partner-a
keyId: partner-a-prod-k004
suite: hmac-v1-sha256
ownerTenant: tenant-a
status: PENDING_ACTIVATION

Client đang dùng:
  secret từ staging
  URI được ký: /public/v1/orders
  URI backend nhìn thấy: /internal/orders
  timestamp: local time, không UTC
  nonce: timestamp theo giây
  body: JSON được signer parse rồi serialize lại
  retry: dùng lại nonce/signature
~~~

Một kỹ sư đề nghị “bật ACTIVE trước, bỏ body hash và nonce, gửi raw secret trong email để cùng debug”.

Hãy giải thích:

1. Những lỗi nào thuộc **provisioning** chứ không phải MAC primitive?
2. Vì sao secret staging không được chấp nhận ở production?
3. Có nên kích hoạt khi chưa có PoP? Nếu không có PoP, thay bằng thủ tục nào được phê duyệt?
4. Client ký external URI trong khi backend verify internal URI cần hợp đồng proxy nào?
5. Vì sao signer serialize JSON lại có thể đổi digest?
6. Timestamp không UTC và nonce dùng timestamp có nguy cơ gì?
7. Vì sao retry cùng signed request phải bị chống replay?
8. Có thể dùng same business idempotency key với nonce mới thế nào?
9. Vì sao bật ACTIVE tạm thời không giải quyết canonical mismatch?
10. Vì sao gửi secret qua email/ticket làm tăng blast radius?
11. Test nào giúp chứng minh K4 đã được activate đúng mà không lộ secret?
12. Khi HMAC đúng nhưng yêu cầu tenant-b, vì sao vẫn có thể trả 403?

**Hướng giải:** hoàn tất owner verification, secure delivery, proof of possession và activation theo policy; client dùng đúng production secret K4, contract raw URI/body và UTC timestamp/nonce unique. Giữ nguyên body digest và replay guard, không in key ra logs. Test với signed vectors độc lập, gateway E2E và tenant authorization.

## 27. Checklist cấp secret trước khi production

- [ ] Yêu cầu issuance có client identity, tenant owner, environment, scope, suite và contact rõ.
- [ ] Approval đúng actor/role; production hoặc high-risk credentials theo separation-of-duties policy.
- [ ] Secret được sinh bằng CSPRNG/KMS/HSM đáng tin, đủ entropy, không dựa thời gian/UUID/password.
- [ ] Secret độc lập theo client/credential/environment/suite khi cần; không tái sử dụng.
- [ ] Key ID duy nhất và không tái sử dụng khi rotate; không chứa secret.
- [ ] Credential metadata gắn owner principal/tenant, status, notBefore/notAfter, secretRef, suite và revision.
- [ ] Raw secret chỉ ở secret manager/KMS/HSM có encryption, IAM least privilege, audit và availability plan.
- [ ] Không commit secret vào Git, config, image, tickets, logs, APM hoặc client public code.
- [ ] One-time retrieval được xác thực đúng recipient, có TTL, no-store và atomic single-use.
- [ ] Retrieval token không nằm trong URL query/referrer/access log.
- [ ] Secret được đưa tới client qua trusted channel; client giữ trong vault/secret manager riêng.
- [ ] Credential mặc định PENDING, không được xác thực request business trước activation.
- [ ] Proof-of-possession/challenge có audience, expiry, nonce dùng một lần và binding với credential.
- [ ] Issuance workflow có retry idempotency, compensation/reconciler và cleanup orphan.
- [ ] Cấp secret lỗi ở RNG/vault/registry/audit thì fail closed, không dùng default secret.
- [ ] Canonical HMAC request contract được công bố rõ method, URI/query, signed headers/body digest và encoding.
- [ ] HTTP verifier lookup exact key ID/secret/state, không thử mọi secret hoặc key revoked.
- [ ] Timestamp UTC/nonce được ký, replay claim atomic sau MAC đúng, store shared khi multi-instance.
- [ ] Gateway/proxy giữ đúng signed bytes/target; backend không tin forwarded identity header tự khai.
- [ ] Authenticated principal đến từ registry, còn authorization tenant/action/resource chạy độc lập.
- [ ] Client retry có nonce mới và idempotency key riêng cho nghiệp vụ.
- [ ] Rotation tạo key ID+secret mới, overlap có hạn, cutover và revoke key cũ.
- [ ] Emergency revoke có runbook, cache invalidation, conformance test qua mọi node/region.
- [ ] Audit events đủ actor/time/credential/suite/outcome nhưng **không chứa secret**.
- [ ] Metrics cardinality hữu hạn, alert key GRACE quá hạn, vault failures và revoked-key acceptance.
- [ ] JUnit/integration/E2E gồm issuance, delivery, activation, MAC/tampering, nonce/replay, key rotation và tenant authz.
- [ ] Mọi thử nghiệm và diễn tập dùng sandbox/test credentials, không lấy secret production đưa vào công cụ debug.
- [ ] Người sở hữu credential biết thời hạn, quy trình revoke, contact khẩn cấp và chính sách lưu trữ/thu hồi.

**Cấp secret HMAC là một quy trình vận hành có trạng thái, kiểm soát danh tính và trách nhiệm**, không phải thao tác tạo chuỗi Base64. Việc cấp phát chỉ hoàn chỉnh khi secret được sinh an toàn, lưu/trao đúng người qua kênh tin cậy, kích hoạt theo policy và được kiểm chứng bằng request HMAC đầy đủ. Sau đó, mỗi request vẫn phải được ràng buộc với canonical method/URI/header/body, timestamp/nonce chống replay, key rotation/revocation và authorization độc lập.

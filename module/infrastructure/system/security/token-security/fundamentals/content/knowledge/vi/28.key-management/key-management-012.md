# Audit key operation

Trong một hệ thống OAuth 2.0/OpenID Connect, **Authorization Server (AS)** phát access token JWT bằng khóa ký lưu tại KMS/HSM; **Resource Server (RS)** như `orders-api` hoặc `payments-api` dùng public verification key để kiểm chữ ký và claims. Nếu xuất hiện một chuỗi thao tác `Sign` bất thường trên key issuer lúc nửa đêm, đội vận hành cần biết **ai** gọi, **dùng khóa nào**, **đã được cho phép hay bị từ chối**, **đã ký thành công hay chưa**, và các thao tác đó có tương ứng với **token issuance/grant hợp lệ** không.

**Audit key operation** là việc ghi nhận, bảo vệ và phân tích bằng chứng về sử dụng, quản trị và thay đổi trạng thái khóa mật mã. Nó không chỉ là bật log `KMS.Sign succeeded`. Một hệ thống cần đối chiếu **workload identity, key reference/version, operation, authorization decision, outcome, timestamp, correlation, policy version và OAuth issuance context**, đồng thời **không ghi private key, HMAC secret, raw access/refresh token hoặc dữ liệu nhạy cảm** vào logs.

Bài thuộc chương **Key management** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung kết nối mô hình tin cậy/vòng đời JWT và opaque token, access/refresh token, OAuth 2.0/OIDC, kiểm `iss`/`aud`/`scope`, lưu trữ, thu hồi và phòng chống đánh cắp/phát lại token. Trọng tâm là **audit thao tác khóa** tại AS, RS, OAuth Client, KMS/HSM và Secret Manager, không thay bài toán authorization của API.

> **Nguyên tắc:** Ghi **đủ metadata đáng tin để điều tra** mà không tạo kho lưu secrets thứ hai. `Sign=SUCCESS` chỉ chứng minh signer đã ký theo input nhận được; nó **không chứng minh input đó chứa claims hợp lệ** nếu thiếu bằng chứng kiểm client/grant/subject/scope của AS.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt **audit key usage**, **audit key administration**, **AS token issuance audit**, **RS token validation audit** và **business authorization audit**.
2. Liệt kê thao tác cần quan sát: `Generate`, `Import`, `Sign`, `Verify`, `Encrypt`, `Decrypt`, `Wrap/Unwrap`, `Rotate`, `Disable`, `Destroy`, `Export Attempt` và `PolicyChange`.
3. Thiết kế structured events chứa actor, key reference/version, algorithm, purpose, phase, decision, outcome, timestamp và correlation.
4. Phân biệt một **attempt** với **succeeded**, **denied**, **failed** hoặc **outcome unknown** khi hệ thống bị timeout.
5. Liên kết KMS `Sign` với token issuance và OAuth grant của AS mà không ghi raw JWT/private key/credential.
6. Đề xuất retention, quyền truy cập, bảo vệ integrity, clock synchronization và cơ chế phát hiện mất sự kiện audit.
7. Viết detection rules cho signing rate spike, unauthorized decrypt/export, cấp IAM `Sign` bất thường, JWKS rotation và cross-tenant access.
8. Thiết kế policy least privilege cho KMS/HSM, Vault/Secret Manager, OAuth client signer và RS verifier.
9. Minh họa phát audit events an toàn bằng Java/Spring mà không làm lộ raw dữ liệu ký và token.
10. Xây dựng negative tests, forensic correlation và playbook ứng cứu khi khóa bị lộ hoặc audit bị tấn công.

## 2. Audit thao tác khóa là gì, khác audit token như thế nào?

### 2.1. Các lớp bằng chứng

| Lớp | Ví dụ sự kiện | Chứng minh được | Không tự chứng minh |
|---|---|---|---|
| **KMS/HSM operation audit** | `SIGN_SUCCEEDED`, keyRef K7, actor AS. | Provider đã thực thi key operation theo khả năng quan sát. | JWT payload có `scope` đúng grant. |
| **Key administration audit** | `KEY_POLICY_UPDATED`, `KEY_DISABLED`. | Một thay đổi quyền/trạng thái khóa đã diễn ra. | Tất cả RS đã ngừng tin key cũ. |
| **AS token issuance audit** | `ACCESS_TOKEN_ISSUED`, scope/audience/grant. | AS quyết định phát token cho client/grant theo quy trình. | KMS operation chắc chắn hoàn tất nếu không có correlation. |
| **RS token validation audit** | `INVALID_SIGNATURE`, `WRONG_AUDIENCE`. | RS kiểm và từ chối/chấp nhận request theo cấu hình. | Token đó có được người dùng yêu cầu hợp lệ hay không. |
| **Business authorization audit** | `ORDER_READ_DENIED` theo object/tenant. | Policy trên đối tượng đã được kiểm. | Signing key được giữ an toàn. |

Để điều tra `payments:refund` xuất hiện trái phép, phải nhìn đồng thời **AS grant policy, signer operations, RS validations và business authorization**, không chỉ tìm chữ ký đúng.

### 2.2. Audit khác authorization

Một service gọi KMS `Sign` thành công không đồng nghĩa service **có quyền phát JWT `sub=admin`**. Tầng phát token phải kiểm client registration, grant, consent, principal/tenant, scope và audience **trước khi ký**. Audit giúp phát hiện và chứng minh vi phạm, **không được dùng để thay kiểm IAM hoặc token claims**.

### 2.3. Audit khác storage của key/token

Raw HMAC/private key là vật liệu bí mật. Raw access token hoặc refresh token là credential có thể bị replay dù không chứa secret ký. **Không sao chép chúng vào audit system**. Thay bằng internal references, operation IDs, status, key version, trusted actor và outcome.

### 2.4. Không phải thao tác nào cũng cần log từng request

KMS/HSM `Sign`, `Decrypt` và policy changes thường có giá trị audit cao. **RS local `Verify`** xảy ra với lưu lượng rất lớn có thể dùng metrics/counts và security decision logs theo risk/retention policy. Yêu cầu thu thập **từng event hay aggregate** phải căn cứ khả năng provider, quy định và threat model; không giả định mọi KMS tự log mọi hoạt động data plane.

## 3. Taxonomy: thao tác nào cần audit?

| Operation class | Ví dụ | Rủi ro chính | Metadata nên ghi |
|---|---|---|---|
| **CREATE/GENERATE** | Tạo RSA issuer pair, AES KEK. | Sai thuật toán, strength, môi trường. | Actor, keyRef, algorithm class, purpose, approval. |
| **IMPORT/RESTORE** | Import wrapped key, restore HSM backup. | Hồi sinh key bị thu hồi, nguồn key không rõ. | Provenance đã biên tập, source class, approval, key version. |
| **SIGN/MAC** | KMS Sign JWT JWS, HSM HMAC. | Issuer impersonation, token forgery. | Workload, keyRef, algorithm, purpose, outcome, correlation. |
| **VERIFY** | HSM Verify, RS JWT verify. | Algorithm confusion, sai issuer/audience. | Key/profile metadata, error counts, outcome. |
| **ENCRYPT/GENERATE_DEK** | Bọc DEK, AEAD data-at-rest. | Sai context/tenant, dữ liệu lộ. | Key purpose, resource class, operation, result. |
| **DECRYPT/UNWRAP** | Unwrap token-store DEK, decrypt DB field. | Đọc dữ liệu trái quyền. | Actor, keyRef, trusted tenant/context, decision. |
| **READ_SECRET** | Vault read HMAC/client secret. | Raw secret exfiltration. | Actor, secretRef/version, outcome; không log secret. |
| **POLICY_CHANGE** | Cấp `Sign` cho RS, thay HSM role. | Privilege escalation. | Actor, approver, sanitized policy diff, policy version. |
| **ROTATE/ACTIVATE** | K1 → K2, đổi active signer. | Token outage, tiếp tục tin key cũ. | Key IDs, phases, change request, JWKS publication. |
| **DISABLE/ENABLE** | Tạm khóa K1. | Cắt dịch vụ hoặc hồi sinh key compromised. | Actor, reason, incident/change reference, outcome. |
| **DELETE/DESTROY** | Hủy key version/KEK. | Mất khả năng decrypt, mất khả năng phục hồi. | Dependency check, dual approval khi cần, confirmation. |
| **EXPORT_ATTEMPT** | Trích private JWK hoặc HMAC secret. | Credential leak. | Actor, keyRef, denied/allowed, policy, không log raw bytes. |
| **BACKUP/REPLICATE** | Backup HSM, replication sang region. | Tăng bản sao bí mật, quyền ở vùng khác. | Actor, destination class, version, approval, result. |

### 3.1. Management plane và data plane

**Management plane:** tạo, rotate, thay policy, disable/delete, set alias hoặc key lifecycle. **Data plane:** `Sign`, `Verify`, `Encrypt`, `Decrypt`, `Wrap/Unwrap`. Một key có IAM ổn nhưng bị sử dụng ký bất thường vẫn cần phát hiện; do đó không chỉ audit thay đổi IAM.

### 3.2. Risk ranking gợi ý

**Nhạy cảm nhất:** private signing key issuer, HMAC secret chung của nhiều RS, KEK bảo vệ token/PII, client authentication private keys và signing operations có thể cấp quyền lớn. **Ít nhạy cảm hơn về confidentiality:** public JWK fetch, nhưng nếu RS đổi trust anchor hoặc JWKS publish sai vẫn là sự kiện quan trọng về integrity.

### 3.3. Không giả định tên API provider là chuẩn chung

Một nhà cung cấp gọi `AsymmetricSign`, hệ khác gọi `Sign`. Audit normalization nên giữ **provider_operation** (nếu có) và map sang một `operation_class=SIGN`. Với thao tác lạ, đánh dấu `UNKNOWN` để điều tra thay vì phân loại sai.

## 4. Actor identity và ranh giới tin cậy

### 4.1. Actor phải đến từ authentication đáng tin

~~~text
Human operator:
  verified corporate identity + role + session / MFA assurance

Authorization Server:
  workload/authorization-server/prod

Resource Server:
  workload/orders-resource-server/prod

Automation:
  key-rotation-controller + approved change/trigger

External OAuth client:
  registered client_id + authenticated client identity
~~~

Không ghi `actor=user-admin` chỉ vì HTTP body hoặc `X-User-Id` tự khai như vậy.

### 4.2. Actor ký khác subject trong token

~~~text
KMS Sign actor:
  workload/authorization-server/prod

OAuth user subject:
  user-742

OAuth client:
  shop-bff

Access token audience:
  orders-api
~~~

KMS thấy **workload AS**. Nó không tự biết `user-742` đã consent hay có role gì; phải liên kết tới **AS authorization decision log** theo correlation.

### 4.3. Identity delegation qua proxy/sidecar

Nếu requests tới KMS đi qua proxy, provider có thể chỉ thấy actor proxy. Cần **authenticated propagation** của source workload và log proxy có integrity; không tin arbitrary `X-Original-Actor` từ public traffic.

### 4.4. Workload identity và environment isolation

KMS/HSM IAM phải kiểm service principal, namespace, environment, key ID/operation, thời hạn credentials và context. **Dev/staging không được ký bằng production issuer key** chỉ do cùng application name. Break-glass human credentials cũng cần expiry, approval và audit riêng.

## 5. Thiết kế structured audit event

### 5.1. Một sự kiện `Sign` được phép

~~~json
{
  "schema_version": "1.0",
  "event_id": "6b9d7cf4-66ca-459e-a831-a4c750aca068",
  "event_type": "crypto.key.operation",
  "operation_class": "SIGN",
  "phase": "COMPLETED",
  "outcome": "SUCCEEDED",
  "occurred_at": "2026-11-23T02:12:44.227Z",
  "observed_at": "2026-11-23T02:12:44.310Z",
  "producer": "authorization-server",
  "actor": {
    "type": "WORKLOAD",
    "identity_ref": "workload/authorization-server/prod"
  },
  "target": {
    "provider": "managed-kms",
    "key_ref": "kms/prod/as-jwt-signing/v7",
    "key_version": "7",
    "algorithm": "RS256",
    "purpose": "ACCESS_JWT_SIGN"
  },
  "authorization": {
    "decision": "ALLOW",
    "policy_version": "kms-policy-19"
  },
  "context": {
    "issuer": "https://login.example.com",
    "audience_ref": "orders-api",
    "tenant_ref": "tenant-beta"
  },
  "correlation": {
    "trace_id": "d7b19c34d2e149cf995d72ce96b73ace",
    "logical_operation_id": "sign-6d9bb0f9",
    "attempt_id": "sign-6d9bb0f9-attempt-1",
    "grant_ref": "internal-grant-2481"
  },
  "result": {
    "provider_request_ref": "kms-request-48c1",
    "latency_ms": 23
  }
}
~~~

Đây là **schema giáo dục**, không phải KMS/RFC/OpenTelemetry schema bắt buộc. Các internal references có thể là PII/correlation identifiers; giảm tối thiểu, giới hạn RBAC/retention. Provider audit log có thể không có `grant_ref`; giữ grant mapping trong AS audit, nối qua operation ID.

### 5.2. Nguồn dữ liệu và field policy

| Field | Nguồn đáng tin | Không được làm |
|---|---|---|
| `actor.identity_ref` | Authenticated workload/IAM principal. | Copy user ID từ request body. |
| `target.key_ref` | Trusted server key mapping/provider response. | Dùng JWT `kid` của caller làm KMS keyRef. |
| `algorithm` | Signer policy/provider operation. | Tin `alg` attacker gửi mà bỏ allowlist. |
| `authorization.decision` | IAM/policy enforcement kết quả xác thực. | Gán ALLOW chỉ vì event đã được tạo. |
| `outcome` | Provider/result mà producer quan sát. | Coi mọi timeout là FAILED_NOT_EXECUTED. |
| `issuer/audience_ref` | AS-issued token policy context. | Đọc từ raw unverified token rồi tin. |
| `occurred_at` | Producer/provider clock đồng bộ. | Tin client-supplied timestamp. |
| `observed_at` | Collector ingest time. | Coi là exact operation time. |
| `grant_ref` | Internal authorization store. | Dùng raw refresh token hoặc authorization code. |

### 5.3. Dữ liệu tuyệt đối không nên ghi theo mặc định

~~~text
private_key_pem / private_jwk.d
symmetric_jwk.k / hmac_secret
plaintext_dek / hsm_pin
client_secret / token endpoint credentials
raw_access_token / raw_refresh_token
raw_authorization_code / raw_signed_client_assertion
Authorization / Cookie / Set-Cookie headers
raw KMS Sign message or digest if sensitive under policy
raw decrypted plaintext / arbitrary ciphertext
~~~

Ngay cả `SHA256(email)` hoặc digest từ không gian nhỏ có thể bị đoán/correlation. Chỉ dùng **internal opaque reference** hoặc keyed pseudonym nếu cần, phải bảo vệ và giới hạn thời hạn lưu.

### 5.4. Schema version và trace IDs

Gắn `schema_version`, `event_id`, `trace_id`, `logical_operation_id` và `attempt_id`. Nếu retry, **một logical operation có nhiều attempts thật**; đừng xóa mất các attempts khi deduplicate. Correlation ID phải là định danh không bí mật, không chứa JWT/token string.

### 5.5. Producer vs provider audit

AS có thể ghi `SIGN_REQUESTED`; KMS ghi `Sign authorized/succeeded`; AS ghi `ACCESS_TOKEN_ISSUED`. Ba nguồn có độ tin cậy khác nhau. **Không coi một event do client app tự gửi có quyền chứng minh provider đã ký**. Đối chiếu producer identity, request IDs và provider logs.

## 6. Attempt, denial, success, timeout và duplicate

### 6.1. Mốc thực thi

~~~mermaid
sequenceDiagram
    autonumber
    participant AS as Authorization Server
    participant KMS as KMS/HSM
    participant A as Audit Pipeline
    AS->>A: SIGN_REQUESTED operation O1
    AS->>KMS: Sign with allowed keyRef
    KMS->>KMS: Evaluate caller IAM and key state
    alt Allowed and completed
        KMS-->>AS: Signature plus request ref
        KMS->>A: Provider SIGN_SUCCEEDED
        AS->>A: AS SIGN_SUCCEEDED
    else Permission denied
        KMS-->>AS: Access denied
        KMS->>A: Provider SIGN_DENIED
        AS->>A: AS SIGN_REJECTED
    else Timeout or uncertain response
        AS--xKMS: No confirmed response
        AS->>A: SIGN_OUTCOME_UNKNOWN
    end
~~~

### 6.2. Timeout không chứng minh Sign không xảy ra

~~~text
AS -> KMS: Sign O1
KMS: Sign completed
Network: drops response
AS: timeout
~~~

AS phải ghi **OUTCOME_UNKNOWN** nếu chưa có xác nhận. Khi retry, dùng `attempt_id` khác; xem provider request IDs để xác định có bao nhiêu ký operations thật. Không biến mọi timeout thành `SIGN_FAILED_NOT_EXECUTED`.

### 6.3. Sign thành công khác token được phát

~~~text
GRANT_APPROVED
SIGN_REQUESTED
SIGN_SUCCEEDED
TOKEN_ISSUANCE_COMMITTED
TOKEN_RESPONSE_ATTEMPTED
~~~

`SIGN_SUCCEEDED` chứng minh chữ ký đã tạo, còn `TOKEN_ISSUANCE_COMMITTED` chứng minh AS đã commit các metadata/grant/token state theo thiết kế. Việc ghi response ra socket **không chắc client đã nhận**. Không gộp các mốc này thành một event `token_delivered=true` thiếu bằng chứng.

### 6.4. Denied events cũng quan trọng

Một KMS `AccessDenied` cho `ExportPrivateKey` hoặc `Decrypt` sai tenant là tín hiệu đáng điều tra. Ghi actor, operation, keyRef, reason code **đã biên tập** và policy version; không echo secret, raw plaintext, PII hoặc internal access policy chi tiết cho caller không đáng tin.

### 6.5. Duplicate audit events và retries

Collector thường cung cấp delivery **at least once**, có thể nhận trùng. Deduplicate cùng `event_id/source_event_id` khi tổng hợp, nhưng không gộp những Sign attempts có `attempt_id` khác. Event ordering nên dùng version/sequence/occurred_at theo nguồn; không chỉ tin thứ tự arrival ở SIEM.

## 7. Liên kết KMS Sign với OAuth token issuance

### 7.1. Chữ ký không tự chứng minh grant hợp lệ

Giả sử client `shop-bff` có grant cho `orders:read` nhưng gửi yêu cầu thêm `payments:refund`. **Authorization Server (AS)** phải kiểm client registration, grant, consent, principal/tenant permissions, scope và audience trước khi gọi KMS. KMS/HSM chỉ biết **workload nào được quyền dùng key để ký**, không có đầy đủ bảng OAuth grants hoặc object-level authorization.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant AS as Authorization Server
    participant POL as Grant Policy
    participant K as KMS/HSM
    participant AUD as Protected Audit
    C->>AS: Token grant request
    AS->>POL: Verify client, subject, scope, audience
    POL-->>AS: Approved claims and grant reference
    AS->>AUD: GRANT_EVALUATED + grant_ref
    AS->>AUD: SIGN_REQUESTED operation_id=O1
    AS->>K: Sign exact approved JWS input
    K->>AUD: Provider Sign audit with request_ref=R1
    K-->>AS: Signature
    AS->>AUD: TOKEN_ISSUANCE_COMMITTED + operation_id=O1
    AS-->>C: Token response; no raw JWT in logs
~~~

### 7.2. Ba định danh không được nhầm

| Identifier | Dùng để | Không dùng làm |
|---|---|---|
| `grant_ref` | Tra internal OAuth grant/consent outcome. | Raw refresh token/authorization code. |
| `logical_operation_id` | Nối intent ký với token issuance logic. | `sub` hoặc token value. |
| `provider_request_ref` | Tra operation trong KMS/HSM log. | Proof OAuth grant hợp lệ khi đứng độc lập. |

Provider audit thường **không có grant_ref**, nên AS lưu mapping `logical_operation_id → grant_ref + provider_request_ref` trong audit store với quyền truy cập phù hợp. Không đưa raw JWT, `client_secret` hoặc plaintext signing input vào mapping.

### 7.3. Đối chiếu `Sign` và token issuance

~~~text
Last 5 minutes:
  KMS Sign succeeded = 15,000
  AS committed access/ID JWT issuance = 7,000
  Known canary, retries, special signatures = 300

Unexplained: investigate by purpose, operation ID and keyRef
~~~

Đây là **ví dụ**, không phải công thức quy kết tấn công. Một token có thể cần nhiều ký operation, retry có thể sinh chữ ký không được gửi, và một key có thể được phép ký nhiều loại payload. Phải đối chiếu **purpose, signer, provider request ID, issuer và AS committed issuance**.

### 7.4. Refresh-token audit là sự kiện khác

~~~text
REFRESH_TOKEN_ROTATED / FAMILY_REVOKED
    -> server-side token/grant state

KMS_SIGN_SUCCEEDED
    -> key operation for newly signed access JWT

ACCESS_TOKEN_ISSUED
    -> AS issuance outcome
~~~

Refresh token thường là opaque credential, dùng tại AS token endpoint. Không ghi raw R1/R2 vào logs. Rotation/reuse detection phụ thuộc token family state, **không tự được bảo đảm bởi việc xoay vòng key ký JWT**.

### 7.5. AS phát sai claims dù khóa an toàn

Nếu AS bị lỗi issuance policy và phát `scope=payments:refund` cho client không được phép, KMS `Sign=SUCCEEDED` vẫn là sự kiện ký **đúng theo IAM**. Cần so **scope được yêu cầu, được đăng ký, grant/consent hiện hành, quyền chủ thể và scope thực phát** để tìm lỗi; audit cryptographic key không thay quyền nghiệp vụ.

## 8. Bảo vệ integrity của audit logs

### 8.1. Attacker có thể xóa dấu vết như thế nào?

Một workload bị xâm nhập có thể:

- Tiếp tục gọi KMS `Sign` theo IAM hiện có.
- Tắt application logger/SDK instrumentation.
- Sửa/xóa local files hoặc lọc `SIGN_SUCCEEDED`.
- Gửi event giả `SIGN_DENIED` che một operation thành công.
- Thao túng timestamp từ local process hoặc tạo log injection.
- Dồn sự kiện rác làm đầy queue và khiến logs thật bị drop.

Vì thế, một nguồn độc lập như **provider-side KMS/HSM audit** và **IAM/control-plane change log** có giá trị đối chiếu với AS logs. Không phải provider nào cũng phát mọi data-plane event theo cùng cấu hình; phải xác minh cụ thể.

### 8.2. Pipeline đề xuất

~~~mermaid
flowchart LR
    AS[Authorization Server audit] --> COL[Authenticated Collector]
    KMS[KMS and HSM audit] --> COL
    IAM[IAM and Key Policy audit] --> COL
    COL --> Q[Durable Queue]
    Q --> ARC[Immutable or WORM Archive]
    Q --> SIEM[SIEM Detection]
    ARC --> IR[Controlled Forensic Export]
    SIEM --> SOC[Alerts and Triage]
~~~

- Collector xác thực producer, kiểm schema và rate limits.
- Archive được bảo vệ khỏi sửa/xóa bởi chính signer workload.
- SIEM dùng bản sao thích hợp để truy vấn, không cấp quyền sửa raw evidence.
- WORM/append-only bảo vệ **event sau khi đã nhận**, không chứng minh nội dung nguồn là thật hoặc không có event nào đã bị bỏ ghi.

### 8.3. Tamper-evident hash chain

Trong mô hình cần chứng cứ integrity cao hơn, một stream có thứ tự/partition rõ có thể liên kết:

~~~text
h0 = trusted anchor
h1 = SHA256(domain_separator || h0 || canonical_event_1)
h2 = SHA256(domain_separator || h1 || canonical_event_2)

checkpoint = Sign(audit_attestation_key, h2 || range || timestamp)
~~~

Đây là **pseudocode**: triển khai phải xác định canonical serialization, thứ tự, partition, trusted initial anchor, protected checkpoint và replay/retention policy. Không dùng **issuer JWT signing key** để ký audit checkpoint nếu có thể tách key usage: audit attestation và token issuance có trust/lifecycle khác nhau.

Hash chain không thay log collection từ nguồn độc lập. Nếu attacker kiểm producer và **không ghi một Sign event từ đầu**, chuỗi còn nguyên không chứng minh operation chưa xảy ra.

### 8.4. Quyền truy cập và xác thực nguồn

- Dùng TLS/mTLS giữa producer–collector–archive khi phù hợp.
- Chỉ authenticated provider/workload được đưa events vào đúng source stream.
- Không chấp nhận caller-supplied `X-Audit-Actor` làm identity tin cậy.
- Tách key admin, audit admin và signing workload; signer không có quyền xóa archive.
- Giới hạn raw event access, cho SOC dùng sanitized/normalized views.
- Audit việc thay đổi **log retention, collector policy và SIEM RBAC**, vì chính audit infrastructure cũng có thể bị tấn công.

## 9. Độ tin cậy và mất sự kiện

### 9.1. Synchronous, outbox và asynchronous logging

| Cách | Ưu điểm | Rủi ro |
|---|---|---|
| **Synchronous receipt trước operation** | Ý định thao tác được collector nhận trước ký. | Tăng latency, audit outage có thể làm dừng issuance; intent chưa chứng minh ký thành công. |
| **Transactional outbox của AS** | Intent/issuance event commit cùng database transaction nội bộ. | Không có distributed transaction tự động với KMS; cần relay/retry. |
| **Asynchronous buffered logging** | Ít overhead cho request. | Có thể mất events khi process crash, queue overflow, deploy sai. |

Chọn mô hình dựa trên mức độ quan trọng. Thao tác **Destroy/Export/PolicyChange** có thể yêu cầu audit/approval bền vững trước khi cho phép; với `Sign` throughput cao, cân bằng evidence completeness và availability theo risk policy.

### 9.2. Audit outage không được thành insecure fallback

~~~text
if audit sink unavailable:
    do NOT log raw JWT/private key to local debug file
    do NOT skip signature verification
    do NOT automatically grant KeyAdmin or Export permissions
~~~

Với high-risk key-management actions có thể **fail closed** khi không có bằng chứng audit theo policy. Với token signing, định nghĩa được phép ký tiếp trong **bounded degraded mode** hay phải ngừng issuance; khi còn vận hành cần telemetry loss alarm và provider-side audit đối chiếu.

### 9.3. Detect dropped events

- Heartbeat từ các producers; cảnh báo “im lặng bất thường”.
- Metrics `produced`, `accepted`, `persisted`, `dropped` và queue lag.
- Provider Sign operation count đối chiếu với AS audit count theo window.
- Source sequence/counters nếu có và có guarantee rõ.
- Reprocess từ durable queue sau lỗi normalizer/collector.
- Monitor IAM/event logging disable, policy changes và archive retention changes.

**Không có audit event không phải bằng chứng không xảy ra thao tác khóa** nếu pipeline không đảm bảo completeness.

### 9.4. Duplicate và out-of-order

At-least-once delivery có thể tạo duplicate. Deduplicate theo `source_event_id`/`event_id` cho **cùng event**, nhưng giữ những `attempt_id` khác nhau. Đừng suy thứ tự tuyệt đối theo SIEM ingest time; dùng provider timestamps, source sequence/version, logical operation IDs và clock uncertainty.

## 10. Timestamp, thứ tự và consistency đa vùng

### 10.1. Một operation có nhiều mốc

~~~text
02:12:44.227Z  KMS completes Sign (occurred_at)
02:12:44.310Z  Collector ingests provider audit (observed_at)
02:13:01.000Z  SIEM indexes event (searchable_at)
~~~

Thời gian do provider/workload đưa ra và thời gian collector nhận có thể lệch vì **network, queue, batching và clock skew**. Để điều tra cần đồng bộ time source, đo ingest lag và biết giới hạn độ chính xác. Không kết luận KMS ký sau AS commit chỉ vì provider log đến dashboard muộn.

### 10.2. Trace ID không tạo thứ tự toàn cục

~~~text
AS region A -> queue A -> SIEM
KMS region B -> provider audit stream -> queue B -> SIEM

Result:
  AS issuance event may be indexed before KMS Sign event,
  even if KMS Sign happened first.
~~~

Đối chiếu `logical_operation_id`, provider request IDs, AS grant/issuance state, source sequence và timestamps có uncertainty. Nếu bằng chứng không cho phép xác định thứ tự, ghi **uncertain order**, không đoán.

### 10.3. Audit timeline của key rotation

~~~text
K2_GENERATED
K2_PUBLIC_JWKS_PUBLISHED
K2_ISSUER_SIGNER_ACTIVATED
K1_STOPPED_SIGNING
K1_LAST_AUTHORIZED_TOKEN_EXPIRED
K1_PUBLIC_KEY_RETIRED
~~~

Trong normal rotation, các RS có thể vẫn phải verify JWT K1 còn hạn. Nếu private K1 bị lộ, **emergency cutoff** khác và có thể phải ngừng tin K1 trước expiry. Audit phải theo dõi key state, rollout và xác minh tất cả RS nhận policy mới.

### 10.4. Client-supplied timestamp không đáng tin

Không cho dữ liệu `X-Used-At` hoặc `request.timestamp` do caller tự gửi quyết định forensic order. Dùng server/provider clocks được quản lý và event source identity đáng tin. Với OAuth token assertions, thời gian claims trong token cũng **không thay provider operation timestamp**.

## 11. Privacy, retention và quyền xem audit

### 11.1. Audit metadata vẫn có thể là dữ liệu nhạy cảm

Ngay cả khi không có raw bearer token, subject, tenant, audience, client ID, timestamps và API usage có thể mô tả hoạt động của người dùng. Không mặc định mọi engineer được xem toàn bộ event stream.

| Nhóm | Nhu cầu hợp lệ | Cần giới hạn |
|---|---|---|
| SOC analyst | Key group, operation, outcome, actor risk category, anomalies. | Raw key, token và PII ngoài phạm vi. |
| AS on-call | Signer latency/errors, issuance correlation, rollout. | Decrypted PII và secrets của service khác. |
| Key administrator | Key policy/lifecycle và provider audit metadata. | Xóa/sửa immutable archive và user token values. |
| Privacy/compliance | Reports theo policy, retention và access approvals. | Unredacted data không cần thiết. |
| Forensic investigator | Evidence export được phê duyệt. | Sửa original evidence hoặc truy vấn ngoài case. |
| AS signer workload | Gửi authenticated events. | Xóa/sửa audit history của chính mình. |

### 11.2. Retention theo purpose và quy định

- **Key policy/rotation/delete events** có thể cần giữ lâu hơn high-volume RS verify logs.
- **Provider audit** và **normalized SIEM view** có thể có retention khác nhau.
- Giảm chi tiết user/tenant khi không còn mục đích hợp lệ; dùng pseudonymization có quyền, không coi hash email là ẩn danh tuyệt đối.
- Encryption-at-rest cho audit store dùng khóa riêng, không dùng issuer JWT signing key làm audit encryption key.
- Thiết kế deletion/privacy obligations phù hợp với immutable/WORM archive và chính sách liên quan; WORM không miễn mọi nghĩa vụ.
- Audit chính việc đổi retention, archive policy và quyền xem log.

### 11.3. Forensic export và chain of custody

1. Xác thực investigator và phạm vi case.
2. Ghi incident/change ID, approval và mục đích export.
3. Export source evidence và schema/provider version.
4. Bảo tồn raw logs theo quyền, phân tích trên bản sao.
5. Tạo checksum/export manifest; khi cần ký bằng **audit attestation key riêng**.
6. Ghi các gaps, clock skew, queue lag và độ chắc chắn của kết luận.
7. Không đưa raw JWT, private key hoặc unredacted PII vào ticket/chat thiếu bảo vệ.

### 11.4. Tránh token enumeration qua audit API

Đừng xây `GET /audit?token=RAW_BEARER`: token đi vào URL/proxy/history. Tra bằng internal opaque reference có RBAC, kiểm caller được phép xem metadata. Trong RFC 7662, `active=false` không cho phép công khai token subject/owner khi caller không có quyền.

## 12. Metrics và SIEM detection rules

### 12.1. Các metrics gợi ý

~~~text
crypto_key_operation_total{service,key_group,operation,outcome}
crypto_key_operation_latency_seconds{service,key_group,operation}
crypto_key_permission_denied_total{service,operation}
crypto_key_export_attempt_total{key_group,result}
crypto_key_policy_change_total{environment,result}
crypto_key_audit_delivery_total{source,status}
crypto_key_audit_pipeline_lag_seconds{source}
oauth_token_issuance_total{issuer,profile,result}
oauth_sign_unmatched_operation_total{issuer,key_group}
jwks_key_rotation_phase{issuer,phase}
oauth_resource_invalid_signature_total{resource}
~~~

Không dùng raw `kid` attacker tự khai, user ID, grant/family ID, email hoặc token bytes làm metric labels. Metrics tổng hợp giúp phát hiện spike nhưng không thay full metadata audit cần cho incident.

### 12.2. Detection matrix

| Rule | Dấu hiệu | Phản ứng |
|---|---|---|
| **Unexpected Sign actor** | Workload ngoài issuer signer allowlist gọi key. | Alert cao, kiểm IAM và AS issuance correlation. |
| **Sign rate spike** | KMS Sign tăng bất thường theo key/purpose. | Đối chiếu login burst, retry, issuance và deployments. |
| **Unmatched Sign operations** | Provider Sign không map với AS issuance/approved jobs sau reconciliation. | Điều tra misuse hoặc audit gaps. |
| **Cross-tenant decrypt** | Context key/tenant không khớp record policy. | Alert, kiểm object-level authorization. |
| **Private key export attempt** | Actor thử `ExportPrivateKey`, kể cả denied. | Triage actor, source, token, policy; không log key material. |
| **IAM policy broadened** | Cấp wildcard `Sign`/`Decrypt` hoặc KeyAdmin quyền sai. | Alert và kiểm change approval. |
| **Unexpected key disable** | Disable/delete/enable ngoài approved workflow. | Kiểm account compromise hoặc outage. |
| **JWKS secret exposure** | Public JWKS lộ private `d`/`kty=oct` secret. | Chặn deploy, emergency incident handling. |
| **Rotation inconsistency** | K2 ký trước prepublish hoặc K1 vẫn ký sau cutoff. | Sửa rollout, kiểm RS key caches và alerts. |
| **Audit stream silence** | Sign vẫn tăng nhưng audit producer ngừng ghi. | Kiểm logging tampering/dropped events. |
| **Secret read anomaly** | Secret Manager read nhiều từ identity lạ. | Điều tra exfiltration, rotate theo risk. |

### 12.3. Baseline giảm false positive

Một đợt login lớn hoặc AS restart có thể tăng Sign QPS hợp lệ. Một issuer rotation có thể tạm tăng `unknown_kid`. Baseline nên theo **issuer, key group, purpose, region, giờ, deployment window, token profile**. Không auto-disable issuer key chỉ vì vượt threshold nếu chưa có approved playbook và đo blast radius.

### 12.4. Điều tra `Sign` nhiều hơn issuance

Nếu KMS Sign count 1000 còn AS access token committed 900, kiểm ID tokens, metadata signing, key reuse hợp lệ, retries, cache/queue lag, missing AS events và incomplete correlation. Khi evidence thiếu, kết luận **unknown/pending investigation**, không đánh đồng toàn bộ 100 operations còn lại với token forgery.

## 13. Audit vòng đời khóa và key rotation

### 13.1. State machine cho issuer signing key

~~~mermaid
stateDiagram-v2
    [*] --> GENERATED
    GENERATED --> PREPUBLISHED: Publish public K2 in trusted JWKS
    PREPUBLISHED --> ACTIVE: Sign new JWTs with K2
    ACTIVE --> VERIFY_ONLY: Stop signing old key K1
    VERIFY_ONLY --> RETIRED: Last authorized K1 token expired
    ACTIVE --> COMPROMISED: Private key exposure
    VERIFY_ONLY --> COMPROMISED: Exposure detected
    COMPROMISED --> DISABLED: Emergency deny/cutoff
    RETIRED --> DESTROYED: Approved final destruction
    DISABLED --> DESTROYED: Approved final destruction
~~~

Đây là **mô hình logic**, không phải state values bắt buộc của JOSE/KMS. KEK dùng encryption có thể cần `DECRYPT_ONLY` để mở dữ liệu cũ. HMAC secret còn dùng để verify **vẫn có khả năng tạo MAC**; không có bảo đảm verify-only tách signer như public key bất đối xứng.

### 13.2. Audit normal rotation đầy đủ

~~~text
K2_GENERATED
K2_PUBLIC_JWKS_PUBLISHED
K2_VERIFIER_CANARY_PASSED
K2_ISSUER_SIGNER_ACTIVATED
K1_STOPPED_SIGNING
K1_LAST_VALID_TOKEN_EXPIRED
K1_PUBLIC_KEY_RETIRED
~~~

Ghi actor, approved change, keyRef/`kid`, old/new state version, relevant issuer, affected RS, timestamps và verification tests. Đừng chỉ log một sự kiện `ROTATION_DONE` vì không đủ điều tra giai đoạn gây 401 hàng loạt.

### 13.3. Emergency cutoff khác normal retirement

Khi **private signing key K1 bị lộ**, giữ public K1 trong trusted JWKS có thể cho attacker tiếp tục ký giả. Incident response có thể cần **ngừng tin K1**, revoke/reissue tokens, cập nhật RS/JWKS caches và đo propagation; có thể gây downtime. Audit lý do cutoff và bằng chứng tất cả verifiers đã ngừng nhận K1.

### 13.4. Encrypting keys và key destroy

Với KEK/DEK, `REWRAP`/`DESTROY` audit cần biết key versions, số lượng wrapped DEKs còn phụ thuộc, backup/DR restore tests và approval. **Không ghi plaintext DEK** để “chứng minh” đã rotate. Nếu DEK đã lộ, chỉ rewrap dưới KEK mới **không bảo vệ ciphertext đã bị sao chép**; cần đánh giá reencrypt.

## 14. IAM và separation of duties

| Principal | Quyền phù hợp | Không nên cấp |
|---|---|---|
| **AS signer workload** | `Sign` bằng issuer private key cụ thể. | Export private key, delete key hoặc decrypt mọi data stores. |
| **Orders Resource Server** | Read trusted public JWKS, verify JWS. | `Sign` issuer key, đọc HMAC secret service khác. |
| **Confidential OAuth client** | Dùng client-owned key cho `private_key_jwt`. | Dùng private key AS để phát access token. |
| **Token metadata decryptor** | `Decrypt/Unwrap` đúng KEK/context đã duyệt. | Decrypt mọi tenant/record tùy ý. |
| **Rotation controller** | Stage/activate theo approved workflow. | Tự cấp toàn quyền KeyAdmin và xóa audit archive. |
| **Auditor/SOC** | Read sanitized audit, investigate. | Export raw key hoặc sửa original events. |
| **Break-glass operator** | Privilege ngắn hạn, reason và approval. | Root/admin không hết hạn, không log. |

### 14.1. Denied operation cũng là security evidence

RS thử gọi `KMS.Sign` bằng issuer key phải bị từ chối. Nếu provider phát audit cho denied call, log nó; điều tra **vì sao RS lại thử ký**. Đừng “chữa log đỏ” bằng cách cấp Sign cho RS.

### 14.2. Audit IAM policy diff

Một event policy change cần ghi:

~~~json
{
  "event_type": "crypto.key.policy_changed",
  "key_ref": "kms/prod/as-signing/v7",
  "change_ref": "CHG-1045",
  "actor_ref": "operator-ref-17",
  "approved_by_ref": "review-ref-62",
  "policy_version_before": "18",
  "policy_version_after": "19",
  "added_permission": "SIGN",
  "added_principal_ref": "workload/as/prod",
  "result": "SUCCEEDED"
}
~~~

Không log secrets/tokens hay toàn bộ policy chứa dữ liệu nhạy cảm chưa biên tập. Xác thực rằng approver có authority, policy diff khớp trạng thái cuối và change request chưa bị giả.

### 14.3. Break-glass và hai người duyệt

Khóa issuer/KEK cấp cao có thể cần dual approval cho disable/export/delete hoặc IAM escalation. Break-glass phải có expiry, audit, ticket/case và post-use review. Các controls này **không thay non-exportable key, least-privilege IAM và cảnh báo Sign misuse**.

### 14.4. Multi-tenant context

Một client/actor có `Decrypt` trên KEK tenant Beta **không được** dùng quyền đó với Anpha. Audit metadata nên chứa **tenant_ref đã xác minh** (hoặc security compartment) khi phù hợp. Đừng lấy `X-Tenant-Id` untrusted làm chứng cứ IAM; kiểm grant/record/encryption context tại service.

## 15. Nguồn audit theo công nghệ key store

### 15.1. KMS/HSM operation-based keys

Provider/HSM có thể audit `Sign`, `Decrypt`, key admin và permission denials theo tính năng/cấu hình. Kiểm thực nghiệm:

- Data-plane audit đã bật chưa và có sampling không.
- Event fields gồm authenticated principal, key version và result không.
- Operation IDs/latency/time semantics thế nào.
- Logs nằm ở account/project/region nào, retention bao lâu.
- Ai có thể disable/change audit settings.
- `Sign` có bị ẩn nội dung ký (nên) và có thể correlate với AS issuance không.
- Cách cảnh báo provider audit stream bị ngừng.

**Không giả định mọi provider đều log từng Sign hoặc cùng một schema**.

### 15.2. Secret Manager/Vault: read secret khác Sign

~~~json
{
  "event_type": "secret.version.accessed",
  "operation": "READ_SECRET",
  "actor_ref": "workload/authorization-server/prod",
  "secret_ref": "secret/prod/jwt-hmac",
  "secret_version": "14",
  "outcome": "SUCCEEDED"
}
~~~

Event này chứng minh truy cập **raw secret theo policy**, khác KMS non-exportable `Sign`. Nếu một RS đọc shared HMAC secret, RS có khả năng tạo MAC; audit unusual secret reads và rotate/contain khi bị lộ. Không log giá trị `k` hay HMAC secret trong event.

### 15.3. File-based PKCS#12/Java KeyStore

Một private key đọc từ `issuer.p12` vào Java heap rồi ký bằng JCA `Signature.sign()` có thể **không sinh provider audit độc lập**. Cần instrument application-level signing wrapper, file/OS access audit theo threat model và kiểm memory dump/diagnostics. KeyStore password bảo vệ file ở trạng thái lưu, **không tạo chứng cứ mọi lần ký**.

### 15.4. Browser/mobile key stores cho DPoP

DPoP private key có thể là non-extractable `CryptoKey` hoặc hardware-backed mobile key. Audit khả dụng phụ thuộc platform. Non-extractable giảm khả năng xuất raw key nhưng XSS/malware có thể **gọi API ký trong context đã chiếm**. Ghi proof failures/replay signals tại AS/RS theo profile; không log full DPoP proof token nếu chứa dữ liệu nhạy cảm.

### 15.5. mTLS certificates và issuer key phải tách

Client mTLS private key/certificate-bound access token dùng để chứng minh client identity/sender binding, khác private key AS ký access JWT. Audit certificate issuance/rotation/revocation và authentication failures theo nhu cầu; không dùng key mTLS client làm issuer token signer chỉ vì đều là RSA/EC keys.

## 16. Java: thiết kế audit event theo allowlist

Một cách tránh leak là **không cho logger nhận raw token/key làm tham số**. Tạo immutable event từ các kiểu/IDs được phép và log metadata đã xác minh.

### 16.1. Các type đơn giản

~~~java
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public final class KeyAudit {
    private KeyAudit() {}

    public enum Operation {
        SIGN, DECRYPT, ENCRYPT, GENERATE_KEY, ROTATE,
        DISABLE, POLICY_CHANGE, EXPORT_ATTEMPT
    }

    public enum Outcome {
        REQUESTED, SUCCEEDED, DENIED, FAILED, UNKNOWN
    }

    public record Event(
        String eventId,
        Instant occurredAt,
        String trustedActorRef,
        String trustedKeyRef,
        Operation operation,
        Outcome outcome,
        String logicalOperationId,
        String providerRequestRef,
        String policyVersion
    ) {
        public Event {
            Objects.requireNonNull(eventId);
            Objects.requireNonNull(occurredAt);
            Objects.requireNonNull(trustedActorRef);
            Objects.requireNonNull(trustedKeyRef);
            Objects.requireNonNull(operation);
            Objects.requireNonNull(outcome);
        }
    }

    public static Event newEvent(
            String trustedActorRef,
            String trustedKeyRef,
            Operation operation,
            Outcome outcome,
            String logicalOperationId,
            String providerRequestRef,
            String policyVersion
    ) {
        return new Event(
            UUID.randomUUID().toString(),
            Instant.now(),
            trustedActorRef,
            trustedKeyRef,
            operation,
            outcome,
            logicalOperationId,
            providerRequestRef,
            policyVersion
        );
    }
}
~~~

### 16.2. Ranh giới của ví dụ

- `trustedActorRef` đến từ authenticated workload context, **không** từ arbitrary HTTP header.
- `trustedKeyRef` đến từ trusted signer configuration/provider metadata, không từ JWT `kid` tự khai.
- `logicalOperationId` được server sinh với một format/size cap, không mang token bytes.
- Event **không có trường `token`, `privateKey`, `rawSignInput`, `plaintextDEK` hoặc `clientSecret`** để giảm nguy cơ truyền nhầm.
- `Event` không tự là audit log durable hoặc cryptographically signed. Phải gửi qua authenticated collector/queue và bảo vệ archive.
- `UUID.randomUUID` ở đây là **event correlation identifier**, không được dùng làm bearer token thay `SecureRandom` hoặc authorization code.
- Không đưa `Exception.getMessage()` không kiểm soát vào event vì provider/HTTP exception có thể chứa raw request body/credentials.

### 16.3. Adapter xuất event phải hạn chế fields

~~~java
public interface KeyAuditSink {
    // Sends only allowlisted metadata.
    // Implementations must provide source auth, retry and delivery metrics.
    void publish(KeyAudit.Event event) throws AuditUnavailableException;
}

public final class AuditUnavailableException extends Exception {
    public AuditUnavailableException(String message) {
        super(message);
    }
}
~~~

Nếu audit sink unavailable, policy quyết định nên fail closed hay dùng bounded degraded mode. **Không chuyển sang ghi `Authorization`/signing input vào local debug file**.

## 17. Java/Spring: wrap thao tác Sign mà không log JWT thô

### 17.1. Tách ý định, provider result và issuance result

Giả sử AS đã kiểm grant/claims và có `jwsSigningInput` đúng chuẩn. Về kiến trúc:

~~~text
Authorization policy approves claims
  -> persist or publish SIGN_REQUESTED with logical_operation_id
  -> trusted signer calls KMS/HSM key reference
  -> record provider result:
       SIGN_SUCCEEDED or SIGN_DENIED or SIGN_OUTCOME_UNKNOWN
  -> assemble JWS and commit issuance record
  -> record ACCESS_TOKEN_ISSUANCE_COMMITTED
~~~

Một cách triển khai khái niệm là **wrapper** giữ correlation và mã lỗi đã biên tập. Đoạn Java sau **không tự gọi KMS thật** và không tự xây JWS; adapter signer phải tuân JOSE `RS256`/`PS256`/`ES256` signature encoding.

### 17.2. Interface signer và kết quả đã xác minh

~~~java
public interface ExternalSigner {
    SignedBytes sign(
        String trustedKeyRef,
        byte[] exactJwsSigningInput
    ) throws ProviderDeniedException, ProviderUnavailableException;
}

public record SignedBytes(
    byte[] signature,
    String providerRequestRef
) {}

public final class ProviderDeniedException extends Exception {
    public ProviderDeniedException(String safeCode) {
        super(safeCode);
    }
}

public final class ProviderUnavailableException extends Exception {
    public ProviderUnavailableException(String safeCode) {
        super(safeCode);
    }
}
~~~

**`providerRequestRef` là ID request do provider trả**, không phải raw private key hoặc token. Adapter phải xác thực workload, cố định keyRef/alg theo issuer policy và không cho untrusted request điều khiển arbitrary Sign.

### 17.3. Pseudocode wrapper có kiểm soát

~~~text
function issueSignedAccessToken(verifiedGrant, trustedASContext):
    assert grant, client, subject, scope, aud and purpose authorized
    operationId = newOpaqueOperationId()
    keyRef = activeSigningKeyFromTrustedServerConfig()
    publishAudit(SIGN_REQUESTED, operationId, keyRef,
                 actor=authenticatedASWorkload)

    try:
        result = kms.sign(keyRef, exactJwsSigningInput)
        publishAudit(SIGN_SUCCEEDED, operationId,
                     providerRequestRef=result.requestRef)
    catch ProviderDenied:
        publishAudit(SIGN_DENIED, operationId, safeReasonCode=AUTHZ_DENIED)
        reject issuance
    catch TimeoutOrLostReply:
        publishAudit(SIGN_OUTCOME_UNKNOWN, operationId)
        reconcile provider side; do not claim key was not used
        reject or retry only under controlled policy

    token = assembleCorrectJws(result.signature)
    commitAuthorizedTokenIssuance(verifiedGrant, tokenMetadataRef)
    publishAudit(TOKEN_ISSUANCE_COMMITTED, operationId, grantRef)
    return tokenResponseToAuthorizedClient()
~~~

**Không log `exactJwsSigningInput`, token string hoặc `result.signature` theo mặc định**. Dù signature bytes thường không là private key, giữ đầy đủ message/signature trong log có thể lộ JWT/PII hoặc giúp correlation không phù hợp.

### 17.4. Nếu publish audit lỗi giữa đường

Ví dụ `SIGN_SUCCEEDED` xảy ra, sau đó AS crash trước `TOKEN_ISSUANCE_COMMITTED`. Không được giả rằng token đã được giao cho client. Điều tra đối chiếu provider request, AS DB/outbox và HTTP response instrumentation có giới hạn. Nếu cần bảo đảm hơn, có thể dùng **transactional outbox cho các event thuộc AS DB transaction**, nhưng không hứa transaction nguyên tử giữa KMS và AS database nếu không có giao thức phân tán hỗ trợ.

### 17.5. Không log exception nguyên văn

Một HTTP/KMS client có thể tạo exception chứa request headers, body hoặc credential. Thay vì:

~~~java
// KHONG AN TOAN:
logger.error("KMS failed for token {}", rawJwt, exception);
~~~

nên log:

~~~java
// Minh hoa: only safe constant/error code and operation ID.
logger.warn(
    "KMS sign outcome unknown; operationId={}, keyGroup={}",
    operationId,
    trustedKeyGroup
);
~~~

Key group và operation ID phải từ trusted/validated data, có length cap. Chi tiết exception chỉ đưa vào restricted diagnostics đã scrub và thực sự cần, không mặc định serialize toàn bộ `Throwable`.

## 18. Java/Spring Security: audit validation khác audit signing

### 18.1. RS chỉ cần public verifier key

Một RS dùng Spring Security JWT decoder với issuer/JWKS đáng tin, không cần quyền KMS Sign:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
          jwk-set-uri: https://login.example.com/oauth2/jwks
~~~

Cấu hình chỉ minh họa nguồn key; RS còn cần **audience validator, token purpose, scope và object/tenant authorization**. `issuer-uri`/`jwk-set-uri` phải là trusted settings, không lấy từ `jku` của raw JWT.

### 18.2. RS nên ghi những lỗi nào?

| Error category | Event/metric an toàn | Tránh |
|---|---|---|
| Signature invalid | `JWT_SIGNATURE_INVALID`, issuer config ID, algorithm category. | In full token/signature/raw JWT. |
| Unknown `kid` | `JWT_UNKNOWN_TRUSTED_KEY` count theo issuer. | Raw attacker-controlled `kid` làm metric label; fetch arbitrary URL. |
| Wrong audience | `JWT_AUDIENCE_DENIED` theo resource. | Copy unverified claims/PII vào audit. |
| Token expired | `JWT_EXPIRED` count. | Log raw expired token. |
| Insufficient scope | `ACCESS_DENIED_SCOPE`, route template, required scope class. | Phát toàn bộ user roles/scope strings nhạy cảm vào public logs. |
| Wrong tenant/object | `OBJECT_AUTHZ_DENIED` theo trusted record/tenant reference. | Ghi full order/PII khi không cần. |
| Revoked opaque token | `INTROSPECTION_INACTIVE` theo issuer/resource. | Tiết lộ token owner/revoke reason cho caller. |

Không gộp `SIGNATURE_INVALID` (mật mã), `INVALID_TOKEN` (authentication), `INSUFFICIENT_SCOPE` và `OBJECT_DENIED` thành một lý do lỗi “sai key” vì sẽ gây sai phân tích.

### 18.3. Audit endpoint access cần data minimization

Một route `GET /api/orders/{orderId}` có thể log **route template** thay vì toàn bộ URL/query chứa PII hoặc token. Nếu kiểm ACL tại service, record `decision=DENY` và safe internal subject/object refs theo chính sách, không log full bearer token.

### 18.4. Opaque token introspection

Nếu RS dùng opaque access token, xác minh qua RFC 7662 introspection. `active=false` nghĩa token không được chấp nhận cho caller/context; **không phải sự kiện về signing key**. Audit đúng source: introspection outcome, AS token/grant state và resource policy. Nếu KMS key khác được dùng để mã hóa token store thì `Decrypt` audit là lớp riêng.

## 19. Threat model cho audit key operation

| Lỗi/kiểu tấn công | Hậu quả | Biện pháp |
|---|---|---|
| **Log raw private key/JWK `d`** | Lộ issuer key, kẻ khác có thể ký token giả. | Không thu thập material; secret scanning và emergency rotation. |
| **Log HS256 secret/JWK `oct.k`** | Một verifier/attacker có thể tạo MAC hợp lệ. | Strict allowlist fields, secret storage và access review. |
| **Log raw access/refresh token** | Bearer replay, refresh grant takeover. | Scrub Authorization/body; reference-based correlation. |
| **Log plain DEK hoặc decrypt plaintext** | Lộ dữ liệu mã hóa hoặc chìa khóa mở nhiều records. | Không ghi payload, chỉ safe operation metadata. |
| **Application tự ghi `Sign=SUCCESS` mà provider không xác nhận** | Sai bằng chứng, che thao tác chưa xảy ra. | Provider-side logs, outcome semantics, request correlation. |
| **Provider audit tắt nhưng app tiếp tục ký** | Mù khả năng phát hiện/forensic. | Audit completeness monitoring, bounded degraded/fail-closed policy. |
| **Application có quyền xóa audit archive** | Attacker xóa dấu sau khi misuse signer. | Tách IAM, immutable/WORM archive, out-of-band copies. |
| **Audit producer identity spoof** | Inject event giả che hoặc gây báo động giả. | Authenticated collector, source identity và signatures khi cần. |
| **`kid` từ JWT được log vào labels** | High-cardinality DoS, log injection. | Normalize/size cap, không metric-label raw input. |
| **KMS Sign không có issuance correlation** | Không biết chữ ký phục vụ token nào. | Operation ID và AS issuance ledger, reconcile. |
| **Timeout ghi FAILED_NOT_EXECUTED** | KMS đã ký nhưng dấu vết phủ nhận. | `OUTCOME_UNKNOWN` và provider lookup. |
| **Duplicate event bị xem là nhiều ký operations** | Alert giả, sai số đếm. | Event dedup theo source_event_id, giữ attempts riêng. |
| **Đồng hồ lệch** | Sai điều tra time order. | NTP/clock monitoring, occurred/observed timestamps. |
| **Key policy change chỉ ghi “success”** | Không biết ai thêm wildcard `Sign`. | Sanitized before/after diff, approver và version. |
| **Sign signer có quyền KeyAdmin** | AS compromise có thể xóa key/logs. | Least privilege, separation of duties, deny tests. |
| **RS được cấp KMS Sign** | RS compromise thành issuer impersonation. | Public verify-only RS, IAM rules. |
| **AS ký claims mà chưa kiểm grant** | Token scope/audience sai dù chữ ký đúng. | Issuance policy validation và AS/RS audit correlation. |
| **Export attempt bị coi noise** | Bỏ qua dấu hiệu exfiltration. | Alert denied `ExportPrivateKey`/`ReadSecret` bất thường. |
| **Audit retention quá ngắn** | Không có evidence khi phát hiện compromise muộn. | Risk/requirements-based retention, protected backups. |
| **Audit retention quá dài không giới hạn** | PII/tracing dataset nhạy cảm tích lũy. | Data minimization, lifecycle/retention policy. |
| **Hash chain không có độc lập checkpoint** | Attacker có thể tái tạo cả chuỗi. | Independent attestation key/pinned checkpoint. |
| **Tin hash chain là chứng minh sự thật** | Sự kiện giả/bị bỏ vẫn “có hash”. | Provider source/authentication và completeness controls. |
| **Public JWKS vô tình chứa private fields** | Token signer secret bị công bố. | Automated public-only projection tests và incident. |
| **Rotate key nhưng audit thiếu phase** | Unknown kid/401 hàng loạt, khó điều tra. | Key-state/issuer/JWKS/RS canary timeline events. |
| **Audit query tìm theo raw token URL** | Token lộ ở HTTP logs/history. | Internal opaque references, authorized query API. |

### 19.1. Security event không nhất thiết là incident

Một `ACCESS_DENIED` đơn lẻ có thể do configuration bug, không phải tấn công. Nhưng một workload chưa đăng ký thử export key, cùng với key-policy modification và spike Sign là chuỗi đáng điều tra. Kết luận phải dựa trên **nhiều nguồn và evidence quality**.

### 19.2. Dùng audit để bảo vệ privacy cũng quan trọng

Một audit system có thể chứa subjects/tenants/grants đủ để tạo lịch sử hoạt động người dùng. Kiểm RBAC, justification, retention, cross-region sharing và truy cập investigator như dữ liệu an ninh nhạy cảm. Không biến `security` thành lý do để thu toàn bộ raw claims/token payload.

## 20. Incident response: nghi ngờ key bị lạm dụng

### 20.1. Tình huống

SOC nhận alert:

~~~text
Time window: 10 minutes
Key: as-jwt-signing K7
Unexpected actor: workload/legacy-batch/prod
Provider Sign succeeded: 4,500
AS access/ID token committed: 1,200
Audit pipeline health: some delay in region B
~~~

Không kết luận ngay có 3.300 token giả. Cần reconcile ký ID/access tokens, retries, provider audit lag và legitimate batch jobs, rồi đánh giá anomaly.

### 20.2. Playbook

1. **Xác minh alert:** actor thực, keyRef/version, data-plane outcome và provider timestamp.
2. **Kiểm nguồn:** KMS/HSM operation audit, AS signer logs, OAuth grants, IAM policy diffs, deployment changes.
3. **Khoanh vùng:** tạm chặn `Sign` cho workload bất thường theo approved incident policy; không làm gián đoạn mọi issuer nếu chưa cần.
4. **Xác định blast radius:** key dùng ký ID/access/client assertion gì, audiences/RS nào trust public key, token lifetime và sessions.
5. **Đánh giá kiểu compromise:** lộ **raw private key**, lộ **HS256 shared secret**, hay chỉ **misuse Sign API**? Ba trường hợp có phương án khác.
6. **Bảo vệ evidence:** giữ raw provider events/AS ledgers, access logs và sanitized correlation mapping; chặn log deletion/tampering.
7. **Containment token/grants:** revoke tokens/refresh family khi áp dụng; nếu private key bị lộ, cân nhắc emergency cutoff key trust ở mọi RS.
8. **Xác minh RS:** token ký bằng key đã bị cutoff còn được chấp nhận ở đâu? JWKS caches/regions, stale auth context và issuer mapping.
9. **Khắc phục gốc:** IAM/wildcard permissions, workload identity, AS policy, key custody, audit coverage.
10. **Post-incident:** đo time-to-detect, time-to-contain, gaps và bổ sung tests/rules.

### 20.3. Key compromise khác bearer token theft

Một bearer JWT bị lộ có thể bị replay trong thời hạn/permission của nó. Một **issuer private signing key** bị lộ có thể cho phép tạo vô số JWT giả cho đến khi RS ngừng tin key. Hệ thống có thể phải rotate/disable key và reissue tokens. Không dùng key rotation diện rộng để xử lý một session logout nếu token revocation phù hợp.

### 20.4. Lộ HMAC secret khác lộ public JWK

Public JWK RSA/EC/OKP verification key được thiết kế để công bố. **Private JWK `d` hoặc symmetric `oct.k` xuất ra JWKS** là sự cố nghiêm trọng, cần rotate/cutoff. Việc đổi JWKS phải có audit trước/sau và kiểm verifiers không nhận sai key.

### 20.5. Audit source bị nghi giả mạo

Nếu một AS instance bị chiếm và gửi events sai, không sửa original history; phân biệt source trust, giữ provider audit và kiểm độc lập. Khi báo cáo điều tra, nêu **gaps và độ chắc chắn**, không tô lại một event `SUCCEEDED` mà chưa xác minh thành provider success.

## 21. Ma trận kiểm thử Audit key operation

### 21.1. Fixtures và phạm vi

~~~text
Test issuer:    https://login.test.example
Test token API: orders-api
Test signing key: test-as-signing K1, RSA, RS256
Test rotation key: test-as-signing K2
Test HMAC key: test-shared-hmac H1 (not exposed in public JWKS)
Test KEK: test-token-store-kek
Test OAuth client: shop-bff
Test subject: user-test-742
Test tenant: tenant-beta

Actors:
  as-signer-prodlike
  orders-rs-prodlike
  rogue-batch
  key-rotation-controller
  audit-collector
  forensic-readonly

Audit sources:
  KMS test operation log
  AS signing/issuance ledger
  IAM/key-policy change log
  RS validation/authorization decisions
  protected collector/archive
~~~

Đây là **môi trường test giả lập/cô lập**, không dùng production private keys, HMAC secrets hay raw access tokens thật. Tất cả tests phải reset key/grant state và dùng clocks/trace IDs riêng.

### 21.2. Operation và IAM tests

| Test | Điều kiện | Kỳ vọng |
|---|---|---|
| AS signer gọi `Sign` đúng key | Workload đã được IAM cho phép. | Provider operation success, actor/key/alg/result được audit. |
| RS chỉ giữ public verifier | Orders RS thử `KMS.Sign`. | Denied, có security event khi nguồn hỗ trợ. |
| Rogue batch gọi issuer key | Actor không có permission. | Denied, alert unexpected actor. |
| AS signer thử `ExportPrivateKey` | Non-exportable key/operation bị cấm. | Denied, export-attempt audit và alert. |
| Auditor thử `Decrypt` token store | Auditor chỉ có quyền read logs. | Denied; không nâng quyền vì có audit role. |
| KeyAdmin đổi IAM policy | Có approved change. | Before/after sanitized diff, actor, approver, version. |
| KeyAdmin cấp wildcard `Sign` | Change không được phép. | Policy gate deny/cảnh báo và audit attempted change. |
| Break-glass quá hạn | Token/role hết hạn. | Denied và recorded attempt. |
| Dev workload dùng prod key | Sai environment/identity. | Denied, không dựa chỉ app name giống nhau. |
| Cross-tenant `Decrypt` | Tenant Beta cố mở record Anpha. | Denied theo context/record authorization. |
| HSM key disable | Approved operator, policy. | State transition audit chính xác. |
| Key delete còn dữ liệu phụ thuộc | KEK còn wrapped DEK chưa migrate. | Block by dependency/approval policy hoặc audit failure an toàn. |
| Secret Manager read H1 | Đúng actor/version. | Read event chỉ metadata, không có value. |
| HMAC secret trong public JWKS | JWKS có `kty=oct`/`k`. | Security test fail, xử lý key exposure. |

### 21.3. Event schema, privacy và correlation tests

| Test | Thao tác | Kỳ vọng |
|---|---|---|
| Sign event đủ trường | Gửi `SIGN_SUCCEEDED`. | Có eventId, timestamp, trusted actor, keyRef, outcome và source. |
| Actor spoofing | Client đặt `X-Audit-Actor=admin`. | Collector không dùng input này làm trusted principal. |
| Raw JWT trong exception | Signer throw lỗi chứa request. | Event/log allowlist không ghi raw token. |
| Raw refresh token | Mock request refresh credential. | Audit chỉ dùng grant/family reference nội bộ. |
| Private JWK trong event | Test gửi `d`/`k` material. | Schema/logger scrub hoặc reject, security test fail. |
| Plaintext DEK trong decrypt event | Inject canary DEK. | Không tồn tại trong log/archive/traces. |
| Sensitive digest | Digest từ username/PII có thể dò. | Không log raw digest khi không có policy và purpose hợp lệ. |
| Untrusted keyRef | HTTP request yêu cầu `keyRef=prod-root`. | AS chỉ chọn trusted configured key, không audit như key đã dùng nếu bị reject. |
| KMS request ID correlation | Provider event và AS ledger cùng operation. | Liên kết đúng một logical operation/attempt theo schema. |
| Wrong grant correlation | Client gửi `grant_ref` giả. | AS xác minh server-side, không gắn event với grant của user khác. |
| Duplicate delivery | Collector nhận lại cùng source_event_id. | Aggregate dedup, original evidence preserved. |
| Different attempts | Retry ký cùng logical operation. | Giữ cả attempt-1/attempt-2, không xóa nhầm. |
| Timeout outcome | KMS ký xong nhưng response mất. | AS ghi UNKNOWN; provider reconciliation xác định. |
| Token issuance vs Sign | Sign succeeded nhưng AS commit fail. | Không ghi TOKEN_ISSUANCE_COMMITTED khi chưa commit. |
| Negative provider event | Unauthorized Sign. | Denial được ghi/alert, không chỉ thu successes. |
| Audit query dùng raw token | Client thử URL `?token=...`. | Endpoint không chấp nhận/không log raw credential, query bằng internal ref. |

### 21.4. Tamper resistance và audit reliability

| Test | Thao tác | Kỳ vọng |
|---|---|---|
| Signer xóa archive | Workload IAM cố delete logs. | Denied. |
| Collector nhận event giả | Producer không authenticated. | Reject, security alert. |
| Signed checkpoint bị sửa | Modify event cũ sau checkpoint. | Hash/integrity verification fails khi scheme dùng. |
| Rebuild hash chain giả | Attacker tái tạo chuỗi không có trusted checkpoint. | Forensic verification không coi đó là bản chuẩn. |
| Missing producer events | AS logger bị tắt, provider Sign vẫn có. | Audit completeness alert. |
| Queue overflow | Tăng tải vượt capacity. | Dropped-event metric/alert, không silent loss. |
| Collector timeout | Không gửi được event ngay. | Retry/queue policy rõ, không dump raw signing input. |
| App crash after Sign | KMS success, AS không ghi completion. | Reconciliation xác định gap/unknown. |
| Out-of-order arrival | Issuance log đến trước Sign log. | Correlation vẫn đúng, không suy order theo ingest time. |
| Clock skew | Producer lệch 90 giây. | Drift monitoring, timestamps có source/uncertainty. |
| Log injection | Client-controlled text chứa newline/JSON. | Serialization/escaping/size limits, không phá schema. |
| Audit archive retention change | IAM actor cố giảm retention trái quyền. | Deny/alert; policy changes audited. |
| Cross-region copy | Audit log đi sang vùng khác. | Data residency/retention policy được kiểm. |
| Forensic export | Authorized investigator xuất case. | Approval, manifest/checksum, chain of custody. |

### 21.5. Token/crypto lifecycle tests

| Test | Điều kiện | Kỳ vọng |
|---|---|---|
| JWT RS256 valid | AS signs with K1. | RS verifies using issuer public JWKS; audit metadata đúng. |
| JWT wrong audience | `aud=payments-api` tại Orders. | RS rejects; không chấp nhận vì key đúng. |
| JWT wrong issuer | Token từ issuer lạ. | Reject; validation audit không giả signer compromise. |
| JWT ID token used as access | `aud=shop-web` tại Orders. | Reject token purpose/audience. |
| OAuth scope escalation | Client xin `payments:refund` không có grant. | AS không gọi Sign cho token sai quyền; deny/audit. |
| Refresh family revoked | R1/R2 state revoked. | Không phát access token mới; token-store audit và signer audit phân biệt. |
| K2 prepublished | Public K2 trong JWKS trước khi ký. | Verifiers resolve K2, audit rollout/canary. |
| K2 signer activated | AS phát `kid=K2`. | Provider operations và AS issuance map đúng K2. |
| K1 verify-only | K1 không compromise, tokens còn hạn. | RS tiếp tục verify theo policy, AS ngừng ký K1. |
| K1 private compromised | Incident cutoff. | Mọi RS trong scope từ chối K1 theo emergency SLA, audit checkpoints. |
| JWKS unknown `kid` flood | Nhiều random key IDs. | Bounded refresh, high-cardinality protection. |
| DPoP proof key mismatch | Holder key sai. | RS rejects; proof validation metadata an toàn. |
| mTLS private key rotation | Client cert đổi. | Actor/cert binding audit, token rebind theo profile. |

## 22. Pseudocode kiểm thử end-to-end và diễn giải kết quả

### 22.1. Một Sign operation có đủ evidence

~~~text
test "AS issuance correlates to provider Sign":
    grant = testAS.approveGrant(
        client="shop-bff", scope={"orders:read"},
        audience="orders-api", subject="user-test-742"
    )

    result = testAS.issueSignedAccessJwt(grant)
    assert result.token is not empty

    asEvent = audit.find(
        eventType="TOKEN_ISSUANCE_COMMITTED",
        logicalOperationId=result.operationId
    )
    kmsEvent = providerAudit.find(
        keyRef="test-as-signing/K1",
        requestRef=asEvent.providerRequestRef
    )

    assert kmsEvent.operation == "SIGN"
    assert kmsEvent.outcome == "SUCCEEDED"
    assert kmsEvent.actor == "as-signer-prodlike"
    assert asEvent.grantRef == grant.internalRef
    assert ordersRS.verifies(result.token)
    assert audit.containsNoRawTokenOrPrivateKey()
~~~

### 22.2. Không nhầm timeout với failure chắc chắn

~~~text
test "sign result unknown after lost response":
    provider.completeSignButDropResponse(operationId="O2")
    result = testAS.trySign(operationId="O2")

    assert result.outcome == "UNKNOWN"
    assert audit.has("SIGN_OUTCOME_UNKNOWN", operationId="O2")

    providerEvent = providerAudit.lookup("O2")
    assert providerEvent.outcome == "SUCCEEDED"

    assert not audit.claims("SIGN_NOT_EXECUTED", operationId="O2")
    assert retriesHaveDistinctAttemptIds()
~~~

### 22.3. RS không được dùng AS signing key

~~~text
test "resource server has verify permission only":
    K1 = testIssuer.getTrustedPublicJwk()
    assert ordersRS.verifyJwtWith(K1) works

    assert iam.denies(
        principal="orders-rs-prodlike",
        operation="Sign",
        keyRef="test-as-signing/K1"
    )

    assert providerAudit.hasDeniedAttempt(
        actor="orders-rs-prodlike",
        keyRef="test-as-signing/K1"
    )
~~~

### 22.4. Cross-tenant decrypt audit

~~~text
test "tenant-bound KEK cannot decrypt unrelated record":
    betaRecord = encryptForTenant(
        tenant="tenant-beta", data=testPayload
    )

    expectDecryptSuccess(
        actor="allowed-beta-decryptor",
        record=betaRecord,
        trustedTenant="tenant-beta"
    )

    expectDecryptDenied(
        actor="anpha-decryptor",
        record=betaRecord,
        trustedTenant="tenant-anpha"
    )

    assert audit.neverIncludesPlaintextDEKOrRecord()
~~~

### 22.5. Log tampering và missing event

~~~text
test "provider audit reveals missing AS Sign event":
    testKms.signAsAuthorizedAS(operationId="O3")
    testAS.suppressApplicationLogForTest("O3")

    detection.reconcile(
        providerSignOperations,
        asSigningLedger,
        withinConfiguredWindow
    )

    assert detection.hasAlert(
        type="UNMATCHED_SIGN_OPERATION",
        operationId="O3"
    )

test "audit archive is not editable by signer":
    assert iam.denies(
        actor="as-signer-prodlike",
        operation="DeleteAuditArchive"
    )

test "tampered event is detected after checkpoint":
    archive.appendAndCheckpoint(testEvents)
    archive.corruptForIsolatedTest(eventId="E1")
    assert verifyAuditCheckpoint() == INTEGRITY_FAILURE
~~~

### 22.6. Kiểm thử có ý nghĩa gì, không có ý nghĩa gì?

Pseudocode không phải mã chạy trực tiếp; integration test thật cần IAM provider/test KMS/HSM, AS/RS môi trường cô lập, reliable message bus/collector, fake clock, keys/token test và backend authorization policy. Một test báo `audit.has(...)` **không chứng minh provider audit gốc đã được xác thực** nếu toàn bộ dữ liệu đều do mock application tự sinh. Phải có tests kiểm **provenance, permission denial, delivery failure, correlation và forensic integrity**.

**Tuyệt đối không dùng private signing key production, thực hiện key disable/delete production hoặc cố lấy raw credentials thật** để chạy bài kiểm thử.

## 23. Bài tập tình huống có đáp án

### Bài 1 — KMS ký thành công nhưng AS không cấp token

~~~text
10:00:00  AS receives a valid grant.
10:00:01  KMS logs Sign SUCCEEDED.
10:00:02  AS database transaction fails.
10:00:03  Client receives HTTP 500.
~~~

**Câu hỏi:** Có thể ghi `TOKEN_ISSUED=SUCCESS` chỉ vì KMS ký thành công không?

**Đáp án:** **Không.** KMS đã tạo chữ ký, nhưng issuance commit/response chưa hoàn tất. Ghi `SIGN_SUCCEEDED` và `TOKEN_ISSUANCE_FAILED/UNKNOWN` theo contract thực. Đối chiếu grant record, operation ID và provider request ID; không gộp hai giai đoạn.

### Bài 2 — Timeout sau Sign

AS gửi request `Sign`, KMS ký xong nhưng network mất gói phản hồi. AS retry.

**Đáp án:** Ghi kết quả request đầu là **OUTCOME_UNKNOWN**, giữ `attempt_id` riêng cho retry. Provider audit có thể xác nhận operation thứ nhất đã xảy ra. Không kết luận “khóa chưa được dùng” từ timeout và không gộp hai attempts thành một chỉ vì cùng grant.

### Bài 3 — Dev workload có quyền ký production JWT

Một thay đổi IAM vô tình cấp `kms:Sign` trên `as-prod-key` cho `workload/dev-batch`.

**Đáp án:** Đây là **privilege escalation** cần alert ngay cả khi dev-batch chưa ký token nào. Audit `KEY_POLICY_CHANGED` phải cho biết actor, approver, before/after diff, thời điểm và keyRef. Chặn/rollback quyền trái policy, kiểm Sign attempts và grant issuance trước/sau thay đổi.

### Bài 4 — Có public JWKS là đủ để audit key operations?

Một team chỉ lưu `/.well-known/jwks.json` theo ngày, không có KMS operation logs.

**Đáp án:** **Không.** Public JWKS cho biết public verification keys theo thời điểm lấy mẫu, không cho biết ai gọi `Sign`, `Decrypt` hoặc sửa IAM. Cần provider-side/application audit, key activation timeline, permission checks và correlation với AS issuance.

### Bài 5 — KMS Sign nhiều hơn token phát

KMS báo 1.500 Sign successes; AS chỉ có 1.200 `ACCESS_TOKEN_ISSUED`.

**Đáp án:** **Chưa đủ bằng chứng** có 300 tokens giả. KMS có thể ký ID tokens, metadata, canaries và retries; AS có thể thiếu events hoặc có issuance failed. Đối chiếu logical operation IDs, key purpose, provider request IDs, queue delay và AS grants trước khi kết luận.

### Bài 6 — Một JWT Bearer bị ghi vào audit

Một developer muốn log `Authorization: Bearer T1` vào `SIGN_REQUESTED` để dễ tìm.

**Đáp án:** **Không được.** Raw bearer token còn hạn có thể bị replay; refresh token còn nguy hiểm hơn vì có thể xin access token mới. Dùng internal token record/grant reference với RBAC; không đưa raw token vào SIEM, ticket hoặc metrics.

### Bài 7 — WORM archive chứng minh không có thao tác ký trái phép?

Team thấy audit archive là immutable và không có event `SIGN_UNAUTHORIZED`.

**Đáp án:** Không chắc. WORM ngăn sửa/xóa **những events đã ingest**, không chứng minh producer không bỏ event, KMS logging đã bật hay event bị drop ở queue. Cần provider audit source, completeness metrics, heartbeat, reconciliation và independent evidence.

### Bài 8 — `kid` bị attacker biến thành thousands labels

Một actor gửi hàng triệu JWT với random `kid`, RS ghi `jwt_unknown_kid_total{kid=...}`.

**Đáp án:** Đây có thể là high-cardinality DoS/telemetry abuse. **Không dùng raw `kid` làm metric label**. Giới hạn kích thước, sanitize nếu cần trong restricted logs, aggregate theo trusted issuer/resource và kiểm bounded JWKS refresh.

### Bài 9 — K1 bị compromise nhưng vẫn verify-only

Private issuer key K1 bị lộ; hệ thống giữ public K1 30 phút để không làm hỏng JWT cũ.

**Đáp án:** Không áp normal rotation máy móc. Attacker có private K1 có thể ký giả token còn được RS nhận. Cần emergency trust cutoff/revoke/reissue, audit việc ngừng tin K1 trên tất cả RS, chấp nhận availability trade-off theo incident plan.

### Bài 10 — Decrypt đúng key, sai tenant

Token metadata store dùng KEK tenant Beta. Một workload có quyền `Decrypt` chung gọi mở ciphertext Beta để xử lý request tenant Anpha.

**Đáp án:** KMS may decrypt nếu IAM quá rộng, nhưng **business authorization sai**. Cần record-level tenant ACL, encryption context/AAD và key policy phù hợp; audit phải ghi trusted actor/tenant context và denied hoặc suspicious outcome **không lộ plaintext/DEK**.

### Bài 11 — mTLS private key và DPoP key có được audit như issuer key?

Một OAuth client dùng mTLS cho client authentication và DPoP cho sender-bound access token.

**Đáp án:** Có thể audit key generation/registration/rotation và proof/authentication failures theo profile, nhưng **đó là key của client/token holder**, không phải issuer signing key. Provider audit availability khác nhau theo OS/TPM/browser/HSM. Không vì có `Sign` event DPoP mà kết luận AS đã ký access token.

### Bài 12 — Quyền audit của điều tra viên

SOC cần điều tra issuer-key compromise và yêu cầu raw refresh tokens của mọi user để so sánh.

**Đáp án:** Raw credentials không cần cho forensic correlation và làm tăng nguy cơ replay. Cung cấp sanitized evidence theo case ID, operation ID, client/grant refs và permissions đúng; bảo tồn original logs có RBAC/retention, audit chính hành động export.

### Bài 13 — Audit sink bị lỗi lúc disable key

Operator disable key nghi bị lộ, nhưng audit collector đang unavailable.

**Đáp án:** Thiết kế phải phân biệt **security containment** và yêu cầu durable audit. Có thể cần provider-side key-management audit hoặc guarded emergency workflow; không mặc định bỏ qua disable để attacker tiếp tục dùng key, cũng không tuyên bố hoàn tất nếu không có xác nhận. Ghi incident evidence qua kênh thay thế được phép, kiểm provider final state và reconcile sau recovery.

### Bài 14 — Một event `Sign=SUCCESS` có thể coi là user MFA không?

KMS đã ký một OIDC ID token chứa `sub=user-742`.

**Đáp án:** Không. KMS thấy signer workload và bytes; user MFA/assurance phải được kiểm tại OP authentication flow và các claims `auth_time`/`acr`/`amr` theo OIDC profile. Audit `Sign` không thay chứng cứ authentication event của user.

## 24. Checklist triển khai Audit key operation

- [ ] Có inventory keyRefs, version, algorithm, purpose, owner, environment và consumer dependencies.
- [ ] Phân loại **issuer signing**, **HMAC shared secret**, **KEK/DEK**, **OAuth client key**, **DPoP/mTLS holder key** và public JWKS.
- [ ] Chỉ ghi operation metadata; không ghi raw private/symmetric key, HSM PIN, plaintext DEK, raw access/refresh token hoặc authorization code.
- [ ] Key operation taxonomy bao quát create/import/restore, Sign/Verify, Encrypt/Decrypt, Wrap/Unwrap, secret read, rotate, disable/delete, export attempt, policy change và backup.
- [ ] Management-plane và data-plane events được thu thập theo risk/compliance/provider capabilities đã xác minh.
- [ ] Event có schema version, unique event ID, operation class, phase, outcome, timestamp, trusted actor, keyRef/version, algorithm và source.
- [ ] Có `logical_operation_id`/`attempt_id`/provider request reference để đối chiếu KMS Sign ↔ AS token issuance.
- [ ] Actor/workload identity đến từ trusted IAM/authentication, không tin HTTP `X-User-Id` hoặc body tự khai.
- [ ] KeyRef, issuer, audience, token purpose và policy fields đến từ server trusted configuration/verified grant.
- [ ] Không dùng untrusted JWT `kid`/`jku`/`x5u` làm key source, signer keyRef hoặc metric label tùy ý.
- [ ] Phân biệt `REQUESTED`, `SUCCEEDED`, `DENIED`, `FAILED` và `OUTCOME_UNKNOWN`, đặc biệt với KMS timeout.
- [ ] `Sign=SUCCESS` không tự được coi là `ACCESS_TOKEN_ISSUED` hoặc OAuth grant hợp lệ.
- [ ] AS kiểm client/grant/consent/subject/scope/audience trước khi gọi signer, audit policy decision riêng.
- [ ] RS kiểm public issuer verification key, `iss`, `aud`, `exp`, token purpose, scope, tenant và object-level authorization.
- [ ] Dùng separate RS validation/authorization audit, không nhầm với issuer signing audit.
- [ ] RFC 7662 opaque token introspection và RFC 7009 revocation được audit ở lớp token/grant state riêng.
- [ ] Có provider-side KMS/HSM logs độc lập với AS logger khi provider cho phép; audit coverage được kiểm thực tế.
- [ ] Collector xác thực producer, kiểm schema/size, log injection và data minimization.
- [ ] Audit archive có RBAC/append-only hoặc WORM khi yêu cầu; signer workload không thể xóa/sửa archive.
- [ ] Có protected hash chain/signed checkpoints nếu cần tamper-evidence; key attestation tách issuer signer key.
- [ ] Có heartbeat/lag/dropped-event metrics, queue retry/reconciliation và cảnh báo audit logging bị disable.
- [ ] Duplicate source events được deduplicate mà không xóa các Sign attempts thật có IDs khác nhau.
- [ ] Timestamp từ trusted producer/provider, ghi occurred/observed time, clock skew và time ordering uncertainty.
- [ ] Bảo vệ audit at rest/in transit; retention phân loại theo purpose/privacy/compliance và quyền điều tra.
- [ ] Audit exports có reason/approval/manifest/checksum, original evidence read-only và chain of custody.
- [ ] IAM tách AS Sign, RS Verify, KEK Decrypt, KeyAdmin, AuditAdmin và forensic read-only roles.
- [ ] Mọi `ExportPrivateKey` attempt, wildcard IAM expansion và key disable/delete đều có alert phù hợp.
- [ ] Break-glass quyền ngắn hạn, phê duyệt có audit, không cấp root admin lâu dài.
- [ ] Sign volume và provider-issuance mismatch được baseline theo key purpose/issuer/region/deployment window.
- [ ] Không xem missing audit events là proof không có thao tác khi pipeline không đầy đủ.
- [ ] Rotation audit gồm K2 generated, public JWKS prepublish, signer switch, K1 stop signing/retire và RS canaries.
- [ ] Emergency compromised key được xử lý khác normal rotation; có trust cutoff/reissue/RS verification metrics.
- [ ] KEK/DEK rotate/rewrap audit chứa versions/context và restore evidence, không log plaintext DEKs.
- [ ] Có tests cho actor spoofing, unauthorized Sign/Decrypt/Export, raw-token leak, malformed events và audit tampering.
- [ ] Có tests cho timeout unknown, duplicate/out-of-order, queue loss, disabled logging và provider reconciliation.
- [ ] Có tests cho wrong `iss`/`aud`/scope/tenant/token type, signature confusion, refresh-family revoke và JWKS rotation.
- [ ] Incident runbook phân biệt raw key exfiltration, Sign API misuse, token theft, audit pipeline compromise và availability incident.
- [ ] Audit failure không dẫn đến bỏ JWT signature/issuer/audience checks hoặc mở quyền Decrypt/Sign.
- [ ] Khi không xác thực được key operation authorization hoặc trust của token, hệ thống **fail closed** theo policy.

**Ghi nhớ:** **Audit key operation** là ghi nhận có kiểm chứng các thao tác sử dụng và quản trị khóa theo **actor, operation, key/version, decision, outcome, thời gian và correlation**, đồng thời bảo vệ chính audit pipeline. **KMS Sign thành công không chứng minh OAuth token có grant/claims hợp lệ**; phải nối provider audit với AS issuance và RS authorization. **Immutable logs không tự bảo đảm sự kiện đã được ghi đầy đủ**, nên cần independent sources, completeness monitoring và reconciliation. Mọi thiết kế audit phải tránh tạo ra kho raw keys, JWT/opaque tokens và PII mới. Với nghi ngờ private key bị lộ, ứng cứu có thể cần emergency key cutoff; với bearer token bị lấy, xử lý token/grant revocation là lớp riêng.

## 25. Tài liệu chuẩn và tham khảo

- **NIST SP 800-57 Part 1 — Recommendation for Key Management:** key roles, generation, storage, lifetime, compromise, recovery và auditing considerations.
- **NIST SP 800-57 Part 2 — Best Practices for Key Management Organizations:** key-management policies, role separation, procedures và accountability.
- **NIST SP 800-53 — Security and Privacy Controls for Information Systems and Organizations:** Audit and Accountability (AU), Access Control (AC), Identification and Authentication (IA), System and Communications Protection (SC).
- **NIST SP 800-92 — Guide to Computer Security Log Management:** log generation, collection, storage, analysis, retention và incident use.
- **NIST SP 800-61 — Computer Security Incident Handling Guide:** incident preparation, analysis, containment và evidence handling; dùng phiên bản và revision đang có hiệu lực theo tổ chức.
- **NIST SP 800-131A — Transitioning the Use of Cryptographic Algorithms and Key Lengths:** key-strength/algorithm migration.
- **RFC 7515 — JSON Web Signature (JWS):** signing input, protected headers và signature semantics.
- **RFC 7516 — JSON Web Encryption (JWE):** encryption operation và ciphertext authentication.
- **RFC 7517 — JSON Web Key (JWK):** `kid`, `kty`, public/private key parameters và JWKS representation.
- **RFC 7518 — JSON Web Algorithms (JWA):** `HS256`, `RS256`, `PS256`, `ES256`, key type/algorithm profiles.
- **RFC 7519 — JSON Web Token (JWT):** issuer, audience, expiry và claims model.
- **RFC 8725 — JSON Web Token Best Current Practices:** key/algorithm confusion, issuer trust, token substitution và validation.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** `at+jwt` token purpose, audience, scope và RS validation.
- **RFC 6749 — OAuth 2.0 Authorization Framework:** AS/RS/client roles, grants, scopes, access/refresh token issuance.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** bearer token replay/leakage và resource-server error behavior.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** token and authorization hardening, replay defense và OAuth security.
- **RFC 7662 — OAuth 2.0 Token Introspection:** server-side `active`/metadata checks cho opaque access tokens.
- **RFC 7009 — OAuth 2.0 Token Revocation:** token/grant revocation requests.
- **RFC 7523 — JWT Profile for OAuth 2.0 Client Authentication and Authorization Grants:** `private_key_jwt`-style client assertions và key roles.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** certificate-bound access tokens và client key roles.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** holder proof keys, replay resistance và validation.
- **OpenID Connect Core 1.0 / Discovery 1.0:** ID token, OP JWKS/issuer trust và claims validation.
- **OASIS PKCS #11 — Cryptographic Token Interface:** HSM token objects, operation semantics và key attribute controls.
- **OWASP Logging Cheat Sheet:** what/when to log, integrity, sanitization và sensitive data exclusion.
- **OWASP Key Management Cheat Sheet:** key access, lifecycle, rotation, storage và compromises.
- **OWASP Secrets Management Cheat Sheet:** access auditing, workload identity, vault usage và secret rotation.
- **OWASP JSON Web Token Cheat Sheet:** signing keys, token validation, storage và revocation.
- **OpenTelemetry specification — Logs and Trace Context:** structured log events, severity, trace correlation và context propagation; cần áp privacy/security policy.
- **Java Security Reference / Java Cryptography Architecture / Java KeyStore API:** `KeyStore`, `Signature`, `Mac`, `Cipher` và provider-based operations.
- **Spring Security Reference — OAuth2 Resource Server JWT/Opaque Tokens:** `NimbusJwtDecoder`, opaque introspection, validators và authorization events.
- **Spring Authorization Server Reference:** OAuth2 token issuance, signing key/JWKSource và authorized client/grant management.

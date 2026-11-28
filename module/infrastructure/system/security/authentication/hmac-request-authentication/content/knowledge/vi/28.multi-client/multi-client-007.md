# Thu hồi từng client trong hệ thống HMAC request authentication đa khách hàng

**Thu hồi từng client** (*per-client revocation*) là khả năng **vô hiệu hóa quyền xác thực của một client cụ thể** trong hệ thống có nhiều client cùng gọi API bằng HMAC, trong khi các client khác vẫn hoạt động bình thường. Khi một client bị thu hồi, **mọi HMAC credential/key version thuộc phạm vi thu hồi của client đó phải bị chặn**, kể cả key cũ đang `RETIRING`, key mới `ACTIVE`, key mới `STAGED` và key được cố gắng bổ sung sau khi thu hồi. Chỉ thu hồi một `keyId` không đủ nếu client còn secret khác.

Bài thuộc chương **Multi-client** trong module **SECURITY_AUTHENTICATION_HMAC_REQUEST_AUTHENTICATION**. Module thiết kế xác thực HTTP request bằng **HMAC với shared secret** và canonical request chứa method, URI, signed headers/body; xác minh chữ ký, dùng timestamp/nonce chống replay, xoay vòng khóa, kiểm thử proxy/gateway và tách **authentication** khỏi **authorization**. Trọng tâm bài này là **ranh giới cô lập giữa các client và hiệu lực của quyết định revoke**, không đơn thuần là xóa secret khỏi một map.

> **Bất biến an toàn:** Khi `client=partner-42` bị `REVOKED` trong scope `prod/payments-api`, mọi request tiếp theo mang identity `partner-42` ở scope đó **phải bị từ chối** dù HMAC đúng bằng bất kỳ key version nào. `partner-77` cùng API **không bị ảnh hưởng**. Không được “khôi phục” client đã revoke bằng cách activate key mới, rollback registry snapshot hoặc nhận một key ID khác.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **client-level revocation**, **individual key revocation**, **credential expiry**, **authorization denial** và **disable tạm thời**.
2. Định nghĩa **client scope** chính xác, ví dụ `(environment, audience, clientId)`, và xác định khi nào cần thu hồi ở phạm vi account/global rộng hơn.
3. Thiết kế **client status** độc lập với các key records, để revoke một lần chặn **tất cả old/new keys**.
4. Thực thi revoke bằng **quyền quản trị riêng, transaction/CAS, revision và revocation epoch**, bảo đảm không mất tác dụng khi rotation/caching đồng thời.
5. Giải thích **độ trễ propagation** và race giữa request đang bay với thời điểm revoke; chọn SLA, consistency model và business commit fence phù hợp.
6. Xử lý fail-closed khi registry/KMS/nonce store lỗi; không bypass authentication hoặc tự fallback sang key mới.
7. Viết Java 17 minh họa registry đa client, signer/verifier HMAC-SHA256, timestamp/nonce, revoke từng key vs từng client và concurrency tests.
8. Kiểm thử gateway, audit, cache, idempotency, secret compromise và tách **authentication** khỏi **business authorization**.

## 2. Bài toán: hai client, nhiều key version

Giả sử dịch vụ `payments-api` phục vụ hai đối tác độc lập:

| Client | Audience | Credential | Trạng thái trước khi revoke |
| --- | --- | --- | --- |
| `partner-42` | `payments-api` | `key-2026-11` / secret A1 | `RETIRING` |
| `partner-42` | `payments-api` | `key-2026-12` / secret A2 | `ACTIVE` |
| `partner-77` | `payments-api` | `key-2026-12` / secret B1 | `ACTIVE` |

Tên `key-2026-12` có thể giống nhau giữa hai client, nhưng secret của `partner-42` và `partner-77` phải được quản lý theo **hai locator khác nhau**. Một request mẫu:

~~~http
POST /v1/payments?currency=VND HTTP/1.1
Host: api.example.test
Content-Type: application/json
X-Client-Id: partner-42
X-Key-Id: key-2026-12
X-Timestamp: 1795831200
X-Nonce: 00112233445566778899aabbccddeeff
X-Content-SHA256: <sha256-body-hex>
X-Signature: <base64-standard-padded-hmac-sha256>

{"orderId":"ord-123","amount":50000}
~~~

Các giá trị `<...>` là placeholder. `X-Client-Id` và `X-Key-Id` chỉ là **lookup hints chưa đáng tin** trước khi HMAC hợp lệ.

Nếu đội bảo mật phát hiện secret A1 của `partner-42` bị lộ:

- **Revoke key A1** đủ khi chỉ A1 bị compromise, client vẫn có thể tiếp tục dùng A2 **nếu đánh giá rủi ro cho phép**.
- **Revoke client `partner-42`** cần thiết khi danh tính/thiết bị/đối tác không còn tin cậy hoặc chưa thể biết key nào bị lộ. Khi đó **A1 và A2 đều phải bị từ chối**, kể cả A2 đã được rotate thành công.
- **`partner-77` vẫn được verify** bằng B1 vì nằm ngoài scope thu hồi.

Đây là điểm khác biệt của **per-client revocation** so với chỉ thay secret: **thu hồi một chủ thể** chứ không chỉ **một chuỗi khóa**.

### 2.1. Client-level status tách khỏi key-level status

~~~text
ClientPolicy(env=prod, audience=payments-api, client=partner-42)
    state = REVOKED
    revocationEpoch = 4

KeyRecord(..., partner-42, key-2026-11)
    state = RETIRING

KeyRecord(..., partner-42, key-2026-12)
    state = ACTIVE

Decision = CLIENT_REVOKED  // ưu tiên chặn cả hai key records
~~~

Trạng thái ở key records có thể giữ nguyên trong thời gian audit/reconciliation; **không bắt buộc phải cập nhật đồng loạt hàng nghìn rows khóa** mới có thể chặn client. Bảo đảm an toàn nằm ở **mỗi verification path bắt buộc kiểm tra client-level status**.

### 2.2. Xóa tất cả keys có đủ không?

Xóa key records là một thao tác vệ sinh/lifecycle, **không phải phương án revoke hoàn chỉnh** nếu:

- Gateway cache đang còn key A1/A2 và vẫn chấp nhận request.
- Một rotation controller đang chạy và tạo key A3 **sau khi bạn xóa A1/A2**.
- Replica khác giữ snapshot cũ.
- Key ID được tái sử dụng hoặc re-onboard tự động với cùng client ID.

**Lưu một revocation tombstone có revision/epoch và kiểm tra mọi đường quản trị lẫn verify** giúp tránh những lỗi này. Lưu key material và tombstone theo chính sách retention, giảm exposure, không log secret.

## 3. Phạm vi thu hồi: một client ở một service hay toàn hệ thống?

Trước khi thực hiện revoke, phải trả lời **“client nào, trong trust domain nào?”**.

~~~text
ClientScope = (
    environment,    // prod, staging
    audience,       // payments-api, admin-api
    clientId        // partner-42
)

KeyLocator = (
    ClientScope,
    keyId
)
~~~

| Quy mô quyết định | Ví dụ | Điều cần lưu ý |
| --- | --- | --- |
| Thu hồi **một key version** | `prod/payments-api/partner-42/key-2026-11` | Key A2 của cùng client có thể vẫn active. |
| Thu hồi **client trong một audience** | `prod/payments-api/partner-42` | Chặn mọi key của client trong payments-api; **không tự chặn** admin-api. |
| Thu hồi **toàn account/organization** | `partner-42` ở mọi audience/prod | Phải có **parent account status** hoặc cơ chế policy fan-out được kiểm chứng. |
| Thu hồi **một môi trường** | `partner-42` trên prod nhưng chưa trên staging | Đừng suy diễn rằng trạng thái của staging đại diện prod hoặc ngược lại. |
| Tạm dừng do rate limit | Quota vượt ngưỡng | Không nhầm với **security revocation**; policy/khả năng khôi phục khác. |

Bài dùng **client-level revocation theo `(prod, payments-api, clientId)`**. Nếu yêu cầu “khóa đối tác trên tất cả API”, phải bổ sung kiểm tra **parent/global deny** ở mọi service, hoặc điều phối thu hồi có acknowledgment/consistency SLA rõ. Không gọi thu hồi một audience là “đã khóa toàn hệ thống”.

### 3.1. Một client ID có thể xuất hiện lại ở môi trường khác

`partner-42` trong staging có thể dùng secret test riêng. Không để một request gửi `X-Environment: prod` quyết định scope: environment/audience phải xuất phát từ **server config và route/identity đã xác thực ở trusted ingress**.

### 3.2. Key ID không phải thuộc tính định danh client

Hai client có thể cùng đặt tên `key-2026-12` nhưng có secret khác nhau. Key lookup **bằng mỗi `keyId`** có thể dùng nhầm secret và phá cô lập. Lookup phải theo exact `(env, audience, claimedClientId, keyId)`; client claim chỉ được công nhận sau khi tag HMAC được xác minh.

## 4. Revocation decision nằm ở đâu trong pipeline?

~~~mermaid
flowchart TD
    A["HTTP request tại trusted ingress"] --> B["Strict parse, reject duplicate security headers"]
    B --> C["Server chọn env/audience + claimed client/key ID"]
    C --> D["Lookup scoped ClientPolicy + KeyRecord"]
    D --> E{"Client bị revoke? Key active/scope đúng?"}
    E -->|Deny / unknown| R["Reject authentication, không side effect"]
    E -->|Allowed| F["Canonical method/URI/headers/body HMAC"]
    F --> G{"Full HMAC tag hợp lệ?"}
    G -->|Không| R
    G -->|Có| H["Freshness timestamp + kiểm tra epoch/revocation"]
    H --> I{"Still allowed?"}
    I -->|Không| R
    I -->|Có| J["Atomic nonce claim (client/audience/nonce)"]
    J -->|Replay hoặc store lỗi| R
    J -->|Pass| K["Authenticated identity"]
    K --> L["Authorization + idempotency + business commit fence"]
~~~

**Client status check có thể diễn ra trước HMAC** để tiết kiệm CPU và chặn sớm client đã bị thu hồi. Nhưng khi đó `claimedClientId` vẫn **chưa phải identity đã xác thực**: không cung cấp chi tiết status/khóa tồn tại ra ngoài, không thực thi business và không ghi dấu “authenticated”.

**Cần kiểm tra lại policy gần điểm quyết định có side effect**. Một verifier lấy bản ghi `ACTIVE` rồi tính HMAC vài mili giây, trong khi controller vừa revoke client. Nếu không có cơ chế fencing/consistency, request có thể được chấp nhận **sau khi lệnh revoke đã commit**.

### 4.1. Định nghĩa mốc có hiệu lực

Hệ thống phải xác định SLA:

- **Tại trusted verifier:** request bắt đầu verify **sau thời điểm revoke commit** phải bị reject sau giới hạn propagation đã công bố.
- **Request đang bay:** nếu đã authenticated trước khi revoke, nó có được hoàn tất nghiệp vụ không? Cần chính sách rõ theo độ nhạy.
- **Side effect nhạy cảm:** nếu yêu cầu “không payment nào commit sau revoke”, phải có **business authorization/commit gate** kiểm tra client status/revocation epoch một cách nhất quán và phối hợp với transaction hoặc downstream operations.

Chỉ thêm `if (client.revoked) return 401` ở đầu API **không chứng minh được** tính chất “không commit sau revoke”. Cần nêu rõ linearization point và kiểm thử race.

### 4.2. Không nhầm với `Authorization` header

`X-Client-Id`, `X-Key-Id` hay `Authorization: HMAC ...` đều là input authentication. **Per-client revocation** là quyết định về **client credential validity**. Sau khi HMAC và nonce PASS, backend vẫn phải kiểm tra **authorization** của client đối với tenant/action/resource — một client đang ACTIVE cũng không tự động có quyền chuyển tiền từ mọi tài khoản.

## 5. Trạng thái và bất biến của client

Mô hình tối giản:

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE: Client được onboard/approve
    ACTIVE --> REVOKED: Authorized security revoke
    REVOKED --> [*]: Retention/audit, không phục hồi cùng identity
~~~

Ở đây **`REVOKED` là trạng thái kết thúc cho credential identity cụ thể**. Nếu doanh nghiệp muốn cho đối tác quay lại, quy trình **re-onboard** phải cấp **identity/credential set mới hoặc generation riêng với approval rõ**, không âm thầm đặt `REVOKED → ACTIVE` bằng dữ liệu backup cũ.

### 5.1. Revocation epoch / revision

Một client record:

~~~text
ClientPolicy:
    scope             = (prod, payments-api, partner-42)
    state             = REVOKED
    revision          = 18
    revocationEpoch   = 3
    revokedAt         = 2026-11-28T02:10:00Z
    revokedBy         = security-incident-controller
    reasonCode        = CREDENTIAL_COMPROMISE
~~~

**`revision`** giúp CAS/optimistic concurrency khi nhiều controller cùng cập nhật. **`revocationEpoch`** giúp phát hiện rằng quyền truy cập đã thay đổi trong khi request đang xử lý: verifier có thể mang epoch đã quan sát và backend/commit gate yêu cầu epoch **vẫn hiện hành**.

Giữ epoch/deny tombstone ở nguồn có consistency phù hợp; không dựa vào việc “đợi TTL cache tự hết” nếu security SLA ngắn hơn TTL.

### 5.2. Thu hồi một key khác thu hồi client

~~~text
revokeKey(client=partner-42, kid=key-2026-11):
    key-2026-11 -> REVOKED
    key-2026-12 -> ACTIVE
    client       -> ACTIVE

revokeClient(client=partner-42):
    client       -> REVOKED
    key-2026-11 -> effectively DENIED
    key-2026-12 -> effectively DENIED
    future keys -> PROVISION/ACTIVATE DENIED
~~~

Với quyết định thu hồi toàn client, **không** cố “cứu availability” bằng cách tự chuyển sang secret A2 trong verifier hoặc cấp ID A3 ngoài quy trình.

### 5.3. Authenticated administrative actor

Chỉ principal có quyền quản trị riêng, được xác thực qua IAM/mTLS/SSO+MFA theo bối cảnh, mới có thể revoke client. Không cho client tự khai `X-Is-Admin: true` hoặc biến một public HMAC request thành lifecycle API mà bỏ kiểm tra quyền.

Tách quyền `REVOKE_CLIENT`, `REVOKE_KEY`, `PROVISION_KEY`, `ROTATE_KEY`, `READ_METADATA` và `EXPORT_SECRET`. Quyền revoke không đồng nghĩa quyền đọc/export raw secret; workflow khẩn cấp cần audit và phê duyệt phù hợp.

## 6. Atomic revoke và chặn concurrent key rotation

Sự cố thường xảy ra khi một controller đang rotate key, một controller khác đang revoke client:

~~~mermaid
sequenceDiagram
    participant K as Rotation controller
    participant S as Security controller
    participant D as Authoritative registry
    K->>D: Read client ACTIVE revision=17
    S->>D: Revoke client expectedRevision=17
    D-->>S: COMMIT REVOKED revision=18 epoch=3
    K->>D: Activate new key with stale snapshot rev=17
    D-->>K: REJECT client REVOKED / revision mismatch
    Note over K,D: New key cannot resurrect client
~~~

**Bất biến control plane:** mọi `stage/provision/activate/rotate` cho client phải tham chiếu authoritative client policy **trong cùng transaction/serialization boundary** với `revokeClient`. Nếu chỉ kiểm tra status rồi làm key write độc lập ở storage khác, revoke có thể bị race.

### 6.1. CAS và tombstone

Một operation mô tả:

~~~text
revokeClient(scope, expectedRevision, actor, reason, now):
    authenticate actor and require REVOKE_CLIENT on scope
    BEGIN SERIALIZABLE TRANSACTION
        lock/conditionally update exact ClientPolicy(scope)
        if already REVOKED -> ALREADY_REVOKED, no extra lifecycle effect
        require revision == expectedRevision
        update state=REVOKED, revision++, revocationEpoch++, revokedAt
        append audit/outbox event (same durable transaction)
    COMMIT
    publish invalidate/cache-version event
    confirm verifier/route enforcement according to SLA
~~~

Trả **ALREADY_REVOKED** cho retry sau timeout với cùng scope/state có thể là hành vi idempotent. Nhưng nếu request đầu chưa rõ đã commit hay chưa vì lỗi mạng, controller nên đọc lại **authoritative revision/state** thay vì tự cấp secret mới hoặc ghi đè dữ liệu.

### 6.2. SQL schema minh họa

~~~sql
CREATE TABLE hmac_client_policy (
    environment      text NOT NULL,
    audience         text NOT NULL,
    client_id        text NOT NULL,
    status           text NOT NULL CHECK (status IN ('ACTIVE', 'REVOKED')),
    revision         bigint NOT NULL DEFAULT 1,
    revocation_epoch bigint NOT NULL DEFAULT 0,
    revoked_at       timestamptz,
    PRIMARY KEY (environment, audience, client_id)
);

CREATE TABLE hmac_key_record (
    environment text NOT NULL,
    audience    text NOT NULL,
    client_id   text NOT NULL,
    key_id      text NOT NULL,
    state       text NOT NULL,
    active_from timestamptz NOT NULL,
    expires_at  timestamptz NOT NULL,
    secret_ref  text NOT NULL,  -- Internal KMS/secret-manager reference
    PRIMARY KEY (environment, audience, client_id, key_id),
    FOREIGN KEY (environment, audience, client_id)
        REFERENCES hmac_client_policy(environment, audience, client_id)
);
~~~

Conditional revoke:

~~~sql
UPDATE hmac_client_policy
SET status = 'REVOKED',
    revision = revision + 1,
    revocation_epoch = revocation_epoch + 1,
    revoked_at = now()
WHERE environment = $1 AND audience = $2 AND client_id = $3
  AND status = 'ACTIVE' AND revision = $4
RETURNING revision, revocation_epoch, revoked_at;
~~~

Một dòng được trả nghĩa là **transition đã xảy ra trong transaction**. Không có dòng có thể là **already revoked, wrong revision hoặc not found** — cần đọc có kiểm soát để phân loại, không tự coi là thành công. Nên ghi **audit/outbox trong cùng transaction** và bảo đảm operation tạo/activate key cũng khóa/đọc client policy tương thích, tránh TOCTOU.

**Không** lưu plaintext secret trong bảng audit; `secret_ref` là tham chiếu nội bộ được kiểm soát, không tạo từ đường dẫn/kid do HTTP caller tùy ý cung cấp.

### 6.3. Parent/global deny khi nhiều audience

Nếu yêu cầu revoke client `partner-42` ở **tất cả** dịch vụ, có thể duy trì parent policy:

~~~text
accountStatus(partner-42) = REVOKED
OR clientStatus(prod,payments-api,partner-42) = REVOKED
    -> REJECT
~~~

Tất cả API cần check parent deny với consistency/caching SLA đã định; fan-out đơn thuần tới hàng chục service **không tự bảo đảm** thu hồi nguyên tử toàn hệ thống.

## 7. Cache, key manager và multi-replica revocation

Một registry trung tâm đã cập nhật `REVOKED` chưa chắc tất cả gateway đọc ngay. Nếu `gateway-a` cache `ACTIVE` suốt 30 phút, “revoke đã commit” nhưng gateway vẫn chấp nhận request cũ.

| Thành phần | Rủi ro | Biện pháp |
| --- | --- | --- |
| Client policy positive cache | `ACTIVE` stale sau revoke. | Version/epoch invalidation, TTL giới hạn và revoke barrier. |
| Key cache | Old/new secret còn nằm trong RAM. | Policy gate **độc lập với cache key material**; giảm key exposure, clear theo revoke. |
| Negative cache | Client/key mới không thấy sau onboarding. | TTL ngắn/invalidation; không dùng cache-miss để tự cấp quyền. |
| Gateway nhiều region | Region A đã revoke, B vẫn accept. | Strong consistency theo yêu cầu hoặc routing gate/acknowledged propagation. |
| KMS/secret manager | Có raw key trong pod dù control plane đã revoke. | Không coi raw secret còn lưu là grant; kiểm tra client status, access policy. |
| Client signer | Client vẫn giữ secret đã cấp. | Revoke **server-side acceptance**, không tin client tự xóa key. |
| Replay nonce store | Một region chưa thấy nonce. | Shared atomic store/partition nhất quán và TTL đủ dài. |

**SLA phải thực tế.** Nếu thiết kế dùng eventual consistency, không hứa “ngay lập tức toàn cầu” chỉ vì có một update SQL. Nếu yêu cầu ngừng nhận request **tại thời điểm revoke commit**, verifier phải đọc từ một authority đủ nhất quán hoặc cần cách cô lập/routing đối với các replica chưa đạt revision tối thiểu.

### 7.1. Revocation barrier/fencing

Một ý tưởng là giữ **revocation epoch** trong token/assertion nội bộ:

~~~text
VerifiedAssertion:
    authenticatedClientId = partner-42
    audience              = payments-api
    revocationEpochSeen   = 2
    canonicalDigest       = ...
~~~

Backend trước khi tạo side effect tra authoritative policy:

~~~text
require currentClientState == ACTIVE
require assertion.revocationEpochSeen == currentRevocationEpoch
require authorization(client, tenant, action, resource)
~~~

Nếu controller đã nâng epoch sang 3, assertion epoch 2 phải bị từ chối. **Kiểm tra ở một thời điểm trước commit vẫn có thể race với revoke ngay sau đó**; nếu yêu cầu bảo đảm cứng “không commit sau revoke”, cần **đồng bộ decision/commit với revoke** (ví dụ row lock/transaction trên cùng authority, outbox/downstream fencing hoặc protocol tương đương).

### 7.2. In-flight request policy

| Thời điểm | Tình huống | Cần quyết định |
| --- | --- | --- |
| Request tới **sau** revoke, verifier có state mới | Không được nhận. | Reject authentication. |
| Request đang tính HMAC khi revoke commit | Có thể đã đọc state cũ. | Recheck epoch hoặc authoritative gate trước tiếp tục. |
| Request đã verified và đã commit payment **trước** revoke | Side effect đã xảy ra hợp lệ theo policy tại thời điểm đó. | Không “xóa ngược” giao dịch chỉ bằng revoke. |
| Request verified trước revoke nhưng payment **chưa** commit | Risk tùy hệ thống. | Business commit fence nếu yêu cầu ngăn commit sau revoke. |
| Downstream external provider đang xử lý | Kết quả có thể unknown khi revoke. | Reconciliation/idempotency, không lặp lệnh tùy tiện. |

## 8. Canonical request và signed client identity

Để tránh trộn khóa giữa các client, dùng hợp đồng minh họa **HMAC-MULTI-CLIENT-REVOKE-V1**:

~~~text
HMAC-MULTI-CLIENT-REVOKE-V1
POST
/v1/payments?currency=VND
audience:payments-api
x-client-id:partner-42
x-key-id:key-2026-12
x-timestamp:1795831200
x-nonce:00112233445566778899aabbccddeeff
content-type:application/json
x-content-sha256:<64-hex-lowercase>
~~~

Đây là **contract học tập**, không phải chuẩn HMAC chung. Nối dòng bằng **LF 0x0A**, mã hóa UTF-8, không thêm LF cuối. `X-Signature` **không nằm trong canonical** vì tag được tính từ canonical.

| Field | Vì sao phải được ký? |
| --- | --- |
| Method `POST` | Tránh dùng MAC cho action khác. |
| Raw path/query | Gắn tag với đúng endpoint và các tham số được thực thi. |
| Audience | Tránh cross-service reuse. |
| **Client ID** | Không cho sửa tên client sau ký để mượn key/nonce policy. |
| **Key ID** | Chọn đúng secret, không fallback sang secret khác. |
| Timestamp + nonce | Freshness và replay guard. |
| Content-Type + body digest | Bảo vệ payload representation. |

**Không dùng `X-Client-Id` làm authenticated principal ngay khi parse.** Server chỉ dùng nó để lookup client/key đúng scope, kiểm tra policy, dựng canonical rồi xác minh HMAC full tag. Sau khi HMAC khớp và nonce được claim, identity mới được coi là authenticated; kiểm tra quyền tenant/resource vẫn là bước riêng.

### 8.1. Key lookup sai scope có thể phá cô lập

Sai:

~~~java
// SAI: keyId có thể giống nhau giữa hai client.
// KeyRecord key = allKeys.get(request.keyId());
~~~

Đúng:

~~~java
KeyLocator locator = new KeyLocator(
    serverEnvironment,
    serverAudience,
    request.claimedClientId(),
    request.signedKeyId()
);
KeyRecord key = registry.lookup(locator);
~~~

Nếu `partner-42` bị revoke nhưng `partner-77` dùng cùng text `key-2026-12`, policy chỉ chặn key của `partner-42`. **Không** xóa hoặc disable tất cả keys có cùng text `keyId` trên mọi client.

### 8.2. Key ID rotation không mở lại quyền client

Một lỗi nghiêm trọng:

~~~text
if (keyRecord.active) {
    // verify request without ever checking client status
}
~~~

Client đã revoke vẫn còn `key-2026-12` active; nhánh này chấp nhận request. Logic đúng:

~~~text
clientStatus == ACTIVE
AND keyStatus IN {ACTIVE, RETIRING}
AND key.scope matches client/audience/environment
AND full HMAC valid
AND signed timestamp fresh
AND nonce atomically claimed
~~~

## 9. Timestamp, nonce và idempotency sau revoke

### 9.1. Timestamp không thay thế revoke

Freshness ví dụ:

\[
\operatorname{fresh}(ts,now) \iff now-300\le ts\le now+60
\]

Key state validity dùng **server verification time**. **Client status `REVOKED` phải chặn request ngay cả khi HMAC được ký trước `revokedAt` và `ts` còn fresh**. Không dùng signed timestamp do client chọn để suy ra rằng credential vẫn được cấp quyền ở quá khứ.

### 9.2. Nonce namespace giữa nhiều client

Với HMAC-V1 trong bài:

~~~text
nonceKey = encodeTuple(audience, authenticatedClientId, nonce)
~~~

**Cùng nonce có thể hợp lệ cho hai client khác nhau** nếu mỗi client ký đúng secret riêng, vì namespace khác nhau. Nhưng **cùng client** dùng nonce ấy với old/new key ID phải bị replay guard từ chối trong retention window.

Với `P=300`, `F=60` và margin 10 giây, nonce TTL bảo thủ từ lần claim là **370 giây**, hoặc lưu tới sau `signedTs + P + margin`. Nonce store phải atomic trên các replica và fail closed khi unavailable. Nonce rejection không được dùng làm cơ chế revoke client, vì kẻ có secret vẫn có thể tạo nonce mới.

### 9.3. Revoke và response cache idempotency

Client có thể gửi payment request `K`, server commit rồi response mất. Nếu **sau đó client bị revoke**, retry với cùng `Idempotency-Key=K`, timestamp/nonce mới và chữ ký hợp lệ bằng secret cũ **không được tự nhận cached business response**. Authentication/authorization hiện tại phải được kiểm tra **trước khi đọc/trả response cache nhạy cảm**.

Ngoài ra:

- Revoke không tự “rollback” payment đã commit; cần nghiệp vụ xử lý hoàn tiền/giải quyết tranh chấp riêng.
- Trạng thái `UNKNOWN` của downstream payment vẫn phải reconcile, không tự execute lại.
- Nếu cần duy trì khả năng tra cứu kết quả giao dịch hợp lệ cho khách hàng sau revoke, mở **kênh hỗ trợ/phân quyền khác được xác thực**, không hồi sinh HMAC credential bị thu hồi.

## 10. Java 17: per-client revocation với keyring và HMAC verifier

Ví dụ dưới đây đặt trong **`PerClientRevocationExample.java`**, sử dụng Java 17 standard library. Nó minh họa:

- `ClientScope` tách biệt theo `prod/payments-api/clientId`; `KeyLocator` còn thêm `keyId`.
- Hai key version của `partner-42` và một key của `partner-77` (có thể trùng **text** key ID).
- Thu hồi **một key** chỉ chặn key đó, còn **thu hồi client** chặn mọi key version/future provisioning.
- Revoke có **admin principal, expected revision, monotonic state, epoch**, idempotent retry và không tự re-onboard client đã revoke.
- Verifier tính HMAC-SHA256 từ canonical, strict Base64 full 32 byte, timestamp freshness, nonce atomic claim và **kiểm tra lại client policy** trước khi trả VERIFIED.
- Test stale timestamp, bad tag, wrong client ID, key ID trùng giữa hai client, cross-key nonce replay, outage, 8 request đồng thời và revoke A không tác động B.

**Đây chỉ là mô hình trong một JVM**, không phải code production: `synchronized`/`ConcurrentHashMap` không cung cấp distributed transaction, policy replication hoặc KMS. Kết quả `VERIFIED` của ví dụ **không** chứng minh business side effect chắc chắn không commit sau revoke; cần authoritative business commit gate theo SLA ở phần 7.

### 10.1. Mã nguồn tự chứa

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
import java.util.HashMap;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicBoolean;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

public final class PerClientRevocationExample {
    private static final SecureRandom RNG = new SecureRandom();
    private static final String ENV = "prod";
    private static final String AUD = "payments-api";
    private static final String METHOD = "POST";
    private static final String TARGET = "/v1/payments?currency=VND";
    private static final String TYPE = "application/json";
    private static final String A = "partner-42";
    private static final String B = "partner-77";
    private static final String OLD = "key-2026-11";
    private static final String NEW = "key-2026-12";
    private static final String ADMIN =
        "workload:security-client-revoker-prod";
    private static final long PAST = 300L;
    private static final long FUTURE = 60L;
    private static final long NONCE_MARGIN = 10L;

    enum ClientStatus { ACTIVE, REVOKED }
    enum KeyStatus { ACTIVE, RETIRING, REVOKED }
    enum AdminOutcome {
        REVOKED, ALREADY_REVOKED, ACCESS_DENIED,
        NOT_FOUND, VERSION_CONFLICT, REGISTRY_UNAVAILABLE,
        KEY_REVOKED, CLIENT_REVOKED, APPLIED
    }
    enum VerifyOutcome {
        VERIFIED, MALFORMED, STALE_TIMESTAMP,
        UNKNOWN_CLIENT, CLIENT_REVOKED, UNKNOWN_KEY,
        KEY_INACTIVE, BAD_SIGNATURE, REPLAY,
        REGISTRY_UNAVAILABLE, NONCE_UNAVAILABLE
    }

    record Scope(String env, String audience, String clientId) {}
    record Locator(Scope scope, String keyId) {}
    record ClientInfo(
        Scope scope, ClientStatus status, long revision,
        long revocationEpoch, Instant revokedAt
    ) {}
    record KeyInfo(
        Locator locator, byte[] secret, KeyStatus state,
        Instant activeFrom, Instant expiresAt
    ) {}
    record Snapshot(KeyInfo key, long epoch, VerifyOutcome denial) {}
    record Request(
        String method, String target, String clientId, String keyId,
        String timestamp, String nonce, String contentType,
        String bodyHash, String signature, byte[] body
    ) {}

    // Demo registry with one lock for ALL client/key policy mutations.
    // Production requires an authoritative transactional data store.
    static final class Registry {
        private final Map<Scope, ClientInfo> clients = new HashMap<>();
        private final Map<Locator, KeyInfo> keys = new HashMap<>();
        private boolean available = true;

        synchronized void setAvailable(boolean value) {
            available = value;
        }

        synchronized boolean onboard(Scope scope) {
            if (!available || scope == null ||
                !ENV.equals(scope.env()) ||
                !AUD.equals(scope.audience()) ||
                !validId(scope.clientId()) ||
                clients.containsKey(scope)) {
                return false;
            }
            clients.put(scope, new ClientInfo(
                scope, ClientStatus.ACTIVE, 1L, 0L, null));
            return true;
        }

        synchronized boolean provisionKey(Locator loc, byte[] secret,
                KeyStatus status, Instant from, Instant until) {
            if (!available || loc == null || loc.scope() == null ||
                !validId(loc.keyId()) || secret == null ||
                secret.length < 32 || from == null ||
                until == null || !from.isBefore(until) ||
                status != KeyStatus.ACTIVE ||
                keys.containsKey(loc)) {
                return false;
            }
            ClientInfo c = clients.get(loc.scope());
            if (c == null || c.status() != ClientStatus.ACTIVE) {
                return false; // Revoked client cannot acquire fresh key.
            }
            keys.put(loc, new KeyInfo(
                loc, secret.clone(), status, from, until));
            return true;
        }

        synchronized AdminOutcome revokeKey(
                String actor, Locator loc) {
            if (!ADMIN.equals(actor)) {
                return AdminOutcome.ACCESS_DENIED;
            }
            if (!available) {
                return AdminOutcome.REGISTRY_UNAVAILABLE;
            }
            KeyInfo key = keys.get(loc);
            if (key == null) {
                return AdminOutcome.NOT_FOUND;
            }
            if (key.state() == KeyStatus.REVOKED) {
                return AdminOutcome.KEY_REVOKED;
            }
            keys.put(loc, new KeyInfo(
                key.locator(), key.secret(), KeyStatus.REVOKED,
                key.activeFrom(), key.expiresAt()));
            return AdminOutcome.KEY_REVOKED;
        }

        synchronized AdminOutcome revokeClient(
                String actor, Scope scope,
                long expectedRevision, Instant now) {
            // Production: actor is platform-authenticated; user-supplied
            // strings must never grant administrative authority.
            if (!ADMIN.equals(actor)) {
                return AdminOutcome.ACCESS_DENIED;
            }
            if (!available) {
                return AdminOutcome.REGISTRY_UNAVAILABLE;
            }
            ClientInfo c = clients.get(scope);
            if (c == null) {
                return AdminOutcome.NOT_FOUND;
            }
            if (c.status() == ClientStatus.REVOKED) {
                return AdminOutcome.ALREADY_REVOKED;
            }
            if (c.revision() != expectedRevision) {
                return AdminOutcome.VERSION_CONFLICT;
            }
            clients.put(scope, new ClientInfo(
                scope, ClientStatus.REVOKED, c.revision() + 1,
                c.revocationEpoch() + 1, now));
            return AdminOutcome.REVOKED;
        }

        synchronized Snapshot select(Locator loc, Instant now) {
            if (!available) {
                throw new IllegalStateException("Registry unavailable");
            }
            ClientInfo client = clients.get(loc.scope());
            if (client == null) {
                return new Snapshot(null, 0L,
                    VerifyOutcome.UNKNOWN_CLIENT);
            }
            if (client.status() != ClientStatus.ACTIVE) {
                return new Snapshot(null, client.revocationEpoch(),
                    VerifyOutcome.CLIENT_REVOKED);
            }
            KeyInfo key = keys.get(loc);
            if (key == null) {
                return new Snapshot(null, client.revocationEpoch(),
                    VerifyOutcome.UNKNOWN_KEY);
            }
            if (!(key.state() == KeyStatus.ACTIVE ||
                  key.state() == KeyStatus.RETIRING) ||
                key.secret() == null || key.secret().length < 32 ||
                now.isBefore(key.activeFrom()) ||
                !now.isBefore(key.expiresAt())) {
                return new Snapshot(null, client.revocationEpoch(),
                    VerifyOutcome.KEY_INACTIVE);
            }
            return new Snapshot(key, client.revocationEpoch(), null);
        }

        // A second check closes a subset of verify-vs-revoke races.
        // It is NOT a durable business commit fence by itself.
        synchronized VerifyOutcome stillEligible(
                Locator loc, long seenEpoch, Instant now) {
            if (!available) {
                throw new IllegalStateException("Registry unavailable");
            }
            ClientInfo c = clients.get(loc.scope());
            if (c == null) {
                return VerifyOutcome.UNKNOWN_CLIENT;
            }
            if (c.status() != ClientStatus.ACTIVE ||
                c.revocationEpoch() != seenEpoch) {
                return VerifyOutcome.CLIENT_REVOKED;
            }
            KeyInfo key = keys.get(loc);
            if (key == null || !(key.state() == KeyStatus.ACTIVE ||
                  key.state() == KeyStatus.RETIRING) ||
                now.isBefore(key.activeFrom()) ||
                !now.isBefore(key.expiresAt())) {
                return VerifyOutcome.KEY_INACTIVE;
            }
            return VerifyOutcome.VERIFIED;
        }

        synchronized long revision(Scope scope) {
            ClientInfo c = clients.get(scope);
            return c == null ? -1L : c.revision();
        }
    }

    // Local demonstration only: no cluster-wide atomicity or persistence.
    static final class Nonces {
        private final ConcurrentHashMap<String, Long> expiry =
            new ConcurrentHashMap<>();
        private volatile boolean available = true;

        void setAvailable(boolean value) {
            available = value;
        }

        boolean claim(String audience, String client, String nonce,
                long now, long expiresAt) {
            if (!available) {
                throw new IllegalStateException("Nonce store unavailable");
            }
            if (expiresAt <= now) {
                return false;
            }
            String k = audience.length() + ":" + audience
                + client.length() + ":" + client
                + nonce.length() + ":" + nonce;
            AtomicBoolean inserted = new AtomicBoolean(false);
            expiry.compute(k, (key, previous) -> {
                if (previous != null && previous > now) {
                    return previous;
                }
                inserted.set(true);
                return expiresAt;
            });
            return inserted.get();
        }
    }

    static boolean validId(String s) {
        return s != null && s.matches("[a-z0-9][a-z0-9-]{0,39}");
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

    static String sha256Hex(byte[] data)
            throws GeneralSecurityException {
        return HexFormat.of().formatHex(
            MessageDigest.getInstance("SHA-256").digest(data));
    }

    static byte[] hmac(byte[] secret, String message)
            throws GeneralSecurityException {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret, "HmacSHA256"));
        return mac.doFinal(
            message.getBytes(StandardCharsets.UTF_8));
    }

    static Long parseTime(String value) {
        if (value == null ||
            !value.matches("[1-9][0-9]{0,18}")) {
            return null;
        }
        try {
            return Long.parseLong(value);
        } catch (NumberFormatException overflow) {
            return null;
        }
    }

    static boolean fresh(long signed, long now) {
        try {
            return signed >= Math.subtractExact(now, PAST) &&
                signed <= Math.addExact(now, FUTURE);
        } catch (ArithmeticException overflow) {
            return false;
        }
    }

    static String canonical(Request req, String actualBodyHash) {
        if (req == null ||
            !METHOD.equals(req.method()) ||
            !TARGET.equals(req.target()) ||
            !TYPE.equals(req.contentType()) ||
            !validId(req.clientId()) ||
            !validId(req.keyId()) ||
            parseTime(req.timestamp()) == null ||
            req.nonce() == null ||
            !req.nonce().matches("[0-9a-f]{32}") ||
            actualBodyHash == null ||
            !actualBodyHash.matches("[0-9a-f]{64}")) {
            throw new IllegalArgumentException(
                "Invalid HMAC-MULTI-CLIENT-REVOKE-V1 fields");
        }
        return String.join("\n",
            "HMAC-MULTI-CLIENT-REVOKE-V1",
            req.method(), req.target(),
            "audience:" + AUD,
            "x-client-id:" + req.clientId(),
            "x-key-id:" + req.keyId(),
            "x-timestamp:" + req.timestamp(),
            "x-nonce:" + req.nonce(),
            "content-type:" + req.contentType(),
            "x-content-sha256:" + actualBodyHash);
    }

    static byte[] decodeTag(String text) {
        if (text == null ||
            !text.matches("[A-Za-z0-9+/]{43}=")) {
            return null;
        }
        try {
            byte[] tag = Base64.getDecoder().decode(text);
            if (tag.length != 32 ||
                !Base64.getEncoder().encodeToString(tag)
                    .equals(text)) {
                return null;
            }
            return tag;
        } catch (IllegalArgumentException invalid) {
            return null;
        }
    }

    static Request sign(String client, String kid, byte[] key,
            Clock clock, String nonce, byte[] body)
            throws GeneralSecurityException {
        String timestamp =
            Long.toString(clock.instant().getEpochSecond());
        String digest = sha256Hex(body);
        Request unsigned = new Request(
            METHOD, TARGET, client, kid, timestamp, nonce,
            TYPE, digest, "", body.clone());
        String signature = Base64.getEncoder().encodeToString(
            hmac(key, canonical(unsigned, digest)));
        return new Request(
            METHOD, TARGET, client, kid, timestamp, nonce,
            TYPE, digest, signature, body.clone());
    }

    static VerifyOutcome verify(Request req, Registry registry,
            Nonces nonces, Clock clock)
            throws GeneralSecurityException {
        if (req == null || req.body() == null ||
            req.body().length > 65536 ||
            !validId(req.clientId()) || !validId(req.keyId())) {
            return VerifyOutcome.MALFORMED;
        }
        Long ts = parseTime(req.timestamp());
        byte[] supplied = decodeTag(req.signature());
        if (ts == null || supplied == null) {
            return VerifyOutcome.MALFORMED;
        }
        Instant nowInstant = clock.instant();
        long now = nowInstant.getEpochSecond();
        if (!fresh(ts, now)) {
            return VerifyOutcome.STALE_TIMESTAMP;
        }

        final String message;
        try {
            String bodyHash = sha256Hex(req.body());
            if (!bodyHash.equals(req.bodyHash())) {
                return VerifyOutcome.BAD_SIGNATURE;
            }
            message = canonical(req, bodyHash);
        } catch (IllegalArgumentException malformed) {
            return VerifyOutcome.MALFORMED;
        }

        Scope scope = new Scope(ENV, AUD, req.clientId());
        Locator locator = new Locator(scope, req.keyId());
        final Snapshot snapshot;
        try {
            snapshot = registry.select(locator, nowInstant);
        } catch (IllegalStateException unavailable) {
            return VerifyOutcome.REGISTRY_UNAVAILABLE;
        }
        if (snapshot.denial() != null) {
            return snapshot.denial();
        }

        byte[] expected = hmac(snapshot.key().secret(), message);
        if (expected.length != 32 ||
            !MessageDigest.isEqual(expected, supplied)) {
            return VerifyOutcome.BAD_SIGNATURE;
        }

        // Re-check current client/key state after HMAC. Production
        // business transaction still needs its own commit fence.
        try {
            VerifyOutcome gate = registry.stillEligible(
                locator, snapshot.epoch(), clock.instant());
            if (gate != VerifyOutcome.VERIFIED) {
                return gate;
            }
        } catch (IllegalStateException unavailable) {
            return VerifyOutcome.REGISTRY_UNAVAILABLE;
        }

        final long expiresAt;
        try {
            expiresAt = Math.addExact(ts,
                Math.addExact(PAST, NONCE_MARGIN));
        } catch (ArithmeticException overflow) {
            return VerifyOutcome.STALE_TIMESTAMP;
        }
        try {
            return nonces.claim(AUD, req.clientId(), req.nonce(),
                    now, expiresAt)
                ? VerifyOutcome.VERIFIED : VerifyOutcome.REPLAY;
        } catch (IllegalStateException unavailable) {
            return VerifyOutcome.NONCE_UNAVAILABLE;
        }
    }

    static Request withClientId(Request req, String changed) {
        return new Request(req.method(), req.target(), changed,
            req.keyId(), req.timestamp(), req.nonce(),
            req.contentType(), req.bodyHash(),
            req.signature(), req.body());
    }

    static Request withBody(Request req, byte[] changed) {
        return new Request(req.method(), req.target(), req.clientId(),
            req.keyId(), req.timestamp(), req.nonce(),
            req.contentType(), req.bodyHash(),
            req.signature(), changed);
    }

    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    static void rfc4231Vector() throws Exception {
        byte[] key = new byte[20];
        Arrays.fill(key, (byte) 0x0b);
        String expected =
            "b0344c61d8db38535ca8afceaf0bf12" +
            "b881dc200c9833da726e9376c2e32cff7";
        check(expected.equals(
            HexFormat.of().formatHex(hmac(key, "Hi There"))),
            "RFC 4231 HMAC-SHA256 known-answer vector");
    }

    public static void main(String[] args) throws Exception {
        rfc4231Vector();
        Instant t0 = Instant.parse("2026-11-28T02:00:00Z");
        Clock clock = Clock.fixed(t0, ZoneOffset.UTC);
        Instant from = t0.minusSeconds(3600);
        Instant until = t0.plusSeconds(86400);
        byte[] aOldSecret = secret();
        byte[] aNewSecret = secret();
        byte[] bSecret = secret();
        byte[] body =
            "{\"orderId\":\"ord-123\",\"amount\":50000}"
                .getBytes(StandardCharsets.UTF_8);
        Scope a = new Scope(ENV, AUD, A);
        Scope b = new Scope(ENV, AUD, B);
        Locator aOld = new Locator(a, OLD);
        Locator aNew = new Locator(a, NEW);
        Locator bNew = new Locator(b, NEW);  // SAME key ID text.
        Registry registry = new Registry();
        check(registry.onboard(a) && registry.onboard(b),
            "Two independent clients onboarded");
        check(registry.provisionKey(aOld, aOldSecret,
                KeyStatus.ACTIVE, from, until),
            "A old key provisioned");
        check(registry.provisionKey(aNew, aNewSecret,
                KeyStatus.ACTIVE, from, until),
            "A new key provisioned");
        check(registry.provisionKey(bNew, bSecret,
                KeyStatus.ACTIVE, from, until),
            "B key provisioned with reused ID text");

        // Two versions of A and B verify independently.
        Request aOldRequest = sign(
            A, OLD, aOldSecret, clock, nonce(), body);
        Request aNewRequest = sign(
            A, NEW, aNewSecret, clock, nonce(), body);
        Request bRequest = sign(
            B, NEW, bSecret, clock, nonce(), body);
        Nonces store = new Nonces();
        check(verify(aOldRequest, registry, store, clock)
                == VerifyOutcome.VERIFIED, "A old verified");
        check(verify(aNewRequest, registry, store, clock)
                == VerifyOutcome.VERIFIED, "A new verified");
        check(verify(bRequest, registry, store, clock)
                == VerifyOutcome.VERIFIED, "B verified");

        HttpRequest sample = HttpRequest.newBuilder(
                URI.create("https://api.example.test" + TARGET))
            .header("Content-Type", aNewRequest.contentType())
            .header("X-Client-Id", aNewRequest.clientId())
            .header("X-Key-Id", aNewRequest.keyId())
            .header("X-Timestamp", aNewRequest.timestamp())
            .header("X-Nonce", aNewRequest.nonce())
            .header("X-Content-SHA256", aNewRequest.bodyHash())
            .header("X-Signature", aNewRequest.signature())
            .POST(HttpRequest.BodyPublishers.ofByteArray(
                aNewRequest.body()))
            .build(); // Demonstrate wire headers only; do not send.
        check(METHOD.equals(sample.method()), "HTTP method");

        // Same kid text on client B does NOT let A borrow B's secret.
        Request wrongClient =
            withClientId(aNewRequest, B);
        check(verify(wrongClient, registry,
                new Nonces(), clock) == VerifyOutcome.BAD_SIGNATURE,
            "Signed client ID cannot be rewritten to another client");
        Request aWithBSecret = sign(
            A, NEW, bSecret, clock, nonce(), body);
        check(verify(aWithBSecret, registry,
                new Nonces(), clock) == VerifyOutcome.BAD_SIGNATURE,
            "Key ID text alone never selects other client's secret");

        // Nonce is separated by client, but SHARED across key versions.
        String reused = nonce();
        Nonces cross = new Nonces();
        Request sameNonceAOld = sign(
            A, OLD, aOldSecret, clock, reused, body);
        Request sameNonceANew = sign(
            A, NEW, aNewSecret, clock, reused, body);
        Request sameNonceB = sign(
            B, NEW, bSecret, clock, reused, body);
        check(verify(sameNonceAOld, registry, cross, clock)
                == VerifyOutcome.VERIFIED, "First A nonce claimed");
        check(verify(sameNonceANew, registry, cross, clock)
                == VerifyOutcome.REPLAY,
            "A cannot reuse nonce across key rotation");
        check(verify(sameNonceB, registry, cross, clock)
                == VerifyOutcome.VERIFIED,
            "B same nonce is separate client scope");

        // Bad body/MAC never consumes a genuine nonce.
        Request freshA = sign(
            A, NEW, aNewSecret, clock, nonce(), body);
        byte[] tamperedBody = body.clone();
        tamperedBody[0] ^= 1;
        Nonces bodyStore = new Nonces();
        check(verify(withBody(freshA, tamperedBody), registry,
                bodyStore, clock) == VerifyOutcome.BAD_SIGNATURE,
            "Body tampering rejected");
        check(verify(freshA, registry, bodyStore, clock)
                == VerifyOutcome.VERIFIED,
            "Bad MAC did not burn a nonce");

        // Revoke ONLY A old key. A new and B still pass.
        check(registry.revokeKey(ADMIN, aOld)
                == AdminOutcome.KEY_REVOKED, "Old A key revoked");
        check(verify(aOldRequest, registry,
                new Nonces(), clock) == VerifyOutcome.KEY_INACTIVE,
            "Single key revoke denies A old");
        check(verify(aNewRequest, registry,
                new Nonces(), clock) == VerifyOutcome.VERIFIED,
            "Single key revoke does not deny A new");
        check(verify(bRequest, registry,
                new Nonces(), clock) == VerifyOutcome.VERIFIED,
            "Single key revoke does not deny B");

        // Unauthenticated/public client cannot invoke admin revoke.
        check(registry.revokeClient(
                "workload:external-client", a, 1L, t0)
                == AdminOutcome.ACCESS_DENIED,
            "Revoke requires independent admin identity");
        check(registry.revokeClient(ADMIN, a, 99L, t0)
                == AdminOutcome.VERSION_CONFLICT,
            "CAS revision prevents stale administrative update");

        // Revoke A CLIENT: all A versions must now fail, even A new.
        check(registry.revokeClient(ADMIN, a, 1L, t0)
                == AdminOutcome.REVOKED,
            "Client A security revocation committed");
        check(registry.revision(a) == 2L,
            "Client revision increments");
        check(registry.revokeClient(ADMIN, a, 1L, t0)
                == AdminOutcome.ALREADY_REVOKED,
            "Idempotent repeat revoke, no resurrection");
        check(!registry.onboard(a),
            "Cannot re-onboard revoked identity via onboarding path");
        check(!registry.provisionKey(
                new Locator(a, "key-2027-01"), secret(),
                KeyStatus.ACTIVE, from, until),
            "Rotation cannot provision new keys for revoked client");
        Request aAgain = sign(
            A, NEW, aNewSecret, clock, nonce(), body);
        check(verify(aAgain, registry,
                new Nonces(), clock) == VerifyOutcome.CLIENT_REVOKED,
            "Revoked A client denied even with valid new-key HMAC");
        check(verify(aOldRequest, registry,
                new Nonces(), clock) == VerifyOutcome.CLIENT_REVOKED,
            "Revoked A client status overrides individual key status");

        // Per-client isolation: B must stay fully operational.
        Request bAfter = sign(
            B, NEW, bSecret, clock, nonce(), body);
        check(verify(bAfter, registry,
                new Nonces(), clock) == VerifyOutcome.VERIFIED,
            "Revoke A must not affect client B");

        // Eight concurrent attempts after A revoked: A denied,
        // B authorized independently. No shared global revoke flag.
        ExecutorService pool = Executors.newFixedThreadPool(8);
        CountDownLatch ready = new CountDownLatch(8);
        CountDownLatch go = new CountDownLatch(1);
        List<Future<VerifyOutcome>> results = new ArrayList<>();
        try {
            for (int i = 0; i < 8; i++) {
                final boolean fromA = (i % 2 == 0);
                Request request = fromA
                    ? sign(A, NEW, aNewSecret, clock, nonce(), body)
                    : sign(B, NEW, bSecret, clock, nonce(), body);
                results.add(pool.submit(
                    (Callable<VerifyOutcome>) () -> {
                        ready.countDown();
                        go.await();
                        return verify(request, registry,
                            new Nonces(), clock);
                    }));
            }
            ready.await();
            go.countDown();
            for (int i = 0; i < results.size(); i++) {
                VerifyOutcome got = results.get(i).get();
                VerifyOutcome want = (i % 2 == 0)
                    ? VerifyOutcome.CLIENT_REVOKED
                    : VerifyOutcome.VERIFIED;
                check(got == want,
                    "Concurrent per-client revocation isolation " + i);
            }
        } finally {
            go.countDown();
            pool.shutdownNow();
        }

        // A registry/KMS outage must NOT bypass revocation checks.
        registry.setAvailable(false);
        check(verify(bAfter, registry, new Nonces(), clock)
                == VerifyOutcome.REGISTRY_UNAVAILABLE,
            "Registry outage must fail closed");
        registry.setAvailable(true);
        Nonces down = new Nonces();
        down.setAvailable(false);
        check(verify(bAfter, registry, down, clock)
                == VerifyOutcome.NONCE_UNAVAILABLE,
            "Nonce store outage must fail closed");

        // Freshness still matters for an ACTIVE client B.
        Request staleB = sign(B, NEW, bSecret,
            Clock.offset(clock, Duration.ofSeconds(-301)),
            nonce(), body);
        check(verify(staleB, registry, new Nonces(), clock)
                == VerifyOutcome.STALE_TIMESTAMP,
            "Active client does not bypass freshness");

        System.out.println(
            "PASS: per-client revoke, multi-key isolation, 8-way test");
    }
}
~~~

### 10.2. Vì sao code kiểm tra client status trước key status?

~~~java
ClientInfo client = clients.get(loc.scope());
if (client.status() != ClientStatus.ACTIVE) {
    return new Snapshot(
        null, client.revocationEpoch(),
        VerifyOutcome.CLIENT_REVOKED);
}
KeyInfo key = keys.get(loc);
~~~

Đây là quyết định nội bộ. Khi client đã revoke, **mọi key đều trở nên vô hiệu cho authentication** mà không cần vòng lặp update từng key record. Không trả nội bộ `CLIENT_REVOKED` thành thông điệp public tiết lộ client nào đã bị thu hồi.

### 10.3. Kiểm tra lại policy sau HMAC

~~~java
VerifyOutcome gate = registry.stillEligible(
    locator, snapshot.epoch(), clock.instant());
if (gate != VerifyOutcome.VERIFIED) {
    return gate;
}
~~~

Nếu revoke xảy ra trong lúc verifier tính HMAC, `stillEligible` phát hiện epoch/state thay đổi trước nonce claim. **Tuy nhiên có thể revoke xảy ra ngay sau dòng trên**, trước khi business commit. Để bảo đảm “không commit sau revoke” cần **commit-time fence có cùng thứ tự nhất quán** với operation revoke; mẫu Java này không cung cấp đảm bảo ấy.

### 10.4. Độ tin cậy của demo và giới hạn production

- `Registry` dùng `synchronized` để serialization trong **một JVM**; không có distributed consensus, SQL transaction thật, policy cache invalidation hay persistent audit.
- `KeyInfo.secret` trong demo giữ raw key bytes; production nên dùng secret manager/KMS/HSM, workload identity/least privilege, tránh copy/log/heap dump.
- `Nonces` dùng `ConcurrentHashMap.compute` trong một process. Production cần store atomic **dùng chung giữa các gateway/region** và TTL đủ với freshness policy.
- `ClientStatus.REVOKED` được giữ làm tombstone; production cần quyết định retention, delete/re-onboard policy, global account deny và quyền admin revoke.
- `Request` giả định các header đã được parse rõ, chưa detect duplicate security header, oversized HTTP message, URI normalization differences. Trusted ingress phải xử lý.
- Chương trình không thực thi payment và không minh họa distributed business commit fence. Integration tests phải đánh giá **in-flight requests, downstream idempotency, external provider reconciliation**.
- Phân loại `VerifyOutcome` là **nội bộ**; HTTP response public nên dùng lỗi chung để giảm enumeration và dữ liệu nhạy cảm.

## 11. Proxy/gateway, nonce store và multi-region

~~~mermaid
sequenceDiagram
    participant C as Client partner-42
    participant P as Untrusted proxy
    participant G as Trusted gateway
    participant R as Client+Key authority
    participant N as Shared nonce store
    participant B as Payment backend
    C->>P: Signed request with clientId, kid, ts, nonce
    P->>G: Forward / retry / possible rewrite
    G->>G: Strict parse, reject duplicate/security ambiguity
    G->>R: Lookup client status + scoped key
    alt Client REVOKED
        R-->>G: DENY independently of key version
        G-->>C: Generic authentication failure
    else Client ACTIVE + key permitted
        R-->>G: Snapshot + policy epoch
        G->>G: Verify canonical HMAC, freshness, epoch
        G->>N: Atomic nonce claim after HMAC
        alt New nonce
            N-->>G: CREATED
            G->>B: Verified identity + epoch/signed semantics
            B->>B: Authorization + idempotency + commit fence
        else Replay or unavailable
            N-->>G: Deny / unavailable
            G-->>C: Reject, no side effect
        end
    end
~~~

| Tình huống | Nguy cơ | Cách phòng vệ |
| --- | --- | --- |
| Gateway A đã thấy REVOKED, B vẫn cache ACTIVE | Client vẫn gọi B được. | Revoke propagation SLA, version barrier, fail-closed routing. |
| HTTP/1.1 → HTTP/2 | Header names lowercase/URI semantics thay đổi. | Parser case-insensitive names, ký đúng raw method/target/body. |
| Duplicate `X-Client-Id`/`X-Key-Id` | Gateway/backend chọn giá trị khác nhau. | Reject duplicate security fields trước khi gộp. |
| Proxy thêm `X-Verified: true` | Backend tưởng client đã authenticate. | Strip spoofed headers, authenticated internal channel/mTLS. |
| Backend trực tiếp public | Bỏ qua gateway HMAC/revoke. | Network isolation và một authoritative authentication boundary. |
| Gateway/client nonce store tách theo key ID | Reuse nonce qua rotation. | Shared namespace theo client/audience, không key ID. |
| Client gửi key ID của client khác | Cross-client key borrowing. | Exact scoped lookup và ký client/key ID trong canonical. |
| Registry outage | Không thể xác nhận client có revoke không. | Fail closed, không dùng default secret hoặc status=ACTIVE giả. |
| Cache replay response sau revoke | Trả dữ liệu nhạy cảm cho client không còn quyền. | Authn/authz và revocation check trước idempotency lookup. |
| Secret vẫn còn trong RAM sau revoke | HMAC có thể được tính dù policy đã deny. | Không dùng secret availability làm auth grant; revoke gate độc lập. |

### 11.1. Revocation và gateway retry

Proxy đôi khi retry một request HTTP nguyên vẹn sau lỗi kết nối. Khi giữ nonce cũ, nó phải bị atomic replay guard từ chối nếu request đầu đã claim. Sau khi client bị revoke, cả retry **nonce cũ** lẫn retry **nonce mới với HMAC đúng** đều không được đi qua client status gate. Một retry không thể “xuyên qua” revocation bằng cách chuyển `kid`.

### 11.2. Không để client B bị vạ lây

Khi revoke A, không xóa cache theo `keyId` dùng chung, không xóa **toàn bộ nonce store**, không restart cluster nếu có lựa chọn tốt hơn và không thiết lập một global `denyAllClients` chỉ để chặn A. Nếu hệ thống có nghi vấn lộ **shared global secret** dùng chung nhiều client, phạm vi sự cố có thể lớn hơn: phải thừa nhận blast radius thật và revoke/rekey những client chịu ảnh hưởng, chứ không giả vờ keys đã cô lập.

## 12. HTTP response, audit và monitoring

### 12.1. Phản hồi public không thành oracle

Đừng trả response như:

~~~json
{
  "error": "partner-42 was revoked at 2026-11-28T02:10:00Z",
  "remainingActiveKeys": ["key-2026-12"]
}
~~~

Đối với caller chưa được xác thực, các lỗi `unknown client`, `revoked client`, `unknown key` và `bad signature` có thể cùng được ánh xạ thành:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: HMAC-V1 realm="payments-api"
Content-Type: application/json
Cache-Control: no-store

{"error":"INVALID_AUTHENTICATION"}
~~~

`HMAC-V1` là scheme minh họa. Với lỗi registry/nonce store unavailable, phản hồi 503 chung có thể phù hợp, nhưng **không** nhận request. **401** là kết quả authentication; nếu HMAC hợp lệ mà client ACTIVE nhưng thiếu quyền nghiệp vụ, **403 Forbidden** thường phù hợp hơn.

### 12.2. Audit event an toàn

~~~json
{
  "event": "hmac_client_revoked",
  "environment": "prod",
  "audience": "payments-api",
  "clientScope": "partner-42",
  "oldState": "ACTIVE",
  "newState": "REVOKED",
  "oldRevision": 17,
  "newRevision": 18,
  "newRevocationEpoch": 3,
  "actor": "workload:security-client-revoker-prod",
  "reasonCode": "CREDENTIAL_COMPROMISE",
  "requestId": "req-opaque-123"
}
~~~

Audit record cần **actor đã xác thực, scope, reason, revision/epoch, timestamp, kết quả và approval** (nếu quy trình yêu cầu), không ghi raw shared secret, full signature, HTTP Authorization hay body chứa PII. Một raw client ID do attacker gửi có thể là dữ liệu cardinality cao; hạn chế dùng làm label metrics.

### 12.3. Những metric hữu ích

| Metric | Ý nghĩa |
| --- | --- |
| Revoked-client verification attempts | Client/attacker vẫn sử dụng credential đã thu hồi. |
| Per-client revoked/active counts | Theo dõi scope ảnh hưởng, tránh xóa nhầm client B. |
| Revocation propagation lag p95/p99 | Một replica còn ACTIVE bao lâu sau khi control plane commit? |
| Client policy epoch drift | Gateway/backend đang dùng revision nào? |
| Unauthorized revoke attempts | Client hoặc workload không được cấp quyền cố đổi lifecycle. |
| Key provisioning attempts after revoke | Rotation/onboarding có bỏ qua client-level tombstone không? |
| HMAC failure/unknown key/replay | Phân biệt sai canonical, key ID, nonce hoặc tấn công. |
| Secret manager/nonce store outages | Xác minh có bị fail closed hay không. |
| In-flight operations at revoke time | Rủi ro commit sau revoke/nhu cầu reconciliation. |
| Post-revocation business side effects | Sự cố nghiêm trọng cần điều tra nếu SLA cấm commit sau revoke. |

Audit/telemetry phải được bảo vệ quyền truy cập và retention; không phát tán raw key IDs hoặc metadata khách hàng vào dashboard công khai.

## 13. Ma trận kiểm thử thu hồi từng client

Với hệ thống phân tán thật, bổ sung integration tests cho **DB transaction/CAS, multi-region cache, gateway failover, client policy epoch và business commit gate**. Java example chỉ kiểm thử trong một JVM.

| Case | Thiết lập và thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Hai client còn active | A và B ký bằng secret riêng | Cả hai verify được khi policy hợp lệ. |
| Một client có old/new key | A có A1 `RETIRING` và A2 `ACTIVE` | Cả hai có thể verify trước revoke. |
| Hai client cùng `keyId` text | A2 và B1 có cùng ID nhưng secret khác | Lookup theo client scope, không dùng nhầm secret. |
| Revoke **một key** của A | Chỉ A1 revoked | A1 reject; A2 và B1 vẫn accept. |
| **Revoke client A** | A status `ACTIVE→REVOKED` | A1/A2 đều reject, B1 vẫn accept. |
| Revoke A không ảnh hưởng B | Gửi request mới của B | Authentication PASS, nonce riêng. |
| Revoke A rồi rotation A3 | Controller cố provision A3 | Deny; client-level tombstone vẫn hiệu lực. |
| Re-onboard A sau revoke | Dùng lại cùng scope/client ID | Deny; cần quy trình/generation mới có kiểm soát. |
| Revoke lặp sau ACK mất | Cùng scope, state đã revoked | Idempotent `ALREADY_REVOKED`, không reset epoch. |
| Stale admin revision | Expected revision không khớp | CAS conflict, không ghi đè. |
| Unauthorized actor | Client tự gọi revoke API | Access denied, không thay state. |
| Unknown client | Claimed ID không có record | Reject, không auto-register/default secret. |
| Wrong scope | Key payments dùng ở admin API | Reject theo audience server-side. |
| Signed client ID bị sửa | Đổi A thành B nhưng giữ tag của A | Fail HMAC hoặc wrong scope; không dùng B secret mù quáng. |
| Body tamper | Sửa request JSON sau ký | Bad signature, không claim nonce. |
| Known key bad MAC | Tag full 32 byte nhưng sai byte | Reject, không thử secret của client khác. |
| Fresh timestamp khi client revoked | A ký nonce/timestamp mới | **REVOKED**, không được bypass. |
| Signed timestamp trước revoke | A gửi muộn với HMAC đúng | Reject theo **server current policy**, không backdate. |
| Nonce trùng giữa A old/new | Same A + same nonce, hai key versions | Lần thứ hai bị replay trong window. |
| Nonce giống nhau giữa A và B | Cùng nonce text, hai clients khác | Có thể pass riêng khi HMAC đúng; namespace độc lập. |
| Nonce TTL quá ngắn | Xóa trước freshness cutoff | Test phải phát hiện replay gap. |
| 8 request đồng thời sau revoke | 4 A + 4 B requests | A đều reject, B đều pass khi store/policy nhất quán. |
| Revoke giữa HMAC và claim | Concurrency race | Epoch recheck phát hiện nếu revoke đã commit trước recheck. |
| Revoke sau recheck trước payment commit | Race muộn | Chỉ commit-time authoritative fence mới đáp ứng policy mạnh. |
| Registry outage | Không đọc được client status | Fail closed, không coi cached key là đủ. |
| Nonce store outage | Không claim được nonce | Fail closed, không cho side effect. |
| Gateway stale ACTIVE | Replica chưa nhận epoch mới | Test revoke SLA/version barrier/traffic gating. |
| Global revoke vs audience revoke | A còn ở admin-api | Theo contract; nếu muốn global cần parent deny. |
| Idempotency cache sau revoke | A retry cùng K và nonce mới | Reject authn trước đọc/trả response cache. |
| Business authz sau verification | B active nhưng không có quyền tenant | Authentication PASS, authorization DENY. |
| Old secret bị compromise | Attacker tạo HMAC mới của A | A revoked nên bị reject dù tag hợp lệ. |

### Câu hỏi tự kiểm tra

1. Vì sao revoke `key-2026-11` của `partner-42` chưa tương đương revoke **toàn bộ client**?
2. Tại sao client-level `REVOKED` nên được lưu độc lập với trạng thái A1/A2 để tránh lỗi khi rotation?
3. Nếu `partner-42` và `partner-77` cùng dùng chuỗi `key-2026-12`, key lookup/revoke phải phân biệt như thế nào?
4. Vì sao `X-Client-Id` là lookup hint chứ chưa phải identity đã xác thực trước HMAC?
5. `revision` và `revocationEpoch` giải quyết hai loại vấn đề khác nhau gì?
6. Một request đã verify trước revoke nhưng payment chưa commit: có thể tiếp tục không, và cần cơ chế nào để đảm bảo “không commit sau revoke”?
7. Nếu một gateway cache client ACTIVE trong 30 phút, tuyên bố “revoke tức thì” có đúng không?
8. Tại sao retry với timestamp/nonce mới và HMAC vẫn hợp lệ không được qua client-level revocation?
9. Vì sao response cache idempotency không được trả body cho client A sau khi bị revoke?
10. Khi secret manager outage, có được dùng secret cache và bỏ qua client status vì cần availability không?

## 14. Checklist thiết kế và triển khai

- [ ] Chốt phạm vi revoke: **một key**, **client trong audience/environment**, hay **toàn account**; ghi thành API/security contract, không suy diễn quá phạm vi.
- [ ] Tạo `ClientPolicy` độc lập theo `(environment,audience,clientId)` cùng `status, revision, epoch, revokedAt`; lưu tombstone đủ thời hạn.
- [ ] Key records nằm theo `(scope,keyId)`; không tra cứu/xóa mọi key chỉ vì trùng text `kid` giữa các client.
- [ ] Verification path luôn check **client-level ACTIVE** và **key-level ACTIVE/RETIRING, validity, scope**, không chỉ key material tồn tại.
- [ ] Revoke bằng principal có quyền `REVOKE_CLIENT` riêng, được xác thực qua trusted IAM/mTLS/SSO; không cho client tự bật/tắt lifecycle bằng header.
- [ ] Commit revoke với atomic CAS/transaction, audit/outbox cùng transaction; retry idempotent và không hồi sinh client REVOKED qua rollback snapshot.
- [ ] Mọi `provision/activate/rotate` phải kiểm tra authoritative client state trong cùng serialization boundary, không tạo A3 sau khi client A revoked.
- [ ] Thiết lập revoke propagation SLA: cache TTL/version invalidation, gateway routing/barrier, multi-region consistency; **fail closed** khi không biết client status.
- [ ] Với chính sách cấm side effect sau revoke, triển khai **authoritative business commit-time fence**/epoch check được phối hợp với revoke, không chỉ pre-HMAC check.
- [ ] Canonical request ký method, raw URI/query, audience, client ID, key ID, timestamp, nonce, content type/body SHA-256; reject duplicate security headers.
- [ ] HMAC-SHA256 dùng full 32-byte tag, strict Base64 padded và `MessageDigest.isEqual`; không fallback sang key khác khi kid/HMAC sai.
- [ ] Timestamp freshness theo server clock, nonce được claim atomically sau HMAC hợp lệ, namespace theo `(audience,authenticatedClientId,nonce)` không key ID.
- [ ] Nonce retention bao trùm `P+F+margin` hoặc tới `signedTs+P+margin`; store dùng chung nhiều replica, xử lý outage fail closed.
- [ ] Không cho revoked client truy xuất **idempotency response cache** hoặc dữ liệu nhạy cảm trước authentication/authorization hiện tại.
- [ ] Secret manager/KMS áp dụng least privilege; không xuất raw secret/log, không coi key cache còn secret là bằng chứng client active.
- [ ] Gateway/backend có trust boundary rõ, strip spoofed identity headers, mTLS/authenticated hop, chặn direct bypass và preserve signed request semantics.
- [ ] HTTP public errors không tiết lộ client/key đang revoked; phân loại chi tiết chỉ trong audit/telemetry đã giảm dữ liệu.
- [ ] Đo revocation lag, policy epoch drift, unauthorized admin calls, key provisioning sau revoke, HMAC/replay events và business commits sau revoke.
- [ ] Kiểm thử key revoke vs client revoke, cô lập A/B, key ID trùng, concurrent 8-way, in-flight/TOCTOU, multi-region stale cache, HMAC tamper, nonce TTL, registry/nonce outage và business authz.

**Kết luận:** **Thu hồi từng client** trong hệ thống HMAC đa khách hàng là quyết định **về danh tính và phạm vi xác thực**, không chỉ xóa hoặc rotate một secret. Muốn revoke `partner-42` nhưng vẫn phục vụ `partner-77`, hệ thống phải có **client policy độc lập, key lookup theo scope, transition nguyên tử không hồi sinh, consistency của trạng thái thu hồi ở verifier và commit gate khi cần**, đồng thời tiếp tục áp dụng HMAC canonical request, timestamp/nonce chống replay, phân quyền và idempotency. Một secret cũ còn trong bộ nhớ **không phải quyền được xác thực**; policy thu hồi hiện tại mới quyết định client còn được phục vụ hay không.

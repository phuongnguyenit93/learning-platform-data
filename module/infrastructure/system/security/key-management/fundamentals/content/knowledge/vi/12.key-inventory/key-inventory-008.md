# Activation time

> **Chương:** Key inventory  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. Activation time là gì?

**Activation time (thời điểm kích hoạt khóa)** là **mốc thời gian từ đó một khóa hoặc một phiên bản khóa có thể bắt đầu được phép sử dụng** cho những mục đích mật mã đã quy định, **nếu mọi điều kiện khác của chính sách đều đạt**. Trong một hệ thống quản lý khóa, activation time thường là một trường metadata quan trọng của **key inventory (danh mục khóa)**.

Ví dụ: nhóm an ninh tạo trước `payment-kek-v3` ngày 28/11/2026 và cấu hình `activationAt = 2026-12-01T00:00:00Z`. Khóa đã tồn tại và có thể đã được nạp vào HSM, nhưng **không được dùng để bọc DEK mới trước thời điểm kích hoạt**. Đúng thời điểm đã hẹn, nếu khóa ở trạng thái được cho phép, policy đã được phê duyệt và ứng dụng chọn đúng version, các thao tác được cấp quyền mới bắt đầu sử dụng khóa.

**Activation time không phải một lời hứa rằng khóa sẽ tự động dùng được đúng giây đó.** Nếu chưa đủ điều kiện, chẳng hạn trạng thái vẫn là `PRE_ACTIVE`, chưa có quyền IAM, HSM không sẵn sàng hoặc policy chưa đồng bộ, hệ thống phải **từ chối**, không bỏ qua kiểm soát chỉ vì đồng hồ đã tới hạn.

Trong mô hình quản lý khóa an toàn, điều kiện tối thiểu thường là:

~~~text
Được phép sử dụng khóa tại thời điểm T
    = đúng key ID/version
    AND state cho phép thao tác
    AND T >= activationAt
    AND T < hạn dùng cho thao tác đó
    AND key usage / algorithm phù hợp
    AND quyền IAM/KMS/HSM hợp lệ
    AND quyền nghiệp vụ cho resource/tenant hợp lệ
    AND không bị suspend/revoke/compromise theo policy
~~~

**Trọng tâm của bài:** hiểu đúng trường `activationAt` trong key inventory, đưa nó vào quy trình **sinh → cấp phát → kích hoạt → sử dụng → xoay vòng → ngừng dùng/thu hồi → hủy**, và triển khai các kiểm soát để mốc thời gian có hiệu lực thật sự trong hệ thống phân tán.

## 2. Phân biệt những mốc thời gian dễ nhầm lẫn

Một key inventory có thể có nhiều timestamp. Nếu đặt tất cả thành một trường `createdAt` hoặc `validUntil`, rất dễ dùng khóa sai thời điểm.

| Thuộc tính | Ý nghĩa | Có đồng nghĩa activation time không? |
| --- | --- | --- |
| **`generatedAt` / `createdAt`** | Thời điểm tạo vật liệu khóa hoặc đối tượng quản lý | **Không**: khóa có thể được tạo trước và chưa được phép dùng |
| **`importedAt` / `provisionedAt`** | Thời điểm nạp vào KMS/HSM hoặc cấp phát cho workload | **Không**: đã tồn tại ở đích chưa có nghĩa đã kích hoạt |
| **`activationAt`** | Thời điểm sớm nhất dự kiến được phép dùng theo chính sách | **Là mốc của bài**; không tự vượt qua state và authorization |
| **`activatedAt` / `activationConfirmedAt`** | Thời điểm có bằng chứng thao tác kích hoạt thực tế thành công | Có thể **trễ hơn** `activationAt`; nên tách khi cần kiểm toán |
| **`firstUsedAt`** | Lần sử dụng thực tế đầu tiên được ghi nhận | Có thể trễ hơn activation nhiều giờ/ngày |
| **`newUseUntil` / `deactivationAt`** | Mốc kết thúc quyền tạo bảo vệ mới | **Không**: là ranh giới kết thúc một loại usage |
| **`oldUseUntil`** | Mốc kết thúc khả năng decrypt/unwrap/verify dữ liệu cũ theo chính sách | Có thể đến sau `newUseUntil` |
| **`revokedAt` / `compromisedAt`** | Mốc thu hồi niềm tin/sử dụng hoặc mốc ghi nhận lộ khóa | Phải xử lý **độc lập**, có thể kết thúc quyền trước lịch |
| **`destroyedAt`** | Thời điểm hoàn tất hủy vật liệu khóa theo bảo đảm của nền tảng | Không phải mốc kích hoạt |
| **`certificate.notBefore`** | Mốc bắt đầu hiệu lực của **chứng thư X.509** | Có liên quan nhưng **không phải** `activationAt` của mọi thao tác khóa |

**Điều cần nhớ:** `activationAt` thể hiện **ý định chính sách**, còn `activatedAt` có thể thể hiện **sự kiện đã xảy ra**. Trong hệ thống chỉ có một trường, phải định nghĩa dứt khoát nó là **scheduled effective time** hay **actual transition time**; không trộn hai ý nghĩa.

### 2.1. Ví dụ cùng một khóa với nhiều mốc

~~~text
2026-11-28 09:00Z  generatedAt       — KMS sinh kek-v3
2026-11-28 09:05Z  provisionedAt     — cấp policy, đưa vào inventory
2026-12-01 00:00Z  activationAt      — thời điểm bắt đầu được phép Wrap mới
2026-12-01 00:00Z  activatedAt      — job xác nhận activation thành công
2026-12-01 00:02Z  firstUsedAt      — request đầu tiên thực sự sử dụng
2027-03-01 00:00Z  newUseUntil      — ngừng Wrap mới; v4 trở thành primary
2027-09-01 00:00Z  oldUseUntil      — hết cửa sổ Unwrap dữ liệu cũ
                    destroyedAt    — chỉ sau kiểm tra backup và phê duyệt
~~~

Các mốc trên là **minh họa**, không phải yêu cầu thời hạn áp dụng cho mọi loại khóa. Đặc biệt, thời điểm thực tế có thể đến trễ hoặc thất bại do hệ thống vận hành; lịch kích hoạt phải có cơ chế phát hiện và xử lý.

## 3. Activation time nằm ở đâu trong key inventory?

**Key inventory** là danh mục có thể truy vấn và kiểm toán về các khóa đang được tổ chức quản lý. Nó nên trả lời được: khóa này **là khóa gì, thuộc ai, nằm ở đâu, được dùng vào mục đích nào, có hiệu lực từ khi nào, còn được dùng bao lâu và ai được phép sử dụng**.

### 3.1. Metadata tối thiểu có ích

| Nhóm | Trường ví dụ | Vì sao cần? |
| --- | --- | --- |
| Định danh | `keyId`, `keyVersion`, `alias` | Phân biệt logical key với phiên bản vật liệu cụ thể |
| Chủ sở hữu | `owner`, `tenant`, `environment`, `service` | Tránh dùng nhầm tenant hoặc staging/production |
| Thuật toán | `algorithm`, `keySize`, `curve` | Kiểm tra tương thích và chính sách độ mạnh |
| Mục đích | `keyUsage`: `ENCRYPT`, `DECRYPT`, `WRAP`, `UNWRAP`, `SIGN`, `VERIFY` | Tránh dùng một key sai mục đích |
| Trạng thái | `lifecycleState`, `primaryForNewUse` | Phân biệt ACTIVE và version đang là mặc định |
| Thời điểm | `createdAt`, **`activationAt`**, `newUseUntil`, `oldUseUntil` | Thực thi cryptoperiod theo thao tác |
| Sự cố | `suspendedAt`, `revokedAt`, `compromiseReason` | Chặn khẩn cấp và điều tra |
| Vị trí | `kmsKeyRef`, `hsmPartition`, `keyStoreRef` | Gọi đúng hệ thống giữ key material |
| Phê duyệt | `policyVersion`, `approvedBy`, `activatedAt` | Kiểm soát thay đổi và chứng cứ kích hoạt |
| Kiểm toán | `lastUsedAt`, `operationCount`, `updatedAt` | Quan sát sai lệch và hạn mức sử dụng |
| Phụ thuộc | `wrappedDekCount`, `dependentServices`, `backupRefs` | Chuẩn bị rotation, retirement và destruction |

**Inventory không phải nơi lưu private key/DEK dạng rõ.** Các trường nên là metadata, định danh hoặc tham chiếu tới keystore/KMS/HSM. Dữ liệu inventory vẫn phải được bảo vệ khỏi chỉnh sửa trái phép: nếu attacker sửa `activationAt` hoặc `primaryForNewUse`, họ có thể khiến hệ thống dùng khóa chưa được phê duyệt hoặc khóa đã nghỉ hưu.

### 3.2. Bản ghi ví dụ

~~~json
{
  "keyId": "billing-kek",
  "keyVersion": "v3",
  "owner": "billing-service",
  "tenantScope": "production",
  "algorithm": "AES-256",
  "purpose": ["WRAP", "UNWRAP"],
  "lifecycleState": "PRE_ACTIVE",
  "primaryForNewUse": false,
  "createdAt": "2026-11-28T09:00:00Z",
  "activationAt": "2026-12-01T00:00:00Z",
  "newUseUntil": "2027-03-01T00:00:00Z",
  "oldUseUntil": "2027-09-01T00:00:00Z",
  "kmsKeyRef": "kms://billing/keys/billing-kek/v3",
  "policyRevision": 17,
  "approvedBy": "key-governance-workflow"
}
~~~

Bản ghi minh họa này **không chứa khóa bí mật**. URI `kms://...` chỉ là chuỗi giả lập, **không phải định dạng chuẩn cho mọi KMS**. `AES-256` ở đây là thông tin khái quát của khóa; thuật toán bọc thực tế phải được định nghĩa rõ theo API KMS/HSM và chính sách.

Điểm đáng chú ý là bản ghi có `activationAt` trong tương lai nhưng **vẫn đang `PRE_ACTIVE` và chưa primary**. Một job được lên lịch chỉ được chuyển state/primary sau khi kiểm tra các điều kiện, không lấy timestamp làm lý do bỏ qua phê duyệt.

## 4. Vòng đời và state machine của khóa

Lịch kích hoạt gắn chặt với trạng thái, nhưng **trạng thái và timestamp là hai chiều kiểm soát độc lập**.

~~~mermaid
flowchart TD
    G[Generated] --> P[Provisioned / Pre-active]
    P --> A{Đến activationAt và đủ policy?}
    A -->|Chưa| P
    A -->|Đủ, đã xác nhận| ACT[Active]
    ACT --> R[Retired / Deactivated]
    ACT --> S[Suspended]
    S -->|Được phê duyệt khôi phục| ACT
    ACT --> C[Revoked / Compromised]
    S --> C
    R --> C
    R --> D[Destroyed theo retention]
    C --> D
~~~

Sơ đồ là **mô hình học thuật**, không đại diện nguyên dạng state machine của AWS KMS, Google Cloud KMS, Azure Key Vault hay một thiết bị HSM bất kỳ. Một nền tảng có thể chỉ phân biệt `Enabled/Disabled/PendingDeletion`; ứng dụng có thể cần quản lý **cryptoperiod riêng** để quyết định chỉ ký/mã hóa mới bằng phiên bản nào.

### 4.1. Hai trường hợp cần từ chối

**Trường hợp A — đến giờ nhưng chưa được phép:** `now >= activationAt`, nhưng trạng thái vẫn `PRE_ACTIVE` hoặc phê duyệt/chuyển đổi chưa hoàn tất. **Từ chối thao tác** và cảnh báo job activation chưa thành công.

**Trường hợp B — đã Active nhưng chưa đến giờ:** một admin bật key object sớm hơn dự kiến. Nếu policy nghiệp vụ quy định `now < activationAt`, **vẫn từ chối thao tác bảo vệ mới**.

Vì vậy, **`ACTIVE` và `now >= activationAt` cần cùng đúng** khi policy có mốc kích hoạt. Ngoài ra vẫn cần kiểm tra IAM, purpose, tenant, limits và trạng thái thu hồi.

### 4.2. Primary version không đồng nghĩa Active

Một hệ thống có thể cho phép `v2` và `v3` cùng tồn tại trong trạng thái có thể xử lý dữ liệu cũ, nhưng chỉ **`v3` là primary** cho `WRAP_NEW`. Việc chuyển primary là **thay đổi điều phối** với hiệu lực và thời điểm xác định; không phải lúc nào cũng là kích hoạt vật liệu khóa lần đầu.

Không nên giải mã bản ghi cũ chỉ bằng một alias `current` đã trỏ sang khóa khác. Ciphertext hoặc wrapped DEK phải mang **key ID/version** đáng tin theo định dạng để dùng đúng khóa đã bảo vệ bản ghi đó.

## 5. Activation time, cryptoperiod và thời hạn sử dụng

**Cryptoperiod** là khoảng thời gian một khóa được phép sử dụng cho các thao tác được chỉ định. Activation time thường là ranh giới **bắt đầu originator-usage period** — thời gian được phép **tạo bảo vệ mới**; tuy nhiên, các quy tắc cụ thể do chính sách và loại khóa quyết định.

Cần phân biệt hai khoảng:

- **Originator-usage period:** mã hóa mới, wrap DEK mới, ký tài liệu mới.
- **Recipient-usage period:** giải mã bản mã đã tồn tại, unwrap DEK cũ hoặc xử lý chứng cứ/chữ ký lịch sử theo chính sách.

~~~text
Thời gian UTC  ---------------------------------------------------->

Generated   Activation                         New-use ends        Old-use ends
    |           |                                     |                   |
    v           v                                     v                   v
 [Pre-active] [ACTIVE: ENCRYPT/WRAP/SIGN NEW] [RETIRED: DECRYPT/UNWRAP OLD] [Stop]
             |<----- originator-usage ----->|<------ recipient-only ---->|

Ghi chú: với VERIFY chữ ký lịch sử cần chính sách trust và bằng chứng thời gian riêng.
~~~

### 5.1. Khoảng thời gian nửa mở

Để không mơ hồ tại đúng ranh giới, nên chọn quy ước **nửa mở**:

\[
\text{new-use allowed} \iff activationAt \le now < newUseUntil
\]

\[
\text{old-use allowed} \iff activationAt \le now < oldUseUntil
\]

Nếu định nghĩa quyền cũ bắt đầu ngay từ lúc khóa được kích hoạt, có thể xét khoảng trên; nhưng **còn điều kiện state và thao tác**. Sau `newUseUntil`, key có thể không còn được dùng để tạo bản mã mới, dù vẫn có quyền decrypt-old. Tại **chính xác `newUseUntil`**, request bảo vệ mới phải bị từ chối.

Không gộp mọi thời gian vào một trường `expiresAt`, vì sẽ dễ hoặc **hủy khóa quá sớm**, hoặc **dùng khóa cũ để tạo dữ liệu mới quá lâu**.

### 5.2. Ví dụ khóa ký số

Private signing key có thể chỉ được phép tạo chữ ký từ `activationAt` đến `newUseUntil`. Sau khi hết giai đoạn này, verifier vẫn có thể cần **public key/chứng thư** để kiểm tra chữ ký lịch sử. Tuy nhiên:

1. **`Signature.verify() = true`** chỉ chứng minh chữ ký hợp lệ đối với public key và đúng byte thông điệp.
2. Cần xác thực **binding public key ↔ người ký**, thời hạn chứng thư, mục đích sử dụng và trạng thái thu hồi.
3. Để chứng minh chữ ký được tạo **trong thời gian được phép**, có thể cần **trusted timestamp** hoặc bằng chứng thời gian độc lập; trường `signedAt` do người ký tự khai báo không đủ.
4. Khóa/chứng thư bị compromise hoặc revoke có thể thay đổi quyết định tin cậy lịch sử theo chính sách.

**Đừng lấy `activationAt` của một key trong inventory làm chứng cứ độc lập về thời điểm chữ ký thực sự được tạo.**

### 5.3. Ví dụ khóa phiên

Traffic keys của TLS/SSH có thời hạn sử dụng ngắn và thường được kích hoạt theo **handshake/key schedule**. Không cần tạo một bản ghi inventory riêng cho mỗi traffic key trong tất cả hệ thống. Inventory có thể quản lý **khóa dài hạn, PSK, ticket key, khóa ký/cert hoặc policy của TLS stack**, còn các traffic secrets tạm thời được quản lý nội bộ bởi giao thức.

Không được dùng một timestamp từ inventory để thay thế **trình tự xác thực handshake** hoặc cơ chế key update của TLS 1.3.

## 6. Quy trình chuẩn bị và kích hoạt key version

Kích hoạt theo lịch phải được thiết kế thành **quy trình có điều kiện và có quan sát**, không phải cron job đơn giản đổi Boolean `isActive = true`.

### 6.1. Preflight trước activation

| Điều kiện | Kiểm tra cần thực hiện |
| --- | --- |
| Key material | Sinh bằng RNG/provider/KMS/HSM phù hợp, đủ độ mạnh và đúng thuật toán |
| Purpose | Chỉ định `WRAP`, `UNWRAP`, `SIGN`, `ENCRYPT`... theo chính sách |
| Ownership | Owner, tenant, môi trường và danh sách workload sử dụng hợp lệ |
| Storage | Khóa nằm trong vùng bảo vệ đã phê duyệt; hạn chế xuất raw key |
| IAM | Principal/role có quyền tối thiểu, tách quyền quản trị và sử dụng |
| Metadata | Key ID/version, `activationAt`, cryptoperiod, policy revision chính xác |
| Đường chuyển đổi | Ứng dụng biết phân biệt primary-for-new với old-version-for-decrypt |
| Data compatibility | Có thể đọc ciphertext/wrapped DEK cũ, key references và backups |
| Observability | Audit chuyển state, canary, chỉ số theo key version, cảnh báo lỗi |
| Approval | Thay đổi đã được duyệt bởi workflow/chủ thể có thẩm quyền |

### 6.2. Trình tự activation có thể kiểm toán

~~~mermaid
sequenceDiagram
    participant Admin as Key governance
    participant Inventory as Key inventory / policy
    participant KMS as KMS/HSM
    participant Scheduler as Activation controller
    participant App as Ứng dụng
    Admin->>KMS: Sinh hoặc import key version mới
    KMS-->>Admin: Key reference + trạng thái thực
    Admin->>Inventory: Ghi metadata, activationAt, policyRevision
    Admin->>Inventory: Phê duyệt activation plan
    Scheduler->>Inventory: Đọc policy/version và thời gian đáng tin
    Scheduler->>Scheduler: Kiểm tra now >= activationAt và mọi precondition
    Scheduler->>KMS: Enable/allow operations khi phù hợp API
    KMS-->>Scheduler: Result / failure
    Scheduler->>Inventory: Commit ACTIVE và primary mapping có kiểm soát
    Inventory-->>App: Versioned event + hiệu lực
    App->>Inventory: Revalidate trước thao tác mới
    App->>KMS: Thực thi theo key version, IAM và policy
~~~

Sơ đồ mô tả **một quy trình logic**, không có nghĩa mọi hạ tầng đều hỗ trợ transaction nguyên tử giữa KMS, inventory và hàng đợi event. Phải thiết kế **retry idempotent, điều kiện chuyển state, rollback an toàn và phát hiện trạng thái lệch**.

**Nếu KMS báo lỗi hoặc inventory không đồng bộ**, không đánh dấu hoàn thành chỉ vì scheduler đã chạy. Nếu activation chưa thành công, ứng dụng không được tự dùng khóa mới hoặc fallback sang khóa không được phép. Cần cảnh báo, thực hiện retry theo policy và giữ an toàn dữ liệu.

## 7. Activation time trong rotation có kế hoạch

Một chiến lược rotation an toàn thường có **giai đoạn chồng lấn**:

1. Tạo khóa `key-v2` **trước activationAt** để có thời gian kiểm thử và phân phối metadata/public key.
2. Phân phối trust/khả năng đọc key version mới cho các verifier/consumer **trước khi bắt đầu ký hoặc mã hóa bằng khóa mới**, nếu kiến trúc cho phép.
3. Khi tới thời điểm đủ điều kiện, kích hoạt `key-v2` và chuyển **primary for new use** sang `v2`.
4. Ngừng dùng `key-v1` cho **ENCRYPT/WRAP/SIGN_NEW**, nhưng giữ thao tác đọc/xác minh lịch sử theo chính sách.
5. Rewrap/re-encrypt dữ liệu phụ thuộc, kiểm tra backup và quan sát những request dùng version cũ.
6. Đóng quyền cũ và hủy key material theo retention, **chỉ sau khi không còn phụ thuộc**.

### 7.1. Lịch minh họa khi thay KEK

| Mốc UTC | `kek-v1` | `kek-v2` |
| --- | --- | --- |
| 28/11/2026 09:00 | Primary, wrap/unwrap | Đã tạo, pre-active |
| 01/12/2026 00:00 | Ngừng wrap mới, unwrap-old có kiểm soát | Activation, trở thành primary để wrap mới |
| 01/03/2027 00:00 | Gần hết cửa sổ xử lý dữ liệu cũ theo kế hoạch | Tiếp tục wrap/unwrap theo policy |
| Sau khi hoàn tất migration/backup | Hủy theo quy trình được phê duyệt | Vẫn quản lý theo cryptoperiod riêng |

**Không tự nhận rằng `v2` kích hoạt sẽ lập tức khiến `v1` không còn decrypt được.** Với dữ liệu cũ, khả năng decrypt thường cần tồn tại đến lúc migration/retention hoàn tất; ngược lại, nếu `v1` bị lộ, phải đánh giá **khác với rotation định kỳ**.

### 7.2. Alias và key version phải rõ nghĩa

Một alias `billing-kek-current` có thể trỏ tới `v2` sau khi activation. Nhưng:

- **Dữ liệu mới** có thể dùng alias primary sau khi kiểm tra state, policy và thời gian.
- **Dữ liệu cũ** phải tham chiếu đúng key ID/version đã dùng để wrap DEK hoặc mã hóa.
- **Không dùng alias đang trỏ `v2` để giải mã một payload chỉ biết đã mã hóa bằng `v1`** nếu provider không có cơ chế phiên bản hóa/nhận diện an toàn hỗ trợ.
- **Không tin `version` do client tự khai** để chọn quyền giải mã dữ liệu tenant khác.

Khi chuyển alias, cần thống nhất **nguồn sự thật**, thời điểm hiệu lực và cache invalidation để tránh node A dùng `v1`, node B dùng `v2` lâu hơn kế hoạch.

## 8. Tùy loại khóa, activation mang nghĩa vận hành khác nhau

| Loại khóa | Khi activation có ý nghĩa gì? | Điều cần quản lý |
| --- | --- | --- |
| **AES DEK** | Bắt đầu mã hóa record mới bằng DEK theo policy | Nonce uniqueness, data scope, DEK rotation, backup |
| **KEK trong KMS/HSM** | Cho phép wrap/unwrap theo policy và key version | IAM, alias primary, wrapped DEK cũ, rewrap |
| **Private key ký số** | Được phép tạo chữ ký mới | Chứng thư, public key distribution, cryptoperiod, signer authorization |
| **Public key xác minh** | Có thể được đưa vào **tập tin cậy theo policy** | Binding danh tính, issuer, chain, trust-store/JWKS cache |
| **PSK / HMAC key** | Các bên được phép bắt đầu dùng bí mật phiên bản mới | Secure provisioning, đồng bộ peer, replay, rotation |
| **Private key giải mã** | Được dùng cho decrypt/unwrap theo chính sách | Dữ liệu đã mã hóa cho public key, retention, không xuất private key |
| **TLS ticket key** | Được phép phát hành hoặc xử lý ticket theo key schedule của server | Đồng bộ giữa node, thời gian ticket, revoke/session handling |

### 8.1. KMS/HSM activation không phải policy chung của mọi API

**KMS** có thể lưu trạng thái `Enabled`, `Disabled`, `PendingDeletion` và hỗ trợ version/alias theo cách riêng. Một số hệ thống hỗ trợ start/end date cho **một số loại vật liệu hoặc policy**, một số không tự bật/tắt theo timestamp.

Nếu API không cung cấp `activationAt` như một điều kiện kiểm tra tại lúc dùng, ứng dụng cần **inventory/policy service** của riêng mình; nhưng policy ứng dụng không thay thế **KMS/HSM enforcement**, và phải tính đến TOCTOU. Không giả định cloud provider nào cũng có nút "schedule activation" áp dụng cho mọi loại khóa.

### 8.2. Chứng thư X.509 `notBefore` khác activation

Chứng thư TLS/PKI có trường hiệu lực `notBefore` và `notAfter`. Public key/chứng thư có thể được **phát hành/phân phối sớm** để client kịp cập nhật, nhưng **không được coi chứng thư có hiệu lực trước `notBefore`** theo kiểm tra PKIX. Tương tự, `notBefore` đã đến **không tự cấp quyền `Sign`** tại HSM, không xác thực issuer/hostname hay làm ứng dụng tin khóa chưa được cấp phép.

Nếu có cả **certificate validity** và **key activation policy**, một chữ ký/kết nối chỉ nên được chấp nhận khi **tất cả điều kiện áp dụng** đều đạt. Không chỉnh ngược `activationAt` để bỏ qua chứng thư chưa có hiệu lực.

### 8.3. JWT/JWKS và kích hoạt khóa ký

Một issuer JWT có thể **công bố public key mới trong JWKS trước khi bắt đầu ký** bằng private key mới để bên xác minh có thời gian cache. Khi issuer chuyển sang dùng khóa mới:

- Token phải chỉ rõ `kid` phù hợp; `kid` chỉ là bộ chọn trong **tập khóa của issuer đã tin cậy**.
- Verifier phải kiểm tra `iss`, `aud`, `exp`, chữ ký và thuật toán được phép.
- Public key cũ có thể cần ở lại JWKS đủ lâu để xác minh token cũ **còn hợp lệ** theo chính sách.
- Nếu key cũ bị compromise, **cần xử lý revoke khác rotation bình thường**, có thể buộc từ chối token liên quan sớm hơn.

**Public key đã có mặt trong JWKS không chứng minh private signing key tương ứng đã Active hay token đã được ký tại một thời điểm đáng tin.**

## 9. Thời gian UTC, độ chính xác và nguồn thời gian tin cậy

### 9.1. Dùng mốc thời gian tuyệt đối

Trong Java, **`Instant`** biểu diễn một mốc trên timeline UTC; dùng rất phù hợp cho `activationAt`. Tránh lưu chỉ `2026-12-01 07:00` mà không có timezone, vì hệ thống đa vùng có thể hiểu khác nhau.

~~~text
activationAt = 2026-12-01T00:00:00Z

Tương ứng ở UTC+07:00:
             2026-12-01 07:00:00+07:00
~~~

Nếu yêu cầu nghiệp vụ nói "bắt đầu lúc 00:00 theo giờ Hà Nội", phải **chuyển từ timezone lịch sang `Instant` trước khi lưu**, không đặt `Z` tùy tiện sau giờ địa phương. Với timezone có daylight saving, các mốc có thể mơ hồ hoặc không tồn tại khi quy đổi; cần xác định chính sách chuyển đổi.

### 9.2. Clock skew và nguồn thời gian

Nếu node A chạy nhanh hơn thực tế 30 giây, nó có thể cho dùng khóa **sớm hơn kế hoạch**. Nếu node B chạy chậm, nó có thể tiếp tục dùng khóa cũ **quá hạn**. Vì vậy:

- Đồng bộ thời gian máy chủ bằng cơ chế vận hành đáng tin (ví dụ hạ tầng time synchronization được quản trị).
- Xác định **điểm ra quyết định authoritative**, tránh tin đồng hồ do client gửi trong request.
- Theo dõi clock drift; có chiến lược xử lý khi sai lệch vượt ngưỡng cho phép.
- Không tự nới cửa sổ kích hoạt với một khoảng `grace` chung nếu làm hỏng ranh giới an toàn.
- Ở hệ thống nhạy cảm, cần thực thi policy gần nơi thao tác mật mã và xét giới hạn về đồng hồ phân tán.

**Chữ ký số không tự xác thực thời điểm tạo chỉ vì inventory biết `activationAt`.** Nếu cần chứng minh lịch sử, sử dụng **trusted timestamp/evidence** thay vì `now` do người ký khai báo.

### 9.3. Quyết định khi hệ thống không biết chắc thời gian

Nếu nguồn thời gian hoặc service policy có lỗi nghiêm trọng, hoạt động tạo bảo vệ mới không nên **fallback sang ngày giờ tùy ý hoặc khóa cũ**. Lựa chọn fail-closed/fail-safe phải được nêu rõ theo mức rủi ro và yêu cầu sẵn sàng, kèm kế hoạch phục hồi.

## 10. Scheduled activation trong hệ thống phân tán

Một scheduler có thể ghi chuyển trạng thái, nhưng việc **tất cả node bắt đầu dùng đúng key version** còn phụ thuộc đồng bộ control plane/data plane.

~~~mermaid
flowchart LR
    Clock[Thời gian đáng tin] --> Controller[Activation controller]
    Policy[Inventory + policyRevision + approval] --> Controller
    Controller --> KMS[KMS/HSM / Key registry]
    Controller --> Event[Versioned activation event]
    Event --> A[Region A]
    Event --> B[Region B]
    Event --> C[Region C / workers]
    A --> Use[Encrypt / Sign / Wrap new]
    B --> Use
    C --> Use
    KMS --> Use
    Audit[Audit + propagation metrics] --> Controller
    Event --> Audit
~~~

### 10.1. Những lỗi dễ xảy ra

**Tình huống 1 — kích hoạt sớm:** một instance chuyển primary trước `activationAt` do cache hoặc clock skew. Tạo bản mã/chữ ký mới bằng key chưa được phê duyệt đúng thời điểm.

**Tình huống 2 — kích hoạt trễ:** đến giờ nhưng job thất bại. Nếu không có giám sát, hệ thống vẫn dùng key cũ hoặc dừng ghi; phải có **quy tắc xử lý** đã phê duyệt.

**Tình huống 3 — trạng thái lệch:** inventory báo `ACTIVE` nhưng KMS vẫn `Disabled`; nhiều request bị lỗi. Ngược lại, KMS đã `Enabled` nhưng inventory vẫn pre-active không có nghĩa được phép dùng.

**Tình huống 4 — stale cache/alias:** node A đã dùng `v2`, node B vẫn `v1`. Nếu `v1` đã vượt new-use period, node B có thể vi phạm policy.

**Tình huống 5 — batch hoặc retry:** một batch được tạo trước activation nhưng retry sau thời điểm chuyển đổi. Cần xác định **quy tắc chọn key theo thời điểm thực thi thao tác**, không theo timestamp do client giả lập.

### 10.2. Cơ chế khắc phục

- Lưu **`policyRevision` tăng đơn điệu** và kiểm tra revision mới nhất ở điểm thực thi.
- Activation event có **event ID**, timestamp, key/version, từ-state/đến-state, revision, chữ ký/xác thực nguồn phát nếu phù hợp.
- Consumer xử lý **idempotent**; event nhận lại hoặc đến lệch thứ tự không làm rollback policy.
- **Cache invalidation** chủ động và TTL được định nghĩa theo độ rủi ro.
- Thực hiện **canary**, kiểm tra negative cases ở một vùng trước khi mở rộng.
- Audit ghi **key ID/version thực tế đã dùng** thay vì chỉ alias mà request yêu cầu.
- Có cơ chế **reconcile** giữa inventory, KMS/HSM, registry, scheduler và những node còn offline.

Đặc biệt, **TOCTOU (time-of-check to time-of-use)** xuất hiện khi ứng dụng kiểm tra trước activation nhưng trạng thái/quyền thay đổi giữa lần kiểm tra và lúc KMS thực thi. Cần enforcement gần **điểm sử dụng khóa**, không dựa hoàn toàn trên một cờ cache được kiểm tra từ lâu.

## 11. Java 17: kiểm tra activation time trước khi dùng key

Ví dụ mô hình hóa metadata key inventory và **quy tắc cho phép theo trạng thái, thời gian, mục đích và primary version**. Chương trình không thực hiện `AES-GCM` hay gọi KMS thật; mục tiêu là giải thích policy gate và những **điểm kiểm thử ranh giới**.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.EnumSet;
import java.util.Set;

public final class KeyActivationPolicyDemo {
    enum State {
        PRE_ACTIVE, ACTIVE, RETIRED, SUSPENDED, REVOKED, DESTROYED
    }

    enum Operation {
        ENCRYPT_NEW, WRAP_NEW, SIGN_NEW, DECRYPT_OLD, UNWRAP_OLD
    }

    record KeyEntry(
            String keyId,
            String keyVersion,
            State state,
            Instant createdAt,
            Instant activationAt,
            Instant newUseUntil,
            Instant oldUseUntil,
            Instant revokedAt,
            boolean primaryForNewUse,
            Set<Operation> allowedOperations,
            long policyRevision) {
        KeyEntry {
            if (keyId == null || keyId.isBlank()
                    || keyVersion == null || keyVersion.isBlank()
                    || state == null || createdAt == null
                    || activationAt == null || newUseUntil == null
                    || oldUseUntil == null || allowedOperations == null
                    || policyRevision < 1
                    || createdAt.isAfter(activationAt)
                    || !activationAt.isBefore(newUseUntil)
                    || newUseUntil.isAfter(oldUseUntil)) {
                throw new IllegalArgumentException("Invalid inventory entry");
            }
            allowedOperations = Set.copyOf(allowedOperations);
        }
    }

    static boolean mayUse(KeyEntry key, Operation op, Instant now) {
        if (key == null || op == null || now == null
                || !key.allowedOperations().contains(op)
                || now.isBefore(key.activationAt())) {
            return false;
        }
        if (key.state() == State.PRE_ACTIVE
                || key.state() == State.SUSPENDED
                || key.state() == State.REVOKED
                || key.state() == State.DESTROYED
                || (key.revokedAt() != null
                    && !now.isBefore(key.revokedAt()))) {
            return false;
        }

        return switch (op) {
            case ENCRYPT_NEW, WRAP_NEW, SIGN_NEW ->
                    key.state() == State.ACTIVE
                    && key.primaryForNewUse()
                    && now.isBefore(key.newUseUntil());

            case DECRYPT_OLD, UNWRAP_OLD ->
                    (key.state() == State.ACTIVE
                            || key.state() == State.RETIRED)
                    && now.isBefore(key.oldUseUntil());
        };
    }

    public static void main(String[] args) {
        Instant created = Instant.parse("2026-11-28T09:00:00Z");
        Instant activate = Instant.parse("2026-12-01T00:00:00Z");
        Instant endNew = Instant.parse("2027-03-01T00:00:00Z");
        Instant endOld = Instant.parse("2027-09-01T00:00:00Z");
        Set<Operation> ops = EnumSet.of(
                Operation.WRAP_NEW, Operation.UNWRAP_OLD);

        KeyEntry pending = new KeyEntry(
                "billing-kek", "v3", State.PRE_ACTIVE, created,
                activate, endNew, endOld, null, false, ops, 17);
        KeyEntry active = new KeyEntry(
                "billing-kek", "v3", State.ACTIVE, created,
                activate, endNew, endOld, null, true, ops, 18);
        KeyEntry retired = new KeyEntry(
                "billing-kek", "v3", State.RETIRED, created,
                activate, endNew, endOld, null, false, ops, 19);
        KeyEntry revoked = new KeyEntry(
                "billing-kek", "v3", State.REVOKED, created,
                activate, endNew, endOld,
                Instant.parse("2027-01-20T12:00:00Z"),
                false, ops, 20);

        // Clock được inject; test thời gian không phụ thuộc máy chạy.
        Clock justBefore = Clock.fixed(
                activate.minusNanos(1), ZoneOffset.UTC);
        Clock onBoundary = Clock.fixed(activate, ZoneOffset.UTC);
        Clock afterRotation = Clock.fixed(
                Instant.parse("2027-04-01T00:00:00Z"), ZoneOffset.UTC);

        if (mayUse(active, Operation.WRAP_NEW, Instant.now(justBefore))) {
            throw new AssertionError("Activated too early");
        }
        if (mayUse(pending, Operation.WRAP_NEW, Instant.now(onBoundary))) {
            throw new AssertionError("Pre-active key was accepted");
        }
        if (!mayUse(active, Operation.WRAP_NEW, Instant.now(onBoundary))) {
            throw new AssertionError("Activation boundary rejected");
        }
        if (mayUse(active, Operation.WRAP_NEW, endNew)) {
            throw new AssertionError("New-use period ended");
        }
        if (mayUse(retired, Operation.WRAP_NEW,
                Instant.now(afterRotation))) {
            throw new AssertionError("Retired key still wraps");
        }
        if (!mayUse(retired, Operation.UNWRAP_OLD,
                Instant.now(afterRotation))) {
            throw new AssertionError("Old data unexpectedly unreadable");
        }
        if (mayUse(revoked, Operation.UNWRAP_OLD,
                Instant.parse("2027-01-21T00:00:00Z"))) {
            throw new AssertionError("Revoked key was accepted");
        }
        System.out.println("Activation time policy checks passed");
    }
}
~~~

### 11.1. Các điểm then chốt trong đoạn mã

1. **Dùng `Instant` thay vì `LocalDateTime`** cho các mốc hiệu lực tuyệt đối; `Clock` được inject để kiểm tra ranh giới, không hard-code `now()` trong logic.
2. **Khoảng `[activationAt, newUseUntil)`** cho phép đúng lúc bắt đầu nhưng không cho dùng **tại** mốc kết thúc.
3. **State và thời gian là hai điều kiện độc lập:** `PRE_ACTIVE` đến đúng giờ vẫn bị từ chối; `ACTIVE` trước giờ cũng bị từ chối.
4. **`primaryForNewUse`** chặn chọn nhầm phiên bản cho thao tác mới; không cản `UNWRAP_OLD` của phiên bản đã retired theo policy minh họa.
5. **`allowedOperations`** cấm dùng sai purpose ngay cả khi key đang Active.
6. **`revokedAt`** và trạng thái `REVOKED` chặn sử dụng. Để đánh giá chữ ký lịch sử cần policy/evidence riêng, không dùng hàm này suy ra tính hợp lệ pháp lý trong quá khứ.
7. **`policyRevision`** là metadata phục vụ đồng bộ; demo chưa xác minh revision với nguồn sự thật hoặc làm authorization của principal/tenant.

**Giới hạn quan trọng:** đây là **policy gate ở ứng dụng**, không thay KMS/HSM, PKI, kiểm tra ciphertext ownership hoặc IAM. Production cần giải quyết **race, clock skew, cache, revocation, failure handling, backup và key version**. Không tự lấy `activationAt` từ request của client để quyết định quyền.

## 12. KMS/HSM và envelope encryption khi đến activation time

Trong **envelope encryption**, dữ liệu được mã hóa bằng **DEK** (Data Encryption Key), sau đó DEK được bọc bởi **KEK** (Key Encryption Key) trong KMS/HSM hoặc bằng cơ chế wrapping phù hợp.

~~~mermaid
sequenceDiagram
    participant Ops as Key governance
    participant Registry as Inventory/policy
    participant KMS as KMS/HSM
    participant App as Data service
    participant DB as Data store
    Ops->>Registry: Lên lịch activationAt cho KEK-v2
    Ops->>KMS: Sinh/provision KEK-v2 an toàn
    Registry->>App: Policy v2 có key mới pre-active
    App->>DB: Bản ghi mới vẫn theo primary cũ
    Note over Ops,App: Đến thời điểm và đủ điều kiện
    Ops->>Registry: Xác nhận kích hoạt và chuyển primary
    App->>KMS: Wrap DEK mới bằng KEK-v2 theo IAM
    App->>DB: Lưu ciphertext + wrapped DEK + key version
    DB-->>App: Bản ghi cũ dùng KEK-v1
    App->>KMS: Unwrap bằng KEK-v1 theo policy đọc dữ liệu cũ
    KMS-->>App: DEK nếu quyền/phiên bản hợp lệ
~~~

Khi chuyển sang KEK mới:

- **Dữ liệu mới:** dùng key version đã Active và được chọn cho `WRAP_NEW`.
- **Dữ liệu cũ:** tiếp tục dùng đúng KEK version đã bọc DEK nếu chính sách cho phép, hoặc **rewrap** sang KEK mới trước khi hủy khóa cũ.
- **Khi DEK bị lộ:** chỉ rewrap DEK dưới KEK mới **không thay byte DEK**, nên có thể cần **DEK mới và re-encrypt** dữ liệu.
- **Khi KEK bị lộ cùng wrapped DEK cũ:** rewrap bản hiện tại **không xóa** bản sao wrapped DEK mà attacker đã lấy; phải đánh giá khả năng lộ DEK/ciphertext và phương án re-encrypt.

**ActivationAt của KEK không làm thay đổi nonce policy của AES-GCM.** Nếu dùng cùng DEK cho nhiều bản mã, phải bảo đảm **không trùng cặp (key, nonce)** theo hạn mức. Nếu đổi DEK, cần gắn metadata cho đúng key version và kiểm tra khả năng khôi phục bản mã cũ.

### Tách quyền KMS và quyền nghiệp vụ

KMS có thể cấp cho workload quyền `Wrap/Unwrap`, nhưng ứng dụng phải kiểm tra **đúng tenant, resource, operation**. Ngược lại, một bản ghi inventory ghi `ACTIVE` không tự cấp cho workload quyền sử dụng HSM. Cả **KMS policy** lẫn **application authorization** cần hợp lệ ở thời điểm thực thi.

## 13. Audit activation time và cảnh báo cần có

Một key inventory tốt có thể trả lời: **ai đã lên lịch, ai phê duyệt, khóa được kích hoạt thực tế khi nào, trạng thái các node ra sao và các request đầu tiên dùng phiên bản mới vào thời điểm nào**.

### 13.1. Sự kiện audit mẫu

~~~json
{
  "eventType": "KEY_ACTIVATED",
  "keyId": "billing-kek",
  "keyVersion": "v3",
  "scheduledActivationAt": "2026-12-01T00:00:00Z",
  "actualActivatedAt": "2026-12-01T00:00:02Z",
  "previousState": "PRE_ACTIVE",
  "currentState": "ACTIVE",
  "primaryForNewUse": true,
  "policyRevision": 18,
  "actor": "approved-activation-controller",
  "approvalRef": "KEY-ROTATION-42",
  "result": "SUCCESS"
}
~~~

Sự kiện minh họa **không chứa key material**. Trong hệ thống thật, audit phải có **integrity, quyền truy cập, correlation/request ID và retention policy**, đồng thời xác thực event đến từ controller được ủy quyền.

### 13.2. Những cảnh báo nên giám sát

| Cảnh báo | Ý nghĩa |
| --- | --- |
| **Activation overdue** | Đã đến `activationAt` nhưng key vẫn `PRE_ACTIVE` hoặc KMS chưa cho phép |
| **Early use detected** | Có thao tác `Encrypt/Wrap/Sign` trước activation |
| **Wrong primary version** | Request mới còn dùng key version cũ sau thời điểm chuyển |
| **Policy revision mismatch** | Node/cache hoặc registry lệch revision |
| **KMS state mismatch** | Inventory ACTIVE nhưng KMS Disabled; hoặc ngược lại |
| **Missing replacement** | Key sắp hết new-use period mà chưa có successor sẵn sàng |
| **Unexpected key use** | Principal/tenant không được cấp quyền vẫn gọi thao tác |
| **Nonce/usage limit** | Lượng dùng hoặc nonce sắp chạm giới hạn của thuật toán |
| **Backup dependency** | Key chuẩn bị destroy trong khi backup còn cần version cũ |

**Không log raw DEK/KEK, private key, PSK, traffic secret, plaintext, password hoặc access token** để chứng minh activation. Chỉ log **metadata cần thiết** như key ID/version, actor, timestamp, operation, verdict và policy revision.

## 14. Tình huống thực tế: kích hoạt khóa ký hóa đơn theo lịch

Một nền tảng hóa đơn cần chuyển private signing key từ `invoice-signing-v8` sang `invoice-signing-v9` đúng **00:00 UTC ngày 01/12/2026**, đồng thời giữ khả năng xác minh hóa đơn cũ.

### Giai đoạn A — Trước activation

1. Nhóm bảo mật sinh `v9` trong HSM theo thuật toán được phê duyệt.
2. Public key/chứng thư `v9` được đăng ký trong registry có **binding issuer → key** và được phân phối tới verifier qua kênh tin cậy.
3. Inventory ghi `activationAt = 2026-12-01T00:00:00Z` và chính sách `SIGN_NEW`; private key vẫn **pre-active**.
4. Các verifier kiểm tra họ có thể đọc phiên bản mới và biết thuật toán phù hợp, nhưng chưa coi key là được phép ký mới trước thời điểm policy.
5. Nhóm triển khai diễn tập đồng hồ, rollback, kiểm tra HSM `Sign` permission và canary.

### Giai đoạn B — Đúng activation

1. Controller dựa trên nguồn thời gian đáng tin xác minh đã tới mốc và phê duyệt chưa thay đổi.
2. Chính sách chuyển `v9` sang **Active** và trở thành **primary** cho thao tác `Sign` mới.
3. `v8` được đưa ra khỏi originator-usage period. Nếu HSM không hỗ trợ cấp quyền riêng cho từng thao tác/phiên bản, cần cơ chế enforce khác phù hợp.
4. Audit ghi scheduled và actual activation, key version, policy revision; hệ thống kiểm thử chữ ký mới với key được trust.

### Giai đoạn C — Sau activation

- Hóa đơn phát hành mới ký bằng `v9`.
- Hóa đơn cũ ký bằng `v8` được xác minh theo policy tin cậy lịch sử, có thể cần **trusted timestamp** và bằng chứng chứng thư.
- Nếu một node vẫn ký bằng `v8` sau mốc ngừng ký mới, đó là sự cố policy/consistency, không phải lý do tự nhận hóa đơn vẫn hợp lệ.
- Nếu private key `v8` bị lộ, thực hiện **revocation/incident response** riêng; không coi rotation định kỳ đã xóa mọi rủi ro.

### Sự cố: hệ thống ở nhiều múi giờ

Một service tại Việt Nam đọc sai `2026-12-01T00:00:00Z` thành **00:00 giờ địa phương**, bắt đầu ký **sớm 7 giờ** so với lịch UTC. Nguyên nhân là dùng `LocalDateTime` không có timezone.

**Cách xử lý:** lưu `Instant` UTC, quy định UI hiển thị cùng timezone và kiểm tra timestamp từ nguồn trung tâm; không dựa vào quy ước ngầm của từng service. Nếu cần kích hoạt theo **00:00 tại một địa phương**, chuyển từ `ZonedDateTime` sang `Instant` một cách có chủ đích rồi mới phát hành policy.

## 15. Sai lầm thường gặp

| Sai lầm | Rủi ro | Cách khắc phục |
| --- | --- | --- |
| Coi `createdAt` bằng `activationAt` | Dùng key ngay sau khi sinh dù chưa phê duyệt | Tách thời điểm tạo, cấp phát, dự kiến kích hoạt và kích hoạt thực tế |
| Chỉ kiểm tra `now >= activationAt` | Key pre-active/suspended/compromised vẫn bị dùng | Kiểm tra thêm state, usage, IAM, trust và policy |
| Chỉ kiểm tra `state = ACTIVE` | Có thể dùng key trước mốc hoặc quá cryptoperiod | Kết hợp ranh giới thời gian và operation-level authorization |
| Lưu giờ địa phương mà không có zone | Node ở vùng khác kích hoạt sớm/trễ | Dùng `Instant` UTC và quy tắc chuyển timezone rõ |
| Đổi alias primary trước khi kiểm tra readiness | Client chưa có key/cert mới, request lỗi | Preflight, phân phối trước, canary và commit có kiểm soát |
| Dùng alias primary để giải mã mọi bản mã cũ | Chọn sai key version | Lưu key reference/version trên payload |
| Chỉ đổi trạng thái trong inventory | KMS/HSM hoặc client vẫn có state khác | Reconcile với KMS, signer, policy cache và các vùng |
| Không chặn stale cache/TOCTOU | Node vẫn dùng key cũ quá hạn hoặc sau revoke | Versioned policy và enforcement gần nơi dùng |
| Tự nới thời gian một cách âm thầm | Có thể làm sai phạm vi hiệu lực khóa | Chính sách clock skew/grace được phê duyệt, audit |
| Gắn `firstUsedAt` làm activation | Nhầm sự kiện sử dụng với mốc được phép | Lưu cả planned activation và actual first use |
| Tin `certificate.notBefore` thay key policy | Bỏ qua signer IAM, trust binding, cryptoperiod | Kiểm tra đồng thời certificate và key lifecycle |
| Sau activation xóa key cũ ngay | Không thể decrypt/unwrap backup hoặc verify lịch sử | Giữ recipient policy, rewrap/re-encrypt và kiểm tra retention |
| Nghe thấy `ACTIVE` nên dùng key cho mọi purpose | Cross-purpose key misuse | Tách `SIGN/WRAP/DECRYPT` và least privilege |
| Backdate `activationAt` sau khi có sự cố | Làm sai audit và lịch sử tin cậy | Ghi lịch sử bất biến, quy trình sửa có phê duyệt |
| Nâng version nhưng không đổi key material thực sự | Không giải quyết được khóa cũ bị lộ | Rotation đúng vật liệu và kế hoạch incident response |
| Không chuẩn bị khóa successor trước hạn | Hết new-use period gây gián đoạn | Cảnh báo sớm, readiness và diễn tập chuyển đổi |

## 16. Checklist triển khai Activation time

- [ ] Key inventory phân biệt **key ID, version, alias, owner, tenant, environment, purpose**?
- [ ] Có `createdAt`, `provisionedAt`, **`activationAt`**, `actualActivatedAt`, `newUseUntil`, `oldUseUntil` khi cần?
- [ ] Đã xác định `activationAt` là **scheduled effective time**, không nhầm với lần sử dụng đầu?
- [ ] Timestamp lưu bằng `Instant`/UTC có định dạng và độ chính xác thống nhất?
- [ ] Có quy định rõ **`[activationAt, newUseUntil)`** cho thao tác tạo bảo vệ mới?
- [ ] State và policy **deny by default** nếu pre-active, suspended, revoked hoặc compromised?
- [ ] Đã xác thực key material, thuật toán, key usage, IAM và ownership trước khi kích hoạt?
- [ ] Activation cần đúng approval và lưu `policyRevision` để chống rollback?
- [ ] Có key successor, kế hoạch phân phối public key/cert/JWKS hoặc PSK khi cần?
- [ ] Hệ thống phân biệt **active** với **primary for new use**?
- [ ] Payload cũ giữ đúng key ID/version, nonce/tag và metadata để đọc/restore?
- [ ] KMS/HSM state và inventory state có quy trình reconcile, không suy diễn API?
- [ ] Có giới hạn clock skew, cache stale, event retry và TOCTOU ở các node?
- [ ] Negative tests bao gồm **trước activation, đúng boundary, sau new-use, wrong state, revoked và sai purpose**?
- [ ] Rotation có cửa sổ xử lý dữ liệu cũ, kiểm thử backup, rewrap/re-encrypt và retention?
- [ ] Audit ghi **scheduled vs actual activation, actor, approval, key version, operation và policy revision** mà không lộ secret?
- [ ] Có cảnh báo activation overdue, early use, alias stale, key successor missing và usage limits?

## 17. Câu hỏi tự kiểm tra

**1. Activation time có phải là thời điểm sinh khóa không?**  
Không. Khóa có thể được tạo và cấp phát trước đó; activation là mốc sớm nhất policy cho phép bắt đầu sử dụng trong phạm vi đã định.

**2. Nếu tới `activationAt` nhưng khóa vẫn `PRE_ACTIVE`, có thể dùng để ký không?**  
Không. Timestamp không tự cấp quyền. Phải đạt đủ state, approval, usage, IAM và trust policy.

**3. Sự khác biệt giữa `activationAt`, `activatedAt` và `firstUsedAt`?**  
`activationAt` là thời điểm hiệu lực dự kiến; `activatedAt` là sự kiện kích hoạt thành công thực tế; `firstUsedAt` là lần sử dụng thực tế đầu tiên. Ba thời điểm có thể khác nhau.

**4. Vì sao giữ `oldUseUntil` sau `newUseUntil`?**  
Vì sau khi ngừng mã hóa/wrap mới, vẫn có thể cần decrypt/unwrap bản ghi cũ hoặc xử lý backup. Việc cho phép cụ thể phụ thuộc policy và KMS.

**5. Chứng thư có `notBefore` hôm nay nghĩa là private key đã được phép `Sign` chưa?**  
Chưa chắc. PKI validity, key activation state, signer IAM, mục đích khóa và quyền nghiệp vụ là các điều kiện riêng.

**6. Khi đổi primary alias sang `v2`, có nên dùng `v2` để giải mã mọi ciphertext cũ không?**  
Không. Dữ liệu cần giữ key ID/version tương ứng và sử dụng đúng phiên bản hoặc cơ chế versioning an toàn của provider.

**7. Một node ở timezone UTC+07 có thể dùng `LocalDateTime` từ chuỗi UTC để lên lịch không?**  
Không nên. Cần parse mốc `Z` thành `Instant`, hoặc chuyển rõ từ timezone kinh doanh sang Instant trước khi lưu.

**8. Tại sao `activationAt` không chứng minh được chữ ký số được tạo đúng thời điểm đó?**  
Vì đó là metadata chính sách. Để xác minh thời điểm tạo chữ ký lịch sử có thể cần trusted timestamp và chứng cứ độc lập, không chỉ một trường thời gian do signer khai báo.

**9. Nếu key bị lộ trước activation, có nên chờ đến activation để revoke không?**  
Không. Phải chặn và xử lý sự cố ngay theo mức rủi ro, không cho nó được kích hoạt chỉ vì lịch đã định.

**10. Kiểm tra `activationAt` trong Java có đủ thay KMS/HSM enforcement không?**  
Không. Cần kiểm soát tại điểm dùng khóa, IAM, authorization theo tenant, chính sách cache/TOCTOU và trạng thái thực tế của KMS/HSM.

## Ghi nhớ

**Activation time là thời điểm sớm nhất mà một key version có thể được phép sử dụng theo chính sách — không phải thời điểm tạo khóa, bằng chứng đã kích hoạt thực tế hay quyền dùng vô điều kiện.** Key inventory cần lưu **key ID/version, purpose, state, activationAt, cryptoperiod, trạng thái thu hồi, owner, policy revision và bằng chứng audit**. Trong hệ thống phân tán, phải giải quyết **UTC/clock skew, scheduler, alias/primary, KMS/HSM state, stale cache và TOCTOU**. Khi rotation, tách quyền **encrypt/wrap/sign mới** khỏi **decrypt/unwrap/verify dữ liệu cũ**, không xóa key khi backup còn phụ thuộc và không tin key bị compromise. Liên kết activation với **mật mã đối xứng, bất đối xứng, chữ ký số, DEK/KEK, envelope encryption, IAM, audit và toàn bộ key lifecycle** giúp việc dùng khóa đúng thời điểm trở thành một bảo đảm có thể kiểm tra, thay vì chỉ là một ô ngày giờ trong inventory.

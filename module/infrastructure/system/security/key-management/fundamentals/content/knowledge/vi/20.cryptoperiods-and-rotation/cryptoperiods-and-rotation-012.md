# Giữ key cũ để decrypt dữ liệu cũ

> **Chương:** Cryptoperiod và rotation  
> **Module:** SECURITY_KEY_MANAGEMENT_FUNDAMENTALS — Nền tảng quản lý khóa mật mã

## 1. Vì sao phải giữ key cũ sau khi rotation?

Trong một hệ thống đã mã hóa dữ liệu, **thay khóa dùng cho dữ liệu mới không làm các ciphertext cũ tự chuyển sang khóa mới**. Ciphertext được tạo bằng vật liệu khóa nào thì việc giải mã, trực tiếp hoặc qua các tầng khóa bọc, vẫn cần **đúng vật liệu và ngữ cảnh mật mã** tương ứng.

**Giữ key cũ để decrypt dữ liệu cũ** là chiến lược quản lý vòng đời theo đó key version cũ **ngừng được chọn để bảo vệ dữ liệu mới** nhưng vẫn được **lưu giữ an toàn, cấp quyền sử dụng có giới hạn và giám sát** để đọc dữ liệu đã mã hóa trước đó. Tùy loại khóa, thao tác lịch sử có thể là **Decrypt**, **Unwrap**, **Verify** hoặc một operation tương đương; không nên đánh đồng các thao tác ấy.

Ví dụ: dịch vụ hóa đơn mã hóa 2 triệu bản ghi bằng các **DEK** được bảo vệ bởi **KEK** `billing-kek/v4`. Ngày 01/03/2027, hệ thống chuyển sang `billing-kek/v5` để bọc DEK mới. Các bản ghi cũ vẫn có `wrappedDek` dưới `v4`. Nếu xóa `v4` ngay mà chưa rewrap, ứng dụng có thể **không còn mở được DEK** và do đó **không còn giải mã được bản ghi**, kể cả khi ciphertext và database backup vẫn nguyên vẹn.

Ngược lại, giữ key cũ **mãi mãi với quyền Encrypt/Decrypt rộng cho mọi service** sẽ làm tăng cơ hội lạm dụng và khiến việc rotation hầu như mất ý nghĩa. Mục tiêu đúng là **duy trì khả năng đọc dữ liệu hợp lệ trong một thời kỳ được quản trị**, đồng thời **chặn use mới, hạn chế quyền, kiểm kê phụ thuộc và có kế hoạch kết thúc**.

### Mục tiêu học tập

Sau bài này, bạn sẽ:

- Phân biệt **originator-usage period** và **recipient-usage period** trong cryptoperiod.
- Thiết kế **old-key decrypt-only/unwrap-only policy**, hiểu khác biệt giữa policy của ứng dụng và trạng thái thực của KMS/HSM.
- Lưu **key ID/version**, thuật toán, nonce/tag, AAD và wrapped DEK để định tuyến đúng key lịch sử.
- Hiểu hai phương án **giữ key cũ có kiểm soát** và **di chuyển dữ liệu sang key mới**; phân biệt **rewrap** với **re-encrypt**.
- Kiểm tra dependency ở **database, backup, snapshot, CDC, archive, DR** trước khi retire/destroy.
- Xử lý **key compromise, KMS outage, revoked key, expired recipient period, tenant authorization**.
- Vận dụng ví dụ **Java 17**, sơ đồ, checklist và câu hỏi tự kiểm tra.

## 2. Hai thời kỳ sử dụng của một key version

**Cryptoperiod** mô tả khoảng mà một khóa được phép sử dụng cho các operation xác định. Cách chia thường dùng trong quản lý khóa gồm:

1. **Originator-usage period:** được dùng khóa để **tạo bảo vệ mật mã mới**, như Encrypt, Wrap, tạo MAC hoặc Sign mới.
2. **Recipient-usage period:** được dùng khóa để **xử lý thông tin đã được bảo vệ từ trước**, như Decrypt, Unwrap hoặc Verify khi chính sách/loại khóa cho phép.

Ví dụ KEK `orders-kek/v4`:

| Mốc UTC minh họa | Trạng thái nghiệp vụ | `WRAP_NEW` | `UNWRAP_OLD` |
| --- | --- | --- | --- |
| Trước 01/12/2026 | PRE_ACTIVE | Cấm | Cấm |
| 01/12/2026 – trước 01/03/2027 | ACTIVE | Cho phép theo IAM và usage limits | Cho phép theo IAM |
| 01/03/2027 – trước 01/09/2027 | RETIRED_FOR_NEW_USE | **Cấm** | Có thể cho phép có kiểm soát |
| Từ 01/09/2027 | OLD_USE_ENDED | Cấm | Cấm nếu không có quy trình ngoại lệ hợp lệ |
| Bất kỳ lúc nào bị xác nhận compromised | COMPROMISED | Cấm | Không mặc nhiên được tiếp tục |

Các ngày chỉ là **ví dụ thiết kế**, không phải quy định “KEK phải rotate mỗi 90 ngày”. Thời kỳ thực tế phải xét thuật toán, lượng sử dụng, dữ liệu phải lưu, rủi ro và chính sách tổ chức.

### 2.1. Khoảng thời gian nửa mở

Một quy ước dễ kiểm tra:

\[
\operatorname{newUseAllowed}(t) \Rightarrow
  activationAt \le t < newUseUntil
\]

\[
\operatorname{oldUseAllowed}(t) \Rightarrow
  activationAt \le t < oldUseUntil
\]

Dấu \(\Rightarrow\) nhấn mạnh **đây chỉ là điều kiện cần theo thời gian**, không đủ để cho phép thực thi. Còn phải kiểm tra **key state, quyền principal, tenant/resource, operation, provider state, cryptographic usage limit và compromise status**.

Tại đúng `newUseUntil`, khóa cũ đã **không được dùng để mã hóa/wrap mới**. Tại đúng `oldUseUntil`, old-use bị chặn theo quy ước nếu chưa có quyết định được phê duyệt khác.

### 2.2. Tại sao `createdAt` khác `activationAt`?

Một KEK có thể được sinh trước thời điểm rollout, lưu trong KMS/HSM dưới trạng thái **PRE_ACTIVE** để kiểm thử quyền và khả năng restore. Nó chưa được phép bảo vệ bản ghi mới chỉ vì key material đã tồn tại.

**Không tự tính cryptoperiod bằng `createdAt + 90 ngày`** nếu chính sách định nghĩa thời gian từ `activationAt` hoặc một sự kiện khác.

### 2.3. Hết thời kỳ dùng mới khác key destruction

**Retirement** có thể chỉ ngừng `Encrypt/Wrap/Sign` mới. **Destruction** làm mất key material theo semantics provider, có thể không thể đảo ngược. **Revocation** là rút quyền/niềm tin do sự cố hoặc chính sách. Ba hành động này **không đồng nghĩa**.

## 3. Sơ đồ giữ key cũ và chuyển primary key

~~~mermaid
flowchart TD
    Owner[Key owner phê duyệt cryptoperiod/rotation] --> NewKey[Tạo KEK v5 trong KMS/HSM]
    NewKey --> Prepare[PRE_ACTIVE: IAM + backup/DR + canary]
    Prepare --> Cutover[Chuyển primary cho WRAP_NEW sang v5]
    Cutover --> NewWrite[Ciphertext mới: DEK được wrap dưới v5]
    Cutover --> OldRead[Ciphertext cũ: wrapped DEK dưới v4]
    OldRead --> OldPolicy[Kiểm tra quyền read + UNWRAP_OLD v4]
    OldPolicy --> OldKek[KEK v4 còn được giữ trong vùng an toàn]
    OldKek --> DecryptOld[Unwrap DEK + AEAD Decrypt dữ liệu cũ]
    OldRead --> Migration[Background rewrap/re-encrypt khi phù hợp]
    Migration --> Backup[Quét backup/archives/DR và thử restore]
    Backup --> Ready{Còn dependency v4?}
    Ready -->|Có| OldPolicy
    Ready -->|Không| Retire[Đóng old use và destroy theo approval]
~~~

**Không phải mọi hệ thống sẽ giữ `v4` trực tuyến.** Có hệ thống chuyển key cũ vào vùng lưu trữ/khôi phục được kiểm soát, chỉ cấp quyền unwrap cho migration hoặc DR. Quyết định dựa trên SLA đọc dữ liệu cũ, rủi ro và tính năng cụ thể của KMS/HSM.

### 3.1. Primary key khác key version cũ

Một alias như `current` hoặc `primary` thường phục vụ **chọn vật liệu cho dữ liệu mới**. Nó không phải đủ thông tin để mở tất cả bản mã lịch sử. Khi alias chuyển từ `v4` sang `v5`, một record có `wrappedDek` dưới `v4` vẫn cần được định tuyến tới `v4` hoặc một provider ciphertext blob có version binding theo thiết kế nhà cung cấp.

### 3.2. Có thể giữ key cũ để decrypt mà không cho encrypt mới không?

**Có, nếu kiến trúc và cơ chế cấp quyền thực thi được điều đó.** Ở tầng ứng dụng/key broker có thể cấm chọn key `v4` cho write path, chỉ cho read path dùng key version từ ciphertext. Nhưng điều này **không tự đảm bảo direct KMS calls bị chặn**. Cần kiểm tra IAM/grants/provider-specific operation controls hoặc thu hẹp principal, giám sát bypass.

### 3.3. Không giả định `Disabled` của KMS là `DecryptOnly`

Ở nhiều KMS, khi một key **Disabled**, cả `Encrypt` lẫn `Decrypt` hoặc `Wrap` và `Unwrap` đều có thể bị từ chối. **Trạng thái `RETIRED_FOR_NEW_USE` trong inventory không đồng nhất với trạng thái `Disabled` của provider**. Nếu cần decrypt dữ liệu cũ, phải thiết kế chính sách hoạt động phù hợp với **API và key states nhà cung cấp thật**.

## 4. Những đối tượng có thể cần giữ key cũ

| Key class | Dữ liệu/đối tượng lịch sử | Operation có thể cần tiếp tục | Điều phải kiểm tra |
| --- | --- | --- | --- |
| **DEK đối xứng** | Ciphertext bản ghi/file | `DECRYPT_OLD` | Đúng DEK, AEAD tag, nonce/AAD, usage period |
| **KEK / wrapping key** | DEK đã bọc, backup key objects | `UNWRAP_OLD` | Wrapped blob, exact KEK version, provider, permissions |
| **Private asymmetric decryption key** | Dữ liệu hoặc DEK đã mã hóa tới public key cũ | `DECRYPT_OLD` | Key transport scheme, certificate/key binding, custody |
| **Private signing key** | Chữ ký cũ | **Không cần** private key để verify; có thể retire/hủy sau khi xét policy | Public key/chứng thư/trust validation history |
| **Public verification key** | Chữ ký số/JWT cũ | `VERIFY_OLD` | `kid`, certificate/issuer/audience/revocation, timestamp |
| **HMAC/PSK dùng xác thực** | MAC/token cũ hoặc giao thức cũ | `VERIFY_OLD` / protocol-specific use | Token TTL, replay, key ID, compromise |
| **Session traffic key** | Gói của phiên đang hoạt động | Decrypt theo đúng session/epoch | Protocol limits, sequence/rekey, không archive tùy tiện |

**Tiêu đề bài nói “decrypt dữ liệu cũ” theo nghĩa nghiệp vụ**, nhưng kỹ thuật chính xác khác theo key class: với KEK là **unwrap DEK**, với chữ ký là **verify bằng public key**, không phải “giải mã chữ ký bằng private key”.

### 4.1. DEK cũ và KEK cũ có thể độc lập

Một DEK `D1` có thể mã hóa một bản ghi duy nhất rồi không bao giờ encrypt thêm. Khi KEK `K4` hết new-use, ứng dụng có thể **rewrap D1 dưới KEK `K5`** mà không thay D1 hoặc ciphertext. Sau khi mọi dependent wrapped DEK, backup và archives được xử lý, có thể không cần giữ `K4` trực tuyến.

### 4.2. Key material có thể đã tồn tại ngoài KMS

Nếu một raw DEK/KEK từng được export, ghi log, đưa vào heap dump, backup VM hoặc trao cho recipient, việc xóa một key version trong KMS **không thu hồi được mọi bản sao**. Đánh giá cryptographic erasure và compromise cần xét toàn bộ đường dữ liệu.

## 5. Dữ liệu cũ phải mang đủ thông tin định tuyến khóa

Một ciphertext được giải mã ổn định trong nhiều năm cần có một **envelope format** hoặc metadata bên ngoài có thể định tuyến đúng vật liệu và thuật toán. Không lưu một tên `activeKey` có thể thay đổi mà quên version.

### 5.1. Ví dụ schema record

~~~json
{
  "formatVersion": 2,
  "tenantId": "tenant-42",
  "recordId": "invoice-000812",
  "dataAlgorithm": "AES-256-GCM",
  "nonceB64": "<12-byte-nonce-encoded>",
  "ciphertextAndTagB64": "<ciphertext-and-authentication-tag>",
  "keyScope": "PER_RECORD",
  "wrappedDekB64": "<wrapped-dek>",
  "wrappingMechanism": "KMS_PROVIDER_BLOB",
  "kekKeyId": "billing-kek",
  "kekVersion": "v4",
  "kekProviderRef": "kms://example/billing-kek/v4",
  "aadContextVersion": 1,
  "recordRevision": 7,
  "encryptedAt": "2026-12-21T06:00:00Z"
}
~~~

Đây là **JSON minh họa**; `kms://example/...` và chuỗi trong dấu nhọn là placeholder, **không phải dữ liệu có thể giải mã**. KMS thật có thể dùng ciphertext blob chứa metadata phiên bản riêng; khi đó cần hiểu semantics provider và đảm bảo blob còn có thể unwrap với key cũ.

| Trường | Tại sao cần? |
| --- | --- |
| `formatVersion` | Chọn decoder cũ đã được cho phép |
| `dataAlgorithm` | Dùng đúng AEAD/mode, tránh downgrade |
| `nonce`, `tag` | Xác minh tính toàn vẹn và giải mã AES-GCM |
| `wrappedDek` | Khôi phục DEK từ lớp KEK |
| `kekKeyId/version` | Định tuyến tới **đúng vật liệu KEK cũ** |
| `tenantId/recordId` | Gắn ngữ cảnh AAD và resource authorization |
| `aadContextVersion` | Tái lập đúng AAD của dữ liệu lịch sử |
| `recordRevision` | Kiểm soát update concurrency, không tự chống rollback mật mã |

### 5.2. Metadata có thể không hoàn toàn đáng tin

Database, queue hoặc blob store có thể bị sửa. Không tự tin vào `tenantId`, `keyVersion`, `algorithm` từ untrusted record rồi bỏ qua chính sách. Ứng dụng phải:

- Lấy **tenant/resource identity** từ nguồn quyền đáng tin và đối chiếu record.
- Chỉ cho phép **algorithm/profile và format versions đã duyệt**.
- Kiểm tra key reference thuộc đúng tenant/purpose.
- Reconstruct **AAD đúng byte** đã dùng khi encrypt, rồi verify tag.
- Không thử qua nhiều KEK/thuật toán tùy tiện khi unwrap lỗi để “tìm một key giải được”.

### 5.3. AAD thay đổi khi chuyển record?

Nếu AAD gắn `tenantId` và `recordId`, đổi hai giá trị này mà giữ nguyên ciphertext/tag làm **authentication thất bại**. Chuyển tenant hoặc đổi record ID thường cần **authorized re-encrypt với context mới**; chỉ rewrap DEK bằng KEK khác không tự sửa data AAD.

### 5.4. Integrity không tự chống rollback nguyên bản ghi

AEAD phát hiện thay đổi byte nhưng một attacker thay **toàn bộ record bằng một phiên bản cũ hợp lệ cùng AAD** có thể vẫn qua tag check. Nếu chống rollback là yêu cầu, cần **counter/revision hoặc log bất biến nằm ngoài miền attacker kiểm soát**, không chỉ một cột `recordRevision` trong cùng database.

## 6. Luồng đọc dữ liệu cũ sau khi đã xoay vòng khóa

~~~mermaid
sequenceDiagram
    participant Caller as Caller
    participant App as Data service
    participant Auth as Resource/IAM policy
    participant DB as Database
    participant Broker as Cryptoperiod + key broker
    participant KMS as KMS/HSM
    Caller->>App: Đọc invoice thuộc tenant A
    App->>Auth: Kiểm tra caller, tenant, record, purpose
    Auth-->>App: Permit / deny
    App->>DB: SELECT tenant + record ID
    DB-->>App: Ciphertext + nonce/tag + wrapped DEK + KEK v4
    App->>Broker: Request UNWRAP_OLD v4, verified context
    Broker->>Broker: State, oldUseUntil, IAM, owner/purpose, usage
    Broker->>KMS: Unwrap theo đúng key version và policy
    KMS-->>Broker: DEK tạm thời hoặc protected operation
    Broker-->>App: DEK/operation result theo API được duyệt
    App->>App: AEAD decrypt + verify tag/AAD
    App-->>Caller: Chỉ plaintext được phép xem
~~~

### 6.1. Authorization trước decrypt

**KMS cho phép unwrap không có nghĩa user được đọc dữ liệu**. Một service có quyền `Unwrap` nhiều DEK không được nhận blob tùy ý từ client rồi giải mã hộ. Trước khi gọi KMS, phải xác minh **caller → tenant → record → purpose/field**.

### 6.2. Định tuyến theo key version, không theo key hiện hành

Reader dùng `kekVersion=v4` có trong record đã xác minh, **không thay bằng alias `current=v5`**. Nếu version không còn tồn tại hoặc bị revoke, xử lý lỗi có kiểm soát; không tự fallback sang file plaintext/raw KEK.

### 6.3. Xử lý lỗi cũ khác lỗi authorization

Các lỗi như **không tìm thấy key version, KMS disabled, old-use period hết, AEAD tag sai, caller không có quyền** cần được phân loại trong audit/monitoring. Client bên ngoài không nhất thiết cần biết mọi nguyên nhân kỹ thuật chi tiết, vì chúng có thể trở thành **oracle** về key ID hoặc dữ liệu của tenant khác.

### 6.4. Giữ raw DEK trong memory càng ngắn càng tốt

Khi KMS trả plaintext DEK, nó có thể hiện diện trong RAM ứng dụng. Dùng DEK chỉ trong phạm vi cần thiết, tránh copy vào distributed cache/log/crash report, dùng best-effort cleanup và giảm TTL. **Không thể bảo đảm xóa mọi bản sao `SecretKey` trong Java heap/native provider**, do đó key material ở application memory là phần phải tính trong threat model.

## 7. Giữ key cũ ở KMS/HSM như thế nào?

Có nhiều lựa chọn, không có một trạng thái “old-decrypt-only” áp dụng cho mọi sản phẩm.

| Phương án | Cách hoạt động | Hạn chế |
| --- | --- | --- |
| **Giữ key version cũ active ở provider, chỉ deny new-use trong broker** | Reader được unwrap lịch sử, writer luôn dùng version mới | Direct provider credential có thể bypass broker nếu IAM không khóa |
| **Provider grants/policies theo operation** | Tách quyền `Wrap` mới và `Unwrap` cũ nếu API hỗ trợ | Semantics khác vendor; cấu hình sai có thể chặn cả hai hoặc mở rộng quyền |
| **Dedicated read/migration principal** | Chỉ dịch vụ đọc hoặc migration có quyền dùng key cũ | Rủi ro principal bị chiếm, cần scope/TTL/monitoring |
| **Controlled archival/recovery path** | Key cũ chỉ được khôi phục khi có yêu cầu lịch sử/DR | Latency và availability; restore/quorum phải được kiểm chứng |
| **Rewrap toàn bộ DEK sang KEK mới** | Giảm phụ thuộc key cũ khi DEK còn đáng tin | Phải xử lý backup/archive, concurrency và tính toàn vẹn |
| **Re-encrypt bằng DEK mới** | Loại bỏ phụ thuộc DEK cũ khỏi dữ liệu mới | Tốn I/O/CPU, cần plaintext tạm và kiểm soát migration |

### 7.1. Provider state không phải policy state

Một KMS có thể cung cấp các trạng thái như `Enabled`, `Disabled`, `PendingDeletion` nhưng **không cung cấp `RETIRED_BUT_DECRYPT_ONLY`**. Nếu key bị Disabled và provider từ chối mọi operation, nghiệp vụ không thể đọc dữ liệu cũ chỉ nhờ một flag `allowDecryptOld=true` trong inventory.

**Phải kiểm thử thực tế** trong môi trường được duyệt: key cũ ở trạng thái dự kiến có unwrap được không? Quyền nào có thể gọi wrap? Ai có thể cấp lại `Encrypt` permission hoặc sửa key policy?

### 7.2. KMS/HSM non-extractable không đồng nghĩa hết nguy cơ

KEK không xuất raw bytes vẫn có thể bị lạm dụng qua API `Decrypt/Unwrap` khi service principal bị chiếm. Vì vậy, giữ key cũ là giữ **khả năng mật mã nhạy cảm**, cần IAM least privilege, tenant/purpose checks, quotas, audit và incident response.

### 7.3. Archive không đồng nghĩa xóa

Nếu old KEK được chuyển sang kho lưu trữ/backup được bảo vệ, tổ chức vẫn cần biết **khả năng khôi phục, custody, recovery approval, retention và effective exposure**. Đừng ghi `DESTROYED` trong inventory khi chỉ có `ARCHIVED` hoặc `DISABLED`.

## 8. Quy tắc “decrypt-only” không phải cho phép vô điều kiện

**Decrypt-only** trong bài là nhãn chính sách nghiệp vụ: cấm tạo bảo vệ mới bằng key cũ, chỉ cho phép thao tác lịch sử khi **đúng key version, quyền, dữ liệu, thời gian và provider state**.

### 8.1. Ma trận operation

| Key state nghiệp vụ | Encrypt/Wrap mới | Decrypt/Unwrap lịch sử | Export raw key | Destroy |
| --- | --- | --- | --- | --- |
| PRE_ACTIVE | Từ chối | Từ chối | Theo policy riêng; thường từ chối | Chỉ quy trình có quyền |
| ACTIVE | Có thể cho phép | Có thể cho phép | Không được suy từ ACTIVE | Chỉ workflow nhạy cảm |
| RETIRED_FOR_NEW_USE | **Từ chối** | Có thể, đến `oldUseUntil` | **Không** vì đã retire | Chỉ sau dependency preflight |
| SUSPENDED | Từ chối | Thường từ chối/chờ điều tra | Từ chối | Không tự hủy vì sự cố |
| COMPROMISED/REVOKED | Từ chối | **Không tự cho phép** | Từ chối | Theo incident/recovery runbook |
| DESTROYED | Không thể | Không thể | Không thể | Đã kết thúc |

**Ma trận là policy ví dụ**, không phải quy định thống nhất của mọi KMS. Cần xét ảnh hưởng lên backup/recovery khi `COMPROMISED` vì ở thời điểm sự cố có thể phải cô lập key trước rồi mới quyết định xử lý dữ liệu.

### 8.2. Tại sao không cho phép writer chọn key version cũ?

Nếu client chỉ định `kekVersion=v4` trong request, một writer lỗi hoặc attacker có thể tạo **nhiều ciphertext mới bị bọc dưới key đã hết originator period**. Write path phải chọn key mới từ **trusted primary-key registry/broker** và từ chối version cũ, không dựa vào alias/key ID do caller tự khai.

### 8.3. Tại sao không cho phép reader dùng mọi key cũ?

Reader chỉ nên được phép dùng **key/version mà ciphertext thật sự cần** và thuộc đúng tenant/resource. Không cho service dò tất cả key versions rồi trả kết quả thành công đầu tiên, vì có thể gây cross-tenant access, key-confusion và chi phí KMS lớn.

## 9. Giữ key cũ bao lâu là đủ?

Không có một mốc cố định cho mọi loại dữ liệu. Cần cân bằng **data retention, required historical access, mức rủi ro, migration capacity, backup lifecycle và legal holds**.

### 9.1. Những câu hỏi quyết định `oldUseUntil`

1. Còn bao nhiêu ciphertext/wrapped DEK đang phụ thuộc key này?
2. Dữ liệu có cần đọc hàng ngày, ít khi đọc hay chỉ khi điều tra/DR?
3. Bản backup/snapshot/archival có tồn tại lâu hơn database chính không?
4. Có thể **rewrap** DEK hoặc **re-encrypt** dữ liệu trước mốc đó không?
5. Dữ liệu có **legal hold/retention** hoặc yêu cầu xác minh lịch sử không?
6. Key có dấu hiệu compromise, thuật toán/provider bị suy yếu không?
7. Chi phí và rủi ro của việc giữ khả năng `Unwrap/Decrypt` thêm một khoảng là bao nhiêu?

### 9.2. Thời hạn của key khác thời hạn của dữ liệu

Hồ sơ có thể phải lưu **7 năm**, còn KEK chỉ được dùng **Wrap New trong vài tháng** theo chính sách giả định. Nếu thực hiện rewrap đều đặn, dữ liệu cũ có thể tiếp tục đọc qua KEK phiên bản mới mà không giữ mọi KEK cũ trực tuyến suốt 7 năm.

### 9.3. Đừng gia hạn `oldUseUntil` tự động vô hạn

Nếu migration chưa xong, không nên tự chỉnh ngày rồi coi đó là việc thường lệ. Cần **báo cáo backlog, nguyên nhân, owner approval, giới hạn thời gian ngoại lệ, risk acceptance và audit**. Khi key đã compromise, gia hạn old-use theo lịch **không hợp thức hóa việc tiếp tục dùng**.

## 10. Rotation KEK: giữ dữ liệu cũ đọc được bằng rewrap

Khi một **KEK** được thay định kỳ và **DEK chưa bị lộ**, rewrap thường là lựa chọn hiệu quả để bỏ dần phụ thuộc KEK cũ mà **không mã hóa lại nội dung dữ liệu**.

~~~text
Trước khi rotation:
  ciphertext = AEAD_Encrypt(DEK_A, data, nonce_A, aad_A)
  wrappedDEK = Wrap(KEK_v4, DEK_A)

Sau khi rewrap:
  ciphertext = AEAD_Encrypt(DEK_A, data, nonce_A, aad_A)  // giữ nguyên
  wrappedDEK = Wrap(KEK_v5, DEK_A)                       // đổi lớp bọc
~~~

### 10.1. Quy trình rewrap có kiểm soát

1. Sinh successor KEK theo CSPRNG/KMS/HSM và policy được phê duyệt.
2. Gán **key ID/version, owner, purpose, cryptoperiod, grant và audit**.
3. Kích hoạt KEK mới cho `WRAP_NEW`; ngừng primary mới của KEK cũ.
4. Quét wrapped DEK cũ theo exact KEK version trong DB/object storage/backups.
5. Dùng provider `ReEncrypt`/rewrap nếu hỗ trợ **không xuất DEK ra application**; nếu phải unwrap rõ, làm trong trusted runtime với quyền hạn và thời gian sống ngắn.
6. Ghi `wrappedDek`, `kekVersion`, `providerRef` cùng nhau bằng transaction/CAS.
7. Kiểm tra decrypt các record và thử restore từ backup.
8. Thu hẹp old-key access rồi mới retire/destroy khi không còn dependency hợp lệ.

### 10.2. Rewrap không thay `AAD` của data ciphertext

Nếu AAD gắn tenant/record, rewrap KEK chỉ đổi lớp wrapped DEK; **data ciphertext/tag/nonce/AAD giữ nguyên**. Đổi tenant/record ID được AAD xác thực thường cần re-encrypt lớp dữ liệu, không được chỉ sửa metadata rồi rewrap.

### 10.3. Rewrap với KMS APIs

Một số managed KMS có API re-encrypt ciphertext key blob từ khóa cũ sang khóa mới mà **không xuất plaintext DEK tới caller**. Một số KMS/HSM chỉ hỗ trợ unwrap/wrap tách bước; một số có giới hạn region, key type, context. **Không giả định API/provider nào cũng giống nhau**; phải đánh giá semantics, quota và audit.

## 11. Rotation DEK: khi nào phải re-encrypt dữ liệu?

**Re-encrypt** tạo bản mã dữ liệu mới, thường bằng **DEK mới**, và cập nhật envelope:

~~~text
Trước:
  ciphertext_v1 = AEAD_Encrypt(DEK_v1, data, nonce_v1, aad_v1)
  wrappedDEK_v1 = Wrap(KEK_old, DEK_v1)

Sau:
  DEK_v2 <- CSPRNG hoặc KMS GenerateDataKey
  ciphertext_v2 = AEAD_Encrypt(DEK_v2, data, nonce_v2, aad_v2)
  wrappedDEK_v2 = Wrap(KEK_active, DEK_v2)
~~~

### 11.1. Khi cần re-encrypt

- **DEK bị lộ** hoặc nguồn sinh không đủ entropy.
- Cặp **(key, nonce)** bị tái sử dụng trong AEAD hoặc usage limit đã bị vượt.
- Algorithm/mode/format cũ không còn được duyệt.
- Thay tenant/resource/AAD binding khiến ciphertext cũ không còn hợp lệ trong ngữ cảnh mới.
- **Raw KEK cũ và wrapped DEK cũ** có thể đã nằm trong tay attacker, khiến DEK cũ không còn đáng tin.

### 11.2. Rewrap không xử lý compromise của DEK

Nếu attacker đã lấy `DEK_v1`, chuyển từ `Wrap(KEK_v4, DEK_v1)` sang `Wrap(KEK_v5, DEK_v1)` **không thay đổi DEK đã lộ**. Khi mức rủi ro yêu cầu, phải sinh DEK mới và mã hóa lại dữ liệu.

### 11.3. Những gì re-encrypt cũng không làm được

Nếu plaintext đã bị đọc trước đó, re-encrypt **không làm attacker quên dữ liệu**. Phải điều tra, chặn các đường rò và xử lý nghĩa vụ thông báo theo chính sách; không đánh đồng rotation với việc xóa lịch sử bị lộ.

## 12. Chuyển tiếp từ KEK cũ sang KEK mới không gián đoạn

~~~mermaid
sequenceDiagram
    participant W as Writer
    participant P as Primary key policy
    participant DB as Database
    participant R as Reader
    participant K as KMS/HSM
    participant M as Rewrap worker
    W->>P: Xin key cho WRAP_NEW
    P-->>W: KEK v5 ACTIVE
    W->>K: Wrap DEK mới bằng v5
    W->>DB: Lưu record mới + v5
    R->>DB: Đọc record cũ + v4
    R->>P: Check UNWRAP_OLD v4 và quyền record
    P-->>R: Allow theo recipient period
    R->>K: Unwrap DEK cũ bằng v4
    K-->>R: DEK/operation result theo API
    M->>DB: Đọc wrapped DEK v4 theo batch
    M->>K: Rewrap v4 -> v5
    K-->>M: Wrapped DEK v5
    M->>DB: CAS update blob + version + revision
    M->>P: Báo backlog, audit và restore status
~~~

### 12.1. Dual-read, single-new-write

Một chiến lược phổ biến:

- **Writer:** chỉ chọn KEK mới cho những DEK được tạo sau cutover.
- **Reader:** biết định tuyến **KEK version cũ và mới** để mở dữ liệu lịch sử.
- **Migration:** rewrap/backfill dần trên hệ thống còn hoạt động.
- **Cleanup:** chỉ ngừng hỗ trợ version cũ khi dữ liệu và backup liên quan được xử lý.

Không nên “dual write raw secret” để tiện rollback vì có thể tạo thêm bản sao, phức tạp hóa key management và rủi ro giữ plaintext.

### 12.2. Giao dịch và concurrency

KMS call thường không thuộc **cùng ACID transaction** với database. Nếu job rewrap thành công ở KMS nhưng DB update thất bại, phải **retry/reconcile** dựa trên record/key version hiện tại. Dùng **idempotency/operation ID** và optimistic concurrency để không ghi đè ciphertext mới của user.

### 12.3. Mẫu cập nhật CAS

~~~sql
UPDATE encrypted_record
SET wrapped_dek = :new_wrapped_dek,
    kek_version = :new_kek_version,
    provider_key_ref = :new_provider_ref,
    row_revision = row_revision + 1
WHERE tenant_id = :tenant_id
  AND record_id = :record_id
  AND row_revision = :expected_revision
  AND kek_version = :old_kek_version;
~~~

**Update count = 1** mới xác nhận job đã cập nhật đúng revision/version. Khi count = 0, record có thể đã đổi; phải đọc lại và quyết định retry hoặc bỏ qua, **không ghi đè mù quáng**. SQL là minh họa về ý tưởng compare-and-swap, không gắn với một DBMS/ORM duy nhất.

### 12.4. Không đóng key cũ trước khi cutover hoàn tất

Nếu writer vẫn có node chạy cấu hình `v4`, đóng quyền old key đột ngột có thể gây lỗi ghi; nếu reader còn record `v4`, `Disabled` sai thời điểm sẽ gây outage đọc. Kế hoạch cần **deployment coordination, canary, compatibility matrix, rollback guard và monitoring**.

## 13. Java 17: đọc dữ liệu cũ bằng key đã retired

Ví dụ sau cho thấy:

1. Tạo DEK AES-256, mã hóa dữ liệu bằng **AES-GCM** và wrap DEK bằng **AES Key Wrap** với KEK `v4`.
2. Sau cutover, **v4 ở trạng thái RETIRED** nhưng được dùng `UNWRAP_OLD` trong khoảng old-use; KEK `v5` trở thành active cho ghi mới.
3. Lệnh tạo bản mã mới bằng `v4` **bị từ chối**.
4. Lệnh đọc record cũ bằng `v4` **vẫn thành công**, nếu đúng tenant/resource và còn thời hạn.
5. Sau `oldUseUntil` hoặc khi `v4` bị **REVOKED**, lệnh đọc bị từ chối.
6. Nếu tráo `recordId` của envelope, **AAD và authentication tag** của GCM phát hiện.

**Lưu ý phạm vi:** để ví dụ tự chứa và dễ học, `DemoRegistry` giữ **KEK dạng SecretKey trong JVM**, không đại diện cho KMS/HSM có non-extractability. Production phải thay lớp wrap/unwrap bằng **KMS/HSM đã được phê duyệt**, phân quyền ở provider, kiểm soát key status và audit. Mã cũng không kết nối database thật và không chứng minh khả năng zeroization hoàn toàn.

### 13.1. Mã Java 17

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class OldKeyDecryptDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int NONCE_BYTES = 12;
    private static final int GCM_TAG_BITS = 128;
    private static final int FORMAT = 1;

    enum State { PRE_ACTIVE, ACTIVE, RETIRED, REVOKED, DESTROYED }
    enum Use { WRAP_NEW, UNWRAP_OLD }

    record KekVersion(
            String keyId, String version, String tenant,
            Instant activeFrom, Instant newUseUntil,
            Instant oldUseUntil, State state,
            boolean providerEnabled, SecretKey material) {
        KekVersion {
            Objects.requireNonNull(keyId);
            Objects.requireNonNull(version);
            Objects.requireNonNull(tenant);
            Objects.requireNonNull(activeFrom);
            Objects.requireNonNull(newUseUntil);
            Objects.requireNonNull(oldUseUntil);
            Objects.requireNonNull(state);
            Objects.requireNonNull(material);
            if (!activeFrom.isBefore(newUseUntil)
                    || oldUseUntil.isBefore(newUseUntil)
                    || !"AES".equalsIgnoreCase(material.getAlgorithm())) {
                throw new IllegalArgumentException("Invalid KEK metadata");
            }
        }
    }

    record Envelope(
            String tenant, String recordId, int format,
            String kekId, String kekVersion,
            byte[] nonce, byte[] wrappedDek, byte[] ciphertextAndTag) {
        Envelope {
            Objects.requireNonNull(tenant);
            Objects.requireNonNull(recordId);
            Objects.requireNonNull(kekId);
            Objects.requireNonNull(kekVersion);
            nonce = Objects.requireNonNull(nonce).clone();
            wrappedDek = Objects.requireNonNull(wrappedDek).clone();
            ciphertextAndTag =
                    Objects.requireNonNull(ciphertextAndTag).clone();
        }
        @Override public byte[] nonce() { return nonce.clone(); }
        @Override public byte[] wrappedDek() { return wrappedDek.clone(); }
        @Override public byte[] ciphertextAndTag() {
            return ciphertextAndTag.clone();
        }
    }

    static final class DemoRegistry {
        // DEMO: production phải dùng KMS/HSM provider references.
        private final Map<String, KekVersion> versions = new HashMap<>();

        void put(KekVersion key) {
            versions.put(key.keyId() + "/" + key.version(), key);
        }

        KekVersion require(String id, String version) {
            KekVersion key = versions.get(id + "/" + version);
            if (key == null) {
                throw new SecurityException("KEK version unavailable");
            }
            return key;
        }
    }

    static void requireUse(
            KekVersion key, Use use, String tenant, Instant now) {
        Objects.requireNonNull(key);
        Objects.requireNonNull(use);
        Objects.requireNonNull(now);
        if (!key.tenant().equals(tenant)
                || !key.providerEnabled()
                || key.state() == State.PRE_ACTIVE
                || key.state() == State.REVOKED
                || key.state() == State.DESTROYED
                || now.isBefore(key.activeFrom())) {
            throw new SecurityException("Key unavailable or out of scope");
        }
        if (use == Use.WRAP_NEW) {
            if (key.state() != State.ACTIVE
                    || !now.isBefore(key.newUseUntil())) {
                throw new SecurityException("New-use period ended");
            }
        } else {
            // ACTIVE hoặc RETIRED vẫn có thể unwrap dữ liệu cũ,
            // miễn provider thực và chính sách đều cho phép.
            if (!now.isBefore(key.oldUseUntil())) {
                throw new SecurityException("Old-use period ended");
            }
        }
    }

    static SecretKey newDek() throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RNG);
        return generator.generateKey();
    }

    static void field(DataOutputStream out, String value)
            throws Exception {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    static byte[] aad(String tenant, String recordId, int format)
            throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        field(out, "OLD-KEY-DECRYPT/AEAD");
        field(out, tenant);
        field(out, recordId);
        out.writeInt(format);
        out.flush();
        return bytes.toByteArray();
    }

    static Envelope encryptNew(
            DemoRegistry registry, String kekId, String kekVersion,
            String trustedTenant, String trustedRecordId,
            byte[] plaintext, Instant now) throws Exception {
        Objects.requireNonNull(registry);
        Objects.requireNonNull(plaintext);
        Objects.requireNonNull(trustedRecordId);
        KekVersion kek = registry.require(kekId, kekVersion);
        requireUse(kek, Use.WRAP_NEW, trustedTenant, now);

        // Sinh DEK mới cho mỗi record; mã hóa đúng một payload.
        SecretKey dek = newDek();
        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);
        Cipher aead = Cipher.getInstance("AES/GCM/NoPadding");
        aead.init(Cipher.ENCRYPT_MODE, dek,
                new GCMParameterSpec(GCM_TAG_BITS, nonce));
        aead.updateAAD(aad(trustedTenant, trustedRecordId, FORMAT));
        byte[] ciphertext = aead.doFinal(plaintext);

        Cipher wrapper = Cipher.getInstance("AESWrap");
        wrapper.init(Cipher.WRAP_MODE, kek.material());
        byte[] wrappedDek = wrapper.wrap(dek);
        return new Envelope(
                trustedTenant, trustedRecordId, FORMAT,
                kek.keyId(), kek.version(),
                nonce, wrappedDek, ciphertext);
    }

    static byte[] decryptOld(
            DemoRegistry registry, Envelope row,
            String authorizedTenant, String authorizedRecordId,
            Instant now) throws Exception {
        Objects.requireNonNull(registry);
        Objects.requireNonNull(row);
        // AuthN/AuthZ nghiệp vụ phải xác thực ĐỘC LẬP trước hàm này.
        if (!row.tenant().equals(authorizedTenant)
                || !row.recordId().equals(authorizedRecordId)
                || row.format() != FORMAT
                || row.nonce().length != NONCE_BYTES
                || row.wrappedDek().length == 0
                || row.wrappedDek().length > 1024
                || row.ciphertextAndTag().length < 16) {
            throw new SecurityException("Envelope not authorized/valid");
        }
        KekVersion kek = registry.require(
                row.kekId(), row.kekVersion());
        requireUse(kek, Use.UNWRAP_OLD, authorizedTenant, now);

        Cipher wrapper = Cipher.getInstance("AESWrap");
        wrapper.init(Cipher.UNWRAP_MODE, kek.material());
        SecretKey dek = (SecretKey) wrapper.unwrap(
                row.wrappedDek(), "AES", Cipher.SECRET_KEY);

        Cipher aead = Cipher.getInstance("AES/GCM/NoPadding");
        aead.init(Cipher.DECRYPT_MODE, dek,
                new GCMParameterSpec(GCM_TAG_BITS, row.nonce()));
        aead.updateAAD(aad(
                authorizedTenant, authorizedRecordId, FORMAT));
        return aead.doFinal(row.ciphertextAndTag()); // Verify tag.
    }

    static void expectDenied(RunnableChecked action) throws Exception {
        try {
            action.run();
        } catch (SecurityException expected) {
            return;
        }
        throw new AssertionError("Operation should have been denied");
    }

    @FunctionalInterface
    interface RunnableChecked { void run() throws Exception; }

    public static void main(String[] args) throws Exception {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RNG);
        SecretKey keyV4 = generator.generateKey();
        SecretKey keyV5 = generator.generateKey();

        Instant oldActive = Instant.parse("2026-12-01T00:00:00Z");
        Instant oldStopNew = Instant.parse("2027-03-01T00:00:00Z");
        Instant oldStopRead = Instant.parse("2027-09-01T00:00:00Z");
        Instant newActive = Instant.parse("2027-03-01T00:00:00Z");

        DemoRegistry registry = new DemoRegistry();
        registry.put(new KekVersion(
                "billing-kek", "v4", "tenant-42",
                oldActive, oldStopNew, oldStopRead,
                State.ACTIVE, true, keyV4));

        byte[] original = "A historical invoice"
                .getBytes(StandardCharsets.UTF_8);
        Envelope historical = encryptNew(
                registry, "billing-kek", "v4", "tenant-42",
                "invoice-081", original,
                Instant.parse("2027-02-10T00:00:00Z"));

        // Cutover: giữ vật liệu v4, nhưng chỉ cho phép đọc cũ.
        registry.put(new KekVersion(
                "billing-kek", "v4", "tenant-42",
                oldActive, oldStopNew, oldStopRead,
                State.RETIRED, true, keyV4));
        registry.put(new KekVersion(
                "billing-kek", "v5", "tenant-42",
                newActive,
                Instant.parse("2027-12-01T00:00:00Z"),
                Instant.parse("2028-06-01T00:00:00Z"),
                State.ACTIVE, true, keyV5));

        Instant afterCutover = Instant.parse("2027-04-01T00:00:00Z");
        expectDenied(() -> encryptNew(
                registry, "billing-kek", "v4", "tenant-42",
                "invoice-new", original, afterCutover));

        byte[] restored = decryptOld(
                registry, historical, "tenant-42",
                "invoice-081", afterCutover);
        if (!Arrays.equals(original, restored)) {
            throw new AssertionError("Historical decryption failed");
        }

        Envelope newlyEncrypted = encryptNew(
                registry, "billing-kek", "v5", "tenant-42",
                "invoice-082", original, afterCutover);
        if (!Arrays.equals(original, decryptOld(
                registry, newlyEncrypted, "tenant-42",
                "invoice-082", afterCutover))) {
            throw new AssertionError("New version failed");
        }

        // Đến oldUseUntil, key v4 không còn được phép decrypt.
        expectDenied(() -> decryptOld(
                registry, historical, "tenant-42",
                "invoice-081", oldStopRead));

        // Sai tenant bị chặn ngay cả khi wrapped DEK còn hợp lệ.
        expectDenied(() -> decryptOld(
                registry, historical, "tenant-99",
                "invoice-081", afterCutover));

        // Nếu sửa metadata recordId nhưng giữ blob, AAD sẽ thất bại.
        Envelope swapped = new Envelope(
                historical.tenant(), "invoice-099",
                historical.format(), historical.kekId(),
                historical.kekVersion(), historical.nonce(),
                historical.wrappedDek(), historical.ciphertextAndTag());
        boolean integrityRejected = false;
        try {
            decryptOld(
                    registry, swapped, "tenant-42",
                    "invoice-099", afterCutover);
        } catch (AEADBadTagException expected) {
            integrityRejected = true;
        }
        if (!integrityRejected) {
            throw new AssertionError("AAD swap was not detected");
        }

        // Compromise/revocation chặn ngay, dù chưa oldUseUntil.
        registry.put(new KekVersion(
                "billing-kek", "v4", "tenant-42",
                oldActive, oldStopNew, oldStopRead,
                State.REVOKED, true, keyV4));
        expectDenied(() -> decryptOld(
                registry, historical, "tenant-42",
                "invoice-081", afterCutover));

        Arrays.fill(restored, (byte) 0); // Chỉ best-effort trong Java.
        System.out.println("Old key decrypt policy: PASS");
    }
}
~~~

### 13.2. Phần nào của ví dụ là policy, phần nào là cryptography?

**Policy:** `requireUse(...)` là cổng từ chối `WRAP_NEW` đối với version đã retired hoặc quá `newUseUntil`. `UNWRAP_OLD` chỉ được dùng trong `oldUseUntil`, với đúng tenant, provider enabled và key state cho phép.

**Cryptography:** `AESWrap` bảo vệ DEK bằng KEK; `AES/GCM/NoPadding` mã hóa dữ liệu dưới DEK và xác minh AAD/tag ở chiều đọc.

**Data binding:** `tenant` và `recordId` được đưa vào AAD với **length-prefixed encoding** để tránh nhập nhằng do nối chuỗi. Thay record ID mà không mã hóa lại tạo tag mismatch.

**Key version:** Reader dùng `kekId/version` có trong envelope, không dùng primary `v5` để thử mở blob thuộc `v4`.

### 13.3. Cảnh báo khi chuyển sang production

- **Key material:** `DemoRegistry` giữ KEK trong JVM; production sử dụng KMS/HSM và các operation grants phù hợp. Không dùng `SecretKey.getEncoded()` để export KEK chỉ nhằm kiểm tra nó.
- **Resource authorization:** các chuỗi `authorizedTenant`/`authorizedRecordId` chỉ có nghĩa khi được **server xác minh từ identity/DB access policy**, không được tin nguyên input client.
- **Thời gian:** `Instant` từ demo phục vụ test; thực tế dùng server/provider trusted time và kiểm soát clock drift, không nhận `now` do user gửi.
- **State:** cập nhật `DemoRegistry` là mô phỏng; không thay đổi provider state hoặc key policy thật. Một key `Disabled` của KMS có thể từ chối toàn bộ thao tác.
- **Distributed concurrency:** chưa có transaction/counter, IAM revoke propagation, CAS, cache invalidation hoặc idempotency; production cần các biện pháp này.
- **Input validation:** demo kiểm tra một số độ dài, chưa có quota đầy đủ cho ciphertext/AAD/record size và unsupported algorithms.
- **Provider compatibility:** `AESWrap` và `AES/GCM/NoPadding` phải được provider phê duyệt và kiểm thử; không fallback sang ECB/CBC không xác thực.
- **Secret cleanup:** `SecretKey` và native crypto provider có thể giữ byte secret trong heap/RAM; `Arrays.fill` trên một mảng output không đảm bảo xóa mọi bản sao.

**Mẫu này kiểm tra các bất biến của chính sách**, không thay STEP Content QA, formal verification hay một bài security audit triển khai thực.

## 14. Nếu không còn giữ key cũ, sẽ xảy ra điều gì?

Một ứng dụng có thể vẫn hoạt động tốt sau rotation **cho đến khi lần đầu đọc dữ liệu rất cũ**. Đây là lý do kiểm tra “encrypt mới thành công” chưa đủ để kết luận rotation hoàn tất.

| Cách key cũ biến mất | Biểu hiện ở reader | Kết quả có thể xảy ra |
| --- | --- | --- |
| Xóa key version cũ trong KMS | `KeyNotFound` hoặc equivalent | Không unwrap được DEK cũ |
| Disable key cũ trước khi migration | `Disabled` / operation denied | Hàng loạt dữ liệu lịch sử không đọc được |
| Đổi alias `current` và mất key version metadata | Reader gọi nhầm `v5` | Unwrap lỗi hoặc định tuyến sai |
| Key cũ ở vùng khác mà không có DR route | KMS endpoint không dùng được | Restore/DR outage |
| Data AAD format cũ bị loại bỏ | AEAD tag fail dù đúng DEK | Không decrypt được record cũ |
| Hủy backup root/recovery credentials | Không restore được HSM key backup | Mất khả năng phục hồi diện rộng |
| Private recipient key bị hủy sớm | Không unwrap được key transport blob cũ | Mất file/export lịch sử |

### 14.1. Không “đoán khóa” khi gặp lỗi

Khi decrypt cũ thất bại, không lặp qua toàn bộ KEK versions, tự thay thuật toán, bỏ AAD hoặc dùng AES-CBC không tag để cứu dữ liệu. Những hành động này dễ dẫn đến **oracle, key-confusion, downgrade hoặc trả plaintext sai**. Điều tra theo **key ID/version và metadata được kiểm tra**, có runbook được phê duyệt.

### 14.2. Khôi phục có thể khác bật lại toàn hệ thống

Nếu business cần đọc một archive cũ hiếm gặp, có thể dùng **quy trình controlled restoration** cấp quyền/phiên ngắn cho đội recovery, với approval, key provenance và audit, thay vì bật quyền `Unwrap` rộng vĩnh viễn trên production.

## 15. Backup, snapshot và DR: phần dữ liệu cũ dễ bị quên nhất

Để xác định có thể hủy key cũ hay chưa, phải tính **cả dữ liệu đang online và các bản sao lịch sử**.

### 15.1. Bản đồ phụ thuộc

~~~mermaid
flowchart TD
    Key[KEK v4 trong KMS/HSM] --> Main[DB primary: wrapped DEK v4]
    Key --> Replica[Read replica / object version]
    Key --> Backup[Daily backups / snapshots]
    Key --> Archive[Legal archive / cold storage]
    Key --> CDC[CDC / ETL / data lake copy]
    Key --> DR[Cross-region disaster recovery]
    Key --> Jobs[Offline exports / queued migration jobs]
    Main --> Inventory[Dependency inventory]
    Replica --> Inventory
    Backup --> Inventory
    Archive --> Inventory
    CDC --> Inventory
    DR --> Inventory
    Jobs --> Inventory
    Inventory --> Decision{Còn bản nào cần KEK v4?}
    Decision -->|Có| Keep[Giữ old-use/recovery policy được duyệt]
    Decision -->|Không| Retire[Hủy sau verify + approval]
~~~

**Sơ đồ là bản đồ cần kiểm tra, không khẳng định mọi CDC/ETL đều chứa wrapped DEK.** Nếu dữ liệu đã được decrypt trước khi vào downstream, rủi ro còn lớn hơn vì có thể tồn tại plaintext; trường hợp đó cần xử lý ngoài chỉ KEK retention.

### 15.2. Hai chiến lược cho backup cũ

**Giữ key cũ để phục hồi backup:** đảm bảo KEK version còn recoverable trong security boundary có approval, IAM và DR tests. Ưu điểm là không phải rewrite mọi snapshot; nhược điểm là kéo dài thời gian cần giữ key.

**Chuyển/đóng backup cũ:** rewrap/re-encrypt hoặc để backup hết retention theo chính sách, rồi mới hủy KEK. Không phải mọi backup dạng immutable đều hỗ trợ chỉnh sửa; có thể cần **tạo bản backup thay thế** và chứng minh khả năng restore.

### 15.3. Kiểm thử restore không được tạo lỗ hổng mới

Khi rehearsal DR, không export raw KEK ra file rồi copy vào môi trường test tùy tiện. Dùng **vendor-supported restore/key transfer**, least privilege và data/test environment được duyệt. Xác minh chính xác:

1. Đúng **key ID/version** cho wrapped DEK lịch sử.
2. Key state và rights sau restore.
3. AEAD tag/AAD/format decoder còn đúng.
4. Key materials ở DR region có cùng semantics bảo vệ được phê duyệt.
5. Audit/owner/custodian xác nhận **restore thành công**, không chỉ “backup file tồn tại”.

### 15.4. Chi phí giữ key cũ là một khoản nợ vận hành

Mỗi key cũ cần monitoring, IAM, backup, incident runbook, policy approval và khả năng restore. Vì vậy, **rewrap sớm và quản lý backlog** thường giúp giảm số key cũ phải duy trì lâu, thay vì tích lũy hàng trăm version không ai biết có thể xóa khi nào.

## 16. Data retention không đồng nghĩa key online lifetime

Một chính sách yêu cầu giữ hồ sơ 7 năm **không có nghĩa** phải giữ KEK cũ với quyền `Wrap/Unwrap` online 7 năm.

Một số lựa chọn:

- **Rewrap liên tục:** wrapped DEK được chuyển sang successor KEK trước khi đóng old-use, giảm phụ thuộc old KEK.
- **Re-encrypt dữ liệu:** thay DEK/ciphertext khi security/profile yêu cầu, có thể đồng bộ với format migration.
- **Recovery-only custody:** key cũ được bảo vệ trong cơ chế archive/backup do provider hỗ trợ và chỉ dùng khi DR/historical restore có phê duyệt.
- **Data deletion/crypto-erasure có chủ đích:** nếu đã hết retention và không còn legal hold, xóa dữ liệu/key theo policy.

Mỗi lựa chọn có **latency, chi phí, rủi ro và khả năng truy cập** khác nhau. Không một giải pháp nào tự tốt hơn cho mọi hệ thống.

### 16.1. Hệ thống nhiều vùng/tenant

Nếu dữ liệu ở region B còn dùng `KEK_v4` nhưng region A đã chuyển `v5`, việc hủy `v4` theo backlog ở region A sẽ gây lỗi ở B. Dependency inventory cần có **tenant, environment, region, object store versions, backups và consumer**. Không lấy metric `100% migrated` trên một database làm điều kiện duy nhất để hủy key.

### 16.2. Immutable backup và legal hold

Backup bất biến hoặc legal hold có thể bắt buộc giữ metadata/ciphertext cũ đến hạn. Muốn bỏ phụ thuộc KEK cần tính tới **quy trình restore từ backup đó**, không chỉ cách đọc hệ thống hiện tại. Nếu backup bị giữ vô thời hạn không rõ owner, phải làm rõ data retention governance thay vì kéo dài secret lifetime vô hạn.

## 17. Ai được phép dùng key cũ để decrypt?

Giữ key cũ **không nên đồng nghĩa mọi người có quyền đọc trước đây đều vẫn được đọc**. Quyền thay đổi theo người, workload, tenant, purpose, thời hạn và hoàn cảnh.

| Vai trò | Quyền hợp lý | Không nên mặc định |
| --- | --- | --- |
| **Data owner** | Xác định retention, business need và ai có thể đọc dữ liệu cũ | Raw DEK/KEK hoặc key policy admin |
| **Key owner** | Quyết định old-use policy, rotation, exception, revoke | Quyền decrypt dữ liệu nghiệp vụ không giới hạn |
| **Data reader service** | Decrypt đúng record/tenant được phép | Encrypt mới bằng key retired, Export KEK |
| **Migration worker** | Rewrap đúng key version/partition trong batch có phê duyệt | Quyền xem toàn bộ plaintext hoặc DeleteKey |
| **KMS/HSM custodian** | Backup/restore/key state operation theo approval | Quyền đọc mọi dữ liệu ứng dụng |
| **Security approver** | Review IAM, incident, cryptoperiod exceptions | Tự xóa audit hoặc bỏ qua dual control |
| **Auditor** | Đọc metadata/evidence có kiểm soát | Decrypt/Unwrap raw secret chỉ để audit |

### 17.1. Quyền theo operation và purpose

Nếu provider hỗ trợ, tách grants cho **`Wrap`** và **`Unwrap`**, principal riêng cho writer và reader, scope theo KEK/tenant. Nếu không, enforce ở key broker và **giới hạn direct provider access**; không tự khẳng định provider có `decrypt-only` key state.

### 17.2. Quorum cho quyết định nhạy cảm

Kéo dài old-use period của root KEK, restore HSM key backup, thay export policy hoặc destroy KEK ảnh hưởng nhiều tenant có thể cần **M-of-N approval** theo risk tier. Quorum phải được **thực thi trên đường operation**, không chỉ hai người bấm nút trên UI trong khi một admin có thể bypass.

### 17.3. Break-glass khác giữ quyền vĩnh viễn

Trong sự cố, cần khả năng **chặn `Unwrap` trái phép ngay** thông qua principal/grant revocation, service quarantine hoặc provider controls. Quyền break-glass có TTL, scope, log và hậu kiểm; **không dùng lý do khẩn cấp để export KEK hay disable/hủy toàn bộ dữ liệu tùy ý**.

## 18. KMS/HSM outage và việc giữ key cũ để đọc dữ liệu

**Availability của đường old-use** trở thành phụ thuộc nghiệp vụ nếu hệ thống còn phải đọc ciphertext lịch sử.

### 18.1. KMS bị lỗi nhưng key cũ vẫn tồn tại

App có thể không mở được DEK vì endpoint KMS unavailable, quota throttling hoặc partition chưa replicate. Việc key chưa bị destroy **không bảo đảm có thể decrypt đúng SLA**.

Giải pháp vận hành có thể gồm:

- HA/DR route và key replication theo **khả năng provider thực tế**.
- Retry với **backoff/jitter, circuit breaker và rate limiting**.
- Kiểm thử restore/credential/IAM theo từng region/partition.
- DEK caching rất ngắn hạn **chỉ khi threat model cho phép**, với scope/TTL/zeroization best-effort.
- Trạng thái dịch vụ rõ khi không thể đọc lịch sử; fail-closed đối với dữ liệu nhạy cảm.

### 18.2. Không fallback sang raw KEK trong environment

Khi KMS unavailable, việc dùng một bản **KEK hex trong file/.env** để unwrap là hạ cấp security boundary, mở đường đọc hàng loạt bản mã nếu host bị chiếm. Chỉ sử dụng **DR đã được phê duyệt**, không thêm đường trích xuất key tự phát.

### 18.3. Cache khiến revocation trễ

Nếu reader cache DEK, có thể tiếp tục decrypt dù KEK đã bị revoke ở KMS cho tới khi DEK cache hết hạn. Đây là **trade-off có thật giữa availability và khả năng thu hồi tức thời**; key owner phải xác định TTL, cache invalidation và sự cố cần flush cache.

## 19. PKI, JWT và dữ liệu “cũ” không phải lúc nào cũng cần private key

Khái niệm giữ key cũ còn liên quan tới **verification**, nhưng cần phân biệt kỹ thuật.

### 19.1. Private signing key

Khi đổi `signing-key/v4` sang `v5`, không nhất thiết giữ **private key v4** để verify chữ ký cũ. Việc xác minh dùng **public key/chứng thư v4**, trong khi private key v4 có thể dừng `Sign` mới và được retire/hủy theo policy.

### 19.2. JWT và HMAC

Với token ký bất đối xứng, verifier có thể giữ public keys cũ trong **JWKS** một khoảng đáp ứng token TTL và trust policy, nhưng phải xét **issuer, audience, `kid`, certificate/key revocation và clock skew**. Với **HMAC JWT**, verifier cần **secret HMAC key cũ** để kiểm tra token cũ, kéo dài rủi ro key exposure; giới hạn token lifetime và verifier scope phù hợp.

### 19.3. Certificate hết hạn không tự cho biết chữ ký lịch sử hợp lệ

`Signature.verify()==true` chỉ xác nhận phép toán; tính hợp lệ lịch sử có thể cần **certificate chain, revocation status, trusted timestamp, key usage và chính sách lưu trữ bằng chứng dài hạn**. Không dùng yêu cầu verify chữ ký cũ làm lý do giữ private signing key với quyền `Sign` mở vĩnh viễn.

### 19.4. Dữ liệu đã mã hóa cho public key người nhận

Khi recipient rotate **encryption key pair**, ciphertext/DEK cũ được mã hóa cho **public key v4** có thể cần **private decryption key v4** để mở. Cần key-to-identity binding, certificate/key version, secure custody và retention. Khi private key v4 bị compromise, chỉ cấp certificate mới **không thu hồi ciphertext/DEK cũ attacker đã lấy**.

## 20. Khi key cũ bị lộ: có còn nên cho decrypt-old?

Đây là **ngoại lệ lớn nhất** của chiến lược giữ key cũ. Nếu raw key hoặc quyền sử dụng key đã bị chiếm, không thể chỉ nhìn `oldUseUntil` rồi tiếp tục cho phép unwrap/decrypt bình thường.

### 20.1. Phân biệt các loại sự cố

| Sự cố | Đối thủ có thể làm gì? | Hành động cần cân nhắc |
| --- | --- | --- |
| **Raw KEK v4 bị lộ** | Unwrap ngoại tuyến các wrapped DEK v4 mà họ có | Chặn operation, đánh giá bản copy, thay DEK/re-encrypt khi cần; rewrap đơn thuần chưa đủ |
| **KMS principal có quyền Unwrap bị chiếm** | Gọi KMS lấy DEK qua API mà không biết raw KEK | Revoke credentials/grants, phân tích actual KMS logs, xác định DEK đã trả |
| **Raw DEK của record bị lộ** | Đọc dữ liệu được mã hóa bằng DEK ấy | Sinh DEK mới và re-encrypt dữ liệu còn cần bảo vệ |
| **Ciphertext/wrapped DEK bị sửa** | Gây lỗi hoặc tráo record | Validate AEAD/AAD, key binding và data authorization |
| **Reader service bị chiếm** | Đọc plaintext/DEK trong scope IAM/app policy | Cô lập service, giảm quyền, kiểm tra cache/log/dữ liệu đã lấy |
| **Chỉ lộ key ID/version metadata** | Có thông tin cấu trúc/key usage | Không tự coi là lộ raw key; rà metadata exposure và quyền |
| **Old key bị xóa nhầm** | Key material có thể không còn để mở backup | Xác minh recoverability, DR path và dependency; không tự tạo lại material giống cũ từ nguồn yếu |

### 20.2. Vì sao rewrap không thu hồi key đã bị lấy?

Giả sử attacker đã sao chép:

~~~text
rawKEK_v4
wrappedDEK_v4 = Wrap(KEK_v4, DEK_A)
ciphertext_A = AEAD_Encrypt(DEK_A, record_A)
~~~

Ứng dụng tạo `KEK_v5` rồi lưu `Wrap(KEK_v5, DEK_A)`. Nhưng attacker vẫn có **rawKEK_v4 và wrappedDEK_v4 cũ**. Họ vẫn có thể khôi phục DEK_A và đọc ciphertext_A đã lấy. Việc rewrap bản trên hệ thống **không làm bản sao của attacker biến mất**.

Nếu DEK có khả năng đã bị lộ, cần đánh giá **DEK mới + re-encrypt**, loại bỏ plaintext copies không cần thiết, rà data access/backup và xử lý tác động. Nếu dữ liệu đã bị đọc, không có phép rotate nào làm người nhận “quên” dữ liệu.

### 20.3. Kịch bản cần đọc dữ liệu cũ để phục hồi sau compromise

Có tình huống tổ chức vẫn cần **giải mã có kiểm soát để migrate/re-encrypt** các bản mã còn dùng key compromised. Khi ấy không bật lại quyền `Unwrap` thông thường cho toàn bộ reader, mà thiết kế **incident-only recovery path** được phê duyệt: cô lập môi trường, least privilege, giám sát, quorum khi phù hợp, xử lý dữ liệu tạm và ghi evidence. Đây là **quy trình ứng phó đặc biệt**, không phải kéo dài cryptoperiod cũ như chưa có sự cố.

### 20.4. Không dùng “cryptoperiod chưa hết” để bỏ qua revocation

**Revocation/compromise có ưu tiên an ninh cao hơn lịch trình sử dụng**. Một key đã compromised có thể còn cần tồn tại phục vụ điều tra hoặc migration, nhưng phải thay cách **cấp quyền và môi trường vận hành**, không mặc nhiên giữ cấp quyền cũ.

## 21. Key inventory, dependency mapping và audit

Giữ key cũ an toàn cần biết **đúng vật liệu nào còn được dùng để mở dữ liệu nào**, chứ không chỉ có một cột `expired=false`.

### 21.1. Metadata nên quản lý

| Nhóm | Thuộc tính | Mục đích |
| --- | --- | --- |
| Identity | `keyId`, `version`, `providerRef` | Đúng vật liệu/định tuyến |
| Origin | `generatedAt`, `importedAt`, `generationMethod` | Provenance và vùng bảo vệ |
| Owner | `keyOwner`, `dataOwner`, `custodian` | Trách nhiệm và phê duyệt |
| Purpose | `keyClass`, `allowedOperations`, `tenantScope` | Không cross-use/cross-tenant |
| Period | `activationAt`, `newUseUntil`, `oldUseUntil` | Thời gian dùng mới/cũ |
| State | `ACTIVE`, `RETIRED`, `SUSPENDED`, `COMPROMISED`, `DESTROYED` | Trạng thái nghiệp vụ |
| Provider | KMS/HSM key state/grants, partition, region | Tính khả dụng và quyền thực |
| Dependencies | `wrappedDekCount`, `backupRefs`, `archives` | Preflight migration/destruction |
| Usage | `unwrapCount`, `lastOldUseAt`, `readerPrincipals` | Giám sát bất thường |
| Governance | `policyRevision`, `approvalRef`, `rotationPlanRef` | Chứng cứ thay đổi |
| Audit | `providerAuditRef`, `migrationJobId` | Điều tra và reconcile |

### 21.2. JSON inventory minh họa

~~~json
{
  "keyId": "billing-kek",
  "keyVersion": "v4",
  "keyClass": "KEY_ENCRYPTION_KEY",
  "ownerTeam": "billing-security",
  "tenantScope": "production/tenant-42",
  "providerRef": "kms://example/billing-kek/v4",
  "lifecycleState": "RETIRED_FOR_NEW_USE",
  "providerState": "ENABLED",
  "allowedNewOperations": [],
  "allowedOldOperations": ["UNWRAP_OLD"],
  "activationAt": "2026-12-01T00:00:00Z",
  "newUseUntil": "2027-03-01T00:00:00Z",
  "oldUseUntil": "2027-09-01T00:00:00Z",
  "policyRevision": 19,
  "dependentRecords": 126300,
  "backupRefs": ["backup-2027-02", "archive-2026-Q4"],
  "migrationJobId": "rewrap-tenant-42-v4-to-v5",
  "approvalRef": "KEY-ROTATION-1081"
}
~~~

Ví dụ này là **schema tự xây**, không phải một KMS API chuẩn. `ENABLED` cùng với `RETIRED_FOR_NEW_USE` **không có nghĩa provider đang thực thi decrypt-only**; việc cấm wrap mới phải được thực thi ở broker/IAM/provider theo thiết kế và kiểm thử chống bypass.

### 21.3. Ví dụ audit operation

~~~json
{
  "eventType": "OLD_KEY_UNWRAP",
  "keyId": "billing-kek",
  "keyVersion": "v4",
  "operation": "UNWRAP_OLD",
  "principal": "billing-reader",
  "tenantScope": "production/tenant-42",
  "recordRef": "invoice-000812",
  "policyRevision": 19,
  "providerOperationId": "kms-unwrap-001281",
  "result": "SUCCESS",
  "recordedAt": "2027-04-01T08:00:00Z"
}
~~~

**Không log raw KEK/DEK, PIN, plaintext, bearer token hoặc secret từ HSM.** Audit metadata cũng cần phân quyền đọc; key ID, tenant, record access patterns có thể nhạy cảm.

### 21.4. Nguồn audit phải phản ánh đúng nơi thực thi

App policy log có thể nói “`ALLOW`”, nhưng KMS thực tế trả `Disabled`, `AccessDenied` hoặc timeout. Phân biệt **application decision** và **provider operation outcome**. Cần correlation ID để đối chiếu, policy revision để kiểm tra stale cache và immutable/tamper-evident logging khi risk tier yêu cầu.

## 22. Monitoring: khi nào được phép đóng key cũ?

Một key cũ không nên biến mất vì “trông có vẻ đã lâu không dùng”. Dựa trên số liệu và **restore evidence**:

| Metric/cảnh báo | Ý nghĩa |
| --- | --- |
| `legacyWrappedDekCount` | Còn bao nhiêu wrapped DEK phụ thuộc version cũ |
| `legacyCiphertextReadRate` | Có bao nhiêu truy cập dữ liệu cũ |
| `oldKeyUnexpectedWrapCount` | Có writer vẫn wrap mới bằng key retired? |
| `unwrapByUnexpectedPrincipal` | Khả năng dùng sai quyền |
| `crossTenantKeyUse` | Lỗi cách ly tenant |
| `oldKeyOldUseDeadlineSoon` | Sắp hết recipient period nhưng còn dependencies |
| `rewrapBacklog` | Migration chưa hoàn tất |
| `rewrapCasConflicts` | Concurrent write/update gây conflict |
| `backupRestoreFailure` | DR không mở được dữ liệu cũ |
| `unknownKekVersion` | Metadata reader/version lỗi |
| `providerDisabledWhileRequired` | KMS key state không khớp business state |
| `keyPolicyRevisionDrift` | Các node/broker chưa thống nhất |
| `aeadTagFailure` | Dữ liệu lỗi, AAD sai hoặc bị sửa |
| `keyCacheStale` | Bản sao DEK/permission vẫn sống sau revoke |

### 22.1. Mốc quyết định không chỉ từ primary DB

Nếu `legacyWrappedDekCount=0` trong DB primary nhưng backup bất biến còn `v4`, vẫn tồn tại dependency. Nếu tất cả backup đã được thay nhưng một consumer offline vẫn dùng archive cũ, cần biết consumer đó còn nghĩa vụ truy xuất hợp lệ không.

### 22.2. “Không có request trong 30 ngày” chưa là chứng cứ an toàn để destroy

Một hồ sơ pháp lý có thể chỉ cần đọc sau nhiều năm. Số lượng read request bằng 0 không nói gì về **retention/legal hold và khả năng phục hồi**. Điều kiện đóng phải dựa trên chính sách, inventory, migration/restore và phê duyệt phù hợp.

## 23. Runbook trước khi ngừng khả năng decrypt dữ liệu cũ

### Bước 1 — Xác định vật liệu và trạng thái

Ghi rõ **keyId, version, providerRef, tenant, purpose, createdAt/activationAt, newUseUntil, oldUseUntil, owner, policy revision**. Xác minh key version không bị alias che khuất.

### Bước 2 — Đánh giá phụ thuộc

Quét DB, object storage, các phiên bản file, backup, snapshots, archive, DR, CDC/ETL và consumer. Đối chiếu `wrappedDek`/key references, không chỉ số record mới.

### Bước 3 — Hoàn tất migration hoặc quyết định retention

Nếu DEK vẫn an toàn, **rewrap** sang KEK mới. Nếu DEK đã lộ/sai nonce/algorithm hoặc thay data AAD, **re-encrypt** theo plan. Nếu dữ liệu hết retention, xác định quy trình xóa dữ liệu/crypto-erasure.

### Bước 4 — Verification và restore rehearsal

Kiểm thử decrypt record cũ, mới; negative tests key version/tenant; phục hồi backup lịch sử; xác nhận keys, permissions, schemas và authenticated context. Test cả trường hợp KMS node/region hỏng.

### Bước 5 — Chặn new-use và thu hẹp old-use

Xác nhận key cũ không còn được `Encrypt/Wrap` mới. Giới hạn old-use access, quota, TTL của service principal và khả năng bypass direct KMS calls.

### Bước 6 — Phê duyệt đóng

**Data owner, Key owner, Security và custodian** theo chính sách xác nhận không còn dependency cần đọc hoặc chấp nhận crypto-erasure. Với root KEK ảnh hưởng nhiều tenant, có thể yêu cầu **quorum approval**.

### Bước 7 — Hủy hoặc archive đúng semantics

Đưa key vào trạng thái phù hợp, dùng vendor-supported destroy/backup decommission process nếu hủy. **Không ghi `DESTROYED` khi chỉ `DISABLED` hoặc `ARCHIVED`**. Giữ evidence, nhưng không giữ raw key trong ticket.

### Bước 8 — Hậu kiểm

Kiểm tra không còn decrypt cũ trái phép, không tạo ciphertext mới dưới version đã retire, audit không bị thiếu và các backup/consumer còn hợp lệ không gặp lỗi.

~~~mermaid
flowchart TD
    Scan[Inventory old key + dependencies] --> Migrate[Rewrap/re-encrypt hoặc xử lý retention]
    Migrate --> Verify[Canary decrypt + restore test]
    Verify --> Decision{Còn dependency hợp lệ?}
    Decision -->|Có| Keep[Giữ controlled old-use / xử lý backlog]
    Keep --> Scan
    Decision -->|Không| Approve[Data/Key owner + Security approval]
    Approve --> Close[Chặn old-use và destroy/archive đúng semantics]
    Close --> Audit[Final audit + monitoring]
~~~

## 24. Case study: lưu trữ hóa đơn 7 năm với KEK rotation

### Bối cảnh

Một nền tảng SaaS lưu hóa đơn cho **150 tenant**, dữ liệu phải giữ nhiều năm. DEK được sinh **per-record** và mã hóa bằng AES-GCM; KEK trong managed KMS bảo vệ DEK. Nhóm Security muốn không dùng KEK quá lâu để tạo bảo vệ mới, nhưng nhóm vận hành phải đọc được hóa đơn cũ khi khách hàng hoặc kiểm toán yêu cầu.

### Giai đoạn A — Rotation thiếu chuẩn bị

Ban đầu, hệ thống lưu:

~~~text
invoice-01: wrapped DEK under tenant-A/KEK-v4
invoice-02: wrapped DEK under tenant-A/KEK-v4
invoice-03: wrapped DEK under tenant-A/KEK-v4

Alias: tenant-A/current -> KEK-v4
~~~

Đội hạ tầng tạo `KEK-v5`, chuyển alias `current` sang v5 và **disable v4** ngay. Writer bắt đầu bọc DEK mới được, nhưng reader dùng bản wrapped DEK cũ dưới v4 nhận lỗi từ KMS.

**Nguyên nhân:** team nhầm “không dùng v4 cho dữ liệu mới” với “v4 không cần tồn tại/hoạt động”. Họ không kiểm tra **recipient-use, metadata và backup dependencies**.

### Giai đoạn B — Sửa thiết kế

Key owner định nghĩa:

- `v5` là **primary for new wrap**.
- `v4` là **RETIRED_FOR_NEW_USE** trong inventory/broker.
- Reader chỉ được `UNWRAP_OLD` v4 với **authorization theo tenant/record**, trong thời kỳ và vùng KMS còn được phép.
- IAM/KMS grants giới hạn principal phù hợp, kiểm thử **không thể bypass write policy**.
- Record giữ `kekVersion` chính xác; không thay bằng alias hiện hành khi đọc.

**Lưu ý:** nếu KMS không hỗ trợ phân quyền wrap/unwrap riêng, phải dùng kiến trúc/broker/grants thích hợp và đánh giá rủi ro direct access, không tuyên bố provider đã enforce decrypt-only.

### Giai đoạn C — Rewrap dần

Worker duyệt record theo tenant và batch, dùng API KMS re-encrypt/rewrap được hỗ trợ, lưu `wrappedDek` mới dưới v5 và cập nhật `kekVersion` cùng transaction. Với conflict, đọc lại `rowRevision` để không ghi đè dữ liệu mới.

Nhóm giám sát:

- Tỷ lệ `legacyWrappedDekCount` giảm.
- Lượng gọi old-key unwrap vẫn đúng read pattern.
- Không có `Wrap New` dưới v4 sau cutover.
- AEAD decrypt/tag còn thành công với records đã migration.
- Backup/DR còn restore được.

### Giai đoạn D — Phát hiện archive còn phụ thuộc v4

DB primary hết bản v4, nhưng **cold archive của năm trước vẫn chứa wrapped DEK v4**. Key owner có hai lựa chọn hợp lệ theo dữ liệu và provider:

1. Giữ v4 **ở vùng recovery có kiểm soát** cho tới khi archive hết retention/được migrate an toàn.
2. Tạo archive mới có DEK được rewrap sang v5, kiểm tra restore, xử lý bản cũ theo chính sách.

Không hủy v4 chỉ vì tiến độ migration primary DB bằng 100%.

### Giai đoạn E — Một principal có quyền Unwrap bị lạm dụng

Sau đó, Security phát hiện principal của reader tenant A bị chiếm. Người xử lý **không chỉ rotate KEK**, mà rà KMS operation logs để xác định các DEK đã có thể được trả dạng rõ và data scope bị ảnh hưởng. Nếu DEK có thể đã lộ, họ **re-encrypt bằng DEK mới** những bản ghi liên quan, đồng thời revoke principal và xử lý cached secrets.

### Kết luận tình huống

Giữ key cũ đúng cách là một phần của **rotation có kiểm soát**: có phiên bản rõ, quyền đọc lịch sử riêng, thời hạn, dependency inventory, migration và recoverability. **Giữ tất cả keys online vô hạn** và **xóa hết ngay khi cutover** đều là những cực đoan thiếu an toàn.

## 25. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Xóa KEK ngay sau khi thay alias `current` | Không unwrap được DEK cũ | Giữ old-use tới khi xử lý dependencies |
| Nghĩ key `Disabled` vẫn được decrypt | Outage vì provider từ chối mọi operation | Kiểm chứng key state và capability thật |
| Dùng KEK retired để wrap dữ liệu mới | Tăng data phụ thuộc key cũ, vi phạm policy | Chặn writer theo key/version/newUseUntil |
| Lưu key alias mà không lưu version | Reader mở nhầm material | Exact key ID/version hoặc provider blob được kiểm chứng |
| Không ghi nonce/tag/AAD format | Mất khả năng decrypt lịch sử | Envelope format/version và data integrity |
| Chỉ kiểm tra KMS IAM, bỏ authorization record | Cross-tenant decrypt oracle | Resource auth trước unwrap |
| Cho reader thử qua mọi key versions | Dò key, confusion, lộ metadata | Định tuyến theo verified key reference |
| Giữ key cũ với quyền Export/Encrypt/Delete mở | Mở rộng blast radius | Least privilege, SoD và old-use-only policy |
| Coi inventory `RETIRED` là provider decrypt-only | Direct KMS calls vẫn bypass | Broker+IAM+provider enforcement |
| Chỉ rewrap DB chính, bỏ qua backup/archive | Không restore được bản cũ | Dependency scan và restore rehearsal |
| Hủy key dựa trên “30 ngày không dùng” | Không đọc được dữ liệu hiếm gặp | Retention/legal hold và approval |
| Chỉ rewrap DEK đã lộ | Attacker vẫn có DEK cũ | DEK mới + re-encrypt khi cần |
| Raw KEK bị lấy, chỉ chuyển wrapped DEK hiện tại | Bản sao old wrapped DEK vẫn decrypt được | Incident impact và data remediation |
| Coi revocation xóa secret đã nhận | Attacker vẫn có raw key/plaintext | Cache/copy assessment, re-encrypt dữ liệu tương lai |
| Giữ old KEK trong file `.env` để dự phòng | Lộ vật liệu ngoài KMS/HSM | Vendor-supported DR, no unapproved fallback |
| KMS call và DB transaction được coi là atomic | Retry/partial update sai | Idempotency/CAS/reconciliation |
| Rewrap worker update cả ciphertext từ snapshot cũ | Lost update | Chỉ update blob+version có revision guard |
| Đổi tenant/record ID mà không đổi AEAD AAD | GCM tag failure | Authorized re-encrypt với context mới |
| AEAD tag hợp lệ được coi là chống rollback | Chấp nhận nguyên record cũ hợp lệ | Trusted revision/audit chống rollback nếu cần |
| Không phân biệt signing và encryption key | Giữ private signing key để verify | Public verification key và PKI history |
| Bỏ qua KMS audit và principal compromise | API unwrap bị lạm dụng không được thấy | Actual operation monitoring + containment |
| Không kiểm soát cache DEK | Vẫn decrypt sau revoke | TTL/scope/flush và incident plan |
| Log raw DEK/KEK trong migration | Tạo đường lộ khóa mới | Log IDs, version và outcome; không log secret |
| Kéo dài `oldUseUntil` vô hạn không duyệt | Key exposure kéo dài | Risk exception/owner/TTL và migration backlog |

## 26. Checklist triển khai an toàn

- [ ] Đã tách **new-use** và **old-use** của từng key class/version?
- [ ] Có định nghĩa thời gian `activationAt`, `newUseUntil`, `oldUseUntil` theo UTC, khoảng nửa mở?
- [ ] `WRAP_NEW/ENCRYPT_NEW/SIGN_NEW` bị chặn với key retired, kể cả direct provider calls nếu kiến trúc cho phép?
- [ ] Không giả định provider `Disabled` tương đương decrypt-only?
- [ ] Reader chỉ mở key version gắn với ciphertext và chỉ trong đúng **tenant/record/purpose**?
- [ ] Có IAM/authorization theo principal, operation, key, tenant, environment và region?
- [ ] Cơ chế decrypt cũ không trở thành API `decrypt any blob` cho caller?
- [ ] DEK/KEK được sinh và lưu trong vùng được duyệt, có provenance và export policy rõ?
- [ ] Envelope lưu **wrapped DEK, exact KEK key/version, AEAD nonce/tag, algorithm và AAD context version**?
- [ ] AAD ràng buộc tenant/record từ nguồn tin cậy, không chấp nhận đổi context không re-encrypt?
- [ ] Đã phân biệt **rewrap KEK** và **DEK mới + re-encrypt** theo threat model?
- [ ] Rotation đã sinh/activate successor và chuyển primary writer trước deadline?
- [ ] Có **dual-read/single-new-write** hoặc chiến lược cutover tương đương đã kiểm chứng?
- [ ] Rewrap jobs có **CAS, transaction, idempotency, checkpoint, retry và audit**?
- [ ] Không delete key cũ chỉ vì alias đổi hoặc primary DB migration báo 100%?
- [ ] Đã inventory **DB, object storage, backups, immutable snapshots, archives, DR, CDC/ETL và offline consumers**?
- [ ] Có **restore rehearsal** thành công với dữ liệu cũ và provider/region dự kiến?
- [ ] Key provider state/IAM/grants thực tế được đối chiếu với inventory/lifecycle policy?
- [ ] Có thời hạn old-use được phê duyệt, kiểm soát ngoại lệ kéo dài và audit lý do?
- [ ] Có principal phục vụ old-read riêng, least privilege, quota/alert và không export raw KEK?
- [ ] KMS outage có fail-safe, HA/DR được duyệt; **không fallback** sang raw KEK trong environment?
- [ ] Cache DEK (nếu dùng) có TTL, tenant scope, revoke/flush strategy?
- [ ] Có negative tests: writer gọi old key, wrong key version, wrong tenant, tag/AAD sai, provider disabled, oldUseUntil, revoked key?
- [ ] Có kiểm thử state trước/khi vừa chạm mốc `oldUseUntil`, không dùng thời gian client?
- [ ] Đã phân biệt **raw-key compromise** với **KMS API misuse** và tác động DEK/ciphertext?
- [ ] Với signing/JWT, đã hiểu verify cũ thường cần **public key/trust history**, không nhất thiết private signing key?
- [ ] Destruction có dependency scan, key/data owner approval, quorum khi cần và bằng chứng đúng provider semantics?
- [ ] Không log raw key, plaintext, credentials, token hoặc DEK trong trace/metrics/backups ngoài policy?

## 27. Câu hỏi tự kiểm tra

**1. Vì sao sau rotation vẫn cần key cũ?**  
Ciphertext và wrapped DEK tạo từ key version cũ **không tự được chuyển sang vật liệu mới**. Nếu chưa rewrap/re-encrypt và chưa hết nhu cầu đọc, vẫn cần khả năng decrypt/unwrap đúng version cũ.

**2. Giữ key cũ có nghĩa tiếp tục encrypt bằng key đó không?**  
Không. Chính sách thường **cấm tạo bảo vệ mới** bằng key đã retire nhưng có thể cho phép **decrypt/unwrap dữ liệu cũ** theo cryptoperiod và quyền.

**3. Originator-usage và recipient-usage khác nhau thế nào?**  
Originator dùng để tạo bảo vệ mới; recipient dùng để xử lý bảo vệ đã có trước, với semantics phụ thuộc key class.

**4. Có thể Disable KEK trong KMS mà vẫn unwrap cũ không?**  
Không được mặc định. Nhiều provider chặn cả wrap lẫn unwrap khi Disabled. Phải kiểm tra API/key state thực tế.

**5. Reader phải chọn KEK nào khi một record có `kekVersion=v4` nhưng alias `current=v5`?**  
Dùng **v4** hoặc provider blob có version binding phù hợp để unwrap DEK của record đó; không tự thay bằng v5.

**6. Vì sao không nên để client tự chọn `kekKeyId` để decrypt bất kỳ dữ liệu nào?**  
Nó có thể biến service thành **decrypt oracle** sử dụng quyền KMS của backend. Cần resource/tenant authorization và trusted key mapping.

**7. Rewrap DEK có làm thay ciphertext dữ liệu không?**  
Thông thường không: giữ DEK và data ciphertext, chỉ thay lớp wrap KEK. Nếu dữ liệu/AAD/DEK phải đổi thì cần re-encrypt.

**8. Khi DEK bị lộ, chỉ đổi KEK và rewrap có đủ không?**  
Không. Attacker vẫn có DEK cũ; cần đánh giá tạo DEK mới và re-encrypt dữ liệu liên quan.

**9. Nếu raw KEK v4 và wrapped DEK v4 cũ đã bị attacker sao chép, việc rewrap hiện tại có giúp họ quên key không?**  
Không. Các bản sao họ giữ vẫn có thể được dùng để unwrap ngoại tuyến.

**10. Vì sao database chính đã migrate hết vẫn chưa được xóa KEK v4?**  
Backup, snapshot, archive, DR hoặc offline consumers có thể vẫn phụ thuộc v4. Cần inventory và restore test.

**11. `oldUseUntil` bằng thời điểm hiện tại có còn cho decrypt không?**  
Với khoảng nửa mở `now < oldUseUntil`, **không**. Tại đúng mốc đã hết old-use period.

**12. Nếu key bị COMPROMISED trước khi old-use kết thúc, có thể tiếp tục theo lịch không?**  
Không mặc nhiên. Phải thực hiện containment/incident response, có thể dùng recovery/migration path đặc biệt được duyệt.

**13. Một private signing key cũ có cần giữ để verify chữ ký cũ không?**  
Thường **không**; verify dùng public key/chứng thư và trust history. Không giữ private key với quyền ký chỉ để verify.

**14. Tại sao đổi `recordId` có thể khiến dữ liệu cũ không decrypt được dù đúng DEK?**  
Nếu `recordId` nằm trong AEAD AAD, context mới không khớp tag cũ. Cần authorized migration/re-encrypt.

**15. CAS/optimistic locking giúp gì trong rewrap?**  
Ngăn worker ghi đè một record đã bị người dùng/job khác cập nhật; khi revision/version không khớp phải reconcile/retry.

**16. KMS key không xuất được có chắc chắn không thể bị lạm dụng?**  
Không. Credential có quyền `Unwrap/Decrypt` có thể bị chiếm; cần IAM, monitoring và app authorization.

**17. Có nên lưu bản raw KEK vào file để phòng KMS ngừng hoạt động không?**  
Không nếu trái key custody policy. Dùng HA/DR hoặc cơ chế backup/restore do provider hỗ trợ.

**18. Giữ key cũ cho retention 7 năm có đồng nghĩa phải bật quyền decrypt online 7 năm không?**  
Không nhất thiết. Có thể rewrap dữ liệu, dùng recovery-only custody hoặc kế hoạch archive phù hợp, tùy rủi ro và yêu cầu đọc.

**19. Khi nào có thể kết thúc old-use và destroy key v4?**  
Sau khi **không còn dependency hợp lệ** hoặc có quyết định crypto-erasure có chủ đích, kiểm tra backup/restore, approval và audit.

**20. Tại sao việc giữ key cũ an toàn cần cả Key owner và Data owner?**  
Key owner quyết định cách sử dụng và bảo vệ key; Data owner quyết định nghĩa vụ truy cập, chia sẻ và retention của dữ liệu. Cần cả hai để tránh xóa sớm hoặc lưu key vô hạn.

## Ghi nhớ

**Giữ key cũ để decrypt dữ liệu cũ là một phần thiết yếu của cryptoperiod và rotation an toàn**: khóa phiên bản cũ **ngừng bảo vệ dữ liệu mới** nhưng có thể tiếp tục phục vụ **giải mã/unwrap lịch sử trong khoảng recipient-usage được cho phép**. Điều này đòi hỏi **exact key ID/version, đúng thuật toán, nonce/tag/AAD, dữ liệu và tenant authorization, IAM/KMS/HSM operation controls, audit và giới hạn thời gian**. Không tự coi `Disabled` của KMS là decrypt-only, không giữ raw key ở application để dự phòng, không xóa key chỉ vì chuyển alias. Muốn giảm thời gian phải giữ key cũ, hãy **rewrap DEK dưới KEK mới khi DEK còn an toàn**, hoặc **thay DEK/re-encrypt khi key đã lộ, sai profile hay đổi AAD**. Chỉ retire/destroy sau khi rà soát **database, backup, archive, DR và mọi phụ thuộc hợp lệ**, có restore evidence và approval. Nguyên tắc kết thúc: **không dùng key cũ để tạo rủi ro mới, không làm mất khả năng đọc dữ liệu cũ khi còn nghĩa vụ, và không coi việc rotation là cách thu hồi những secret đã bị lộ**.

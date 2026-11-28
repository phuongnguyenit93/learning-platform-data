# Access audit cho key storage — Kiểm toán truy cập nơi lưu trữ khóa mật mã

## 1. Access audit cho key storage là gì?

**Access audit cho key storage** là quá trình **ghi nhận, bảo vệ, đối chiếu và phân tích bằng chứng về mọi hoạt động truy cập, sử dụng hoặc thay đổi có ý nghĩa bảo mật đối với khóa mật mã và môi trường lưu trữ khóa**. Mục tiêu không chỉ là trả lời “ai đã mở kho khóa?” mà còn:

- **Ai** (principal, workload, admin, service account) thực hiện yêu cầu?
- **Truy cập tài sản nào** (key ID, key version, KMS/HSM partition, keystore, bản sao lưu)?
- **Thực hiện hành động gì** (đọc metadata, sử dụng khóa, sửa policy, tạo grant, backup, rotate, destroy)?
- **Tại sao** hành động hợp lệ (purpose, approval, ticket, phiên ứng cứu, data scope)?
- **Khi nào và từ đâu** (thời điểm có nguồn đáng tin, môi trường, phiên, nguồn gọi)?
- **Quyết định và kết quả** thế nào (allow/deny, success/failure, provider result)?
- **Bằng chứng có toàn vẹn, đầy đủ và tra cứu lại được không?**

Ví dụ: dịch vụ Billing dùng KEK `billing-kek-v3` trong KMS để giải bọc DEK, rồi DEK mã hóa hóa đơn bằng AES-GCM. Log `Unwrap` ở KMS cho biết service account nào đã yêu cầu giải bọc, nhưng **không nhất thiết ghi lại mọi lượt đọc hóa đơn sau đó** nếu ứng dụng giữ DEK plaintext trong RAM/cache. Muốn kiểm toán đầy đủ quyền truy cập dữ liệu cần **kết hợp log của KMS với log ứng dụng và kiểm soát cache**.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, access audit là mối nối giữa **key storage**, **vòng đời khóa** (tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy), mật mã đối xứng/bất đối xứng, chữ ký số, KMS/HSM, **envelope encryption**, IAM và ứng cứu sự cố.

> **Điểm cốt lõi:** **Audit chứng minh các sự kiện được quan sát và ghi lại; audit không tự ngăn thao tác trái phép.** Cần cả **authorization enforcement**, **nhật ký đáng tin**, **phát hiện bất thường** và **hành động ứng cứu**.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **audit quyền truy cập**, **audit sử dụng khóa**, **audit thay đổi quản trị** và **audit truy cập dữ liệu**.
2. Xác định những sự kiện cần ghi ở KMS, HSM/PKCS#11, Java keystore, ứng dụng và control plane.
3. Thiết kế event schema có **identity, action, resource, context, decision, outcome và correlation ID**.
4. Giải thích giới hạn của audit khi **DEK đã được giải bọc**, key bị cache hoặc vật liệu khóa bị xuất ra ngoài.
5. Bảo vệ log khỏi sửa/xóa và không vô tình ghi **private key, DEK, KEK, PIN hoặc plaintext nhạy cảm**.
6. Thiết kế cảnh báo, đối soát, quy trình kiểm thử và phản ứng khi xuất hiện hoạt động bất thường.

## 2. Access audit khác access control thế nào?

**Access control** quyết định một yêu cầu **được phép hay bị từ chối**. **Access audit** tạo và giữ bằng chứng về **yêu cầu, quyết định và những gì thực sự xảy ra**.

| Thành phần | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Authentication** | Principal là ai? | Workload identity đã xác thực với cloud IAM |
| **Authorization** | Principal có được dùng key/operation đó? | Cho `Sign` nhưng không cho `Decrypt` |
| **Business authorization** | Nội dung/dữ liệu có được xử lý theo mục đích? | Hóa đơn đã chốt mới được ký |
| **Access audit** | Ai yêu cầu, hệ thống quyết định gì, provider làm gì? | Event có key ID, operation, result |
| **Monitoring/detection** | Có mẫu sử dụng khác thường? | Đột biến `Unwrap` lúc không có batch job |
| **Incident response** | Có cần cô lập, rotate hay điều tra? | Thu hồi grant và kiểm tra dữ liệu phụ thuộc |

Một KMS có thể trả về **`AccessDenied`**. Đây là một **quyết định bảo mật** đáng ghi nhận, không phải bằng chứng rằng đối thủ đã đọc được dữ liệu.

Ngược lại, API trả **thành công** chưa chứng minh việc dùng khóa đúng nghiệp vụ: service có thể được quyền `Sign` nhưng lại ký artifact chưa được phê duyệt. Vì vậy cần cả **log provider và log quyết định nghiệp vụ**.

### Sự kiện yêu cầu và sự kiện hoàn tất

Không nên chỉ lưu một boolean `success=true`. Với operation có thể kéo dài hoặc retry, nên phân biệt:

- **Request received:** đã nhận yêu cầu với ID nào.
- **Authorization decision:** allow/deny, policy revision, lý do ở mức an toàn.
- **Provider execution:** API đã được gọi hay chưa, operation nào, kết quả ra sao.
- **Business outcome:** hóa đơn đã phát hành, dữ liệu đã trả cho khách hàng, hay job đã rollback.
- **Final reconciliation:** đối soát những sự kiện thiếu/không khớp khi hệ phân tán có lỗi.

Log “đã duyệt” **không chứng minh KMS đã thực hiện**; log “KMS đã thực hiện” **không chứng minh kết quả đã được sử dụng đúng cách**.

## 3. Những nơi lưu khóa cần audit

**Key storage** không chỉ là một HSM. Nó có thể gồm KMS, keystore, secret manager, backup và những nơi bản sao khóa tồn tại.

| Nơi lưu hoặc đường sử dụng | Dấu vết có thể thu thập | Giới hạn |
| --- | --- | --- |
| **Managed KMS** | API key usage, key policy, grants, key state, rotation tùy provider | Không thấy hoạt động offline với DEK plaintext đã trả |
| **HSM / PKCS#11** | Login, session, object management, Sign/Decrypt/Wrap tùy firmware/logging | Không phải mọi token đều log mọi call hoặc giữ business context |
| **Java KeyStore/PKCS#12 file** | File-open, process identity, decrypt keystore, app events | OS log đọc file không nói private key đã dùng ra sao trong JVM |
| **Secret manager** | Read/rotate/version/access policy của secret | Nếu trả raw secret, các lần dùng sau bên ngoài vault khó quan sát |
| **Database chứa wrapped DEK** | Read/write ciphertext, wrapped DEK, key version | Không đồng nghĩa DEK được giải bọc hoặc plaintext bị đọc |
| **Backup/DR** | Tạo, tải, sao chép, restore, xóa và quyền backup | Snapshot có thể chứa secret mà log ứng dụng không nhìn thấy |
| **Ứng dụng** | Business request, data scope, decision, key version | Phải bảo vệ khỏi caller tự giả event hoặc tắt log |
| **CI/CD/configuration** | Thay IAM, policy, KMS alias, deploy key mapping | Không thay thế provider log xác nhận thao tác thật |
| **Bộ nhớ/cache** | Cache hit/miss ở mức chỉ số hoặc event có kiểm soát | Không nên dump DEK/secret để “audit” |

### Tránh nhầm vị trí khóa với nguồn log

Một KMS có thể dùng HSM ở backend, nhưng khách hàng thường nhận **service API audit**, không tự nhiên nhận tất cả log nội bộ HSM. Một HSM tự vận hành có thể yêu cầu cấu hình **native audit facility**; không suy ra mặc định có một schema chung cho mọi thiết bị.

**Phải kiểm tra năng lực, cấu hình bật log, phạm vi sự kiện, độ trễ và khả năng thất lạc log của từng nền tảng.**

## 4. Ba lớp audit quan trọng nhất

~~~mermaid
flowchart TD
    R[Yêu cầu từ người dùng / workload] --> A[Ứng dụng: xác thực và business policy]
    A -->|Deny| AD[Application deny audit]
    A -->|Allow| C[Control plane: IAM, purpose, key state]
    C -->|Deny| CD[Policy deny audit]
    C -->|Allow| P[KMS/HSM: key operation]
    P --> PL[Provider log: operation và result]
    P --> D[Ứng dụng xử lý ciphertext / signature / plaintext]
    D --> DL[Business outcome + data access audit]
    AD --> SIEM[Collector / SIEM]
    CD --> SIEM
    PL --> SIEM
    DL --> SIEM
    SIEM --> X[Đối chiếu key ID + request ID + time + actor]
    X --> DET[Phát hiện bất thường / ứng cứu]
~~~

### 4.1. Application audit

Ứng dụng biết **loại tài liệu, tenant, người dùng cuối, trạng thái phê duyệt và kết quả nghiệp vụ**. KMS thường không hiểu hóa đơn nào đã chốt hay token có được phát cho đúng audience.

### 4.2. Control-plane audit

Quản lý các quyết định và thay đổi **policy, grants, key state, key alias, owner/custodian, cryptoperiod, rotation approval**. Đặc biệt quan trọng khi một admin có quyền **tự cấp thêm quyền**.

### 4.3. Data-plane / provider audit

Ghi hoạt động **`Sign`, `Decrypt`, `Unwrap`, `GenerateMac`, `DeriveKey`, `GenerateDataKey`**... theo API thực tế. Một số dịch vụ có cơ chế giới hạn logging, khác biệt loại event hoặc sự kiện không có đầy đủ key material version.

**Các lớp này bổ trợ nhau.** Không thể chỉ chọn một trong ba rồi tuyên bố mọi hành động truy cập khóa đã được ghi nhận.

## 5. Phân loại sự kiện theo rủi ro

Mỗi loại sự kiện cần **mức ưu tiên, retention và tuyến cảnh báo** tương ứng.

| Nhóm | Sự kiện ví dụ | Vì sao quan trọng |
| --- | --- | --- |
| **Discovery/metadata** | `DescribeKey`, list keys, đọc key inventory | Có thể tiết lộ cấu trúc hệ thống dù không lộ key |
| **Authentication** | Login HSM, thất bại PIN, role switch, session establishment | Phát hiện dùng danh tính bất thường |
| **Cryptographic use** | Encrypt, Decrypt, Sign, VerifyMac, GenerateMac, Derive | Theo dõi quyền dùng khóa thực |
| **Key material exposure** | Export nếu được hỗ trợ, backup/restore, data key plaintext được trả | Nguy cơ bí mật rời boundary |
| **Key lifecycle** | Generate, import, activate, disable, rotate, schedule deletion, destroy | Thay đổi khả năng bảo vệ/khôi phục |
| **Authorization change** | Tạo grant, sửa key policy/IAM, thay role, trust relationship | Có thể mở đường sử dụng khóa ngoài ý định |
| **Routing/version** | Đổi alias, current key version, JWKS/certificate mapping | Ảnh hưởng output mới và khả năng verify |
| **Incident/break-glass** | Cấp quyền phục hồi, emergency disable, resume | Cần lý do, giới hạn thời gian và hậu kiểm |
| **Audit infrastructure** | Thay cấu hình log, xóa log, dừng collector, thay retention | Có thể che giấu các hành vi trên |

### Không mặc định API `Verify` hoặc `GetPublicKey` là vô hại

Public key có thể công khai, nhưng việc đọc metadata/certificate vẫn có thể tiết lộ **định danh hệ thống hoặc mạng lưới phụ thuộc**. Việc phân loại cảnh báo nên dựa trên risk tier; không phải mọi lần đọc public key đều cần báo động mức cao.

### Phải hiểu “sự kiện xuất khóa”

Một KMS non-exportable có thể **không có API export raw KEK/private key**, nhưng `Decrypt` một wrapped DEK có thể trả về **DEK plaintext** cho ứng dụng. Audit phải hiểu **tác động thực tế** của API, không chỉ dựa vào tên `Export`.

## 6. Audit cho key storage phải ghi những trường gì?

Một record hữu ích thường gồm **thông tin định danh, ngữ cảnh chính sách, hành động, kết quả và liên kết truy vết**.

| Trường | Nội dung | Mục đích |
| --- | --- | --- |
| `eventId` | ID sự kiện duy nhất | Dedup và kiểm soát ingest |
| `requestId` / `correlationId` | Kết nối nhiều lớp | Ghép app ↔ policy ↔ provider |
| `eventTimeUtc` | Thời điểm có nguồn và timezone rõ | Timeline và phát hiện chậm trễ |
| `observedAtUtc` | Lúc collector nhận event | Đo độ trễ và phát hiện missing logs |
| `source` | Application, KMS, HSM, IAM, backup | Nguồn bằng chứng |
| `actor` | Workload/service identity hoặc người quản trị | Trách nhiệm hành động |
| `onBehalfOf` | Người dùng cuối/ủy quyền nếu xác minh được | Truy ngược business request |
| `keyId` / `keyVersion` | Resource và vật liệu/phân phiên cụ thể | Không nhầm alias |
| `purpose` | Mục đích được phê duyệt | Phát hiện cross-purpose |
| `action` | API/operation và loại sự kiện | Hiểu tác động |
| `decision` | Allow/deny hoặc not-applicable | Tách authorization khỏi execution |
| `outcome` | Success/failure/timeout/unknown | Không suy diễn từ request |
| `policyRevision` | Phiên bản policy đã xét | Điều tra thay đổi quyền |
| `environment` / `tenantScope` | Phạm vi đã xác thực | Ngăn lẫn prod/test/tenant |
| `approvalRef` | Quyết định hoặc ticket liên quan | Dual control và exception |
| `providerEventRef` | ID sự kiện KMS/HSM tương ứng | Đối chiếu thật |
| `reasonCode` | Nguyên nhân từ chối/hành động | Triage và phân loại |
| `logSchemaVersion` | Phiên bản định dạng | Đọc được sự kiện lịch sử |

**Không phải sự kiện nào cũng có tất cả trường.** Ví dụ HSM chỉ biết token role và key handle; ứng dụng mới biết tenant thực. Khi thiếu, đánh dấu `UNKNOWN` hoặc `NOT_APPLICABLE` theo schema; **không bịa** một principal hoặc business approval để “đủ cột”.

### Đừng chỉ log alias

Alias có thể đổi từ key v1 sang v2 sau khi request được khởi tạo. Để điều tra, nên ghi **key resource ID và version thực sự được provider sử dụng** nếu API có cung cấp; lưu alias/request routing như **metadata bổ sung**, không thay thế định danh vật liệu.

## 7. Ví dụ audit event — sử dụng KEK hợp lệ

Dữ liệu YAML sau là **schema minh họa nội bộ**, không phải đầu ra chuẩn của một KMS cụ thể:

~~~yaml
schemaVersion: "1"
eventId: "evt-2030-000042"
requestId: "req-9b6c"
correlationId: "corr-billing-5512"
eventTimeUtc: "2030-05-10T14:20:00Z"
observedAtUtc: "2030-05-10T14:20:02Z"
source: "kms-api"
actor:
  type: "WORKLOAD_IDENTITY"
  id: "billing-reader-prod"
resource:
  keyId: "billing-kek-v3"
  keyVersion: "v3"
  purpose: "DEK_KEY_WRAPPING"
  environment: "production"
  tenantScope: "tenant-a"
action: "UnwrapKey"
authorization:
  decision: "ALLOW"
  policyRevision: "policy-24"
  approvedOperation: "UnwrapKey"
execution:
  outcome: "SUCCESS"
  providerEventRef: "provider-event-ref"
businessContext:
  operationClass: "READ_ENCRYPTED_RECORD"
  approvedDataScopeRef: "scope-ref"
  dataRecordCount: 1
audit:
  sensitivity: "SECURITY_METADATA"
  classification: "RESTRICTED"
~~~

Dù event ghi `outcome=SUCCESS`, nó **không có nghĩa** người dùng đã đọc thành công đúng một hóa đơn. KMS chỉ biết operation ở phạm vi của nó. Cần đối chiếu với **application data-access event** để biết việc giải mã và trả dữ liệu có xảy ra.

### Những điều tuyệt đối không ghi

**Không đưa** vào log:

- Raw **DEK, KEK, HMAC secret, private key, ECDH shared secret** hoặc seed RNG.
- **PIN HSM, password, access token, session cookie, recovery code, reset token**.
- Plaintext hóa đơn, dữ liệu cá nhân/nhạy cảm không cần cho mục đích kiểm toán.
- Bản sao bộ nhớ, stack trace hoặc HTTP body chứa secret.
- Toàn bộ **ciphertext/wrapped key** nếu không có nhu cầu và quyền bảo vệ phù hợp.
- **Encryption context/AAD** chứa PII hoặc bí mật nếu hệ thống log trường này.

**Ngay cả hash của dữ liệu nhạy cảm cũng phải đánh giá**: nếu miền giá trị nhỏ hoặc dễ đoán, hash có thể cho phép dò đoán. Dùng event ID/reference, pseudonymization hoặc digest được thiết kế đúng threat model.

## 8. Những ai có thể truy cập kho khóa?

Phải audit **cả nhân dạng trực tiếp và quyền gián tiếp**.

### 8.1. Workload identity

Microservice có quyền `Decrypt`, `Sign` hoặc `Unwrap`. Khi một workload bị chiếm, log của KMS có thể vẫn ghi **principal hợp lệ**. Vì vậy cần ghép **deploy revision, request lineage, region, batch ID và business context** để phát hiện lạm dụng.

### 8.2. Key custodian và HSM admin

Họ có thể tạo key, đổi policy, backup, rotate hoặc disable. Họ **không mặc nhiên nên có quyền sử dụng `Sign/Decrypt`**. Cần giám sát những thao tác quyền cao và đặc biệt là **tự nâng quyền**.

### 8.3. Key owner và approver

Owner phê duyệt purpose, cryptoperiod, recovery hoặc destroy. Một event “đã phê duyệt” cần liên kết tới **request bất biến, key ID/version, operation, thời hạn và identity được xác thực**.

### 8.4. Cloud/root administrator

Một admin không có quyền `Decrypt` trực tiếp nhưng có thể **sửa IAM/key policy, tạo grant, đổi role trust, disable log hoặc cấp quyền cho mình** vẫn là đối tượng đặc biệt phải theo dõi.

### 8.5. Backup/DR operator

Người được phép tạo/khôi phục bản backup có thể tiếp cận vùng chứa key material theo cơ chế provider. `Restore` cần được phân loại như thao tác nhạy cảm, không chỉ là hoạt động lưu trữ thông thường.

### 8.6. Người có thể tắt audit

**Người quản trị collector, log storage hoặc SIEM** có thể tác động đến bằng chứng. Cần separation of duties để người dùng key không thể **tự xóa dấu vết** mà không bị phát hiện.

## 9. Auditing HSM và PKCS#11

Khi sử dụng **HSM**, một ứng dụng Java có thể gọi PKCS#11 qua provider hoặc native client. Cần phân biệt **API call của ứng dụng**, **event của token** và **quyết định IAM/role bên ngoài HSM**.

~~~mermaid
sequenceDiagram
    participant App as Java application
    participant P11 as PKCS#11 provider
    participant HSM as HSM token
    participant CL as HSM audit/collector
    participant AL as Application audit
    App->>P11: Signature.initSign(private key handle)
    P11->>HSM: Authenticate/session + Sign mechanism
    HSM-->>P11: Signature hoặc lỗi
    P11-->>App: Result/exception
    HSM-->>CL: HSM event nếu được cấu hình/hỗ trợ
    App->>AL: Business approval, key ref, request outcome
    CL->>AL: Đối soát timestamp/key handle/correlation nếu có
~~~

### Những sự kiện cần tìm hiểu ở từng HSM

- Token initialization, partition management, Security Officer login.
- User login/logout, session open/close và các lỗi xác thực.
- Tạo/import/wrap/unwrap key, thay attributes và object deletion.
- Key usage `C_Sign`, `C_Decrypt`, `C_DeriveKey`... **nếu sản phẩm ghi nhận**.
- Thay firmware, policy, role, backup/restore và quorum.
- Tamper alarm, self-test, entropy/DRBG warning và hardware fault.
- Cấu hình audit logging và trạng thái log buffer/export.

**Không mặc định mỗi lời gọi `C_Sign` đều sinh một event độc lập trong log HSM**. Một số thiết bị hạn chế chi tiết hoặc mức log; cần kiểm tra tài liệu, cấu hình, thử nghiệm và mức bảo đảm của sản phẩm.

### Key handle chưa đủ để đối chiếu

Trong PKCS#11, object/session handle có thể chỉ có ý nghĩa trong phạm vi session hoặc token. Nên có mapping đáng tin từ **`CKA_ID`, key label, certificate fingerprint hoặc provider key identifier** sang **key inventory ID/version**. Label không nhất thiết duy nhất; thay label cũng không đồng nghĩa thay key material.

### Cẩn trọng khi log lỗi HSM

Một exception có thể chứa thông tin driver, đường dẫn native library, token label hoặc dữ liệu ứng dụng. Hãy **sanitize** trước khi đưa vào log tập trung; ghi loại lỗi, mã sự kiện, correlation ID và tham chiếu nhà cung cấp đủ để điều tra.

## 10. Auditing managed KMS và API quyền cao

Một managed KMS thường cung cấp audit thông qua hệ thống log nền tảng cloud. **Tên API, khả năng log, các trường và độ trễ cụ thể tùy nhà cung cấp**.

### Kiểm soát hai nhóm hoạt động

**Data-plane cryptographic use**, ví dụ:

~~~text
GenerateDataKey / Encrypt / Decrypt
Sign / Verify / GenerateMac / VerifyMac
Wrap / Unwrap / ReEncrypt / Derive (nếu provider hỗ trợ)
~~~

**Control-plane administration**, ví dụ:

~~~text
CreateKey / ImportKey / EnableKey / DisableKey
RotateKey / UpdateKeyPolicy / CreateGrant / RevokeGrant
ScheduleDeletion / CancelDeletion / DeleteKey
ChangeAlias / ChangeRole / ChangeAuditConfiguration
~~~

Danh sách này **mang tính khái niệm**; không phải mọi tên operation tồn tại nguyên văn trên mọi API.

### Audit key use không đủ để biết input

Hệ thống KMS có thể log `Decrypt` và danh tính người gọi, nhưng không nhất thiết log plaintext/ciphertext — điều đó **thường là đặc tính bảo vệ dữ liệu, không phải lỗi**.

Để truy nguyên business operation, ứng dụng nên ghi **request ID, loại dữ liệu, version và phạm vi truy cập** mà không ghi bí mật. Không đưa PII vào trường encryption context hoặc request metadata có khả năng đi vào provider audit.

### Admin action phải được đối chiếu

Một lệnh `CreateGrant` có thể làm thay đổi quyền sử dụng key nhiều giờ hoặc nhiều tháng sau. Audit không nên chỉ theo dõi các lượt `Decrypt` mà bỏ qua **ai đã trao quyền `Decrypt`**.

## 11. Java keystore, file permission và điểm mù của host audit

Khi khóa được lưu trong **JKS/PKCS#12, PEM hoặc file nhạy cảm**, audit có những giới hạn khác HSM/KMS.

### OS file-open log không chứng minh key đã được dùng

Một event OS cho thấy tiến trình mở file `/secure/keystore.p12` có thể chỉ phản ánh load keystore khi khởi động. Sau đó ứng dụng có thể giữ private key trong memory và thực hiện hàng nghìn phép ký mà **không mở lại file**. Muốn audit sử dụng khóa phải có **instrumentation ở điểm gọi `Signature`/`Cipher` hoặc gateway**.

### Cần audit cả quyền truy cập file và thay đổi file

- ACL, owner, mode, group, mount và đặc quyền của process.
- Thao tác đọc, copy, restore, thay/ghi đè file.
- Cập nhật keystore password, credential source và key alias.
- Backup/snapshot, debugger, heap dump, crash dump và khả năng đọc RAM.
- Secret được đưa vào process qua environment, CI/CD hoặc container volume.

Không phải mọi hệ điều hành hay agent đều ghi lại đủ các event trên. Tổ chức cần lựa chọn kiểm soát **phù hợp rủi ro**, tránh kết luận “đã bật audit OS thì không còn đường lộ private key”.

## 12. Envelope encryption: vì sao log KMS có điểm mù?

**Envelope encryption** sử dụng **DEK** để mã hóa/giải mã dữ liệu, còn **KEK** trong KMS/HSM để bọc hoặc giải bọc DEK.

~~~mermaid
flowchart LR
    DB[(Ciphertext + wrapped DEK)] --> App[Ứng dụng]
    App --> Gate{DEK có trong cache?}
    Gate -->|Không| KMS[KMS/HSM Unwrap DEK]
    KMS --> Cache[DEK plaintext tạm trong memory]
    Gate -->|Có| Cache
    Cache --> AES[AES-GCM Decrypt + verify tag]
    AES --> Result[Dữ liệu được truy cập sau business authorization]
    KMS --> KL[KMS audit event]
    Result --> AL[Application data-access audit]
    Cache --> MET[Cache/security telemetry không chứa DEK]
    KL --> Join[Đối chiếu theo key version và request]
    AL --> Join
    MET --> Join
~~~

### Hai sự thật khác nhau

1. **KMS thấy thao tác `Unwrap`**: nghĩa là một yêu cầu giải bọc đến KMS và có kết quả theo log.
2. **Ứng dụng thấy thao tác `Decrypt` dữ liệu**: có thể xảy ra nhiều lần sau một lần unwrap, nếu DEK được giữ trong cache.

Vì vậy không thể suy ra:

~~~text
1 KMS Unwrap success == 1 record đã đọc
0 KMS Unwrap hôm nay == 0 dữ liệu đã giải mã hôm nay
Disable KEK == mọi ứng dụng lập tức dừng dùng DEK cached
~~~

Các phép tương đương này **sai trong thiết kế có cache/raw DEK ngoài KMS**.

### Thiết kế audit theo nhiều lớp

- Log **lần unwrap** với KEK ID/version và workload identity.
- Log **business data access** với record/scope reference có bảo vệ quyền, principal và quyết định.
- Quan sát **cache policy** như TTL, hit/miss tổng hợp và sự kiện invalidation; không in DEK.
- Có chiến lược **ngừng sử dụng DEK cached** khi suspend, compromise hoặc thu hồi principal.
- Liên kết **ciphertext ↔ wrapped DEK ↔ KEK version** để hỗ trợ điều tra và rotation.
- Kiểm tra hành vi khi service restart, failover hoặc chạy đồng thời ở nhiều vùng.

### Tại sao không đơn giản tắt DEK cache?

Không cache có thể giảm một số điểm mù nhưng tăng độ trễ/chi phí, đồng thời không loại bỏ khả năng raw DEK xuất hiện trong RAM trong lúc giải mã. Quyết định cache phải dựa trên threat model và kiểm soát thực tế, **không coi cache là mặc nhiên sai hoặc mặc nhiên vô hại**.

## 13. Audit quyền quản trị: grants, policy và dual control

Các thao tác trên **control plane** có thể gây hại hơn hàng nghìn lượt dùng hợp lệ. Ví dụ một admin sửa key policy để tự cấp quyền `Decrypt`, dùng quyền đó rồi khôi phục policy như cũ.

~~~mermaid
flowchart TD
    R[Yêu cầu đổi quyền / restore / destroy] --> Q[Request cố định: key ID, action, scope, revision]
    Q --> O[Key owner approval]
    Q --> S[Security approval độc lập khi cần]
    O --> C{Đủ quyền và còn hiệu lực?}
    S --> C
    C -->|Không| D[Từ chối và log]
    C -->|Có| E[Executor kiểm tra state và revision mới nhất]
    E -->|Không đạt| D
    E -->|Đạt| K[Thực thi tại IAM/KMS/HSM]
    K --> P[Provider audit event]
    P --> A[Đối soát request/approval/provider result]
    D --> A
~~~

### Một audit trail phê duyệt đáng tin phải có

- Request ID, **payload bất biến** hoặc digest được bảo vệ.
- Key ID/version, action, principal, scope và kỳ hạn.
- Người đề xuất, approver, executor; xác thực đủ mạnh và quyền thực tại thời điểm duyệt.
- Chính sách cần **hai người độc lập** hay một quyền ứng cứu đặc biệt?
- Time, decision, expiry, policy revision và trạng thái request.
- Provider event tương ứng và kết quả kiểm thử hậu thay đổi.

### Chống self-approval và self-escalation

Dual control sẽ thất bại nếu cùng một người có thể:

- Sửa bảng approvals, role, identity provider hoặc workflow code.
- Dùng hai account cùng thuộc quyền kiểm soát cá nhân.
- Tự thay key policy rồi cấp `Sign/Decrypt/Unwrap`.
- Xóa log provider hoặc thay retention sau khi thực thi.

**Audit phải theo dõi cả đường gián tiếp dẫn tới quyền**, không chỉ event `Decrypt`.

## 14. Bảo vệ log: toàn vẹn, chống sửa và khả năng truy vấn

Nhật ký chứa bằng chứng nhạy cảm. Nếu kẻ tấn công có thể xóa/sửa log sau khi dùng khóa, việc ghi log ban đầu không đem lại khả năng điều tra đáng tin.

### 14.1. Tách nơi ghi và nơi lưu

Một kiến trúc thường gồm:

~~~mermaid
flowchart TD
    K[KMS/HSM audit] --> C[Collector bảo vệ đường truyền]
    A[Application audit] --> C
    IAM[IAM và control-plane audit] --> C
    C --> S[Security log storage có retention và quyền riêng]
    S --> I[Integrity controls / append-only / WORM khi phù hợp]
    S --> Q[SIEM search, detection, correlation]
    Q --> IR[Incident response]
    C --> H[Health + lag + missing events monitoring]
~~~

Có thể dùng **append-only storage**, **WORM/immutable retention**, đối soát sequence number, ký bản ghi hoặc hash chain để tăng khả năng phát hiện sửa đổi; lựa chọn tùy hệ thống và mức bảo đảm.

### 14.2. Hash chain có những giới hạn gì?

Ví dụ:

~~~text
h0 = trustedInitialDigest
h1 = H(h0 || canonical(event1))
h2 = H(h1 || canonical(event2))
...
~~~

Một hash chain có thể giúp phát hiện thay đổi dữ liệu **nếu có anchor tin cậy được lưu ngoài vùng attacker có thể sửa**. Nhưng nếu attacker có thể tính lại toàn bộ chain rồi thay luôn anchor, chain không còn giá trị chứng minh. Nó cũng **không tự đảm bảo event đã được ghi từ đầu**.

### 14.3. Đồng bộ thời gian

Cần ghi **UTC và độ lệch/độ tin cậy của nguồn thời gian** khi cần. Hệ phân tán có thể có độ trễ ingest hoặc clock skew; không nên mặc định sắp xếp các log từ ba hệ thống chỉ theo timestamp là suy ra được thứ tự tuyệt đối của mọi thao tác.

Dùng **request ID, event ID, provider sequence và causal links** nếu có; phân biệt **event time** với **ingestion time**.

### 14.4. Retention khác nhau theo mục đích

Thời hạn giữ log phụ thuộc phân loại tài sản, yêu cầu pháp lý/tuân thủ, nhu cầu điều tra và chính sách dữ liệu cá nhân. Không mặc định “giữ mãi mãi”. Thiết kế cần có:

- Phân loại độ nhạy và **quyền chỉ đọc** cho auditor/SOC.
- Retention, legal hold, cơ chế xóa khi hết hạn.
- Khả năng truy vấn bản ghi cũ dù schema đã version hóa.
- Backup/DR của log và kiểm thử phục hồi.
- Cách phát hiện **collector ngừng nhận event** hoặc bị thay policy.

## 15. Log an toàn: audit không được biến thành kho bí mật

Đây là một trong những rủi ro nghiêm trọng nhất của **access audit cho key storage**: log lại **chính key material đang cố bảo vệ**.

### Không làm điều này

~~~java
// PHẢN VÍ DỤ - KHÔNG DÙNG:
logger.info("New DEK: " + java.util.Arrays.toString(dekBytes));
logger.info("HSM PIN = " + new String(pinChars));
logger.info("Decrypted invoice = " + plaintext);
~~~

Các dòng trên có thể đẩy key, PIN hoặc dữ liệu đã giải mã đến **SIEM, observability vendor, log archive, backup và nhiều người được quyền xem log**.

### Thay bằng metadata tối thiểu

~~~text
operation: DECRYPT_RECORD
keyId: billing-dek-v7
kekId: billing-kek-v3
actor: billing-reader-prod
tenantScopeRef: tenant-token
requestId: request-123
decision: ALLOW
outcome: SUCCESS
recordCount: 1
~~~

Không nên log bản ghi plaintext hoặc raw key, cũng không tự động log **toàn bộ request body**. Tránh đặt PII vào key labels, key IDs, event names hoặc custom encryption context; các trường metadata đó có thể bị sao chép sang log ở nhiều lớp.

### Data minimization và privacy

Đôi khi cần điều tra truy cập theo user/tenant, nhưng không có nghĩa tất cả log phải ghi **tên, email, số định danh khách hàng**. Có thể dùng **ID tham chiếu, pseudonymization và phân quyền truy vấn** theo chính sách; bảo đảm vẫn truy ngược được khi có thẩm quyền.

Không nhầm pseudonymization với **ẩn danh tuyệt đối**: correlation ID hoặc tenant reference vẫn có thể là dữ liệu nhạy cảm khi liên kết với nguồn khác.

## 16. Java 11+: ví dụ tạo audit event không chứa key material

Đoạn mã dưới đây minh họa một **policy gate** và event audit cho thao tác sử dụng key. Nó **không tạo hoặc sử dụng key thực**, không gọi KMS/HSM và không thay IAM. Mục tiêu là minh họa **deny được ghi nhận**, **success phải được phân biệt với allow**, và **chỉ ghi metadata được cho phép**.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Objects;

public final class KeyStorageAccessAuditDemo {

    enum Operation {
        SIGN, DECRYPT, UNWRAP, CHANGE_POLICY, DESTROY_KEY
    }

    enum State {
        PRE_ACTIVATION, ACTIVE, SUSPENDED,
        DEACTIVATED, COMPROMISED, DESTROYED
    }

    enum Decision {
        ALLOW, DENY
    }

    enum Outcome {
        NOT_EXECUTED, SUCCEEDED, FAILED
    }

    static final class KeyMetadata {
        final String id;
        final String purpose;
        final State state;
        final String approvedPrincipal;
        final long policyRevision;

        KeyMetadata(String id, String purpose, State state,
                    String approvedPrincipal, long policyRevision) {
            this.id = Objects.requireNonNull(id);
            this.purpose = Objects.requireNonNull(purpose);
            this.state = Objects.requireNonNull(state);
            this.approvedPrincipal = Objects.requireNonNull(approvedPrincipal);
            this.policyRevision = policyRevision;
        }
    }

    static final class AuditEvent {
        final Instant eventTime;
        final String requestId;
        final String actorId;
        final String keyId;
        final Operation operation;
        final Decision decision;
        final Outcome outcome;
        final long policyRevision;

        AuditEvent(Instant eventTime, String requestId, String actorId,
                   String keyId, Operation operation, Decision decision,
                   Outcome outcome, long policyRevision) {
            this.eventTime = Objects.requireNonNull(eventTime);
            this.requestId = Objects.requireNonNull(requestId);
            this.actorId = Objects.requireNonNull(actorId);
            this.keyId = Objects.requireNonNull(keyId);
            this.operation = Objects.requireNonNull(operation);
            this.decision = Objects.requireNonNull(decision);
            this.outcome = Objects.requireNonNull(outcome);
            this.policyRevision = policyRevision;
        }

        // Mã hóa event dạng các trường có phân cách cố định,
        // chỉ dùng các ID giả định đáng tin trong ví dụ này.
        String safeSummary() {
            return "time=" + eventTime
                    + " req=" + requestId
                    + " actor=" + actorId
                    + " key=" + keyId
                    + " op=" + operation
                    + " decision=" + decision
                    + " outcome=" + outcome
                    + " policyRev=" + policyRevision;
        }
    }

    interface AuditSink {
        void append(AuditEvent event);
    }

    static final class ConsoleAuditSink implements AuditSink {
        public void append(AuditEvent event) {
            // Chỉ demo. Production dùng structured logger/collector
            // chống sửa/xóa, có redaction và health monitoring.
            System.out.println(event.safeSummary());
        }
    }

    static Decision decide(
            KeyMetadata key, String actor, Operation operation) {
        if (key == null || actor == null || operation == null) {
            return Decision.DENY;
        }
        if (key.state != State.ACTIVE
                || !key.approvedPrincipal.equals(actor)) {
            return Decision.DENY;
        }
        // Ví dụ chỉ cho phép UNWRAP theo purpose đã duyệt.
        return operation == Operation.UNWRAP
                && "DEK_KEY_WRAPPING".equals(key.purpose)
                ? Decision.ALLOW
                : Decision.DENY;
    }

    static void handleRequest(
            KeyMetadata key, String actor, Operation operation,
            String requestId, Clock clock, AuditSink sink) {
        Objects.requireNonNull(key);
        Objects.requireNonNull(actor);
        Objects.requireNonNull(operation);
        Objects.requireNonNull(requestId);
        Objects.requireNonNull(clock);
        Objects.requireNonNull(sink);

        Decision decision = decide(key, actor, operation);

        // Demo chỉ audit QUYẾT ĐỊNH, không gọi HSM/KMS.
        // Vì không thực thi, outcome luôn NOT_EXECUTED.
        AuditEvent event = new AuditEvent(
                clock.instant(), requestId, actor, key.id,
                operation, decision, Outcome.NOT_EXECUTED,
                key.policyRevision);
        sink.append(event);

        if (decision == Decision.DENY) {
            throw new SecurityException("Key operation denied");
        }

        // Nếu đây là production, chỉ sau bước này mới gọi provider.
        // Phải ghi thêm event kết quả EXECUTION thành công/thất bại
        // với providerEventRef và correlationId.
    }

    public static void main(String[] args) {
        Clock clock = Clock.fixed(
                Instant.parse("2030-06-01T12:00:00Z"), ZoneOffset.UTC);
        AuditSink sink = new ConsoleAuditSink();

        KeyMetadata key = new KeyMetadata(
                "billing-kek-v3", "DEK_KEY_WRAPPING", State.ACTIVE,
                "billing-reader-prod", 24L);

        handleRequest(key, "billing-reader-prod",
                Operation.UNWRAP, "req-001", clock, sink);

        try {
            handleRequest(key, "unexpected-workload",
                    Operation.UNWRAP, "req-002", clock, sink);
            throw new AssertionError("Unauthorized actor must fail");
        } catch (SecurityException expected) {
            System.out.println("Denied request confirmed");
        }

        KeyMetadata suspended = new KeyMetadata(
                key.id, key.purpose, State.SUSPENDED,
                key.approvedPrincipal, 25L);

        try {
            handleRequest(suspended, "billing-reader-prod",
                    Operation.UNWRAP, "req-003", clock, sink);
            throw new AssertionError("Suspended key must fail");
        } catch (SecurityException expected) {
            System.out.println("Suspended request denied");
        }
    }
}
~~~

**Kết quả minh họa:**

~~~text
time=2030-06-01T12:00:00Z req=req-001 actor=billing-reader-prod key=billing-kek-v3 op=UNWRAP decision=ALLOW outcome=NOT_EXECUTED policyRev=24
time=2030-06-01T12:00:00Z req=req-002 actor=unexpected-workload key=billing-kek-v3 op=UNWRAP decision=DENY outcome=NOT_EXECUTED policyRev=24
Denied request confirmed
time=2030-06-01T12:00:00Z req=req-003 actor=billing-reader-prod key=billing-kek-v3 op=UNWRAP decision=DENY outcome=NOT_EXECUTED policyRev=25
Suspended request denied
~~~

### Những điểm ví dụ thể hiện

1. **Allow và execution success khác nhau**: `ALLOW` trong demo chỉ nói policy gate cho phép; **chưa có phép unwrap thật**.
2. **Deny cũng có giá trị audit**: hành vi gọi sai principal hoặc key suspended cần được ghi nhận.
3. **Không log secret**: không có DEK, KEK, plaintext, PIN hoặc access token trong event.
4. **Policy revision** giúp truy xét vì sao một yêu cầu bị chặn ở phiên bản policy nhất định.
5. **Yêu cầu về nguồn thời gian**: code dùng `Clock` để kiểm thử, nhưng runtime thật cần đồng bộ và theo dõi clock skew.

### Giới hạn cần giải quyết trong production

- **Không tin actor, key ID, request ID do caller tự nhập**. Phải lấy từ identity provider/control plane đáng tin, kiểm tra định dạng và encode/redact giá trị khi log.
- `safeSummary()` chỉ thích hợp cho **các ID kiểm soát trong demo**; dữ liệu không đáng tin có thể gây **log injection** qua xuống dòng/ký tự điều khiển. Dùng structured logger với schema và encoding/redaction chuẩn.
- **AuditSink là console**: không có integrity, durable delivery, retry, backpressure hay giám sát lỗi; không dùng làm hệ thống audit production.
- Không có key usage thực, tenant/data scope, business approval, cryptoperiod hoặc điều kiện provider.
- Không có **execution-result event** sau KMS/HSM, không có provider request ID và audit correlation.
- Nếu audit cần được coi là **điều kiện bắt buộc trước thao tác nhạy cảm**, phải định nghĩa hành vi khi sink thất bại (*fail closed* hoặc cơ chế journal/durable queue theo rủi ro). Không được mặc định `stdout` đã ghi là event đã lưu an toàn.
- Không giải quyết TOCTOU, event ordering, transaction, retry, duplicate events hay key material cached ngoài KMS.

**Bài học:** code audit phải **không phát tán bí mật** và phải cho biết **giới hạn của bằng chứng mà nó tạo ra**.

## 17. Access audit và trạng thái vòng đời khóa

Một yêu cầu dùng key hợp lệ hôm qua có thể **không còn hợp lệ hôm nay**, vì key state, cryptoperiod, IAM hoặc policy thay đổi.

| State / sự kiện | Audit cần xác minh | Nguy cơ |
| --- | --- | --- |
| **Pre-activation** | Key chưa được dùng production, các lần từ chối đã được ghi | Sử dụng trước phê duyệt |
| **Active** | Đúng principal/operation/purpose và thời hạn | Key bị dùng ngoài mục đích |
| **Suspended** | Operation mới phải bị chặn theo policy; audit deny và các ngoại lệ | Cache, session hoặc API bypass |
| **Deactivated** | Không còn new-use; legacy decrypt/verify nếu được phép | Writer cũ vẫn dùng v1 |
| **Compromised** | Điều tra mọi key use, credential, wrapped DEK và trust | Chỉ disable mà bỏ qua dữ liệu cũ |
| **Rotation** | New output dùng key v2; dữ liệu v1 được xử lý theo kế hoạch | Alias đổi nhưng key material không đổi |
| **Destroyed** | Provider xác nhận tiêu hủy và dữ liệu không còn phụ thuộc | Mất khả năng decrypt/restore |

### Đừng lẫn `Disabled` với `Destroyed`

**Disable** ở KMS có thể chặn operation nhưng vật liệu vẫn tồn tại. **Pending deletion** khác sự kiện **destruction completed**. Audit phải ghi **trạng thái provider thực sự** và các bước chuyển, không suy diễn chỉ từ tên nút trong giao diện.

### Audit sau rotation

Cần biết:

- Alias đã trỏ sang key nào tại thời điểm request.
- Key ID/material version nào **thực sự tạo ciphertext/chữ ký mới**.
- Những wrapped DEK nào còn phụ thuộc KEK cũ.
- Bản backup nào chưa migrate.
- Những API legacy `Decrypt/Unwrap/Verify` còn được phép.
- Ai đã phê duyệt và xác nhận điều kiện hủy v1.

## 18. Phát hiện bất thường: từ log sang hành động

Audit có giá trị cao khi **giúp phát hiện thay đổi rủi ro và phản ứng kịp thời**.

### 18.1. Những tín hiệu cần theo dõi

| Phát hiện | Giả thuyết rủi ro | Điều cần kiểm tra |
| --- | --- | --- |
| `Sign` tăng bất thường ngoài lịch phát hành | Signing oracle hoặc bị lạm dụng | Principal, artifact/digest approval, pipeline |
| `Unwrap` hàng loạt ở tenant lạ | Lộ grant hoặc khai thác dữ liệu | Scope/tenant, data-access logs, cache |
| `Decrypt` từ môi trường staging trên key production | Sai boundary hoặc credential bị lấy | Identity, IAM, network, config |
| `CreateGrant` rồi `Decrypt` ngay sau đó | Tự nâng quyền hoặc workflow sai | Admin change, approval, provider events |
| Nhiều `AccessDenied` trên một key | Quét quyền hoặc cấu hình lỗi | Principal, API sequence, nguyên nhân |
| Dùng key đã `SUSPENDED` mà provider vẫn success | Bypass, consistency hoặc cached secret | Key state, cache, session, vùng |
| `ScheduleDeletion` trên KEK còn dữ liệu phụ thuộc | Nguy cơ mất dữ liệu | Wrapped DEK mapping và backup |
| Tắt audit hoặc thay log retention gần thao tác key use | Cố che dấu | Quyền log admin và timeline |
| Key không còn provider calls nhưng app vẫn decrypt | DEK cached hoặc thao tác ngoài KMS | Application telemetry và data access audit |

### 18.2. Ngưỡng không nên tùy tiện

Ví dụ một batch job hợp lệ có thể gọi `Unwrap` hàng nghìn lần; ngược lại, **một** lần `Sign` trên CA root key không được phê duyệt đã là sự kiện nghiêm trọng.

Thiết kế alert nên dựa vào:

- **Purpose/risk tier của key**.
- Principal và **hành vi chuẩn** của workload.
- Thời điểm, region, tenant và environment.
- Số lượt gọi, tỷ lệ deny/success và changes trước/sau.
- Sự kiện có **approval tương ứng** hay không.
- Tác động thực tế lên dữ liệu/chữ ký.

### 18.3. Không chỉ nhìn một event

Một chuỗi **policy changed → grant created → decrypt burst → log disabled** có thể nguy hiểm hơn bốn event độc lập. Correlation engine cần nối các sự kiện với **actor, key ID, policy revision và khoảng thời gian hợp lý**, đồng thời chấp nhận độ trễ ingest.

## 19. Incident response dựa trên audit truy cập kho khóa

Khi một cảnh báo liên quan key storage xuất hiện, trước hết cần xác định **điều gì thực sự bị tiếp cận**.

### Runbook khái niệm

1. **Xác nhận event:** nguồn, key ID/version, principal, API, timestamp và event ID, không chỉ tin một dashboard tóm tắt.
2. **Đối chiếu identity:** principal có thực sự được phép, credential có khả năng bị chiếm hoặc tự nâng quyền không?
3. **Kiểm tra thay đổi gần kề:** IAM/key policy, grants, alias, key state, deployment, backup và log settings.
4. **Cô lập có kiểm soát:** thu hồi credential/grant, suspend key hoặc chặn operation theo mức rủi ro; cân nhắc tác động availability của KEK.
5. **Bảo toàn bằng chứng:** provider logs, application audit, key inventory, approval, data access logs, request correlation và trạng thái collector.
6. **Phân loại tác động:** raw private key/KEK/DEK lộ, hay chỉ API bị lạm dụng? Có cached DEK, signed output, JWT hoặc wrapped DEK bị lấy?
7. **Phạm vi dữ liệu lịch sử:** liệt kê ciphertext, DEK, chữ ký, tag HMAC và phiên ECDH/TLS chịu ảnh hưởng.
8. **Khắc phục:** rotate key/credential, rewrap hoặc re-encrypt đúng trường hợp, thu hồi chứng thư/JWKS/trust khi cần.
9. **Kiểm tra lại:** negative tests, tính nhất quán vùng, key state, IAM, audit ingestion và khôi phục nghiệp vụ.
10. **Hậu kiểm:** báo cáo evidence, nguyên nhân, thời điểm tác động, kiểm soát bổ sung và owner.

### Phân biệt các loại lộ

| Tình huống | Audit có thể chỉ ra | Hướng điều tra |
| --- | --- | --- |
| IAM credential bị lấy | API calls từ identity hợp lệ nhưng ngữ cảnh bất thường | Các grants và output đã trả, không chỉ raw key |
| Signing key non-exportable bị lạm dụng | `Sign` bất thường | Chữ ký trên nội dung nào, phát tới đâu, trust còn hiệu lực |
| KEK có quyền unwrap quá rộng | `Unwrap` cho nhiều scope | DEK nào có thể được giải bọc và dữ liệu tương ứng |
| Raw DEK bị lộ từ app/cache | Có thể **không có KMS event mới** | Heap/crash dump, app logs, data access, host compromise |
| Backup chứa key bị sao chép | Sự kiện storage/backup access | Vật liệu có thể khôi phục và quyền của người lấy |
| HSM admin bị chiếm | Policy/role/backup/destruction changes | Self-escalation, audit integrity, token state |

**Rotation không xóa được dữ liệu đã bị sao chép** và **disable private signing key không làm các chữ ký đã phát biến mất**. Audit giúp xác định phạm vi nhưng không đảo ngược việc lộ bí mật.

## 20. Kiểm thử khả năng audit trong production

Không nên chỉ thấy cấu hình “logging enabled” rồi kết luận hệ thống đạt yêu cầu.

### 20.1. Kiểm thử theo chuỗi end-to-end

~~~mermaid
sequenceDiagram
    participant T as Authorized test workload
    participant App as Application
    participant KMS as KMS/HSM
    participant L as Log collector/SIEM
    T->>App: Yêu cầu test có request ID
    App->>KMS: Operation với test key
    KMS-->>App: Success hoặc AccessDenied
    App-->>L: Business + decision event
    KMS-->>L: Provider event nếu hỗ trợ
    L->>L: Correlate event IDs/key ID/actor
    L-->>T: Kết quả kiểm tra coverage, latency và field completeness
~~~

### 20.2. Bộ test tối thiểu

1. **Allowed use:** Operation hợp lệ có đủ application + provider events với ID khớp.
2. **Denied use:** Principal sai, key suspended hoặc operation sai tạo event từ chối; không có success provider ngoài dự kiến.
3. **Admin change:** Tạo/revoke grant, sửa policy, đổi alias và disable tạo audit có chủ thể.
4. **Approval bypass:** Direct provider API ngoài workflow bị chặn; nếu thất bại, phát alert phù hợp.
5. **Secrets redaction:** Test với dữ liệu mô phỏng chứng minh log không có secret, PIN, token, plaintext hoặc HTTP body nhạy cảm.
6. **Cache path:** Một lần unwrap nhưng nhiều lần decrypt trong ứng dụng có **business data access events** và cache telemetry phù hợp.
7. **Collector outage:** Mất kết nối/queue đầy tạo cảnh báo; chính sách xử lý khi audit bắt buộc bị lỗi được thực thi.
8. **Replay/dedup:** Gửi lại event không gây đếm sai hoặc tạo chuỗi sự kiện giả.
9. **Clock skew:** Event đến chậm vẫn đối chiếu được bằng request ID và thời gian ingest.
10. **Tamper simulation:** Người dùng app/KMS không thể xóa/sửa log đã lưu ngoài quyền; thay cấu hình audit tạo cảnh báo.
11. **Backup/restore:** Sự kiện truy cập backup/DR và key restores được ghi và điều tra được.
12. **Lifecycle:** Sau rotation có thể truy ngược v1/v2 theo **key material/version thật**, không chỉ alias.
13. **Multi-region:** Mỗi vùng/partition/cụm HSM đều có log coverage theo chính sách.
14. **Incident tabletop:** Tái dựng timeline nghi lộ key chỉ từ những nguồn log và inventory sẵn có.

### 20.3. Đo chất lượng audit

| Chỉ số | Điều cần biết |
| --- | --- |
| **Event coverage** | Tỷ lệ loại operation quan trọng đã có nguồn event |
| **Ingestion latency** | Chênh lệch event time và arrival time |
| **Field completeness** | Bao nhiêu event có key ID, principal, result, correlation |
| **Deduplication accuracy** | Có đếm lặp do retry/collector không |
| **Provider–application correlation** | Bao nhiêu operation nối được hai lớp |
| **Tamper resistance** | Ai có thể sửa/xóa, hệ thống có phát hiện không |
| **Detection effectiveness** | Cảnh báo có bắt được các kịch bản test rủi ro |
| **Evidence retrieval** | Có truy vấn được event lịch sử theo retention |
| **Secret leakage count** | Có secret/PII trái chính sách xuất hiện trong log không |
| **Missing-event alarm** | Collector ngừng hoạt động có báo động kịp thời không |

**Không có con số chuẩn chung** cho mọi hệ thống. Target coverage, độ trễ, retention và cảnh báo cần gắn với key risk tier và các yêu cầu đã được phê duyệt.

## 21. Case study: phát hiện lạm dụng KEK của Billing

### Bối cảnh

Dịch vụ Billing dùng một KEK trong KMS để giải bọc DEK của hóa đơn. Một nhân viên triển khai sai IAM khiến service account của môi trường test có quyền gọi `Unwrap` trên KEK production.

### Những sự kiện cần nối

| Thời điểm minh họa | Nguồn | Event | Ý nghĩa |
| --- | --- | --- | --- |
| 10:00 | IAM/control plane | `GrantCreated` cho test identity | Quyền được mở rộng |
| 10:02 | KMS | `Unwrap` success bằng test identity | Tài nguyên đã thực hiện operation |
| 10:03 | Ứng dụng | Không có business request production tương ứng | Dấu hiệu dùng ngoài workflow |
| 10:04 | SOC rule | Cross-environment key access alert | Cần điều tra ngay |
| 10:07 | IAM | Grant revoked | Đã cô lập đường grant cụ thể |
| 10:10 | Incident log | Bắt đầu đánh giá wrapped DEK và output | Chưa được kết luận không lộ dữ liệu |

Mốc thời gian mang tính giả định, không biểu diễn SLA bắt buộc.

### Phân tích đúng

- `Unwrap` success là một tín hiệu đáng quan tâm: DEK plaintext có thể đã được trả ra, **tùy operation**.
- Không có log đọc dữ liệu từ ứng dụng **không bảo đảm dữ liệu không bị giải mã**, vì đối thủ có thể dùng DEK ngoài hệ thống nếu có ciphertext.
- Nếu **DEK đã lộ**, chỉ rotate KEK hoặc rewrap DEK là chưa đủ; cần đánh giá thay DEK/re-encrypt dữ liệu và tác động lịch sử.
- Disable KEK toàn phần có thể khiến ứng dụng hợp lệ không đọc được dữ liệu; trong một số trường hợp, thu hồi grant cụ thể là biện pháp cô lập chính xác hơn, phụ thuộc mức độ nghiêm trọng.
- Phải kiểm tra các service còn **DEK plaintext trong cache** và mọi key khác test identity có thể dùng.

### Bài học audit

**Không thể điều tra dựa trên log KMS đơn lẻ.** Timeline cần **IAM change + KMS use + application context + key inventory + bản đồ ciphertext/wrapped DEK**.

## 22. Case study: khóa ký HSM bị dùng ngoài lịch phát hành

Một pipeline ký artifact dùng private key non-exportable trong HSM. Ngoài lịch release, hệ thống phát hiện nhiều lượt `Sign` thành công.

### Những câu hỏi cần trả lời

1. Principal nào gọi `Sign`? Session/role HSM nào được sử dụng?
2. Digest/artifact ID đã ký có nằm trong danh sách release được phê duyệt?
3. Có hai approval độc lập cho exact manifest khi chính sách yêu cầu không?
4. Key version, certificate và thời điểm ký là gì?
5. Có artifact nào đã được công bố hoặc thiết bị nào còn tin chữ ký?
6. Quyền `Sign` đến từ grant cũ, policy change hay credential bị lấy?
7. Phải suspend key, thu hồi credential, phát public verification key mới hoặc cập nhật trust như thế nào?

### Điểm giới hạn

HSM **không tự hiểu digest đại diện artifact hợp lệ hay độc hại**. Nếu audit chỉ ghi “HSM đã Sign”, điều đó **không đủ** để kết luận release hợp lệ. Cần log business approval, manifest/digest reference, kiểm soát artifact provenance và log phát hành.

Khi private key đã lộ, việc thay cặp khóa và xử lý **certificate/JWKS/trust** là bài toán riêng; chữ ký cũ cần phân tích theo thời gian, chứng cứ và chính sách.

## 23. Những lỗi thường gặp khi audit key storage

| Sai lầm | Tác động | Cách khắc phục |
| --- | --- | --- |
| Chỉ ghi `success=true` | Không biết actor, key và operation | Schema rõ identity/action/resource/outcome |
| Coi allow là crypto success | Lẫn approval với thực thi | Ghi decision và provider result riêng |
| Chỉ log KMS, bỏ qua app | Không thấy business context và DEK cache | Đối soát KMS + app + data access |
| Chỉ log app, bỏ provider | Không phát hiện bypass trực tiếp | Cưỡng chế và ghi log tại IAM/KMS/HSM |
| Ghi raw DEK/KEK/private key “để dễ debug” | Log trở thành kho bí mật | Redaction, safe schema, tests |
| Ghi PIN/token hoặc HTTP body vào log | Rủi ro lộ credential và PII | Allowlist fields, không log payload nhạy cảm |
| Dùng alias làm key identifier duy nhất | Không phân biệt vật liệu v1/v2 | Resource ID và material version |
| Không log deny | Không phát hiện quét quyền | Ghi từ chối theo policy, chống log flood |
| Log không có policy revision | Không tái dựng được quyết định | Versioned policy + event |
| Không audit `CreateGrant`/policy changes | Admin tự mở quyền không bị thấy | Control-plane audit và alerts |
| Tin một log collector luôn nhận đủ | Mất sự kiện khi outage | Health/lag/coverage monitoring |
| Cho cùng admin sử dụng key và xóa log | Khó điều tra lạm dụng | SoD, immutable retention, independent audit |
| Chỉ dùng hash chain trong vùng attacker sửa được | Có thể sửa lại cả chain | External anchors và integrity controls |
| Không quản lý clock skew | Timeline sai | Event/ingestion time, request IDs |
| Không thử trực tiếp HSM/provider | Không biết key use log có thực | Test cơ chế audit theo product |
| Coi 0 API KMS calls là 0 data access | DEK cached hoạt động ngoài KMS | Business data audit và cache observability |
| Coi `Disabled` là key đã bị hủy | Sai trạng thái và xử lý dữ liệu | Kiểm tra lifecycle/provider |
| Không đối chiếu backup/DR | Bỏ sót key material bên ngoài vault chính | Audit backup/export/restore |
| Log chứa tenant/customer PII quá rộng | Xâm phạm dữ liệu cá nhân | Data minimization, access control và retention |
| Không cảnh báo log config bị tắt | Attacker che dấu hoạt động | Audit-the-auditor, tamper alerts |
| Mặc định log API success chứng minh business hợp lệ | Signing/decrypt oracle | Business approval và audit |
| Hủy log quá sớm hoặc giữ vô hạn | Thiếu chứng cứ hoặc tăng rủi ro dữ liệu | Retention/hold theo chính sách |

## 24. Checklist triển khai Access audit cho key storage

1. **Inventory:** Đã có key ID, version, purpose, owner, custodian, environment, tenant, nơi lưu và hệ phụ thuộc?
2. **Bản đồ điểm truy cập:** Những đường vào gồm KMS API, HSM/PKCS#11, file keystore, secret manager, backup/DR, admin console và cache?
3. **Event coverage:** Có ghi các thao tác đọc metadata, key use, policy/grant changes, key state, rotation, restore và destroy?
4. **Identity:** Principal được xác thực có thể quy trách nhiệm? Có theo dõi service account/shared admin credential?
5. **Business context:** Có loại dữ liệu, business approval, purpose/data scope, nhưng không lộ plaintext hoặc PII không cần thiết?
6. **Resource:** Event ghi **đúng key ID/version** thực dùng, không chỉ alias hoặc token slot?
7. **Decision/outcome:** Có phân biệt request, allow/deny, provider execution, success/failure và business result?
8. **Correlation:** Có request ID/event ID nối application, IAM và KMS/HSM; chấp nhận event đến chậm?
9. **KMS/HSM capability:** Đã xác minh event nào được vendor hỗ trợ và logging có thực sự bật?
10. **Java keystore:** Nếu khóa nằm trong file hoặc JVM, có audit sử dụng ở điểm call chứ không chỉ file open?
11. **DEK cache:** Có business data-access audit và cache policy để tránh điểm mù của KMS?
12. **Least privilege:** Workload chỉ dùng đúng key/operation; custodian không mặc nhiên có `Decrypt/Sign`?
13. **Indirect access:** Có theo dõi admin tự sửa IAM, grant, role trust, workflow và audit policy?
14. **Dual control:** Restore/export/destroy hoặc signing action rủi ro cao có approval độc lập, log được và gắn đúng request?
15. **Secret safety:** Có kiểm thử redaction, ngăn log raw keys, HSM PIN, session token, plaintext, sensitive context/AAD?
16. **Integrity:** Log storage có quyền riêng, retention bảo vệ, khả năng phát hiện xóa/sửa và bằng chứng audit admin?
17. **Time:** Có UTC, source time, ingestion time, clock drift/lag và ID giúp xây timeline?
18. **Retention:** Có chính sách giữ log và legal hold phù hợp, quyền truy vấn độc lập, cách xóa sau hết hạn?
19. **Detection:** Có alert theo purpose/risk tier cho Sign/Unwrap bất thường, cross-environment access, grant escalation?
20. **Incident response:** Có runbook khi IAM credential, KEK/DEK, signing key, HMAC key hoặc recovery secret bị lộ?
21. **Rotation:** Có đối chiếu output mới dùng version mới, legacy access và wrapped DEK còn phụ thuộc key cũ?
22. **Destroy:** Có event xác minh theo provider, dependency check và backup/DR trước khi kết luận vật liệu đã bị hủy?
23. **Negative tests:** Sai principal, tenant, purpose, operation, suspended key và API bypass có bị chặn và được ghi nhận?
24. **Collector fault:** Có giám sát ingestion, missing events, disk/queue/backpressure và chính sách fail-closed khi bắt buộc?
25. **DR drill:** Khi restore vault/log, có tìm được key metadata, approval và provider history cần cho điều tra?
26. **Đánh giá thường kỳ:** Owner/custodian/security/auditor có đối soát logs, policies, inventory và quyền truy cập bất thường?

### Ghi nhớ

**Access audit cho key storage** là hệ thống bằng chứng cho biết **ai đã yêu cầu hoặc thực hiện thao tác nào trên key nào, dưới quyền và chính sách nào, với kết quả gì**. Cần phân biệt **quyết định cho phép** với **phép toán đã thực thi**, và nối **application audit, control-plane audit, KMS/HSM provider logs**. Với **envelope encryption**, log `Unwrap` của KEK **không chứng minh mọi lần dùng DEK cached**; vì vậy phải bổ sung kiểm toán truy cập dữ liệu ở ứng dụng. Log cần **đầy đủ nhưng tối thiểu về dữ liệu**, không chứa raw key, HSM PIN, token hoặc plaintext, và được bảo vệ khỏi sửa/xóa với retention rõ ràng. Audit chỉ thật sự có giá trị khi đi cùng **IAM least privilege, kiểm soát key owner/custodian, dual control, giám sát bất thường, ứng cứu compromise, rotation và kiểm tra dữ liệu lịch sử**. Mục tiêu cuối cùng không phải “có nhiều log”, mà là **có thể tái dựng và chứng minh một cách đáng tin điều gì đã xảy ra với khóa mật mã — và phát hiện kịp thời khi điều đó không nên xảy ra**.

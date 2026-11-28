# Dấu hiệu compromise — Nhận biết khóa mật mã có thể bị lộ hoặc bị lạm dụng

## 1. Dấu hiệu compromise là gì?

**Dấu hiệu compromise** (*indicator of potential key compromise*) là quan sát hoặc bằng chứng khiến tổ chức có lý do nghi ngờ **vật liệu khóa mật mã đã mất tính bí mật, khả năng sử dụng khóa đã bị chiếm dụng, chính sách kiểm soát khóa bị vượt qua hoặc các bảo đảm bảo mật liên quan khóa không còn đáng tin**.

Một dấu hiệu **chưa chắc chứng minh raw key bytes đã bị sao chép**. Ví dụ:

- Hệ thống phát hiện `Sign` bất thường bằng private key trong HSM. Đó có thể là **lạm dụng quyền ký**, dù key material chưa rời HSM.
- Một tệp log chứa plaintext AES DEK. Đây là **bằng chứng xuất hiện key material ngoài vùng được phép**, ngay cả khi chưa biết ai đã đọc log.
- IAM ghi `AccessDenied` với hàng trăm yêu cầu `Decrypt`. Đây là **dấu hiệu dò quyền hoặc cấu hình sai**, không chứng minh dữ liệu đã bị giải mã.
- AES-GCM nonce bị lặp dưới cùng DEK. Hệ thống có thể mất bảo đảm mật mã dù **không có bằng chứng raw key bị lấy**.

Bài thuộc chương **Revocation và compromise** của mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**. Mục tiêu là nhận diện rủi ro trên toàn vòng đời khóa từ **tạo, cấp phát, lưu trữ, sử dụng, rotation, thu hồi đến hủy**, gắn với mật mã đối xứng/bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, phân quyền và kiểm toán.

> **Nguyên tắc điều tra:** Phải phân biệt **dấu hiệu**, **giả thuyết**, **bằng chứng xác nhận**, **ảnh hưởng thực tế** và **quyết định ứng cứu**. Không suy ra một điều chưa được chứng minh chỉ từ một log hoặc một cảnh báo.

### Mục tiêu học tập

Sau bài, người học có thể:

1. Phân loại dấu hiệu **key-material exposure, unauthorized key use, policy compromise, cryptographic failure và trust compromise**.
2. Xác định nguồn telemetry từ **KMS, HSM/PKCS#11, IAM, ứng dụng, CI/CD, filesystem, backup và PKI**.
3. Hiểu các dấu hiệu đặc thù của **DEK, KEK, private signing key, HMAC key, KDF master và key-agreement key**.
4. Đánh giá **chất lượng bằng chứng, confidence, false positive và mức độ ưu tiên**.
5. Thiết kế event schema, correlation rule và alert **không ghi raw key hoặc plaintext nhạy cảm**.
6. Thực hiện **bảo toàn bằng chứng, cô lập quyền và rotation/revocation** theo đúng loại sự cố.
7. Kiểm thử detection và lập checklist để phân biệt **“không có sự kiện”** với **“không có đường quan sát”**.

## 2. Phân biệt incident, indicator, suspicion và confirmed compromise

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Indicator** | Quan sát cần làm rõ | Một role mới gọi `Decrypt` vào đêm khuya |
| **Detection/alert** | Quy tắc hoặc hệ thống phát tín hiệu | SIEM phát alert vượt baseline |
| **Suspicion** | Có giả thuyết rủi ro hợp lý nhưng chưa đủ kết luận | Nghi credential của reader bị lấy |
| **Confirmed misuse** | Có bằng chứng key operation trái phép đã xảy ra | Provider ghi `Sign SUCCESS` trên manifest không được duyệt |
| **Confirmed material exposure** | Bằng chứng raw secret/private material tồn tại ngoài vùng đã cho phép | Raw DEK xuất hiện trong public artifact |
| **Impact assessment** | Xác định dữ liệu/trust/output chịu ảnh hưởng | 200 wrapped DEK có thể đã được unwrap |
| **False positive** | Tín hiệu giải thích được và không phải sự kiện ác ý theo chứng cứ | Batch migration đã được phê duyệt gọi 10.000 lần `Decrypt` |
| **Unknown** | Thiếu telemetry để xác nhận hoặc loại trừ | KMS log không lưu một nhóm API trong giai đoạn sự cố |

### “Nghi ngờ compromise” không có nghĩa phải chờ chắc chắn

Với key rủi ro cao, **đợi xác nhận raw key bị lấy** có thể tạo thêm thiệt hại. Incident team có thể **thu hồi credential, chặn grants, tạm dừng new-use, sinh key thay thế** theo risk tier trong khi tiếp tục điều tra.

### “Không có bằng chứng” có thể do không quan sát được

Một HSM có thể không log từng phép `C_Sign`; một ứng dụng có thể cache DEK rồi decrypt offline mà không gọi KMS. Do đó:

~~~text
Không thấy KMS Decrypt hôm nay
    ≠ không có AES Decrypt tại ứng dụng.

Không thấy ExportRawPrivateKey
    ≠ không có chữ ký trái phép.

Không thấy successful API trong log bị mất
    ≠ chứng minh không có API thành công.
~~~

**Kết luận phải nêu rõ phạm vi và giới hạn telemetry**.

## 3. Tài sản nào bị “compromise” và nguy cơ là gì?

Không chỉ có vật liệu bí mật. Một sự cố có thể ảnh hưởng nhiều lớp khác nhau.

| Tài sản hoặc quyền | Điều cần bảo vệ | Dấu hiệu đáng chú ý |
| --- | --- | --- |
| **Raw symmetric DEK** | Bí mật dữ liệu được mã hóa | DEK trong log, dump, secret store ngoài chính sách |
| **KEK trong KMS/HSM** | Đường bọc/giải bọc nhiều DEK | `Unwrap` bất thường, policy change, admin key export |
| **Private signing key** | Quyền tạo chữ ký đáng tin | `Sign` ngoài workflow, certificate/JWKS bị thay |
| **HMAC secret** | Xác thực messages giữa các bên | HMAC hợp lệ từ nguồn lạ, partner leak, replay |
| **KDF master/seed** | Nguồn của nhiều subkeys | Root/PRK/seed xuất hiện trong artifact hoặc memory |
| **Agreement private key** | Shared secret/session establishment | Key material leak, peer trust sai, session anomaly |
| **IAM credential/grant** | Quyền gọi operation | Credential bị đánh cắp, role trust mở quá rộng |
| **Key policy/alias** | Mapping và giới hạn sử dụng | `ChangePolicy`, `CreateGrant`, đổi alias ngoài change request |
| **Backup và recovery media** | Bản sao key cho khôi phục | Snapshot bị tải ngoài, restore trái phép |
| **Audit pipeline** | Bằng chứng đáng tin | Logging bị tắt, event gap, retention bị thay |

**Một incident có thể đồng thời chạm nhiều tài sản.** Ví dụ: quyền `Unwrap` bị lạm dụng có thể làm **lộ DEK plaintext** dù raw KEK trong HSM vẫn non-exportable.

## 4. Xây dựng threat model trước khi đọc log

Một hệ thống quản lý khóa an toàn phải biết:

- **Ai có quyền hợp lệ?** Workload, key owner, custodian, auditor, incident responder.
- **Key nằm ở đâu?** Managed KMS, HSM/PKCS#11, Java keystore, secret manager, mobile client, memory/cache.
- **Key có thể rời boundary không?** Raw export, wrapped export, `GenerateDataKey`, backup/restore.
- **Operation nào gây tác động?** `Encrypt`, `Decrypt`, `Sign`, `GenerateMac`, `Wrap`, `Unwrap`, `Derive`.
- **Dữ liệu nào phụ thuộc?** Ciphertext, wrapped DEK, token, chữ ký, TLS session, artifact phát hành.
- **Những đường quyền gián tiếp?** Sửa IAM, tạo grant, CI/CD deploy, debug process, log admin.
- **Khi không có log thì sao?** Cached key, offline cryptography, network outage, missing collector.

~~~mermaid
flowchart TD
    K[Key material và key usage] --> Storage[KMS/HSM/keystore/backup]
    K --> App[Application + in-memory DEK]
    K --> Trust[Certificate/JWKS/partner trust]
    Storage --> LS[Provider và admin audit]
    App --> LA[Business request và host telemetry]
    Trust --> LT[PKI/JWKS/issuer change logs]
    LS --> Correlation[Correlate key ID/version + principal + thời gian]
    LA --> Correlation
    LT --> Correlation
    Correlation --> Hypothesis[Giả thuyết compromise]
    Hypothesis --> Action[Cô lập + điều tra + xử lý theo impact]
~~~

**Không có một nguồn log nào quan sát được mọi hành vi liên quan khóa.** Mô hình cần phản ánh hệ thống thật, không lấy danh sách API của cloud provider A để suy đoán thiết bị B.

## 5. Nguồn telemetry nào đáng tin và nguồn nào có điểm mù?

| Nguồn | Có thể chứng minh | Điều không thể tự chứng minh |
| --- | --- | --- |
| **KMS API logs** | Principal/request/key operation và result nếu được bật và hỗ trợ | Local AES-GCM với DEK đã trả cho client |
| **HSM native audit** | Token login, admin, object operations, key usage tùy thiết bị | Nghiệp vụ và exact artifact approved |
| **IAM/control-plane logs** | Ai cấp grant, sửa key policy, role trust và resource | Raw key có thực sự bị lấy qua API khác không |
| **Ứng dụng/gateway** | User/tenant, data scope, business approval và outcome | Provider có thực sự làm phép toán, nếu app log sai |
| **Host/EDR/OS audit** | Process, file read, debugger, snapshot, dump, network | Raw material có chắc bị đọc từ memory không |
| **Secret manager** | Secret access/version/rotation | Những lần dùng raw secret sau khi lấy |
| **CI/CD, config audit** | Deploy revision, biến môi trường, artifact publication | Ai thực sự gọi decrypt offline |
| **Database/object storage** | Đọc wrapped DEK/ciphertext, snapshot export | Đọc ciphertext có đồng nghĩa decrypt thành công không |
| **PKI/JWKS** | Thay khóa công khai, certificate và trust | Private signing key có bị sao chép không |
| **Backup/DR** | Sao lưu, tải, restore/replicate | Bản copy của secret ngoài backup đó đã bị xóa chưa |

### Provider success khác application success

Một event `Decrypt SUCCESS` tại KMS cho biết **provider đã xử lý yêu cầu theo semantics API**, không nhất thiết chứng minh user được quyền đọc record đó. Ứng dụng cần log **business authorization** và kết quả trả dữ liệu riêng.

Một `AccessDenied` cho biết thao tác **đã bị từ chối ở điểm enforcement được ghi nhận**. Nó không tự chứng minh rằng caller không thể lấy cùng dữ liệu qua API khác.

## 6. Dấu hiệu vật liệu khóa xuất hiện ngoài vùng bảo vệ

Đây thường là nhóm có **độ ưu tiên cao** vì một khi bí mật đã được sao chép, revoke API ở nguồn có thể không còn ngăn đối thủ sử dụng bản sao.

### Các nơi cần theo dõi

1. Raw DEK, KEK, HMAC secret, private key hoặc seed được ghi vào **application log**.
2. PEM private key, PKCS#12/JKS với password bị lộ, key bytes nằm trong **public repository**.
3. Docker image/container layer, build artifact, CI job output hoặc IaC state chứa key.
4. Crash dump, heap dump, core file hoặc debugger session bị tải ra ngoài.
5. Backups, snapshots và object versions có key material bị đọc bởi principal không có quyền.
6. Clipboard, terminal history, process arguments hoặc temporary file chứa secret.
7. Raw key export từ hệ cho phép export nằm ngoài approval.
8. Private key được import vào HSM nhưng **bản sao trước import** vẫn tồn tại.
9. Recovery share/escrow material bị thu thập trái chính sách.
10. Key bytes được gửi qua chat/email/ticket hoặc HTTP request không có quy trình bảo vệ secret.

### Đánh giá đúng mức độ

Phát hiện **một pattern trông giống private key** chỉ là **tín hiệu ban đầu**. Cần xác minh artifact thực sự chứa key hợp lệ, còn hiệu lực, có liên quan resource production hay chỉ là **test fixture/public example**.

**Không in lại secret ra log hoặc SIEM để “đối chiếu”.** Dùng secret-scanning process hạn chế quyền, tham chiếu artifact/byte-range và fingerprint hoặc bằng chứng được thiết kế theo chính sách mà không lan truyền raw material.

### Không tự nhận là “an toàn vì đã xóa file”

Một khi raw secret xuất hiện ở repo/log, có thể tồn tại trong **git history, forks, caches, logs archive, backups hoặc các bản đã tải về**. Cần điều tra, rotation và thu hồi phù hợp thay vì chỉ xóa dòng đang hiển thị.

## 7. Dấu hiệu KMS key-use bất thường

KMS thường là điểm quan sát quan trọng đối với KEK và cryptographic API.

| Tín hiệu | Giả thuyết | Kiểm tra cần làm |
| --- | --- | --- |
| `Decrypt`/`Unwrap` từ service không thường dùng | Credential leak hoặc grant quá rộng | Principal, key ID, IAM policy history |
| Burst `Unwrap` trong khoảng ngắn | Dữ liệu/DEK có thể bị thu thập | Business batch approvals, wrapped DEK scope |
| Lệnh `Sign` ngoài lịch phát hành | Signing oracle bị lạm dụng | Manifest approval, release pipeline |
| `GenerateDataKey` tăng đột biến | DEK plaintext có thể được cấp quá rộng | API semantics, workload, tenant |
| `CreateGrant` rồi nhiều `Decrypt` | Self-escalation hoặc change bất thường | Approver, actor, policy revision |
| `DisableKey`/`ScheduleDeletion` bất ngờ | Phá hoại availability hoặc che dấu | Change ticket, owner, dependencies |
| Alias đổi từ key prod sang resource lạ | Redirect sử dụng key | Mapping trước/sau, environment |
| Deny liên tục nhiều key IDs | Quét quyền hoặc sai cấu hình | Key enumeration, user agent, host |
| Không có log như thường lệ | Collector/configuration failure | Health checks, baseline event flow |

### Đừng suy diễn quá mức

- Một `Decrypt SUCCESS` trên **KEK/managed key** không tự chứng minh raw KEK rời hệ thống.
- `GenerateDataKey` có thể trả **plaintext DEK** cho client, tùy API; phải phân biệt điều này với export KEK.
- Một batch đúng nghiệp vụ có thể dùng `Decrypt` hàng nghìn lần; lượng lớn **không tự là tấn công**.
- Nhiều `AccessDenied` có thể đến từ **deploy sai IAM**, dù vẫn là sự kiện cần xử lý.

**Mỗi alert nên có lý do rủi ro và thông tin đối chiếu, không chỉ một ngưỡng tùy tiện.**

## 8. Dấu hiệu HSM/PKCS#11 bị lạm dụng hoặc mất bảo đảm

HSM có thể giữ private key non-exportable, nhưng vẫn có những đường compromise:

- **Security Officer** hoặc key custodian login từ thời gian/thiết bị không hợp lệ.
- Nhiều lần thất bại HSM PIN, thay role hoặc session bất thường.
- `C_Sign`, `C_Decrypt`, `C_DeriveKey`, `C_WrapKey`/`C_UnwrapKey` được gọi ngoài allowlist, **nếu thiết bị có audit operation này**.
- Tạo/import/xóa object, sửa attributes, thay wrapping key hoặc key alias ngoài change request.
- Backup/restore hoặc cluster replication tới thiết bị/partition không mong muốn.
- Thay firmware, mechanism policy hoặc cấu hình audit.
- Tamper alarm, self-test error, entropy/DRBG failure.
- Log buffer đầy, audit daemon dừng, HSM clock drift hoặc mất đồng bộ.
- Đường quản trị out-of-band được sử dụng trái phép.

### Những attributes cần đối chiếu

| Thuộc tính điển hình | Vai trò trong đánh giá |
| --- | --- |
| `CKA_EXTRACTABLE` | Khả năng wrap/export material qua token theo policy |
| `CKA_SENSITIVE` | Hạn chế truy vấn giá trị key |
| `CKA_SIGN`/`CKA_DECRYPT` | Key object được phép thực hiện operation tương ứng |
| `CKA_WRAP`/`CKA_UNWRAP` | Key được dùng để bảo vệ/khôi phục key khác |
| `CKA_DERIVE` | Khả năng tạo key material dẫn xuất |
| `CKA_ID`/`CKA_LABEL` | Mapping đối tượng; **không bảo đảm uniqueness** |
| `CKA_ALWAYS_SENSITIVE`/`CKA_NEVER_EXTRACTABLE` | Provenance theo semantics token, **không chứng minh lịch sử trước import** |

**Không mặc định mọi HSM ghi log từng API call**. Cần kiểm tra cấu hình và tài liệu của thiết bị thật; không suy luận thiếu event là operation chưa xảy ra.

### Tamper alarm không phải một kết luận duy nhất

HSM có thể zeroize material hoặc khóa các operation trong một số điều kiện tamper; hành vi cụ thể phụ thuộc model, firmware và cấu hình. **Không khẳng định khóa đã hủy hoặc chưa lộ** trước khi đọc bằng chứng thiết bị và làm theo quy trình incident của nhà cung cấp.

## 9. IAM và control plane: dấu hiệu đường vòng cấp quyền

Nhiều sự cố không bắt đầu từ phá mật mã mà từ **đường quyền gián tiếp**.

### Chuỗi điển hình

~~~mermaid
sequenceDiagram
    participant A as Principal nghi vấn
    participant IAM as IAM/key policy
    participant KMS as KMS/HSM
    participant SOC as Detection
    A->>IAM: ChangePolicy/CreateGrant cho phép Decrypt
    IAM-->>SOC: Administrative audit event
    A->>KMS: Decrypt/Unwrap bằng quyền mới
    KMS-->>SOC: Cryptographic use audit event
    A->>IAM: Revoke grant/khôi phục policy
    IAM-->>SOC: Administrative audit event
    SOC->>SOC: Nối actor, key, thời điểm và approval
~~~

### Kiểm tra quyền nào?

- Ai có thể `CreateGrant`, đổi key policy, đổi IAM trust hoặc đổi role?
- Ai có thể **impersonate workload identity** và lấy token service?
- Ai có thể sửa code của encryption/signing gateway rồi triển khai?
- Ai được dùng **break-glass role**, trong điều kiện nào và ai phê duyệt?
- Ai có thể tắt audit hoặc giảm retention?
- Có ai được phép **thay key alias** mà không đổi material?
- Một principal ở staging có thể được chuyển quyền sang production không?

Một role **không có `Decrypt` hiện tại** vẫn có thể nguy hiểm nếu có quyền **tự cấp `Decrypt` rồi xóa dấu vết**.

### SoD và dual control

**Separation of duties (SoD)** giúp tách người đề xuất, phê duyệt, thực thi và kiểm toán thay đổi key policy. **Dual control** phù hợp với các hành động rủi ro cao như export KEK/private key, restore root key hoặc mở quyền `Sign/Decrypt` đặc biệt, nhưng không cần bắt hai người phê duyệt từng AES-GCM operation thông thường.

## 10. Dấu hiệu private signing key bị lạm dụng

Với private signing key, compromise có thể là **mất quyền kiểm soát việc ký**, không nhất thiết là lộ raw private material.

### Dấu hiệu có giá trị

1. `Sign SUCCESS` bằng key vốn chỉ dùng cho **release window** nhưng xảy ra ngoài lịch.
2. HSM nhận digest không xuất phát từ **artifact/manifest đã phê duyệt**.
3. JWT có chữ ký hợp lệ nhưng `issuer`, `audience`, `claims` hoặc `issuedAt` không phù hợp.
4. Số JWT/chứng thư/hóa đơn được ký vượt xa hành vi chuẩn.
5. `kid` hoặc signing certificate thay đột ngột, không khớp key inventory.
6. JWT/JWKS endpoint trỏ tới public key của resource lạ.
7. Signing service account bị lấy, dùng từ host/region không thuộc allowlist.
8. Quy trình CI/CD phát artifact có chữ ký nhưng không có **approval hoặc build provenance**.
9. Certificate được cấp hoặc thu hồi trái phép bằng CA/intermediate key.
10. Root/CA HSM backup hoặc signing credential được truy cập ngoài key ceremony.

### Đừng nhầm valid signature với valid business action

Một chữ ký RSA-PSS/ECDSA/Ed25519 được verify đúng **chứng minh quan hệ mật mã với key tương ứng**, nhưng **không chứng minh nội dung được owner phê duyệt** nếu hệ thống cho một caller ký digest tùy ý.

**Signing oracle** là vấn đề key-use authorization: raw private key có thể vẫn nằm trong HSM non-exportable, nhưng một API `Sign` quá rộng đã tạo chữ ký trái phép.

### Xử lý hậu quả

Điều tra **artifact đã ký, token đã phát, public trust, certificate validity, timestamp**. Rotation key pair và cập nhật trust có thể cần thiết, nhưng không tự động làm mọi chữ ký lịch sử hợp lệ hay không hợp lệ. Quyết định phụ thuộc evidence và chính sách xác minh.

## 11. Dấu hiệu compromise đối với DEK và AES-GCM

**DEK** là khóa trực tiếp mã hóa dữ liệu. Một số dấu hiệu không phải raw DEK leak nhưng vẫn làm bảo mật dữ liệu suy yếu.

### 11.1. DEK xuất hiện trong log hoặc RAM dump

Nếu `SecretKey.getEncoded()`, byte array hoặc plaintext DEK nằm trong log, tracing hoặc dump có quyền truy cập rộng, đó là **đường exposure** nghiêm trọng.

### 11.2. Nonce AES-GCM bị lặp

Với GCM, **không được dùng cùng nonce cho nhiều lần encrypt khác nhau dưới cùng key**. Sự cố có thể xảy ra do:

- Hard-code nonce.
- Multi-node counter cùng bắt đầu từ 0.
- Snapshot/restore làm lặp RNG/counter.
- Retry encrypt payload khác với nonce cũ.
- Nonce lấy từ ID không bảo đảm duy nhất.
- Vượt giới hạn số lần sử dụng key mà thiết kế chấp nhận.

Nonce reuse có thể ảnh hưởng **confidentiality và integrity** ngay cả khi không có bằng chứng raw DEK bị sao chép. Phải đánh giá ciphertext đã chịu ảnh hưởng, thay key và sửa nguồn nonce trước khi tiếp tục.

### 11.3. Authentication tag failure tăng bất thường

Nhiều lần AES-GCM tag verification fail có thể do:

- Ciphertext/tag bị sửa.
- Dùng nhầm DEK hoặc key version.
- AAD không khớp tenant/record/schema.
- Corruption do storage/replication.
- Lỗi migration hoặc bị tấn công.

**Tag failure không tự chứng minh attacker có key**; nhiều trường hợp chỉ là dữ liệu hỏng hoặc triển khai sai. Không bỏ qua tag để “đọc tạm” plaintext; làm vậy phá ranh giới xác thực.

### 11.4. Old-key new-use sau cutover

Nếu key-v1 đã deactivated nhưng vẫn tạo ciphertext mới, có thể có **writer cũ, stale cache, grant chưa thu hồi hoặc bypass policy**. Đối chiếu key material version thực tế thay vì chỉ tên alias.

## 12. Envelope encryption: KEK, wrapped DEK và điểm mù audit

Trong **envelope encryption**:

~~~text
DATA_CIPHERTEXT = AEAD-Encrypt(DEK, plaintext, nonce, AAD)
WRAPPED_DEK = Wrap(KEK, DEK)

KEK thường nằm trong KMS/HSM.
DEK có thể được ứng dụng nhận dạng plaintext tạm để xử lý dữ liệu.
~~~

~~~mermaid
flowchart TD
    Data[(Ciphertext + wrapped DEK)] --> App[Application reader]
    App --> Cache{Đã cache DEK plaintext?}
    Cache -->|Chưa| KMS[KMS/HSM Unwrap DEK]
    KMS --> Mem[DEK plaintext trong RAM theo API]
    Cache -->|Rồi| Mem
    Mem --> AES[AES-GCM Decrypt/Verify]
    AES --> Result[Business data access]
    KMS --> KLog[KMS audit]
    Result --> ALog[Application audit]
    KLog --> Correlate[Đối chiếu key/version, actor, request]
    ALog --> Correlate
~~~

### Những kết luận không được đưa ra

- **“KEK non-exportable nên không DEK nào có thể lộ”** — sai nếu `Unwrap` trả plaintext DEK.
- **“Không thấy `Unwrap` mới tức không có decrypt dữ liệu”** — sai khi DEK cached.
- **“Đã disable KEK nên mọi ứng dụng không thể giải mã”** — không bảo đảm nếu có DEK plaintext trong RAM.
- **“Đã rotate KEK nên dữ liệu bị lộ dưới DEK cũ an toàn trở lại”** — rewrap không thay raw DEK.
- **“Lấy được wrapped DEK là đã có plaintext DEK”** — không nhất thiết; cần kiểm tra unwrap capability/KEK.

### Câu hỏi phải điều tra

1. Credential nghi vấn có thể gọi **Decrypt/Unwrap/GenerateDataKey** nào?
2. Có **provider SUCCESS** trả plaintext DEK không?
3. Wrapped DEK nào bị tải từ database/object storage?
4. DEK version nào được dùng mã hóa dữ liệu nào?
5. Có cache, dump, application log hoặc bản sao DEK nào ngoài KMS?
6. Đối thủ có thể tự dùng DEK offline sau khi nhận plaintext không?
7. Nếu DEK có thể lộ, những ciphertext/backup nào cần đánh giá re-encrypt?

**Blast radius của KEK và DEK khác nhau**, nên không chọn rotation theo tên API đơn lẻ.

## 13. HMAC key: dấu hiệu giả mạo và phát lại thông điệp

**HMAC** sử dụng shared secret để tạo và kiểm tra MAC. Nếu có hai bên giữ cùng secret, compromise có thể đến từ bất kỳ bên nào.

### Chỉ dấu

- Webhook có MAC hợp lệ nhưng xuất hiện từ **client/partner identity** không hợp lệ.
- Message ID lặp lại, timestamp bất thường, sequence đảo ngược hoặc replay vượt ngưỡng.
- Partner thông báo secret bị đưa vào repository, ticket hoặc log.
- Một secret được tái sử dụng cho nhiều partner, làm tăng phạm vi.
- MAC verification thành công với **old key version** sau cutover.
- Có thay đổi message canonicalization hoặc key lookup khiến một tenant dùng key tenant khác.
- API `GenerateMac` tại KMS/HSM bị gọi ngoài workflow/host thường dùng.

### Một MAC hợp lệ chưa chắc là bằng chứng rò key

HMAC hợp lệ cũng có thể đến từ **sender hợp lệ** với một request được gửi lại hoặc metadata định danh sai. Cần đối chiếu **peer authentication, transport, request ID, message freshness, business permissions**.

### Anti-replay là lớp riêng

Rotation HMAC secret không tự chặn **replay của message cũ** nếu hệ thống không kiểm tra nonce/timestamp/message ID. Cần quy tắc chấp nhận thời gian và lưu trạng thái replay phù hợp.

## 14. KDF master, RNG và lỗi tạo khóa

Một master secret hoặc RNG lỗi có thể ảnh hưởng **nhiều keys** nhưng không tạo ra event `Export` hay `Decrypt` bất thường.

### Dấu hiệu master compromise

- Master/PRK/seed xuất hiện trong CI log, env dump, backup ngoài policy.
- HSM/KMS key derivation API được gọi với **context không thuộc purpose**.
- Cùng key material được import cho nhiều tenant/purpose.
- Parent key bị nghi lộ, trong khi các child keys vẫn được dùng cho new-use.
- HKDF `info` được nối mơ hồ, gây trùng context giữa vai trò/tenant.
- Root/KEK được backup/restore trên target không thuộc trust domain.

### Dấu hiệu RNG/DRBG lỗi

- Ứng dụng sinh key bằng `java.util.Random`, timestamp, PID hoặc seed có thể đoán.
- Chứng cứ hai key production trùng material ngoài thiết kế.
- HSM báo entropy/DRBG health test failure.
- Snapshot/restore hoặc khởi tạo container khiến **state RNG/counter** bị lặp.
- Nonce/ciphertext có mẫu lặp không phù hợp expected randomness.
- Lỗi firmware/provider công bố ảnh hưởng key generation của phiên bản đang dùng.

**Không suy ra RNG an toàn chỉ vì vài trăm key bytes khác nhau.** Chất lượng đến từ thiết kế DRBG/CSPRNG, entropy, provider, health checks và kiểm thử có phương pháp.

### HKDF domain separation

Ví dụ:

~~~text
PRK = HKDF-Extract(salt, master)
DEK = HKDF-Expand(PRK, "billing/v2/data-aes-gcm", 32)
MAC = HKDF-Expand(PRK, "billing/v2/webhook-hmac", 32)
~~~

Hai nhãn giúp tách purpose theo giả định HKDF an toàn, **nhưng nếu master bị lộ, đối thủ có thể tính lại cả hai subkeys**. Đổi nhãn trên **cùng master compromised** không khôi phục tính bí mật.

## 15. Agreement keys, TLS, certificate và public-key trust

### Static agreement key

Một ECDH/X25519 private key bị lộ có thể ảnh hưởng shared secrets hoặc sessions liên quan, tùy key schedule/giao thức. Dấu hiệu gồm:

- Private agreement key xuất hiện trong backup/log ngoài policy.
- Peer public key hoặc trust binding bị thay.
- Khóa static được dùng ở nhiều peer/trust domains sai mục đích.
- Session/key derivation activity bất thường.

**ECDH tự nó không xác thực peer.** Thiếu peer authentication có thể tạo MITM mà không cần raw private key bị lộ.

### TLS certificate private key

Dấu hiệu gồm chứng thư bất ngờ được cấp, private key lộ trong repo/host, certificate/key mismatch hoặc server bị kiểm soát. Phải phân biệt **chứng thư public được nhìn thấy** (bình thường) với **private key bị lộ**.

TLS hiện đại có thể có forward secrecy từ ephemeral key agreement, nhưng **không bảo đảm mọi traffic lịch sử an toàn** khi host/session secrets hoặc ticket keys cũng bị lấy. Impact assessment phải tách **authentication key, handshake/session key và ticket encryption key**.

### Thay đổi public trust

- JWKS endpoint xuất hiện `kid` không trong inventory.
- Certificate chain, issuer/trust anchor bị thay ngoài lịch.
- DNS/config redirect đến key source không đáng tin.
- CRL/OCSP hoặc distribution point có bất thường vận hành.
- Verifier chấp nhận algorithm hoặc key do input không đáng tin áp đặt.

Public key có thể công khai; **việc đổi nguồn trust** mới là dấu hiệu cần phân tích, không phải bản thân hành vi tải public key.

## 16. Backup, CI/CD và môi trường vận hành là nguồn lộ bí mật

Một key có thể được lưu an toàn trong KMS nhưng bị lộ tại **pipeline và những nơi dữ liệu đầu ra xuất hiện**.

### Các tín hiệu vận hành

| Nơi | Dấu hiệu |
| --- | --- |
| **CI/CD** | Private key hoặc secret xuất hiện trong build output; runner tải artifact chứa keys |
| **Container** | Secret trong image layer, env dump, init script, startup diagnostics |
| **Kubernetes/secret store** | Secret read/list từ service account không đúng scope |
| **OS/process** | Heap/core dump, attach debugger, memory inspection ngoài approval |
| **Network** | Raw key upload tới endpoint không được phép, traffic khác baseline |
| **DB/object store** | Bulk download wrapped DEK + ciphertext ngoài business request |
| **Backup** | Snapshot/restore ngoài lịch, bản sao chuyển vùng hoặc account lạ |
| **DR** | Key được restore vào test environment, audit của recovery thiếu |
| **Config management** | Key alias, secret reference, CA trust store đổi ngoài change ticket |

### Không biến điều tra thành sự cố mới

Khi săn tìm raw secrets trong artifacts, **không sao chép toàn bộ secret vào case ticket hoặc chat**. Dùng quy trình quét được phân quyền, chỉ lưu **artifact reference, loại mẫu, nơi phát hiện, thời gian và kết quả xác nhận**. Các tài liệu/bằng chứng chứa secret phải ở **vault hoặc kho forensics phù hợp**.

## 17. Thang chất lượng bằng chứng và độ tin cậy

Thang dưới đây chỉ là **hướng dẫn phân loại**, không phải công thức thay thế chuyên gia ứng cứu.

| Mức chứng cứ | Ví dụ | Điều có thể nói |
| --- | --- | --- |
| **Signal yếu** | Thời điểm gọi KMS khác thường | Cần điều tra; chưa biết có misuse |
| **Signal có ngữ cảnh** | `Decrypt` từ role mới + không có change approval | Nghi lạm dụng quyền |
| **Bằng chứng provider operation** | `Sign SUCCESS` ngoài allowlist được đối chiếu | Có thao tác ký bằng key đã xảy ra theo log |
| **Bằng chứng business misuse** | Artifact signed hash không khớp manifest approved | Output ký có thể không hợp lệ nghiệp vụ |
| **Bằng chứng material exposure** | Secret production bytes được xác minh trong artifact công khai | Key material đã xuất hiện ngoài boundary |
| **Bằng chứng tác động dữ liệu** | Log/data trail cho thấy record được đọc và trả ngoài scope | Có dấu hiệu/khẳng định tác động theo độ tin cậy evidence |
| **Không đủ telemetry** | Log collector tắt trong cửa sổ sự cố | Không được kết luận “không compromise” |

### Confidence không phải severity

- **Confidence:** mức chắc chắn giả thuyết đúng.
- **Severity:** tác động có thể xảy ra và độ khẩn cấp.
- Một raw CA private key **có thể lộ** nhưng chưa chắc chắn vẫn có thể là sự kiện **severity rất cao**.
- Một `AccessDenied` đã xác nhận là thất bại có confidence cao nhưng impact có thể thấp.

Cần ghi **cả hai** để tránh lẫn “chưa chắc chắn” với “không cần phản ứng”.

## 18. Các trường audit event cần thiết để phát hiện compromise

Một schema hữu ích phải cho phép nối **actor–action–resource–time–decision–outcome–purpose–scope**.

~~~yaml
schemaVersion: "1"
eventId: "evt-2030-0301"
eventTimeUtc: "2030-05-12T09:12:00Z"
observedAtUtc: "2030-05-12T09:12:02Z"
source: "KMS_AUDIT"
correlationId: "corr-billing-1001"
actor:
  principalId: "billing-reader-prod"
  identityAssurance: "WORKLOAD_IDENTITY"
  sourceEnvironment: "production"
resource:
  keyId: "billing-kek-v3"
  materialVersion: "v3"
  registeredPurpose: "DEK_KEY_WRAPPING"
request:
  operation: "Unwrap"
  intendedPurpose: "READ_INVOICE"
  tenantScopeReference: "tenant-a"
authorization:
  decision: "ALLOW"
  policyRevision: "kms-policy-24"
execution:
  outcome: "SUCCESS"
  providerEventReference: "provider-event-id"
review:
  observedAnomaly: "UNWRAP_OUTSIDE_BUSINESS_REQUEST"
  incidentConfidence: "INVESTIGATING"
  approvalReference: "NONE_FOUND"
  containsKeyMaterial: false
~~~

**Schema trên là minh họa**, không phải cấu trúc audit chuẩn chung của mọi provider.

### Không thể bắt mọi nguồn có đủ trường

HSM token log có thể biết key handle, operation và token role nhưng **không biết tenant/business purpose**. Event collector phải thể hiện trường thiếu bằng **UNKNOWN/NOT_APPLICABLE**, không bịa một người dùng cuối.

### Không ghi những dữ liệu này

- Raw DEK/KEK/HMAC secret/private key/KDF master/seed.
- Plaintext nhạy cảm, HSM PIN, session token, password.
- Full request body hoặc encryption context có PII không cần thiết.
- Heap dump trực tiếp trong SIEM.
- Toàn bộ wrapped key/ciphertext nếu không có yêu cầu và bảo vệ tương ứng.

**Audit phải giúp điều tra mà không trở thành kho bí mật mới.**

## 19. Đối chiếu các lớp log để dựng timeline

Một cảnh báo thường chỉ có ý nghĩa khi ghép với những sự kiện khác.

~~~mermaid
flowchart LR
    IAM[Policy/grant changes] --> Join[Correlation engine]
    KMS[Key-use events] --> Join
    APP[App authorization/data access] --> Join
    CICD[Deployment/CI history] --> Join
    BACKUP[Backup/restore activity] --> Join
    Join --> T[Timeline: key ID + actor + request ID + UTC]
    T --> H[Hypotheses: misuse/exposure/config error]
    H --> R[Risk assessment + evidence preservation]
~~~

### Điều gì nên liên kết?

- **Key ID/material version:** không chỉ alias “current”.
- **Principal identity:** service account, impersonated role và session lineage.
- **Correlation/request ID:** ghép KMS request với business operation nếu có.
- **Policy revision:** tại thời điểm gọi operation, ai đã cho phép?
- **Event time/ingest time:** phát hiện clock skew và log delay.
- **Tenant/environment/region:** cross-scope/cross-environment use.
- **Approval reference:** release, migration, backup, incident break-glass.
- **Provider result:** allow khác success; timeout khác deny.
- **Data/asset reference:** wrapped DEK, ciphertext, artifact digest, certificate fingerprint.

### Trình tự có thể không hiển nhiên

Clock skew và ingest lag khiến event B xuất hiện trên dashboard trước event A dù thực tế A xảy ra trước. Dùng **causal/request IDs, provider sequence, revision, trusted timestamps** khi có thể. Không ghép máy móc dựa trên timestamp đến từng mili-giây nếu nguồn thời gian khác nhau.

## 20. Rule detection nào hữu ích?

Các rule dưới đây là **mẫu logic**, không phải SIEM query chạy trực tiếp trên mọi nền tảng.

| Rule | Điều kiện minh họa | Vì sao đáng điều tra |
| --- | --- | --- |
| **Unexpected Sign** | `Sign SUCCESS` ngoài release window và thiếu approved digest | Key có thể bị dùng làm signing oracle |
| **Grant → Decrypt** | `CreateGrant` rồi `Decrypt` cùng key/actor trong cửa sổ ngắn | Có thể tự nâng quyền |
| **Cross-environment** | staging identity gọi production key | Lỗi trust boundary hoặc credential leak |
| **Unwrap without business request** | Provider `Unwrap` nhưng không có app authorization tương ứng | Có thể bypass đường ứng dụng |
| **Old key new-use** | Key đã deactivated vẫn `Encrypt`/`Sign SUCCESS` | Fencing/rotation chưa hiệu lực |
| **Export/Backup anomaly** | Export, restore, snapshot ngoài change request | Có thể material copy |
| **HSM admin anomaly** | SO login/partition change bất thường | Rủi ro key object/roles |
| **Audit configuration change** | Logging disabled hoặc retention giảm gần key-use event | Có thể che dấu |
| **GCM integrity spike** | Tag failures tăng, cùng keyVersion và shard | Sai key/AAD/corruption hoặc attack |
| **Secret discovery** | Validated production secret xuất hiện trong artifact | Direct material exposure |
| **Public trust change** | JWKS/cert issuer/key khác inventory | Key substitution hoặc roll-over sai |
| **KDF context misuse** | Derive bằng context tenant khác | Cross-purpose/tenant key access |

### Ví dụ truy vấn sự kiện quan hệ

~~~sql
-- PSEUDO SQL: tên bảng/trường và time handling tùy hệ SIEM.
SELECT g.actor, g.key_id, g.event_time AS grant_time,
       d.event_time AS decrypt_time, d.provider_ref
FROM key_events g
JOIN key_events d
  ON g.key_id = d.key_id
 AND g.actor = d.actor
WHERE g.action = 'CREATE_GRANT'
  AND g.outcome = 'SUCCESS'
  AND d.action IN ('DECRYPT', 'UNWRAP')
  AND d.outcome = 'SUCCESS'
  AND d.event_time >= g.event_time
  AND d.event_time < g.event_time + INTERVAL '10' MINUTE;
~~~

**Một match chưa chứng minh hành vi ác ý**. Phải so với **approved change, business migration, source identity và key purpose**.

### Không tự động disable toàn bộ KEK chỉ vì một điểm bất thường

Auto-containment cần risk tier và guardrails; nếu key bảo vệ dữ liệu trọng yếu, disable có thể gây mất khả dụng rộng. Có thể **chặn principal/grant cụ thể** trước, đồng thời tăng severity khi có bằng chứng raw exposure hoặc root/signing-key abuse.

## 21. Baseline, false positive và độ ưu tiên

### Dùng baseline có ngữ cảnh

Một job backup hợp lệ có thể gọi `Decrypt/Unwrap` với volume lớn vào cuối tháng; signing CA root có thể chỉ ký vài lần mỗi năm. Không dùng một threshold cho mọi key.

Xây baseline theo:

- **Purpose/risk tier** của key.
- Workload principal và deployment revision.
- Giờ hoạt động, release schedule, scheduled migration/backup.
- Tenant, region, environment và data classification.
- `allow/deny` tỷ lệ và các `errorCode`.
- Key state, cryptoperiod và key usage limit.
- Mức độ đầy đủ của audit sources.

### Ma trận severity × confidence minh họa

| Dấu hiệu | Confidence ban đầu | Severity tiềm năng | Quyết định đầu |
| --- | --- | --- | --- |
| 10 deny từ service mới deploy | Thấp/trung bình | Thấp đến trung bình | Kiểm tra config/IAM |
| `Sign SUCCESS` ngoài approved release | Trung bình/cao nếu log đáng tin | Cao | Chặn đường ký, điều tra output |
| Raw DEK production được xác minh ở public artifact | Cao | Cao | Incident secret exposure, thay key |
| HSM root/CA private key export bất thường | Tùy evidence; rất cần xác minh | Rất cao | Cô lập quyền, PKI/HSM incident |
| `Decrypt` volume lớn theo batch đã duyệt | Trung bình về event | Tùy scope | Đối chiếu approval, không auto-escalate |
| Audit collector mất toàn bộ log | Cao về mất telemetry | Có thể cao | Khôi phục logging và điều tra blind window |

**Mức độ cụ thể phụ thuộc hệ thống**. Một trường hợp hiếm với tác động lớn có thể cần hành động ngay dù chưa chứng minh kẻ tấn công.

### Khi đã loại trừ cảnh báo

Lưu lại **vì sao** đó là false positive, bằng chứng nào được xem, change ticket nào liên quan. Đừng tạo allowlist vĩnh viễn cho một principal chỉ vì một lần batch hợp lệ.

## 22. Java 11+: ví dụ phát hiện chuỗi sự kiện đáng ngờ

Mã dưới đây minh họa **phân tích metadata audit** mà không đụng raw key. Mục tiêu là tìm các dấu hiệu:

1. `Sign SUCCESS` ngoài cửa sổ phát hành đã phê duyệt.
2. `Unwrap SUCCESS` từ principal khác workload được phép.
3. `CreateGrant SUCCESS` rồi `Unwrap SUCCESS` trên cùng key/principal trong một khoảng ngắn.
4. Key đã `DEACTIVATED` mà còn `Encrypt SUCCESS`.

**Đây là rule engine giáo dục, không tự động kết luận compromise hoặc gọi API vô hiệu khóa.** Production phải lấy event từ nguồn đã xác thực, đối chiếu approval, scope, event completeness và yêu cầu xử lý backfill/clock skew.

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class KeyCompromiseSignalsDemo {

    enum Action { CREATE_GRANT, UNWRAP, SIGN, ENCRYPT, CHANGE_POLICY }
    enum Outcome { SUCCESS, DENIED, FAILED, UNKNOWN }
    enum KeyState { ACTIVE, SUSPENDED, DEACTIVATED, COMPROMISED }

    static final class Event {
        final String eventId;
        final Instant time;
        final String actor;
        final String keyId;
        final Action action;
        final Outcome outcome;
        final KeyState keyState;
        final boolean approvedBusinessWindow;

        Event(String eventId, String time, String actor, String keyId,
              Action action, Outcome outcome, KeyState keyState,
              boolean approvedBusinessWindow) {
            this.eventId = eventId;
            this.time = Instant.parse(time);
            this.actor = actor;
            this.keyId = keyId;
            this.action = action;
            this.outcome = outcome;
            this.keyState = keyState;
            this.approvedBusinessWindow = approvedBusinessWindow;
        }
    }

    static final class Finding {
        final String reason;
        final String keyId;
        final String eventId;

        Finding(String reason, String keyId, String eventId) {
            this.reason = reason;
            this.keyId = keyId;
            this.eventId = eventId;
        }

        public String toString() {
            return "reason=" + reason + " key=" + keyId
                    + " event=" + eventId;
        }
    }

    static List<Finding> detect(List<Event> input,
                                Set<String> approvedUnwrapActors) {
        List<Event> events = new ArrayList<>(input);
        events.sort(Comparator.comparing(e -> e.time));
        List<Finding> findings = new ArrayList<>();
        Set<String> seenIds = new HashSet<>();
        List<Event> grants = new ArrayList<>();

        for (Event event : events) {
            // Dùng ID để chống đếm lặp; production còn cần schema validation.
            if (event.eventId == null || !seenIds.add(event.eventId)) {
                continue;
            }

            if (event.action == Action.CREATE_GRANT
                    && event.outcome == Outcome.SUCCESS) {
                grants.add(event);
            }

            if (event.outcome != Outcome.SUCCESS) {
                continue;
            }

            if (event.action == Action.SIGN
                    && !event.approvedBusinessWindow) {
                findings.add(new Finding(
                        "SIGN_OUTSIDE_APPROVED_WINDOW",
                        event.keyId, event.eventId));
            }

            if (event.action == Action.UNWRAP
                    && !approvedUnwrapActors.contains(event.actor)) {
                findings.add(new Finding(
                        "UNEXPECTED_UNWRAP_PRINCIPAL",
                        event.keyId, event.eventId));
            }

            if (event.action == Action.ENCRYPT
                    && event.keyState == KeyState.DEACTIVATED) {
                findings.add(new Finding(
                        "NEW_USE_AFTER_DEACTIVATION",
                        event.keyId, event.eventId));
            }

            if (event.action == Action.UNWRAP) {
                for (Event grant : grants) {
                    boolean sameActorAndKey =
                            grant.actor.equals(event.actor)
                            && grant.keyId.equals(event.keyId);
                    long seconds = Duration.between(
                            grant.time, event.time).getSeconds();
                    if (sameActorAndKey
                            && seconds >= 0 && seconds <= 600) {
                        findings.add(new Finding(
                                "GRANT_THEN_UNWRAP",
                                event.keyId, event.eventId));
                        break;
                    }
                }
            }
        }
        return findings;
    }

    public static void main(String[] args) {
        List<Event> events = Arrays.asList(
            new Event("e1", "2030-05-10T09:00:00Z",
                "migration-worker", "billing-kek-v3",
                Action.CREATE_GRANT, Outcome.SUCCESS,
                KeyState.ACTIVE, true),
            new Event("e2", "2030-05-10T09:03:00Z",
                "migration-worker", "billing-kek-v3",
                Action.UNWRAP, Outcome.SUCCESS,
                KeyState.ACTIVE, true),
            new Event("e3", "2030-05-10T10:15:00Z",
                "release-signer", "release-signing-v5",
                Action.SIGN, Outcome.SUCCESS,
                KeyState.ACTIVE, false),
            new Event("e4", "2030-05-10T10:16:00Z",
                "old-writer", "billing-dek-v1",
                Action.ENCRYPT, Outcome.SUCCESS,
                KeyState.DEACTIVATED, false)
        );

        Set<String> approvedUnwrapActors =
                new HashSet<>(Arrays.asList("billing-reader-prod"));

        for (Finding finding : detect(events, approvedUnwrapActors)) {
            System.out.println(finding);
        }
    }
}
~~~

### Kết quả minh họa

~~~text
reason=UNEXPECTED_UNWRAP_PRINCIPAL key=billing-kek-v3 event=e2
reason=GRANT_THEN_UNWRAP key=billing-kek-v3 event=e2
reason=SIGN_OUTSIDE_APPROVED_WINDOW key=release-signing-v5 event=e3
reason=NEW_USE_AFTER_DEACTIVATION key=billing-dek-v1 event=e4
~~~

### Giới hạn rõ ràng của demo

- Trường `approvedBusinessWindow` trong code là **dữ liệu giả lập**, không phải nguồn approval tin cậy. Production phải xác minh quyết định nghiệp vụ bằng hệ thống phê duyệt độc lập.
- `grant.actor == unwrap.actor` không đầy đủ cho **grant delegatee**: ở thực tế người tạo grant và người nhận grant thường **khác nhau**. Phải đọc exact grant target, resource, IAM lineage và policy semantics của provider.
- Trạng thái `DEACTIVATED` gắn vào event là ví dụ; production cần **state at event time**, không suy từ trạng thái hiện tại.
- Rule không kiểm tra scope/tenant, trusted event sources, tamper, clock skew, late events hoặc duplicate ID giữa nguồn khác nhau.
- Code chỉ xử lý input trong RAM; production cần windowed streaming, dedup, persistence, event schema validation, replay và backfill.
- Không có cơ chế tự ngăn key misuse; **finding không phải enforcement**.
- Không log raw keys/private material; các ID vẫn cần **input encoding** để tránh log injection nếu lấy từ dữ liệu không đáng tin.
- Mỗi finding là **đầu mối điều tra**, không tự xác nhận compromise.

## 23. Từ dấu hiệu đến ứng cứu: 15 phút đầu cần gì?

Mục tiêu trong giai đoạn đầu là **giảm nguy cơ tiếp diễn và bảo vệ chứng cứ**, không nhất thiết phải hủy key ngay.

### Runbook khái niệm

1. **Mở incident:** gán ID, owner/incident commander, severity/confidence và phạm vi ban đầu.
2. **Xác minh signal:** nguồn log, event ID, thời điểm UTC, operation, key ID/version, actor, outcome.
3. **Bảo toàn bằng chứng:** snapshot policy revisions, KMS/HSM audit, app logs, approvals, CI/CD và backup events.
4. **Xác định cửa sổ phơi nhiễm:** earliest plausible exposure, thời điểm phát hiện, lần operation cuối đã biết.
5. **Cô lập đường nghi vấn:** thu hồi credential, grant, session; chặn đường trực tiếp `Sign/Decrypt/Unwrap`.
6. **Đánh giá availability:** key dùng để giải mã những dữ liệu nào và việc disable ảnh hưởng gì?
7. **Phân loại material:** raw key exposure hay API misuse, hay lỗi crypto/nonce/RNG?
8. **Thông báo owner/custodian/security/partner** theo chính sách.
9. **Chuẩn bị key mới trong vùng sạch** nếu risk assessment yêu cầu; không sinh bằng RNG/host đang nghi compromised.
10. **Mở investigation và remediation plan** với người chịu trách nhiệm, trạng thái và evidence.

Không có **SLA 15 phút chung** cho mọi tổ chức; tiêu đề chỉ nhấn mạnh các hành động **ưu tiên sớm**.

### Bảo toàn nhưng không phát tán bí mật

Những evidence có thể chứa raw key cần được xử lý trong **forensic vault hoặc kênh điều tra bảo vệ cao**, với quyền tối thiểu. Không đính kèm private key plaintext vào ticket để thuận tiện trao đổi.

## 24. Khi nào phải rotate, revoke hay tạm dừng sử dụng?

Các hành động này có ý nghĩa khác nhau.

| Hành động | Hiệu quả | Giới hạn |
| --- | --- | --- |
| **Revoke IAM credential/grant** | Ngừng một đường gọi provider API | Không xóa raw key đã xuất hoặc DEK cache |
| **Suspend/disable key** | Chặn key operation theo provider/state | Có thể chặn cả reader hợp lệ; không xóa cached DEK |
| **Rotate key material** | Tạo material mới và chuyển new-use | Không xóa old ciphertext/secret mà attacker đã copy |
| **Rewrap DEK** | Thay KEK bảo vệ DEK | Không thay DEK/ciphertext dữ liệu |
| **Re-encrypt data** | Thay DEK bảo vệ dữ liệu hiện còn quản lý | Không thu hồi bản sao plaintext/ciphertext lịch sử |
| **Reissue/revoke certificate** | Cập nhật hệ PKI và trạng thái trust | Verifier/caches phải cập nhật; chữ ký lịch sử cần phân tích |
| **Rotate HMAC secret** | Chặn MAC mới bằng secret cũ sau cutover | Cần phối hợp các bên và anti-replay |
| **Destroy key** | Xóa/zeroize material theo provider/policy | Có thể mất dữ liệu; không xóa bản sao ngoài boundary |

### Không tự động dùng một hành động cho mọi dấu hiệu

**Một KMS credential bị lộ** có thể cần revoke credential ngay, đồng thời điều tra xem đã gọi `Unwrap` ra DEK plaintext hay chưa. **Một HSM signing key bị lạm dụng** có thể cần ngừng Sign API và xử lý trust, dù private bytes non-exportable.

### Chú ý cryptoperiod và lifecycle

`ACTIVE`, `SUSPENDED`, `DEACTIVATED`, `COMPROMISED`, `DESTROYED` là các trạng thái có ý nghĩa khác nhau. **Đánh dấu COMPROMISED không tự làm provider ngừng dùng key** nếu policy không được thực thi; ngược lại `Disabled` của provider có thể không xóa khả năng local decrypt từ DEK cached.

## 25. Case study A — KMS credential bị lấy và nhiều lượt Unwrap

### Bối cảnh

Dịch vụ Billing dùng một **KEK** trong KMS để bọc DEK của hóa đơn. Một workload identity có quyền `Unwrap` bị nghi đã lộ. KMS ghi vài trăm `Unwrap SUCCESS` ngoài giờ chạy batch.

### Các evidence cần đối chiếu

| Quan sát | Nguồn | Ý nghĩa |
| --- | --- | --- |
| Role trust thay đổi trước giờ xảy ra sự cố | IAM audit | Có thể tạo đường quyền |
| `Unwrap SUCCESS` từ principal bị nghi | KMS | DEK plaintext có thể đã được trả theo API semantics |
| Không có business request tương ứng | Application audit | Nghi gọi trực tiếp hoặc bypass |
| Wrapped DEK bị tải hàng loạt | Database/object log | Có thể đối thủ có cả blob và kết quả unwrap |
| Cache của reader vẫn giữ DEK cũ | Host telemetry | Disable KEK chưa ngăn mọi local decrypt |
| `CreateGrant` rồi `RevokeGrant` | Control plane | Cần điều tra tự cấp quyền |

### Kết luận không được nhảy vội

Không thấy raw **KEK** rời KMS **không đồng nghĩa** không có DEK lộ. Ngược lại, một `Unwrap SUCCESS` không tự chứng minh đối thủ đã đọc toàn bộ hóa đơn; phải có **wrapped DEK mapping, ciphertext availability, app/host evidence**.

### Hướng xử lý

1. Thu hồi credential/grant và cô lập workload.
2. Đối chiếu key IDs, wrapped DEKs đã gọi và ciphertext/tenant liên quan.
3. Sinh credential mới và cân nhắc KEK rotation.
4. **Rewrap** DEK dưới KEK mới khi mục tiêu là thay lớp bọc.
5. Nếu DEK có thể đã ra plaintext cho attacker, đánh giá **thay DEK + re-encrypt** dữ liệu.
6. Xác minh backup/replica/old object versions; không hủy KEK cũ khi còn phụ thuộc chưa xử lý.
7. Cải thiện IAM, direct API prevention, audit correlation và TTL/cache policy.

**Bài học:** Điều tra dựa trên **vật liệu có thể rời boundary và tài sản được mã hóa**, không chỉ tên của key API.

## 26. Case study B — Chữ ký HSM hợp lệ trên artifact không được duyệt

### Bối cảnh

Một private signing key non-exportable nằm trong HSM, dùng ký release artifact. SOC phát hiện nhiều `Sign SUCCESS` dù không có đợt release được duyệt.

### Hai giả thuyết

- **Giả thuyết 1:** Private key bị export/sao chép trái phép.
- **Giả thuyết 2:** Attacker có credential `Sign`, dùng HSM như **signing oracle**.

Cả hai đều nghiêm trọng, nhưng yêu cầu chứng cứ và phạm vi ảnh hưởng khác nhau.

### Quy trình

1. Chặn service credential, grants và direct Sign API ngoài signing gateway.
2. Bảo toàn HSM events, approved manifest/digest, CI/CD provenance.
3. Liệt kê **artifact digests đã được ký** và nơi đã phát hành.
4. Xác minh private key attributes/provenance, không suy raw leak chỉ từ `Sign SUCCESS`.
5. Sinh signing key pair mới và chuẩn bị phân phối verification key/certificate.
6. Ràng buộc signing với **exact digest/manifest approval** và workload identity tin cậy.
7. Xem xét thu hồi trust/signatures/tokens theo chính sách, time evidence và impact.
8. Giám sát key cũ sau khi dừng new-use.

**Bài học:** Key non-exportable giảm một số đường lộ raw material nhưng **không ngăn chữ ký trái phép khi authorization sai**.

## 27. Case study C — Public secret, GCM nonce lỗi và master-key reuse

### Kịch bản 1 — Raw HMAC key lộ qua repository

Một đối tác xác thực webhook bằng HMAC secret. Secret xuất hiện trong repository công khai.

- Xác nhận có phải **secret production còn hiệu lực** không.
- Không sao chép raw secret vào ticket hoặc chat.
- Tạo **key mới riêng cho partner**; cấp qua kênh xác thực.
- Dừng chấp nhận old key đúng kế hoạch incident, rà soát **replay/forged messages**.
- Nếu cùng secret được dùng cho tenant/DEK khác, mở rộng impact assessment.
- Xóa artifact không đủ vì git history và copies có thể vẫn tồn tại.

### Kịch bản 2 — GCM nonce lặp sau autoscaling

Hai worker cùng AES-GCM DEK khởi tạo nonce counter từ 0. KMS logs không có điều bất thường.

- Dấu hiệu không nằm ở key API mà ở **ciphertext/nonce metadata**.
- Có thể mất bảo đảm confidentiality/integrity dù raw DEK vẫn bí mật.
- Ngừng writer lỗi, thay DEK, sửa nonce allocation và đánh giá ciphertext cũ.
- Kiểm tra snapshot/restart, multi-region, usage limits và data correctness.
- **Không chữa bằng cách chỉ tăng entropy key nhưng giữ code nonce lỗi.**

### Kịch bản 3 — Root master được dùng sinh subkeys nhiều purpose

Một service lưu master vào CI variable cho một tác vụ debug và log trở nên công khai.

- Các subkeys HKDF có `info` khác nhau **không độc lập với master**.
- Phải xác định parent–child lineage, tenant, service, epochs và cryptoperiod.
- Sinh master mới từ nguồn tin cậy, thay descendant keys theo mục đích.
- Đánh giá dữ liệu, webhook, sessions và trust đã bảo vệ bởi descendants.
- **Đổi `info` trên master cũ có thể vẫn để attacker tính các subkeys mới.**

## 28. Kiểm thử năng lực phát hiện compromise

Không nên chờ một sự cố thật để biết key audit có hoạt động không.

### Bài test end-to-end được phép

1. Dùng **test key** gọi `Decrypt`/`Sign` hợp lệ, xác minh source event và correlation.
2. Dùng principal không được phép gọi `Decrypt`/`Unwrap`, xác minh deny và alert khi cần.
3. Tạo một **test grant** trong môi trường kiểm soát, xác nhận rule liên kết grant change với key use.
4. Thử `Sign` trên một **test manifest không được phê duyệt**, kiểm tra signing gateway từ chối.
5. Thay metadata AAD ở test ciphertext, xác nhận AES-GCM tag fail; không bypass.
6. Kiểm tra log không chứa raw test key, HSM PIN, plaintext hoặc token.
7. Tắt collector trong **môi trường test** theo kế hoạch, xác nhận missing-event/lag alert.
8. Thử backup/restore của **test key** với approval và audit source/destination.
9. Giả lập old-key new-use sau rotation cutover, xác nhận writer fencing.
10. Thử replay/HMAC old-version theo use case có kiểm soát.
11. Kiểm thử multi-region timestamp, duplicate events và late ingestion.
12. Thực hiện tabletop về raw DEK exposure, HSM signing misuse và KDF master compromise.
13. Đo khả năng truy vết key ID/material version qua inventory, data envelope và provider.
14. Xác minh SOC biết cách giữ bằng chứng mà không phát tán raw key.

### Các metric nên quan sát

| Chỉ số | Ý nghĩa |
| --- | --- |
| **Event coverage** | Những operation rủi ro cao có đủ nguồn audit |
| **Detection latency** | Thời gian từ event đến alert |
| **Correlation success** | Ghép được app request với provider/key IDs |
| **False-positive rate** | Alert không đúng hoặc thiếu ngữ cảnh |
| **Missed-event alarm** | Mất collector hoặc config bị tắt được báo |
| **Provider/admin visibility** | Có nhìn được key use và policy changes không |
| **Source trust/integrity** | Log có phân quyền, chống sửa và retention |
| **Secret leakage into logs** | Không biến audit thành điểm lộ key |
| **Investigation readiness** | Tìm được dependencies/backups và mốc nghi lộ |
| **Negative-test success** | Wrong purpose/tenant/principal/action bị từ chối |

**Không có một tỷ lệ/ngưỡng đúng cho mọi hệ thống**. Target dựa trên risk tier, workflow, khối lượng và yêu cầu tuân thủ.

## 29. Những lỗi thường gặp khi đánh giá dấu hiệu compromise

| Sai lầm | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Coi mọi `AccessDenied` là data breach | Nâng severity sai | Phân biệt attempt, decision, execution |
| Coi `Decrypt SUCCESS` là raw KEK đã lộ | Nhầm key boundary | Hiểu rõ API semantics và output |
| Coi HSM non-exportable bảo đảm không misuse | Bỏ sót signing/decrypt oracle | Kiểm tra business authorization |
| Chỉ theo dõi `ExportKey` | Bỏ qua `Unwrap` trả DEK plaintext | Threat model tất cả data-plane outputs |
| Coi 0 KMS calls là 0 local decrypt | Điểm mù cached DEK | App data-access audit và host telemetry |
| Không audit `ChangePolicy`/`CreateGrant` | Bỏ qua tự nâng quyền | Control-plane correlation |
| Gắn alert theo volume cứng | False positive/missed incident | Baseline theo purpose và schedule |
| Không phân biệt signal/confirmed | Kết luận thiếu căn cứ | Evidence ladder, confidence, severity |
| Không bảo toàn log sớm | Mất timeline/forensics | Incident evidence capture |
| In raw secret để điều tra | Tạo exposure mới | Secure evidence handling và metadata refs |
| Dùng tên alias làm vật liệu version | Không biết key thật đã dùng | Key ID/material version mapping |
| Chỉ log app mà bỏ provider | Có thể bypass qua direct API | KMS/HSM/IAM log |
| Chỉ log provider mà bỏ app | Không biết business purpose | App/approval audit |
| Không xem HSM audit capability | Tưởng có log khi thực tế không | Provider tests và coverage |
| Tin timestamp sắp xếp tuyệt đối | Clock skew gây timeline sai | Correlation IDs và ingest time |
| Chỉ rotate KEK sau khi DEK lộ | DEK cũ vẫn decrypt dữ liệu | Re-encrypt và đánh giá old copies |
| Rotate signing key nhưng vẫn mở Sign oracle | Key mới tiếp tục bị lạm dụng | Sửa IAM/gateway approval |
| Coi revocation xóa chữ ký đã phát | Sai trust semantics | PKI/JWT impact assessment |
| Coi public key public là private leak | Báo động sai | Phân biệt asymmetric key material |
| Coi HMAC hợp lệ luôn nghĩa partner hợp lệ | Replay hoặc shared key abuse | Peer auth, anti-replay |
| Không xét KDF master compromise | Bỏ sót toàn bộ descendants | Key hierarchy inventory |
| Chỉ sửa RNG sau khi đã sinh lại key yếu | Vẫn compromised | Sửa nguồn trước rotation |
| Tái dùng nonce GCM sau key change không kiểm soát | Có thể lại phát sinh lỗi | Nonce strategy/usage limits |
| Quên backup/DR, object versions | Phạm vi exposure không đầy đủ | Dependency/restore inventory |
| Destroy key ngay để “an toàn” | Mất dữ liệu/bằng chứng | Containment + recovery plan |
| Tuyên bố không có incident vì hết cảnh báo | Có thể lỗ hổng vẫn tồn tại | Root-cause, test, closure evidence |

## 30. Checklist vận hành và điều tra Dấu hiệu compromise

### A. Quan sát và triage

1. **Key inventory:** Key ID/material version, purpose, state, owner/custodian, tenant và environment đã rõ?
2. **Signal source:** Event từ KMS/HSM/IAM/app/host/backup/PKI nào?
3. **Evidence quality:** Đó là alert suy đoán, provider operation success hay material exposure đã xác minh?
4. **Confidence và severity:** Đã ghi riêng mức chắc chắn và tác động tiềm năng?
5. **Timeline:** Có event time/ingest time UTC, timezone và clock skew?
6. **Actor:** Principal có được xác thực, có quyền impersonate hoặc self-escalation?
7. **Operation:** `Encrypt`, `Decrypt`, `Unwrap`, `Sign`, `GenerateMac`, `Derive`, export hay admin change?
8. **Outcome:** Allow/deny/timeout/provider success/business result được phân biệt?
9. **Purpose/tenant:** Có sự kiện cross-purpose, cross-tenant hoặc cross-environment?
10. **Approval:** Có authorized batch/release/migration/backup giải thích tín hiệu?
11. **Missing telemetry:** Có blind spot ở HSM, cached DEK, log collector, server hoặc region?
12. **False positive:** Có bằng chứng giải thích event, không chỉ giả định theo lịch?

### B. Key material và phạm vi ảnh hưởng

13. **Raw material:** Có DEK/KEK/HMAC/private key/master/seed xuất hiện ở log/repo/backup không?
14. **DEK cache:** Có host/app nào đang giữ DEK plaintext, kể cả sau KMS disable?
15. **Wrapped DEK:** Những blobs/ciphertext nào có thể đã được lấy hoặc unwrap?
16. **Signing:** Có artifact/JWT/chứng thư đã được ký trái workflow?
17. **PKI trust:** Certificate/JWKS/key source đã được thay trái phép?
18. **HMAC/partner:** Có shared secret leak, message replay hoặc verification ngoài phiên bản?
19. **KDF master:** Có subkeys nào phụ thuộc cùng root/seed bị nghi lộ?
20. **Nonce/RNG:** Có AES-GCM nonce reuse hoặc DRBG/entropy issue?
21. **Agreement/TLS:** Có session/ticket/private-key material hoặc peer trust bị ảnh hưởng?
22. **Backup/DR:** Key copies, snapshots, archives và restore activities đã kiểm kê?
23. **Material provenance:** Key được generated/imported/restored; từng có bản raw ngoài boundary?
24. **Historical exposure:** Earliest plausible exposure và old ciphertext/outputs đã phân tích?

### C. Cô lập, rotation và khôi phục

25. **Credential/grants:** Đã chặn principal/role và kiểm tra hiệu lực thu hồi thực?
26. **Provider key state:** Hiểu `SUSPENDED`/`Disabled`/`COMPROMISED`/`Destroyed` và tác động availability?
27. **No fail-open:** Khi KMS lỗi, không fallback sang key nghi lộ?
28. **New key:** Nếu cần rotation, material mới sinh từ nguồn **đáng tin**, không dùng RNG/master đã lỗi?
29. **Rewrap vs re-encrypt:** Đã chọn đúng giải pháp cho KEK hoặc raw DEK exposure?
30. **Signing trust:** Đã chặn oracle, cập nhật verifier/certificate và đánh giá chữ ký lịch sử?
31. **HMAC coordination:** Đối tác đã nhận secret mới, có key version và anti-replay?
32. **Backup dependency:** Không destroy old key khi còn ciphertext/backup cần phục hồi?
33. **Multi-region:** Các writer/reader/caches đã được fence và cập nhật?
34. **SoD:** Key owner/custodian/security/incident roles có approvals độc lập khi cần?
35. **Forensics:** Evidence nhạy cảm được bảo vệ, không sao chép raw secret sang ticket/log?

### D. Kiểm chứng và hậu kiểm

36. **Negative tests:** Wrong principal/key/purpose/operation/state có thực sự bị provider từ chối?
37. **Audit completeness:** Provider, app và control plane được nối bằng key ID và correlation ID?
38. **Collector health:** Mất sự kiện hoặc thay retention có cảnh báo?
39. **Detection tuning:** Rule đã xét baseline, release window, backup jobs và false positives?
40. **Dependencies:** Đã tìm mọi nơi còn raw key/wrapped key/data/trust version cũ?
41. **Residual risk:** Đã ghi rằng rotation không thu hồi các bản sao attacker đã có?
42. **Closure:** Có bằng chứng đủ cho incident decision, remedial actions và postmortem?
43. **Owner review:** Có người chịu trách nhiệm khắc phục nguyên nhân IAM, RNG, nonce, code hoặc key granularity?
44. **Drill:** Có lịch diễn tập với **test keys** và thử khôi phục thật trong phạm vi cho phép?

## 31. Tổng kết

**Dấu hiệu compromise** không chỉ là một dòng log nói “key bị lộ”. Nó có thể là **raw key xuất hiện ngoài vùng bảo vệ**, **API `Sign/Decrypt/Unwrap` bị lạm dụng**, **grants/IAM bị sửa**, **HSM tamper**, **RNG hoặc nonce AES-GCM có lỗi**, **public trust bị thay**, hoặc **backup chứa bí mật bị sao chép**. Mỗi tín hiệu dẫn tới giả thuyết và phạm vi ảnh hưởng khác nhau.

Một quy trình tốt phải **phân biệt suspicion với confirmation, identity compromise với key-material exposure, provider success với business authorization, KEK với DEK, và rotation với revocation/destruction**. KMS/HSM tạo điểm cưỡng chế và bằng chứng quan trọng nhưng **không nhìn thấy mọi hoạt động với DEK plaintext cached**; do đó phải kết hợp **application audit, control-plane changes, host/backup telemetry và key inventory**.

Khi có dấu hiệu, ưu tiên **bảo toàn bằng chứng, cô lập quyền có nguy cơ, xác định loại secret và mọi tài sản phụ thuộc**, rồi **thay khóa, rewrap, re-encrypt, cập nhật PKI/JWKS/HMAC trust và kiểm chứng recovery** khi phù hợp. **Raw secret hoặc dữ liệu mà đối thủ đã sao chép không biến mất chỉ vì key được rotate**. Thành công không phải là “hết alert”, mà là **có thể giải thích điều gì đã xảy ra, giới hạn thiệt hại và chứng minh các đường lạm dụng không còn hoạt động**.

# Rotation khi nghi ngờ compromise — Xoay vòng khóa khi có dấu hiệu bị lộ hoặc lạm dụng

## 1. Rotation khi nghi ngờ compromise là gì?

**Rotation khi nghi ngờ compromise** là quy trình **đánh giá rủi ro, cô lập đường sử dụng khóa có khả năng không còn an toàn, tạo vật liệu khóa mới từ nguồn tin cậy, chuyển các hệ thống sang khóa mới, xử lý dữ liệu và niềm tin phụ thuộc khóa cũ, rồi thu hồi hoặc hủy khóa cũ theo điều kiện có kiểm chứng**.

Một sự cố có thể chưa chứng minh được **raw key material đã bị sao chép**, nhưng các bằng chứng như **IAM credential bị đánh cắp, yêu cầu `Decrypt` bất thường, HSM báo tamper, bản sao DEK trong log, chữ ký trái phép hoặc lỗ hổng RNG** đã đủ để kích hoạt quy trình ứng cứu và cân nhắc rotation sớm.

Trong chương **Cryptoperiod và rotation** thuộc mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, đây là trường hợp đặc biệt của **vòng đời khóa mật mã**: một khóa đang ở giai đoạn sử dụng có thể cần dừng *new-use* trước khi hết cryptoperiod dự kiến. Chủ đề kết nối mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, phân quyền, kiểm toán, thu hồi và hủy khóa.

Ví dụ:

- Dịch vụ Billing dùng `KEK-v3` tại KMS để bọc các DEK của hóa đơn.
- Credential của `billing-reader-prod` bị nghi bị lấy cắp.
- Audit xuất hiện nhiều yêu cầu `Unwrap` lúc không có nghiệp vụ tương ứng.
- Nhóm sự cố chưa biết đối thủ đã lấy được plaintext DEK hay chỉ thử các lời gọi thất bại.

**Không nên kết luận ngay “KEK đã lộ”**, nhưng cũng không nên tiếp tục cho credential cũ hoạt động như bình thường. Phải **cô lập quyền**, xác định những key và DEK có thể bị ảnh hưởng, chuẩn bị khóa thay thế, và quyết định **rewrap hay re-encrypt** dựa trên loại bí mật thực sự có nguy cơ lộ.

> **Nguyên tắc:** **Suspicion không đồng nghĩa confirmation; rotation không đồng nghĩa containment; và đổi khóa hôm nay không xóa dữ liệu hoặc khóa đã bị sao chép hôm qua.**

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt rotation định kỳ với **incident-driven/emergency rotation**.
2. Phân tích dấu hiệu **nghi ngờ lộ vật liệu**, **lạm dụng key API** và **lộ credential**.
3. Chọn thứ tự **contain → preserve evidence → assess → rotate → cutover → remediate → retire** phù hợp.
4. Quyết định hành động với **DEK, KEK, signing key, HMAC key, KDF master và agreement key**.
5. Hiểu điểm mù của **KMS/HSM**, bản sao key ở RAM/cache và dữ liệu lịch sử.
6. Thiết kế **versioning, dual-read/single-write, IAM, audit, DR và điều kiện hủy khóa**.
7. Xây dựng runbook, negative tests và ví dụ Java mô tả policy gate trong sự cố.

## 2. Cryptoperiod định kỳ và rotation do sự cố khác gì nhau?

**Cryptoperiod** là khoảng thời gian mà một khóa được phép sử dụng cho các thao tác được định nghĩa theo chính sách và mô hình quản lý vòng đời. Trong thực tế cần phân biệt **thời hạn bảo vệ/được phép tạo output mới** với **thời gian phải giữ vật liệu cũ để decrypt/verify dữ liệu lịch sử**.

| Tiêu chí | Rotation theo lịch | Rotation khi nghi ngờ compromise |
| --- | --- | --- |
| **Trigger** | Cryptoperiod, policy, usage limit, kế hoạch vận hành | Dấu hiệu lộ key, lạm dụng API, lỗ hổng RNG/IAM, tamper |
| **Tính khẩn cấp** | Có thể có thời gian chuẩn bị/canary | Có thể phải cô lập ngay cả khi nguyên nhân chưa rõ |
| **Độ tin cậy vào key cũ** | Được quản lý như legacy key nếu không có dấu hiệu lộ | Phải đánh giá lại, có thể tạm dừng mọi new-use |
| **Kế hoạch dữ liệu** | New-write cutover rồi migrate theo lịch | Ưu tiên đối tượng rủi ro, có thể re-encrypt khẩn |
| **Phê duyệt** | Workflow thường kỳ | Incident commander/owner/security theo quy trình khẩn |
| **Khả năng rollback** | Có thể có rollback được duyệt | **Không được âm thầm quay lại dùng khóa nghi lộ** |
| **Audit** | Theo dõi tiến độ/tuân thủ | Bảo toàn chứng cứ, dựng timeline, xác định blast radius |
| **Tiêu chí hoàn tất** | Hết phụ thuộc theo mục tiêu rotation | Cô lập nguyên nhân, key mới tin cậy, xử lý trust/data/backup/incident |

**Không có một chu kỳ “90 ngày” hoặc một thời gian phản ứng cố định đúng cho mọi key.** Cryptoperiod và ngưỡng sự cố phụ thuộc thuật toán, độ nhạy tài sản, số lượt sử dụng, mô hình đe dọa, quy định và chính sách được phê duyệt.

### Hai thời điểm phải ghi rõ

- **Incident observation time:** lúc nhận diện dấu hiệu đáng ngờ.
- **Earliest plausible exposure time:** mốc sớm nhất có khả năng bị lộ dựa trên bằng chứng, **có thể chưa biết**.

Mốc sớm nhất quan trọng để đánh giá **ciphertext, DEK, chữ ký, token và backup** đã tồn tại trong khoảng nghi lộ; đừng mặc định phạm vi ảnh hưởng chỉ bắt đầu lúc cảnh báo xuất hiện.

## 3. “Nghi ngờ compromise” bao gồm những loại nào?

**Compromise** không chỉ là lấy được raw key bytes. Một key có thể vẫn nằm nguyên trong HSM nhưng bị **sử dụng trái phép** thông qua một API có quyền.

| Loại | Điều có thể đã xảy ra | Ví dụ | Câu hỏi cần điều tra |
| --- | --- | --- | --- |
| **Raw key exposure** | Secret/private material đã ra ngoài boundary | DEK bị in log, private key trong snapshot | Những bản sao nào còn tồn tại? |
| **Authorized API misuse** | Đối thủ dùng credential hợp lệ để gọi operation | `Sign` artifact chưa duyệt | Những output trái phép nào đã được tạo? |
| **Credential compromise** | Role/token/PIN/service account có thể bị lấy | IAM key leaked | Quyền nào bị dùng và đã trả ra secret chưa? |
| **Policy compromise** | IAM/grant/role trust bị mở rộng trái phép | Admin tạo grant `Decrypt` | Ai đổi policy, bao giờ, còn đường vòng nào? |
| **Implementation compromise** | Lỗi nonce, KDF, RNG, code/firmware | AES-GCM nonce lặp hoặc RNG dự đoán | Material và ciphertext nào có thể yếu? |
| **Physical HSM event** | Tamper alarm hoặc bất thường thiết bị | HSM tamper/self-test alert | Theo tài liệu, khóa đã bị zeroize/chặn hay chưa? |
| **Trust-material compromise** | Certificate, recipient public key hoặc phân phối trust bị thay | JWKS endpoint bị sửa | Verifier đang tin khóa nào? |
| **Backup/restore exposure** | Bản sao khóa đã được đọc hoặc phục hồi | HSM recovery media thất lạc | Có khả năng dựng lại raw secret hoặc dùng API không? |

### Suspected không phải confirmed

- **Suspected:** có chỉ dấu nhưng còn thiếu bằng chứng quyết định. Hành động phù hợp có thể là **cô lập credential, tạm suspend new-use, mở điều tra, tạo khóa sạch**.
- **Confirmed:** có bằng chứng đủ mạnh rằng raw key đã lộ hoặc operation trái phép đã diễn ra. Phải **xác định phụ thuộc, thay vật liệu, xử lý dữ liệu/trust lịch sử** theo loại sự cố.
- **Ruled out với bằng chứng:** tín hiệu được giải thích hợp lý; vẫn phải đối soát policy, audit coverage và quyết định có resume old key không.

Đừng tuyên bố **“không thấy log nghĩa là chưa bị lộ”**. Đặc biệt khi ứng dụng có plaintext DEK trong cache, HSM/KMS không nhìn thấy các thao tác offline.

## 4. Dấu hiệu nào nên kích hoạt quy trình đánh giá?

Các trigger thường gặp:

1. **Raw key/private key/DEK xuất hiện** trong log, core dump, CI artifact, file công khai hoặc secret manager ngoài chính sách.
2. IAM credential của workload có quyền `Decrypt`, `Unwrap`, `Sign` hoặc `GenerateDataKey` bị nghi mất.
3. **Đột biến Sign/Decrypt/Unwrap** ngoài lịch nghiệp vụ, sai tenant/environment hoặc từ principal lạ.
4. Có thao tác **CreateGrant/ChangePolicy** ngay trước những API use không được phê duyệt.
5. Private signing key bị nghi đã tạo chữ ký số/JWT hoặc release artifact trái phép.
6. HSM báo **tamper, entropy failure, DRBG health failure, firmware integrity alert** hoặc bị mất quyền kiểm soát.
7. Phát hiện **nonce AES-GCM trùng dưới cùng DEK** hoặc key generation dùng nguồn dễ đoán.
8. Backup chứa KEK/DEK/CA private key bị truy cập hoặc sao chép ngoài quy trình.
9. Một HMAC secret dùng chung nhiều đối tác bị nghi rò rỉ ở một đối tác.
10. KDF master/root secret hoặc seed đã xuất hiện ở nơi không đáng tin.
11. Pipeline deployment trỏ production sang **key/alias của staging** hoặc nhập nhầm raw material.
12. Người quản trị bị nghi có thể **thay policy và xóa log** liên quan khóa.

**Không phải mọi cảnh báo đều chứng minh compromise.** Nhưng với khóa rủi ro cao như root CA/signing key hoặc KEK bảo vệ nhiều DEK, một dấu hiệu nhỏ có thể đòi hỏi cô lập sớm hơn so với key thử nghiệm.

## 5. Mục tiêu xử lý: giảm rủi ro mà không hủy khả năng khôi phục

Một quyết định incident rotation phải cân bằng:

- **Confidentiality:** ngăn đối thủ tiếp tục decrypt hoặc lấy thêm key material.
- **Integrity/authenticity:** ngăn ký số, tạo MAC hoặc ciphertext trái phép.
- **Availability:** giữ hệ thống phục vụ nghiệp vụ trong giới hạn an toàn.
- **Recoverability:** giữ đường đọc dữ liệu lịch sử/backup theo yêu cầu.
- **Forensics:** không xóa chứng cứ trước khi lưu giữ.
- **Containment:** ngăn credential, session, grants và cached DEK bị lạm dụng.
- **Compliance:** tuân thủ retention, approval, audit và các nghĩa vụ thông báo liên quan.

### Không coi key deletion là phản xạ đầu tiên

Xóa ngay KEK có thể khiến hàng triệu wrapped DEK **không thể giải bọc**. Xóa private signing key có thể không ngăn các chữ ký đã phát còn được xác minh; ngược lại nó có thể phá một quy trình khôi phục hợp lệ.

**Containment thường được thực hiện trước bằng quyền, trạng thái, mạng, key API và quy trình ứng cứu**, rồi mới quyết định thời điểm tiêu hủy material.

### Không coi availability là lý do để fail open

Nếu signing key bị nghi lộ, hệ thống không nên **âm thầm fallback** sang key cũ khi key mới hoặc KMS lỗi. Khi cần ngoại lệ, phải có **risk acceptance, scope, hạn dùng, dual control khi phù hợp và audit**, chứ không phải một `try/catch` bỏ qua policy.

## 6. Quy trình tổng thể: contain, assess, rotate, recover

~~~mermaid
flowchart TD
    Alert[Dấu hiệu key compromise] --> Triage[Xác minh tín hiệu, key ID, principal, scope]
    Triage --> Contain[Cô lập credential/grant/operation; giữ bằng chứng]
    Contain --> Type{Loại rủi ro?}
    Type -->|Raw secret lộ| Material[Thay material, đánh giá ciphertext/backup]
    Type -->|API misuse| Api[Chặn oracle, kiểm tra output trái phép]
    Type -->|Policy/RNG flaw| Root[Sửa nguyên nhân, xác định keys phụ thuộc]
    Material --> NewKey[Sinh key mới từ nguồn và boundary tin cậy]
    Api --> NewKey
    Root --> NewKey
    NewKey --> Preflight[Pre-activation: IAM, readers, DR, trust, audit]
    Preflight --> Cutover[Cutover new-use sang version mới]
    Cutover --> Migrate[Rewrap / re-encrypt / trust distribution theo key type]
    Migrate --> Check{Còn phụ thuộc và rủi ro chưa xử lý?}
    Check -->|Có| Migrate
    Check -->|Không| Retire[Thu hồi và hủy old key theo policy]
    Retire --> Review[Audit, postmortem, cải thiện kiểm soát]
~~~

**Đây là luồng ra quyết định khái niệm, không phải các bước bắt buộc phải chạy nối tiếp hoàn toàn.** Khi rủi ro cao, **containment và tạo key mới** có thể diễn ra song song; việc bảo toàn log phải bắt đầu sớm. Tùy dịch vụ, có thể phải đưa hệ thống về chế độ **read-only hoặc dừng signing** trong lúc chuẩn bị.

### Phân công cụ thể

- **Incident commander:** quyết định ưu tiên, mức rủi ro, phối hợp ứng cứu.
- **Key owner:** phê duyệt purpose, cryptoperiod, key replacement và xử lý phụ thuộc.
- **Key custodian/KMS admin:** cô lập/rotate/backup theo quyền kỹ thuật.
- **Application/data owner:** kiểm soát writer/reader, nghiệp vụ, data migration.
- **Security reviewer:** đánh giá threat model, IAM, root cause và bằng chứng.
- **Auditor/forensics:** bảo toàn, đối chiếu log và change history.
- **Partner/trust owner:** cập nhật chứng thư/JWKS/HMAC secret/recipient public key.

Separation of duties phải xét **quyền tự nâng**: một admin không có `Decrypt` trực tiếp nhưng sửa được grants/IAM cũng cần kiểm soát.

## 7. Bước 1 — Xác nhận tài sản và mốc nghi ngờ

Trước khi quyết định đổi key nào, cần xác định:

~~~text
incidentId: INC-2030-042
keyResourceId: billing-kek-v3
materialVersion: v3
keyPurpose: WRAP_BILLING_DEKS
stateAtDetection: ACTIVE
environment: production
tenantOrDataScope: billing-tenants
owner: billing-data-owner
custodian: kms-platform-team
firstObservedUtc: 2030-05-12T09:30:00Z
earliestPossibleExposureUtc: UNKNOWN
suspectedMode: CREDENTIAL_AND_UNWRAP_API_MISUSE
confidence: INVESTIGATING
~~~

Đây là **bản ghi ví dụ**, không phải kết luận hay schema chuẩn của nhà cung cấp.

### Cần kết nối key inventory

- Material version khác gì với **logical KMS resource ID/alias**?
- Khóa được **generate trong HSM/KMS**, import hay derive từ master nào?
- Có **wrapped DEK, ciphertext, signing artifacts, HMAC peers hoặc backup** phụ thuộc không?
- Có copy hoặc wrapped export/import sang **region, account, HSM partition** khác?
- Tại thời điểm nghi ngờ, **cryptoperiod, key state và grants** như thế nào?
- Người dùng/partner nào đang tin **public key/certificate** tương ứng?
- Có những **DEK plaintext cached** trong workload nào?

**Không đổi alias rồi kết luận đã đổi vật liệu khóa.** Cần ghi key ID/version thực sự được dùng tại provider và data envelope.

## 8. Bước 2 — Cô lập đường lạm dụng trước khi thay khóa

### 8.1. Thu hồi principal/credential có thể bị chiếm

- Disable/rotate API credentials, workload identity hoặc token có nguy cơ.
- Revoke grants, trust relationships, IAM policy quá rộng.
- Tách service/instance/container bị nghi compromise khỏi luồng production.
- Chặn đường gọi `Sign`, `Decrypt`, `Unwrap`, `DeriveKey` trái scope.
- Giám sát API hoạt động còn lại; không dựa vào một thao tác revoke đã gửi nếu chưa **xác minh hiệu lực thực tế**.

### 8.2. Suspend key theo khả năng provider

Có thể chuyển **logical lifecycle state** sang `SUSPENDED` hoặc **disable key ở KMS**, nhưng cần biết:

- Một provider có thể chặn **cả Encrypt và Decrypt** khi `Disabled`.
- Chặn **new-use** và giữ **legacy decrypt có kiểm soát** đôi khi cần app gateway/key version routing, không thể hiện bằng một nút provider.
- KMS/HSM token/session/cached plaintext key có semantics riêng; không assume tất cả operation bị ngắt tức thời.
- Một grant bị revoke có thể còn session hoặc cache cần invalidate theo thực tế sản phẩm.

### 8.3. Không xóa chứng cứ

Trước khi chỉnh môi trường, bảo toàn **KMS/HSM event IDs, application logs, IAM policy history, approval records, key inventory, CI/CD deployment revision, timestamps, host/backup logs** theo quy trình forensics.

Không ghi raw key hoặc plaintext vào hệ thống log như cách “bảo toàn chứng cứ”. Nếu cần xử lý vật liệu nhạy cảm để điều tra, phải có kênh và phạm vi bảo vệ riêng.

### 8.4. Không kiểm tra bằng cách thử xuất key

Việc ép `ExportRawKey` hoặc dump JVM/HSM chỉ để xác minh liệu key có lộ chưa có thể **tạo ra sự cố mới**. Dùng bằng chứng provider/attributes, audit, test keys và phương pháp forensics được phê duyệt.

## 9. Bước 3 — Phân loại ảnh hưởng theo loại khóa

Không có một lệnh `rotate()` an toàn cho mọi loại key. Cần biết **operation**, **key purpose** và **những tài sản được bảo vệ**.

| Khóa hoặc tài sản | Khi nghi compromise | Hành động chính | Sai lầm cần tránh |
| --- | --- | --- | --- |
| **AES DEK** | Raw bytes có thể bị lấy, hoặc nonce/integrity lỗi | Thay DEK; đánh giá re-encrypt data/ciphertext lịch sử | Chỉ rewrap DEK cũ |
| **KEK** | Có thể mất quyền kiểm soát wrap/unwrap | Thay KEK, rà soát wrapped DEK, rewrap; xét DEK exposure | Tưởng KEK mới tự bảo vệ DEK đã lộ |
| **HMAC key** | Shared secret có thể bị lộ tại một bên | Key mới cho các bên, dual verification window chặt, anti-replay | Chỉ đổi key tại sender |
| **Signing private key** | Có thể bị sao chép hoặc dùng tạo chữ ký trái phép | Thay cặp khóa, phân phối public trust mới, điều tra output cũ | Coi xóa private key làm chữ ký đã phát mất hiệu lực |
| **CA private key** | Trust root/intermediate có thể mất an toàn | Quy trình PKI incident, certificate revocation/reissuance/trust update | Chỉ cài một file cert mới mà không xử lý chain |
| **KDF master/root** | Nhiều subkey phụ thuộc cùng source | Thay master từ nguồn tin cậy, liệt kê descendants, migrate | HKDF lại từ master đã lộ |
| **Static ECDH key** | Private agreement material có thể bị lấy | Thay pair và đánh giá các session/key schedules phụ thuộc | Nghĩ ECDH tự xác thực peer |
| **Ephemeral session key** | Có thể bị lộ cục bộ trong phiên | Đóng/renew session, đánh giá transcript/secrets | Dùng lại private ephemeral key cho các phiên khác |
| **KMS credential** | Có quyền API nhưng raw key chưa chắc lộ | Thu hồi quyền, kiểm tra output/cached secrets, quyết định rotate | Kết luận mọi key đều lộ hoặc không key nào lộ |
| **Public key/certificate** | Chỉ được công bố bình thường | Xác minh trust/binding, không mặc nhiên coi là lộ secret | Rotate private key chỉ vì public key được nhìn thấy |

**Nguyên tắc:** Bảo vệ bí mật (*confidentiality*) và bảo đảm quyền tạo output (*authenticity/integrity*) bị ảnh hưởng khác nhau. Có thể phải làm cả hai, nhưng **loại remediation phải đúng**.

## 10. Key hierarchy và blast radius khi root bị nghi lộ

Một secret thường là **tổ tiên của nhiều bí mật khác**:

~~~mermaid
flowchart TD
    Root[Root/Master hoặc KDF IKM] --> KEK[KEK phiên bản cũ]
    Root --> MAC[HMAC subkey]
    Root --> AGREE[Agreement/traffic subkey]
    KEK --> DEK1[Wrapped DEK dataset A]
    KEK --> DEK2[Wrapped DEK dataset B]
    DEK1 --> C1[(Ciphertext dataset A)]
    DEK2 --> C2[(Ciphertext dataset B)]
    MAC --> W[Webhook messages]
    AGREE --> S[Sessions]
~~~

**Sơ đồ chỉ minh họa quan hệ phụ thuộc**, không khẳng định mọi hệ thống derive KEK/HMAC/agreement key từ cùng master; trong thực tế nên tách key purpose/trust domain như yêu cầu.

### Khi master/key derivation source bị nghi lộ

- Phải xác định `parentKeyId`, `childKeyId`, `info`/domain, version và scope.
- Nếu master bị lộ, **đổi nhãn HKDF** rồi dẫn xuất từ **cùng master cũ** không khôi phục bí mật.
- Tạo **master mới thật sự** bằng CSPRNG/KMS/HSM có mức tin cậy cần thiết.
- Di chuyển các descendant keys và dữ liệu/trust được bảo vệ theo từng loại.
- Không tự gọi subkeys cùng master là **độc lập tuyệt đối**; chúng phụ thuộc cùng root.

### Nếu RNG/DRBG hoặc seed bị nghi compromised

Một vòng rotation dùng **cùng nguồn sinh yếu** có thể lại tạo khóa đoán được. Cần **sửa/đổi nguồn entropy, provider, host, firmware hoặc quy trình provisioning** trước khi tin key mới.

### Nếu raw secret bị sao chép ngoài KMS

Non-exportability tại HSM sau khi import không xóa được **bản sao trước import**. Phải xét provenance, backup, application memory, old secret store và nơi vật liệu đã từng tồn tại.

## 11. Bước 4 — Sinh key mới trong vùng tin cậy

Khóa thay thế cần **mới về vật liệu**, đúng **key type, algorithm, key usage và source trust**.

### Preflight key mới

1. **Key owner** xác nhận purpose, tài sản và cryptoperiod mới.
2. **Incident team** đánh giá liệu hệ thống tạo khóa cũ/RNG/KMS có còn đáng tin.
3. Sinh key ở **HSM/KMS mới hoặc partition/identity đã kiểm tra**, nếu boundary cũ bị nghi vấn.
4. Gán **key ID và material version mới**; không chỉ đổi alias.
5. Thiết lập **non-exportable/sensitive**, usage attributes và IAM/grants phù hợp.
6. Tách key theo **tenant/service/environment/purpose** nếu compromise cho thấy blast radius quá rộng.
7. Với signing, chuẩn bị **public key/certificate/JWKS** cùng metadata trust.
8. Với DEK/KEK, chuẩn bị **wrapped DEKs, encryption context/AAD và key version routing**.
9. Kiểm thử **negative operations**, hạn chế tự nâng quyền và audit provider.
10. Kiểm tra **HA/backup/DR**, tránh tạo key mới nhưng không có khả năng khôi phục.

**Đừng dùng khóa mới để mã hóa dữ liệu production khi reader/verifier chưa sẵn sàng.** `PRE_ACTIVATION` là trạng thái logic thuận tiện để kiểm tra toàn bộ điều kiện này trước cutover.

### Không dùng lại same raw material

~~~text
key-v1 (material = X, suspected compromised)
alias key-v2 -> same material X       # KHÔNG phải rotation

key-v2 (material = Y, generated securely)
new key resource / material version   # Rotation thực sự
~~~

Sự độc lập/sức mạnh của Y đến từ **nguồn sinh và key management**, không phải kiểm tra vài bytes khác X.

## 12. Bước 5 — Cutover an toàn: reader-first, single-write

Với dữ liệu cần đọc/verify lịch sử, thường cần chuẩn bị **reader/verifier hỗ trợ cả key version cũ và mới** trước khi chuyển writer/signer sang khóa mới.

~~~mermaid
sequenceDiagram
    participant IC as Incident team
    participant KMS as KMS/HSM
    participant App as App readers/writers
    participant Data as Storage
    participant Audit as Audit
    IC->>KMS: Tạo key v2, policy hạn chế và test
    IC->>App: Reader/verifier hỗ trợ v1/v2 theo metadata
    IC->>App: Writer/signing chỉ new-use v2
    App->>KMS: Encrypt/Sign với v2 theo quyền
    KMS-->>App: Ciphertext/signature hoặc response
    App->>Data: Lưu output kèm key ID/version v2
    App-->>Audit: Key version + approval + result
    IC->>KMS: Chặn new-use v1, cô lập grants cũ
    IC->>Data: Lập kế hoạch legacy migration/verification
~~~

### Điều bắt buộc

- **Reader-first:** mọi reader/verifier cần hiểu metadata v2 và có trust/key tương ứng.
- **Single-write:** sau cutover, new ciphertext/signature phải dùng **v2**, không phát output mới từ v1.
- **Writer fencing:** chặn instance/service/region chưa nâng cấp và job cũ còn dùng v1.
- **Versioned metadata:** ciphertext, wrapped DEK, JWT `kid`, certificate hoặc signature envelope phải gắn **key ID/version thực**.
- **Rollback có kiểm soát:** nếu code rollback, vẫn phải đọc/verify được output v2; không bật lại new-use v1 nghi lộ chỉ vì tiện.

### Khi cần dừng dịch vụ

Nếu chưa có key mới tin cậy hoặc không thể ngăn signing oracle/decrypt oracle bằng quyền, việc **tạm ngừng chức năng nhạy cảm** có thể an toàn hơn tiếp tục phát output bị lạm dụng. Quyết định cần có owner và incident commander theo runbook, không phải fallback tự động.

## 13. Rotation KEK: rewrap DEK và điều kiện đánh giá re-encrypt

Giả sử ứng dụng dùng **envelope encryption**:

~~~text
ciphertext = AES-GCM(DEK-v1, plaintext, nonce, AAD)
wrappedDEK = Wrap(KEK-v1, DEK-v1)
~~~

Nếu **chỉ KEK cần đổi**, một kế hoạch có thể là:

~~~text
wrappedDEK_v2 = Rewrap(KEK-v1 -> KEK-v2, DEK-v1)
ciphertext dữ liệu vẫn giữ nguyên
DEK-v1 vẫn là DEK ban đầu
~~~

Trong nhiều kiến trúc, **rewrap DEK** không yêu cầu giải mã/re-encrypt toàn bộ dữ liệu. Tuy nhiên cần dùng **API hợp lệ**, đúng wrapping mechanism và kiểm soát plaintext DEK khi provider không có transcrypt nội bộ.

### Khi rewrap có thể đủ

- KEK đến hạn rotation theo lịch.
- Vật liệu DEK còn được đánh giá là bí mật, không có bằng chứng cho thấy plaintext DEK đã bị lấy.
- Chính sách chỉ yêu cầu thay lớp bọc và trust boundary của KEK.

### Khi rewrap **không đủ**

- Raw **DEK đã bị lộ**.
- Attacker đã `Unwrap` ra plaintext DEK và có ciphertext tương ứng.
- KEK lộ đồng thời đối thủ có khả năng sở hữu **wrapped DEK**; cần đánh giá liệu DEK đã hay có thể được giải bọc.
- Nguồn sinh DEK bị nghi yếu hoặc lộ.
- Yêu cầu mới là **DEK material phải khác**, không chỉ KEK.

### Những điểm cần đối soát

| Thành phần | Khi rewrap |
| --- | --- |
| DEK material | Thường **không đổi** |
| Data ciphertext/nonce/tag | Thường **không đổi** |
| Wrapped DEK blob | **Đổi** |
| KEK ID/material version | **Đổi** |
| Key inventory và grant | Phải cập nhật |
| Backup chứa wrapped DEK cũ | Phải đánh giá |
| Cached plaintext DEK | **Không tự biến mất** |
| KMS Unwrap audit | Chỉ thấy call tới provider, không thấy mọi local decrypt |

**Disable KEK-v1 không tự thu hồi raw DEK** đã trả cho các workload. Đây là giới hạn rất quan trọng khi phản ứng với credential compromise.

## 14. Rotation DEK: re-encrypt dữ liệu khi raw DEK bị nghi lộ

Khi **DEK trực tiếp bảo vệ dữ liệu** có nguy cơ bị sao chép, chỉ bọc lại DEK cũ là sai mục tiêu. Hệ thống cần **thay DEK** và đánh giá **re-encrypt** dữ liệu liên quan.

### Quy trình một record AES-GCM

1. Lấy ciphertext-v1 và **nonce, tag, AAD profile, DEK ID/version** bằng một snapshot nhất quán.
2. Xác thực quyền migration và `Unwrap/Decrypt` phù hợp; không cho phép thao tác hàng loạt ngoài scope.
3. Giải mã bằng DEK-v1 và **xác minh authentication tag** trước khi chấp nhận plaintext.
4. Sinh/nhận **DEK-v2 mới** từ nguồn tin cậy.
5. Tạo **nonce mới theo thiết kế không lặp dưới cùng key**, AAD mới ràng buộc tenant, record và version.
6. AES-GCM Encrypt plaintext với DEK-v2; tạo ciphertext-v2 và tag-v2.
7. Bọc DEK-v2 bằng KEK đúng policy, hoặc dùng key handle tương ứng.
8. **Commit atomically/conditionally** ciphertext, nonce, tag, AAD metadata, wrapped DEK và key version.
9. Ghi audit **không chứa plaintext/DEK**.
10. Chỉ retire DEK-v1 sau khi dependency và retention được xử lý.

### Hai lỗi đặc biệt nghiêm trọng

**GCM tag sai:** không được bỏ qua verification hoặc stream plaintext chưa xác thực sang database mới. Một số API streaming có thể phát plaintext trước khi kiểm tra tag cuối; phải staging/commit an toàn hoặc dùng thiết kế chunked AEAD chuẩn.

**Concurrent update:** migration worker đọc revision cũ, trong khi request nghiệp vụ đã cập nhật record. Nếu worker ghi đè không kiểm tra **revision/ETag/CAS**, có thể mất cập nhật. Rotation không được làm hỏng tính nhất quán nghiệp vụ.

### Một mối giới hạn không đảo ngược

**Re-encrypt không làm ciphertext-v1 hoặc DEK-v1 mà attacker đã giữ biến mất.** Phải điều tra old backups, object versions, external shares và plaintext có thể đã bị truy cập.

## 15. Khi AES-GCM nonce bị dùng sai, rotation không chỉ là đổi key

Một lớp sự cố có thể xảy ra ngay cả khi **raw DEK chưa bị lấy**: ứng dụng **tái sử dụng nonce dưới cùng AES-GCM key**.

### Vì sao nguy hiểm?

GCM cần tính **duy nhất của nonce dưới cùng một key**. Nonce lặp có thể phá các bảo đảm về **confidentiality và integrity**. Việc phát hiện lỗi nonce là một trigger incident rotation hợp lý.

### Hướng ứng cứu

1. Ngừng writer dùng **cặp key/nonce strategy sai**.
2. Thay key và sửa **nonce allocation / RNG / counter management** trước khi bật lại.
3. Xác định ciphertext đã dùng nonce trùng và những dữ liệu có thể bị ảnh hưởng.
4. Đánh giá khả năng **plaintext/integrity của ciphertext cũ** đã mất bảo đảm.
5. Re-encrypt từ **nguồn dữ liệu đáng tin** khi có thể; không tự coi ciphertext cũ đã xác thực hoàn hảo nếu security guarantee bị phá.
6. Kiểm tra multi-node, VM snapshot/restart, DR và giới hạn sử dụng mỗi key.
7. Ghi audit, kết quả rà soát và xử lý dữ liệu lịch sử.

**Tạo key mới rồi tiếp tục dùng lại nonce cố định với key mới** chỉ trì hoãn sự cố; phải sửa nguyên nhân.

## 16. Rotation private signing key: JWT, chứng thư và chữ ký lịch sử

Đối với **signing key**, điều cần bảo vệ không chỉ là private key material mà còn **quyền tạo chữ ký hợp lệ** và **niềm tin của verifier**.

### Khi private key có thể bị sao chép

- Sinh **signing key pair mới** trong boundary tin cậy.
- Chặn new-sign bằng old key và các grants/credentials liên quan.
- Phát **public verification key/certificate/JWKS** mới qua nguồn được tin cậy.
- Xác định output đã tạo trong khoảng nghi lộ: JWT, release artifact, hóa đơn, tài liệu, chứng thư.
- Đánh giá **token/chữ ký đã phát** và sự cần thiết của revoke/denylist, expiry, trust policy hoặc thông báo recipient.
- Duy trì metadata cần cho **xác minh chữ ký lịch sử hợp lệ**, phù hợp chính sách và chứng cứ thời gian.

### Signing oracle: key không xuất nhưng vẫn bị lạm dụng

Nếu HSM giữ private key **non-exportable** mà attacker có IAM `Sign`, đối thủ vẫn có thể yêu cầu HSM ký artifact giả. Khi đó:

- Private key **chưa chắc bị lộ dạng bytes**.
- Chữ ký output có thể **hợp lệ về mật mã** nhưng trái phép về nghiệp vụ.
- Phải ngăn **đường Sign API**, ràng buộc **digest/manifest đã được phê duyệt**, và điều tra chữ ký đã được tạo.
- Rotation signing key có thể là một phần phục hồi trust, nhưng **không thay được sửa business authorization**.

### JWT/JWKS

Với JWT đã ký bằng key nghi lộ:

- Kiểm tra **`kid`, issuer, audience, algorithm, expiry, token type** và trust source.
- Cập nhật JWKS/public keys và verifier theo kế hoạch; **xóa old public key khỏi trust** có thể khiến token hợp lệ chưa hết hạn bị từ chối.
- Nếu attacker có private signing key, họ có thể tạo token với **thời hạn/claim giả**; không chỉ chờ token bình thường hết hạn mà thiếu phân tích.
- Có thể cần thu hồi session, denylist, rút ngắn TTL, dùng key new issuer và cập nhật downstream trust tùy thiết kế.

**Không tin `kid` hoặc JWKS URL do token không đáng tin tự chỉ định** mà không có trust policy.

### X.509/PKI

Khi private key gắn chứng thư có nguy cơ compromise:

- Theo quy trình PKI/CA, xem xét **certificate revocation (CRL/OCSP), reissuance, trust updates** và phân phối thông tin.
- Đánh giá **timestamp, thời điểm ký, LTV** và các chữ ký lịch sử theo yêu cầu.
- Với **CA private key**, phạm vi ảnh hưởng có thể bao gồm nhiều chứng thư đã cấp; phải kích hoạt runbook PKI riêng.
- Không tuyên bố **mọi chữ ký trong quá khứ tự động vô hiệu** hay **mọi chữ ký vẫn đáng tin**. Kết luận phụ thuộc thời điểm chứng cứ, chain/policy và phạm vi compromise.

## 17. HMAC/shared secret: rotation cần phối hợp hai đầu

Với **HMAC**, bên tạo và bên xác minh MAC thường cùng biết secret. Nếu một đối tác làm lộ HMAC secret, không thể chỉ đổi server key rồi mặc định client biết khóa mới.

### Kế hoạch

1. Xác định **đối tác/tenant và version** dùng key có nguy cơ.
2. Sinh **HMAC key mới riêng** cho đối tác đó.
3. Cấp key mới qua **kênh provisioning được xác thực**, không gửi raw secret qua chat/email không được phê duyệt.
4. Chuẩn bị **key version identifier** và thời điểm cutover.
5. Khi cần, có **verification window** rất ngắn cho old key theo đánh giá rủi ro; tuyệt đối không âm thầm chấp nhận vĩnh viễn key nghi lộ.
6. Chống **replay** bằng timestamp/nonce/message ID theo giao thức và retention.
7. Từ chối new-use old key, kiểm tra các phía đã chuyển.
8. Thu hồi/hủy old key theo điều kiện và điều tra messages giả có thể đã phát.

### Một biến chứng

Nếu **cùng raw HMAC secret** được chia cho nhiều partners, **một sự cố ở một partner có thể kéo theo rotation toàn bộ**. Tách secret theo partner từ đầu để giới hạn blast radius.

### HMAC không thay chữ ký số

Một bên nhận HMAC biết secret và có khả năng tạo MAC hợp lệ. Vì vậy HMAC có mô hình phân chia trách nhiệm khác **chữ ký số bất đối xứng**; đừng kỳ vọng HMAC tạo bằng chứng người ký không thể chối bỏ theo cùng cách.

## 18. Agreement keys, TLS và forward secrecy

### Static ECDH/X25519

Nếu private agreement key dài hạn bị nghi lộ, phải:

- Thay key pair, phân phối **public key có xác thực**.
- Kiểm tra peer trust và KDF/key schedule.
- Đánh giá sessions/shared secrets đã dựa vào private key đó.
- Ngăn sử dụng lại old agreement key ngoài policy.

**ECDH thuần túy không tự xác thực peer**, nên rotation không sửa được lỗi MITM nếu không sửa giao thức xác thực.

### TLS server authentication private key

Một TLS certificate private key bị nghi compromise cần xử lý **new certificate/key pair, revoke/trust updates, server rollout** và đánh giá session tickets/credentials liên quan theo implementation.

**Một TLS 1.3 handshake dùng ephemeral key agreement phù hợp thường có forward secrecy đối với việc lộ riêng authentication key sau này**, trong phạm vi giả định giao thức và secret được xử lý đúng. Nhưng không suy ra **mọi TLS session/ticket và dữ liệu lịch sử đều an toàn**:

- Session secrets, ticket encryption keys và 0-RTT có rủi ro riêng.
- Host compromise có thể lấy plaintext hoặc traffic secrets.
- Ứng dụng/giao thức khác có thể không dùng ephemeral agreement đúng.
- Dữ liệu cũ có thể đã bị truy cập trực tiếp, không thông qua phá TLS.

### Ephemeral key compromise

Với một session key tạm bị lộ, hướng xử lý thường gồm **đóng hoặc renegotiate/establish phiên mới theo giao thức**, đánh giá traffic đã bị lộ. Không dùng một private ephemeral key qua nhiều sessions trái thiết kế chỉ để giảm chi phí.

## 19. KMS/HSM: non-exportable giảm rủi ro nhưng không thay IAM

Một key trong HSM có thể được cấu hình `non-exportable` và chỉ cho operation phù hợp. Điều đó bảo vệ một số đường lộ raw material, nhưng **không bảo đảm mọi lệnh ký/giải mã đều hợp lệ về nghiệp vụ**.

### Ba tầng cần kiểm soát

~~~mermaid
flowchart TD
    Request[Yêu cầu business] --> Business[Business auth: purpose, tenant, content approval]
    Business -->|Allow| IAM[IAM/control plane: principal, grant, key state]
    IAM -->|Allow| HSM[KMS/HSM key operation]
    HSM --> Output[Ciphertext, signature, plaintext DEK tùy API]
    Business -->|Deny| Deny[Từ chối và audit]
    IAM -->|Deny| Deny
    HSM --> ProviderLog[Provider audit]
    Business --> AppLog[Application audit]
    IAM --> IAMLog[Policy audit]
    ProviderLog --> Join[Incident correlation]
    AppLog --> Join
    IAMLog --> Join
~~~

### Key operation là “oracle” nếu IAM hoặc business auth sai

- **Signing oracle:** caller ký digest tùy ý với private key protected.
- **Decrypt oracle:** caller có thể gửi ciphertext của dữ liệu không thuộc scope để lấy plaintext.
- **Unwrap oracle:** caller nhận plaintext DEK cho wrapped key không được phép.
- **Derivation oracle:** caller chọn context khác để sinh subkey ngoài purpose.

**Không phải mọi dịch vụ có các API trên theo cùng tên**, nhưng rủi ro tương tự tồn tại khi được cấp operation với scope quá rộng.

### Hành động khi nghi lộ IAM credential

1. Chặn đường gọi bằng principal cũ; thu hồi grants/role token và kiểm tra hiệu lực.
2. Audit operation nào đã **trả raw DEK, plaintext, signature hoặc derived key**.
3. Nếu key material non-exportable và chỉ có bằng chứng `Sign` abuse, phân loại tác động **chữ ký trái phép** thay vì tuyên bố raw private key chắc chắn đã lộ.
4. Nếu API trả plaintext DEK, phải đánh giá các DEK đã được xuất **dù KEK vẫn non-exportable**.
5. Sửa điều kiện IAM và business authorization; không chỉ rotate key rồi giữ credential sai.
6. Đổi material/key pair khi chính sách hoặc risk assessment yêu cầu.

### `CKA_EXTRACTABLE` và import provenance

Trong PKCS#11, `CKA_EXTRACTABLE`, `CKA_SENSITIVE`, `CKA_SIGN`, `CKA_DECRYPT`, `CKA_WRAP` v.v. có ý nghĩa token-specific. Không suy ra một key “chưa bao giờ lộ” chỉ từ trạng thái hiện tại `CKA_EXTRACTABLE=false`; có thể từng **import key từ nguồn bên ngoài**.

## 20. Điểm mù plaintext DEK, cache và bản sao khóa

Trong envelope encryption, một KMS có thể giữ KEK non-exportable nhưng trả **plaintext DEK tạm** để ứng dụng thực hiện AES-GCM tại host.

~~~text
KMS:
    Unwrap(KEK, wrappedDEK) -> DEK plaintext cho client, nếu API cho phép

Ứng dụng:
    cache DEK trong RAM
    AES-GCM Decrypt/Encrypt nhiều record
    không gọi KMS cho mỗi record
~~~

### Vì sao quan trọng khi ứng cứu?

- **0 lượt `Decrypt`/`Unwrap` mới tại KMS** không chứng minh **0 lần giải mã local**.
- `Disable KEK` không tự xóa DEK plaintext trong RAM.
- Kẻ tấn công chiếm host có thể đọc DEK từ **heap, crash dump, telemetry hoặc file tạm**.
- Nếu DEK được share theo tenant/dataset, một bản lộ có thể ảnh hưởng nhiều ciphertext.
- Một hệ thống multi-region có thể có cached DEK ở nhiều node khác nhau.

### Kiểm soát

- TTL và phạm vi cache phù hợp risk tier.
- Cơ chế invalidation/restart/cô lập instance khi nghi lộ.
- Không log raw DEK, KEK, private key, HSM PIN hoặc plaintext.
- Giới hạn quyền host/debug/backup và khả năng lấy process dump.
- Dùng **per-object DEK hoặc purpose scoping** khi cần giảm blast radius.
- Xem xét **encryption gateway/HSM operation** nếu không chấp nhận raw DEK ở host.

**Java `Arrays.fill` không đảm bảo xóa mọi bản sao secret trong heap/native memory**; zeroization phải được hiểu đúng boundary và provider.

## 21. Java 11+: policy gate khi key bị nghi compromise

Ví dụ sau mô phỏng **key lifecycle gate** trong một service. Nó thể hiện:

- Key đang `ACTIVE` và không có incident được phép **new encrypt** theo đúng principal/purpose.
- Khi chuyển sang `SUSPECTED` hoặc `CONFIRMED`, **new-use bị chặn**.
- Legacy decryption có thể chỉ được cấp cho **recovery worker** dưới **approval riêng, trong phạm vi hẹp**.
- `DESTROY` không được thực hiện bởi API key use thông thường.
- Mỗi quyết định tạo **audit metadata không chứa raw key**.

**Đây là ví dụ policy logic, không gọi KMS/HSM và không thể thay thế IAM/provider enforcement.** Trạng thái suspected/confirmed là mô hình quản trị của ứng dụng, không phải key state phổ quát của mọi KMS.

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

public final class SuspectedKeyCompromiseGateDemo {

    enum KeyState {
        PRE_ACTIVATION, ACTIVE, SUSPENDED,
        DEACTIVATED, COMPROMISED, DESTROYED
    }

    enum IncidentConfidence {
        NONE, SUSPECTED, CONFIRMED
    }

    enum Operation {
        NEW_ENCRYPT, NEW_SIGN, LEGACY_DECRYPT, DESTROY
    }

    enum Principal {
        BILLING_WRITER, SIGNING_GATEWAY,
        BILLING_READER, INCIDENT_RECOVERY
    }

    enum Purpose {
        BILLING_DATA, INVOICE_SIGNATURE
    }

    static final class KeyRecord {
        final String id;
        final String materialVersion;
        final Purpose purpose;
        final KeyState state;
        final IncidentConfidence incident;
        final long policyRevision;

        KeyRecord(String id, String materialVersion, Purpose purpose,
                  KeyState state, IncidentConfidence incident,
                  long policyRevision) {
            this.id = Objects.requireNonNull(id);
            this.materialVersion = Objects.requireNonNull(materialVersion);
            this.purpose = Objects.requireNonNull(purpose);
            this.state = Objects.requireNonNull(state);
            this.incident = Objects.requireNonNull(incident);
            this.policyRevision = policyRevision;
        }
    }

    static final class Request {
        final String requestId;
        final Principal principal;
        final Operation operation;
        final Purpose requestedPurpose;
        final boolean recoveryApprovalVerified;

        Request(String requestId, Principal principal,
                Operation operation, Purpose requestedPurpose,
                boolean recoveryApprovalVerified) {
            this.requestId = Objects.requireNonNull(requestId);
            this.principal = Objects.requireNonNull(principal);
            this.operation = Objects.requireNonNull(operation);
            this.requestedPurpose = Objects.requireNonNull(requestedPurpose);
            this.recoveryApprovalVerified = recoveryApprovalVerified;
        }
    }

    static boolean allow(KeyRecord key, Request request) {
        if (key.purpose != request.requestedPurpose
                || key.state == KeyState.DESTROYED
                || key.state == KeyState.PRE_ACTIVATION) {
            return false;
        }

        // Hủy key thuộc workflow đặc biệt, không qua API use thông thường.
        if (request.operation == Operation.DESTROY) {
            return false;
        }

        // Incident: không cho phép tạo ciphertext/chữ ký mới bằng key cũ.
        boolean incidentOpen = key.incident != IncidentConfidence.NONE;
        if (incidentOpen) {
            return request.operation == Operation.LEGACY_DECRYPT
                    && key.purpose == Purpose.BILLING_DATA
                    && request.principal == Principal.INCIDENT_RECOVERY
                    && request.recoveryApprovalVerified
                    && (key.state == KeyState.SUSPENDED
                        || key.state == KeyState.COMPROMISED);
            // Production phải có scope, TTL, approval độc lập,
            // KMS enforcement, audit và cô lập recovery worker thật.
        }

        if (key.state != KeyState.ACTIVE) {
            return false;
        }

        return (request.operation == Operation.NEW_ENCRYPT
                   && key.purpose == Purpose.BILLING_DATA
                   && request.principal == Principal.BILLING_WRITER)
                || (request.operation == Operation.NEW_SIGN
                   && key.purpose == Purpose.INVOICE_SIGNATURE
                   && request.principal == Principal.SIGNING_GATEWAY)
                || (request.operation == Operation.LEGACY_DECRYPT
                   && key.purpose == Purpose.BILLING_DATA
                   && request.principal == Principal.BILLING_READER);
    }

    static void process(KeyRecord key, Request request, Clock clock) {
        boolean permitted = allow(key, request);

        // Chỉ in metadata ID và quyết định; KHÔNG in secret/payload.
        Instant time = clock.instant();
        System.out.printf(
                "time=%s req=%s key=%s version=%s incident=%s"
                + " state=%s op=%s actor=%s decision=%s policyRev=%d%n",
                time, request.requestId, key.id, key.materialVersion,
                key.incident, key.state, request.operation,
                request.principal, permitted ? "ALLOW" : "DENY",
                key.policyRevision);

        if (!permitted) {
            throw new SecurityException("Key use denied");
        }

        // Demo không thực thi phép mật mã: ALLOW != provider success.
    }

    public static void main(String[] args) {
        Clock clock = Clock.systemUTC();

        KeyRecord normal = new KeyRecord(
                "billing-dek-v1", "v1", Purpose.BILLING_DATA,
                KeyState.ACTIVE, IncidentConfidence.NONE, 18L);

        KeyRecord suspected = new KeyRecord(
                "billing-dek-v1", "v1", Purpose.BILLING_DATA,
                KeyState.SUSPENDED, IncidentConfidence.SUSPECTED, 19L);

        Request newEncrypt = new Request(
                "req-new-write", Principal.BILLING_WRITER,
                Operation.NEW_ENCRYPT, Purpose.BILLING_DATA, false);

        process(normal, newEncrypt, clock); // Allow trên policy demo.

        try {
            process(suspected, newEncrypt, clock);
            throw new AssertionError("Suspected key accepted for new use");
        } catch (SecurityException expected) {
            System.out.println("Suspected key new-use: blocked");
        }

        Request recovery = new Request(
                "req-incident-recovery", Principal.INCIDENT_RECOVERY,
                Operation.LEGACY_DECRYPT, Purpose.BILLING_DATA, true);
        process(suspected, recovery, clock);
        System.out.println("Recovery policy gate passed; provider not called");

        Request unapprovedRecovery = new Request(
                "req-without-approval", Principal.INCIDENT_RECOVERY,
                Operation.LEGACY_DECRYPT, Purpose.BILLING_DATA, false);
        try {
            process(suspected, unapprovedRecovery, clock);
            throw new AssertionError("Unapproved recovery accepted");
        } catch (SecurityException expected) {
            System.out.println("Unapproved recovery: blocked");
        }
    }
}
~~~

### Giải thích giới hạn

1. `recoveryApprovalVerified=true` là **giả định demo**. Production không tin một boolean do client gửi: phải xác minh **approval source, identity, scope, TTL, key ID/version và ticket**.
2. Nếu **KMS đang disable hoàn toàn key**, gate `ALLOW` không khiến `Decrypt` thành công; phải chọn **recovery path thực sự được nhà cung cấp hỗ trợ và chấp thuận**.
3. Trong nhiều sự cố confirmed, legacy decrypt có thể quá rủi ro. Quy trình thật có thể **chặn hoàn toàn** thay vì cho recovery; demo chỉ minh họa đường ngoại lệ được giám sát.
4. Mã không triển khai **business authorization, tenant isolation, rate limiting, provider audit hoặc WORM log**.
5. Khi policy cho phép, kết quả mới chỉ là **authorization decision**; phải ghi event thực thi `SUCCESS/FAILURE` riêng.
6. **Không dùng gate trong JVM** để thay thế quyền IAM/PKCS#11/HSM. Nếu app bị chiếm quyền, attacker có thể bypass gate.
7. Không có logic để resume key sau khi suspicion được loại trừ; đó là **workflow phê duyệt khác**, không phải `incident=NONE` tự động.
8. **Không dùng key compromised để tạo output mới** và không hủy bằng thao tác API mặc định.

## 22. Java 11+: minh họa re-encrypt khi DEK-v1 bị nghi lộ

Ví dụ thứ hai minh họa bản chất mật mã khi đổi **DEK**. Nó dùng:

- Hai **AES-256 DEKs khác nhau** được sinh bằng `KeyGenerator`.
- AES-GCM với **nonce 96 bit mới** và tag 128 bit.
- **AAD** ràng buộc tenant, record ID, DEK version và revision bằng length-prefix.
- `Decrypt.doFinal()` xác minh tag trước khi dùng plaintext làm nguồn re-encrypt.
- `AtomicReference.compareAndSet` mô phỏng commit có kiểm tra revision.
- Negative test thay tenant làm xác minh tag thất bại.

**Ví dụ không có KMS/HSM/wrapped DEK thực; key tồn tại trong JVM và chỉ phục vụ học thuật.**

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicReference;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public final class SuspectedDekReencryptDemo {

    private static final SecureRandom RNG = new SecureRandom();
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;

    static final class EncryptedRecord {
        final String tenant;
        final String id;
        final String dekVersion;
        final long revision;
        final byte[] nonce;
        final byte[] ciphertextAndTag;

        EncryptedRecord(String tenant, String id, String dekVersion,
                        long revision, byte[] nonce,
                        byte[] ciphertextAndTag) {
            this.tenant = tenant;
            this.id = id;
            this.dekVersion = dekVersion;
            this.revision = revision;
            this.nonce = nonce.clone();
            this.ciphertextAndTag = ciphertextAndTag.clone();
        }
    }

    static SecretKey freshAes256Key()
            throws GeneralSecurityException {
        KeyGenerator generator = KeyGenerator.getInstance("AES");
        generator.init(256, RNG);
        return generator.generateKey();
    }

    static void field(DataOutputStream out, String text)
            throws java.io.IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    static byte[] aad(EncryptedRecord record)
            throws java.io.IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        field(out, "billing/aes-gcm-record/v1");
        field(out, record.tenant);
        field(out, record.id);
        field(out, record.dekVersion);
        out.writeLong(record.revision);
        out.flush();
        return bytes.toByteArray();
    }

    static EncryptedRecord encrypt(
            String tenant, String id, String version, long revision,
            byte[] plaintext, SecretKey dek) throws Exception {

        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);

        EncryptedRecord ctx = new EncryptedRecord(
                tenant, id, version, revision, nonce, new byte[0]);

        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, dek,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad(ctx));
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);

        return new EncryptedRecord(
                tenant, id, version, revision,
                nonce, ciphertextAndTag);
    }

    static byte[] decrypt(EncryptedRecord record, SecretKey dek)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, dek,
                new GCMParameterSpec(TAG_BITS, record.nonce));
        cipher.updateAAD(aad(record));
        return cipher.doFinal(record.ciphertextAndTag);
    }

    public static void main(String[] args) throws Exception {
        SecretKey dekV1 = freshAes256Key();
        SecretKey dekV2 = freshAes256Key();
        byte[] original = "training-invoice-data"
                .getBytes(StandardCharsets.UTF_8);

        try {
            EncryptedRecord old = encrypt(
                    "tenant-a", "invoice-42", "dek-v1",
                    7L, original, dekV1);

            AtomicReference<EncryptedRecord> slot =
                    new AtomicReference<>(old);
            EncryptedRecord snapshot = slot.get();

            // Điều kiện incident xử lý ở policy/IAM bên ngoài demo:
            // DEK-v1 không được dùng tạo ciphertext mới.
            byte[] recovered = decrypt(snapshot, dekV1);
            EncryptedRecord next;
            try {
                next = encrypt(
                        snapshot.tenant, snapshot.id, "dek-v2",
                        snapshot.revision + 1, recovered, dekV2);
            } finally {
                Arrays.fill(recovered, (byte) 0);
            }

            // CAS giả lập: không ghi đè nếu record đổi trong lúc migrate.
            if (!slot.compareAndSet(snapshot, next)) {
                throw new IllegalStateException(
                        "Concurrent modification; reread before retry");
            }

            byte[] checked = decrypt(slot.get(), dekV2);
            try {
                System.out.println("Content preserved: "
                        + MessageDigest.isEqual(original, checked));
                System.out.println("New key version: "
                        + slot.get().dekVersion);
            } finally {
                Arrays.fill(checked, (byte) 0);
            }

            // AAD thay tenant phải khiến GCM authentication fail.
            EncryptedRecord tampered = new EncryptedRecord(
                    "tenant-b", next.id, next.dekVersion,
                    next.revision, next.nonce, next.ciphertextAndTag);

            try {
                decrypt(tampered, dekV2);
                throw new AssertionError("Wrong tenant AAD accepted");
            } catch (AEADBadTagException expected) {
                System.out.println("Wrong tenant AAD: rejected");
            }
        } finally {
            Arrays.fill(original, (byte) 0);
        }

        // Không in DEK, plaintext, HSM PIN, secrets hay ciphertext.
        // Production cần KMS/HSM, wrapped DEK, transactions,
        // approval, incident audit, backup/DR và IAM.
    }
}
~~~

### Kết quả dự kiến

~~~text
Content preserved: true
New key version: dek-v2
Wrong tenant AAD: rejected
~~~

### Điều ví dụ không chứng minh

- Raw DEK-v1 của một sự cố thật chưa chắc còn ở nơi có thể truy cập; migration có thể cần **break-glass restore** được kiểm soát.
- `AtomicReference` chỉ bảo vệ **một object trong một JVM**, không thay DB CAS/transaction trên nhiều instance.
- Hai secret được sinh trong cùng JVM, nên không chứng minh key material được bảo vệ bởi HSM.
- **Nonce ngẫu nhiên 96 bit** không chứng minh không va chạm tại quy mô lớn; phải có chiến lược nonce/usage limit phù hợp.
- Demo không bao gồm **wrapped DEK, KEK version, data scope, tenant authorization, backups hoặc incident notification**.
- `Arrays.fill` là **best effort**, không chứng minh zeroization mọi bản sao trong native/JVM memory.
- Re-encrypt không làm old ciphertext/DEK mà attacker đã copy biến mất.
- Với ciphertext cũ đã mất bảo đảm integrity, phải xác minh nguồn dữ liệu theo runbook, không mặc định mọi plaintext nhận được là đáng tin.

## 23. Backup, archive, HA và DR sau incident rotation

Một trong những lỗi lớn nhất là **hủy khóa cũ trước khi biết mọi dữ liệu phụ thuộc**.

### Những nơi phải tìm

- Wrapped DEK ở database/object store.
- Ciphertext-v1 trong **database snapshot, point-in-time recovery, archive lạnh**.
- Object version cũ và cross-region replication.
- HSM/KMS protected backup, key replicas và recovery media.
- Plaintext DEK/key trong application memory, cache hoặc dump.
- Bản export hợp pháp cho đối tác, escrow hoặc legal hold.
- Chứng thư/public keys và **signature history**.
- Event/incident evidence có retention riêng.

### HA không tự là backup

Cụm HSM/KMS hỗ trợ **availability** nhưng lỗi policy hoặc xóa nhầm có thể lan sang replica. Cần **restore drill** được kiểm soát, xác nhận cả key material/attributes và quyền sử dụng, không chỉ node còn online.

### Hai tình huống mâu thuẫn cần giải quyết

- **Security:** muốn vô hiệu key nghi lộ càng sớm càng tốt.
- **Recovery:** backup lịch sử còn được mã hóa bằng key đó và có retention bắt buộc.

Có thể cần giữ **legacy decrypt-only trong một boundary cô lập**, chỉ với incident approval, giám sát và thời hạn, cho đến khi đã di chuyển/không còn phụ thuộc. Nhưng nếu raw key đã confirmed compromised, việc duy trì bất kỳ đường sử dụng nào phải được **risk assessment riêng**; không có quy tắc bắt buộc luôn cho phép legacy decrypt.

### Không tuyên bố “đã zeroize mọi nơi” chỉ từ một API

`Disable`, `ScheduleDeletion`, xóa alias và `DestroyKey` có semantics khác nhau theo provider. Phải có **evidence về trạng thái key thực**, replicas, backup và retention; không giả định xóa từ KMS làm mọi bản sao ngoài KMS biến mất.

## 24. Multi-region, cache và rollback trong sự cố

Một rotation khẩn cấp có thể thất bại khi chỉ kiểm tra **region chính**.

### Những race thường gặp

1. Region A chuyển new writes sang key-v2, region B vẫn dùng key-v1 do config cache.
2. Reader ở region C chưa biết key-v2 nên không mở được ciphertext mới.
3. Migration worker đọc revision cũ rồi ghi đè dữ liệu người dùng vừa cập nhật.
4. Alias trỏ v2 nhưng job cũ **đã giữ handle/material v1**.
5. KMS disable key-v1 nhưng service còn plaintext DEK-v1 cached.
6. Replication chậm khôi phục object version cũ sau cutover.
7. Rollback code vô tình tiếp tục ký/mã hóa bằng v1.

### Kiểm soát

- Reader/verifier readiness across regions.
- **Writer fencing** và server-side authorization theo version.
- Key-version metadata gắn trên mỗi ciphertext/signature.
- **CAS/ETag/transactions** khi migration thay dữ liệu.
- Telemetry số **new-use v1** sau thời điểm cutover.
- Chặn fallback tự động sang key nghi lộ.
- Cache TTL/invalidation, session revocation và restart/cô lập workload nghi vấn.
- Replication/DR drills trước khi tuyên bố hoàn tất.

**Rollback ứng dụng không phải rollback trạng thái compromise.** Nếu hệ thống đã ghi dữ liệu bằng v2, rollback vẫn phải **đọc được v2**, không tái cho phép new-use v1 ngoài quy trình được đánh giá.

## 25. Audit: tách evidence, decision và execution

Một incident-driven rotation cần một **timeline có thể tái dựng**: ai phát hiện, ai quyết định, provider đã làm gì, dữ liệu đã chuyển tới đâu.

### Event schema minh họa

~~~yaml
schemaVersion: "1"
incidentId: "INC-2030-042"
eventType: "KEY_INCIDENT_ROTATION_CUTOVER"
eventId: "evt-2030-1010"
occurredAtUtc: "2030-05-12T10:10:00Z"
actor: "security-incident-controller"
key:
  oldKeyId: "billing-kek-v3"
  oldMaterialVersion: "v3"
  newKeyId: "billing-kek-v4"
  newMaterialVersion: "v4"
  purpose: "DEK_KEY_WRAPPING"
incident:
  suspectedMode: "CREDENTIAL_AND_UNWRAP_API_MISUSE"
  confidence: "SUSPECTED"
  earliestPossibleExposureUtc: "UNKNOWN"
decision:
  oldKeyNewUse: "BLOCK"
  legacyDecryptPolicy: "INCIDENT_APPROVAL_ONLY"
  approvalRef: "incident-approval-52"
  keyPolicyRevision: "policy-r31"
execution:
  writerCutoverConfirmed: true
  kmsChangeEventRef: "provider-event-id"
  dataMigrationStatus: "IN_PROGRESS"
audit:
  correlationId: "corr-incident-042"
  containsRawKeyMaterial: false
~~~

**Đây là schema ví dụ**, không phải log API chuẩn của một KMS/HSM. Thông tin `writerCutoverConfirmed` phải đến từ **bằng chứng operation/data version thực**, không chỉ từ một deployment success notification.

### Những event quan trọng

| Nguồn | Sự kiện | Ý nghĩa |
| --- | --- | --- |
| IAM | Credential disabled, grants revoked, policy changed | Cô lập quyền |
| KMS/HSM | `Sign`, `Decrypt`, `Unwrap`, key disable/rotate | Hoạt động thực tế của provider nếu logging hỗ trợ |
| Ứng dụng | Business approval, data access, output key version | Ngữ nghĩa dữ liệu/chữ ký |
| Migration worker | Batch commit, conflict, error, quarantine | Tiến độ thực |
| DB/object store | Row revision/ETag, object version | Tránh mất dữ liệu |
| PKI/JWKS | Certificate published/revoked, trust updated | Cutover niềm tin |
| Backup/DR | Restore drill, dependency scan | Khả năng khôi phục |
| Security operations | Incident decision, approval, exception, close | Trách nhiệm và hậu kiểm |

### Không log raw secrets

**Không đưa DEK, KEK, private key, master, HSM PIN, access token, plaintext, signed payload nhạy cảm hoặc memory dump vào audit event**. Dùng key ID/version, event ID, principal, operation, scope, result, policy revision và correlation ID.

### Log không phải bằng chứng bao phủ hoàn toàn

- HSM có thể **không log từng `C_Sign`** tùy cấu hình.
- KMS thường không biết **local AES-GCM Decrypt** bằng DEK cached.
- Application log có thể sai hoặc bị tắt khi process bị chiếm.
- Đồng hồ phân tán có **clock skew/ingest lag**.

Bảo vệ log bằng quyền độc lập, integrity/WORM khi cần, đối soát **application/control-plane/provider** và giám sát chính collector.

## 26. Case study A — Credential KMS của Billing bị nghi lộ

### Bối cảnh

`billing-platform` mã hóa hóa đơn bằng **AES-GCM DEK** per record, DEK được bọc bằng KEK trong managed KMS. Credential của `billing-reader-prod` xuất hiện trong một môi trường ngoài chính sách.

Hệ thống phát hiện một số `Unwrap` calls lúc không có corresponding business request. **Chưa có bằng chứng raw KEK rời khỏi KMS**.

### Timeline giả định

| Giờ UTC | Quan sát | Hành động |
| --- | --- | --- |
| 09:30 | Security nhận tín hiệu credential bị lộ | Tạo incident và bảo toàn log |
| 09:33 | IAM/KMS thấy `Unwrap` bất thường | Thu hồi credential/grants liên quan |
| 09:38 | Kiểm tra provider event IDs, key/resource scope | Phân loại DEK nào có thể đã được trả |
| 09:45 | Tạo identity sạch và KEK-v4 theo policy | Chuẩn bị reader và tests |
| 10:10 | Writer dùng KEK-v4 để bọc DEK mới | Chặn new-use v3 và audit cutover |
| 10:30 | Migration rewrap bắt đầu | Đối soát wrapped DEK và phụ thuộc |
| Sau đó | Xét DEK nào có thể bị lấy plaintext | Quyết định re-encrypt records tương ứng |

Các mốc chỉ minh họa, **không phải SLA tiêu chuẩn**.

### Hai nhánh điều tra

**Nhánh 1 — Không có bằng chứng plaintext DEK bị trả, nhưng chưa chắc chắn tuyệt đối**

- Cô lập credential là ưu tiên.
- Có thể rotate KEK và **rewrap** theo policy.
- Giữ theo dõi app/cache và xác minh log coverage.
- Có thể áp dụng thêm biện pháp bảo vệ tùy risk tier.

**Nhánh 2 — Một số `Unwrap` success trả DEK plaintext**

- Xác định **wrapped DEK/key IDs và ciphertext** liên quan.
- Chỉ rewrap KEK không đủ cho **những DEK có thể đã lộ**.
- Sinh DEK mới, **re-encrypt** dữ liệu phù hợp và đánh giá old copies/backup.
- Kết hợp data-access audit, vì attacker có thể decrypt offline sau khi nhận DEK.

### Bài học

**Credential compromise không tự chứng minh raw KEK bị lộ**, nhưng có thể dẫn đến lộ **DEK plaintext** hoặc dữ liệu thông qua API có quyền. Rotation đúng phải dựa trên **output có thể đã rời boundary**, không chỉ key resource nào được gọi.

## 27. Case study B — HSM signing key được dùng ký release trái phép

### Bối cảnh

Private key `release-signing-v5` được tạo trong HSM và đặt **non-exportable**. Pipeline CI bị chiếm một service account có quyền `Sign`. Attackers đã gọi trực tiếp API và tạo các chữ ký trên manifest chưa được release owner phê duyệt.

### Cần phân biệt

- Private signing key **có thể vẫn chưa từng rời HSM**.
- Các chữ ký được tạo bởi HSM vẫn có thể **verify đúng về mật mã**.
- Hệ thống không có bằng chứng đủ rằng output đó hợp lệ về nghiệp vụ.
- Nếu artifact được công bố, consumers có thể tin các chữ ký theo trust policy cũ.

### Quy trình ứng cứu

1. Thu hồi service credential, grants và chặn đường `Sign` trực tiếp.
2. Bảo toàn HSM audit, CI logs, manifest/digest reference và release approvals.
3. Liệt kê output được ký ngoài workflow; xác định có artifact nào đã phát hành.
4. Sinh signing key v6 trong boundary sạch và review key usage.
5. Chuyển signing service sang **exact digest/manifest approval** với IAM least privilege.
6. Phân phối verifier trust/public key v6; xử lý public trust v5 và artifact đã ký trái phép.
7. Không hủy dữ liệu chứng minh/vật liệu cần cho forensics trước khi có kế hoạch lưu giữ.
8. Giám sát mọi `Sign` mới với key-v5 và direct API bypass.

### Bài học

**Rotation private key giúp thiết lập trust mới**, nhưng nếu service tiếp tục cho gọi `Sign` trên nội dung tùy ý thì **v6 cũng có thể bị lạm dụng**. Phải sửa cả authorization và release workflow.

## 28. Case study C — HMAC key chung bị lộ tại một đối tác

### Bối cảnh

Ba đối tác cùng dùng một HMAC key để gửi webhook tới API của doanh nghiệp. Một đối tác báo đã lưu secret trong repository công khai.

### Vì sao phạm vi lớn?

- Cùng một secret có thể tạo MAC hợp lệ cho **cả ba đối tác**, nếu API không tách identity/context phù hợp.
- Các message đã được chấp nhận có thể gồm message giả, replay hoặc data bị sửa.
- Đổi shared secret một phía có thể làm hỏng webhook của các đối tác chưa chuyển.

### Thiết kế xử lý

1. Thu hồi/chặn old key qua gateway khi rủi ro cho phép; dùng chính sách tạm thời được phê duyệt nếu cần duy trì dịch vụ.
2. Sinh **HMAC key riêng per partner**, quản lý version và trust distribution riêng.
3. Bổ sung **partner identity binding, timestamp/nonce/message ID và anti-replay**.
4. Phát key mới qua provisioning được xác thực.
5. Cắt new-use old key, giám sát failed verification và lạm dụng replay.
6. Xử lý lịch sử webhook giả và nghĩa vụ thông báo.
7. Thay đổi key inventory để không còn một raw secret xuyên nhiều trust domains.

**Bài học:** Khóa bị chia sẻ cho nhiều bên làm tăng blast radius; rotation khi compromise là cơ hội sửa lại **key granularity và purpose separation**, không chỉ đổi bytes.

## 29. Khi suspicion bị loại trừ, có thể resume key cũ không?

Không có câu trả lời chung. **Kết luận không compromise** phải dựa trên bằng chứng: log coverage, identity investigation, timeline, HSM/key provenance, operation output và risk acceptance.

### Quy tắc ra quyết định

- **Nếu chỉ là cấu hình sai và không có dấu hiệu raw key lộ:** có thể cân nhắc tiếp tục key theo workflow được phê duyệt.
- **Nếu không thể loại trừ raw key exposure:** ưu tiên material mới, đặc biệt với tài sản rủi ro cao.
- **Nếu đã cutover và tạo output bằng key mới:** không nên bật new-use key cũ chỉ để tiện rollback.
- **Nếu key cũ có dấu hiệu bị dùng tạo chữ ký trái phép:** cần đánh giá trust và output, dù key chưa bị export.
- **Nếu HSM báo tamper/entropy lỗi:** theo tài liệu vendor và quy trình bảo đảm; không tự resume sau một reboot.
- **Nếu key đã được đánh dấu `COMPROMISED` và material lộ confirmed:** không coi việc sửa IAM là phục hồi tính bí mật.

### Ghi rõ ba quyết định độc lập

1. **Incident status:** suspected / confirmed / ruled out.
2. **Key lifecycle state:** suspended / deactivated / compromised / destroyed.
3. **Operation authorization:** new-use, legacy decrypt, verify historical và recovery exception.

Một incident đóng **không tự động** có nghĩa key cũ lại được phép tạo output mới.

## 30. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chờ xác nhận raw key lộ rồi mới chặn credential | Attacker tiếp tục dùng key API | Cô lập quyền theo risk tier ngay khi có chỉ dấu |
| Xem API misuse là chắc chắn raw key leak | Phân loại sai, gây gián đoạn không cần thiết | Xác định output và boundary thật |
| Xem HSM non-exportable là đủ chống misuse | Signing/decrypt oracle còn hoạt động | IAM + business authorization |
| Chỉ rotate key, không thu hồi credential bị lấy | Key v2 tiếp tục bị lạm dụng | Contain identity và self-escalation |
| Đổi alias từ v1 sang v2 mà vật liệu không đổi | Không có rotation thực | Tạo material mới và kiểm tra provenance |
| Tạo key mới bằng RNG/seed đã bị nghi lỗi | Lặp nguyên nhân compromise | Sửa nguồn entropy trước |
| Rewrap DEK đã bị lộ bằng KEK mới | Raw DEK vẫn giải mã được dữ liệu | Thay DEK, re-encrypt theo scope |
| Nghĩ re-encrypt xóa data attacker từng lấy | Không thể thu hồi bản sao cũ | Đánh giá old ciphertext, backup và notification |
| Xóa KEK-v1 trước khi hoàn tất migration | Mất khả năng unwrap dữ liệu cũ | Dependency inventory và DR drill |
| Disable KEK rồi tưởng DEK cached đã bị xóa | Local decrypt vẫn có thể xảy ra | Cache invalidation và cô lập host |
| Dùng lại nonce AES-GCM sau migration | Có thể phá bảo mật GCM | Nonce mới/strategy không lặp |
| Bỏ qua GCM tag để cứu dữ liệu | Chấp nhận plaintext không xác thực | Quarantine và integrity incident |
| Không ràng buộc record revision khi re-encrypt | Mất cập nhật của user | CAS/transaction |
| Rollback writer sang key nghi lộ | Tiếp tục phát ciphertext/signature rủi ro | Fencing, incident-approved decisions |
| Chỉ cập nhật một region | Region khác tiếp tục dùng v1 | Multi-region readiness/monitoring |
| Gỡ JWKS old key mà không xét token còn hiệu lực | Từ chối token hợp lệ ngoài ý định | Trust transition và incident policy |
| Không loại old signing trust khi key thật sự lộ | Attacker có thể tiếp tục tạo chữ ký/token được tin | Trust revocation/update theo yêu cầu |
| Coi mọi chữ ký lịch sử tự động vô hiệu | Phân tích sai bằng chứng/trust | Timestamp, certificate status, policy |
| Coi certificate renewal là key pair rotation | Private key cũ vẫn tồn tại | Sinh cặp khóa mới khi cần |
| Rotate HMAC chỉ phía server | Partner không đồng bộ | Provisioning và versioned cutover |
| HKDF tiếp từ master compromised | Subkey mới vẫn có thể bị tính | Thay master và descendants |
| Quên backup/object versions/DR | Còn phụ thuộc key cũ | Inventory/restore drills |
| Không giữ bằng chứng trước xóa | Mất timeline điều tra | Forensics và immutable audit |
| Ghi raw DEK/private key vào log incident | Tạo thêm key compromise | Audit chỉ metadata/refs |
| Tuyên bố 0 KMS calls là 0 data access | Bỏ sót cached DEK | Application data-access audit |
| Ghi `ALLOW` là đã Sign/Decrypt thành công | Nhầm decision và execution | Provider result event riêng |
| Chỉ test trên mock, không test IAM thật | Bypass vẫn có thể tồn tại | Negative integration tests |
| Không đối soát quyền indirect `CreateGrant` | Self-escalation | Separation of duties + policy boundaries |
| Hủy old key theo tỷ lệ migration 99% | 1% dữ liệu còn lại có thể mất | Verify 100% dependencies theo scope |
| Mặc định mọi nghi ngờ cần phá hủy ngay | Có thể mất dữ liệu hoặc bằng chứng | Risk-based containment và recovery planning |

## 31. Checklist production cho rotation khi nghi ngờ compromise

### A. Phát hiện, phân loại và cô lập

1. **Incident ID:** Có event, owner, incident commander và mốc phát hiện/earliest plausible exposure?
2. **Key inventory:** Có key ID/material version, purpose, origin, parent-child, tenant/environment và dependencies?
3. **Loại nghi ngờ:** Raw material, API misuse, credential, IAM, RNG, HSM tamper hay trust compromise?
4. **Bằng chứng:** Có lưu KMS/HSM, IAM, application, CI/CD và backup logs an toàn?
5. **Containment:** Đã chặn credential/grants/role trust và đường calling API nghi vấn?
6. **Key state:** Có phân biệt `SUSPENDED`, provider `Disabled`, `COMPROMISED` và `DESTROYED`?
7. **Business scope:** Những người dùng, tenant, record, signatures và partners nào chịu ảnh hưởng?
8. **Không tự nâng quyền:** Admin hoặc workload có thể sửa policy/tự cấp Decrypt/Sign không?
9. **Cache/secrets:** Đã kiểm tra raw DEK trong app/cache/host dumps, protected backup và secret store?
10. **Availability:** Nếu disable KEK làm reader không hoạt động, có recovery path được phê duyệt không?

### B. Chuẩn bị và cutover

11. **Trusted generation:** Key mới có sinh từ CSPRNG/DRBG/KMS/HSM tin cậy, khác material cũ?
12. **RNG/root issue:** Nếu nguồn sinh/master nghi lộ, đã sửa nguyên nhân trước khi tạo key mới?
13. **Key usage:** DEK/KEK/HMAC/signing/agreement keys có purpose riêng, không reuse sai?
14. **IAM/SoD:** Key owner, custodian, approver và workload có quyền đúng và audit riêng?
15. **Pre-activation:** Key v2 đã kiểm thử thuật toán, attributes, grants, backup/DR và negative tests?
16. **Reader-first:** Reader/verifier/partner đã hiểu key version mới trước khi writer/signing cutover?
17. **Single-write:** New data/signature chỉ dùng key v2 sau cutover?
18. **No fail-open:** KMS lỗi không tự fallback xuống key nghi lộ hoặc test key?
19. **Multi-region:** Có writer fencing, cache invalidation, region checks và monitoring old-key use?
20. **Metadata:** Ciphertext/signature/JWT có key ID/material version và AAD/trust references chính xác?

### C. Dữ liệu và trust lịch sử

21. **KEK:** Có phân biệt rotate/re-wrapping với thay DEK?
22. **DEK:** Nếu raw DEK có thể lộ, có đánh giá re-encrypt dữ liệu, không chỉ rewrap?
23. **GCM:** Nonce không lặp dưới cùng key, tag được verify, AAD ràng buộc ngữ cảnh?
24. **Concurrent writes:** Migration dùng CAS/ETag/transaction để không ghi đè dữ liệu mới?
25. **Large data:** Không công bố plaintext trước khi authenticated decrypt hoàn tất?
26. **Signing:** Đã chặn signing oracle và kiểm tra digest/artifact/token trái phép?
27. **PKI/JWKS:** Public trust, certificate revocation, verifier caches và token expiry đã xử lý?
28. **HMAC:** Các đối tác đã nhận key mới, có anti-replay và legacy window hợp lý?
29. **Agreement/TLS:** Static private key, ephemeral sessions và key schedule đã được đánh giá riêng?
30. **KDF master:** Đã tìm và thay descendants nếu root có nguy cơ lộ?
31. **Backup/DR:** Đã thử restore v1/v2, đối chiếu archives, replicas và legal hold?
32. **Old key:** Chỉ hủy khi có điều kiện dependency, retention, incident và approval đầy đủ?

### D. Kiểm chứng và đóng sự cố

33. **IAM negative tests:** Principal cũ không còn `Decrypt`, `Unwrap`, `Sign`, `CreateGrant` trái phép?
34. **Key negative tests:** Key v1 không tạo output mới; v2 chỉ dùng đúng purpose/scope?
35. **Data tests:** Round trip/AEAD tag/tenant AAD/corrupt ciphertext/canary migration đạt?
36. **Reconciliation:** App, KMS/HSM, DB, PKI, key inventory và backup cùng báo key version phù hợp?
37. **Audit completeness:** Decision và execution tách biệt, event có provider ref, không chứa raw secrets?
38. **Monitoring:** Alert old-key use, grant escalation, signing burst, unwrap anomaly và missing logs?
39. **Residual risk:** Đã ghi rủi ro old ciphertext/secret đã bị đối thủ sao chép không thể thu hồi?
40. **Postmortem:** Có root-cause remediation, owner, deadline và kiểm tra lại cryptoperiod/key granularity?
41. **Closure decision:** Đóng incident có bằng chứng; không tự resume key cũ chỉ vì cảnh báo hết?
42. **Khả năng diễn tập:** Đã thử runbook với test key, backup và các vùng trong môi trường phù hợp?

## 32. Tổng kết

**Rotation khi nghi ngờ compromise** không phải thao tác đổi tên hoặc bấm nút Rotate trên KMS. Đây là **quy trình ứng cứu rủi ro toàn vòng đời khóa**: xác định tài sản và nguyên nhân, **cô lập quyền bị nghi lạm dụng**, bảo toàn bằng chứng, tạo **material mới từ nguồn tin cậy**, chuyển new-use sang key mới, rồi xử lý **ciphertext, wrapped DEK, chữ ký, trust, partner secrets, backup và dữ liệu lịch sử** trước khi thu hồi hoặc hủy khóa cũ.

Cần phân biệt rõ **nghi ngờ lộ raw key** với **lạm dụng API có quyền**. HSM non-exportable giúp giảm đường xuất vật liệu, nhưng không chặn signing/decrypt oracle khi IAM hoặc business policy sai. Trong **envelope encryption**, **rotate KEK/rewrap** có thể giữ nguyên DEK và ciphertext; nếu **raw DEK đã lộ**, phải đánh giá **thay DEK và re-encrypt dữ liệu**. Với **signing key**, phải cập nhật public trust/JWKS/certificate và đánh giá output đã ký; với **HMAC**, cần phối hợp các bên chia sẻ secret; với **KDF master**, cần xử lý cả cây subkeys. Một key mới **không làm dữ liệu đã bị sao chép trước đó biến mất**.

An toàn thực sự được xác nhận bằng **IAM/KMS/HSM enforcement, versioned cutover, audit ba lớp, negative tests, backup/DR và điều kiện destruction**. **Không tiếp tục dùng key nghi lộ cho output mới vì tiện rollback, không hủy key cũ khi còn phụ thuộc chưa xử lý, và không đóng incident chỉ vì một dashboard thông báo “rotation completed”.**

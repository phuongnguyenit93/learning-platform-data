# Thu hồi sau khi phân phối sai – Xử lý khóa mật mã và quyền truy cập đã cấp nhầm

**Thu hồi sau khi phân phối sai** là quy trình **cô lập, vô hiệu hóa và thay thế khóa hoặc quyền sử dụng khóa** khi một hệ thống đã cấp phát **vật liệu khóa, wrapped key, public key/trust binding, credential hoặc quyền KMS/HSM** cho sai người nhận, sai tenant, sai hệ thống, sai môi trường hoặc sai mục đích. Mục tiêu không chỉ là chặn những thao tác tiếp theo mà còn **đánh giá tác động đã xảy ra, khôi phục trạng thái tin cậy, bảo toàn dữ liệu và tạo bằng chứng kiểm toán**.

Bài thuộc chương **Key distribution** của module **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, gắn với toàn bộ vòng đời **tạo → cấp phát → lưu trữ → sử dụng → xoay vòng → thu hồi → hủy khóa**. Nó kết nối mật mã đối xứng, bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, IAM, PKI, audit và khôi phục sau sự cố.

> **Nguyên tắc không thể bỏ qua:** **Có thể thu hồi quyền dùng khóa trong KMS, nhưng không thể buộc một người đã đọc được secret key phải “quên” những bytes đó.** Nếu **DEK, KEK, private key, HMAC key hay PSK rõ** đã rời ranh giới tin cậy, phải giả định bí mật có thể đã bị sao chép cho tới khi có bằng chứng để đánh giá khác. Đổi IAM hoặc xóa email/ticket **không làm khóa đã lộ trở lại bí mật**.

## 1. Phân phối sai là gì?

Một số tình huống:

1. **Sai người nhận:** hệ thống gửi DEK rõ cho service account không được phép.
2. **Sai tenant:** bản mã và wrapped DEK của tenant A được gửi cho tenant B, trong khi quyền KMS không cách ly đủ.
3. **Sai môi trường:** production key hoặc credential truy cập KMS production được đưa vào CI/staging.
4. **Sai khóa công khai:** Ledger Service được phát public key của attacker nhưng gắn nhãn “Payment Service”.
5. **Sai mục đích:** signing key có quyền Sign release được cấp cho workload vốn chỉ cần Verify.
6. **Sai phiên bản:** hệ thống phân phối lại key S1 đã retired/revoked sau khi đã công bố S2.
7. **Sai mức xuất khóa:** private key/KEK vốn phải non-exportable bị xuất thành file hoặc log.
8. **Sai phạm vi quyền:** một KMS grant/role cho phép `Decrypt`/`Sign` trên cả key family thay vì một key/tenant.
9. **Sai kênh:** khóa được gửi qua ticket, chat, URL, artifact hoặc tracing có người đọc ngoài phạm vi.
10. **Sai đường phục hồi:** một vùng DR nhận wrapped DEK nhưng không có KEK/context hợp lệ, dẫn đến dữ liệu không đọc được.

**Phân phối sai không đồng nghĩa chắc chắn đã lộ plaintext key.** Nếu chỉ có **public key** bị gửi nhầm thì thường là rủi ro **authenticity/trust mapping**, không phải lộ bí mật. Nếu chỉ có **wrapped DEK** được gửi sai, mức ảnh hưởng phụ thuộc **cơ chế wrap, quyền unwrap, context, dữ liệu kèm theo**. Quy trình phải phân loại trước khi quyết định rotation.

### 1.1. Phân biệt ba vấn đề

| Vấn đề | Ví dụ | Hướng điều tra chính |
| --- | --- | --- |
| **Rò rỉ vật liệu khóa (secret exposure)** | Raw DEK, KEK, HMAC key, private signing key, seed bị cấp cho người lạ. | Key rotation/re-encryption/revocation; dữ liệu và chữ ký bị ảnh hưởng. |
| **Cấp quyền dùng khóa sai (capability exposure)** | KMS IAM grant cho workload B có thể `Sign` hoặc `Decrypt` bằng non-exportable key A. | Thu hồi quyền/session, đối chiếu operation logs, đánh giá có lạm dụng hay không. |
| **Sai thông tin tin cậy/phân phối (trust misbinding)** | Công bố public key Sx của issuer khác dưới tên Payment S2. | Sửa trust registry, chống rollback, xác minh event/chữ ký đã được chấp nhận. |

Một sự cố có thể thuộc **nhiều nhóm**. Ví dụ credential bị cấp nhầm có thể bị dùng để **unwrap raw DEK**, biến sự cố IAM thành sự cố lộ key material.

## 2. Revocation nghĩa là gì – và không có nghĩa là gì?

“Thu hồi” có thể là những hành động rất khác nhau:

| Hành động | Có thể chặn điều gì? | Không tự khắc phục điều gì? |
| --- | --- | --- |
| **Thu hồi IAM grant/session/token** | Ngăn principal tiếp tục gọi API khi quyền đã thực sự hết hiệu lực. | Không xóa secret hoặc plaintext đã được lấy trước đó. |
| **Disable key object** | Chặn một số phép toán KMS/HSM trên key theo khả năng provider. | Không thu hồi bản sao raw key ở ngoài KMS; có thể làm gián đoạn ứng dụng hợp lệ. |
| **Rotate KEK** | Dùng KEK mới cho wrap mới và migration. | Không thay DEK hiện có; không bảo vệ DEK đã bị lộ. |
| **Re-wrap DEK** | Chuyển cùng DEK sang lớp bọc bằng KEK mới. | Không thay ciphertext/DEK; không chữa DEK compromise. |
| **Rotate DEK + re-encrypt** | Bảo vệ dữ liệu còn cần bí mật bằng một DEK mới. | Không xóa plaintext/ciphertext từng bị attacker đọc trước khi thay. |
| **Revoke signing key/trust** | Ngăn bên xác minh chấp nhận chữ ký theo chính sách mới. | Không xóa chữ ký đã phát hành; khó phân biệt chữ ký lịch sử nếu không có bằng chứng thời gian. |
| **Thu hồi certificate/identity** | Ngăn tiếp tục xác thực một danh tính ở các hệ kiểm tra revocation đúng. | Không lập tức cắt mọi session đang sống hoặc khắc phục client bỏ qua revocation. |
| **Xóa file/ticket/log chứa secret** | Giảm bản sao còn tiếp cận được trong hệ do tổ chức quản lý. | Không đảm bảo đã thu hồi các bản sao tải xuống/backup. |
| **Destroy key material** | Làm mất một đường sử dụng/khôi phục khóa theo cơ chế provider. | Có thể gây mất dữ liệu vĩnh viễn và không chứng minh tất cả bản sao đã biến mất. |

**Không nên chọn giải pháp có tác động không thể đảo ngược trước khi xác định dependency**. Ví dụ `ScheduleKeyDeletion` cho KEK v3 khi archive còn DEK được bọc dưới v3 có thể phá hủy khả năng khôi phục dữ liệu, trong khi bản sao raw key đã lộ **vẫn có thể tồn tại bên ngoài KMS**.

### 2.1. Phân biệt tính bí mật về sau với bảo mật quá khứ

Giả sử attacker biết DEK-D tại thời điểm T1. Hệ thống tạo DEK-E và re-encrypt lúc T2.

- Dữ liệu được mã hóa **sau T2 bằng DEK-E** có thể được bảo vệ trước attacker chỉ biết DEK-D, nếu các điều kiện khác đúng.
- Dữ liệu **trước T2** mã hóa bằng DEK-D **đã có thể bị đọc** nếu attacker lấy được ciphertext tương ứng.
- Thay DEK ở T2 **không thu hồi được thông tin attacker đã biết**, không thu hồi các bản copy đã xuất, không sửa được log chứa plaintext và không tự xoá backups cũ.

Vì thế cần tách **containment và phục hồi khả năng bảo mật tương lai** khỏi **đánh giá rủi ro dữ liệu quá khứ**. Không tuyên bố “không còn rò rỉ” chỉ vì hệ thống đã rotate.

## 3. Threat model sau một lần cấp phát sai

Điểm khởi đầu là **khả năng attacker nhận được gì và có thể làm gì**.

| Tài sản/đường lộ | Điều có thể bị lạm dụng | Nguồn bằng chứng cần kiểm |
| --- | --- | --- |
| **Plaintext DEK AES** | Decrypt các ciphertext bảo vệ bởi DEK đó. | Key inventory, bản ghi mã hóa, nơi DEK được cấp/log, access to ciphertext. |
| **Plaintext KEK** | Unwrap nhiều DEK nếu có wrapped blobs và scheme phù hợp. | KEK hierarchy, wrapped DEK catalog, backup và điểm lưu blob. |
| **Private signing key** | Tạo chữ ký hợp lệ về mật mã. | Sign audit, signed events/artifacts, trust registry, validity/revocation timeline. |
| **HMAC key / PSK** | Giả mạo message hoặc phiên dùng shared secret. | Các bên cùng biết secret, MAC verification logs, active sessions. |
| **Seed/recovery material** | Tái tạo key khác, mở đường recovery. | Key derivation graph, HSM backup/escrow, principal có quyền. |
| **KMS principal/grant/token** | Gọi Sign/Decrypt/Unwrap theo quyền còn hiệu lực. | IAM changes, provider audit, token expiry/session, key policy. |
| **Wrapped DEK** | Có thể hỗ trợ mở DEK nếu có KEK/rights; tăng số bản sao key ciphertext. | Wrap integrity/context, IAM, key refs, tenant mapping. |
| **Public key/trust entry sai** | Xác minh chữ ký của sai issuer; gửi secret cho sai người nhận. | Registry mutations, client caches, key pinning, trust path. |
| **TLS certificate/identity sai** | MITM/impersonation nếu client tin identity sai. | PKI issuance, mTLS connection logs, client trust, session state. |
| **Chỉ key ID/alias** | Thường là lộ metadata, không tự cấp quyền dùng key. | Naming/architecture sensitivity và chính sách exposure. |

**Không đánh đồng mọi loại compromise**. Một public key không phải secret cần rotate chỉ vì bị nhìn thấy; nhưng một public key bị **gắn sai danh tính** có thể làm cho hệ thống chấp nhận dữ liệu giả hoặc encrypt cho kẻ tấn công.

### 3.1. Ba câu hỏi về attacker

1. **Đã thấy những bytes nào?** Raw secret, wrapped blob, token, metadata, hay chỉ public key?
2. **Đã có khả năng sử dụng điều gì?** KMS Sign/Decrypt, truy cập ciphertext, sửa registry, thêm principal hoặc thay trust?
3. **Còn giữ được gì sau khi quyền bị thu hồi?** Bản copy plaintext, raw key, chữ ký đã tạo, phiên đang mở, dữ liệu trong cache/backup?

Câu trả lời quyết định cần **revoke permission**, **rotate secret**, **re-encrypt data**, **reissue certificate**, **invalidate session**, **correct trust** hay nhiều thao tác cùng lúc.

## 4. Sự cố cần được quản trị bằng người có thẩm quyền

**Không để người phát hiện tự quyết định hủy khóa trong panic.** Một sự cố phân phối sai phải có incident ownership và giới hạn quyền.

| Vai trò | Trách nhiệm |
| --- | --- |
| **Incident commander** | Xác định mức độ, phạm vi, thứ tự ưu tiên, điều phối kênh liên lạc và quyết định dừng dịch vụ khi cần. |
| **Security/cryptography owner** | Phân loại compromise, đề xuất chặn key usage, chính sách revoke/rotate/re-encrypt và phê duyệt ngoại lệ. |
| **KMS/HSM operator** | Thực hiện IAM/key state changes, key generation, secure rewrap/backup theo quyền được phê duyệt. |
| **IAM/identity team** | Thu hồi credential/grant/session, kiểm tra role propagation, certificate trust và cấp danh tính mới. |
| **Application owner/developer** | Xác minh tenant/object binding, luồng dữ liệu, đổi cấu hình key reference, triển khai migration và negative tests. |
| **Data owner** | Xác định loại dữ liệu, retention, thông báo bên liên quan và đánh giá tác động nghiệp vụ. |
| **SRE/DR team** | Duy trì dịch vụ, rollout/canary, backup/restore và RPO/RTO. |
| **Auditor/SOC** | Bảo vệ bằng chứng, đối chiếu log độc lập, phát hiện lạm dụng và hậu kiểm. |

Với key nguy hiểm như root KEK, release signing key hoặc HSM recovery, có thể yêu cầu **dual control/quorum**. Phê duyệt khẩn cấp phải có **đường break-glass đã được chuẩn bị**, không được tự tạo một quyền root vô hạn vì hệ thống đang gặp sự cố.

## 5. Quy trình phản ứng tổng quát

~~~mermaid
flowchart TD
    DETECT["Phát hiện phân phối sai"] --> TRIAGE["Xác minh loại key/quyền, đối tượng nhận và phạm vi"]
    TRIAGE --> STOP["Chặn cấp phát mới, cô lập recipient/path bị lỗi"]
    STOP --> EVIDENCE["Bảo toàn audit + inventory + timeline"]
    EVIDENCE --> DECIDE{"Raw secret đã/ có thể lộ?"}
    DECIDE -->|Có| MATERIAL["Lập kế hoạch rotate/revoke material và dữ liệu/chữ ký"]
    DECIDE -->|Chưa có bằng chứng| RIGHTS["Thu hồi capability/credential và điều tra thao tác đã gọi"]
    MATERIAL --> SWITCH["Cấp khóa mới và chuyển luồng ứng dụng an toàn"]
    RIGHTS --> SWITCH
    SWITCH --> RECON["Đối soát ciphertext, trust, consumers và backups"]
    RECON --> VERIFY["Kiểm tra phân quyền, cryptography và restore"]
    VERIFY --> CLOSE["Thu hồi quyền tạm, hậu kiểm và sửa gốc rễ"]
~~~

Sơ đồ chỉ là **khung điều phối**. Khi một secret thật bị lộ, phải đánh giá compromise rộng hơn. Khi một KMS principal bị cấp nhầm, việc điều tra **các lượt Sign/Decrypt/Unwrap đã thực hiện** là chìa khóa xác định liệu vật liệu khóa hoặc plaintext đã thực sự rời ranh giới tin cậy.

### 5.1. Bước 1 – Ngừng tạo thêm lỗi

Các hành động containment có thể gồm:

- Tắt endpoint/job đang cấp phát key sai tenant.
- Đổi registry/config để không phát hành key/recipient mapping sai cho request mới.
- Thu hồi IAM grant, workload credential, session hoặc token có khả năng lạm dụng.
- Khoanh vùng access tới log, CI artifact, bucket hoặc queue chứa secret.
- Tạm dừng Sign/Unwrap/GenerateDataKey trên đúng key/principal liên quan khi policy cho phép.
- Vô hiệu hóa public key hoặc certificate sai khỏi danh sách tin cậy của các consumer.

**Không tự vô hiệu hóa mọi KEK** nếu hệ thống cần giải mã dữ liệu sống còn mà chưa có đường phục hồi. Phải cân nhắc nguy cơ tiếp tục lộ dữ liệu so với tính sẵn sàng và cách thức khôi phục đã được phê duyệt.

### 5.2. Bước 2 – Bảo toàn bằng chứng mà không phát tán secret

Thu thập theo quyền:

- Incident ID, thời gian bắt đầu/kết thúc có thể xảy ra, deployment/config change liên quan.
- Issuer, recipient, tenant, application/workload identity và môi trường.
- Key IDs/material versions, algorithm, key usage, lifecycle state.
- Quyền KMS và các thay đổi IAM/PKI/trust registry.
- Event IDs, request/correlation IDs và outcome của thao tác Sign/Decrypt/Unwrap.
- Các bản sao/đường phát tán: message queue, log collector, CI/CD, tickets, cache, backup, recipients.

**Không dán raw DEK/KEK/private key vào incident ticket để “làm bằng chứng”.** Lưu **định danh đã được phép, sự kiện KMS và chứng cứ được bảo vệ**, không tái phân phối chính secret vừa lộ.

### 5.3. Bước 3 – Xác định khóa/phạm vi bị ảnh hưởng

Một key inventory hữu ích phải trả lời:

~~~text
KEY MATERIAL / KEY ID / VERSION
  |-- HAS_OWNER --> team / policy
  |-- ALLOWED_FOR --> purpose / operation / tenant
  |-- WRAPS --> DEK -> ENCRYPTS --> object / dataset / backup
  |-- SIGNS --> events / artifacts -> VERIFIED_BY --> consumers
  |-- ACCESSED_BY --> principals / grants / sessions
  |-- REPLICATED_TO --> regions / archives / recovery locations
  |-- PREDECESSOR/SUCCESSOR --> old/new key version
~~~

Đây là **đồ thị phụ thuộc**, không phải chỉ một bảng liệt kê tên khóa. Nếu chỉ biết “KEK X bị lộ” nhưng không biết **DEK nào được wrap**, rất khó ước tính tác động hoặc đưa ra kế hoạch thay khóa có thể kiểm chứng.

### 5.4. Bước 4 – Khôi phục bằng successor và cập nhật consumer

Sau containment:

1. Sinh key material mới bằng **CSPRNG/KMS/HSM được phê duyệt**.
2. Ghi owner, purpose, algorithm, key version/successor và trạng thái.
3. Cấp phép **đúng principal, operation và key family** cho luồng phục hồi.
4. Chuyển **new writes/new Sign** sang khóa mới theo thứ tự bảo đảm consumer sẵn sàng.
5. Migrate DEK/ciphertext/trust registry theo **loại compromise**, không áp cùng một thao tác cho mọi key.
6. Xác minh IAM/KMS/provider audit, application authorization, crypto tag/signature và backup restore.
7. Thu hồi đặc quyền tạm và đối soát các đường phát tán còn tồn tại.

**Rollback application không phải rollback key security**. Nếu key cũ đã compromise, không được tự bật lại quyền dùng nó chỉ vì deployment mới gây lỗi. Cần có đường sửa ứng dụng **không tái kích hoạt key bị lộ**.

## 6. Ma trận phản ứng theo loại phân phối sai

| Loại phân phối sai | Cô lập trước tiên | Thay/khôi phục | Lưu ý đặc biệt |
| --- | --- | --- | --- |
| **DEK rõ đến sai recipient** | Chặn luồng cấp DEK và khả năng đọc ciphertext. | Tạo DEK mới, đánh giá re-encrypt dữ liệu liên quan. | Re-wrap cùng DEK không giải quyết compromise. |
| **KEK rõ bị lộ** | Hạn chế wrap/unwrap và các bản sao liên quan. | KEK successor, đánh giá DEK đã bị unwrap; rewrap và **re-encrypt nếu DEK có nguy cơ lộ**. | KEK cũ có thể bảo vệ nhiều DEK/backups. |
| **Private signing key rõ bị lộ** | Chặn Sign, ngừng tin key cũ theo chính sách. | Tạo S2, cập nhật trusted public key, điều tra chữ ký lịch sử. | Không thể “thu hồi toán học” chữ ký đã phát hành. |
| **HMAC key/PSK đến sai bên** | Chặn bên sai, vô hiệu hóa phiên/token liên quan. | Rotate shared secret cho tất cả bên hợp lệ. | Cửa sổ chấp nhận secret cũ cần giới hạn và review. |
| **KMS credential/grant bị cấp nhầm** | Revoke role/grant/token/session và principal nếu cần. | Tái cấp danh tính/quyền tối thiểu, điều tra API usage. | Key material có thể vẫn an toàn **nếu không bị export/unwrap**. |
| **Wrapped DEK gửi nhầm** | Thu hồi truy cập object và quyền KMS liên quan. | Kiểm context, wrap integrity, key permissions; rewrap/rotate khi rủi ro yêu cầu. | Không tự coi blob bằng plaintext DEK. |
| **Public key sai issuer/trust binding** | Ngừng chấp nhận mapping sai, chặn cập nhật mới. | Khôi phục trust anchor/registry, publish key đúng và anti-rollback. | Kiểm lại event/token/chữ ký đã được chấp nhận. |
| **TLS certificate/key trust sai** | Chặn identity/session và đường kết nối có nguy cơ. | Reissue/revoke certificate, sửa trust store/identity binding. | Kiểm tra client bỏ qua hostname/revocation. |
| **Key version đã revoked được phát lại** | Cô lập source/feed/cache và ngừng trust key cũ. | Trạng thái version monotonic, revocation propagation. | Signed manifest cũ vẫn có thể Verify toán học thành công. |
| **Chỉ lộ key ID/alias** | Xem mức độ metadata leakage. | Có thể không cần thay material; sửa quyền/naming nếu cần. | Biết key ID không tự cấp quyền sử dụng khóa. |

**Một loại phân phối sai có thể cần nhiều hàng trong bảng**. Ví dụ gửi nhầm raw DEK kèm ciphertext cho tenant khác vừa là **data breach** vừa là **key material compromise**.

## 7. Trường hợp DEK bị phân phối sai

Trong **envelope encryption**, DEK mã hóa dữ liệu; KEK ở KMS/HSM bảo vệ DEK dưới dạng **wrapped DEK**. Nếu một DEK rõ đã được cấp cho sai recipient, **thu hồi KMS grant không xóa được DEK khỏi bộ nhớ/bản copy của recipient**.

### 7.1. Hậu quả với AES-GCM

Nếu DEK-A được dùng cùng nonce/AAD đúng để mã hóa invoice A1, A2... và attacker có cả DEK-A lẫn ciphertext, họ có thể giải mã các dữ liệu liên quan theo khả năng tiếp cận.

Không phải mọi record trong hệ đều bị ảnh hưởng: phạm vi phụ thuộc **DEK scope**, cách chia tenant/partition, số lần reuse DEK, key derivation và nơi ciphertext tồn tại.

**Không tái sử dụng DEK bị lộ cho encryption mới.** Nếu có data-key caching, cần invalidate cache liên quan; đồng thời kiểm tra mọi instance có bản sao DEK trong RAM.

### 7.2. Re-wrap không phải rotate DEK

~~~text
Trước khi sự cố:
  Ciphertext = AES-GCM-Encrypt(DEK-A, invoice)
  W3 = Wrap(KEK-v3, DEK-A)

Sau khi chỉ re-wrap:
  Ciphertext KHÔNG ĐỔI
  W4 = Wrap(KEK-v4, DEK-A)
  DEK-A vẫn là DEK-A và có thể đã nằm trong tay attacker

Nếu cần đổi DEK:
  DEK-B = GenerateFreshDataKey()
  Ciphertext-B = AES-GCM-Encrypt(DEK-B, invoice, nonce mới, AAD đúng)
  W4-B = Wrap(KEK-v4, DEK-B)
~~~

**Không bao giờ chỉ sửa metadata `dekVersion` rồi tuyên bố dữ liệu đã đổi khóa.** Rotation của DEK có nghĩa **vật liệu DEK thực sự khác**; dữ liệu cũ phải được mã hóa lại hoặc giải pháp đặc thù được đánh giá.

### 7.3. Quy trình thay DEK an toàn

1. Xác định đúng tập ciphertext theo **DEK ID/version và inventory**.
2. Sinh **DEK mới** trong KMS hoặc nguồn sinh khóa tin cậy theo chính sách.
3. Chặn ghi mới bằng DEK cũ; hỗ trợ **đọc phiên bản cũ** có kiểm soát khi migration chưa xong.
4. Đọc dữ liệu cũ trong môi trường có quyền, xác minh **AEAD tag và authorization**.
5. Encrypt bằng DEK mới với **nonce duy nhất theo key**, AAD đúng ngữ cảnh và schema version phù hợp.
6. Lưu atomically **ciphertext/tag, nonce, wrapped DEK mới, key references/versions, revision**.
7. Dùng CAS/idempotency để tránh hai workers ghi đè dữ liệu hoặc lệch ciphertext với DEK.
8. Kiểm tra read path, backup/restore, rồi mới cân nhắc retire/destruction của DEK cũ.
9. Đánh giá bản copy ciphertext/DEK còn trong snapshots hoặc log.

**Lưu ý:** Nếu AAD của dữ liệu chứa KEK reference hoặc wrapping metadata có thể thay đổi, một migration “chỉ đổi wrapped DEK” có thể làm **GCM tag verification thất bại**. Cần thiết kế AAD ổn định hoặc thực hiện re-encrypt theo schema có kiểm soát.

## 8. Trường hợp KEK bị phân phối sai

**KEK** có thể bọc **nhiều DEK**. Nếu raw KEK v3 bị lộ, blast radius phụ thuộc wrapped DEK và ciphertext mà bên nhận trái phép tiếp cận.

~~~mermaid
flowchart LR
    KEK["KEK v3 bị lộ"] --> W1["Wrapped DEK-A"]
    KEK --> W2["Wrapped DEK-B"]
    KEK --> W3["Wrapped DEK-C / backups"]
    W1 --> DEKA["DEK-A"] --> DATAA["Invoices tenant A"]
    W2 --> DEKB["DEK-B"] --> DATAB["Invoices tenant B"]
    W3 --> DEKC["DEK-C"] --> DATAC["Archives"]
~~~

**Phân biệt:**

- Nếu chỉ **IAM grant** dùng KEK bị lộ và đã revoke, phải xem audit `Decrypt/Unwrap` đã xảy ra; key bytes có thể vẫn ở trong KMS.
- Nếu **raw KEK** đã rời KMS, giả định attacker có thể unwrap các DEK mà họ có wrapped blobs tương ứng, bất kể IAM sau đó.
- Nếu KEK là **non-exportable**, việc lộ IAM credential không tự chứng minh raw KEK đã lộ; nhưng **lạm dụng API Unwrap** vẫn có thể làm lộ DEK.
- Nếu dùng một **KEK chung cho nhiều tenant**, phạm vi ảnh hưởng tiềm năng rộng hơn so với KEK tách tenant, nhưng cần xác minh thực tế.

### 8.1. Chuyển KEK và đối soát DEK

Một kế hoạch có thể gồm:

1. Cô lập quyền sử dụng KEK v3, áp quyết định bảo mật về việc tạm disable hay giới hạn API.
2. Tạo KEK v4 trong KMS/HSM, gắn successor/predecessor ở registry.
3. Chuyển **new wraps/new writes** sang v4.
4. **Re-wrap DEK chưa compromise** theo API KMS/HSM được phép, hạn chế raw DEK đi qua worker.
5. Với DEK **đã/được đánh giá có thể bị lộ**, tạo DEK mới và **re-encrypt dữ liệu**, không chỉ re-wrap.
6. Đối soát live DB, archive, snapshots, cache và recovery regions.
7. Kiểm tra RPO/RTO và data restore; **không destroy KEK v3 khi vẫn cần nó để đọc dữ liệu** hoặc còn legal hold chưa giải quyết.
8. Thu hồi grants tạm, ghi audit và thông báo kết quả theo phạm vi.

**Re-wrap không làm mất quyền của attacker đã lấy raw KEK cũ và wrapped DEK cũ**. Nếu các bản sao này đã rời ranh giới tin cậy, phải coi dữ liệu liên quan có nguy cơ đã bị mở, dù blob mới đang được bảo vệ dưới v4.

### 8.2. Tại sao không hủy KEK ngay?

KMS `DisableKey` và `ScheduleKeyDeletion` có thể ngăn giải mã dữ liệu hợp lệ trước khi migration hoàn tất. Một **backup cũ** có thể còn wrapped DEK v3; hủy KEK v3 khiến snapshot không còn khả năng restore, trong khi **bản sao KEK bị lộ ở ngoài KMS không nhất thiết bị hủy**.

Trong tình huống compromise nghiêm trọng, containment nhanh có thể cần chấp nhận gián đoạn. Nhưng quyết định phải xuất phát từ **incident commander/security/data owner** với đánh giá **khả năng khôi phục**, không phải logic “key exposed → delete ngay”.

## 9. Trường hợp private signing key bị phân phối sai

Private signing key Ed25519/ECDSA/RSA-PSS có thể được sử dụng để tạo **chữ ký hợp lệ về mặt toán học**. Nếu attacker lấy được private key, họ có thể giả mạo các sự kiện hoặc artifact trong phạm vi trust.

### 9.1. Phải xử lý cả signer và verifier

~~~mermaid
sequenceDiagram
    participant SOC as Security/Incident
    participant KMS as KMS/HSM
    participant Signer as Payment Service
    participant Registry as Trusted key registry/PKI
    participant Verifier as Ledger Service
    SOC->>KMS: Chặn Sign S1 / revoke principal theo policy
    SOC->>KMS: Tạo signing key S2 mới
    KMS-->>Registry: Public key/certificate S2 qua quy trình đã duyệt
    Registry-->>Verifier: Signed/trusted key metadata S2
    Verifier->>Verifier: Verify trust, issuer, purpose, version, revoke S1
    SOC->>Signer: Chuyển Sign mới sang S2
    Signer->>Verifier: Event ký bằng S2
    Verifier->>Verifier: Verify signature + authorization + chống replay
~~~

**Sự cố không được khắc phục chỉ ở phía signer**. Nếu Ledger vẫn tin S1 như một key hợp lệ cho chữ ký mới, kẻ tấn công có thể tiếp tục gửi các event ký bằng S1.

### 9.2. Chữ ký lịch sử phải được xử lý theo thời gian

Một chữ ký trên artifact/event **không đổi bytes sau khi key bị revoke**. Một hệ thống Verify có thể vẫn cho kết quả toán học hợp lệ đối với chữ ký S1, nhưng **độ tin cậy nghiệp vụ** cần được đánh giá theo:

- Khi nào private key có thể đã bị lộ?
- Có bằng chứng thời gian đáng tin từ bên độc lập hoặc audit append-only không?
- Hệ thống chấp nhận chữ ký S1 cho **lịch sử** hay vẫn cho **giao dịch mới**?
- Key usage, issuer, audience, tenant và event ID có đúng không?
- Có **replay/idempotency** đã được thực thi không?
- Chữ ký trên release artifact có gắn đúng digest/provenance và phê duyệt phát hành không?

**Không mặc định mọi chữ ký lịch sử đều sai**, cũng không mặc định chúng đáng tin chỉ vì `Verify` trả true. Quyết định cần dựa trên **revocation policy, timeline và bằng chứng**.

### 9.3. Public key bị phân phối nhầm khác private key bị lộ

Nếu chỉ **public key sai** được đưa vào trust store, không nhất thiết có private key hợp pháp bị lộ. Vấn đề là verifier có thể **tin nhầm signer**. Giải pháp là sửa/thu hồi trust binding, ngăn rollback và kiểm tra các event có thể đã được chấp nhận bằng key giả.

Nếu **private key thật** bị lộ, cần rotate signing key, chặn Sign cũ và cập nhật trust. Hai sự cố có thể xảy ra đồng thời nhưng không được đánh đồng khi báo cáo.

## 10. Trường hợp PSK, HMAC key và session key bị cấp nhầm

### 10.1. HMAC/PSK – Bí mật dùng chung

Một secret dùng chung giữa A và B có thể cho phép cả hai tạo MAC hoặc xác thực phiên. Nếu cấp nhầm cho C:

- **C có thể giả mạo A hoặc B** trong phạm vi mô hình xác thực, không chỉ đọc dữ liệu.
- Cần **cấp secret mới** cho đúng các bên, dừng dùng shared secret cũ.
- Cần quản lý **dual-key acceptance window** khi rollout; không để secret cũ được chấp nhận vô hạn.
- Phải đánh giá message/token đã được xác thực bằng secret cũ và chống replay.
- Không gửi secret mới qua cùng **đường phân phối chưa được sửa**.

**Không dùng hash thuần như một MAC**; dùng HMAC/KMAC đúng API và key usage. Không tái sử dụng một secret HMAC cho AES, password pepper hoặc nhiều trust domains tùy tiện.

### 10.2. TLS/mTLS và khóa phiên

Nếu một **session secret** bị lộ, cần xác định **phiên nào, thời gian và kênh nào** bị ảnh hưởng. Có thể cần chấm dứt session/connection, vô hiệu hóa resumption tickets hoặc credential liên quan theo giao thức và triển khai.

- **TLS 1.3** dùng key schedule tạo traffic secrets từ handshake; hai bên không nên truyền raw traffic key như một message độc lập.
- **mTLS** xác thực danh tính hai phía ở lớp vận chuyển nhưng không tự quyết định quyền trên từng tenant/object.
- **Forward secrecy** có thể giới hạn hậu quả khi long-term identity key bị lộ về sau, nhưng **không bảo vệ một session key đã trực tiếp bị lộ**.
- Khi chứng chỉ/private identity key bị phân phối sai, phải xem **PKI revocation, session lifetime, credential và trust propagation**.

**Không cố tự khôi phục bảo mật bằng giao thức “X25519 + checksum” tự chế**. Sử dụng TLS/mTLS hoặc authenticated key agreement đã được đánh giá, bảo vệ peer identities và transcript binding.

## 11. KMS/HSM: thu hồi quyền và ngăn tiếp tục dùng key

Khi sự cố là **cấp nhầm quyền**, không phải raw key export, cần tập trung vào thực thi policy và điều tra **quyền đã được dùng**.

### 11.1. Quyền nào cần rà soát?

| Quyền hoặc hành động | Vì sao nguy hiểm nếu cấp sai? |
| --- | --- |
| **GenerateDataKey / Encrypt** | Tạo DEK/wrapped DEK dưới key hoặc tenant không được phép. |
| **Decrypt / Unwrap** | Có thể đưa DEK hoặc plaintext tới workload không được phép. |
| **Sign** | Có thể tạo chữ ký hợp lệ dưới danh tính tin cậy. |
| **Verify/GetPublicKey** | Thường ít nhạy cảm hơn, nhưng trust/key metadata vẫn cần kiểm soát. |
| **CreateGrant/ChangeKeyPolicy** | Có thể tạo đường leo thang quyền hoặc duy trì quyền trái phép. |
| **ExportKey / ExportPrivateKey** | Có thể đưa raw key ra khỏi KMS/HSM nếu provider hỗ trợ. |
| **Disable/Enable/Delete/ScheduleDeletion** | Có thể gây gián đoạn hoặc làm mất dữ liệu. |
| **Import/BYOK/Restore** | Có thể thay provenance hoặc phục hồi key/trust trạng thái không còn hợp lệ. |

Tên API thực tế **phụ thuộc provider**. Không mặc định mọi KMS hỗ trợ `ExportKey` hoặc có API giống nhau.

### 11.2. Thu hồi quyền phải có bằng chứng hiệu lực

Các bước thông thường:

1. Revoke grants và chỉnh IAM/key policy theo nguồn quyền thực sự.
2. Revoke/rotate workload credentials hoặc token đã cấp nhầm.
3. Xử lý **session/cache** còn hiệu lực theo khả năng nền tảng; không tin việc đóng ticket đã cắt phiên.
4. Ghi audit của các thay đổi quyền và lấy **provider request IDs** để đối chiếu.
5. Thử **negative authorization** từ principal sai trên resource/key đúng mục tiêu.
6. Kiểm tra **grant propagation và eventual consistency** nếu provider có độ trễ áp chính sách.
7. Xem lại quyền tạo grant/chỉnh IAM để tránh principal tự cấp lại cho mình.

**Một lời gọi `RevokeGrant` thành công không tự chứng minh mọi session đã chấm dứt tức thì**. Phải xác minh hành vi từ phía principal thực, phù hợp cơ chế provider và thời điểm hiệu lực.

### 11.3. Tránh “break-glass admin” vô hạn

Trong sự cố khẩn cấp có thể cần một đường quyền đặc biệt. Nhưng break-glass phải có:

- Incident ID và mục đích cụ thể.
- Requester/approver độc lập hoặc quorum theo chính sách.
- Danh tính và authentication được bảo vệ.
- **Key IDs, operations, tenants, môi trường và TTL** được giới hạn theo khả năng.
- Giám sát thời gian gần thực và audit không nằm dưới cùng quyền xóa của operator.
- Thu hồi session/grant và hậu kiểm sau khi hoàn tất.

**Không dùng tình huống “thu hồi sau cấp sai” làm lý do mở toàn bộ `kms:*` để sửa nhanh**; điều đó chỉ tạo một đợt phân phối quyền sai khác.

## 12. Sai trust mapping: public key, certificate, JWKS và anti-rollback

Một cơ chế phân phối có xác thực phải gắn public key với **issuer, recipient/audience, algorithm, key usage, tenant và version**.

### 12.1. Ví dụ key substitution

Ledger tải JWKS từ URL do token cung cấp và thấy `kid=S1`. Attacker tạo cặp key riêng, ký event rồi đưa `jku` trỏ tới JWKS do họ quản lý. Nếu Ledger tin URL đó mà không có issuer policy, **chữ ký hợp lệ về mật mã nhưng không hợp lệ về danh tính**.

Khi phát hiện:

1. Dừng nhận key sources ngoài allowlist/trust policy.
2. Thu hồi entry sai trong registry và đẩy **trusted mapping mới**.
3. Vô hiệu hóa hoặc làm mới verifier caches theo policy.
4. Chặn rollback để key mapping cũ không được phát lại.
5. Rà soát event/token đã được Verify bằng entry sai.
6. Khôi phục audit, kiểm tra issuer, audience, tenant và event ID.

### 12.2. Có cần signed manifest hay không?

Một **signed public-key manifest** có thể giúp phát hiện tráo key nếu verifier **đã có trust anchor độc lập** để xác minh chữ ký trên manifest. Nhưng signed manifest không chữa được:

- **Issuer/distributor signing key** đã bị lộ.
- Trust anchor được cài từ một nguồn sai.
- Signed manifest cũ được phát lại sau revocation.
- Quyền nghiệp vụ của issuer không được kiểm tra.

Do đó verifier phải kiểm **current revocation state, version monotonic, key usage và thời hạn** ngoài chữ ký. Với PKI/TLS, cần xác minh certificate chain, identity/hostname và policy, không dùng trust-all để bypass.

### 12.3. Trạng thái tin cậy phải được cập nhật atomically

Một bản ghi trust có thể gồm:

~~~yaml
issuerRef: "payment-service"
keyFamily: "payment-event-signing"
activeVersion: 4
acceptedKeyRefs:
  - "payment-signing-s4"
revokedKeyRefs:
  - "payment-signing-s3"
policyVersion: "payment-trust-v9"
revision: 108
~~~

Đây là **mẫu metadata**, không phải bí mật khóa. Nếu chỉ cập nhật `activeVersion` mà vẫn giữ key revoked trong allowlist không có điều kiện, verifier có thể tiếp tục tin key cũ. Khi có nhiều consumer, cần **publish/cutover/acknowledgment và cơ chế anti-rollback** theo mô hình triển khai.

## 13. Ứng dụng multi-tenant và phân phối nhầm wrapped DEK

Giả sử `invoice-123` của tenant A được mã hóa bằng DEK-A, DEK-A được wrap dưới KEK-Billing. Do lỗi phân quyền, API trả cho tenant B:

~~~text
ciphertext(invoice-123)
nonce / tag
wrapped(DEK-A)
keyRef / metadata
~~~

**Không nhất thiết tenant B đã lấy được DEK-A rõ.** Nhưng nếu workload của B được cấp `DecryptDataKey` trên KEK chung, hoặc KMS context/ứng dụng không ràng buộc tenant chính xác, có thể xảy ra đọc dữ liệu chéo tenant.

### 13.1. Những lớp phải kiểm tra

| Lớp | Câu hỏi |
| --- | --- |
| **Application authorization** | Caller có quyền với invoice và tenant từ danh tính đã xác thực không? |
| **Database isolation** | Query có lọc tenant/owner đúng và ngăn IDOR không? |
| **KMS IAM/key policy** | Workload nào có thể unwrap bằng KEK? Điều kiện context có được thực thi đúng? |
| **Encryption context** | Tenant, object, purpose có được ràng buộc nếu provider hỗ trợ? |
| **AES-GCM AAD** | Ciphertext có được xác thực với metadata ổn định không? |
| **Key material custody** | DEK rõ có xuất sang tenant B hoặc log/tracing không? |
| **Audit** | Có thể đối chiếu request app với KMS Decrypt/Unwrap không? |

**Lỗi KMS permissions và lỗi application authorization có thể cùng tồn tại.** Sửa policy KMS mà không sửa IDOR sẽ để lại đường lộ ciphertext/metadata; sửa IDOR nhưng không thu hồi principal có quyền KMS sai vẫn để lại rủi ro độc lập.

### 13.2. Không tự re-encrypt tất cả khi chưa phân loại

Nếu chỉ **wrapped DEK và ciphertext** bị gửi nhầm nhưng principal sai không thể unwrap và **không có bằng chứng raw DEK bị lộ**, hành động đáp ứng có thể tập trung vào **thu hồi quyền truy cập, kiểm tra integrity/context, audit, rate limit và đánh giá dữ liệu lộ**. Data owner/security sẽ quyết định có cần rotation thêm theo rủi ro.

Nếu có bằng chứng principal đã **Unwrap được DEK rõ** hoặc truy xuất plaintext, cần mở rộng scope như **DEK compromise** ở mục trước. Không dùng một câu trả lời đơn giản cho mọi incident.

## 14. Ví dụ Java 17: policy planner cho sự cố phân phối sai

Một luồng phản ứng phải bắt đầu bằng **metadata đáng tin**, không phải nhận bytes khóa để đưa vào log. Đoạn Java 17 sau minh họa một **policy planner** tạo các yêu cầu hành động theo **loại tài sản bị phân phối sai**.

Mục tiêu kỹ thuật:

- Phân biệt **raw DEK, raw KEK, private signing key, shared MAC/PSK, wrapped DEK, public key mapping, KMS credential**.
- Tránh nhầm **thu hồi IAM** với **thu hồi vật liệu đã lộ**.
- Không tự thực thi `DeleteKey`/`DisableKey` từ một quy tắc đơn giản.
- Yêu cầu **approval và inventory scope** trước các thao tác không thể đảo ngược.
- Chỉ xuất **plan metadata và reason codes**, không xử lý DEK/KEK thật.

> **Giới hạn:** Đây là ví dụ **đào tạo logic phân loại sự cố**, không phải incident response engine production, **không kết nối KMS/IAM thật**, không xác minh identity/approval và không tự giải quyết pháp lý/tuân thủ. Quyết định thực tế phải được Security, key owner, data owner và đội vận hành phê duyệt theo threat model.

~~~java
import java.util.EnumSet;
import java.util.Objects;
import java.util.Set;

public final class WrongKeyDistributionResponseDemo {
    enum ExposureKind {
        RAW_DEK,
        RAW_KEK,
        PRIVATE_SIGNING_KEY,
        HMAC_OR_PSK,
        KMS_CREDENTIAL,
        WRAPPED_DEK_ONLY,
        WRONG_PUBLIC_KEY_TRUST
    }

    enum Action {
        STOP_DISTRIBUTION,
        PRESERVE_EVIDENCE,
        REVOKE_ACCESS,
        INVESTIGATE_KMS_USAGE,
        ROTATE_KEY_MATERIAL,
        ASSESS_DEK_REENCRYPTION,
        ASSESS_WRAPPED_DEK_DEPENDENCIES,
        REISSUE_SIGNING_IDENTITY,
        REBUILD_TRUST_REGISTRY,
        INVALIDATE_SESSIONS_AND_CACHES,
        VERIFY_BACKUP_AND_RESTORE,
        INDEPENDENT_APPROVAL_REQUIRED
    }

    // Chỉ chứa reference đã được phê duyệt; tuyệt đối KHÔNG chứa
    // key bytes, token, ciphertext, private key hoặc raw KMS response.
    record Incident(
            String incidentRef,
            String keyRef,
            String tenantRef,
            ExposureKind kind,
            boolean confirmedPlaintextExposure) {}

    record ResponsePlan(
            String incidentRef,
            String keyRef,
            Set<Action> requiredAssessments) {}

    static ResponsePlan plan(Incident incident) {
        Objects.requireNonNull(incident);
        if (incident.incidentRef() == null
                || incident.incidentRef().isBlank()
                || incident.keyRef() == null
                || incident.keyRef().isBlank()
                || incident.tenantRef() == null
                || incident.tenantRef().isBlank()
                || incident.kind() == null) {
            throw new IllegalArgumentException("Invalid incident metadata");
        }

        EnumSet<Action> steps = EnumSet.of(
                Action.STOP_DISTRIBUTION,
                Action.PRESERVE_EVIDENCE,
                Action.REVOKE_ACCESS,
                Action.INDEPENDENT_APPROVAL_REQUIRED);

        switch (incident.kind()) {
            case RAW_DEK -> {
                steps.add(Action.ROTATE_KEY_MATERIAL);
                steps.add(Action.ASSESS_DEK_REENCRYPTION);
                steps.add(Action.ASSESS_WRAPPED_DEK_DEPENDENCIES);
                steps.add(Action.VERIFY_BACKUP_AND_RESTORE);
            }
            case RAW_KEK -> {
                steps.add(Action.ROTATE_KEY_MATERIAL);
                steps.add(Action.ASSESS_WRAPPED_DEK_DEPENDENCIES);
                steps.add(Action.ASSESS_DEK_REENCRYPTION);
                steps.add(Action.INVESTIGATE_KMS_USAGE);
                steps.add(Action.VERIFY_BACKUP_AND_RESTORE);
            }
            case PRIVATE_SIGNING_KEY -> {
                steps.add(Action.ROTATE_KEY_MATERIAL);
                steps.add(Action.REISSUE_SIGNING_IDENTITY);
                steps.add(Action.REBUILD_TRUST_REGISTRY);
                steps.add(Action.INVESTIGATE_KMS_USAGE);
            }
            case HMAC_OR_PSK -> {
                steps.add(Action.ROTATE_KEY_MATERIAL);
                steps.add(Action.INVALIDATE_SESSIONS_AND_CACHES);
            }
            case KMS_CREDENTIAL -> {
                steps.add(Action.INVESTIGATE_KMS_USAGE);
                steps.add(Action.INVALIDATE_SESSIONS_AND_CACHES);
            }
            case WRAPPED_DEK_ONLY -> {
                steps.add(Action.ASSESS_WRAPPED_DEK_DEPENDENCIES);
                steps.add(Action.INVESTIGATE_KMS_USAGE);
            }
            case WRONG_PUBLIC_KEY_TRUST -> {
                steps.add(Action.REBUILD_TRUST_REGISTRY);
                steps.add(Action.INVALIDATE_SESSIONS_AND_CACHES);
            }
        }

        // Nếu điều tra xác nhận plaintext key có thể đã rời
        // custody, xem xét mở rộng phạm vi re-encryption.
        // Không tự động phán đoán loại dữ liệu hay chạy crypto.
        if (incident.confirmedPlaintextExposure()
                && (incident.kind() == ExposureKind.KMS_CREDENTIAL
                    || incident.kind() == ExposureKind.WRAPPED_DEK_ONLY)) {
            steps.add(Action.ROTATE_KEY_MATERIAL);
            steps.add(Action.ASSESS_DEK_REENCRYPTION);
            steps.add(Action.ASSESS_WRAPPED_DEK_DEPENDENCIES);
        }

        return new ResponsePlan(
                incident.incidentRef(),
                incident.keyRef(),
                Set.copyOf(steps));
    }

    public static void main(String[] args) {
        Incident exposedDek = new Incident(
                "INC-2026-KEY-041",
                "billing-dek-family-A",
                "tenant-A",
                ExposureKind.RAW_DEK,
                true);

        Incident wrongJwks = new Incident(
                "INC-2026-KEY-042",
                "payment-signing-public-s2",
                "payments",
                ExposureKind.WRONG_PUBLIC_KEY_TRUST,
                false);

        System.out.println(plan(exposedDek));
        System.out.println(plan(wrongJwks));

        // Chỉ in reference và action enums. Trong production:
        // mapping sang automation phải kiểm role, scope, policy
        // version, trạng thái key, dependency và approval thật.
    }

    private WrongKeyDistributionResponseDemo() {}
}
~~~

### 14.1. Điều ví dụ thể hiện

1. **Phân loại trước hành động:** `RAW_DEK` dẫn tới kiểm tra re-encryption, còn `WRONG_PUBLIC_KEY_TRUST` dẫn tới sửa trust registry.
2. **Thu hồi quyền không thay rotation:** một plan với `REVOKE_ACCESS` không có nghĩa secret đã lộ được giữ bí mật trở lại.
3. **Không tự thực hiện thao tác không thể đảo ngược:** code không gọi KMS `Delete` hay xuất key material.
4. **Không in bí mật:** event chỉ mang incident/key/tenant reference và enum action, không chứa secret.
5. **Yêu cầu phê duyệt độc lập:** response plan là **đề xuất để review**, không phải lệnh tự động.
6. **Không suy diễn quá mức từ wrapped DEK:** chỉ khi điều tra cho thấy plaintext exposure mới mở rộng đánh giá DEK re-encryption.
7. **Hành vi có thể kiểm thử:** mỗi loại exposure sinh danh sách hành động có thể đối chiếu với policy.

### 14.2. Hạn chế không được bỏ qua

- `Incident` không xác thực người gửi; **attacker không được phép gửi payload làm hệ thống tự disable key**.
- `confirmedPlaintextExposure` chỉ là metadata minh họa, phải đến từ **bằng chứng và người có thẩm quyền**.
- **DEK vs KEK vs signing key** có thể có nhiều usage thực tế; taxonomy này không thể thay đầy đủ key inventory.
- Không có token/session revocation thật, KMS adapter, transaction, retry, audit persistence, concurrency hoặc recovery drill.
- `Set.copyOf` cho tập action không bảo đảm thứ tự; **runbook phải quy định quan hệ phụ thuộc và thứ tự thực thi**.
- Không có cơ chế **quorum, approval signatures, RBAC, least privilege** hay phân loại mức độ ưu tiên theo sự cố.
- Không thể dùng một enum để quyết định có cần thông báo vi phạm dữ liệu hoặc giữ bằng chứng pháp lý hay không.
- Không nên log key ID/tenant ID tùy tiện nếu chúng chứa PII; ví dụ sử dụng **opaque references**.

**Đặc biệt:** Không nên tự triển khai crypto operations trong incident planner. Việc xoay/re-encrypt phải dùng **KMS/HSM và thư viện AEAD chuẩn**, theo quy trình độc lập đã được kiểm tra.

## 15. Quy trình migration có thể rollback nhưng không tái tin khóa bị lộ

Một kế hoạch thay khóa cần có **read compatibility** và **atomic metadata updates**, nhưng phải tránh **security rollback**.

### 15.1. Với dữ liệu envelope encryption

~~~mermaid
flowchart TD
    PLAN["Xác minh DEK/KEK và dữ liệu bị ảnh hưởng"] --> NEW["Tạo DEK/KEK successor theo policy"]
    NEW --> SWITCH["Chuyển new writes sang key mới"]
    SWITCH --> MIGRATE["Migrate/re-encrypt/re-wrap đúng loại compromise"]
    MIGRATE --> CAS["CAS cập nhật ciphertext + wrapped DEK + references atomically"]
    CAS --> VERIFY["Verify AEAD tag, quyền tenant, consistency"]
    VERIFY --> BACKUP["Đối soát snapshots, archive và DR"]
    BACKUP --> DECIDE{"Key cũ còn dependency/retention?"}
    DECIDE -->|Có| PROTECT["Giới hạn đường đọc cũ, chặn writes, xử lý recovery"]
    DECIDE -->|Không| RETIRE["Retire/disable theo phê duyệt"]
    RETIRE --> DESTROY["Destroy theo chính sách và bằng chứng"]
~~~

Nếu **DEK đã lộ**, migration cần **re-encrypt bằng DEK mới**. Nếu chỉ đổi KEK còn DEK được đánh giá không bị lộ, re-wrap có thể phù hợp. Nếu signing key bị lộ, vấn đề chính là **trust và chữ ký**, không phải ciphertext.

### 15.2. Tại sao cần CAS?

Khi online writers và migration workers cùng cập nhật một record, một worker có thể:

- Đọc ciphertext cũ bảo vệ bằng DEK-A.
- Một writer khác đổi sang DEK-B và ciphertext-B.
- Worker đầu lưu lại wrapped DEK-A theo metadata mới mà không kiểm tra revision.

Kết quả: metadata, wrapped DEK và ciphertext **không còn nhất quán**, có thể không giải mã được. Cần **compare-and-swap** (revision/version), cập nhật nguyên tử đúng nhóm trường và retry idempotent theo bản ghi thực.

### 15.3. Không retry mù khi KMS báo lỗi

| Lỗi | Cách xử lý |
| --- | --- |
| **AccessDenied** | Kiểm IAM/policy, không fallback sang hard-coded key. |
| **Context mismatch** | Kiểm tenant/object/purpose và encryption context gốc, không thử mọi key. |
| **GCM tag invalid** | Từ chối plaintext, kiểm integrity, không bỏ tag verification. |
| **KMS timeout/throttling** | Retry có giới hạn và backoff theo idempotency. |
| **Old key disabled** | Đánh giá recovery/trust policy; không tự bật lại key compromise. |
| **DB conflict** | Đọc lại revision và key lineage, không ghi đè mù. |
| **Missing key material** | Xác định provider recovery/backup, không tạo key khác rồi coi có thể decrypt cũ. |

**Không chọn “dịch vụ chạy được” bằng cách bỏ bảo mật.** Khả năng sẵn sàng phải dựa trên phương án DR/caching có kiểm soát được thiết kế trước, không phải fallback secret cố định.

## 16. Backup/DR và key lifecycle sau phân phối sai

Các bản sao lưu có thể chứa:

- Wrapped DEK dưới KEK cũ.
- Ciphertext và AEAD nonce/tag của dữ liệu cũ.
- Certificate/public key trust stores ở thời điểm chưa revoke.
- Key registry/alias state cũ.
- KMS/HSM backup/recovery blobs.
- Application configuration hoặc IAM policy bị lỗi.
- Logs có thể chứa raw key bị lộ.

**Restore snapshot cũ có thể tái tạo chính lỗ hổng đã được sửa.** Vì vậy runbook khôi phục phải **reconcile với current revocation state và current IAM/trust policy**, không phục hồi nguyên xi một trust store từng chấp nhận attacker key.

### 16.1. RPO/RTO và dependency version

- **RPO:** lượng trạng thái được chấp nhận mất sau sự cố.
- **RTO:** thời gian mục tiêu để hệ thống trở lại hoạt động.
- **Key-version coverage:** bản sao dữ liệu tại recovery point có đi kèm wrapped DEK và đường giải mã qua KEK tương ứng không?
- **Revocation freshness:** sau restore, hệ thống có biết key/credential nào **đã bị revoke sau snapshot** không?
- **Cryptographic recovery testing:** restore thật một tập dữ liệu đã được phép, kiểm tra AES-GCM tag và phân quyền.

**Một snapshot có đủ ciphertext nhưng thiếu đường phục hồi DEK/KEK không bảo đảm khả năng khôi phục**. Ngược lại, phục hồi key sai trạng thái có thể làm hệ thống tiếp tục chấp nhận chữ ký giả.

### 16.2. Crypto-shredding: tuyên bố phải có điều kiện

Crypto-shredding chỉ có ý nghĩa khi **mọi đường có thể giải mã trong phạm vi được xác định** đã bị loại bỏ. Nếu raw DEK từng được gửi nhầm, **không thể bảo đảm attacker đã xóa bản sao đó**.

Do đó không nên tuyên bố “đã crypto-shred mọi bản sao” chỉ bằng `DestroyKey` trên một KMS object. Cần phân biệt:

- Khóa đã được hủy ở **miền tổ chức kiểm soát** theo bằng chứng provider.
- Bản sao ở **backup/escrow/replica/log/cache** đã được xử lý theo chính sách.
- Bên nhận trái phép **có thể còn bản sao ngoài kiểm soát**, đây là rủi ro còn lại phải ghi nhận.

## 17. Kiểm toán và truyền thông sự cố

Audit cần **đủ để dựng timeline nhưng không làm phát tán secret thêm lần nữa**.

### 17.1. Bộ sự kiện gợi ý

~~~json
{
  "eventType": "KEY_DISTRIBUTION_INCIDENT",
  "incidentRef": "INC-2026-KEY-041",
  "sourceServiceRef": "billing-service",
  "recipientRef": "unexpected-workload",
  "keyRef": "billing-dek-family-A",
  "keyUsage": "DATA_ENCRYPTION",
  "exposureClass": "RAW_DEK",
  "containmentState": "IN_PROGRESS",
  "policyVersion": "key-distribution-policy-v5",
  "result": "REQUIRES_ROTATION_ASSESSMENT",
  "correlationId": "opaque-event-id"
}
~~~

Đây là **mẫu metadata minh họa**, không phải bằng chứng sự cố thật. Không in DEK, KEK, private key, credential, full KMS response, HSM shares, plaintext dữ liệu hoặc nội dung ticket chứa secret.

### 17.2. Nguồn audit cần đối chiếu

| Nguồn | Câu hỏi |
| --- | --- |
| **Application audit** | Caller nào được cho phép/từ chối trên tenant/object? |
| **KMS provider audit** | Principal nào đã Sign/Decrypt/Unwrap/GenerateDataKey trên key nào? |
| **IAM change history** | Ai đã tạo role/grant, chỉnh policy hoặc mở rộng trust? |
| **PKI/key registry logs** | Public key/certificate nào được phát hành, revoke hoặc thay mapping? |
| **CI/CD/artifact logs** | Secret có đi vào build job, image hoặc release nào? |
| **Log/APM/SIEM export inventory** | Có bản sao key/credential trong pipelines hoặc archive nào? |
| **Data access logs** | Ciphertext/plaintext nào đã được đọc, export hoặc gửi ra ngoài? |
| **Backup/DR records** | Snapshot và recovery path nào còn dựa vào key cũ? |

**Không có log Decrypt không chứng minh key chưa lộ** nếu raw DEK đã bị copy qua kênh khác. Ngược lại, một **KMS Decrypt SUCCESS** không tự chứng minh người dùng cuối có quyền truy cập dữ liệu; cần liên kết cả lớp ứng dụng.

### 17.3. Truyền thông và phê duyệt

Tổ chức cần quy định:

- Ai được biết **tên key, tenant, resource và severity**.
- Ai được duyệt rotate/revoke/disable/destroy và theo mức ảnh hưởng.
- Khi nào cần thông báo data owner, khách hàng, nhà cung cấp hoặc bộ phận pháp lý theo nghĩa vụ áp dụng.
- Cách bảo vệ **incident evidence** và giới hạn truy cập log/copy secret.
- Tiêu chí đóng sự cố và **rủi ro còn lại** phải được ghi nhận.

**Không gửi nguyên key đã lộ cho các bên để họ “xác nhận đã nhận”**. Chỉ gửi các định danh/bằng chứng đã phân loại và hành động cần thực hiện.

## 18. Kiểm thử xác minh thu hồi đã hiệu lực

Một sự cố chưa hoàn tất nếu chỉ có dòng ticket “rotated successfully”. Cần negative tests và kiểm tra **đường sử dụng thực tế**.

| Kiểm thử | Kết quả mong đợi |
| --- | --- |
| Principal sai tiếp tục gọi KMS Sign/Decrypt | Bị từ chối sau khi chính sách/phiên có hiệu lực. |
| Token/credential đã revoke | Không tạo được session mới, phiên cũ được xử lý theo provider. |
| Service tenant B đọc invoice tenant A | Application authorization từ chối **trước khi gọi KMS**. |
| DEK cũ bị phân phối sai | New writes không còn dùng DEK cũ; dữ liệu được migrate theo scope. |
| Wrapped DEK/metadata bị thay | KMS integrity/context hoặc AES-GCM AAD/tag từ chối. |
| KEK v3 đã retired | Không tạo wrapped DEK mới dưới v3; đường đọc lịch sử đúng policy. |
| Private signing key S1 bị revoke | Verifier từ chối chữ ký mới theo trust policy. |
| Public key attacker ở registry cũ | Trust store mới không chấp nhận; rollback manifest bị từ chối. |
| Verifier cache trước revocation | Cache được invalidated hoặc hết hạn theo chiến lược đã duyệt. |
| TLS client nhận certificate sai hostname | Từ chối; không có trust-all fallback. |
| PSK/HMAC secret cũ | Các bên chấp nhận secret mới, không tiếp tục nhận token/MAC cũ ngoài cửa sổ. |
| DR restore snapshot trước sự cố | Không hồi sinh IAM/trust/key state bị revoke, dữ liệu còn đọc được hợp lệ. |
| CI/CD/observability | Không xuất raw key/credential vào log và artifacts. |
| Concurrent migration | Không ghi đè ciphertext/wrapped DEK lệch version; CAS hoạt động. |
| Audit trail | Đối chiếu được timeline và approvals, không có raw secret. |

### 18.1. Xác nhận công việc “đã xong” theo ba tầng

1. **Containment:** đường phân phối sai đã được chặn; principal/session/grant/trust sai không còn tác dụng theo cơ chế kiểm tra thực tế.
2. **Recovery:** successor keys/trust đã được triển khai; dữ liệu vẫn giải mã/xác minh đúng và đạt mục tiêu vận hành có phê duyệt.
3. **Residual risk:** dữ liệu/chữ ký lịch sử, logs, backups, bản sao ngoài kiểm soát và nghĩa vụ thông báo đã được đánh giá, tài liệu hóa.

Một trong ba tầng chưa đạt thì không nên gọi sự cố là “không còn ảnh hưởng”.

## 19. Tình huống thực tế: Payment, Ledger và Billing

Một nền tảng thanh toán có:

- **Billing Service:** AES-GCM encrypt invoices bằng DEK; KMS/HSM giữ KEK.
- **Payment Service:** KMS/HSM Sign payment events bằng Ed25519.
- **Ledger Service:** Verify chữ ký từ key registry/JWKS tin cậy, kiểm tra issuer, audience, tenant và replay.

### 19.1. Sự cố A – Billing cấp nhầm raw DEK cho tenant khác

Một migration job có bug dùng `tenantRef` từ request chưa được xác thực, làm **DEK của tenant A** được đưa vào response của workload tenant B.

Hướng xử lý:

1. Chặn endpoint/job và cô lập principal hoặc cache liên quan.
2. Xác định **DEK ID, record IDs, ciphertext và backup** được bảo vệ bằng DEK đó.
3. Kiểm tra KMS/API audit và logs để phân loại ai có thể đã nhận raw DEK và ciphertext.
4. Tạo DEK successor, chuyển new writes và migrate/re-encrypt dữ liệu bị ảnh hưởng.
5. Đối soát metadata AAD/context, wrapped DEK và quyền read của tenant A/B.
6. Test tenant B không còn lấy được DEK/record A; giám sát thêm.
7. Không tuyên bố đã khôi phục bí mật cho các plaintext có thể đã bị đọc trước khi rotate.

**Một thay đổi IAM đúng là cần thiết nhưng chưa đủ** khi raw DEK đã rời ranh giới ứng dụng.

### 19.2. Sự cố B – Payment private key S1 bị đóng trong artifact

Một release artifact chứa **private signing key S1** dưới dạng file PEM có thể trích xuất. Một số nhóm ngoài phạm vi có artifact.

Hướng xử lý:

1. Ngừng dùng S1 để Sign mới; áp chính sách kiểm soát khẩn cấp.
2. Phát hành S2 trong KMS/HSM, chỉ đưa **public key** tới verifiers theo trust path đúng.
3. Cập nhật Ledger trust; không tin S1 vô điều kiện cho event mới.
4. Xem các signed events trong thời gian có nguy cơ và kiểm chứng dữ liệu nghiệp vụ/idempotency.
5. Đánh giá artifact repositories, caches và bản sao đã phát hành.
6. Thu hồi/quản lý S1, audit root cause để không tiếp tục đóng private key vào build.

**Không thể lấy lại mọi bản artifact đã tải xuống.** Do đó kế hoạch **revocation và xử lý lịch sử** là phần chính, không chỉ xóa private PEM ở commit mới.

### 19.3. Sự cố C – Ledger tin public key của attacker

Một cache/JWKS mapping bị thay để `kid=S2` trỏ tới public key của attacker. Ledger có thể đã chấp nhận một số event giả với chữ ký hợp lệ dưới key đó.

Hướng xử lý:

1. Cô lập nguồn registry/cache sai và chặn nhận key từ URL không được kiểm soát.
2. Khôi phục issuer/trust anchor/algorithm/key usage đúng; áp version monotonic và revocation.
3. Rà soát các event đã được chấp nhận theo **key fingerprint/trust entry và thời gian**.
4. Với sự kiện tiền tệ, kiểm tra authorization và chống replay/idempotency.
5. Sửa nguồn phân phối và security review; không tự kết luận private key thật của Payment đã bị lộ.

**Điểm chung:** Cả ba tình huống đều là “phân phối sai”, nhưng **phản ứng khác nhau** vì tài sản bị ảnh hưởng và trust boundary khác nhau.

## 20. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Chỉ revoke IAM sau khi raw DEK lộ | Người nhận trái phép vẫn có thể giữ DEK. | DEK rotation/re-encrypt và đánh giá dữ liệu cũ. |
| Coi wrapped DEK bằng raw DEK | Đánh giá sai severity hoặc xử lý quá rộng không có căn cứ. | Phân loại blob, wrap context, quyền unwrap và bằng chứng. |
| Coi KMS non-exportable là không thể lạm dụng | Principal có quyền Sign/Decrypt vẫn có thể tạo chữ ký/đọc dữ liệu. | Revoke rights, điều tra provider audit và scope. |
| Re-wrap cùng DEK đã bị lộ | Ciphertext cũ vẫn có thể giải mã bằng DEK đã lộ. | Thay DEK khi cần và re-encrypt. |
| Hủy KEK ngay lập tức | Mất khả năng đọc archive/snapshot nhưng không xóa key attacker đã copy. | Dependency inventory, recovery plan, phê duyệt. |
| Không chuyển verifier trust sau private key compromise | Attacker tiếp tục tạo chữ ký được chấp nhận. | Rotate signer và cập nhật/revoke ở verifier. |
| Tin chữ ký hợp lệ là event được phép | Event giả/replay vẫn có thể qua Verify. | Kiểm issuer/audience/tenant/authorization/idempotency. |
| Tự lấy public key từ token/JWKS URL | Chấp nhận key attacker. | Issuer allowlist/trust anchor, identity binding. |
| Không chống rollback trust store | Manifest/cert/key cũ có thể tái xuất hiện. | Monotonic version, revocation state và atomic update. |
| Chỉ sửa một API, quên CI/log/backup | Raw secret vẫn tồn tại ở nhiều bản sao. | Truy theo distribution chain và quản trị retention. |
| Cấp quyền `kms:*` để khôi phục nhanh | Tăng phạm vi quyền sai, nguy cơ xóa/giả mạo. | Least privilege, scoped break-glass và audit. |
| Quên phiên/token đang hoạt động | Quyền bị revoke trên giấy nhưng access vẫn tiếp diễn. | Xác minh policy propagation, session/cache invalidation. |
| Dùng KMS key alias như material version | Gọi sai key khi rotate/restore. | Trusted key ID/version/lineage và metadata. |
| Thay mỗi `keyVersion` nhưng không đổi ciphertext | Metadata và key material không nhất quán. | Atomic re-encryption/rewrap đúng loại thao tác. |
| Bỏ qua AES-GCM tag để “đọc tạm” | Chấp nhận dữ liệu bị sửa, mất tính toàn vẹn. | Fail closed, đúng AAD/nonce/tag. |
| Dựa duy nhất vào KMS logs | Không biết user cuối có quyền với dữ liệu hay không. | Correlate application authorization và provider audit. |
| Bật lại signing key đã revoke khi restore | Tái mở đường giả mạo event. | Reconcile với current trust/revocation state. |
| Mặc định mọi public key phát nhầm đều là secret leak | Khó chọn đúng hành động, làm gián đoạn không cần thiết. | Phân biệt key material và trust binding. |
| Không kiểm DR trước khi destroy | Hủy khả năng phục hồi dữ liệu lịch sử. | Restore drill với đúng key versions. |
| Chỉ đóng incident sau rotation | Không xử lý dữ liệu/chữ ký có thể đã lộ trước đó. | Residual-risk review và hậu kiểm. |

## 21. Checklist xử lý sau phân phối sai

1. **Xác định:** secret key, public key, wrapped DEK, credential hay capability KMS nào được cấp nhầm?
2. **Phạm vi:** key ID/version, usage, tenant, issuer/recipient và environment có được xác minh từ nguồn tin cậy không?
3. **Thời điểm:** biết cửa sổ phân phối sai, thời gian phát hiện và cập nhật chính sách chưa?
4. **Containment:** đã ngừng đường phát tán và giới hạn quyền đọc/copy tiếp chưa?
5. **Credentials:** grants, sessions, cache và token còn hiệu lực đã được xử lý theo provider chưa?
6. **Material exposure:** có raw DEK/KEK/private key/PSK/seed thực sự ra khỏi custody không?
7. **Operations:** đã kiểm audit Sign/Decrypt/Unwrap/GenerateDataKey chưa?
8. **Data dependencies:** ciphertext, wrapped DEK, archives/backups và consumers liên quan đã được kiểm kê chưa?
9. **DEK compromise:** có cần DEK mới và re-encrypt thay vì chỉ re-wrap không?
10. **KEK compromise:** đã xác định phạm vi DEK có thể unwrap và bảo vệ backups chưa?
11. **Signing compromise:** đã chặn Sign cũ, phát hành S2 và cập nhật verifier trust chưa?
12. **Trust misbinding:** có kiểm issuer/audience/key usage/algorithm/revocation/anti-rollback không?
13. **IAM:** application authorization theo tenant/object và KMS policy có được kiểm tra riêng không?
14. **Migration:** new writes/Sign đã chuyển sang successor, updates atomically và có CAS không?
15. **Crypto:** AES-GCM nonce/tag/AAD, chữ ký và key schedule có còn đúng sau migration không?
16. **Recovery:** DR snapshots có được đối soát với key versions và current revocation state chưa?
17. **Destroy:** đã có approval và dependency check trước bất kỳ thao tác không thể đảo ngược chưa?
18. **Audit:** có timeline, actor, reason codes, policy versions và correlation IDs mà không log key material không?
19. **Negative tests:** principal/tenant sai, key cũ, trust cũ và revoked credential đều bị từ chối chưa?
20. **Residual risk:** phạm vi dữ liệu đã có thể bị đọc hoặc chữ ký giả đã có thể được phát hành được ghi nhận chưa?
21. **Prevention:** root cause được khắc phục ở code, KMS policy, registry, CI/log hoặc quy trình phân phối chưa?
22. **Ownership:** incident commander, Security, data owner và các consumer đã xác nhận điều kiện kết thúc chưa?

## 22. Câu hỏi tự kiểm tra

1. “Thu hồi quyền KMS” khác “thu hồi secret đã bị người khác biết” ở đâu?
2. Tại sao xóa một message chứa DEK không tự bảo đảm khóa đã trở lại bí mật?
3. Khi chỉ có public key bị đưa nhầm vào trust store, có nhất thiết private key thật đã bị lộ không?
4. DEK và KEK khác nhau về phạm vi ảnh hưởng khi bị phân phối sai như thế nào?
5. Vì sao re-wrap DEK dưới KEK mới không chữa được DEK compromise?
6. Nếu raw KEK đã lộ, tại sao phải xem tất cả wrapped DEK và backups liên quan?
7. KMS non-exportable key có thể bị lạm dụng như thế nào mà không cần xuất private key?
8. Khi một workload đã gọi `DecryptDataKey` trái phép, những bằng chứng nào giúp xác định DEK và dữ liệu rõ có thể bị ảnh hưởng?
9. Vì sao một chữ ký S1 vẫn Verify toán học thành công sau khi private key S1 bị revoke?
10. Điều gì cần thay ở phía Ledger khi Payment signing key bị compromise?
11. Tại sao chỉ chặn key ở signer mà không cập nhật verifier trust là chưa đủ?
12. Khi key mapping trong JWKS bị tráo, vì sao kiểm `kid` không chứng minh issuer?
13. Trong hệ multi-tenant, vì sao KMS IAM thành công không đồng nghĩa user cuối được đọc dữ liệu?
14. Nếu wrapped DEK bị gửi sai tenant nhưng không thể unwrap, cần đánh giá rủi ro thế nào?
15. Nếu PSK/HMAC secret bị cấp nhầm, vì sao cần cập nhật cả hai bên chia sẻ secret?
16. Tại sao phải xử lý session, resumption hoặc token sau khi thu hồi identity?
17. Một snapshot được tạo trước ngày revoke có thể tạo nguy cơ gì khi DR restore?
18. Vì sao CAS quan trọng khi re-encrypt đang chạy đồng thời với service online?
19. Nếu KMS AccessDenied sau thu hồi, có được fallback sang raw AES key cố định không?
20. Những metadata audit nào đủ điều tra mà không cần log DEK/KEK/private key?
21. Vì sao destroy KEK không chứng minh đã crypto-shred mọi bản copy DEK?
22. Điều kiện nào chứng minh containment, recovery và residual-risk review đã hoàn tất?

**Ghi nhớ:** **Thu hồi sau khi phân phối sai** là một **quy trình xử lý sự cố theo loại tài sản và ranh giới tin cậy**, không phải một nút `Revoke` dùng chung. Phải **chặn đường cấp sai, bảo toàn bằng chứng, thu hồi quyền và phiên, đánh giá raw key exposure, rotate/re-encrypt hoặc sửa trust đúng trường hợp, đối soát KMS/HSM và application authorization, xác minh backup/DR và lưu audit**. Khi một secret đã rời khỏi miền tin cậy, không thể bảo đảm người nhận trái phép quên nó; mục tiêu thực tế là **hạn chế sử dụng tiếp, giảm rủi ro về sau, đánh giá tác động quá khứ và khôi phục vòng đời khóa với bằng chứng có thể kiểm chứng**.

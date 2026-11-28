# Backup storage độc lập — Tách vùng lưu trữ sao lưu khỏi hệ thống quản lý khóa production

## 1. Backup storage độc lập là gì?

**Backup storage độc lập** là cách thiết kế trong đó **bản sao lưu, dữ liệu phục hồi và bằng chứng cần thiết để khôi phục khóa được lưu trong một vùng quản trị riêng biệt với môi trường production**, có danh tính, quyền truy cập, ranh giới mạng, cơ chế bảo vệ và quy trình phục hồi riêng.

Mục tiêu là bảo đảm sự cố trong production **không tự động xóa, sửa, mã hóa lại hoặc làm mất khả năng truy cập bản sao lưu**. Một bản backup đặt ở bucket khác nhưng vẫn dùng cùng tài khoản quản trị, cùng credential và cùng quyền xóa có thể vẫn bị phá hủy trong một cuộc tấn công chiếm quyền production.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, backup storage độc lập hỗ trợ vòng đời khóa từ **tạo, cấp phát, lưu trữ, sử dụng, rotation, thu hồi đến hủy**. Nó kết nối với **mật mã đối xứng/bất đối xứng, chữ ký số, KMS/HSM, envelope encryption, kiểm soát truy cập và kiểm toán**.

Ví dụ, hệ thống Billing dùng KMS/HSM bảo vệ KEK, DEK mã hóa hóa đơn và database lưu ciphertext. Một cuộc tấn công ransomware chiếm quyền quản trị production. Nếu backup ciphertext, metadata key version và recovery material đều nằm trong cùng account với quyền quản trị đó, attacker có thể xóa cả dữ liệu lẫn khả năng phục hồi. Thiết kế độc lập tạo một **recovery boundary** mà quyền production không thể tự ý thay đổi.

> **Nguyên tắc:** Backup chỉ thực sự độc lập khi **đường quản trị, quyền xóa, credential, khả năng khôi phục và bằng chứng toàn vẹn** được bảo vệ trước cùng sự cố có thể phá production.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **backup storage độc lập** với việc chỉ tạo thêm một bản sao trong cùng môi trường.
2. Thiết kế tách biệt **account, region, network, identity, administrator và audit**.
3. Phân biệt backup dữ liệu mã hóa, backup key material, backup metadata và recovery evidence.
4. Chọn mô hình phù hợp cho **KMS, HSM, wrapped DEK, signing key và key hierarchy**.
5. Bảo vệ backup bằng **immutability/WORM, offline copy, encryption, integrity manifest và quorum approval**.
6. Thiết kế retention, RPO/RTO, restore order, key custody và recovery drill.
7. Nhận diện rủi ro **ransomware, credential compromise, circular dependency và backup poisoning**.

## 2. Vì sao một bản backup trong cùng production chưa đủ?

Giả sử production có:

~~~text
Production account:
    Database
    Ciphertext object store
    KMS key / HSM partition
    Backup bucket
    Backup job
    IAM administrator
~~~

Nếu một attacker chiếm được quyền admin account, họ có thể đồng thời:

- Xóa database và backup bucket.
- Thay retention hoặc tắt versioning.
- Xóa snapshot/replica.
- Sửa backup job để tạo bản sao hỏng.
- Disable hoặc schedule deletion KEK.
- Sửa IAM để chặn recovery team.
- Xóa log hoặc làm sai lệch manifest.

**Khác vị trí lưu trữ không có nghĩa khác trust boundary.** Hai bucket trong cùng account có thể cùng chịu một quyền quản trị; hai region có thể dùng cùng identity provider và cùng control plane.

### Một ví dụ so sánh

| Thiết kế | Điều có thể bảo vệ | Điểm yếu còn lại |
| --- | --- | --- |
| Hai thư mục trên cùng máy | Hạn chế lỗi xóa nhầm đơn giản | Mất máy/ransomware làm mất cả hai |
| Hai bucket cùng account | Một số lỗi object-level | Admin account có thể xóa cả hai |
| Hai region cùng account | Một số sự cố vùng địa lý | Identity/admin/control plane có thể dùng chung |
| Account backup riêng, credential riêng | Tách quyền production | Cần kiểm soát trust, recovery role và tổ chức |
| Backup account + immutable copy + offline copy | Giảm nguy cơ sửa/xóa đồng thời | Vẫn cần kiểm tra integrity, key recovery và restore |
| Bản offline do custodian độc lập giữ | Tách khỏi đường mạng thường ngày | Có rủi ro mất media, sai quy trình và lỗi khôi phục |

### Độc lập phải xét theo nhiều chiều

Không chỉ hỏi **“backup nằm ở đâu?”** mà phải hỏi:

- Ai có quyền ghi, đọc, xóa và thay retention?
- Production credential có thể assume role ở backup account không?
- Backup admin có thể đăng nhập production không?
- Một IdP bị chiếm có thể cấp quyền cho cả hai bên không?
- Log của backup có nằm trong cùng account mà attacker có thể xóa không?
- Recovery key có phụ thuộc vào chính hệ thống đang được phục hồi không?
- Có người hoặc quy trình độc lập xác nhận restore không?

## 3. Phân biệt bốn loại thứ cần backup trong key management

Trong hệ thống quản lý khóa, “backup khóa” có thể chỉ nhiều tài sản rất khác nhau. Cần kiểm kê riêng.

| Loại | Ví dụ | Mục đích | Lưu ý |
| --- | --- | --- | --- |
| **Encrypted data backup** | Database snapshot, object ciphertext, archive | Khôi phục dữ liệu nghiệp vụ | Có thể không dùng được nếu mất key |
| **Key material backup** | HSM secure backup, wrapped key blob, recovery share | Khôi phục khả năng dùng key | Phụ thuộc loại key và cơ chế provider |
| **Key metadata/config backup** | Key ID/version, purpose, attributes, policy, alias mapping | Dựng lại quan hệ và cách sử dụng | Không chứa raw secret |
| **Recovery evidence** | Manifest, checksums, approvals, audit, certificate chain | Xác minh nguồn gốc và tính toàn vẹn | Cần giữ độc lập, chống sửa |

### 3.1. Encrypted data backup

Bản sao dữ liệu có thể gồm:

- Ciphertext.
- Nonce/IV và authentication tag.
- AAD hoặc thông tin cần tái tạo AAD.
- Wrapped DEK.
- Key ID/material version.
- Schema version, record ID và metadata định tuyến.
- Database transaction/log sequence hoặc object version.

**Chỉ có ciphertext mà không có metadata key version và cách khôi phục key có thể khiến backup không thể giải mã.**

### 3.2. Key material backup

Không phải key nào cũng được phép export. Có thể có các dạng:

- **HSM vendor-supported secure backup:** vật liệu được sao lưu trong định dạng bảo vệ của thiết bị, thường phụ thuộc backup domain/partition và quy trình restore.
- **Wrapped key backup:** key được bọc dưới một wrapping key được kiểm soát.
- **KMS provider-managed durability/replication:** nhà cung cấp quản lý material và availability theo semantics dịch vụ; không nhất thiết cho khách hàng export raw key.
- **Recovery shares hoặc quorum material:** các phần thông tin phục hồi được phân tách theo quy trình split knowledge.
- **Public key/certificate archive:** dữ liệu công khai phục vụ verify lịch sử; không phải private key backup.

**Không dùng cách export raw key tùy tiện chỉ để tạo một bản backup.** Phải tuân thủ key usage, exportability, custody policy và cơ chế backup được thiết kế cho đúng loại thiết bị/dịch vụ.

### 3.3. Metadata/config backup

Metadata thường không bí mật như raw key nhưng có thể nhạy cảm về kiến trúc và quyền. Cần lưu:

- Key ID, version, purpose, algorithm và state.
- Owner, custodian, workload principal và scope.
- Key policy/IAM revision, grants và allowed operations.
- Parent/child lineage nếu dùng KDF.
- KEK–wrapped DEK dependencies.
- HSM partition, token/object identifier và backup-set reference.
- Rotation, activation, revocation và destruction history.
- Mapping ciphertext/archive tới key version.

### 3.4. Recovery evidence

Evidence giúp trả lời **bản backup này đến từ đâu, có bị sửa không, ai đã tạo và ai đã phê duyệt restore?** Bao gồm manifest, signature, digest, event references, timestamps, chain of custody và kết quả restore test.

## 4. Mô hình độc lập: tách control plane và recovery plane

Một thiết kế tham khảo tách production và backup thành hai miền quản trị.

~~~mermaid
flowchart LR
    subgraph PROD["Production trust domain"]
      APP[Workloads]
      DB[(Ciphertext database)]
      KMS[KMS / HSM production]
      APP --> DB
      APP --> KMS
      DB --> JOB[Backup export job]
      KMS --> META[Key metadata export]
    end
    subgraph REC["Independent recovery domain"]
      ING[Restricted backup ingest]
      IMM[(Immutable backup storage)]
      OFF[(Offline / isolated copy)]
      VAULT[Recovery evidence vault]
      ING --> IMM
      IMM --> OFF
      ING --> VAULT
    end
    JOB --> ING
    META --> ING
    IMM --> RESTORE[Approved restore workflow]
    OFF --> RESTORE
    VAULT --> RESTORE
~~~

**Đường dữ liệu backup có thể đi từ production sang recovery domain**, nhưng quyền quản trị production không được tự động trở thành quyền sửa/xóa bản sao đã lưu.

### Những ranh giới cần tách

1. **Account/subscription/project:** backup nằm trong account riêng.
2. **Identity:** credential backup không tái sử dụng production service account.
3. **Administrator:** người quản trị backup không mặc nhiên là production admin.
4. **Network:** ingest path được giới hạn; backup storage không mở write API rộng.
5. **Audit:** log gửi sang miền lưu trữ khác và có quyền xóa độc lập.
6. **Retention:** production không được tự rút ngắn retention hoặc phá legal hold.
7. **Recovery approval:** restore cần xác thực và phê duyệt theo mức rủi ro.
8. **Key custody:** recovery material được giữ theo quy trình riêng, có kiểm kê và kiểm tra định kỳ.

### Tách account vẫn có thể chưa đủ

Nếu backup account chấp nhận assume-role từ production root/admin, hoặc cả hai phụ thuộc một IdP duy nhất có thể bị chiếm, sự độc lập suy giảm. Cần threat model cả **identity federation, break-glass, organization policy, service control policy, billing/admin ownership và audit control**.

## 5. Các lớp độc lập cần thiết

| Lớp | Thiết kế gợi ý | Câu hỏi kiểm chứng |
| --- | --- | --- |
| **Logical** | Account/project/tenant riêng | Production admin có thể sửa backup policy không? |
| **Identity** | IdP/role/credential độc lập hoặc trust có giới hạn | Một credential bị lộ có mở cả hai miền? |
| **Administrative** | Backup custodian và approver độc lập | Một người có thể ghi, xóa và duyệt restore? |
| **Network** | Private ingest, isolated restore network, offline media | Production host có thể truy cập xóa bản backup? |
| **Geographic** | Region/site khác theo BCP/DR | Sự cố vùng có ảnh hưởng cả hai? |
| **Storage** | Immutable/WORM/versioned/object-lock hoặc offline | Có thể sửa/xóa trong retention không? |
| **Cryptographic** | Backup encryption key và signing evidence phù hợp | Mất production KEK có làm mất backup key? |
| **Audit** | Log độc lập, append-only và alert | Attacker có thể xóa cả event và alert? |
| **Process** | Dual control, approval, restore drill | Có khôi phục mà không cần một admin duy nhất? |

### Nguyên tắc “blast radius”

**Mục tiêu không phải tạo thật nhiều tài khoản**, mà là giảm số lớp có thể bị phá bởi cùng một credential, cùng một admin, cùng một lỗi cấu hình hoặc cùng một sự cố địa lý.

## 6. Immutable, WORM và offline backup

### 6.1. Immutable storage

**Immutable backup** là bản sao được bảo vệ khỏi thay đổi/xóa trong khoảng thời gian hoặc điều kiện được cấu hình. Các cơ chế thường gặp:

- Object lock với retention mode phù hợp.
- WORM (*Write Once, Read Many*) storage.
- Snapshot lock hoặc retention lock.
- Append-only repository.
- Versioned object storage với quyền xóa phiên bản bị giới hạn.

Tên gọi và semantics khác nhau giữa sản phẩm. Cần kiểm tra **ai có thể bypass, rút ngắn hoặc thay retention**, thời điểm lock bắt đầu, và quyền xóa sau khi hết retention.

### 6.2. WORM không tự chứng minh dữ liệu đúng

Một attacker có thể đưa **backup đã bị mã hóa độc hại hoặc dữ liệu đã bị sửa** vào kho immutable. WORM giữ nguyên bản sao đó rất tốt, nhưng nó cũng có thể giữ nguyên **bản sao sai**.

Vì vậy cần:

- Backup manifest và checksum.
- Xác thực nguồn backup và job identity.
- Chữ ký manifest từ một signer được bảo vệ độc lập.
- Versioning và chain-of-custody.
- Kiểm thử restore và xác minh dữ liệu sau restore.

### 6.3. Offline backup

Bản offline có thể là media hoặc kho không được kết nối thường xuyên với production network. Nó giảm nguy cơ ransomware lan truyền qua credential/network, nhưng cần:

- Quản lý media, serial, vị trí và người giữ.
- Mã hóa media và bảo vệ key phục hồi.
- Quy trình đưa media ra/vào vùng cách ly.
- Quét malware và xác minh integrity trước khi restore.
- Kiểm tra tuổi thọ vật lý, format và thiết bị đọc.
- Diễn tập khôi phục khi người giữ chính vắng mặt.

### 6.4. Kết hợp nhiều lớp

~~~text
Copy A: production snapshot — phục vụ khôi phục nhanh
Copy B: immutable backup account — chống xóa/sửa trái phép
Copy C: offline or isolated media — giảm ảnh hưởng ransomware diện rộng
Evidence: manifest, signature, audit và restore test — xác minh nguồn gốc
~~~

Không phải hệ thống nào cũng cần ba bản theo cùng cách; số lượng và vị trí phải dựa trên RPO/RTO, giá trị dữ liệu, threat model và yêu cầu lưu trữ.

## 7. Quy tắc 3-2-1 và cách áp dụng cho backup khóa

Quy tắc **3-2-1** thường được diễn giải:

- Có ít nhất **3 bản dữ liệu** (tính cả bản production).
- Lưu trên ít nhất **2 loại phương tiện hoặc miền lưu trữ khác nhau**.
- Có ít nhất **1 bản offsite**.

Với key management, không nên áp dụng máy móc như thể **mọi raw key đều phải có ba bản export**. Điều cần sao lưu là **những tài sản có thể khôi phục hợp lệ**, theo cơ chế an toàn của key type.

### Bản mở rộng thường được dùng

Một số tổ chức thêm:

- **1 immutable copy**.
- **1 offline/air-gapped copy**.
- Kiểm thử restore định kỳ.

Đây là cách tăng khả năng chống ransomware, không phải một chuẩn bắt buộc áp dụng giống nhau cho mọi tổ chức.

### 3-2-1 cho từng nhóm tài sản

| Tài sản | Ví dụ cách triển khai |
| --- | --- |
| Database/ciphertext | Snapshot, immutable object backup, offsite copy |
| Wrapped DEK | Backup cùng dữ liệu và metadata, bảo vệ integrity |
| HSM backup set | Secure backup theo vendor, bản lưu ở vị trí độc lập |
| KMS metadata/policy | Export cấu hình và event references; material theo provider semantics |
| Public certificates/JWKS history | Archive có integrity và provenance |
| Recovery shares | Lưu riêng, phân tán custodian, kiểm kê và quorum |
| Audit/manifest | Append-only/WORM và bản lưu độc lập |

**Không tạo thêm bản sao raw secret vượt policy** chỉ để đạt con số 3-2-1.

## 8. Backup encryption: khóa bảo vệ bản backup phải được quản lý ra sao?

Backup thường chứa dữ liệu nhạy cảm và có thể tồn tại lâu hơn dữ liệu production. Cần bảo vệ cả **confidentiality, integrity và khả năng phục hồi**.

### 8.1. Mã hóa backup

Có thể dùng envelope encryption:

~~~text
backup plaintext stream
    -- AEAD with backup DEK -->
backup ciphertext
    -- wrap backup DEK with backup KEK -->
wrapped backup DEK
~~~

Trong đó:

- **Backup DEK** mã hóa một backup set hoặc segment theo thiết kế.
- **Backup KEK** bảo vệ backup DEK.
- Key ID/version, nonce, tag, AAD và manifest được lưu kèm.
- Backup KEK được bảo vệ trong một trust domain có khả năng phục hồi độc lập.

### 8.2. Không tạo circular dependency

Một lỗi nguy hiểm là:

~~~text
Muốn đọc backup cần backup KEK.
Muốn khôi phục backup KEK lại cần production KMS.
Production KMS đang là hệ thống bị mất.
=> Không thể phục hồi.
~~~

Nếu backup nhằm khôi phục sau khi production KMS gặp sự cố, **không để toàn bộ khả năng mở backup phụ thuộc duy nhất vào chính KMS đó**. Thiết kế một recovery path được phê duyệt, ví dụ HSM backup domain độc lập, backup KEK được bảo vệ riêng hoặc cơ chế provider-supported recovery.

### 8.3. Không dùng một KEK chung tùy tiện

Backup KEK có thể có blast radius lớn. Cần quyết định:

- Per backup domain, service, dataset hay environment?
- Ai được `Wrap/Unwrap`?
- Có non-exportable hoặc hardware protection không?
- Có quorum cho restore?
- Backup KEK rotation ảnh hưởng bao nhiêu bản backup?
- Nếu backup KEK bị compromise thì phải rewrap hay re-encrypt backup?

### 8.4. Tách quyền production và recovery

Production workload có thể được phép **ghi backup stream vào ingest endpoint**, nhưng không được đọc/xóa mọi backup đã lưu. Recovery operator có thể được phép **đọc một backup set sau approval**, nhưng không mặc nhiên được quyền sửa production KMS policy.

## 9. Backup và recovery của HSM

HSM có thể có cơ chế **secure backup/restore** riêng, khác với việc copy file keystore.

### Cần hiểu trước khi triển khai

- Key object có được phép backup không?
- Backup được mã hóa/bảo vệ bởi **backup key, cloning domain, partition hoặc quorum secret** nào?
- Backup có chứa key attributes và metadata không?
- Restore sang thiết bị/partition/model/firmware nào được hỗ trợ?
- Có yêu cầu số lượng HSM, security officer hoặc M-of-N?
- Backup set có phụ thuộc serial, firmware, vendor license hoặc domain cụ thể?
- Restore có giữ được `CKA_SENSITIVE`, `CKA_EXTRACTABLE`, `CKA_SIGN`, `CKA_DECRYPT` và các attributes khác không?
- Có thể xác minh key identity sau restore bằng key check value/fingerprint hoặc test operation không?

### HSM backup không đồng nghĩa export raw key

Một backup format có thể giữ key material trong **dạng bảo vệ của vendor/HSM domain**, không cho người vận hành xem raw bytes. Đó thường là đặc tính cần giữ.

### Các lỗi phổ biến

1. Backup file có nhưng mất **backup domain key**.
2. Có backup domain nhưng không còn đủ quorum custodian.
3. Restore sang thiết bị không tương thích.
4. Key object phục hồi nhưng **attributes/policy khác** bản gốc.
5. Restore xong không biết key có đúng material/version cần thiết.
6. Chỉ backup HSM nhưng thiếu certificate, key labels, inventory và ứng dụng sử dụng.
7. Một HSM admin có thể tự xóa backup lẫn key production.
8. Chưa từng thử restore trên thiết bị dự phòng.

**Chỉ coi HSM backup là có giá trị khi đã kiểm thử restore và xác minh semantics trên model/firmware thực tế.**

## 10. KMS managed service: replication khác backup độc lập

Nhiều managed KMS quản lý key material trong hạ tầng của nhà cung cấp. Khách hàng có thể có các tính năng như:

- Regional/multi-region key replication.
- Automatic durability và high availability.
- Key version/rotation.
- Import/export hoặc external key store theo loại key.
- Backup/restore hoặc recovery workflow riêng tùy sản phẩm.

**Không phải dịch vụ KMS nào cũng cho export hoặc backup raw key material.** Với một số key, provider quản lý durability; trách nhiệm của khách hàng là backup **metadata, policy, grants, aliases, dependency mapping, ciphertext và recovery configuration** theo đúng semantics dịch vụ.

### Replication có thể chia sẻ cùng control plane

Một key replica ở region khác giúp chống một số sự cố vùng địa lý, nhưng có thể vẫn bị ảnh hưởng bởi:

- Tài khoản quản trị bị chiếm.
- Policy hoặc grant bị sửa.
- Xóa key/replica theo quyền chung.
- Organization-level policy bị thay.
- Billing/tenant suspension hoặc lỗi nhà cung cấp.
- Misconfiguration đồng bộ sang nhiều region.

### Thiết kế cần hỏi

1. Key có **multi-region replication** hay chỉ có key độc lập ở region khác?
2. Xóa primary ảnh hưởng replica thế nào?
3. Ai được phép disable, schedule deletion hoặc change policy?
4. Có deletion protection/retention/approval nào?
5. Nếu account/IdP production mất, recovery team còn truy cập KMS không?
6. Có cách tái tạo **metadata, IAM và dependency map** khi resource không thể khôi phục?
7. Backup data được mã hóa bởi key nào và có đường giải mã khi KMS production không khả dụng?

**Đừng gọi replication là backup độc lập nếu quyền và failure domain vẫn chung.**

## 11. Bảo vệ metadata và mapping dữ liệu–khóa

Một bản backup ciphertext cần metadata để tìm đúng key và tái tạo cách giải mã.

### Metadata nên có

| Trường | Lý do cần |
| --- | --- |
| `backupSetId` | Nhận diện một tập backup |
| `sourceSystem` / environment | Xác định nguồn và trust domain |
| `createdAtUtc` | Xác định thời điểm snapshot |
| `dataVersion` / transaction watermark | Khôi phục đúng điểm dữ liệu |
| `keyId` / `materialVersion` | Chọn đúng key version |
| `keyPurpose` / algorithm | Không dùng nhầm key |
| `wrappedDekReference` | Tìm bản DEK được bọc |
| `nonce` / `tag` / AAD profile | Thực hiện authenticated decryption |
| `schemaVersion` | Giải mã và parse đúng format |
| `manifestDigest` | Kiểm tra toàn vẹn |
| `manifestSignatureRef` | Xác minh nguồn backup |
| `retentionUntil` / legal hold | Không xóa sớm |
| `restoreDependencyRefs` | Biết thứ tự phục hồi |

### Metadata có thể bị attacker sửa để gây mất dữ liệu

Ví dụ attacker thay `keyId` từ `billing-dek-v3` sang `test-key-v1`, hoặc sửa AAD/tenant ID. Kết quả có thể là giải mã thất bại hoặc tệ hơn là dữ liệu được định tuyến sai nếu ứng dụng thiết kế thiếu kiểm tra.

Cần **manifest có integrity**, metadata có version và restore tool kiểm tra **key purpose, tenant, source và schema** trước khi giải mã.

### Không đưa raw secret vào manifest

Manifest chỉ nên tham chiếu key ID/version và wrapped material theo chính sách. Không ghi raw DEK/KEK, private key, HSM PIN hay password phục hồi.

## 12. Integrity và authenticity của backup

**Checksum** giúp phát hiện dữ liệu thay đổi ngoài ý muốn; **chữ ký số hoặc MAC** có thể xác thực nguồn gốc manifest theo mô hình trust đã chọn.

### Phân biệt

| Cơ chế | Có thể phát hiện | Không tự chứng minh |
| --- | --- | --- |
| CRC/checksum đơn giản | Lỗi truyền tải/ngẫu nhiên | Attacker không thể sửa cả dữ liệu và checksum |
| SHA-256 digest | Bytes khác manifest | Ai đã tạo manifest |
| HMAC | Manifest được tạo bởi bên biết shared secret | Danh tính cá nhân nếu nhiều bên cùng biết key |
| Digital signature | Manifest được ký bởi private key tương ứng | Signer có phê duyệt backup hay không |
| Immutable storage | Bản đã ghi không bị thay trong điều kiện lock | Bản ban đầu đúng hoặc không độc hại |
| Trusted timestamp | Bằng chứng thời gian cho đối tượng được đóng dấu | Nguồn dữ liệu hợp lệ về nghiệp vụ |

### Một manifest backup có thể chứa

~~~yaml
schemaVersion: "1"
backupSetId: "billing-prod-2030-05-12T0100Z"
source:
  system: "billing"
  environment: "production"
  accountRef: "prod-account-ref"
createdAtUtc: "2030-05-12T01:00:00Z"
content:
  objectCount: 12840
  totalBytes: 845000000
  archiveDigest:
    algorithm: "SHA-256"
    value: "example-digest-reference"
encryption:
  algorithm: "AES-256-GCM"
  backupKeyId: "backup-kek-v4"
  wrappedDekReference: "wrapped-dek-object-ref"
  aadProfile: "backup-envelope/v1"
dependencies:
  keyMetadataSnapshot: "key-inventory-snapshot-ref"
  policySnapshot: "policy-revision-ref"
  transactionWatermark: "db-lsn-reference"
retention:
  immutableUntilUtc: "2030-08-10T00:00:00Z"
evidence:
  signatureReference: "backup-manifest-signature-ref"
~~~

**Đây là cấu trúc minh họa**, không phải schema provider chung. Digest và signature bytes cần được lưu/đối chiếu theo định dạng canonical được định nghĩa rõ.

### Vì sao cần chữ ký manifest độc lập?

Nếu attacker có thể sửa archive và manifest cùng lúc, SHA-256 digest mới có thể vẫn khớp. Một chữ ký từ **backup manifest signing key** được bảo vệ trong trust domain độc lập giúp phát hiện thay đổi do người không có signing authority.

Nhưng nếu chính signing key hoặc signing API bị chiếm, chữ ký cũng có thể bị giả. Do đó cần **approval, provenance, audit và separation of duties**.

## 13. Backup signing key cũng cần recovery plan

Nếu manifest được ký bằng một signing key, cần xác định:

- Key đó có cùng trust domain với production signing key không?
- Ai được ký manifest và nội dung nào được ký?
- Private key có non-exportable trong HSM không?
- Public verification key/certificate được archive ở đâu?
- Nếu backup signing key bị compromise thì xác minh backup lịch sử thế nào?
- Có timestamp/evidence archive không?
- Có quy trình thay signing key mà vẫn verify manifest cũ không?

**Không dùng production release-signing key để ký backup manifest chỉ vì nó đã có sẵn.** Purpose khác nhau, blast radius và quy trình phê duyệt khác nhau.

## 14. Tách quyền ghi, đọc, xóa và restore

Backup storage cần phân quyền theo **operation**, không cấp một role “backup-admin” có toàn quyền cho mọi tác vụ.

| Vai trò | Quyền phù hợp | Quyền nên tách |
| --- | --- | --- |
| **Production backup writer** | Gửi backup vào ingest path, theo source identity | Không đọc/xóa/đổi retention backup đã lưu |
| **Backup storage service** | Ghi object, enforce retention và versioning | Không quản trị production key |
| **Backup custodian** | Quản lý storage policy, lifecycle theo approval | Không tự duyệt restore nhạy cảm |
| **Recovery operator** | Đọc backup set đã phê duyệt, restore vào quarantine | Không sửa immutable retention |
| **Security approver** | Duyệt break-glass, key recovery và scope | Không trực tiếp sửa/xóa bằng chứng |
| **Auditor** | Đọc audit và kiểm tra evidence | Không sửa backup/log |
| **Production administrator** | Quản trị production | Không có quyền xóa bản sao độc lập |

### Ma trận thao tác

~~~text
Production writer:
    PutBackup      = ALLOW (restricted ingest)
    ListAllBackups = DENY
    ReadBackup     = DENY
    DeleteBackup   = DENY
    ChangeRetention= DENY
    Restore        = DENY

Recovery operator:
    ReadApprovedSet= ALLOW (time-bound)
    RestoreToQuarantine = ALLOW
    DeleteBackup   = DENY
    ChangeRetention= DENY

Independent approvers:
    ApproveRestore = ALLOW (separate identities)
    RawKeyExport   = DENY by default
~~~

Đây là ma trận logic. Cú pháp IAM, object lock bypass và quyền root/admin tùy sản phẩm. Cần kiểm thử **direct API, role assumption, service account và break-glass**.

### Dual control và quorum

Với recovery material rủi ro cao, có thể yêu cầu **M-of-N approval**, split knowledge hoặc hai custodian độc lập. Không cần hai người duyệt từng object backup thông thường; quorum phù hợp hơn với **restore root key, mở backup domain, export/import private key hoặc khôi phục dữ liệu nhạy cảm quy mô lớn**.

## 15. Identity và credential cho backup domain

Một account riêng nhưng sử dụng lại cùng **production admin credential** có thể mất ý nghĩa độc lập.

### Khuyến nghị

- Tạo **backup workload identity** riêng cho ingest.
- Không lưu backup admin credential trong production secret store.
- Không cho production workload tự assume backup custodian role.
- Recovery identity có MFA/strong authentication và time-bound elevation.
- Tách quyền tạo, phê duyệt, thực hiện restore và xóa.
- Break-glass credential được giữ offline hoặc trong vault riêng, kiểm kê và thử nghiệm.
- Alert khi backup policy, retention, lock hoặc audit config thay đổi.
- Định kỳ rà soát trust relationship giữa hai account.
- Có quy trình thay credential sau incident.

### Đừng tạo dependency một chiều không thể phục hồi

Nếu backup account chỉ đăng nhập qua **IdP production**, khi production IdP bị compromise hoặc outage, recovery team có thể mất quyền. Cần phương án identity recovery được thiết kế, kiểm soát độc lập và diễn tập; tránh tạo tài khoản local không quản lý hoặc backdoor không audit.

## 16. Network isolation và luồng ingest

### Luồng ghi backup nên tối giản

~~~mermaid
flowchart TD
    P[Production backup agent] -->|Authenticated push| I[Restricted ingest endpoint]
    I --> V[Validate source identity and manifest]
    V --> S[Write-only staging]
    S --> C[Content and malware checks]
    C --> L[Immutable retention lock]
    L --> A[Independent audit]
    A --> R[Recovery catalog]
    R --> Q[Approved restore workflow]
~~~

### Thiết kế luồng

1. Production agent chỉ được kết nối **một endpoint ingest** cần thiết.
2. Endpoint xác thực source, backup set, time window và manifest.
3. Ghi vào vùng staging với quyền hẹp.
4. Xác minh checksum/signature, format, size, object count và policy.
5. Chỉ sau khi validation đạt mới đưa vào **immutable retention**.
6. Tách quyền ingest khỏi quyền list/read/delete.
7. Restore đi qua **network/quarantine riêng**, không kết nối trực tiếp production ngay.
8. Audit cả allow/deny, source identity, destination, backup ID và retention.

### Chống backup poisoning

Attacker có thể chiếm production rồi gửi backup đã bị sửa nhưng vẫn đúng checksum do chính attacker tạo. Cần so sánh với:

- Snapshot/transaction watermark đã được xác nhận.
- Application-level consistency checks.
- Independent business controls hoặc source-of-truth.
- Nhiều restore points theo thời gian.
- Malware scanning trong vùng quarantine.
- Chữ ký/approval của backup pipeline độc lập.

**Integrity của bytes không đồng nghĩa integrity của nội dung nghiệp vụ.**

## 17. Retention, RPO và RTO

Backup storage độc lập phải đáp ứng cả **thời gian lưu** và **khả năng phục hồi thực tế**.

### Khái niệm

- **RPO (Recovery Point Objective):** mức mất dữ liệu tối đa theo thời gian mà nghiệp vụ chấp nhận.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ.
- **Retention:** thời gian giữ backup/evidence.
- **Legal hold:** yêu cầu giữ lại tài sản trong thời gian điều tra/tranh chấp.
- **Cryptoperiod:** khoảng thời gian key được phép dùng cho operation đã định; không đồng nghĩa retention của ciphertext hoặc key backup.

### Ví dụ mục tiêu

| Nhóm dữ liệu | RPO ví dụ | RTO ví dụ | Lưu ý |
| --- | --- | --- | --- |
| Metadata KMS/policy | 1 giờ | 4 giờ | Cần snapshot mỗi khi thay đổi trọng yếu |
| Key inventory/lineage | 1 giờ | 4 giờ | Giữ history, không chỉ trạng thái hiện tại |
| Database ciphertext | 15 phút | 8 giờ | Phụ thuộc transaction log và volume |
| HSM secure backup | Theo change/key ceremony | 1 ngày | Phải kiểm thử restore trên thiết bị tương thích |
| Public cert/JWKS history | 1 ngày hoặc theo change | 4 giờ | Cần cho verify lịch sử |
| Recovery evidence/audit | Theo policy | 1 ngày | Bảo vệ integrity và retention |

**Các số trên chỉ là ví dụ**, không phải SLA chung. RPO/RTO cần được owner phê duyệt theo business impact và kiểm chứng bằng drill.

### Retention của key và dữ liệu không giống nhau

Một ciphertext có thể cần lưu 10 năm trong khi DEK không còn được dùng để encrypt mới sau 1 năm. Tuy vậy, **key cũ hoặc khả năng khôi phục key cũ có thể vẫn cần thiết** để đọc archive trong thời hạn retention.

Không hủy key chỉ vì **cryptoperiod tạo dữ liệu mới đã kết thúc**. Cần xét data retention, backup, legal hold và restore dependencies.

## 18. Catalog và inventory cho backup

Không thể restore có kiểm soát nếu không biết **backup set nào chứa gì, phụ thuộc key nào và bản nào đã được kiểm tra**.

### Catalog nên ghi

- Backup set ID, source system, environment, region và thời gian tạo.
- Loại dữ liệu: ciphertext, wrapped DEK, key metadata, HSM backup set, public trust.
- Digest/checksum, manifest signature reference và validation status.
- Key ID/version/purpose, wrapping key version và key lineage.
- Storage account/bucket/media ID và immutability retention.
- Transaction watermark, snapshot ID, database/schema version.
- Restore prerequisites, software/firmware compatibility.
- Custodian, approver, restore history và test result.
- Legal hold, expiry và destruction approval.

### Không chỉ lưu catalog trong production

Nếu catalog là cơ sở duy nhất để tìm backup nhưng production admin có thể xóa catalog, bản backup có thể còn nguyên nhưng **không thể định vị hoặc hiểu cách phục hồi**.

Lưu catalog snapshot trong **backup domain hoặc evidence vault độc lập**, có integrity và version history. Catalog cũng phải được restore test.

## 19. Backup KDF, HSM recovery shares và split knowledge

Một số hệ thống dùng **master key, seed hoặc recovery shares** để khôi phục key hierarchy.

### Split knowledge

Split knowledge là cách chia bí mật hoặc thông tin cần thiết để không một người giữ toàn bộ. Ví dụ, một recovery process yêu cầu **3 trong 5 custodian shares**.

### M-of-N quorum

Quorum có thể kiểm soát:

- Restore HSM backup domain.
- Mở partition/root KEK recovery.
- Khôi phục CA signing key.
- Import private key có ảnh hưởng rộng.
- Thực hiện break-glass decrypt.

### Những điều cần quản lý

1. Share có định danh, version và inventory; không để lẫn bản cũ/mới.
2. Custodian khác nhau, không cùng kiểm soát mọi share.
3. Mỗi share lưu trong **vùng bảo vệ độc lập**, có niêm phong và kiểm kê.
4. Quy trình thay người giữ, mất share, suspected compromise và revoke.
5. Thử quorum định kỳ bằng **test material**.
6. Không chụp ảnh/scan share vào ticket hoặc cloud drive không được duyệt.
7. Backup shares cũng cần backup/DR, nhưng phải tránh sao chép làm mất split knowledge.
8. Ghi audit người tham gia, mục đích, thời gian và kết quả.

### Không phải mọi HSM dùng cùng cơ chế

Một số thiết bị có M-of-N activation, một số dùng backup domain key, quorum token hoặc quy trình vendor-specific. Không áp dụng thuật ngữ split knowledge như thể đó là một API chuẩn chung.

## 20. Restore order: phục hồi theo dependency graph

Một bản database backup có thể không giải mã được nếu key hierarchy, metadata và trust chưa sẵn sàng.

~~~mermaid
flowchart TD
    I[Incident containment and clean recovery environment] --> A[Restore identity and admin access]
    A --> E[Restore audit and evidence catalog]
    E --> M[Restore key metadata and policy]
    M --> H[Recover HSM/KMS/key backup domain]
    H --> T[Verify key identity and permitted operations]
    T --> D[Restore ciphertext, wrapped DEKs and database]
    D --> V[Validate manifest, AEAD tags and data consistency]
    V --> Q[Quarantine application and test reads]
    Q --> P[Approve controlled production cutover]
~~~

### Thứ tự có thể thay đổi

Đây là dependency mẫu. Nếu provider KMS còn hoạt động và chỉ database bị mất, không cần restore KMS. Nếu HSM bị sự cố, cần khôi phục **HSM backup domain và quorum** trước khi giải mã. Nếu IdP production bị compromise, phải thiết lập identity recovery độc lập trước.

### Không đưa dữ liệu chưa xác minh thẳng vào production

Restore vào **quarantine/staging**:

- Xác minh manifest/signature.
- Kiểm tra key IDs và purpose.
- Test decrypt/verify với test record hoặc sample đã được phê duyệt.
- Kiểm tra schema và transaction consistency.
- Quét malware/IOC nếu có sự cố ransomware.
- Xác nhận không có policy hoặc startup script bị cài cắm.
- Chỉ cutover sau approval.

## 21. Integrity check: checksum, signature và test decrypt

### Ba tầng kiểm tra

1. **Storage integrity:** bytes backup có khớp digest/manifest không?
2. **Cryptographic integrity:** wrapped key và AEAD ciphertext có xác minh được không?
3. **Application consistency:** dữ liệu sau restore có đúng schema, quan hệ và business invariants không?

### Không dùng checksum đơn lẻ như bằng chứng authenticity

Nếu archive và checksum cùng được ghi vào một nơi mà attacker sửa được, họ có thể tính checksum mới. Cần manifest được **ký bởi backup signing key** trong trust domain độc lập hoặc cơ chế authenticity tương đương.

### Test decrypt

Với ciphertext AEAD:

- Chọn sample có metadata, AAD và key version rõ.
- Thực hiện decrypt trong boundary được phê duyệt.
- Xác minh tag trước khi sử dụng plaintext.
- So sánh digest/business invariant với dữ liệu tham chiếu tin cậy.
- Không đưa plaintext hoặc DEK vào log.

**Không chỉ test rằng API trả `SUCCESS`**. Phải xác nhận đúng record, đúng tenant, đúng key version và dữ liệu sau giải mã có ý nghĩa.

## 22. Java 11+: kiểm tra digest archive và chữ ký manifest

Ví dụ sau minh họa một phần bước xác minh trước restore:

- Đọc archive theo stream, không tải toàn bộ file vào RAM.
- Tính SHA-256 và so sánh với digest trong **manifest đã xác minh chữ ký**.
- Xác minh chữ ký detached của manifest bằng public key lấy từ **trust store độc lập**.
- Không chứa private key, raw DEK hoặc thông tin đăng nhập.
- Tách kiểm tra manifest signature khỏi kiểm tra archive digest.

**Ví dụ không triển khai PKI path validation, TSA, object lock, HSM hoặc parser manifest canonical.** Production phải xác minh certificate/trust chain và định dạng manifest theo chuẩn đã chọn.

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Signature;
import java.util.Arrays;

public final class BackupManifestVerifierDemo {

    static byte[] sha256(Path archive) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] buffer = new byte[64 * 1024];

        try (InputStream in = Files.newInputStream(archive)) {
            int read;
            while ((read = in.read(buffer)) != -1) {
                digest.update(buffer, 0, read);
            }
        } finally {
            Arrays.fill(buffer, (byte) 0);
        }
        return digest.digest();
    }

    static boolean verifyManifestSignature(
            PublicKey trustedBackupSigner,
            byte[] exactManifestBytes,
            byte[] detachedSignature) throws Exception {

        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(trustedBackupSigner);
        verifier.update(exactManifestBytes);
        return verifier.verify(detachedSignature);
    }

    static boolean verifyArchiveDigest(
            Path archive, byte[] expectedSha256) throws Exception {

        byte[] actual = sha256(archive);
        try {
            return MessageDigest.isEqual(actual, expectedSha256);
        } finally {
            Arrays.fill(actual, (byte) 0);
        }
    }

    static byte[] signManifest(PrivateKey testKey, byte[] manifest)
            throws Exception {
        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(testKey, new SecureRandom());
        signer.update(manifest);
        return signer.sign();
    }

    static String toHex(byte[] bytes) {
        StringBuilder result = new StringBuilder(bytes.length * 2);
        for (byte value : bytes) {
            result.append(String.format("%02x", value & 0xff));
        }
        return result.toString();
    }

    static byte[] fromHex(String hex) {
        if (hex == null || (hex.length() & 1) != 0) {
            throw new IllegalArgumentException("Invalid hex digest");
        }
        byte[] result = new byte[hex.length() / 2];
        for (int i = 0; i < result.length; i++) {
            int high = Character.digit(hex.charAt(i * 2), 16);
            int low = Character.digit(hex.charAt(i * 2 + 1), 16);
            if (high < 0 || low < 0) {
                throw new IllegalArgumentException("Invalid hex digest");
            }
            result[i] = (byte) ((high << 4) | low);
        }
        return result;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: BackupManifestVerifierDemo <archive-path>");
        }

        Path archive = Path.of(args[0]);

        // Demo tự sinh signer tạm để minh họa luồng ký/verify.
        // Production phải lấy public key từ trust store độc lập đã xác minh,
        // không lấy trust anchor chưa xác minh từ chính backup archive.
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(3072, new SecureRandom());
        KeyPair testSigner = generator.generateKeyPair();

        byte[] archiveDigest = sha256(archive);
        String digestHex = toHex(archiveDigest);
        byte[] manifestBytes = (
                "schemaVersion=1\n"
                + "backupSetId=demo-backup\n"
                + "archiveSha256=" + digestHex + "\n")
                .getBytes(StandardCharsets.UTF_8);
        byte[] manifestSignature = signManifest(
                testSigner.getPrivate(), manifestBytes);

        boolean signatureValid = verifyManifestSignature(
                testSigner.getPublic(), manifestBytes, manifestSignature);

        if (!signatureValid) {
            throw new SecurityException("Manifest signature invalid");
        }

        byte[] expectedArchiveDigest = fromHex(digestHex);
        boolean archiveValid;
        try {
            archiveValid = verifyArchiveDigest(
                    archive, expectedArchiveDigest);
        } finally {
            Arrays.fill(expectedArchiveDigest, (byte) 0);
            Arrays.fill(archiveDigest, (byte) 0);
        }

        if (!archiveValid) {
            throw new SecurityException("Archive digest mismatch");
        }

        System.out.println("Manifest signature: VALID");
        System.out.println("Archive digest: MATCH");
        System.out.println("Restore gate: READY FOR FURTHER VALIDATION");

        // Thử phát hiện manifest bị sửa sau khi ký.
        byte[] tampered = Arrays.copyOf(
                manifestBytes, manifestBytes.length + 1);
        tampered[tampered.length - 1] = (byte) '!';
        boolean tamperedAccepted = verifyManifestSignature(
                testSigner.getPublic(), tampered, manifestSignature);
        System.out.println("Tampered manifest accepted: "
                + tamperedAccepted);

        // READY không có nghĩa được tự động restore production.
        // Cần kiểm tra retention, key dependencies, malware,
        // AEAD integrity, transaction consistency và approval.
    }

}
~~~

### Demo khác gì production?

Demo tự sinh một cặp RSA tạm để có thể chạy độc lập và kiểm tra luồng ký/verify. Trong production, **không dùng cặp khóa vừa sinh cùng process để tự xác thực chính nó**: public key/certificate phải đến từ trust store độc lập, có xác minh chain, purpose, trạng thái và policy. Nếu tự động lấy public key từ chính archive chưa xác minh, attacker có thể thay cả manifest lẫn public key để tạo một bộ khớp giả.

### Những giới hạn cần hiểu

- SHA-256 xác nhận **bytes khớp digest**, không chứng minh ai tạo archive.
- Chữ ký xác thực manifest theo public key, nhưng cần **xác minh certificate/trust và quyền signer**.
- Mẫu manifest trong demo dùng encoding cố định và đơn giản; production cần canonical format có version, length/escaping rõ ràng và parser được kiểm thử.
- `Arrays.fill` chỉ là best effort; buffer không chứa raw key nhưng vẫn được xóa sau khi đọc.
- Không có logic tự động restore hoặc import key vào KMS/HSM.
- Không coi `READY FOR FURTHER VALIDATION` là phê duyệt production restore.

## 23. Recovery test và restore drill

**Backup chưa từng restore thử chỉ là một giả định về khả năng phục hồi.**

### Các cấp độ kiểm thử

| Cấp | Bài test | Mục tiêu |
| --- | --- | --- |
| **Level 1 — Inventory** | Kiểm tra backup set, manifest, retention và key refs | Có thể tìm đúng bản |
| **Level 2 — Integrity** | Verify digest/signature và object versions | Phát hiện bản bị sửa |
| **Level 3 — Key recovery** | Restore test key/HSM backup vào thiết bị thử | Kiểm tra cơ chế key backup |
| **Level 4 — Data recovery** | Restore ciphertext và decrypt sample | Xác minh key/data dependencies |
| **Level 5 — Application recovery** | Khởi động app trong quarantine | Kiểm tra schema và business flow |
| **Level 6 — Full DR** | Diễn tập mất production account/region/IdP | Chứng minh independence và RTO/RPO |

### Kịch bản phải thử

- Mất toàn bộ production account.
- Production IdP hoặc credential bị compromise.
- KMS primary unavailable hoặc key bị disable.
- HSM primary bị hỏng hoặc mất partition.
- Ransomware xóa production và cố xóa backup.
- Backup writer gửi dữ liệu bị hỏng.
- Backup KEK/recovery share thiếu một custodian.
- Restore phải dùng key version cũ để đọc archive.
- Backup metadata bị thiếu hoặc sai.
- Một backup copy không có integrity evidence.

### Đo lường

- Thời gian phát hiện backup không hợp lệ.
- Thời gian cấp quyền recovery có approval.
- Thời gian khôi phục key và metadata.
- Thời gian restore ciphertext và kiểm tra AEAD.
- Tỷ lệ backup set restore thành công.
- Mức chênh RPO thực tế so với mục tiêu.
- Số bước phụ thuộc một người hoặc một credential.
- Khả năng hoàn tất khi production IdP/admin không dùng được.

## 24. Ransomware và backup poisoning

### Ransomware

Attacker có thể mã hóa/xóa production và tìm backup thông qua:

- Credential dùng chung.
- Network mount hoặc backup agent chạy quyền cao.
- Backup admin token lưu trong production.
- API xóa snapshot/object versions.
- Tắt retention/immutability trước khi xóa.
- Sửa backup catalog để làm mất khả năng tìm bản tốt.

**Immutable/offline copy** làm tăng chi phí và độ khó của hành vi này, nhưng không thay thế kiểm soát identity, retention và restore tests.

### Backup poisoning

Một bản backup có thể được tạo sau khi attacker đã sửa dữ liệu hoặc cài persistence. Nếu chỉ giữ bản mới nhất, kho immutable có thể lưu lâu dài **một trạng thái đã bị xâm nhập**.

Biện pháp:

- Giữ nhiều restore points theo thời gian.
- Xác định **earliest plausible compromise** và backup trước thời điểm đó.
- Kiểm tra malware/IOC và application invariants.
- Dùng transaction watermark và source-of-truth độc lập.
- Quarantine trước restore.
- Không tự động chọn bản mới nhất chỉ vì timestamp mới nhất.

### Clean recovery

Khi nghi production bị compromise, dựng môi trường phục hồi sạch, kiểm tra image/config/dependencies và credential trước khi kết nối lại production. Restore database sạch nhưng chạy ứng dụng hoặc startup script bị cài cắm có thể tái nhiễm.

## 25. Recovery key custody và break-glass

Độc lập storage không hữu ích nếu khi cần restore, không ai có quyền hoặc không ai biết cách mở backup.

### Break-glass cần được thiết kế trước

- Có **recovery role** được cấp quyền tối thiểu và có thời hạn.
- MFA hoặc cơ chế xác thực mạnh.
- Approval độc lập theo scope.
- Quorum cho root key/HSM recovery khi cần.
- Credential được giữ tách khỏi production.
- Mọi lần sử dụng tạo audit ở miền độc lập.
- Sau recovery, thu hồi elevated credentials và rà soát mọi thao tác.
- Không để một cá nhân duy nhất nắm cả backup, key recovery và log deletion.

### Cần tránh

1. Recovery password chỉ lưu trong password manager production.
2. HSM backup key chỉ có một người giữ.
3. Quorum shares được cất cùng một két hoặc cùng một cloud drive.
4. Break-glass account không bao giờ được thử và đã hết hạn.
5. Admin restore có quyền xóa backup evidence.
6. Restore tool dùng mặc định production credential bị nghi compromise.
7. Quy trình yêu cầu email approval từ hệ thống email đang mất.

**Break-glass là một đường phục hồi được kiểm soát**, không phải tài khoản superuser không audit.

## 26. Retention và destruction của backup

Backup phải có vòng đời rõ ràng:

~~~text
Created
  -> Validated
  -> Immutable / Retained
  -> Eligible for restore
  -> Retention expired or legal hold released
  -> Approved destruction
  -> Destruction evidence archived
~~~

### Điều kiện trước khi xóa

- Retention period đã hết.
- Không còn legal hold, investigation hoặc regulatory hold.
- Có bản thay thế đã được xác minh nếu policy yêu cầu.
- Không còn dependency của ciphertext/archive vào key backup set sắp xóa.
- Quorum/approval độc lập đã hoàn tất.
- Xác định mọi replica, version, offline media và catalog reference.
- Có bằng chứng destruction phù hợp với provider/media.

### Crypto-erasure

Một số thiết kế dùng **hủy key mã hóa backup** để khiến ciphertext không thể giải mã. Cần hiểu rõ:

- Còn bản sao key ở HSM backup, escrow, cache hoặc replica không?
- Có backup DEK/KEK khác không?
- Có dữ liệu plaintext hoặc bản backup chưa mã hóa không?
- Key đó có dùng chung cho nhiều backup set không?
- Có legal hold hoặc nghĩa vụ lưu trữ không?

**Crypto-erasure không được tuyên bố thành công chỉ vì xóa một alias hoặc disable một KMS resource.** Cần evidence về key material, replicas, backups và mọi bản sao ngoài hệ thống.

## 27. Case study A — Ransomware chiếm production account

### Bối cảnh

Một hệ thống lưu hóa đơn dưới dạng ciphertext. Database, KMS key, backup bucket và backup job đều nằm trong cùng production account. Attacker chiếm production admin và xóa database, snapshot, backup object; đồng thời schedule deletion KEK.

### Vì sao kiến trúc thất bại?

- Backup storage và production dùng chung admin trust.
- Backup writer có quyền list/delete rộng.
- Không có immutable retention độc lập.
- Key policy và backup catalog cùng miền quản trị.
- Không có offline copy được kiểm thử.

### Thiết kế cải thiện

1. Tạo backup account riêng, identity và administrator độc lập.
2. Production writer chỉ được push vào ingest endpoint.
3. Backup service xác minh manifest rồi ghi immutable storage.
4. Có offline/isolated copy theo risk tier.
5. Lưu key metadata, wrapped DEK và ciphertext dependency map.
6. Bảo vệ recovery key/backup domain bằng HSM/quorum độc lập.
7. Audit và alert về retention change/delete được gửi sang miền khác.
8. Diễn tập restore khi production account không truy cập được.

### Bài học

**Một bản backup khác region nhưng vẫn bị production admin xóa không phải là bản sao độc lập đủ mạnh.**

## 28. Case study B — HSM backup tồn tại nhưng không thể restore

### Bối cảnh

Nhóm vận hành đã tạo file HSM backup và lưu ở kho immutable. Khi HSM chính hỏng, nhóm phát hiện backup được tạo dưới một backup domain mà recovery shares đã thất lạc; thiết bị dự phòng không tương thích firmware.

### Nguyên nhân

- Chỉ xác nhận file backup đã upload.
- Không inventory quorum shares và custodian.
- Không thử restore trên HSM tương thích.
- Không lưu tài liệu firmware/partition mapping.
- Không có người thay thế khi custodian chính vắng mặt.

### Khắc phục

1. Xây dựng HSM backup inventory với backup-set ID, domain, device compatibility và key object references.
2. Quản lý recovery shares theo split knowledge/quorum.
3. Lưu thông tin firmware/partition/config có integrity.
4. Thử restore định kỳ bằng test material và thiết bị dự phòng.
5. Xác minh key identity/attributes sau restore.
6. Diễn tập khi thiếu một custodian theo quorum policy.
7. Lưu kết quả test và owner remediation.

### Bài học

**Backup file tồn tại không đồng nghĩa key có thể khôi phục.** Restore path, quorum và compatibility mới chứng minh được khả năng phục hồi.

## 29. Case study C — Backup ciphertext có nhưng mất KMS metadata

### Bối cảnh

Database snapshot và ciphertext object được lưu trong backup account riêng. Tuy nhiên, key inventory, alias mapping, key policy revision và mapping `wrappedDEK -> keyVersion` chỉ tồn tại trong production database đã mất.

### Hậu quả

- Không biết ciphertext dùng DEK/KEK version nào.
- Alias `current` đã đổi và không phản ánh key lịch sử.
- Một số key đã deactivated nhưng còn cần đọc archive.
- KMS resource có thể vẫn tồn tại nhưng recovery team không biết scope/permission cần thiết.
- Restore tool có nguy cơ thử sai key hoặc dùng nhầm tenant context.

### Khắc phục

- Backup key inventory và metadata snapshot định kỳ.
- Giữ **material version, key purpose, key ID, parent-child lineage và policy revision**.
- Archive public cert/JWKS history và HSM object metadata.
- Lưu mapping ciphertext, wrapped DEK và schema/AAD version.
- Bảo vệ catalog độc lập với production.
- Restore thử toàn bộ dependency graph, không chỉ object data.

### Bài học

**Backup dữ liệu và backup khả năng hiểu/giải mã dữ liệu phải được thiết kế cùng nhau.**

## 30. Những lỗi phổ biến khi thiết kế backup storage độc lập

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đặt bucket khác nhưng cùng admin account | Attacker xóa được cả hai | Tách account và identity |
| Dùng cùng production credential để ghi và xóa backup | Ransomware có quyền phá bản sao | Writer chỉ push/write-only |
| Gọi multi-region replication là backup độc lập | Control plane chung vẫn là điểm lỗi | Tách failure domain và test account loss |
| Chỉ backup ciphertext, không backup metadata | Không biết key version/AAD/schema | Backup dependency catalog |
| Export raw key để backup tùy tiện | Tăng exposure và vi phạm key usage | HSM/KMS supported backup |
| Backup HSM nhưng mất quorum shares | Không thể restore key | Custodian inventory và drill |
| Dùng production KEK làm dependency duy nhất của backup | Circular dependency khi KMS mất | Recovery key path độc lập |
| Dùng backup KEK nhưng không backup/recover nó | Ciphertext backup không mở được | Backup domain key custody |
| Dùng chung backup KEK cho mọi môi trường | Blast radius lớn | Tách backup trust domain |
| WORM nhưng không verify manifest | Lưu bền bản backup bị poison | Signature, digest, provenance |
| Checksum nằm cùng nơi attacker sửa được | Attacker thay cả archive và checksum | Signed manifest độc lập |
| Tin chữ ký manifest mà không kiểm tra signer trust | Key ký có thể bị giả/compromise | Trust chain, approval và audit |
| Backup signer dùng chung release-signing key | Trộn purpose | Signing key riêng cho backup |
| Offline media không được restore test | Có thể hỏng hoặc thiếu thiết bị đọc | Media lifecycle và drill |
| Recovery IdP phụ thuộc production IdP | Mất quyền khi production outage | Identity recovery độc lập |
| Một người giữ mọi recovery shares | Single-person compromise | Split knowledge/M-of-N |
| Retention do production admin sửa được | Xóa backup trước thời hạn | Immutable lock và independent approval |
| Chỉ giữ backup mới nhất | Có thể giữ bản đã bị attacker sửa | Nhiều restore points |
| Restore thẳng vào production | Tái nhiễm malware/persistence | Quarantine và validation |
| Không kiểm tra AEAD tag sau restore | Chấp nhận dữ liệu không xác thực | Verify tag trước khi commit |
| Restore HSM không kiểm tra attributes | Key phục hồi có quyền rộng hơn | Verify usage/non-exportability |
| Xóa key cũ khi ciphertext còn retention | Mất dữ liệu lịch sử | Dependency scan và legal hold |
| Coi disable key là crypto-erasure | Replica/cache/copy có thể còn | Destruction evidence |
| Catalog chỉ ở production | Không tìm được bản backup | Archive catalog độc lập |
| Không thử khi một custodian vắng mặt | Quorum thực tế không đạt | Diễn tập personnel continuity |
| Không log restore approval | Không truy được ai phục hồi | Independent audit |
| Backup ingest cho phép list/read/delete | Production compromise có thể lấy/xóa backup | Separate API permissions |
| Không kiểm tra clock/retention timestamps | Xóa sai hoặc giữ sai thời hạn | Trusted time và policy review |
| Backup writer gửi dữ liệu đã bị sửa | Immutable giữ bản độc hại | Multiple restore points và clean source |
| RPO/RTO chỉ ghi trong tài liệu | Không chứng minh đạt mục tiêu | Đo bằng restore drill |

## 31. Checklist production — Backup storage độc lập

### A. Phân tách trust boundary

1. **Storage account:** Backup nằm trong account/project/subscription độc lập?
2. **Identity:** Production credential không thể tự assume backup custodian role?
3. **Administrators:** Có người quản trị backup độc lập và approval riêng?
4. **IdP:** Nếu production IdP bị compromise/outage, recovery identity còn hoạt động?
5. **Network:** Production chỉ push vào ingest path, không có quyền truy cập rộng?
6. **Region/site:** Có bản sao ngoài failure domain địa lý chính?
7. **Audit:** Log backup và retention change nằm trong miền không bị production admin xóa?
8. **Break-glass:** Có credential/role phục hồi độc lập, MFA và time-bound elevation?

### B. Backup tài sản khóa và dữ liệu

9. **Data backup:** Ciphertext, nonce/tag/AAD, schema và transaction watermark được lưu?
10. **Key material:** Có cơ chế backup/replication phù hợp với từng loại KMS/HSM/key?
11. **No raw export by default:** Không export raw key chỉ để tăng số lượng bản sao?
12. **Metadata:** Key ID/version, purpose, state, policy revision và lineage được backup?
13. **Wrapped DEK:** Mapping wrapped DEK tới KEK/version có thể tái dựng?
14. **HSM:** Backup domain, partition, attributes, firmware compatibility và quorum được inventory?
15. **KMS:** Hiểu semantics replication/durability/deletion và khả năng khôi phục của provider?
16. **Certificates:** Public verification material, certificate chain và JWKS history được archive?
17. **Recovery evidence:** Manifest, signature, digest, approvals và audit references có bản độc lập?

### C. Bảo vệ storage và backup key

18. **Immutable:** Retention/WORM/Object Lock có được enforce và test quyền bypass?
19. **Offline:** Có offline/isolated copy khi risk tier yêu cầu và có media lifecycle?
20. **Encryption:** Backup ciphertext được bảo vệ bằng backup DEK/KEK phù hợp?
21. **Independent KEK:** Backup key có recovery path không phụ thuộc duy nhất production KMS?
22. **Quorum:** Root/HSM/recovery material có split knowledge/M-of-N khi phù hợp?
23. **Manifest:** Archive digest và manifest signature được xác minh từ trust store độc lập?
24. **Purpose separation:** Backup signing key không dùng chung release/signing key trái policy?
25. **Retention:** Production không thể rút ngắn retention hoặc xóa legal hold?
26. **Catalog:** Backup catalog và restore dependencies có bản độc lập?
27. **Poisoning:** Có nhiều restore points và validation source độc lập?

### D. Restore và vận hành

28. **Restore order:** Có dependency graph cho identity, audit, metadata, HSM/KMS, ciphertext và application?
29. **Quarantine:** Backup được restore vào môi trường cách ly trước khi production cutover?
30. **Key verification:** Sau HSM/KMS restore đã kiểm tra key identity, attributes và permitted operations?
31. **AEAD:** Sample decrypt xác minh tag/AAD/key version trước khi tin plaintext?
32. **Consistency:** Có kiểm tra transaction watermark, schema và business invariants?
33. **RPO/RTO:** Mục tiêu có được đo trong drill thực tế?
34. **Custodian continuity:** Restore đạt quorum khi một người giữ share vắng mặt?
35. **Credential hygiene:** Recovery credential được rotate/revoke sau break-glass?
36. **Audit:** Ai ghi, đọc, approve, restore và thay retention đều được ghi nhận?
37. **Destruction:** Không hủy key/backup còn dependency, retention hoặc legal hold?
38. **Drill cadence:** Có lịch thử restore key, dữ liệu và toàn hệ thống?
39. **Ransomware:** Có tabletop khi production admin và IdP bị chiếm?
40. **Evidence:** Có lưu kết quả drill, lỗi, RPO/RTO thực tế và owner remediation?

## 32. Tổng kết

**Backup storage độc lập** là một ranh giới phục hồi được bảo vệ trước những sự cố có thể phá production. Tách bucket hoặc region chỉ giải quyết một phần; cần tách **account, identity, administrator, network, retention, audit, key custody và restore approval**. Production workload chỉ nên có quyền gửi backup vào ingest path; backup custodian và recovery operator cần quyền riêng, có audit và kiểm soát thời hạn.

Trong key management, phải backup đồng bộ **ciphertext, wrapped DEK, key metadata, policy/lineage, HSM recovery material và evidence** theo khả năng của từng loại dịch vụ. **KMS replication không mặc nhiên là backup độc lập; HSM backup file không chứng minh restore được; WORM không chứng minh nội dung ban đầu đúng; checksum không chứng minh nguồn gốc.** Cần tránh circular dependency khiến backup phải dùng chính production KMS đang bị mất để giải mã.

Khả năng phục hồi chỉ được chứng minh bằng **restore drill**: xác minh manifest, phục hồi identity và key theo đúng quorum, kiểm tra key attributes, giải mã mẫu có AEAD tag hợp lệ, kiểm tra transaction/business consistency và đo RPO/RTO. Giữ nhiều restore points, quarantine dữ liệu sau restore và không hủy key cũ khi ciphertext/archive còn phụ thuộc. **Một bản backup tốt là bản có thể tìm, xác minh và khôi phục an toàn ngay cả khi production account, credential hoặc control plane chính không còn đáng tin.**

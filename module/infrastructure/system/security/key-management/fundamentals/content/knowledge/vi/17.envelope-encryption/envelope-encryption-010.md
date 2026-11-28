# Re-encrypt data khi rotate DEK — Mã hóa lại dữ liệu khi thay khóa dữ liệu

## 1. Re-encrypt data khi rotate DEK là gì?

**Re-encrypt data khi rotate DEK** là quá trình **giải mã dữ liệu đang được bảo vệ bằng DEK cũ, kiểm tra tính toàn vẹn, rồi mã hóa lại bằng một DEK mới** theo thuật toán, nonce/IV và ngữ cảnh xác thực phù hợp. Sau đó hệ thống lưu **ciphertext mới cùng metadata của DEK mới**, đồng thời quản lý phụ thuộc của ciphertext, backup và phiên bản khóa cũ.

**DEK (Data Encryption Key)** là khóa trực tiếp bảo vệ nội dung, thường bằng thuật toán mã hóa đối xứng như **AES-GCM**. Trong **envelope encryption**, DEK thường được bọc bởi **KEK (Key Encryption Key)** ở KMS/HSM. Do đó:

- **Rotate KEK và rewrap DEK** có thể giữ nguyên DEK và ciphertext dữ liệu.
- **Rotate DEK và re-encrypt data** thay **chính khóa trực tiếp mã hóa plaintext**, nên thường phải tạo ciphertext mới nếu muốn di chuyển dữ liệu lịch sử sang khóa mới.

Ví dụ, hóa đơn `invoice-0123` hiện dùng `DEK-v1`:

~~~text
ciphertext_v1 = AES-GCM-Encrypt(DEK-v1, plaintext, nonce_v1, AAD_v1)
wrappedDEK_v1 = KMS-Wrap(KEK-v3, DEK-v1)

Sau khi rotate DEK và mã hóa lại:
plaintext  = AES-GCM-Decrypt-Verify(DEK-v1, ciphertext_v1, nonce_v1, AAD_v1)
ciphertext_v2 = AES-GCM-Encrypt(DEK-v2, plaintext, nonce_v2, AAD_v2)
wrappedDEK_v2 = KMS-Wrap(KEK-được-chọn, DEK-v2)
~~~

**`DEK-v2` phải là vật liệu mới** được sinh hoặc dẫn xuất theo thiết kế mật mã đã phê duyệt; không thể chỉ đổi trường `keyVersion` từ `v1` sang `v2`.

Trong mô-đun **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, chủ đề này gắn với vòng đời khóa từ **tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi đến hủy**, cũng như **KMS/HSM, thuật toán đối xứng, phân quyền, kiểm toán và phục hồi dữ liệu**.

> **Nguyên tắc:** Mã hóa lại thành công phải bảo đảm **plaintext được giữ nguyên ở mức nghiệp vụ**, **ciphertext và metadata mới đồng bộ**, **không tái sử dụng nonce sai quy tắc**, **không ghi đè dữ liệu khi có writer đồng thời**, và **không hủy DEK cũ khi còn bản mã/backup phụ thuộc**.

### Mục tiêu học tập

1. Phân biệt chính xác **DEK rotation**, **KEK rotation**, **rewrap** và **re-encrypt**.
2. Hiểu vì sao cần **verify authentication tag trước khi chấp nhận dữ liệu** rồi mã hóa lại.
3. Thiết kế định dạng envelope chứa **key ID/version, nonce, tag, AAD context và revision**.
4. Xây dựng quy trình online với **dual-read/single-write, optimistic concurrency, batching và retry**.
5. Chọn chiến lược **new-write-only, lazy migration, bulk migration hoặc emergency re-encryption**.
6. Dùng Java JCA/JCE để minh họa quá trình decrypt → encrypt bằng hai DEK riêng.
7. Xử lý **backup/DR, KMS/HSM, IAM, cache, key compromise, rollback và audit**.

## 2. Phân biệt rotate DEK với rotate KEK

Đây là sự khác biệt quan trọng nhất trong envelope encryption.

| Thuộc tính | **Rotate KEK / rewrap** | **Rotate DEK / re-encrypt** |
| --- | --- | --- |
| Khóa thay đổi | KEK bảo vệ một hoặc nhiều DEK | DEK trực tiếp bảo vệ dữ liệu |
| DEK có thay không? | **Thường không** khi chỉ rewrap | **Có** |
| Ciphertext dữ liệu có đổi không? | **Thường không**, nếu DEK không đổi | **Có** khi mã hóa lại |
| Wrapped DEK có đổi không? | Có nếu chuyển sang KEK mới | Có thể có vì đang bọc **DEK mới** |
| Cần truy cập plaintext dữ liệu? | Thông thường không, nếu API rewrap phù hợp | **Có** ở một ranh giới xử lý an toàn, trừ khi có cơ chế đặc biệt được chứng minh |
| Tải I/O | Thường trên wrapped key/metadata | Có thể phải đọc/ghi toàn bộ dữ liệu |
| Tác động đến nonce/tag | Không phải tạo lại ciphertext dữ liệu | Phải tạo nonce/tag mới theo AEAD |
| Khi DEK đã lộ | **Không đủ** để khôi phục bí mật | Cần đánh giá thay DEK và mã hóa lại |
| Khi KEK đã lộ | Rewrap có thể là một bước, nhưng phải đánh giá DEK bị ảnh hưởng | Có thể cần nếu DEK cũng đã bị lộ |
| Phụ thuộc sau migration | Bản bọc DEK và KEK version | Dữ liệu, DEK version, backups và old ciphertext |

**Rewrap không phải một từ đồng nghĩa với re-encrypt.** Trong mô hình thông thường, rewrap chỉ thay lớp bảo vệ khóa; re-encrypt thay lớp mã hóa dữ liệu.

### Một ví dụ nhỏ

~~~text
Trước:
  DATA = E(DEK-A, invoice)
  WRAP = W(KEK-1, DEK-A)

Chỉ rotate KEK:
  DATA = E(DEK-A, invoice)    # Không đổi
  WRAP = W(KEK-2, DEK-A)      # Đổi

Rotate DEK và re-encrypt:
  DATA = E(DEK-B, invoice)    # Đổi
  WRAP = W(KEK-2, DEK-B)      # Đổi theo DEK mới
~~~

**Kết luận:** Phải biết khóa nào trực tiếp mã hóa dữ liệu trước khi viết rotation policy hoặc migration job.

## 3. Khi nào thật sự cần re-encrypt dữ liệu?

Không phải mọi lần đến lịch rotation đều bắt buộc mã hóa lại toàn bộ dữ liệu lịch sử ngay lập tức. Chính sách cần phân biệt **ngừng sử dụng DEK cũ cho dữ liệu mới** và **di chuyển dữ liệu đã tồn tại**.

### 3.1. Scheduled rotation

DEK đến hạn cryptoperiod; tổ chức có thể chọn:

- Dùng DEK mới cho **new writes**, giữ DEK cũ ở chế độ decrypt-only theo retention.
- Re-encrypt từng bản ghi khi chúng được đọc/cập nhật.
- Re-encrypt toàn bộ trước một deadline đã phê duyệt.

Chọn hướng nào phụ thuộc **risk tier, data classification, số lượng bản mã, thời gian lưu trữ và năng lực vận hành**.

### 3.2. Nghi hoặc xác nhận DEK bị lộ

Nếu đối thủ có **raw DEK**, mọi ciphertext được bảo vệ bằng DEK đó và có thể lọt vào tay đối thủ phải được đánh giá. Việc thay DEK cho dữ liệu mới và mã hóa lại dữ liệu đang quản lý là hành động cần cân nhắc khẩn cấp.

**Nhưng re-encrypt hôm nay không xóa được ciphertext cũ, DEK cũ hoặc plaintext mà đối thủ đã sao chép trước đó.** Cần điều tra lịch sử, backup, log, cache, external copies và nghĩa vụ ứng cứu tương ứng.

### 3.3. Thay thuật toán hoặc sửa lỗi giao thức

Ví dụ hệ thống trước đây dùng mode không có xác thực hoặc nonce AES-GCM có nguy cơ trùng. Migration có thể yêu cầu **đổi DEK, định dạng ciphertext, AAD và kiểm tra dữ liệu nguồn**, chứ không chỉ “encrypt lại”.

Nếu ciphertext cũ không có authentication tag hoặc tính toàn vẹn không đáng tin, **không được khẳng định đã xác minh dữ liệu cũ** bằng một phép decrypt thành công. Cần quy trình đánh giá nguồn và xử lý integrity riêng.

### 3.4. Thay ranh giới tenant hoặc tổ chức

Khi tách tenant, môi trường production/staging hoặc vùng dữ liệu, tổ chức có thể muốn mỗi tenant có **DEK riêng** để hạn chế blast radius. Việc di chuyển dữ liệu phải bảo đảm **scope đúng tenant** và không dùng nhầm AAD/key của đối tượng khác.

### 3.5. Thay nhà cung cấp KMS/HSM

Khi di chuyển provider, nếu chỉ đổi KEK và giữ DEK, có thể rewrap; nếu chính sách mới yêu cầu **DEK được sinh và quản lý riêng**, re-encrypt có thể bắt buộc. Không giả định provider cho phép xuất hoặc chuyển raw key material giữa hai nơi.

## 4. Mô hình đe dọa: re-encrypt giải quyết điều gì?

Trước khi chạy một job lớn, xác định **vật liệu nào đã hoặc có thể bị lộ**.

| Điều bị lộ hoặc thay đổi | Có bắt buộc re-encrypt? | Phân tích |
| --- | --- | --- |
| KEK cần thay theo lịch, DEK vẫn bí mật | Không nhất thiết | Rewrap có thể đáp ứng mục tiêu |
| DEK plaintext đã lộ | Thường cần cân nhắc **thay DEK + re-encrypt** | Raw DEK cũ vẫn giải mã được old ciphertext |
| App credential có quyền `Unwrap` bị lấy | Phụ thuộc bằng chứng | Kiểm tra DEK nào đã được trả và ciphertext nào bị truy cập |
| Private signing key bị lộ | Không phải giải pháp chính | Thay key ký, đánh giá chữ ký/trust, không tự liên quan DEK |
| AES-GCM nonce lặp dưới cùng DEK | Cần ứng cứu/migration theo phạm vi | Rủi ro bảo mật tăng ngay cả khi raw DEK chưa lộ |
| Certificate hoặc public key hết hạn | Không liên quan trực tiếp | Thay chứng thư/trust theo PKI |
| Chuyển chính sách tenant sang tách khóa | Tùy mục tiêu | Có thể cần re-encrypt để cách ly dữ liệu cũ |
| Sửa lỗi `keyVersion` metadata nhưng DEK không đổi | Không đủ để gọi rotation | Cần xác minh vật liệu và dữ liệu thật |

### Câu hỏi rủi ro cốt lõi

**Đối thủ đã có được gì?** Nếu họ giữ `DEK-v1` và `ciphertext_v1`, việc hệ thống tạo `ciphertext_v2` không thể lấy lại plaintext đã lộ. Nếu đối thủ chỉ biết key ID/metadata, tác động khác hẳn raw DEK.

**Điểm bí mật chung nằm ở đâu?** Nếu DEK v1 và v2 đều được dẫn xuất từ một master đã lộ, thay chỉ nhãn dẫn xuất có thể không khôi phục tính bí mật. Cần thay **trust root/master** và đánh giá mọi descendant keys.

## 5. Envelope encryption và phạm vi của DEK

Một kiến trúc điển hình:

~~~mermaid
flowchart TD
    P[Dữ liệu gốc] --> E[AES-GCM Encrypt bằng DEK]
    DEK[DEK sinh bằng CSPRNG] --> E
    E --> C[(Ciphertext + nonce + tag + AAD context)]
    DEK --> W[Wrap / Encrypt DEK]
    KEK[KEK trong KMS/HSM] --> W
    W --> WD[(Wrapped DEK + KEK ID/version)]
    C --> DB[(Object/DB record)]
    WD --> DB
    KM[Key inventory và rotation policy] --> DEK
    KM --> KEK
~~~

### Cách phân đoạn DEK

| Phạm vi một DEK | Điểm mạnh | Chi phí/rủi ro |
| --- | --- | --- |
| **Per object / per record** | Giới hạn số ciphertext cho mỗi DEK | Số wrapped DEK lớn, nhiều metadata/KMS calls |
| **Per tenant** | Tách biệt tenant tốt hơn shared global key | Một DEK có thể bảo vệ nhiều bản ghi tenant |
| **Per data shard / dataset** | Cân bằng quản lý và tốc độ | Blast radius phụ thuộc kích thước shard |
| **Per service** | Ít key hơn, quản lý dễ hơn | Khóa lộ có thể ảnh hưởng nhiều tenant |
| **Per session / ephemeral** | Thời gian sống ngắn | Cần key schedule và khôi phục session phù hợp |

**Granularity của DEK quyết định khối lượng re-encrypt.** Với một DEK per record, có thể tạo DEK mới cho từng bản ghi. Với một DEK per tenant, phải lập kế hoạch cho tất cả bản mã thuộc tenant đó.

### Không nhầm DEK version với database row version

- **DEK version:** cho biết **vật liệu khóa** dùng mã hóa.
- **KEK version:** cho biết khóa bọc DEK.
- **Schema version:** cho biết cấu trúc envelope/ciphertext.
- **Row revision / ETag:** để phát hiện **writer đồng thời**.
- **Business version:** phiên bản nội dung nghiệp vụ.

Các loại version này có thể thay đổi độc lập; cần lưu riêng để tránh lỗi migration.

## 6. Thiết kế định dạng dữ liệu mã hóa có thể migration

Mỗi ciphertext phải chứa hoặc liên kết tới đủ metadata để chọn **đúng khóa, nonce, thuật toán và AAD**. Không nên dựa duy nhất vào alias `current-key`.

### Ví dụ envelope minh họa

~~~yaml
schemaVersion: "2"
tenantId: "tenant-a"
recordId: "invoice-0123"
rowRevision: 41
contentEncryption:
  algorithm: "AES-256-GCM"
  dekVersion: "dek-2026-v2"
  nonceEncoding: "base64"
  nonce: "<12-byte-nonce-encoded>"
  ciphertextAndTagEncoding: "base64"
  ciphertextAndTag: "<ciphertext-with-authentication-tag>"
  aadProfile: "billing-record-aad-v2"
keyEnvelope:
  wrappingAlgorithm: "provider-approved-wrap"
  kekResourceId: "billing-kek-v4"
  wrappedDekEncoding: "base64"
  wrappedDek: "<wrapped-dek-data>"
migration:
  targetDekVersion: "dek-2026-v2"
  migrationRevision: 3
  changeRequestRef: "change-approval-id"
~~~

**Đây là schema mô tả**, không phải một lệnh KMS hoặc giá trị base64 có thể dùng trực tiếp. Placeholder không chứa dữ liệu bí mật thật.

### Trường nào phải được bảo vệ tính toàn vẹn?

Các trường ảnh hưởng đến ngữ nghĩa **tenant, record ID, key version, thuật toán, schema và phạm vi dữ liệu** phải được ràng buộc bằng thiết kế có kiểm tra integrity. Với AES-GCM, **AAD (Additional Authenticated Data)** có thể gắn các giá trị được chọn vào authentication tag.

Ví dụ một profile AAD:

~~~text
AAD = encodeCanonical(
    domain = "billing-record-encryption/v2",
    tenantId,
    recordId,
    dekVersion,
    rowRevision
)
~~~

**AAD không phải bí mật**, nhưng nó **được xác thực khi kiểm tra tag**. Nếu attacker thay tenant, ID hoặc version trong envelope mà không thể tạo tag hợp lệ, decrypt phải thất bại.

### Canonical encoding

Không ghép chuỗi không có quy ước:

~~~text
["ab", "c"] -> "abc"
["a", "bc"] -> "abc"
~~~

Dùng length-prefix, schema có thứ tự cố định hoặc canonical serialization. Nếu `rowRevision` hoặc `dekVersion` thay đổi khi re-encrypt, **phải tính AAD mới khi tạo ciphertext mới**; không thể đổi metadata rồi giữ tag cũ.

### Key ID không phải một quyền truy cập

Attacker có thể sửa `dekVersion` nếu metadata không được bảo vệ. Dù không biết raw DEK, việc chọn nhầm key có thể làm ứng dụng lộ lỗi hoặc tấn công nhầm phạm vi. Ứng dụng cần **ủy quyền tenant/record** trước key lookup, kiểm tra key ID thuộc đúng domain và luôn **verify tag**.

## 7. AES-GCM khi re-encrypt: những bất biến không được phá

**AES-GCM** là AEAD: tạo ciphertext và authentication tag để bảo vệ bí mật và tính toàn vẹn đối với plaintext/AAD trong giới hạn bảo mật của cơ chế.

### 7.1. Dùng DEK mới thực sự

**DEK-v2** phải là khóa mới từ nguồn ngẫu nhiên hoặc KDF có thiết kế tách miền/version đúng. Không nên tạo `v2` bằng cách sao chép raw DEK-v1 hoặc đổi tên alias.

### 7.2. Nonce không được lặp dưới cùng một key

Đối với GCM, **không tái sử dụng cùng nonce với cùng DEK**. Một nonce có thể công khai; vấn đề không phải giữ nonce bí mật mà là **quản lý tính không lặp trong phạm vi một key**.

- Với hệ thống dùng **nonce ngẫu nhiên 96 bit**, phải xét xác suất va chạm và **giới hạn số lần dùng mỗi key** theo thiết kế/đặc tả.
- Với **counter-based nonce**, phải có cơ chế phân bổ không trùng giữa các writer, region, restart và restore.
- Trong re-encrypt, sinh nonce cho **ciphertext mới**; không sao chép nonce cũ chỉ vì đã đổi DEK.
- **Random nonce không mang bảo đảm tuyệt đối không va chạm**. Hệ thống lưu lượng cao cần thiết kế và giới hạn tương ứng.

### 7.3. Kiểm tra tag trước khi chấp nhận plaintext

Quy trình phải **giải mã và xác minh tag** của ciphertext cũ trước khi sử dụng plaintext làm nguồn dữ liệu mới.

Một số API streaming có thể trả **plaintext từng chunk trước khi xác minh tag cuối cùng**. Không ghi dữ liệu đó ra nơi đáng tin, gửi qua network hoặc commit như dữ liệu hợp lệ **trước khi xác thực hoàn tất**. Với file lớn, thiết kế staging/commit hoặc cơ chế chunked AEAD chuẩn để bảo đảm không xuất dữ liệu chưa xác thực.

### 7.4. Không trộn key và metadata

Đối với một record:

~~~text
(ciphertext, tag, nonce, AAD profile, DEK version, wrapped DEK, KEK version)
~~~

phải đồng bộ theo định dạng lưu trữ. Không được ghi **ciphertext_v2** nhưng để `dekVersion=v1`, hoặc cập nhật `rowRevision` không khớp AAD đã dùng.

### 7.5. Xử lý lỗi theo kiểu fail closed

**AEADBadTagException** hoặc lỗi xác minh integrity phải được coi là **dữ liệu không đáng tin / sai khóa hoặc metadata**, không được “thử giải mã không kiểm tra tag” để tiếp tục migration.

Không tự fallback liên tục qua mọi key trong kho khi một version thất bại; làm vậy gây nhiễu audit, tăng chi phí và có thể tạo oracle. Chọn khóa bằng **metadata có kiểm soát** và xử lý lỗi chính xác.

## 8. Thuật toán re-encrypt một bản ghi

Một trình tự logic:

1. **Xác thực và ủy quyền** job/service được phép xử lý record/tenant và dùng DEK-v1/v2.
2. **Đọc snapshot nhất quán** của ciphertext_v1, nonce, tag, metadata, row revision và wrapped DEK.
3. **Xác định đúng DEK cũ** bằng key ID/version và cơ chế unwrap theo IAM; không đoán khóa.
4. **Decrypt + verify** ciphertext_v1 với AAD_v1; nếu lỗi, **dừng và cách ly record**, không ghi đè.
5. **Sinh hoặc truy xuất DEK mới** từ nguồn bảo mật và đúng target version. Nếu mỗi record có DEK riêng, tạo record-specific DEK mới.
6. **Tạo nonce mới** theo chính sách AES-GCM và xây AAD_v2 theo metadata mới.
7. **Encrypt plaintext** bằng DEK-v2, lấy ciphertext_v2 và tag_v2.
8. **Wrap DEK-v2** bằng KEK đúng chính sách, hoặc gắn đúng key reference nếu vật liệu được giữ trong dịch vụ.
9. **Kiểm tra dữ liệu mới** theo cơ chế được chấp thuận (ví dụ giải mã thử và xác minh checksum/value trong vùng an toàn).
10. **Commit atomically/conditional** ciphertext, tag, nonce, wrapped DEK, version, row revision; nếu revision đã đổi, bỏ kết quả cũ và retry có kiểm soát.
11. **Ghi audit** metadata: key IDs, phiên bản, record scope, revision, outcome, không log plaintext/DEK.
12. **Giới hạn/xóa best-effort buffer bí mật**, checkpoint tiến độ và không hủy DEK-v1 khi còn phụ thuộc.

~~~mermaid
sequenceDiagram
    participant J as Migration worker
    participant DB as Data store
    participant KMS as KMS/HSM
    participant AUD as Security audit
    J->>DB: Read ciphertext_v1 + metadata + revision
    DB-->>J: Snapshot record
    J->>KMS: Unwrap DEK-v1 theo đúng quyền
    KMS-->>J: DEK-v1 trong vùng xử lý được phép
    J->>J: AES-GCM Decrypt + VERIFY tag_v1
    Note over J: Nếu tag sai: quarantine, không ghi đè
    J->>KMS: Generate/Unwrap DEK-v2 + wrap theo policy
    KMS-->>J: DEK-v2 + wrapped DEK-v2 (nếu API hỗ trợ)
    J->>J: Tạo nonce_v2, AAD_v2 và AES-GCM Encrypt
    J->>DB: Conditional update WHERE revision = expected
    alt Revision hợp lệ
        DB-->>J: Commit thành công
        J->>AUD: MIGRATION_SUCCEEDED + key versions
    else Đã có writer khác
        DB-->>J: Conflict, không ghi đè
        J->>AUD: MIGRATION_CONFLICT + retry
    end
~~~

**Không để plaintext ở database/queue tạm** chỉ để thuận tiện di chuyển. Nếu cần staging cho file lớn, phải thiết kế vùng staging được bảo vệ và không công bố dữ liệu chưa được xác thực.

## 9. Bốn chiến lược migrate dữ liệu khi rotate DEK

| Chiến lược | Cách hoạt động | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| **New-write-only** | Dữ liệu mới dùng DEK-v2; dữ liệu cũ giữ v1 | Cutover nhẹ, ít I/O | Phụ thuộc DEK-v1 tồn tại lâu |
| **Lazy re-encryption** | Khi record được đọc/ghi, chuyển ciphertext sang v2 | Trải tải theo truy cập thực | Record ít truy cập không được di chuyển |
| **Bulk/background re-encryption** | Worker quét record v1 và mã hóa lại theo batch | Có tiến độ, deadline rõ | Chi phí I/O/CPU/KMS và nguy cơ tranh chấp |
| **Emergency migration** | Ưu tiên đối tượng rủi ro cao khi nghi lộ DEK | Hạn chế new use, giảm tiếp xúc hiện tại | Không phục hồi bí mật đã lộ, ảnh hưởng availability |

### 9.1. New-write-only có phải rotation thành công?

Có thể là **đã hoàn thành cutover cho new use**, nhưng **chưa hoàn thành migration lịch sử** nếu chính sách yêu cầu mọi dữ liệu chuyển sang v2. Báo cáo phải tách rõ hai mốc này.

### 9.2. Lazy migration có thể không bao giờ hoàn tất

Dữ liệu archive ít đọc có thể vẫn dùng v1 nhiều năm. Nếu có deadline hủy DEK-v1, cần kết hợp **batch sweep** hoặc giữ legacy decrypt theo retention đã duyệt.

### 9.3. Bulk migration cần giới hạn tài nguyên

Không nên tạo một job đọc toàn bộ cơ sở dữ liệu, giải mã hàng triệu record đồng thời rồi viết lại. Cần **batch, checkpoint, backpressure, retry, rate limit, canary và circuit breaker**.

### 9.4. Emergency migration không thay incident response

Khi lộ DEK, phải điều tra ciphertext đã bị sao chép và nơi DEK còn tồn tại, không chỉ bật một worker re-encrypt. Tùy tình huống, ưu tiên **cô lập quyền, thu hồi credential và bảo toàn bằng chứng** trước khi di chuyển.

## 10. Online rotation: dual-read, single-write và cutover

Khi hệ thống vẫn phải phục vụ request trong lúc migration, chiến lược thường an toàn là:

1. **Prepare readers:** trước tiên triển khai reader có thể decrypt **đúng key version v1 và v2** theo metadata.
2. **Create DEK-v2:** sinh vật liệu mới, cấu hình KMS/HSM, policy và key inventory, kiểm thử trên dữ liệu được phép.
3. **Switch writers:** sau khi reader đã sẵn sàng, writer chỉ mã hóa **dữ liệu mới bằng v2**.
4. **Migrate legacy records:** chạy lazy/bulk re-encryption, không ảnh hưởng tới writer production.
5. **Stop old new-use:** chặn writer cũ tiếp tục tạo ciphertext v1, kể cả service instance/cache/region chưa cập nhật.
6. **Retain old decrypt:** chỉ giữ quyền decrypt/unwrap v1 theo phạm vi và thời hạn được duyệt.
7. **Retire v1:** chỉ khi dữ liệu, archive và backup còn phụ thuộc đã được xử lý.

~~~mermaid
flowchart TD
    P[Preflight: DEK-v2 + IAM + readers ready] --> D[Dual-read: hỗ trợ v1 và v2 theo metadata]
    D --> W[Single-write: output mới chỉ dùng v2]
    W --> M[Migration worker re-encrypt record v1]
    M --> V[Đối chiếu tiến độ và thử restore]
    V --> Q{Còn ciphertext/backup dùng v1?}
    Q -->|Có| M
    Q -->|Không| R[Ngừng legacy decrypt và thu hồi quyền v1]
    R --> H[Đủ retention/approval thì hủy material v1]
    X[Compromise nghiêm trọng] -.-> IR[Emergency isolation và incident response riêng]
~~~

### Tại sao không cho writer fallback từ v2 sang v1?

Nếu v2 lỗi hoặc KMS trả lỗi, việc ứng dụng **âm thầm quay lại v1** có thể tạo thêm ciphertext bằng khóa đã đến hạn hoặc đã bị nghi lộ. Chính sách thường nên **fail closed** hoặc dùng cơ chế rollback có phê duyệt, audit và giới hạn rõ.

**Rollback routing không giống rollback dữ liệu**: nếu v2 đã mã hóa record mới, quay writer về v1 vẫn phải giữ khả năng decrypt ciphertext v2.

## 11. Concurrency: chống ghi đè record được cập nhật cùng lúc

Giả sử migration worker đọc hóa đơn ở `revision=41`, trong khi một request nghiệp vụ cập nhật hóa đơn thành `revision=42` và mã hóa bằng v2. Nếu migration worker tiếp tục **ghi đè bản mã v2 bằng plaintext cũ của revision 41**, dữ liệu cập nhật sẽ bị mất.

### Dùng optimistic concurrency / CAS

Một cập nhật có điều kiện có thể có dạng:

~~~sql
-- SQL minh họa; cú pháp transaction/encoding tùy database.
UPDATE encrypted_records
SET
    ciphertext_and_tag = :new_ciphertext_and_tag,
    nonce = :new_nonce,
    aad_profile = :new_aad_profile,
    dek_version = :new_dek_version,
    wrapped_dek = :new_wrapped_dek,
    kek_version = :new_kek_version,
    revision = revision + 1
WHERE
    id = :record_id
    AND tenant_id = :tenant_id
    AND revision = :expected_revision
    AND dek_version = :expected_old_dek_version;
~~~

**Chỉ khi số dòng cập nhật đúng bằng 1 mới coi migration record đó đã commit.** Nếu số dòng bằng 0, có thể record đã được di chuyển, xóa hoặc sửa bởi writer khác. Worker phải **đọc lại và quyết định lại**, không retry bằng cách ghi đè mù.

### Những gì phải commit cùng nhau

- Ciphertext và authentication tag.
- Nonce/IV.
- AAD profile và metadata AAD nếu lưu.
- DEK ID/version và wrapped DEK/KEK version phù hợp.
- Database revision, trạng thái migration/checkpoint nếu liên quan transaction.

Một database record có thể chứa metadata đủ để cập nhật atomically. Với object storage và metadata lưu riêng, cần **versioned object + manifest/pointer commit**, không cho reader thấy bản mã mới nhưng key reference cũ.

### Row revision trong AAD

Nếu **revision là một trường AAD**, worker phải tạo ciphertext với **revision mới** trước khi commit. Khi update thành công, revision lưu phải **khớp số được đưa vào AAD**. Nếu update conflict, kết quả encrypt dựa trên revision cũ không còn hợp lệ và phải bỏ.

### Tránh race với xóa và retention

Nếu record vừa bị xóa theo chính sách, migration không được “hồi sinh” record bằng một bản ghi mã hóa lại. Các trạng thái **tombstone/legal hold/retention** cần nằm trong predicate hoặc state machine có kiểm soát.

## 12. Batching, retry và idempotency

Re-encrypt dữ liệu sản xuất thường là **migration job dài, có thể dừng rồi chạy tiếp**.

### 12.1. Checkpoint

Nên lưu tiến độ bằng **record ID, partition, key version và revision**, không chỉ “đã xử lý 90%”. Nếu dữ liệu được thêm/sửa liên tục, con số tổng cần có **định nghĩa rõ**: tổng snapshot ban đầu, tổng ciphertext v1 hiện còn, hay tổng công việc đã hoàn thành.

### 12.2. Idempotency

Một retry hợp lệ phải không làm hỏng dữ liệu:

~~~text
Nếu record đã ở target DEK v2 và metadata hợp lệ:
    skip hoặc verify theo policy
Nếu record ở DEK v1:
    decrypt-verify + encrypt + conditional commit
Nếu record đã đổi revision trong lúc xử lý:
    bỏ output chưa commit, đọc lại và đánh giá
Nếu record có tag lỗi:
    quarantine, không “sửa” bằng cách bỏ qua kiểm tra
~~~

Mỗi lần **encrypt lại với AES-GCM** cần nonce phù hợp; không tái sử dụng kết quả encryption từ một bản ghi đã thay đổi plaintext/AAD, trừ trường hợp retry **cùng kết quả bất biến** được thiết kế an toàn.

### 12.3. Retry/backoff

Lỗi KMS timeout, quota, session exhaustion và transient network failure có thể retry với **backoff, jitter và giới hạn số lần**. Lỗi **authentication tag, sai tenant, key không tồn tại, policy deny** không nên được retry vô hạn như lỗi mạng.

### 12.4. Dead-letter/quarantine

Ghi reference, reason code và trạng thái vào hàng xử lý sự cố **không chứa plaintext/DEK**. Cho phép đội vận hành xử lý sai metadata hoặc dữ liệu không hợp lệ qua workflow có audit, không ngầm bỏ qua bản ghi trong báo cáo “100% migrated”.

## 13. Java 11+: re-encrypt một record bằng hai DEK khác nhau

Ví dụ Java sau sử dụng JCA/JCE để minh họa:

- AES-256-GCM cho ciphertext v1 và v2.
- Hai **DEK được sinh riêng** bằng `KeyGenerator`/`SecureRandom`.
- AAD có **tenant, record ID, DEK version và row revision** dưới dạng length-prefix.
- Kiểm tra tag trong `Cipher.doFinal()` **trước khi** mã hóa dữ liệu sang v2.
- Tạo nonce 12 byte mới, 128-bit authentication tag.
- `AtomicReference.compareAndSet` để mô phỏng **conditional commit** trên **một record trong bộ nhớ**.

**Đây là ví dụ giáo dục, không dùng trực tiếp làm migration production.** Khóa ở trong JVM, không được bọc bằng KMS; `AtomicReference` không thay thế transaction của database hoặc kiểm soát concurrent writers trên nhiều máy.

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

public final class DekReencryptionDemo {
    private static final SecureRandom RNG = new SecureRandom();
    private static final int NONCE_BYTES = 12;
    private static final int TAG_BITS = 128;
    private static final String CIPHER = "AES/GCM/NoPadding";

    static final class EncryptedRecord {
        final String tenantId;
        final String recordId;
        final String dekVersion;
        final long revision;
        final byte[] nonce;
        final byte[] ciphertextAndTag;

        EncryptedRecord(String tenantId, String recordId,
                        String dekVersion, long revision,
                        byte[] nonce, byte[] ciphertextAndTag) {
            this.tenantId = tenantId;
            this.recordId = recordId;
            this.dekVersion = dekVersion;
            this.revision = revision;
            this.nonce = nonce.clone();
            this.ciphertextAndTag = ciphertextAndTag.clone();
        }
    }

    static SecretKey newAes256Dek() throws GeneralSecurityException {
        KeyGenerator kg = KeyGenerator.getInstance("AES");
        kg.init(256, RNG);
        return kg.generateKey();
    }

    // Canonical AAD: mỗi string có độ dài trước byte UTF-8.
    static void field(DataOutputStream out, String value)
            throws java.io.IOException {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(bytes.length);
        out.write(bytes);
    }

    static byte[] aad(EncryptedRecord record)
            throws java.io.IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(buffer);
        field(out, "billing-record-v1");
        field(out, record.tenantId);
        field(out, record.recordId);
        field(out, record.dekVersion);
        out.writeLong(record.revision);
        out.flush();
        return buffer.toByteArray();
    }

    static EncryptedRecord encrypt(
            String tenant, String id, String dekVersion,
            long revision, byte[] plaintext, SecretKey dek)
            throws Exception {

        byte[] nonce = new byte[NONCE_BYTES];
        RNG.nextBytes(nonce);

        // Metadata được xác thực cùng ciphertext.
        EncryptedRecord context = new EncryptedRecord(
                tenant, id, dekVersion, revision, nonce, new byte[0]);

        Cipher cipher = Cipher.getInstance(CIPHER);
        cipher.init(Cipher.ENCRYPT_MODE, dek,
                new GCMParameterSpec(TAG_BITS, nonce));
        cipher.updateAAD(aad(context));
        byte[] ciphertextAndTag = cipher.doFinal(plaintext);

        return new EncryptedRecord(
                tenant, id, dekVersion, revision, nonce, ciphertextAndTag);
    }

    static byte[] decrypt(EncryptedRecord record, SecretKey dek)
            throws Exception {
        Cipher cipher = Cipher.getInstance(CIPHER);
        cipher.init(Cipher.DECRYPT_MODE, dek,
                new GCMParameterSpec(TAG_BITS, record.nonce));
        cipher.updateAAD(aad(record));

        // doFinal xác minh GCM tag; không dùng plaintext
        // trước khi doFinal trả thành công.
        return cipher.doFinal(record.ciphertextAndTag);
    }

    public static void main(String[] args) throws Exception {
        SecretKey dekV1 = newAes256Dek();
        SecretKey dekV2 = newAes256Dek();

        byte[] original = "invoice-demo-only"
                .getBytes(StandardCharsets.UTF_8);

        try {
            EncryptedRecord oldRecord = encrypt(
                    "tenant-a", "invoice-0123", "dek-v1",
                    41L, original, dekV1);

            // Mô phỏng một record được quản lý bởi DB.
            AtomicReference<EncryptedRecord> slot =
                    new AtomicReference<>(oldRecord);

            EncryptedRecord snapshot = slot.get();

            // 1. Verify ciphertext v1 trước khi chấp nhận plaintext.
            byte[] plaintext = decrypt(snapshot, dekV1);
            EncryptedRecord next;
            try {
                // 2. Mã hóa lại bằng vật liệu DEK-v2 + nonce mới.
                // Revision 42 được đưa vào AAD mới.
                next = encrypt(snapshot.tenantId, snapshot.recordId,
                        "dek-v2", snapshot.revision + 1,
                        plaintext, dekV2);
            } finally {
                Arrays.fill(plaintext, (byte) 0);
            }

            // 3. Chỉ commit nếu snapshot chưa bị thay thế.
            boolean committed = slot.compareAndSet(snapshot, next);
            if (!committed) {
                throw new IllegalStateException(
                        "Concurrent update: must reread, not overwrite");
            }

            // 4. Verify record mới với đúng key/metadata.
            byte[] verified = decrypt(slot.get(), dekV2);
            try {
                System.out.println("Migration committed: " + committed);
                System.out.println("Content preserved: "
                        + MessageDigest.isEqual(original, verified));
                System.out.println("New DEK version: "
                        + slot.get().dekVersion);
            } finally {
                Arrays.fill(verified, (byte) 0);
            }

            // 5. Cùng ciphertext với tenant metadata bị sửa
            // phải bị phát hiện bởi GCM tag.
            EncryptedRecord tampered = new EncryptedRecord(
                    "tenant-b", next.recordId, next.dekVersion,
                    next.revision, next.nonce, next.ciphertextAndTag);
            try {
                decrypt(tampered, dekV2);
                throw new AssertionError("Tampered AAD accepted");
            } catch (AEADBadTagException expected) {
                System.out.println("Wrong tenant metadata: rejected");
            }

            // Không log plaintext, raw key hay nonce như một secret.
            // Production còn cần wrapped DEK + KEK ID, DB transaction,
            // IAM, key inventory, retry/rollback, audit và backup.
        } finally {
            Arrays.fill(original, (byte) 0);
        }
    }
}
~~~

**Kết quả dự kiến:**

~~~text
Migration committed: true
Content preserved: true
New DEK version: dek-v2
Wrong tenant metadata: rejected
~~~

### Những gì ví dụ làm đúng

- **V1 và v2 dùng hai `SecretKey` mới**; không đơn thuần đổi alias.
- **Không dùng plaintext trước khi GCM `doFinal()` thành công**.
- **AAD ràng buộc tenant, record, DEK version và revision**.
- **Nonce mới** được sinh cho ciphertext mới.
- **CAS** từ chối kết quả migration nếu snapshot bị thay.
- Có **negative test** cho metadata sai tenant.

### Những giới hạn không được bỏ qua

1. `AtomicReference` chỉ bảo vệ **một object trong cùng tiến trình**. Production cần DB transaction/optimistic locking hoặc versioned object store.
2. **Không có wrapped DEK** hay KMS/HSM trong demo. Trong production, DEK-v1/v2 phải được cung cấp và bảo vệ theo key policy, có liên kết rõ tới KEK/version.
3. `SecureRandom` + nonce 96 bit ngẫu nhiên **không chứng minh chắc chắn không va chạm ở mọi quy mô**. Production phải xác định giới hạn sử dụng và chiến lược nonce đúng.
4. Không có business authorization, tenant isolation ở storage, IAM, retention, writer fencing hoặc distributed transaction.
5. `Arrays.fill` chỉ là **best effort**; JVM/JCE có thể giữ bản sao mảng hoặc key material bên trong provider.
6. Kiểm tra `original` và `verified` mô phỏng **tính nhất quán của một lần migration**; không thay test restore, dữ liệu lớn hoặc thuật toán cũ.
7. Demo mã hóa toàn bộ bản ghi trong RAM. Với object lớn cần **thiết kế streaming authenticated staging** và chỉ commit sau khi xác minh đầy đủ.
8. Nếu DEK-v1 đã compromised, ví dụ **không giải quyết** old ciphertext/backups mà attacker đã sao chép.

## 14. KMS/HSM và quyền cần có cho migration

Một migration worker có thể phải **đọc dữ liệu, giải bọc DEK cũ, bọc DEK mới và cập nhật ciphertext**. Đó là một tổ hợp quyền rủi ro cao.

### Mô hình quyền tối thiểu

| Principal/role | Quyền có thể cần | Không nên mặc định có |
| --- | --- | --- |
| **Key owner** | Phê duyệt mục đích, phạm vi, kế hoạch migration | Raw DEK hoặc quyền `Decrypt` mọi dữ liệu |
| **Key custodian** | Tạo/rotate key, cấu hình HSM/KMS policy | Quyền đọc plaintext dữ liệu nghiệp vụ |
| **Migration worker** | Đọc đúng tập ciphertext, `Unwrap` v1, dùng/nhận DEK v2, ghi đúng record | Quyền export KEK, sửa IAM hoặc đọc mọi tenant |
| **Application writer** | Mã hóa dữ liệu mới bằng v2 | Tiếp tục Encrypt v1 trái chính sách |
| **Application reader** | Decrypt đúng v1/v2 trong thời gian transition | Brute force mọi key hoặc bỏ qua tenant authorization |
| **Security approver** | Review và phê duyệt thao tác rủi ro cao | Tự thực thi/export secret |
| **Auditor** | Đọc bằng chứng thay đổi/sử dụng | Xóa log, truy cập DEK plaintext |

### Quyền gián tiếp

Một admin không có `Unwrap` trực tiếp nhưng được phép **tự sửa key policy/grant** vẫn có thể tạo đường truy cập. Cần xét `CreateGrant`, role trust, service identity, workflow deployment và quyền tắt audit.

### HSM bảo vệ cái gì?

Một **KEK non-exportable** có thể giữ trong HSM/KMS, nhưng khi service `Unwrap` DEK và nhận raw DEK ở host, **DEK plaintext đã rời boundary** theo thiết kế. Phải bảo vệ memory, crash dump, secret logging, cache và thời gian tồn tại.

Không mặc định mọi KMS có API `ReEncrypt`, `GenerateDataKey` hoặc `DeriveKey` giống nhau. Việc tạo/bọc DEK và chi phí throughput tùy **provider, key type và cơ chế hỗ trợ**.

## 15. Phân loại DEK và cách lựa chọn khóa mới

### 15.1. DEK riêng per object

Nếu mỗi object có wrapped DEK riêng, có thể:

1. Sinh DEK mới cho object đó.
2. Decrypt object với old DEK.
3. Encrypt bằng new DEK, wrap và cập nhật envelope.
4. Không lưu raw DEK sau khi hoàn tất.

Ưu điểm: dễ giới hạn blast radius và migration theo object. Thách thức: lượng DEK/wrapped metadata lớn và nhiều API KMS.

### 15.2. DEK chung cho một dataset/tenant

Nếu cả tenant dùng **một DEK-v1**, tất cả ciphertext của tenant đang dùng khóa đó có thể phụ thuộc v1. Sau cutover, đảm bảo writer không tiếp tục dùng v1; migration phải có cách thống kê và chuyển từng ciphertext.

**Không được hủy v1 chỉ vì 99,9% record đã hoàn tất**: phần còn lại có thể chứa dữ liệu cực kỳ quan trọng hoặc thuộc archive ít truy cập.

### 15.3. DEK dẫn xuất từ master

Một hệ thống có thể dẫn xuất subkey từ master bằng KDF chuẩn và context. Nếu **master bị lộ**, chỉ dẫn xuất `DEK-v2` với label khác từ **cùng master cũ** không giải quyết rủi ro. Khi cần tách ranh giới compromise, phải thay master và thiết kế lại phụ thuộc.

### 15.4. Key equality không phải test bảo mật đầy đủ

Hai DEK được sinh riêng theo CSPRNG an toàn có thể xác suất rất nhỏ trùng nhau, nhưng **không nên kiểm chứng bảo mật bằng cách sinh vài trăm khóa rồi so sánh byte**. Cần kiểm tra **nguồn entropy, provider, key provenance, key usage và IAM**.

## 16. Xử lý plaintext an toàn trong migration

Re-encrypt yêu cầu một bước có plaintext, nên phạm vi xử lý phải được thu hẹp.

### Các kiểm soát thực tế

- Worker chạy với **identity riêng**, mạng/host được harden và phạm vi tenant/dataset cụ thể.
- **Không ghi plaintext, DEK, KEK, PIN HSM, credential hoặc payload nhạy cảm vào log**.
- Không đưa plaintext vào job queue, dead-letter topic, monitoring trace, core dump hoặc crash report.
- Hạn chế **buffer lifetime**; nếu môi trường hỗ trợ, dùng vùng xử lý và thư viện có bảo đảm phù hợp.
- Kiểm tra **auth tag trước khi công bố plaintext**; với file lớn, dùng staging được bảo vệ.
- Đặt TTL và hạn mức cache của plaintext DEK; xét cache invalidation khi có compromise.
- Kết thúc job hoặc revoke quyền thì thu hồi grant, credential và xử lý dữ liệu tạm.
- Backup/observability của worker cũng phải nằm trong threat model.

**Java `Arrays.fill` không bảo đảm xóa mọi bản sao trong heap/native memory**. Không tuyên bố “zeroization hoàn toàn” chỉ vì đã gán mảng về zero. Nếu thiết kế không chấp nhận raw DEK ở host, cần cân nhắc **cryptographic operations trong boundary** hoặc kiến trúc dịch vụ dữ liệu/TEE/HSM phù hợp với threat model và năng lực thực tế.

### HSM có thể tự re-encrypt dữ liệu mà không ra plaintext?

Một số dịch vụ có API cho phép chuyển **ciphertext của key do chính dịch vụ quản lý** mà không lộ plaintext ra client. Nhưng **không được đánh đồng** API re-encrypt của KMS với việc chuyển một database record được mã hóa **bằng DEK ở ứng dụng**. Nhiều API chỉ xử lý **wrapped key hoặc ciphertext trực tiếp thuộc KMS**.

Nếu claim rằng plaintext không bao giờ ra khỏi HSM, phải chỉ ra **thuật toán, API, giới hạn kích thước và boundary thực tế** hỗ trợ điều đó.

## 17. Dữ liệu lớn, object storage và stream encryption

Đối với bản ghi nhỏ, có thể decrypt toàn bộ trong memory rồi encrypt lại. Với **file nhiều GB**, phương án đó không thực tế.

### 17.1. Tránh công bố plaintext trước khi verify

Trong AES-GCM một tag cho toàn bộ file, **tag có thể chỉ được kiểm tra cuối luồng**. Một API có thể đã cho stream plaintext ra từng chunk trước lúc xác minh xong. Không nên gửi chunk đó đến người dùng hay ghi đè dữ liệu gốc trước khi authentication thành công.

Giải pháp có thể là:

- Đọc ciphertext vào **vùng staging được bảo vệ**, decrypt và chỉ **commit output** sau khi verify tag.
- Sử dụng **chunked AEAD framing** đã được thiết kế và đánh giá: mỗi chunk có nonce/tag riêng, ràng buộc **thứ tự, offset, tổng số chunk, file ID và kết thúc thông điệp**.
- Dùng dịch vụ encryption có **mô hình stream/file** và bằng chứng integrity phù hợp; không tự tạo scheme nối chunk tùy tiện.

### 17.2. Object versioning

Với object store hỗ trợ phiên bản:

1. Đọc object version `old-etag` và metadata.
2. Tạo một **object version mới** đã mã hóa v2.
3. Xác minh v2 theo đúng key/AAD/tag.
4. Thay pointer/manifest chỉ khi `old-etag` hoặc revision còn hợp lệ.
5. Giữ hoặc dọn phiên bản cũ theo retention và incident policy.

Không xóa object version v1 chỉ vì pointer đã chuyển v2; các **snapshot, replication, backup và legal hold** có thể còn cần được đánh giá.

## 18. Backup, archive và disaster recovery

DEK-v1 có thể vẫn cần sau khi production database đã chuyển hết record sang v2.

### Những nơi thường bị quên

- Database snapshot/point-in-time recovery.
- Object version cũ, archive lạnh và bản sao cross-region.
- Backup của wrapped DEK, KEK hoặc key handles.
- Bản export/trích xuất cho đối tác theo chính sách.
- Bản lưu phục vụ điều tra, legal hold hoặc chứng cứ.
- Replicas/CDC stream và môi trường khôi phục sau thảm họa.

### Ba chiến lược quản trị backup

| Chiến lược | Lợi ích | Chi phí/rủi ro |
| --- | --- | --- |
| **Giữ DEK-v1 decrypt-only đến hết retention backup** | Restore backup cũ được | Giữ secret cũ lâu hơn, quyền và audit phải chặt |
| **Re-encrypt/rewrite backup** | Có thể giảm phụ thuộc DEK-v1 | Rất tốn tài nguyên, phức tạp consistency và retention |
| **Tạo backup mới v2, loại backup v1 đúng hạn** | Đơn giản hơn khi retention cho phép | Khoảng chờ vẫn cần DEK-v1; phải thử restore |

**Hủy DEK-v1** chỉ khi đã xác minh mọi bản mã và backup còn cần giải mã bằng v1 **đã được xử lý hoặc không còn nghĩa vụ giữ**. Không dựa vào “0 lượt KMS Unwrap trong 30 ngày” để kết luận không còn phụ thuộc: dữ liệu cũ có thể ít được đọc hoặc DEK đang trong cache.

### Restore drill

Thực hiện thử nghiệm khôi phục có kiểm soát với bản backup đại diện. Kiểm tra **đúng DEK/KEK version, nonce/AAD/tag, metadata và quyền**. Không chỉ kiểm tra rằng storage còn file backup.

## 19. Multi-region, replication và consistency

Một deployment nhiều vùng có thể có các writer khác nhau:

- Region A chuyển sang v2; Region B vẫn cache cấu hình v1.
- Record v2 được replicate tới reader chỉ biết v1.
- Alias/KMS key version có semantics khác giữa các vùng.
- Migration job ở hai vùng cùng đọc v1 và cùng ghi kết quả v2 khác nonce.
- Replica chậm có thể đưa **ciphertext v1** trở lại read path sau cutover.

### Kiểm soát đề xuất

1. **Reader-first deployment:** tất cả reader cần hiểu format/key v2 trước khi writer cutover.
2. **Writer fencing:** không cho writer cũ tạo ciphertext v1 sau mốc chính sách.
3. **Versioned metadata:** mỗi record tự nêu đúng DEK/KEK version và AAD profile.
4. **Concurrency control:** dùng revision/ETag/transaction tương ứng với hệ lưu trữ thực.
5. **Migration lease hoặc work partitioning:** tránh nhiều worker ghi cùng record; CAS vẫn là lớp bảo vệ cuối.
6. **Observability per region:** đo output new-use theo key version và số record còn v1.
7. **Fail closed:** nếu reader không có quyền dùng key version cần thiết, trả lỗi có kiểm soát; không đoán/fallback ngoài policy.

**Độ nhất quán của alias không đồng nghĩa độ nhất quán của dữ liệu.** Key lookup, DB commit, object manifests và regional replicas cần được kiểm tra riêng.

## 20. Incident response khi rotate DEK vì compromise

Nếu có dấu hiệu DEK-v1 đã lộ, quy trình không thể chỉ là “chạy job mã hóa lại”.

### Runbook

1. **Xác nhận và phân loại:** raw DEK, wrapped DEK, KEK, KMS credential, app cache hay backup đã bị truy cập?
2. **Cô lập đường lộ:** thu hồi credential/grant, chặn service sai phạm, cân nhắc suspend KEK hoặc DEK workflow theo availability/rủi ro.
3. **Bảo toàn chứng cứ:** KMS/HSM events, app logs, key inventory, ciphertext version, backup access và approvals.
4. **Khoanh vùng ảnh hưởng:** DEK-v1 bảo vệ những tenant, record, file, snapshot và phiên bản nào?
5. **Sinh DEK-v2 từ nguồn đáng tin:** nếu lỗi đến từ RNG, KDF/master yếu thì sửa nguyên nhân trước khi tạo lại.
6. **Chuyển new-use sang v2:** chặn writer v1, cập nhật IAM, test và key routing.
7. **Re-encrypt ưu tiên:** dữ liệu nhạy cảm hoặc có khả năng bị truy cập cao; dùng integrity verification và concurrency control.
8. **Đánh giá lịch sử:** dữ liệu đã bị lấy dưới ciphertext v1 không an toàn trở lại chỉ nhờ migration.
9. **Xử lý backup/replica:** chọn retention/reencrypt/delete theo trách nhiệm pháp lý và khả năng khôi phục.
10. **Thu hồi/hủy đúng chính sách:** không hủy v1 khi vẫn cần restore hoặc đang có legal hold; nếu v1 đã lộ, legacy decrypt phải được kiểm soát thật chặt.
11. **Hậu kiểm:** xem xét notification, thay đổi IAM/cache policy, bảo vệ plaintext và cải thiện logging.

### Tình huống cần phân biệt

- **Lộ KEK nhưng chưa rõ DEK:** đánh giá khả năng đối thủ có wrapped DEK, các lệnh unwrap đã thực hiện và phạm vi dữ liệu.
- **Lộ raw DEK:** cần đánh giá ciphertext thuộc DEK đó và khả năng re-encrypt.
- **Lộ key ký số:** xử lý chữ ký/trust, không nhầm với DEK re-encrypt.
- **Lộ shared HMAC secret:** thay khóa MAC ở các bên, kiểm tra replay và message authenticity.
- **Lộ master KDF:** subkey v2 dẫn xuất từ master cũ có thể không còn an toàn.

## 21. Kiểm toán và đo tiến độ migration

**Migration completed** phải là một trạng thái có bằng chứng, không chỉ là dashboard hiển thị 100%.

### Event audit mẫu

~~~yaml
schemaVersion: "1"
eventType: "DEK_REENCRYPT_RECORD_COMMITTED"
requestId: "migration-2030-0071"
recordRef: "invoice-0123"
tenantScope: "tenant-a"
source:
  dekVersion: "dek-v1"
  rowRevision: 41
target:
  dekVersion: "dek-v2"
  rowRevision: 42
  kekReference: "billing-kek-v4"
decision:
  policyRevision: "dek-rotation-policy-v3"
  approvalRef: "approved-migration-id"
execution:
  actor: "billing-dek-migration-worker"
  result: "SUCCESS"
  providerEventRef: "kms-request-id"
eventTimeUtc: "2030-05-10T10:00:00Z"
~~~

Không ghi **DEK/KEK bytes, plaintext, HSM PIN, KMS token hoặc dữ liệu cá nhân nhạy cảm** vào event. `recordRef` nên có chính sách pseudonymization và quyền truy vấn tương ứng.

### Chỉ số quan trọng

| Chỉ số | Vì sao cần |
| --- | --- |
| Tỷ lệ **new writes** dùng DEK-v2 | Chứng minh writer cutover |
| Số ciphertext còn `dekVersion=v1` | Theo dõi phụ thuộc chưa di chuyển |
| Số record migrate/giờ | Ước lượng tải và tiến độ |
| Conflict/CAS retry rate | Phát hiện tranh chấp với writer |
| GCM authentication failure count | Phát hiện sai tag, dữ liệu hỏng hoặc sai metadata |
| KMS `Unwrap`/`GenerateDataKey` latency và failures | Đánh giá health/cost |
| Plaintext buffer/cache policy violations | Phát hiện nguy cơ lộ key và dữ liệu |
| Backup/DR dependency count | Quyết định khi nào được retire key |
| Old-key new-use attempts sau cutover | Phát hiện instance chưa nâng cấp hoặc bypass |
| Quarantine/dead-letter size | Bảo đảm không che giấu record lỗi |
| Audit correlation coverage | Chứng minh job/KMS/storage event liên kết |

**Đếm số record v1 còn lại phải tính cả nơi ít hiển thị** như archive, bản sao dự phòng và object version cũ, nếu mục tiêu của chính sách bao trùm chúng.

## 22. Kiểm thử trước và sau re-encryption

### 22.1. Kiểm thử chức năng

1. **Round trip:** Decrypt v1 → encrypt v2 → decrypt v2, so khớp plaintext/đối tượng nghiệp vụ.
2. **Wrong DEK:** dùng key sai phải thất bại; không cho phép output hỏng được chấp nhận.
3. **Wrong AAD:** đổi tenant/record ID/key version/revision phải làm tag verification thất bại.
4. **Tampered ciphertext/tag:** sửa một bit phải bị phát hiện theo đặc tính AEAD.
5. **Empty/large/binary payload:** dữ liệu rỗng, Unicode, nhị phân, file lớn và edge cases.
6. **Nonce management:** đảm bảo chiến lược không trùng, kiểm tra phân vùng/counter/giới hạn đúng thiết kế.
7. **Metadata atomicity:** không xuất hiện ciphertext v2 gắn `dekVersion=v1`.
8. **DB revision conflict:** writer thay record giữa read và commit thì migration không ghi đè.
9. **Retry crash:** worker chết trước/sau commit vẫn có thể resume idempotently.
10. **Object version restore:** reader chọn đúng bản mã và key theo manifest.

### 22.2. Kiểm thử bảo mật

1. **Cross-tenant:** migration worker không thể decrypt/copy record của tenant khác ngoài scope.
2. **Key permission:** principal không được phép `Unwrap` v1 hoặc use v2 bị KMS/HSM từ chối.
3. **Key state:** key suspended/deactivated không bị dùng cho new-use trái policy.
4. **No secret logging:** scan test logs với secret mẫu; không có DEK, plaintext, token, HSM PIN.
5. **Provider bypass:** gọi trực tiếp KMS ngoài workflow không vượt IAM.
6. **Fail closed:** tag failure, wrong metadata hoặc policy deny không tạo output v2.
7. **Backup access:** operator không có quyền không thể restore dữ liệu/keys tùy ý.
8. **Rewrap vs re-encrypt:** chứng minh raw DEK v2 khác v1 và ciphertext đã thực sự đổi.

### 22.3. Kiểm thử vận hành

1. **Canary migration** trên tập dữ liệu đại diện.
2. **Latency/throughput** ở tải bình thường và cao điểm.
3. **Quotas/rate limits** của KMS/HSM, DB và object store.
4. **Restart/failover** khi job đang decrypt, encrypt hoặc commit.
5. **Multi-region version skew** và replica lag.
6. **Backup restore drill** với cả record v1 và v2.
7. **Rollback routing** sau khi đã có dữ liệu v2.
8. **Destruction readiness**: chứng minh còn phụ thuộc thì không thể xóa key v1.
9. **Audit verification**: decision, provider execution, DB commit và failure được liên kết đúng.
10. **Compromise tabletop**: DEK-v1 lộ thì runbook thực sự tìm được mọi ciphertext phụ thuộc.

## 23. Case study: Billing chuyển DEK tenant từ v1 sang v2

### 23.1. Bối cảnh

`billing-platform` dùng một DEK cho dữ liệu hóa đơn của `tenant-a`, DEK này được bọc dưới KEK trong KMS. DEK-v1 đến hạn rotation. Hệ thống có **5 triệu bản ghi**, 3 vùng ứng dụng, bản sao database và backup định kỳ. Con số chỉ nhằm minh họa quy mô triển khai.

Yêu cầu:

- Không ngừng toàn bộ dịch vụ trong thời gian migration.
- Dữ liệu có thể đọc/ghi ở các vùng đã sẵn sàng.
- Không làm mất bản cập nhật hóa đơn đang diễn ra.
- Mỗi ciphertext có metadata đúng DEK version.
- Có khả năng khôi phục backup trước khi hủy v1.
- Có audit để chứng minh tiến độ và quyền sử dụng.

### 23.2. Kế hoạch triển khai

**Giai đoạn A — Thiết kế và preflight**

- Key owner phê duyệt cryptoperiod, mục đích và deadline.
- Custodian tạo DEK-v2 qua KMS/HSM đúng nguồn, gắn key inventory.
- Reader hiểu v1/v2, verify AEAD và key version.
- Kiểm tra IAM: migration worker dùng đúng tenant; writer mới không còn quyền tạo ciphertext v1 sau cutover.
- Thử restore một backup và kiểm tra object/row version.

**Giai đoạn B — Cutover new writes**

- Truyền cấu hình version có kiểm soát tới mọi vùng.
- Chuyển writer sang DEK-v2.
- Audit `dekVersion` thực tế trên dữ liệu mới, không chỉ log “alias updated”.
- Chặn hoặc quarantine request còn dùng v1 trái chính sách.

**Giai đoạn C — Bulk re-encryption**

- Worker lấy batch v1 theo partition, đọc ciphertext + revision.
- Giải mã và xác minh tag bằng DEK-v1; nếu sai đưa vào quarantine.
- Encrypt bằng v2, nonce mới, AAD theo tenant/ID/revision.
- Ghi atomically bằng CAS; nếu conflict thì đọc lại record.
- Checkpoint tiến độ, throttle KMS/DB, thống kê còn v1.
- Không tạo queue chứa plaintext.

**Giai đoạn D — Kiểm tra và retire**

- Quét đối soát toàn bộ dataset, replicas, archive/backups thuộc phạm vi.
- Đọc thử mẫu ciphertext v2 và khôi phục backup cũ.
- Ghi báo cáo migration, quyết định legacy decrypt của v1.
- Chỉ khi **hết phụ thuộc theo retention** mới phê duyệt hủy DEK-v1.

### 23.3. Tình huống race minh họa

~~~text
10:00:00  Worker đọc invoice-0123 revision=41, DEK-v1
10:00:01  API user cập nhật invoice-0123 -> revision=42, DEK-v2
10:00:02  Worker mã hóa lại bản snapshot revision=41
10:00:03  Worker UPDATE ... WHERE revision=41 -> 0 rows
10:00:04  Worker bỏ output chưa commit và đọc lại revision=42
10:00:05  Record đã là DEK-v2 -> skip
~~~

**Nếu thiếu `WHERE revision=41`, bản ghi revision 42 có thể bị ghi đè bằng nội dung cũ.** Đây là lỗi **mất cập nhật**, không phải lỗi AES.

### 23.4. Khi v1 bị nghi compromise giữa chừng

Không tự động tiếp tục quy trình scheduled rotation. Cần mở **incident response riêng**, cô lập quyền cũ, xác định dữ liệu/backup có khả năng bị lấy và ưu tiên phạm vi rủi ro. Hệ thống có thể cần duy trì decrypt-only v1 có kiểm soát để phục hồi hợp pháp trong khi xử lý sự cố.

## 24. Các lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đổi `dekVersion=v2` nhưng không thay vật liệu | Không có DEK rotation thật | Sinh DEK mới và xác minh provenance |
| Chỉ rewrap dưới KEK mới khi DEK đã lộ | Đối thủ vẫn có raw DEK cũ | Thay DEK, re-encrypt, ứng cứu lịch sử |
| Re-encrypt nhưng dùng lại nonce trái chính sách | Có thể phá bảo mật AES-GCM | Nonce mới/quản lý nonce đúng theo key |
| Bỏ qua GCM tag để “cứu dữ liệu” | Hợp thức hóa plaintext không tin cậy | Fail closed, quarantine và điều tra |
| Stream plaintext chưa verify tag vào DB mới | Đưa dữ liệu chưa xác thực vào vùng tin cậy | Staging/commit sau verify |
| Chỉ đổi ciphertext, giữ key version/tag/nonce cũ | Dữ liệu không thể giải mã hoặc integrity sai | Atomic envelope update |
| Ghép AAD không canonical | Có thể nhầm tenant/context | Encoding length-prefix/chuẩn |
| Đọc v1 rồi ghi đè không kiểm tra revision | Lost update khi writer đồng thời | CAS/ETag/transaction |
| Rollback xóa DEK-v2 đã có dữ liệu thật | Không thể decrypt bản ghi v2 | Giữ v2 theo dependency |
| Tự fallback sang DEK-v1 khi v2 lỗi | Tiếp tục dùng key quá hạn hoặc compromised | Fail closed và rollback phê duyệt |
| Chạy bulk migration toàn bảng một lần | Quá tải DB/KMS và ảnh hưởng SLA | Batch, throttle, checkpoint |
| Retry tag failure vô hạn | Che dấu dữ liệu hỏng hoặc sai metadata | Quarantine và incident triage |
| Log plaintext hoặc raw DEK để debug | Mở đường rò rỉ dữ liệu và key | Metadata-only audit và redaction |
| Hủy DEK-v1 khi database chính hết v1 | Backup/archive vẫn có thể cần | Dependency inventory và restore drill |
| Dùng alias thay key ID/version thực | Khó truy tìm vật liệu mã hóa | Versioned envelope/manifest |
| Writer ở vùng phụ tiếp tục dùng v1 | Rotation không hoàn tất new-use | Multi-region readiness và fencing |
| Quên raw DEK cache sau suspend | Có thể tiếp tục decrypt ngoài KMS | Cache policy, incident containment |
| Không thử dữ liệu rỗng/nhị phân/file lớn | Migration có thể làm hỏng payload | Round trip và integration tests |
| Tin re-encrypt thu hồi dữ liệu attacker đã lấy | Sai threat model | Đánh giá old copies và notification |
| Gọi automatic KEK rotation là DEK re-encryption | Báo cáo sai mức bảo vệ | Tách rõ material version và data migration |
| Tạo DEK-v2 từ master đã lộ | Key mới vẫn tính được | Thay master và đánh giá descendants |
| Coi `0 KMS decrypt` là không còn dữ liệu cũ | DEK cached hoặc archive không truy cập | Kiểm kê ciphertext/backup thực tế |

## 25. Checklist production cho re-encrypt data khi rotate DEK

1. **Scope:** DEK-v1 đang mã hóa dữ liệu nào: per record, tenant, shard, backup và archive?
2. **Trigger:** Đây là scheduled rotation, nonce/usage limit, thuật toán lỗi hay nghi key compromise?
3. **Threat model:** Raw DEK/KEK/master hoặc chỉ credential bị lộ? Có dữ liệu lịch sử đối thủ đã lấy?
4. **Key provenance:** DEK-v2 thực sự là vật liệu mới từ CSPRNG/KMS/HSM phù hợp?
5. **Purpose:** DEK có đúng mục đích mã hóa dữ liệu, tách với KEK/signing/HMAC/agreement key?
6. **KMS/HSM:** Worker có quyền unwrap old DEK và dùng/wrap new DEK theo least privilege, không tự sửa grants?
7. **Envelope:** Có đủ key ID/version, algorithm, nonce, tag, wrapped DEK, KEK ID/version, AAD profile và schema version?
8. **AAD:** Tenant/record/key version/revision có encoding canonical và được xác thực?
9. **GCM nonce:** Có chiến lược không lặp dưới cùng key, tính tới song song, vùng, restart và usage limits?
10. **Decrypt-verify:** Chỉ chấp nhận plaintext cũ sau khi xác minh tag thành công; tag lỗi phải quarantine?
11. **Plaintext:** Có giới hạn RAM/cache/temporary files, không log hoặc đẩy vào queue?
12. **Reader readiness:** Các reader đã hiểu cả v1/v2 trước khi writer cutover?
13. **Single-write:** Writer mới chỉ tạo ciphertext v2; các writer v1 bị fencing/chặn?
14. **Concurrency:** CAS/transaction/ETag bảo đảm không ghi đè business updates hoặc tombstones?
15. **Atomic commit:** Ciphertext, nonce, tag, DEK version, wrapped DEK/KEK version, revision được thay đồng bộ?
16. **Idempotency:** Retry sau crash/timeout không tạo plaintext mismatch hoặc ghi đè bản ghi mới?
17. **Batching:** Có checkpoint, throttle, jitter/backoff, quarantine và tiến độ có định nghĩa rõ?
18. **Large objects:** Có staging/stream AEAD an toàn, không công bố plaintext trước khi verify?
19. **Performance:** Đã đo CPU/IO, KMS quota, cache impact, replica lag và latency?
20. **Multi-region:** Có xử lý stale readers/writers và key version consistency?
21. **Audit:** Có log source/target version, actor, scope, approval, outcome, provider event, không chứa secret?
22. **Negative tests:** Sai key, sai tenant/AAD, tampered tag, suspended key, wrong-purpose operation đều bị từ chối?
23. **Data consistency:** Round-trip/semantic checks và sample restore đã đạt với nhiều loại dữ liệu?
24. **Rollback:** Nếu v2 đã tạo output thật, có giữ khả năng decrypt v2 dù rollback ứng dụng?
25. **Backup/DR:** Đã kiểm kê snapshot/archives/object versions và chiến lược retention của DEK-v1?
26. **Compromise:** Khi raw DEK-v1 lộ, có incident response, đánh giá old ciphertext và dữ liệu đã bị sao chép?
27. **Deactivation:** Đã chặn new-use v1 nhưng vẫn quản lý legacy decrypt được phê duyệt?
28. **Destruction:** Có bằng chứng hết phụ thuộc + owner approval trước khi hủy v1 và bản sao?
29. **Success criteria:** Có tách mốc **new-write cutover** khỏi **historical re-encryption completion**?
30. **Postmortem:** Có kiểm tra sai lệch, sự kiện bất thường, risk acceptance và bài học cho lần rotation kế tiếp?

### Ghi nhớ

**Re-encrypt data khi rotate DEK** là thao tác **giải mã/xác minh dữ liệu dưới DEK cũ, rồi mã hóa lại dưới DEK mới**, đồng thời cập nhật **nonce, authentication tag, AAD và metadata key version** một cách nhất quán. Nó **khác KEK rewrap**: rewrap có thể giữ nguyên DEK và ciphertext, nên không giải quyết sự cố **raw DEK đã lộ**. Trong production, phải thiết kế **reader hỗ trợ version cũ/mới trước cutover, writer chỉ dùng DEK mới, migration có CAS/transaction, batching/idempotency, kiểm tra toàn vẹn và hạn chế plaintext**. Đặc biệt, **AES-GCM không cho phép lặp nonce dưới cùng key**, và plaintext chưa xác minh tag không được công bố như dữ liệu đáng tin. **Backup, archive, replica và rollback** quyết định khi nào có thể ngừng hoặc hủy DEK cũ. Re-encryption không xóa những bản sao ciphertext/DEK mà đối thủ đã giữ; nó phải đi cùng **KMS/HSM, IAM least privilege, key inventory, audit, incident response và quản trị vòng đời khóa**.

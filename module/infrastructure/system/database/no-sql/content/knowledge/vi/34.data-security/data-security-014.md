# Bảo vệ snapshot, dump, log thay đổi và dữ liệu kiểm thử

## 1. Mở đầu: database đã bảo mật nhưng bản dump lại bị lộ

Một ứng dụng Java quản lý đơn hàng dùng NoSQL. Database production có network isolation, xác thực, phân quyền theo tenant và mã hóa ổ đĩa. Nhóm phát triển cần kiểm thử lỗi liên quan đến dữ liệu lớn nên tạo bản dump, tải về máy cá nhân và nạp vào staging.

```text
Production NoSQL
    |  access controlled, audited
    |
    +--- backup snapshot ----------> Object storage
    |                                   |
    |                                   +-- wrongly public / overbroad IAM
    |
    +--- developer dump -----------> Local laptop
    |                                   |
    |                                   +-- sync drive / lost device
    |
    +--- change stream -----------> Kafka / CDC log
                                        |
                                        +-- long retention / shared topic
                                        |
                                        +-- staging replay
```

Nếu dump chứa tên khách hàng, địa chỉ, mã thanh toán, email và thông tin giao hàng thật, nó **vẫn là dữ liệu nhạy cảm** dù file không còn nằm trong database gốc. Một snapshot có mã hóa nhưng key giải mã được cấp cho tất cả thành viên nhóm cũng không còn có ranh giới truy cập tương đương production.

Một sự cố tương tự có thể đến từ **change log**: ứng dụng đã xóa trường nhạy cảm khỏi document hiện tại nhưng log CDC còn giữ ảnh trước khi cập nhật, hoặc topic sự kiện được nạp sang môi trường test bằng tài khoản quá rộng.

Thông điệp chính:

> **Mọi bản sao chứa dữ liệu thật—snapshot, export, dump, file log, bản ghi CDC, bản phục hồi, dữ liệu test—phải được bảo vệ theo độ nhạy của nội dung và mục đích sử dụng, không theo tên môi trường hay phần mở rộng file.**

Bài này thuộc chương **Bảo mật dữ liệu** của module **Database No SQL**, tập trung vào bảo vệ toàn bộ vòng đời những **bản sao và dữ liệu phát sinh** ngoài database production.

## 2. Mục tiêu học tập

Sau bài học, bạn cần:

1. Xác định những nơi dữ liệu NoSQL có thể được **sao chép hoặc tái dựng**, kể cả logs, snapshots, caches và test fixtures.
2. Phân tích **threat model** cho dump, backup, CDC/change logs và môi trường kiểm thử.
3. Thiết kế quyền **least privilege, tách vai trò, approval, audit** cho export/backup/restore.
4. Hiểu **encryption at rest, encryption in transit, envelope encryption**, KMS và chính sách giữ key đủ cho khôi phục.
5. Phân biệt **snapshot consistency**, **data confidentiality**, **durability**, **recoverability**, **immutability** và **integrity verification**.
6. Bảo vệ backup/object storage khỏi public access, cross-account leaks, ransomware và việc xóa ngoài ý muốn.
7. Bảo vệ CDC/outbox/stream payload, schema history, before/after images, retry topics và DLQ.
8. Thiết kế bộ dữ liệu test dùng **synthetic generation, masking, pseudonymization** và kiểm soát tái định danh.
9. Tránh đưa raw production data vào local development, CI artifacts, support tickets hoặc observability logs.
10. Tạo runbook xuất/khôi phục dữ liệu, kiểm tra kiểm soát và xử lý sự cố lộ bản sao.

## 3. Một database có nhiều bản sao với mức rủi ro khác nhau

| Bản sao / nguồn phát sinh | Ví dụ | Rủi ro riêng |
|---|---|---|
| Snapshot storage | Cloud volume snapshot, managed database snapshot | IAM quá rộng, chia sẻ snapshot sai tài khoản |
| Logical dump | BSON/JSON/CSV/NDJSON, backup archive | File plaintext, copy về laptop, lộ qua object store |
| Physical backup | SSTables, RDB, AOF, index segments | Chứa byte thô, dữ liệu đã xóa có thể còn |
| Point-in-time recovery (PITR) | Snapshot + redo/change logs | Có thể phục dựng trạng thái dữ liệu trước lúc xóa |
| CDC/change stream | Insert/update/delete, before/after images | Có lịch sử field nhạy cảm và user activity |
| Outbox/event broker | Kafka topics, Redis Streams, DLQ | Fan-out nhiều consumers, retention độc lập |
| Read model/cache/search | Elasticsearch/OpenSearch, Redis | Copy không đồng bộ, permission scope khác |
| Test/staging database | Subset hoặc bản clone production | Developer quyền rộng, integration gửi dữ liệu ra bên ngoài |
| CI/test artifacts | Test reports, screenshots, logs, snapshots | Artifacts tải được bởi nhiều dự án/nhân viên |
| Diagnostic dump | Heap dump, core dump, query profiler | Có token, record payload và secrets đang ở memory |
| Support export | CSV gửi đối tác hoặc ticket attachment | Chia sẻ qua email/ticket, khó thu hồi |

Một lệnh “xóa dữ liệu khỏi production” **không tự động xóa tất cả các bản sao**. Phải biết bản copy đang ở đâu, ai quản lý, retention bao lâu và khả năng khôi phục/thu hồi.

## 4. Phân biệt năm mục tiêu bảo vệ

1. **Confidentiality (bí mật):** chỉ đúng chủ thể mới được xem nội dung.
2. **Integrity (toàn vẹn):** phát hiện hoặc ngăn sửa dữ liệu trái phép, không phục hồi bản backup bị giả mạo.
3. **Availability (sẵn dùng):** còn snapshot/log/keys để restore khi cần.
4. **Recoverability (khôi phục được):** thực sự phục hồi thành công với RPO/RTO yêu cầu.
5. **Data minimization & lifecycle:** không giữ dữ liệu quá nhu cầu, xóa/retire theo chính sách.

Các mục tiêu có thể xung đột:

- Backup **immutable 90 ngày** hỗ trợ chống ransomware nhưng có tác động đến yêu cầu xóa dữ liệu nhanh.
- Mã hóa với key không ai có thể truy cập làm nội dung bí mật, nhưng **không còn khả năng restore**.
- Snapshot nhiều khu vực giúp recovery nhưng mở thêm bề mặt truy cập và nghĩa vụ quản trị.
- CDC giữ sự kiện 30 ngày tăng khả năng replay nhưng lưu lịch sử dữ liệu nhạy cảm lâu hơn.

Vì vậy một phương án đúng phải xác định **business requirements, threat model, retention và trách nhiệm** trước khi chọn công nghệ.

## 5. Vòng đời một bản sao dữ liệu

```text
AUTHORIZATION
     |
     v
CREATE / EXTRACT
     |
     v
CLASSIFY + LABEL
     |
     v
ENCRYPT + TRANSFER
     |
     v
STORE + ACCESS CONTROL
     |
     +-- READ / RESTORE / TEST / REPLAY
     |
     v
AUDIT + VERIFY + ROTATE / REKEY
     |
     v
RETIRE / EXPIRE / DELETE
     |
     v
VERIFY DISPOSITION + HANDLE RETENTION EXCEPTIONS
```

Mỗi bước có một câu hỏi bảo mật:

| Bước | Câu hỏi |
|---|---|
| Cho phép | Ai được yêu cầu dump? Có ticket/mục đích/thời hạn không? |
| Tạo | Data scope có bị thu hẹp đúng tenant/collection không? |
| Phân loại | Có PII, bí mật, dữ liệu thanh toán, tokens, nội dung tự do không? |
| Truyền | Có TLS và endpoint xác thực? Có lưu file tạm ở nơi khác không? |
| Lưu | Mã hóa ở rest? IAM/bucket policy/ACL có tối thiểu không? |
| Sử dụng | Ai có quyền đọc/giải mã? Môi trường test có outbound network không? |
| Giám sát | Có audit trail, object access logs, integrity checks không? |
| Hết hạn | Ai xóa bản chính, bản replicate, temporary files và test copies? |

## 6. Threat model: không chỉ lo hacker bên ngoài

Những con đường dữ liệu có thể lộ:

- **Public object storage:** bucket/container hoặc object policy cấu hình sai.
- **Overprivileged credentials:** một tài khoản backup có cả quyền read/export/delete tất cả tenants.
- **Insider misuse:** người có quyền vận hành tải toàn bộ khách hàng thay vì subset được phê duyệt.
- **Supply-chain/CI compromise:** pipeline đọc secrets và artifacts, có thể tải dump.
- **Lost endpoint:** laptop hoặc USB chứa file plaintext.
- **Misconfigured integration:** staging gửi email/SMS đến khách hàng thật.
- **Shared observability:** structured logs/trace attributes chứa full document.
- **Data re-identification:** bộ test “ẩn tên” nhưng giữ email hash không salt và địa chỉ/zip code.
- **Ransomware:** xóa hoặc mã hóa cả production lẫn backups do cùng credential.
- **Retention drift:** topic CDC và DLQ giữ payload lâu hơn chính sách.
- **Cross-tenant confusion:** một bản dump chứa nhiều tenants nhưng test query chỉ gắn tenant ID giả.
- **Restore-to-less-secure:** backup được restore ở môi trường với authorization/TLS yếu hơn.

### Dữ liệu gốc và metadata đều cần bảo vệ

Tên object như `tenant-acme/export-2026-11-14/jane@example.com.json` có thể lộ tenant/customer dù payload đã mã hóa. Các thành phần **object key, topic name, filenames, labels, audit logs** đều nên tránh PII không cần thiết.

## 7. Phân loại trước khi export: dữ liệu nào được phép đi đâu?

Một policy minh họa:

| Phân loại | Ví dụ | Đích được phép | Cách xử lý |
|---|---|---|---|
| Public | Public catalog | Test/staging theo policy | Có thể sao chép, kiểm tra integrity |
| Internal | Metadata kỹ thuật không nhạy cảm | Nội bộ có IAM | Mã hóa, access logging |
| Confidential | Orders, contacts, addresses | Backup production, workload được cấp quyền | Least privilege, encryption, retention |
| Restricted | Credentials, tokens, bí mật riêng, dữ liệu nhạy cảm đặc biệt | Chỉ nơi có phê duyệt cụ thể | Thường **không export**; strip/redact/rotate |

Đây là bảng tham khảo, không thay classification policy của tổ chức. Mức độ nhạy cảm phải xét cả **khả năng kết hợp nhiều trường**.

### Phân loại theo trường nhưng kiểm soát cả collection

```json
{
  "orderId": "O-1001",
  "tenantId": "T-01",
  "amountMinor": 200000,
  "customer": {
    "name": "Nguyen Van A",
    "email": "person@example.invalid",
    "phone": "+84-000-000-000"
  },
  "paymentProviderToken": "REDACTED",
  "deliveryNotes": "free-text may contain sensitive information"
}
```

Ngay cả khi `paymentProviderToken` bị bỏ, `deliveryNotes` là nội dung tự do có thể chứa số điện thoại, địa chỉ và thông tin khác. Không đánh giá tính an toàn của bản dump chỉ bằng danh sách field top-level.

## 8. Dữ liệu dẫn xuất **kế thừa mức nhạy cảm của thông tin**, không phải môi trường

```text
Production orders (confidential)
      |
      +--> BSON dump        (still confidential)
      +--> snapshot         (still confidential)
      +--> CDC before-image (possibly more sensitive)
      +--> search index     (depends on fields, often confidential)
      +--> test clone       (still confidential until safely transformed)
```

Một output biến đổi có thể được **hạ phân loại** khi đã chứng minh rằng nội dung không còn đủ để nhận diện/khai thác nhạy cảm theo threat model, nhưng chỉ đổi tên file sang `sample-data.json` không có tác dụng gì.

### Những bản sao thường bị bỏ sót

- Dump tạm trong `/tmp`.
- Tập tin nén sau backup; bản plaintext trước nén vẫn còn.
- Cloud object version cũ.
- Thumbnails, screenshots, report previews.
- Object replication cross-region.
- Log của command-line có đường dẫn chứa token.
- Query profiler slow query chứa input values.
- Crash/heap dump.
- DLQ, retry topic và temporary CDC staging queue.

**Inventory và data lineage** phải nối nguồn→bản sao→consumer→chính sách xóa/khôi phục.

## 9. Data inventory và lineage: biết bản sao đang ở đâu

Một bản ghi catalog tối thiểu:

```yaml
artifact:
  id: backup-orders-2026-11-14
  kind: database-snapshot
  source:
    service: orders
    environment: production
    data_classification: confidential
  destination:
    account: production-backup-account
    region: approved-region
    storage_class: encrypted-object-storage
  owner: data-protection-team
  purpose: disaster-recovery
  created_at: "2026-11-14T02:00:00Z"
  expires_at: "policy-defined"
  encryption_key_reference: approved-kms-key-id
  restore_test_reference: restore-test-id
  legal_hold: false
```

Đây là metadata minh họa, không phải công thức config của một cloud. Tránh đưa raw secrets/credentials vào catalog.

### Tối thiểu cần tra được

1. Dữ liệu từ source nào, thuộc tenant/loại nào?
2. Artifact nằm ở region/account/bucket/path nào?
3. Ai có thể tạo, đọc, chia sẻ, restore, xóa và **giải mã**?
4. Lý do tồn tại và thời hạn giữ?
5. Có version/replica/copy offline nào khác?
6. Ai kiểm chứng integrity và restore?
7. Ai chịu trách nhiệm xóa hoặc giải quyết exception?

## 10. Least privilege: tách người tạo, người đọc và người xóa backup

Một tài khoản có tất cả quyền:

```text
db.readAll
snapshot.create
backup.readAll
backup.deleteAll
kms.decryptAny
objectStorage.makePublic
```

là điểm thất bại lớn. Nếu bị chiếm, attacker có thể **đọc dữ liệu, xóa backups và giải mã mọi bản copy**.

### Tách vai trò

| Vai trò | Được phép | Không mặc định được |
|---|---|---|
| Backup creator | Tạo snapshot và ghi vào đích chuẩn | Đọc/giải mã toàn bộ payload |
| Backup verifier | Kiểm tra manifest, integrity và test restore có kiểm soát | Public share, xóa backups production |
| Restore operator | Restore vào môi trường approved theo ticket | Restore tới tài khoản tùy ý |
| Data export approver | Duyệt scope/mục đích/retention | Tự export nếu policy đòi separation |
| Dev/test engineer | Dùng synthetic/sanitized dataset | Read production dump/keys |
| Security auditor | Đọc audit metadata theo quyền | Xem dữ liệu khách hàng không cần thiết |
| Break-glass operator | Quyền khẩn cấp thời hạn ngắn, có audit | Quyền thường trực không giám sát |

Tách quyền **IAM/storage**, **database credentials** và **KMS decrypt grants**. Quyền đọc object không nhất thiết bao gồm quyền giải mã, nhưng nếu hai quyền đều cấp rộng thì encryption không ngăn được data exfiltration.

## 11. Tenant isolation khi export/restore

Một hệ multi-tenant có thể lưu các tenants chung collection:

```json
{
  "_id": "ORDER-1001",
  "tenantId": "T01",
  "amountMinor": 500000
}
```

Nếu làm một subset export cho tenant T01:

```text
authorized principal -> verified tenant T01
        |
        v
query filter tenantId=T01
        |
        v
validate output scope
        |
        v
encrypted export in tenant-scoped destination
```

### Lỗ hổng dễ gặp

- Lấy tenant ID từ request body mà không kiểm tra membership.
- Query chính có tenant filter nhưng lookup/embed/join ở collection khác bỏ tenant.
- Cache token trộn tenant.
- File name T01 nhưng nội dung có document T02.
- Restore subset T01 vào staging dùng chung mà test user T02 đọc được.
- Audit logs ghi raw PII khi report export thành công.

### Kiểm tra đầu ra

Trước khi công bố export, có thể kiểm tra số lượng/canonical hashes theo tenant và **quét dấu hiệu scope mismatch**. Nếu một document thiếu `tenantId` hoặc có tenant khác, fail-closed/quarantine thay vì tự gán T01 để “cho đủ dữ liệu”.

### Physical snapshot khác logical tenant export

Snapshot ở mức volume/table/database chung thường **không thể coi là chỉ thuộc một tenant**; dù người request chỉ muốn tenant T01, snapshot có thể chứa toàn bộ tenants. Muốn chia sẻ một tenant, cần cơ chế logical extraction và kiểm soát field/scope riêng.

## 12. Object storage: private-by-default và cấu hình an toàn

Object storage là đích phổ biến cho dumps, snapshot exports và test artifacts. Các lỗi có thể đến từ **bucket policy, object ACL, signed URL, role trust và replication**.

### Một kiến trúc tham khảo

```text
Production NoSQL
      |
      | Backup role, read source + write only to approved prefix
      v
Private object storage / backup account
      |
      +-- default deny public access
      +-- TLS-only transfer policy
      +-- encryption with approved key
      +-- object versioning / retention lock if needed
      +-- audit object reads / deletes
      +-- replication to approved recovery account/region
      |
      v
Isolated restore workflow / time-limited grant
```

### Các kiểm soát cốt lõi

1. **Chặn public access** ở cấp account/bucket/container theo nền tảng hỗ trợ.
2. Không dùng wildcard cho bất kỳ principal nào đọc mọi artifact khi không cần.
3. Policy yêu cầu TLS, encryption và key phù hợp khi upload.
4. Hạn chế nguồn kết nối hoặc service endpoints khi nền tảng cung cấp và threat model đòi hỏi.
5. Giới hạn destination prefix/account/region.
6. Log access và thay đổi chính sách; bảo vệ audit logs khỏi sửa/xóa.
7. Sử dụng **time-bound grants** cho restore, không chia sẻ long-lived access keys.
8. Theo dõi public exposure, cross-account shares, policy drift và bất thường tải xuống khối lượng lớn.
9. Có quy trình revoke access và rotation khi credentials bị lộ.

### Tránh nhầm “bucket private” với “dữ liệu luôn an toàn”

Một IAM principal quá rộng, một function CI bị chiếm, hoặc key được cấp cho mọi developers vẫn có thể đọc object private. Phải xem **đường đi thực tế của quyền** từ principal → object read → decrypt → export.

## 13. Signed URLs và temporary sharing

Một pre-signed URL là **bearer capability**: ai cầm URL hợp lệ thường có thể thực hiện thao tác được ký trong thời hạn/điều kiện đã cấp.

Rủi ro:

- URL xuất hiện trong chat, support ticket, browser history, referrer hoặc log.
- TTL quá dài.
- URL cho phép đọc một dump full production thay vì tập subset.
- Không có revocation tức thì đơn giản khi URL đã phát ra, tùy cơ chế/storage platform.
- Consumer copy dữ liệu về nơi khác trước khi URL hết hạn.

### Tối thiểu cần

- Phát URL **chỉ sau authorization** và approval phù hợp.
- Object/key cụ thể, method cụ thể, thời gian ngắn.
- Không đặt secrets và PII trong URL.
- Chặn caching/relogging URL ở client/logging layer khi có thể.
- Bảo vệ destination bằng encryption và audit downloads.
- Với dữ liệu nhạy cảm cao, cân nhắc mediated download service có policy/authentication per request thay vì share link trực tiếp.

**Hết hạn URL không xóa các file người nhận đã tải.** Trách nhiệm hậu chia sẻ phải được xác định rõ.

## 14. Encryption at rest: hiểu giới hạn bảo vệ

Mã hóa lưu trữ có thể được thực hiện tại:

```text
Database storage layer
       |
       v
Volume/snapshot encryption
       |
       v
Object storage server-side encryption
       |
       v
Optional application-side encryption of exported artifact
```

Các lớp này bảo vệ những mối đe dọa khác nhau. **Server-side encryption** thường chống đọc dữ liệu trên thiết bị lưu trữ trái phép nhưng không ngăn một principal đã được cấp quyền đọc và giải mã qua API hợp lệ.

### Cách chọn

| Cách mã hóa | Phù hợp khi | Lưu ý |
|---|---|---|
| Storage-managed encryption | Bảo vệ mặc định, vận hành đơn giản | IAM/ACL vẫn quan trọng |
| Customer-managed KMS key | Cần kiểm soát key grants, audit/rotation | Dễ bị ảnh hưởng nếu key disabled/deleted |
| Client-side envelope encryption | Tách nội dung khỏi storage operator/quyền đọc object | Cần key lifecycle, restore tooling và cryptographic metadata |
| Field-level encryption | Một số fields rất nhạy cảm, phân quyền sâu | Query/index và sharing semantics phức tạp |

### Không tự thiết kế thuật toán

Nếu cần application-side encryption, dùng thư viện/SDK uy tín hỗ trợ **authenticated encryption** (ví dụ AES-GCM theo API và nonce policy đúng) thay vì tự tạo XOR, AES-ECB hoặc một hàm hash làm “mã hóa”.

Hash một giá trị không phải encryption có thể giải mã. Base64, nén gzip hoặc đổi extension file không phải cơ chế bảo mật.

## 15. Envelope encryption: khóa dữ liệu và khóa bao

Một sơ đồ:

```text
Random Data Encryption Key (DEK)
         |
         +-- encrypt dump -> encrypted_data
         |
         +-- encrypt/wrap DEK with KMS Key Encryption Key (KEK)
                              |
                              v
                 encrypted_dek + key_ref

Stored artifact:
  ciphertext
  encrypted_dek
  algorithm / nonce / AAD metadata
  integrity/authentication tag
  storage manifest
```

Khi restore, ứng dụng được phép có thể nhờ KMS unwrap DEK, rồi giải mã artifact theo cipher metadata.

### Cần phân biệt

- **DEK:** khóa dùng mã hóa payload.
- **KEK/KMS key:** khóa bảo vệ DEK, có policy riêng.
- **Ciphertext:** payload sau mã hóa.
- **AAD:** metadata được xác thực cùng ciphertext nếu protocol hỗ trợ, có thể gắn backup ID, schema, tenant/scope.
- **Authentication tag:** phát hiện payload/metadata bị sửa đổi không hợp lệ.

Không tự giả định một file được mã hóa nghĩa là integrity đã được xác thực: chế độ encryption phải hỗ trợ authentication hoặc có một cơ chế integrity riêng đúng threat model.

### Backup metadata cũng cần bảo vệ

Nếu attacker sửa manifest để trỏ bản backup sang source/tenant khác, chỉ encrypted payload chưa bảo vệ toàn bộ workflow. Cần verify metadata binding, ownership, signing/authentication, schema và destination context.

## 16. KMS: key policy, grants và khả năng phục hồi

Các lỗi phổ biến:

- Backup được mã hóa bằng một key không còn quyền decrypt khi disaster xảy ra.
- Một key thuộc môi trường development được dùng để mã hóa production.
- Restore role có quyền object read nhưng không có quyền unwrap DEK.
- Quá nhiều nhân viên được cấp `kms:Decrypt` trên toàn bộ keys.
- Key bị schedule deletion trong khi bản backup cũ vẫn cần.
- Cross-region copy giữ object nhưng không có key tương ứng ở region phục hồi.
- Mất key identifier/version/metadata nên không biết key nào giải mã.

### Quy tắc

1. Phân quyền backup create, restore và key admin **riêng** khi khả thi.
2. Gắn key với environment/data classification/approved recovery scope.
3. Quản lý key references và quyền cross-account/cross-region có chủ đích.
4. Rotate keys với kế hoạch đọc được **backups lịch sử**.
5. Test restore định kỳ qua đường quyền khẩn cấp đã phê duyệt.
6. Log KMS key usage, grant changes, unexpected decrypt spikes.
7. Chỉ xóa key khi không còn artifact/hợp đồng retention nào cần đến.

### Key rotation không đồng nghĩa tự động re-encrypt mọi backup

Một hệ KMS có thể luân chuyển phiên bản key dùng cho operations mới trong khi vẫn hỗ trợ decrypt artifacts cũ; một migration khác có thể phải re-wrap DEK hoặc re-encrypt toàn bộ archive. Cần hiểu provider/SDK semantics, không mặc định “đã rotate” nghĩa bytes cũ được mã hóa lại.

### Crypto-shredding phải có phạm vi đúng

Hủy key có thể làm ciphertext không thể giải mã **nếu không còn bản sao key hoặc plaintext**, nhưng cũng phá hủy khả năng restore. Với key được nhiều tenant/backups dùng chung, hủy key để đáp ứng yêu cầu xóa **một tenant** có thể gây mất dữ liệu của tenant khác. Cần key hierarchy và data lifecycle được thiết kế từ đầu.

## 17. Encryption in transit: từng hop đều cần trust boundary

```text
Database -- TLS --> Backup worker
   Worker -- TLS --> Object storage
   Worker -- TLS --> Key management
   Restore tool -- TLS --> Isolated target database
```

Điểm cần đánh giá:

- TLS phiên bản/kiểm tra certificate chain/hostname hợp lệ.
- mTLS hoặc workload identity nếu hệ yêu cầu.
- Không bật tùy chọn “skip certificate validation” để sửa lỗi connectivity.
- Credentials không đưa vào command line/log/URL.
- Network egress chỉ cho destinations được phép.
- Proxy/load balancer có được phép xem plaintext không?
- Retry không viết nội dung nhạy cảm ra debug logs.

### Database TLS chưa bảo vệ file tạm

Nếu worker nhận dữ liệu an toàn qua TLS nhưng ghi plaintext `dump.json` vào volume shared trước khi upload, một threat khác đã xuất hiện. Có thể stream trực tiếp qua encrypting writer hoặc dùng encrypted ephemeral disk với lifecycle ngắn, tùy nền tảng và định dạng backup.

## 18. File tạm, container và máy phát triển

Một lệnh export thường tạo files tại:

```text
/tmp/orders-dump
/workspace/backup.archive
CI runner workspace
developer Downloads folder
container writable layer
shell command history
```

### Kiểm soát

- Dùng isolated job/runner được cấp quyền, không export qua laptop khi không cần.
- Hạn chế OS file permissions và quyền mount.
- Tránh ghi ra shared volume, hostPath và world-readable temp folders.
- Encrypt ephemeral storage nếu phù hợp.
- Không cho upload artifacts tự động từ working directory chứa dữ liệu thật.
- Xóa temporary files theo lifecycle và log completion.
- Đề phòng crash dump/heap dump có chứa DB credentials và record payload.

### “Xóa file” có chắc dữ liệu bị xóa vật lý?

Trên SSD, snapshots, copy-on-write filesystems, cloud blocks và các bản replica, xóa path không đồng nghĩa đảm bảo mọi byte vật lý bị ghi đè. Dùng lifecycle của managed storage, cryptographic erasure trong phạm vi key phù hợp, và quy trình disposition của nền tảng. Không tự tuyên bố tuân thủ xóa bằng một lệnh `rm` đơn giản.

## 19. Integrity: mã hóa không đủ nếu không xác minh bản backup

Một bản dump có thể:

- Truyền thiếu một segment.
- Bị truncation.
- Mất file manifest.
- Bị ghi đè nhầm version.
- Không khớp database schema hoặc snapshot point.
- Bị attacker thay thế bằng ciphertext khác.

### Manifest tham khảo

```json
{
  "backupId": "orders-backup-20261114-0200",
  "sourceClusterId": "orders-cluster-A",
  "scope": "approved-database-scope",
  "createdAt": "2026-11-14T02:00:00Z",
  "format": "document-archive-v2",
  "encryption": {
    "algorithm": "approved-aead",
    "keyReference": "approved-key-id"
  },
  "objects": [
    {
      "name": "part-0001.enc",
      "sizeBytes": 1048576,
      "sha256": "placeholder-digest"
    }
  ],
  "snapshotPosition": "source-specific-consistent-position"
}
```

Manifest này là ví dụ định dạng; digest placeholder không có giá trị kiểm tra. **SHA-256 không có key** phát hiện file thay đổi do lỗi truyền/nhầm lẫn nếu digest được lưu ở nơi tin cậy, nhưng attacker có thể thay **cả file lẫn digest**. Nếu threat model có attacker ghi vào destination, cần manifest được xác thực/được ký hoặc lưu trong trust boundary khác.

### Kiểm tra trước khi restore

1. Source/backup ID và scope chính xác.
2. Artifact complete, size và danh sách parts đúng.
3. Integrity hashes/signatures hoặc AEAD tags hợp lệ.
4. Key references và quyền decrypt hợp lệ.
5. Backup format/schema/version tương thích restore tooling.
6. Snapshot/log boundaries được hiểu đúng.
7. Restore vào đúng môi trường, có access isolation.

## 20. Snapshot consistency: backup bí mật nhưng vẫn phải phục hồi đúng

Một NoSQL cluster đang có writes:

```text
T0 Order O1 -> PENDING
T1 Payment P1 -> PAID
T2 Order O1 -> PAID
```

Nếu dump lần lượt các collections tại những thời điểm khác nhau, backup có thể chứa `Order=PENDING` nhưng `Payment=PAID`, hoặc ngược lại.

**Đó là vấn đề tính nhất quán của snapshot**, khác vấn đề bảo mật nhưng rất quan trọng để xác định backup có thể dùng được khi khôi phục.

### Các mô hình

| Loại | Phạm vi nhất quán | Lưu ý |
|---|---|---|
| File-level copy | Theo file/hệ thống lưu trữ | Chưa chắc nhất quán database khi đang write |
| Logical dump trực tiếp | Theo từng query/collection, tùy tool | Có thể không có global snapshot |
| DB-coordinated snapshot | Theo consistency boundary của engine | Phải hiểu replicas/shards/transactions |
| Snapshot + change log/PITR | Phục hồi đến mốc log đã xác định | Cần giữ cả snapshot, logs và keys |

### Trước khi tuyên bố “khôi phục được”

Test read/write consistency, schema constraints, representative queries, CDC replay boundary, index rebuilding và tenant permission. Một lệnh restore có exit code 0 không đủ để khẳng định dữ liệu đúng nghiệp vụ.

## 21. Backup immutability và bảo vệ trước ransomware

Ransomware hoặc credential compromise có thể xóa cả production và backups nếu chúng dùng cùng principal.

Một kiến trúc tốt có thể có:

```text
Production account
    |
    +-- application database (write operations)
    |
    +-- backup producer role (write approved backup objects)
              |
              v
       Separate backup account
          - deny normal deletion
          - retention lock / WORM where required
          - separate key administration
          - independent audit logs
          - isolated recovery process
```

### Immutable không có nghĩa unreadable

Object lock/WORM giúp hạn chế sửa/xóa trong một thời gian, nhưng nếu read/decrypt quyền quá rộng thì attacker vẫn có thể **tải dữ liệu**. Cần cả confidentiality, not just integrity/retention.

### Immutable cũng tạo nghĩa vụ lifecycle

Nếu lưu immutable 1 năm nhưng policy data minimization chỉ cho phép 90 ngày, cần xử lý xung đột **trước khi cấu hình**, cùng legal/compliance owners và mô hình exception. Không tự tăng retention dài vô hạn chỉ vì “an toàn hơn”.

### Restore phải độc lập với production credentials

Nếu muốn khôi phục sau khi production IAM/KMS bị compromise, recovery path phải đủ tách biệt, có cơ chế break-glass và validation. Đừng đợi đến lúc incident mới phát hiện mọi backup đều dùng key đã bị vô hiệu.

## 22. Retention: snapshot, dump, CDC và test copies không cùng thời hạn

Một policy ví dụ:

| Loại bản sao | Căn cứ quyết định thời gian giữ |
|---|---|
Daily snapshots | RPO/RTO, lịch sử sự cố, legal requirements |
PITR logs | Recovery window, storage headroom, latency |
Ad hoc debug dump | Thời gian giải quyết ticket, tối thiểu cần thiết |
CDC topics | Replay window, consumer lag, reprocessing needs |
DLQ/retry topic | Thời gian điều tra, redrive và dedup horizon |
Test fixtures | Release/test purpose, mức anonymization |
Temporary export artifacts | Job completion và approved download window |
Audit logs | Compliance/security incident investigation |

Không có **một số ngày đúng cho tất cả**. Đặt retention theo loại dữ liệu và mục đích, có automation hết hạn, audit về disposition và quy trình legal hold.

### Versions và replicas

Xóa object hiện tại có thể vẫn còn **object version cũ** hoặc bản replicate ở region khác. Retention logic cần bao gồm versions, delete markers, snapshots, DLQ và downstream copies. Kiểm tra effective deletion, không chỉ HTTP response của một API delete.

### Dedup và replay

Nếu CDC có thể replay sự kiện sau 30 ngày nhưng event-id ledger chỉ giữ 3 ngày, worker có thể áp tác dụng nghiệp vụ trùng. Retention bảo mật phải phối hợp correctness: giảm thời gian giữ dữ liệu nhưng vẫn có strategy an toàn cho replay/restore.

## 23. Data deletion và backup lịch sử: giải quyết xung đột bằng policy

Một khách hàng yêu cầu xóa dữ liệu khỏi ứng dụng:

```text
Primary NoSQL record deleted
  |
  +-- Redis cache?
  +-- Search index?
  +-- Kafka topic / CDC before image?
  +-- RDB/AOF/SSTable remnants?
  +-- Snapshots / PITR archive?
  +-- Test/staging datasets?
  +-- Analytics materialized views?
```

### Những câu hỏi phải trả lời

1. Có cơ sở pháp lý/chính sách nào yêu cầu giữ bản sao trong thời hạn nhất định?
2. Backup được phép tồn tại đến expiry nhưng **không được dùng để phục hồi nội dung đã xóa** mà không replay deletion events không?
3. Có thể tách key theo tenant/record để hỗ trợ crypto-erasure mà không phá khả năng restore hợp lệ không?
4. Restore vào một snapshot lịch sử có thể **hồi sinh dữ liệu đã xóa**; quy trình sau restore sẽ áp các tombstone/deletion records như thế nào?
5. Các test copies có được kiểm soát bởi inventory và deletion workflows không?

### Không hứa “đã xóa mọi nơi” khi chưa chứng minh

Quy trình cần định nghĩa phạm vi, thời hạn, ngoại lệ retention, bản replicate và cách xác minh. Nếu có yêu cầu pháp lý theo khu vực, tham vấn người chịu trách nhiệm quyền riêng tư/pháp lý để xác định nghĩa vụ cụ thể; không suy một quy tắc chung áp cho tất cả tổ chức.

## 24. MongoDB: dump, restore, oplog và snapshots

MongoDB có nhiều con đường tạo bản sao:

- `mongodump`/`mongorestore` cho logical backup/restore.
- Managed snapshots / cluster snapshots tùy deployment.
- Filesystem/volume snapshot phối hợp với database consistency.
- Oplog và Change Streams dùng cho replication/CDC.
- Database profiler, audit logs, server logs và diagnostic data.

### Logical dump không tự động an toàn

Một tập `.bson` hoặc archive chứa raw document fields vẫn nhạy cảm, dù không phải JSON người nhìn đọc ngay. Có thể dùng công cụ giải mã BSON hoặc restore vào DB khác để đọc.

```text
mongodump -> dump/orders.bson -> archive.gz -> object storage
               ^                  ^              ^
           sensitive           sensitive      sensitive
```

Nén **không phải mã hóa**. Nếu dùng file nén, đặt policy mã hóa/ACL cho cả file tạm và artifact cuối, không chỉ file đích object storage.

### Quyền

Backup service account nên có các role/quyền tối thiểu cần cho loại backup và cluster scope. Restore service account khác, chỉ dùng trong workflow được duyệt; không dùng app runtime credential có full admin cho cả dump lẫn restore.

### Snapshot nhất quán

Logical dumps các collections trong lúc source đang write có thể không tương ứng một snapshot transaction-consistent của toàn bộ hệ. Các tùy chọn/dải oplog hoặc snapshot mechanics phụ thuộc topology/phiên bản và thời điểm; cần dùng hướng dẫn hỗ trợ đúng deployment, không tự ghép timestamp của các files rồi gọi là point-in-time consistent.

### Oplog / Change Streams

Oplog và change events có thể tiết lộ document keys, các trường đã cập nhật, và trong những cấu hình có before/after images, nội dung nhạy cảm cả trước khi xóa. Chỉ người/connector cần thiết mới được quyền truy cập, và phải giữ retention phù hợp. **Đổi read concern không thay authorization của bản dump.**

### Restore test

Restore vào cluster cô lập, vô hiệu hóa outbound integrations, áp access policy phù hợp trước khi cấp quyền người kiểm thử. Không chụp ảnh màn hình hoặc đính kèm record thật vào ticket để chứng minh restore thành công.

## 25. Redis: RDB, AOF, replication và backup chứa dữ liệu sống

Redis có các cơ chế lưu dữ liệu như RDB snapshots và Append Only File (AOF), tùy cấu hình/phiên bản.

```text
Redis memory:
  session token
  cache of customer profile
  payment retry state
  rate limit key

RDB snapshot / AOF:
  may preserve those values
```

### Các hiểu lầm

- “Redis chỉ là cache nên không có dữ liệu nhạy cảm”: sai nếu ứng dụng bỏ session/PII/credentials vào value.
- “Key đã hết TTL thì không thể xuất hiện trong mọi bản backup cũ”: sai, một snapshot lịch sử có thể chứa nó.
- “RDB là binary format nên khó đọc”: không phải biện pháp bảo mật.
- “Replica chỉ có quyền read nên an toàn”: replica vẫn có thể chứa full sensitive dataset.

### Kiểm soát

1. Trước hết **không lưu secret/plaintext PII nếu không cần**; dùng opaque tokens và TTL phù hợp.
2. Bảo vệ file RDB/AOF, backups và replica links theo phân loại dữ liệu.
3. Dùng ACL/authentication, TLS nếu được triển khai và cấu hình đúng.
4. Hạn chế quyền thay đổi persistence/dump locations.
5. Tránh đưa raw keys có email/customer IDs vào logs và dashboards.
6. Mã hóa storage snapshots và destination object storage.
7. Phân biệt Redis role cache có thể tái tạo với Redis được dùng như nguồn trạng thái quan trọng: RPO/restore requirements khác nhau.

### Snapshot và consistency

RDB phản ánh một thời điểm theo cơ chế snapshot, trong khi AOF ghi chuỗi operations để replay theo persistence settings. Cả hai có durability/restore semantics phụ thuộc cấu hình; không tự lấy chúng làm bằng chứng không mất bất kỳ write nào.

## 26. Cassandra: SSTables, nodetool snapshot và commitlog

Với Cassandra, bản snapshot thường chứa SSTable files hoặc links/hardlinks đến dữ liệu trên disk theo công cụ/phiên bản. Nội dung storage vật lý có thể chứa:

- Rows/columns của nhiều partitions/tenants.
- Tombstones.
- Data có lịch sử xóa chưa được compact/garbage-collected theo semantics.
- Secondary-index/materialized-view data nếu lưu trong phạm vi snapshot liên quan.

### Rủi ro bảo mật riêng

Một file SSTable copy từ node production có thể được đọc offline qua tooling thích hợp. **Không coi file unreadable bằng text editor là đã mã hóa.**

### Quy trình an toàn

```text
DBA/backup job obtains approved snapshot
   |
   v
Identify keyspace/table/tenant scope
   |
   v
Encrypt + transfer through controlled channel
   |
   v
Private backup storage with retention and audit
   |
   v
Restore into isolated cluster with expected schema/config
```

### Consistency trong distributed storage

Snapshot từ các nodes tại những thời điểm khác nhau không tự tạo một **global transaction snapshot**. Quorum/replication, repair, compaction, schema version và commitlog replay có ảnh hưởng đến recovery; cần dùng backup strategy được hỗ trợ cho topology. Không tự định nghĩa “copy SSTables của 2/3 nodes là hoàn chỉnh” chỉ từ số replicas.

### Log lifecycle

Commitlog/snapshots có thể giữ byte dữ liệu đã được ghi/xóa trong khoảng thời gian nhất định. Retention và data deletion policy phải cân nhắc cả physical copies/tombstones, không chỉ SELECT query trên primary data model.

## 27. DynamoDB: on-demand backup, PITR và export

DynamoDB có các tính năng managed backup, point-in-time recovery và export workflows tùy khả năng/điều kiện dịch vụ. Một export có thể tạo artifacts trong S3/object storage theo quyền IAM/service role.

### Trust boundaries

```text
DynamoDB table
     |
     +-- backup/PITR service-managed copies
     |
     +-- export job --> S3 bucket/prefix
                           |
                           +-- IAM bucket policy
                           +-- KMS key policy
                           +-- data classification/retention
```

Không xem “table IAM đã đúng” là đủ. Khi xuất ra object storage, quyền đọc S3 + KMS decrypt và replication/sharing chính là security surface mới.

### Tenant scoping

Managed export/table backup có thể bao phủ **toàn bảng**, không phải tự động lọc tenant. Nếu table shared nhiều tenants, đừng cung cấp table snapshot cho một khách hàng chỉ yêu cầu dữ liệu của họ.

### PITR có thể tái dựng dữ liệu đã xóa

Một restore về timestamp trước khi xóa có thể chứa records không còn trong live table. Quy trình khôi phục phải có policy kiểm soát truy cập và **deletion replay/reconciliation** khi phù hợp nghĩa vụ dữ liệu.

### Xác minh quyền service

Export/read permissions, trust relations giữa DynamoDB và S3/KMS, account/region và encryption grants khác với quyền truy vấn dữ liệu của client app. Thường nên có job role chuyên trách và scoped destination, không trao quyền export toàn bộ tables cho CI/test role.

## 28. Elasticsearch/OpenSearch: snapshot repository và index bản sao

Search indexes có thể chứa dữ liệu dạng:

- Document source fields.
- Tokens/inverted-index terms.
- Doc values/stored fields.
- Searchable metadata, geographic coordinates và user events.
- Derived/embedded data, vectors hoặc content snippets.

Một **snapshot repository** có thể lưu các index artifacts ở object storage hoặc backend khác. Repository permissions phải được bảo vệ; đọc snapshot có thể cho phép phục dựng dữ liệu index, dù ứng dụng UI chỉ trả một phần fields.

### Pitfalls

- Index document có field nhạy cảm `_source`, nhưng API filter nó khỏi response; snapshot vẫn chứa dữ liệu đó.
- Query logs slow search chứa search terms liên quan PII.
- Snapshot repository được dùng chung dev/prod và cấp quyền quá rộng.
- Restore tạo index alias trỏ nhầm dữ liệu production sang staging.
- Index tồn tại lâu hơn source retention.

### Checklist

1. Chỉ index fields cần cho search.
2. Phân loại và mã hóa snapshots.
3. Ràng buộc repository access, namespace và restore privileges.
4. Kiểm tra alias/role mappings/tenancy khi restore.
5. Đặt retention cho index snapshots và old indices.
6. Đo reconciliation: xóa ở source phải dẫn tới xóa/redact read model theo policy.

Không coi search cluster green/healthy là dấu hiệu access policies hoặc dữ liệu index đều đúng.

## 29. Graph databases: graph dump có thể suy lộ quan hệ

Trong graph database, ngay cả khi node properties như tên/email được mask, **cấu trúc quan hệ** có thể nhạy cảm:

```text
Customer_001 --TRANSFERRED_TO--> Account_003
Customer_001 --MEMBER_OF-----> Risk_Group_17
Account_003  --LINKED_TO-----> Investigation_42
```

Nếu dùng graph dump để test recommendations, việc giữ topology đầy đủ có thể tiết lộ association hiếm và giúp tái định danh.

### Các biện pháp

- Dùng graph tổng hợp/synthetic topology khi có thể.
- Nếu phải subset graph, đánh giá cả **relationships, paths, degree distributions, timestamps**.
- Đánh giá privacy risk với những nodes/edges hiếm.
- Tách quyền export graph khỏi quyền chỉ query một neighborhood.
- Bảo vệ backup/dump files, snapshots và query logs.
- Test restore vào database cô lập; không cho graph explorer staging quyền truy cập production artifacts.

### Vì sao masking labels chưa đủ?

Một người có thể suy ra identity nhờ một pattern quan hệ hiếm (ví dụ chỉ một account liên kết tới 12 tổ chức cụ thể). Pseudonymized node IDs không biến graph thành anonymous.

## 30. CDC/change logs có thể nhạy cảm hơn document hiện tại

Một document trước khi cập nhật:

```json
{
  "customerId": "C01",
  "email": "old-address@example.invalid",
  "token": "SENSITIVE-REDACTED",
  "status": "ACTIVE"
}
```

Ứng dụng cập nhật để xóa `token`:

```json
{
  "customerId": "C01",
  "email": "new-address@example.invalid",
  "status": "ACTIVE"
}
```

Nếu CDC source hoặc connector cấu hình capture full before-image/after-image, log có thể giữ **cả token cũ và địa chỉ cũ**, dù app current document đã xóa.

### Các dạng dữ liệu trong change events

| Event type | Những gì có thể lộ |
|---|---|
| Insert | Full new document hoặc fields được chọn |
| Update | Modified fields, document key, pre/post image tùy source config |
| Delete | Document key, tombstone, previous image trong những chế độ hỗ trợ |
| Schema/config change | Collection names, field names, data model |
| Transaction metadata | Correlation IDs, session/time, actor information |
| Error/retry event | Raw payload hoặc cause chứa field nhạy cảm |

### Không kết luận mọi CDC đều có before images

Nội dung thực tế phụ thuộc NoSQL engine, connector, options, privileges và version. **Threat model phải đọc event schema và cấu hình capture thực tế**, không mặc định full document luôn có hoặc không có.

### Xóa field khỏi live record không xóa log cũ

Retention/compaction/snapshot của source log, broker và DLQ độc lập. Khi thay chính sách dữ liệu nhạy cảm, phải kiểm tra lịch sử đã được phát vào những hệ nào.

## 31. CDC security: least-privilege connector và topic ACL

Pipeline:

```text
NoSQL source
     | read/change-stream privilege
     v
CDC connector
     | broker producer principal
     v
Encrypted broker topic
     | consumer group permissions
     +----> Search projector
     +----> Analytics pipeline
     +----> Fraud service
     +----> Test listener?  <-- high-risk
```

### Quyền theo hop

- Source role: chỉ đọc change streams/collections thực sự cần.
- Connector workload identity: secrets được lưu trong secret manager, không trong logs/config plaintext.
- Broker ACL: producer chỉ ghi topics approved; consumer chỉ đọc topics cần thiết.
- Consumer group permissions: không trao read toàn cụm cho mỗi microservice.
- Transport encryption và cluster authentication.
- Topic retention và encryption/storage policies.
- Audit event reads, group membership, new subscriptions và unusual throughput.
- Không cho dev/test identity dùng quyền subscribe production topic có PII.

### Tách topic theo độ nhạy

Một topic `all-changes` chứa raw full documents đòi mọi consumers có quyền thấy toàn bộ dữ liệu. Nếu chỉ cần event `OrderPaid(orderId, revision)`, có thể thiết kế **outbox business event tối thiểu**, phân loại topic theo audience và cấp quyền riêng.

### Không dùng producer payload masking như biện pháp duy nhất

Nếu raw CDC connector gửi topic internal đã có PII rồi một consumer downstream mới mask, các consumers khác vẫn có thể đọc raw. Nếu cần boundary sanitized, triển khai transform được kiểm soát ở **đúng nơi chuyển trust boundary**, hạn chế ACL của raw topic và audit consumer list.

## 32. Outbox: publish event tối thiểu thay vì raw document

Một transactional outbox event:

```json
{
  "eventId": "EV-9081",
  "eventType": "OrderPaid",
  "tenantToken": "tenant-scoped-token",
  "orderId": "O-1001",
  "orderRevision": 8,
  "occurredAt": "2026-11-14T09:00:00Z"
}
```

Có thể đủ cho consumer tra cứu qua API được phân quyền, không cần gửi:

```json
{
  "customerEmail": "customer@example.invalid",
  "deliveryAddress": "raw personal address",
  "paymentToken": "REDACTED"
}
```

### Đánh đổi

**Event tối thiểu** giảm exposure nhưng consumer có thể cần gọi lại source, tăng coupling/latency và gặp version inconsistency nếu không có snapshot/version-aware API. Với hệ cần payload trong event, chọn fields cụ thể, encrypt nếu thích hợp và giới hạn consumer authorization.

### Không dùng event bus làm cơ chế vượt quyền

Nếu ứng dụng không cho service A đọc customer contact từ database, đừng mặc định service A được đọc contact chỉ vì topic CDC broadcast. **ACL trên broker và phân loại nội dung sự kiện** phải tương ứng.

## 33. Snapshot của change logs và broker backups cũng chứa dữ liệu nhạy cảm

Khi bảo vệ Kafka/stream, đừng chỉ nhìn broker live:

```text
Production CDC topic
    |
    +-- broker log segments on disks
    +-- tiered storage / broker snapshots
    +-- mirrored cluster cross-region
    +-- compacted topics / tombstones
    +-- retry topic
    +-- dead-letter topic
    +-- analytics sink
    +-- local consumer debug dump
```

### Retention và log compaction

Log compaction thường giữ state/latest record theo key và có semantics riêng cho tombstones, nhưng **không phải công cụ đáp ứng mọi yêu cầu xóa dữ liệu nhạy cảm**. Các segment cũ, mirrored copies, backups, DLQ và consumers khác có retention độc lập.

### Tránh gửi PII vào message keys

Broker key có thể xuất hiện trong logs, partition routing và monitoring. Không đưa email/phone dạng plaintext làm key nếu không cần; dùng stable surrogate IDs hoặc tokenization policy.

### Schema registry/history

Schema definitions có thể tiết lộ tên fields và data model, nhưng thường không chứa record values. Dù vậy schema history/log/config có thể lộ database names, credentials bị cấu hình sai, hoặc metadata nhạy cảm. Áp access controls và secret scanning.

## 34. Dead-letter queue (DLQ) thường bị quên khi xóa dữ liệu

Một pipeline bị lỗi decode và lưu raw event vào DLQ:

```json
{
  "eventId": "EV-9081",
  "error": "Unsupported schema version",
  "originalPayload": {
    "customerEmail": "customer@example.invalid",
    "notes": "sensitive user text"
  }
}
```

Nếu DLQ retention 180 ngày trong khi main topic 7 ngày, **đường lỗi giữ PII lâu hơn đường chính**.

### Thiết kế DLQ an toàn

1. Chọn lưu **reference**, encrypted payload hoặc redacted subset khi đủ để triage.
2. Restrict read access vào DLQ theo đội có trách nhiệm.
3. Đặt retention dựa trên nhu cầu xử lý/khả năng replay.
4. Không log toàn bộ original event vào exception traces.
5. Có workflow redrive với idempotency, authorization và audit.
6. Xử lý compliance deletion đối với DLQ/backup copies theo policy.
7. Giám sát DLQ growth và consumer error classes mà không đưa PII vào metric labels.

### Lỗi kiểu “poison event” không cho phép bỏ qua bảo mật

Trong lúc khôi phục sự cố, không gửi toàn bộ payload qua kênh chat công khai để “nhờ xem nhanh”. Dùng kênh truy cập được kiểm soát và redacted diagnostic fixtures.

## 35. Test data: mặc định tạo synthetic, không clone production

Một test database lý tưởng chứa **dữ liệu giả có cấu trúc hợp lệ**, đủ để kiểm tra logic, scale và edge cases, nhưng không chứa PII/thông tin bí mật thật.

```text
Schema + business constraints + distributions (approved)
                         |
                         v
                 Synthetic generator
                         |
                         v
                  Test fixture set
                         |
             +-----------+-----------+
             |                       |
          CI tests               Staging tests
             |                       |
         disposable             isolated, TTL
```

### Vì sao synthetic data thường là lựa chọn đầu tiên?

- Không cần chuyển raw production PII qua trust boundary.
- Dễ tạo edge cases chưa từng xảy ra trong production.
- Dễ tái lập bug từ seed.
- Có thể kiểm soát lượng records, tenant skew, document sizes.
- Có thể tự động reset CI.
- Hạn chế rủi ro gửi notifications/payment tới người thật.

### Giới hạn

Dữ liệu synthetic quá đơn giản có thể không phát hiện performance bugs liên quan distribution, graph topology hoặc text length. Có thể tạo **phân bố thống kê giả lập** dựa trên aggregate metrics được phép dùng, nhưng tránh sao chép records hiếm hoặc quá chi tiết đến mức giúp nhận dạng người thật.

## 36. Phân biệt synthetic, anonymization, pseudonymization và masking

| Phương pháp | Mô tả | Bảo đảm cần hiểu |
|---|---|---|
| **Synthetic generation** | Sinh records giả từ model/constraints | Chỉ an toàn khi generator không memorizes hoặc phát lại dữ liệu thật |
| **Masking** | Ẩn/thay một số trường, ví dụ email, name | Các fields khác vẫn có thể định danh |
| **Pseudonymization** | Thay identifiers bằng tokens ổn định | Có thể liên kết/tái định danh khi có mapping/key hoặc side information |
| **Tokenization** | Thay dữ liệu nhạy cảm bằng token, có thể qua vault | Vault/mapping phải được bảo vệ; token có thể có quyền truy cập |
| **Anonymization** | Biến đổi đủ để giảm khả năng nhận diện theo tiêu chuẩn/threat model | Khó chứng minh; cần đánh giá cả quasi-identifiers và cross-dataset linkage |
| **Aggregation** | Chỉ xuất thống kê tổng hợp | Small groups/unique combinations vẫn có rủi ro tái định danh |
| **Differential privacy** | Cơ chế thống kê có định nghĩa privacy budget trong thiết kế phù hợp | Không tự xảy ra khi chỉ thêm noise thủ công |

### Từ “anonymized” phải được dùng cẩn thận

Đổi `email` thành SHA-256(email), bỏ tên và giữ địa chỉ/zipcode/dob **không chắc là anonymous**. Hash trơn của email có thể bị dictionary attack; tổ hợp tuổi/khu vực/sự kiện hiếm có thể nhận diện.

**Pseudonymized data vẫn thường cần controls tương đương dữ liệu cá nhân theo policy**, tùy khả năng liên kết/tái định danh và bối cảnh.

## 37. Tại sao đổi email thành hash không đủ?

Giả sử test record:

```json
{
  "emailHash": "sha256-of-email",
  "birthDate": "1990-01-02",
  "postalCode": "rare-postcode",
  "purchaseAt": "2026-11-14T01:23:45Z",
  "purchaseAmount": 123456789
}
```

Rủi ro:

1. Email thường có entropy thấp hơn random token và có thể được đoán từ dictionary.
2. Birth date + postal code + purchase metadata có thể tạo quasi-identifier.
3. Một giao dịch có số tiền/thời gian đặc biệt có thể khớp public facts.
4. Nếu hash ổn định dùng ở nhiều datasets, attacker có thể liên kết người giữa hệ.

### Hướng cải thiện

- Ưu tiên synthetic identifiers.
- Nếu cần stable pseudonyms, dùng HMAC/tokenization với key quản lý phù hợp và scope per dataset/tenant.
- Coarsen dates, amounts và geography nếu không cần mức chi tiết.
- Loại bỏ free-text PII và rare attributes.
- Đánh giá risk of re-identification theo mục đích, audience và side information.
- Dùng privacy review trước khi gọi một dataset “safe for unrestricted dev access”.

## 38. Java 17: pseudonymize identifier bằng HMAC có scope

Ví dụ có mục tiêu giữ quan hệ giữa `customerId` và `order.customerId` trong cùng tenant, nhưng không đưa raw customer ID vào test environment.

```java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.Base64;
import java.util.Objects;
import javax.crypto.Mac;
import javax.crypto.SecretKey;

public final class TestPseudonymizer {
    private final SecretKey key;

    // The key is injected from a controlled secret manager.
    public TestPseudonymizer(SecretKey key) {
        this.key = Objects.requireNonNull(key);
    }

    public String customerToken(String tenantId, String customerId) {
        return token("customer", tenantId, customerId);
    }

    public String orderToken(String tenantId, String orderId) {
        return token("order", tenantId, orderId);
    }

    private String token(
            String domain, String tenantId, String rawId) {
        try {
            if (tenantId == null || tenantId.isBlank()
                    || rawId == null || rawId.isBlank()) {
                throw new IllegalArgumentException("missing ID");
            }

            // Length-prefix avoids ambiguous delimiter concatenation.
            String input =
                segment(domain) + segment(tenantId) + segment(rawId);

            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(key);
            byte[] digest = mac.doFinal(
                input.getBytes(StandardCharsets.UTF_8)
            );
            String encoded = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);

            // ~132 bits of HMAC output for example stable test IDs.
            return "test_" + encoded.substring(0, 22);
        } catch (GeneralSecurityException ex) {
            throw new IllegalStateException("HMAC unavailable", ex);
        }
    }

    private static String segment(String s) {
        Objects.requireNonNull(s);
        return s.length() + ":" + s;
    }
}
```

### Giới hạn của ví dụ

- Mã chỉ **pseudonymize identifier**, không biến cả dataset thành anonymous.
- HMAC key phải đến từ secret manager / một security job, **không** ghi vào repo, test artifact hoặc container image.
- Key không được cấp cho các test developers không cần quyền tái dựng mapping.
- Mọi reference tới cùng customer trong cùng tenant phải dùng **cùng domain+tenant+raw customer ID**, tránh orphan references.
- Token ổn định có thể bị liên kết trong dataset test; nếu cần unlinkability giữa môi trường, dùng key riêng theo destination/generation.
- Thay key làm tokens đổi; cần version/manifest và regeneration plan.
- Việc cắt HMAC 22 ký tự có xác suất collision rất nhỏ trong quy mô phù hợp nhưng không tuyệt đối bằng 0; có thể giữ digest đầy đủ nếu constraint/size cho phép.
- Không dùng cách này để mã hóa một field cần khôi phục giá trị: HMAC là one-way keyed function, **không phải encryption**.
- `segment(s)` dùng UTF-16 string length; nếu có nhiều ngôn ngữ cùng tạo token, cần **một canonical byte-level serialization spec** (length theo UTF-8 bytes) để ra cùng kết quả.

### Vì sao thêm domain?

Không muốn một raw ID `123` ở domain customer vô tình tạo cùng token với order ID `123`. Domain separation cũng giúp không liên kết tokens giữa các mục đích nếu được thiết kế đúng.

## 39. Java: allowlist transform thay vì blacklist field

Một kỹ thuật phổ biến nhưng dễ hỏng:

```text
clone full document
remove "email"
remove "phone"
send all remaining fields to staging
```

Ngày mai developer thêm `customer.deliveryNotes` chứa PII, blacklist không biết để xóa.

**Allowlist** an toàn hơn cho test fixture:

```java
import java.time.Instant;
import java.util.Map;

record SafeOrderFixture(
    String orderId,
    String tenantId,
    String customerId,
    String state,
    long amountMinor,
    String currency,
    Instant createdAt
) {}

public final class OrderFixtureTransformer {
    private final TestPseudonymizer pseudonymizer;

    public OrderFixtureTransformer(
            TestPseudonymizer pseudonymizer) {
        this.pseudonymizer = pseudonymizer;
    }

    public SafeOrderFixture transform(
            String tenantId,
            String orderId,
            String customerId,
            String state,
            long amountMinor,
            String currency,
            Instant originalTime) {
        // Fields are explicitly chosen. No raw notes, email,
        // address, payment token or free-text fields are copied.
        return new SafeOrderFixture(
            pseudonymizer.orderToken(tenantId, orderId),
            "test-tenant",
            pseudonymizer.customerToken(tenantId, customerId),
            sanitizeState(state),
            bucketAmount(amountMinor),
            currency,
            shiftTime(originalTime)
        );
    }

    private static String sanitizeState(String state) {
        return switch (state) {
            case "NEW", "PAID", "CANCELED" -> state;
            default -> "UNKNOWN";
        };
    }

    private static long bucketAmount(long amountMinor) {
        if (amountMinor < 0) return 0;
        return (amountMinor / 10000L) * 10000L;
    }

    private static Instant shiftTime(Instant time) {
        return time.plusSeconds(86400L * 365L);
    }
}
```

### Đừng dùng nguyên code để tuyên bố an toàn privacy

Ví dụ cố ý giới thiệu **data minimization và field allowlist**, nhưng chưa kiểm tra toàn bộ privacy threat model. Việc bucket amount và shift timestamp không chứng minh anonymity. `tenantId` đã gán chung `test-tenant` có thể làm mất isolation tests; nếu cần nhiều tenants, phải tạo **synthetic tenant mapping** riêng và giữ quan hệ nhất quán.

Mọi bản ghi test cần được kiểm tra schema, referential integrity, distribution và chính sách dữ liệu trước khi phát hành.

## 40. Giữ quan hệ và invariant khi tạo dữ liệu test

Một NoSQL model thường có denormalized records:

```text
customers:            C1, C2
orders:               O1(customer=C1), O2(customer=C1)
ordersByCustomer:      C1 -> [O1, O2]
searchProjection:      O1 + customer attributes
paymentOutbox:         Event(OrderPaid, O1)
```

Nếu mỗi collection mask riêng bằng random IDs, integrity bị phá:

```text
orders.customerId = TEST-C999
customers._id      = TEST-C888  <-- orphan
```

### Cách duy trì

1. Xây **mapping đồng nhất** cho cùng logical entity, có domain/tenant scope.
2. Áp dụng cho mọi collections/tables/edge references.
3. Tái tạo denormalized projections thay vì copy raw hidden fields.
4. Đảm bảo unique constraints, partition keys và sorting semantics.
5. Tạo test events với revisions/order/causal dependency hợp lệ.
6. Dùng synthetic timestamps/amounts phù hợp business rules.
7. Kiểm tra số orphan references, duplicate keys và cross-tenant references.

### Nhưng không cần giữ mọi tương quan thật

Một số quan hệ hiếm có thể giúp tái định danh; phải có privacy review về điều gì thực sự cần cho test. Nếu chỉ kiểm tra API CRUD, có thể sinh toàn bộ entities/edges giả thay vì giữ cấu trúc production.

## 41. Test dữ liệu ở quy mô lớn mà không dùng PII thật

Đối với performance benchmark, có thể sinh:

- Số tenants/size theo phân bố minh họa hoặc aggregate được phê duyệt.
- Partition key skew (có tenant lớn, hot keys).
- Document sizes từ vài KiB đến hàng trăm KiB.
- Nested arrays ở các độ dài khác nhau.
- Tombstones/deletes/TTL expiries.
- Các query filters có selectivity khác nhau.
- CDC event bursts, duplicates và out-of-order cases.
- Unicode, text dài, null/missing/empty fields.

### Vì sao cần phân bố?

Nếu 1 triệu synthetic records đều dài đúng 200 bytes, benchmark có thể không phát hiện heap pressure và network bottlenecks khi production có p99 document size 1 MiB. **Giữ phân bố kỹ thuật, không giữ danh tính khách hàng** là mục tiêu tốt hơn.

### K-anonymity và privacy thresholds

Những kỹ thuật nhóm/giảm độ phân giải có thể giúp hạn chế uniqueness, nhưng không đảm bảo privacy tự động. Với dữ liệu giao dịch/đồ thị, cần đánh giá các đường re-identification thực tế; chỉ vì một nhóm có ít nhất k bản ghi không có nghĩa không còn rủi ro mọi trường hợp.

## 42. Free-text, JSON động và vectors: vùng khó sanitize

NoSQL thường chứa trường schema linh hoạt:

```json
{
  "metadata": {
    "notes": "customer supplied arbitrary text",
    "customFields": {
      "idNumber": "SENSITIVE-REDACTED"
    }
  },
  "embedding": [0.01, 0.02, 0.03]
}
```

### Rủi ro

- PII bị chôn trong text tự do.
- Một khách hàng tạo key tùy ý như `medicalNotes` hay `credential`.
- JSON nested rất sâu làm sanitizer bỏ sót.
- Vector embeddings có thể chứa tín hiệu từ nội dung gốc và có rủi ro suy luận/khôi phục thuộc tính nhất định.
- Test logs, prompt debugging hoặc trace capture tự động ghi toàn bộ original payload.

### Chính sách

- Không copy arbitrary free text sang staging nếu không có nhu cầu rõ.
- Thay bằng synthetic text theo độ dài/ký tự/phân bố phù hợp.
- Khóa schema policy theo collection/field và validation.
- Nếu muốn dùng embeddings, ưu tiên vectors tổng hợp hoặc embeddings sinh từ synthetic content.
- Kiểm tra nested unknown fields: **drop by default**, không copy unknown to test.

### PII detection tool không hoàn hảo

Regex/DLP scanner có thể bỏ sót PII hoặc báo giả. Dùng **allowlist, synthetic data và manual privacy review** cho dữ liệu nhạy cảm, không coi một scanner “0 findings” là bằng chứng an toàn tuyệt đối.

## 43. Local developer và CI: không tải production raw dump để debug

Một anti-pattern:

```text
Developer downloads all-orders-prod.archive
  -> restores into local MongoDB
  -> records screenshot of customer address
  -> uploads screenshot into issue tracker
  -> CI uploads database dump as test artifact
```

Hệ thống đã có thêm nhiều bản copy không được inventory, retention hoặc IAM theo chuẩn production.

### Quy trình tốt hơn

1. Đầu tiên tạo **minimal synthetic reproduction**.
2. Nếu chưa tái hiện, yêu cầu scoped export có approval.
3. Thực hiện sanitize trong **controlled environment**, không trên laptop.
4. Chỉ phát hành sanitized fixture qua artifact store được cấp quyền.
5. Dùng ephemeral test environment với ingress/egress policy.
6. Cấm gửi email, SMS, payment hoặc webhook thật từ staging.
7. Auto-expire test resources, artifacts và secrets.
8. Log việc dataset được sinh/dùng/xóa; nếu phát hiện PII, quarantine và xử lý incident.

### CI artifacts cũng là data store

Build logs, unit-test failure dumps, coverage files, screenshots, trace artifacts và crash reports có thể giữ raw documents. Retention/permissions trên CI cần được đưa vào **data lifecycle**.

## 44. Staging isolation: dữ liệu kiểm thử không được vô tình chạm người thật

```text
Staging app
   |
   +-- test MongoDB (sanitized only)
   +-- fake SMTP sink
   +-- mocked payment provider
   +-- test webhook listener
   +-- outbound allowlist / egress controls
```

### Một số nguyên tắc

- Tách DB account, credentials, networks và buckets giữa staging/prod.
- Không để staging đọc production snapshot repository.
- Kết nối dịch vụ bên ngoài qua sandbox credentials thật sự, không chỉ đổi tên environment variable.
- Tắt/giả lập email/SMS trước khi nạp dataset.
- Tenant IDs/users trong staging phải synthetic hoặc remapped.
- Không cho release pipeline có quyền tự restore production data vào môi trường tùy ý.
- Lưu test data dưới TTL/lifecycle; xóa khi ticket/release kết thúc.

### “Staging cũng có SSO” chưa đủ

Nếu tất cả developers đều có role admin và có quyền export entire test DB, raw production clone vẫn là vấn đề. **Điều quan trọng là data thật đã được giảm độ nhạy đúng cách trước khi vào môi trường có phạm vi truy cập rộng.**

## 45. Query logs và database profiling có thể chứa input thật

Không ít hệ bật slow query logs để tối ưu NoSQL:

```text
timestamp=...
database=orders
query={ "email": "customer@example.invalid" }
duration_ms=234
```

Ngay cả khi kết quả document không nằm trong log, **query parameters** có thể chứa PII hoặc token, và trace attributes có thể ghi raw filter, payload hoặc URL query string.

### Quy tắc ghi log

- Log **query template/operation class** thay vì raw values khi không cần.
- Với dynamic JSON filters, sanitize allowlist fields.
- Không log DB connection strings có username/password.
- Không log raw JWT, session tokens, KMS keys hoặc pre-signed URLs.
- Dùng redacted trace attributes và giới hạn sampling.
- Set log retention và access control theo classification.
- Bảo vệ log archive/object storage/replication tương tự data store.
- Có privacy review khi bật verbose/debug logging trên production.

### Không hiểu sai “logs không là database”

Central log search có thể có hàng nghìn người được phép query. Một raw query chứa email hoặc shipping address xuất hiện ở log dễ bị đọc rộng hơn so với collection gốc. **Tác động bảo mật đến từ dữ liệu trong log, không phải loại hệ thống lưu trữ.**

## 46. Heap dumps, core dumps và tracing attachments

Một Java worker đọc 100.000 customer records; khi OOM:

```text
Heap dump:
  byte arrays with JSON
  MongoDB Documents
  JDBC/NoSQL credentials in objects
  TLS session state or tokens
  request payloads
```

Heap/core dumps có thể chứa fragments của sensitive data dù dữ liệu gốc đã được mã hóa trên disk.

### Kiểm soát

1. Chỉ bật heap dumps khi có nhu cầu và trong vùng lưu trữ được bảo vệ.
2. Giới hạn ai tải/analyze dumps.
3. Encrypt artifacts, retention ngắn theo incident, audit downloads.
4. Không đính kèm dump vào issue tracker rộng quyền.
5. Nếu dùng third-party diagnostics, đánh giá hợp đồng xử lý dữ liệu và phạm vi chia sẻ.
6. Quarantine/delete theo lifecycle sau khi đã hoàn thành điều tra.

### Encryption at rest của database không bảo vệ heap

DB driver đã giải mã record để ứng dụng xử lý, nên PII có thể nằm trong memory. Bảo vệ diagnostics phải được xem là **một luồng dữ liệu riêng**.

## 47. Observability metrics: tránh PII trong labels

Anti-pattern:

```text
nosql_query_count{
  tenantId="T01",
  email="customer@example.invalid",
  orderId="O12345",
  fullQuery="{...}"
} 1
```

Ngoài rủi ro lộ PII, cardinality có thể tăng cực nhanh khiến hệ metrics/alerting quá tải.

### Thiết kế

Thường nên giữ các chiều:

```text
service, environment, operation, database_role,
error_category, query_template, region
```

Các nhãn như raw tenant ID hoặc request ID chỉ nên dùng nếu có nhu cầu hợp lệ và đã đánh giá cardinality/privacy; nhiều trường hợp phù hợp hơn với **tracing/log có quyền** hoặc aggregate per tenant tier.

### Một trace mẫu

Thay vì:

```text
db.query = find users where email="person@example.invalid"
```

dùng:

```text
db.operation = find
db.collection = users
db.query_template = find-by-email
db.duration_ms = 123
trace.id = non-secret-trace-identifier
```

Một trace ID cũng cần được bảo vệ trước việc người khác dùng nó để truy cập dữ liệu nếu tracing backend không có authorization phù hợp.

## 48. Export approval: định nghĩa workflow và bằng chứng

Một yêu cầu “xuất 100.000 customers để debug” nên được chuyển thành:

```text
REQ-123:
  requester        : verified employee/workload
  purpose          : reproduce pagination bug
  exact fields     : tenantToken, orderIdToken, status, createdAt
  target scope     : selected synthetic/sanitized tenant
  data owner       : orders-team
  security review  : required if restricted source
  destination      : approved encrypted staging data store
  access duration  : bounded
  retention        : bounded
  audit id         : REQ-123
```

### Quy trình

1. Xác nhận **mục đích và dữ liệu tối thiểu**.
2. Ưu tiên synthetic reproduction; chỉ dùng production subset khi cần.
3. Duyệt quyền theo data owner/security policy.
4. Tạo short-lived export job identity.
5. Extract/filter/transform trong controlled environment.
6. Encrypt và chuyển tới đích được phê duyệt.
7. Verify manifest, counts, scope, sensitive fields policies.
8. Cấp quyền đọc có thời hạn cho đúng người.
9. Lưu audit và chủ sở hữu bản sao.
10. Xóa/expire theo retention, ghi nhận exceptions.

### Không tạo “quy trình bí mật” thủ công

Một người admin chạy export bằng credential cá nhân rồi gửi link chat khó audit và khó revoke. Nên đóng gói bằng workflow có log, approvals, ownership và least privilege.

## 49. Export job dưới dạng trạng thái có thể kiểm soát

Một export service có thể có:

```text
REQUESTED
    |
    v
AUTHORIZED
    |
    v
EXTRACTING
    |
    v
TRANSFORMING / REDACTING
    |
    v
ENCRYPTING + UPLOADING
    |
    v
VALIDATING
    |
    v
AVAILABLE_UNTIL_EXPIRY
    |
    v
EXPIRED / DISPOSED
```

Nếu bị lỗi:

```text
FAILED
  -> clean up temporary artifacts
  -> revoke grants/tokens
  -> record cause without raw PII
  -> alert owner if sensitive partial object might exist
```

### Idempotency và checkpoint

Export hàng triệu records có thể chạy theo batches, có cursor/checkpoint. Nếu job crash sau upload part nhưng trước checkpoint, retry có thể tạo duplicate files. Dùng **deterministic part IDs, manifest và conditional output write** để có khả năng resume an toàn.

### Bảo mật checkpoint

Checkpoint có thể chứa source token, source IDs hoặc tenant scope; không publish nguyên checkpoint lên client/ticket nếu có thông tin nhạy cảm. Dùng opaque job IDs và authorization khi truy cập progress.

### Không cho fail-open khi sanitizer lỗi

Nếu transform gặp field không hỗ trợ/schema version mới, **dừng/quarantine** thay vì chuyển raw document sang destination “để không mất dữ liệu”. Dữ liệu an toàn quan trọng hơn tỉ lệ job success.

## 50. Restore runbook: luôn giả định dữ liệu đã hồi sinh là nhạy cảm

### Trước restore

1. Xác định incident/recovery purpose, target RPO/RTO.
2. Chọn backup ID/source log point có inventory và manifest hợp lệ.
3. Phê duyệt đích: environment, account, network, tenant scope.
4. Xác minh backup/object integrity và KMS key grants.
5. Đảm bảo restore principal có time-limited permissions.
6. Cấu hình **isolate outbound integrations** trước khi dữ liệu xuất hiện.
7. Xác minh target disks/buckets encrypted, audit enabled.
8. Chuẩn bị deletion/reconciliation events sau snapshot point.

### Trong restore

```text
Verify archive
    |
    v
Decrypt in approved environment
    |
    v
Restore to isolated target
    |
    v
Validate data and schema
    |
    v
Reconcile source positions/deletions/permissions
    |
    v
Only then authorize dependent applications/traffic
```

Không restore trực tiếp vào production bằng một lệnh copy khi chưa xác định nguy cơ ghi đè và failure recovery policy.

### Sau restore

- Test read/write paths và required indexes.
- Kiểm tra tenant isolation và least privilege.
- Xác minh pipeline CDC/change-log replay boundary.
- Áp các yêu cầu xóa/revocation mới hơn snapshot nếu chính sách đòi hỏi.
- Đảm bảo test credentials/notification integrations không phát tán dữ liệu.
- Thu hồi temporary access, xóa temp plaintext, ghi restore evidence.

## 51. Kiểm tra restore không nên dùng record khách hàng thật để “chụp làm bằng chứng”

Một đội QA có thể chứng minh restore bằng:

```text
Backup manifest verified.
Table/collection schema present.
Record counts within expected bounds.
Checksums or sampled keyed hashes validated.
Synthetic canary records survive restore.
Critical queries pass.
Data isolation policy verified.
```

Không cần in ra tên/địa chỉ của một khách hàng cụ thể trên screenshot gửi rộng.

### Synthetic canary

Đặt một record test có identity phi nhạy cảm trong production theo policy (nếu sản phẩm cho phép) để kiểm tra continuity/restore. Canary phải không tác động nghiệp vụ thực và không vi phạm uniqueness/payment.

### Kiểm tra số lượng không đủ

Hai bản backup có cùng count nhưng dữ liệu sai hoặc missing field. Cần schema/integrity checks, source revision validation hoặc domain invariants phù hợp.

### Test restore có RPO/RTO

Đo số thời gian từ bắt đầu disaster drill đến lúc hệ có read/write path an toàn, và độ mới dữ liệu đã được restore; một bản backup tồn tại nhưng cần 48 giờ để restore có thể không đáp ứng RTO yêu cầu.

## 52. Audit: ai đã đọc, xuất và phục hồi dữ liệu?

Một log audit cho export operation có thể ghi:

```json
{
  "eventType": "DATA_EXPORT_APPROVED",
  "requestId": "REQ-123",
  "actorId": "employee-or-workload-id",
  "sourceId": "orders-production",
  "dataClassification": "CONFIDENTIAL",
  "approvedScope": "tenant-scoped",
  "destinationId": "approved-staging-artifact",
  "createdAt": "2026-11-14T10:00:00Z",
  "retentionPolicyId": "short-lived-debug-export"
}
```

**Không đưa raw records hoặc secrets vào audit log** nếu không có nhu cầu được phê duyệt. Audit chính là một data store cần giữ an toàn và có retention đúng.

### Audit events quan trọng

- Snapshot created/shared/copied/deleted.
- Export requested/approved/denied/completed.
- Object read/download spikes.
- KMS decrypt grant/usage/key disabled/deletion scheduled.
- Backup retention policy hoặc object lock thay đổi.
- Restore operation started/completed/failed.
- CDC consumer group/topic ACL mới.
- DLQ raw-event accesses.
- Test dataset published/expired.
- Public access policy drift.

### Audit không tự chứng minh an toàn

Nếu logs có thể bị xóa bởi cùng principal đã exfiltrate dữ liệu, attacker có thể xóa dấu vết. Bảo vệ audit sink bằng controls độc lập, write-only ingestion hoặc immutability phù hợp.

## 53. Detection: cảnh báo cho việc sử dụng dữ liệu bất thường

Một số cảnh báo có thể hành động:

| Cảnh báo | Tín hiệu | Triage |
|---|---|---|
| `UnexpectedProductionDump` | Lệnh export ngoài approved job/ticket | Principal, source, destination, purpose |
| `BackupObjectPublicExposure` | Object/bucket/snapshot public hoặc cross-account share bất thường | Isolate access, incident security |
| `MassBackupDownload` | Tải lượng bytes bất thường từ archive | Identity, region, preceding permissions |
| `KmsDecryptSpike` | Key decrypt tăng từ principal không thường dùng | Grant changes, access path |
| `MissingBackupEncryption` | New object không đáp ứng encryption policy | Quarantine, prevent distribution |
| `BackupRetentionAtRisk` | Backup/logs có nguy cơ mất trước RPO/RTO | Storage headroom, workflow |
| `RestoreToUnapprovedEnvironment` | Restore ngoài allowlist | Stop/quarantine target, audit |
| `RawPiiDetectedInTestArtifact` | Scanner phát hiện dữ liệu không được phép trong CI/staging | Quarantine artifact, revoke access |
| `CdcUnauthorizedSubscription` | New identity đọc restricted topic | Revoke ACL, investigate scope |
| `DataDispositionOverdue` | Artifact quá hạn chưa xóa | Owner, copies, exceptions |

### Không alert từng raw record

Alert từ scanner/telemetry nên ghi **artifact ID, owner, severity và link runbook**, không kèm raw email/card/address. Với security incidents, mở restricted investigation record theo policy.

### Detection có false positives

KMS usage tăng có thể do restore drill được phê duyệt; nên correlation với change ticket/approved workflow, nhưng đừng whitelist toàn bộ hoạt động chỉ vì principal “thường là backup service”.

## 54. Incident response: phát hiện một dump bị lộ

Giả sử object storage audit cho thấy một archive production bị công bố ngoài policy.

### Triage nhanh

1. Xác định object/snapshot ID, source, classification, time window.
2. Bảo toàn **metadata/audit evidence** theo incident policy.
3. Ngăn truy cập tiếp: revoke public policy/grants/signed URLs nếu nền tảng hỗ trợ, cô lập credentials.
4. Xác định những principals/IPs/downloads có thể đã truy cập.
5. Xác định phạm vi data: tenants, collections, PII/credentials, before images.
6. Kiểm tra bản sao phát sinh: mirrors, CI artifacts, shared tickets.
7. Rotate/revoke secrets/tokens nếu có khả năng lộ; không chỉ xóa archive.
8. Kích hoạt team security/privacy/legal theo nghĩa vụ thông báo và incident policy.
9. Rà soát root cause: IAM/bucket policy/approval/CI/system access.
10. Thêm preventive controls và verify không còn exposure.

### Không hứa rằng đổi URL là lấy dữ liệu về

Nếu một người đã tải file, vô hiệu URL không xóa bản họ giữ. Phải điều tra truy cập, mức độ dữ liệu và quy trình xử lý phù hợp.

### Nếu dump chứa database credentials

Giả định credentials có thể bị compromise theo threat model, rotate theo quy trình và đánh giá downstream misuse. Một backup được mã hóa ở storage nhưng dump plaintext được ai đó tải qua authorized path vẫn có thể gây leak.

## 55. Incident response: test environment vô tình chứa production PII

Một scanner tìm thấy email thật trong CI artifact.

### Các bước

1. Ngừng public/share download của artifact và cô lập pipeline/runner nếu cần.
2. Xác định dataset source, sanitizer version và data lineage.
3. Kiểm tra logs, screenshots, caches, object versions, mirrors và các downloads đã xảy ra.
4. Tìm lỗi allowlist/field mapping, nested JSON hoặc free text.
5. Thu hồi grants và xóa copies theo policy.
6. Rotate secrets nếu artifacts chứa credentials/tokens.
7. Tạo lại synthetic fixture hoặc chạy sanitizer đã được kiểm soát.
8. Thêm regression tests để raw field không quay lại.
9. Báo cáo/sự cố privacy theo quy trình và kiểm tra risk.

### Đừng dùng dữ liệu thật để chứng minh dữ liệu thật bị lộ

Báo cáo kỹ thuật dùng **redacted samples, field names, counts, hashes có quyền**. Không gửi nguyên danh sách emails vào ticket rộng quyền.

## 56. Fault injection và security exercises

Chạy trong staging/lab với dataset giả:

| Thí nghiệm | Kỳ vọng |
|---|---|
| Bucket vô tình được gắn public-read | Policy scanner phát hiện, permission bị từ chối |
| Restore role có object read nhưng không có KMS decrypt | Fail có thông báo rõ, không cố giảm encryption |
| Key cũ bị disable trong restore drill | Runbook nhận diện dependency, escalation, không phá dữ liệu |
| Export job crash khi file plaintext đang tồn tại | Cleanup/quarantine, không publish |
| Tenant T01 export có record T02 | Output validation fail-closed |
| Sanitizer gặp field nested lạ | Drop/quarantine, không forward raw |
| Java CI crash với heap dump | Dump không upload công khai; retention/access |
| CDC before-image chứa token giả | Topic ACL/redaction/encryption/retention kiểm soát |
| DLQ chứa raw payload giả | Chỉ đội được cấp quyền đọc, lifecycle |
| Restore snapshot trước sự kiện delete | Reconcile deletion records, không mở API sớm |
| Object versioning giữ archive đã “xóa” | Lifecycle kiểm tra versions/replicas |
| Signed URL bị chia sẻ sang tester khác | Scope/expiry và revoke/incident workflow |
| Test staging có outbound email thật | Egress/sandbox chặn gửi |
| Storage backup account bị credential compromise | Immutability/separate key policy giảm blast radius |
| Monitoring exporter mất visibility | Không báo database “healthy” giả |

### Kết quả test nên ghi

- Scenario, expected control, observed result.
- Identity/permission scope.
- Artifact ID và data classification (không raw PII).
- Restore/exfiltration boundary.
- Incident/runbook owner.
- Remediation và ngày kiểm tra lại.

Một security test thành công không chỉ có exit code: nó phải chứng minh **quyền sai bị chặn, dữ liệu không rò, lỗi được audit và môi trường còn phục hồi được**.

## 57. Bài tập thực hành: nhận diện và thiết kế kiểm soát

### Bài 1 — Sơ đồ bản sao của NoSQL

Một ứng dụng có MongoDB, Redis cache, Kafka CDC, Elasticsearch và CI pipeline. Vẽ **data lineage** từ document `Customer` tới snapshot, cache, event log, search projection, test artifacts. Đánh dấu nơi có thể tồn tại PII sau khi primary document bị xóa.

### Bài 2 — Phân loại một bản dump

Đội phát triển tạo file `customers.bson.gz`. Một người nói “đã nén nên không thể đọc dễ dàng”. Hãy giải thích vì sao dữ liệu vẫn là confidential và đề xuất encryption/IAM/retention.

### Bài 3 — Tenant scope

Một bảng NoSQL chung chứa tenant T01/T02. Khách hàng T01 yêu cầu export dữ liệu của họ; nhóm vận hành đề xuất chia sẻ volume snapshot. Vì sao snapshot có thể chứa T02? Thiết kế quy trình logical export an toàn hơn.

### Bài 4 — Mô hình quyền

Một backup role có quyền đọc all collections, tạo snapshot, tải archive, xóa backups và `kms:Decrypt` trên mọi key. Hãy tách quyền của backup creator, restore operator, auditor và break-glass admin.

### Bài 5 — Signed URL

Một pre-signed URL đọc production dump có TTL 30 ngày và được dán trong public issue. Nêu những biện pháp containment và giải thích vì sao URL hết hạn không thu hồi bản sao đã tải.

### Bài 6 — Envelope encryption

Mô tả quan hệ giữa DEK, KEK, encrypted DEK, ciphertext và AEAD tag. Ai cần quyền unwrap DEK khi restore? Tại sao storage read permission không nhất thiết là decrypt permission?

### Bài 7 — KMS rotation

Một công ty đổi KMS key nhưng quên test restore backups 2 năm tuổi. Phân tích các trường hợp backup cũ vẫn đọc được và trường hợp bị mất khả năng khôi phục. Không giả định rotation đã tự re-encrypt mọi artifact.

### Bài 8 — Mất key

Backup immutable 1 năm vẫn còn đủ, nhưng khóa giải mã cũ đã bị xóa. Backup có đáp ứng recoverability không? Đề xuất key lifecycle checks và disaster drill.

### Bài 9 — Restore từ snapshot cũ

Một khách hàng đã xóa profile ở T2. Disaster restore source về snapshot T1 (trước khi xóa), rồi mở API. Profile xuất hiện lại. Làm gì để không vô tình hồi sinh dữ liệu khi phục hồi?

### Bài 10 — Integrity manifest

Một attacker có quyền ghi archive và manifest nhưng không có signing key. Tại sao checksum SHA-256 lưu cùng manifest chưa đủ để chống giả mạo? Đề xuất authenticated encryption, signature hoặc trusted manifest storage.

### Bài 11 — MongoDB dump

Đội test muốn chạy `mongodump` từ production vào laptop. Chuyển yêu cầu thành workflow approval, subset, sanitization, encryption và short retention. Khi nào nên từ chối raw export?

### Bài 12 — Redis RDB/AOF

Ứng dụng đặt session tokens trong Redis. Một RDB snapshot được upload lên shared bucket. Tại sao key hết TTL trong live Redis không đồng nghĩa snapshot lịch sử đã an toàn?

### Bài 13 — Cassandra snapshot

Một node Cassandra chứa SSTables có tombstones và data từ nhiều tenants. Đội vận hành copy SSTables qua USB để test recovery. Liệt kê nguy cơ bảo mật và giới hạn consistency/recovery của một node copy.

### Bài 14 — DynamoDB export

DynamoDB table có encrypted data và export sang S3. IAM table rất chặt, nhưng S3 bucket cho mọi engineer đọc và KMS key mở rộng. Trust boundary nào đã thay đổi? Chọn controls phù hợp.

### Bài 15 — Elasticsearch snapshot

Search API ẩn `customerEmail` khỏi response, nhưng index `_source` vẫn có field này và snapshots được share với staging. Có thể xem staging dataset không nhạy cảm không? Cần sửa ở index/snapshot/restore nào?

### Bài 16 — Graph anonymity

Graph dataset xóa node names nhưng giữ quan hệ bạn bè/điểm đến hiếm. Giải thích cách topology có thể tái định danh; đề xuất synthetic graph hoặc giảm chi tiết.

### Bài 17 — CDC before-image

Customer document xóa field `secretToken` lúc T3. Raw CDC topic lưu before-image. Nếu topic retention là 30 ngày, rủi ro gì vẫn còn? Có nên broadcast raw topic cho mọi service không?

### Bài 18 — Outbox tối thiểu

Một email notification consumer cần biết `OrderPaid` để gửi message, nhưng không cần thông tin thẻ thanh toán. Thiết kế event schema tối thiểu, ACL của topic và nguồn thông tin được ủy quyền.

### Bài 19 — Dead-letter queue

Main Kafka topic giữ events 7 ngày, DLQ giữ raw records 180 ngày và có user access rộng. Hãy mô tả violation có thể có và cách thay bằng encrypted/redacted references, retention và audit.

### Bài 20 — HMAC test IDs

Một dataset staging dùng `SHA256(email)` để thay email. Nêu nguy cơ dictionary attack. Viết chính sách HMAC/tokenization có domain+tenant scope, key management và rotation.

### Bài 21 — Referential integrity

Ba collections `customers`, `orders`, `ordersByCustomer` có duplicate embedded customer data. Đề xuất transformation giữ quan hệ customer ID nhất quán mà không copy raw PII.

### Bài 22 — PII trong free-text

Sanitizer bỏ email/phone top-level nhưng giữ `deliveryNotes`. Một customer đã nhập số thẻ/địa chỉ trong notes. Tại sao denylist không đủ? Viết allowlist schema cho safe fixture.

### Bài 23 — Dữ liệu synthetic cho performance

NoSQL production có hotspot tenant, document sizes p99 lớn và nhiều tombstones. Thiết kế synthetic workload tái tạo các tính chất kỹ thuật nhưng không sao chép raw records/timestamps/PII hiếm.

### Bài 24 — CI artifact incident

Một test exception in toàn bộ JSON chứa email vào stdout, hệ CI giữ logs 90 ngày. Hãy vẽ các bản sao và đề xuất sanitation, artifact permissions, quarantine và xóa theo policy.

### Bài 25 — Heap dump

Java service OOM và tạo `heap.hprof` khi driver đang giữ dữ liệu khách hàng. Vì sao file này có thể nhạy cảm hơn logs thông thường? Đề xuất access/retention/diagnostic process.

### Bài 26 — Export crash

Một export job đã ghi 5 parts vào storage nhưng crash trước khi cập nhật checkpoint. Nếu retry tạo thêm 5 parts cùng dữ liệu, rủi ro integrity là gì? Đề xuất deterministic part names và manifest commit.

### Bài 27 — Object storage versions

Admin xóa `dump-2026-11-14.enc` nhưng bucket có versioning và replication. Những bản sao nào có thể còn? Làm sao xác minh lifecycle theo policy?

### Bài 28 — Audit và anomaly

Một production backup principal bắt đầu tải 300 GiB vào địa chỉ mạng lạ ngoài khung giờ backup. Đề xuất signals, incident route, containment và logs cần bảo toàn.

### Bài 29 — Encryption không thay authorization

Một archive S3 được mã hóa bằng CMK nhưng mọi developer có object read và KMS decrypt. Giải thích vì sao “encrypted” không đồng nghĩa chỉ người được phép theo business mới thấy nội dung.

### Bài 30 — Thiết kế tổng hợp

Thiết kế hệ:

```text
MongoDB production
  ├── encrypted daily snapshots + PITR
  ├── CDC into Kafka
  ├── search projection
  └── approved sanitized export to ephemeral staging
```

Xác định IAM/KMS/ACL, retention theo từng artifact, source log positions, restore consistency, delete replay, synthetic fixture policy, audit, incident alerting và kiểm thử failover. Giải thích vì sao không để staging đọc trực tiếp production raw data.

## 58. Bảng quyết định: có thực sự cần dùng dữ liệu production?

| Nhu cầu | Phương án ưu tiên | Khi nào cân nhắc dữ liệu thật? |
|---|---|---|
Unit test CRUD/validation | Synthetic fixtures | Hầu như không cần |
| Integration test schema/relationships | Synthetic graph/document model | Khi bug phụ thuộc pattern quá đặc thù và đã được phê duyệt |
| Load/performance benchmark | Synthetic data theo distributions kỹ thuật | Chỉ dùng approved aggregate statistics hoặc scoped transformation nếu cần |
| Debug lỗi một document | Minimal redacted reproduction | Khi không thể tái hiện và có approval/data minimization |
| Disaster recovery test | Restore isolated backup có kiểm soát | Có thể cần backup thật trong môi trường bảo vệ tương đương |
| Data migration rehearsal | Sanitized/synthetic large dataset | Cần privacy review khi exact semantics phụ thuộc raw data |
| Incident investigation | Restricted query/probe và redacted evidence | Raw artifacts chỉ cho principal có quyền, audit |
| Support partner export | Minimal customer-approved dataset | Theo agreement/approval, không dùng shared whole-db dump |

### Quy tắc lựa chọn

1. Tạo synthetic trước.
2. Nếu không đủ, thu hẹp trường/scope và biến đổi trong controlled job.
3. Nếu vẫn cần dữ liệu thật, áp quyền/approval/security boundary tương đương sensitivity.
4. Mục đích kết thúc → expire/delete hoặc giữ theo documented exception.

## 59. Checklist bảo vệ snapshot, dump và backup

1. Đã phân loại data source và bản sao **theo nội dung** chưa?
2. Có inventory chứa owner, purpose, source, destination, region, key reference và retention không?
3. Có thể truy ra mọi copies, replicas, versions và temporary files không?
4. Ai được tạo, đọc, giải mã, restore, share và delete backups?
5. Backup creator có tách khỏi restore/key admin khi cần không?
6. Backup/export role có quyền tối thiểu theo DB/table/collection/tenant scope không?
7. Destination object storage có private-by-default, TLS và access logging không?
8. Có chặn policy public access/snapshot cross-account share ngoài allowlist không?
9. Dữ liệu có encryption at rest, in transit; cần client-side encryption không?
10. KMS keys/grants có scope đúng environment và recovery role không?
11. Backups cũ còn giải mã được sau key rotation không?
12. Có test trường hợp KMS key disabled/missing không?
13. Backup file/manifest có integrity validation và trusted metadata không?
14. Snapshot có consistency boundary đúng để restore không?
15. Có khả năng PITR khi cần, giữ source logs đủ lâu không?
16. Có regular restore drills với RPO/RTO và domain invariants không?
17. Immutable retention có phù hợp deletion/legal hold policy không?
18. Có cơ chế chống xóa backups bởi cùng principal production không?
19. Có plan phục hồi khi production account/KMS bị compromise không?
20. Có xóa temporary plaintext và quản lý copies trên endpoint/CI không?

## 60. Checklist bảo vệ CDC, event logs và dữ liệu dẫn xuất

1. CDC schema thực tế có before/after images hay full documents không?
2. Source connector có chỉ đọc collections/events cần thiết không?
3. Broker producer/consumer ACL có phân scope topic/group/environment không?
4. Raw event payload có vượt nhu cầu của consumers không?
5. Có tách raw restricted topics khỏi sanitized business events không?
6. Event keys/headers/schema history có lộ email, IDs hoặc secret không?
7. DLQ/retry topic có giữ raw payload lâu hơn main topic không?
8. Topic/segment/snapshot/tiered storage/mirror retention có trong inventory không?
9. Khi delete data, các event logs/tombstones/projections/backup copies được xử lý thế nào?
10. Có logging/tracing vô tình ghi raw event hoặc exception payload không?
11. Có audit subscriber mới, ACL changes và unusual topic reads không?
12. Consumer redrive/replay có authorization và idempotency không?
13. CDC recovery từ snapshot/log có thể hồi sinh dữ liệu đã xóa không?
14. Những source offsets/resume tokens có được bảo vệ như metadata nhạy cảm khi cần không?
15. Có runbook khi retention gap làm không thể resume không?

## 61. Checklist bảo vệ dữ liệu kiểm thử và diagnostics

1. Unit/integration/performance tests có thể dùng synthetic data không?
2. Dataset generator có bảo tồn business invariants mà không giữ raw PII không?
3. Nếu dùng source thật, có approval và xử lý trong controlled environment không?
4. Masking có theo **allowlist**, không chỉ blacklist vài top-level fields không?
5. Nested JSON/free-text/attachments/vectors/graph edges có được xét không?
6. Pseudonymization key và mapping có được bảo vệ, versioned, rotated không?
7. Tokenization có giữ consistent referential IDs trong đúng tenant scope không?
8. Dataset test có còn khả năng tái định danh nhờ timestamps, rare paths, geography không?
9. Test fixtures có classification và scope truy cập sau transformation không?
10. Staging có DB/network/IAM/KMS tách production không?
11. Staging outbound email/SMS/payment/webhook đã được sandbox/chặn chưa?
12. CI có thể upload logs/screenshots/heap dumps chứa raw data không?
13. Có retention, ownership và auto-expiration cho test datasets/artifacts không?
14. Có scanner/validation và fail-closed khi sanitizer gặp unknown fields không?
15. Có runbook phát hiện và xử lý PII trong test artifact không?
16. Có audit việc ai lấy dataset, ai restore và xuất đi đâu không?

## 62. Những hiểu lầm cần tránh

| Hiểu lầm | Thực tế |
|---|---|
| “Dump dạng BSON/binary khó đọc nên an toàn” | Có thể restore/parse; vẫn chứa nội dung thật |
| “gzip là mã hóa” | Nén không bảo vệ confidentiality |
| “Backup encrypted nên ai cũng tải được” | Người có decrypt grant vẫn đọc được; IAM vẫn cần |
| “Database đã có RBAC thì backup tự kế thừa” | Snapshot/export có IAM và trust boundary khác |
| “Snapshot một node là snapshot toàn cluster nhất quán” | Phụ thuộc engine/topology/consistency strategy |
| “Backup job success là restore được” | Cần integrity verification và restore drills |
| “Key rotation làm mọi backup cũ an toàn tuyệt đối” | Phải hiểu key versions/re-wrap và grants |
| “Xóa file backup là xóa mọi bản sao” | Versions/replicas/PITR/logs có thể còn |
| “Xóa live record đồng nghĩa log history đã xóa” | CDC/before images/snapshots vẫn có thể chứa |
| “Test environment không quan trọng vì không là production” | Nếu có dữ liệu thật thì vẫn có nguy cơ tương đương |
| “Hash email là anonymization” | Hash trơn dễ suy đoán; linkability/re-identification |
| “HMAC/tokenization làm dữ liệu hoàn toàn anonymous” | Mapping/key và các quasi-identifiers vẫn có thể liên kết |
| “Mask names là đủ cho graph” | Cấu trúc quan hệ có thể tái định danh |
| “Đã strip email nên free text an toàn” | Notes/custom JSON chứa PII khó phát hiện |
| “Search API ẩn field thì snapshot không chứa field” | Index snapshot có thể chứa `_source`/stored data |
| “DLQ chỉ dùng cho lỗi nên không nhạy cảm” | DLQ có thể giữ raw event lâu hơn topic chính |
| “Signed URL hết hạn là dữ liệu đã thu hồi” | Files đã tải tiếp tục tồn tại |
| “Encryption thay authorization” | Không ngăn privileged misuse |
| “Bật verbose logging cho dễ debug không sao” | Query/trace/heap logs có thể chứa PII và tokens |
| “Xóa key mã hóa là cách xóa một tenant an toàn” | Shared keys có thể làm mất dữ liệu của tenants khác |
| “Không còn PII scanner findings là chắc chắn anonymous” | DLP scanners có false negatives và linkability |
| “Audit log không thể bị sửa vì có log service” | Cần tách quyền, retention/immutability và kiểm soát admin |

## 63. Kết luận

Trong hệ NoSQL, dữ liệu nhạy cảm **không dừng lại ở collection đang phục vụ API**. Nó đi vào snapshots, dump archives, physical files, CDC/change logs, retry queues, search indexes, caches, local diagnostics, CI artifacts và những môi trường test. Mỗi lần dữ liệu được copy hoặc thay đổi định dạng là một **trust boundary** cần đánh giá lại.

Các nguyên tắc cốt lõi:

1. **Phân loại theo nội dung, không theo đích lưu.** File `orders-test.json` vẫn nhạy cảm nếu chứa dữ liệu khách hàng thật.
2. **Không cho phép export vô hạn chỉ vì có DB read quyền.** Dùng least privilege, scoped jobs, approvals, audit và short-lived access.
3. **Mã hóa cả lưu trữ và truyền tải**, đồng thời quản trị KMS grants, key rotation và khả năng restore backups cũ.
4. **Integrity, consistency và recoverability khác confidentiality.** Backup mã hóa vẫn có thể bị lỗi, không nhất quán hoặc không đọc được khi mất key.
5. **Object storage, signed URLs và snapshots là tài nguyên có chính sách riêng.** Không giả định chúng kế thừa ranh giới database gốc.
6. **CDC/before images/DLQ giữ lịch sử dữ liệu.** Xóa live document không làm mọi copies biến mất; cần retention và deletion reconciliation.
7. **Ưu tiên synthetic test data.** Nếu buộc dùng dữ liệu thật, xử lý bằng allowlist transformation, privacy review, pseudonymization có scope và ephemeral destinations.
8. **Không đưa raw data vào logs, traces, heap dumps và CI artifacts.** Đây là những bản sao thường có số người xem rộng hơn production database.
9. **Restore phải diễn tập và có data security guardrails.** Restore vào cô lập, validate integrity/tenant scope, ngăn integrations thật và xử lý dữ liệu đã xóa sau snapshot.
10. **Theo dõi cả sự kiện truy cập dữ liệu**, không chỉ backup success: exports bất thường, public shares, KMS decrypt spikes, DLQ access, datasets quá hạn.

Trước khi tạo một bản sao mới, hãy hỏi:

> **“Bản sao này chứa gì, ai thật sự có thể đọc và giải mã, nó nằm ở đâu, được giữ đến khi nào, có thể restore an toàn không, và nếu người dùng yêu cầu xóa hoặc credential bị lộ thì chúng ta kiểm soát được những bản copy nào?”**

Nếu trả lời được bằng **data inventory, policies, audit và restore/security tests**, hệ NoSQL mới bảo vệ dữ liệu xuyên suốt vòng đời — không chỉ lúc dữ liệu còn ở production database.

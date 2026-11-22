# Mã hóa, lưu giữ, lưu ngoài máy chủ và phân quyền bản sao

Một bản sao lưu PostgreSQL chỉ có giá trị khi có thể khôi phục đúng dữ liệu, trong thời gian cần thiết và khi người có trách nhiệm vẫn truy cập được bản sao. Trong môi trường production, backup thường chứa dữ liệu nhạy cảm tương đương hoặc còn tập trung hơn database đang chạy. Vì vậy, bảo vệ backup cần giải quyết đồng thời bốn vấn đề: **mã hóa**, **lưu giữ**, **lưu ngoài máy chủ** và **phân quyền truy cập**.

Mã hóa bảo vệ nội dung khi file hoặc object bị đọc trái phép; retention xác định cần giữ những bản nào và trong bao lâu; offsite storage giúp sống sót khi máy chủ, vùng lưu trữ hoặc cả site gặp sự cố; access control giới hạn ai có thể tạo, đọc, xóa, thay đổi retention hoặc khôi phục bản sao. Bốn lớp này phải được thiết kế cùng với WAL archiving, backup catalog, key management, restore testing và mục tiêu RPO/RTO.

Bài học này tập trung vào cách xây dựng một chính sách bảo vệ backup PostgreSQL có thể vận hành được: chọn loại backup, mã hóa đúng tầng, quản lý khóa, lưu bản sao độc lập với máy chủ nguồn, thiết lập retention chống xóa nhầm/ransomware và phân quyền theo least privilege.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt logical backup, physical base backup, WAL archive và storage snapshots.
2. Xác định dữ liệu nào cần được mã hóa: backup files, WAL, manifests, catalog, credentials và transport.
3. Phân biệt encryption at rest, encryption in transit và client-side encryption.
4. Giải thích envelope encryption, KMS/HSM, data encryption keys và key-encryption keys.
5. Lập kế hoạch key rotation, key recovery, revocation và separation of duties.
6. Thiết kế backup retention theo RPO/RTO, business requirements và legal obligations.
7. Phân biệt full, differential, incremental backups và WAL retention.
8. Thiết kế offsite, cross-account, cross-region và immutable/WORM copies.
9. Phân quyền backup operator, restore operator, storage administrator và key administrator.
10. Áp dụng least privilege cho PostgreSQL roles, service accounts, object storage và KMS.
11. Bảo vệ backup catalog, manifests, checksums và archive chain.
12. Kiểm thử restore, PITR và disaster recovery thay vì chỉ kiểm tra backup job thành công.
13. Xử lý ransomware, credential compromise, accidental deletion, key loss và archive gaps.

> **Phạm vi:** Các ví dụ minh họa PostgreSQL self-managed và managed services. Tên role, quyền cloud, KMS APIs, backup tool options và hành vi retention phụ thuộc provider/version. Luôn kiểm tra tài liệu của công cụ và nền tảng đang dùng trước khi áp dụng cấu hình production.

## 2. Vì sao backup cần chính sách bảo vệ riêng?

Backup thường chứa:

- Dữ liệu khách hàng, giao dịch, thông tin định danh và dữ liệu nghiệp vụ.
- WAL records phản ánh thay đổi của database.
- Schema, function definitions, grants và role metadata trong một số logical dumps.
- Database names, hostnames, paths, topology và operational metadata.
- Manifests, backup labels, checksums và recovery information.

Một file backup bị lộ có thể cho phép attacker đọc dữ liệu offline mà không cần đăng nhập vào PostgreSQL. Một tài khoản có quyền xóa backup có thể làm hỏng khả năng phục hồi dù production database chưa bị thay đổi. Một KMS key bị xóa hoặc mất quyền truy cập có thể khiến backup còn nguyên bytes nhưng không giải mã được.

### Ba mục tiêu bảo vệ

**Confidentiality:** người không được phép không đọc được nội dung backup.

**Integrity:** backup không bị sửa, thay thế hoặc ghép sai mà không phát hiện.

**Availability:** backup và các khóa cần thiết còn truy cập được khi cần restore.

Một thiết kế chỉ mã hóa mà không quản lý key recovery có thể bảo vệ confidentiality nhưng phá availability. Một thiết kế chỉ có offsite copy nhưng cùng credentials có quyền xóa ở mọi nơi không bảo vệ tốt trước ransomware.

## 3. Phân loại các loại bản sao PostgreSQL

| Loại | Nội dung | Cách phục hồi thường gặp |
|---|---|---|
| Logical backup | Schema/data ở mức SQL objects, ví dụ pg_dump | pg_restore hoặc psql |
| Physical base backup | Data directory/cluster files nhất quán | Restore physical files, start recovery |
| WAL archive | WAL segments liên tục sau base backup | Replay WAL để PITR/roll-forward |
| Storage snapshot | Snapshot block volume/filesystem theo cơ chế nhất quán | Restore volume/snapshot, recovery theo quy trình |
| Configuration/metadata backup | Configs, service definitions, secrets references, backup catalog | Rebuild environment và kết nối backup chain |

### Logical backup

Ví dụ:

```sh
pg_dump -Fc -d appdb -f appdb.dump
pg_restore --list appdb.dump
```

Custom-format dump hỗ trợ restore chọn lọc và parallel restore với pg_restore. Logical backup hữu ích cho migration, object-level recovery và portability, nhưng không tự thay thế base backup + WAL archive cho PITR toàn cluster.

### Physical base backup

Ví dụ:

```sh
pg_basebackup \
  -h db-primary.example.internal \
  -U backup_user \
  -D /backup/staging/base_2026_11_14 \
  -Fp -X stream -P
```

Lệnh là ví dụ khái niệm; cần cấu hình replication connection, authentication, TLS, destination và quyền phù hợp. Physical backup thường gắn với một PostgreSQL major version/platform compatibility và cần WAL để phục hồi nhất quán.

### WAL archive

WAL archive cung cấp chuỗi log để replay từ base backup tới recovery target. Một base backup không có WAL chain cần thiết có thể không đáp ứng PITR. Ngược lại, WAL archive mà không có base backup tương ứng cũng không đủ để dựng database từ đầu.

## 4. Backup chain và recovery chain

Một chuỗi PITR cơ bản:

```text
Base backup B0
   |
   +-- WAL segment 0001
   +-- WAL segment 0002
   +-- WAL segment 0003
   +-- WAL segment 0004
             |
             +-- Recovery target time/LSN
```

Để khôi phục tại thời điểm T:

1. Chọn base backup bắt đầu trước T.
2. Xác minh base backup hoàn chỉnh và manifest/checksums hợp lệ.
3. Lấy đủ WAL segments liên tục từ backup tới T.
4. Khôi phục cấu hình recovery phù hợp.
5. Replay WAL đến target đã chọn.
6. Kiểm tra dữ liệu và mở dịch vụ theo cutover plan.

### Backup retention phải giữ cả chain

Không thể chỉ giữ “base backup mới nhất” rồi xóa tất cả WAL cũ nếu cần phục hồi về một thời điểm trước backup mới nhất. Retention policy phải biết mỗi base backup cần WAL range nào, timeline nào và backup catalog nào.

## 5. Mô hình bảo vệ backup theo nhiều lớp

Một kiến trúc tham khảo:

```text
PostgreSQL primary
   |
   +--> Backup agent / pg_dump / pg_basebackup
   |        |
   |        +--> Local staging (restricted, short-lived)
   |                 |
   |                 +--> Encrypt / checksum / manifest
   |                          |
   |                          +--> Offsite object storage
   |                                   |
   |                                   +--> Immutable retention / Object Lock
   |                                   |
   |                                   +--> Cross-account / cross-region copy
   |
   +--> WAL archive pipeline ----------------------^

KMS/HSM --> key policy / audit / rotation / recovery

Restore environment --> read-only verification --> controlled cutover
```

### Vì sao nhiều lớp?

- Mã hóa bảo vệ nội dung backup.
- Offsite bảo vệ khi host/site/volume nguồn bị mất.
- Immutable copy bảo vệ trước lệnh xóa/sửa trái phép.
- Cross-account tách quyền quản trị khỏi production.
- KMS tách quyền giải mã khỏi quyền đọc storage.
- Restore testing chứng minh chuỗi backup thật sự dùng được.

Không có một sản phẩm hay một checkbox nào thay thế toàn bộ các lớp này.

## 6. Encryption at rest

**Encryption at rest** bảo vệ dữ liệu lưu trên storage bằng cách mã hóa sector, volume, filesystem, object hoặc file. Với backup PostgreSQL, có thể mã hóa ở nhiều tầng:

| Tầng | Ví dụ | Phạm vi |
|---|---|---|
| Disk/volume encryption | Encrypted block volume | Mọi bytes trên volume |
| Filesystem encryption | Encrypted filesystem | Files trong filesystem |
| Object storage encryption | SSE-S3/SSE-KMS/provider-managed encryption | Objects lưu trên storage |
| Backup-tool encryption | pgBackRest encryption hoặc tool-supported encryption | Backup repository/content |
| Client-side/file encryption | Encrypt trước khi upload | Bytes đã mã hóa trước khi rời backup host |

### Mã hóa storage có đủ không?

Encryption at rest ở storage layer hữu ích khi disk/object bị tháo hoặc truy cập trực tiếp trái phép. Tuy nhiên, nếu attacker có quyền đọc object thông qua API được cấp phép, storage service có thể trả plaintext sau khi tự giải mã. Khi threat model yêu cầu storage administrator/provider không đọc được nội dung, cần cân nhắc client-side encryption với key do tổ chức kiểm soát.

### Mã hóa nhiều tầng

Có thể dùng cả volume encryption và backup-level encryption. Hai lớp có mục tiêu khác nhau: một lớp bảo vệ physical storage; lớp còn lại bảo vệ backup artifact khi copy qua nhiều storage systems hoặc tài khoản.

## 7. Encryption in transit

Backup data đi qua network giữa:

- PostgreSQL primary và backup host.
- Backup host và object storage.
- Primary và standby/replica.
- KMS client và key service.
- Restore host và storage.

Sử dụng TLS/HTTPS hoặc giao thức được mã hóa và xác thực cho mọi đường truyền. Với PostgreSQL connection, cấu hình TLS và xác minh server certificate/hostname, ví dụ:

```text
sslmode=verify-full
sslrootcert=/secure/path/ca.crt
```

### Chỉ bật encryption chưa đủ

TLS cần xác minh identity phía server. Nếu client chấp nhận mọi certificate hoặc không kiểm tra hostname, attacker có thể giả mạo endpoint trong một số tình huống. Dùng certificate validation phù hợp, bảo vệ CA material và theo dõi expiry/rotation.

### Kiểm tra kết nối PostgreSQL

```sql
SHOW ssl;

SELECT
    pid,
    usename,
    application_name,
    client_addr,
    ssl,
    version,
    cipher
FROM pg_catalog.pg_stat_ssl;
```

View pg_stat_ssl hiển thị trạng thái TLS của sessions. Quyền xem sessions khác có thể phụ thuộc privilege/version.

## 8. Client-side encryption và server-side encryption

**Server-side encryption (SSE):** storage service mã hóa object khi lưu và giải mã khi người dùng đọc object qua API được authorize.

**Client-side encryption (CSE):** backup client mã hóa bytes trước khi gửi đến storage; storage chỉ giữ ciphertext.

| Tiêu chí | SSE | CSE |
|---|---|---|
| Ai thực hiện mã hóa? | Storage provider/service | Backup client hoặc encryption gateway |
| Storage API trả gì? | Plaintext cho caller có quyền | Ciphertext; caller phải có key/client để giải mã |
| Quản lý key | Provider/KMS integration | Tổ chức hoặc KMS do tổ chức kiểm soát |
| Độ phức tạp restore | Thường đơn giản hơn | Cần tool/key/config tương thích |
| Bảo vệ trước storage admin | Tùy trust model/provider | Mạnh hơn nếu storage không có key |
| Key loss risk | Provider recovery model | Có thể mất khả năng restore nếu key mất |

### Chọn theo threat model

Nếu mục tiêu là bảo vệ media bị tháo hoặc object storage infrastructure, SSE có thể đáp ứng. Nếu cần ngăn storage account administrator đọc nội dung, client-side encryption thường phù hợp hơn. Dù chọn cách nào, hãy thử restore từ môi trường độc lập để xác nhận key access hoạt động.
# Mã hóa, lưu giữ, lưu ngoài máy chủ và phân quyền bản sao

Một bản sao lưu PostgreSQL chỉ có giá trị khi có thể khôi phục đúng dữ liệu, trong thời gian cần thiết và khi người có trách nhiệm vẫn truy cập được bản sao. Trong môi trường production, backup thường chứa dữ liệu nhạy cảm tương đương hoặc còn tập trung hơn database đang chạy. Vì vậy, bảo vệ backup cần giải quyết đồng thời bốn vấn đề: **mã hóa**, **lưu giữ**, **lưu ngoài máy chủ** và **phân quyền truy cập**.

Mã hóa bảo vệ nội dung khi file hoặc object bị đọc trái phép; retention xác định cần giữ những bản nào và trong bao lâu; offsite storage giúp sống sót khi máy chủ, vùng lưu trữ hoặc cả site gặp sự cố; access control giới hạn ai có thể tạo, đọc, xóa, thay đổi retention hoặc khôi phục bản sao. Bốn lớp này phải được thiết kế cùng với WAL archiving, backup catalog, key management, restore testing và mục tiêu RPO/RTO.

Bài học này tập trung vào cách xây dựng một chính sách bảo vệ backup PostgreSQL có thể vận hành được: chọn loại backup, mã hóa đúng tầng, quản lý khóa, lưu bản sao độc lập với máy chủ nguồn, thiết lập retention chống xóa nhầm/ransomware và phân quyền theo least privilege.

## 9. Envelope encryption

Nhiều hệ thống dùng **envelope encryption** để mã hóa lượng dữ liệu lớn mà không dùng trực tiếp một master key cho từng byte:

1. Tạo một Data Encryption Key (DEK) cho backup hoặc backup object.
2. Dùng DEK mã hóa backup content bằng thuật toán đối xứng phù hợp.
3. Dùng Key Encryption Key (KEK) trong KMS/HSM để wrap/mã hóa DEK.
4. Lưu ciphertext và wrapped DEK cùng metadata cần thiết.
5. Khi restore, client được authorize yêu cầu KMS unwrap DEK rồi giải mã backup.

```text
Backup plaintext
     |
     +-- DEK (random, scoped)
     |       |
     |       +-- encrypt backup --> ciphertext
     |
     +-- KEK in KMS/HSM
             |
             +-- wrap DEK --> wrapped DEK

Storage: ciphertext + wrapped DEK + manifest
```

### Vì sao envelope encryption hữu ích?

- KMS/HSM chỉ xử lý key material nhỏ thay vì hàng TB dữ liệu.
- DEK có thể khác nhau theo backup/object.
- KEK rotation có thể re-wrap DEKs trong một số thiết kế mà không mã hóa lại toàn bộ backup.
- KMS audit log có thể ghi nhận key usage.

### Phải lưu metadata

Backup manifest cần xác định encryption algorithm/version, key identifier, wrapped DEK, nonce/IV, authentication tag và tool/version metadata theo format đã chọn. Không tự thiết kế crypto format nếu không có thư viện/protocol đã được đánh giá.

## 10. Chọn thuật toán và thư viện mã hóa

Ưu tiên các thuật toán authenticated encryption hiện đại, được thư viện/tool uy tín hỗ trợ, ví dụ AES-256-GCM hoặc ChaCha20-Poly1305 trong môi trường phù hợp. Thuật toán cụ thể phải tuân theo policy bảo mật và khả năng của backup tool/KMS.

### Authenticated encryption

AEAD cung cấp confidentiality và integrity/authentication cho ciphertext. Nếu backup bị thay đổi, giải mã/verify authentication tag phải thất bại.

### Tránh tự xây crypto

- Không tự viết thuật toán mã hóa.
- Không tái sử dụng nonce/IV sai cách.
- Không lưu key cùng plaintext backup.
- Không hard-code password/key trong script hoặc repository.
- Không dùng checksum không keyed như bằng chứng chống attacker có quyền sửa cả file lẫn checksum.

Hãy dùng backup-tool encryption hoặc thư viện mã hóa chuẩn có định dạng versioned và quy trình key recovery đã thử nghiệm.

## 11. Checksum, integrity và authenticity

Checksum giúp phát hiện file bị hỏng trong truyền tải/lưu trữ:

```sh
sha256sum base_2026_11_14.tar
```

Nếu checksum được lưu trong manifest cùng backup, restore process có thể so sánh để phát hiện corruption.

### Checksum không tự chống sửa trái phép

Attacker có quyền ghi backup và manifest có thể thay cả hai. Để xác thực nguồn gốc/integrity trước attacker:

- Ký manifest bằng signing key tách biệt.
- Lưu signature ở repository/account độc lập.
- Giới hạn quyền ghi signature.
- Audit mọi lần tạo/verify.
- Có immutable copy để ngăn sửa nội dung sau khi lưu.

### Backup manifest

Một manifest nên mô tả:

- Backup ID, database/cluster identity.
- Backup type và tool/version.
- Thời điểm bắt đầu/kết thúc.
- Base backup/checkpoint/WAL range.
- File/object names và sizes.
- Checksums.
- Encryption metadata/key ID.
- Retention class và expiration.
- Restore instructions/config references.

Không đưa secrets, passwords hoặc plaintext keys vào manifest.

## 12. Key management: khóa quan trọng hơn file

Mã hóa backup chỉ có ích nếu key được bảo vệ và vẫn có thể truy cập khi restore. Key management cần giải quyết:

- Ai tạo key?
- Ai có quyền dùng key để encrypt?
- Ai có quyền decrypt?
- Ai có thể rotate/disable/delete key?
- Key được backup/recover ra sao?
- Key tồn tại bao lâu so với backup retention?
- Điều gì xảy ra khi nhân sự/service account rời hệ thống?

### KMS và HSM

KMS quản lý lifecycle, policy, audit và cryptographic operations. HSM cung cấp môi trường bảo vệ key material phần cứng. Managed KMS thường tích hợp HSM ở phía provider; chi tiết trust boundary phụ thuộc dịch vụ.

### Tách quyền

Backup operator có thể được phép dùng key để encrypt nhưng không nhất thiết được phép decrypt mọi backup. Restore operator cần decrypt trong môi trường restore được phê duyệt. Key administrator quản lý lifecycle/policy nhưng không nhất thiết có quyền đọc database backup.

## 13. DEK và KEK lifecycle

| Key | Vai trò | Lifecycle |
|---|---|---|
| DEK | Mã hóa backup bytes/object | Tạo theo backup hoặc repository policy; wrap bằng KEK; giữ wrapped copy cùng metadata |
| KEK | Bảo vệ DEK | Quản lý trong KMS/HSM; rotation, disable, policy và recovery |
| Signing key | Ký manifest/catalog | Tách quyền; bảo vệ private key; rotate theo trust policy |
| TLS private key | Xác thực endpoints | Certificate renewal/rotation; không dùng lại cho backup content |

### Không xóa key khi còn backup phụ thuộc

Nếu KEK bị xóa vĩnh viễn, wrapped DEKs có thể không unwrap được. Backup files vẫn tồn tại nhưng không thể giải mã. Retention policy phải tính **key retention** và key recovery cùng tuổi thọ backup.

## 14. Key rotation

Rotation có nhiều mức:

1. **KEK rotation:** thay key mã hóa DEK. Có thể re-wrap DEKs bằng KEK mới mà không mã hóa lại toàn bộ backup, nếu hệ thống hỗ trợ.
2. **DEK rotation:** tạo DEK mới cho backup tiếp theo hoặc re-encrypt existing backup theo policy.
3. **Signing key rotation:** chuyển manifest signatures sang signing key mới, giữ public verification keys cũ đủ lâu để verify lịch sử.
4. **TLS certificate rotation:** thay certificates trước expiry và cập nhật trust chains.

### Rotation không đồng nghĩa revoke ngay

Sau rotation, vẫn cần giải mã các backup cũ. Giữ key version cũ ở trạng thái decrypt-capable trong thời gian retention và recovery window; hạn chế quyền encrypt bằng key cũ nếu policy cho phép.

### Quy trình an toàn

- Tạo version mới.
- Cấp quyền encrypt/decrypt theo policy.
- Thử encrypt một backup test.
- Thử restore backup cũ bằng key cũ.
- Thử restore backup mới bằng key mới.
- Cập nhật catalog/runbook.
- Chỉ retire key cũ sau khi mọi dependencies hết hạn và có phê duyệt.

## 15. Key recovery và disaster recovery

Một sự cố site-wide có thể làm mất cả backup storage lẫn quyền truy cập KMS. Vì vậy cần kiểm tra:

- KMS service có sẵn ở region DR không?
- Identity/role restore có được provision ở account DR không?
- Key policy có cho phép decrypt từ restore environment không?
- Nếu KMS unavailable, có emergency process nào hợp lệ?
- Có key escrow/backup theo policy, nếu mô hình yêu cầu?
- Ai được phép kích hoạt emergency decrypt?

### Không xuất plaintext key ra file tùy tiện

Nếu cần key escrow hoặc recovery material, dùng quy trình HSM/KMS/provider được phê duyệt, dual control và audit. Không copy master key vào cùng offsite bucket với backup.

### Restore drill phải kiểm tra key path

Thử khôi phục backup trong tài khoản/region khác với quyền production thường ngày. Điều này xác nhận key policy, network, identity federation và decrypt permissions hoạt động khi disaster thật xảy ra.

## 16. Encryption password và secret handling

Một số công cụ backup dùng passphrase hoặc secret file để encrypt/decrypt. Cách truyền secret ảnh hưởng tới rủi ro:

- Tránh command-line arguments nếu process list/logs có thể lộ.
- Tránh echo secret trong shell history hoặc CI output.
- Tránh commit .env, credentials hoặc private keys vào Git.
- Dùng secret manager/short-lived credentials khi có thể.
- Giới hạn file permissions và process identity.
- Xóa staging plaintext sau khi xác nhận encrypted artifact hoàn chỉnh.

### Secret rotation

Khi đổi password hoặc credential của backup repository, cần giữ khả năng decrypt các backup cũ. Nếu mỗi repository dùng một key/passphrase riêng, catalog phải chỉ ra version tương ứng mà không chứa plaintext secret.

## 17. Retention policy là gì?

Retention xác định **backup nào được giữ, backup nào được phép hết hạn và điều kiện xóa**. Một chính sách phải bao phủ:

- Logical dumps.
- Physical full/incremental/differential backups.
- WAL archives.
- Manifests/catalogs/checksums.
- Encryption keys/key versions.
- Offsite/cross-region/immutable copies.
- Audit records và restore evidence.

### Retention không chỉ là “giữ 30 ngày”

Một doanh nghiệp có thể cần:

- Hourly recovery points trong vài ngày.
- Daily backups trong vài tuần.
- Weekly backups trong vài tháng.
- Monthly/year-end backups theo quy định.
- Legal hold cho một tập dữ liệu cụ thể.

Thời hạn phải xuất phát từ RPO, RTO, compliance, business recovery needs, privacy/data deletion obligations và storage cost.

## 18. Full, differential và incremental backup

Các công cụ backup có thể dùng thuật ngữ hơi khác nhau; kiểm tra semantics của tool:

| Loại | Nội dung |
|---|---|
| Full | Một bản backup đầy đủ độc lập theo định nghĩa công cụ |
| Differential | Thay đổi kể từ full backup gần nhất |
| Incremental | Thay đổi kể từ một backup trước đó, thường là backup gần nhất trong chain |

### Ví dụ chain

```text
Sunday: Full F0
Monday: Incremental I1
Tuesday: Incremental I2
Wednesday: Incremental I3

Restore Wednesday:
  F0 + I1 + I2 + I3
```

Nếu I2 bị thiếu/corrupt, restore chain có thể không hoàn tất tùy tool. Retention phải giữ các dependencies và backup catalog đủ để dựng lại đúng chain.

### Differential

Ví dụ:

```text
Sunday: Full F0
Monday: Diff D1 (since F0)
Tuesday: Diff D2 (since F0)
Wednesday: Diff D3 (since F0)

Restore Wednesday:
  F0 + D3
```

Differential có thể lớn dần theo thời gian; đổi lại restore chain ít bước hơn incremental chain.

## 19. Retention và WAL archive

Đối với physical backup + PITR:

- Giữ base backup đủ mới để đáp ứng recovery objectives.
- Giữ WAL segments liên tục cần cho từng base backup còn trong retention.
- Giữ timeline history files.
- Giữ backup manifest/catalog và checksums.
- Giữ encryption keys tương ứng.

### Ví dụ

Nếu giữ full backup 30 ngày và cần PITR đến bất kỳ thời điểm nào trong 30 ngày, phải giữ WAL archive liên tục cho các recovery chains được hỗ trợ trong khoảng đó. Không thể xóa WAL cũ chỉ vì một base backup mới vừa hoàn thành nếu các restore points cũ vẫn thuộc policy.

### Retention theo dependency

Một WAL segment có thể được nhiều backup/recovery windows cần. Chỉ xóa khi mọi chain còn được giữ không còn phụ thuộc vào nó.

## 20. Retention theo thời gian và theo số lượng

Hai cách thường gặp:

- Giữ theo age, ví dụ 35 ngày.
- Giữ theo count, ví dụ 7 full backups gần nhất.

### Kết hợp

Một policy có thể giữ:

- 14 daily recovery points.
- 8 weekly points.
- 12 monthly points.
- 1 annual point.

Đây là ví dụ minh họa, không phải lịch retention mặc định. Cần xác định daily/weekly/monthly backup nào là full hay synthetic full, và WAL ranges phụ thuộc thế nào.

### Không xóa chỉ theo filename timestamp

Dùng backup catalog/tool metadata để biết dependency và status. Xóa file thủ công có thể làm chain hỏng hoặc tool không nhận ra backup còn lại.

## 21. Retention lock và legal hold

Retention lock ngăn object bị xóa hoặc ghi đè trước một thời điểm đã định. Legal hold có thể giữ object vô thời hạn hoặc cho đến khi có quyết định release theo quy trình pháp lý.

### Hai chế độ thường gặp

- **Governance mode:** một số identity đặc biệt có thể override retention nếu được cấp quyền và đáp ứng policy.
- **Compliance mode:** retention lock nghiêm ngặt hơn; ngay cả administrator có quyền cao cũng không thể xóa object trước expiry theo semantics provider.

Tên gọi/chức năng phụ thuộc object storage provider.

### Cần phân biệt

Retention lock bảo vệ object khỏi bị xóa/sửa trong thời hạn. Nó không tự chứng minh nội dung object đúng, không thay encryption, không ngăn lộ dữ liệu và không bảo đảm key còn dùng được.

### Legal hold

Legal hold có thể áp dụng theo case/dataset, cần owner và audit trail. Không tự động xóa bản sao đang bị legal hold khi retention thường hết hạn.

## 22. Immutable backup và WORM

**WORM (Write Once, Read Many)** cho phép ghi một lần rồi bảo vệ object khỏi sửa/xóa trong thời hạn. Immutable backup hữu ích trước:

- Ransomware chiếm quyền production.
- Admin credential bị lộ.
- Script cleanup chạy nhầm.
- Attacker xóa backup cùng lúc với database.

### Thiết kế

1. Upload backup vào bucket/repository có versioning hoặc immutable retention.
2. Thiết lập retention lock trước khi attacker có thể thay đổi policy.
3. Tách quyền quản trị retention khỏi production account.
4. Bật audit log cho put/get/delete/retention changes.
5. Kiểm thử restore từ immutable copy.

### Versioning không tự là immutability

Versioning giúp giữ versions cũ, nhưng identity có quyền xóa versions hoặc lifecycle policy có thể vẫn xóa chúng. Kết hợp Object Lock/WORM và policy hạn chế delete/version deletion.

## 23. Offsite backup là gì?

Offsite backup là bản sao được lưu ngoài failure domain của hệ thống nguồn. Ví dụ:

- Một object storage account riêng.
- Một cloud region khác.
- Một provider hoặc storage system độc lập.
- Một data center/site khác.
- Offline/tape storage được kiểm soát.

### Vì sao cùng máy chủ không đủ?

Nếu backup nằm trên cùng volume hoặc cùng host với PostgreSQL, lỗi disk, ransomware, admin mistake hoặc mất host có thể làm mất cả primary lẫn backup.

### Độc lập failure domains

Offsite không chỉ là một thư mục khác. Cần xem:

- Credentials và identity provider.
- Account/subscription/project.
- Region/provider.
- Network/control plane.
- KMS key administration.
- Delete/retention policy.

Nếu cùng một admin credential có thể xóa cả primary và offsite copy, hai nơi vẫn chung một failure domain về quyền quản trị.

## 24. Cross-account và cross-region copies

Cross-account copy đặt backup ở account/project riêng để giảm blast radius khi production account bị compromise. Cross-region copy giúp khôi phục khi region chính mất khả năng hoạt động.

| Thiết kế | Bảo vệ chủ yếu | Cần kiểm tra |
|---|---|---|
| Same account, different bucket | Lỗi path/object ở mức hạn chế | Cùng admin/delete credentials |
| Separate account | Production account compromise | Trust policy, cross-account roles |
| Separate region | Region outage | KMS key availability, replication delay |
| Separate provider | Provider/control-plane outage | Data egress, format, restore tooling |
| Offline copy | Online ransomware/deletion | Custody, rotation, restore access |

### Cross-region không tự đủ

Nếu KMS key chỉ có ở region chính hoặc policy không cho phép DR role decrypt, backup copy ở region phụ có thể không restore được. Kiểm thử cả storage path và key path.

## 25. Thiết kế backup repository độc lập

Một repository offsite nên có:

- Storage account/project riêng.
- Bucket/container riêng cho từng environment hoặc security boundary.
- Versioning/immutability phù hợp.
- Encryption key policy độc lập.
- Service account chỉ có quyền cần thiết.
- Audit logs gửi sang hệ thống log riêng.
- Network/private endpoint hoặc egress policy nếu có.
- Lifecycle rules phù hợp retention.
- Restore role riêng, được kích hoạt có kiểm soát.

### Tách production và backup control plane

Không dùng chung một admin role để quản trị database, xóa backup, thay retention lock và xóa KMS keys. Tách quyền giúp một credential compromise không đồng thời phá toàn bộ recovery chain.

## 26. Backup staging trên máy chủ nguồn

Một số công cụ cần ghi backup vào local staging trước khi upload. Staging cần được bảo vệ:

- Dùng filesystem/volume có encryption at rest.
- Chỉ backup service account được đọc/ghi.
- Hạn chế quyền shell/admin trên host.
- Không để plaintext staging tồn tại lâu hơn cần thiết.
- Có disk quota/headroom và alert.
- Dọn file tạm bằng tool-aware cleanup.
- Không xóa staging khi upload chưa được xác nhận hoàn tất.

### Staging không phải offsite copy

Staging chỉ là điểm trung gian. Chỉ đánh dấu backup complete sau khi upload xong, checksum/integrity verify thành công và catalog cập nhật.

## 27. Quyền object storage: tách actions

Không gộp mọi quyền thành một role admin. Tách theo hành động:

| Role | Quyền điển hình | Không nên có mặc định |
|---|---|---|
| Backup writer | Put object vào prefix được chỉ định | Delete object, change retention, manage bucket policy |
| Restore reader | List/get object cần restore | Put/delete, change retention |
| Retention manager | Quản lý lifecycle/retention theo policy | Decrypt key hoặc đọc plaintext |
| Storage auditor | Đọc audit/config metadata | Đọc object content |
| Platform administrator | Quản trị account theo quy trình | Quyền đơn phương phá immutable controls |

Tên actions cụ thể phụ thuộc provider. Cần kiểm tra cả quyền kế thừa ở bucket, account, organization và KMS.

## 28. PostgreSQL backup role và quyền replication

Với physical backup qua pg_basebackup, user cần quyền replication phù hợp và được phép kết nối theo pg_hba.conf. Ví dụ:

```sql
CREATE ROLE backup_user
WITH LOGIN REPLICATION
PASSWORD 'set-through-secret-management';
```

Ví dụ chỉ minh họa role attribute. Không đặt password production trong SQL history hoặc script plaintext; dùng secret manager và rotate theo policy.

### Logical dump privileges

pg_dump thường cần quyền CONNECT, USAGE/SELECT trên các objects được dump, cùng quyền đọc large objects/sequence hoặc metadata theo nhu cầu. Dùng role riêng, read-only và test trên schema thực tế; không cấp superuser chỉ để backup chạy.

### Row-Level Security

Nếu bảng bật RLS, cần hiểu pg_dump behavior, quyền BYPASSRLS/owner và option tương ứng. Backup thiếu rows do RLS có thể hoàn tất thành công nhưng không phải bản sao đầy đủ. Xác định rõ backup role có được phép bypass RLS theo policy và audit.

## 29. pg_hba.conf và network access

Chỉ cho phép backup service account kết nối từ backup host/network được chỉ định. Dùng TLS và authentication phù hợp, giới hạn CIDR và tránh mở replication connection cho toàn internet.

Ví dụ khái niệm:

```text
# TYPE  DATABASE  USER         ADDRESS          METHOD
hostssl replication backup_user 10.20.30.40/32   scram-sha-256
```

Đây là ví dụ syntax; cần đặt rule đúng vị trí trong pg_hba.conf và cấu hình TLS/certificate. Một rule rộng hơn ở phía trên có thể match trước rule hẹp hơn.

### Không quên network policy

Security group/firewall/private endpoint cũng cần giới hạn source/destination. pg_hba.conf không thay thế network firewall.

## 30. Service accounts và short-lived credentials

Backup automation không nên phụ thuộc tài khoản người dùng cá nhân. Dùng service identity riêng:

- Một identity để tạo backup.
- Một identity để ghi offsite repository.
- Một identity để restore/read.
- Một identity quản lý key nếu cần.

### Ưu tiên credentials ngắn hạn

Khi provider hỗ trợ, dùng workload identity, instance role, managed identity hoặc short-lived tokens thay static access keys. Điều này giảm nguy cơ secret lâu dài bị lộ.

### Nếu phải dùng static credentials

- Lưu trong secret manager.
- Hạn chế scope/resource/actions.
- Rotate định kỳ và sau sự cố.
- Không chia sẻ giữa production và DR.
- Audit usage và phát hiện credentials bất thường.

## 31. Separation of duties

Tách các nhiệm vụ quan trọng:

| Nhiệm vụ | Vai trò đề xuất |
|---|---|
| Tạo backup | Backup operator/service |
| Đọc backup | Restore operator được phê duyệt |
| Xóa/expire backup | Retention manager theo policy |
| Thay đổi Object Lock | Security/storage administrator có dual control |
| Tạo/rotate KEK | Key administrator |
| Decrypt trong DR | Restore role + KMS policy/approval |
| Kiểm tra audit | Security auditor |

### Vì sao cần tách?

Một người có thể cần tạo backup nhưng không nên có khả năng xóa tất cả copies hoặc xóa key dùng để giải mã. Một người quản lý key có thể không cần quyền đọc plaintext data. Separation of duties giảm rủi ro insider và credential compromise.

## 32. Audit trail và phát hiện truy cập bất thường

Ghi nhận:

- Ai tạo backup, từ host/database nào.
- Ai upload/download object.
- Ai gọi decrypt/unwrap key.
- Ai thay retention/lifecycle/Object Lock.
- Ai xóa object/version hoặc thay bucket policy.
- Ai restore và nơi nhận dữ liệu.
- Ai thay credentials/roles/KMS policies.

### Audit logs phải độc lập

Nếu audit logs chỉ nằm trong production account, attacker chiếm account có thể xóa cả backup và bằng chứng. Gửi audit events sang log account/SIEM độc lập, áp dụng retention/immutability và hạn chế quyền chỉnh sửa.

## 33. Backup catalog và metadata protection

Backup catalog thường chứa thông tin về:

- Backup IDs và backup sets.
- Parent/child relationships của incremental backups.
- WAL ranges/timelines.
- Start/stop LSN hoặc backup labels.
- Checksums và file mappings.
- Encryption key IDs/versions.
- Retention/expiration state.

Catalog bị mất có thể khiến việc tìm và ghép backup chain khó khăn dù files vẫn còn. Bảo vệ catalog bằng backup riêng, versioning, encryption, immutable/offsite copies và restore test.

### Catalog không chứa plaintext secrets

Catalog nên chứa key identifier và metadata cần thiết, không chứa DEK plaintext, passphrase hoặc cloud credentials.

## 34. Backup integrity và restore verification

Backup job exit code 0 chỉ chứng minh công cụ báo thành công theo quy trình của nó. Cần nhiều lớp kiểm tra:

1. Backup file/object có đủ size và manifest.
2. Checksum/hash verify thành công.
3. Backup catalog nhận diện backup.
4. WAL chain liên tục nếu cần PITR.
5. Encryption metadata/key ID có thể resolve.
6. Restore tool có thể đọc và giải mã.
7. PostgreSQL có thể start/recover.
8. Dữ liệu nghiệp vụ được kiểm tra sau restore.

### Integrity vs recoverability

Checksum đúng không chứng minh database có thể start. Backup decrypt được không chứng minh WAL chain đủ. Database start không chứng minh business data đầy đủ hoặc RPO được đáp ứng. Cần kiểm thử end-to-end.

## 35. Restore test theo lịch

Thiết kế restore drills:

- Restore logical dump vào isolated database.
- Restore physical base backup vào isolated host.
- Replay WAL đến một target time.
- Restore offsite copy ở region/account DR.
- Restore bằng key version cũ.
- Restore khi production credentials không khả dụng.
- Kiểm tra backup chain sau retention cleanup.

### Đo

- Restore duration.
- WAL replay duration.
- Data validation duration.
- Key access latency/failure.
- Network throughput.
- Storage provisioning time.
- RTO thực tế so với mục tiêu.

Không chỉ kiểm tra backup creation; **restore test mới chứng minh bản sao có thể sử dụng**.

## 36. RPO, RTO và retention

**RPO (Recovery Point Objective):** lượng dữ liệu tối đa tổ chức chấp nhận mất, thường biểu diễn theo thời gian.

**RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ.

Ví dụ:

- RPO 15 phút: cần recovery points/WAL archive đủ sát để mất tối đa 15 phút thay đổi.
- RTO 2 giờ: cần base backup, WAL chain, keys, compute/storage và restore runbook đủ nhanh để đưa dịch vụ trở lại trong 2 giờ.

### RPO không chỉ do lịch full backup

PITR với WAL archiving liên tục có thể tạo recovery points gần thời điểm sự cố hơn. Nếu archive lag 40 phút, lịch base backup mỗi đêm không cứu được RPO 15 phút.

### RTO không chỉ do kích thước backup

Thời gian restore còn phụ thuộc provisioning, network, decrypt, decompression, WAL replay, index/constraint validation, application checks và cutover.

## 37. Retention, privacy và data deletion

Backup retention có thể xung đột với yêu cầu xóa dữ liệu cá nhân hoặc legal hold. Cần policy được pháp lý/security/data governance phê duyệt:

- Xác định retention basis cho từng loại dữ liệu.
- Xác định khi nào backup hết hạn và được xóa.
- Xem liệu có cần cryptographic erasure theo key scope hay không.
- Quản lý legal hold/exception.
- Ghi nhận khi dữ liệu được xóa khỏi live systems và thời điểm backup cũ hết hạn.
- Đảm bảo restore không tái đưa dữ liệu đã xóa vào production mà không chạy lại deletion controls.

### Cryptographic erasure

Trong một số thiết kế, hủy key có thể khiến ciphertext không thể giải mã. Đây là thao tác có hậu quả lớn và không thể thay thế quy trình xóa dữ liệu nếu key dùng chung cho nhiều backup hoặc có bản plaintext khác. Chỉ áp dụng khi encryption/key scope và legal policy được thiết kế rõ.

## 38. Ransomware và immutable backups

Ransomware có thể tìm kiếm và xóa backup trước khi mã hóa production. Các biện pháp:

- Tách backup account khỏi production identity.
- Dùng immutable/WORM retention.
- Hạn chế quyền delete/version delete.
- Bảo vệ KMS key deletion bằng dual control và deletion waiting period nếu provider hỗ trợ.
- Dùng credentials ngắn hạn.
- Giữ offline/air-gapped copy theo threat model.
- Audit và alert hành động xóa/retention changes.
- Kiểm tra restore từ bản immutable.

### Không coi immutable là toàn bộ giải pháp

Attacker vẫn có thể đánh cắp plaintext nếu có decrypt rights, làm hỏng backup mới trước khi lock, hoặc chiếm restore environment. Cần phân tách write/read/decrypt/delete permissions và kiểm tra backup integrity.

## 39. Bảo vệ trước accidental deletion

Các lớp bảo vệ:

- Object versioning.
- Soft delete/recycle bin theo provider.
- Retention lock.
- MFA/approval cho destructive operations.
- Cross-account copy.
- Audit alerts cho delete events.
- IaC review cho lifecycle/bucket policy changes.

### Lifecycle rules

Lifecycle policy có thể tự xóa object sau expiration. Lỗi cấu hình prefix/tag có thể xóa backup còn cần. Test rule trên prefix sandbox, review plan, dùng tag rõ ràng và theo dõi số objects sắp expire.

## 40. Quy trình publish một backup an toàn

Một pipeline tham khảo:

1. Tạo backup từ PostgreSQL theo snapshot/backup tool protocol.
2. Thu thập WAL/metadata cần thiết cho consistency và PITR.
3. Tính checksums và tạo manifest.
4. Mã hóa backup bằng DEK.
5. Wrap DEK bằng KEK/KMS.
6. Upload ciphertext/manifest vào offsite repository.
7. Áp dụng immutable retention và cross-account/region replication.
8. Verify object sizes/checksums/signatures.
9. Cập nhật backup catalog và key references.
10. Chạy restore validation theo lịch và ghi audit evidence.

### Trạng thái backup

Không đánh dấu backup COMPLETE ngay sau khi local dump kết thúc. Chỉ publish complete khi mọi artifacts, WAL dependencies, encryption metadata, object uploads và integrity checks cần thiết đã thành công.

## 41. Ví dụ: pgBackRest và repository encryption

pgBackRest là một công cụ phổ biến để quản lý physical backups, incremental/differential backups, WAL archiving và repository. Công cụ hỗ trợ mã hóa repository bằng passphrase trong các cấu hình phù hợp.

Ví dụ cấu hình khái niệm:

```ini
[global]
repo1-type=s3
repo1-path=/pgbackrest
repo1-s3-bucket=company-pg-backups
repo1-s3-region=ap-southeast-1
repo1-cipher-type=aes-256-cbc
repo1-cipher-pass=<provided-through-secure-secret-management>

[app]
pg1-path=/var/lib/postgresql/data
```

Đây là ví dụ minh họa các loại cấu hình, không phải file production hoàn chỉnh. Các options, encryption modes và provider-specific settings phải được xác nhận theo phiên bản pgBackRest đang dùng. Không đặt passphrase plaintext trong file config có quyền đọc rộng; dùng secret injection và file permissions phù hợp.

### Cần kiểm tra

- Repository encryption đã bật trên đúng repo chưa?
- Mọi backup/WAL objects cần thiết có được mã hóa không?
- Key/passphrase có được lưu và recover độc lập không?
- Restore host có thể đọc repository và giải mã không?
- Repository metadata/catalog có được bảo vệ không?
- Offsite bucket có immutable retention và policy riêng không?

## 42. Ví dụ: Barman và object storage

Barman quản lý physical backup và WAL archiving cho PostgreSQL. Bản thân kiến trúc backup có thể kết hợp với encryption ở filesystem, storage, object storage hoặc một lớp client-side phù hợp.

### Thiết kế

1. Barman nhận base backup/WAL từ PostgreSQL.
2. Backup repository nằm trên storage đã mã hóa.
3. Một pipeline copy/replicate artifacts sang offsite object storage.
4. Object storage bật SSE-KMS hoặc nhận ciphertext đã được mã hóa client-side.
5. Bucket policy/retention lock ngăn xóa trái phép.
6. Restore drill xác nhận Barman và key access đọc được bản offsite.

Không giả định chỉ vì Barman backup thành công thì repository đã có client-side encryption. Xác định chính xác encryption layer và test plaintext exposure theo threat model.

## 43. Ví dụ: pg_dump mã hóa trước khi upload

Với logical dump, có thể tạo file custom-format rồi đưa qua một công cụ mã hóa chuẩn trước khi upload:

```sh
pg_dump -Fc -d appdb -f /secure-staging/appdb.dump

# Encrypt using an approved, authenticated-encryption tool.
# Store ciphertext and signed manifest in offsite storage.

sha256sum /secure-staging/appdb.dump
```

Đoạn trên mô tả các bước, không cung cấp lệnh mã hóa cụ thể vì định dạng/key management phụ thuộc tool được tổ chức phê duyệt. Không tự ghép OpenSSL flags hoặc cipher options vào production khi chưa định nghĩa nonce, authentication, key wrapping và restore format.

### Restore

1. Download ciphertext.
2. Verify signed manifest/checksum.
3. Obtain decrypt permission/key version.
4. Decrypt vào staging được bảo vệ.
5. Chạy pg_restore --list để xác nhận dump đọc được.
6. Restore vào isolated database.
7. Chạy data validation.

Không giải mã backup nhạy cảm vào thư mục world-readable hoặc ổ đĩa tạm không được mã hóa.

## 44. Snapshot storage và consistency

Storage snapshot có thể rất nhanh, nhưng snapshot database đang hoạt động phải tuân theo consistency protocol. Một block snapshot không được tạo theo quy trình PostgreSQL-aware có thể cần crash recovery và WAL phù hợp.

### Các kiểu snapshot

- Crash-consistent: tương đương storage bị mất điện tại một thời điểm; PostgreSQL cần recovery.
- Application-consistent: backup orchestration phối hợp với database để đảm bảo state nhất quán.
- Snapshot có WAL/archive integration: kết hợp volume snapshot và WAL để phục hồi/PITR.

### Cần xác minh

- Snapshot bao gồm đúng volumes/data files cần thiết?
- WAL/pg_wal có được snapshot hoặc archive nhất quán?
- Có nhiều volumes phải snapshot đồng bộ không?
- Có backup label/metadata cần thiết?
- Restore snapshot có thể start/recover trên đúng PostgreSQL version?

Snapshot nhanh không đồng nghĩa backup hoàn chỉnh hoặc PITR-ready.

## 45. Backup encryption và WAL encryption

WAL chứa thông tin thay đổi dữ liệu, có thể tiết lộ dữ liệu nhạy cảm. Nếu backup base được mã hóa nhưng WAL archive plaintext, attacker có thể đọc hoặc tái dựng một phần nội dung.

### Phải bao phủ

- Base backups.
- WAL archive segments.
- Logical dumps.
- Temporary/staging files.
- Backup manifests/catalogs.
- Exported configuration files.
- Replicated copies và cross-region copies.

### Encryption scope

Xác định liệu encryption áp dụng trước upload hay do storage service thực hiện. Kiểm tra mọi đường đi của WAL, bao gồm archive command, object replication, restore download và temporary spool.

## 46. TLS cho WAL streaming và backup connections

Streaming replication và pg_basebackup dùng PostgreSQL connections. Có thể yêu cầu TLS qua server settings/pg_hba rules và client SSL parameters.

### Kiểm tra

```sql
SHOW ssl;
SHOW ssl_min_protocol_version;

SELECT
    pid,
    usename,
    application_name,
    client_addr,
    ssl,
    version,
    cipher
FROM pg_catalog.pg_stat_ssl;
```

### Certificate lifecycle

- Bảo vệ private keys với quyền filesystem chặt.
- Dùng CA/certificate chain có quy trình renewal.
- Cập nhật trust stores ở backup/restore hosts.
- Theo dõi expiry trước khi đến hạn.
- Kiểm tra hostname verification.
- Thu hồi certificate khi identity bị compromise.

Không để backup pipeline fail bất ngờ vì certificate hết hạn hoặc CA rotation không được triển khai trên DR host.

## 47. Encryption metadata và tool compatibility

Một backup có thể được mã hóa bởi tool/version cụ thể. Để restore nhiều năm sau, cần lưu:

- Tool name/version.
- Encryption format/version.
- Cipher/AEAD algorithm.
- KMS key ID/version hoặc passphrase reference.
- Wrapped DEK metadata.
- Compression format/version.
- Manifest schema version.
- Restore commands/runbook đã kiểm chứng.

### Backward compatibility

Đừng nâng cấp tool hoặc đổi encryption format mà không thử đọc backup cũ. Giữ binary/container image phù hợp hoặc xác định đường migrate repository sang format mới.

### Không lưu secrets trong runbook

Runbook chỉ tham chiếu secret manager/key ID và hướng dẫn authorization. Không chèn passphrase/private key trực tiếp vào tài liệu hoặc ticket.

## 48. Compression và encryption order

Thông thường, dữ liệu được **compress trước rồi encrypt**:

```text
Database backup
   |
   +--> Compression
           |
           +--> Encryption
                   |
                   +--> Offsite storage
```

Encryption làm dữ liệu có entropy cao, nên compress sau encryption thường gần như không giảm size. Compression trước encryption thường tiết kiệm storage/network hơn.

### Tác động

- Compression dùng CPU và có thể kéo dài backup.
- Encryption dùng CPU hoặc accelerator.
- Parallelism ảnh hưởng throughput và memory.
- Restore cần giải mã rồi giải nén.

Đo end-to-end backup/restore time trên dữ liệu đại diện; không tối ưu storage ratio mà làm RTO vượt mục tiêu.

## 49. Backup repository và deduplication

Một số công cụ/repositories hỗ trợ block-level deduplication hoặc incremental chains. Dedup có thể giảm storage, nhưng retention/immutability và encryption order ảnh hưởng hiệu quả:

- Encrypt từng file bằng DEK ngẫu nhiên có thể làm bytes thay đổi hoàn toàn và giảm dedup.
- Repository-level encryption có thể bảo toàn dedup trong một số tool design.
- Dedup service có thể cần thấy plaintext hoặc chunk metadata tùy kiến trúc.

### Threat model

Deduplication có thể làm lộ thông tin qua side channels trong một số thiết kế cross-tenant. Dùng cơ chế của tool/provider đã được đánh giá; không tự thiết kế convergent encryption chỉ để tiết kiệm storage.

## 50. Retention của backup logical và physical

Logical dumps và physical backups có đặc tính khác:

| Tiêu chí | Logical | Physical |
|---|---|---|
| Portability | Cao hơn giữa một số environments/versions | Gắn với cluster/version/platform |
| Object-level restore | Thuận tiện hơn | Thường restore cluster/database rồi xử lý |
| PITR toàn cluster | Không tự có từ dump đơn lẻ | Kết hợp base backup + WAL |
| Size/time | Có thể tốn thời gian cho database lớn | Thường phù hợp physical recovery lớn |
| Retention dependencies | Thường độc lập từng dump | Incremental chain/WAL dependencies |

Một chiến lược có thể giữ daily logical dumps cho selected databases và physical base backup + WAL cho disaster recovery. Cả hai cần encryption, offsite, retention và restore tests.

## 51. Phân vùng retention theo sensitivity

Không phải mọi database có cùng dữ liệu nhạy cảm hoặc thời hạn lưu giữ. Có thể phân loại:

- Tier A: dữ liệu khách hàng/tài chính, encryption mạnh, immutable offsite, access approval.
- Tier B: operational metadata, retention ngắn hơn theo nhu cầu.
- Tier C: test/synthetic data, policy đơn giản hơn nhưng vẫn có access controls.

### Cẩn thận với derived data

Một database được xem là “chỉ metadata” vẫn có thể chứa usernames, email, IP addresses, internal topology hoặc SQL text. Đánh giá nội dung thực tế trước khi giảm controls.

## 52. Access control cho backup repository

Access control phải kiểm soát riêng:

- List objects.
- Read/download.
- Upload/create.
- Overwrite existing versions.
- Delete versions.
- Change retention/legal hold.
- Change bucket policy/encryption settings.
- Decrypt/unwrap keys.
- Replicate objects/copy across accounts.

### Least privilege

Một backup writer thường chỉ cần Put vào prefix cụ thể. Nó không cần Delete bucket, đổi lifecycle hoặc quản lý KMS key. Restore reader cần Get/List trong thời gian được cấp quyền. Retention manager cần policy actions nhưng không cần đọc plaintext.

## 53. Object prefix và environment isolation

Tổ chức repository theo security boundary:

```text
backup-root/
  prod/
    cluster-a/
    cluster-b/
  staging/
    cluster-test/
  legal-hold/
    case-2026-001/
```

Đây là layout ví dụ. Có thể dùng bucket/container riêng thay prefix nếu cần policy độc lập mạnh hơn.

### Lợi ích

- Role chỉ có quyền trên prefix/environment cần thiết.
- Retention có thể khác nhau.
- Audit phân tách dễ hơn.
- Tránh backup test ghi đè production.

Prefix không tự tạo security boundary nếu bucket policy cho phép access rộng.

## 54. Access control cho restore

Restore có thể tạo một bản sao plaintext ở môi trường mới. Quy trình cần xác định:

- Ai được yêu cầu restore?
- Ai phê duyệt dữ liệu nhạy cảm?
- Restore vào account/VPC/network nào?
- Ai có decrypt permission và trong thời gian bao lâu?
- Có cần masking/anonymization trước khi developer truy cập?
- Staging data được giữ bao lâu và xóa thế nào?

### Restore không tự động cho phép sử dụng dữ liệu

Một engineer có thể cần kiểm thử restore nhưng không cần đọc dữ liệu khách hàng. Có thể restore trong isolated environment, giới hạn network, mask dữ liệu và cấp access tạm thời theo ticket.

## 55. Restore testing và dữ liệu nhạy cảm

Khi restore backup production vào non-production:

- Giới hạn người truy cập.
- Mask/anonymize dữ liệu nếu phù hợp.
- Không gửi dump qua email/chat.
- Dùng encrypted volumes.
- Hạn chế outbound network.
- Xóa staging sau thời hạn.
- Audit query/download activity nếu có.

Backup encryption không còn bảo vệ khi restore thành plaintext. Restore environment cần controls tương đương production hoặc policy riêng được phê duyệt.

## 56. Immutable retention và quyền delete

Một role backup writer có thể được phép tạo object mới nhưng không xóa versions. Retention service có thể tự expire objects khi đủ hạn. Security admin có quyền thay Object Lock phải được bảo vệ bằng MFA/dual approval.

### Xử lý exception

Nếu cần xóa backup sớm vì privacy/legal requirement:

1. Xác định chính xác objects/versions và dependencies.
2. Kiểm tra legal hold và regulatory rules.
3. Xác nhận restore chain còn đáp ứng policy sau deletion.
4. Phê duyệt bởi owner/security/legal theo quy trình.
5. Thực hiện bằng role chuyên biệt.
6. Lưu audit evidence và kiểm tra trạng thái sau thao tác.

Không bypass retention lock bằng cách xóa bucket/account hoặc key mà không đánh giá hậu quả phục hồi.

## 57. Cross-account copy và trust policy

Backup writer từ production account chỉ nên assume role ở backup account với quyền upload đúng prefix. Backup account không nên tin mọi principal của production account.

### Kiểm soát

- Giới hạn principal ARN/service identity cụ thể.
- Giới hạn external ID/conditions nếu provider hỗ trợ.
- Hạn chế actions và resource ARNs.
- Dùng session duration ngắn.
- Audit AssumeRole và object writes.
- Không cấp quyền thay bucket policy/retention.

### Restore role

Restore role có thể ở account DR riêng, chỉ được bật trong thời gian restore và có quyền read/decrypt phù hợp. Có thể dùng approval workflow hoặc just-in-time access.

## 58. KMS policy và decrypt permissions

Object storage policy và KMS key policy là hai lớp khác nhau. Một principal có quyền GetObject nhưng không có quyền decrypt key có thể tải ciphertext nhưng không đọc plaintext. Ngược lại, có decrypt key nhưng không đọc object cũng không đủ restore.

### Kiểm tra cả hai

- Storage identity có Get/List đúng objects?
- KMS identity có decrypt/unwrap đúng key version?
- Key policy có cho phép role DR?
- Network endpoint tới KMS có hoạt động ở region DR?
- Key chưa bị disabled/pending deletion?
- Audit log ghi nhận decrypt events?

Đừng cấp kms:* chỉ để sửa một lỗi AccessDenied. Xác định action cụ thể và resource/key context.

## 59. KMS deletion protection

Xóa KEK có thể phá khả năng decrypt tất cả backup phụ thuộc. Bảo vệ key:

- Hạn chế quyền schedule deletion.
- Yêu cầu MFA/dual approval.
- Bật deletion waiting period nếu provider hỗ trợ.
- Alert khi key policy/disable/deletion thay đổi.
- Giữ key inventory gắn với backup retention.
- Kiểm tra key state trong backup verification.

### Disable khác delete

Disable key có thể tạm ngăn decrypt nhưng có thể bật lại; scheduled deletion có thể dẫn tới mất key vĩnh viễn sau waiting period. Runbook phải phân biệt và quy định người có quyền thực hiện.

## 60. Retention và lifecycle automation

Lifecycle automation giúp expire backups theo policy nhưng phải nhận diện dependency:

1. Xác định backup set đã hết retention.
2. Kiểm tra backup không phải parent của incremental chain còn được giữ.
3. Kiểm tra WAL range không còn cần cho bất kỳ recovery point nào còn hiệu lực.
4. Kiểm tra legal hold.
5. Kiểm tra immutable retention expiry.
6. Xóa qua backup tool/catalog hoặc lifecycle mechanism được hỗ trợ.
7. Cập nhật catalog/audit.
8. Xác minh restore points còn lại vẫn hoạt động.

Không dùng một rule xóa mọi object sau 30 ngày nếu backup chain cần dependencies dài hơn hoặc có monthly/legal copies.

## 61. Quy trình restore từ offsite backup

Một restore runbook nên mô tả các bước theo thứ tự:

1. Mở incident/change record và xác định business owner.
2. Chọn recovery point phù hợp với RPO.
3. Xác định base backup và WAL chain cần thiết.
4. Xác nhận backup manifest, signature/checksum và catalog.
5. Provision restore host/storage/network.
6. Cấp short-lived storage read và KMS decrypt permissions.
7. Download ciphertext về encrypted staging.
8. Verify integrity rồi decrypt/decompress.
9. Restore physical files hoặc pg_restore logical dump.
10. Replay WAL tới target nếu PITR.
11. Chạy database/business validation.
12. Cấp quyền ứng dụng, cutover và theo dõi.
13. Revoke temporary permissions, bảo vệ/xóa staging theo policy.

### Phải có owner cho từng bước

Runbook cần nêu người thực hiện, người phê duyệt, thời gian dự kiến, dependencies và escalation contact. Một lệnh restore không đủ làm runbook disaster recovery.

## 62. PITR và recovery target

PostgreSQL hỗ trợ recovery target theo thời gian, transaction ID, restore point hoặc LSN tùy version/configuration. Một số cấu hình recovery hiện đại dùng recovery.signal cùng các recovery_target_* parameters; cách triển khai phụ thuộc major version.

Ví dụ khái niệm:

```text
restore_command = 'retrieve archived WAL segment'
recovery_target_time = '2026-11-14 10:30:00+07'
recovery_target_action = 'pause'
```

Không copy nguyên dòng restore_command này vào production: nó phải là command/script lấy đúng WAL segment, kiểm tra tên file và trả exit status phù hợp. Chọn target action theo kế hoạch cutover và version.

### Chọn recovery target

- Tìm thời điểm ngay trước thao tác gây hỏng dữ liệu.
- Xác nhận timezone/time source.
- Nếu dùng named restore point, kiểm tra WAL có chứa restore point.
- Dùng pause để kiểm tra state trước khi promote nếu quy trình yêu cầu.
- Tránh target quá sớm gây mất giao dịch hợp lệ không cần thiết.

## 63. PITR chain completeness

Trước restore, cần xác nhận:

- Base backup hợp lệ và có metadata start/stop.
- WAL archive bắt đầu từ segment cần thiết cho base backup.
- Không thiếu segment giữa chừng.
- Timeline history files có đủ nếu có timeline switch.
- Encryption key versions còn hoạt động.
- Restore command truy cập đúng repository/region.
- Backup tool biết chain/dependencies.

Một gap WAL nhỏ có thể làm PITR tới target muộn hơn thất bại dù backup files khác vẫn nguyên vẹn.

## 64. Restore vào isolated environment

Đừng restore backup production trực tiếp đè lên production đang hoạt động nếu chưa có cutover plan.

### Isolated restore

- Dùng VPC/subnet riêng.
- Chặn outbound network mặc định.
- Không đăng ký vào service discovery production.
- Không gửi email/payment/webhook thật.
- Dùng credentials riêng.
- Giới hạn người truy cập.
- Mask dữ liệu nếu dùng cho non-production.

### Vì sao?

Một database restore có thể chứa jobs, triggers, scheduled tasks hoặc credentials khiến application thực hiện side effects khi khởi động. Isolation giúp kiểm tra dữ liệu mà không tạo giao dịch ngoài ý muốn.

## 65. Restore validation cho PostgreSQL

Sau khi database start:

```sql
SELECT version();
SELECT pg_is_in_recovery();
SELECT current_database();
SELECT now();
```

Kiểm tra thêm:

- Expected databases/schemas/tables tồn tại.
- Row counts/aggregates/key ranges theo validation plan.
- Constraints và indexes usable.
- Extensions/functions/roles/configuration phù hợp.
- Sequences/identity values ở trạng thái đúng.
- WAL recovery kết thúc theo target mong muốn.
- Application smoke tests thành công.

### Không chỉ đếm rows

Một table có đúng row count vẫn có thể thiếu hoặc sai dữ liệu. Dùng business invariants, checksums, sums, representative queries và application-level checks.

## 66. Restore logical dump

Kiểm tra archive:

```sh
pg_restore --list appdb.dump
```

Restore vào database test:

```sh
createdb restore_test
pg_restore \
  --dbname=restore_test \
  --no-owner \
  --no-privileges \
  appdb.dump
```

Options như no-owner/no-privileges chỉ phù hợp với một số môi trường; nếu cần giữ ownership/grants, phải có roles tương ứng và restore policy phù hợp.

### Globals

pg_dump không tự backup cluster-wide roles/tablespaces như pg_dumpall globals. Nếu cần, lưu globals theo quy trình riêng và bảo vệ file đó như dữ liệu nhạy cảm:

```sh
pg_dumpall --globals-only > globals.sql
```

Kiểm tra nội dung và quyền file; globals dump có thể chứa role definitions/password hashes và security metadata.

## 67. Restore physical base backup

Với physical backup:

1. Dùng PostgreSQL major version tương thích.
2. Chuẩn bị data directory rỗng và owner/permissions phù hợp.
3. Khôi phục base backup theo tool.
4. Cung cấp WAL archive và restore command.
5. Cấu hình recovery target nếu cần PITR.
6. Start server trong network cô lập.
7. Theo dõi recovery logs đến khi đạt target.
8. Kiểm tra pg_is_in_recovery() và dữ liệu.

Không copy một data directory đang chạy bằng filesystem copy thông thường mà không dùng backup protocol/snapshot consistency phù hợp.

## 68. Restore test cho encryption key cũ

Mỗi key rotation nên kèm restore test:

| Test | Kết quả mong đợi |
|---|---|
| Backup mã hóa bằng key version cũ | Decrypt thành công trong retention window |
| Backup mới bằng key version mới | Decrypt thành công |
| Restore role ở DR account | Có quyền unwrap key cần thiết |
| Key bị disable trong lab | Restore fail có thông báo rõ; re-enable theo approval |
| Manifest có key ID sai | Validation fail trước khi restore |

Không thử disable/delete key production để kiểm tra. Dùng test keys và repository cô lập.

## 69. Restore time và bottleneck

RTO có thể bị chi phối bởi:

- Storage provisioning.
- Object download/network throughput.
- Decryption/decompression CPU.
- Backup chain length.
- WAL replay volume.
- Database crash recovery.
- Index/constraint rebuild nếu logical restore.
- DNS, secrets, certificates và application deployment.
- Business validation/cutover.

### Đo thực tế

Ghi timestamps cho từng phase. Nếu RTO mục tiêu 2 giờ nhưng download backup mất 90 phút, tối ưu WAL replay sẽ không giải quyết bottleneck chính.

## 70. Backup retention và restore frequency

Backup được giữ 7 năm nhưng không restore test trong 7 năm có thể không đáng tin cậy do:

- Tool format thay đổi.
- Key version bị retire.
- Certificate/CA hết hạn.
- Cloud account/role bị xóa.
- Archive tier retrieval quá chậm.
- Documentation lỗi thời.
- PostgreSQL major version/platform không còn hỗ trợ.

Retention dài cần cả **operational compatibility plan**: lưu tool/runtime, key lifecycle, catalog, documentation và test restore định kỳ.

## 71. Runbook: backup job thành công nhưng object chưa offsite

1. Kiểm tra backup process exit code và local staging status.
2. Xác định upload job có chạy không.
3. Kiểm tra object count/size và multipart completion.
4. Kiểm tra credentials, network, endpoint và bucket policy.
5. Kiểm tra checksum/manifest sau upload.
6. Kiểm tra encryption metadata và key ID.
7. Chỉ publish backup complete sau verification.
8. Giữ local staging theo thời hạn ngắn đã định.
9. Retry upload theo idempotent object key/tool protocol.
10. Alert nếu offsite RPO bị vượt.

Không xóa local staging chỉ vì process backup đã kết thúc; cần xác nhận offsite artifact đã hoàn chỉnh.

## 72. Runbook: backup tồn tại nhưng không giải mã được

1. Đọc manifest để xác định encryption format và key ID/version.
2. Kiểm tra tool/version và decrypt compatibility.
3. Kiểm tra KMS key state: enabled, scheduled deletion, policy.
4. Xác nhận restore role có quyền unwrap/decrypt.
5. Kiểm tra network/region endpoint tới KMS.
6. Xem audit logs cho AccessDenied/key errors.
7. Xác minh wrapped DEK/nonce/tag metadata không bị hỏng.
8. Dùng key recovery/approval process nếu cần.
9. Test decrypt trên copy cô lập.
10. Không ghi plaintext key vào log/ticket khi khắc phục.

## 73. Runbook: KMS key bị disable hoặc scheduled deletion

1. Xác định key ID/version và backup sets phụ thuộc.
2. Xác định ai/automation đã thay đổi state qua audit logs.
3. Nếu đang trong deletion waiting period, kích hoạt cancel deletion theo approval.
4. Khôi phục policy/permissions cần thiết.
5. Thử decrypt một backup test.
6. Xác nhận restore role và DR region có quyền.
7. Đánh giá key compromise hay accidental action.
8. Rotate/replace key theo incident response nếu cần.
9. Cập nhật inventory/dependency map.
10. Tạo alert và dual control để ngăn lặp lại.

Nếu key đã bị xóa vĩnh viễn, khả năng phục hồi phụ thuộc key backup/escrow hoặc một bản copy được mã hóa bằng key khác. Không giả định ciphertext có thể khôi phục bằng cách tạo key mới cùng tên.

## 74. Runbook: phát hiện backup bị sửa hoặc xóa

1. Dừng lifecycle/destructive automation liên quan.
2. Bảo toàn audit logs và evidence.
3. Xác định objects, versions, manifests và signatures bị ảnh hưởng.
4. Kiểm tra immutable/offline/cross-account copies.
5. Revoke compromised credentials/roles.
6. Kiểm tra KMS policy và decrypt activity.
7. Chọn bản backup đã verify gần nhất.
8. Restore vào isolated environment.
9. Đánh giá data exposure và báo cáo theo incident policy.
10. Khôi phục pipeline bằng identity/key mới sau khi containment.

Không ghi đè forensic evidence bằng một backup mới có cùng object names.

## 75. Runbook: offsite region không truy cập được

1. Xác nhận outage thuộc storage, network, identity hay KMS.
2. Kiểm tra cross-region replica/secondary repository.
3. Kiểm tra key availability và policy ở DR region.
4. Xác nhận backup catalog/manifests có bản sao.
5. Provision restore environment ở region còn hoạt động.
6. Cấp short-lived restore identity.
7. Restore một backup đã verify.
8. Kiểm tra WAL chain/PITR coverage.
9. Thực hiện application validation và cutover theo DR plan.
10. Sau khi region phục hồi, reconcile backup replication gap.

## 76. Runbook: retention xóa nhầm backup cần thiết

1. Dừng lifecycle job hoặc sửa policy gây lỗi.
2. Kiểm tra versioning, soft-delete, immutable copy và cross-account repository.
3. Xác định backup chain/WAL range bị ảnh hưởng.
4. Đánh giá recovery points còn lại và RPO impact.
5. Khôi phục objects nếu provider hỗ trợ undelete/version restore.
6. Verify manifest/checksum/key access.
7. Test restore chain.
8. Cập nhật catalog.
9. Review lifecycle selectors/tags/prefix.
10. Thêm dry-run, approval và alert trước lần xóa tiếp theo.

## 77. Runbook: nghi ngờ ransomware chiếm backup credentials

1. Revoke/disable compromised service identities.
2. Dừng các jobs upload/delete có thể bị attacker kiểm soát.
3. Bảo vệ immutable/offline copies và audit logs.
4. Kiểm tra object deletes/version deletes/retention changes.
5. Kiểm tra KMS decrypt/disable/delete activity.
6. Xác định backup nào được tạo trước thời điểm compromise.
7. Verify signatures/checksums từ trust domain độc lập.
8. Restore vào clean-room environment.
9. Rotate credentials/keys theo incident response plan.
10. Khôi phục pipeline bằng identities mới và kiểm thử.

Không dùng backup mới tạo sau compromise nếu chưa xác minh integrity và nguồn gốc.

## 78. Checklist thiết kế backup security

### Encryption

- Backup, WAL, catalog, manifests và staging có được mã hóa?
- Encryption at rest và in transit đã được xác minh?
- Client-side encryption có cần theo threat model?
- Key IDs/versions được catalog hóa?
- Key rotation/recovery đã thử nghiệm?

### Retention và integrity

- Retention đáp ứng RPO/RTO/compliance?
- WAL dependencies và incremental chains được giữ đủ?
- Có immutable/WORM copies?
- Manifest/checksum/signature được bảo vệ?
- Legal hold và deletion obligations được xử lý?

### Offsite

- Bản sao nằm ngoài host/site/account failure domain?
- Cross-region/cross-account có hoạt động?
- KMS key sẵn sàng ở DR?
- Archive/replication lag có alert?

### Access control

- Backup writer không có delete/admin rights?
- Restore reader được cấp quyền tạm thời?
- Retention và KMS admin tách biệt?
- MFA/dual approval cho destructive operations?
- Audit logs độc lập và immutable?

### Restore

- Restore drill định kỳ?
- PITR chain được xác minh?
- Restore bằng key cũ và role DR đã thử?
- RTO thực tế được đo?
- Runbook và owner còn hiệu lực?

## 79. Ma trận quyền mẫu

| Hành động | Backup writer | Restore operator | Retention admin | Key admin | Auditor |
|---|---:|---:|---:|---:|---:|
| Tạo backup | Có | Không | Không | Không | Không |
| Upload object | Có | Không | Không | Không | Không |
| Read/download | Theo prefix staging nếu cần | Có, tạm thời | Không mặc định | Không | Metadata |
| Decrypt/unwrap key | Encrypt-only nếu hỗ trợ | Có, có approval | Không | Quản lý policy | Audit |
| Delete object/version | Không | Không | Theo policy/approval | Không | Không |
| Change retention/Object Lock | Không | Không | Có, dual control | Không | Read audit |
| Rotate KEK | Không | Không | Không | Có, dual control | Read audit |
| Read audit logs | Không | Không mặc định | Không | Không | Có |

Đây là ma trận tham khảo. Hãy map sang actions cụ thể của provider và kiểm tra quyền kế thừa; một role có quyền cao ở account level có thể vượt mọi giới hạn prefix.

## 80. Các nguyên tắc dễ hiểu nhầm

**“Backup encrypted at rest nghĩa là mọi administrator đều không đọc được.”** Không. SSE có thể trả plaintext cho caller được authorize.

**“TLS là đủ để bảo vệ backup.”** Không. TLS bảo vệ đường truyền; object vẫn cần encryption at rest/client-side theo threat model.

**“Checksum chứng minh backup không bị attacker sửa.”** Không nếu attacker sửa được cả backup và checksum. Cần signature/immutable copy.

**“Backup file còn tồn tại nghĩa là có thể restore.”** Không nếu key, catalog, WAL chain hoặc tool format bị mất.

**“KMS key có thể xóa khi đã rotate.”** Không nếu backup cũ vẫn phụ thuộc key version đó.

**“Cross-region copy tự động có thể decrypt.”** Không. Cần key policy, identity và KMS availability ở DR region.

**“Versioning đồng nghĩa immutable.”** Không. Versions cũ vẫn có thể bị xóa nếu identity có quyền.

**“Offsite bucket trong cùng account đủ chống ransomware.”** Không nếu cùng credentials/admin có thể xóa cả hai.

**“Backup writer cần quyền admin để backup chạy.”** Không. Cấp quyền đúng cho backup method và objects.

**“pg_dump bao gồm mọi cluster globals.”** Không. Roles/tablespaces và cluster-wide metadata cần quy trình riêng.

**“Base backup không cần WAL.”** Physical backup thường cần WAL tương ứng để đảm bảo consistency/recovery và PITR.

**“WAL archive không cần base backup.”** Không. WAL chain cần base backup phù hợp để dựng database.

**“Retention chỉ là số ngày.”** Không. Phải giữ dependency chain, keys, legal holds và restore metadata.

**“Backup job exit code 0 là đủ.”** Không. Cần upload, integrity verification và restore test.

**“Restore vào staging không có rủi ro dữ liệu.”** Không. Backup production vẫn chứa dữ liệu nhạy cảm và application side effects.

**“Hủy key là cách xóa dữ liệu đơn giản.”** Không. Key có thể dùng chung nhiều backups; cryptographic erasure cần thiết kế và phê duyệt.

**“Object Lock bảo vệ trước mọi sự cố.”** Không. Nó không bảo vệ confidentiality, key availability hay tính đúng đắn của backup mới.

**“Immutable backup không cần audit.”** Không. Cần phát hiện ai thay policy, key và restore permissions.

**“Tạo backup thường xuyên nghĩa là RPO tốt.”** Không nếu WAL archive lag hoặc restore chain thiếu.

**“Có backup nghĩa là đạt RTO.”** Không nếu provisioning/decrypt/download/replay/validation mất quá lâu.

## 81. Bài tập thực hành

### Bài 1 — Phân loại backup

Phân biệt pg_dump, pg_basebackup, WAL archive và storage snapshot. Mỗi loại phù hợp cho tình huống restore nào?

### Bài 2 — Threat model

Một object storage administrator có thể đọc object qua API. SSE-KMS có bảo vệ nội dung trước identity này không? Khi nào cần client-side encryption?

### Bài 3 — Encryption at rest

So sánh volume encryption, filesystem encryption, object SSE-KMS và backup-tool encryption. Chọn các lớp cho một backup repository production.

### Bài 4 — Encryption in transit

Giải thích TLS và hostname verification. Vì sao sslmode=verify-full mạnh hơn việc chỉ mã hóa connection mà không xác minh server identity?

### Bài 5 — Client-side encryption

Thiết kế pipeline pg_dump -> authenticated encryption -> object storage. Những metadata nào phải lưu để restore?

### Bài 6 — Envelope encryption

Vẽ luồng DEK/KEK: tạo DEK, encrypt backup, wrap DEK, lưu wrapped DEK, unwrap khi restore. KMS không cần nhận toàn bộ backup bytes vì sao?

### Bài 7 — AEAD

Giải thích confidentiality và integrity/authentication của AES-GCM hoặc ChaCha20-Poly1305. Vì sao nonce reuse nguy hiểm?

### Bài 8 — Checksum và signature

Một attacker có quyền ghi object và manifest. Vì sao SHA-256 checksum đơn thuần không đủ? Thiết kế signed manifest với signing key tách biệt.

### Bài 9 — Key rotation

Một repository có backup 2 năm dùng KEK v1. Thiết kế rotation sang KEK v2 mà vẫn restore được backup cũ.

### Bài 10 — Key deletion

Nếu KEK v1 bị xóa trong khi backup cũ còn retention 5 năm, hậu quả là gì? Thiết kế key inventory/deletion guard.

### Bài 11 — Key recovery

Một region DR không truy cập KMS key của region chính. Hãy nêu các bước chuẩn bị để restore vẫn có thể decrypt trong DR.

### Bài 12 — Secret handling

Đánh giá rủi ro khi passphrase được truyền qua command-line argument, shell history hoặc CI logs. Đề xuất secret manager/short-lived credentials.

### Bài 13 — Retention

Thiết kế retention gồm hourly trong 48 giờ, daily trong 30 ngày, weekly trong 12 tuần và monthly trong 12 tháng. Các dependency nào cần giữ thêm?

### Bài 14 — Full/differential/incremental

So sánh restore chain của full + incremental với full + differential. Tác động tới storage và RTO là gì?

### Bài 15 — WAL retention

Một base backup được giữ 30 ngày và cần PITR trong toàn bộ 30 ngày. Vì sao WAL archive phải được giữ liên tục theo recovery chain?

### Bài 16 — Legal hold

Một backup đã hết retention thường nhưng đang bị legal hold. Thiết kế exception để lifecycle automation không xóa object đó.

### Bài 17 — Immutable/WORM

Phân biệt versioning, governance retention lock và compliance retention lock. Cơ chế nào ngăn administrator xóa object sớm hơn?

### Bài 18 — Offsite

Một backup được lưu ở volume khác cùng host. Vì sao chưa phải offsite? Thiết kế ít nhất hai failure domains độc lập.

### Bài 19 — Cross-account

Thiết kế production backup role chỉ được Put vào prefix ở backup account. Những quyền nào phải bị từ chối?

### Bài 20 — Cross-region

Một region chính bị outage. Hãy liệt kê storage, KMS, identity, network, catalog và WAL dependencies cần có ở DR region.

### Bài 21 — Staging

Một backup tool tạo plaintext file trên local staging rồi upload. Thiết kế permissions, encryption, cleanup và failure recovery.

### Bài 22 — PostgreSQL backup role

Tạo role replication-only cho pg_basebackup. Vì sao không cấp superuser? Nêu các cấu hình pg_hba/TLS cần kiểm tra.

### Bài 23 — Logical dump permissions

Một pg_dump hoàn tất nhưng thiếu rows do RLS. Hãy giải thích rủi ro và thiết kế role/validation để backup đầy đủ theo policy.

### Bài 24 — Separation of duties

Phân chia backup writer, restore reader, retention manager, key admin và auditor. Vì sao không nên giao tất cả quyền cho một service account?

### Bài 25 — Audit

Thiết kế audit events cần ghi cho object upload/download/delete, KMS decrypt, retention changes và restore actions. Log nên được lưu ở đâu?

### Bài 26 — Backup catalog

Một incremental backup còn file nhưng catalog mất. Những metadata/dependencies nào cần để khôi phục chain?

### Bài 27 — Restore verification

Thiết kế quy trình verify checksum, signature, encryption metadata, WAL continuity và PostgreSQL startup. Vì sao từng bước chứng minh một thuộc tính khác nhau?

### Bài 28 — RPO/RTO

Một hệ thống yêu cầu RPO 15 phút, RTO 2 giờ. Đề xuất lịch base backup, WAL archive, offsite replication và restore test.

### Bài 29 — Restore từ logical dump

Tạo pg_dump custom format, verify bằng pg_restore --list rồi restore vào database cô lập. Những roles/globals nào cần chuẩn bị riêng?

### Bài 30 — Restore physical/PITR

Thiết kế quy trình restore base backup và replay WAL đến một recovery_target_time. Cần kiểm tra timeline history và WAL gap ra sao?

### Bài 31 — Snapshot consistency

Phân biệt crash-consistent và application-consistent snapshots. Vì sao snapshot đồng thời nhiều volumes cần orchestration?

### Bài 32 — Compression/encryption

Vì sao thường compress trước rồi encrypt? Đo CPU, storage ratio và restore time cho hai pipeline.

### Bài 33 — Deduplication

Giải thích vì sao encrypt mỗi file bằng DEK ngẫu nhiên có thể giảm dedup efficiency. Nêu rủi ro của convergent encryption.

### Bài 34 — Lifecycle rule

Một rule xóa object sau 30 ngày vô tình xóa parent full backup còn được incremental chain sử dụng. Thiết kế dependency-aware cleanup.

### Bài 35 — Restore staging security

Restore database production vào staging cho developer. Thiết kế network isolation, masking, access approval, outbound restrictions và cleanup.

### Bài 36 — Ransomware

Attacker chiếm production admin credential và xóa backup trong cùng account. Thiết kế cross-account immutable copy, identity isolation và key controls.

### Bài 37 — KMS key disabled

Backup còn nguyên nhưng decrypt thất bại do key disabled. Viết runbook kiểm tra key state, audit, policy, approval và restore test.

### Bài 38 — Archive outage

Archive destination gián đoạn 20 phút trong khi WAL generation cao. Thiết kế alert, disk headroom, retry và kiểm chứng PITR continuity.

### Bài 39 — Retention/privacy

Một khách hàng yêu cầu xóa dữ liệu cá nhân trong khi backup immutable còn 90 ngày. Đề xuất phối hợp data governance, legal hold, restore deletion replay và key-scope analysis.

### Bài 40 — Thiết kế backup security end-to-end

Một công ty vận hành PostgreSQL production:

- 8 TB dữ liệu giao dịch.
- RPO 5 phút, RTO 90 phút.
- Physical base backup hằng ngày, incremental mỗi 6 giờ.
- WAL archive liên tục.
- Hai cloud regions và một backup account riêng.
- Dữ liệu chứa thông tin khách hàng.
- Một team vận hành database, một team security quản lý KMS.
- Cần giữ daily 35 ngày, weekly 6 tháng, annual 7 năm.
- Ransomware/credential compromise nằm trong threat model.

Hãy thiết kế:

1. Encryption at rest/in transit/client-side phù hợp threat model.
2. DEK/KEK strategy, key rotation và recovery ở DR region.
3. Backup/WAL/catalog/manifests retention dependencies.
4. Offsite cross-account/cross-region immutable copies.
5. IAM/PostgreSQL roles theo least privilege và separation of duties.
6. Object Lock/legal hold và lifecycle rules.
7. Audit logging độc lập và alert destructive actions.
8. Restore runbook, PITR và data validation.
9. Restore drills chứng minh RPO/RTO với key versions cũ.
10. Incident response khi backup bị xóa, key bị disable hoặc archive bị gián đoạn.

## Kết luận

**Backup PostgreSQL là một tài sản dữ liệu nhạy cảm và phải được bảo vệ như production data.** Mã hóa at rest/in transit/client-side, integrity checks và key management bảo vệ confidentiality/integrity; nhưng chỉ có ý nghĩa khi khóa vẫn có thể được khôi phục trong thời gian cần thiết. Envelope encryption và KMS giúp quản lý DEK/KEK, còn key rotation phải giữ khả năng giải mã mọi backup vẫn nằm trong retention.

**Retention phải hiểu toàn bộ recovery chain.** Full/incremental/differential backups có dependencies khác nhau; physical base backup cần WAL liên tục cho PITR; manifests, catalogs, timeline history và key versions cũng phải được giữ. Lifecycle automation cần dependency-aware cleanup, legal hold và immutable/WORM controls để chống xóa nhầm hoặc ransomware.

**Offsite backup cần độc lập failure domain và quyền quản trị.** Cross-account, cross-region, immutable storage, service identities ngắn hạn, least privilege và separation of duties giảm khả năng một credential compromise phá cả primary lẫn backup. Storage permission và KMS decrypt permission là hai lớp riêng, cần kiểm tra cả hai trong DR.

Cuối cùng, **restore test mới chứng minh backup dùng được**. Hãy kiểm tra checksum/signature, key access, WAL continuity, PostgreSQL recovery, business data và thời gian restore trong môi trường cô lập. Một backup chỉ hoàn chỉnh khi có thể tìm thấy, đọc, giải mã, khôi phục và xác minh theo RPO/RTO đã cam kết.

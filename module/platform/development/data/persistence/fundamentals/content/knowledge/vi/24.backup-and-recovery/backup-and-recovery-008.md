# Kiểm tra tính toàn vẹn và khả năng đọc của bản sao

Trong chương **Sao lưu và khôi phục** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**, việc có một tệp backup không đồng nghĩa với việc hệ thống Java có thể khôi phục dữ liệu khi gặp sự cố. Một tệp có thể tồn tại nhưng bị cắt cụt; giải nén được nhưng thiếu dữ liệu; chứa dữ liệu đầy đủ nhưng không có WAL để phục hồi tới mốc mong muốn; hoặc khôi phục database thành công mà ứng dụng không đăng nhập, đọc bảng hay kiểm tra được bất biến nghiệp vụ.

Đề bài **kiểm tra tính toàn vẹn và khả năng đọc của bản sao** yêu cầu trả lời nhiều câu hỏi khác nhau: **bản sao có đủ và đúng byte không, có thể giải mã và giải nén không, có thuộc một chuỗi backup nhất quán không, có thể phục hồi thành database chạy được không, và ứng dụng có thực sự đọc được dữ liệu cần thiết không?**

Với Java, kết quả cuối không chỉ là lệnh `RESTORE` trả mã thoát bằng 0. Nó còn là khả năng khôi phục schema, dữ liệu, quyền truy cập và giao thức persistence để ứng dụng tiếp tục hoạt động mà không vi phạm transaction, idempotency, giới hạn bảo mật hay mục tiêu phục hồi đã cam kết.

## 1. Một bản sao “tồn tại” khác một bản sao “phục hồi được”

Giả sử hệ thống PostgreSQL có cron job tạo tệp `shop-2026-11-22.dump` mỗi đêm. Dashboard cho biết “backup completed” và dung lượng tệp là 12 GB. Điều đó **chỉ chứng minh job đã báo hoàn tất và có dữ liệu được lưu**, chưa đủ để kết luận:

- Tất cả byte đã được ghi/truyền đúng, không bị thay đổi sau khi backup.
- Tệp có định dạng và phiên bản công cụ phù hợp với quy trình restore.
- Khóa giải mã và cấu hình nén còn sử dụng được.
- Backup chứa đúng database, schema, bảng, role và dữ liệu nghiệp vụ cần bảo vệ.
- Một bản sao vật lý có WAL, file và chuỗi incremental cần cho recovery.
- Database khôi phục vượt qua kiểm tra cấu trúc, có thể khởi động và phục vụ truy vấn.
- Tài khoản ứng dụng Java có thể kết nối và đọc/ghi đúng các đối tượng cần thiết.
- Thời điểm khôi phục đáp ứng **RPO** và quá trình khôi phục đáp ứng **RTO**.

**Nguyên tắc vận hành:** một backup chỉ nên được xem là **có khả năng phục hồi đã được kiểm chứng** sau khi vượt qua những bài kiểm tra phù hợp với loại backup, hệ quản trị, kiến trúc ứng dụng và mức rủi ro dữ liệu.

## 2. Sáu tầng kiểm tra từ file đến nghiệp vụ

Có thể tổ chức kiểm tra theo một chuỗi ngày càng mạnh:

```text
Backup job tạo artifact
          |
          v
 [1] Hiện diện và metadata
     Đúng nguồn, thời điểm, kích thước, định dạng?
          |
          v
 [2] Toàn vẹn byte
     Checksum/hash/signature/manifest có khớp?
          |
          v
 [3] Khả năng giải mã/giải nén/đọc định dạng
     Có đủ key, codec, phiên bản công cụ?
          |
          v
 [4] Tính đầy đủ của backup set
     Base + incremental + WAL + globals có đủ?
          |
          v
 [5] Phục hồi trong môi trường cô lập
     DB khởi động, cấu trúc/constraint/index hợp lệ?
          |
          v
 [6] Kiểm chứng ứng dụng và nghiệp vụ
     Java kết nối, đọc/ghi thử đúng, đối soát dữ liệu?
          |
          v
  Ghi bằng chứng, RPO/RTO, quyết định sẵn sàng
```

| Tầng | Ví dụ phép thử | Chứng minh được | Không chứng minh được |
| --- | --- | --- | --- |
| 1. Metadata | Kiểm tra tên, kích thước, lịch và mã backup job. | Artifact được tạo và tìm thấy. | Dữ liệu bên trong có đúng. |
| 2. Toàn vẹn byte | SHA-256, manifest, đối chiếu checksum nguồn–đích. | Byte chưa thay đổi so với bản tham chiếu tin cậy. | Nội dung ban đầu có hợp lệ hay đầy đủ. |
| 3. Định dạng | Test giải mã, giải nén, mở archive. | Công cụ có thể đọc cấu trúc/container. | Mọi bảng đều phục hồi và ứng dụng chạy được. |
| 4. Tập backup | Xác nhận base/incremental/WAL liên tục. | Có các thành phần cần theo kế hoạch recovery. | Toàn bộ quá trình replay sẽ thành công. |
| 5. Restore | Dựng instance cô lập, replay và kiểm tra cấu trúc. | Có thể đưa dữ liệu trở lại DBMS hoạt động. | Hợp đồng nghiệp vụ và client Java đã đúng. |
| 6. Nghiệp vụ | JDBC smoke test, invariants, so sánh mốc. | Các chức năng quan trọng làm việc với dữ liệu phục hồi. | Không còn lỗi ẩn ở mọi bảng và mọi tình huống. |

Không nên dùng một kiểm tra tầng 2 để tuyên bố đã hoàn tất tầng 5 hoặc 6. **Checksum tốt là điều kiện có ích, nhưng không phải bài kiểm thử phục hồi.**

## 3. Hiểu rõ loại backup trước khi chọn cách kiểm tra

Một tổ chức có thể dùng nhiều dạng backup:

| Loại | Nội dung điển hình | Ưu điểm | Kiểm tra cần chú ý |
| --- | --- | --- | --- |
| **Logical dump** | SQL hoặc archive chứa định nghĩa và dữ liệu object. | Linh hoạt khôi phục đối tượng, di chuyển/đối chiếu schema. | Khả năng đọc archive, restore schema/data, role/extension và semantics. |
| **Physical/base backup** | Bản sao các file của cluster/database theo cơ chế DBMS. | Phục hồi nguyên cluster, thường phù hợp dữ liệu lớn. | Manifest, dữ liệu file, WAL, phiên bản/kiến trúc và thử khởi động. |
| **Incremental/differential backup** | Chỉ phần dữ liệu thay đổi theo một điểm cơ sở. | Tiết kiệm dung lượng và thời gian lấy bản sao. | Đầy đủ chuỗi base → incremental, thứ tự và khả năng hợp nhất. |
| **Continuous WAL/redo archive** | Các bản ghi log để replay sau base backup. | Point-in-time recovery (PITR), RPO nhỏ hơn chỉ backup định kỳ. | Liên tục segment/timeline, có thể giải mã và replay tới target. |
| **Volume/snapshot** | Ảnh chụp block/volume ở một thời điểm. | Tạo nhanh ở hạ tầng hỗ trợ. | Cơ chế snapshot nhất quán với DB/WAL, đủ volume, khả năng attach/boot. |
| **Backup từ dịch vụ managed DB** | Snapshot/PITR theo hợp đồng provider. | Dịch vụ quản lý nhiều bước hạ tầng. | Kiểm tra được thời điểm phục hồi, thao tác restore thật, giới hạn tài khoản/quota. |

Ví dụ cụ thể:

- `pg_dump` thường tạo **logical backup** của một database; bản dump theo database không tự chứa mọi role/tablespace và cấu hình cấp cluster.
- `pg_basebackup` tạo **physical base backup** của PostgreSQL cluster; quy trình recovery phụ thuộc định dạng, manifest, WAL và tính tương thích.
- Snapshot của filesystem/volume **không mặc nhiên an toàn** nếu sao chụp các phần dữ liệu và WAL không nhất quán hoặc thiếu phối hợp theo yêu cầu của DBMS.

**Không áp dụng nguyên xi cách kiểm tra một `.dump` cho một thư mục physical backup.** Mỗi loại có cấu trúc và công cụ xác minh riêng.

## 4. Xác định “đúng bản sao” bằng metadata có thể truy vết

Trước checksum, cần xác nhận artifact có nguồn gốc đúng. Tối thiểu nên lưu:

- **Backup ID** ổn định và loại backup (logical/physical/incremental).
- Danh tính hệ thống nguồn, database/cluster và môi trường, tránh lẫn production với staging.
- Mốc bắt đầu/kết thúc backup, độ mới dữ liệu có thể phục hồi và timezone.
- Version PostgreSQL/DBMS, phiên bản công cụ backup, định dạng/nén/mã hóa.
- Danh sách artifact, object-store bucket/path, kích thước và checksum/manifest.
- ID khóa mã hóa/KMS (không lưu secret thô), chủ thể tạo backup và chính sách retention.
- Với physical/PITR: base backup, phụ thuộc incremental, WAL range, timeline và mốc recovery.
- Kết quả từng phép kiểm tra, phiên bản công cụ kiểm tra và ngày thử restore gần nhất.

Ví dụ bản ghi metadata **minh họa**, không phải định dạng chuẩn bắt buộc:

```yaml
backup_id: shopdb-full-20261122-0100
source_environment: production
source_database: shopdb
backup_type: logical_custom
created_at_utc: "2026-11-22T01:00:00Z"
database_major_version: 17
archive_name: shopdb-full-20261122-0100.dump
archive_size_bytes: 12500000000
checksum_algorithm: sha256
sha256: "<trusted-digest-recorded-separately>"
encryption_key_reference: "kms-key-alias-or-id"
retention_class: daily
verification_status: pending_restore
```

Giá trị trong ví dụ chỉ để minh họa cấu trúc, **không phải kết quả backup đã thực hiện**. Metadata phải được lưu ở vị trí có kiểm soát phiên bản/quyền sửa phù hợp. Nếu người tấn công có thể sửa cả tệp backup lẫn checksum đặt cạnh nó, so khớp hash **không bảo vệ được trước việc giả mạo có chủ ý**.

## 5. Checksum, hash và chữ ký: xác minh đúng điều gì?

Một checksum/hash như SHA-256 là hàm tạo dấu vân tay byte cho một artifact. Khi kiểm tra lại, nếu digest khác giá trị tham chiếu tin cậy, file có thể bị hỏng, cắt ngắn hoặc thay đổi.

```text
Sau backup:
  artifact bytes ----> SHA-256 ----> digest gốc được lưu an toàn

Sau truyền/lưu trữ:
  artifact bytes ----> SHA-256 ----> digest mới
                                  |
                         so sánh bằng nhau?
                         /            \
                       Có             Không
                       |               |
          byte giống bản tham chiếu     dừng / điều tra
```

Với máy Linux có thể dùng:

```bash
# Thực hiện ở vị trí có quyền đọc backup và được phép kiểm tra.
sha256sum /backups/shopdb-full.dump

# Nếu manifest SHA-256 được lấy từ nguồn tin cậy:
sha256sum --check /backups/shopdb-full.sha256
```

Trên Windows PowerShell:

```powershell
Get-FileHash -LiteralPath 'D:\Backups\shopdb-full.dump' -Algorithm SHA256
```

**Phạm vi bảo đảm:**

1. Hash so sánh **byte của file**, không xác nhận file chứa đủ bảng hoặc là snapshot transaction nhất quán.
2. File có thể đã sai ngay lúc tạo; checksum được tạo từ file sai vẫn sẽ “khớp”.
3. Hash không chứng minh tính bí mật. File backup chứa dữ liệu nhạy cảm vẫn cần mã hóa và hạn chế truy cập.
4. Để chống sửa đổi ác ý, cần một **nguồn manifest/digest có tính xác thực**, ví dụ chữ ký số hoặc metadata được bảo vệ bằng quyền/immutability độc lập.
5. Khi backup gồm nhiều file, cần manifest của **toàn bộ tập file** và quan hệ phụ thuộc, không chỉ hash một file lớn.

Nếu file được mã hóa, cần quy định checksum tính trên **ciphertext** hay **plaintext**. Hash ciphertext giúp xác minh bản truyền/lưu trữ; kiểm tra giải mã và hash plaintext giúp kiểm tra thêm khả năng truy xuất nội dung sau giải mã. Không bắt buộc lưu plaintext để thực hiện kiểm tra.

## 6. Nén và mã hóa: bản sao còn giải nén, giải mã được không?

Một artifact có thể giữ nguyên byte nhưng **không sử dụng được** vì:

- Không còn quyền truy cập khóa KMS hoặc password giải mã.
- Key đã bị xóa/rotate không đúng quy trình hoặc thiếu thông tin version.
- Công cụ/codec nén không tương thích môi trường khôi phục.
- Một tầng mã hóa/phân mảnh của provider không được cấu hình trong môi trường DR.
- Tệp chứa dữ liệu được nén đúng container nhưng một member bên trong bị lỗi.

Với file gzip thuần, có thể dùng:

```bash
# Chỉ có ý nghĩa với file gzip, không áp dụng cho mọi loại .dump.
gzip -t /backups/shopdb.sql.gz
```

Lệnh `gzip -t` giúp phát hiện nhiều lỗi hỏng stream nén/CRC; nó **không xác minh SQL trong đó có thể chạy lại hay có đủ dữ liệu nghiệp vụ**.

Với backup được mã hóa, bài kiểm tra nên:

1. Dùng đúng **identity khôi phục** và quyền giải mã thực tế, không chỉ quyền của người đã tạo backup.
2. Xác nhận key/credential còn có thể truy xuất và các ràng buộc vùng/account của KMS đáp ứng kịch bản DR.
3. Giải mã thử trong môi trường cô lập, qua luồng có kiểm soát để tránh ghi plaintext ra thư mục chia sẻ.
4. Đọc/giải nén định dạng thành công, sau đó tiếp tục kiểm tra sâu hơn.
5. Ghi bằng chứng **đã giải mã được**, không ghi password, key material hoặc dữ liệu khách hàng vào log.

**Không nên cho việc thử restore phụ thuộc vào credential chỉ một người sở hữu hoặc một KMS nằm đúng ở vùng hạ tầng đang giả định sẽ bị mất.**

## 7. PostgreSQL logical backup: `pg_dump` và `pg_restore`

Một ví dụ tạo logical backup dưới dạng custom archive:

```bash
# Chạy bằng role backup chuyên dụng có quyền đọc phù hợp.
# Kết nối/secret được cấp qua cơ chế triển khai; không nhúng password.
pg_dump --host=db-primary \
        --username=backup_reader \
        --dbname=shopdb \
        --format=custom \
        --file=/backups/shopdb-full.dump
```

`pg_dump` tạo snapshot nhất quán theo cơ chế của nó trong khi database có thể đang có giao dịch khác. Nhưng kết quả backup **phụ thuộc phạm vi dump, quyền đọc, tùy chọn exclude, định dạng và khả năng đọc các object liên quan**.

### Kiểm tra cấu trúc archive mà chưa khôi phục

Với custom archive hoặc định dạng mà `pg_restore` hỗ trợ:

```bash
pg_restore --list /backups/shopdb-full.dump
```

Danh sách này giúp xác nhận archive có thể nhận diện và xem **table of contents (TOC)**: schema, table, data section, sequence và các object được lưu tùy định dạng. Đây là **kiểm tra ban đầu**, không chứng minh toàn bộ payload được đọc hết hoặc thực thi thành công trên database đích.

Đừng lẫn hai loại artifact:

- `pg_dump --format=custom` → dùng `pg_restore` để liệt kê và phục hồi.
- `pg_dump --format=plain` → tệp SQL thuần thường chạy bằng `psql`; `pg_restore --list` không phải công cụ phù hợp cho tệp này.

### Khôi phục thử logical dump vào database cô lập

Trong **môi trường thử nghiệm**, với database trống đã provision bằng quyền phù hợp:

```bash
# Môi trường cô lập: không trỏ tới production.
createdb --host=restore-lab --username=restore_operator shopdb_restore

pg_restore --host=restore-lab \
           --username=restore_operator \
           --dbname=shopdb_restore \
           --exit-on-error \
           --no-owner \
           --no-acl \
           /backups/shopdb-full.dump
```

Chọn `--no-owner` và `--no-acl` ở đây **chỉ để minh họa phục hồi dữ liệu/đối tượng trong lab** khi role nguồn không có ở lab. Chúng **không phục hồi đầy đủ mô hình quyền production**. Nếu mục tiêu là kiểm chứng DR end-to-end, cần **tái tạo roles/privileges và thử bằng danh tính runtime thật**, không được coi restore bỏ qua ACL là đủ.

Với cluster có global objects như roles/tablespaces hoặc phụ thuộc extension, cần có quy trình lưu/khôi phục **riêng những thành phần không nằm trong logical dump một database**. Một số trường hợp dùng `pg_dumpall --globals-only` trong thiết kế backup, nhưng nó cũng cần quyền/phân loại dữ liệu nhạy cảm và kiểm tra phù hợp. Không thực thi script globals vào hệ thống đang hoạt động nếu chưa review tác động.

**Điều cần đánh dấu:** `pg_restore --list` thành công khác xa `pg_restore --exit-on-error` thành công, và cả hai vẫn khác việc Java thực hiện được nghiệp vụ sau restore.

## 8. PostgreSQL physical backup: manifest và `pg_verifybackup`

Với physical backup, PostgreSQL cung cấp cơ chế manifest để kiểm tra các file được backup. Một ví dụ với định dạng plain:

```bash
# Chạy trên máy/volume dành cho backup, với quyền replication phù hợp.
# Không dùng lại thư mục dữ liệu production.
pg_basebackup --host=db-primary \
              --username=backup_operator \
              --pgdata=/backups/base-001 \
              --format=plain \
              --wal-method=stream \
              --progress

# Kiểm tra bằng công cụ phù hợp phiên bản PostgreSQL.
pg_verifybackup /backups/base-001
```

Khi manifest có mặt và phù hợp, `pg_verifybackup` kiểm tra sự nhất quán của tập file được ghi trong manifest và các checksum theo manifest; nó còn kiểm tra phần WAL cần thiết trong giới hạn khả năng của công cụ và cấu hình. Kết quả phụ thuộc phiên bản PostgreSQL, bản backup, WAL hiện diện và cách sử dụng tùy chọn. Phải đọc tài liệu của đúng phiên bản đang triển khai trước khi diễn giải mã thoát.

**Các giới hạn rất quan trọng:**

- Không phải mọi file trong một cluster đều được kiểm tra như file thông thường; có những file/thư mục được loại trừ theo quy tắc của công cụ.
- Verification của manifest **không thay thế quá trình khởi động và crash recovery thật**.
- Nếu backup được lấy bằng công cụ khác hoặc manifest bị thiếu, không tự coi việc chạy một lệnh chung là đã kiểm tra thành công.
- Việc có WAL đủ để hoàn tất base backup **khác** với việc có toàn bộ WAL archive để PITR tới một mốc bất kỳ nhiều giờ sau đó.
- Nếu PostgreSQL dùng WAL archive nằm ngoài thư mục backup, phải xác minh chuỗi WAL và thử replay qua đúng cơ chế phục hồi đó; chỉ kiểm tra base directory là chưa đủ.

**Bản sao vật lý còn phải tương thích với môi trường phục hồi**: phiên bản PostgreSQL, kiến trúc/tệp dữ liệu, extension, cấu hình và cách cung cấp WAL. Không đặt physical backup trực tiếp vào data directory đang chạy để “thử mở”.

## 9. Page checksum khác backup checksum và manifest

Trong PostgreSQL có thể gặp ít nhất ba kiểu phát hiện hỏng dữ liệu:

| Kiểu | Phạm vi | Giúp phát hiện | Không đảm bảo |
| --- | --- | --- | --- |
| **Backup file hash** | Byte của tệp backup/object. | Tệp khác với digest tham chiếu. | Nội dung DB bên trong có hợp lệ. |
| **Backup manifest/verification** | Tập file được backup và checksum theo manifest. | File thiếu, thay đổi hoặc một số vấn đề liên quan backup set/WAL. | Restore/PITR và nghiệp vụ luôn thành công. |
| **Database page checksum** | Những trang dữ liệu được engine kiểm tra theo cấu hình. | Một số dạng hỏng dữ liệu trang khi được đọc/kiểm tra. | Mọi object, log, file, ứng dụng và backup đều hoàn hảo. |

PostgreSQL page checksum cần được bật/cấu hình phù hợp trong cluster; không thể suy ra rằng mọi hệ thống đều có. Một hệ thống không có page checksum vẫn có thể có manifest hash của backup, nhưng các phạm vi phát hiện lỗi **khác nhau**.

Sau restore, có thể cân nhắc công cụ kiểm tra cấu trúc bảng/index như các tiện ích của PostgreSQL tương thích phiên bản, hoặc các kiểm tra logic đọc dữ liệu. Chúng bổ sung lẫn nhau nhưng **không thay cho kiểm thử use case**.

Không xem “không có lỗi checksum” là bằng chứng rằng một `UPDATE` lỗi nghiệp vụ chưa từng làm sai số dư: checksum phát hiện lỗi byte/cấu trúc ở phạm vi nhất định, không biết điều kiện nghiệp vụ “tổng tiền của sổ cái phải cân”.

## 10. WAL và tính đầy đủ của chuỗi phục hồi tới một thời điểm

Một yêu cầu khôi phục thường không phải “lấy database từ đêm qua”, mà là **“khôi phục tới trước khi thao tác nhầm xảy ra lúc 14:07”**. Với PITR, cần có:

1. Base backup hợp lệ trước thời điểm mục tiêu.
2. WAL cần thiết để làm nhất quán base backup và replay tới target.
3. Một chuỗi WAL **liên tục, đúng timeline** theo quy trình recovery.
4. Cấu hình restore command/nguồn WAL, quyền giải mã và công cụ tương thích.
5. Định nghĩa target theo timestamp, transaction ID, LSN hoặc recovery target hỗ trợ, có kiểm tra thời điểm thực tế sau restore.

```text
Base backup (t0)
      |
      v
WAL segment A ----> segment B ----> segment C ----> segment D
      |                 |                |              |
      +-----------------+----------------+--------------+
                        chuỗi cần replay
                                      |
                          Target t3 ở giữa segment C
```

Nếu thiếu segment B, có base backup sạch và segment C/D vẫn **không đủ** để replay liên tục tới t3. Với backup incremental, còn cần đầy đủ các bản incremental trước khi có một base có thể phục hồi.

### Kiểm tra WAL không chỉ bằng tên file

Đối soát nên xem:

- Backup bắt đầu/kết thúc tại đâu và WAL range bắt buộc là gì.
- Tất cả segment/timeline history cần thiết có sẵn, checksum/metadata đúng.
- Archive command không báo thành công giả khi bản sao chưa được lưu bền vững.
- Quyền đọc, giải mã và tốc độ lấy WAL trong môi trường DR.
- WAL retention không xóa một phần chuỗi mà một base backup còn phụ thuộc.
- Việc failover có tạo timeline mới hay không và quy trình chọn target đúng nhánh.

Để **xác nhận cuối cùng**, hãy phục hồi thật vào môi trường cô lập rồi kiểm tra timeline và target đạt được. Việc có tên file theo thứ tự không chứng minh mọi bản ghi WAL đều đọc và áp dụng được.

## 11. Kiểm thử PITR: phục hồi đúng mốc, không chỉ khởi động được

Một quy trình drill PITR có thể:

1. Chọn một bản base backup đã xác minh và mốc mục tiêu nằm trong khoảng WAL archive hiện có.
2. Dựng máy/cluster phục hồi riêng, cấu hình recovery an toàn.
3. Khai báo target theo cơ chế PostgreSQL phiên bản đang dùng.
4. Để DBMS replay WAL tới target, không gửi request ghi từ ứng dụng production vào cluster này.
5. Kiểm tra trạng thái recovery và thời điểm/mốc thực tế đã đạt.
6. Truy vấn những dữ liệu hoặc marker dự kiến **có trước** và **không có sau** target.
7. Lưu lại bằng chứng, thời gian phục hồi và lỗi gặp phải.

Ví dụ giả định:

```text
13:55:00  Order #A commit
14:02:00  Payment #B commit
14:07:30  Job lỗi vô tình xóa hàng
14:10:00  Phát hiện và cô lập lỗi

Target PITR: trước thao tác xóa 14:07:30,
với giải thích rõ timezone và mốc transaction/LSN nếu cần.

Kiểm tra sau restore:
  Order #A tồn tại
  Payment #B tồn tại
  Dữ liệu trước thao tác xóa được bảo toàn
  Thay đổi commit sau target không xuất hiện theo hợp đồng PITR
```

**Thời điểm theo đồng hồ không luôn đủ để phân biệt những transaction sát nhau.** Khi cần khôi phục cực chính xác, phải xác định transaction boundary/LSN hoặc mốc hỗ trợ đáng tin cậy, hiểu xử lý commit và thứ tự WAL của DBMS.

Không đặt target là “trước 14:07” chỉ vì log ứng dụng có timestamp đó: đồng hồ service có thể lệch, log được ghi trước/sau commit, event có thể đến trễ và một số transaction vẫn đang xử lý.

## 12. Restore cô lập: yêu cầu an toàn tối thiểu

**Restore drill không được gây tác dụng lên production.** Một bản backup production có thể chứa:

- Credential/service endpoint cũ.
- Outbox event chưa phát, job định kỳ đang chờ.
- Webhook subscription và cấu hình gửi email/SMS.
- Dữ liệu cá nhân, thông tin thanh toán và token truy cập.
- Account/cấu hình cho các integration có thể gọi API ngoài.

Vì vậy môi trường thử restore cần:

| Kiểm soát | Mục tiêu |
| --- | --- |
| **Mạng cô lập/egress deny** | Không tự gửi mail, thu tiền, gọi webhook hay cập nhật hệ ngoài. |
| **Tên cluster và DNS riêng** | Không lẫn JDBC URL của production với restore lab. |
| **Credential khôi phục riêng** | Không đặt password production trong file/thư mục thử. |
| **Quyền truy cập tối thiểu** | Chỉ nhóm drill có quyền xem dữ liệu thật; có audit. |
| **Không bật consumer/scheduler tự động** | Tránh phát lại outbox và job từ snapshot. |
| **Không xuất bản endpoint public** | Tránh dữ liệu backup lộ qua ứng dụng thử. |
| **Kế hoạch hủy môi trường** | Xóa dữ liệu tạm và khóa theo chính sách bảo mật. |

Trình tự nên là **cô lập mạng và quyền trước → restore → kiểm tra dữ liệu → chỉ bật ứng dụng đã vô hiệu hóa side effects**. Việc “sau khi restore sẽ nhớ tắt scheduler” thường là quá muộn: scheduler có thể bắt đầu chạy ngay khi process khởi động.

Với dữ liệu nhạy cảm, xét che/mask dữ liệu trong một bản sao dành cho phát triển, nhưng **drill phục hồi disaster recovery cần xác minh được cơ chế phục hồi bản gốc**. Masking không được che khuất lỗi do schema, constraint hoặc kiểu dữ liệu thật.

## 13. Đọc được database: kiểm tra cấu trúc và hệ thống

Sau restore, việc server trả “ready” là cần nhưng không đủ. Nên kiểm tra:

1. Database mở kết nối và phục vụ lệnh SQL theo phiên bản đã dự kiến.
2. Schema, bảng, view, sequence, function, extension và cấu trúc quan trọng có mặt.
3. Chỉ mục, constraint, khóa ngoại và cấu hình collations đáp ứng điều kiện sử dụng.
4. Các role/quyền có thể được phục hồi/áp dụng đúng theo runbook.
5. Kích thước/schema không lệch bất thường so với metadata của backup.
6. Câu truy vấn đại diện đọc được các bảng lớn hoặc bảng đã từng xảy ra lỗi.
7. Nếu có mã hóa ở tầng dữ liệu/ứng dụng, các giá trị quan trọng có thể giải mã với khóa đúng.
8. Các dependency của ứng dụng (extension, custom type, stored procedure) hoạt động sau khi khôi phục.

Ví dụ kiểm tra chỉ đọc trên PostgreSQL **đã restore trong lab**:

```sql
SELECT current_database(), current_user, version();

SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'shop'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;

SELECT extname, extversion
FROM pg_extension
ORDER BY extname;

SELECT COUNT(*) AS orders_restored
FROM shop.orders;
```

`COUNT(*)` là kiểm tra dữ liệu **có thể đọc**, không tự chứng minh từng hàng đúng. Với bảng rất lớn, COUNT toàn bảng có thể tốn I/O/CPU; lên lịch theo ngân sách tài nguyên của drill và bổ sung truy vấn mẫu/kiểm tra cấu trúc, không biến bài test thành nguyên nhân làm hệ thống lab quá tải.

### “Đọc được” phải được hiểu theo góc nhìn của ứng dụng

DBA đăng nhập bằng superuser và đọc bảng thành công chưa chứng minh tài khoản runtime Java đọc được. Nên kiểm tra lại bằng **role và cấu hình ứng dụng tương ứng**, bao gồm:

- `SELECT`/`INSERT`/`UPDATE` cần thiết theo principle of least privilege.
- Search path, RLS và tenant context trong connection pool.
- JDBC driver, kiểu dữ liệu, timezone và character encoding.
- Khả năng ánh xạ object sang entity/DTO của JPA hoặc repository.
- Các constraint mà use case phụ thuộc.

## 14. JDBC smoke test cho dữ liệu phục hồi

Một smoke test Java có thể mở kết nối **chỉ đọc** tới restore lab và lấy những giá trị đại diện. Ví dụ:

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;

public final class RestoreReadSmokeTest {
    public record OrderSnapshot(
            UUID id, String status, long totalCents
    ) {}

    public static OrderSnapshot readOrder(
            String jdbcUrl,
            String username,
            String password,
            UUID expectedOrderId
    ) throws SQLException {
        // Chỉ sử dụng URL trỏ tới restore lab đã cô lập.
        try (Connection connection = DriverManager.getConnection(
                jdbcUrl, username, password)) {
            connection.setReadOnly(true);
            String sql = """
                SELECT id, status, total_cents
                  FROM shop.orders
                 WHERE id = ?
                """;
            try (PreparedStatement statement =
                    connection.prepareStatement(sql)) {
                statement.setObject(1, expectedOrderId);
                try (ResultSet rs = statement.executeQuery()) {
                    if (!rs.next()) {
                        throw new IllegalStateException(
                                "Expected order not present in restore");
                    }
                    return new OrderSnapshot(
                            (UUID) rs.getObject("id"),
                            rs.getString("status"),
                            rs.getLong("total_cents")
                    );
                }
            }
        }
    }
}
```

Đây là **ví dụ minh họa** dùng JDBC tiêu chuẩn với PostgreSQL UUID, không phải một công cụ tự chạy hoàn chỉnh. URL, credentials và ID test cần lấy từ cấu hình drill an toàn; không hard-code password hoặc dùng ID của khách thật trong log công khai.

Điều test xác nhận được:

- Driver kết nối được tới database phục hồi.
- Danh tính runtime đọc được bảng và cột cần thiết.
- Một hàng được kỳ vọng tồn tại và mapping kiểu dữ liệu hoạt động.

Điều chưa xác nhận: mọi hàng đều đúng, chức năng ghi chạy được, transaction mới có thể commit, RLS cho các tenant khác đúng, hoặc dữ liệu phù hợp toàn bộ bất biến. Cần mở rộng bằng integration test có dữ liệu fixture/mốc đối soát và thao tác ghi **chỉ trong lab đã cô lập**.

## 15. Đối soát dữ liệu nghiệp vụ sau restore

Một bản backup có thể hợp lệ về byte và khởi động được nhưng chứa dữ liệu **sai ngay trước thời điểm backup**. Kiểm tra nghiệp vụ nên dựa vào bất biến và dấu mốc được định nghĩa trước.

Ví dụ hệ thống bán hàng:

| Bất biến hoặc bằng chứng | Cách kiểm tra | Điều kiện |
| --- | --- | --- |
| Tồn kho không âm | Truy vấn số hàng `available < 0`. | Biết rõ schema và quy tắc giữ hàng. |
| Mỗi request ID chỉ có một kết quả cuối | Kiểm tra ràng buộc unique và các kết quả bị trùng logic. | Có định danh nghiệp vụ ổn định. |
| Tổng nợ/có khớp sổ cái | Aggregate trên ledger tại mốc nhất quán. | Không dùng số dư materialized thiếu bối cảnh. |
| Trạng thái đơn hợp lệ | So sánh với state machine và sự kiện cuối. | Định nghĩa chuyển trạng thái đã được version hóa. |
| Quan hệ tham chiếu | Kiểm tra khóa ngoại, hàng mồ côi có chủ đích. | Có đầy đủ dữ liệu liên quan trong phạm vi backup. |
| Mốc trước/sau PITR | So marker/order có commit trước và sau target. | Mốc thời gian/timeline được xác định đúng. |
| Số hàng/aggregate theo tập | So với snapshot/đối soát tin cậy cùng thời điểm. | Không so nhầm với production đã ghi tiếp nhiều giờ. |

Ví dụ SQL kiểm tra dữ liệu đã khôi phục:

```sql
-- Chỉ là ví dụ bảng; thay theo schema thật của ứng dụng.
SELECT COUNT(*) AS negative_inventory_rows
FROM shop.inventory
WHERE available < 0;

SELECT COUNT(*) AS invalid_order_states
FROM shop.orders
WHERE status NOT IN ('DRAFT', 'SUBMITTED', 'CANCELLED');

-- Kiểm tra dữ liệu theo một tập test marker được quản lý riêng.
SELECT id, status, total_cents
FROM shop.orders
WHERE id IN (:known_order_ids);
```

Với bảng có `CHECK`, một số truy vấn có thể không phát hiện lỗi mới vì constraint đã cưỡng chế dữ liệu được ghi hợp lệ; điều đó vẫn hữu ích để xác nhận dữ liệu khôi phục đọc được. Với dữ liệu bị nạp từ nguồn cũ, constraint từng bị vô hiệu hóa hoặc logic nghiệp vụ có nhiều bảng, cần kiểm tra sâu hơn.

**Không so số hàng trong backup từ 01:00 với production lúc 09:00 rồi coi chênh lệch là hỏng dữ liệu.** Production có thể tiếp tục nhận hàng triệu giao dịch. Cần so với checkpoint/snapshot/marker phù hợp **cùng mốc nhất quán**.

## 16. Độ đúng của nội dung khác độ đúng của phạm vi backup

Một lần restore thành công có thể không chứa một số thứ ứng dụng cần:

- Một database khác trong cùng hệ thống.
- Role và quyền cluster, tablespace, extension hoặc cấu hình server.
- Blob hoặc file đính kèm nằm trong object storage, không ở PostgreSQL.
- Schema của service phụ trợ, event log, idempotency records hoặc outbox.
- Secret/KMS key cần giải mã dữ liệu cấp ứng dụng.
- Các bản ghi trong external SaaS/payment provider không thuộc backup DB.

Ví dụ Order DB backup đầy đủ nhưng ảnh hóa đơn lưu ở object storage đã bị xóa và không có backup riêng. Kiểm tra bảng `orders` đọc được **không khôi phục được file hóa đơn**.

Một **recovery inventory** nên mô tả:

```text
Business capability: Tra cứu đơn hàng
   |
   +-- Order DB snapshot / WAL
   +-- Roles, schema, extensions
   +-- Object storage chứa chứng từ
   +-- KMS/decryption key
   +-- Configuration và secrets cho runtime
   +-- Version ứng dụng/JDBC driver tương thích
   +-- Các event/integration cần đối soát sau sự cố
```

**Backup của một database** và **khả năng phục hồi một năng lực nghiệp vụ** có phạm vi khác nhau. Nếu một quy trình cần nhiều kho dữ liệu, cần định nghĩa **điểm nhất quán liên hệ thống** và cách đối soát sau khi chúng được restore về các mốc không hoàn toàn trùng nhau.

## 17. RPO, RTO và bằng chứng thay vì ước lượng

Hai chỉ số thường gặp:

- **RPO (Recovery Point Objective):** mức mất dữ liệu theo thời gian mà nghiệp vụ có thể chấp nhận. Ví dụ “tối đa 15 phút dữ liệu được xác nhận mất do sự cố trong phạm vi thiết kế”.
- **RTO (Recovery Time Objective):** thời gian cho phép để khôi phục khả năng phục vụ theo phạm vi và trạng thái mục tiêu đã định.

Ví dụ một bản full mỗi ngày và không lưu WAL liên tục: dù file backup kiểm tra checksum tốt, RPO tiềm năng có thể gần cả ngày. Ngược lại, một cơ chế archive WAL liên tục có thể giảm khoảng mất dữ liệu nhưng **không bảo đảm thực tế RPO** nếu archive backlog hoặc mất segment.

### Tính trên tình huống giả định

Giả sử sự cố xảy ra lúc 15:00. Mốc commit cuối có thể khôi phục được là 14:54, và ứng dụng phục hồi đầy đủ lúc 15:55:

```text
RPO quan sát = 15:00 - 14:54 = 6 phút
RTO quan sát = 15:55 - 15:00 = 55 phút
```

Hai con số này **chỉ mang ý nghĩa khi đã xác minh mốc khôi phục thực tế**. Nếu WAL có tới 14:58 nhưng restore không thể replay vì thiếu một segment trước đó, không được báo RPO = 2 phút chỉ dựa vào tên file cuối cùng.

RTO cần tính cả nhận diện sự cố, quyết định kích hoạt DR, lấy backup/khóa, provision máy, truyền dữ liệu, replay WAL, xác minh, chuyển lưu lượng và kiểm tra ứng dụng. Chỉ đo thời gian `pg_restore` là **thấp hơn thời gian phục hồi end-to-end**.

### Phân rã RTO để tìm điểm cải thiện

```text
Phát hiện & kích hoạt DR    8 phút
Provision + lấy artifact  12 phút
Restore/replay             20 phút
Kiểm tra nghiệp vụ         10 phút
Chuyển traffic              5 phút
-------------------------------
Tổng minh họa              55 phút
```

Trong thực tế một số bước có thể chạy song song, phụ thuộc vào công cụ và chính sách. Hãy dùng **thời gian đo được ở drill** thay vì cộng các ước lượng thiếu bằng chứng.

## 18. Tự động hóa kiểm tra nhưng không tự động tuyên bố “an toàn”

Một pipeline kiểm tra có thể được chia thành các job độc lập:

```text
Backup completed
      |
      +--> A. Inventory artifacts / metadata
      |
      +--> B. SHA/manifest verification
      |
      +--> C. Decryption / decompression / format check
      |
      +--> D. Base + incremental + WAL chain check
      |
      v
Queue restore drill
      |
      +--> E. Restore isolated DB
      +--> F. Structural checks + sample SQL
      +--> G. Java smoke + business invariants
      +--> H. Measure RPO/RTO, retain evidence
      |
      v
Backup recoverability verdict
```

Mỗi bước phải trả kết quả rõ:

| Trạng thái | Ý nghĩa |
| --- | --- |
| `PENDING` | Chưa thực hiện bước kiểm tra. |
| `PASS` | Hoàn thành điều kiện được định nghĩa cho bước đó. |
| `FAIL` | Có bằng chứng không đạt: checksum mismatch, thiếu WAL, restore lỗi... |
| `INCONCLUSIVE` | Không thể kết luận: môi trường lab lỗi, key tạm không truy xuất, thiếu dữ liệu đối soát... |
| `EXPIRED` | Kết quả kiểm tra quá cũ so với ngưỡng yêu cầu; cần drill mới. |

Đừng gom mọi trạng thái `INCONCLUSIVE` vào `PASS` chỉ vì backup job ban đầu xanh. Một bản backup “đã được verify hash” nhưng **chưa từng restore** nên được báo đúng là “đã kiểm tra hash, chưa xác nhận restore”, không phải “DR ready”.

Với nhiều backup mỗi ngày, có thể kiểm tra hash/manifest cho mọi artifact và làm restore drill định kỳ theo mẫu, cộng thêm restore bắt buộc sau những thay đổi lớn về engine/codec/key/chuỗi backup. Tần suất dựa trên rủi ro và RPO/RTO, không dùng một lịch chung cho mọi hệ thống.

## 19. Thiết kế một báo cáo kiểm tra có khả năng audit

Một báo cáo drill nên trả lời được **ai, kiểm tra cái gì, ở đâu, khi nào và kết quả ra sao**:

```yaml
drill_id: restore-lab-20261122-001
backup_id: shopdb-full-20261122-0100
restore_environment: isolated-restore-lab
backup_type: logical_custom
artifact_integrity: PASS
decryption_test: PASS
format_inspection: PASS
restore_process: PASS
database_startup: PASS
java_read_smoke: PASS
business_invariant_checks: PASS
target_recovery_point: "2026-11-22T01:00:00Z"
observed_recovery_point: "2026-11-22T01:00:00Z"
observed_rto_minutes: 42
review_status: pending_approval
```

Đây là **ví dụ cấu trúc báo cáo**, các trạng thái và con số không phải kết quả đã chạy. Một hệ thống thực cần lưu evidence và log đủ rõ mà **không lộ dữ liệu khách hàng hoặc secret**, tham chiếu đến artifact/manifest bất biến và phiên bản code thực thi kiểm tra.

Tối thiểu nên giữ:

1. Backup ID và artifact hashes/manifest.
2. Version/tùy chọn công cụ tạo và restore.
3. Thành phần base, incremental, WAL đã sử dụng.
4. Quyền và identity dùng để decrypt/restore/đọc.
5. Exit code và log lỗi đã lọc dữ liệu nhạy cảm.
6. Bằng chứng đọc SQL/JDBC và các invariant được kiểm tra.
7. Mốc restore đạt được, RPO/RTO thực tế và sai khác so với mục tiêu.
8. Người phê duyệt, vấn đề tồn đọng và kế hoạch khắc phục.

**Báo cáo phải gắn với đúng backup set**, tránh lấy kết quả restore một file tuần trước để xác nhận tự động file backup mới tạo hôm nay.

## 20. Bảo vệ bản sao khỏi hỏng hoặc bị mã hóa bởi ransomware

Khả năng kiểm tra và phục hồi còn phụ thuộc **các bản sao có sống sót sau sự cố** hay không. Nếu attacker có quyền xóa toàn bộ backup và sửa manifest, việc chạy hash định kỳ không bảo đảm có bản sao sạch để khôi phục.

Các biện pháp thiết kế thường gặp:

- Nhiều bản sao trên miền lỗi độc lập; vận dụng nguyên tắc 3-2-1 khi phù hợp yêu cầu.
- Một bản sao **offsite/khác tài khoản hoặc vùng quản trị**, không cùng quyền xóa với tài khoản ghi production.
- Object lock/WORM/immutability với retention hợp lệ, có cơ chế chống xóa sớm theo chính sách.
- Role backup **chỉ có quyền ghi cần thiết**, role verify/restore chỉ có quyền đọc/giải mã phù hợp; phân tách quyền xóa.
- Manifest hoặc chữ ký được bảo vệ khỏi sửa đổi trái phép.
- Kiểm soát và giám sát việc xóa hàng loạt, thay retention, sửa lifecycle policy.
- Thử drill **từ bản sao ở vùng DR thật**, không chỉ từ đường dẫn local trên máy backup.

Không có chiến lược immutability nào thay thế quy trình quản lý khóa mã hóa. Một bản sao WORM nguyên vẹn nhưng không còn key giải mã vẫn không thể dùng để phục hồi.

## 21. Các lỗi thường gặp và cách giải thích đúng

| Ngộ nhận | Điều cần hiểu |
| --- | --- |
| “File backup có kích thước lớn là đã đủ dữ liệu.” | Có thể bị cắt hoặc thiếu database/object; cần manifest và restore. |
| “Hash SHA-256 khớp nghĩa là database đã phục hồi được.” | Hash chỉ xác nhận byte so với tham chiếu tin cậy. |
| “Giải nén thành công nghĩa là mọi bảng dùng được.” | Còn thiếu schema, role, extension, constraint hoặc dữ liệu có thể sai logic. |
| “`pg_restore --list` thành công nghĩa là restore hoàn chỉnh.” | Liệt kê TOC không thực thi mọi object/data. |
| “`pg_verifybackup` PASS nghĩa là không cần chạy recovery.” | Manifest/file check không thay thế boot và replay thử. |
| “Có base backup là chắc PITR tới hôm nay.” | Cần WAL liên tục, đúng timeline và đúng target. |
| “WAL archive có segment cuối là chuỗi không hở.” | Có thể thiếu segment giữa hoặc sai timeline. |
| “Restore bằng superuser đọc được là Java API cũng đọc được.” | Cần roles, grants, RLS, JDBC driver, schema/extension tương thích. |
| “COUNT trong bản restore phải bằng production hiện tại.” | Hai hệ thống có thể ở mốc commit khác nhau. |
| “Snapshot volume luôn tạo bản DB nhất quán.” | Cần xem phối hợp dữ liệu, log và toàn bộ volume theo DBMS. |
| “Backup có mã hóa là không cần kiểm tra.” | Key có thể mất; ciphertext có thể hỏng; dữ liệu vẫn có thể sai. |
| “Khôi phục được dữ liệu DB tức workflow ngoài DB cũng đúng.” | Object storage, payment provider, events/secret có phạm vi recovery riêng. |
| “RTO bằng thời gian chạy `pg_restore`.” | Còn detection, provision, replay, validation, cutover và smoke test. |
| “Restore lab có thể mở internet để test cho sát production.” | Có nguy cơ replay outbox, gửi email hoặc gọi cổng thanh toán thật. |
| “Một bản backup được restore thành công năm ngoái đủ cho mọi bản mới.” | Artifact, schema, key, DB version và runbook thay đổi theo thời gian. |

## 22. Ma trận kiểm thử lỗi cho bài backup/recovery

Để xác minh pipeline không báo xanh giả, hãy chủ động tạo **bản sao kiểm thử hỏng** trong môi trường cô lập. **Không sửa/xóa backup production thật để tạo kịch bản.**

| Kịch bản | Bước phải phát hiện | Kết quả mong đợi |
| --- | --- | --- |
| Cắt cụt một file backup test | Hash/manifest, mở archive hoặc restore. | `FAIL`, không đánh dấu DR ready. |
| Đổi một byte của artifact test | SHA-256/manifest. | Mismatch, dừng hoặc điều tra. |
| Thay checksum và file cùng lúc | Xác thực manifest/chữ ký độc lập. | Phát hiện giả mạo nếu có trust anchor. |
| Mất key giải mã | Decryption test. | `FAIL/INCONCLUSIVE` theo nguyên nhân; có runbook key recovery. |
| Thiếu một incremental ở giữa | Chain validation/restore. | Không công bố restore point phụ thuộc. |
| Thiếu WAL segment giữa chuỗi | WAL chain/replay PITR. | Không thể đạt target; báo mốc còn khôi phục được nếu xác định chính xác. |
| Backup đúng nhưng sai database | Metadata và kiểm tra schema/marker. | Phát hiện nguồn sai. |
| Dump không chứa một bảng quan trọng | TOC/schema và SQL smoke. | Báo thiếu phạm vi. |
| Restore thiếu role/extension | Restore log hoặc Java integration. | Báo lỗi cấu hình và khắc phục có kiểm soát. |
| Java JDBC có sai timezone/column mapping | Application smoke test. | Báo lỗi ở tầng ứng dụng. |
| Bản sao từ trước một lần ghi hợp lệ | Đối soát recovery point. | Phân biệt RPO hợp lệ với “mất dữ liệu ngoài mục tiêu”. |
| Restore lab vô tình có worker outbox chạy | Egress/scheduler isolation test. | Không phát được side effect ra ngoài. |
| Key được rotate nhưng bản cũ dùng key cũ | Decrypt test với quy trình DR. | Key history/access còn đáp ứng retention. |

Test pipeline cần phân biệt **một backup thật bị lỗi** với **lab tạm thiếu tài nguyên**. Không đánh dấu pass khi không có kết quả; đánh dấu inconclusive và lên lịch thử lại, đồng thời giữ backup khác đã xác minh để đáp ứng RPO/RTO.

## 23. Runbook kiểm tra định kỳ

Một quy trình phù hợp cho nhóm phát triển/vận hành Java có thể chia theo mức độ:

### Mỗi lần backup

1. Xác minh job hoàn tất và artifact xuất hiện ở điểm lưu trữ đích.
2. Ghi nguồn, loại backup, thời điểm, version và phụ thuộc.
3. Xác minh checksum/manifest theo công cụ tương ứng.
4. Thử đọc container/định dạng ở mức có thể mà không cần restore đầy đủ.
5. Kiểm tra kết quả lưu trữ độc lập và trạng thái retention.
6. Phát cảnh báo ngay nếu thiếu artifact, hash mismatch hoặc chain sai.

### Theo lịch drill phục hồi

1. Chọn bản sao theo phân loại rủi ro và **mốc recovery mục tiêu**.
2. Dựng môi trường cô lập, kiểm tra quyền decrypt và lấy artifact.
3. Restore đầy đủ, replay WAL tới mốc nếu đó là kịch bản PITR.
4. Khởi động DB và kiểm tra cấu trúc, extension, schema, quyền.
5. Chạy query nghiệp vụ, đối soát marker và ứng dụng Java smoke.
6. Ghi thời gian thực tế, RPO/RTO và bằng chứng.
7. Review thất bại, tạo hành động khắc phục và thử lại sau sửa.

### Sau thay đổi đáng kể

Làm thêm drill khi:

- Nâng major version PostgreSQL hoặc driver/ORM ảnh hưởng định dạng/khả năng đọc.
- Đổi công cụ backup, codec nén hoặc giải pháp mã hóa/KMS.
- Chuyển storage/bucket, quyền IAM hoặc vùng DR.
- Thay retention/WAL archive/incremental chain.
- Thêm database, extension, object storage hoặc phụ thuộc mới quan trọng.
- Thay mô hình role/RLS, kiến trúc multi-tenant hoặc schema có dữ liệu nhạy cảm.

Không đặt lịch một lần rồi quên các điều kiện làm **mất khả năng restore** dù file backup vẫn tồn tại.

## 24. Tình huống thực hành: backup thành công nhưng không phục hồi được tới 14:05

Giả sử công ty đặt mục tiêu **RPO 15 phút, RTO 60 phút** cho một dịch vụ đơn hàng Java. Hệ thống dùng PostgreSQL, base backup hằng ngày và WAL archive để PITR.

Vào lúc 14:10, một thao tác sai gây mất dữ liệu. Đội vận hành muốn phục hồi tới **14:05**, trước thay đổi lỗi. Bản base backup đêm trước kiểm tra hash thành công. Tuy nhiên, khi thử replay, công cụ báo **thiếu WAL segment ở khoảng 11:30**.

**Phân tích theo từng tầng:**

1. **Hiện diện:** base backup có mặt và metadata đúng.
2. **Hash:** artifact base còn nguyên so với manifest.
3. **Định dạng:** base backup có thể đọc được.
4. **Chuỗi PITR:** thiếu WAL 11:30; không có đường replay liên tục từ base tới 14:05.
5. **Restore:** không đạt recovery target 14:05 theo kế hoạch.
6. **Nghiệp vụ:** chưa có instance đạt target để chạy smoke test hay đối soát đơn hàng.

Kết luận đúng là **bản base backup kiểm tra tốt nhưng kế hoạch PITR không khả dụng tới mốc yêu cầu**. Không được báo “backup healthy” theo nghĩa DR end-to-end chỉ vì base hash khớp. Cần tìm WAL thiếu ở các bản sao độc lập, đánh giá khả năng khôi phục khác theo runbook, và ghi nhận RPO thực tế thay vì tự giả định đã đạt.

### Câu hỏi mở rộng

- Nếu tìm được segment thiếu trong object storage ở vùng khác, làm sao chứng minh nó đúng timeline và replay được?
- Nếu restore lab cần 75 phút, nên thay đổi phần nào để đáp ứng RTO 60 phút?
- Nếu Order DB phục hồi nhưng Payment Service giữ dữ liệu mới hơn, cần đối soát giao dịch nào?
- Nếu bản sao được mã hóa bằng khóa đã vô hiệu hóa, quy trình DR phải có quyền/key nào?
- Bằng chứng nào cho thấy ứng dụng Java đã đọc được order và chạy được những câu SQL thiết yếu?

## 25. Câu hỏi tự kiểm tra

**Câu 1.** SHA-256 của tệp dump khớp với digest được lưu. Có thể tuyên bố dump chắc chắn phục hồi được không?

**Không.** Hash chỉ xác nhận byte không đổi so với tham chiếu; cần mở định dạng, restore và kiểm tra dữ liệu/ứng dụng.

**Câu 2.** `pg_restore --list` đọc được TOC. Bước nào còn cần thiết?

Phục hồi thử bằng `pg_restore` trên database cô lập, xem lỗi thực thi, kiểm tra bảng/extension/role và chạy smoke test nghiệp vụ.

**Câu 3.** Một base backup có đủ file và manifest PASS, nhưng không có WAL archive sau mốc backup. Có đạt PITR tới 14:00 được không?

**Không mặc nhiên.** Cần chuỗi WAL liên tục, đúng timeline, tới target. Verification base không thay thế kiểm thử PITR.

**Câu 4.** `pg_verifybackup` PASS có chứng minh ứng dụng Java chắc chắn kết nối và đọc được dữ liệu không?

**Không.** Còn phụ thuộc restore, schema/role/extension, driver và logic nghiệp vụ. Phải chạy Java/JDBC smoke test trên DB phục hồi.

**Câu 5.** Tại sao không so thẳng `COUNT(*)` ở backup đêm qua với production hiện tại?

Vì production có thể đã nhận thêm/đổi dữ liệu. Cần so tại cùng snapshot/recovery point hoặc dùng marker và bất biến có ý nghĩa.

**Câu 6.** Backup mã hóa không bị đổi byte nhưng không còn KMS key thì có phục hồi được không?

**Không.** Khả năng giải mã là yêu cầu độc lập; phải giữ/quản lý key và quyền truy cập phù hợp thời hạn retention.

**Câu 7.** Restore bằng superuser đọc bảng thành công có chứng minh API runtime sẽ hoạt động không?

**Không.** Role runtime có thể thiếu quyền, RLS/search path khác hoặc ứng dụng không tương thích. Phải test theo danh tính và cấu hình dự kiến.

**Câu 8.** Restore lab có thể khởi động scheduler và consumer production để “kiểm thử sát thực tế” không?

**Không được để chúng tạo side effect thật.** Cần cô lập mạng, thay endpoint/credential và tắt hoặc mô phỏng scheduler, payment, mail, webhook, outbox relay.

**Câu 9.** RTO có phải bằng thời gian `pg_restore` không?

**Không.** Bao gồm phát hiện, kích hoạt, provision, truyền backup, replay, kiểm tra và cutover tới khả năng phục vụ đã cam kết.

**Câu 10.** Hash của base backup đúng nhưng thiếu một WAL segment, nên báo trạng thái thế nào?

**Phân biệt các tầng:** tính toàn vẹn của base PASS, kiểm tra chuỗi WAL/PITR FAIL hoặc chưa đủ, trạng thái recoverability tới target không đạt. Không tổng hợp thành một dấu xanh sai.

## Kết luận

**Kiểm tra bản sao không dừng ở câu hỏi “file còn ở đó không?”.** Một quy trình đáng tin phải phân biệt **tính toàn vẹn byte**, **khả năng giải mã và đọc định dạng**, **tính đầy đủ của base/incremental/WAL**, **khả năng restore**, và **khả năng đọc đúng dữ liệu bằng ứng dụng Java**.

Trong thiết kế persistence, hãy lưu metadata và manifest có thể xác thực, thực hiện restore drill cô lập, kiểm tra schema/quyền/JDBC, đối soát dữ liệu tại recovery point phù hợp và đo **RPO/RTO thực tế**. Chỉ khi có bằng chứng đi qua các tầng đó, đội ngũ mới có cơ sở tin rằng bản sao có thể biến thành một hệ thống hoạt động trở lại sau sự cố — thay vì chỉ là một tệp nằm trong kho lưu trữ.

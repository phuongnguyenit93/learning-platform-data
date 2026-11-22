# Manifest, pg_verifybackup và xác minh bản sao lưu PostgreSQL

Một bản backup PostgreSQL chỉ có giá trị khi có thể khôi phục được dữ liệu cần thiết vào thời điểm cần thiết. Việc lệnh backup kết thúc với exit code 0 mới chứng minh quá trình tạo bản sao lưu đã hoàn tất theo cơ chế của công cụ; nó chưa chứng minh mọi file vẫn nguyên vẹn sau khi copy, upload, lưu trữ hoặc truyền qua mạng.

PostgreSQL cung cấp **backup manifest** và công cụ **pg_verifybackup** để kiểm tra tính toàn vẹn của physical base backup được tạo bằng pg_basebackup. Manifest ghi nhận các file thuộc bản backup cùng kích thước và checksum; pg_verifybackup đọc manifest rồi so sánh với nội dung thực tế, đồng thời có thể kiểm tra các WAL segments cần thiết và parse WAL records.

Tuy nhiên, xác minh checksum vẫn chưa thay thế một lần restore thực tế. Một quy trình backup đáng tin cậy cần nhiều lớp:

1. Tạo base backup nhất quán.
2. Lưu manifest cùng backup và bảo vệ tính toàn vẹn của manifest.
3. Chạy pg_verifybackup trên bản sao đã lưu ở đích.
4. Bảo đảm WAL cần thiết có mặt và có thể đọc.
5. Restore thử vào môi trường cô lập.
6. Khởi động PostgreSQL, kiểm tra recovery và dữ liệu.
7. Chạy kiểm tra nghiệp vụ và đo thời gian khôi phục.

Bài học này giải thích cấu trúc manifest, cách sử dụng pg_verifybackup, phạm vi mà công cụ xác minh, các giới hạn cần hiểu và cách xây dựng quy trình kiểm chứng backup có thể lặp lại.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của backup manifest trong physical backup PostgreSQL.
2. Mô tả thông tin file, kích thước, checksum và WAL range được manifest ghi nhận.
3. Tạo base backup có manifest bằng pg_basebackup.
4. Chọn checksum algorithm phù hợp và hiểu khác biệt giữa checksum và chữ ký số.
5. Chạy pg_verifybackup và đọc kết quả/exit status.
6. Dùng các tùy chọn manifest path, WAL directory, progress và chế độ kiểm tra phù hợp với phiên bản.
7. Phân biệt kiểm tra file checksum, kiểm tra WAL và kiểm tra khả năng restore.
8. Hiểu ảnh hưởng của plain format, tar format, tablespaces và WAL được lưu riêng.
9. Phát hiện file thiếu, file thừa, sai kích thước, checksum mismatch và WAL không hợp lệ.
10. Hiểu vì sao một manifest bị sửa cùng với file có thể làm mất giá trị xác minh.
11. Kết hợp pg_verifybackup với restore drill, PITR và kiểm tra ứng dụng.
12. Lập lịch, lưu báo cáo, quản lý retention và cảnh báo backup verification.

## 2. Backup manifest là gì?

Backup manifest là một file mô tả nội dung của một physical base backup. Với pg_basebackup trên các phiên bản hỗ trợ manifest, PostgreSQL tạo file có tên:

```text
backup_manifest
```

Manifest thường nằm ở thư mục gốc của bản backup dạng plain. Với các định dạng backup khác, vị trí lưu manifest phụ thuộc cách pg_basebackup ghi output.

Manifest cung cấp một danh sách có cấu trúc về những file thuộc backup, cùng thông tin để kiểm tra chúng. Nó cũng ghi nhận WAL ranges liên quan tới tính nhất quán của backup.

### 2.1. Vì sao cần manifest?

Khi backup được truyền qua nhiều bước:

```text
PostgreSQL primary
      |
      v
pg_basebackup
      |
      v
Local staging directory
      |
      v
Compression / encryption / packaging
      |
      v
Object storage / backup repository
      |
      v
Restore staging host
```

File có thể bị thiếu, bị cắt ngắn, bị ghi đè hoặc hỏng trong một bước copy. Manifest cho phép kiểm tra các file trong backup có còn khớp với metadata và checksum đã ghi nhận khi tạo backup hay không.

### 2.2. Manifest không phải backup

Manifest chỉ là metadata mô tả backup. Nó không chứa toàn bộ database pages và không thể thay thế data files, WAL hoặc base backup.

### 2.3. Manifest không tự bảo vệ chính nó

Nếu một người hoặc một quy trình lỗi sửa cả file backup lẫn manifest để chúng khớp với nhau, phép kiểm tra checksum có thể vẫn thành công. Vì vậy, cần bảo vệ manifest bằng quyền truy cập, immutable storage, chữ ký hoặc digest được lưu độc lập.

## 3. Những thông tin quan trọng trong manifest

Manifest là JSON. Các trường cụ thể và phiên bản manifest có thể thay đổi theo PostgreSQL major version, nhưng thường có những nhóm thông tin sau:

| Nhóm | Ý nghĩa |
| --- | --- |
| Manifest version | Phiên bản định dạng manifest |
| PostgreSQL version | Phiên bản server tạo backup |
| System identifier | Định danh cluster nguồn |
| Files | Danh sách file thuộc backup |
| File size | Kích thước file tại thời điểm tạo manifest |
| File checksum | Checksum của nội dung file theo algorithm đã chọn |
| WAL ranges | Khoảng WAL cần thiết để backup đạt trạng thái nhất quán |
| Manifest checksum | Checksum kiểm tra nội dung manifest |

### 3.1. Danh sách files

Mỗi file entry có thể ghi đường dẫn tương đối, kích thước và checksum. Đường dẫn giúp công cụ xác định file nào phải tồn tại trong backup.

### 3.2. File size

Kích thước giúp phát hiện file bị truncate hoặc thay đổi kích thước. Một file có đúng kích thước vẫn có thể chứa bytes sai, vì vậy cần checksum.

### 3.3. File checksum

Checksum được tính trên nội dung file khi manifest được tạo. Khi verify, công cụ đọc file hiện tại và tính lại checksum để so sánh.

### 3.4. WAL ranges

Manifest ghi lại thông tin WAL liên quan tới backup. Đây là cơ sở để pg_verifybackup biết những segment nào cần có và kiểm tra khả năng đọc/parse WAL.

### 3.5. Manifest checksum

Manifest cũng có checksum để phát hiện lỗi nội bộ của file manifest. Checksum này không phải chữ ký số và không chứng minh manifest đến từ một nguồn đáng tin cậy.

## 4. Checksum trong manifest

Checksum là giá trị được tính từ bytes của file. Nếu nội dung thay đổi, checksum có xác suất cao thay đổi theo.

PostgreSQL hỗ trợ nhiều thuật toán checksum cho manifest tùy phiên bản. Các lựa chọn thường gặp gồm CRC32C và các thuật toán SHA-2 như SHA256, SHA384 hoặc SHA512.

### 4.1. CRC32C

CRC32C có tốc độ tốt và hữu ích để phát hiện lỗi truyền/lưu trữ ngẫu nhiên. Nó không phải cryptographic hash và không được thiết kế để chống kẻ tấn công chủ động tạo nội dung va chạm.

### 4.2. SHA256

SHA256 có thể được chọn để có checksum mạnh hơn cho kiểm tra integrity. Nó phù hợp hơn khi cần giảm rủi ro va chạm có chủ đích so với CRC32C.

### 4.3. Checksum không phải encryption

Checksum không mã hóa dữ liệu và không che nội dung backup. Nếu backup chứa PII hoặc secrets, cần encryption at rest/in transit và access control riêng.

### 4.4. Checksum không phải chữ ký số

SHA256 trong manifest không tự xác thực ai đã tạo backup. Nếu attacker có thể thay đổi cả file và manifest, họ có thể tính checksum mới.

Để xác thực nguồn gốc:

- Tạo digest của manifest sau backup.
- Ký digest bằng key được quản lý ngoài backup repository.
- Lưu signature hoặc digest trong hệ thống có quyền ghi độc lập.
- Bảo vệ private signing key bằng KMS/HSM hoặc secret management.
- Khi restore, xác minh chữ ký/digest trước rồi mới tin manifest.

### 4.5. Chọn thuật toán khi tạo backup

Ví dụ:

```bash
pg_basebackup --pgdata=/backup/staging/base_2026_11_14 --format=plain --wal-method=stream --manifest-checksums=SHA256 --progress --verbose
```

Đây là ví dụ cho môi trường lab. Các tùy chọn và thuật toán được hỗ trợ cần kiểm tra bằng pg_basebackup --help của đúng PostgreSQL version.

### 4.6. Algorithm phải tương thích

pg_verifybackup cần hiểu thuật toán được ghi trong manifest. Dùng binary phù hợp với phiên bản backup và kiểm tra help/version trước khi đưa vào automation.

## 5. Tạo backup có manifest bằng pg_basebackup

pg_basebackup tạo physical base backup từ một PostgreSQL server đang chạy, thông qua replication protocol.

Ví dụ:

```bash
pg_basebackup --host=db-primary.example.internal --port=5432 --username=backup_user --pgdata=/backup/staging/base_2026_11_14 --format=plain --wal-method=stream --manifest-checksums=SHA256 --progress --verbose
```

Ví dụ cần role có quyền replication phù hợp, xác thực đã cấu hình, network truy cập được và thư mục đích có đủ dung lượng. Không ghi password production trực tiếp trong command history.

### 5.1. Manifest mặc định

Trên các phiên bản hỗ trợ, pg_basebackup tạo backup manifest theo mặc định. Tùy chọn --no-manifest tắt việc tạo manifest; khi đó pg_verifybackup không có manifest để xác minh.

### 5.2. Chọn plain format

Với plain format, pg_basebackup ghi ra một directory tree có cấu trúc như PGDATA và manifest nằm cùng cây backup. Đây là workflow đơn giản để chạy pg_verifybackup trực tiếp trên thư mục.

### 5.3. Tar format

pg_basebackup cũng hỗ trợ tar format. Quy trình xử lý manifest và việc pg_verifybackup có thể đọc trực tiếp archive phụ thuộc phiên bản/công cụ. Workflow dễ kiểm soát là giải nén các tar files vào một staging directory theo đúng cấu trúc backup, đặt manifest đúng vị trí mà tool mong đợi, rồi xác minh bản đã giải nén. Không verify riêng một file tar bằng cách giả định nó là PGDATA directory.

Nếu hệ thống dùng backup manager hoặc archive format riêng, dùng workflow verification được công cụ đó hỗ trợ và vẫn kiểm tra nội dung đã restore vào staging.

### 5.4. Không bỏ manifest để tiết kiệm vài bytes

Manifest thường nhỏ so với data files. Bỏ manifest làm mất một lớp kiểm tra quan trọng và khiến quy trình verify cần tự xây metadata khác.

## 6. Các phương pháp lấy WAL khi tạo base backup

pg_basebackup có các WAL methods chính:

| Method | Cách hoạt động | Trade-off |
| --- | --- | --- |
| stream | Stream WAL đồng thời với quá trình backup | Thường tiện cho backup tự chứa; cần đủ WAL sender connections |
| fetch | Lấy WAL cần thiết ở cuối backup | Primary phải giữ đủ WAL trong suốt backup |
| none | Không lấy WAL cùng backup | Cần archive/recovery path riêng để hoàn tất và restore |

### 6.1. stream

```bash
pg_basebackup -D /backup/base_stream -Fp -X stream -P
```

WAL được stream trong lúc backup. Primary thường cần thêm một WAL sender cho luồng WAL riêng, ngoài connection dùng để copy data.

### 6.2. fetch

```bash
pg_basebackup -D /backup/base_fetch -Fp -X fetch -P
```

WAL được lấy sau khi phần data backup hoàn tất. Nếu primary recycle segment cần thiết trước khi fetch, backup có thể thất bại. Retention phải đủ trong toàn bộ thời gian backup.

### 6.3. none

```bash
pg_basebackup -D /backup/base_no_wal -Fp -X none -P
```

Với none, backup không tự chứa WAL theo cách stream/fetch. Cần một archive có đầy đủ WAL range và recovery procedure tương ứng. Đừng xem một thư mục data-only là bản backup có thể khôi phục độc lập.

### 6.4. WAL range và backup consistency

Online physical backup cần WAL để đưa các data files về một trạng thái nhất quán khi recovery. Manifest ghi nhận WAL range cần thiết để công cụ verify kiểm tra phần WAL liên quan.

## 7. Chạy pg_verifybackup

Với plain-format backup directory:

```bash
pg_verifybackup /backup/staging/base_2026_11_14
```

Khi thành công, pg_verifybackup kết thúc với exit status 0 và thông báo backup đã được xác minh. Nếu phát hiện file thiếu, sai kích thước, checksum mismatch hoặc WAL không hợp lệ, công cụ báo lỗi và trả exit status khác 0.

### 7.1. Chạy trên bản đã copy tới đích

Một quy trình hữu ích:

1. Tạo backup ở staging.
2. Verify staging để phát hiện lỗi ngay sau khi backup.
3. Copy/upload backup và manifest tới repository.
4. Download hoặc mount bản backup tại một verify host.
5. Chạy pg_verifybackup trên bản ở đích.

Lần verify thứ hai kiểm tra cả đường truyền/lưu trữ từ staging tới repository.

### 7.2. Dùng đúng directory

Tham số chính là backup directory, không phải database name, PGDATA đang chạy hoặc đường dẫn tới một file data riêng lẻ.

### 7.3. Không chạy trên PGDATA đang được server sử dụng

Verify một bản backup bất biến hoặc bản sao staging. Không thay đổi files trong lúc pg_verifybackup đang đọc chúng; kết quả có thể không phản ánh một snapshot nhất quán.

### 7.4. Chạy dưới quyền phù hợp

Process cần đọc tất cả file backup, bao gồm file trong tablespaces được map. Cấp quyền read-only cần thiết; không cần chạy tool với quyền root nếu không có lý do.

## 8. Các tùy chọn pg_verifybackup

Tùy chọn cụ thể phụ thuộc phiên bản. Luôn kiểm tra:

```bash
pg_verifybackup --help
pg_verifybackup --version
```

Những tùy chọn thường gặp:

| Tùy chọn | Mục đích |
| --- | --- |
| --manifest-path | Chỉ định đường dẫn manifest khi không dùng vị trí mặc định |
| --wal-directory | Chỉ định directory chứa WAL cần kiểm tra nếu WAL nằm riêng |
| --progress | Hiển thị tiến độ verify |
| --quiet | Giảm output thông thường |
| --exit-on-error | Dừng ngay khi gặp lỗi đầu tiên |
| --no-parse-wal | Bỏ qua bước parse WAL |
| --skip-checksums | Bỏ qua việc kiểm tra checksum file |

Không phải mọi tùy chọn có mặt trên mọi major version. Đọc help của binary đang triển khai.

### 8.1. Progress

```bash
pg_verifybackup --progress /backup/base_2026_11_14
```

Hữu ích với backup lớn để biết quá trình đang tiến triển.

### 8.2. Chỉ định manifest path

```bash
pg_verifybackup --manifest-path=/backup/metadata/backup_manifest /backup/base_2026_11_14
```

Chỉ dùng khi manifest được lưu ở vị trí khác theo workflow hợp lệ. Manifest phải mô tả đúng backup directory đang verify.

### 8.3. WAL directory riêng

```bash
pg_verifybackup --wal-directory=/backup/wal/pg_cluster_a /backup/base_2026_11_14
```

Tùy chọn này hữu ích khi WAL cần cho backup được lưu ngoài thư mục data backup. Xác minh rằng directory chứa đúng các segment/timeline được manifest yêu cầu.

### 8.4. no-parse-wal

```bash
pg_verifybackup --no-parse-wal /backup/base_2026_11_14
```

Tùy chọn này bỏ qua parse WAL. Nó có thể giảm thời gian trong một số workflow, nhưng giảm phạm vi xác minh. Không dùng như chế độ verification đầy đủ nếu mục tiêu là kiểm tra cả khả năng đọc cấu trúc WAL.

### 8.5. skip-checksums

```bash
pg_verifybackup --skip-checksums /backup/base_2026_11_14
```

Tùy chọn này bỏ qua kiểm tra checksum nội dung file. Nó không tương đương một lần verify integrity đầy đủ. Chỉ dùng khi có mục tiêu chẩn đoán cụ thể và có lớp xác minh khác.

### 8.6. exit-on-error

Mặc định công cụ có thể tiếp tục để báo nhiều lỗi trong một lần chạy. exit-on-error dừng sớm ở lỗi đầu tiên, phù hợp khi muốn fail-fast trong pipeline hoặc điều tra một failure cụ thể.

## 9. pg_verifybackup kiểm tra những gì?

Phạm vi chính:

1. Đọc và kiểm tra cấu trúc manifest.
2. Xác định các file backup được liệt kê.
3. Kiểm tra sự hiện diện và kích thước file.
4. Tính lại checksum và so sánh với manifest, trừ khi bỏ qua checksum.
5. Phát hiện file thiếu hoặc file không mong đợi theo quy tắc kiểm tra của tool.
6. Xác định WAL segments cần thiết từ manifest.
7. Kiểm tra WAL files liên quan và parse WAL records nếu không tắt bước parse.

### 9.1. File bị thiếu

Nếu một file được manifest liệt kê nhưng không có ở backup directory, verify sẽ báo lỗi.

### 9.2. File bị truncate

Nếu file nhỏ hơn hoặc khác kích thước ghi trong manifest, verify có thể phát hiện qua size check.

### 9.3. File cùng size nhưng nội dung khác

Checksum giúp phát hiện trường hợp file có cùng kích thước nhưng bytes đã thay đổi.

### 9.4. File thừa

File xuất hiện ngoài manifest có thể chỉ ra backup directory bị trộn với dữ liệu khác hoặc có thay đổi sau khi backup. Công cụ có thể báo file không mong đợi theo cách nó kiểm tra directory tree. Điều tra trước khi bỏ qua; không tự động xóa file lạ trong bản backup gốc.

### 9.5. WAL thiếu hoặc hỏng

Manifest ghi WAL ranges cần thiết. pg_verifybackup có thể phát hiện segment cần thiết không có sẵn hoặc WAL không thể parse theo format/version tương ứng.

### 9.6. Không kiểm tra semantics nghiệp vụ

Checksum đúng không chứng minh tất cả business rows cần thiết đều có mặt, foreign keys hoặc business invariants đáp ứng mong muốn, extension có thể được nạp trên host restore, ứng dụng có thể kết nối hoặc backup có thể restore trong RTO yêu cầu. Những điều đó cần restore test và application-level validation.

## 10. Kiểm tra file checksum khác với data page checksum

PostgreSQL có hai khái niệm dễ nhầm:

| Khái niệm | Kiểm tra gì? | Cách sử dụng |
| --- | --- | --- |
| Backup manifest checksum | Bytes của file backup so với checksum ghi trong manifest | pg_verifybackup |
| Data page checksum | Nội dung page database có checksum page hợp lệ hay không | Được kiểm tra khi page được đọc; pg_checksums có thể kiểm tra offline |

### 10.1. Manifest checksum

Nó kiểm tra file backup hiện tại có khớp file tại thời điểm manifest được tạo hay không.

### 10.2. Data checksums

Data page checksums được bật khi khởi tạo cluster hoặc bằng quy trình hỗ trợ ở phiên bản phù hợp. Chúng giúp phát hiện page corruption khi PostgreSQL đọc page.

### 10.3. pg_checksums

pg_checksums là công cụ riêng để kiểm tra hoặc quản lý page checksums trong các điều kiện hỗ trợ. Việc check cluster thường yêu cầu server đã dừng sạch; không chạy offline checksum tool trên data directory đang được PostgreSQL sử dụng.

### 10.4. Hai lớp có thể bổ sung nhau

pg_verifybackup kiểm tra file copy có khớp manifest; page checksums kiểm tra tính toàn vẹn ở mức page database. Sau khi restore vào một cluster cô lập và dừng server theo đúng quy trình, có thể dùng pg_checksums nếu cấu hình/version phù hợp.

## 11. WAL verification và pg_waldump

WAL cần thiết để đưa online base backup về trạng thái nhất quán. pg_verifybackup có thể dùng khả năng parse WAL của PostgreSQL (thông qua các công cụ/thư viện tương ứng của phiên bản) để kiểm tra các records trong WAL segments liên quan.

### 11.1. Vì sao parse WAL?

File WAL tồn tại và có đúng kích thước vẫn có thể chứa bytes sai. Parse giúp phát hiện một số dạng corruption hoặc record không hợp lệ.

### 11.2. Không đồng nghĩa replay thành công tới mọi target

Parse WAL không thay thế restore/recovery. Recovery còn phụ thuộc base backup, timeline, control files, archive chain, cấu hình và khả năng replay trong server thực tế.

### 11.3. WAL version compatibility

WAL format thay đổi theo PostgreSQL major version. Dùng pg_verifybackup/pg_waldump phù hợp với major version của backup; không dùng binary cũ hơn rồi coi kết quả là kết luận đầy đủ.

### 11.4. WAL directory

Nếu backup dùng WAL ngoài directory backup, chỉ định đúng directory qua tùy chọn tương ứng. Đừng verify một WAL directory rỗng rồi kết luận backup có đầy đủ WAL.

### 11.5. No-parse-wal

Bỏ parse WAL chỉ bỏ một lớp kiểm tra. Trong quy trình production, nếu cần skip vì lý do thời gian, hãy ghi nhận đây là verification coverage bị giảm và bù bằng restore drill.

## 12. Backup format và tablespaces

Một PostgreSQL cluster có thể gồm PGDATA và nhiều tablespaces đặt ở đường dẫn khác.

### 12.1. Plain format

Plain format tạo directory tree có thể dùng làm PGDATA cho restore. Đây là cách trực tiếp nhất để pg_verifybackup đọc các file và manifest.

### 12.2. Tar format

Tar format đóng các phần của backup vào archive files. Trước khi verify bằng workflow yêu cầu directory tree, cần giải nén đầy đủ các archive đúng vị trí, bao gồm manifest và tablespaces. Giữ nguyên mapping/path semantics.

### 12.3. Tablespaces

Nếu source có tablespaces, base backup có thể chứa dữ liệu tablespace ngoài PGDATA hoặc mapping theo tùy chọn của pg_basebackup. Khi verify, các directory được manifest tham chiếu phải tồn tại ở vị trí tương ứng.

### 12.4. Tablespace mapping

Ví dụ:

```bash
pg_basebackup -D /backup/base -Fp -X stream -T /var/lib/postgresql/tablespace_fast=/backup/tablespaces/fast
```

Đường dẫn minh họa; mapping phải khớp tablespace thật trên source. Ghi lại mapping trong backup metadata để restore host tái tạo đúng cấu trúc.

### 12.5. Symlinks

Tablespaces có thể được biểu diễn bằng symlinks trong PGDATA. Khi copy/restore, cần bảo đảm target directories tồn tại, quyền truy cập đúng và symlink không trỏ về data directory production ngoài ý muốn.

### 12.6. Verify tất cả file tree

Chỉ verify thư mục PGDATA mà bỏ qua tablespace directories có thể khiến kiểm tra không đầy đủ. Xác minh toàn bộ backup layout theo manifest và cách backup được tạo.

## 13. Manifest và backup sau compression/encryption

Một backup repository có thể lưu backup dưới dạng compressed/encrypted object thay vì directory plain.

### 13.1. Verify trước hay sau giải nén?

pg_verifybackup cần đọc file tree ở dạng backup mà nó hiểu. Với object đã nén/mã hóa, quy trình thường là:

1. Kiểm tra object metadata và transport checksum nếu có.
2. Download object.
3. Giải mã bằng key được quản lý an toàn.
4. Giải nén vào staging directory cô lập.
5. Chạy pg_verifybackup trên file tree đã giải nén.

### 13.2. Compression checksum

Một archive format có thể có checksum riêng cho container. Nó kiểm tra tính toàn vẹn của archive container, nhưng không thay thế việc kiểm tra file-level manifest sau khi giải nén.

### 13.3. Encryption authentication

Dùng authenticated encryption hoặc cơ chế integrity tương ứng để phát hiện ciphertext bị sửa. Không coi encryption không có authentication là đủ để chứng minh backup không bị thay đổi.

### 13.4. Kiểm tra object size và metadata

Lưu object size, storage version ID, ETag/checksum theo semantics của storage provider, upload timestamp và backup ID. Một số ETag không phải SHA256 của nội dung object; đọc đúng tài liệu storage.

### 13.5. Không ghi đè backup đã xác minh

Đặt mỗi backup vào một path/version bất biến hoặc unique ID. Không upload backup mới vào cùng prefix/file name theo cách có thể làm thay đổi artifact đã được xác minh.

## 14. Bảo vệ manifest và chuỗi provenance

Checksum chỉ hữu ích khi manifest được tin cậy.

### 14.1. Threat model

Xét hai tình huống:

- Lỗi ngẫu nhiên: disk, network, RAM hoặc storage làm bytes thay đổi.
- Sửa đổi có chủ đích: một actor có quyền ghi thay cả backup và manifest.

Manifest checksum giải quyết tốt hơn tình huống lỗi ngẫu nhiên. Nó không tự giải quyết việc manifest bị thay bởi actor có quyền.

### 14.2. Ký manifest

Sau khi backup hoàn tất:

1. Đọc file backup_manifest.
2. Tính digest bằng thuật toán được tổ chức chọn.
3. Ký digest bằng private key không nằm cùng backup.
4. Lưu signature, key ID, backup ID và metadata ở một nơi độc lập.
5. Khi verify, xác minh signature trước rồi chạy pg_verifybackup.

Ví dụ ý tưởng:

```text
backup_manifest
      |
      v
SHA-256 digest
      |
      v
Ký bằng private key
      |
      v
signature + key_id + backup_id
      |
      v
Lưu trong immutable metadata repository
```

Không coi sơ đồ này là câu lệnh ký cụ thể; dùng công cụ/KMS phù hợp với tổ chức.

### 14.3. Immutable storage

Object lock, versioning hoặc WORM retention có thể giảm khả năng backup bị sửa/xóa trước hạn. Kiểm tra retention mode, quyền bypass và account quản trị.

### 14.4. Least privilege

Backup writer có thể tạo object mới nhưng không nên có quyền xóa hoặc ghi đè mọi backup lịch sử. Restore operator nên có quyền đọc cần thiết, không mặc định có quyền xóa.

### 14.5. Provenance metadata

Gắn mỗi backup với backup ID, cluster/system identifier, PostgreSQL major/minor version, start/end time, backup tool version, manifest digest/signature, WAL method, tablespace mappings, encryption key ID, storage object/version ID và verification result/timestamp.

## 15. Một pipeline backup và verify hoàn chỉnh

```text
1. Preflight
   |
2. pg_basebackup tạo base backup + manifest
   |
3. Kiểm tra pg_basebackup exit status
   |
4. pg_verifybackup trên staging
   |
5. Sign/hash manifest và ghi metadata
   |
6. Compress/encrypt/upload
   |
7. Download/restore artifact vào verify staging
   |
8. Verify signature + pg_verifybackup
   |
9. Restore drill trong môi trường cô lập
   |
10. Application smoke tests
   |
11. Ghi verification record
   |
12. Retention/lifecycle theo policy
```

### 15.1. Preflight

Kiểm tra dung lượng, network, replication role, số WAL senders, backup destination, encryption key và lịch backup.

### 15.2. Backup

Chạy pg_basebackup với manifest, WAL method và tablespace mapping đã xác định. Lưu stdout/stderr và exit status.

### 15.3. Verify staging

Chạy pg_verifybackup ngay sau khi tạo. Nếu thất bại, không promote artifact thành backup verified.

### 15.4. Publish artifact

Copy/upload tới repository với object versioning/immutability. Không thay đổi file tree sau khi đã ký manifest nếu không tạo artifact mới.

### 15.5. Verify tại destination

Kiểm tra artifact sau khi download/restore staging. Đây là nơi phát hiện lỗi transport, storage hoặc decompression.

### 15.6. Restore drill

Khởi động một PostgreSQL instance độc lập từ backup, sử dụng WAL/archive path phù hợp và chạy query kiểm tra.

## 16. Ví dụ tạo và verify plain backup

Tạo thư mục đích mới, rỗng và chỉ dành cho một backup:

```bash
pg_basebackup --host=db-primary.example.internal --port=5432 --username=backup_user --pgdata=/backup/staging/pg_2026_11_14T020000Z --format=plain --wal-method=stream --manifest-checksums=SHA256 --progress --verbose
```

Sau khi command thành công:

```bash
pg_verifybackup --progress /backup/staging/pg_2026_11_14T020000Z
```

Kiểm tra metadata:

```bash
ls -lah /backup/staging/pg_2026_11_14T020000Z
```

Thư mục thường có các thành phần như PG_VERSION, base, global, pg_wal, pg_tblspc, backup_label và backup_manifest, tùy backup layout/version/tablespaces.

### 16.1. Không copy thêm file tùy tiện vào backup

Nếu muốn lưu log, signature hoặc metadata riêng, đặt ở sibling directory hoặc repository metadata path. Tránh làm lẫn file vận hành với data tree cần manifest verify.

### 16.2. Không sửa file sau verify

Nếu nén, mã hóa hoặc copy tiếp, verify lại ở artifact cuối cùng sau khi giải mã/giải nén. Một lần verify trước upload không kiểm tra được bytes sau upload.

## 17. Ví dụ kiểm tra khi WAL lưu ở nơi riêng

Nếu workflow lưu WAL cần thiết ở directory riêng:

```bash
pg_verifybackup --wal-directory=/backup/wal/pg_cluster_a /backup/staging/base_2026_11_14
```

Đảm bảo directory chứa đúng WAL segments và timeline cần thiết theo manifest. Tên segment có thể giống nhau ở các timeline khác nhau; recovery metadata và history files vẫn quan trọng.

Nếu dùng WAL archive ngoài filesystem, cần fetch/copy các segment cần thiết vào một staging WAL directory trước khi verify, hoặc dùng backup tooling hỗ trợ archive verification. Không trỏ tùy tiện tới archive root chứa nhiều clusters.

## 18. Đọc lỗi pg_verifybackup

Các nhóm lỗi thường gặp:

| Lỗi | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| Manifest không đọc được | File thiếu, JSON lỗi, permission | Kiểm tra manifest path và copy process |
| File missing | Backup copy thiếu file | So path trong manifest, storage logs |
| Size mismatch | File truncate hoặc bị thay đổi | So kích thước, object version, transfer logs |
| Checksum mismatch | Bytes thay đổi hoặc manifest không khớp | Kiểm tra source/destination digest, disk/network |
| Unexpected file | Backup tree bị thêm file hoặc trộn dữ liệu | Xác định file đến từ bước nào |
| WAL missing | Thiếu segment trong WAL range | Kiểm tra WAL method, archive và wal directory |
| WAL parse error | Segment hỏng, sai version hoặc thiếu bytes | Kiểm tra segment, timeline, tool version |
| Permission denied | User verify không đọc được file | Sửa quyền read-only trên staging |
| Unsupported format/version | Tool không tương thích | Dùng binary đúng major/version |

### 18.1. Checksum mismatch không nên bị bỏ qua

Không dùng --skip-checksums để biến backup hỏng thành backup verified. Tìm bản sao khác, kiểm tra source và destination, rồi tạo lại nếu không xác định được nguyên nhân.

### 18.2. File missing

Một file thiếu có thể là do backup chưa copy đủ, tablespace không được mount, object bị lifecycle xóa hoặc giải nén sai cấu trúc. Không tạo file rỗng để làm verify pass.

### 18.3. WAL parse error

Xác định segment name, timeline và tool version. Đối chiếu bản WAL archive độc lập nếu có. Một segment hỏng có thể làm backup không thể recover tới trạng thái nhất quán.

### 18.4. Permission error

Chạy verify dưới một account có quyền đọc đúng các directory, kể cả tablespace symlink targets. Không cần cấp quyền write nếu chỉ xác minh.

## 19. pg_verifybackup không chứng minh điều gì?

Dù verify thành công, vẫn cần hiểu giới hạn:

- Không chứng minh backup có thể khởi động trên mọi operating system/architecture.
- Không chứng minh PostgreSQL binary/extension tương thích trên restore host.
- Không chứng minh cấu hình ngoài PGDATA đã được backup.
- Không chứng minh secrets, certificates, service files hoặc scripts ngoài database đã được lưu.
- Không chứng minh WAL archive có đầy đủ mọi segment ngoài range mà backup manifest yêu cầu.
- Không chứng minh PITR tới mọi thời điểm trong retention window nếu chưa kiểm tra archive chain.
- Không chứng minh ứng dụng có thể kết nối hoặc chạy đúng.
- Không chứng minh business data invariants.
- Không đo RTO thực tế.
- Không bảo vệ backup trước actor có quyền sửa cả file và manifest.

### 19.1. PostgreSQL configuration

Các file cấu hình có thể nằm ngoài PGDATA hoặc được quản lý bằng automation/secrets manager. Backup data directory không tự bảo đảm các file đó được sao lưu đúng.

### 19.2. Roles và database objects

Physical base backup chứa cluster data files, nhưng restore runbook vẫn cần hiểu roles, extension binaries, shared libraries, external services và các phụ thuộc môi trường.

### 19.3. Encryption keys

Nếu backup được mã hóa, mất key có thể khiến một backup checksum-perfect vẫn không thể đọc. Backup key material và quy trình key recovery phải được kiểm thử độc lập.

### 19.4. External dependencies

Ứng dụng có thể phụ thuộc object storage, secrets, DNS, certificates, message brokers hoặc service endpoints. Restore database chưa khôi phục các phụ thuộc này.

## 20. Restore test: lớp xác minh quan trọng nhất

Một restore drill chứng minh backup có thể chuyển thành một PostgreSQL instance hoạt động trong môi trường mục tiêu.

### 20.1. Môi trường cô lập

Restore vào VM/container/host riêng:

- Không trỏ tới production primary.
- Dùng port khác.
- Chặn outbound network không cần thiết.
- Không để ứng dụng production tự động kết nối.
- Dùng tablespace path riêng.
- Dùng credentials test.

### 20.2. Chuẩn bị backup

Download backup artifact, xác minh signature/digest, giải mã/giải nén và chạy pg_verifybackup.

### 20.3. Chuẩn bị recovery configuration

Tùy PostgreSQL version và recovery target, chuẩn bị cấu hình:

- restore_command nếu cần WAL archive.
- recovery.signal cho archive recovery/PITR ở các phiên bản hiện đại.
- recovery_target_time/LSN/name khi cần.
- primary_conninfo/standby.signal nếu mục tiêu là standby, không phải độc lập PITR.
- Tablespace mapping và permissions.

Không dùng một cấu hình recovery chung cho mọi loại drill. Một restore test base backup độc lập và một standby bootstrap test có mục tiêu khác nhau.

### 20.4. Khởi động

```bash
pg_ctl -D /restore/lab/pgdata -l /restore/lab/postgres.log start
```

Command minh họa; service manager/container runtime của môi trường có thể khác.

### 20.5. Kiểm tra server

```sql
SELECT version(), pg_is_in_recovery(), current_timestamp;
```

Nếu PITR instance đã promote/hoàn tất recovery, pg_is_in_recovery() thường trả false. Nếu mục tiêu là standby đang replay, nó sẽ trả true. Đọc đúng trạng thái mong đợi của drill.

### 20.6. Kiểm tra database và tables

```sql
SELECT datname
FROM pg_database
ORDER BY datname;

SELECT schemaname, count(*) AS table_count
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
GROUP BY schemaname
ORDER BY schemaname;
```

Các query này chỉ là smoke test ban đầu; cần query nghiệp vụ cụ thể để kiểm tra dữ liệu.

## 21. Kiểm tra ứng dụng và business invariants

Một backup có thể khởi động thành công nhưng dữ liệu vẫn thiếu so với nhu cầu nghiệp vụ.

Ví dụ các kiểm tra:

- Số lượng khách hàng/orders theo khoảng thời gian.
- Tổng số giao dịch theo ngày.
- Tổng tiền theo currency.
- Số foreign key orphan nếu hệ thống có quy tắc kiểm tra riêng.
- Tồn kho không âm nếu đó là invariant.
- Số lượng tenant và dữ liệu phân vùng.
- Các sequence/identity values còn phù hợp.

### 21.1. Row counts

So sánh row counts với baseline hoặc backup metadata, nhưng đừng yêu cầu mọi table phải bằng số liệu live source nếu backup được tạo ở thời điểm khác.

### 21.2. Aggregate checks

Có thể tính tổng, min/max timestamp, counts theo status để phát hiện một số loại thiếu dữ liệu. Chọn kiểm tra dựa trên semantics của domain.

### 21.3. Referential checks

PostgreSQL thường giữ constraint consistency trong physical backup, nhưng application-level references ngoài database hoặc dữ liệu được replicate/ETL riêng cần kiểm tra thêm.

### 21.4. Application smoke test

Khởi chạy một phiên bản ứng dụng cấu hình vào restore host, thực hiện read-only workflows và kiểm tra response. Không cho test app gửi email, thanh toán, webhook hoặc side effects ra production.

### 21.5. Không chạy destructive test trên backup gốc

Tạo bản restore dùng một lần hoặc snapshot clone. Giữ artifact backup bất biến.

## 22. PITR verification khác base backup verification

Base backup verify chứng minh file tree/WAL range được manifest mô tả còn nguyên vẹn. PITR verification còn cần chứng minh archive chain có thể replay tới target.

### 22.1. Kiểm tra archive chain

Đảm bảo base backup hợp lệ, WAL liên tục từ điểm cần thiết, timeline history files có mặt, restore_command truy xuất được segment và encryption/decompression của archive hoạt động.

### 22.2. Restore tới một target time

Trong môi trường cô lập, cấu hình recovery target và khởi động instance. Xác minh server dừng recovery ở target mong muốn hoặc đạt trạng thái tương ứng theo quy trình version.

### 22.3. Kiểm tra dữ liệu trước/sau target

Chọn một transaction marker hoặc business event có thời điểm đã biết. Xác nhận event trước target có mặt và event sau target không có mặt nếu mục tiêu test yêu cầu.

### 22.4. Kiểm tra nhiều thời điểm

Một lần PITR test ở thời điểm gần nhất không chứng minh archive cũ hơn còn nguyên. Chạy định kỳ trên các backup ages khác nhau.

## 23. Đo RTO và RPO trong restore drill

### 23.1. RPO

Recovery Point Objective là mức mất dữ liệu theo thời gian có thể chấp nhận. Với PITR, đo điểm mới nhất có thể khôi phục dựa trên WAL archive thực sự sẵn có.

### 23.2. RTO

Recovery Time Objective là thời gian mục tiêu để đưa hệ thống trở lại hoạt động. Đo từ lúc bắt đầu restore/failover workflow đến khi ứng dụng vượt qua smoke tests.

### 23.3. Các mốc nên ghi

| Mốc | Ý nghĩa |
| --- | --- |
| Backup start/end | Thời gian tạo base backup |
| Upload complete | Artifact đã đến repository |
| Verify complete | pg_verifybackup hoàn tất |
| Download/decrypt complete | Backup sẵn sàng cho restore |
| Restore start/end | Data files được chuẩn bị |
| PostgreSQL ready | Server nhận kết nối |
| Recovery complete | WAL replay đạt target |
| Application ready | Smoke tests thành công |

### 23.4. Không lấy thời gian pg_verifybackup làm RTO

Verify thường chỉ là một bước. Download, decrypt, extract, WAL replay, extension setup và application validation có thể chiếm phần lớn thời gian.

## 24. Kiểm tra backup sau copy và object storage

Một artifact có thể pass verify ở staging nhưng hỏng sau khi upload.

### 24.1. Hai lần kiểm tra

- Verify trước upload: kiểm tra output pg_basebackup.
- Verify sau download: kiểm tra artifact đã đi qua storage/transport.

### 24.2. Object version

Ghi lại immutable object version ID hoặc generation ID để restore đúng phiên bản đã verify. Không chỉ dùng một object key có thể bị overwrite.

### 24.3. Multipart upload

Đảm bảo upload hoàn tất, object size đúng và multipart ETag được hiểu đúng theo provider. ETag không phải lúc nào cũng là content MD5.

### 24.4. Copy giữa regions

Nếu backup được replicate sang region DR, kiểm tra object tại region đích bằng cách download/verify hoặc dùng cơ chế checksum end-to-end đáng tin cậy. Đừng chỉ dựa vào trạng thái replication metadata.

### 24.5. Restore credentials

Backup repository cần được truy cập trong tình huống disaster. Không để restore workflow phụ thuộc duy nhất vào một credential service hoặc region có thể đã mất.

## 25. Kiểm tra tablespaces và external paths

Tablespace data có thể nằm ngoài PGDATA. Một backup manifest/verify chỉ hữu ích nếu toàn bộ các đường dẫn được xử lý đúng.

### 25.1. Inventory tablespaces

```sql
SELECT spcname, pg_tablespace_location(oid) AS location
FROM pg_tablespace
ORDER BY spcname;
```

### 25.2. Lưu mapping

Ghi lại source tablespace path và destination mapping. Restore host có thể dùng path khác, nhưng phải bảo đảm cấu trúc được tái tạo đúng.

### 25.3. Permission và ownership

PostgreSQL service account cần quyền truy cập các tablespace directories. Verify account có thể đọc; restore account cần quyền sở hữu/ghi theo yêu cầu server.

### 25.4. Mount mất

Nếu tablespace mount không có khi restore, server có thể không khởi động hoặc data bị thiếu. Kiểm tra mount/volume trước khi pg_verifybackup và trước restore start.

## 26. Backup manifest và phiên bản PostgreSQL

Manifest có version riêng và gắn với server version/system identifier. Các binary pg_basebackup và pg_verifybackup có thể có thay đổi giữa major versions.

### 26.1. Dùng tool version phù hợp

Ghi lại:

```bash
pg_basebackup --version
pg_verifybackup --version
```

Nên dùng binary cùng major version hoặc version được tài liệu PostgreSQL xác nhận tương thích với backup. WAL parsing đặc biệt cần đúng format.

### 26.2. Không giả định manifest format bất biến

Các trường JSON có thể bổ sung theo major version. Không tự viết parser chỉ đọc một schema cố định rồi loại bỏ các trường không biết.

### 26.3. Backup từ cluster khác

System identifier giúp xác định cluster nguồn. Trước khi restore, đối chiếu metadata để tránh nhầm backup của staging, production hoặc một cluster khác.

### 26.4. Minor version

Minor update thường giữ compatibility trong cùng major series, nhưng extension/binary environment vẫn cần được kiểm tra trong restore test.

## 27. pg_verifybackup trong automation

Một shell pipeline nên dừng nếu backup hoặc verify thất bại:

```bash
set -euo pipefail
BACKUP_DIR="/backup/staging/base_20261114T020000Z"
mkdir -p "$BACKUP_DIR"
pg_basebackup --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --pgdata="$BACKUP_DIR" --format=plain --wal-method=stream --manifest-checksums=SHA256 --progress
pg_verifybackup --progress "$BACKUP_DIR"
```

Đây là ví dụ Bash. Quản lý credentials qua .pgpass/secret manager; không export password vào command line hoặc log.

### 27.1. Exit status

Chỉ đánh dấu backup verified nếu pg_basebackup exit code thành công, manifest tồn tại và có thể đọc, pg_verifybackup exit code bằng 0 và metadata backup được ghi bền vững.

### 27.2. Không bỏ qua lỗi qua pipe

Nếu pipeline có pipe như pg_basebackup | tee, dùng set -o pipefail để exit status của command upstream không bị che bởi tee.

### 27.3. Atomic promotion

Tạo backup trong staging directory có tên riêng. Chỉ sau khi verify thành công mới chuyển trạng thái/metadata sang verified hoặc publish path bất biến. Tránh để consumer restore nhìn thấy backup đang tạo dở.

### 27.4. Không tái sử dụng directory cũ

Mỗi lần backup dùng directory/object ID mới. Nếu dùng lại directory, file thừa từ lần trước có thể gây nhầm lẫn và verification failures.

## 28. Ghi nhận verification result

Mỗi lần verify nên tạo một record bất biến hoặc append-only:

| Field | Ví dụ |
| --- | --- |
| backup_id | pg-prod-a-20261114T020000Z |
| cluster_system_id | System identifier từ backup metadata |
| source_version | PostgreSQL major/minor |
| backup_tool_version | pg_basebackup version |
| verify_tool_version | pg_verifybackup version |
| manifest_digest | SHA256 của manifest |
| checksum_algorithm | SHA256 |
| wal_method | stream |
| backup_started_at | UTC timestamp |
| backup_completed_at | UTC timestamp |
| verified_at | UTC timestamp |
| verify_status | VERIFIED / FAILED |
| restore_test_status | PASSED / FAILED / NOT_RUN |
| restore_duration | Seconds |
| restore_target | Host/isolated environment ID |
| artifact_version | Immutable object version |

### 28.1. Tách verify status và restore status

Không gộp hai trạng thái:

- VERIFIED: pg_verifybackup thành công.
- RESTORE_TESTED: backup đã được restore và test thành công.

Một backup có thể verified nhưng chưa từng restore-tested.

### 28.2. Ghi failure details

Lưu command, tool version, exit status, stderr, failed file path, WAL segment và thời điểm. Hạn chế log secrets/credentials.

### 28.3. Không ghi VERIFIED trước khi command kết thúc

Nếu process bị timeout hoặc agent mất kết nối, trạng thái cần là UNKNOWN/IN_PROGRESS cho đến khi xác nhận process result.

## 29. Tần suất xác minh

Một policy thường chia nhiều lớp:

- Verify mỗi backup sau khi tạo.
- Verify lại sau khi upload/replicate tới repository.
- Restore test định kỳ.
- PITR drill định kỳ tới nhiều target times.
- Restore test trước major upgrade hoặc thay đổi backup tooling.

Tần suất cụ thể phụ thuộc RPO/RTO, dữ liệu, chi phí restore và yêu cầu compliance.

### 29.1. Verify mọi backup

pg_verifybackup thường rẻ hơn restore full cluster, nên có thể chạy cho từng artifact nếu resource budget cho phép.

### 29.2. Restore drill lấy mẫu có chủ đích

Không nhất thiết restore mọi backup nếu chi phí lớn, nhưng phải có sampling policy bao phủ backup mới/cũ, region, storage class, encryption key và backup method.

### 29.3. Sau thay đổi hệ thống

Chạy restore drill khi thay PostgreSQL major version, backup agent hoặc pg_basebackup binary, compression/encryption format, object storage provider/region, tablespace layout, WAL archive/restore scripts hoặc KMS/key rotation.

## 30. Kiểm tra retention và khả năng restore lịch sử

Backup có thể pass verify hôm nay nhưng bị xóa ngày mai do lifecycle policy sai.

### 30.1. Retention chain

Lập danh sách base backups còn được giữ và WAL ranges cần thiết cho từng backup/PITR window.

### 30.2. WAL archive cleanup

Không xóa WAL chỉ vì một standby đã replay xong. WAL có thể còn cần cho base backup cũ, PITR hoặc disaster recovery region.

### 30.3. Object lifecycle

Kiểm tra expiration, transition, legal hold, object lock và version deletion. Một policy phải giữ cả base backup và WAL cần thiết.

### 30.4. Restore point coverage

Kiểm tra khả năng khôi phục tại các thời điểm trong retention window, không chỉ ở thời điểm gần nhất.

## 31. Troubleshooting: manifest không tồn tại

Nguyên nhân:

- Backup tạo bằng --no-manifest.
- Backup được tạo bằng công cụ/phiên bản không hỗ trợ manifest.
- Manifest nằm ở vị trí khác.
- Manifest bị bỏ khi đóng gói hoặc copy.
- Backup directory sai.

Hướng xử lý:

1. Kiểm tra command tạo backup và tool version.
2. Tìm manifest trong artifact/package theo layout đã biết.
3. Nếu không có manifest, không thể dùng pg_verifybackup theo workflow manifest thông thường.
4. Tạo lại backup có manifest hoặc dùng cơ chế verification phù hợp của backup tool.

Không tự tạo manifest rỗng để làm cho pg_verifybackup chạy được.

## 32. Troubleshooting: checksum mismatch

Một file có checksum khác manifest có thể do lỗi copy/upload/download, storage corruption, file bị sửa sau backup, quá trình giải nén/giải mã lỗi, manifest thuộc backup khác hoặc tool/format compatibility issue.

Quy trình:

1. Ghi nhận file path và checksum algorithm.
2. So manifest digest với bản đã ký/lưu độc lập.
3. Kiểm tra object version và transfer logs.
4. So với bản staging đã verify trước upload nếu còn.
5. Tải lại object vào staging mới.
6. Verify lại.
7. Nếu mismatch vẫn tồn tại, đánh dấu backup FAILED và tạo backup mới.

Không sửa manifest checksum để khớp file hỏng.

## 33. Troubleshooting: WAL range không đầy đủ

Nguyên nhân có thể:

- Backup dùng wal_method=none nhưng archive không được cung cấp.
- -X fetch không lấy được segment vì primary đã recycle.
- WAL directory riêng chưa được mount/copy.
- Archive cleanup xóa segment còn cần.
- Timeline history file bị thiếu.
- Segment hỏng hoặc không tương thích.

Hướng xử lý:

1. Đọc WAL range trong manifest.
2. Xác định segment đầu/cuối và timeline.
3. Tìm trong backup pg_wal và archive repository.
4. Kiểm tra archive catalog/backup tool metadata.
5. Khôi phục đúng segments vào staging WAL directory.
6. Chạy lại pg_verifybackup.
7. Thực hiện restore test nếu WAL chain đã được xác minh.

## 34. Troubleshooting: pg_verifybackup thành công nhưng restore thất bại

Đây là lý do không được đồng nhất verify với restore.

Các nguyên nhân:

- PostgreSQL binary/extension không tương thích.
- Tablespace path hoặc mount sai.
- restore_command lỗi.
- WAL archive thiếu segment ngoài phần đã verify.
- Recovery target cấu hình sai.
- Quyền file hoặc owner không đúng.
- postgresql.conf/external config thiếu.
- Encryption key hoặc certificate không truy cập được.
- Storage/architecture có khác biệt.

Hướng xử lý:

1. Đọc PostgreSQL startup/recovery logs.
2. Xác định lỗi xảy ra trước recovery, trong WAL replay hay sau startup.
3. Kiểm tra version, extension và shared libraries.
4. Kiểm tra tablespaces, permissions và mounts.
5. Kiểm tra archive fetch và timeline.
6. Kiểm tra recovery settings.
7. Ghi lại RTO impact và sửa restore runbook.

## 35. Backup verification và logical backups

pg_verifybackup được thiết kế cho physical base backups có manifest theo workflow PostgreSQL. Nó không phải công cụ xác minh mọi loại backup.

### 35.1. pg_dump

pg_dump tạo logical dump. Các file dump không có backup_manifest theo cấu trúc physical backup.

### 35.2. pg_restore

Với custom/directory/tar dump, cần kiểm tra archive format bằng công cụ tương ứng, rồi restore thử vào database mới. Ví dụ:

```bash
pg_restore --list /backup/logical/app.dump
```

Lệnh này liệt kê archive entries; nó không chứng minh restore thành công. Cần thực hiện pg_restore vào database test.

### 35.3. SQL dump

Với plain SQL dump, có thể kiểm tra file digest, gzip integrity nếu nén, rồi chạy psql vào database lab. Một lần restore thực tế là lớp kiểm chứng mạnh hơn việc chỉ kiểm tra file có tồn tại.

### 35.4. Backup manager

Nếu dùng Barman, pgBackRest hoặc một công cụ backup khác, dùng verify/check commands của công cụ đó và kết hợp restore test. Không giả định pg_verifybackup có thể thay thế toàn bộ metadata/index của backup manager.

## 36. So sánh các lớp xác minh

| Lớp | Phát hiện | Không chứng minh |
| --- | --- | --- |
| File exists/size | File thiếu hoặc truncate | Bytes đúng |
| Manifest checksum | File bytes khác manifest | Manifest đáng tin nếu có thể bị sửa |
| Manifest signature | Nguồn gốc/integrity metadata theo key | Restore thành công |
| WAL parse | Một số lỗi cấu trúc WAL | Recovery tới mọi target |
| pg_verifybackup | File tree và WAL trong phạm vi tool | Business correctness/RTO |
| Restore test | Server có thể khởi động/recover trong môi trường test | Mọi workflow production đều đúng |
| Application tests | Các luồng nghiệp vụ được chọn hoạt động | Mọi dữ liệu/business rule |
| PITR drill | Khôi phục tới target đã thử | Tất cả target trong mọi thời điểm |

Một quy trình trưởng thành dùng nhiều lớp phù hợp với rủi ro, không dựa vào một trạng thái xanh duy nhất.

## 37. Checklist vận hành cho backup manifest

### Khi tạo backup

- [ ] pg_basebackup version phù hợp với PostgreSQL server.
- [ ] Backup directory mới và rỗng.
- [ ] Manifest được tạo, không dùng --no-manifest ngoài chủ đích.
- [ ] Checksum algorithm được ghi nhận.
- [ ] WAL method phù hợp với recovery design.
- [ ] Tablespaces được map/backup đầy đủ.
- [ ] Exit code và logs được lưu.

### Khi verify

- [ ] pg_verifybackup version phù hợp.
- [ ] Manifest đúng backup ID.
- [ ] Tất cả file paths được đọc.
- [ ] Checksum được kiểm tra.
- [ ] WAL directory/segments cần thiết có mặt.
- [ ] WAL parse không bị skip nếu mục tiêu cần kiểm tra đầy đủ.
- [ ] Exit status bằng 0.
- [ ] Báo cáo verify được lưu.

### Khi lưu repository

- [ ] Backup artifact có unique immutable ID/version.
- [ ] Manifest digest/signature được lưu độc lập.
- [ ] Encryption key và restore credentials có thể truy cập trong DR.
- [ ] Object size/checksum/version metadata được ghi.
- [ ] Backup được verify lại sau copy/upload.
- [ ] Retention không xóa base backup/WAL còn cần.

### Khi restore drill

- [ ] Restore vào môi trường cô lập.
- [ ] Tablespaces và external dependencies đã chuẩn bị.
- [ ] PostgreSQL/extension versions phù hợp.
- [ ] WAL archive/recovery target được cấu hình đúng.
- [ ] Server khởi động và recovery hoàn tất.
- [ ] Query smoke tests thành công.
- [ ] Business invariants được kiểm tra.
- [ ] RTO/RPO được đo.

## 38. Bài tập thực hành PostgreSQL

Thực hiện trên lab/staging và repository giả lập. Không cố tình sửa hoặc xóa backup production để thử lỗi.

1. **Manifest:** giải thích vai trò của backup_manifest.
2. **Manifest path:** tìm vị trí manifest trong plain-format backup.
3. **JSON:** đọc các nhóm metadata trong manifest.
4. **System identifier:** giải thích vì sao cần ghi nhận cluster source.
5. **File list:** xác định một file path, size và checksum entry.
6. **WAL range:** mô tả vì sao manifest cần ghi WAL ranges.
7. **Checksum:** phân biệt CRC32C và SHA256.
8. **Security:** giải thích checksum khác chữ ký số như thế nào.
9. **Base backup:** tạo một backup plain-format có manifest.
10. **Checksum option:** tạo backup với SHA256 nếu phiên bản hỗ trợ.
11. **No manifest:** giải thích hệ quả khi dùng --no-manifest.
12. **Verify:** chạy pg_verifybackup trên backup vừa tạo.
13. **Progress:** chạy verify với --progress.
14. **Version:** đọc pg_basebackup và pg_verifybackup versions.
15. **Help:** dùng --help để liệt kê options của binary hiện tại.
16. **Plain format:** giải thích vì sao directory tree tiện cho verification.
17. **Tar format:** xây dựng workflow extract-to-staging trước khi verify.
18. **WAL stream:** tạo backup bằng -X stream và kiểm tra WAL files.
19. **WAL fetch:** giải thích retention cần thiết khi dùng -X fetch.
20. **WAL none:** mô tả archive requirement khi dùng -X none.
21. **Missing file:** tạo bản copy lab thiếu một file và quan sát verify failure.
22. **Truncate:** truncate một file trong bản sao lab và đọc lỗi.
23. **Checksum mismatch:** thay đổi bytes mà giữ size rồi chạy verify.
24. **Unexpected file:** thêm một file thử nghiệm và quan sát tool xử lý.
25. **Manifest missing:** di chuyển manifest trong bản lab và đọc lỗi.
26. **Manifest path:** dùng --manifest-path để trỏ tới manifest đúng.
27. **WAL directory:** thử --wal-directory với WAL được lưu riêng.
28. **WAL parse:** chạy verify mặc định và giải thích lớp parse.
29. **No parse:** dùng --no-parse-wal và mô tả coverage bị giảm.
30. **Skip checksum:** dùng --skip-checksums trên bản lab và giải thích vì sao không thể đánh dấu verified đầy đủ.
31. **Exit status:** viết script fail khi pg_verifybackup trả non-zero.
32. **Fail fast:** thử --exit-on-error và so output với default behavior.
33. **Tablespaces:** tạo tablespace lab và backup cluster có tablespace.
34. **Mapping:** dùng tablespace mapping và ghi lại path.
35. **Symlink:** kiểm tra pg_tblspc và target directories.
36. **Permission:** chạy verify dưới user chỉ có quyền read.
37. **File integrity:** so manifest checksum với digest độc lập.
38. **Manifest signature:** thiết kế quy trình ký manifest bằng key ngoài backup.
39. **Tampering:** giải thích vì sao sửa file và manifest cùng lúc có thể qua checksum check.
40. **Immutable storage:** thiết kế object lock/versioning cho backup artifacts.
41. **Compression:** nén backup rồi giải nén vào staging và verify.
42. **Encryption:** mã hóa artifact, giải mã và verify file tree.
43. **Transport:** copy backup sang host khác rồi verify sau download.
44. **Object version:** ghi lại object version ID của backup đã verified.
45. **WAL range:** xác định segments cần thiết từ manifest.
46. **Timeline:** giải thích vì sao timeline history có thể quan trọng cho restore.
47. **pg_waldump:** dùng công cụ phù hợp để xem WAL records trên lab.
48. **Tool compatibility:** thử giải thích rủi ro dùng binary khác major version.
49. **Page checksums:** phân biệt manifest checksum với data page checksum.
50. **pg_checksums:** nghiên cứu điều kiện chạy offline check.
51. **Restore:** restore backup vào một PGDATA lab mới.
52. **Startup:** kiểm tra PostgreSQL start thành công từ backup.
53. **Recovery:** quan sát log và trạng thái pg_is_in_recovery().
54. **PITR:** restore tới một recovery_target_time trong lab.
55. **WAL archive:** kiểm tra restore_command lấy segment từ archive.
56. **Missing WAL:** mô phỏng thiếu WAL trong lab và quan sát recovery failure.
57. **Application test:** chạy một smoke test read-only trên restored database.
58. **Business invariant:** chọn aggregate để xác minh dữ liệu.
59. **Sequence:** kiểm tra sequence values sau restore.
60. **Extensions:** xác minh extension binaries có mặt trên restore host.
61. **External config:** lập danh sách config/secrets không nằm trong PGDATA.
62. **Tablespace restore:** restore vào path mapping khác.
63. **RTO:** đo thời gian download, extract, verify, restore và startup.
64. **RPO:** xác định WAL archive mới nhất có thể phục hồi.
65. **Restore drill:** viết runbook restore hoàn chỉnh.
66. **Backup metadata:** thiết kế record backup_id, system_id, version và manifest digest.
67. **Verify status:** tách VERIFIED khỏi RESTORE_TESTED.
68. **Automation:** viết shell pipeline có set -euo pipefail.
69. **Pipe status:** giải thích vai trò pipefail khi dùng tee.
70. **Atomic promotion:** chỉ publish backup sau khi verify thành công.
71. **Retry:** thiết kế retry không ghi đè artifact đã verified.
72. **Archive format:** phân biệt pg_verifybackup với pg_restore --list.
73. **Logical dump:** lập cách verify pg_dump bằng restore test.
74. **Backup manager:** nghiên cứu verify/restore checks của Barman hoặc pgBackRest.
75. **Retention:** xác định WAL archive cần giữ cho các base backup đang còn.
76. **Monitoring:** tạo dashboard verify success/failure và backup age.
77. **Alert:** cảnh báo backup mới nhất chưa được verify.
78. **Region DR:** download và verify backup tại region dự phòng.
79. **Key recovery:** diễn tập lấy encryption/signing key trong DR.
80. **Thiết kế tổng hợp:** xây pipeline base backup, manifest signature, upload immutable, destination verification, PITR restore drill, business smoke tests, RTO/RPO metrics và retention cho PostgreSQL production.

## 39. Anti-pattern thường gặp

| Anti-pattern | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Chỉ nhìn pg_basebackup exit code | Không kiểm tra file sau copy | Chạy pg_verifybackup |
| Dùng --no-manifest mà vẫn gọi pg_verifybackup | Không có metadata để đối chiếu | Tạo backup có manifest |
| Tin checksum là chữ ký | Manifest có thể bị thay cùng data | Ký/lưu digest độc lập |
| Chỉ verify staging | Không phát hiện lỗi upload/storage | Verify lại sau download |
| Dùng --skip-checksums để pass pipeline | Bỏ lớp kiểm tra bytes | Đánh dấu coverage giảm và điều tra |
| Luôn dùng --no-parse-wal | Không kiểm tra cấu trúc WAL | Parse WAL theo policy |
| Verify chỉ PGDATA nhưng bỏ tablespaces | Bỏ sót data files | Verify đầy đủ backup layout |
| Dùng binary khác major version tùy tiện | WAL/manifest không tương thích | Dùng tool phù hợp |
| Nghĩ pg_verifybackup chứng minh restore | Có thể vẫn fail khi recovery | Restore drill |
| Nghĩ verify chứng minh business correctness | Dữ liệu nghiệp vụ có thể sai/thiếu | Business validation |
| Không lưu manifest | Mất căn cứ verify sau này | Lưu cùng backup |
| Ghi đè backup path cũ | Mất artifact đã verified | Unique immutable backup ID |
| Copy thiếu WAL khi dùng -X none | Backup không hoàn tất recovery | Lưu archive WAL chain |
| Không kiểm tra encryption key | Backup không giải mã được | Key recovery drill |
| Restore trên production | Gây rủi ro dữ liệu/side effects | Restore vào môi trường cô lập |
| Không test tablespace mount | Server không start | Kiểm tra mapping/volume |
| Chỉ test startup | Không biết app hoạt động | Smoke tests và invariants |
| Gộp VERIFIED với RESTORE_TESTED | Báo cáo quá mức | Tách hai trạng thái |
| Không đo RTO/RPO | Không biết đạt SLA | Ghi thời gian và recovery point |
| Xóa WAL archive theo standby hiện tại | Phá PITR | Retention theo backup catalog |

## 40. Checklist xác minh bản sao lưu

### Artifact và manifest

- [ ] Backup ID và source cluster được xác định.
- [ ] Manifest tồn tại và thuộc đúng backup.
- [ ] Manifest digest/signature được xác minh nếu policy yêu cầu.
- [ ] Tool versions và checksum algorithm được ghi nhận.
- [ ] Backup tree và tablespaces có đầy đủ.

### pg_verifybackup

- [ ] Chạy trên artifact đã hoàn tất copy/upload.
- [ ] File presence và size checks thành công.
- [ ] Checksum verification được bật.
- [ ] WAL range có đủ segment cần thiết.
- [ ] WAL parse được thực hiện theo policy.
- [ ] Exit status bằng 0.
- [ ] Output/report được lưu.

### Restore

- [ ] Có base backup và WAL archive path phù hợp.
- [ ] Restore vào môi trường cô lập.
- [ ] PostgreSQL version/extensions/tablespaces phù hợp.
- [ ] Server start/recovery thành công.
- [ ] Query smoke tests thành công.
- [ ] Business invariants được kiểm tra.
- [ ] RTO/RPO được đo.

### Lifecycle

- [ ] Artifact có immutable version.
- [ ] Backup và WAL retention đồng bộ với PITR policy.
- [ ] Encryption/signing keys có DR access path.
- [ ] Restore drill được lên lịch và ghi kết quả.
- [ ] Alert khi backup chưa verify hoặc restore test quá hạn.

## 41. Tổng kết

Backup manifest và pg_verifybackup cung cấp một lớp kiểm tra quan trọng cho physical base backup PostgreSQL:

```text
pg_basebackup
    |
    +--> Data files
    |
    +--> WAL cần thiết
    |
    +--> backup_manifest
              |
              v
       pg_verifybackup
              |
              v
       File / size / checksum / WAL checks
              |
              v
       Restore drill + PITR + app tests
```

Những nguyên tắc quan trọng:

- **Manifest mô tả backup**, gồm file entries, kích thước, checksum và WAL ranges; nó không thay thế data files hoặc WAL.
- **pg_verifybackup xác minh nội dung file tree và WAL trong phạm vi hỗ trợ.** Dùng binary phù hợp với phiên bản và đọc kỹ tùy chọn làm giảm coverage.
- **Checksum không phải chữ ký số.** Bảo vệ manifest bằng digest/signature độc lập, quyền hạn và immutable storage.
- **WAL là một phần của tính nhất quán và recovery.** Backup không kèm WAL cần có archive/recovery path đầy đủ.
- **Tablespaces và các file ngoài PGDATA phải được tính đến.** Verify đúng toàn bộ layout và mapping.
- **Verified không đồng nghĩa restore-tested.** Chỉ restore drill mới kiểm tra được quy trình khởi động, WAL replay, extension, tablespace và cấu hình.
- **Restore thành công chưa đồng nghĩa ứng dụng đúng.** Chạy business checks, smoke tests và đo RTO/RPO.
- **Verify lại sau khi upload/copy.** Một lần verify ở staging không chứng minh object tại DR region còn nguyên vẹn.
- **Giữ backup và WAL theo cùng recovery policy.** Cleanup sai có thể khiến base backup còn đó nhưng không thể PITR.

Một hệ thống backup đáng tin cậy không chỉ tạo ra file thành công. Nó phải chứng minh được artifact còn nguyên vẹn, có đủ WAL, có thể restore trong môi trường mục tiêu và đáp ứng thời gian phục hồi mà tổ chức cam kết.

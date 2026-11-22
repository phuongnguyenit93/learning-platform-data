# RMAN repository, control file và recovery catalog

Recovery Manager (RMAN) là công cụ của Oracle Database dùng để sao lưu, phục hồi và quản lý vòng đời backup. Khi RMAN thực hiện một lệnh backup hoặc restore, nó cần biết database có những datafile nào, backup nào đã được tạo, backup piece nằm ở đâu, archived redo log nào có sẵn và database đang ở incarnation nào. Tập hợp metadata đó được gọi là **RMAN repository**.

RMAN repository có thể được lưu trong control file của database đích hoặc trong một recovery catalog đặt ở database khác. Control file luôn là thành phần cốt lõi của database và có thể lưu repository mà không cần cài recovery catalog. Recovery catalog là kho metadata bổ sung, hữu ích khi cần lưu lịch sử lâu hơn, quản lý nhiều database tập trung hoặc sử dụng stored script.

Điều quan trọng là phân biệt metadata với dữ liệu backup. Repository ghi nhận backup đã được tạo và vị trí của nó; các block dữ liệu thực tế vẫn nằm trong backup piece trên disk, tape hoặc thiết bị lưu trữ tương ứng. Có repository mà không còn backup piece thì không thể khôi phục dữ liệu từ backup đó. Ngược lại, backup piece còn tồn tại nhưng metadata bị mất vẫn có thể được đưa trở lại repository bằng các lệnh `CATALOG` trong những trường hợp phù hợp.

## 1. RMAN repository lưu những thông tin gì?

Repository là nguồn thông tin RMAN dùng để lập kế hoạch và thực hiện backup, restore, recover cũng như kiểm tra trạng thái các bản sao lưu. Metadata thường bao gồm:

- Database identity như DBID, tên database và thông tin incarnation.
- Cấu trúc database: datafile, tablespace, control file và redo log liên quan đến quá trình backup/recovery.
- Backup set, backup piece, image copy, loại backup, tag, thời điểm bắt đầu/kết thúc và trạng thái của backup.
- Datafile và archived redo log đã được backup, checkpoint SCN và các thông tin cần để xác định khả năng phục hồi.
- Vị trí, tên handle và loại thiết bị chứa backup piece.
- RMAN persistent configuration như retention policy, default device type, channel, compression, encryption và control file autobackup.
- Các thay đổi cấu trúc database và thông tin cần để theo dõi backup qua những lần thay đổi đó.

Một số metadata có vòng đời và cách lưu khác nhau tùy repository đang dùng. Control file có các record section với khả năng tái sử dụng; recovery catalog có thể giữ lịch sử dài hơn và lưu thông tin tập trung cho nhiều target database.

### Repository không phải là nơi chứa nội dung backup

Ví dụ một lệnh:

```rman
BACKUP DATABASE PLUS ARCHIVELOG;
```

RMAN đọc cấu trúc database, tạo backup set/piece trên thiết bị được cấu hình, rồi ghi metadata mô tả kết quả vào repository. Repository có thể cho biết backup piece có handle nào, thuộc backup set nào và được tạo lúc nào. Các block của datafile và archived redo log được lưu trong backup piece, không được nhúng toàn bộ vào control file hay recovery catalog.

Vì vậy cần bảo vệ đồng thời ba lớp:

1. **Backup data**: backup piece, image copy và archived redo log trên thiết bị lưu trữ.
2. **Control file**: chứa cấu trúc database và RMAN repository cục bộ, đồng thời rất quan trọng cho mount, restore và recovery.
3. **Recovery catalog (nếu sử dụng)**: giữ metadata bổ sung ở database riêng và cần có kế hoạch backup/recovery riêng.

## 2. Hai nơi lưu RMAN repository

```text
                         RMAN client
                              |
                    target connection
                              |
                              v
                     Target database
                              |
                    +---------+---------+
                    |                   |
                    v                   v
             Control file          Datafiles / redo
             RMAN repository       Database contents
                    |
                    | resynchronization
                    v
             Recovery catalog database
             (optional, separate DB)
                    |
                    v
             Catalog schema / RC_* metadata

Backup data files are stored separately on disk, tape or another device.
```

### 2.1. Control file repository

Khi RMAN kết nối target database mà không chỉ định recovery catalog, RMAN sử dụng control file của target làm repository. Đây là chế độ thường được gọi là **NOCATALOG**.

Control file lưu các record về backup, archived redo log, cấu trúc database và RMAN configuration. Khi RMAN tạo backup, các record tương ứng được ghi vào control file. Khi thực hiện restore, RMAN đọc metadata này để tìm backup phù hợp và xác định các bước tiếp theo.

Ưu điểm:

- Không cần triển khai thêm một database chỉ để lưu RMAN metadata.
- Cấu hình và vận hành đơn giản; RMAN có thể backup/restore trực tiếp dựa trên control file.
- Phù hợp với database đơn lẻ hoặc môi trường không cần lưu lịch sử RMAN tập trung trong thời gian dài.

Giới hạn:

- Dung lượng record trong control file có giới hạn và một số record có thể được tái sử dụng theo cơ chế quản lý của control file.
- Lịch sử backup cũ có thể không còn đầy đủ nếu record đã bị ghi đè hoặc bị xóa khỏi repository.
- Nếu mất toàn bộ control file và không có recovery catalog, việc tìm backup để khôi phục phụ thuộc nhiều vào control file autobackup, DBID và thông tin backup còn có thể truy cập.
- Không có một kho trung tâm thuận tiện để quản lý metadata của nhiều target database.

### 2.2. Recovery catalog repository

Recovery catalog là một schema chuyên dụng nằm trong một Oracle Database khác với target database. Schema này chứa các bảng, view và metadata RMAN. RMAN kết nối đồng thời tới target database và catalog database để ghi nhận, truy vấn và đồng bộ repository.

Recovery catalog thường hữu ích khi:

- Cần lưu lịch sử backup dài hơn khoảng record có thể được giữ trong control file.
- Quản lý backup của nhiều target database từ một nơi.
- Muốn có báo cáo tập trung về backup, archived log, incarnation và cấu hình RMAN.
- Cần dùng stored script được lưu trong recovery catalog.
- Cần thêm một nguồn metadata hỗ trợ khi control file của target bị mất hoặc hư hỏng.

Recovery catalog không chứa datafile hay backup piece. Nó lưu metadata về những bản backup và vị trí của chúng. Khi khôi phục, RMAN vẫn cần truy cập backup data thực tế và vẫn cần control file phù hợp để mount database và thực hiện recovery.

### 2.3. Có thể dùng RMAN mà không có recovery catalog

Recovery catalog là tùy chọn. Một database có thể dùng RMAN ở chế độ NOCATALOG và lưu metadata trong control file. Nếu sau này triển khai recovery catalog, có thể tạo catalog, kết nối cả target lẫn catalog rồi đăng ký database để đồng bộ metadata.

Việc dùng recovery catalog không làm control file trở nên không cần thiết. Control file vẫn được Oracle sử dụng khi vận hành database và vẫn là một thành phần quan trọng của quá trình restore/recovery. Recovery catalog chỉ bổ sung một nơi lưu metadata độc lập.

## 3. Control file và vai trò đối với RMAN

Control file là file nhị phân nhỏ nhưng thiết yếu của Oracle Database. Nó lưu metadata mô tả cấu trúc database và trạng thái cần thiết để Oracle mount, mở và phục hồi database.

Một số thông tin quan trọng trong control file:

- Database name, DBID và thông tin tạo database.
- Tên và vị trí datafile, online redo log file.
- Checkpoint và thông tin đồng bộ cần thiết cho instance recovery/media recovery.
- Thông tin về backup, archived redo log và các record của RMAN repository.
- Thông tin liên quan đến database incarnation và một số thay đổi cấu trúc.

Nếu tất cả bản control file đều bị mất, database không thể mount theo cách thông thường cho đến khi control file được khôi phục hoặc tạo lại theo quy trình phù hợp. Vì vậy control file cần được multiplex, backup và lưu trên thiết bị độc lập với các file database chính khi có thể.

### 3.1. Kiểm tra control file đang sử dụng

```sql
SHOW PARAMETER control_files;

SELECT name, status
FROM v$controlfile;
```

`CONTROL_FILES` cho biết danh sách đường dẫn control file mà instance sử dụng. Oracle duy trì các bản multiplexed control file với nội dung đồng nhất. Khi ghi control file, Oracle ghi tới các bản được cấu hình; mất một bản có thể xử lý bằng cách khôi phục bản sao còn tốt theo quy trình vận hành, nhưng không nên coi multiplexing là thay thế cho backup.

### 3.2. Control file autobackup

RMAN có thể tự động backup control file. Khi bật tính năng này, RMAN tạo control file autobackup theo quy tắc của nó sau các hoạt động backup và các thay đổi cấu trúc database phù hợp. Nếu database sử dụng SPFILE, autobackup còn có thể chứa SPFILE để hỗ trợ khởi động lại instance khi mất cả cấu hình khởi động.

Bật control file autobackup:

```rman
CONFIGURE CONTROLFILE AUTOBACKUP ON;
```

Có thể chỉ định format cho autobackup trên disk:

```rman
CONFIGURE CONTROLFILE AUTOBACKUP FORMAT FOR DEVICE TYPE DISK
  TO '/backup/oracle/%F';
```

`%F` là chuỗi thay thế có định dạng nhận diện control file autobackup, bao gồm DBID và thông tin sequence theo quy ước của RMAN. Đường dẫn trên chỉ là ví dụ; cần chọn nơi lưu thực tế, bảo đảm quyền ghi, dung lượng và khả năng truy cập khi disaster recovery.

Có thể tạo backup control file rõ ràng:

```rman
BACKUP CURRENT CONTROLFILE;
```

Control file autobackup đặc biệt hữu ích trong tình huống mất control file khi không thể mount database. Nếu dùng NOCATALOG, RMAN có thể cần DBID để tìm autobackup khi chưa có control file và chưa kết nối catalog.

### 3.3. `CONTROL_FILE_RECORD_KEEP_TIME`

Control file có những record section dùng để lưu thông tin backup và archived log. Một số section có cơ chế circular reuse: record cũ có thể được tái sử dụng khi không gian cần thiết. Tham số `CONTROL_FILE_RECORD_KEEP_TIME` đặt số ngày tối thiểu mà Oracle cố gắng giữ các record có thể tái sử dụng trước khi chúng đủ điều kiện bị ghi đè.

Kiểm tra tham số:

```sql
SHOW PARAMETER control_file_record_keep_time;
```

Không nên hiểu tham số này là retention policy của RMAN hoặc cam kết rằng mọi record chắc chắn tồn tại đúng số ngày đã cấu hình. Nó điều khiển vòng đời record trong control file; retention policy quyết định backup nào cần được giữ để đáp ứng yêu cầu phục hồi. Hai cơ chế có mục đích khác nhau.

Nếu dùng recovery catalog, metadata được resynchronize sang catalog có thể tiếp tục được lưu ở đó ngay cả khi record cũ trong control file sau này được tái sử dụng. Điều này là một lý do recovery catalog hữu ích cho lịch sử dài hạn. Tuy nhiên, catalog phải được đồng bộ và backup đúng cách.

Có thể xem tình trạng các record section:

```sql
SELECT
    type,
    record_size,
    records_total,
    records_used,
    first_index,
    last_index
FROM v$controlfile_record_section
ORDER BY type;
```

Đặc biệt chú ý các section liên quan đến backup và archived log khi điều tra vì sao metadata cũ không còn trong control file.

### 3.4. Snapshot control file

Snapshot control file là bản sao control file nhất quán mà RMAN sử dụng trong một số thao tác backup để đọc metadata mà không bị ảnh hưởng bởi các thay đổi đồng thời lên control file đang hoạt động. Đây là khái niệm khác với control file autobackup.

- **Snapshot control file**: bản sao làm việc phục vụ quá trình RMAN đọc metadata nhất quán.
- **Control file autobackup**: bản backup control file được lưu để có thể restore khi cần.
- **Control file hiện hành**: file Oracle dùng để mount và vận hành database.

Không được nhầm snapshot control file với một bản backup độc lập có thể thay thế chiến lược bảo vệ control file.

## 4. Recovery catalog: thành phần và lợi ích

### 4.1. Cấu trúc triển khai

Một triển khai recovery catalog thường có:

1. Một Oracle Database riêng để lưu catalog schema.
2. Một database user/schema chuyên dụng làm owner của recovery catalog.
3. Tablespace và quota phù hợp cho schema catalog.
4. Kết nối mạng và Oracle Net service từ RMAN client tới catalog database.
5. Kết nối từ RMAN client tới target database.

Nên tách catalog database khỏi target database để metadata không phụ thuộc hoàn toàn vào chính database đang được bảo vệ. Catalog database cũng cần có chiến lược backup, bảo mật, giám sát và kiểm thử khôi phục riêng.

Không nên dùng schema ứng dụng thông thường làm owner của recovery catalog. Hãy tạo user chuyên dụng, giới hạn quyền truy cập và bảo vệ thông tin xác thực của catalog như một tài sản vận hành quan trọng.

### 4.2. Metadata tập trung cho nhiều target database

Một recovery catalog có thể quản lý metadata của nhiều database đã đăng ký. Mỗi database được nhận diện bằng DBID; với môi trường Data Guard hoặc các cấu hình nhiều database liên quan, cần quản lý thêm thông tin định danh như `DB_UNIQUE_NAME` theo cấu hình và phiên bản Oracle.

Mô hình tập trung giúp DBA có thể xem backup của nhiều database qua cùng một catalog, lập báo cáo và áp dụng quy trình vận hành thống nhất. Tuy nhiên, quyền và chính sách retention vẫn cần được thiết kế phù hợp cho từng database.

### 4.3. Lịch sử lâu dài và stored script

Control file có giới hạn về record và có thể tái sử dụng record cũ. Recovery catalog được lưu trong các bảng của database catalog nên thích hợp để giữ metadata trong thời gian dài hơn, miễn là catalog được resynchronize và dung lượng được quản lý phù hợp.

Recovery catalog cũng hỗ trợ stored script của RMAN. Ví dụ, có thể lưu một script backup dùng chung để DBA chạy theo lịch vận hành. Nếu không dùng recovery catalog, có thể lưu lệnh RMAN trong command file ở hệ điều hành hoặc hệ thống quản lý cấu hình; không nên nhầm file script bên ngoài với stored script bên trong catalog.

## 5. Tạo và đăng ký recovery catalog

Các bước dưới đây là ví dụ minh họa cho một môi trường đã được DBA chuẩn bị. Tên service, user, password, tablespace và chính sách quyền cần thay theo hệ thống thực tế.

### 5.1. Chuẩn bị catalog database và schema

DBA tạo một user chuyên dụng trên catalog database, cấp quyền theo tài liệu Oracle cho vai trò `RECOVERY_CATALOG_OWNER`, cấu hình default tablespace và quota. Ví dụ khái quát:

```sql
CREATE USER rman_catalog
  IDENTIFIED BY "<strong-password>"
  DEFAULT TABLESPACE rman_catalog_ts
  QUOTA UNLIMITED ON rman_catalog_ts;

GRANT RECOVERY_CATALOG_OWNER TO rman_catalog;
```

Đây là ví dụ về cấu trúc thao tác, không phải script triển khai đầy đủ cho mọi phiên bản. Tablespace phải tồn tại; password phải được quản lý an toàn; quyền tạo schema và cấp role cần được thực hiện bởi DBA có thẩm quyền. Trong môi trường production, nên cân nhắc quota hữu hạn và quy trình mở rộng tablespace thay vì cấp dung lượng không giới hạn.

### 5.2. Tạo catalog

Kết nối RMAN tới catalog database bằng user owner:

```text
rman catalog rman_catalog@RCAT
```

Sau khi xác thực, tạo các đối tượng catalog:

```rman
CREATE CATALOG;
```

Nếu muốn chỉ định tablespace khác với default tablespace của schema, có thể dùng cú pháp `CREATE CATALOG TABLESPACE ...` phù hợp với phiên bản RMAN đang sử dụng.

Lệnh tạo catalog tạo cấu trúc metadata trong schema. Nó không backup target database và cũng không tự động đăng ký tất cả database trong hệ thống.

### 5.3. Kết nối target và catalog

RMAN cần kết nối tới target database và recovery catalog:

```text
rman target sys@ORCL catalog rman_catalog@RCAT
```

Trong môi trường có OS authentication phù hợp, có thể kết nối target bằng cú pháp `target /` và chỉ định catalog riêng. Tài khoản target cần quyền SYSDBA hoặc quyền kết nối RMAN phù hợp theo phiên bản và chính sách bảo mật. Không ghi password production trực tiếp vào command history hoặc tài liệu dùng chung.

### 5.4. Đăng ký target database

Khi kết nối cả target và catalog, thực hiện:

```rman
REGISTER DATABASE;
```

RMAN đăng ký database hiện tại vào catalog và đồng bộ các metadata cần thiết từ control file. Có thể kiểm tra danh sách database đã đăng ký bằng:

```rman
LIST INCARNATION OF DATABASE;
```

Hoặc truy vấn view catalog bằng schema owner, ví dụ:

```sql
SELECT db_key, dbid, name
FROM rc_database
ORDER BY name;
```

Tên cột và view có thể khác theo phiên bản catalog; nên tham khảo data dictionary của đúng phiên bản khi xây dựng báo cáo tự động.

### 5.5. Nâng cấp catalog schema

Khi sử dụng RMAN client/database phiên bản mới hơn, có thể cần nâng cấp recovery catalog schema để tương thích với phiên bản RMAN mới. RMAN có thể yêu cầu chạy `UPGRADE CATALOG` khi phát hiện schema cũ.

Trước khi nâng cấp:

- Kiểm tra ma trận tương thích giữa RMAN client, target database và catalog database.
- Backup recovery catalog database.
- Xác nhận các target database và công cụ quản trị đang dùng phiên bản nào.
- Thực hiện trong cửa sổ bảo trì phù hợp và kiểm tra sau nâng cấp.

Không nên tự suy ra rằng mọi phiên bản RMAN đều tương thích với mọi phiên bản catalog chỉ vì kết nối thành công. Hãy theo tài liệu tương thích của Oracle cho phiên bản đang vận hành.

## 6. Resynchronization: đồng bộ control file với recovery catalog

Khi dùng recovery catalog, control file của target vẫn là nơi Oracle ghi nhận trạng thái vận hành và RMAN dùng nó làm nguồn thông tin quan trọng. Recovery catalog cần được đồng bộ để nhận những thay đổi mới. Quá trình đồng bộ đó gọi là **resynchronization**.

RMAN thực hiện resync tự động trong những hoạt động phù hợp, chẳng hạn sau các thao tác backup hoặc khi cần cập nhật metadata. DBA cũng có thể yêu cầu đồng bộ thủ công:

```rman
RESYNC CATALOG;
```

Resync đưa các thay đổi repository từ control file của target vào recovery catalog. Nếu control file đã tái sử dụng record cũ trước khi catalog kịp nhận metadata, một số lịch sử có thể không được catalog thu thập đầy đủ. Do đó, việc kết nối catalog định kỳ và để RMAN resync theo quy trình bình thường là quan trọng.

### 6.1. Resync không phải là backup

`RESYNC CATALOG` chỉ đồng bộ metadata. Lệnh này không sao chép datafile, backup piece hay archived redo log sang catalog database. Nó cũng không thay thế backup control file hoặc backup chính catalog database.

### 6.2. Catalog không truy cập được

Nếu recovery catalog database tạm thời không khả dụng, RMAN vẫn có thể hoạt động dựa trên control file repository khi kết nối theo chế độ NOCATALOG và khi thông tin cần thiết còn trong control file. Khi catalog hoạt động trở lại, kết nối lại target/catalog và thực hiện resync để cập nhật metadata.

Khả năng tiếp tục thao tác cụ thể còn phụ thuộc lệnh đang chạy, repository metadata còn sẵn có, backup device và trạng thái database. Không nên bỏ qua sự cố catalog kéo dài: các record trong control file vẫn có vòng đời riêng và có thể bị tái sử dụng.

## 7. RMAN configuration được lưu ở đâu?

RMAN persistent configuration gồm những thiết lập như:

- Retention policy.
- Default device type.
- Channel và parallelism.
- Backup optimization.
- Compression và encryption.
- Control file autobackup.
- Snapshot control file name.
- Cấu hình liên quan đến tape/SBT nếu sử dụng.

Khi không dùng recovery catalog, cấu hình RMAN được lưu trong control file của target. Khi dùng recovery catalog, cấu hình được lưu trong catalog và được quản lý cùng repository tương ứng.

Xem cấu hình hiện tại:

```rman
SHOW ALL;
```

Ví dụ cấu hình retention policy và control file autobackup:

```rman
CONFIGURE RETENTION POLICY TO RECOVERY WINDOW OF 7 DAYS;
CONFIGURE CONTROLFILE AUTOBACKUP ON;
```

Retention policy xác định mức backup cần giữ để đáp ứng mục tiêu phục hồi. Ví dụ `RECOVERY WINDOW OF 7 DAYS` yêu cầu giữ đủ backup và redo cần thiết để có thể phục hồi về các thời điểm trong cửa sổ bảy ngày, theo khả năng của chuỗi backup và archived log. Đây không đơn giản là xóa mọi file cũ hơn bảy ngày.

Có thể chọn chính sách theo redundancy, ví dụ giữ một số bản backup cần thiết gần nhất. Chính sách phù hợp phụ thuộc RPO, RTO, dung lượng lưu trữ và yêu cầu kiểm toán của hệ thống.

## 8. Bảo trì metadata và phân biệt các trạng thái backup

Quản lý repository cần phân biệt rõ backup còn tồn tại, backup bị thiếu và backup không còn cần thiết theo retention policy.

### 8.1. Liệt kê backup

```rman
LIST BACKUP SUMMARY;
LIST BACKUP OF DATABASE;
LIST BACKUP OF ARCHIVELOG ALL;
REPORT SCHEMA;
LIST INCARNATION OF DATABASE;
```

Các lệnh `LIST` đọc metadata repository để hiển thị backup mà RMAN đang biết. `REPORT SCHEMA` hiển thị cấu trúc datafile/tablespace mà RMAN ghi nhận.

### 8.2. Crosscheck: đối chiếu metadata với thiết bị lưu trữ

Theo thời gian, backup piece có thể bị di chuyển, xóa thủ công, mất do lỗi lưu trữ hoặc không còn truy cập được. Repository vẫn có thể ghi nhận backup đó là available. `CROSSCHECK` kiểm tra sự hiện diện của backup trên thiết bị tương ứng và cập nhật trạng thái trong repository.

```rman
CROSSCHECK BACKUP;
CROSSCHECK ARCHIVELOG ALL;
```

Nếu RMAN không tìm thấy file đã ghi nhận, trạng thái backup có thể được chuyển thành `EXPIRED`. Crosscheck không phải lệnh xóa backup file; nó cập nhật metadata theo kết quả kiểm tra.

### 8.3. Expired và obsolete không giống nhau

| Trạng thái/khái niệm | Ý nghĩa | Cách xử lý thường gặp |
|---|---|---|
| `EXPIRED` | Repository ghi nhận backup nhưng crosscheck không tìm thấy file tương ứng trên thiết bị | Xác minh file có bị di chuyển hoặc thiết bị mất kết nối; sau đó cân nhắc `DELETE EXPIRED` để dọn record |
| `OBSOLETE` | Backup không còn cần thiết để đáp ứng retention policy hiện tại | Xem bằng `REPORT OBSOLETE`; sau khi xác nhận, dùng `DELETE OBSOLETE` theo quy trình |
| `AVAILABLE` | RMAN hiện ghi nhận backup có thể truy cập theo lần kiểm tra gần nhất | Vẫn cần kiểm tra khả năng đọc và restore thực tế theo lịch |

`EXPIRED` nói về việc RMAN không tìm thấy file ở vị trí đã biết; `OBSOLETE` nói về chính sách giữ backup. Một backup có thể available nhưng obsolete; một backup expired có thể chưa obsolete theo retention policy. Hai trạng thái này không thể thay thế cho nhau.

### 8.4. Dọn record expired

Sau khi đã xác minh các file thật sự không còn trên thiết bị và không có kế hoạch khôi phục lại chúng, có thể dọn record expired:

```rman
DELETE EXPIRED BACKUP;
DELETE EXPIRED ARCHIVELOG ALL;
```

Các lệnh này dọn metadata của những đối tượng được đánh dấu expired. Vì RMAN đã xác định file không tồn tại ở vị trí kiểm tra, thao tác chủ yếu là làm sạch repository; vẫn phải kiểm tra kỹ phạm vi trước khi chạy.

### 8.5. Xóa backup obsolete

Xem trước những backup không còn cần theo retention policy:

```rman
REPORT OBSOLETE;
```

Sau khi kiểm tra policy và yêu cầu lưu trữ, có thể xóa:

```rman
DELETE OBSOLETE;
```

Khác với `DELETE EXPIRED`, `DELETE OBSOLETE` có thể xóa các backup piece thực tế khỏi thiết bị và cập nhật repository. Không chạy lệnh này nếu retention policy chưa phản ánh đúng yêu cầu khôi phục, legal hold hoặc thời gian lưu trữ của tổ chức.

### 8.6. Đưa backup file có sẵn trở lại repository

Nếu backup piece còn tồn tại trên disk nhưng metadata không còn trong repository, RMAN có thể catalog file đó để nhận diện lại, miễn file thuộc định dạng và phạm vi RMAN hỗ trợ.

```rman
CATALOG START WITH '/backup/oracle/' NOPROMPT;
```

Hoặc catalog một backup piece cụ thể:

```rman
CATALOG BACKUPPIECE '/backup/oracle/backup_piece_01.bkp';
```

Lệnh `CATALOG` bổ sung metadata về file vào repository; nó không tạo ra một bản backup mới và không sửa nội dung backup piece. Trước khi catalog một thư mục, cần xác minh đó là nơi chứa backup đúng target database và tránh đưa nhầm file không liên quan.

## 9. Các view dùng để kiểm tra repository

RMAN command như `LIST`, `REPORT` và `SHOW` thường là giao diện thuận tiện để kiểm tra repository. Khi cần giám sát hoặc viết báo cáo SQL, có thể đọc các dynamic performance view ở target hoặc recovery catalog view ở catalog schema.

### 9.1. View phía target database

Một số view thường dùng:

| View | Nội dung |
|---|---|
| `V$DATABASE` | DBID, database name, incarnation và trạng thái database |
| `V$CONTROLFILE` | Danh sách control file đang cấu hình |
| `V$CONTROLFILE_RECORD_SECTION` | Số record đã dùng/tổng số trong từng section của control file |
| `V$BACKUP_SET` | Metadata backup set |
| `V$BACKUP_PIECE` | Metadata backup piece và handle |
| `V$BACKUP_DATAFILE` | Thông tin datafile được ghi nhận trong backup |
| `V$ARCHIVED_LOG` | Metadata archived redo log |
| `V$RMAN_CONFIGURATION` | Cấu hình RMAN persistent |

Ví dụ xem DBID và database name:

```sql
SELECT dbid, name, open_mode, database_role
FROM v$database;
```

Xem backup set gần đây:

```sql
SELECT
    set_stamp,
    set_count,
    backup_type,
    incremental_level,
    pieces,
    start_time,
    completion_time
FROM v$backup_set
ORDER BY completion_time DESC;
```

Xem backup piece và trạng thái:

```sql
SELECT
    set_stamp,
    set_count,
    piece#,
    handle,
    status,
    start_time,
    completion_time
FROM v$backup_piece
ORDER BY completion_time DESC;
```

Các cột hiển thị và khả năng truy vấn phụ thuộc phiên bản, quyền truy cập và loại backup. Không nên giả định mọi cột có cùng ý nghĩa trong mọi release; tra data dictionary của phiên bản database đang dùng.

### 9.2. View phía recovery catalog

Khi kết nối catalog schema, có thể sử dụng các view `RC_*` để truy vấn metadata tập trung. Ví dụ:

```sql
SELECT db_key, dbid, name
FROM rc_database
ORDER BY name;
```

Một số view catalog thường gặp gồm `RC_DATABASE`, `RC_BACKUP_SET`, `RC_BACKUP_PIECE`, `RC_BACKUP_DATAFILE`, `RC_ARCHIVED_LOG` và các view về cấu hình RMAN. Tên view và cột cần được xác nhận theo phiên bản recovery catalog.

Không nên cập nhật trực tiếp các bảng hoặc view nền của recovery catalog bằng DML. Hãy dùng lệnh RMAN như `REGISTER`, `RESYNC`, `CHANGE`, `CATALOG`, `CROSSCHECK` và `DELETE` để repository được cập nhật theo quy tắc nhất quán của RMAN.

## 10. Khôi phục khi mất control file

Mất control file là tình huống nghiêm trọng vì database cần control file để mount. Nếu đã bật control file autobackup và backup được lưu ở vị trí còn truy cập được, RMAN có thể restore control file trước rồi tiếp tục restore/recover database.

Quy trình tổng quát trong môi trường NOCATALOG:

```rman
STARTUP NOMOUNT;
SET DBID 1234567890;
RESTORE CONTROLFILE FROM AUTOBACKUP;
ALTER DATABASE MOUNT;
RESTORE DATABASE;
RECOVER DATABASE;
```

`1234567890` là DBID minh họa, phải thay bằng DBID thật. Khi chưa có control file và không kết nối recovery catalog, DBID giúp RMAN nhận diện đúng autobackup. DBID có thể được lưu trong hồ sơ cấu hình database, log backup hoặc tài liệu vận hành.

Sau khi restore control file và mount database, RMAN có thể đọc repository từ control file vừa khôi phục để tìm các backup còn được ghi nhận. Nếu cần phục hồi bằng backup control file, thao tác mở database thường phải dùng `OPEN RESETLOGS` sau khi recovery hoàn tất theo quy tắc của Oracle cho tình huống đó:

```rman
ALTER DATABASE OPEN RESETLOGS;
```

Không áp dụng `OPEN RESETLOGS` một cách máy móc cho mọi tình huống restore/recovery. Kiểu recovery, việc dùng backup control file, điểm phục hồi và thông báo của Oracle quyết định cách mở database. Đặc biệt, incomplete recovery hoặc recovery bằng backup control file thường tạo incarnation mới và yêu cầu mở `RESETLOGS`.

Nếu recovery catalog còn khả dụng, RMAN có thể dùng metadata trong catalog để tìm backup ngay cả khi control file hiện hành bị mất. Tuy nhiên, database vẫn cần một control file được restore để mount và thực hiện các bước recovery.

### 10.1. Vì sao cần bảo vệ control file autobackup?

Nếu chỉ backup datafile mà không có control file backup phù hợp, DBA có thể phải dựng lại control file thủ công từ trace hoặc từ thông tin cấu trúc đã ghi nhận. Quá trình này phức tạp và dễ bỏ sót cấu hình. Control file autobackup giúp lưu lại cấu trúc database và metadata cần thiết để khởi đầu quá trình restore.

Nên kiểm tra định kỳ:

- Control file autobackup có thực sự được tạo sau backup không.
- Autobackup được lưu ở vị trí độc lập và có thể truy cập khi database down không.
- Format autobackup có được ghi nhận và DBID có được lưu trong hồ sơ vận hành không.
- Backup control file có được giữ theo thời gian phù hợp với retention và yêu cầu disaster recovery không.
- Có thực hiện diễn tập restore control file và recovery database không.

## 11. Bảo vệ recovery catalog

Recovery catalog chứa metadata có giá trị vận hành cao. Nếu catalog database bị mất, target control file vẫn có thể giữ một phần metadata, nhưng lịch sử dài hạn hoặc stored script có thể không còn. Vì vậy catalog database cần được bảo vệ như một database production quan trọng.

Các nguyên tắc chính:

1. Đặt catalog trên database độc lập với target database được bảo vệ.
2. Backup catalog database thường xuyên và kiểm tra khả năng restore của chính catalog.
3. Giám sát dung lượng tablespace, tăng trưởng metadata và trạng thái database catalog.
4. Giới hạn quyền truy cập schema owner; không chia sẻ credential catalog rộng rãi.
5. Ghi nhận service name, DBID, phiên bản RMAN và quy trình kết nối trong tài liệu vận hành bảo mật.
6. Kiểm tra resynchronization sau các đợt bảo trì, thay đổi phiên bản hoặc gián đoạn kết nối.
7. Kiểm thử quy trình phục hồi target khi catalog database không sẵn sàng.

Không nên đặt toàn bộ backup piece cùng một nơi với recovery catalog database rồi xem đó là một bản sao an toàn. Backup data, control file và catalog cần được bảo vệ trước các miền lỗi khác nhau, chẳng hạn mất máy chủ, lỗi storage, sự cố vùng hoặc thao tác xóa nhầm.

## 12. Tình huống thường gặp và hướng xử lý

### 12.1. RMAN không tìm thấy backup mà file vẫn còn

Nguyên nhân có thể là metadata đã bị tái sử dụng khỏi control file, catalog chưa được resync, hoặc backup được copy từ một thiết bị khác mà chưa catalog vào repository hiện tại.

Hướng xử lý:

1. Xác minh file backup còn nguyên vẹn và đúng target database.
2. Kiểm tra DBID, incarnation và vị trí backup.
3. Kiểm tra `LIST BACKUP` và repository đang được RMAN sử dụng.
4. Nếu file hợp lệ nhưng chưa có metadata, cân nhắc `CATALOG BACKUPPIECE` hoặc `CATALOG START WITH`.
5. Thử đọc và restore trong môi trường kiểm thử khi mức độ quan trọng cho phép.

Không nên tự tạo record trong bảng repository bằng SQL để buộc RMAN nhận backup.

### 12.2. Backup bị đánh dấu EXPIRED

`EXPIRED` thường có nghĩa crosscheck không tìm thấy file ở vị trí mà repository ghi nhận. Có thể storage tạm thời không mount, tape chưa được nạp, đường dẫn thay đổi hoặc file thực sự đã bị xóa.

Trước khi dọn record, kiểm tra thiết bị lưu trữ và đường dẫn. Nếu file chỉ tạm thời không truy cập được, khôi phục kết nối storage rồi crosscheck lại. Chỉ dùng `DELETE EXPIRED` sau khi xác nhận record cần được dọn.

### 12.3. Lịch sử backup trong control file bị thiếu

Có thể record cũ đã được tái sử dụng theo cơ chế record section và `CONTROL_FILE_RECORD_KEEP_TIME`. Nếu catalog đã được resync trước đó, kiểm tra metadata trong catalog. Nếu không có catalog, xác minh backup file còn tồn tại và có thể catalog lại hay không.

Tăng `CONTROL_FILE_RECORD_KEEP_TIME` có thể giúp giữ record lâu hơn trong control file, nhưng không thay thế recovery catalog cho yêu cầu lưu lịch sử dài hạn và cũng không thay thế backup control file.

### 12.4. Recovery catalog không kết nối được

Kiểm tra listener/service của catalog database, kết nối mạng, credential, trạng thái schema và tablespace. Nếu cần chạy backup trong lúc catalog tạm thời không khả dụng, DBA có thể đánh giá việc dùng repository trong control file bằng kết nối NOCATALOG, tùy lệnh và trạng thái hiện tại.

Sau khi catalog hoạt động lại, kết nối đúng target/catalog và thực hiện resync. Ghi nhận khoảng thời gian gián đoạn để xác định metadata nào có thể không còn trong control file.

### 12.5. Catalog schema cần nâng cấp

Kiểm tra phiên bản RMAN client, target database và catalog schema. Backup catalog database trước khi chạy `UPGRADE CATALOG`; sau nâng cấp, kiểm tra đăng ký database, resync và các lệnh `LIST`/`REPORT` quan trọng.

## 13. Quy trình vận hành mẫu

Một quy trình RMAN có recovery catalog có thể được tổ chức như sau:

```text
Trước khi backup
    |
    +--> Kiểm tra target và catalog kết nối được
    +--> Kiểm tra storage, channel và dung lượng
    +--> Xem RMAN configuration / retention policy
    |
    v
Thực hiện backup database và archived log
    |
    +--> RMAN ghi backup piece lên storage
    +--> RMAN cập nhật repository trong control file
    +--> RMAN resync metadata sang recovery catalog
    |
    v
Kiểm tra kết quả
    |
    +--> LIST BACKUP / REPORT OBSOLETE
    +--> Kiểm tra trạng thái backup piece
    +--> Lưu log và metric vận hành
    |
    v
Bảo trì định kỳ
    |
    +--> CROSSCHECK BACKUP / ARCHIVELOG
    +--> Xử lý EXPIRED sau khi xác minh
    +--> DELETE OBSOLETE theo policy đã duyệt
    +--> Backup recovery catalog database
    +--> Diễn tập restore/recover
```

Ví dụ một phiên RMAN đơn giản:

```rman
SHOW ALL;
REPORT SCHEMA;
BACKUP DATABASE PLUS ARCHIVELOG;
LIST BACKUP SUMMARY;
CROSSCHECK BACKUP;
REPORT OBSOLETE;
```

Các lệnh dọn backup nên được tách thành bước vận hành có kiểm tra và phê duyệt phù hợp, đặc biệt trong môi trường có yêu cầu lưu trữ dài hạn. Không nên gộp `DELETE OBSOLETE` vào mọi job backup nếu retention policy chưa được kiểm chứng bằng một bài diễn tập restore.

## 14. Kiểm thử khả năng phục hồi

Backup thành công và metadata đầy đủ không chứng minh database chắc chắn khôi phục được. Cần định kỳ thực hiện restore/recover trên môi trường kiểm thử hoặc môi trường diễn tập có kiểm soát.

Một bài kiểm thử nên xác nhận:

- Có thể truy cập backup piece và archived redo log cần thiết.
- Có thể tìm backup từ control file repository hoặc recovery catalog.
- Có thể restore control file từ autobackup khi cần.
- Có thể mount database và restore datafile.
- Có đủ archived redo log để recover đến điểm mong muốn.
- Có hiểu rõ khi nào phải mở database bằng `RESETLOGS`.
- Sau recovery, ứng dụng và dữ liệu được kiểm tra theo tiêu chí nghiệp vụ.
- Thời gian thực hiện đáp ứng RTO và điểm dữ liệu phục hồi đáp ứng RPO.

Nên ghi lại kết quả diễn tập, thời gian từng bước, backup được sử dụng, các thiếu sót và hành động khắc phục. Đây là bằng chứng thực tế về khả năng phục hồi, có giá trị hơn việc chỉ nhìn trạng thái `AVAILABLE` trong repository.

## 15. Những điểm cần nhớ

- RMAN repository là metadata mô tả database, backup, archived log, incarnation và cấu hình RMAN; nó không chứa nội dung datafile backup.
- Control file là repository mặc định và luôn cần thiết cho hoạt động database. Có thể dùng RMAN ở chế độ NOCATALOG.
- Recovery catalog là kho metadata tùy chọn ở database riêng; nó hỗ trợ lịch sử dài hạn, quản lý nhiều target database và stored script.
- Khi dùng catalog, RMAN đồng bộ metadata từ control file sang catalog bằng resynchronization. `RESYNC CATALOG` chỉ đồng bộ metadata, không backup dữ liệu.
- Control file autobackup giúp khôi phục control file khi sự cố; nên bật, lưu ở nơi an toàn và diễn tập restore.
- `CONTROL_FILE_RECORD_KEEP_TIME` điều khiển vòng đời record trong control file; nó khác retention policy của RMAN.
- `EXPIRED` nghĩa là RMAN không tìm thấy file khi crosscheck; `OBSOLETE` nghĩa là backup không còn cần theo retention policy.
- `CATALOG` có thể đưa backup file hợp lệ trở lại repository khi metadata không còn.
- Recovery catalog database cũng phải được backup, giám sát và kiểm thử khôi phục.
- Chỉ có thể xác nhận chiến lược backup đáng tin cậy sau khi đã diễn tập restore/recover thành công.

Thiết kế RMAN repository tốt là thiết kế cả metadata lẫn backup data như một hệ thống thống nhất: control file được bảo vệ, recovery catalog được triển khai khi có nhu cầu, repository được đồng bộ, backup được kiểm tra và quy trình restore được thực hành thường xuyên.

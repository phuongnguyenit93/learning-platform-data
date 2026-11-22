# Khôi phục schema hoặc toàn server vào môi trường cô lập

Khôi phục cơ sở dữ liệu vào một môi trường cô lập là cách kiểm tra bản sao lưu, điều tra sự cố, thử nâng cấp hoặc tái hiện lỗi mà không tác động đến hệ thống đang phục vụ ứng dụng. Với MySQL, bạn có thể khôi phục một schema (database) bằng bản sao lưu logic, hoặc khôi phục toàn bộ instance bằng bản sao lưu vật lý. Mỗi cách có phạm vi, yêu cầu tương thích và quy trình xác minh riêng.

Trong module `DATABASE_MYSQL`, bài học này kết nối các kỹ năng về schema, bảng InnoDB, tài khoản, phân quyền, giao dịch và vận hành. Một lần restore chỉ hoàn tất khi dữ liệu có thể đọc được, các đối tượng phụ thuộc hoạt động, và máy chủ được giữ trong phạm vi cô lập đã định.

Sau bài học, bạn có thể:

- Phân biệt khôi phục một schema với khôi phục toàn bộ MySQL instance.
- Chuẩn bị máy chủ đích riêng biệt, hạn chế kết nối và các tác vụ tự động.
- Dùng `mysqldump` và `mysql` để khôi phục schema hoặc nhiều schema.
- Khôi phục backup vật lý bằng công cụ đã tạo ra backup đó.
- Xử lý tài khoản, quyền, `DEFINER`, event, binary log và khóa mã hóa.
- Xác minh dữ liệu, đối tượng schema và khả năng vận hành sau restore.
- Lập quy trình thử khôi phục có thể lặp lại và ghi nhận thời gian phục hồi.

## 1. Chọn đúng phạm vi khôi phục

Trước khi chạy lệnh, hãy xác định kết quả cần đạt. Một schema thường gồm bảng, view, trigger, routine và event. Một MySQL instance còn có thể gồm nhiều schema, tài khoản và role, cấu hình máy chủ, log, trạng thái replication, chứng thư, keyring và các tệp dữ liệu hệ thống.

| Mục tiêu | Cách tiếp cận thường dùng | Thành phần cần chú ý |
|---|---|---|
| Khôi phục một schema | Backup logic của schema rồi import bằng `mysql` | Bảng, view, trigger, routine, event, charset/collation và `DEFINER` |
| Khôi phục nhiều schema ứng dụng | Backup logic nhiều schema hoặc dùng tiện ích dump của MySQL Shell | Tên schema, phụ thuộc giữa schema, tài khoản và quyền |
| Khôi phục toàn instance | Backup vật lý phù hợp với phiên bản/công cụ, hoặc dump logic có kế hoạch cho toàn bộ schema ứng dụng | Data directory, cấu hình, tài khoản, keyring, log và tương thích phiên bản |
| Khôi phục tại một thời điểm | Restore backup nền rồi áp dụng binary log đến thời điểm hoặc vị trí mong muốn | Binlog, GTID, múi giờ và mốc dừng chính xác |

Backup logic lưu câu lệnh SQL để tái tạo đối tượng và dữ liệu. Nó linh hoạt khi chỉ cần một schema hoặc cần chuyển dữ liệu sang instance khác, nhưng thời gian import có thể dài với lượng dữ liệu lớn. Backup vật lý lưu các tệp dữ liệu theo định dạng của công cụ backup; nó thường phù hợp hơn cho khôi phục instance lớn, nhưng đòi hỏi tương thích phiên bản và quy trình restore cụ thể của công cụ.

Không dùng backup vật lý của một công cụ với lệnh restore của công cụ khác. Với backup mã hóa InnoDB, phải chuẩn bị keyring hoặc dịch vụ quản lý khóa tương ứng trước khi MySQL mở các tablespace được mã hóa.

## 2. Chuẩn bị môi trường cô lập

Môi trường cô lập có thể là máy ảo, máy chủ thử nghiệm hoặc container chuyên dụng. Mục tiêu là cho phép quản trị viên và nhóm kiểm thử truy cập dữ liệu phục hồi, đồng thời ngăn máy chủ đó giao tiếp nhầm với hệ thống sản xuất.

### 2.1. Tách biệt hạ tầng

Trước khi restore, chuẩn bị:

- Máy chủ hoặc container riêng, có data directory và cấu hình riêng.
- Cổng MySQL khác với máy chủ đang chạy trên cùng host, ví dụ `3307` thay cho `3306`.
- Socket, PID file, error log và thư mục tạm riêng nếu chạy nhiều instance trên cùng máy.
- Firewall hoặc network policy giới hạn kết nối vào/ra; không để máy thử nghiệm có đường kết nối ứng dụng tới production.
- Dung lượng đĩa đủ cho dữ liệu đã giải nén, redo/undo, file tạm và khoảng trống trong lúc import hoặc prepare backup.
- Phiên bản MySQL và plugin tương thích với định dạng backup. Nếu mục tiêu là thử nâng cấp, hãy restore trước vào phiên bản tương thích với backup rồi thực hiện nâng cấp như một bước riêng.

Ví dụ cấu hình minh họa cho một instance thử nghiệm trên Linux:

```ini
[mysqld]
port=3307
datadir=/var/lib/mysql-restore
socket=/var/run/mysqld/mysqld-restore.sock
pid-file=/var/run/mysqld/mysqld-restore.pid
log-error=/var/log/mysql/restore-error.log
server-id=7307
event_scheduler=OFF
super_read_only=ON
```

Đây là cấu hình khung, cần điều chỉnh theo cách cài đặt và phiên bản MySQL. Nếu chạy instance thứ hai trên cùng host, phải kiểm tra các đường dẫn, quyền hệ điều hành và tài nguyên để tránh xung đột. `super_read_only=ON` giúp giữ dữ liệu chỉ đọc trong giai đoạn xác minh; quản trị viên có thể thay đổi có chủ đích khi cần thử thao tác ghi.

### 2.2. Ngăn tác vụ tự động chạy nhầm

Một bản phục hồi có thể chứa event, trigger, routine, plugin hoặc cấu hình từng chạy trong production. Trước khi mở kết nối cho ứng dụng thử nghiệm:

- Giữ `event_scheduler=OFF` để event không tự chạy khi instance khởi động.
- Không cấu hình replica tự động kết nối tới source production. Xóa hoặc vô hiệu hóa cấu hình replication theo hướng dẫn của phiên bản; kiểm tra các replication channel trước khi cho phép kết nối mạng.
- Chặn egress tới dịch vụ thanh toán, gửi email, webhook, queue, object storage và các hệ thống bên ngoài có thể bị tác động bởi dữ liệu thử nghiệm.
- Không dùng DNS hoặc endpoint của production trong cấu hình ứng dụng thử nghiệm.
- Dùng tài khoản thử nghiệm với quyền tối thiểu; thay hoặc vô hiệu hóa thông tin xác thực production được lưu trong cấu hình ứng dụng.
- Nếu dữ liệu có thông tin cá nhân hoặc bí mật kinh doanh, giới hạn người được truy cập và áp dụng quy trình masking phù hợp.

Nếu bản sao data directory được dùng để dựng một node mới, hãy bảo đảm `server_id` không trùng và kiểm tra `server_uuid` trước khi đưa node vào bất kỳ topology replication nào. Không nối máy phục hồi vào production chỉ để kiểm tra dữ liệu.

### 2.3. Ghi nhận thông tin trước restore

Tạo hồ sơ cho lần thử nghiệm:

| Thông tin | Ví dụ nội dung cần ghi |
|---|---|
| Nguồn backup | Tên instance, loại backup, vị trí lưu và mã định danh bộ backup |
| Thời điểm | Thời điểm backup, thời điểm bắt đầu restore và mốc dữ liệu mong muốn |
| Phiên bản | MySQL, hệ điều hành, công cụ backup và plugin liên quan |
| Phạm vi | Schema, bảng hoặc toàn instance |
| Mã hóa | Keyring/KMS/HSM cần thiết và cách truy cập an toàn |
| Môi trường đích | Host, port, data directory, firewall và người được phép truy cập |
| Kết quả | Thời gian restore, lỗi, số lượng đối tượng và kết quả kiểm tra |

Kiểm tra checksum hoặc chữ ký của bộ backup theo quy trình lưu trữ trước khi sử dụng. Không giải nén hoặc restore một tệp backup chưa rõ nguồn gốc vào máy chủ có quyền truy cập mạng rộng.

## 3. Khôi phục một schema bằng backup logic

Ví dụ sau dùng `mysqldump` và `mysql` trên hệ thống có hai schema: `appdb` là schema cần khôi phục, `appdb_restore` là schema đích trong môi trường thử nghiệm. Các lệnh shell minh họa dùng cú pháp Linux/macOS; trên Windows, dùng PowerShell hoặc shell tương ứng và điều chỉnh đường dẫn.

### 3.1. Tạo hoặc nhận file dump

Nếu cần tự tạo backup logic từ nguồn, có thể dùng:

```bash
mysqldump \
  --host=source-db.example \
  --user=backup_user \
  --single-transaction \
  --routines \
  --events \
  --triggers \
  --hex-blob \
  --set-gtid-purged=OFF \
  appdb > appdb.sql
```

Tùy chọn `--single-transaction` tạo snapshot nhất quán cho các bảng InnoDB trong điều kiện phù hợp. Trong lúc dump, tránh các thao tác DDL như `ALTER TABLE`, `DROP TABLE` hoặc `RENAME TABLE` trên những bảng được dump. Với bảng không dùng transactional engine, snapshot này không bảo đảm tính nhất quán tương tự; cần khóa hoặc dùng phương thức backup phù hợp.

`--routines`, `--events` và `--triggers` giúp đưa các đối tượng phụ trợ vào dump. `--hex-blob` biểu diễn dữ liệu nhị phân theo dạng hex để tránh một số vấn đề chuyển đổi ký tự. Không đặt mật khẩu trực tiếp trong dòng lệnh; dùng `-p` để nhập tương tác hoặc cơ chế quản lý thông tin xác thực được bảo vệ.

Ví dụ đặt `--set-gtid-purged=OFF` vì đây là dump một schema để nhập vào instance thử nghiệm độc lập; nó không mang trạng thái GTID toàn cục của nguồn sang đích. Nếu mục tiêu là khôi phục toàn instance và giữ lịch sử GTID, cần thiết kế riêng việc chuyển GTID theo topology và phiên bản, không dùng tùy chọn này một cách máy móc.

Nếu file dump được tạo bằng `--databases appdb`, file thường chứa câu lệnh tạo/chọn database. Nếu dump chỉ định tên schema ở cuối lệnh như ví dụ trên, file thường chứa các câu lệnh tạo đối tượng bên trong schema và có thể import vào schema đích đã tạo sẵn.

### 3.2. Tạo schema đích

Kết nối vào instance cô lập trên cổng `3307`:

```bash
mysql --host=127.0.0.1 --port=3307 --user=restore_admin -p
```

Tạo schema với charset và collation tương thích với nguồn:

```sql
CREATE DATABASE appdb_restore
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

Ví dụ collation trên phù hợp với các bản MySQL có hỗ trợ nó. Nếu nguồn dùng charset/collation khác, hãy kiểm tra `SHOW CREATE DATABASE appdb;` trên nguồn và dùng giá trị tương ứng. Chọn sai collation có thể làm thay đổi quy tắc so sánh, sắp xếp hoặc tính duy nhất của chuỗi.

### 3.3. Import vào schema đích

Thoát khỏi client SQL rồi chạy:

```bash
mysql \
  --host=127.0.0.1 \
  --port=3307 \
  --user=restore_admin \
  -p \
  appdb_restore < appdb.sql
```

Lệnh này giả định file dump không chứa câu lệnh `CREATE DATABASE` hoặc `USE appdb` buộc import quay về schema nguồn. Nếu dump được tạo với `--databases appdb`, cần đọc và hiểu cấu trúc dump trước khi restore; khi muốn giữ nguyên tên schema, có thể import file đó vào instance cô lập mà không truyền tên database ở cuối lệnh. Nếu muốn đổi tên schema, phải dùng quy trình chuyển đổi có kiểm soát, không thay thế chuỗi tên database một cách mù quáng trong file SQL.

Nếu import dừng giữa chừng, không mặc định rằng schema đã hoàn chỉnh. Xem lỗi đầu tiên, xác định các đối tượng đã được tạo, rồi quyết định xóa schema thử nghiệm và chạy lại từ đầu hay tiếp tục theo kế hoạch phục hồi. Tránh chạy lặp dump trên schema có dữ liệu dở dang vì có thể gây lỗi đối tượng đã tồn tại hoặc dữ liệu trùng.

### 3.4. Kiểm tra đối tượng phụ thuộc

Một schema có thể được import nhưng vẫn thiếu quyền hoặc đối tượng liên quan. Kiểm tra:

```sql
SHOW TABLES FROM appdb_restore;

SELECT TABLE_TYPE, COUNT(*) AS object_count
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'appdb_restore'
GROUP BY TABLE_TYPE;

SHOW TRIGGERS FROM appdb_restore;
SHOW EVENTS FROM appdb_restore;
```

Kiểm tra thêm view, routine và các đối tượng có `DEFINER`. View hoặc routine có thể phụ thuộc vào tài khoản chưa tồn tại hoặc quyền không được khôi phục. Xác định tài khoản sở hữu/định danh `DEFINER`, tạo lại tài khoản hoặc điều chỉnh đối tượng theo chính sách thử nghiệm. Không cấp quyền `SUPER` hay quyền quản trị rộng cho ứng dụng chỉ để làm biến mất lỗi quyền.

## 4. Khôi phục nhiều schema ứng dụng bằng dump logic

Nếu cần khôi phục một tập schema ứng dụng, có thể tạo dump với nhiều tên database:

```bash
mysqldump \
  --host=source-db.example \
  --user=backup_user \
  --single-transaction \
  --routines \
  --events \
  --triggers \
  --hex-blob \
  --set-gtid-purged=OFF \
  --databases appdb reporting auditdb > application-schemas.sql
```

Import vào instance cô lập:

```bash
mysql \
  --host=127.0.0.1 \
  --port=3307 \
  --user=restore_admin \
  -p < application-schemas.sql
```

Vì dump được tạo với `--databases`, nó chứa tên schema và các câu lệnh tạo/chọn schema. Hãy kiểm tra trước xem các tên schema trong file có đúng với mục tiêu phục hồi hay không.

### 4.1. Tài khoản và quyền truy cập

Dump schema không đồng nghĩa với việc đã khôi phục đầy đủ tài khoản và quyền của instance. Lập danh sách người dùng, role, quyền cấp ở cấp global, schema, bảng và routine. Trên nguồn, có thể xem định nghĩa và quyền của một tài khoản bằng:

```sql
SHOW CREATE USER 'app_user'@'10.%';
SHOW GRANTS FOR 'app_user'@'10.%';
```

Lặp lại cho các tài khoản và role cần thiết, lưu kết quả ở nơi được bảo vệ rồi rà soát trước khi áp dụng vào instance thử nghiệm. Không mang nguyên mật khẩu, token hoặc quyền truy cập production sang môi trường dùng chung. Tạo thông tin xác thực riêng, giới hạn host và chỉ cấp quyền cần cho mục đích kiểm thử.

Không restore đè toàn bộ schema hệ thống `mysql` một cách tùy tiện, nhất là khi phiên bản nguồn và đích khác nhau. Cách lưu trữ tài khoản và metadata nội bộ thay đổi theo phiên bản; hãy dùng cơ chế quản lý tài khoản được hỗ trợ cho phiên bản đích và chỉ tái tạo các tài khoản/quyền cần thiết.

### 4.2. Những đối tượng cần kiểm tra thêm

- **View:** kiểm tra định nghĩa, schema tham chiếu và quyền của `DEFINER`.
- **Trigger:** kiểm tra trigger có phụ thuộc vào bảng khác hoặc gọi routine không tồn tại.
- **Stored procedure/function:** kiểm tra `DEFINER`, `SQL SECURITY`, quyền thực thi và các đối tượng được gọi.
- **Event:** kiểm tra lịch chạy, múi giờ và bảo đảm event scheduler vẫn tắt cho tới khi được phép.
- **Foreign key:** kiểm tra các bảng được khôi phục đầy đủ và thứ tự import không gây lỗi ràng buộc.
- **Charset/collation:** kiểm tra cả cấp database, table và column khi cần so sánh với nguồn.
- **AUTO_INCREMENT:** kiểm tra giá trị kế tiếp sau import, đặc biệt nếu dữ liệu được lọc hoặc chuyển đổi.

## 5. Khôi phục toàn instance bằng backup vật lý

Backup vật lý thường là lựa chọn phù hợp khi cần phục hồi toàn bộ instance lớn, gồm data files và cấu trúc InnoDB liên quan. Phải dùng đúng công cụ đã tạo backup, đúng quy trình prepare và restore của phiên bản đó.

Ví dụ dưới đây minh họa quy trình phổ biến với Percona XtraBackup. Tên tùy chọn và yêu cầu tương thích có thể khác giữa các phiên bản XtraBackup; luôn đối chiếu tài liệu của phiên bản đã dùng để tạo backup.

### 5.1. Kiểm tra và prepare backup

Trước tiên, xác minh backup là bản đầy đủ cần thiết, có các incremental backup (nếu có), và đã được sao chép đầy đủ sang vùng lưu trữ của môi trường cô lập. Với backup full đơn giản, bước prepare thường có dạng:

```bash
xtrabackup --prepare --target-dir=/backup/full
```

Nếu backup có các phần incremental, phải áp dụng chúng theo đúng thứ tự và cú pháp của phiên bản công cụ. Không bỏ qua bước prepare khi công cụ yêu cầu, vì backup vật lý có thể chưa ở trạng thái nhất quán để phục hồi.

Nếu dữ liệu được mã hóa, nạp hoặc cấu hình keyring tương ứng theo hướng dẫn của phiên bản MySQL và công cụ backup trước khi khởi động instance đã phục hồi. Thiếu khóa có thể khiến MySQL không mở được tablespace dù các tệp dữ liệu đã được copy đầy đủ.

### 5.2. Copy backup vào data directory riêng

Ví dụ quy trình trên một máy Linux thử nghiệm, giả sử dịch vụ tên `mysqld` và data directory là `/var/lib/mysql`:

```bash
sudo systemctl stop mysqld
sudo mv /var/lib/mysql /var/lib/mysql.before-restore
sudo mkdir -p /var/lib/mysql

sudo xtrabackup --copy-back --target-dir=/backup/full
sudo chown -R mysql:mysql /var/lib/mysql
sudo systemctl start mysqld
```

Các lệnh này chỉ là ví dụ cho một môi trường đã chuẩn bị riêng. Xác nhận đúng dịch vụ và đường dẫn trước khi chạy. Data directory đích phải đáp ứng điều kiện của công cụ restore; không copy-back lên thư mục đang chứa dữ liệu cần giữ. Việc đổi tên data directory cũ giúp giữ lại trạng thái trước thử nghiệm để đối chiếu hoặc quay lại môi trường thử nghiệm ban đầu.

Nếu dùng MySQL Enterprise Backup hoặc công cụ khác, lệnh prepare/copy-back sẽ khác. Không lấy lệnh XtraBackup áp dụng cho định dạng backup khác.

### 5.3. Khởi động và xác minh instance

Sau khi khởi động, kiểm tra error log trước khi mở quyền truy cập cho nhóm kiểm thử. Xác nhận:

- MySQL khởi động thành công và không có lỗi InnoDB, keyring, redo log hoặc data dictionary.
- Instance đang nghe đúng địa chỉ và cổng thử nghiệm.
- `server_id`, `server_uuid` và cấu hình replication không khiến node tham gia topology production.
- `event_scheduler` vẫn tắt và các kết nối ra ngoài vẫn bị chặn.
- Các schema, bảng và đối tượng quan trọng xuất hiện như mong đợi.
- Tài khoản truy cập được giới hạn theo mục đích thử nghiệm.

Không mở cổng ra mạng rộng chỉ vì máy chủ đã khởi động thành công. Mở quyền truy cập theo từng nhóm và duy trì giới hạn mạng trong toàn bộ thời gian thử nghiệm.

## 6. Khôi phục tại một thời điểm bằng binary log

Khi cần phục hồi đến ngay trước một thao tác xóa nhầm hoặc cập nhật sai, có thể dùng backup đầy đủ làm mốc rồi phát lại binary log đến thời điểm hoặc vị trí mong muốn. Quy trình này được gọi là point-in-time recovery (PITR).

Các bước khái quát:

1. Chọn bản backup đầy đủ gần nhất trước sự cố.
2. Restore backup đó vào môi trường cô lập.
3. Xác định file binary log và mốc thời gian/vị trí dừng cần phục hồi.
4. Dùng `mysqlbinlog` đọc log theo đúng thứ tự và phát lại các sự kiện cần thiết vào instance cô lập.
5. Dừng tại mốc trước giao dịch gây lỗi; xác minh dữ liệu và ứng dụng.

Ví dụ minh họa khi đã xác định chính xác file log và vị trí dừng:

```bash
mysqlbinlog \
  --start-position=4 \
  --stop-position=987654 \
  /backup/binlog.000123 \
  /backup/binlog.000124 | \
mysql --host=127.0.0.1 --port=3307 --user=restore_admin -p
```

Vị trí `987654` chỉ là số minh họa, không được dùng nguyên trạng. Phải xác định đúng vị trí hoặc thời điểm từ log và đối chiếu với giao dịch cần loại trừ. Nếu dùng GTID, cần hiểu cách GTID được ghi trong dump, trạng thái `gtid_executed` của instance đích và tác động của việc phát lại. Không áp dụng một lệnh PITR chung cho mọi cấu hình GTID.

Không phát lại binary log production vào máy chủ production để thử nghiệm. Thực hiện trên instance cô lập và giữ lại bản backup ban đầu để có thể lặp lại quá trình.

## 7. Các yếu tố tương thích cần đối chiếu

Khôi phục thành công phụ thuộc vào sự tương thích giữa nguồn backup và instance đích.

| Yếu tố | Điều cần kiểm tra | Rủi ro nếu sai |
|---|---|---|
| Phiên bản MySQL | Phiên bản nguồn, phiên bản tạo backup, phiên bản đích và lộ trình nâng cấp được hỗ trợ | Lỗi data dictionary, định dạng tệp hoặc metadata |
| Storage engine | Engine của bảng, plugin và thư viện liên quan | Bảng không mở được hoặc thiếu chức năng |
| Charset/collation | Charset và collation cấp schema/bảng/cột | Thay đổi so sánh, sắp xếp hoặc ràng buộc duy nhất |
| SQL mode | `sql_mode` nguồn và đích | Dữ liệu hoặc câu lệnh có thể bị xử lý khác |
| Múi giờ | `time_zone`, bảng múi giờ và cấu hình ứng dụng | Lệch thời gian trong truy vấn và event |
| Tài khoản | User, role, host, quyền và `DEFINER` | Ứng dụng không đăng nhập hoặc routine/view lỗi |
| Mã hóa | Keyring, KMS/HSM, chứng thư và quyền lấy khóa | Không mở được tablespace hoặc log mã hóa |
| Replication/GTID | `server_id`, `server_uuid`, channel và trạng thái GTID | Node kết nối nhầm topology hoặc không thể áp dụng log |
| Cấu hình instance | Buffer pool, đường dẫn, plugin, TLS, log và cổng | Máy chủ không khởi động hoặc hoạt động khác nguồn |

Với restore vật lý, ưu tiên phiên bản tương thích với backup. Khi mục tiêu là nâng cấp MySQL, hãy tách hai hoạt động: khôi phục trên phiên bản tương thích trước, xác minh dữ liệu, rồi thực hiện nâng cấp theo đường dẫn được hỗ trợ.

## 8. Xác minh sau khôi phục

Đừng chỉ dựa vào việc MySQL khởi động thành công. Xác minh theo nhiều lớp để phát hiện thiếu dữ liệu hoặc đối tượng phụ thuộc.

### 8.1. Xác minh schema và số lượng đối tượng

```sql
SHOW DATABASES;

SELECT
    TABLE_SCHEMA,
    TABLE_TYPE,
    COUNT(*) AS object_count
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA IN ('appdb_restore', 'reporting')
GROUP BY TABLE_SCHEMA, TABLE_TYPE
ORDER BY TABLE_SCHEMA, TABLE_TYPE;
```

So sánh số lượng bảng, view và các đối tượng với manifest hoặc kết quả ghi nhận từ nguồn backup. Kiểm tra riêng các bảng quan trọng thay vì chỉ dựa vào tổng số đối tượng.

### 8.2. Xác minh dữ liệu nghiệp vụ

Ví dụ kiểm tra số lượng và khoảng thời gian của bảng giao dịch:

```sql
SELECT COUNT(*) AS payment_count
FROM appdb_restore.payment_record;

SELECT
    MIN(created_at) AS first_record,
    MAX(created_at) AS last_record
FROM appdb_restore.payment_record;
```

Đối chiếu với số liệu của bản backup hoặc báo cáo đã chụp tại thời điểm tương ứng. Với dữ liệu lớn, dùng checksum hoặc công cụ xác minh phù hợp để kiểm tra sâu hơn; không chạy truy vấn quét toàn bảng trên máy chủ có tài nguyên hạn chế nếu chưa đánh giá tác động.

### 8.3. Xác minh ứng dụng và quyền

- Kết nối bằng tài khoản thử nghiệm và chạy các truy vấn đại diện cho luồng đọc/ghi.
- Kiểm tra view, trigger, routine và event; event vẫn phải tắt cho tới khi có quyết định rõ ràng.
- Xác nhận tài khoản có đúng quyền và không có tài khoản production không cần thiết.
- Kiểm tra các ràng buộc foreign key, index và giá trị `AUTO_INCREMENT` của bảng quan trọng.
- Kiểm tra log MySQL để tìm warning/error phát sinh trong quá trình restore và truy vấn.
- Xác nhận ứng dụng thử nghiệm dùng endpoint, mật khẩu, queue và dịch vụ bên ngoài của môi trường thử nghiệm.

Nếu dữ liệu có thông tin nhạy cảm, kiểm tra việc masking trước khi cấp quyền cho người dùng rộng hơn nhóm phục hồi. Bản restore có thể chứa dữ liệu thật với mức độ nhạy cảm tương đương production.

## 9. Sự cố thường gặp khi restore

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `Access denied` khi import | Tài khoản đích thiếu quyền tạo bảng, view, routine hoặc trigger | Cấp quyền tối thiểu phù hợp trên instance cô lập; kiểm tra quyền `DEFINER` riêng |
| Lỗi database đã tồn tại hoặc bảng đã tồn tại | Import lặp hoặc schema đích chưa được làm sạch | Xác định trạng thái import; nếu cần, tạo lại schema thử nghiệm từ đầu theo kế hoạch |
| View/routine lỗi do `DEFINER` | Tài khoản định danh không có ở đích hoặc quyền không phù hợp | Kiểm tra `SHOW CREATE VIEW`/routine và tạo hoặc điều chỉnh definer theo chính sách |
| Collation không được hỗ trợ | Phiên bản đích cũ hơn hoặc thiếu collation nguồn | Dùng phiên bản tương thích hoặc lập kế hoạch chuyển đổi collation có kiểm tra |
| MySQL không mở được tablespace mã hóa | Keyring thiếu, sai phiên bản hoặc không truy cập được | Khôi phục keyring tương ứng, xác minh quyền và log trước khi khởi động lại |
| Lỗi InnoDB khi restore vật lý | Backup chưa prepare, sai công cụ/phiên bản hoặc tệp bị thiếu | Kiểm tra manifest, prepare theo đúng công cụ và đọc error log |
| Dữ liệu thiếu giao dịch cuối | Backup không bao phủ thời điểm cần hoặc PITR dừng quá sớm | Đối chiếu thời điểm backup, binlog và vị trí dừng |
| Event chạy ngoài ý muốn | `event_scheduler` bật trên môi trường phục hồi | Tắt scheduler, kiểm tra event đã import và rà soát log tác động |
| Instance tham gia replication ngoài ý muốn | Cấu hình replication được giữ nguyên hoặc node được kết nối vào mạng nguồn | Ngắt kết nối, vô hiệu hóa replication theo phiên bản và kiểm tra channel trước khi tiếp tục |

Khi gặp lỗi, lưu error log, đầu ra lệnh và trạng thái instance tại thời điểm lỗi. Nếu cần thử lại từ đầu, xác định rõ thư mục dữ liệu và schema nào thuộc môi trường thử nghiệm trước khi xóa hoặc tạo lại. Không xóa backup gốc trong lúc điều tra.

## 10. Runbook khôi phục mẫu

Runbook dưới đây có thể dùng làm khung cho một lần diễn tập khôi phục schema hoặc instance:

1. **Xác định mục tiêu:** schema hay toàn instance; thời điểm dữ liệu cần đạt; người chịu trách nhiệm xác minh.
2. **Chọn backup:** xác minh mã định danh, checksum, phiên bản, phạm vi và binary log đi kèm.
3. **Chuẩn bị máy cô lập:** tách mạng, cổng, data directory, tài khoản và cấu hình; tắt event scheduler và replication tự động.
4. **Chuẩn bị khóa:** nạp keyring hoặc thiết lập quyền truy cập KMS/HSM nếu backup được mã hóa.
5. **Restore:** dùng đúng công cụ và đúng quy trình cho backup logic hoặc vật lý.
6. **PITR nếu cần:** áp dụng binary log tới đúng thời điểm/vị trí dừng đã xác định.
7. **Xác minh:** kiểm tra log, schema, số lượng dữ liệu, đối tượng phụ thuộc, quyền và truy vấn nghiệp vụ.
8. **Kiểm tra cô lập:** xác nhận không có kết nối hoặc tác vụ tự động nào tác động tới production.
9. **Ghi nhận:** lưu thời gian, lỗi, bước thủ công, kết quả kiểm thử và người xác nhận.
10. **Kết thúc thử nghiệm:** giới hạn hoặc thu hồi quyền truy cập, lưu kết quả cần thiết, rồi xử lý dữ liệu thử nghiệm theo chính sách lưu trữ.

Các chỉ số nên đo trong diễn tập:

- **RTO (Recovery Time Objective):** thời gian mục tiêu để đưa dịch vụ hoặc dữ liệu trở lại trạng thái sử dụng được.
- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất, thường được biểu diễn bằng khoảng thời gian.
- Thời gian chuẩn bị máy đích, prepare backup, import/restore, PITR và xác minh.
- Dung lượng backup, dung lượng đích và tài nguyên CPU/I/O tiêu thụ.
- Số bước cần thao tác thủ công và số lỗi cần xử lý.

RTO/RPO phải được đo bằng diễn tập với dữ liệu và hạ tầng gần thực tế; không suy ra từ tốc độ của một lần restore nhỏ.

## 11. Tình huống thực hành

Một ứng dụng thương mại dùng MySQL với hai schema `shop` và `reporting`. Nhóm vận hành cần khôi phục schema `shop` vào môi trường thử nghiệm để tái hiện lỗi tính tổng đơn hàng. Sau đó, nhóm cần diễn tập khôi phục toàn instance từ backup vật lý và kiểm tra bản sao lưu có thể dùng cho DR.

Thực hiện trong môi trường lab:

1. Ghi lại phiên bản MySQL, charset/collation, engine và danh sách đối tượng của hai schema.
2. Chuẩn bị instance cô lập trên cổng riêng, bật `event_scheduler=OFF`, giữ `super_read_only=ON` trong giai đoạn xác minh và chặn kết nối ra production.
3. Tạo dump logic của schema `shop` với bảng, view, trigger, routine và event.
4. Tạo schema `shop_restore` có charset/collation tương ứng rồi import dump vào đó.
5. Kiểm tra số lượng bảng, số đơn hàng, tổng tiền theo một khoảng ngày và các routine/view quan trọng.
6. Ghi nhận tài khoản, role và `DEFINER` cần thiết; tạo tài khoản thử nghiệm với quyền tối thiểu.
7. Dùng bản backup vật lý được tạo bởi công cụ phù hợp để dựng một instance cô lập thứ hai; chuẩn bị keyring trước khi mở dữ liệu mã hóa.
8. Nếu có binary log, thực hiện PITR trên instance lab tới thời điểm ngay trước một thay đổi thử nghiệm đã biết.
9. Đo thời gian restore và xác minh, ghi lại RTO/RPO thực tế cùng các bước cần cải thiện.

**Câu hỏi tự đánh giá:**

- Vì sao backup logic một schema có thể phù hợp hơn backup vật lý khi cần khôi phục riêng một database?
- Vì sao `--single-transaction` không bảo đảm snapshot nhất quán cho mọi storage engine và khi có DDL đồng thời?
- Khi dump được tạo với `--databases`, cần lưu ý gì về câu lệnh `CREATE DATABASE` và `USE` trong file?
- Vì sao không nên restore toàn bộ schema hệ thống `mysql` tùy tiện sang phiên bản khác?
- Vì sao cần tắt event scheduler và chặn kết nối ra production trên máy chủ phục hồi?
- Nếu backup dữ liệu được mã hóa, cần chuẩn bị những thành phần nào trước khi khởi động instance đã restore?
- Làm thế nào xác định mốc PITR ngay trước giao dịch gây lỗi?

## Kết luận

Khôi phục schema hoặc toàn MySQL instance vào môi trường cô lập là một quy trình gồm chuẩn bị hạ tầng, lựa chọn đúng loại backup, khôi phục dữ liệu, xử lý phụ thuộc và xác minh kết quả. Môi trường cô lập bảo vệ hệ thống đang chạy và cho phép diễn tập có kiểm soát. Hãy coi một lần restore chỉ đạt yêu cầu khi dữ liệu và đối tượng quan trọng đã được xác minh, khóa và tài khoản cần thiết hoạt động đúng, và kết nối/tác vụ tự động vẫn nằm trong phạm vi thử nghiệm.

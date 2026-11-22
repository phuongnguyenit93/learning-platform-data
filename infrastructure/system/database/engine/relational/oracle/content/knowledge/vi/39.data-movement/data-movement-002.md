# Data Pump: expdp, impdp và xử lý phía máy chủ

Oracle Data Pump là bộ công cụ nhập và xuất dữ liệu logic của Oracle Database. Hai tiện ích thường dùng là `expdp` để export và `impdp` để import. DBA dùng Data Pump để di chuyển schema, bảng, metadata, dữ liệu hoặc một phần database giữa các môi trường; tạo bản trích xuất phục vụ kiểm thử; và chuyển dữ liệu giữa các phiên bản Oracle tương thích.

Điểm quan trọng khi vận hành Data Pump là **công việc đọc và ghi dữ liệu được thực hiện chủ yếu bởi các tiến trình phía database server**. Máy chạy lệnh `expdp` hoặc `impdp` chỉ khởi tạo và điều khiển job. Vì vậy, đường dẫn dump file và log file được phân giải trên máy chủ database theo `DIRECTORY` object, không phải thư mục hiện tại của terminal đang chạy tiện ích.

## 1. Data Pump hoạt động như thế nào?

### 1.1. Hai tiện ích expdp và impdp

| Tiện ích | Vai trò | Hướng dữ liệu |
|---|---|---|
| `expdp` | Export dữ liệu và metadata từ database ra dump file hoặc chuyển trực tiếp qua database link. | Database nguồn → dump set hoặc database đích. |
| `impdp` | Import dữ liệu và metadata từ dump file hoặc đọc trực tiếp database nguồn qua database link. | Dump set hoặc database nguồn → database đích. |

Data Pump là công cụ di chuyển dữ liệu logic. Nó xuất các đối tượng database và dữ liệu theo phạm vi được chọn; nó không phải bản backup vật lý thay thế RMAN. RMAN bảo vệ và phục hồi datafile, control file, archived redo log theo cơ chế physical backup/recovery. Data Pump phù hợp khi cần chọn schema/bảng, đổi tên schema, đổi tablespace hoặc tái tạo đối tượng ở database khác.

### 1.2. Xử lý phía máy chủ

Khi chạy `expdp` hoặc `impdp`, client kết nối tới database và yêu cầu tạo một Data Pump job. Database tạo master table để theo dõi metadata và trạng thái job, sau đó điều phối các Data Pump server process/worker thực hiện đọc, ghi, chuyển đổi và nạp dữ liệu.

```text
Máy chạy expdp / impdp
       |
       |  Kết nối Oracle Net, gửi tham số và lệnh điều khiển
       v
Oracle Database instance
       |
       +---- Master table / job metadata
       |
       +---- Data Pump master process
       |
       +---- Worker processes
       |          |
       |          +---- Đọc/ghi bảng và metadata
       |          +---- Xử lý song song khi được cấu hình
       |
       v
DIRECTORY object trên database server
       |
       +---- Dump file(s)
       +---- Log file
       +---- SQLFILE hoặc file liên quan
```

Client có thể chạy trên máy DBA, máy ứng dụng hoặc một host quản trị riêng. Dump file và log file vẫn được đọc/ghi tại vị trí server-side mà `DIRECTORY` object trỏ tới. Đây là khác biệt quan trọng so với việc dùng `scp`, `cp` hoặc một công cụ client tự ghi file vào máy cục bộ.

### 1.3. Những gì nằm ở client và những gì nằm ở server

| Thành phần | Nơi được xử lý hoặc lưu |
|---|---|
| Executable `expdp`/`impdp` | Máy chạy tiện ích, cần Oracle client tương thích. |
| Kết nối database và tham số job | Client gửi tới database server. |
| Parameter file (`PARFILE`) | Được tiện ích client đọc từ máy chạy lệnh. |
| Data Pump master table và worker | Database server. |
| Dump file (`DUMPFILE`) | Filesystem hoặc storage mà database server truy cập qua directory object. |
| Log file (`LOGFILE`) | Directory trên database server. |
| File DDL từ `SQLFILE` | Directory trên database server. |

Ví dụ, nếu DBA chạy `expdp` từ laptop và database server nằm trên Linux, `DIRECTORY=DP_DIR` vẫn trỏ tới thư mục Linux trên server. Thư mục `C:\temp` của laptop không tự trở thành nơi ghi dump file chỉ vì lệnh được chạy từ Windows.

## 2. Chuẩn bị DIRECTORY object

### 2.1. Directory object là gì?

Oracle dùng database directory object để ánh xạ một tên logic sang một đường dẫn filesystem trên máy chủ database. Ví dụ, DBA tạo `DP_DIR` trỏ tới `/u01/dpump`:

```sql
CREATE DIRECTORY dp_dir AS '/u01/dpump';
```

`CREATE DIRECTORY` chỉ tạo metadata trong database; nó không tự tạo thư mục trên hệ điều hành. DBA hoặc quản trị viên hệ điều hành phải tạo thư mục và cấp quyền đọc/ghi cho tài khoản OS chạy Oracle Database.

Có thể kiểm tra directory object:

```sql
SELECT directory_name, directory_path
FROM dba_directories
WHERE directory_name = 'DP_DIR';
```

Tên directory object thường được lưu dạng chữ hoa nếu không tạo bằng quoted identifier.

### 2.2. Cấp quyền READ và WRITE

User chạy Data Pump cần quyền trên directory object. Ví dụ:

```sql
GRANT READ, WRITE ON DIRECTORY dp_dir TO app_migration;
```

`READ` cho phép đọc file trong directory; `WRITE` cho phép tạo hoặc ghi file. Export thường cần quyền ghi dump/log; import cần đọc dump và ghi log. Nếu dùng `SQLFILE`, Data Pump cần ghi file SQL vào directory.

Quyền database trên directory object và quyền filesystem của OS là hai lớp riêng biệt:

- `GRANT READ, WRITE ON DIRECTORY` cho phép user dùng directory qua Oracle.
- Quyền filesystem phải cho phép tài khoản OS chạy database đọc hoặc ghi thư mục thật.

Nếu một trong hai lớp thiếu quyền, job có thể báo lỗi truy cập file dù lớp còn lại đã được cấu hình đúng.

### 2.3. Tạo thư mục và cấp quyền trên hệ điều hành

Ví dụ trên Linux, quản trị viên hệ điều hành tạo thư mục và cấp quyền cho Oracle software owner:

```bash
mkdir -p /u01/dpump
chown oracle:oinstall /u01/dpump
chmod 750 /u01/dpump
```

Tên user/group và quyền thực tế phải theo chuẩn bảo mật của máy chủ. Không dùng quyền `777` chỉ để khắc phục lỗi Data Pump. Nếu thư mục nằm trên NFS, object storage gateway hoặc shared filesystem, cần xác nhận mount, quyền truy cập, dung lượng, quota và khả năng truy cập từ mọi instance có thể chạy worker.

### 2.4. Directory mặc định DATA_PUMP_DIR

Oracle thường cung cấp directory object `DATA_PUMP_DIR` trong các cài đặt được hỗ trợ. Có thể kiểm tra:

```sql
SELECT directory_name, directory_path
FROM dba_directories
WHERE directory_name = 'DATA_PUMP_DIR';
```

Không nên mặc định đường dẫn hoặc quyền của `DATA_PUMP_DIR` giống nhau giữa mọi môi trường. Hãy xác nhận server-side path, dung lượng và grants trước khi dùng. Trong hệ thống production, directory riêng theo mục đích và quyền giới hạn thường dễ quản trị hơn.

## 3. Các chế độ export và import

Data Pump hỗ trợ nhiều phạm vi công việc. Chọn mode phù hợp giúp giới hạn dữ liệu được di chuyển và giảm thời gian xử lý.

| Mode | Tham số | Phạm vi |
|---|---|---|
| Full database | `FULL=YES` | Export/import phạm vi database theo quyền và đối tượng được hỗ trợ. |
| Schema | `SCHEMAS=...` | Một hoặc nhiều schema. |
| Table | `TABLES=...` | Một hoặc nhiều bảng, có thể chỉ định partition tùy nhu cầu. |
| Tablespace | `TABLESPACES=...` | Các đối tượng thuộc phạm vi tablespace được chọn. |
| Transportable | `TRANSPORTABLE=...` cùng tùy chọn liên quan | Di chuyển tablespace theo cơ chế transportable, có điều kiện về tính tương thích và self-contained. |

Ví dụ schema export:

```text
SCHEMAS=APP
```

Export một số bảng:

```text
TABLES=APP.CUSTOMERS,APP.ORDERS
```

Export full database:

```text
FULL=YES
```

Full export cần quyền Data Pump phù hợp, thường liên quan role `DATAPUMP_EXP_FULL_DATABASE`; full import có thể cần `DATAPUMP_IMP_FULL_DATABASE`. Quyền cụ thể phụ thuộc thao tác, object và phiên bản. Không cấp role rộng chỉ để tránh một lỗi quyền chưa được phân tích.

User có thể export schema của chính mình trong phạm vi quyền sở hữu và các quyền cần thiết. Khi export schema khác, bảng của user khác hoặc thực hiện full export, cần kiểm tra role và grants tương ứng.

### 3.1. Chọn nội dung export/import

Tham số `CONTENT` xác định phần nội dung:

| Giá trị | Ý nghĩa |
|---|---|
| `ALL` | Metadata và dữ liệu. Đây là mặc định thông dụng. |
| `DATA_ONLY` | Chỉ dữ liệu, không tạo metadata đối tượng. |
| `METADATA_ONLY` | Chỉ metadata, không nạp dữ liệu bảng. |

Ví dụ chỉ export cấu trúc:

```text
CONTENT=METADATA_ONLY
```

Chỉ export dữ liệu:

```text
CONTENT=DATA_ONLY
```

Khi import `DATA_ONLY`, bảng đích và cấu trúc cần thiết phải tồn tại hoặc được chuẩn bị phù hợp. Khi import `METADATA_ONLY`, dữ liệu bảng sẽ không được nạp.

### 3.2. Ước tính dung lượng và thời gian

Data Pump có thể ước tính dung lượng trước khi export:

```text
ESTIMATE_ONLY=YES
ESTIMATE=BLOCKS
```

Hoặc dùng thống kê:

```text
ESTIMATE=STATISTICS
```

Ước tính không phải cam kết kích thước dump cuối cùng. Compression, metadata, dữ liệu LOB, độ phân bố và cách tổ chức dump file có thể làm dung lượng thực tế khác. Cần có vùng đệm và giám sát dung lượng filesystem trong khi job chạy.

## 4. Sử dụng expdp để export

### 4.1. Cú pháp cơ bản

Một lệnh export schema thường có dạng:

```bash
expdp app_migration@ORCLPDB \
  SCHEMAS=APP \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_export_%U.dmp \
  LOGFILE=app_export.log
```

Sau khi nhập lệnh, client có thể yêu cầu mật khẩu nếu chưa dùng cơ chế xác thực an toàn. Tránh đặt mật khẩu trực tiếp trong command line vì nó có thể xuất hiện trong process list, shell history hoặc log công cụ quản trị. Có thể dùng prompt tương tác, external password store hoặc phương thức credential được tổ chức phê duyệt.

Trong ví dụ:

- `SCHEMAS=APP` chọn schema cần export.
- `DIRECTORY=DP_DIR` chỉ directory object trên database server.
- `DUMPFILE=app_export_%U.dmp` đặt mẫu tên dump file; `%U` cho phép Data Pump tạo nhiều file khi cần.
- `LOGFILE=app_export.log` tạo log ở directory server-side.

### 4.2. Export bảng cụ thể

```bash
expdp app_migration@ORCLPDB \
  TABLES=APP.CUSTOMERS,APP.ORDERS \
  DIRECTORY=DP_DIR \
  DUMPFILE=customer_orders_%U.dmp \
  LOGFILE=customer_orders_export.log
```

Có thể export partition hoặc subpartition của bảng nếu cần trích xuất một phần dữ liệu. Cần xác nhận cú pháp `TABLES` theo đối tượng và phiên bản. Export một bảng có thể kéo theo metadata phụ thuộc; không nên mặc định rằng dump chỉ chứa đúng một file bảng độc lập với các đối tượng liên quan.

### 4.3. Dùng PARFILE để quản lý tham số

Khi có nhiều tham số, nên dùng parameter file để dễ đọc và lưu cấu hình công việc. Ví dụ `app_export.par` trên máy chạy tiện ích client:

```text
DIRECTORY=DP_DIR
DUMPFILE=app_export_%U.dmp
LOGFILE=app_export.log
JOB_NAME=APP_EXPORT_JOB
SCHEMAS=APP
PARALLEL=4
FILESIZE=10G
METRICS=YES
LOGTIME=ALL
```

Chạy:

```bash
expdp app_migration@ORCLPDB PARFILE=app_export.par
```

`PARFILE` là file được client đọc trên máy chạy `expdp`; còn `DUMPFILE` và `LOGFILE` vẫn nằm ở server-side directory. Không đặt mật khẩu thật trong parfile nếu file có thể được lưu trong source control, thư mục chia sẻ hoặc log triển khai.

### 4.4. Chia dump thành nhiều file

Với dữ liệu lớn, dùng `%U` cùng `PARALLEL` và `FILESIZE`:

```text
DUMPFILE=app_export_%U.dmp
PARALLEL=4
FILESIZE=10G
```

`%U` cho phép tạo tên file theo số thứ tự, chẳng hạn `app_export_01.dmp`, `app_export_02.dmp`. `FILESIZE` giới hạn kích thước từng dump file theo cấu hình. `PARALLEL` đặt số worker tối đa được yêu cầu; hiệu quả thực tế phụ thuộc tài nguyên CPU, I/O, storage và khả năng xử lý của database.

Một dump set có thể gồm nhiều file. Khi import, cần cung cấp đầy đủ các file thuộc dump set. Thiếu một file có thể khiến job không đọc được toàn bộ dữ liệu.

### 4.5. Lọc đối tượng và dữ liệu

`INCLUDE` và `EXCLUDE` cho phép chọn hoặc bỏ qua loại đối tượng cụ thể. Không dùng đồng thời hai tham số này trong cùng job.

Ví dụ chỉ export bảng và index:

```text
INCLUDE=TABLE
INCLUDE=INDEX
```

Ví dụ loại bỏ thống kê optimizer:

```text
EXCLUDE=STATISTICS
```

Để lọc dòng của một bảng, có thể dùng `QUERY`. Ví dụ trong parfile:

```text
TABLES=APP.ORDERS
QUERY=APP.ORDERS:"WHERE ORDER_DATE >= DATE '2026-01-01'"
```

`QUERY` lọc dữ liệu export; cần xác định rõ schema và bảng khi có nhiều bảng cùng tên hoặc job có nhiều table. Điều kiện phải phù hợp kiểu dữ liệu và cú pháp Oracle SQL. Nếu dùng ký tự đặc biệt, dấu nháy hoặc shell quoting, nên thử parfile ở môi trường kiểm thử trước.

### 4.6. Export nhất quán tại một thời điểm

Khi dữ liệu thay đổi trong lúc export, có thể cần một ảnh chụp logic nhất quán. Data Pump hỗ trợ `FLASHBACK_SCN` hoặc `FLASHBACK_TIME` trong các trường hợp phù hợp.

Ví dụ:

```text
FLASHBACK_SCN=123456789012
```

Export sẽ đọc dữ liệu theo SCN đã chọn nếu điều kiện flashback và undo retention cho phép. Cần xác định SCN hợp lệ, bảo đảm đủ undo và kiểm tra thời gian chạy job. Nếu undo không đủ, job có thể thất bại với lỗi snapshot/undo. Không nên chọn một SCN quá cũ mà không đánh giá khả năng cung cấp consistent read.

## 5. Sử dụng impdp để import

### 5.1. Import schema từ dump file

Ví dụ import schema `APP` vào database đích:

```bash
impdp app_migration@TARGETPDB \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_export_%U.dmp \
  LOGFILE=app_import.log \
  SCHEMAS=APP
```

Dump file phải được đặt trong directory server-side của database đích, không chỉ nằm trên máy client chạy `impdp`. Nếu file đang ở máy khác, cần chuyển tới storage mà database đích truy cập được hoặc dùng `NETWORK_LINK` để đọc trực tiếp từ database nguồn.

### 5.2. Remap schema

Khi chuyển schema nguồn sang tên khác ở đích:

```text
REMAP_SCHEMA=APP:APP_TEST
```

Ví dụ:

```bash
impdp app_migration@TARGETPDB \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_export_%U.dmp \
  LOGFILE=app_test_import.log \
  REMAP_SCHEMA=APP:APP_TEST
```

`REMAP_SCHEMA` ánh xạ owner nguồn sang owner đích. User đích cần tồn tại hoặc được tạo theo quy trình phù hợp; Data Pump không phải lúc nào cũng tạo user và cấp đầy đủ quyền đăng nhập theo yêu cầu ứng dụng. Cần kiểm tra tablespace, quota, role, grants, database link, directory và object dependency sau import.

### 5.3. Remap tablespace

`REMAP_TABLESPACE` ánh xạ segment từ tablespace nguồn sang tablespace đích:

```text
REMAP_TABLESPACE=APP_DATA:APP_DATA_TEST
REMAP_TABLESPACE=APP_INDEX:APP_INDEX_TEST
```

Điều này hữu ích khi database đích có quy hoạch storage khác. Hãy tạo tablespace đích, xác nhận dung lượng, autoextend, encryption, quota và tiêu chuẩn đặt tên trước khi import. Một số đối tượng hoặc kiểu import đặc biệt có quy tắc riêng; không giả định mọi tham chiếu tablespace đều được remap giống nhau.

### 5.4. Xử lý bảng đã tồn tại

Khi bảng đích đã tồn tại, `TABLE_EXISTS_ACTION` quyết định cách import dữ liệu:

| Giá trị | Hành vi |
|---|---|
| `SKIP` | Bỏ qua bảng đã tồn tại. Đây là mặc định phổ biến. |
| `APPEND` | Nạp thêm dòng vào bảng hiện có. |
| `TRUNCATE` | Xóa dữ liệu hiện có bằng truncate rồi nạp dữ liệu mới. |
| `REPLACE` | Drop bảng hiện có, tạo lại từ metadata dump rồi nạp dữ liệu. |

Ví dụ:

```text
TABLE_EXISTS_ACTION=APPEND
```

Chọn sai hành động có thể tạo dữ liệu trùng, xóa dữ liệu hiện có hoặc làm mất thay đổi schema ở đích. `TRUNCATE` và `REPLACE` có tác động phá hủy dữ liệu/đối tượng; cần xác nhận backup, phạm vi và phê duyệt trước khi dùng. Hành vi có thể phụ thuộc kiểu import và các tham số khác.

### 5.5. Chỉ import metadata hoặc dữ liệu

Chỉ tạo đối tượng:

```text
CONTENT=METADATA_ONLY
```

Chỉ nạp dòng dữ liệu:

```text
CONTENT=DATA_ONLY
```

Các chế độ này hữu ích khi cần triển khai schema trước, sau đó nạp dữ liệu hoặc khi bảng đã được tạo bằng migration script. Cần bảo đảm constraint, index, trigger và sequence phù hợp với thứ tự import và yêu cầu ứng dụng.

### 5.6. Xem trước DDL bằng SQLFILE

`SQLFILE` yêu cầu `impdp` ghi các lệnh DDL dự kiến ra file thay vì thực thi chúng. Ví dụ:

```bash
impdp app_migration@TARGETPDB \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_export_%U.dmp \
  SQLFILE=app_preview.sql \
  SCHEMAS=APP
```

File `app_preview.sql` được ghi ở directory server-side. Có thể dùng nó để xem trước object, owner, tablespace và DDL trước khi import thực tế. `SQLFILE` không phải bản import thử đầy đủ: nó không nạp dữ liệu và không chứng minh mọi bước import sẽ thành công.

## 6. Di chuyển trực tiếp qua NETWORK_LINK

Data Pump có thể đọc dữ liệu trực tiếp từ database nguồn qua database link, không cần tạo dump file trung gian. Ví dụ import schema từ database nguồn:

```bash
impdp app_migration@TARGETPDB \
  NETWORK_LINK=SOURCE_LINK \
  SCHEMAS=APP \
  LOGFILE=network_import.log \
  DIRECTORY=DP_DIR
```

`SOURCE_LINK` là database link được tạo trong database đích và kết nối tới database nguồn. Job chạy ở phía database đích; dữ liệu được đọc qua kết nối database link. Log vẫn được ghi ở directory server-side của database đích. Không có dump file trong ví dụ này.

Các điểm cần chuẩn bị:

- Database link phải kết nối được tới đúng service nguồn.
- User qua database link phải có quyền đọc đối tượng và metadata cần export.
- Network giữa hai database phải đủ ổn định và có băng thông phù hợp.
- Phiên bản, character set, kiểu dữ liệu và tính năng phải tương thích.
- Cần đánh giá tải trên cả nguồn và đích; network import không miễn phí tài nguyên.

`NETWORK_LINK` có thể hữu ích khi không muốn quản lý dump file, nhưng không thay thế kế hoạch backup. Nếu kết nối bị gián đoạn hoặc dữ liệu lớn, cần đánh giá khả năng restart và thời gian chạy. Đối với migration quan trọng, dump file có thể dễ kiểm soát, kiểm tra và chuyển giao hơn.

## 7. Tính tương thích và các tình huống migration

### 7.1. Khác phiên bản Oracle

Khi export từ phiên bản mới sang phiên bản cũ, cần kiểm tra mức tương thích của dump metadata và tính năng. Tham số `VERSION` có thể giới hạn phiên bản metadata mà Data Pump tạo:

```text
VERSION=19.0
```

Giá trị phải phù hợp phiên bản đích và tài liệu Oracle. `VERSION` không biến một tính năng mới thành tính năng cũ; đối tượng hoặc thuộc tính không được phiên bản đích hỗ trợ có thể không export/import được. Cần thử trên bản sao và xem log cảnh báo.

### 7.2. Transportable tablespaces

Transportable tablespaces cho phép di chuyển datafile của tablespace cùng metadata thay vì export toàn bộ dòng dữ liệu theo cách thông thường. Cách này có thể nhanh với dữ liệu lớn, nhưng yêu cầu tablespace set tự chứa (self-contained), tương thích nền tảng/endian hoặc có bước chuyển đổi phù hợp, và phải tuân thủ trình tự read-only/export/copy/import.

Đây là kỹ thuật migration chuyên biệt; không nên coi `TRANSPORTABLE=ALWAYS` là một tham số thay thế đơn giản cho schema export. Hãy kiểm tra điều kiện self-contained, datafile, endian, encryption và version trước khi triển khai.

### 7.3. Di chuyển dữ liệu mã hóa

Nếu dữ liệu nguồn dùng TDE, cần xem xét cả encryption của tablespace/column và encryption của dump file. Data Pump có thể yêu cầu keystore hoặc mật khẩu export/import phù hợp với kiểu mã hóa. Khi di chuyển sang database khác, cần lập kế hoạch chuyển khóa TDE theo quy trình an toàn nếu dữ liệu hoặc dump cần được giải mã tại đích.

Không đưa keystore password, encryption password hoặc key material vào parfile có quyền đọc rộng. Lưu credential trong secret manager và thử import bằng chính cơ chế mã hóa dự kiến.

## 8. Theo dõi và điều khiển Data Pump job

### 8.1. Đặt JOB_NAME và LOGTIME/METRICS

Đặt tên job giúp DBA nhận diện và attach khi cần:

```text
JOB_NAME=APP_EXPORT_20261114
LOGTIME=ALL
METRICS=YES
STATUS=60
```

- `JOB_NAME` đặt tên cho Data Pump job.
- `LOGTIME=ALL` ghi timestamp cho các thông báo log trên phiên bản hỗ trợ.
- `METRICS=YES` bổ sung thông tin thống kê xử lý vào log.
- `STATUS=60` yêu cầu hiển thị trạng thái định kỳ theo khoảng giây trong khi client chờ.

Các tham số hiển thị và log có thể khác giữa phiên bản. Dùng `HELP=Y` hoặc tài liệu phiên bản để xác nhận tham số hỗ trợ.

### 8.2. Attach vào job đang chạy

Nếu client bị đóng hoặc mất kết nối, job server-side có thể vẫn tiếp tục chạy. DBA có thể kết nối lại và attach bằng job name:

```bash
expdp app_migration@ORCLPDB ATTACH=APP_EXPORT_20261114
```

Hoặc với import:

```bash
impdp app_migration@TARGETPDB ATTACH=APP_IMPORT_20261114
```

Trong interactive command mode, có thể xem trạng thái:

```text
Export> STATUS
```

Thoát khỏi client bằng `EXIT_CLIENT` sẽ tách client khỏi job; nó không đồng nghĩa với việc dừng job. Cần phân biệt thao tác detach client với stop hoặc kill job.

### 8.3. Dừng và tiếp tục job

Trong interactive mode, Data Pump hỗ trợ các lệnh điều khiển như:

```text
Export> STOP_JOB=IMMEDIATE
```

Sau khi job dừng, có thể attach lại và dùng:

```text
Export> START_JOB
```

`STOP_JOB=IMMEDIATE` dừng job ngay; job thường có thể được khởi động lại nếu metadata và file cần thiết còn nguyên. `STOP_JOB` không phải thao tác xóa job. Trước khi dừng, hãy xem worker, trạng thái hiện tại, dung lượng và tác động đến ứng dụng.

`KILL_JOB` chấm dứt và loại bỏ job theo cơ chế Data Pump; đây là lựa chọn mạnh hơn và có thể làm mất khả năng resume của job. Không dùng khi chỉ muốn tạm dừng để bảo trì.

### 8.4. Theo dõi bằng data dictionary

Một số view hữu ích:

```sql
SELECT owner_name, job_name, operation, job_mode,
       state, degree, attached_sessions, datapump_sessions
FROM dba_datapump_jobs
ORDER BY owner_name, job_name;
```

```sql
SELECT owner_name, job_name, instance_id, saddr, session_type
FROM dba_datapump_sessions
ORDER BY owner_name, job_name;
```

View `DBA_DATAPUMP_JOBS` và `DBA_DATAPUMP_SESSIONS` cho biết job, trạng thái và session liên quan. Tên cột có thể khác theo phiên bản; kiểm tra data dictionary thực tế nếu truy vấn không khớp.

Có thể theo dõi tiến độ qua `V$SESSION_LONGOPS` trong một số pha xử lý:

```sql
SELECT
    sid,
    serial#,
    opname,
    sofar,
    totalwork,
    units,
    elapsed_seconds,
    time_remaining
FROM v$session_longops
WHERE opname LIKE 'SYS_EXPORT%'
   OR opname LIKE 'SYS_IMPORT%'
ORDER BY start_time DESC;
```

`V$SESSION_LONGOPS` không nhất thiết hiển thị tiến độ đầy đủ cho mọi pha hoặc mọi loại object. Kết hợp log, interactive `STATUS`, các view Data Pump và theo dõi storage/CPU/I/O để đánh giá.

### 8.5. Job master table

Data Pump tạo master table trong schema sở hữu job để lưu trạng thái và metadata điều khiển. Khi job hoàn tất thành công, master table thường được dọn theo cơ chế Data Pump. Với job dừng hoặc lỗi, metadata có thể còn lại để hỗ trợ attach/resume.

Không xóa master table thủ công khi chưa hiểu trạng thái job. Xóa nhầm có thể làm mất khả năng tiếp tục hoặc gây khó khăn khi dọn dẹp. Hãy dùng `ATTACH`, `STATUS`, `STOP_JOB`, `START_JOB` hoặc `KILL_JOB` theo đúng mục tiêu.

## 9. Data Pump trong môi trường RAC

Trong Oracle RAC, Data Pump có thể sử dụng nhiều instance khi cấu hình cluster và storage cho phép. Nếu directory path chỉ tồn tại trên một node, worker chạy ở node khác có thể không truy cập được dump/log.

Các điểm cần kiểm tra:

- Directory object trỏ tới shared filesystem hoặc storage được mọi node liên quan truy cập.
- Quyền OS của Oracle owner nhất quán trên các node.
- Dump file và log file không nằm trên filesystem local chỉ có một node nhìn thấy nếu job có thể phân tán.
- `PARALLEL` và `CLUSTER` được chọn theo năng lực storage và mục tiêu vận hành.

Nếu chỉ một node có thể truy cập thư mục, có thể cân nhắc `CLUSTER=NO` để giới hạn job ở instance kết nối trong các tình huống được hỗ trợ. Tuy nhiên, đây không thay thế việc thiết kế storage dùng chung đúng cách. Hãy xác nhận cú pháp, service và hành vi trên phiên bản RAC đang dùng.

## 10. Bảo mật khi chạy Data Pump

### 10.1. Nguyên tắc quyền tối thiểu

- Cấp `READ`/`WRITE` trên đúng directory object cần dùng.
- Chỉ cấp quyền export/import schema khác hoặc full database khi có nhiệm vụ rõ ràng.
- Không cấp `DATAPUMP_EXP_FULL_DATABASE` hoặc `DATAPUMP_IMP_FULL_DATABASE` theo thói quen.
- Bảo vệ filesystem server-side; không cho user OS không liên quan đọc dump file.
- Đặt log và dump trong vùng lưu trữ có retention và quyền truy cập phù hợp.
- Kiểm tra grants, roles và owner sau import.

Dump file có thể chứa dữ liệu nhạy cảm ở dạng có thể đọc hoặc giải mã tùy cấu hình. Hãy bảo vệ dump như dữ liệu production nếu chưa được masking hoặc mã hóa phù hợp.

### 10.2. Mã hóa dump file

Data Pump hỗ trợ mã hóa dump file bằng các chế độ `ENCRYPTION` tùy phiên bản và cấu hình. Ví dụ minh họa:

```text
ENCRYPTION=ALL
ENCRYPTION_MODE=PASSWORD
ENCRYPTION_PASSWORD=<secret>
```

Các tùy chọn có thể gồm mã hóa dữ liệu, metadata hoặc toàn bộ dump; mode có thể dựa trên password, transparent hoặc dual tùy phiên bản. Hãy kiểm tra tài liệu phiên bản trước khi chọn. Không đưa mật khẩu thật vào command line hoặc parfile lưu lâu dài. Mật khẩu cần được trao đổi qua secret manager và có thể lấy lại trong thời gian backup còn hiệu lực.

Nếu dùng transparent encryption dựa trên TDE, việc import phụ thuộc keystore và khóa liên quan. Nếu dùng password mode, mất mật khẩu khiến dump không thể giải mã. Vì vậy, credential là một thành phần của quy trình backup/restore, không phải thông tin phụ.

### 10.3. Bảo vệ thông tin đăng nhập

Tránh viết `username/password@service` với mật khẩu thật trong shell history, script hoặc lịch chạy. Các phương án an toàn hơn tùy môi trường gồm:

- Để tiện ích hỏi mật khẩu qua prompt.
- Dùng Oracle Secure External Password Store hoặc cơ chế wallet được quản trị.
- Dùng tài khoản dịch vụ riêng và secret manager tích hợp với scheduler.
- Giới hạn quyền đọc parfile, script, log và thư mục làm việc.

Không đặt credential trong `PARFILE` chỉ vì muốn gom mọi tham số vào một file. Parfile nên chứa cấu hình job; bí mật cần có vòng đời và quyền truy cập riêng.

## 11. Lỗi thường gặp và cách xử lý

| Lỗi hoặc hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `ORA-39002: invalid operation` | Tham số hoặc thao tác Data Pump không hợp lệ trong ngữ cảnh hiện tại. | Đọc log đầy đủ, kiểm tra cú pháp và quyền. |
| `ORA-39070: Unable to open the log file` | Directory object, quyền database hoặc quyền OS không phù hợp; filesystem không sẵn sàng. | Kiểm tra `DBA_DIRECTORIES`, grants và quyền OS trên database server. |
| `ORA-39087: directory name ... is invalid` | Directory object không tồn tại hoặc tên không đúng. | Kiểm tra tên directory và container hiện tại. |
| `ORA-29283: invalid file operation` | Oracle server process không thể mở/ghi file tại path. | Kiểm tra path server-side, mount, OS permission, dung lượng và SELinux/ACL nếu có. |
| `ORA-31640` / `ORA-27037` | Không đọc được dump file hoặc file không tồn tại ở vị trí server nhìn thấy. | Xác nhận file nằm ở server-side directory, tên đúng và quyền đọc. |
| `ORA-31684` | Đối tượng đã tồn tại khi import. | Xem log và chọn `TABLE_EXISTS_ACTION` hoặc xử lý object theo kế hoạch. |
| `ORA-39151` | Đối tượng được bỏ qua do đã tồn tại hoặc chính sách import. | Xác nhận hành động import và object đích. |
| Job chậm hoặc không có tiến độ rõ | I/O, CPU, network, lock, LOB hoặc worker thiếu tài nguyên. | Kiểm tra `STATUS`, log, `V$SESSION_LONGOPS`, storage và wait event. |
| Import thiếu dữ liệu | Thiếu dump piece, filter không đúng hoặc job lỗi giữa chừng. | Kiểm tra dump set, log, tham số `QUERY/INCLUDE/EXCLUDE` và trạng thái job. |
| Import thiếu quyền | User đích không có quota, object privilege hoặc quyền tạo object. | Xác định object cụ thể và cấp quyền tối thiểu. |

Thông báo lỗi gốc thường xuất hiện trước các lỗi tổng hợp `ORA-390xx`. Đọc toàn bộ log và xác định lỗi đầu tiên giúp tìm nguyên nhân chính xác hơn.

## 12. Quy trình migration mẫu

Giả sử cần chuyển schema `APP` từ database nguồn sang PDB thử nghiệm, đổi owner thành `APP_TEST` và chuyển segment sang tablespace `APP_DATA_TEST`.

### 12.1. Chuẩn bị nguồn và đích

Ở nguồn:

- Xác nhận schema, object, dung lượng, LOB và dependency.
- Chọn thời điểm dữ liệu nhất quán hoặc lên kế hoạch downtime nếu cần.
- Xác nhận user export có quyền cần thiết.

Ở đích:

- Tạo tablespace đích và user `APP_TEST` theo quy trình quản trị.
- Tạo directory object trỏ tới storage server-side.
- Cấp quyền directory cho user migration.
- Kiểm tra version, character set, quota, grants và dung lượng.

### 12.2. Export

Tạo `app_export.par` trên máy chạy client:

```text
DIRECTORY=DP_DIR
DUMPFILE=app_migration_%U.dmp
LOGFILE=app_migration_export.log
JOB_NAME=APP_MIGRATION_EXPORT
SCHEMAS=APP
PARALLEL=4
FILESIZE=10G
LOGTIME=ALL
METRICS=YES
```

Chạy:

```bash
expdp app_migration@SOURCEPDB PARFILE=app_export.par
```

Đợi job hoàn tất và kiểm tra log. Sau đó chuyển toàn bộ dump pieces từ storage server-side nguồn sang nơi database đích có thể đọc. Xác minh đủ file, kích thước và checksum trước khi import.

### 12.3. Xem trước DDL

Trên đích, dùng `SQLFILE` để tạo DDL preview:

```bash
impdp app_migration@TARGETPDB \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_migration_%U.dmp \
  SQLFILE=app_migration_preview.sql \
  REMAP_SCHEMA=APP:APP_TEST \
  REMAP_TABLESPACE=APP_DATA:APP_DATA_TEST
```

Đọc file preview trên server-side storage và xác nhận owner, tablespace, object cùng các lệnh DDL dự kiến. Đây là bước kiểm tra metadata, chưa nạp dữ liệu.

### 12.4. Import

Sau khi phê duyệt, chạy import:

```bash
impdp app_migration@TARGETPDB \
  DIRECTORY=DP_DIR \
  DUMPFILE=app_migration_%U.dmp \
  LOGFILE=app_migration_import.log \
  JOB_NAME=APP_MIGRATION_IMPORT \
  REMAP_SCHEMA=APP:APP_TEST \
  REMAP_TABLESPACE=APP_DATA:APP_DATA_TEST \
  LOGTIME=ALL \
  METRICS=YES
```

Nếu cần import lại vào schema đã có bảng, hãy xác định `TABLE_EXISTS_ACTION` theo mục tiêu. Không thêm `REPLACE` hoặc `TRUNCATE` chỉ để bỏ qua lỗi object exists.

### 12.5. Xác nhận sau import

- Đọc log và xác định mọi lỗi, warning hoặc object bị bỏ qua.
- So sánh danh sách object, số dòng và dữ liệu nghiệp vụ với nguồn theo tiêu chí đã thống nhất.
- Kiểm tra invalid object và compile lại theo quy trình.
- Kiểm tra index, constraint, trigger, sequence, grants, role, synonym và database link.
- Kiểm tra user đích có quota và quyền tối thiểu.
- Chạy smoke test ứng dụng trên PDB đích.
- Lưu dump, log và checksum theo retention đã phê duyệt.

## 13. Nguyên tắc vận hành tốt

- Luôn nhớ `DIRECTORY` là directory object server-side; `PARFILE` là file client-side.
- Xác nhận database service và container trước khi chạy export/import.
- Dùng `PARFILE` cho job nhiều tham số, nhưng không lưu mật khẩu trong đó.
- Dùng tên `JOB_NAME`, `LOGTIME`, `METRICS` để dễ giám sát và điều tra.
- Dùng `%U`, `PARALLEL` và `FILESIZE` khi cần nhiều dump piece; bảo đảm import có đủ tất cả file.
- Ước tính dung lượng, kiểm tra filesystem và băng thông trước khi chạy job lớn.
- Chọn `CONTENT`, `SCHEMAS`, `TABLES`, `INCLUDE`, `EXCLUDE` và `QUERY` theo phạm vi cần di chuyển.
- Dùng `SQLFILE` để xem trước DDL khi import có tác động lớn.
- Dùng `ATTACH` để quản lý job server-side; phân biệt detach, stop, resume và kill.
- Trong RAC, xác nhận directory storage được worker trên các node truy cập.
- Bảo vệ dump file, log và credential; mã hóa dump nếu dữ liệu nhạy cảm cần được bảo vệ.
- Đọc log đầy đủ và xác nhận dữ liệu sau import; không xem exit code là bằng chứng duy nhất.

## Kết luận

Data Pump `expdp` và `impdp` là công cụ di chuyển dữ liệu logic linh hoạt. Client khởi tạo và điều khiển job, còn database server thực hiện công việc và truy cập dump/log qua directory object. Hiểu rõ ranh giới client/server, quyền database và quyền filesystem là điều kiện đầu tiên để tránh lỗi đường dẫn và truy cập file. Khi kết hợp đúng mode export/import, parfile, filter, remap, giám sát job, kiểm soát bảo mật và xác nhận sau import, DBA có thể di chuyển schema hoặc dữ liệu giữa các môi trường một cách có kiểm soát và có thể truy vết.

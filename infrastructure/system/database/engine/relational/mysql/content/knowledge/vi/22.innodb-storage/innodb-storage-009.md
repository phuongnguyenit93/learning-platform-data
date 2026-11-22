# Temporary tablespace, undo tablespace và quản lý dung lượng

Bài học thuộc chương **Lưu trữ InnoDB** của module **DATABASE_MYSQL**. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý vấn đề vận hành cơ sở dữ liệu quan hệ. Temporary tablespace và undo tablespace đều chiếm dung lượng đĩa, nhưng phục vụ các mục đích khác nhau. Muốn xử lý đúng tình trạng file InnoDB tăng kích thước, cần xác định file đó lưu dữ liệu tạm của session, rollback segment cho temporary table hay undo log phục vụ MVCC của bảng thông thường.

Sau bài này, bạn có thể phân biệt session temporary tablespace, global temporary tablespace và undo tablespace; hiểu vai trò của undo log, rollback segment và purge; theo dõi dung lượng bằng INFORMATION_SCHEMA; nhận diện transaction dài làm history list tăng; cấu hình giới hạn temporary tablespace và tự động truncate undo tablespace; đồng thời xử lý sự cố dung lượng mà không xóa file InnoDB thủ công.

## 1. Ba loại tablespace cần phân biệt

Trong InnoDB, tên gọi “temporary” và “undo” dễ gây nhầm lẫn vì cả hai đều liên quan đến dữ liệu không phải bản ghi lâu dài của bảng nghiệp vụ.

Có ba thành phần chính:

1. **Session temporary tablespace:** lưu user-created temporary table và internal temporary table trên đĩa do optimizer tạo.
2. **Global temporary tablespace:** thường là file **ibtmp1**, lưu rollback segment cho thay đổi trên user-created temporary table.
3. **Undo tablespace:** lưu undo log của transaction thao tác trên các bảng thông thường, phục vụ rollback và consistent read/MVCC.

| Thành phần | Mục đích | Dữ liệu điển hình | Vòng đời dung lượng |
|---|---|---|---|
| Session temporary tablespace | Lưu temporary table theo session và internal temp table của optimizer | Kết quả trung gian, bảng tạm do ứng dụng tạo | Khi session ngắt kết nối, tablespace được truncate và trả về pool |
| Global temporary tablespace (ibtmp1) | Lưu rollback segment cho thay đổi trên user-created temporary table | Undo cho INSERT/UPDATE/DELETE trên temporary table | Được tạo lại khi server khởi động bình thường; file có thể autoextend |
| Undo tablespace | Lưu undo log cho bảng thông thường | Phiên bản dữ liệu cũ, thông tin rollback | Có thể tăng theo workload; có thể truncate khi undo không còn được transaction/read view sử dụng |

Điểm cần nhớ: ibtmp1 không phải nơi chứa toàn bộ temporary table trên đĩa. Các temporary table của session và internal temporary table của optimizer dùng session temporary tablespace; global temporary tablespace chủ yếu lưu rollback segment cho thay đổi trên temporary table do người dùng tạo.

## 2. Session temporary tablespace

Session temporary tablespace là tablespace InnoDB được cấp cho một session khi session cần tạo temporary table trên đĩa.

Nó lưu:

- Temporary table do người dùng tạo bằng CREATE TEMPORARY TABLE.
- Internal temporary table trên đĩa mà optimizer tạo trong quá trình xử lý truy vấn.

Trong MySQL 9.7, InnoDB luôn được dùng làm storage engine cho internal temporary table trên đĩa.

### Pool của session temporary tablespace

Khi server khởi động, InnoDB tạo pool ban đầu gồm 10 session temporary tablespace. Khi session lần đầu cần một temporary table trên đĩa, InnoDB cấp tablespace từ pool.

Một session có thể được cấp tối đa hai tablespace:

- Một tablespace cho user-created temporary tables.
- Một tablespace cho internal temporary tables do optimizer tạo.

Khi session disconnect, các session temporary tablespace được truncate và trả về pool. Pool có thể được mở rộng tự động khi cần, nhưng số lượng tablespace trong pool không tự giảm trong thời gian server chạy.

Điều này có nghĩa:

- Một session tạo temporary table lớn có thể làm file session temporary tablespace tăng kích thước.
- Khi session đóng, tablespace được truncate và trả lại pool để tái sử dụng.
- Số file trong pool không nhất thiết biến mất sau khi session đóng.
- Server shutdown bình thường sẽ loại bỏ pool; pool được tạo lại khi server khởi động.

Các file session temporary tablespace thường có phần mở rộng .ibt và nằm trong thư mục mặc định #innodb_temp bên dưới data directory.

### Cấu hình vị trí

Biến innodb_temp_tablespaces_dir xác định nơi InnoDB tạo pool session temporary tablespace.

Kiểm tra:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_temp_tablespaces_dir';
~~~

Trong MySQL 9.7:

| Thuộc tính | Giá trị |
|---|---|
| Scope | GLOBAL |
| Dynamic | No |
| Default | #innodb_temp |

Đây là biến startup-only. Muốn đổi vị trí, cấu hình trong file option rồi khởi động lại server theo quy trình vận hành. Không di chuyển hoặc xóa file trong thư mục này khi server đang chạy.

## 3. Global temporary tablespace (ibtmp1)

Global temporary tablespace là tablespace tạm dùng chung của InnoDB. File mặc định thường là ibtmp1.

Nó lưu rollback segment cho thay đổi trên temporary table do người dùng tạo. Ví dụ, khi session chạy INSERT, UPDATE hoặc DELETE trên một temporary table InnoDB, undo log tương ứng được đặt trong rollback segment của global temporary tablespace.

Các undo log này chỉ cần cho rollback khi server đang chạy; chúng không cần redo logging để phục hồi crash như undo log của bảng thông thường.

### Vòng đời của ibtmp1

Theo cấu hình mặc định:

- File ibtmp1 được tạo khi MySQL khởi động.
- File có kích thước ban đầu hơi lớn hơn 12 MB.
- File autoextend khi cần thêm dung lượng.
- Khi server shutdown bình thường, global temporary tablespace được loại bỏ.
- Khi server khởi động lại, tablespace được tạo mới.
- Nếu server dừng bất thường, file có thể còn lại trên filesystem; lần khởi động sau MySQL xử lý việc tạo lại theo quy trình khởi động.

Không xóa ibtmp1 khi server đang chạy. Nếu cần thu hồi dung lượng file global temporary tablespace đã phình to, cách thông thường là lên lịch restart MySQL trong cửa sổ bảo trì phù hợp.

### Kiểm tra cấu hình và kích thước

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_temp_data_file_path';

SELECT
    FILE_NAME,
    TABLESPACE_NAME,
    INITIAL_SIZE,
    TOTAL_EXTENTS * EXTENT_SIZE AS total_size_bytes,
    DATA_FREE,
    MAXIMUM_SIZE
FROM INFORMATION_SCHEMA.FILES
WHERE TABLESPACE_NAME = 'innodb_temporary';
~~~

Giá trị mặc định của innodb_temp_data_file_path là:

~~~text
ibtmp1:12M:autoextend
~~~

Có thể cấu hình giới hạn tối đa, ví dụ:

~~~ini
[mysqld]
innodb_temp_data_file_path=ibtmp1:12M:autoextend:max:2G
~~~

Trong ví dụ này, file bắt đầu ở khoảng 12 MB, được phép tự mở rộng và có giới hạn 2 GB. Cấu hình này cần restart server.

Đặt giới hạn không làm truy vấn cần nhiều temporary space tự động chạy thành công. Nếu file chạm giới hạn, thao tác cần thêm không gian có thể thất bại do không thể mở rộng tablespace. Chọn giới hạn theo dung lượng đĩa và workload thực tế; không đặt quá thấp khiến truy vấn báo lỗi thường xuyên.

## 4. Temporary table, internal temporary table và tmpdir không giống nhau

Có nhiều loại file tạm trong MySQL. Không phải file nào có chữ “tmp” cũng thuộc InnoDB temporary tablespace.

| Thành phần | Dùng cho | Cấu hình/quan sát |
|---|---|---|
| User-created temporary table | Bảng tạm do ứng dụng tạo trong session | CREATE TEMPORARY TABLE, INNODB_TEMP_TABLE_INFO |
| Internal temporary table | Bảng trung gian do optimizer tạo, ví dụ một số truy vấn GROUP BY, DISTINCT, UNION, window operation | INNODB_SESSION_TEMP_TABLESPACES |
| Session temporary tablespace | File .ibt cấp cho session để lưu temporary table trên đĩa | innodb_temp_tablespaces_dir |
| Global temporary tablespace | Rollback segment cho thay đổi trên user-created temporary table | ibtmp1, innodb_temp_data_file_path |
| tmpdir | Thư mục tạm chung của MySQL cho một số hoạt động | Biến tmpdir |
| innodb_tmpdir | Thư mục file sort tạm cho một số online ALTER TABLE rebuild | Biến innodb_tmpdir |

Đặc biệt, innodb_tmpdir không phải nơi chứa session temporary tablespace hoặc ibtmp1. Nó được dùng cho temporary sort files trong online ALTER TABLE có rebuild bảng. Không đổi innodb_tmpdir với kỳ vọng di chuyển toàn bộ temporary table của InnoDB.

## 5. Undo log và undo tablespace là gì?

Undo log là tập hợp các undo record gắn với một transaction đọc/ghi. Một undo record chứa thông tin cần thiết để đảo ngược thay đổi gần nhất của transaction trên clustered index record.

Undo log phục vụ hai mục đích quan trọng:

1. **Rollback:** nếu transaction bị rollback, InnoDB dùng undo record để hoàn tác thay đổi của transaction.
2. **Consistent read/MVCC:** nếu một transaction cần nhìn phiên bản dữ liệu cũ theo read view của nó, InnoDB dùng undo record để dựng lại phiên bản trước đó.

Undo log được tổ chức theo cấu trúc:

~~~text
Undo record
    ↓
Undo log segment
    ↓
Rollback segment
    ↓
Undo tablespace
~~~

Rollback segment nằm trong undo tablespace hoặc global temporary tablespace.

### Undo log khác redo log

| Loại log | Mục đích chính |
|---|---|
| Undo log | Hoàn tác thay đổi và dựng phiên bản cũ cho consistent read |
| Redo log | Phục hồi thay đổi đã ghi theo cơ chế crash recovery |

Undo không phải bản sao lưu database. Redo không thay thế undo. Hai loại log có vai trò khác nhau trong transaction và phục hồi.

### Undo cho bảng thông thường và temporary table

InnoDB phân bổ undo log riêng theo loại thao tác:

- INSERT trên bảng thông thường.
- UPDATE/DELETE trên bảng thông thường.
- INSERT trên user-created temporary table.
- UPDATE/DELETE trên user-created temporary table.

Undo cho bảng thông thường được cấp từ rollback segment trong undo tablespace. Undo cho user-created temporary table được cấp từ rollback segment trong global temporary tablespace.

Điều này giải thích vì sao một workload tạo và sửa nhiều temporary table có thể làm ibtmp1 tăng, trong khi một workload UPDATE/DELETE lớn trên bảng nghiệp vụ có thể làm undo tablespace tăng.

## 6. Vì sao undo tablespace tăng kích thước?

Undo tablespace tăng khi workload tạo ra nhiều undo record và InnoDB chưa thể giải phóng chúng.

Các nguyên nhân phổ biến:

- Transaction UPDATE/DELETE số lượng lớn.
- Transaction mở lâu và chưa COMMIT/ROLLBACK.
- Session giữ transaction ở trạng thái idle nhưng vẫn mở.
- Transaction dùng consistent read giữ read view cũ.
- Một workload ghi dữ liệu nhanh hơn tốc độ purge xử lý undo không còn cần thiết.
- Batch job chạy quá lâu mà không chia transaction phù hợp.

### Transaction dài giữ phiên bản cũ

Giả sử Session A bắt đầu transaction ở isolation level REPEATABLE READ và tạo read view. Trong lúc A vẫn mở, Session B liên tục UPDATE rồi COMMIT dữ liệu.

Session A cần tiếp tục nhìn thấy phiên bản phù hợp với read view cũ. Vì vậy, InnoDB phải giữ lại undo cần thiết để dựng các phiên bản cũ cho A.

Nếu Session A mở lâu, purge không thể loại bỏ một số undo record mà read view đó còn cần. Undo tablespace có thể tiếp tục tăng.

Một transaction chỉ đọc cũng có thể giữ read view và làm history list tăng, dù transaction đó không tạo undo record mới.

### History list length

History list length là chỉ số thể hiện purge lag trong phần TRANSACTIONS của SHOW ENGINE INNODB STATUS.

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

Tìm phần:

~~~text
------------
TRANSACTIONS
------------
...
History list length 20
~~~

Không dùng một con số cố định làm ngưỡng cảnh báo cho mọi hệ thống. Hãy quan sát xu hướng theo thời gian, tốc độ tăng, lượng ghi, thời gian transaction cũ nhất và dung lượng đĩa còn trống.

Một giá trị tăng liên tục có thể cho thấy purge không theo kịp hoặc có read view cũ đang giữ undo.

## 7. Purge giải phóng undo như thế nào?

Purge là tiến trình nền của InnoDB xử lý các undo log record đã không còn cần cho rollback hoặc MVCC.

Ví dụ DELETE một hàng không đồng nghĩa hàng và index record bị xóa vật lý ngay lập tức. InnoDB đánh dấu thay đổi và giữ undo cần thiết. Khi không còn transaction/read view nào cần phiên bản cũ, purge có thể xử lý delete-marked record và giải phóng undo tương ứng.

Luồng khái niệm:

~~~text
UPDATE / DELETE
      ↓
Tạo undo record
      ↓
COMMIT
      ↓
Undo có thể vẫn cần cho read view cũ
      ↓
Read view cũ kết thúc
      ↓
Purge xử lý history list
      ↓
Undo record không còn cần được giải phóng
      ↓
Rollback segment có thể tái sử dụng hoặc truncate
~~~

Purge không thể xóa undo mà một transaction đang cần để đọc phiên bản cũ. Vì vậy, tăng số purge thread không tự giải quyết được một transaction cũ đang giữ read view.

Khi history list tăng, cần kiểm tra cả transaction dài lẫn năng lực purge; không chỉ tăng cấu hình purge một cách máy móc.

## 8. Undo tablespace mặc định và vị trí lưu trữ

Khi khởi tạo MySQL instance, InnoDB tạo hai undo tablespace mặc định:

| Tên tablespace | Tên file mặc định |
|---|---|
| innodb_undo_001 | undo_001 |
| innodb_undo_002 | undo_002 |

Hai tablespace này được tạo từ lúc khởi tạo instance vì rollback segment cần tồn tại trước khi server nhận câu SQL. Hai undo tablespace active cũng là điều kiện tối thiểu cho cơ chế tự động truncate.

Biến innodb_undo_directory xác định nơi tạo undo tablespace mặc định và undo tablespace do người dùng tạo nếu không chỉ định đường dẫn riêng.

Kiểm tra:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'innodb_undo_directory';
~~~

Nếu biến không được cấu hình, undo tablespace mặc định nằm trong data directory.

Trong MySQL 9.7, innodb_undo_directory có phạm vi GLOBAL và không dynamic. Thay đổi vị trí là công việc cấu hình/restart có quy trình; không di chuyển file undo khi server đang chạy.

### Xem file undo hiện có

~~~sql
SELECT
    TABLESPACE_NAME,
    FILE_NAME,
    FILE_TYPE
FROM INFORMATION_SCHEMA.FILES
WHERE FILE_TYPE = 'UNDO LOG'
ORDER BY TABLESPACE_NAME;
~~~

Một instance hỗ trợ tối đa 127 undo tablespace, tính cả hai tablespace mặc định. Có thể tạo thêm undo tablespace khi cần phân tán dung lượng hoặc giảm kích thước từng tablespace, nhưng phải đánh giá workload và I/O trước khi thay đổi.

## 9. Theo dõi session temporary tablespace

MySQL cung cấp bảng metadata INFORMATION_SCHEMA.INNODB_SESSION_TEMP_TABLESPACES để quan sát session temporary tablespace.

~~~sql
SELECT
    ID,
    SPACE,
    PATH,
    SIZE,
    STATE,
    PURPOSE
FROM INFORMATION_SCHEMA.INNODB_SESSION_TEMP_TABLESPACES
ORDER BY SIZE DESC;
~~~

Các cột quan trọng:

| Cột | Ý nghĩa |
|---|---|
| ID | Process/session ID |
| SPACE | Tablespace ID |
| PATH | Đường dẫn file |
| SIZE | Kích thước tính bằng byte |
| STATE | ACTIVE hoặc INACTIVE |
| PURPOSE | Mục đích sử dụng tablespace |

ACTIVE cho biết tablespace đang được session sử dụng; INACTIVE cho biết nó đang ở pool để tái sử dụng.

Có thể đối chiếu với processlist:

~~~sql
SELECT
    ID,
    USER,
    HOST,
    DB,
    COMMAND,
    TIME,
    STATE,
    INFO
FROM INFORMATION_SCHEMA.PROCESSLIST
ORDER BY TIME DESC;
~~~

Để xem user-created temporary table InnoDB đang hoạt động:

~~~sql
SELECT *
FROM INFORMATION_SCHEMA.INNODB_TEMP_TABLE_INFO;
~~~

Bảng INNODB_TEMP_TABLE_INFO chỉ cung cấp thông tin về user-created temporary table đang hoạt động trong instance. Internal temporary table do optimizer tạo được theo dõi qua session temporary tablespace metadata, không nhất thiết xuất hiện trong bảng này.

## 10. Theo dõi kích thước temporary và undo tablespace

Bảng INFORMATION_SCHEMA.FILES cung cấp metadata của file tablespace InnoDB.

### Global temporary tablespace

~~~sql
SELECT
    FILE_NAME,
    TABLESPACE_NAME,
    INITIAL_SIZE,
    TOTAL_EXTENTS * EXTENT_SIZE AS allocated_bytes,
    DATA_FREE,
    MAXIMUM_SIZE
FROM INFORMATION_SCHEMA.FILES
WHERE TABLESPACE_NAME = 'innodb_temporary';
~~~

### Undo tablespace

~~~sql
SELECT
    FILE_NAME,
    TABLESPACE_NAME,
    INITIAL_SIZE,
    TOTAL_EXTENTS * EXTENT_SIZE AS allocated_bytes,
    DATA_FREE,
    MAXIMUM_SIZE
FROM INFORMATION_SCHEMA.FILES
WHERE FILE_TYPE = 'UNDO LOG'
ORDER BY TABLESPACE_NAME;
~~~

### Trạng thái undo tablespace

~~~sql
SELECT
    NAME,
    STATE,
    FILE_SIZE,
    ALLOCATED_SIZE
FROM INFORMATION_SCHEMA.INNODB_TABLESPACES
WHERE NAME LIKE 'innodb_undo_%'
ORDER BY NAME;
~~~

Khi đọc số liệu:

- FILE_SIZE thể hiện kích thước file tablespace.
- ALLOCATED_SIZE thể hiện dung lượng đã cấp phát theo metadata InnoDB.
- DATA_FREE là thông tin dung lượng trống trong file theo metadata của INFORMATION_SCHEMA.FILES.
- Kích thước file trên filesystem có thể lớn hơn lượng dữ liệu đang sử dụng.

Đừng kết luận file bị rò rỉ chỉ vì kích thước file chưa giảm sau khi workload kết thúc. Tablespace có thể giữ lại vùng trống để tái sử dụng; việc trả dung lượng về filesystem là một bước riêng.

## 11. Quản lý global temporary tablespace

Biến innodb_temp_data_file_path xác định tên, vị trí tương đối, kích thước và thuộc tính của global temporary tablespace data file.

Kiểm tra:

~~~sql
SELECT @@GLOBAL.innodb_temp_data_file_path;
~~~

Ví dụ cấu hình có giới hạn:

~~~ini
[mysqld]
innodb_temp_data_file_path=ibtmp1:12M:autoextend:max:2G
~~~

Các thuộc tính:

- Tên file: ibtmp1.
- Kích thước khởi đầu: 12M.
- autoextend: cho phép file tự tăng khi thiếu không gian.
- max:2G: giới hạn kích thước file.

Biến này là GLOBAL, không dynamic. Cấu hình cần restart server.

### Khi ibtmp1 đã tăng rất lớn

Trước khi restart:

1. Kiểm tra file nào đang tăng và dung lượng filesystem.
2. Kiểm tra các session đang tạo temporary table lớn.
3. Kiểm tra truy vấn có GROUP BY, DISTINCT, ORDER BY, UNION hoặc window operation tạo nhiều dữ liệu trung gian.
4. Xem session nào giữ temporary table lâu.
5. Kiểm tra workload có đang chạy online DDL hay không.
6. Lên lịch restart nếu cần thu hồi dung lượng file global temporary tablespace.

Restart bình thường sẽ tạo lại global temporary tablespace theo cấu hình. Restart không phải giải pháp thay thế cho việc sửa truy vấn hoặc giới hạn workload gây tăng dung lượng lặp lại.

Không xóa ibtmp1 bằng filesystem command khi MySQL còn chạy.

## 12. Tự động truncate undo tablespace

MySQL hỗ trợ tự động truncate undo tablespace khi file vượt ngưỡng cấu hình.

Hai biến chính:

| Biến | Ý nghĩa | Đặc điểm |
|---|---|---|
| innodb_undo_log_truncate | Bật/tắt tự động truncate undo tablespace | GLOBAL, dynamic, mặc định ON trong MySQL 9.7 |
| innodb_max_undo_log_size | Ngưỡng kích thước để xem xét truncate | GLOBAL, dynamic, mặc định 1 GiB |

Kiểm tra:

~~~sql
SELECT
    @@GLOBAL.innodb_undo_log_truncate,
    @@GLOBAL.innodb_max_undo_log_size;
~~~

Bật tự động truncate:

~~~sql
SET GLOBAL innodb_undo_log_truncate = ON;
~~~

Đặt ngưỡng 1 GiB:

~~~sql
SET GLOBAL innodb_max_undo_log_size = 1073741824;
~~~

Đây là ví dụ cấu hình, không phải giá trị khuyến nghị cho mọi workload. Chọn ngưỡng theo dung lượng đĩa, tốc độ phát sinh undo, thời gian transaction và khả năng purge.

### Điều kiện tối thiểu

Tự động truncate cần ít nhất hai undo tablespace active. MySQL tạo sẵn hai undo tablespace mặc định khi khởi tạo instance.

Khi một undo tablespace vượt ngưỡng:

1. InnoDB đánh dấu tablespace được chọn để truncate.
2. Rollback segment trong tablespace được chọn ngừng nhận transaction mới.
3. Transaction đang dùng rollback segment đó được phép hoàn tất.
4. Purge giải phóng undo log không còn cần thiết.
5. Khi rollback segment đã được giải phóng, tablespace được truncate về 16 MB.
6. Rollback segment được kích hoạt lại để phục vụ transaction mới.

Quá trình này không xóa undo còn cần cho transaction đang chạy hoặc read view cũ.

### Theo dõi hoạt động truncate

~~~sql
SELECT
    NAME,
    SUBSYSTEM,
    COMMENT
FROM INFORMATION_SCHEMA.INNODB_METRICS
WHERE NAME LIKE '%truncate%';
~~~

Tần suất purge kiểm tra tablespace để truncate được điều khiển bởi innodb_purge_rseg_truncate_frequency. Giá trị mặc định là 128. Chỉ cân nhắc thay đổi sau khi đã xác định purge đang xử lý chậm và hiểu ảnh hưởng tải.

## 13. Truncate undo tablespace thủ công

Có thể chủ động đưa một undo tablespace ra khỏi hoạt động để purge giải phóng rollback segment và truncate file.

Tuy nhiên, manual truncation cần tối thiểu **ba undo tablespace active**:

- Hai tablespace vẫn phải active để duy trì điều kiện hỗ trợ automatic truncation.
- Một tablespace thứ ba được đưa sang inactive để truncate.

Quy trình khái niệm:

~~~sql
ALTER UNDO TABLESPACE undo_user_01 SET INACTIVE;
~~~

Theo dõi trạng thái:

~~~sql
SELECT
    NAME,
    STATE,
    FILE_SIZE,
    ALLOCATED_SIZE
FROM INFORMATION_SCHEMA.INNODB_TABLESPACES
WHERE NAME = 'undo_user_01';
~~~

Khi trạng thái chuyển thành empty, có thể kích hoạt lại:

~~~sql
ALTER UNDO TABLESPACE undo_user_01 SET ACTIVE;
~~~

Hoặc nếu đó là undo tablespace do người dùng tạo và có chủ đích loại bỏ:

~~~sql
DROP UNDO TABLESPACE undo_user_01;
~~~

Không thể DROP undo tablespace mặc định innodb_undo_001 và innodb_undo_002. Một undo tablespace chỉ được DROP khi ở trạng thái empty.

Đây là thao tác quản trị có ảnh hưởng đến phân bổ rollback segment. Không chạy tùy tiện trong production. Trước khi thực hiện, xác minh số tablespace active, transaction đang dùng rollback segment, trạng thái purge, tải I/O và khả năng phục hồi.

## 14. Vì sao truncate undo có thể ảnh hưởng hiệu năng?

Khi một undo tablespace được đưa ra khỏi hoạt động để truncate, các rollback segment trong đó tạm thời không nhận transaction mới. Những undo tablespace active còn lại phải gánh tải.

Điều này có thể làm hiệu năng giảm nhẹ tùy:

- Số undo tablespace còn active.
- Số transaction đồng thời.
- Lượng undo log đang tồn tại.
- Kích thước undo tablespace.
- Tốc độ I/O.
- Transaction dài còn sử dụng rollback segment.
- Tải chung của server.

Tự động truncate không có nghĩa file sẽ co lại ngay khi vừa vượt ngưỡng. InnoDB phải chờ transaction hoàn tất và purge giải phóng undo trước.

Nếu file lớn do transaction dài giữ read view, tăng số lần purge kiểm tra không thể bỏ qua read view đó. Cần xử lý nguyên nhân giữ undo trước.

## 15. Quy trình điều tra khi undo tablespace tăng liên tục

### Bước 1: xem history list length

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

Ghi nhận History list length và so sánh qua nhiều thời điểm.

### Bước 2: tìm transaction cũ

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_mysql_thread_id,
    trx_rows_modified,
    trx_rows_locked,
    trx_query
FROM INFORMATION_SCHEMA.INNODB_TRX
ORDER BY trx_started;
~~~

Tìm transaction có thời gian tồn tại dài, nhiều hàng đã sửa hoặc trạng thái idle nhưng chưa kết thúc.

### Bước 3: kiểm tra session và ứng dụng sở hữu transaction

~~~sql
SELECT
    ID,
    USER,
    HOST,
    DB,
    COMMAND,
    TIME,
    STATE,
    INFO
FROM INFORMATION_SCHEMA.PROCESSLIST
ORDER BY TIME DESC;
~~~

Đối chiếu trx_mysql_thread_id với PROCESSLIST.ID. Xác định ứng dụng, job hoặc connection pool đang giữ transaction.

### Bước 4: xem undo tablespace

~~~sql
SELECT
    TABLESPACE_NAME,
    FILE_NAME,
    TOTAL_EXTENTS * EXTENT_SIZE AS allocated_bytes,
    DATA_FREE
FROM INFORMATION_SCHEMA.FILES
WHERE FILE_TYPE = 'UNDO LOG'
ORDER BY allocated_bytes DESC;
~~~

### Bước 5: xử lý transaction cũ

Ưu tiên yêu cầu ứng dụng hoàn tất COMMIT/ROLLBACK theo logic nghiệp vụ. Nếu phải KILL session, cần hiểu rằng rollback của transaction lớn có thể mất thời gian và tiếp tục tạo tải I/O.

Không xóa undo file và không sửa metadata tablespace bằng filesystem command.

### Bước 6: quan sát purge bắt kịp

Sau khi transaction cũ kết thúc, theo dõi History list length và dung lượng undo theo thời gian. Purge có thể cần thời gian để giải phóng undo không còn được sử dụng.

### Bước 7: xác minh cơ chế truncate

Kiểm tra innodb_undo_log_truncate, innodb_max_undo_log_size, số undo tablespace active và trạng thái trong INNODB_TABLESPACES.

Nếu nguyên nhân tăng dung lượng vẫn còn, việc truncate chỉ giải phóng dung lượng tạm thời và file có thể tăng lại.

## 16. Phân biệt dung lượng file với dung lượng dữ liệu còn cần

Một file tablespace lớn không có nghĩa toàn bộ dữ liệu bên trong vẫn đang được sử dụng.

Có ba trạng thái cần phân biệt:

1. **Undo còn cần:** transaction hoặc read view vẫn cần phiên bản cũ; purge chưa thể giải phóng.
2. **Undo đã giải phóng nhưng vùng trống còn trong tablespace:** vùng trống có thể được tái sử dụng cho undo mới.
3. **Tablespace đã truncate:** file được thu nhỏ để trả dung lượng về filesystem.

Ví dụ, sau một đợt UPDATE lớn, transaction kết thúc và purge xử lý xong. File undo có thể vẫn giữ kích thước lớn nhưng có nhiều vùng trống nội bộ. Nếu chưa có truncate, dung lượng filesystem chưa chắc giảm.

Tương tự, session temporary tablespace có thể được truncate khi session disconnect rồi trả về pool; global temporary tablespace có cơ chế thu hồi file khi server restart bình thường.

Đừng dùng rm, del hoặc công cụ filesystem để xóa file .ibu, .ibt hoặc ibtmp1 khi MySQL đang hoạt động. InnoDB cần metadata và file tablespace khớp nhau để hoạt động và phục hồi.

## 17. Bài thực hành: quan sát temporary tablespace

Bài lab dùng hai session để quan sát session temporary tablespace và global temporary tablespace.

### Bước 1: Session A tạo temporary table

~~~sql
CREATE TEMPORARY TABLE tmp_session_report (
    id INT NOT NULL PRIMARY KEY,
    payload VARCHAR(200) NOT NULL
) ENGINE=InnoDB;

INSERT INTO tmp_session_report (id, payload)
VALUES
    (1, REPEAT('A', 100)),
    (2, REPEAT('B', 100)),
    (3, REPEAT('C', 100));

SELECT * FROM tmp_session_report;
~~~

Temporary table chỉ hiển thị trong Session A. Session khác không thể SELECT trực tiếp bảng này.

### Bước 2: Session B xem metadata session temporary tablespace

~~~sql
SELECT
    ID,
    SPACE,
    PATH,
    SIZE,
    STATE,
    PURPOSE
FROM INFORMATION_SCHEMA.INNODB_SESSION_TEMP_TABLESPACES
ORDER BY SIZE DESC;
~~~

Tìm session ID tương ứng với Session A và quan sát PATH, SIZE, STATE, PURPOSE.

### Bước 3: xem user-created temporary table đang hoạt động

~~~sql
SELECT *
FROM INFORMATION_SCHEMA.INNODB_TEMP_TABLE_INFO;
~~~

Đối chiếu thông tin bảng tạm với session temporary tablespace.

### Bước 4: xem global temporary tablespace

~~~sql
SELECT
    FILE_NAME,
    TABLESPACE_NAME,
    TOTAL_EXTENTS * EXTENT_SIZE AS allocated_bytes,
    DATA_FREE
FROM INFORMATION_SCHEMA.FILES
WHERE TABLESPACE_NAME = 'innodb_temporary';
~~~

Kích thước có thể không thay đổi rõ rệt với bộ dữ liệu nhỏ. Mục tiêu là xác định metadata và phân biệt file global với file session.

### Bước 5: đóng Session A

Trong Session A:

~~~sql
DROP TEMPORARY TABLE tmp_session_report;
~~~

Sau đó đóng connection Session A. Session temporary tablespace được truncate và trả lại pool. Kiểm tra lại metadata ở Session B; file có thể xuất hiện ở trạng thái INACTIVE.

## 18. Bài thực hành: quan sát undo và purge

Bài lab này tạo một read view cũ ở Session A, sau đó cập nhật dữ liệu đã commit từ Session B để quan sát history list.

Chỉ chạy trên môi trường thử nghiệm riêng, không dùng bảng nghiệp vụ.

### Bước 1: tạo dữ liệu

~~~sql
CREATE DATABASE IF NOT EXISTS innodb_space_lab;
USE innodb_space_lab;

CREATE TABLE undo_probe (
    id INT NOT NULL PRIMARY KEY,
    value_num INT NOT NULL
) ENGINE=InnoDB;

INSERT INTO undo_probe (id, value_num)
VALUES
    (1, 10),
    (2, 20),
    (3, 30),
    (4, 40),
    (5, 50);
~~~

### Bước 2: Session A giữ consistent read view

~~~sql
START TRANSACTION WITH CONSISTENT SNAPSHOT;

SELECT *
FROM undo_probe
ORDER BY id;
~~~

Giữ transaction này mở trong lúc thực hiện bước tiếp theo.

### Bước 3: Session B cập nhật và commit

~~~sql
USE innodb_space_lab;

UPDATE undo_probe
SET value_num = value_num + 100
WHERE id BETWEEN 1 AND 5;

COMMIT;

SELECT *
FROM undo_probe
ORDER BY id;
~~~

Session B nhìn thấy giá trị mới. Session A vẫn có thể nhìn thấy phiên bản cũ theo read view đã tạo.

### Bước 4: quan sát history list

Ở một session quản trị khác:

~~~sql
SHOW ENGINE INNODB STATUS;
~~~

Tìm History list length trong phần TRANSACTIONS. Giá trị thực tế phụ thuộc workload, purge và thời điểm lấy mẫu; không yêu cầu phải đạt một con số cụ thể với bộ dữ liệu lab nhỏ.

### Bước 5: kết thúc read view cũ

Trong Session A:

~~~sql
COMMIT;
~~~

Sau đó tiếp tục quan sát SHOW ENGINE INNODB STATUS. Khi không còn read view nào cần các phiên bản cũ, purge có thể giải phóng undo tương ứng. Việc giảm History list length không nhất thiết xảy ra ngay tức thì.

### Bước 6: kiểm tra undo tablespace

~~~sql
SELECT
    TABLESPACE_NAME,
    FILE_NAME,
    TOTAL_EXTENTS * EXTENT_SIZE AS allocated_bytes,
    DATA_FREE
FROM INFORMATION_SCHEMA.FILES
WHERE FILE_TYPE = 'UNDO LOG';
~~~

Với lượng dữ liệu nhỏ, kích thước file có thể không thay đổi đáng kể. Điều quan trọng là hiểu quan hệ giữa transaction cũ, undo, history list và purge.

### Dọn dẹp

~~~sql
DROP DATABASE innodb_space_lab;
~~~

Chỉ xóa database lab vừa tạo. Đảm bảo Session A đã COMMIT hoặc ROLLBACK trước khi dọn dẹp.

## 19. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| ibtmp1 tăng liên tục | Nhiều thay đổi trên temporary table hoặc workload tạo temporary data lớn | Kiểm tra session, truy vấn và giới hạn innodb_temp_data_file_path |
| File session .ibt tăng | Session tạo temporary table hoặc internal temporary table lớn | Xem INNODB_SESSION_TEMP_TABLESPACES, truy vấn và session đang giữ file |
| Đóng session nhưng file vẫn còn trong thư mục | Tablespace được truncate và trả về pool; pool không tự giảm số file | Kiểm tra STATE và SIZE thay vì chờ file biến mất |
| Undo tablespace tăng | Nhiều UPDATE/DELETE hoặc transaction dài giữ undo | Kiểm tra INNODB_TRX, History list length và purge |
| History list length tăng liên tục | Purge không theo kịp hoặc read view cũ đang giữ phiên bản | Xác định transaction cũ và workload ghi |
| Transaction đã COMMIT nhưng undo file chưa nhỏ | Undo được giải phóng nội bộ nhưng file chưa truncate | Kiểm tra cơ chế auto truncate và trạng thái tablespace |
| innodb_undo_log_truncate bật nhưng file chưa giảm | Chưa có đủ hai tablespace active, undo còn được dùng hoặc purge chưa giải phóng | Kiểm tra transaction, active tablespace và ngưỡng truncate |
| Manual truncate báo không thể deactivate | Không đủ ba undo tablespace active hoặc trạng thái không phù hợp | Kiểm tra số tablespace và làm theo quy trình manual truncate |
| Restart nhưng file temporary lại tăng | Workload tiếp tục tạo temporary data lớn | Sửa truy vấn, giới hạn session và theo dõi dung lượng |
| Server không khởi động sau khi di chuyển undo file | File không ở known directory hoặc metadata không khớp | Khôi phục đúng vị trí/cấu hình theo quy trình phục hồi InnoDB |
| Online ALTER tạo nhiều file tạm ngoài dự kiến | innodb_tmpdir/tmpdir khác với InnoDB temporary tablespace | Xác định loại file và đúng biến cấu hình |

## 20. Checklist vận hành temporary và undo tablespace

- [ ] Đã phân biệt session temporary tablespace, global temporary tablespace và undo tablespace.
- [ ] Đã biết ibtmp1 lưu rollback segment cho thay đổi trên user-created temporary table.
- [ ] Đã biết internal temporary table trên đĩa dùng InnoDB trong MySQL 9.7.
- [ ] Đã biết session temporary tablespace được truncate và trả về pool khi session disconnect.
- [ ] Đã kiểm tra INNODB_SESSION_TEMP_TABLESPACES và INNODB_TEMP_TABLE_INFO.
- [ ] Đã kiểm tra kích thước file bằng INFORMATION_SCHEMA.FILES.
- [ ] Đã phân biệt innodb_tmpdir với innodb_temp_tablespaces_dir và innodb_temp_data_file_path.
- [ ] Đã biết innodb_temp_data_file_path và innodb_temp_tablespaces_dir là startup-only.
- [ ] Đã biết undo log phục vụ rollback và MVCC consistent read.
- [ ] Đã theo dõi History list length và transaction cũ nhất.
- [ ] Đã kiểm tra INFORMATION_SCHEMA.INNODB_TRX khi undo tăng.
- [ ] Đã hiểu purge chỉ giải phóng undo không còn được transaction/read view sử dụng.
- [ ] Đã xác định hai undo tablespace mặc định và vị trí innodb_undo_directory.
- [ ] Đã kiểm tra innodb_undo_log_truncate và innodb_max_undo_log_size.
- [ ] Đã xác minh có tối thiểu hai undo tablespace active cho automatic truncation.
- [ ] Chỉ manual truncate khi đáp ứng điều kiện tối thiểu ba tablespace active.
- [ ] Không xóa file .ibu, .ibt hoặc ibtmp1 thủ công khi server đang chạy.
- [ ] Đã phân biệt vùng trống nội bộ với dung lượng đã trả về filesystem.
- [ ] Đã lên kế hoạch restart nếu cần thu hồi dung lượng global temporary tablespace.
- [ ] Có cảnh báo dung lượng filesystem và xu hướng tăng tablespace.

## 21. Nguyên tắc cần ghi nhớ

1. Session temporary tablespace lưu user-created temporary table và internal temporary table trên đĩa.
2. Global temporary tablespace ibtmp1 lưu rollback segment cho thay đổi trên user-created temporary table.
3. Undo tablespace lưu undo log cho transaction thao tác trên bảng thông thường.
4. Undo log phục vụ rollback và MVCC consistent read; redo log phục vụ crash recovery.
5. Transaction dài và read view cũ có thể giữ undo, khiến History list length tăng.
6. Purge chỉ giải phóng undo không còn được transaction hoặc read view sử dụng.
7. Session temporary tablespace được truncate và trả về pool khi session disconnect; pool không tự giảm số lượng file khi server chạy.
8. ibtmp1 mặc định autoextend và thường chỉ được tạo lại để thu hồi dung lượng sau normal shutdown/restart.
9. innodb_tmpdir dành cho temporary sort file của một số online ALTER TABLE, không phải session temporary tablespace.
10. MySQL 9.7 tạo hai undo tablespace mặc định: innodb_undo_001 và innodb_undo_002.
11. Automatic undo truncation cần ít nhất hai undo tablespace active; manual truncation cần ít nhất ba.
12. Không xóa file tablespace thủ công; dùng metadata, cấu hình và câu lệnh quản trị đúng quy trình.

## Tài liệu tham khảo chính thức

Các hành vi trong bài được đối chiếu với **MySQL 9.7 Reference Manual** tại ngày **19-11-2026**:

1. [Temporary Tablespaces](https://dev.mysql.com/doc/refman/9.7/en/innodb-temporary-tablespace.html): session temporary tablespace, global temporary tablespace, vòng đời file và cách kiểm tra kích thước.
2. [Undo Tablespaces](https://dev.mysql.com/doc/refman/9.7/en/innodb-undo-tablespaces.html): undo tablespace mặc định, vị trí lưu, thêm/xóa tablespace, tự động và thủ công truncate.
3. [Undo Logs](https://dev.mysql.com/doc/refman/9.7/en/innodb-undo-logs.html): undo log, undo segment, rollback segment và vai trò của undo cho bảng thông thường/temporary table.
4. [InnoDB Multi-Versioning](https://dev.mysql.com/doc/refman/9.7/en/innodb-multi-versioning.html): MVCC, phiên bản hàng cũ, purge và ảnh hưởng của transaction dài.
5. [Purge Configuration](https://dev.mysql.com/doc/refman/9.7/en/innodb-purge-configuration.html): History list length, purge lag, transaction dài và cấu hình purge.
6. [InnoDB Startup Options and System Variables](https://dev.mysql.com/doc/refman/9.7/en/innodb-parameters.html): innodb_temp_tablespaces_dir, innodb_temp_data_file_path, innodb_tmpdir, innodb_undo_directory và các biến truncate undo.
7. [INFORMATION_SCHEMA FILES Table](https://dev.mysql.com/doc/refman/9.7/en/information-schema-files-table.html): metadata file tablespace, FILE_TYPE, kích thước và dung lượng trống.
8. [INNODB_SESSION_TEMP_TABLESPACES](https://dev.mysql.com/doc/refman/9.7/en/information-schema-innodb-session-temp-tablespaces-table.html): theo dõi session temporary tablespace theo session, path, size và state.
9. [INNODB_TEMP_TABLE_INFO](https://dev.mysql.com/doc/refman/9.7/en/information-schema-innodb-temp-table-info-table.html): metadata của user-created temporary table InnoDB đang hoạt động.


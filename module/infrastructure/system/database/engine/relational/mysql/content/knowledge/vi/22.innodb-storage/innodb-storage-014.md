# Lưu trữ InnoDB

## TRUNCATE, DROP, OPTIMIZE và khả năng thu hồi dung lượng

Xóa dữ liệu trong MySQL không phải lúc nào cũng làm file dữ liệu nhỏ đi. Với InnoDB, `DELETE` đánh dấu các record cần xóa và không gian chỉ được giải phóng sau khi purge có thể loại bỏ phiên bản cũ; phần trống thường được tái sử dụng bên trong tablespace. `TRUNCATE TABLE` loại bỏ toàn bộ dữ liệu bằng thao tác DDL nhanh; `DROP TABLE` loại bỏ cả đối tượng bảng; còn `OPTIMIZE TABLE` có thể rebuild bảng và index để tổ chức lại dữ liệu, đồng thời trả lại không gian chưa dùng trong một số loại tablespace.

Kết quả thu hồi dung lượng phụ thuộc nơi bảng được lưu: file-per-table, general tablespace hay system tablespace. Cần phân biệt ba việc: xóa record logic, trả page về vùng trống để InnoDB tái sử dụng và thu nhỏ file vật lý để hệ điều hành nhìn thấy dung lượng được trả lại. Đây là ba kết quả khác nhau.

### 1. Phân biệt DELETE, TRUNCATE, DROP và OPTIMIZE

| Lệnh | Tác động chính | Có điều kiện `WHERE`? | Có thể rollback bằng transaction? | Mục tiêu dung lượng |
| --- | --- | --- | --- | --- |
| `DELETE` | Xóa từng hàng thỏa điều kiện; có thể xóa một phần hoặc toàn bộ | Có | Có với InnoDB nếu transaction chưa commit | Đánh dấu record để purge; page trống thường được tái sử dụng |
| `TRUNCATE TABLE` | Làm rỗng toàn bộ bảng bằng DDL | Không | Không; có implicit commit | Giải phóng không gian dữ liệu/index của bảng cho tablespace quản lý |
| `DROP TABLE` | Xóa đối tượng bảng và dữ liệu/index của nó | Không | Không; có implicit commit | Có thể xóa file tablespace riêng nếu bảng dùng file-per-table |
| `OPTIMIZE TABLE` | Tổ chức lại bảng và index, cập nhật thống kê | Không | Không; là thao tác DDL/bảo trì | Có thể trả phần không gian không còn cần cho file-per-table về hệ điều hành |

`DELETE` là DML; các lệnh `TRUNCATE`, `DROP` và `OPTIMIZE` là DDL hoặc thao tác bảo trì có hành vi DDL. Vì vậy, chúng có ranh giới transaction và quyền thực thi khác nhau. Không dùng `TRUNCATE` hoặc `DROP` như một cách viết ngắn của `DELETE` khi ứng dụng cần rollback hoặc kích hoạt logic theo từng hàng.

### 2. DELETE: xóa hàng nhưng chưa chắc giảm file

`DELETE` xóa các hàng thỏa điều kiện và có thể nằm trong transaction InnoDB:

```sql
START TRANSACTION;

DELETE FROM event_log
WHERE created_at < '2025-01-01';

-- Có thể kiểm tra kết quả trước khi quyết định.
ROLLBACK;
```

Nếu rollback trước commit, InnoDB dùng undo để khôi phục các thay đổi. Nếu commit, các record bị xóa được đánh dấu và chỉ được purge vật lý khi không còn read view nào cần phiên bản cũ. Một transaction `REPEATABLE READ` chạy lâu có thể giữ lịch sử undo cần thiết, làm purge chậm và trì hoãn việc dọn record.

Sau purge, page có thể có thêm free space để dùng cho insert hoặc update sau này. Nhưng file `.ibd` thường vẫn giữ kích thước đã cấp phát. Ví dụ, xóa 80% hàng của một bảng file-per-table có thể làm phần lớn page bên trong bảng trở nên thưa hoặc trống, trong khi kích thước file trên filesystem chưa giảm tương ứng.

Đây thường là hành vi có lợi nếu bảng tiếp tục nhận dữ liệu: InnoDB có thể tái sử dụng page đã cấp phát mà không cần xin thêm không gian từ hệ điều hành. Chỉ khi cần trả dung lượng vật lý cho filesystem, mới cần cân nhắc rebuild hoặc thao tác DDL khác.

### 3. TRUNCATE TABLE: làm rỗng toàn bộ bảng

Cú pháp:

```sql
TRUNCATE TABLE event_log;
```

`TRUNCATE TABLE` loại bỏ toàn bộ hàng của bảng bằng thao tác DDL. Nó thường nhanh hơn `DELETE FROM event_log` không có `WHERE` vì không phải xử lý từng hàng theo cách DML thông thường. Những điểm quan trọng:

- Không có `WHERE`; không thể chỉ xóa một phần dữ liệu.
- Không phát sinh sự kiện `DELETE` cho từng hàng và không kích hoạt trigger `DELETE` của bảng.
- Đặt lại bộ đếm `AUTO_INCREMENT` về giá trị khởi đầu theo định nghĩa bảng.
- Cần quyền `DROP` trên bảng.
- Là DDL có implicit commit; không thể hoàn tác bằng `ROLLBACK` của transaction bao quanh.
- Có thể bị từ chối nếu bảng được tham chiếu bởi khóa ngoại từ một bảng khác; ngoại lệ là self-referencing foreign key theo quy tắc của MySQL.

Ví dụ minh họa khác biệt về `AUTO_INCREMENT`:

```sql
CREATE TABLE import_stage (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    payload JSON
) ENGINE = InnoDB;

INSERT INTO import_stage (payload)
VALUES ('{"batch": 1}'), ('{"batch": 2}');

TRUNCATE TABLE import_stage;

INSERT INTO import_stage (payload)
VALUES ('{"batch": 3}');
-- id được cấp lại từ đầu theo AUTO_INCREMENT hiện hành.
```

Không dựa vào số `AUTO_INCREMENT` như một bộ đếm liên tục hoặc một định danh không bao giờ tái sử dụng. Nếu hệ thống cần giữ lịch sử định danh, hãy lưu dữ liệu lịch sử ở bảng khác hoặc dùng chiến lược khóa phù hợp.

`TRUNCATE` cũng không chạy logic nghiệp vụ được cài trong trigger `DELETE`. Nếu cần ghi audit theo từng hàng, phát sự kiện domain hoặc cập nhật bảng liên quan theo từng bản ghi, phải dùng quy trình DML phù hợp thay vì thay thế bằng `TRUNCATE`.

### 4. DROP TABLE: xóa đối tượng bảng

Cú pháp cơ bản:

```sql
DROP TABLE event_log;
```

`DROP TABLE` xóa định nghĩa bảng cùng dữ liệu và index. Với file-per-table, thao tác thành công thường loại bỏ tablespace riêng của bảng và file `.ibd` tương ứng. Với bảng nằm trong system/general tablespace dùng chung, không gian của bảng được trả về vùng lưu trữ dùng chung để tái sử dụng; file chứa tablespace không tự thu nhỏ chỉ vì một bảng bị drop.

`DROP TABLE` là DDL có implicit commit và không thể rollback bằng `ROLLBACK`. Trước khi drop bảng có quan hệ khóa ngoại, phải xem xét các constraint phụ thuộc và thứ tự migration. MySQL thường không cho drop một bảng đang được bảng khác tham chiếu bằng foreign key khi kiểm tra khóa ngoại được bật. Tắt `foreign_key_checks` không tự động xóa các định nghĩa constraint ở bảng con; việc dùng tùy chọn này cần kế hoạch kiểm tra tính toàn vẹn và khôi phục constraint rõ ràng.

Để tránh lỗi khi bảng không tồn tại, có thể dùng:

```sql
DROP TABLE IF EXISTS event_log;
```

Lệnh này vẫn là thao tác xóa không thể hoàn tác bằng transaction. `IF EXISTS` chỉ làm thay đổi cách xử lý trường hợp thiếu bảng, không biến lệnh thành thao tác an toàn có thể rollback.

### 5. OPTIMIZE TABLE với InnoDB

Cú pháp:

```sql
OPTIMIZE TABLE customer_order;
```

Với InnoDB, `OPTIMIZE TABLE` thường được ánh xạ thành thao tác rebuild tương đương `ALTER TABLE ... FORCE`. Quá trình này tạo lại cấu trúc bảng và index, tổ chức lại page, loại bỏ khoảng trống không còn cần thiết trong cấu trúc được rebuild và cập nhật thống kê index. Đây không phải lệnh chỉ đơn giản xóa những byte trống trong file.

Một số trường hợp nên cân nhắc `OPTIMIZE TABLE`:

- Bảng file-per-table đã xóa một lượng lớn hàng và cần trả không gian trống về filesystem.
- Bảng có mức phân mảnh hoặc phân bố page không còn phù hợp với workload sau nhiều thay đổi lớn.
- Cần rebuild index và cập nhật thống kê sau một đợt thay đổi dữ liệu lớn, sau khi đã đánh giá kế hoạch truy vấn.

Không nên chạy `OPTIMIZE TABLE` định kỳ theo lịch cứng cho mọi bảng. Rebuild tiêu thụ CPU, I/O và dung lượng tạm; nó có thể làm tăng replication lag, tạo tải cho backup và ảnh hưởng các transaction khác. Nếu bảng vẫn tiếp tục tăng trưởng, không gian vừa thu hồi có thể lại được cấp phát trong thời gian ngắn.

### 6. File-per-table và tablespace dùng chung quyết định có giảm file hay không

Khả năng trả dung lượng về hệ điều hành phụ thuộc loại tablespace:

| Nơi lưu bảng InnoDB | Sau `DELETE` và purge | Sau `TRUNCATE TABLE` | Sau `OPTIMIZE TABLE` hoặc rebuild |
| --- | --- | --- | --- |
| File-per-table (`.ibd` riêng) | Page trống thường được giữ trong file để tái sử dụng | Bảng được làm rỗng và không gian tablespace riêng có thể được giải phóng/tái tạo | File tablespace có thể được tạo lại nhỏ hơn và trả phần dư cho filesystem |
| General tablespace | Page trống được trả về vùng dùng chung để tái sử dụng | Không gian bảng được giải phóng trong tablespace chung | Có thể tổ chức lại dữ liệu nhưng file general tablespace không tự thu nhỏ theo bảng |
| System tablespace (`ibdata`) | Không gian có thể tái sử dụng trong system tablespace | Không làm `ibdata` nhỏ lại | Rebuild bảng không thu nhỏ system tablespace đã cấp phát |

Kiểm tra `innodb_file_per_table` không đủ để biết chắc bảng hiện hữu đang nằm ở đâu, vì biến này chủ yếu điều khiển mặc định cho bảng mới. Cần kiểm tra metadata tablespace của chính bảng.

Ví dụ xem file-per-table và page size:

```sql
SHOW VARIABLES LIKE 'innodb_file_per_table';
SHOW VARIABLES LIKE 'innodb_page_size';

SELECT
    NAME,
    SPACE_TYPE,
    FILE_SIZE,
    ALLOCATED_SIZE
FROM information_schema.innodb_tablespaces
WHERE NAME LIKE CONCAT(DATABASE(), '/customer_order%');
```

Tên tablespace và cách hiển thị có thể khác theo loại bảng và phiên bản. Hãy đối chiếu `INFORMATION_SCHEMA.INNODB_TABLES` và `INNODB_TABLESPACES` khi cần xác định chính xác space ID và file tương ứng.

### 7. So sánh khả năng thu hồi dung lượng

Ví dụ một bảng file-per-table ban đầu chiếm 20 GiB. Sau khi xóa phần lớn hàng, page được purge và có thể tái sử dụng, nhưng file `.ibd` vẫn khoảng 20 GiB. Nếu rebuild thành công và dữ liệu còn lại chỉ cần 4 GiB, file mới có thể nhỏ hơn đáng kể; con số cuối cùng còn phụ thuộc index, page fill factor, row format và metadata.

```text
Trước khi xóa:
  customer_order.ibd  ~20 GiB

Sau DELETE + purge:
  customer_order.ibd  ~20 GiB
  (nhiều page trống, có thể tái sử dụng)

Sau OPTIMIZE/rebuild thành công:
  customer_order.ibd  ~4 GiB
  (kích thước minh họa; tùy dữ liệu và cấu trúc index)
```

Với general hoặc system tablespace, rebuild có thể làm vùng trống bên trong tablespace tăng lên để các bảng khác dùng lại, nhưng file dùng chung không nhất thiết nhỏ hơn. Đây là lý do cần xác định mục tiêu trước khi chạy lệnh: tối ưu truy vấn, tái sử dụng không gian nội bộ hay giảm dung lượng filesystem.

### 8. DDL, implicit commit và Atomic DDL

`TRUNCATE TABLE`, `DROP TABLE` và thao tác rebuild của `OPTIMIZE TABLE` có hành vi DDL. Các lệnh DDL thông thường tạo implicit commit trước và/hoặc sau thao tác theo quy tắc của MySQL. Vì vậy, không thể bọc chúng trong transaction rồi kỳ vọng `ROLLBACK` khôi phục bảng hoặc dữ liệu đã bị loại bỏ.

Ví dụ, lệnh `TRUNCATE` sẽ kết thúc transaction hiện hành trước khi thực thi:

```sql
START TRANSACTION;

UPDATE account
SET status = 'review'
WHERE id = 10;

TRUNCATE TABLE import_stage;

ROLLBACK;
-- UPDATE trước TRUNCATE đã bị implicit commit; ROLLBACK này không hoàn tác nó.
```

MySQL 8.0 hỗ trợ Atomic DDL cho nhiều thao tác DDL được hỗ trợ trên InnoDB. Atomic DDL giúp một statement được thực hiện theo cách crash-safe: sau sự cố, metadata và thay đổi từ statement không để lại trạng thái nửa chừng theo phạm vi hỗ trợ của engine. Tuy nhiên, **Atomic DDL không có nghĩa DDL có thể rollback bởi người dùng**. Một `TRUNCATE` hoặc `DROP` đã hoàn tất vẫn không thể khôi phục bằng `ROLLBACK` của transaction.

Atomic DDL cũng không thay thế backup. Trước thao tác xóa hoặc rebuild quan trọng, phải có bản backup có thể phục hồi và kiểm tra quy trình restore.

### 9. Khóa, dung lượng tạm và ảnh hưởng vận hành khi rebuild

`OPTIMIZE TABLE` hoặc DDL rebuild có thể cần tạo cấu trúc mới trước khi thay thế cấu trúc cũ. Trong thời gian này, hệ thống có thể cần dung lượng tạm đáng kể, thường phải dự trù ít nhất xấp xỉ kích thước dữ liệu và index đang rebuild, cộng thêm log và headroom cho workload. Mức thực tế phụ thuộc thuật toán DDL, phiên bản, cấu trúc bảng và thay đổi đồng thời.

Các rủi ro cần đánh giá:

- **Disk capacity:** thiếu dung lượng tạm có thể làm rebuild thất bại hoặc gây áp lực lên filesystem.
- **Metadata lock (MDL):** statement cần lấy MDL; transaction dài đang truy cập bảng có thể làm DDL chờ. Một DDL đang chờ cũng có thể khiến truy vấn mới xếp hàng phía sau.
- **Concurrent DML:** khả năng đọc/ghi đồng thời phụ thuộc thuật toán và phiên bản; không mặc định rằng `OPTIMIZE TABLE` luôn không khóa hoặc luôn cho phép ghi.
- **Replication:** DDL được ghi vào binary log theo quy tắc máy chủ và có thể gây tải/độ trễ trên replica.
- **Backup và I/O:** rebuild tạo lượng đọc/ghi lớn, cạnh tranh với workload và cửa sổ backup.
- **Thời gian thực hiện:** bảng lớn hoặc index rộng có thể mất nhiều thời gian; cần đo trên môi trường tương tự trước khi triển khai.

Trước khi chạy, kiểm tra transaction dài, metadata lock, dung lượng filesystem, replica lag và cửa sổ bảo trì. Đối với bảng quan trọng, thử quy trình trên bản sao dữ liệu và chuẩn bị phương án dừng/khôi phục.

### 10. Đo dung lượng trước và sau thao tác

Không dùng riêng `COUNT(*)` để kết luận file đã thu nhỏ. Hãy so sánh metadata của bảng, tablespace và kích thước file trên filesystem.

Thông tin ước lượng ở mức bảng:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE,
    DATA_LENGTH,
    INDEX_LENGTH,
    DATA_FREE
FROM information_schema.tables
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customer_order';
```

Thông tin tablespace trong MySQL 8.0:

```sql
SELECT
    SPACE,
    NAME,
    SPACE_TYPE,
    FILE_SIZE,
    ALLOCATED_SIZE
FROM information_schema.innodb_tablespaces
WHERE NAME LIKE CONCAT(DATABASE(), '/customer_order%');
```

`DATA_LENGTH`, `INDEX_LENGTH` và `DATA_FREE` là số liệu theo cách engine báo cáo, có thể là ước lượng hoặc phản ánh phạm vi tablespace dùng chung. Để xác nhận dung lượng vật lý được trả lại, cần kiểm tra kích thước file thực tế trên filesystem sau khi thao tác hoàn tất. Không đọc hoặc sửa nội dung nhị phân của `.ibd` hay `ibdata` bằng công cụ ngoài khi MySQL đang sử dụng chúng.

Nên ghi lại số liệu trước/sau cùng một thời điểm đo: số hàng, `DATA_LENGTH`, `INDEX_LENGTH`, `DATA_FREE`, `FILE_SIZE`, `ALLOCATED_SIZE`, dung lượng filesystem và replica lag. Sau đó so sánh với mục tiêu ban đầu: dung lượng được tái sử dụng hay dung lượng đã trả về hệ điều hành.

### 11. Chọn lệnh theo mục tiêu

| Nhu cầu | Lựa chọn thường phù hợp | Lưu ý |
| --- | --- | --- |
| Xóa một tập hàng theo điều kiện và cần rollback | `DELETE ... WHERE ...` trong transaction | Chờ purge; file có thể không giảm |
| Làm rỗng bảng staging và chấp nhận DDL | `TRUNCATE TABLE` | Không có WHERE, reset AUTO_INCREMENT, implicit commit, kiểm tra FK và trigger |
| Loại bỏ bảng không còn sử dụng | `DROP TABLE` | Xóa đối tượng; kiểm tra dependency/FK và backup |
| Trả dung lượng của file-per-table sau khi xóa nhiều dữ liệu | `OPTIMIZE TABLE` hoặc rebuild có kế hoạch | Cần dung lượng tạm, I/O và đánh giá MDL |
| Giải phóng không gian để bảng khác dùng trong tablespace chung | `DELETE`/purge hoặc `TRUNCATE`/rebuild phù hợp | File tablespace chung không tự thu nhỏ |
| Giảm kích thước system tablespace `ibdata` | Không thể chỉ bằng `OPTIMIZE TABLE` | Thường cần thiết kế lại và dựng instance/data directory mới theo quy trình migration/restore |

Nếu mục tiêu là xóa dữ liệu cũ theo thời gian ở bảng rất lớn, cân nhắc partitioning ngay từ thiết kế. Bỏ một partition có thể hiệu quả hơn xóa hàng triệu record, nhưng thay đổi partition vẫn là DDL và phải xét khóa ngoại, index, binary log và yêu cầu lưu giữ dữ liệu.

### 12. Checklist trước khi thu hồi dung lượng

1. Xác nhận mục tiêu là xóa logic, tái sử dụng page trong tablespace hay giảm dung lượng filesystem.
2. Xác định bảng nằm trong file-per-table, general tablespace hay system tablespace.
3. Kiểm tra foreign key, trigger, `AUTO_INCREMENT`, quyền và tác động implicit commit trước `TRUNCATE`/`DROP`.
4. Với `DELETE`, theo dõi transaction dài và purge để biết khi nào record cũ có thể được dọn.
5. Với `OPTIMIZE TABLE`, dự trù dung lượng tạm, I/O, metadata lock, thời gian và replica lag.
6. Đo số liệu metadata và kích thước file trước/sau; không suy ra file đã giảm chỉ từ số hàng.
7. Có backup và kiểm tra khả năng restore trước thao tác không thể rollback.
8. Không thao tác trực tiếp trên file `.ibd`, `ibdata`, redo hoặc undo; để InnoDB quản lý tablespace.

`DELETE` giải phóng record theo cơ chế transaction và purge; `TRUNCATE` làm rỗng bảng bằng DDL; `DROP` xóa đối tượng; `OPTIMIZE` rebuild để tổ chức lại cấu trúc. Chỉ khi hiểu loại tablespace và mục tiêu dung lượng mới có thể chọn đúng thao tác và dự đoán được phần không gian nào được tái sử dụng bên trong InnoDB, phần nào thực sự trả về hệ điều hành.

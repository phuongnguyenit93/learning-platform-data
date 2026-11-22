# System tablespace, file-per-table và general tablespace

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích tablespace là vùng lưu trữ vật lý của InnoDB và phân biệt nó với database/schema, table và index.
- Nhận biết vai trò, vị trí và cách cấu hình system tablespace.
- Hiểu `innodb_file_per_table` và cách InnoDB lưu mỗi bảng trong file `.ibd` riêng.
- Tạo general tablespace để nhiều bảng dùng chung một vùng lưu trữ.
- Chuyển bảng giữa system tablespace, file-per-table tablespace và general tablespace.
- So sánh khả năng thu hồi dung lượng, di chuyển, sao lưu và vận hành của ba loại tablespace.
- Theo dõi tablespace bằng `INFORMATION_SCHEMA` và các biến cấu hình InnoDB.
- Chọn cách bố trí dữ liệu phù hợp với dung lượng, I/O, vòng đời bảng và yêu cầu vận hành.

Các ví dụ hướng tới MySQL 8.0/8.4 với InnoDB. Một số chi tiết về metadata, câu lệnh DDL và cấu hình có thể khác giữa các phiên bản; hãy đối chiếu phiên bản server đang triển khai trước khi áp dụng.

## 1. Tablespace là gì?

Trong InnoDB, tablespace là vùng lưu trữ logic chứa các page dữ liệu và index. Tablespace được biểu diễn bởi một hoặc nhiều data file trên hệ thống tệp. InnoDB đọc và ghi các page trong tablespace thông qua cơ chế quản lý file space của engine.

Không nên đồng nhất các khái niệm sau:

- **Database/schema:** không gian tên logic dùng để nhóm bảng, view, routine và các đối tượng khác.
- **Table:** cấu trúc dữ liệu logic gồm hàng và cột.
- **Index:** cấu trúc hỗ trợ tìm kiếm và truy cập hàng; index của InnoDB cũng được lưu dưới dạng page.
- **Tablespace:** vùng lưu trữ vật lý nơi InnoDB phân bổ page cho dữ liệu và index.
- **Data file:** file trên đĩa đại diện cho một phần hoặc toàn bộ tablespace.

Một schema có thể có nhiều bảng ở các tablespace khác nhau. Một general tablespace có thể chứa bảng thuộc nhiều schema. Vì vậy, ranh giới schema và ranh giới lưu trữ không nhất thiết trùng nhau.

### 1.1. Ba cách bố trí cần biết

| Loại tablespace | Cách lưu trữ | Phạm vi dùng chung | Đặc điểm nổi bật |
|---|---|---|---|
| System tablespace | Một hoặc nhiều file hệ thống, thường bắt đầu bằng `ibdata1` | Toàn bộ instance InnoDB | Chứa change buffer và có thể chứa dữ liệu/index của bảng được đặt vào system tablespace |
| File-per-table | Một file `.ibd` cho mỗi bảng InnoDB | Riêng một bảng | Mặc định cho bảng mới; dễ thu hồi dung lượng khi truncate/drop bảng |
| General tablespace | Một tablespace dùng chung, có data file `.ibd` | Nhiều bảng, có thể thuộc nhiều schema | Cho phép nhóm bảng và đặt data file ở vị trí lưu trữ được quản lý riêng |

Không có một lựa chọn tốt nhất cho mọi hệ thống. File-per-table là mặc định phù hợp với phần lớn ứng dụng; system tablespace và general tablespace hữu ích trong những tình huống cần vùng lưu trữ dùng chung hoặc quản lý vị trí dữ liệu theo nhóm.

## 2. System tablespace

System tablespace là vùng lưu trữ dùng chung ở cấp InnoDB instance. Trong cấu hình phổ biến, file đầu tiên có tên `ibdata1` và nằm trong MySQL data directory.

System tablespace là nơi lưu change buffer. Nó cũng có thể chứa dữ liệu và index của các bảng nếu bảng được tạo hoặc chuyển vào system tablespace thay vì file-per-table hay general tablespace. Các cấu trúc nội bộ khác có thể phụ thuộc phiên bản và cấu hình; không nên suy luận rằng mọi file InnoDB hoặc toàn bộ metadata đều nằm trong `ibdata1`.

### 2.1. Cấu hình bằng innodb_data_file_path

Biến khởi động `innodb_data_file_path` xác định số lượng, tên và kích thước data file của system tablespace.

Ví dụ cấu hình một file có thể tự mở rộng:

```ini
[mysqld]
innodb_data_file_path=ibdata1:12M:autoextend
```

Trong ví dụ, `ibdata1` có kích thước ban đầu 12 MB và được phép tăng khi InnoDB cần thêm không gian. `autoextend` được đặt ở data file cuối cùng trong danh sách. Kích thước tăng thêm được điều khiển bởi `innodb_autoextend_increment`.

Có thể định nghĩa nhiều data file trong system tablespace:

```ini
[mysqld]
innodb_data_home_dir=
innodb_data_file_path=/data/ibdata1:512M;/disk2/ibdata2:128M:autoextend
```

Các file được ghép nối về mặt logic thành một system tablespace; đây không phải cơ chế striping dữ liệu tự động qua nhiều ổ đĩa. InnoDB phân bổ không gian theo cấu trúc tablespace và quy tắc của engine.

Đây là ví dụ cấu hình minh họa. Với instance đã chạy, kích thước hiện tại của file phải khớp với cấu hình được khai báo. Không được đổi con số ban đầu của một file đang tồn tại rồi kỳ vọng MySQL tự resize file đó khi khởi động.

### 2.2. Mở rộng system tablespace

Hai cách phổ biến để mở rộng:

1. Cấu hình data file cuối cùng có `autoextend`, sau đó khởi động lại server với cấu hình phù hợp.
2. Thêm data file mới vào `innodb_data_file_path` theo quy trình dừng server, cập nhật cấu hình và khởi động lại.

Khi thêm file mới, cần khai báo đúng kích thước hiện tại của file cuối cùng đang có. Nếu file cuối đang `autoextend`, quy trình thêm file cần điều chỉnh cấu hình để mô tả chính xác kích thước đã tăng của file đó trước khi thêm data file mới. Không khai báo một tên file đã tồn tại như thể đó là file mới.

### 2.3. System tablespace không thể thu nhỏ tại chỗ

Một đặc điểm vận hành quan trọng: MySQL không hỗ trợ giảm kích thước system tablespace đã tồn tại. Khi bảng bị xóa hoặc dữ liệu được giải phóng, không gian trống trong system tablespace có thể được InnoDB tái sử dụng, nhưng file system tablespace không tự co lại để trả dung lượng về hệ điều hành.

Nếu cần một system tablespace nhỏ hơn, hướng xử lý là tạo instance mới với cấu hình mong muốn rồi khôi phục dữ liệu từ backup theo quy trình được kiểm thử. Không xóa, đổi tên hoặc di chuyển thủ công `ibdata1` khi server đang dùng nó.

### 2.4. Đưa bảng vào system tablespace

Khi cần đặt một bảng vào system tablespace, có thể chỉ định tường minh:

```sql
CREATE TABLE app.legacy_cache (
    cache_id BIGINT NOT NULL,
    payload JSON NOT NULL,
    PRIMARY KEY (cache_id)
) ENGINE = InnoDB
  TABLESPACE = innodb_system;
```

`innodb_system` là tên tablespace đặc biệt của system tablespace. Tùy phiên bản và cấu hình, có các giới hạn về row format và tính năng; không nên đặt bảng vào system tablespace chỉ để giảm số lượng file mà không đánh giá hậu quả về thu hồi dung lượng và bảo trì.

## 3. File-per-table tablespace

File-per-table là cách InnoDB lưu dữ liệu và index của một bảng trong một tablespace riêng, thường được biểu diễn bằng file `.ibd` trong thư mục schema bên dưới MySQL data directory.

Ví dụ, bảng `sales.orders` thường có file:

```text
<datadir>/sales/orders.ibd
```

File chứa dữ liệu và các index của riêng bảng `orders`. Mỗi bảng có không gian lưu trữ riêng, nên kích thước và vòng đời file có thể được theo dõi độc lập.

### 3.1. innodb_file_per_table

Biến `innodb_file_per_table` điều khiển cách bố trí mặc định khi tạo bảng InnoDB. Trong MySQL 8.0/8.4, giá trị mặc định là `ON`.

Kiểm tra:

```sql
SHOW VARIABLES LIKE 'innodb_file_per_table';
```

Có thể thay đổi ở runtime bằng biến GLOBAL:

```sql
SET GLOBAL innodb_file_per_table = ON;
```

Thay đổi này ảnh hưởng cách bố trí mặc định của các bảng được tạo sau đó. Nó không tự động di chuyển những bảng đang nằm trong system tablespace hoặc general tablespace sang file-per-table. Muốn di chuyển bảng hiện có, cần dùng DDL `ALTER TABLE ... TABLESPACE` phù hợp.

Ngay cả khi biến mặc định đang OFF, có thể chỉ định rõ file-per-table khi tạo bảng:

```sql
CREATE TABLE app.events (
    event_id BIGINT NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (event_id)
) ENGINE = InnoDB
  TABLESPACE = innodb_file_per_table;
```

### 3.2. Ưu điểm của file-per-table

- Khi `DROP TABLE` hoặc `TRUNCATE TABLE` một bảng file-per-table, file riêng có thể được xóa/tạo lại và dung lượng được trả về hệ điều hành.
- Dễ theo dõi dung lượng của từng bảng qua kích thước file `.ibd`.
- Có thể đặt file bảng trên thiết bị lưu trữ riêng bằng tùy chọn `DATA DIRECTORY` trong những trường hợp được hỗ trợ.
- Hỗ trợ quy trình transportable tablespace cho việc export/import bảng riêng theo điều kiện và quy trình của InnoDB.
- Giảm phạm vi ảnh hưởng khi một file bảng gặp vấn đề lưu trữ so với việc nhiều bảng cùng nằm trong một file chia sẻ.
- Hỗ trợ các tính năng gắn với một số row format như `DYNAMIC` và `COMPRESSED` mà system tablespace không hỗ trợ theo cùng cách.

### 3.3. Giới hạn và chi phí

- Nhiều bảng đồng nghĩa nhiều file và file descriptor hơn. Instance có số lượng bảng rất lớn cần theo dõi giới hạn hệ điều hành và tài nguyên file.
- Metadata tablespace được giữ trong bộ nhớ trong thời gian sống của tablespace; số lượng tablespace quá lớn có thể tăng chi phí bộ nhớ.
- Dung lượng trống bên trong file của một bảng chỉ có thể được bảng đó sử dụng; không gian chưa dùng của bảng này không tự chuyển sang bảng khác.
- Thao tác drop bảng có thể cần xử lý nhiều page trong buffer pool và có thể tạo độ trễ trên hệ thống lớn.
- Một file riêng không có nghĩa backup vật lý có thể tùy tiện sao chép file đang mở; cần backup nhất quán theo quy trình của MySQL.

### 3.4. DELETE không đồng nghĩa file nhỏ lại

Xóa nhiều hàng bằng `DELETE` thường giải phóng page để InnoDB tái sử dụng bên trong tablespace. Kích thước file `.ibd` trên hệ điều hành không nhất thiết giảm ngay.

Với file-per-table, `TRUNCATE TABLE` hoặc `DROP TABLE` có thể trả không gian file về hệ điều hành. `OPTIMIZE TABLE` trên InnoDB thường thực hiện rebuild để tổ chức lại bảng; cần đánh giá dung lượng tạm, thời gian và metadata lock trước khi chạy trên bảng lớn.

## 4. General tablespace

General tablespace là tablespace InnoDB dùng chung do DBA tạo bằng `CREATE TABLESPACE`. Một general tablespace có thể chứa nhiều bảng, kể cả bảng thuộc các schema khác nhau. Nó không thuộc riêng một database/schema nào.

General tablespace hữu ích khi muốn:

- Gom một nhóm bảng vào cùng vùng lưu trữ.
- Đặt data file ở vị trí lưu trữ được quản lý riêng, có thể nằm ngoài MySQL data directory.
- Quản lý nhóm bảng theo mục đích vận hành, dung lượng hoặc thiết bị I/O.
- Giảm số lượng tablespace metadata trong bộ nhớ so với việc mỗi bảng có một file-per-table riêng.

General tablespace chia sẻ dung lượng giữa các bảng, vì vậy cần theo dõi tăng trưởng của toàn bộ nhóm bảng.

### 4.1. Tạo general tablespace

Ví dụ tạo tablespace tên `app_shared`:

```sql
CREATE TABLESPACE app_shared
    ADD DATAFILE 'app_shared.ibd'
    ENGINE = InnoDB;
```

`ADD DATAFILE` có thể chỉ định tên file. Nếu bỏ qua phần này, MySQL có thể tạo file với tên duy nhất theo quy tắc của engine.

Tên general tablespace phân biệt chữ hoa/chữ thường trong MySQL. Không dùng tiền tố `innodb_` cho tên tự đặt vì đây là tiền tố dành cho mục đích đặc biệt.

### 4.2. Đặt bảng mới vào general tablespace

Sau khi tablespace đã tồn tại, có thể tạo bảng trong đó:

```sql
CREATE TABLE sales.orders_archive (
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(19,2) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_archive_customer (customer_id)
) ENGINE = InnoDB
  TABLESPACE = app_shared;
```

Một bảng khác thuộc schema khác cũng có thể sử dụng cùng general tablespace:

```sql
CREATE TABLE audit.event_archive (
    event_id BIGINT NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    occurred_at DATETIME NOT NULL,
    PRIMARY KEY (event_id)
) ENGINE = InnoDB
  TABLESPACE = app_shared;
```

Như vậy, `sales.orders_archive` và `audit.event_archive` có thể cùng lưu trong `app_shared.ibd`, dù chúng thuộc hai schema khác nhau.

### 4.3. Đặt data file ngoài data directory

General tablespace có thể đặt data file trong một thư mục ngoài MySQL data directory:

```sql
CREATE TABLESPACE archive_storage
    ADD DATAFILE '/mysql-storage/archive/archive_storage.ibd'
    ENGINE = InnoDB;
```

Thư mục phải tồn tại và phải được InnoDB nhận diện là thư mục hợp lệ. Với đường dẫn ngoài các thư mục đã biết, có thể cần cấu hình `innodb_directories` lúc khởi động server. Không thể tùy ý tạo general tablespace trong một thư mục con nằm bên dưới data directory vì có thể xung đột với cách InnoDB tạo file-per-table.

Đường dẫn ví dụ chỉ minh họa cú pháp. Trên production, cần chuẩn bị quyền đọc/ghi của tài khoản chạy MySQL, dung lượng, mount point, backup và quy trình phục hồi trước khi tạo tablespace.

### 4.4. Di chuyển bảng vào general tablespace

Có thể chuyển bảng hiện có vào general tablespace:

```sql
ALTER TABLE sales.orders_archive
    TABLESPACE = app_shared;
```

Lệnh này chuyển bảng từ file-per-table hoặc system tablespace vào general tablespace đã tồn tại. Không thể chuyển một tablespace file-per-table đang có thành general tablespace bằng cách đổi tên file; cần thực hiện DDL di chuyển bảng.

### 4.5. Giới hạn của general tablespace

- Không hỗ trợ temporary table.
- Không hỗ trợ tạo temporary general tablespace.
- Không hỗ trợ đặt partition/subpartition của bảng InnoDB vào shared tablespace như general hoặc system tablespace.
- Không hỗ trợ `ALTER TABLE ... DISCARD TABLESPACE` và `IMPORT TABLESPACE` cho bảng thuộc general tablespace.
- Khi bảng trong general tablespace bị `DROP` hoặc `TRUNCATE`, phần dung lượng được giải phóng nằm bên trong file dùng chung để InnoDB tái sử dụng; file không tự co lại để trả dung lượng về hệ điều hành.
- DDL kiểu copy/rebuild trên bảng trong shared tablespace có thể cần thêm dung lượng tạm tương đương dữ liệu và index của bảng; phần tăng thêm có thể vẫn nằm trong file shared sau khi DDL hoàn tất.
- DDL liên quan tới general tablespace sử dụng metadata lock ở phạm vi tablespace và có thể ảnh hưởng các thao tác DDL khác trên bảng cùng tablespace.

Vì các giới hạn này, general tablespace cần kế hoạch dung lượng và vòng đời rõ ràng. Không nên gom các bảng tăng trưởng không kiểm soát vào cùng một file chỉ để giảm số lượng `.ibd`.

## 5. Di chuyển bảng giữa các loại tablespace

MySQL cho phép dùng `ALTER TABLE ... TABLESPACE` để di chuyển bảng giữa general tablespace, file-per-table tablespace và system tablespace.

### 5.1. Từ file-per-table hoặc system sang general

```sql
ALTER TABLE sales.orders_archive
    TABLESPACE = app_shared;
```

General tablespace `app_shared` phải được tạo trước.

### 5.2. Từ general hoặc file-per-table sang system

```sql
ALTER TABLE sales.orders_archive
    TABLESPACE = innodb_system;
```

Chỉ dùng khi có lý do vận hành rõ ràng. Đưa dữ liệu người dùng vào system tablespace có thể làm file system tablespace tăng và không thể thu nhỏ tại chỗ sau này.

### 5.3. Từ system hoặc general sang file-per-table

```sql
ALTER TABLE sales.orders_archive
    TABLESPACE = innodb_file_per_table;
```

Lệnh này tạo file-per-table tablespace cho bảng. Sau khi di chuyển khỏi general tablespace, dung lượng trống trong file shared vẫn là dung lượng nội bộ của general tablespace; nó không tự giảm theo kích thước của bảng đã chuyển đi.

### 5.4. ALTER TABLE ... TABLESPACE là thao tác rebuild

Trong MySQL 8.4, `ALTER TABLE ... TABLESPACE` thực hiện full table rebuild, kể cả khi tablespace đích có vẻ giống tablespace hiện tại. Vì vậy, cần dự trù:

- Dung lượng bổ sung cho dữ liệu và index trong lúc rebuild.
- I/O đọc/ghi và thời gian thực hiện trên bảng lớn.
- Metadata lock ở thời điểm bắt đầu/kết thúc DDL.
- Ảnh hưởng đến replication lag, backup window và workload đang chạy.
- Khả năng rollback/khôi phục khi DDL thất bại.

Không chạy di chuyển hàng loạt trên production mà chưa thử với bản sao dữ liệu và kiểm tra dung lượng đĩa. Với general tablespace, phần dung lượng tạm phát sinh từ table-copy operation có thể không được trả lại hệ điều hành sau khi hoàn tất.

### 5.5. Không dùng ALTER TABLESPACE như công cụ di chuyển partition vào shared tablespace

InnoDB không hỗ trợ đặt partition/subpartition vào shared tablespace như system hoặc general tablespace. Khi làm việc với bảng partitioned, cần kiểm tra riêng giới hạn tablespace của partition; không áp dụng ví dụ di chuyển bảng thường cho partitioned table.

## 6. So sánh khả năng thu hồi dung lượng

Đây là khác biệt có ảnh hưởng lớn đến vận hành:

| Thao tác | System tablespace | File-per-table | General tablespace |
|---|---|---|---|
| `DELETE` nhiều hàng | Page trống được tái sử dụng nội bộ; file không tự nhỏ lại | Page có thể tái sử dụng trong bảng; file thường không nhỏ ngay | Page trống được tái sử dụng bởi các bảng trong tablespace; file không tự nhỏ lại |
| `TRUNCATE TABLE` | Dung lượng trống được giữ trong shared file để tái sử dụng | File bảng được tạo lại và dung lượng có thể trả về OS | Dung lượng được giữ trong shared file để tái sử dụng |
| `DROP TABLE` | Không làm system tablespace co lại | File `.ibd` của bảng được xóa và dung lượng trả về OS | Dung lượng được giữ trong shared file; cần drop tablespace riêng nếu muốn xóa toàn bộ file |
| Chuyển một bảng ra ngoài | System file không co lại | File riêng theo bảng đích | File shared vẫn giữ dung lượng trống để tái sử dụng |

Ví dụ: nếu một bảng 200 GB nằm trong general tablespace và bị drop, InnoDB có thể tái sử dụng không gian bên trong file shared cho dữ liệu InnoDB khác. Hệ điều hành vẫn nhìn thấy file tablespace có kích thước lớn. Nếu mục tiêu là trả dung lượng về OS, cần di chuyển hoặc drop các bảng còn lại, sau đó drop chính general tablespace khi nó rỗng.

### 6.1. Khi nào file-per-table phù hợp?

Chọn file-per-table khi:

- Bảng có vòng đời độc lập và thường xuyên được archive/drop/truncate.
- Cần quan sát kích thước từng bảng.
- Cần transport/import một bảng riêng theo quy trình được hỗ trợ.
- Muốn tránh việc bảng này chiếm dung lượng trống của bảng khác.
- Phần lớn workload là ứng dụng OLTP thông thường và không có yêu cầu đặc biệt về shared storage.

### 6.2. Khi nào general tablespace phù hợp?

Cân nhắc general tablespace khi:

- Có một nhóm bảng cần cùng vị trí lưu trữ hoặc cùng chính sách quản lý dung lượng.
- Cần đặt file ở một thiết bị/thư mục được quản lý riêng.
- Muốn giảm số lượng tablespace metadata so với rất nhiều file-per-table.
- Các bảng có vòng đời và tốc độ tăng trưởng tương đối đồng nhất.
- Đã có kế hoạch xử lý dung lượng trống bên trong file shared và giới hạn import/export.

### 6.3. Khi nào system tablespace nên được giữ cho nội bộ?

Trong nhiều ứng dụng, giữ user table ở file-per-table hoặc general tablespace giúp tránh system tablespace phình to vì dữ liệu nghiệp vụ. System tablespace vẫn cần cho các cấu trúc nội bộ của InnoDB, và chỉ nên đặt user table vào đó khi đã hiểu giới hạn về mở rộng/thu nhỏ cũng như quy trình backup/restore.

## 7. Theo dõi tablespace và dung lượng

### 7.1. Kiểm tra cấu hình liên quan

```sql
SHOW VARIABLES LIKE 'innodb_file_per_table';
SHOW VARIABLES LIKE 'innodb_data_file_path';
SHOW VARIABLES LIKE 'innodb_data_home_dir';
SHOW VARIABLES LIKE 'datadir';
```

Các biến này cho biết mặc định tạo bảng, đường dẫn system data file và data directory. Không phải tất cả tablespace đều nằm trong `datadir`; general tablespace có thể được đặt ở vị trí hợp lệ bên ngoài.

### 7.2. Liệt kê tablespace

```sql
SELECT
    SPACE,
    NAME,
    SPACE_TYPE,
    FILE_SIZE,
    ALLOCATED_SIZE,
    AUTOEXTEND_SIZE,
    ENCRYPTION,
    STATE
FROM information_schema.INNODB_TABLESPACES
ORDER BY SPACE_TYPE, NAME;
```

Các cột cung cấp thông tin về tablespace và data file. `FILE_SIZE` biểu diễn kích thước file theo metadata của InnoDB; `ALLOCATED_SIZE` biểu diễn dung lượng đã được cấp phát theo cách engine báo cáo. Không đồng nhất các giá trị này với tổng kích thước logic của hàng trong bảng.

### 7.3. Xem đường dẫn data file

```sql
SELECT
    SPACE,
    PATH
FROM information_schema.INNODB_DATAFILES
ORDER BY SPACE, PATH;
```

Truy vấn này hữu ích khi cần xác định file vật lý của tablespace. Đường dẫn thực tế còn phụ thuộc cấu hình và quyền hệ thống.

### 7.4. Xác định bảng thuộc tablespace nào

```sql
SELECT
    t.NAME AS table_name,
    t.SPACE,
    s.NAME AS tablespace_name,
    s.SPACE_TYPE,
    s.FILE_SIZE,
    s.ALLOCATED_SIZE
FROM information_schema.INNODB_TABLES AS t
JOIN information_schema.INNODB_TABLESPACES AS s
  ON s.SPACE = t.SPACE
WHERE t.NAME LIKE 'sales/%'
ORDER BY t.NAME;
```

Tên bảng trong `INNODB_TABLES` thường được biểu diễn theo dạng `schema/table`. Có thể dùng truy vấn tương tự để xác định những bảng đang chiếm một general tablespace cụ thể.

### 7.5. Xác định các bảng trong general tablespace trước khi drop

```sql
SELECT
    s.NAME AS tablespace_name,
    t.NAME AS table_name
FROM information_schema.INNODB_TABLESPACES AS s
JOIN information_schema.INNODB_TABLES AS t
  ON t.SPACE = s.SPACE
WHERE s.NAME = 'app_shared'
ORDER BY t.NAME;
```

Chỉ drop general tablespace sau khi không còn bảng nào trong đó. `DROP DATABASE` có thể xóa các bảng thuộc schema nhưng không tự xóa general tablespace dùng chung, kể cả khi tablespace trở nên rỗng.

## 8. Tạo và xóa general tablespace theo quy trình

Ví dụ sau minh họa vòng đời của một general tablespace trong môi trường thử nghiệm.

### 8.1. Tạo tablespace và hai schema

```sql
CREATE DATABASE IF NOT EXISTS sales;
CREATE DATABASE IF NOT EXISTS audit;

CREATE TABLESPACE archive_shared
    ADD DATAFILE 'archive_shared.ibd'
    ENGINE = InnoDB;
```

### 8.2. Tạo bảng ở hai schema khác nhau

```sql
CREATE TABLE sales.orders_archive (
    order_id BIGINT NOT NULL,
    total_amount DECIMAL(19,2) NOT NULL,
    archived_at DATETIME NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB
  TABLESPACE = archive_shared;

CREATE TABLE audit.events_archive (
    event_id BIGINT NOT NULL,
    event_name VARCHAR(100) NOT NULL,
    archived_at DATETIME NOT NULL,
    PRIMARY KEY (event_id)
) ENGINE = InnoDB
  TABLESPACE = archive_shared;
```

### 8.3. Xác nhận bảng cùng nằm trong tablespace

```sql
SELECT
    s.NAME AS tablespace_name,
    t.NAME AS table_name
FROM information_schema.INNODB_TABLESPACES AS s
JOIN information_schema.INNODB_TABLES AS t
  ON t.SPACE = s.SPACE
WHERE s.NAME = 'archive_shared'
ORDER BY t.NAME;
```

### 8.4. Di chuyển một bảng ra file-per-table

```sql
ALTER TABLE sales.orders_archive
    TABLESPACE = innodb_file_per_table;
```

Lệnh trên rebuild bảng. File shared `archive_shared.ibd` vẫn chứa bảng `audit.events_archive`; không thể drop tablespace khi còn bảng này.

### 8.5. Xóa bảng còn lại rồi drop tablespace

Trong môi trường thực hành:

```sql
DROP TABLE audit.events_archive;
DROP TABLESPACE archive_shared;
```

Chỉ thực hiện các lệnh DROP trên dữ liệu thử nghiệm hoặc sau khi đã xác nhận chính xác các bảng và kế hoạch lưu trữ. Xóa bảng cuối cùng không tự xóa general tablespace; cần lệnh `DROP TABLESPACE` riêng.

## 9. Backup, restore và di chuyển dữ liệu

Tablespace là một phần của bố cục lưu trữ vật lý, vì vậy cần được tính đến trong kế hoạch backup và restore.

### 9.1. Backup vật lý

Backup vật lý phải tạo ra một bản sao nhất quán của toàn bộ thành phần cần thiết để khôi phục instance: data file, redo/undo và metadata liên quan theo phương pháp backup đang dùng. Không tự sao chép `ibdata1`, `.ibd` hoặc file general tablespace từ một server đang chạy rồi xem đó là backup hợp lệ.

Với system tablespace, mất file hệ thống có thể ảnh hưởng nhiều bảng và cấu trúc InnoDB dùng chung. Với general tablespace, file dùng chung chứa nhiều bảng; backup một bảng riêng bằng cách chỉ copy file shared có thể mang theo dữ liệu không liên quan và không tạo ra một bản import độc lập hợp lệ.

### 9.2. Backup logic

Dump logic lưu cấu trúc và dữ liệu dưới dạng câu lệnh SQL. Khi restore, cách bố trí tablespace có thể phụ thuộc DDL được dump, cấu hình đích và các thao tác tạo tablespace tương ứng. Nếu cần giữ nguyên placement của bảng trong general tablespace, phải bảo đảm DDL tạo tablespace đích trước khi tạo bảng và kiểm tra lại sau restore.

### 9.3. Transportable tablespace

File-per-table tablespace hỗ trợ quy trình export/import bảng riêng trong các điều kiện của InnoDB, thường liên quan đến `FLUSH TABLES ... FOR EXPORT`, `DISCARD TABLESPACE` và `IMPORT TABLESPACE`. Quy trình cần định nghĩa bảng tương thích, file metadata khi được yêu cầu, phiên bản và cấu hình tương thích.

General tablespace không hỗ trợ `ALTER TABLE ... DISCARD TABLESPACE` và `IMPORT TABLESPACE` cho từng bảng thuộc nó. Nếu cần vận chuyển một bảng độc lập, cần chuyển bảng sang file-per-table theo kế hoạch DDL phù hợp trước khi dùng quy trình transportable tablespace.

### 9.4. Khôi phục khi cần giảm system tablespace

Nếu system tablespace đã tăng lớn và cần một bố cục mới nhỏ hơn, phương án được hỗ trợ là tạo instance mới với cấu hình mong muốn rồi restore từ backup. Không xóa các page trống hoặc cắt file `ibdata1` bằng công cụ hệ điều hành.

## 10. Những lỗi vận hành thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| `ibdata1` tiếp tục lớn sau khi xóa bảng | System tablespace giữ không gian trống để InnoDB tái sử dụng | Theo dõi mức sử dụng; nếu cần nhỏ hơn, migrate/restore sang instance mới |
| `DROP TABLE` không làm file general nhỏ lại | Bảng nằm trong shared tablespace | Không gian được tái sử dụng nội bộ; drop tablespace khi đã rỗng nếu cần trả file về OS |
| `DELETE` nhiều hàng nhưng `.ibd` không giảm | DELETE giải phóng page bên trong, không nhất thiết thu nhỏ file | Đánh giá `OPTIMIZE TABLE`/rebuild hoặc vòng đời truncate/drop phù hợp |
| Đổi `innodb_file_per_table` nhưng bảng cũ không chuyển | Biến chỉ thay đổi mặc định tạo bảng mới | Dùng `ALTER TABLE ... TABLESPACE = innodb_file_per_table` nếu cần di chuyển |
| Không thể drop general tablespace | Vẫn còn bảng thuộc tablespace | Liệt kê bằng `INNODB_TABLESPACES`/`INNODB_TABLES`, di chuyển hoặc drop bảng theo kế hoạch |
| `DROP DATABASE` xong general tablespace vẫn tồn tại | General tablespace không thuộc một schema cụ thể | Xác nhận tablespace rỗng rồi `DROP TABLESPACE` riêng |
| `ALTER TABLE ... TABLESPACE` cần nhiều dung lượng | Di chuyển gây full table rebuild | Dự trù thêm dung lượng cho data/index và theo dõi DDL |
| Không import được bảng từ general tablespace | General tablespace không hỗ trợ DISCARD/IMPORT TABLESPACE cho từng bảng | Chuyển bảng sang file-per-table theo quy trình được hỗ trợ |
| Tạo general tablespace ngoài datadir bị lỗi | Thư mục chưa tồn tại hoặc chưa được InnoDB nhận diện | Chuẩn bị thư mục, quyền và cấu hình `innodb_directories` đúng cách |

## 11. Quy trình lựa chọn tablespace

1. **Xác định vòng đời bảng:** bảng có được truncate/drop/archive độc lập hay tồn tại lâu dài?
2. **Xác định nhu cầu dung lượng:** cần thu hồi dung lượng về OS hay chỉ cần tái sử dụng nội bộ?
3. **Xác định vị trí lưu trữ:** có cần đặt bảng trên thiết bị hoặc thư mục riêng không?
4. **Đánh giá số lượng bảng:** số file `.ibd` và metadata tablespace có ảnh hưởng vận hành không?
5. **Đánh giá backup/restore:** cần backup toàn instance, nhóm bảng hay vận chuyển từng bảng?
6. **Chọn mặc định:** file-per-table phù hợp với đa số bảng nghiệp vụ có vòng đời độc lập.
7. **Dùng general tablespace có chủ đích:** gom nhóm bảng có yêu cầu lưu trữ tương đồng và chấp nhận shared capacity/restore limitations.
8. **Hạn chế user table trong system tablespace:** chỉ dùng khi có lý do kỹ thuật cụ thể và hiểu rằng system tablespace không thể thu nhỏ tại chỗ.
9. **Thử nghiệm DDL di chuyển:** xác minh rebuild, thời gian, metadata lock, dung lượng và replication lag.
10. **Theo dõi định kỳ:** so sánh kích thước file, allocated size, dung lượng trống và tốc độ tăng trưởng.

## 12. Checklist trước khi triển khai production

- [ ] Đã xác định bảng đang ở system, file-per-table hay general tablespace.
- [ ] Đã kiểm tra `innodb_file_per_table` và `innodb_data_file_path`.
- [ ] Đã phân biệt dung lượng file với dung lượng page trống có thể tái sử dụng.
- [ ] Đã hiểu system tablespace không thể thu nhỏ tại chỗ.
- [ ] General tablespace chỉ chứa các bảng có vòng đời và nhu cầu lưu trữ phù hợp.
- [ ] Đã kiểm tra giới hạn temporary table, partition và DISCARD/IMPORT của general tablespace.
- [ ] Đã xác nhận thư mục data file, quyền truy cập và dung lượng thiết bị.
- [ ] Đã tính dung lượng bổ sung cho `ALTER TABLE ... TABLESPACE` rebuild.
- [ ] Đã có backup nhất quán và kế hoạch restore được kiểm thử.
- [ ] Không copy `.ibd` hoặc `ibdata1` thủ công từ server đang chạy.
- [ ] Đã kiểm tra danh sách bảng trước khi `DROP TABLESPACE`.
- [ ] Đã theo dõi metadata lock, I/O, replication lag và dung lượng sau di chuyển.

## 13. Kết luận

System tablespace là vùng lưu trữ dùng chung của InnoDB, thường được biểu diễn bởi `ibdata1`; nó chứa change buffer và có thể chứa dữ liệu/index của bảng được đặt vào đó. System tablespace có thể mở rộng nhưng không thể thu nhỏ tại chỗ.

File-per-table lưu dữ liệu và index của một bảng trong file `.ibd` riêng. Đây là mặc định phù hợp cho phần lớn bảng nghiệp vụ vì dễ quan sát, di chuyển và thu hồi dung lượng khi truncate/drop bảng. General tablespace cho phép nhiều bảng, kể cả từ nhiều schema, dùng chung một vùng lưu trữ; đổi lại, dung lượng trống được giữ trong file shared và có các giới hạn về temporary table, partition và transportable tablespace.

Hãy chọn tablespace theo vòng đời dữ liệu, yêu cầu thu hồi dung lượng, vị trí I/O và chiến lược backup/restore. Trước khi di chuyển bảng, luôn tính chi phí full rebuild và kiểm tra trên môi trường thử nghiệm. Quản lý tablespace đúng cách giúp kiểm soát tăng trưởng file, giảm rủi ro vận hành và giữ cho quy trình khôi phục dữ liệu có thể dự đoán.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: The System Tablespace](https://dev.mysql.com/doc/refman/8.4/en/innodb-system-tablespace.html)
- [MySQL 8.4 Reference Manual: File-Per-Table Tablespaces](https://dev.mysql.com/doc/refman/8.4/en/innodb-file-per-table-tablespaces.html)
- [MySQL 8.4 Reference Manual: General Tablespaces](https://dev.mysql.com/doc/refman/8.4/en/general-tablespaces.html)
- [MySQL 8.4 Reference Manual: CREATE TABLESPACE](https://dev.mysql.com/doc/refman/8.4/en/create-tablespace.html)

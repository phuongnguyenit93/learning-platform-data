# Data dictionary và khác biệt so với các file metadata của bản cũ

MySQL cần lưu thông tin mô tả database để hiểu cấu trúc bảng, cột, index, view, trigger, routine và các đối tượng khác. Những thông tin này được gọi là **metadata**. Cách MySQL lưu và quản lý metadata đã thay đổi lớn từ MySQL 8.0.

Ở các phiên bản cũ, metadata được phân tán giữa các file trong thư mục dữ liệu, các bảng hệ thống và dictionary riêng của storage engine. Ví dụ, file `.frm` chứa định nghĩa bảng ở lớp server, còn InnoDB duy trì thông tin nội bộ riêng về bảng và tablespace. Từ MySQL 8.0, MySQL sử dụng **transactional data dictionary** tập trung, lưu metadata trong các bảng dictionary do server quản lý và sử dụng InnoDB.

Sự thay đổi này ảnh hưởng đến cách đọc metadata, sao lưu, khôi phục, nâng cấp phiên bản và xử lý sự cố. Đặc biệt, không thể tiếp tục coi file `.frm` là nguồn định nghĩa bảng hoặc tự sao chép/xóa các file metadata như cách làm với một số hệ thống cũ.

Bài học thuộc phạm vi `DATABASE_MYSQL`: hiểu kiến trúc metadata để thiết kế, truy vấn, quản trị và vận hành database quan hệ an toàn; biết dùng giao diện SQL được hỗ trợ để kiểm tra schema thay vì phụ thuộc vào cấu trúc file nội bộ.

## 1. Metadata và data dictionary

### 1.1. Metadata là gì?

Metadata là dữ liệu mô tả các đối tượng trong database, không phải dữ liệu nghiệp vụ được lưu trong từng hàng. Ví dụ, với bảng:

~~~sql
CREATE TABLE sales.orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    total DECIMAL(12, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer (customer_id)
) ENGINE = InnoDB;
~~~

Các hàng chứa mã đơn hàng, khách hàng, tổng tiền và thời điểm tạo là dữ liệu nghiệp vụ. Metadata mô tả:

- Database `sales` và bảng `orders`.
- Tên, thứ tự và kiểu dữ liệu của từng cột.
- Thuộc tính `NOT NULL`, `AUTO_INCREMENT` và giá trị mặc định.
- Primary key và secondary index.
- Storage engine InnoDB.
- Charset, collation, partition và các thuộc tính khác nếu có.

Metadata cũng bao gồm định nghĩa view, trigger, stored procedure, function, event, tablespace, partition và các đối tượng database khác.

### 1.2. Data dictionary là gì?

**Data dictionary** là thành phần quản lý metadata của các đối tượng database. Server dùng dictionary để tra cứu định nghĩa, phân giải tên, kiểm tra quan hệ giữa các đối tượng, chuẩn bị câu lệnh và thực hiện DDL.

Một luồng khái quát:

~~~text
Câu lệnh SQL
    |
    v
Phân tích cú pháp và phân giải tên
    |
    v
Tra cứu metadata / data dictionary
    |
    +--> Metadata object đã có trong cache
    |
    +--> Đọc dictionary khi cần
    |
    v
Kiểm tra quyền và chuẩn bị đối tượng
    |
    v
Thực thi câu lệnh và làm việc với storage engine
~~~

Đây là sơ đồ khái niệm. Quy trình nội bộ thực tế có nhiều bước hơn và thay đổi theo loại câu lệnh, storage engine và phiên bản.

Data dictionary không phải một schema ứng dụng mà người dùng có thể tự tạo hoặc cập nhật. Nó là thành phần nội bộ của MySQL Server, có giao diện đọc metadata được hỗ trợ như `SHOW`, `INFORMATION_SCHEMA` và một số công cụ chẩn đoán.

## 2. Kiến trúc metadata trước MySQL 8.0

Trong các phiên bản cũ, metadata không nằm trong một kho thống nhất. Tùy loại đối tượng và storage engine, thông tin có thể được lưu trong:

1. File metadata trong thư mục database của data directory.
2. Bảng hệ thống trong schema `mysql`.
3. Data dictionary riêng của storage engine, chẳng hạn dictionary nội bộ của InnoDB.
4. File dữ liệu, file index hoặc tablespace chứa dữ liệu vật lý và một số thông tin engine-specific.

Do đó, file metadata ở lớp server và dictionary bên trong storage engine có thể cùng mô tả những khía cạnh liên quan của một bảng. Chúng phải nhất quán với nhau.

### 2.1. File .frm

Trong các phiên bản MySQL trước 8.0, mỗi bảng thường có file `.frm` chứa thông tin định nghĩa bảng ở lớp server, ví dụ:

- Tên và cấu trúc cột.
- Kiểu dữ liệu, thuộc tính và thứ tự cột.
- Thông tin index và các thuộc tính định nghĩa bảng ở mức server.
- Thông tin cần thiết để server mở và xử lý bảng.

Các view cũng có file `.frm` trong những phiên bản sử dụng cơ chế này.

File `.frm` không chứa toàn bộ hàng dữ liệu của bảng. Dữ liệu và index vật lý phụ thuộc storage engine. Ví dụ:

- MyISAM thường sử dụng `.MYD` cho dữ liệu và `.MYI` cho index.
- InnoDB có thể lưu bảng trong shared system tablespace `ibdata*` hoặc file-per-table `.ibd`, tùy cấu hình.

Vì vậy, không được nhầm `.frm` với file dữ liệu `.ibd`, `.MYD` hoặc file index `.MYI`.

### 2.2. Một số file metadata khác

Ngoài `.frm`, các phiên bản cũ còn dùng những file có vai trò riêng:

| File | Vai trò trong kiến trúc cũ | Thông tin chuyển sang đâu trong MySQL 8.0? |
|---|---|---|
| `.frm` | Định nghĩa bảng và view ở lớp server | Data dictionary tables |
| `.TRG` | Thông tin định nghĩa/tham số trigger | Data dictionary tables |
| `.TRN` | Namespace/tên trigger | Data dictionary tables |
| `.par` | Thông tin định nghĩa partition cho những trường hợp còn dùng file này | Data dictionary tables; InnoDB đã có native partitioning từ MySQL 5.7 |
| `db.opt` | Charset và collation mặc định của database | Data dictionary tables |
| `.isl` | Đường dẫn tới file-per-table tablespace InnoDB đặt ngoài data directory | Thông tin tablespace trong data dictionary |
| `ddl_log.log` | Ghi nhận thao tác metadata phát sinh từ một số câu lệnh DDL | Cơ chế DDL và dictionary mới |

Bảng này mô tả vai trò khái quát của các file được loại bỏ. Không phải mọi phiên bản hoặc mọi storage engine đều tạo tất cả các loại file này. Ví dụ, InnoDB ngừng sử dụng file partition `.par` khi hỗ trợ native partitioning từ MySQL 5.7.

### 2.3. Metadata trong system tables và storage engine

Một số thông tin hệ thống cũ được lưu trong các bảng thuộc schema `mysql`. Ví dụ, các phiên bản cũ lưu định nghĩa stored routine và event trong các bảng hệ thống như `proc` và `event`. Những bảng này không đồng nghĩa với file `.frm`.

InnoDB cũng duy trì dictionary nội bộ để quản lý bảng, index, tablespace và các đối tượng thuộc engine. Trong kiến trúc cũ, server-level metadata và InnoDB internal dictionary có vai trò khác nhau nhưng phải mô tả cùng một đối tượng nhất quán.

Điều này làm cho việc quản lý metadata phức tạp hơn: một thao tác DDL có thể phải cập nhật nhiều nơi. Khi có sự cố hoặc thao tác file không đúng, trạng thái file metadata, system tables và dictionary của engine có thể không còn khớp.

### 2.4. Vì sao kiến trúc file-based gây khó khăn?

Các hạn chế của cách lưu metadata phân tán gồm:

- Server phải quản lý và đọc nhiều file định nghĩa.
- Việc quét file và tra cứu metadata có thể tốn chi phí.
- Metadata ở server và storage engine phải được đồng bộ.
- Lỗi filesystem, file bị thiếu hoặc bị hỏng có thể khiến server không mở được bảng.
- Xử lý crash recovery, replication và DDL phức tạp hơn.
- Khó mở rộng metadata cho những loại đối tượng hoặc tính năng mới.
- Các công cụ sao lưu và khôi phục phải hiểu những file metadata liên quan.

Ví dụ, nếu file `.frm` bị thiếu nhưng file dữ liệu InnoDB vẫn còn, server có thể không mở bảng bình thường dù dữ liệu vật lý chưa chắc đã mất. Nếu định nghĩa trong file và dictionary nội bộ InnoDB không khớp, thao tác nâng cấp hoặc mở bảng có thể gặp lỗi.

Không nên tự sửa file để khớp với dictionary hoặc tự tạo file thay thế bằng cách đổi tên. Phải xác định đúng phiên bản, storage engine và phương án khôi phục được hỗ trợ.

## 3. Transactional data dictionary từ MySQL 8.0

MySQL 8.0 thay thế kiến trúc metadata phân tán bằng một data dictionary giao dịch (transactional data dictionary) được quản lý tập trung.

### 3.1. Metadata được lưu trong InnoDB

Các bảng dictionary nội bộ thuộc schema hệ thống `mysql` và sử dụng InnoDB. Các bảng này được bảo vệ; người dùng không thể truy vấn hoặc sửa trực tiếp theo cách thông thường.

MySQL cung cấp các giao diện ổn định hơn để xem metadata:

- `INFORMATION_SCHEMA`: thông tin về schema, bảng, cột, index, routine, trigger, partition và nhiều đối tượng khác.
- `SHOW`: các câu lệnh như `SHOW CREATE TABLE`, `SHOW COLUMNS`, `SHOW INDEX`, `SHOW TRIGGERS`.
- `Performance Schema`: thông tin quan sát hoạt động server, lock và các sự kiện.
- `sys`: các view hỗ trợ chẩn đoán được xây dựng trên Performance Schema và các nguồn khác.

Các giao diện này che giấu cấu trúc lưu trữ nội bộ. Ứng dụng nên dựa vào chúng thay vì phụ thuộc vào tên bảng dictionary bên trong.

### 3.2. Lợi ích của transactional data dictionary

So với kiến trúc cũ, data dictionary mới mang lại:

- **Quản lý tập trung:** metadata của các đối tượng được quản lý trong một schema dictionary thống nhất.
- **Tính giao dịch và crash-safe:** thay đổi metadata được lưu bằng cơ chế InnoDB, hỗ trợ phục hồi nhất quán sau sự cố.
- **Atomic DDL:** một số thao tác DDL được hỗ trợ có thể được thực hiện nguyên tử, bao gồm cập nhật dictionary và thay đổi liên quan.
- **Cache metadata thống nhất:** các đối tượng dictionary được cache trong bộ nhớ và có thể tái sử dụng.
- **Tích hợp INFORMATION_SCHEMA:** nhiều view metadata có thể truy vấn trên data dictionary, hỗ trợ optimizer sử dụng index của nguồn bên dưới.
- **Khả năng mở rộng:** thêm thuộc tính và loại đối tượng mới thuận tiện hơn so với phụ thuộc vào cấu trúc file cố định.

### 3.3. Atomic DDL không phải rollback DDL bằng transaction người dùng

Atomic DDL giúp server bảo đảm thao tác DDL được hỗ trợ hoàn tất toàn bộ hoặc được phục hồi khi có lỗi/crash. Nó không có nghĩa mọi câu lệnh DDL có thể được hoàn tác bằng `ROLLBACK` trong transaction ứng dụng.

Ví dụ, nhiều câu lệnh `CREATE TABLE`, `ALTER TABLE` và `DROP TABLE` vẫn gây implicit commit. Hãy tách biệt:

- Atomic DDL: bảo đảm nhất quán ở cấp server trong quá trình thực hiện thao tác DDL được hỗ trợ.
- Transaction DML: quản lý thay đổi dữ liệu hàng bằng `START TRANSACTION`, `COMMIT`, `ROLLBACK`.

## 4. So sánh kiến trúc cũ và mới

| Tiêu chí | Trước MySQL 8.0 | MySQL 8.0 trở lên |
|---|---|---|
| Nguồn metadata | File metadata, system tables và dictionary riêng của storage engine | Transactional data dictionary tập trung |
| Định nghĩa bảng | File `.frm` ở lớp server | Dictionary tables |
| Trigger | File `.TRG`, `.TRN` | Dictionary tables |
| Định nghĩa partition | Có thể có file `.par` tùy engine/phiên bản | Dictionary tables |
| Charset/collation mặc định database | File `db.opt` | Dictionary tables |
| Dictionary storage | Phân tán, có thành phần nontransactional | InnoDB |
| Crash safety của metadata | Phức tạp do nhiều nguồn lưu trữ | Transactional, crash-safe |
| DDL | Phải đồng bộ nhiều nguồn metadata | Có atomic DDL cho các thao tác được hỗ trợ |
| Truy vấn metadata | Một số giao diện phải tổng hợp từ nhiều nguồn | INFORMATION_SCHEMA tích hợp với data dictionary |
| Cache | Nhiều cơ chế cache theo từng lớp | Có Dictionary Object Cache tập trung |
| Quản lý file thủ công | Một số quy trình cũ phụ thuộc file metadata | Không quản lý định nghĩa bảng bằng file .frm |

Điểm quan trọng: MySQL 8.0 không loại bỏ mọi file trong data directory. Nó loại bỏ **các file dùng để lưu metadata theo kiến trúc cũ**. File dữ liệu và tablespace vẫn tồn tại theo storage engine.

## 5. Các file vẫn tồn tại sau khi loại bỏ .frm

Một nhầm lẫn phổ biến là cho rằng MySQL 8.0 không còn file vật lý cho bảng. Thực tế, data dictionary và data file có vai trò khác nhau.

| File hoặc loại file | Vai trò | Còn được sử dụng trong MySQL 8.0+? |
|---|---|---|
| `.ibd` | InnoDB file-per-table hoặc general tablespace | Có |
| `ibdata*` | InnoDB system tablespace, có thể chứa dữ liệu hệ thống và các cấu trúc InnoDB | Có |
| `.MYD` | Dữ liệu bảng MyISAM | Có nếu dùng MyISAM |
| `.MYI` | Index bảng MyISAM | Có nếu dùng MyISAM |
| Redo log | Ghi nhận thay đổi để phục hồi InnoDB | Có |
| Undo tablespace/log | Hỗ trợ MVCC và rollback | Có |
| `.frm` | Metadata định nghĩa bảng ở lớp server | Không còn từ MySQL 8.0 |
| `.TRG`, `.TRN` | Metadata trigger kiểu cũ | Không còn từ MySQL 8.0 |
| `db.opt` | Metadata charset/collation mặc định database kiểu cũ | Không còn từ MySQL 8.0 |

Một file `.ibd` có thể chứa dữ liệu, index và serialized dictionary information (SDI). Nó không phải một file `.frm` mới; cấu trúc, mục đích và cách sử dụng khác nhau.

## 6. Serialized Dictionary Information (SDI)

Từ MySQL 8.0.3, MySQL còn lưu metadata dưới dạng serialized dictionary information, viết tắt là **SDI**.

SDI là bản metadata được tuần tự hóa dưới định dạng JSON. Vai trò của nó là cung cấp một bản biểu diễn metadata bổ sung trong tablespace, hỗ trợ các thao tác như transportable tablespace và khôi phục thông tin đối tượng trong một số tình huống.

### 6.1. SDI được lưu ở đâu?

- InnoDB lưu SDI bên trong các file tablespace, chẳng hạn file-per-table `.ibd`, general tablespace, system tablespace và dictionary tablespace `mysql.ibd`.
- NDB lưu SDI trong NDB dictionary.
- Storage engine khác có thể lưu SDI thành file `.sdi` trong thư mục database.
- Với MyISAM, file `.sdi` có vai trò trong thao tác `IMPORT TABLE`.

SDI trong một InnoDB tablespace chỉ mô tả các table và tablespace object thuộc tablespace đó. Nó không phải bản sao đầy đủ của toàn bộ data dictionary trên server.

### 6.2. Trích xuất SDI bằng ibd2sdi

MySQL cung cấp công cụ `ibd2sdi` để trích xuất SDI từ file tablespace InnoDB.

Ví dụ:

~~~bash
ibd2sdi /var/lib/mysql/sales/orders.ibd
~~~

Lưu SDI ra file JSON:

~~~bash
ibd2sdi --dump-file=orders-sdi.json /var/lib/mysql/sales/orders.ibd
~~~

Đầu ra chứa các bản ghi JSON với thông tin định danh, loại đối tượng và dữ liệu metadata. Công cụ có thể đọc file tablespace khi server đang chạy hoặc offline, nhưng trong một số thời điểm liên quan tới DDL, rollback hoặc purge undo, việc đọc SDI có thể thất bại tạm thời.

Cần nhớ các giới hạn:

- `ibd2sdi` chỉ trích xuất metadata SDI; không khôi phục hàng dữ liệu.
- SDI chỉ mô tả các đối tượng thuộc tablespace đang đọc.
- Nó không thay thế backup đầy đủ, redo/undo recovery hoặc quy trình restore.
- Không chỉnh sửa file `.ibd` hoặc JSON SDI rồi đưa trở lại datadir như một cách thay đổi schema.
- Việc import tablespace cần tuân thủ quy trình InnoDB được hỗ trợ và điều kiện tương thích.

SDI là điểm khác biệt quan trọng: MySQL 8.0 không dùng `.frm` nhưng vẫn có thể lưu một bản biểu diễn metadata trong tablespace để phục vụ mục đích kỹ thuật cụ thể.

## 7. Đọc metadata đúng cách trong MySQL 8.0+

Thay vì đọc file nội bộ, hãy dùng giao diện SQL được hỗ trợ.

### 7.1. Xem định nghĩa bảng

~~~sql
SHOW CREATE TABLE sales.orders\G
~~~

Lệnh trả về DDL có thể dùng để hiểu cột, index, constraint, engine, charset và các tùy chọn của bảng.

### 7.2. Xem danh sách bảng và storage engine

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    TABLE_TYPE,
    ENGINE,
    TABLE_COLLATION
FROM information_schema.tables
WHERE TABLE_SCHEMA = 'sales'
ORDER BY TABLE_NAME;
~~~

### 7.3. Xem metadata cột

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ORDINAL_POSITION,
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    EXTRA
FROM information_schema.columns
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
~~~

### 7.4. Xem index

~~~sql
SELECT
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    COLLATION,
    CARDINALITY,
    INDEX_TYPE
FROM information_schema.statistics
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

### 7.5. Xem trigger

~~~sql
SHOW TRIGGERS FROM sales;
~~~

Hoặc:

~~~sql
SELECT
    TRIGGER_NAME,
    EVENT_MANIPULATION,
    EVENT_OBJECT_TABLE,
    ACTION_TIMING,
    ACTION_STATEMENT
FROM information_schema.triggers
WHERE TRIGGER_SCHEMA = 'sales'
ORDER BY EVENT_OBJECT_TABLE, TRIGGER_NAME;
~~~

### 7.6. Xem view, routine và event

~~~sql
SHOW CREATE VIEW sales.active_orders\G
SHOW CREATE PROCEDURE sales.recalculate_order_total\G
SHOW EVENTS FROM sales;
~~~

Khi xuất backup logic, cần nhớ routine và event phải được đưa vào dump bằng tùy chọn tương ứng như `--routines` và `--events`. Đừng giả định rằng dump toàn bộ database luôn tự động chứa mọi đối tượng theo cách giống nhau giữa các phiên bản.

## 8. Khác biệt vận hành khi nâng cấp từ phiên bản cũ

Việc chuyển từ MySQL 5.7 sang MySQL 8.0 không đơn thuần là thay binary. Server phải chuyển metadata từ kiến trúc cũ sang transactional data dictionary.

### 8.1. Quy trình nâng cấp có kiểm soát

Trước khi nâng cấp:

1. Đọc hướng dẫn nâng cấp chính thức cho phiên bản nguồn và phiên bản đích.
2. Kiểm tra phiên bản, hệ điều hành, cấu hình, plugin, storage engine và ứng dụng.
3. Kiểm tra tính tương thích của schema, trigger, routine, event và kiểu dữ liệu.
4. Kiểm tra orphan `.frm` files và các lỗi metadata được công cụ upgrade phát hiện.
5. Tạo backup nhất quán và thử restore vào môi trường riêng.
6. Chạy thử quy trình nâng cấp trên bản sao gần với production.
7. Lập kế hoạch downtime, giám sát và phương án xử lý nếu upgrade thất bại.

Ví dụ, tài liệu MySQL 8.4 đưa ra lệnh kiểm tra nâng cấp:

~~~bash
mysqlcheck -u root -p --all-databases --check-upgrade
~~~

Lệnh này cần tài khoản phù hợp và phải được dùng theo hướng dẫn của phiên bản đích. Nó giúp phát hiện một số vấn đề tương thích, nhưng không thay thế toàn bộ quy trình kiểm tra readiness.

### 8.2. Điều gì xảy ra khi server khởi động với phiên bản mới?

Trong quy trình nâng cấp được hỗ trợ, MySQL Server kiểm tra phiên bản data dictionary. Nếu cần nâng cấp, server tạo/cập nhật các bảng dictionary, chuyển metadata đã lưu sang định nghĩa mới và tái khởi tạo dictionary.

Khi hoàn tất, các file metadata kiểu cũ được loại bỏ theo quy trình nâng cấp. Ví dụ, sau khi nâng cấp thành công, bạn không còn thấy file `.frm` bên cạnh các bảng như ở MySQL 5.7.

Không tự xóa file metadata trước khi server thực hiện upgrade. Không copy riêng file `.frm` từ server cũ sang datadir MySQL 8.0. Không khởi động server mới với một datadir được ghép thủ công từ nhiều nguồn không nhất quán.

### 8.3. Có thể downgrade bằng cách khởi động binary cũ không?

Sau khi data dictionary đã được nâng cấp, không thể mặc định khởi động lại bằng binary phiên bản cũ. Định dạng và cấu trúc dictionary có thể đã thay đổi; việc downgrade tại chỗ không được hỗ trợ theo cách tùy tiện.

Nếu cần quay lại phiên bản cũ, phải có kế hoạch đã thử nghiệm, thường dựa trên backup trước nâng cấp hoặc logical dump/restore tương thích. Không xem việc giữ lại file `.frm` hoặc copy datadir cũ là phương án rollback.

### 8.4. Sao lưu không còn là copy riêng file metadata

Với MySQL 8.0+, backup phải bảo toàn data dictionary cùng dữ liệu và các cấu trúc engine liên quan. Hãy dùng công cụ backup được hỗ trợ:

- Logical backup như `mysqldump` hoặc MySQL Shell dump utilities.
- Physical backup tương thích với phiên bản và cấu hình server.
- Snapshot do nhà cung cấp managed database hỗ trợ, với điều kiện nhất quán được công bố.

Với `mysqldump`, cần chỉ định tùy chọn phù hợp để đưa stored routine và event vào dump, ví dụ `--routines` và `--events`. Sau khi backup, phải thử restore vào môi trường riêng và kiểm tra schema, dữ liệu, trigger, routine, event, quyền và ứng dụng.

## 9. Ví dụ điều tra: bảng còn file .ibd nhưng không có .frm

Giả sử bạn nhận một bản sao thư mục dữ liệu MySQL 8.0 và thấy:

~~~text
/var/lib/mysql/sales/
    orders.ibd
~~~

Bạn không thấy `orders.frm` và cho rằng file metadata đã bị thiếu.

Đây là kết luận sai nếu server thực sự dùng MySQL 8.0 trở lên. MySQL không còn dùng file `.frm` để lưu định nghĩa bảng. Metadata chính được quản lý trong transactional data dictionary. Với InnoDB, file `.ibd` còn chứa SDI của bảng và tablespace.

Cách điều tra đúng:

1. Xác định chính xác phiên bản server và data directory thuộc về phiên bản nào.
2. Nếu server đang hoạt động, dùng `SHOW CREATE TABLE sales.orders` và `INFORMATION_SCHEMA.TABLES` để kiểm tra bảng.
3. Nếu server không hoạt động và cần xem metadata trong tablespace, dùng `ibd2sdi` trên bản sao phù hợp của file `.ibd`.
4. Xác định đây có phải file-per-table tablespace hợp lệ, có đủ các file và cấu trúc cần thiết hay không.
5. Nếu mục tiêu là khôi phục bảng, làm theo quy trình backup/restore hoặc transportable tablespace được hỗ trợ cho đúng phiên bản.
6. Không tự tạo file `.frm`, đổi tên file hoặc chép file vào datadir để thử làm server nhận bảng.

Nếu đây là datadir MySQL 5.7 thì việc thiếu `.frm` có ý nghĩa khác và có thể là dấu hiệu metadata bị mất. Vì vậy, luôn xác định phiên bản trước khi kết luận.

## 10. Các hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| File .frm chứa toàn bộ dữ liệu bảng | .frm chứa định nghĩa metadata ở lớp server; dữ liệu và index nằm theo storage engine |
| MySQL 8.0 không còn file vật lý của bảng | File dữ liệu và tablespace như .ibd, ibdata*, .MYD, .MYI vẫn tồn tại |
| Mọi metadata cũ đều chỉ nằm trong .frm | Metadata được phân tán giữa file, system table và dictionary riêng của engine |
| InnoDB trước 8.0 không có dictionary riêng | InnoDB có internal data dictionary, song song với metadata ở lớp server |
| Có thể copy .frm sang MySQL 8.0 để phục hồi bảng | MySQL 8.0 không dùng .frm; dùng backup/restore hoặc quy trình tablespace được hỗ trợ |
| Có thể sửa trực tiếp dictionary table trong schema mysql | Dictionary tables được bảo vệ; dùng SHOW và INFORMATION_SCHEMA |
| SDI là file .frm mới | SDI là metadata JSON được lưu trong tablespace hoặc file .sdi tùy engine |
| ibd2sdi có thể phục hồi toàn bộ bảng | ibd2sdi chỉ trích xuất metadata SDI, không khôi phục hàng dữ liệu |
| Atomic DDL nghĩa là mọi DDL có thể rollback | Atomic DDL là cơ chế nguyên tử ở cấp server cho thao tác được hỗ trợ |
| Copy thư mục database khi server đang chạy là backup hợp lệ | Phải dùng phương thức backup nhất quán và được hỗ trợ |

## 11. Checklist khi làm việc với schema metadata

- [ ] Đã xác định phiên bản MySQL trước khi kiểm tra file metadata.
- [ ] Hiểu vai trò lịch sử của .frm, .TRG, .TRN, .par và db.opt.
- [ ] Phân biệt file metadata với file dữ liệu/index như .ibd, .MYD và .MYI.
- [ ] Hiểu metadata cũ được phân tán giữa server, system tables và storage engine.
- [ ] Biết transactional data dictionary xuất hiện từ MySQL 8.0.
- [ ] Không đọc hoặc sửa trực tiếp dictionary tables nội bộ.
- [ ] Dùng SHOW và INFORMATION_SCHEMA để kiểm tra schema.
- [ ] Hiểu vai trò của SDI và giới hạn của ibd2sdi.
- [ ] Có backup nhất quán trước khi nâng cấp.
- [ ] Đã kiểm tra orphan .frm và điều kiện tương thích khi nâng cấp từ bản cũ.
- [ ] Đã thử restore và xác minh routine, trigger, event, quyền cùng dữ liệu.
- [ ] Có phương án rollback dựa trên backup đã thử nghiệm.

## 12. Bài tập thực hành

### Bài 1: Khảo sát metadata của một bảng

Chọn một bảng trong database thực hành và chạy:

~~~sql
SHOW CREATE TABLE sales.orders\G

SELECT *
FROM information_schema.columns
WHERE table_schema = 'sales'
  AND table_name = 'orders'
ORDER BY ordinal_position;

SELECT *
FROM information_schema.statistics
WHERE table_schema = 'sales'
  AND table_name = 'orders'
ORDER BY index_name, seq_in_index;
~~~

Ghi lại cột, kiểu dữ liệu, index, engine và charset. Giải thích metadata khác dữ liệu hàng như thế nào.

### Bài 2: So sánh kiến trúc cũ và mới

Dựa vào tài liệu MySQL 5.7 và MySQL 8.4, lập bảng so sánh vai trò của:

- `.frm`
- `.TRG` và `.TRN`
- `db.opt`
- Dictionary nội bộ của InnoDB
- Transactional data dictionary

Giải thích vì sao file `.frm` không còn trong MySQL 8.0 nhưng file `.ibd` vẫn còn.

### Bài 3: Khảo sát SDI

Trên một máy MySQL 8.0+ có quyền truy cập file tablespace, dùng `ibd2sdi` để xuất metadata của một bảng InnoDB ra JSON. Đọc các thuộc tính tên bảng, cột, index và tablespace.

Chỉ thực hiện trên môi trường lab hoặc bản sao phù hợp. Không chỉnh sửa file tablespace.

### Bài 4: Chuẩn bị checklist nâng cấp

Giả lập kế hoạch chuyển một instance MySQL 5.7 sang 8.0. Liệt kê:

- Backup và thử restore.
- Kiểm tra orphan .frm.
- Kiểm tra trigger, routine, event và engine.
- Kiểm tra phiên bản ứng dụng và connector.
- Thời điểm chạy upgrade.
- Kiểm tra metadata và dữ liệu sau upgrade.
- Kế hoạch quay lại bằng backup nếu cần.

## 13. Kết luận

Trước MySQL 8.0, metadata được phân tán giữa file như `.frm`, `.TRG`, `.TRN`, `.par`, `db.opt`, các bảng hệ thống và dictionary riêng của storage engine. Cách tổ chức này khiến server phải duy trì tính nhất quán giữa nhiều nguồn lưu trữ.

MySQL 8.0 chuyển sang transactional data dictionary tập trung dựa trên InnoDB, hỗ trợ crash-safe metadata, atomic DDL và giao diện metadata thống nhất. Các file metadata cũ được loại bỏ, nhưng file dữ liệu và tablespace vẫn tồn tại. SDI cung cấp thêm bản metadata tuần tự hóa trong tablespace, hỗ trợ một số thao tác kỹ thuật và điều tra.

Khi quản trị, hãy xác định đúng phiên bản và storage engine, dùng `SHOW` và `INFORMATION_SCHEMA` để đọc metadata, dùng công cụ phù hợp để backup/restore và tuân thủ quy trình nâng cấp. Không thao tác file metadata nội bộ bằng tay hoặc coi việc thiếu `.frm` là lỗi trên MySQL 8.0+.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – MySQL Data Dictionary](https://dev.mysql.com/doc/refman/8.4/en/data-dictionary.html)
- [MySQL 8.4 Reference Manual – Removal of File-based Metadata Storage](https://dev.mysql.com/doc/refman/8.4/en/data-dictionary-file-removal.html)
- [MySQL 8.4 Reference Manual – Transactional Storage of Dictionary Data](https://dev.mysql.com/doc/refman/8.4/en/data-dictionary-transactional-storage.html)
- [MySQL 8.4 Reference Manual – Data Dictionary Schema](https://dev.mysql.com/doc/refman/8.4/en/data-dictionary-schema.html)
- [MySQL 8.4 Reference Manual – Serialized Dictionary Information (SDI)](https://dev.mysql.com/doc/refman/8.4/en/serialized-dictionary-information.html)
- [MySQL 8.4 Reference Manual – ibd2sdi utility](https://dev.mysql.com/doc/refman/8.4/en/ibd2sdi.html)
- [MySQL 8.4 Reference Manual – Data Dictionary Usage Differences](https://dev.mysql.com/doc/refman/8.4/en/data-dictionary-usage-differences.html)
- [MySQL 8.4 Reference Manual – Preparing Your Installation for Upgrade](https://dev.mysql.com/doc/refman/8.4/en/upgrade-prerequisites.html)
- [MySQL 8.4 Reference Manual – Upgrade Troubleshooting](https://dev.mysql.com/doc/refman/8.4/en/upgrade-troubleshooting.html)
- [MySQL 5.7 Reference Manual – File Locations](https://dev.mysql.com/doc/refman/5.7/en/data-directory.html)


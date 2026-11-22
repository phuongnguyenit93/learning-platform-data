# ALTER TABLE để thêm, đổi và xóa cột trong SQL

> **Chủ đề:** Database SQL → Bảng và lược đồ  
> **Trọng tâm:** Dùng **ALTER TABLE** để phát triển cấu trúc bảng đã tồn tại: **thêm cột**, **đổi tên cột**, **thay đổi định nghĩa cột** và **xóa cột**. Đồng thời hiểu những tác động lên dữ liệu, ràng buộc, câu truy vấn, ứng dụng và quá trình triển khai thực tế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **ALTER TABLE** thuộc nhóm lệnh DDL và phân biệt thay đổi cấu trúc với thay đổi dữ liệu bằng UPDATE.
- Thêm một hoặc nhiều cột và xác định tác động của **NULL**, **DEFAULT**, **NOT NULL** lên dữ liệu cũ và dữ liệu mới.
- Đổi tên cột bằng **RENAME COLUMN** hoặc cú pháp phù hợp với hệ quản trị đang dùng.
- Phân biệt **đổi tên cột** với **đổi kiểu dữ liệu, độ dài, khả năng NULL hoặc giá trị mặc định** của cột.
- Xóa cột và nhận biết nguy cơ mất dữ liệu, phụ thuộc khóa, chỉ mục, view, trigger, procedure và mã ứng dụng.
- Đọc và viết các biến thể ALTER TABLE thường gặp trên **PostgreSQL**, **MySQL**, **SQL Server**, **Oracle Database** và **SQLite**.
- Lập một quy trình migration có kiểm tra dữ liệu, phương án khôi phục và phối hợp giữa các phiên bản ứng dụng.

## 2. ALTER TABLE là gì?

Một bảng SQL có hai khía cạnh liên quan:

1. **Cấu trúc (schema):** danh sách cột, kiểu dữ liệu, khóa, ràng buộc, giá trị mặc định, chỉ mục và các thành phần phụ thuộc.
2. **Dữ liệu (data):** các dòng đang được lưu trong bảng.

Ví dụ, một bảng sản phẩm có thể gồm:

| Cột | Kiểu dự kiến | Ý nghĩa |
|---|---|---|
| **ma_san_pham** | Số nguyên | Khóa định danh sản phẩm |
| **ten_san_pham** | Chuỗi | Tên sản phẩm |
| **gia_ban** | Số thập phân | Giá bán hiện tại |
| **ghi_chu_cu** | Chuỗi | Ghi chú theo thiết kế cũ |

Một định nghĩa bảng minh họa:

~~~sql
CREATE TABLE san_pham (
    ma_san_pham INTEGER PRIMARY KEY,
    ten_san_pham VARCHAR(150) NOT NULL,
    gia_ban DECIMAL(12, 2) NOT NULL,
    ghi_chu_cu VARCHAR(500)
);
~~~

Cú pháp trên tương đối quen thuộc, nhưng tính khả chuyển của kiểu dữ liệu, ràng buộc và cách thay đổi bảng vẫn phụ thuộc DBMS.

Giả sử bảng có dữ liệu:

| ma_san_pham | ten_san_pham | gia_ban | ghi_chu_cu |
|---:|---|---:|---|
| 101 | Bàn phím cơ | 850000.00 | Lô cũ |
| 102 | Chuột không dây | 320000.00 | NULL |
| 103 | Màn hình | 4200000.00 | Kiểm tra bao bì |

Khi hệ thống phát triển, bạn muốn:

- Thêm **ma_sku** để tích hợp kho.
- Đổi tên **gia_ban** thành **don_gia** để thống nhất thuật ngữ.
- Mở rộng độ chính xác của cột tiền từ **DECIMAL(12,2)** thành **DECIMAL(14,2)**.
- Xóa **ghi_chu_cu** vì không còn sử dụng.

**ALTER TABLE** là lệnh DDL dùng để sửa định nghĩa của bảng đã tồn tại mà không cần viết lại toàn bộ lệnh CREATE TABLE từ đầu:

~~~sql
ALTER TABLE ten_bang
    thao_tac_thay_doi;
~~~

Cấu trúc cụ thể của **thao_tac_thay_doi** khác nhau theo DBMS.

### 2.1. So sánh ALTER TABLE và UPDATE

| Lệnh | Thay đổi điều gì? | Ví dụ |
|---|---|---|
| **ALTER TABLE** | Cấu trúc bảng, định nghĩa cột/ràng buộc | Thêm cột **ma_sku** |
| **UPDATE** | Giá trị trong những dòng đã có | Gán **ma_sku = 'SP-101'** cho một dòng |
| **INSERT** | Thêm dòng dữ liệu | Thêm một sản phẩm mới |
| **DELETE** | Xóa dòng dữ liệu | Xóa sản phẩm theo mã |
| **DROP TABLE** | Xóa toàn bộ bảng, gồm cấu trúc và dữ liệu | Xóa bảng **san_pham** |

Ví dụ hai thao tác có mục đích khác nhau:

~~~sql
-- Thêm cột vào cấu trúc.
ALTER TABLE san_pham
ADD COLUMN ma_sku VARCHAR(40);

-- Gán giá trị cho một dòng đã tồn tại.
UPDATE san_pham
SET ma_sku = 'SP-101'
WHERE ma_san_pham = 101;
~~~

Với các hệ hỗ trợ cú pháp **ADD COLUMN** như PostgreSQL, MySQL và SQLite, câu đầu thay đổi định nghĩa bảng; câu sau thay đổi dữ liệu. **SQL Server và Oracle có biến thể cú pháp ADD riêng** sẽ được trình bày ở phần sau.

### 2.2. Vì sao ALTER TABLE cần thận trọng?

Bảng đang tồn tại có thể được đọc/ghi đồng thời bởi ứng dụng. Một thay đổi cấu trúc có thể dẫn đến:

- Câu INSERT hoặc SELECT cũ không còn tương thích.
- Dữ liệu cũ không đáp ứng **NOT NULL**, **CHECK** hoặc kiểu dữ liệu mới.
- Ràng buộc khóa ngoại, chỉ mục, view hoặc trigger ngăn thay đổi.
- DDL phải chờ khóa; hoặc tự gây khóa làm giảm khả năng phục vụ.
- Hệ quản trị phải quét hoặc viết lại một bảng lớn.
- Xóa cột khiến dữ liệu gốc không còn truy xuất được từ bảng.
- Bản rollback triển khai ứng dụng không còn phù hợp với schema đã đổi.

Vì vậy, kỹ năng dùng ALTER TABLE gồm **biết câu lệnh** và **biết triển khai câu lệnh khi bảng có dữ liệu thật**.

## 3. Thêm cột bằng ADD COLUMN

### 3.1. Trường hợp cơ bản: thêm cột cho phép NULL

Ví dụ với PostgreSQL, MySQL và SQLite:

~~~sql
ALTER TABLE san_pham
ADD COLUMN ma_sku VARCHAR(40);
~~~

Mục đích: tạo cột **ma_sku** mới để lưu mã quản lý kho.

Sau khi thêm, về mặt kết quả truy vấn, các dòng hiện có sẽ có **ma_sku = NULL** nếu không được chỉ định giá trị khác bởi cơ chế mặc định hoặc chuyển đổi dữ liệu:

| ma_san_pham | ten_san_pham | ma_sku |
|---:|---|---|
| 101 | Bàn phím cơ | NULL |
| 102 | Chuột không dây | NULL |
| 103 | Màn hình | NULL |

Có thể điền dữ liệu sau khi thêm cột:

~~~sql
UPDATE san_pham
SET ma_sku = 'SP-101'
WHERE ma_san_pham = 101;

UPDATE san_pham
SET ma_sku = 'SP-102'
WHERE ma_san_pham = 102;
~~~

**Vì sao cột mới thường nên cho phép NULL ở giai đoạn đầu?** Vì những dòng cũ chưa có dữ liệu cho thuộc tính mới, và các phiên bản ứng dụng đang chạy có thể chưa biết cột đó. Thêm cột cho phép NULL thường giúp quá trình chuyển đổi diễn ra từng bước.

### 3.2. Thêm cột với DEFAULT

Nếu muốn mỗi sản phẩm mới có trạng thái mặc định là **ACTIVE**:

~~~sql
ALTER TABLE san_pham
ADD COLUMN trang_thai VARCHAR(20) DEFAULT 'ACTIVE';
~~~

**DEFAULT** là giá trị mặc định khi ứng dụng INSERT một dòng mà không cung cấp giá trị cho cột đó, trong những ngữ cảnh DBMS áp dụng default.

Ví dụ:

~~~sql
INSERT INTO san_pham (
    ma_san_pham, ten_san_pham, gia_ban
)
VALUES (
    104, 'Giá đỡ laptop', 250000.00
);
~~~

Khi cột **trang_thai** có default tương ứng, dòng mới được gán trạng thái **ACTIVE**. Việc biểu diễn giá trị mặc định ở **các dòng cũ** sau khi ADD có thể được DBMS xử lý bằng metadata hoặc bằng việc cập nhật/viết lại dữ liệu thực tế. Đừng suy từ kết quả SELECT rằng DBMS đã thực sự cập nhật vật lý từng dòng.

**DEFAULT không phải NOT NULL.** Trong nhiều DBMS, ứng dụng vẫn có thể chèn NULL tường minh vào cột có DEFAULT, nếu cột cho phép NULL:

~~~sql
-- Có thể tạo NULL tường minh khi cột cho phép NULL.
INSERT INTO san_pham (
    ma_san_pham, ten_san_pham, gia_ban, trang_thai
)
VALUES (
    105, 'Thảm bàn', 99000.00, NULL
);
~~~

Do đó, cần kết hợp NOT NULL nếu nghiệp vụ không cho phép thiếu giá trị.

### 3.3. Thêm cột NOT NULL

Trường hợp bảng đã có dòng dữ liệu, câu lệnh sau thường gặp vấn đề:

~~~sql
-- Có thể thất bại khi bảng đã có dữ liệu,
-- vì chưa có giá trị cho cột moi_bat_buoc.
ALTER TABLE san_pham
ADD COLUMN moi_bat_buoc VARCHAR(30) NOT NULL;
~~~

Vì sao? Mọi dòng của bảng phải có giá trị hợp lệ tại cột mới, nhưng trước đó các dòng không có thuộc tính này.

Có hai hướng triển khai tùy yêu cầu và DBMS.

**Hướng A — Có default đúng nghiệp vụ:**

~~~sql
-- Ví dụ cú pháp PostgreSQL/MySQL.
ALTER TABLE san_pham
ADD COLUMN nguon_hang VARCHAR(20)
NOT NULL DEFAULT 'CHUA_XAC_DINH';
~~~

Lựa chọn **CHUA_XAC_DINH** chỉ hợp lệ nếu đây là trạng thái nghiệp vụ cho phép. Không tự động chọn một giá trị “cho qua NOT NULL” khi nó khiến dữ liệu sai ý nghĩa.

**Hướng B — Thêm nullable, cập nhật dữ liệu, sau đó áp NOT NULL:**

~~~sql
-- Bước 1: thêm cột.
ALTER TABLE san_pham
ADD COLUMN ma_sku VARCHAR(40);

-- Bước 2: cập nhật dữ liệu cũ.
UPDATE san_pham
SET ma_sku = 'SP-' || CAST(ma_san_pham AS VARCHAR(20))
WHERE ma_sku IS NULL;

-- Bước 3: đặt NOT NULL (ví dụ PostgreSQL).
ALTER TABLE san_pham
ALTER COLUMN ma_sku SET NOT NULL;
~~~

Ví dụ trên dùng toán tử nối chuỗi **||** phổ biến ở PostgreSQL; MySQL mặc định thường dùng **CONCAT()** và SQL Server thường có cách ghép khác. Đây là một **kịch bản minh họa theo PostgreSQL**, không phải đoạn SQL nguyên vẹn chạy trên mọi DBMS.

Trước bước 3, cần bảo đảm **tất cả giá trị đã được cập nhật và ứng dụng không tiếp tục ghi NULL**. Nếu cập nhật từng đợt, phải xử lý xung đột với dữ liệu mới được chèn trong thời gian migration.

### 3.4. Thêm nhiều cột trong một thao tác

Khả năng thêm nhiều cột và cú pháp khác nhau:

~~~sql
-- PostgreSQL: nhiều ADD COLUMN trong một ALTER TABLE.
ALTER TABLE san_pham
ADD COLUMN chieu_dai_mm INTEGER,
ADD COLUMN chieu_rong_mm INTEGER;
~~~

~~~sql
-- MySQL: cú pháp ADD COLUMN lặp lại.
ALTER TABLE san_pham
ADD COLUMN chieu_dai_mm INT,
ADD COLUMN chieu_rong_mm INT;
~~~

~~~sql
-- SQL Server: một ADD, sau đó liệt kê các định nghĩa cột.
ALTER TABLE dbo.san_pham
ADD chieu_dai_mm INT NULL,
    chieu_rong_mm INT NULL;
~~~

~~~sql
-- Oracle Database: nhóm các cột trong dấu ngoặc.
ALTER TABLE san_pham
ADD (
    chieu_dai_mm NUMBER(10),
    chieu_rong_mm NUMBER(10)
);
~~~

SQLite hỗ trợ ADD COLUMN theo từng lệnh, nhưng không dùng cú pháp nhiều ADD COLUMN trong cùng một ALTER TABLE như PostgreSQL/MySQL. Nếu cần hai cột, thực hiện hai câu ALTER TABLE riêng biệt với điều kiện phù hợp.

Các ví dụ về **chieu_dai_mm**, **chieu_rong_mm** chỉ dùng để so sánh cách viết; không cần thực thi chúng nếu hệ thống không có thuộc tính kích thước.

## 4. Cú pháp ADD COLUMN theo hệ quản trị

| Hệ quản trị | Dạng thêm một cột phổ biến |
|---|---|
| **PostgreSQL** | **ALTER TABLE bang ADD COLUMN cot kieu;** |
| **MySQL** | **ALTER TABLE bang ADD COLUMN cot kieu;** |
| **SQL Server** | **ALTER TABLE bang ADD cot kieu NULL;** |
| **Oracle Database** | **ALTER TABLE bang ADD (cot kieu);** |
| **SQLite** | **ALTER TABLE bang ADD COLUMN cot kieu;** |

Ví dụ cùng yêu cầu: thêm cột **mo_ta** có thể để trống.

**PostgreSQL**

~~~sql
ALTER TABLE san_pham
ADD COLUMN mo_ta VARCHAR(500);
~~~

**MySQL**

~~~sql
ALTER TABLE san_pham
ADD COLUMN mo_ta VARCHAR(500) NULL;
~~~

**SQL Server**

~~~sql
ALTER TABLE dbo.san_pham
ADD mo_ta NVARCHAR(500) NULL;
~~~

**Oracle Database**

~~~sql
ALTER TABLE san_pham
ADD (mo_ta VARCHAR2(500));
~~~

**SQLite**

~~~sql
ALTER TABLE san_pham
ADD COLUMN mo_ta TEXT;
~~~

Nhìn bề ngoài, các lệnh đều thể hiện cùng thao tác. Nhưng phải kiểm tra kiểu dữ liệu (VARCHAR/VARCHAR2/NVARCHAR/TEXT), độ dài, Unicode, khả năng NULL, cấu hình và phiên bản DBMS.

### 4.1. Lưu ý riêng khi ADD COLUMN trên SQLite

SQLite có cách triển khai **ALTER TABLE** và hệ kiểu dữ liệu khác nhiều DBMS máy chủ. Khi ADD COLUMN, có một số hạn chế thường gặp:

- Không thêm cột mới với **PRIMARY KEY** hoặc **UNIQUE** trực tiếp trong định nghĩa ADD COLUMN.
- Cột mới có **NOT NULL** thường cần giá trị DEFAULT không NULL.
- Một số biểu thức DEFAULT, như **CURRENT_TIMESTAMP** hoặc biểu thức nằm trong ngoặc, không được dùng với ADD COLUMN như khi CREATE TABLE.
- Cột có ràng buộc **REFERENCES** có yêu cầu riêng liên quan default và trạng thái bật kiểm tra khóa ngoại.
- **CHECK**, cột generated và việc xác nhận dữ liệu hiện có chịu các giới hạn theo phiên bản.

Khi thiết kế thay đổi nằm ngoài những khả năng trực tiếp đó, SQLite thường cần **tạo bảng mới, chuyển dữ liệu rồi thay thế bảng cũ** theo quy trình migration được hỗ trợ chính thức.

## 5. Đổi tên cột: RENAME COLUMN

Đổi tên cột là thay **tên dùng để truy cập một thuộc tính**, trong khi mục tiêu thông thường là **giữ lại các giá trị đang lưu**.

Giả sử bảng có cột **gia_ban**, nhưng đội phát triển thống nhất tên mới là **don_gia**.

### 5.1. PostgreSQL

~~~sql
ALTER TABLE san_pham
RENAME COLUMN gia_ban TO don_gia;
~~~

### 5.2. MySQL

MySQL 8.0 trở lên có cú pháp:

~~~sql
ALTER TABLE san_pham
RENAME COLUMN gia_ban TO don_gia;
~~~

Các môi trường MySQL cũ hơn thường dùng **CHANGE COLUMN**, yêu cầu khai báo lại định nghĩa cột:

~~~sql
-- MySQL: khi dùng CHANGE COLUMN phải nêu cả kiểu cột.
ALTER TABLE san_pham
CHANGE COLUMN gia_ban don_gia DECIMAL(12, 2) NOT NULL;
~~~

**Rủi ro của CHANGE COLUMN:** nếu cột cũ còn có DEFAULT, COMMENT hoặc thuộc tính quan trọng khác, việc khai báo lại thiếu thông tin có thể vô tình đổi định nghĩa cột. Trước khi dùng, phải xem cấu trúc hiện tại và chép đúng những thuộc tính cần giữ.

### 5.3. Oracle Database

~~~sql
ALTER TABLE san_pham
RENAME COLUMN gia_ban TO don_gia;
~~~

Oracle hỗ trợ dạng RENAME COLUMN nhưng có các quy định về phụ thuộc vào cột và các đối tượng schema liên quan.

### 5.4. SQLite

Từ SQLite 3.25.0 có cú pháp:

~~~sql
ALTER TABLE san_pham
RENAME COLUMN gia_ban TO don_gia;
~~~

Các phiên bản hiện đại có thể tự cập nhật tham chiếu tên cột trong một số định nghĩa trigger, view và chỉ mục thuộc schema. Tuy nhiên, nếu việc đổi tên tạo nhập nhằng hoặc bị hạn chế do cấu trúc schema, lệnh có thể lỗi. Khả năng chuyển đổi tự động trong database **không cập nhật các chuỗi SQL trong mã ứng dụng**.

### 5.5. SQL Server

SQL Server thường dùng thủ tục hệ thống **sp_rename** để đổi tên cột:

~~~sql
EXEC sp_rename
    N'dbo.san_pham.gia_ban',
    N'don_gia',
    N'COLUMN';
~~~

Trong ví dụ:

- **dbo** là schema chứa bảng; thay bằng schema thực tế nếu khác.
- **san_pham.gia_ban** xác định cột cũ.
- **don_gia** là tên mới, không phải định nghĩa lại kiểu dữ liệu.
- **COLUMN** thông báo đối tượng cần đổi tên là cột.

**Không nên** áp dụng một câu **ALTER TABLE ... RENAME COLUMN** giống PostgreSQL lên SQL Server mà không kiểm tra: cú pháp đổi tên thông dụng là khác.

### 5.6. Kết quả sau khi đổi tên

Giả sử lệnh đổi tên thành công:

~~~sql
SELECT
    ma_san_pham,
    ten_san_pham,
    don_gia
FROM san_pham;
~~~

Các giá trị 850000.00, 320000.00, 4200000.00 vẫn là dữ liệu giá của sản phẩm. Tuy nhiên, truy vấn cũ:

~~~sql
SELECT gia_ban
FROM san_pham;
~~~

có thể lỗi vì tên **gia_ban** đã không còn là cột của bảng.

**Đổi tên cột thường giữ dữ liệu, nhưng không bảo đảm giữ tính tương thích của mọi câu SQL, view, stored procedure, ORM mapping, báo cáo và chương trình đọc dữ liệu.**

## 6. “Đổi cột” còn có thể nghĩa là đổi kiểu hoặc thuộc tính

Người học dễ nhầm hai thao tác:

| Nhu cầu | Thao tác | Ví dụ |
|---|---|---|
| Đổi **tên** | RENAME COLUMN / sp_rename / CHANGE COLUMN | gia_ban → don_gia |
| Đổi **kiểu dữ liệu** | ALTER COLUMN TYPE / MODIFY COLUMN / ALTER COLUMN / MODIFY | DECIMAL(12,2) → DECIMAL(14,2) |
| Đổi khả năng chứa NULL | SET/DROP NOT NULL hoặc định nghĩa lại cột | nullable → NOT NULL |
| Đổi giá trị mặc định | SET/DROP DEFAULT hoặc thay đổi constraint/default | DEFAULT 'DRAFT' → 'ACTIVE' |

Mặc dù đều là sửa cột, các thao tác không tương đương. Đổi kiểu có thể phải **kiểm tra hoặc chuyển đổi dữ liệu hiện có**; đổi tên chủ yếu ảnh hưởng các tham chiếu theo tên.

## 7. Đổi kiểu dữ liệu hoặc độ dài cột

Giả sử giá bán cần dải giá trị rộng hơn và yêu cầu vẫn giữ hai chữ số thập phân.

### 7.1. PostgreSQL: ALTER COLUMN ... TYPE

~~~sql
ALTER TABLE san_pham
ALTER COLUMN gia_ban TYPE NUMERIC(14, 2);
~~~

Nếu cần chuyển đổi dữ liệu bằng một biểu thức rõ ràng, PostgreSQL hỗ trợ **USING**:

~~~sql
-- Ví dụ giả định cot_gia_van_ban chứa chuỗi số hợp lệ.
ALTER TABLE san_pham
ALTER COLUMN cot_gia_van_ban TYPE NUMERIC(14, 2)
USING cot_gia_van_ban::NUMERIC(14, 2);
~~~

**USING** giúp mô tả cách chuyển từ dữ liệu cũ sang dữ liệu mới, nhưng sẽ lỗi nếu dữ liệu thực tế không chuyển được. Cần phát hiện và làm sạch giá trị sai định dạng trước migration.

### 7.2. MySQL: MODIFY COLUMN

~~~sql
ALTER TABLE san_pham
MODIFY COLUMN gia_ban DECIMAL(14, 2) NOT NULL;
~~~

**MODIFY COLUMN** nêu lại định nghĩa cột, do đó phải kiểm tra và giữ những thuộc tính cần thiết (NOT NULL, DEFAULT, COMMENT và các thuộc tính áp dụng khác). Không coi việc đổi precision là một thay thế văn bản chỉ gồm con số.

### 7.3. SQL Server: ALTER COLUMN

~~~sql
ALTER TABLE dbo.san_pham
ALTER COLUMN gia_ban DECIMAL(14, 2) NOT NULL;
~~~

Kiểu và tính nullable cần được chỉ định phù hợp với trạng thái mong muốn. Một số thuộc tính, ràng buộc và phụ thuộc có thể ngăn ALTER COLUMN trực tiếp; phải xử lý chúng theo quy trình an toàn.

### 7.4. Oracle Database: MODIFY

~~~sql
ALTER TABLE san_pham
MODIFY (gia_ban NUMBER(14, 2));
~~~

Trong Oracle, khả năng đổi kiểu hoặc thu hẹp độ dài trên cột đã có dữ liệu chịu các hạn chế quan trọng. Đừng suy rằng cứ tăng/giảm độ dài là không cần kiểm tra dữ liệu và phụ thuộc. Các kiểu như **VARCHAR2**, **NUMBER**, **DATE** có quy tắc riêng.

### 7.5. SQLite: thay kiểu bằng tái tạo bảng khi cần

SQLite không cung cấp cú pháp **ALTER COLUMN TYPE** trực tiếp theo kiểu PostgreSQL cho mọi trường hợp. Với thay đổi định nghĩa cột mà ALTER TABLE hỗ trợ hạn chế, thông thường cần:

1. Tạo bảng mới có schema mong muốn.
2. Chuyển đổi và chép dữ liệu từ bảng cũ.
3. Thay thế bảng cũ bằng bảng mới trong một quy trình có quản lý giao dịch/phụ thuộc.
4. Tạo lại các đối tượng liên quan và kiểm tra tính toàn vẹn.

SQLite có **type affinity** và mô hình lưu trữ động, nên việc đổi chuỗi khai báo kiểu không tự bảo đảm dữ liệu lưu trong cột mới đã được chuẩn hóa đúng kiểu.

### 7.6. Mở rộng và thu hẹp kiểu có mức rủi ro khác nhau

Một số ví dụ:

- **VARCHAR(50) → VARCHAR(200)** thường dễ hơn việc thu hẹp.
- **VARCHAR(200) → VARCHAR(50)** có thể bị từ chối nếu tồn tại chuỗi dài hơn 50 đơn vị độ dài theo quy tắc DBMS.
- **DECIMAL(12,2) → DECIMAL(14,2)** mở rộng độ chính xác.
- **DECIMAL(14,2) → DECIMAL(8,2)** có thể gây tràn giá trị hoặc lỗi chuyển đổi.
- **VARCHAR → INTEGER** yêu cầu mọi giá trị cần chuyển có dạng số hợp lệ theo DBMS.
- **TIMESTAMP → DATE** có thể làm mất phần thời gian và múi giờ liên quan.
- Chuyển kiểu số thực dấu phẩy động sang **DECIMAL** cần kiểm tra độ chính xác và quy tắc làm tròn.

Ví dụ kiểm tra trước khi thu hẹp độ dài:

~~~sql
-- Ví dụ minh họa: tìm chuỗi tên dài hơn 50 ký tự.
-- Hàm đo độ dài phụ thuộc phương ngữ.
SELECT ma_san_pham, ten_san_pham
FROM san_pham
WHERE CHAR_LENGTH(ten_san_pham) > 50;
~~~

PostgreSQL và MySQL hỗ trợ **CHAR_LENGTH**; SQL Server thường dùng **LEN** với quy tắc độ dài khác về khoảng trắng cuối; các DBMS khác cần đối chiếu kiểu và hàm tương ứng. Với Unicode và tên tiếng Việt, cần đặc biệt phân biệt chiều dài theo ký tự/byte.

## 8. Thay đổi NULL và DEFAULT sau khi đã thêm cột

### 8.1. Thêm ràng buộc NOT NULL sau khi điền dữ liệu

Một quy trình có thể là:

~~~sql
-- Ví dụ PostgreSQL.
ALTER TABLE san_pham
ADD COLUMN ma_sku VARCHAR(40);

UPDATE san_pham
SET ma_sku = 'SP-' || CAST(ma_san_pham AS VARCHAR(20))
WHERE ma_sku IS NULL;

ALTER TABLE san_pham
ALTER COLUMN ma_sku SET NOT NULL;
~~~

Ở bảng lớn, **UPDATE** theo toàn bảng có thể gây giao dịch dài, phát sinh WAL/redo log, áp lực khóa và làm chậm hệ thống. Phần cập nhật thường cần chia thành các đợt; tuy nhiên không nên tự động đưa cơ chế chia đợt vào ví dụ nếu chưa biết khóa, dữ liệu và khối lượng thực tế.

Cú pháp thay nullable:

| DBMS | Cách thường gặp |
|---|---|
| PostgreSQL | **ALTER COLUMN cot SET NOT NULL** hoặc **DROP NOT NULL** |
| MySQL | **MODIFY COLUMN cot kieu NOT NULL** hoặc **... NULL** |
| SQL Server | **ALTER COLUMN cot kieu NOT NULL** hoặc **... NULL** |
| Oracle | **MODIFY (cot NOT NULL)** hoặc thay định nghĩa phù hợp |
| SQLite | Thường phải dựng lại bảng khi cần đổi thuộc tính hiện có |

Đổi từ **nullable** sang **NOT NULL** là một thay đổi **siết ràng buộc**. DBMS phải xác nhận dữ liệu hiện có hợp lệ; nếu còn NULL, migration thường không thể hoàn tất.

### 8.2. Thay đổi giá trị mặc định

**PostgreSQL:**

~~~sql
ALTER TABLE san_pham
ALTER COLUMN trang_thai SET DEFAULT 'ACTIVE';
~~~

Bỏ giá trị mặc định:

~~~sql
ALTER TABLE san_pham
ALTER COLUMN trang_thai DROP DEFAULT;
~~~

**MySQL:** có dạng **ALTER COLUMN ... SET DEFAULT** hoặc **DROP DEFAULT** trong các phiên bản hỗ trợ, đồng thời có thể thay định nghĩa qua MODIFY COLUMN.

~~~sql
ALTER TABLE san_pham
ALTER COLUMN trang_thai SET DEFAULT 'ACTIVE';
~~~

**Oracle Database:** thường dùng MODIFY:

~~~sql
ALTER TABLE san_pham
MODIFY (trang_thai DEFAULT 'ACTIVE');
~~~

**SQL Server:** giá trị DEFAULT thường gắn với một **default constraint**; có thể phải xóa constraint hiện có trước khi tạo giá trị mới:

~~~sql
-- Khi chưa có default constraint khác trên cột:
ALTER TABLE dbo.san_pham
ADD CONSTRAINT DF_san_pham_trang_thai
DEFAULT 'ACTIVE' FOR trang_thai;
~~~

Ví dụ xóa constraint theo tên đã biết:

~~~sql
ALTER TABLE dbo.san_pham
DROP CONSTRAINT DF_san_pham_trang_thai;
~~~

Trong hệ thật, cần xác minh constraint tồn tại, tên hiện tại và các phụ thuộc trước khi sửa.

**SQLite:** không có cú pháp ALTER COLUMN SET DEFAULT thông dụng cho một cột hiện hữu; thường phải thay schema bằng quy trình tái tạo bảng.

**Đổi DEFAULT không tự động có nghĩa phải cập nhật toàn bộ dữ liệu đã tồn tại.** Nếu muốn dữ liệu cũ thay đổi, hãy viết câu **UPDATE** với phạm vi xác định.

## 9. Xóa cột bằng DROP COLUMN

### 9.1. Xóa một cột không còn sử dụng

Giả sử **ghi_chu_cu** đã được chuyển sang nơi lưu trữ khác hoặc không còn cần thiết.

~~~sql
ALTER TABLE san_pham
DROP COLUMN ghi_chu_cu;
~~~

Dạng **DROP COLUMN** được hỗ trợ trên nhiều DBMS như PostgreSQL, MySQL, SQL Server, Oracle Database và SQLite hiện đại, nhưng có khác biệt về điều kiện cho phép, khóa, phụ thuộc và khả năng thay đổi vật lý.

Sau khi xóa, truy vấn:

~~~sql
SELECT ghi_chu_cu
FROM san_pham;
~~~

sẽ không còn hợp lệ.

### 9.2. Hậu quả về dữ liệu

Xóa cột là một thao tác có thể dẫn đến **mất khả năng truy xuất dữ liệu gốc**, và tùy DBMS có thể loại bỏ dữ liệu vật lý ngay hoặc vào một giai đoạn nội bộ khác. Trong mọi trường hợp, ứng dụng không nên mặc định có thể lấy lại giá trị cũ bằng một lệnh ALTER TABLE ngược.

Nếu cần khôi phục cột:

~~~sql
ALTER TABLE san_pham
ADD COLUMN ghi_chu_cu VARCHAR(500);
~~~

lệnh này chỉ **tạo lại một cột cùng tên**; nó **không tự khôi phục** các giá trị “Lô cũ” hoặc “Kiểm tra bao bì” đã bị xóa khỏi cột trước. Muốn khôi phục dữ liệu cần nguồn đã lưu riêng hoặc cơ chế backup/restore phù hợp.

### 9.3. Các đối tượng phụ thuộc có thể ngăn DROP

Một cột có thể đang được dùng bởi:

- **PRIMARY KEY** hoặc **UNIQUE**.
- **FOREIGN KEY** trong cùng bảng hoặc từ bảng khác.
- **CHECK constraint**, **DEFAULT constraint**.
- **INDEX**, index biểu thức, generated/computed column.
- **VIEW**, **MATERIALIZED VIEW**, stored procedure, trigger.
- **PARTITION KEY**, các đặc tính vật lý hoặc cấu hình riêng của DBMS.
- Mã SQL, ORM mapping, báo cáo, job đồng bộ hoặc công cụ ETL bên ngoài cơ sở dữ liệu.

Đừng mặc định **DROP COLUMN** sẽ tự xóa mọi phụ thuộc. Tùy DBMS, lệnh có thể bị từ chối, yêu cầu xóa phụ thuộc trước hoặc hỗ trợ tùy chọn hành vi khác.

Ví dụ PostgreSQL có cơ chế **CASCADE** với DROP COLUMN:

~~~sql
-- Chỉ minh họa cú pháp: có thể xóa thêm đối tượng phụ thuộc.
ALTER TABLE san_pham
DROP COLUMN ghi_chu_cu CASCADE;
~~~

**CASCADE có thể làm biến mất thêm các đối tượng phụ thuộc**, nên không dùng như cách sửa lỗi tự động. Cần xác định chính xác các phụ thuộc và hậu quả trước khi cho phép thay đổi.

### 9.4. SQLite và DROP COLUMN

SQLite hỗ trợ **DROP COLUMN** từ phiên bản **3.35.0**, với những điều kiện hạn chế. Cột không thể được xóa trực tiếp nếu nó được sử dụng bởi các cấu trúc như khóa chính, ràng buộc UNIQUE, chỉ mục, khóa ngoại, biểu thức CHECK, generated column, trigger hoặc view theo các quy tắc phụ thuộc cụ thể.

Nếu DROP COLUMN không thể hoàn thành, phải thiết kế lại bảng và các đối tượng liên quan theo quy trình migration chính thức của SQLite.

### 9.5. Trình tự xóa cột an toàn

Trong hệ thống có nhiều phiên bản ứng dụng cùng hoạt động, cách an toàn thường gồm:

1. **Ngừng tham chiếu cột** trong mã đọc, ghi, báo cáo và các job liên quan.
2. **Triển khai phiên bản ứng dụng** không còn phụ thuộc cột đó.
3. **Quan sát thực tế** để bảo đảm các dịch vụ/job cũ đã kết thúc hoặc chuyển đổi.
4. **Sao lưu dữ liệu cần giữ** và có kế hoạch khôi phục.
5. **Kiểm tra phụ thuộc trong DBMS** và xác định thời gian/kiểu khóa có thể xảy ra.
6. **Thực thi DROP COLUMN** bằng migration kiểm soát được.
7. **Kiểm tra sau thay đổi**: truy vấn nghiệp vụ, ràng buộc, dữ liệu còn lại và tình trạng ứng dụng.

Với cột quan trọng hoặc dữ liệu lớn, cần lên lịch triển khai phù hợp và giữ kế hoạch phục hồi trước khi thực thi.

## 10. Bảng so sánh ADD, RENAME, MODIFY, DROP theo DBMS

| Tác vụ | PostgreSQL | MySQL | SQL Server | Oracle | SQLite |
|---|---|---|---|---|---|
| Thêm cột | **ADD COLUMN** | **ADD COLUMN** | **ADD** | **ADD (cot kieu)** | **ADD COLUMN** |
| Đổi tên cột | **RENAME COLUMN ... TO** | **RENAME COLUMN ... TO** ở bản hiện đại; hoặc **CHANGE COLUMN** | **sp_rename** | **RENAME COLUMN ... TO** | **RENAME COLUMN ... TO** từ 3.25.0 |
| Đổi kiểu dữ liệu | **ALTER COLUMN ... TYPE** | **MODIFY COLUMN** hoặc **CHANGE COLUMN** | **ALTER COLUMN** | **MODIFY (...)** | Thường tái tạo bảng |
| Đổi NULL/NOT NULL | **ALTER COLUMN SET/DROP NOT NULL** | **MODIFY COLUMN** | **ALTER COLUMN** | **MODIFY (...)** | Thường tái tạo bảng |
| Đổi DEFAULT | **ALTER COLUMN SET/DROP DEFAULT** | **ALTER COLUMN SET/DROP DEFAULT** hoặc **MODIFY** | Thường thông qua DEFAULT constraint | **MODIFY (... DEFAULT ...)** | Thường tái tạo bảng |
| Xóa cột | **DROP COLUMN** | **DROP COLUMN** | **DROP COLUMN** | **DROP COLUMN** | **DROP COLUMN** từ 3.35.0 |

**Lưu ý:** bảng mô tả những cách viết phổ biến; tính năng và khả năng sử dụng còn phụ thuộc **phiên bản, loại bảng, dữ liệu hiện có, index/constraint, engine lưu trữ và cấu hình**. Từ khóa giống nhau không bảo đảm cùng mức khóa, thời gian chạy hoặc hành vi giao dịch.

## 11. Kịch bản tổng hợp: phát triển bảng sản phẩm trên PostgreSQL

Phần này dùng **PostgreSQL** làm môi trường ví dụ để các lệnh tạo thành một quy trình nhất quán. Không áp dụng nguyên văn sang mọi DBMS.

### 11.1. Trạng thái đầu

~~~sql
CREATE TABLE san_pham (
    ma_san_pham INTEGER PRIMARY KEY,
    ten_san_pham VARCHAR(150) NOT NULL,
    gia_ban NUMERIC(12, 2) NOT NULL,
    ghi_chu_cu VARCHAR(500)
);
~~~

Dữ liệu:

~~~sql
INSERT INTO san_pham (
    ma_san_pham, ten_san_pham, gia_ban, ghi_chu_cu
)
VALUES
    (101, 'Bàn phím cơ', 850000.00, 'Lô cũ'),
    (102, 'Chuột không dây', 320000.00, NULL),
    (103, 'Màn hình', 4200000.00, 'Kiểm tra bao bì');
~~~

### 11.2. Bước 1 — Thêm mã SKU nullable

~~~sql
ALTER TABLE san_pham
ADD COLUMN ma_sku VARCHAR(40);
~~~

Mục đích: thay đổi cấu trúc mà chưa bắt dữ liệu cũ phải lập tức có SKU.

### 11.3. Bước 2 — Điền mã SKU cho dữ liệu cũ

~~~sql
UPDATE san_pham
SET ma_sku = 'SP-' || CAST(ma_san_pham AS VARCHAR(20))
WHERE ma_sku IS NULL;
~~~

Theo dữ liệu minh họa, ba sản phẩm có SKU **SP-101**, **SP-102**, **SP-103**.

**Giả định cần hiểu:** cách sinh mã từ ma_san_pham chỉ là quy tắc ví dụ; nếu doanh nghiệp có quy chuẩn SKU khác thì phải dùng quy tắc thật, kiểm tra trùng và không đoán mã tùy tiện.

### 11.4. Bước 3 — Siết NOT NULL

Sau khi đã kiểm tra mọi dòng có SKU và mọi đường ghi dữ liệu mới đều gán SKU:

~~~sql
ALTER TABLE san_pham
ALTER COLUMN ma_sku SET NOT NULL;
~~~

Lệnh có thể phải quét bảng hoặc xác minh ràng buộc. Với bảng lớn, cần đánh giá ảnh hưởng khóa và chi phí thực thi.

### 11.5. Bước 4 — Mở rộng kiểu tiền

~~~sql
ALTER TABLE san_pham
ALTER COLUMN gia_ban TYPE NUMERIC(14, 2);
~~~

Mục đích: cho phép số tiền lớn hơn trong tương lai. Tác động vật lý và việc cần viết lại bảng tùy từng kiểu chuyển đổi và phiên bản PostgreSQL.

### 11.6. Bước 5 — Đổi tên cột giá

~~~sql
ALTER TABLE san_pham
RENAME COLUMN gia_ban TO don_gia;
~~~

Từ lúc đổi tên, ứng dụng phải truy cập cột bằng **don_gia** hoặc qua một lớp tương thích đã chuẩn bị. Không nên thực hiện ngay khi còn phiên bản ứng dụng cũ chỉ biết **gia_ban**.

### 11.7. Bước 6 — Xóa ghi chú cũ khi không còn phụ thuộc

~~~sql
ALTER TABLE san_pham
DROP COLUMN ghi_chu_cu;
~~~

**Chỉ thực hiện khi** dữ liệu cột ghi_chu_cu không cần giữ ở bảng hiện tại, đã đáp ứng yêu cầu lưu trữ và không còn ứng dụng/phụ thuộc sử dụng.

### 11.8. Trạng thái cấu trúc dự kiến

| Cột | Kiểu dự kiến | Thuộc tính |
|---|---|---|
| **ma_san_pham** | INTEGER | PRIMARY KEY |
| **ten_san_pham** | VARCHAR(150) | NOT NULL |
| **don_gia** | NUMERIC(14,2) | NOT NULL |
| **ma_sku** | VARCHAR(40) | NOT NULL |

Truy vấn phù hợp cấu trúc mới:

~~~sql
SELECT
    ma_san_pham,
    ten_san_pham,
    ma_sku,
    don_gia
FROM san_pham
ORDER BY ma_san_pham;
~~~

Kịch bản trên mang tính học tập trên bảng nhỏ. Với ứng dụng sản xuất đang hoạt động, **thêm cột**, **điền dữ liệu**, **đổi code**, **đổi tên** và **xóa cột** thường cần được tách thành các lần triển khai có kiểm soát.

## 12. Vấn đề lớn nhất: sự tương thích giữa ứng dụng cũ và schema mới

Giả sử hệ thống có hai phiên bản ứng dụng:

- **Phiên bản A** đang truy vấn **SELECT gia_ban FROM san_pham**.
- **Phiên bản B** dùng tên **don_gia**.

Nếu đổi trực tiếp **gia_ban → don_gia** trong database khi A vẫn đang chạy, A có thể lỗi ngay. Một migration schema thành công về mặt cú pháp chưa đủ chứng minh triển khai hệ thống thành công.

### 12.1. Mẫu triển khai Expand → Migrate → Contract

Một phương án có thể dùng khi đổi tên cột trong hệ thống không thể cập nhật đồng thời mọi thành phần:

**Expand — mở rộng schema:**

~~~sql
-- Ví dụ PostgreSQL; cho phép tồn tại cả cột cũ và mới.
ALTER TABLE san_pham
ADD COLUMN don_gia NUMERIC(14, 2);
~~~

Lúc này **gia_ban** vẫn tồn tại nên ứng dụng cũ có thể tiếp tục dùng.

**Migrate — chuyển dữ liệu và mã ứng dụng:**

~~~sql
UPDATE san_pham
SET don_gia = gia_ban
WHERE don_gia IS NULL;
~~~

Ứng dụng mới bắt đầu đọc **don_gia** khi đã có dữ liệu hợp lệ. Trong giai đoạn chuyển tiếp, cần một cơ chế được thiết kế để **duy trì nhất quán giữa hai cột** nếu có ghi mới hoặc cập nhật giá: ví dụ cập nhật hai cột trong cùng giao dịch, dùng lớp tương thích, hoặc cơ chế đồng bộ phù hợp DBMS.

**Contract — thu gọn schema:**

Sau khi tất cả dịch vụ đã đọc/ghi cột mới và kiểm tra dữ liệu khớp, cân nhắc:

~~~sql
ALTER TABLE san_pham
ALTER COLUMN don_gia SET NOT NULL;

-- Chỉ khi không còn phụ thuộc.
ALTER TABLE san_pham
DROP COLUMN gia_ban;
~~~

**Ưu điểm:** các phiên bản ứng dụng có thể chuyển đổi dần.  
**Đánh đổi:** trong giai đoạn song song, hệ thống cần quản lý việc ghi hai cột để tránh dữ liệu lệch nhau.

### 12.2. Không đồng nhất RENAME với “thêm cột mới rồi xóa cột cũ”

**RENAME COLUMN** đổi tên một cột hiện có; mục đích thường là giữ nguyên dữ liệu và các thuộc tính của nó.

**ADD cột mới → UPDATE → DROP cột cũ** tạo một cột khác với định nghĩa mới. Quy trình này có thể hữu ích để đảm bảo tương thích phiên bản hoặc đổi kiểu phức tạp, nhưng cũng yêu cầu chuyển các thuộc tính như:

- NOT NULL và DEFAULT.
- UNIQUE, CHECK, FOREIGN KEY.
- Chỉ mục và các cột tham gia chỉ mục.
- Quyền truy cập cột, thống kê, comment, collation.
- Trigger, view, biểu thức computed/generated.
- Logic ghi đồng thời và thời gian dữ liệu đang chuyển tiếp.

Không được giả định cột mới kế thừa mọi thuộc tính của cột cũ.

## 13. DDL trong giao dịch: không có một quy tắc chung cho mọi DBMS

Một phản xạ thường gặp là bọc mọi lệnh ALTER TABLE giữa **BEGIN** và **ROLLBACK**, giả định khi có lỗi sẽ hoàn tác mọi thay đổi.

Thực tế:

- **PostgreSQL** cho phép nhiều thao tác DDL thông thường trong giao dịch và có thể rollback, nhưng một số lệnh đặc biệt không được phép chạy trong transaction block.
- **MySQL** có cơ chế implicit commit đối với nhiều câu DDL, dù một số thao tác hỗ trợ **atomic DDL** theo nghĩa riêng của hệ thống; không đồng nhất atomic DDL với khả năng ứng dụng tự ROLLBACK toàn bộ chuỗi migration.
- **Oracle Database** thông thường implicit commit quanh DDL; không thể coi nhiều lệnh ALTER TABLE là một transaction do ứng dụng điều khiển giống PostgreSQL.
- **SQL Server** cho phép nhiều DDL trong transaction tường minh nhưng có các ràng buộc/ngoại lệ và tác động khóa, phiên bản.
- **SQLite** hỗ trợ thay đổi schema trong giao dịch theo cách của SQLite; tuy nhiên giới hạn cú pháp ALTER TABLE vẫn tồn tại.

Vì vậy, tính năng **rollback migration** phải được đánh giá trên đúng DBMS. Một file SQL có câu lệnh “DOWN” để thêm lại cột sau DROP **không tự khôi phục dữ liệu** đã mất.

### 13.1. Đừng nhầm atomic và online

Hai khái niệm khác nhau:

- **Atomic:** thao tác thành công hoàn toàn hoặc thất bại mà không để schema ở trạng thái hoàn thành một phần theo cơ chế được hỗ trợ.
- **Online:** các hoạt động đọc/ghi khác vẫn tiếp tục được với mức gián đoạn cho phép.

Một ALTER TABLE có thể atomic nhưng vẫn cần khóa mạnh, chờ giao dịch khác hoặc khiến ứng dụng bị chậm. Ngược lại, khả năng thực hiện online có điều kiện theo loại thay đổi, engine, phiên bản và cấu hình.

### 13.2. Khóa và thời gian chạy

Một số thay đổi chỉ cập nhật metadata; số khác phải quét bảng, xác minh ràng buộc hoặc viết lại dữ liệu. Với bảng lớn, ảnh hưởng có thể gồm:

- Chờ khóa schema hoặc khóa đối tượng.
- Chặn các truy vấn đọc/ghi trong một khoảng thời gian.
- Tăng sử dụng CPU, I/O, log và dung lượng lưu trữ tạm.
- Làm chậm replication hoặc đồng bộ sang hệ thống khác.
- Gây lỗi timeout hoặc vượt thời gian cho phép của ứng dụng.

**Không suy từ tên lệnh ALTER TABLE rằng thao tác luôn “nhanh” hoặc “không khóa”.** Cần tham khảo tài liệu online DDL/locking theo DBMS và đo thử với dữ liệu quy mô tương đương.

## 14. Quản lý migration bằng phiên bản

Trong dự án lớn, schema thường được quản lý như mã nguồn thông qua các file migration và công cụ như **Flyway** hoặc **Liquibase**; hoặc cơ chế tương ứng trong framework.

Ví dụ một lộ trình:

~~~text
V001__create_san_pham.sql
V002__add_ma_sku_nullable.sql
V003__backfill_ma_sku.sql
V004__require_ma_sku.sql
V005__add_don_gia.sql
V006__backfill_don_gia.sql
V007__remove_gia_ban_after_cutover.sql
~~~

Tên file chỉ là minh họa: cú pháp tên, thứ tự và cơ chế chạy thực tế phụ thuộc công cụ.

### 14.1. Migration thuận và khả năng khôi phục

**Up migration** là thay đổi theo hướng schema mới; **down migration** nếu có là kịch bản đi ngược. Nhưng không phải thao tác nào cũng đảo ngược được đầy đủ.

| Thao tác | Có thể đảo lại cấu trúc? | Dữ liệu có bảo toàn tự động không? |
|---|---|---|
| ADD COLUMN | Có thể DROP COLUMN | Giá trị ghi vào cột mới sẽ mất nếu drop |
| RENAME COLUMN | Có thể đổi tên ngược | Thường giữ giá trị, nhưng phụ thuộc ứng dụng/schema |
| Mở rộng VARCHAR | Có thể thử thu hẹp | Không nếu dữ liệu mới vượt giới hạn cũ |
| Đổi kiểu số/chuỗi | Có thể cần chuyển ngược | Không bảo đảm chuyển đổi không mất mát |
| DROP COLUMN | Có thể ADD lại tên cột | Không; giá trị cũ cần backup hoặc bản sao |

Một bản rollback đúng cần xem xét **dữ liệu**, **ứng dụng đã triển khai**, **đối tượng phụ thuộc** và **tính tương thích phiên bản**, thay vì chỉ đảo thứ tự các câu ALTER TABLE.

### 14.2. Vì sao không nên dùng ALTER TABLE thủ công trên mỗi môi trường?

Nếu lập trình viên trực tiếp sửa schema ở môi trường phát triển nhưng không ghi migration, môi trường kiểm thử hoặc production có thể khác cấu trúc. Điều này dẫn đến lỗi “máy của tôi chạy được”.

Quản lý schema bằng migration giúp:

- Mô tả ai thay đổi gì và vì sao.
- Áp dụng cùng một chuỗi thay đổi theo thứ tự.
- Kiểm tra trên môi trường staging.
- Phát hiện khác biệt schema và lỗi triển khai.
- Phối hợp thay đổi database với bản phát hành ứng dụng.

Tuy vậy, công cụ migration không tự bảo đảm an toàn: nội dung câu SQL, dữ liệu thật và thứ tự triển khai vẫn phải được thiết kế đúng.

## 15. Kiểm tra trước và sau khi ALTER TABLE

### 15.1. Xem định nghĩa hiện tại

Không đoán kiểu cột từ tên cột. Hãy xem schema thực tế qua catalog, công cụ quản trị hoặc lệnh tương ứng.

Ví dụ:

~~~sql
-- PostgreSQL: truy vấn metadata thông qua information_schema.
SELECT
    column_name,
    data_type,
    character_maximum_length,
    numeric_precision,
    numeric_scale,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'san_pham'
ORDER BY ordinal_position;
~~~

Trên các DBMS khác, **INFORMATION_SCHEMA** hoặc catalog hệ thống có cấu trúc và mức đầy đủ khác nhau. Oracle thường có **USER_TAB_COLUMNS**/**ALL_TAB_COLUMNS**; SQLite có **PRAGMA table_info(...)** và các lệnh liên quan; SQL Server có catalog **sys.columns**, **sys.types**, **sys.default_constraints**. Chỉ dùng lệnh phù hợp DBMS mục tiêu.

### 15.2. Kiểm tra dữ liệu trước khi siết NOT NULL

~~~sql
SELECT COUNT(*) AS so_dong_thieu_sku
FROM san_pham
WHERE ma_sku IS NULL;
~~~

Nếu kết quả khác 0, cần giải quyết dữ liệu thiếu trước khi áp NOT NULL.

### 15.3. Kiểm tra giá trị trước khi thu hẹp kiểu

Ví dụ nếu muốn giảm cột giá từ dải lớn xuống nhỏ:

~~~sql
SELECT
    MIN(gia_ban) AS gia_nho_nhat,
    MAX(gia_ban) AS gia_lon_nhat,
    COUNT(*) AS so_dong
FROM san_pham;
~~~

Mục tiêu: hiểu biên giá trị thực tế trước khi thay precision/scale. Khi đổi kiểu chuỗi sang số, cần kiểm tra cả giá trị không hợp lệ, định dạng thập phân, dấu phân cách và chuỗi trống.

### 15.4. Kiểm tra đối tượng phụ thuộc

Trước khi RENAME/DROP/ALTER COLUMN, kiểm tra:

- Khóa chính, khóa ngoại, UNIQUE, CHECK, DEFAULT.
- Index và các biểu thức index.
- View, trigger, procedure, function, generated column.
- Câu SQL động trong ứng dụng, hệ báo cáo, ETL, job định kỳ.
- Quyền truy cập cột hoặc chính sách bảo mật theo cột (nếu có).
- Cơ chế replication, CDC và bộ đọc schema (nếu áp dụng).

**Đặc biệt:** một số tham chiếu tên cột nằm trong chuỗi SQL của mã ứng dụng, không xuất hiện như dependency nội bộ của database. Catalog không thể tìm hết mọi nơi cần sửa.

### 15.5. Kiểm tra sau migration

Sau khi thay đổi thành công:

~~~sql
-- Ví dụ sau giai đoạn thêm SKU và đổi gia_ban thành don_gia.
SELECT
    ma_san_pham,
    ten_san_pham,
    ma_sku,
    don_gia
FROM san_pham
ORDER BY ma_san_pham;
~~~

Xác nhận:

1. Danh sách cột và kiểu dữ liệu đúng yêu cầu.
2. Số dòng không thay đổi ngoài ý định.
3. Dữ liệu cột cũ còn lại đúng, dữ liệu cột mới được điền theo quy tắc.
4. Ràng buộc NOT NULL/UNIQUE/CHECK/FK thực sự hoạt động.
5. Ứng dụng có thể đọc/ghi với schema mới.
6. Không còn job hoặc mã cũ truy cập cột đã đổi/xóa.
7. Thời gian truy vấn và mức khóa vẫn nằm trong giới hạn chấp nhận.

## 16. Những lỗi phổ biến

### 16.1. Thêm cột bắt buộc khi chưa biết điền dữ liệu cũ

~~~sql
-- Có thể lỗi trên bảng đã có dữ liệu.
ALTER TABLE san_pham
ADD COLUMN phan_loai VARCHAR(20) NOT NULL;
~~~

**Nguyên nhân:** dòng cũ không có giá trị.  
**Cách xử lý:** có default đúng nghiệp vụ hoặc thêm nullable → điền dữ liệu → siết NOT NULL.

### 16.2. Nhầm DEFAULT với việc sửa mọi dòng cũ

~~~sql
ALTER TABLE san_pham
ADD COLUMN trang_thai VARCHAR(20) DEFAULT 'ACTIVE';
~~~

Không được kết luận rằng lệnh đã thực thi một UPDATE vật lý trên mọi dòng cũ. DBMS có thể tối ưu cách lưu trữ, và ngữ nghĩa đối với dữ liệu có sẵn cần được xác minh theo phiên bản. Nếu yêu cầu thay đổi trạng thái dữ liệu cũ theo điều kiện nghiệp vụ, hãy có bước UPDATE tường minh.

### 16.3. Đổi tên cột ngay khi ứng dụng vẫn dùng tên cũ

~~~sql
ALTER TABLE san_pham
RENAME COLUMN gia_ban TO don_gia;
~~~

Lệnh có thể thành công nhưng API hoặc báo cáo vẫn gửi **SELECT gia_ban** và phát sinh lỗi. Cần kiểm soát phiên bản ứng dụng hoặc dùng chiến lược chuyển tiếp nhiều giai đoạn.

### 16.4. Đổi kiểu mà không kiểm tra dữ liệu

~~~sql
-- Ví dụ có thể lỗi hoặc mất tính chính xác.
ALTER TABLE san_pham
ALTER COLUMN gia_ban TYPE NUMERIC(8, 2);
~~~

Với giá trị lớn vượt phạm vi cho phép, thao tác có thể bị từ chối. Việc đổi precision/scale có thể làm tròn hoặc thay đổi số liệu theo quy tắc DBMS. Phải xác minh dữ liệu và yêu cầu nghiệp vụ trước.

### 16.5. Xóa cột để sửa lỗi phụ thuộc

~~~sql
-- Không dùng CASCADE theo phản xạ.
ALTER TABLE san_pham
DROP COLUMN ghi_chu_cu CASCADE;
~~~

CASCADE có thể ảnh hưởng nhiều đối tượng. Nếu DROP không thể thực thi vì cột có phụ thuộc, hãy tìm và xử lý những phụ thuộc đó có chủ đích.

### 16.6. Tưởng thêm lại cột là khôi phục dữ liệu

~~~sql
ALTER TABLE san_pham DROP COLUMN ghi_chu_cu;
ALTER TABLE san_pham ADD COLUMN ghi_chu_cu VARCHAR(500);
~~~

Hai câu lệnh có thể khiến schema cuối có cột cùng tên, nhưng **dữ liệu ghi_chu_cu gốc đã không còn trong cột vừa thêm lại**.

### 16.7. Bỏ qua sự khác nhau về cú pháp

~~~sql
-- Không áp dụng nguyên văn câu này cho mọi DBMS.
ALTER TABLE san_pham
ALTER COLUMN gia_ban TYPE NUMERIC(14, 2);
~~~

Đây là cú pháp PostgreSQL. Với MySQL thường cần **MODIFY COLUMN**; SQL Server dùng **ALTER COLUMN** nhưng không có TYPE ở vị trí tương tự; Oracle dùng **MODIFY**; SQLite có hạn chế thay đổi kiểu trực tiếp.

### 16.8. Cho rằng ALTER TABLE trên bảng lớn luôn nhanh

Ngay cả khi cú pháp đơn giản, thay đổi có thể khóa bảng hoặc đòi quét/viết lại nhiều dữ liệu. Trước khi triển khai cần đánh giá thời gian thực tế, phiên bản DBMS và cơ chế online DDL tương ứng.

### 16.9. Không tính đến thao tác đồng thời khi backfill

Trong lúc **UPDATE** điền cột mới, một dịch vụ khác có thể chèn bản ghi thiếu giá trị hoặc cập nhật cột cũ. Nếu không phối hợp các đường ghi, khi siết NOT NULL hoặc chuyển ứng dụng sang cột mới có thể xảy ra lỗi hoặc sai lệch dữ liệu.

## 17. Bài tập thực hành

Các bài dưới đây sử dụng bảng **san_pham** có cấu trúc ban đầu:

~~~sql
CREATE TABLE san_pham (
    ma_san_pham INTEGER PRIMARY KEY,
    ten_san_pham VARCHAR(150) NOT NULL,
    gia_ban DECIMAL(12, 2) NOT NULL,
    ghi_chu_cu VARCHAR(500)
);
~~~

Trừ khi đề bài nói khác, hãy viết theo cú pháp **PostgreSQL** để có thể so sánh các câu lệnh trong một phương ngữ nhất quán.

### Bài 1 — Thêm cột cho phép NULL

Hãy thêm cột **nha_san_xuat** với kiểu VARCHAR(100), chấp nhận NULL.

<details>
<summary>Gợi ý đáp án</summary>

~~~sql
ALTER TABLE san_pham
ADD COLUMN nha_san_xuat VARCHAR(100);
~~~

Các dòng hiện có chưa có dữ liệu nhà sản xuất nên có thể đọc thành NULL.

</details>

### Bài 2 — Thêm cột với DEFAULT và NOT NULL

Hãy thêm cột **dang_ban** để đánh dấu sản phẩm còn bán, sử dụng kiểu BOOLEAN, mặc định TRUE và không cho phép NULL (trên PostgreSQL).

<details>
<summary>Gợi ý đáp án</summary>

~~~sql
ALTER TABLE san_pham
ADD COLUMN dang_ban BOOLEAN NOT NULL DEFAULT TRUE;
~~~

Cần xác nhận TRUE là giá trị mặc định nghiệp vụ đúng cho các sản phẩm đang tồn tại. Các DBMS khác có thể biểu diễn boolean bằng kiểu hoặc cú pháp khác.

</details>

### Bài 3 — Đổi tên cột

Hãy đổi **ten_san_pham** thành **ten_hien_thi**.

<details>
<summary>Gợi ý đáp án</summary>

~~~sql
ALTER TABLE san_pham
RENAME COLUMN ten_san_pham TO ten_hien_thi;
~~~

Nếu ứng dụng cũ vẫn truy vấn tên cũ, cần phương án tương thích hoặc phối hợp triển khai.

</details>

### Bài 4 — Đổi độ dài cột

Hãy đổi cột tên sản phẩm từ VARCHAR(150) lên VARCHAR(300) trên PostgreSQL, giả sử vẫn mang tên **ten_san_pham**.

<details>
<summary>Gợi ý đáp án</summary>

~~~sql
ALTER TABLE san_pham
ALTER COLUMN ten_san_pham TYPE VARCHAR(300);
~~~

Nếu đã làm Bài 3 trên cùng database, tên cột bây giờ là **ten_hien_thi**, nên phải thay tên tương ứng. Các bài có thể thực hiện trên bản sao schema riêng để tránh phụ thuộc thứ tự làm.

</details>

### Bài 5 — Thêm cột bắt buộc vào bảng có dữ liệu

Bảng đang có 10.000 sản phẩm. Bạn cần thêm cột **ma_sku** NOT NULL, không có một default chung đúng nghiệp vụ. Hãy mô tả các bước cần làm.

<details>
<summary>Gợi ý đáp án</summary>

1. Thêm **ma_sku** kiểu phù hợp và cho phép NULL.
2. Quyết định cách tạo SKU hợp lệ, nhất quán và không trùng theo yêu cầu nghiệp vụ.
3. Cập nhật dữ liệu cũ, có thể theo lô để giảm áp lực lên bảng lớn.
4. Sửa mọi đường ghi của ứng dụng để sản phẩm mới được gán SKU.
5. Kiểm tra không còn NULL và các ràng buộc cần thiết như UNIQUE.
6. Siết NOT NULL trên DBMS mục tiêu sau khi đã xác minh dữ liệu.

Ví dụ cấu trúc câu lệnh PostgreSQL:

~~~sql
ALTER TABLE san_pham ADD COLUMN ma_sku VARCHAR(40);

-- Phần UPDATE cần quy tắc tạo SKU thật của doanh nghiệp.

SELECT COUNT(*) AS so_dong_thieu
FROM san_pham
WHERE ma_sku IS NULL;

ALTER TABLE san_pham
ALTER COLUMN ma_sku SET NOT NULL;
~~~

Chỉ chạy lệnh SET NOT NULL khi số dòng thiếu bằng 0 và đường ghi mới đã đáp ứng.

</details>

### Bài 6 — Xóa cột

Bảng không còn dùng **ghi_chu_cu**. Hãy viết câu SQL xóa cột trên PostgreSQL và giải thích điều cần làm trước khi chạy.

<details>
<summary>Gợi ý đáp án</summary>

~~~sql
ALTER TABLE san_pham
DROP COLUMN ghi_chu_cu;
~~~

Trước khi chạy cần kiểm tra phụ thuộc và mã ứng dụng, xác định dữ liệu có cần giữ lại hay không, có bản sao/backup phù hợp, và đánh giá thời gian khóa/triển khai. Thêm lại cột sau này không tự khôi phục giá trị cũ.

</details>

### Bài 7 — Chuyển cú pháp giữa DBMS

Viết câu lệnh đổi tên cột **gia_ban** thành **don_gia** trong SQL Server.

<details>
<summary>Gợi ý đáp án</summary>

~~~sql
EXEC sp_rename
    N'dbo.san_pham.gia_ban',
    N'don_gia',
    N'COLUMN';
~~~

Cần xác nhận schema của bảng và kiểm tra những đối tượng/mã SQL còn tham chiếu **gia_ban**.

</details>

### Bài 8 — Phân biệt đổi tên với đổi kiểu

Một đồng nghiệp dùng câu:

~~~sql
ALTER TABLE san_pham
RENAME COLUMN gia_ban TO don_gia;
~~~

rồi kết luận “cột đã trở thành DECIMAL(14,2)”. Điều đó có đúng không?

<details>
<summary>Gợi ý đáp án</summary>

Không. **RENAME COLUMN** chỉ đổi tên cột. Để đổi kiểu hoặc precision/scale trên PostgreSQL, cần một thao tác khác:

~~~sql
ALTER TABLE san_pham
ALTER COLUMN don_gia TYPE NUMERIC(14, 2);
~~~

Vẫn phải đánh giá dữ liệu và phụ thuộc trước khi thay kiểu.

</details>

### Bài 9 — Vì sao không thể rollback đơn giản sau DROP?

Bạn xóa cột **ghi_chu_cu** rồi muốn rollback bằng ADD COLUMN cùng tên. Kết quả có khôi phục ghi chú cũ không?

<details>
<summary>Gợi ý đáp án</summary>

Không. ADD tạo một cột mới, không có cơ chế tự nạp lại giá trị đã bị xóa khỏi cột cũ. Muốn phục hồi phải có backup, bản sao dữ liệu trước xóa hoặc cơ chế khôi phục khác đã chuẩn bị.

</details>

### Bài 10 — Lập kế hoạch migration không gián đoạn

Một API cũ đang đọc **gia_ban**, API mới sẽ đọc **don_gia**. Bạn có thể đổi tên cột ngay giữa lúc hai phiên bản vẫn hoạt động không? Nêu một chiến lược triển khai.

<details>
<summary>Gợi ý đáp án</summary>

Không nên đổi trực tiếp khi API cũ chưa hỗ trợ tên mới. Có thể triển khai theo mô hình **Expand → Migrate → Contract**:

1. Thêm cột **don_gia** nullable.
2. Chuyển dữ liệu và duy trì đồng bộ giữa **gia_ban** và **don_gia** trong thời gian chuyển tiếp.
3. Triển khai API mới và kiểm tra toàn bộ luồng đọc/ghi.
4. Đảm bảo không còn thành phần nào phụ thuộc **gia_ban**.
5. Siết ràng buộc mới và xóa cột cũ trong migration riêng sau khi dữ liệu đã an toàn.

Cần đánh giá thêm hiệu năng, tính nhất quán và rollback theo DBMS thực tế.

</details>

## 18. Câu hỏi thường gặp

### Có thể ADD COLUMN vào bảng đang chứa hàng triệu dòng không?

Có thể, tùy DBMS và loại cột cần thêm. Tuy nhiên, mức khóa, việc viết lại bảng, kiểm tra default/constraint và thời gian chạy có thể rất khác nhau. Cần xem khả năng online/instant DDL của đúng DBMS, thử trên dữ liệu gần thực tế và chuẩn bị kế hoạch triển khai.

### Có thể thêm cột NOT NULL mà không DEFAULT không?

Với **bảng trống**, nhiều DBMS cho phép. Với **bảng có dữ liệu**, việc bắt các dòng cũ thỏa NOT NULL thường không thể thực hiện ngay nếu không có cách cung cấp giá trị. Giải pháp thường là default phù hợp hoặc thêm nullable trước, backfill, rồi siết NOT NULL.

### RENAME COLUMN có làm mất dữ liệu không?

Mục đích của RENAME COLUMN là đổi tên cột, thường giữ nguyên giá trị của cột đó. Nhưng thao tác có thể làm hỏng các tham chiếu theo tên trong mã ứng dụng hoặc đối tượng phụ thuộc. Cần kiểm tra và triển khai tương thích.

### Đổi VARCHAR(50) thành VARCHAR(200) có chắc chắn an toàn không?

Việc nới giới hạn thường đơn giản hơn thu hẹp, nhưng vẫn phải xét ràng buộc, chỉ mục, phụ thuộc, khóa và cơ chế thực thi của DBMS. Tính “an toàn” ở môi trường sản xuất còn phụ thuộc chi phí thay đổi và tương thích ứng dụng.

### DROP COLUMN có xóa toàn bộ bảng không?

Không. **DROP COLUMN** xóa một cột khỏi định nghĩa bảng; **DROP TABLE** xóa đối tượng bảng. Tuy nhiên, việc xóa một cột có thể làm mất dữ liệu thuộc cột đó và ảnh hưởng đối tượng phụ thuộc.

### Có thể gộp tất cả ADD, RENAME và DROP trong một câu ALTER TABLE không?

Một số DBMS cho phép gộp nhiều thay đổi trong một câu; số khác có cú pháp hoặc hạn chế riêng. Khi migration chứa nhiều bước phụ thuộc vào trạng thái trước đó, tách bước rõ ràng thường giúp kiểm soát và chẩn đoán lỗi dễ hơn. Không nên giả định một câu SQL gộp sẽ chạy trên mọi DBMS.

### Có thể dùng IF EXISTS / IF NOT EXISTS để migration chạy lặp lại không?

Một số DBMS hỗ trợ **IF EXISTS** hoặc **IF NOT EXISTS** trong một số biến thể ALTER TABLE, nhưng không đồng nhất. Ngay cả khi có, **“cột đã tồn tại” không chứng minh kiểu, default hoặc ràng buộc của cột đúng**. Công cụ migration nên quản lý phiên bản schema và kiểm tra định nghĩa, thay vì chỉ bỏ qua lỗi do tên đã tồn tại.

## 19. Ghi nhớ

- **ALTER TABLE** là câu lệnh DDL thay đổi cấu trúc một bảng đang tồn tại; **UPDATE** mới thay đổi giá trị trong các dòng.
- **ADD COLUMN** mở rộng bảng. Khi thêm cột NOT NULL vào bảng có dữ liệu, phải giải quyết giá trị cho các dòng cũ và các đường ghi mới.
- **DEFAULT** xác định giá trị mặc định trong những trường hợp DBMS áp dụng; **không thay thế NOT NULL** và không nên bị nhầm với một bản cập nhật dữ liệu cũ có chủ đích.
- **RENAME COLUMN** đổi tên cột; **ALTER/MODIFY COLUMN** thay kiểu, độ dài hoặc thuộc tính. Hai nhóm thao tác khác nhau.
- **DROP COLUMN** có thể làm mất dữ liệu và phá vỡ các đối tượng hoặc ứng dụng đang phụ thuộc vào cột. Thêm lại cột không tự khôi phục giá trị cũ.
- **PostgreSQL, MySQL, SQL Server, Oracle và SQLite khác cú pháp và khả năng ALTER TABLE**. Đối chiếu đúng DBMS và phiên bản đang sử dụng.
- Với hệ thống đang hoạt động, xem xét **mở rộng schema → cập nhật dữ liệu và ứng dụng → siết ràng buộc hoặc loại bỏ cột cũ** theo nhiều lần migration.
- Luôn kiểm tra **schema hiện tại, dữ liệu thực tế, dependency, mức khóa, kế hoạch rollback và ứng dụng sau triển khai**.

### Tài liệu tham khảo để tra cứu theo phiên bản

Khi cần áp dụng câu lệnh lên một hệ quản trị cụ thể, nên xem tài liệu chính thức tương ứng:

- **PostgreSQL Documentation:** *ALTER TABLE*, *Data Definition*, *Constraints*, *Explicit Locking*.
- **MySQL Reference Manual:** *ALTER TABLE Statement*, *InnoDB and Online DDL*, *Data Type Syntax*.
- **Microsoft Learn (Transact-SQL):** *ALTER TABLE*, *ALTER TABLE ... ALTER COLUMN*, *sp_rename*, *Default Constraints*.
- **Oracle Database SQL Language Reference:** *ALTER TABLE*, *Modifying Table Columns*, *Renaming Columns*.
- **SQLite Documentation:** *ALTER TABLE*, *Making Other Kinds of Table Schema Changes*, *CREATE TABLE*.
- **Flyway / Liquibase documentation:** quản lý phiên bản thay đổi schema, lịch sử migration và quy trình triển khai.

Các lệnh trong bài là ví dụ học tập. Khi vận hành thực tế, **phiên bản DBMS, kiểu dữ liệu, cấu trúc bảng, số lượng dòng và phụ thuộc** quyết định lệnh có hợp lệ và an toàn hay không.

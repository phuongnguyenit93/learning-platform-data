# Chuẩn SQL, phương ngữ và tính khả chuyển của câu lệnh

> **Bối cảnh:** SQL là ngôn ngữ phổ biến để làm việc với cơ sở dữ liệu quan hệ, nhưng một câu lệnh chạy đúng trên PostgreSQL chưa chắc chạy nguyên vẹn trên MySQL, SQL Server, Oracle Database hoặc SQLite. Bài học này giải thích vì sao có khác biệt, phần nào của SQL được chuẩn hóa, cách đọc và viết câu lệnh dễ chuyển giữa các hệ quản trị, cũng như cách xử lý khi phải sử dụng tính năng riêng của một hệ.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **chuẩn SQL** với **phương ngữ SQL** và hiểu vì sao “hỗ trợ SQL” không có nghĩa là hỗ trợ mọi cú pháp giống nhau.
- Nhận diện các điểm thường cản trở việc chuyển câu lệnh giữa các hệ quản trị cơ sở dữ liệu (DBMS): kiểu dữ liệu, phân trang, hàm, định danh, khóa tự sinh, xử lý giá trị NULL, thao tác thêm/cập nhật đồng thời và giao dịch.
- Viết các truy vấn dùng tập tính năng SQL chung, đồng thời nhận biết những trường hợp phải tách mã riêng theo DBMS.
- Phân biệt **chạy được về cú pháp** với **đúng về ý nghĩa, kết quả và hiệu năng**.
- Xây dựng cách kiểm thử tính khả chuyển trên đúng phiên bản và cấu hình cơ sở dữ liệu mà ứng dụng dùng.

## 2. Chuẩn SQL là gì?

### 2.1. SQL là ngôn ngữ khai báo

SQL (Structured Query Language) dùng để định nghĩa, truy vấn và thao tác dữ liệu trong cơ sở dữ liệu quan hệ. Với câu lệnh truy vấn, lập trình viên mô tả **muốn lấy dữ liệu nào**, còn DBMS lựa chọn kế hoạch thực thi cụ thể.

Ví dụ, yêu cầu “lấy mã và tên khách hàng đang hoạt động, sắp xếp theo mã” có thể viết:

~~~sql
SELECT ma_khach_hang, ten_khach_hang
FROM khach_hang
WHERE trang_thai = 'ACTIVE'
ORDER BY ma_khach_hang;
~~~

Truy vấn này không chỉ định DBMS phải đọc bảng bằng cách quét toàn bộ hay dùng chỉ mục. Hai DBMS có thể trả cùng kết quả nhưng triển khai và tối ưu khác nhau.

Các nhóm câu lệnh thường gặp là:

| Nhóm | Mục đích | Ví dụ |
|---|---|---|
| Định nghĩa dữ liệu (DDL) | Tạo và thay đổi cấu trúc | CREATE TABLE, ALTER TABLE, DROP TABLE |
| Truy vấn và thao tác dữ liệu | Đọc, thêm, sửa, xóa bản ghi | SELECT, INSERT, UPDATE, DELETE |
| Điều khiển giao dịch | Xác nhận hoặc hủy thay đổi | COMMIT, ROLLBACK |
| Điều khiển quyền truy cập | Cấp, thu hồi quyền | GRANT, REVOKE |

**DQL, DML, DDL, DCL, TCL** là cách phân loại thường dùng trong tài liệu đào tạo; ranh giới và tên nhóm không nên được hiểu là các “chế độ” bắt buộc tồn tại giống nhau trong mọi DBMS.

### 2.2. Ai định nghĩa chuẩn?

SQL được chuẩn hóa trong bộ tiêu chuẩn **ISO/IEC 9075**. Nhiều phiên bản đã được công bố qua thời gian, chẳng hạn SQL-92, SQL:1999, SQL:2003, SQL:2016 và SQL:2023. Các phiên bản bổ sung hoặc phát triển khả năng biểu thức, truy vấn, dữ liệu có cấu trúc và những tính năng mới của ngôn ngữ.

Chuẩn mô tả ngữ pháp và hành vi dự kiến của nhiều tính năng SQL. Tuy nhiên:

1. Chuẩn có nhiều phần và nhiều tính năng; một sản phẩm có thể chỉ triển khai một tập con.
2. DBMS thường bổ sung **phần mở rộng** để giải quyết nhu cầu riêng hoặc tối ưu cho kiến trúc của họ.
3. Một tính năng có cùng tên vẫn có thể khác về kiểu dữ liệu, giới hạn, xử lý lỗi hoặc các trường hợp biên.
4. Phiên bản DBMS và thiết lập máy chủ có thể thay đổi cú pháp được chấp nhận cũng như cách diễn giải câu lệnh.

Vì vậy, câu hỏi thực tế là **“tính năng này có hoạt động đúng trên các DBMS và phiên bản mục tiêu của ứng dụng không?”**, thay vì chỉ hỏi “câu lệnh này có phải SQL không?”.

### 2.3. Chuẩn, triển khai và phương ngữ

- **SQL chuẩn (standard SQL):** ngôn ngữ được mô tả bởi tiêu chuẩn ISO/IEC 9075.
- **Triển khai SQL:** tập tính năng và hành vi một DBMS thực sự cung cấp.
- **Phương ngữ SQL (SQL dialect):** cú pháp, hàm, kiểu dữ liệu và cách sử dụng SQL đặc trưng của một DBMS.

Một số hệ quản trị phổ biến là **PostgreSQL**, **MySQL**, **Microsoft SQL Server** (thường gắn với tên **T-SQL**), **Oracle Database** và **SQLite**. Không nên gọi toàn bộ SQL là “MySQL” hay “SQL Server”: đó là tên các sản phẩm hoặc hệ sinh thái triển khai SQL.

Ví dụ, yêu cầu lấy 10 dòng đầu tiên sau khi sắp xếp có thể được diễn đạt khác nhau:

~~~sql
-- PostgreSQL, MySQL, SQLite
SELECT ma_khach_hang
FROM khach_hang
ORDER BY ma_khach_hang
LIMIT 10;
~~~

~~~sql
-- SQL Server
SELECT TOP (10) ma_khach_hang
FROM khach_hang
ORDER BY ma_khach_hang;
~~~

~~~sql
-- Oracle Database (12c trở lên)
SELECT ma_khach_hang
FROM khach_hang
ORDER BY ma_khach_hang
FETCH FIRST 10 ROWS ONLY;
~~~

Ba câu lệnh cùng phục vụ một yêu cầu nghiệp vụ, nhưng **LIMIT**, **TOP** và **FETCH FIRST** không thay thế trực tiếp cho nhau trên mọi sản phẩm.

## 3. Tính khả chuyển của SQL gồm những mức nào?

**Tính khả chuyển (portability)** là khả năng đưa câu lệnh, lược đồ hoặc logic truy cập dữ liệu sang môi trường DBMS khác mà không phải sửa nhiều và vẫn thỏa yêu cầu.

Có ít nhất bốn mức cần phân biệt:

| Mức | Câu hỏi kiểm tra | Ví dụ |
|---|---|---|
| **Cú pháp** | DBMS khác có phân tích và chạy được câu lệnh không? | SQL Server không dùng LIMIT theo cách PostgreSQL dùng. |
| **Ngữ nghĩa** | Câu lệnh có hiểu và xử lý dữ liệu giống nhau không? | Cách so sánh chuỗi phụ thuộc collation; phép toán trên thời gian phụ thuộc kiểu dữ liệu và múi giờ. |
| **Kết quả và ràng buộc** | Dòng dữ liệu, thứ tự, lỗi, tính nguyên tử và tính đúng đắn có như mong muốn không? | Cách thực thi khóa ngoại, UPSERT và DDL trong giao dịch có thể khác. |
| **Hiệu năng** | Câu lệnh còn đáp ứng yêu cầu khi dữ liệu tăng không? | Cùng truy vấn JOIN có thể dùng kế hoạch thực thi khác trên từng DBMS. |

**Một câu lệnh có thể khả chuyển về cú pháp mà vẫn không khả chuyển về hành vi.** Ví dụ, truy vấn không có ORDER BY không cam kết thứ tự dòng, dù kết quả có vẻ “ổn định” khi chạy thử trên một máy.

Tính khả chuyển luôn có **phạm vi**. Một câu lệnh có thể chuyển tốt giữa PostgreSQL 16 và PostgreSQL 17, nhưng gặp vấn đề khi chuyển từ PostgreSQL sang SQL Server. Ngay cả hai phiên bản của cùng sản phẩm cũng có thể có khác biệt tính năng.

## 4. Phần SQL chung nên ưu tiên khi viết truy vấn

Giả sử hệ thống bán hàng có các bảng:

| Bảng | Cột minh họa | Ý nghĩa |
|---|---|---|
| khach_hang | ma_khach_hang, ten_khach_hang, trang_thai | Danh mục khách hàng |
| don_hang | ma_don_hang, ma_khach_hang, tong_tien, trang_thai, ngay_dat | Các đơn hàng của khách |
| san_pham | ma_san_pham, ten_san_pham, gia_ban | Danh mục sản phẩm |

Các cột được giả định có kiểu phù hợp. Đây là **mô hình minh họa**, không phải một bộ lệnh DDL có thể dùng nguyên vẹn cho mọi DBMS.

### 4.1. SELECT, WHERE, JOIN, GROUP BY và ORDER BY

Một truy vấn dùng nhiều cấu trúc quen thuộc và khá rộng rãi:

~~~sql
SELECT
    k.ma_khach_hang,
    k.ten_khach_hang,
    COUNT(d.ma_don_hang) AS so_don_da_thanh_toan,
    COALESCE(SUM(d.tong_tien), 0) AS tong_da_mua
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
   AND d.trang_thai = 'PAID'
WHERE k.trang_thai = 'ACTIVE'
GROUP BY k.ma_khach_hang, k.ten_khach_hang
ORDER BY tong_da_mua DESC, k.ma_khach_hang ASC;
~~~

Ý nghĩa:

- **LEFT JOIN** giữ khách hàng đang hoạt động kể cả khi chưa có đơn thanh toán.
- Điều kiện trạng thái của đơn nằm trong **ON**. Nếu chuyển điều kiện đó xuống WHERE, các khách chưa có đơn phù hợp sẽ bị loại khỏi kết quả.
- **COUNT(d.ma_don_hang)** trả 0 nếu không có đơn phù hợp, vì COUNT trên một cột bỏ qua giá trị NULL.
- **SUM** có thể trả NULL khi không có dòng giá trị phù hợp; **COALESCE** thay NULL bằng 0.
- **GROUP BY** liệt kê đầy đủ các cột được chọn ngoài hàm tổng hợp, tránh phụ thuộc vào chế độ xử lý nhóm riêng của từng DBMS.
- **ORDER BY** nêu thứ tự ưu tiên một cách tường minh. Mã khách hàng làm tiêu chí phụ khi hai khách có tổng tiền bằng nhau.

Khi cần chỉ lấy một số lượng dòng nhất định, hãy bổ sung phân trang theo đúng DBMS mục tiêu, không tự giả định cú pháp giới hạn dòng giống nhau.

### 4.2. CASE, COALESCE, NULLIF, EXISTS

Nhiều tác vụ nghiệp vụ có thể biểu diễn bằng các cấu trúc chung:

~~~sql
SELECT
    ma_san_pham,
    gia_ban,
    CASE
        WHEN gia_ban >= 1000000 THEN 'CAO'
        WHEN gia_ban >= 200000 THEN 'TRUNG_BINH'
        ELSE 'THAP'
    END AS nhom_gia
FROM san_pham;
~~~

~~~sql
-- Chỉ lấy khách hàng có ít nhất một đơn đã thanh toán.
SELECT k.ma_khach_hang, k.ten_khach_hang
FROM khach_hang k
WHERE EXISTS (
    SELECT 1
    FROM don_hang d
    WHERE d.ma_khach_hang = k.ma_khach_hang
      AND d.trang_thai = 'PAID'
);
~~~

**EXISTS** kiểm tra sự tồn tại của dòng thỏa điều kiện, tránh tạo nhiều bản sao khách hàng như một JOIN trực tiếp khi một khách có nhiều đơn. **CASE**, **COALESCE** và **NULLIF** được hỗ trợ rộng rãi, nhưng kiểu kết quả sau chuyển đổi kiểu ngầm vẫn cần được kiểm tra với dữ liệu thực tế.

### 4.3. Các nguyên tắc giúp câu lệnh ít phụ thuộc phương ngữ

- Viết rõ **JOIN ... ON** thay cho cú pháp nối bảng bằng dấu phẩy và điều kiện nối nằm lẫn trong WHERE.
- Định danh cột đủ rõ ràng, nhất là khi nhiều bảng có cột trùng tên.
- Dùng **CASE**, **COALESCE**, **CAST**, **EXISTS**, **IN**, các phép tổng hợp phổ biến trước khi chọn hàm riêng của DBMS.
- Chỉ dùng ORDER BY khi có yêu cầu thứ tự; đừng dựa vào thứ tự lưu vật lý hay thứ tự sau GROUP BY.
- Tránh đặt tên bảng, cột trùng từ khóa SQL; dùng tên dễ đọc, thống nhất, không phụ thuộc chữ hoa/chữ thường.
- Đặt tham số qua **prepared statement / parameter binding** của driver hoặc thư viện truy cập dữ liệu thay cho nối chuỗi tạo SQL.
- Luôn kiểm tra tài liệu của **phiên bản DBMS cụ thể** trước khi tuyên bố một tính năng “chạy trên mọi hệ”.

## 5. Những khác biệt phương ngữ thường gặp

Bảng sau là ví dụ định hướng, không phải cam kết mọi phiên bản đều hỗ trợ mọi cách viết.

| Nhu cầu | PostgreSQL | MySQL | SQL Server | Oracle Database | SQLite |
|---|---|---|---|---|---|
| Giới hạn số dòng thông dụng | LIMIT | LIMIT | TOP hoặc OFFSET ... FETCH | FETCH FIRST (12c+) | LIMIT |
| Ghép chuỗi thường dùng | Toán tử \|\| | CONCAT() | CONCAT() hoặc + | Toán tử \|\| | Toán tử \|\| |
| Khóa tăng tự động | GENERATED ... AS IDENTITY / serial | AUTO_INCREMENT | IDENTITY | GENERATED ... AS IDENTITY | INTEGER PRIMARY KEY gắn với rowid* |
| Thêm nếu chưa có, cập nhật nếu trùng | INSERT ... ON CONFLICT | INSERT ... ON DUPLICATE KEY UPDATE | Thường dùng logic giao dịch riêng hoặc MERGE | MERGE | INSERT ... ON CONFLICT |
| Kiểu logic thường dùng | boolean | BOOLEAN là bí danh TINYINT(1) | bit | Phụ thuộc phiên bản và kiểu cột | Quy ước lưu số 0/1; không có lớp lưu trữ BOOLEAN riêng |
| Trích ngày hiện tại | CURRENT_DATE | CURRENT_DATE | CAST(GETDATE() AS date) | CURRENT_DATE | CURRENT_DATE (kết quả có dạng văn bản) |

*Trong SQLite, thuộc tính khóa và cách tạo rowid có nhiều quy tắc chi tiết; không suy ra mọi cột INTEGER đều tự tăng như nhau. Từ khóa AUTOINCREMENT của SQLite còn có ngữ nghĩa riêng, không nên thêm theo thói quen.*

Các phần dưới đây giải thích tại sao những khác biệt này có thể ảnh hưởng trực tiếp đến dữ liệu.

### 5.1. Định danh và dấu nháy

Trong SQL, **chuỗi ký tự** thường đặt trong dấu nháy đơn:

~~~sql
SELECT ma_khach_hang
FROM khach_hang
WHERE trang_thai = 'ACTIVE';
~~~

Theo cú pháp định danh phân cách của SQL chuẩn, tên cột hoặc bảng đặc biệt có thể đặt trong **dấu nháy kép**:

~~~sql
SELECT "ten_khach_hang"
FROM "khach_hang";
~~~

Tuy nhiên, các DBMS có thêm quy ước riêng:

| DBMS | Quy ước định danh phân cách hay gặp |
|---|---|
| PostgreSQL, Oracle | "ten_cot" |
| MySQL | \`ten_cot\` mặc định; có thể bật ANSI_QUOTES |
| SQL Server | [ten_cot], hoặc "ten_cot" khi QUOTED_IDENTIFIER phù hợp |
| SQLite | "ten_cot"; cũng nhận một số cách viết tương thích khác |

**Đừng nhầm** dấu nháy đơn của giá trị chuỗi với dấu nháy của định danh. Cách xử lý chữ hoa/chữ thường của định danh cũng không đồng nhất: PostgreSQL thường gấp định danh không nháy thành chữ thường, trong khi chuẩn SQL quy định quy tắc theo chữ hoa; MySQL còn có khác biệt tên bảng theo hệ điều hành và cấu hình.

**Khuyến nghị:** ưu tiên tên không có khoảng trắng, dấu đặc biệt, từ khóa dành riêng hoặc phụ thuộc chữ hoa/chữ thường, chẳng hạn **ma_don_hang** thay cho tên có dấu cách như **Order Detail**. Quy ước đặt tên nhất quán giúp giảm nhu cầu dùng dấu nháy riêng của từng hệ.

### 5.2. Chuỗi và các hàm xử lý chuỗi

Xét yêu cầu ghép họ và tên, mỗi DBMS có thể có cách diễn đạt khác nhau:

~~~sql
-- PostgreSQL, Oracle, SQLite
SELECT ho || ' ' || ten AS ho_ten
FROM nhan_vien;
~~~

~~~sql
-- MySQL
SELECT CONCAT(ho, ' ', ten) AS ho_ten
FROM nhan_vien;
~~~

~~~sql
-- SQL Server
SELECT CONCAT(ho, ' ', ten) AS ho_ten
FROM nhan_vien;
~~~

Toán tử **||** là phép nối chuỗi trong SQL chuẩn, nhưng MySQL mặc định thường hiểu nó là phép OR logic nếu không bật chế độ PIPES_AS_CONCAT. Ngay cả hàm CONCAT cũng có thể khác trong cách xử lý đối số NULL. Ví dụ, một hệ có thể coi NULL như chuỗi rỗng khi ghép, hệ khác truyền NULL ra kết quả.

Cần xác định quy tắc mong muốn thay vì suy luận theo tên hàm. Khi nghiệp vụ coi NULL là chuỗi rỗng, có thể chuẩn hóa đầu vào:

~~~sql
SELECT
    COALESCE(ho, '') AS ho_hien_thi,
    COALESCE(ten, '') AS ten_hien_thi
FROM nhan_vien;
~~~

Sau đó lựa chọn toán tử/hàm ghép tương ứng trong từng phương ngữ.

Một khác biệt dễ bỏ sót khác là **độ dài chuỗi**. Ví dụ, MySQL phân biệt LENGTH() (độ dài theo byte) với CHAR_LENGTH() (độ dài theo ký tự); SQL Server dùng LEN() với quy tắc riêng về dấu cách ở cuối; PostgreSQL có CHAR_LENGTH(); SQLite có length(). Với tiếng Việt có dấu và Unicode, khác biệt byte/ký tự có thể ảnh hưởng trực tiếp tới kiểm tra dữ liệu.

### 5.3. Lấy N dòng và phân trang

Yêu cầu nghiệp vụ: “Lấy 10 khách hàng, bắt đầu từ vị trí 21, sắp xếp theo mã khách hàng tăng dần”.

~~~sql
-- PostgreSQL, MySQL, SQLite
SELECT ma_khach_hang, ten_khach_hang
FROM khach_hang
ORDER BY ma_khach_hang
LIMIT 10 OFFSET 20;
~~~

~~~sql
-- SQL Server (2012 trở lên)
SELECT ma_khach_hang, ten_khach_hang
FROM khach_hang
ORDER BY ma_khach_hang
OFFSET 20 ROWS FETCH NEXT 10 ROWS ONLY;
~~~

~~~sql
-- Oracle Database (12c trở lên)
SELECT ma_khach_hang, ten_khach_hang
FROM khach_hang
ORDER BY ma_khach_hang
OFFSET 20 ROWS FETCH NEXT 10 ROWS ONLY;
~~~

Một số DBMS cũng hỗ trợ cú pháp **OFFSET ... FETCH** gần chuẩn; song những khác biệt về yêu cầu ORDER BY và phiên bản vẫn cần được kiểm tra.

**Lưu ý quan trọng:**

- Thiếu ORDER BY, khái niệm “10 dòng đầu” thường không có ý nghĩa ổn định.
- ORDER BY chỉ theo cột có giá trị trùng nhau vẫn có thể cho thứ tự không ổn định giữa các dòng hòa. Thêm khóa duy nhất vào cuối tiêu chí sắp xếp nếu cần phân trang ổn định.
- OFFSET lớn có thể tốn chi phí. Với màn hình cuộn qua rất nhiều dữ liệu, có thể cân nhắc **keyset pagination** (lấy trang sau dựa trên giá trị khóa cuối trang trước).
- Trên các bản ghi thay đổi liên tục, ngay cả ORDER BY tường minh cũng không làm các trang OFFSET bất biến giữa những lần truy vấn. Cần thiết kế mức nhất quán dữ liệu phù hợp.

Ví dụ keyset pagination theo khóa tăng dần:

~~~sql
-- Lấy trang tiếp theo khi trang trước kết thúc ở mã 1050.
-- Chỉ dùng khi ma_khach_hang có thứ tự so sánh phù hợp.
SELECT ma_khach_hang, ten_khach_hang
FROM khach_hang
WHERE ma_khach_hang > 1050
ORDER BY ma_khach_hang;
~~~

Để giới hạn số dòng của trang, ứng dụng vẫn phải thêm phần cú pháp giới hạn phù hợp DBMS.

### 5.4. Sinh khóa và giá trị mặc định

Thiết kế “cột ID tự sinh” là một trong các điểm khó chuyển nhất ở tầng DDL.

~~~sql
-- PostgreSQL: một cách khai báo hiện đại
CREATE TABLE nhom_hang (
    ma_nhom BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ten_nhom VARCHAR(100) NOT NULL
);
~~~

~~~sql
-- MySQL
CREATE TABLE nhom_hang (
    ma_nhom BIGINT AUTO_INCREMENT PRIMARY KEY,
    ten_nhom VARCHAR(100) NOT NULL
);
~~~

~~~sql
-- SQL Server
CREATE TABLE nhom_hang (
    ma_nhom BIGINT IDENTITY(1, 1) PRIMARY KEY,
    ten_nhom VARCHAR(100) NOT NULL
);
~~~

Oracle Database có tính năng identity ở các phiên bản hiện đại, nhưng chi tiết định nghĩa và lấy ID vừa thêm vẫn khác. SQLite dùng cơ chế rowid với trường hợp khai báo riêng.

Khi chuyển hệ, không chỉ đổi từ khóa: cần xem **cách cấp phát giá trị, hành vi khi rollback, cơ chế lấy khóa vừa tạo, quyền chèn giá trị thủ công, giới hạn số và việc đồng bộ khóa**. Mã ứng dụng nên dùng cơ chế trả khóa do thư viện hoặc DBMS hỗ trợ và có kiểm thử thực tế.

### 5.5. INSERT kết hợp UPDATE khi bị trùng khóa (UPSERT)

Nghiệp vụ: có bảng **ton_kho(ma_san_pham, so_luong)**, trong đó **ma_san_pham** có UNIQUE hoặc PRIMARY KEY. Khi nhập thêm 5 sản phẩm P01, hệ thống phải tạo dòng nếu chưa có, hoặc cộng thêm 5 nếu đã có.

~~~sql
-- PostgreSQL
INSERT INTO ton_kho (ma_san_pham, so_luong)
VALUES ('P01', 5)
ON CONFLICT (ma_san_pham)
DO UPDATE
SET so_luong = ton_kho.so_luong + EXCLUDED.so_luong;
~~~

~~~sql
-- MySQL
INSERT INTO ton_kho (ma_san_pham, so_luong)
VALUES ('P01', 5)
ON DUPLICATE KEY UPDATE
    so_luong = so_luong + 5;
~~~

SQLite hiện đại có cú pháp **ON CONFLICT** tương tự PostgreSQL cho nhiều trường hợp. SQL Server và Oracle thường có thể sử dụng **MERGE** hoặc giải pháp cập nhật/chèn trong giao dịch. Tuy nhiên, tính an toàn khi có nhiều giao dịch đồng thời phụ thuộc DBMS, ràng buộc duy nhất, cách khóa và mức cô lập. Không nên kết luận “MERGE tương đương UPSERT” trong mọi trường hợp.

**Điểm cần hiểu:** ở PostgreSQL, điều kiện xung đột trong ví dụ gắn với khóa **ma_san_pham**; ở MySQL, cú pháp ON DUPLICATE KEY UPDATE có thể được kích hoạt khi vi phạm bất kỳ khóa UNIQUE hoặc PRIMARY KEY liên quan. Nếu bảng có nhiều khóa UNIQUE, hai câu lệnh nhìn giống nhau có thể cập nhật những dòng khác nhau. Đây là khác biệt **ngữ nghĩa**, không chỉ cú pháp.

### 5.6. Kiểu dữ liệu: tên giống không đồng nghĩa hành vi giống

Các hệ quản trị có sự khác nhau về:

| Mục | Vấn đề cần kiểm tra |
|---|---|
| Số nguyên | Dải giá trị, có/không hỗ trợ UNSIGNED, tràn số |
| DECIMAL/NUMERIC | Precision, scale, làm tròn, kiểu kết quả sau phép tính |
| FLOAT/REAL/DOUBLE | Sai số số thực nhị phân, kiểu và độ chính xác |
| VARCHAR/CHAR/TEXT | Độ dài theo byte hay ký tự, trailing spaces, collation |
| BOOLEAN | Kiểu logic thật, kiểu số hoặc quy ước lưu trữ |
| DATE/TIME/TIMESTAMP | Có múi giờ hay không; độ chính xác; cách đổi kiểu |
| BLOB/BINARY | Giới hạn dung lượng, cách truyền tham số và so sánh |
| JSON | Kiểu lưu trữ, phép truy cập, chỉ mục và cú pháp truy vấn |
| UUID | Kiểu bản địa hay lưu chuỗi/binary |

Ví dụ, lệnh khai báo **BOOLEAN** có thể được chấp nhận trong nhiều hệ, nhưng SQL Server phổ biến dùng **BIT**, MySQL xem BOOLEAN là bí danh của **TINYINT(1)**, còn SQLite sử dụng các lớp lưu trữ động. Vì vậy, ứng dụng không nên giả định rằng mọi DBMS trả cùng giá trị, cùng kiểu driver hoặc cùng quy tắc ép kiểu.

Với tiền tệ, ưu tiên một kiểu **DECIMAL/NUMERIC** có precision và scale được xác định theo yêu cầu, đồng thời kiểm tra cách DBMS thực hiện phép toán trên nó. Dùng FLOAT cho các khoản tiền yêu cầu chính xác tuyệt đối thường gây lỗi biểu diễn.

### 5.7. NULL và logic ba giá trị

Trong SQL, NULL biểu thị giá trị chưa biết/không có theo mô hình dữ liệu, và nhiều biểu thức có ba kết quả logic: **TRUE**, **FALSE**, **UNKNOWN**.

~~~sql
-- Không đúng về ý định tìm các dòng có email NULL:
SELECT ma_khach_hang
FROM khach_hang
WHERE email = NULL;
~~~

~~~sql
-- Đúng:
SELECT ma_khach_hang
FROM khach_hang
WHERE email IS NULL;
~~~

Các câu lệnh sau có ý nghĩa khác nhau:

~~~sql
SELECT COUNT(*) FROM khach_hang;
-- Đếm số dòng.

SELECT COUNT(email) FROM khach_hang;
-- Đếm các dòng có email khác NULL.
~~~

~~~sql
SELECT ma_khach_hang
FROM khach_hang
WHERE email IS NOT NULL;
~~~

Mặc dù **IS NULL** và **COALESCE** là công cụ chung, hãy kiểm tra quy tắc đặc thù về chuỗi rỗng và NULL. Oracle truyền thống coi chuỗi ký tự độ dài 0 là NULL trong nhiều ngữ cảnh; PostgreSQL và MySQL phân biệt chuỗi rỗng với NULL. Vì vậy, dữ liệu nhập **''** có thể cho kết quả lọc hoặc kiểm tra ràng buộc khác nhau.

**Bẫy với NOT IN:** nếu tập con chứa NULL, biểu thức NOT IN có thể cho UNKNOWN và không trả các dòng như kỳ vọng.

~~~sql
-- Thường dễ kiểm soát hơn NOT IN nếu tập con có thể chứa NULL:
SELECT k.ma_khach_hang
FROM khach_hang k
WHERE NOT EXISTS (
    SELECT 1
    FROM don_hang d
    WHERE d.ma_khach_hang = k.ma_khach_hang
);
~~~

### 5.8. Ngày giờ, múi giờ và ép kiểu

Một chuỗi như **'2026-11-14'** có thể được suy diễn thành kiểu ngày ở DBMS này nhưng bị hiểu là văn bản hoặc cần chuyển đổi tường minh ở DBMS khác.

SQL chuẩn có các kiểu và biểu thức ngày giờ, nhưng cách xử lý thời điểm, kiểu có múi giờ, định dạng đầu vào, thời gian địa phương và độ chính xác vẫn khác nhau.

Ví dụ, biểu thức:

~~~sql
SELECT CURRENT_TIMESTAMP;
~~~

được hỗ trợ rộng rãi nhưng **kiểu dữ liệu trả về, múi giờ và mức chính xác** không nhất thiết giống nhau.

Khuyến nghị cho ứng dụng:

1. Quy định rõ nghiệp vụ dùng **ngày lịch** (date) hay **thời điểm tuyệt đối** (instant).
2. Truyền giá trị qua **tham số đã gắn kiểu** ở driver/ORM, tránh tự xây chuỗi ngày giờ.
3. Chuẩn hóa cách lưu và chuyển đổi múi giờ, thường là lưu thời điểm theo UTC rồi đổi theo vùng giờ lúc hiển thị.
4. Kiểm thử những thời điểm chuyển ngày, vùng giờ và các trường hợp thiếu/thừa chính xác phần giây.
5. Tránh sao chép hàm riêng như GETDATE(), NOW(), SYSDATE hay phép cộng “ngày + số” sang DBMS khác mà không kiểm tra ý nghĩa.

### 5.9. So sánh chuỗi, Unicode và collation

**Collation** quyết định cách so sánh và sắp xếp chuỗi, có thể xét chữ hoa/thường, dấu, quy tắc ngôn ngữ và các yếu tố khác. Hai DBMS cùng chạy:

~~~sql
SELECT ten_khach_hang
FROM khach_hang
ORDER BY ten_khach_hang;
~~~

vẫn có thể sắp xếp tên tiếng Việt khác nhau vì collation của cột hoặc kết nối. Điều kiện **LIKE**, phép so sánh **=**, ràng buộc **UNIQUE** trên chuỗi và quy tắc bỏ khoảng trắng cũng có thể cho kết quả khác.

Ví dụ, nếu một môi trường coi **An** và **an** bằng nhau còn môi trường khác phân biệt chữ hoa, việc chuyển lược đồ có thể làm dữ liệu hiện có vi phạm UNIQUE hoặc khiến tìm kiếm khác kết quả cũ.

Cách xử lý là định nghĩa rõ yêu cầu nghiệp vụ về **phân biệt chữ hoa/thường, phân biệt dấu, chuẩn hóa Unicode, so sánh và sắp xếp**, sau đó chọn collation hoặc chuẩn hóa dữ liệu phù hợp trên từng DBMS. Không nên tự giả định bộ sắp xếp mặc định giống nhau.

## 6. Lược đồ và giao dịch: phần hay bị bỏ sót khi chỉ nhìn câu SELECT

Một bộ SQL không chỉ gồm truy vấn. Khả năng chuyển hệ còn phụ thuộc cách tạo bảng, ràng buộc và quản lý thay đổi.

### 6.1. Constraint cần được kiểm tra bằng dữ liệu thử

Các khái niệm **PRIMARY KEY**, **UNIQUE**, **FOREIGN KEY**, **NOT NULL**, **CHECK** có mặt rộng rãi, nhưng việc thực thi và quy tắc biên có thể khác theo DBMS/phiên bản/cấu hình.

Ví dụ:

~~~sql
CREATE TABLE don_hang (
    ma_don_hang INTEGER PRIMARY KEY,
    ma_khach_hang INTEGER NOT NULL,
    tong_tien DECIMAL(12, 2) NOT NULL,
    CONSTRAINT ck_tong_tien CHECK (tong_tien >= 0),
    CONSTRAINT fk_don_hang_khach
        FOREIGN KEY (ma_khach_hang)
        REFERENCES khach_hang(ma_khach_hang)
);
~~~

Đây là ví dụ thiết kế lược đồ để thảo luận. Để chạy thực tế, bảng **khach_hang** phải tồn tại và định nghĩa kiểu/khóa tương thích.

Những điểm cần kiểm tra khi chuyển hệ:

- DBMS có **thực sự kiểm tra** CHECK và FOREIGN KEY trong môi trường ứng dụng hay không, thay vì chỉ nhận cú pháp khai báo?
- UNIQUE cho phép bao nhiêu giá trị NULL và có coi các giá trị ấy là trùng nhau không?
- Khi xóa bản ghi cha, **ON DELETE CASCADE**, **RESTRICT** hoặc **NO ACTION** có đúng ý nghĩa và thời điểm mong muốn không?
- Việc đổi kiểu, thêm cột NOT NULL, sửa tên cột và thêm chỉ mục có cần cú pháp migration riêng không?

SQLite có cấu hình kiểm tra khóa ngoại cần được bật đúng; một số phiên bản MySQL cũ từng chấp nhận CHECK nhưng không thực thi. Bởi vậy, không thể lấy việc CREATE TABLE thành công làm bằng chứng tất cả ràng buộc đã được bảo đảm.

### 6.2. DDL và giao dịch không thống nhất

Với giao dịch thao tác dữ liệu, các câu lệnh thông thường là:

~~~sql
BEGIN;
UPDATE tai_khoan
SET so_du = so_du - 100
WHERE ma_tai_khoan = 1;

UPDATE tai_khoan
SET so_du = so_du + 100
WHERE ma_tai_khoan = 2;

COMMIT;
~~~

Cú pháp **bắt đầu giao dịch** có thể khác theo hệ (chẳng hạn START TRANSACTION hoặc BEGIN TRANSACTION), và ví dụ trên chưa xử lý đầy đủ tính hợp lệ số dư hay tình huống lỗi. Không sử dụng như một quy trình chuyển tiền hoàn chỉnh.

Khác biệt còn rõ hơn khi có **CREATE/ALTER/DROP** trong giao dịch:

- Một số DBMS cho phép nhiều thay đổi DDL được rollback.
- Một số DBMS tự commit trước/sau những lệnh DDL nhất định.
- Một số thao tác quản trị hoặc tạo chỉ mục có giới hạn riêng về ngữ cảnh giao dịch.

Vì vậy, kịch bản migration cần viết và kiểm thử cho đúng DBMS thay vì giả định “mọi lệnh nằm giữa BEGIN và ROLLBACK đều hoàn tác được”.

### 6.3. Cú pháp là một chuyện, cách đồng thời là chuyện khác

Cùng một cặp lệnh UPDATE/INSERT có thể hoạt động khác dưới tải đồng thời do mức cô lập (isolation level), quy tắc khóa, deadlock, retry và những thay đổi xảy ra giữa lúc đọc với lúc ghi. **Khả chuyển nghiệp vụ** đòi hỏi cả ràng buộc dữ liệu, giao dịch và ứng xử khi gặp xung đột.

Ví dụ, cách “SELECT kiểm tra tồn tại; nếu không có thì INSERT” có thể gặp race condition nếu hai giao dịch cùng thấy dòng chưa tồn tại. Giải pháp cần khóa duy nhất và một cơ chế chèn/cập nhật an toàn phù hợp DBMS mục tiêu.

## 7. Từ truy vấn theo phương ngữ đến thiết kế khả chuyển

Giả sử ứng dụng ban đầu chạy SQL Server và có truy vấn:

~~~sql
-- Phụ thuộc SQL Server
SELECT TOP (5)
    [ma_don_hang],
    [ngay_dat],
    [tong_tien]
FROM [don_hang]
WHERE [trang_thai] = 'PAID'
ORDER BY [ngay_dat] DESC, [ma_don_hang] DESC;
~~~

Truy vấn chứa phần riêng của SQL Server: **TOP** và dấu ngoặc vuông cho định danh.

Có thể tách thành hai lớp.

**Lớp logic chung:**

~~~sql
SELECT ma_don_hang, ngay_dat, tong_tien
FROM don_hang
WHERE trang_thai = 'PAID'
ORDER BY ngay_dat DESC, ma_don_hang DESC
~~~

**Lớp giới hạn số dòng theo DBMS:**

~~~sql
-- PostgreSQL, MySQL, SQLite: thêm cuối câu lệnh
LIMIT 5;
~~~

~~~sql
-- Oracle Database: thêm cuối câu lệnh
FETCH FIRST 5 ROWS ONLY;
~~~

~~~sql
-- SQL Server: chọn TOP (5) hoặc OFFSET/FETCH thích hợp
-- và giữ ORDER BY để kết quả có ý nghĩa ổn định.
~~~

Ví dụ này minh họa **tách yêu cầu nghiệp vụ ra khỏi phần cú pháp thay đổi**; không có nghĩa có thể nối những đoạn code một cách máy móc. Cú pháp SQL cần được tạo hoàn chỉnh bởi bộ xây dựng truy vấn hoặc adapter theo dialect, đồng thời mọi giá trị động phải được tham số hóa.

### 7.1. Dùng cửa sổ ROW_NUMBER khi phù hợp

Một phương án khác là đưa logic đánh số dòng vào truy vấn:

~~~sql
WITH don_da_xep AS (
    SELECT
        ma_don_hang,
        ngay_dat,
        tong_tien,
        ROW_NUMBER() OVER (
            ORDER BY ngay_dat DESC, ma_don_hang DESC
        ) AS so_thu_tu
    FROM don_hang
    WHERE trang_thai = 'PAID'
)
SELECT ma_don_hang, ngay_dat, tong_tien
FROM don_da_xep
WHERE so_thu_tu BETWEEN 1 AND 5
ORDER BY so_thu_tu;
~~~

**ROW_NUMBER() OVER (...)** và CTE (**WITH**) được hỗ trợ ở các phiên bản hiện đại của nhiều DBMS lớn. Cách này thường giảm khác biệt cú pháp phân trang trong những môi trường đã xác định hỗ trợ hàm cửa sổ, nhưng không bảo đảm tương thích với mọi phiên bản cũ và không bảo đảm hiệu năng tốt nhất. **ORDER BY** ngoài cùng vẫn cần để cam kết thứ tự trả về.

### 7.2. Chọn ranh giới phụ thuộc DBMS một cách có chủ đích

Trong thực tế có ba chiến lược phổ biến:

| Chiến lược | Phù hợp khi | Đánh đổi |
|---|---|---|
| Chỉ sử dụng tập SQL chung | Nhiều DBMS mục tiêu, truy vấn tương đối cơ bản | Có thể bỏ lỡ tính năng hoặc tối ưu mạnh của DBMS |
| SQL chung + adapter theo dialect | Phần lớn câu lệnh giống nhau, vài chỗ khác như LIMIT/UPSERT | Phải duy trì và kiểm thử từng adapter |
| Sử dụng phương ngữ riêng ở tầng dữ liệu | Hệ thống gắn với một DBMS, cần tính năng đặc thù | Việc chuyển DBMS sau này đòi hỏi migration và sửa code |

**Không nhất thiết phải theo đuổi một câu SQL “chạy ở mọi nơi”.** Mục tiêu tốt hơn là xác định trước danh sách DBMS được hỗ trợ, dùng tính năng chung ở nơi hợp lý và cô lập các khác biệt thành những phần dễ thay thế, có kiểm thử.

## 8. Viết SQL an toàn và khả chuyển trong ứng dụng

### 8.1. Tham số hóa là trách nhiệm của tầng truy cập dữ liệu

Không tạo câu lệnh bằng phép nối trực tiếp giá trị người dùng:

~~~text
KHÔNG NÊN:
"SELECT * FROM khach_hang WHERE email = '" + userInput + "'"
~~~

Cách này dễ gây **SQL injection** và lỗi khi giá trị chứa dấu nháy, dấu tiếng Việt hoặc dữ liệu ngày giờ.

Thay vào đó, dùng API prepared statement / parameter binding của thư viện truy cập dữ liệu. **Kiểu ký hiệu tham số** tùy driver:

- JDBC thường dùng dấu hỏi **?**.
- PostgreSQL native client thường dùng vị trí **$1**, **$2**, ...
- Một số driver/DBMS dùng tham số tên như **:email** hoặc **@email**.

Ví dụ minh họa kiểu JDBC:

~~~java
String sql = """
    SELECT ma_khach_hang, ten_khach_hang
    FROM khach_hang
    WHERE email = ?
    """;

try (PreparedStatement stmt = connection.prepareStatement(sql)) {
    stmt.setString(1, email);
    try (ResultSet rs = stmt.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getString("ten_khach_hang"));
        }
    }
}
~~~

Trong ứng dụng Java, **JDBC cung cấp một API chung** cho kết nối, thao tác và lấy kết quả; tuy nhiên điều đó không khiến mọi chuỗi SQL truyền qua JDBC tự động trở nên khả chuyển. Driver, kiểu dữ liệu trả về và phương ngữ vẫn cần được xử lý đúng.

### 8.2. Các biến thể SQL nên được quản lý ở một nơi

Nếu cùng hỗ trợ PostgreSQL và SQL Server, có thể mô tả hợp đồng:

~~~text
listPaidOrders(limit, offset, sort)
    -> tạo câu SELECT có tham số
    -> thêm phần phân trang phù hợp dialect
    -> trả cùng cấu trúc kết quả cho tầng nghiệp vụ
~~~

Tầng nghiệp vụ chỉ nên yêu cầu **danh sách đơn hàng đã thanh toán**, không phải tự biết dùng TOP hay LIMIT. Những phần như truy vấn JSON, tìm kiếm toàn văn, UPSERT, khóa tự sinh và migration thường cần adapter riêng.

Ngay cả khi dùng ORM/query builder, cần kiểm tra SQL thực tế mà thư viện tạo ra: abstraction có thể giảm khác biệt, nhưng không xóa mọi giới hạn của DBMS.

## 9. Quy trình đánh giá tính khả chuyển trước khi chuyển DBMS

### Bước 1 — Chốt phạm vi hỗ trợ

Ghi rõ **tên DBMS, phiên bản, driver và cấu hình quan trọng**. Ví dụ “hỗ trợ PostgreSQL và SQL Server” còn quá chung chung nếu chưa nêu phiên bản và collation, timezone, SQL mode hay tùy chọn ràng buộc liên quan.

### Bước 2 — Lập bảng kiểm kê tính năng SQL đang dùng

Tìm các điểm có rủi ro cao:

- LIMIT, TOP, OFFSET/FETCH, cách phân trang.
- AUTO_INCREMENT, IDENTITY, sequence, lấy khóa vừa sinh.
- UPSERT, MERGE, RETURNING/OUTPUT.
- Hàm chuỗi, JSON, ngày giờ, so khớp văn bản, tìm kiếm toàn văn.
- DDL migration, computed/generated column, index đặc biệt.
- Câu SQL trong stored procedure, trigger, view hoặc truy vấn tự viết trong ứng dụng.

### Bước 3 — Phân loại và quyết định giải pháp

Với mỗi tính năng, chọn một trong ba cách:

1. **Giữ nguyên** nếu đã kiểm chứng chạy đúng trên mọi DBMS mục tiêu.
2. **Chuyển thành biểu thức chung** khi có cách viết tương đương rõ ràng.
3. **Tách thành biến thể theo DBMS** khi cú pháp hoặc hành vi không thể đồng nhất an toàn.

Không cố thay thế các chức năng chỉ trông giống nhau về tên. Với UPSERT, ngày giờ, JSON và collation, phải kiểm tra cả ý nghĩa.

### Bước 4 — Kiểm thử trên DBMS thật

Một bài kiểm thử chỉ chạy trên SQLite **không đủ** để xác nhận câu lệnh hoạt động trên PostgreSQL hoặc SQL Server. Kiểm thử tích hợp cần chạy trên đúng DBMS mục tiêu với bộ dữ liệu thể hiện:

- Dòng không có dữ liệu liên quan, NULL, chuỗi rỗng, ký tự Unicode và tên tiếng Việt.
- Giá trị trùng nhau khi ORDER BY, nhiều trang dữ liệu và ghi/xóa giữa các lần đọc.
- Giá trị số ở ranh giới precision/scale và thời điểm biên theo múi giờ.
- Xung đột khóa UNIQUE, cập nhật đồng thời, rollback và lỗi giữa giao dịch.
- Kiểm tra ràng buộc FK/CHECK/UNIQUE và migration.

So sánh **kết quả có ý nghĩa nghiệp vụ**, không chỉ so chuỗi thông báo hoặc kế hoạch thực thi. Ngoài tính đúng đắn, đo thêm thời gian chạy và kiểm tra chỉ mục với dữ liệu đủ lớn.

### Bước 5 — Duy trì hợp đồng tương thích

Đưa các hệ DBMS được hỗ trợ vào kiểm thử định kỳ/CI khi khả thi. Mỗi khi thêm tính năng SQL mới hoặc nâng phiên bản driver/DBMS, kiểm tra lại các câu liên quan. Nếu một tính năng chỉ hoạt động trên một hệ, ghi rõ đó là lựa chọn kiến trúc để người bảo trì biết phạm vi tương thích.

## 10. Những ngộ nhận thường gặp

| Ngộ nhận | Điều cần hiểu |
|---|---|
| “Mọi hệ hỗ trợ SQL nên câu lệnh nào cũng chạy được.” | Mỗi hệ triển khai tập chuẩn và phần mở rộng riêng. |
| “Nếu câu lệnh chạy thành công thì kết quả chắc chắn giống nhau.” | NULL, ép kiểu, collation, timezone và ràng buộc có thể đổi kết quả. |
| “Có ORDER BY trong truy vấn con thì kết quả ngoài cùng cũng đã được sắp xếp.” | Muốn cam kết thứ tự đầu ra, đặt ORDER BY tại truy vấn ngoài cùng. |
| “LIMIT 10 luôn lấy cùng 10 dòng.” | Không có thứ tự xác định, 10 dòng được chọn có thể thay đổi. |
| “Dùng JDBC/ORM là xong việc chuyển DBMS.” | API truy cập chung không tự chuẩn hóa SQL, schema hoặc hành vi giao dịch. |
| “Tên kiểu dữ liệu giống nhau thì kiểu dữ liệu tương đương.” | Precision, range, NULL, múi giờ và quy tắc ép kiểu cần được kiểm tra. |
| “Bật chế độ tương thích là mọi khác biệt đều biến mất.” | Chế độ cấu hình chỉ điều chỉnh một phần hành vi và có thể kéo theo rủi ro mới. |
| “Viết theo chuẩn là sẽ nhanh trên mọi hệ.” | Khả chuyển cú pháp không đồng nghĩa tối ưu hiệu năng. |

## 11. Bài tập tự luyện

### Bài 1 — Phân biệt chuẩn và phương ngữ

Một thành viên nhóm nói: “Truy vấn của chúng ta dùng TOP, như vậy đây không còn là SQL nữa”.

**Câu hỏi:** Phát biểu đó đúng hay sai? Tại sao?

<details>
<summary>Gợi ý đáp án</summary>

Sai. Đây vẫn là câu lệnh SQL, nhưng sử dụng cú pháp TOP thuộc phương ngữ SQL Server. Từ “SQL” chỉ ngôn ngữ chung; phương ngữ mô tả những biến thể theo sản phẩm.
</details>

### Bài 2 — NULL

Tìm khách hàng chưa cung cấp email. Truy vấn sau có đúng không?

~~~sql
SELECT ma_khach_hang
FROM khach_hang
WHERE email = NULL;
~~~

<details>
<summary>Gợi ý đáp án</summary>

Không. Cần dùng:

~~~sql
SELECT ma_khach_hang
FROM khach_hang
WHERE email IS NULL;
~~~
</details>

### Bài 3 — LEFT JOIN

Một báo cáo phải hiển thị **tất cả** khách hàng đang hoạt động, kể cả người chưa mua hàng. Phần nào của truy vấn sau làm mất khách chưa mua?

~~~sql
SELECT k.ma_khach_hang, COUNT(d.ma_don_hang) AS so_don
FROM khach_hang k
LEFT JOIN don_hang d
    ON d.ma_khach_hang = k.ma_khach_hang
WHERE k.trang_thai = 'ACTIVE'
  AND d.trang_thai = 'PAID'
GROUP BY k.ma_khach_hang;
~~~

<details>
<summary>Gợi ý đáp án</summary>

Điều kiện d.trang_thai = 'PAID' trong WHERE loại cả các dòng NULL do LEFT JOIN tạo ra. Chuyển điều kiện trạng thái đơn sang ON, giữ điều kiện trạng thái khách hàng trong WHERE.
</details>

### Bài 4 — Chuyển phân trang

Viết lại ý tưởng “lấy 10 khách hàng tiếp theo sau 20 dòng đầu” cho SQL Server, biết cần sắp xếp tăng dần theo khóa ma_khach_hang.

<details>
<summary>Gợi ý đáp án</summary>

~~~sql
SELECT ma_khach_hang, ten_khach_hang
FROM khach_hang
ORDER BY ma_khach_hang
OFFSET 20 ROWS FETCH NEXT 10 ROWS ONLY;
~~~

Cú pháp trên dùng được trong các phiên bản SQL Server hỗ trợ OFFSET/FETCH và cần ORDER BY.
</details>

### Bài 5 — Đánh giá khả chuyển

Một ứng dụng chuyển từ MySQL sang PostgreSQL. Truy vấn cũ dùng CONCAT(), cột cờ trạng thái khai báo BOOLEAN, bảng có AUTO_INCREMENT và có ON DUPLICATE KEY UPDATE.

**Câu hỏi:** Phần nào chỉ cần xem lại cú pháp; phần nào cần kiểm tra thêm ngữ nghĩa và dữ liệu?

<details>
<summary>Gợi ý đáp án</summary>

Cả bốn phần đều phải kiểm tra. Ghép chuỗi cần xét quy tắc NULL, kiểu trả về; BOOLEAN trong MySQL là bí danh kiểu số, còn PostgreSQL có kiểu boolean; AUTO_INCREMENT chuyển sang identity/sequence và phải kiểm tra cấp phát/lấy khóa; ON DUPLICATE KEY UPDATE khác ON CONFLICT cả cú pháp và phạm vi khóa duy nhất kích hoạt cập nhật. Không thể chỉ tìm và thay các từ khóa trong file SQL.
</details>

## 12. Ghi nhớ và tài liệu đối chiếu

- **SQL chuẩn** tạo ngôn ngữ chung; **phương ngữ** và **triển khai** quyết định câu lệnh nào thực sự chạy trên DBMS, phiên bản và cấu hình cụ thể.
- **Khả chuyển** phải xét cú pháp, ngữ nghĩa, ràng buộc, giao dịch, dữ liệu đầu ra và hiệu năng.
- Các cấu trúc như SELECT, WHERE, JOIN, GROUP BY, CASE, COALESCE và EXISTS thường là nền tảng tốt để viết truy vấn đa DBMS, nhưng vẫn cần kiểm thử.
- Các điểm thường cần xử lý theo DBMS gồm **phân trang, khóa tự sinh, UPSERT/MERGE, hàm chuỗi/ngày giờ, kiểu dữ liệu, collation và DDL**.
- Với dự án thực tế, hãy xác định rõ **những DBMS và phiên bản được hỗ trợ**, cô lập tính năng theo phương ngữ và kiểm thử trực tiếp trên các hệ đó.

Khi cần xác minh một cú pháp hoặc hành vi cụ thể, nên đối chiếu **ISO/IEC 9075** cùng tài liệu SQL chính thức của đúng sản phẩm và phiên bản: PostgreSQL Documentation, MySQL Reference Manual, Microsoft Learn (Transact-SQL), Oracle Database SQL Language Reference và SQLite Documentation. Bảng so sánh trong bài mang tính học tập; tài liệu phiên bản của DBMS là nguồn quyết định cho triển khai thực tế.

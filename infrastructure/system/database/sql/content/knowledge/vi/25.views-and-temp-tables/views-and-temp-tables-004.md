# Điều kiện cập nhật qua view theo hệ quản trị trong SQL

> **Module:** Database SQL  
> **Chương:** View và bảng trung gian  
> **Bài học:** Điều kiện cập nhật qua view theo hệ quản trị

Một **view** là đối tượng SQL trình bày dữ liệu qua một truy vấn SELECT được đặt tên. View giúp đơn giản hóa truy vấn, ẩn một phần cấu trúc bảng, cung cấp giao diện dữ liệu cho ứng dụng và kiểm soát cách người dùng tiếp cận dữ liệu. Nhưng khi viết lệnh UPDATE, INSERT hoặc DELETE trực tiếp **trên view**, một câu hỏi xuất hiện:

**Thay đổi một hàng trong kết quả SELECT của view có được hệ quản trị chuyển thành thay đổi rõ ràng, hợp lệ ở bảng gốc hay không?**

Không phải view nào cũng cập nhật được. Một view chỉ lọc các cột từ một bảng thường có khả năng cập nhật tự động; view tổng hợp theo phòng ban, nối nhiều bảng, tính cột mới hoặc hợp nhiều tập dữ liệu lại có thể không cập nhật trực tiếp được. Quan trọng hơn, **PostgreSQL, MySQL, SQL Server, Oracle và SQLite không áp dụng một quy tắc và cú pháp duy nhất**.

Bài học này giải thích điều kiện **updatable view**, vai trò của **WITH CHECK OPTION**, cơ chế **INSTEAD OF trigger**, khả năng cập nhật qua view có JOIN, cách xử lý quyền và ràng buộc, cùng những ví dụ theo hệ quản trị và bài tập thực hành.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **bảng gốc**, **view thông thường**, **materialized/indexed view** và **bảng trung gian**.
- Giải thích “**view có thể cập nhật**” là khả năng chuyển DML trên view thành DML trên bảng thực, không phải thuộc tính hiển nhiên của mọi SELECT.
- Dự đoán một view đơn giản từ **một bảng, các cột trực tiếp** thường có khả năng UPDATE tự động khi nào.
- Nhận biết những cấu trúc gây hạn chế: **GROUP BY, aggregate, DISTINCT, UNION, JOIN, cột tính toán, window function, LIMIT/TOP** và các phép biến đổi khác.
- Phân biệt khả năng **UPDATE**, **INSERT**, **DELETE** vì một view có thể cho phép thao tác này nhưng không cho phép thao tác khác.
- Sử dụng **WITH CHECK OPTION** để ngăn cập nhật/chèn làm một hàng không còn thỏa bộ lọc của view.
- Phân biệt **LOCAL** và **CASCADED CHECK OPTION** ở hệ có hỗ trợ.
- Mô tả cách triển khai DML thông qua **INSTEAD OF trigger** khi view không tự động cập nhật được.
- So sánh quy tắc của **PostgreSQL, MySQL, SQL Server, Oracle Database và SQLite**.
- Phân tích ảnh hưởng của **khóa chính, khóa ngoại, NOT NULL, CHECK, quyền truy cập, trigger và transaction**.
- Viết truy vấn an toàn từ Java/JDBC, kiểm tra số hàng tác động và xử lý concurrency.
- Thiết kế bộ kiểm thử để xác định một view có thể sửa cột nào, dưới điều kiện nào và có bảo toàn dữ liệu không.

## 2. View là gì? Nó không nhất thiết chứa bản sao dữ liệu

Giả sử bảng **nhan_vien** lưu tất cả nhân viên. Ta tạo view chỉ hiển thị nhân viên đang hoạt động:

~~~sql
CREATE VIEW v_nhan_vien_active AS
SELECT
    ma_nv,
    ten_nv,
    ma_phong,
    luong,
    trang_thai
FROM nhan_vien
WHERE trang_thai = 'ACTIVE';
~~~

Truy vấn:

~~~sql
SELECT ma_nv, ten_nv, luong
FROM v_nhan_vien_active
ORDER BY ma_nv;
~~~

về mặt logic hiển thị các dòng thỏa điều kiện từ bảng gốc. Với **view thông thường**, kết quả được xác định từ dữ liệu nền tại thời điểm thực thi (trong ngữ cảnh transaction/snapshot của DBMS), chứ không phải một bản sao vật lý độc lập luôn được giữ trong view.

Khi viết:

~~~sql
UPDATE v_nhan_vien_active
SET luong = luong + 1000000
WHERE ma_nv = 101;
~~~

DBMS phải xác định **hàng của bảng nhan_vien nào** tương ứng với hàng được chọn trong view. Nếu ánh xạ rõ ràng, hệ quản trị có thể áp UPDATE vào bảng gốc.

### 2.1. Những gì UPDATE qua view không làm

- Không tạo một “bản sao” của nhân viên chỉ bên trong view.
- Không tự thay đổi định nghĩa câu SELECT của view.
- Không tự bảo đảm dữ liệu vẫn thỏa điều kiện WHERE của view, trừ khi có **CHECK OPTION** hoặc ràng buộc tương đương.
- Không bỏ qua NOT NULL, CHECK, UNIQUE, FOREIGN KEY và trigger của bảng gốc.
- Không tự cấp quyền thay đổi dữ liệu nếu cơ chế bảo mật không cho phép.

**DML qua view là DML tới dữ liệu thực**, nếu DBMS và định nghĩa view cho phép.

## 3. Chuẩn bị bảng ví dụ

Các ví dụ khái niệm dùng hai bảng:

~~~sql
CREATE TABLE phong_ban (
    ma_phong VARCHAR(20) PRIMARY KEY,
    ten_phong VARCHAR(100) NOT NULL
);

CREATE TABLE nhan_vien (
    ma_nv INTEGER PRIMARY KEY,
    ten_nv VARCHAR(100) NOT NULL,
    ma_phong VARCHAR(20),
    luong DECIMAL(14, 2) NOT NULL,
    trang_thai VARCHAR(20) NOT NULL,
    ngay_vao DATE,
    CONSTRAINT fk_nv_phong
        FOREIGN KEY (ma_phong) REFERENCES phong_ban(ma_phong),
    CONSTRAINT ck_luong
        CHECK (luong >= 0)
);
~~~

Bảng dữ liệu giả định:

| ma_nv | ten_nv | ma_phong | luong | trang_thai |
|---:|---|---|---:|---|
| 101 | An | IT | 12000000 | ACTIVE |
| 102 | Bình | IT | 15000000 | ACTIVE |
| 103 | Chi | HR | 11000000 | INACTIVE |
| 104 | Dũng | HR | 13000000 | ACTIVE |
| 105 | Hà | NULL | 10000000 | ACTIVE |

Và phòng ban:

| ma_phong | ten_phong |
|---|---|
| IT | Công nghệ |
| HR | Nhân sự |

Một số DBMS có khác biệt về tên kiểu, identity, khóa, DDL và transaction. Mục tiêu bảng trên là làm rõ quan hệ dữ liệu. Khi thực hành, hãy dùng cơ sở dữ liệu **thử nghiệm** và xác định chính xác phiên bản đang chạy.

**Quy ước bài học:** Các ví dụ UPDATE thường được diễn giải độc lập dựa trên dữ liệu ban đầu, trừ khi có ghi chú về chuỗi thay đổi.

## 4. Ba câu hỏi cần phân biệt khi DML qua view

Khi nói “view cập nhật được”, cần tách ba khả năng:

1. **UPDATE** — thay giá trị của hàng gốc được view hiển thị.
2. **INSERT** — thêm hàng qua view sao cho DBMS biết đủ cột cần thiết ở bảng gốc.
3. **DELETE** — xóa hàng gốc tương ứng với một dòng trong view.

Một view có thể **UPDATE được một số cột** nhưng **không INSERT được** vì không hiển thị một cột bắt buộc, không có DEFAULT ở bảng gốc.

Ví dụ: view chỉ gồm **ma_nv, ten_nv** của bảng nhan_vien, nhưng bảng gốc bắt buộc **luong NOT NULL**, **trang_thai NOT NULL**. Nếu hai cột bắt buộc không có DEFAULT, INSERT thông qua view chỉ cung cấp ma_nv, ten_nv có thể thất bại dù UPDATE ten_nv thành công.

Tương tự, một cột tính toán trong view có thể **đọc được** nhưng **không phải mục tiêu của SET**.

### 4.1. “Updatable view” không có nghĩa mọi thao tác đều hợp lệ

Hãy xét riêng:

- View có hỗ trợ UPDATE không?
- Cột **luong** có thể sửa không?
- View có hỗ trợ INSERT không?
- Có thể thêm hàng với các cột hiện có không?
- DELETE có được phép không?
- Có constraint, trigger hoặc quyền nào tiếp tục hạn chế không?

Không nên dùng câu “view này updatable” như cam kết mọi DML đều thành công.

## 5. Điều kiện cốt lõi: ánh xạ một hàng view tới hàng gốc

Trong dạng đơn giản nhất, DBMS có thể tự cập nhật nếu:

- View tham chiếu đến **một bảng** hoặc một view nền mà DBMS biết cách cập nhật.
- Một dòng của view tương ứng với **một dòng xác định** ở bảng gốc.
- Những cột muốn SET là **tham chiếu trực tiếp** tới cột có thể cập nhật của bảng gốc.
- Định nghĩa view không có những phép biến đổi khiến kết quả không thể ánh xạ ngược một cách rõ ràng.
- Bảng nền và giao dịch cho phép thao tác.

Ví dụ dễ hiểu:

~~~sql
CREATE VIEW v_luong_active AS
SELECT ma_nv, ten_nv, luong, trang_thai
FROM nhan_vien
WHERE trang_thai = 'ACTIVE';
~~~

Nếu DBMS hỗ trợ **simple auto-updatable view**, có thể:

~~~sql
UPDATE v_luong_active
SET luong = 14000000
WHERE ma_nv = 101;
~~~

Hàng 101 ở bảng nhan_vien đổi lương, view sau đó phản ánh giá trị mới.

### 5.1. Khả năng ánh xạ không chỉ là “có khóa chính trong SELECT”

Một số hệ có thể cập nhật cột trực tiếp của view đơn giản dù khóa chính không hiện diện trong danh sách SELECT, vì DBMS vẫn hiểu các dòng nền trong kế hoạch thực thi. Nhưng trong thiết kế ứng dụng, đưa **định danh ổn định** vào view thường tốt để viết WHERE an toàn và kiểm tra đúng hàng.

Ở view có JOIN, tình huống phức tạp hơn: một nhân viên có thể xuất hiện nhiều lần nếu bảng nguồn bên kia không có quan hệ một–một; khi đó ánh xạ và điều kiện cập nhật sẽ có hạn chế theo từng DBMS.

## 6. Cập nhật qua view có WHERE

Xét:

~~~sql
CREATE VIEW v_nhan_vien_active AS
SELECT ma_nv, ten_nv, ma_phong, luong, trang_thai
FROM nhan_vien
WHERE trang_thai = 'ACTIVE';
~~~

Câu:

~~~sql
UPDATE v_nhan_vien_active
SET luong = luong + 1000000
WHERE ma_phong = 'IT';
~~~

về ý nghĩa cập nhật các hàng:

~~~text
trang_thai = 'ACTIVE'
AND ma_phong = 'IT'
~~~

ở bảng gốc, giả sử DBMS cho phép cập nhật view.

Dữ liệu ban đầu: An và Bình đủ điều kiện; Chi không vì INACTIVE, Dũng không vì HR.

### 6.1. Hai tầng điều kiện

Có thể hình dung:

~~~text
Điều kiện thuộc view: trang_thai = 'ACTIVE'
Điều kiện của UPDATE: ma_phong = 'IT'
Hai điều kiện cùng chọn các hàng đích
~~~

Nhưng cách DBMS viết lại câu lệnh, áp quyền và xử lý trigger là chi tiết sản phẩm. Đây là **ngữ nghĩa logic**, không phải cam kết kế hoạch thực thi.

### 6.2. UPDATE hàng không xuất hiện trong view

~~~sql
UPDATE v_nhan_vien_active
SET luong = 17000000
WHERE ma_nv = 103;
~~~

Nhân viên 103 đang INACTIVE nên không có trong view. Trong cơ chế view đơn giản, câu lệnh sẽ không chọn hàng 103 để sửa. Nó **không tự nhìn xuyên qua điều kiện view** chỉ vì bạn biết khóa của hàng nền.

### 6.3. UPDATE không có WHERE vẫn nguy hiểm

~~~sql
UPDATE v_nhan_vien_active
SET luong = luong * 1.10;
~~~

có thể tăng lương **tất cả nhân viên ACTIVE** được view hiển thị, chứ không chỉ một người. Điều kiện WHERE nằm trong định nghĩa view không thay thế việc giới hạn **phạm vi nghiệp vụ** của lệnh UPDATE.

## 7. Một hàng có thể “biến mất” khỏi view sau UPDATE

Giả sử view hiển thị người ACTIVE:

~~~sql
CREATE VIEW v_active AS
SELECT ma_nv, ten_nv, trang_thai
FROM nhan_vien
WHERE trang_thai = 'ACTIVE';
~~~

Với hệ cho phép UPDATE view đơn giản:

~~~sql
UPDATE v_active
SET trang_thai = 'INACTIVE'
WHERE ma_nv = 101;
~~~

Nếu view **không có WITH CHECK OPTION**, nhiều DBMS có thể chấp nhận cập nhật này. Hàng nền 101 trở thành INACTIVE và **không còn xuất hiện** trong lần SELECT tiếp theo từ v_active.

Đây không nhất thiết là lỗi; có hệ thống cố ý dùng view để xử lý chuyển trạng thái. Nhưng khi view được sử dụng như **giao diện chỉ cho phép thao tác lên những hàng vẫn thuộc tập ACTIVE**, hành vi này có thể vi phạm quy tắc.

Giải pháp SQL thường dùng: **WITH CHECK OPTION**.

## 8. WITH CHECK OPTION: giữ hàng mới trong phạm vi view

Mẫu tổng quát:

~~~sql
CREATE VIEW v_active_checked AS
SELECT ma_nv, ten_nv, trang_thai, luong
FROM nhan_vien
WHERE trang_thai = 'ACTIVE'
WITH CHECK OPTION;
~~~

Trong DBMS hỗ trợ cú pháp và view này có thể cập nhật, CHECK OPTION buộc giá trị **sau INSERT/UPDATE qua view** tiếp tục thỏa bộ lọc của view.

Ví dụ hợp lệ:

~~~sql
UPDATE v_active_checked
SET luong = luong + 1000000
WHERE ma_nv = 101;
~~~

Hàng vẫn ACTIVE nên được phép, nếu các ràng buộc khác thỏa.

Ví dụ không hợp lệ:

~~~sql
UPDATE v_active_checked
SET trang_thai = 'INACTIVE'
WHERE ma_nv = 101;
~~~

Vì hàng mới sẽ không thỏa **trang_thai = 'ACTIVE'**, DBMS áp CHECK OPTION sẽ **từ chối** thao tác.

### 8.1. CHECK OPTION áp dụng cho hàng mới, không chỉ hàng cũ

Khi UPDATE một view, DBMS đã biết hàng cũ thuộc tập view. CHECK OPTION kiểm tra **trạng thái hàng sau thay đổi** có còn thuộc view hay không.

Nếu điều kiện view là:

~~~sql
WHERE trang_thai = 'ACTIVE'
  AND luong >= 10000000
~~~

thì hạ lương một người xuống 9000000 cũng có thể bị CHECK OPTION từ chối, vì người đó sẽ không còn thỏa view dù trạng thái vẫn ACTIVE.

### 8.2. CHECK OPTION có xét NULL

Trong SQL, điều kiện:

~~~sql
WHERE trang_thai = 'ACTIVE'
~~~

chỉ chọn TRUE. Nếu SET trang_thai = NULL, điều kiện là UNKNOWN, không thể tiếp tục thuộc view. CHECK OPTION không coi UNKNOWN là TRUE. Ngoài ra, cột bảng gốc có thể bị NOT NULL từ chối trước hoặc trong cùng phép thao tác.

### 8.3. CHECK OPTION không làm view phức tạp tự trở thành updatable

Thêm CHECK OPTION **không thể** biến một view GROUP BY, UNION hay tính toán tùy ý thành view tự động cập nhật được. Nó là **điều kiện kiểm tra bổ sung** cho DML được phép, không phải bộ chuyển đổi truy vấn tổng hợp thành UPDATE.

### 8.4. CHECK OPTION không áp dụng như bộ lọc DELETE

DELETE xóa hàng thay vì tạo một trạng thái mới cần vẫn nằm trong view. Do đó CHECK OPTION chủ yếu kiểm soát **INSERT/UPDATE**, không tự biến mọi DELETE qua view thành thao tác bị cấm. Muốn cấm DELETE, cần dùng quyền, trigger hoặc quy tắc phù hợp.

## 9. LOCAL và CASCADED CHECK OPTION ở những hệ hỗ trợ

Một số DBMS, nổi bật là **PostgreSQL** và **MySQL**, cho phép hai phạm vi:

- **LOCAL CHECK OPTION**: kiểm tra điều kiện tại lớp view hiện tại, theo quy tắc của DBMS và các CHECK OPTION đã có ở lớp dưới.
- **CASCADED CHECK OPTION**: kiểm tra cả điều kiện của view hiện tại **và các view nền liên quan** có khả năng cập nhật, theo quy tắc cụ thể của DBMS.

Ví dụ nhiều lớp:

~~~sql
CREATE VIEW v_luong_cao AS
SELECT ma_nv, ten_nv, luong, trang_thai
FROM nhan_vien
WHERE luong >= 15000000;

CREATE VIEW v_luong_cao_active AS
SELECT ma_nv, ten_nv, luong, trang_thai
FROM v_luong_cao
WHERE trang_thai = 'ACTIVE'
WITH CASCADED CHECK OPTION;
~~~

Giả sử Bình đang ACTIVE và lương 15000000. Nếu UPDATE qua v_luong_cao_active giảm lương xuống 12000000, hàng sẽ không còn thuộc **v_luong_cao**. Với CASCADED CHECK OPTION được hỗ trợ và áp dụng đầy đủ, cập nhật bị chặn.

### 9.1. LOCAL có thể cho kết quả khác

Nếu view trên chỉ có:

~~~sql
WITH LOCAL CHECK OPTION
~~~

và view nền v_luong_cao **không có CHECK OPTION riêng**, phạm vi kiểm tra có thể tập trung vào điều kiện trực tiếp **trang_thai='ACTIVE'**, thay vì cưỡng chế điều kiện lương ở lớp dưới. Khi đó sự thay đổi lương có thể làm hàng ra khỏi lớp view nền nếu điều kiện khác và cơ chế cập nhật cho phép.

**Lưu ý:** Cú pháp LOCAL/CASCADED và cách lan truyền qua view trigger-updatable, view không tự cập nhật hoặc các lớp có CHECK OPTION riêng có ngoại lệ theo DBMS. Không lấy ví dụ LOCAL ở PostgreSQL áp dụng nguyên văn cho Oracle/SQL Server/SQLite.

### 9.2. Default không được đoán

PostgreSQL và MySQL thường dùng ngữ nghĩa **CASCADED** khi có CHECK OPTION nhưng không chỉ rõ LOCAL/CASCADED; hãy xác minh theo tài liệu phiên bản. Một view **không ghi CHECK OPTION** không vì thế mặc định buộc giữ mọi hàng trong bộ lọc.

## 10. View chứa cột tính toán: có thể đọc nhưng không SET vào cột đó

Ví dụ:

~~~sql
CREATE VIEW v_bang_luong AS
SELECT
    ma_nv,
    ten_nv,
    luong,
    luong * 12 AS luong_nam
FROM nhan_vien;
~~~

Cột **luong** tham chiếu trực tiếp tới cột gốc. Cột **luong_nam** là biểu thức.

~~~sql
SELECT ma_nv, luong, luong_nam
FROM v_bang_luong;
~~~

dùng để xem dữ liệu.

Trong nhiều DBMS, câu:

~~~sql
UPDATE v_bang_luong
SET luong = 16000000
WHERE ma_nv = 101;
~~~

có thể hợp lệ nếu view đáp ứng điều kiện cập nhật tự động.

Nhưng:

~~~sql
UPDATE v_bang_luong
SET luong_nam = 192000000
WHERE ma_nv = 101;
~~~

không có ánh xạ trực tiếp “gán luong_nam” về bảng gốc. DBMS không tự biết bạn muốn đặt luong = 16000000, hay thay công thức, hay lưu thêm cột mới. Trong những hệ hỗ trợ cập nhật cột trực tiếp, cột tính toán vẫn thường **read-only**.

### 10.1. Alias không làm cột thành không cập nhật được

~~~sql
CREATE VIEW v_luong_alias AS
SELECT ma_nv AS id, luong AS muc_luong
FROM nhan_vien;
~~~

Cột **muc_luong** chỉ là tên khác cho cột luong, vẫn có ánh xạ trực tiếp. Hệ hỗ trợ simple view có thể chấp nhận:

~~~sql
UPDATE v_luong_alias
SET muc_luong = 14000000
WHERE id = 101;
~~~

Khác với **luong * 12**, một biểu thức phái sinh.

### 10.2. Hàm tạo cột mới cũng thường read-only

Các cột:

~~~sql
UPPER(ten_nv) AS ten_in_hoa
ROUND(luong / 1000000, 2) AS luong_trieu
CASE WHEN luong > 15000000 THEN 'CAO' ELSE 'KHAC' END AS nhom
~~~

là biểu thức. Muốn cập nhật bản gốc, thường phải sửa cột trực tiếp hoặc dùng trigger/procedure xác định quy tắc ánh xạ ngược.

## 11. DISTINCT làm mất mối quan hệ một hàng–một hàng

Giả sử:

~~~sql
CREATE VIEW v_phong_co_nhan_vien AS
SELECT DISTINCT ma_phong
FROM nhan_vien;
~~~

Mỗi ma_phong có thể đại diện cho hàng chục nhân viên.

Câu:

~~~sql
UPDATE v_phong_co_nhan_vien
SET ma_phong = 'SALES'
WHERE ma_phong = 'IT';
~~~

không thể tự suy ra phải sửa **một**, **mười** hay **toàn bộ** nhân viên IT. DISTINCT đã loại thông tin phân biệt các hàng gốc. Các DBMS thông thường **không tự động cập nhật dạng view này**.

DISTINCT dù kết quả hiện tại tình cờ một dòng/giá trị cũng không làm định nghĩa view trở thành phép ánh xạ an toàn nói chung.

## 12. GROUP BY, aggregate và HAVING thường không thể UPDATE tự động

~~~sql
CREATE VIEW v_tong_luong_phong AS
SELECT
    ma_phong,
    COUNT(*) AS so_nhan_vien,
    SUM(luong) AS tong_luong,
    AVG(luong) AS luong_binh_quan
FROM nhan_vien
GROUP BY ma_phong;
~~~

View trả một hàng mỗi phòng. Nếu:

~~~sql
UPDATE v_tong_luong_phong
SET tong_luong = 50000000
WHERE ma_phong = 'IT';
~~~

DBMS không biết nên:

- Tăng lương tất cả nhân viên đều nhau?
- Sửa lương của một người?
- Chia thêm theo hệ số?
- Thêm nhân viên?
- Đổi trạng thái và phạm vi tính tổng?

Không có phép ánh xạ ngược tổng quát từ **SUM** về các dòng gốc. View có GROUP BY, aggregate, HAVING, window function hoặc các phép tạo kết quả tổng hợp thường **không tự động cập nhật được**.

### 12.1. HAVING cũng là chỉ dấu

~~~sql
SELECT ma_phong, AVG(luong) AS avg_luong
FROM nhan_vien
GROUP BY ma_phong
HAVING AVG(luong) > 12000000;
~~~

Các dòng kết quả là nhóm, không còn tương ứng đơn giản với một dòng gốc.

### 12.2. Nếu cần cập nhật theo tổng hợp

Có thể dùng aggregate trong **điều kiện/nguồn tính toán** của UPDATE lên bảng gốc, theo cú pháp DBMS, nhưng điều đó khác với cập nhật trực tiếp một cột aggregate của view.

Ví dụ muốn tăng lương những nhân viên thuộc phòng có mức lương bình quân thấp, có thể viết một UPDATE bảng gốc kết hợp subquery GROUP BY sau khi định nghĩa rõ chính sách; không gán trực tiếp avg_luong của view rồi mong SQL tự phân bổ.

## 13. UNION, INTERSECT, EXCEPT và phép tập hợp

Giả sử:

~~~sql
CREATE VIEW v_nhan_su_ghep AS
SELECT ma_nv, ten_nv FROM nhan_vien_chinh
UNION ALL
SELECT ma_nv, ten_nv FROM nhan_vien_thoi_vu;
~~~

Một dòng kết quả có thể đến từ một trong hai bảng. Nếu ma_nv trùng, từ view không chắc chắn có thể xác định bảng nào phải sửa. UNION/UNION ALL thường làm view không tự động cập nhật được trong những DBMS phổ biến.

Tương tự, INTERSECT và EXCEPT tạo tập kết quả dựa trên phép toán tập hợp, không có ánh xạ ngược tổng quát.

### 13.1. UNION ALL không giải quyết tự động ánh xạ

Dù UNION ALL giữ các dòng trùng thay vì loại như UNION, DBMS vẫn cần biết **bảng đích nào** cho mỗi hàng. Một cột “nguon” nếu thêm vào SELECT có thể giúp một **INSTEAD OF trigger** tự quyết định bảng nền, nhưng không có nghĩa engine sẽ tự biến view thành updatable.

## 14. JOIN: một bài toán quan trọng và có khác biệt theo DBMS

Xét:

~~~sql
CREATE VIEW v_nhan_vien_phong AS
SELECT
    n.ma_nv,
    n.ten_nv,
    n.luong,
    n.trang_thai,
    p.ma_phong,
    p.ten_phong
FROM nhan_vien n
JOIN phong_ban p
  ON p.ma_phong = n.ma_phong;
~~~

Câu:

~~~sql
UPDATE v_nhan_vien_phong
SET luong = 16000000
WHERE ma_nv = 101;
~~~

**Có thể** được hỗ trợ trực tiếp ở một số hệ nếu đáp ứng quy tắc **chỉ sửa một bảng gốc**, phép JOIN và ràng buộc đảm bảo ánh xạ. Nhưng không nên kết luận view có JOIN luôn cập nhật được.

### 14.1. Phân biệt sửa một bảng và sửa hai bảng

Sửa cột luong thuộc **nhan_vien** có một hướng ánh xạ hợp lý.

Nhưng:

~~~sql
UPDATE v_nhan_vien_phong
SET luong = 16000000,
    ten_phong = 'Kỹ thuật'
WHERE ma_nv = 101;
~~~

muốn cập nhật **nhan_vien** lẫn **phong_ban**. Nhiều DBMS không cho một UPDATE qua view tự động sửa **hai bảng gốc** đồng thời. Cần các thao tác riêng trong transaction hoặc trigger/procedure quy định rõ.

### 14.2. Khóa bảo toàn (key preservation)

Ở Oracle, khái niệm **key-preserved table** rất quan trọng cho join view: những khóa của một bảng phải tiếp tục xác định duy nhất hàng tương ứng trong kết quả join theo quy tắc của Oracle. Ở các hệ khác, yêu cầu một–một và cập nhật một bảng cũng cần cân nhắc, dù thuật ngữ và kiểm tra khác.

Ví dụ phong_ban.ma_phong là PRIMARY KEY nên mỗi nhân viên có tối đa một phòng phù hợp. Tuy nhiên, nếu JOIN tới một bảng chi tiết có nhiều dòng cho mỗi nhân viên, cùng một nhân viên có thể xuất hiện nhiều dòng trong view:

~~~text
Nhan vien 101 -- Chi tiet A
Nhan vien 101 -- Chi tiet B
~~~

Khi đó việc cập nhật dựa trên hàng view có thể mơ hồ hoặc bị từ chối.

### 14.3. INNER JOIN khác OUTER JOIN

Một số DBMS hỗ trợ UPDATE qua view JOIN trong phạm vi nhất định, nhưng **OUTER JOIN** có hàng được bổ sung NULL ở một phía và ràng buộc updatability khác INNER JOIN. Không giả định chỉ cần hai bảng có khóa ngoại là mọi kiểu JOIN view đều sửa được.

## 15. Subquery, LIMIT, TOP, ORDER BY và window function

Những cấu trúc khác cũng cần thận trọng:

- **Subquery trong SELECT list**: cột trả về thường là biểu thức, không phải cột gốc cập nhật trực tiếp.
- **LIMIT/OFFSET** hoặc **TOP**: có thể khiến tập hàng view phụ thuộc thứ tự/giới hạn và làm view không tự động updatable theo DBMS.
- **Window function** như ROW_NUMBER, RANK, SUM OVER: kết quả tính toán phụ thuộc nhiều hàng; view chứa window function thường bị hạn chế.
- **ORDER BY** trong định nghĩa view: nhiều DBMS không cho hoặc không bảo đảm thứ tự khi SELECT view; có hệ cho trong một số ngữ cảnh, nhưng ORDER BY không tự xác định khả năng updatability.
- **LATERAL/APPLY** và table functions: ánh xạ DML có các giới hạn riêng.

### 15.1. Không chọn theo kết quả tính thứ tự rồi mặc định sửa được

~~~sql
CREATE VIEW v_xep_hang_luong AS
SELECT
    ma_nv,
    ten_nv,
    luong,
    ROW_NUMBER() OVER (ORDER BY luong DESC, ma_nv) AS hang_luong
FROM nhan_vien;
~~~

Cột hang_luong phụ thuộc vào toàn bảng. Không thể tự UPDATE hang_luong=1 để khiến một nhân viên trở thành người có lương cao nhất. Phải xác định một UPDATE lên bảng gốc và quy tắc nghiệp vụ riêng.

## 16. Khả năng cập nhật ở PostgreSQL

PostgreSQL hỗ trợ **automatically updatable views** cho các định nghĩa đủ đơn giản và các cơ chế DML khác cho view phức tạp.

Về nguyên tắc, một view tự động cập nhật thường cần:

- Một nguồn FROM có thể cập nhật theo quy định, thường là **một bảng hoặc view tự động cập nhật**.
- Không có DISTINCT, GROUP BY, HAVING, LIMIT, OFFSET và các phép tập hợp kiểu UNION/INTERSECT/EXCEPT.
- Không có aggregate, window functions hoặc set-returning functions trong danh sách SELECT theo quy tắc PostgreSQL.
- Cột được sửa là **tham chiếu đơn giản tới cột gốc**; cột biểu thức có thể đọc nhưng không SET trực tiếp.

Các hạn chế chính xác còn có chi tiết theo phiên bản. Với view JOIN, PostgreSQL không tự động cập nhật như simple view; có thể dùng **INSTEAD OF trigger** hoặc cơ chế rule phù hợp.

### 16.1. Ví dụ tạo view tự động updatable

~~~sql
CREATE VIEW v_pg_active AS
SELECT
    ma_nv, ten_nv, luong, trang_thai
FROM nhan_vien
WHERE trang_thai = 'ACTIVE'
WITH CASCADED CHECK OPTION;
~~~

Sau đó:

~~~sql
UPDATE v_pg_active
SET luong = luong + 500000
WHERE ma_nv = 101;
~~~

được chuyển tới bảng nhan_vien nếu thỏa điều kiện, quyền và constraint.

~~~sql
UPDATE v_pg_active
SET trang_thai = 'INACTIVE'
WHERE ma_nv = 101;
~~~

bị CHECK OPTION từ chối vì hàng mới không còn ACTIVE.

### 16.2. LOCAL và CASCADED

PostgreSQL hỗ trợ:

~~~sql
WITH LOCAL CHECK OPTION
~~~

và:

~~~sql
WITH CASCADED CHECK OPTION
~~~

ở phần định nghĩa view thích hợp. CASCADED là hướng kiểm tra các điều kiện qua lớp view nền tự động updatable, còn LOCAL tập trung vào view hiện tại và các check đã quy định. Có ngoại lệ với **INSTEAD OF trigger/rule** ở lớp view nền; không cho rằng CHECK OPTION tự lan tới mọi cơ chế viết lại.

### 16.3. Cột tính toán là read-only

~~~sql
CREATE VIEW v_pg_luong AS
SELECT
    ma_nv,
    luong,
    luong * 12 AS luong_nam
FROM nhan_vien;
~~~

UPDATE luong có thể được hỗ trợ; UPDATE luong_nam thường không, vì đó là biểu thức.

### 16.4. Kiểm tra metadata

PostgreSQL cung cấp thông tin qua **information_schema.views**, ví dụ thuộc tính **is_updatable**, cũng như metadata về cột và view definition. Các thông tin này giúp thăm dò khả năng tự động cập nhật nhưng **không thay thế việc kiểm tra quyền, constraint và trigger**.

## 17. PostgreSQL INSTEAD OF trigger cho view JOIN

Giả sử v_nhan_vien_phong có JOIN, và nghiệp vụ muốn chỉ cho đổi **luong** của nhân viên qua giao diện đó.

Một cách làm minh họa:

~~~sql
CREATE VIEW v_pg_nv_phong AS
SELECT
    n.ma_nv,
    n.ten_nv,
    n.luong,
    p.ten_phong
FROM nhan_vien n
JOIN phong_ban p
  ON p.ma_phong = n.ma_phong;
~~~

Tạo trigger function:

~~~sql
CREATE OR REPLACE FUNCTION fn_pg_doi_luong_qua_view()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.ma_nv IS DISTINCT FROM OLD.ma_nv
       OR NEW.ten_nv IS DISTINCT FROM OLD.ten_nv
       OR NEW.ten_phong IS DISTINCT FROM OLD.ten_phong
    THEN
        RAISE EXCEPTION
            'View nay chi cho phep thay doi luong';
    END IF;

    UPDATE nhan_vien
       SET luong = NEW.luong
     WHERE ma_nv = OLD.ma_nv;

    RETURN NEW;
END;
$$;
~~~

Gắn vào view:

~~~sql
CREATE TRIGGER trg_pg_doi_luong_qua_view
INSTEAD OF UPDATE ON v_pg_nv_phong
FOR EACH ROW
EXECUTE FUNCTION fn_pg_doi_luong_qua_view();
~~~

Sau đó:

~~~sql
UPDATE v_pg_nv_phong
SET luong = 16000000
WHERE ma_nv = 101;
~~~

gọi trigger thay vì kỳ vọng PostgreSQL tự sửa JOIN view.

**Điểm cần nhớ:** Đây là ví dụ định hướng. Trong production cần kiểm tra quyền chạy function, bảo vệ schema/search_path, xử lý row count nếu bản gốc bị xóa, kiểm soát trigger side effects và concurrency. Trigger phải xác định rõ các cột nào được phép, không âm thầm bỏ qua thay đổi trái chính sách.

### 17.1. RETURN NEW và kết quả thao tác

Trong PostgreSQL, một INSTEAD OF trigger row-level trả NEW hoặc NULL có thể ảnh hưởng cách DBMS coi hàng đã được xử lý và kết quả RETURNING. Không tùy tiện thay RETURN NEW bằng RETURN NULL nếu ứng dụng cần số hàng hoặc kết quả được báo chính xác.

### 17.2. CHECK OPTION và view xử lý bằng trigger

CHECK OPTION tự động không phải bộ kiểm soát đầy đủ cho mọi view được cập nhật bằng trigger. Nếu trigger cho phép thao tác vượt điều kiện hiển thị, bạn cần **thi hành quy tắc đó trong trigger/bảng gốc** hoặc qua cấu trúc view có hỗ trợ check chính xác. Tài liệu PostgreSQL có ngoại lệ khi cascade qua view xử lý bằng trigger/rule.

## 18. MySQL: view updatable và thuật toán MERGE/TEMPTABLE

MySQL hỗ trợ cập nhật một số view nếu chúng có thể được xử lý phù hợp, thường bằng thuật toán **MERGE** đối với view được phép. View dùng **TEMPTABLE** (vật hóa kết quả tạm cho truy vấn) thường **không updatable**.

Ví dụ:

~~~sql
CREATE VIEW v_mysql_active AS
SELECT ma_nv, ten_nv, luong, trang_thai
FROM nhan_vien
WHERE trang_thai = 'ACTIVE'
WITH CASCADED CHECK OPTION;
~~~

Ở phiên bản phù hợp, có thể:

~~~sql
UPDATE v_mysql_active
SET luong = luong + 500000
WHERE ma_nv = 101;
~~~

### 18.1. ALGORITHM=MERGE không có nghĩa là câu lệnh MERGE DML

Trong MySQL:

~~~sql
CREATE ALGORITHM=MERGE VIEW v_mysql_luong AS
SELECT ma_nv, luong
FROM nhan_vien;
~~~

**ALGORITHM=MERGE** là cách hệ xử lý truy vấn tới view, **không phải** câu lệnh SQL MERGE dùng để UPSERT. Đây là hai khái niệm khác nhau, dù đều có chữ MERGE.

MySQL còn có **ALGORITHM=UNDEFINED** và **ALGORITHM=TEMPTABLE**. Cách chọn thuật toán và tính updatable phụ thuộc cấu trúc view.

### 18.2. JOIN view có thể cập nhật hạn chế

MySQL có thể hỗ trợ UPDATE qua một số **multi-table views** nếu có thể xử lý bằng MERGE, thường với INNER JOIN và điều kiện ánh xạ phù hợp. Tuy nhiên, một UPDATE qua view chỉ được thay các cột thuộc **một bảng gốc** trong trường hợp cho phép; không được giả định có thể sửa hai bảng gốc cùng lúc.

Ví dụ sửa luong qua view JOIN có thể hợp lệ khi các điều kiện MySQL được đáp ứng, nhưng sửa đồng thời luong và ten_phong từ hai bảng thường không hợp lệ trong một UPDATE qua view.

### 18.3. Những cấu trúc thường cản trở

DISTINCT, GROUP BY, HAVING, aggregate, window functions, UNION, subquery trong select list, TEMPTABLE và một số JOIN/biểu thức có thể khiến view không updatable. MySQL có tập quy tắc riêng; không lấy danh sách PostgreSQL làm định nghĩa tuyệt đối cho MySQL.

### 18.4. CHECK OPTION và metadata

MySQL hỗ trợ **WITH LOCAL CHECK OPTION** và **WITH CASCADED CHECK OPTION** với view thích hợp. Có thể kiểm tra:

~~~sql
SELECT
    TABLE_NAME,
    IS_UPDATABLE,
    CHECK_OPTION
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'v_mysql_active';
~~~

Dữ liệu metadata cho biết khả năng và check option mà MySQL xác định; một câu UPDATE vẫn có thể thất bại vì quyền, ràng buộc hoặc điều kiện dữ liệu thực tế.

### 18.5. SQL SECURITY

MySQL hỗ trợ **SQL SECURITY DEFINER** và **SQL SECURITY INVOKER** cho view theo quy tắc quyền của DBMS. Một view updatable về mặt cấu trúc **không đồng nghĩa người gọi được quyền cập nhật**. Quyền thực thi và security context phải được thiết kế riêng.

## 19. SQL Server: cập nhật view trực tiếp trong giới hạn

SQL Server cho phép UPDATE thông qua view khi thao tác có thể chuyển xuống bảng gốc theo những hạn chế được tài liệu mô tả, bao gồm:

- Các cột được sửa phải tham chiếu trực tiếp đến cột gốc, không phải biểu thức phái sinh.
- Thao tác sửa thông qua view thường phải tác động **chỉ một bảng gốc** trong một câu lệnh.
- Một số cấu trúc aggregate, GROUP BY, DISTINCT, phép tập hợp và điều kiện khác không cho khả năng cập nhật thông thường.
- Có thể xử lý view phức tạp bằng **INSTEAD OF trigger** theo quy tắc.

### 19.1. Simple view và CHECK OPTION

~~~sql
CREATE VIEW dbo.v_sqlserver_active
AS
SELECT ma_nv, ten_nv, luong, trang_thai
FROM dbo.nhan_vien
WHERE trang_thai = 'ACTIVE'
WITH CHECK OPTION;
~~~

Ví dụ:

~~~sql
UPDATE dbo.v_sqlserver_active
SET luong = luong + 500000
WHERE ma_nv = 101;
~~~

thay đổi lương nếu các điều kiện thỏa.

~~~sql
UPDATE dbo.v_sqlserver_active
SET trang_thai = 'INACTIVE'
WHERE ma_nv = 101;
~~~

bị CHECK OPTION cấm vì sau cập nhật nhân viên không còn nằm trong view.

SQL Server dùng **WITH CHECK OPTION** theo cú pháp view của nó; không mặc định có LOCAL/CASCADED keywords giống PostgreSQL/MySQL.

### 19.2. JOIN view và một bảng gốc

View JOIN trong SQL Server có thể cập nhật cột của **một bảng nền** nếu các điều kiện đáp ứng, nhưng một UPDATE muốn sửa luong của nhan_vien **và** ten_phong của phong_ban cùng lúc thường không được phép bằng cơ chế direct view update.

Cần kiểm tra các cột thuộc bảng gốc nào; tên cột hiển thị trong view không tự nói lên nguồn vật lý.

### 19.3. INSTEAD OF trigger trên view

Để kiểm soát DML trên JOIN view, SQL Server hỗ trợ **INSTEAD OF UPDATE trigger**. Với view:

~~~sql
CREATE VIEW dbo.v_nv_phong AS
SELECT
    n.ma_nv,
    n.ten_nv,
    n.luong,
    p.ten_phong
FROM dbo.nhan_vien AS n
JOIN dbo.phong_ban AS p
  ON p.ma_phong = n.ma_phong;
~~~

một trigger minh họa chỉ xử lý thay đổi luong:

~~~sql
CREATE TRIGGER dbo.trg_v_nv_phong_luong
ON dbo.v_nv_phong
INSTEAD OF UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    IF UPDATE(ma_nv) OR UPDATE(ten_nv) OR UPDATE(ten_phong)
    BEGIN
        THROW 50001, 'Chi duoc sua luong qua view', 1;
    END;

    UPDATE n
       SET n.luong = i.luong
      FROM dbo.nhan_vien AS n
      JOIN inserted AS i
        ON i.ma_nv = n.ma_nv;
END;
~~~

SQL Server dùng pseudo-table **inserted** (giá trị mới) và **deleted** (giá trị cũ) trong trigger; chúng có thể chứa **nhiều hàng**. Vì vậy trigger phải viết **set-based**, không giả định mỗi lần trigger chỉ có một nhân viên.

**Lưu ý:** Ví dụ dùng THROW và UPDATE(column) để minh họa kiểm soát cột; trong production cần xử lý trường hợp đổi khóa, hàng bị xóa, quyền, transaction, trigger lồng nhau và việc trigger hỗ trợ các biểu thức UPDATE phức tạp. Cũng phải kiểm tra những hạn chế kết hợp **WITH CHECK OPTION** và INSTEAD OF trigger theo phiên bản SQL Server đích.

### 19.4. Schemabinding và indexed view

**WITH SCHEMABINDING** giúp ràng buộc cấu trúc đối tượng nền theo quy tắc SQL Server, không có nghĩa view phức tạp tự cập nhật được. **Indexed view** là cơ chế vật hóa/có chỉ mục với các điều kiện riêng; không đồng nhất với một simple view thông thường.

## 20. Oracle Database: inherently updatable view và key-preserved table

Oracle phân biệt view **inherently updatable** (tự cập nhật theo quy tắc) và view cần **INSTEAD OF trigger**. Những điều kiện quan trọng:

- Simple view từ một bảng, các cột gốc và không có phép tổng hợp/phân nhóm thường là ứng viên updatable.
- Với **join view**, khái niệm **key-preserved table** liên quan trực tiếp đến khả năng cập nhật cột của bảng nền.
- View có các phép biến đổi phức tạp như aggregate, GROUP BY, DISTINCT, set operator thường không có ánh xạ DML tự động.
- INSERT và DELETE có thể có quy tắc riêng khác UPDATE.
- Không được sửa trực tiếp một số cột tham gia cấu trúc join theo những hạn chế của Oracle.

### 20.1. Simple view với CHECK OPTION

~~~sql
CREATE VIEW v_oracle_active AS
SELECT ma_nv, ten_nv, luong, trang_thai
FROM nhan_vien
WHERE trang_thai = 'ACTIVE'
WITH CHECK OPTION;
~~~

Câu UPDATE lương:

~~~sql
UPDATE v_oracle_active
SET luong = luong + 500000
WHERE ma_nv = 101;
~~~

có thể hợp lệ nếu view và quyền/constraint đáp ứng.

Câu đổi trạng thái làm hàng rời khỏi view bị CHECK OPTION từ chối.

### 20.2. WITH READ ONLY

Oracle hỗ trợ view có **WITH READ ONLY** để thể hiện chính sách không sửa qua view:

~~~sql
CREATE VIEW v_oracle_bao_cao AS
SELECT
    ma_phong,
    COUNT(*) AS so_nv,
    AVG(luong) AS luong_tb
FROM nhan_vien
GROUP BY ma_phong
WITH READ ONLY;
~~~

Ở đây view tổng hợp vốn không phải ứng viên tự động cập nhật; READ ONLY thể hiện rõ ý định sử dụng chỉ để đọc. Không suy ra các DBMS khác đều có cùng cú pháp **WITH READ ONLY** ở cuối CREATE VIEW.

### 20.3. USER_UPDATABLE_COLUMNS

Oracle cung cấp thông tin các cột updatable/insertable/deletable qua data dictionary, ví dụ **USER_UPDATABLE_COLUMNS**:

~~~sql
SELECT
    table_name,
    column_name,
    updatable,
    insertable,
    deletable
FROM user_updatable_columns
WHERE table_name = 'V_ORACLE_ACTIVE';
~~~

Tên view trong dictionary thường được ghi chữ hoa với các identifier không đặt trong dấu quote. Metadata nên được xem là dấu hiệu **khả năng cấu trúc**, không thay thế kiểm tra quyền, constraint và logic trigger.

## 21. Oracle INSTEAD OF trigger cho view phức tạp

Với view JOIN:

~~~sql
CREATE VIEW v_oracle_nv_phong AS
SELECT
    n.ma_nv,
    n.ten_nv,
    n.luong,
    p.ten_phong
FROM nhan_vien n
JOIN phong_ban p
  ON p.ma_phong = n.ma_phong;
~~~

có thể định nghĩa trigger:

~~~sql
CREATE OR REPLACE TRIGGER trg_oracle_nv_phong_update
INSTEAD OF UPDATE ON v_oracle_nv_phong
FOR EACH ROW
BEGIN
    UPDATE nhan_vien
       SET luong = :NEW.luong
     WHERE ma_nv = :OLD.ma_nv;
END;
/
~~~

Đây là **ví dụ đơn giản** minh họa cú pháp INSTEAD OF trên view. Trigger này chỉ chủ động xử lý luong. Trong ứng dụng thật, cần **từ chối** các thay đổi thuộc những cột khác, không được âm thầm bỏ qua sửa ten_phong/ma_nv/ten_nv; đồng thời phải xử lý row count, constraint, nhiều hàng, quyền và concurrency theo thiết kế.

### 21.1. :OLD và :NEW

Oracle row-level trigger dùng **:OLD** và **:NEW** để truy cập giá trị hàng trước và sau DML qua view. Chúng không phải cùng một cơ chế/cú pháp với pseudo-table **inserted/deleted** của SQL Server.

### 21.2. Key-preserved join view không đồng nghĩa trigger bắt buộc

Một join view có thể tự cập nhật được cột của bảng được bảo toàn khóa theo quy tắc Oracle. Trigger là lựa chọn khi DML không được hỗ trợ tự động hoặc cần nghiệp vụ chuyển đổi đặc biệt. Không dùng INSTEAD OF trigger nếu nó chỉ lặp lại cập nhật đơn giản nhưng lại làm tăng rủi ro và độ phức tạp không cần thiết.

## 22. SQLite: view thông thường read-only

Đây là khác biệt quan trọng: trong **SQLite, view là read-only theo mặc định**. Ngay cả view rất đơn giản:

~~~sql
CREATE VIEW v_sqlite_active AS
SELECT ma_nv, ten_nv, luong, trang_thai
FROM nhan_vien
WHERE trang_thai = 'ACTIVE';
~~~

không tự chấp nhận:

~~~sql
UPDATE v_sqlite_active
SET luong = 14000000
WHERE ma_nv = 101;
~~~

chỉ vì SELECT xuất phát từ một bảng.

SQLite hỗ trợ DML thông qua view bằng **INSTEAD OF triggers**.

### 22.1. Tạo INSTEAD OF UPDATE trigger

~~~sql
CREATE TRIGGER trg_sqlite_update_active
INSTEAD OF UPDATE ON v_sqlite_active
BEGIN
    UPDATE nhan_vien
       SET luong = NEW.luong
     WHERE ma_nv = OLD.ma_nv
       AND trang_thai = 'ACTIVE';
END;
~~~

Khi ứng dụng chạy:

~~~sql
UPDATE v_sqlite_active
SET luong = 14000000
WHERE ma_nv = 101;
~~~

SQLite thực thi trigger, và trigger cập nhật bảng nhan_vien.

**Lưu ý:** Ví dụ chỉ triển khai đổi luong. Nếu view cho phép UPDATE trang_thai hoặc ten_nv mà trigger không xử lý, người dùng có thể tưởng thao tác thành công nhưng thay đổi bị bỏ qua. Trong production, cần chặn các cột không cho phép và định nghĩa đầy đủ nghiệp vụ.

### 22.2. Mô phỏng CHECK OPTION trong SQLite trigger

SQLite không cung cấp cùng cú pháp **WITH CHECK OPTION** dành cho view như một số DBMS khác. Nếu muốn không cho đổi trang_thai ra khỏi ACTIVE, có thể kiểm tra trong trigger:

~~~sql
CREATE TRIGGER trg_sqlite_update_active_checked
INSTEAD OF UPDATE ON v_sqlite_active
BEGIN
    SELECT CASE
        WHEN NEW.trang_thai IS NULL
          OR NEW.trang_thai <> 'ACTIVE'
        THEN RAISE(ABORT, 'View chi chap nhan ACTIVE')
    END;

    UPDATE nhan_vien
       SET ten_nv = NEW.ten_nv,
           luong = NEW.luong,
           trang_thai = NEW.trang_thai
     WHERE ma_nv = OLD.ma_nv;
END;
~~~

**Không tạo đồng thời hai trigger UPDATE có chức năng chồng nhau rồi kỳ vọng chỉ một trigger hoạt động**. Đoạn thứ hai là **phương án thay thế** trigger thứ nhất, không phải yêu cầu tạo cả hai. Khi chạy thực tế, hãy xóa trigger cũ hoặc chọn tên/cấu hình thích hợp, rồi kiểm thử hành vi.

### 22.3. Số hàng thay đổi qua trigger

SQLite có khác biệt về cách báo số hàng thay đổi khi DML chạy trên view và được thực thi bằng INSTEAD OF trigger. Các hàm/API như sqlite3_changes() không nhất thiết phản ánh đúng số thay đổi bên trong trigger như một UPDATE trực tiếp lên bảng gốc. Vì vậy, với thao tác quan trọng, cần kiểm tra dữ liệu nền hoặc cơ chế phản hồi/audit được thiết kế rõ.

### 22.4. SQLite không có GRANT như server RDBMS

SQLite thường là cơ sở dữ liệu nhúng, quyền file và ứng dụng đóng vai trò bảo mật quan trọng; không có mô hình GRANT UPDATE ON VIEW giống PostgreSQL/Oracle/SQL Server. Trigger giúp định nghĩa cách chuyển DML, không tự thay thế quyền truy cập ứng dụng.

## 23. Bảng so sánh theo hệ quản trị

| Khía cạnh | PostgreSQL | MySQL | SQL Server | Oracle | SQLite |
|---|---|---|---|---|---|
| Simple view một bảng có thể UPDATE tự động | Có, theo điều kiện | Có, theo điều kiện | Có, theo điều kiện | Có, theo điều kiện | Không, view read-only mặc định |
| Cột biểu thức trực tiếp UPDATE | Thường không | Thường không | Thường không | Thường không | Chỉ qua trigger tùy thiết kế |
| View có GROUP BY/aggregate tự cập nhật | Không theo cơ chế thông thường | Không theo cơ chế thông thường | Không theo cơ chế thông thường | Không theo cơ chế thông thường | Không |
| Một số JOIN view có thể UPDATE tự động | Không theo simple auto-update | Có điều kiện, thường một bảng | Có điều kiện, một bảng | Có điều kiện/key preservation | Không |
| WITH CHECK OPTION | Có | Có | Có | Có | Không có cú pháp tương ứng |
| LOCAL/CASCADED CHECK OPTION | Có | Có | Không cùng cú pháp | Không cùng cú pháp | Không |
| INSTEAD OF trigger trên view | Có | Không có mô hình INSTEAD OF trigger view tương tự | Có | Có | Có |
| Materialized/indexed view | Materialized view riêng | Không có materialized view native phổ thông | Indexed view theo quy tắc riêng | Materialized view | Không native cùng nghĩa |

Bảng là **định hướng tổng quan**, không thay thế tài liệu của bản DBMS cụ thể. Mỗi dòng “Có điều kiện” có thể có ngoại lệ về cấu trúc SELECT, loại DML, khóa, cột trực tiếp, quyền và ràng buộc.

### 23.1. Chú ý MySQL về trigger

MySQL hỗ trợ trigger trên **bảng** nhưng không cung cấp cùng cơ chế **INSTEAD OF trigger trên view** như PostgreSQL, SQL Server, Oracle và SQLite. Khi view MySQL không updatable, thường phải cập nhật **bảng nền**, dùng stored procedure/API hoặc thiết kế lại view và giao diện ghi.

### 23.2. Không suy luận từ tên sản phẩm

PostgreSQL và SQL Server đều có view và trigger, nhưng cú pháp function, inserted/deleted, RETURNING/OUTPUT, LOCAL/CASCADED và bảo mật khác nhau. Dù nhiều SQL trông tương tự, **một file migration cập nhật view không thể coi là khả chuyển nguyên văn giữa năm DBMS**.

## 24. INSERT qua view: điều kiện thường chặt hơn UPDATE

Ví dụ view chỉ hiển thị:

~~~sql
CREATE VIEW v_nv_ten AS
SELECT ma_nv, ten_nv
FROM nhan_vien;
~~~

Bảng nhan_vien còn các cột bắt buộc **luong NOT NULL**, **trang_thai NOT NULL**. Nếu không có DEFAULT, lệnh:

~~~sql
INSERT INTO v_nv_ten (ma_nv, ten_nv)
VALUES (106, 'Lan');
~~~

có thể thất bại do không cung cấp được luong/trang_thai cho hàng mới ở bảng gốc, ngay cả nếu DBMS coi view là simple updatable.

### 24.1. Một view INSERT được cần đáp ứng nhiều thứ

- Cột được INSERT có ánh xạ đến cột gốc có thể ghi.
- Các cột NOT NULL không có DEFAULT được cung cấp theo quy tắc.
- Khóa chính/khóa duy nhất hợp lệ.
- FOREIGN KEY/ CHECK/trigger ở bảng nền không bị vi phạm.
- Hàng mới thỏa CHECK OPTION nếu view có kiểm tra.
- Người dùng có quyền INSERT trên view theo mô hình DBMS.

### 24.2. View có bộ lọc và INSERT

~~~sql
CREATE VIEW v_insert_active AS
SELECT ma_nv, ten_nv, luong, trang_thai
FROM nhan_vien
WHERE trang_thai = 'ACTIVE'
WITH CHECK OPTION;
~~~

Nếu INSERT đưa trang_thai='INACTIVE', hàng mới không thuộc view nên CHECK OPTION từ chối, khi DBMS hỗ trợ thao tác đó. Nếu không có CHECK OPTION, một số hệ cho phép chèn hàng không hiển thị trong view, khiến người dùng tưởng INSERT “mất dữ liệu”.

### 24.3. Cột tự sinh, DEFAULT và IDENTITY

Một bảng gốc có identity/sequence/default có thể giải quyết việc thiếu cột được sinh tự động. Nhưng cột thuộc view có phải INSERT được hay không vẫn phụ thuộc loại cột và DBMS.

## 25. DELETE qua view: tác động thật tới bảng nền

Với view đơn giản:

~~~sql
CREATE VIEW v_active_for_delete AS
SELECT ma_nv, ten_nv, trang_thai
FROM nhan_vien
WHERE trang_thai = 'ACTIVE';
~~~

Ở hệ hỗ trợ DELETE từ view:

~~~sql
DELETE FROM v_active_for_delete
WHERE ma_nv = 101;
~~~

có thể **xóa hàng 101 ở bảng nhan_vien**, không chỉ “ẩn” hàng khỏi view. Đây là khác biệt nguy hiểm.

### 25.1. Xóa qua view khác UPDATE trạng thái

Nếu mục tiêu chỉ là không còn hiển thị, có thể cần:

~~~sql
UPDATE nhan_vien
SET trang_thai = 'INACTIVE'
WHERE ma_nv = 101;
~~~

trên bảng nền hoặc API phù hợp, không phải DELETE. Đối với view có CHECK OPTION, UPDATE chuyển ra khỏi view có thể bị từ chối, nhưng DELETE vẫn có ngữ nghĩa xóa hàng.

### 25.2. Xóa qua JOIN view

DELETE qua view JOIN có hạn chế khác UPDATE và phụ thuộc DBMS; có thể có nhiều bảng hoặc nhiều hàng tương ứng. Không giả định vì SELECT view thấy một nhân viên nên DELETE có thể dễ dàng chọn đúng một dòng gốc trong mọi JOIN.

## 26. VIEW và bảng trung gian không phải cùng loại đối tượng

Trong chương “View và bảng trung gian”, cần tách bốn mô hình:

1. **View thường:** lưu định nghĩa SELECT, dữ liệu đọc từ nguồn.
2. **Temporary table:** bảng vật lý tạm có dữ liệu riêng, có thể UPDATE trực tiếp như một bảng theo quyền và constraint.
3. **Staging/intermediate table:** bảng lưu dữ liệu trung gian cho ETL/đồng bộ, có thể UPDATE mà không tự làm đổi bảng nguồn.
4. **Materialized view/indexed view:** cơ chế lưu kết quả/cấu trúc có chỉ mục được duy trì theo quy tắc sản phẩm; DML trực tiếp khác view thường.

### 26.1. UPDATE bảng tạm không sửa bảng gốc

Giả sử:

~~~sql
CREATE TEMPORARY TABLE staging_luong AS
SELECT ma_nv, luong
FROM nhan_vien;
~~~

Cú pháp CREATE TEMPORARY TABLE AS SELECT thay đổi giữa DBMS; ví dụ trên mang tính định hướng.

Nếu UPDATE staging_luong:

~~~sql
UPDATE staging_luong
SET luong = luong + 1000000;
~~~

thì dữ liệu của **bảng trung gian** đổi. Bảng nhan_vien **không tự đổi**. Muốn áp thay đổi vào bảng chính, cần câu UPDATE/JOIN/MERGE riêng, có kiểm tra khóa, quyền, transaction.

### 26.2. View không có khả năng UPDATE giống bảng tạm

Không nên đổi view phức tạp thành bảng tạm rồi nghĩ mọi DML lên bảng tạm sẽ tự đồng bộ ngược về bảng gốc. Bảng tạm là dữ liệu độc lập, còn view là giao diện truy vấn tới bảng khác.

## 27. Materialized view và indexed view

**PostgreSQL materialized view** lưu kết quả truy vấn và được làm mới bằng REFRESH MATERIALIZED VIEW; không coi UPDATE trực tiếp từng hàng materialized view là cơ chế sửa bảng nền như simple view.

**Oracle materialized view** có các khả năng refresh và, trong những cấu hình chuyên biệt, cơ chế cập nhật/replication riêng; không mặc định mọi materialized view đều DML giống bảng gốc.

**SQL Server indexed view** là view có chỉ mục vật lý và quy tắc duy trì đặc thù. Không suy luận rằng một view có chỉ mục thì mọi cột/tập kết quả đều updateable; cần xem các hạn chế của indexed view và cách DML lên bảng nền tác động tới nó.

**MySQL** không có loại native materialized view phổ thông với cùng cách dùng PostgreSQL; thường phải dùng bảng lưu cache và quy trình refresh riêng.

**SQLite** không có materialized view native tương tự; ứng dụng có thể tạo bảng cache và tự cập nhật.

Bài toán “đổi một ô trong kết quả tổng hợp” không có nghiệm tự động chỉ vì kết quả được vật hóa. Cần quy tắc kinh doanh để cập nhật bảng nguồn.

## 28. CTE và view không phải lúc nào cũng cùng khả năng DML

Một **CTE** là tập kết quả được định nghĩa trong một câu lệnh:

~~~sql
WITH active AS (
    SELECT ma_nv, luong
    FROM nhan_vien
    WHERE trang_thai = 'ACTIVE'
)
SELECT *
FROM active;
~~~

Khả năng UPDATE thông qua CTE/derived table phụ thuộc DBMS, cú pháp và cấu trúc truy vấn. Một số hệ cho phép UPDATE qua CTE có thể cập nhật; hệ khác yêu cầu UPDATE bảng gốc với CTE làm nguồn lọc hoặc tính toán.

Không nên mặc định vì một SELECT được đặt tên bằng **WITH** nên nó có cùng DML semantics với một **CREATE VIEW** đã lưu trong schema.

### 28.1. Dùng CTE làm nguồn UPDATE bảng thật

Với nhu cầu tính mức tăng lương từ bảng khác, một CTE có thể giúp tạo nguồn có khóa duy nhất. Nhưng cần UPDATE đúng bảng nhân viên và điều kiện khóa chặt chẽ, thay vì cố UPDATE một view tổng hợp chỉ để tận dụng kết quả SELECT.

## 29. WITH CHECK OPTION khác CHECK constraint

Hai cơ chế thường bị nhầm:

**CHECK constraint trên bảng gốc:**

~~~sql
CONSTRAINT ck_luong CHECK (luong >= 0)
~~~

áp dụng cho dữ liệu của bảng gốc theo quy tắc constraint, bất kể DML đi từ đâu.

**WITH CHECK OPTION trên view:**

~~~sql
WHERE trang_thai = 'ACTIVE'
WITH CHECK OPTION
~~~

kiểm soát **DML qua view** để hàng mới còn thuộc tập hiển thị của view. Nếu ai đó có quyền UPDATE trực tiếp bảng nhan_vien, họ có thể đổi trang_thai sang INACTIVE mà không đi qua view; CHECK OPTION của view **không tự chặn** thao tác trực tiếp đó.

### 29.1. Chọn công cụ theo bất biến

| Quy tắc | Nơi phù hợp |
|---|---|
| Lương không âm cho toàn hệ thống | CHECK constraint ở bảng gốc |
| Mã nhân viên duy nhất | PRIMARY KEY/UNIQUE |
| Mã phòng tham chiếu phòng hợp lệ | FOREIGN KEY |
| Chỉ ghi qua view ACTIVE khi bản mới vẫn ACTIVE | WITH CHECK OPTION khi hỗ trợ |
| Không cho nhân viên thường sửa lương | GRANT/RLS/API permission |
| View JOIN cần chuyển UPDATE tới bảng nền | INSTEAD OF trigger/procedure |
| Không cho sửa trạng thái sau khi chốt kỳ | Transactional business validation/constraint/trigger |

**CHECK OPTION không thể thay thế constraint hoặc hệ thống quyền.**

## 30. Vấn đề quyền: updatable về cấu trúc chưa chắc được phép sửa

Ngay cả view rất đơn giản vẫn có thể không UPDATE được với tài khoản hiện tại vì thiếu quyền.

Ví dụ hướng SQL phổ biến:

~~~sql
GRANT SELECT, UPDATE ON v_nhan_vien_active TO role_ung_dung;
~~~

Nhưng cú pháp GRANT và cách kiểm tra quyền nguồn khác nhau theo DBMS.

### 30.1. PostgreSQL

View thường có mô hình quyền liên quan tới **chủ sở hữu view** khi truy cập bảng nền, trừ những cấu hình đặc biệt như **security_invoker** trên phiên bản hỗ trợ. Cần thiết kế cả quyền trên view, quyền lên bảng và Row-Level Security (RLS) nếu dùng.

### 30.2. MySQL

SQL SECURITY DEFINER/INVOKER và quyền thực tế của tài khoản quy định cách view truy cập dữ liệu gốc. Độ updatable của view và quyền DML là hai kiểm tra khác nhau.

### 30.3. SQL Server

Ownership chaining và GRANT trên view có thể ảnh hưởng khả năng truy cập bảng gốc. Tuy nhiên, người dùng được GRANT UPDATE trên view cũng có thể phải chịu giới hạn của trigger, schema và bảo mật cơ sở dữ liệu.

### 30.4. Oracle

Quyền trên view, quyền trực tiếp cần thiết cho đối tượng nền, chủ sở hữu và quyền của trigger/procedure phải được xem trong mô hình Oracle.

### 30.5. SQLite

Không có mô hình GRANT từng view như server DBMS. Quyền file, kết nối và tầng ứng dụng là lớp kiểm soát quan trọng.

### 30.6. View không tự là ranh giới an ninh hoàn chỉnh

Nếu ứng dụng có quyền cập nhật trực tiếp bảng nền, việc tạo một view chỉ lọc ACTIVE không thể ngăn ứng dụng bỏ qua view. Hãy giới hạn quyền nền, xác thực tenant, dùng RLS khi phù hợp và kiểm tra chính sách ở nơi có hiệu lực.

## 31. Cập nhật trong hệ multi-tenant

Giả sử nhan_vien có thêm **tenant_id** và nhiều tenant có thể cùng ma_nv=101.

View:

~~~sql
CREATE VIEW v_active_tenant AS
SELECT tenant_id, ma_nv, ten_nv, luong, trang_thai
FROM nhan_vien
WHERE trang_thai = 'ACTIVE';
~~~

chưa hề giới hạn tenant. Câu:

~~~sql
UPDATE v_active_tenant
SET luong = luong + 1000000
WHERE ma_nv = 101;
~~~

có thể sửa ma_nv 101 ở **nhiều tenant** nếu khóa/WHERE không đủ. Hãy dùng khóa nghiệp vụ đầy đủ:

~~~sql
WHERE tenant_id = :tenant_id
  AND ma_nv = :ma_nv
~~~

Bảo đảm tenant_id đến từ ngữ cảnh xác thực đáng tin cậy, không chỉ dựa vào giá trị do client tự gửi. Trong một số kiến trúc, row-level security hoặc view theo tenant có thể bổ sung bảo vệ, nhưng vẫn phải hiểu quyền và CHECK OPTION trên DBMS thực.

### 31.1. CHECK OPTION không tự sinh chính sách tenant

Một view lọc:

~~~sql
WHERE tenant_id = 'T1'
~~~

với CHECK OPTION có thể ngăn người dùng UPDATE một hàng thuộc T1 thành tenant T2 **qua view**. Nhưng nó không chặn DML trực tiếp trên bảng gốc và không thay thế ràng buộc quyền. Nếu ứng dụng tạo view động theo tenant, còn có rủi ro quản lý schema/quyền.

## 32. Cập nhật cột không hiển thị trong view

Nếu view chỉ có:

~~~sql
SELECT ma_nv, ten_nv, luong
FROM nhan_vien
~~~

thì câu:

~~~sql
UPDATE v_luong
SET trang_thai = 'INACTIVE'
WHERE ma_nv = 101;
~~~

thường không hợp lệ vì **trang_thai không phải cột của view** (dù tồn tại trong bảng gốc). DML trên view chỉ được tham chiếu các cột view cho phép, hoặc phải chuyển hướng qua procedure/trigger có API riêng.

Cần phân biệt:

- Cột **không được SELECT** trong view: không có tên để SET trực tiếp trên view.
- Cột **được SELECT nhưng là biểu thức**: có tên nhưng thường không có ánh xạ cập nhật tự động.
- Cột **được SELECT trực tiếp từ bảng gốc**: có thể UPDATE nếu view và DBMS hỗ trợ.

## 33. Cột được đọc nhưng không nên cho sửa

Một view có thể cho phép nhân viên cập nhật **email liên hệ**, nhưng không nên cho cập nhật **luong, tenant_id, trang_thai xác thực**.

Các cách triển khai:

- Chỉ SELECT những cột cho phép sửa trong một view riêng.
- Dùng quyền UPDATE theo cột khi DBMS hỗ trợ.
- Dùng trigger/procedure/API từ chối những thay đổi ngoài chính sách.
- Dùng CHECK constraint/FOREIGN KEY/UNIQUE ở bảng nguồn.
- Có audit trail cho thay đổi nhạy cảm.

**Ẩn cột trong view giúp giảm bề mặt giao diện**, nhưng việc cấm cập nhật phải phù hợp với quyền và cách ứng dụng kết nối database.

## 34. Thao tác UPDATE với số hàng 0

Câu:

~~~sql
UPDATE v_nhan_vien_active
SET luong = 14000000
WHERE ma_nv = 103;
~~~

có thể trả 0 hàng do ma_nv 103 INACTIVE. Các nguyên nhân khác có thể gồm:

- ID không tồn tại ở bảng nền.
- Người dùng không có quyền thấy hàng do RLS/security.
- WHERE phụ của UPDATE không thỏa.
- Giao dịch khác đã thay đổi trạng thái.
- Trigger quyết định bỏ qua thao tác theo chính sách.
- Driver/DBMS báo matched/changed row count khác nhau.

Ứng dụng không được suy ra “đã sửa thành công” chỉ vì SQL không báo lỗi.

### 34.1. View có trigger và row count

Ở các hệ có INSTEAD OF trigger, số hàng mà ứng dụng nhận có thể phản ánh những quy tắc riêng về DML/trigger, khác số hàng nền thực sự đổi. Với SQLite, đặc biệt cần chú ý API đếm thay đổi không tự bao gồm cập nhật trong trigger trên view. Nếu nghiệp vụ quan trọng, có thể cần truy vấn kiểm tra hoặc tín hiệu từ procedure/audit.

## 35. Triggers phải xử lý nhiều hàng, không chỉ một hàng

Một lệnh UPDATE có thể chọn nhiều dòng:

~~~sql
UPDATE v_nhan_vien_active
SET luong = luong * 1.05
WHERE luong < 15000000;
~~~

Trigger trên view phải xử lý đúng toàn bộ tập. Những vấn đề thường gặp:

- SQL Server **inserted/deleted** chứa nhiều dòng; không lấy một giá trị đơn lẻ mà bỏ qua các dòng khác.
- PostgreSQL và Oracle INSTEAD OF trigger thường chạy theo từng hàng, cần cân nhắc chi phí khi cập nhật hàng loạt.
- SQLite INSTEAD OF trigger có NEW/OLD theo từng hàng, cần kiểm soát logic đã định nghĩa.
- Nếu JOIN tạo hai dòng view cho một hàng nền, trigger có thể nhận nhiều sự kiện và cập nhật bảng nền lặp; nên thiết kế khóa và phép nối rõ.
- Trigger cần kiểm soát NULL, thay đổi khóa, trạng thái không hợp lệ, constraint và lỗi giao dịch.

### 35.1. Không âm thầm nuốt thao tác không được hỗ trợ

Ví dụ trigger chỉ sửa luong nhưng người dùng gọi:

~~~sql
UPDATE v_nv_phong
SET ten_phong = 'Nhân sự mới'
WHERE ma_nv = 101;
~~~

Nếu trigger không báo lỗi và chỉ bỏ qua ten_phong, ứng dụng có thể coi cập nhật thành công dù không có thay đổi mong muốn. Một API ghi an toàn nên **từ chối rõ** cột không cho phép hoặc triển khai đầy đủ thao tác.

## 36. Concurrency khi cập nhật qua view

UPDATE qua view cuối cùng vẫn là thao tác trên dữ liệu nền, nên gặp các vấn đề của transaction:

- Hai người cùng sửa lương một nhân viên.
- Một người chuyển trạng thái khiến hàng rời khỏi view trước khi người khác UPDATE.
- Một người xóa hàng, người khác ghi qua trigger.
- Trigger JOIN lại bảng nền trong lúc dữ liệu liên quan thay đổi.
- Cập nhật nhiều bảng cần toàn vẹn giao dịch.

### 36.1. Optimistic locking

Bảng nhan_vien có thể có **phien_ban INTEGER**. View đưa cột đó ra:

~~~sql
CREATE VIEW v_nv_version AS
SELECT ma_nv, luong, trang_thai, phien_ban
FROM nhan_vien
WHERE trang_thai = 'ACTIVE';
~~~

Ứng dụng đọc phiên bản 5, sau đó:

~~~sql
UPDATE v_nv_version
SET luong = 15000000,
    phien_ban = phien_ban + 1
WHERE ma_nv = 101
  AND phien_ban = 5;
~~~

Nếu hàng vẫn ACTIVE và version chưa đổi, cập nhật có thể thành công trên DBMS cho phép view DML. Nếu có người khác sửa trước và tăng version, WHERE không còn khớp. Phải kiểm tra kết quả và xử lý xung đột, không ghi đè mù.

### 36.2. Trigger làm thay đổi semantics

Nếu view cần INSTEAD OF trigger, cơ chế optimistic lock ở trên phải được thực thi **ở thao tác UPDATE bảng gốc bên trong trigger**, với version predicate phù hợp. Chỉ lọc view theo version rồi thực thi một UPDATE nền không kiểm tra version có thể vẫn tạo race condition.

### 36.3. Transaction

Nếu thao tác qua view cập nhật hai bảng (qua trigger/procedure), các bước phải giữ tính nhất quán của nghiệp vụ. Dùng transaction thích hợp và xử lý lỗi/rollback; đừng nghĩ một trigger có thể gọi hệ thống bên ngoài rồi rollback được mọi side effect.

## 37. Hiệu năng: view không phải phép tăng tốc tự động

View giúp tái sử dụng truy vấn, nhưng không mặc nhiên nhanh hơn SELECT trực tiếp.

- View đơn giản có thể được tối ưu và kết hợp điều kiện WHERE với bảng nền.
- View phức tạp có JOIN, GROUP BY và nhiều lớp có thể tạo kế hoạch tốn tài nguyên.
- DML qua view có trigger có thể tạo nhiều UPDATE/SELECT phụ.
- CHECK OPTION cần kiểm tra điều kiện sau cập nhật.
- Trigger hoặc rule có thể làm tăng số câu truy vấn và khóa.
- Indexed/materialized views có cơ chế bảo trì riêng, có thể tăng chi phí khi bảng nền thay đổi.

### 37.1. Không đặt hàm trên cột lọc tùy tiện

Ví dụ view lọc:

~~~sql
WHERE UPPER(trang_thai) = 'ACTIVE'
~~~

có thể hợp lệ để đọc nhưng ảnh hưởng tới khả năng dùng chỉ mục thông thường và hành vi collation. Nếu bảng nền lưu trạng thái chuẩn hóa, nên dùng predicate trực tiếp phù hợp và constraint đảm bảo giá trị.

### 37.2. Đo kế hoạch thực thi

Tùy DBMS, dùng EXPLAIN/EXPLAIN ANALYZE, execution plan, DBMS_XPLAN hoặc EXPLAIN QUERY PLAN. Với DML thật, kiểm tra trên môi trường thử nghiệm và hiểu tác động transaction trước khi dùng công cụ thực thi có side effects.

## 38. Thử xem metadata trước khi viết ứng dụng

Với view cần cập nhật, nên biết:

- View definition hiện tại là gì?
- View có tự động updatable theo DBMS không?
- Những cột nào updatable?
- View có CHECK OPTION không?
- View có INSTEAD OF trigger/rule không?
- Người dùng ứng dụng được GRANT những gì?
- Bảng nền có constraint/trigger nào?
- Câu UPDATE sẽ thay một hay nhiều bảng?
- Có row-level security, trigger audit, computed columns hoặc chính sách tenant không?

### 38.1. PostgreSQL

Thông tin schema view trong **information_schema.views** (gồm is_updatable) và catalog hệ thống giúp điều tra. Một số metadata về cột có thể hữu ích, nhưng cần thử DML trên test DB để biết chính xác hành vi.

### 38.2. MySQL

**INFORMATION_SCHEMA.VIEWS** có IS_UPDATABLE và CHECK_OPTION, là cách thuận tiện kiểm tra nhận định của server.

### 38.3. SQL Server

Có thể xem **sys.views**, định nghĩa view trong **sys.sql_modules**, dependency và triggers liên quan; không có một cờ đơn giản đủ giải thích mọi khả năng cập nhật. Cần đọc quy tắc CREATE VIEW/UPDATE và test có kiểm soát.

### 38.4. Oracle

**USER_UPDATABLE_COLUMNS** là nguồn dữ liệu hữu ích để xem khả năng INSERT/UPDATE/DELETE theo cột; cũng cần xem trigger và view definition.

### 38.5. SQLite

**sqlite_schema** lưu định nghĩa view/trigger; phải kiểm tra INSTEAD OF trigger cụ thể. Không có cờ updatable tự động tương đương vì view vốn read-only.

## 39. Một quy trình thiết kế view có cập nhật an toàn

**Bước 1 — Xác định mục tiêu đọc và ghi.** View chỉ để báo cáo hay là giao diện chỉnh sửa?

**Bước 2 — Xác định bảng/cột nguồn.** Mỗi cột view lấy trực tiếp từ đâu? Có biểu thức hoặc nhiều bảng không?

**Bước 3 — Xác định thao tác được phép.** UPDATE cột nào, INSERT có hợp lệ, DELETE có bị cấm?

**Bước 4 — Kiểm tra updatability theo DBMS.** Không dùng quy tắc PostgreSQL để kết luận thay cho SQLite.

**Bước 5 — Định nghĩa bất biến.** CHECK OPTION, constraint bảng nền, security, trạng thái và tenant.

**Bước 6 — Chọn phương thức ghi.** DML tự động qua simple view, INSTEAD OF trigger, stored procedure hoặc UPDATE bảng gốc có kiểm soát.

**Bước 7 — Kiểm thử.** Dòng bình thường, ngoài view, giá trị làm hàng rời view, NULL, vi phạm constraint, nhiều hàng, concurrency và rollback.

**Bước 8 — Theo dõi.** Row count, audit, trigger failures, performance và thay đổi schema.

**Bước 9 — Tài liệu hóa.** Nêu rõ view nào **read-only**, view nào **UPDATE được**, những cột và điều kiện nào được cho phép.

## 40. Các lỗi thường gặp

| Sai lầm | Vì sao sai hoặc nguy hiểm | Cách xử lý |
|---|---|---|
| Nghĩ mọi view đều UPDATE được | View có thể tổng hợp, JOIN, set operator | Kiểm tra cấu trúc và DBMS |
| Thấy SELECT từ một bảng, suy ra SQLite cho UPDATE | SQLite view mặc định read-only | INSTEAD OF trigger hoặc UPDATE bảng |
| Nhầm UPDATE view với sửa bản sao | DML thường đổi dữ liệu nền | Xác định bảng gốc chịu tác động |
| View có GROUP BY nhưng muốn SET SUM | Không biết phân bổ về các dòng nguồn | UPDATE bảng gốc theo quy tắc nghiệp vụ |
| DISTINCT và nghĩ còn khóa hàng gốc | DISTINCT có thể gộp nhiều hàng | Không direct UPDATE |
| JOIN hai bảng rồi SET cột cả hai | Nhiều DBMS cấm một UPDATE qua view sửa hai bảng | Transaction/procedure/trigger |
| Không xét key-preserved table trên Oracle | JOIN có thể làm mơ hồ hàng nền | Kiểm tra data dictionary/quy tắc |
| SET cột tính toán | Cột không ánh xạ trực tiếp | Sửa cột gốc hoặc logic trigger rõ |
| Không dùng CHECK OPTION khi cần giữ hàng trong view | Hàng có thể biến mất sau UPDATE | WITH CHECK OPTION |
| Nghĩ CHECK OPTION luôn được bật | View thường không tự check | Khai báo rõ |
| Nghĩ CHECK OPTION bảo vệ DML trực tiếp lên bảng nền | Check thuộc đường ghi qua view | Constraint/RLS/quyền bảng nền |
| Nhầm LOCAL với CASCADED | Lọc của view nền có thể không được kiểm soát | Chọn mức check theo DBMS |
| Nghĩ CHECK OPTION cấm DELETE | DELETE không tạo hàng mới trong view | Kiểm soát quyền DELETE |
| Quên cột NOT NULL ẩn khi INSERT | INSERT qua view thất bại | DEFAULT hoặc API khác |
| Quên khóa/tenant khi UPDATE | Sửa nhiều hàng, sai tenant | WHERE full key, quyền |
| MySQL ALGORITHM=MERGE bị hiểu là UPSERT MERGE | Hai khái niệm khác nhau | Đọc ngữ nghĩa view algorithm |
| MySQL TEMPTABLE view nhưng cố UPDATE | TEMPTABLE thường không updatable | Đổi view/ghi bảng |
| Dùng INSTEAD OF trigger không kiểm tra cột | Thay đổi không hỗ trợ bị bỏ lặng | Reject rõ hoặc triển khai đủ |
| Trigger SQL Server giả định một dòng | inserted/deleted có thể nhiều dòng | Viết set-based |
| Trigger bỏ version predicate | Race condition/lost update | Optimistic locking tại bảng nền |
| Không kiểm tra row count | UPDATE có thể chọn 0/nhiều hàng | Kiểm tra và xác minh |
| Nghĩ view có security filter tự bảo vệ mọi đường ghi | Có thể truy cập bảng nền trực tiếp | Quyền tối thiểu, RLS/API |
| Nhầm view thường với materialized view | DML/refresh semantics khác | Phân biệt loại đối tượng |
| UPDATE bảng staging rồi nghĩ bảng gốc đổi | Bảng staging lưu dữ liệu riêng | UPDATE/MERGE riêng vào đích |
| Không kiểm thử khi đổi DBMS | Quy tắc updatability khác hẳn | Test theo phiên bản thực tế |
| Không hiểu transaction/autocommit | Không rollback được sau COMMIT | Quy trình giao dịch và audit |

## 41. Bộ kiểm thử gợi ý

| Tình huống | Điều cần xác minh |
|---|---|
| View đơn giản một bảng | UPDATE cột trực tiếp được phép ở DBMS phù hợp |
| View có alias | Cột alias vẫn ánh xạ đúng |
| View có cột tính toán | Cột biểu thức không bị SET tùy tiện |
| View có WHERE ACTIVE | Hàng INACTIVE không bị UPDATE qua view |
| Không CHECK OPTION | Hàng có thể rời view theo ngữ nghĩa hệ |
| Có CHECK OPTION | UPDATE làm hàng rời view bị từ chối |
| View nhiều lớp | LOCAL/CASCADED đúng kỳ vọng |
| Hàng mới qua INSERT | Các NOT NULL/DEFAULT/UNIQUE hợp lệ |
| INSERT ngoài bộ lọc | CHECK OPTION chặn khi thích hợp |
| DELETE qua view | Hiểu tác động tới bảng nền |
| View JOIN một–một | DBMS có cho update một bảng không |
| View JOIN một–nhiều | Không cập nhật mơ hồ/lặp |
| SET cột của hai bảng JOIN | Bị chặn hoặc xử lý qua API rõ |
| GROUP BY/SUM | Không tự cập nhật tổng |
| UNION/DISTINCT | Không giả định updatable |
| SQLite không trigger | UPDATE view bị từ chối |
| SQLite có INSTEAD OF trigger | Bảng nền thay đổi đúng |
| Trigger chỉ hỗ trợ một cột | Cột khác bị từ chối minh bạch |
| Trigger nhiều hàng | Không bỏ sót bản ghi |
| Constraint luong >= 0 | Giá trị âm bị từ chối |
| Sai FK ma_phong | Ràng buộc được tôn trọng |
| Tài khoản không có UPDATE | Lệnh bị từ chối theo quyền |
| Tenant khác cùng ma_nv | Không bị cập nhật nhầm |
| Hai session sửa cùng hàng | Xử lý optimistic lock/conflict |
| Transaction rollback | Dữ liệu nền quay về khi rollback được |
| Schema bảng nền thay đổi | View/trigger và migration được kiểm tra |
| Materialized/indexed view | Không nhầm DML với refresh |

## 42. Bài tập thực hành có đáp án

Các bài tập dùng bảng và dữ liệu ở phần 3. Hãy tưởng tượng khôi phục dữ liệu ban đầu trước mỗi bài trừ khi nêu rõ. Các lệnh thay đổi dữ liệu chỉ nên chạy trong môi trường thử nghiệm.

### Bài 1 — View là gì?

View thông thường có phải luôn chứa bản sao riêng của dữ liệu được SELECT không?

<details>
<summary>Đáp án</summary>

**Không.** View thường lưu định nghĩa SELECT và truy vấn dữ liệu nền trong ngữ cảnh thực thi; nó không tương đương một bảng cache vật lý độc lập.

</details>

### Bài 2 — Cập nhật lương qua simple view

Tạo view chỉ chọn nhân viên ACTIVE và cập nhật lương nhân viên 101 lên 14000000. Giả sử DBMS hỗ trợ simple updatable view.

<details>
<summary>Đáp án</summary>

~~~sql
CREATE VIEW v_active_luong AS
SELECT ma_nv, luong, trang_thai
FROM nhan_vien
WHERE trang_thai = 'ACTIVE';

UPDATE v_active_luong
SET luong = 14000000
WHERE ma_nv = 101;
~~~

Hàng nền 101 đổi lương. Hàng 103 INACTIVE không nằm trong view.

</details>

### Bài 3 — Quên WHERE

Nếu UPDATE v_active_luong SET luong = luong + 1000000 không có WHERE thì sao?

<details>
<summary>Đáp án</summary>

Có thể tăng lương **tất cả nhân viên được view hiển thị**, không chỉ một người. Điều kiện trong view giới hạn ACTIVE nhưng vẫn có thể là nhiều người.

</details>

### Bài 4 — Hàng ngoài view

UPDATE view ACTIVE với WHERE ma_nv=103 khi người 103 INACTIVE có sửa được họ không?

<details>
<summary>Đáp án</summary>

Trong simple view semantics, **không** vì người 103 không thuộc tập kết quả view trước thao tác, nên không là hàng đích của UPDATE đó.

</details>

### Bài 5 — Hàng biến mất

Vì sao UPDATE v_active SET trang_thai='INACTIVE' có thể thành công rồi hàng không còn xuất hiện ở view?

<details>
<summary>Đáp án</summary>

Nếu **không có CHECK OPTION**, DBMS có thể cho phép sửa dữ liệu nền. Hàng mới không thỏa WHERE ACTIVE nên bị ẩn khỏi kết quả view.

</details>

### Bài 6 — CHECK OPTION

Viết view ACTIVE có CHECK OPTION và dự đoán UPDATE đổi ACTIVE thành INACTIVE.

<details>
<summary>Đáp án</summary>

~~~sql
CREATE VIEW v_active_checked AS
SELECT ma_nv, ten_nv, trang_thai
FROM nhan_vien
WHERE trang_thai = 'ACTIVE'
WITH CHECK OPTION;
~~~

Ở DBMS hỗ trợ, UPDATE khiến hàng không còn ACTIVE sẽ **bị từ chối**.

</details>

### Bài 7 — CHECK OPTION và lương

View có điều kiện luong>=10000000. Giảm lương nhân viên xuống 9000000 qua view có CHECK OPTION có được không?

<details>
<summary>Đáp án</summary>

**Không**, nếu hệ áp CHECK OPTION: hàng sau UPDATE không còn thỏa bộ lọc lương.

</details>

### Bài 8 — CHECK OPTION và DELETE

CHECK OPTION có tự bảo đảm không ai được DELETE hàng qua view không?

<details>
<summary>Đáp án</summary>

**Không.** CHECK OPTION kiểm soát trạng thái hàng sau INSERT/UPDATE; muốn hạn chế DELETE phải dùng quyền hoặc logic riêng.

</details>

### Bài 9 — LOCAL/CASCADED

Một view v2 xây trên v1. Muốn giữ điều kiện lọc cả v2 và v1 trên PostgreSQL/MySQL khi hỗ trợ, chọn LOCAL hay CASCADED?

<details>
<summary>Đáp án</summary>

**CASCADED** theo quy tắc hệ đó, với lưu ý ngoại lệ ở các lớp view trigger-updatable hoặc không tự updatable.

</details>

### Bài 10 — Cột tính toán

View hiển thị luong_nam=luong*12. Có thể SET luong_nam=240000000 như một cột gốc thông thường không?

<details>
<summary>Đáp án</summary>

Thông thường **không**. luong_nam là biểu thức, không có ánh xạ ngược duy nhất. Cần SET luong hoặc xử lý theo API/trigger được thiết kế rõ.

</details>

### Bài 11 — Alias

View có luong AS muc_luong. Muc_luong có thể khác luong_nam về khả năng UPDATE thế nào?

<details>
<summary>Đáp án</summary>

muc_luong là **alias trực tiếp** của cột gốc, có thể được UPDATE trong simple updatable view. luong_nam là kết quả tính toán, thường read-only.

</details>

### Bài 12 — DISTINCT

Vì sao SELECT DISTINCT ma_phong FROM nhan_vien không tự là view updatable?

<details>
<summary>Đáp án</summary>

Một dòng ma_phong có thể gộp nhiều nhân viên; DBMS không biết phải sửa dòng gốc nào khi UPDATE giá trị đó.

</details>

### Bài 13 — SUM theo phòng

Muốn UPDATE tong_luong ở view GROUP BY, vấn đề gì phát sinh?

<details>
<summary>Đáp án</summary>

SUM gộp nhiều dòng nhân viên thành một giá trị. Không có quy tắc phân bổ tổng mới thành các thay đổi ở từng nhân viên, nên aggregate view thường không tự cập nhật.

</details>

### Bài 14 — JOIN một bảng

View JOIN nhân viên/phòng, UPDATE chỉ cột luong. Có phải chắc chắn được trên mọi DBMS không?

<details>
<summary>Đáp án</summary>

**Không.** MySQL, SQL Server, Oracle có khả năng hạn chế tùy JOIN, khóa và một bảng đích; PostgreSQL không tự cập nhật simple join view; SQLite chỉ qua INSTEAD OF trigger.

</details>

### Bài 15 — JOIN hai bảng

Vì sao SET luong và ten_phong trong một UPDATE view JOIN có thể không hợp lệ?

<details>
<summary>Đáp án</summary>

Hai cột thuộc **hai bảng nền khác nhau**. Nhiều DBMS không hỗ trợ cập nhật cả hai bảng gốc qua một UPDATE view tự động. Cần transaction/procedure/trigger có quy tắc rõ.

</details>

### Bài 16 — Key preservation

Thuật ngữ key-preserved table đặc biệt quan trọng ở hệ quản trị nào khi đánh giá UPDATE qua join view?

<details>
<summary>Đáp án</summary>

**Oracle Database.** Khả năng bảo toàn khóa giúp xác định liệu cột của một bảng nguồn trong kết quả join có thể được cập nhật theo quy tắc Oracle hay không.

</details>

### Bài 17 — PostgreSQL

Liệt kê một số dấu hiệu khiến PostgreSQL simple view không còn automatically updatable.

<details>
<summary>Đáp án</summary>

Nhiều nguồn FROM/JOIN, GROUP BY, HAVING, DISTINCT, UNION/INTERSECT/EXCEPT, LIMIT/OFFSET, aggregate, window/set-returning function theo quy tắc PostgreSQL. Cột biểu thức cũng không phải cột UPDATE trực tiếp.

</details>

### Bài 18 — MySQL MERGE

MySQL ALGORITHM=MERGE ở CREATE VIEW có phải câu lệnh UPSERT MERGE không?

<details>
<summary>Đáp án</summary>

**Không.** ALGORITHM=MERGE mô tả cách MySQL xử lý view. Nó không phải DML MERGE để chèn/cập nhật.

</details>

### Bài 19 — TEMPTABLE

Vì sao MySQL view dùng ALGORITHM=TEMPTABLE thường không updatable?

<details>
<summary>Đáp án</summary>

Vì kết quả view được xử lý theo một dạng bảng tạm cho truy vấn, không giữ ánh xạ sửa trực tiếp từng hàng nền theo yêu cầu updatable view của MySQL.

</details>

### Bài 20 — SQL Server trigger nhiều hàng

Trong INSTEAD OF UPDATE trigger của SQL Server, vì sao không được giả định inserted chỉ có một hàng?

<details>
<summary>Đáp án</summary>

Một lệnh UPDATE có thể tác động nhiều hàng. inserted/deleted là **tập hàng**, nên trigger phải viết **set-based** để xử lý tất cả.

</details>

### Bài 21 — Oracle dictionary

Oracle có view dữ liệu từ điển nào giúp xem cột UPDATABLE/INSERTABLE/DELETABLE?

<details>
<summary>Đáp án</summary>

**USER_UPDATABLE_COLUMNS** (hoặc nhóm dictionary tương ứng theo quyền/schema).

</details>

### Bài 22 — SQLite

Nếu CREATE VIEW đơn giản trong SQLite mà không có trigger, UPDATE view có tự được chuyển xuống bảng nền không?

<details>
<summary>Đáp án</summary>

**Không.** View SQLite read-only mặc định; muốn DML qua view cần INSTEAD OF trigger thích hợp.

</details>

### Bài 23 — SQLite CHECK OPTION

SQLite có WITH CHECK OPTION giống PostgreSQL để tự chặn một hàng rời view không?

<details>
<summary>Đáp án</summary>

**Không có cùng cú pháp view CHECK OPTION**. Có thể triển khai kiểm tra trong INSTEAD OF trigger bằng RAISE(ABORT,...) và logic phù hợp.

</details>

### Bài 24 — INSERT qua view

View chỉ chọn ma_nv,ten_nv nhưng bảng nền có luong NOT NULL và không DEFAULT. INSERT chỉ hai cột có thể thất bại không?

<details>
<summary>Đáp án</summary>

**Có.** Bảng nền vẫn yêu cầu giá trị cho luong. Updatable view không tự giải quyết cột NOT NULL bị ẩn.

</details>

### Bài 25 — Bảng staging

Nếu tạo bảng tạm từ SELECT nhan_vien rồi UPDATE bảng tạm, bảng nhan_vien có tự thay đổi không?

<details>
<summary>Đáp án</summary>

**Không.** Bảng tạm/staging chứa dữ liệu riêng. Muốn cập nhật bảng gốc cần UPDATE/MERGE riêng.

</details>

### Bài 26 — Materialized view

PostgreSQL materialized view có nên được cập nhật từng hàng để sửa nhan_vien như simple view không?

<details>
<summary>Đáp án</summary>

**Không.** Materialized view của PostgreSQL dùng cơ chế lưu kết quả/REFRESH; không coi UPDATE trực tiếp từng hàng là cách sửa bảng nền.

</details>

### Bài 27 — Quyền

Một view structurally updatable có chắc người dùng hiện tại được UPDATE không?

<details>
<summary>Đáp án</summary>

**Không.** Còn quyền DML, chủ sở hữu/security context, RLS, constraint và trigger. Khả năng cấu trúc không đồng nghĩa được phép sửa.

</details>

### Bài 28 — Multi-tenant

Tại sao UPDATE view chỉ WHERE ma_nv=101 có thể sai nếu nhiều tenant cùng ma_nv?

<details>
<summary>Đáp án</summary>

Vì có thể sửa nhiều hàng thuộc tenant khác. Phải lọc theo **tenant_id + ma_nv** từ ngữ cảnh xác thực, kèm cơ chế bảo mật phù hợp.

</details>

### Bài 29 — Version

Cần thêm điều kiện gì nếu chỉ muốn cập nhật nhân viên 101 khi phiên bản vẫn là 5?

<details>
<summary>Đáp án</summary>

~~~sql
UPDATE v_nv_version
SET luong = 15000000,
    phien_ban = phien_ban + 1
WHERE ma_nv = 101
  AND phien_ban = 5;
~~~

Nếu đi qua INSTEAD OF trigger, kiểm tra version phải có ở UPDATE bảng nền để chống race.

</details>

### Bài 30 — Nhận định đúng hay sai

“Có WITH CHECK OPTION thì view GROUP BY sẽ UPDATE được tổng lương”. Đúng hay sai?

<details>
<summary>Đáp án</summary>

**Sai.** CHECK OPTION chỉ kiểm tra điều kiện hàng mới của một view có cơ chế DML phù hợp; nó không tạo cách phân bổ giá trị tổng hợp xuống các dòng nguồn.

</details>

### Bài 31 — Trigger chỉ sửa một cột

Trigger INSTEAD OF UPDATE chỉ ghi luong, nhưng client SET ten_nv. Rủi ro gì?

<details>
<summary>Đáp án</summary>

Có thể **âm thầm bỏ qua** thay đổi ten_nv, khiến client tưởng đã sửa. Trigger/API nên từ chối rõ hoặc triển khai đầy đủ các cột được cho phép.

</details>

### Bài 32 — Thiết kế phương án khả chuyển

Bạn cần triển khai chức năng sửa lương qua view ở cả PostgreSQL, SQL Server và SQLite. Có thể dùng một câu CREATE VIEW và một UPDATE giống hệt mà chắc chắn hoạt động không?

<details>
<summary>Đáp án</summary>

**Không.** PostgreSQL và SQL Server có simple updatable view theo điều kiện; SQLite cần INSTEAD OF trigger. Cần thiết kế lớp ghi theo DBMS hoặc dùng API/procedure thống nhất ở tầng ứng dụng và kiểm thử tương ứng.

</details>

### Bài 33 — CHECK OPTION và thay đổi trực tiếp bảng nền

Nếu view ACTIVE có CHECK OPTION, người có quyền UPDATE trực tiếp bảng nhan_vien có thể đặt trang_thai='INACTIVE' ở bảng nền không?

<details>
<summary>Đáp án</summary>

**Có thể**, nếu không có constraint/quyền khác cấm. CHECK OPTION của view không tự cấm các thao tác đi thẳng vào bảng nền.

</details>

### Bài 34 — Câu hỏi tổng hợp

Một view JOIN nhân viên và phòng hiển thị ma_nv,ten_nv,luong,ten_phong. Nghiệp vụ chỉ cho sửa luong, yêu cầu không âm, chống ghi đè nếu version đổi và ghi audit. Bạn sẽ chọn những lớp bảo vệ nào?

<details>
<summary>Đáp án</summary>

- Xác nhận khả năng UPDATE view JOIN theo DBMS; dùng INSTEAD OF trigger/procedure nếu cần.
- Chỉ cho phép sửa luong; từ chối thay đổi những cột khác.
- CHECK(luong >= 0) ở bảng nhan_vien.
- Dùng ma_nv và tenant_id (nếu có) làm khóa.
- Kiểm tra phien_ban trong thao tác UPDATE bảng nền, rồi tăng version.
- Ghi audit cho thay đổi có hiệu lực trong transaction phù hợp.
- Test cập nhật một hàng, nhiều hàng, lỗi constraint, version cũ, quyền và rollback.

</details>

## 43. Tình huống tổng hợp: view như giao diện ghi an toàn

Một ứng dụng nhân sự chỉ được phép **chỉnh thông tin liên hệ của nhân viên ACTIVE**, không được sửa lương hoặc phòng ban. Yêu cầu:

- Mỗi nhân viên có khóa duy nhất ma_nv (và tenant_id nếu multi-tenant).
- Các trường có thể sửa là email và số điện thoại.
- Nhân viên INACTIVE không được sửa qua giao diện này.
- Client không được đổi trang_thai để đưa hàng ra/vào phạm vi view.
- Mọi lần sửa phải có updated_at/audit và xử lý concurrency.

### 43.1. Phương án trên DBMS hỗ trợ simple updatable view

Tạo view chỉ đưa các cột cần thiết:

~~~sql
CREATE VIEW v_lien_he_active AS
SELECT
    ma_nv,
    email,
    so_dien_thoai,
    trang_thai,
    phien_ban
FROM nhan_vien
WHERE trang_thai = 'ACTIVE'
WITH CHECK OPTION;
~~~

Ví dụ này giả định bảng nghiệp vụ có thêm email, so_dien_thoai, phien_ban và DBMS hỗ trợ cú pháp. Thực tế có thể không muốn hiển thị trang_thai như một cột cho phép sửa; khi đó cần quyền theo cột hoặc thiết kế quyền khác.

DML:

~~~sql
UPDATE v_lien_he_active
SET email = :email_moi,
    phien_ban = phien_ban + 1
WHERE ma_nv = :id
  AND phien_ban = :expected_version;
~~~

**Phải** kiểm tra UPDATE này có được phép SET từng cột, có tác dụng như ý và có bảo vệ quyền trước khi đưa production. CHECK OPTION ngăn hàng mới rời khỏi view, nhưng **không tự cấm người có quyền** SET luong nếu luong được lộ trong view/quyền phù hợp; do đó cần giới hạn quyền cột/API.

### 43.2. Phương án trên SQLite hoặc view phức tạp

Tạo INSTEAD OF trigger, kiểm tra:

1. Hàng OLD đang ACTIVE.
2. Người dùng chỉ thay những trường liên hệ cho phép.
3. Giá trị NEW đạt validation.
4. UPDATE bảng nền với **ma_nv + version cũ**.
5. Nếu không có hàng nền khớp, báo conflict.
6. Đảm bảo audit và transaction.

View trigger giúp tách hợp đồng ghi khỏi cấu trúc bảng nền, nhưng việc triển khai phải kiểm soát **đầy đủ thao tác UPDATE**, không chỉ một câu UPDATE bỏ qua các điều kiện.

### 43.3. Các bước kiểm thử

- Nhân viên ACTIVE sửa email thành công.
- Nhân viên INACTIVE bị từ chối/0 hàng.
- Client không sửa được luong.
- Không được đổi trang_thai nếu bị cấm.
- Email trùng UNIQUE (nếu có) bị xử lý đúng.
- Version cũ không ghi đè bản mới.
- Trigger ghi đúng audit cho nhiều hàng.
- Transaction rollback không để dữ liệu phụ dở dang.
- Người dùng không thể bypass view qua quyền bảng nền.

## 44. Tóm tắt cần ghi nhớ

1. **View thông thường** là giao diện SELECT tới dữ liệu nền; UPDATE qua view, khi được phép, thường làm thay đổi **bảng gốc**.
2. “Updatable view” là **khả năng có điều kiện**, không phải thuộc tính mặc định của mọi view.
3. Simple view từ **một bảng với cột tham chiếu trực tiếp** là trường hợp điển hình có thể cập nhật tự động ở PostgreSQL, MySQL, SQL Server và Oracle; **SQLite không tự động cho UPDATE view**.
4. **Cột tính toán**, aggregate, GROUP BY, DISTINCT, UNION và window function thường không có ánh xạ UPDATE trực tiếp.
5. **JOIN view** có hạn chế khác nhau theo DBMS; Oracle chú ý **key-preserved table**, MySQL/SQL Server có khả năng hạn chế với một bảng nền, PostgreSQL thường cần trigger/rule cho JOIN view.
6. **WITH CHECK OPTION** kiểm tra rằng hàng sau INSERT/UPDATE qua view vẫn thuộc bộ lọc; không phải bảo vệ DELETE hoặc các đường ghi trực tiếp bảng nền.
7. **LOCAL/CASCADED** ở PostgreSQL/MySQL liên quan phạm vi điều kiện của các lớp view; không áp dụng máy móc sang hệ khác.
8. **INSTEAD OF trigger** cho phép xây logic ghi qua view phức tạp ở PostgreSQL, SQL Server, Oracle và SQLite; MySQL không có cơ chế view INSTEAD OF trigger tương ứng.
9. Trigger phải xử lý **đúng cột, đúng hàng, đúng khóa**, từ chối thao tác không hỗ trợ và đảm bảo concurrency.
10. **INSERT** qua view còn phụ thuộc NOT NULL, DEFAULT, cột tự sinh, UNIQUE, FK và CHECK ở bảng nền.
11. **DELETE** qua view có thể xóa thật hàng nền; đừng nhầm với ẩn hàng khỏi view hoặc soft delete.
12. **Materialized/indexed view** và **bảng staging/tạm** có cơ chế lưu/ghi khác view thông thường.
13. Quyền, RLS, security context, tenant và transaction vẫn quyết định có được ghi và có giữ toàn vẹn dữ liệu hay không.
14. Hãy kiểm tra metadata, phiên bản DBMS, constraint, trigger và số hàng thực sự đổi; **một câu SQL chạy được chưa chứng minh nghiệp vụ đúng**.
15. Một thiết kế tốt cần trả lời: **view ánh xạ về bảng nào, DML nào được phép, điều kiện nào phải giữ sau cập nhật và cơ chế nào kiểm soát khi nhiều người cùng sửa?**

### Tài liệu tham khảo theo DBMS

Khi triển khai thực tế, cần đọc tài liệu chính thức **đúng phiên bản**:

- **PostgreSQL Documentation:** CREATE VIEW, Automatically Updatable Views, WITH CHECK OPTION, CREATE TRIGGER, INSTEAD OF Triggers, information_schema.views, Row Security Policies.
- **MySQL Reference Manual:** Updatable and Insertable Views, View Processing Algorithms, WITH CHECK OPTION, INFORMATION_SCHEMA.VIEWS, SQL SECURITY.
- **Microsoft Learn — SQL Server:** CREATE VIEW (Transact-SQL), Modify Data Through a View, WITH CHECK OPTION, CREATE TRIGGER, INSTEAD OF Triggers, inserted/deleted Tables, SCHEMABINDING.
- **Oracle Database SQL Language Reference:** CREATE VIEW, UPDATE Statement, DML on Join Views, Key-Preserved Tables, WITH CHECK OPTION, WITH READ ONLY, INSTEAD OF Triggers, USER_UPDATABLE_COLUMNS.
- **SQLite Documentation:** CREATE VIEW, CREATE TRIGGER, INSTEAD OF Triggers, RAISE(), sqlite_schema, changes()/sqlite3_changes().
- **Java JDBC Documentation:** PreparedStatement, executeUpdate, transaction management and driver-specific row-count semantics.

**Câu hỏi tự kiểm tra cuối bài:** **“Khi UPDATE một dòng của view, DBMS có xác định được chính xác dòng và cột nào ở bảng nền cần sửa, hàng mới có còn hợp lệ theo điều kiện view không, và người dùng có thực sự được phép thực hiện thao tác đó không?”**. Trả lời được ba phần này giúp tránh phần lớn lỗi cập nhật qua view khi chuyển giữa các hệ quản trị SQL.

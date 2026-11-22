# UNIQUE và các khác biệt khi dữ liệu có NULL trong SQL

Trong cơ sở dữ liệu quan hệ, một bảng có thể cần nhiều quy tắc **không được trùng giá trị**. Mỗi khách hàng có một mã riêng, mỗi tài khoản có một tên đăng nhập riêng, hoặc trong cùng một tổ chức không được có hai sản phẩm mang cùng mã nội bộ. SQL cung cấp ràng buộc **`UNIQUE`** để hệ quản trị cơ sở dữ liệu (DBMS) kiểm soát những quy tắc như vậy ngay tại nơi lưu dữ liệu.

Vấn đề trở nên thú vị khi cột cho phép **`NULL`**: nếu hai hàng đều chưa có email, chúng có vi phạm `UNIQUE (email)` không? Nếu một khóa duy nhất gồm hai cột mà một cột là `NULL` thì sao? Câu trả lời **phụ thuộc vào cách hệ quản trị xử lý `NULL` trong ràng buộc duy nhất** và đôi khi phụ thuộc cả cấu hình, phiên bản, kiểu chỉ mục.

Bài học trình bày ngữ nghĩa của `UNIQUE`, lý do `NULL` không giống giá trị thông thường, cách khai báo ràng buộc đơn và ghép, sự khác biệt giữa PostgreSQL, MySQL, SQL Server, Oracle, và những mẫu thiết kế khi nghiệp vụ yêu cầu chỉ những giá trị đã nhập mới phải duy nhất hoặc cả trường hợp thiếu giá trị cũng phải được kiểm soát. Các ví dụ thực hành chính sử dụng **PostgreSQL**.

## 1. UNIQUE bảo đảm điều gì?

`UNIQUE` là **ràng buộc toàn vẹn** (*integrity constraint*) nhằm ngăn các hàng có giá trị trùng nhau trên một cột hoặc một tập cột được chỉ định, theo quy tắc so sánh của hệ quản trị. Nó có thể được khai báo cùng bảng khi tạo bảng hoặc thêm sau bằng `ALTER TABLE`.

Ví dụ:

~~~sql
CREATE TABLE khach_hang (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ho_ten VARCHAR(150) NOT NULL,
    email VARCHAR(255),
    CONSTRAINT uq_khach_hang_email UNIQUE (email)
);
~~~

Trong PostgreSQL, câu lệnh này có ba điểm riêng biệt:

- `id ... PRIMARY KEY`: mỗi hàng có khóa chính riêng, không `NULL`.
- `email VARCHAR(255)`: một hàng **được phép chưa có email** vì không khai báo `NOT NULL`.
- `CONSTRAINT uq_khach_hang_email UNIQUE (email)`: những **email có giá trị khác `NULL`** không được trùng nhau theo cách so sánh của cột/chỉ mục.

Ràng buộc duy nhất thuộc về **schema của bảng**. Dù dữ liệu được thêm từ một API, script SQL, công cụ quản trị hay một dịch vụ khác, DBMS vẫn kiểm tra quy tắc khi các câu lệnh ghi tác động đến cột liên quan. Điều này quan trọng khi nhiều chương trình cùng sử dụng một cơ sở dữ liệu.

### 1.1. UNIQUE khác PRIMARY KEY

| Tiêu chí | `PRIMARY KEY` | `UNIQUE` |
| --- | --- | --- |
| Mục đích | Xác định duy nhất từng hàng | Bảo đảm duy nhất cho một hoặc nhiều giá trị nghiệp vụ |
| Số lượng mỗi bảng | Tối đa một khóa chính, có thể gồm nhiều cột | Có thể có nhiều ràng buộc `UNIQUE` |
| Có cho phép `NULL`? | **Không**, các cột khóa chính phải `NOT NULL` | Có thể cho phép `NULL`; cách kiểm tra trùng `NULL` tùy DBMS |
| Ví dụ | `PRIMARY KEY (id)` | `UNIQUE (email)`, `UNIQUE (tenant_id, ma_san_pham)` |
| Cơ chế thực thi | Thường được hỗ trợ bằng chỉ mục duy nhất | Thường được hỗ trợ bằng chỉ mục duy nhất |

Một bảng có thể có khóa chính `id` và đồng thời bắt `email`, `so_dien_thoai`, hoặc tổ hợp `(ma_to_chuc, ma_nhan_vien)` phải duy nhất. **Khóa chính thay thế** (như UUID, số tự tăng) không thay thế được các quy tắc duy nhất của nghiệp vụ.

### 1.2. UNIQUE không phải CHECK hay DEFAULT

- `CHECK (gia >= 0)` kiểm tra một điều kiện trên dữ liệu được ghi; nó không tự so sánh giá trị với các hàng khác.
- `DEFAULT 'MOI'` cung cấp giá trị mặc định khi cột bị bỏ qua; nó không cấm hai hàng cùng mang giá trị `'MOI'`.
- `UNIQUE (email)` so sánh các khóa giữa các hàng để ngăn trùng theo ngữ nghĩa của DBMS.
- `NOT NULL` ngăn thiếu giá trị; tự nó **không cấm** hai hàng có cùng giá trị khác `NULL`.

Những ràng buộc này bổ sung cho nhau. Nếu một giá trị vừa **bắt buộc** vừa **duy nhất**, thông thường cần `NOT NULL` và `UNIQUE` (hoặc `PRIMARY KEY` nếu đó là khóa chính).

## 2. Hiểu NULL trước khi hiểu UNIQUE

`NULL` là dấu hiệu **không có giá trị hoặc giá trị chưa xác định** trong mô hình SQL. Nó không phải một giá trị chuỗi đặc biệt, không phải số `0`, không phải `FALSE`, và không đồng nghĩa với chuỗi rỗng `''` trong PostgreSQL.

Giả sử hai khách hàng chưa cung cấp email:

| id | ho_ten | email |
| --- | --- | --- |
| 1 | An | `NULL` |
| 2 | Bình | `NULL` |

Hai hàng đều thiếu email **không có nghĩa** hai người có cùng một địa chỉ email. Khi truy vấn:

~~~sql
SELECT NULL = NULL AS ket_qua;
~~~

Trong SQL, biểu thức so sánh thông thường `NULL = NULL` có kết quả **`UNKNOWN`** (thường hiển thị như `NULL`) chứ không phải `TRUE`. Bởi vậy câu:

~~~sql
-- Không tìm được hàng có email NULL theo cách mong muốn.
SELECT *
FROM khach_hang
WHERE email = NULL;
~~~

không đúng mục đích. Cần dùng:

~~~sql
SELECT *
FROM khach_hang
WHERE email IS NULL;
~~~

Ngược lại:

~~~sql
SELECT *
FROM khach_hang
WHERE email IS NOT NULL;
~~~

chỉ chọn khách hàng đã có email.

### 2.1. “Không biết có bằng nhau không” khác “đã xác định là khác nhau”

Trong phép so sánh của truy vấn, `NULL = NULL` không cho kết quả `TRUE`. Nhưng khi kiểm tra **tính duy nhất**, DBMS cần một quy tắc về cách xử lý những khóa có `NULL`:

- **`NULLS DISTINCT`**: xem các giá trị `NULL` là khác nhau **cho mục đích kiểm tra trùng trong `UNIQUE`**; nhiều hàng thiếu giá trị có thể cùng tồn tại.
- **`NULLS NOT DISTINCT`**: xem `NULL` như khớp với `NULL` **cho mục đích kiểm tra trùng trong `UNIQUE`**; các hàng có cùng bộ giá trị, kể cả vị trí `NULL`, sẽ xung đột.

Hai cách này là **quy tắc của phép kiểm tra duy nhất**, không thay đổi kết quả của toán tử `=` trong truy vấn SQL. PostgreSQL 15 trở lên cho phép khai báo tường minh `NULLS NOT DISTINCT` cho ràng buộc/chỉ mục duy nhất.

## 3. PostgreSQL: UNIQUE thông thường cho phép nhiều NULL

Trong PostgreSQL, mặc định ràng buộc `UNIQUE` coi các `NULL` là **distinct**. Vì vậy nhiều khách hàng chưa có email **không vi phạm** `UNIQUE (email)`.

Tạo bảng thử nghiệm độc lập:

~~~sql
CREATE TABLE email_thu_nghiem (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT,
    CONSTRAINT uq_email_thu_nghiem UNIQUE (email)
);

INSERT INTO email_thu_nghiem (email)
VALUES
    ('an@example.com'),
    (NULL),
    (NULL),
    ('binh@example.com');

SELECT id, email
FROM email_thu_nghiem
ORDER BY id;
~~~

Kết quả minh họa trên bảng mới tạo:

| id | email |
| --- | --- |
| 1 | `an@example.com` |
| 2 | `NULL` |
| 3 | `NULL` |
| 4 | `binh@example.com` |

Hai dòng `NULL` đều hợp lệ. Ngược lại, câu sau **bị từ chối** vì email đã tồn tại:

~~~sql
-- Cố tình minh họa trường hợp vi phạm:
-- INSERT INTO email_thu_nghiem (email)
-- VALUES ('an@example.com');
~~~

PostgreSQL thường trả lỗi `duplicate key value violates unique constraint` với SQLSTATE **`23505`**. Khi sử dụng qua ứng dụng, hãy dựa vào mã lỗi và tên ràng buộc phù hợp để xử lý xung đột, thay vì so khớp cứng toàn bộ câu chữ thông báo.

### 3.1. Cập nhật cũng có thể vi phạm UNIQUE

Ràng buộc không chỉ kiểm tra ở `INSERT`. Một `UPDATE` có thể biến hai giá trị trước đó khác nhau thành trùng:

~~~sql
-- Dòng id = 4 đang là binh@example.com.
-- Chuyển thành giá trị đang tồn tại -> lỗi UNIQUE:
-- UPDATE email_thu_nghiem
-- SET email = 'an@example.com'
-- WHERE id = 4;
~~~

Trong khi đó:

~~~sql
UPDATE email_thu_nghiem
SET email = NULL
WHERE id = 4;
~~~

hợp lệ theo mặc định PostgreSQL, vì sau cập nhật vẫn có thể có nhiều hàng `NULL`.

### 3.2. DISTINCT, GROUP BY và UNIQUE có ngữ nghĩa riêng

Một điểm dễ nhầm: `UNIQUE` mặc định cho phép nhiều `NULL`, nhưng `SELECT DISTINCT` thường chỉ hiển thị **một** giá trị `NULL` trong kết quả; `GROUP BY email` cũng gom các hàng có `NULL` vào **một nhóm**.

~~~sql
SELECT DISTINCT email
FROM email_thu_nghiem;

SELECT email, COUNT(*) AS so_hang
FROM email_thu_nghiem
GROUP BY email;
~~~

Vì vậy, nếu `GROUP BY` báo có nhiều hàng `NULL`, không thể kết luận rằng bảng đang vi phạm `UNIQUE (email)` mặc định trong PostgreSQL. **Phép nhóm của truy vấn và quy tắc duy nhất là hai ngữ cảnh khác nhau**.

Lưu ý thêm: `COUNT(email)` bỏ qua `NULL`; `COUNT(*)` đếm cả hàng có `NULL`. Hai hàm đếm này trả kết quả khác nhau nếu dữ liệu thiếu.

## 4. UNIQUE nhiều cột: khóa ghép và trường hợp có NULL

Ràng buộc duy nhất có thể áp dụng lên **tổ hợp các cột**, còn gọi là *composite UNIQUE*. Nó không có nghĩa từng cột riêng lẻ phải duy nhất.

Ví dụ mỗi tổ chức quản lý mã sản phẩm riêng:

~~~sql
CREATE TABLE san_pham_theo_to_chuc (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    to_chuc_id BIGINT NOT NULL,
    ma_san_pham VARCHAR(50) NOT NULL,
    ten VARCHAR(150) NOT NULL,
    CONSTRAINT uq_to_chuc_ma_san_pham
        UNIQUE (to_chuc_id, ma_san_pham)
);

INSERT INTO san_pham_theo_to_chuc
    (to_chuc_id, ma_san_pham, ten)
VALUES
    (10, 'SP001', 'Ban phim'),
    (20, 'SP001', 'Ban phim'),
    (10, 'SP002', 'Chuot');
~~~

Cả ba dòng hợp lệ: `SP001` xuất hiện ở **hai tổ chức khác nhau**. Nhưng:

~~~sql
-- Trùng bộ (to_chuc_id, ma_san_pham) = (10, 'SP001'):
-- INSERT INTO san_pham_theo_to_chuc
--     (to_chuc_id, ma_san_pham, ten)
-- VALUES (10, 'SP001', 'Ban phim khac');
~~~

bị từ chối.

### 4.1. Điều gì xảy ra nếu một thành phần của khóa ghép là NULL?

Xét một bảng khác cho phép mã sản phẩm còn thiếu:

~~~sql
CREATE TABLE ma_san_pham_tuy_chon (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    to_chuc_id BIGINT NOT NULL,
    ma_san_pham VARCHAR(50),
    CONSTRAINT uq_to_chuc_ma_tuy_chon
        UNIQUE (to_chuc_id, ma_san_pham)
);

INSERT INTO ma_san_pham_tuy_chon
    (to_chuc_id, ma_san_pham)
VALUES
    (10, NULL),
    (10, NULL),
    (10, 'SP001'),
    (20, 'SP001');
~~~

Trong **PostgreSQL mặc định**, cả bốn dòng hợp lệ:

- `(10, NULL)` được lặp vì cặp khóa có thành phần `NULL`.
- `(10, 'SP001')` và `(20, 'SP001')` khác nhau ở `to_chuc_id`.
- Một dòng `(10, 'SP001')` thứ hai bị từ chối vì **cả hai thành phần không `NULL` đều trùng**.

Quy tắc mặc định `NULLS DISTINCT` của PostgreSQL còn cho phép hai bộ `(NULL, 'SP001')` nếu cột thứ nhất cho phép `NULL`. Chỉ cần có ít nhất một vị trí `NULL` giữa các khóa cần so sánh là có thể có nhiều bộ trông giống nhau theo cách in ra màn hình, nhưng không xung đột theo quy tắc mặc định.

**Không nên suy ra từ ví dụ này rằng mọi DBMS đều cho phép lặp bộ `(10, NULL)`.** SQL Server và Oracle có những khác biệt quan trọng sẽ được phân tích ở phần tiếp theo.

### 4.2. UNIQUE (A, B) không tương đương UNIQUE (A) và UNIQUE (B)

~~~sql
CONSTRAINT uq_cung_cap UNIQUE (nha_cung_cap_id, ma_hang)
~~~

chỉ yêu cầu **cặp giá trị** là duy nhất. Nếu khai báo:

~~~sql
UNIQUE (nha_cung_cap_id),
UNIQUE (ma_hang)
~~~

thì nhà cung cấp chỉ được xuất hiện ở một hàng, và mã hàng chỉ được xuất hiện ở một hàng trên toàn bảng — một quy tắc khác hẳn, thường sai cho bảng sản phẩm. Phạm vi của tính duy nhất phải đến từ **yêu cầu nghiệp vụ**, không chỉ từ việc “trong bảng có bao nhiêu cột”.

## 5. Khác biệt giữa PostgreSQL, MySQL, SQL Server và Oracle

Đây là phần cần kiểm tra kỹ khi di chuyển schema hoặc kết nối ứng dụng với DBMS khác. Ví dụ dễ so sánh nhất là một cột `email` cho phép `NULL` và có ràng buộc `UNIQUE`.

| Hệ quản trị | UNIQUE trên **một cột nullable** | UNIQUE ghép nếu một thành phần là NULL | Cách đáp ứng yêu cầu khác |
| --- | --- | --- | --- |
| **PostgreSQL** | Mặc định cho phép **nhiều `NULL`** | Mặc định có thể lặp bộ khóa nếu có thành phần `NULL` | PostgreSQL **15+**: `UNIQUE NULLS NOT DISTINCT`; hoặc dùng unique index có điều kiện |
| **MySQL (InnoDB)** | Cho phép **nhiều `NULL`** | Có thể lặp các bộ có thành phần `NULL` theo quy tắc unique index | Thiết kế `NOT NULL`, generated column/biểu thức có quy tắc phù hợp hoặc logic bổ sung |
| **SQL Server** | Ràng buộc/chỉ mục `UNIQUE` thông thường chỉ cho **một `NULL`** ở khóa một cột | Hai bộ khóa được coi trùng nếu các thành phần tương ứng giống nhau, kể cả vị trí `NULL` | **Filtered unique index** `WHERE email IS NOT NULL` để cho nhiều `NULL` |
| **Oracle Database** | Cho phép **nhiều `NULL`** ở khóa một cột | Đối với khóa ghép **có một phần `NULL`**, các giá trị không `NULL` trùng nhau có thể gây vi phạm; bộ toàn `NULL` có thể lặp | Cần xét riêng quy tắc khóa ghép; function-based index hoặc thiết kế khác khi cần |

Tất cả các dòng trên mô tả hành vi thường gặp của các hệ quản trị nêu tên; cấu hình và phiên bản vẫn có thể ảnh hưởng đến những khía cạnh khác như collation, cú pháp expression index và khóa/chỉ mục có điều kiện. **`NULL` của `UNIQUE` là một vấn đề đặc thù DBMS, không nên lấy kết quả thử nghiệm trên PostgreSQL rồi mặc định nó đúng với SQL Server hoặc Oracle.**

### 5.1. PostgreSQL: tùy chọn NULLS NOT DISTINCT từ phiên bản 15

PostgreSQL 15 trở lên hỗ trợ:

~~~sql
CREATE TABLE ma_dinh_danh_pg15 (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_ngoai TEXT,
    CONSTRAINT uq_ma_ngoai
        UNIQUE NULLS NOT DISTINCT (ma_ngoai)
);
~~~

Với ràng buộc này:

~~~sql
INSERT INTO ma_dinh_danh_pg15 (ma_ngoai)
VALUES (NULL);                -- Thành công.

-- Cố thêm NULL lần thứ hai:
-- INSERT INTO ma_dinh_danh_pg15 (ma_ngoai)
-- VALUES (NULL);             -- Vi phạm uq_ma_ngoai.
~~~

PostgreSQL bây giờ coi các giá trị `NULL` là **không khác biệt cho việc xác định xung đột duy nhất**. Tương tự, với:

~~~sql
CREATE TABLE ma_kep_pg15 (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    to_chuc_id BIGINT,
    ma_noi_bo TEXT,
    CONSTRAINT uq_ma_kep_pg15
        UNIQUE NULLS NOT DISTINCT (to_chuc_id, ma_noi_bo)
);
~~~

hai dòng `(10, NULL)` sẽ xung đột; hai dòng `(NULL, 'SP001')` cũng xung đột; hai dòng `(NULL, NULL)` cũng xung đột. Nhưng `(10, NULL)` và `(20, NULL)` vẫn khác vì cột `to_chuc_id` khác nhau.

Có thể thể hiện quy tắc tương tự bằng **unique index**:

~~~sql
CREATE UNIQUE INDEX ux_ma_ngoai_null_khong_phan_biet
ON ma_san_pham_tuy_chon (ma_san_pham)
NULLS NOT DISTINCT;
~~~

Lệnh chỉ minh họa cú pháp trên một bảng đang tồn tại: nếu bảng có nhiều `NULL` hoặc giá trị trùng theo quy tắc mới, quá trình tạo index sẽ thất bại. Không chạy lệnh này ngay sau ví dụ `ma_san_pham_tuy_chon` đã chèn nhiều `NULL` khi chưa xử lý dữ liệu. Với PostgreSQL trước 15, không có cú pháp `NULLS NOT DISTINCT` này; phải dùng giải pháp khác khi nghiệp vụ yêu cầu.

### 5.2. MySQL: nhiều NULL được chấp nhận

Ví dụ MySQL 8.0:

~~~sql
CREATE TABLE email_mysql (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NULL,
    CONSTRAINT uq_email_mysql UNIQUE (email)
);

INSERT INTO email_mysql (email)
VALUES (NULL), (NULL), ('an@example.com');
~~~

Thông thường ba dòng đều hợp lệ trong MySQL/InnoDB. Một email đã có giá trị nếu thêm trùng sẽ xung đột. Với unique index nhiều cột, một cột `NULL` trong bộ khóa thường cho phép những bộ có thành phần `NULL` xuất hiện nhiều lần.

MySQL còn có các quy tắc riêng về **collation**, so sánh chuỗi, độ dài prefix index và kiểu dữ liệu, nên hai email khác nhau về chữ hoa/thường có thể vẫn bị coi là bằng nhau trong một collation không phân biệt hoa/thường. **Nhiều `NULL` được phép** và **hai chuỗi được coi bằng nhau hay không** là hai vấn đề tách biệt.

### 5.3. SQL Server: UNIQUE thông thường chỉ chấp nhận một NULL

Ví dụ SQL Server:

~~~sql
CREATE TABLE dbo.email_sqlserver (
    id BIGINT IDENTITY(1, 1) PRIMARY KEY,
    email NVARCHAR(255) NULL,
    CONSTRAINT uq_email_sqlserver UNIQUE (email)
);

INSERT INTO dbo.email_sqlserver (email)
VALUES (NULL);       -- Thành công.

-- Một NULL khác sẽ vi phạm UNIQUE:
-- INSERT INTO dbo.email_sqlserver (email)
-- VALUES (NULL);
~~~

Hành vi này khác PostgreSQL/MySQL với ràng buộc thông thường. Khi nghiệp vụ là “**email có thể thiếu ở nhiều người, nhưng email nào đã nhập thì phải duy nhất**”, SQL Server thường dùng **filtered unique index**:

~~~sql
CREATE TABLE dbo.email_tuy_chon_sqlserver (
    id BIGINT IDENTITY(1, 1) PRIMARY KEY,
    email NVARCHAR(255) NULL
);

CREATE UNIQUE INDEX ux_email_da_nhap
ON dbo.email_tuy_chon_sqlserver (email)
WHERE email IS NOT NULL;

INSERT INTO dbo.email_tuy_chon_sqlserver (email)
VALUES (NULL), (NULL), (N'an@example.com');
~~~

Index chỉ chứa/kiểm soát các hàng thỏa `WHERE email IS NOT NULL`, vì vậy nhiều hàng `NULL` không gây xung đột. Giá trị email đã nhập vẫn phải duy nhất. Đây là **index duy nhất có điều kiện**, không phải cú pháp `UNIQUE` constraint có mệnh đề `WHERE`.

Với khóa ghép trong SQL Server, nếu hai hàng có cùng bộ `(to_chuc_id, ma_noi_bo)`, kể cả bộ `(10, NULL)`, chúng cũng có thể xung đột dưới ràng buộc `UNIQUE` thông thường. Muốn bỏ qua một số trường hợp thiếu giá trị, phải thiết kế điều kiện index sát yêu cầu cụ thể.

### 5.4. Oracle: chú ý khóa ghép có NULL và chuỗi rỗng

Trong Oracle, `UNIQUE` **một cột** cho phép nhiều hàng có `NULL`. Tuy nhiên, khi **khóa duy nhất gồm nhiều cột**, trường hợp chỉ một phần của bộ khóa là `NULL` cần chú ý:

- Hai bộ khóa **toàn `NULL`** không bị coi là trùng theo ràng buộc unique thông thường.
- Nếu các thành phần **không `NULL` giống nhau** trong một khóa ghép có `NULL` ở các vị trí còn lại, Oracle có thể coi đó là một vi phạm duy nhất. Ví dụ hai bộ `(10, NULL)` với cùng `10` không nên được giả định là hợp lệ như trong PostgreSQL mặc định.

Một khác biệt quan trọng khác: với các kiểu chuỗi ký tự thông dụng hiện nay, Oracle xem **chuỗi rỗng `''` như `NULL`**. Bởi vậy khi kiểm tra một ràng buộc duy nhất trên email hoặc mã văn bản, việc ứng dụng truyền `''` có thể dẫn tới hành vi giống dữ liệu thiếu, trong khi PostgreSQL phân biệt `''` với `NULL`.

Ví dụ Oracle:

~~~sql
CREATE TABLE email_oracle (
    id NUMBER(19) GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email VARCHAR2(255),
    CONSTRAINT uq_email_oracle UNIQUE (email)
);
~~~

Khi thiết kế schema chung giữa Oracle và một DBMS khác, cần kiểm tra riêng **khóa ghép nullable** và **quy tắc chuỗi rỗng**. Đổi cú pháp kiểu dữ liệu mà không xem xét ngữ nghĩa có thể làm ứng dụng nhận kết quả khác trên cùng một bộ dữ liệu logic.

## 6. Chọn quy tắc UNIQUE theo ý nghĩa nghiệp vụ

Trước khi viết lệnh, cần trả lời: **thiếu giá trị có được phép không; nếu thiếu thì bao nhiêu bản ghi được phép thiếu; và phạm vi trùng được tính trên những hàng nào?**

### 6.1. Trường hợp A: bắt buộc có giá trị và phải duy nhất

Ví dụ mọi tài khoản phải có tên đăng nhập và không thể trùng:

~~~sql
CREATE TABLE tai_khoan_dang_nhap (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ten_dang_nhap VARCHAR(80) NOT NULL,
    CONSTRAINT uq_ten_dang_nhap UNIQUE (ten_dang_nhap)
);
~~~

Vì `NOT NULL`, không còn câu hỏi nhiều `NULL` có được phép hay không. `UNIQUE` ngăn các tên đăng nhập trùng nhau theo phép so sánh của DBMS. Nếu tên cần không phân biệt chữ hoa/thường, còn phải xác định quy tắc chuẩn hóa/collation hoặc index biểu thức tương ứng.

### 6.2. Trường hợp B: cho phép nhiều hàng chưa có giá trị, nhưng giá trị đã nhập phải duy nhất

Ví dụ email là thông tin tùy chọn:

| Email | Có được lưu bao nhiêu hàng? |
| --- | --- |
| `NULL` | Nhiều hàng được phép |
| `an@example.com` | Tối đa một hàng trong phạm vi quy định |
| `binh@example.com` | Tối đa một hàng trong phạm vi quy định |

Áp dụng:

- **PostgreSQL/MySQL:** `UNIQUE (email)` thông thường đáp ứng phần lớn yêu cầu này.
- **Oracle, khóa một cột:** `UNIQUE (email)` thông thường cho nhiều `NULL`; nhớ kiểm soát chuỗi rỗng.
- **SQL Server:** dùng **filtered unique index `WHERE email IS NOT NULL`**.

Nếu muốn mọi hàng thiếu email đều được lưu, đừng tự biến `NULL` thành một chuỗi hằng như `'chua_co_email'` rồi đặt `UNIQUE`: hằng này sẽ trùng ngay khi có khách hàng thứ hai chưa có email. Dùng sentinel còn có nguy cơ va chạm với dữ liệu thực và làm giảm ý nghĩa của cột.

### 6.3. Trường hợp C: cho phép NULL nhưng nhiều nhất một hàng được NULL

Đây là **quy tắc ngược** với trường hợp B:

| Email | Có được lưu bao nhiêu hàng? |
| --- | --- |
| `NULL` | Tối đa một hàng |
| Mỗi email cụ thể | Tối đa một hàng |

Trong PostgreSQL 15+:

~~~sql
CREATE TABLE ma_duy_nhat_ke_ca_thieu (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_ngoai TEXT,
    CONSTRAINT uq_ma_ke_ca_null
        UNIQUE NULLS NOT DISTINCT (ma_ngoai)
);
~~~

SQL Server có hành vi gần với yêu cầu này đối với `UNIQUE` **một cột** thông thường. MySQL/Oracle không nên được giả định có cùng hành vi: nếu cần “tối đa một giá trị thiếu”, phải thiết kế ràng buộc/index biểu thức, cấu trúc dữ liệu hoặc cơ chế kiểm soát phù hợp với DBMS.

Nếu nghiệp vụ thật sự **không cho phép thiếu giá trị**, giải pháp đơn giản và rõ nghĩa hơn là `NOT NULL UNIQUE`, thay vì cho phép một dòng `NULL`.

### 6.4. Trường hợp D: duy nhất theo tổ chức, không duy nhất toàn hệ thống

Ứng dụng đa tổ chức (*multi-tenant*) có thể cho phép hai tổ chức khác nhau cùng dùng mã nhân viên `NV001`, nhưng trong một tổ chức không được trùng:

~~~sql
CREATE TABLE nhan_vien_theo_to_chuc (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    to_chuc_id BIGINT NOT NULL,
    ma_nhan_vien VARCHAR(30) NOT NULL,
    ho_ten TEXT NOT NULL,
    CONSTRAINT uq_nhan_vien_theo_to_chuc
        UNIQUE (to_chuc_id, ma_nhan_vien)
);
~~~

Đặt `to_chuc_id NOT NULL` và `ma_nhan_vien NOT NULL` để giới hạn rõ ràng: mỗi bộ `(to_chuc_id, ma_nhan_vien)` phải duy nhất. Nếu `ma_nhan_vien` thực tế cho phép thiếu, phải quay lại câu hỏi về quy tắc `NULL` theo DBMS.

### 6.5. Trường hợp E: chỉ những bản ghi đang hoạt động mới cần duy nhất

Nhiều hệ thống dùng *soft delete*: dữ liệu đã xóa nghiệp vụ vẫn còn trong bảng để lưu lịch sử. Ví dụ email của một tài khoản bị vô hiệu hóa có thể được tái sử dụng bởi tài khoản hoạt động mới, nhưng trong **nhóm còn hoạt động** không được trùng.

PostgreSQL hỗ trợ **partial unique index**:

~~~sql
CREATE TABLE tai_khoan_co_lich_su (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT,
    xoa_luc TIMESTAMPTZ
);

CREATE UNIQUE INDEX ux_email_tai_khoan_dang_hoat_dong
ON tai_khoan_co_lich_su (email)
WHERE xoa_luc IS NULL
  AND email IS NOT NULL;
~~~

Ở đây:

- Hai bản ghi **đang hoạt động** (`xoa_luc IS NULL`) có cùng email khác `NULL` sẽ xung đột.
- Bản ghi **đã xóa mềm** (`xoa_luc IS NOT NULL`) không tham gia kiểm tra của index này.
- Nhiều bản ghi hoạt động chưa có email được phép vì điều kiện index loại `email IS NULL`.

Cần nhìn đúng yêu cầu nghiệp vụ: nếu **không được tái sử dụng email** dù tài khoản đã xóa mềm, thì index có điều kiện như trên không đáp ứng. Khi muốn cả dữ liệu lịch sử cũng phải duy nhất, phải giữ ràng buộc ở phạm vi toàn bảng hoặc chọn mô hình lưu lịch sử khác.

SQL Server cũng hỗ trợ **filtered index** với mục tiêu tương tự và cú pháp điều kiện phù hợp T-SQL. Những hệ quản trị khác có thể cần generated column, function-based index hoặc thiết kế thay thế; không mặc định mọi DBMS hỗ trợ nguyên cú pháp `CREATE UNIQUE INDEX ... WHERE ...`.

## 7. Chữ hoa/thường, khoảng trắng và chuẩn hóa dữ liệu ảnh hưởng đến UNIQUE

`UNIQUE (email)` kiểm tra **hai giá trị có được DBMS coi là bằng nhau hay không**, chứ không tự hiểu đầy đủ ý nghĩa của email, số điện thoại hoặc mã định danh nghiệp vụ.

Ví dụ:

~~~text
an@example.com
An@Example.com
 an@example.com
an@example.com 
~~~

Những chuỗi này có thể được coi là trùng hoặc khác nhau tùy **collation**, quy tắc so sánh chuỗi và cách ứng dụng chuẩn hóa. Một số DBMS/collation không phân biệt chữ hoa/thường; một số khác phân biệt. Khoảng trắng ở đầu/cuối, Unicode và cách so sánh ký tự cũng cần được xem xét.

### 7.1. UNIQUE trên giá trị gốc không phải quy tắc “không trùng sau chuẩn hóa”

Trong PostgreSQL, nếu nghiệp vụ muốn so sánh email **không phân biệt chữ hoa/thường**, có thể dùng unique expression index:

~~~sql
CREATE TABLE lien_he (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT
);

CREATE UNIQUE INDEX ux_lien_he_email_khong_phan_biet_hoa_thuong
ON lien_he (lower(email))
WHERE email IS NOT NULL;
~~~

Ví dụ này đặt quy tắc tính duy nhất trên kết quả `lower(email)`, nên hai giá trị khác nhau chỉ ở chữ hoa/thường theo quy tắc hàm/collation có thể xung đột. Đây là **chỉ mục duy nhất trên biểu thức**, không đơn thuần là `UNIQUE (email)` trên cột gốc.

Nếu cần loại cả khoảng trắng đầu/cuối, có thể cân nhắc biểu thức như `lower(btrim(email))` hoặc chuẩn hóa giá trị **trước khi lưu** trong một cột có quy tắc rõ ràng. Cần xác định quy tắc nghiệp vụ trước: với email, phần tên người dùng ở trước `@` có những đặc thù theo tiêu chuẩn; tùy hệ thống, việc chuyển toàn bộ email sang chữ thường có thể là chính sách xử lý tài khoản, không phải quy tắc luôn đúng với mọi địa chỉ có thể tồn tại.

### 7.2. UNIQUE không tự kiểm tra “đúng định dạng”

Một chuỗi `'khong-phai-email'` có thể **duy nhất** mà vẫn không phải email hợp lệ. `UNIQUE` không thay thế validation định dạng. Các ràng buộc khác hoặc tầng ứng dụng có thể kiểm tra miền giá trị, độ dài, quy tắc chuẩn hóa và quyền sử dụng.

Tương tự, `UNIQUE (so_dien_thoai)` không tự nhận ra `'0901234567'`, `'+84901234567'` và `'84 901 234 567'` có thể quy về cùng số điện thoại. Cần chuẩn hóa theo quy tắc có căn cứ trước khi áp dụng duy nhất.

### 7.3. NULL, chuỗi rỗng và chuỗi chỉ có khoảng trắng

Trong PostgreSQL:

~~~sql
SELECT
    NULL IS NULL AS gia_tri_thieu,
    '' IS NULL AS chuoi_rong_la_null,
    '   ' IS NULL AS chuoi_khoang_trang_la_null;
~~~

Kết quả logic lần lượt là `TRUE`, `FALSE`, `FALSE`. Vì vậy cột `email TEXT UNIQUE` mặc định có thể chứa **nhiều `NULL`**, nhưng thường không thể chứa nhiều chuỗi rỗng `''` giống hệt nhau theo quy tắc so sánh thông thường. Nếu ứng dụng dùng `''` để biểu diễn “không có email”, giá trị rỗng đầu tiên có thể ghi thành công còn lần thứ hai bị từ chối.

Trong Oracle, chuỗi rỗng thường được xem như `NULL`, khiến cùng một dữ liệu đầu vào có thể có kết quả khác. Quy tắc nhập liệu nên xác định rõ **thiếu giá trị thì truyền `NULL`, hay buộc người dùng nhập một giá trị hợp lệ**.

## 8. Kiểm tra trùng dữ liệu trước khi thêm UNIQUE vào bảng đã có

Khi thêm ràng buộc cho một bảng đã có dữ liệu, DBMS phải xác nhận rằng **những hàng hiện có** không vi phạm quy tắc mới. Không thể chỉ đặt `UNIQUE` rồi hy vọng dữ liệu trùng cũ sẽ tự được sửa.

Ví dụ PostgreSQL, muốn bổ sung unique cho cột email:

~~~sql
SELECT
    email,
    COUNT(*) AS so_lan
FROM khach_hang
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1
ORDER BY so_lan DESC, email;
~~~

Truy vấn chỉ chọn email **khác `NULL`**, phù hợp để phát hiện các giá trị trùng có thể vi phạm `UNIQUE (email)` mặc định PostgreSQL. Nếu không có dòng trả về, chưa chắc đã đủ để bảo đảm tạo index thành công trong mọi trường hợp (còn phụ thuộc quy tắc collation, dữ liệu thay đổi đồng thời, tên biểu thức hay trạng thái hệ thống), nhưng đây là bước khảo sát dữ liệu hữu ích.

Nếu dùng `UNIQUE NULLS NOT DISTINCT (email)`, cần kiểm tra thêm **số hàng có `NULL`**:

~~~sql
SELECT COUNT(*) AS so_hang_email_null
FROM khach_hang
WHERE email IS NULL;
~~~

Có **hơn một** hàng `NULL` thì không thể thêm ngay ràng buộc `NULLS NOT DISTINCT` trên một cột mà vẫn giữ nguyên tất cả hàng đó.

Sau khi xử lý dữ liệu theo nghiệp vụ, có thể thêm constraint:

~~~sql
ALTER TABLE khach_hang
ADD CONSTRAINT uq_email_khach_hang_moi UNIQUE (email);
~~~

**Lưu ý về ví dụ:** bảng `khach_hang` ở phần đầu đã có `uq_khach_hang_email`. Lệnh `ALTER TABLE` ngay trên chỉ là ví dụ cú pháp cho **bảng chưa có ràng buộc tương đương**; không cần tạo một ràng buộc trùng lặp trên chính bảng đã được khai báo từ đầu.

Với bảng lớn, việc tạo hoặc xác thực ràng buộc có thể tốn tài nguyên và khóa ở những mức độ khác nhau tùy DBMS. PostgreSQL có lựa chọn tạo unique index bằng cơ chế `CONCURRENTLY` với các điều kiện riêng khi triển khai, nhưng đây là vấn đề migration/vận hành; không nên áp dụng thiếu kế hoạch chỉ dựa trên ví dụ học tập.

### 8.1. Xử lý dữ liệu trùng là quyết định nghiệp vụ

Nếu phát hiện hai khách hàng đang có cùng email, không nên tự ý xóa một hàng để “qua được” lệnh tạo `UNIQUE`. Cần xác định:

- Hai hàng là bản ghi trùng cần hợp nhất hay là hai thực thể hợp lệ dùng chung địa chỉ?
- Nếu hợp nhất, các khóa ngoại, giao dịch, lịch sử và quyền truy cập sẽ được chuyển ra sao?
- Email có cần duy nhất trên toàn hệ thống hay chỉ trong một tổ chức?
- Có cần tách email liên hệ chung khỏi email dùng để đăng nhập?

Thêm ràng buộc đúng giúp ngăn dữ liệu sai trong tương lai, nhưng phải xử lý dữ liệu hiện tại phù hợp với chính sách nghiệp vụ trước.

## 9. UNIQUE trong môi trường nhiều giao dịch

Một cách thường gây lỗi khi phát triển ứng dụng:

~~~text
Giao dịch A: SELECT để kiểm tra email chưa tồn tại
Giao dịch B: SELECT để kiểm tra email chưa tồn tại
Giao dịch A: INSERT email đó
Giao dịch B: INSERT email đó
~~~

Cả hai truy vấn kiểm tra ban đầu có thể đều thấy “chưa có”. Nếu ứng dụng chỉ kiểm tra trước ở tầng code rồi chèn, đó là một **race condition**. Ràng buộc duy nhất tại database là tuyến phòng vệ bảo đảm không có hai giá trị xung đột cùng được xác nhận theo quy tắc `UNIQUE`.

Trong PostgreSQL có thể sử dụng câu lệnh:

~~~sql
INSERT INTO email_thu_nghiem (email)
VALUES ('an@example.com')
ON CONFLICT (email) DO NOTHING
RETURNING id, email;
~~~

Nếu email đó đã tồn tại, câu lệnh **không chèn hàng mới** và `RETURNING` không trả về hàng được chèn; không có nghĩa DB tự trả về ID của hàng đã có. Nếu email là `NULL`, với unique index mặc định của PostgreSQL, nhiều `NULL` **không phải xung đột**, nên `ON CONFLICT` sẽ không cản việc chèn một hàng `NULL` mới.

Ứng dụng có thể dùng `ON CONFLICT DO UPDATE` khi có nghiệp vụ cập nhật bản ghi đang tồn tại, nhưng phải xác định rõ điều kiện và cột được phép thay đổi. Không nên tự động ghi đè dữ liệu của người khác chỉ vì họ có cùng một giá trị được coi là duy nhất.

### 9.1. Khi DB báo lỗi duy nhất

Nếu không dùng `ON CONFLICT` hoặc cơ chế tương đương, ứng dụng cần:

1. Bắt lỗi vi phạm duy nhất do DBMS/driver báo về;
2. Xác định ràng buộc nào bị vi phạm (ví dụ email, mã tổ chức);
3. Trả về lỗi nghiệp vụ rõ ràng hoặc thực hiện chính sách retry phù hợp;
4. Xử lý tình trạng giao dịch theo quy tắc của DBMS.

Trong PostgreSQL, một câu lệnh gây lỗi bên trong giao dịch có thể làm giao dịch chuyển sang **trạng thái lỗi**, cần rollback (hoặc xử lý bằng savepoint phù hợp) trước khi tiếp tục. Không nên giả định sau lỗi `23505` vẫn có thể chạy các câu tiếp theo và commit giao dịch như bình thường.

**Đặc biệt với `NULL`:** một ràng buộc `UNIQUE` chỉ bảo vệ các giá trị được coi xung đột. Nếu DBMS mặc định cho phép nhiều `NULL`, ứng dụng không thể dựa vào lỗi unique để thực thi yêu cầu “chỉ có một bản ghi chưa có email”. Phải chọn ràng buộc/chỉ mục phù hợp ngay từ thiết kế.

## 10. UNIQUE constraint và UNIQUE index có giống nhau không?

Hai khái niệm có liên quan nhưng không hoàn toàn đồng nhất:

| Khái niệm | Vai trò chính | Ví dụ |
| --- | --- | --- |
| **UNIQUE constraint** | Quy tắc toàn vẹn được khai báo trong schema bảng | `CONSTRAINT uq_email UNIQUE (email)` |
| **UNIQUE index** | Cấu trúc chỉ mục duy nhất hỗ trợ kiểm tra khóa, có thể hỗ trợ biểu thức/điều kiện tùy DBMS | `CREATE UNIQUE INDEX ... ON ... (lower(email))` |

Trong PostgreSQL, khai báo `UNIQUE` constraint thường tự tạo một B-tree unique index để thực thi quy tắc. Không cần tạo thêm một unique index tương đương trên cùng cột chỉ để “bảo đảm chắc chắn hơn”: sự lặp lại không đem lại một quy tắc mới, có thể tăng chi phí lưu trữ và ghi dữ liệu.

Tuy nhiên unique index có thể thể hiện những yêu cầu mà cú pháp constraint thông thường khó diễn đạt, như:

~~~sql
-- Chỉ kiểm soát email có giá trị của tài khoản chưa xóa mềm.
CREATE UNIQUE INDEX ux_email_hoat_dong
ON tai_khoan_co_lich_su (email)
WHERE xoa_luc IS NULL AND email IS NOT NULL;

-- So sánh email sau khi chuyển thành chữ thường.
CREATE UNIQUE INDEX ux_email_lower
ON lien_he (lower(email))
WHERE email IS NOT NULL;
~~~

Không mọi DBMS có cùng tập tính năng, cách optimizer dùng index hoặc cách tham chiếu unique index trong khóa ngoại. **Điều kiện chính để thiết kế vẫn là quy tắc toàn vẹn nghiệp vụ và cơ chế DBMS thực thi nó**, chứ không chỉ là tên “index” hay “constraint”.

### 10.1. Ràng buộc UNIQUE hoãn kiểm tra

Một số DBMS, trong đó có PostgreSQL và Oracle, hỗ trợ ràng buộc duy nhất **deferrable** theo điều kiện cú pháp và cấu hình. Điều này cho phép một số kiểm tra được dời đến cuối giao dịch, hữu ích khi cần hoán đổi các giá trị duy nhất giữa hai hàng trong cùng giao dịch.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE vi_tri_xep_hang (
    id BIGINT PRIMARY KEY,
    vi_tri INTEGER NOT NULL,
    CONSTRAINT uq_vi_tri
        UNIQUE (vi_tri) DEFERRABLE INITIALLY IMMEDIATE
);
~~~

Nếu ứng dụng cần một giao dịch tạm thời có giá trị trùng ở giữa các bước nhưng cuối cùng toàn bộ dữ liệu trở về trạng thái hợp lệ, có thể chủ động trì hoãn kiểm tra ràng buộc phù hợp qua `SET CONSTRAINTS` trong PostgreSQL. Tính năng này phụ thuộc DBMS, loại ràng buộc và cách thực thi; **không được xem mọi `UNIQUE` đều tự động hoãn kiểm tra**. Trong PostgreSQL, ràng buộc duy nhất có thể hoãn không thể dùng làm arbiter cho `INSERT ... ON CONFLICT`, nên cần thiết kế phù hợp khi sử dụng UPSERT.

## 11. Các tình huống dễ nhầm và cách hiểu đúng

| Nhận định dễ nhầm | Cách hiểu chính xác |
| --- | --- |
| “UNIQUE luôn cấm hai NULL.” | Sai nếu khái quát: PostgreSQL/MySQL/Oracle với khóa một cột thường cho nhiều `NULL`; SQL Server thông thường chỉ cho một. |
| “NULL = NULL là TRUE.” | Phép so sánh thông thường trả `UNKNOWN`. Quy tắc xung đột của `UNIQUE` là cơ chế riêng. |
| “Trong UNIQUE ghép, NULL luôn cho phép trùng.” | Không đúng với mọi DBMS; Oracle và SQL Server cần được xét riêng. |
| “UNIQUE (A, B) có nghĩa A và B đều riêng lẻ duy nhất.” | Nó yêu cầu **tổ hợp (A, B)** duy nhất theo ngữ nghĩa DBMS. |
| “PRIMARY KEY và UNIQUE giống nhau về NULL.” | `PRIMARY KEY` không cho `NULL`; `UNIQUE` có thể cho. |
| “UNIQUE sẽ ngăn chuỗi rỗng giống NULL.” | Chuỗi rỗng và `NULL` khác nhau ở nhiều DBMS; Oracle có hành vi riêng. |
| “UNIQUE tự chuyển email về chữ thường.” | Nó so sánh theo kiểu dữ liệu/collation/index; cần quy tắc chuẩn hóa rõ. |
| “Kiểm tra SELECT trước INSERT là đủ ngăn trùng.” | Có race condition khi nhiều giao dịch cùng ghi; cần ràng buộc DB. |
| “ON CONFLICT sẽ ngăn mọi hàng NULL trùng.” | Chỉ xử lý xung đột mà unique index/constraint thực tế phát hiện. |
| “Đổi DEFAULT hoặc thêm NOT NULL giống UNIQUE.” | `DEFAULT`, `NOT NULL`, `UNIQUE` phục vụ các mục đích khác nhau. |
| “Thêm UNIQUE vào bảng cũ sẽ tự sửa dữ liệu trùng.” | DBMS sẽ từ chối tạo ràng buộc nếu dữ liệu không thỏa điều kiện. |

## 12. Bài tập thực hành có lời giải

### Bài 1: Dự đoán INSERT vào UNIQUE nullable của PostgreSQL

Tạo bảng:

~~~sql
CREATE TABLE bai_tap_email (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE
);
~~~

Cho các lệnh:

~~~sql
INSERT INTO bai_tap_email VALUES (1, NULL);
INSERT INTO bai_tap_email VALUES (2, NULL);
INSERT INTO bai_tap_email VALUES (3, 'a@example.com');
-- INSERT INTO bai_tap_email VALUES (4, 'a@example.com');
~~~

**Câu hỏi:** Lệnh nào hợp lệ?

**Lời giải:** Ba lệnh đầu hợp lệ trong PostgreSQL mặc định. Lệnh thứ tư (đang chú thích) vi phạm `UNIQUE (email)`, vì `'a@example.com'` đã tồn tại. Hai `NULL` không xung đột theo quy tắc mặc định.

### Bài 2: Một email chưa biết nhưng chỉ có một vị trí “thiếu”

Yêu cầu: cột `ma_tham_chieu` cho phép `NULL`, nhưng không được có **hai hàng cùng `NULL`**. Viết bảng trên PostgreSQL 15+.

**Một lời giải:**

~~~sql
CREATE TABLE bai_tap_ma_tham_chieu (
    id INTEGER PRIMARY KEY,
    ma_tham_chieu TEXT,
    CONSTRAINT uq_ma_tham_chieu
        UNIQUE NULLS NOT DISTINCT (ma_tham_chieu)
);
~~~

Nếu nghiệp vụ thực ra yêu cầu **mọi hàng đều phải có mã**, thay thế bằng `ma_tham_chieu TEXT NOT NULL UNIQUE` là rõ nghĩa hơn.

### Bài 3: Khóa ghép có NULL

Trong PostgreSQL, bảng có:

~~~sql
CREATE TABLE bai_tap_kep (
    id INTEGER PRIMARY KEY,
    to_chuc_id INTEGER NOT NULL,
    ma TEXT,
    UNIQUE (to_chuc_id, ma)
);
~~~

Có thể chèn lần lượt các bộ `(10, NULL)`, `(10, NULL)`, `(10, 'A')`, `(10, 'A')` không?

**Lời giải:** Hai bộ `(10, NULL)` hợp lệ theo mặc định PostgreSQL. Bộ `(10, 'A')` đầu tiên hợp lệ, bộ thứ hai vi phạm `UNIQUE (to_chuc_id, ma)`. Nếu dùng `UNIQUE NULLS NOT DISTINCT` trong PostgreSQL 15+, bộ `(10, NULL)` thứ hai cũng bị từ chối.

### Bài 4: SQL Server với email tùy chọn

Yêu cầu: có thể lưu nhiều khách hàng chưa nhập email, nhưng không được có hai email giống nhau. Viết cơ chế chính trong SQL Server.

**Lời giải:**

~~~sql
CREATE TABLE dbo.bai_tap_email_tuy_chon (
    id BIGINT IDENTITY(1, 1) PRIMARY KEY,
    email NVARCHAR(255) NULL
);

CREATE UNIQUE INDEX ux_email_tuy_chon
ON dbo.bai_tap_email_tuy_chon (email)
WHERE email IS NOT NULL;
~~~

`UNIQUE (email)` thông thường của SQL Server **không** đáp ứng yêu cầu “nhiều `NULL`” như trên, vì thường chỉ cho một `NULL` trên một cột.

### Bài 5: Duy nhất cho các bản ghi chưa bị xóa mềm

Trong PostgreSQL, bảng `tai_khoan` có `email TEXT` và `xoa_luc TIMESTAMPTZ` (`NULL` nghĩa là còn hoạt động). Cho phép tài khoản đã xóa mềm giữ lại email cũ, nhưng cấm hai tài khoản còn hoạt động dùng cùng email đã nhập.

**Lời giải:**

~~~sql
CREATE TABLE bai_tap_tai_khoan (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT,
    xoa_luc TIMESTAMPTZ
);

CREATE UNIQUE INDEX ux_bai_tap_email_hoat_dong
ON bai_tap_tai_khoan (email)
WHERE xoa_luc IS NULL AND email IS NOT NULL;
~~~

Đây là unique index có điều kiện. Nếu muốn email được so sánh không phân biệt hoa/thường, yêu cầu còn cần áp dụng quy tắc chuẩn hóa hoặc biểu thức index phù hợp.

### Bài 6: Vì sao cần UNIQUE khi đã SELECT kiểm tra?

Hai yêu cầu tạo tài khoản cùng lúc đều kiểm tra `SELECT 1 FROM tai_khoan WHERE email = ...` và cùng thấy chưa có email. Liệu kiểm tra ở tầng ứng dụng đã đủ chưa?

**Lời giải:** Chưa. Kết quả `SELECT` có thể đã cũ khi một giao dịch khác ghi giá trị đó. `UNIQUE` tại DB giúp phát hiện xung đột khi ghi; ứng dụng vẫn cần bắt lỗi, thông báo phù hợp và quản lý transaction/retry theo nghiệp vụ.

### Bài 7: Đọc kết quả thống kê các NULL

Giả sử bảng PostgreSQL có `email UNIQUE` với các giá trị: `NULL`, `NULL`, `'a@example.com'`. Truy vấn:

~~~sql
SELECT email, COUNT(*) AS so_luong
FROM bai_tap_email
GROUP BY email;
~~~

có thể trả về một nhóm `NULL` với `so_luong = 2` hay không?

**Lời giải:** Có, nếu những giá trị đã được lưu trong bảng. `GROUP BY` gom `NULL` vào cùng một nhóm; `UNIQUE` mặc định PostgreSQL vẫn cho phép nhiều `NULL`. Hai tính chất không mâu thuẫn.

## 13. Tóm lược cách lựa chọn quy tắc

Trước khi thêm `UNIQUE`, hãy diễn đạt yêu cầu nghiệp vụ bằng câu đầy đủ rồi chọn cơ chế:

| Yêu cầu | Cơ chế nên cân nhắc |
| --- | --- |
| Bắt buộc có giá trị và không được trùng | `NOT NULL` kết hợp `UNIQUE`, hoặc `PRIMARY KEY` cho khóa chính |
| Chưa có giá trị được phép ở nhiều hàng, các giá trị đã nhập phải duy nhất | `UNIQUE` thông thường trong PostgreSQL/MySQL/Oracle (khóa một cột); filtered index ở SQL Server |
| Tối đa một hàng có `NULL` và không trùng giá trị đã nhập | PostgreSQL 15+ `UNIQUE NULLS NOT DISTINCT`; SQL Server `UNIQUE` thông thường với khóa một cột; DBMS khác cần cơ chế khác |
| Mã chỉ cần duy nhất trong phạm vi tổ chức | `UNIQUE (to_chuc_id, ma)`; xem xét cột nullable |
| Chỉ hàng đang hoạt động phải duy nhất | Partial/filtered unique index khi DBMS hỗ trợ |
| Không trùng sau khi chuẩn hóa chữ hoa/thường | Quy tắc chuẩn hóa nhất quán, collation phù hợp hoặc unique index trên biểu thức |
| Bảng đã có dữ liệu | Khảo sát trùng theo **đúng** quy tắc sắp áp dụng, xử lý dữ liệu trước rồi triển khai constraint/index |

**Điểm cốt lõi:** `UNIQUE` bảo vệ tính duy nhất nhưng không tự quyết định “thiếu giá trị” nghĩa là gì trong nghiệp vụ. Với `NULL`, cùng một lược đồ nhìn qua có vẻ giống nhau vẫn có thể chấp nhận những bộ dữ liệu khác nhau giữa PostgreSQL, MySQL, SQL Server và Oracle. Thiết kế đáng tin cậy cần xác định rõ **phạm vi duy nhất, cách đối xử với `NULL`, cách so sánh chuỗi và trạng thái bản ghi**, rồi mới chọn `UNIQUE` constraint hoặc unique index thích hợp.

# Tạo dữ liệu liên quan và lấy khóa vừa sinh trong SQL

Một thao tác thêm dữ liệu thường không dừng ở một bảng. Khi người dùng tạo đơn hàng, hệ thống có thể phải:

1. Thêm **đơn hàng** vào bảng cha.
2. Nhận **khóa chính vừa được cơ sở dữ liệu sinh ra**.
3. Thêm các **dòng chi tiết đơn**, mỗi dòng chứa khóa ngoại trỏ về đúng đơn vừa tạo.
4. Bảo đảm các bước liên quan **cùng thành công hoặc cùng bị hoàn tác** nếu xảy ra lỗi.

Ví dụ:

~~~text
Khách hàng An
    │
    │ tạo đơn
    ▼
Đơn hàng id = 501       ← ID do database sinh
    │
    ├── Dòng 1: Sách SQL × 2, don_hang_id = 501
    └── Dòng 2: Sổ tay  × 1, don_hang_id = 501
~~~

Nếu ứng dụng đoán ID bằng `MAX(id) + 1`, hoặc tạo đơn xong nhưng quên dùng giao dịch để thêm chi tiết, nó có thể gắn các dòng vào nhầm đơn hoặc để lại đơn hàng thiếu chi tiết khi gặp lỗi.

Bài này thuộc chương **Thêm dữ liệu** của module **Database SQL**, tập trung vào việc **tạo dữ liệu có quan hệ và lấy khóa vừa sinh**. Ví dụ SQL chính dùng **PostgreSQL**; phần ứng dụng dùng **Java/JDBC**. Cuối bài có so sánh cách lấy khóa trên MySQL, MariaDB, SQL Server, Oracle và SQLite.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Xác định thứ tự thêm các bảng có quan hệ **cha–con** qua khóa chính và khóa ngoại.
- Tạo khóa chính tự sinh bằng `GENERATED ... AS IDENTITY` trong PostgreSQL.
- Lấy ID vừa được tạo bằng `INSERT ... RETURNING id`, không suy đoán bằng `MAX(id)`.
- Dùng ID vừa nhận để thêm đúng các dòng chi tiết.
- Tạo cha và con trong **một statement PostgreSQL** với data-modifying CTE và `RETURNING`.
- Tạo nhiều hàng và biết cách **ánh xạ từng khóa sinh ra với từng dữ liệu đầu vào**.
- Dùng `BEGIN`, `COMMIT`, `ROLLBACK` hoặc transaction JDBC để giữ tính nhất quán.
- Hiểu các trường hợp thiếu bản ghi tham chiếu, vi phạm FK, UNIQUE, CHECK và dữ liệu chèn được 0 hàng.
- Tránh các lỗi cạnh tranh khi nhiều người cùng thêm dữ liệu, xử lý thử lại yêu cầu và khóa nghiệp vụ.
- Chọn cách lấy khóa phù hợp theo DBMS và driver mà không lẫn ID giữa các kết nối.

## 2. Mô hình dữ liệu cha–con

Trong cơ sở dữ liệu quan hệ, **khóa chính (PRIMARY KEY)** định danh hàng trong bảng. **Khóa ngoại (FOREIGN KEY)** lưu tham chiếu đến khóa được phép tồn tại ở bảng khác.

Mô hình bán hàng:

~~~text
lk_khach_hang
  id (PK)
  email (UNIQUE)
  ho_ten
       │
       │ 1 ─── N
       ▼
lk_don_hang
  id (PK, tự sinh)
  khach_hang_id (FK)
  ma_yeu_cau (UNIQUE, tùy chọn)
  trang_thai
  tao_luc
       │
       │ 1 ─── N
       ▼
lk_dong_don
  id (PK, tự sinh)
  don_hang_id (FK)
  san_pham_id (FK)
  so_luong
  don_gia
       ▲
       │ N ─── 1
lk_san_pham
  id (PK, tự sinh)
  ma_sp (UNIQUE)
  ten
  gia_hien_tai
~~~

Một đơn hàng có thể chứa nhiều dòng, nhưng mỗi dòng chỉ thuộc **một đơn hàng** qua `don_hang_id`. Bảng `lk_dong_don` còn trỏ đến sản phẩm qua `san_pham_id`.

Ở dữ liệu này, một đơn mới có thể cần hai loại khóa ngoại:

- `khach_hang_id`: lấy từ **khách hàng đã tồn tại**.
- `don_hang_id`: lấy từ **đơn hàng vừa được tạo**.

Đây là hai bài toán khác nhau. Khóa khách hàng phải xác định đúng từ dữ liệu hiện có; còn khóa đơn hàng do DBMS sinh khi INSERT, cần lấy lại an toàn ngay từ thao tác đó.

### 2.1. Thứ tự thông thường khi thêm dữ liệu liên quan

Nếu chưa có khách hàng/sản phẩm:

~~~text
Tạo khách hàng ─────────────────┐
                               ▼
                         Tạo đơn hàng ──► Lấy id đơn
                               │
Tạo/tra cứu sản phẩm ───────────┤
                               ▼
                         Tạo các dòng đơn
                               │
                               ▼
                        COMMIT giao dịch
~~~

Trong mô hình FK thông thường được kiểm tra ngay, bạn không thể thêm dòng đơn trỏ tới một đơn **chưa tồn tại**.

Có những cơ sở dữ liệu hỗ trợ kiểm tra FK trì hoãn trong những tình huống đặc biệt, nhưng đó không phải lý do để bỏ qua quy tắc cơ bản: **tạo bản ghi được tham chiếu trước, rồi tạo bản ghi tham chiếu**.

## 3. Bộ dữ liệu thực hành PostgreSQL

Thực hành trong **database thử nghiệm**, sử dụng cùng một phiên kết nối. Các bảng trong bài có tiền tố `lk_` và là **TEMP TABLE**, không phải bảng sản xuất.

### 3.1. Bảng khách hàng

~~~sql
CREATE TEMP TABLE lk_khach_hang (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    ho_ten TEXT NOT NULL
);
~~~

`GENERATED ALWAYS AS IDENTITY` khai báo một cột dùng cơ chế sinh giá trị từ sequence được DBMS quản lý. Khi INSERT thông thường, ta **không cung cấp id**, để PostgreSQL tự sinh.

### 3.2. Bảng sản phẩm

~~~sql
CREATE TEMP TABLE lk_san_pham (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_sp TEXT NOT NULL UNIQUE,
    ten TEXT NOT NULL,
    gia_hien_tai NUMERIC(12,2) NOT NULL
        CHECK (gia_hien_tai >= 0)
);
~~~

`ma_sp` là mã sản phẩm có ý nghĩa nghiệp vụ, dùng để tra cứu; `id` là khóa kỹ thuật của bảng.

### 3.3. Bảng đơn hàng

~~~sql
CREATE TEMP TABLE lk_don_hang (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    khach_hang_id BIGINT NOT NULL
        REFERENCES lk_khach_hang(id),
    ma_yeu_cau TEXT UNIQUE,
    trang_thai TEXT NOT NULL DEFAULT 'NEW'
        CHECK (trang_thai IN ('NEW', 'PAID', 'CANCELLED')),
    tao_luc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Bảng này có:

- `id` tự sinh: khóa chính để nối dòng đơn.
- `khach_hang_id`: FK đến khách hàng.
- `ma_yeu_cau`: mã nghiệp vụ/khóa yêu cầu tùy chọn, có UNIQUE để minh họa kiểm soát việc gửi lại yêu cầu.
- `trang_thai` có DEFAULT 'NEW' và CHECK.
- `tao_luc` tự lấy thời điểm theo cơ sở dữ liệu khi không truyền giá trị.

Trong PostgreSQL, UNIQUE mặc định cho phép nhiều giá trị `NULL`, nên nhiều đơn có thể không có `ma_yeu_cau`. Nếu ứng dụng cần mọi đơn đều có mã này, nên thêm `NOT NULL` và bảo đảm quy tắc tạo mã ở tầng nghiệp vụ.

### 3.4. Bảng dòng đơn

~~~sql
CREATE TEMP TABLE lk_dong_don (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    don_hang_id BIGINT NOT NULL
        REFERENCES lk_don_hang(id),
    san_pham_id BIGINT NOT NULL
        REFERENCES lk_san_pham(id),
    so_luong INTEGER NOT NULL CHECK (so_luong > 0),
    don_gia NUMERIC(12,2) NOT NULL CHECK (don_gia >= 0),
    UNIQUE (don_hang_id, san_pham_id)
);
~~~

Ở ví dụ đơn giản này, một sản phẩm xuất hiện **tối đa một dòng trong cùng đơn** nhờ UNIQUE `(don_hang_id, san_pham_id)`. Hệ thống thật có thể cho phép nhiều dòng cùng sản phẩm do chương trình khuyến mãi, lô hàng hoặc lựa chọn khác; khi ấy khóa và mô hình chi tiết phải thay đổi theo nghiệp vụ.

`don_gia` trong dòng đơn là **giá được ghi nhận khi tạo đơn**, không phải tham chiếu trực tiếp tới `gia_hien_tai` mỗi lần đọc. Khi giá danh mục thay đổi, đơn hàng lịch sử vẫn phải có khả năng lưu giá tại thời điểm giao dịch.

### 3.5. Nạp dữ liệu danh mục

~~~sql
INSERT INTO lk_khach_hang (email, ho_ten)
VALUES
    ('an@example.test', 'An'),
    ('binh@example.test', 'Bình')
RETURNING id, email, ho_ten;

INSERT INTO lk_san_pham (ma_sp, ten, gia_hien_tai)
VALUES
    ('SACH_SQL', 'Sách SQL', 120000),
    ('SO_TAY', 'Sổ tay', 30000),
    ('BUT', 'Bút', 10000)
RETURNING id, ma_sp, ten, gia_hien_tai;
~~~

Các kết quả `RETURNING` chứa ID được DBMS sinh trong **phiên thực hành của bạn**. Không cần giả định khách An luôn có ID 1 hoặc sách luôn có ID 1. Mã email và `ma_sp` giúp tra cứu đúng bản ghi mà không phụ thuộc con số sequence.

**Lưu ý khi chạy ví dụ:** một số lệnh tiếp theo sẽ thực sự INSERT thêm đơn/dòng. Chúng dùng các `ma_yeu_cau` khác nhau để tách tình huống. Chạy lại nguyên cùng lệnh INSERT có mã UNIQUE cố định sẽ gặp lỗi trùng, đây là hành vi ràng buộc đúng. Có thể bắt đầu lại bằng phiên kết nối thử nghiệm mới để khởi tạo lại bảng tạm.

## 4. Khóa tự sinh: IDENTITY, sequence và DEFAULT

### 4.1. Không tự điền giá trị ID khi DBMS đã chịu trách nhiệm

Đúng với bảng `lk_don_hang`:

~~~sql
INSERT INTO lk_don_hang (khach_hang_id)
SELECT id
FROM lk_khach_hang
WHERE email = 'an@example.test'
RETURNING id, khach_hang_id, trang_thai, tao_luc;
~~~

Không đưa cột `id` vào danh sách INSERT. PostgreSQL tự lấy giá trị từ sequence của identity.

Lệnh dưới **không phải cách INSERT thông thường** cho cột `GENERATED ALWAYS`:

~~~sql
-- Không áp dụng như một INSERT mặc định của GENERATED ALWAYS.
INSERT INTO lk_don_hang (id, khach_hang_id)
VALUES (500, 1);
~~~

PostgreSQL có cơ chế cho phép ghi đè ID trong các trường hợp đặc biệt bằng `OVERRIDING SYSTEM VALUE`, nhưng đây không phải cách dùng cho nghiệp vụ tạo đơn thông thường. Gán ID thủ công có thể gây xung đột hoặc khiến ứng dụng lệch quy tắc quản lý sequence.

### 4.2. GENERATED ALWAYS khác GENERATED BY DEFAULT

PostgreSQL hỗ trợ:

~~~sql
id BIGINT GENERATED ALWAYS AS IDENTITY
~~~

và:

~~~sql
id BIGINT GENERATED BY DEFAULT AS IDENTITY
~~~

- `ALWAYS`: ưu tiên bắt DBMS sinh ID; ghi ID tường minh cần cú pháp ghi đè thích hợp.
- `BY DEFAULT`: DBMS sinh ID khi không có giá trị được cung cấp, nhưng cho phép cung cấp giá trị tường minh theo các quy tắc cột.

Cả hai có thể được dùng làm khóa chính. **PRIMARY KEY** và **IDENTITY** làm hai nhiệm vụ: PRIMARY KEY bảo đảm tính duy nhất/không NULL của khóa, còn IDENTITY cung cấp giá trị mới.

### 4.3. ID không nhất thiết tăng liên tục không hở

Identity thường dựa trên sequence. Sequence có thể tiêu thụ giá trị dù transaction sau đó ROLLBACK, hoặc có khoảng trống do cache, xử lý lỗi và thao tác quản trị.

Ví dụ các đơn có ID 501, 502 rồi 504 **không chứng minh thiếu một đơn nghiệp vụ**; ID 503 có thể đã được cấp nhưng giao dịch bị hoàn tác. Không dùng khóa tự sinh làm số thứ tự hóa đơn phải liên tục nếu nghiệp vụ có quy tắc số chứng từ nghiêm ngặt; cần cơ chế quản lý riêng.

## 5. Lấy khóa vừa sinh bằng RETURNING

Trong PostgreSQL, cách trực tiếp nhất là thêm `RETURNING` vào INSERT:

~~~sql
INSERT INTO lk_don_hang
    (khach_hang_id, ma_yeu_cau)
SELECT
    kh.id,
    'DEMO-RETURNING-01'
FROM lk_khach_hang AS kh
WHERE kh.email = 'an@example.test'
RETURNING
    id,
    khach_hang_id,
    ma_yeu_cau,
    trang_thai,
    tao_luc;
~~~

Giả sử DBMS cấp ID `501`, bạn có thể thấy một hàng:

| id | khach_hang_id | ma_yeu_cau | trang_thai |
|---:|---:|---|---|
| 501 | *ID của An* | DEMO-RETURNING-01 | NEW |

Con số **501 chỉ là minh họa**, không phải kết quả được bảo đảm. Cột `id` trả về là **khóa của chính hàng vừa được INSERT**.

### 5.1. RETURNING không cần SELECT MAX(id)

Cách không an toàn:

~~~sql
-- KHÔNG dùng để lấy khóa của đơn vừa tạo!
SELECT MAX(id) AS id_moi_nhat
FROM lk_don_hang;
~~~

Nếu nhiều kết nối cùng chèn đơn, `MAX(id)` có thể là ID của **đơn do kết nối khác tạo ra**. Ngay cả khi chỉ một người thao tác, `MAX(id)` vẫn diễn đạt “giá trị ID lớn nhất trong bảng”, chứ không phải “ID của INSERT mà tôi vừa thực hiện”.

Cách đúng theo PostgreSQL:

~~~sql
INSERT INTO lk_don_hang (...)
VALUES (...)
RETURNING id;
~~~

Ở đây `...` chỉ là vị trí minh họa để nhớ cú pháp; lệnh hoàn chỉnh đã có ở trên.

### 5.2. RETURNING có thể trả nhiều cột

Ngoài ID, ứng dụng có thể cần giá trị mặc định do DBMS đặt:

~~~sql
INSERT INTO lk_don_hang
    (khach_hang_id, ma_yeu_cau)
SELECT
    id,
    'DEMO-RETURNING-02'
FROM lk_khach_hang
WHERE email = 'binh@example.test'
RETURNING id, trang_thai, tao_luc;
~~~

Ứng dụng nhận cùng lúc:

- ID mới.
- Trạng thái mặc định `NEW`.
- Thời điểm tạo do database cung cấp.

Với các cột DEFAULT, generated columns hoặc thay đổi phù hợp do trigger trước khi ghi, `RETURNING` có thể giúp quan sát giá trị hàng được ghi thực tế. Không nên tự tính lại giá trị ở ứng dụng nếu database là nguồn chính thức của giá trị ấy.

### 5.3. INSERT ... SELECT có thể không thêm hàng nào

Ở ví dụ INSERT đơn bằng SELECT khách theo email:

~~~sql
INSERT INTO lk_don_hang (khach_hang_id)
SELECT id
FROM lk_khach_hang
WHERE email = 'khong_co@example.test'
RETURNING id;
~~~

Nếu không có khách với email này, `SELECT` nguồn trả **0 hàng**. Khi đó INSERT cũng thêm **0 hàng**, `RETURNING` trả **0 hàng**, nhưng không nhất thiết ném lỗi.

Đây là tình huống phải kiểm tra ở ứng dụng: nếu yêu cầu bắt buộc tạo đúng một đơn, **0 hàng là thất bại nghiệp vụ** dù statement không vi phạm cú pháp hay ràng buộc.

### 5.4. Hàng mới từ RETURNING thuộc statement của bạn

`RETURNING` gắn trực tiếp với statement INSERT đang chạy và không bị nhầm với hàng người khác chèn sau đó. Đây là lý do nó phù hợp hơn truy vấn `MAX(id)` hoặc chọn hàng mới nhất theo thời gian.

## 6. Thêm dòng con sau khi có ID cha

Giả sử ứng dụng vừa thực thi INSERT đơn và nhận `don_hang_id = 501`. Trong chương trình, ta giữ ID đó trong biến rồi dùng làm tham số cho INSERT dòng:

~~~sql
-- Mẫu cho lệnh có tham số của ứng dụng:
INSERT INTO lk_dong_don
    (don_hang_id, san_pham_id, so_luong, don_gia)
SELECT
    :don_hang_id,
    sp.id,
    :so_luong,
    sp.gia_hien_tai
FROM lk_san_pham AS sp
WHERE sp.ma_sp = :ma_sp;
~~~

Các ký hiệu `:don_hang_id`, `:so_luong` và `:ma_sp` trong đoạn này là **tham số minh họa**, không phải cú pháp PostgreSQL thuần có thể dán nguyên vào mọi SQL client. Với JDBC, chúng được truyền thành các vị trí `?`; ở một số thư viện khác có thể dùng named parameters.

Cách điền:

- `don_hang_id`: ID đơn vừa được DBMS trả về.
- `so_luong`: số lượng khách chọn.
- `ma_sp`: mã sản phẩm từ danh mục.
- `sp.gia_hien_tai`: giá đọc từ bảng sản phẩm để ghi vào chi tiết.

Vì `lk_dong_don.don_hang_id` là FOREIGN KEY, nếu dùng một ID đơn không tồn tại, INSERT sẽ bị từ chối theo chính sách kiểm tra FK thông thường.

### 6.1. Một phiên SQL dùng mã yêu cầu thay vì đoán ID

Để chạy ngay trong PostgreSQL mà không nhập thủ công ID đã trả về, ta có thể tìm đơn theo `ma_yeu_cau` duy nhất, sau đó tạo hai dòng:

~~~sql
INSERT INTO lk_dong_don
    (don_hang_id, san_pham_id, so_luong, don_gia)
SELECT
    dh.id,
    sp.id,
    yc.so_luong,
    sp.gia_hien_tai
FROM lk_don_hang AS dh
CROSS JOIN (
    VALUES
        ('SACH_SQL', 2),
        ('SO_TAY',   1)
) AS yc(ma_sp, so_luong)
JOIN lk_san_pham AS sp
    ON sp.ma_sp = yc.ma_sp
WHERE dh.ma_yeu_cau = 'DEMO-RETURNING-01'
RETURNING
    id,
    don_hang_id,
    san_pham_id,
    so_luong,
    don_gia;
~~~

Câu này dùng mã yêu cầu **đã có từ mục 5** để tìm đúng đơn trong DB; nó không phải phương thức thay thế cho việc ứng dụng lấy khóa trực tiếp bằng RETURNING. Trong ứng dụng thật, nên dùng **ID được trả về trong cùng transaction**. Đoạn SQL này chỉ giúp thực hành mà không phụ thuộc ID tự sinh là bao nhiêu.

Đơn có hai dòng với thành tiền:

\[
2\times120000+1\times30000=270000
\]

### 6.2. Thiếu sản phẩm có thể làm INSERT thêm ít hàng hơn dự kiến

Câu `INSERT ... SELECT` bên trên dùng JOIN danh mục sản phẩm. Nếu một `ma_sp` trong danh sách không tồn tại, dòng yêu cầu đó **bị loại bởi JOIN** và INSERT có thể chỉ thêm một dòng, hoặc không thêm dòng nào, **mà không nhất thiết ném lỗi**.

Nếu yêu cầu phải có đúng hai sản phẩm, ứng dụng cần kiểm tra số hàng ảnh hưởng hoặc xác thực đầy đủ trước khi quyết định COMMIT. **INSERT chạy thành công không có nghĩa đã chèn đủ tất cả dòng được yêu cầu.**

### 6.3. Vì sao không đưa cả hai dòng vào VALUES với ID cố định?

Ví dụ không nên sao chép:

~~~sql
-- Chỉ đúng nếu 501 thực sự là ID đã được sinh trong lần chạy của bạn.
INSERT INTO lk_dong_don
    (don_hang_id, san_pham_id, so_luong, don_gia)
VALUES
    (501, 10, 2, 120000);
~~~

Các ID 501 và 10 có thể thuộc bản ghi khác, không tồn tại hoặc đã bị sử dụng ở môi trường khác. Đừng chuyển những ID minh họa trong tài liệu thành giá trị cố định trong mã nghiệp vụ.

## 7. PostgreSQL: tạo cha và con trong một statement

Một khả năng rất hữu ích của PostgreSQL là **data-modifying CTE**: đặt câu INSERT cha trong mệnh đề `WITH`, đưa khóa mới ra bằng `RETURNING`, rồi cho INSERT con đọc khóa ấy.

### 7.1. Ví dụ một đơn với hai dòng

~~~sql
WITH don_moi AS (
    INSERT INTO lk_don_hang
        (khach_hang_id, ma_yeu_cau)
    SELECT
        kh.id,
        'DEMO-CTE-01'
    FROM lk_khach_hang AS kh
    WHERE kh.email = 'an@example.test'
    RETURNING id
)
INSERT INTO lk_dong_don
    (don_hang_id, san_pham_id, so_luong, don_gia)
SELECT
    d.id,
    sp.id,
    yc.so_luong,
    sp.gia_hien_tai
FROM don_moi AS d
CROSS JOIN (
    VALUES
        ('SACH_SQL', 2),
        ('BUT',      3)
) AS yc(ma_sp, so_luong)
JOIN lk_san_pham AS sp
    ON sp.ma_sp = yc.ma_sp
RETURNING
    id AS dong_don_id,
    don_hang_id,
    san_pham_id,
    so_luong,
    don_gia;
~~~

Ý nghĩa:

1. `don_moi` INSERT một đơn, lấy `id` mới bằng `RETURNING id`.
2. Câu INSERT ngoài đọc `d.id` từ kết quả `RETURNING`.
3. Tập `VALUES` mô tả hai sản phẩm và số lượng.
4. JOIN `lk_san_pham` lấy khóa sản phẩm và giá.
5. INSERT ngoài tạo dòng con với `don_hang_id = d.id`, đúng khóa vừa được sinh.
6. `RETURNING` cuối trả các dòng chi tiết vừa tạo, bao gồm khóa đơn liên quan.

Với đơn giá mẫu:

\[
2\times120000+3\times10000=270000
\]

### 7.2. Điểm mạnh: không cần đoán khóa và không cần chuyển ID qua hai lần gọi

Mọi dòng con lấy ID trực tiếp từ `don_moi`. Trong PostgreSQL, các thay đổi của **một statement** được xử lý theo tính nguyên tử: nếu INSERT con vi phạm ràng buộc và statement thất bại, thay đổi cha của **cùng statement** cũng không được xác nhận độc lập.

Tuy nhiên, câu SQL vẫn phải bảo đảm điều kiện nghiệp vụ. **Một statement nguyên tử không tự bảo đảm “đúng hai sản phẩm”** khi JOIN danh mục có thể loại các mã không tồn tại.

### 7.3. Một lưu ý quan trọng về data-modifying CTE

Các phần sửa dữ liệu trong cùng statement PostgreSQL có cơ chế nhìn dữ liệu đặc thù: không nên giả định INSERT ở CTE cha khiến bảng cha có thể được truy vấn như dữ liệu đã tồn tại để các nhánh khác đọc trực tiếp trong cùng statement.

**Kênh truyền dữ liệu đáng tin cậy giữa các bước sửa là kết quả `RETURNING`**:

~~~sql
WITH don_moi AS (
    INSERT INTO lk_don_hang (...)
    VALUES (...)
    RETURNING id
)
INSERT INTO lk_dong_don (...)
SELECT don_moi.id, ...
FROM don_moi;
~~~

Đây chỉ là mẫu cú pháp rút gọn để minh họa. Không thay `FROM don_moi` bằng một truy vấn `SELECT MAX(id) FROM lk_don_hang`; câu đó vừa không đảm bảo nhìn đúng hàng mới, vừa sai mục đích concurrency.

### 7.4. Truy vấn con con có thể thêm 0 dòng

Nếu không tìm được khách An trong bước `INSERT ... SELECT` cha, `don_moi` trả 0 hàng. Khi đó INSERT dòng con cũng 0 hàng. Đây vẫn có thể là statement hợp lệ, vì không có ràng buộc nào bắt buộc phải thêm một đơn.

Ứng dụng cần xác minh **số hàng được trả về và số dòng được kỳ vọng**, không chỉ kiểm tra câu lệnh có báo lỗi hay không.

## 8. Tính nguyên tử và transaction khi thêm nhiều bảng

Nếu một quy trình có **nhiều statement**, hãy đặt chúng trong transaction:

~~~sql
BEGIN;

-- 1. INSERT đơn, lấy ID bằng RETURNING trong ứng dụng.
-- 2. Dùng ID đó INSERT từng dòng đơn.
-- 3. Kiểm tra số dòng, sản phẩm, giá trị và các quy tắc nghiệp vụ.

COMMIT;
~~~

Nếu có lỗi hoặc không đạt điều kiện kinh doanh, thay `COMMIT` bằng `ROLLBACK`.

### 8.1. Atomicity không chỉ là INSERT có chạy được

Ví dụ quy trình mong muốn:

~~~text
BEGIN
  INSERT đơn → nhận ID mới
  INSERT dòng Sách
  INSERT dòng Sổ tay
  Kiểm tra đã có đúng 2 dòng
  COMMIT
~~~

Nếu dòng Sổ tay bị lỗi do mã sản phẩm không tồn tại, hệ thống không nên COMMIT một đơn chỉ có dòng Sách.

Một transaction giúp **hoàn tác cả những INSERT trước đó** nếu ứng dụng quyết định ROLLBACK. Nếu để mỗi statement tự commit riêng, đơn cha có thể đã được lưu vĩnh viễn trước khi dòng con thất bại.

### 8.2. Mẫu SQL thực hành một transaction

~~~sql
BEGIN;

WITH don_moi AS (
    INSERT INTO lk_don_hang
        (khach_hang_id, ma_yeu_cau)
    SELECT
        id,
        'DEMO-TRANS-01'
    FROM lk_khach_hang
    WHERE email = 'binh@example.test'
    RETURNING id
)
INSERT INTO lk_dong_don
    (don_hang_id, san_pham_id, so_luong, don_gia)
SELECT
    d.id,
    p.id,
    yc.so_luong,
    p.gia_hien_tai
FROM don_moi AS d
CROSS JOIN (
    VALUES
        ('SACH_SQL', 1),
        ('SO_TAY',   2)
) AS yc(ma_sp, so_luong)
JOIN lk_san_pham AS p
    ON p.ma_sp = yc.ma_sp
RETURNING don_hang_id, id AS dong_id;

-- Nếu kết quả và nghiệp vụ đều đúng:
COMMIT;
~~~

Ví dụ này đã tạo cha/con trong một statement; `BEGIN ... COMMIT` có ích nếu bạn cần mở rộng transaction thêm các bước như ghi nhật ký, trừ tồn kho hoặc cập nhật trạng thái. Trường hợp các bước này phải cùng nhất quán, chúng nên nằm trong một transaction được thiết kế phù hợp.

### 8.3. PostgreSQL sau lỗi trong transaction

Khi một statement bên trong transaction bị lỗi, PostgreSQL thường đánh dấu transaction là **aborted**, và các statement tiếp theo sẽ báo không thể thực thi trong transaction hiện tại cho đến khi xử lý.

Hãy `ROLLBACK`, hoặc dùng `SAVEPOINT` trước thao tác có thể lỗi nếu muốn khôi phục về một điểm trung gian hợp lệ.

Ví dụ:

~~~sql
BEGIN;

SAVEPOINT truoc_dong_thu_hai;

-- Một INSERT có thể gặp lỗi ở đây.

-- Nếu lỗi và muốn tiếp tục transaction:
ROLLBACK TO SAVEPOINT truoc_dong_thu_hai;

-- Khi hoàn tất phần hợp lệ:
COMMIT;
~~~

Đây là mẫu mô tả giao dịch; không chạy `ROLLBACK TO` như quy trình thường lệ nếu không có lỗi và chính sách nghiệp vụ không cần quay lại savepoint. Với đơn hàng phải có đủ chi tiết, **ROLLBACK toàn bộ** thường đúng hơn việc bỏ qua một dòng bị lỗi.

### 8.4. Khóa identity có thể bị “nhảy số” sau ROLLBACK

Ví dụ một transaction tạo đơn ID 501, sau đó lỗi và ROLLBACK. Lần INSERT hợp lệ tiếp theo có thể nhận ID 502 hoặc giá trị khác, thay vì tái sử dụng 501.

Điều đó bình thường: **sequence không được thiết kế để tạo dãy khóa không có khoảng trống**. Không cố sửa sequence sau mỗi ROLLBACK vì có thể tạo nguy cơ trùng khóa trong môi trường nhiều kết nối.

## 9. Kiểm tra đủ dữ liệu đầu vào trước khi thêm cha

Ví dụ trong phần 7 giả định cả hai mã sản phẩm tồn tại. Nếu một mã sai, JOIN có thể loại một dòng mà câu SQL vẫn tạo đơn. Có thể kiểm tra số dòng đầu vào so với số dòng tìm thấy.

### 9.1. Kiểm tra danh sách sản phẩm

~~~sql
WITH yeu_cau(ma_sp, so_luong) AS (
    VALUES
        ('SACH_SQL', 2),
        ('SO_TAY',   1)
),
hop_le AS (
    SELECT
        yc.ma_sp,
        yc.so_luong,
        p.id AS san_pham_id,
        p.gia_hien_tai
    FROM yeu_cau AS yc
    JOIN lk_san_pham AS p
        ON p.ma_sp = yc.ma_sp
)
SELECT
    (SELECT COUNT(*) FROM yeu_cau) AS so_dong_yeu_cau,
    (SELECT COUNT(*) FROM hop_le) AS so_dong_tim_duoc,
    (SELECT COUNT(DISTINCT ma_sp) FROM yeu_cau)
        AS so_ma_san_pham_khac_nhau;
~~~

Nếu kết quả là 2, 2, 2, ta có hai mã khác nhau và đều tìm thấy sản phẩm. Nếu `so_dong_tim_duoc` nhỏ hơn số dòng yêu cầu, có mã sản phẩm không tồn tại.

Với quy tắc UNIQUE `(don_hang_id, san_pham_id)`, các mã sản phẩm trùng nhau trong cùng đơn cần được gom số lượng hoặc bị từ chối theo nghiệp vụ, tránh chèn hai dòng trùng khóa.

### 9.2. Chỉ tạo đơn khi danh sách đầu vào khớp đầy đủ

Một ví dụ PostgreSQL gộp kiểm tra vào statement:

~~~sql
WITH yeu_cau(ma_sp, so_luong) AS (
    VALUES
        ('SACH_SQL', 2),
        ('SO_TAY',   1)
),
hang_da_tim AS (
    SELECT
        yc.ma_sp,
        yc.so_luong,
        p.id AS san_pham_id,
        p.gia_hien_tai
    FROM yeu_cau AS yc
    JOIN lk_san_pham AS p
        ON p.ma_sp = yc.ma_sp
),
du_dieu_kien AS (
    SELECT
        (SELECT COUNT(*) FROM yeu_cau)
            = (SELECT COUNT(*) FROM hang_da_tim)
        AND
        (SELECT COUNT(DISTINCT ma_sp) FROM yeu_cau)
            = (SELECT COUNT(*) FROM yeu_cau)
        AND
        (SELECT COUNT(*) FROM yeu_cau) > 0 AS hop_le
),
don_moi AS (
    INSERT INTO lk_don_hang
        (khach_hang_id, ma_yeu_cau)
    SELECT
        kh.id,
        'DEMO-GUARDED-01'
    FROM lk_khach_hang AS kh
    CROSS JOIN du_dieu_kien AS dk
    WHERE kh.email = 'an@example.test'
      AND dk.hop_le
    RETURNING id
)
INSERT INTO lk_dong_don
    (don_hang_id, san_pham_id, so_luong, don_gia)
SELECT
    d.id,
    h.san_pham_id,
    h.so_luong,
    h.gia_hien_tai
FROM don_moi AS d
CROSS JOIN hang_da_tim AS h
RETURNING don_hang_id, san_pham_id, so_luong;
~~~

Trong ví dụ này, `don_moi` chỉ INSERT khi tìm đúng khách và kiểm tra danh sách cho kết quả hợp lệ. Nếu thiếu mã sản phẩm hoặc danh sách mã trùng, CTE cha trả 0 hàng nên INSERT con cũng 0 hàng.

**Điểm giới hạn:** SQL trên chỉ minh họa kiểm tra số mã và sự tồn tại sản phẩm. Ứng dụng vẫn cần xác thực số lượng hợp lệ, thỏa thuận giá, quyền của khách, tồn kho, giới hạn đơn và **kiểm tra chính xác số hàng trả về**. Nếu một điều kiện làm statement chèn 0 dòng, không nên coi đó là đơn đã được tạo thành công.

### 9.3. Một số quy tắc không thể giải bằng COUNT đơn giản

Nếu sản phẩm có nhiều biến thể, mã sản phẩm có thể không đủ để định danh dòng đặt hàng. Nếu cho phép cùng sản phẩm nhiều mức giá/khuyến mãi, UNIQUE `(don_hang_id, san_pham_id)` của mẫu không còn phù hợp. Khi đó, thiết kế khóa dòng và kiểm tra đầu vào phải theo đúng nghiệp vụ.

**Đừng dùng SQL tổng quát của bài làm thiết kế thương mại điện tử hoàn chỉnh** khi còn thiếu các ràng buộc quan trọng như tính giá, tồn kho, đặt chỗ, thuế và thanh toán.

## 10. Thêm nhiều bản ghi cha và ánh xạ nhiều khóa mới

Khi INSERT **một hàng**, `RETURNING id` đơn giản. Khi INSERT **nhiều hàng**, câu lệnh có thể trả nhiều ID. Vấn đề là: **ID nào thuộc bản ghi đầu vào nào?**

### 10.1. Trả cả khóa mới và khóa nghiệp vụ

~~~sql
INSERT INTO lk_khach_hang (email, ho_ten)
VALUES
    ('chi@example.test', 'Chi'),
    ('dung@example.test', 'Dũng')
RETURNING id, email, ho_ten;
~~~

Kết quả có hai hàng, mỗi hàng gồm ID mới và email tương ứng.

Thay vì dựa vào thứ tự của các dòng trả về, ứng dụng có thể tạo ánh xạ:

~~~text
email                   -> id vừa sinh
chi@example.test        -> <ID của Chi>
dung@example.test       -> <ID của Dũng>
~~~

Trong batch thật, thứ tự trả về có thể phụ thuộc DBMS, driver, trigger và cách thực thi. **Đừng mặc định phần tử ID thứ nhất luôn tương ứng phần tử request thứ nhất nếu không có bảo đảm rõ ràng của công nghệ đang dùng.**

### 10.2. Cột ánh xạ cần đủ duy nhất

`email` có UNIQUE nên phù hợp để nhận diện bản ghi trong ví dụ. Nếu trả thêm `ho_ten`, hai người cùng tên vẫn có thể không phân biệt được bằng tên. Một khóa nghiệp vụ đáng tin cậy cần có ràng buộc và quy tắc duy nhất rõ ràng.

Đối với batch đơn hàng, có thể dùng một **request token** riêng trên mỗi đơn như `ma_yeu_cau` để ánh xạ:

~~~sql
INSERT INTO lk_don_hang
    (khach_hang_id, ma_yeu_cau)
SELECT
    kh.id,
    src.ma_yeu_cau
FROM lk_khach_hang AS kh
JOIN (
    VALUES
        ('an@example.test', 'BATCH-DON-A'),
        ('binh@example.test', 'BATCH-DON-B')
) AS src(email, ma_yeu_cau)
    ON src.email = kh.email
RETURNING id, ma_yeu_cau, khach_hang_id;
~~~

`RETURNING id, ma_yeu_cau` giúp ghép ID về đúng yêu cầu. Nhưng nếu một email không tìm thấy khách, INSERT thêm ít đơn hơn đầu vào; cần kiểm tra số hàng.

### 10.3. Không giả định ID liên tiếp

Ngay cả khi INSERT hai hàng vào cùng bảng, không nên dựa vào `id_moi + 1` để suy ra hàng thứ hai. Sequence có thể bị tiêu thụ bởi thao tác khác hoặc chịu tác động của cách cấp phát giá trị. Mỗi hàng cần lấy ID thực sự từ `RETURNING` hoặc cơ chế tương ứng của driver.

## 11. Tạo quan hệ nhiều–nhiều

Không phải mọi dữ liệu liên quan đều là một cha và nhiều con. Một sinh viên có thể đăng ký nhiều khóa học; một khóa học có nhiều sinh viên. Đây là quan hệ **nhiều–nhiều** với bảng liên kết.

### 11.1. Tạo bảng ví dụ độc lập

~~~sql
CREATE TEMP TABLE lk_sinh_vien (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_sv TEXT NOT NULL UNIQUE,
    ho_ten TEXT NOT NULL
);

CREATE TEMP TABLE lk_khoa_hoc (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_khoa TEXT NOT NULL UNIQUE,
    ten_khoa TEXT NOT NULL
);

CREATE TEMP TABLE lk_dang_ky (
    sinh_vien_id BIGINT NOT NULL
        REFERENCES lk_sinh_vien(id),
    khoa_hoc_id BIGINT NOT NULL
        REFERENCES lk_khoa_hoc(id),
    ngay_dang_ky DATE NOT NULL DEFAULT CURRENT_DATE,
    PRIMARY KEY (sinh_vien_id, khoa_hoc_id)
);
~~~

Ở đây bảng `lk_dang_ky` có khóa chính tổng hợp, không cần một ID tự sinh riêng vì cặp sinh viên–khóa học đã định danh bản ghi đăng ký.

### 11.2. Thêm hai bảng được tham chiếu

~~~sql
INSERT INTO lk_sinh_vien (ma_sv, ho_ten)
VALUES ('SV001', 'Minh')
RETURNING id, ma_sv;

INSERT INTO lk_khoa_hoc (ma_khoa, ten_khoa)
VALUES
    ('SQL_CO_BAN', 'SQL cơ bản'),
    ('JAVA_CO_BAN', 'Java cơ bản')
RETURNING id, ma_khoa;
~~~

### 11.3. Thêm bảng liên kết bằng khóa được tra cứu đúng

~~~sql
INSERT INTO lk_dang_ky (sinh_vien_id, khoa_hoc_id)
SELECT
    sv.id,
    kh.id
FROM lk_sinh_vien AS sv
CROSS JOIN lk_khoa_hoc AS kh
WHERE sv.ma_sv = 'SV001'
  AND kh.ma_khoa IN ('SQL_CO_BAN', 'JAVA_CO_BAN')
RETURNING sinh_vien_id, khoa_hoc_id, ngay_dang_ky;
~~~

Kết quả có **hai dòng đăng ký** nếu cả sinh viên và hai khóa học tồn tại. `lk_dang_ky` chứa đúng ID thật của hai bảng tham chiếu, thay vì một ID do người viết SQL phỏng đoán.

### 11.4. Khi cần tạo cả hai phía cùng lúc

Nếu thao tác phải tạo sinh viên mới, tạo khóa học mới và tạo đăng ký, có thể dùng một transaction gồm các INSERT tương ứng và lấy từng ID qua RETURNING/driver. Với nhiều mối quan hệ, việc chia statement và transaction rõ ràng thường dễ kiểm soát hơn một câu CTE nhiều INSERT quá phức tạp.

## 12. Java/JDBC: lấy ID bằng RETURNING

Đối với ứng dụng Java dùng PostgreSQL JDBC driver, một lựa chọn rất rõ là dùng `INSERT ... RETURNING id` và đọc bằng `ResultSet`.

Ví dụ phương thức chỉ tạo một đơn:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class OrderRepository {
    private OrderRepository() {}

    public static long insertOrder(
            Connection conn,
            long customerId,
            String requestKey
    ) throws SQLException {

        String sql = """
            INSERT INTO lk_don_hang
                (khach_hang_id, ma_yeu_cau)
            VALUES (?, ?)
            RETURNING id
            """;

        try (PreparedStatement ps =
                     conn.prepareStatement(sql)) {
            ps.setLong(1, customerId);
            ps.setString(2, requestKey);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException(
                        "INSERT đơn hàng không trả về ID"
                    );
                }

                long orderId = rs.getLong("id");

                if (rs.next()) {
                    throw new SQLException(
                        "INSERT đơn hàng trả hơn một ID"
                    );
                }
                return orderId;
            }
        }
    }
}
~~~

### 12.1. Vì sao dùng PreparedStatement?

Dấu `?` là tham số JDBC:

- `ps.setLong(1, customerId)` truyền khóa khách hàng.
- `ps.setString(2, requestKey)` truyền mã yêu cầu.

Không ghép giá trị đầu vào thành SQL bằng cộng chuỗi, vì dễ phát sinh lỗi quoting, SQL injection và sai kiểu dữ liệu.

### 12.2. Vì sao executeQuery hoạt động ở ví dụ PostgreSQL?

Statement `INSERT ... RETURNING id` trả một tập hàng chứa ID, nên với PostgreSQL JDBC có thể đọc bằng `executeQuery()`. Đối với các JDBC driver/DBMS khác, hỗ trợ cú pháp RETURNING và lựa chọn API có thể khác; không nên sao chép nguyên phương thức này rồi kỳ vọng chạy trên mọi DBMS.

### 12.3. Không tự động COMMIT trong repository đơn lẻ

Hàm trên không tự gọi `conn.commit()`. Điều này cho phép tầng dịch vụ quyết định transaction bao gồm **cả đơn và các dòng đơn**, thay vì commit đơn cha quá sớm.

Nếu `conn` đang có `autoCommit = true`, mỗi statement thành công có thể được commit tự động theo JDBC. Với thao tác nhiều bảng, tầng điều phối phải chủ động tắt auto-commit trong thời gian transaction.

## 13. Java/JDBC: tạo đơn và hai dòng trong một transaction

Ví dụ đầy đủ hơn: dùng cùng `Connection`, lấy ID vừa sinh, sau đó thêm hai dòng sản phẩm theo mã. Nếu không tìm thấy sản phẩm hoặc ràng buộc lỗi, transaction sẽ ROLLBACK.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class OrderService {

    private OrderService() {}

    public static long createOrder(
            Connection conn,
            long customerId,
            String requestKey
    ) throws SQLException {

        boolean oldAutoCommit = conn.getAutoCommit();
        conn.setAutoCommit(false);

        try {
            long orderId = insertOrder(
                conn, customerId, requestKey
            );

            insertLine(conn, orderId, "SACH_SQL", 2);
            insertLine(conn, orderId, "SO_TAY", 1);

            conn.commit();
            return orderId;

        } catch (SQLException | RuntimeException ex) {
            try {
                conn.rollback();
            } catch (SQLException rollbackError) {
                ex.addSuppressed(rollbackError);
            }
            throw ex;

        } finally {
            conn.setAutoCommit(oldAutoCommit);
        }
    }

    private static long insertOrder(
            Connection conn,
            long customerId,
            String requestKey
    ) throws SQLException {

        String sql = """
            INSERT INTO lk_don_hang
                (khach_hang_id, ma_yeu_cau)
            VALUES (?, ?)
            RETURNING id
            """;

        try (PreparedStatement ps =
                     conn.prepareStatement(sql)) {
            ps.setLong(1, customerId);
            ps.setString(2, requestKey);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException(
                        "Không lấy được ID đơn hàng"
                    );
                }
                return rs.getLong(1);
            }
        }
    }

    private static void insertLine(
            Connection conn,
            long orderId,
            String productCode,
            int quantity
    ) throws SQLException {

        String sql = """
            INSERT INTO lk_dong_don
                (don_hang_id, san_pham_id, so_luong, don_gia)
            SELECT
                ?,
                sp.id,
                ?,
                sp.gia_hien_tai
            FROM lk_san_pham AS sp
            WHERE sp.ma_sp = ?
            """;

        try (PreparedStatement ps =
                     conn.prepareStatement(sql)) {
            ps.setLong(1, orderId);
            ps.setInt(2, quantity);
            ps.setString(3, productCode);

            int insertedRows = ps.executeUpdate();

            if (insertedRows != 1) {
                throw new SQLException(
                    "Sản phẩm không tồn tại hoặc INSERT " +
                    "không tạo đúng một dòng: " + productCode
                );
            }
        }
    }
}
~~~

### 13.1. Những yếu tố bảo vệ trong ví dụ

- Dùng **cùng Connection** cho mọi statement: transaction và khóa tham chiếu có cùng ngữ cảnh.
- `conn.setAutoCommit(false)`: không tự commit đơn cha trước các dòng con.
- ID đơn lấy từ `RETURNING` của chính INSERT tạo đơn.
- Dùng `PreparedStatement` để truyền tham số có kiểu.
- Kiểm tra `executeUpdate() == 1` cho mỗi dòng: nếu mã sản phẩm không tồn tại và INSERT ... SELECT thêm 0 hàng, nghiệp vụ vẫn nhận ra thất bại.
- Nếu có lỗi, gọi `rollback()` rồi ném lại lỗi.
- Chỉ `commit()` sau khi cả hai dòng đều được thêm.
- Phục hồi cấu hình auto-commit ban đầu ở `finally`.

### 13.2. Ví dụ áp dụng khi sử dụng connection do service kiểm soát

Hàm `createOrder` ở trên **giả định nó sở hữu ranh giới transaction của Connection** được truyền vào. Nếu Connection đã nằm trong transaction lớn hơn do framework quản lý, tự ý `commit`/`rollback` hoặc đổi auto-commit có thể phá quy tắc của framework.

Trong Spring hay một transaction manager khác, thường để **service transaction** điều phối và repository chỉ thực thi statement. Khi đó, dùng cơ chế quản lý transaction được framework hỗ trợ thay vì sao chép nguyên cách tự bật/tắt auto-commit ở mọi tầng.

### 13.3. Khôi phục auto-commit cũng có thể gặp lỗi

`conn.setAutoCommit(oldAutoCommit)` có thể ném `SQLException`, đặc biệt khi kết nối hỏng. Mẫu dùng `finally` bảo đảm có nỗ lực khôi phục trạng thái; trong hệ thống thật cần chính sách quản lý connection pool và lỗi kết nối phù hợp.

### 13.4. Giá sản phẩm có thể thay đổi trong lúc tạo đơn

Ví dụ đọc `gia_hien_tai` tại thời điểm INSERT dòng. Nếu quy trình phải đảm bảo giá ổn định cho toàn bộ đơn, ứng dụng có thể cần:

- Một phiên bản báo giá/đơn giá được xác nhận.
- Cơ chế khóa hoặc mức cô lập phù hợp.
- Quy tắc hiệu lực giá theo thời gian.
- Chuyển giá đã được chấp nhận từ tầng đặt hàng vào dòng đơn.

Transaction một mình không tự bảo đảm tất cả quy tắc định giá thương mại. Đây là phần thiết kế nghiệp vụ mở rộng, không phải thuộc tính của `RETURNING`.

## 14. JDBC getGeneratedKeys: lựa chọn qua API driver

JDBC còn có API chuẩn để yêu cầu các khóa tự sinh:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public static long insertOrderWithGeneratedKeys(
        Connection conn,
        long customerId
) throws SQLException {

    String sql = """
        INSERT INTO lk_don_hang (khach_hang_id)
        VALUES (?)
        """;

    try (PreparedStatement ps = conn.prepareStatement(
            sql,
            Statement.RETURN_GENERATED_KEYS
    )) {
        ps.setLong(1, customerId);

        int affected = ps.executeUpdate();
        if (affected != 1) {
            throw new SQLException(
                "Không tạo đúng một đơn hàng"
            );
        }

        try (ResultSet keys = ps.getGeneratedKeys()) {
            if (!keys.next()) {
                throw new SQLException(
                    "Driver không trả khóa vừa sinh"
                );
            }
            return keys.getLong(1);
        }
    }
}
~~~

### 14.1. Khác RETURNING ở điểm nào?

| Cách | Ví dụ | Phạm vi |
|---|---|---|
| PostgreSQL `RETURNING` | `INSERT ... RETURNING id` | SQL PostgreSQL trả tập hàng gồm những cột chỉ định |
| JDBC `getGeneratedKeys` | `Statement.RETURN_GENERATED_KEYS` | API của JDBC, phụ thuộc driver hỗ trợ và DBMS |
| Driver chỉ định tên cột | `prepareStatement(sql, new String[]{"id"})` | Có thể giúp yêu cầu cụ thể cột khóa khi driver hỗ trợ |

Với PostgreSQL JDBC, một số driver có thể trả nhiều cột hơn mong muốn nếu chỉ yêu cầu khóa theo cách chung; nên xem hành vi driver hoặc chỉ định tên cột khóa khi cần.

### 14.2. Dùng kiểu khóa phù hợp

Cột `id` là `BIGINT` trong SQL, nên Java `long` và `ResultSet.getLong` phù hợp trong ví dụ. Với khóa UUID, ứng dụng phải đọc theo kiểu hỗ trợ tương ứng, không mặc định mọi khóa sinh đều là số nguyên.

### 14.3. Batch INSERT cần ánh xạ chính xác

Nếu dùng JDBC batch tạo nhiều cha, `getGeneratedKeys` có thể có hành vi khác nhau theo driver/DBMS về số khóa trả, thứ tự và cách xử lý nhiều statement. Không nên mặc định `keys.getLong(1)` theo thứ tự batch là an toàn cho mọi hệ thống.

Khi cần ánh xạ chính xác, hãy cân nhắc:

- Trả **ID và khóa nghiệp vụ duy nhất** bằng RETURNING ở DBMS hỗ trợ.
- Thực hiện từng INSERT và giữ kết quả theo từng request trong một transaction khi quy mô chấp nhận.
- Dùng cơ chế batch và mapping **được driver tài liệu hóa** cho phiên bản đang chạy.

## 15. Không lấy khóa bằng MAX(id), ORDER BY id DESC hoặc LASTVAL tùy tiện

### 15.1. MAX(id) không thuộc về transaction của bạn

Hai kết nối A và B cùng làm:

~~~text
A: INSERT đơn A -> được ID 100
B: INSERT đơn B -> được ID 101
A: SELECT MAX(id) -> có thể thấy 101 nếu B đã commit
A: INSERT dòng đơn với 101 -> gắn nhầm đơn của B
~~~

Đây là một lỗi nghiêm trọng: dòng chi tiết thuộc nhầm đơn dù ràng buộc FK **vẫn có thể hợp lệ**, vì đơn 101 có tồn tại.

Tương tự, câu:

~~~sql
SELECT id
FROM lk_don_hang
ORDER BY id DESC
LIMIT 1;
~~~

cũng chỉ tìm ID lớn nhất hiện nhìn thấy, không chứng minh nó thuộc INSERT của kết nối đang thao tác.

### 15.2. Sequence PostgreSQL có currval, nhưng RETURNING rõ hơn

PostgreSQL có `currval(sequence)`, trả giá trị sequence được cấp gần đây trong **phiên kết nối hiện tại** cho sequence cụ thể, sau khi phiên đó đã gọi `nextval` tương ứng.

Một ví dụ nếu bạn hiểu tên sequence được gắn với identity:

~~~sql
SELECT currval(
    pg_get_serial_sequence('lk_don_hang', 'id')
);
~~~

Đoạn này chỉ có ý nghĩa **sau khi phiên hiện tại đã tạo giá trị sequence của lk_don_hang**, và tên bảng phải phân giải đúng đối tượng trong search path. Nếu chưa có giá trị sequence trong session, `currval` gây lỗi.

`currval` theo sequence có các đặc tính an toàn hơn `MAX(id)` về cạnh tranh giữa kết nối, nhưng nó vẫn làm ứng dụng phụ thuộc đến việc biết sequence nào vừa dùng. Với INSERT hàng loạt, trigger hoặc nhiều sequence liên quan, `RETURNING id` thường trực tiếp và dễ đọc hơn.

### 15.3. LASTVAL không phải lựa chọn mặc định

PostgreSQL còn có `lastval()` cho sequence được gọi gần đây nhất trong phiên, nhưng nếu nhiều sequence được dùng (chẳng hạn do trigger), kết quả có thể không phải sequence của đơn hàng bạn cần.

**Quy tắc thực hành:** khi DBMS hỗ trợ, ưu tiên lấy khóa từ **chính statement INSERT** bằng RETURNING/OUTPUT hoặc API generated keys phù hợp, không hỏi “khóa lớn nhất của bảng hiện nay là gì?”.

## 16. Lỗi ràng buộc thường gặp

Thiết kế khóa ngoại và ràng buộc giúp database ngăn dữ liệu bị nối sai, nhưng ứng dụng vẫn cần xử lý thông báo lỗi và rollback.

### 16.1. FK: dòng con trỏ tới đơn không tồn tại

~~~sql
-- Ví dụ gây lỗi nếu không có đơn id = -999:
INSERT INTO lk_dong_don
    (don_hang_id, san_pham_id, so_luong, don_gia)
SELECT
    -999,
    p.id,
    1,
    p.gia_hien_tai
FROM lk_san_pham AS p
WHERE p.ma_sp = 'SACH_SQL';
~~~

Nếu sản phẩm tồn tại và SELECT tạo hàng, FK `don_hang_id` sẽ từ chối vì đơn -999 không có trong bảng cha.

Đây không phải lỗi “khóa sinh bị thất lạc” của DBMS; đây là lỗi dùng **khóa tham chiếu sai**.

### 16.2. FK: sản phẩm không tồn tại

Nếu chèn trực tiếp một `san_pham_id` không có thật, FK cũng sẽ từ chối. Nhưng nếu câu lệnh dùng `INSERT ... SELECT ... WHERE ma_sp = 'KHONG_CO'`, SELECT trả 0 hàng nên **không có hàng mới để kiểm tra FK**. Hai tình huống khác nhau:

- **Tham chiếu bằng ID không tồn tại trong hàng được chèn** → lỗi FK.
- **Nguồn SELECT không tạo hàng** → thường 0 hàng được thêm, có thể không lỗi.

Phải kiểm tra số hàng được chèn nếu nghiệp vụ yêu cầu đủ dòng.

### 16.3. CHECK: số lượng không hợp lệ

~~~sql
-- Minh họa lỗi CHECK do so_luong phải > 0.
INSERT INTO lk_dong_don
    (don_hang_id, san_pham_id, so_luong, don_gia)
SELECT
    dh.id,
    p.id,
    0,
    p.gia_hien_tai
FROM lk_don_hang AS dh
CROSS JOIN lk_san_pham AS p
WHERE dh.ma_yeu_cau = 'DEMO-RETURNING-01'
  AND p.ma_sp = 'BUT';
~~~

Nếu các bản ghi tham chiếu tồn tại, lệnh cố chèn `so_luong = 0` sẽ vi phạm CHECK. Việc này nên được thử riêng ở môi trường học; nếu đang ở một transaction PostgreSQL và xảy ra lỗi, cần rollback trước khi tiếp tục.

### 16.4. UNIQUE: trùng một sản phẩm trong đơn

Nếu đơn đã có một dòng cho `SACH_SQL`, INSERT một dòng khác cùng `don_hang_id` và `san_pham_id` bị ràng buộc UNIQUE từ chối.

Điều này bảo vệ quy tắc “mỗi sản phẩm tối đa một dòng/đơn” của ví dụ, nhưng không thay ứng dụng quyết định liệu khi người dùng chọn sản phẩm hai lần thì nên **gộp số lượng**, **báo lỗi**, hay **cho hai dòng với khóa khác**.

### 16.5. Các mã SQLSTATE thường gặp trong PostgreSQL

| SQLSTATE | Ý nghĩa thường gặp |
|---|---|
| `23503` | Vi phạm foreign key |
| `23505` | Vi phạm unique constraint |
| `23502` | Vi phạm not-null constraint |
| `23514` | Vi phạm check constraint |
| `25P02` | Transaction hiện tại đã bị đánh dấu lỗi; cần rollback trước khi tiếp tục |

Ứng dụng nên ánh xạ mã lỗi sang thông báo nghiệp vụ phù hợp, đồng thời giữ thông tin gốc cho chẩn đoán kỹ thuật. Không dựa vào nguyên văn thông báo lỗi theo ngôn ngữ server để quyết định luồng chương trình.

## 17. Retry, idempotency và mã yêu cầu duy nhất

Trong hệ thống thật, người dùng có thể nhấn “Đặt hàng” hai lần; mạng có thể bị ngắt sau khi database đã COMMIT nhưng trước khi client nhận phản hồi. Ứng dụng thử lại thao tác có thể vô tình tạo **hai đơn khác nhau**.

**Idempotency** ở đây nghĩa là cùng một yêu cầu tạo đơn được gửi lại không nên tạo trùng một nghiệp vụ.

### 17.1. Khóa yêu cầu duy nhất

Cột `ma_yeu_cau TEXT UNIQUE` trong `lk_don_hang` dùng để mô tả một mã riêng cho **mỗi yêu cầu nghiệp vụ**. Ví dụ:

~~~sql
INSERT INTO lk_don_hang
    (khach_hang_id, ma_yeu_cau)
SELECT
    kh.id,
    'REQ-2026-001'
FROM lk_khach_hang AS kh
WHERE kh.email = 'an@example.test'
RETURNING id, ma_yeu_cau;
~~~

Nếu gửi lại cùng `ma_yeu_cau`, UNIQUE sẽ chặn một đơn thứ hai có cùng mã.

### 17.2. PostgreSQL ON CONFLICT DO NOTHING

~~~sql
INSERT INTO lk_don_hang
    (khach_hang_id, ma_yeu_cau)
SELECT
    kh.id,
    'REQ-2026-001'
FROM lk_khach_hang AS kh
WHERE kh.email = 'an@example.test'
ON CONFLICT (ma_yeu_cau) DO NOTHING
RETURNING id, ma_yeu_cau;
~~~

Nếu đơn được chèn mới, RETURNING có một hàng. Nếu đã tồn tại mã yêu cầu, `DO NOTHING` bỏ qua thao tác chèn và **RETURNING không trả ID của hàng đã tồn tại**.

Đây là điểm rất dễ nhầm: `ON CONFLICT DO NOTHING RETURNING id` **không tự “lấy lại ID cũ”**.

### 17.3. Nếu cần tìm lại ID đã có

Sau khi xác định xung đột và theo quy trình transaction phù hợp:

~~~sql
SELECT
    id,
    khach_hang_id,
    trang_thai
FROM lk_don_hang
WHERE ma_yeu_cau = 'REQ-2026-001';
~~~

Không chỉ lấy ID rồi tiếp tục thêm dòng mới một cách mù quáng. Phải kiểm tra **mã yêu cầu thuộc đúng khách**, nội dung đơn có khớp payload cũ không, và thao tác trước đã hoàn thành hay còn thiếu bước nào.

### 17.4. Upsert RETURNING có thể trả ID nhưng có tác dụng UPDATE

PostgreSQL cho phép:

~~~sql
INSERT INTO lk_don_hang
    (khach_hang_id, ma_yeu_cau)
SELECT kh.id, 'REQ-2026-002'
FROM lk_khach_hang AS kh
WHERE kh.email = 'an@example.test'
ON CONFLICT (ma_yeu_cau)
DO UPDATE SET
    ma_yeu_cau = EXCLUDED.ma_yeu_cau
RETURNING id;
~~~

Cách này có thể trả ID của hàng được INSERT hoặc UPDATE. Nhưng `DO UPDATE` thực sự là một nhánh UPDATE, có thể kích hoạt trigger, quyền, WAL, khóa hoặc logic cập nhật khác, dù gán cùng giá trị.

**Không nên dùng nhánh cập nhật “giả” chỉ để lấy khóa một cách mặc định**. Hãy lựa chọn theo thiết kế idempotency và hiệu ứng phụ của bảng.

### 17.5. UNIQUE ở header chưa đủ để bảo đảm toàn bộ workflow idempotent

Nếu header đã tồn tại nhưng các dòng đơn bị thêm lại, bạn có thể gặp UNIQUE hoặc gấp đôi số lượng nếu mô hình cho phép nhiều dòng.

Một quy trình retry đúng cần **bao quát cả đơn và chi tiết**:

- Gắn mỗi yêu cầu với một mã duy nhất.
- Tạo header và dòng trong một transaction.
- Khi retry, xác định giao dịch trước đã thành công hay chưa.
- Không thêm lại chi tiết vào một đơn hoàn tất nếu không có logic xử lý rõ ràng.
- So khớp dữ liệu request cũ và mới khi cùng mã yêu cầu.

Điều này là trách nhiệm của thiết kế nghiệp vụ; một câu `ON CONFLICT` đơn lẻ không thay thế toàn bộ quy trình.

## 18. Nhiều kết nối, cạnh tranh và kiểm soát quyền

### 18.1. Không dùng lại ID giữa các Connection một cách tùy tiện

Kết nối A INSERT đơn và lấy ID. Nếu muốn chèn chi tiết trong cùng transaction, phải dùng **cùng Connection A**. Nếu chuyển sang Connection B:

- B không thuộc transaction chưa COMMIT của A.
- B có thể **chưa nhìn thấy** đơn vừa được tạo.
- FK khi INSERT con có thể chờ hoặc thất bại theo tình trạng giao dịch và cơ chế khóa.
- A và B không có cùng ngữ cảnh rollback.

Các connection pool không tự bảo đảm hai repository call dùng cùng Connection nếu không có transaction manager hay cơ chế truyền connection phù hợp.

### 18.2. Không nhầm ID được sinh với quyền truy cập

Biết hoặc đoán được một `don_hang_id` không có nghĩa người dùng được phép thêm dòng vào đơn đó. FK chỉ xác thực đơn tồn tại, không xác thực **ai được thao tác đơn**.

Ứng dụng cần kiểm tra:

- Đơn thuộc đúng khách/tài khoản được phép.
- Trạng thái đơn cho phép thêm hoặc sửa dòng.
- Quyền của người gọi đối với sản phẩm, giá và đơn.
- Dữ liệu truyền qua API được kiểm tra và ràng buộc.

**Không dùng tính “khó đoán” của ID làm cơ chế phân quyền.**

### 18.3. Không dùng SELECT MAX(id) + 1 để sinh khóa

~~~sql
-- Sai trong môi trường đồng thời:
SELECT COALESCE(MAX(id), 0) + 1
FROM lk_don_hang;
~~~

Hai giao dịch có thể cùng tính ra một giá trị trước khi bất kỳ bên nào chèn, gây lỗi hoặc tranh chấp. Identity/sequence, UUID và các cơ chế phát sinh khóa được thiết kế cho mục đích này phù hợp hơn.

### 18.4. Khóa và mức cô lập không thay được UNIQUE

Nếu ứng dụng có mã đơn nghiệp vụ duy nhất, hãy khai báo `UNIQUE` ở database. Kiểm tra trước bằng:

~~~sql
SELECT 1
FROM lk_don_hang
WHERE ma_yeu_cau = 'REQ-2026-003';
~~~

rồi quyết định INSERT có thể bị **race condition** giữa hai request. Ràng buộc UNIQUE là tuyến phòng thủ đúng khi hai bên cùng chèn. Với PostgreSQL, `ON CONFLICT` giúp xử lý xung đột theo chính sách được xác định.

## 19. RETURNING nhiều dòng và dữ liệu con sinh từ VALUES

Một mẫu tiện dụng khác là tạo cha bằng CTE rồi thêm nhiều dòng con từ danh sách đầu vào.

~~~sql
WITH yeu_cau(ma_sp, so_luong) AS (
    VALUES
        ('SACH_SQL', 1),
        ('SO_TAY',   2),
        ('BUT',      5)
),
don_moi AS (
    INSERT INTO lk_don_hang
        (khach_hang_id, ma_yeu_cau)
    SELECT
        kh.id,
        'DEMO-BA-DONG-01'
    FROM lk_khach_hang AS kh
    WHERE kh.email = 'binh@example.test'
    RETURNING id
)
INSERT INTO lk_dong_don
    (don_hang_id, san_pham_id, so_luong, don_gia)
SELECT
    d.id,
    sp.id,
    yc.so_luong,
    sp.gia_hien_tai
FROM don_moi AS d
CROSS JOIN yeu_cau AS yc
JOIN lk_san_pham AS sp
    ON sp.ma_sp = yc.ma_sp
RETURNING
    id AS dong_id,
    don_hang_id,
    san_pham_id,
    so_luong,
    don_gia;
~~~

Nếu cả ba mã sản phẩm tồn tại và không có lỗi ràng buộc, truy vấn chèn một đơn và ba dòng. Dòng con nhận:

| Mã sản phẩm | Số lượng | Đơn giá | Thành tiền |
|---|---:|---:|---:|
| SACH_SQL | 1 | 120000 | 120000 |
| SO_TAY | 2 | 30000 | 60000 |
| BUT | 5 | 10000 | 50000 |

Tổng đơn là:

\[
120000+60000+50000=230000
\]

`RETURNING` cuối trả khóa của **ba dòng con** và khóa đơn cha mà chúng cùng tham chiếu. Không được dựa vào thứ tự hàng RETURNING để ánh xạ về từng mã sản phẩm nếu API yêu cầu mapping chính xác. Có thể sử dụng các khóa trả về cùng `san_pham_id` để tra cứu mã, hoặc thiết kế dữ liệu đầu vào/đầu ra có định danh ổn định.

### 19.1. Cẩn thận khi một sản phẩm xuất hiện hai lần

Nếu `VALUES` có cùng `ma_sp` ở hai dòng, UNIQUE `(don_hang_id, san_pham_id)` sẽ không cho phép cả hai dòng cùng tồn tại trong đơn mẫu. Hãy chọn một trong các cách:

- Gom số lượng theo mã sản phẩm trước INSERT.
- Từ chối payload trùng mã.
- Thay đổi mô hình nếu nghiệp vụ thật cho phép nhiều dòng cùng sản phẩm.

Không dùng `DISTINCT` chỉ để che hai dòng khác số lượng hoặc giá, vì nó có thể loại/giữ dữ liệu không theo ý nghĩa nghiệp vụ.

## 20. Tra cứu lại đơn và chi tiết sau khi INSERT

Sau khi đã thêm dữ liệu, cần kiểm tra nó gắn đúng các khóa quan hệ bằng JOIN:

~~~sql
SELECT
    dh.id AS don_hang_id,
    dh.ma_yeu_cau,
    kh.ho_ten AS khach_hang,
    dd.id AS dong_don_id,
    sp.ma_sp,
    sp.ten AS san_pham,
    dd.so_luong,
    dd.don_gia,
    dd.so_luong * dd.don_gia AS thanh_tien
FROM lk_don_hang AS dh
JOIN lk_khach_hang AS kh
    ON kh.id = dh.khach_hang_id
LEFT JOIN lk_dong_don AS dd
    ON dd.don_hang_id = dh.id
LEFT JOIN lk_san_pham AS sp
    ON sp.id = dd.san_pham_id
WHERE dh.ma_yeu_cau = 'DEMO-CTE-01'
ORDER BY dd.id;
~~~

Với đơn ở phần 7, kết quả có hai dòng chi tiết. `LEFT JOIN` giữ được đơn cha ngay cả khi một thao tác nào đó đã tạo đơn nhưng chưa có chi tiết. Khi đó các cột dòng con có thể là NULL.

### 20.1. Đếm dòng và tổng tiền đúng cấp

~~~sql
SELECT
    dh.id,
    dh.ma_yeu_cau,
    COUNT(dd.id) AS so_dong,
    COALESCE(
        SUM(dd.so_luong * dd.don_gia),
        0
    ) AS tong_tien
FROM lk_don_hang AS dh
LEFT JOIN lk_dong_don AS dd
    ON dd.don_hang_id = dh.id
WHERE dh.ma_yeu_cau = 'DEMO-CTE-01'
GROUP BY dh.id, dh.ma_yeu_cau;
~~~

Nếu hai sản phẩm được chèn đúng, kết quả có **so_dong = 2** và **tong_tien = 270000**.

Vì dùng `LEFT JOIN`, nếu đơn không có dòng con, `COUNT(dd.id)` sẽ bằng 0; `COUNT(*)` lại có thể bằng 1 do hàng đệm của phía cha.

### 20.2. Không lấy ID mới thông qua truy vấn tổng hợp sau khi hoàn tất

Truy vấn JOIN/COUNT là công cụ **đọc và kiểm tra quan hệ**. Nó không thay thế việc lấy ID cha ngay ở bước tạo đơn. Ứng dụng nên truyền và lưu ID từ RETURNING/driver trong suốt quy trình ghi, thay vì thực hiện một truy vấn rộng để “đoán xem đơn nào vừa được tạo”.

## 21. Chọn giữa một statement và nhiều statement trong transaction

Không phải mọi workflow cần phải gói vào một CTE khổng lồ.

| Tình huống | Cách thường phù hợp | Lưu ý |
|---|---|---|
| Chỉ tạo một cha và cần ID | `INSERT ... RETURNING id` | Đọc đúng một ID |
| Tạo cha và vài con đơn giản trên PostgreSQL | INSERT cha trong CTE + INSERT con từ `RETURNING` | Một statement, nhưng cần kiểm tra số lượng con |
| Tạo cha, nhiều con, cập nhật tồn kho, ghi audit | Nhiều statement trong một transaction | Dễ phân nhánh và kiểm soát lỗi |
| Ứng dụng Java cần SQL tương đối di động | JDBC `getGeneratedKeys` | Kiểm tra driver và ánh xạ khóa |
| Batch nhiều cha | RETURNING ID + khóa nghiệp vụ | Không suy ra ánh xạ theo thứ tự |
| Nhiều bảng có quan hệ nhiều–nhiều | Tạo/tra cứu các đầu liên kết rồi chèn bridge table | Ràng buộc khóa tổng hợp hoặc khóa dòng phù hợp |
| Request có thể retry | Mã yêu cầu UNIQUE + transaction + kiểm tra payload | Không thêm lại chi tiết tùy tiện |

**Nguyên tắc chọn:** số statement không phải tiêu chí duy nhất. Cần bảo toàn đúng nghiệp vụ, xử lý đầy đủ đầu vào, giữ nguyên tử giữa các bước và có cách lấy/ánh xạ khóa chính xác.

## 22. Khác biệt giữa các hệ quản trị

Không phải mọi DBMS dùng cùng một cú pháp `RETURNING`. Tuy nhiên, mục tiêu giống nhau: **lấy khóa liên quan đến INSERT mà chính ứng dụng vừa chạy**.

| DBMS | Cơ chế lấy khóa thường dùng | Lưu ý |
|---|---|---|
| **PostgreSQL** | `INSERT ... RETURNING id`, JDBC generated keys | Hỗ trợ data-modifying CTE; IDENTITY và sequence |
| **MySQL** | `LAST_INSERT_ID()` trên cùng connection, JDBC generated keys | MySQL không hỗ trợ PostgreSQL-style `INSERT ... RETURNING` thông thường; phải kiểm tra phiên bản và driver |
| **MariaDB** | `LAST_INSERT_ID()`; `INSERT ... RETURNING` từ các phiên bản hỗ trợ | Mức hỗ trợ cú pháp khác MySQL |
| **SQL Server** | `OUTPUT INSERTED.Id`, `SCOPE_IDENTITY()`, JDBC generated keys | `OUTPUT` có quy tắc riêng khi bảng có trigger; không dùng `@@IDENTITY` tùy tiện |
| **Oracle** | `RETURNING ... INTO` trong PL/SQL/client phù hợp, sequence hoặc identity | Cơ chế bind biến đầu ra khác PostgreSQL |
| **SQLite** | `RETURNING` trên các phiên bản hỗ trợ, `last_insert_rowid()` cùng connection | ROWID và AUTOINCREMENT có quy tắc riêng; thao tác theo connection |

### 22.1. MySQL: LAST_INSERT_ID theo kết nối

Ví dụ minh họa (giả sử bảng MySQL có cột `id BIGINT AUTO_INCREMENT PRIMARY KEY`):

~~~sql
INSERT INTO don_hang (khach_hang_id)
VALUES (123);

SELECT LAST_INSERT_ID() AS don_hang_id;
~~~

`LAST_INSERT_ID()` gắn với session/connection MySQL hiện tại, nên tránh được lỗi lấy ID lớn nhất của kết nối khác như `MAX(id)`. Nhưng phải sử dụng **cùng connection** và hiểu hành vi khi INSERT nhiều hàng hoặc thao tác khác can thiệp. Không chuyển lệnh trên sang PostgreSQL như một cú pháp tương đương.

### 22.2. MariaDB: INSERT RETURNING khi phiên bản hỗ trợ

Trong các phiên bản MariaDB hỗ trợ `INSERT ... RETURNING`, có thể dùng mẫu:

~~~sql
INSERT INTO don_hang (khach_hang_id)
VALUES (123)
RETURNING id;
~~~

Khả năng cụ thể và giới hạn theo phiên bản cần xác nhận. MySQL và MariaDB đã tách biệt về tập tính năng; không mặc định hỗ trợ của MariaDB có sẵn trên MySQL.

### 22.3. SQL Server: OUTPUT INSERTED

Mẫu T-SQL:

~~~sql
INSERT INTO dbo.DonHang (KhachHangId)
OUTPUT INSERTED.Id
VALUES (123);
~~~

`OUTPUT INSERTED.Id` trả ID của hàng vừa chèn. Với bảng có trigger được bật, SQL Server có quy tắc về việc `OUTPUT` trực tiếp không dùng `INTO`; có trường hợp cần `OUTPUT ... INTO` một bảng nhận trung gian. Hãy kiểm tra thiết kế bảng và tài liệu phiên bản.

Một cách khác:

~~~sql
INSERT INTO dbo.DonHang (KhachHangId)
VALUES (123);

SELECT SCOPE_IDENTITY() AS DonHangId;
~~~

`SCOPE_IDENTITY()` trả identity được sinh trong phạm vi thực thi phù hợp; không nên mặc định `@@IDENTITY` an toàn vì có thể chịu ảnh hưởng từ trigger ở scope khác. Với nhiều hàng và nhiều bảng liên quan, `OUTPUT` thường thể hiện ánh xạ chi tiết hơn.

### 22.4. Oracle: RETURNING INTO

Trong PL/SQL, ví dụ minh họa:

~~~sql
DECLARE
    v_id NUMBER;
BEGIN
    INSERT INTO don_hang (khach_hang_id)
    VALUES (123)
    RETURNING id INTO v_id;

    DBMS_OUTPUT.PUT_LINE('ID=' || v_id);
END;
/
~~~

`RETURNING ... INTO` đặt ID vào biến `v_id` trong PL/SQL. Cách truyền biến đầu ra trong JDBC/driver Oracle là câu chuyện riêng; không thể sao chép `RETURNING id` của PostgreSQL rồi kỳ vọng Oracle xử lý hệt như một SELECT trả bảng.

### 22.5. SQLite: RETURNING và last_insert_rowid

Trong SQLite mới hỗ trợ RETURNING (từ 3.35.0), có thể dùng:

~~~sql
INSERT INTO don_hang (khach_hang_id)
VALUES (123)
RETURNING id;
~~~

Với bảng có khóa số nguyên phù hợp, `last_insert_rowid()` trả ROWID chèn thành công gần đây trên **cùng kết nối**; cách dùng cần lưu ý trigger, virtual table và các trường hợp đặc biệt.

Trong SQLite, `INTEGER PRIMARY KEY` trên bảng rowid thông thường liên quan chặt với ROWID. Từ khóa `AUTOINCREMENT` không bắt buộc để có khóa tự cấp và có chi phí/quy tắc riêng; không nên thêm chỉ vì nghĩ mọi ID phải có từ khóa này.

### 22.6. Kết luận khi chuyển DBMS

Chọn cơ chế theo:

1. DBMS và phiên bản.
2. Driver/thư viện truy cập dữ liệu.
3. INSERT một hàng hay nhiều hàng.
4. Yêu cầu ánh xạ ID mới với dữ liệu đầu vào.
5. Transaction, trigger và quy tắc xử lý xung đột.

**Điều không thay đổi:** không lấy khóa cho bản ghi vừa chèn bằng `MAX(id)` rồi coi đó là khóa của mình.

## 23. Lỗi và hiểu nhầm thường gặp

| Lỗi hoặc hiểu nhầm | Hậu quả | Cách phù hợp |
|---|---|---|
| “ID vừa sinh luôn là MAX(id)” | Có thể lấy khóa của giao dịch khác | RETURNING/OUTPUT/generated keys |
| “Khóa mới là MAX(id) + 1” | Race condition, va chạm | IDENTITY/AUTO_INCREMENT/sequence |
| “INSERT SELECT không báo lỗi nghĩa đã chèn đủ” | Mã không tìm thấy có thể tạo 0 hoặc ít hàng | Kiểm tra affected rows/RETURNING |
| “Tạo đơn xong COMMIT rồi mới chèn dòng vẫn nguyên tử” | Có thể để lại đơn thiếu chi tiết | Một transaction cho toàn workflow |
| “FK cho phép bỏ qua kiểm tra quyền” | Dòng có thể trỏ tới đơn tồn tại nhưng không thuộc người dùng | Phân quyền nghiệp vụ |
| “Mọi ID identity phải liên tục” | Rollback/sequence có thể bỏ số | Không dùng ID làm số chứng từ liên tục |
| “RETURNING của ON CONFLICT DO NOTHING cho ID cũ” | Thường trả 0 hàng khi không chèn | Xử lý nhánh conflict riêng |
| “JDBC getGeneratedKeys chạy như nhau ở mọi driver” | Khóa/batch có thể có khác biệt | Kiểm tra tài liệu driver và mapping |
| “INSERT nhiều hàng rồi ID theo đúng thứ tự VALUES” | Dễ gắn nhầm khi batch/driver thay đổi | Trả ID cùng khóa nghiệp vụ |
| “Dùng hai Connection vẫn chung transaction” | Chưa thấy cha hoặc rollback không bao phủ | Dùng cùng Connection/transaction manager |
| “Không cần kiểm tra số dòng con” | Có thể tạo đơn chỉ một phần | Xác thực đủ đầu vào, kiểm tra affected rows |
| “Nếu lỗi thì cứ COMMIT phần hợp lệ” | Dữ liệu quan hệ không hoàn chỉnh | Rollback theo quy tắc nghiệp vụ |
| “Cứ gán ID minh họa trong tài liệu vào DB thật” | Có thể vi phạm identity/FK hoặc gắn nhầm | Luôn lấy khóa thực tế |
| “Tổng số dòng sau LEFT JOIN dùng COUNT(*)” | Đơn không có con vẫn có hàng đệm | COUNT(con.id) |
| “Giá hiện tại trong danh mục luôn là giá lịch sử” | Đơn cũ bị thay đổi ý nghĩa khi cập nhật giá | Lưu đơn giá tại dòng đơn |
| “Mã yêu cầu UNIQUE đủ xử lý mọi retry” | Retry có thể thêm lại con hoặc payload khác | Idempotency bao quát transaction |
| “Lấy ID bằng SELECT ORDER BY tao_luc DESC LIMIT 1” | Trùng thời điểm, đồng thời, không bảo đảm sở hữu | RETURNING từ INSERT chính |
| “ROLLBACK sẽ trả lại ID sequence” | Sequence có thể đã tiêu thụ giá trị | Chấp nhận khoảng trống ID |

## 24. Bài tập thực hành có lời giải

Các bài dưới dùng bộ bảng `lk_khach_hang`, `lk_san_pham`, `lk_don_hang`, `lk_dong_don` của phần 3. Nên thực hành trong phiên riêng hoặc theo đúng thứ tự; những bài INSERT thực sự làm thay đổi dữ liệu và mã yêu cầu UNIQUE không thể dùng lại tùy tiện.

### Bài 1. Tạo một đơn cho An và lấy ID

**Yêu cầu:** để DBMS sinh ID, giữ trạng thái mặc định, trả ID và thời điểm tạo.

~~~sql
INSERT INTO lk_don_hang
    (khach_hang_id, ma_yeu_cau)
SELECT
    id,
    'BT-265-01'
FROM lk_khach_hang
WHERE email = 'an@example.test'
RETURNING id, ma_yeu_cau, trang_thai, tao_luc;
~~~

**Đáp án:** một hàng có ID tự sinh và trạng thái NEW nếu khách An tồn tại. Không có con số ID cố định cho mọi lần chạy.

### Bài 2. Tạo dòng đơn bằng ID từ bảng cha

**Yêu cầu:** cho đơn có mã `BT-265-01`, thêm hai sách SQL và một bút.

~~~sql
INSERT INTO lk_dong_don
    (don_hang_id, san_pham_id, so_luong, don_gia)
SELECT
    dh.id,
    sp.id,
    yc.so_luong,
    sp.gia_hien_tai
FROM lk_don_hang AS dh
CROSS JOIN (
    VALUES ('SACH_SQL', 2), ('BUT', 1)
) AS yc(ma_sp, so_luong)
JOIN lk_san_pham AS sp
    ON sp.ma_sp = yc.ma_sp
WHERE dh.ma_yeu_cau = 'BT-265-01'
RETURNING don_hang_id, san_pham_id, so_luong;
~~~

**Đáp án:** hai dòng chi tiết cùng trỏ đến ID của đơn vừa tạo ở bài 1. Tổng giá trị theo giá mẫu là `2×120000 + 1×10000 = 250000`.

### Bài 3. Tạo cha–con trong một statement

**Yêu cầu:** tạo đơn cho Bình với một Sách SQL và hai Sổ tay, không biết trước khóa đơn.

~~~sql
WITH don_moi AS (
    INSERT INTO lk_don_hang
        (khach_hang_id, ma_yeu_cau)
    SELECT id, 'BT-265-03'
    FROM lk_khach_hang
    WHERE email = 'binh@example.test'
    RETURNING id
)
INSERT INTO lk_dong_don
    (don_hang_id, san_pham_id, so_luong, don_gia)
SELECT
    d.id,
    sp.id,
    yc.so_luong,
    sp.gia_hien_tai
FROM don_moi AS d
CROSS JOIN (
    VALUES ('SACH_SQL', 1), ('SO_TAY', 2)
) AS yc(ma_sp, so_luong)
JOIN lk_san_pham AS sp
    ON sp.ma_sp = yc.ma_sp
RETURNING don_hang_id, san_pham_id, so_luong;
~~~

**Đáp án:** một đơn, hai dòng; tổng tiền theo đơn giá mẫu là `120000 + 60000 = 180000`. ID đơn không cần hardcode vì lấy từ CTE `don_moi`.

### Bài 4. Vì sao không dùng MAX(id)?

**Đề bài:** A chèn đơn và được ID 50; B chèn đơn và được ID 51 rồi commit. A chạy `SELECT MAX(id)` và nhận 51. Dòng con của A sẽ bị gắn vào đâu?

**Đáp án:** nếu A dùng 51, dòng có thể gắn sai vào đơn của B, dù FK vẫn thấy đơn 51 tồn tại. Phải dùng ID 50 từ INSERT của A, được lấy qua RETURNING/generated keys.

### Bài 5. Kiểm tra một mã sản phẩm không tồn tại

**Yêu cầu:** chèn một dòng bằng `INSERT ... SELECT` với `ma_sp = 'KHONG_CO'`. Vì sao câu lệnh có thể không lỗi mà không có dòng mới?

~~~sql
INSERT INTO lk_dong_don
    (don_hang_id, san_pham_id, so_luong, don_gia)
SELECT
    dh.id,
    sp.id,
    1,
    sp.gia_hien_tai
FROM lk_don_hang AS dh
JOIN lk_san_pham AS sp
    ON sp.ma_sp = 'KHONG_CO'
WHERE dh.ma_yeu_cau = 'BT-265-01'
RETURNING id;
~~~

**Đáp án:** JOIN không tìm thấy sản phẩm nên SELECT nguồn trả 0 hàng; INSERT cũng thêm 0 hàng. Ứng dụng phải kiểm tra số hàng nếu yêu cầu bắt buộc có một dòng.

### Bài 6. Ràng buộc nào bảo vệ liên kết đơn–dòng?

**Đề bài:** nếu cố chèn `don_hang_id = -1` không tồn tại, ràng buộc nào chặn? Nếu trùng cùng cặp đơn và sản phẩm, ràng buộc nào chặn?

**Đáp án:** FOREIGN KEY trên `don_hang_id` chặn tham chiếu không tồn tại. UNIQUE `(don_hang_id, san_pham_id)` chặn cùng sản phẩm lặp theo mô hình bài. PRIMARY KEY trên `id` của dòng bảo đảm mỗi dòng có khóa riêng.

### Bài 7. Khi nào cần transaction?

**Đề bài:** ứng dụng tạo đơn, thêm dòng A thành công, thêm dòng B lỗi. Muốn bảo đảm đơn không có một phần chi tiết thì làm gì?

**Đáp án:** cả ba thao tác thuộc cùng transaction; khi dòng B lỗi, ROLLBACK toàn bộ. Không commit đơn và dòng A trước khi dòng B hoàn tất.

### Bài 8. Lấy khóa theo cặp email–ID cho nhiều khách hàng

~~~sql
INSERT INTO lk_khach_hang (email, ho_ten)
VALUES
    ('hoa@example.test', 'Hòa'),
    ('lam@example.test', 'Lâm')
RETURNING id, email;
~~~

**Đáp án:** hai hàng có ID mới và email tương ứng. Ứng dụng ánh xạ bằng email UNIQUE; không giả định ID thứ nhất ứng với dòng VALUES thứ nhất nếu driver/công nghệ không bảo đảm cách trả thứ tự.

### Bài 9. Tính tổng một đơn không dùng ID cố định

**Yêu cầu:** với `BT-265-03`, đếm dòng và tổng tiền theo giá đã lưu trong dòng đơn.

~~~sql
SELECT
    dh.ma_yeu_cau,
    COUNT(dd.id) AS so_dong,
    COALESCE(
        SUM(dd.so_luong * dd.don_gia),
        0
    ) AS tong_tien
FROM lk_don_hang AS dh
LEFT JOIN lk_dong_don AS dd
    ON dd.don_hang_id = dh.id
WHERE dh.ma_yeu_cau = 'BT-265-03'
GROUP BY dh.id, dh.ma_yeu_cau;
~~~

**Đáp án:** nếu bài 3 chạy thành công và chưa sửa dữ liệu, `so_dong = 2` và `tong_tien = 180000`.

### Bài 10. Vì sao ON CONFLICT DO NOTHING RETURNING id rỗng?

**Đề bài:** nếu `ma_yeu_cau = 'BT-265-03'` đã tồn tại, câu INSERT với `ON CONFLICT (ma_yeu_cau) DO NOTHING RETURNING id` trả bao nhiêu hàng?

**Đáp án:** thường **0 hàng** vì không có INSERT mới. Nó không tự lấy ID của đơn đã tồn tại. Muốn tái sử dụng đơn cũ, phải truy vấn và xác thực theo quy trình idempotency phù hợp.

### Bài 11. Tạo sinh viên và khóa học rồi đăng ký

**Yêu cầu:** tạo sinh viên `SV002`, sau đó đăng ký khóa `SQL_CO_BAN` đã tồn tại; không hardcode ID.

~~~sql
BEGIN;

INSERT INTO lk_sinh_vien (ma_sv, ho_ten)
VALUES ('SV002', 'Phương')
RETURNING id, ma_sv;

INSERT INTO lk_dang_ky (sinh_vien_id, khoa_hoc_id)
SELECT
    sv.id,
    kh.id
FROM lk_sinh_vien AS sv
CROSS JOIN lk_khoa_hoc AS kh
WHERE sv.ma_sv = 'SV002'
  AND kh.ma_khoa = 'SQL_CO_BAN'
RETURNING sinh_vien_id, khoa_hoc_id;

COMMIT;
~~~

**Đáp án:** một sinh viên mới và một dòng đăng ký nếu khóa học tồn tại. Nhưng vì INSERT ... SELECT có thể thêm 0 hàng nếu khóa học không có, việc quyết định COMMIT phải dựa trên xác nhận kết quả và yêu cầu nghiệp vụ. Đoạn script minh họa cấu trúc; trong ứng dụng, kiểm tra số hàng trước COMMIT.

### Bài 12. Sửa lỗi JDBC khi dùng hai Connection

**Đề bài:** hàm `insertOrder(connA)` trả ID mới trong transaction A chưa commit; hàm `insertLine(connB, id)` dùng một kết nối B khác rồi cố chèn FK. Vì sao nguy hiểm?

**Đáp án:** A và B không cùng transaction. B có thể chưa nhìn thấy đơn mới của A, có thể phải chờ hoặc thất bại, và rollback A không bao phủ thao tác ở B. Dùng cùng Connection trong transaction hoặc để transaction manager đảm bảo các thao tác cùng ngữ cảnh.

### Bài 13. Đếm số dòng từ RETURNING

**Yêu cầu:** một lệnh INSERT con dự kiến tạo ba sản phẩm nhưng RETURNING chỉ trả hai dòng. Có thể COMMIT không?

**Đáp án:** nếu nghiệp vụ bắt buộc đủ ba, **không**. Cần kiểm tra sản phẩm nào không được tìm thấy, dữ liệu trùng hay điều kiện lọc làm mất hàng; rollback hoặc không tạo đơn ngay từ đầu theo thiết kế. Sự thiếu hàng có thể không tự phát sinh lỗi ràng buộc.

### Bài 14. Giá lịch sử và giá hiện tại

**Đề bài:** đơn được tạo khi Sách SQL có giá 120000; hôm sau giá danh mục thành 130000. Tổng tiền dòng đơn cũ nên dựa vào cột nào?

**Đáp án:** `lk_dong_don.don_gia` đã được lưu khi đặt hàng, không lấy `lk_san_pham.gia_hien_tai` để tính lại lịch sử. Quy trình tạo đơn cần ghi nhận giá đã được chấp nhận theo nghiệp vụ.

### Bài 15. Sequence bỏ số có phải lỗi?

**Đề bài:** một transaction được cấp ID 10 rồi ROLLBACK. Lần sau ID là 11, không có đơn nào ID 10. Có nên tự cập nhật sequence về 10?

**Đáp án:** không. Khoảng trống ID là hành vi bình thường của sequence. Cố chỉnh sequence khi có nhiều kết nối có thể gây trùng khóa hoặc xung đột; không dùng ID kỹ thuật như số chứng từ bắt buộc liên tục.

### Bài 16. Xác định lệnh đúng theo hệ quản trị

**Đề bài:** ghép lựa chọn kỹ thuật với DBMS:

| DBMS | Lựa chọn |
|---|---|
| PostgreSQL | `INSERT ... RETURNING id` |
| SQL Server | `OUTPUT INSERTED.Id` |
| MySQL | `LAST_INSERT_ID()` cùng connection/JDBC generated keys |
| Oracle | `RETURNING id INTO bien` trong ngữ cảnh PL/SQL phù hợp |
| SQLite hiện đại | `INSERT ... RETURNING id` khi phiên bản hỗ trợ |

**Đáp án:** những lựa chọn trên là các hướng thông dụng; cần xác nhận phiên bản và driver. Không áp dụng nguyên cú pháp của hệ này sang hệ kia.

## 25. Quy trình chuẩn khi thiết kế thao tác tạo dữ liệu liên quan

Khi lập trình tạo đơn hàng, phiếu nhập hoặc bản ghi cha–con, có thể dựa vào quy trình sau:

### Bước 1 — Xác định khóa và quan hệ

- Bảng nào là cha, bảng nào là con?
- FK nào bắt buộc?
- PK nào được DBMS sinh, khóa nghiệp vụ nào có UNIQUE?
- Một cha có thể có bao nhiêu con và có cho phép con trùng dữ liệu không?

### Bước 2 — Xác thực đầu vào và quyền

- Khách hàng tồn tại và người gọi được quyền tạo dữ liệu?
- Danh sách sản phẩm hợp lệ, số lượng dương, không thiếu mã?
- Giá/thuế/chiết khấu được tính theo quy tắc được phép?
- Có mã yêu cầu để chống tạo trùng khi retry không?

### Bước 3 — Mở transaction khi cần nhiều statement

- Dùng một Connection hoặc transaction manager.
- Không commit giữa chừng.
- Xác định điều kiện hoàn tất toàn bộ nghiệp vụ.

### Bước 4 — INSERT cha và lấy khóa thực

- Ưu tiên RETURNING/OUTPUT/generated keys theo DBMS.
- Đọc đúng số hàng trả về.
- Không dùng MAX(id), ID lớn nhất hoặc số ID tự đoán.

### Bước 5 — INSERT con với chính khóa vừa nhận

- Sử dụng ID cha đã lấy trong transaction.
- Tra cứu FK khác theo khóa duy nhất.
- Chèn đúng số dòng, kiểm tra kết quả và ràng buộc.

### Bước 6 — Xác minh điều kiện nghiệp vụ rồi COMMIT

- Số dòng, sản phẩm, số lượng và giá đúng?
- Không có thao tác nào bị bỏ qua vì INSERT ... SELECT trả 0 dòng?
- Nếu lỗi, ROLLBACK toàn bộ phần phải nguyên tử.

### Bước 7 — Trả phản hồi có định danh đáng tin cậy

- Trả ID đơn và trạng thái từ thao tác đã hoàn tất.
- Khi request được gửi lại, đối chiếu mã yêu cầu và trạng thái thay vì tạo trùng.
- Không coi ID là bằng chứng phân quyền.

## 26. Tổng kết

Khi **tạo dữ liệu liên quan và lấy khóa vừa sinh**, tư duy đúng là thiết kế một thao tác **liên kết được, nguyên tử và an toàn trước cạnh tranh**:

- Tạo **bản ghi cha trước**, lấy ID thực do database sinh, rồi dùng ID ấy làm FK của bản ghi con.
- Với PostgreSQL, `INSERT ... RETURNING id` là cách trực tiếp để nhận khóa cùng statement; data-modifying CTE có thể truyền khóa mới từ INSERT cha sang INSERT con trong **một statement**.
- Với ứng dụng Java, có thể dùng PostgreSQL RETURNING hoặc JDBC `getGeneratedKeys`; nếu có nhiều statement, chúng cần thuộc **cùng transaction**.
- `INSERT ... SELECT` có thể thêm **0 hoặc ít hàng hơn dự kiến** khi dữ liệu tham chiếu thiếu; ứng dụng phải kiểm tra số hàng thật và quy tắc nghiệp vụ.
- Không lấy ID cha bằng `MAX(id)`, `ORDER BY id DESC LIMIT 1` hoặc phép tính `MAX(id)+1`; những cách này không gắn khóa với INSERT của bạn và có thể sai khi nhiều người ghi đồng thời.
- Ràng buộc **PRIMARY KEY, FOREIGN KEY, UNIQUE, CHECK** giúp giữ dữ liệu đúng cấu trúc, nhưng không thay thế xác thực quyền, tính giá, kiểm tra đủ chi tiết và xử lý retry.
- ID tự sinh không cần liên tục; khoảng trống sau ROLLBACK là bình thường.
- Mỗi DBMS có cú pháp lấy khóa khác nhau, nhưng nguyên tắc chung vẫn là **nhận khóa từ chính thao tác INSERT, giữ đúng ngữ cảnh kết nối và transaction**.

Khi nắm vững luồng **INSERT cha → nhận khóa → INSERT con → kiểm tra → COMMIT**, bạn sẽ có nền tảng an toàn để xây dựng các chức năng tạo đơn hàng, đăng ký học, phiếu nhập kho và mọi dữ liệu có quan hệ trong cơ sở dữ liệu SQL.

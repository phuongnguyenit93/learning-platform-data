# Khai báo cột, kiểu dữ liệu và giá trị mặc định trong SQL

Khi thiết kế một bảng SQL, việc đặt tên bảng mới chỉ là bước đầu. Người thiết kế còn phải xác định **bảng chứa những cột nào, mỗi cột chấp nhận dạng dữ liệu gì, có được để trống hay không, và nếu ứng dụng không truyền giá trị thì cơ sở dữ liệu xử lý thế nào**. Các lựa chọn này tạo thành một phần quan trọng của *lược đồ* (schema), quyết định dữ liệu được lưu hợp lệ ra sao và ảnh hưởng lâu dài đến câu truy vấn, API, hiệu năng và khả năng nâng cấp ứng dụng.

Bài học giải thích cách khai báo cột trong `CREATE TABLE` và `ALTER TABLE`, chọn kiểu dữ liệu phù hợp, sử dụng `NULL`/`NOT NULL`, khai báo `DEFAULT`, phân biệt giá trị mặc định với giá trị được tính toán hoặc tự sinh, rồi áp dụng vào một mô hình bán hàng. Ví dụ thực hành chính dùng **PostgreSQL**; các phần so sánh chỉ rõ những điểm khác ở MySQL, SQL Server và Oracle Database.

## 1. Bảng và cột thuộc về lược đồ dữ liệu

Trong cơ sở dữ liệu quan hệ, **bảng** (*table*) lưu tập các hàng (*row*), còn **cột** (*column*) mô tả một thuộc tính của thực thể. Ví dụ, bảng `san_pham` có thể chứa tên sản phẩm, giá, số lượng tồn kho và thời điểm tạo.

~~~text
san_pham
┌────┬──────────────┬───────────┬─────────┬───────────┐
│ id │ ten          │ gia       │ ton_kho │ dang_ban  │
├────┼──────────────┼───────────┼─────────┼───────────┤
│  1 │ Ban phim     │ 450000.00 │      12 │ true      │
│  2 │ Chuot        │ 250000.00 │      20 │ true      │
└────┴──────────────┴───────────┴─────────┴───────────┘
~~~

Ở mức lược đồ, mỗi cột cần trả lời các câu hỏi:

| Câu hỏi | Ví dụ trả lời | Cấu phần SQL liên quan |
| --- | --- | --- |
| Cột tên gì? | `gia` | Định danh cột |
| Kiểu giá trị được lưu? | Số thập phân chính xác | `NUMERIC(12, 2)` |
| Có bắt buộc nhập? | Có | `NOT NULL` |
| Giá trị nào được phép? | Không âm | `CHECK (gia >= 0)` |
| Nếu bỏ qua khi thêm hàng? | Không có mặc định | Không khai báo `DEFAULT` |
| Cột có nhận diện hàng? | `id` là khóa chính | `PRIMARY KEY` |
| Giá trị có tự sinh? | ID từ sequence/identity | `GENERATED ... AS IDENTITY` |

Một **khai báo cột** thông thường có dạng khái quát:

~~~sql
ten_cot kieu_du_lieu
    [DEFAULT bieu_thuc]
    [rang_buoc_cot ...]
~~~

Ký hiệu `[...]` ở đây mô tả phần **tùy chọn** trong tài liệu cú pháp, không phải dấu ngoặc vuông cần gõ trong câu SQL. Thứ tự và các tùy chọn chính xác phụ thuộc hệ quản trị và loại ràng buộc. Có thể khai báo một số ràng buộc ở cấp cột, cũng có thể khai báo ở cấp bảng, đặc biệt khi chúng liên quan nhiều cột.

## 2. Khai báo cột bằng CREATE TABLE

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE san_pham (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ten VARCHAR(150) NOT NULL,
    gia NUMERIC(12, 2) NOT NULL CHECK (gia >= 0),
    ton_kho INTEGER NOT NULL DEFAULT 0 CHECK (ton_kho >= 0),
    dang_ban BOOLEAN NOT NULL DEFAULT TRUE,
    ngay_tao TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ghi_chu TEXT
);
~~~

Phân tích lần lượt:

- `id BIGINT ... PRIMARY KEY`: khóa định danh có kiểu số nguyên lớn, giá trị được PostgreSQL cấp bằng cơ chế identity; khóa chính không được `NULL` và phải duy nhất.
- `ten VARCHAR(150) NOT NULL`: tên sản phẩm là chuỗi có giới hạn tối đa 150 ký tự theo ngữ nghĩa kiểu của PostgreSQL, phải có giá trị khác `NULL`.
- `gia NUMERIC(12, 2) NOT NULL CHECK (gia >= 0)`: giá có nhiều nhất 12 chữ số tổng cộng, trong đó 2 chữ số sau dấu thập phân; giá phải không âm.
- `ton_kho INTEGER NOT NULL DEFAULT 0`: nếu câu lệnh thêm hàng bỏ qua cột này thì hệ quản trị dùng giá trị mặc định `0`; ràng buộc cũng ngăn số âm.
- `dang_ban BOOLEAN NOT NULL DEFAULT TRUE`: sản phẩm mới mặc định ở trạng thái đang bán.
- `ngay_tao TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP`: ghi thời điểm mặc định theo đồng hồ giao dịch của PostgreSQL.
- `ghi_chu TEXT`: không khai báo `NOT NULL` và không có `DEFAULT`, vì vậy mặc định có thể nhận `NULL`.

`PRIMARY KEY`, `NOT NULL`, `CHECK` là **ràng buộc** nhằm bảo vệ tính hợp lệ của dữ liệu. `DEFAULT` là **quy tắc cấp giá trị khi bỏ qua cột hoặc yêu cầu dùng mặc định**. Hai vai trò khác nhau và thường được kết hợp.

### 2.1. Định danh cột và quy ước tên

Để ít phụ thuộc vào dấu trích dẫn định danh giữa các DBMS, có thể dùng tên chữ thường, không dấu, phân tách từ bằng `_`: `ngay_tao`, `so_luong`, `gia_ban`. Tránh từ khóa như `ORDER`, `GROUP`, tránh khoảng trắng và tên dễ gây hiểu nhầm. PostgreSQL có cơ chế chuyển định danh không trích dẫn về chữ thường; Oracle thường chuyển sang chữ hoa; SQL Server và MySQL có thêm quy tắc phụ thuộc cấu hình. Cách viết `snake_case` giúp giảm sai sót khi dùng SQL viết tay, migration và ORM.

### 2.2. Chọn cột cần lưu, không chỉ chọn kiểu

Một thiết kế tốt cần phân biệt **dữ liệu gốc cần lưu** với **giá trị có thể tính từ dữ liệu khác**. Ví dụ `so_luong`, `don_gia` và `thanh_tien` có quan hệ nhân; nếu luôn lưu cả ba mà không có cơ chế bảo đảm tính nhất quán, chúng có thể mâu thuẫn sau khi cập nhật. Cột được tính toán (*generated/computed column*) hoặc biểu thức trong truy vấn đôi khi thích hợp hơn một cột thường. Phần 8 sẽ phân biệt rõ với `DEFAULT`.

## 3. Chọn kiểu dữ liệu phù hợp cho từng cột

**Kiểu dữ liệu** là hợp đồng giữa ứng dụng và cơ sở dữ liệu: hệ quản trị dùng nó để kiểm tra giá trị, lưu trữ, so sánh, tính toán và hỗ trợ các phép toán hợp lệ. Không nên chọn `VARCHAR` cho mọi cột chỉ vì mọi giá trị đều có thể chuyển thành văn bản.

### 3.1. Các nhóm kiểu dữ liệu thường gặp

| Nhóm | Kiểu minh họa PostgreSQL | Dùng cho | Lưu ý |
| --- | --- | --- | --- |
| Số nguyên | `SMALLINT`, `INTEGER`, `BIGINT` | Số lượng, thứ tự, khóa số nguyên | Có giới hạn trên/dưới; không lưu chữ số có nghĩa như chuỗi mã bưu chính. |
| Số thập phân chính xác | `NUMERIC(p,s)`, `DECIMAL(p,s)` | Tiền, tỷ lệ cần quy tắc làm tròn rõ | `p` là precision, `s` là scale; phải định nghĩa đơn vị tiền/tỷ giá. |
| Số thực xấp xỉ | `REAL`, `DOUBLE PRECISION` | Đo lường, khoa học, tính toán có sai số chấp nhận được | Không dùng tùy tiện cho tiền cần độ chính xác thập phân. |
| Chuỗi | `CHAR(n)`, `VARCHAR(n)`, `TEXT` | Tên, mô tả, mã văn bản | Cần xét giới hạn dài, encoding và collation. |
| Logic | `BOOLEAN` | Bật/tắt, có/không | Có thể có `NULL` nếu không `NOT NULL`. |
| Ngày/giờ | `DATE`, `TIME`, `TIMESTAMP`, `TIMESTAMPTZ` | Ngày sinh, giờ địa phương, thời điểm sự kiện | Phân biệt ngày, giờ và thời điểm tuyệt đối. |
| Nhị phân | `BYTEA` | File, chữ ký số, mã băm | Là byte, không phải chuỗi ký tự Base64/hex. |
| Định danh | `UUID` | Mã bản ghi phát sinh từ nhiều dịch vụ | Khác `VARCHAR(36)` và khóa tự tăng. |
| Dữ liệu cấu trúc | `JSONB`, `JSON` | Thuộc tính linh hoạt có cấu trúc | Không thay thế thiết kế quan hệ cho mọi trường hợp. |
| Khác | `INTERVAL`, kiểu mảng, enum, kiểu tự định nghĩa | Khoảng thời gian, dữ liệu chuyên biệt | Phụ thuộc DBMS và khả năng mở rộng ứng dụng. |

Mỗi DBMS có bộ kiểu và quy tắc riêng. Ví dụ MySQL dùng `DATETIME`/`TIMESTAMP` với hành vi múi giờ khác PostgreSQL; SQL Server có `DATETIME2`, `DATETIMEOFFSET`; Oracle có `VARCHAR2`, `NUMBER`, `TIMESTAMP WITH TIME ZONE`. Khi viết SQL đa hệ quản trị, cần kiểm tra kiểu tương đương thực sự thay vì chỉ thay tên từ khóa.

### 3.2. Số nguyên: phạm vi quan trọng hơn thói quen

Trong PostgreSQL:

| Kiểu | Dung lượng giá trị | Phạm vi số nguyên có dấu |
| --- | --- | --- |
| `SMALLINT` | 2 byte | −32.768 đến 32.767 |
| `INTEGER` | 4 byte | −2.147.483.648 đến 2.147.483.647 |
| `BIGINT` | 8 byte | −9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 |

`INTEGER` thường đủ cho số lượng nhỏ và bộ đếm; `BIGINT` phù hợp khi ID hoặc tổng giá trị có thể tăng rất lớn. Dữ liệu đầu vào vượt phạm vi sẽ bị từ chối thay vì tự động biến một cột `INTEGER` thành `BIGINT`.

**Phân biệt số và mã:** `ma_buu_chinh = '00123'` là mã có số 0 ở đầu, không phải số để cộng trừ. Nên lưu bằng kiểu chuỗi thay vì `INTEGER`. Tương tự, số điện thoại có dấu `+`, có số 0 đầu và không tham gia phép toán số học.

### 3.3. DECIMAL/NUMERIC cho giá trị thập phân chính xác

~~~sql
gia NUMERIC(12, 2) NOT NULL
~~~

`NUMERIC(12,2)` cho **12 chữ số có nghĩa**, trong đó **2 chữ số sau dấu thập phân**; vùng trước dấu thập phân thường có tối đa 10 chữ số trong những giá trị được chấp nhận. Ví dụ `1234567890.12` nằm trong giới hạn; `12345678901.23` vượt giới hạn. PostgreSQL làm tròn giá trị có quá nhiều chữ số sau dấu thập phân theo quy tắc của `numeric` trước khi kiểm tra liệu giá trị có vừa precision đã khai báo hay không.

~~~sql
CREATE TABLE gia_tham_khao (
    id INTEGER PRIMARY KEY,
    gia NUMERIC(12, 2) NOT NULL CHECK (gia >= 0)
);

INSERT INTO gia_tham_khao (id, gia)
VALUES (1, 199000.50);
~~~

Với phép tính tiền nhiều đơn vị tiền tệ, phải xác định **đơn vị, số chữ số thập phân và quy tắc làm tròn nghiệp vụ**. Không nên giả định mọi loại tiền đều có hai chữ số thập phân. Kiểu `DOUBLE PRECISION` biểu diễn số thực theo dạng nhị phân xấp xỉ; các biểu thức như `0.1 + 0.2` có thể không có giá trị nhị phân đúng bằng `0.3`.

### 3.4. VARCHAR, TEXT và CHAR

- `VARCHAR(n)`: chuỗi có giới hạn chiều dài `n`; hữu ích khi miền nghiệp vụ yêu cầu giới hạn rõ.
- `TEXT`: chuỗi có độ dài biến đổi trong giới hạn DBMS; phù hợp mô tả, nội dung không cần `n` cố định.
- `CHAR(n)`: kiểu ký tự có độ dài cố định và hành vi đệm khoảng trắng; chỉ nên chọn khi thực sự cần ngữ nghĩa đó.

~~~sql
ho_ten VARCHAR(150) NOT NULL,
mo_ta TEXT,
ma_quoc_gia CHAR(2)
~~~

Trong PostgreSQL, `VARCHAR(n)` đo chiều dài theo **số ký tự**, không đơn thuần là số byte UTF-8; còn việc lưu trữ thực tế phụ thuộc encoding. Các hệ quản trị khác có thể có lựa chọn chiều dài theo byte/ký tự. Đặc biệt SQL Server thường cần `NVARCHAR` để hỗ trợ Unicode theo ngữ nghĩa quen thuộc, còn Oracle phân biệt tùy chọn độ dài `BYTE`/`CHAR` cho một số kiểu. Hãy thử dữ liệu tiếng Việt thực tế thay vì chỉ kiểm tra chuỗi ASCII.

### 3.5. BOOLEAN và giá trị ba trạng thái

~~~sql
da_thanh_toan BOOLEAN NOT NULL DEFAULT FALSE
~~~

`BOOLEAN` thường biểu diễn `TRUE` và `FALSE`, nhưng cột **có thể chứa `NULL`** nếu không khai báo `NOT NULL`. `NULL` có nghĩa **chưa biết/không có giá trị**, không đồng nhất với `FALSE`. Truy vấn:

~~~sql
SELECT *
FROM don_hang
WHERE da_thanh_toan = FALSE;
~~~

chỉ chọn những hàng thực sự có giá trị `FALSE`, không tự bao gồm các hàng có `NULL`. Trong PostgreSQL có thể kiểm tra `IS NULL`, `IS TRUE`, `IS FALSE`, hoặc dùng `COALESCE` khi nghiệp vụ quy định cách xử lý giá trị chưa biết.

### 3.6. Ngày giờ: chọn đúng loại thời gian

| Kiểu PostgreSQL | Ý nghĩa thường gặp | Ví dụ ứng dụng |
| --- | --- | --- |
| `DATE` | Ngày trên lịch, không có giờ | Ngày sinh, ngày đến hạn |
| `TIME` | Giờ trong ngày, không kèm ngày | Giờ mở cửa dự kiến |
| `TIMESTAMP WITHOUT TIME ZONE` | Ngày và giờ theo lịch, không mang thông tin múi giờ | Lịch cố định theo giờ địa phương nếu có quy ước timezone riêng |
| `TIMESTAMP WITH TIME ZONE` / `TIMESTAMPTZ` | Thời điểm trên trục thời gian, hiển thị theo múi giờ phiên làm việc | Thời điểm tạo đơn, sự kiện hệ thống |

PostgreSQL lưu `TIMESTAMPTZ` theo thời điểm tuyệt đối và chuyển đổi khi nhập/hiển thị dựa trên múi giờ; **không lưu nguyên nhãn tên múi giờ** như `Asia/Ho_Chi_Minh` bên trong mỗi giá trị. Nếu nghiệp vụ cần giữ múi giờ gốc của người dùng, lưu thêm thông tin múi giờ ở cột riêng.

Ví dụ:

~~~sql
ngay_giao_du_kien DATE,
ngay_tao TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
~~~

Một cột `DATE` có giá trị mặc định `CURRENT_DATE` nếu muốn mặc định ngày hiện hành theo quy tắc phiên DBMS; một cột ghi thời điểm sự kiện thường dùng `CURRENT_TIMESTAMP` hoặc giá trị thời gian do ứng dụng cung cấp theo hợp đồng đã chọn.

## 4. NULL, NOT NULL và các ràng buộc có liên quan

**`NULL` biểu diễn sự thiếu/không xác định của một giá trị**, không phải số `0`, chuỗi rỗng `''`, hay `FALSE`.

~~~sql
CREATE TABLE khach_hang (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ho_ten VARCHAR(150) NOT NULL,
    email VARCHAR(255),
    ngay_dang_ky DATE NOT NULL DEFAULT CURRENT_DATE
);
~~~

Trong bảng trên, `ho_ten` bắt buộc có giá trị khác `NULL`; `email` có thể chưa biết; `ngay_dang_ky` mặc định ngày hiện hành khi bỏ qua cột.

`NOT NULL` chỉ ngăn `NULL`, **không tự ngăn chuỗi rỗng hoặc chỉ có khoảng trắng** ở PostgreSQL:

~~~sql
-- Trong PostgreSQL, chuỗi rỗng không phải NULL:
INSERT INTO khach_hang (ho_ten)
VALUES ('');
~~~

Để buộc chuỗi có nội dung, có thể thêm ràng buộc nghiệp vụ:

~~~sql
ALTER TABLE khach_hang
ADD CONSTRAINT ck_khach_hang_ho_ten
CHECK (length(btrim(ho_ten)) > 0);
~~~

Điều kiện `CHECK` được kiểm tra trên giá trị hàng khi ghi hoặc cập nhật; trong SQL nói chung, `CHECK` không thay cho `NOT NULL` vì một biểu thức trả về `UNKNOWN` do `NULL` có thể được coi là không vi phạm `CHECK`. Trên Oracle, chuỗi ký tự độ dài bằng không lại thường được xử lý như `NULL` với các kiểu chuỗi hiện hành, nên không được suy diễn nguyên quy tắc PostgreSQL sang Oracle.

Các ràng buộc có vai trò bổ trợ:

| Ràng buộc | Chức năng | Minh họa |
| --- | --- | --- |
| `NOT NULL` | Bắt buộc có giá trị | `ten TEXT NOT NULL` |
| `CHECK` | Điều kiện đúng cho từng hàng | `CHECK (so_luong > 0)` |
| `UNIQUE` | Ngăn tổ hợp giá trị trùng theo quy tắc DBMS | `UNIQUE (email)` |
| `PRIMARY KEY` | Định danh duy nhất, không `NULL` | `id BIGINT PRIMARY KEY` |
| `FOREIGN KEY` | Bảo vệ quan hệ tham chiếu | `REFERENCES khach_hang(id)` |
| `DEFAULT` | Cung cấp giá trị khi được yêu cầu/bỏ qua | `DEFAULT CURRENT_DATE` |

**`DEFAULT` không phải ràng buộc tính duy nhất hoặc tính hợp lệ**: nếu khai báo `gia NUMERIC DEFAULT -10` mà không có `CHECK`, cơ sở dữ liệu vẫn có thể lưu `-10`. Tương tự, giá trị mặc định không tự buộc ứng dụng luôn dùng giá trị đó.

## 5. DEFAULT hoạt động khi nào?

`DEFAULT` định nghĩa **biểu thức để cấp giá trị cho một cột khi `INSERT` bỏ qua cột đó hoặc câu lệnh yêu cầu rõ từ khóa `DEFAULT`**. Với PostgreSQL, nếu cột không có mặc định tường minh, giá trị mặc định hiệu lực thông thường là `NULL` (trừ cột có cơ chế đặc biệt như identity/generated).

Xét bảng:

~~~sql
CREATE TABLE don_hang_mau (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mo_ta TEXT NOT NULL,
    so_luong INTEGER NOT NULL DEFAULT 1 CHECK (so_luong > 0),
    trang_thai VARCHAR(20) NOT NULL DEFAULT 'MOI',
    ghi_chu TEXT,
    ngay_tao TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

### 5.1. Bỏ qua cột ở INSERT

~~~sql
INSERT INTO don_hang_mau (mo_ta)
VALUES ('Dat hang thu nghiem')
RETURNING id, so_luong, trang_thai, ghi_chu, ngay_tao;
~~~

Giả sử đây là bản ghi đầu tiên, giá trị nhận được sẽ **tương tự**:

| id | so_luong | trang_thai | ghi_chu | ngay_tao |
| --- | --- | --- | --- | --- |
| Giá trị identity được cấp | 1 | `MOI` | `NULL` | Thời điểm mặc định khi thực hiện |

Không nên giả định ID chắc chắn bắt đầu từ 1 trong một bảng đã có dữ liệu hoặc sau khi sequence thay đổi. Các cột có `DEFAULT` nhận giá trị mặc định; `ghi_chu` không có `DEFAULT` nên nhận `NULL`; `mo_ta` bắt buộc được truyền vì không có giá trị mặc định và có `NOT NULL`.

### 5.2. Yêu cầu dùng DEFAULT tường minh

~~~sql
INSERT INTO don_hang_mau (mo_ta, so_luong, trang_thai)
VALUES ('Don thu hai', DEFAULT, DEFAULT);
~~~

Ở đây `DEFAULT` là từ khóa SQL, **không phải chuỗi** `'DEFAULT'`. Câu lệnh yêu cầu hệ quản trị dùng `1` cho `so_luong` và `'MOI'` cho `trang_thai`.

Trong PostgreSQL, cũng có thể yêu cầu đặt lại giá trị cột về mặc định khi cập nhật:

~~~sql
UPDATE don_hang_mau
SET trang_thai = DEFAULT
WHERE id = 1;
~~~

`UPDATE ... SET col = DEFAULT` là hành động **chủ động**; cơ sở dữ liệu không tự áp dụng `DEFAULT` cho cột khác ở mỗi lần cập nhật. Ví dụ cập nhật `so_luong` không làm `ngay_tao` tự đổi nếu không có trigger, logic ứng dụng hay cơ chế riêng.

### 5.3. Chỉ rõ NULL khác với bỏ qua cột

~~~sql
-- Bỏ qua ghi_chu: PostgreSQL dùng mặc định hiệu lực NULL.
INSERT INTO don_hang_mau (mo_ta)
VALUES ('Khong co ghi chu');

-- Chỉ rõ NULL cho ghi_chu: vẫn hợp lệ vì cột cho phép NULL.
INSERT INTO don_hang_mau (mo_ta, ghi_chu)
VALUES ('Ghi chu khong biet', NULL);

-- Nếu chỉ rõ NULL cho so_luong, sẽ vi phạm NOT NULL:
-- INSERT INTO don_hang_mau (mo_ta, so_luong)
-- VALUES ('Don loi', NULL);
~~~

**`DEFAULT 1` không chuyển một giá trị `NULL` được truyền tường minh thành `1` trong PostgreSQL.** Lỗi dễ gặp là ứng dụng luôn gửi đủ cột, điền `NULL` khi không có dữ liệu rồi mong DB sử dụng mặc định. Với thiết kế kiểu này, ứng dụng phải bỏ qua cột, truyền từ khóa `DEFAULT` trong SQL thích hợp, hoặc tự quyết định giá trị tại tầng ứng dụng.

Một số DBMS có lựa chọn chế độ SQL và ngoại lệ xử lý khác nhau; vì vậy luôn xác định rõ hệ quản trị và cấu hình khi trao đổi về `DEFAULT` với `NULL`.

### 5.4. Các kiểu biểu thức mặc định

| Mục đích | Ví dụ PostgreSQL | Ý nghĩa |
| --- | --- | --- |
| Hằng số | `DEFAULT 0` | Số mặc định |
| Giá trị logic | `DEFAULT FALSE` | Trạng thái mặc định |
| Chuỗi | `DEFAULT 'MOI'` | Trạng thái nghiệp vụ |
| Ngày hiện hành | `DEFAULT CURRENT_DATE` | Ngày dựa trên phiên và quy tắc DB |
| Thời điểm | `DEFAULT CURRENT_TIMESTAMP` | Thời điểm gắn với transaction trong PostgreSQL |
| UUID ngẫu nhiên | `DEFAULT gen_random_uuid()` | Sinh định danh UUID mỗi lần dùng mặc định |
| Kết quả hàm khác | `DEFAULT lower('ABC')` | Tính biểu thức cho giá trị mặc định, nếu được phép |

PostgreSQL cho phép nhiều biểu thức mặc định, nhưng **một biểu thức `DEFAULT` của cột không thể trực tiếp tham chiếu cột khác trong cùng hàng**:

~~~sql
-- KHÔNG hợp lệ như một DEFAULT trong PostgreSQL:
-- thanh_tien NUMERIC(14, 2) DEFAULT (so_luong * don_gia)
~~~

Muốn tính `thanh_tien` từ `so_luong` và `don_gia`, có thể dùng cột generated phù hợp, tính trong truy vấn hoặc logic nghiệp vụ có kiểm soát.

### 5.5. Hằng mặc định và biểu thức mặc định khác nhau

~~~sql
CREATE TABLE nhat_ky_su_kien (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    loai_su_kien TEXT NOT NULL DEFAULT 'TAO',
    thoi_diem TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

- `'TAO'` là **hằng**: mỗi lần dùng mặc định đều có giá trị như nhau.
- `CURRENT_TIMESTAMP` là **biểu thức thời gian**: giá trị được tính theo quy tắc thời gian của DBMS khi câu lệnh sử dụng mặc định.

Trong PostgreSQL, `CURRENT_TIMESTAMP` có giá trị thời điểm bắt đầu **giao dịch hiện tại**; nhiều hàng được thêm trong cùng giao dịch có thể nhận cùng một thời điểm. Nếu cần thời điểm đồng hồ thực tại mỗi lần gọi, PostgreSQL cung cấp `clock_timestamp()`, nhưng cần cân nhắc ý nghĩa nghiệp vụ, mức chính xác và đồng bộ thời gian giữa DB với ứng dụng.

**Không dùng mặc định thời gian để thay thế mọi thời điểm nghiệp vụ**: `ngay_dat_hang`, `ngay_giao_du_kien`, `ngay_tao` có ý nghĩa khác nhau. Mặc định `CURRENT_TIMESTAMP` thường phù hợp cho thời điểm tạo bản ghi tại DB; thời điểm do khách chọn phải được truyền rõ hoặc tính theo quy tắc riêng.

## 6. DEFAULT và IDENTITY / AUTO_INCREMENT / SEQUENCE

Một cột khóa chính có thể cần **giá trị tự sinh**. Mặc định dạng hằng `DEFAULT 1` không phù hợp với cột khóa chính, vì mọi hàng bỏ qua cột sẽ cố dùng cùng một ID và gây xung đột. DBMS cung cấp cơ chế cấp giá trị khác nhau.

### 6.1. PostgreSQL: GENERATED AS IDENTITY

~~~sql
CREATE TABLE phieu_nhap (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ghi_chu TEXT
);

INSERT INTO phieu_nhap (ghi_chu)
VALUES ('Nhap dot 1')
RETURNING id;
~~~

`GENERATED ALWAYS AS IDENTITY` yêu cầu PostgreSQL cấp giá trị theo cơ chế identity khi không được chỉ dẫn đặc biệt; chèn trực tiếp ID thông thường bị từ chối. Với `GENERATED BY DEFAULT AS IDENTITY`, hệ quản trị tự cấp nếu cột bị bỏ qua nhưng cho phép câu lệnh cung cấp ID tường minh. Chọn chế độ theo chính sách quản lý khóa.

Các bộ cấp số/sequence có thể **bỏ số** khi giao dịch rollback, có cache, bị thay đổi hoặc có nhiều phiên chạy đồng thời. Vì vậy **ID tự tăng không bảo đảm không có khoảng trống hay đúng thứ tự commit**. Số ID thường là định danh kỹ thuật, không nên coi là số hóa đơn liên tục có yêu cầu pháp lý.

### 6.2. UUID dùng hàm mặc định

~~~sql
CREATE TABLE tai_lieu (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ten TEXT NOT NULL
);

INSERT INTO tai_lieu (ten)
VALUES ('Tai lieu A')
RETURNING id;
~~~

Trong PostgreSQL hiện đại, `gen_random_uuid()` sinh UUID ngẫu nhiên, thường thuộc UUIDv4. Với các phiên bản PostgreSQL cũ hơn, việc sử dụng hàm có thể cần extension hoặc cơ chế khác. `DEFAULT gen_random_uuid()` là **biểu thức mặc định sinh khóa**, khác cú pháp `GENERATED ... AS IDENTITY` vốn dùng cho khóa số nguyên. Cả hai nên được kết hợp với `PRIMARY KEY` hoặc `UNIQUE` để database bảo vệ tính duy nhất.

## 7. Thiết kế thực tế: khai báo cột cho đơn hàng

Một mô hình bán hàng cần tối thiểu khách hàng, sản phẩm và đơn hàng. Ví dụ sau tập trung vào **kiểu, tính bắt buộc và mặc định**, đồng thời bổ sung vài ràng buộc cơ bản:

~~~sql
CREATE TABLE khach_hang_demo (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ho_ten VARCHAR(150) NOT NULL,
    email VARCHAR(255),
    ngay_dang_ky DATE NOT NULL DEFAULT CURRENT_DATE
);

CREATE TABLE san_pham_demo (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ten VARCHAR(150) NOT NULL,
    gia NUMERIC(12, 2) NOT NULL CHECK (gia >= 0),
    ton_kho INTEGER NOT NULL DEFAULT 0 CHECK (ton_kho >= 0),
    dang_ban BOOLEAN NOT NULL DEFAULT TRUE,
    ngay_tao TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE don_hang_demo (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    khach_hang_id BIGINT NOT NULL REFERENCES khach_hang_demo(id),
    thoi_diem_dat TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    trang_thai VARCHAR(20) NOT NULL DEFAULT 'MOI',
    ghi_chu TEXT,
    CONSTRAINT ck_don_hang_trang_thai
        CHECK (trang_thai IN ('MOI', 'DA_XAC_NHAN', 'DA_HUY'))
);
~~~

Các cột `id` được cấp số riêng theo từng bảng; `khach_hang_id` là khóa ngoại, phải lấy từ một khách hàng tồn tại. `trang_thai` mặc định `'MOI'`, nhưng `CHECK` tiếp tục ngăn các giá trị không thuộc tập cho phép kể cả khi ứng dụng truyền tường minh.

### 7.1. Chèn dữ liệu có sử dụng mặc định

~~~sql
INSERT INTO khach_hang_demo (ho_ten, email)
VALUES ('Nguyen Van An', 'an@example.com')
RETURNING id, ngay_dang_ky;

INSERT INTO san_pham_demo (ten, gia)
VALUES ('Ban phim co', 750000.00)
RETURNING id, ton_kho, dang_ban, ngay_tao;
~~~

Ở lệnh thứ hai, do không cung cấp `ton_kho`, `dang_ban` và `ngay_tao`, PostgreSQL lần lượt dùng `0`, `TRUE` và thời điểm hiện tại theo quy tắc `CURRENT_TIMESTAMP`.

Tạo đơn hàng tham chiếu khách hàng đã thêm:

~~~sql
-- Minh họa khi đã biết khach_hang_demo.id = 1.
-- Trong ứng dụng thật, lấy ID thực tế từ RETURNING.
INSERT INTO don_hang_demo (khach_hang_id, ghi_chu)
VALUES (1, 'Giao gio hanh chinh')
RETURNING id, thoi_diem_dat, trang_thai;
~~~

Nếu ID `1` không tồn tại trong bảng khách hàng, khóa ngoại sẽ từ chối câu lệnh. **Giá trị mặc định không thể tạo một khách hàng hợp lệ thay cho khóa ngoại bị thiếu**. Nên lấy ID thực tế từ `RETURNING` hoặc từ dữ liệu ứng dụng đã xác minh.

### 7.2. Nhập sai vẫn bị ràng buộc từ chối

~~~sql
-- Trạng thái không thuộc tập cho phép -> vi phạm CHECK:
-- INSERT INTO don_hang_demo (khach_hang_id, trang_thai)
-- VALUES (1, 'KHONG_XAC_DINH');

-- Bỏ qua gia -> NULL hiệu lực nhưng cột NOT NULL -> lỗi:
-- INSERT INTO san_pham_demo (ten)
-- VALUES ('San pham thieu gia');

-- Gửi ton_kho = -1 -> vi phạm CHECK:
-- INSERT INTO san_pham_demo (ten, gia, ton_kho)
-- VALUES ('San pham loi', 10000, -1);

-- Gửi ton_kho = NULL -> vi phạm NOT NULL dù cột DEFAULT 0:
-- INSERT INTO san_pham_demo (ten, gia, ton_kho)
-- VALUES ('San pham loi', 10000, NULL);
~~~

Điểm quan trọng: **`DEFAULT` giúp ứng dụng bỏ qua giá trị hợp lý; ràng buộc quyết định dữ liệu được phép tồn tại**. Không nên trộn lẫn hai trách nhiệm.

### 7.3. Dùng mặc định cho cột không có nghĩa “giá trị luôn đúng”

`ton_kho DEFAULT 0` hợp lý nếu sản phẩm mới chưa có hàng. Nhưng `gia DEFAULT 0` có thể là lựa chọn xấu nếu thiếu giá cần được báo lỗi. Khi đặt mặc định, nên hỏi:

1. Giá trị đó có phải **trạng thái ban đầu hợp lệ trong nghiệp vụ** không?
2. Việc ứng dụng quên truyền giá trị có nên được xử lý tự động, hay nên báo lỗi để tránh dữ liệu sai?
3. Có cần phân biệt **chưa biết**, **chưa nhập** và **giá trị thật là 0/false** không?
4. Giá trị mặc định cần cố định theo schema hay có thể thay đổi theo cấu hình, thời gian hoặc ngữ cảnh nghiệp vụ?

Ví dụ `so_luong DEFAULT 1` có thể hợp lý khi một đơn thường đặt một sản phẩm, nhưng có thể che lỗi nếu API đáng lẽ bắt buộc người dùng chọn số lượng. Dùng `DEFAULT` là quyết định thiết kế dữ liệu, không phải cách làm cho mọi câu `INSERT` đều thành công.

## 8. DEFAULT khác cột sinh, trigger và giá trị từ ứng dụng

Ba kỹ thuật thường dễ bị nhầm:

| Kỹ thuật | Khi nào tạo/cập nhật? | Thích hợp cho |
| --- | --- | --- |
| **DEFAULT** | Khi một thao tác ghi yêu cầu dùng mặc định, thường lúc `INSERT` bỏ qua cột | Trạng thái bắt đầu, số lượng mặc định, thời điểm tạo |
| **Generated/computed column** | DB tính theo biểu thức dựa trên cột khác theo quy tắc DBMS | Tổng tiền theo dòng, thông tin dẫn xuất |
| **Trigger** | DB thực hiện logic tự động theo sự kiện `INSERT`/`UPDATE`/`DELETE` phù hợp | Audit hoặc quy tắc đặc thù cần logic ngoài DEFAULT |
| **Giá trị do ứng dụng truyền** | Ứng dụng quyết định trước khi ghi | Giá trị thuộc hành động người dùng hay quy tắc dịch vụ |

### 8.1. Cột được tính từ cột khác

Ví dụ PostgreSQL với **generated stored column**:

~~~sql
CREATE TABLE chi_tiet_don_hang_demo (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    so_luong INTEGER NOT NULL CHECK (so_luong > 0),
    don_gia NUMERIC(12, 2) NOT NULL CHECK (don_gia >= 0),
    thanh_tien NUMERIC(14, 2)
        GENERATED ALWAYS AS (so_luong * don_gia) STORED
);

INSERT INTO chi_tiet_don_hang_demo (so_luong, don_gia)
VALUES (2, 125000.00);

SELECT so_luong, don_gia, thanh_tien
FROM chi_tiet_don_hang_demo;
~~~

Kết quả `thanh_tien` được tính thành `250000.00` từ các cột cùng hàng. Trong PostgreSQL, biểu thức generated column phải thỏa các giới hạn về tính bất biến và tham chiếu; nó không được dùng tùy ý mọi hàm hoặc tham chiếu tới các hàng khác.

Sự khác biệt cơ bản:

- `DEFAULT 0` cho `thanh_tien` chỉ điền `0` khi cột bị bỏ qua; nó **không tính lại** sau khi `so_luong` hoặc `don_gia` đổi.
- `GENERATED ALWAYS AS (so_luong * don_gia) STORED` buộc DB tính giá trị theo biểu thức khi dữ liệu nguồn được ghi/sửa.
- Nếu cần mức giá có chiết khấu, thuế, quy tắc làm tròn hoặc lịch sử giá phức tạp, chỉ một biểu thức nhân có thể chưa đáp ứng yêu cầu nghiệp vụ.

### 8.2. Cột created_at và updated_at

Thiết kế thường gặp:

~~~sql
CREATE TABLE ghi_chu_demo (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    noi_dung TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Cả hai cột sẽ có mặc định lúc thêm hàng. Nhưng khi chạy:

~~~sql
UPDATE ghi_chu_demo
SET noi_dung = 'Noi dung moi'
WHERE id = 1;
~~~

`updated_at` **không tự động đổi chỉ vì có `DEFAULT CURRENT_TIMESTAMP`**. Trong PostgreSQL, muốn cập nhật thời gian sửa có thể đặt rõ `updated_at = CURRENT_TIMESTAMP` trong lệnh `UPDATE`, dùng trigger, hoặc để ORM/ứng dụng quản lý. MySQL có cú pháp `ON UPDATE CURRENT_TIMESTAMP` cho những kiểu cột hỗ trợ; cú pháp đó không tự áp dụng cho PostgreSQL.

## 9. Thay đổi cột và mặc định sau khi tạo bảng

Lược đồ thay đổi khi nghiệp vụ phát triển. SQL hỗ trợ `ALTER TABLE`, nhưng cần nhớ rằng **thay đổi mặc định cho thao tác tương lai không nhất thiết thay đổi dữ liệu đã có**.

### 9.1. Thêm cột với mặc định

~~~sql
ALTER TABLE san_pham_demo
ADD COLUMN can_kiem_duyet BOOLEAN NOT NULL DEFAULT FALSE;
~~~

Trong PostgreSQL, lệnh này thêm cột bắt buộc, mặc định `FALSE`. Những hàng hiện có sẽ nhìn thấy giá trị mặc định phù hợp với ngữ nghĩa thao tác thêm cột; PostgreSQL hiện đại có tối ưu hóa đối với nhiều mặc định hằng. Chi phí thay đổi vẫn phụ thuộc biểu thức mặc định, phiên bản và kích thước bảng.

Khi thêm cột `NOT NULL` **mà không có mặc định** vào bảng đang có hàng, hệ quản trị thường không thể tạo một giá trị hợp lệ cho các hàng cũ. Một cách triển khai có kiểm soát là:

~~~sql
-- Giai đoạn 1: thêm cột cho phép NULL.
ALTER TABLE san_pham_demo
ADD COLUMN ma_noi_bo VARCHAR(50);

-- Giai đoạn 2: điền dữ liệu thực tế hợp lệ cho mọi hàng cũ.
-- Phần này phụ thuộc quy tắc nghiệp vụ và dữ liệu hiện có.

-- Giai đoạn 3: sau khi bảo đảm không còn NULL:
-- ALTER TABLE san_pham_demo
-- ALTER COLUMN ma_noi_bo SET NOT NULL;
~~~

Không tự điền một chuỗi giả như `'unknown'` vào mọi hàng nếu cột mã nội bộ phải là duy nhất hoặc có giá trị nghiệp vụ thực sự. Phải chọn cách backfill phù hợp với dữ liệu nguồn.

### 9.2. Đổi mặc định cho lần chèn sau

~~~sql
ALTER TABLE san_pham_demo
ALTER COLUMN dang_ban SET DEFAULT FALSE;
~~~

Sau câu này, một sản phẩm **mới** bị bỏ qua `dang_ban` sẽ mặc định `FALSE`. Các sản phẩm đã lưu `TRUE` vẫn có giá trị `TRUE`: việc đổi `DEFAULT` không chạy `UPDATE` trên tất cả bản ghi cũ.

Muốn thay đổi các hàng cũ, cần lệnh DML riêng và điều kiện rõ ràng:

~~~sql
-- Chỉ minh họa: việc cập nhật toàn bộ cần có chủ đích nghiệp vụ.
-- UPDATE san_pham_demo SET dang_ban = FALSE;
~~~

Gỡ mặc định:

~~~sql
ALTER TABLE san_pham_demo
ALTER COLUMN dang_ban DROP DEFAULT;
~~~

Lúc này `dang_ban` vẫn `NOT NULL`; nếu `INSERT` bỏ qua cột và không còn cơ chế sinh giá trị nào khác thì sẽ bị từ chối, vì mặc định hiệu lực là `NULL` nhưng ràng buộc không cho phép `NULL`.

### 9.3. Thay kiểu dữ liệu

~~~sql
-- Ví dụ đổi cột ten từ VARCHAR(150) sang VARCHAR(250).
ALTER TABLE san_pham_demo
ALTER COLUMN ten TYPE VARCHAR(250);
~~~

Mở rộng giới hạn chuỗi thường đơn giản hơn việc thu hẹp. Với phép chuyển không tương thích, PostgreSQL có thể cần mệnh đề `USING`, ví dụ chuyển một cột chuỗi hợp lệ thành số. Trước khi thay kiểu, cần kiểm tra dữ liệu hiện có, index, constraint, view, ứng dụng đọc/ghi và nguy cơ khóa bảng hoặc viết lại dữ liệu. Cú pháp `ALTER COLUMN TYPE` không giống nhau giữa các DBMS.

### 9.4. Kiểm tra metadata lược đồ

Trong PostgreSQL, có thể đọc thông tin cột qua `information_schema.columns`:

~~~sql
SELECT
    column_name,
    data_type,
    character_maximum_length,
    numeric_precision,
    numeric_scale,
    is_nullable,
    column_default,
    is_identity
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'san_pham_demo'
ORDER BY ordinal_position;
~~~

Truy vấn này giúp kiểm tra định nghĩa cột từ metadata thay vì đoán bằng dữ liệu mẫu. Một số thuộc tính có thể được biểu diễn theo cách riêng của hệ quản trị; với PostgreSQL, cấu hình đầy đủ của identity, generated column hoặc các tùy chọn riêng có thể cần xem thêm catalog chuyên dụng/`\d` trong `psql`.

## 10. Khác biệt giữa PostgreSQL, MySQL, SQL Server và Oracle

Các ý tưởng **kiểu dữ liệu, `NULL`, ràng buộc và mặc định** có mặt ở nhiều DBMS, nhưng cú pháp chi tiết không hoàn toàn tương đương.

| Nhu cầu | PostgreSQL | MySQL | SQL Server | Oracle |
| --- | --- | --- | --- | --- |
| Chuỗi Unicode thông dụng | `VARCHAR(n)`, `TEXT` với encoding phù hợp | `VARCHAR(n)` với character set phù hợp, thường `utf8mb4` | `NVARCHAR(n)`; các kiểu `VARCHAR` với collation UTF-8 phụ thuộc cấu hình/phiên bản | `VARCHAR2(n)` với thiết lập ký tự phù hợp, hoặc `NVARCHAR2` |
| Số thập phân chính xác | `NUMERIC(p,s)` | `DECIMAL(p,s)` | `DECIMAL(p,s)` | `NUMBER(p,s)` |
| Thời điểm có ngữ nghĩa múi giờ | `TIMESTAMPTZ` | `TIMESTAMP` có cơ chế chuyển đổi timezone riêng | `DATETIMEOFFSET` khi cần kèm offset; `DATETIME2` cho local datetime | `TIMESTAMP WITH TIME ZONE` |
| ID số tự sinh | `GENERATED ... AS IDENTITY` | `AUTO_INCREMENT` | `IDENTITY(seed, increment)` | `GENERATED ... AS IDENTITY` |
| Mặc định thời điểm | `DEFAULT CURRENT_TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP` cho cột hỗ trợ | `DEFAULT SYSUTCDATETIME()` hoặc hàm thích hợp | `DEFAULT SYSTIMESTAMP` |
| Sửa mặc định | `ALTER COLUMN ... SET DEFAULT` | Có thể dùng `ALTER COLUMN ... SET DEFAULT` hoặc sửa định nghĩa cột, tùy phiên bản/tính năng | Thường thao tác trên **DEFAULT constraint** | `MODIFY (cot DEFAULT ...)` |

Ví dụ minh họa tối giản ở mỗi hệ:

**PostgreSQL**

~~~sql
CREATE TABLE phieu_pg (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trang_thai TEXT NOT NULL DEFAULT 'MOI',
    ngay_tao TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

**MySQL 8.0**

~~~sql
CREATE TABLE phieu_mysql (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    trang_thai VARCHAR(20) NOT NULL DEFAULT 'MOI',
    ngay_tao TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

**SQL Server**

~~~sql
CREATE TABLE dbo.phieu_sqlserver (
    id BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
    trang_thai NVARCHAR(20) NOT NULL
        CONSTRAINT df_phieu_trang_thai DEFAULT N'MOI',
    ngay_tao DATETIME2(3) NOT NULL
        CONSTRAINT df_phieu_ngay_tao DEFAULT SYSUTCDATETIME()
);
~~~

**Oracle Database**

~~~sql
CREATE TABLE phieu_oracle (
    id NUMBER(19) GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trang_thai VARCHAR2(20) DEFAULT 'MOI' NOT NULL,
    ngay_tao TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL
);
~~~

Chúng cùng hướng đến ba cột: mã tự sinh, trạng thái mặc định và thời điểm tạo; nhưng **không có nghĩa hành vi thời gian, kiểu chuỗi và cơ chế cấp số là giống hệt nhau**. Khi thiết kế cho ứng dụng đa nền tảng, hãy kiểm tra bằng migration và kết nối đến phiên bản DBMS thật.

### 10.1. Một số khác biệt dễ gây lỗi

- **SQL Server:** `DEFAULT` thường được quản lý dưới dạng constraint; thay đổi mặc định có thể cần tìm và xóa constraint đang gắn với cột rồi tạo constraint mới. `IDENTITY` khác cú pháp PostgreSQL.
- **MySQL:** các chế độ SQL như strict mode ảnh hưởng đến cách xử lý giá trị thiếu/sai; một số mặc định theo biểu thức chỉ được hỗ trợ ở phiên bản cụ thể. Cột `TIMESTAMP` và `DATETIME` có hành vi khác nhau về múi giờ.
- **Oracle:** chuỗi ký tự rỗng có thể được coi như `NULL`; nhiều kiểu dữ liệu và mặc định khác PostgreSQL. Kiểu `NUMBER` có cách khai báo và xử lý precision/scale riêng.
- **PostgreSQL:** `TIMESTAMPTZ` và `TIMESTAMP` khác ý nghĩa; `DEFAULT CURRENT_TIMESTAMP` không tự cập nhật cột khi `UPDATE`; `IDENTITY` là cơ chế khác với `DEFAULT nextval(...)` của kiểu `SERIAL` cũ.

## 11. Những lỗi phổ biến khi khai báo cột

| Cách làm dễ lỗi | Vì sao có vấn đề | Cách tiếp cận phù hợp |
| --- | --- | --- |
| Dùng `VARCHAR` cho giá tiền | Phép toán/sắp xếp có thể trở thành thao tác chuỗi hoặc phải ép kiểu | `NUMERIC/DECIMAL` với precision/scale phù hợp |
| Dùng `DOUBLE PRECISION` cho mọi phép tính tiền | Số thực nhị phân có sai số biểu diễn | Chọn số thập phân chính xác và quy tắc làm tròn |
| Lưu số điện thoại, mã bưu chính bằng `INTEGER` | Mất số 0 đầu, không giữ dấu `+` | Dùng kiểu chuỗi và kiểm tra định dạng |
| Mọi cột đều có `DEFAULT ''` hoặc `DEFAULT 0` | Che giấu dữ liệu chưa có và làm sai ngữ nghĩa | Chỉ đặt mặc định khi giá trị thực sự hợp lý |
| `DEFAULT` mà không có `NOT NULL` | Ứng dụng vẫn có thể truyền `NULL` ở nhiều DBMS | Dùng `NOT NULL` nếu cột bắt buộc |
| Cho rằng `DEFAULT NOW()` cập nhật khi sửa hàng | Giá trị mặc định không tự chạy lại mỗi lần UPDATE | Dùng logic cập nhật hoặc trigger phù hợp |
| Đặt `DEFAULT` tính từ cột khác | Nhiều DBMS không cho biểu thức mặc định tham chiếu cột cùng hàng | Dùng generated column hoặc tính lúc ghi |
| Thay `DEFAULT` rồi kỳ vọng dữ liệu cũ đổi | `SET DEFAULT` thường tác động các lần ghi sau | Backfill bằng DML có điều kiện nếu cần |
| Thu hẹp kiểu/cột trên bảng lớn mà không khảo sát | Giá trị có thể bị từ chối, khóa/viết lại bảng, ảnh hưởng dịch vụ | Kiểm tra dữ liệu và lên migration có kiểm soát |
| Xem `NOT NULL` là đủ kiểm tra chuỗi hợp lệ | Chuỗi rỗng hoặc khoảng trắng vẫn có thể hợp lệ | Thêm `CHECK` hoặc validation nghiệp vụ |
| Bỏ qua sự khác biệt dialect | Cùng tên kiểu hoặc từ khóa nhưng có hành vi khác | Xác minh phiên bản và cấu hình DBMS thật |

## 12. Bài tập thực hành

### Bài 1: Thiết kế bảng nhân viên

Yêu cầu bảng `nhan_vien`: ID tự sinh, họ tên bắt buộc, lương không âm với hai chữ số thập phân, đang làm việc mặc định `TRUE`, ngày vào làm mặc định ngày hiện hành, ghi chú tùy chọn.

**Một lời giải PostgreSQL:**

~~~sql
CREATE TABLE nhan_vien (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ho_ten VARCHAR(150) NOT NULL,
    luong NUMERIC(14, 2) NOT NULL CHECK (luong >= 0),
    dang_lam_viec BOOLEAN NOT NULL DEFAULT TRUE,
    ngay_vao_lam DATE NOT NULL DEFAULT CURRENT_DATE,
    ghi_chu TEXT
);
~~~

Để tạo nhân viên mới, ứng dụng cần truyền tối thiểu `ho_ten` và `luong`, còn có thể bỏ qua ID, trạng thái và ngày vào làm nếu phù hợp nghiệp vụ.

### Bài 2: Đoán kết quả của DEFAULT

Cho:

~~~sql
CREATE TABLE vi_du_default (
    id INTEGER PRIMARY KEY,
    so_luong INTEGER NOT NULL DEFAULT 5,
    ghi_chu TEXT
);

INSERT INTO vi_du_default (id) VALUES (1);
INSERT INTO vi_du_default (id, so_luong) VALUES (2, 8);
-- INSERT INTO vi_du_default (id, so_luong) VALUES (3, NULL);
~~~

**Đáp án:** Hàng `id = 1` nhận `so_luong = 5`, `ghi_chu = NULL`; hàng `id = 2` nhận `so_luong = 8`; câu chèn hàng `id = 3` (đang chú thích) sẽ bị từ chối vì `NOT NULL`, mặc dù cột có `DEFAULT 5`.

### Bài 3: Thay đổi mặc định

Một bảng đang có nhiều hàng với `trang_thai = 'MOI'`. Quản trị viên chạy:

~~~sql
ALTER TABLE don_hang_mau
ALTER COLUMN trang_thai SET DEFAULT 'CHO_XAC_NHAN';
~~~

Những hàng cũ có tự chuyển sang `CHO_XAC_NHAN` không?

**Đáp án:** Không. Mặc định mới áp dụng khi thao tác ghi sau đó yêu cầu dùng mặc định; giá trị đã lưu không tự thay đổi. Cần DML riêng nếu muốn chuyển các hàng cũ, đồng thời phải xét ràng buộc `CHECK` nếu bảng có danh sách trạng thái cho phép.

### Bài 4: Thời điểm tạo và cập nhật

Khách muốn cột `ngay_sua` tự đổi khi một hàng được cập nhật. Khai báo `ngay_sua TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP` đã đủ chưa?

**Đáp án:** Chưa trong PostgreSQL. `DEFAULT` thường điền giá trị khi `INSERT` bỏ qua cột, không tự chạy mỗi lần `UPDATE`. Cần ứng dụng cập nhật cột, dùng trigger hoặc cơ chế DBMS tương ứng.

### Bài 5: Bản ghi có giá tính từ số lượng

Đề nghị thiết kế `thanh_tien` sao cho luôn bằng `so_luong * don_gia` trong PostgreSQL. Dùng `DEFAULT 0` có đạt không?

**Đáp án:** Không. Có thể dùng một **generated column**:

~~~sql
CREATE TABLE dong_hang_bai_tap (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    so_luong INTEGER NOT NULL CHECK (so_luong > 0),
    don_gia NUMERIC(12, 2) NOT NULL CHECK (don_gia >= 0),
    thanh_tien NUMERIC(14, 2)
        GENERATED ALWAYS AS (so_luong * don_gia) STORED
);
~~~

Ở đây DB tính giá trị `thanh_tien` từ hai cột nguồn theo cơ chế generated column; `DEFAULT 0` chỉ điền một hằng ban đầu, không bảo đảm công thức sau khi dữ liệu thay đổi.

### Bài 6: Chọn kiểu cho từng thuộc tính

Chọn kiểu hợp lý trong PostgreSQL cho các cột: `ma_buu_chinh` (có số 0 đầu), `so_tien` (cần chính xác hai chữ số thập phân theo nghiệp vụ), `thoi_diem_gui` (một thời điểm trên trục thời gian), `da_xu_ly` (đúng/sai), `tai_lieu` (byte PDF).

**Đáp án gợi ý:** `VARCHAR` cho mã bưu chính, `NUMERIC(p,2)` cho số tiền, `TIMESTAMPTZ` cho thời điểm, `BOOLEAN` cho trạng thái và `BYTEA` cho nội dung PDF. Cần bổ sung `NOT NULL`, `DEFAULT`, `CHECK` tùy từng quy tắc nghiệp vụ.

## 13. Ghi nhớ cách đọc và thiết kế một khai báo cột

Khi gặp câu lệnh:

~~~sql
so_luong INTEGER NOT NULL DEFAULT 1 CHECK (so_luong > 0)
~~~

hãy đọc theo bốn lớp nghĩa: **tên cột** là `so_luong`; **kiểu dữ liệu** là số nguyên `INTEGER`; **giá trị bắt buộc** vì `NOT NULL`; nếu chèn mà **bỏ qua cột** thì lấy mặc định `1`, và mọi giá trị được lưu phải **lớn hơn 0** do `CHECK`. Đây là những cơ chế khác nhau cùng bảo vệ một thuộc tính.

Việc khai báo cột tốt bắt đầu từ ý nghĩa dữ liệu: số hay mã; thời điểm hay ngày lịch; có thể chưa biết hay bắt buộc; giá trị mặc định có thật sự hợp lệ không; giá trị cần được sinh một lần hay tính lại theo cột khác. Từ những quyết định đó, lựa chọn `CREATE TABLE`, kiểu dữ liệu, `NOT NULL`, `DEFAULT`, các ràng buộc và migration sẽ trở nên có căn cứ và nhất quán.

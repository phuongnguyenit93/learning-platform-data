# Loại bản sao bằng DISTINCT và xác định mức chi tiết của kết quả

Khi truy vấn dữ liệu quan hệ, số dòng trả về không chỉ phụ thuộc vào số dòng đang lưu trong bảng. Nó còn phụ thuộc vào **cột được chọn**, **quan hệ giữa các bảng khi JOIN**, **điều kiện lọc**, **cách nhóm** và **quy tắc loại dòng trùng**. Hai truy vấn cùng đọc một bảng có thể trả về số dòng khác nhau mà cả hai đều đúng.

`DISTINCT` giúp loại bỏ những **dòng kết quả trùng nhau theo tập biểu thức trong SELECT**. Tuy nhiên, muốn sử dụng đúng cần xác định **mức chi tiết của kết quả** (*result grain* hoặc *granularity*): **mỗi dòng kết quả đại diện cho một đối tượng hay một tổ hợp nào?** Một khách hàng, một đơn hàng, một dòng chi tiết đơn hàng, hay một cặp khách hàng–trạng thái?

Đây là bài học trong chủ đề *Truy vấn cơ bản* của SQL. Ví dụ sử dụng cú pháp **PostgreSQL** để thực hành; những phần mang tính chuẩn SQL như `SELECT DISTINCT`, `GROUP BY`, `JOIN` được giải thích riêng với các mở rộng đặc thù PostgreSQL như `DISTINCT ON`.

## 1. Bản sao của dòng kết quả là gì?

Giả sử có bảng khách hàng:

| id | ten_khach_hang | thanh_pho |
| --- | --- | --- |
| 1 | An | Hà Nội |
| 2 | Bình | Hà Nội |
| 3 | Chi | Đà Nẵng |
| 4 | Dung | `NULL` |
| 5 | Em | `NULL` |

Nếu truy vấn cả mã khách hàng và thành phố:

~~~sql
SELECT id, thanh_pho
FROM khach_hang;
~~~

thì mỗi hàng vẫn khác nhau ở `id`, kể cả khi nhiều người sống cùng thành phố. Nhưng nếu chỉ chọn thành phố:

~~~sql
SELECT thanh_pho
FROM khach_hang;
~~~

kết quả có thể gồm `Hà Nội`, `Hà Nội`, `Đà Nẵng`, `NULL`, `NULL`. **Hai lần xuất hiện `Hà Nội` là trùng nhau trong tập kết quả một cột**, nhưng hai khách hàng An và Bình vẫn là hai thực thể khác nhau trong bảng gốc.

Khái niệm “trùng” vì vậy mang tính **tương đối với dữ liệu mà truy vấn đang hiển thị**:

- Nếu chọn `id`, các khách hàng có mã khác nhau không phải dòng trùng.
- Nếu chọn `thanh_pho`, những khách hàng cùng thành phố tạo ra giá trị trùng.
- Nếu chọn `thanh_pho, ten_khach_hang`, từng **cặp** mới là đơn vị được so sánh.

`DISTINCT` không tự tìm “bản ghi trùng về nghiệp vụ” trong bảng và không xóa dữ liệu. Nó chỉ điều chỉnh tập dòng **được trả về từ câu SELECT**.

## 2. Cú pháp SELECT DISTINCT

Cú pháp tổng quát:

~~~sql
SELECT DISTINCT bieu_thuc_1, bieu_thuc_2, ...
FROM ten_bang
WHERE dieu_kien;
~~~

`DISTINCT` áp dụng cho **toàn bộ danh sách biểu thức SELECT**, không chỉ biểu thức đầu tiên. Hai dòng chỉ bị xem là trùng trong kết quả nếu tất cả các giá trị tương ứng đều không phân biệt được nhau theo quy tắc loại trùng của hệ quản trị.

Ví dụ:

~~~sql
SELECT DISTINCT thanh_pho
FROM khach_hang;
~~~

Trên dữ liệu minh họa, có ba giá trị thành phố khác biệt: `Hà Nội`, `Đà Nẵng` và `NULL`. `DISTINCT` giữ một lần xuất hiện cho mỗi giá trị khác biệt.

Thêm cột `ten_khach_hang`:

~~~sql
SELECT DISTINCT thanh_pho, ten_khach_hang
FROM khach_hang;
~~~

Vì tên của năm khách hàng khác nhau, cả năm cặp `(thanh_pho, ten_khach_hang)` vẫn khác nhau. Truy vấn trên **không phải cách lấy một khách hàng đại diện cho mỗi thành phố**.

### 2.1. SELECT mặc định là ALL

Trong SQL thông thường, nếu không viết `DISTINCT` thì kết quả giữ các dòng trùng khi chúng xuất hiện. Có thể diễn đạt tường minh:

~~~sql
SELECT ALL thanh_pho FROM khach_hang;
~~~

và:

~~~sql
SELECT thanh_pho FROM khach_hang;
~~~

với ngữ nghĩa như nhau. Mô hình kết quả của một truy vấn SQL thường là một **multiset** hoặc *bag*: cùng một dòng giá trị có thể xuất hiện nhiều lần, khác với tập hợp toán học chỉ chứa mỗi phần tử một lần.

### 2.2. DISTINCT không sắp xếp kết quả

~~~sql
SELECT DISTINCT thanh_pho
FROM khach_hang;
~~~

không bảo đảm `Hà Nội` luôn xuất hiện trước `Đà Nẵng`, dù hệ quản trị đôi khi triển khai `DISTINCT` bằng thao tác sắp xếp. Muốn thứ tự ổn định phải dùng `ORDER BY`:

~~~sql
SELECT DISTINCT thanh_pho
FROM khach_hang
ORDER BY thanh_pho;
~~~

Vị trí `NULL` khi sắp xếp và quy tắc so sánh chữ phụ thuộc DBMS, collation và các tùy chọn `NULLS FIRST`/`NULLS LAST` nếu được hỗ trợ.

### 2.3. DISTINCT không thay đổi dữ liệu gốc

~~~sql
SELECT DISTINCT thanh_pho
FROM khach_hang;
~~~

chỉ loại trùng khi **đọc**. Bảng `khach_hang` vẫn có đầy đủ các khách hàng An, Bình, Chi, Dung, Em. Để ngăn trùng khi **ghi** theo một quy tắc nghiệp vụ, dùng ràng buộc `UNIQUE`/khóa phù hợp; để xóa dữ liệu thực sự cần các thao tác DML có chủ đích. Không nhầm `SELECT DISTINCT` với `DELETE`, `DROP` hay `UNIQUE`.

## 3. Thực hành với bộ dữ liệu nhất quán

Những ví dụ tiếp theo dùng ba bảng nhỏ. Có thể chạy toàn bộ phần tạo dữ liệu trong một phiên **PostgreSQL mới**. `TEMP TABLE` chỉ tồn tại trong phiên kết nối tương ứng và không phải bảng lưu lâu dài.

~~~sql
CREATE TEMP TABLE khach_hang (
    id INTEGER PRIMARY KEY,
    ten_khach_hang TEXT NOT NULL,
    thanh_pho TEXT
);

INSERT INTO khach_hang (id, ten_khach_hang, thanh_pho)
VALUES
    (1, 'An',   'Hà Nội'),
    (2, 'Bình', 'Hà Nội'),
    (3, 'Chi',  'Đà Nẵng'),
    (4, 'Dung', NULL),
    (5, 'Em',   NULL);

CREATE TEMP TABLE don_hang (
    id INTEGER PRIMARY KEY,
    khach_hang_id INTEGER NOT NULL REFERENCES khach_hang(id),
    thoi_diem_dat TIMESTAMPTZ NOT NULL,
    trang_thai TEXT NOT NULL,
    tong_tien NUMERIC(12, 2) NOT NULL
);

INSERT INTO don_hang
    (id, khach_hang_id, thoi_diem_dat, trang_thai, tong_tien)
VALUES
    (101, 1, '2026-01-02 09:00:00+07', 'DA_XAC_NHAN', 200000),
    (102, 1, '2026-01-05 10:00:00+07', 'DA_XAC_NHAN', 150000),
    (103, 2, '2026-01-03 14:00:00+07', 'MOI',         300000),
    (104, 3, '2026-01-04 16:00:00+07', 'DA_XAC_NHAN', 200000),
    (105, 3, '2026-01-06 08:00:00+07', 'MOI',         100000);

CREATE TEMP TABLE chi_tiet_don_hang (
    id INTEGER PRIMARY KEY,
    don_hang_id INTEGER NOT NULL REFERENCES don_hang(id),
    ma_san_pham TEXT NOT NULL,
    so_luong INTEGER NOT NULL
);

INSERT INTO chi_tiet_don_hang
    (id, don_hang_id, ma_san_pham, so_luong)
VALUES
    (1001, 101, 'SP_A', 1),
    (1002, 101, 'SP_B', 2),
    (1003, 102, 'SP_A', 1),
    (1004, 103, 'SP_C', 3),
    (1005, 104, 'SP_B', 1),
    (1006, 105, 'SP_C', 2);
~~~

Các bảng có số dòng và mức chi tiết khác nhau:

| Bảng | Số dòng | Mức chi tiết tự nhiên | Khóa xác định từng hàng |
| --- | ---: | --- | --- |
| `khach_hang` | 5 | Một khách hàng | `khach_hang.id` |
| `don_hang` | 5 | Một đơn hàng | `don_hang.id` |
| `chi_tiet_don_hang` | 6 | Một dòng sản phẩm trong đơn hàng | `chi_tiet_don_hang.id` |

Quan hệ giữa chúng:

~~~mermaid
flowchart LR
    K["khach_hang\n1 dòng / khách hàng"] -->|"1 khách: 0..n đơn"| D["don_hang\n1 dòng / đơn hàng"]
    D -->|"1 đơn: 0..n dòng hàng"| C["chi_tiet_don_hang\n1 dòng / dòng hàng"]
~~~

Khách hàng `1` có hai đơn (101, 102); khách hàng `3` có hai đơn (104, 105); khách hàng `4` và `5` chưa có đơn. Đơn `101` có hai dòng hàng. Những điều đó sẽ quyết định số dòng khi ghép bảng.

## 4. Mức chi tiết của kết quả (*grain*) là gì?

**Grain** trả lời câu hỏi: **“Một dòng của kết quả tương ứng với một đối tượng hoặc một tổ hợp định danh nào?”**

Ví dụ:

| Mong muốn | Grain | Cột định danh kết quả thường cần |
| --- | --- | --- |
| Danh sách khách hàng | Một dòng cho mỗi khách hàng | `khach_hang.id` |
| Danh sách đơn hàng | Một dòng cho mỗi đơn | `don_hang.id` |
| Danh sách sản phẩm từng đơn | Một dòng cho mỗi dòng chi tiết đơn | `chi_tiet_don_hang.id` |
| Các thành phố có khách | Một dòng cho mỗi giá trị thành phố | `thanh_pho` |
| Tổng tiền theo khách | Một dòng cho mỗi khách hàng | `khach_hang_id` |
| Số đơn theo khách và trạng thái | Một dòng cho mỗi cặp khách–trạng thái | `(khach_hang_id, trang_thai)` |

Grain phải được xác định **trước khi** chọn `DISTINCT`, `GROUP BY` hay `JOIN`. Nếu yêu cầu là “một dòng cho mỗi khách hàng”, một truy vấn trả về nhiều dòng vì khách có nhiều đơn cần được xét lại về **cách ghép hoặc tổng hợp**, không thể tự động coi mọi dòng trùng sau JOIN là dữ liệu hỏng.

### 4.1. Grain không đồng nghĩa số cột

Một dòng chứa 15 cột vẫn có thể đại diện cho **một khách hàng**. Ngược lại, một kết quả chỉ có 2 cột `khach_hang_id` và `ma_san_pham` có thể đại diện cho **mỗi cặp khách hàng–sản phẩm**, khiến một khách hàng xuất hiện ở nhiều dòng.

Người thiết kế cần nêu rõ **khóa logic của kết quả**. Ví dụ:

~~~sql
SELECT id, ten_khach_hang, thanh_pho
FROM khach_hang;
~~~

Một dòng ứng với một `id` khách hàng. Nhưng:

~~~sql
SELECT thanh_pho
FROM khach_hang;
~~~

không còn cột `id`; giờ truy vấn trả về **giá trị thành phố của mỗi dòng khách hàng**, cho phép các thành phố lặp. Chỉ khi thêm `DISTINCT` mới chuyển ý nghĩa thành **mỗi thành phố khác biệt một dòng**.

### 4.2. Kết quả có thể mất thông tin khi giảm grain

Từ danh sách năm khách hàng sang hai thành phố có giá trị và một `NULL`, ta đã **bỏ** thông tin về số khách hàng ở mỗi thành phố và danh tính của từng người. Việc giảm số dòng không phải lúc nào cũng sai; nó đúng khi mục tiêu là **danh mục thành phố xuất hiện**.

Nếu mục tiêu là “bao nhiêu khách ở mỗi thành phố”, chỉ dùng `DISTINCT` sẽ đánh mất thông tin đếm. Phải dùng `GROUP BY` với hàm tổng hợp `COUNT(*)`.

## 5. DISTINCT trên nhiều cột: đơn vị loại trùng là một bộ giá trị

Ví dụ thống kê các trạng thái đơn xuất hiện:

~~~sql
SELECT DISTINCT trang_thai
FROM don_hang
ORDER BY trang_thai;
~~~

Kết quả có hai dòng:

| trang_thai |
| --- |
| `DA_XAC_NHAN` |
| `MOI` |

Chọn thêm `khach_hang_id`:

~~~sql
SELECT DISTINCT khach_hang_id, trang_thai
FROM don_hang
ORDER BY khach_hang_id, trang_thai;
~~~

Kết quả có bốn cặp:

| khach_hang_id | trang_thai |
| ---: | --- |
| 1 | `DA_XAC_NHAN` |
| 2 | `MOI` |
| 3 | `DA_XAC_NHAN` |
| 3 | `MOI` |

Đơn 101 và 102 đều là `(1, 'DA_XAC_NHAN')`, nên chỉ còn **một** cặp. Nhưng khách hàng 3 có hai trạng thái, nên vẫn xuất hiện **hai dòng**. Điều này phù hợp nếu câu hỏi là “mỗi khách từng có những trạng thái đơn nào?”, không phù hợp nếu câu hỏi là “mỗi khách chỉ một dòng”.

Nếu thêm `id` của đơn hàng:

~~~sql
SELECT DISTINCT id, khach_hang_id, trang_thai
FROM don_hang;
~~~

cả năm đơn vẫn xuất hiện vì `id` đã duy nhất. **Thêm một cột duy nhất vào danh sách SELECT có thể khiến `DISTINCT` không loại được dòng nào**. Do đó, câu `SELECT DISTINCT *` thường không giải quyết một vấn đề đòi hỏi loại trùng theo **một phần các cột**.

### 5.1. DISTINCT hoạt động trên biểu thức, không chỉ tên cột

~~~sql
SELECT DISTINCT upper(trang_thai) AS trang_thai_chuan_hoa
FROM don_hang
ORDER BY trang_thai_chuan_hoa;
~~~

Ở đây phép so sánh trùng áp dụng trên **kết quả `upper(trang_thai)`**. Với văn bản có khác biệt hoa/thường hoặc biểu thức làm tròn/sắp nhóm, hai hàng dữ liệu gốc khác nhau có thể cho cùng biểu thức và bị gộp vào một kết quả.

Ví dụ làm tròn:

~~~sql
SELECT DISTINCT round(tong_tien / 100000.0) AS bac_gia
FROM don_hang
ORDER BY bac_gia;
~~~

Giá trị `tong_tien` có thể khác nhau nhưng `bac_gia` trùng. Trước khi dùng `DISTINCT` trên biểu thức, cần biết **đang muốn phân biệt giá trị gốc hay kết quả đã biến đổi**.

### 5.2. Collation và kiểu dữ liệu ảnh hưởng đến điều được coi là trùng

Với chuỗi ký tự, DBMS so sánh theo kiểu dữ liệu và collation đang áp dụng; một số collation coi `An` và `an` tương đương, một số phân biệt. Việc loại trùng `DISTINCT` có thể phản ánh những quy tắc đó. Không nên suy rằng mọi DBMS và mọi database đều xử lý chữ hoa, dấu hoặc khoảng trắng giống nhau.

Nếu nghiệp vụ muốn “mỗi email đã chuẩn hóa một lần”, cần định nghĩa chuẩn hóa hợp lệ, ví dụ `lower(btrim(email))` trong môi trường phù hợp, rồi `DISTINCT` trên **biểu thức đã chuẩn hóa**, thay vì tin rằng bản thân `DISTINCT email` tự hiểu ý nghĩa nghiệp vụ của email.

## 6. DISTINCT và NULL

`NULL` trong SQL biểu diễn thiếu hoặc chưa biết giá trị. Khi so sánh thông thường:

~~~sql
SELECT NULL = NULL AS ket_qua;
~~~

kết quả không phải `TRUE` mà là giá trị logic **`UNKNOWN`** (thường được hiển thị là `NULL`). Nhưng trong **`SELECT DISTINCT`**, nhiều dòng có `NULL` ở cùng vị trí biểu thức được **gộp thành một bộ kết quả**.

Trên bảng mẫu:

~~~sql
SELECT DISTINCT thanh_pho
FROM khach_hang;
~~~

trả về ba giá trị khác biệt: `Hà Nội`, `Đà Nẵng`, **một** `NULL`. Hai khách hàng Dung và Em không bị xóa; truy vấn chỉ hiển thị một bản của trạng thái “chưa biết thành phố”.

Muốn xem riêng những khách chưa có thành phố:

~~~sql
SELECT id, ten_khach_hang
FROM khach_hang
WHERE thanh_pho IS NULL
ORDER BY id;
~~~

Hai dòng vẫn hiện ra vì `id` khác nhau và câu truy vấn không làm mất grain khách hàng.

### 6.1. DISTINCT và UNIQUE khác nhau khi có NULL

Cùng từ “duy nhất”, nhưng hai cơ chế có mục tiêu khác nhau:

- `SELECT DISTINCT thanh_pho` gom các kết quả `NULL` thành một biểu diễn trong tập dòng trả về.
- `UNIQUE (thanh_pho)` là **ràng buộc khi ghi**. Các DBMS xử lý nhiều `NULL` trong ràng buộc này khác nhau: PostgreSQL mặc định thường cho phép nhiều `NULL`, SQL Server với khóa unique một cột thông thường lại có giới hạn khác.

Vì vậy không lấy hành vi của `SELECT DISTINCT` để suy ra `UNIQUE` sẽ ngăn hoặc cho phép dữ liệu `NULL` giống hệt.

### 6.2. Đếm NULL cần dùng đúng hàm

~~~sql
SELECT
    COUNT(*) AS tong_so_khach,
    COUNT(thanh_pho) AS so_khach_co_thanh_pho,
    COUNT(DISTINCT thanh_pho) AS so_thanh_pho_co_gia_tri
FROM khach_hang;
~~~

Với dữ liệu mẫu:

| tong_so_khach | so_khach_co_thanh_pho | so_thanh_pho_co_gia_tri |
| ---: | ---: | ---: |
| 5 | 3 | 2 |

`COUNT(*)` đếm mọi dòng; `COUNT(thanh_pho)` đếm dòng có thành phố **khác `NULL`**; `COUNT(DISTINCT thanh_pho)` đếm **số giá trị thành phố khác nhau và khác `NULL`**. Truy vấn `SELECT DISTINCT thanh_pho` lại có **ba** dòng vì nó hiển thị thêm một dòng `NULL`. Đây không phải mâu thuẫn: `COUNT(expr)` loại `NULL` khỏi đối số đếm.

## 7. DISTINCT và GROUP BY: cùng có thể giảm dòng, nhưng câu hỏi khác nhau

Một kết quả duy nhất theo thành phố có thể được tạo theo hai cách:

~~~sql
SELECT DISTINCT thanh_pho
FROM khach_hang;

SELECT thanh_pho
FROM khach_hang
GROUP BY thanh_pho;
~~~

Với trường hợp chọn **chỉ cột dùng để nhóm** như trên, hai câu thường cho cùng tập giá trị, bao gồm một nhóm `NULL`. Tuy nhiên:

- `DISTINCT` nhấn mạnh **loại các dòng kết quả giống nhau sau phép chiếu**.
- `GROUP BY` xác định **những nhóm dòng** và cho phép tính các hàm tổng hợp như `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`.

Ví dụ hỏi “có bao nhiêu khách hàng ở mỗi thành phố?”:

~~~sql
SELECT
    thanh_pho,
    COUNT(*) AS so_khach
FROM khach_hang
GROUP BY thanh_pho
ORDER BY thanh_pho NULLS LAST;
~~~

Kết quả:

| thanh_pho | so_khach |
| --- | ---: |
| Đà Nẵng | 1 |
| Hà Nội | 2 |
| `NULL` | 2 |

Không thể lấy `SELECT DISTINCT thanh_pho` rồi đọc được số lượng hai khách ở Hà Nội, vì thông tin số lần xuất hiện đã bị loại.

### 7.1. GROUP BY có thể xác định grain mới

Ví dụ thống kê doanh thu theo khách hàng:

~~~sql
SELECT
    khach_hang_id,
    COUNT(*) AS so_don,
    SUM(tong_tien) AS tong_doanh_thu
FROM don_hang
GROUP BY khach_hang_id
ORDER BY khach_hang_id;
~~~

Kết quả:

| khach_hang_id | so_don | tong_doanh_thu |
| ---: | ---: | ---: |
| 1 | 2 | 350000.00 |
| 2 | 1 | 300000.00 |
| 3 | 2 | 300000.00 |

Grain mới là **một dòng cho mỗi khách hàng có đơn hàng**. Hai đơn của An **được cộng**, không phải bị loại một đơn như khi dùng `DISTINCT khach_hang_id`.

Nếu yêu cầu gồm cả khách hàng chưa có đơn, phải bắt đầu từ bảng khách hàng rồi `LEFT JOIN` và xử lý đếm/tổng hợp để giữ khách không có bản ghi con:

~~~sql
SELECT
    kh.id AS khach_hang_id,
    kh.ten_khach_hang,
    COUNT(dh.id) AS so_don,
    COALESCE(SUM(dh.tong_tien), 0) AS tong_doanh_thu
FROM khach_hang AS kh
LEFT JOIN don_hang AS dh
    ON dh.khach_hang_id = kh.id
GROUP BY kh.id, kh.ten_khach_hang
ORDER BY kh.id;
~~~

`COUNT(dh.id)` trả `0` khi không có đơn vì `dh.id` là `NULL` ở dòng `LEFT JOIN` không khớp. Nếu dùng `COUNT(*)`, mỗi khách chưa có đơn vẫn tạo **một dòng nối mở rộng**, khiến số đếm sai thành `1`. Đây là lỗi grain và cách đếm, `DISTINCT` không tự sửa được.

### 7.2. COUNT DISTINCT khác DISTINCT của SELECT

~~~sql
SELECT COUNT(DISTINCT khach_hang_id) AS so_khach_da_mua
FROM don_hang;
~~~

trả về `3`, vì các đơn đến từ khách 1, 2 và 3. Trong khi:

~~~sql
SELECT DISTINCT khach_hang_id
FROM don_hang;
~~~

trả về **ba dòng** chứa các ID `1`, `2`, `3`. Hai cách cùng sử dụng ý tưởng giá trị khác biệt, nhưng cách đầu trả về **một số đếm**, cách sau trả về **danh sách**.

Một số DBMS cho phép cú pháp đếm distinct trên nhiều biểu thức khác nhau, nhưng không thống nhất cách diễn đạt hoặc xử lý `NULL`. Nếu muốn đếm số cặp phân biệt `(khach_hang_id, trang_thai)` theo cách dễ đọc trên PostgreSQL, có thể dùng subquery:

~~~sql
SELECT COUNT(*) AS so_cap_phan_biet
FROM (
    SELECT DISTINCT khach_hang_id, trang_thai
    FROM don_hang
) AS cac_cap;
~~~

Kết quả là `4` với dữ liệu mẫu.

## 8. DISTINCT sau JOIN: phải kiểm tra quan hệ trước

Đây là tình huống phổ biến nhất khiến người học dùng `DISTINCT` quá sớm. Trước tiên hãy hiểu **mỗi dòng đầu vào JOIN đại diện cho gì**.

### 8.1. Quan hệ một khách hàng – nhiều đơn hàng

~~~sql
SELECT
    kh.id AS khach_hang_id,
    kh.ten_khach_hang,
    dh.id AS don_hang_id
FROM khach_hang AS kh
JOIN don_hang AS dh
    ON dh.khach_hang_id = kh.id
ORDER BY kh.id, dh.id;
~~~

Kết quả:

| khach_hang_id | ten_khach_hang | don_hang_id |
| ---: | --- | ---: |
| 1 | An | 101 |
| 1 | An | 102 |
| 2 | Bình | 103 |
| 3 | Chi | 104 |
| 3 | Chi | 105 |

An và Chi xuất hiện hai lần vì mỗi người có hai đơn. Đây **không phải dữ liệu lỗi**. Grain sau JOIN là **một dòng cho mỗi đơn hàng kèm thông tin khách**. Nếu chọn cả `don_hang_id`, năm dòng khác nhau, nên:

~~~sql
SELECT DISTINCT
    kh.id AS khach_hang_id,
    kh.ten_khach_hang,
    dh.id AS don_hang_id
FROM khach_hang AS kh
JOIN don_hang AS dh
    ON dh.khach_hang_id = kh.id;
~~~

vẫn trả về năm dòng.

### 8.2. Nếu muốn chỉ khách hàng có đơn hàng

Khi yêu cầu thực sự là **mỗi khách hàng có ít nhất một đơn xuất hiện một lần**, có hai cách:

**Cách A: JOIN rồi DISTINCT ở mức khách hàng**

~~~sql
SELECT DISTINCT
    kh.id,
    kh.ten_khach_hang
FROM khach_hang AS kh
JOIN don_hang AS dh
    ON dh.khach_hang_id = kh.id
ORDER BY kh.id;
~~~

Kết quả gồm ba khách: An, Bình, Chi. Lưu ý **không chọn `dh.id`**, vì cột đó làm grain quay lại mỗi đơn.

**Cách B: EXISTS để diễn đạt điều kiện tồn tại**

~~~sql
SELECT
    kh.id,
    kh.ten_khach_hang
FROM khach_hang AS kh
WHERE EXISTS (
    SELECT 1
    FROM don_hang AS dh
    WHERE dh.khach_hang_id = kh.id
)
ORDER BY kh.id;
~~~

`EXISTS` trả lời trực tiếp câu hỏi “khách hàng này **có ít nhất một** đơn hay không?” mà không tạo dòng nhân bản từ các đơn. Khi không cần lấy dữ liệu từ hàng con, `EXISTS` thường diễn đạt đúng ý định hơn và có thể giúp bộ tối ưu hóa xử lý như một dạng *semi-join*. Không nên khẳng định nó luôn nhanh hơn; cần đo theo kế hoạch thực thi và chỉ mục thực tế.

### 8.3. JOIN sang bảng chi tiết làm tăng thêm số dòng

~~~sql
SELECT
    dh.id AS don_hang_id,
    ct.id AS chi_tiet_id,
    ct.ma_san_pham,
    ct.so_luong
FROM don_hang AS dh
JOIN chi_tiet_don_hang AS ct
    ON ct.don_hang_id = dh.id
ORDER BY dh.id, ct.id;
~~~

Kết quả có **sáu** dòng chi tiết vì đơn 101 có hai dòng hàng. Nếu cần **một dòng cho mỗi đơn**, JOIN trực tiếp với chi tiết mà chưa nhóm sẽ tạo nhiều dòng cho đơn 101. Thêm `DISTINCT dh.id` chỉ cho biết mã đơn, không tính được tổng số sản phẩm.

Muốn biết tổng số lượng sản phẩm trong từng đơn:

~~~sql
SELECT
    dh.id AS don_hang_id,
    SUM(ct.so_luong) AS tong_so_luong
FROM don_hang AS dh
JOIN chi_tiet_don_hang AS ct
    ON ct.don_hang_id = dh.id
GROUP BY dh.id
ORDER BY dh.id;
~~~

Grain là một dòng theo **đơn hàng** và tổng số lượng được tính từ các dòng chi tiết. Với dữ liệu mẫu, đơn `101` có tổng `3` đơn vị sản phẩm (`1 + 2`), không phải `2` vì có hai dòng, và không phải `1` vì chỉ nhìn một sản phẩm.

### 8.4. JOIN sai điều kiện: DISTINCT che triệu chứng

Ví dụ cố tình thiếu điều kiện kết nối:

~~~sql
-- Minh họa nguy cơ: không có ON nên tạo mọi cặp!
SELECT kh.id, dh.id
FROM khach_hang AS kh
CROSS JOIN don_hang AS dh;
~~~

Với năm khách và năm đơn, kết quả có **25 cặp**. `SELECT DISTINCT kh.id` sau phép ghép có thể trả về năm ID khách và trông “đúng số lượng”, nhưng không chứng minh kết nối đúng nghiệp vụ. Một JOIN sai có thể làm tăng tổng doanh thu, số lượng đơn hoặc kết quả phân trang.

Khi thấy nhiều dòng ngoài dự kiến, hãy xác nhận **khóa liên kết và quan hệ 1–1, 1–n, n–n** trước. `DISTINCT` chỉ nên được dùng khi mục tiêu thật sự là **tập giá trị khác biệt**.

## 9. “Một dòng mỗi khách hàng” nhưng vẫn cần thông tin từ đơn hàng

Đây là yêu cầu đòi hỏi lựa chọn quy tắc **đại diện**, không chỉ loại trùng.

Giả sử muốn trả về **mỗi khách đã mua một dòng, kèm đơn mới nhất của khách**. Nếu viết:

~~~sql
SELECT DISTINCT
    kh.id,
    kh.ten_khach_hang,
    dh.id,
    dh.thoi_diem_dat
FROM khach_hang AS kh
JOIN don_hang AS dh
    ON dh.khach_hang_id = kh.id;
~~~

thì vẫn có năm dòng, vì hai đơn của An mang ID/thời điểm khác nhau. Nếu xóa các cột đơn hàng khỏi SELECT để còn ba khách, lại **mất thông tin đơn mới nhất**. Cần quy tắc chọn một đơn đại diện.

### 9.1. Dùng ROW_NUMBER để chọn dòng đại diện

Một mẫu SQL sử dụng **window function**:

~~~sql
WITH don_duoc_xep_hang AS (
    SELECT
        dh.id AS don_hang_id,
        dh.khach_hang_id,
        dh.thoi_diem_dat,
        dh.tong_tien,
        ROW_NUMBER() OVER (
            PARTITION BY dh.khach_hang_id
            ORDER BY dh.thoi_diem_dat DESC, dh.id DESC
        ) AS stt
    FROM don_hang AS dh
)
SELECT
    kh.id AS khach_hang_id,
    kh.ten_khach_hang,
    dxh.don_hang_id,
    dxh.thoi_diem_dat,
    dxh.tong_tien
FROM khach_hang AS kh
JOIN don_duoc_xep_hang AS dxh
    ON dxh.khach_hang_id = kh.id
   AND dxh.stt = 1
ORDER BY kh.id;
~~~

`PARTITION BY dh.khach_hang_id` chia đơn theo khách; `ORDER BY` sắp đơn mới nhất trước; `ROW_NUMBER()` cấp thứ tự `1, 2, ...` trong mỗi khách; `stt = 1` lấy **một đơn mới nhất**.

Thêm `dh.id DESC` làm tiêu chí phụ để chọn ổn định khi hai đơn có cùng thời điểm. Với dữ liệu mẫu:

| khach_hang_id | ten_khach_hang | don_hang_id |
| ---: | --- | ---: |
| 1 | An | 102 |
| 2 | Bình | 103 |
| 3 | Chi | 105 |

Khách chưa có đơn không xuất hiện do dùng `JOIN`. Nếu cần giữ cả Dung và Em, có thể thay bằng `LEFT JOIN` với điều kiện `dxh.stt = 1` ở **mệnh đề `ON`** hoặc tiền lọc trong CTE, để hai người chưa có đơn vẫn được biểu diễn bằng các cột đơn hàng `NULL`.

Window function không tự giảm số dòng; chính bước lọc `stt = 1` mới chọn một hàng đại diện theo grain mong muốn.

### 9.2. PostgreSQL: DISTINCT ON chọn một dòng mỗi nhóm

PostgreSQL có tiện ích **`DISTINCT ON`**, không phải cú pháp SQL chuẩn dùng được ở mọi hệ quản trị:

~~~sql
SELECT DISTINCT ON (khach_hang_id)
    khach_hang_id,
    id AS don_hang_id,
    thoi_diem_dat,
    tong_tien
FROM don_hang
ORDER BY khach_hang_id, thoi_diem_dat DESC, id DESC;
~~~

`DISTINCT ON (khach_hang_id)` **giữ dòng đầu tiên của mỗi nhóm khách** theo thứ tự do `ORDER BY` quy định. Điều kiện của PostgreSQL yêu cầu các biểu thức `DISTINCT ON` phải khớp những biểu thức đầu tiên trong `ORDER BY` theo quy tắc của nó. Vì vậy `ORDER BY khach_hang_id, thoi_diem_dat DESC, id DESC` là dạng phù hợp: nhóm theo khách, rồi ưu tiên đơn mới nhất và ID lớn nhất khi trùng thời gian.

Nếu thiếu thứ tự đủ xác định, “dòng đầu tiên” không mang ý nghĩa lựa chọn ổn định. Đây là điểm khác quan trọng với **`SELECT DISTINCT` thường**: `DISTINCT ON` cho phép giữ **các cột khác nhau của một hàng được chọn**, trong khi `SELECT DISTINCT` chỉ loại những **bộ giá trị kết quả trùng hoàn toàn**.

Nếu ứng dụng cần SQL chạy trên nhiều DBMS, mẫu `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)` thường là lựa chọn dễ chuyển đổi hơn, dù vẫn phải kiểm tra cú pháp và tối ưu hóa của DBMS đích.

## 10. DISTINCT, ORDER BY và LIMIT/OFFSET

Phép lọc, loại trùng, sắp xếp và phân trang phục vụ các vai trò khác nhau. Một cách hình dung thứ tự xử lý **logic** thường gặp của truy vấn SQL là:

~~~mermaid
flowchart TD
    A["FROM / JOIN: hình thành tập dòng nguồn"] --> B["WHERE: lọc dòng"]
    B --> C["GROUP BY: nhóm khi có tổng hợp"]
    C --> D["HAVING: lọc nhóm"]
    D --> E["SELECT: tạo các biểu thức kết quả"]
    E --> F["DISTINCT: loại bộ kết quả trùng"]
    F --> G["ORDER BY: sắp xếp kết quả"]
    G --> H["LIMIT / OFFSET / FETCH: lấy phần kết quả"]
~~~

Đây là **mô hình logic để hiểu ngữ nghĩa**, không phải cam kết thứ tự thao tác vật lý trong kế hoạch thực thi. Bộ tối ưu hóa có thể thay đổi chiến lược hoặc đẩy phép lọc để chạy hiệu quả hơn mà vẫn giữ ngữ nghĩa đúng.

### 10.1. Phân trang sau khi loại trùng

~~~sql
SELECT DISTINCT trang_thai
FROM don_hang
ORDER BY trang_thai
LIMIT 1;
~~~

Truy vấn trả một trạng thái theo thứ tự sắp xếp sau khi loại trùng. Không tương đương với việc lấy một đơn hàng trước rồi mới hỏi trạng thái của đơn đó:

~~~sql
SELECT DISTINCT trang_thai
FROM (
    SELECT trang_thai
    FROM don_hang
    ORDER BY id
    LIMIT 1
) AS mot_don;
~~~

Truy vấn thứ hai cố ý giới hạn dữ liệu **đầu vào** còn một đơn trước khi `DISTINCT`, nên có thể cho tập trạng thái khác. Vị trí của `LIMIT` trong query/subquery thay đổi ý nghĩa.

### 10.2. ORDER BY với SELECT DISTINCT

Trong PostgreSQL, khi dùng `SELECT DISTINCT`, biểu thức dùng trong `ORDER BY` thông thường phải xuất hiện trong danh sách SELECT:

~~~sql
-- Hợp lệ:
SELECT DISTINCT trang_thai
FROM don_hang
ORDER BY trang_thai;

-- Không hợp lệ trong PostgreSQL:
-- SELECT DISTINCT trang_thai
-- FROM don_hang
-- ORDER BY thoi_diem_dat DESC;
~~~

Vì một trạng thái có thể xuất hiện ở nhiều đơn với nhiều thời điểm, nên “sắp theo thời điểm của trạng thái” **chưa xác định chọn thời điểm nào**. Nếu muốn sắp theo thời điểm xuất hiện mới nhất của mỗi trạng thái, hãy định nghĩa rõ bằng tổng hợp:

~~~sql
SELECT
    trang_thai,
    MAX(thoi_diem_dat) AS xuat_hien_moi_nhat
FROM don_hang
GROUP BY trang_thai
ORDER BY xuat_hien_moi_nhat DESC, trang_thai;
~~~

### 10.3. Kết quả phân trang cần thứ tự xác định

`LIMIT 10 OFFSET 10` không mang ý nghĩa “trang thứ hai ổn định” nếu không có `ORDER BY` rõ ràng. Ngay cả khi đã `DISTINCT`, việc phân trang vẫn có thể đổi khi dữ liệu được thêm/sửa. Với dữ liệu lớn và thay đổi thường xuyên, có thể cân nhắc **keyset pagination** khi có khóa/thứ tự phù hợp; đó là quyết định về mô hình phân trang chứ không phải tính năng thay thế cho `DISTINCT`.

## 11. Hiệu năng: DISTINCT có chi phí và không chữa sai thiết kế

Để xác định dòng khác biệt, DBMS thường phải thực hiện chiến lược như **sắp xếp rồi loại dòng trùng** hoặc **băm theo khóa phân biệt**. Với tập dữ liệu lớn, thao tác này có thể tiêu thụ bộ nhớ, CPU, I/O hoặc cần dữ liệu tạm. Kế hoạch cụ thể phụ thuộc DBMS, thống kê, chỉ mục, độ rộng dòng và truy vấn.

Ví dụ:

~~~sql
SELECT DISTINCT khach_hang_id
FROM don_hang;
~~~

có thể hiệu quả hơn việc lấy tất cả đơn rồi loại trùng ở ứng dụng, nhưng không có nghĩa `DISTINCT` luôn “miễn phí”. Nếu mục tiêu là lọc khách có đơn, `EXISTS` có thể biểu diễn tốt hơn; nếu mục tiêu là tổng tiền theo khách, `GROUP BY` mới cung cấp phép tính đúng. Cần chọn **đúng toán tử theo ý nghĩa**, sau đó mới tối ưu.

### 11.1. Những câu hỏi cần hỏi khi số dòng tăng bất thường

1. **Grain mong muốn** là một khách, một đơn, một chi tiết hay một cặp giá trị?
2. Từng bảng có grain gì? Khóa nào định danh mỗi dòng?
3. Điều kiện JOIN dùng đúng khóa và đủ các thành phần chưa, nhất là trong dữ liệu đa tổ chức?
4. Có JOIN từ bảng cha sang nhiều hàng con hay nhiều quan hệ 1–n đồng thời không?
5. Có đang chọn cột `id` làm `DISTINCT` không thể giảm số dòng?
6. Cần loại bộ trùng, đếm số giá trị khác biệt, tổng hợp hay chọn một hàng đại diện?

Đặc biệt khi nối **hai bảng con 1–n** cùng cha, mỗi bên có thể nhân số dòng của bên kia. Ví dụ một đơn có ba dòng sản phẩm và hai sự kiện thanh toán: JOIN cùng lúc có thể tạo sáu dòng. Nếu lấy `SUM(so_luong)` sau JOIN, tổng có thể bị **nhân đôi**. Thêm `DISTINCT` vào SELECT không tự bảo đảm tổng đúng; thường cần **tổng hợp từng bảng con về grain đơn hàng trước khi ghép**.

### 11.2. Dùng EXPLAIN để tìm điểm gây nhân dòng

Trong PostgreSQL:

~~~sql
EXPLAIN
SELECT DISTINCT kh.id, kh.ten_khach_hang
FROM khach_hang AS kh
JOIN don_hang AS dh ON dh.khach_hang_id = kh.id;
~~~

`EXPLAIN` mô tả kế hoạch dự kiến của bộ tối ưu hóa và giúp xem các bước JOIN, sắp xếp hoặc loại trùng. Nếu chạy `EXPLAIN ANALYZE`, truy vấn **được thực thi thật** để đo thời gian và số dòng thực tế; chỉ dùng khi phù hợp môi trường, đặc biệt với câu lệnh có khả năng thay đổi dữ liệu.

Không thể đánh giá chính xác hiệu năng chỉ từ việc thấy từ khóa `DISTINCT`; hiệu năng còn phụ thuộc dữ liệu, chỉ mục, cấu hình và mục đích kết quả.

## 12. Các cách xác nhận grain và đếm dòng

Khi debug một truy vấn thực tế, có thể kiểm tra bằng những truy vấn nhỏ:

**Đếm số dòng gốc:**

~~~sql
SELECT COUNT(*) AS so_don
FROM don_hang;
-- 5
~~~

**Đếm số khách khác biệt trong đơn hàng:**

~~~sql
SELECT COUNT(DISTINCT khach_hang_id) AS so_khach_co_don
FROM don_hang;
-- 3
~~~

**Tìm khách xuất hiện hơn một lần trong bảng đơn:**

~~~sql
SELECT
    khach_hang_id,
    COUNT(*) AS so_don
FROM don_hang
GROUP BY khach_hang_id
HAVING COUNT(*) > 1
ORDER BY khach_hang_id;
-- Khách 1 và 3, mỗi người có 2 đơn.
~~~

**Kiểm tra số dòng sau JOIN:**

~~~sql
SELECT COUNT(*) AS so_dong_sau_join
FROM khach_hang AS kh
JOIN don_hang AS dh
    ON dh.khach_hang_id = kh.id;
-- 5 dòng: một dòng cho mỗi đơn, trong bộ mẫu này.
~~~

**Kiểm tra grain qua số khóa khác nhau:**

~~~sql
SELECT
    COUNT(*) AS so_dong,
    COUNT(DISTINCT kh.id) AS so_khach,
    COUNT(DISTINCT dh.id) AS so_don
FROM khach_hang AS kh
JOIN don_hang AS dh
    ON dh.khach_hang_id = kh.id;
-- so_dong = 5, so_khach = 3, so_don = 5.
~~~

Trong ví dụ, `so_dong` và `so_don` bằng nhau nên sau JOIN kết quả vẫn có một dòng cho mỗi đơn; `so_khach` nhỏ hơn vì một khách có thể có nhiều đơn. Tuy vậy, kiểm tra số lượng riêng lẻ **không phải chứng minh đầy đủ** rằng một JOIN luôn đúng: các dòng bị thiếu và dòng nhân bản có thể tình cờ triệt tiêu về mặt số đếm. Cần xác nhận thêm khóa, logic quan hệ và dữ liệu mẫu.

### 12.1. Đừng vội dùng DISTINCT để làm sạch bảng nguồn

Nếu bảng nguồn thật sự có dữ liệu trùng nghiệp vụ, chẳng hạn hai bản ghi khách có cùng mã định danh do nhập lỗi, cần xử lý ở nơi dữ liệu được ghi và xem xét ràng buộc `UNIQUE`. `SELECT DISTINCT` chỉ thay đổi phần hiển thị, không ngăn dữ liệu trùng tiếp tục được tạo hoặc gây lỗi ở chỗ khác.

Ngược lại, nhiều đơn của cùng khách hoặc nhiều sản phẩm trong cùng đơn hoàn toàn là dữ liệu **hợp lệ**. Gọi chúng là “trùng” vì thấy tên khách lặp là nhầm giữa grain khách hàng và grain đơn/chi tiết đơn.

## 13. Bảng chọn nhanh: yêu cầu nào dùng cách nào?

| Câu hỏi nghiệp vụ | Grain kết quả | Cách tiếp cận phù hợp |
| --- | --- | --- |
| Có những thành phố nào trong dữ liệu khách? | Một giá trị thành phố | `SELECT DISTINCT thanh_pho` |
| Có bao nhiêu thành phố đã nhập? | Một số đếm | `COUNT(DISTINCT thanh_pho)` |
| Mỗi thành phố có bao nhiêu khách? | Một dòng mỗi thành phố | `GROUP BY thanh_pho`, `COUNT(*)` |
| Khách nào từng đặt hàng? | Một dòng mỗi khách có đơn | `WHERE EXISTS (...)`, hoặc JOIN rồi `DISTINCT` chỉ các cột khách |
| Mỗi khách đã đặt bao nhiêu đơn? | Một dòng mỗi khách | `GROUP BY khach_hang_id`, `COUNT(*)` |
| Mỗi khách từng có trạng thái đơn nào? | Một dòng mỗi cặp khách–trạng thái | `SELECT DISTINCT khach_hang_id, trang_thai` |
| Đơn gần nhất của từng khách? | Một dòng mỗi khách có đơn | `ROW_NUMBER()` và lọc `rn = 1`; PostgreSQL có `DISTINCT ON` |
| Tổng số lượng sản phẩm của từng đơn? | Một dòng mỗi đơn | JOIN chi tiết rồi `SUM`/`GROUP BY` đúng grain |
| Một email không được nhập trùng trong DB? | Quy tắc khi ghi, không phải truy vấn hiển thị | Ràng buộc `UNIQUE` theo ngữ nghĩa nghiệp vụ |

## 14. Các lỗi phổ biến khi dùng DISTINCT

| Cách hiểu/cách viết dễ sai | Vì sao sai hoặc chưa đủ | Cách sửa tư duy |
| --- | --- | --- |
| “`DISTINCT` chỉ áp dụng cho cột đầu tiên.” | Nó áp dụng cho **bộ tất cả biểu thức** trong SELECT. | Xác định tập cột định nghĩa trùng lặp. |
| “JOIN trả nhiều dòng thì thêm DISTINCT *.” | JOIN 1–n có thể tạo các dòng khác biệt hợp lệ. | Kiểm tra khóa JOIN và grain muốn đạt. |
| “`DISTINCT id, ten` cho một dòng mỗi tên.” | Cột `id` riêng biệt làm mọi cặp khác nhau. | Chỉ chọn cột cần phân biệt hoặc xác định quy tắc đại diện. |
| “`DISTINCT` giúp lấy đơn mới nhất.” | Nó không tự chọn theo ngày. | Dùng `ROW_NUMBER`, `DISTINCT ON` hoặc mẫu truy vấn có quy tắc rõ. |
| “Kết quả DISTINCT tự có thứ tự.” | Không có `ORDER BY` thì thứ tự không được bảo đảm. | Thêm thứ tự có ý nghĩa khi cần. |
| “DISTINCT và GROUP BY là một.” | GROUP BY hỗ trợ tổng hợp; DISTINCT loại bộ kết quả trùng. | Chọn theo câu hỏi nghiệp vụ. |
| “`COUNT(DISTINCT col)` bằng số dòng `SELECT DISTINCT col`.” | COUNT đối số bỏ `NULL`; SELECT DISTINCT có thể giữ một `NULL`. | Xét quy tắc NULL của từng biểu thức. |
| “Dùng `DISTINCT` sẽ sửa số tiền bị nhân do JOIN sai.” | Phép nhân dòng có thể ảnh hưởng tổng trước khi loại trùng. | Sửa JOIN hoặc tổng hợp ở grain đúng. |
| “Dùng DISTINCT để ngăn dữ liệu mới bị trùng.” | DISTINCT chỉ tác động truy vấn SELECT. | Dùng constraint/index phù hợp khi ghi. |
| “Thấy ít dòng hơn nghĩa là truy vấn đúng hơn.” | Có thể đã loại mất chi tiết cần thiết. | Đối chiếu với grain mà yêu cầu đặt ra. |

## 15. Bài tập thực hành có lời giải

Tất cả bài tập dùng dữ liệu ở mục 3 trong PostgreSQL, trừ khi nêu khác. Nên xác định **grain** (một dòng biểu diễn gì) trước khi dự đoán số dòng.

### Bài 1: DISTINCT một cột

~~~sql
SELECT DISTINCT trang_thai
FROM don_hang;
~~~

**Câu hỏi:** Có bao nhiêu dòng? **Lời giải:** Hai dòng, tương ứng `DA_XAC_NHAN` và `MOI`. Không có `ORDER BY` nên không giả định thứ tự hiển thị.

### Bài 2: DISTINCT hai cột

~~~sql
SELECT DISTINCT khach_hang_id, trang_thai
FROM don_hang;
~~~

**Câu hỏi:** Có bao nhiêu dòng? **Lời giải:** Bốn dòng: `(1, DA_XAC_NHAN)`, `(2, MOI)`, `(3, DA_XAC_NHAN)`, `(3, MOI)`. Hai đơn 101 và 102 của khách 1 có cùng cặp nên được biểu diễn một lần.

### Bài 3: Thêm một cột ID

~~~sql
SELECT DISTINCT id, khach_hang_id, trang_thai
FROM don_hang;
~~~

**Câu hỏi:** Vì sao kết quả có năm dòng? **Lời giải:** `id` là khóa duy nhất của đơn hàng, nên mỗi bộ ba `(id, khach_hang_id, trang_thai)` là khác nhau. `DISTINCT` không giảm số dòng.

### Bài 4: DISTINCT và NULL

~~~sql
SELECT DISTINCT thanh_pho
FROM khach_hang;

SELECT COUNT(DISTINCT thanh_pho)
FROM khach_hang;
~~~

**Câu hỏi:** Vì sao câu đầu có ba dòng nhưng câu sau trả số `2`? **Lời giải:** `SELECT DISTINCT` hiển thị hai thành phố có giá trị cộng một `NULL`. `COUNT(DISTINCT ...)` chỉ đếm các giá trị khác biệt và khác `NULL`.

### Bài 5: JOIN hay dữ liệu trùng?

~~~sql
SELECT kh.ten_khach_hang, dh.id
FROM khach_hang AS kh
JOIN don_hang AS dh
    ON dh.khach_hang_id = kh.id;
~~~

**Câu hỏi:** Vì sao An và Chi lặp hai lần? **Lời giải:** Mỗi người có hai đơn. Grain của truy vấn là **mỗi đơn hàng kèm tên khách**; lặp tên khách là đúng theo quan hệ 1–n. Nếu muốn mỗi khách xuất hiện một dòng, hãy diễn đạt rõ liệu cần danh sách khách có đơn, tổng số đơn hay đơn mới nhất rồi chọn `EXISTS`, `GROUP BY`, hoặc `ROW_NUMBER` phù hợp.

### Bài 6: Số đơn theo từng khách, kể cả khách chưa mua

Hãy viết truy vấn trả về một dòng cho mỗi khách (tổng cộng năm dòng), với `so_don = 0` cho Dung và Em.

**Một lời giải:**

~~~sql
SELECT
    kh.id,
    kh.ten_khach_hang,
    COUNT(dh.id) AS so_don
FROM khach_hang AS kh
LEFT JOIN don_hang AS dh
    ON dh.khach_hang_id = kh.id
GROUP BY kh.id, kh.ten_khach_hang
ORDER BY kh.id;
~~~

`COUNT(dh.id)` đếm ID đơn **khác NULL**, nên trả `0` với khách không có đơn. `COUNT(*)` không phù hợp ở trường hợp này vì dòng mở rộng do `LEFT JOIN` vẫn được đếm.

### Bài 7: Chọn đơn mới nhất

**Yêu cầu:** Trả mỗi khách có đơn một dòng với ID của đơn mới nhất. Có nên dùng `SELECT DISTINCT khach_hang_id, id` không?

**Lời giải:** Không, vì mỗi `id` đơn là duy nhất, câu đó vẫn trả đủ năm dòng. Có thể viết:

~~~sql
SELECT khach_hang_id, don_hang_id
FROM (
    SELECT
        khach_hang_id,
        id AS don_hang_id,
        ROW_NUMBER() OVER (
            PARTITION BY khach_hang_id
            ORDER BY thoi_diem_dat DESC, id DESC
        ) AS rn
    FROM don_hang
) AS x
WHERE rn = 1
ORDER BY khach_hang_id;
~~~

Kết quả gồm `(1, 102)`, `(2, 103)`, `(3, 105)`. Mức chi tiết là một dòng cho mỗi khách có đơn.

### Bài 8: Một sản phẩm có thể xuất hiện trong nhiều đơn

~~~sql
SELECT DISTINCT ma_san_pham
FROM chi_tiet_don_hang
ORDER BY ma_san_pham;
~~~

**Câu hỏi:** Kết quả gồm những mã nào? **Lời giải:** `SP_A`, `SP_B`, `SP_C` — mỗi mã một lần. Đây là **danh sách mã sản phẩm đã từng xuất hiện**, không phải số dòng chi tiết, tổng số lượng hay danh mục đầy đủ các sản phẩm của hệ thống.

### Bài 9: Phân biệt số đơn và tổng số sản phẩm

~~~sql
SELECT
    don_hang_id,
    COUNT(*) AS so_dong_hang,
    SUM(so_luong) AS tong_so_luong
FROM chi_tiet_don_hang
GROUP BY don_hang_id
ORDER BY don_hang_id;
~~~

**Câu hỏi:** Với đơn `101`, hai cột kết quả là bao nhiêu? **Lời giải:** `so_dong_hang = 2` vì có hai dòng chi tiết, nhưng `tong_so_luong = 3` vì số lượng là `1 + 2`. `SELECT DISTINCT don_hang_id` chỉ cho biết đơn đó tồn tại, không trả lời các phép tính này.

## 16. Ghi nhớ khi đọc một câu truy vấn

Trước mỗi câu SQL có `DISTINCT`, hãy diễn đạt trong một câu ngắn: **“Tôi cần một dòng cho mỗi ...”**. Nếu phần còn lại của câu đó là *giá trị thành phố*, `SELECT DISTINCT thanh_pho` phù hợp. Nếu là *khách hàng*, cần giữ khóa khách; nếu là *đơn hàng*, cần giữ khóa đơn; nếu là *một đơn mới nhất của mỗi khách*, phải có tiêu chí chọn đại diện.

`DISTINCT` là công cụ hữu ích để loại các **bộ giá trị kết quả lặp lại**. Nó hoạt động trên toàn bộ danh sách biểu thức SELECT, gộp các kết quả `NULL` trùng ở vị trí tương ứng, và không tự sắp xếp hay sửa dữ liệu nguồn. Việc kết hợp đúng `DISTINCT` với **grain**, `JOIN`, `GROUP BY`, `COUNT(DISTINCT ...)`, `EXISTS` và các kỹ thuật chọn dòng đại diện giúp kết quả SQL vừa đúng ý nghĩa vừa tránh mất hoặc nhân bản thông tin.

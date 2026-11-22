# INNER JOIN và điều kiện ghép bằng khóa trong SQL

Trong cơ sở dữ liệu quan hệ, thông tin của một nghiệp vụ thường được chia thành nhiều bảng: bảng khách hàng lưu thông tin khách, bảng đơn hàng lưu những lần mua, còn bảng chi tiết đơn hàng lưu các sản phẩm trong từng đơn. Nếu một báo cáo cần hiển thị **mã đơn hàng, tên khách và trạng thái đơn**, ta phải **kết nối các bảng bằng mối quan hệ giữa các khóa**.

`INNER JOIN` là một trong những phép ghép nền tảng của SQL. Nó chỉ giữ các **cặp hoặc tổ hợp hàng thỏa điều kiện ghép**. Sử dụng đúng `INNER JOIN` đòi hỏi nhiều hơn việc nhớ cú pháp: người viết truy vấn cần hiểu khóa chính, khóa ngoại, mối quan hệ một–nhiều, mức chi tiết của kết quả và những trường hợp dữ liệu không khớp hoặc chứa `NULL`.

Bài này tập trung vào **`INNER JOIN` và điều kiện ghép bằng khóa**. Các ví dụ chính chạy trên **PostgreSQL**, đồng thời chỉ ra các điểm chung và khác biệt cần lưu ý ở MySQL, SQL Server và Oracle Database.

## 1. Tại sao cần JOIN?

Giả sử hệ thống lưu:

**Bảng khách hàng**

| id | ten_khach_hang |
| ---: | --- |
| 1 | An |
| 2 | Bình |
| 3 | Chi |

**Bảng đơn hàng**

| id | khach_hang_id | tong_tien |
| ---: | ---: | ---: |
| 101 | 1 | 200000 |
| 102 | 1 | 300000 |
| 103 | 2 | 150000 |

Trong bảng đơn hàng, `khach_hang_id` lưu **khóa tham chiếu** đến khách hàng, thay vì sao chép toàn bộ tên và thông tin liên hệ vào mỗi đơn. Cách tách bảng có thể giảm dư thừa, bảo vệ tính nhất quán và thể hiện rõ quan hệ giữa các thực thể.

Muốn xem tên khách của từng đơn, ta có thể ghép:

~~~sql
SELECT
    dh.id AS ma_don_hang,
    kh.ten_khach_hang,
    dh.tong_tien
FROM don_hang AS dh
INNER JOIN khach_hang AS kh
    ON dh.khach_hang_id = kh.id;
~~~

Ý nghĩa quan trọng nhất của điều kiện:

~~~sql
ON dh.khach_hang_id = kh.id
~~~

là **đơn hàng của một khách chỉ ghép với đúng hàng khách hàng mà khóa tham chiếu trỏ tới**. Nếu bỏ hoặc viết sai điều kiện này, kết quả có thể bị nhân dòng, ghép sai tên khách và làm sai số liệu.

## 2. Ôn lại khóa chính và khóa ngoại

Trước khi học JOIN, cần phân biệt hai loại khóa:

- **Khóa chính** (*primary key*, `PRIMARY KEY`): tập một hoặc nhiều cột nhận diện duy nhất một hàng trong bảng; các cột thuộc khóa chính không được `NULL`.
- **Khóa ngoại** (*foreign key*, `FOREIGN KEY`): tập cột trong bảng con tham chiếu khóa phù hợp của bảng cha, giúp DBMS bảo vệ quan hệ tham chiếu khi khai báo và thực thi ràng buộc.

Ví dụ thiết kế:

~~~sql
CREATE TABLE khach_hang (
    id BIGINT PRIMARY KEY,
    ho_ten TEXT NOT NULL
);

CREATE TABLE don_hang (
    id BIGINT PRIMARY KEY,
    khach_hang_id BIGINT NOT NULL,
    tong_tien NUMERIC(12, 2) NOT NULL,
    CONSTRAINT fk_don_hang_khach
        FOREIGN KEY (khach_hang_id) REFERENCES khach_hang(id)
);
~~~

Ở đây:

| Bảng | Cột | Vai trò |
| --- | --- | --- |
| `khach_hang` | `id` | Khóa chính của khách |
| `don_hang` | `id` | Khóa chính của đơn hàng |
| `don_hang` | `khach_hang_id` | Khóa ngoại tham chiếu `khach_hang.id` |

Quan hệ **một khách hàng – nhiều đơn hàng** được mô tả:

~~~mermaid
flowchart LR
    K["khach_hang\nPK: id"] -->|"1 khách có thể có 0..n đơn"| D["don_hang\nPK: id\nFK: khach_hang_id"]
~~~

**Chú ý:** Cột khóa ngoại **không mặc nhiên duy nhất** trong bảng con. Nhiều đơn hoàn toàn có thể cùng chứa `khach_hang_id = 1`. Chính điều đó giải thích vì sao kết quả JOIN có thể có nhiều dòng cho cùng một khách.

Ràng buộc `FOREIGN KEY` và câu lệnh `JOIN` là hai khái niệm liên quan nhưng **khác nhiệm vụ**: ràng buộc bảo vệ quan hệ khi ghi dữ liệu; JOIN đọc dữ liệu bằng điều kiện do truy vấn cung cấp. Một truy vấn vẫn có thể ghép các bảng dù chưa khai báo khóa ngoại, nhưng như vậy DBMS không tự bảo đảm toàn vẹn tham chiếu.

## 3. Cú pháp INNER JOIN

Cấu trúc cơ bản:

~~~sql
SELECT danh_sach_cot
FROM bang_trai AS a
INNER JOIN bang_phai AS b
    ON dieu_kien_ghep
WHERE dieu_kien_loc
ORDER BY cot_sap_xep;
~~~

`INNER JOIN` lấy các hàng bên trái, tìm các hàng bên phải thỏa điều kiện trong `ON` rồi sinh ra một dòng kết quả cho **mỗi cặp hàng khớp**. Nếu một hàng bên trái khớp ba hàng bên phải thì thường sinh ba dòng; nếu không khớp hàng nào thì **không xuất hiện**.

Trong các hệ quản trị phổ biến, viết `JOIN` không kèm `INNER` thường có cùng nghĩa với `INNER JOIN`:

~~~sql
FROM don_hang AS dh
JOIN khach_hang AS kh
    ON dh.khach_hang_id = kh.id
~~~

Tuy vậy, khi học cú pháp, viết đầy đủ `INNER JOIN` có thể giúp nhấn mạnh **chỉ giữ các hàng khớp**.

### 3.1. Vai trò của FROM, JOIN, ON và WHERE

| Thành phần | Chức năng | Ví dụ |
| --- | --- | --- |
| `FROM` | Xác định bảng/nguồn dữ liệu ban đầu | `FROM don_hang AS dh` |
| `INNER JOIN` | Khai báo nguồn dữ liệu cần kết nối | `INNER JOIN khach_hang AS kh` |
| `ON` | Mô tả **điều kiện ghép hàng** | `ON dh.khach_hang_id = kh.id` |
| `WHERE` | Lọc kết quả theo điều kiện nghiệp vụ | `WHERE dh.trang_thai = 'MOI'` |
| `SELECT` | Chọn các cột/biểu thức đưa ra kết quả | `SELECT dh.id, kh.ho_ten` |

Với `INNER JOIN` thuần túy và các điều kiện xác định thông thường, một phép lọc được đặt trong `ON` hoặc `WHERE` đôi khi cho cùng tập dòng. Tuy nhiên, cách viết rõ nhất là **đặt quan hệ giữa các khóa trong `ON`**, còn điều kiện lọc nghiệp vụ thường đặt trong `WHERE`. Khi chuyển sang `LEFT JOIN`, vị trí `ON`/`WHERE` có thể làm thay đổi kết quả đáng kể.

### 3.2. Dùng bí danh để tránh mơ hồ

Nhiều bảng có cột cùng tên `id`, `ten`, `ngay_tao`. Khi nối, cần chỉ rõ cột thuộc bảng nào:

~~~sql
SELECT
    dh.id AS don_hang_id,
    kh.id AS khach_hang_id,
    kh.ten_khach_hang
FROM don_hang AS dh
INNER JOIN khach_hang AS kh
    ON dh.khach_hang_id = kh.id;
~~~

`dh` và `kh` là **bí danh bảng** (*table alias*) có hiệu lực trong truy vấn. Chúng giúp câu SQL ngắn mà vẫn dễ xác định nguồn của từng cột. `AS don_hang_id` và `AS khach_hang_id` là **bí danh cột kết quả**, không đổi tên cột vật lý trong bảng.

Nếu viết `SELECT id` khi cả hai bảng đều có cột `id`, DBMS thường báo lỗi **tên cột không rõ thuộc bảng nào**. Nên định danh cột bằng bí danh ở các truy vấn có JOIN, nhất là cột khóa.

## 4. Bộ dữ liệu PostgreSQL để thực hành

Để mọi ví dụ nhất quán, ta tạo ba bảng tạm: khách hàng, đơn hàng, chi tiết đơn hàng. Hệ thống phục vụ hai tổ chức khác nhau nhằm minh họa cả trường hợp ghép theo khóa trong môi trường đa tổ chức.

~~~sql
CREATE TEMP TABLE khach_hang_join (
    id INTEGER PRIMARY KEY,
    to_chuc_id INTEGER NOT NULL,
    ten_khach_hang TEXT NOT NULL,
    thanh_pho TEXT,
    CONSTRAINT uq_khach_theo_to_chuc UNIQUE (to_chuc_id, id)
);

INSERT INTO khach_hang_join (id, to_chuc_id, ten_khach_hang, thanh_pho)
VALUES
    (1, 10, 'An',   'Hà Nội'),
    (2, 10, 'Bình', 'Đà Nẵng'),
    (3, 10, 'Chi',  'Hà Nội'),
    (4, 20, 'Dung', 'TP.HCM'),
    (5, 20, 'Em',   'TP.HCM'),
    (6, 10, 'Lan',  NULL);

CREATE TEMP TABLE don_hang_join (
    id INTEGER PRIMARY KEY,
    to_chuc_id INTEGER NOT NULL,
    khach_hang_id INTEGER NOT NULL,
    trang_thai TEXT NOT NULL,
    tong_tien NUMERIC(12, 2) NOT NULL CHECK (tong_tien >= 0),
    CONSTRAINT fk_don_khach_cung_to_chuc
        FOREIGN KEY (to_chuc_id, khach_hang_id)
        REFERENCES khach_hang_join(to_chuc_id, id)
);

INSERT INTO don_hang_join
    (id, to_chuc_id, khach_hang_id, trang_thai, tong_tien)
VALUES
    (101, 10, 1, 'MOI',           200000),
    (102, 10, 1, 'DA_THANH_TOAN', 300000),
    (103, 10, 2, 'DA_THANH_TOAN', 150000),
    (104, 20, 4, 'MOI',           400000),
    (105, 20, 4, 'DA_HUY',        500000),
    (106, 10, 3, 'MOI',           120000);

CREATE TEMP TABLE chi_tiet_don_hang_join (
    id INTEGER PRIMARY KEY,
    don_hang_id INTEGER NOT NULL REFERENCES don_hang_join(id),
    ma_san_pham TEXT NOT NULL,
    so_luong INTEGER NOT NULL CHECK (so_luong > 0)
);

INSERT INTO chi_tiet_don_hang_join
    (id, don_hang_id, ma_san_pham, so_luong)
VALUES
    (1001, 101, 'SP_A', 1),
    (1002, 101, 'SP_B', 2),
    (1003, 102, 'SP_A', 3),
    (1004, 103, 'SP_C', 1),
    (1005, 104, 'SP_A', 1),
    (1006, 105, 'SP_A', 1),
    (1007, 105, 'SP_B', 4);
~~~

Các bảng có số dòng và mức chi tiết (*grain*) khác nhau:

| Bảng | Số dòng | Một dòng đại diện cho | Khóa chính |
| --- | ---: | --- | --- |
| `khach_hang_join` | 6 | Một khách hàng | `id` |
| `don_hang_join` | 6 | Một đơn hàng | `id` |
| `chi_tiet_don_hang_join` | 7 | Một dòng sản phẩm trong đơn | `id` |

Khách An có hai đơn (101, 102); khách Dung có hai đơn (104, 105); khách Em và Lan chưa có đơn; đơn 101 và 105 có hai dòng chi tiết; đơn 106 chưa có dòng chi tiết trong bộ dữ liệu thực hành. Các trường hợp này giúp thấy **INNER JOIN có thể loại hàng không khớp và nhân hàng khớp nhiều lần**.

## 5. INNER JOIN bằng khóa ngoại và khóa chính

Truy vấn lấy mỗi đơn kèm tên khách:

~~~sql
SELECT
    dh.id AS don_hang_id,
    dh.to_chuc_id,
    kh.ten_khach_hang,
    dh.trang_thai,
    dh.tong_tien
FROM don_hang_join AS dh
INNER JOIN khach_hang_join AS kh
    ON dh.khach_hang_id = kh.id
ORDER BY dh.id;
~~~

Kết quả:

| don_hang_id | to_chuc_id | ten_khach_hang | trang_thai | tong_tien |
| ---: | ---: | --- | --- | ---: |
| 101 | 10 | An | MOI | 200000 |
| 102 | 10 | An | DA_THANH_TOAN | 300000 |
| 103 | 10 | Bình | DA_THANH_TOAN | 150000 |
| 104 | 20 | Dung | MOI | 400000 |
| 105 | 20 | Dung | DA_HUY | 500000 |
| 106 | 10 | Chi | MOI | 120000 |

Trong **bộ dữ liệu này**, `kh.id` là khóa chính toàn cục, nên ghép bằng `dh.khach_hang_id = kh.id` xác định duy nhất khách hàng đúng cho mỗi đơn. Bảng đơn có sáu hàng và mỗi đơn có một khách hàng tồn tại, nên kết quả có **sáu dòng**.

**Tại sao tên An xuất hiện hai lần?** Vì truy vấn hiện có mức chi tiết **một dòng cho mỗi đơn hàng**, không phải mỗi khách hàng. An có hai đơn nên tên An lặp hai lần — đó là dữ liệu hợp lệ, không phải lỗi trùng.

### 5.1. Ghép đủ khóa để thể hiện phạm vi tổ chức

Vì lược đồ còn có cặp khóa ngoại `(to_chuc_id, khach_hang_id)`, có thể viết rõ cả hai thành phần:

~~~sql
SELECT
    dh.id AS don_hang_id,
    dh.to_chuc_id,
    kh.ten_khach_hang
FROM don_hang_join AS dh
INNER JOIN khach_hang_join AS kh
    ON dh.to_chuc_id = kh.to_chuc_id
   AND dh.khach_hang_id = kh.id
ORDER BY dh.id;
~~~

Với bảng này, kết quả giống truy vấn chỉ ghép `id`, vì `kh.id` đã duy nhất trên toàn bảng và ràng buộc khóa ngoại ghép bảo đảm mỗi đơn trỏ tới khách trong cùng tổ chức. Viết đủ cặp khóa giúp **biểu diễn rõ bất biến theo tổ chức**; quan trọng hơn, ở những mô hình mà mã khách chỉ duy nhất *trong từng tổ chức*, ghép đủ thành phần là **bắt buộc để tránh ghép nhầm**.

### 5.2. Thứ tự hai bảng trong INNER JOIN

~~~sql
FROM don_hang_join AS dh
INNER JOIN khach_hang_join AS kh
    ON dh.khach_hang_id = kh.id
~~~

và:

~~~sql
FROM khach_hang_join AS kh
INNER JOIN don_hang_join AS dh
    ON kh.id = dh.khach_hang_id
~~~

đều ghép các cặp hàng khớp theo cùng một phép bằng trong ví dụ. Về tập các cặp hàng, INNER JOIN có tính giao hoán theo ngữ nghĩa quan hệ thông thường; tuy nhiên **thứ tự cột khi `SELECT *`**, thứ tự dòng hiển thị khi thiếu `ORDER BY`, và kế hoạch thực thi có thể khác. Khi cần thứ tự ổn định, luôn dùng `ORDER BY`; khi cần giao diện cột ổn định, liệt kê cột tường minh.

## 6. INNER JOIN giữ hàng khớp và loại hàng không khớp

Xét từ phía bảng khách hàng:

~~~sql
SELECT
    kh.id AS khach_hang_id,
    kh.ten_khach_hang,
    dh.id AS don_hang_id
FROM khach_hang_join AS kh
INNER JOIN don_hang_join AS dh
    ON dh.khach_hang_id = kh.id
ORDER BY kh.id, dh.id;
~~~

Kết quả có sáu dòng đơn hàng, nhưng chỉ đại diện cho **bốn** khách đã có đơn: An, Bình, Chi, Dung. Khách Em và Lan không xuất hiện, vì **không có hàng đơn hàng nào khớp khóa của họ**.

Đây là đặc điểm cơ bản:

> `INNER JOIN` giữ **các tổ hợp hàng có điều kiện `ON` nhận `TRUE`**, không giữ các hàng bên trái hoặc bên phải mà không có cặp khớp.

Nếu yêu cầu là “danh sách khách đã mua ít nhất một lần”, INNER JOIN có thể kết hợp với `DISTINCT` hoặc dùng `EXISTS`:

~~~sql
SELECT DISTINCT
    kh.id,
    kh.ten_khach_hang
FROM khach_hang_join AS kh
INNER JOIN don_hang_join AS dh
    ON dh.khach_hang_id = kh.id
ORDER BY kh.id;
~~~

Kết quả gồm An, Bình, Chi, Dung — mỗi khách một dòng.

Hoặc:

~~~sql
SELECT kh.id, kh.ten_khach_hang
FROM khach_hang_join AS kh
WHERE EXISTS (
    SELECT 1
    FROM don_hang_join AS dh
    WHERE dh.khach_hang_id = kh.id
)
ORDER BY kh.id;
~~~

`EXISTS` trực tiếp kiểm tra “có ít nhất một đơn hay không” mà không tạo nhiều dòng rồi loại trùng. Khi không cần cột đơn hàng, cách này thường phản ánh ý định rõ hơn. Không nên khẳng định nó luôn nhanh hơn; hiệu năng tùy chỉ mục, dữ liệu và bộ tối ưu hóa.

### 6.1. Khi cần giữ khách chưa có đơn thì sao?

Nếu yêu cầu đổi thành “**mọi khách hàng**, kể cả người chưa có đơn”, `INNER JOIN` không đủ. Cần cân nhắc `LEFT JOIN`:

~~~sql
SELECT
    kh.id,
    kh.ten_khach_hang,
    dh.id AS don_hang_id
FROM khach_hang_join AS kh
LEFT JOIN don_hang_join AS dh
    ON dh.khach_hang_id = kh.id
ORDER BY kh.id, dh.id;
~~~

Khách Em và Lan sẽ được giữ lại với `don_hang_id = NULL` ở các dòng mở rộng. Đó là **một yêu cầu khác** với INNER JOIN; không nên coi việc INNER JOIN không trả khách chưa mua là lỗi nếu truy vấn vốn chỉ tìm khách có đơn.

### 6.2. Hàng con không có cha và vai trò FOREIGN KEY

Trong bộ dữ liệu trên, `don_hang_join.khach_hang_id` là `NOT NULL` và được bảo vệ bởi khóa ngoại đến bảng khách. Vì vậy không thể chèn bình thường một đơn có khách không tồn tại trong phạm vi được tham chiếu. Ví dụ:

~~~sql
-- Dự kiến bị từ chối vì không có khách id 999 thuộc tổ chức 10:
-- INSERT INTO don_hang_join
--     (id, to_chuc_id, khach_hang_id, trang_thai, tong_tien)
-- VALUES (199, 10, 999, 'MOI', 100000);
~~~

Nếu database **không có hoặc tạm thời chưa thực thi** khóa ngoại, dữ liệu mồ côi (*orphan*) có thể tồn tại; khi INNER JOIN đơn với khách, những hàng đơn không có khách khớp sẽ không xuất hiện. Điều này có thể khiến báo cáo đếm ít hơn bảng gốc.

Nếu cột khóa ngoại cho phép `NULL`, biểu thức `dh.khach_hang_id = kh.id` có kết quả `UNKNOWN` cho hàng có khóa ngoại `NULL`, nên hàng đó **không có cặp khớp** theo phép bằng thông thường.

## 7. Một–một, một–nhiều và nhiều–nhiều quyết định số dòng JOIN

Việc JOIN không “giữ nguyên số dòng của bảng trái” như một quy tắc chung. Số dòng phụ thuộc **số cặp hàng thỏa điều kiện**.

### 7.1. Ghép từ đơn hàng sang khách: nhiều–một

Mỗi đơn có một `khach_hang_id`, và `kh.id` là duy nhất:

~~~sql
SELECT dh.id, kh.ten_khach_hang
FROM don_hang_join AS dh
INNER JOIN khach_hang_join AS kh
    ON dh.khach_hang_id = kh.id;
~~~

Mỗi đơn có **tối đa một** khách khớp. Vì dữ liệu hiện tại có đầy đủ khóa ngoại hợp lệ, sáu đơn tạo sáu dòng.

### 7.2. Ghép từ khách sang đơn: một–nhiều

~~~sql
SELECT kh.id, kh.ten_khach_hang, dh.id AS don_hang_id
FROM khach_hang_join AS kh
INNER JOIN don_hang_join AS dh
    ON kh.id = dh.khach_hang_id;
~~~

Khách An và Dung mỗi người tạo **hai dòng** do có hai đơn. Khách chưa có đơn tạo **không dòng nào**. Grain của kết quả là đơn hàng kèm thông tin khách, dù phần `FROM` bắt đầu bằng bảng khách.

### 7.3. Ghép một đơn sang nhiều dòng chi tiết

~~~sql
SELECT
    dh.id AS don_hang_id,
    ct.id AS chi_tiet_id,
    ct.ma_san_pham,
    ct.so_luong
FROM don_hang_join AS dh
INNER JOIN chi_tiet_don_hang_join AS ct
    ON ct.don_hang_id = dh.id
ORDER BY dh.id, ct.id;
~~~

Kết quả:

| don_hang_id | chi_tiet_id | ma_san_pham | so_luong |
| ---: | ---: | --- | ---: |
| 101 | 1001 | SP_A | 1 |
| 101 | 1002 | SP_B | 2 |
| 102 | 1003 | SP_A | 3 |
| 103 | 1004 | SP_C | 1 |
| 104 | 1005 | SP_A | 1 |
| 105 | 1006 | SP_A | 1 |
| 105 | 1007 | SP_B | 4 |

Có **bảy dòng**, vì tổng số dòng chi tiết là bảy. Đơn 101 và 105 xuất hiện hai lần, còn đơn 106 **không xuất hiện** vì chưa có dòng chi tiết.

Đây là điểm cần nhớ trước khi kết hợp dữ liệu để báo cáo: nếu truy vấn cần **một dòng trên một đơn**, JOIN đến bảng chi tiết mà chưa tổng hợp sẽ biến kết quả thành **mỗi dòng chi tiết một dòng**.

### 7.4. Nhiều–nhiều qua bảng trung gian

Một sản phẩm có thể xuất hiện trong nhiều đơn; một đơn có thể chứa nhiều sản phẩm. Quan hệ đó thường được thiết kế bằng **bảng trung gian** `chi_tiet_don_hang`:

~~~mermaid
flowchart LR
    D["don_hang\nPK: id"] -->|"1..n dòng chi tiết"| CT["chi_tiet_don_hang\nFK: don_hang_id\nFK: ma_san_pham"]
    P["san_pham\nPK: ma_san_pham"] -->|"1..n dòng chi tiết"| CT
~~~

Trong dữ liệu thực hành, `ma_san_pham` là giá trị chuỗi và **chưa** khai báo khóa ngoại đến bảng `san_pham`. Sơ đồ thể hiện mô hình quan hệ thường gặp khi ứng dụng có bảng sản phẩm và ràng buộc tương ứng, không hàm ý ví dụ đã tạo bảng sản phẩm. Nếu cần truy vấn tên sản phẩm, phải có bảng danh mục và điều kiện nối `ct.ma_san_pham = sp.ma_san_pham` với khóa/kiểu dữ liệu phù hợp.

## 8. Ghép ba bảng và xác định mức chi tiết kết quả

Kết hợp khách hàng, đơn hàng và chi tiết:

~~~sql
SELECT
    kh.ten_khach_hang,
    dh.id AS don_hang_id,
    ct.ma_san_pham,
    ct.so_luong
FROM khach_hang_join AS kh
INNER JOIN don_hang_join AS dh
    ON dh.to_chuc_id = kh.to_chuc_id
   AND dh.khach_hang_id = kh.id
INNER JOIN chi_tiet_don_hang_join AS ct
    ON ct.don_hang_id = dh.id
ORDER BY dh.id, ct.id;
~~~

Một dòng kết quả bây giờ tương ứng với **một dòng chi tiết đơn hàng kèm thông tin đơn và khách**. Có bảy dòng — không phải sáu khách hoặc sáu đơn. Khách Chi, dù có đơn 106, **không xuất hiện** vì đơn 106 chưa có chi tiết; Em và Lan cũng không xuất hiện vì chưa có đơn.

Có thể minh họa bằng sơ đồ chuỗi:

~~~mermaid
flowchart TD
    A["6 khách hàng"] --> B["JOIN đơn bằng FK = PK"]
    B --> C["6 hàng khớp: 6 đơn của 4 khách"]
    C --> D["JOIN chi tiết bằng don_hang_id = id"]
    D --> E["7 hàng khớp: 7 dòng chi tiết của 5 đơn"]
    E --> F["Mức chi tiết: 1 dòng / chi tiết đơn"]
~~~

**Không dùng `SELECT DISTINCT kh.ten_khach_hang, dh.id, ct.ma_san_pham` như một cách chung để sửa số dòng.** Nếu một đơn có hai dòng cùng mã sản phẩm nhưng các chi tiết khác nhau, `DISTINCT` có thể loại mất những dòng cần cho phép tính. Ngược lại, nếu chọn cả khóa chi tiết `ct.id`, các dòng vốn đã khác nhau, `DISTINCT` không giảm dòng nào.

### 8.1. Muốn một dòng trên mỗi đơn thì GROUP BY

Ví dụ tính tổng số lượng của các đơn **có chi tiết**:

~~~sql
SELECT
    dh.id AS don_hang_id,
    kh.ten_khach_hang,
    SUM(ct.so_luong) AS tong_so_luong
FROM don_hang_join AS dh
INNER JOIN khach_hang_join AS kh
    ON kh.to_chuc_id = dh.to_chuc_id
   AND kh.id = dh.khach_hang_id
INNER JOIN chi_tiet_don_hang_join AS ct
    ON ct.don_hang_id = dh.id
GROUP BY dh.id, kh.ten_khach_hang
ORDER BY dh.id;
~~~

Kết quả có năm đơn (101–105). Với đơn 101, tổng số lượng là `3`; với đơn 105 là `5`. Đơn 106 không có chi tiết nên INNER JOIN loại khỏi phép nhóm.

Nếu cần **tất cả sáu đơn**, kể cả đơn chưa có chi tiết, phải cân nhắc `LEFT JOIN` từ đơn sang chi tiết và dùng `COALESCE(SUM(ct.so_luong), 0)` khi nghiệp vụ xem đơn chưa có chi tiết là tổng số lượng 0. Đó là một thay đổi về phạm vi kết quả, không đơn thuần thay `INNER` bằng `LEFT` mà không xem xét `NULL`.

### 8.2. Muốn một dòng mỗi khách thì tổng hợp ở grain khách

~~~sql
SELECT
    kh.id AS khach_hang_id,
    kh.ten_khach_hang,
    COUNT(dh.id) AS so_don,
    SUM(dh.tong_tien) AS tong_gia_tri_don
FROM khach_hang_join AS kh
INNER JOIN don_hang_join AS dh
    ON dh.khach_hang_id = kh.id
GROUP BY kh.id, kh.ten_khach_hang
ORDER BY kh.id;
~~~

Kết quả:

| khach_hang_id | ten_khach_hang | so_don | tong_gia_tri_don |
| ---: | --- | ---: | ---: |
| 1 | An | 2 | 500000 |
| 2 | Bình | 1 | 150000 |
| 3 | Chi | 1 | 120000 |
| 4 | Dung | 2 | 900000 |

Em và Lan không có đơn nên không xuất hiện. Số tiền ở đây là **tổng giá trị đơn** lưu trong cột `tong_tien`, không tự động là doanh thu đã ghi nhận; cần thêm điều kiện trạng thái/hoàn tiền nếu nghiệp vụ yêu cầu.

## 9. Điều kiện ghép phải dựa trên khóa, không dựa trên vẻ giống nhau

Một lỗi nguy hiểm là ghép hai bảng theo cột trông có liên quan nhưng **không định danh đúng hàng**.

### 9.1. Ghép bằng tên thay vì ID

Không nên viết:

~~~sql
-- Ví dụ sai về thiết kế nếu hai bảng đều có tên khách:
-- ON dh.ten_khach_hang = kh.ten_khach_hang
~~~

Tên khách có thể trùng, thay đổi, có khoảng trắng, dấu tiếng Việt, cách viết khác nhau hoặc giá trị `NULL`. Ghép theo tên có thể tạo nhiều cặp sai hoặc bỏ sót đúng khách. Khi đã có quan hệ `don_hang.khach_hang_id -> khach_hang.id`, hãy dùng **khóa ổn định và được DBMS bảo vệ**.

### 9.2. Ghép nhầm hai khóa chính

Đây là lỗi trông hợp lý nhưng sai ý nghĩa:

~~~sql
-- Sai quan hệ:
-- FROM don_hang_join AS dh
-- JOIN khach_hang_join AS kh
--   ON dh.id = kh.id
~~~

`dh.id` là mã **đơn hàng**, còn `kh.id` là mã **khách hàng**. Hai cột cùng tên `id` không có nghĩa chúng có quan hệ. Điều kiện đúng là:

~~~sql
ON dh.khach_hang_id = kh.id
~~~

Hãy đọc **khóa ngoại trong schema** để xác định cột dùng nối, thay vì ghép các cột có kiểu dữ liệu giống nhau hoặc cùng tên.

### 9.3. Khóa ghép: phải dùng đủ thành phần

Giả sử một hệ thống khác cấp mã khách **theo từng tổ chức**, nên cùng mã `KH001` có thể tồn tại ở cả tổ chức 10 và 20. Tạo bảng minh họa độc lập:

~~~sql
CREATE TEMP TABLE khach_theo_to_chuc (
    to_chuc_id INTEGER NOT NULL,
    ma_khach TEXT NOT NULL,
    ten TEXT NOT NULL,
    PRIMARY KEY (to_chuc_id, ma_khach)
);

INSERT INTO khach_theo_to_chuc
    (to_chuc_id, ma_khach, ten)
VALUES
    (10, 'KH001', 'An'),
    (20, 'KH001', 'Dung'),
    (10, 'KH002', 'Bình');

CREATE TEMP TABLE don_theo_to_chuc (
    id INTEGER PRIMARY KEY,
    to_chuc_id INTEGER NOT NULL,
    ma_khach TEXT NOT NULL,
    CONSTRAINT fk_don_khach_ma_ghep
        FOREIGN KEY (to_chuc_id, ma_khach)
        REFERENCES khach_theo_to_chuc(to_chuc_id, ma_khach)
);

INSERT INTO don_theo_to_chuc (id, to_chuc_id, ma_khach)
VALUES (201, 10, 'KH001'), (202, 20, 'KH001'), (203, 10, 'KH002');
~~~

Nếu JOIN **chỉ bằng `ma_khach`**:

~~~sql
SELECT d.id AS don_id, d.to_chuc_id, k.to_chuc_id AS to_chuc_khach, k.ten
FROM don_theo_to_chuc AS d
INNER JOIN khach_theo_to_chuc AS k
    ON d.ma_khach = k.ma_khach
ORDER BY d.id, k.to_chuc_id;
~~~

Đơn 201 thuộc tổ chức 10 và mang mã `KH001`, nhưng sẽ khớp **cả An thuộc tổ chức 10 lẫn Dung thuộc tổ chức 20**. Đơn 202 cũng khớp cả hai. Kết quả có **năm dòng** thay vì ba: một trường hợp **nhân dòng và ghép sai phạm vi tổ chức**.

Điều kiện đúng:

~~~sql
SELECT
    d.id AS don_id,
    d.to_chuc_id,
    k.ten AS ten_khach
FROM don_theo_to_chuc AS d
INNER JOIN khach_theo_to_chuc AS k
    ON d.to_chuc_id = k.to_chuc_id
   AND d.ma_khach = k.ma_khach
ORDER BY d.id;
~~~

Trả đúng ba dòng:

| don_id | to_chuc_id | ten_khach |
| ---: | ---: | --- |
| 201 | 10 | An |
| 202 | 20 | Dung |
| 203 | 10 | Bình |

**Nguyên tắc:** nếu khóa tham chiếu là **tổ hợp `(A, B)`**, điều kiện ghép cần so khớp **cả `A` và `B`** theo đúng quan hệ. Dùng thiếu một thành phần có thể cho kết quả tưởng hợp lệ về cú pháp nhưng sai dữ liệu và nguy hiểm trong hệ thống nhiều khách hàng/tổ chức.

### 9.4. Chỉ số mã giống nhau không đủ xác định quan hệ

Một bảng dòng hàng có `don_hang_id = 101`, trong khi bảng khác có `khach_hang_id = 101`: hai giá trị số bằng nhau không tạo quan hệ tự động. Phải xác nhận **ý nghĩa và phạm vi của cột**, đặc biệt trong những hệ thống có nhiều bảng tự sinh ID bắt đầu từ 1.

## 10. Dùng ON, USING và cách viết WHERE cũ

### 10.1. Cách viết rõ ràng nên ưu tiên: INNER JOIN ... ON

~~~sql
SELECT dh.id, kh.ten_khach_hang
FROM don_hang_join AS dh
INNER JOIN khach_hang_join AS kh
    ON dh.khach_hang_id = kh.id;
~~~

Ưu điểm là **mối quan hệ được đặt ngay cạnh bảng được ghép**, giúp đọc và bảo trì dễ hơn khi thêm nhiều bảng.

### 10.2. USING khi hai bên có cột cùng tên và cùng ý nghĩa

`USING (ten_cot)` là dạng rút gọn mà một số DBMS hỗ trợ khi **cột dùng ghép có cùng tên ở cả hai bảng**. Ví dụ hai bảng minh họa độc lập:

~~~sql
CREATE TEMP TABLE phong_ban_join (
    phong_ban_id INTEGER PRIMARY KEY,
    ten_phong TEXT NOT NULL
);

CREATE TEMP TABLE nhan_vien_join (
    id INTEGER PRIMARY KEY,
    phong_ban_id INTEGER,
    ten_nhan_vien TEXT NOT NULL
);

INSERT INTO phong_ban_join VALUES
    (10, 'Kỹ thuật'),
    (20, 'Kinh doanh');

INSERT INTO nhan_vien_join VALUES
    (1, 10, 'An'),
    (2, 10, 'Bình'),
    (3, 20, 'Chi');

SELECT phong_ban_id, nv.ten_nhan_vien, pb.ten_phong
FROM nhan_vien_join AS nv
INNER JOIN phong_ban_join AS pb
    USING (phong_ban_id)
ORDER BY nv.id;
~~~

Ở PostgreSQL, `USING (phong_ban_id)` tương đương về điều kiện khớp với:

~~~sql
ON nv.phong_ban_id = pb.phong_ban_id
~~~

khi hai bên dùng cùng tên cột. Với `SELECT *`, `USING` còn ảnh hưởng cách **trình bày cột kết quả**: cột dùng `USING` thường chỉ xuất hiện một lần, khác với `ON` để lại hai cột nguồn. `USING` không phù hợp trực tiếp cho `dh.khach_hang_id = kh.id` vì tên cột khác nhau.

Không phải mọi DBMS đều hỗ trợ `USING` theo cùng cú pháp: PostgreSQL, MySQL và Oracle hỗ trợ những dạng tương ứng; SQL Server thường dùng `ON` thay vì `USING`.

### 10.3. Điều kiện JOIN viết trong WHERE kiểu cũ

Một số mã SQL cũ:

~~~sql
SELECT dh.id, kh.ten_khach_hang
FROM don_hang_join AS dh, khach_hang_join AS kh
WHERE dh.khach_hang_id = kh.id;
~~~

Về mặt tập cặp hàng, câu này có thể cho kết quả giống INNER JOIN bằng khóa ở trên. Tuy nhiên dấu phẩy giữa các bảng dễ khiến người đọc bỏ sót điều kiện ghép, nhất là khi có nhiều bảng, và một thiếu sót có thể tạo **tích Descartes**. Cách viết `INNER JOIN ... ON` tường minh thường nên được ưu tiên trong mã mới.

## 11. CROSS JOIN và tác hại của thiếu điều kiện ghép

Khi không có quan hệ giới hạn số cặp, mỗi hàng bên trái có thể được ghép với **mọi** hàng bên phải:

~~~sql
SELECT
    dh.id AS don_id,
    kh.id AS khach_id
FROM don_hang_join AS dh
CROSS JOIN khach_hang_join AS kh;
~~~

Với sáu đơn và sáu khách, `CROSS JOIN` tạo **36 cặp**. Đây là thao tác hợp lệ khi mục đích thật là mọi tổ hợp (ví dụ tạo bảng tất cả cặp sản phẩm–màu sắc), nhưng sai nếu định hiển thị tên khách theo đơn.

### 11.1. INNER JOIN với điều kiện luôn đúng

~~~sql
SELECT COUNT(*) AS so_cap
FROM don_hang_join AS dh
INNER JOIN khach_hang_join AS kh
    ON TRUE;
~~~

Kết quả là `36` trong bộ dữ liệu mẫu, giống `CROSS JOIN`. Câu SQL có chữ `INNER JOIN` **không tự bảo đảm** điều kiện ghép đã đúng; **nội dung `ON`** mới quyết định hàng nào khớp.

### 11.2. Nguy cơ tăng bùng nổ số dòng

Nếu bảng A có 100.000 hàng và bảng B có 50.000 hàng, tích Descartes lý thuyết có thể có **5 tỷ cặp** trước các phép lọc/giới hạn. Bộ tối ưu hóa có thể áp dụng phép lọc phù hợp sớm hơn, nhưng một JOIN thiếu khóa vẫn có nguy cơ tiêu tốn tài nguyên lớn hoặc làm sai số liệu.

Khi một truy vấn JOIN đột nhiên trả nhiều dòng hơn dự kiến, hãy kiểm tra **điều kiện `ON`**, không vội thêm `DISTINCT` để che triệu chứng.

## 12. NULL trong điều kiện ghép bằng khóa

Điều kiện phổ biến:

~~~sql
ON a.ma_tham_chieu = b.ma
~~~

sử dụng phép so sánh `=`. Trong logic ba giá trị SQL, nếu một bên là `NULL`, phép so sánh thường trả **`UNKNOWN`**, không phải `TRUE`. Vì INNER JOIN chỉ giữ cặp hàng có điều kiện `ON` là `TRUE`, các hàng như vậy không ghép được.

Ví dụ độc lập:

~~~sql
CREATE TEMP TABLE nhom_ma_join (
    id INTEGER PRIMARY KEY,
    ma TEXT
);

CREATE TEMP TABLE nhan_ma_join (
    id INTEGER PRIMARY KEY,
    ma TEXT
);

INSERT INTO nhom_ma_join VALUES (1, 'A'), (2, NULL);
INSERT INTO nhan_ma_join VALUES (10, 'A'), (11, NULL);

SELECT a.id AS id_nhom, b.id AS id_nhan
FROM nhom_ma_join AS a
INNER JOIN nhan_ma_join AS b
    ON a.ma = b.ma
ORDER BY a.id, b.id;
~~~

Kết quả chỉ có cặp `(1, 10)` do `'A' = 'A'`. Hai giá trị `NULL` **không ghép nhau bằng `=`**.

### 12.1. NULL-safe equality không phải luôn đúng cho khóa nghiệp vụ

Trong PostgreSQL, có thể dùng:

~~~sql
ON a.ma IS NOT DISTINCT FROM b.ma
~~~

Biểu thức này coi hai `NULL` như **không khác nhau** cho mục đích so sánh, nên ví dụ trên sẽ có thêm cặp `(2, 11)`. Tuy nhiên:

**Hai giá trị chưa biết không có nghĩa hai thực thể chắc chắn có cùng mã.** Với quan hệ PK/FK, việc ghép mọi bản ghi `NULL` với nhau thường là **sai nghiệp vụ** và có thể gây nhân dòng hàng loạt. Không thay phép nối `=` bằng null-safe equality một cách máy móc; chỉ dùng khi quy tắc nghiệp vụ thật sự định nghĩa hai dấu hiệu thiếu là một khóa ghép hợp lệ.

Một số DBMS có cú pháp so sánh `NULL` an toàn khác nhau. Quan trọng hơn cú pháp là định nghĩa **thế nào là khớp khóa** trong lược đồ.

### 12.2. Tránh COALESCE về một mã giả khi ghép

~~~sql
-- Nguy hiểm nếu mã '-1' có thể là một giá trị thật:
-- ON COALESCE(a.ma, '-1') = COALESCE(b.ma, '-1')
~~~

Cách này có thể làm hai `NULL` khớp nhau và còn khiến `NULL` khớp với **giá trị thật `'-1'`**. Nó có thể gây sai quan hệ, tạo dòng thừa và ảnh hưởng khả năng dùng chỉ mục. Nếu cần xử lý thiếu khóa, nên giải quyết tại mô hình dữ liệu và điều kiện nghiệp vụ tường minh.

## 13. INNER JOIN kết hợp WHERE

Điều kiện `ON` thể hiện **quan hệ ghép**, còn `WHERE` thường dùng để lọc theo yêu cầu:

~~~sql
SELECT
    dh.id AS don_id,
    kh.ten_khach_hang,
    dh.tong_tien
FROM don_hang_join AS dh
INNER JOIN khach_hang_join AS kh
    ON dh.khach_hang_id = kh.id
WHERE dh.to_chuc_id = 10
  AND dh.trang_thai = 'DA_THANH_TOAN'
ORDER BY dh.id;
~~~

Kết quả gồm đơn 102 của An và 103 của Bình. Điều kiện khách thuộc tổ chức nào vẫn có thể được thể hiện trong `ON` khi cần, đặc biệt với khóa ghép và chính sách phạm vi:

~~~sql
FROM don_hang_join AS dh
INNER JOIN khach_hang_join AS kh
    ON kh.to_chuc_id = dh.to_chuc_id
   AND kh.id = dh.khach_hang_id
WHERE dh.to_chuc_id = 10
  AND dh.trang_thai = 'DA_THANH_TOAN'
~~~

### 13.1. AND/OR phải được nhóm đúng

Giả sử yêu cầu là “tổ chức 10, đơn ở trạng thái MỚI hoặc ĐÃ THANH TOÁN”. Viết:

~~~sql
WHERE dh.to_chuc_id = 10
  AND (
      dh.trang_thai = 'MOI'
      OR dh.trang_thai = 'DA_THANH_TOAN'
  )
~~~

Hoặc:

~~~sql
WHERE dh.to_chuc_id = 10
  AND dh.trang_thai IN ('MOI', 'DA_THANH_TOAN')
~~~

Nếu thiếu ngoặc:

~~~sql
-- Dễ sai: OR có thể đưa đơn ngoài tổ chức 10 vào kết quả.
WHERE dh.to_chuc_id = 10
  AND dh.trang_thai = 'MOI'
   OR dh.trang_thai = 'DA_THANH_TOAN'
~~~

`AND` có ưu tiên cao hơn `OR`, khiến các đơn ĐÃ THANH TOÁN thuộc tổ chức khác cũng có thể được chọn. Điều kiện JOIN đúng nhưng **điều kiện lọc sai vẫn làm kết quả sai**. Trong hệ thống đa tổ chức, đây còn là vấn đề phân quyền và cách ly dữ liệu.

### 13.2. INNER JOIN và LEFT JOIN có khác biệt ON/WHERE

Với `INNER JOIN`, biểu thức `dh.trang_thai = 'MOI'` đặt thêm trong `ON` hoặc `WHERE` thường cho cùng các cặp hàng khớp, khi xét các điều kiện thông thường và không có phép xử lý đặc thù.

Nhưng với `LEFT JOIN`, điều kiện trên bảng bên phải trong `ON` quyết định **hàng bên phải nào được ghép**, còn điều kiện trong `WHERE` có thể loại các hàng bên trái không có cặp khớp. Do đó, không chuyển điều kiện từ `ON` sang `WHERE` tùy tiện khi thay đổi loại JOIN. Phần này chủ yếu học INNER JOIN; hãy giữ phân biệt để tránh hình thành thói quen gây lỗi khi học các phép JOIN khác.

## 14. Kiểm tra số dòng và phát hiện JOIN sai

Một số truy vấn hỗ trợ xác nhận **mức chi tiết và quan hệ khóa**.

### 14.1. Đếm dòng trước và sau JOIN

~~~sql
SELECT COUNT(*) AS so_khach
FROM khach_hang_join;
-- 6

SELECT COUNT(*) AS so_don
FROM don_hang_join;
-- 6

SELECT COUNT(*) AS so_dong_sau_join
FROM don_hang_join AS dh
INNER JOIN khach_hang_join AS kh
    ON dh.khach_hang_id = kh.id;
-- 6
~~~

Kết quả bằng sáu ở JOIN thứ ba vì trong dữ liệu mẫu **mọi đơn có đúng một khách khớp**. Không nên kết luận “INNER JOIN luôn trả số dòng bằng bảng bên trái”; đó chỉ là hệ quả của **khóa duy nhất phía khách và tính hợp lệ của khóa ngoại phía đơn** trong trường hợp này.

### 14.2. Đếm tổng dòng và số khóa khác biệt

~~~sql
SELECT
    COUNT(*) AS so_dong,
    COUNT(DISTINCT kh.id) AS so_khach,
    COUNT(DISTINCT dh.id) AS so_don
FROM khach_hang_join AS kh
INNER JOIN don_hang_join AS dh
    ON dh.khach_hang_id = kh.id;
~~~

Kết quả:

| so_dong | so_khach | so_don |
| ---: | ---: | ---: |
| 6 | 4 | 6 |

Số dòng bằng số đơn; số khách nhỏ hơn vì một khách có nhiều đơn. Đây là bằng chứng hữu ích để hiểu grain, không phải chứng minh tổng quát rằng mọi bản ghi được ghép đúng: trong dữ liệu thực, các dòng bị thiếu và dòng nhân bản có thể tình cờ làm số đếm tổng bằng dự kiến.

### 14.3. Tìm đơn bị mất khi INNER JOIN

Nếu không có khóa ngoại hoặc nghi dữ liệu không nhất quán, có thể dùng `LEFT JOIN` để dò **đơn không có khách khớp**:

~~~sql
SELECT
    dh.id AS don_hang_id,
    dh.khach_hang_id
FROM don_hang_join AS dh
LEFT JOIN khach_hang_join AS kh
    ON dh.to_chuc_id = kh.to_chuc_id
   AND dh.khach_hang_id = kh.id
WHERE kh.id IS NULL;
~~~

Với bộ dữ liệu hiện tại kết quả rỗng, bởi khóa ngoại ghép đang hợp lệ. Trong dữ liệu không có ràng buộc tương ứng, câu này giúp phát hiện đơn không thể ghép với một khách khớp theo điều kiện đã chọn. Lưu ý `kh.id` là khóa chính không `NULL`, nên kiểm tra `IS NULL` trên cột đó là dấu hiệu tin cậy cho việc không có cặp khớp ở `LEFT JOIN`.

### 14.4. Tìm khóa ghép không duy nhất bên được coi là “một”

Giả sử dùng một bảng danh mục khách không có ràng buộc duy nhất:

~~~sql
SELECT
    to_chuc_id,
    ma_khach,
    COUNT(*) AS so_hang
FROM khach_theo_to_chuc
GROUP BY to_chuc_id, ma_khach
HAVING COUNT(*) > 1;
~~~

Với bộ dữ liệu đúng schema, truy vấn rỗng vì `PRIMARY KEY (to_chuc_id, ma_khach)` đã ngăn trùng. Nhưng trên nguồn dữ liệu nhập vào chưa có khóa hoặc bảng staging, cách đếm này giúp tìm những **bộ khóa xuất hiện nhiều hơn một lần** trước khi dùng chúng làm phía “một” của JOIN.

**Không nên dùng `SELECT DISTINCT` để che những cặp sai do điều kiện JOIN thiếu thành phần**: nó có thể khiến số dòng trông hợp lý nhưng vẫn liên kết nhầm thực thể và tính tổng sai.

## 15. JOIN có thể làm sai SUM và COUNT nếu không hiểu grain

Một lỗi điển hình là tính tổng cột thuộc **bảng đơn hàng** sau khi JOIN sang **bảng chi tiết** mà không xét việc mỗi đơn có nhiều chi tiết.

~~~sql
SELECT
    SUM(dh.tong_tien) AS tong_co_the_bi_nhan
FROM don_hang_join AS dh
INNER JOIN chi_tiet_don_hang_join AS ct
    ON ct.don_hang_id = dh.id;
~~~

Trong bộ dữ liệu:

- Đơn 101 có hai dòng chi tiết nên `tong_tien = 200000` bị cộng **hai lần**.
- Đơn 105 có hai dòng chi tiết nên `tong_tien = 500000` bị cộng **hai lần**.
- Đơn 106 không có chi tiết nên không được cộng.

Kết quả biểu thức trên là **2.250.000**, không phải tổng của sáu đơn. Tổng cột `tong_tien` trên toàn bộ bảng đơn hàng là **1.670.000**; tổng của **năm đơn có chi tiết** là **1.550.000**. Sự khác biệt không phải lỗi của `SUM`, mà là do **JOIN đổi mức chi tiết của tập hàng**.

### 15.1. Tính tổng tại grain đúng

Nếu yêu cầu là **tổng giá trị tất cả đơn**, không cần JOIN chi tiết:

~~~sql
SELECT SUM(tong_tien) AS tong_gia_tri
FROM don_hang_join;
-- 1670000
~~~

Nếu yêu cầu là **tổng giá trị các đơn có ít nhất một dòng chi tiết**, có thể dùng `EXISTS`:

~~~sql
SELECT SUM(dh.tong_tien) AS tong_gia_tri_don_co_chi_tiet
FROM don_hang_join AS dh
WHERE EXISTS (
    SELECT 1
    FROM chi_tiet_don_hang_join AS ct
    WHERE ct.don_hang_id = dh.id
);
-- 1550000
~~~

Hoặc lấy danh sách đơn có chi tiết khác biệt trước rồi tổng hợp theo đơn. Điều quan trọng là chỉ cộng **mỗi đơn một lần** khi số tiền thuộc grain đơn hàng.

### 15.2. Đừng mặc định SUM(DISTINCT tong_tien) sửa được

~~~sql
-- Không nên dùng như công thức tổng giá trị đơn:
-- SUM(DISTINCT dh.tong_tien)
~~~

`SUM(DISTINCT tong_tien)` loại những **giá trị tiền bằng nhau**, không loại theo **ID đơn hàng**. Nếu hai đơn khác nhau cùng có số tiền 200.000, một trong hai giá trị sẽ bị bỏ khỏi phép cộng dù đó là **hai đơn hợp lệ**. Cần tổng hợp hoặc chọn dòng ở **khóa đơn hàng**, không phải theo giá trị tiền.

### 15.3. Ghép nhiều bảng con 1–n cùng một bảng cha

Giả sử ngoài chi tiết đơn còn có nhiều lần thử thanh toán hoặc nhiều sự kiện giao hàng. JOIN cùng lúc hai bảng con 1–n vào đơn có thể tạo **tích số dòng** giữa các hàng con: một đơn có 3 dòng chi tiết và 2 lần thanh toán có thể sinh **6 dòng**.

Nếu cần hai chỉ tiêu độc lập, thường nên **tổng hợp mỗi bảng con về một dòng trên mỗi đơn trước khi JOIN**:

~~~sql
-- Mẫu khái quát; bang_thanh_toan chỉ là tên minh họa.
WITH so_luong_theo_don AS (
    SELECT don_hang_id, SUM(so_luong) AS tong_so_luong
    FROM chi_tiet_don_hang_join
    GROUP BY don_hang_id
),
tien_thanh_toan_theo_don AS (
    SELECT don_hang_id, SUM(so_tien) AS tong_da_thanh_toan
    FROM bang_thanh_toan
    GROUP BY don_hang_id
)
SELECT
    dh.id,
    ct.tong_so_luong,
    tt.tong_da_thanh_toan
FROM don_hang_join AS dh
INNER JOIN so_luong_theo_don AS ct
    ON ct.don_hang_id = dh.id
INNER JOIN tien_thanh_toan_theo_don AS tt
    ON tt.don_hang_id = dh.id;
~~~

Truy vấn khái quát này cần bảng `bang_thanh_toan(don_hang_id, so_tien)` tồn tại mới chạy được. Nó minh họa một nguyên tắc: **mỗi CTE đã đưa dữ liệu về grain đơn hàng**, nên JOIN các kết quả tổng hợp không nhân số tiền theo số dòng chi tiết. Với `INNER JOIN`, chỉ các đơn có cả chi tiết lẫn thanh toán sẽ được giữ; nếu muốn giữ các đơn thiếu một trong hai loại dữ liệu thì cần `LEFT JOIN` và cách xử lý `NULL` phù hợp.

## 16. SELF JOIN: ghép bảng với chính nó bằng khóa

Một bảng nhân viên có thể lưu `quan_ly_id` tham chiếu `id` của một nhân viên khác trong **chính bảng đó**:

~~~sql
CREATE TEMP TABLE nhan_vien_tu_ghep (
    id INTEGER PRIMARY KEY,
    ten TEXT NOT NULL,
    quan_ly_id INTEGER REFERENCES nhan_vien_tu_ghep(id)
);

INSERT INTO nhan_vien_tu_ghep (id, ten, quan_ly_id)
VALUES
    (1, 'An', NULL),
    (2, 'Bình', 1),
    (3, 'Chi', 1),
    (4, 'Dung', 2);
~~~

Để tìm nhân viên có quản lý và tên người quản lý:

~~~sql
SELECT
    nv.id,
    nv.ten AS ten_nhan_vien,
    ql.ten AS ten_quan_ly
FROM nhan_vien_tu_ghep AS nv
INNER JOIN nhan_vien_tu_ghep AS ql
    ON nv.quan_ly_id = ql.id
ORDER BY nv.id;
~~~

Kết quả gồm Bình → An, Chi → An và Dung → Bình. An không có quản lý (`quan_ly_id = NULL`) nên không xuất hiện trong INNER JOIN.

**Self JOIN vẫn là phép ghép bằng khóa**, nhưng phải đặt **hai bí danh khác nhau** (`nv` và `ql`) để phân biệt vai trò của hai lần tham chiếu bảng. Nếu yêu cầu hiển thị cả nhân viên cao nhất chưa có quản lý, dùng `LEFT JOIN` thay vì `INNER JOIN`.

## 17. INNER JOIN và các loại JOIN khác

Để chọn đúng, cần biết INNER JOIN thuộc một nhóm phép ghép:

| Loại JOIN | Ý nghĩa trọng tâm | Khi thường dùng |
| --- | --- | --- |
| **INNER JOIN** | Chỉ giữ những cặp hàng có điều kiện ghép đúng | Đơn hàng kèm tên khách tồn tại |
| **LEFT JOIN** | Giữ mọi hàng bảng trái, kể cả không có hàng phải khớp | Danh sách mọi khách, kể cả chưa mua |
| **RIGHT JOIN** | Giữ mọi hàng bảng phải, kể cả không có hàng trái khớp | Có thể viết lại bằng LEFT JOIN khi đổi thứ tự bảng |
| **FULL OUTER JOIN** | Giữ cả các hàng không khớp ở hai phía | Đối soát hai nguồn; hỗ trợ tùy DBMS |
| **CROSS JOIN** | Tạo mọi tổ hợp hai bảng | Sinh tổ hợp hoặc thao tác có chủ đích |

Trong bài này, mục tiêu là hiểu **INNER JOIN**: mỗi dòng kết quả tồn tại vì có **một cặp hàng khớp khóa**. Khi bài toán yêu cầu giữ bản ghi không khớp, cần chuyển sang loại JOIN khác hoặc dùng `NOT EXISTS` để tìm phần thiếu.

### 17.1. INNER JOIN không phải phép giao hai bảng nguyên vẹn

Đôi khi `INNER JOIN` được diễn giải là “giao giữa hai bảng”. Cách nói này hữu ích như một hình ảnh ban đầu, nhưng dễ gây hiểu nhầm: hai bảng có thể có **bộ cột khác nhau**, và INNER JOIN tạo **cặp hàng khớp theo điều kiện**, không chỉ trả các hàng giống hệt xuất hiện ở cả hai bảng như phép giao tập hợp `INTERSECT`.

Một khách có hai đơn sẽ xuất hiện ở **hai cặp hàng**, dù bản ghi khách đó chỉ có một trong bảng khách. Đây là lý do nên luôn hình dung **quan hệ ghép và số cặp khớp**, thay vì chỉ vẽ hai tập hợp giao nhau.

## 18. Hiệu năng INNER JOIN: khóa, chỉ mục và kế hoạch thực thi

Một `INNER JOIN` viết đúng cú pháp có thể xử lý bảng rất lớn. Hiệu năng phụ thuộc vào kích thước bảng, mức phân bố khóa, điều kiện lọc, chỉ mục và thuật toán do bộ tối ưu hóa lựa chọn.

### 18.1. Chỉ mục hỗ trợ tra cứu theo khóa

- Khóa chính `khach_hang.id` thường được bảo vệ bằng một chỉ mục duy nhất.
- Với truy vấn ghép `don_hang.khach_hang_id = khach_hang.id`, **index trên khóa ngoại ở bảng đơn hàng** có thể hữu ích khi tra cứu các đơn của một khách, lọc từ bảng khách hoặc khi thực hiện những thao tác ràng buộc tham chiếu.
- Trong PostgreSQL, khai báo `FOREIGN KEY` **không tự động tạo index cho cột khóa ngoại ở bảng con**. Có thể cân nhắc tạo:

~~~sql
CREATE INDEX idx_don_hang_join_khach
ON don_hang_join (khach_hang_id);
~~~

Với mô hình khóa ghép và truy vấn luôn giới hạn tổ chức:

~~~sql
CREATE INDEX idx_don_hang_join_theo_to_chuc_khach
ON don_hang_join (to_chuc_id, khach_hang_id);
~~~

Hai index chỉ là **ví dụ thiết kế**, không phải lời khuyên tạo cả hai trên mọi bảng. Chỉ mục có chi phí lưu trữ và cập nhật; lựa chọn thứ tự cột và số lượng index nên dựa trên truy vấn thường gặp, điều kiện lọc và kế hoạch thực tế. Với các bảng tạm chỉ có vài dòng như ở bài này, PostgreSQL có thể chọn quét bảng trực tiếp thay vì dùng index, và điều đó hoàn toàn bình thường.

### 18.2. Thuật toán JOIN có thể khác câu SQL viết ra

Các DBMS thường có những chiến lược vật lý như:

- **Nested loop join:** lấy hàng từ một phía rồi tìm hàng khớp phía còn lại; có thể phù hợp khi tập dữ liệu phía ngoài nhỏ và có index.
- **Hash join:** tạo cấu trúc băm theo khóa từ một nguồn rồi dò khớp các hàng phía kia; thường hữu ích cho các phép ghép bằng khóa trên tập lớn.
- **Merge join:** ghép hai dòng dữ liệu đã có thứ tự phù hợp theo khóa; có thể hiệu quả khi nguồn được sắp xếp theo khóa.

Ba cách có thể thực thi **cùng một ngữ nghĩa INNER JOIN**. Người viết SQL không nên chọn cú pháp JOIN dựa vào suy đoán rằng một toán tử vật lý nhất định bắt buộc được sử dụng.

### 18.3. EXPLAIN trong PostgreSQL

~~~sql
EXPLAIN
SELECT
    dh.id,
    kh.ten_khach_hang
FROM don_hang_join AS dh
INNER JOIN khach_hang_join AS kh
    ON dh.khach_hang_id = kh.id
WHERE dh.to_chuc_id = 10;
~~~

`EXPLAIN` cho biết kế hoạch dự kiến, chẳng hạn cách đọc hai bảng, ước lượng số dòng và thuật toán JOIN. `EXPLAIN ANALYZE` sẽ thực sự chạy truy vấn để thống kê số dòng và thời gian, vì vậy chỉ dùng trong môi trường và câu lệnh thích hợp.

Khi cần tối ưu:

1. Xác nhận **điều kiện ghép đúng khóa** trước;
2. Xác nhận **grain mong muốn**, số dòng đầu vào và số dòng sau JOIN;
3. Kiểm tra điều kiện lọc có giảm đáng kể số dòng trước JOIN về mặt logic không;
4. Xem kế hoạch, statistics và chỉ mục phù hợp;
5. Đo trên workload thực, thay vì mặc định thêm `DISTINCT` hoặc thêm index là nhanh hơn.

### 18.4. Hàm/ép kiểu trong điều kiện JOIN

~~~sql
-- Ví dụ quan hệ phụ thuộc vào dữ liệu văn bản chuẩn hóa:
-- ON lower(a.ma_khach) = lower(b.ma_khach)
~~~

Nếu schema thật sự có khóa nhận diện, nên ghép theo **khóa đã được chuẩn hóa và bảo vệ** thay vì áp dụng hàm vào từng hàng để so sánh. Hàm hoặc ép kiểu trên cột dùng nối có thể tăng chi phí và làm index thường ít hiệu quả, bên cạnh nguy cơ ghép nhầm theo quy tắc chữ hoa/thường và collation. Nếu phải nối dữ liệu từ hai hệ thống có mã khác nhau, cần một bước **mapping/chuẩn hóa dữ liệu có kiểm soát**, không coi `lower` hay `replace` là công thức ghép định danh luôn đúng.

## 19. Khác biệt giữa các hệ quản trị

`INNER JOIN ... ON` là cú pháp phổ biến của SQL và hoạt động trong PostgreSQL, MySQL, SQL Server, Oracle Database. Những điểm cần lưu ý thường nằm ở **kiểu khóa, collation, cú pháp rút gọn, xử lý `NULL` và kế hoạch thực thi**.

| Chủ đề | PostgreSQL | MySQL | SQL Server | Oracle Database |
| --- | --- | --- | --- | --- |
| `INNER JOIN ... ON` | Hỗ trợ | Hỗ trợ | Hỗ trợ | Hỗ trợ |
| `JOIN` thay cho `INNER JOIN` | Thường tương đương | Thường tương đương | Thường tương đương | Thường tương đương |
| `USING (cot)` | Hỗ trợ | Hỗ trợ | Không phải cú pháp T-SQL JOIN thông thường | Hỗ trợ |
| `NULL = NULL` trong JOIN | `UNKNOWN`, không khớp | `UNKNOWN`, không khớp | `UNKNOWN`, không khớp với phép `=` thông thường theo logic chuẩn | `UNKNOWN`, không khớp |
| Kiểu tự sinh khóa | `IDENTITY`, sequence, UUID | `AUTO_INCREMENT`, các phương án khác | `IDENTITY`, `UNIQUEIDENTIFIER` | `IDENTITY`, sequence, `RAW` |
| Index trên khóa ngoại | Không tự tạo index ở bảng con chỉ nhờ `FOREIGN KEY` | Cơ chế InnoDB yêu cầu index hỗ trợ và có thể tạo phù hợp | Không mặc định tạo index chỉ vì khai báo FK | Không tự tạo index FK theo cách tương đương |
| Cách xem kế hoạch | `EXPLAIN`, `EXPLAIN ANALYZE` | `EXPLAIN` và công cụ theo phiên bản | Actual/Estimated Execution Plan, `SET SHOWPLAN...` | `EXPLAIN PLAN`, `DBMS_XPLAN` |

### 19.1. Collation có thể thay đổi kết quả khi nối bằng chuỗi

Một hệ thống dùng `ma_khach` kiểu chuỗi có thể coi `'kh001'` và `'KH001'` là bằng nhau trong một collation không phân biệt chữ hoa/thường, trong khi ở collation khác chúng được xem là hai chuỗi khác nhau. Vì vậy:

~~~sql
ON d.ma_khach = k.ma_khach
~~~

có thể cho kết quả khác nếu hai môi trường có quy tắc so sánh chuỗi khác nhau. Để khóa ghép ổn định, nên xác định rõ **kiểu dữ liệu, collation và chính sách chuẩn hóa mã**.

### 19.2. Hạn chế của cú pháp JOIN cũ

Oracle có các cách viết outer join cũ như `(+)`; một số mã SQL lịch sử dùng dấu phẩy trong `FROM` và điều kiện nối ở `WHERE`. Trong mã mới, cú pháp `INNER JOIN ... ON` của ANSI SQL thường dễ đọc, dễ bảo trì và tránh nhầm với các quy tắc đặc thù của kiểu viết cũ.

### 19.3. Không suy ra hiệu năng từ tên DBMS

Một `INNER JOIN` ấn định **ngữ nghĩa cặp hàng khớp**; DBMS tự lựa chọn cách thực thi. PostgreSQL, MySQL, SQL Server và Oracle có các cơ chế thống kê, index và thuật toán thực thi khác nhau. Không có kết luận đúng cho mọi hệ thống rằng INNER JOIN luôn chạy nhanh hơn phép truy vấn con hoặc rằng đổi thứ tự bảng trong SQL luôn làm kế hoạch thực thi tốt hơn.

## 20. Những lỗi thường gặp khi INNER JOIN

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Ghép `dh.id = kh.id` thay vì `dh.khach_hang_id = kh.id` | Cột cùng tên nhưng khác ý nghĩa, mất hoặc sai cặp | Xác nhận quan hệ PK/FK trong schema |
| Bỏ một thành phần khóa ghép `(to_chuc_id, ma_khach)` | Ghép sai khách giữa các tổ chức, nhân dòng | Đưa **đủ mọi thành phần khóa** vào `ON` |
| Ghép theo tên khách | Tên trùng, đổi tên, khác chuẩn hóa | Dùng khóa định danh ổn định |
| Thiếu điều kiện `ON` hoặc dùng `ON TRUE` sai mục đích | Tích Descartes hoặc quá nhiều dòng | Dùng INNER JOIN bằng điều kiện khóa thật |
| Tưởng mỗi khách xuất hiện một lần sau JOIN đơn | Quan hệ 1–n tạo nhiều dòng trên cùng khách | Xác định grain, dùng `EXISTS`/`GROUP BY` khi cần |
| Tưởng mọi khách xuất hiện sau INNER JOIN | Khách không có đơn bị loại | Dùng `LEFT JOIN` khi cần giữ hàng không khớp |
| JOIN đơn với chi tiết rồi `SUM(dh.tong_tien)` | Tổng tiền mỗi đơn bị lặp theo số dòng chi tiết | Tổng hợp ở grain đơn hoặc dùng EXISTS |
| Dùng `SUM(DISTINCT tong_tien)` để “sửa” | Hai đơn có cùng số tiền hợp lệ bị gộp | Phân biệt theo ID đơn, không theo giá trị tiền |
| Dùng `SELECT DISTINCT *` để che nhân dòng | Có thể bỏ mất chi tiết hoặc không giải quyết nguyên nhân | Sửa điều kiện JOIN và grain |
| Quên `NULL` trong khóa dùng `=` | Hàng thiếu khóa không khớp | Xác định chính sách khóa nullable |
| Đặt `OR` trong WHERE thiếu ngoặc | Lọc sai phạm vi, có nguy cơ lộ dữ liệu tổ chức khác | Nhóm các nhánh thay thế bằng ngoặc hoặc IN |
| Không kiểm tra index và kế hoạch | JOIN trên bảng lớn có thể tốn tài nguyên | Đo với EXPLAIN/stats và chỉ mục phù hợp |

## 21. Bài tập thực hành có lời giải

Các bài sau sử dụng bảng `khach_hang_join`, `don_hang_join` và `chi_tiet_don_hang_join` đã tạo ở mục 4 trong cùng phiên PostgreSQL, trừ khi nói rõ khác. Hãy trả lời trước **một dòng kết quả đại diện cho gì**, rồi mới dự đoán số dòng.

### Bài 1: INNER JOIN hai bảng

~~~sql
SELECT
    dh.id,
    kh.ten_khach_hang
FROM don_hang_join AS dh
INNER JOIN khach_hang_join AS kh
    ON dh.khach_hang_id = kh.id
ORDER BY dh.id;
~~~

**Câu hỏi:** Có bao nhiêu dòng? An xuất hiện mấy lần?

**Lời giải:** Có **6 dòng**, một dòng cho mỗi đơn hàng vì mỗi đơn có đúng một khách khớp. An xuất hiện **2 lần** do sở hữu đơn 101 và 102. Không phải dữ liệu khách bị nhân bản trong bảng gốc.

### Bài 2: Khách không có đơn

**Câu hỏi:** INNER JOIN từ `khach_hang_join` đến `don_hang_join` có hiển thị Em và Lan không? Nếu yêu cầu hiện tất cả khách, cần làm gì?

**Lời giải:** Em và Lan **không xuất hiện** vì không có đơn khớp. Muốn hiển thị mọi khách kèm đơn nếu có, dùng `LEFT JOIN` từ bảng khách sang bảng đơn:

~~~sql
SELECT kh.id, kh.ten_khach_hang, dh.id AS don_hang_id
FROM khach_hang_join AS kh
LEFT JOIN don_hang_join AS dh
    ON dh.khach_hang_id = kh.id
ORDER BY kh.id, dh.id;
~~~

### Bài 3: Tìm các khách đã từng mua

**Yêu cầu:** mỗi khách có ít nhất một đơn xuất hiện **một dòng**.

**Một lời giải:**

~~~sql
SELECT kh.id, kh.ten_khach_hang
FROM khach_hang_join AS kh
WHERE EXISTS (
    SELECT 1
    FROM don_hang_join AS dh
    WHERE dh.khach_hang_id = kh.id
)
ORDER BY kh.id;
~~~

Kết quả gồm **4 khách**: An, Bình, Chi, Dung. Có thể dùng INNER JOIN rồi `DISTINCT` trên ID/tên khách, nhưng `EXISTS` trực tiếp diễn đạt yêu cầu có ít nhất một bản ghi liên quan.

### Bài 4: INNER JOIN ba bảng

~~~sql
SELECT
    kh.ten_khach_hang,
    dh.id AS don_hang_id,
    ct.id AS chi_tiet_id
FROM khach_hang_join AS kh
INNER JOIN don_hang_join AS dh
    ON dh.khach_hang_id = kh.id
INNER JOIN chi_tiet_don_hang_join AS ct
    ON ct.don_hang_id = dh.id;
~~~

**Câu hỏi:** Có bao nhiêu dòng và tại sao không thấy đơn 106?

**Lời giải:** Có **7 dòng**, tương ứng bảy dòng chi tiết đang tồn tại. Đơn 106 chưa có dòng chi tiết nên không khớp INNER JOIN cuối. Grain kết quả là một dòng cho mỗi chi tiết đơn hàng kèm khách và đơn.

### Bài 5: Khóa ghép trong hệ thống đa tổ chức

Khách hàng được xác định bằng cặp `(to_chuc_id, ma_khach)`. Hai tổ chức 10 và 20 đều có `ma_khach = 'KH001'`. Một câu JOIN chỉ dùng `ON d.ma_khach = k.ma_khach` có vấn đề gì?

**Lời giải:** Đơn thuộc tổ chức 10 có thể bị ghép với cả khách cùng mã ở tổ chức 20, gây **nhân dòng và gán sai khách**. Điều kiện đúng:

~~~sql
ON d.to_chuc_id = k.to_chuc_id
AND d.ma_khach = k.ma_khach
~~~

Ràng buộc `FOREIGN KEY (to_chuc_id, ma_khach)` tham chiếu `PRIMARY KEY (to_chuc_id, ma_khach)` giúp database bảo vệ chính quan hệ này khi ghi.

### Bài 6: SUM bị nhân sau JOIN

~~~sql
SELECT SUM(dh.tong_tien)
FROM don_hang_join AS dh
INNER JOIN chi_tiet_don_hang_join AS ct
    ON ct.don_hang_id = dh.id;
~~~

**Câu hỏi:** Vì sao tổng không bằng `SUM(tong_tien)` trực tiếp ở bảng đơn hàng?

**Lời giải:** Đơn 101 và 105 mỗi đơn có hai dòng chi tiết nên tổng tiền bị cộng hai lần; đơn 106 không có chi tiết bị loại. Tổng JOIN là **2.250.000**, còn tổng mọi đơn là **1.670.000**. Nếu muốn tổng **các đơn có chi tiết nhưng mỗi đơn tính một lần**, dùng `EXISTS` hoặc chọn khóa đơn trước khi tổng hợp.

### Bài 7: Lọc đơn của tổ chức 10

**Yêu cầu:** hiển thị mã đơn, tên khách, trạng thái cho đơn thuộc tổ chức 10, chỉ lấy đơn `'MOI'` hoặc `'DA_THANH_TOAN'`, ghép đúng phạm vi tổ chức.

**Một lời giải:**

~~~sql
SELECT
    dh.id AS don_hang_id,
    kh.ten_khach_hang,
    dh.trang_thai
FROM don_hang_join AS dh
INNER JOIN khach_hang_join AS kh
    ON kh.to_chuc_id = dh.to_chuc_id
   AND kh.id = dh.khach_hang_id
WHERE dh.to_chuc_id = 10
  AND dh.trang_thai IN ('MOI', 'DA_THANH_TOAN')
ORDER BY dh.id;
~~~

Kết quả gồm các đơn `101`, `102`, `103`, `106`; đơn của tổ chức 20 không xuất hiện.

### Bài 8: NULL trong điều kiện ghép

Cho:

~~~sql
SELECT a.id, b.id
FROM nhom_ma_join AS a
INNER JOIN nhan_ma_join AS b
    ON a.ma = b.ma;
~~~

**Câu hỏi:** Hai hàng có `ma = NULL` có ghép nhau không?

**Lời giải:** **Không**, phép so sánh `NULL = NULL` có kết quả `UNKNOWN`, không phải `TRUE`. Với dữ liệu ở mục 12, chỉ cặp mã `'A'` khớp. Nếu nghiệp vụ muốn phép so sánh null-safe, PostgreSQL có `IS NOT DISTINCT FROM`, nhưng không mặc định dùng nó cho quan hệ PK/FK do hai giá trị thiếu không chứng minh hai thực thể liên quan.

### Bài 9: Ghép nhầm theo ID

Một lập trình viên nối:

~~~sql
ON dh.id = kh.id
~~~

vì cả hai bảng đều có cột tên `id`. Vì sao không đúng?

**Lời giải:** `dh.id` là ID **đơn**, `kh.id` là ID **khách**. Quan hệ thực tế là `dh.khach_hang_id` tham chiếu `kh.id`, vì vậy phải viết `ON dh.khach_hang_id = kh.id`. Tên cột giống nhau hoặc giá trị số trùng ngẫu nhiên không xác lập quan hệ.

### Bài 10: Tổng số lượng sản phẩm theo đơn

**Yêu cầu:** mỗi đơn **có dòng chi tiết** xuất hiện một lần với tổng số lượng sản phẩm. Dùng INNER JOIN và GROUP BY.

**Một lời giải:**

~~~sql
SELECT
    dh.id AS don_hang_id,
    SUM(ct.so_luong) AS tong_so_luong
FROM don_hang_join AS dh
INNER JOIN chi_tiet_don_hang_join AS ct
    ON ct.don_hang_id = dh.id
GROUP BY dh.id
ORDER BY dh.id;
~~~

Kết quả gồm **5 dòng**, một cho mỗi đơn 101–105; đơn 101 có tổng số lượng `3`, đơn 105 có `5`. Nếu muốn giữ cả đơn 106, cần thay đổi yêu cầu ghép sang `LEFT JOIN` và quy định cách hiển thị số lượng khi chưa có chi tiết.

### Bài 11: Dò các đơn không có khách hợp lệ

Trong một hệ thống nhập dữ liệu cũ **chưa có ràng buộc khóa ngoại**, cần tìm đơn không ghép được với khách. `INNER JOIN` có giúp thấy trực tiếp các hàng mồ côi đó không?

**Lời giải:** Không, INNER JOIN **loại** hàng không khớp. Dùng `LEFT JOIN` và kiểm tra khóa phía khách `IS NULL`, hoặc dùng `NOT EXISTS`:

~~~sql
SELECT dh.id, dh.khach_hang_id
FROM don_hang_join AS dh
WHERE NOT EXISTS (
    SELECT 1
    FROM khach_hang_join AS kh
    WHERE kh.to_chuc_id = dh.to_chuc_id
      AND kh.id = dh.khach_hang_id
);
~~~

Với bộ dữ liệu thực hành đã có ràng buộc khóa ngoại, truy vấn không trả hàng. Trong bảng nguồn chưa kiểm soát toàn vẹn, nó có thể phát hiện các đơn có khóa tham chiếu không hợp lệ.

## 22. Ghi nhớ khi thiết kế và đọc INNER JOIN

Hãy đọc điều kiện:

~~~sql
FROM don_hang_join AS dh
INNER JOIN khach_hang_join AS kh
    ON dh.to_chuc_id = kh.to_chuc_id
   AND dh.khach_hang_id = kh.id
~~~

theo thứ tự ý nghĩa:

1. **`dh` là bảng đơn hàng**, mỗi hàng đại diện một đơn.
2. **`kh` là bảng khách hàng**, mỗi hàng đại diện một khách.
3. Cặp khóa `(to_chuc_id, khach_hang_id)` của đơn xác định khách đúng trong cùng tổ chức.
4. **`INNER JOIN` chỉ giữ cặp khớp**; đơn không có khách phù hợp hoặc khách không có đơn sẽ không xuất hiện theo quan hệ ghép này.
5. **Grain kết quả** tùy hướng quan hệ: một khách có nhiều đơn khiến tên khách lặp theo mỗi đơn. Ghép thêm chi tiết có thể tiếp tục tăng số dòng.
6. Các phép tổng hợp `COUNT`, `SUM`, `AVG` phải được đặt trên **mức chi tiết đúng**, không tự cộng dữ liệu bảng cha sau khi nhân dòng bởi JOIN bảng con.

**Kết luận:** `INNER JOIN` không chỉ là cú pháp nối hai tên bảng; nó là thao tác kết hợp những **hàng thỏa quan hệ khóa**. Viết đúng điều kiện `ON` — đầy đủ khóa chính/khóa ngoại, nhất là khóa ghép có phạm vi tổ chức — giúp tránh ghép sai thực thể. Hiểu số cặp khớp và mức chi tiết kết quả giúp tránh lỗi nhân dòng, mất hàng và tính tổng sai. Khi cần giữ hàng không khớp, tìm hàng thiếu quan hệ hoặc tính toán ở một grain khác, hãy chủ động lựa chọn `LEFT JOIN`, `EXISTS`, `NOT EXISTS` hoặc `GROUP BY` thay vì thêm `DISTINCT` để che nguyên nhân.

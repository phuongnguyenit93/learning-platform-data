# Truy vấn con tương quan và phạm vi tham chiếu trong SQL

Một câu SQL có thể chứa một truy vấn khác bên trong nó. Chẳng hạn, để tìm khách hàng **đã từng đặt ít nhất một đơn**, ta có thể dùng truy vấn con để kiểm tra đơn hàng. Khi truy vấn con cần biết **khách hàng hiện đang được xét ở truy vấn bên ngoài**, nó sẽ tham chiếu đến cột của truy vấn ngoài. Đó là **truy vấn con tương quan** (*correlated subquery*).

Trọng tâm của bài học không chỉ là cú pháp `EXISTS` hay `SELECT` lồng nhau, mà là **phạm vi tham chiếu** (*name/reference scope*): một tên bảng, bí danh hoặc tên cột trong truy vấn con đang chỉ đến nguồn dữ liệu ở **cấp nào**? Vì sao `dh.khach_hang_id = kh.id` khiến truy vấn con phụ thuộc từng khách hàng, còn một lỗi đặt bí danh có thể biến câu lệnh thành truy vấn không còn tương quan?

Bài sử dụng **PostgreSQL** làm môi trường minh họa, với mô hình khách hàng, đơn hàng và thanh toán. Các nguyên tắc về phạm vi tham chiếu, `EXISTS`, `NOT EXISTS`, truy vấn con trả một giá trị và cách đối chiếu khóa cũng áp dụng rộng rãi trong SQL, nhưng các tiện ích `LATERAL`, `LIMIT` và cú pháp xử lý đặc biệt có thể khác giữa các hệ quản trị.

## 1. Truy vấn con là gì?

**Truy vấn con** (*subquery*) là một biểu thức truy vấn được đặt bên trong câu SQL khác, thường dùng để:

- Kiểm tra **có hay không** một hàng đáp ứng điều kiện bằng `EXISTS`/`NOT EXISTS`;
- Kiểm tra giá trị thuộc một tập bằng `IN`/`NOT IN`;
- Tính **một giá trị** như `COUNT`, `AVG`, `MAX` cho một hàng bên ngoài;
- Tạo tập hàng trung gian trong `FROM`, CTE hoặc một phép ghép;
- Lọc, phân loại, sắp xếp hoặc cập nhật dữ liệu bằng điều kiện phụ thuộc vào bảng khác.

Ví dụ truy vấn con không tương quan:

~~~sql
SELECT id, ten_khach_hang
FROM khach_hang_tq
WHERE id IN (
    SELECT khach_hang_id
    FROM don_hang_tq
);
~~~

Truy vấn bên trong lấy các mã khách có đơn. Nó **không dùng cột hay bí danh nào của câu SELECT bên ngoài**. Vì vậy đây là một truy vấn con **không tương quan** (*uncorrelated subquery*).

Ngược lại:

~~~sql
SELECT kh.id, kh.ten_khach_hang
FROM khach_hang_tq AS kh
WHERE EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE dh.khach_hang_id = kh.id
);
~~~

Biểu thức `kh.id` nằm trong truy vấn con nhưng `kh` được khai báo ở **truy vấn ngoài**. Đó chính là mối tương quan: câu truy vấn bên trong cần giá trị khóa của hàng `kh` đang được xét.

**Cách ghi nhớ:** truy vấn con thông thường có thể đứng riêng về mặt dữ liệu mà nó tham chiếu; truy vấn con tương quan **mượn ngữ cảnh của truy vấn bao ngoài** để xác định điều kiện hoặc kết quả.

## 2. Bộ dữ liệu thực hành PostgreSQL

Để theo dõi chính xác phạm vi và số dòng, ta sử dụng ba bảng tạm trong **cùng một phiên kết nối PostgreSQL**. Khi mở phiên mới, phải tạo lại bảng tạm.

### 2.1. Bảng khách hàng

~~~sql
CREATE TEMP TABLE khach_hang_tq (
    id INTEGER PRIMARY KEY,
    to_chuc_id INTEGER NOT NULL,
    ten_khach_hang TEXT NOT NULL,
    thanh_pho TEXT,
    CONSTRAINT uq_khach_theo_to_chuc_tq UNIQUE (to_chuc_id, id)
);

INSERT INTO khach_hang_tq
    (id, to_chuc_id, ten_khach_hang, thanh_pho)
VALUES
    (1, 10, 'An',   'Hà Nội'),
    (2, 10, 'Bình', 'Đà Nẵng'),
    (3, 10, 'Chi',  'Hà Nội'),
    (4, 20, 'Dung', 'TP.HCM'),
    (5, 20, 'Em',   'TP.HCM'),
    (6, 10, 'Lan',  NULL);
~~~

Có sáu khách hàng; mỗi hàng đại diện cho **một khách**, nhận diện bằng `id`. Cột `to_chuc_id` giúp minh họa hệ thống phục vụ nhiều tổ chức, trong đó mỗi thao tác liên quan có thể phải bảo đảm dữ liệu thuộc đúng tổ chức.

### 2.2. Bảng đơn hàng

~~~sql
CREATE TEMP TABLE don_hang_tq (
    id INTEGER PRIMARY KEY,
    to_chuc_id INTEGER NOT NULL,
    khach_hang_id INTEGER NOT NULL,
    thoi_diem_dat TIMESTAMPTZ NOT NULL,
    trang_thai TEXT NOT NULL,
    tong_tien NUMERIC(12, 2) NOT NULL CHECK (tong_tien >= 0),
    CONSTRAINT fk_don_khach_tq
        FOREIGN KEY (to_chuc_id, khach_hang_id)
        REFERENCES khach_hang_tq(to_chuc_id, id)
);

INSERT INTO don_hang_tq
    (id, to_chuc_id, khach_hang_id,
     thoi_diem_dat, trang_thai, tong_tien)
VALUES
    (101, 10, 1, '2026-10-01 09:00:00+07', 'DA_THANH_TOAN', 200000),
    (102, 10, 1, '2026-10-05 10:00:00+07', 'MOI',           300000),
    (103, 10, 2, '2026-10-03 14:00:00+07', 'DA_THANH_TOAN', 150000),
    (104, 10, 3, '2026-10-04 08:00:00+07', 'DA_HUY',        120000),
    (105, 20, 4, '2026-10-06 16:00:00+07', 'DA_THANH_TOAN', 400000),
    (106, 20, 4, '2026-10-07 11:00:00+07', 'MOI',           500000),
    (107, 10, 3, '2026-10-09 09:00:00+07', 'DA_THANH_TOAN',  80000),
    (108, 10, 1, '2026-10-10 13:00:00+07', 'DA_THANH_TOAN', 300000);
~~~

Bảng đơn hàng có tám dòng; mỗi dòng là **một đơn hàng**, và cặp `(to_chuc_id, khach_hang_id)` tham chiếu đúng khách hàng. Phân bố:

| Khách hàng | ID khách | Các đơn | Số đơn |
| --- | ---: | --- | ---: |
| An | 1 | 101, 102, 108 | 3 |
| Bình | 2 | 103 | 1 |
| Chi | 3 | 104, 107 | 2 |
| Dung | 4 | 105, 106 | 2 |
| Em | 5 | Không có | 0 |
| Lan | 6 | Không có | 0 |

### 2.3. Bảng thanh toán

~~~sql
CREATE TEMP TABLE thanh_toan_tq (
    id INTEGER PRIMARY KEY,
    don_hang_id INTEGER REFERENCES don_hang_tq(id),
    ket_qua TEXT NOT NULL,
    so_tien NUMERIC(12, 2) NOT NULL CHECK (so_tien >= 0)
);

INSERT INTO thanh_toan_tq (id, don_hang_id, ket_qua, so_tien)
VALUES
    (201, 101, 'THANH_CONG', 200000),
    (202, 103, 'THANH_CONG', 150000),
    (203, NULL, 'CHO_XU_LY',      0),
    (204, 105, 'THANH_CONG', 400000),
    (205, 108, 'THANH_CONG', 300000),
    (206, 108, 'THAT_BAI',   300000);
~~~

Cột `don_hang_id` cố ý **cho phép `NULL`** ở giao dịch 203 để minh họa vấn đề `NOT IN`. Đơn 108 có **hai bản ghi thanh toán** với kết quả khác nhau, giúp phân biệt yêu cầu “có ít nhất một thanh toán thành công” và yêu cầu “mọi lần thanh toán đều thành công”.

Quan hệ dữ liệu:

~~~mermaid
flowchart LR
    KH["khach_hang_tq\n1 hàng / khách hàng"] -->|"0..n đơn"| DH["don_hang_tq\n1 hàng / đơn hàng"]
    DH -->|"0..n lần thanh toán"| TT["thanh_toan_tq\n1 hàng / giao dịch thanh toán"]
~~~

**Lưu ý về ràng buộc:** một `FOREIGN KEY` nullable cho phép bản ghi thanh toán chưa có đơn tham chiếu theo ngữ nghĩa thông thường; khi có mã đơn khác `NULL`, nó phải tham chiếu đơn hợp lệ. Dữ liệu này chỉ phục vụ học truy vấn; hệ thống thanh toán thật cần thêm quy tắc trạng thái, quyền truy cập và toàn vẹn nghiệp vụ.

## 3. Truy vấn con tương quan hoạt động ra sao?

Yêu cầu: **liệt kê các khách đã từng đặt ít nhất một đơn**.

~~~sql
SELECT
    kh.id,
    kh.ten_khach_hang
FROM khach_hang_tq AS kh
WHERE EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE dh.khach_hang_id = kh.id
      AND dh.to_chuc_id = kh.to_chuc_id
)
ORDER BY kh.id;
~~~

Kết quả:

| id | ten_khach_hang |
| ---: | --- |
| 1 | An |
| 2 | Bình |
| 3 | Chi |
| 4 | Dung |

Em và Lan không có đơn nên `EXISTS` không tìm được hàng khớp. Hai điều kiện bên trong truy vấn con:

~~~sql
dh.khach_hang_id = kh.id
AND dh.to_chuc_id = kh.to_chuc_id
~~~

liên kết đơn hàng `dh` của **truy vấn con** với khách hàng `kh` của **truy vấn ngoài**.

### 3.1. Mô hình tư duy “theo từng hàng”

Có thể tưởng tượng câu SQL được xét một cách logic:

1. Xét khách An (`kh.id = 1`, `kh.to_chuc_id = 10`).
2. Ở truy vấn con, tìm đơn có `dh.khach_hang_id = 1` và `dh.to_chuc_id = 10`.
3. Có các đơn 101, 102, 108 nên `EXISTS` trả `TRUE`; giữ An.
4. Xét Bình, Chi, Dung tương tự: có đơn nên giữ.
5. Xét Em và Lan: không có đơn, `EXISTS` là `FALSE`; loại.

Đây là **mô hình ngữ nghĩa** giúp hiểu tham chiếu ngoài, **không phải khẳng định DBMS nhất thiết chạy truy vấn con vật lý sáu lần**. Bộ tối ưu hóa có thể chuyển đổi thành *semi-join*, dùng chỉ mục, cache, sắp xếp lại các thao tác hoặc một kế hoạch khác mà vẫn bảo toàn kết quả.

### 3.2. Thành phần nào tạo ra tương quan?

Xét:

~~~sql
SELECT 1
FROM don_hang_tq AS dh
WHERE dh.khach_hang_id = kh.id
~~~

`dh` được khai báo trong truy vấn con nên thuộc **phạm vi trong**; `kh` không được khai báo ở đó mà được lấy từ **phạm vi truy vấn ngoài**. Cặp `dh.khach_hang_id = kh.id` làm điều kiện thay đổi theo khách đang xét.

Nếu bỏ điều kiện tương quan:

~~~sql
SELECT kh.id, kh.ten_khach_hang
FROM khach_hang_tq AS kh
WHERE EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
);
~~~

thì vì bảng `don_hang_tq` đang có hàng, `EXISTS` là `TRUE` cho **mọi** khách; kết quả có **sáu** dòng. Đây là lỗi phổ biến khi người viết quên nối truy vấn con với truy vấn ngoài.

### 3.3. Tương quan không có nghĩa bảng con phải có FOREIGN KEY

Một truy vấn con có thể tham chiếu bất kỳ biểu thức/cột ngoài hợp lệ nào, ngay cả khi không có ràng buộc khóa ngoại. Nhưng khi bài toán là liên hệ thực thể, **nên dựa vào khóa và quan hệ đã thiết kế**. Ghép hai bảng theo tên khách, địa chỉ hoặc mã không duy nhất có thể sinh kết quả sai dù cú pháp correlated subquery hợp lệ.

## 4. Phạm vi tham chiếu: tên nào thuộc cấp nào?

Điều quan trọng nhất của bài: **mỗi `SELECT` tạo một cấp truy vấn với các nguồn dữ liệu và bí danh riêng**. Khi một tham chiếu tên cột xuất hiện ở cấp trong, DBMS cần xác định nó thuộc nguồn nào.

~~~text
SELECT ngoài
  FROM khach_hang_tq AS kh       <-- bí danh kh ở phạm vi ngoài
  WHERE EXISTS (
      SELECT trong
        FROM don_hang_tq AS dh   <-- bí danh dh ở phạm vi trong
        WHERE dh.khach_hang_id = kh.id
                ^ bên trong        ^ từ bên ngoài
  )
~~~

**Quy tắc thực hành quan trọng:** ở truy vấn con tương quan, hãy **ghi rõ bí danh** cho mỗi cột tham gia liên hệ. Khi viết `kh.id`, người đọc biết chắc đó là khách hàng ở ngoài; khi viết `dh.khach_hang_id`, người đọc biết chắc đó là khóa ngoại của đơn.

### 4.1. Tên cột không có bí danh có thể bị hiểu khác mong muốn

Ví dụ dễ nhầm:

~~~sql
-- Không nên dùng: id được phân giải ở phạm vi don_hang_tq!
SELECT kh.id
FROM khach_hang_tq AS kh
WHERE EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE khach_hang_id = id
);
~~~

Trong truy vấn con, `don_hang_tq` có **cả `khach_hang_id` và `id`**, nên hai tên không có bí danh được phân giải thành các cột của `dh`. Điều kiện thực chất là `dh.khach_hang_id = dh.id`, **không phải** `dh.khach_hang_id = kh.id`. Trên dữ liệu mẫu không có đơn nào mà ID đơn bằng ID khách, truy vấn trả rỗng — một kết quả sai với yêu cầu ban đầu.

Sửa:

~~~sql
WHERE dh.khach_hang_id = kh.id
~~~

**Một truy vấn chạy không báo lỗi chưa chắc tham chiếu đúng phạm vi.** Với correlated subquery, tên cột thiếu bí danh có thể tạo ra truy vấn **không tương quan** ngoài ý định, dẫn đến kết quả luôn `TRUE`, luôn `FALSE` hoặc ghép nhầm.

### 4.2. Bí danh trùng tên gây che khuất (*shadowing*)

Xét ví dụ:

~~~sql
-- Ví dụ có chủ ý sai:
SELECT kh.id, kh.ten_khach_hang
FROM khach_hang_tq AS kh
WHERE EXISTS (
    SELECT 1
    FROM don_hang_tq AS kh
    WHERE kh.khach_hang_id = 1
);
~~~

Hai cấp truy vấn cùng khai báo bí danh `kh`. **Bí danh `kh` ở cấp trong che khuất bí danh `kh` bên ngoài** khi phân giải bên trong subquery. Vì có các đơn của khách 1, `EXISTS` luôn đúng, nên kết quả có **cả sáu khách**, không phải chỉ khách 1.

Cách viết rõ ràng:

~~~sql
SELECT kh.id, kh.ten_khach_hang
FROM khach_hang_tq AS kh
WHERE EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE dh.khach_hang_id = kh.id
      AND dh.to_chuc_id = kh.to_chuc_id
);
~~~

Quy ước bí danh theo vai trò (`kh` cho khách, `dh` cho đơn, `tt` cho thanh toán) không phải yêu cầu bắt buộc của SQL, nhưng giúp tránh lỗi rất khó nhận ra.

### 4.3. Tên bí danh của truy vấn trong không dùng được bên ngoài

~~~sql
SELECT kh.id
FROM khach_hang_tq AS kh
WHERE EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE dh.khach_hang_id = kh.id
)
-- Không thể ORDER BY dh.id ở đây: dh không thuộc phạm vi ngoài.
ORDER BY kh.id;
~~~

`dh` chỉ tồn tại trong phạm vi subquery. Tương tự, một bí danh cột tính trong `SELECT` ngoài không tự động trở thành tên cột có thể tham chiếu trong `WHERE` của cùng cấp. Quy tắc dùng alias ở `ORDER BY`, `GROUP BY`, `HAVING` có khác biệt và giới hạn theo DBMS; không nên dùng chúng thay thế cho việc xác định đúng nguồn cột khi tương quan.

### 4.4. Phạm vi của bảng dẫn xuất trong FROM: cần LATERAL

Trong PostgreSQL, một **derived table** thông thường đặt trong `FROM` không thể tùy ý tham chiếu các bảng đứng trước nó trong cùng `FROM`:

~~~sql
-- Không hợp lệ dưới dạng derived table thông thường trong PostgreSQL:
-- SELECT kh.id, x.so_don
-- FROM khach_hang_tq AS kh
-- JOIN (
--     SELECT COUNT(*) AS so_don
--     FROM don_hang_tq AS dh
--     WHERE dh.khach_hang_id = kh.id
-- ) AS x ON TRUE;
~~~

Muốn phần truy vấn trong `FROM` **nhận giá trị từ hàng của bảng đứng trước**, PostgreSQL dùng `LATERAL`. Phần 12 sẽ có ví dụ chạy được. Đây là giới hạn **phạm vi tham chiếu ở mệnh đề `FROM`**, không phải phủ định việc truy vấn con trong `WHERE` hoặc `SELECT` có thể tương quan.

## 5. EXISTS: kiểm tra có ít nhất một hàng khớp

`EXISTS (subquery)` trả `TRUE` nếu truy vấn con sinh **ít nhất một hàng**, và `FALSE` nếu không có hàng nào. Nó không yêu cầu lấy hết dữ liệu chi tiết của bảng con để đưa ra kết quả.

Ví dụ: khách thuộc tổ chức 10 có ít nhất một đơn đã thanh toán:

~~~sql
SELECT
    kh.id,
    kh.ten_khach_hang
FROM khach_hang_tq AS kh
WHERE kh.to_chuc_id = 10
  AND EXISTS (
      SELECT 1
      FROM don_hang_tq AS dh
      WHERE dh.to_chuc_id = kh.to_chuc_id
        AND dh.khach_hang_id = kh.id
        AND dh.trang_thai = 'DA_THANH_TOAN'
  )
ORDER BY kh.id;
~~~

Kết quả là An, Bình, Chi (`id` 1, 2, 3). Dung có đơn đã thanh toán nhưng thuộc tổ chức 20, không thuộc phạm vi truy vấn. Em và Lan chưa có đơn.

### 5.1. SELECT 1 hay SELECT * trong EXISTS?

~~~sql
WHERE EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE dh.khach_hang_id = kh.id
)
~~~

Với `EXISTS`, điều quan trọng là **có hàng hay không**, không phải các giá trị được chọn. Viết `SELECT 1` thường giúp người đọc nhìn ra ý định rõ hơn; `SELECT *` cũng có thể được dùng trong phần lớn tình huống thông thường. Không suy rằng `SELECT 1` luôn nhanh hơn `SELECT *` vì DBMS có thể tối ưu để chỉ kiểm tra sự tồn tại.

Nếu subquery trả một hàng có giá trị `NULL` thì `EXISTS` vẫn là **`TRUE`**, vì **hàng tồn tại**. Khác với `IN`, `EXISTS` không đối chiếu giá trị từ danh sách `SELECT` với giá trị bên ngoài.

### 5.2. EXISTS không nhân dòng của khách hàng

Khách An có ba đơn, nhưng truy vấn:

~~~sql
SELECT kh.id, kh.ten_khach_hang
FROM khach_hang_tq AS kh
WHERE EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE dh.khach_hang_id = kh.id
      AND dh.to_chuc_id = kh.to_chuc_id
);
~~~

vẫn trả **một dòng cho An**, vì mỗi khách trong bảng ngoài được giữ hoặc bị loại **một lần**. Ngược lại, `INNER JOIN` khách–đơn có thể tạo ba dòng cho An trước khi dùng `DISTINCT` hay `GROUP BY`.

Với mục tiêu **“khách hàng có ít nhất một đơn”**, `EXISTS` thường diễn đạt đúng mức chi tiết kết quả ngay từ đầu.

### 5.3. EXISTS với nhiều bảng bên trong

Yêu cầu: khách có ít nhất một đơn **đã ghi nhận giao dịch thanh toán thành công**:

~~~sql
SELECT kh.id, kh.ten_khach_hang
FROM khach_hang_tq AS kh
WHERE EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    INNER JOIN thanh_toan_tq AS tt
        ON tt.don_hang_id = dh.id
    WHERE dh.khach_hang_id = kh.id
      AND dh.to_chuc_id = kh.to_chuc_id
      AND tt.ket_qua = 'THANH_CONG'
)
ORDER BY kh.id;
~~~

Kết quả là **An, Bình, Dung** (ID 1, 2, 4). Chi có đơn `107` mang trạng thái `DA_THANH_TOAN`, nhưng **bộ dữ liệu mẫu không có giao dịch thanh toán thành công nào tham chiếu đơn đó**, nên Chi không xuất hiện trong câu truy vấn này. Đó là sự khác biệt giữa **trạng thái lưu trên đơn** và **sự tồn tại của giao dịch thanh toán thành công**.

### 5.4. Không cần thêm LIMIT 1 để EXISTS “nhanh hơn”

Vì `EXISTS` chỉ cần biết có hàng, nhiều DBMS đã tối ưu việc kiểm tra tồn tại. Viết `LIMIT 1` trong subquery thường không cần thiết cho ý nghĩa:

~~~sql
WHERE EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE dh.khach_hang_id = kh.id
)
~~~

Thêm `LIMIT 1` trong PostgreSQL không làm thay đổi giá trị `EXISTS` trong trường hợp này, nhưng không có bảo đảm luôn cải thiện hiệu năng. Ngược lại, `LIMIT 0` sẽ khiến subquery không trả hàng, làm `EXISTS` luôn `FALSE`. Hãy viết để diễn đạt đúng yêu cầu, rồi đo kế hoạch khi có vấn đề về hiệu năng.

## 6. NOT EXISTS: tìm trường hợp không có hàng liên quan

`NOT EXISTS (subquery)` trả `TRUE` khi truy vấn con **không tìm thấy** hàng nào phù hợp với điều kiện tương quan.

Ví dụ: khách chưa từng có đơn:

~~~sql
SELECT
    kh.id,
    kh.ten_khach_hang
FROM khach_hang_tq AS kh
WHERE NOT EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE dh.to_chuc_id = kh.to_chuc_id
      AND dh.khach_hang_id = kh.id
)
ORDER BY kh.id;
~~~

Kết quả:

| id | ten_khach_hang |
| ---: | --- |
| 5 | Em |
| 6 | Lan |

Câu truy vấn không lấy khách rồi đếm số đơn; nó hỏi trực tiếp **không tồn tại đơn khớp khách này**.

### 6.1. Phủ định phải nằm đúng phạm vi

So sánh hai yêu cầu:

**A. “Khách không có bất kỳ đơn nào”:**

~~~sql
WHERE NOT EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE dh.khach_hang_id = kh.id
      AND dh.to_chuc_id = kh.to_chuc_id
)
~~~

**B. “Khách không có đơn ĐÃ THANH TOÁN”:**

~~~sql
WHERE NOT EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE dh.khach_hang_id = kh.id
      AND dh.to_chuc_id = kh.to_chuc_id
      AND dh.trang_thai = 'DA_THANH_TOAN'
)
~~~

Hai điều kiện không tương đương. Một khách có đơn MỚI nhưng chưa có đơn đã thanh toán **không thỏa A** nhưng **có thể thỏa B**. Khi viết `NOT EXISTS`, hãy tự hỏi đang phủ định **sự tồn tại của tập con nào**.

### 6.2. “Mọi đơn đều đã thanh toán”: bẫy tập rỗng

Một cách diễn đạt:

~~~sql
SELECT kh.id, kh.ten_khach_hang
FROM khach_hang_tq AS kh
WHERE NOT EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE dh.khach_hang_id = kh.id
      AND dh.to_chuc_id = kh.to_chuc_id
      AND dh.trang_thai <> 'DA_THANH_TOAN'
);
~~~

Nghĩa đen là **“không có đơn nào của khách bị đánh dấu khác ĐÃ THANH TOÁN”**. Em và Lan **cũng thỏa**, vì họ không có đơn nào để vi phạm điều kiện. Đây là một ví dụ của **đúng trên tập rỗng** (*vacuous truth*): “mọi phần tử thỏa P” không bị phản bác nếu tập phần tử rỗng.

Nếu yêu cầu nghiệp vụ là “**khách đã đặt ít nhất một đơn và tất cả các đơn đó đều đã thanh toán**”, cần thêm điều kiện tồn tại ít nhất một đơn:

~~~sql
SELECT kh.id, kh.ten_khach_hang
FROM khach_hang_tq AS kh
WHERE EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE dh.to_chuc_id = kh.to_chuc_id
      AND dh.khach_hang_id = kh.id
)
AND NOT EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE dh.to_chuc_id = kh.to_chuc_id
      AND dh.khach_hang_id = kh.id
      AND dh.trang_thai <> 'DA_THANH_TOAN'
)
ORDER BY kh.id;
~~~

Trong bộ dữ liệu mẫu, chỉ có **Bình** (ID 2) thỏa: một đơn 103 và đơn đó đã thanh toán; An có đơn MỚI, Chi có đơn ĐÃ HỦY, Dung có đơn MỚI.

Nếu cột `trang_thai` cho phép `NULL`, phép `<> 'DA_THANH_TOAN'` không tự bắt `NULL`. Khi `NULL` phải được xem là **chưa chứng minh đã thanh toán**, điều kiện phủ định cần thêm `OR dh.trang_thai IS NULL` hoặc phép so sánh `IS DISTINCT FROM` trong PostgreSQL. Trong ví dụ, cột được khai báo `NOT NULL`, nên không có trường hợp đó.

## 7. Vì sao NOT EXISTS thường an toàn hơn NOT IN khi có NULL?

Hai cách viết thoạt nhìn giống nhau:

~~~sql
-- A: kiểm tra không thuộc tập mã đơn trong bảng thanh toán.
SELECT dh.id
FROM don_hang_tq AS dh
WHERE dh.id NOT IN (
    SELECT tt.don_hang_id
    FROM thanh_toan_tq AS tt
);
~~~

và:

~~~sql
-- B: kiểm tra không có giao dịch thanh toán khớp mã đơn.
SELECT dh.id
FROM don_hang_tq AS dh
WHERE NOT EXISTS (
    SELECT 1
    FROM thanh_toan_tq AS tt
    WHERE tt.don_hang_id = dh.id
)
ORDER BY dh.id;
~~~

**Trong dữ liệu mẫu, kết quả khác nhau.**

Truy vấn A **không trả dòng nào**, vì tập `tt.don_hang_id` chứa một `NULL` (giao dịch 203). Đối với một ID không khớp các giá trị rõ ràng trong tập, `NOT IN` với phần tử `NULL` tạo kết quả `UNKNOWN`, không phải `TRUE`; `WHERE` loại những dòng đó. Các ID đã khớp thì `NOT IN` là `FALSE`.

Truy vấn B trả các đơn **102, 104, 106, 107**: chúng không có bất kỳ giao dịch thanh toán nào được liên kết bằng `tt.don_hang_id = dh.id`. Dòng `tt.don_hang_id IS NULL` không khớp ID đơn khác `NULL`, nên không làm mất những kết quả này.

### 7.1. NULL ở hai phía vẫn cần hiểu rõ

`NOT EXISTS` không bị một `NULL` ở **tập con** “đầu độc” theo cách `NOT IN` bị ảnh hưởng, nhưng nó chỉ xác định **có hàng thỏa điều kiện tương quan hay không**. Nếu khóa phía ngoài có thể là `NULL`, biểu thức so sánh `=` sẽ không coi hai `NULL` là khớp; yêu cầu nghiệp vụ phải quyết định như vậy có đúng hay không.

Nếu chắc chắn truy vấn con không sinh `NULL` và kiểu dữ liệu phù hợp, `NOT IN` có thể diễn đạt đúng một số yêu cầu. Tuy nhiên trong các truy vấn chống ghép (*anti-join*) với khóa nullable hoặc dữ liệu chưa sạch, `NOT EXISTS` thường dễ giải thích đúng hơn.

### 7.2. Đừng dùng COALESCE sang một mã giả để “chữa” NULL

Ví dụ:

~~~sql
-- Cần thận trọng:
-- WHERE COALESCE(tt.don_hang_id, -1) = COALESCE(dh.id, -1)
~~~

Nếu mã `-1` xuất hiện hợp lệ, có thể tạo **khớp giả**. Ngay cả khi không có `-1`, việc coi hai khóa thiếu là cùng một thực thể chưa chắc đúng nghiệp vụ. Thông thường nên định nghĩa quan hệ dựa trên khóa hợp lệ và xử lý dữ liệu thiếu tường minh.

## 8. Truy vấn con tương quan trả về một giá trị (*scalar subquery*)

Không phải correlated subquery nào cũng trả `TRUE`/`FALSE`. Một truy vấn con có thể được đặt ở vị trí cần **một giá trị**, chẳng hạn danh sách `SELECT`:

~~~sql
SELECT
    kh.id,
    kh.ten_khach_hang,
    (
        SELECT COUNT(*)
        FROM don_hang_tq AS dh
        WHERE dh.to_chuc_id = kh.to_chuc_id
          AND dh.khach_hang_id = kh.id
    ) AS so_don
FROM khach_hang_tq AS kh
ORDER BY kh.id;
~~~

Kết quả:

| id | ten_khach_hang | so_don |
| ---: | --- | ---: |
| 1 | An | 3 |
| 2 | Bình | 1 |
| 3 | Chi | 2 |
| 4 | Dung | 2 |
| 5 | Em | 0 |
| 6 | Lan | 0 |

Subquery `SELECT COUNT(*)` cho **một hàng có một giá trị** với mỗi khách, kể cả khi không có đơn: `COUNT(*)` trên tập rỗng trả `0`. Khách hàng ở truy vấn ngoài **không bị mất** vì subquery chỉ tính một giá trị để hiển thị.

### 8.1. Quy tắc scalar subquery: một cột, tối đa một hàng

Một scalar subquery phải tạo **một cột** và **không quá một hàng** để dùng như một giá trị:

- **Một hàng, một cột:** lấy giá trị của ô đó.
- **Không có hàng:** biểu thức scalar subquery thường trả **`NULL`**.
- **Nhiều hơn một hàng:** DBMS thường báo lỗi vì không thể lấy một giá trị duy nhất.
- **Nhiều hơn một cột:** không hợp lệ khi ngữ cảnh yêu cầu một scalar đơn.

Ví dụ dễ gây lỗi:

~~~sql
-- Không hợp lệ cho khách An có ba đơn:
-- SELECT kh.id,
--     (SELECT dh.id
--      FROM don_hang_tq AS dh
--      WHERE dh.khach_hang_id = kh.id) AS mot_don
-- FROM khach_hang_tq AS kh;
~~~

Truy vấn con có thể trả ba ID `101, 102, 108` cho An, nên không thể điền vào một ô `mot_don`. Không nên dựa vào “cứ lấy hàng đầu tiên” khi không có tiêu chí đại diện.

### 8.2. Dùng COUNT, SUM, AVG, MAX để tạo một giá trị

~~~sql
SELECT
    kh.id,
    kh.ten_khach_hang,
    (
        SELECT SUM(dh.tong_tien)
        FROM don_hang_tq AS dh
        WHERE dh.to_chuc_id = kh.to_chuc_id
          AND dh.khach_hang_id = kh.id
    ) AS tong_gia_tri,
    (
        SELECT MAX(dh.thoi_diem_dat)
        FROM don_hang_tq AS dh
        WHERE dh.to_chuc_id = kh.to_chuc_id
          AND dh.khach_hang_id = kh.id
    ) AS lan_dat_gan_nhat
FROM khach_hang_tq AS kh
ORDER BY kh.id;
~~~

Với dữ liệu mẫu, tổng giá trị đơn của An là `800000`, Bình `150000`, Chi `200000`, Dung `900000`. Em và Lan chưa có đơn nên `SUM` và `MAX` trả `NULL` chứ không tự cho `0`. Điều đó khác với `COUNT(*)`.

Nếu trong báo cáo muốn hiển thị tổng bằng 0 cho khách chưa có đơn:

~~~sql
COALESCE(
    (
        SELECT SUM(dh.tong_tien)
        FROM don_hang_tq AS dh
        WHERE dh.to_chuc_id = kh.to_chuc_id
          AND dh.khach_hang_id = kh.id
    ),
    0
) AS tong_gia_tri_hien_thi
~~~

Nên dùng `COALESCE` theo **ý nghĩa nghiệp vụ**: tổng tiền không có đơn có thể hiển thị `0`, nhưng ngày đặt gần nhất không có dữ liệu thường nên giữ `NULL` hoặc nhãn “chưa đặt”.

### 8.3. Có thể dùng scalar subquery trong WHERE

Yêu cầu: đơn hàng nào có giá trị **lớn hơn giá trị trung bình các đơn của chính khách đó**?

~~~sql
SELECT
    dh.id,
    dh.khach_hang_id,
    dh.tong_tien
FROM don_hang_tq AS dh
WHERE dh.tong_tien > (
    SELECT AVG(d2.tong_tien)
    FROM don_hang_tq AS d2
    WHERE d2.to_chuc_id = dh.to_chuc_id
      AND d2.khach_hang_id = dh.khach_hang_id
)
ORDER BY dh.id;
~~~

Kết quả:

| id | khach_hang_id | tong_tien | Giải thích |
| ---: | ---: | ---: | --- |
| 102 | 1 | 300000 | An: trung bình `800000 / 3` |
| 104 | 3 | 120000 | Chi: trung bình `(120000+80000)/2 = 100000` |
| 106 | 4 | 500000 | Dung: trung bình `(400000+500000)/2 = 450000` |
| 108 | 1 | 300000 | An: cũng lớn hơn trung bình của An |

Đơn 103 có giá trị **bằng** trung bình của Bình vì Bình chỉ có một đơn, nên không thỏa phép `>`.

Điểm quan trọng: giá trị trung bình được tính **theo nhóm tương quan của từng đơn**, không phải trung bình chung của toàn bộ bảng.

## 9. Tương quan nhiều cấp: truy vấn lồng trong truy vấn lồng

Một truy vấn con có thể chứa truy vấn con khác. Ở cấp sâu nhất, tham chiếu có thể đi đến một cấp bao ngoài gần hơn hoặc cấp ngoài xa hơn, miễn là tên đó hợp lệ và không bị nguồn cùng tên ở cấp gần hơn che khuất.

Ví dụ: tìm khách có **một đơn** và đơn đó có **một giao dịch thanh toán thành công**:

~~~sql
SELECT
    kh.id,
    kh.ten_khach_hang
FROM khach_hang_tq AS kh
WHERE EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE dh.to_chuc_id = kh.to_chuc_id
      AND dh.khach_hang_id = kh.id
      AND EXISTS (
          SELECT 1
          FROM thanh_toan_tq AS tt
          WHERE tt.don_hang_id = dh.id
            AND tt.ket_qua = 'THANH_CONG'
      )
)
ORDER BY kh.id;
~~~

Các cấp:

~~~text
Cấp 1: khach_hang_tq AS kh
   |
   +-- Cấp 2: don_hang_tq AS dh
          dùng kh.id và kh.to_chuc_id của cấp 1
          |
          +-- Cấp 3: thanh_toan_tq AS tt
                 dùng dh.id của cấp 2
~~~

Kết quả là An, Bình và Dung (1, 2, 4). Với yêu cầu này, từng nhánh `EXISTS` giữ đúng liên hệ: **giao dịch thanh toán phải thuộc chính đơn được tìm thấy**, và đơn đó phải thuộc khách đang xét.

### 9.1. Có thể tham chiếu trực tiếp cấp ngoài xa

Về mặt phạm vi, subquery cấp 3 có thể tham chiếu `kh.id` từ cấp 1 nếu tên còn nhìn thấy và cách viết hợp lệ. Nhưng nên tự hỏi **điều kiện liên hệ thực thể** đã đủ chưa. Trong mô hình trên, thanh toán liên kết với **đơn** bằng `tt.don_hang_id = dh.id`, không nên bỏ quan hệ đó rồi cố so sánh thanh toán trực tiếp với mã khách chỉ vì tham chiếu ngoài xa được phép.

**Phạm vi cú pháp được phép không đồng nghĩa điều kiện quan hệ đúng nghiệp vụ.**

### 9.2. Đổi tên bí danh ở mỗi cấp

Một mẫu dễ đọc:

- `kh`: khách hàng ở cấp ngoài;
- `dh`: đơn hàng ở cấp giữa;
- `tt`: thanh toán ở cấp sâu nhất.

Tránh dùng `x` ở cả ba cấp nếu không cần thiết. Khi các bí danh bị dùng lại, việc phân giải tên có thể chọn **nguồn ở cấp gần nhất**, tạo lỗi ngầm khó phát hiện.

## 10. Chọn một hàng đại diện bằng truy vấn con tương quan

Yêu cầu: **mỗi khách có đơn lấy đúng đơn gần nhất theo thời điểm đặt; khi trùng thời điểm thì chọn ID lớn hơn**. Đó không còn là vấn đề “có đơn hay không”, mà là chọn **một hàng đại diện trong tập đơn của mỗi khách**.

Trong PostgreSQL:

~~~sql
SELECT
    dh.id AS don_hang_id,
    dh.khach_hang_id,
    dh.thoi_diem_dat,
    dh.tong_tien
FROM don_hang_tq AS dh
WHERE dh.id = (
    SELECT d2.id
    FROM don_hang_tq AS d2
    WHERE d2.to_chuc_id = dh.to_chuc_id
      AND d2.khach_hang_id = dh.khach_hang_id
    ORDER BY d2.thoi_diem_dat DESC, d2.id DESC
    LIMIT 1
)
ORDER BY dh.khach_hang_id;
~~~

Kết quả:

| khach_hang_id | don_hang_id |
| ---: | ---: |
| 1 | 108 |
| 2 | 103 |
| 3 | 107 |
| 4 | 106 |

Vì truy vấn ngoài bắt đầu từ bảng **đơn hàng**, Em và Lan không có đơn nên không có dòng tương ứng. `ORDER BY ... LIMIT 1` trong scalar subquery giúp lựa chọn **một ID duy nhất** có quy tắc rõ.

### 10.1. Đừng dùng MAX(id) để thay “đơn mới nhất” vô điều kiện

`MAX(id)` chọn **ID lớn nhất**, không nhất thiết là **thời điểm mới nhất**. Nếu ID được nhập từ hệ thống khác, có khoảng nhảy, hoặc đơn được chèn không theo thứ tự ngày đặt, hai khái niệm có thể khác nhau. Khi nghiệp vụ nói “gần nhất”, phải dựa trên cột thời gian tương ứng và thêm tiêu chí phụ để xử lý trường hợp cùng thời điểm.

### 10.2. Phân biệt một hàng với tất cả hàng đồng hạng

Nếu yêu cầu là “đơn có **giá trị tiền lớn nhất** của mỗi khách”, biểu thức sau có thể trả **nhiều đơn cho một khách** khi đồng hạng:

~~~sql
SELECT
    dh.id,
    dh.khach_hang_id,
    dh.tong_tien
FROM don_hang_tq AS dh
WHERE dh.tong_tien = (
    SELECT MAX(d2.tong_tien)
    FROM don_hang_tq AS d2
    WHERE d2.to_chuc_id = dh.to_chuc_id
      AND d2.khach_hang_id = dh.khach_hang_id
)
ORDER BY dh.khach_hang_id, dh.id;
~~~

Khách An có **hai** đơn 102 và 108 cùng tổng tiền `300000`, nên cả hai đều đạt `MAX`. Điều này **đúng** nếu yêu cầu là lấy **mọi đơn đồng hạng cao nhất**; nếu yêu cầu đúng **một** đơn thì phải thêm quy tắc phá hòa (*tie-breaker*), chẳng hạn thời điểm rồi ID.

### 10.3. Dùng ROW_NUMBER làm cách tương đương về ý định

Một kỹ thuật SQL phổ biến khác:

~~~sql
WITH don_duoc_xep AS (
    SELECT
        dh.*,
        ROW_NUMBER() OVER (
            PARTITION BY dh.to_chuc_id, dh.khach_hang_id
            ORDER BY dh.thoi_diem_dat DESC, dh.id DESC
        ) AS rn
    FROM don_hang_tq AS dh
)
SELECT id, khach_hang_id, thoi_diem_dat, tong_tien
FROM don_duoc_xep
WHERE rn = 1
ORDER BY khach_hang_id;
~~~

`ROW_NUMBER` phân thứ tự bên trong mỗi nhóm khách; `rn = 1` lấy một đơn gần nhất. Với dữ liệu mẫu, kết quả giống truy vấn con tương quan có `LIMIT 1`. Trong bài toán **top N trong mỗi nhóm** hoặc cần lấy nhiều cột từ hàng đại diện, window function hoặc `LATERAL` có thể dễ đọc hơn; lựa chọn tối ưu còn phụ thuộc DBMS và chỉ mục.

## 11. Truy vấn con trong HAVING và các ngữ cảnh khác

Tương quan không giới hạn ở `WHERE`. Một subquery có thể dùng trong `SELECT`, `HAVING`, `ORDER BY` hoặc lệnh sửa dữ liệu, với điều kiện phạm vi và kiểu kết quả hợp lệ.

### 11.1. HAVING: tham chiếu khóa nhóm

Ví dụ cần liệt kê **tổ chức có ít nhất một đơn từ 450.000 trở lên**, cùng số khách của tổ chức:

~~~sql
SELECT
    kh.to_chuc_id,
    COUNT(*) AS so_khach
FROM khach_hang_tq AS kh
GROUP BY kh.to_chuc_id
HAVING EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE dh.to_chuc_id = kh.to_chuc_id
      AND dh.tong_tien >= 450000
)
ORDER BY kh.to_chuc_id;
~~~

Kết quả là tổ chức `20` với `so_khach = 2`, vì có đơn 106 trị giá `500000`. Tổ chức 10 không có đơn đạt ngưỡng đó.

Trong một truy vấn đã `GROUP BY kh.to_chuc_id`, giá trị `kh.to_chuc_id` được dùng làm **khóa nhóm**, nên có thể tham chiếu nó trong điều kiện tương quan của `HAVING`. Không nên tùy tiện dùng một cột ngoài **không thuộc nhóm và không được tổng hợp** trong cùng ngữ cảnh, vì DBMS có thể từ chối hoặc ý nghĩa không xác định.

### 11.2. UPDATE với điều kiện EXISTS

Truy vấn con tương quan có thể quyết định **những hàng nào được cập nhật**. Ví dụ giao dịch minh họa, chỉ chuyển trạng thái đơn đã thanh toán sang một nhãn xử lý khi có ít nhất một bản ghi thanh toán thành công:

~~~sql
BEGIN;

UPDATE don_hang_tq AS dh
SET trang_thai = 'CHO_GIAO'
WHERE dh.trang_thai = 'DA_THANH_TOAN'
  AND EXISTS (
      SELECT 1
      FROM thanh_toan_tq AS tt
      WHERE tt.don_hang_id = dh.id
        AND tt.ket_qua = 'THANH_CONG'
  );

SELECT id, trang_thai
FROM don_hang_tq
ORDER BY id;

ROLLBACK;
~~~

Trong dữ liệu mẫu, các đơn 101, 103, 105 và 108 thỏa điều kiện `UPDATE`. `ROLLBACK` đưa dữ liệu trở về trạng thái trước ví dụ. Đây **không phải quy trình chuyển trạng thái thanh toán đầy đủ** cho hệ thống sản xuất; cập nhật nghiệp vụ thật có thể cần giao dịch, kiểm soát đồng thời, audit và xác minh thanh toán.

Có thể dùng correlated subquery trong `DELETE` với `EXISTS`/`NOT EXISTS`, nhưng thao tác xóa dữ liệu thật phải được kiểm soát cẩn thận. Đừng nhầm ý nghĩa của một câu SELECT học tập với mức độ an toàn của lệnh ghi.

### 11.3. ORDER BY với scalar subquery

Ví dụ sắp khách theo số đơn giảm dần:

~~~sql
SELECT
    kh.id,
    kh.ten_khach_hang
FROM khach_hang_tq AS kh
ORDER BY (
    SELECT COUNT(*)
    FROM don_hang_tq AS dh
    WHERE dh.to_chuc_id = kh.to_chuc_id
      AND dh.khach_hang_id = kh.id
) DESC,
kh.id;
~~~

`COUNT(*)` là một giá trị nên có thể dùng làm khóa sắp xếp. Với truy vấn phức tạp, có thể tính `so_don` ở một CTE hoặc truy vấn con `SELECT` trước rồi `ORDER BY so_don` để tránh lặp biểu thức và tăng tính dễ đọc.

## 12. LATERAL: truy vấn trong FROM tham chiếu hàng bên trái

Trong PostgreSQL, `LATERAL` cho phép một truy vấn con ở `FROM` sử dụng giá trị của các bảng/nguồn đứng trước nó trong cùng danh sách `FROM` hoặc phía bên trái của phép JOIN tương ứng.

Ví dụ **mọi khách hàng** kèm **một đơn mới nhất nếu có**:

~~~sql
SELECT
    kh.id AS khach_hang_id,
    kh.ten_khach_hang,
    don_gan_nhat.id AS don_hang_id,
    don_gan_nhat.thoi_diem_dat,
    don_gan_nhat.tong_tien
FROM khach_hang_tq AS kh
LEFT JOIN LATERAL (
    SELECT
        dh.id,
        dh.thoi_diem_dat,
        dh.tong_tien
    FROM don_hang_tq AS dh
    WHERE dh.to_chuc_id = kh.to_chuc_id
      AND dh.khach_hang_id = kh.id
    ORDER BY dh.thoi_diem_dat DESC, dh.id DESC
    LIMIT 1
) AS don_gan_nhat ON TRUE
ORDER BY kh.id;
~~~

Kết quả giữ **sáu khách hàng**, trong đó:

| khach_hang_id | ten_khach_hang | don_hang_id |
| ---: | --- | ---: |
| 1 | An | 108 |
| 2 | Bình | 103 |
| 3 | Chi | 107 |
| 4 | Dung | 106 |
| 5 | Em | `NULL` |
| 6 | Lan | `NULL` |

Ở đây:

1. `kh` là nguồn bên trái.
2. Subquery `LATERAL` nhìn thấy `kh.id` và `kh.to_chuc_id`.
3. Nó chọn tối đa một đơn gần nhất bằng `ORDER BY ... LIMIT 1`.
4. `LEFT JOIN LATERAL ... ON TRUE` giữ khách không có đơn, điền `NULL` cho các cột đơn hàng.

Nếu dùng `INNER JOIN LATERAL` thay vì `LEFT JOIN LATERAL` với subquery này, khách Em và Lan sẽ **không xuất hiện**, vì không có hàng bên phải được sinh ra để ghép.

### 12.1. LATERAL khác scalar subquery ở điểm nào?

| Tiêu chí | Scalar correlated subquery | LATERAL derived table |
| --- | --- | --- |
| Vị trí thường gặp | `SELECT`, `WHERE`, `ORDER BY` | `FROM` / `JOIN` |
| Giá trị trả về cho một ngữ cảnh scalar | Tối đa **một hàng, một cột** | Có thể trả **nhiều cột, nhiều hàng** |
| Tham chiếu ngoài | Tới phạm vi truy vấn bao ngoài hợp lệ | Tới nguồn đứng trước/ở bên trái theo quy tắc `LATERAL` |
| Lấy nhiều thuộc tính của đơn mới nhất | Có thể cần nhiều scalar subquery hoặc tổ chức khác | Một `LATERAL` lấy cùng lúc ID, thời gian, tiền |
| Giữ khách không có đơn | Query ngoài từ bảng khách vẫn có dòng, scalar không có hàng trả `NULL` | `LEFT JOIN LATERAL` giữ khách; `INNER JOIN LATERAL` loại khách không khớp |

Trong SQL Server, dạng bài toán tương ứng thường dùng **`CROSS APPLY`** hoặc **`OUTER APPLY`**; Oracle cũng có các khả năng `LATERAL`/`APPLY` ở phiên bản thích hợp. MySQL 8.0.14+ có hỗ trợ derived table kiểu lateral với cú pháp và giới hạn riêng. Không chép nguyên `LEFT JOIN LATERAL ... LIMIT 1` sang mọi hệ quản trị mà không đổi cú pháp.

## 13. Truy vấn con tương quan so với JOIN và GROUP BY

Nhiều câu hỏi có thể được diễn đạt theo hơn một cách. Ví dụ tính số đơn của từng khách:

**Cách A — scalar correlated subquery:**

~~~sql
SELECT
    kh.id,
    kh.ten_khach_hang,
    (
        SELECT COUNT(*)
        FROM don_hang_tq AS dh
        WHERE dh.to_chuc_id = kh.to_chuc_id
          AND dh.khach_hang_id = kh.id
    ) AS so_don
FROM khach_hang_tq AS kh
ORDER BY kh.id;
~~~

**Cách B — LEFT JOIN và GROUP BY:**

~~~sql
SELECT
    kh.id,
    kh.ten_khach_hang,
    COUNT(dh.id) AS so_don
FROM khach_hang_tq AS kh
LEFT JOIN don_hang_tq AS dh
    ON dh.to_chuc_id = kh.to_chuc_id
   AND dh.khach_hang_id = kh.id
GROUP BY kh.id, kh.ten_khach_hang
ORDER BY kh.id;
~~~

Cả hai trả sáu khách và số đơn `3,1,2,2,0,0` trong dữ liệu mẫu.

**Vì sao `COUNT(dh.id)` chứ không phải `COUNT(*)`?** Với `LEFT JOIN`, khách không có đơn vẫn tạo một dòng mở rộng chứa `dh.id = NULL`. `COUNT(*)` đếm dòng đó thành `1`, còn `COUNT(dh.id)` bỏ qua `NULL`, cho `0`.

**Cách C — tổng hợp trước rồi JOIN:**

~~~sql
WITH thong_ke_don AS (
    SELECT
        to_chuc_id,
        khach_hang_id,
        COUNT(*) AS so_don,
        SUM(tong_tien) AS tong_tien
    FROM don_hang_tq
    GROUP BY to_chuc_id, khach_hang_id
)
SELECT
    kh.id,
    kh.ten_khach_hang,
    COALESCE(tk.so_don, 0) AS so_don,
    COALESCE(tk.tong_tien, 0) AS tong_tien_hien_thi
FROM khach_hang_tq AS kh
LEFT JOIN thong_ke_don AS tk
    ON tk.to_chuc_id = kh.to_chuc_id
   AND tk.khach_hang_id = kh.id
ORDER BY kh.id;
~~~

CTE `thong_ke_don` đã đưa dữ liệu về **một dòng mỗi khách–tổ chức có đơn**, nên khi JOIN sẽ không nhân dòng khách. Cách này hữu ích khi cần nhiều chỉ tiêu cùng mức chi tiết.

### 13.1. Nên chọn cách nào?

| Nhu cầu | Lựa chọn thường rõ nghĩa |
| --- | --- |
| Chỉ hỏi “có hàng liên quan không?” | `EXISTS` |
| Chỉ hỏi “không có hàng liên quan?” | `NOT EXISTS` |
| Cần một phép đếm/tổng cho từng hàng ngoài | Scalar correlated subquery hoặc JOIN tổng hợp |
| Cần nhiều chỉ tiêu cùng một nhóm | Tổng hợp trước bằng `GROUP BY`/CTE rồi JOIN |
| Cần nhiều cột từ hàng gần nhất | Window function hoặc `LATERAL`/APPLY |
| Cần mọi dòng chi tiết khớp | `INNER JOIN` thông thường |
| Cần giữ cả hàng ngoài không có hàng con | `LEFT JOIN`, `LEFT JOIN LATERAL` hoặc scalar subquery phù hợp |

Không có quy tắc “truy vấn con tương quan luôn chậm” hoặc “JOIN luôn nhanh”. Cùng một câu SQL có thể được tối ưu hóa thành các kế hoạch khác nhau theo phiên bản DBMS, số dòng và thống kê.

## 14. Phạm vi tổ chức, khóa ghép và nguy cơ ghép nhầm

Trong bộ dữ liệu mẫu, `khach_hang_tq.id` là khóa chính **toàn cục**, nên `dh.khach_hang_id = kh.id` đủ để xác định đúng hàng khách về mặt khóa. Tuy nhiên lược đồ còn định nghĩa **khóa ngoại ghép** `(to_chuc_id, khach_hang_id)` để giữ phạm vi tổ chức.

Nếu một hệ thống khác chỉ cấp mã khách **duy nhất trong từng tổ chức**, cùng `ma_khach = 'KH001'` có thể xuất hiện tại tổ chức 10 và 20. Khi đó correlated subquery sau có thể sai:

~~~sql
-- Chỉ minh họa lỗi nếu ma_khach chỉ duy nhất trong phạm vi tổ chức:
-- WHERE EXISTS (
--     SELECT 1
--     FROM don_theo_to_chuc AS dh
--     WHERE dh.ma_khach = kh.ma_khach
-- )
~~~

Điều kiện đúng thường phải gồm **cả mã tổ chức và mã khách**:

~~~sql
-- Mẫu mô hình khóa ghép:
-- WHERE EXISTS (
--     SELECT 1
--     FROM don_theo_to_chuc AS dh
--     WHERE dh.to_chuc_id = kh.to_chuc_id
--       AND dh.ma_khach = kh.ma_khach
-- )
~~~

Truy vấn con tương quan **không tự bảo vệ phạm vi dữ liệu** nếu người viết thiếu thành phần khóa. Lỗi có thể nguy hiểm hơn một phép đếm sai: câu hỏi “khách đã có đơn chưa?” có thể trả `TRUE` vì tìm được đơn của **tổ chức khác có cùng mã**.

Đối với điều kiện quyền truy cập, cần thiết kế biện pháp kiểm soát thích hợp ở database và ứng dụng; việc viết đủ khóa trong subquery giúp biểu diễn đúng quan hệ, nhưng không thay thế toàn bộ cơ chế phân quyền.

## 15. Những lỗi phạm vi tham chiếu rất dễ mắc

### 15.1. Quên điều kiện tương quan

~~~sql
SELECT kh.id
FROM khach_hang_tq AS kh
WHERE EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE dh.trang_thai = 'DA_THANH_TOAN'
);
~~~

Vì bảng đơn có ít nhất một đơn đã thanh toán, `EXISTS` là `TRUE` với **mọi** khách. Câu này không hỏi “khách này có đơn đã thanh toán?”, mà hỏi “**toàn hệ thống** có đơn đã thanh toán không?”. Sửa bằng điều kiện `dh.khach_hang_id = kh.id` và phạm vi tổ chức thích hợp.

### 15.2. Ghép nhầm cột có cùng tên

Trong subquery:

~~~sql
-- Điều kiện không tham chiếu kh ở ngoài:
WHERE dh.khach_hang_id = dh.id
~~~

không tương đương với:

~~~sql
WHERE dh.khach_hang_id = kh.id
~~~

Cả hai vế của biểu thức thứ nhất đều thuộc bảng đơn, nên ý nghĩa hoàn toàn khác.

### 15.3. Đặt bí danh ngoài trong SELECT bên trong nhưng không có FROM tương ứng

Không được sử dụng tên bảng/alias **không nằm trong phạm vi có thể tham chiếu**. Ví dụ một truy vấn con không thể tự nhiên tham chiếu bí danh được khai báo ở một subquery **anh em** hoặc ở một bảng xuất hiện **sau** nó trong ngữ cảnh `FROM` không cho phép lateral. Cần xác định cấu trúc cấp truy vấn, dùng `LATERAL` khi phù hợp hoặc đưa phép JOIN lên cấp có thể nhìn thấy cả hai nguồn.

### 15.4. Tưởng EXISTS cần giá trị SELECT là TRUE

~~~sql
WHERE EXISTS (
    SELECT NULL
    FROM don_hang_tq AS dh
    WHERE dh.khach_hang_id = kh.id
)
~~~

Trong PostgreSQL, nếu có một hàng khớp, `EXISTS` vẫn `TRUE` dù biểu thức trong danh sách `SELECT` là `NULL`. Nó kiểm tra **sự tồn tại của hàng**, không xét xem giá trị được chọn có đúng hay khác `NULL`.

### 15.5. Tưởng scalar subquery trả nhiều dòng tự lấy dòng đầu

Không có quy tắc chung rằng scalar subquery tự chọn dòng đầu. Nếu kết quả có nhiều dòng, DBMS thường báo lỗi. Cần xác định **một giá trị tổng hợp** hoặc **một hàng đại diện có thứ tự và giới hạn rõ ràng**.

### 15.6. Tưởng NOT EXISTS và NOT IN luôn tương đương

`NOT IN` có thể chịu ảnh hưởng của `NULL` trong tập giá trị. `NOT EXISTS` xét điều kiện khớp hàng; cần dùng đúng theo ngữ nghĩa dữ liệu và xác định trường hợp khóa phía ngoài nullable.

## 16. Hiệu năng: correlated subquery không nhất thiết là N+1 truy vấn

Cách giải thích logic “với mỗi khách, kiểm tra các đơn” dễ khiến người học suy ra DBMS phải **gửi một truy vấn mới qua mạng cho mỗi khách**. Điều đó **không bắt buộc đúng**.

**N+1 query problem** trong ứng dụng thường có nghĩa code gọi database nhiều lần: một lần lấy danh sách khách và N lần riêng biệt lấy đơn cho từng khách, tạo N+1 vòng trao đổi mạng.

Một câu SQL:

~~~sql
SELECT kh.id
FROM khach_hang_tq AS kh
WHERE EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE dh.khach_hang_id = kh.id
);
~~~

là **một câu SQL gửi lên database**. Hệ quản trị có thể dùng một kế hoạch *semi-join*, hash, nested loop có index hoặc thao tác khác. Mặc dù một kế hoạch có thể thực hiện nhiều lần kiểm tra nội bộ, điều đó **không đồng nghĩa N lần round-trip từ ứng dụng**.

### 16.1. Khi nào correlated subquery có thể tốn chi phí?

Chi phí có thể tăng khi:

- Tập ngoài có rất nhiều hàng;
- Truy vấn trong phải quét bảng lớn và thiếu index hữu ích cho điều kiện tương quan;
- Subquery chứa biểu thức phức tạp, tổng hợp, sắp xếp hoặc giới hạn khiến việc tối ưu/biến đổi khó hơn;
- Điều kiện dùng hàm hoặc ép kiểu trên cột khóa làm index thông thường ít hữu ích;
- Các tham số và phân bố dữ liệu khiến kế hoạch chọn không phù hợp.

Không thể đánh giá chỉ từ việc thấy chữ `EXISTS` hay một cặp SELECT lồng nhau.

### 16.2. Index phục vụ điều kiện tương quan

Các truy vấn ở bài này thường tìm đơn theo:

~~~sql
WHERE dh.to_chuc_id = kh.to_chuc_id
  AND dh.khach_hang_id = kh.id
~~~

Trong PostgreSQL, có thể cân nhắc index:

~~~sql
CREATE INDEX idx_don_hang_tq_khach
ON don_hang_tq (to_chuc_id, khach_hang_id);
~~~

Với mẫu lấy đơn mới nhất của khách:

~~~sql
CREATE INDEX idx_don_hang_tq_khach_moi_nhat
ON don_hang_tq (
    to_chuc_id,
    khach_hang_id,
    thoi_diem_dat DESC,
    id DESC
);
~~~

Index thứ hai có thể giúp tra cứu theo khách và lấy đơn theo thứ tự mong muốn mà không cần xử lý quá nhiều hàng. Nhưng **không mặc định cần cả hai index**; index đa cột có thể phục vụ một phần workload của index ngắn hơn và mọi index đều tăng chi phí lưu trữ/ghi. Chỉ nên quyết định trên truy vấn thực tế và kế hoạch thực thi.

PostgreSQL **không tự động tạo index trên các cột khóa ngoại của bảng con** chỉ vì có `FOREIGN KEY`. Chỉ mục PK/UNIQUE ở bảng cha và các index khác là vấn đề riêng. Điều kiện tương quan theo khóa ngoại của bảng con thường đáng được xem xét về hiệu năng khi dữ liệu lớn.

### 16.3. Đọc kế hoạch với EXPLAIN

~~~sql
EXPLAIN
SELECT
    kh.id,
    kh.ten_khach_hang
FROM khach_hang_tq AS kh
WHERE EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE dh.to_chuc_id = kh.to_chuc_id
      AND dh.khach_hang_id = kh.id
);
~~~

`EXPLAIN` mô tả kế hoạch dự kiến. Có thể gặp các kiểu kế hoạch như **semi join**, **nested loop** hoặc **subplan** tùy truy vấn, dữ liệu và phiên bản. Khi cân nhắc hiệu năng, nên quan sát **số dòng ước lượng, số dòng thực tế, số lần lặp và chiến lược truy cập** ở môi trường có dữ liệu đại diện.

`EXPLAIN ANALYZE` thực thi câu truy vấn để đo lường; hãy cẩn trọng với lệnh ghi hoặc hệ thống sản xuất. Bảng tạm chỉ có vài hàng trong bài này không thể đại diện cho chi phí của hệ thống lớn.

### 16.4. So sánh với JOIN/GROUP BY bằng dữ liệu thật

Nếu phải tính nhiều số liệu theo khách như `COUNT`, `SUM`, `MAX` và tỷ lệ, một CTE tổng hợp rồi JOIN thường giúp tránh viết nhiều scalar subquery lặp đi lặp lại. Nếu chỉ cần câu hỏi tồn tại, `EXISTS` thường gọn và đúng nghĩa. Nếu cần dữ liệu chi tiết, JOIN hoặc LATERAL phù hợp hơn.

Không dùng `DISTINCT` để che việc JOIN nhân dòng thay cho phân tích **mức chi tiết kết quả**.

## 17. Những khác biệt giữa PostgreSQL, MySQL, SQL Server và Oracle

Các DBMS lớn đều hỗ trợ những ý tưởng chính của correlated subquery, nhưng một số cú pháp chọn hàng đại diện và tham chiếu ở `FROM` khác nhau:

| Nhu cầu | PostgreSQL | MySQL | SQL Server | Oracle Database |
| --- | --- | --- | --- | --- |
| Subquery tương quan trong WHERE | Có | Có | Có | Có |
| `EXISTS` / `NOT EXISTS` | Có | Có | Có | Có |
| Scalar correlated subquery | Có | Có | Có | Có |
| Giới hạn một hàng sau ORDER BY | `LIMIT 1` hoặc `FETCH FIRST 1 ROW ONLY` | `LIMIT 1` | `TOP (1)` hoặc `OFFSET ... FETCH` theo cú pháp thích hợp | `FETCH FIRST 1 ROW ONLY` ở phiên bản phù hợp |
| Derived table tham chiếu nguồn đứng trước | `LATERAL` | `LATERAL` ở phiên bản hỗ trợ | `CROSS APPLY` / `OUTER APPLY` | `LATERAL` / `CROSS APPLY` / `OUTER APPLY` theo phiên bản |
| So sánh null-safe | `IS [NOT] DISTINCT FROM` | Toán tử `<=>` và các tính năng liên quan | Tùy phiên bản có `IS [NOT] DISTINCT FROM`; có thể cần biểu thức tường minh | `IS [NOT] DISTINCT FROM` ở phiên bản hỗ trợ; các cách khác ở phiên bản cũ |
| Kiểm tra kế hoạch | `EXPLAIN`, `EXPLAIN ANALYZE` | `EXPLAIN`, công cụ theo phiên bản | Estimated/Actual Execution Plan | `EXPLAIN PLAN`, `DBMS_XPLAN` |

### 17.1. Chọn đơn mới nhất: khác cú pháp giới hạn hàng

**PostgreSQL / MySQL** thường sử dụng:

~~~sql
SELECT d2.id
FROM don_hang_tq AS d2
WHERE d2.khach_hang_id = kh.id
ORDER BY d2.thoi_diem_dat DESC, d2.id DESC
LIMIT 1
~~~

**SQL Server** thường sử dụng:

~~~sql
SELECT TOP (1) d2.id
FROM don_hang AS d2
WHERE d2.khach_hang_id = kh.id
ORDER BY d2.thoi_diem_dat DESC, d2.id DESC
~~~

**Oracle** ở phiên bản hỗ trợ cú pháp giới hạn hàng:

~~~sql
SELECT d2.id
FROM don_hang d2
WHERE d2.khach_hang_id = kh.id
ORDER BY d2.thoi_diem_dat DESC, d2.id DESC
FETCH FIRST 1 ROW ONLY
~~~

Đây là các **mẫu cú pháp riêng của từng DBMS**, không phải ba câu lệnh chạy trên cùng một hệ. Với dữ liệu đa tổ chức, phải thêm điều kiện `to_chuc_id` tương ứng như ví dụ PostgreSQL chính của bài.

### 17.2. SQL Server và APPLY

Một cách dùng SQL Server:

~~~sql
SELECT
    kh.id,
    d_moi.id AS don_hang_id
FROM khach_hang AS kh
OUTER APPLY (
    SELECT TOP (1) dh.id
    FROM don_hang AS dh
    WHERE dh.khach_hang_id = kh.id
    ORDER BY dh.thoi_diem_dat DESC, dh.id DESC
) AS d_moi;
~~~

`OUTER APPLY` giữ khách không có đơn theo vai trò tương tự `LEFT JOIN LATERAL`; `CROSS APPLY` chỉ giữ khách có hàng được trả từ phần bên phải, tương tự `INNER JOIN LATERAL` trong tình huống này. Cần xét cú pháp và kế hoạch của SQL Server thật khi chuyển ứng dụng.

### 17.3. Null, collation và kiểu dữ liệu vẫn ảnh hưởng kết quả

Về cơ bản, `NULL = NULL` không khớp trong điều kiện tương quan dùng `=`. Nhưng một số DBMS có toán tử hoặc tùy chọn so sánh khác. Với khóa chuỗi, collation có thể làm hai mã chỉ khác hoa/thường được coi là bằng nhau hoặc khác nhau. Vì vậy **cùng câu correlated subquery về mặt chữ viết có thể cho kết quả khác** nếu kiểu dữ liệu, collation, chuẩn hóa và ràng buộc khác nhau.

Không tự suy diễn từ một truy vấn PostgreSQL sang hệ khác khi có `LIMIT`, `LATERAL`, kiểu chuỗi, khóa nullable hay điều kiện đặc biệt.

## 18. Bảng tổng hợp các sai sót thường gặp

| Sai sót | Vì sao nguy hiểm | Cách khắc phục |
| --- | --- | --- |
| Quên `dh.khach_hang_id = kh.id` | `EXISTS` trở thành điều kiện toàn cục, có thể giữ mọi khách | Đưa khóa ngoài vào điều kiện trong subquery |
| Viết `khach_hang_id = id` không bí danh | `id` có thể được phân giải ở bảng trong thay vì bảng ngoài | Viết `dh.khach_hang_id = kh.id` tường minh |
| Dùng cùng bí danh ở hai cấp | Bí danh trong che khuất bí danh ngoài | Đặt tên alias khác nhau theo vai trò |
| Bỏ `to_chuc_id` ở khóa ghép | Kết quả sai phạm vi tổ chức, có thể lộ thông tin | Ghép đủ các thành phần khóa và kiểm soát phân quyền |
| `NOT IN` với tập con chứa `NULL` | Có thể không trả hàng dù có đơn không khớp | Dùng `NOT EXISTS` với điều kiện khớp rõ |
| Tưởng `EXISTS (SELECT NULL ...)` là FALSE | EXISTS quan tâm **có hàng**, không quan tâm giá trị SELECT | Dùng EXISTS đúng mục đích |
| Scalar subquery có nhiều dòng | Không có một giá trị duy nhất; DBMS báo lỗi | Tổng hợp hoặc chọn một hàng đại diện bằng thứ tự rõ |
| Dùng `MAX(id)` làm đơn mới nhất | ID lớn nhất không bảo đảm thời điểm mới nhất | Sắp theo thời điểm và tiêu chí phá hòa |
| `NOT EXISTS` để kiểm tra mọi đơn đã thanh toán mà quên kiểm tra có đơn | Khách không có đơn cũng thỏa điều kiện phủ định | Thêm `EXISTS` yêu cầu ít nhất một đơn |
| Tưởng `COUNT(*)` và `SUM(...)` đều trả 0 khi không có hàng | `SUM`/ `MAX` thường là `NULL` khi tập rỗng | `COALESCE` theo ý nghĩa báo cáo |
| Dùng derived table trong FROM tham chiếu bảng ngoài không có `LATERAL` | Vượt phạm vi tên theo cú pháp tương ứng | Dùng `LATERAL`/APPLY hoặc viết lại |
| Tưởng correlated subquery luôn thực thi N query qua mạng | Một SQL có thể được optimizer biến đổi thành semi-join | Xem kế hoạch, phân biệt với N+1 ở tầng ứng dụng |
| Thay bằng JOIN rồi không xét nhân dòng | Khách có nhiều đơn tạo nhiều dòng; tổng hợp dễ bị nhân | Xác định grain; dùng EXISTS, GROUP BY hoặc tổng hợp trước |

## 19. Bài tập thực hành có lời giải

Các bài tập dùng ba bảng PostgreSQL ở mục 2. Khi giải, hãy xác định **bí danh nào thuộc phạm vi trong/ngoài**, sau đó dự đoán số dòng hoặc giá trị. Một số câu chứa mã SQL cố ý sai để luyện nhận diện lỗi.

### Bài 1: Khách đã có đơn

**Yêu cầu:** liệt kê ID và tên khách có ít nhất một đơn, mỗi khách xuất hiện một lần. Dùng correlated subquery.

**Một lời giải:**

~~~sql
SELECT kh.id, kh.ten_khach_hang
FROM khach_hang_tq AS kh
WHERE EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE dh.to_chuc_id = kh.to_chuc_id
      AND dh.khach_hang_id = kh.id
)
ORDER BY kh.id;
~~~

Kết quả gồm ID `1,2,3,4`. Mức chi tiết là **mỗi khách một dòng**, không phải mỗi đơn.

### Bài 2: Khách chưa có đơn

**Yêu cầu:** tìm khách chưa từng có đơn.

**Lời giải:**

~~~sql
SELECT kh.id, kh.ten_khach_hang
FROM khach_hang_tq AS kh
WHERE NOT EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE dh.to_chuc_id = kh.to_chuc_id
      AND dh.khach_hang_id = kh.id
)
ORDER BY kh.id;
~~~

Kết quả ID `5,6` — Em và Lan. `NOT EXISTS` kiểm tra **không có hàng khớp**, không phải `COUNT(*) = NULL`.

### Bài 3: Đếm số đơn từng khách

**Yêu cầu:** giữ cả sáu khách và hiển thị số đơn, khách chưa mua là 0.

**Lời giải:**

~~~sql
SELECT
    kh.id,
    (
        SELECT COUNT(*)
        FROM don_hang_tq AS dh
        WHERE dh.khach_hang_id = kh.id
          AND dh.to_chuc_id = kh.to_chuc_id
    ) AS so_don
FROM khach_hang_tq AS kh
ORDER BY kh.id;
~~~

Kết quả lần lượt `3,1,2,2,0,0`. `COUNT(*)` trả 0 khi không có hàng khớp.

### Bài 4: Scalar subquery nhiều dòng

Cho:

~~~sql
SELECT kh.id,
       (
           SELECT dh.id
           FROM don_hang_tq AS dh
           WHERE dh.khach_hang_id = kh.id
       ) AS don_hang_id
FROM khach_hang_tq AS kh;
~~~

**Câu hỏi:** Vì sao câu này không phù hợp để lấy một ID đơn cho mỗi khách?

**Lời giải:** Khách An có ba đơn, Chi và Dung có hai đơn; scalar subquery trả hơn một hàng nên PostgreSQL báo lỗi. Muốn đơn mới nhất, thêm điều kiện tương quan đủ khóa và `ORDER BY dh.thoi_diem_dat DESC, dh.id DESC LIMIT 1`. Muốn số lượng đơn, dùng `COUNT(*)`.

### Bài 5: Phát hiện tham chiếu nhầm phạm vi

Cho:

~~~sql
SELECT kh.id
FROM khach_hang_tq AS kh
WHERE EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE khach_hang_id = id
);
~~~

**Câu hỏi:** `id` trong `WHERE` con trỏ tới bảng nào?

**Lời giải:** Tên `id` có trong `don_hang_tq AS dh` ở **cấp trong**, nên nó được hiểu là `dh.id`. Điều kiện thành `dh.khach_hang_id = dh.id`, không liên kết với `kh` ngoài. Sửa thành `dh.khach_hang_id = kh.id` (và thêm `dh.to_chuc_id = kh.to_chuc_id` nếu cần giữ phạm vi tổ chức).

### Bài 6: Trùng bí danh

Cho:

~~~sql
SELECT kh.id
FROM khach_hang_tq AS kh
WHERE EXISTS (
    SELECT 1
    FROM don_hang_tq AS kh
    WHERE kh.khach_hang_id = 1
);
~~~

**Câu hỏi:** Vì sao lấy cả sáu khách, không chỉ khách 1?

**Lời giải:** `kh` bên trong trỏ tới **bảng đơn hàng**, che khuất `kh` ở truy vấn ngoài. Vì có đơn mang `khach_hang_id = 1`, `EXISTS` là điều kiện toàn cục đúng cho mọi khách. Cần đổi alias bên trong thành `dh` và tham chiếu rõ `dh.khach_hang_id = kh.id`.

### Bài 7: NOT IN và NULL

Giả sử muốn tìm đơn **không có giao dịch thanh toán**. Có nên dùng:

~~~sql
WHERE dh.id NOT IN (
    SELECT don_hang_id
    FROM thanh_toan_tq
)
~~~

**Lời giải:** Không nên dùng nguyên dạng này với bộ dữ liệu mẫu, vì danh sách chứa `NULL`, khiến `NOT IN` không trả dòng nào. Dùng:

~~~sql
SELECT dh.id
FROM don_hang_tq AS dh
WHERE NOT EXISTS (
    SELECT 1
    FROM thanh_toan_tq AS tt
    WHERE tt.don_hang_id = dh.id
)
ORDER BY dh.id;
~~~

Kết quả là `102,104,106,107`.

### Bài 8: Đơn lớn hơn trung bình của khách

**Yêu cầu:** lấy đơn có `tong_tien` lớn hơn giá trị trung bình của chính khách sở hữu đơn đó.

**Lời giải:**

~~~sql
SELECT dh.id, dh.khach_hang_id, dh.tong_tien
FROM don_hang_tq AS dh
WHERE dh.tong_tien > (
    SELECT AVG(d2.tong_tien)
    FROM don_hang_tq AS d2
    WHERE d2.to_chuc_id = dh.to_chuc_id
      AND d2.khach_hang_id = dh.khach_hang_id
)
ORDER BY dh.id;
~~~

Kết quả ID `102,104,106,108`. Điều kiện tương quan làm phép `AVG` thay đổi theo khách, không lấy trung bình toàn hệ thống.

### Bài 9: Lấy đơn mới nhất của từng khách

**Yêu cầu:** chỉ một đơn gần nhất cho mỗi khách **có đơn**.

**Một lời giải PostgreSQL:**

~~~sql
SELECT dh.id, dh.khach_hang_id
FROM don_hang_tq AS dh
WHERE dh.id = (
    SELECT d2.id
    FROM don_hang_tq AS d2
    WHERE d2.to_chuc_id = dh.to_chuc_id
      AND d2.khach_hang_id = dh.khach_hang_id
    ORDER BY d2.thoi_diem_dat DESC, d2.id DESC
    LIMIT 1
)
ORDER BY dh.khach_hang_id;
~~~

Kết quả các cặp `(don, khach)`: `(108,1)`, `(103,2)`, `(107,3)`, `(106,4)`. `id DESC` là tiêu chí phá hòa khi thời điểm bằng nhau.

### Bài 10: “Mọi đơn đã thanh toán” và tập rỗng

**Yêu cầu:** tìm khách đã đặt **ít nhất một đơn** và **không có đơn nào khác trạng thái `DA_THANH_TOAN`**.

**Một lời giải:**

~~~sql
SELECT kh.id, kh.ten_khach_hang
FROM khach_hang_tq AS kh
WHERE EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE dh.khach_hang_id = kh.id
      AND dh.to_chuc_id = kh.to_chuc_id
)
AND NOT EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE dh.khach_hang_id = kh.id
      AND dh.to_chuc_id = kh.to_chuc_id
      AND dh.trang_thai <> 'DA_THANH_TOAN'
);
~~~

Kết quả chỉ **Bình (ID 2)**. Nếu bỏ `EXISTS` thứ nhất, Em và Lan chưa có đơn cũng đáp ứng `NOT EXISTS` thứ hai; đó là bẫy tập rỗng.

### Bài 11: Nhiều cấp tham chiếu

**Yêu cầu:** lấy khách có ít nhất một đơn gắn với giao dịch thanh toán `THANH_CONG`. Hãy chỉ rõ alias ở từng cấp.

**Lời giải:**

~~~sql
SELECT kh.id
FROM khach_hang_tq AS kh
WHERE EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE dh.to_chuc_id = kh.to_chuc_id
      AND dh.khach_hang_id = kh.id
      AND EXISTS (
          SELECT 1
          FROM thanh_toan_tq AS tt
          WHERE tt.don_hang_id = dh.id
            AND tt.ket_qua = 'THANH_CONG'
      )
)
ORDER BY kh.id;
~~~

`kh` thuộc cấp ngoài, `dh` cấp giữa và `tt` cấp trong cùng. Kết quả `1,2,4`.

### Bài 12: Giữ cả khách không có đơn khi lấy đơn gần nhất

**Yêu cầu:** một dòng mỗi khách, có ID đơn gần nhất nếu tồn tại, kể cả Em và Lan.

**Lời giải PostgreSQL:**

~~~sql
SELECT
    kh.id AS khach_hang_id,
    d_moi.id AS don_hang_id
FROM khach_hang_tq AS kh
LEFT JOIN LATERAL (
    SELECT dh.id
    FROM don_hang_tq AS dh
    WHERE dh.to_chuc_id = kh.to_chuc_id
      AND dh.khach_hang_id = kh.id
    ORDER BY dh.thoi_diem_dat DESC, dh.id DESC
    LIMIT 1
) AS d_moi ON TRUE
ORDER BY kh.id;
~~~

Kết quả có **sáu dòng**, trong đó Em và Lan có `don_hang_id = NULL`. `LATERAL` cho phép phần `FROM` bên phải tham chiếu `kh`, còn `LEFT JOIN` giữ khách không có đơn.

## 20. Chọn cách viết theo ngữ nghĩa của câu hỏi

| Câu hỏi | Grain mong muốn | Cấu trúc phù hợp |
| --- | --- | --- |
| Khách nào có đơn? | Một hàng mỗi khách có đơn | `WHERE EXISTS (SELECT 1 ... WHERE dh.khach_hang_id = kh.id)` |
| Khách nào chưa có đơn? | Một hàng mỗi khách không có đơn | `WHERE NOT EXISTS (...)` |
| Khách nào có giao dịch thanh toán thành công? | Một hàng mỗi khách thỏa điều kiện | `EXISTS` lồng nhau hoặc `EXISTS` với JOIN ở subquery |
| Mỗi khách có bao nhiêu đơn? | Một hàng mỗi khách | Scalar `SELECT COUNT(*)` tương quan hoặc LEFT JOIN/GROUP BY |
| Tổng tiền của từng khách? | Một hàng mỗi khách | Scalar `SUM` hoặc tổng hợp trước bằng CTE |
| Đơn nào lớn hơn mức trung bình của chính khách đó? | Một hàng mỗi đơn thỏa điều kiện | Scalar `AVG` tương quan trong WHERE hoặc window function |
| Một đơn gần nhất của mỗi khách? | Một hàng mỗi khách có đơn | Scalar subquery chọn ID, `ROW_NUMBER` hoặc `DISTINCT ON` trong PostgreSQL |
| Mọi khách, kèm đơn gần nhất nếu có? | Một hàng mỗi khách | `LEFT JOIN LATERAL` hoặc window function kết hợp LEFT JOIN |
| Đơn không có giao dịch thanh toán? | Một hàng mỗi đơn không có thanh toán | `NOT EXISTS`, tránh bẫy `NOT IN` chứa `NULL` |
| Những bản ghi phải sửa khi có hàng liên quan? | Những hàng ghi thỏa điều kiện | `UPDATE ... WHERE EXISTS (...)` có kiểm soát giao dịch |

## 21. Kết luận: nhận diện tương quan bằng phạm vi tên

Khi đọc câu SQL:

~~~sql
SELECT kh.id
FROM khach_hang_tq AS kh
WHERE EXISTS (
    SELECT 1
    FROM don_hang_tq AS dh
    WHERE dh.khach_hang_id = kh.id
      AND dh.to_chuc_id = kh.to_chuc_id
);
~~~

hãy kiểm tra bốn điều:

1. **Cấp ngoài là gì?** `khach_hang_tq AS kh`; mỗi hàng ngoài biểu diễn một khách.
2. **Cấp trong là gì?** `don_hang_tq AS dh`; truy vấn con tìm các đơn khớp.
3. **Cột nào thực sự tham chiếu ra ngoài?** `kh.id` và `kh.to_chuc_id`, được lấy từ cấp ngoài.
4. **Subquery cần trả loại kết quả gì?** `EXISTS` chỉ kiểm tra có hàng; scalar subquery phải trả tối đa một hàng, một cột; `LATERAL` trong `FROM` có thể sinh nhiều cột/hàng và tham chiếu nguồn bên trái.

**Điểm cốt lõi:** một truy vấn con trở thành **tương quan** khi nó **phụ thuộc vào giá trị hoặc biểu thức ở một phạm vi truy vấn bao ngoài**. Việc dùng đúng bí danh và đầy đủ thành phần khóa bảo đảm truy vấn tìm đúng hàng liên quan. `EXISTS`/`NOT EXISTS` phù hợp với câu hỏi tồn tại/không tồn tại; subquery tổng hợp phù hợp với một giá trị theo hàng ngoài; `LATERAL`, window function và JOIN có thể giải quyết các bài toán cần nhiều cột hoặc nhiều dòng. Khi cần tối ưu, hãy giữ đúng ngữ nghĩa trước, sau đó kiểm tra kế hoạch thực thi thay vì đoán số lần chạy dựa trên hình thức SQL.

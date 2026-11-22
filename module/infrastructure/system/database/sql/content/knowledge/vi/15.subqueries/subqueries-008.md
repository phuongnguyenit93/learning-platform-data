# Chọn giữa JOIN, truy vấn con và CTE theo mục đích trong SQL

Khi một truy vấn cần dữ liệu từ nhiều nguồn hoặc phải tính toán qua nhiều bước, bạn thường có hơn một cách viết SQL. Chẳng hạn, để tìm **khách hàng đã từng thanh toán**, ta có thể kết nối bảng khách hàng với đơn hàng bằng `JOIN`, kiểm tra sự tồn tại bằng `EXISTS` hoặc lọc khóa qua truy vấn con `IN`. Với báo cáo doanh thu, có thể tổng hợp trong một bảng dẫn xuất (derived table), dùng truy vấn con tương quan hoặc chia thành các bước `WITH ... AS (...)`, còn gọi là **CTE** (*Common Table Expression*).

Các cách viết ấy **không phải lúc nào cũng thay thế nhau được**. Một `JOIN` có thể làm một khách hàng xuất hiện nhiều lần; `EXISTS` chỉ trả lời có hay không; truy vấn con vô hướng đòi hỏi kết quả tối đa một hàng; còn CTE chủ yếu giúp đặt tên và tổ chức các bước xử lý. Việc chọn đúng cách viết trước hết là quyết định về **ý nghĩa kết quả**, rồi mới đến tính dễ đọc và hiệu năng.

Bài học này thuộc chương **Truy vấn con** của module **Database SQL**. Ta sẽ dùng một bộ dữ liệu PostgreSQL tự chứa, giải cùng loại yêu cầu bằng nhiều kỹ thuật, giải thích kết quả, rủi ro `NULL`, bội số dòng sau JOIN, và cách đánh giá hiệu năng thay vì chọn theo định kiến.

## 1. Bốn công cụ cần phân biệt

### 1.1. JOIN: ghép các nguồn dữ liệu

`JOIN` tạo kết quả bằng cách kết hợp các hàng của hai nguồn theo một điều kiện. Đây là lựa chọn tự nhiên khi cần **lấy cột từ nhiều bảng** hoặc ghép dữ liệu dựa trên quan hệ.

~~~sql
SELECT
    kh.ho_ten,
    dh.id AS ma_don
FROM khach_hang AS kh
JOIN don_hang AS dh
    ON dh.khach_hang_id = kh.id;
~~~

Đây là ví dụ cú pháp, chưa phải các bảng được tạo trong bài. Nó trả **một hàng cho mỗi cặp khách hàng–đơn hàng khớp**. Một khách hàng có ba đơn thường xuất hiện ba lần.

### 1.2. Truy vấn con: đặt một SELECT bên trong truy vấn khác

Truy vấn con (*subquery*) có nhiều vị trí:

- Trong `WHERE`, kiểm tra điều kiện như `IN`, `EXISTS`, `NOT EXISTS`.
- Trong `SELECT`, trả một giá trị cho mỗi hàng, thường là **scalar subquery**.
- Trong `FROM` hoặc `JOIN`, tạo một nguồn dữ liệu dạng bảng, thường gọi là **bảng dẫn xuất** (*derived table*).
- Trong `HAVING`, so sánh kết quả nhóm với giá trị do một truy vấn khác tính ra.

Ví dụ kiểm tra khách hàng có đơn:

~~~sql
SELECT kh.ho_ten
FROM khach_hang AS kh
WHERE EXISTS (
    SELECT 1
    FROM don_hang AS dh
    WHERE dh.khach_hang_id = kh.id
);
~~~

Ở đây truy vấn con trả lời **có ít nhất một dòng hay không**, không đưa tất cả dòng đơn hàng vào kết quả ngoài.

### 1.3. CTE: đặt tên một kết quả trung gian trong cùng câu lệnh

~~~sql
WITH don_paid AS (
    SELECT id, khach_hang_id
    FROM don_hang
    WHERE trang_thai = 'PAID'
)
SELECT kh.ho_ten, dp.id
FROM khach_hang AS kh
JOIN don_paid AS dp
    ON dp.khach_hang_id = kh.id;
~~~

`don_paid` là tên được khai báo trong mệnh đề `WITH`; nó có phạm vi trong **statement hiện tại**, không phải bảng vĩnh viễn để các statement sau tự truy cập.

CTE đặc biệt hữu ích để mô tả truy vấn **theo từng bước có tên**, nhất là khi có nhiều phép lọc, tính tổng, xếp hạng hoặc cùng một kết quả trung gian được tham chiếu ở nhiều nơi.

### 1.4. Bảng dẫn xuất: truy vấn con ở vị trí nguồn dữ liệu

~~~sql
SELECT kh.ho_ten, x.so_don
FROM khach_hang AS kh
LEFT JOIN (
    SELECT khach_hang_id, COUNT(*) AS so_don
    FROM don_hang
    GROUP BY khach_hang_id
) AS x
    ON x.khach_hang_id = kh.id;
~~~

Bảng dẫn xuất `x` có một hàng theo `khach_hang_id`, vì vậy dễ ghép với bảng khách hàng mà không nhân số dòng theo từng đơn.

**Điểm phân biệt:** CTE và bảng dẫn xuất đều có thể tạo **nguồn dữ liệu logic** cho phần truy vấn tiếp theo; JOIN là **phép kết hợp nguồn**; còn các truy vấn con trong `EXISTS` hay biểu thức vô hướng có vai trò khác. Một câu SQL có thể dùng **cả JOIN, truy vấn con và CTE cùng lúc**.

## 2. Bảng lựa chọn nhanh theo mục đích

| Bạn đang muốn làm gì? | Cách thường phù hợp | Vì sao? |
|---|---|---|
| Lấy tên khách hàng kèm từng đơn | `JOIN ... ON` | Cần cột từ cả hai bảng và một dòng theo từng cặp khớp |
| Giữ khách hàng chưa có đơn | `LEFT JOIN` | Giữ phía trái ngay cả khi phía phải không khớp |
| Chỉ hỏi “khách hàng có đơn PAID không?” | `EXISTS` | Kiểm tra sự tồn tại, không nhân khách hàng theo số đơn |
| Hỏi “khách hàng chưa có đơn PAID?” | `NOT EXISTS` | Diễn đạt không tồn tại, tránh bẫy NULL của `NOT IN` |
| Lọc ID thuộc tập giá trị trả bởi truy vấn khác | `IN (SELECT ...)` hoặc `EXISTS` | Biểu đạt tư cách thành viên/tồn tại |
| So sánh với một tổng hoặc trung bình chung | Truy vấn con vô hướng | Kết quả cần một giá trị làm ngưỡng |
| Hiển thị số đơn cho từng khách hàng | `LEFT JOIN` vào kết quả `GROUP BY`, hoặc scalar subquery | Đưa số đếm về đúng một hàng mỗi khách |
| Tổng hợp các dòng chi tiết trước khi ghép với đơn | Bảng dẫn xuất/CTE + `JOIN` | Kiểm soát mức chi tiết và tránh nhân số |
| Có nhiều bước lọc, tổng hợp, xếp hạng | CTE | Đặt tên từng bước, dễ đọc và bảo trì |
| Dùng một kết quả trung gian ở nhiều nơi trong statement | CTE | Tránh phải lặp lại đoạn SQL, dù không hứa chỉ thực thi một lần |
| Lấy một dòng phụ thuộc vào từng dòng bên ngoài | `LATERAL`/`APPLY` hoặc window function | Hữu ích cho “bản ghi mới nhất theo từng đối tượng” |
| Duyệt cấu trúc phân cấp như cây quản lý | CTE đệ quy | Dùng `WITH RECURSIVE` ở DBMS hỗ trợ |

Không có quy tắc “truy vấn con luôn chậm hơn JOIN” hay “CTE luôn nhanh hơn subquery”. Phần lớn quyết định đầu tiên là **số hàng cần trả**, **điều kiện tồn tại**, **độ rõ của câu SQL** và **cách xử lý NULL**. Hiệu năng được đánh giá sau bằng kế hoạch truy vấn và dữ liệu thật.

## 3. Bộ dữ liệu thực hành PostgreSQL

Các ví dụ dùng cơ sở dữ liệu bán hàng nhỏ. Hãy chạy các lệnh sau trong **PostgreSQL thử nghiệm**, cùng một phiên kết nối. Những bảng `TEMP` chỉ tồn tại trong phiên hiện tại, giúp không tạo bảng nghiệp vụ lâu dài trong hệ thống.

### 3.1. Tạo bảng khách hàng, đơn hàng, sản phẩm và dòng chi tiết

~~~sql
CREATE TEMP TABLE jc_khach_hang (
    id INTEGER PRIMARY KEY,
    ho_ten VARCHAR(100) NOT NULL,
    khu_vuc VARCHAR(20) NOT NULL
);

CREATE TEMP TABLE jc_don_hang (
    id INTEGER PRIMARY KEY,
    khach_hang_id INTEGER NOT NULL
        REFERENCES jc_khach_hang(id),
    ngay_dat DATE NOT NULL,
    trang_thai VARCHAR(20) NOT NULL
        CHECK (trang_thai IN ('NEW', 'PAID', 'CANCELLED'))
);

CREATE TEMP TABLE jc_san_pham (
    id INTEGER PRIMARY KEY,
    ten VARCHAR(100) NOT NULL
);

CREATE TEMP TABLE jc_chi_tiet_don (
    don_hang_id INTEGER NOT NULL
        REFERENCES jc_don_hang(id),
    san_pham_id INTEGER NOT NULL
        REFERENCES jc_san_pham(id),
    so_luong INTEGER NOT NULL CHECK (so_luong > 0),
    don_gia NUMERIC(12,2) NOT NULL CHECK (don_gia >= 0),
    PRIMARY KEY (don_hang_id, san_pham_id)
);
~~~

Quan hệ chính:

~~~text
jc_khach_hang (1) ── (N) jc_don_hang
                              │
                              │ (1)
                              │
                              └── (N) jc_chi_tiet_don (N) ── (1) jc_san_pham
~~~

Một khách hàng có thể có nhiều đơn. Mỗi đơn có thể có nhiều dòng sản phẩm, hoặc chưa có dòng nào. `don_gia` trong bảng chi tiết là giá ghi nhận trên dòng đơn mẫu, không phải giá hiện tại trong bảng sản phẩm.

### 3.2. Nạp dữ liệu mẫu

~~~sql
INSERT INTO jc_khach_hang (id, ho_ten, khu_vuc) VALUES
    (1, 'An',   'Bắc'),
    (2, 'Bình', 'Nam'),
    (3, 'Chi',  'Bắc'),
    (4, 'Dũng', 'Trung'),
    (5, 'Hà',   'Nam');

INSERT INTO jc_don_hang
    (id, khach_hang_id, ngay_dat, trang_thai)
VALUES
    (101, 1, DATE '2026-11-01', 'PAID'),
    (102, 1, DATE '2026-11-03', 'NEW'),
    (103, 2, DATE '2026-11-04', 'PAID'),
    (104, 2, DATE '2026-11-05', 'CANCELLED'),
    (105, 4, DATE '2026-11-06', 'PAID'),
    (106, 4, DATE '2026-11-08', 'PAID'),
    (107, 5, DATE '2026-11-09', 'NEW');

INSERT INTO jc_san_pham (id, ten) VALUES
    (10, 'Sách SQL'),
    (20, 'Sổ tay'),
    (30, 'Bút');

INSERT INTO jc_chi_tiet_don
    (don_hang_id, san_pham_id, so_luong, don_gia)
VALUES
    (101, 10, 2, 100000),
    (101, 20, 1,  30000),
    (102, 30, 3,  10000),
    (103, 10, 1, 100000),
    (103, 30, 2,  10000),
    (104, 20, 1,  30000),
    (105, 20, 2,  30000),
    (105, 30, 1,      0);
~~~

Bộ dữ liệu có **5 khách hàng**, **7 đơn hàng**, **3 sản phẩm** và **8 dòng chi tiết**.

Những trường hợp được cố ý đưa vào:

- **Chi (ID 3) chưa có đơn**.
- **Hà (ID 5) có một đơn NEW nhưng chưa có đơn PAID**.
- **Dũng (ID 4) có hai đơn PAID**, trong đó đơn 106 chưa có dòng chi tiết.
- Đơn 101 và 103 có **nhiều dòng chi tiết**, nên JOIN trực tiếp có thể nhân hàng.
- Một dòng của đơn 105 có `don_gia = 0`, nhưng đó vẫn là dòng chi tiết tồn tại thật.

### 3.3. Kết quả mẫu để đối chiếu

Tổng tiền mỗi đơn, nếu đơn chưa có chi tiết được quy ước hiển thị là 0:

| Đơn | Khách hàng | Trạng thái | Số dòng chi tiết | Tổng tiền |
|---:|---|---|---:|---:|
| 101 | An | PAID | 2 | 230000 |
| 102 | An | NEW | 1 | 30000 |
| 103 | Bình | PAID | 2 | 120000 |
| 104 | Bình | CANCELLED | 1 | 30000 |
| 105 | Dũng | PAID | 2 | 60000 |
| 106 | Dũng | PAID | 0 | 0 |
| 107 | Hà | NEW | 0 | 0 |

Tổng tiền theo **đơn PAID**:

| Khách hàng | Số đơn PAID | Tổng tiền từ chi tiết đơn PAID |
|---|---:|---:|
| An | 1 | 230000 |
| Bình | 1 | 120000 |
| Chi | 0 | 0 |
| Dũng | 2 | 60000 |
| Hà | 0 | 0 |

Đây là tổng giá trị **dòng chi tiết của các đơn có trạng thái PAID trong dữ liệu mẫu**. Không mặc nhiên xem đó là doanh thu kế toán thực tế vì hệ thống thật có thể cần các quy tắc thuế, hoàn tiền, chiết khấu và thời điểm ghi nhận khác.

## 4. Trường hợp 1: cần cột từ hai bảng → JOIN

Yêu cầu: **liệt kê từng đơn hàng cùng tên khách hàng**.

~~~sql
SELECT
    dh.id AS ma_don,
    kh.ho_ten,
    dh.trang_thai,
    dh.ngay_dat
FROM jc_don_hang AS dh
JOIN jc_khach_hang AS kh
    ON kh.id = dh.khach_hang_id
ORDER BY dh.id;
~~~

Kết quả:

| ma_don | ho_ten | trang_thai | ngay_dat |
|---:|---|---|---|
| 101 | An | PAID | 2026-11-01 |
| 102 | An | NEW | 2026-11-03 |
| 103 | Bình | PAID | 2026-11-04 |
| 104 | Bình | CANCELLED | 2026-11-05 |
| 105 | Dũng | PAID | 2026-11-06 |
| 106 | Dũng | PAID | 2026-11-08 |
| 107 | Hà | NEW | 2026-11-09 |

`JOIN` ở đây tạo **một hàng cho mỗi đơn**, vì mỗi đơn trỏ đến đúng một khách hàng qua khóa ngoại. Điều kiện `kh.id = dh.khach_hang_id` phản ánh quan hệ dữ liệu.

### 4.1. JOIN có thể nhân số dòng ở quan hệ một-nhiều

Nếu đảo chiều và bắt đầu từ khách hàng:

~~~sql
SELECT
    kh.id,
    kh.ho_ten,
    dh.id AS ma_don
FROM jc_khach_hang AS kh
JOIN jc_don_hang AS dh
    ON dh.khach_hang_id = kh.id
ORDER BY kh.id, dh.id;
~~~

Kết quả có **7 dòng**. An xuất hiện hai lần, Bình hai lần và Dũng hai lần. **Chi không xuất hiện** vì không có đơn.

Đó không phải lỗi SQL: mỗi cặp khớp tạo một hàng. Nhưng nếu yêu cầu chỉ là “danh sách khách hàng đã đặt đơn, **mỗi khách một dòng**”, phép JOIN trực tiếp cần xử lý thêm hoặc nên dùng `EXISTS`.

### 4.2. Giữ khách hàng chưa có đơn → LEFT JOIN

~~~sql
SELECT
    kh.id,
    kh.ho_ten,
    dh.id AS ma_don
FROM jc_khach_hang AS kh
LEFT JOIN jc_don_hang AS dh
    ON dh.khach_hang_id = kh.id
ORDER BY kh.id, dh.id;
~~~

Kết quả có **8 dòng**: bảy cặp khách–đơn và thêm một dòng cho **Chi** với `ma_don = NULL`.

`LEFT JOIN` hữu ích khi cần giữ toàn bộ bên trái để hiển thị khách hàng chưa có dữ liệu liên quan. Nhưng nếu muốn **mỗi khách hàng một dòng**, JOIN vẫn có thể nhân khách hàng có nhiều đơn; cần `GROUP BY`, một bảng tổng hợp hoặc kỹ thuật tồn tại phù hợp.

### 4.3. Xác định cấp hạt dữ liệu trước khi JOIN

Trước khi viết JOIN, hỏi:

> “Một hàng kết quả cuối cùng đại diện cho **một khách hàng**, **một đơn**, hay **một dòng sản phẩm trong đơn**?”

Nếu mục tiêu là một hàng mỗi đơn, có thể JOIN khách hàng 1:1 theo đơn mà không nhân số đơn. Nhưng JOIN thêm `jc_chi_tiet_don` sẽ tạo **một hàng mỗi dòng chi tiết** cho các đơn có chi tiết, và các đơn không có chi tiết bị loại nếu dùng INNER JOIN. Thay đổi đó có thể đúng cho báo cáo dòng hàng, nhưng sai cho bảng tổng số đơn.

## 5. Trường hợp 2: chỉ kiểm tra tồn tại → EXISTS

Yêu cầu: **liệt kê khách hàng có ít nhất một đơn PAID, mỗi khách hàng đúng một hàng**.

### 5.1. JOIN trực tiếp có thể làm lặp khách hàng

~~~sql
SELECT
    kh.id,
    kh.ho_ten
FROM jc_khach_hang AS kh
JOIN jc_don_hang AS dh
    ON dh.khach_hang_id = kh.id
WHERE dh.trang_thai = 'PAID'
ORDER BY kh.id;
~~~

Kết quả là **4 dòng**:

| id | ho_ten |
|---:|---|
| 1 | An |
| 2 | Bình |
| 4 | Dũng |
| 4 | Dũng |

Dũng có hai đơn PAID (105 và 106), nên xuất hiện hai lần. Khi chỉ hỏi **có hay không**, bạn không cần những bản ghi đơn cụ thể trong kết quả ngoài.

### 5.2. EXISTS diễn đạt đúng câu hỏi “có hay không”

~~~sql
SELECT
    kh.id,
    kh.ho_ten
FROM jc_khach_hang AS kh
WHERE EXISTS (
    SELECT 1
    FROM jc_don_hang AS dh
    WHERE dh.khach_hang_id = kh.id
      AND dh.trang_thai = 'PAID'
)
ORDER BY kh.id;
~~~

Kết quả:

| id | ho_ten |
|---:|---|
| 1 | An |
| 2 | Bình |
| 4 | Dũng |

`EXISTS` trả TRUE nếu truy vấn con có **ít nhất một hàng**. Nó không cộng thêm một hàng bên ngoài cho mỗi đơn PAID. Do đó, mỗi khách hàng từ `jc_khach_hang` vẫn xuất hiện tối đa một lần, miễn bảng khách hàng không có các ID lặp.

Ở truy vấn trên:

- `kh.id` là cột của truy vấn **bên ngoài**.
- `dh.khach_hang_id` và `dh.trang_thai` là cột của truy vấn **bên trong**.
- Điều kiện `dh.khach_hang_id = kh.id` làm truy vấn con **tương quan** (*correlated*) với hàng bên ngoài.

### 5.3. Vì sao SELECT 1 trong EXISTS?

~~~sql
WHERE EXISTS (
    SELECT 1
    FROM jc_don_hang AS dh
    WHERE dh.khach_hang_id = kh.id
)
~~~

`EXISTS` chỉ quan tâm truy vấn con **có hàng nào không**, không dùng giá trị cụ thể trong danh sách SELECT. Vì thế `SELECT 1` là cách viết dễ đọc để nhấn mạnh tính tồn tại.

Không nên nghĩ SQL bắt buộc phải lấy số 1 rồi so sánh giá trị ấy. Về ngữ nghĩa, `EXISTS (SELECT 1 ...)` và `EXISTS (SELECT dh.id ...)` thường tương đương cho điều kiện tồn tại. Bộ tối ưu có thể thực thi như một dạng **semi-join**, không nhất thiết phải chạy từng subquery nguyên vẹn theo cách thủ công cho mọi hàng.

### 5.4. JOIN DISTINCT có thay EXISTS được không?

Trong bài toán nhỏ này:

~~~sql
SELECT DISTINCT
    kh.id,
    kh.ho_ten
FROM jc_khach_hang AS kh
JOIN jc_don_hang AS dh
    ON dh.khach_hang_id = kh.id
WHERE dh.trang_thai = 'PAID'
ORDER BY kh.id;
~~~

cũng trả An, Bình và Dũng một lần. Nhưng `DISTINCT` là phép loại trùng **sau khi xác định các dòng kết quả**, còn `EXISTS` diễn đạt ngay từ đầu câu hỏi có tồn tại hay không.

Nếu chỉ cần kiểm tra sự tồn tại và không cần cột của bảng đơn, **`EXISTS` thường là lựa chọn dễ hiểu hơn**. Không nên mặc định DISTINCT luôn sai hoặc EXISTS luôn nhanh hơn; việc chọn kế hoạch thực thi tùy optimizer và dữ liệu.

## 6. Trường hợp 3: kiểm tra không tồn tại → NOT EXISTS

Yêu cầu: **tìm khách hàng chưa có đơn PAID**.

~~~sql
SELECT
    kh.id,
    kh.ho_ten
FROM jc_khach_hang AS kh
WHERE NOT EXISTS (
    SELECT 1
    FROM jc_don_hang AS dh
    WHERE dh.khach_hang_id = kh.id
      AND dh.trang_thai = 'PAID'
)
ORDER BY kh.id;
~~~

Kết quả:

| id | ho_ten |
|---:|---|
| 3 | Chi |
| 5 | Hà |

- **Chi:** chưa có bất kỳ đơn nào.
- **Hà:** có đơn 107, nhưng trạng thái NEW chứ không phải PAID.

Hai người đáp ứng câu hỏi “chưa có đơn PAID”, dù lý do khác nhau.

### 6.1. “Chưa có đơn” khác “chưa có đơn PAID”

Nếu thay đổi mục tiêu sang **khách hàng chưa từng đặt đơn**, bỏ điều kiện trạng thái:

~~~sql
SELECT
    kh.id,
    kh.ho_ten
FROM jc_khach_hang AS kh
WHERE NOT EXISTS (
    SELECT 1
    FROM jc_don_hang AS dh
    WHERE dh.khach_hang_id = kh.id
)
ORDER BY kh.id;
~~~

Kết quả chỉ có **Chi**.

`NOT EXISTS` trả lời chính xác điều kiện phủ định đối với tập đã mô tả trong truy vấn con. Nó không tự hiểu “đơn hàng hợp lệ” hoặc “đã phát sinh doanh thu”; những điều kiện đó phải được viết ra.

### 6.2. LEFT JOIN ... IS NULL như một cách anti-join

Cũng có thể tìm khách chưa có đơn PAID bằng:

~~~sql
SELECT
    kh.id,
    kh.ho_ten
FROM jc_khach_hang AS kh
LEFT JOIN jc_don_hang AS dh
    ON dh.khach_hang_id = kh.id
   AND dh.trang_thai = 'PAID'
WHERE dh.id IS NULL
ORDER BY kh.id;
~~~

Kết quả vẫn là Chi và Hà. Đây là kiểu **anti-join** dùng LEFT JOIN rồi kiểm tra **khóa không NULL của nguồn bên phải**.

`NOT EXISTS` thường thể hiện ý nghĩa “không tồn tại dòng phù hợp” ngắn gọn hơn, nhất là khi điều kiện nhiều cột. Cả hai có thể hiệu quả; cần dùng `EXPLAIN` trên cơ sở dữ liệu thực tế nếu hiệu năng quan trọng.

## 7. IN, EXISTS và cái bẫy NOT IN khi có NULL

### 7.1. IN: cột thuộc tập giá trị từ truy vấn con

~~~sql
SELECT
    kh.id,
    kh.ho_ten
FROM jc_khach_hang AS kh
WHERE kh.id IN (
    SELECT dh.khach_hang_id
    FROM jc_don_hang AS dh
    WHERE dh.trang_thai = 'PAID'
)
ORDER BY kh.id;
~~~

Kết quả cũng là **An, Bình, Dũng**. `IN` rất dễ hiểu khi truy vấn con trả một cột ID dùng để so sánh.

Ở bộ dữ liệu thực hành, `dh.khach_hang_id` có `NOT NULL` nên tình huống NULL trong tập khóa không xuất hiện. Tuy nhiên, với những truy vấn con khác có thể trả NULL, cần hiểu logic SQL ba giá trị.

### 7.2. Vì sao NOT IN có thể bất ngờ không trả hàng?

Thử ví dụ độc lập trong PostgreSQL:

~~~sql
SELECT a.id
FROM (
    VALUES (1), (2), (3)
) AS a(id)
WHERE a.id NOT IN (
    SELECT b.id
    FROM (
        VALUES (1), (NULL::INTEGER)
    ) AS b(id)
)
ORDER BY a.id;
~~~

**Kết quả: không có dòng nào.**

Với `a.id = 1`, tập có 1 nên điều kiện `NOT IN` là FALSE. Với `a.id = 2` hoặc 3, tập con không có 2/3 nhưng **có NULL**. Phép so sánh với NULL cho UNKNOWN, khiến `NOT IN` không trở thành TRUE, và `WHERE` không chọn dòng.

Đây là một trong những lỗi phổ biến nhất khi viết “không thuộc tập” bằng `NOT IN`.

### 7.3. Khi nào NOT IN vẫn có thể dùng?

Nếu bạn biết chắc **giá trị ở truy vấn ngoài và mọi giá trị của truy vấn con không NULL**, và các kiểu so sánh phù hợp, `NOT IN` có thể diễn đạt yêu cầu rõ ràng.

Ví dụ với khóa `jc_don_hang.khach_hang_id NOT NULL`:

~~~sql
SELECT kh.id, kh.ho_ten
FROM jc_khach_hang AS kh
WHERE kh.id NOT IN (
    SELECT dh.khach_hang_id
    FROM jc_don_hang AS dh
    WHERE dh.trang_thai = 'PAID'
)
ORDER BY kh.id;
~~~

Kết quả là Chi và Hà trong bộ dữ liệu này. Tuy nhiên, khi truy vấn con có thể chứa NULL do bảng/biểu thức khác, **`NOT EXISTS` thường an toàn và thể hiện điều kiện không tồn tại tốt hơn**.

Đừng sửa sự cố NOT IN bằng việc dùng `DISTINCT` trong subquery: DISTINCT không loại bỏ NULL theo cách giải quyết logic UNKNOWN của phép so sánh.

### 7.4. EXISTS và IN không đồng nghĩa ở mọi tình huống

Trong ví dụ lọc khách theo ID có đơn PAID, chúng có thể cùng kết quả. Nhưng cần thận trọng:

- `EXISTS` kiểm tra **hàng tồn tại**, không so một giá trị cụ thể với tập.
- `IN` so sánh **giá trị** với những giá trị trong tập.
- `NULL` ở biểu thức ngoài hoặc trong tập có thể khiến IN trả UNKNOWN.
- Subquery có nhiều cột hoặc điều kiện tương quan phức tạp cần xem cú pháp và ngữ nghĩa cụ thể.
- `EXISTS` thường thuận tiện khi điều kiện liên quan **nhiều cột** giữa truy vấn trong và ngoài.

**Chọn theo ý nghĩa trước:** “có dòng phù hợp?” → EXISTS; “giá trị thuộc danh sách?” → IN; “không có dòng phù hợp?” → NOT EXISTS.

## 8. Trường hợp 4: cần một giá trị để so sánh → scalar subquery

**Truy vấn con vô hướng (scalar subquery)** là subquery đặt ở vị trí biểu thức và có kết quả tối đa **một hàng, một cột**.

Ví dụ: tìm những đơn được đặt vào **ngày mới nhất trong bảng**.

~~~sql
SELECT
    dh.id,
    dh.khach_hang_id,
    dh.ngay_dat
FROM jc_don_hang AS dh
WHERE dh.ngay_dat = (
    SELECT MAX(ngay_dat)
    FROM jc_don_hang
)
ORDER BY dh.id;
~~~

Truy vấn con `SELECT MAX(ngay_dat) ...` trả **một giá trị** là `2026-11-09`. Truy vấn ngoài chọn đơn **107**.

Khi có nhiều đơn cùng ngày mới nhất, truy vấn ngoài có thể trả **nhiều đơn**, dù scalar subquery trả một ngày. Điều này đúng với mục tiêu “mọi đơn ở ngày mới nhất”.

### 8.1. Truy vấn con không tương quan

Truy vấn `SELECT MAX(ngay_dat) FROM jc_don_hang` không tham chiếu cột của truy vấn ngoài. Nó là **uncorrelated subquery**.

Một biểu thức tổng hợp như MAX không có GROUP BY trả một hàng trong trường hợp thông thường, kể cả khi bảng rỗng (khi đó giá trị là NULL). Vì vậy, nó phù hợp làm scalar subquery.

### 8.2. Nếu scalar subquery trả nhiều hàng?

Ví dụ sai ý định:

~~~sql
-- Có thể lỗi: subquery trả nhiều id.
SELECT kh.id
FROM jc_khach_hang AS kh
WHERE kh.id = (
    SELECT khach_hang_id
    FROM jc_don_hang
);
~~~

`jc_don_hang` có nhiều dòng nên subquery trả nhiều giá trị. Trong PostgreSQL, một scalar subquery được dùng với dấu `=` như trên phải có **không quá một hàng**; nhiều hàng sẽ gây lỗi.

Cách sửa phụ thuộc mục tiêu:

- Muốn “ID khách hàng thuộc những ID đặt đơn” → `IN` hoặc `EXISTS`.
- Muốn “ID bằng một giá trị duy nhất theo quy tắc” → phải định nghĩa cách lấy giá trị duy nhất, chẳng hạn một phép tổng hợp hoặc lựa chọn có `ORDER BY ... LIMIT 1` phù hợp.
- Muốn các cột từ từng dòng đơn → dùng JOIN.

**Đừng thêm LIMIT 1 chỉ để dập lỗi** nếu chưa biết vì sao cần chọn một dòng và tiêu chí nào quyết định dòng đó.

### 8.3. Subquery vô hướng trả 0 hàng và NULL

Nếu truy vấn con trả **0 hàng**, scalar subquery thông thường cho giá trị NULL:

~~~sql
SELECT (
    SELECT dh.id
    FROM jc_don_hang AS dh
    WHERE dh.id = -999
) AS ma_don_khong_ton_tai;
~~~

Kết quả: một hàng với giá trị `NULL`. Nếu cột kết quả được dùng trong so sánh `=`, logic ba giá trị có thể khiến `WHERE` không chọn dòng nào.

Trường hợp này khác `EXISTS`: EXISTS trả FALSE khi subquery không có hàng, không cần phân biệt giá trị cột của subquery.

## 9. Truy vấn con tương quan để tính chỉ số từng hàng

Yêu cầu: **hiển thị tất cả khách hàng cùng số đơn PAID**, kể cả người có 0 đơn PAID.

~~~sql
SELECT
    kh.id,
    kh.ho_ten,
    (
        SELECT COUNT(*)
        FROM jc_don_hang AS dh
        WHERE dh.khach_hang_id = kh.id
          AND dh.trang_thai = 'PAID'
    ) AS so_don_paid
FROM jc_khach_hang AS kh
ORDER BY kh.id;
~~~

Kết quả:

| id | ho_ten | so_don_paid |
|---:|---|---:|
| 1 | An | 1 |
| 2 | Bình | 1 |
| 3 | Chi | 0 |
| 4 | Dũng | 2 |
| 5 | Hà | 0 |

Đây là **correlated scalar subquery** vì có `dh.khach_hang_id = kh.id`. Giá trị đếm phụ thuộc từng khách hàng ở truy vấn ngoài.

### 9.1. Vì sao COUNT(*) cho 0?

Một truy vấn tổng hợp `COUNT(*)` **không có GROUP BY** trên tập rỗng trả 0, nên khách hàng không có đơn PAID nhận 0. Nếu thay bằng `SUM`, `AVG`, `MIN` hoặc `MAX`, tập rỗng thường cho NULL.

Ví dụ lấy số tiền từ chi tiết đơn PAID:

~~~sql
SELECT
    kh.id,
    kh.ho_ten,
    (
        SELECT SUM(ct.so_luong * ct.don_gia)
        FROM jc_don_hang AS dh
        JOIN jc_chi_tiet_don AS ct
            ON ct.don_hang_id = dh.id
        WHERE dh.khach_hang_id = kh.id
          AND dh.trang_thai = 'PAID'
    ) AS tong_paid
FROM jc_khach_hang AS kh
ORDER BY kh.id;
~~~

Kết quả: An 230000, Bình 120000, Chi NULL, Dũng 60000, Hà NULL.

`SUM` của nhóm không có dòng chi tiết phù hợp trả NULL; nếu báo cáo muốn hiển thị 0, có thể bọc biểu thức bằng `COALESCE(..., 0)`. Nhưng khi cần phân biệt “chưa có số liệu” với “giá trị đã xác nhận bằng 0”, phải giữ thêm các chỉ số hỗ trợ hoặc mô hình hóa ngữ nghĩa dữ liệu rõ ràng.

### 9.2. Có nhất thiết subquery phải chạy từng lần một?

Về **cách hiểu logic**, truy vấn con phụ thuộc `kh.id` của hàng ngoài. Nhưng không nên suy ra rằng PostgreSQL bắt buộc thực hiện một lần quét toàn bộ bảng đơn cho từng khách. Bộ tối ưu có thể dùng index, chuyển đổi thành phép JOIN hoặc chọn kế hoạch khác tùy query.

Với nhiều khách hàng và nhiều chỉ số tổng hợp, việc viết nhiều correlated subquery riêng biệt đôi khi khó đọc hoặc tốn tài nguyên; bảng dẫn xuất tổng hợp và JOIN hoặc CTE là những cách tổ chức đáng cân nhắc.

## 10. Cùng bài toán số đơn PAID: correlated subquery hay JOIN tổng hợp?

Câu ở mục 9 trả đúng một hàng cho mỗi khách hàng. Có thể viết theo hướng **tổng hợp trước, JOIN sau**.

### 10.1. Bảng dẫn xuất trong LEFT JOIN

~~~sql
SELECT
    kh.id,
    kh.ho_ten,
    COALESCE(ds.so_don_paid, 0) AS so_don_paid
FROM jc_khach_hang AS kh
LEFT JOIN (
    SELECT
        khach_hang_id,
        COUNT(*) AS so_don_paid
    FROM jc_don_hang
    WHERE trang_thai = 'PAID'
    GROUP BY khach_hang_id
) AS ds
    ON ds.khach_hang_id = kh.id
ORDER BY kh.id;
~~~

Kết quả giống bảng ở mục 9: `1, 1, 0, 2, 0` theo ID khách hàng.

**Vì sao đúng?** Bảng dẫn xuất `ds` có **tối đa một hàng cho mỗi khach_hang_id** do GROUP BY. LEFT JOIN với khách hàng không làm nhân số khách hàng; các khách không có nhóm PAID được giữ lại, với `ds.so_don_paid = NULL` và COALESCE đổi sang 0.

### 10.2. So sánh hai cách diễn đạt

| Tiêu chí | Correlated scalar subquery | LEFT JOIN bảng dẫn xuất tổng hợp |
|---|---|---|
| Ý nghĩa | Với mỗi khách, lấy một chỉ số từ tập đơn liên quan | Tạo bảng chỉ số theo khách rồi ghép |
| Kết quả ví dụ | Một hàng cho mỗi khách | Một hàng cho mỗi khách |
| Cần giữ khách không có đơn | Tự giữ vì nguồn ngoài là bảng khách | Dùng LEFT JOIN |
| Dễ thêm nhiều cột tổng hợp | Có thể cần nhiều subquery hoặc thêm kỹ thuật khác | Thêm các hàm tổng hợp trong cùng bảng dẫn xuất |
| Nguy cơ nhân dòng | Không nhân hàng ngoài khi biểu thức thật sự vô hướng | Không nhân nếu bảng tổng hợp có tối đa một hàng theo khóa JOIN |
| Hiệu năng | Phụ thuộc optimizer, index và quy mô | Phụ thuộc optimizer, index và quy mô |

Không nên khẳng định cách nào luôn tốt hơn. Với một chỉ số ngắn, subquery tương quan có thể rất rõ. Với nhiều chỉ số theo cùng khóa, một bảng tổng hợp hoặc CTE thường dễ đọc và bảo trì hơn.

## 11. Bảng dẫn xuất: tính ở một cấp rồi JOIN ở cấp khác

Yêu cầu: **liệt kê mỗi đơn cùng tổng tiền**, kể cả đơn chưa có chi tiết.

~~~sql
SELECT
    dh.id AS ma_don,
    kh.ho_ten,
    dh.trang_thai,
    COALESCE(tong.tong_tien, 0) AS tong_tien
FROM jc_don_hang AS dh
JOIN jc_khach_hang AS kh
    ON kh.id = dh.khach_hang_id
LEFT JOIN (
    SELECT
        ct.don_hang_id,
        SUM(ct.so_luong * ct.don_gia) AS tong_tien
    FROM jc_chi_tiet_don AS ct
    GROUP BY ct.don_hang_id
) AS tong
    ON tong.don_hang_id = dh.id
ORDER BY dh.id;
~~~

Kết quả:

| ma_don | ho_ten | trang_thai | tong_tien |
|---:|---|---|---:|
| 101 | An | PAID | 230000 |
| 102 | An | NEW | 30000 |
| 103 | Bình | PAID | 120000 |
| 104 | Bình | CANCELLED | 30000 |
| 105 | Dũng | PAID | 60000 |
| 106 | Dũng | PAID | 0 |
| 107 | Hà | NEW | 0 |

Trong bảng dẫn xuất:

~~~sql
SELECT
    don_hang_id,
    SUM(so_luong * don_gia) AS tong_tien
FROM jc_chi_tiet_don
GROUP BY don_hang_id
~~~

mỗi `don_hang_id` có **tối đa một dòng kết quả**. Nhờ đó, khi JOIN vào bảng đơn, mỗi đơn vẫn có một hàng, không bị nhân theo số dòng sản phẩm.

### 11.1. Đếm số dòng chi tiết ở cùng cấp

~~~sql
SELECT
    dh.id,
    COALESCE(tong.so_dong, 0) AS so_dong,
    COALESCE(tong.tong_tien, 0) AS tong_tien
FROM jc_don_hang AS dh
LEFT JOIN (
    SELECT
        don_hang_id,
        COUNT(*) AS so_dong,
        SUM(so_luong * don_gia) AS tong_tien
    FROM jc_chi_tiet_don
    GROUP BY don_hang_id
) AS tong
    ON tong.don_hang_id = dh.id
ORDER BY dh.id;
~~~

Cùng một bảng dẫn xuất có thể cung cấp nhiều chỉ số theo đơn: số dòng và tổng tiền. Đây là lý do cách tổng hợp trước rồi JOIN thường phù hợp khi muốn nhiều chỉ số ở **mức đơn hàng**.

### 11.2. Bảng dẫn xuất không lưu dữ liệu lâu dài

`FROM (SELECT ...) AS tong` tạo nguồn kết quả logic trong **statement hiện tại**. Không thể chạy một SELECT khác rồi tham chiếu trực tiếp `tong` như bảng vật lý khi statement đã kết thúc.

Nếu cần tái sử dụng lâu dài, bạn có thể cân nhắc **VIEW**; nếu cần lưu dữ liệu tạm qua nhiều statement, có thể cân nhắc **TEMP TABLE**. Đó là những đối tượng khác, có chi phí và vòng đời khác.

## 12. CTE: chia một báo cáo nhiều bước thành các khối dễ đọc

Một báo cáo thực tế có thể yêu cầu:

1. Tính tổng tiền **từng đơn**.
2. Chỉ giữ **đơn PAID**.
3. Tính **số đơn PAID và tổng tiền PAID theo khách hàng**.
4. Ghép lại để hiển thị **mọi khách hàng**, kể cả người chưa có đơn PAID.

CTE giúp đặt tên từng bước theo đúng mục đích.

~~~sql
WITH tong_tung_don AS (
    SELECT
        dh.id AS don_hang_id,
        dh.khach_hang_id,
        dh.trang_thai,
        COALESCE(SUM(ct.so_luong * ct.don_gia), 0)
            AS tong_tien
    FROM jc_don_hang AS dh
    LEFT JOIN jc_chi_tiet_don AS ct
        ON ct.don_hang_id = dh.id
    GROUP BY dh.id, dh.khach_hang_id, dh.trang_thai
),
don_paid AS (
    SELECT
        don_hang_id,
        khach_hang_id,
        tong_tien
    FROM tong_tung_don
    WHERE trang_thai = 'PAID'
),
tong_theo_khach AS (
    SELECT
        khach_hang_id,
        COUNT(*) AS so_don_paid,
        SUM(tong_tien) AS tong_paid
    FROM don_paid
    GROUP BY khach_hang_id
)
SELECT
    kh.id,
    kh.ho_ten,
    COALESCE(tk.so_don_paid, 0) AS so_don_paid,
    COALESCE(tk.tong_paid, 0) AS tong_paid
FROM jc_khach_hang AS kh
LEFT JOIN tong_theo_khach AS tk
    ON tk.khach_hang_id = kh.id
ORDER BY kh.id;
~~~

Kết quả:

| id | ho_ten | so_don_paid | tong_paid |
|---:|---|---:|---:|
| 1 | An | 1 | 230000 |
| 2 | Bình | 1 | 120000 |
| 3 | Chi | 0 | 0 |
| 4 | Dũng | 2 | 60000 |
| 5 | Hà | 0 | 0 |

### 12.1. Cách đọc chuỗi CTE

~~~text
jc_don_hang LEFT JOIN jc_chi_tiet_don
            │
            ▼
      tong_tung_don
      (một dòng / đơn)
            │
            ▼
         don_paid
      (chỉ đơn PAID)
            │
            ▼
      tong_theo_khach
      (một dòng / khách)
            │
            ▼
jc_khach_hang LEFT JOIN tong_theo_khach
            │
            ▼
    một dòng / khách hàng
~~~

Mỗi khối thể hiện **một thay đổi cấp hạt hoặc phạm vi**:

- `tong_tung_don`: mỗi dòng là một đơn.
- `don_paid`: vẫn mỗi dòng một đơn, nhưng chỉ các đơn PAID.
- `tong_theo_khach`: mỗi dòng là một khách hàng có đơn PAID.
- SELECT cuối: một dòng cho **mọi khách hàng**.

Khi cần sửa điều kiện trạng thái hoặc thêm chỉ số, các bước có tên giúp xác định vị trí thay đổi dễ hơn một câu SQL có nhiều cấp ngoặc lồng nhau.

### 12.2. CTE không phải một bảng vật lý mới

CTE không mặc nhiên lưu vĩnh viễn kết quả, và **không đảm bảo chỉ tính đúng một lần**. Bộ tối ưu có thể inline hoặc materialize tùy DBMS, phiên bản và cách dùng. Trong PostgreSQL từ 12, các CTE thường có thể được gộp vào truy vấn ngoài trong trường hợp phù hợp; một số CTE cũng có lựa chọn `MATERIALIZED` hoặc `NOT MATERIALIZED`.

Điều quan trọng ở cấp học này là: **CTE giúp tổ chức và đặt tên cho kết quả trung gian**, không phải lời hứa tăng tốc.

### 12.3. CTE có thể dùng lại trong cùng statement

~~~sql
WITH tong_don AS (
    SELECT
        dh.id,
        COALESCE(SUM(ct.so_luong * ct.don_gia), 0) AS tong_tien
    FROM jc_don_hang AS dh
    LEFT JOIN jc_chi_tiet_don AS ct
        ON ct.don_hang_id = dh.id
    GROUP BY dh.id
)
SELECT
    td.id,
    td.tong_tien,
    tb.trung_binh
FROM tong_don AS td
CROSS JOIN (
    SELECT AVG(tong_tien) AS trung_binh
    FROM tong_don
) AS tb
WHERE td.tong_tien > tb.trung_binh
ORDER BY td.tong_tien DESC, td.id;
~~~

Ở đây `tong_don` xuất hiện trong SELECT ngoài và trong bảng dẫn xuất tính trung bình. Truy vấn tính **trung bình tổng tiền của tất cả 7 đơn** (kể cả đơn có tổng 0 và đơn chưa PAID). Những đơn có giá trị vượt trung bình là **101** và **103**.

Trung bình là:

\[
\frac{230000 + 30000 + 120000 + 30000 + 60000 + 0 + 0}{7}
= \frac{470000}{7}
\approx 67142.86
\]

CTE giúp tránh chép lại đoạn tính tổng từng đơn ở hai nơi. Nhưng việc có thực thi một lần hay nhiều lần vẫn do DBMS quyết định.

## 13. Cùng một yêu cầu: ba cách viết khác nhau

Yêu cầu được chọn: **hiển thị mỗi khách hàng với số đơn PAID**, kể cả khách có 0 đơn. Dữ liệu dự kiến: An 1, Bình 1, Chi 0, Dũng 2, Hà 0.

### Cách A — Correlated scalar subquery

~~~sql
SELECT
    kh.id,
    kh.ho_ten,
    (
        SELECT COUNT(*)
        FROM jc_don_hang AS dh
        WHERE dh.khach_hang_id = kh.id
          AND dh.trang_thai = 'PAID'
    ) AS so_don_paid
FROM jc_khach_hang AS kh
ORDER BY kh.id;
~~~

Cách này gọn nếu chỉ cần một giá trị tính cho từng khách.

### Cách B — LEFT JOIN bảng dẫn xuất

~~~sql
SELECT
    kh.id,
    kh.ho_ten,
    COALESCE(x.so_don_paid, 0) AS so_don_paid
FROM jc_khach_hang AS kh
LEFT JOIN (
    SELECT
        khach_hang_id,
        COUNT(*) AS so_don_paid
    FROM jc_don_hang
    WHERE trang_thai = 'PAID'
    GROUP BY khach_hang_id
) AS x
    ON x.khach_hang_id = kh.id
ORDER BY kh.id;
~~~

Cách này tách rõ việc đếm đơn theo khách trước khi JOIN, thuận tiện khi thêm các chỉ số cùng nhóm.

### Cách C — CTE + LEFT JOIN

~~~sql
WITH so_don_paid_theo_khach AS (
    SELECT
        khach_hang_id,
        COUNT(*) AS so_don_paid
    FROM jc_don_hang
    WHERE trang_thai = 'PAID'
    GROUP BY khach_hang_id
)
SELECT
    kh.id,
    kh.ho_ten,
    COALESCE(x.so_don_paid, 0) AS so_don_paid
FROM jc_khach_hang AS kh
LEFT JOIN so_don_paid_theo_khach AS x
    ON x.khach_hang_id = kh.id
ORDER BY kh.id;
~~~

Cách B và C dùng cùng một logic tổng hợp. Khác biệt chính là vị trí khai báo nguồn tính số đơn: **bảng dẫn xuất nằm ngay trong JOIN**, còn **CTE đặt tên ở đầu statement**.

### 13.1. Chọn cách nào?

Nếu bài toán chỉ có một chỉ số ngắn, Cách A có thể dễ đọc. Nếu cần mở rộng bảng chỉ số theo khách, Cách B hoặc C thường thuận tiện. Nếu phải ghép nhiều bước phức tạp, CTE thường nổi bật về tổ chức.

**Kết quả đúng và ý nghĩa dữ liệu giống nhau mới là cơ sở để so hiệu năng.** Đừng so tốc độ của một truy vấn đếm toàn bộ đơn với truy vấn chỉ đếm PAID rồi kết luận công cụ nào nhanh hơn.

## 14. Tránh bùng nổ số hàng khi JOIN nhiều quan hệ một-nhiều

Đây là lỗi quan trọng khi quyết định có nên **JOIN trực tiếp** hay **tổng hợp trước bằng subquery/CTE**.

Yêu cầu: **một hàng mỗi khách với số đơn và tổng tiền từ dòng chi tiết**.

### 14.1. JOIN trực tiếp có thể làm COUNT sai

~~~sql
SELECT
    kh.id,
    kh.ho_ten,
    COUNT(dh.id) AS dem_sau_join
FROM jc_khach_hang AS kh
LEFT JOIN jc_don_hang AS dh
    ON dh.khach_hang_id = kh.id
LEFT JOIN jc_chi_tiet_don AS ct
    ON ct.don_hang_id = dh.id
GROUP BY kh.id, kh.ho_ten
ORDER BY kh.id;
~~~

Kết quả số đếm:

| Khách hàng | Số đơn thật | `COUNT(dh.id)` sau JOIN chi tiết |
|---|---:|---:|
| An | 2 | 3 |
| Bình | 2 | 3 |
| Chi | 0 | 0 |
| Dũng | 2 | 3 |
| Hà | 1 | 1 |

Vì đơn 101 có hai dòng chi tiết và đơn 102 có một, An xuất hiện 3 dòng sau JOIN. Bình có 2 dòng ở đơn 103 và 1 dòng ở đơn 104 nên cũng bị đếm thành 3. Dũng có 2 dòng ở đơn 105 và 1 hàng LEFT JOIN đại diện đơn 106 chưa có chi tiết, nên COUNT(dh.id) là 3. Hà có đơn 107 không có chi tiết nhưng LEFT JOIN vẫn giữ một dòng cho đơn ấy.

**Lỗi nằm ở mức chi tiết:** `COUNT(dh.id)` đếm số dòng sau JOIN, không tự đếm số đơn khác nhau.

### 14.2. DISTINCT có thể sửa một chỉ số, không sửa mọi phép tính

~~~sql
SELECT
    kh.id,
    COUNT(DISTINCT dh.id) AS so_don
FROM jc_khach_hang AS kh
LEFT JOIN jc_don_hang AS dh
    ON dh.khach_hang_id = kh.id
LEFT JOIN jc_chi_tiet_don AS ct
    ON ct.don_hang_id = dh.id
GROUP BY kh.id
ORDER BY kh.id;
~~~

`COUNT(DISTINCT dh.id)` trả đúng số đơn. Nhưng không nên dùng `SUM(DISTINCT ct.so_luong * ct.don_gia)` để “sửa” tổng tiền bị nhân: hai dòng sản phẩm khác nhau có thể có cùng thành tiền, và DISTINCT sẽ loại nhầm một khoản hợp lệ.

Khi nhiều chỉ số có **mức chi tiết nguồn khác nhau**, tốt nhất là xác định và tổng hợp chúng đúng cấp trước khi kết hợp.

### 14.3. Tổng hợp riêng hai nguồn rồi JOIN

~~~sql
WITH so_don AS (
    SELECT
        khach_hang_id,
        COUNT(*) AS so_don
    FROM jc_don_hang
    GROUP BY khach_hang_id
),
tong_tien AS (
    SELECT
        dh.khach_hang_id,
        SUM(ct.so_luong * ct.don_gia) AS tong
    FROM jc_don_hang AS dh
    JOIN jc_chi_tiet_don AS ct
        ON ct.don_hang_id = dh.id
    GROUP BY dh.khach_hang_id
)
SELECT
    kh.id,
    kh.ho_ten,
    COALESCE(sd.so_don, 0) AS so_don,
    COALESCE(tt.tong, 0) AS tong_tien_cac_dong
FROM jc_khach_hang AS kh
LEFT JOIN so_don AS sd
    ON sd.khach_hang_id = kh.id
LEFT JOIN tong_tien AS tt
    ON tt.khach_hang_id = kh.id
ORDER BY kh.id;
~~~

Kết quả:

| ho_ten | so_don | tong_tien_cac_dong |
|---|---:|---:|
| An | 2 | 260000 |
| Bình | 2 | 150000 |
| Chi | 0 | 0 |
| Dũng | 2 | 60000 |
| Hà | 1 | 0 |

Báo cáo này cố ý tính tổng dòng chi tiết **của tất cả trạng thái đơn**, gồm cả NEW và CANCELLED. Vì thế An có 230000 + 30000 = 260000, Bình có 120000 + 30000 = 150000. Nếu mục tiêu là tổng tiền PAID, cần lọc `dh.trang_thai = 'PAID'` trong CTE `tong_tien`.

Nhờ mỗi CTE được GROUP BY `khach_hang_id`, chúng có **tối đa một dòng mỗi khách**, rồi LEFT JOIN không tạo tích nhân không mong muốn.

## 15. WHERE, ON, HAVING và phạm vi của truy vấn con

Khi chuyển đổi giữa JOIN và subquery, **vị trí điều kiện lọc** có thể thay đổi kết quả.

### 15.1. LEFT JOIN với điều kiện trong ON

Yêu cầu: **giữ tất cả khách hàng và đếm đơn PAID**.

~~~sql
SELECT
    kh.ho_ten,
    COUNT(dh.id) AS so_don_paid
FROM jc_khach_hang AS kh
LEFT JOIN jc_don_hang AS dh
    ON dh.khach_hang_id = kh.id
   AND dh.trang_thai = 'PAID'
GROUP BY kh.id, kh.ho_ten
ORDER BY kh.id;
~~~

Kết quả: An 1, Bình 1, Chi 0, Dũng 2, Hà 0.

Điều kiện `dh.trang_thai = 'PAID'` nằm trong `ON` nên chỉ quyết định **đơn nào được ghép**, không loại khách bên trái chưa có đơn PAID.

### 15.2. Chuyển điều kiện xuống WHERE có thể loại khách

~~~sql
SELECT
    kh.ho_ten,
    COUNT(dh.id) AS so_don_paid
FROM jc_khach_hang AS kh
LEFT JOIN jc_don_hang AS dh
    ON dh.khach_hang_id = kh.id
WHERE dh.trang_thai = 'PAID'
GROUP BY kh.id, kh.ho_ten
ORDER BY kh.id;
~~~

Câu này chỉ còn **An, Bình, Dũng**. Vì `WHERE` loại những hàng có `dh.trang_thai = NULL` hoặc trạng thái không phải PAID, Chi và Hà không còn xuất hiện.

Khi chọn giữa LEFT JOIN, bảng dẫn xuất, hoặc EXISTS, cần xác định rõ mục tiêu **giữ hay loại đối tượng không khớp**.

### 15.3. HAVING để lọc nhóm theo chỉ số tổng hợp

Yêu cầu: **khách hàng có ít nhất hai đơn**.

~~~sql
SELECT
    dh.khach_hang_id,
    COUNT(*) AS so_don
FROM jc_don_hang AS dh
GROUP BY dh.khach_hang_id
HAVING COUNT(*) >= 2
ORDER BY dh.khach_hang_id;
~~~

Kết quả: khách hàng 1, 2 và 4, mỗi người có 2 đơn.

Có thể diễn đạt bằng bảng dẫn xuất:

~~~sql
SELECT x.khach_hang_id, x.so_don
FROM (
    SELECT khach_hang_id, COUNT(*) AS so_don
    FROM jc_don_hang
    GROUP BY khach_hang_id
) AS x
WHERE x.so_don >= 2
ORDER BY x.khach_hang_id;
~~~

Hai cách cho cùng kết quả ở ví dụ này. Dùng `HAVING` thường ngắn hơn nếu chỉ cần lọc ngay các nhóm được tính. Bảng dẫn xuất hoặc CTE hữu ích khi kết quả đếm còn cần **JOIN, dùng nhiều lần hoặc xử lý tiếp**.

## 16. So sánh với một mức trung bình: scalar subquery hay CTE?

Yêu cầu: **tìm những đơn PAID có tổng tiền lớn hơn trung bình tổng tiền của các đơn PAID**.

Cần chú ý cấp dữ liệu: tổng tiền không nằm trực tiếp ở `jc_don_hang` mà phải tính từ `jc_chi_tiet_don`. Vì thế trước tiên phải tạo **một dòng mỗi đơn PAID**.

### 16.1. Dùng CTE để tính tổng và trung bình

~~~sql
WITH don_paid_co_tong AS (
    SELECT
        dh.id AS ma_don,
        dh.khach_hang_id,
        COALESCE(SUM(ct.so_luong * ct.don_gia), 0)
            AS tong_tien
    FROM jc_don_hang AS dh
    LEFT JOIN jc_chi_tiet_don AS ct
        ON ct.don_hang_id = dh.id
    WHERE dh.trang_thai = 'PAID'
    GROUP BY dh.id, dh.khach_hang_id
)
SELECT
    d.ma_don,
    d.tong_tien
FROM don_paid_co_tong AS d
WHERE d.tong_tien > (
    SELECT AVG(tong_tien)
    FROM don_paid_co_tong
)
ORDER BY d.tong_tien DESC, d.ma_don;
~~~

Có bốn đơn PAID: 101 = 230000, 103 = 120000, 105 = 60000, 106 = 0. Trung bình:

\[
\frac{230000 + 120000 + 60000 + 0}{4} = 102500
\]

Kết quả:

| ma_don | tong_tien |
|---:|---:|
| 101 | 230000 |
| 103 | 120000 |

Ở đây, CTE giúp **định nghĩa tổng tiền theo đơn một lần trong câu SQL**, còn scalar subquery ở WHERE tính **một giá trị trung bình** từ kết quả CTE.

### 16.2. Cùng ý bằng JOIN với bảng trung bình một hàng

~~~sql
WITH don_paid_co_tong AS (
    SELECT
        dh.id AS ma_don,
        COALESCE(SUM(ct.so_luong * ct.don_gia), 0)
            AS tong_tien
    FROM jc_don_hang AS dh
    LEFT JOIN jc_chi_tiet_don AS ct
        ON ct.don_hang_id = dh.id
    WHERE dh.trang_thai = 'PAID'
    GROUP BY dh.id
)
SELECT
    d.ma_don,
    d.tong_tien,
    tb.avg_tong_tien
FROM don_paid_co_tong AS d
CROSS JOIN (
    SELECT AVG(tong_tien) AS avg_tong_tien
    FROM don_paid_co_tong
) AS tb
WHERE d.tong_tien > tb.avg_tong_tien
ORDER BY d.tong_tien DESC, d.ma_don;
~~~

Bảng dẫn xuất `tb` có **một hàng** vì AVG không có GROUP BY, nên CROSS JOIN chỉ bổ sung một cột trung bình cho mỗi đơn, không nhân số dòng. Kết quả vẫn là đơn 101 và 103, có thêm cột ngưỡng 102500.

**Cách chọn:** nếu chỉ cần ngưỡng trong điều kiện, scalar subquery rất gọn; nếu muốn **hiển thị ngưỡng** hoặc dùng ngưỡng ở nhiều biểu thức, ghép một nguồn một hàng qua CROSS JOIN có thể rõ ràng.

## 17. Lấy một hàng mới nhất theo từng khách: window function, LATERAL hay correlated subquery?

Yêu cầu: **hiển thị mọi khách hàng cùng mã đơn mới nhất**, nếu chưa có đơn thì mã đơn NULL. Khi hai đơn cùng ngày, chọn ID lớn hơn làm tiêu chí phá hòa.

Đây là bài toán **top 1 per group**, có nhiều cách nhưng cần nhất quán về điều kiện thứ tự.

### 17.1. CTE + ROW_NUMBER

~~~sql
WITH don_co_hang AS (
    SELECT
        dh.id,
        dh.khach_hang_id,
        dh.ngay_dat,
        ROW_NUMBER() OVER (
            PARTITION BY dh.khach_hang_id
            ORDER BY dh.ngay_dat DESC, dh.id DESC
        ) AS rn
    FROM jc_don_hang AS dh
)
SELECT
    kh.id,
    kh.ho_ten,
    d.id AS don_moi_nhat
FROM jc_khach_hang AS kh
LEFT JOIN don_co_hang AS d
    ON d.khach_hang_id = kh.id
   AND d.rn = 1
ORDER BY kh.id;
~~~

Kết quả:

| Khách hàng | don_moi_nhat |
|---|---:|
| An | 102 |
| Bình | 104 |
| Chi | NULL |
| Dũng | 106 |
| Hà | 107 |

`ROW_NUMBER` đánh số các đơn trong từng nhóm khách hàng. `rn = 1` là đơn mới nhất theo thứ tự đã khai báo. Điều kiện này nằm trong `ON` để giữ **Chi** khi không có đơn.

### 17.2. PostgreSQL: LEFT JOIN LATERAL

~~~sql
SELECT
    kh.id,
    kh.ho_ten,
    moi.id AS don_moi_nhat
FROM jc_khach_hang AS kh
LEFT JOIN LATERAL (
    SELECT dh.id
    FROM jc_don_hang AS dh
    WHERE dh.khach_hang_id = kh.id
    ORDER BY dh.ngay_dat DESC, dh.id DESC
    LIMIT 1
) AS moi ON TRUE
ORDER BY kh.id;
~~~

Truy vấn con `LATERAL` được phép tham chiếu `kh.id` của nguồn bên trái, rồi chọn một đơn theo thứ tự đã xác định. Nếu không có đơn, LEFT JOIN giữ khách và điền `moi.id = NULL`.

Đây là cú pháp đặc thù được PostgreSQL và một số DBMS hỗ trợ. Trong SQL Server có thể biểu diễn mô hình phụ thuộc tương tự bằng `OUTER APPLY`. `LATERAL` không bắt buộc cho bài toán đơn giản nhưng hữu ích khi cần lấy một vài hàng liên quan theo từng đối tượng.

### 17.3. Scalar subquery trong SELECT

Nếu chỉ cần **một cột mã đơn**:

~~~sql
SELECT
    kh.id,
    kh.ho_ten,
    (
        SELECT dh.id
        FROM jc_don_hang AS dh
        WHERE dh.khach_hang_id = kh.id
        ORDER BY dh.ngay_dat DESC, dh.id DESC
        LIMIT 1
    ) AS don_moi_nhat
FROM jc_khach_hang AS kh
ORDER BY kh.id;
~~~

Kết quả giống hai cách trên. Nếu cần nhiều cột của cùng đơn mới nhất, `LATERAL` hoặc CTE/window kết hợp JOIN có thể rõ hơn so với viết nhiều scalar subquery lặp lại.

### 17.4. Vì sao không chỉ lấy MAX(id)?

Không được mặc nhiên coi ID lớn nhất là đơn mới nhất nếu ID không được bảo đảm tăng theo thời điểm nghiệp vụ. Bộ dữ liệu mẫu vô tình có ID tăng theo ngày, nhưng quy tắc đúng ở đây là **`ORDER BY ngay_dat DESC, id DESC`**. Trong thực tế, đơn được nhập bù, di chuyển dữ liệu hoặc thay đổi khóa có thể làm giả định “MAX(id) là mới nhất” không còn đúng.

## 18. CTE đệ quy: khi truy vấn có quan hệ phân cấp

Trong đa số ví dụ trên, CTE không đệ quy: mỗi bước chỉ dùng dữ liệu hoặc các CTE đã khai báo. Với dữ liệu dạng **cây tổ chức, danh mục cha–con hoặc đường đi**, một CTE đệ quy có thể phù hợp hơn JOIN lặp nhiều tầng cố định.

Ví dụ PostgreSQL tự chứa, dùng giá trị minh họa:

~~~sql
WITH RECURSIVE cay AS (
    SELECT
        id,
        ten,
        cha_id,
        0 AS do_sau
    FROM (
        VALUES
            (1, 'Gốc', NULL::INTEGER),
            (2, 'Nhánh A', 1),
            (3, 'Nhánh B', 1),
            (4, 'Lá A1', 2)
    ) AS v(id, ten, cha_id)
    WHERE cha_id IS NULL

    UNION ALL

    SELECT
        v.id,
        v.ten,
        v.cha_id,
        cay.do_sau + 1
    FROM cay
    JOIN (
        VALUES
            (1, 'Gốc', NULL::INTEGER),
            (2, 'Nhánh A', 1),
            (3, 'Nhánh B', 1),
            (4, 'Lá A1', 2)
    ) AS v(id, ten, cha_id)
        ON v.cha_id = cay.id
)
SELECT id, ten, cha_id, do_sau
FROM cay
ORDER BY do_sau, id;
~~~

Ví dụ cho biết kết quả phân cấp: Gốc độ sâu 0; Nhánh A và Nhánh B độ sâu 1; Lá A1 độ sâu 2. Các chuỗi VALUES bị lặp để câu SQL độc lập không cần tạo bảng; trong ứng dụng nên dùng bảng phân cấp có thật.

**Cẩn trọng với chu trình:** nếu dữ liệu cha–con có vòng lặp mà truy vấn đệ quy không có cơ chế phát hiện chu trình hoặc giới hạn phù hợp, truy vấn có thể sinh dữ liệu không mong muốn. Phần này chỉ nhằm nhận diện **mục đích của recursive CTE**, không thay thế bài học chuyên sâu về đệ quy, cycle detection và tối ưu cây.

## 19. Hiểu phạm vi tên và mức trả về

Lỗi cú pháp/ý nghĩa thường xuất phát từ việc không biết subquery đang trả **một giá trị**, **nhiều dòng**, hay **một bảng có cột được đặt tên**.

### 19.1. Truy vấn con trong FROM cần cung cấp cột cho bên ngoài

~~~sql
SELECT x.ma_don, x.so_dong
FROM (
    SELECT
        don_hang_id AS ma_don,
        COUNT(*) AS so_dong
    FROM jc_chi_tiet_don
    GROUP BY don_hang_id
) AS x
ORDER BY x.ma_don;
~~~

Truy vấn ngoài chỉ nhìn thấy `x.ma_don` và `x.so_dong`. Nó **không thể** tham chiếu `x.don_hang_id` vì cột bên trong đã được đổi tên thành `ma_don`.

### 19.2. Alias bên trong không tự tồn tại bên ngoài

~~~sql
SELECT x.ma_don
FROM (
    SELECT ct.don_hang_id AS ma_don
    FROM jc_chi_tiet_don AS ct
) AS x;
~~~

Bí danh `ct` chỉ có hiệu lực bên trong subquery. Ở ngoài, cần dùng tên nguồn `x` và các cột mà `x` xuất ra. Không được viết `SELECT ct.don_hang_id` ở ngoài phạm vi của `ct`.

### 19.3. Alias cột SELECT và WHERE cùng cấp

Trong PostgreSQL, có thể dùng bí danh cột đầu ra ở `ORDER BY`:

~~~sql
SELECT
    id,
    so_luong * don_gia AS thanh_tien
FROM jc_chi_tiet_don
ORDER BY thanh_tien DESC;
~~~

Nhưng đoạn truy vấn trên sẽ lỗi vì bảng `jc_chi_tiet_don` **không có cột `id`**; ví dụ đúng với bộ dữ liệu là:

~~~sql
SELECT
    don_hang_id,
    so_luong * don_gia AS thanh_tien
FROM jc_chi_tiet_don
ORDER BY thanh_tien DESC, don_hang_id;
~~~

Trong `WHERE` cùng cấp, bí danh vừa khai báo ở `SELECT` thông thường không dùng được:

~~~sql
-- Không hợp lệ trong PostgreSQL: WHERE không thấy alias thanh_tien.
SELECT so_luong * don_gia AS thanh_tien
FROM jc_chi_tiet_don
WHERE thanh_tien > 100000;
~~~

Dùng lại biểu thức, hoặc đặt phép tính trong bảng dẫn xuất/CTE:

~~~sql
SELECT x.don_hang_id, x.thanh_tien
FROM (
    SELECT
        don_hang_id,
        so_luong * don_gia AS thanh_tien
    FROM jc_chi_tiet_don
) AS x
WHERE x.thanh_tien > 100000
ORDER BY x.don_hang_id;
~~~

Đây là một lý do thực tế để chọn bảng dẫn xuất: **tạo tên cho biểu thức, rồi lọc hoặc JOIN dựa trên tên đó ở lớp ngoài**.

### 19.4. Bảng dẫn xuất thông thường và phụ thuộc tương quan

Không phải mọi DBMS cho phép một subquery trong FROM tham chiếu alias của bảng đứng trước. Với PostgreSQL, khi nguồn phụ thuộc từng hàng bên trái, sử dụng `LATERAL` như phần 17. Trong SQL Server, những cấu trúc tương ứng là `CROSS APPLY` và `OUTER APPLY`.

Nếu dữ liệu trung gian độc lập với nguồn ngoài, bảng dẫn xuất/CTE thông thường thường dễ đọc hơn.

## 20. Hiệu năng: đừng chọn công cụ bằng định kiến

Một quan niệm sai phổ biến là:

> “JOIN chắc chắn nhanh hơn subquery”, hoặc “CTE luôn chạy một lần nên nhanh hơn”.

Thực tế, DBMS tối ưu **kế hoạch thực thi của toàn bộ câu SQL**. Truy vấn `EXISTS` có thể được tối ưu thành semi-join; derived table có thể được gộp; một CTE có thể bị inline hoặc materialize; correlated subquery có thể dùng chỉ mục hiệu quả. Ngược lại, JOIN không phù hợp có thể nhân hàng và làm tổng hợp cực kỳ tốn kém.

### 20.1. Các câu hỏi nên hỏi trước khi tối ưu

1. **Kết quả có đúng không?** Cùng yêu cầu phải cùng tập dữ liệu, số hàng và cách xử lý NULL.
2. **Mức chi tiết là gì?** Một khách, một đơn hay một dòng sản phẩm?
3. **Điều kiện nào lọc được dữ liệu sớm về mặt ngữ nghĩa?** Ví dụ chỉ đơn PAID.
4. **Có điều kiện JOIN rõ ràng và đầy đủ không?** Tránh tạo tích Descartes vô tình.
5. **Các cột JOIN/lọc có chỉ mục phù hợp không?** Ví dụ `jc_don_hang.khach_hang_id`.
6. **Số hàng ước lượng và thực tế khác nhau nhiều không?** Có thể do thống kê hoặc bội số JOIN.
7. **Có tính lặp nhiều aggregate cùng nhóm không?** Cân nhắc tổng hợp thành nguồn một hàng mỗi khóa.
8. **Có ORDER BY/LIMIT đặc thù không?** Cách lấy Top N có thể ảnh hưởng kế hoạch.

### 20.2. Sử dụng EXPLAIN trong PostgreSQL

~~~sql
EXPLAIN
SELECT
    kh.id,
    kh.ho_ten
FROM jc_khach_hang AS kh
WHERE EXISTS (
    SELECT 1
    FROM jc_don_hang AS dh
    WHERE dh.khach_hang_id = kh.id
      AND dh.trang_thai = 'PAID'
);
~~~

`EXPLAIN` hiển thị kế hoạch dự kiến của PostgreSQL. Bạn có thể gặp tên bước như Seq Scan, Index Scan, Hash Join, Nested Loop hoặc các phép semi-join, tùy thống kê, chỉ mục, kích thước bảng và phiên bản.

`EXPLAIN ANALYZE` chạy câu SQL để đo đạc thực tế, nên cần cẩn trọng với lệnh làm thay đổi dữ liệu và môi trường sản xuất. Bộ dữ liệu mẫu chỉ vài hàng, vì vậy kế hoạch thường thiên về tính đơn giản; không thể dùng nó để khẳng định giải pháp tốt nhất cho bảng hàng triệu dòng.

### 20.3. Index giúp gì?

Với mô hình đơn hàng:

- Index trên `jc_don_hang.khach_hang_id` có thể hỗ trợ tìm đơn theo khách.
- Một index kết hợp `(khach_hang_id, trang_thai)` có thể phù hợp khi thường kiểm tra đơn PAID theo khách, tùy số hàng và tính chọn lọc.
- Khóa chính trên `jc_chi_tiet_don(don_hang_id, san_pham_id)` đã tạo index có cột đầu là `don_hang_id` trong PostgreSQL, hữu ích cho JOIN/tổng hợp theo đơn.

Nhưng không nên tạo index chỉ vì một ví dụ có JOIN. Index làm tăng chi phí ghi và lưu trữ; phải xem nhu cầu truy vấn thật, kế hoạch và lượng dữ liệu.

### 20.4. CTE không đồng nghĩa materialization

Trong PostgreSQL hiện đại, nhiều CTE không đệ quy, không có tác dụng phụ có thể được gộp vào truy vấn ngoài. Tùy ngữ cảnh, bạn có thể gặp:

~~~sql
WITH tong AS MATERIALIZED (
    SELECT khach_hang_id, COUNT(*) AS so_don
    FROM jc_don_hang
    GROUP BY khach_hang_id
)
SELECT *
FROM tong;
~~~

hoặc:

~~~sql
WITH tong AS NOT MATERIALIZED (
    SELECT khach_hang_id, COUNT(*) AS so_don
    FROM jc_don_hang
    GROUP BY khach_hang_id
)
SELECT *
FROM tong;
~~~

`MATERIALIZED` và `NOT MATERIALIZED` là các chỉ dẫn cụ thể của PostgreSQL trong những trường hợp hỗ trợ, không phải cú pháp chuyển nguyên xi sang mọi hệ quản trị. Chúng có thể ảnh hưởng việc gộp/tính trung gian, nhưng **không phải công thức tăng tốc mặc định**. Chỉ dùng khi hiểu kế hoạch thực thi và có mục đích tối ưu cụ thể.

## 21. Tính di động giữa các hệ quản trị

JOIN, các truy vấn con và CTE là những cấu trúc phổ biến của SQL, nhưng vẫn có khác biệt giữa hệ quản trị và phiên bản.

| Hệ quản trị | JOIN / Subquery / CTE | Lưu ý quan trọng |
|---|---|---|
| **PostgreSQL** | Đều được hỗ trợ rộng rãi | `WITH RECURSIVE`, `LATERAL`, `FILTER`, `LIMIT`; có `MATERIALIZED`/`NOT MATERIALIZED` cho CTE trong điều kiện hỗ trợ |
| **MySQL** | JOIN/subquery; CTE ở các phiên bản hiện đại | MySQL 8.0+ hỗ trợ CTE; `LIMIT`, hành vi tối ưu derived table/CTE tùy phiên bản |
| **MariaDB** | JOIN/subquery và CTE ở các phiên bản phù hợp | Cần kiểm tra phiên bản cụ thể đối với đệ quy, LATERAL hoặc cách tối ưu |
| **SQL Server** | JOIN/subquery và CTE | `WITH` có các quy tắc vị trí dấu chấm phẩy; `CROSS APPLY`/`OUTER APPLY`; dùng `TOP` hoặc `OFFSET ... FETCH` thay `LIMIT` |
| **Oracle** | JOIN/subquery và CTE | Có subquery factoring với `WITH`; cách giới hạn dòng và alias bảng khác PostgreSQL |
| **SQLite** | JOIN/subquery và CTE ở bản hiện đại | `WITH RECURSIVE` có mặt; kiểu dữ liệu, ngày tháng và một số tính năng JOIN khác DBMS lớn |

### 21.1. SQL Server: CTE với WITH

Ví dụ T-SQL, giả sử bảng `dbo.DonHang` có các cột tương ứng:

~~~sql
;WITH so_don AS (
    SELECT
        KhachHangId,
        COUNT(*) AS SoDon
    FROM dbo.DonHang
    GROUP BY KhachHangId
)
SELECT KhachHangId, SoDon
FROM so_don;
~~~

Dấu chấm phẩy trước `WITH` thường được dùng để kết thúc an toàn statement trước đó trong script T-SQL. CTE trong SQL Server không nên mặc định được coi là kết quả vật lý lưu riêng; việc tối ưu phụ thuộc kế hoạch.

### 21.2. PostgreSQL và MySQL: LIMIT

~~~sql
SELECT id, ngay_dat
FROM jc_don_hang
ORDER BY ngay_dat DESC, id DESC
LIMIT 1;
~~~

Ví dụ dùng bảng PostgreSQL mẫu; các hệ khác như MySQL có cú pháp `LIMIT` tương tự. SQL Server có thể dùng `TOP 1` hoặc `FETCH` với ORDER BY thích hợp; Oracle hiện đại có `FETCH FIRST 1 ROW ONLY`.

### 21.3. Oracle và bí danh bảng

Oracle thường dùng bí danh bảng **không có `AS`**:

~~~sql
SELECT d.id, d.khach_hang_id
FROM don_hang d
WHERE EXISTS (
    SELECT 1
    FROM chi_tiet_don ct
    WHERE ct.don_hang_id = d.id
);
~~~

Tên bảng chỉ là minh họa khi chuyển sang Oracle. Một số cú pháp PostgreSQL như ép kiểu `::NUMERIC`, `LIMIT` hay `FILTER` không bảo đảm chuyển nguyên xi.

### 21.4. Đệ quy và nguồn phụ thuộc có cú pháp riêng

- PostgreSQL/SQLite/MySQL hiện đại thường dùng `WITH RECURSIVE` cho CTE đệ quy.
- SQL Server có cú pháp CTE đệ quy theo T-SQL, thường không đặt từ `RECURSIVE` sau WITH.
- PostgreSQL có `LATERAL`; SQL Server có `APPLY`; Oracle có những khả năng riêng cho nguồn phụ thuộc.
- MySQL/MariaDB và các bản khác có mức hỗ trợ LATERAL/derived table khác nhau theo phiên bản.

Vì vậy, **nguyên tắc chọn theo mục đích có tính di động hơn cú pháp triển khai chi tiết**. Hãy kiểm tra tài liệu chính thức của phiên bản DBMS bạn đang dùng khi chuyển các ví dụ nâng cao.

## 22. Các lỗi phổ biến khi chọn JOIN, subquery và CTE

| Lỗi hoặc nhận định | Vấn đề | Cách tiếp cận phù hợp |
|---|---|---|
| “Muốn biết khách có đơn, phải JOIN” | JOIN có thể làm lặp khách theo số đơn | Dùng EXISTS khi chỉ cần có/không |
| “NOT IN luôn tương đương NOT EXISTS” | NULL trong tập của NOT IN có thể khiến kết quả UNKNOWN | Ưu tiên NOT EXISTS khi kiểm tra không tồn tại |
| “Subquery vô hướng luôn trả một giá trị hợp lệ” | Có thể trả 0 hàng (NULL) hoặc nhiều hàng (lỗi) | Xác định số hàng, dùng aggregate/IN/EXISTS đúng mục đích |
| “CTE là bảng tạm lưu sẵn” | CTE có phạm vi statement; DBMS quyết định materialize | Không dựa vào giả định vật lý |
| “JOIN thêm chi tiết không ảnh hưởng COUNT đơn” | Quan hệ một-nhiều làm nhân hàng | Kiểm soát cấp hạt, pre-aggregate hoặc COUNT DISTINCT phù hợp |
| “SUM DISTINCT sửa mọi tổng bị nhân” | Những dòng thật có cùng số tiền có thể bị loại nhầm | Tổng hợp ở đúng khóa và JOIN đúng quan hệ |
| “LEFT JOIN rồi WHERE trạng thái PAID vẫn giữ khách trống” | WHERE lọc hàng có giá trị NULL bên phải | Đặt điều kiện ghép trong ON |
| “Cứ lồng subquery là nhanh” | Tốc độ phụ thuộc kế hoạch, chỉ mục, dữ liệu | Dùng EXPLAIN, so các truy vấn đúng ngữ nghĩa |
| “CTE luôn nhanh hơn subquery” | Có thể inline/materialize; tối ưu phụ thuộc DBMS | Chọn CTE vì rõ các bước, đo hiệu năng nếu cần |
| “GROUP BY theo ID đơn là đủ sau khi JOIN nhiều nhánh 1:N” | Các nhánh có thể nhân lẫn nhau trước khi tổng hợp | Tổng hợp từng nhánh đúng cấp trước JOIN |
| “MAX(id) luôn là bản ghi mới nhất” | ID không bảo đảm thứ tự thời gian | Dùng ngày và tie-breaker |
| “Thêm LIMIT 1 giải quyết scalar subquery nhiều hàng” | Chọn tùy ý nếu không có quy tắc ORDER BY | Xác định tiêu chí lấy đúng một hàng |
| “ORDER BY trong CTE quyết định thứ tự cuối” | Thứ tự ngoài không được bảo đảm | Đặt ORDER BY ở SELECT ngoài cùng |
| “Mỗi cách viết phải có một kế hoạch cố định” | Optimizer có thể viết lại truy vấn | Xem kế hoạch thực tế |
| “Chỉ cần kết quả đúng trên mẫu nhỏ” | Dữ liệu thật có thể có NULL/trùng/nhiều dòng liên quan | Xác định bất biến và các trường hợp biên |

### 22.1. Kiểm tra số hàng sau từng bước

Khi một báo cáo bị sai, một kỹ thuật đơn giản là kiểm tra `COUNT(*)` ở mỗi cấp:

~~~sql
SELECT COUNT(*) AS so_khach
FROM jc_khach_hang;

SELECT COUNT(*) AS so_don
FROM jc_don_hang;

SELECT COUNT(*) AS so_dong_chi_tiet
FROM jc_chi_tiet_don;
~~~

Kết quả lần lượt **5, 7, 8**.

Khi JOIN đơn với chi tiết:

~~~sql
SELECT COUNT(*) AS so_dong_sau_join
FROM jc_don_hang AS dh
JOIN jc_chi_tiet_don AS ct
    ON ct.don_hang_id = dh.id;
~~~

Kết quả **8**, vì đây là một dòng trên mỗi chi tiết, không phải 7 đơn. Nếu mục tiêu là một hàng mỗi đơn, cần GROUP BY hoặc dùng kết quả đã tổng hợp trước khi JOIN.

### 22.2. Đừng phụ thuộc thứ tự không khai báo

Các ví dụ có `ORDER BY` khi cần kết quả dễ đối chiếu. Dù dùng JOIN, subquery hay CTE, **không có ORDER BY ngoài cùng thì SQL không bảo đảm thứ tự hiển thị**. Điều này đặc biệt quan trọng khi dùng `LIMIT`/phân trang.

## 23. Bài tập thực hành có lời giải

Các bài dưới dùng bộ bảng `jc_khach_hang`, `jc_don_hang`, `jc_san_pham` và `jc_chi_tiet_don` đã tạo ở phần 3. Những lệnh dưới đây chỉ đọc dữ liệu; không sửa bảng.

### Bài 1. Chọn cách truy vấn phù hợp

**Yêu cầu:** ghép mỗi đơn hàng với tên khách hàng và ngày đặt. Nên chọn JOIN, EXISTS hay scalar subquery?

**Đáp án:** `JOIN` vì cần cột của cả hai bảng, và mỗi đơn thuộc đúng một khách.

~~~sql
SELECT
    dh.id,
    kh.ho_ten,
    dh.ngay_dat
FROM jc_don_hang AS dh
JOIN jc_khach_hang AS kh
    ON kh.id = dh.khach_hang_id
ORDER BY dh.id;
~~~

Kết quả có **7 dòng**, mỗi đơn một dòng.

### Bài 2. Khách hàng đã có ít nhất một đơn PAID

**Yêu cầu:** mỗi khách xuất hiện tối đa một lần, không cần thông tin từng đơn.

~~~sql
SELECT kh.id, kh.ho_ten
FROM jc_khach_hang AS kh
WHERE EXISTS (
    SELECT 1
    FROM jc_don_hang AS dh
    WHERE dh.khach_hang_id = kh.id
      AND dh.trang_thai = 'PAID'
)
ORDER BY kh.id;
~~~

**Đáp án:** An, Bình, Dũng. Dũng có hai đơn PAID nhưng chỉ xuất hiện một lần.

### Bài 3. Khách hàng chưa có đơn PAID

~~~sql
SELECT kh.id, kh.ho_ten
FROM jc_khach_hang AS kh
WHERE NOT EXISTS (
    SELECT 1
    FROM jc_don_hang AS dh
    WHERE dh.khach_hang_id = kh.id
      AND dh.trang_thai = 'PAID'
)
ORDER BY kh.id;
~~~

**Đáp án:** Chi và Hà. Chi không có đơn nào; Hà có đơn NEW nhưng không PAID.

### Bài 4. Ngày đặt đơn mới nhất

**Yêu cầu:** tìm tất cả các đơn được đặt vào ngày mới nhất trong bảng.

~~~sql
SELECT id, ngay_dat, trang_thai
FROM jc_don_hang
WHERE ngay_dat = (
    SELECT MAX(ngay_dat)
    FROM jc_don_hang
)
ORDER BY id;
~~~

**Đáp án:** đơn 107 ngày 2026-11-09, trạng thái NEW. Scalar subquery trả một ngày, nhưng nếu nhiều đơn có cùng ngày lớn nhất, truy vấn ngoài có thể trả nhiều dòng.

### Bài 5. Đếm số đơn từng khách bằng subquery tương quan

~~~sql
SELECT
    kh.id,
    kh.ho_ten,
    (
        SELECT COUNT(*)
        FROM jc_don_hang AS dh
        WHERE dh.khach_hang_id = kh.id
    ) AS so_don
FROM jc_khach_hang AS kh
ORDER BY kh.id;
~~~

**Đáp án:** An 2, Bình 2, Chi 0, Dũng 2, Hà 1.

### Bài 6. Viết lại bài 5 bằng LEFT JOIN bảng dẫn xuất

~~~sql
SELECT
    kh.id,
    kh.ho_ten,
    COALESCE(x.so_don, 0) AS so_don
FROM jc_khach_hang AS kh
LEFT JOIN (
    SELECT
        khach_hang_id,
        COUNT(*) AS so_don
    FROM jc_don_hang
    GROUP BY khach_hang_id
) AS x
    ON x.khach_hang_id = kh.id
ORDER BY kh.id;
~~~

**Đáp án:** cùng kết quả bài 5. Điểm khác là câu này tính `COUNT(*)` theo khách ở bảng dẫn xuất rồi JOIN kết quả một dòng mỗi khách.

### Bài 7. Tính tổng tiền PAID theo khách bằng CTE

**Yêu cầu:** giữ mọi khách, kể cả người chưa có đơn PAID; đơn PAID chưa có dòng chi tiết hiển thị tổng 0.

~~~sql
WITH tong_don AS (
    SELECT
        dh.id,
        dh.khach_hang_id,
        dh.trang_thai,
        COALESCE(SUM(ct.so_luong * ct.don_gia), 0) AS tong_tien
    FROM jc_don_hang AS dh
    LEFT JOIN jc_chi_tiet_don AS ct
        ON ct.don_hang_id = dh.id
    GROUP BY dh.id, dh.khach_hang_id, dh.trang_thai
),
tong_paid AS (
    SELECT
        khach_hang_id,
        SUM(tong_tien) AS tong
    FROM tong_don
    WHERE trang_thai = 'PAID'
    GROUP BY khach_hang_id
)
SELECT
    kh.ho_ten,
    COALESCE(tp.tong, 0) AS tong_paid
FROM jc_khach_hang AS kh
LEFT JOIN tong_paid AS tp
    ON tp.khach_hang_id = kh.id
ORDER BY kh.id;
~~~

**Đáp án:** An 230000, Bình 120000, Chi 0, Dũng 60000, Hà 0.

### Bài 8. Phát hiện lỗi khi JOIN làm lặp số đơn

**Đề bài:** vì sao câu sau không trả số đơn thật của An?

~~~sql
SELECT
    kh.ho_ten,
    COUNT(dh.id) AS so_don
FROM jc_khach_hang AS kh
JOIN jc_don_hang AS dh
    ON dh.khach_hang_id = kh.id
JOIN jc_chi_tiet_don AS ct
    ON ct.don_hang_id = dh.id
WHERE kh.id = 1
GROUP BY kh.ho_ten;
~~~

**Đáp án:** An có 2 đơn nhưng tổng **3 dòng chi tiết** của hai đơn, nên COUNT(dh.id) cho 3. Một cách sửa ngắn cho riêng chỉ số số đơn là `COUNT(DISTINCT dh.id)`; cách tổng quát hơn là đếm trên bảng đơn trước khi JOIN bảng chi tiết. Nếu còn yêu cầu giữ đơn không có chi tiết, cần xét LEFT JOIN và điều kiện thích hợp.

### Bài 9. Vì sao NOT IN không trả dòng?

~~~sql
SELECT a.id
FROM (VALUES (1), (2), (3)) AS a(id)
WHERE a.id NOT IN (
    SELECT b.id
    FROM (VALUES (1), (NULL::INTEGER)) AS b(id)
);
~~~

**Đáp án:** không có dòng nào, vì NULL trong tập subquery khiến những giá trị không khớp rõ ràng trở thành UNKNOWN thay vì TRUE đối với NOT IN. Nếu mục tiêu là kiểm tra không có dòng phù hợp, dùng `NOT EXISTS` với điều kiện nối tương quan thường dễ kiểm soát hơn.

### Bài 10. Lấy đơn mới nhất của mỗi khách

~~~sql
WITH xep_hang AS (
    SELECT
        id,
        khach_hang_id,
        ngay_dat,
        ROW_NUMBER() OVER (
            PARTITION BY khach_hang_id
            ORDER BY ngay_dat DESC, id DESC
        ) AS rn
    FROM jc_don_hang
)
SELECT
    kh.ho_ten,
    x.id AS don_moi_nhat
FROM jc_khach_hang AS kh
LEFT JOIN xep_hang AS x
    ON x.khach_hang_id = kh.id
   AND x.rn = 1
ORDER BY kh.id;
~~~

**Đáp án:** An 102, Bình 104, Chi NULL, Dũng 106, Hà 107. CTE đặt tên kết quả xếp hạng; LEFT JOIN giữ người chưa có đơn.

### Bài 11. Đơn PAID vượt trung bình PAID

**Yêu cầu:** tính tổng tiền từng đơn PAID trước, rồi lấy những đơn có tổng lớn hơn trung bình của bốn đơn PAID.

~~~sql
WITH tong_paid_theo_don AS (
    SELECT
        dh.id AS ma_don,
        COALESCE(SUM(ct.so_luong * ct.don_gia), 0) AS tong_tien
    FROM jc_don_hang AS dh
    LEFT JOIN jc_chi_tiet_don AS ct
        ON ct.don_hang_id = dh.id
    WHERE dh.trang_thai = 'PAID'
    GROUP BY dh.id
)
SELECT ma_don, tong_tien
FROM tong_paid_theo_don
WHERE tong_tien > (
    SELECT AVG(tong_tien)
    FROM tong_paid_theo_don
)
ORDER BY tong_tien DESC, ma_don;
~~~

**Đáp án:** đơn 101 (230000) và 103 (120000). Trung bình các đơn PAID là 102500.

### Bài 12. Tự quyết định công cụ

Xem bốn câu hỏi dưới đây. Với mỗi câu, chọn giải pháp dễ diễn đạt nhất và giải thích vì sao:

| Yêu cầu | Gợi ý |
|---|---|
| Danh sách sản phẩm kèm tên từng dòng đơn có sử dụng sản phẩm | JOIN để lấy cột từ sản phẩm và chi tiết |
| Khách hàng có ít nhất một đơn NEW | EXISTS vì chỉ cần điều kiện tồn tại |
| Đơn đặt vào ngày gần nhất của toàn bộ hệ thống | Scalar subquery lấy MAX(ngay_dat) |
| Báo cáo nhiều bước: tổng theo đơn → lọc PAID → tổng theo khu vực | CTE kết hợp GROUP BY và JOIN |

**Điểm cần rút ra:** bản thân công cụ không quyết định tính đúng. Bạn phải mô tả trước **đầu ra có một hàng cho đối tượng nào**, sau đó mới chọn JOIN, subquery và CTE sao cho phục vụ đúng mục tiêu.

## 24. Quy trình thực tế để chọn cách viết truy vấn

Khi gặp một yêu cầu truy vấn nhiều bảng, bạn có thể làm theo chuỗi quyết định sau.

### Bước 1: Xác định một hàng đầu ra đại diện cho gì

Ví dụ: **mỗi khách hàng**, **mỗi đơn**, hay **mỗi sản phẩm trong một đơn**. Việc xác định mức chi tiết (*grain*) giúp biết JOIN nào có thể nhân hàng.

### Bước 2: Xác định bạn cần dữ liệu hay chỉ cần điều kiện

Nếu cần thêm cột của bảng khác → thường `JOIN`. Nếu chỉ cần biết có/không có dòng phù hợp → `EXISTS`/`NOT EXISTS`. Nếu chỉ cần so sánh với một ngưỡng tính từ dữ liệu → scalar subquery có thể hợp lý.

### Bước 3: Xác định kết quả trung gian có cần gom nhóm không

Nếu dữ liệu nguồn là dòng chi tiết nhưng đầu ra ở cấp đơn, hãy `GROUP BY don_hang_id` **trước khi ghép** với nguồn ở cấp đơn khi phù hợp. Có thể dùng bảng dẫn xuất hoặc CTE để đặt tên cho kết quả tổng hợp.

### Bước 4: Xác định số bước và khả năng tái sử dụng

Một bước ngắn có thể đặt ngay trong `FROM (SELECT ...)`. Nhiều bước có phụ thuộc hoặc sử dụng lại sẽ dễ đọc hơn khi khai báo bằng `WITH`. CTE không tự biến thành bảng lưu vĩnh viễn.

### Bước 5: Kiểm tra NULL, tập rỗng và bản ghi không khớp

- `EXISTS` khi không có hàng → FALSE.
- `NOT EXISTS` khi không có hàng → TRUE.
- Scalar subquery không có hàng → NULL.
- `COUNT(*)` trên tập rỗng không GROUP BY → 0.
- `SUM` trên tập rỗng → NULL.
- `LEFT JOIN` giữ hàng bên trái nhưng có thể bị một điều kiện `WHERE` trên bảng phải loại đi.
- `NOT IN` cần cẩn thận với NULL trong tập giá trị.

### Bước 6: Chỉ sau khi đúng mới so hiệu năng

Xem chỉ mục, lượng dữ liệu, độ chọn lọc, kế hoạch `EXPLAIN` và số hàng sau từng JOIN. Không chọn JOIN hay CTE chỉ vì một lời khẳng định “cái này luôn nhanh hơn”.

### Bước 7: Kết thúc bằng ORDER BY khi cần thứ tự

Nếu ứng dụng cần phân trang hoặc kết quả có thứ tự để kiểm thử, hãy đặt `ORDER BY` ở truy vấn ngoài cùng, với tiêu chí phá hòa rõ ràng khi cần.

## 25. Tổng kết

**JOIN, truy vấn con và CTE không phải ba lựa chọn loại trừ nhau.** Chúng giải quyết các khía cạnh khác nhau của bài toán:

- **JOIN** là công cụ chính để ghép các hàng và lấy cột từ nhiều nguồn. Hãy chú ý quan hệ một-nhiều và bội số dòng.
- **EXISTS/NOT EXISTS** phù hợp khi chỉ cần xác định một bản ghi liên quan có tồn tại hay không; chúng thường tránh việc làm lặp hàng của nguồn ngoài. **IN** phù hợp cho kiểm tra thuộc tập, nhưng **NOT IN** cần đặc biệt cẩn trọng với NULL.
- **Scalar subquery** phù hợp khi cần một giá trị so sánh hoặc hiển thị cho một hàng. Truy vấn này có thể trả NULL nếu không có hàng và lỗi nếu trả nhiều hàng ở vị trí đòi hỏi một giá trị.
- **Bảng dẫn xuất** giúp tính toán hoặc tổng hợp thành một nguồn dữ liệu rồi JOIN/lọc tiếp, rất hữu ích để giữ đúng mức chi tiết.
- **CTE** giúp chia truy vấn thành các bước có tên, rõ ràng khi có nhiều phép xử lý; không tự bảo đảm kết quả được lưu vật lý hay chỉ thực thi một lần.
- **Window function, LATERAL/APPLY và recursive CTE** là các lựa chọn nâng cao cho xếp hạng theo nhóm, nguồn phụ thuộc và dữ liệu phân cấp.

Một câu SQL tốt là câu **trả đúng số hàng, đúng ý nghĩa, xử lý đúng NULL và đọc được dễ dàng**. Khi đã đạt những điều đó, mới dùng kế hoạch thực thi và dữ liệu thực tế để chọn phương án tối ưu.

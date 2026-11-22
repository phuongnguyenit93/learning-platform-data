# Duyệt cây cha-con và tính độ sâu bằng truy vấn đệ quy SQL

> **Module:** Database SQL  
> **Chương:** Truy vấn đệ quy  
> **Bài học:** Duyệt cây cha-con và tính độ sâu

Một cơ sở dữ liệu quan hệ thường lưu cấu trúc phân cấp trong một bảng: mỗi nhân viên có thể có một người quản lý; mỗi danh mục có một danh mục cha; mỗi phòng ban nằm dưới một đơn vị cấp trên; mỗi bình luận có thể trả lời một bình luận khác. Muốn lấy **toàn bộ các cấp con**, **chuỗi tổ tiên**, **độ sâu của một nút**, hoặc **độ sâu lớn nhất của cây**, truy vấn một lần JOIN thông thường thường chưa đủ vì số cấp không cố định.

**Truy vấn đệ quy**, thường viết bằng **recursive common table expression (CTE)**, cho phép bắt đầu từ một tập nút gốc rồi liên tục đi theo quan hệ cha–con cho đến khi không còn nút mới. Bài học trình bày cách xây truy vấn, diễn giải kết quả, kiểm soát chu trình và khác biệt giữa các hệ quản trị.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận biết mô hình **adjacency list** dùng cột **id** và **parent_id** (hoặc **quan_ly_id**) để biểu diễn cây.
- Phân biệt **nút gốc**, **nút cha**, **nút con trực tiếp**, **hậu duệ**, **tổ tiên**, **lá**, **mức (level)** và **độ sâu (depth)**.
- Viết **WITH RECURSIVE** với hai phần **anchor** và **recursive member**, nối bằng **UNION ALL**.
- Duyệt **từ gốc xuống lá**, duyệt **một cây con** và truy ngược **từ nút lên tổ tiên**.
- Tính **độ sâu từng nút**, **độ sâu tối đa**, **số nút theo từng tầng** và **số hậu duệ** của một nút.
- Xây đường dẫn từ gốc đến nút; hiểu **thứ tự trình bày** khác **thứ tự xử lý nội bộ** của CTE.
- Nhận diện trường hợp **nhiều gốc**, **mồ côi**, **chu trình**, **khóa trùng** và mô hình không còn là cây thật.
- Kiểm soát đệ quy bằng giới hạn tầng và cơ chế phát hiện chu trình; biết vì sao **UNION** không thay thế hoàn toàn việc chống chu trình.
- So sánh cú pháp **PostgreSQL**, **MySQL 8+**, **SQL Server**, **SQLite**, **Oracle Database**.
- Vận dụng truy vấn vào hệ thống thực tế và đọc được kết quả mong đợi từ dữ liệu mẫu.

## 2. Cây cha-con được lưu trong bảng quan hệ ra sao?

Một cây có các **nút (nodes)** và **cạnh (edges)**. Mỗi nút, ngoại trừ gốc, có đúng **một cha trực tiếp**. Một cha có thể có không, một hoặc nhiều con.

Ví dụ bảng **nhan_vien**:

| id | ho_ten | quan_ly_id |
|---:|---|---:|
| 1 | Lan | NULL |
| 2 | Minh | 1 |
| 3 | Hoa | 1 |
| 4 | Bình | 2 |
| 5 | An | 2 |
| 6 | Dũng | 3 |
| 7 | Hà | 3 |
| 8 | Trang | 6 |
| 9 | Mai | 6 |
| 10 | Linh | NULL |
| 11 | Tâm | 10 |
| 12 | Quỳnh | 8 |

Trong đó:

- **id**: định danh duy nhất mỗi nhân viên.
- **ho_ten**: tên dùng để hiển thị.
- **quan_ly_id**: mã nhân viên quản lý trực tiếp, tham chiếu về **nhan_vien.id**.
- **quan_ly_id IS NULL**: nhân viên không có người quản lý trực tiếp trong phạm vi cấu trúc này, được xem là **gốc**.

Một sơ đồ trực quan:

~~~text
Lan (1)
├── Minh (2)
│   ├── Bình (4)
│   └── An (5)
└── Hoa (3)
    ├── Dũng (6)
    │   ├── Trang (8)
    │   │   └── Quỳnh (12)
    │   └── Mai (9)
    └── Hà (7)

Linh (10)
└── Tâm (11)
~~~

Bảng chứa **hai cây độc lập**, nên toàn bộ dữ liệu là một **rừng (forest)**. Việc có nhiều gốc là hợp lệ nếu mô hình cho phép nhiều tổ chức hoặc nhiều cây danh mục.

### 2.1. Các quan hệ cần phân biệt

Giả sử xét nhân viên **Trang (8)**:

| Khái niệm | Giá trị |
|---|---|
| Cha trực tiếp | Dũng (6) |
| Gốc cây | Lan (1) |
| Tổ tiên | Dũng (6), Hoa (3), Lan (1) |
| Con trực tiếp | Quỳnh (12) |
| Hậu duệ | Quỳnh (12) |
| Đường từ gốc | Lan → Hoa → Dũng → Trang |
| Độ sâu khi gốc bằng 0 | 3 |
| Khoảng cách đến gốc | 3 cạnh |

**Con trực tiếp** khác **tất cả hậu duệ**. Một câu JOIN một lần có thể lấy con trực tiếp, nhưng muốn lấy mọi hậu duệ ở số tầng bất kỳ thì cần lặp quan hệ.

### 2.2. Định nghĩa độ sâu trước khi truy vấn

Trong bài, mặc định:

\[
\operatorname{depth}(\text{gốc})=0
\]

Với mỗi nút con:

\[
\operatorname{depth}(\text{con})=\operatorname{depth}(\text{cha})+1
\]

Như vậy, độ sâu bằng **số cạnh từ gốc đến nút**, không phải số nút trên đường đi.

| Nút | Đường đi | Độ sâu từ gốc |
|---|---|---:|
| Lan (1) | Lan | 0 |
| Hoa (3) | Lan → Hoa | 1 |
| Dũng (6) | Lan → Hoa → Dũng | 2 |
| Trang (8) | Lan → Hoa → Dũng → Trang | 3 |
| Quỳnh (12) | Lan → Hoa → Dũng → Trang → Quỳnh | 4 |

Một số ứng dụng gọi **level** là 1 cho gốc; nếu dùng cách này thì **level = depth + 1**. Hai cách đều có thể đúng, nhưng **phải chọn và ghi rõ một quy ước** để tránh lỗi lệch 1.

## 3. Chuẩn bị dữ liệu để tự thực hành

Ví dụ DDL cho nhiều DBMS phổ biến:

~~~sql
CREATE TABLE nhan_vien (
    id INTEGER PRIMARY KEY,
    ho_ten VARCHAR(100) NOT NULL,
    quan_ly_id INTEGER,
    CONSTRAINT fk_nhan_vien_quan_ly
        FOREIGN KEY (quan_ly_id)
        REFERENCES nhan_vien(id)
);
~~~

Trong cấu trúc này, **FOREIGN KEY tự tham chiếu** giúp kiểm tra rằng mã quản lý có giá trị thì phải tồn tại trong bảng; gốc có **quan_ly_id NULL** vẫn được phép.

Nạp dữ liệu minh họa:

~~~sql
INSERT INTO nhan_vien (id, ho_ten, quan_ly_id) VALUES
    (1,  'Lan',   NULL),
    (2,  'Minh',  1),
    (3,  'Hoa',   1),
    (4,  'Bình',  2),
    (5,  'An',    2),
    (6,  'Dũng',  3),
    (7,  'Hà',    3),
    (8,  'Trang', 6),
    (9,  'Mai',   6),
    (10, 'Linh',  NULL),
    (11, 'Tâm',   10),
    (12, 'Quỳnh', 8);
~~~

Cú pháp **INSERT nhiều nhóm VALUES** không tương thích nguyên văn với mọi phiên bản Oracle; ở Oracle 19c thường cần INSERT ALL hoặc nhiều INSERT. Đối với bài học, phần quan trọng là **bộ dữ liệu logic** và truy vấn đệ quy, không phải cú pháp nạp nhiều hàng.

**Không chạy ví dụ nạp dữ liệu trên môi trường production.** Nên dùng cơ sở dữ liệu bài tập hoặc transaction có thể hoàn tác.

### 3.1. Vì sao không thể nối cố định 2–3 lần?

Để lấy con trực tiếp của Lan:

~~~sql
SELECT id, ho_ten, quan_ly_id
FROM nhan_vien
WHERE quan_ly_id = 1;
~~~

Kết quả là Minh (2), Hoa (3).

Để lấy cháu của Lan, có thể nối hai bản sao của bảng:

~~~sql
SELECT
    c2.id,
    c2.ho_ten
FROM nhan_vien c1
JOIN nhan_vien c2
    ON c2.quan_ly_id = c1.id
WHERE c1.quan_ly_id = 1;
~~~

Kết quả là Bình, An, Dũng, Hà (tầng 2). Nhưng muốn lấy Trang, Mai, Quỳnh phải nối thêm lần nữa hoặc nhiều lần nữa. Nếu doanh nghiệp có 20 tầng thì cách viết số JOIN cố định trở nên khó bảo trì và không linh hoạt.

**Recursive CTE** giải quyết bằng cách mô tả **một bước cha → con** rồi để DBMS lặp bước đó cho đến khi hết kết quả mới.

## 4. Recursive CTE gồm những thành phần nào?

Mẫu tổng quát:

~~~sql
WITH RECURSIVE ten_cte AS (
    -- Phần 1: anchor (điểm bắt đầu)
    SELECT ...

    UNION ALL

    -- Phần 2: recursive member (một bước lặp)
    SELECT ...
    FROM bang_con ...
    JOIN ten_cte ...
        ON ...
)
SELECT ...
FROM ten_cte;
~~~

Có ba phần khái niệm:

1. **Anchor member:** xác định dòng đầu tiên của hành trình, ví dụ toàn bộ nút có quan_ly_id NULL.
2. **Recursive member:** từ các dòng vừa tìm được, tìm các con trực tiếp của chúng và tính thêm thuộc tính như depth + 1.
3. **Truy vấn cuối:** đọc tập kết quả sau khi CTE hoàn tất; có thể sắp xếp, lọc hay tổng hợp.

**UNION ALL** kết hợp dòng anchor và các dòng do bước đệ quy sinh ra mà **không tự loại trùng**. Với một cây hợp lệ, mỗi nút có đúng một đường từ gốc, nên dùng UNION ALL thường đơn giản và hiệu quả.

### 4.1. Truy vấn từ gốc xuống dưới

~~~sql
WITH RECURSIVE cay AS (
    -- Anchor: mọi gốc có độ sâu 0
    SELECT
        id,
        ho_ten,
        quan_ly_id,
        0 AS do_sau,
        id AS ma_goc
    FROM nhan_vien
    WHERE quan_ly_id IS NULL

    UNION ALL

    -- Recursive member: tìm con của những nút đã có
    SELECT
        n.id,
        n.ho_ten,
        n.quan_ly_id,
        c.do_sau + 1 AS do_sau,
        c.ma_goc
    FROM nhan_vien n
    JOIN cay c
        ON n.quan_ly_id = c.id
)
SELECT
    id,
    ho_ten,
    quan_ly_id,
    ma_goc,
    do_sau
FROM cay
ORDER BY ma_goc, do_sau, id;
~~~

Truy vấn này mô tả ý nghĩa đúng cho **PostgreSQL, MySQL 8+, SQLite** và những DBMS hỗ trợ **WITH RECURSIVE** theo cú pháp tương ứng. SQL Server và Oracle không viết từ khóa **RECURSIVE** ở vị trí này; phần phương ngữ ở sau sẽ trình bày cách sửa.

**ma_goc** là giá trị **id của nút anchor**, được mang xuống tất cả con qua **c.ma_goc**. Nó giúp tách các cây trong cùng một rừng.

### 4.2. Kết quả mong đợi

Với tập dữ liệu mẫu:

| id | ho_ten | ma_goc | do_sau |
|---:|---|---:|---:|
| 1 | Lan | 1 | 0 |
| 2 | Minh | 1 | 1 |
| 3 | Hoa | 1 | 1 |
| 4 | Bình | 1 | 2 |
| 5 | An | 1 | 2 |
| 6 | Dũng | 1 | 2 |
| 7 | Hà | 1 | 2 |
| 8 | Trang | 1 | 3 |
| 9 | Mai | 1 | 3 |
| 12 | Quỳnh | 1 | 4 |
| 10 | Linh | 10 | 0 |
| 11 | Tâm | 10 | 1 |

Đây là kết quả theo **ORDER BY ma_goc, do_sau, id**: sắp theo gốc, theo độ sâu rồi theo mã. Truy vấn không cam kết trình bày đúng thứ tự “đọc hết nhánh Minh rồi sang nhánh Hoa”; việc **duyệt theo quan hệ** và **sắp xếp đầu ra** là hai khái niệm riêng.

### 4.3. Diễn giải từng vòng lặp

Với cây Lan:

| Lượt | Dòng mới được tìm | Độ sâu |
|---:|---|---:|
| Anchor | Lan (1) | 0 |
| 1 | Minh (2), Hoa (3) | 1 |
| 2 | Bình (4), An (5), Dũng (6), Hà (7) | 2 |
| 3 | Trang (8), Mai (9) | 3 |
| 4 | Quỳnh (12) | 4 |
| 5 | Không có con mới | Kết thúc |

Trong một mô hình triển khai recursive CTE, DBMS thường duy trì tập kết quả trung gian của từng vòng. Cách xử lý vật lý và thứ tự hàng trong mỗi vòng không nhất thiết giống nhau giữa các hệ.

### 4.4. Tại sao điều kiện JOIN viết như vậy?

~~~sql
ON n.quan_ly_id = c.id
~~~

**n** là ứng viên **con** trong bảng gốc. **c** là nút **cha đã tìm thấy** trong CTE. Điều kiện yêu cầu mã quản lý của n bằng id của c.

Nếu viết ngược:

~~~sql
ON n.id = c.quan_ly_id
~~~

thì đây là hướng đi **lên cha**, không phải đi xuống con. Chọn đúng hướng cạnh là điều quan trọng nhất khi viết thành phần đệ quy.

## 5. Tính độ sâu từng nút

Giá trị depth được tạo như sau:

~~~sql
-- Anchor:
0 AS do_sau

-- Recursive member:
c.do_sau + 1 AS do_sau
~~~

Theo định nghĩa:

\[
d(\text{con})=d(\text{cha})+1
\]

Với Trang (8), chuỗi đường đi là **1 → 3 → 6 → 8**, có ba cạnh, nên độ sâu là **3**. Quỳnh (12) nằm thêm một cạnh nữa nên độ sâu là **4**.

### 5.1. Muốn gốc có level = 1

Chỉ đổi anchor:

~~~sql
SELECT id, ho_ten, quan_ly_id, 1 AS cap_do
FROM nhan_vien
WHERE quan_ly_id IS NULL
~~~

Phần đệ quy vẫn lấy **c.cap_do + 1**. Khi đó Lan/Linh ở cấp 1, Minh/Hoa/Tâm ở cấp 2, Quỳnh ở cấp 5.

Không nên trộn **do_sau** bắt đầu từ 0 với **cap_do** bắt đầu từ 1 trong cùng báo cáo mà không ghi rõ quy ước.

### 5.2. Độ sâu không phải số con

- **Độ sâu**: số cạnh từ gốc đến nút.
- **Số con trực tiếp**: số nút có quan_ly_id bằng id nút đó.
- **Số hậu duệ**: số nút nằm dưới một nút ở mọi cấp.
- **Chiều cao của nút (height)**: độ dài đường đi dài nhất từ nút đó xuống một lá, thường đo bằng số cạnh.

Ví dụ, Hoa (3) có **2 con trực tiếp** là Dũng (6) và Hà (7), nhưng có **4 hậu duệ** là 6, 7, 8, 9 và còn Quỳnh (12), tổng **5 hậu duệ**. Chiều cao của Hoa là **3 cạnh** theo đường 3 → 6 → 8 → 12. Độ sâu của Hoa từ gốc Lan chỉ là **1**.

Phân biệt các đại lượng này giúp tránh gọi nhầm “độ sâu” khi thực chất cần “chiều cao” hoặc “số cấp con”.

## 6. Duyệt một cây con từ một nút cho trước

Nếu cần lấy toàn bộ nhân viên cấp dưới của **Hoa (3)**, đổi anchor thành nút có id = 3.

~~~sql
WITH RECURSIVE cay_con AS (
    SELECT
        id,
        ho_ten,
        quan_ly_id,
        0 AS do_sau_tuong_doi
    FROM nhan_vien
    WHERE id = 3

    UNION ALL

    SELECT
        n.id,
        n.ho_ten,
        n.quan_ly_id,
        c.do_sau_tuong_doi + 1
    FROM nhan_vien n
    JOIN cay_con c
        ON n.quan_ly_id = c.id
)
SELECT
    id,
    ho_ten,
    do_sau_tuong_doi
FROM cay_con
ORDER BY do_sau_tuong_doi, id;
~~~

Kết quả:

| id | ho_ten | do_sau_tuong_doi |
|---:|---|---:|
| 3 | Hoa | 0 |
| 6 | Dũng | 1 |
| 7 | Hà | 1 |
| 8 | Trang | 2 |
| 9 | Mai | 2 |
| 12 | Quỳnh | 3 |

**do_sau_tuong_doi** trong ví dụ này đo **khoảng cách từ Hoa**, không phải độ sâu từ gốc Lan. Trang có độ sâu toàn cục 3 nhưng độ sâu tương đối từ Hoa là 2.

### 6.1. Cây con có bao gồm nút được chọn không?

Truy vấn trên **có** Hoa (anchor). Nếu yêu cầu “chỉ lấy cấp dưới của Hoa, không bao gồm chính Hoa”, lọc ở SELECT ngoài:

~~~sql
SELECT id, ho_ten, do_sau_tuong_doi
FROM cay_con
WHERE do_sau_tuong_doi > 0;
~~~

Cách này giữ khả năng dùng Hoa làm điểm bắt đầu để tìm con, rồi loại Hoa khi xuất kết quả. **Không loại anchor trước khi đệ quy**, vì nếu anchor không tồn tại thì không thể đi xuống.

### 6.2. Cây con của nút lá

Nếu chọn **Bình (4)**, anchor trả một dòng Bình ở độ sâu 0; bước đệ quy không tìm thấy con. Kết quả có một dòng nếu bao gồm nút gốc của cây con, hoặc không có dòng nếu lọc do_sau_tuong_doi > 0.

### 6.3. Cây con của mã không tồn tại

Nếu anchor dùng **id = 999** nhưng không có bản ghi, tập anchor rỗng; recursive member không thể sinh thêm dòng. Kết quả rỗng.

Ở tầng ứng dụng, cần phân biệt **không có nút 999** với **nút tồn tại nhưng không có cấp dưới**. Trường hợp thứ hai sẽ có một dòng khi bao gồm anchor, còn trường hợp thứ nhất không có dòng.

## 7. Duyệt ngược: tìm tổ tiên và khoảng cách tới gốc

Muốn biết **Quỳnh (12)** nằm dưới ai, bắt đầu từ 12 rồi liên tục tìm **cha**.

~~~sql
WITH RECURSIVE to_tien AS (
    SELECT
        id,
        ho_ten,
        quan_ly_id,
        0 AS khoang_cach
    FROM nhan_vien
    WHERE id = 12

    UNION ALL

    SELECT
        cha.id,
        cha.ho_ten,
        cha.quan_ly_id,
        t.khoang_cach + 1
    FROM nhan_vien cha
    JOIN to_tien t
        ON cha.id = t.quan_ly_id
)
SELECT
    id,
    ho_ten,
    khoang_cach
FROM to_tien
ORDER BY khoang_cach;
~~~

Kết quả:

| id | ho_ten | khoang_cach |
|---:|---|---:|
| 12 | Quỳnh | 0 |
| 8 | Trang | 1 |
| 6 | Dũng | 2 |
| 3 | Hoa | 3 |
| 1 | Lan | 4 |

Ở truy vấn này, **khoang_cach** là số cạnh **đi ngược từ Quỳnh**, không phải độ sâu của mỗi tổ tiên trong toàn cây. Lan có độ sâu toàn cục 0 nhưng khoang_cach = 4 so với Quỳnh.

### 7.1. Chỉ lấy tổ tiên, không lấy chính nút

~~~sql
SELECT id, ho_ten, khoang_cach
FROM to_tien
WHERE khoang_cach > 0
ORDER BY khoang_cach;
~~~

Kết quả là Trang, Dũng, Hoa, Lan.

### 7.2. Tìm gốc của nút

Khi chuỗi tham chiếu cha hợp lệ và không có chu trình, gốc là dòng trong kết quả to_tien có **quan_ly_id IS NULL**:

~~~sql
SELECT id AS ma_goc, ho_ten AS ten_goc
FROM to_tien
WHERE quan_ly_id IS NULL;
~~~

Với Quỳnh, kết quả là **Lan (1)**.

Nếu tham chiếu cha bị thiếu ở giữa hoặc có chu trình, truy vấn có thể không tìm thấy dòng gốc, hoặc lặp nếu không bảo vệ. Phần dữ liệu bất thường sẽ trình bày cách xử lý.

## 8. Tính độ sâu tối đa của từng cây

Từ CTE **cay** ở phần 4, có thể tổng hợp:

~~~sql
WITH RECURSIVE cay AS (
    SELECT
        id,
        quan_ly_id,
        0 AS do_sau,
        id AS ma_goc
    FROM nhan_vien
    WHERE quan_ly_id IS NULL

    UNION ALL

    SELECT
        n.id,
        n.quan_ly_id,
        c.do_sau + 1,
        c.ma_goc
    FROM nhan_vien n
    JOIN cay c
        ON n.quan_ly_id = c.id
)
SELECT
    ma_goc,
    MAX(do_sau) AS do_sau_lon_nhat
FROM cay
GROUP BY ma_goc
ORDER BY ma_goc;
~~~

Kết quả:

| ma_goc | do_sau_lon_nhat |
|---:|---:|
| 1 | 4 |
| 10 | 1 |

- Cây Lan có đường dài nhất **1 → 3 → 6 → 8 → 12**, gồm 4 cạnh.
- Cây Linh có đường **10 → 11**, gồm 1 cạnh.

**MAX(do_sau)** là độ sâu lớn nhất của các nút **được CTE duyệt tới**. Nếu có dữ liệu mồ côi hoặc một chu trình tách biệt khỏi gốc, các dòng đó không xuất hiện trong CTE bắt đầu từ **quan_ly_id IS NULL**, nên kết quả này không phản ánh toàn bộ các dòng không kết nối gốc.

### 8.1. Độ sâu lớn nhất của toàn bộ rừng

Nếu chỉ cần một giá trị:

~~~sql
WITH RECURSIVE cay AS (
    SELECT id, quan_ly_id, 0 AS do_sau
    FROM nhan_vien
    WHERE quan_ly_id IS NULL

    UNION ALL

    SELECT n.id, n.quan_ly_id, c.do_sau + 1
    FROM nhan_vien n
    JOIN cay c ON n.quan_ly_id = c.id
)
SELECT MAX(do_sau) AS do_sau_lon_nhat
FROM cay;
~~~

Kết quả theo mẫu: **4**.

Nếu bảng không có gốc nào, CTE có thể rỗng; **MAX(...) trên tập rỗng trả NULL** theo ngữ nghĩa tổng hợp thông thường, không tự trả 0. Đó có thể là dấu hiệu bảng trống, dữ liệu chỉ có chu trình hoặc quy tắc nhận diện gốc không đúng.

### 8.2. Chiều cao của một cây con

Với CTE bắt đầu tại **Hoa (3)** ở phần 6:

~~~sql
SELECT MAX(do_sau_tuong_doi) AS chieu_cao
FROM cay_con;
~~~

Kết quả là **3 cạnh**. Vì anchor có do_sau_tuong_doi = 0, trường hợp cây con chỉ có một nút sẽ cho chiều cao 0.

Không nhầm **chiều cao tính từ Hoa** với **độ sâu toàn cục của Hoa**.

## 9. Đếm số nút ở từng độ sâu

Đây là dạng báo cáo “tổ chức có bao nhiêu tầng nhân viên” hoặc “có bao nhiêu danh mục ở mỗi cấp”.

~~~sql
WITH RECURSIVE cay AS (
    SELECT
        id,
        quan_ly_id,
        id AS ma_goc,
        0 AS do_sau
    FROM nhan_vien
    WHERE quan_ly_id IS NULL

    UNION ALL

    SELECT
        n.id,
        n.quan_ly_id,
        c.ma_goc,
        c.do_sau + 1
    FROM nhan_vien n
    JOIN cay c ON n.quan_ly_id = c.id
)
SELECT
    ma_goc,
    do_sau,
    COUNT(*) AS so_nut
FROM cay
GROUP BY ma_goc, do_sau
ORDER BY ma_goc, do_sau;
~~~

Kết quả:

| ma_goc | do_sau | so_nut |
|---:|---:|---:|
| 1 | 0 | 1 |
| 1 | 1 | 2 |
| 1 | 2 | 4 |
| 1 | 3 | 2 |
| 1 | 4 | 1 |
| 10 | 0 | 1 |
| 10 | 1 | 1 |

Tổng các giá trị so_nut là **12**, bằng số nhân viên mẫu. Trong một **cây hợp lệ** được bắt đầu từ mọi gốc, mỗi nút xuất hiện đúng một lần. Nếu dữ liệu có nút không nối được tới gốc hoặc có đường trùng trong mô hình đồ thị, tổng này có thể không còn bằng số dòng bảng gốc.

## 10. Tìm nút lá và nút có con

**Nút lá** là nút không có **con trực tiếp** trong phạm vi cấu trúc đang xét.

Không cần đệ quy để kiểm tra một nút có con hay không:

~~~sql
SELECT
    n.id,
    n.ho_ten
FROM nhan_vien n
WHERE NOT EXISTS (
    SELECT 1
    FROM nhan_vien c
    WHERE c.quan_ly_id = n.id
)
ORDER BY n.id;
~~~

Với dữ liệu mẫu, các lá là:

| id | ho_ten |
|---:|---|
| 4 | Bình |
| 5 | An |
| 7 | Hà |
| 9 | Mai |
| 11 | Tâm |
| 12 | Quỳnh |

**Trang (8)** không phải lá vì có con Quỳnh (12), dù Trang chỉ có một con.

### 10.1. Kết hợp độ sâu và điều kiện lá

Nếu muốn biết các lá nằm ở cấp nào:

~~~sql
WITH RECURSIVE cay AS (
    SELECT id, ho_ten, quan_ly_id, 0 AS do_sau
    FROM nhan_vien
    WHERE quan_ly_id IS NULL

    UNION ALL

    SELECT n.id, n.ho_ten, n.quan_ly_id, c.do_sau + 1
    FROM nhan_vien n
    JOIN cay c ON n.quan_ly_id = c.id
)
SELECT
    c.id,
    c.ho_ten,
    c.do_sau
FROM cay c
WHERE NOT EXISTS (
    SELECT 1
    FROM nhan_vien n
    WHERE n.quan_ly_id = c.id
)
ORDER BY c.do_sau DESC, c.id;
~~~

Cách này tìm **lá trong toàn bảng** nhưng chỉ hiển thị các lá **duyệt tới từ gốc**. Trong dữ liệu sạch, hai tập trùng nhau. Với orphan/cycle, cần xét lại tập cần kiểm tra.

### 10.2. “Lá trong cây con bị cắt ở depth 2” khác lá thật

Nếu CTE giới hạn do_sau <= 2 rồi kiểm tra không có con trong **kết quả CTE**, một nút depth 2 có thể trông giống lá dù nó còn con ở depth 3 ngoài giới hạn.

Vì vậy, hãy xác định:

- **Lá thật của cấu trúc toàn bảng:** không có con trong bảng nguồn.
- **Lá của tập kết quả đã bị giới hạn:** không có con được chọn trong phạm vi truy vấn.

Hai khái niệm khác nhau và có thể dẫn tới kết quả khác nhau.

## 11. Lọc theo một độ sâu cụ thể

Từ CTE cay:

~~~sql
SELECT id, ho_ten, ma_goc, do_sau
FROM cay
WHERE do_sau = 2;
~~~

Kết quả trên cây Lan là **Bình (4), An (5), Dũng (6), Hà (7)**.

Để lấy các nút từ tầng 1 đến tầng 3:

~~~sql
SELECT id, ho_ten, do_sau
FROM cay
WHERE do_sau BETWEEN 1 AND 3;
~~~

**BETWEEN** bao gồm cả hai cận, nên các cấp 1, 2, 3 được giữ; không có cấp 0 hay cấp 4.

### 11.1. Giới hạn ở SELECT ngoài không luôn tiết kiệm đệ quy

~~~sql
SELECT id, ho_ten, do_sau
FROM cay
WHERE do_sau <= 2;
~~~

Ở mức ngữ nghĩa, truy vấn trả các nút đến tầng 2. Tuy nhiên, nếu giới hạn chỉ ở SELECT ngoài, phần CTE có thể vẫn duyệt sâu hơn trước khi lọc kết quả.

Nếu mục tiêu là **không tạo dòng đệ quy sâu hơn tầng 2**, đặt giới hạn trong recursive member:

~~~sql
WITH RECURSIVE cay AS (
    SELECT id, ho_ten, quan_ly_id, 0 AS do_sau
    FROM nhan_vien
    WHERE quan_ly_id IS NULL

    UNION ALL

    SELECT n.id, n.ho_ten, n.quan_ly_id, c.do_sau + 1
    FROM nhan_vien n
    JOIN cay c ON n.quan_ly_id = c.id
    WHERE c.do_sau < 2
)
SELECT id, ho_ten, do_sau
FROM cay
ORDER BY do_sau, id;
~~~

Kết quả chứa **độ sâu 0, 1, 2**. Ở lượt đang có c.do_sau = 2, điều kiện **c.do_sau < 2** không còn TRUE, nên không phát sinh con có độ sâu 3.

### 11.2. Giới hạn tầng không đồng nghĩa phát hiện chu trình

Nếu dữ liệu có chu trình, một điều kiện **c.do_sau < 100** có thể ngăn đệ quy kéo dài quá 100 tầng, nhưng **không chứng minh dữ liệu hợp lệ**. Nó chỉ cắt bớt kết quả; nút có thể lặp lại nhiều lần trước khi đạt giới hạn.

Khi muốn kiểm tra hoặc chịu được dữ liệu có chu trình, cần giải pháp phát hiện nút đã đi qua trên **từng đường đi**.

## 12. Xây đường dẫn từ gốc tới nút

Bên cạnh độ sâu, ứng dụng thường cần chuỗi:

~~~text
Lan > Hoa > Dũng > Trang > Quỳnh
~~~

hoặc đường dẫn mã:

~~~text
/1/3/6/8/12
~~~

Đường dẫn hữu ích cho breadcrumb, hiển thị cây trong ứng dụng, phát hiện đường đi lặp và sắp xếp theo nhánh. Tuy nhiên, **cú pháp nối chuỗi** và **kiểu chuỗi trong CTE đệ quy** khác nhau giữa các DBMS.

### 12.1. PostgreSQL: nối chuỗi bằng ||

Ví dụ:

~~~sql
WITH RECURSIVE cay AS (
    SELECT
        n.id,
        n.ho_ten,
        n.quan_ly_id,
        0 AS do_sau,
        n.ho_ten::text AS duong_dan_ten
    FROM nhan_vien n
    WHERE n.quan_ly_id IS NULL

    UNION ALL

    SELECT
        n.id,
        n.ho_ten,
        n.quan_ly_id,
        c.do_sau + 1,
        c.duong_dan_ten || ' > ' || n.ho_ten
    FROM nhan_vien n
    JOIN cay c ON n.quan_ly_id = c.id
)
SELECT id, ho_ten, do_sau, duong_dan_ten
FROM cay
ORDER BY id;
~~~

Cú pháp **::text** và phép nối chuỗi **||** ở ví dụ phù hợp PostgreSQL. Đối với Quỳnh:

~~~text
Lan > Hoa > Dũng > Trang > Quỳnh
~~~

Một số DBMS cũng dùng ||, nhưng **SQL Server** thường dùng **+** cho nối chuỗi, **MySQL** thường dùng **CONCAT**. Không nên sao chép nguyên PostgreSQL query sang các hệ đó.

### 12.2. MySQL: phải chú ý độ rộng kiểu ở anchor

Một mẫu trong MySQL 8+:

~~~sql
WITH RECURSIVE cay AS (
    SELECT
        n.id,
        n.ho_ten,
        n.quan_ly_id,
        0 AS do_sau,
        CAST(n.ho_ten AS CHAR(1000)) AS duong_dan_ten
    FROM nhan_vien n
    WHERE n.quan_ly_id IS NULL

    UNION ALL

    SELECT
        n.id,
        n.ho_ten,
        n.quan_ly_id,
        c.do_sau + 1,
        CONCAT(c.duong_dan_ten, ' > ', n.ho_ten)
    FROM nhan_vien n
    JOIN cay c ON n.quan_ly_id = c.id
)
SELECT id, do_sau, duong_dan_ten
FROM cay;
~~~

**Vì sao CAST?** Trong MySQL, kiểu cột kết quả CTE đệ quy được xác định từ **anchor**. Nếu anchor chỉ có tên ngắn, phần đệ quy nối thêm nhiều tên có thể **vượt độ rộng đã suy ra**, gây lỗi “Data too long” hoặc hành vi phụ thuộc chế độ SQL. CAST chuỗi ở anchor thành độ rộng phù hợp tránh việc kiểu quá hẹp.

Nhưng **CHAR(1000) không phải giới hạn an toàn cho mọi cây**. Cần tính độ sâu tối đa, chiều dài tên, encoding và giới hạn kiểu. Nếu đường dẫn có thể rất dài, nên thiết kế lại cách biểu diễn thay vì tăng độ rộng không kiểm soát.

### 12.3. SQL Server: ép kiểu của anchor và nhánh đệ quy

Trong SQL Server, recursive CTE không có từ khóa RECURSIVE:

~~~sql
WITH cay AS (
    SELECT
        id,
        ho_ten,
        quan_ly_id,
        0 AS do_sau,
        CAST(ho_ten AS NVARCHAR(MAX)) AS duong_dan_ten
    FROM nhan_vien
    WHERE quan_ly_id IS NULL

    UNION ALL

    SELECT
        n.id,
        n.ho_ten,
        n.quan_ly_id,
        c.do_sau + 1,
        CAST(c.duong_dan_ten + N' > ' + n.ho_ten
             AS NVARCHAR(MAX))
    FROM nhan_vien n
    JOIN cay c
        ON n.quan_ly_id = c.id
)
SELECT id, do_sau, duong_dan_ten
FROM cay
OPTION (MAXRECURSION 100);
~~~

Ở SQL Server, **kiểu của các cột tương ứng trong anchor và recursive member phải khớp theo yêu cầu recursive CTE**, nên dùng CAST phù hợp ở cả hai phần nếu cần. **NVARCHAR(MAX)** giúp đường dẫn không bị giới hạn bởi kích thước của tên ở anchor, nhưng vẫn có chi phí bộ nhớ.

**OPTION (MAXRECURSION 100)** là query hint giới hạn độ sâu thực thi; nó không tự phát hiện chu trình và không thay thế kiểm tra dữ liệu. SQL Server có giới hạn đệ quy mặc định thường là 100; muốn đổi phải đặt query hint phù hợp. **MAXRECURSION 0** bỏ giới hạn do hint này, có thể nguy hiểm với dữ liệu có chu trình.

### 12.4. Đường dẫn tên hay đường dẫn ID?

Đường dẫn **tên** dễ đọc nhưng:

- Tên có thể trùng hoặc thay đổi.
- Tên chứa dấu phân cách như **/** hoặc **>** khiến phân tích chuỗi khó hơn.
- Chuỗi có thể dài và ảnh hưởng hiệu năng.

Đường dẫn **ID** ổn định hơn nếu id không đổi và duy nhất. Với bài toán **phát hiện chu trình**, nên theo dõi **ID** hoặc khóa định danh, không nên dựa vào tên.

## 13. Thứ tự hiển thị: breadth-first và depth-first

Hai cách duyệt phổ biến trong cấu trúc cây:

- **Breadth-first (BFS):** hiển thị các nút theo tầng, ưu tiên tầng nông trước.
- **Depth-first (DFS):** hiển thị theo nhánh, đi sâu xuống nhánh đang xét rồi mới chuyển nhánh khác.

Ví dụ ở cây Lan:

~~~text
BFS theo id:
Lan
Minh, Hoa
Bình, An, Dũng, Hà
Trang, Mai
Quỳnh

Một DFS theo thứ tự id của con:
Lan
  Minh
    Bình
    An
  Hoa
    Dũng
      Trang
        Quỳnh
      Mai
    Hà
~~~

**Recursive CTE xác định quan hệ nút được tìm, không tự cam kết thứ tự đầu ra**. Không nên nghĩ rằng do DBMS có thể dùng một tập làm việc theo tầng thì SELECT không ORDER BY chắc chắn cho BFS.

### 13.1. Sắp xếp gần với BFS

Nếu có **do_sau**, sắp theo:

~~~sql
ORDER BY ma_goc, do_sau, id;
~~~

sẽ tạo **thứ tự theo tầng** trong từng cây, với tiêu chí phụ theo id. Đây là cách trình bày BFS ở mức nhóm theo chiều sâu; thứ tự các nút cùng tầng được chọn bằng id, không nhất thiết phản ánh thứ tự con theo từng cha.

### 13.2. Sắp theo nhánh bằng path key

Để tạo thứ tự **DFS ổn định**, có thể xây **duong_sap_xep** bằng chuỗi mã ID ở từng cấp rồi ORDER BY chuỗi đó.

Ví dụ đường đi:

~~~text
/000001/000003/000006/000008/000012
~~~

Nếu mỗi đoạn ID được cố định độ rộng, thứ tự từ điển của đường dẫn thường khớp với thứ tự cây theo các mã ID không âm trong phạm vi độ rộng đó.

Nhưng nếu dùng chuỗi ID **không đệm 0**, thứ tự từ điển có thể đặt **10 trước 2**, không giống thứ tự số. Cần chọn cách mã hóa đoạn rõ ràng, hoặc dùng cấu trúc mảng/ordering column chuyên biệt của DBMS.

### 13.3. PostgreSQL SEARCH DEPTH FIRST / BREADTH FIRST

PostgreSQL phiên bản 14+ hỗ trợ cú pháp **SEARCH** trong recursive CTE:

~~~sql
WITH RECURSIVE cay(id, ho_ten, quan_ly_id, do_sau) AS (
    SELECT
        id, ho_ten, quan_ly_id, 0
    FROM nhan_vien
    WHERE quan_ly_id IS NULL

    UNION ALL

    SELECT
        n.id, n.ho_ten, n.quan_ly_id, c.do_sau + 1
    FROM nhan_vien n
    JOIN cay c ON n.quan_ly_id = c.id
)
SEARCH DEPTH FIRST BY id SET thu_tu
SELECT id, ho_ten, quan_ly_id, do_sau
FROM cay
ORDER BY thu_tu;
~~~

**SEARCH DEPTH FIRST ... SET thu_tu** tạo cột sắp xếp cho DFS; **SEARCH BREADTH FIRST** cho cách sắp theo tầng. Cần **ORDER BY thu_tu** để trình bày theo thứ tự đó. SEARCH không có nghĩa DBMS bắt buộc thay đổi thuật toán vật lý đệ quy thành DFS/BFS; nó chủ yếu cung cấp khóa sắp xếp theo yêu cầu.

Không phải mọi DBMS hỗ trợ cú pháp SEARCH theo SQL chuẩn; nhiều hệ cần tự xây path key.

## 14. Phát hiện chu trình: trường hợp đặc biệt nguy hiểm

Một **cây hợp lệ** không có chu trình. Nhưng dữ liệu sai có thể tạo:

~~~text
A (20) -> B (21) -> A (20)
~~~

trong đó mũi tên biểu thị đường đi từ cha đến con hoặc quan hệ tham chiếu tạo vòng. Ví dụ:

| id | quan_ly_id |
|---:|---:|
| 20 | 21 |
| 21 | 20 |

Nếu bắt đầu đệ quy tại 20 và đi theo con, truy vấn có thể tạo chuỗi:

~~~text
20 -> 21 -> 20 -> 21 -> 20 -> ...
~~~

Với **UNION ALL** và cột depth tăng, mỗi vòng tạo thêm dòng mới, nên không tự kết thúc. DBMS có thể dừng do ngưỡng recursion, lỗi tài nguyên hoặc timeout; không nên trông chờ các giới hạn đó là giải pháp nghiệp vụ.

### 14.1. Chu trình có thể không được tìm thấy từ gốc

Trong mô hình mỗi nút có đúng **một parent_id**, một chu trình kín thường **không nối được tới nút gốc có parent_id NULL** theo hướng cha–con. Vì vậy:

~~~sql
WHERE quan_ly_id IS NULL
~~~

làm anchor có thể **bỏ sót cả thành phần chứa chu trình**. Truy vấn từ các gốc hợp lệ chạy xong không chứng minh toàn bảng không có chu trình.

Muốn kiểm tra chất lượng dữ liệu, cần thêm truy vấn phát hiện **nút không thể đi từ gốc** hoặc bắt đầu chuỗi tổ tiên tại các nút cần kiểm tra, có cơ chế chống vòng lặp.

### 14.2. Giới hạn tầng là biện pháp an toàn bổ sung

Trong recursive member:

~~~sql
WHERE c.do_sau < 100
~~~

sẽ không sinh dòng sau tầng 100, nhưng **không biết** liệu câu SQL kết thúc vì đã đến lá hay vì vừa cắt một chu trình hoặc cây sâu hợp lệ. Truy vấn an toàn nên có cả:

1. **Giới hạn tầng** theo chính sách để bảo vệ tài nguyên.
2. **Phát hiện nút đã xuất hiện trong đường đi** để loại/đánh dấu chu trình.
3. **Cơ chế báo dữ liệu lỗi** nếu có chu trình hoặc dữ liệu không nối về gốc.

### 14.3. PostgreSQL: theo dõi mảng ID đã ghé thăm

Ví dụ duyệt từ một nút tùy chọn, có thể có dữ liệu sai:

~~~sql
WITH RECURSIVE duyet AS (
    SELECT
        n.id,
        n.quan_ly_id,
        0 AS do_sau,
        ARRAY[n.id] AS da_tham
    FROM nhan_vien n
    WHERE n.id = 20

    UNION ALL

    SELECT
        n.id,
        n.quan_ly_id,
        d.do_sau + 1,
        d.da_tham || n.id
    FROM nhan_vien n
    JOIN duyet d
        ON n.quan_ly_id = d.id
    WHERE NOT (n.id = ANY(d.da_tham))
      AND d.do_sau < 100
)
SELECT id, quan_ly_id, do_sau, da_tham
FROM duyet;
~~~

**ARRAY[n.id]** lưu các ID trên đường đi. Trước khi thêm n, điều kiện:

~~~sql
NOT (n.id = ANY(d.da_tham))
~~~

kiểm tra ID n **chưa từng xuất hiện trên chính đường đi đó**.

Nếu 20 → 21 → 20, truy vấn thêm 20 rồi 21; đến lúc xét thêm 20 lần hai, điều kiện không TRUE nên không tạo dòng lặp.

Đây là cú pháp PostgreSQL cho mảng, **không portable** sang SQL Server/MySQL/SQLite. Mảng **da_tham** là tập đường đi có thứ tự, không phải một danh sách ID toàn cục cho tất cả nhánh; một nút có thể xuất hiện trên hai đường khác nhau trong mô hình đồ thị, tùy dữ liệu.

### 14.4. PostgreSQL CYCLE

PostgreSQL 14+ hỗ trợ cú pháp **CYCLE** theo hướng SQL chuẩn cho recursive CTE:

~~~sql
WITH RECURSIVE duyet(id, quan_ly_id, do_sau) AS (
    SELECT id, quan_ly_id, 0
    FROM nhan_vien
    WHERE id = 20

    UNION ALL

    SELECT
        n.id,
        n.quan_ly_id,
        d.do_sau + 1
    FROM nhan_vien n
    JOIN duyet d ON n.quan_ly_id = d.id
)
CYCLE id SET la_chu_trinh USING duong_id
SELECT id, quan_ly_id, do_sau, la_chu_trinh, duong_id
FROM duyet;
~~~

**CYCLE id** yêu cầu theo dõi ID lặp trên đường đi. DBMS tạo cột trạng thái chu trình và cột đường đi. Trong mô hình trên, một dòng lặp có thể được đánh dấu là chu trình rồi không tiếp tục mở rộng. Khi cần phân biệt **phát hiện lỗi** với **bỏ qua lỗi**, hãy kiểm tra cột la_chu_trinh thay vì chỉ lẳng lặng loại dòng lặp.

Tính năng CYCLE/SEARCH có thể không có trong các DBMS hay phiên bản cũ hơn. Ngoài ra, câu lệnh trên giả định các nút 20,21 đã có trong bảng; chúng **không thuộc bộ dữ liệu sạch** ở phần 2.

### 14.5. Dùng chuỗi đường dẫn khi không có mảng

Trong DBMS không hỗ trợ mảng như PostgreSQL, có thể tạo đường dẫn ID được bao bởi dấu phân cách:

~~~text
,1,3,6,8,
~~~

Để kiểm tra nút 12 có trong đường dẫn hay chưa, tìm chuỗi:

~~~text
,12,
~~~

**Không** chỉ tìm **'12'** trong một chuỗi mã nối tự do vì mã 2 có thể vô tình khớp bên trong 12.

Ví dụ ý tưởng trên MySQL:

~~~sql
WITH RECURSIVE duyet AS (
    SELECT
        n.id,
        n.quan_ly_id,
        0 AS do_sau,
        CAST(CONCAT(',', n.id, ',') AS CHAR(2000)) AS duong_id
    FROM nhan_vien n
    WHERE n.id = 20

    UNION ALL

    SELECT
        n.id,
        n.quan_ly_id,
        d.do_sau + 1,
        CONCAT(d.duong_id, n.id, ',')
    FROM nhan_vien n
    JOIN duyet d
        ON n.quan_ly_id = d.id
    WHERE LOCATE(CONCAT(',', n.id, ','), d.duong_id) = 0
      AND d.do_sau < 100
)
SELECT * FROM duyet;
~~~

Điều kiện **LOCATE** không tìm thấy chuỗi ID đã có trong path. Mẫu này dành cho **ID số nguyên**, không chứa dấu phẩy; nếu khóa là chuỗi có dấu phân cách cần escape hoặc mã hóa khóa rõ ràng. Độ rộng path và giới hạn tầng phải được chọn tương ứng. Với dữ liệu lớn, dùng giải pháp chu trình chuyên biệt hoặc kiểm soát toàn vẹn ở tầng ứng dụng có thể phù hợp hơn.

### 14.6. Vì sao UNION thay UNION ALL chưa đủ?

Một cách thử là đổi:

~~~sql
UNION ALL
~~~

thành:

~~~sql
UNION
~~~

**UNION** loại các dòng trùng **theo toàn bộ cột của CTE**, có thể giúp ngừng lặp trong một số phép truy hồi mà dòng mới giống hệt dòng cũ. Nhưng nếu CTE có:

~~~text
(id, do_sau)
(20, 0)
(21, 1)
(20, 2)
(21, 3)
...
~~~

thì mỗi cặp **(id, do_sau)** đều khác nhau. UNION không loại được lần xuất hiện sau của cùng ID vì **do_sau đã đổi**. Nếu thêm path, mỗi vòng càng tạo chuỗi mới.

**Kết luận:** UNION không phải công cụ phát hiện chu trình đáng tin cậy cho truy vấn tính độ sâu. Cần theo dõi **ID hoặc khóa** đã gặp trên đường đi.

## 15. Dữ liệu mồ côi: parent_id không tìm thấy cha

Xét một bản ghi sai trong bảng staging:

| id | ho_ten | quan_ly_id |
|---:|---|---:|
| 30 | Nhân viên chưa rõ quản lý | 999 |

Nếu không có id 999, nút 30 là **mồ côi (orphan)**. Nó không phải gốc theo quy tắc **quan_ly_id IS NULL**, nhưng cũng không thể đi từ gốc nào đến nó.

### 15.1. Tìm các dòng thiếu bản ghi cha

~~~sql
SELECT
    n.id,
    n.ho_ten,
    n.quan_ly_id
FROM nhan_vien n
LEFT JOIN nhan_vien cha
    ON cha.id = n.quan_ly_id
WHERE n.quan_ly_id IS NOT NULL
  AND cha.id IS NULL;
~~~

Trong bộ dữ liệu sạch sẽ **không có dòng nào**. Nếu thêm dòng id 30, quan_ly_id 999 vào bảng chưa áp dụng FOREIGN KEY, truy vấn sẽ trả id 30.

**Phân biệt:**

- **quan_ly_id IS NULL**: nút gốc theo quy ước.
- **quan_ly_id = 999** nhưng không có cha: orphan.
- **có cha nhưng chuỗi cha tạo vòng**: chu trình.

Ba trường hợp cần xử lý khác nhau. Không nên tự động coi mọi orphan là gốc nếu nghiệp vụ không cho phép.

### 15.2. Kiểm tra nút không thể duyệt từ gốc

Có thể tìm những ID không được recursive CTE từ mọi gốc chạm tới:

~~~sql
WITH RECURSIVE cay AS (
    SELECT id, quan_ly_id
    FROM nhan_vien
    WHERE quan_ly_id IS NULL

    UNION ALL

    SELECT n.id, n.quan_ly_id
    FROM nhan_vien n
    JOIN cay c ON n.quan_ly_id = c.id
)
SELECT n.id, n.ho_ten, n.quan_ly_id
FROM nhan_vien n
WHERE NOT EXISTS (
    SELECT 1
    FROM cay c
    WHERE c.id = n.id
);
~~~

Trên một **bảng adjacency list có ID duy nhất**, các dòng không thể đi từ gốc có thể gồm orphan, hậu duệ của orphan hoặc thành phần chứa chu trình. **Truy vấn này phát hiện không thể tới từ gốc; nó không phân biệt nguyên nhân**. Nếu muốn biết chính xác vì sao, phải kiểm tra chuỗi tổ tiên hoặc constraint.

Nếu dữ liệu là một đồ thị có nhiều đường đi và chu trình, truy vấn không bảo vệ chu trình có thể không an toàn; ở ví dụ adjacency list mỗi nút một cha, chu trình kín không có đường đi xuống từ gốc nên không bị mở rộng từ anchor gốc, nhưng không thể áp dụng nhận định này cho đồ thị tổng quát.

### 15.3. FOREIGN KEY chưa bảo đảm không có chu trình

Một FOREIGN KEY tự tham chiếu bảo đảm cha tồn tại (với khóa không NULL và constraint được thực thi), nhưng **không tự ngăn mọi chu trình**. Hai nhân viên có thể cùng lúc trỏ nhau theo những thao tác cho phép hoặc đã tồn tại do migration/kiểm tra trì hoãn.

**CHECK (id <> quan_ly_id)** có thể ngăn một nút tự làm cha của chính nó, nhưng **không ngăn vòng dài hơn** như 20 → 21 → 20.

Muốn bảo đảm cấu trúc thật sự là cây, hệ thống có thể cần logic kiểm tra vòng lặp tại giao dịch cập nhật quan hệ cha, quy tắc tổ chức và cơ chế đồng thời phù hợp.

## 16. Nhiều gốc, không có gốc, và biểu diễn rừng

Nếu nhiều dòng có **quan_ly_id IS NULL**, recursive CTE anchor nhiều dòng. Mỗi gốc mở một cây riêng, và dùng **ma_goc** để nhận diện.

### 16.1. Chỉ duyệt một gốc cụ thể

~~~sql
WITH RECURSIVE cay AS (
    SELECT
        id,
        ho_ten,
        quan_ly_id,
        0 AS do_sau
    FROM nhan_vien
    WHERE id = 1

    UNION ALL

    SELECT
        n.id,
        n.ho_ten,
        n.quan_ly_id,
        c.do_sau + 1
    FROM nhan_vien n
    JOIN cay c ON n.quan_ly_id = c.id
)
SELECT id, ho_ten, do_sau
FROM cay;
~~~

Kết quả chỉ có các nút dưới **Lan (1)** và Lan, không có Linh/Tâm.

### 16.2. Không có gốc nào

Nếu mọi quan_ly_id khác NULL, anchor “WHERE quan_ly_id IS NULL” là rỗng. CTE trả rỗng, kể cả khi bảng có nhiều nhân viên.

Nguyên nhân có thể là:

- Dữ liệu chỉ có thành phần chu trình.
- Mọi nút trỏ tới cha không tồn tại (khi thiếu FOREIGN KEY).
- Mô hình dùng **mã sentinel** khác NULL để biểu diễn gốc.
- Điều kiện anchor không phù hợp mô hình dữ liệu.

Không nên xem kết quả rỗng là bằng chứng bảng không có dữ liệu.

### 16.3. Có thể dùng một nút gốc giả?

Một số hệ thêm nút **ROOT** ảo để gộp các cây vào một cây lớn; khi đó độ sâu mỗi gốc cũ tăng 1 nếu đếm từ ROOT ảo. Đây là cách biểu diễn có thể hữu ích nhưng **làm thay đổi quy ước độ sâu**. Nếu báo cáo yêu cầu gốc thực bằng 0, đừng thêm nút giả mà không điều chỉnh.

## 17. Tính số hậu duệ của một nút

Giả sử cần biết **Hoa (3)** có bao nhiêu cấp dưới ở tất cả các tầng.

Dùng CTE cây con từ Hoa:

~~~sql
WITH RECURSIVE cay_con AS (
    SELECT id, quan_ly_id, 0 AS do_sau
    FROM nhan_vien
    WHERE id = 3

    UNION ALL

    SELECT n.id, n.quan_ly_id, c.do_sau + 1
    FROM nhan_vien n
    JOIN cay_con c ON n.quan_ly_id = c.id
)
SELECT
    COUNT(*) - 1 AS so_hau_due
FROM cay_con;
~~~

Kết quả là **5**, gồm Dũng (6), Hà (7), Trang (8), Mai (9), Quỳnh (12). Trừ 1 vì CTE có cả anchor Hoa.

Nếu nút khởi đầu không tồn tại, COUNT(*) = 0 và **COUNT(*) − 1 = −1**, không có ý nghĩa “−1 hậu duệ”. Vì vậy, công thức này chỉ đúng khi chắc chắn **anchor có đúng một dòng**. Với đầu vào tùy ý, nên lọc bỏ anchor:

~~~sql
SELECT COUNT(*) AS so_hau_due
FROM cay_con
WHERE do_sau > 0;
~~~

Cách này cho 0 cả khi không có nút khởi đầu; nếu cần phân biệt “không tồn tại” với “không có con”, phải kiểm tra sự tồn tại của anchor riêng.

### 17.1. Đếm hậu duệ của mọi nút

Một cách khái niệm là bắt đầu từ **mọi nhân viên** làm điểm gốc cây con, mang theo **ma_diem_bat_dau**:

~~~sql
WITH RECURSIVE quan_he AS (
    SELECT
        id AS ma_diem_bat_dau,
        id AS ma_hau_due,
        0 AS khoang_cach
    FROM nhan_vien

    UNION ALL

    SELECT
        q.ma_diem_bat_dau,
        n.id AS ma_hau_due,
        q.khoang_cach + 1
    FROM quan_he q
    JOIN nhan_vien n
        ON n.quan_ly_id = q.ma_hau_due
)
SELECT
    ma_diem_bat_dau AS id,
    COUNT(*) - 1 AS so_hau_due,
    MAX(khoang_cach) AS chieu_cao
FROM quan_he
GROUP BY ma_diem_bat_dau
ORDER BY id;
~~~

Trên một **rừng hợp lệ**, mỗi cặp tổ tiên–hậu duệ xuất hiện đúng một lần. Câu này tính:

- **so_hau_due**: tổng số hậu duệ của mỗi nút, không kể nó.
- **chieu_cao**: khoảng cách lớn nhất từ nút đến hậu duệ xa nhất.

Ví dụ:

| id | so_hau_due | chieu_cao |
|---:|---:|---:|
| 1 | 9 | 4 |
| 2 | 2 | 1 |
| 3 | 5 | 3 |
| 6 | 3 | 2 |
| 8 | 1 | 1 |
| 12 | 0 | 0 |
| 10 | 1 | 1 |

**Chi phí:** truy vấn từ **mọi nút** có thể sinh số dòng xấp xỉ tổng số cặp tổ tiên–hậu duệ, lớn hơn nhiều so với số nút. Với cây sâu gần như một danh sách liên kết gồm N nút, số dòng trung gian có thể xấp xỉ **N(N+1)/2**. Đừng dùng mẫu này trên bảng rất lớn mà không đánh giá hiệu năng và dữ liệu có chu trình.

## 18. Các phương ngữ SQL và cách viết recursive CTE

Cấu trúc ý tưởng giống nhau, nhưng không phải DBMS nào cũng viết **WITH RECURSIVE**.

### 18.1. PostgreSQL

PostgreSQL hỗ trợ **WITH RECURSIVE**:

~~~sql
WITH RECURSIVE cay AS (
    SELECT id, quan_ly_id, 0 AS do_sau
    FROM nhan_vien
    WHERE quan_ly_id IS NULL

    UNION ALL

    SELECT n.id, n.quan_ly_id, c.do_sau + 1
    FROM nhan_vien n
    JOIN cay c ON n.quan_ly_id = c.id
)
SELECT *
FROM cay;
~~~

Đối với chu trình và thứ tự, PostgreSQL 14+ hỗ trợ **SEARCH**/**CYCLE**; các phiên bản khác có thể cần tự quản lý mảng ID và đường dẫn.

### 18.2. MySQL 8+

MySQL 8.0 có recursive CTE với **WITH RECURSIVE**:

~~~sql
WITH RECURSIVE cay AS (
    SELECT id, quan_ly_id, 0 AS do_sau
    FROM nhan_vien
    WHERE quan_ly_id IS NULL

    UNION ALL

    SELECT n.id, n.quan_ly_id, c.do_sau + 1
    FROM nhan_vien n
    JOIN cay c ON n.quan_ly_id = c.id
)
SELECT *
FROM cay;
~~~

Lưu ý:

- Kiểu cột recursive CTE được suy ra từ **anchor**; với đường dẫn chuỗi, CAST đủ rộng ở anchor.
- MySQL có cấu hình giới hạn số vòng lặp recursive CTE (ví dụ **cte_max_recursion_depth**).
- Một số cấu trúc trong recursive member bị giới hạn hơn các SELECT thông thường; cần kiểm tra tài liệu đúng phiên bản khi kết hợp tổng hợp, DISTINCT hoặc subquery.

### 18.3. SQL Server

SQL Server viết **WITH cay AS** thay vì WITH RECURSIVE:

~~~sql
WITH cay AS (
    SELECT id, quan_ly_id, 0 AS do_sau
    FROM nhan_vien
    WHERE quan_ly_id IS NULL

    UNION ALL

    SELECT n.id, n.quan_ly_id, c.do_sau + 1
    FROM nhan_vien n
    JOIN cay c ON n.quan_ly_id = c.id
)
SELECT id, quan_ly_id, do_sau
FROM cay
OPTION (MAXRECURSION 100);
~~~

Nếu câu lệnh đứng sau một câu lệnh SQL khác trong cùng batch, thường dùng **;WITH** hoặc kết thúc câu lệnh trước bằng dấu chấm phẩy để tránh lỗi cú pháp.

SQL Server có giới hạn mặc định của recursion và cung cấp hint **MAXRECURSION** cho câu SELECT ngoài. Giới hạn này bảo vệ khỏi vòng lặp quá sâu, nhưng không phải cơ chế phát hiện chu trình.

### 18.4. SQLite

SQLite hỗ trợ **WITH RECURSIVE**:

~~~sql
WITH RECURSIVE cay(id, quan_ly_id, do_sau) AS (
    SELECT id, quan_ly_id, 0
    FROM nhan_vien
    WHERE quan_ly_id IS NULL

    UNION ALL

    SELECT n.id, n.quan_ly_id, c.do_sau + 1
    FROM nhan_vien n
    JOIN cay c ON n.quan_ly_id = c.id
)
SELECT *
FROM cay;
~~~

SQLite có những khả năng riêng trong việc điều chỉnh thứ tự xử lý bằng ORDER BY ở recursive member, nhưng cách đó không nên bị nhầm với **ORDER BY đầu ra** chung của các DBMS. Để viết đa hệ, hãy giữ điều kiện kết thúc/chu trình rõ ràng và sắp xếp kết quả cuối tường minh.

### 18.5. Oracle Database: recursive subquery factoring

Oracle Database phổ biến như 19c dùng **WITH ten_cte (...) AS (...)**, **không viết từ khóa RECURSIVE** như PostgreSQL/MySQL.

~~~sql
WITH cay (id, quan_ly_id, do_sau, ma_goc) AS (
    SELECT
        id,
        quan_ly_id,
        0 AS do_sau,
        id AS ma_goc
    FROM nhan_vien
    WHERE quan_ly_id IS NULL

    UNION ALL

    SELECT
        n.id,
        n.quan_ly_id,
        c.do_sau + 1,
        c.ma_goc
    FROM nhan_vien n
    JOIN cay c
        ON n.quan_ly_id = c.id
)
SELECT id, quan_ly_id, do_sau, ma_goc
FROM cay
ORDER BY ma_goc, do_sau, id;
~~~

Ở Oracle, danh sách tên cột sau tên CTE có vai trò quan trọng trong recursive subquery factoring. Các quy tắc về thứ tự SELECT, kiểu dữ liệu và giới hạn nội dung recursive member cũng cần tuân thủ. Oracle còn có tính năng phân cấp riêng **CONNECT BY**, trình bày dưới đây.

### 18.6. Bảng so sánh ngắn

| DBMS | Khởi đầu CTE | Điểm cần chú ý |
|---|---|---|
| PostgreSQL | WITH RECURSIVE | Mảng ID, SEARCH/CYCLE ở phiên bản hỗ trợ |
| MySQL 8+ | WITH RECURSIVE | Kiểu từ anchor, giới hạn recursion của server |
| SQL Server | WITH ten_cte AS | Không có từ khóa RECURSIVE, MAXRECURSION |
| SQLite | WITH RECURSIVE | Cú pháp recursive CTE, kiểu linh hoạt |
| Oracle Database | WITH ten_cte(col,...) AS | Recursive subquery factoring; CONNECT BY riêng |

Không nên đổi cú pháp bằng cách chỉ thay tên DBMS trong tài liệu. Các ràng buộc kiểu dữ liệu và phạm vi biểu thức trong recursive member có thể khiến cùng một ý tưởng cần câu SQL khác nhau.

## 19. Oracle CONNECT BY: một cách khác để duyệt phân cấp

Oracle Database có cú pháp **hierarchical query** với **START WITH ... CONNECT BY**:

~~~sql
SELECT
    id,
    ho_ten,
    quan_ly_id,
    LEVEL - 1 AS do_sau,
    CONNECT_BY_ROOT id AS ma_goc,
    SYS_CONNECT_BY_PATH(ho_ten, ' > ') AS duong_dan
FROM nhan_vien
START WITH quan_ly_id IS NULL
CONNECT BY NOCYCLE PRIOR id = quan_ly_id;
~~~

Giải thích:

- **START WITH quan_ly_id IS NULL**: chọn nút bắt đầu.
- **CONNECT BY PRIOR id = quan_ly_id**: tìm nút con có parent bằng id nút cha đang xét.
- **LEVEL**: trong Oracle, gốc có LEVEL = 1, nên **LEVEL − 1** cho độ sâu gốc 0.
- **CONNECT_BY_ROOT id**: lấy mã gốc của đường đi.
- **SYS_CONNECT_BY_PATH**: tạo chuỗi đường đi theo cột tên.
- **NOCYCLE**: cho phép truy vấn xử lý dữ liệu có vòng mà không phát sinh lỗi vòng theo cách thông thường; có thể dùng thêm **CONNECT_BY_ISCYCLE** để kiểm tra trường hợp tạo vòng, tùy câu truy vấn.

Cú pháp CONNECT BY **không phải SQL chuẩn phổ quát**; phù hợp khi hệ thống dùng Oracle và tận dụng các tính năng phân cấp riêng.

### 19.1. Tìm con của Hoa theo CONNECT BY

~~~sql
SELECT
    id,
    ho_ten,
    LEVEL - 1 AS do_sau_tuong_doi
FROM nhan_vien
START WITH id = 3
CONNECT BY NOCYCLE PRIOR id = quan_ly_id;
~~~

Kết quả gồm Hoa ở depth 0 rồi các hậu duệ 6, 7, 8, 9, 12 theo tầng tương đối. Nếu cần thứ tự **anh chị em**, Oracle hỗ trợ **ORDER SIBLINGS BY** trong hierarchical query.

### 19.2. Đừng nhầm chiều PRIOR

~~~sql
CONNECT BY PRIOR id = quan_ly_id
~~~

và:

~~~sql
CONNECT BY PRIOR quan_ly_id = id
~~~

đi theo hai hướng quan hệ khác nhau. Khi duyệt gốc xuống con, cần vế PRIOR đại diện **id của nút cha**, vế còn lại là **mã quản lý của ứng viên con**.

## 20. Quy tắc anchor và recursive member cần nhất quán

Trong recursive CTE, hai SELECT được nối bằng UNION ALL phải trả:

- **Cùng số cột**.
- Các cột ở **cùng thứ tự**.
- Kiểu dữ liệu tương ứng phù hợp với yêu cầu DBMS.
- Giá trị có cùng ý nghĩa ở mỗi vị trí.

Ví dụ đúng:

~~~sql
-- Anchor:
SELECT id, quan_ly_id, 0 AS do_sau

UNION ALL

-- Recursive member:
SELECT n.id, n.quan_ly_id, c.do_sau + 1
~~~

Ví dụ sai ý nghĩa:

~~~sql
-- Anchor đặt (id, quan_ly_id, do_sau).
SELECT id, quan_ly_id, 0

UNION ALL

-- Recursive member nhầm thứ tự cột.
SELECT n.quan_ly_id, n.id, c.do_sau + 1
~~~

Nếu id và quan_ly_id đều là INTEGER, DBMS có thể không báo lỗi kiểu dữ liệu, nhưng giá trị **id** trong CTE sẽ bị đặt bằng quan_ly_id, làm đệ quy sai.

### 20.1. Không làm thay đổi định danh nút trong recursive member

Trong truy vấn duyệt cây, **id** của CTE cần là ID của **nút đang xét** ở từng bước, để lần tiếp theo tìm con bằng:

~~~sql
n.quan_ly_id = c.id
~~~

Nếu lỡ giữ mã gốc trong cột id, recursive member có thể liên tục tìm lại con của gốc hoặc dừng sai. Hãy tách cột:

- **id**: nút hiện tại.
- **ma_goc**: gốc của đường đi.
- **do_sau**: số cạnh từ anchor.
- **duong_dan**: danh sách/chuỗi các nút đã qua.

## 21. Tại sao dùng UNION ALL thay cho UNION?

Trong một cây được xác định đúng, từ mỗi gốc tới mỗi nút có **một đường duy nhất**. Vì vậy, recursive member không cần loại trùng đường đi; dùng **UNION ALL** phản ánh ngữ nghĩa tự nhiên.

**UNION** có thể tạo thao tác loại trùng trên các hàng của CTE, làm chi phí tăng và có thể che dữ liệu trùng. Quan trọng hơn, như phần chu trình đã nêu, UNION **không chắc dừng được vòng** khi có depth/path thay đổi.

Chỉ dùng UNION khi **loại trùng toàn bộ hàng** là một phần có chủ đích của thuật toán và đã phân tích tính kết thúc. Đừng dùng nó như cách thay thế kiểm tra **chu trình theo ID**.

### 21.1. Khi có nhiều đường đi tới cùng một nút

Nếu dữ liệu không phải cây một-cha mà là **đồ thị có hướng** hoặc một DAG (mỗi nút có thể có nhiều cha), một nút có thể xuất hiện nhiều lần trong truy vấn từ gốc vì có nhiều đường khác nhau.

Ví dụ:

~~~text
A -> B -> D
 \-> C -> D
~~~

D có hai đường từ A. Với recursive CTE mang **do_sau** hoặc path, D có thể xuất hiện hai lần, mỗi lần gắn với một đường. Đây có thể là kết quả đúng nếu yêu cầu là **liệt kê đường đi**.

Nếu yêu cầu là **danh sách nút duy nhất có thể tới**, phải loại trùng **theo ID** sau khi xác định chính sách với độ sâu (ngắn nhất, dài nhất hay một đường bất kỳ). Không thể chỉ SELECT DISTINCT id, do_sau rồi mong luôn có một dòng cho D nếu hai đường khác độ sâu.

## 22. Cây, DAG và đồ thị có chu trình: không phải một bài toán

| Mô hình | Quan hệ cha | Có chu trình? | Độ sâu có duy nhất? |
|---|---|---|---|
| **Cây** | Mỗi nút không gốc có một cha | Không | Có, từ một gốc xác định |
| **Rừng** | Nhiều cây riêng | Không | Có, tính trong từng cây |
| **DAG** | Một nút có thể có nhiều cha | Không | Có thể có nhiều khoảng cách đường đi |
| **Đồ thị có hướng tổng quát** | Có thể nhiều cha | Có thể | Cần xác định quy tắc và chống vòng |

Ví dụ D có hai đường từ A:

~~~text
A -> B -> D       độ dài 2 cạnh
A -> C -> E -> D  độ dài 3 cạnh
~~~

Nếu hỏi **“độ sâu của D”** trong DAG, có ít nhất hai định nghĩa có thể dùng:

- **Khoảng cách ngắn nhất** từ A đến D: 2.
- **Khoảng cách dài nhất** từ A đến D: 3.

Trong cây, hai giá trị trùng nhau vì chỉ có một đường. Khi thiết kế dữ liệu cho một nút có nhiều cha, phải chọn cách hiểu độ sâu trước khi viết MAX/MIN. Không nên gọi kết quả từ một đường bất kỳ là “độ sâu duy nhất” nếu dữ liệu thực sự là DAG.

## 23. Truy vấn đệ quy có thể bị nhân dòng do khóa trùng

Trong ví dụ chuẩn, **id** là PRIMARY KEY nên mỗi ID chỉ có một dòng. Nhưng một bảng staging chưa kiểm tra khóa có thể có:

~~~text
id | quan_ly_id
---+-----------
1  | NULL
2  | 1
2  | 1
3  | 2
~~~

Khi từ 1 tìm con, sẽ thấy **hai dòng id=2**. Ở tầng tiếp theo, mỗi dòng 2 lại tìm được id=3, khiến **id=3 có thể xuất hiện hai lần** dù bảng chỉ có một dòng id=3.

Nếu tiếp tục nhiều cấp, số đường lặp có thể tăng mạnh, làm:

- **COUNT(*)** trong CTE cao hơn số nhân viên thật.
- Kết quả độ sâu có nhiều dòng cùng ID.
- Tính chi phí lớn không cần thiết.
- Phát hiện chu trình bằng tên/giá trị không đúng định danh.

**Giải pháp nền tảng:** bảo đảm **id duy nhất** ở bảng nguồn bằng PRIMARY KEY/UNIQUE, và kiểm tra staging trước khi duyệt.

Truy vấn kiểm tra trùng ID:

~~~sql
SELECT id, COUNT(*) AS so_lan
FROM nhan_vien_nhap
GROUP BY id
HAVING COUNT(*) > 1;
~~~

**Lưu ý:** trong bảng nhan_vien chuẩn có PRIMARY KEY, ID trùng không thể được lưu khi ràng buộc được thực thi. Ví dụ này dành cho bảng nhập liệu chưa kiểm soát.

## 24. Kiểm tra chất lượng cấu trúc trước khi tính depth

Để duyệt được một rừng hợp lệ, cần có:

1. **ID duy nhất**.
2. **Parent ID NULL** đúng nghĩa gốc hoặc tham chiếu tới ID có thật.
3. Không có nút tự làm cha, nếu mô hình không cho phép.
4. Không có chu trình dài hơn một cạnh.
5. Mỗi nút con có đúng một cha theo lược đồ.
6. Các cây/gốc hợp lệ theo chính sách nghiệp vụ.
7. Giới hạn độ sâu phù hợp nếu hệ thống đặt ngưỡng.

### 24.1. Nút tự làm cha

~~~sql
SELECT id, ho_ten
FROM nhan_vien
WHERE quan_ly_id = id;
~~~

Nếu id = 20 và quan_ly_id = 20, đệ quy từ id 20 sẽ tự quay lại id 20. Ràng buộc CHECK đơn giản có thể ngăn trường hợp một-cạnh:

~~~sql
CONSTRAINT ck_khong_tu_quan_ly
CHECK (quan_ly_id IS NULL OR quan_ly_id <> id)
~~~

Nhưng CHECK này **không chặn chu trình nhiều nút**. Tính hỗ trợ CHECK và cách thực thi cần được xác nhận theo phiên bản DBMS.

### 24.2. Parent ID không tồn tại

~~~sql
SELECT n.id, n.quan_ly_id
FROM nhan_vien n
WHERE n.quan_ly_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM nhan_vien cha
      WHERE cha.id = n.quan_ly_id
  );
~~~

Truy vấn cho biết orphan. Nếu FOREIGN KEY đang được thực thi, trường hợp này bình thường không thể có; nhưng vẫn hữu ích để kiểm tra staging hoặc dữ liệu di trú.

### 24.3. Nút không thể đi đến từ gốc

Dùng CTE từ gốc như phần 15.2 rồi lấy **nhan_vien EXCEPT tập ID đã duyệt** hoặc NOT EXISTS. Không thể tới từ gốc có thể do orphan, hậu duệ của orphan hoặc thành phần chu trình. Cần điều tra tiếp, không tự “sửa” bằng cách gán parent_id NULL tất cả.

### 24.4. Độ sâu vượt chính sách

Giả sử một doanh nghiệp cho phép tối đa 6 tầng:

~~~sql
WITH RECURSIVE cay AS (
    SELECT id, quan_ly_id, 0 AS do_sau
    FROM nhan_vien
    WHERE quan_ly_id IS NULL

    UNION ALL

    SELECT n.id, n.quan_ly_id, c.do_sau + 1
    FROM nhan_vien n
    JOIN cay c ON n.quan_ly_id = c.id
    WHERE c.do_sau < 100
)
SELECT id, do_sau
FROM cay
WHERE do_sau > 6;
~~~

Giới hạn kỹ thuật 100 giúp bảo vệ tài nguyên ở mức minh họa; nhưng báo cáo này **không xác minh** những nút sâu hơn 100 có tồn tại hay không. Một kiểm tra toàn vẹn hoàn chỉnh cần xác định dữ liệu có chu trình và cách bảo đảm đã duyệt đủ cây, thay vì chỉ giới hạn rồi kết luận “không có nút quá sâu”.

## 25. Cập nhật cha: độ sâu và đường dẫn của hậu duệ thay đổi

Giả sử chuyển **Dũng (6)** từ quản lý Hoa (3) sang Minh (2):

~~~text
Trước:
Lan -> Hoa -> Dũng -> Trang -> Quỳnh

Sau:
Lan -> Minh -> Dũng -> Trang -> Quỳnh
~~~

Trong ví dụ này, **độ sâu từ Lan không đổi** vì Minh và Hoa đều đang ở depth 1. Nhưng nếu chuyển Dũng lên trực tiếp dưới Lan:

~~~text
Lan -> Dũng -> Trang -> Quỳnh
~~~

thì độ sâu của Dũng và toàn bộ hậu duệ giảm 1, và đường dẫn thay đổi.

### 25.1. Không chỉ cập nhật một dòng khi có dữ liệu suy diễn

Ở adjacency list thuần túy, ta thường chỉ cập nhật **quan_ly_id** của nút được chuyển. Recursive CTE sẽ tính lại depth/path từ dữ liệu hiện hành.

Nếu hệ thống còn lưu **depth/path/closure table** đã tính sẵn, việc đổi cha có thể yêu cầu cập nhật **toàn bộ hậu duệ** hoặc tái tính chỉ mục/closure tương ứng, để tránh dữ liệu suy diễn bị lỗi thời.

### 25.2. Ngăn chuyển cha tạo vòng

Ví dụ không hợp lệ: đặt **quan_ly_id của Lan (1) = 12**, tức Lan làm con của Quỳnh trong khi Quỳnh vốn là hậu duệ Lan. Thao tác sẽ tạo chu trình:

~~~text
Lan -> Hoa -> Dũng -> Trang -> Quỳnh -> Lan
~~~

FOREIGN KEY vẫn có thể chấp nhận mã 12 vì nhân viên 12 có thật. Vì vậy, trước khi chuyển nút X dưới cha mới Y, cần kiểm tra **Y không phải X và không nằm trong cây con của X**.

Một hướng giải quyết:

1. Duyệt toàn bộ hậu duệ của X, có chống chu trình.
2. Nếu Y nằm trong tập này hoặc Y = X, từ chối thao tác.
3. Thực hiện kiểm tra và cập nhật trong một chiến lược giao dịch/khóa bảo đảm an toàn khi có yêu cầu đồng thời.

Chỉ SELECT kiểm tra rồi UPDATE trong hai giao dịch không đồng bộ có thể gặp điều kiện chạy đua. Cơ chế khóa, trigger hoặc xử lý tại tầng nghiệp vụ cần thiết kế phù hợp với DBMS và tính nhất quán mong muốn.

## 26. Hiệu năng của truy vấn đệ quy

Recursive CTE hữu ích, nhưng hiệu năng phụ thuộc vào kích thước cây, độ sâu và cách tìm con ở mỗi bước.

### 26.1. Chỉ mục trên parent_id

Để tìm con:

~~~sql
ON n.quan_ly_id = c.id
~~~

DBMS cần tra cứu những dòng có **quan_ly_id** bằng id của nút cha. Một chỉ mục thường hữu ích:

~~~sql
CREATE INDEX idx_nhan_vien_quan_ly_id
ON nhan_vien (quan_ly_id);
~~~

Khóa chính **id** thường được DBMS hỗ trợ bởi cấu trúc truy cập thích hợp, nhưng không nên giả định FOREIGN KEY tự động tạo chỉ mục ở **quan_ly_id** trên mọi hệ.

### 26.2. Phân biệt độ rộng cây với độ sâu

- **Cây rộng:** nhiều con trực tiếp, có thể sinh hàng nghìn hoặc hàng triệu dòng ở một vài tầng.
- **Cây sâu:** chuỗi cha–con dài, số vòng recursive CTE lớn và đường dẫn có thể rất dài.
- **Rừng nhiều gốc:** anchor có nhiều dòng; mỗi cây mở rộng độc lập về ngữ nghĩa.

Một truy vấn có depth tối đa nhỏ vẫn có thể tạo **rất nhiều dòng** nếu cây rộng. Giới hạn độ sâu không đồng nghĩa giới hạn tổng số dòng.

### 26.3. Không mang quá nhiều cột theo từng vòng

Thành phần recursive member lặp lại nhiều lần. Nếu mỗi dòng CTE chứa văn bản rất dài, JSON lớn hoặc toàn bộ thông tin nhân viên, chi phí bộ nhớ/tạm có thể tăng.

Một mẫu thường hiệu quả hơn là chỉ mang:

~~~text
id, quan_ly_id, ma_goc, do_sau
~~~

rồi JOIN bảng nhan_vien để lấy ho_ten và các cột hiển thị ở truy vấn cuối.

Ví dụ:

~~~sql
WITH RECURSIVE cay AS (
    SELECT id, quan_ly_id, id AS ma_goc, 0 AS do_sau
    FROM nhan_vien
    WHERE quan_ly_id IS NULL

    UNION ALL

    SELECT n.id, n.quan_ly_id, c.ma_goc, c.do_sau + 1
    FROM nhan_vien n
    JOIN cay c ON n.quan_ly_id = c.id
)
SELECT
    c.id,
    n.ho_ten,
    c.ma_goc,
    c.do_sau
FROM cay c
JOIN nhan_vien n ON n.id = c.id;
~~~

Điều này đặc biệt hữu ích khi cây lớn; nhưng không phải quy tắc bắt buộc, và cần đo hiệu năng trên dữ liệu thực.

### 26.4. Đếm mọi quan hệ tổ tiên–hậu duệ có thể tốn nhiều

Truy vấn bắt đầu từ **mọi nút** (phần 17.1) có thể có số dòng trung gian **O(N²)** đối với một chuỗi dài N nút. Nếu cần truy vấn hậu duệ/tổ tiên rất thường xuyên trong hệ thống cực lớn, có thể cân nhắc cấu trúc lưu trữ chuyên dụng như **closure table**, **materialized path** hoặc công cụ xử lý đồ thị, thay vì chạy lại tất cả đường đi liên tục.

### 26.5. Kế hoạch và thống kê

Hãy dùng công cụ của DBMS:

- PostgreSQL: EXPLAIN/EXPLAIN ANALYZE.
- MySQL: EXPLAIN và các công cụ theo phiên bản.
- SQL Server: actual execution plan.
- Oracle: DBMS_XPLAN hoặc công cụ kế hoạch tương ứng.
- SQLite: EXPLAIN QUERY PLAN.

Không kết luận recursive CTE luôn nhanh hay luôn chậm hơn các cách lưu cây khác. Đánh giá theo **số nút, độ sâu, tần suất cập nhật cha, truy vấn cần lấy và chỉ mục**.

## 27. Các mô hình lưu cây khác

### 27.1. Adjacency list

Lưu:

~~~text
id | parent_id
~~~

Ưu điểm:

- Đơn giản, trực quan.
- Dễ cập nhật một quan hệ cha.
- Hợp với FOREIGN KEY tự tham chiếu.

Nhược điểm:

- Lấy mọi tổ tiên/hậu duệ cần recursive query.
- Tính toán path/depth nhiều lần có thể tốn chi phí.
- Cần kiểm tra chu trình khi đổi cha.

### 27.2. Materialized path

Mỗi nút lưu một đường dẫn, ví dụ:

~~~text
/1/3/6/8/
~~~

Lấy hậu duệ có thể dựa vào tiền tố đường dẫn, nhưng cần thiết kế cách mã hóa/escape, index và cập nhật nhiều dòng khi chuyển nhánh. Không được coi tên người là khóa đường dẫn nếu có thể đổi tên hoặc trùng.

### 27.3. Closure table

Lưu cặp **(ancestor_id, descendant_id, distance)**:

| ancestor_id | descendant_id | distance |
|---:|---:|---:|
| 1 | 1 | 0 |
| 1 | 3 | 1 |
| 1 | 6 | 2 |
| 1 | 8 | 3 |
| 1 | 12 | 4 |
| 3 | 12 | 3 |

Lấy toàn bộ hậu duệ hoặc độ sâu tương đối có thể dùng JOIN/lọc trên bảng closure. Đổi cha đòi hỏi duy trì nhiều cặp quan hệ, phức tạp hơn adjacency list.

### 27.4. Nested sets

Lưu **left/right bounds** cho mỗi nút; lấy cây con có thể dựa vào khoảng, nhưng cập nhật cấu trúc có thể tốn kém. Thường phù hợp hơn khi cây ít thay đổi và đọc nhiều.

### 27.5. Chọn mô hình theo mục đích

| Nhu cầu | Gợi ý |
|---|---|
| Dữ liệu phân cấp vừa phải, thường thay đổi cha | Adjacency list + recursive CTE |
| Truy vấn tổ tiên/hậu duệ rất nhiều, đọc nặng | Cân nhắc closure table/materialized path |
| Chỉ cần con trực tiếp | Adjacency list + JOIN/WHERE đơn giản |
| Cây sâu, báo cáo path nhiều lần | Cân nhắc cache hoặc materialized path có đồng bộ |
| Đồ thị nhiều cha/nhiều loại cạnh | Mô hình graph/edge table rõ ràng |

Không nên chuyển mô hình lưu trữ chỉ vì viết recursive CTE trông dài. Trước hết xác định yêu cầu nghiệp vụ, tần suất truy vấn và chi phí cập nhật dữ liệu.

## 28. Dùng recursive CTE trong Java/JDBC

Giả sử ứng dụng cần hiển thị các nhân viên dưới **một quản lý được chọn**. Hãy **tham số hóa id** thay vì ghép trực tiếp vào chuỗi SQL.

Ví dụ dành cho DBMS hỗ trợ cú pháp **WITH RECURSIVE**:

~~~java
String sql = """
    WITH RECURSIVE cay_con AS (
        SELECT
            id,
            ho_ten,
            quan_ly_id,
            0 AS do_sau
        FROM nhan_vien
        WHERE id = ?

        UNION ALL

        SELECT
            n.id,
            n.ho_ten,
            n.quan_ly_id,
            c.do_sau + 1
        FROM nhan_vien n
        JOIN cay_con c ON n.quan_ly_id = c.id
        WHERE c.do_sau < ?
    )
    SELECT id, ho_ten, do_sau
    FROM cay_con
    WHERE do_sau > 0
    ORDER BY do_sau, id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, 3);    // quản lý Hoa
    ps.setInt(2, 20);   // giới hạn kỹ thuật số tầng

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            int id = rs.getInt("id");
            String ten = rs.getString("ho_ten");
            int doSau = rs.getInt("do_sau");
            System.out.println(id + " | " + ten + " | " + doSau);
        }
    }
}
~~~

Kết quả từ Hoa là cấp dưới **6, 7, 8, 9, 12** với độ sâu tương đối tương ứng.

**PreparedStatement** giúp truyền tham số đúng kiểu và tránh ghép SQL từ dữ liệu người dùng. Tuy nhiên:

- Tham số **giới hạn tầng** không thay thế **phát hiện chu trình**.
- Nếu muốn giữ cả quản lý được chọn, bỏ **WHERE do_sau > 0**.
- Nếu DBMS là SQL Server/Oracle, phải điều chỉnh cú pháp CTE, không dùng nguyên văn từ khóa RECURSIVE.
- Nếu mã quản lý không tồn tại, kết quả sẽ rỗng; ứng dụng có thể cần báo “không tìm thấy” thay vì “không có cấp dưới”.
- Nếu cây rất lớn, cần giới hạn số dòng hoặc phân trang/trình bày theo từng cấp phù hợp, không mặc định tải toàn bộ vào giao diện.

## 29. Các lỗi thường gặp

| Lỗi | Vì sao xảy ra | Cách xử lý |
|---|---|---|
| Nhầm hướng JOIN | Đang đi ngược lên cha thay vì xuống con | Đi xuống: n.parent_id = c.id |
| Anchor sai | Chọn mọi nút thay vì chọn gốc hoặc nút chỉ định | Xác định rõ điểm bắt đầu |
| Gốc depth = 1 nhưng báo cáo coi gốc 0 | Lệch một cấp | Quy định depth/level thống nhất |
| Chỉ dùng JOIN một/hai lần | Bỏ sót cây sâu hơn | Recursive CTE |
| Giới hạn depth ở SELECT ngoài rồi tưởng dừng lặp | CTE có thể vẫn mở rộng sâu | Đặt giới hạn trong recursive member |
| Tưởng LIMIT hay ORDER BY ngoài cùng chống vòng | Có thể vẫn lặp hoặc tiêu tốn tài nguyên | Theo dõi ID đã thăm, giới hạn kỹ thuật |
| Đổi UNION ALL thành UNION để chống chu trình | Depth/path đổi nên dòng không trùng | Chống chu trình theo khóa trên từng đường |
| Dùng tên để nhận biết chu trình | Tên trùng/đổi, không phải ID | Theo dõi khóa định danh |
| Tạo path chuỗi trong MySQL từ kiểu ngắn | Chuỗi dài vượt kiểu anchor | CAST đủ rộng, kiểm soát độ dài |
| Tưởng ORDER BY depth là thứ tự DFS | Depth sắp theo tầng | Xây path key hoặc SEARCH |
| Tưởng recursive CTE trả đúng thứ tự chạy | SQL không bảo đảm thứ tự không ORDER BY | Sắp xếp cuối cùng |
| Không xử lý nhiều gốc | Nhầm forest thành một cây | Mang ma_goc, nhóm theo root |
| Chỉ bắt đầu từ gốc và kết luận dữ liệu sạch | Orphan/chu trình có thể bị bỏ sót | Kiểm tra unreachable nodes |
| Tưởng FOREIGN KEY ngăn mọi chu trình | FK kiểm tra tồn tại cha, không ngăn vòng nhiều nút | Kiểm tra thay đổi cha và chống vòng |
| Đếm COUNT(*)−1 khi anchor rỗng | Có thể ra −1 | Lọc do_sau > 0, kiểm tra tồn tại |
| Nhầm depth toàn cục với khoảng cách từ anchor | Cùng nút có hai con số khác | Đặt tên do_sau_tuong_doi/khoang_cach |
| Nhầm chiều cao với độ sâu | Hai đại lượng khác nhau | Xác định từ gốc hay xuống lá |
| Nhóm theo tên thay vì ID | Nút trùng tên bị gộp | Dùng định danh duy nhất |
| Parent_id không có index | Mỗi vòng tìm con có thể đắt | Xem xét index trên parent_id |
| Nhiều nguồn con/khóa trùng | Nhân số dòng, COUNT sai | Bảo đảm tính duy nhất, phân tích grain |
| Mang cột lớn theo mọi vòng | Tăng bộ nhớ/IO | Chỉ mang ID, parent, root, depth cần thiết |
| Truy vấn mọi cặp tổ tiên–hậu duệ trên cây lớn | Có thể sinh O(N²) dòng | Xem xét closure table/cache |
| Chuyển nhánh mà không kiểm tra hậu duệ | Tạo chu trình | Kiểm tra Y không thuộc subtree của X |
| Dùng WITH RECURSIVE trên SQL Server/Oracle | Sai cú pháp | Dùng WITH CTE theo phương ngữ |
| SQL Server hết MAXRECURSION | Có thể là cây sâu hoặc dữ liệu vòng | Xác minh dữ liệu, đặt giới hạn phù hợp |
| Tưởng cắt ở depth N chứng minh không có nút sâu hơn | Kết quả bị cắt | Theo dõi trạng thái bị cắt/kiểm tra đầy đủ |

## 30. Bài tập thực hành

Bài tập sử dụng bộ dữ liệu **nhan_vien** ở phần 2, trừ khi ghi rõ giả định khác. Các đáp án minh họa chủ yếu dùng **WITH RECURSIVE**; khi dùng SQL Server/Oracle cần đổi cú pháp theo phần phương ngữ.

### Bài 1 — Xác định gốc

Trong bảng mẫu, những nhân viên nào là gốc của các cây? Viết SQL tìm họ.

<details>
<summary>Đáp án gợi ý</summary>

**Lan (1)** và **Linh (10)**.

~~~sql
SELECT id, ho_ten
FROM nhan_vien
WHERE quan_ly_id IS NULL;
~~~

</details>

### Bài 2 — Con trực tiếp khác hậu duệ

Ai là **con trực tiếp** của Hoa (3), và ai là **toàn bộ hậu duệ** của Hoa?

<details>
<summary>Đáp án gợi ý</summary>

Con trực tiếp: **Dũng (6), Hà (7)**.

Toàn bộ hậu duệ: **Dũng (6), Hà (7), Trang (8), Mai (9), Quỳnh (12)**.

Lấy con trực tiếp chỉ cần WHERE quan_ly_id = 3. Lấy toàn bộ hậu duệ cần recursive CTE hoặc mô hình đã lưu sẵn quan hệ tổ tiên–hậu duệ.

</details>

### Bài 3 — Độ sâu của một nút

Cho gốc có depth = 0. Tính độ sâu từ Lan của Minh, Dũng, Trang, Quỳnh.

<details>
<summary>Đáp án gợi ý</summary>

- Minh (2): **1**.
- Dũng (6): **2**.
- Trang (8): **3**.
- Quỳnh (12): **4**.

Đếm số cạnh trên đường từ gốc Lan đến từng nút.

</details>

### Bài 4 — Viết recursive CTE từ gốc

Viết truy vấn lấy toàn bộ nhân viên của rừng, gồm id, ma_goc và do_sau.

<details>
<summary>Đáp án gợi ý</summary>

~~~sql
WITH RECURSIVE cay AS (
    SELECT id, quan_ly_id, id AS ma_goc, 0 AS do_sau
    FROM nhan_vien
    WHERE quan_ly_id IS NULL

    UNION ALL

    SELECT n.id, n.quan_ly_id, c.ma_goc, c.do_sau + 1
    FROM nhan_vien n
    JOIN cay c ON n.quan_ly_id = c.id
)
SELECT id, ma_goc, do_sau
FROM cay
ORDER BY ma_goc, do_sau, id;
~~~

</details>

### Bài 5 — Một cây con

Viết truy vấn lấy **mọi nhân viên dưới Minh (2)**, không lấy Minh, và có khoảng cách tương đối.

<details>
<summary>Đáp án gợi ý</summary>

~~~sql
WITH RECURSIVE cay_con AS (
    SELECT id, quan_ly_id, 0 AS khoang_cach
    FROM nhan_vien
    WHERE id = 2

    UNION ALL

    SELECT n.id, n.quan_ly_id, c.khoang_cach + 1
    FROM nhan_vien n
    JOIN cay_con c ON n.quan_ly_id = c.id
)
SELECT id, khoang_cach
FROM cay_con
WHERE khoang_cach > 0;
~~~

Kết quả: Bình (4) và An (5), mỗi người cách Minh một cạnh.

</details>

### Bài 6 — Duyệt ngược

Từ Quỳnh (12), các tổ tiên lần lượt là ai, theo khoảng cách tăng dần?

<details>
<summary>Đáp án gợi ý</summary>

**Trang (8)**, **Dũng (6)**, **Hoa (3)**, **Lan (1)** với khoảng cách 1, 2, 3, 4.

Duyệt từ 12 bằng điều kiện tìm cha **cha.id = c.quan_ly_id**.

</details>

### Bài 7 — Độ sâu tối đa

Cây Lan và cây Linh có độ sâu tối đa bằng bao nhiêu?

<details>
<summary>Đáp án gợi ý</summary>

- Cây Lan: **4**.
- Cây Linh: **1**.

Dùng MAX(do_sau) GROUP BY ma_goc từ recursive CTE của toàn rừng.

</details>

### Bài 8 — Thống kê theo tầng

Cây Lan có bao nhiêu nhân viên ở các tầng 0, 1, 2, 3, 4?

<details>
<summary>Đáp án gợi ý</summary>

Lần lượt **1, 2, 4, 2, 1**. Dùng COUNT(*) GROUP BY do_sau và ma_goc = 1 trên CTE.

</details>

### Bài 9 — Nút lá

Nhân viên nào là lá trong tập mẫu? Viết điều kiện SQL.

<details>
<summary>Đáp án gợi ý</summary>

**Bình (4), An (5), Hà (7), Mai (9), Tâm (11), Quỳnh (12)**.

~~~sql
SELECT n.id, n.ho_ten
FROM nhan_vien n
WHERE NOT EXISTS (
    SELECT 1
    FROM nhan_vien c
    WHERE c.quan_ly_id = n.id
);
~~~

</details>

### Bài 10 — Cắt ở tầng 2

Trong recursive member, nếu viết **WHERE c.do_sau < 2** và anchor depth = 0, độ sâu lớn nhất có thể xuất hiện ở kết quả là bao nhiêu?

<details>
<summary>Đáp án gợi ý</summary>

**2**. Những nút ở depth 1 có thể sinh con depth 2; nhưng nút depth 2 không được sinh con depth 3.

</details>

### Bài 11 — Đường dẫn tên

Tạo một chuỗi đường đi từ Lan tới Quỳnh. Kết quả mong đợi là gì?

<details>
<summary>Đáp án gợi ý</summary>

~~~text
Lan > Hoa > Dũng > Trang > Quỳnh
~~~

Trong PostgreSQL có thể nối **c.duong_dan || ' > ' || n.ho_ten**; trong MySQL dùng CONCAT; SQL Server dùng + và cần chú ý kiểu/độ rộng chuỗi.

</details>

### Bài 12 — Phát hiện chu trình hai nút

Giả sử có bản ghi 20 → 21 và 21 → 20 theo quan hệ parent. Vì sao UNION thay UNION ALL chưa chắc ngăn truy vấn lặp khi CTE có cột do_sau?

<details>
<summary>Đáp án gợi ý</summary>

Vì các dòng như **(20,0), (21,1), (20,2), (21,3)** khác nhau ở do_sau. UNION chỉ loại dòng giống nhau trên **mọi cột**, nên không loại được ID lặp nếu depth thay đổi. Cần theo dõi ID đã xuất hiện trên đường đi hoặc dùng CYCLE nếu DBMS hỗ trợ.

</details>

### Bài 13 — Orphan

Một nhân viên có id = 30, quan_ly_id = 999 nhưng không có nhân viên 999. Dòng này có thuộc kết quả truy vấn bắt đầu từ các gốc parent NULL không?

<details>
<summary>Đáp án gợi ý</summary>

Thông thường **không**. Dòng 30 không phải gốc và không thể được tìm như con của một nút 999 trong bảng. Đây là **orphan**, cần kiểm tra bằng NOT EXISTS hoặc LEFT JOIN tới bảng cha.

</details>

### Bài 14 — FOREIGN KEY và vòng lặp

FOREIGN KEY (quan_ly_id) REFERENCES nhan_vien(id) có đảm bảo không tồn tại chu trình 20 ↔ 21 không?

<details>
<summary>Đáp án gợi ý</summary>

**Không.** FK kiểm tra tham chiếu cha có tồn tại, không bảo đảm cấu trúc không có vòng nhiều nút. Cần kiểm tra chu trình khi thay đổi cha, có cơ chế giao dịch phù hợp.

</details>

### Bài 15 — Phương ngữ

Với cùng ý tưởng recursive CTE, SQL Server và Oracle có dùng từ khóa **WITH RECURSIVE** như PostgreSQL không?

<details>
<summary>Đáp án gợi ý</summary>

**Không.** SQL Server dùng **WITH cte AS (...)**, có thể kèm OPTION (MAXRECURSION ...). Oracle dùng recursive subquery factoring với **WITH cte(col,...) AS (...)**, hoặc tính năng **START WITH ... CONNECT BY**.

</details>

### Bài 16 — Tính số hậu duệ

Hoa (3) có bao nhiêu hậu duệ và chiều cao cây con bằng bao nhiêu nếu số cạnh từ Hoa tới lá xa nhất được dùng làm chiều cao?

<details>
<summary>Đáp án gợi ý</summary>

Hoa có **5 hậu duệ**: 6, 7, 8, 9, 12. Chiều cao là **3** cạnh qua đường Hoa → Dũng → Trang → Quỳnh.

</details>

### Bài 17 — Nút không tồn tại

Truy vấn cây con bắt đầu từ id = 999 (không có trong bảng). Vì sao COUNT(*) − 1 không nên dùng máy móc để đếm hậu duệ?

<details>
<summary>Đáp án gợi ý</summary>

Anchor rỗng làm COUNT(*) = 0, nên COUNT(*)−1 thành **−1**, vô nghĩa. Dùng COUNT(*) WHERE do_sau > 0 hoặc kiểm tra sự tồn tại anchor riêng.

</details>

### Bài 18 — Duyệt DFS hay BFS?

Vì sao **ORDER BY ma_goc, do_sau, id** không tương đương với DFS theo nhánh?

<details>
<summary>Đáp án gợi ý</summary>

Vì nó sắp mọi nút depth 1 trước depth 2, tức ưu tiên theo tầng. DFS cần lần lượt đi sâu vào nhánh đang xét rồi mới đổi nhánh. Muốn thứ tự DFS, xây khóa đường đi phù hợp hoặc dùng SEARCH DEPTH FIRST trên DBMS hỗ trợ, sau đó ORDER BY khóa đó.

</details>

### Bài 19 — Tên trùng

Hai nhân viên khác nhau cùng tên **An**. Có nên phát hiện chu trình bằng cách thấy tên **An** đã xuất hiện trên đường đi không?

<details>
<summary>Đáp án gợi ý</summary>

**Không.** Tên không định danh duy nhất; hai người khác nhau có thể trùng tên. Theo dõi **id hoặc khóa định danh** trên từng đường đi.

</details>

### Bài 20 — Chuyển nhánh

Nếu cập nhật **quan_ly_id của Lan (1) = 12**, dữ liệu sẽ gặp vấn đề gì? Cần kiểm tra gì trước khi cập nhật cha?

<details>
<summary>Đáp án gợi ý</summary>

Quỳnh (12) vốn là hậu duệ Lan, nên đặt Lan dưới Quỳnh tạo chu trình. Trước khi gán cha mới Y cho X, cần kiểm tra **Y không bằng X và không thuộc cây con của X**, đồng thời thực thi kiểm tra/cập nhật có bảo vệ giao dịch để tránh xung đột đồng thời.

</details>

### Bài 21 — Đọc lược đồ

Giả sử gốc có depth 0, câu SQL:

~~~sql
WITH RECURSIVE x AS (
    SELECT id, quan_ly_id, 0 AS depth
    FROM nhan_vien
    WHERE id = 6

    UNION ALL

    SELECT n.id, n.quan_ly_id, x.depth + 1
    FROM nhan_vien n
    JOIN x ON n.quan_ly_id = x.id
)
SELECT id, depth FROM x;
~~~

sẽ trả những ID nào với dữ liệu mẫu?

<details>
<summary>Đáp án gợi ý</summary>

- Dũng (6), depth 0.
- Trang (8), Mai (9), depth 1.
- Quỳnh (12), depth 2.

Đây là **độ sâu tương đối từ Dũng**, không phải độ sâu toàn cục từ Lan.

</details>

### Bài 22 — Tính khoảng cách tổ tiên

Trong chuỗi 12 → 8 → 6 → 3 → 1, nếu CTE truy ngược từ 12 với distance = 0 thì giá trị distance của Lan là bao nhiêu? Nó có phải depth toàn cục của Lan không?

<details>
<summary>Đáp án gợi ý</summary>

Distance của Lan là **4** vì có bốn cạnh từ Quỳnh lên Lan. **Không** phải depth toàn cục của Lan; Lan là gốc nên depth toàn cục bằng 0.

</details>

## 31. Tình huống tổng hợp: trang quản trị sơ đồ tổ chức

Giả sử trang quản trị cần bốn tính năng:

1. Hiển thị một **cây nhân viên** từ quản lý được chọn, với độ sâu tương đối và tên để thụt dòng.
2. Hiển thị **đường dẫn quản lý** tới một nhân viên.
3. Đếm **số cấp dưới** của từng quản lý và tìm **độ sâu tối đa** của cây tổ chức.
4. Khi đổi quản lý, **không cho chuyển dưới chính hậu duệ**.

Một thiết kế trên adjacency list có thể triển khai như sau:

### 31.1. Màn hình cây con

Từ id quản lý đầu vào, chạy CTE xuống con và trả **id, ho_ten, quan_ly_id, do_sau_tuong_doi**, cùng đường dẫn ID hoặc khóa thứ tự nếu giao diện cần DFS ổn định.

Không mặc định **ORDER BY depth** tạo đúng cấu trúc hiển thị lồng nhau. Nếu giao diện tự dựng cây từ id/parent_id, thứ tự của từng nhóm anh chị em nên được quy định riêng (chẳng hạn theo tên, mã hoặc trường sort_order).

### 31.2. Breadcrumb quản lý

Từ nhân viên đầu vào, truy ngược qua **cha.id = c.quan_ly_id**. Kết quả có khoảng cách 0 tại nhân viên, tăng lên ở từng tổ tiên. Nếu cần hiển thị từ gốc tới nhân viên, phải **đảo thứ tự trình bày** dựa trên khoảng cách hoặc xây đường dẫn khi đi từ gốc.

### 31.3. Báo cáo thống kê

Từ tất cả gốc, tính **ma_goc** và **do_sau** để:

- Đếm số nhân viên từng tầng.
- Tính MAX(do_sau) của mỗi cây.
- Phát hiện cây vượt giới hạn tổ chức.
- Xem phân bố số nhân viên ở các tầng.

Nếu muốn số hậu duệ của **mọi nhân viên** thường xuyên, cân nhắc việc truy vấn từ mọi anchor tạo lượng lớn cặp tổ tiên–hậu duệ, hoặc một cơ chế lưu/cache chỉ số được cập nhật đúng.

### 31.4. Kiểm tra thay đổi quan hệ cha

Trước thao tác chuyển nhân viên X dưới Y:

- Kiểm tra X và Y tồn tại.
- Kiểm tra Y ≠ X.
- Kiểm tra Y **không thuộc cây con của X**.
- Kiểm tra ràng buộc tổ chức (ví dụ không vượt độ sâu tối đa).
- Thực hiện cập nhật trong một chính sách transaction/locking bảo đảm không hai thao tác đồng thời tạo vòng.
- Nếu có path/closure lưu sẵn, cập nhật các dữ liệu suy diễn liên quan.

Không dùng mỗi FOREIGN KEY để kết luận phép chuyển cha hợp lệ về cấu trúc cây.

### 31.5. Kiểm tra dữ liệu sau migration

Sau khi nạp hàng triệu nhân viên/danh mục từ hệ thống cũ, cần kiểm tra:

- Trùng **id**.
- **parent_id** trỏ tới ID không tồn tại.
- Nút tự tham chiếu.
- Thành phần **không tới được từ bất kỳ gốc nào**.
- Chu trình nhiều nút.
- Số gốc ngoài kỳ vọng.
- Độ sâu vượt chính sách.
- Tập nút thực sự có trong kết quả đệ quy.
- Các chỉ số thống kê có nhất quán với số dòng nguồn hay không.

Một truy vấn đệ quy chạy xong không đủ chứng minh cấu trúc cây sạch; nó có thể chỉ duyệt các thành phần có gốc và bỏ qua những nhánh lỗi.

## 32. Tổng kết kiến thức cần ghi nhớ

1. **Adjacency list** lưu một cạnh cha–con bằng **id** và **parent_id**; với cây hợp lệ, mỗi nút không gốc có đúng một cha và không có chu trình.
2. **Recursive CTE** có **anchor** chọn điểm bắt đầu và **recursive member** lặp quan hệ một bước. Thường ghép hai phần bằng **UNION ALL**.
3. Đi **xuống con** bằng điều kiện **n.parent_id = c.id**; đi **lên cha** bằng **cha.id = c.parent_id**.
4. Nếu gốc có **do_sau = 0**, mỗi bước xuống tăng 1; do_sau là **số cạnh từ anchor đến nút**, không nhất thiết là độ sâu toàn cục khi anchor nằm giữa cây.
5. Muốn duyệt **một cây con**, chọn nút đó làm anchor. Muốn bỏ nó khỏi kết quả, lọc **do_sau > 0** ở SELECT cuối.
6. Muốn duyệt cả rừng, anchor các nút **parent_id IS NULL** và mang theo **ma_goc** để phân biệt cây.
7. **MAX(do_sau)** cho độ sâu tối đa của các nút đã duyệt; **COUNT(*) GROUP BY do_sau** cho số nút mỗi tầng.
8. **Nút lá** không có con trực tiếp; có thể tìm bằng NOT EXISTS mà không cần đệ quy.
9. **ORDER BY** ở SELECT ngoài quyết định thứ tự hiển thị. Sắp theo depth giống phân tầng; muốn DFS cần khóa đường dẫn hoặc SEARCH khi DBMS hỗ trợ.
10. **Chu trình có thể khiến UNION ALL lặp vô hạn** và **UNION không chắc ngăn được** vì depth/path thay đổi. Theo dõi **ID đã thăm trên từng đường**, dùng CYCLE nếu hỗ trợ và đặt giới hạn kỹ thuật.
11. **Orphan và thành phần chu trình có thể bị bỏ sót** khi chỉ anchor từ các gốc hợp lệ. Cần kiểm tra cả các nút không tới được từ gốc.
12. **FOREIGN KEY** giúp kiểm tra cha tồn tại, nhưng **không tự bảo đảm không có chu trình**. Đổi cha cần kiểm tra quan hệ hậu duệ và tính đồng thời.
13. **PostgreSQL/MySQL/SQLite** dùng **WITH RECURSIVE**; **SQL Server/Oracle** dùng cú pháp WITH khác; Oracle còn có **START WITH ... CONNECT BY**.
14. Chỉ mục trên **parent_id**, kiểu dữ liệu path, giới hạn recursion và lượng dòng trung gian quyết định hiệu năng.
15. Trước khi viết truy vấn, hãy hỏi **đang tính khoảng cách từ đâu, muốn lấy ai, và cấu trúc có chắc là cây hợp lệ không?** Đây là chìa khóa để duyệt đúng và tính đúng độ sâu.

### Tài liệu tham khảo theo DBMS

Khi đưa vào hệ thống thực tế, hãy tra cứu tài liệu chính thức theo **sản phẩm và phiên bản đang chạy**, đặc biệt các mục recursive CTE, hierarchical queries, cycle detection, query limits và execution plans:

- **PostgreSQL Documentation:** *WITH Queries — Recursive Queries*, *SEARCH/CYCLE*, *Array Functions and Operators*.
- **MySQL Reference Manual:** *Recursive Common Table Expressions*, *Limiting Common Table Expression Recursion*, *WITH Syntax*.
- **Microsoft Learn — Transact-SQL:** *Recursive Queries Using Common Table Expressions*, *MAXRECURSION Query Hint*.
- **Oracle Database SQL Language Reference:** *Hierarchical Queries*, *Recursive Subquery Factoring*, *SEARCH and CYCLE Clauses*.
- **SQLite Documentation:** *The WITH Clause — Recursive Common Table Expressions*, *Controlling Depth-First Versus Breadth-First Search*.

**Nguyên tắc cuối cùng:** một recursive CTE đúng không chỉ “chạy tới hết dòng”. Nó phải bắt đầu từ **đúng nút**, đi theo **đúng hướng**, tính depth theo **quy ước rõ ràng**, bảo vệ khỏi **dữ liệu có vòng hoặc mất cha**, và chỉ hiển thị/tổng hợp các nút mà nghiệp vụ thật sự yêu cầu.

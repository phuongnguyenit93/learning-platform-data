# Chuyển hàng thành cột bằng tổng hợp có điều kiện

Trong **Database SQL**, dữ liệu giao dịch thường được lưu theo dạng **mỗi dòng là một sự kiện**: một đơn hàng, một lượt bán, một khoản thu hoặc một lần ghi nhận trạng thái. Nhưng báo cáo lại hay cần dạng **mỗi dòng là một đối tượng, mỗi cột là một loại chỉ tiêu**, ví dụ một dòng cho mỗi khu vực và ba cột doanh thu `ONLINE`, `STORE`, `PARTNER`.

Kỹ thuật biến những **giá trị nằm trên nhiều hàng thành các cột báo cáo** gọi là **pivot (xoay dữ liệu)**. Một cách viết phổ biến, dễ hiểu và áp dụng được ở nhiều hệ quản trị là **tổng hợp có điều kiện (conditional aggregation)**: kết hợp `GROUP BY` với `SUM(CASE WHEN ...)`, `COUNT(CASE WHEN ...)`, `AVG(CASE WHEN ...)` hoặc các hàm tổng hợp khác.

Bài học thuộc nhóm **Mẫu truy vấn**: không chỉ giới thiệu câu SQL chạy được mà còn giải thích cách chọn đúng đơn vị nhóm, xử lý giá trị thiếu, tránh nhân số liệu khi `JOIN`, phân biệt lọc trước và sau tổng hợp, và biết khi nào nên dùng cú pháp `PIVOT` riêng của DBMS.

## 1. Từ bảng dài sang bảng rộng

Giả sử dữ liệu bán hàng ban đầu có dạng:

| region | channel | amount |
| --- | --- | ---: |
| Bắc | ONLINE | 100 |
| Bắc | STORE | 200 |
| Bắc | ONLINE | 150 |
| Nam | ONLINE | 80 |
| Nam | STORE | 120 |
| Nam | STORE | 60 |
| Trung | ONLINE | 90 |

Đây là **dạng dài (long format)**: kênh bán nằm trong một cột `channel`, mỗi giao dịch là một dòng.

Báo cáo cần:

| region | online_amount | store_amount | total_amount |
| --- | ---: | ---: | ---: |
| Bắc | 250 | 200 | 450 |
| Nam | 80 | 180 | 260 |
| Trung | 90 | 0 | 90 |

Đây là **dạng rộng (wide format)**: các giá trị `ONLINE` và `STORE` trở thành tên cột. Ta muốn SQL:

1. Gom các giao dịch của cùng một khu vực thành một **nhóm**.
2. Trong mỗi nhóm, chỉ cộng tiền của kênh `ONLINE` vào cột `online_amount`.
3. Chỉ cộng tiền của kênh `STORE` vào cột `store_amount`.
4. Cộng tất cả giao dịch của nhóm vào `total_amount`.

Ý tưởng:

```text
Dữ liệu dài                      Tổng hợp có điều kiện
region  channel   amount          GROUP BY region
Bắc     ONLINE       100                  |
Bắc     STORE        200                  v
Bắc     ONLINE       150       Bắc  | ONLINE = 100+150
Nam     ONLINE        80            | STORE  = 200
Nam     STORE        120
Nam     STORE         60       Nam  | ONLINE = 80
                                       | STORE  = 120+60
```

**Pivot bằng tổng hợp có điều kiện không tự tạo cột mới tùy ý.** Các tên cột đích thường phải được **liệt kê trước trong SQL**. Đây là dạng *static pivot*, rất phù hợp khi bộ kênh/trạng thái/tháng báo cáo đã biết.

## 2. Công thức cơ bản: SUM kết hợp CASE WHEN

Mẫu nền tảng:

```sql
SELECT
    group_key,
    SUM(CASE WHEN category = 'A' THEN amount ELSE 0 END) AS amount_a,
    SUM(CASE WHEN category = 'B' THEN amount ELSE 0 END) AS amount_b,
    SUM(amount) AS total_amount
FROM source_table
GROUP BY group_key;
```

Cách đọc:

- `GROUP BY group_key` tạo một dòng kết quả cho mỗi giá trị nhóm.
- `CASE WHEN category = 'A' THEN amount ELSE 0 END` tạo một giá trị riêng trên **từng dòng nguồn**: tiền thật nếu là A, bằng 0 nếu không phải A.
- `SUM(...)` cộng các giá trị đó **trong nhóm hiện tại**.
- Biểu thức tương tự dành cho B.
- `AS amount_a` và `AS amount_b` đặt tên cột báo cáo; tên này không có nghĩa là database tự tạo cột vật lý.

Ví dụ SQL tổng quát:

```sql
SELECT
    region,
    SUM(CASE WHEN channel = 'ONLINE'
             THEN amount ELSE 0 END) AS online_amount,
    SUM(CASE WHEN channel = 'STORE'
             THEN amount ELSE 0 END) AS store_amount,
    SUM(amount) AS total_amount
FROM sales
GROUP BY region
ORDER BY region;
```

Nếu một khu vực có nhiều giao dịch ONLINE, tất cả các khoản đó được cộng vào cùng một ô `online_amount`.

### Vì sao phải có GROUP BY?

Không có `GROUP BY`:

```sql
SELECT
    SUM(CASE WHEN channel = 'ONLINE'
             THEN amount ELSE 0 END) AS online_amount,
    SUM(CASE WHEN channel = 'STORE'
             THEN amount ELSE 0 END) AS store_amount
FROM sales;
```

kết quả là **một dòng tổng cho toàn bộ bảng** sau các điều kiện lọc, không phải một dòng mỗi khu vực.

Thêm `GROUP BY region` thay đổi **đơn vị của dòng kết quả** thành **một khu vực**. Nếu nhóm theo cả `region, sold_on` thì đơn vị thành **một khu vực trong một ngày**. Chọn sai tập cột `GROUP BY` sẽ thay đổi kết quả pivot dù từng phép `SUM(CASE...)` viết đúng.

## 3. CASE tạo giá trị từng dòng; SUM thực hiện tổng hợp

Giả sử chỉ xét các dòng của khu vực Bắc:

| channel | amount | `CASE ... ONLINE ... ELSE 0` | `CASE ... STORE ... ELSE 0` |
| --- | ---: | ---: | ---: |
| ONLINE | 100 | 100 | 0 |
| STORE | 200 | 0 | 200 |
| ONLINE | 150 | 150 | 0 |

Sau khi tính `CASE` trên từng dòng:

```text
online_amount = SUM(100, 0, 150) = 250
store_amount  = SUM(0, 200, 0)   = 200
total_amount  = SUM(100,200,150) = 450
```

Không phải `CASE` tự cộng dữ liệu. `CASE` chỉ **chọn biểu thức của từng dòng**, còn hàm `SUM` mới kết hợp các giá trị của nhóm.

Cũng không phải `SUM` tự biết rằng `'ONLINE'` phải thành tên cột: chính người viết SQL đặt tên `AS online_amount` và lựa chọn điều kiện `channel = 'ONLINE'`.

### Thứ tự các nhánh điều kiện

Khi một điều kiện chỉ thuộc một nhóm và các nhóm loại trừ nhau, mỗi cột thường dùng một `CASE` riêng. Không viết:

```sql
-- Không đáp ứng mục tiêu ba cột riêng:
SUM(CASE
      WHEN channel = 'ONLINE' THEN amount
      WHEN channel = 'STORE' THEN amount
      ELSE 0
    END)
```

Biểu thức trên cộng tiền của cả ONLINE và STORE **vào một số**, chứ không tạo hai cột. Muốn hai cột, cần **hai biểu thức tổng hợp**.

## 4. ELSE 0, không có ELSE và COALESCE khác nhau ra sao?

Đây là chi tiết quyết định ý nghĩa “không có dữ liệu”.

### Cách A: SUM(CASE ... THEN amount ELSE 0 END)

```sql
SUM(CASE WHEN channel = 'ONLINE'
         THEN amount ELSE 0 END) AS online_amount
```

Trong một nhóm **có ít nhất một dòng**, các dòng không khớp cho giá trị 0. Nếu không có dòng ONLINE nhưng có các dòng kênh khác, tổng là **0**.

### Cách B: SUM(CASE ... THEN amount END)

```sql
SUM(CASE WHEN channel = 'ONLINE'
         THEN amount END) AS online_amount
```

Không có `ELSE` thì `CASE` ngầm trả `NULL` khi không khớp. `SUM` bỏ qua các giá trị `NULL`, và nếu không có giá trị số khác `NULL` để cộng thì `SUM` thường trả **`NULL`**, không phải 0.

### Cách C: COALESCE bao quanh SUM

```sql
COALESCE(
    SUM(CASE WHEN channel = 'ONLINE' THEN amount END),
    0
) AS online_amount
```

Cách này chủ động chuyển kết quả tổng hợp `NULL` thành 0 cho mục đích trình bày.

| Tình huống | `SUM(CASE ... ELSE 0 END)` | `SUM(CASE ... END)` | `COALESCE(SUM(CASE ... END),0)` |
| --- | --- | --- | --- |
| Nhóm có dòng ONLINE số 100 | 100 | 100 | 100 |
| Nhóm có dòng nhưng không có ONLINE | 0 | `NULL` | 0 |
| Không tồn tại nhóm đầu vào để `GROUP BY` | Không có dòng kết quả | Không có dòng kết quả | Không có dòng kết quả |
| Có dòng ONLINE nhưng `amount` là `NULL`, không có khoản số nào khác | Có thể `NULL` nếu mọi giá trị CASE đều NULL | `NULL` | 0 |

**Một cảnh báo:** khi `amount` được phép `NULL`, `ELSE 0` không thay thế giá trị `NULL` ở nhánh `THEN amount`. Nếu muốn coi khoản tiền thiếu là 0, phải nêu rõ chính sách và có thể dùng `COALESCE(amount,0)`; nhưng như vậy sẽ **mất khả năng phân biệt chưa ghi nhận với số 0 thật**.

**Không có dòng trong nhóm** khác với **nhóm có dòng nhưng không có giá trị của một kênh**. Nếu khu vực không có bất kỳ giao dịch nào, `GROUP BY region` trên bảng giao dịch không sinh ra hàng cho khu vực đó. Muốn vẫn hiển thị khu vực, cần nối với **bảng danh mục khu vực** (mục 9).

## 5. COUNT có điều kiện: đếm dòng của từng loại

Pivot không chỉ áp dụng cho doanh thu. Cũng có thể đếm số giao dịch theo kênh:

```sql
SELECT
    region,
    COUNT(CASE WHEN channel = 'ONLINE' THEN 1 END) AS online_count,
    COUNT(CASE WHEN channel = 'STORE' THEN 1 END) AS store_count,
    COUNT(CASE WHEN channel = 'PARTNER' THEN 1 END) AS partner_count
FROM sales
GROUP BY region;
```

`COUNT(expression)` đếm **giá trị khác `NULL`**. Vì thế `CASE WHEN ... THEN 1 END` tạo 1 khi khớp và `NULL` khi không khớp; COUNT trả đúng số dòng phù hợp.

Cách tương đương thường gặp:

```sql
SELECT
    region,
    SUM(CASE WHEN channel = 'ONLINE' THEN 1 ELSE 0 END)
        AS online_count
FROM sales
GROUP BY region;
```

Khác biệt cần nhớ: `COUNT(CASE...)` trả **0** khi không có giá trị khác `NULL`, còn `SUM(CASE...)` trên tập đầu vào hoàn toàn rỗng có thể trả `NULL`; trong các nhóm có dòng, cả hai thường bằng nhau nếu viết đúng.

### Lỗi COUNT(CASE ... ELSE 0 END)

```sql
-- SAI nếu mục tiêu là chỉ đếm ONLINE:
COUNT(CASE WHEN channel = 'ONLINE' THEN 1 ELSE 0 END)
```

Cách trên đếm **mọi dòng** vì cả `1` và `0` đều khác `NULL`. Nếu muốn dùng `ELSE 0`, hãy dùng `SUM`, không dùng `COUNT`.

### Đếm giá trị có thật khác với đếm sự kiện

```sql
COUNT(CASE WHEN channel = 'ONLINE' THEN customer_id END)
```

chỉ đếm các dòng ONLINE có `customer_id IS NOT NULL`. Trong khi:

```sql
COUNT(CASE WHEN channel = 'ONLINE' THEN 1 END)
```

đếm mọi giao dịch ONLINE, kể cả khi `customer_id IS NULL`.

Với yêu cầu **khách hàng duy nhất theo kênh**:

```sql
COUNT(DISTINCT CASE
    WHEN channel = 'ONLINE' THEN customer_id
END) AS online_unique_customers
```

`DISTINCT` loại các ID trùng **trong riêng tập ONLINE** và bỏ `NULL`. Tổng số khách hàng duy nhất theo từng kênh **không nhất thiết bằng** tổng số khách hàng duy nhất toàn vùng vì một người có thể mua ở nhiều kênh.

## 6. AVG, MIN, MAX trong bảng pivot

Tùy chỉ tiêu, không nhất thiết dùng `SUM`.

### Giá trị giao dịch trung bình từng kênh

```sql
SELECT
    region,
    AVG(CASE WHEN channel = 'ONLINE' THEN amount END)
        AS avg_online_amount,
    AVG(CASE WHEN channel = 'STORE' THEN amount END)
        AS avg_store_amount
FROM sales
GROUP BY region;
```

Cách viết **không có `ELSE 0`** rất quan trọng: `AVG` chỉ tính trên các khoản tiền của kênh được chọn. Những dòng khác được `CASE` trả `NULL` và không tham gia mẫu số.

Nếu viết:

```sql
-- Thường SAI ý nghĩa "trung bình của giao dịch ONLINE".
AVG(CASE WHEN channel = 'ONLINE' THEN amount ELSE 0 END)
```

thì mẫu số có thể gồm **mọi dòng trong khu vực**, khiến trung bình của ONLINE giảm giả tạo.

Ví dụ khu vực Bắc có năm giao dịch đã thanh toán, trong đó hai giao dịch ONLINE có tiền 100 và 150. Trung bình ONLINE đúng là:

\[
(100 + 150) / 2 = 125
\]

Nhưng dùng `AVG(CASE ... ELSE 0 END)` sẽ chia 250 cho cả 5 giao dịch, được **50**, không trả lời câu hỏi “giao dịch ONLINE trung bình bao nhiêu”.

Nếu không có giao dịch thuộc một kênh, `AVG(CASE ... END)` trả `NULL`; đó có thể là biểu diễn đúng của “không có mẫu để tính trung bình”, thay vì số 0.

### Giá trị lớn nhất/nhỏ nhất theo loại

```sql
SELECT
    region,
    MAX(CASE WHEN channel = 'ONLINE' THEN amount END)
        AS largest_online_sale,
    MIN(CASE WHEN channel = 'STORE' THEN amount END)
        AS smallest_store_sale
FROM sales
GROUP BY region;
```

`MAX` chọn số tiền lớn nhất trong các giao dịch ONLINE; `MIN` chọn nhỏ nhất trong các giao dịch STORE. Không có giao dịch phù hợp thì kết quả `NULL`.

### MAX(CASE ...) để đưa giá trị văn bản vào một ô

Nếu dữ liệu bảo đảm **mỗi nhóm chỉ có tối đa một dòng cho một loại**, có thể dùng:

```sql
SELECT
    customer_id,
    MAX(CASE WHEN contact_type = 'EMAIL' THEN contact_value END)
        AS email,
    MAX(CASE WHEN contact_type = 'PHONE' THEN contact_value END)
        AS phone
FROM customer_contacts
GROUP BY customer_id;
```

Đây chỉ là mẫu minh họa, chưa tạo bảng `customer_contacts`. Nếu một khách có **nhiều email**, `MAX` sẽ lấy một giá trị lớn nhất theo quy tắc so sánh chuỗi, **không tự chọn email chính hoặc mới nhất**. Khi cần “giá trị mới nhất”, phải xác định thứ tự bằng cột ngày/ID, xử lý trùng và chọn đúng một dòng trước khi pivot.

## 7. Chuẩn bị bộ dữ liệu PostgreSQL có đủ trường hợp khó

Phần thực hành sử dụng **PostgreSQL** trong database học tập. Hai bảng có tiền tố `sql256_` để giảm nguy cơ trùng với bảng nghiệp vụ. Có bốn khu vực, ba kênh bán và ba trạng thái đơn; một khu vực không có bất kỳ giao dịch **PAID** nào.

### 7.1. Tạo bảng danh mục và bảng giao dịch

```sql
CREATE TABLE sql256_regions (
    region_code VARCHAR(2) PRIMARY KEY,
    region_name VARCHAR(30) NOT NULL
);

CREATE TABLE sql256_sales (
    sale_id INTEGER PRIMARY KEY,
    region_code VARCHAR(2) NOT NULL
        REFERENCES sql256_regions(region_code),
    channel VARCHAR(12) NOT NULL,
    sold_on DATE NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    status VARCHAR(12) NOT NULL,
    customer_id INTEGER
);
```

`amount` được khai báo `NOT NULL` trong bảng thực hành để kết quả tổng tiền rõ ràng. Ở hệ thật, nếu tiền có thể `NULL` thì phải xem quy tắc tại mục 4.

### 7.2. Chèn dữ liệu

```sql
INSERT INTO sql256_regions (region_code, region_name)
VALUES
    ('B', 'Bắc'),
    ('N', 'Nam'),
    ('T', 'Trung'),
    ('W', 'Tây');

INSERT INTO sql256_sales
    (sale_id,region_code,channel,sold_on,amount,status,customer_id)
VALUES
    ( 1,'B','ONLINE', DATE '2026-01-03',100.00,'PAID',1),
    ( 2,'B','STORE', DATE '2026-01-06',200.00,'PAID',2),
    ( 3,'B','ONLINE', DATE '2026-02-02',150.00,'PAID',1),
    ( 4,'B','PARTNER',DATE '2026-02-15', 50.00,'PAID',3),
    ( 5,'B','ONLINE', DATE '2026-02-20', 25.00,'CANCELLED',4),
    ( 6,'N','ONLINE', DATE '2026-01-07', 80.00,'PAID',5),
    ( 7,'N','STORE', DATE '2026-01-15',120.00,'PAID',5),
    ( 8,'N','STORE', DATE '2026-03-05', 60.00,'PAID',6),
    ( 9,'N','PARTNER',DATE '2026-03-12', 40.00,'PENDING',NULL),
    (10,'T','ONLINE', DATE '2026-01-20', 90.00,'PAID',7),
    (11,'T','ONLINE', DATE '2026-03-11', 30.00,'PAID',NULL),
    (12,'B','STORE', DATE '2026-03-19', 70.00,'PAID',2),
    (13,'W','STORE', DATE '2026-03-22',999.00,'CANCELLED',8);
```

Kiểm tra:

```sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_rows,
    SUM(amount) FILTER (WHERE status = 'PAID') AS paid_amount
FROM sql256_sales;
```

Kết quả lần lượt **13**, **10**, **950.00**. `FILTER` là cú pháp được PostgreSQL hỗ trợ; phần sau sẽ giới thiệu cách viết `CASE` di động hơn.

## 8. Pivot số tiền đã thanh toán theo khu vực và kênh

Đây là truy vấn trung tâm của bài:

```sql
SELECT
    s.region_code,
    SUM(CASE WHEN s.channel = 'ONLINE' THEN s.amount ELSE 0 END)
        AS online_amount,
    SUM(CASE WHEN s.channel = 'STORE' THEN s.amount ELSE 0 END)
        AS store_amount,
    SUM(CASE WHEN s.channel = 'PARTNER' THEN s.amount ELSE 0 END)
        AS partner_amount,
    SUM(s.amount) AS total_amount,
    COUNT(*) AS paid_sale_count
FROM sql256_sales AS s
WHERE s.status = 'PAID'
GROUP BY s.region_code
ORDER BY s.region_code;
```

Kết quả:

| region_code | online_amount | store_amount | partner_amount | total_amount | paid_sale_count |
| --- | ---: | ---: | ---: | ---: | ---: |
| B | 250.00 | 270.00 | 50.00 | 570.00 | 5 |
| N | 80.00 | 180.00 | 0.00 | 260.00 | 3 |
| T | 120.00 | 0.00 | 0.00 | 120.00 | 2 |

Ở vùng Bắc:

- ONLINE: `100 + 150 = 250`.
- STORE: `200 + 70 = 270`.
- PARTNER: `50`.
- Tổng đã thanh toán: `250 + 270 + 50 = 570`.

Ở vùng Nam, `PENDING` của kênh PARTNER không được tính vì `WHERE status = 'PAID'`. Ở vùng Tây, giao dịch STORE bị `CANCELLED` nên **không có nhóm Tây** trong kết quả từ bảng giao dịch sau `WHERE`.

**Đừng nhầm không có dòng Tây với doanh thu Tây bằng `NULL` hoặc 0.** Trong câu `GROUP BY` này, Tây **không tồn tại ở đầu ra**, vì không có dòng nào qua `WHERE` để tạo nhóm. Mục 9 xử lý việc hiển thị cả vùng không phát sinh doanh thu hợp lệ.

### Kiểm tra tính nhất quán tổng tiền

Nếu bộ kênh hợp lệ chỉ gồm ba kênh trên, mỗi dòng `PAID` thuộc đúng một kênh, nên tổng ba cột kênh bằng `total_amount`.

Nhưng nếu tương lai xuất hiện `channel = 'MOBILE'`, cột `total_amount` sẽ cộng cả MOBILE, còn ba cột pivot vẫn chỉ cộng ONLINE/STORE/PARTNER. Khi đó tổng ba cột sẽ **nhỏ hơn tổng thật**. Cần cập nhật danh sách kênh báo cáo, thêm cột `other_amount` hoặc thể hiện cảnh báo loại chưa phân loại; không được âm thầm cho rằng đã bao phủ mọi giá trị.

## 9. Giữ cả nhóm không có giao dịch bằng LEFT JOIN

Một báo cáo quản trị có thể yêu cầu hiển thị **tất cả khu vực**, kể cả nơi không có giao dịch PAID. Cần xuất phát từ `sql256_regions` (bảng danh mục) và `LEFT JOIN` dữ liệu phù hợp.

### Cách đúng: lọc PAID trong ON

```sql
SELECT
    r.region_code,
    r.region_name,
    SUM(CASE WHEN s.channel = 'ONLINE' THEN s.amount ELSE 0 END)
        AS online_amount,
    SUM(CASE WHEN s.channel = 'STORE' THEN s.amount ELSE 0 END)
        AS store_amount,
    SUM(CASE WHEN s.channel = 'PARTNER' THEN s.amount ELSE 0 END)
        AS partner_amount,
    COALESCE(SUM(s.amount), 0) AS total_amount,
    COUNT(s.sale_id) AS paid_sale_count
FROM sql256_regions AS r
LEFT JOIN sql256_sales AS s
  ON s.region_code = r.region_code
 AND s.status = 'PAID'
GROUP BY r.region_code, r.region_name
ORDER BY r.region_code;
```

Kết quả bao gồm thêm:

| region_code | region_name | online_amount | store_amount | partner_amount | total_amount | paid_sale_count |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| B | Bắc | 250 | 270 | 50 | 570 | 5 |
| N | Nam | 80 | 180 | 0 | 260 | 3 |
| T | Trung | 120 | 0 | 0 | 120 | 2 |
| W | Tây | 0 | 0 | 0 | 0 | 0 |

Dòng Tây được giữ vì nó có trong bảng `regions`. Khi không có sale PAID tương ứng, `LEFT JOIN` tạo một dòng có các cột `s` là `NULL`:

- `CASE WHEN s.channel = 'ONLINE' THEN s.amount ELSE 0 END` trả 0 vì điều kiện không đúng.
- `COUNT(s.sale_id)` trả 0 vì `s.sale_id` là `NULL`.
- `SUM(s.amount)` trả `NULL` nên `COALESCE(SUM(s.amount),0)` biểu diễn tổng là 0.

### Lỗi phổ biến: để điều kiện status trong WHERE

```sql
-- SAI nếu phải giữ cả vùng không có đơn PAID:
SELECT r.region_code, COUNT(*) AS row_count
FROM sql256_regions AS r
LEFT JOIN sql256_sales AS s
  ON s.region_code = r.region_code
WHERE s.status = 'PAID'
GROUP BY r.region_code;
```

`WHERE s.status = 'PAID'` loại dòng mà `s` được bổ sung bằng `NULL`, nên Tây biến mất. Điều kiện trong `ON` và điều kiện trong `WHERE` **không tương đương** khi giữ dòng bên trái của OUTER JOIN.

### Cảnh báo COUNT(*) trên LEFT JOIN

```sql
-- Sai nếu muốn đếm số giao dịch thực:
COUNT(*)
```

Vùng Tây vẫn có một dòng kết quả `LEFT JOIN` được bổ sung `NULL` ở phía `s`; `COUNT(*)` vì thế có thể trả **1**, không phải 0. Dùng `COUNT(s.sale_id)` với khóa sale không `NULL` để chỉ đếm giao dịch thực sự có mặt.

### Cách khác: tổng hợp trước rồi LEFT JOIN

Nếu nhiều phần báo cáo dùng cùng tổng tiền theo vùng, có thể tổng hợp trong CTE:

```sql
WITH paid_pivot AS (
    SELECT
        region_code,
        SUM(CASE WHEN channel = 'ONLINE' THEN amount ELSE 0 END)
            AS online_amount,
        SUM(CASE WHEN channel = 'STORE' THEN amount ELSE 0 END)
            AS store_amount,
        SUM(CASE WHEN channel = 'PARTNER' THEN amount ELSE 0 END)
            AS partner_amount,
        SUM(amount) AS total_amount,
        COUNT(*) AS sale_count
    FROM sql256_sales
    WHERE status = 'PAID'
    GROUP BY region_code
)
SELECT
    r.region_code,
    r.region_name,
    COALESCE(p.online_amount, 0) AS online_amount,
    COALESCE(p.store_amount, 0) AS store_amount,
    COALESCE(p.partner_amount, 0) AS partner_amount,
    COALESCE(p.total_amount, 0) AS total_amount,
    COALESCE(p.sale_count, 0) AS paid_sale_count
FROM sql256_regions AS r
LEFT JOIN paid_pivot AS p ON p.region_code = r.region_code
ORDER BY r.region_code;
```

Cách này làm rõ **hai giai đoạn logic**: pivot trên tập giao dịch PAID, rồi thêm các khu vực còn thiếu. `COALESCE` ở truy vấn ngoài xử lý việc không có một dòng tương ứng trong `paid_pivot`.

## 10. Lọc toàn bộ nguồn và điều kiện trong CASE khác nhau

Có ba cách viết dễ bị nhầm:

**A. Chỉ dùng các giao dịch PAID cho mọi chỉ tiêu:**

```sql
SELECT region_code,
       SUM(CASE WHEN channel = 'ONLINE' THEN amount ELSE 0 END)
           AS online_amount,
       SUM(amount) AS total_amount
FROM sql256_sales
WHERE status = 'PAID'
GROUP BY region_code;
```

**B. Giữ mọi giao dịch làm đầu vào, nhưng chỉ tính PAID cho từng cột:**

```sql
SELECT region_code,
       SUM(CASE WHEN status = 'PAID' AND channel = 'ONLINE'
                THEN amount ELSE 0 END) AS paid_online_amount,
       SUM(CASE WHEN status = 'PAID'
                THEN amount ELSE 0 END) AS total_paid_amount,
       COUNT(*) AS all_sale_rows
FROM sql256_sales
GROUP BY region_code;
```

**C. Lọc giao dịch theo kênh trước rồi đếm mọi dòng còn lại:**

```sql
SELECT region_code,
       COUNT(*) AS online_rows
FROM sql256_sales
WHERE channel = 'ONLINE'
GROUP BY region_code;
```

A và B có thể cho cùng tiền PAID ở những khu vực có giao dịch, nhưng **số nhóm và các chỉ tiêu khác** có thể khác:

- A **không trả vùng Tây** vì Tây không có giao dịch PAID.
- B vẫn trả Tây với `total_paid_amount = 0` vì Tây có một giao dịch CANCELLED.
- B có thể đồng thời đếm toàn bộ giao dịch với `all_sale_rows`.
- C chỉ tính kênh ONLINE, bất kể trạng thái nếu không thêm `status` vào `WHERE`.

**Nguyên tắc:** `WHERE` loại dòng khỏi **toàn bộ phép tổng hợp trong câu truy vấn**; điều kiện trong `CASE` chỉ quyết định **đóng góp vào một ô/chỉ tiêu cụ thể**, không tự loại dòng khỏi những phép tổng hợp khác.

## 11. Đếm, doanh thu và khách hàng duy nhất trên cùng một hàng

Một bảng pivot có thể chứa nhiều họ chỉ tiêu cùng lúc.

```sql
-- PostgreSQL:
SELECT
    s.region_code,
    SUM(CASE WHEN s.channel = 'ONLINE' THEN s.amount ELSE 0 END)
        AS online_amount,
    COUNT(CASE WHEN s.channel = 'ONLINE' THEN 1 END)
        AS online_sale_count,
    COUNT(DISTINCT CASE
        WHEN s.channel = 'ONLINE' THEN s.customer_id
    END) AS online_unique_customers,
    COUNT(*) AS paid_sale_count,
    COUNT(DISTINCT s.customer_id) AS paid_unique_customers
FROM sql256_sales AS s
WHERE s.status = 'PAID'
GROUP BY s.region_code
ORDER BY s.region_code;
```

Với vùng Bắc:

- `online_amount = 250`.
- `online_sale_count = 2` (sale 1 và 3).
- `online_unique_customers = 1` (cả hai lần bán đều là customer 1).
- `paid_sale_count = 5`.
- `paid_unique_customers = 3` (customer 1, 2, 3).

Với vùng Trung, có hai giao dịch ONLINE nhưng một dòng thiếu `customer_id`; vì thế `online_sale_count = 2` và `online_unique_customers = 1`.

Việc tách **số lượt** và **số đối tượng khác nhau** giúp tránh giải thích nhầm `COUNT(DISTINCT ...)` là số giao dịch. Người có nhiều giao dịch có thể chỉ được đếm một lần trong số unique.

## 12. Pivot tháng: thêm thời gian vào danh sách cột

Khi cần báo cáo tháng 1, 2 và 3 của năm 2026, có thể tạo ba cột tháng bằng điều kiện ngày:

```sql
SELECT
    s.region_code,
    SUM(CASE WHEN s.sold_on >= DATE '2026-01-01'
              AND s.sold_on <  DATE '2026-02-01'
             THEN s.amount ELSE 0 END) AS jan_amount,
    SUM(CASE WHEN s.sold_on >= DATE '2026-02-01'
              AND s.sold_on <  DATE '2026-03-01'
             THEN s.amount ELSE 0 END) AS feb_amount,
    SUM(CASE WHEN s.sold_on >= DATE '2026-03-01'
              AND s.sold_on <  DATE '2026-04-01'
             THEN s.amount ELSE 0 END) AS mar_amount,
    SUM(s.amount) AS total_paid_amount
FROM sql256_sales AS s
WHERE s.status = 'PAID'
  AND s.sold_on >= DATE '2026-01-01'
  AND s.sold_on <  DATE '2026-04-01'
GROUP BY s.region_code
ORDER BY s.region_code;
```

Kết quả:

| region_code | jan_amount | feb_amount | mar_amount | total_paid_amount |
| --- | ---: | ---: | ---: | ---: |
| B | 300 | 200 | 70 | 570 |
| N | 200 | 0 | 60 | 260 |
| T | 90 | 0 | 30 | 120 |

Tổng toàn bộ ba tháng = `590 + 200 + 160 = 950`.

Ưu điểm của điều kiện khoảng **`>= đầu tháng` và `< đầu tháng tiếp theo`**:

- Phân biệt được **năm**; không gộp tháng 1 năm khác.
- Thích hợp với cả `DATE` và cách xử lý phù hợp cho `TIMESTAMP` khi dùng các mốc đúng kiểu.
- Nếu dùng bộ lọc ngoài cùng theo khoảng liên tục, DBMS có thể tận dụng index trên cột ngày tốt hơn việc áp hàm lên cột ở mọi dòng, tùy execution plan.

### Dùng EXTRACT khi phù hợp

Trên PostgreSQL, có thể viết:

```sql
SUM(CASE WHEN EXTRACT(YEAR FROM sold_on) = 2026
          AND EXTRACT(MONTH FROM sold_on) = 1
         THEN amount ELSE 0 END) AS jan_amount
```

Cách này dễ đọc, nhưng phải **ghép năm với tháng**. Chỉ `EXTRACT(MONTH FROM sold_on) = 1` sẽ cộng tháng 1 của mọi năm. Đối với cột `TIMESTAMPTZ`, việc nhóm ngày/tháng còn phụ thuộc **múi giờ nghiệp vụ**; cùng một instant có thể thuộc tháng khác theo UTC và giờ địa phương.

### Khi tháng là hàng hay cột?

Pivot thành mười hai cột có ích cho báo cáo cố định theo năm. Nếu người dùng cần tự chọn khoảng dài nhiều năm hoặc mở rộng số kỳ linh hoạt, dạng dài:

```sql
SELECT
    DATE_TRUNC('month', sold_on::timestamp)::date AS month_start,
    region_code,
    SUM(amount) AS paid_amount
FROM sql256_sales
WHERE status = 'PAID'
GROUP BY DATE_TRUNC('month', sold_on::timestamp)::date, region_code
ORDER BY month_start, region_code;
```

có thể thuận tiện hơn để frontend/chart xoay thành các cột. Hãy chọn định dạng đầu ra theo nhu cầu sử dụng, không nhất thiết pivot tất cả dữ liệu ngay trong SQL.

## 13. PostgreSQL FILTER: cú pháp ngắn thay cho CASE

PostgreSQL hỗ trợ điều kiện riêng cho aggregate bằng `FILTER (WHERE ...)`:

```sql
SELECT
    region_code,
    COALESCE(SUM(amount) FILTER (WHERE channel = 'ONLINE'), 0)
        AS online_amount,
    COALESCE(SUM(amount) FILTER (WHERE channel = 'STORE'), 0)
        AS store_amount,
    COALESCE(SUM(amount) FILTER (WHERE channel = 'PARTNER'), 0)
        AS partner_amount,
    COUNT(*) FILTER (WHERE channel = 'ONLINE') AS online_count,
    COUNT(*) AS paid_sale_count
FROM sql256_sales
WHERE status = 'PAID'
GROUP BY region_code
ORDER BY region_code;
```

Ở ví dụ này, `FILTER` áp dụng riêng cho từng hàm tổng hợp. `WHERE status = 'PAID'` bên ngoài vẫn lọc nguồn cho **tất cả** chỉ tiêu.

Tương ứng:

| `CASE` | `FILTER` trên PostgreSQL |
| --- | --- |
| `SUM(CASE WHEN cond THEN amount END)` | `SUM(amount) FILTER (WHERE cond)` |
| `COALESCE(SUM(CASE WHEN cond THEN amount END),0)` | `COALESCE(SUM(amount) FILTER (WHERE cond),0)` |
| `COUNT(CASE WHEN cond THEN 1 END)` | `COUNT(*) FILTER (WHERE cond)` |
| `COUNT(DISTINCT CASE WHEN cond THEN id END)` | `COUNT(DISTINCT id) FILTER (WHERE cond)` |
| `AVG(CASE WHEN cond THEN amount END)` | `AVG(amount) FILTER (WHERE cond)` |

**Không mặc định `FILTER` có trên tất cả DBMS.** SQLite cũng hỗ trợ aggregate `FILTER` từ một số phiên bản hiện đại; MySQL/MariaDB và SQL Server thường dùng `CASE` cho bài toán tương ứng. Nếu cần viết SQL có thể chuyển hệ, `CASE WHEN` thường là lựa chọn quen thuộc hơn.

### Khi FILTER và CASE khác nhau về NULL

`SUM(CASE WHEN cond THEN amount ELSE 0 END)` trên nhóm có dòng có thể trả 0 khi không có dòng phù hợp; `SUM(amount) FILTER (WHERE cond)` thường trả `NULL` khi không có giá trị phù hợp. Muốn hiển thị 0, dùng `COALESCE` với `FILTER` như truy vấn trên. Không đổi cơ học hai cú pháp mà bỏ qua sự khác biệt này.

## 14. Pivot theo hai chiều: GROUP BY nhiều khóa

Có thể tạo một dòng cho mỗi **khu vực và năm**, rồi cột là các kênh:

```sql
SELECT
    region_code,
    EXTRACT(YEAR FROM sold_on)::int AS sale_year,
    SUM(CASE WHEN channel = 'ONLINE' THEN amount ELSE 0 END)
        AS online_amount,
    SUM(CASE WHEN channel = 'STORE' THEN amount ELSE 0 END)
        AS store_amount
FROM sql256_sales
WHERE status = 'PAID'
GROUP BY region_code, EXTRACT(YEAR FROM sold_on)
ORDER BY region_code, sale_year;
```

Ở bộ dữ liệu mẫu chỉ có năm 2026, nhưng khi thêm năm mới, mỗi khu vực có thể xuất hiện nhiều dòng, mỗi năm một dòng.

Nếu đồng thời nhóm theo `region_code, channel`:

```sql
GROUP BY region_code, channel
```

thì mỗi kênh trở thành **một hàng riêng** trong từng khu vực, làm mất mục tiêu “một dòng mỗi khu vực” khi pivot kênh. Các cột trong `GROUP BY` chính là **khóa của một hàng báo cáo**. Cần chọn chúng theo câu hỏi nghiệp vụ, không sao chép tùy ý tất cả cột có trong `SELECT` nguồn.

### Nhiều cột pivot có thể tạo từ tổ hợp điều kiện

Muốn hai cột **ONLINE đã thanh toán trong tháng 1** và **ONLINE đã thanh toán trong tháng 2**:

```sql
SELECT
    region_code,
    SUM(CASE
          WHEN status = 'PAID'
           AND channel = 'ONLINE'
           AND sold_on >= DATE '2026-01-01'
           AND sold_on < DATE '2026-02-01'
          THEN amount ELSE 0
        END) AS jan_online_amount,
    SUM(CASE
          WHEN status = 'PAID'
           AND channel = 'ONLINE'
           AND sold_on >= DATE '2026-02-01'
           AND sold_on < DATE '2026-03-01'
          THEN amount ELSE 0
        END) AS feb_online_amount
FROM sql256_sales
GROUP BY region_code;
```

Đây vẫn là conditional aggregation. Một cột pivot có thể có **nhiều điều kiện** bằng `AND`, miễn mỗi điều kiện phản ánh đúng định nghĩa chỉ tiêu.

## 15. JOIN nhân dòng: nguy cơ cộng doanh thu nhiều lần

Giả sử một dòng bán hàng được JOIN với bảng ghi chú và có nhiều ghi chú cho một giao dịch:

```sql
-- MẪU CÓ NGUY CƠ ĐẾM SAI: nếu mỗi sale có nhiều notes.
SELECT
    s.region_code,
    SUM(CASE WHEN s.channel = 'ONLINE'
             THEN s.amount ELSE 0 END) AS online_amount
FROM sales AS s
JOIN sale_notes AS n ON n.sale_id = s.sale_id
GROUP BY s.region_code;
```

Nếu một sale ONLINE số tiền 100 có **ba ghi chú**, JOIN tạo **ba dòng** tương ứng, và `SUM` có thể cộng 100 **ba lần**. Conditional aggregation chỉ cộng những dòng mà nó nhận được; nó không tự nhận biết một sale bị lặp do JOIN.

Các cách xử lý:

1. Nếu chỉ cần lọc “giao dịch **có ít nhất một ghi chú**”, dùng `EXISTS` để giữ **mỗi sale một lần**.
2. Nếu cần doanh thu và số ghi chú, tổng hợp ghi chú **riêng theo sale_id** trước, rồi JOIN kết quả một-dòng-mỗi-sale.
3. Nếu bảng JOIN một-một, khai báo/kiểm tra `UNIQUE` để bảo đảm không nhân dòng.
4. Kiểm tra `COUNT(*)` so với `COUNT(DISTINCT s.sale_id)` sau JOIN để phát hiện nhân dòng bất ngờ.

Ví dụ ý tưởng với `EXISTS`:

```sql
-- Chỉ chạy nếu có bảng sales/sale_notes theo cấu trúc tương ứng.
SELECT
    s.region_code,
    SUM(CASE WHEN s.channel = 'ONLINE' THEN s.amount ELSE 0 END)
        AS online_amount
FROM sales AS s
WHERE EXISTS (
    SELECT 1
    FROM sale_notes AS n
    WHERE n.sale_id = s.sale_id
)
GROUP BY s.region_code;
```

`EXISTS` chỉ xét điều kiện có tồn tại; nó không nhân dòng `sales` theo số ghi chú.

**Không “sửa” bằng `SUM(DISTINCT s.amount)` một cách tùy tiện.** Hai giao dịch độc lập có cùng số tiền 100 vẫn cần được cộng thành 200; `SUM(DISTINCT amount)` có thể gộp thành 100, gây thiếu doanh thu.

## 16. Pivot theo giá trị không có trong danh sách cột

Static pivot chỉ biết các loại đã được liệt kê:

```sql
SUM(CASE WHEN channel = 'ONLINE' THEN amount ELSE 0 END) AS online_amount,
SUM(CASE WHEN channel = 'STORE' THEN amount ELSE 0 END) AS store_amount,
SUM(CASE WHEN channel = 'PARTNER' THEN amount ELSE 0 END) AS partner_amount
```

Nếu xuất hiện kênh mới `APP`, nó **không tự thành một cột `app_amount`**. Muốn giữ khả năng đối soát tổng, có thể thêm cột khác:

```sql
SELECT
    region_code,
    SUM(CASE WHEN channel = 'ONLINE' THEN amount ELSE 0 END)
        AS online_amount,
    SUM(CASE WHEN channel = 'STORE' THEN amount ELSE 0 END)
        AS store_amount,
    SUM(CASE WHEN channel = 'PARTNER' THEN amount ELSE 0 END)
        AS partner_amount,
    SUM(CASE WHEN channel NOT IN ('ONLINE','STORE','PARTNER')
             THEN amount ELSE 0 END) AS other_amount,
    SUM(amount) AS total_amount
FROM sql256_sales
WHERE status = 'PAID'
GROUP BY region_code;
```

Với bảng thực hành, `other_amount = 0`. Trong hệ thật, nếu `channel` có thể `NULL` và cần coi đó là “loại khác”, bổ sung điều kiện `OR channel IS NULL`; bởi `NULL NOT IN (...)` trả UNKNOWN chứ không trả TRUE.

### Kiểm tra tổng các cột

Nếu các điều kiện kênh **loại trừ nhau và phủ hết giá trị hợp lệ**, kỳ vọng:

```text
online_amount + store_amount + partner_amount + other_amount
= total_amount
```

Nếu không bằng nhau, kiểm tra kênh không được phân loại, `NULL`, các trường hợp số tiền thiếu, logic điều kiện bị chồng lên nhau hoặc JOIN gây nhân dòng. Kiểm tra này hữu ích khi sản phẩm mở rộng số loại theo thời gian.

## 17. Dynamic pivot: khi danh sách cột biến động

Khi bảng có hàng trăm kênh/nhãn và người dùng được phép chọn bộ cột, viết tay:

```sql
SUM(CASE WHEN channel = 'A' THEN amount ELSE 0 END) AS a,
SUM(CASE WHEN channel = 'B' THEN amount ELSE 0 END) AS b,
...
```

không còn thuận tiện.

**Dynamic pivot** là quá trình xác định danh sách giá trị phân loại trước, sau đó **tạo cấu trúc SQL với số cột thay đổi**. Khác với giá trị của `WHERE`, **tên cột kết quả là một phần của cú pháp SQL** và thường không thể được thay thế bằng một placeholder `?` theo cách bind parameter thông thường.

Một quy trình an toàn:

1. Lấy các kênh hợp lệ từ **bảng danh mục/allowlist đáng tin cậy**, hoặc từ truy vấn `SELECT DISTINCT channel` đã kiểm soát.
2. Xác định giới hạn số cột và độ dài câu SQL.
3. Sinh mỗi biểu thức tổng hợp với **tên alias đã được làm sạch/quote đúng dialect**.
4. Bind mọi giá trị dữ liệu bằng **prepared statement** khi có thể.
5. Không nối trực tiếp chuỗi kênh do người dùng cung cấp vào tên cột, điều kiện hay toàn bộ SQL nếu không xử lý an toàn.
6. Giữ quy tắc thứ tự cột và schema đầu ra rõ ràng với client.

Với API có schema cố định, đôi khi giữ kết quả **dạng dài** sẽ thuận tiện hơn:

```sql
SELECT
    region_code,
    channel,
    SUM(amount) AS paid_amount
FROM sql256_sales
WHERE status = 'PAID'
GROUP BY region_code, channel
ORDER BY region_code, channel;
```

Frontend hoặc thư viện báo cáo có thể pivot kết quả dài thành bảng rộng theo danh sách cột động, trong khi SQL vẫn có **ba cột ổn định**: `region_code`, `channel`, `paid_amount`.

**Lựa chọn giữa static pivot và dynamic pivot là quyết định thiết kế giao diện dữ liệu**, không chỉ quyết định cú pháp SQL.

## 18. PIVOT native và khác biệt giữa các DBMS

Conditional aggregation bằng `CASE` là phương án dễ chuyển hệ. Một số DBMS còn có cú pháp riêng như `PIVOT`.

| DBMS | Cách thường dùng | Lưu ý |
| --- | --- | --- |
| **PostgreSQL** | `SUM(CASE ...)`, `FILTER (WHERE ...)`; có extension `tablefunc/crosstab` khi phù hợp | `crosstab` có yêu cầu về danh mục cột và kiểu kết quả; không phải cú pháp `PIVOT` chuẩn dùng ngay |
| **MySQL/MariaDB** | `SUM(CASE ...)`, `COUNT(CASE ...)` | Không giả định có toán tử `PIVOT` native giống SQL Server |
| **SQL Server** | `CASE` hoặc `PIVOT` | `PIVOT` cần liệt kê tên giá trị thành cột trong `IN (...)` |
| **SQLite** | `CASE`; aggregate `FILTER` trên phiên bản hỗ trợ | Không mặc định hỗ trợ cú pháp `PIVOT` như SQL Server; extension/giải pháp ngoài là tùy cài đặt |
| **Oracle Database** | `CASE` hoặc `PIVOT` | Cú pháp và cách đặt alias giá trị pivot theo Oracle; không giống hệt SQL Server |

### SQL Server: PIVOT native

Ví dụ với bảng có cột `region_code`, `channel`, `amount`, `status`:

```sql
-- SQL Server:
SELECT
    p.region_code,
    COALESCE(p.[ONLINE], 0) AS online_amount,
    COALESCE(p.[STORE], 0) AS store_amount,
    COALESCE(p.[PARTNER], 0) AS partner_amount
FROM (
    SELECT region_code, channel, amount
    FROM dbo.sales
    WHERE status = 'PAID'
) AS src
PIVOT (
    SUM(amount)
    FOR channel IN ([ONLINE], [STORE], [PARTNER])
) AS p
ORDER BY p.region_code;
```

Các tên trong `IN` là **cột kết quả do PIVOT tạo**, không phải chuỗi bind parameter thông thường. Subquery `src` chỉ giữ những cột thật sự cần cho pivot; nếu giữ thêm những cột chi tiết không mong muốn, SQL Server `PIVOT` có thể tạo nhóm khác với ý định.

### Oracle Database: PIVOT native

Ví dụ Oracle theo cùng ý tưởng:

```sql
-- Oracle Database:
SELECT
    region_code,
    NVL(online_amount, 0) AS online_amount,
    NVL(store_amount, 0) AS store_amount,
    NVL(partner_amount, 0) AS partner_amount
FROM (
    SELECT region_code, channel, amount
    FROM sales
    WHERE status = 'PAID'
)
PIVOT (
    SUM(amount)
    FOR channel IN (
        'ONLINE' AS online_amount,
        'STORE' AS store_amount,
        'PARTNER' AS partner_amount
    )
)
ORDER BY region_code;
```

`NVL` là hàm thay thế `NULL` quen thuộc của Oracle. Khi chuyển sang PostgreSQL/MySQL/SQL Server, dùng `COALESCE` nếu phù hợp. Cú pháp tên cột của Oracle sau `PIVOT` cần kiểm tra thực tế trên phiên bản dự án sử dụng.

### Không chỉ vì ngắn hơn mà PIVOT luôn tốt hơn CASE

Các điều kiện bổ sung như `status='PAID'`, theo khoảng tháng, đếm người mua khác nhau hay bổ sung cột OTHER có thể khiến `SUM(CASE ...)` dễ đọc và linh hoạt hơn. `PIVOT` native có thể thuận tiện cho bảng chéo cố định nhưng tính hỗ trợ, khả năng tối ưu và tên cột thay đổi theo dialect.

Đặc biệt, một truy vấn được thiết kế để chạy trên **nhiều DBMS** thường ưu tiên conditional aggregation thay vì cú pháp PIVOT riêng.

## 19. Hiệu năng: số nhóm, số cột, bộ lọc và index

Conditional aggregation vẫn là phép tổng hợp. DBMS phải đọc các dòng phù hợp, phân vào các nhóm và tính các biểu thức aggregate cho từng nhóm.

Các yếu tố đáng quan tâm:

- **Số dòng đầu vào:** dùng `WHERE` thích hợp để chỉ xét thời gian/trạng thái cần thiết.
- **Số nhóm:** một khu vực khác với một khu vực–khách hàng–ngày; quá nhiều nhóm có thể tăng chi phí hash/sort aggregate.
- **Số cột pivot:** mỗi cột có thêm biểu thức điều kiện cần tính.
- **JOIN:** quan hệ một-nhiều có thể nhân dòng làm số liệu sai và tăng khối lượng dữ liệu.
- **Kiểu dữ liệu:** `NUMERIC/DECIMAL` cho tiền cần precision/scale phù hợp, tránh overflow hoặc sai số.
- **Chỉ mục:** bộ lọc `status`, `sold_on` và `region_code` có thể hưởng lợi từ index phù hợp tùy workload, nhưng không có index “tự tăng tốc mọi SUM(CASE)” trong mọi kế hoạch.
- **Phân bố dữ liệu:** nếu hầu hết giao dịch đều PAID, index `status` đơn lẻ có thể kém chọn lọc; nếu thời gian rất hẹp, index theo ngày có thể hữu ích hơn.

Ví dụ PostgreSQL:

```sql
CREATE INDEX ix_sql256_sales_status_date_region
ON sql256_sales (status, sold_on, region_code);
```

Chỉ tạo index thực hành sau khi xác định chưa có cấu trúc tương đương và hiểu chi phí ghi dữ liệu. Trên bảng học tập 13 dòng, PostgreSQL có thể chọn **sequential scan** thay vì index vì rẻ hơn; điều đó không chứng minh index vô ích với bảng lớn.

Dùng `EXPLAIN`:

```sql
EXPLAIN
SELECT
    region_code,
    SUM(CASE WHEN channel = 'ONLINE' THEN amount ELSE 0 END)
        AS online_amount
FROM sql256_sales
WHERE status = 'PAID'
GROUP BY region_code;
```

`EXPLAIN` của PostgreSQL cho kế hoạch dự kiến. `EXPLAIN (ANALYZE, BUFFERS)` trên truy vấn `SELECT` cho kết quả đo khi thực thi, nên chỉ chạy ở môi trường phù hợp. Không coi **nhiều cột CASE** luôn chậm hơn nhiều câu truy vấn riêng: thường tổng hợp nhiều chỉ tiêu cùng lúc giúp tránh đọc lại nguồn quá nhiều lần, nhưng vẫn cần đo theo workload thật.

## 20. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Kết quả vẫn có nhiều dòng mỗi khu vực | `GROUP BY` chứa cả `channel` hoặc cột chi tiết | Chỉ nhóm theo khóa một dòng báo cáo |
| Một kênh không có dữ liệu trả `NULL` thay vì 0 | `SUM(CASE ... END)`/`FILTER` không có giá trị để cộng | Dùng `COALESCE` nếu số 0 đúng nghiệp vụ |
| Khu vực không có giao dịch biến mất | `GROUP BY` chỉ trên bảng giao dịch hoặc `WHERE` loại dòng sau LEFT JOIN | Lấy danh mục làm bên trái, lọc PAID trong `ON` hoặc CTE |
| Vùng không có sale lại có count = 1 | `COUNT(*)` trên dòng `LEFT JOIN` bổ sung NULL | Dùng `COUNT(s.sale_id)` với khóa không NULL |
| COUNT một kênh bằng tổng tất cả dòng | `COUNT(CASE ... ELSE 0 END)` | `COUNT(CASE ... THEN 1 END)` hoặc `SUM(CASE ... THEN 1 ELSE 0 END)` |
| Trung bình kênh quá thấp | `AVG(CASE ... ELSE 0 END)` đưa dòng kênh khác vào mẫu số | `AVG(CASE ... THEN amount END)` |
| Tổng các cột kênh không bằng tổng chung | Có category ngoài danh sách, giá trị NULL hoặc điều kiện không phủ hết | Thêm OTHER/điều kiện NULL và kiểm tra tính đầy đủ |
| Doanh thu tăng gấp đôi sau JOIN | Một sale ghép nhiều dòng bảng con | Tổng hợp riêng/EXISTS/đảm bảo JOIN một-một |
| `SUM(DISTINCT amount)` làm mất doanh thu | Hai giao dịch thật cùng số tiền bị gộp | Không distinct theo tiền; dùng khóa giao dịch để xử lý lặp |
| Pivot tháng gộp dữ liệu của nhiều năm | Điều kiện chỉ so số tháng | Thêm năm hoặc dùng khoảng ngày đầy đủ |
| `AVG` hoặc `MAX` trả NULL khi không có giao dịch | Không có mẫu thống kê | Giữ NULL khi có ý nghĩa “không xác định”; chỉ COALESCE nếu báo cáo yêu cầu |
| Dynamic pivot gây lỗi/injection | Nối giá trị do người dùng nhập vào identifier/câu SQL | Dùng danh sách cho phép, quote identifier đúng dialect, bind dữ liệu |
| SQL Server PIVOT trả nhiều dòng ngoài ý muốn | Subquery nguồn giữ cột không cần và thay đổi khóa nhóm ngầm | Chỉ SELECT đúng khóa nhóm, category và measure |
| Các DBMS trả khác kiểu tiền/tên cột | Khác kiểu số, collation, alias, cú pháp native PIVOT | CAST rõ ràng và thử trên đúng phiên bản |

## 21. Bài tập thực hành

Các bài dưới đây dùng `sql256_regions` và `sql256_sales` ở mục 7. Giữ bảng cho đến khi làm xong bài tập.

### Bài 1 — Pivot ba kênh

Viết truy vấn cho mỗi `region_code` một dòng với ba cột `online_amount`, `store_amount`, `partner_amount`, chỉ tính `status='PAID'`. Vì sao cần `GROUP BY region_code` mà không nhóm theo `channel`?

### Bài 2 — Hai kiểu đếm có điều kiện

Viết hai biểu thức tương đương để đếm số sale PAID thuộc kênh STORE theo khu vực: một bằng `COUNT(CASE...)`, một bằng `SUM(CASE...)`. Giải thích lỗi nếu viết `COUNT(CASE WHEN ... THEN 1 ELSE 0 END)`.

### Bài 3 — Giữ khu vực Tây

Vì sao câu `SELECT region_code ... FROM sql256_sales WHERE status='PAID' GROUP BY region_code` không có dòng Tây? Viết truy vấn từ `sql256_regions LEFT JOIN sql256_sales` để trả cả Tây với tổng tiền PAID bằng 0.

### Bài 4 — Doanh thu và khách hàng duy nhất

Trên các đơn PAID của vùng Bắc, tính `online_sale_count`, `online_unique_customers`, `online_amount`. Giải thích vì sao số sale và số unique customer khác nhau.

### Bài 5 — Trung bình đúng mẫu số

Trong vùng Bắc, hai giao dịch ONLINE đã thanh toán có tiền 100 và 150, tổng năm giao dịch PAID. Tính kết quả của:

```sql
AVG(CASE WHEN channel = 'ONLINE' THEN amount END)
AVG(CASE WHEN channel = 'ONLINE' THEN amount ELSE 0 END)
```

khi cả hai được dùng với `WHERE status='PAID'`, `GROUP BY region_code`. Cách nào là trung bình **chỉ của sale ONLINE**?

### Bài 6 — Pivot tháng

Viết ba cột tiền PAID của tháng 1, 2, 3 năm 2026 theo khu vực. Vì sao không nên chỉ dùng điều kiện `EXTRACT(MONTH FROM sold_on)=1` nếu dữ liệu có nhiều năm?

### Bài 7 — Lọc trong WHERE và CASE

So sánh hai truy vấn: (A) `WHERE status='PAID'` rồi tổng hợp; (B) giữ mọi sale nhưng `SUM(CASE WHEN status='PAID' THEN amount ELSE 0 END)`. Khu vực nào có thể hiện ở B nhưng biến mất ở A? Chỉ tiêu `COUNT(*)` của hai truy vấn mang ý nghĩa khác nhau thế nào?

### Bài 8 — LEFT JOIN và COUNT

Giải thích tại sao vùng không có sale PAID trong `LEFT JOIN` có thể cho `COUNT(*)=1` nhưng `COUNT(s.sale_id)=0`.

### Bài 9 — Nhiều giao dịch có cùng tiền

Hai sale khác nhau của cùng khách có số tiền đều 100. Khi tính doanh thu, vì sao `SUM(DISTINCT amount)` có thể sai? Cần xác định trùng **giao dịch** như thế nào?

### Bài 10 — Dynamic pivot

Một hệ thống có thể xuất hiện thêm kênh APP mà không báo trước. Đề xuất hai thiết kế: (1) báo cáo cột cố định và có `other_amount`; (2) kết quả dạng dài cho frontend pivot. Nêu ưu/nhược và lưu ý an toàn khi sinh SQL động.

### Bài 11 — SQL Server PIVOT

Mô tả những cột tối thiểu cần có trong subquery nguồn của SQL Server `PIVOT (SUM(amount) FOR channel IN ([ONLINE],[STORE],[PARTNER]))` để mỗi vùng cho một dòng. Vì sao không nên mang thêm `sale_id` trong subquery nguồn nếu không muốn nhóm theo giao dịch?

### Bài 12 — Kiểm tra số liệu tổng

Từ bộ dữ liệu thực hành, tính tổng doanh thu PAID của toàn bộ ba kênh và tổng theo từng kênh. Viết một cách kiểm tra tổng ba cột pivot có bằng `SUM(amount)` trên cùng tập PAID hay không; điều kiện nào khiến phép kiểm tra không còn đúng nếu schema kênh thay đổi?

## 22. Gợi ý đáp án

**Bài 1:**

```sql
SELECT
    region_code,
    SUM(CASE WHEN channel='ONLINE' THEN amount ELSE 0 END) AS online_amount,
    SUM(CASE WHEN channel='STORE' THEN amount ELSE 0 END) AS store_amount,
    SUM(CASE WHEN channel='PARTNER' THEN amount ELSE 0 END) AS partner_amount
FROM sql256_sales
WHERE status='PAID'
GROUP BY region_code
ORDER BY region_code;
```

Nếu nhóm theo `channel`, cùng một vùng lại tách thành nhiều dòng, không còn “một dòng một khu vực”.

**Bài 2:**

```sql
COUNT(CASE WHEN channel='STORE' THEN 1 END)
SUM(CASE WHEN channel='STORE' THEN 1 ELSE 0 END)
```

Dùng sau `WHERE status='PAID'` hoặc đặt điều kiện PAID thêm trong `CASE`. `COUNT(... ELSE 0)` đếm cả dòng không thuộc STORE.

**Bài 3:** Tây không có sale PAID nên không có nhóm trong tập sau `WHERE`. Giải pháp:

```sql
SELECT
    r.region_code,
    COALESCE(SUM(s.amount),0) AS paid_amount,
    COUNT(s.sale_id) AS paid_sale_count
FROM sql256_regions AS r
LEFT JOIN sql256_sales AS s
  ON s.region_code = r.region_code AND s.status = 'PAID'
GROUP BY r.region_code
ORDER BY r.region_code;
```

Tây có `paid_amount=0` và `paid_sale_count=0`.

**Bài 4:** Bắc: `online_sale_count=2`; `online_unique_customers=1`; `online_amount=250`. Sale 1 và sale 3 đều thuộc customer 1.

**Bài 5:** `AVG(CASE ... THEN amount END) = 125`; `AVG(CASE ... THEN amount ELSE 0 END) = 50` với năm sale PAID ở Bắc. Cách đầu đúng nếu mục tiêu là số tiền trung bình **trên các giao dịch ONLINE**.

**Bài 6:** Dùng khoảng ngày của từng tháng, ví dụ `sold_on >= DATE '2026-01-01' AND sold_on < DATE '2026-02-01'` bên trong `CASE`. Kết quả tiền theo `(B,N,T)`: tháng 1 `(300,200,90)`, tháng 2 `(200,0,0)`, tháng 3 `(70,60,30)`. Chỉ lấy MONTH sẽ gộp tháng 1 của nhiều năm.

**Bài 7:** Tây có thể xuất hiện ở B với tổng PAID = 0 vì có một sale CANCELLED, nhưng không xuất hiện ở A. `COUNT(*)` ở A là số sale PAID; ở B nếu không lọc ngoài là số **mọi sale**.

**Bài 8:** `LEFT JOIN` giữ dòng vùng bên trái dù không có sale khớp, tạo một dòng có các cột sale `NULL`; `COUNT(*)` đếm dòng này, `COUNT(s.sale_id)` không đếm giá trị `NULL`.

**Bài 9:** Hai sale hợp lệ cùng tiền 100 phải có doanh thu 200; `SUM(DISTINCT amount)` chỉ cộng giá trị 100 một lần. Muốn deduplicate giao dịch, dùng khóa `sale_id` hoặc khóa sự kiện nghiệp vụ thích hợp rồi xác định chính xác bản ghi trùng.

**Bài 10:** Báo cáo tĩnh cần cập nhật SQL khi thêm kênh mới; `other_amount` giúp giữ được số liệu chưa có cột riêng. Dạng dài dễ mở rộng cho frontend nhưng đòi hỏi UI tự tạo cột. Dynamic SQL cần allowlist, quote identifier, kiểm soát số cột và bind dữ liệu.

**Bài 11:** Chỉ cần `region_code`, `channel` và `amount` trong nguồn PIVOT khi một hàng báo cáo là một vùng. Nếu đưa `sale_id` theo, engine có thể xem ID giao dịch là cột nhóm không xoay, tạo nhiều dòng mỗi vùng.

**Bài 12:** ONLINE = **450**, STORE = **450**, PARTNER = **50**; tổng PAID = **950**. Có thể so tổng từng vùng hoặc toàn hệ:

```sql
WITH p AS (
    SELECT
        region_code,
        SUM(CASE WHEN channel='ONLINE' THEN amount ELSE 0 END) AS online_amt,
        SUM(CASE WHEN channel='STORE' THEN amount ELSE 0 END) AS store_amt,
        SUM(CASE WHEN channel='PARTNER' THEN amount ELSE 0 END) AS partner_amt,
        SUM(amount) AS total_amt
    FROM sql256_sales
    WHERE status='PAID'
    GROUP BY region_code
)
SELECT
    region_code,
    online_amt + store_amt + partner_amt AS pivot_sum,
    total_amt,
    (online_amt + store_amt + partner_amt = total_amt) AS totals_match
FROM p
ORDER BY region_code;
```

Trên dữ liệu đã cho, `totals_match` đều là `TRUE`. Khi có kênh APP hoặc `channel IS NULL` không được tính vào một cột pivot, tổng các cột kênh có thể nhỏ hơn `total_amt`.

## 23. Dọn dữ liệu học tập

Chỉ chạy nếu hai bảng do **chính bạn tạo** trong môi trường thử và không còn cần làm bài:

```sql
DROP TABLE sql256_sales;
DROP TABLE sql256_regions;
```

Bảng sale có khóa ngoại tham chiếu region, nên xóa bảng sale trước. Không dùng `DROP TABLE` trên bảng nghiệp vụ thật hoặc cơ sở dữ liệu dùng chung.

## 24. Kết luận

**Chuyển hàng thành cột bằng tổng hợp có điều kiện** là mẫu truy vấn dựa trên hai ý tưởng: **`GROUP BY` xác định một dòng kết quả**, còn **mỗi `SUM/COUNT/AVG/MAX(CASE WHEN...)` xác định một cột chỉ tiêu**. Kỹ thuật này thuận tiện cho báo cáo doanh thu theo kênh, đếm trạng thái, thống kê tháng, tạo bảng chéo và nhiều nhu cầu pivot tĩnh.

Để báo cáo đúng dữ liệu, hãy kiểm tra: **đơn vị nhóm**, **điều kiện nào nằm trong `WHERE` và điều kiện nào nằm trong `CASE`**, **số 0 có khác với không có dữ liệu hay không**, **LEFT JOIN có giữ nhóm rỗng không**, và **JOIN có nhân dòng giao dịch không**. Khi danh mục giá trị thay đổi liên tục, cân nhắc xuất dạng dài hoặc sinh pivot động an toàn thay vì giả định các cột cố định sẽ tự bao phủ mọi loại mới.

# WHERE, toán tử so sánh và kết hợp AND, OR, NOT trong Oracle SQL

Khi viết câu lệnh `SELECT` trong **Oracle Database**, người lập trình thường không muốn đọc toàn bộ các hàng của một bảng. Thay vào đó, ta cần lọc những bản ghi thỏa mãn quy tắc nghiệp vụ: đơn hàng đã thanh toán, giao dịch lớn hơn một ngưỡng, khách hàng thuộc một khu vực, hoặc những đơn hàng **vừa** có trạng thái phù hợp **vừa** nằm trong khoảng thời gian yêu cầu. Mệnh đề **`WHERE`** chính là nơi biểu diễn các điều kiện lọc đó.

```sql
SELECT order_id, customer_name, amount
FROM orders
WHERE order_status = 'PAID'
  AND amount >= 300;
```

Trong câu lệnh trên, `WHERE` chỉ giữ những hàng mà **cả hai điều kiện** đều đúng: trạng thái bằng `'PAID'` **và** giá trị đơn hàng ít nhất là 300. Để viết các bộ lọc chính xác, cần hiểu toán tử so sánh (`=`, `<>`, `<`, `>`, `<=`, `>=`), toán tử logic (`AND`, `OR`, `NOT`), **thứ tự ưu tiên**, dấu ngoặc và **logic ba giá trị `TRUE`/`FALSE`/`UNKNOWN`** khi có `NULL`.

Bài học tập trung vào cú pháp Oracle SQL, giải thích cách kết hợp điều kiện, minh họa bằng dữ liệu thực hành và chỉ ra những lỗi có thể làm báo cáo trả sai dữ liệu dù SQL vẫn chạy thành công.

## 1. Vị trí của WHERE trong câu SELECT

Một câu truy vấn cơ bản thường có dạng:

```sql
SELECT column_1, column_2, ...
FROM table_name
WHERE search_condition
ORDER BY column_1;
```

- `SELECT`: chỉ ra các cột hoặc biểu thức muốn trả về.
- `FROM`: xác định bảng, view hoặc nguồn dữ liệu.
- **`WHERE`:** lọc từng hàng dựa trên điều kiện logic.
- `ORDER BY`: sắp xếp các hàng kết quả sau khi lọc.

**Nguyên tắc quan trọng:** `WHERE` chỉ giữ hàng mà điều kiện có kết quả **`TRUE`**. Nếu điều kiện là `FALSE` hoặc **`UNKNOWN`** (không xác định, thường do `NULL`), hàng đó không xuất hiện trong kết quả.

```text
                       TABLE ORDERS
                             |
                             v
                   Đánh giá điều kiện WHERE
                             |
                   +---------+---------+
                   |         |         |
                  TRUE     FALSE     UNKNOWN
                   |         |         |
                   v         +---------+
               Giữ hàng         Loại hàng
                   |
                   v
              SELECT / ORDER BY
                   |
                   v
                 Kết quả
```

Không có `WHERE`, một `SELECT` thông thường có thể trả về tất cả hàng mà nguồn truy vấn cho phép. Với bảng lớn, điều này vừa tốn tài nguyên, vừa có thể trả dữ liệu ngoài phạm vi nghiệp vụ. Ngược lại, **lọc đúng về mặt logic không đồng nghĩa truy vấn chắc chắn nhanh**: hiệu năng còn phụ thuộc dữ liệu, index, thống kê và kế hoạch thực thi của Oracle.

## 2. Chuẩn bị dữ liệu minh họa

Các ví dụ tiếp theo dùng bảng giả **`LAB_WHERE_ORDERS`**, không chứa dữ liệu khách hàng thật. Phần DDL/DML này chỉ dành cho schema thực hành Oracle **DEV/TEST** đã có quyền `CREATE TABLE` và quota phù hợp. Trước khi chạy, xác nhận đúng user và PDB:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME')   AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user
FROM dual;
```

### 2.1. Tạo bảng trong schema lab

```sql
CREATE TABLE lab_where_orders (
    order_id       NUMBER PRIMARY KEY,
    customer_name  VARCHAR2(80 CHAR) NOT NULL,
    region_code    VARCHAR2(10 CHAR),
    order_status   VARCHAR2(20 CHAR) NOT NULL,
    amount         NUMBER(12, 2) NOT NULL,
    created_on     DATE NOT NULL,
    is_priority    NUMBER(1) DEFAULT 0 NOT NULL,
    CONSTRAINT ck_lab_where_priority CHECK (is_priority IN (0, 1))
);
```

`REGION_CODE` được phép `NULL` để minh họa logic ba giá trị. `ORDER_STATUS` và `AMOUNT` được khai báo `NOT NULL` để những ví dụ so sánh cơ bản không phải xử lý trường hợp thiếu dữ liệu. Cột `IS_PRIORITY` dùng `NUMBER(1)` với quy ước `1 = có ưu tiên`, `0 = không ưu tiên`; đây là cách lưu cờ tương thích với nhiều phiên bản Oracle, không phải SQL `BOOLEAN` native.

### 2.2. Nạp tám đơn hàng giả

```sql
INSERT ALL
    INTO lab_where_orders VALUES (1, 'An',   'HN',  'NEW',       150,  DATE '2026-11-01', 1)
    INTO lab_where_orders VALUES (2, 'Binh', 'HCM', 'PAID',      350,  DATE '2026-11-02', 0)
    INTO lab_where_orders VALUES (3, 'Chi',  'HN',  'PAID',      500,  DATE '2026-11-03', 1)
    INTO lab_where_orders VALUES (4, 'Dung', 'DN',  'CANCELLED', 120,  DATE '2026-11-04', 0)
    INTO lab_where_orders VALUES (5, 'Em',   NULL,  'NEW',       250,  DATE '2026-11-05', 0)
    INTO lab_where_orders VALUES (6, 'Giang','HCM', 'NEW',      1000,  DATE '2026-11-06', 1)
    INTO lab_where_orders VALUES (7, 'Ha',   'DN',  'PAID',       90,  DATE '2026-11-07', 0)
    INTO lab_where_orders VALUES (8, 'Khanh',NULL,  'PAID',      400,  DATE '2026-11-08', 1)
SELECT 1 FROM dual;

COMMIT;
```

Oracle dùng biểu thức **`DATE 'YYYY-MM-DD'`** để diễn đạt ngày dưới dạng date literal, tránh phụ thuộc định dạng chuỗi ngày mặc định của session. Dữ liệu trên có tám hàng:

| `ORDER_ID` | Khách hàng | Vùng | Trạng thái | `AMOUNT` | Ngày tạo | Ưu tiên |
|---:|---|---|---|---:|---|---:|
| 1 | An | HN | NEW | 150 | 2026-11-01 | 1 |
| 2 | Binh | HCM | PAID | 350 | 2026-11-02 | 0 |
| 3 | Chi | HN | PAID | 500 | 2026-11-03 | 1 |
| 4 | Dung | DN | CANCELLED | 120 | 2026-11-04 | 0 |
| 5 | Em | `NULL` | NEW | 250 | 2026-11-05 | 0 |
| 6 | Giang | HCM | NEW | 1000 | 2026-11-06 | 1 |
| 7 | Ha | DN | PAID | 90 | 2026-11-07 | 0 |
| 8 | Khanh | `NULL` | PAID | 400 | 2026-11-08 | 1 |

Từ đây, những câu lệnh `SELECT` trong bài có thể thực hành trên chính bảng `LAB_WHERE_ORDERS`. Những ví dụ tham chiếu bảng khác sẽ được ghi rõ là ví dụ khái niệm.

## 3. Sáu toán tử so sánh thông dụng

Oracle SQL hỗ trợ các toán tử so sánh để tạo điều kiện trong `WHERE`:

| Toán tử | Ý nghĩa | Ví dụ | Điều kiện cần thỏa |
|---|---|---|---|
| `=` | Bằng | `order_status = 'PAID'` | Trạng thái bằng PAID |
| `<>` | Khác | `order_status <> 'CANCELLED'` | Trạng thái không bằng CANCELLED |
| `!=` | Khác (cách viết Oracle hỗ trợ) | `amount != 0` | Số tiền khác 0 |
| `>` | Lớn hơn | `amount > 300` | Số tiền lớn hơn 300, không gồm 300 |
| `>=` | Lớn hơn hoặc bằng | `amount >= 300` | Số tiền ít nhất 300 |
| `<` | Nhỏ hơn | `amount < 300` | Số tiền dưới 300 |
| `<=` | Nhỏ hơn hoặc bằng | `amount <= 300` | Số tiền tối đa 300 |

Với điều kiện khác nhau, có thể viết `<>`, `!=` hoặc `^=` trong Oracle; **`<>`** là cách phổ biến và dễ nhận biết theo SQL chuẩn. Một dấu bằng `=` dùng để **so sánh giá trị** trong điều kiện, không phải phép gán biến Java. Không viết `==` như trong nhiều ngôn ngữ lập trình:

```sql
-- Đúng:
SELECT order_id FROM lab_where_orders WHERE amount = 500;

-- Không dùng cú pháp kiểu Java/C trong điều kiện SQL:
-- SELECT order_id FROM lab_where_orders WHERE amount == 500;
```

### 3.1. Bằng (`=`) và khác (`<>`)

```sql
SELECT order_id, customer_name, order_status
FROM lab_where_orders
WHERE order_status = 'PAID'
ORDER BY order_id;
```

Kết quả có các đơn **2, 3, 7, 8**, vì chỉ bốn hàng đó có `ORDER_STATUS = 'PAID'`.

```sql
SELECT order_id, order_status
FROM lab_where_orders
WHERE order_status <> 'CANCELLED'
ORDER BY order_id;
```

Câu thứ hai lấy tất cả đơn trừ đơn **4**. Vì `ORDER_STATUS` được khai báo `NOT NULL`, ở đây không có rắc rối `UNKNOWN`. Nhưng với cột nullable như `REGION_CODE`, `<>` không tự bao gồm `NULL`; phần sau sẽ giải thích.

### 3.2. So sánh lớn hơn, nhỏ hơn và ranh giới

```sql
-- Giá trị lớn hơn 350, không gồm 350.
SELECT order_id, amount
FROM lab_where_orders
WHERE amount > 350
ORDER BY amount;
```

Các đơn **8 (400), 3 (500), 6 (1000)** thỏa mãn. Nếu dùng `>= 350`, đơn **2 (350)** được thêm vào. Khi biến một yêu cầu nghiệp vụ thành SQL, sự khác biệt giữa **“lớn hơn”** và **“ít nhất”** có thể ảnh hưởng hóa đơn, ngưỡng phê duyệt hoặc chính sách ưu đãi.

```sql
-- Mức tiền từ 200 đến 500, bao gồm hai đầu mút.
SELECT order_id, amount
FROM lab_where_orders
WHERE amount >= 200
  AND amount <= 500
ORDER BY order_id;
```

Kết quả là đơn **2, 3, 5, 8**. Oracle không dùng chuỗi so sánh kiểu toán học `200 <= amount <= 500`; hãy kết hợp **hai điều kiện bằng `AND`** hoặc dùng `BETWEEN` khi phù hợp.

### 3.3. So sánh ký tự không hoàn toàn giống so sánh số

```sql
SELECT order_id, customer_name
FROM lab_where_orders
WHERE customer_name = 'An';
```

Giá trị `'An'` là **string literal** vì nằm trong dấu nháy đơn. Với so sánh ký tự, kết quả phụ thuộc **kiểu dữ liệu, collation và một số cấu hình so sánh Oracle**. Không được mặc định mọi deployment luôn coi `'An'` bằng `'an'` hoặc luôn khác nhau theo cùng cách. So sánh `CHAR` còn có các quy tắc blank-padding nhất định; `VARCHAR2` có ngữ nghĩa khác.

Nếu nghiệp vụ cần so sánh **không phân biệt chữ hoa/chữ thường**, phải thiết kế rõ (collation, cột chuẩn hóa hoặc biểu thức như `UPPER(customer_name) = 'AN'`) và kiểm thử với ngôn ngữ/ký tự thực tế. Đặt hàm lên cột có thể ảnh hưởng khả năng dùng index thông thường, nên không biến mọi phép so sánh thành `UPPER(...)` một cách máy móc.

### 3.4. So sánh ngày và thời gian

```sql
SELECT order_id, created_on
FROM lab_where_orders
WHERE created_on >= DATE '2026-11-03'
ORDER BY created_on;
```

Kết quả là đơn **3 đến 8**, do các ngày đó bằng hoặc sau ngày 2026-11-03. Kiểu `DATE` của Oracle **bao gồm cả thành phần giờ, phút, giây**, dù các dòng ví dụ lưu thời điểm nửa đêm. Nếu `CREATED_ON` chứa cả giờ, câu:

```sql
WHERE created_on = DATE '2026-11-03'
```

chỉ khớp giá trị đúng **00:00:00** ngày đó, không mặc nhiên khớp tất cả bản ghi từ sáng tới tối. Cách lọc một ngày bằng **khoảng nửa mở** thường rõ hơn:

```sql
SELECT order_id, created_on
FROM lab_where_orders
WHERE created_on >= DATE '2026-11-03'
  AND created_on <  DATE '2026-11-04';
```

Trong ví dụ có dữ liệu ngày nguyên, truy vấn chọn đơn **3**. Nếu bảng chứa cả giờ trong ngày 03/11, nó vẫn chọn đúng tất cả thời điểm trước 00:00 ngày 04/11. Khi làm việc với `TIMESTAMP WITH TIME ZONE`, cần xác định chính sách timezone và dùng tham số có kiểu phù hợp; so sánh khoảng thời gian không nên dựa vào chuỗi ngày không định dạng.

## 4. Toán tử logic AND: mọi điều kiện phải đúng

`AND` kết hợp nhiều điều kiện. Hàng chỉ được giữ lại khi **tất cả điều kiện đều `TRUE`**.

```sql
SELECT order_id, order_status, amount
FROM lab_where_orders
WHERE order_status = 'PAID'
  AND amount >= 300
ORDER BY order_id;
```

Những đơn đã thanh toán là **2, 3, 7, 8**. Trong đó, đơn **2 (350), 3 (500), 8 (400)** đạt ngưỡng 300; đơn **7 (90)** không đạt nên bị loại.

| `ORDER_ID` | `order_status = 'PAID'` | `amount >= 300` | `AND` | Giữ? |
|---:|---|---|---|---|
| 2 | TRUE | TRUE | TRUE | Có |
| 3 | TRUE | TRUE | TRUE | Có |
| 7 | TRUE | FALSE | FALSE | Không |
| 8 | TRUE | TRUE | TRUE | Có |

Một ví dụ có **ba điều kiện cùng phải đúng**:

```sql
SELECT order_id, amount, is_priority
FROM lab_where_orders
WHERE amount >= 300
  AND is_priority = 1
  AND order_status <> 'CANCELLED'
ORDER BY order_id;
```

Kết quả là đơn **3, 6, 8**. Đơn 6 có trạng thái `NEW`, nhưng vẫn hợp lệ vì điều kiện chỉ yêu cầu **không bị hủy**, chứ không bắt buộc `PAID`. Nếu nghiệp vụ thật cần đơn đã thanh toán, phải ghi `order_status = 'PAID'` thay vì `<> 'CANCELLED'`.

### 4.1. Bảng chân trị AND với TRUE/FALSE

| A | B | `A AND B` |
|---|---|---|
| TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE |
| FALSE | TRUE | FALSE |
| FALSE | FALSE | FALSE |

Trong thực tế, SQL còn có `UNKNOWN`; logic ba giá trị sẽ được trình bày riêng. Việc biết `AND` không có nghĩa “điều kiện nào xuất hiện trước thì chắc chắn được đánh giá trước”; Oracle optimizer có thể sắp xếp hoặc biến đổi cách thực hiện predicate.

## 5. Toán tử logic OR: chỉ cần một điều kiện đúng

`OR` giữ một hàng khi **ít nhất một điều kiện `TRUE`**.

```sql
SELECT order_id, region_code, order_status
FROM lab_where_orders
WHERE region_code = 'HN'
   OR order_status = 'NEW'
ORDER BY order_id;
```

Đơn thuộc vùng `HN` là **1, 3**. Đơn trạng thái `NEW` là **1, 5, 6**. Hợp của hai tập là **1, 3, 5, 6**. Đơn 1 đáp ứng cả hai điều kiện nhưng **chỉ xuất hiện một lần** vì mỗi hàng nguồn được xét một lần; `OR` không tự nhân đôi hàng.

| `ORDER_ID` | Vùng HN? | Trạng thái NEW? | `OR` | Kết quả |
|---:|---|---|---|---|
| 1 | TRUE | TRUE | TRUE | Giữ |
| 3 | TRUE | FALSE | TRUE | Giữ |
| 5 | UNKNOWN (`NULL`) | TRUE | TRUE | Giữ |
| 6 | FALSE | TRUE | TRUE | Giữ |
| 8 | UNKNOWN (`NULL`) | FALSE | UNKNOWN | Loại |

Ví dụ này cho thấy **`OR` có thể cho kết quả `TRUE` dù một vế là `UNKNOWN`**, miễn vế còn lại đã là `TRUE`.

### 5.1. OR có khác IN không?

Khi so sánh **cùng một cột** với nhiều giá trị cố định, `IN` thường ngắn gọn hơn:

```sql
SELECT order_id, region_code
FROM lab_where_orders
WHERE region_code = 'HN'
   OR region_code = 'HCM';
```

Có thể viết tương đương trong ngữ cảnh danh sách giá trị không null:

```sql
SELECT order_id, region_code
FROM lab_where_orders
WHERE region_code IN ('HN', 'HCM')
ORDER BY order_id;
```

Kết quả là đơn **1, 2, 3, 6**. Nhưng `IN` không thay thế được mọi `OR`: biểu thức `region_code = 'HN' OR amount >= 500` gồm **hai cột và hai điều kiện khác nhau**, không thể rút gọn thành `region_code IN (...)` mà giữ nguyên ý nghĩa.

### 5.2. Bảng chân trị OR với TRUE/FALSE

| A | B | `A OR B` |
|---|---|---|
| TRUE | TRUE | TRUE |
| TRUE | FALSE | TRUE |
| FALSE | TRUE | TRUE |
| FALSE | FALSE | FALSE |

Trong ứng dụng, `OR` thường diễn đạt **nhiều đường đi hợp lệ**: người dùng là quản trị viên **hoặc** là người tạo đơn hàng; hàng có trạng thái `NEW` **hoặc** `PAID`; bản ghi thuộc nhóm A **hoặc** vượt ngưỡng ưu tiên. Những biểu thức có tính bảo mật phải đặt dấu ngoặc cẩn thận để tránh một nhánh `OR` bỏ qua các điều kiện ràng buộc chung.

## 6. Toán tử NOT: phủ định một điều kiện

`NOT` đảo giá trị logic của điều kiện:

- `NOT TRUE` thành `FALSE`.
- `NOT FALSE` thành `TRUE`.
- `NOT UNKNOWN` vẫn là **`UNKNOWN`**.

```sql
SELECT order_id, order_status
FROM lab_where_orders
WHERE NOT (order_status = 'CANCELLED')
ORDER BY order_id;
```

Vì `ORDER_STATUS NOT NULL`, kết quả tương đương với:

```sql
SELECT order_id, order_status
FROM lab_where_orders
WHERE order_status <> 'CANCELLED'
ORDER BY order_id;
```

Cả hai loại đơn **4**. Dấu ngoặc làm rõ phạm vi của `NOT` và giảm nhầm lẫn khi biểu thức phức tạp.

### 6.1. Phủ định cả một nhóm điều kiện

```sql
SELECT order_id, order_status, amount
FROM lab_where_orders
WHERE NOT (order_status = 'NEW' AND amount < 300)
ORDER BY order_id;
```

Nhóm bị loại là **đơn vừa `NEW` vừa dưới 300**: đơn **1** và **5**. Các đơn còn lại được giữ, kể cả đơn **6** có trạng thái `NEW` nhưng `AMOUNT = 1000`.

Theo **định luật De Morgan** trong logic ba giá trị của SQL, có thể biến đổi biểu thức:

```sql
NOT (A AND B)  tương đương  (NOT A) OR (NOT B)
NOT (A OR B)   tương đương  (NOT A) AND (NOT B)
```

Trong SQL ví dụ:

```sql
WHERE NOT (order_status = 'NEW' AND amount < 300)
```

tương đương về điều kiện logic với:

```sql
WHERE order_status <> 'NEW' OR amount >= 300
```

Do hai cột này `NOT NULL`, kết quả minh họa khá trực quan. Với cột nullable, định luật vẫn giữ theo logic ba giá trị, nhưng **không được bỏ qua trường hợp `UNKNOWN`**.

## 7. Thứ tự ưu tiên: NOT, AND, OR và dấu ngoặc

Oracle đánh giá **toán tử so sánh/điều kiện** để tạo giá trị logic, sau đó áp dụng các toán tử logic theo thứ tự ưu tiên quan trọng:

```text
   Độ ưu tiên cao
          |
     Phép so sánh / điều kiện (ví dụ =, >=, LIKE, IN, ...)
          |
         NOT
          |
         AND
          |
         OR
          |
   Độ ưu tiên thấp
```

**Dấu ngoặc `(...)` có thể nhóm biểu thức để chủ động thay đổi cách kết hợp**, và nên được sử dụng khi một câu `WHERE` vừa có `AND` vừa có `OR`.

### 7.1. Ví dụ khác biệt lớn do thiếu ngoặc

```sql
SELECT order_id, order_status, amount
FROM lab_where_orders
WHERE order_status = 'NEW'
   OR order_status = 'PAID' AND amount >= 400
ORDER BY order_id;
```

Vì `AND` ưu tiên cao hơn `OR`, Oracle hiểu tương đương:

```sql
WHERE order_status = 'NEW'
   OR (order_status = 'PAID' AND amount >= 400)
```

Kết quả là **1, 3, 5, 6, 8**: mọi đơn `NEW` đều được chọn, kể cả đơn 1 (150) và 5 (250); các đơn `PAID` chỉ được chọn nếu đạt 400.

Nếu yêu cầu nghiệp vụ là **đơn `NEW` hoặc `PAID`, nhưng bất kể trạng thái nào cũng phải có `AMOUNT >= 400`**, cần viết:

```sql
SELECT order_id, order_status, amount
FROM lab_where_orders
WHERE (order_status = 'NEW' OR order_status = 'PAID')
  AND amount >= 400
ORDER BY order_id;
```

Kết quả giờ là **3, 6, 8**. Hai truy vấn đều hợp lệ về cú pháp nhưng trả kết quả **khác nhau**. Đây là dạng lỗi nguy hiểm vì có thể âm thầm làm sai báo cáo, phân quyền hoặc tính toán nghiệp vụ.

| `ORDER_ID` | Trạng thái | Số tiền | Không ngoặc | Có ngoặc quanh `NEW OR PAID` |
|---:|---|---:|---|---|
| 1 | NEW | 150 | Giữ | Loại |
| 3 | PAID | 500 | Giữ | Giữ |
| 5 | NEW | 250 | Giữ | Loại |
| 6 | NEW | 1000 | Giữ | Giữ |
| 8 | PAID | 400 | Giữ | Giữ |

### 7.2. Dấu ngoặc để giữ một điều kiện chung

Giả sử hệ thống nhiều tenant cần lọc mọi đơn có `TENANT_ID = :tenant_id` và thuộc một trong hai trạng thái. Mẫu đúng là:

```sql
-- Ví dụ khái niệm: bảng này phải có cột TENANT_ID trên schema thật.
SELECT order_id, order_status
FROM tenant_orders
WHERE tenant_id = :tenant_id
  AND (order_status = 'NEW' OR order_status = 'PAID');
```

Nếu bỏ ngoặc:

```sql
WHERE tenant_id = :tenant_id
  AND order_status = 'NEW'
   OR order_status = 'PAID'
```

điều kiện tương đương `(tenant_id = :tenant_id AND order_status = 'NEW') OR order_status = 'PAID'`. Nó có thể chọn **mọi đơn PAID của tenant khác**. Ở đây lỗi ngoặc không chỉ sai kết quả mà còn có thể thành **lỗi bảo vệ dữ liệu giữa tenant**. Khi dùng RLS/VPD hoặc cơ chế phân quyền database, vẫn phải thiết kế predicate ứng dụng đúng, không xem một điều kiện `OR` thiếu ngoặc là vô hại.

### 7.3. Không dựa vào thứ tự viết để ép Oracle chạy phép kiểm tra trước

Về logic, ta thường đọc từ trái qua phải, nhưng SQL là ngôn ngữ khai báo; **Oracle optimizer có thể biến đổi, đẩy hoặc sắp xếp đánh giá predicate**. Đừng dựa vào “short-circuit” theo thứ tự câu chữ để tránh lỗi chia cho 0:

```sql
-- Không nên giả định điều kiện đầu chắc chắn được đánh giá trước:
-- WHERE denominator <> 0 AND numerator / denominator > 10
```

Nếu cần tránh chia cho 0 trong biểu thức, có thể sử dụng `NULLIF`:

```sql
-- Ví dụ khái niệm trên bảng có NUMERATOR, DENOMINATOR.
SELECT numerator / NULLIF(denominator, 0) AS ratio
FROM lab_ratios
WHERE numerator / NULLIF(denominator, 0) > 10;
```

Khi `DENOMINATOR = 0`, `NULLIF` trả `NULL`; phép chia cho `NULL` cho kết quả `NULL` và điều kiện `> 10` thành `UNKNOWN`, nên hàng không được chọn. Truy vấn này chỉ để minh họa chiến lược an toàn; bảng `LAB_RATIOS` không thuộc dữ liệu lab đã tạo.

## 8. NULL và logic ba giá trị: phần bắt buộc để dùng WHERE đúng

Trong Oracle SQL, `NULL` đại diện cho **giá trị chưa được biết hoặc không được cung cấp**, không phải số 0, chuỗi `'NULL'` hay mặc nhiên là `FALSE`.

Ví dụ bảng lab có hai đơn **5** và **8** chưa biết `REGION_CODE`:

```sql
SELECT order_id, region_code
FROM lab_where_orders
WHERE region_code IS NULL
ORDER BY order_id;
```

Kết quả là **5 và 8**. Trong khi đó:

```sql
SELECT order_id, region_code
FROM lab_where_orders
WHERE region_code = NULL;
```

không trả về hai hàng đó, bởi so sánh `= NULL` cho **`UNKNOWN`**, không phải `TRUE`. Tương tự, `region_code <> NULL` cũng không phải cách lấy tất cả vùng đã có dữ liệu.

### 8.1. `IS NULL` và `IS NOT NULL`

```sql
-- Chọn hàng chưa có mã vùng.
SELECT order_id FROM lab_where_orders
WHERE region_code IS NULL;

-- Chọn hàng đã có mã vùng.
SELECT order_id FROM lab_where_orders
WHERE region_code IS NOT NULL;
```

Kết quả lần lượt là **5, 8** và **1, 2, 3, 4, 6, 7**. Các từ `IS NULL` và `IS NOT NULL` là **điều kiện**, không phải toán tử gán giá trị.

### 8.2. Tại sao `<>` không bao gồm hàng NULL?

```sql
SELECT order_id, region_code
FROM lab_where_orders
WHERE region_code <> 'HN'
ORDER BY order_id;
```

Kết quả: **2, 4, 6, 7**. Những hàng `REGION_CODE = NULL` bị loại, mặc dù trong ngôn ngữ đời thường ta có thể nói “chưa biết vùng thì không phải HN”. Trong SQL, khi chưa biết vùng, Oracle **không thể khẳng định** nó khác `'HN'` hay bằng `'HN'`.

Nếu nghiệp vụ muốn chọn **mọi hàng không ghi nhận là HN**, bao gồm trường hợp chưa có vùng, hãy viết rõ:

```sql
SELECT order_id, region_code
FROM lab_where_orders
WHERE region_code <> 'HN'
   OR region_code IS NULL
ORDER BY order_id;
```

Kết quả là **2, 4, 5, 6, 7, 8**. Câu này có ý nghĩa nghiệp vụ khác câu đầu; không nên tự thêm `OR ... IS NULL` nếu hệ thống thật muốn loại dữ liệu chưa rõ.

### 8.3. Bảng chân trị ba giá trị của AND và OR

| A | B | `A AND B` | `A OR B` |
|---|---|---|---|
| TRUE | TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE | TRUE |
| TRUE | UNKNOWN | UNKNOWN | TRUE |
| FALSE | TRUE | FALSE | TRUE |
| FALSE | FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | TRUE | UNKNOWN | TRUE |
| UNKNOWN | FALSE | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

Trong Oracle, *UNKNOWN* được biểu diễn bởi kết quả logic không xác định do `NULL` trong điều kiện. Cách nhớ:

- `FALSE AND UNKNOWN` vẫn **FALSE**, vì đã biết toàn biểu thức không thể đúng.
- `TRUE OR UNKNOWN` vẫn **TRUE**, vì đã có ít nhất một vế đúng.
- `TRUE AND UNKNOWN` là **UNKNOWN**.
- `FALSE OR UNKNOWN` là **UNKNOWN**.
- `NOT UNKNOWN` vẫn **UNKNOWN**.

### 8.4. `NOT` không biến NULL thành TRUE

```sql
SELECT order_id, region_code
FROM lab_where_orders
WHERE NOT (region_code = 'HN')
ORDER BY order_id;
```

Kết quả giống `region_code <> 'HN'`: **2, 4, 6, 7**. `NOT (NULL = 'HN')` vẫn **UNKNOWN**, không phải TRUE. Nếu muốn bao gồm NULL, phải thêm nhánh `OR region_code IS NULL` hoặc diễn đạt quy tắc nghiệp vụ một cách tương đương.

### 8.5. Chuỗi rỗng trong Oracle

Ở các phiên bản Oracle thông dụng, chuỗi ký tự độ dài 0 (`''`) trong SQL thường được xử lý như `NULL` đối với các kiểu ký tự liên quan. Vì thế với cột `VARCHAR2`, một giá trị đầu vào `''` có thể trở thành `NULL` và không thỏa điều kiện `column = ''` như người mới học kỳ vọng. Muốn tìm giá trị thiếu, dùng `IS NULL` và **định nghĩa rõ dữ liệu trống/không có dữ liệu trong ứng dụng**; không thiết kế nghiệp vụ dựa trên giả định rằng chuỗi rỗng và null luôn được phân biệt trong Oracle.

## 9. Các điều kiện thường đi kèm WHERE: BETWEEN, IN, LIKE

Mặc dù trọng tâm là toán tử so sánh và `AND`/`OR`/`NOT`, Oracle còn cung cấp các **điều kiện tiện ích** thường giúp biểu thức lọc dễ đọc hơn.

### 9.1. BETWEEN: khoảng bao gồm hai đầu mút

```sql
SELECT order_id, amount
FROM lab_where_orders
WHERE amount BETWEEN 200 AND 500
ORDER BY order_id;
```

Với giá trị số không null, điều kiện tương đương:

```sql
WHERE amount >= 200 AND amount <= 500
```

Kết quả: **2, 3, 5, 8**. **`BETWEEN` bao gồm cả hai đầu mút**: đơn 3 có `AMOUNT = 500` vẫn được chọn. Với `DATE` có giờ, `BETWEEN DATE '2026-11-01' AND DATE '2026-11-30'` chỉ bao gồm thời điểm **00:00:00** ngày 30/11 ở cận trên, không phải cả ngày; vì thế lọc khoảng ngày thường nên dùng `>= start AND < next_day` để tránh mất hàng ở phần cuối ngày.

### 9.2. IN: một giá trị thuộc tập lựa chọn

```sql
SELECT order_id, order_status
FROM lab_where_orders
WHERE order_status IN ('NEW', 'PAID')
ORDER BY order_id;
```

Kết quả là tất cả đơn trừ đơn **4** (`CANCELLED`). Câu này tương đương với:

```sql
WHERE order_status = 'NEW' OR order_status = 'PAID'
```

trong dữ liệu mẫu không null. Nếu kết hợp thêm các điều kiện khác, viết:

```sql
SELECT order_id, amount
FROM lab_where_orders
WHERE order_status IN ('NEW', 'PAID')
  AND amount >= 400
ORDER BY order_id;
```

Kết quả **3, 6, 8**. Việc dùng `IN` làm rõ nhóm trạng thái và tránh phải lặp nhiều vế `OR` trên cùng cột.

### 9.3. NOT IN và bẫy NULL

```sql
SELECT order_id, order_status
FROM lab_where_orders
WHERE order_status NOT IN ('CANCELLED')
ORDER BY order_id;
```

Vì danh sách không chứa `NULL` và `ORDER_STATUS` không null, câu này lấy tất cả đơn trừ đơn **4**. Tuy nhiên:

```sql
-- Không dùng như cách loại một trạng thái trong dữ liệu thực:
SELECT order_id
FROM lab_where_orders
WHERE order_status NOT IN ('CANCELLED', NULL);
```

**không trả về hàng nào trong dữ liệu mẫu**. Giải thích: `x NOT IN (a, NULL)` về logic tương đương `x <> a AND x <> NULL`. Khi `x <> a` là TRUE, vế còn lại vẫn UNKNOWN, toàn điều kiện UNKNOWN; khi `x = a`, toàn điều kiện FALSE. Không hàng nào cho kết quả TRUE.

Bẫy đặc biệt nguy hiểm khi `NOT IN` dùng **subquery có thể trả về NULL**:

```sql
-- Ví dụ khái niệm: bảng EXCLUDED_CUSTOMERS không nằm trong lab.
SELECT customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT e.customer_id
    FROM excluded_customers e
);
```

Nếu subquery có một giá trị `NULL`, kết quả có thể bị loại ngoài dự kiến. Có thể lọc `WHERE e.customer_id IS NOT NULL` trong subquery nếu đúng nghiệp vụ, hoặc cân nhắc **`NOT EXISTS`** với phép nối tương quan được định nghĩa rõ. `NOT EXISTS` có ngữ nghĩa kiểm tra tồn tại khác `NOT IN`, nhất là khi khóa có thể null; cần xét dữ liệu và mục đích trước khi thay.

### 9.4. LIKE: tìm theo mẫu ký tự

```sql
SELECT order_id, customer_name
FROM lab_where_orders
WHERE customer_name LIKE 'G%';
```

Trong dữ liệu mẫu, câu này tìm **Giang (đơn 6)** theo mẫu bắt đầu bằng `G`. Hai ký tự đại diện thường dùng:

- `%`: chuỗi có độ dài bằng 0 hoặc nhiều ký tự.
- `_`: **một** ký tự.

Ví dụ:

```sql
WHERE customer_name LIKE 'A%'   -- tên bắt đầu bằng A
WHERE customer_name LIKE '_a%'  -- ký tự thứ hai là a
WHERE customer_name NOT LIKE 'G%' -- tên không phù hợp mẫu G%
```

Với một cột nullable, `NOT LIKE` cũng có thể trả UNKNOWN nếu giá trị là NULL. Dấu `%` và `_` là wildcard trong `LIKE`; nếu muốn tìm ký tự `%` hoặc `_` **theo nghĩa đen**, dùng mệnh đề `ESCAPE` theo cú pháp Oracle:

```sql
-- Ví dụ khái niệm trên bảng sản phẩm có cột PRODUCT_CODE.
SELECT product_code
FROM lab_products
WHERE product_code LIKE 'AB\_%' ESCAPE '\';
```

Mẫu này tìm mã bắt đầu bằng ký tự `AB_` theo nghĩa đen, rồi bất kỳ phần tiếp theo. Kết quả phụ thuộc collation và dữ liệu thực tế; bảng `LAB_PRODUCTS` không thuộc bộ dữ liệu được tạo ở phần 2.

## 10. Đặt AND, OR, NOT vào những bài toán nghiệp vụ thực tế

### 10.1. Đơn cần xử lý ưu tiên

Yêu cầu: “Lấy đơn hàng ở vùng HCM **và** (là đơn ưu tiên **hoặc** có giá trị ít nhất 500).”

```sql
SELECT order_id, region_code, amount, is_priority
FROM lab_where_orders
WHERE region_code = 'HCM'
  AND (is_priority = 1 OR amount >= 500)
ORDER BY order_id;
```

Trong mẫu, vùng HCM có đơn 2 và 6. Đơn 2 không ưu tiên và chỉ 350 nên bị loại; đơn **6** được giữ vì vừa ở HCM vừa có mức tiền 1000 và `IS_PRIORITY = 1`. Đây là biểu thức đúng cấu trúc **`A AND (B OR C)`**.

### 10.2. Đơn chưa bị hủy và đã đủ ngưỡng

```sql
SELECT order_id, order_status, amount
FROM lab_where_orders
WHERE order_status <> 'CANCELLED'
  AND amount >= 250
ORDER BY order_id;
```

Kết quả là đơn **2, 3, 5, 6, 8**. Cách diễn đạt `<> 'CANCELLED'` có thể giữ nhiều trạng thái khác ngoài `NEW`/`PAID` nếu hệ thống sau này thêm `REFUNDED`, `SUSPENDED` hoặc trạng thái khác. Nếu nghiệp vụ chỉ cho phép hai trạng thái, dùng **`IN ('NEW', 'PAID')`** thay vì phủ định một trạng thái duy nhất.

### 10.3. Danh sách cần xác minh vùng hoặc đơn chưa thanh toán

Yêu cầu: “Tìm đơn thiếu mã vùng **hoặc** còn `NEW`.”

```sql
SELECT order_id, region_code, order_status
FROM lab_where_orders
WHERE region_code IS NULL
   OR order_status = 'NEW'
ORDER BY order_id;
```

Kết quả **1, 5, 6, 8**. Đơn 5 thỏa cả hai nhánh nhưng chỉ xuất hiện một lần, đơn 8 được giữ vì thiếu mã vùng dù trạng thái là PAID.

### 10.4. Chọn đơn trong thời gian và trạng thái phù hợp

```sql
SELECT order_id, created_on, order_status, amount
FROM lab_where_orders
WHERE created_on >= DATE '2026-11-03'
  AND created_on <  DATE '2026-11-08'
  AND order_status IN ('NEW', 'PAID')
ORDER BY created_on;
```

Trong dữ liệu mẫu, khoảng này chứa ngày **03/11 đến trước 08/11**. Đơn 4 bị loại vì CANCELLED. Kết quả là **3, 5, 6, 7**. Điều kiện nửa mở giúp truy vấn vẫn đúng nếu một ngày có nhiều thời điểm khác nhau.

## 11. WHERE với tham số bind trong Java/JDBC

Trong ứng dụng Java, các ngưỡng lọc thường đến từ request hoặc màn hình tìm kiếm. Không nối trực tiếp giá trị người dùng vào chuỗi SQL; hãy sử dụng **bind parameters** (`?` trong JDBC hoặc `:name` ở một số công cụ/framework) để giữ tách biệt **dữ liệu** và **cú pháp SQL**, hỗ trợ tái sử dụng cursor và giảm nguy cơ SQL injection.

### 11.1. PreparedStatement với AND

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class OrderSearch {
    public static void printPaidOrders(Connection connection,
                                       BigDecimal minAmount) throws SQLException {
        String sql = """
            SELECT order_id, customer_name, amount
            FROM lab_where_orders
            WHERE order_status = ?
              AND amount >= ?
            ORDER BY order_id
            """;

        try (PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setString(1, "PAID");
            statement.setBigDecimal(2, minAmount);

            try (ResultSet result = statement.executeQuery()) {
                while (result.next()) {
                    System.out.printf("Order %d: %s, %s%n",
                        result.getLong("order_id"),
                        result.getString("customer_name"),
                        result.getBigDecimal("amount"));
                }
            }
        }
    }
}
```

Ví dụ dùng **Java text block** (Java 15 trở lên) và JDBC driver Oracle phù hợp. Trên phiên bản Java cũ, có thể tạo chuỗi bằng phép nối các **đoạn SQL cố định**, nhưng vẫn giữ giá trị người dùng dưới dạng bind. `BigDecimal` phù hợp hơn việc dùng số dấu phẩy động nhị phân cho số tiền cần độ chính xác thập phân.

### 11.2. Tham số tùy chọn và các điều kiện động

Giả sử API cho phép tìm đơn theo `minAmount` hoặc theo `regionCode`, và hai bộ lọc đều tùy chọn. Có hai hướng thường gặp:

1. **Xây dựng SQL có điều kiện**, chỉ thêm predicate khi tham số được cung cấp, còn giá trị luôn bind; quản lý thứ tự placeholder cẩn thận.
2. Dùng predicate tùy chọn như `(:region IS NULL OR region_code = :region)` nếu framework hỗ trợ named bind và đã kiểm tra execution plan; cách này tiện nhưng không phải lúc nào cũng tối ưu hiệu năng.

Ví dụ Oracle SQL mang tính khái niệm:

```sql
SELECT order_id, region_code, amount
FROM lab_where_orders
WHERE (:min_amount IS NULL OR amount >= :min_amount)
  AND (:region IS NULL OR region_code = :region)
ORDER BY order_id;
```

**Lưu ý:** khi `:region` là `NULL`, điều kiện thứ hai được dùng như “không áp bộ lọc vùng”, nên bao gồm cả những hàng `REGION_CODE IS NULL`. Nó **khác** yêu cầu “chỉ tìm đơn có vùng NULL”. Cần quy ước API để phân biệt **tham số không được cung cấp** và **người dùng muốn tìm trường đang trống**.

Không thể dùng bind parameter để thay trực tiếp tên cột hoặc từ khóa `ORDER BY` như một identifier SQL. Nếu người dùng chọn cột sắp xếp, ứng dụng phải ánh xạ các lựa chọn cho phép sang tên cột SQL **đã được kiểm soát**, không nối dữ liệu tùy ý vào truy vấn.

### 11.3. Cú pháp bind trong SQL client khác JDBC

Trong SQL*Plus/SQLcl, bạn có thể khai báo bind variable theo cơ chế của client; trong JDBC `PreparedStatement`, placeholder thường là `?`. Nhiều framework Java như Spring JDBC cho phép named parameters (`:minAmount`). Cú pháp placeholder là **giao diện của client/framework**, trong khi ngữ nghĩa `AND`, `OR`, `NOT`, `NULL` vẫn do Oracle SQL quyết định.

## 12. WHERE, JOIN và HAVING: những chỗ dễ đặt nhầm điều kiện

### 12.1. WHERE lọc hàng; HAVING lọc nhóm

```sql
SELECT order_status, COUNT(*) AS order_count
FROM lab_where_orders
WHERE amount >= 100
GROUP BY order_status
HAVING COUNT(*) >= 2
ORDER BY order_status;
```

Truy vấn này dùng `WHERE` để bỏ những đơn có số tiền dưới 100 **trước khi** tạo nhóm theo trạng thái, rồi dùng `HAVING` để chỉ giữ những nhóm có ít nhất hai hàng. Trong dữ liệu mẫu, đơn 7 (90) không được tính vào các nhóm. Không dùng `WHERE COUNT(*) >= 2` như điều kiện lọc từng hàng; biểu thức tổng hợp cần được dùng đúng ngữ cảnh, thường là `HAVING`.

### 12.2. WHERE khác điều kiện ON của OUTER JOIN

Giả sử `CUSTOMERS` và `ORDERS` là hai bảng nghiệp vụ, cần lấy mọi khách hàng, kể cả khách chưa có đơn trả tiền. Với `LEFT JOIN`, đặt điều kiện trạng thái ở `ON` khác với đặt ở `WHERE`:

```sql
-- Ví dụ khái niệm với các bảng CUSTOMERS và ORDERS được tạo sẵn.
SELECT c.customer_id, o.order_id
FROM customers c
LEFT JOIN orders o
  ON o.customer_id = c.customer_id
 AND o.order_status = 'PAID';
```

Đoạn trên vẫn giữ khách hàng không có đơn `PAID`, với cột của `o` là `NULL`. Nhưng:

```sql
SELECT c.customer_id, o.order_id
FROM customers c
LEFT JOIN orders o
  ON o.customer_id = c.customer_id
WHERE o.order_status = 'PAID';
```

sẽ loại hàng có `o.order_status = NULL` do không match bên phải. Với điều kiện này, kết quả giống hướng lọc các khách đã có đơn PAID hơn là giữ mọi khách hàng. Khi chuyển predicate giữa `ON` và `WHERE`, cần xét loại JOIN và `NULL`, không chỉ xem cú pháp có chạy được hay không.

### 12.3. Alias trong SELECT chưa dùng được tùy ý tại WHERE

Ví dụ:

```sql
SELECT amount * 1.1 AS adjusted_amount
FROM lab_where_orders
WHERE amount > 300;
```

Ở Oracle SQL thông dụng, không thể giả định alias `ADJUSTED_AMOUNT` vừa khai báo trong danh sách `SELECT` sẽ dùng được ngay trong cùng mệnh đề `WHERE`. Muốn lọc theo biểu thức, có thể lặp biểu thức khi phù hợp hoặc đặt trong một **subquery/CTE**, sau đó lọc ở truy vấn ngoài:

```sql
SELECT order_id, adjusted_amount
FROM (
    SELECT order_id, amount * 1.1 AS adjusted_amount
    FROM lab_where_orders
)
WHERE adjusted_amount > 300;
```

Việc nhân `1.1` ở đây chỉ minh họa alias/biểu thức; với tính tiền thật cần áp dụng đúng đơn vị, thuế và quy tắc làm tròn nghiệp vụ.

## 13. Ảnh hưởng đến hiệu năng khi kết hợp nhiều điều kiện

`WHERE` chỉ mô tả **bản ghi nào được chọn**, không ra lệnh Oracle phải dùng một thuật toán vật lý cố định. Optimizer có thể chọn full table scan, index range scan, index unique scan, kết hợp điều kiện hoặc biến đổi biểu thức tùy statistics, kích thước bảng, index và tham số. Một câu SQL hợp logic vẫn có thể tốn CPU/I/O nếu không có đường truy cập thích hợp.

### 13.1. Predicate thường có thể tận dụng index

Giả sử có index phù hợp trên `CREATED_ON`:

```sql
SELECT order_id, created_on
FROM lab_where_orders
WHERE created_on >= DATE '2026-11-01'
  AND created_on <  DATE '2026-12-01';
```

Điều kiện khoảng trên **cột gốc** thường tạo cơ hội cho Oracle dùng index theo range scan nếu optimizer thấy có lợi. Trong khi đó:

```sql
-- Có thể làm khó khả năng dùng B-tree index thông thường trên CREATED_ON:
SELECT order_id
FROM lab_where_orders
WHERE TRUNC(created_on) = DATE '2026-11-03';
```

đặt hàm `TRUNC` lên cột, làm thay đổi dạng predicate. Oracle có thể dùng **function-based index** hoặc biến đổi phù hợp trong một số điều kiện, nhưng **không mặc định** index thường trên `CREATED_ON` sẽ được dùng như khi lọc bằng khoảng nửa mở. Với bài toán theo ngày, viết điều kiện `>= start AND < next_day` thường dễ theo dõi và thân thiện với nhiều phương án index.

### 13.2. OR có thể phức tạp hơn AND về đường truy cập

```sql
WHERE region_code = 'HN' OR order_status = 'NEW'
```

Hai nhánh có thể phù hợp với các index khác nhau. Oracle có thể chọn full scan, OR expansion hoặc kế hoạch khác dựa trên chi phí; **`OR` không đồng nghĩa chậm** và cũng không bảo đảm luôn dùng từng index riêng. Không tự thay `OR` bằng `UNION ALL` nếu chưa xét duplicate: một hàng thỏa cả hai nhánh có thể xuất hiện hai lần với `UNION ALL`, khác ngữ nghĩa của một điều kiện `OR` trên cùng bảng.

### 13.3. NOT và biểu thức phủ định

Các predicate như `<>`, `NOT IN`, `NOT LIKE` hoặc `NOT (...)` có thể chọn phần lớn bảng, nên một full scan đôi khi hợp lý. Không có quy tắc “có index thì mọi truy vấn `NOT` sẽ nhanh”; cần biết **độ chọn lọc** (bao nhiêu hàng được giữ), phân bố dữ liệu và kế hoạch thực tế. Những cột lọc thường xuyên nên được đánh giá theo workload đọc/ghi chứ không chỉ vì xuất hiện trong `WHERE`.

### 13.4. Tránh ép kiểu ngầm định không rõ ràng

```sql
-- Cột AMOUNT có kiểu NUMBER, hãy bind kiểu số đúng:
WHERE amount >= :min_amount
```

Nếu ứng dụng truyền chuỗi `'300'` thay vì số 300, Oracle có thể phải chuyển kiểu ngầm định. Điều này phụ thuộc ngữ cảnh, NLS và dữ liệu; có thể gây lỗi chuyển số hoặc plan không mong muốn. Với `DATE`, truyền chuỗi ngày không định dạng càng dễ gặp vấn đề do `NLS_DATE_FORMAT`. Dùng **typed bind parameters**, `DATE 'YYYY-MM-DD'`, `TO_DATE(..., format_mask)` khi thật sự cần chuyển chuỗi, hoặc API thời gian đúng kiểu từ Java.

### 13.5. Xem execution plan khi cần

Nếu truy vấn lớn chạy chậm, hãy bắt đầu từ câu SQL, bind, số hàng trả về và các index đã có. Người có quyền phù hợp có thể dùng công cụ giải thích plan hoặc xem cursor plan để hiểu Oracle sử dụng phương án truy cập nào. Phân tích plan không phải kiểm chứng tính đúng đắn duy nhất: **điều kiện sai vẫn có thể dùng index rất nhanh**. Ưu tiên xác nhận ý nghĩa nghiệp vụ và kết quả trước khi tối ưu.

## 14. Lỗi thường gặp với WHERE và các toán tử logic

| Cách viết/giả định sai | Vấn đề | Cách xử lý |
|---|---|---|
| `WHERE amount == 100` | `==` là cú pháp từ ngôn ngữ khác, không phải so sánh SQL thông dụng | Dùng `amount = 100` |
| `WHERE region_code = NULL` | So sánh với `NULL` tạo `UNKNOWN` | Dùng `IS NULL` |
| `WHERE region_code <> 'HN'` để bao gồm cả vùng chưa biết | Hàng có `NULL` bị loại | Nếu nghiệp vụ muốn, thêm `OR region_code IS NULL` |
| `A OR B AND C` khi định dùng `(A OR B) AND C` | `AND` ưu tiên cao hơn `OR` | Viết dấu ngoặc rõ ràng |
| `WHERE NOT region_code = 'HN'` được hiểu là lấy cả NULL | `NOT UNKNOWN` vẫn UNKNOWN | Phân biệt `<>`, `IS NULL` và phạm vi NOT |
| `WHERE amount BETWEEN 100 AND 200` nhưng nghĩ không gồm hai đầu | `BETWEEN` bao gồm 100 và 200 | Dùng `>`/`<` nếu cần khoảng mở |
| `NOT IN (subquery)` mà subquery có `NULL` | Có thể loại mọi hàng ngoài ý muốn | Xử lý null trong subquery hoặc dùng `NOT EXISTS` đúng ngữ nghĩa |
| `WHERE date_column = DATE '2026-11-03'` để tìm cả ngày | DATE có thể chứa giờ, phút, giây | Lọc `>=` đầu ngày và `<` đầu ngày kế tiếp |
| `WHERE amount > '100'` dựa trên chuỗi | Có thể chuyển kiểu ngầm định | Dùng giá trị số và typed bind |
| Đặt nhánh `OR` ngoài điều kiện tenant | Có thể lộ dữ liệu tenant khác | Nhóm các lựa chọn bằng ngoặc rồi `AND` điều kiện tenant |
| Dùng `OR` thay bằng `UNION ALL` tùy tiện | Có thể nhân đôi hàng thỏa cả hai điều kiện | Đối chiếu ngữ nghĩa tập hợp và duplicate |
| Giả định `AND` đánh giá vế trái trước | Optimizer có thể biến đổi/đẩy predicate | Dùng biểu thức an toàn, ví dụ `NULLIF` khi chia |
| `NOT (A OR B)` biến thành `NOT A OR NOT B` | Sai định luật De Morgan | Đúng là `NOT A AND NOT B` |
| Lọc tổng hợp bằng `WHERE COUNT(*) > 2` | Sai ngữ cảnh dùng aggregate | Dùng `GROUP BY` + `HAVING` |

Đối với các lỗi cú pháp, Oracle có thể báo những mã `ORA-009xx` tùy câu SQL cụ thể; **không nên đoán một mã cố định** nếu chưa xem toàn bộ thông báo. Ngược lại, các trường hợp thiếu dấu ngoặc hoặc xử lý `NULL` sai thường **không báo lỗi**, nên cần kiểm thử dữ liệu biên.

## 15. Bài thực hành có kiểm soát

Các bài dưới đây dùng bảng `LAB_WHERE_ORDERS` đã tạo trong phần 2. Chỉ chạy trên DEV/TEST, không thay đổi dữ liệu thật. Sau mỗi câu, hãy tự xác định điều kiện cho từng hàng **trước khi** xem kết quả; việc suy luận theo `TRUE`/`FALSE`/`UNKNOWN` giúp phát hiện sai sót dù truy vấn chạy thành công.

### Bài 1 — So sánh bằng và không bằng

```sql
SELECT order_id, order_status
FROM lab_where_orders
WHERE order_status = 'NEW'
ORDER BY order_id;
```

**Kết quả mong đợi:** đơn **1, 5, 6**. Thay `=` thành `<>` để lấy những hàng không ở trạng thái `NEW`; vì cột này không null, kết quả gồm **2, 3, 4, 7, 8**.

### Bài 2 — Khoảng giá trị và ranh giới

```sql
SELECT order_id, amount
FROM lab_where_orders
WHERE amount > 250 AND amount <= 500
ORDER BY order_id;
```

**Kết quả mong đợi:** **2, 3, 8**. Đơn 5 đúng 250 nên bị loại; đơn 3 đúng 500 vẫn được giữ. Thử thay `> 250` bằng `>= 250` để quan sát khác biệt.

### Bài 3 — Kết hợp AND và OR có ngoặc

```sql
SELECT order_id, order_status, amount
FROM lab_where_orders
WHERE (order_status = 'NEW' OR order_status = 'PAID')
  AND amount >= 400
ORDER BY order_id;
```

**Kết quả mong đợi:** **3, 6, 8**. Bỏ ngoặc và đối chiếu để thấy các hàng `NEW` dưới 400 có thể bị đưa vào kết quả.

### Bài 4 — Cột NULL và phủ định

```sql
SELECT order_id, region_code
FROM lab_where_orders
WHERE NOT (region_code = 'HN')
ORDER BY order_id;
```

**Kết quả mong đợi:** **2, 4, 6, 7**, không gồm 5 và 8 vì `NOT UNKNOWN` vẫn UNKNOWN. Sau đó thêm `OR region_code IS NULL` để bao gồm hai hàng chưa có mã vùng.

### Bài 5 — IN, NOT IN và NULL

```sql
SELECT order_id, order_status
FROM lab_where_orders
WHERE order_status IN ('NEW', 'PAID')
ORDER BY order_id;
```

**Kết quả mong đợi:** mọi đơn trừ **4**. Giải thích vì sao `NOT IN ('CANCELLED', NULL)` không thể thay thế điều kiện lọc trạng thái đã biết.

### Bài 6 — Kiểm tra date range

```sql
SELECT order_id, created_on
FROM lab_where_orders
WHERE created_on >= DATE '2026-11-05'
  AND created_on <  DATE '2026-11-08'
ORDER BY order_id;
```

**Kết quả mong đợi:** **5, 6, 7**. Hãy giải thích vì sao 8 bị loại và vì sao cận trên dùng `<` có lợi khi dữ liệu có thành phần thời gian.

### Bài 7 — Phủ định một nhóm điều kiện

Yêu cầu: “Lấy tất cả đơn trừ các đơn `NEW` có giá trị dưới 300.” Hãy viết cả hai dạng:

```sql
-- Cách 1: NOT bao quanh cả nhóm.
SELECT order_id
FROM lab_where_orders
WHERE NOT (order_status = 'NEW' AND amount < 300)
ORDER BY order_id;

-- Cách 2: Dùng định luật De Morgan.
SELECT order_id
FROM lab_where_orders
WHERE order_status <> 'NEW' OR amount >= 300
ORDER BY order_id;
```

**Kết quả mong đợi của cả hai:** **2, 3, 4, 6, 7, 8**. Những hàng bị loại là 1 và 5.

### Bài 8 — Viết điều kiện từ ngôn ngữ nghiệp vụ

Yêu cầu: “Tìm đơn tại HN hoặc HCM, có số tiền ít nhất 300, và không ở trạng thái `CANCELLED`.” Một cách viết:

```sql
SELECT order_id, region_code, amount, order_status
FROM lab_where_orders
WHERE region_code IN ('HN', 'HCM')
  AND amount >= 300
  AND order_status <> 'CANCELLED'
ORDER BY order_id;
```

**Kết quả mong đợi:** **2, 3, 6**. Viết lại `IN` bằng `OR` nhưng phải đặt ngoặc:

```sql
WHERE (region_code = 'HN' OR region_code = 'HCM')
  AND amount >= 300
  AND order_status <> 'CANCELLED'
```

Thử cố ý bỏ ngoặc, rồi giải thích vì sao các điều kiện chung không còn áp dụng cho mọi nhánh `OR`.

### Thu dọn dữ liệu thực hành

Khi đã xác nhận đây là bảng giả **do mình tạo trong đúng schema DEV/TEST**, và không có bài thực hành khác đang dùng chung, có thể thu dọn bằng lệnh:

```sql
DROP TABLE lab_where_orders PURGE;
```

`DROP TABLE ... PURGE` xóa bảng/dữ liệu, không đưa vào recycle bin và là thao tác DDL có implicit commit. **Không chạy trên production**, không dùng nếu tên bảng trùng với tài nguyên không thuộc phạm vi bài lab.

## 16. Câu hỏi ôn tập

**Câu 1.** Điều kiện `WHERE amount >= 100 AND amount <= 200` có bao gồm giá trị 100 và 200 không?

**Trả lời:** Có. Cả hai toán tử `>=` và `<=` đều bao gồm giá trị biên; có thể diễn đạt bằng `BETWEEN 100 AND 200` khi phù hợp.

**Câu 2.** `A OR B AND C` tương đương `(A OR B) AND C` hay `A OR (B AND C)`?

**Trả lời:** `A OR (B AND C)`, vì `AND` có ưu tiên cao hơn `OR`.

**Câu 3.** Với `REGION_CODE = NULL`, biểu thức `REGION_CODE <> 'HN'` là TRUE, FALSE hay UNKNOWN?

**Trả lời:** `UNKNOWN`. Hàng không được chọn bởi `WHERE` nếu không có vế điều kiện khác làm biểu thức tổng thể thành TRUE.

**Câu 4.** Hai hàng có `REGION_CODE IS NULL`; làm cách nào chỉ lấy những hàng đó?

**Trả lời:** `WHERE region_code IS NULL`, không viết `region_code = NULL`.

**Câu 5.** `NOT (A OR B)` tương đương biểu thức nào?

**Trả lời:** `(NOT A) AND (NOT B)`. Đây là định luật De Morgan; không được đổi thành `(NOT A) OR (NOT B)`.

**Câu 6.** `WHERE status NOT IN ('NEW', NULL)` có thể chọn những hàng `PAID` không?

**Trả lời:** Không theo cách mong đợi. Vì danh sách có `NULL`, vế `status <> NULL` là `UNKNOWN`; những hàng không khớp `'NEW'` sẽ có kết quả tổng thể `UNKNOWN` và bị loại.

**Câu 7.** Một bảng `ORDERS` chứa `CREATED_ON` kiểu DATE với cả giờ. Muốn chọn trọn ngày 03/11/2026, viết sao?

**Trả lời:** `created_on >= DATE '2026-11-03' AND created_on < DATE '2026-11-04'` là cách rõ ràng với khoảng nửa mở.

**Câu 8.** Tại sao `AND denominator <> 0` đặt trước phép chia trong `WHERE` chưa phải biện pháp phòng lỗi chia cho 0 đáng tin?

**Trả lời:** Vì optimizer có thể biến đổi cách đánh giá predicate. Nên dùng biểu thức an toàn như chia cho `NULLIF(denominator,0)` khi phù hợp.

**Câu 9.** Vì sao một điều kiện `OR` sai ngoặc có thể nguy hiểm trong ứng dụng multi-tenant?

**Trả lời:** Một nhánh `OR` có thể bỏ qua điều kiện `TENANT_ID`, làm truy vấn lấy dữ liệu tenant khác. Cần nhóm các lựa chọn rồi áp dụng điều kiện giới hạn tenant cho toàn bộ biểu thức.

**Câu 10.** Có thể khẳng định mọi câu `WHERE col = value` đều sử dụng index không?

**Trả lời:** Không. Oracle optimizer quyết định plan theo chi phí, index, thống kê và khối lượng dữ liệu. Tính đúng đắn của bộ lọc và hiệu năng truy vấn là hai vấn đề liên quan nhưng khác nhau.

## Kết luận

**`WHERE` lọc những hàng có điều kiện `TRUE`**. Toán tử so sánh (`=`, `<>`, `>`, `>=`, `<`, `<=`) diễn đạt quan hệ giữa giá trị; `AND` yêu cầu mọi điều kiện đúng, `OR` yêu cầu ít nhất một điều kiện đúng, còn `NOT` phủ định một biểu thức logic. Khi kết hợp, **`NOT` ưu tiên hơn `AND`, `AND` ưu tiên hơn `OR`**, vì vậy nên viết dấu ngoặc để thể hiện chính xác quy tắc nghiệp vụ.

Điểm không thể bỏ qua trong Oracle SQL là **`NULL` dẫn đến `UNKNOWN`**, không phải tự động thành `FALSE`: `= NULL` và `<> NULL` không dùng để kiểm tra dữ liệu thiếu, `NOT UNKNOWN` vẫn UNKNOWN, `NOT IN` có phần tử `NULL` có thể làm bộ lọc cho kết quả rỗng ngoài dự kiến. Hãy sử dụng `IS NULL`, `IS NOT NULL`, khoảng thời gian có biên rõ ràng, bind parameters đúng kiểu dữ liệu và thử nghiệm trên bộ dữ liệu có cả giá trị thông thường lẫn tình huống biên. Một biểu thức `WHERE` tốt phải **đúng dữ liệu trước**, sau đó mới được tối ưu hiệu năng bằng kế hoạch thực thi và index phù hợp.

# ORDER BY, độ ưu tiên và xử lý trùng trong truy vấn tập hợp Oracle

Trong Oracle Database, đôi khi một báo cáo cần ghép kết quả từ nhiều truy vấn: danh sách khách hàng đến từ website và cửa hàng, mã sản phẩm từ nhiều kho, danh sách người dùng thuộc nhiều nhóm, hoặc các bản ghi có mặt ở cả hai nguồn. **Set operators** (`UNION`, `UNION ALL`, `INTERSECT`, `MINUS`) kết hợp kết quả của nhiều câu `SELECT` thành một kết quả chung. Khi dùng chúng, ba vấn đề cần được hiểu chính xác là:

1. **Xử lý trùng:** kết quả có giữ mọi lần xuất hiện của một hàng hay loại các hàng trùng nhau?
2. **Độ ưu tiên:** khi nối nhiều set operator trong cùng câu SQL, Oracle nhóm các phép toán theo thứ tự nào?
3. **Sắp xếp:** `ORDER BY` sắp xếp từng truy vấn thành phần hay toàn bộ kết quả đã kết hợp?

Đây là những chi tiết có thể làm thay đổi số hàng, ý nghĩa nghiệp vụ và thứ tự dữ liệu mà ứng dụng nhận được. Một câu SQL chạy thành công vẫn có thể trả thiếu bản ghi nếu dùng `UNION` thay cho `UNION ALL`, hoặc trả thừa nếu chiếu thiếu cột khiến các hàng khác nhau bị coi là trùng.

## 1. Truy vấn tập hợp là gì?

Một **compound query** là câu truy vấn kết hợp hai hoặc nhiều `SELECT` bằng set operator. Mỗi `SELECT` thành phần tạo ra một tập hàng; operator xác định cách ghép, lấy phần chung hoặc loại phần thuộc tập bên phải.

```text
             SELECT từ nguồn A
                    |
                    v
                Tập A
                    \
                     \
                      +---- SET OPERATOR ----> Tập kết quả
                     /
                    /
                Tập B
                    ^
                    |
             SELECT từ nguồn B
```

Ví dụ hai nguồn bán hàng có thể cùng lưu mã khách hàng:

```sql
SELECT customer_id
FROM web_customers
UNION
SELECT customer_id
FROM store_customers;
```

Truy vấn trên trả danh sách mã khách hàng khác nhau xuất hiện ở ít nhất một nguồn. Nếu cần giữ số lần một khách hàng xuất hiện ở mỗi nguồn, phải dùng `UNION ALL`.

Set operator làm việc trên **các hàng được SELECT trả ra**, không tự biết khóa chính hay ý nghĩa nghiệp vụ của bảng nguồn. Nếu hai hàng khác nhau trong bảng nhưng có cùng các giá trị ở toàn bộ cột được chọn, chúng có thể bị xem là trùng khi dùng operator loại duplicate.

## 2. Bốn set operator cơ bản

Oracle 19c SQL Language Reference liệt kê bốn operator cơ bản: `UNION`, `UNION ALL`, `INTERSECT`, `MINUS`.

| Operator | Kết quả | Xử lý duplicate |
|---|---|---|
| `UNION` | Hàng xuất hiện ở A hoặc B | Loại các hàng trùng trong kết quả hợp |
| `UNION ALL` | Tất cả hàng của A và B | Giữ mọi lần xuất hiện, kể cả trùng trong từng nguồn và giữa hai nguồn |
| `INTERSECT` | Hàng xuất hiện ở cả A và B | Chỉ trả mỗi hàng chung một lần |
| `MINUS` | Hàng có trong A nhưng không có trong B | Chỉ trả mỗi hàng còn lại một lần |

Có thể hình dung:

```text
UNION       = A hợp B, loại trùng
UNION ALL   = A nối B, giữ mọi lần xuất hiện
INTERSECT   = A giao B, loại trùng
MINUS       = A trừ B, loại trùng
```

**`MINUS` có hướng:** `A MINUS B` khác `B MINUS A`. Còn `UNION`, `UNION ALL` và `INTERSECT` có tính đối xứng về tập hàng (nếu giữ nguyên kiểu/cột tương ứng), dù thứ tự cột và tên cột đầu ra vẫn dựa trên truy vấn thành phần đầu tiên.

### 2.1. UNION: hợp và loại trùng

```sql
SELECT customer_id FROM web_customers
UNION
SELECT customer_id FROM store_customers;
```

Nếu mã `102` xuất hiện ba lần trong nguồn website và một lần trong nguồn cửa hàng, kết quả `UNION` chỉ có một hàng `102`. `UNION` loại duplicate dựa trên **toàn bộ hàng được chọn**, không chỉ dựa trên một cột mà người viết nghĩ là khóa.

### 2.2. UNION ALL: hợp và giữ trùng

```sql
SELECT customer_id FROM web_customers
UNION ALL
SELECT customer_id FROM store_customers;
```

Nếu `102` xuất hiện ba lần ở website và một lần ở cửa hàng, kết quả có bốn hàng `102`. Operator này thích hợp khi mỗi lần xuất hiện mang ý nghĩa riêng, chẳng hạn sự kiện, giao dịch, lịch sử truy cập hoặc bản ghi cần đối soát.

### 2.3. INTERSECT: phần chung

```sql
SELECT customer_id FROM web_customers
INTERSECT
SELECT customer_id FROM store_customers;
```

Chỉ những mã có mặt trong cả hai nguồn được trả về. Nếu một mã xuất hiện nhiều lần ở mỗi bên, `INTERSECT` cơ bản vẫn trả một hàng cho mã đó.

### 2.4. MINUS: có ở truy vấn trái nhưng không có ở truy vấn phải

```sql
SELECT customer_id FROM web_customers
MINUS
SELECT customer_id FROM store_customers;
```

Kết quả là các mã có trong website nhưng không có trong cửa hàng. Đổi thứ tự hai `SELECT` sẽ trả danh sách ngược lại. `MINUS` cơ bản cũng loại duplicate ở kết quả, kể cả khi mã chỉ xuất hiện nhiều lần trong nguồn bên trái.

## 3. Dữ liệu thực hành: hai nguồn có duplicate và NULL

Các ví dụ tiếp theo dùng hai bảng giả `LAB_WEB_SIGNUPS` và `LAB_STORE_SIGNUPS`. Mỗi hàng biểu diễn một lần ghi nhận khách hàng ở một kênh. Một khách hàng có thể xuất hiện nhiều lần, vì vậy các bảng **cố ý không đặt primary key trên `CUSTOMER_ID`**.

Chỉ tạo bảng trong schema thực hành **DEV/TEST** được cấp quyền `CREATE TABLE` và quota. Trước khi chạy DDL, xác nhận đúng service, PDB và user:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME')   AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user
FROM dual;
```

### 3.1. Tạo hai bảng lab

```sql
CREATE TABLE lab_web_signups (
    signup_id     NUMBER,
    customer_id   NUMBER,
    display_name  VARCHAR2(80 CHAR),
    region_code   VARCHAR2(10 CHAR)
);

CREATE TABLE lab_store_signups (
    signup_id     NUMBER,
    customer_id   NUMBER,
    display_name  VARCHAR2(80 CHAR),
    region_code   VARCHAR2(10 CHAR)
);
```

### 3.2. Nạp dữ liệu giả

```sql
INSERT ALL
    INTO lab_web_signups VALUES (1, 101, 'An',            'HN')
    INTO lab_web_signups VALUES (2, 102, 'Binh',          'HCM')
    INTO lab_web_signups VALUES (3, 102, 'Binh',          'HCM')
    INTO lab_web_signups VALUES (4, 102, 'Binh (alias)',  'HCM')
    INTO lab_web_signups VALUES (5, 103, 'Chi',           'DN')
    INTO lab_web_signups VALUES (6, NULL,'Guest',         'HN')
    INTO lab_web_signups VALUES (7, 104, 'Lan',           'HN')
SELECT 1 FROM dual;

INSERT ALL
    INTO lab_store_signups VALUES (11, 102, 'Binh',  'HCM')
    INTO lab_store_signups VALUES (12, 104, 'Lan',   'HN')
    INTO lab_store_signups VALUES (13, 105, 'Dung',  'DN')
    INTO lab_store_signups VALUES (14, NULL,'Guest', 'HN')
    INTO lab_store_signups VALUES (15, NULL,'Guest', 'HN')
SELECT 1 FROM dual;

COMMIT;
```

Hai nguồn có các đặc điểm:

- `CUSTOMER_ID = 102` xuất hiện ba lần trong bảng website và một lần trong bảng cửa hàng.
- Một số hàng trùng hoàn toàn trên các cột `CUSTOMER_ID`, `DISPLAY_NAME`, `REGION_CODE`.
- `CUSTOMER_ID = 102` còn có một hàng tên `Binh (alias)`, khác hàng `Binh` dù cùng mã khách hàng.
- `CUSTOMER_ID = 104` xuất hiện ở cả hai nguồn.
- `CUSTOMER_ID = 105` chỉ có ở cửa hàng.
- `CUSTOMER_ID = NULL` xuất hiện một lần ở website và hai lần ở cửa hàng.

### 3.3. Xem dữ liệu từng nguồn

```sql
SELECT customer_id, display_name, region_code
FROM lab_web_signups
ORDER BY customer_id NULLS LAST, signup_id;

SELECT customer_id, display_name, region_code
FROM lab_store_signups
ORDER BY customer_id NULLS LAST, signup_id;
```

Hai câu lệnh trên chỉ sắp xếp **mỗi bảng riêng** để quan sát dữ liệu. Khi dùng set operator, thứ tự cuối cùng sẽ do `ORDER BY` của compound query quyết định.

## 4. Quan sát sự khác nhau giữa UNION và UNION ALL

### 4.1. UNION trên một cột

```sql
SELECT customer_id
FROM lab_web_signups
UNION
SELECT customer_id
FROM lab_store_signups
ORDER BY customer_id NULLS LAST;
```

Tập kết quả gồm:

| `CUSTOMER_ID` | Số hàng trong kết quả |
|---:|---:|
| 101 | 1 |
| 102 | 1 |
| 103 | 1 |
| 104 | 1 |
| 105 | 1 |
| `NULL` | 1 |

Tổng cộng **6 hàng**. Ba lần `102` ở website và một lần ở cửa hàng được gộp thành một hàng vì câu truy vấn chỉ chiếu `CUSTOMER_ID`. Các giá trị `NULL` cũng được xử lý trong phép so sánh tập để loại bản sao; điều này khác cách viết `WHERE customer_id = NULL` trong điều kiện thông thường.

### 4.2. UNION ALL trên một cột

```sql
SELECT customer_id
FROM lab_web_signups
UNION ALL
SELECT customer_id
FROM lab_store_signups
ORDER BY customer_id NULLS LAST;
```

Tổng cộng **12 hàng**: 7 hàng từ website và 5 hàng từ cửa hàng. `102` xuất hiện bốn lần; `NULL` xuất hiện ba lần. `UNION ALL` không xóa duplicate ở bên trái, bên phải hay giữa hai bên.

| `CUSTOMER_ID` | Số lần trong website | Số lần trong cửa hàng | UNION | UNION ALL |
|---:|---:|---:|---:|---:|
| 101 | 1 | 0 | 1 | 1 |
| 102 | 3 | 1 | 1 | 4 |
| 103 | 1 | 0 | 1 | 1 |
| 104 | 1 | 1 | 1 | 2 |
| 105 | 0 | 1 | 1 | 1 |
| `NULL` | 1 | 2 | 1 | 3 |
| **Tổng** | **7** | **5** | **6** | **12** |

### 4.3. Duplicate được xác định trên toàn bộ cột SELECT

Đây là điểm rất quan trọng. Khi viết:

```sql
SELECT customer_id
FROM lab_web_signups
UNION
SELECT customer_id
FROM lab_store_signups;
```

Oracle chỉ so sánh **một cột**. Hai bản ghi có cùng `CUSTOMER_ID = 102` sẽ được xem là trùng, dù một hàng tên `Binh` và hàng kia tên `Binh (alias)`.

Nếu chọn thêm tên và vùng:

```sql
SELECT customer_id, display_name, region_code
FROM lab_web_signups
UNION
SELECT customer_id, display_name, region_code
FROM lab_store_signups
ORDER BY customer_id NULLS LAST, display_name;
```

thì `(102, 'Binh', 'HCM')` và `(102, 'Binh (alias)', 'HCM')` là **hai hàng khác nhau**, nên cả hai được giữ trong kết quả `UNION`. Những hàng giống nhau trên cả ba cột mới bị loại.

Vì vậy, khi muốn “danh sách khách hàng duy nhất”, hãy xác định rõ duy nhất theo `CUSTOMER_ID` hay theo toàn bộ tuple đang chọn. Không dùng `SELECT * UNION SELECT *` như một cách thay thế chung cho việc xác định khóa nghiệp vụ.

## 5. INTERSECT và MINUS: phần chung và phần chênh lệch

### 5.1. INTERSECT cơ bản

```sql
SELECT customer_id
FROM lab_web_signups
INTERSECT
SELECT customer_id
FROM lab_store_signups
ORDER BY customer_id NULLS LAST;
```

Kết quả là `102`, `104` và `NULL`: các giá trị có mặt trong cả hai nguồn. Dù `102` xuất hiện nhiều lần, `INTERSECT` không có `ALL` chỉ trả một lần cho giá trị đó. `NULL` có mặt ở cả hai tập cũng được nhận diện là phần chung trong ngữ nghĩa set operation.

### 5.2. MINUS cơ bản

```sql
SELECT customer_id
FROM lab_web_signups
MINUS
SELECT customer_id
FROM lab_store_signups
ORDER BY customer_id NULLS LAST;
```

Kết quả là `101` và `103`: những giá trị có ở website nhưng không có ở cửa hàng. `102` bị loại vì đã có ở tập bên phải; `104` và `NULL` cũng có ở cả hai bên nên không còn trong kết quả.

Đổi hướng:

```sql
SELECT customer_id
FROM lab_store_signups
MINUS
SELECT customer_id
FROM lab_web_signups
ORDER BY customer_id NULLS LAST;
```

Kết quả chỉ còn `105`, vì đây là mã xuất hiện ở cửa hàng nhưng không xuất hiện ở website.

### 5.3. INTERSECT và MINUS cơ bản loại duplicate

| Giá trị | Web | Store | INTERSECT | Web MINUS Store |
|---:|---:|---:|---:|---:|
| 101 | 1 | 0 | 0 | 1 |
| 102 | 3 | 1 | 1 | 0 |
| 103 | 1 | 0 | 0 | 1 |
| 104 | 1 | 1 | 1 | 0 |
| 105 | 0 | 1 | 0 | 0 |
| `NULL` | 1 | 2 | 1 | 0 |

Các cột kết quả trong bảng là **số lần xuất hiện của giá trị trong kết quả**, không phải số hàng gốc. Operator cơ bản trả tập hàng distinct.

## 6. ALL variants: giữ multiplicity trong phép giao và phép trừ

Oracle Database 21c SQL Language Reference và tài liệu Oracle AI Database 26ai có thêm các dạng `INTERSECT ALL`, `MINUS ALL`, `EXCEPT` và `EXCEPT ALL`. Oracle 19c SQL Reference chỉ liệt kê bốn operator cơ bản. Vì vậy, nếu hệ thống còn chạy 19c, không dùng các cú pháp mới này trước khi xác nhận release đích hỗ trợ.

### 6.1. INTERSECT ALL

`INTERSECT ALL` giữ các hàng chung **kể cả số lần xuất hiện**. Với một tuple xuất hiện `m` lần ở tập A và `n` lần ở tập B, số lần trong kết quả là `MIN(m, n)`.

```sql
-- Oracle 21c/26ai theo SQL Reference có hỗ trợ INTERSECT ALL.
SELECT customer_id
FROM lab_web_signups
INTERSECT ALL
SELECT customer_id
FROM lab_store_signups
ORDER BY customer_id NULLS LAST;
```

Theo dữ liệu lab:

- `102`: `MIN(3, 1) = 1` lần.
- `104`: `MIN(1, 1) = 1` lần.
- `NULL`: `MIN(1, 2) = 1` lần.

Kết quả có **3 hàng**. So với `INTERSECT` cơ bản, dữ liệu mẫu tình cờ có cùng số hàng vì mỗi giá trị chung có ít nhất một lần ở cả hai bên; khác biệt sẽ thấy rõ khi cả hai bên đều có nhiều bản sao.

### 6.2. MINUS ALL

`MINUS ALL` giữ phần chênh lệch số lần xuất hiện từ tập bên trái. Với tuple xuất hiện `m` lần ở A và `n` lần ở B, kết quả có `MAX(m - n, 0)` lần.

```sql
-- Oracle 21c/26ai theo SQL Reference có hỗ trợ MINUS ALL.
SELECT customer_id
FROM lab_web_signups
MINUS ALL
SELECT customer_id
FROM lab_store_signups
ORDER BY customer_id NULLS LAST;
```

Theo dữ liệu lab:

- `101`: `MAX(1 - 0, 0) = 1` lần.
- `102`: `MAX(3 - 1, 0) = 2` lần.
- `103`: `MAX(1 - 0, 0) = 1` lần.
- `104`: `MAX(1 - 1, 0) = 0` lần.
- `105`: `MAX(0 - 1, 0) = 0` lần.
- `NULL`: `MAX(1 - 2, 0) = 0` lần.

Kết quả gồm `101`, `102`, `102`, `103` — **4 hàng**. Operator này hữu ích khi đối soát số lần ghi nhận, thay vì chỉ quan tâm giá trị có xuất hiện hay không.

### 6.3. EXCEPT và EXCEPT ALL

Trong tài liệu Oracle 21c/26ai, `EXCEPT` là synonym của `MINUS` và có cùng ngữ nghĩa; `EXCEPT ALL` tương ứng với `MINUS ALL`.

```sql
-- Dạng distinct: tương đương MINUS.
SELECT customer_id FROM lab_web_signups
EXCEPT
SELECT customer_id FROM lab_store_signups;

-- Dạng giữ phần multiplicity còn lại; Oracle 21c/26ai.
SELECT customer_id FROM lab_web_signups
EXCEPT ALL
SELECT customer_id FROM lab_store_signups;
```

Nếu cần tương thích với codebase Oracle 19c, `MINUS` và `MINUS ALL` không cùng mức hỗ trợ; `MINUS ALL` không nằm trong danh sách operator của tài liệu 19c. Dùng `MINUS` cơ bản cho logic distinct trên 19c.

### 6.4. Bảng so sánh DISTINCT và ALL

| Operator | Dạng cơ bản | Dạng ALL (21c/26ai) | Quy tắc số lần xuất hiện |
|---|---|---|---|
| Hợp | `UNION` | `UNION ALL` | `UNION`: một bản sao; `UNION ALL`: `m + n` |
| Giao | `INTERSECT` | `INTERSECT ALL` | Cơ bản: một bản sao nếu có ở cả hai; ALL: `MIN(m, n)` |
| Trừ | `MINUS` / `EXCEPT` | `MINUS ALL` / `EXCEPT ALL` | Cơ bản: một bản sao nếu chỉ có ở trái; ALL: `MAX(m - n, 0)` |

`UNION` đã là dạng distinct mặc định; không cần viết `UNION DISTINCT` trong các ví dụ thông thường.

## 7. NULL và duplicate trong truy vấn tập hợp

Không nên mang nguyên cách suy luận của phép so sánh `=` trong `WHERE` sang set operator. Trong điều kiện thông thường, `NULL = NULL` cho `UNKNOWN`. Trong các phép toán tập hợp, Oracle có ngữ nghĩa nhận diện các giá trị NULL chung để thực hiện loại trùng, giao và trừ. Tài liệu Oracle mô tả rõ NULL chung trong `INTERSECT ALL` và số lượng NULL còn lại trong `MINUS ALL`.

Ví dụ:

```sql
SELECT CAST(NULL AS NUMBER) AS value_col FROM dual
UNION
SELECT CAST(NULL AS NUMBER) AS value_col FROM dual;
```

Kết quả chỉ có **một hàng NULL** vì `UNION` loại duplicate. Với `UNION ALL`, cả hai hàng NULL đều được giữ.

```sql
SELECT CAST(NULL AS NUMBER) AS value_col FROM dual
INTERSECT
SELECT CAST(NULL AS NUMBER) AS value_col FROM dual;
```

Kết quả có một hàng NULL vì giá trị null xuất hiện ở cả hai tập. Nếu muốn hiểu multiplicity của NULL ở 21c/26ai, có thể thực hành `INTERSECT ALL` và `MINUS ALL` với các truy vấn có nhiều `SELECT CAST(NULL AS NUMBER) FROM dual`.

**Lưu ý:** `NULL` ở đây là giá trị của hàng trong kết quả. Nó không đồng nghĩa với một chuỗi ký tự `'NULL'`, số 0 hay chuỗi rỗng. Nếu cần placeholder cho cột thiếu ở một nhánh, hãy `CAST(NULL AS datatype)` để giữ đúng kiểu dữ liệu của cột tương ứng.

## 8. Thứ tự ưu tiên của các set operator

Oracle Database hiện tài liệu hóa các set operator có **cùng độ ưu tiên**. Nếu một compound query có nhiều operator và không nhóm bằng dấu ngoặc, Oracle đánh giá các phép toán từ **trái sang phải**.

Ví dụ:

```sql
SELECT 1 AS id FROM dual
UNION
SELECT 2 FROM dual
INTERSECT
SELECT 2 FROM dual;
```

Với quy tắc trái sang phải hiện được tài liệu Oracle nêu, cách nhóm là:

```text
(A UNION B) INTERSECT C

A = {1}
B = {2}
C = {2}

A UNION B       = {1, 2}
{1, 2} INTERSECT C = {2}
```

Kết quả là `2`. Nếu người đọc tự áp dụng quy tắc “INTERSECT luôn ưu tiên hơn UNION” từ một hệ quản trị khác, họ có thể dự đoán sai kết quả.

### 8.1. Dùng CTE để biểu đạt thứ tự rõ ràng

Nếu nghiệp vụ muốn `(A UNION B) INTERSECT C`, có thể nhóm A và B trong CTE:

```sql
WITH a_union_b AS (
    SELECT 1 AS id FROM dual
    UNION
    SELECT 2 FROM dual
)
SELECT id
FROM a_union_b
INTERSECT
SELECT 2 FROM dual;
```

Nếu nghiệp vụ muốn `A UNION (B INTERSECT C)`, nhóm B và C trước:

```sql
WITH b_intersect_c AS (
    SELECT 2 AS id FROM dual
    INTERSECT
    SELECT 2 FROM dual
)
SELECT 1 AS id FROM dual
UNION
SELECT id FROM b_intersect_c;
```

Kết quả lần lượt là `{2}` và `{1, 2}`. CTE giúp ý định rõ ràng, dễ kiểm thử và tránh phụ thuộc vào việc người đọc nhớ độ ưu tiên mặc định.

### 8.2. Oracle có thể thay đổi độ ưu tiên INTERSECT trong tương lai

Tài liệu SQL Reference của Oracle 19c, 21c và 26ai hiện mô tả các set operator có cùng độ ưu tiên và đánh giá trái sang phải khi không có ngoặc. Tài liệu cũng có ghi chú rằng một bản phát hành tương lai có thể cho `INTERSECT` độ ưu tiên cao hơn để phù hợp SQL standard. Vì vậy, khi kết hợp `INTERSECT` với `UNION` hoặc `MINUS`, **luôn dùng ngoặc/CTE để chỉ định thứ tự nghiệp vụ**, kể cả khi code đang chạy đúng trên release hiện tại.

### 8.3. Không nhầm độ ưu tiên set operator với AND/OR trong WHERE

`AND` và `OR` là toán tử logic bên trong điều kiện của một query block; `UNION`, `INTERSECT`, `MINUS` kết hợp **kết quả của nhiều query block**. Chúng hoạt động ở hai cấp khác nhau.

```sql
SELECT customer_id
FROM lab_web_signups
WHERE region_code = 'HN' OR region_code = 'HCM'
UNION
SELECT customer_id
FROM lab_store_signups
WHERE region_code = 'DN';
```

Mỗi `WHERE` lọc hàng của nguồn tương ứng trước khi set operator kết hợp kết quả. Nếu một query block có cả `AND` và `OR`, vẫn cần ngoặc theo quy tắc điều kiện SQL riêng; dấu ngoặc của compound query không tự thay đổi logic bên trong `WHERE`.

## 9. ORDER BY trong compound query: sắp xếp toàn bộ kết quả

**Không có `ORDER BY`, Oracle không bảo đảm thứ tự hàng được trả về.** Điều này đúng cả với `UNION ALL`: việc dữ liệu thường xuất hiện theo thứ tự nhánh trái rồi nhánh phải trong một lần chạy không phải cam kết thứ tự của SQL.

Khi có `ORDER BY` ở cuối compound query, Oracle sắp xếp **toàn bộ tập kết quả sau khi áp dụng set operator**, không sắp xếp từng nhánh riêng.

```sql
SELECT customer_id
FROM lab_web_signups
UNION ALL
SELECT customer_id
FROM lab_store_signups
ORDER BY customer_id NULLS LAST;
```

Tất cả hàng từ cả hai nguồn được sắp theo `CUSTOMER_ID`. Nếu có nhiều hàng cùng giá trị, thứ tự tương đối giữa chúng vẫn chưa xác định trừ khi thêm tiêu chí phụ.

### 9.1. ORDER BY chỉ xuất hiện một lần ở cuối

Không viết `ORDER BY` ở giữa các nhánh của compound query như sau:

```sql
-- Không hợp lệ theo quy tắc compound query Oracle:
SELECT customer_id
FROM lab_web_signups
ORDER BY customer_id
UNION ALL
SELECT customer_id
FROM lab_store_signups;
```

Hãy đặt `ORDER BY` sau `SELECT` thành phần cuối:

```sql
SELECT customer_id
FROM lab_web_signups
UNION ALL
SELECT customer_id
FROM lab_store_signups
ORDER BY customer_id;
```

Nếu cần giới hạn/top-N riêng cho từng nguồn, hãy thiết kế các query block/inline view có row limiting phù hợp rồi kết hợp chúng; không dựa vào một `ORDER BY` ở nhánh giữa compound query.

### 9.2. ORDER BY dùng alias hoặc vị trí cột

Với compound query, Oracle yêu cầu `ORDER BY` tham chiếu **vị trí cột** hoặc **alias của kết quả**, thay vì viết một biểu thức tùy ý. Tên cột kết quả lấy từ danh sách `SELECT` của query thành phần đầu tiên.

```sql
SELECT customer_id AS member_id,
       display_name AS member_name
FROM lab_web_signups
UNION ALL
SELECT customer_id,
       display_name
FROM lab_store_signups
ORDER BY member_id, member_name;
```

Hoặc dùng vị trí:

```sql
SELECT customer_id, display_name
FROM lab_web_signups
UNION ALL
SELECT customer_id, display_name
FROM lab_store_signups
ORDER BY 1, 2;
```

`ORDER BY 1` là sắp theo biểu thức thứ nhất trong select list; `ORDER BY 2` là biểu thức thứ hai. Dùng alias thường dễ đọc và ít lỗi hơn khi thay đổi thứ tự cột. Tuy nhiên, nếu tên alias trùng/khó phân biệt, cần đặt tên cột đầu ra rõ ràng ngay ở `SELECT` đầu tiên.

### 9.3. Biểu thức trong SELECT đầu tiên phải có alias nếu dùng để ORDER BY

```sql
SELECT UPPER(display_name) AS normalized_name
FROM lab_web_signups
UNION
SELECT UPPER(display_name)
FROM lab_store_signups
ORDER BY normalized_name;
```

Alias `NORMALIZED_NAME` ở nhánh đầu xác định tên cột đầu ra, vì vậy có thể dùng ở `ORDER BY` cuối. Nếu muốn sắp theo một biểu thức không có trong danh sách đầu ra, hãy bọc compound query trong truy vấn ngoài.

### 9.4. Bọc compound query để sắp theo biểu thức khác

Ví dụ muốn sắp xếp tên không phân biệt hoa/thường mà không muốn đưa thêm biểu thức vào kết quả set operation:

```sql
SELECT customer_id, display_name
FROM (
    SELECT customer_id, display_name
    FROM lab_web_signups
    UNION
    SELECT customer_id, display_name
    FROM lab_store_signups
)
ORDER BY UPPER(display_name), customer_id;
```

Compound query bên trong tạo kết quả trước; query bên ngoài sắp xếp bằng biểu thức `UPPER`. Cách bọc này còn hữu ích khi cần áp dụng `FETCH FIRST`, tạo thêm cột sắp xếp hoặc đặt logic trình bày sau khi đã hoàn thành phép hợp/giao/trừ.

### 9.5. ASC, DESC và vị trí NULL

Oracle mặc định:

- `ASC`: tăng dần; `NULLS LAST` là mặc định.
- `DESC`: giảm dần; `NULLS FIRST` là mặc định.

Nên ghi rõ `NULLS FIRST` hoặc `NULLS LAST` khi báo cáo cần thứ tự ổn định, đặc biệt khi cột được phép null:

```sql
SELECT customer_id
FROM lab_web_signups
UNION
SELECT customer_id
FROM lab_store_signups
ORDER BY customer_id ASC NULLS LAST;
```

### 9.6. Thứ tự xác định khi có nhiều hàng cùng khóa sắp xếp

Nếu chỉ viết:

```sql
ORDER BY customer_id
```

thì các hàng có cùng `CUSTOMER_ID` không có thứ tự phụ được bảo đảm. Khi kết quả có nhiều bản ghi cùng mã, thêm cột phụ:

```sql
SELECT customer_id, display_name, signup_id
FROM lab_web_signups
UNION ALL
SELECT customer_id, display_name, signup_id
FROM lab_store_signups
ORDER BY customer_id NULLS LAST, signup_id;
```

Nếu `SIGNUP_ID` chỉ duy nhất trong từng nguồn, nó chưa chắc duy nhất trên toàn kết quả. Khi cần thứ tự hoàn toàn xác định, hãy thêm `SOURCE_CODE` hoặc một khóa tổng hợp duy nhất phù hợp. Điều này quan trọng khi phân trang, xuất file hoặc đối soát dữ liệu.

## 10. Thứ tự nhánh không phải thứ tự kết quả

Một hiểu lầm thường gặp là nghĩ `UNION ALL` luôn trả toàn bộ nhánh thứ nhất trước rồi tới nhánh thứ hai. SQL là ngôn ngữ khai báo; optimizer có thể chọn kế hoạch thực thi khác. Nếu không có `ORDER BY`, ứng dụng không được dựa vào thứ tự xuất hiện của các nhánh.

Nếu nghiệp vụ muốn hiển thị website trước cửa hàng, hãy đưa một cột thứ tự nguồn vào query rồi sắp xếp ở ngoài:

```sql
SELECT source_name, customer_id, display_name
FROM (
    SELECT 1 AS source_order,
           'WEB' AS source_name,
           customer_id,
           display_name
    FROM lab_web_signups

    UNION ALL

    SELECT 2 AS source_order,
           'STORE' AS source_name,
           customer_id,
           display_name
    FROM lab_store_signups
)
ORDER BY source_order,
         customer_id NULLS LAST,
         display_name;
```

Query ngoài không hiển thị `SOURCE_ORDER` nhưng dùng nó để sắp xếp. Kết quả có thể được trình bày theo nhóm WEB rồi STORE, sau đó theo mã khách hàng. Nếu thêm `SOURCE_NAME` vào **bên trong một `UNION` distinct**, hàng từ hai nguồn có source khác nhau sẽ không còn là duplicate; vì vậy chỉ thêm cột nguồn khi thực sự muốn phân biệt bản ghi theo nguồn.

## 11. Kiểu dữ liệu và vị trí cột phải tương thích

Mỗi query thành phần phải trả về:

1. **Cùng số lượng cột**.
2. Các cột tương ứng phải nằm **cùng vị trí** và thuộc **cùng nhóm kiểu dữ liệu** (ví dụ numeric với numeric, character với character).
3. Tên alias ở query đầu tiên xác định tên cột kết quả; alias ở nhánh sau không đổi tên đầu ra.

Ví dụ hợp lệ:

```sql
SELECT customer_id, display_name
FROM lab_web_signups
UNION ALL
SELECT customer_id, display_name
FROM lab_store_signups;
```

Ví dụ sai nhóm kiểu:

```sql
-- Không hợp lệ: cột thứ nhất là NUMBER, cột tương ứng là VARCHAR2.
SELECT customer_id
FROM lab_web_signups
UNION
SELECT display_name
FROM lab_store_signups;
```

Oracle không tự chuyển giữa các nhóm kiểu dữ liệu cho set operator; có thể gặp lỗi như `ORA-01790`. Nếu nghiệp vụ thực sự muốn hợp nhất thành một cột văn bản, phải chuyển kiểu tường minh:

```sql
SELECT TO_CHAR(customer_id) AS member_value
FROM lab_web_signups
UNION
SELECT display_name
FROM lab_store_signups;
```

Tuy nhiên, gom mã số và tên người vào một cột chung có thể gây khó xử lý ở tầng ứng dụng. Thường tốt hơn là chuẩn hóa cấu trúc kết quả bằng nhiều cột có kiểu tương ứng.

### 11.1. Numeric precedence

Nếu các cột tương ứng đều thuộc nhóm số, Oracle xác định kiểu kết quả theo numeric precedence:

```text
BINARY_DOUBLE > BINARY_FLOAT > NUMBER
```

Nếu có `BINARY_DOUBLE`, kết quả có kiểu `BINARY_DOUBLE`; nếu không có nhưng có `BINARY_FLOAT`, kết quả là `BINARY_FLOAT`; nếu tất cả là `NUMBER`, kết quả là `NUMBER`. Điều này có thể ảnh hưởng độ chính xác và mapping JDBC, vì vậy không nên trộn kiểu số dấu phẩy động vào báo cáo tiền tệ chỉ vì một nguồn đang dùng kiểu khác.

### 11.2. CHAR và VARCHAR2

Với cột ký tự:

- Nếu hai query đều trả `CHAR` có cùng độ dài, kiểu kết quả là `CHAR` với độ dài đó.
- Nếu `CHAR` có độ dài khác nhau, kết quả là `VARCHAR2` với độ dài của `CHAR` dài hơn.
- Nếu một hoặc cả hai query trả `VARCHAR2`, kết quả là `VARCHAR2`.

Đừng mặc định cột đầu ra luôn giữ nguyên datatype/length của từng nhánh; hãy kiểm tra metadata hoặc cast rõ ràng nếu contract ứng dụng cần độ dài cụ thể.

### 11.3. Dùng CAST cho placeholder NULL

Khi một nguồn không có một thuộc tính nhưng nguồn khác có, dùng typed NULL để bảo đảm datatype tương thích:

```sql
SELECT customer_id,
       display_name,
       CAST(NULL AS VARCHAR2(30 CHAR)) AS store_note
FROM lab_web_signups

UNION ALL

SELECT customer_id,
       display_name,
       CAST('Imported from store' AS VARCHAR2(30 CHAR)) AS store_note
FROM lab_store_signups;
```

`CAST(NULL AS VARCHAR2(...))` nêu rõ kiểu cột thứ ba. Không nên chỉ viết `NULL` trong các biểu thức phức tạp khi Oracle có thể cần xác định kiểu đầu ra hoặc khi nhánh còn lại trả kiểu khác.

### 11.4. Các kiểu dữ liệu bị hạn chế

Oracle đặt một số hạn chế cho set operator. Ví dụ, không dùng các operator này trực tiếp trên cột `BLOB`, `CLOB`, `BFILE`, `VARRAY` hoặc nested table; các operator distinct như `UNION`, `INTERSECT`, `MINUS` (và `EXCEPT` ở release hỗ trợ) cũng có hạn chế với `LONG`. Khi cần so sánh dữ liệu LOB, hãy thiết kế cách so sánh/định danh phù hợp thay vì cố đưa LOB vào `UNION`.

## 12. ORDER BY kết hợp row limiting

Sau khi ghép nhiều query, có thể sắp xếp toàn bộ kết quả rồi giới hạn số hàng:

```sql
SELECT customer_id, display_name
FROM lab_web_signups
UNION ALL
SELECT customer_id, display_name
FROM lab_store_signups
ORDER BY customer_id NULLS LAST, display_name
FETCH FIRST 5 ROWS ONLY;
```

`FETCH FIRST 5 ROWS ONLY` áp dụng cho **kết quả compound query đã sắp xếp**, không phải mỗi nhánh riêng. Nếu bỏ `ORDER BY`, năm hàng được chọn không có thứ tự ổn định giữa các lần chạy.

### 12.1. WITH TIES

Nếu nghiệp vụ cần lấy thêm các hàng đồng hạng với hàng cuối, có thể cân nhắc `FETCH FIRST ... WITH TIES` cùng `ORDER BY`:

```sql
SELECT customer_id, display_name
FROM lab_web_signups
UNION ALL
SELECT customer_id, display_name
FROM lab_store_signups
ORDER BY customer_id NULLS LAST
FETCH FIRST 5 ROWS WITH TIES;
```

Khi dùng `WITH TIES`, Oracle có thể trả nhiều hơn năm hàng nếu hàng tiếp theo có cùng giá trị sort key với hàng ở vị trí cuối. Nếu thêm một cột unique vào `ORDER BY`, các hàng thường không còn đồng hạng; do đó phải chọn sort key theo đúng ý nghĩa nghiệp vụ.

### 12.2. Phân trang ổn định

Để phân trang compound query, cần một thứ tự xác định, thường gồm cột sắp xếp chính và khóa phụ duy nhất:

```sql
SELECT source_order, signup_id, customer_id, display_name
FROM (
    SELECT 1 AS source_order, signup_id, customer_id, display_name
    FROM lab_web_signups
    UNION ALL
    SELECT 2 AS source_order, signup_id, customer_id, display_name
    FROM lab_store_signups
)
ORDER BY source_order, signup_id
OFFSET 0 ROWS FETCH NEXT 20 ROWS ONLY;
```

Trong ví dụ, `SIGNUP_ID` chỉ duy nhất trong mỗi nguồn, nhưng cặp `(SOURCE_ORDER, SIGNUP_ID)` xác định một hàng trong kết quả. Khi trang tiếp theo được lấy, thứ tự đó giúp giảm nguy cơ hàng nhảy giữa các trang do tie. Nếu dữ liệu thay đổi giữa hai request, offset pagination vẫn có thể lệch; hệ thống tải dữ liệu lớn nên cân nhắc keyset pagination hoặc snapshot phù hợp.

## 13. ORDER BY và duplicate: hai thao tác độc lập

`ORDER BY` **không loại duplicate**. `UNION` loại duplicate vì bản thân operator có semantics distinct; `UNION ALL` giữ duplicate dù có sắp xếp sau đó.

```sql
-- Vẫn giữ duplicate; ORDER BY chỉ thay đổi thứ tự hiển thị.
SELECT customer_id
FROM lab_web_signups
UNION ALL
SELECT customer_id
FROM lab_store_signups
ORDER BY customer_id;
```

Ngược lại, `UNION` vẫn loại duplicate ngay cả khi không có `ORDER BY`:

```sql
SELECT customer_id
FROM lab_web_signups
UNION
SELECT customer_id
FROM lab_store_signups;
```

Không dựa vào việc kết quả `UNION` “trông như đã sắp xếp” để bỏ `ORDER BY`. Oracle có thể dùng một kế hoạch thực thi khác theo phiên bản, statistics hoặc tải hệ thống. **Loại trùng và sắp xếp là hai yêu cầu khác nhau, phải được viết riêng.**

## 14. Chọn UNION hay UNION ALL theo ý nghĩa dữ liệu

| Tình huống | Lựa chọn thường phù hợp | Vì sao |
|---|---|---|
| Ghép log sự kiện từ hai nguồn, mỗi sự kiện là một lần xảy ra | `UNION ALL` | Hai event giống nội dung vẫn có thể là hai lần xảy ra khác nhau |
| Tạo danh sách mã khách hàng duy nhất từ nhiều kênh | `UNION` | Chỉ cần một lần xuất hiện của mỗi mã |
| Đối chiếu mã có ở cả hai hệ thống | `INTERSECT` | Cần phần chung distinct |
| Tìm mã chỉ có ở hệ thống A | `MINUS` | Cần tập chênh lệch distinct có hướng |
| Đối chiếu số lần xuất hiện giữa hai nguồn | `INTERSECT ALL` / `MINUS ALL` nếu release hỗ trợ | Giữ thông tin multiplicity |
| Giữ bản ghi trùng để kiểm tra dữ liệu import | `UNION ALL` | Không làm mất bằng chứng duplicate |

### 14.1. UNION có thể tốn thêm công việc loại trùng

Để thực hiện `UNION`, `INTERSECT`, `MINUS` distinct, Oracle phải xử lý duplicate/membership. Tùy kế hoạch, optimizer có thể dùng sort, hash hoặc phương án khác; với dữ liệu lớn, thao tác này có thể dùng PGA/TEMP và làm truy vấn tốn tài nguyên hơn `UNION ALL`.

`UNION ALL` thường tránh bước loại trùng, nhưng không phải lúc nào cũng làm toàn bộ truy vấn nhanh hơn theo mọi workload. Quan trọng hơn, **không đổi `UNION` thành `UNION ALL` chỉ để tăng tốc nếu nghiệp vụ yêu cầu kết quả distinct**. Trước khi tối ưu, hãy xác định duplicate là dữ liệu cần giữ hay dữ liệu cần loại.

### 14.2. Không dùng UNION để che lỗi dữ liệu

Nếu hai nguồn chứa bản ghi trùng ngoài ý muốn, `UNION` có thể làm báo cáo nhìn có vẻ sạch nhưng che mất vấn đề chất lượng dữ liệu. Khi điều tra import, đối soát hoặc kiểm tra duplicate, `UNION ALL` kèm cột nguồn thường giúp phát hiện dữ liệu tốt hơn.

## 15. Các lỗi thường gặp

| Lỗi/triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `ORA-01789: query block has incorrect number of result columns` | Các SELECT thành phần trả số cột khác nhau | Đối chiếu số cột và thứ tự cột của từng nhánh |
| `ORA-01790: expression must have same datatype as corresponding expression` | Các cột cùng vị trí không cùng datatype group/tương thích | Dùng `CAST`/hàm chuyển kiểu rõ ràng và thống nhất schema |
| Kết quả thiếu hàng sau khi ghép | Dùng `UNION` hoặc operator distinct trong khi cần giữ multiplicity | Xem lại yêu cầu; có thể cần `UNION ALL` |
| Kết quả `UNION` chỉ còn một hàng dù nguồn có nhiều bản ghi | Các hàng giống nhau trên toàn bộ cột được chọn | Chọn thêm khóa nếu cần phân biệt bản ghi, hoặc dùng `UNION ALL` |
| `MINUS` trả kết quả ngược kỳ vọng | Đặt sai thứ tự truy vấn trái/phải | Xác định rõ A trừ B hay B trừ A |
| Kết quả khác giữa phiên bản | Dùng cú pháp ALL/EXCEPT không được release hỗ trợ hoặc giả định precedence khác | Kiểm tra phiên bản và dùng ngoặc/CTE |
| `ORDER BY` lỗi trong compound query | Đặt ở nhánh giữa hoặc dùng biểu thức trực tiếp | Đặt một ORDER BY ở cuối; dùng alias/position hoặc bọc query ngoài |
| Kết quả không có thứ tự ổn định | Không có ORDER BY hoặc sort key không duy nhất | Thêm ORDER BY và khóa phụ phù hợp |
| Nghĩ UNION ALL luôn trả nhánh trái trước | Dựa vào thứ tự thực thi tình cờ | Đưa source-order vào kết quả và ORDER BY tường minh |
| Sort sai cột sau khi đổi select list | Dùng `ORDER BY 1`, `ORDER BY 2` phụ thuộc vị trí | Ưu tiên alias rõ ràng |
| Dữ liệu NULL bị gộp hoặc giao nhau ngoài dự đoán | Áp logic `=` trong WHERE vào set semantics | Hiểu quy tắc NULL của set operator; kiểm thử riêng |
| Query chạy nhưng tên cột kết quả không như mong muốn | Alias ở nhánh sau không đặt tên đầu ra | Đặt alias ở SELECT thành phần đầu tiên |

## 16. Ví dụ compound query nhiều operator

Giả sử cần tạo tập khách hàng thỏa các quy tắc:

1. Khách hàng có ở website hoặc cửa hàng.
2. Loại những khách đã bị khóa.
3. Chỉ giữ khách có trong danh sách xác minh.

Hãy đặt tên từng tập bằng CTE để biểu đạt ý định:

```sql
WITH all_signups AS (
    SELECT customer_id
    FROM lab_web_signups
    UNION
    SELECT customer_id
    FROM lab_store_signups
),
not_blocked AS (
    SELECT customer_id
    FROM all_signups
    MINUS
    SELECT customer_id
    FROM blocked_customers
),
verified AS (
    SELECT customer_id
    FROM not_blocked
    INTERSECT
    SELECT customer_id
    FROM verified_customers
)
SELECT customer_id
FROM verified
ORDER BY customer_id NULLS LAST;
```

`BLOCKED_CUSTOMERS` và `VERIFIED_CUSTOMERS` là bảng nghiệp vụ giả định, không thuộc lab đã tạo. CTE đặt tên từng bước giúp người đọc hiểu rõ thứ tự phép toán, tránh viết một chuỗi dài `UNION`, `MINUS`, `INTERSECT` mà phải tự suy luận cách nhóm.

### 16.1. Nếu muốn giữ số lần xuất hiện trong nguồn

Nếu mục tiêu là kiểm tra tổng số lần khách đăng ký, dùng `UNION ALL` và nhóm sau đó:

```sql
WITH all_signups AS (
    SELECT customer_id, 'WEB' AS source_name
    FROM lab_web_signups
    UNION ALL
    SELECT customer_id, 'STORE' AS source_name
    FROM lab_store_signups
)
SELECT customer_id,
       COUNT(*) AS signup_count,
       COUNT(CASE WHEN source_name = 'WEB' THEN 1 END) AS web_count,
       COUNT(CASE WHEN source_name = 'STORE' THEN 1 END) AS store_count
FROM all_signups
GROUP BY customer_id
ORDER BY customer_id NULLS LAST;
```

Ở đây `UNION ALL` bảo toàn các lần ghi nhận; `GROUP BY` sau đó mới tổng hợp số lần theo khách hàng. `COUNT(*)` đếm cả hàng có `CUSTOMER_ID = NULL`, còn `COUNT(customer_id)` sẽ bỏ qua giá trị null. Vì vậy hai cách đếm có thể cho kết quả khác nhau.

## 17. Bài thực hành có kiểm soát

Các bài tập dùng hai bảng lab đã tạo. Chỉ chạy trong schema DEV/TEST được cấp quyền và xác nhận đúng PDB/service. Những bài có `INTERSECT ALL` hoặc `MINUS ALL` yêu cầu release có hỗ trợ theo SQL Reference (Oracle 21c/26ai); nếu hệ thống lab là 19c, chỉ thực hành các operator cơ bản.

### Bài 1 — UNION và UNION ALL

```sql
SELECT customer_id
FROM lab_web_signups
UNION
SELECT customer_id
FROM lab_store_signups
ORDER BY customer_id NULLS LAST;
```

Đếm số hàng, sau đó đổi `UNION` thành `UNION ALL`. Giải thích vì sao kết quả tăng từ 6 lên 12 hàng.

### Bài 2 — Duplicate phụ thuộc select list

Chạy hai truy vấn:

```sql
SELECT customer_id
FROM lab_web_signups
UNION
SELECT customer_id
FROM lab_store_signups;

SELECT customer_id, display_name, region_code
FROM lab_web_signups
UNION
SELECT customer_id, display_name, region_code
FROM lab_store_signups;
```

Giải thích vì sao hai hàng có `CUSTOMER_ID = 102` nhưng tên khác nhau có thể vẫn xuất hiện riêng ở truy vấn thứ hai.

### Bài 3 — INTERSECT và MINUS

```sql
SELECT customer_id FROM lab_web_signups
INTERSECT
SELECT customer_id FROM lab_store_signups;

SELECT customer_id FROM lab_web_signups
MINUS
SELECT customer_id FROM lab_store_signups;

SELECT customer_id FROM lab_store_signups
MINUS
SELECT customer_id FROM lab_web_signups;
```

Ghi kết quả từng câu và giải thích vì sao đổi bên trái/phải của `MINUS` làm thay đổi kết quả.

### Bài 4 — ALL variants (Oracle 21c/26ai)

```sql
SELECT customer_id FROM lab_web_signups
INTERSECT ALL
SELECT customer_id FROM lab_store_signups;

SELECT customer_id FROM lab_web_signups
MINUS ALL
SELECT customer_id FROM lab_store_signups;
```

Đối chiếu số lần xuất hiện của `102` và `NULL` với bảng multiplicity ở phần 6. Không chạy cú pháp này trên môi trường 19c.

### Bài 5 — Độ ưu tiên

Chạy:

```sql
SELECT 1 AS id FROM dual
UNION
SELECT 2 FROM dual
INTERSECT
SELECT 2 FROM dual;
```

Sau đó viết lại bằng CTE để biểu đạt riêng hai cách nhóm `(A UNION B) INTERSECT C` và `A UNION (B INTERSECT C)`. Ghi lại vì sao dấu ngoặc/CTE làm ý định rõ hơn.

### Bài 6 — ORDER BY ở cuối

```sql
SELECT customer_id AS member_id, display_name AS member_name
FROM lab_web_signups
UNION ALL
SELECT customer_id, display_name
FROM lab_store_signups
ORDER BY member_id NULLS LAST, member_name;
```

Thử `ORDER BY 2, 1` rồi giải thích sự khác biệt. Không thêm `ORDER BY` vào giữa hai nhánh.

### Bài 7 — Giữ thứ tự nguồn tường minh

Viết truy vấn `UNION ALL` có `SOURCE_ORDER = 1` cho WEB và `SOURCE_ORDER = 2` cho STORE; bọc trong query ngoài và `ORDER BY SOURCE_ORDER, CUSTOMER_ID`. Sau đó thử bỏ `ORDER BY` và giải thích vì sao không thể dựa vào thứ tự mặc định.

### Bài 8 — Kiểm tra datatype

Chạy một câu có cột NUMBER ở nhánh đầu và VARCHAR2 ở nhánh sau để quan sát lỗi kiểu; sau đó sửa bằng `CAST` về cùng kiểu và giải thích vì sao chuyển đổi tường minh an toàn hơn implicit conversion qua nhóm dữ liệu.

### Thu dọn dữ liệu lab

Chỉ khi xác nhận đúng hai bảng do mình tạo trong DEV/TEST, không có bài thực hành khác sử dụng, có thể thu dọn:

```sql
DROP TABLE lab_web_signups PURGE;
DROP TABLE lab_store_signups PURGE;
```

`DROP TABLE ... PURGE` xóa bảng và dữ liệu, không đưa vào recycle bin; đây là thao tác DDL có implicit commit. Không chạy trên production hoặc trên bảng ngoài phạm vi lab.

## 18. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `UNION` và `UNION ALL` chỉ khác tốc độ | Khác semantics: một loại duplicate, một giữ mọi lần xuất hiện |
| `UNION` loại duplicate theo khóa chính bảng nguồn | Nó so sánh toàn bộ cột được SELECT |
| `INTERSECT` giữ số lần trùng | Dạng cơ bản trả distinct rows; dùng `INTERSECT ALL` khi release hỗ trợ và cần multiplicity |
| `MINUS` là phép trừ đối xứng | A MINUS B khác B MINUS A |
| `UNION ALL` luôn trả nhánh trái trước | Không có ORDER BY thì không bảo đảm thứ tự |
| `ORDER BY` ở nhánh đầu chỉ sắp nhánh đầu | Compound query dùng ORDER BY cuối để sắp toàn kết quả |
| Có thể dùng alias của nhánh thứ hai làm tên kết quả | Tên cột đầu ra dựa vào select list của nhánh đầu |
| ORDER BY có thể chứa biểu thức bất kỳ trong compound query | Dùng alias/position; nếu cần biểu thức khác, bọc query ngoài |
| Oracle luôn cho INTERSECT ưu tiên hơn UNION | Tài liệu hiện tại mô tả cùng độ ưu tiên, trái sang phải; hãy dùng ngoặc |
| `NULL` luôn không khớp với NULL trong mọi ngữ cảnh | Set operation có ngữ nghĩa duplicate/membership riêng cho NULL |
| Các operator ALL có trên mọi bản Oracle | 19c reference chỉ liệt kê operator cơ bản; 21c/26ai docs có thêm ALL variants và EXCEPT |
| ORDER BY tự loại duplicate | ORDER BY chỉ sắp xếp; việc loại duplicate do operator distinct quyết định |
| Thêm SOURCE vào SELECT không ảnh hưởng UNION | SOURCE làm các hàng khác nhau theo toàn tuple và có thể ngăn việc gộp duplicate |

## 19. Câu hỏi ôn tập

**Câu 1.** Hai nguồn có mã khách hàng `101, 102, 102` và `102, 103`. `UNION` trả bao nhiêu giá trị khác nhau?

**Đáp án:** Ba giá trị: `101`, `102`, `103`.

**Câu 2.** Với cùng dữ liệu, `UNION ALL` trả bao nhiêu hàng?

**Đáp án:** Năm hàng, vì giữ mọi lần xuất hiện của hai nguồn.

**Câu 3.** `UNION` loại duplicate dựa trên cột nào?

**Đáp án:** Toàn bộ các biểu thức trong select list; hai hàng chỉ bị coi là trùng khi các giá trị tương ứng của toàn bộ hàng được chọn trùng theo ngữ nghĩa set operation.

**Câu 4.** `INTERSECT` và `MINUS` cơ bản có giữ nhiều bản sao của một hàng không?

**Đáp án:** Không. Hai operator cơ bản trả kết quả distinct.

**Câu 5.** `MINUS` khác `INTERSECT` như thế nào?

**Đáp án:** `INTERSECT` trả hàng có trong cả hai tập; `MINUS` trả hàng chỉ có ở tập bên trái.

**Câu 6.** Nếu `A` có ba bản sao của `X`, `B` có một bản sao của `X`, `A MINUS ALL B` còn mấy bản sao `X`?

**Đáp án:** Hai, vì multiplicity còn lại là `MAX(3 - 1, 0)`.

**Câu 7.** Oracle hiện tại nhóm `A UNION B INTERSECT C` như thế nào khi không có ngoặc?

**Đáp án:** Các set operator có cùng độ ưu tiên và được đánh giá từ trái sang phải, tức `(A UNION B) INTERSECT C` theo tài liệu hiện tại. Nên dùng ngoặc/CTE để không phụ thuộc mặc định.

**Câu 8.** `ORDER BY` trong compound query đặt ở đâu?

**Đáp án:** Một lần ở cuối compound query; nó sắp xếp toàn bộ kết quả.

**Câu 9.** Vì sao `ORDER BY 2` có thể gây lỗi bảo trì?

**Đáp án:** Nó phụ thuộc vị trí cột; khi thay đổi select list, vị trí 2 có thể chuyển sang cột khác. Alias rõ ràng thường dễ đọc hơn.

**Câu 10.** Không có ORDER BY, `UNION ALL` có bảo đảm hàng từ nhánh đầu xuất hiện trước nhánh sau không?

**Đáp án:** Không. SQL không bảo đảm thứ tự kết quả nếu không có ORDER BY.

**Câu 11.** Hai query chọn `NUMBER` và `VARCHAR2` ở cùng vị trí có thể UNION trực tiếp không?

**Đáp án:** Không nếu khác datatype group; cần chuyển kiểu tường minh về cùng nhóm.

**Câu 12.** Nếu muốn sắp compound query theo `UPPER(name)` nhưng không muốn thêm cột đó vào kết quả distinct, nên làm gì?

**Đáp án:** Bọc compound query trong inline view rồi dùng `ORDER BY UPPER(name)` ở query ngoài.

## Kết luận

Set operator kết hợp **kết quả của nhiều câu SELECT**; `UNION` hợp và loại trùng, `UNION ALL` hợp và giữ mọi bản sao, `INTERSECT` lấy phần chung distinct, còn `MINUS` lấy phần chỉ có ở truy vấn trái. Trong các bản Oracle có hỗ trợ, `INTERSECT ALL` và `MINUS ALL` giữ multiplicity theo số lần xuất hiện; `EXCEPT` là tên thay thế của `MINUS` trong tài liệu các bản mới hơn. Duplicate được xét trên **toàn bộ tuple được SELECT**, vì vậy chọn cột nào ảnh hưởng trực tiếp số hàng kết quả.

Theo SQL Reference hiện hành, các set operator có cùng độ ưu tiên và được đánh giá trái sang phải nếu không có nhóm tường minh; Oracle có lưu ý về khả năng thay đổi độ ưu tiên `INTERSECT` trong tương lai. Hãy dùng ngoặc hoặc CTE khi trộn nhiều operator. Với `ORDER BY`, chỉ đặt một lần ở cuối compound query để sắp toàn bộ kết quả; dùng alias hoặc vị trí cột, thêm tiêu chí phụ khi cần thứ tự xác định và không dựa vào thứ tự nhánh khi thiếu `ORDER BY`.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c — The UNION [ALL], INTERSECT, MINUS Operators](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/The-UNION-ALL-INTERSECT-MINUS-Operators.html): bốn set operator cơ bản, quy tắc precedence, datatype, duplicate và các hạn chế.
- [Oracle Database 19c — Sorting Query Results](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Sorting-Query-Results.html): ORDER BY trong compound query, alias/vị trí và sắp xếp toàn bộ kết quả.
- [Oracle Database 21c — The Set Operators](https://docs.oracle.com/en/database/oracle/oracle-database/21/sqlrf/The-UNION-ALL-INTERSECT-MINUS-Operators.html): INTERSECT ALL, MINUS ALL, EXCEPT và EXCEPT ALL.
- [Oracle AI Database 26ai — The Set Operators](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/The-UNION-ALL-INTERSECT-MINUS-Operators.html): ngữ nghĩa set operator và các lưu ý phiên bản hiện hành.

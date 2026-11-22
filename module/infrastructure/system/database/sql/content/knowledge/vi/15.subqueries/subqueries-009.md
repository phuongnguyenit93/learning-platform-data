# Bẫy NOT IN khi truy vấn con trả về NULL

Một câu SQL rất tự nhiên khi cần “lấy các khách hàng **không thuộc** danh sách bị chặn” là:

```sql
SELECT customer_id
FROM customers
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM blocked_customers
);
```

Nhưng nếu truy vấn con trả về `NULL`, câu lệnh này có thể **không trả về bất kỳ khách hàng nào**, dù rõ ràng có khách không bị chặn. SQL không nhất thiết báo lỗi; kết quả đơn giản là rỗng. Đây là một bẫy đặc biệt nguy hiểm vì truy vấn trông hợp lý, vẫn chạy được và có thể làm báo cáo hoặc quy trình xử lý bỏ sót toàn bộ dữ liệu.

Nguyên nhân nằm ở **logic ba giá trị của SQL**: ngoài `TRUE` và `FALSE` còn có `UNKNOWN` khi so sánh với `NULL`. `NOT IN` không coi `NULL` trong truy vấn con là một giá trị có thể bỏ qua như nhiều người kỳ vọng.

Bài học thuộc **Database SQL → Truy vấn con**, phân tích kỹ ngữ nghĩa của `NOT IN (subquery)`, giải thích tại sao một `NULL` có thể ảnh hưởng tất cả hàng không khớp, cách dùng `NOT EXISTS` để diễn đạt “không tồn tại bản ghi liên quan”, và những trường hợp cần xử lý `NULL` ở cả **truy vấn ngoài** lẫn **truy vấn con**. Ví dụ có thể chạy trực tiếp trên **PostgreSQL**; các lưu ý chuyển hệ quản trị được trình bày riêng.

## 1. IN, NOT IN và truy vấn con trong WHERE

`IN` dùng để kiểm tra một giá trị có bằng ít nhất một giá trị trong danh sách hoặc kết quả truy vấn con hay không:

```sql
SELECT ...
FROM source_table AS s
WHERE s.key_column IN (
    SELECT t.key_column
    FROM other_table AS t
);
```

`NOT IN` diễn đạt điều kiện phủ định:

```sql
SELECT ...
FROM source_table AS s
WHERE s.key_column NOT IN (
    SELECT t.key_column
    FROM other_table AS t
);
```

Về mặt cú pháp, vế phải có thể là danh sách hằng:

```sql
WHERE customer_id NOT IN (2, 5, 8)
```

hoặc là truy vấn con trả về một cột:

```sql
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM blocked_customers
)
```

Khi truy vấn con trả về `2`, `5` và `8`, một khách có mã `1` không nằm trong danh sách và có thể được giữ lại. Vấn đề bắt đầu khi truy vấn con còn trả về **`NULL`**.

### Bảng giá trị đơn giản

Các biểu thức sau minh họa ngữ nghĩa SQL thông dụng và chạy trong PostgreSQL:

| Biểu thức | Kết quả logic |
| --- | --- |
| `1 IN (1, 2)` | TRUE |
| `1 NOT IN (1, 2)` | FALSE |
| `3 IN (1, 2)` | FALSE |
| `3 NOT IN (1, 2)` | TRUE |
| `1 IN (1, NULL)` | TRUE |
| `1 NOT IN (1, NULL)` | FALSE |
| `3 IN (1, NULL)` | UNKNOWN |
| `3 NOT IN (1, NULL)` | UNKNOWN |

Hàng cuối là trọng tâm: **`3 NOT IN (1, NULL)` không phải TRUE**, vì SQL không có đủ thông tin để xác nhận `3` khác mọi giá trị của danh sách. Một phần tử là `NULL` nên phép so sánh với phần tử đó là UNKNOWN.

## 2. Logic ba giá trị: vì sao NULL thay đổi kết quả?

Trong SQL, `NULL` biểu thị **không có giá trị xác định** trong ngữ cảnh một biểu thức. Nó không tự động bằng 0, bằng chuỗi rỗng hoặc bằng một giá trị thiếu khác.

Các phép so sánh thông thường khi có `NULL` tham gia thường cho `UNKNOWN`:

```sql
-- PostgreSQL
SELECT 1 = NULL::INTEGER AS one_equals_null,
       1 <> NULL::INTEGER AS one_differs_from_null,
       NULL::INTEGER = NULL::INTEGER AS two_nulls_equal;
```

Ba cột đều trả `NULL`, biểu diễn trạng thái logic UNKNOWN.

Bảng logic phủ định:

| Điều kiện `p` | `NOT p` |
| --- | --- |
| TRUE | FALSE |
| FALSE | TRUE |
| UNKNOWN | UNKNOWN |

Mệnh đề `WHERE` **chỉ giữ hàng khi điều kiện là TRUE**. Hàng có điều kiện FALSE hoặc UNKNOWN đều bị loại.

```sql
SELECT 1 AS example
WHERE 1 NOT IN (2, NULL);
```

Truy vấn trên trả **0 hàng**. Không phải vì mã 1 thật sự nằm trong danh sách; nguyên nhân là điều kiện `NOT IN` trả UNKNOWN.

### So sánh bằng NULL không trở thành FALSE

Một nhầm lẫn phổ biến:

> “Mã khách hàng là 1, mà NULL không phải 1, nên chắc chắn điều kiện 1 khác NULL là đúng.”

Trong logic SQL, `NULL` có thể đại diện một giá trị chưa được biết. Do đó `1 <> NULL` không khẳng định TRUE hay FALSE; nó là UNKNOWN.

Cách kiểm tra giá trị thiếu là `IS NULL` hoặc `IS NOT NULL`:

```sql
SELECT NULL::INTEGER IS NULL AS is_missing,
       1 IS NOT NULL AS known_number;
```

Hai biểu thức trả TRUE. Tuy nhiên, dùng `IS NULL` để kiểm tra **không có giá trị** khác với việc so sánh `=` hoặc `<>` giữa hai giá trị cụ thể.

## 3. NOT IN tương đương với “khác tất cả”, không phải “khác ít nhất một”

Hãy xét:

```sql
5 NOT IN (2, 3, NULL)
```

Trong logic SQL, ý nghĩa này tương đương với việc 5 phải **khác mọi phần tử**:

```sql
5 <> 2
AND 5 <> 3
AND 5 <> NULL
```

Từng phần:

- `5 <> 2` là TRUE.
- `5 <> 3` là TRUE.
- `5 <> NULL` là UNKNOWN.

Ghép lại:

```text
TRUE AND TRUE AND UNKNOWN = UNKNOWN
```

Vì vậy `5 NOT IN (2, 3, NULL)` là UNKNOWN và bị `WHERE` loại.

Nhưng nếu giá trị cần kiểm tra **thật sự xuất hiện** trong danh sách:

```sql
2 NOT IN (2, 3, NULL)
```

thì kết quả là FALSE, vì đã có phần tử `2` chắc chắn bằng giá trị bên trái. Tức là:

```text
2 <> 2     → FALSE
2 <> 3     → TRUE
2 <> NULL  → UNKNOWN

FALSE AND TRUE AND UNKNOWN → FALSE
```

**Với một danh sách có cả giá trị thông thường và `NULL`:**

- Hàng có giá trị **khớp một phần tử đã biết**: `NOT IN` trả FALSE.
- Hàng không khớp các giá trị đã biết: `NOT IN` thường trả UNKNOWN do còn phần tử `NULL`.
- Không có hàng nào thuộc hai nhóm trên được chọn bởi `WHERE`.

Đây là lý do một `NULL` trong truy vấn con có thể làm kết quả `NOT IN` rỗng hoàn toàn.

### NOT IN và <> ALL

Với truy vấn con trả về một cột, có thể hiểu:

```sql
x NOT IN (SELECT y FROM t)
```

tương đương về ý nghĩa với:

```sql
x <> ALL (SELECT y FROM t)
```

`ALL` đòi hỏi điều kiện `x <> y` đúng với **mọi** giá trị `y`. Nếu có giá trị `NULL` làm một lần so sánh thành UNKNOWN, và không có so sánh nào trả FALSE, kết quả chung là UNKNOWN.

`IN` thì tương ứng với một dạng kiểm tra `= ANY`: chỉ cần **ít nhất một** giá trị bằng nhau thật sự là đủ trả TRUE. Bởi vậy sự có mặt của `NULL` không ngăn `1 IN (1, NULL)` trả TRUE.

## 4. Thực hành PostgreSQL: thấy lỗi ngay trên dữ liệu mẫu

Tạo hai bảng tạm trong **một phiên PostgreSQL thực hành**:

- `candidate_customers_197`: các khách hàng đang được xét.
- `blocked_customers_197`: danh sách mã khách bị chặn; có một hàng mang `NULL`, tượng trưng dữ liệu nhập chưa hoàn thiện.

Bảng tạm chỉ tồn tại trong phiên kết nối. Nếu đã tạo cùng tên, mở phiên mới hoặc đổi tên trước khi chạy lại.

### Bước 1: Tạo bảng và nạp dữ liệu

```sql
CREATE TEMP TABLE candidate_customers_197 (
    candidate_row_id INTEGER PRIMARY KEY,
    customer_id      INTEGER,
    customer_name    TEXT NOT NULL
);

INSERT INTO candidate_customers_197
    (candidate_row_id, customer_id, customer_name)
VALUES
    (1, 1,    'An'),
    (2, 2,    'Bình'),
    (3, 3,    'Chi'),
    (4, 4,    'Dũng'),
    (5, NULL, 'Khách chưa gán mã'),
    (6, 5,    'Hà'),
    (7, 6,    'Lan');

CREATE TEMP TABLE blocked_customers_197 (
    block_row_id INTEGER PRIMARY KEY,
    customer_id  INTEGER,
    reason       TEXT NOT NULL
);

INSERT INTO blocked_customers_197
    (block_row_id, customer_id, reason)
VALUES
    (1, 2,    'Có yêu cầu chặn'),
    (2, 5,    'Tài khoản bị khóa'),
    (3, NULL, 'Dữ liệu nhập thiếu mã');
```

Quan sát:

```sql
SELECT candidate_row_id, customer_id, customer_name
FROM candidate_customers_197
ORDER BY candidate_row_id;

SELECT block_row_id, customer_id, reason
FROM blocked_customers_197
ORDER BY block_row_id;
```

Dữ liệu danh sách bị chặn là:

```text
customer_id
-----------
2
5
NULL
```

Các mã khách có giá trị xác định **không bị chặn** là `1`, `3`, `4`, `6`. Khách có `customer_id = NULL` chưa thể khẳng định danh tính của họ bằng một mã số cụ thể.

### Bước 2: Viết NOT IN theo trực giác

```sql
SELECT c.candidate_row_id,
       c.customer_id,
       c.customer_name
FROM candidate_customers_197 AS c
WHERE c.customer_id NOT IN (
    SELECT b.customer_id
    FROM blocked_customers_197 AS b
)
ORDER BY c.candidate_row_id;
```

**Kết quả: 0 hàng.**

Tại sao?

- Khách có mã `2` và `5`: bị loại vì khớp mã trong danh sách chặn, `NOT IN` = FALSE.
- Khách mã `1`, `3`, `4`, `6`: không khớp 2 hoặc 5, nhưng kết quả so với `NULL` là UNKNOWN, `NOT IN` = UNKNOWN.
- Khách chưa có mã (`customer_id = NULL`): phép kiểm tra với danh sách không rỗng cũng là UNKNOWN.

Vì `WHERE` chỉ chọn TRUE, không hàng nào được giữ. Đây là **kết quả đúng theo ngữ nghĩa SQL**, nhưng thường **không đúng ý định nghiệp vụ** của người viết truy vấn.

### Bước 3: Hiển thị kết quả ba giá trị thay vì chỉ lọc

Trong PostgreSQL, một cột boolean có giá trị UNKNOWN được thể hiện là SQL `NULL`:

```sql
SELECT c.candidate_row_id,
       c.customer_id,
       c.customer_id IN (
           SELECT b.customer_id
           FROM blocked_customers_197 AS b
       ) AS is_in_blocked_list,
       c.customer_id NOT IN (
           SELECT b.customer_id
           FROM blocked_customers_197 AS b
       ) AS is_not_in_blocked_list
FROM candidate_customers_197 AS c
ORDER BY c.candidate_row_id;
```

Kết quả về mặt logic:

| candidate_row_id | customer_id | `is_in_blocked_list` | `is_not_in_blocked_list` |
| ---: | ---: | --- | --- |
| 1 | 1 | UNKNOWN (`NULL`) | UNKNOWN (`NULL`) |
| 2 | 2 | TRUE | FALSE |
| 3 | 3 | UNKNOWN (`NULL`) | UNKNOWN (`NULL`) |
| 4 | 4 | UNKNOWN (`NULL`) | UNKNOWN (`NULL`) |
| 5 | `NULL` | UNKNOWN (`NULL`) | UNKNOWN (`NULL`) |
| 6 | 5 | TRUE | FALSE |
| 7 | 6 | UNKNOWN (`NULL`) | UNKNOWN (`NULL`) |

Có thể kiểm tra trực tiếp một biểu thức là UNKNOWN:

```sql
SELECT
    (1 NOT IN (2, NULL)) IS UNKNOWN AS is_unknown,
    (2 NOT IN (2, NULL)) IS FALSE   AS is_false;
```

Cả hai cột trả TRUE. Đừng hiểu “không có hàng trả về” là truy vấn không được thực thi; nó đã chạy và loại các hàng do logic điều kiện.

## 5. Cách sửa thứ nhất: loại NULL ở truy vấn con

Nếu yêu cầu nghiệp vụ là “so sánh khách với các **mã chặn đã xác định**”, có thể viết:

```sql
SELECT c.candidate_row_id,
       c.customer_id,
       c.customer_name
FROM candidate_customers_197 AS c
WHERE c.customer_id NOT IN (
    SELECT b.customer_id
    FROM blocked_customers_197 AS b
    WHERE b.customer_id IS NOT NULL
)
ORDER BY c.candidate_row_id;
```

Bây giờ truy vấn con trả `2`, `5`, **không còn `NULL`**. Kết quả gồm:

| candidate_row_id | customer_id | customer_name |
| ---: | ---: | --- |
| 1 | 1 | An |
| 3 | 3 | Chi |
| 4 | 4 | Dũng |
| 7 | 6 | Lan |

Khách chưa có mã (`candidate_row_id = 5`) không xuất hiện vì `NULL NOT IN (2,5)` vẫn là UNKNOWN.

### Cần xử lý cả NULL ở vế trái

Để thể hiện rõ ý định “chỉ lấy khách **đã có mã** và không có trong danh sách chặn”, hãy viết cả hai điều kiện:

```sql
SELECT c.candidate_row_id,
       c.customer_id,
       c.customer_name
FROM candidate_customers_197 AS c
WHERE c.customer_id IS NOT NULL
  AND c.customer_id NOT IN (
      SELECT b.customer_id
      FROM blocked_customers_197 AS b
      WHERE b.customer_id IS NOT NULL
  )
ORDER BY c.candidate_row_id;
```

Điều kiện ở truy vấn con bảo đảm không có mã chặn `NULL` gây UNKNOWN. Điều kiện ở truy vấn ngoài bảo đảm khách chưa được gán mã không bị coi là khách đã xác nhận không thuộc danh sách chặn.

**Hai kiểm tra `IS NOT NULL` có vai trò khác nhau**, dù trên dữ liệu mẫu hiện tại việc lọc `NULL` của truy vấn con đã khiến hàng ngoài có mã `NULL` bị loại.

### Khi nào cách này hợp lý?

Cách lọc `NULL` trong truy vấn con phù hợp nếu:

- Các hàng có mã chặn `NULL` được xác định là **dữ liệu lỗi/chưa hoàn thiện**, không thể dùng để chặn một mã khách cụ thể.
- Yêu cầu nghiệp vụ cho phép **bỏ qua các mã chặn chưa biết** trong phép so sánh.
- Bạn vẫn muốn dùng `NOT IN` vì ngữ nghĩa và hệ thống kiểu đã được kiểm soát.
- Mọi giá trị vế trái cần so sánh cũng được xác định rõ là khác `NULL`, hoặc chính sách xử lý riêng đã được viết.

Không nên áp dụng `WHERE b.customer_id IS NOT NULL` một cách máy móc nếu một hàng `NULL` trong bảng chặn có ý nghĩa khác, ví dụ “chặn tất cả khách chưa gán mã”. Khi ấy phải định nghĩa điều kiện nghiệp vụ riêng.

## 6. Cách sửa thường được ưu tiên: NOT EXISTS

`NOT EXISTS` kiểm tra **không tồn tại hàng nào** trong một truy vấn con **thỏa điều kiện tương quan** với hàng bên ngoài.

```sql
SELECT c.candidate_row_id,
       c.customer_id,
       c.customer_name
FROM candidate_customers_197 AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customers_197 AS b
    WHERE b.customer_id = c.customer_id
)
ORDER BY c.candidate_row_id;
```

Đây là một *correlated subquery* (truy vấn con tương quan): điều kiện `b.customer_id = c.customer_id` dùng cột `c` của hàng ở truy vấn ngoài.

Với mỗi khách:

1. Tìm trong bảng chặn xem có ít nhất một hàng mà `b.customer_id = c.customer_id` là TRUE hay không.
2. `EXISTS` trả TRUE nếu có hàng phù hợp, FALSE nếu không.
3. `NOT EXISTS` đảo kết quả TRUE/FALSE đó.
4. `WHERE` giữ khách nếu `NOT EXISTS` là TRUE.

**Một hàng trong bảng chặn có `customer_id = NULL` không tự làm nhiễm UNKNOWN cho toàn bộ điều kiện như `NOT IN`.** Nó chỉ không thỏa điều kiện `b.customer_id = c.customer_id` khi dùng phép `=` thông thường, vì phép so sánh cho UNKNOWN chứ không phải TRUE.

### Kết quả có một khác biệt quan trọng

Câu `NOT EXISTS` ở trên trả các hàng **1, 3, 4, 5, 7**. Nó bao gồm cả **candidate_row_id = 5**, nơi `c.customer_id` là `NULL`!

Tại sao? Với khách chưa có mã:

```sql
b.customer_id = NULL
```

không bao giờ TRUE cho bất kỳ hàng nào trong bảng chặn, kể cả hàng có `b.customer_id = NULL`. Vì vậy truy vấn con tương quan không trả hàng, `NOT EXISTS` là TRUE.

Nếu yêu cầu chỉ xét khách **có mã hợp lệ**, cần thêm điều kiện ngoài:

```sql
SELECT c.candidate_row_id,
       c.customer_id,
       c.customer_name
FROM candidate_customers_197 AS c
WHERE c.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM blocked_customers_197 AS b
      WHERE b.customer_id = c.customer_id
  )
ORDER BY c.candidate_row_id;
```

Kết quả là **1, 3, 4, 7** — đúng nhóm khách có mã `1`, `3`, `4`, `6`.

**Kết luận quan trọng:** `NOT EXISTS` giúp tránh bẫy `NULL` từ truy vấn con, nhưng **không tự đưa ra quyết định nghiệp vụ cho `NULL` ở cột bên ngoài**. Cần xác định xem khách thiếu mã nên được giữ, loại hay đưa vào nhóm kiểm tra riêng.

## 7. Vì sao EXISTS/NOT EXISTS không bị “NULL poisoning”?

`EXISTS (subquery)` chỉ kiểm tra **truy vấn con trả ít nhất một hàng hay không**. Nó không cần kết quả `SELECT` của hàng đó là số, chữ hay `NULL`.

```sql
-- PostgreSQL: truy vấn con có một hàng, dù giá trị chọn là NULL
SELECT EXISTS (
    SELECT NULL::INTEGER
) AS row_exists;
```

Kết quả là TRUE.

Ngược lại:

```sql
-- Truy vấn con không có hàng
SELECT EXISTS (
    SELECT NULL::INTEGER WHERE FALSE
) AS row_exists;
```

Kết quả là FALSE.

Trong mẫu anti-join:

```sql
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customers_197 AS b
    WHERE b.customer_id = c.customer_id
)
```

`SELECT 1` chỉ là một quy ước dễ đọc. Viết `SELECT *` cũng mang cùng ý nghĩa tồn tại hàng; nội dung cột được chọn không phải điều kiện quyết định `EXISTS`.

### Phép so sánh vẫn dùng logic ba giá trị

Cần phân biệt:

- `EXISTS`/`NOT EXISTS` tự trả kết quả TRUE/FALSE dựa trên **số hàng** của truy vấn con.
- Điều kiện `WHERE b.customer_id = c.customer_id` **bên trong** truy vấn con vẫn áp dụng logic ba giá trị; so sánh với `NULL` là UNKNOWN và không giữ hàng.

Vì vậy không nên kết luận “`NOT EXISTS` luôn coi hai `NULL` là khác nhau” theo một nghĩa nghiệp vụ duy nhất. Nó chỉ đang hỏi liệu có **hàng khớp theo điều kiện được viết** hay không.

## 8. So sánh NOT IN, NOT EXISTS và LEFT JOIN anti-join

Cùng yêu cầu “lấy khách có mã đã xác định và **không có mã chặn khớp**”, ta có ba lựa chọn SQL.

### 8.1. NOT IN với cả hai vế không NULL

```sql
SELECT c.candidate_row_id, c.customer_id
FROM candidate_customers_197 AS c
WHERE c.customer_id IS NOT NULL
  AND c.customer_id NOT IN (
      SELECT b.customer_id
      FROM blocked_customers_197 AS b
      WHERE b.customer_id IS NOT NULL
  )
ORDER BY c.candidate_row_id;
```

### 8.2. NOT EXISTS với khóa ngoài không NULL

```sql
SELECT c.candidate_row_id, c.customer_id
FROM candidate_customers_197 AS c
WHERE c.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM blocked_customers_197 AS b
      WHERE b.customer_id = c.customer_id
  )
ORDER BY c.candidate_row_id;
```

### 8.3. LEFT JOIN ... IS NULL

```sql
SELECT c.candidate_row_id, c.customer_id
FROM candidate_customers_197 AS c
LEFT JOIN blocked_customers_197 AS b
  ON b.customer_id = c.customer_id
WHERE c.customer_id IS NOT NULL
  AND b.block_row_id IS NULL
ORDER BY c.candidate_row_id;
```

Cả ba cách trả `candidate_row_id` **1, 3, 4, 7** với dữ liệu mẫu.

Ở cách thứ ba, `b.block_row_id` là **khóa chính không cho `NULL`** của bảng chặn. Nếu không có bản ghi b khớp, `LEFT JOIN` tạo giá trị `NULL` ở phía phải nên `b.block_row_id IS NULL` nhận diện hàng không khớp.

Không nên lấy một cột phía phải có thể `NULL` trên hàng **thật** để xác định có/không có bản ghi, đặc biệt nếu điều kiện nối cho phép khớp `NULL` theo quy tắc riêng. Khóa không nullable là dấu hiệu an toàn hơn để phát hiện không có hàng khớp sau `LEFT JOIN`.

### Chọn cách nào?

| Cách | Ưu điểm về cách đọc | Điểm phải lưu ý |
| --- | --- | --- |
| `NOT IN (subquery)` | Gọn, tự nhiên khi so sánh tập giá trị | `NULL` ở tập con có thể làm điều kiện UNKNOWN; vế ngoài cũng cần chính sách `NULL` |
| `NOT EXISTS` | Diễn đạt trực tiếp “không có bản ghi khớp” | Phải viết đúng điều kiện tương quan; xử lý `NULL` phía ngoài theo yêu cầu |
| `LEFT JOIN ... IS NULL` | Có thể phù hợp khi truy vấn đã dùng `LEFT JOIN` | Đặt predicate đúng trong `ON` và kiểm tra cột nhận diện hàng phải không nullable |

Không thể khẳng định một cách tuyệt đối rằng `NOT EXISTS` luôn nhanh hơn `NOT IN`. Bộ tối ưu của DBMS có thể chuyển các cấu trúc về anti-join hoặc chọn kế hoạch khác dựa trên thống kê và tính nullable. Lựa chọn đầu tiên nên theo **tính đúng đắn và khả năng diễn đạt**, rồi kiểm tra hiệu năng trên dữ liệu thực tế.

## 9. Trường hợp đặc biệt: truy vấn con rỗng

Một ngoại lệ quan trọng: `NOT IN` với **tập kết quả rỗng** trả TRUE, kể cả khi giá trị bên trái là `NULL`.

Định nghĩa logic:

> “Giá trị x khác **mọi** phần tử trong tập rỗng” là đúng vì không có phần tử nào phản bác điều kiện.

Quan sát trong PostgreSQL:

```sql
SELECT 1 NOT IN (
    SELECT 2 WHERE FALSE
) AS known_value_not_in_empty;

SELECT NULL::INTEGER NOT IN (
    SELECT 2 WHERE FALSE
) AS null_value_not_in_empty;
```

**Cả hai trả TRUE.**

Do đó không nên phát biểu quá rộng rằng “`NULL NOT IN (...)` luôn là UNKNOWN”. Điều đó đúng với nhiều **tập con không rỗng**, nhưng khi tập con rỗng, kết quả là TRUE.

### Tại sao điều này quan trọng cho bộ lọc IS NOT NULL?

Giả sử bạn đã sửa bẫy bằng cách lọc `NULL` ở truy vấn con:

```sql
WHERE c.customer_id NOT IN (
    SELECT b.customer_id
    FROM blocked_customers_197 AS b
    WHERE b.customer_id IS NOT NULL
      AND b.reason = 'Không tồn tại'
)
```

Ở dữ liệu mẫu, không có lý do `'Không tồn tại'` nên truy vấn con rỗng. Khi đó **ngay cả khách có `c.customer_id IS NULL` cũng qua được `NOT IN`**.

Muốn luôn loại khách chưa gán mã, phải đặt `c.customer_id IS NOT NULL` **tách biệt** ở `WHERE` ngoài:

```sql
SELECT c.candidate_row_id, c.customer_id
FROM candidate_customers_197 AS c
WHERE c.customer_id IS NOT NULL
  AND c.customer_id NOT IN (
      SELECT b.customer_id
      FROM blocked_customers_197 AS b
      WHERE b.customer_id IS NOT NULL
        AND b.reason = 'Không tồn tại'
  )
ORDER BY c.candidate_row_id;
```

Kết quả gồm mọi khách **có mã xác định** (1, 2, 3, 4, 5, 6), vì không có mã chặn nào trong tập điều kiện này.

Điểm rút ra: lọc `NULL` ở truy vấn con **không thay thế** chính sách kiểm tra `NULL` ở truy vấn ngoài.

## 10. Khi cả hai bên đều NULL: có muốn coi chúng là khớp không?

Một nghiệp vụ có thể định nghĩa hai giá trị thiếu là **cùng một trạng thái**, nhưng cũng có thể coi chúng là hai danh tính chưa biết và **không được ghép với nhau**.

Nếu muốn coi `NULL` của hai bên là cùng giá trị cho mục đích so khớp, PostgreSQL hỗ trợ `IS NOT DISTINCT FROM`:

```sql
SELECT c.candidate_row_id, c.customer_id
FROM candidate_customers_197 AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customers_197 AS b
    WHERE b.customer_id IS NOT DISTINCT FROM c.customer_id
)
ORDER BY c.candidate_row_id;
```

Bởi vì bảng chặn chứa một hàng `customer_id = NULL`, truy vấn con giờ **có thể khớp** với khách bên ngoài có mã `NULL`. Do đó khách chưa gán mã không được trả về. Kết quả còn **1, 3, 4, 7**.

So sánh:

| Điều kiện tương quan | `NULL` bên ngoài có khớp `NULL` bên trong không? |
| --- | --- |
| `b.customer_id = c.customer_id` | Không; so sánh là UNKNOWN |
| `b.customer_id IS NOT DISTINCT FROM c.customer_id` | Có; trả TRUE khi cả hai `NULL` |

Với nhiều hệ thống khách hàng, “cùng không có customer_id” **không chứng minh** hai hàng thuộc cùng khách. Do đó việc dùng so sánh an toàn với `NULL` cần có cơ sở từ hợp đồng dữ liệu, không nên chỉ dùng để nhận kết quả mong muốn.

Một cách viết rõ hơn khi yêu cầu chỉ kiểm tra những khách có ID là **giữ `c.customer_id IS NOT NULL`**, thay vì cố xác định hai giá trị `NULL` có khớp nhau hay không.

## 11. Lỗi khác: quên điều kiện tương quan trong NOT EXISTS

`NOT EXISTS` chỉ đúng nếu truy vấn con kiểm tra **mối liên hệ với từng hàng ngoài**.

Ví dụ **sai mục tiêu**:

```sql
SELECT c.candidate_row_id
FROM candidate_customers_197 AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customers_197 AS b
)
ORDER BY c.candidate_row_id;
```

Truy vấn con ở đây **không có điều kiện tham chiếu `c`**. Vì bảng chặn có ít nhất một hàng, `EXISTS` luôn TRUE và `NOT EXISTS` luôn FALSE cho mọi khách. Kết quả lại là 0 hàng — nhưng lần này vì truy vấn con không tương quan, **không phải** vì `NULL`.

Một lỗi tinh vi hơn:

```sql
-- Sai nếu muốn tìm mã khách không nằm trong danh sách bị chặn
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customers_197 AS b
    WHERE b.customer_id IS NOT NULL
)
```

Truy vấn con vẫn chỉ hỏi “bảng chặn có bất kỳ mã khác `NULL` nào không?”, chứ không hỏi “bảng chặn có mã nào **bằng mã của khách hiện tại** không?”.

Cách đúng cần chứa điều kiện:

```sql
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customers_197 AS b
    WHERE b.customer_id = c.customer_id
)
```

Hãy đọc `NOT EXISTS` thành câu tiếng Việt:

> “Giữ khách c **nếu không tồn tại** hàng b **có customer_id bằng customer_id của c**.”

Nếu không thể nói rõ **hàng bên trong khớp hàng bên ngoài theo cột nào**, câu truy vấn có thể chưa diễn đạt đúng yêu cầu.

## 12. Cẩn thận với AND/OR trong truy vấn con

Giả sử danh sách chặn còn có trạng thái hiệu lực. Mục tiêu là loại khách có một bản ghi chặn **đang hiệu lực**, không loại khách chỉ có bản ghi hết hiệu lực.

Ví dụ cú pháp minh họa, giả định bảng `blocked_records` có các cột `customer_id`, `is_active`:

```sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_records AS b
    WHERE b.customer_id = c.customer_id
      AND b.is_active = TRUE
);
```

Điều kiện `b.customer_id = c.customer_id` và `b.is_active = TRUE` phải **cùng đúng trên một hàng b** để hàng ngoài bị loại.

Khi điều kiện phức tạp:

```sql
WHERE b.customer_id = c.customer_id
  AND (
       b.is_active = TRUE
       OR b.block_reason = 'PERMANENT'
  )
```

dấu ngoặc bảo đảm quy tắc “đúng khách và (chặn đang hiệu lực hoặc chặn vĩnh viễn)”.

Nếu bỏ ngoặc:

```sql
-- Sai ý nghĩa: một bản ghi PERMANENT của khách khác có thể làm subquery có hàng
WHERE b.customer_id = c.customer_id
  AND b.is_active = TRUE
   OR b.block_reason = 'PERMANENT'
```

do `AND` có ưu tiên cao hơn `OR`, một bản ghi `PERMANENT` của **bất cứ khách nào** có thể làm `NOT EXISTS` trả FALSE đối với mọi khách. Đây là bẫy khác trong anti-join, độc lập với `NULL` nhưng dễ xuất hiện khi sửa câu SQL có nhiều điều kiện.

## 13. Khóa ghép và NOT IN nhiều cột

Trong ứng dụng đa tenant, một đối tượng có thể được nhận diện bởi **hai cột** `(tenant_id, order_id)` thay vì một cột `order_id`.

Một số hệ quản trị, trong đó có PostgreSQL, cho phép so sánh hàng (*row value*) trong `NOT IN`:

```sql
-- PostgreSQL
SELECT o.tenant_id, o.order_id
FROM orders AS o
WHERE (o.tenant_id, o.order_id) NOT IN (
    SELECT b.tenant_id, b.order_id
    FROM blocked_orders AS b
);
```

Cú pháp trên chỉ là ví dụ khi hai bảng có tồn tại. Nếu **một trong các thành phần khóa có thể `NULL`**, phép so sánh hàng cũng chịu ảnh hưởng của logic ba giá trị. Một giá trị `NULL` ở truy vấn con **có thể** làm một số cặp không khớp trở thành UNKNOWN.

Điểm tinh tế: với nhiều cột, một cặp hàng có thể được xác định **khác nhau chắc chắn** nhờ một cột đã biết không bằng nhau, dù cột khác mang `NULL`. Vì vậy không nên khẳng định một hàng có `NULL` trong truy vấn con sẽ luôn làm **mọi** hàng ngoài trả UNKNOWN trong phép so sánh khóa ghép. Hành vi cụ thể phụ thuộc từng cặp giá trị.

### Thể hiện khóa ghép bằng NOT EXISTS

Thường dễ kiểm soát hơn khi viết:

```sql
SELECT o.tenant_id, o.order_id
FROM orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_orders AS b
    WHERE b.tenant_id = o.tenant_id
      AND b.order_id  = o.order_id
);
```

Cả hai thành phần khóa phải cùng khớp. Không được chỉ nối theo `order_id` nếu nhiều tenant có thể dùng cùng một mã đơn.

Nếu `tenant_id` hoặc `order_id` có thể `NULL`, vẫn phải xác định chính sách như ở phần trước. Nếu chúng là khóa chính không `NULL`, ngữ nghĩa “không tồn tại cặp khóa tương ứng” rõ ràng hơn.

### Ví dụ thực hành không cần bảng ngoài

```sql
WITH orders(tenant_id, order_id) AS (
    VALUES ('T1'::TEXT, 101), ('T1', 102), ('T2', 101)
),
blocked(tenant_id, order_id) AS (
    VALUES ('T1'::TEXT, 101)
)
SELECT o.tenant_id, o.order_id
FROM orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked AS b
    WHERE b.tenant_id = o.tenant_id
      AND b.order_id = o.order_id
)
ORDER BY o.tenant_id, o.order_id;
```

Kết quả là **(T1,102)** và **(T2,101)**. Dù cùng `order_id = 101`, đơn T2–101 không bị loại vì không phải của tenant T1.

## 14. EXCEPT và phép trừ tập hợp: không hoàn toàn giống NOT IN

Một cách khác để tìm các giá trị có ở tập A nhưng không có ở tập B là `EXCEPT` (ở DBMS hỗ trợ):

```sql
SELECT customer_id
FROM candidate_customers_197
EXCEPT
SELECT customer_id
FROM blocked_customers_197;
```

Với dữ liệu thực hành, kết quả là các ID `1`, `3`, `4`, `6`.

Vì sao không có `NULL` trong kết quả? Trong phép toán tập hợp như `EXCEPT`, hệ quản trị áp dụng ngữ nghĩa xác định giá trị hàng **trùng nhau để khử tập hợp**, trong đó các hàng có `NULL` tương ứng được xem là cùng giá trị cho mục đích khử trùng. Danh sách chặn cũng có `NULL` nên giá trị thiếu đó được trừ khỏi tập khách.

**Không được suy luận từ `EXCEPT` rằng `NULL = NULL` trả TRUE trong `WHERE`.** Đây là hai ngữ cảnh SQL khác nhau.

Ngoài ra, `EXCEPT` trên một cột:

- Chỉ trả về giá trị `customer_id`, không tự mang theo `customer_name` hoặc các cột khác.
- Mặc định hoạt động theo ngữ nghĩa tập hợp, thường **loại trùng** các giá trị đầu ra.
- Không tương đương với anti-join cần giữ **mọi hàng ứng viên** khi có nhiều khách cùng một mã hoặc khi cần giữ dữ liệu chi tiết.
- Có cú pháp/mức hỗ trợ khác nhau giữa các DBMS và phiên bản.

Nếu yêu cầu là “giữ nguyên từng hàng khách hàng với tên và các thông tin khác, trừ những hàng khớp danh sách chặn”, `NOT EXISTS` thường diễn đạt trực tiếp hơn.

## 15. NULL lọt vào truy vấn con bằng những con đường nào?

Một bảng có thể được thiết kế với cột mã `NOT NULL`, nhưng điều đó **không bảo đảm mọi biểu thức trong truy vấn con đều khác `NULL`**.

Một số tình huống:

### 15.1. Cột nguồn cho phép NULL

```sql
SELECT b.customer_id
FROM blocked_customers_197 AS b;
```

Trong bảng mẫu, `customer_id` không có ràng buộc `NOT NULL` nên một hàng mang `NULL` là hợp lệ theo schema tạm.

### 15.2. LEFT JOIN tạo NULL dù cột gốc NOT NULL

Giả sử bảng bên phải có khóa chính không `NULL`, nhưng không tìm thấy hàng khớp:

```sql
SELECT b.customer_id
FROM source_records AS s
LEFT JOIN blocked_customers AS b
  ON b.customer_id = s.customer_id;
```

Các hàng phía trái không khớp sẽ có `b.customer_id = NULL` trong **kết quả join**, kể cả khi cột gốc `blocked_customers.customer_id` là `NOT NULL`. Vì vậy, nếu đưa biểu thức đó vào `NOT IN` ở một truy vấn khác, bẫy `NULL` vẫn có thể xuất hiện.

Tên `source_records` và `blocked_customers` ở đây chỉ là bảng minh họa trong một hệ thống khác, không phải các bảng được tạo trong bài thực hành.

### 15.3. CASE, NULLIF hoặc hàm chuyển đổi sinh NULL

```sql
SELECT NULLIF(b.customer_id, 0) AS normalized_id
FROM blocked_customers_197 AS b;
```

Nếu có mã `0`, biểu thức `NULLIF(...,0)` sẽ chuyển nó thành `NULL`. Còn `CASE ... ELSE NULL END` hoặc kết quả của một phép tính trên dữ liệu thiếu cũng có thể sinh `NULL`.

Đừng chỉ kiểm tra định nghĩa kiểu của một cột gốc. Hãy nhìn **biểu thức thực sự trong SELECT của truy vấn con**, các phép nối và bộ lọc tạo ra tập so sánh.

### 15.4. Tham số ứng dụng và danh sách tạm

Một danh sách mã được truyền từ ứng dụng có thể chứa `NULL` hoặc được mở rộng thành một bảng tạm chứa `NULL`. Nếu ứng dụng tạo câu:

```sql
WHERE customer_id NOT IN (2, 5, NULL)
```

thì vẫn có cùng vấn đề. Đây không chỉ là bẫy của truy vấn con; truy vấn con khiến nó khó nhận ra hơn vì dữ liệu danh sách có thể thay đổi theo thời gian.

## 16. NOT IN có thể đúng khi nào?

`NOT IN` **không phải một toán tử sai**. Nó hoạt động rõ ràng khi giá trị so sánh được xác định và tập so sánh không có `NULL`.

Ví dụ:

```sql
SELECT c.candidate_row_id, c.customer_id
FROM candidate_customers_197 AS c
WHERE c.customer_id IS NOT NULL
  AND c.customer_id NOT IN (2, 5)
ORDER BY c.candidate_row_id;
```

Kết quả là 1, 3, 4, 7.

`NOT IN` cũng phù hợp khi truy vấn con chọn một cột **được chứng minh không thể NULL**, ví dụ khóa chính không nullable, và vế ngoài được xử lý theo chính sách rõ ràng:

```sql
SELECT c.customer_id
FROM candidate_customers_197 AS c
WHERE c.customer_id IS NOT NULL
  AND c.customer_id NOT IN (
      SELECT b.block_row_id
      FROM blocked_customers_197 AS b
  );
```

Câu này chỉ minh họa việc `block_row_id` là khóa chính không `NULL`. **Nó không thực hiện yêu cầu tìm khách không bị chặn**, vì đang so customer ID với mã hàng `block_row_id`, hai khái niệm khác nhau. Điều kiện loại trừ chỉ đúng khi **hai cột thực sự thuộc cùng miền định danh**. Không được đổi cột chỉ để tránh `NULL` mà bỏ qua ngữ nghĩa quan hệ.

Một thiết kế phù hợp hơn cho hệ thống thật là đặt mã khách bị chặn là `NOT NULL` nếu **mọi bản ghi chặn đều bắt buộc gắn với một khách có ID**. Hàng dữ liệu chưa xác định ID nên được xử lý ở luồng nhập liệu/kiểm tra riêng, thay vì âm thầm đưa `NULL` vào tập ID dùng để lọc.

### Bảo đảm ở schema và ở truy vấn

Hai cách bổ trợ nhau:

- **Schema:** ràng buộc `NOT NULL`, khóa ngoại và quy tắc nhập liệu khi phù hợp.
- **Truy vấn:** `IS NOT NULL` ở vế ngoài hoặc tập con khi chính sách lọc yêu cầu; hoặc dùng `NOT EXISTS` với điều kiện tương quan rõ ràng.

Ràng buộc schema mạnh có thể làm các truy vấn ngắn gọn và cho trình tối ưu thêm thông tin, nhưng biểu thức dẫn xuất và outer join vẫn phải được xem xét.

## 17. Viết truy vấn an toàn trong báo cáo và nghiệp vụ

Một hệ thống phân nhóm khách hàng có thể cần nhiều nhãn khác nhau:

- `blocked`: mã khách có bản ghi chặn khớp.
- `not_blocked`: mã khách đã biết và không có bản ghi chặn khớp.
- `unknown_customer_id`: khách chưa có mã, không đủ thông tin để khẳng định thuộc nhóm nào.

Thay vì lọc mà làm mất nhóm thứ ba, có thể trả **cột trạng thái**:

```sql
SELECT c.candidate_row_id,
       c.customer_id,
       c.customer_name,
       CASE
           WHEN c.customer_id IS NULL THEN 'unknown_customer_id'
           WHEN EXISTS (
               SELECT 1
               FROM blocked_customers_197 AS b
               WHERE b.customer_id = c.customer_id
           ) THEN 'blocked'
           ELSE 'not_blocked'
       END AS customer_block_status
FROM candidate_customers_197 AS c
ORDER BY c.candidate_row_id;
```

Kết quả:

| candidate_row_id | customer_id | customer_block_status |
| ---: | ---: | --- |
| 1 | 1 | not_blocked |
| 2 | 2 | blocked |
| 3 | 3 | not_blocked |
| 4 | 4 | not_blocked |
| 5 | `NULL` | unknown_customer_id |
| 6 | 5 | blocked |
| 7 | 6 | not_blocked |

Đây là cách thể hiện **ba trạng thái nghiệp vụ** một cách tường minh, không đánh đồng khách thiếu ID với khách chắc chắn không có trong danh sách chặn.

Muốn lọc chỉ những khách đã xác định không bị chặn, có thể dùng truy vấn `NOT EXISTS` ở mục 6. Muốn giữ cả khách thiếu mã để xác minh thủ công, cần một quy trình xử lý riêng thay vì coi họ “không bị chặn” theo mặc định.

## 18. Hiệu năng: không tối ưu dựa trên khẩu hiệu

Có lời khuyên phổ biến “luôn thay `NOT IN` bằng `NOT EXISTS` vì nhanh hơn”. Cách nói này không đủ chính xác cho mọi DBMS và mọi loại dữ liệu.

Những điều thực sự ảnh hưởng tới kế hoạch truy vấn gồm:

- Bảng ngoài và bảng trong có bao nhiêu hàng.
- Có index trên khóa tương quan hay không.
- Cột có ràng buộc `NOT NULL` hay không.
- Bộ lọc trong truy vấn con có độ chọn lọc thế nào.
- Có một hay nhiều cột làm khóa quan hệ.
- Truy vấn con có tương quan, hàm phức tạp hoặc phép chuyển kiểu hay không.
- Khả năng tối ưu `NOT IN`, `NOT EXISTS` thành anti-join của từng DBMS/phiên bản.

Trong PostgreSQL, có thể quan sát kế hoạch bằng:

```sql
EXPLAIN
SELECT c.candidate_row_id
FROM candidate_customers_197 AS c
WHERE c.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM blocked_customers_197 AS b
      WHERE b.customer_id = c.customer_id
  );
```

Tùy thống kê và kích thước dữ liệu, optimizer có thể chọn hash anti join, nested loop anti join hoặc kế hoạch thích hợp khác. Với bảng thực hành rất nhỏ, quét tuần tự vẫn có thể là quyết định hiệu quả.

**Ưu tiên thứ tự:** đúng ngữ nghĩa → dễ đọc và kiểm soát `NULL` → đo hiệu năng thực tế → tối ưu nếu cần. Không thay một phép lọc sai ngữ nghĩa bằng một phép lọc “nhanh” hơn.

## 19. Khác biệt và lưu ý theo DBMS

| Hệ quản trị | Điều cần nhớ |
| --- | --- |
| **PostgreSQL** | `NOT IN` và phép so sánh với `NULL` theo logic ba giá trị; `NOT EXISTS` là cách thường dùng cho anti-join. Có `IS [NOT] DISTINCT FROM` để so sánh an toàn với `NULL`. |
| **MySQL** | `NOT IN` với `NULL` cũng cần thận trọng. MySQL hỗ trợ toán tử so sánh an toàn với `NULL` là `<=>` khi nghiệp vụ cần khớp cả hai `NULL`. |
| **SQL Server** | Với ngữ nghĩa so sánh `NULL` thông thường, `NOT IN` có bẫy tương tự. Các quy tắc lịch sử liên quan `ANSI_NULLS` có thể ảnh hưởng một số môi trường cũ; không nên dựa vào cấu hình để thay thế logic truy vấn rõ ràng. |
| **Oracle Database** | `NULL` trong kết quả truy vấn con có thể làm `NOT IN` không chọn các hàng không khớp theo cách người viết mong đợi. Trong Oracle, chuỗi ký tự độ dài 0 thường được xử lý như `NULL`, nên dữ liệu chuỗi thiếu càng cần lưu ý. |
| **SQLite** | `NOT IN` có các trường hợp `NULL` và tập rỗng tương tự cần chú ý; SQLite có typing động, nên vẫn phải đảm bảo so sánh các mã định danh tương thích về kiểu. |

Các phiên bản và tính năng tối ưu có thể khác nhau, nhưng lời giải thích dựa trên **TRUE/FALSE/UNKNOWN** là cách hiểu phù hợp cho các ví dụ phổ biến. Không nên cho rằng mọi hệ quản trị sẽ tự bỏ các `NULL` khỏi truy vấn con trước khi đánh giá `NOT IN`.

## 20. Những lỗi thường gặp và cách nhận diện

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `NOT IN (SELECT id ...)` trả 0 hàng bất ngờ | Truy vấn con có ít nhất một `NULL` | Kiểm tra `IS NULL` ở kết quả truy vấn con; cân nhắc `NOT EXISTS` hoặc lọc `NULL` có chủ đích |
| Không thấy khách thiếu ID trong kết quả | Vế trái là `NULL` và tập con không rỗng | Quy định chính sách vế trái: lọc, giữ hay phân nhóm riêng |
| Sau khi lọc `NULL` ở truy vấn con, khách thiếu ID bỗng xuất hiện | Truy vấn con trở thành **rỗng** | Thêm `c.customer_id IS NOT NULL` nếu chỉ muốn khách có ID |
| `NOT EXISTS` lại giữ khách có `customer_id = NULL` | Phép `=` với `NULL` không tạo hàng khớp trong subquery | Xử lý `NULL` vế ngoài rõ ràng |
| `NOT EXISTS` trả 0 hàng với mọi khách | Quên điều kiện tương quan và bảng trong không rỗng | Đảm bảo có `b.customer_id = c.customer_id` |
| Dùng `<> ALL` vẫn gặp UNKNOWN | `<> ALL` có ngữ nghĩa tương tự `NOT IN` | Cần giải quyết `NULL`, không chỉ đổi cú pháp |
| Dùng `COALESCE(id,-1)` để khớp NULL gây nhầm mã | Giá trị `-1` có thể là mã thật hoặc đổi ý nghĩa “chưa biết” | Dùng chính sách khóa rõ ràng, `IS NOT DISTINCT FROM` nếu thực sự cần null-safe match |
| `LEFT JOIN` lọc `right.some_nullable_column IS NULL` cho kết quả thừa | Cột đó có thể `NULL` trên hàng phải thực | Kiểm tra khóa nhận diện bên phải không nullable |
| Chuyển sang `EXCEPT` làm mất các hàng trùng | `EXCEPT` mặc định dùng ngữ nghĩa tập hợp | Dùng `NOT EXISTS` khi cần giữ từng hàng nguồn |
| Anti-join sai tenant | Điều kiện tương quan chỉ có `order_id`, thiếu `tenant_id` | Ghép đủ khóa tổng hợp |
| Truy vấn bị chậm | Thiếu index, tập dữ liệu lớn hoặc predicate phức tạp | Đo `EXPLAIN`, xem index và thống kê; tránh khẳng định cú pháp nào luôn nhanh |
| `IS NULL` ở bảng gốc không có nhưng subquery vẫn trả NULL | `LEFT JOIN`, `CASE`, `NULLIF`, biểu thức dẫn xuất | Kiểm tra **giá trị đầu ra thực của subquery**, không chỉ định nghĩa cột nguồn |

## 21. Bài tập thực hành

Dùng hai bảng tạm `candidate_customers_197` và `blocked_customers_197` của mục 4. Hãy **dự đoán kết quả bằng logic ba giá trị trước khi chạy**.

### Bài 1. Phân biệt TRUE, FALSE, UNKNOWN

Dự đoán:

```sql
SELECT
    1 NOT IN (2, 5) AS a,
    1 NOT IN (2, 5, NULL) AS b,
    2 NOT IN (2, 5, NULL) AS c,
    NULL::INTEGER NOT IN (2, 5) AS d;
```

Giải thích từng cột bằng ý nghĩa “khác tất cả”.

### Bài 2. Truy vấn con chứa NULL

Viết `NOT IN` để tìm khách không nằm trong `blocked_customers_197` mà không lọc `NULL`. Có bao nhiêu hàng? Vì sao?

### Bài 3. Lọc NULL đúng phía

Viết lại bài 2 để:

- Bỏ qua `customer_id IS NULL` trong danh sách chặn.
- Không chọn khách có `customer_id IS NULL`.
- Giữ các hàng khách không có mã chặn khớp.

Dự đoán `candidate_row_id` nhận được.

### Bài 4. Chuyển sang NOT EXISTS

Viết truy vấn tương quan dùng `NOT EXISTS`, trước tiên **không** kiểm tra `c.customer_id IS NOT NULL`, sau đó thêm kiểm tra. Hai kết quả khác nhau ở hàng nào? Vì sao?

### Bài 5. Tập con rỗng

Dự đoán:

```sql
SELECT NULL::INTEGER NOT IN (
    SELECT 1 WHERE FALSE
) AS result_for_null;
```

Kết quả là TRUE, FALSE hay UNKNOWN?

### Bài 6. NOT EXISTS không tương quan

Câu sau trả những hàng nào?

```sql
SELECT c.candidate_row_id
FROM candidate_customers_197 AS c
WHERE NOT EXISTS (
    SELECT 1 FROM blocked_customers_197
);
```

Giải thích lỗi về mối quan hệ giữa hai bảng.

### Bài 7. So sánh NULL với NULL theo yêu cầu nghiệp vụ

Dùng `IS NOT DISTINCT FROM` trong `NOT EXISTS` để coi mã `NULL` ở hai phía là khớp. Kết quả khác truy vấn dùng `=` ở khách nào? Khi nào cách so khớp này là sai về nghiệp vụ?

### Bài 8. LEFT JOIN anti-join

Viết một `LEFT JOIN` giữa ứng viên và danh sách chặn, chỉ giữ khách có mã xác định mà không có hàng chặn. Sử dụng `b.block_row_id IS NULL` để phát hiện không khớp.

### Bài 9. Dữ liệu nhập có NULL bất ngờ

Viết câu `SELECT` xác định xem bảng chặn có bao nhiêu hàng có `customer_id IS NULL` và bao nhiêu hàng có mã đã biết. Đề xuất một cách xử lý dữ liệu thiếu mà không bỏ qua trách nhiệm làm sạch dữ liệu nguồn.

### Bài 10. Khóa ghép nhiều tenant

Với:

```text
orders:   (T1,101), (T1,102), (T2,101)
blocked:  (T1,101)
```

Viết `NOT EXISTS` trả các đơn không nằm trong danh sách chặn theo **cả tenant_id và order_id**. Vì sao không được chỉ so `order_id`?

### Bài 11. EXCEPT và giữ chi tiết hàng

Chạy `EXCEPT` trên hai tập `customer_id`. So sánh tập mã nhận được với kết quả `NOT EXISTS`. Nếu cần giữ `customer_name` và từng hàng ứng viên, nên dùng cách nào?

### Bài 12. Định nghĩa trạng thái nghiệp vụ

Tạo một cột `customer_block_status` bằng `CASE` có ba nhãn: `'blocked'`, `'not_blocked'` và `'unknown_customer_id'`. Yêu cầu giữ **cả bảy hàng** để thấy sự khác nhau giữa khách có mã, khách bị chặn và khách chưa gán mã.

## 22. Gợi ý đáp án

### Bài 1

- `a = TRUE`: 1 khác cả 2 và 5.
- `b = UNKNOWN`: khác 2 và 5 nhưng không thể xác định so với `NULL`.
- `c = FALSE`: 2 có trong danh sách, nên phủ định `IN` là FALSE.
- `d = UNKNOWN`: vế trái `NULL` so với danh sách không rỗng không tạo được kết luận khác tất cả.

### Bài 2

```sql
SELECT c.candidate_row_id, c.customer_id
FROM candidate_customers_197 AS c
WHERE c.customer_id NOT IN (
    SELECT b.customer_id
    FROM blocked_customers_197 AS b
)
ORDER BY c.candidate_row_id;
```

Kết quả **0 hàng** vì tập con gồm `2, 5, NULL`: các mã 2/5 bị loại bằng FALSE; các mã còn lại gặp UNKNOWN.

### Bài 3

```sql
SELECT c.candidate_row_id, c.customer_id
FROM candidate_customers_197 AS c
WHERE c.customer_id IS NOT NULL
  AND c.customer_id NOT IN (
      SELECT b.customer_id
      FROM blocked_customers_197 AS b
      WHERE b.customer_id IS NOT NULL
  )
ORDER BY c.candidate_row_id;
```

Kết quả `candidate_row_id` là **1, 3, 4, 7**.

### Bài 4

```sql
SELECT c.candidate_row_id, c.customer_id
FROM candidate_customers_197 AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customers_197 AS b
    WHERE b.customer_id = c.customer_id
)
ORDER BY c.candidate_row_id;
```

Kết quả là **1, 3, 4, 5, 7**. Thêm `c.customer_id IS NOT NULL` ở `WHERE` ngoài thì loại hàng 5, còn **1, 3, 4, 7**. Vì `NULL = NULL` không trả TRUE nên `NOT EXISTS` thông thường không thấy hàng khớp cho mã ngoài `NULL`.

### Bài 5

Kết quả **TRUE**: truy vấn con không có hàng nào nên điều kiện `NOT IN` được thỏa mãn trên tập rỗng, ngay cả khi vế trái là `NULL`.

### Bài 6

Kết quả **0 hàng**: bảng chặn không rỗng nên truy vấn con có hàng với **mọi ứng viên**. `NOT EXISTS` trả FALSE vì không có điều kiện tương quan đến `c`.

### Bài 7

```sql
SELECT c.candidate_row_id, c.customer_id
FROM candidate_customers_197 AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customers_197 AS b
    WHERE b.customer_id IS NOT DISTINCT FROM c.customer_id
)
ORDER BY c.candidate_row_id;
```

Kết quả **1, 3, 4, 7**. Khách có mã `NULL` (hàng 5) bị loại vì khớp hàng chặn có mã `NULL` theo toán tử này. Nhưng “cùng thiếu mã” không tự chứng minh hai bản ghi thuộc cùng một người, nên chỉ dùng khi chính sách dữ liệu cho phép.

### Bài 8

```sql
SELECT c.candidate_row_id, c.customer_id
FROM candidate_customers_197 AS c
LEFT JOIN blocked_customers_197 AS b
  ON b.customer_id = c.customer_id
WHERE c.customer_id IS NOT NULL
  AND b.block_row_id IS NULL
ORDER BY c.candidate_row_id;
```

Kết quả **1, 3, 4, 7**.

### Bài 9

```sql
SELECT
    COUNT(*) FILTER (WHERE customer_id IS NULL)
        AS missing_ids,
    COUNT(customer_id) AS known_ids
FROM blocked_customers_197;
```

Kết quả `missing_ids = 1` và `known_ids = 2`. Có thể đưa các hàng thiếu mã vào danh sách cần bổ sung/xác minh, hạn chế nhập mã rỗng ở bước ghi và đặt ràng buộc `NOT NULL` khi hợp đồng dữ liệu yêu cầu.

### Bài 10

```sql
WITH orders(tenant_id, order_id) AS (
    VALUES ('T1'::TEXT, 101), ('T1', 102), ('T2', 101)
),
blocked(tenant_id, order_id) AS (
    VALUES ('T1'::TEXT, 101)
)
SELECT o.tenant_id, o.order_id
FROM orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked AS b
    WHERE b.tenant_id = o.tenant_id
      AND b.order_id  = o.order_id
)
ORDER BY o.tenant_id, o.order_id;
```

Kết quả **(T1,102)** và **(T2,101)**. Chỉ dùng `order_id` sẽ loại nhầm đơn T2–101.

### Bài 11

```sql
SELECT customer_id FROM candidate_customers_197
EXCEPT
SELECT customer_id FROM blocked_customers_197;
```

Các giá trị nhận được là `1,3,4,6` (thứ tự không bảo đảm nếu thiếu `ORDER BY`). `NOT EXISTS` có thể giữ cả mã, tên và từng hàng ứng viên nên phù hợp hơn khi yêu cầu là lọc bản ghi chi tiết.

### Bài 12

```sql
SELECT c.candidate_row_id,
       c.customer_id,
       c.customer_name,
       CASE
           WHEN c.customer_id IS NULL
               THEN 'unknown_customer_id'
           WHEN EXISTS (
               SELECT 1
               FROM blocked_customers_197 AS b
               WHERE b.customer_id = c.customer_id
           ) THEN 'blocked'
           ELSE 'not_blocked'
       END AS customer_block_status
FROM candidate_customers_197 AS c
ORDER BY c.candidate_row_id;
```

Trả cả bảy hàng với trạng thái đúng theo mã khách; khách hàng 5 giữ nhãn `'unknown_customer_id'` thay vì bị ép thành `'not_blocked'`.

## 23. Quy trình suy nghĩ trước khi dùng NOT IN với truy vấn con

Khi gặp yêu cầu “lấy các hàng **không có trong** tập dữ liệu khác”, hãy trả lời lần lượt:

1. **Hai cột so sánh có cùng ý nghĩa không?** Phải cùng miền định danh; không được thay cột chỉ vì một cột có ràng buộc `NOT NULL`.
2. **Vế phải có thể trả `NULL` không?** Xét cả cột nguồn, `LEFT JOIN`, `CASE`, `NULLIF`, dữ liệu tạm và các biểu thức dẫn xuất.
3. **Vế trái có thể là `NULL` không?** Nếu có, cần quyết định giữ, loại hoặc phân nhóm “chưa biết”.
4. **Truy vấn con có thể rỗng không?** `NOT IN` với tập rỗng trả TRUE, kể cả với vế trái `NULL`.
5. **Yêu cầu là so tập giá trị hay không tồn tại bản ghi khớp?** Với bài toán anti-join theo quan hệ, `NOT EXISTS` thường gần ngôn ngữ nghiệp vụ hơn.
6. **Nếu dùng NOT EXISTS, đã có điều kiện tương quan chưa?** Ví dụ `b.customer_id = c.customer_id`; với khóa ghép cần đủ mọi thành phần.
7. **Hai `NULL` có được xem là khớp không?** Đó là quyết định nghiệp vụ, không phải đặc quyền mặc định của `NOT EXISTS`.
8. **Kết quả có giữ từng hàng nguồn không?** `EXCEPT` và `NOT EXISTS` có hành vi khác nhau với giá trị lặp và cột chi tiết.
9. **Sau khi đúng ngữ nghĩa, hiệu năng ra sao?** Kiểm tra thống kê, index và `EXPLAIN` thay vì chọn cú pháp theo khẩu hiệu.

Điểm cần nhớ nhất: **`NOT IN` không tự bỏ qua `NULL` trong truy vấn con.** Một hàng `NULL` có thể biến điều kiện “không nằm trong danh sách” thành UNKNOWN cho mọi giá trị không khớp đã biết, khiến `WHERE` loại sạch kết quả. `NOT EXISTS` thường là cách diễn đạt vững hơn cho yêu cầu “không có bản ghi liên quan”, nhưng vẫn phải viết điều kiện tương quan chính xác và xử lý `NULL` bên ngoài theo đúng quy tắc dữ liệu.

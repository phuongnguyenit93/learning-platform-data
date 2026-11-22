# NULL, NOT IN và ngữ nghĩa ba giá trị khi viết lại truy vấn

Trong SQL, `NULL` biểu thị dữ liệu chưa biết hoặc không có giá trị được xác định. Vì vậy, phép so sánh với `NULL` không hoạt động như so sánh hai số hoặc hai chuỗi thông thường. SQL dùng logic ba giá trị gồm `TRUE`, `FALSE` và `UNKNOWN`. Đặc điểm này ảnh hưởng trực tiếp đến `WHERE`, `JOIN`, `IN`, `NOT IN`, `NOT EXISTS` và mọi phép viết lại điều kiện truy vấn.

Một lỗi phổ biến là thay `NOT IN` bằng `NOT EXISTS`, dùng `= NULL` để tìm giá trị rỗng, hoặc thêm `COALESCE` mà không xem xét ngữ nghĩa. Câu SQL sau khi viết lại có thể nhanh hơn nhưng trả về tập hàng khác. Với module **DATABASE_PERFORMANCE**, việc tối ưu phải dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; do đó cần hiểu đúng logic trước, sau đó mới đánh giá kế hoạch và hiệu năng. Nội dung module bao gồm thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh.

Bài học thuộc chương **Điều kiện và biểu thức** và tập trung vào cách `NULL` tác động đến ngữ nghĩa ba giá trị, các bẫy của `NOT IN` và nguyên tắc viết lại truy vấn mà vẫn giữ đúng quy tắc nghiệp vụ.

## 1. NULL có ý nghĩa gì?

`NULL` không phải số 0, chuỗi rỗng, chuỗi `'NULL'` hay một giá trị đặc biệt có thể so sánh bằng toán tử `=`. Nó biểu thị rằng giá trị không được biết, không được cung cấp hoặc không áp dụng trong ngữ cảnh dữ liệu.

Ví dụ, bảng khách hàng có thể có `middle_name` là `NULL` khi khách hàng không cung cấp tên đệm. Cột `shipped_at` có thể là `NULL` khi đơn hàng chưa được giao. Hai trường hợp có ý nghĩa nghiệp vụ khác nhau, nhưng đều yêu cầu truy vấn xử lý trạng thái thiếu giá trị một cách tường minh.

Các biểu thức sau không cho kết quả `TRUE`:

```sql
NULL = NULL       -- UNKNOWN
NULL = 10         -- UNKNOWN
NULL <> 10        -- UNKNOWN
NULL > 10         -- UNKNOWN
NOT (NULL = 10)   -- UNKNOWN
```

Muốn kiểm tra một cột có giá trị `NULL`, dùng `IS NULL` hoặc `IS NOT NULL`:

```sql
SELECT customer_id
FROM customers
WHERE middle_name IS NULL;
```

Không viết `middle_name = NULL`, vì phép so sánh đó trả về `UNKNOWN` cho mọi hàng, kể cả hàng có `middle_name` đang là `NULL`.

## 2. Logic ba giá trị trong SQL

Trong logic hai giá trị thông thường, một điều kiện chỉ có thể đúng hoặc sai. SQL bổ sung `UNKNOWN` để biểu diễn kết quả chưa thể xác định do có `NULL` tham gia vào biểu thức.

### 2.1. Bảng chân trị của NOT, AND và OR

| P | `NOT P` |
|---|---|
| TRUE | FALSE |
| FALSE | TRUE |
| UNKNOWN | UNKNOWN |

| P | Q | `P AND Q` | `P OR Q` |
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

Một số quy tắc quan trọng:

- `TRUE AND UNKNOWN` là `UNKNOWN`, vì chưa biết điều kiện thứ hai có đúng hay không.
- `FALSE AND UNKNOWN` là `FALSE`, vì chỉ cần một vế sai thì toàn bộ phép AND sai.
- `TRUE OR UNKNOWN` là `TRUE`, vì chỉ cần một vế đúng thì toàn bộ phép OR đúng.
- `FALSE OR UNKNOWN` là `UNKNOWN`, vì kết quả còn phụ thuộc vế chưa biết.
- `NOT UNKNOWN` vẫn là `UNKNOWN`; phủ định một điều chưa biết không biến nó thành đúng.

Những quy tắc này giải thích vì sao việc thêm `NOT`, đổi `AND` thành `OR` hoặc chuyển điều kiện vào/ra một subquery có thể làm thay đổi tập hàng được chọn.

### 2.2. WHERE chỉ giữ hàng có điều kiện TRUE

Mệnh đề `WHERE` chỉ giữ những hàng mà biểu thức điều kiện cho kết quả `TRUE`. Hàng có kết quả `FALSE` hoặc `UNKNOWN` đều bị loại.

Ví dụ:

```sql
SELECT employee_id, bonus
FROM employees
WHERE bonus > 1000;
```

Nếu `bonus` là `NULL`, phép so sánh `bonus > 1000` trả về `UNKNOWN`, nên hàng đó không xuất hiện trong kết quả. Điều này không có nghĩa bonus được xem là nhỏ hơn hoặc bằng 1000; đơn giản là không thể xác định điều kiện có đúng hay không.

Điểm khác biệt giữa `FALSE` và `UNKNOWN` vẫn quan trọng trong các biểu thức lớn hơn, trong `CASE`, trong phép phủ định và khi chuyển logic sang nơi khác. Không nên gom hai trạng thái này thành một khái niệm “sai” khi viết lại truy vấn.

### 2.3. CHECK và các ngữ cảnh khác

Không phải mọi mệnh đề SQL xử lý `UNKNOWN` giống `WHERE`. Trong nhiều hệ quản trị quan hệ, một `CHECK` constraint chỉ từ chối hàng khi biểu thức cho kết quả `FALSE`; kết quả `UNKNOWN` thường được chấp nhận. Vì vậy, `CHECK (age >= 18)` không nhất thiết cấm `age IS NULL`; muốn bắt buộc có tuổi còn cần `NOT NULL`.

Ví dụ:

```sql
CREATE TABLE members (
    member_id BIGINT PRIMARY KEY,
    age INTEGER NOT NULL CHECK (age >= 18)
);
```

Ở đây `NOT NULL` và `CHECK` có hai vai trò khác nhau: `NOT NULL` cấm thiếu tuổi, còn `CHECK` giới hạn giá trị tuổi được phép. Quy tắc chi tiết cần kiểm tra theo hệ quản trị, nhưng không nên giả định `CHECK` tự thay thế được `NOT NULL`.

## 3. IN và NOT IN thực chất hoạt động thế nào?

`IN` kiểm tra một giá trị có bằng ít nhất một phần tử trong danh sách hoặc tập kết quả hay không. Về logic, nó tương tự phép OR của các so sánh bằng.

```sql
customer_id IN (10, 20, 30)
```

tương tự:

```sql
customer_id = 10
OR customer_id = 20
OR customer_id = 30
```

`NOT IN` là phủ định của `IN`, tương ứng với việc tất cả phép so sánh khác đều phải đúng. Có thể hiểu nó gần với `<> ALL` trên tập giá trị. Vì `UNKNOWN` lan truyền qua `NOT`, `AND` và `OR`, một `NULL` trong danh sách có thể làm kết quả của `NOT IN` trở thành `UNKNOWN`.

### 3.1. NULL trong danh sách NOT IN

Xét điều kiện:

```sql
WHERE customer_id NOT IN (10, 20, NULL)
```

Với `customer_id = 30`, các phép so sánh là:

```text
30 <> 10     TRUE
30 <> 20     TRUE
30 <> NULL   UNKNOWN
TRUE AND TRUE AND UNKNOWN = UNKNOWN
```

Vì `WHERE` loại `UNKNOWN`, hàng có `customer_id = 30` cũng bị loại. Nếu danh sách chứa `NULL`, các giá trị không khớp với những phần tử còn lại thường không thể làm `NOT IN` trở thành `TRUE`.

Ví dụ có thể gây lỗi logic:

```sql
SELECT customer_id
FROM customers
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM blocked_customers
);
```

Nếu `blocked_customers.customer_id` có chỉ một hàng `NULL`, các khách hàng không khớp với mã bị chặn cũng có thể biến mất khỏi kết quả. Truy vấn có thể chạy thành công và không báo lỗi, nên đây là lỗi ngữ nghĩa khó nhận ra nếu chỉ kiểm tra cú pháp hoặc thời gian chạy.

### 3.2. Kết quả của NOT IN trong các trường hợp khác nhau

| Giá trị bên trái | Tập bên phải | Kết quả `NOT IN` | Hàng được WHERE giữ? |
|---|---|---|---|
| 30 | `{10, 20}` | TRUE | Có |
| 10 | `{10, 20}` | FALSE | Không |
| 30 | `{10, 20, NULL}` | UNKNOWN | Không |
| NULL | `{10, 20}` | UNKNOWN | Không |
| NULL | tập rỗng | TRUE theo quy tắc `ALL` trên tập rỗng | Có |
| 30 | tập rỗng | TRUE | Có |

Trường hợp tập rỗng là chi tiết dễ bị bỏ qua: không tồn tại phần tử nào mâu thuẫn với điều kiện “khác mọi phần tử”, nên `NOT IN` là đúng kể cả khi giá trị bên trái là `NULL`. Vì vậy, thêm `left_column IS NOT NULL` vào mọi truy vấn `NOT IN` không phải lúc nào cũng giữ nguyên ngữ nghĩa.

### 3.3. IN cũng có thể trả về UNKNOWN

`IN` không miễn nhiễm với `NULL`. Ví dụ:

```sql
WHERE customer_id IN (10, 20, NULL)
```

Với `customer_id = 30`, không có phần tử bằng 30 và có một phép so sánh với `NULL`, nên kết quả là `UNKNOWN`. Với `customer_id = 10`, kết quả là `TRUE` vì đã có một phép so sánh đúng; `UNKNOWN` ở phần tử khác không làm mất kết quả đúng đó.

## 4. Bẫy NOT IN với subquery

Vấn đề thường xuất hiện khi cột bên trong subquery có thể chứa `NULL`:

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT b.customer_id
    FROM blocked_customers AS b
);
```

Giả sử dữ liệu `blocked_customers` có các giá trị `10`, `20` và `NULL`. Với khách hàng `30`, phép kiểm tra khác tất cả giá trị không thể xác định là đúng vì `30 <> NULL` là `UNKNOWN`. Kết quả bị loại.

Trước khi dùng `NOT IN`, cần trả lời:

- Cột bên trong subquery có được ràng buộc `NOT NULL` không?
- Dữ liệu hiện tại có chứa `NULL` không?
- Dữ liệu tương lai có thể thêm `NULL` không?
- Nếu khóa bên trái là `NULL`, nghiệp vụ muốn giữ hay loại hàng đó?
- Tập con bên phải có thể rỗng không?

Không chỉ chạy một truy vấn kiểm tra dữ liệu hiện tại rồi kết luận an toàn. Ràng buộc schema và quy tắc ghi dữ liệu mới quyết định liệu `NULL` có thể xuất hiện trong tương lai.

## 5. Viết lại NOT IN bằng NOT EXISTS

`NOT EXISTS` kiểm tra subquery có trả về hàng nào hay không. Nó không đánh giá danh sách so sánh theo cùng cách với `NOT IN`; nó chỉ hỏi liệu có hàng thỏa điều kiện tương quan hay không.

Ví dụ anti-join theo nghĩa “không có bản ghi chặn khớp mã khách hàng”:

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customers AS b
    WHERE b.customer_id = c.customer_id
);
```

Với `c.customer_id = 30`, hàng `b.customer_id = NULL` không làm điều kiện bằng trở thành `TRUE`, nên hàng đó không tạo ra kết quả trong subquery. Nếu không có mã khớp, `NOT EXISTS` là `TRUE` và khách hàng 30 được giữ.

Đây thường là cách diễn đạt phù hợp cho yêu cầu nghiệp vụ “chọn các hàng không có hàng liên quan khớp khóa”. Tuy nhiên, không được coi `NOT EXISTS` là phép thay thế tự động tương đương với `NOT IN` trong mọi trường hợp.

### 5.1. Khác biệt khi khóa bên trái là NULL

Với `c.customer_id IS NULL`:

- `c.customer_id NOT IN (subquery không rỗng)` thường là `UNKNOWN`, nên `WHERE` loại hàng.
- `NOT EXISTS (... WHERE b.customer_id = c.customer_id)` là `TRUE` nếu không có phép so sánh nào cho kết quả `TRUE`; so sánh `NULL = NULL` là `UNKNOWN`, không tạo hàng khớp.

Do đó, `NOT EXISTS` có thể giữ hàng bên trái có khóa `NULL`, trong khi `NOT IN` loại hàng đó khi tập bên phải không rỗng. Nếu nghiệp vụ không cho phép khóa bên trái thiếu, hãy thể hiện rõ:

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE c.customer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM blocked_customers AS b
      WHERE b.customer_id = c.customer_id
  );
```

Điều kiện `IS NOT NULL` ở đây là một quyết định nghiệp vụ: chỉ chọn khách hàng có mã xác định. Nó không phải một bước tối ưu có thể thêm tùy tiện.

### 5.2. Khác biệt khi khóa bên phải có NULL

Nếu `blocked_customers.customer_id` chứa `NULL`, `NOT EXISTS` vẫn tìm các giá trị khớp bằng `=` và bỏ qua hàng `NULL` vì so sánh không cho `TRUE`. Trong khi đó, `NOT IN` bị ảnh hưởng bởi `NULL` ở tập bên phải.

Nếu mục tiêu là “không có mã bị chặn bằng mã khách hàng”, `NOT EXISTS` thường thể hiện đúng yêu cầu hơn. Nếu muốn dùng `NOT IN`, cần đảm bảo tập con không chứa `NULL`, chẳng hạn:

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
WHERE c.customer_id IS NOT NULL
  AND c.customer_id NOT IN (
      SELECT b.customer_id
      FROM blocked_customers AS b
      WHERE b.customer_id IS NOT NULL
  );
```

Truy vấn trên chủ động loại khóa khách hàng `NULL` và loại `NULL` khỏi tập bên phải. Đây là một chính sách null rõ ràng; hãy xác nhận nó phù hợp với nghiệp vụ.

### 5.3. Khi nào hai cách có cùng tập kết quả?

Nếu cả khóa bên trái và khóa bên phải đều được đảm bảo `NOT NULL`, thì `NOT IN` và `NOT EXISTS` với phép so sánh bằng tương ứng thường cho cùng tập hàng:

```sql
-- NOT IN
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT b.customer_id
    FROM blocked_customers AS b
);

-- NOT EXISTS
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customers AS b
    WHERE b.customer_id = c.customer_id
);
```

Điều kiện `NOT NULL` phải được bảo đảm bởi schema hoặc logic dữ liệu, không chỉ là quan sát trong một lần chạy. Ngay cả khi hai truy vấn tương đương về kết quả, hiệu năng vẫn phụ thuộc hệ quản trị, thống kê, chỉ mục, số hàng và kế hoạch thực thi.

### 5.4. Muốn mô phỏng chính xác NOT IN trong WHERE

Nếu yêu cầu là giữ đúng tập hàng mà `NOT IN` chọn, kể cả trường hợp tập bên phải rỗng, hãy mô tả rõ quy tắc:

- Tập bên phải rỗng: `NOT IN` là `TRUE`, kể cả khóa bên trái là `NULL`.
- Tập bên phải không rỗng: chỉ chọn khi khóa bên trái không `NULL`, không có giá trị khớp và tập bên phải không chứa `NULL`.
- Nếu có giá trị khớp hoặc có `NULL` làm kết quả không xác định, hàng không được `WHERE` giữ.

Một biểu thức tương đương về việc giữ hàng trong `WHERE` có thể viết như sau. CTE `s` đại diện cho tập khóa bên phải của truy vấn thực tế:

```sql
WITH s AS (
    SELECT right_key
    FROM right_table
    WHERE ...
)
SELECT l.*
FROM left_table AS l
WHERE NOT EXISTS (SELECT 1 FROM s)
   OR (
       l.left_key IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM s AS r WHERE r.right_key = l.left_key
       )
       AND NOT EXISTS (
           SELECT 1 FROM s AS r WHERE r.right_key IS NULL
       )
   );
```

Biểu thức này nhằm minh họa ngữ nghĩa tập hàng trong `WHERE`; nó có thể lặp lại việc đánh giá subquery và không phải cách viết mặc định để tối ưu. Trong thực tế, hãy ưu tiên diễn đạt đúng quy tắc nghiệp vụ bằng `NOT EXISTS` và các điều kiện null rõ ràng. Nếu cần giữ nguyên giá trị `UNKNOWN` như một biểu thức được trả về trong `SELECT` hoặc dùng ở ngữ cảnh khác, phải kiểm tra cả ba trạng thái, không chỉ việc hàng có được lọc hay không.

## 6. LEFT JOIN ... IS NULL như một anti-join

Một cách khác để tìm hàng không có hàng khớp là `LEFT JOIN` rồi lọc các hàng không có đối tượng bên phải:

```sql
SELECT c.customer_id, c.full_name
FROM customers AS c
LEFT JOIN blocked_customers AS b
  ON b.customer_id = c.customer_id
WHERE b.customer_id IS NULL;
```

Mẫu này thường được gọi là anti-join. Khi không có hàng bên phải khớp, `LEFT JOIN` tạo một hàng kết quả với các cột bên phải được điền `NULL`; điều kiện `b.customer_id IS NULL` giữ lại hàng đó.

### 6.1. Kiểm tra cột dùng để nhận diện không khớp

Để mẫu `LEFT JOIN ... IS NULL` đáng tin cậy, hãy kiểm tra một cột bên phải chắc chắn không `NULL` trong mọi hàng khớp, thường là khóa chính hoặc cột được ràng buộc `NOT NULL`:

```sql
SELECT c.customer_id
FROM customers AS c
LEFT JOIN blocked_customers AS b
  ON b.customer_id = c.customer_id
WHERE b.blocked_id IS NULL; -- blocked_id là khóa chính NOT NULL
```

Nếu kiểm tra một cột bên phải vốn có thể `NULL`, hàng đã khớp vẫn có thể bị hiểu nhầm là không khớp. Đây là lỗi thường gặp khi dùng một thuộc tính nghiệp vụ nullable thay vì khóa định danh.

### 6.2. Điều kiện của bảng bên phải phải đặt đúng chỗ

Xét yêu cầu lấy khách hàng không có đơn hàng đang mở. Điều kiện trạng thái cần nằm trong `ON`:

```sql
SELECT c.customer_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'OPEN'
WHERE o.order_id IS NULL;
```

Nếu chuyển `o.status = 'OPEN'` xuống `WHERE`, các hàng được mở rộng với `NULL` bởi `LEFT JOIN` sẽ bị loại bởi điều kiện so sánh, làm thay đổi hành vi gần như inner join. Vị trí điều kiện trong `ON` và `WHERE` có ý nghĩa khác nhau với outer join.

Trong nhiều hệ quản trị, optimizer có thể biến `NOT EXISTS` và `LEFT JOIN ... IS NULL` thành cùng một dạng anti-join. Không nên chọn cách viết chỉ vì tin rằng một cú pháp luôn nhanh hơn; hãy xem execution plan và đo trên workload thực tế.

## 7. So sánh NULL một cách tường minh

Nếu nghiệp vụ muốn xem hai giá trị `NULL` là “bằng nhau” trong một phép so sánh, toán tử `=` thông thường không đáp ứng điều đó. Một số hệ quản trị hỗ trợ toán tử so sánh null-safe:

- `IS NOT DISTINCT FROM` xem hai giá trị bằng nhau nếu chúng bằng theo phép so sánh thông thường hoặc cả hai đều `NULL`.
- `IS DISTINCT FROM` là phủ định null-safe của phép so sánh đó.
- MySQL hỗ trợ toán tử `<=>` cho null-safe equality.

Ví dụ theo cú pháp SQL hỗ trợ `IS NOT DISTINCT FROM`:

```sql
SELECT *
FROM source_rows AS s
JOIN target_rows AS t
  ON s.external_code IS NOT DISTINCT FROM t.external_code;
```

Với MySQL, biểu thức tương ứng có thể dùng:

```sql
ON s.external_code <=> t.external_code
```

Khả năng hỗ trợ phụ thuộc hệ quản trị và phiên bản. Không thay `=` bằng phép so sánh null-safe chỉ để “tránh UNKNOWN”: hai phép toán có ngữ nghĩa khác nhau. Nếu hai cột cùng `NULL`, phép so sánh null-safe sẽ coi chúng khớp, có thể tạo nhiều hàng join nếu dữ liệu chứa nhiều `NULL`.

## 8. COALESCE và giá trị thay thế: không tự động an toàn

Một cách viết thường thấy là thay `NULL` bằng một giá trị giả:

```sql
WHERE COALESCE(status, 'UNKNOWN') <> 'CLOSED'
```

Điều kiện này có thể làm `NULL` được xem như một trạng thái cụ thể. Nhưng chỉ an toàn nếu giá trị thay thế không thể trùng với dữ liệu hợp lệ và quy tắc nghiệp vụ thực sự muốn xử lý `NULL` như vậy.

Các rủi ro gồm:

- Giá trị thay thế có thể xuất hiện trong dữ liệu thật, làm hai trạng thái khác nhau bị gộp.
- Hàm bọc quanh cột có thể khiến chỉ mục B-tree thông thường khó được sử dụng, trừ khi hệ quản trị hỗ trợ expression/function-based index tương ứng.
- Kiểu dữ liệu và collation của giá trị thay thế có thể gây chuyển đổi hoặc thay đổi so sánh.
- Biểu thức có thể che giấu việc dữ liệu bị thiếu thay vì xử lý đúng ý nghĩa của nó.

Nếu muốn giữ tất cả trạng thái khác `CLOSED`, bao gồm `NULL`, có thể viết rõ:

```sql
WHERE status <> 'CLOSED'
   OR status IS NULL
```

Nếu muốn chỉ giữ trạng thái đã xác định và khác `CLOSED`:

```sql
WHERE status IS NOT NULL
  AND status <> 'CLOSED'
```

Hai biểu thức có chính sách null khác nhau. Chọn theo yêu cầu nghiệp vụ, rồi kiểm tra kế hoạch thực thi để xem việc viết rõ điều kiện có ảnh hưởng đến chỉ mục và ước lượng hay không.

## 9. NULL trong JOIN, GROUP BY và hàm tổng hợp

### 9.1. Điều kiện JOIN bằng thông thường

Trong phép nối:

```sql
SELECT *
FROM a
JOIN b ON a.external_id = b.external_id;
```

`NULL` ở một trong hai phía không tạo ra hàng khớp vì `NULL = NULL` là `UNKNOWN`, không phải `TRUE`. Nếu nghiệp vụ yêu cầu hai giá trị thiếu được xem là tương đương, cần dùng phép so sánh null-safe được hệ quản trị hỗ trợ hoặc mô hình hóa khóa rõ ràng.

### 9.2. GROUP BY và DISTINCT

Trong các thao tác nhóm hoặc loại trùng, SQL thường gom các giá trị `NULL` vào cùng một nhóm hoặc xem chúng là một giá trị xuất hiện để loại trùng, dù phép so sánh `NULL = NULL` vẫn là `UNKNOWN`. Đây là quy tắc của từng ngữ cảnh toán tử, không thể suy ra từ phép so sánh bằng thông thường.

Ví dụ:

```sql
SELECT region, COUNT(*)
FROM customers
GROUP BY region;
```

Các hàng có `region IS NULL` thường được gom vào một nhóm `NULL`. Cần xem kết quả nhóm đó có ý nghĩa nghiệp vụ gì trước khi lọc bỏ.

### 9.3. COUNT và các hàm tổng hợp

`COUNT(*)` đếm hàng, kể cả hàng có cột `NULL`. `COUNT(column)` chỉ đếm giá trị không `NULL` của cột đó. Các hàm như `SUM`, `AVG`, `MIN` và `MAX` thường bỏ qua giá trị `NULL`; nếu không có giá trị phù hợp, kết quả có thể là `NULL`.

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(bonus) AS rows_with_bonus,
    AVG(bonus) AS average_bonus
FROM employees;
```

Không dùng `COALESCE(AVG(bonus), 0)` nếu số 0 sẽ làm người đọc hiểu nhầm rằng trung bình thực sự bằng 0 trong khi không có dữ liệu bonus. Nếu cần hiển thị 0, hãy đảm bảo báo cáo phân biệt được “không có dữ liệu” với “giá trị trung bình bằng 0”.

## 10. Viết lại truy vấn mà không đổi ngữ nghĩa

Trước khi thay `NOT IN`, `NOT EXISTS`, `LEFT JOIN` hoặc `COALESCE`, hãy xác định rõ chính sách cho `NULL` ở cả hai phía.

Một quy trình an toàn:

1. **Xác định ý nghĩa dữ liệu thiếu.** `NULL` nghĩa là chưa biết, không có, không áp dụng hay chưa hoàn tất?
2. **Kiểm tra ràng buộc schema.** Cột có `NOT NULL`, khóa chính, khóa ngoại hoặc constraint nào bảo đảm không có `NULL`?
3. **Liệt kê trường hợp biên.** Giá trị trái `NULL`, giá trị phải `NULL`, có giá trị khớp, không có giá trị khớp và tập con rỗng.
4. **Viết rõ quy tắc mong muốn.** Ví dụ “không tồn tại bản ghi chặn có cùng mã xác định” khác với “khác tất cả giá trị trong tập theo ngữ nghĩa `NOT IN`”.
5. **Tạo dữ liệu kiểm thử nhỏ.** Bao gồm đủ trường hợp `NULL`, giá trị trùng và tập rỗng.
6. **So sánh kết quả trước/sau.** So sánh tập khóa và số hàng, không chỉ so sánh tổng số hàng nếu có thể xảy ra trùng lặp.
7. **Kiểm tra execution plan.** Đánh giá anti-join, semi-join, scan/seek, số hàng ước lượng/thực tế, loops và I/O.
8. **Đo workload đại diện.** So sánh độ trễ, throughput, CPU, I/O và tác động lên các truy vấn khác.

### 10.1. Bộ dữ liệu kiểm thử cho NOT IN

Có thể tạo tập dữ liệu nhỏ để quan sát logic:

```sql
CREATE TABLE candidates (
    candidate_id INTEGER
);

CREATE TABLE excluded_ids (
    excluded_id INTEGER
);

INSERT INTO candidates (candidate_id)
VALUES (10), (20), (30), (NULL);

INSERT INTO excluded_ids (excluded_id)
VALUES (10), (NULL);
```

Chạy hai truy vấn:

```sql
SELECT candidate_id
FROM candidates
WHERE candidate_id NOT IN (
    SELECT excluded_id FROM excluded_ids
);
```

```sql
SELECT c.candidate_id
FROM candidates AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM excluded_ids AS e
    WHERE e.excluded_id = c.candidate_id
);
```

Truy vấn `NOT IN` không giữ các giá trị không khớp vì tập bên phải chứa `NULL`. Truy vấn `NOT EXISTS` giữ `30` và cũng có thể giữ hàng `candidate_id IS NULL`, vì không có phép bằng nào tạo kết quả `TRUE`. Đây là khác biệt ngữ nghĩa cần được quyết định rõ ràng.

Nếu muốn `NOT EXISTS` nhưng loại mã ứng viên `NULL`, thêm điều kiện:

```sql
WHERE c.candidate_id IS NOT NULL
  AND NOT EXISTS (...)
```

Khi thử nghiệm, hãy kiểm tra từng hàng để hiểu kết quả, rồi mới chạy trên dữ liệu lớn.

## 11. Ảnh hưởng đến bộ tối ưu và chỉ mục

Logic đúng là điều kiện tiên quyết; sau đó mới xem cách viết truy vấn ảnh hưởng đến kế hoạch.

### 11.1. NOT EXISTS có thể trở thành anti-semi join

Nhiều hệ quản trị có thể biến `NOT EXISTS` tương quan thành một toán tử anti-semi join hoặc dạng kế hoạch tương đương. Nếu cột khóa bên trong có chỉ mục, bộ tối ưu có thể kiểm tra nhanh sự tồn tại của giá trị khớp và dừng sau khi tìm thấy hàng đầu tiên.

Điều này không bảo đảm `NOT EXISTS` luôn nhanh hơn `NOT IN`. Với ràng buộc `NOT NULL`, hai truy vấn có thể được tối ưu thành kế hoạch tương tự. Kết quả phụ thuộc hệ quản trị, phiên bản, thống kê, số hàng và hình dạng subquery.

### 11.2. Chỉ mục trên khóa tương quan

Với truy vấn:

```sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customers AS b
    WHERE b.customer_id = c.customer_id
);
```

chỉ mục trên `blocked_customers(customer_id)` có thể hỗ trợ kiểm tra sự tồn tại. Nếu truy vấn còn lọc theo trạng thái hoặc tenant, chỉ mục ghép có thể cần được đánh giá theo thứ tự điều kiện và workload thực tế.

Không thêm chỉ mục chỉ vì thấy `NOT EXISTS`. Hãy kiểm tra kế hoạch có scan lặp lại ở nhánh trong hay không, số loops, số hàng đọc, độ chọn lọc và tần suất truy vấn. Với tập dữ liệu nhỏ, scan có thể là lựa chọn rẻ hơn.

### 11.3. Predicate có hàm và tính sargable

Điều kiện như `COALESCE(column, value) = ...` hoặc hàm áp lên cột có thể làm giảm khả năng dùng chỉ mục thông thường, tùy hệ quản trị và cách tối ưu. Nếu mục tiêu là kiểm tra `NULL`, `IS NULL` thường biểu đạt trực tiếp hơn. Nếu cần tìm theo biểu thức, cân nhắc expression/function-based index sau khi xác nhận hỗ trợ và đo chi phí duy trì.

Việc thay `NOT IN` bằng `NOT EXISTS` cũng có thể thay đổi hình dạng kế hoạch. Hãy dùng `EXPLAIN` hoặc công cụ tương ứng, xem anti-join, index seek/scan, số hàng ước lượng/thực tế và trạng thái chờ để hiểu tác động.

## 12. Các lỗi viết lại thường gặp

- **Dùng `= NULL`:** biểu thức trả về `UNKNOWN`; phải dùng `IS NULL`.
- **Cho rằng `NULL = NULL`:** phép so sánh bằng thông thường không xem hai `NULL` là bằng nhau.
- **Không kiểm tra NULL trong subquery của NOT IN:** chỉ một `NULL` có thể làm nhiều hàng không khớp bị loại.
- **Thay NOT IN bằng NOT EXISTS mà không xem khóa trái:** hàng bên trái `NULL` có thể được giữ bởi `NOT EXISTS`.
- **Thêm `IS NOT NULL` tùy tiện:** có thể làm mất trường hợp tập con rỗng mà `NOT IN` vốn trả về `TRUE`.
- **Dùng LEFT JOIN rồi kiểm tra cột nullable:** hàng khớp có giá trị cột đó `NULL` có thể bị nhầm là không khớp.
- **Đưa điều kiện bảng phải từ ON xuống WHERE:** có thể biến outer join thành hành vi inner join.
- **Dùng COALESCE với sentinel tùy ý:** có thể gộp giá trị hợp lệ với trạng thái thiếu và làm thay đổi khả năng dùng chỉ mục.
- **Chỉ so sánh số hàng:** hai kết quả có cùng số lượng nhưng khác khóa hoặc khác nội dung vẫn có thể sai.
- **Tối ưu trước khi xác định nghiệp vụ:** tốc độ tăng không có ý nghĩa nếu quy tắc lọc đã bị thay đổi.

## 13. Bài tập tự kiểm tra

### Bài tập 1: NOT IN chứa NULL

Một subquery trả về các mã `5`, `8` và `NULL`. Điều kiện ngoài là `product_id NOT IN (subquery)`. Hàng có `product_id = 12` có được giữ trong `WHERE` không?

**Gợi ý trả lời:** không. Các so sánh `12 <> 5` và `12 <> 8` là `TRUE`, nhưng `12 <> NULL` là `UNKNOWN`. Kết quả tổng hợp là `UNKNOWN`, nên `WHERE` loại hàng.

### Bài tập 2: NOT EXISTS giữ khóa NULL

Một truy vấn dùng `NOT EXISTS` với điều kiện `b.external_id = c.external_id`. Hàng `c.external_id` là `NULL` và không có hàng nào trong `b` khớp.

**Câu hỏi:** hàng bên trái có được giữ không? Nếu nghiệp vụ yêu cầu chỉ giữ mã xác định thì viết thế nào?

**Gợi ý trả lời:** `NOT EXISTS` là `TRUE` vì không có hàng nào làm phép so sánh thành `TRUE`, nên hàng có khóa `NULL` được giữ. Nếu chỉ nhận mã xác định, thêm `c.external_id IS NOT NULL`.

### Bài tập 3: LEFT JOIN anti-join

Bạn dùng `LEFT JOIN blocked_customers b` rồi `WHERE b.comment IS NULL` để tìm khách hàng không bị chặn. Nhưng `comment` được phép `NULL` ngay cả khi hàng chặn tồn tại.

**Câu hỏi:** vì sao kết quả có thể sai và cần đổi điều kiện kiểm tra thành gì?

**Gợi ý trả lời:** hàng khớp vẫn có thể có `comment IS NULL`, nên bị hiểu nhầm là không khớp. Hãy kiểm tra một cột bên phải được bảo đảm `NOT NULL`, thường là khóa chính như `b.blocked_id IS NULL`.

### Bài tập 4: Chọn chính sách NULL

Một báo cáo muốn liệt kê các tài khoản không xuất hiện trong danh sách tài khoản bị khóa. `account_id` của hai bảng theo thiết kế phải luôn có giá trị, nhưng dữ liệu cũ có thể vi phạm quy tắc.

**Yêu cầu:** nêu cách xác minh và chọn phép viết lại.

**Gợi ý trả lời:** kiểm tra constraint và chất lượng dữ liệu, xác định cách xử lý các hàng cũ có `NULL`, sau đó dùng `NOT EXISTS` với phép bằng nếu yêu cầu là “không tồn tại mã khớp”, hoặc `NOT IN` khi cả hai phía được bảo đảm không `NULL`. So sánh tập khóa trả về trước/sau và đo execution plan trên dữ liệu đại diện.

### Checklist trước khi viết lại điều kiện có NULL

- [ ] Đã phân biệt `TRUE`, `FALSE` và `UNKNOWN`.
- [ ] Đã xác định `WHERE` chỉ giữ hàng có kết quả `TRUE`.
- [ ] Đã kiểm tra `NULL` ở vế trái và tập kết quả bên phải của `IN`/`NOT IN`.
- [ ] Đã xem xét trường hợp subquery rỗng.
- [ ] Đã xác định chính sách nghiệp vụ cho khóa thiếu.
- [ ] Đã kiểm tra `NOT EXISTS` có thể giữ hàng bên trái `NULL` hay không.
- [ ] Nếu dùng `LEFT JOIN ... IS NULL`, đã chọn cột bên phải `NOT NULL` để nhận diện không khớp.
- [ ] Đã đặt điều kiện của bảng phải đúng vị trí trong `ON` hoặc `WHERE`.
- [ ] Đã tránh sentinel `COALESCE` không an toàn.
- [ ] Đã so sánh tập kết quả và kiểm tra execution plan trước/sau.
- [ ] Đã đo độ trễ, throughput, I/O và chi phí truy vấn trên workload đại diện.

`NULL` làm SQL vận hành theo logic ba giá trị, vì vậy `NOT IN`, `NOT EXISTS` và `LEFT JOIN ... IS NULL` chỉ tương đương khi các điều kiện về nullability và ngữ nghĩa được xác định. Hãy làm rõ chính sách dữ liệu thiếu, kiểm thử các trường hợp biên, so sánh tập kết quả và sau đó mới tối ưu kế hoạch thực thi. Cách làm này giữ được tính đúng đắn trong khi vẫn cho phép đánh giá chỉ mục, anti-join và chi phí truy vấn bằng số liệu.

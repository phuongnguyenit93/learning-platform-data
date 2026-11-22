# NULL trong so sánh hàng của phép toán tập hợp

Một trong những điểm dễ gây nhầm lẫn khi học SQL là câu hỏi: **hai hàng đều chứa `NULL` có được coi là trùng nhau không?** Nếu kiểm tra bằng dấu `=`, `NULL = NULL` cho kết quả **`UNKNOWN`**, chứ không phải `TRUE`. Nhưng khi ghép hai tập kết quả bằng `UNION`, tìm phần chung bằng `INTERSECT` hoặc tìm phần khác biệt bằng `EXCEPT`, SQL lại cần một quy tắc để nhận diện **hàng trùng nhau**. Trong ngữ cảnh đó, những vị trí cùng chứa `NULL` được xem là **không khác biệt** khi xác định các hàng trùng.

Ví dụ, nếu hai truy vấn đều trả về hàng `('A', NULL)`, thì:

- `UNION` chỉ giữ **một** hàng `('A', NULL)`.
- `INTERSECT` có thể trả về **một** hàng `('A', NULL)` vì hàng này xuất hiện ở cả hai phía.
- `EXCEPT` loại hàng `('A', NULL)` khỏi phía trái nếu phía phải cũng có hàng tương ứng.
- `UNION ALL` vẫn giữ cả hai hàng vì nó **không loại trùng**.

Nguyên tắc này khác với phép so sánh bằng thông thường trong `WHERE` hoặc `JOIN ... ON`. Bài học sẽ giúp bạn hiểu sự khác biệt đó, sử dụng `UNION`, `INTERSECT`, `EXCEPT` cùng các biến thể `ALL`, và xử lý các bản ghi chứa một hay nhiều giá trị `NULL` khi đối chiếu dữ liệu.

Ví dụ thực hành dùng **PostgreSQL** để có thể minh họa đầy đủ cả `INTERSECT ALL` và `EXCEPT ALL`. Tính năng hỗ trợ, tên phép toán hoặc biến thể `ALL` có thể khác giữa các hệ quản trị SQL.

## 1. Hai loại so sánh không được đánh đồng

Trong SQL có ít nhất hai ngữ cảnh liên quan tới việc các hàng “bằng nhau”.

### 1.1. So sánh bằng trong biểu thức điều kiện

Một phép so sánh thông thường:

```sql
SELECT NULL = NULL AS comparison_result;
-- PostgreSQL: NULL (biểu thị UNKNOWN trong logic ba giá trị)
```

Kết quả không phải `TRUE`. SQL sử dụng **logic ba giá trị**:

| Biểu thức | Kết quả logic |
|---|---|
| `3 = 3` | `TRUE` |
| `3 = 4` | `FALSE` |
| `NULL = 3` | `UNKNOWN` |
| `NULL = NULL` | `UNKNOWN` |
| `NULL <> NULL` | `UNKNOWN` |
| `NULL IS NULL` | `TRUE` |

Trong `WHERE`, chỉ điều kiện đánh giá thành `TRUE` mới giữ hàng; `FALSE` và `UNKNOWN` đều loại hàng. Trong `INNER JOIN ... ON`, chỉ cặp hàng thỏa điều kiện ghép là `TRUE` mới tạo cặp ghép.

### 1.2. Nhận diện hàng trùng trong phép toán tập hợp

Khi thực hiện `UNION`, `INTERSECT`, `EXCEPT` ở dạng mặc định **không có `ALL`**, SQL phải xác định những hàng kết quả nào được xem là trùng nhau để loại trùng hoặc đối chiếu tập hợp.

Trong ngữ cảnh **so sánh hàng cho phép toán tập hợp**:

- Hai giá trị **khác `NULL`** ở cùng vị trí được đối chiếu theo quy tắc bình đẳng tương ứng với kiểu dữ liệu và DBMS.
- Hai vị trí **đều `NULL`** được xem là **không khác biệt** để nhận diện bản ghi trùng.
- Một phía `NULL`, phía còn lại có giá trị đã biết thì **khác biệt**.
- Với hàng nhiều cột, phải xét **tất cả các cột được chọn**, không chỉ một cột.

Do đó, hai hàng `('A', NULL)` có thể được xem là **cùng một hàng trong `UNION`** mặc dù biểu thức `NULL = NULL` không cho `TRUE`.

**Cách nhớ:** phép `=` là một **biểu thức logic ba giá trị**; còn loại trùng trong phép toán tập hợp dựa trên quan hệ **“không khác biệt” (*not distinct*)** giữa các hàng. Đây là hai cơ chế khác nhau.

## 2. Nhắc lại UNION, INTERSECT và EXCEPT

Ba phép toán tập hợp quan trọng là:

| Phép toán | Câu hỏi nó trả lời | Mặc định không `ALL` |
|---|---|---|
| `UNION` | Những hàng xuất hiện ở **ít nhất một** phía? | Gộp hai phía rồi loại trùng |
| `INTERSECT` | Những hàng xuất hiện ở **cả hai** phía? | Lấy phần giao, mỗi hàng duy nhất một lần |
| `EXCEPT` | Những hàng ở **phía trái nhưng không có ở phía phải**? | Lấy phần hiệu, mỗi hàng duy nhất một lần |

Các dạng:

```sql
SELECT cot_a, cot_b FROM tap_trai
UNION
SELECT cot_a, cot_b FROM tap_phai;

SELECT cot_a, cot_b FROM tap_trai
INTERSECT
SELECT cot_a, cot_b FROM tap_phai;

SELECT cot_a, cot_b FROM tap_trai
EXCEPT
SELECT cot_a, cot_b FROM tap_phai;
```

Các truy vấn kết hợp phải có **cùng số cột**, các cột ở cùng vị trí cần có **kiểu dữ liệu tương thích** và các phép so sánh/tập hợp phù hợp với DBMS. Tên cột của kết quả thường được lấy từ truy vấn đầu tiên. Các hàng được đối chiếu **theo vị trí cột**, không dựa vào tên hay ý nghĩa tên cột.

`EXCEPT` có tính **hướng**: `A EXCEPT B` không giống `B EXCEPT A`. `UNION` và `INTERSECT` về mặt tập hợp có tính giao hoán, dù thứ tự hiển thị có thể khác vì không có `ORDER BY`.

**Quan trọng:** ba phép toán trên không tự sắp xếp kết quả theo một thứ tự đáng tin cậy. Muốn kết quả ổn định khi xem hoặc phân trang, cần thêm `ORDER BY` thích hợp vào **toàn bộ kết quả cuối cùng**.

## 3. Bộ dữ liệu mẫu có NULL và bản ghi trùng

Để dễ thấy sự khác nhau giữa mặc định và `ALL`, ta tạo **hai tập dữ liệu** có các cặp giá trị trùng nhau, trong đó nhiều cặp chứa `NULL`. Các cột `row_id` là khóa riêng để có thể phân biệt từng bản ghi nguồn; chúng **không được đưa vào phép toán tập hợp khi muốn đối chiếu theo hai cột nghiệp vụ**.

Tạo hai bảng trong **database thực hành riêng**:

```sql
CREATE TABLE left_rows (
    row_id INTEGER PRIMARY KEY,
    code VARCHAR(10),
    shade VARCHAR(10)
);

CREATE TABLE right_rows (
    row_id INTEGER PRIMARY KEY,
    code VARCHAR(10),
    shade VARCHAR(10)
);

INSERT INTO left_rows (row_id, code, shade)
VALUES
    (1,  'A',  'red'),
    (2,  'A',  'red'),
    (3,  'A',  NULL),
    (4,  'A',  NULL),
    (5,  NULL, 'red'),
    (6,  NULL, 'red'),
    (7,  NULL, NULL),
    (8,  'B',  'blue'),
    (9,  'C',  NULL),
    (10, 'L',  'only');

INSERT INTO right_rows (row_id, code, shade)
VALUES
    (101, 'A',  'red'),
    (102, 'A',  NULL),
    (103, 'A',  NULL),
    (104, NULL, 'red'),
    (105, NULL, NULL),
    (106, NULL, NULL),
    (107, 'B',  'blue'),
    (108, 'R',  'only'),
    (109, 'B',  NULL),
    (110, 'A',  'green');
```

### 3.1. Dữ liệu phía trái

| row_id | code | shade |
|---:|---|---|
| 1 | A | red |
| 2 | A | red |
| 3 | A | `NULL` |
| 4 | A | `NULL` |
| 5 | `NULL` | red |
| 6 | `NULL` | red |
| 7 | `NULL` | `NULL` |
| 8 | B | blue |
| 9 | C | `NULL` |
| 10 | L | only |

### 3.2. Dữ liệu phía phải

| row_id | code | shade |
|---:|---|---|
| 101 | A | red |
| 102 | A | `NULL` |
| 103 | A | `NULL` |
| 104 | `NULL` | red |
| 105 | `NULL` | `NULL` |
| 106 | `NULL` | `NULL` |
| 107 | B | blue |
| 108 | R | only |
| 109 | B | `NULL` |
| 110 | A | green |

Mỗi bảng có **10 hàng vật lý**, nhưng có những giá trị nghiệp vụ lặp lại. Ví dụ, `('A', 'red')` có **hai** bản ghi ở trái và **một** bản ghi ở phải; `('A', NULL)` có **hai** bản ghi ở mỗi phía; `(NULL, NULL)` có **một** bản ghi ở trái và **hai** bản ghi ở phải.

Ta sẽ so sánh kết quả chỉ trên **`(code, shade)`**. Một hàng `(NULL, 'red')` không bị đồng nhất với `(NULL, NULL)`, vì cột `shade` ở một phía là `'red'` và ở phía kia là `NULL`.

## 4. UNION: hai hàng có NULL vẫn có thể bị gộp thành một

### 4.1. UNION mặc định loại trùng

```sql
SELECT code, shade FROM left_rows
UNION
SELECT code, shade FROM right_rows
ORDER BY code NULLS LAST, shade NULLS LAST;
```

Kết quả có **10 hàng khác biệt** theo hai cột được chọn:

| code | shade |
|---|---|
| A | green |
| A | red |
| A | `NULL` |
| B | blue |
| B | `NULL` |
| C | `NULL` |
| L | only |
| R | only |
| `NULL` | red |
| `NULL` | `NULL` |

Giải thích một số dòng:

- `('A', 'red')` xuất hiện hai lần ở trái và một lần ở phải, nhưng `UNION` chỉ hiển thị **một lần**.
- `('A', NULL)` xuất hiện bốn lần tính cả hai phía, nhưng kết quả cũng chỉ có **một hàng**.
- `(NULL, 'red')` xuất hiện ba lần, kết quả chỉ có **một hàng**.
- `(NULL, NULL)` xuất hiện ba lần, kết quả chỉ có **một hàng**.
- `('A', NULL)` và `(NULL, NULL)` vẫn **khác nhau**, vì vị trí `code` khác biệt.

Đối với việc loại trùng, `NULL` ở cùng vị trí được xử lý như **không khác biệt**. SQL **không** sử dụng `NULL = NULL` thành `TRUE`, mà áp dụng quy tắc riêng cho so sánh các hàng trong tập hợp.

`UNION` không phải là “nối các hàng theo điều kiện khóa” như `JOIN`. Nó **xếp chồng** hai kết quả có cấu trúc tương ứng, rồi loại các hàng bị coi là trùng trên **toàn bộ danh sách cột**.

### 4.2. Ví dụ tối giản chỉ với NULL

```sql
SELECT CAST(NULL AS VARCHAR(10)) AS code,
       CAST(NULL AS VARCHAR(10)) AS shade
UNION
SELECT CAST(NULL AS VARCHAR(10)),
       CAST(NULL AS VARCHAR(10));
```

Kết quả chỉ **một hàng `(NULL, NULL)`**. Đây là minh họa trực tiếp rằng `UNION` loại trùng những hàng cùng chứa `NULL`.

### 4.3. UNION ALL không loại trùng

```sql
SELECT code, shade FROM left_rows
UNION ALL
SELECT code, shade FROM right_rows
ORDER BY code NULLS LAST, shade NULLS LAST;
```

`UNION ALL` trả **20 hàng**: 10 hàng từ trái và 10 hàng từ phải. Các hàng `(NULL, NULL)`, `('A', NULL)` hay `('A', 'red')` giữ đúng số lần xuất hiện trong hai đầu vào. `ALL` không có nghĩa “coi `NULL` khác nhau”; đơn giản là **không thực hiện bước loại trùng** của `UNION`.

Để xem số lần xuất hiện mà không phải đọc 20 hàng:

```sql
WITH combined AS (
    SELECT code, shade FROM left_rows
    UNION ALL
    SELECT code, shade FROM right_rows
)
SELECT code, shade, COUNT(*) AS occurrences
FROM combined
GROUP BY code, shade
ORDER BY code NULLS LAST, shade NULLS LAST;
```

| code | shade | occurrences |
|---|---|---:|
| A | green | 1 |
| A | red | 3 |
| A | `NULL` | 4 |
| B | blue | 2 |
| B | `NULL` | 1 |
| C | `NULL` | 1 |
| L | only | 1 |
| R | only | 1 |
| `NULL` | red | 3 |
| `NULL` | `NULL` | 3 |

`GROUP BY code, shade` cũng tạo **một nhóm** cho các hàng có cùng mẫu `NULL` ở từng vị trí; đây là điểm tương đồng giữa cách nhóm và cách nhận diện trùng của phép toán tập hợp.

## 5. INTERSECT: NULL ở cùng vị trí vẫn thuộc phần giao

`INTERSECT` chỉ giữ những hàng **xuất hiện ở cả hai phía**. Ở dạng mặc định, mỗi hàng chung chỉ xuất hiện một lần trong kết quả.

```sql
SELECT code, shade FROM left_rows
INTERSECT
SELECT code, shade FROM right_rows
ORDER BY code NULLS LAST, shade NULLS LAST;
```

Kết quả có **5 hàng**:

| code | shade | Vì sao thuộc phần giao? |
|---|---|---|
| A | red | Có ở cả hai bảng |
| A | `NULL` | Cả hai có hàng `('A', NULL)` |
| B | blue | Có ở cả hai bảng |
| `NULL` | red | Cả hai có hàng `(NULL, 'red')` |
| `NULL` | `NULL` | Cả hai có hàng `(NULL, NULL)` |

Trong khi đó:

- `('C', NULL)` chỉ có ở trái.
- `('L', 'only')` chỉ có ở trái.
- `('R', 'only')`, `('B', NULL)`, `('A', 'green')` chỉ có ở phải.

Những hàng chỉ xuất hiện ở một phía không thuộc phần giao.

### 5.1. Ví dụ một hàng đều NULL

```sql
SELECT CAST(NULL AS INTEGER) AS marker
INTERSECT
SELECT CAST(NULL AS INTEGER);
```

Kết quả **một hàng `NULL`**. Với so sánh bằng thông thường:

```sql
SELECT CAST(NULL AS INTEGER) = CAST(NULL AS INTEGER) AS ordinary_equality;
-- NULL (UNKNOWN), không phải TRUE
```

Hai câu trả lời không mâu thuẫn: **`INTERSECT` xét các hàng có phải không khác biệt trong phép toán tập hợp**, còn `=` xét biểu thức logic thông thường.

### 5.2. INTERSECT không phải INNER JOIN

Nếu viết:

```sql
SELECT l.code, l.shade
FROM left_rows AS l
INNER JOIN right_rows AS r
    ON l.code = r.code
   AND l.shade = r.shade;
```

thì các cặp có `NULL` ở một trong hai cột **không khớp** bằng dấu `=`: điều kiện `NULL = NULL` là `UNKNOWN`. Chỉ các cặp có đủ giá trị không `NULL` và bằng nhau mới ghép được trong dữ liệu mẫu:

- `('A', 'red')`.
- `('B', 'blue')`.

Ngoài ra, `JOIN` tạo một hàng cho **mỗi cặp khớp**, nên `('A', 'red')` có thể lặp vì hai hàng ở phía trái đều khớp một hàng phía phải. Kết quả và số lần xuất hiện của `JOIN` **không tương đương với `INTERSECT`**.

Nếu mục tiêu chỉ là tìm những **cặp giá trị chung** giữa hai tập kết quả và chấp nhận hàng có `NULL`, `INTERSECT` thể hiện trực tiếp ý định hơn.

## 6. EXCEPT: loại hàng có cùng mẫu NULL ở phía phải

`EXCEPT` lấy **các hàng xuất hiện ở phía trái nhưng không xuất hiện ở phía phải**.

```sql
SELECT code, shade FROM left_rows
EXCEPT
SELECT code, shade FROM right_rows
ORDER BY code NULLS LAST, shade NULLS LAST;
```

Kết quả có **2 hàng**:

| code | shade |
|---|---|
| C | `NULL` |
| L | only |

Tại sao `('A', NULL)` không còn?

Vì phía phải cũng có `('A', NULL)`; trong ngữ cảnh `EXCEPT`, hai hàng đó **không khác biệt** nên hàng ở trái bị loại. Tương tự, `(NULL, 'red')` và `(NULL, NULL)` đều bị loại vì phía phải có các hàng tương ứng.

Phép `EXCEPT` thực hiện so sánh trên **cả hai cột**:

- `('C', NULL)` **khác** `('A', NULL)` vì cột `code` khác.
- `(NULL, 'red')` **khác** `(NULL, NULL)` vì cột `shade` khác.
- Hai hàng phải không khác biệt ở **từng vị trí tương ứng** thì mới được xem là cùng giá trị của phép toán tập hợp.

### 6.1. Đảo thứ tự hai tập làm thay đổi kết quả

```sql
SELECT code, shade FROM right_rows
EXCEPT
SELECT code, shade FROM left_rows
ORDER BY code NULLS LAST, shade NULLS LAST;
```

Kết quả có **3 hàng**:

| code | shade |
|---|---|
| A | green |
| B | `NULL` |
| R | only |

Phía phải ban đầu có ba mẫu chỉ riêng nó. Do đó `A EXCEPT B` và `B EXCEPT A` có ý nghĩa khác nhau; khi đối soát, nên ghi rõ hướng “bản ghi **chỉ có ở nguồn nào**”.

### 6.2. Ví dụ tối giản

```sql
SELECT CAST(NULL AS INTEGER) AS marker
EXCEPT
SELECT CAST(NULL AS INTEGER);
```

Kết quả **không có hàng nào**, vì hàng `NULL` ở trái đã có hàng không khác biệt ở phải.

Nếu cùng hai hàng đó mà dùng `WHERE x <> y` thì điều kiện với `NULL` là `UNKNOWN`, dẫn tới cách xử lý khác. Không thay `EXCEPT` bằng một điều kiện `<>` thông thường rồi giả định luôn tương đương.

## 7. Phân biệt mặc định DISTINCT với các biến thể ALL

Đến đây, các ví dụ dùng `UNION`, `INTERSECT` và `EXCEPT` mặc định — tức xử lý theo **tập hợp các hàng khác biệt**. Nhưng SQL thường làm việc với **multiset/bag**: cùng một hàng có thể xuất hiện nhiều lần. PostgreSQL hỗ trợ biến thể `ALL` để giữ hoặc tính **số lần xuất hiện**.

Giả sử một mẫu hàng `x` xuất hiện:

- `m` lần ở phía trái.
- `n` lần ở phía phải.

Với các phép `ALL` được PostgreSQL hỗ trợ:

| Phép toán | Số lần xuất hiện của mẫu `x` |
|---|---:|
| `UNION ALL` | `m + n` |
| `INTERSECT ALL` | `min(m, n)` |
| `EXCEPT ALL` (trái trừ phải) | `max(m - n, 0)` |

Các phép **không có `ALL`** chỉ giữ **một** hàng nếu mẫu đó thuộc kết quả, hoặc **không có** hàng nếu không thuộc.

Điều cần nhấn mạnh: khái niệm **mẫu hàng** ở đây vẫn sử dụng quy tắc **không khác biệt**, tức các vị trí đều `NULL` được xem như cùng mẫu khi tính tần suất.

### 7.1. Bảng tần suất hai phía

Với dữ liệu mẫu:

| Mẫu hàng `(code, shade)` | Số lần trái `m` | Số lần phải `n` | `INTERSECT ALL`: min | `EXCEPT ALL` trái-phải |
|---|---:|---:|---:|---:|
| `('A', 'red')` | 2 | 1 | 1 | 1 |
| `('A', NULL)` | 2 | 2 | 2 | 0 |
| `(NULL, 'red')` | 2 | 1 | 1 | 1 |
| `(NULL, NULL)` | 1 | 2 | 1 | 0 |
| `('B', 'blue')` | 1 | 1 | 1 | 0 |
| `('C', NULL)` | 1 | 0 | 0 | 1 |
| `('L', 'only')` | 1 | 0 | 0 | 1 |
| `('R', 'only')` | 0 | 1 | 0 | 0 |
| `('B', NULL)` | 0 | 1 | 0 | 0 |
| `('A', 'green')` | 0 | 1 | 0 | 0 |

Khi áp dụng `ALL`:

- `INTERSECT ALL` có tổng **6 hàng**.
- `EXCEPT ALL` (trái trừ phải) có tổng **4 hàng**.
- `UNION ALL` có tổng **20 hàng**.

### 7.2. INTERSECT ALL giữ số lần xuất hiện tối thiểu

```sql
SELECT code, shade FROM left_rows
INTERSECT ALL
SELECT code, shade FROM right_rows
ORDER BY code NULLS LAST, shade NULLS LAST;
```

Kết quả gồm **6 hàng** theo số lần xuất hiện:

| code | shade | Số lần trong kết quả |
|---|---|---:|
| A | red | 1 |
| A | `NULL` | 2 |
| B | blue | 1 |
| `NULL` | red | 1 |
| `NULL` | `NULL` | 1 |

Ví dụ `('A', NULL)` có hai bản ghi ở mỗi phía, nên `INTERSECT ALL` trả **hai** hàng `('A', NULL)`, trong khi `INTERSECT` mặc định chỉ trả **một**. Như vậy, `INTERSECT ALL` vẫn nhận diện các hàng có `NULL` như cùng mẫu để **đếm số lần**, nhưng không loại toàn bộ bản sao.

### 7.3. EXCEPT ALL trừ số lần xuất hiện

```sql
SELECT code, shade FROM left_rows
EXCEPT ALL
SELECT code, shade FROM right_rows
ORDER BY code NULLS LAST, shade NULLS LAST;
```

Kết quả có **4 hàng**:

| code | shade | Số lần trong kết quả |
|---|---|---:|
| A | red | 1 |
| C | `NULL` | 1 |
| L | only | 1 |
| `NULL` | red | 1 |

Vì phía trái có **hai** `('A', 'red')` nhưng phía phải chỉ có **một**, vẫn còn **một** bản sao sau `EXCEPT ALL`. Tương tự `(NULL, 'red')` còn một bản sao. Ngược lại:

- `('A', NULL)`: `2 - 2 = 0`, không còn.
- `(NULL, NULL)`: phía trái `1`, phía phải `2`; kết quả `max(1 - 2, 0) = 0`.

Điểm khác biệt rất quan trọng:

- `EXCEPT` mặc định chỉ hỏi **mẫu hàng có xuất hiện ở phải không**; nếu có thì loại mẫu đó hoàn toàn khỏi kết quả trái.
- `EXCEPT ALL` trừ **số lượng bản sao**, nên một mẫu có thể vẫn còn nếu phía trái xuất hiện nhiều hơn phía phải.

### 7.4. EXCEPT ALL theo chiều ngược lại

```sql
SELECT code, shade FROM right_rows
EXCEPT ALL
SELECT code, shade FROM left_rows
ORDER BY code NULLS LAST, shade NULLS LAST;
```

Kết quả có **4 hàng**: `('A', 'green')`, `('B', NULL)`, `('R', 'only')` và **một** `(NULL, NULL)` còn dư vì phía phải ban đầu có hai bản sao trong khi phía trái chỉ có một.

Ví dụ này hữu ích khi đối soát hai nguồn cần kiểm tra **cả chênh lệch bản ghi trùng**, không chỉ chênh lệch mẫu dữ liệu.

**Lưu ý phương ngữ:** không phải mọi DBMS đều có `INTERSECT ALL` hoặc `EXCEPT ALL`. Đừng mặc định một biến thể `ALL` chạy được chỉ vì `UNION ALL` được hỗ trợ. Nếu hệ đang dùng không có, cần kiểm tra tài liệu phiên bản và lựa chọn cách đếm tần suất hoặc đối soát khác.

## 8. Sự khác biệt với DISTINCT và GROUP BY

Hai cấu trúc khác cũng thường khiến người học chú ý tới `NULL` là `DISTINCT` và `GROUP BY`.

### 8.1. SELECT DISTINCT gộp các mẫu có NULL giống nhau

```sql
SELECT DISTINCT code, shade
FROM left_rows
ORDER BY code NULLS LAST, shade NULLS LAST;
```

Kết quả có **7 hàng khác biệt**, mặc dù nguồn có 10 hàng:

```text
('A', 'red')
('A', NULL)
('B', 'blue')
('C', NULL)
('L', 'only')
(NULL, 'red')
(NULL, NULL)
```

Hai hàng `('A', NULL)` ở trái không biến thành hai kết quả khác biệt. Tương tự với `(NULL, 'red')` và `('A', 'red')`.

`SELECT DISTINCT code, shade FROM left_rows` tương ứng với việc lấy danh sách các mẫu hàng phân biệt trong bảng. Còn `UNION` kết hợp và loại trùng **giữa hai truy vấn**.

### 8.2. GROUP BY gom những hàng có NULL ở cùng vị trí

```sql
SELECT code, shade, COUNT(*) AS row_count
FROM left_rows
GROUP BY code, shade
ORDER BY code NULLS LAST, shade NULLS LAST;
```

| code | shade | row_count |
|---|---|---:|
| A | red | 2 |
| A | `NULL` | 2 |
| B | blue | 1 |
| C | `NULL` | 1 |
| L | only | 1 |
| `NULL` | red | 2 |
| `NULL` | `NULL` | 1 |

`GROUP BY` tạo **một nhóm** cho các hàng không khác biệt trên khóa nhóm, kể cả khi các thành phần khóa đều là `NULL`. `COUNT(*)` đếm số hàng trong từng nhóm.

Điểm này phù hợp với cách phép toán tập hợp nhận diện mẫu, nhưng **khác** biểu thức `WHERE code = NULL`. Để tìm hàng có giá trị thiếu bằng điều kiện, phải dùng `code IS NULL`.

### 8.3. COUNT(DISTINCT cột) có quy tắc riêng đối với NULL

Một chỗ dễ suy luận sai:

```sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(code) AS known_codes,
    COUNT(DISTINCT code) AS distinct_known_codes
FROM left_rows;
```

Với dữ liệu trái:

| all_rows | known_codes | distinct_known_codes |
|---:|---:|---:|
| 10 | 7 | 4 |

Giải thích:

- `COUNT(*)` đếm mọi hàng: **10**.
- `COUNT(code)` chỉ đếm hàng có `code` **không `NULL`**: **7**.
- `COUNT(DISTINCT code)` đếm các giá trị `code` phân biệt **không `NULL`**: **A, B, C, L = 4**.

Trong khi đó:

```sql
SELECT DISTINCT code
FROM left_rows
ORDER BY code NULLS LAST;
```

trả **5 hàng**: `A`, `B`, `C`, `L` và **một** hàng `NULL`. Vì thế **số hàng của `SELECT DISTINCT code` không nhất thiết bằng `COUNT(DISTINCT code)`** khi có `NULL`. Đừng lấy quy tắc của hàm tổng hợp này để suy ra `UNION` sẽ loại mọi hàng chứa `NULL`.

## 9. Vì sao JOIN với dấu bằng không mô phỏng đúng INTERSECT?

Giả sử muốn đối chiếu **những mẫu `(code, shade)` có ở cả hai bảng**. Một cách thử dễ mắc lỗi:

```sql
SELECT DISTINCT l.code, l.shade
FROM left_rows AS l
JOIN right_rows AS r
    ON l.code = r.code
   AND l.shade = r.shade
ORDER BY l.code NULLS LAST, l.shade NULLS LAST;
```

Kết quả chỉ có:

| code | shade |
|---|---|
| A | red |
| B | blue |

Các mẫu `('A', NULL)`, `(NULL, 'red')` và `(NULL, NULL)` không được ghép vì ít nhất một phép so sánh `=` trả `UNKNOWN`. `DISTINCT` ở đầu ra chỉ loại bản sao của **các cặp đã ghép**, không thể tạo lại những cặp bị loại do `NULL`.

Trong khi đó:

```sql
SELECT code, shade FROM left_rows
INTERSECT
SELECT code, shade FROM right_rows;
```

trả **5 mẫu chung**, bao gồm cả ba mẫu chứa `NULL`.

### 9.1. So sánh NULL-safe bằng IS NOT DISTINCT FROM

PostgreSQL hỗ trợ phép so sánh:

```sql
value_a IS NOT DISTINCT FROM value_b
```

Nó có hành vi:

| a | b | `a = b` | `a IS NOT DISTINCT FROM b` |
|---|---|---|---|
| 5 | 5 | `TRUE` | `TRUE` |
| 5 | 7 | `FALSE` | `FALSE` |
| 5 | `NULL` | `UNKNOWN` | `FALSE` |
| `NULL` | `NULL` | `UNKNOWN` | `TRUE` |

Nếu thực sự muốn dùng `JOIN` theo quy tắc không khác biệt trên cả hai cột:

```sql
SELECT DISTINCT l.code, l.shade
FROM left_rows AS l
JOIN right_rows AS r
    ON l.code IS NOT DISTINCT FROM r.code
   AND l.shade IS NOT DISTINCT FROM r.shade
ORDER BY l.code NULLS LAST, l.shade NULLS LAST;
```

Với dữ liệu mẫu, truy vấn này tạo đúng **5 mẫu chung** như `INTERSECT`. Nhưng bản thân `JOIN` trước `DISTINCT` vẫn có thể sinh **nhiều cặp** do các bản sao lặp ở cả hai bảng, làm tốn tài nguyên hoặc gây nhân hàng nếu chọn thêm cột khác.

**Không biến mọi phép `=` thành so sánh NULL-safe một cách tùy tiện.** Với khóa định danh, hai giá trị chưa biết có thể **không** nên được coi là khớp nhau về nghiệp vụ. Phép toán tập hợp cần quy tắc loại trùng, còn điều kiện quan hệ giữa khách và đơn có thể cần quy tắc hoàn toàn khác.

### 9.2. Mẫu hai cột khác biệt ở một vị trí

Một đối chiếu hàng gồm hai cột không giống phép `OR`:

```sql
-- ĐÚNG cho so khớp cả hàng:
ON l.code IS NOT DISTINCT FROM r.code
AND l.shade IS NOT DISTINCT FROM r.shade
```

Nếu viết `OR` giữa hai điều kiện, `('A', 'red')` có thể khớp với `('A', 'green')` chỉ vì cùng `code = 'A'`. Như thế đang kiểm tra **có ít nhất một cột khớp**, không phải **toàn bộ hàng khớp**. Mọi cột tham gia phép toán tập hợp đều quan trọng.

## 10. Vì sao NOT EXISTS với dấu = cũng có thể khác EXCEPT?

`NOT EXISTS` thường được dùng để tìm bản ghi không có đối tác. Nhưng nếu điều kiện đối chiếu chứa `NULL`, cách viết bằng dấu `=` không luôn tương đương với `EXCEPT`.

### 10.1. Ví dụ NOT EXISTS chưa xử lý NULL

```sql
SELECT DISTINCT l.code, l.shade
FROM left_rows AS l
WHERE NOT EXISTS (
    SELECT 1
    FROM right_rows AS r
    WHERE r.code = l.code
      AND r.shade = l.shade
)
ORDER BY l.code NULLS LAST, l.shade NULLS LAST;
```

Truy vấn con chỉ tìm thấy cặp khớp khi cả hai phép so sánh `=` đều là `TRUE`. Với các mẫu chứa `NULL`, nó không tìm thấy cặp, ngay cả khi phía phải có hàng “không khác biệt” theo quy tắc tập hợp.

Kết quả vì vậy chứa **5 mẫu**:

| code | shade |
|---|---|
| A | `NULL` |
| C | `NULL` |
| L | only |
| `NULL` | red |
| `NULL` | `NULL` |

Trong khi `left_rows EXCEPT right_rows` chỉ có **2 mẫu** `('C', NULL)` và `('L', 'only')`. Ba mẫu `('A', NULL)`, `(NULL, 'red')`, `(NULL, NULL)` bị `EXCEPT` loại vì chúng có ở phía phải.

**Khác biệt không phải lỗi của `NOT EXISTS`**; nó là do biểu thức `=` trong `WHERE` của truy vấn con sử dụng logic ba giá trị, không dùng quy tắc không khác biệt của phép toán tập hợp.

### 10.2. Dùng điều kiện không khác biệt để mô phỏng EXCEPT

Nếu yêu cầu là mô phỏng **`EXCEPT` mặc định** trên hai cột bằng `NOT EXISTS` trong PostgreSQL:

```sql
SELECT DISTINCT l.code, l.shade
FROM left_rows AS l
WHERE NOT EXISTS (
    SELECT 1
    FROM right_rows AS r
    WHERE r.code IS NOT DISTINCT FROM l.code
      AND r.shade IS NOT DISTINCT FROM l.shade
)
ORDER BY l.code NULLS LAST, l.shade NULLS LAST;
```

Kết quả là **2 mẫu** `('C', NULL)` và `('L', 'only')` — cùng tập kết quả với `EXCEPT` mặc định.

Hai yếu tố đều cần chú ý:

1. `IS NOT DISTINCT FROM` ở **từng cột** bảo đảm các hàng có `NULL` cùng vị trí được xem là khớp.
2. `SELECT DISTINCT` bảo đảm đầu ra là **mỗi mẫu một hàng**, giống `EXCEPT` mặc định, ngay cả khi bảng trái có bản sao.

Nếu muốn mô phỏng **`EXCEPT ALL`**, kỹ thuật `NOT EXISTS` nêu trên **không đủ**, vì nó chỉ kiểm tra có/không có đối tác mà không trừ số bản sao. Khi đó phải làm việc với tần suất hoặc phương pháp đánh số bản sao phù hợp.

## 11. Chỉ chọn những cột muốn so sánh

Đây là lỗi rất phổ biến trong đối soát dữ liệu.

Trong bảng mẫu, `row_id` được sinh khác nhau ở hai phía: bảng trái dùng 1–10, bảng phải dùng 101–110. Nếu viết:

```sql
SELECT row_id, code, shade FROM left_rows
INTERSECT
SELECT row_id, code, shade FROM right_rows;
```

Kết quả **rỗng**, vì không có hàng nào trùng **cả `row_id`, `code` và `shade`**. Dù hai phía cùng có `('A', NULL)` ở hai cột nghiệp vụ, ID của bản ghi vẫn khác nhau.

Trong khi:

```sql
SELECT code, shade FROM left_rows
INTERSECT
SELECT code, shade FROM right_rows;
```

trả 5 mẫu chung.

**Quy tắc:** phép toán tập hợp so sánh **toàn bộ bộ cột được chọn**. Nếu đối soát theo một khóa nghiệp vụ gồm `(code, shade)`, đừng vô tình thêm mã ID nội bộ, thời điểm nạp dữ liệu hoặc cột metadata thay đổi mỗi lần nhập vào danh sách so sánh.

Tương tự, nếu cùng một mã `code` nhưng có `shade` khác nhau, việc so sánh cả hai cột cho thấy **hai hàng khác nhau**. Nếu chỉ muốn so sánh danh sách mã `code`, hãy chọn chỉ cột đó — nhưng khi đó bạn đang trả lời câu hỏi khác và có thể gộp các mẫu có màu khác nhau.

### 11.1. Cùng số cột nhưng sai thứ tự cũng sai ý nghĩa

Ví dụ:

```sql
-- Không đúng ý định nếu muốn đối chiếu code với code, shade với shade:
SELECT code, shade FROM left_rows
INTERSECT
SELECT shade, code FROM right_rows;
```

Hai truy vấn vẫn có hai cột văn bản tương thích, nhưng `code` ở trái được so với `shade` ở phải, và ngược lại. SQL không tự ghép cột bằng tên; nó so sánh theo **vị trí thứ nhất với thứ nhất, thứ hai với thứ hai**.

## 12. NULL có thật, chuỗi 'NULL' và giá trị mặc định

Khi dữ liệu đến từ CSV, JSON hoặc một hệ thống khác, thường xuất hiện cách biểu diễn “thiếu dữ liệu” khác nhau:

- `NULL` thật ở cột SQL.
- Chuỗi ký tự `'NULL'`.
- Chuỗi rỗng `''`.
- Chuỗi `'N/A'` hoặc `'unknown'`.
- Giá trị mặc định như `0` hoặc `'-'`.

Những cách biểu diễn này **không tự động tương đương** trong phép toán tập hợp.

Ví dụ PostgreSQL:

```sql
SELECT CAST(NULL AS TEXT) AS v
UNION
SELECT 'NULL' AS v;
```

Kết quả có **hai hàng**: một giá trị SQL `NULL` và một chuỗi thật `'NULL'`. Dấu nháy đơn khiến `'NULL'` trở thành **văn bản**, không phải dấu hiệu thiếu dữ liệu.

Tương tự:

```sql
SELECT CAST(NULL AS TEXT) AS v
UNION
SELECT '' AS v;
```

Trong PostgreSQL, kết quả có **hai hàng**: `NULL` và chuỗi rỗng. Trên Oracle Database, cách xử lý chuỗi rỗng trong nhiều ngữ cảnh ký tự có khác biệt đáng kể (thường được coi như `NULL`); cần kiểm tra phương ngữ trước khi suy luận.

### 12.1. COALESCE có thể thay đổi quy tắc đồng nhất

Nếu muốn coi `NULL` như một nhãn hiển thị, có thể dùng:

```sql
SELECT COALESCE(code, '[missing]') AS displayed_code
FROM left_rows;
```

Nhưng nếu dùng `COALESCE` **ngay trong các cột đối chiếu**, bạn đang thay đổi tiêu chí so sánh. Hai hàng có mã `NULL` và mã thật bằng chuỗi `'[missing]'` sẽ trở nên giống nhau sau biểu thức, dù chúng khác nhau ở dữ liệu gốc.

Để đối soát chính xác, nên phân biệt rõ:

- **Giá trị gốc** dùng để xác định hàng có trùng không.
- **Giá trị hiển thị** chỉ giúp người đọc hiểu dữ liệu thiếu.
- **Giá trị đã chuẩn hóa** (nếu có) phải theo quy tắc nghiệp vụ được xác nhận.

Đừng tự biến `NULL` thành 0, chuỗi rỗng hoặc một mã giả chỉ để “làm cho `UNION` dễ chạy”. SQL đã có quy tắc xử lý `NULL` trong phép toán tập hợp.

## 13. Thứ tự, dấu ngoặc và thứ tự ưu tiên phép toán

### 13.1. ORDER BY không thay đổi quy tắc loại trùng

`ORDER BY ... NULLS FIRST` hoặc `NULLS LAST` chỉ kiểm soát **vị trí hiển thị** của `NULL`, không thay đổi việc một hàng có được xem là trùng trong `UNION` hay chung trong `INTERSECT`.

```sql
SELECT code, shade FROM left_rows
INTERSECT
SELECT code, shade FROM right_rows
ORDER BY code NULLS FIRST, shade NULLS FIRST;
```

Kết quả vẫn là **5 mẫu chung**, chỉ vị trí hiển thị khác với `ORDER BY ... NULLS LAST` ở mục trước.

Trong PostgreSQL, `NULLS FIRST/LAST` có thể ghi trực tiếp sau khóa sắp xếp. Các DBMS khác nhau về mặc định đặt `NULL` đầu/cuối và hỗ trợ cú pháp này. Với kết quả có nhiều bản sao từ `ALL`, `ORDER BY` cũng không tạo danh tính riêng cho các bản sao hoàn toàn giống nhau.

### 13.2. Đặt dấu ngoặc khi phối hợp nhiều phép toán

Khi viết nhiều toán tử tập hợp trong cùng một truy vấn, các DBMS áp dụng quy tắc kết hợp và độ ưu tiên riêng. Trong PostgreSQL, `INTERSECT` có độ ưu tiên cao hơn `UNION` và `EXCEPT`; `UNION` và `EXCEPT` kết hợp từ trái sang phải nếu không có dấu ngoặc.

Để người đọc không phải ghi nhớ độ ưu tiên, hãy dùng ngoặc rõ ràng:

```sql
-- Ví dụ cấu trúc: (A UNION B) rồi mới trừ C
(
    SELECT code, shade FROM left_rows
    UNION
    SELECT code, shade FROM right_rows
)
EXCEPT
SELECT code, shade
FROM left_rows
WHERE code = 'A';
```

Đặc biệt khi sử dụng `ALL`, đổi thứ tự phép toán có thể đổi **số lần xuất hiện**, không chỉ đổi các mẫu được chọn. Trước khi viết câu đối soát phức tạp, hãy xác định từng bước cần áp dụng lên tập dữ liệu nào.

### 13.3. Đừng dựa vào ORDER BY nằm ở từng nhánh

Nếu chỉ cần thứ tự **kết quả cuối**, nên viết `ORDER BY` sau toàn bộ phép toán tập hợp:

```sql
SELECT code, shade FROM left_rows
UNION
SELECT code, shade FROM right_rows
ORDER BY code NULLS LAST, shade NULLS LAST;
```

Sắp xếp từng nguồn riêng không có nghĩa thứ tự đó được giữ sau `UNION` hoặc `INTERSECT`. Khi cần `ORDER BY` đi kèm `LIMIT` trong một nhánh trước khi thực hiện phép toán tập hợp, phải đặt nhánh vào ngoặc/cấu trúc truy vấn phù hợp theo DBMS và hiểu rằng **tập đầu vào đã được giới hạn trước**.

## 14. Đối soát dữ liệu thực tế: chọn DISTINCT hay ALL?

Giả sử một hệ thống nhập bảng kết quả từ hai nguồn. Người kiểm thử đặt câu hỏi: “Hai nguồn có cùng các mã hàng không?” Có hai cách diễn giải:

### 14.1. Đối soát mẫu bản ghi khác biệt

Nếu chỉ cần biết mỗi **mẫu giá trị** có ở nguồn A và B hay không, bất kể số lần lặp:

```sql
-- Những mẫu chỉ có ở trái:
SELECT code, shade FROM left_rows
EXCEPT
SELECT code, shade FROM right_rows;

-- Những mẫu chỉ có ở phải:
SELECT code, shade FROM right_rows
EXCEPT
SELECT code, shade FROM left_rows;
```

Với dữ liệu mẫu:

- Chỉ có bên trái: `('C', NULL)`, `('L', 'only')`.
- Chỉ có bên phải: `('A', 'green')`, `('B', NULL)`, `('R', 'only')`.

Các mẫu `('A', 'red')`, `('A', NULL)`, `(NULL, 'red')`, `(NULL, NULL)`, `('B', 'blue')` hiện diện ở **cả hai nguồn**, dù số bản sao khác nhau.

### 14.2. Đối soát số lần xuất hiện

Nếu yêu cầu là hai nguồn có **cùng dữ liệu kể cả số bản sao**, chỉ kiểm tra `EXCEPT` mặc định là chưa đủ. Ví dụ, trái có hai `('A', 'red')` nhưng phải chỉ một. Cả hai nguồn đều có mẫu này, nên `EXCEPT` mặc định **không báo chênh lệch**; `EXCEPT ALL` sẽ cho thấy bên trái còn **một bản sao dư**.

Trong PostgreSQL, một hướng so sánh là kiểm tra cả hai chiều:

```sql
-- Bản sao dư ở nguồn trái:
SELECT code, shade FROM left_rows
EXCEPT ALL
SELECT code, shade FROM right_rows;

-- Bản sao dư ở nguồn phải:
SELECT code, shade FROM right_rows
EXCEPT ALL
SELECT code, shade FROM left_rows;
```

Để kết luận hai nguồn **khớp hoàn toàn về đa tập hàng**, cả hai kết quả `EXCEPT ALL` phải rỗng. Điều này mạnh hơn việc chỉ so sánh hai danh sách `DISTINCT`.

### 14.3. Kiểm tra tần suất khi DBMS không hỗ trợ EXCEPT ALL

Nếu không thể dùng `EXCEPT ALL`, có thể tạo bảng tổng hợp tần suất theo khóa đối chiếu. Trên PostgreSQL:

```sql
WITH left_counts AS (
    SELECT code, shade, COUNT(*) AS n_left
    FROM left_rows
    GROUP BY code, shade
),
right_counts AS (
    SELECT code, shade, COUNT(*) AS n_right
    FROM right_rows
    GROUP BY code, shade
)
SELECT
    l.code AS left_code,
    l.shade AS left_shade,
    r.code AS right_code,
    r.shade AS right_shade,
    COALESCE(l.n_left, 0) AS count_left,
    COALESCE(r.n_right, 0) AS count_right
FROM left_counts AS l
FULL OUTER JOIN right_counts AS r
    ON l.code IS NOT DISTINCT FROM r.code
   AND l.shade IS NOT DISTINCT FROM r.shade
WHERE l.n_left IS DISTINCT FROM r.n_right
ORDER BY
    COALESCE(l.code, r.code) NULLS LAST,
    COALESCE(l.shade, r.shade) NULLS LAST;
```

Truy vấn này thực hiện **ba bước**:

1. `GROUP BY` mỗi nguồn để tính số bản sao của từng mẫu hàng, kể cả mẫu chứa `NULL`.
2. `FULL OUTER JOIN` hai bảng đếm bằng phép so sánh **NULL-safe** theo từng cột.
3. Chỉ giữ các mẫu có số bản sao khác nhau, coi phía thiếu mẫu là số đếm 0 bằng `COALESCE`.

Ví dụ trên dùng `IS NOT DISTINCT FROM`/`IS DISTINCT FROM` của PostgreSQL; khi chuyển sang DBMS khác, phải thay bằng cú pháp null-safe được hỗ trợ hoặc một phương pháp tương đương. Không thể chỉ nối bằng `l.code = r.code AND l.shade = r.shade` nếu muốn khớp đúng những mẫu có `NULL`.

**Một lưu ý về biểu diễn:** ở mẫu mà `code` hoặc `shade` vốn là `NULL`, cả cột `left_code` và `right_code` trong đầu ra có thể cùng hiển thị `NULL` dù thực sự có hàng ở cả hai phía. Vì thế cần đọc **`count_left` và `count_right`** để phân biệt có bao nhiêu bản ghi, thay vì suy đoán tình trạng khớp chỉ từ ô `NULL`.

### 14.4. Chọn mức chi tiết và cột đối chiếu

Trong công việc thực tế, trước khi đối soát cần trả lời:

- Mỗi hàng đại diện cho **giao dịch, sản phẩm, dòng hóa đơn hay khách hàng**?
- Những cột nào tạo thành **khóa nghiệp vụ** để xác định một mẫu?
- Giá trị `NULL` là **chưa biết**, **không áp dụng**, hay lỗi nhập?
- Cần so khớp **mẫu duy nhất**, hay so **số lần xuất hiện**?
- Có cần chuẩn hóa kiểu, khoảng trắng, chữ hoa/thường, múi giờ hoặc đơn vị tiền trước khi so?
- Có cột metadata như thời điểm nạp, ID nội bộ mà **không nên** đưa vào phép so sánh không?

Đối soát kỹ thuật không chỉ là chọn một từ khóa SQL. Nếu hai nguồn khác quy tắc chuẩn hóa, cùng một giao dịch có thể bị xem là khác nhau; ngược lại, chuẩn hóa quá mức có thể gộp nhầm các giao dịch thật sự khác.

## 15. Khác biệt giữa các phương ngữ SQL

Nguyên tắc **nhận diện hàng không khác biệt khi loại trùng hoặc lấy phần giao/hiệu** là trọng tâm của các phép toán tập hợp theo SQL. Tuy nhiên, khả năng hỗ trợ toán tử và các biến thể `ALL` khác nhau giữa hệ quản trị và phiên bản.

| Hệ quản trị | `UNION` / `UNION ALL` | `INTERSECT` / `EXCEPT` | Biến thể `INTERSECT ALL`, `EXCEPT ALL` |
|---|---|---|---|
| PostgreSQL | Hỗ trợ | Hỗ trợ | Hỗ trợ |
| SQL Server | Hỗ trợ | Hỗ trợ `INTERSECT`, `EXCEPT` | Không có cú pháp `ALL` cho hai phép đó trong các phiên bản thông dụng |
| SQLite | Hỗ trợ | Hỗ trợ | Không hỗ trợ biến thể `ALL` tương ứng trong cú pháp compound SELECT phổ biến |
| MySQL | Hỗ trợ | Khả năng phụ thuộc phiên bản; dòng MySQL 8.0 mới có hỗ trợ | Cần kiểm tra phiên bản và tài liệu cụ thể |
| Oracle Database | Hỗ trợ | Có `INTERSECT` và phép hiệu `MINUS` ở nhiều phiên bản; các tên khác có thể được bổ sung | Cần kiểm tra phiên bản, không giả định đồng nhất |

Một số hệ dùng **`MINUS`** thay hoặc bên cạnh `EXCEPT`. Ngoài cú pháp, cần lưu ý:

- **So sánh văn bản và collation:** các hệ có thể dùng quy tắc khác nhau cho chữ hoa/thường, dấu, khoảng trắng hoặc ký tự Unicode.
- **Kiểu dữ liệu:** từng vị trí trong hai truy vấn cần tương thích; `NULL` không tự sửa lỗi khi hai cột có kiểu không thể hòa hợp.
- **Chuỗi rỗng:** Oracle có hành vi đặc thù coi chuỗi rỗng là `NULL` trong nhiều ngữ cảnh ký tự; PostgreSQL phân biệt `''` với `NULL`.
- **Định dạng và thứ tự kết quả:** các hệ khác nhau về cú pháp `NULLS FIRST`/`NULLS LAST` và mặc định đặt `NULL`; thứ tự sắp xếp **không quyết định** một hàng có trùng trong tập hợp hay không.
- **Biến thể `ALL`:** cần phân biệt phép toán loại trùng với phép toán tính số lần xuất hiện. Không tự mô phỏng `INTERSECT ALL`/`EXCEPT ALL` bằng `INTERSECT`/`EXCEPT` mặc định.

Nếu một câu lệnh bị báo không hỗ trợ, hãy kiểm tra tài liệu của **đúng DBMS và phiên bản** trước khi đổi thuật toán. Với yêu cầu đối soát hàng có `NULL`, nhất thiết phải giữ nguyên ý nghĩa **so khớp NULL-safe** trong giải pháp thay thế.

## 16. Những lỗi thường gặp

### Lỗi 1 — “NULL không bằng NULL, nên UNION phải giữ hai hàng NULL”

Sai. `UNION` loại trùng theo quy tắc hàng **không khác biệt**; hai hàng cùng `NULL` ở các vị trí tương ứng được coi là trùng. `NULL = NULL` không cho `TRUE` trong điều kiện thông thường nhưng đó là ngữ cảnh khác.

### Lỗi 2 — “INTERSECT không thể trả hàng chứa NULL”

Sai. Nếu cả hai đầu vào có cùng mẫu `('A', NULL)` hoặc `(NULL, NULL)`, `INTERSECT` có thể trả mẫu đó.

### Lỗi 3 — “EXCEPT bỏ qua những hàng có NULL”

Sai. `EXCEPT` vẫn xét những hàng chứa `NULL` khi lấy phần hiệu. Một hàng có `NULL` bị loại nếu phía phải có hàng không khác biệt; nếu không có, nó có thể nằm trong kết quả.

### Lỗi 4 — “UNION ALL cũng phải gộp NULL vì chúng trùng nhau”

Sai. `UNION ALL` **không thực hiện bước loại trùng**, bất kể các hàng có `NULL` hay không.

### Lỗi 5 — “INTERSECT ALL giống INTERSECT, chỉ khác thứ tự”

Sai. `INTERSECT ALL` giữ mỗi mẫu số lần bằng **tần suất nhỏ hơn giữa hai phía**, nên có thể chứa nhiều bản sao giống nhau. `INTERSECT` mặc định chỉ trả một bản sao của mỗi mẫu chung.

### Lỗi 6 — “EXCEPT ALL cũng xóa toàn bộ mẫu nếu phía phải xuất hiện”

Sai. `EXCEPT ALL` **trừ số lần xuất hiện**, nên vẫn giữ bản sao dư ở phía trái.

### Lỗi 7 — “JOIN bằng dấu = là cách viết khác của INTERSECT”

Sai trong hai khía cạnh: `JOIN ... ON l.a = r.a` không khớp các cặp `NULL` tương ứng, và `JOIN` có thể nhân hàng theo số cặp khớp. `INTERSECT` mặc định so khớp mẫu null-safe và loại trùng.

### Lỗi 8 — “NOT EXISTS với dấu = luôn tương đương EXCEPT”

Không luôn đúng khi có `NULL`. `NOT EXISTS` chỉ kiểm tra các hàng thỏa điều kiện tương quan, còn `=` với `NULL` có kết quả `UNKNOWN`. Khi cần mô phỏng `EXCEPT`, phải dùng điều kiện so sánh không khác biệt và xử lý trùng lặp phù hợp.

### Lỗi 9 — “Thêm ID vào SELECT không ảnh hưởng tập kết quả”

Sai. Phép toán tập hợp so sánh **tất cả các cột được chọn**. Nếu hai phía có ID khác nhau, những hàng giống nhau ở cột nghiệp vụ có thể không còn được xem là trùng.

### Lỗi 10 — “GROUP BY gom NULL nhưng COUNT(DISTINCT col) phải đếm một NULL”

Không nhất thiết. `SELECT DISTINCT col` có thể hiển thị một hàng `NULL`; `COUNT(DISTINCT col)` theo ngữ nghĩa tổng hợp thông thường chỉ đếm giá trị **không `NULL`**. Phải phân biệt loại trùng hàng với cách hàm đếm xử lý giá trị thiếu.

### Lỗi 11 — “COALESCE(NULL, 0) an toàn trong mọi đối soát”

Không. Thay `NULL` bằng 0 làm mất khác biệt giữa **giá trị chưa biết** và **giá trị bằng 0**; nếu nguồn có số 0 thật, các hàng có thể bị đồng nhất sai.

### Lỗi 12 — “Không có ORDER BY nghĩa là tập hợp sẽ được sắp theo cột đầu tiên”

Không. Các phép toán tập hợp không bảo đảm thứ tự xuất hiện; DBMS có thể dùng nhiều chiến lược thực thi. `ORDER BY` cuối truy vấn nếu cần thứ tự ổn định.

## 17. Bài tập tự thực hành

Sử dụng các bảng `left_rows` và `right_rows` ở mục 3. Hãy **dự đoán kết quả trước khi chạy**.

### Bài 1 — Hai NULL trong UNION

```sql
SELECT CAST(NULL AS INTEGER) AS x
UNION
SELECT CAST(NULL AS INTEGER);
```

**Đáp án:** **một** hàng `NULL`. Giải thích vì sao câu này không mâu thuẫn với `NULL = NULL` trả `UNKNOWN`.

### Bài 2 — UNION ALL

```sql
SELECT CAST(NULL AS INTEGER) AS x
UNION ALL
SELECT CAST(NULL AS INTEGER);
```

**Đáp án:** **hai** hàng, đều có giá trị `NULL`. Vì `ALL` không loại trùng.

### Bài 3 — Phần giao có NULL

```sql
SELECT code, shade FROM left_rows
INTERSECT
SELECT code, shade FROM right_rows
ORDER BY code NULLS LAST, shade NULLS LAST;
```

**Đáp án:** **5 mẫu**: `('A','red')`, `('A',NULL)`, `('B','blue')`, `(NULL,'red')`, `(NULL,NULL)`.

### Bài 4 — Phần hiệu theo hai chiều

```sql
SELECT code, shade FROM left_rows
EXCEPT
SELECT code, shade FROM right_rows;
```

```sql
SELECT code, shade FROM right_rows
EXCEPT
SELECT code, shade FROM left_rows;
```

**Đáp án:** chiều trái–phải có **2** mẫu `('C',NULL)`, `('L','only')`; chiều phải–trái có **3** mẫu `('A','green')`, `('B',NULL)`, `('R','only')`.

### Bài 5 — INTERSECT ALL và EXCEPT ALL

Không cần chạy ngay. Dựa vào số bản sao của `('A', NULL)` và `(NULL, 'red')`:

1. `INTERSECT ALL` trả bao nhiêu bản sao của hai mẫu này?
2. `EXCEPT ALL` trái trừ phải còn bao nhiêu?

**Đáp án:** `('A',NULL)` có 2 ở trái và 2 ở phải → `INTERSECT ALL` giữ **2**, `EXCEPT ALL` còn **0**. `(NULL,'red')` có 2 ở trái và 1 ở phải → `INTERSECT ALL` giữ **1**, `EXCEPT ALL` còn **1**.

### Bài 6 — Thay INTERSECT bằng INNER JOIN sai ở đâu?

```sql
SELECT DISTINCT l.code, l.shade
FROM left_rows AS l
JOIN right_rows AS r
  ON l.code = r.code
 AND l.shade = r.shade;
```

**Đáp án:** chỉ có **2 mẫu** `('A','red')` và `('B','blue')`. Hãy sửa bằng `IS NOT DISTINCT FROM` trên **cả hai cột** để nhận đủ **5 mẫu chung** như `INTERSECT` mặc định.

### Bài 7 — NOT EXISTS với và không có NULL-safe

Chạy hai truy vấn:

```sql
-- A: so sánh bằng thông thường.
SELECT DISTINCT l.code, l.shade
FROM left_rows AS l
WHERE NOT EXISTS (
    SELECT 1
    FROM right_rows AS r
    WHERE r.code = l.code
      AND r.shade = l.shade
);

-- B: so sánh NULL-safe.
SELECT DISTINCT l.code, l.shade
FROM left_rows AS l
WHERE NOT EXISTS (
    SELECT 1
    FROM right_rows AS r
    WHERE r.code IS NOT DISTINCT FROM l.code
      AND r.shade IS NOT DISTINCT FROM l.shade
);
```

**Đáp án:** A có **5 mẫu** vì những mẫu chứa `NULL` không khớp bằng `=`; B có **2 mẫu** và tương đương `EXCEPT` mặc định trên hai cột.

### Bài 8 — Tác động của việc thêm row_id

```sql
SELECT row_id, code, shade FROM left_rows
INTERSECT
SELECT row_id, code, shade FROM right_rows;
```

**Đáp án:** **0 hàng**, vì dãy ID của hai bảng không giao nhau. Tại sao cần loại `row_id` khỏi các cột đối chiếu nếu chỉ muốn so sánh theo `(code, shade)`?

### Bài 9 — COUNT(DISTINCT) và SELECT DISTINCT

```sql
SELECT COUNT(DISTINCT code) FROM left_rows;

SELECT DISTINCT code
FROM left_rows
ORDER BY code NULLS LAST;
```

**Đáp án:** câu đầu cho **4** (A, B, C, L); câu sau có **5 hàng** (A, B, C, L, NULL). Giải thích vì sao `COUNT(DISTINCT code)` không tính giá trị `NULL`.

### Bài 10 — Tình huống đối soát thực tế

Nguồn A có hai lần `('A','red')`, nguồn B có một lần `('A','red')`; mọi mẫu khác đều khớp nhau. Yêu cầu:

1. Kiểm tra **hai nguồn có cùng tập mẫu khác biệt** hay không.
2. Kiểm tra **hai nguồn có cùng số bản sao của từng mẫu** hay không.

**Đáp án định hướng:** yêu cầu 1 có thể dùng `EXCEPT` hai chiều; cả hai kết quả rỗng trong tình huống đã nêu. Yêu cầu 2 cần `EXCEPT ALL` hai chiều hoặc bảng đếm tần suất; sẽ thấy A còn dư **một** `('A','red')`. Hãy giải thích vì sao `UNION`/`INTERSECT` mặc định không đủ để phát hiện chênh lệch về số bản sao.

## 18. Bảng ghi nhớ nhanh

| Tình huống | Hành vi cần nhớ |
|---|---|
| `NULL = NULL` trong `WHERE` | `UNKNOWN`, không phải `TRUE` |
| Hai hàng `(NULL, NULL)` trong `UNION` | Được xem là trùng; giữ một bản sao |
| Hai hàng `('A', NULL)` ở hai phía `INTERSECT` | Được xem là cùng mẫu; xuất hiện trong phần giao |
| `('A', NULL)` ở cả trái và phải trong `EXCEPT` | Bị loại khỏi kết quả trái |
| `('A', NULL)` và `(NULL, 'A')` | Là hai mẫu khác nhau |
| `UNION ALL` | Không loại trùng |
| `INTERSECT ALL` | Giữ min(số bản sao trái, số bản sao phải) |
| `EXCEPT ALL` | Giữ max(số bản sao trái - phải, 0) |
| `SELECT DISTINCT` / `GROUP BY` | Các mẫu có `NULL` cùng vị trí được nhóm hoặc loại trùng |
| `COUNT(DISTINCT col)` | Không tính `NULL` trong các giá trị được đếm |
| `JOIN ON a = b` khi cả hai `NULL` | Không khớp vì điều kiện là `UNKNOWN` |
| `a IS NOT DISTINCT FROM b` | Cách so sánh NULL-safe khi DBMS hỗ trợ |
| `ORDER BY ... NULLS LAST` | Chỉ ảnh hưởng thứ tự hiển thị |
| `EXCEPT` trên cột nghiệp vụ | Không tự so sánh theo ID bị loại khỏi `SELECT` |

## Kết luận

Trong SQL, cần tách biệt **so sánh logic thông thường** với **so sánh hàng dùng để thực hiện phép toán tập hợp**:

- `NULL = NULL` không cho `TRUE` trong `WHERE` và `JOIN ... ON`, mà cho `UNKNOWN`.
- Khi nhận diện hàng trùng trong `UNION`, lấy phần giao bằng `INTERSECT` hoặc loại phần chung bằng `EXCEPT`, **hai vị trí cùng `NULL` được xem là không khác biệt**. Quy tắc xét **toàn bộ các cột được chọn**.
- Các dạng mặc định làm việc với **các mẫu khác biệt**; những dạng `ALL` được hỗ trợ sẽ tính tới **số lần xuất hiện**.
- `JOIN` hoặc `NOT EXISTS` chỉ tương đương phép toán tập hợp trong một số điều kiện nhất định; muốn mô phỏng cách đối chiếu hàng có `NULL` cần dùng **so sánh NULL-safe** và xử lý bản sao phù hợp.
- Khi đối soát dữ liệu, hãy quyết định **so mẫu hay so số bản sao**, chọn đúng cột nghiệp vụ và không trộn giá trị SQL `NULL` với chuỗi `'NULL'` hoặc số 0.

Nếu ghi nhớ một nguyên tắc duy nhất, hãy nhớ: **“`NULL` không bằng `NULL` theo toán tử `=` thông thường, nhưng hai hàng có `NULL` ở cùng vị trí vẫn có thể là một mẫu hàng trong `UNION`, `INTERSECT` và `EXCEPT`.”** Phân biệt được hai ngữ cảnh này là nền tảng để viết truy vấn tập hợp chính xác, đặc biệt khi dữ liệu thực tế chứa những trường chưa được xác định.

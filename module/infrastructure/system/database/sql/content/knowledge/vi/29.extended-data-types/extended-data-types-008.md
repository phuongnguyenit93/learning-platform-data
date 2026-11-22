# Kiểu mảng, phép truy cập phần tử và chuyển mảng thành hàng

SQL thường được học với mô hình **mỗi ô chứa một giá trị**, còn các thông tin lặp lại được đặt ở nhiều hàng của bảng con. Tuy nhiên, một số hệ quản trị hỗ trợ **kiểu mảng (*array*)** để một cột lưu nhiều phần tử có thứ tự: danh sách nhãn sản phẩm, các điểm đánh giá, một chuỗi số đo, những mã liên quan hoặc danh sách bước xử lý.

Ví dụ sản phẩm 101 có ba nhãn:

```text
product_id = 101
tags       = ['clothing', 'blue', 'sale']
```

Khi làm việc với cột này, ta cần trả lời những câu hỏi rất khác nhau:

- **Truy cập phần tử:** nhãn đầu tiên là gì? Nhãn cuối cùng là gì? Có phần tử ở vị trí 0 không?
- **Truy cập một đoạn:** lấy hai nhãn đầu, hoặc đọc cả chiều dài mảng?
- **Tìm kiếm:** sản phẩm có nhãn `sale` không? Có ít nhất một nhãn trong tập `blue`, `sport` không?
- **Chuyển mảng thành hàng:** làm sao biến ba nhãn thành ba dòng kết quả để `JOIN`, `GROUP BY`, `COUNT` hoặc phân tích?
- **Khôi phục dữ liệu:** làm sao gom nhiều hàng thành một mảng theo thứ tự xác định?
- **Xử lý ngoại lệ:** mảng rỗng, mảng `NULL`, phần tử `NULL` và phần tử bị lặp có giống nhau không?

Bài học thuộc chương **Dữ liệu mở rộng** của **Database SQL**. Phần chính dùng **PostgreSQL** với kiểu mảng thật như `text[]` và `integer[]`, cú pháp `ARRAY[...]`, chỉ số phần tử, `UNNEST`, `WITH ORDINALITY` và `LATERAL`. Phần sau đối chiếu **BigQuery, Snowflake, MySQL, SQL Server, SQLite và Oracle**, bởi các hệ này **không dùng chung cú pháp hay cùng hệ chỉ số**.

> **Điểm quan trọng nhất:** PostgreSQL thường bắt đầu chỉ số mảng tại **1**; BigQuery, Snowflake và các đường dẫn JSON thông dụng thường bắt đầu tại **0**. Ngoài ra, một truy vấn bung mảng có thể **làm mất hàng gốc có mảng rỗng hoặc NULL** nếu dùng kiểu join không phù hợp. Không được port câu SQL xử lý mảng giữa DBMS bằng cách chỉ đổi tên hàm.

## 1. Phân biệt mảng SQL với chuỗi ký tự và bảng con

### 1.1. Mảng có các phần tử riêng biệt

Một cột PostgreSQL:

```sql
tags TEXT[]
```

có thể chứa:

```text
{'clothing','blue','sale'}
```

Đây là **một giá trị mảng** chứa ba giá trị `TEXT`, không phải một chuỗi đơn có dấu phẩy. Cơ sở dữ liệu biết về **phần tử**, **kiểu phần tử**, **chiều**, **vị trí**, và có các hàm/toán tử thao tác trực tiếp.

So với việc lưu chuỗi:

```text
clothing,blue,sale
```

mảng tránh việc phải tự tách chuỗi theo dấu phẩy trong các trường hợp đơn giản. Nếu nhãn chứa dấu phẩy, dấu nháy hoặc ký tự escape, tự mã hóa danh sách bằng chuỗi càng dễ lỗi.

### 1.2. Mảng và JSON array không tự động giống nhau

Hai biểu diễn:

```sql
ARRAY['blue', 'sale']::TEXT[]
```

và:

```json
["blue", "sale"]
```

có nội dung nhìn tương tự nhưng **khác kiểu dữ liệu**:

- `TEXT[]` là mảng SQL PostgreSQL có kiểu phần tử `TEXT`.
- `JSON`/`JSONB` có cấu trúc dữ liệu JSON và có thể chứa các kiểu giá trị khác nhau, object lồng nhau, JSON null, v.v.
- Cú pháp lấy phần tử, so sánh, kiểm tra tồn tại, tạo chỉ mục và bung mảng **không hoàn toàn trùng nhau**.

Không giả định rằng `UNNEST(jsonb_column)` có cùng hành vi với `UNNEST(text_array_column)`. PostgreSQL có các hàm JSON như `jsonb_array_elements` hoặc `jsonb_array_elements_text` dành cho JSONB.

### 1.3. Mảng và bảng con: chọn theo quan hệ dữ liệu

Một danh sách nhãn sản phẩm cũng có thể lưu ở bảng chuẩn hóa:

```text
products
---------
product_id | product_name
101        | Ao xanh

product_tags
------------
product_id | position | tag
101        | 1        | clothing
101        | 2        | blue
101        | 3        | sale
```

Mảng thuận tiện khi danh sách nhỏ, thường được đọc cùng bản ghi, ít cần ràng buộc từng phần tử. Bảng con thường phù hợp hơn nếu cần khóa ngoại từ từng nhãn, tìm kiếm và thống kê phức tạp, cập nhật từng phần tử nhiều, hoặc đảm bảo tính duy nhất/phân quyền ở cấp quan hệ.

**Dùng được mảng không có nghĩa mọi quan hệ một-nhiều đều nên được nhét vào một cột.**

## 2. Bộ dữ liệu mẫu PostgreSQL

Tạo một bảng sản phẩm có hai cột mảng:

- `tags TEXT[]`: các nhãn của sản phẩm.
- `scores INTEGER[]`: các điểm đánh giá thử nghiệm.

Hai cột đều cho phép `NULL` để luyện phân biệt giá trị thiếu và mảng rỗng.

### 2.1. Tạo bảng

```sql
CREATE TABLE product_array_lab (
    product_id INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    product_name TEXT NOT NULL,
    tags TEXT[],
    scores INTEGER[]
);
```

### 2.2. Nạp tám sản phẩm

```sql
INSERT INTO product_array_lab
    (product_id, tenant_id, product_name, tags, scores)
VALUES
    (101, 1, 'Ao xanh',
     ARRAY['clothing', 'blue', 'sale'],
     ARRAY[5, 4, 5]),

    (102, 1, 'Ao trang',
     ARRAY['clothing', 'white'],
     ARRAY[4, 4]),

    (103, 1, 'Giay chay',
     ARRAY['shoes', 'sport', 'sale'],
     ARRAY[5, 3, 5, 4]),

    (104, 1, 'Mu',
     '{}'::TEXT[],
     '{}'::INTEGER[]),

    (105, 2, 'Tui xanh',
     ARRAY['bag', 'blue'],
     ARRAY[NULL, 5]::INTEGER[]),

    (106, 2, 'Binh nuoc',
     NULL::TEXT[],
     NULL::INTEGER[]),

    (107, 2, 'Ao the thao',
     ARRAY['clothing', 'sport', 'sport'],
     ARRAY[4, 5]),

    (108, 2, 'Ao cam',
     ARRAY['clothing', 'orange'],
     ARRAY[3]);
```

### 2.3. Nhận diện từng trường hợp

| product_id | tenant | tags | scores | Điểm cần quan sát |
|---:|---:|---|---|---|
| 101 | 1 | clothing, blue, sale | 5, 4, 5 | Ba nhãn và ba điểm |
| 102 | 1 | clothing, white | 4, 4 | Hai nhãn |
| 103 | 1 | shoes, sport, sale | 5, 3, 5, 4 | Bốn điểm |
| 104 | 1 | **mảng rỗng** | **mảng rỗng** | Không có phần tử |
| 105 | 2 | bag, blue | **NULL**, 5 | Mảng có một phần tử NULL |
| 106 | 2 | **NULL** | **NULL** | Bản thân cột mảng không có giá trị |
| 107 | 2 | clothing, sport, sport | 4, 5 | Nhãn `sport` lặp hai lần |
| 108 | 2 | clothing, orange | 3 | Mảng một phần tử |

Bảng có **8 hàng sản phẩm**. Nếu bung tất cả `tags` theo số phần tử:

```text
101: 3
102: 2
103: 3
104: 0
105: 2
106: không có mảng -> 0 hàng khi UNNEST
107: 3
108: 2
--------------------------
Tổng: 15 phần tử nhãn
```

Hai tình huống phải nhớ:

- `product_id = 104` có mảng `'{}'::TEXT[]`: **mảng tồn tại nhưng có 0 phần tử**.
- `product_id = 106` có `tags IS NULL`: **giá trị mảng không tồn tại/không được biết**, không nhất thiết có nghĩa “không có nhãn”.

## 3. Tạo mảng với ARRAY[...] và kiểu phần tử

### 3.1. Array constructor

Trong PostgreSQL:

```sql
SELECT ARRAY[10, 20, 30] AS numbers;
```

Trả một giá trị mảng số nguyên gồm ba phần tử.

```sql
SELECT ARRAY['red', 'blue', 'green']::TEXT[] AS colors;
```

Trả một mảng `TEXT[]`. Việc ép kiểu `::TEXT[]` làm rõ kiểu cột khi biểu thức có thể bị suy diễn theo ngữ cảnh khác.

### 3.2. Mảng rỗng cần kiểu rõ ràng

Một mảng rỗng:

```sql
SELECT '{}'::TEXT[] AS empty_tags;
```

khác với:

```sql
SELECT NULL::TEXT[] AS missing_tags;
```

Nếu dùng dạng constructor rỗng `ARRAY[]`, PostgreSQL cần biết **kiểu của phần tử**:

```sql
SELECT ARRAY[]::INTEGER[] AS empty_scores;
```

Không thể để PostgreSQL tự suy ra chính xác kiểu phần tử của một constructor không chứa gì trong mọi ngữ cảnh.

### 3.3. Các phần tử thường cùng một kiểu

`INTEGER[]` chứa các giá trị số nguyên hoặc `NULL` có kiểu tương ứng; `TEXT[]` chứa các giá trị văn bản. Không nên giả định một mảng SQL typed có thể tự do chứa object JSON, số, chuỗi và các cấu trúc không đồng nhất theo cách tương tự JSON array.

Ví dụ mảng điểm:

```sql
SELECT ARRAY[5, NULL, 4]::INTEGER[] AS scores;
```

được phép nếu phần tử mảng chấp nhận `NULL` trong ngữ cảnh đó. Việc cột `scores INTEGER[]` không có `NOT NULL` nói về **toàn bộ cột mảng**, không mặc nhiên áp ràng buộc “mọi phần tử phải khác NULL”.

### 3.4. Dạng literal dấu ngoặc nhọn

PostgreSQL hỗ trợ input literal của mảng:

```sql
SELECT '{blue,sale}'::TEXT[] AS tags;
```

Với phần tử có dấu phẩy, khoảng trắng, dấu nháy hoặc ký tự escape, dạng literal có quy tắc trích dẫn riêng và dễ viết sai. Khi viết SQL hoặc truyền giá trị từ ứng dụng, nên ưu tiên **parameter binding** và `ARRAY[...]`/driver array APIs phù hợp thay vì tự nối chuỗi literal phức tạp.

### 3.5. Tạo mảng từ truy vấn con

PostgreSQL cho phép:

```sql
SELECT ARRAY(
    SELECT p.product_id
    FROM product_array_lab AS p
    WHERE p.tenant_id = 1
    ORDER BY p.product_id
) AS tenant_1_product_ids;
```

Kết quả là mảng:

```text
{101,102,103,104}
```

**Thứ tự** được xác định nhờ `ORDER BY` trong truy vấn tạo phần tử. Nếu bỏ `ORDER BY`, không dựa vào thứ tự hàng tình cờ do bảng/index trả ra.

## 4. Truy cập phần tử: chỉ số bắt đầu từ 1 trong mảng PostgreSQL thông thường

Với:

```sql
SELECT tags
FROM product_array_lab
WHERE product_id = 101;
```

mảng `tags` là:

```text
vị trí:    1            2       3
phần tử: clothing     blue    sale
```

### 4.1. Lấy phần tử bằng dấu ngoặc vuông

```sql
SELECT
    product_id,
    tags[1] AS first_tag,
    tags[2] AS second_tag,
    tags[3] AS third_tag
FROM product_array_lab
WHERE product_id = 101;
```

Kết quả:

| product_id | first_tag | second_tag | third_tag |
|---:|---|---|---|
| 101 | clothing | blue | sale |

Với các mảng thông thường do `ARRAY[...]` tạo, **phần tử đầu tiên có chỉ số 1**, không phải 0.

### 4.2. Chỉ số 0 không phải phần tử đầu

```sql
SELECT
    product_id,
    tags[0] AS index_zero,
    tags[1] AS index_one
FROM product_array_lab
WHERE product_id = 101;
```

Với mảng mẫu có lower bound 1:

| index_zero | index_one |
|---|---|
| `NULL` | clothing |

Trong PostgreSQL, chỉ số ngoài phạm vi của mảng thông thường thường cho giá trị `NULL` khi đọc theo cách hợp lệ, không tự chuyển `tags[0]` thành phần tử đầu tiên.

### 4.3. Chỉ số vượt chiều dài

```sql
SELECT tags[99] AS tag_99
FROM product_array_lab
WHERE product_id = 101;
```

Với mảng chỉ có ba phần tử, kết quả đọc thường là `NULL`. Tuy nhiên:

> **`tags[99] IS NULL` không chứng minh mảng chứa phần tử NULL ở vị trí 99.**

Nó có thể chỉ là **không có phần tử tại vị trí đó**. Muốn biết kích thước/cận chỉ số, dùng `cardinality`, `array_lower` và `array_upper`, không chỉ kiểm tra giá trị đọc.

### 4.4. PostgreSQL không dùng -1 như Python để lấy phần tử cuối

Nhiều ngôn ngữ dùng `array[-1]` cho phần tử cuối. Đối với mảng PostgreSQL thông thường bắt đầu tại 1, `tags[-1]` **không** mang ý nghĩa “phần tử cuối”.

Thay vào đó:

```sql
SELECT
    product_id,
    tags[array_upper(tags, 1)] AS last_tag
FROM product_array_lab
WHERE product_id = 101;
```

Kết quả: `sale`.

`array_upper(tags, 1)` trả cận trên của chiều thứ nhất khi xác định được. Với mảng rỗng hoặc `NULL`, phải chấp nhận trường hợp kết quả không có cận để lấy phần tử.

### 4.5. Cận chỉ số có thể không bắt đầu tại 1

PostgreSQL còn hỗ trợ mảng có cận dưới khác 1. Ví dụ:

```sql
WITH x AS (
    SELECT array_fill(
        7,
        ARRAY[4],
        ARRAY[-2]
    ) AS numbers
)
SELECT
    array_lower(numbers, 1) AS lower_bound,
    array_upper(numbers, 1) AS upper_bound,
    numbers[-2] AS first_actual_element,
    numbers[1] AS last_actual_element
FROM x;
```

Mảng này có bốn phần tử số 7, nhưng chỉ số thực từ **-2 đến 1**. Do đó:

- “Phần tử đầu tiên của mảng” nên hiểu theo **cận dưới thực tế**.
- “Vị trí thứ nhất” khi bung mảng bằng ordinality không nhất thiết trùng **subscript thực tế** nếu mảng có lower bound tùy chỉnh.
- Trong phần lớn ứng dụng dùng `ARRAY[...]`, cận dưới là 1, nhưng không nên khẳng định đó là quy luật bất biến của mọi mảng PostgreSQL.

## 5. Lấy một lát cắt mảng

PostgreSQL cho phép lấy **đoạn con** bằng dấu hai chấm:

```sql
SELECT
    product_id,
    tags[1:2] AS first_two_tags,
    tags[2:3] AS second_to_third
FROM product_array_lab
WHERE product_id = 101;
```

Kết quả:

```text
first_two_tags = {clothing,blue}
second_to_third = {blue,sale}
```

### 5.1. Lát cắt trả mảng, không phải giá trị scalar

So sánh:

```sql
tags[2]   -- TEXT: một phần tử
tags[1:2] -- TEXT[]: một mảng con
```

Sự khác biệt kiểu dữ liệu ảnh hưởng trực tiếp đến toán tử và hàm có thể dùng tiếp. Không dùng kết quả `tags[1:2]` như một chuỗi đơn nếu truy vấn muốn một phần tử.

### 5.2. Lát cắt vượt cận

Với mảng có ba phần tử, lát cắt `tags[2:99]` có thể chỉ lấy phần giao giữa đoạn yêu cầu và phạm vi hiện có theo quy tắc mảng PostgreSQL, thay vì tạo ra 98 vị trí `NULL` giống một vector cố định.

Hãy nhớ mảng có **cận chỉ số**, không tự sinh phần tử mới khi bạn yêu cầu đọc một lát cắt. Nếu cần chính xác số phần tử, dùng `cardinality` hoặc các hàm chỉ số và kiểm tra dữ liệu.

### 5.3. Mảng hai chiều có cú pháp lát cắt tương tự

Với `INTEGER[][]`, có thể dùng `matrix[1][2]` để lấy một ô, hoặc `matrix[1:2][1:2]` để lấy vùng mảng. Phần 13 đi sâu vào truy cập và bung mảng nhiều chiều.

## 6. Mảng NULL, mảng rỗng và phần tử NULL

Đây là ba trạng thái **không được gộp làm một**.

| Giá trị cột | Ý nghĩa | `cardinality` trên PostgreSQL |
|---|---|---:|
| `NULL::TEXT[]` | Không có giá trị mảng/không biết danh sách | `NULL` |
| `'{}'::TEXT[]` | Có mảng, nhưng có **0 phần tử** | 0 |
| `ARRAY[NULL]::TEXT[]` | Mảng có **1 phần tử**, phần tử đó là NULL | 1 |
| `ARRAY['a',NULL,'b']::TEXT[]` | Mảng có 3 vị trí, một giá trị thiếu | 3 |

### 6.1. Đo bằng cardinality

```sql
SELECT
    cardinality(NULL::TEXT[]) AS null_array_size,
    cardinality('{}'::TEXT[]) AS empty_array_size,
    cardinality(ARRAY[NULL]::TEXT[]) AS one_null_element_size,
    cardinality(ARRAY['a', NULL, 'b']::TEXT[]) AS mixed_array_size;
```

Kết quả:

| null_array_size | empty_array_size | one_null_element_size | mixed_array_size |
|---|---:|---:|---:|
| `NULL` | 0 | 1 | 3 |

### 6.2. array_length không đồng nghĩa cardinality

```sql
SELECT
    cardinality('{}'::TEXT[]) AS num_elements,
    array_length('{}'::TEXT[], 1) AS dimension_length;
```

Trong PostgreSQL, với một mảng rỗng:

```text
num_elements     = 0
dimension_length = NULL
```

Do đó không được viết logic:

```sql
WHERE array_length(tags, 1) = 0
```

rồi cho rằng nó tìm được mọi mảng rỗng. So sánh `NULL = 0` không cho `TRUE`.

Để lọc mảng rỗng đúng ý định:

```sql
SELECT product_id
FROM product_array_lab
WHERE cardinality(tags) = 0;
```

Kết quả: **104**.

Để lọc cột không có giá trị mảng:

```sql
SELECT product_id
FROM product_array_lab
WHERE tags IS NULL;
```

Kết quả: **106**.

### 6.3. Kiểm tra cả NULL và rỗng khi nghiệp vụ coi như nhau

Một số báo cáo muốn coi `NULL` và `{}` đều là “không có nhãn khả dụng”. Có thể viết:

```sql
SELECT product_id
FROM product_array_lab
WHERE tags IS NULL
   OR cardinality(tags) = 0
ORDER BY product_id;
```

Kết quả: **104, 106**.

Đây là **quy tắc nghiệp vụ chủ ý**. Nó làm mất phân biệt giữa “chưa biết danh sách” và “đã biết chắc không có nhãn”; với hệ thống nhập liệu, phân biệt này có thể rất quan trọng.

### 6.4. Phần tử NULL không làm toàn mảng thành NULL

`scores` của 105 là:

```text
{NULL,5}
```

```sql
SELECT
    product_id,
    scores IS NULL AS array_missing,
    cardinality(scores) AS total_positions,
    scores[1] AS first_score,
    scores[2] AS second_score
FROM product_array_lab
WHERE product_id = 105;
```

Kết quả:

| product_id | array_missing | total_positions | first_score | second_score |
|---:|---|---:|---|---:|
| 105 | false | 2 | `NULL` | 5 |

Nếu nghiệp vụ nói “điểm đánh giá luôn là 1–5 và không được NULL”, ràng buộc cho **toàn cột `NOT NULL`** chưa đủ để cấm từng phần tử NULL. Có thể cần validation khi ghi hoặc chuẩn hóa điểm thành bảng con với `score NOT NULL CHECK (score BETWEEN 1 AND 5)`.

## 7. Hàm hữu ích khi truy cập và thao tác mảng

### 7.1. array_lower, array_upper và array_dims

```sql
SELECT
    product_id,
    array_lower(tags, 1) AS first_subscript,
    array_upper(tags, 1) AS last_subscript,
    array_dims(tags) AS dimensions
FROM product_array_lab
WHERE product_id IN (101, 104, 106)
ORDER BY product_id;
```

Với 101, cận thông thường là `1` và `3`, còn `array_dims(tags)` diễn tả chiều và cận, ví dụ `[1:3]`. Với mảng rỗng và giá trị NULL, không có một dải chỉ số phần tử hữu dụng.

### 7.2. array_position và array_positions

```sql
SELECT
    product_id,
    array_position(tags, 'sport') AS first_sport_position,
    array_positions(tags, 'sport') AS all_sport_positions
FROM product_array_lab
WHERE product_id IN (103, 107)
ORDER BY product_id;
```

Kết quả:

| product_id | first_sport_position | all_sport_positions |
|---:|---:|---|
| 103 | 2 | `{2}` |
| 107 | 2 | `{2,3}` |

`array_position` trả **vị trí đầu tiên khớp** hoặc `NULL` nếu không tìm thấy (theo ngữ nghĩa của hàm). `array_positions` trả danh sách các vị trí khớp; nó giúp thấy rõ nhãn lặp ở sản phẩm 107.

Với những hàm này, việc so khớp `NULL` có quy tắc riêng của PostgreSQL; không suy diễn hoàn toàn từ biểu thức `= NULL` trong `WHERE`.

### 7.3. array_append và array_prepend

```sql
SELECT
    array_append(ARRAY['blue']::TEXT[], 'sale') AS append_result,
    array_prepend('new', ARRAY['blue']::TEXT[]) AS prepend_result;
```

Kết quả lần lượt:

```text
{blue,sale}
{new,blue}
```

### 7.4. Nối hai mảng bằng ||

```sql
SELECT
    ARRAY['blue','sale']::TEXT[]
    || ARRAY['sport']::TEXT[] AS combined_tags;
```

Kết quả:

```text
{blue,sale,sport}
```

Phép nối mảng **không mặc định loại phần tử trùng**. Ví dụ nối `{sport}` với `{sport}` tạo hai phần tử `sport`.

### 7.5. array_remove và phần tử lặp

```sql
SELECT
    product_id,
    tags AS original_tags,
    array_remove(tags, 'sport') AS without_sport
FROM product_array_lab
WHERE product_id = 107;
```

Kết quả:

```text
original_tags = {clothing,sport,sport}
without_sport = {clothing}
```

`array_remove` loại **tất cả phần tử bằng giá trị cần loại** theo quy tắc hàm, không chỉ xóa phần tử `sport` đầu tiên. Nếu yêu cầu “xóa đúng phần tử ở vị trí thứ hai nhưng giữ vị trí thứ ba”, cần thiết kế phép biến đổi theo vị trí, không chỉ gọi `array_remove`.

### 7.6. string_to_array và array_to_string

```sql
SELECT
    string_to_array('blue,sale,sport', ',') AS parsed,
    array_to_string(
        ARRAY['blue','sale','sport']::TEXT[],
        ','
    ) AS joined;
```

Kết quả tương đương:

```text
parsed = {blue,sale,sport}
joined = blue,sale,sport
```

Đây là minh họa cho **dữ liệu đơn giản không có dấu phân cách nằm bên trong phần tử**. Với dữ liệu người dùng nhập có dấu phẩy, dấu nháy hoặc escape, không được dùng phép tách chuỗi đơn giản như một giao thức trao đổi dữ liệu không mất mát; hãy dùng JSON/CSV parser có quy tắc chuẩn hoặc array parameters.

## 8. Lọc sản phẩm có phần tử bằng ANY

PostgreSQL hỗ trợ:

```sql
expression = ANY(array_expression)
```

Ý tưởng là so biểu thức với **ít nhất một phần tử của mảng**.

### 8.1. Tìm sản phẩm có nhãn sale

```sql
SELECT product_id, product_name, tags
FROM product_array_lab
WHERE 'sale' = ANY(tags)
ORDER BY product_id;
```

Kết quả:

| product_id | product_name |
|---:|---|
| 101 | Ao xanh |
| 103 | Giay chay |

Không cần biết `sale` đứng ở vị trí thứ mấy trong mảng.

### 8.2. ANY khác truy cập phần tử đầu tiên

```sql
WHERE tags[1] = 'sale'
```

chỉ kiểm tra nhãn **đầu tiên**. Trong dữ liệu mẫu, 101 có `sale` ở vị trí 3 và 103 ở vị trí 3, nên biểu thức đó không tìm được chúng. Còn:

```sql
WHERE 'sale' = ANY(tags)
```

kiểm tra **mọi phần tử** theo ngữ nghĩa membership.

### 8.3. ANY trên mảng NULL, rỗng và chứa NULL

SQL có logic ba giá trị: `TRUE`, `FALSE` và `UNKNOWN/NULL`.

Với mảng:

- `'sale' = ANY('{}'::TEXT[])` là **FALSE**: không có phần tử nào khớp.
- `'sale' = ANY(NULL::TEXT[])` cho **NULL**.
- `'sale' = ANY(ARRAY['sale', NULL]::TEXT[])` là **TRUE**, vì đã có phần tử khớp.
- `'sale' = ANY(ARRAY['blue', NULL]::TEXT[])` có thể là **NULL**: không thấy giá trị khớp nhưng phép so với phần tử NULL là không xác định.

Trong `WHERE`, chỉ những hàng có điều kiện **TRUE** được giữ; `FALSE` và `NULL` đều không đi vào kết quả.

**Không dùng `NOT ('sale' = ANY(tags))` rồi mặc định nó chọn mọi hàng không có sale**, vì các trường hợp mảng hoặc phần tử NULL có thể cho kết quả UNKNOWN.

### 8.4. ALL: điều kiện phải đúng với mọi phần tử

```sql
SELECT
    4 = ALL(ARRAY[4,4]::INTEGER[]) AS all_fours,
    4 = ALL(ARRAY[4,5]::INTEGER[]) AS one_differs,
    4 = ALL('{}'::INTEGER[]) AS empty_all;
```

Về logic:

| Biểu thức | Kết quả |
|---|---|
| `4 = ALL(ARRAY[4,4])` | TRUE |
| `4 = ALL(ARRAY[4,5])` | FALSE |
| `4 = ALL('{}'::INTEGER[])` | TRUE theo *vacuous truth* |

Với mảng rỗng, không có phần tử nào phản ví dụ cho điều kiện `ALL`, nên mệnh đề logic được xem là đúng. Trái lại, `ANY` trên mảng rỗng là false.

Nếu phần tử có `NULL`, `ALL` cũng có thể trả UNKNOWN khi không có phần tử nào làm biểu thức sai rõ ràng.

### 8.5. ANY/ALL không tự tương đương EXISTS/NOT EXISTS

`EXISTS (SELECT 1 FROM ... )` kiểm tra **hàng kết quả của một truy vấn con**. `= ANY(tags)` kiểm tra **phần tử của một giá trị mảng**. Có thể chuyển sang `UNNEST` rồi viết `EXISTS`, nhưng cấu trúc và hành vi với `NULL` cần được hiểu rõ.

Ví dụ:

```sql
SELECT p.product_id
FROM product_array_lab AS p
WHERE EXISTS (
    SELECT 1
    FROM unnest(p.tags) AS u(tag)
    WHERE u.tag = 'sale'
)
ORDER BY p.product_id;
```

Trả 101 và 103 trong bộ mẫu. Cách này hữu ích nếu cần điều kiện phức tạp trên từng phần tử, nhưng không mặc định nhanh hơn toán tử mảng có thể dùng chỉ mục.

## 9. Toán tử chứa, tập con và giao nhau của mảng PostgreSQL

PostgreSQL có các toán tử thường dùng với mảng:

| Toán tử | Ý nghĩa khái quát |
|---|---|
| `a @> b` | Mảng `a` **chứa** các phần tử của `b` |
| `a <@ b` | Các phần tử của `a` được **chứa trong** `b` |
| `a && b` | Hai mảng có **ít nhất một phần tử chung** |
| `a = b` | So sánh hai giá trị mảng theo quy tắc kiểu/chiều/thứ tự của PostgreSQL |

### 9.1. Chứa một nhãn

```sql
SELECT product_id, product_name
FROM product_array_lab
WHERE tags @> ARRAY['sale']::TEXT[]
ORDER BY product_id;
```

Kết quả: **101 và 103**.

### 9.2. Chứa đồng thời hai nhãn

```sql
SELECT product_id
FROM product_array_lab
WHERE tags @> ARRAY['clothing', 'blue']::TEXT[]
ORDER BY product_id;
```

Kết quả: **101**. Sản phẩm 105 có blue nhưng không có clothing.

### 9.3. Có ít nhất một nhãn trong hai nhãn

```sql
SELECT product_id
FROM product_array_lab
WHERE tags && ARRAY['blue', 'sport']::TEXT[]
ORDER BY product_id;
```

Kết quả: **101, 103, 105, 107**.

`&&` thể hiện **giao nhau không rỗng** giữa hai tập phần tử theo ngữ nghĩa toán tử; không cần cả hai nhãn phải cùng tồn tại.

### 9.4. Toán tử @> không đếm số lần xuất hiện

Sản phẩm 107 có:

```text
{clothing,sport,sport}
```

Một điểm dễ nhầm:

```sql
SELECT
    ARRAY['sport']::TEXT[]
        @> ARRAY['sport','sport']::TEXT[] AS contains_duplicates;
```

Trong PostgreSQL, toán tử **containment** không xem số lần xuất hiện của phần tử như phép so multiset; các phần tử lặp **không được xử lý như số lượng bắt buộc** trong kiểu điều kiện này. Nó không phù hợp để hỏi “mảng có ít nhất **hai lần** sport hay không”.

Muốn đếm số lần xuất hiện, bung mảng:

```sql
SELECT p.product_id, COUNT(*) AS sport_count
FROM product_array_lab AS p
CROSS JOIN LATERAL unnest(p.tags) AS u(tag)
WHERE u.tag = 'sport'
GROUP BY p.product_id
HAVING COUNT(*) >= 2;
```

Kết quả: **107** với `sport_count = 2`.

### 9.5. Chọn toán tử theo yêu cầu nghiệp vụ

| Câu hỏi | Biểu thức thường hợp |
|---|---|
| Có nhãn `sale` không? | `'sale' = ANY(tags)` hoặc `tags @> ARRAY['sale']` |
| Có cả `sale` và `blue` không? | `tags @> ARRAY['sale','blue']` |
| Có `blue` hoặc `sport` không? | `tags && ARRAY['blue','sport']` |
| Có ít nhất hai phần tử `sport` không? | `UNNEST` + `COUNT(*)`/`HAVING` |
| Thứ tự nhãn có đúng bằng một mảng mẫu? | So sánh mảng bằng `=` với quy tắc kiểu/chiều phù hợp |

## 10. UNNEST: chuyển một mảng thành nhiều hàng

### 10.1. Một mảng, ba hàng

```sql
SELECT tag
FROM unnest(
    ARRAY['clothing', 'blue', 'sale']::TEXT[]
) AS x(tag);
```

Kết quả theo ví dụ:

| tag |
|---|
| clothing |
| blue |
| sale |

Một mảng có ba phần tử trở thành một quan hệ gồm **ba hàng**. Lúc này có thể dùng các phép SQL thông thường: `WHERE`, `JOIN`, `GROUP BY`, `COUNT`, `DISTINCT`, `ORDER BY`.

### 10.2. UNNEST không tự bảo đảm thứ tự hiển thị cuối

Mảng có thứ tự phần tử. Hàm `unnest` trên PostgreSQL phát ra các phần tử theo thứ tự lưu trữ của mảng; tuy nhiên, **kết quả SQL không có `ORDER BY` cuối không nên được sử dụng như một bảo đảm thứ tự đầu ra** khi kết hợp với join, group, các phép biến đổi hoặc optimizer.

Muốn giữ thứ tự vị trí một cách tường minh, dùng **`WITH ORDINALITY`** rồi `ORDER BY` theo cột vị trí. Phần 11 minh họa.

### 10.3. UNNEST mảng rỗng

```sql
SELECT tag
FROM unnest('{}'::TEXT[]) AS x(tag);
```

Trả **0 hàng**.

### 10.4. UNNEST mảng NULL

```sql
SELECT tag
FROM unnest(NULL::TEXT[]) AS x(tag);
```

Cũng trả **0 hàng** trong ngữ cảnh này. Tuy nhiên, từ 0 hàng của `UNNEST` không thể suy ra dữ liệu gốc là mảng rỗng hay bản thân mảng `NULL`.

### 10.5. UNNEST mảng chứa phần tử NULL

```sql
SELECT score
FROM unnest(ARRAY[NULL, 5]::INTEGER[]) AS x(score);
```

Trả **hai hàng**, trong đó hàng đầu có `score = NULL`, hàng sau có `score = 5`.

**Phân biệt:**

- `UNNEST(NULL::INTEGER[])`: **0 hàng**.
- `UNNEST('{}'::INTEGER[])`: **0 hàng**.
- `UNNEST(ARRAY[NULL]::INTEGER[])`: **1 hàng chứa NULL**.

Nếu dùng `COUNT(*)` sau khi bung mảng, hàng chứa `NULL` vẫn được đếm. `COUNT(score)` chỉ đếm giá trị `score` không NULL.

## 11. WITH ORDINALITY: giữ vị trí phần tử khi chuyển thành hàng

### 11.1. Thêm cột vị trí

```sql
SELECT
    u.tag,
    u.position
FROM unnest(
    ARRAY['clothing','blue','sale']::TEXT[]
) WITH ORDINALITY AS u(tag, position)
ORDER BY u.position;
```

Kết quả:

| tag | position |
|---|---:|
| clothing | 1 |
| blue | 2 |
| sale | 3 |

`WITH ORDINALITY` thêm bộ đếm vị trí **1, 2, 3, ...** theo từng lần khai triển của hàm trong PostgreSQL.

### 11.2. Ordinality không luôn là subscript thực tế

Với mảng thông thường có chỉ số `1..N`, `position` thường trùng các chỉ số đó. Nhưng PostgreSQL cho phép **cận dưới khác 1**, như ví dụ `array_fill` ở mục 4.

`WITH ORDINALITY` đếm **thứ tự phần tử được đưa ra**, bắt đầu tại 1. Nó không tự cam kết cột position bằng subscript gốc của một mảng bắt đầu ở `-2` hay `0`.

Nếu cần subscript thật cho mảng một chiều, dùng `generate_subscripts` theo phần 13.

### 11.3. Khi nào cần WITH ORDINALITY?

- Hiển thị nhãn theo thứ tự ban đầu.
- Giữ mối quan hệ giữa phần tử và vị trí.
- Ghép với một bảng khác có vị trí tương ứng.
- Tính những thống kê phụ thuộc thứ tự, ví dụ phần tử đứng trước/sau.
- Gom dữ liệu lại bằng `array_agg(... ORDER BY position)`.

**Không dùng `ROW_NUMBER() OVER ()` không có thứ tự được xác định để giả lập vị trí gốc.** Khi thứ tự quan trọng, phải lấy vị trí do nguồn cung cấp.

## 12. UNNEST cột mảng của nhiều hàng: CROSS JOIN LATERAL

Trên bảng `product_array_lab`, mỗi hàng sản phẩm có một mảng riêng. Ta muốn một hàng kết quả cho **mỗi nhãn của mỗi sản phẩm**.

### 12.1. CROSS JOIN LATERAL

```sql
SELECT
    p.product_id,
    p.product_name,
    u.tag,
    u.position
FROM product_array_lab AS p
CROSS JOIN LATERAL
    unnest(p.tags) WITH ORDINALITY AS u(tag, position)
ORDER BY p.product_id, u.position;
```

`LATERAL` cho phép hàm ở bên phải tham chiếu `p.tags` của **hàng phía trái**. Với mỗi sản phẩm, PostgreSQL khai triển mảng `tags` tương ứng.

Ví dụ một phần kết quả:

| product_id | product_name | tag | position |
|---:|---|---|---:|
| 101 | Ao xanh | clothing | 1 |
| 101 | Ao xanh | blue | 2 |
| 101 | Ao xanh | sale | 3 |
| 102 | Ao trang | clothing | 1 |
| 102 | Ao trang | white | 2 |
| 103 | Giay chay | shoes | 1 |
| 103 | Giay chay | sport | 2 |
| 103 | Giay chay | sale | 3 |
| 105 | Tui xanh | bag | 1 |
| 105 | Tui xanh | blue | 2 |
| 107 | Ao the thao | clothing | 1 |
| 107 | Ao the thao | sport | 2 |
| 107 | Ao the thao | sport | 3 |
| 108 | Ao cam | clothing | 1 |
| 108 | Ao cam | orange | 2 |

Tổng cộng **15 hàng kết quả**. Không có sản phẩm 104 và 106:

- 104 có mảng rỗng nên `unnest` trả 0 hàng.
- 106 có mảng `NULL` nên `unnest` cũng trả 0 hàng.
- `CROSS JOIN` với 0 hàng phía phải làm hàng sản phẩm đó **không xuất hiện** trong kết quả cuối.

### 12.2. LATERAL là quan hệ phụ thuộc theo từng hàng

Nếu viết:

```sql
FROM product_array_lab AS p
CROSS JOIN LATERAL unnest(p.tags) AS u(tag)
```

về mặt tư duy:

```text
product 101 -> unnest(tags101) -> 3 hàng
product 102 -> unnest(tags102) -> 2 hàng
product 103 -> unnest(tags103) -> 3 hàng
product 104 -> unnest({})      -> 0 hàng
product 105 -> unnest(tags105) -> 2 hàng
product 106 -> unnest(NULL)    -> 0 hàng
product 107 -> unnest(tags107) -> 3 hàng
product 108 -> unnest(tags108) -> 2 hàng
```

Sau đó các phần kết quả được kết hợp thành tập kết quả SQL.

Trong PostgreSQL, một **table function** ở `FROM` có thể tham chiếu cột của bảng trước nó ở những ngữ cảnh mà từ khóa `LATERAL` có thể được bỏ qua. Tuy nhiên, viết `CROSS JOIN LATERAL` tường minh giúp người học nhìn rõ mối phụ thuộc và phân biệt với việc bung một mảng hằng.

### 12.3. Khi nào dùng CROSS JOIN LATERAL?

Khi mục tiêu là **chỉ lấy những phần tử thực sự tồn tại**, chẳng hạn:

- Đếm tổng số nhãn thực tế.
- Lọc sản phẩm có nhãn cụ thể.
- Phân tích tần suất xuất hiện của từng nhãn.
- Chuyển mảng thành bảng con để kết hợp với danh mục nhãn.

Nếu cần **giữ mọi sản phẩm dù không có nhãn**, phải dùng loại join khác.

## 13. LEFT JOIN LATERAL: giữ sản phẩm có mảng rỗng hoặc NULL

### 13.1. Giữ toàn bộ tám sản phẩm

```sql
SELECT
    p.product_id,
    p.product_name,
    u.tag,
    u.position
FROM product_array_lab AS p
LEFT JOIN LATERAL
    unnest(p.tags) WITH ORDINALITY AS u(tag, position)
    ON TRUE
ORDER BY p.product_id, u.position;
```

Khi một sản phẩm không tạo được phần tử từ `unnest`, `LEFT JOIN` vẫn giữ **một hàng phía trái** với các cột `u.tag` và `u.position` là `NULL`.

Số hàng kết quả:

```text
15 hàng nhãn thật
+ 1 hàng placeholder cho product 104 (mảng rỗng)
+ 1 hàng placeholder cho product 106 (mảng NULL)
= 17 hàng kết quả
```

Trích đoạn:

| product_id | tag | position |
|---:|---|---:|
| 103 | shoes | 1 |
| 103 | sport | 2 |
| 103 | sale | 3 |
| 104 | `NULL` | `NULL` |
| 105 | bag | 1 |
| 105 | blue | 2 |
| 106 | `NULL` | `NULL` |
| 107 | clothing | 1 |
| 107 | sport | 2 |
| 107 | sport | 3 |

### 13.2. COUNT(*) khác COUNT(u.tag)

```sql
SELECT
    COUNT(*) AS joined_rows,
    COUNT(u.tag) AS non_null_tags,
    COUNT(u.position) AS actual_array_positions,
    COUNT(DISTINCT p.product_id) AS distinct_products
FROM product_array_lab AS p
LEFT JOIN LATERAL
    unnest(p.tags) WITH ORDINALITY AS u(tag, position)
    ON TRUE;
```

Với dữ liệu mẫu:

| joined_rows | non_null_tags | actual_array_positions | distinct_products |
|---:|---:|---:|---:|
| 17 | 15 | 15 | 8 |

Giải thích:

- `COUNT(*)` đếm **cả hàng placeholder** của outer join, nên là 17.
- `COUNT(u.tag)` chỉ đếm nhãn không NULL, nên là 15.
- `COUNT(u.position)` đếm những hàng **thực sự có phần tử được bung** vì ordinality không NULL với phần tử hợp lệ, kể cả phần tử có **giá trị `NULL`**.
- `COUNT(DISTINCT p.product_id)` cho 8 sản phẩm.

**Nếu mảng có phần tử NULL**, `COUNT(u.tag)` có thể **ít hơn** số phần tử thật. Khi cần đếm các vị trí mảng kể cả vị trí chứa NULL, `COUNT(u.position)` thường phù hợp hơn trong mẫu `WITH ORDINALITY`.

### 13.3. Phân biệt placeholder và phần tử NULL thật

Hai tình huống có thể hiển thị cùng một giá trị `u.tag = NULL`:

1. Sản phẩm có **mảng rỗng/NULL**, outer join thêm hàng placeholder.
2. Mảng có **một phần tử thật mang giá trị NULL**.

Sự khác biệt thể hiện qua `u.position`:

- Placeholder: `u.position IS NULL`.
- Phần tử thật là NULL: `u.position IS NOT NULL`, còn `u.tag IS NULL`.

Đây là lý do `WITH ORDINALITY` hữu ích hơn chỉ để khôi phục thứ tự: nó còn giúp phân biệt **hàng do outer join tạo** với **hàng sinh từ phần tử mảng**.

### 13.4. WHERE sau LEFT JOIN có thể làm mất hàng đã giữ

Ví dụ:

```sql
SELECT p.product_id, u.tag
FROM product_array_lab AS p
LEFT JOIN LATERAL unnest(p.tags) AS u(tag) ON TRUE
WHERE u.tag = 'sale';
```

Điều kiện `WHERE u.tag = 'sale'` loại cả các hàng `u.tag IS NULL`, nên kết quả chỉ có 101 và 103. **LEFT JOIN không bảo đảm giữ mọi sản phẩm sau khi `WHERE` đã lọc trên cột bên phải**.

Nếu muốn giữ sản phẩm và chỉ gắn các nhãn `sale` khi có:

```sql
SELECT p.product_id, u.tag
FROM product_array_lab AS p
LEFT JOIN LATERAL unnest(p.tags) AS u(tag)
    ON u.tag = 'sale'
ORDER BY p.product_id;
```

thì vẫn giữ mỗi sản phẩm không có sale bằng một hàng `u.tag = NULL`. Đặt điều kiện ở `ON` và `WHERE` **không cùng ngữ nghĩa** khi dùng outer join.

## 14. Chỉ số thật bằng generate_subscripts

Khi mảng có lower bound tùy chỉnh, `WITH ORDINALITY` đếm vị trí xuất ra, không nhất thiết là subscript nguồn.

PostgreSQL có:

```sql
generate_subscripts(array_expression, dimension)
```

### 14.1. Liệt kê các chỉ số của một mảng một chiều

```sql
SELECT
    s.i AS actual_subscript,
    p.tags[s.i] AS tag
FROM product_array_lab AS p
CROSS JOIN LATERAL
    generate_subscripts(p.tags, 1) AS s(i)
WHERE p.product_id = 101
ORDER BY s.i;
```

Kết quả:

| actual_subscript | tag |
|---:|---|
| 1 | clothing |
| 2 | blue |
| 3 | sale |

Đối với mảng thông thường, kết quả trùng ordinality 1,2,3.

### 14.2. Mảng có lower bound âm

```sql
WITH x AS (
    SELECT array_fill(
        7,
        ARRAY[4],
        ARRAY[-2]
    ) AS a
)
SELECT
    s.i,
    x.a[s.i] AS value
FROM x
CROSS JOIN LATERAL
    generate_subscripts(x.a, 1) AS s(i)
ORDER BY s.i;
```

Kết quả chỉ số:

```text
-2, -1, 0, 1
```

Nếu dùng `unnest(a) WITH ORDINALITY` cho cùng mảng, cột ordinality sẽ là:

```text
1, 2, 3, 4
```

**Hai chuỗi mô tả hai ý khác nhau:** subscript thật và thứ tự duyệt phần tử.

### 14.3. Ma trận nhiều chiều

```sql
WITH x AS (
    SELECT ARRAY[
        [10, 20],
        [30, 40]
    ]::INTEGER[] AS matrix
)
SELECT
    matrix[1][1] AS row1_col1,
    matrix[1][2] AS row1_col2,
    matrix[2][1] AS row2_col1,
    matrix[2][2] AS row2_col2,
    cardinality(matrix) AS total_elements,
    array_ndims(matrix) AS number_of_dimensions
FROM x;
```

Kết quả:

```text
row1_col1 = 10
row1_col2 = 20
row2_col1 = 30
row2_col2 = 40
total_elements = 4
number_of_dimensions = 2
```

`cardinality` đếm **tổng số phần tử của mọi chiều**, không chỉ số hàng của ma trận.

### 14.4. UNNEST mảng hai chiều làm phẳng

```sql
SELECT element
FROM unnest(
    ARRAY[[10,20],[30,40]]::INTEGER[]
) AS u(element);
```

Phần tử được đọc theo thứ tự lưu trữ của mảng nhiều chiều PostgreSQL, về ví dụ sẽ gồm `10,20,30,40`. Tuy nhiên, `unnest` đã **làm phẳng** kết quả: nó không tự trả hai cột `row_index` và `column_index`.

Nếu cần giữ tọa độ:

```sql
WITH x AS (
    SELECT ARRAY[[10,20],[30,40]]::INTEGER[] AS a
)
SELECT
    r.i AS row_index,
    c.j AS column_index,
    x.a[r.i][c.j] AS element
FROM x
CROSS JOIN LATERAL
    generate_subscripts(x.a, 1) AS r(i)
CROSS JOIN LATERAL
    generate_subscripts(x.a, 2) AS c(j)
ORDER BY r.i, c.j;
```

Kết quả:

| row_index | column_index | element |
|---:|---:|---:|
| 1 | 1 | 10 |
| 1 | 2 | 20 |
| 2 | 1 | 30 |
| 2 | 2 | 40 |

Mảng nhiều chiều của PostgreSQL không hoàn toàn giống “danh sách các danh sách có kích thước bất kỳ” trong Python/JSON. Mảng nhiều chiều cần tuân thủ các quy tắc kích thước hình chữ nhật trong những phép dựng/cập nhật phù hợp. Nếu dữ liệu lồng nhau có số phần tử tùy ý mỗi nhánh, JSON hoặc mô hình bảng con có thể phù hợp hơn.

## 15. UNNEST nhiều mảng cùng lúc: ghép theo vị trí và đệm NULL

PostgreSQL hỗ trợ trong `FROM`:

```sql
SELECT
    x.tag,
    x.weight,
    x.position
FROM unnest(
    ARRAY['blue','sale']::TEXT[],
    ARRAY[10]::INTEGER[]
) WITH ORDINALITY AS x(tag, weight, position)
ORDER BY x.position;
```

Kết quả:

| tag | weight | position |
|---|---:|---:|
| blue | 10 | 1 |
| sale | `NULL` | 2 |

Trong dạng `unnest(array1, array2, ...)` **được hỗ trợ ở FROM**, các mảng được khai triển **song song theo vị trí**. Khi có mảng ngắn hơn, các vị trí còn thiếu được **đệm NULL**.

### 15.1. Không nhầm với CROSS JOIN hai UNNEST

Hai cấu trúc khác nhau:

**Ghép phần tử theo vị trí:**

```sql
SELECT *
FROM unnest(
    ARRAY['a','b']::TEXT[],
    ARRAY[10,20]::INTEGER[]
) AS u(letter, number);
```

Kết quả **2 hàng**:

```text
a 10
b 20
```

**Tích Descartes:**

```sql
SELECT a.letter, b.number
FROM unnest(ARRAY['a','b']::TEXT[]) AS a(letter)
CROSS JOIN unnest(ARRAY[10,20]::INTEGER[]) AS b(number);
```

Kết quả **4 hàng**:

```text
a 10
a 20
b 10
b 20
```

Đây là hai nghiệp vụ khác nhau. Khi muốn nối “vị trí thứ i của mảng A với vị trí thứ i của mảng B”, không dùng hai `CROSS JOIN` độc lập.

### 15.2. Trường hợp mảng không cùng chiều dài

Việc tự động đệm `NULL` có thể che lỗi chất lượng dữ liệu nếu quy tắc nói “mỗi nhãn phải có đúng một trọng số”.

Trước khi bung:

```sql
SELECT
    cardinality(ARRAY['blue','sale']::TEXT[]) AS tag_count,
    cardinality(ARRAY[10]::INTEGER[]) AS weight_count;
```

cho `tag_count=2` và `weight_count=1`. Nếu độ dài phải bằng nhau, cần kiểm tra hoặc constraint/validation phù hợp, không chấp nhận tự động đệm NULL như dữ liệu hợp lệ.

## 16. Thống kê sau khi bung mảng

Khi mảng đã trở thành các hàng, các phép tổng hợp SQL hoạt động như với bất kỳ bảng nào.

### 16.1. Đếm tần suất từng nhãn

```sql
SELECT
    u.tag,
    COUNT(*) AS occurrences
FROM product_array_lab AS p
CROSS JOIN LATERAL unnest(p.tags) AS u(tag)
GROUP BY u.tag
ORDER BY occurrences DESC, u.tag;
```

Kết quả:

| tag | occurrences |
|---|---:|
| clothing | 4 |
| sport | 3 |
| blue | 2 |
| sale | 2 |
| bag | 1 |
| orange | 1 |
| shoes | 1 |
| white | 1 |

Tổng occurrences là **15**.

`sport` có **3 lần xuất hiện** vì:

- Sản phẩm 103 có một `sport`.
- Sản phẩm 107 có **hai `sport`**.

### 16.2. Đếm số sản phẩm phân biệt có từng nhãn

Nếu câu hỏi là “có bao nhiêu **sản phẩm** được gắn nhãn sport?”, phải loại ảnh hưởng của nhãn lặp trong một sản phẩm:

```sql
SELECT
    u.tag,
    COUNT(DISTINCT p.product_id) AS product_count
FROM product_array_lab AS p
CROSS JOIN LATERAL unnest(p.tags) AS u(tag)
GROUP BY u.tag
ORDER BY product_count DESC, u.tag;
```

Đối với `sport`, kết quả **2 sản phẩm**: 103 và 107, không phải 3.

**Đây là khác biệt giữa đếm phần tử và đếm đối tượng có phần tử**. Khi dữ liệu cho phép trùng nhãn, không chọn `COUNT(*)` chỉ vì nhìn kết quả đơn giản.

### 16.3. Đếm số nhãn mỗi sản phẩm

Nếu chỉ cần tổng phần tử:

```sql
SELECT
    product_id,
    cardinality(tags) AS tag_count
FROM product_array_lab
ORDER BY product_id;
```

Kết quả:

| product_id | tag_count |
|---:|---:|
| 101 | 3 |
| 102 | 2 |
| 103 | 3 |
| 104 | 0 |
| 105 | 2 |
| 106 | `NULL` |
| 107 | 3 |
| 108 | 2 |

Không cần `UNNEST` chỉ để lấy chiều dài mảng. Ngược lại, nếu cần **số nhãn khác nhau**, `cardinality` không đủ vì 107 chứa nhãn trùng.

### 16.4. Đếm số nhãn phân biệt

```sql
SELECT
    p.product_id,
    COUNT(DISTINCT u.tag) AS distinct_tag_count
FROM product_array_lab AS p
LEFT JOIN LATERAL unnest(p.tags) AS u(tag) ON TRUE
GROUP BY p.product_id
ORDER BY p.product_id;
```

Kết quả:

| product_id | distinct_tag_count |
|---:|---:|
| 101 | 3 |
| 102 | 2 |
| 103 | 3 |
| 104 | 0 |
| 105 | 2 |
| 106 | 0 |
| 107 | **2** |
| 108 | 2 |

Với `LEFT JOIN`, `COUNT(DISTINCT u.tag)` bỏ qua `NULL` của placeholder nên 104/106 đều là 0. Nhưng nếu cần giữ sự phân biệt “chưa biết mảng” (106) với “mảng rỗng” (104), vẫn phải lấy thêm `p.tags IS NULL` hoặc kiểm tra trực tiếp nguồn.

## 17. Chuyển các phần tử thành mảng trở lại bằng ARRAY_AGG

Phép ngược về mặt ý tưởng của `UNNEST` là **tổng hợp nhiều hàng thành mảng**.

### 17.1. ARRAY_AGG cơ bản

```sql
SELECT array_agg(product_id ORDER BY product_id) AS tenant_1_ids
FROM product_array_lab
WHERE tenant_id = 1;
```

Kết quả:

```text
{101,102,103,104}
```

`ORDER BY` **bên trong `array_agg`** quyết định thứ tự phần tử kết quả. Không dựa vào thứ tự tình cờ của các hàng đầu vào.

### 17.2. Dựng lại một mảng sau UNNEST

```sql
SELECT
    p.product_id,
    array_agg(u.tag ORDER BY u.position) AS rebuilt_tags
FROM product_array_lab AS p
CROSS JOIN LATERAL
    unnest(p.tags) WITH ORDINALITY AS u(tag, position)
WHERE p.product_id = 107
GROUP BY p.product_id;
```

Kết quả:

```text
product_id = 107
rebuilt_tags = {clothing,sport,sport}
```

Vì có `ORDER BY u.position`, nhãn lặp `sport` vẫn được giữ đúng thứ tự. Không tự dùng `DISTINCT` nếu yêu cầu khôi phục nguyên bản nội dung có phần tử lặp.

### 17.3. ARRAY_AGG trên tập không có hàng

```sql
SELECT array_agg(p.product_id ORDER BY p.product_id)
FROM product_array_lab AS p
WHERE p.tenant_id = 999;
```

Trong PostgreSQL, `array_agg` trên **tập không có hàng đầu vào** thường trả `NULL`, **không phải tự động trả `{}`**.

Nếu quy tắc muốn mảng rỗng:

```sql
SELECT COALESCE(
    array_agg(p.product_id ORDER BY p.product_id),
    '{}'::INTEGER[]
) AS product_ids
FROM product_array_lab AS p
WHERE p.tenant_id = 999;
```

Kết quả là mảng rỗng số nguyên.

### 17.4. Bẫy ARRAY_AGG với LEFT JOIN

```sql
SELECT
    p.product_id,
    array_agg(u.tag ORDER BY u.position) AS tags_rebuilt
FROM product_array_lab AS p
LEFT JOIN LATERAL
    unnest(p.tags) WITH ORDINALITY AS u(tag, position)
    ON TRUE
GROUP BY p.product_id
ORDER BY p.product_id;
```

Với sản phẩm 104/106, outer join **tạo một hàng placeholder có `u.tag = NULL`**. Khi đó `array_agg` có thể tạo **mảng một phần tử NULL**, không phải mảng rỗng.

Để loại placeholder:

```sql
SELECT
    p.product_id,
    COALESCE(
        array_agg(u.tag ORDER BY u.position)
            FILTER (WHERE u.position IS NOT NULL),
        '{}'::TEXT[]
    ) AS tags_rebuilt
FROM product_array_lab AS p
LEFT JOIN LATERAL
    unnest(p.tags) WITH ORDINALITY AS u(tag, position)
    ON TRUE
GROUP BY p.product_id
ORDER BY p.product_id;
```

Mẫu này giữ được những **phần tử NULL thật sự** của một mảng vì ordinality của phần tử đó không NULL, đồng thời bỏ hàng placeholder.

**Nhưng** với 106 có `tags IS NULL`, biểu thức `COALESCE` biến thành `{}`. Nếu nghiệp vụ cần **phân biệt NULL và rỗng**, không được chuẩn hóa cả hai thành mảng rỗng; hãy giữ thông tin `p.tags IS NULL` và trả lại `NULL` riêng khi cần.

### 17.5. ARRAY_AGG DISTINCT có thể làm mất thông tin

```sql
SELECT
    array_agg(DISTINCT u.tag ORDER BY u.tag) AS unique_tags
FROM product_array_lab AS p
CROSS JOIN LATERAL unnest(p.tags) AS u(tag)
WHERE p.product_id = 107;
```

Kết quả:

```text
{clothing,sport}
```

Nó **không giống** mảng gốc `{clothing,sport,sport}` vì đã loại phần tử lặp. Dùng `DISTINCT` khi muốn một **tập giá trị phân biệt**, không dùng khi cần tái lập chuỗi thứ tự có thể chứa trùng lặp.

## 18. Mảng điểm số: một ví dụ về NULL trong phép tổng hợp

Mảng `scores` của product 105 là `{NULL,5}`.

### 18.1. Bung scores với vị trí

```sql
SELECT
    p.product_id,
    s.score,
    s.position
FROM product_array_lab AS p
CROSS JOIN LATERAL
    unnest(p.scores) WITH ORDINALITY AS s(score, position)
WHERE p.product_id = 105
ORDER BY s.position;
```

Kết quả:

| product_id | score | position |
|---:|---:|---:|
| 105 | `NULL` | 1 |
| 105 | 5 | 2 |

### 18.2. COUNT(*) khác COUNT(score)

```sql
SELECT
    p.product_id,
    COUNT(*) AS positions_count,
    COUNT(s.score) AS non_null_score_count,
    AVG(s.score) AS avg_score
FROM product_array_lab AS p
CROSS JOIN LATERAL unnest(p.scores) AS s(score)
WHERE p.product_id = 105
GROUP BY p.product_id;
```

Kết quả:

```text
positions_count      = 2
non_null_score_count = 1
avg_score            = 5
```

`AVG` bỏ qua các giá trị `NULL`. Nó không chia tổng 5 cho hai vị trí để ra 2.5; chỉ một điểm không NULL nên trung bình bằng 5.

### 18.3. Trung bình điểm cho mọi sản phẩm

```sql
SELECT
    p.product_id,
    COUNT(s.position) AS score_positions,
    COUNT(s.score) AS known_scores,
    AVG(s.score) AS avg_score
FROM product_array_lab AS p
LEFT JOIN LATERAL
    unnest(p.scores) WITH ORDINALITY AS s(score, position)
    ON TRUE
GROUP BY p.product_id
ORDER BY p.product_id;
```

Đối với 104 (mảng rỗng) và 106 (mảng NULL), `score_positions = 0`, `known_scores = 0` và `avg_score = NULL`. Như đã giải thích, cần kiểm tra cột mảng gốc nếu muốn phân biệt hai trường hợp.

Với 105, hai vị trí nhưng chỉ một điểm được biết; đây là một lý do nên báo cả **số vị trí** và **số giá trị hợp lệ**, không chỉ hiển thị một điểm trung bình.

## 19. Cập nhật mảng trong SQL

Mảng có thể được cập nhật cùng hàng chứa nó. Khi thực hành, dùng transaction và `ROLLBACK` để giữ dữ liệu mẫu ban đầu.

### 19.1. Thêm một nhãn vào cuối

```sql
BEGIN;

UPDATE product_array_lab
SET tags = array_append(tags, 'new')
WHERE product_id = 101
RETURNING product_id, tags;

ROLLBACK;
```

Trong transaction, tags của 101 thành:

```text
{clothing,blue,sale,new}
```

Sau `ROLLBACK`, trở lại ba nhãn ban đầu.

### 19.2. Không tự thêm vào mảng NULL

Với product 106, `tags` là `NULL`. Đừng giả định mọi hàm thao tác mảng có cùng hành vi khi đối số là mảng NULL. Nếu nghiệp vụ coi mảng thiếu là mảng rỗng trước khi thêm:

```sql
BEGIN;

UPDATE product_array_lab
SET tags = array_append(
    COALESCE(tags, '{}'::TEXT[]),
    'new'
)
WHERE product_id = 106
RETURNING product_id, tags;

ROLLBACK;
```

`COALESCE` ở đây là **quyết định nghiệp vụ**: chuyển `NULL` thành `{}` để thêm phần tử, không phải tự động bảo toàn sự khác nhau giữa dữ liệu chưa biết và rỗng.

### 19.3. Xóa tất cả nhãn trùng

```sql
BEGIN;

UPDATE product_array_lab
SET tags = array_remove(tags, 'sport')
WHERE product_id = 107
RETURNING product_id, tags;

ROLLBACK;
```

Kết quả tạm thời là `{clothing}`, vì cả hai `sport` đều bị loại.

### 19.4. Thay một phần tử theo chỉ số

PostgreSQL hỗ trợ gán vào subscript mảng trong `UPDATE`:

```sql
BEGIN;

UPDATE product_array_lab
SET tags[2] = 'navy'
WHERE product_id = 101
RETURNING product_id, tags;

ROLLBACK;
```

Trong transaction, mảng thành `{clothing,navy,sale}`. Khi cập nhật chỉ số vượt phạm vi hoặc mảng nhiều chiều, PostgreSQL có quy tắc mở rộng/giới hạn riêng; không nên gán bừa chỉ số rất lớn vì có thể làm cấu trúc dữ liệu bất ngờ hoặc lỗi.

### 19.5. Tránh race condition đọc–sửa–ghi mảng từ ứng dụng

Một mẫu ứng dụng:

```text
SELECT tags FROM products WHERE product_id=101
-> thêm 'new' trong Java/Python
-> UPDATE products SET tags=<mảng mới>
```

có thể bị **lost update** nếu hai phiên cùng đọc mảng cũ, sửa riêng rồi ghi đè toàn bộ giá trị. Khi phù hợp, dùng cập nhật biểu thức ở database như `SET tags = array_append(tags,'new')` trong transaction, hoặc dùng locking/optimistic version để bảo vệ thay đổi.

Nếu nghiệp vụ cấm nhãn trùng, phải có cơ chế kiểm tra và thiết kế ràng buộc phù hợp; `array_append` **không tự đảm bảo uniqueness** của phần tử mảng.

## 20. Thiết kế dữ liệu: khi nào dùng mảng, khi nào dùng bảng con?

Giả sử nhãn sản phẩm ngày càng phức tạp:

- Mỗi nhãn có mã định danh, tên, loại, màu hiển thị.
- Muốn áp ràng buộc rằng nhãn phải tồn tại trong bảng danh mục.
- Cần biết ai gắn nhãn và thời điểm nào.
- Muốn phân quyền theo nhãn.
- Cần báo cáo tỷ lệ sử dụng nhãn trên hàng chục triệu sản phẩm.

Một cột `tags TEXT[]` có thể trở nên khó quản lý. Khi đó có thể chuẩn hóa:

```sql
CREATE TABLE product_tags_lab (
    product_id INTEGER NOT NULL
        REFERENCES product_array_lab(product_id),
    position INTEGER NOT NULL CHECK (position >= 1),
    tag TEXT NOT NULL,
    PRIMARY KEY (product_id, position)
);
```

### 20.1. Chuyển mảng hiện tại thành hàng bảng con

```sql
INSERT INTO product_tags_lab (product_id, position, tag)
SELECT
    p.product_id,
    u.position::INTEGER,
    u.tag
FROM product_array_lab AS p
CROSS JOIN LATERAL
    unnest(p.tags) WITH ORDINALITY AS u(tag, position);
```

Trên dữ liệu mẫu, câu lệnh thêm **15 hàng** vào bảng `product_tags_lab`.

Các trường:

- `product_id` giữ liên kết tới sản phẩm.
- `position` giữ thứ tự phần tử ban đầu.
- `tag` giữ giá trị nhãn.

Tập mẫu không có nhãn `NULL`, nên ràng buộc `tag NOT NULL` không gây lỗi. Nếu dữ liệu thật chứa phần tử `NULL`, phải quyết định lọc, chuyển đổi hay cho phép null trước khi đưa vào bảng con.

### 20.2. Muốn cấm nhãn trùng trong cùng sản phẩm

Nếu quy tắc nghiệp vụ nói một nhãn chỉ được gắn một lần cho mỗi sản phẩm, có thể cân nhắc:

```sql
ALTER TABLE product_tags_lab
ADD CONSTRAINT uq_product_tag_lab
UNIQUE (product_id, tag);
```

**Nhưng lệnh này sẽ thất bại trên dữ liệu mẫu đã chuyển**, vì product 107 có hai hàng `(107, 'sport')`. Cần quyết định:

- Trùng là dữ liệu sai cần dọn.
- Trùng có ý nghĩa nghiệp vụ (ví dụ occurrence/weight) và cần được giữ.
- Thứ tự vị trí quan trọng hơn uniqueness.

Không tự xóa một phần tử lặp khi chưa xác định ý nghĩa.

### 20.3. Bảng con giúp áp dụng ràng buộc quan hệ

Với bảng con, ta có thể tạo:

```sql
CREATE INDEX idx_product_tags_tag_lab
ON product_tags_lab (tag, product_id);
```

và dùng SQL thông thường:

```sql
SELECT DISTINCT p.product_id, p.product_name
FROM product_array_lab AS p
JOIN product_tags_lab AS pt
    ON pt.product_id = p.product_id
WHERE pt.tag = 'sale'
ORDER BY p.product_id;
```

Kết quả vẫn là 101 và 103. Với dữ liệu lớn, bảng con có thể được tối ưu tốt cho một số quan hệ/truy vấn, đồng thời cho phép khóa ngoại tới bảng danh mục nhãn.

### 20.4. Mảng vẫn hữu ích trong nhiều tình huống

Mảng là lựa chọn hợp lý khi:

- Danh sách ngắn và có giới hạn hợp lý.
- Phần tử thường được đọc/ghi cùng hàng cha.
- Cần giữ thứ tự phần tử.
- Không cần khóa ngoại hay thuộc tính phức tạp cho từng phần tử.
- DBMS hỗ trợ truy vấn/indexing mảng phù hợp workload.

Quyết định là một **trade-off về mô hình, truy vấn và chi phí bảo trì**, không phải kết luận “mảng luôn sai chuẩn hóa”.

## 21. Chỉ mục GIN và hiệu năng truy vấn mảng PostgreSQL

Với bảng lớn, quét mọi mảng để kiểm tra một nhãn có thể tốn chi phí. PostgreSQL hỗ trợ chỉ mục **GIN** cho nhiều toán tử mảng.

### 21.1. Tạo GIN index

```sql
CREATE INDEX idx_product_array_tags_gin_lab
ON product_array_lab
USING GIN (tags);
```

Trên những workload phù hợp, chỉ mục có thể giúp:

```sql
SELECT product_id
FROM product_array_lab
WHERE tags @> ARRAY['sale']::TEXT[];
```

và:

```sql
SELECT product_id
FROM product_array_lab
WHERE tags && ARRAY['blue','sport']::TEXT[];
```

### 21.2. GIN không phải B-tree sắp xếp theo phần tử

GIN được thiết kế để lập chỉ mục những **giá trị có nhiều thành phần** theo khả năng của operator class, giúp tìm hàng chứa phần tử/tokens phù hợp. Nó **không** tự cung cấp thứ tự sản phẩm theo `product_id` hay thứ tự phần tử trong mảng như B-tree composite key.

Khi truy vấn cần:

```sql
ORDER BY product_id DESC
LIMIT 10
```

bộ tối ưu vẫn phải kết hợp các lựa chọn quét/sắp phù hợp. Không cho rằng một GIN index đủ để tăng tốc mọi `ORDER BY` và `UNNEST`.

### 21.3. ANY không nhất thiết dùng cùng chỉ mục như @>

Hai câu:

```sql
WHERE 'sale' = ANY(tags)
```

và:

```sql
WHERE tags @> ARRAY['sale']::TEXT[]
```

thường có mục tiêu membership tương tự trên dữ liệu nhãn không NULL, nhưng **không bảo đảm cùng kế hoạch thực thi hay cùng khả năng dùng GIN index**. PostgreSQL GIN array operator classes thường hỗ trợ các toán tử như `@>` và `&&` theo quy tắc riêng. Muốn tối ưu, hãy đo truy vấn thực và kiểm tra plan, không chỉ dựa trên tính tương đương trực giác.

### 21.4. EXPLAIN và bảng nhỏ

```sql
EXPLAIN
SELECT product_id
FROM product_array_lab
WHERE tags @> ARRAY['sale']::TEXT[];
```

Với **8 sản phẩm**, PostgreSQL có thể chọn `Seq Scan` dù đã có GIN index, vì đọc tám hàng rất rẻ. Đây không phải bằng chứng GIN index “không hoạt động”.

`EXPLAIN (ANALYZE, BUFFERS)` thực thi câu SELECT để đo thực tế; với DML như `UPDATE`/`DELETE`, việc dùng `ANALYZE` cũng thực thi câu DML, nên cần transaction và môi trường thích hợp.

### 21.5. Chi phí ghi và kích thước dữ liệu

GIN index có chi phí lưu trữ và bảo trì. Nếu thường xuyên thay đổi mảng, database phải cập nhật cấu trúc index theo những phần tử thay đổi; một hàng có mảng dài và nhiều phần tử có thể tốn nhiều công sức hơn một khóa B-tree ngắn.

Với dữ liệu lớn:

- Chỉ tạo index cho truy vấn thường xuyên và có lợi.
- Giới hạn độ dài mảng hợp lý nếu nghiệp vụ cho phép.
- Kiểm tra thống kê, số lượng phần tử, độ chọn lọc và truy vấn thực.
- Cân nhắc bảng con nếu cần thao tác độc lập trên từng phần tử.
- Theo dõi chi phí INSERT/UPDATE/DELETE, không chỉ tốc độ SELECT.

## 22. BigQuery: ARRAY, UNNEST và chỉ số 0/1 theo hàm truy cập

**Google BigQuery (GoogleSQL)** hỗ trợ kiểu `ARRAY<T>` và `UNNEST`, nhưng cách truy cập vị trí **khác PostgreSQL**.

### 22.1. Tạo một array trong BigQuery

```sql
-- BigQuery GoogleSQL
SELECT ['clothing', 'blue', 'sale'] AS tags;
```

Cũng có thể biểu diễn kiểu rõ ràng:

```sql
SELECT ARRAY<STRING>['clothing', 'blue', 'sale'] AS tags;
```

Không dùng ép kiểu `::TEXT[]` của PostgreSQL trong BigQuery.

### 22.2. OFFSET bắt đầu từ 0

```sql
-- BigQuery
WITH x AS (
    SELECT ['clothing','blue','sale'] AS tags
)
SELECT
    tags[OFFSET(0)] AS first_tag,
    tags[OFFSET(1)] AS second_tag,
    tags[OFFSET(2)] AS third_tag
FROM x;
```

Kết quả: `clothing`, `blue`, `sale`.

### 22.3. ORDINAL bắt đầu từ 1

```sql
-- BigQuery
WITH x AS (
    SELECT ['clothing','blue','sale'] AS tags
)
SELECT
    tags[ORDINAL(1)] AS first_tag,
    tags[ORDINAL(2)] AS second_tag
FROM x;
```

BigQuery cho cả hai cách:

- `OFFSET(0)` là phần tử đầu tiên theo **hệ đếm từ 0**.
- `ORDINAL(1)` là phần tử đầu tiên theo **hệ đếm từ 1**.

**Không dùng `tags[1]` của PostgreSQL như bản dịch ngầm sang BigQuery**. Phải chọn đúng `OFFSET` hoặc `ORDINAL`.

### 22.4. SAFE_OFFSET và SAFE_ORDINAL

Trên BigQuery, truy cập ngoài phạm vi bằng dạng không an toàn có thể gây lỗi. Dùng:

```sql
-- BigQuery
WITH x AS (
    SELECT ['clothing','blue','sale'] AS tags
)
SELECT
    tags[SAFE_OFFSET(99)] AS no_such_element,
    tags[SAFE_ORDINAL(99)] AS no_such_ordinal
FROM x;
```

cho các giá trị `NULL` khi vị trí không tồn tại.

Đây là khác biệt quan trọng với thói quen đọc mảng ngoài phạm vi trong PostgreSQL. Không tự cho rằng mọi DBMS đều trả NULL hoặc mọi DBMS đều ném lỗi cho cùng một chỉ số.

### 22.5. UNNEST và WITH OFFSET

```sql
-- BigQuery
WITH products AS (
    SELECT 101 AS product_id,
           ['clothing','blue','sale'] AS tags
)
SELECT
    p.product_id,
    tag,
    pos
FROM products AS p
CROSS JOIN UNNEST(p.tags) AS tag WITH OFFSET AS pos
ORDER BY p.product_id, pos;
```

Kết quả:

| product_id | tag | pos |
|---:|---|---:|
| 101 | clothing | **0** |
| 101 | blue | 1 |
| 101 | sale | 2 |

Khác PostgreSQL `WITH ORDINALITY` bắt đầu từ **1**, BigQuery `WITH OFFSET` trả vị trí **0-based**. Nếu ứng dụng cần vị trí hiển thị từ 1, có thể cộng `pos + 1` theo mục đích.

### 22.6. CROSS JOIN và LEFT JOIN trong BigQuery

BigQuery có thể dùng `CROSS JOIN UNNEST` để bung mảng, và `LEFT JOIN UNNEST` để giữ hàng phía trái khi mảng không có phần tử theo cú pháp GoogleSQL phù hợp.

Ví dụ:

```sql
-- BigQuery
WITH products AS (
    SELECT 101 AS product_id, ['sale','blue'] AS tags
    UNION ALL
    SELECT 104, ARRAY<STRING>[]
    UNION ALL
    SELECT 106, CAST(NULL AS ARRAY<STRING>)
)
SELECT
    p.product_id,
    tag
FROM products AS p
LEFT JOIN UNNEST(p.tags) AS tag
ORDER BY p.product_id, tag;
```

Ý tưởng giống outer expansion: giữ product 104/106 dù không có phần tử, với giá trị bên phải NULL.

### 22.7. BigQuery ARRAY_AGG

```sql
-- BigQuery
SELECT ARRAY_AGG(tag ORDER BY pos) AS tags_rebuilt
FROM (
    SELECT tag, pos
    FROM UNNEST(['sale','blue']) AS tag WITH OFFSET AS pos
);
```

Thu lại mảng theo thứ tự. BigQuery có quy tắc riêng về `NULL` trong array và các tùy chọn như `IGNORE NULLS` trong `ARRAY_AGG`; không port nguyên logic mảng chứa NULL của PostgreSQL mà chưa kiểm tra BigQuery.

## 23. Snowflake: ARRAY_CONSTRUCT và LATERAL FLATTEN

**Snowflake** hỗ trợ dữ liệu bán cấu trúc như `VARIANT`, `ARRAY` và các kiểu mảng có cấu trúc theo khả năng phiên bản. Cách truy cập phần tử và làm phẳng không giống PostgreSQL `TEXT[]`.

### 23.1. Tạo và lấy phần tử

```sql
-- Snowflake
SELECT ARRAY_CONSTRUCT('clothing', 'blue', 'sale') AS tags;
```

Một cách lấy phần tử:

```sql
-- Snowflake
SELECT
    GET(ARRAY_CONSTRUCT('clothing','blue','sale'), 0) AS first_tag,
    GET(ARRAY_CONSTRUCT('clothing','blue','sale'), 2) AS third_tag;
```

Đối với cách truy cập array thông dụng của Snowflake, chỉ số **bắt đầu từ 0**. Các giá trị có thể có kiểu bán cấu trúc nên việc ép kiểu sang `VARCHAR`/`STRING` có thể cần thiết tùy biểu thức và mục đích.

### 23.2. LATERAL FLATTEN

Giả sử bảng Snowflake `product_events` có cột `tags` chứa array:

```sql
-- Snowflake, giả định product_events.tags có dữ liệu ARRAY.
SELECT
    p.product_id,
    f.value::STRING AS tag,
    f.index AS zero_based_index
FROM product_events AS p,
     LATERAL FLATTEN(INPUT => p.tags) AS f
ORDER BY p.product_id, f.index;
```

`FLATTEN` có các cột kết quả như `VALUE` và `INDEX`. `INDEX` cho vị trí phần tử mảng theo ngữ nghĩa Snowflake, thường **0-based**.

**Lưu ý:** `product_events` ở đây là bảng **giả định trên Snowflake**, không phải bảng PostgreSQL `product_array_lab`. Đoạn này minh họa cú pháp phương ngữ và không chạy trực tiếp trên PostgreSQL.

### 23.3. OUTER => TRUE

```sql
-- Snowflake
SELECT
    p.product_id,
    f.value,
    f.index
FROM product_events AS p,
     LATERAL FLATTEN(
         INPUT => p.tags,
         OUTER => TRUE
     ) AS f;
```

`OUTER => TRUE` giúp tạo hàng trong các tình huống expansion không sinh phần tử theo ngữ nghĩa FLATTEN. Tuy nhiên, phân biệt **empty compound**, **NULL**, **missing path** và các biến thể dữ liệu bán cấu trúc cần xem các cột kết quả và quy tắc Snowflake, không chỉ `f.value IS NULL`.

### 23.4. Snowflake không đồng nhất typed arrays PostgreSQL

Phép lọc phần tử, chuyển kiểu, cấu trúc nested arrays và kiểm soát kiểu trong Snowflake có đặc điểm riêng. Không port:

```sql
WHERE tags @> ARRAY['sale']::TEXT[]
```

nguyên văn từ PostgreSQL. Hãy dùng hàm/toán tử hỗ trợ array/VARIANT trong phiên bản Snowflake cụ thể và kiểm tra việc chuyển kiểu, chi phí FLATTEN cùng điều kiện lọc.

## 24. SQL Server: OPENJSON và chỉ số mảng JSON bắt đầu từ 0

SQL Server trong nhiều phiên bản phổ biến thao tác với danh sách qua **JSON lưu trong chuỗi** và các hàm JSON. Đây **không phải cột `TEXT[]` native theo cú pháp PostgreSQL**.

### 24.1. Đọc một phần tử trong JSON array

```sql
-- SQL Server
DECLARE @tags NVARCHAR(MAX) = N'["clothing","blue","sale"]';

SELECT
    JSON_VALUE(@tags, '$[0]') AS first_tag,
    JSON_VALUE(@tags, '$[2]') AS third_tag;
```

Kết quả: `clothing` và `sale`.

Đường dẫn JSON `$[0]` bắt đầu từ **0**.

### 24.2. OPENJSON biến array thành hàng

```sql
-- SQL Server
DECLARE @tags NVARCHAR(MAX) = N'["clothing","blue","sale"]';

SELECT
    j.[key] AS zero_based_index,
    j.[value] AS tag,
    j.[type] AS json_type
FROM OPENJSON(@tags) AS j
ORDER BY TRY_CONVERT(INT, j.[key]);
```

`OPENJSON` mặc định trả các cột logic `key`, `value`, `type`. Với JSON array, `key` thể hiện **vị trí phần tử** dưới dạng ký tự số như '0', '1', '2'. Muốn sắp theo vị trí số, không dựa vào thứ tự từ điển khi có hơn chín phần tử; dùng chuyển kiểu số phù hợp.

**Điều kiện phiên bản:** `OPENJSON` yêu cầu phiên bản SQL Server và mức compatibility level có hỗ trợ tính năng (thường tối thiểu **130**). Với database cũ phải kiểm tra cấu hình trước khi dùng.

### 24.3. CROSS APPLY và OUTER APPLY

Giả sử bảng SQL Server `dbo.products_json` có cột `tags_json` lưu JSON array:

```sql
-- SQL Server: chỉ lấy những phần tử được bung.
SELECT
    p.product_id,
    j.[value] AS tag
FROM dbo.products_json AS p
CROSS APPLY OPENJSON(p.tags_json) AS j;
```

`CROSS APPLY` là một cách cho phép hàm ở bên phải dùng cột của hàng `p`. Nó gần với ý tưởng `CROSS JOIN LATERAL`.

Muốn giữ sản phẩm không có phần tử:

```sql
-- SQL Server
SELECT
    p.product_id,
    j.[value] AS tag
FROM dbo.products_json AS p
OUTER APPLY OPENJSON(p.tags_json) AS j;
```

`OUTER APPLY` mang ý tưởng outer expansion: giữ hàng sản phẩm kể cả khi phần bên phải không có hàng.

### 24.4. Không nhầm JSON NULL và SQL NULL

Một JSON array có phần tử `null` khác một cột SQL chứa `NULL` và khác chuỗi JSON `[]`. Khi bung qua `OPENJSON`, cần xem `type` và dữ liệu gốc để phân biệt trường hợp phù hợp, không chỉ dựa trên một giá trị `[value] IS NULL`.

Trong các phiên bản SQL Server mới, khả năng lưu JSON có thể thay đổi; ví dụ dùng `NVARCHAR(MAX)` vẫn minh họa đúng cách hoạt động của các hàm JSON truyền thống.

## 25. MySQL 8.0+: JSON_ARRAY, JSON_EXTRACT và JSON_TABLE

MySQL không có cú pháp cột `TEXT[]` như PostgreSQL trong thiết kế quan hệ phổ biến. Nhu cầu mảng thường được đáp ứng bằng kiểu **JSON**.

### 25.1. Tạo JSON array

```sql
-- MySQL
SELECT JSON_ARRAY('clothing', 'blue', 'sale') AS tags;
```

### 25.2. Truy cập theo JSON path 0-based

```sql
-- MySQL
SELECT
    JSON_EXTRACT(
        JSON_ARRAY('clothing','blue','sale'),
        '$[0]'
    ) AS first_tag_json,
    JSON_UNQUOTE(
        JSON_EXTRACT(
            JSON_ARRAY('clothing','blue','sale'),
            '$[2]'
        )
    ) AS third_tag_text;
```

`$[0]` là phần tử đầu tiên. `JSON_EXTRACT` trả giá trị JSON theo quy tắc MySQL, còn `JSON_UNQUOTE` giúp lấy nội dung chuỗi không có dấu trích dẫn JSON.

### 25.3. JSON_TABLE chuyển phần tử thành hàng

MySQL 8.0+ hỗ trợ `JSON_TABLE` trong các phiên bản có tính năng này:

```sql
-- MySQL 8.0+
SELECT
    jt.position,
    jt.tag
FROM JSON_TABLE(
    JSON_ARRAY('clothing', 'blue', 'sale'),
    '$[*]'
    COLUMNS (
        position FOR ORDINALITY,
        tag VARCHAR(100) PATH '$'
    )
) AS jt
ORDER BY jt.position;
```

Kết quả:

| position | tag |
|---:|---|
| **1** | clothing |
| 2 | blue |
| 3 | sale |

**Điểm dễ nhầm:** đường dẫn JSON phần tử ở MySQL là `$[0]` cho phần tử đầu, nhưng cột `FOR ORDINALITY` của `JSON_TABLE` đánh số **1,2,3**. Hai kiểu chỉ số cùng xuất hiện trong một DBMS vì phục vụ cơ chế khác nhau.

### 25.4. Bung JSON array của một bảng

Giả sử bảng `products_json` có cột `tags_json JSON`:

```sql
-- MySQL 8.0+
SELECT
    p.product_id,
    jt.position,
    jt.tag
FROM products_json AS p
CROSS JOIN JSON_TABLE(
    p.tags_json,
    '$[*]'
    COLUMNS (
        position FOR ORDINALITY,
        tag VARCHAR(100) PATH '$'
    )
) AS jt
ORDER BY p.product_id, jt.position;
```

`JSON_TABLE` có cơ chế tham chiếu dữ liệu từ hàng phía trái theo khả năng phiên bản MySQL. Với mảng rỗng hoặc JSON null, cần xem cách nó tạo hàng và áp dụng outer join nếu muốn giữ các hàng sản phẩm không có phần tử.

### 25.5. Đừng đánh đồng JSON_TABLE với UNNEST của typed SQL array

`JSON_TABLE` có `COLUMNS` để định nghĩa cách trích dữ liệu và kiểu đầu ra; nó liên quan đến JSON path, JSON null, kiểu ép và xử lý lỗi/thiếu giá trị theo cú pháp MySQL. PostgreSQL `unnest(text[])` thì trả các phần tử typed array.

Cùng mục tiêu “một phần tử thành một hàng”, nhưng cách chuẩn hóa, kiểu dữ liệu và quy tắc xử lý lỗi khác nhau.

## 26. SQLite: json_each và json_extract

SQLite có các hàm JSON (khả năng sẵn có phụ thuộc phiên bản và cách build/extension), nhưng không có cú pháp typed `TEXT[]` như PostgreSQL.

### 26.1. Lấy phần tử đầu tiên

```sql
-- SQLite
SELECT
    json_extract('["clothing","blue","sale"]', '$[0]') AS first_tag,
    json_extract('["clothing","blue","sale"]', '$[2]') AS third_tag;
```

Kết quả: `clothing` và `sale`.

### 26.2. json_each làm phẳng một JSON array

```sql
-- SQLite
SELECT
    CAST(j.key AS INTEGER) AS position_zero_based,
    j.value AS tag,
    j.type AS json_type
FROM json_each('["clothing","blue","sale"]') AS j
ORDER BY CAST(j.key AS INTEGER);
```

Kết quả:

| position_zero_based | tag |
|---:|---|
| 0 | clothing |
| 1 | blue |
| 2 | sale |

`json_each` trả các cột như `key`, `value`, `type`. Với array, `key` biểu thị vị trí 0-based. Với object JSON, `key` có thể là **tên thuộc tính**, nên đừng mặc định mọi `json_each` đều trả khóa số.

### 26.3. Kết hợp với bảng sản phẩm

Giả sử bảng SQLite `products_json` có cột `tags_json` chứa chuỗi JSON hợp lệ:

```sql
-- SQLite: các phần tử được bung.
SELECT p.product_id, j.value AS tag
FROM products_json AS p,
     json_each(p.tags_json) AS j;
```

Khi muốn giữ sản phẩm không có phần tử, có thể dùng outer join theo khả năng truy vấn:

```sql
-- SQLite: giữ hàng sản phẩm phía trái.
SELECT p.product_id, j.value AS tag
FROM products_json AS p
LEFT JOIN json_each(p.tags_json) AS j ON TRUE;
```

Cần phân biệt dữ liệu JSON `[]`, JSON `null` và SQL `NULL` khi báo cáo; việc một lần bung không tạo phần tử không chứng minh chúng có cùng ý nghĩa nguồn.

## 27. Oracle: collection và TABLE(), khác JSON array

Oracle có **collection types** như nested table/varray và các hàm SQL/PLSQL để thao tác danh sách, đồng thời có JSON riêng.

### 27.1. Biến một collection thành hàng

Ví dụ một collection kiểu có sẵn:

```sql
-- Oracle
SELECT x.COLUMN_VALUE AS tag
FROM TABLE(
    SYS.ODCIVARCHAR2LIST('clothing', 'blue', 'sale')
) x;
```

`TABLE(collection_expression)` biến collection thành quan hệ hàng dùng được trong SQL. Cột phần tử đơn thường xuất hiện dưới tên `COLUMN_VALUE` cho collection scalar.

### 27.2. Truy cập phần tử trong PL/SQL

Trong ngữ cảnh Oracle PL/SQL, cú pháp truy cập collection thường dùng **dấu ngoặc tròn**:

```sql
DECLARE
    v_tags SYS.ODCIVARCHAR2LIST :=
        SYS.ODCIVARCHAR2LIST('clothing', 'blue', 'sale');
BEGIN
    DBMS_OUTPUT.PUT_LINE(v_tags(1));
END;
/
```

Ví dụ này in `clothing`. Với collection dense kiểu mẫu, phần tử đầu bắt đầu tại **1**; các loại collection khác có thể có phương thức, cận và đặc tính khác. Không chuyển `tags[1]` PostgreSQL hoặc `tags[OFFSET(0)]` BigQuery nguyên văn sang Oracle PL/SQL.

### 27.3. Nested table, varray và JSON không hoàn toàn giống nhau

Oracle có các kiểu collection khác nhau về kích thước tối đa, tính liên tục/chỉ số và cách lưu. `TABLE(...)` trong SQL cũng không tự cam kết thứ tự trình bày cuối; nếu cần thứ tự, phải chọn cách biểu diễn vị trí và `ORDER BY` phù hợp.

Đối với **JSON arrays**, Oracle có các hàm SQL/JSON như `JSON_TABLE` với cách khai báo path và cột riêng. Không nhầm `TABLE(collection)` của typed Oracle collection với `JSON_TABLE` của JSON document.

## 28. Bảng đối chiếu phương ngữ

| Vấn đề | PostgreSQL typed array | BigQuery ARRAY | Snowflake ARRAY/VARIANT | MySQL JSON | SQL Server JSON | SQLite JSON | Oracle collection |
|---|---|---|---|---|---|---|---|
| Tạo mảng/danh sách | `ARRAY['a','b']::TEXT[]` | `['a','b']` | `ARRAY_CONSTRUCT(...)` | `JSON_ARRAY(...)` | Chuỗi JSON/hàm JSON | Chuỗi JSON/hàm JSON | Constructor collection |
| Truy cập đầu | `a[1]` (mảng thường) | `a[OFFSET(0)]` hoặc `a[ORDINAL(1)]` | `GET(a,0)` | `$[0]` | `$[0]` | `$[0]` | `a(1)` trong PL/SQL phù hợp |
| Bung thành hàng | `unnest(a)` | `UNNEST(a)` | `LATERAL FLATTEN` | `JSON_TABLE` | `OPENJSON` | `json_each` | `TABLE(collection)` |
| Vị trí bung | `WITH ORDINALITY` từ 1 | `WITH OFFSET` từ 0 | `FLATTEN.INDEX` từ 0 | `FOR ORDINALITY` từ 1 | `OPENJSON.[key]` từ 0 | `json_each.key` từ 0 | Cần cách lấy vị trí theo collection/ngữ cảnh |
| Giữ hàng gốc không có phần tử | `LEFT JOIN LATERAL ... ON TRUE` | `LEFT JOIN UNNEST` | `OUTER=>TRUE` theo ngữ nghĩa FLATTEN | Outer join phù hợp | `OUTER APPLY` | `LEFT JOIN json_each` | Outer join/collection logic phù hợp |
| Lọc tồn tại phần tử | `ANY`, `@>`, `&&` | `EXISTS`/`UNNEST` và hàm array | Hàm array/VARIANT tương ứng | JSON search/functions | `OPENJSON`/JSON functions | `json_each`/JSON functions | Collection/JSON phù hợp |
| Đặc biệt cần nhớ | Lower bound có thể khác 1; `NULL` vs `{}` | OFFSET/ORDINAL và SAFE variants | Kiểu VARIANT và OUTER FLATTEN | JSON path 0-based nhưng ordinality 1-based | `OPENJSON` phụ thuộc compatibility level | JSON functions phụ thuộc build/version | Nhiều loại collection với quy tắc riêng |

Bảng mô tả **hướng tiếp cận thường gặp**, không nói các hệ có mọi khả năng tương đương. Khả năng lưu mảng typed, JSON, semi-structured, tạo chỉ mục và quản lý phần tử thay đổi theo DBMS/phiên bản. Chỉ lấy **đúng cú pháp được hệ đang chạy hỗ trợ**.

## 29. Những lỗi thường gặp

### Lỗi 1 — Dùng chỉ số 0 cho mảng PostgreSQL thông thường

`tags[0]` không phải phần tử đầu nếu mảng bắt đầu tại 1. Dùng `tags[1]` hoặc `array_lower(tags,1)` theo cận thực tế.

### Lỗi 2 — Dùng -1 kiểu Python để lấy phần tử cuối

`tags[-1]` không tự có nghĩa “phần tử cuối”. Dùng `tags[array_upper(tags,1)]` trên mảng một chiều phù hợp.

### Lỗi 3 — Nghĩ mọi mảng PostgreSQL đều có lower bound 1

PostgreSQL hỗ trợ mảng có cận khác 1. `WITH ORDINALITY` là bộ đếm vị trí xuất ra, không nhất thiết là subscript nguồn.

### Lỗi 4 — Nhầm mảng rỗng với mảng NULL

`'{}'::TEXT[]` có 0 phần tử; `NULL::TEXT[]` là bản thân giá trị mảng không có. `cardinality` lần lượt trả 0 và NULL.

### Lỗi 5 — Dùng array_length(...,1)=0 để tìm mảng rỗng

`array_length` trên chiều của mảng rỗng có thể trả NULL. Dùng `cardinality(tags)=0` cho mảng rỗng PostgreSQL.

### Lỗi 6 — Coi mảng chứa một phần tử NULL như mảng rỗng

`ARRAY[NULL]::TEXT[]` có **một phần tử** và `UNNEST` trả một hàng chứa NULL. `COUNT(*)` và `COUNT(value)` khác nhau.

### Lỗi 7 — Truy cập ngoài cận rồi kết luận phần tử là NULL thật

Đọc `tags[99]` cho NULL không chứng minh vị trí 99 tồn tại. Kiểm tra cận/chiều hoặc dùng `WITH ORDINALITY`.

### Lỗi 8 — Tin rằng UNNEST giữ thứ tự cuối trong mọi truy vấn

Trong SQL, để đảm bảo thứ tự đầu ra, dùng `WITH ORDINALITY` rồi `ORDER BY`. Đặc biệt sau join/group, thứ tự tình cờ không phải hợp đồng.

### Lỗi 9 — Dùng CROSS JOIN LATERAL khi phải giữ mọi sản phẩm

`UNNEST` của mảng rỗng/NULL trả 0 hàng, nên `CROSS JOIN` làm mất product 104/106. Dùng `LEFT JOIN LATERAL ... ON TRUE` nếu cần giữ hàng gốc.

### Lỗi 10 — Nghĩ LEFT JOIN LATERAL luôn tạo số hàng bằng số sản phẩm

Sản phẩm có ba nhãn sẽ tạo ba hàng, còn mảng rỗng tạo một placeholder; tổng có thể **nhiều hơn số sản phẩm**.

### Lỗi 11 — COUNT(*) trên outer expansion để đếm phần tử thật

`COUNT(*)` đếm cả placeholder. Dùng `COUNT(position)` nếu cần tính cả phần tử thật có giá trị NULL mà không đếm hàng rỗng của outer join.

### Lỗi 12 — Đặt điều kiện bên phải trong WHERE rồi tưởng giữ được LEFT JOIN

`WHERE u.tag='sale'` loại hàng placeholder. Nếu muốn giữ sản phẩm không có sale, cân nhắc điều kiện `ON u.tag='sale'`.

### Lỗi 13 — Ghép hai UNNEST bằng CROSS JOIN khi muốn zip theo vị trí

Hai mảng dài 2 có thể tạo **4 cặp** qua Cartesian product. Dùng dạng unnest nhiều mảng theo vị trí hoặc join theo ordinality nếu yêu cầu.

### Lỗi 14 — Bỏ qua phần tử được đệm NULL khi hai mảng không đều

`unnest(array1,array2)` ở FROM có thể đệm NULL cho mảng ngắn hơn. Nếu độ dài phải bằng nhau, hãy kiểm tra số phần tử trước.

### Lỗi 15 — ARRAY_AGG trên tập rỗng mặc định trả mảng rỗng

PostgreSQL `array_agg` thường trả `NULL` khi không có hàng. Nếu muốn `{}`, `COALESCE` phải là quyết định có chủ đích.

### Lỗi 16 — ARRAY_AGG sau LEFT JOIN tạo một phần tử NULL

Hàng placeholder từ outer join có thể đi vào `array_agg`. Dùng `FILTER (WHERE ordinality IS NOT NULL)` để bỏ placeholder.

### Lỗi 17 — Dùng DISTINCT rồi tưởng khôi phục mảng gốc

`ARRAY_AGG(DISTINCT tag)` loại nhãn trùng. Với product 107, `sport` xuất hiện hai lần; kết quả không còn giống mảng gốc.

### Lỗi 18 — Dùng COUNT(*) để đếm số sản phẩm gắn nhãn

Product 107 có hai `sport`; `COUNT(*)` sau unnest đếm số phần tử, không phải số product. Dùng `COUNT(DISTINCT product_id)` khi báo cáo số sản phẩm.

### Lỗi 19 — Nghĩ ANY với NULL luôn là FALSE

`= ANY` có thể trả UNKNOWN nếu mảng/so sánh có NULL. `WHERE` chỉ giữ TRUE; trong phủ định logic cần chú ý ba giá trị.

### Lỗi 20 — Nghĩ @> có kiểm tra số lần xuất hiện

Array containment PostgreSQL không phải phép so multiset đếm duplicate. Dùng `UNNEST` + `COUNT` nếu cần “ít nhất hai lần sport”.

### Lỗi 21 — Cho rằng một GIN index tăng tốc mọi phép lọc và sắp

GIN phù hợp một số toán tử array như `@>`/`&&`, nhưng không tự cung cấp mọi `ORDER BY`/`LIMIT`. Kiểm tra `EXPLAIN` và workload.

### Lỗi 22 — Nhét quan hệ phức tạp vào mảng dù cần khóa ngoại từng phần tử

Mảng tiện lợi nhưng khó áp ràng buộc thuộc tính/quan hệ tới từng nhãn. Khi yêu cầu phức tạp, cân nhắc bảng con với khóa, FK và index.

### Lỗi 23 — Dùng toàn bộ mảng làm “bộ giá trị duy nhất” mà không kiểm soát duplicate

`array_append` không tự cấm cùng nhãn xuất hiện hai lần. Quy tắc uniqueness phần tử cần validation hoặc thiết kế bảng con thích hợp.

### Lỗi 24 — Port dấu ngoặc vuông PostgreSQL sang BigQuery

BigQuery dùng `[OFFSET(0)]` hoặc `[ORDINAL(1)]` với hàm truy cập rõ ràng; `SAFE_OFFSET`/`SAFE_ORDINAL` dùng khi muốn xử lý ngoài cận thành NULL.

### Lỗi 25 — Nhầm WITH OFFSET BigQuery với WITH ORDINALITY PostgreSQL

BigQuery offset 0, PostgreSQL ordinality 1. Khi đối chiếu vị trí, phải quy đổi đúng.

### Lỗi 26 — Nhầm JSON path 0-based với MySQL JSON_TABLE FOR ORDINALITY

`$[0]` là phần tử đầu trong JSON path MySQL, nhưng cột `FOR ORDINALITY` của `JSON_TABLE` được đánh số từ 1.

### Lỗi 27 — Dùng UNNEST(TEXT[]) cho JSONB PostgreSQL

JSONB là kiểu khác typed array. Dùng `jsonb_array_elements`/`jsonb_array_elements_text` khi cột là JSONB và cần xử lý JSON array.

### Lỗi 28 — Coi Snowflake FLATTEN, SQL Server OPENJSON, SQLite json_each là cùng một hàm

Mục tiêu tương tự nhưng kiểu, cột đầu ra, chỉ số, NULL/missing và điều kiện outer expansion khác nhau.

### Lỗi 29 — Không kiểm tra khả năng JSON của SQL Server hoặc SQLite

`OPENJSON` yêu cầu phiên bản/compatibility level SQL Server phù hợp; SQLite cần phiên bản/build có chức năng JSON. Không mặc định tất cả môi trường đều hỗ trợ.

### Lỗi 30 — Cập nhật mảng bằng read-modify-write không có bảo vệ đồng thời

Hai phiên đọc cùng mảng rồi ghi đè nguyên giá trị có thể làm mất thay đổi của nhau. Cân nhắc phép cập nhật mảng trong SQL, transaction và version/locking.

## 30. Bài tập thực hành có đáp án

Các bài 1–26 dùng PostgreSQL và bảng `product_array_lab` ở mục 2. Các bài cuối đối chiếu phương ngữ. Trừ các bài được chỉ rõ thao tác DML, đây là những truy vấn chỉ đọc. Với `UPDATE` trong môi trường thực hành, dùng `BEGIN ... ROLLBACK` để giữ dữ liệu gốc.

### Bài 1 — Tạo mảng số nguyên

Viết một biểu thức tạo mảng có ba số 10, 20, 30.

```sql
SELECT ARRAY[10,20,30]::INTEGER[] AS numbers;
```

**Đáp án:** một mảng số nguyên ba phần tử, không phải ba hàng.

### Bài 2 — Truy cập phần tử thứ hai

```sql
SELECT tags[2] AS second_tag
FROM product_array_lab
WHERE product_id = 101;
```

**Đáp án:** `blue`. Chỉ số mảng thông thường PostgreSQL bắt đầu tại 1.

### Bài 3 — Đọc phần tử đầu và cuối

```sql
SELECT
    tags[array_lower(tags,1)] AS first_tag,
    tags[array_upper(tags,1)] AS last_tag
FROM product_array_lab
WHERE product_id = 103;
```

**Đáp án:** `shoes` và `sale`.

### Bài 4 — Chỉ số 0 có phải đầu mảng không?

```sql
SELECT tags[0], tags[1]
FROM product_array_lab
WHERE product_id = 102;
```

**Đáp án:** với mảng mẫu lower bound 1, `tags[0] = NULL` và `tags[1] = clothing`. Không dùng 0 theo thói quen Java/Python.

### Bài 5 — Lấy hai phần tử đầu

```sql
SELECT tags[1:2]
FROM product_array_lab
WHERE product_id = 101;
```

**Đáp án:** mảng con `{clothing,blue}`.

### Bài 6 — Mảng rỗng

```sql
SELECT product_id
FROM product_array_lab
WHERE cardinality(tags) = 0;
```

**Đáp án:** **104**. `cardinality('{}'::TEXT[])=0`.

### Bài 7 — Cột mảng NULL

```sql
SELECT product_id
FROM product_array_lab
WHERE tags IS NULL;
```

**Đáp án:** **106**. Đây không phải mảng rỗng `{}`.

### Bài 8 — Mảng một phần tử NULL

```sql
SELECT cardinality(ARRAY[NULL]::INTEGER[]);
```

**Đáp án:** **1**, vì mảng chứa một vị trí có giá trị NULL.

### Bài 9 — array_length và cardinality

Với `'{}'::TEXT[]`, `cardinality` và `array_length(...,1)` khác nhau thế nào?

**Đáp án:** `cardinality = 0`, còn `array_length(...,1) = NULL` trong PostgreSQL.

### Bài 10 — Tìm nhãn sale với ANY

```sql
SELECT product_id
FROM product_array_lab
WHERE 'sale' = ANY(tags)
ORDER BY product_id;
```

**Đáp án:** **101, 103**.

### Bài 11 — Chứa đồng thời blue và clothing

```sql
SELECT product_id
FROM product_array_lab
WHERE tags @> ARRAY['blue','clothing']::TEXT[];
```

**Đáp án:** **101**.

### Bài 12 — Có blue hoặc sport

```sql
SELECT product_id
FROM product_array_lab
WHERE tags && ARRAY['blue','sport']::TEXT[]
ORDER BY product_id;
```

**Đáp án:** **101, 103, 105, 107**.

### Bài 13 — Đếm sport lặp

```sql
SELECT p.product_id, COUNT(*) AS sport_count
FROM product_array_lab AS p
CROSS JOIN LATERAL unnest(p.tags) AS u(tag)
WHERE u.tag = 'sport'
GROUP BY p.product_id
ORDER BY p.product_id;
```

**Đáp án:** 103 có `1`, 107 có `2`.

### Bài 14 — Bung mảng sản phẩm 101

```sql
SELECT tag
FROM unnest(
    (SELECT tags
     FROM product_array_lab
     WHERE product_id = 101)
) AS u(tag);
```

**Đáp án:** ba hàng có `clothing`, `blue`, `sale`. Nếu cần thứ tự hiển thị chắc chắn, dùng `WITH ORDINALITY` và `ORDER BY`.

### Bài 15 — Giữ vị trí nhãn

```sql
SELECT u.position, u.tag
FROM product_array_lab AS p
CROSS JOIN LATERAL
    unnest(p.tags) WITH ORDINALITY AS u(tag, position)
WHERE p.product_id = 101
ORDER BY u.position;
```

**Đáp án:** `(1,clothing)`, `(2,blue)`, `(3,sale)`.

### Bài 16 — CROSS JOIN LATERAL cho toàn bảng

```sql
SELECT COUNT(*) AS emitted_tags
FROM product_array_lab AS p
CROSS JOIN LATERAL unnest(p.tags) AS u(tag);
```

**Đáp án:** **15 hàng**, vì 104/106 không phát sinh phần tử.

### Bài 17 — LEFT JOIN LATERAL

```sql
SELECT
    COUNT(*) AS rows_after_join,
    COUNT(u.tag) AS known_tags
FROM product_array_lab AS p
LEFT JOIN LATERAL unnest(p.tags) AS u(tag)
    ON TRUE;
```

**Đáp án:** `rows_after_join = 17`, `known_tags = 15`.

### Bài 18 — Phần tử NULL thật và placeholder

Giả sử bung `ARRAY[NULL,5]::INTEGER[]` bằng `WITH ORDINALITY`, sau đó outer join với hàng chứa mảng rỗng. Làm sao phân biệt phần tử NULL thật với placeholder?

**Đáp án:** kiểm tra **ordinality**. Phần tử thật có position không NULL dù value NULL; placeholder có cả value và position NULL.

### Bài 19 — Đếm số nhãn khác nhau của product 107

```sql
SELECT COUNT(DISTINCT u.tag)
FROM product_array_lab AS p
CROSS JOIN LATERAL unnest(p.tags) AS u(tag)
WHERE p.product_id = 107;
```

**Đáp án:** **2 nhãn**: clothing và sport, dù có ba phần tử.

### Bài 20 — Đếm số sản phẩm có nhãn sport

```sql
SELECT COUNT(DISTINCT p.product_id)
FROM product_array_lab AS p
CROSS JOIN LATERAL unnest(p.tags) AS u(tag)
WHERE u.tag = 'sport';
```

**Đáp án:** **2 sản phẩm** (103, 107), không phải 3 occurrences.

### Bài 21 — Khôi phục mảng theo vị trí

```sql
SELECT array_agg(u.tag ORDER BY u.position)
FROM product_array_lab AS p
CROSS JOIN LATERAL
    unnest(p.tags) WITH ORDINALITY AS u(tag, position)
WHERE p.product_id = 107;
```

**Đáp án:** `{clothing,sport,sport}`. Không thêm `DISTINCT` nếu muốn giữ nguyên số lần xuất hiện.

### Bài 22 — ARRAY_AGG không có hàng

```sql
SELECT array_agg(product_id)
FROM product_array_lab
WHERE tenant_id = 999;
```

**Đáp án:** thường là `NULL` trong PostgreSQL, không tự tạo `{}`. Dùng `COALESCE(...,'{}'::INTEGER[])` khi muốn mảng rỗng.

### Bài 23 — Giữ empty array sau LEFT JOIN

Làm sao tránh `ARRAY_AGG` thu placeholder thành `{NULL}`?

**Đáp án:**

```sql
COALESCE(
    array_agg(u.tag ORDER BY u.position)
        FILTER (WHERE u.position IS NOT NULL),
    '{}'::TEXT[]
)
```

Nếu muốn giữ khác biệt giữa `NULL` nguồn và `{}`, cần kiểm tra `p.tags IS NULL` và quyết định riêng.

### Bài 24 — Điểm trung bình product 105

```sql
SELECT
    COUNT(*) AS positions,
    COUNT(score) AS known_scores,
    AVG(score) AS avg_score
FROM unnest(
    ARRAY[NULL,5]::INTEGER[]
) AS u(score);
```

**Đáp án:** `positions=2`, `known_scores=1`, `avg_score=5`.

### Bài 25 — Hai UNNEST song song

```sql
SELECT *
FROM unnest(
    ARRAY['a','b']::TEXT[],
    ARRAY[10]::INTEGER[]
) AS u(letter, number);
```

**Đáp án:** hai hàng `(a,10)` và `(b,NULL)`. Mảng ngắn hơn được đệm NULL trong mẫu `FROM` này.

### Bài 26 — CROSS JOIN hai UNNEST

Hai mảng dài 2 được bung bằng hai `CROSS JOIN` riêng thì có bao nhiêu hàng?

**Đáp án:** `2 × 2 = 4` hàng, không phải hai hàng ghép theo vị trí.

### Bài 27 — Mảng hai chiều

```sql
WITH x AS (
    SELECT ARRAY[[10,20],[30,40]]::INTEGER[] AS a
)
SELECT a[2][1], cardinality(a)
FROM x;
```

**Đáp án:** `a[2][1]=30`, tổng phần tử bằng **4**.

### Bài 28 — generate_subscripts

Tại sao `generate_subscripts` khác `WITH ORDINALITY` khi mảng bắt đầu tại -2?

**Đáp án:** `generate_subscripts` cho **subscript gốc** `-2,-1,0,1`; ordinality cho **thứ tự bung** `1,2,3,4`.

### Bài 29 — Thêm một nhãn trong transaction

```sql
BEGIN;

UPDATE product_array_lab
SET tags = array_append(tags, 'new')
WHERE product_id = 101
RETURNING tags;

ROLLBACK;
```

**Đáp án:** trong transaction có `{clothing,blue,sale,new}`; rollback khôi phục mảng ban đầu.

### Bài 30 — Xóa nhãn lặp

```sql
SELECT array_remove(
    ARRAY['clothing','sport','sport']::TEXT[],
    'sport'
);
```

**Đáp án:** `{clothing}`. `array_remove` không chỉ loại một occurrence đầu.

### Bài 31 — BigQuery OFFSET/ORDINAL

Mảng `['clothing','blue','sale']` trong BigQuery: hai biểu thức nào lấy `blue`?

**Đáp án:** `tags[OFFSET(1)]` hoặc `tags[ORDINAL(2)]`.

### Bài 32 — BigQuery WITH OFFSET

`UNNEST(['a','b']) WITH OFFSET AS pos` trả những vị trí nào?

**Đáp án:** **0 và 1**. Đừng nhầm với PostgreSQL `WITH ORDINALITY` là **1 và 2**.

### Bài 33 — Snowflake FLATTEN

Trong Snowflake, cột nào của `LATERAL FLATTEN(INPUT => p.tags)` thường cho giá trị phần tử và chỉ số?

**Đáp án:** `VALUE` chứa giá trị phần tử, `INDEX` chứa vị trí **0-based** của array.

### Bài 34 — SQL Server OPENJSON

`OPENJSON(N'["a","b"]')` trả hai dòng với `key` như thế nào?

**Đáp án:** key tương ứng `0` và `1` dưới dạng dữ liệu văn bản khóa; `value` là `a` và `b`. Dùng `CROSS APPLY` hoặc `OUTER APPLY` để bung theo hàng bảng.

### Bài 35 — MySQL JSON_TABLE

MySQL dùng `JSON_EXTRACT(tags,'$[0]')` lấy phần tử đầu; tại sao cột `FOR ORDINALITY` của `JSON_TABLE` lại trả 1 cho phần tử đầu?

**Đáp án:** JSON path dùng **0-based** indexing, còn `FOR ORDINALITY` tạo bộ đếm dòng **1-based**.

### Bài 36 — SQLite json_each

Trên SQLite, `json_each('["a","b"]')` tạo bao nhiêu hàng và key bắt đầu từ đâu?

**Đáp án:** **2 hàng**, các array key tương ứng vị trí **0 và 1**.

### Bài 37 — Oracle collection

Oracle PL/SQL có một collection `v_tags` kiểu `SYS.ODCIVARCHAR2LIST('a','b')`. Cách truy cập phần tử đầu trong ví dụ là gì?

**Đáp án:** `v_tags(1)` trong PL/SQL, không phải cú pháp `v_tags[1]` của PostgreSQL hay `[OFFSET(0)]` của BigQuery.

### Bài 38 — Mảng hay bảng con?

Hệ thống muốn đảm bảo mỗi nhãn có khóa ngoại tới danh mục, không cho nhãn trùng trong từng sản phẩm và ghi lại người gắn nhãn. Nên dùng `TEXT[]` hay bảng con?

**Đáp án định hướng:** bảng con như `product_tags(product_id,tag,position,assigned_by,assigned_at)` thường phù hợp hơn vì có thể đặt FK, UNIQUE, index và quản lý thuộc tính mỗi quan hệ. Nếu phần tử có thể lặp với ý nghĩa nghiệp vụ, cần thiết kế khóa/ordinal tương ứng thay vì áp UNIQUE mù quáng.

## 31. Bảng ghi nhớ nhanh

| Mục tiêu | PostgreSQL | Ghi nhớ |
|---|---|---|
| Tạo mảng | `ARRAY['a','b']::TEXT[]` | Kiểu phần tử rõ ràng |
| Mảng rỗng | `'{}'::TEXT[]` | 0 phần tử |
| Mảng NULL | `NULL::TEXT[]` | Không có giá trị mảng |
| Phần tử NULL | `ARRAY[NULL]::TEXT[]` | Một phần tử có giá trị NULL |
| Phần tử đầu | `tags[1]` | Với mảng thông thường bắt đầu từ 1 |
| Phần tử cuối | `tags[array_upper(tags,1)]` | Không dùng -1 kiểu Python |
| Lát cắt | `tags[1:2]` | Kết quả là mảng con |
| Tổng số phần tử | `cardinality(tags)` | Rỗng → 0; NULL → NULL |
| Chiều cụ thể | `array_length(tags,1)` | Rỗng có thể → NULL |
| Cận chỉ số thật | `array_lower`, `array_upper` | Có thể khác 1 |
| Vị trí nhãn | `array_position`/`array_positions` | Tìm vị trí xuất hiện |
| Có nhãn sale | `'sale'=ANY(tags)` | Nhớ logic NULL |
| Chứa cả hai nhãn | `tags @> ARRAY['a','b']` | Không đếm duplicate |
| Có ít nhất một nhãn | `tags && ARRAY['a','b']` | Giao mảng |
| Chuyển mảng thành hàng | `unnest(tags)` | Rỗng/NULL → 0 hàng |
| Giữ vị trí phát ra | `WITH ORDINALITY` | Đánh số 1-based |
| Bung mỗi hàng sản phẩm | `CROSS JOIN LATERAL unnest(p.tags)` | Loại sản phẩm không có phần tử |
| Giữ sản phẩm không có nhãn | `LEFT JOIN LATERAL ... ON TRUE` | Thêm placeholder NULL |
| Giữ chỉ số gốc | `generate_subscripts(a,1)` | Khác ordinality nếu lower bound đặc biệt |
| Ghép nhiều mảng theo vị trí | `unnest(a,b)` trong FROM | Có thể đệm NULL |
| Gom hàng thành mảng | `array_agg(x ORDER BY pos)` | Có thứ tự rõ ràng |
| Tránh placeholder trong ARRAY_AGG | `FILTER (WHERE pos IS NOT NULL)` | Phân biệt outer join và phần tử NULL |
| Thêm phần tử | `array_append(tags,'x')` | Không tự cấm trùng |
| Index tìm phần tử | `GIN(tags)`, toán tử phù hợp | Không tự tối ưu mọi query |
| BigQuery | `UNNEST` + `WITH OFFSET` | Offset 0-based; ORDINAL 1-based |
| Snowflake | `LATERAL FLATTEN` | INDEX 0-based |
| MySQL | `JSON_TABLE` | JSON path 0-based; ordinality 1-based |
| SQL Server | `OPENJSON` + `APPLY` | Key array 0-based |
| SQLite | `json_each` | Key array 0-based |
| Oracle | `TABLE(collection)` | Collection rules riêng |

## Kết luận

**Kiểu mảng** mở rộng cách biểu diễn dữ liệu trong SQL: một cột có thể chứa **nhiều phần tử có thứ tự**, nhưng việc truy cập và biến đổi cần hiểu rõ kiểu dữ liệu, chỉ số và cardinality.

Các nguyên tắc quan trọng:

1. **Mảng PostgreSQL thông thường bắt đầu ở chỉ số 1**, không phải 0. Dùng `array_lower`/`array_upper` khi cần thao tác đúng với mảng có lower bound đặc biệt; không mặc định `[-1]` là phần tử cuối.
2. **`NULL`, `{}` và `{NULL}` là ba tình huống khác nhau.** `cardinality`, `array_length` và `UNNEST` cho kết quả khác nhau theo ngữ nghĩa của từng trường hợp.
3. **`ANY`, `ALL`, `@>`, `&&`** giúp tìm và so sánh phần tử, nhưng phải xét logic ba giá trị và sự khác nhau giữa **kiểm tra tồn tại** với **đếm số lần xuất hiện**.
4. **`UNNEST` biến phần tử thành hàng**; `WITH ORDINALITY` giữ vị trí phát ra. Khi bung mảng thuộc từng hàng của bảng, dùng `LATERAL` để biểu diễn sự phụ thuộc.
5. **`CROSS JOIN LATERAL` và `LEFT JOIN LATERAL` cho hai tập kết quả khác nhau.** Cách đầu chỉ giữ hàng có phần tử; cách sau còn giữ sản phẩm có mảng rỗng/NULL.
6. **`COUNT(*)`, `COUNT(value)`, `COUNT(position)` và `COUNT(DISTINCT ...)` trả lời những câu hỏi khác nhau** sau khi bung mảng. Tương tự, `ARRAY_AGG` cần `ORDER BY` và thường cần `FILTER` khi khôi phục dữ liệu sau outer join.
7. **Typed SQL arrays và JSON arrays khác nhau.** BigQuery, Snowflake, MySQL, SQL Server, SQLite và Oracle có cú pháp khai triển cũng như hệ đếm vị trí riêng; không port truy vấn mảng nguyên văn.
8. **Mảng không thay thế mọi bảng con**. Khi cần khóa ngoại, thuộc tính trên từng phần tử, uniqueness hoặc analytics lớn, mô hình quan hệ chuẩn hóa có thể rõ ràng hơn. Với PostgreSQL, GIN index có thể hỗ trợ một số truy vấn theo phần tử khi workload phù hợp.

Điều cần nhớ khi thiết kế là **mảng là một giá trị nhưng `UNNEST` tạo ra một quan hệ nhiều hàng**. Mỗi lần chuyển giữa hai cách biểu diễn, phải kiểm soát **số phần tử, thứ tự, giá trị NULL, phần tử trùng và việc giữ hoặc loại hàng gốc**. Khi làm rõ những chi tiết đó, bạn có thể khai thác dữ liệu dạng danh sách bằng SQL mà không làm mất hàng, đếm sai hay trộn lẫn chỉ số giữa các phương ngữ.

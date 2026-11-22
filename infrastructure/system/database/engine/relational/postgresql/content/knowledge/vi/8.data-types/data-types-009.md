# Mảng, kiểu phần tử và kích thước mảng trong PostgreSQL

## 1. Vì sao PostgreSQL có kiểu dữ liệu mảng?

Trong mô hình quan hệ, một bảng gồm các hàng và cột. Thông thường mỗi cột lưu một giá trị thuộc một kiểu dữ liệu nhất định. PostgreSQL mở rộng khả năng này bằng **array type** (kiểu mảng): một giá trị trong một cột có thể chứa **nhiều phần tử cùng kiểu**.

Ví dụ một dự án có ba nhãn:

```text
project_id = 101
project_name = "Tối ưu truy vấn"
labels = {"postgresql", "performance", "backend"}
```

Thay vì tạo ba cột `label_1`, `label_2`, `label_3`, ta có thể dùng một cột `labels text[]`.

PostgreSQL cho phép:

- Khai báo cột kiểu `integer[]`, `text[]`, `uuid[]`, `date[]` và nhiều kiểu mảng khác.
- Tạo mảng bằng `ARRAY[...]` hoặc bằng cú pháp literal `'{...}'` kèm kiểu dữ liệu.
- Lưu mảng một chiều hoặc đa chiều, truy cập phần tử bằng chỉ số.
- Đo số chiều, chiều dài từng chiều, tổng số phần tử và cận chỉ số.
- Thêm/bớt/thay phần tử, kiểm tra chứa/chồng lấp.
- Biến phần tử mảng thành các hàng với `unnest()`, hoặc gom hàng thành mảng với `array_agg()`.
- Tạo chỉ mục GIN cho một số truy vấn tìm kiếm phần tử mảng.

Mảng hữu ích khi nhóm phần tử là một giá trị tập hợp nhỏ và thường được xử lý cùng bản ghi cha. Tuy nhiên, mảng **không phải giải pháp mặc định cho mọi quan hệ một-nhiều**. Khi phần tử cần khóa ngoại, quyền riêng, thuộc tính riêng hoặc cập nhật độc lập, bảng con thường phù hợp hơn.

Bài học tập trung vào ba câu hỏi:

1. **Kiểu phần tử:** một mảng chứa dữ liệu kiểu gì?
2. **Kích thước và chiều:** mảng dài bao nhiêu, có mấy chiều, đánh chỉ số từ đâu?
3. **Vận hành:** đọc/ghi, tìm kiếm, mở rộng, biến đổi và thiết kế schema với mảng thế nào cho đúng?

## 2. Hình dung một mảng ở mức dữ liệu

Một mảng một chiều:

```text
Giá trị:       10      20      30      40
Chỉ số:         1       2       3       4
              [1]     [2]     [3]     [4]
```

Một mảng hai chiều:

```text
                  Cột 1   Cột 2   Cột 3
Hàng chỉ số 1        1        2        3
Hàng chỉ số 2        4        5        6

ARRAY[[1, 2, 3],
      [4, 5, 6]]
```

Mảng được hiểu theo **số chiều** (*dimensions*), **độ dài từng chiều** (*length per dimension*) và **cận dưới/cận trên** của mỗi chiều (*lower/upper bounds*).

Với `ARRAY[10,20,30,40]`:

- Số chiều: 1.
- Độ dài chiều 1: 4.
- Tổng số phần tử: 4.
- Cận dưới mặc định: 1.
- Cận trên: 4.

Với `ARRAY[[1,2,3],[4,5,6]]`:

- Số chiều: 2.
- Chiều 1 có độ dài 2.
- Chiều 2 có độ dài 3.
- Tổng số phần tử: 6.
- Chỉ số phần tử `5` là `[2][2]` theo cách viết mặc định.

**Lưu ý quan trọng:** PostgreSQL mặc định đánh chỉ số mảng từ **1**, không từ 0 như các mảng Java hoặc JavaScript. PostgreSQL cũng cho phép mảng có **cận dưới khác 1** trong một số cách tạo dữ liệu; không thể luôn suy đoán chỉ số đầu bằng 1 khi xử lý mảng có nguồn gốc đặc biệt.

## 3. Kiểu phần tử: `integer[]`, `text[]`, `uuid[]` và các kiểu khác

### 3.1. Cú pháp khai báo

Phần lớn kiểu dữ liệu PostgreSQL đều có kiểu mảng tương ứng.

```sql
CREATE SCHEMA IF NOT EXISTS array_lab;

CREATE TABLE array_lab.examples (
    example_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scores integer[],
    labels text[],
    prices numeric(12,2)[],
    event_days date[],
    member_ids uuid[],
    flags boolean[]
);
```

Các kiểu phần tử tương ứng:

| Cột | Kiểu mảng | Kiểu mỗi phần tử | Ví dụ sử dụng |
|---|---|---|---|
| `scores` | `integer[]` | `integer` | Điểm theo các lượt đo |
| `labels` | `text[]` | `text` | Các nhãn ngắn |
| `prices` | `numeric(12,2)[]` | `numeric(12,2)` | Dãy giá trị tiền tệ minh họa |
| `event_days` | `date[]` | `date` | Danh sách ngày |
| `member_ids` | `uuid[]` | `uuid` | Tập ID tham chiếu theo ứng dụng |
| `flags` | `boolean[]` | `boolean` | Dãy trạng thái đúng/sai |

`numeric(12,2)[]` là mảng có phần tử numeric theo khai báo kiểu; nếu cần bảo đảm các yếu tố nghiệp vụ bổ sung, ví dụ các giá trị không âm, phải bổ sung ràng buộc hoặc chuẩn hóa dữ liệu.

Cú pháp `integer[]` rất thông dụng. PostgreSQL cũng hiểu dạng SQL truyền thống như `integer ARRAY` trong khai báo. Trong code hiện đại, dùng `[]` thường ngắn gọn và dễ đọc.

### 3.2. Kiểu mảng và kiểu phần tử liên hệ thế nào?

Trong PostgreSQL, một kiểu cơ sở như `integer` có kiểu mảng liên quan (ví dụ hệ thống có tên kiểu nội bộ của mảng integer). Khi khai báo `integer[]`, bạn đang dùng **array type** chứa phần tử `integer`.

Một số phép kiểm tra:

```sql
SELECT
    pg_typeof(ARRAY[1, 2, 3]) AS integer_array_type,
    pg_typeof(ARRAY['a', 'b']) AS text_array_type,
    pg_typeof(ARRAY[true, false]) AS boolean_array_type;
```

Thông thường kết quả hiển thị kiểu tương đương `integer[]`, `text[]` và `boolean[]`.

Không nên dùng chuỗi tên kiểu nội bộ với dấu gạch dưới trong SQL ứng dụng chỉ vì thấy nó trong catalog. Cú pháp chuẩn, dễ bảo trì hơn là `integer[]`, `text[]` hoặc kiểu mảng tương ứng.

### 3.3. Phần tử phải có kiểu tương thích

Ví dụ hợp lệ:

```sql
SELECT ARRAY[1, 2, 3]::integer[];
SELECT ARRAY['postgresql', 'sql']::text[];
SELECT ARRAY[DATE '2026-11-14', DATE '2026-11-15']::date[];
```

Ví dụ cần xử lý kiểu:

```sql
-- Không nên giả định mọi hỗn hợp dữ liệu đều tự có kiểu chung hợp lệ:
SELECT ARRAY[1, 'not-a-number'];
```

PostgreSQL phải xác định **một kiểu phần tử chung** cho mảng. Nếu chuỗi không chuyển được sang kiểu suy luận hoặc không tìm được kiểu tương thích, câu lệnh sẽ lỗi. Trong ứng dụng, nên khai báo/cast kiểu rõ thay vì dựa vào chuyển kiểu ngầm khi dữ liệu nhập phức tạp.

Ví dụ truyền integer dưới dạng chuỗi hợp lệ có ép kiểu:

```sql
SELECT ARRAY['10'::integer, '20'::integer];
```

### 3.4. Mảng và phần tử NULL

Cột mảng có thể là `NULL`, và một mảng **không NULL** vẫn có thể chứa các phần tử `NULL`.

```sql
SELECT
    NULL::integer[] AS whole_array_is_null,
    ARRAY[]::integer[] AS empty_but_not_null,
    ARRAY[10, NULL, 30]::integer[] AS array_with_null_element;
```

Ba trường hợp này **khác nhau**:

| Giá trị | Ý nghĩa |
|---|---|
| `NULL::integer[]` | Chưa có giá trị mảng / không biết mảng |
| `ARRAY[]::integer[]` | Mảng tồn tại nhưng không có phần tử |
| `ARRAY[10,NULL,30]::integer[]` | Mảng có ba vị trí, một phần tử là NULL |

Đặt `labels text[] NOT NULL` chỉ ngăn **toàn bộ cột mảng** bị NULL; nó không tự ngăn `labels = ARRAY['a',NULL]::text[]`. Nếu không được có phần tử NULL, cần ràng buộc bổ sung hoặc chọn mô hình bảng liên quan.

## 4. Cách tạo giá trị mảng

### 4.1. Dùng `ARRAY[...]`

Cách trực quan:

```sql
SELECT ARRAY[10, 20, 30] AS numbers;

SELECT ARRAY['Java', 'PostgreSQL', 'SQL']::text[] AS technologies;

SELECT ARRAY[
    TIMESTAMPTZ '2026-11-14 09:00:00+07',
    TIMESTAMPTZ '2026-11-15 09:00:00+07'
] AS meeting_times;
```

`ARRAY[...]` là array constructor. Các biểu thức bên trong được PostgreSQL đánh giá để tạo phần tử.

Dùng cast `::integer[]`, `::text[]` khi muốn xác định kiểu chính xác, đặc biệt với mảng rỗng hoặc giá trị parameter chưa rõ kiểu.

### 4.2. Mảng rỗng phải có kiểu phần tử

Không nên viết:

```sql
-- Không đủ thông tin kiểu phần tử:
-- SELECT ARRAY[];
```

PostgreSQL không thể suy ra kiểu phần tử từ một constructor rỗng. Cần:

```sql
SELECT ARRAY[]::integer[] AS empty_integers;
SELECT ARRAY[]::text[] AS empty_labels;
```

Một cách khác:

```sql
SELECT '{}'::integer[] AS empty_integers;
```

Ý nghĩa là mảng tồn tại và chứa **0 phần tử**, không phải NULL.

### 4.3. Array literal dùng ngoặc nhọn

PostgreSQL có cú pháp nhập mảng dưới dạng **chuỗi được cast**:

```sql
SELECT '{10,20,30}'::integer[];

SELECT '{"xin chào","a,b",""}'::text[];
```

Trong literal kiểu `text[]`, phần tử chứa dấu phẩy, dấu ngoặc kép, backslash hoặc ký tự đặc biệt cần được quoting/escaping theo cú pháp array input. Cách đọc/ghi văn bản literal có thể khá khó khi có nhiều tầng escape (SQL string, JSON, shell).

**Ưu tiên `ARRAY[...]` hoặc parameter binding của driver** cho code ứng dụng. Không tự ghép chuỗi literal mảng từ dữ liệu người dùng: ngoài nguy cơ injection, rất dễ hỏng escape và phân biệt NULL với chuỗi `'NULL'`.

### 4.4. Constructor và literal không giống hệt nhau

| Biểu thức | Cách PostgreSQL hiểu |
|---|---|
| `ARRAY[1,2,3]` | Các biểu thức SQL tạo phần tử |
| `'{1,2,3}'::integer[]` | Chuỗi theo cú pháp array input, chuyển sang integer array |
| `ARRAY['a,b','c']` | Phần tử đầu là chuỗi `a,b` |
| `'{"a,b","c"}'::text[]` | Cần quote để dấu phẩy thuộc phần tử đầu |
| `ARRAY[]::integer[]` | Mảng rỗng kiểu integer |
| `'{}'::integer[]` | Mảng rỗng cùng kiểu integer |

Với giá trị ngày, UUID hoặc enum, dùng kiểu cast rõ ràng có thể giúp tránh nhầm lẫn do phép suy luận kiểu.

## 5. Khai báo kích thước: vì sao `integer[3]` không giới hạn ba phần tử?

Một điểm khác với nhiều ngôn ngữ lập trình: PostgreSQL cho phép viết kích thước trong khai báo kiểu mảng, nhưng **không thực thi kích thước đã khai báo** như một giới hạn dữ liệu.

Hai cách khai báo:

```sql
CREATE TABLE array_lab.declared_sizes (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    expected_three integer[3],
    expected_matrix integer[2][3]
);
```

Các con số `[3]` và `[2][3]` ở khai báo **không buộc** giá trị phải có đúng ba phần tử hoặc đúng ma trận 2×3. PostgreSQL không dùng những con số này làm constraint độ dài, và số chiều khai báo cũng không được thực thi như một constraint cứng trên giá trị.

Ví dụ:

```sql
INSERT INTO array_lab.declared_sizes (
    expected_three,
    expected_matrix
)
VALUES (
    ARRAY[1, 2, 3, 4, 5],
    ARRAY[[1, 2], [3, 4]]
);

SELECT
    cardinality(expected_three) AS number_of_elements,
    array_dims(expected_matrix) AS actual_dimensions
FROM array_lab.declared_sizes;
```

Mặc dù tên cột và khai báo gợi ý ba phần tử hoặc 2×3, các giá trị trên vẫn thể hiện kích thước thực tế riêng.

**Nguyên tắc:** muốn đảm bảo số lượng phần tử, hãy đặt **`CHECK` constraint** phù hợp, không chỉ viết `integer[3]`.

### 5.1. Ví dụ giới hạn tổng số phần tử

```sql
CREATE TABLE array_lab.fixed_scores (
    record_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scores integer[] NOT NULL,
    CONSTRAINT scores_exactly_three
        CHECK (cardinality(scores) = 3)
);
```

Giờ:

```sql
INSERT INTO array_lab.fixed_scores(scores)
VALUES (ARRAY[80, 90, 75]);
```

thành công, còn:

```sql
-- Dự kiến lỗi CHECK:
INSERT INTO array_lab.fixed_scores(scores)
VALUES (ARRAY[80, 90]);
```

bị từ chối.

**Cẩn trọng:** `cardinality(scores) = 3` chỉ ràng buộc **tổng số phần tử**. Một mảng có ba phần tử không tự chứng minh số chiều phải là 1, hoặc cận dưới phải bằng 1. Nếu giao diện/thuật toán yêu cầu đúng dạng vector một chiều, cần thiết kế thêm điều kiện cho hình dạng hoặc chuẩn hóa đầu vào.

### 5.2. Vì sao không nên mặc định "mảng luôn có kích thước cố định"?

PostgreSQL array là kiểu dữ liệu với kích thước biến thiên. Kích thước thực tế nằm trong **giá trị mảng**, không bị “khóa” bởi cú pháp `[n]` của column type.

Điều này tạo sự linh hoạt nhưng đồng thời đòi hỏi application kiểm soát:

- Số phần tử tối đa.
- Số chiều được phép.
- Phần tử NULL.
- Giá trị hợp lệ của từng phần tử.
- Có được phép trùng lặp hay không.
- Độ lớn của mảng và chi phí cập nhật/đọc.

## 6. Đo số chiều, độ dài và tổng phần tử

Đây là những hàm quan trọng nhất cho chủ đề kích thước mảng.

| Hàm | Trả về | Ví dụ ý nghĩa |
|---|---|---|
| `array_ndims(a)` | Số chiều của mảng | 1 với vector, 2 với ma trận |
| `array_length(a, n)` | Độ dài của chiều thứ `n` | Số phần tử trên chiều 1 |
| `cardinality(a)` | Tổng số phần tử ở mọi chiều | 6 với ma trận 2×3 |
| `array_dims(a)` | Chuỗi mô tả cận chỉ số của các chiều | `[1:2][1:3]` |
| `array_lower(a, n)` | Cận dưới của chiều `n` | Thường là 1 |
| `array_upper(a, n)` | Cận trên của chiều `n` | Thường bằng độ dài nếu bắt đầu tại 1 |

### 6.1. Thực hành với mảng một chiều

```sql
SELECT
    array_ndims(ARRAY[10,20,30,40]) AS ndims,
    array_length(ARRAY[10,20,30,40], 1) AS len_dim1,
    cardinality(ARRAY[10,20,30,40]) AS total_elements,
    array_dims(ARRAY[10,20,30,40]) AS dimension_bounds,
    array_lower(ARRAY[10,20,30,40], 1) AS lower_bound,
    array_upper(ARRAY[10,20,30,40], 1) AS upper_bound;
```

Giá trị mong đợi:

| ndims | len_dim1 | total_elements | dimension_bounds | lower_bound | upper_bound |
|---:|---:|---:|---|---:|---:|
| 1 | 4 | 4 | `[1:4]` | 1 | 4 |

### 6.2. Thực hành với mảng hai chiều

```sql
SELECT
    array_ndims(ARRAY[[1,2,3],[4,5,6]]) AS ndims,
    array_length(ARRAY[[1,2,3],[4,5,6]], 1) AS rows_count,
    array_length(ARRAY[[1,2,3],[4,5,6]], 2) AS columns_count,
    cardinality(ARRAY[[1,2,3],[4,5,6]]) AS total_elements,
    array_dims(ARRAY[[1,2,3],[4,5,6]]) AS dimension_bounds;
```

Kết quả:

```text
ndims            = 2
rows_count       = 2
columns_count    = 3
total_elements   = 6
dimension_bounds = [1:2][1:3]
```

Độ dài của từng chiều không giống tổng phần tử. Với ma trận 2×3, `array_length(..., 1) = 2` còn `cardinality(...) = 6`.

### 6.3. Mảng rỗng và giá trị NULL

Đây là một điểm dễ sai:

```sql
SELECT
    array_length(ARRAY[]::integer[], 1) AS length_empty,
    cardinality(ARRAY[]::integer[]) AS cardinality_empty,
    cardinality(NULL::integer[]) AS cardinality_null;
```

Ngữ nghĩa quan trọng:

- `array_length` đối với **chiều không có phần tử/không tồn tại** trả `NULL`, **không phải 0**.
- `cardinality` của **mảng rỗng không NULL** trả `0`.
- `cardinality` của **toàn bộ mảng NULL** trả `NULL`.

Khi cần đếm số phần tử và xử lý mảng rỗng, `cardinality()` thường dễ dùng hơn. Nếu cột có thể NULL và muốn coi NULL là 0 theo chính sách ứng dụng:

```sql
SELECT COALESCE(cardinality(NULL::integer[]), 0) AS safe_count;
```

Tuy vậy, quyết định xem NULL và mảng rỗng có cùng ý nghĩa nghiệp vụ không phải do SQL tự quyết định.

### 6.4. Chiều không tồn tại

```sql
SELECT
    array_length(ARRAY[10,20,30], 2) AS second_dimension_length,
    array_upper(ARRAY[10,20,30], 2) AS second_dimension_upper;
```

Mảng trên chỉ có một chiều, nên hỏi chiều thứ hai không cho một độ dài hợp lệ. Đừng dùng các giá trị NULL từ truy vấn như vậy để suy luận rằng hàng chứa dữ liệu hỏng.

## 7. Chỉ số dưới và chỉ số trên không nhất thiết bắt đầu bằng 1

Đa số mảng khởi tạo bằng `ARRAY[...]` được đánh chỉ số từ 1:

```sql
SELECT
    (ARRAY[10, 20, 30])[1] AS first,
    (ARRAY[10, 20, 30])[3] AS third;
```

Nhưng PostgreSQL cho phép mảng có cận dưới khác 1, ví dụ literal ghi rõ bounds:

```sql
SELECT '[0:2]={10,20,30}'::integer[] AS zero_based_array;
```

Truy cập:

```sql
SELECT
    ('[0:2]={10,20,30}'::integer[])[0] AS first_element,
    ('[0:2]={10,20,30}'::integer[])[2] AS last_element,
    array_lower('[0:2]={10,20,30}'::integer[], 1) AS lower_index,
    array_upper('[0:2]={10,20,30}'::integer[], 1) AS upper_index;
```

Giá trị mong đợi: phần tử đầu là 10 tại chỉ số 0, phần tử cuối là 30 tại chỉ số 2.

### 7.1. Tạo mảng có lower bound cụ thể bằng `array_fill`

```sql
SELECT
    array_fill(7, ARRAY[3], ARRAY[0]) AS filled_array,
    array_dims(array_fill(7, ARRAY[3], ARRAY[0])) AS bounds;
```

Ở đây:

- `7` là giá trị dùng để điền.
- `ARRAY[3]` mô tả một chiều có độ dài 3.
- `ARRAY[0]` quy định cận dưới của chiều đó là 0.

Một trường hợp hai chiều:

```sql
SELECT
    array_fill(5, ARRAY[2,3], ARRAY[0,1]) AS matrix,
    array_dims(array_fill(5, ARRAY[2,3], ARRAY[0,1])) AS bounds;
```

Kết quả có **hai chiều**, lần lượt dài 2 và 3; cận dưới là 0 ở chiều 1 và 1 ở chiều 2.

### 7.2. Vì sao chuyện này ảnh hưởng code?

Không nên coi `array_length(a,1)` luôn bằng chỉ số trên. Với mảng bắt đầu ở 0 và dài 3:

- `array_length(a,1) = 3`.
- `array_lower(a,1) = 0`.
- `array_upper(a,1) = 2`.

Nếu cần đi qua **chỉ số thật**, dùng `generate_subscripts()` thay vì tự suy luận chỉ số từ 1 đến `cardinality()`.

## 8. Truy cập một phần tử và cắt lát (*slice*)

### 8.1. Truy cập theo chỉ số

```sql
SELECT
    (ARRAY['SQL', 'PostgreSQL', 'Java'])[1] AS first_item,
    (ARRAY['SQL', 'PostgreSQL', 'Java'])[2] AS second_item;
```

Cú pháp:

```text
array_expression[subscript]
```

Trong câu `SELECT`, thường đặt biểu thức mảng phức tạp trong ngoặc đơn trước khi thêm `[index]`.

Với một cột:

```sql
SELECT
    example_id,
    labels[1] AS first_label
FROM array_lab.examples;
```

### 8.2. Chỉ số vượt cận

```sql
SELECT (ARRAY[10,20,30])[9] AS out_of_range;
```

Truy cập **một phần tử** ngoài cận trong biểu thức thông thường trả `NULL`, không nhất thiết ném exception như truy cập mảng sai chỉ số trong Java.

Điều này khiến câu:

```sql
SELECT labels[3]
FROM array_lab.examples;
```

có thể trả NULL bởi **ít hơn ba phần tử**, bởi phần tử thứ ba thật sự là NULL hoặc vì cột mảng NULL. Nếu ứng dụng cần phân biệt, kiểm tra `cardinality`, `array_lower/upper` và trạng thái null của mảng.

### 8.3. Cắt lát mảng

```sql
SELECT
    (ARRAY[10,20,30,40,50])[2:4] AS middle_slice;
```

Phần slice từ chỉ số 2 đến 4 tương ứng các giá trị `20,30,40`. Cú pháp:

```text
array_expression[start_index:end_index]
```

PostgreSQL cho phép slice nhiều chiều với các cặp cận tương ứng. Khi dùng slice, cần phân biệt **chỉ số của mảng nguồn** và cận của giá trị mảng được trả ra; không nên mặc định mọi thao tác slice, concatenation hoặc assignment đều bảo toàn/đặt lại bounds y hệt nhau trong mọi trường hợp.

### 8.4. Cú pháp dễ nhầm giữa element và slice

Ví dụ `a[2]` lấy **một phần tử**, còn `a[2:3]` lấy **một mảng con**. Với multi-dimensional array, nếu một chiều được viết theo slice, PostgreSQL có quy tắc coi các chỉ số khác trong biểu thức là slice bounds; hãy viết đủ cận rõ ràng để tránh kết quả bất ngờ.

## 9. Mảng nhiều chiều: ma trận và hình dạng

### 9.1. Tạo mảng hai chiều

```sql
SELECT ARRAY[
    [1, 2, 3],
    [4, 5, 6]
]::integer[] AS matrix;
```

Bạn cũng có thể dùng literal:

```sql
SELECT '{{1,2,3},{4,5,6}}'::integer[] AS matrix;
```

Lấy phần tử hàng 2, cột 1:

```sql
SELECT
    (ARRAY[[1,2,3],[4,5,6]])[2][1] AS value_4,
    (ARRAY[[1,2,3],[4,5,6]])[2][3] AS value_6;
```

### 9.2. Các chiều cần có độ dài tương ứng

PostgreSQL lưu multi-dimensional array với hình dạng **hình chữ nhật**: các sub-array cùng mức phải có số phần tử/chiều phù hợp.

Ví dụ cố gắng tạo dữ liệu không đều:

```sql
-- Dự kiến lỗi: các mảng con có số phần tử không khớp.
SELECT ARRAY[
    [1, 2, 3],
    [4, 5]
];
```

Mảng trên không phải ma trận 2×3 hợp lệ, vì hàng thứ hai chỉ có hai phần tử.

Nếu nghiệp vụ thật sự cần “danh sách các danh sách dài ngắn khác nhau”, hãy cân nhắc:

- Một bảng con ghi từng phần tử kèm tọa độ/thứ tự.
- Một cấu trúc JSONB khi dữ liệu phân cấp không đồng đều và cần lưu dạng document.
- Tách thành nhiều mảng một chiều ở các hàng khác nhau.

Không nên dựa vào PostgreSQL array đa chiều để lưu các mảng con “ragged” khác chiều dài.

### 9.3. Có phải mỗi chiều là một kiểu mảng khác nhau?

Không. `integer[]` và `integer[][]` sử dụng cùng ý tưởng **array type có kiểu phần tử integer**; số chiều của **giá trị** được xác định từ dữ liệu. PostgreSQL không tạo một “kiểu riêng chỉ chấp nhận mảng hai chiều 2×3” chỉ vì bạn viết `integer[2][3]` trong khai báo cột.

Hãy dùng `array_ndims()`, `array_length()` và constraint nếu schema nghiệp vụ yêu cầu hình dạng cụ thể.

### 9.4. Tổng số phần tử và số chiều

```sql
SELECT
    array_ndims('{{1,2,3},{4,5,6}}'::integer[]) AS dimensions,
    array_length('{{1,2,3},{4,5,6}}'::integer[], 1) AS dim1,
    array_length('{{1,2,3},{4,5,6}}'::integer[], 2) AS dim2,
    cardinality('{{1,2,3},{4,5,6}}'::integer[]) AS total;
```

Kết quả kỳ vọng: `2` chiều, kích thước `2×3`, tổng `6` phần tử.

## 10. Cập nhật phần tử mảng trong một cột

### 10.1. Gán lại một phần tử

Tạo bảng nhỏ để thực hành:

```sql
CREATE TABLE array_lab.test_scores (
    student_id bigint PRIMARY KEY,
    scores integer[] NOT NULL DEFAULT ARRAY[]::integer[]
);

INSERT INTO array_lab.test_scores(student_id, scores)
VALUES (101, ARRAY[75, 80, 85]);
```

Cập nhật phần tử thứ hai:

```sql
UPDATE array_lab.test_scores
SET scores[2] = 95
WHERE student_id = 101
RETURNING student_id, scores;
```

Giá trị từ `{75,80,85}` trở thành `{75,95,85}` theo thứ tự phần tử.

### 10.2. Gán giá trị toàn mảng

```sql
UPDATE array_lab.test_scores
SET scores = ARRAY[90, 91, 92, 93]
WHERE student_id = 101
RETURNING scores;
```

Câu này thay toàn bộ giá trị mảng bằng mảng mới có bốn phần tử. Không có quy tắc giới hạn độ dài từ `integer[]` nếu chưa thêm constraint.

### 10.3. Mở rộng mảng khi gán chỉ số xa

PostgreSQL có thể mở rộng một mảng **một chiều** khi gán phần tử ở vị trí ngoài cận, và những vị trí xen giữa có thể được điền NULL.

```sql
UPDATE array_lab.test_scores
SET scores = ARRAY[10,20,30]
WHERE student_id = 101;

UPDATE array_lab.test_scores
SET scores[5] = 50
WHERE student_id = 101
RETURNING scores;
```

Giá trị có thể trở thành:

```text
{10,20,30,NULL,50}
```

Đây là một lý do quan trọng để kiểm soát **độ dài và phần tử NULL** bằng validation/constraint nếu ứng dụng yêu cầu vector liên tục.

**Không suy luận rằng khả năng mở rộng chỉ số ngoài cận được hỗ trợ y hệt đối với mọi mảng nhiều chiều.** PostgreSQL có giới hạn với thao tác mở rộng và assignment trên multi-dimensional arrays.

### 10.4. Cập nhật có điều kiện và transaction

Nếu nhiều request sửa cùng một hàng, các cập nhật mảng đều ảnh hưởng bản ghi chứa mảng đó. Với ứng dụng thực tế, cần xử lý concurrency bằng transaction, điều kiện kiểm tra và/hoặc optimistic version.

Ví dụ:

```sql
UPDATE array_lab.test_scores
SET scores[2] = 98
WHERE student_id = 101
  AND scores[2] = 20
RETURNING student_id, scores;
```

Câu này chỉ cập nhật khi phần tử thứ hai đang có giá trị 20; kết quả `0 hàng` nghĩa là điều kiện không còn đúng hoặc bản ghi không tồn tại. Đây là một ví dụ cập nhật có điều kiện, không thay thế đầy đủ chiến lược quản lý đồng thời cho mọi use case.

## 11. Nối, thêm và thay phần tử mảng

PostgreSQL cung cấp hàm thao tác với mảng, đặc biệt thuận tiện cho mảng một chiều.

### 11.1. Thêm ở cuối và đầu

```sql
SELECT array_append(ARRAY[10,20], 30) AS appended;
SELECT array_prepend(5, ARRAY[10,20]) AS prepended;
```

Kết quả:

```text
array_append -> {10,20,30}
array_prepend -> {5,10,20}
```

Mỗi hàm tạo giá trị mảng mới; chúng không tự sửa cột trong bảng nếu bạn chưa dùng `UPDATE`.

Ví dụ cập nhật:

```sql
UPDATE array_lab.test_scores
SET scores = array_append(scores, 100)
WHERE student_id = 101
RETURNING scores;
```

Lệnh trên nối một phần tử vào cuối mảng hiện có. Nếu cần ngăn phần tử trùng, phải kiểm tra theo nghiệp vụ; `array_append` **không tự loại trùng**.

### 11.2. Nối hai mảng

```sql
SELECT ARRAY[1,2] || ARRAY[3,4] AS combined;
```

Kết quả: `{1,2,3,4}`.

Để nối một phần tử, cũng có thể dùng toán tử `||` trong các trường hợp kiểu tương thích, nhưng các biểu thức chứa literal chưa rõ kiểu có thể bị parser hiểu thành **mảng literal** thay vì một phần tử. Để tránh mơ hồ:

```sql
SELECT array_append(ARRAY[1,2], 3);
SELECT ARRAY[1,2] || ARRAY[3];
```

Cả hai rõ ràng hơn việc ghép mảng với một chuỗi text chưa cast kiểu.

### 11.3. `array_cat`

```sql
SELECT array_cat(
    ARRAY['sql','postgresql']::text[],
    ARRAY['jdbc','psql']::text[]
) AS combined_labels;
```

`array_cat` nối các mảng theo ngữ nghĩa số chiều tương thích. Với mảng đa chiều, quy tắc nối có thêm điều kiện về hình dạng và bounds; không nên mặc định nó giống nối hai danh sách phẳng trong mọi trường hợp.

### 11.4. Xóa hoặc thay mọi phần tử có một giá trị

```sql
SELECT array_remove(ARRAY[1,2,1,3], 1) AS removed;
SELECT array_replace(ARRAY[1,2,1,3], 1, 9) AS replaced;
```

Kết quả:

```text
array_remove  -> {2,3}
array_replace -> {9,2,9,3}
```

`array_remove` loại bỏ **tất cả** phần tử có giá trị được chọn, không chỉ phần tử đầu tiên. Hàm này được thiết kế cho mảng **một chiều**. Nếu cần thao tác vị trí hoặc xử lý ma trận, chọn phép biến đổi khác, không giả định hàm hoạt động tương tự cho mọi số chiều.

### 11.5. Tìm vị trí phần tử

```sql
SELECT array_position(ARRAY[5,10,5,20], 5) AS first_position;

SELECT array_positions(ARRAY[5,10,5,20], 5) AS all_positions;
```

Kết quả mong đợi:

```text
first_position = 1
all_positions  = {1,3}
```

Một ví dụ tìm phần tử NULL:

```sql
SELECT array_position(
    ARRAY[10,NULL,30]::integer[],
    NULL
) AS null_element_position;
```

Hàm tìm kiếm mảng trong PostgreSQL có thể xét phần tử NULL theo ngữ nghĩa so sánh *IS NOT DISTINCT FROM*, nên có thể tìm thấy vị trí NULL. `array_position`/`array_positions` dành cho mảng một chiều; không dùng để xác định tọa độ đa chiều.

## 12. Biến mảng thành các hàng với `unnest()`

Đây là một trong những thao tác quan trọng nhất khi kết hợp mảng với SQL quan hệ.

```sql
SELECT value
FROM unnest(ARRAY[10,20,30]) AS t(value);
```

Kết quả:

| value |
|---:|
| 10 |
| 20 |
| 30 |

Hàm `unnest()` mở một mảng thành **tập các hàng**. Điều này giúp join, filter, aggregate và xử lý từng phần tử bằng những công cụ SQL quen thuộc.

### 12.1. Giữ thứ tự bằng `WITH ORDINALITY`

```sql
SELECT
    u.label,
    u.ordinality
FROM unnest(
    ARRAY['sql','postgresql','java']::text[]
) WITH ORDINALITY AS u(label, ordinality)
ORDER BY u.ordinality;
```

Kết quả:

| label | ordinality |
|---|---:|
| sql | 1 |
| postgresql | 2 |
| java | 3 |

`WITH ORDINALITY` bổ sung một cột **thứ tự hàng do hàm sinh ra**, bắt đầu từ 1. Nếu mảng gốc có cận dưới đặc biệt như 0 hoặc -2, `ordinality` vẫn là số thứ tự các phần tử được phát ra, **không nhất thiết bằng subscript thật trong mảng gốc**.

### 12.2. `unnest()` với mảng nhiều chiều

```sql
SELECT value
FROM unnest(ARRAY[[1,2],[3,4]]) AS u(value);
```

Kết quả là các phần tử được mở thành một luồng một chiều theo thứ tự lưu trữ của mảng, thường quan sát được là 1, 2, 3, 4. Nếu muốn giữ **tọa độ hàng/cột**, chỉ dùng `unnest() WITH ORDINALITY` chưa đủ vì ordinality là số thứ tự phẳng.

### 12.3. Lấy chỉ số thật với `generate_subscripts()`

Ví dụ mảng một chiều có cận dưới 0:

```sql
WITH sample AS (
    SELECT '[0:2]={10,20,30}'::integer[] AS values
)
SELECT
    idx,
    values[idx] AS element_value
FROM sample
CROSS JOIN LATERAL generate_subscripts(values, 1) AS g(idx)
ORDER BY idx;
```

Kết quả:

| idx | element_value |
|---:|---:|
| 0 | 10 |
| 1 | 20 |
| 2 | 30 |

`generate_subscripts(a, dimension)` trả các chỉ số hợp lệ của một chiều, nên phù hợp khi cần xử lý bounds không chuẩn.

### 12.4. Tọa độ của mảng hai chiều

```sql
WITH sample AS (
    SELECT ARRAY[[1,2,3],[4,5,6]] AS matrix
)
SELECT
    row_idx,
    col_idx,
    matrix[row_idx][col_idx] AS element_value
FROM sample
CROSS JOIN LATERAL
    generate_subscripts(matrix, 1) AS r(row_idx)
CROSS JOIN LATERAL
    generate_subscripts(matrix, 2) AS c(col_idx)
ORDER BY row_idx, col_idx;
```

Kết quả:

```text
row_idx | col_idx | element_value
--------+---------+--------------
      1 |       1 | 1
      1 |       2 | 2
      1 |       3 | 3
      2 |       1 | 4
      2 |       2 | 5
      2 |       3 | 6
```

Dùng mẫu này khi phân tích một ma trận cần tọa độ; dùng `unnest()` khi chỉ cần mọi phần tử như một tập hợp phẳng.

## 13. Gom các hàng thành mảng với `array_agg()`

Hướng ngược lại của `unnest()` thường là `array_agg()`.

### 13.1. Gom điểm thành một mảng

Giả sử bảng quan hệ ghi từng lần đo:

```sql
CREATE TABLE array_lab.measurements (
    sensor_id bigint NOT NULL,
    measured_at timestamptz NOT NULL,
    temperature numeric(6,2) NOT NULL,
    PRIMARY KEY (sensor_id, measured_at)
);
```

Dữ liệu mẫu:

```sql
INSERT INTO array_lab.measurements
    (sensor_id, measured_at, temperature)
VALUES
    (1, '2026-11-14 09:00:00+07', 28.50),
    (1, '2026-11-14 09:05:00+07', 28.80),
    (1, '2026-11-14 09:10:00+07', 29.10),
    (2, '2026-11-14 09:00:00+07', 25.00);
```

Gom theo sensor:

```sql
SELECT
    sensor_id,
    array_agg(temperature ORDER BY measured_at) AS temperatures
FROM array_lab.measurements
GROUP BY sensor_id
ORDER BY sensor_id;
```

`ORDER BY measured_at` **nằm trong aggregate** để xác định thứ tự phần tử trong mảng kết quả. Không nên mặc định `array_agg` sẽ gom theo thứ tự thời gian nếu không có chỉ định.

### 13.2. Gom phần tử không trùng

```sql
SELECT array_agg(DISTINCT label ORDER BY label) AS distinct_labels
FROM unnest(
    ARRAY['sql','java','sql','postgresql']::text[]
) AS t(label);
```

Kết quả là tập nhãn không trùng theo thứ tự xác định. Đây là phép biến đổi **khi truy vấn**, không phải ràng buộc khiến cột mảng trong bảng luôn loại trùng.

### 13.3. Aggregate trên tập rỗng

Một điểm rất dễ bỏ qua: giống nhiều aggregate khác, `array_agg()` trên tập **không có hàng** thường trả `NULL`, không tự trả mảng rỗng.

```sql
SELECT array_agg(value) AS result
FROM unnest(ARRAY[]::integer[]) AS u(value);
```

Nếu API yêu cầu luôn trả mảng, dùng:

```sql
SELECT COALESCE(
    array_agg(value ORDER BY value),
    ARRAY[]::integer[]
) AS result
FROM unnest(ARRAY[]::integer[]) AS u(value);
```

Khi dữ liệu được dùng trong JSON/API, việc phân biệt `NULL` và `[]` cần được thống nhất trong hợp đồng ứng dụng.

### 13.4. `ARRAY(SELECT ...)`

Một cách tạo mảng từ subquery:

```sql
SELECT ARRAY(
    SELECT temperature
    FROM array_lab.measurements
    WHERE sensor_id = 1
    ORDER BY measured_at
) AS temperatures;
```

Khác với `array_agg()` khi không có hàng, constructor `ARRAY(SELECT ...)` có thể tạo một **mảng rỗng** phù hợp khi subquery không trả hàng. Cả hai đều hữu ích; lựa chọn tùy cách bạn muốn xử lý `NULL`/mảng rỗng và ngữ nghĩa query.

## 14. Tìm phần tử: `ANY`, `ALL` và toán tử mảng

### 14.1. So sánh với mọi phần tử bằng `ANY`

Tìm xem `20` có xuất hiện trong mảng:

```sql
SELECT 20 = ANY(ARRAY[10,20,30]) AS contains_20;
```

Kết quả: `true`.

Với cột `labels`:

```sql
SELECT example_id
FROM array_lab.examples
WHERE 'postgresql' = ANY(labels);
```

`ANY` cho phép một phép so sánh được thử với các phần tử mảng. Khi có NULL, giá trị chân lý ba trạng thái của SQL (TRUE/FALSE/UNKNOWN) có thể ảnh hưởng kết quả, nên tránh suy luận rằng mọi phép kiểm tra `ANY` luôn trả một boolean không NULL trong mọi trường hợp.

### 14.2. So sánh với tất cả phần tử bằng `ALL`

```sql
SELECT 10 < ALL(ARRAY[20,30,40]) AS less_than_all;
```

Kết quả: `true`.

`ALL` không có nghĩa “mảng chứa mọi nhãn cần tìm”. Nó là phép **so sánh một biểu thức với từng phần tử**. Ví dụ `10 < ALL(...)` yêu cầu 10 nhỏ hơn mọi phần tử.

Với mảng rỗng, các toán tử `ANY`/`ALL` có quy tắc logic riêng (so sánh không có phần tử nào thỏa vs không có phần tử nào vi phạm), nên kiểm tra rõ ngữ nghĩa khi dùng cho điều kiện nghiệp vụ.

### 14.3. Toán tử bao hàm `@>` và `<@`

PostgreSQL cung cấp:

| Toán tử | Nghĩa | Ví dụ |
|---|---|---|
| `a @> b` | `a` chứa các phần tử của `b` | `ARRAY[1,2,3] @> ARRAY[2,3]` |
| `a <@ b` | `a` được chứa trong `b` | `ARRAY[2] <@ ARRAY[1,2,3]` |
| `a && b` | Hai mảng có ít nhất một phần tử chung | `ARRAY[1,2] && ARRAY[2,4]` |
| `a = b` | Hai giá trị mảng bằng nhau theo quy tắc so sánh mảng | `ARRAY[1,2] = ARRAY[1,2]` |

Ví dụ:

```sql
SELECT
    ARRAY[1,2,3] @> ARRAY[2,3] AS contains_all,
    ARRAY[2,3] <@ ARRAY[1,2,3] AS is_contained,
    ARRAY[1,2] && ARRAY[2,4] AS overlaps,
    ARRAY[1,2] = ARRAY[1,2] AS equals;
```

Các kết quả trên đều là `true`.

### 14.4. Khác biệt giữa bao hàm và tập hợp toán học

Trong toán tử bao hàm của PostgreSQL, **số lần lặp của một phần tử không được xem như số lượng bản sao cần khớp**. Chẳng hạn:

```sql
SELECT
    ARRAY[1] @> ARRAY[1,1] AS contains_duplicates,
    ARRAY[1,1] @> ARRAY[1] AS reverse_contains;
```

Cả hai có thể là `true`, vì toán tử này quan tâm sự hiện diện của phần tử, không bảo đảm khớp đa tập có đếm số lần xuất hiện.

Nếu yêu cầu nghiệp vụ là “số 1 phải xuất hiện ít nhất hai lần”, `@> ARRAY[1,1]` không kiểm tra đúng. Cần đếm phần tử bằng `unnest()`/aggregation hoặc thiết kế cấu trúc dữ liệu phù hợp.

### 14.5. Tìm nhãn theo nhiều điều kiện

Giả sử bảng dự án có cột `labels text[]`.

Chứa **tất cả** nhãn chỉ định:

```sql
SELECT project_id, project_name
FROM array_lab.projects
WHERE labels @> ARRAY['postgresql','backend']::text[];
```

Có **ít nhất một** nhãn:

```sql
SELECT project_id, project_name
FROM array_lab.projects
WHERE labels && ARRAY['postgresql','java']::text[];
```

Hai truy vấn diễn đạt hai điều kiện khác nhau. `@>` là “có đủ các phần tử yêu cầu”, còn `&&` là “giao nhau không rỗng”.

## 15. Chỉ mục GIN cho mảng

Với vài hàng dữ liệu, quét bảng có thể đủ nhanh. Khi bảng có nhiều hàng và truy vấn thường xuyên kiểm tra chứa/chồng lấp, PostgreSQL có thể sử dụng **GIN index** (*Generalized Inverted Index*).

### 15.1. Bảng dự án có nhãn

```sql
CREATE TABLE array_lab.projects (
    project_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_name text NOT NULL,
    labels text[] NOT NULL DEFAULT ARRAY[]::text[],
    CONSTRAINT labels_at_most_12
        CHECK (cardinality(labels) <= 12)
);
```

Thêm dữ liệu:

```sql
INSERT INTO array_lab.projects(project_name, labels)
VALUES
    ('Tối ưu truy vấn', ARRAY['postgresql','backend','performance']),
    ('Ứng dụng Java', ARRAY['java','backend']),
    ('Báo cáo dữ liệu', ARRAY['postgresql','reporting']),
    ('Thiết kế API', ARRAY[]::text[]);
```

Ở bảng này, `labels` không được NULL và có tối đa 12 phần tử, nhưng ràng buộc hiện tại **chưa** cấm phần tử NULL hoặc nhãn trùng lặp.

### 15.2. Tạo GIN index

```sql
CREATE INDEX idx_projects_labels_gin
ON array_lab.projects
USING gin (labels);
```

Với operator class mảng mặc định hỗ trợ, GIN thường có thể hỗ trợ những toán tử như:

- `@>`: chứa.
- `<@`: được chứa.
- `&&`: giao nhau.
- `=`: bằng nhau, theo khả năng operator class.

Ví dụ:

```sql
SELECT project_id, project_name
FROM array_lab.projects
WHERE labels @> ARRAY['postgresql']::text[];
```

Có thể kiểm tra kế hoạch trên lab:

```sql
EXPLAIN
SELECT project_id, project_name
FROM array_lab.projects
WHERE labels @> ARRAY['postgresql']::text[];
```

**Không kỳ vọng mọi truy vấn đều chọn GIN index.** Với bảng nhỏ, PostgreSQL có thể thấy sequential scan rẻ hơn. Quyết định còn phụ thuộc thống kê, độ chọn lọc, số lượng phần tử, cấu hình và chi phí của thao tác ghi.

### 15.3. Khi nào GIN hữu ích và khi nào không?

| Truy vấn hoặc workload | Điều nên cân nhắc |
|---|---|
| Tìm hàng có nhãn X bằng `labels @> ARRAY['X']` | GIN thường là ứng viên phù hợp |
| Tìm hàng có ít nhất một trong X/Y bằng `labels && ARRAY[...]` | GIN có thể hữu ích |
| Lọc theo `'X' = ANY(labels)` | Không mặc định tương đương về cách tận dụng GIN; cân nhắc rewrite dùng `@>` |
| Tra cứu theo `project_id` | Primary key B-tree thường phù hợp hơn |
| Cập nhật mảng liên tục, mảng rất dài | GIN có chi phí cập nhật/lưu trữ; cần đo |
| Truy vấn số lượng nhãn hoặc truy cập theo vị trí | Không mặc định GIN sẽ tối ưu điều kiện này |
| Cần báo cáo/join dữ liệu từng nhãn | Bảng quan hệ chuẩn hóa thường tốt hơn |

Một mảng quá dài có thể khiến hàng và chỉ mục trở nên đắt đỏ. **GIN không phải lý do để đưa toàn bộ quan hệ một-nhiều vào một cột mảng** khi các phần tử cần được cập nhật độc lập.

## 16. NULL, mảng rỗng và ràng buộc cho mảng trong schema

### 16.1. Các ràng buộc cơ bản

Ví dụ một hệ thống cho phép mỗi bài viết có từ 0 đến 8 nhãn:

```sql
CREATE TABLE array_lab.articles (
    article_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    tags text[] NOT NULL DEFAULT ARRAY[]::text[],
    CHECK (cardinality(tags) BETWEEN 0 AND 8)
);
```

Ý nghĩa:

- Không cho **toàn bộ mảng** NULL.
- Mặc định là mảng rỗng kiểu text.
- Tối đa 8 **phần tử**, kể cả phần tử NULL nếu không có ràng buộc khác.

Nếu nghiệp vụ yêu cầu “ít nhất một nhãn”, có thể dùng `cardinality(tags) BETWEEN 1 AND 8`, nhưng cần nhớ ràng buộc này không tự cấm phần tử NULL.

### 16.2. Kiểm tra phần tử NULL trong mảng một chiều

Với mảng một chiều, có thể dùng `array_position(a, NULL)` để tìm vị trí phần tử NULL:

```sql
SELECT
    array_position(ARRAY['a',NULL,'c']::text[], NULL)
        AS null_position,
    array_position(ARRAY['a','b','c']::text[], NULL)
        AS no_null_position;
```

Nếu `no_null_position` là NULL thì không tìm thấy phần tử NULL trong mảng một chiều đó. Trong thiết kế constraint cho dữ liệu phức tạp, cần đồng thời xét **số chiều**, kiểu phần tử và tình huống mảng rỗng. Các hàm tìm kiếm vị trí có giới hạn số chiều, nên đừng áp dụng một constraint dùng `array_position` cho giá trị đa chiều mà không kiểm soát đầu vào.

### 16.3. Ràng buộc hình dạng một chiều

Nếu nghiệp vụ yêu cầu giá trị rỗng hoặc mảng một chiều:

```sql
CREATE TABLE array_lab.one_dimensional_vectors (
    vector_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    numbers integer[] NOT NULL DEFAULT ARRAY[]::integer[],
    CONSTRAINT only_empty_or_one_dimension
        CHECK (
            cardinality(numbers) = 0
            OR array_ndims(numbers) = 1
        )
);
```

Điều kiện cho phép mảng rỗng và các mảng một chiều. Nếu còn yêu cầu cận dưới phải là 1:

```sql
ALTER TABLE array_lab.one_dimensional_vectors
ADD CONSTRAINT one_based_or_empty
CHECK (
    cardinality(numbers) = 0
    OR array_lower(numbers, 1) = 1
);
```

Đây là lựa chọn khi ứng dụng cần cách đánh chỉ số cố định. Trong môi trường thật, cần cân nhắc dữ liệu đã tồn tại trước khi thêm constraint.

### 16.4. Phần tử trùng lặp là vấn đề riêng

`integer[]` có thể chứa `{1,1,2}`. `text[]` có thể chứa hai lần cùng nhãn. PostgreSQL không có ràng buộc `UNIQUE` **cho từng phần tử trong một cột array** tương đương `UNIQUE` trên các hàng của bảng liên kết.

Nếu tính duy nhất của từng phần tử là ràng buộc quan trọng và số phần tử không nhỏ, một bảng con với `UNIQUE(parent_id, element_value)` thường rõ ràng, dễ kiểm soát và tiện tìm kiếm hơn.

## 17. So sánh mảng với mô hình một-nhiều dùng bảng con

Giả sử mỗi dự án có nhiều nhãn.

### 17.1. Cách dùng mảng

```sql
CREATE TABLE array_lab.projects_simple (
    project_id bigint PRIMARY KEY,
    project_name text NOT NULL,
    labels text[] NOT NULL DEFAULT ARRAY[]::text[]
);
```

Ưu điểm:

- Ít bảng.
- Đọc toàn bộ danh sách nhãn của một dự án rất thuận tiện.
- Phù hợp nhóm nhãn nhỏ, ít cập nhật, không có metadata riêng.
- Có GIN cho tìm kiếm các nhãn theo một số toán tử.

Nhược điểm:

- Không có foreign key trực tiếp trên **từng phần tử** của mảng tới một bảng `tags`.
- Khó quản lý metadata như ai gắn nhãn, lúc nào hoặc trọng số của từng nhãn.
- Khó enforce unique mỗi phần tử như một constraint quan hệ đơn giản.
- Cập nhật một phần tử thường làm thay đổi giá trị mảng của bản ghi cha, có thể tạo tranh chấp khi nhiều thao tác đồng thời.
- Khi mảng rất dài, dung lượng, TOAST, index và chi phí ghi có thể tăng.

### 17.2. Cách chuẩn hóa bằng bảng liên kết

```sql
CREATE TABLE array_lab.projects_normalized (
    project_id bigint PRIMARY KEY,
    project_name text NOT NULL
);

CREATE TABLE array_lab.tags (
    tag_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tag_name text NOT NULL UNIQUE
);

CREATE TABLE array_lab.project_tags (
    project_id bigint NOT NULL
        REFERENCES array_lab.projects_normalized(project_id),
    tag_id bigint NOT NULL
        REFERENCES array_lab.tags(tag_id),
    added_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, tag_id)
);
```

Ưu điểm:

- Foreign key trên mỗi liên kết.
- Primary key ngăn gắn trùng một tag vào cùng project.
- Có thể lưu metadata cho liên kết.
- Truy vấn/join/aggregate theo tag dễ hơn khi cần báo cáo phức tạp.
- Cập nhật một liên kết mà không phải thay toàn mảng.

Đổi lại, việc đọc danh sách nhãn có thể cần join hoặc `array_agg()` để đóng gói cho API.

### 17.3. Chọn cách nào?

| Đặc điểm dữ liệu | Mảng | Bảng liên kết |
|---|---|---|
| Dãy giá trị nhỏ, thường đọc/ghi cùng bản ghi | Phù hợp | Có thể quá phức tạp |
| Phần tử có metadata riêng | Khó | Phù hợp |
| Cần foreign key cho từng phần tử | Không trực tiếp | Phù hợp |
| Cần unique cho từng phần tử | Phải kiểm soát thêm | `PRIMARY KEY/UNIQUE` rõ ràng |
| Cần cập nhật phần tử độc lập với cạnh tranh cao | Cân nhắc chi phí ghi hàng cha | Thường tốt hơn |
| Cần lọc "có nhãn X" | GIN có thể phù hợp | Index trên bảng liên kết cũng phù hợp |
| Cần tổng hợp, đếm, join theo phần tử thường xuyên | Có thể dùng `unnest` nhưng tốn chuyển đổi | Tự nhiên theo SQL quan hệ |
| Số lượng phần tử có thể rất lớn | Cần cẩn trọng | Thường dễ mở rộng và bảo trì hơn |

**Quy tắc thiết kế:** dùng mảng khi một danh sách nhỏ thực sự là **một thuộc tính dạng tập hợp** của hàng; dùng bảng con khi từng phần tử là **một thực thể hoặc một mối quan hệ có vòng đời riêng**.

## 18. Mảng, JSONB và kiểu dữ liệu khác

PostgreSQL có nhiều cấu trúc lưu tập hợp, cần phân biệt:

| Kiểu | Đặc điểm | Khi phù hợp |
|---|---|---|
| `integer[]`, `text[]` | Các phần tử cùng kiểu; có chiều, chỉ số và toán tử mảng | Dãy số, nhãn đơn giản |
| `jsonb` | Cấu trúc JSON linh hoạt, có object và array lồng nhau, kiểu phần tử có thể khác nhau | Payload bán cấu trúc, cấu hình linh hoạt |
| Bảng con | Các hàng có khóa, ràng buộc, chỉ mục riêng | Quan hệ một-nhiều quan trọng |
| Range types | Biểu diễn khoảng như `int4range`/`tstzrange` | Khoảng giá trị, lịch thời gian |
| `hstore` (extension) | Key-value text | Một số dữ liệu thuộc tính động đơn giản |

Ví dụ:

```sql
SELECT
    ARRAY[10,20,30]::integer[] AS typed_array,
    '[10,20,"thirty"]'::jsonb AS heterogeneous_json;
```

`integer[]` giữ kiểu phần tử integer. JSONB có thể trộn số và chuỗi, nhưng cơ chế chỉ mục, truy vấn và ràng buộc sẽ khác.

Một JSON array có thể chứa các mảng con độ dài khác nhau, còn mảng PostgreSQL nhiều chiều yêu cầu hình dạng phù hợp. Không nên ép dữ liệu JSON không đồng nhất sang `integer[][]` chỉ vì đều hiển thị bằng dấu ngoặc.

## 19. Dùng mảng làm tham số cho truy vấn an toàn

### 19.1. Tìm nhiều ID bằng `ANY($1)`

Giả sử ứng dụng cần lấy những công việc có ID trong danh sách người dùng được phép truy cập:

```sql
SELECT project_id, project_name
FROM array_lab.projects
WHERE project_id = ANY($1::bigint[]);
```

`$1` là tham số của PostgreSQL trong prepared statement/driver, **không phải biến đã có sẵn khi chạy trực tiếp trong psql**. Cần bind một giá trị kiểu `bigint[]` thật sự.

Với một danh sách ID hợp lệ, cách này thường tránh việc ứng dụng tạo chuỗi SQL `IN (1,2,3,...)` bằng nối text không được kiểm soát.

### 19.2. Ví dụ Java/JDBC với PostgreSQL array

Đoạn Java rút gọn, giả sử đã có `java.sql.Connection connection` và dependency pgJDBC:

```java
import java.sql.Array;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class ArrayQueryExample {
    public static void findProjects(Connection connection)
            throws SQLException {

        String sql = """
            SELECT project_id, project_name
            FROM array_lab.projects
            WHERE labels @> ?::text[]
            ORDER BY project_id
            """;

        Array labels = connection.createArrayOf(
            "text",
            new String[] {"postgresql"}
        );

        try {
            try (PreparedStatement statement =
                     connection.prepareStatement(sql)) {
                statement.setArray(1, labels);

                try (ResultSet rs = statement.executeQuery()) {
                    while (rs.next()) {
                        System.out.println(
                            rs.getLong("project_id")
                            + ": "
                            + rs.getString("project_name")
                        );
                    }
                }
            }
        } finally {
            labels.free();
        }
    }
}
```

Đây là ví dụ dùng **Java 15+ text blocks**; việc cấu hình datasource, connection pool, exception handling cấp ứng dụng và quyền database không nằm trong đoạn code.

Ý nghĩa:

- `createArrayOf("text", ...)` tạo đối tượng JDBC `Array` phù hợp.
- `setArray(...)` bind vào một prepared statement thay vì tự xây dựng literal kiểu `'{...}'`.
- SQL cast `?::text[]` giúp nêu rõ kiểu tham số.
- Chuỗi nhãn được truyền như dữ liệu, không bị nối vào SQL.
- Tài nguyên statement, result set và JDBC Array được giải phóng phù hợp.

Nếu cần lấy giá trị mảng từ kết quả:

```java
Array sqlArray = rs.getArray("labels");
if (sqlArray != null) {
    try {
        String[] labels = (String[]) sqlArray.getArray();
        // Sử dụng các phần tử của mảng.
    } finally {
        sqlArray.free();
    }
}
```

Đoạn trên là minh họa trong ngữ cảnh có `ResultSet rs` đang mở; kiểu Java cụ thể của `getArray()` phụ thuộc kiểu SQL và driver. Với `integer[]`, có thể nhận wrapper array hoặc cấu trúc phù hợp; không mặc định ép mọi kiểu PostgreSQL array thành `String[]`.

### 19.3. Mảng SQL và Java array không có cùng chỉ số

Java array thường đánh chỉ số từ **0**:

```java
String[] values = {"A", "B", "C"};
String first = values[0];
```

Trong PostgreSQL, mảng tạo bằng `ARRAY['A','B','C']` thường có phần tử đầu tại `[1]`. Khi chuyển qua driver, cần hiểu cách mapping sang mảng Java để tránh lỗi lệch chỉ số.

Ngoài ra, thứ tự phần tử là một thuộc tính của array, nhưng khi biến thành các hàng SQL rồi aggregate trở lại, cần `ORDER BY` rõ để bảo toàn thứ tự mong muốn.

## 20. Hiệu năng và giới hạn khi mảng tăng lớn

### 20.1. Một phần tử thay đổi vẫn thuộc cùng hàng

Khi cập nhật `labels` của một dự án, PostgreSQL thực hiện một bản ghi cập nhật cho hàng chứa mảng theo cơ chế MVCC. Mảng có thể được lưu cùng hàng hoặc sử dụng TOAST khi giá trị lớn; thao tác không đồng nghĩa sửa đúng một byte của một file đơn giản.

Do đó, nếu hai transaction cùng liên tục thêm nhãn vào **cùng một project row**, chúng có thể tranh chấp trên hàng đó. Chọn bảng liên kết khi cần cập nhật các phần tử độc lập với tần suất cao.

### 20.2. Mảng dài không tự được tối ưu vì chỉ có một cột

Khi có hàng nghìn phần tử trong một cột:

- Kết quả SELECT chứa mảng lớn có thể tiêu thụ băng thông.
- Update mảng có thể tạo phiên bản hàng mới và ảnh hưởng TOAST/WAL.
- GIN index có thể tăng kích thước và chi phí cập nhật.
- Một số thao tác `unnest`, lọc, sort và aggregate có chi phí đáng kể.
- Index và thống kê có thể cần được điều chỉnh theo workload.

Mảng có giới hạn kích thước giá trị và dữ liệu cột theo kiến trúc PostgreSQL; không nên dùng nó để nhét một tập dữ liệu khổng lồ chỉ vì không bị giới hạn bởi `integer[3]`. Các yêu cầu lưu hàng triệu phần tử thường cần đánh giá bảng quan hệ, partitioning, hệ lưu trữ chuyên biệt hoặc mô hình thích hợp hơn.

### 20.3. Đo bằng `EXPLAIN`

```sql
EXPLAIN
SELECT project_id
FROM array_lab.projects
WHERE labels && ARRAY['postgresql','java']::text[];
```

Nếu có quyền và dữ liệu lab, có thể xem chi tiết thực thi bằng:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT project_id
FROM array_lab.projects
WHERE labels && ARRAY['postgresql','java']::text[];
```

`EXPLAIN ANALYZE` **thực thi câu truy vấn**; với SELECT trong lab thì thường an toàn, nhưng không chạy trên các câu UPDATE/DELETE gây thay đổi production nếu chưa có quy trình bảo vệ. Kết quả thời gian/plan phụ thuộc môi trường và số liệu thực tế.

## 21. Một số lỗi thường gặp

### 21.1. Nhầm `integer[3]` thành giới hạn ba phần tử

Khai báo kích thước trong kiểu mảng không được thực thi như constraint. Nếu phải có đúng ba điểm, dùng `CHECK (cardinality(scores) = 3)` và các điều kiện hình dạng/phần tử phù hợp.

### 21.2. Dùng chỉ số 0 cho mọi mảng

`ARRAY[10,20,30]` mặc định bắt đầu từ 1. `a[0]` thường trả NULL, không phải phần tử đầu. Nhưng mảng có lower bound 0 cũng tồn tại, nên hãy xem `array_lower()` khi cần tổng quát.

### 21.3. Dùng `array_length(a,1) = 0` để kiểm tra mảng rỗng

Với mảng rỗng, `array_length(...,1)` trả NULL, nên so sánh với 0 không cho kết quả đúng. Dùng `cardinality(a) = 0` nếu muốn kiểm tra mảng rỗng không NULL.

### 21.4. Không phân biệt NULL và `{}`

`NULL::text[]` là chưa có giá trị mảng; `'{}'::text[]` là mảng rỗng. Chọn ngữ nghĩa rõ và dùng `NOT NULL DEFAULT ARRAY[]::text[]` nếu luôn muốn mảng tồn tại.

### 21.5. Tưởng `NOT NULL` cấm phần tử NULL

`labels text[] NOT NULL` không cấm `ARRAY['sql',NULL]`. Nếu phần tử NULL là sai nghiệp vụ, kiểm soát rõ bằng schema/validation phù hợp.

### 21.6. Viết mảng hai chiều không đều

`ARRAY[[1,2,3],[4,5]]` không có hình dạng ma trận hợp lệ. PostgreSQL yêu cầu các phần tương ứng trong multi-dimensional array có độ dài nhất quán.

### 21.7. Tưởng `@>` đếm số lần lặp phần tử

`ARRAY[1] @> ARRAY[1,1]` có thể là TRUE. Toán tử containment không bảo đảm đếm duplicate. Dùng phép đếm phần tử thật khi cần multiplicity.

### 21.8. Quên thứ tự khi dùng `array_agg()`

Không có `ORDER BY` nằm trong aggregate, thứ tự phần tử không được bảo đảm theo ý định nghiệp vụ. Dùng `array_agg(value ORDER BY timestamp_or_position)`.

### 21.9. Tưởng `unnest() WITH ORDINALITY` trả subscript gốc

`ordinality` đánh số từ 1 theo thứ tự xuất hiện, không nhất thiết trùng lower bound của mảng gốc. Dùng `generate_subscripts()` nếu cần chỉ số thực.

### 21.10. Quên `tenant_id` hoặc khóa liên kết khi gom mảng

Trong hệ thống đa tenant, việc `array_agg` toàn bộ nhãn hoặc ID mà không lọc theo tenant có thể gom nhầm dữ liệu từ nhiều tổ chức. Mảng là kiểu dữ liệu, **không phải cơ chế phân quyền**. RLS, điều kiện `WHERE` và các ràng buộc vẫn cần thiết.

### 21.11. Chọn kiểu mảng cho quan hệ cần khóa ngoại mỗi phần tử

Ví dụ `customer_ids bigint[]` không tự có foreign key áp cho từng ID trong mảng. Nếu cần bảo đảm từng customer tồn tại và thuộc đúng tenant, bảng liên kết có FK rõ ràng thường tốt hơn.

### 21.12. Đổi `text[]` sang JSONB mà không đổi ngữ nghĩa query

Mảng SQL và JSON array có ngữ nghĩa element type, index, operator và dữ liệu NULL khác nhau. Cần điều chỉnh query/constraint khi thay mô hình, không chỉ cast tùy tiện để dập lỗi.

### 21.13. Dùng `'x' = ANY(labels)` rồi kỳ vọng luôn dùng GIN

GIN thường hỗ trợ tốt nhiều toán tử mảng như `@>`, `<@`, `&&`. Planner không nhất thiết dùng index tương tự cho một biểu thức scalar = ANY. Cần xem kế hoạch truy vấn và chọn predicate/index phù hợp.

## 22. Bài thực hành tổng hợp

Phần này dùng một database **lab** mà role có quyền tạo schema/bảng; không chạy trên production.

### Bước 1: Tạo bảng chứa mảng nhãn

```sql
CREATE SCHEMA IF NOT EXISTS array_lab;

CREATE TABLE array_lab.work_items (
    work_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    tags text[] NOT NULL DEFAULT ARRAY[]::text[],
    effort_estimates integer[] NOT NULL DEFAULT ARRAY[]::integer[],
    CHECK (cardinality(tags) <= 10),
    CHECK (cardinality(effort_estimates) <= 5)
);
```

Bảng gồm hai kiểu mảng:

- `tags text[]`: dãy nhãn.
- `effort_estimates integer[]`: dãy số giờ công ước tính cho các vòng lập kế hoạch.

Cả hai mặc định là mảng rỗng nhưng hiện chưa có ràng buộc chặn trùng lặp hay phần tử NULL.

### Bước 2: Chèn dữ liệu

```sql
INSERT INTO array_lab.work_items(title, tags, effort_estimates)
VALUES
    (
        'Tối ưu truy vấn báo cáo',
        ARRAY['postgresql','sql','performance']::text[],
        ARRAY[8,6,5]
    ),
    (
        'Tạo API mới',
        ARRAY['java','api']::text[],
        ARRAY[12,10]
    ),
    (
        'Cập nhật tài liệu',
        ARRAY[]::text[],
        ARRAY[3]
    )
RETURNING work_id, title, tags, effort_estimates;
```

### Bước 3: Đếm và truy cập phần tử

```sql
SELECT
    work_id,
    title,
    tags[1] AS first_tag,
    cardinality(tags) AS tag_count,
    array_length(effort_estimates,1) AS estimates_count,
    effort_estimates[1] AS first_estimate
FROM array_lab.work_items
ORDER BY work_id;
```

Với hàng tài liệu có mảng nhãn rỗng:

- `first_tag` trả NULL.
- `tag_count` bằng 0.
- Mảng effort có một phần tử 3.

### Bước 4: Thêm nhãn

```sql
UPDATE array_lab.work_items
SET tags = array_append(tags, 'review')
WHERE title = 'Cập nhật tài liệu'
RETURNING title, tags;
```

Vì `array_append` không tự kiểm tra trùng, chạy hai lần sẽ có thể thêm hai nhãn `review`. Khi nghiệp vụ cần nhãn unique, ứng dụng phải xử lý riêng hoặc dùng bảng liên kết.

### Bước 5: Tìm những công việc liên quan PostgreSQL

```sql
SELECT work_id, title, tags
FROM array_lab.work_items
WHERE tags @> ARRAY['postgresql']::text[]
ORDER BY work_id;
```

Nếu có nhiều dữ liệu và thường xuyên truy vấn theo nhãn, có thể thêm:

```sql
CREATE INDEX idx_work_items_tags_gin
ON array_lab.work_items USING gin(tags);
```

### Bước 6: Biến tags thành các hàng

```sql
SELECT
    w.work_id,
    w.title,
    tag.tag_value,
    tag.ordinality
FROM array_lab.work_items AS w
CROSS JOIN LATERAL
    unnest(w.tags) WITH ORDINALITY AS tag(tag_value, ordinality)
ORDER BY w.work_id, tag.ordinality;
```

Mỗi phần tử nhãn trở thành một hàng. Với mảng rỗng, `CROSS JOIN LATERAL unnest(...)` không tạo hàng cho work item đó. Nếu muốn giữ cả work item không có nhãn, cân nhắc `LEFT JOIN LATERAL ... ON true`.

### Bước 7: Gom trở lại mảng có thứ tự

```sql
SELECT
    work_id,
    array_agg(tag_value ORDER BY ordinality) AS rebuilt_tags
FROM (
    SELECT
        w.work_id,
        tag.tag_value,
        tag.ordinality
    FROM array_lab.work_items AS w
    CROSS JOIN LATERAL
        unnest(w.tags) WITH ORDINALITY
        AS tag(tag_value, ordinality)
) AS exploded
GROUP BY work_id
ORDER BY work_id;
```

Những work item không có nhãn không xuất hiện trong kết quả này vì subquery không tạo hàng tương ứng. Nếu API phải trả mọi work item, dùng `LEFT JOIN LATERAL` và xử lý tập rỗng/NULL phù hợp.

### Bước 8: Quan sát mảng hai chiều

```sql
SELECT
    array_ndims(ARRAY[[1,2,3],[4,5,6]]) AS dimensions,
    array_length(ARRAY[[1,2,3],[4,5,6]], 1) AS rows_count,
    array_length(ARRAY[[1,2,3],[4,5,6]], 2) AS columns_count,
    cardinality(ARRAY[[1,2,3],[4,5,6]]) AS total_elements;
```

Kỳ vọng: 2 chiều, 2 hàng, 3 cột và 6 phần tử.

### Bước 9: So sánh mảng rỗng với NULL

```sql
SELECT
    cardinality(ARRAY[]::text[]) AS empty_count,
    array_length(ARRAY[]::text[],1) AS empty_length,
    cardinality(NULL::text[]) AS null_count,
    ARRAY[]::text[] IS NULL AS empty_is_null,
    NULL::text[] IS NULL AS null_is_null;
```

Kỳ vọng:

```text
empty_count  = 0
empty_length = NULL
null_count   = NULL
empty_is_null = false
null_is_null  = true
```

### Bước 10: Xem kế hoạch truy vấn

```sql
EXPLAIN
SELECT work_id, title
FROM array_lab.work_items
WHERE tags && ARRAY['postgresql','java']::text[];
```

Với dữ liệu mẫu rất nhỏ, PostgreSQL có thể chọn sequential scan dù đã tạo GIN index. Điều đó không có nghĩa index bị lỗi; cần dữ liệu và thống kê đại diện trước khi đánh giá hiệu quả thực sự.

## 23. Câu hỏi và bài tập có lời giải

### Bài 1. `integer[4]` có tự giới hạn 4 phần tử?

Cho:

```sql
CREATE TABLE array_lab.demo_size (
    numbers integer[4]
);
```

**Câu hỏi:** có thể lưu mảng 5 phần tử không?

**Lời giải:** có thể, vì con số `4` trong khai báo kiểu array không phải giới hạn được PostgreSQL thực thi. Nếu yêu cầu chính xác 4 phần tử, dùng constraint như `CHECK (cardinality(numbers) = 4)` kết hợp `NOT NULL` và điều kiện hình dạng phù hợp.

### Bài 2. Mảng này có bao nhiêu phần tử?

```sql
SELECT cardinality(ARRAY[[10,20,30],[40,50,60]]);
```

**Lời giải:** 6. Đây là ma trận 2×3, nên tổng số phần tử là 2 nhân 3, không phải 2 hay 3.

### Bài 3. Phần tử đầu có phải luôn là `a[1]`?

Cho:

```sql
SELECT '[0:2]={10,20,30}'::integer[];
```

**Lời giải:** không. Mảng này bắt đầu tại 0; phần tử đầu là `a[0]`. Dùng `array_lower(a,1)` để xác định cận dưới, không mặc định 1 trong mọi nguồn dữ liệu.

### Bài 4. Vì sao kiểm tra mảng rỗng bằng `array_length = 0` sai?

```sql
SELECT array_length(ARRAY[]::text[],1);
```

**Lời giải:** hàm trả NULL cho chiều không tồn tại/không có phần tử. Dùng `cardinality(a) = 0` khi `a` là mảng không NULL.

### Bài 5. Tìm cả hai nhãn

Bạn có cột `labels text[]`, muốn lấy những bản ghi có cả `postgresql` và `backend`.

**Lời giải:**

```sql
SELECT *
FROM array_lab.projects
WHERE labels @> ARRAY['postgresql','backend']::text[];
```

Nếu chỉ cần ít nhất một trong hai nhãn, dùng `&&` thay vì `@>`.

### Bài 6. Mảng có phần tử NULL có phải mảng NULL?

```sql
SELECT ARRAY[1,NULL,3]::integer[];
```

**Lời giải:** không. Mảng không NULL có ba phần tử, phần tử thứ hai là NULL. Cột `NOT NULL` không ngăn tình huống đó.

### Bài 7. `array_agg()` có bảo đảm thứ tự không?

Một bảng chứa các điểm đo với thời gian tương ứng.

**Lời giải:** không nên dựa vào thứ tự ngẫu nhiên của rows. Dùng:

```sql
SELECT array_agg(temperature ORDER BY measured_at)
FROM array_lab.measurements
WHERE sensor_id = 1;
```

Cú pháp `ORDER BY` nằm bên trong aggregate để sắp xếp phần tử mảng.

### Bài 8. Mảng hai chiều lệch hàng

```sql
SELECT ARRAY[[1,2,3],[4,5]];
```

**Lời giải:** không hợp lệ cho multi-dimensional array hình chữ nhật. Cần các sub-array có hình dạng tương thích, ví dụ `ARRAY[[1,2,3],[4,5,6]]`.

### Bài 9. Có nên lưu hàng nghìn order ID trong `customer.orders bigint[]`?

**Lời giải:** thường không. Đơn hàng là thực thể có nhiều thuộc tính, trạng thái, mối quan hệ, khóa ngoại và vòng đời cập nhật độc lập. Nên tạo bảng `orders` có `customer_id` tham chiếu khách hàng. Mảng có thể phù hợp cho dãy giá trị nhỏ kèm một record nhưng không thay thế mô hình quan hệ nhiều thực thể.

### Bài 10. Có thể dùng foreign key cho từng phần tử trong `member_ids uuid[]`?

**Lời giải:** PostgreSQL không cung cấp cú pháp foreign key thông thường áp riêng cho từng phần tử của một cột array như với một cột scalar. Nếu tính toàn vẹn tham chiếu là yêu cầu bắt buộc, nên dùng bảng liên kết `project_members(project_id, member_id)` với foreign keys thích hợp.

### Bài 11. `unnest WITH ORDINALITY` và `generate_subscripts` khác nhau thế nào?

**Lời giải:** `unnest WITH ORDINALITY` tạo dòng theo thứ tự phần tử kèm ordinal bắt đầu từ 1; `generate_subscripts(a,n)` trả các **subscript hợp lệ thực tế** của chiều `n`, kể cả mảng có cận dưới 0 hay âm. Với ma trận cần tọa độ, dùng `generate_subscripts` từng chiều.

### Bài 12. Vì sao thêm GIN mà planner vẫn quét bảng?

**Lời giải:** với bảng nhỏ hoặc điều kiện kém chọn lọc, sequential scan có thể rẻ hơn. GIN cũng không phù hợp mọi toán tử và workload. Dùng `EXPLAIN` cùng dữ liệu đại diện, đo chi phí index khi ghi và xem lại thống kê.

## 24. Bảng ghi nhớ nhanh

| Nhu cầu | Cú pháp PostgreSQL | Ghi chú |
|---|---|---|
| Khai báo mảng số nguyên | `numbers integer[]` | Kiểu phần tử là integer |
| Khai báo mảng text | `labels text[]` | Dùng được với GIN cho một số toán tử |
| Constructor một chiều | `ARRAY[1,2,3]` | Thường chỉ số từ 1 |
| Constructor hai chiều | `ARRAY[[1,2],[3,4]]` | Hình dạng chữ nhật |
| Mảng rỗng | `ARRAY[]::integer[]` | Cần kiểu phần tử |
| Array literal | `'{1,2,3}'::integer[]` | Cú pháp text có quy tắc escape |
| Truy cập phần tử | `a[2]` | Ngoài cận thường trả NULL |
| Slice | `a[2:4]` | Trả mảng con |
| Đếm chiều | `array_ndims(a)` | Số chiều thực của giá trị |
| Độ dài chiều 1 | `array_length(a,1)` | Mảng rỗng trả NULL |
| Tổng phần tử | `cardinality(a)` | Mảng rỗng trả 0 |
| Cận chỉ số | `array_lower(a,1)`, `array_upper(a,1)` | Không mặc định 1 trong mọi trường hợp |
| Mô tả bounds | `array_dims(a)` | Ví dụ `[1:2][1:3]` |
| Tạo mảng có bounds | `array_fill(7, ARRAY[3], ARRAY[0])` | Độ dài 3, bắt đầu ở 0 |
| Thêm cuối | `array_append(a, x)` | Không tự loại trùng |
| Thêm đầu | `array_prepend(x, a)` | Với mảng phù hợp |
| Nối mảng | `a || b` hoặc `array_cat(a,b)` | Cần kiểu/hình dạng tương thích |
| Xóa giá trị | `array_remove(a,x)` | Loại mọi lần xuất hiện trong mảng 1D |
| Thay giá trị | `array_replace(a,old,new)` | Thay các phần tử khớp |
| Tìm vị trí | `array_position(a,x)` | Mảng một chiều |
| Mở thành rows | `unnest(a)` | Các phần tử thành tập hàng |
| Giữ thứ tự mở mảng | `unnest(a) WITH ORDINALITY` | Ordinal từ 1, không nhất thiết là subscript |
| Lấy chỉ số thật | `generate_subscripts(a,1)` | Tôn trọng lower/upper bounds |
| Gom thành mảng | `array_agg(x ORDER BY y)` | Chỉ định thứ tự rõ |
| Có giá trị x? | `x = ANY(a)` | Chú ý NULL và phép so sánh |
| Chứa mọi giá trị | `a @> b` | Không đếm số lần lặp |
| Có phần tử chung | `a && b` | Có thể hỗ trợ GIN |
| Tạo GIN index | `CREATE INDEX ... USING gin (labels)` | Dùng với operator phù hợp |
| Ràng buộc độ dài | `CHECK (cardinality(a) <= 10)` | Cú pháp `integer[10]` không tự enforce |
| Mặc định mảng rỗng | `NOT NULL DEFAULT ARRAY[]::text[]` | Không cấm phần tử NULL |
| Foreign key trên mỗi phần tử | Thường chọn bảng liên kết | Array không thay FK quan hệ |

## 25. Tổng kết: hiểu đúng kiểu phần tử và kích thước thực

Có ba lớp kiến thức cần luôn tách bạch khi sử dụng array trong PostgreSQL:

**Thứ nhất, kiểu phần tử.** `integer[]`, `text[]`, `uuid[]`... mô tả những giá trị mà mảng có thể chứa. Mảng thường gồm các phần tử cùng kiểu hoặc có thể chuyển về một kiểu chung. Mảng chứa `NULL` vẫn có thể là một giá trị mảng không NULL.

**Thứ hai, hình dạng thực tế.** Mỗi mảng có số chiều, chiều dài và bounds phụ thuộc giá trị. Khai báo `integer[3]` hoặc `integer[2][3]` **không tự áp ràng buộc** lên độ dài/số chiều. Dùng `array_ndims`, `array_length`, `cardinality`, `array_lower`, `array_upper` và `array_dims` để hiểu dữ liệu, kết hợp `CHECK` khi nghiệp vụ đòi cấu trúc cụ thể.

**Thứ ba, lựa chọn mô hình.** Các hàm `unnest`, `array_agg`, `array_append`, các toán tử `@>`/`&&` và GIN index khiến array rất hữu ích cho danh sách nhỏ trong một hàng. Nhưng khi phần tử cần foreign key, tính duy nhất riêng, metadata, quyền hoặc cập nhật độc lập, bảng quan hệ chuẩn hóa thường phù hợp hơn.

Nắm chắc ba điều này sẽ giúp bạn tránh lỗi chỉ số, độ dài, NULL, thao tác đa chiều và thiết kế dữ liệu khó bảo trì, đồng thời tận dụng hiệu quả các kiểu mảng mạnh mẽ của PostgreSQL.


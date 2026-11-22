# Chia số nguyên, chia thập phân và phép chia lấy dư

Phép chia xuất hiện thường xuyên trong truy vấn SQL: tính tỷ lệ hoàn thành, giá trung bình trên một sản phẩm, số thùng hàng đóng được, số món còn dư hoặc xác định một mã là chẵn hay lẻ. Tuy nhiên, câu lệnh trông giống nhau có thể cho kết quả rất khác nhau tùy **kiểu dữ liệu của toán hạng**, **toán tử được dùng** và **hệ quản trị cơ sở dữ liệu**.

Trong PostgreSQL, biểu thức `5 / 2` trả về **2** vì hai toán hạng đều là số nguyên, còn `5.0 / 2` trả về **2.5** vì phép tính sử dụng kiểu số thập phân. Nếu muốn phần dư, dùng `5 % 2` để nhận **1**. Đó là ba ý tưởng cốt lõi của bài học **Database SQL → Biểu thức và hàm** này.

Bài học sử dụng **PostgreSQL** để thực hành thống nhất. Các hệ quản trị như MySQL, SQL Server, SQLite và Oracle có những khác biệt đáng kể, được phân biệt ở phần cuối. Khi chuyển ví dụ sang hệ khác, đừng suy luận rằng toán tử `/` luôn trả về cùng một kiểu và cùng kết quả.

## 1. Ba kiểu kết quả cần phân biệt

Với hai số nguyên dương `a = 11` và `b = 4`:

| Nhu cầu | Ví dụ PostgreSQL | Giá trị | Diễn giải |
| --- | --- | ---: | --- |
| Lấy **thương nguyên** | `11 / 4` | 2 | Có 2 nhóm đầy đủ, mỗi nhóm 4 đơn vị |
| Lấy **thương thập phân** | `11::numeric / 4` | 2.75 | Tỷ số chính xác theo phép chia số thập phân |
| Lấy **phần dư** | `11 % 4` | 3 | Sau 2 nhóm đầy đủ còn 3 đơn vị |

Hai giá trị **thương nguyên** và **phần dư** liên hệ với nhau bằng đẳng thức:

\[
11 = 4 \times 2 + 3
\]

Trong ví dụ có số dương, ta cũng có `0 <= 3 < 4`. Biết cả thương nguyên lẫn phần dư giúp trả lời câu hỏi “đóng được bao nhiêu thùng đầy và còn thừa bao nhiêu món?”. Thương thập phân giải quyết một câu hỏi khác: “11 so với 4 là tỷ số bao nhiêu?”.

**Điểm cần nhớ:** trong nhiều hệ quản trị, ký hiệu `/` không tự quyết định kết quả là số nguyên hay số thập phân. **Kiểu dữ liệu tham gia phép chia** cũng ảnh hưởng kết quả.

## 2. Chuẩn bị dữ liệu để thực hành

Trong database PostgreSQL dùng riêng cho bài thực hành, hãy tạo bảng `lab_division_batches_138`. Đoạn sau dành cho **lần chạy đầu tiên**, khi bảng chưa tồn tại:

~~~sql
CREATE TABLE lab_division_batches_138 (
    batch_id INTEGER PRIMARY KEY,
    finished_count INTEGER NOT NULL CHECK (finished_count >= 0),
    planned_count INTEGER NOT NULL CHECK (planned_count >= 0),
    item_count INTEGER NOT NULL CHECK (item_count >= 0),
    box_capacity INTEGER NOT NULL CHECK (box_capacity >= 0)
);

INSERT INTO lab_division_batches_138
    (batch_id, finished_count, planned_count, item_count, box_capacity)
VALUES
    (1, 3, 8, 11, 4),
    (2, 5, 5, 18, 6),
    (3, 0, 0,  0, 0),
    (4, 2, 3,  9, 4),
    (5, 1, 2,  5, 2);
~~~

Các cột có ý nghĩa như sau:

- `finished_count`: số công việc đã hoàn thành trong một đợt.
- `planned_count`: số công việc đã dự kiến trong đợt đó.
- `item_count`: số món hàng cần đóng gói.
- `box_capacity`: sức chứa của một thùng, tính bằng số món.

Bảng cố ý có một dòng `batch_id = 3` với `planned_count = 0` và `box_capacity = 0` để minh họa **mẫu số bằng 0**. Trong một hệ thống đóng gói thực tế, sức chứa bằng 0 thường là dữ liệu không hợp lệ và cần quy tắc như `CHECK (box_capacity > 0)`. Ở bài học này, dữ liệu đó được cho phép chỉ để quan sát cách SQL xử lý.

Xem dữ liệu khởi tạo:

~~~sql
SELECT
    batch_id,
    finished_count,
    planned_count,
    item_count,
    box_capacity
FROM lab_division_batches_138
ORDER BY batch_id;
~~~

| batch_id | finished_count | planned_count | item_count | box_capacity |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 3 | 8 | 11 | 4 |
| 2 | 5 | 5 | 18 | 6 |
| 3 | 0 | 0 | 0 | 0 |
| 4 | 2 | 3 | 9 | 4 |
| 5 | 1 | 2 | 5 | 2 |

Các ví dụ bên dưới đều chỉ đọc dữ liệu. Không cần thực hiện thao tác `UPDATE` hoặc `DELETE` để hiểu phép chia.

## 3. Chia số nguyên trong PostgreSQL

### 3.1. Hai toán hạng nguyên tạo thương nguyên

~~~sql
SELECT
    11 / 4 AS a,
    10 / 2 AS b,
    3 / 8 AS c;
~~~

Kết quả:

| a | b | c |
| ---: | ---: | ---: |
| 2 | 5 | 0 |

PostgreSQL có các toán tử chia được lựa chọn theo kiểu toán hạng. Khi cả hai toán hạng là số nguyên như `INTEGER`, phép chia nguyên **bỏ phần lẻ của thương bằng cách cắt về 0** (*truncation toward zero*).

Vì vậy:

- `11 / 4 = 2`, không phải 2.75.
- `10 / 2 = 5`, vì phép chia hết.
- `3 / 8 = 0`, vì thương thật nằm giữa 0 và 1.

Đây không phải lỗi làm tròn hiển thị. **Phần thập phân đã bị loại trong chính phép tính**.

### 3.2. Kiểm tra kiểu của biểu thức

PostgreSQL hỗ trợ hàm `pg_typeof(...)` để xem kiểu kết quả:

~~~sql
SELECT
    pg_typeof(11 / 4) AS int_expression_type,
    pg_typeof(11.0 / 4) AS decimal_expression_type;
~~~

Đối với ví dụ này, `11 / 4` có kiểu `integer` và `11.0 / 4` có kiểu `numeric`. Hàm `pg_typeof` là chức năng của PostgreSQL, không phải cú pháp SQL chuẩn dùng chung cho mọi hệ quản trị.

Lưu ý: số nguyên rất lớn có thể là `BIGINT` hoặc một kiểu số khác; không nên cho rằng mọi phép chia giữa các cột tên `count` đều có kiểu `INTEGER`. Hãy kiểm tra kiểu thật của cột và biểu thức.

### 3.3. Trường hợp thương âm

Với PostgreSQL, phép chia số nguyên cắt về **0**, không phải luôn làm tròn xuống theo trục số:

~~~sql
SELECT
    -5 / 2  AS negative_left,
     5 / -2 AS negative_right,
    -5 / -2 AS both_negative;
~~~

| negative_left | negative_right | both_negative |
| ---: | ---: | ---: |
| -2 | -2 | 2 |

Ví dụ `-5 / 2` có thương toán học là `-2.5`; cắt về 0 cho `-2`, còn lấy `FLOOR(-2.5)` cho `-3`. Hai thao tác **khác nhau** khi kết quả âm.

Không dùng `FLOOR(a / b)` trên biểu thức đã chia nguyên để “khôi phục” phần lẻ: ở thời điểm gọi `FLOOR`, phần lẻ đã mất.

## 4. Chia thập phân: giữ phần lẻ khi cần tính tỷ lệ

### 4.1. Chuyển ít nhất một toán hạng sang NUMERIC

Trong PostgreSQL, chỉ cần ít nhất một toán hạng có kiểu thập phân phù hợp để phép chia nhận kiểu thập phân:

~~~sql
SELECT
    11.0 / 4 AS literal_decimal,
    CAST(11 AS NUMERIC) / 4 AS cast_function,
    11::numeric / 4 AS postgres_cast,
    11 / 4.0 AS decimal_denominator;
~~~

Bốn biểu thức đều có **giá trị toán học 2.75**. Dạng chữ số được hiển thị có thể khác nhau tùy kiểu, độ chính xác và công cụ SQL.

Hai cách chuyển kiểu thông dụng:

~~~sql
-- CAST: cu phap SQL pho bien.
CAST(11 AS NUMERIC)

-- :: la cu phap ep kieu ngan cua PostgreSQL.
11::numeric
~~~

`NUMERIC` (hoặc `DECIMAL` trong nhiều ngữ cảnh) phù hợp với các phép tính cần phần thập phân có kiểm soát, chẳng hạn tỷ lệ và số tiền. Kiểu `DOUBLE PRECISION` cũng hỗ trợ chia ra phần lẻ, nhưng là kiểu dấu phẩy động nhị phân, có thể có sai số biểu diễn đối với một số phân số thập phân.

### 4.2. CAST phải diễn ra **trước** phép chia

So sánh hai biểu thức dễ bị nhầm:

~~~sql
SELECT
    CAST(11 / 4 AS NUMERIC(10, 2)) AS cast_after_division,
    CAST(11 AS NUMERIC(10, 2)) / 4 AS cast_before_division;
~~~

Giá trị:

| cast_after_division | cast_before_division |
| ---: | ---: |
| 2.00 | 2.75 |

Biểu thức đầu thực hiện `11 / 4` thành **2** rồi mới đổi **2** sang kiểu số thập phân. Biểu thức sau đổi `11` thành số thập phân trước khi chia nên vẫn giữ phần lẻ.

Sơ đồ:

~~~text
CAST(11 / 4 AS NUMERIC)       CAST(11 AS NUMERIC) / 4
      |                                  |
      v                                  v
  11 / 4 -> 2                      11.0 / 4 -> 2.75
      |                                  |
      v                                  v
  2 -> 2.00                           2.75

Sau khi thuong nguyen da mat phan le, CAST khong phuc hoi duoc.
~~~

### 4.3. Viết số có dấu chấm thập phân

Trong ví dụ PostgreSQL:

~~~sql
SELECT 3 / 8 AS integer_result,
       3.0 / 8 AS decimal_result;
~~~

`3 / 8` trả về **0**; `3.0 / 8` trả về **0.375**.

Ở PostgreSQL, literal `3.0` được suy ra là `NUMERIC`. Với ứng dụng gửi tham số từ Java/JDBC hoặc một ORM, kiểu của **tham số thực tế** mới là điều cần kiểm tra. Đừng chỉ thay cách hiển thị giá trị ở giao diện rồi giả định phía database đã dùng phép chia thập phân.

### 4.4. Tính tỷ lệ phần trăm

Một sai lầm phổ biến:

~~~sql
SELECT 100 * 3 / 8 AS percent_wrong;
~~~

Trong PostgreSQL, cả ba toán hạng đều nguyên. Phép nhân tạo `300`, sau đó `300 / 8` lấy thương nguyên, cho **37**. Đáp số đúng về mặt tỷ lệ là **37.5%**.

Viết:

~~~sql
SELECT
    100.0 * 3 / 8 AS percent_decimal,
    ROUND(100.0 * 3 / 8, 2) AS percent_rounded;
~~~

Cả hai có giá trị **37.5**, và cột `percent_rounded` được làm tròn về hai chữ số thập phân (thường hiển thị `37.50`).

Khi tính tỷ lệ, nên đưa phép tính vào miền số thập phân **từ trước lần chia đầu tiên**.

## 5. Chia lấy dư bằng toán tử % và hàm MOD

### 5.1. Phần dư là gì?

Trong phép chia số nguyên dương, thương nguyên `q` và phần dư `r` thỏa:

\[
a = b \times q + r,\quad 0 \le r < b \;(b>0)
\]

Ví dụ:

\[
11 = 4 \times 2 + 3
\]

Trong PostgreSQL:

~~~sql
SELECT
    11 / 4 AS whole_groups,
    11 % 4 AS remaining_items;
~~~

Kết quả là **2 nhóm đầy** và **3 đơn vị còn lại**.

Toán tử `%` trả về **phần dư**, không phải ký hiệu phần trăm trong SQL. Để đổi một tỷ lệ sang phần trăm, thường dùng phép nhân `* 100`; viết `%` trong SQL là một phép toán khác.

### 5.2. Cách dùng MOD

PostgreSQL còn có hàm `mod(a, b)`:

~~~sql
SELECT
    11 % 4 AS remainder_operator,
    MOD(11, 4) AS remainder_function;
~~~

Cả hai trả về **3**. Với kiểu `NUMERIC`, PostgreSQL cũng hỗ trợ tính phần dư có phần thập phân:

~~~sql
SELECT MOD(11.5::numeric, 4::numeric) AS decimal_remainder;
~~~

Kết quả là **3.5**, vì `11.5 = 4 × 2 + 3.5`. Không phải mọi hệ quản trị cho phép `%` hoạt động giống hệt với mọi kiểu số thập phân; nên dùng cú pháp được tài liệu hệ quản trị đó hỗ trợ.

### 5.3. Kiểm tra chẵn/lẻ

Với mã nguyên không âm:

~~~sql
SELECT
    12 % 2 AS even_remainder,
    13 % 2 AS odd_remainder;
~~~

Kết quả `12 % 2 = 0`, `13 % 2 = 1`. Từ đó:

~~~sql
SELECT batch_id, item_count
FROM lab_division_batches_138
WHERE item_count % 2 = 0
ORDER BY batch_id;
~~~

Các đợt có `item_count` chẵn là **2** (18 món) và **3** (0 món). Số 0 là số chẵn theo định nghĩa toán học vì chia hết cho 2.

### 5.4. Chia công việc thành chu kỳ

Nếu muốn gắn số thứ tự chu kỳ từ `0` đến `3` cho các `batch_id` dương, có thể dùng:

~~~sql
SELECT
    batch_id,
    (batch_id - 1) % 4 AS cycle_index
FROM lab_division_batches_138
ORDER BY batch_id;
~~~

| batch_id | cycle_index |
| ---: | ---: |
| 1 | 0 |
| 2 | 1 |
| 3 | 2 |
| 4 | 3 |
| 5 | 0 |

Vòng lặp lặp lại sau mỗi bốn ID. Cách phân nhóm theo phần dư là **một ví dụ kỹ thuật**, không tự bảo đảm các nhóm có cùng tải thực tế hoặc có cùng số hàng khi dữ liệu phân bố không đều.

## 6. Phần dư với số âm: cẩn thận dấu của kết quả

Trong PostgreSQL, phép chia nguyên **cắt về 0** và phần dư giữ **dấu của số bị chia** (khi khác 0). Ví dụ:

~~~sql
SELECT
    -5 / 2 AS q1,
    -5 % 2 AS r1,
     5 / -2 AS q2,
     5 % -2 AS r2,
    -5 / -2 AS q3,
    -5 % -2 AS r3;
~~~

Kết quả trong PostgreSQL:

| Phép chia | Thương nguyên | Phần dư | Kiểm tra |
| --- | ---: | ---: | --- |
| `-5 / 2` và `-5 % 2` | -2 | -1 | `(-2) × 2 + (-1) = -5` |
| `5 / -2` và `5 % -2` | -2 | 1 | `(-2) × (-2) + 1 = 5` |
| `-5 / -2` và `-5 % -2` | 2 | -1 | `2 × (-2) + (-1) = -5` |

Kết quả này khác một số ngôn ngữ lập trình hoặc định nghĩa modulo toán học luôn yêu cầu phần dư không âm. Nếu bạn dùng phần dư để tạo chỉ số mảng hay phân nhóm chu kỳ, hãy xác định liệu số âm có thể xuất hiện hay không.

Với **số chia dương** `b`, khi muốn chuẩn hóa phần dư về khoảng `0 ... b-1` trên PostgreSQL, có thể dùng biểu thức:

~~~sql
SELECT MOD(MOD(-5, 4) + 4, 4) AS normalized_remainder;
~~~

Kết quả là **3**. Đó là một **quy tắc chuẩn hóa** chủ động; không phải kết quả trực tiếp của `-5 % 4` trong PostgreSQL, vốn là `-1`.

## 7. Mẫu số bằng 0: lỗi và cách xử lý bằng NULLIF

Trong PostgreSQL, phép chia cho 0 gây lỗi:

~~~sql
-- SAI: khong the chia cho 0.
SELECT 5 / 0;
~~~

Tương tự, phần dư với số chia bằng 0 cũng không hợp lệ:

~~~sql
-- SAI: mau so cua phep MOD bang 0.
SELECT 5 % 0;
~~~

Trong thực tế, mẫu số có thể lấy từ một cột dữ liệu. Nếu chỉ một hàng có mẫu số 0, câu `SELECT` tính chia trên toàn bộ bảng có thể bị lỗi, khiến bạn không nhận được các kết quả còn lại.

### 7.1. Dùng NULLIF để tránh chia cho 0

`NULLIF(x, y)` trả về `NULL` nếu `x` bằng `y`; ngược lại trả về `x`. Vì vậy:

~~~sql
SELECT
    5 / NULLIF(0, 0) AS safe_integer_division,
    5.0 / NULLIF(0, 0) AS safe_decimal_division,
    5 % NULLIF(0, 0) AS safe_remainder;
~~~

Cả ba biểu thức trả về **`NULL`**, thay vì gây lỗi chia cho 0. Khi mẫu số khác 0, `NULLIF(mau_so, 0)` trả lại mẫu số để phép chia diễn ra như bình thường.

**Quan trọng:** `NULLIF` chỉ ngăn lỗi mẫu số 0. Nó **không tự chuyển chia nguyên thành chia thập phân**:

~~~sql
SELECT
    3 / NULLIF(8, 0) AS still_integer,
    3.0 / NULLIF(8, 0) AS decimal_result;
~~~

Kết quả tương ứng là **0** và **0.375**. Nếu cần tỷ lệ, phải xử lý cả **kiểu dữ liệu** và **mẫu số 0**.

### 7.2. Có nên thay NULL bằng 0?

Có thể dùng `COALESCE` để thay `NULL` trong kết quả:

~~~sql
SELECT
    COALESCE(5.0 / NULLIF(0, 0), 0) AS fallback_value;
~~~

Kết quả là **0**, nhưng điều này không có nghĩa tỷ số thật bằng 0. Trong toán học và nhiều nghiệp vụ, phép chia cho 0 là **không xác định**. Nếu ứng dụng quy ước “chưa đủ dữ liệu thì hiển thị 0%”, hãy ghi rõ quy ước đó; nếu không, giữ `NULL` hoặc hiển thị nhãn “Chưa xác định” sẽ tránh đánh đồng dữ liệu thiếu với kết quả bằng 0.

### 7.3. Ngăn mẫu số bằng 0 từ khâu thiết kế bảng

Nếu quy tắc nghiệp vụ nói sức chứa thùng **luôn phải dương**, nên định nghĩa:

~~~sql
box_capacity INTEGER NOT NULL CHECK (box_capacity > 0)
~~~

Đây là **đoạn định nghĩa cột**, không phải câu SQL hoàn chỉnh. Nó có thể được đặt trong `CREATE TABLE` thích hợp. Bảng thực hành ở mục 2 cố ý dùng `box_capacity >= 0` để quan sát dữ liệu lỗi; bảng sản xuất có thể cần ràng buộc chặt hơn.

Chỉ đổi ràng buộc sau khi đã kiểm tra và xử lý các hàng không hợp lệ đang có. Không nên tự sửa 0 thành 1 nếu “sức chứa 1 món” không phải dữ liệu đúng về nghiệp vụ.

## 8. Áp dụng vào bài toán đóng gói: thương, dư và số thùng cần dùng

Giả sử mỗi thùng chứa tối đa `box_capacity` món. Ta cần phân biệt:

- **Số thùng đầy**: thương nguyên của `item_count / box_capacity`.
- **Số món còn lại**: phần dư `item_count % box_capacity`.
- **Tổng số thùng cần để chứa hết**: nếu có món còn dư thì cần thêm một thùng, nghĩa là phải **làm tròn lên** thương thập phân.

### 8.1. Số thùng đầy và hàng còn dư

~~~sql
SELECT
    batch_id,
    item_count,
    box_capacity,
    item_count / NULLIF(box_capacity, 0) AS full_boxes,
    item_count % NULLIF(box_capacity, 0) AS leftover_items
FROM lab_division_batches_138
ORDER BY batch_id;
~~~

Kết quả:

| batch_id | item_count | box_capacity | full_boxes | leftover_items |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 11 | 4 | 2 | 3 |
| 2 | 18 | 6 | 3 | 0 |
| 3 | 0 | 0 | `NULL` | `NULL` |
| 4 | 9 | 4 | 2 | 1 |
| 5 | 5 | 2 | 2 | 1 |

Đối với đợt 1, `11 / 4 = 2` và `11 % 4 = 3`: có thể đóng **2 thùng đầy**, còn **3 món**. Đợt 2 chia hết, nên không có món dư. Đợt 3 có sức chứa 0 và không thể xác định được cách đóng gói hợp lệ, vì thế biểu thức trả về `NULL`.

### 8.2. Khi cần tổng số thùng, hãy làm tròn lên

Nếu đóng cả hàng còn dư vào một thùng cuối, số thùng cần dùng khác số thùng **đầy**:

~~~sql
SELECT
    batch_id,
    item_count,
    box_capacity,
    CEIL(item_count::numeric / NULLIF(box_capacity, 0)) AS required_boxes
FROM lab_division_batches_138
ORDER BY batch_id;
~~~

Kết quả dự kiến:

| batch_id | required_boxes |
| ---: | ---: |
| 1 | 3 |
| 2 | 3 |
| 3 | `NULL` |
| 4 | 3 |
| 5 | 3 |

`CEIL(...)` (*ceiling*) làm tròn **lên số nguyên gần nhất** đối với thương thập phân. Ví dụ `11 / 4` có thương số thực 2.75, nên cần 3 thùng. Nếu lấy `11 / 4` theo phép chia nguyên rồi mới gọi `CEIL`, kết quả vẫn là 2 và sẽ **thiếu thùng**.

Lưu ý: công thức trên giả định các món có cùng loại, có thể xếp tối đa đúng `box_capacity` món/thùng và không có ràng buộc kích thước/trọng lượng khác. Bài toán đóng gói thực tế có thể phức tạp hơn.

## 9. Áp dụng vào tỷ lệ hoàn thành

Một tỷ lệ hoàn thành có dạng:

\[
\text{Tỷ lệ hoàn thành (\%)} =
\frac{\text{số công việc hoàn thành}}{\text{số công việc dự kiến}} \times 100
\]

Nếu hai cột đều là `INTEGER` và viết:

~~~sql
SELECT
    batch_id,
    finished_count / NULLIF(planned_count, 0) AS ratio_wrong
FROM lab_division_batches_138
ORDER BY batch_id;
~~~

Thương nguyên của đợt 1 là **0**, dù thực tế đã hoàn thành 3/8 công việc. Đợt 4 là `2 / 3 = 0`; đợt 5 là `1 / 2 = 0`. Chỉ có đợt 2 trả về 1, vì 5/5 chia hết.

### 9.1. Đưa phép tính sang số thập phân ngay từ đầu

~~~sql
SELECT
    batch_id,
    finished_count,
    planned_count,
    ROUND(
        100.0 * finished_count / NULLIF(planned_count, 0),
        2
    ) AS completion_percent
FROM lab_division_batches_138
ORDER BY batch_id;
~~~

Kết quả:

| batch_id | finished_count | planned_count | completion_percent |
| ---: | ---: | ---: | ---: |
| 1 | 3 | 8 | 37.50 |
| 2 | 5 | 5 | 100.00 |
| 3 | 0 | 0 | `NULL` |
| 4 | 2 | 3 | 66.67 |
| 5 | 1 | 2 | 50.00 |

Giải thích:

1. `100.0` là literal kiểu `NUMERIC` trong PostgreSQL, nên phép nhân/chia sau đó sử dụng số thập phân.
2. `NULLIF(planned_count, 0)` trả về `NULL` cho đợt 3, tránh lỗi mẫu số bằng 0.
3. `ROUND(..., 2)` làm tròn kết quả số thập phân đến hai chữ số sau dấu chấm.
4. Với đợt 4, `2 / 3` là tỷ số 0.6666...; nhân 100 cho 66.6666... rồi làm tròn thành **66.67%**.

Nếu muốn cột là tỷ số `0...1` thay vì phần trăm, bỏ phép nhân 100:

~~~sql
SELECT
    batch_id,
    ROUND(
        finished_count::numeric / NULLIF(planned_count, 0),
        4
    ) AS completion_ratio
FROM lab_division_batches_138
ORDER BY batch_id;
~~~

Với đợt 1, kết quả là **0.3750**; đợt 4 là **0.6667**. Quy tắc định dạng số phần trăm trên giao diện phải nhất quán: đừng nhân 100 ở SQL rồi lại nhân 100 thêm lần nữa ở tầng giao diện.

### 9.2. Tỷ lệ tổng hợp: SUM trước hay AVG từng tỷ lệ?

Nếu muốn tỷ lệ hoàn thành **trên tổng tất cả công việc**, hãy chia tổng số việc hoàn thành cho tổng số việc dự kiến:

~~~sql
SELECT
    ROUND(
        100.0 * SUM(finished_count)
        / NULLIF(SUM(planned_count), 0),
        2
    ) AS overall_completion_percent
FROM lab_division_batches_138;
~~~

Với dữ liệu mẫu, tổng hoàn thành là `3 + 5 + 0 + 2 + 1 = 11`, tổng dự kiến là `8 + 5 + 0 + 3 + 2 = 18`. Tỷ lệ tổng là **61.11%**.

Điều này khác với việc tính trung bình đơn giản các tỷ lệ từng đợt: mỗi đợt có số công việc dự kiến khác nhau, nên một đợt nhỏ không nên tự động có trọng số ngang đợt lớn khi câu hỏi là **tỷ lệ trên toàn bộ công việc**.

Một sai lầm khác là ép kiểu sau khi đã tính tổng và **đã chia nguyên**:

~~~sql
-- SAI neu can ty le thap phan:
SELECT CAST(SUM(finished_count) / SUM(planned_count) AS NUMERIC)
FROM lab_division_batches_138;
~~~

`SUM` của cột nguyên có thể cho kết quả kiểu nguyên lớn; chia hai giá trị kiểu nguyên trong PostgreSQL vẫn có thể làm mất phần lẻ. Hãy chuyển một vế sang `NUMERIC` trước phép chia hoặc nhân với literal `100.0` như truy vấn tỷ lệ ở trên.

## 10. ROUND, TRUNC, FLOOR và CEIL khác phép chia nguyên

Một thương có phần thập phân không phải lúc nào cũng cần hiển thị nguyên vẹn. PostgreSQL cung cấp các hàm xử lý kết quả:

~~~sql
SELECT
    11::numeric / 4 AS exact_quotient,
    ROUND(11::numeric / 4, 1) AS rounded_one_digit,
    TRUNC(11::numeric / 4, 1) AS truncated_one_digit,
    FLOOR(11::numeric / 4) AS floor_value,
    CEIL(11::numeric / 4) AS ceiling_value;
~~~

| Biểu thức | Kết quả | Ý nghĩa |
| --- | ---: | --- |
| `11::numeric / 4` | 2.75 | Thương thập phân |
| `ROUND(11::numeric / 4, 1)` | 2.8 | Làm tròn đến 1 chữ số thập phân |
| `TRUNC(11::numeric / 4, 1)` | 2.7 | Cắt bớt phần thập phân còn 1 chữ số |
| `FLOOR(11::numeric / 4)` | 2 | Số nguyên lớn nhất không vượt quá 2.75 |
| `CEIL(11::numeric / 4)` | 3 | Số nguyên nhỏ nhất không nhỏ hơn 2.75 |

Với số âm, khác biệt rõ hơn:

~~~sql
SELECT
    -5 / 2 AS integer_division,
    TRUNC(-5::numeric / 2) AS truncate_decimal,
    FLOOR(-5::numeric / 2) AS floor_decimal,
    CEIL(-5::numeric / 2) AS ceiling_decimal;
~~~

| integer_division | truncate_decimal | floor_decimal | ceiling_decimal |
| ---: | ---: | ---: | ---: |
| -2 | -2 | -3 | -2 |

**Phép chia nguyên** là hành vi của toán tử `/` với hai toán hạng nguyên trong PostgreSQL; `ROUND`, `TRUNC`, `FLOOR` và `CEIL` là những thao tác riêng trên một giá trị đã được tính. Không nên dùng lẫn chúng khi yêu cầu chính xác “làm tròn gần nhất”, “làm tròn xuống” hay “lấy số nhóm đầy”.

### Độ chính xác NUMERIC và số thực dấu phẩy động

`NUMERIC`/`DECIMAL` được dùng khi cần kiểm soát phép tính thập phân. Tuy vậy, phép chia vô hạn như `1 / 3` vẫn cần một độ chính xác hữu hạn khi lưu hoặc hiển thị; `ROUND(..., 2)` quy định mức làm tròn cho báo cáo.

`REAL` và `DOUBLE PRECISION` là kiểu dấu phẩy động nhị phân. Chúng nhanh và hữu ích trong nhiều tính toán khoa học nhưng có thể không biểu diễn chính xác một số phân số thập phân như 0.1. Với tiền và tỷ lệ báo cáo cần quy tắc làm tròn rõ ràng, nên ưu tiên kiểu dữ liệu và phép tính phù hợp với độ chính xác nghiệp vụ.

Một điểm thực tế: phép nhân hoặc cộng **giữa các số nguyên lớn** có thể bị tràn kiểu trước khi kết quả được chuyển sang thập phân. Ví dụ công thức phần trăm nên dùng `100.0 * finished_count` hoặc ép kiểu số đếm từ sớm, thay vì giả định `100 * finished_count` luôn nằm trong giới hạn kiểu nguyên.

## 11. Thứ tự toán tử và dấu ngoặc ảnh hưởng kết quả

Các phép `*`, `/` và `%` có mức ưu tiên cao hơn `+` và `-` trong các biểu thức số học cơ bản; nên dùng **dấu ngoặc** khi cần làm rõ ý nghĩa.

Ví dụ hai cách tính khác nhau trong PostgreSQL:

~~~sql
SELECT
    5 / 2 * 2 AS divide_then_multiply,
    5 * 2 / 2 AS multiply_then_divide;
~~~

Kết quả lần lượt là **4** và **5**. Trong biểu thức đầu, `5 / 2` đã thành **2** rồi mới nhân 2. Trong biểu thức sau, `5 * 2` thành **10** rồi chia 2, nên không có phần lẻ để mất.

Nếu mục đích là biểu thức phân số, cách rõ ràng hơn:

~~~sql
SELECT
    (5::numeric / 2) * 2 AS preserved_fraction;
~~~

Kết quả là **5**, vì phép chia thực hiện ở kiểu thập phân.

Tương tự, các công thức doanh thu trên mỗi sản phẩm có thể cần dấu ngoặc:

~~~sql
-- Gia tri trung binh cua mot don co tong 120 va 3 san pham.
SELECT
    120::numeric / 3 AS unit_price,
    (120::numeric + 30) / 3 AS unit_price_including_fee;
~~~

Kết quả tương ứng là **40** và **50**. Nếu phí 30 là phí **cho toàn bộ đơn hàng**, đặt nó trong tử số sẽ khác việc cộng phí 30 **cho từng sản phẩm**. Kết quả SQL đúng về số học chỉ có ý nghĩa nếu công thức phản ánh đúng nghiệp vụ.

## 12. Phép chia và NULL

`NULL` trong SQL biểu thị giá trị chưa có hoặc chưa biết. Hầu hết biểu thức số học thông thường có toán hạng `NULL` sẽ trả về `NULL`:

~~~sql
SELECT
    8 / NULL::integer AS divided_by_null,
    NULL::integer / 2 AS null_numerator,
    8 % NULL::integer AS remainder_with_null;
~~~

Ba cột đều có giá trị `NULL`. Đây không phải lỗi chia cho 0: **0** là một giá trị số cụ thể, còn `NULL` là thiếu giá trị.

Với biểu thức mẫu:

~~~sql
SELECT
    finished_count::numeric / NULLIF(planned_count, 0) AS ratio
FROM lab_division_batches_138
ORDER BY batch_id;
~~~

Nếu `planned_count = 0`, biểu thức trả `NULL`. Nếu cột `planned_count` cho phép chứa `NULL` trong một schema khác, kết quả cũng có thể là `NULL`, nhưng **lý do nghiệp vụ khác**: một bên là mẫu số bằng 0, bên kia là mẫu số chưa có. Muốn hiển thị thông báo cụ thể cho từng tình huống, hãy dùng `CASE`:

~~~sql
SELECT
    batch_id,
    CASE
        WHEN planned_count = 0 THEN 'Chua co ke hoach'
        ELSE 'Co ke hoach'
    END AS plan_status
FROM lab_division_batches_138
ORDER BY batch_id;
~~~

Ví dụ `CASE` trên chỉ xử lý 0 vì cột mẫu được khai báo `NOT NULL`. Nếu dùng bảng thực tế có cột nullable, cần thêm nhánh `WHEN planned_count IS NULL` để tách riêng dữ liệu chưa biết.

## 13. Khác biệt giữa các hệ quản trị SQL

Không có một quy tắc duy nhất cho phép chia `/` trên tất cả các hệ quản trị:

| Hệ quản trị | `5 / 2` thường cho | Muốn thương nguyên | Lấy phần dư | Ghi chú |
| --- | ---: | --- | --- | --- |
| **PostgreSQL** | 2 nếu hai toán hạng là `INTEGER` | `5 / 2` | `5 % 2` hoặc `MOD(5, 2)` | `5.0 / 2` cho kết quả 2.5; `::numeric` là cú pháp ép kiểu riêng |
| **MySQL** | 2.5 (phép chia thông thường `/`) | `5 DIV 2` | `5 % 2` hoặc `MOD(5, 2)` | `DIV` chuyên cho thương nguyên; kiểu và cách làm tròn phụ thuộc toán hạng |
| **SQL Server** | 2 nếu hai toán hạng nguyên | Chia nguyên bằng `/` với toán hạng nguyên | `5 % 2` | Ép ít nhất một toán hạng thành `DECIMAL` để giữ phần lẻ |
| **SQLite** | 2 nếu hai toán hạng nguyên | `5 / 2` | `5 % 2` | `5.0 / 2` cho 2.5; toán tử `%` làm việc theo chuyển đổi số nguyên của SQLite |
| **Oracle Database** | 2.5 | Dùng `TRUNC(5 / 2)` nếu muốn cắt phần lẻ | `MOD(5, 2)` | `NUMBER` và phép `/` có ngữ nghĩa khác chia nguyên PostgreSQL |

Ví dụ ở **MySQL**:

~~~sql
SELECT
    5 / 2 AS decimal_quotient,
    5 DIV 2 AS integer_quotient,
    MOD(5, 2) AS remainder_value;
~~~

Kết quả về giá trị lần lượt **2.5**, **2** và **1**.

Ví dụ ở **SQL Server**:

~~~sql
SELECT
    5 / 2 AS integer_quotient,
    CAST(5 AS DECIMAL(10, 2)) / 2 AS decimal_quotient,
    5 % 2 AS remainder_value;
~~~

Các giá trị tương ứng là **2**, **2.5** và **1**; cách hiển thị độ chính xác thập phân phụ thuộc kiểu kết quả.

Các lệnh ở hai ví dụ vừa nêu dùng để **đối chiếu dialect**, không được ghép thành script chạy trên PostgreSQL của bài thực hành. Ngoài ra, một số hệ quản trị có quy tắc riêng về chia cho 0, cảnh báo, chế độ SQL, ép kiểu ngầm và dấu phần dư. Hãy xác nhận hành vi của hệ quản trị cụ thể trước khi dùng kết quả trong báo cáo hoặc nghiệp vụ.

## 14. Các lỗi thường gặp

| Cách viết hoặc quan niệm dễ sai | Hậu quả | Cách xử lý |
| --- | --- | --- |
| `3 / 8` để tính tỷ lệ PostgreSQL | Nhận 0 do chia nguyên | `3::numeric / 8` hoặc `3.0 / 8` |
| `CAST(3 / 8 AS NUMERIC)` | Đổi **0** sang numeric, không lấy lại được 0.375 | Ép kiểu **trước** khi chia |
| `100 * finished_count / planned_count` với số nguyên | Tỷ lệ phần trăm bị cắt phần lẻ | `100.0 * finished_count / NULLIF(planned_count, 0)` |
| `item_count / box_capacity` để đếm **tổng** số thùng cần dùng | Bỏ sót thùng chứa phần dư | `CEIL(item_count::numeric / capacity)` khi capacity > 0 |
| `item_count % 0` | Lỗi vì số chia bằng 0 | Xử lý dữ liệu và dùng `NULLIF` nếu cần |
| `COALESCE(a / NULLIF(b, 0), 0)` rồi coi 0 là tỷ lệ thật | Che khuất mẫu số không hợp lệ | Chỉ dùng giá trị thay thế khi nghiệp vụ quy định rõ |
| `-5 % 2` được đoán là 1 | Sai với PostgreSQL: kết quả là -1 | Kiểm tra quy ước dấu phần dư |
| `FLOOR(-5::numeric / 2)` được cho là bằng chia nguyên | `FLOOR(-2.5) = -3`, khác `-5 / 2 = -2` | Phân biệt làm tròn xuống và cắt về 0 |
| `ROUND(5 / 2, 2)` để lấy 2.50 | Phần lẻ đã mất trước khi gọi `ROUND`; còn có thể sai kiểu hàm | `ROUND(5::numeric / 2, 2)` |
| Cho rằng `%` là phép tính “phần trăm” | Nhận phần dư thay vì tỷ lệ | Dùng phép nhân `* 100` sau phép chia thập phân |
| Áp dụng `5 / 2 = 2` cho MySQL/Oracle | Kết quả khác giữa các hệ quản trị | Kiểm tra SQL dialect, kiểu và cú pháp phù hợp |

## 15. Bài tập thực hành

Các bài dưới đây dùng dữ liệu `lab_division_batches_138` ở mục 2. Hãy dự đoán kết quả trước khi xem đáp án và thực thi trên database thực hành.

### Bài 1 — So sánh kết quả phép chia

Dự đoán bốn giá trị:

~~~sql
SELECT
    9 / 4 AS a,
    9.0 / 4 AS b,
    9 % 4 AS c,
    CAST(9 / 4 AS NUMERIC(10, 2)) AS d;
~~~

**Đáp án:** `a = 2`, `b = 2.25`, `c = 1`, `d = 2.00`. Cột `d` đã tính thương nguyên trước khi ép kiểu.

### Bài 2 — Giữ phần thập phân của một tỷ số

Viết phép chia `7` cho `8` nhận giá trị **0.875** thay vì 0.

**Đáp án tham khảo:**

~~~sql
SELECT 7::numeric / 8 AS ratio;
~~~

Hoặc dùng `CAST(7 AS NUMERIC) / 8`.

### Bài 3 — Số thùng đầy và phần dư

Một đợt có 23 món, mỗi thùng chứa 5 món. Hỏi có bao nhiêu thùng đầy và còn mấy món?

**Đáp án:**

~~~sql
SELECT
    23 / 5 AS full_boxes,
    23 % 5 AS leftover_items;
~~~

Kết quả **4 thùng đầy** và **3 món dư** vì `23 = 5 × 4 + 3`. Nếu phải chứa cả 23 món thì cần **5 thùng**.

### Bài 4 — Tỷ lệ hoàn thành và làm tròn

Viết truy vấn tính phần trăm hoàn thành của từng đợt, làm tròn hai chữ số, xử lý `planned_count = 0`.

**Đáp án:**

~~~sql
SELECT
    batch_id,
    ROUND(
        100.0 * finished_count / NULLIF(planned_count, 0),
        2
    ) AS completion_percent
FROM lab_division_batches_138
ORDER BY batch_id;
~~~

Kết quả lần lượt **37.50**, **100.00**, **NULL**, **66.67**, **50.00** theo ID 1–5.

### Bài 5 — Tại sao NULLIF chưa đủ?

Một người viết:

~~~sql
SELECT 3 / NULLIF(8, 0) AS ratio;
~~~

Truy vấn không lỗi nhưng `ratio` lại bằng 0. Vì sao? Sửa thế nào?

**Đáp án:** `NULLIF(8, 0)` trả về 8 thuộc kiểu nguyên; `3 / 8` vẫn là phép chia nguyên PostgreSQL. Cần đổi một toán hạng sang thập phân:

~~~sql
SELECT 3.0 / NULLIF(8, 0) AS ratio;
~~~

Kết quả là **0.375**.

### Bài 6 — So sánh FLOOR, TRUNC và phép chia nguyên âm

Dự đoán:

~~~sql
SELECT
    -7 / 3 AS integer_result,
    TRUNC(-7::numeric / 3) AS truncated_result,
    FLOOR(-7::numeric / 3) AS floor_result,
    -7 % 3 AS remainder_result;
~~~

**Đáp án:** chia nguyên **-2**, `TRUNC` **-2**, `FLOOR` **-3**, phần dư **-1**. Kiểm tra: `-7 = 3 × (-2) + (-1)`.

### Bài 7 — Tính tổng tỷ lệ, tránh tính trung bình sai

Sử dụng bảng mẫu, tính tỷ lệ hoàn thành của **toàn bộ các đợt**, thay vì trung bình của tỷ lệ mỗi đợt. Yêu cầu xử lý tổng kế hoạch bằng 0.

**Đáp án:**

~~~sql
SELECT
    ROUND(
        100.0 * SUM(finished_count)
        / NULLIF(SUM(planned_count), 0),
        2
    ) AS overall_percent
FROM lab_division_batches_138;
~~~

Kết quả **61.11%**, vì tổng hoàn thành 11 trên tổng kế hoạch 18.

### Bài 8 — Tìm các đợt cần thêm thùng không đầy

Yêu cầu: liệt kê đợt có `box_capacity > 0` và có ít nhất một món dư sau khi chia theo sức chứa thùng.

**Đáp án:**

~~~sql
SELECT batch_id, item_count, box_capacity
FROM lab_division_batches_138
WHERE box_capacity > 0
  AND item_count % box_capacity <> 0
ORDER BY batch_id;
~~~

Kết quả là các đợt **1, 4, 5**. Đợt 2 chia hết, còn đợt 3 không có sức chứa hợp lệ. Trong thực tế, nếu điều kiện chia được lồng vào biểu thức phức tạp, dùng `NULLIF(box_capacity, 0)` hoặc bảo vệ dữ liệu ở schema sẽ giúp tránh phụ thuộc vào giả định về thứ tự đánh giá điều kiện.

### Bài 9 — Phân biệt thương nguyên và số thùng phải dùng

Đối với đợt 4 (9 món, 4 món/thùng), kết quả nào phù hợp khi cần biết **số thùng phải chuẩn bị**?

~~~sql
SELECT
    9 / 4 AS whole_boxes,
    CEIL(9::numeric / 4) AS required_boxes;
~~~

**Đáp án:** `whole_boxes = 2` là số thùng **đầy**; `required_boxes = 3` là số thùng **phải có** để chứa toàn bộ 9 món. Sự khác nhau đến từ yêu cầu nghiệp vụ, không phải một câu SQL “sai cú pháp”.

## 16. Ghi nhớ khi viết phép chia trong SQL

| Mục tiêu | Mẫu PostgreSQL | Ý nghĩa |
| --- | --- | --- |
| Thương nguyên | `a / b` (cả hai nguyên) | Cắt phần lẻ của thương về 0 |
| Thương thập phân | `a::numeric / b` | Giữ phần thập phân |
| Phần dư | `a % b` hoặc `MOD(a, b)` | Phần còn lại sau phép chia |
| Tránh lỗi chia cho 0 | `a::numeric / NULLIF(b, 0)` | Trả NULL nếu b bằng 0 |
| Làm tròn tỷ số | `ROUND(a::numeric / NULLIF(b, 0), 2)` | Làm tròn đến hai chữ số thập phân |
| Số nhóm đầy | `a / b` với a, b nguyên không âm và b dương | Số nhóm có đủ b đơn vị |
| Số nhóm cần để chứa hết | `CEIL(a::numeric / NULLIF(b, 0))` | Làm tròn lên, kể cả nhóm cuối chưa đầy |
| Tỷ lệ phần trăm | `100.0 * a / NULLIF(b, 0)` | Đổi tỷ số sang đơn vị phần trăm |

Khi gặp một phép chia trong SQL, nên tự hỏi: **“Các toán hạng đang có kiểu gì? Mình muốn thương nguyên, thương thập phân hay phần dư? Mẫu số có thể bằng 0 hoặc NULL không? Kết quả có cần làm tròn theo quy tắc nghiệp vụ nào?”** Trả lời lần lượt bốn câu hỏi này sẽ tránh được những lỗi tính toán âm thầm, đặc biệt ở tỷ lệ, báo cáo, đơn giá và phân nhóm dữ liệu.

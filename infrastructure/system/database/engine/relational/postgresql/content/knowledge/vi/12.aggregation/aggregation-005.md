# string_agg, array_agg, json_agg và thứ tự phần tử

Một truy vấn tổng hợp không nhất thiết chỉ trả về một con số như `COUNT(*)` hoặc `SUM(amount)`. Trong PostgreSQL, bạn có thể biến nhiều hàng thành **một chuỗi**, **một mảng PostgreSQL** hoặc **một mảng JSON** để phục vụ báo cáo, API và xử lý dữ liệu tiếp theo. Ba hàm phổ biến là **`string_agg`**, **`array_agg`** và **`json_agg`**.

Ví dụ một đơn hàng có ba dòng sản phẩm. Có ít nhất ba cách biểu diễn những dòng này:

```text
Dữ liệu nguồn:
order_id | line_no | product_name
---------+---------+--------------
1001     | 1       | Chuột
1001     | 2       | Bàn phím
1001     | 3       | Chuột

string_agg → "Chuột, Bàn phím, Chuột"
array_agg  → {"Chuột","Bàn phím","Chuột"}
json_agg   → ["Chuột","Bàn phím","Chuột"]
```

Ba kết quả khác nhau cả về **kiểu dữ liệu** lẫn cách sử dụng. Chuỗi thuận tiện để hiển thị; mảng PostgreSQL phù hợp cho SQL và các phép toán mảng; JSON phù hợp để trao đổi dữ liệu có cấu trúc. Nhưng điểm chung là **thứ tự các phần tử không được bảo đảm nếu không yêu cầu rõ ràng**.

Bài học tập trung vào:

- Phân biệt chữ ký, kiểu trả về và ý nghĩa của `string_agg`, `array_agg`, `json_agg`.
- Dùng **`ORDER BY` nằm trong lời gọi aggregate**, tách biệt với `ORDER BY` của kết quả truy vấn.
- Xử lý **`DISTINCT`**, **`FILTER`**, `NULL`, nhóm không có hàng và kiểu dữ liệu của `COALESCE`.
- Tổng hợp thành JSON objects, cấu trúc JSON lồng nhau, mảng và chuỗi đã khử trùng lặp.
- Tránh nhân bản phần tử khi `JOIN` nhiều bảng một-nhiều; xử lý số lượng phần tử lớn.
- Ứng dụng trong SQL/JDBC và những bài tập thực hành theo ngữ cảnh đơn hàng.

> **Phạm vi:** Ví dụ sử dụng PostgreSQL và một database lab. Các câu `CREATE`/`INSERT` chỉ nên chạy trong môi trường thử nghiệm còn trống tên đối tượng. Với PostgreSQL ở các phiên bản khác nhau, một số biến thể hàm JSON và cú pháp mở rộng có thể khác; các kỹ thuật cơ bản trong bài sử dụng các aggregate phổ biến.

## 1. Một aggregate tạo một giá trị từ nhiều hàng

Một aggregate thường nhận các giá trị của **nhiều hàng trong cùng một nhóm** rồi tạo một kết quả.

```sql
SELECT
    order_id,
    COUNT(*) AS line_count
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

`COUNT(*)` trả số hàng. Thay vì đếm, ta có thể **gom giá trị**:

```sql
SELECT
    order_id,
    string_agg(product_name, ', ' ORDER BY line_no) AS names
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Ý tưởng:

```text
Các hàng trong nhóm order_id = 1001
       │
       ▼
Sắp theo line_no bên trong aggregate
       │
       ▼
"Chuột" → "Bàn phím" → "Chuột"
       │
       ▼
Nối lại bằng ", "
       │
       ▼
Một giá trị text: "Chuột, Bàn phím, Chuột"
```

`GROUP BY` quyết định **những hàng nào thuộc cùng nhóm**. `ORDER BY` bên trong aggregate quyết định **thứ tự các giá trị khi ghép**. `ORDER BY` ở cuối câu truy vấn quyết định **thứ tự các dòng kết quả sau tổng hợp**. Ba trách nhiệm khác nhau và không thể thay thế cho nhau.

## 2. Chuẩn bị dữ liệu thử nghiệm

Tạo schema riêng để tránh phụ thuộc `search_path`:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_aggregates;

CREATE TABLE lesson_aggregates.customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL
);

CREATE TABLE lesson_aggregates.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES lesson_aggregates.customers(customer_id),
    ordered_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('PENDING', 'PAID', 'CANCELLED'))
);

CREATE TABLE lesson_aggregates.order_items (
    order_id BIGINT NOT NULL
        REFERENCES lesson_aggregates.orders(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_name TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    note TEXT,
    PRIMARY KEY (order_id, line_no)
);
```

Thêm dữ liệu:

```sql
INSERT INTO lesson_aggregates.customers(customer_id, customer_name)
VALUES
    (1, 'An'),
    (2, 'Bình'),
    (3, 'Chi');

INSERT INTO lesson_aggregates.orders(
    order_id, customer_id, ordered_at, status
)
VALUES
    (1001, 1, TIMESTAMPTZ '2026-11-10 09:00:00+07', 'PAID'),
    (1002, 1, TIMESTAMPTZ '2026-11-11 11:00:00+07', 'PENDING'),
    (1003, 2, TIMESTAMPTZ '2026-11-12 14:00:00+07', 'PAID'),
    (1004, 3, TIMESTAMPTZ '2026-11-13 16:00:00+07', 'PENDING');

INSERT INTO lesson_aggregates.order_items(
    order_id, line_no, product_name, quantity, unit_price, note
)
VALUES
    (1001, 1, 'Chuột',      2, 120000, 'Khuyến mại'),
    (1001, 2, 'Bàn phím',   1, 450000, NULL),
    (1001, 3, 'Chuột',      1, 120000, NULL),
    (1002, 1, 'Tai nghe',   1, 800000, 'Quà tặng'),
    (1003, 1, 'Cáp USB-C',  3, 100000, NULL);
```

Đặc điểm của bộ dữ liệu:

- Đơn **1001** có ba item; hai item cùng tên **Chuột**.
- Đơn **1002** có một item là **Tai nghe**.
- Đơn **1003** có một item là **Cáp USB-C**.
- Đơn **1004** chưa có item nào.
- Cột `note` có cả giá trị text lẫn `NULL`.

Các trường hợp này sẽ giúp phân biệt trùng giá trị, phần tử null, nhóm không có hàng và thứ tự tổng hợp.

### Xác định thứ tự nguồn để xem dữ liệu

```sql
SELECT
    order_id,
    line_no,
    product_name,
    quantity,
    note
FROM lesson_aggregates.order_items
ORDER BY order_id, line_no;
```

`ORDER BY` ở đây chỉ sắp **những hàng đang được hiển thị**. Nó không tạo một quy tắc thứ tự vĩnh viễn cho bảng hoặc cho aggregate được thực hiện ở truy vấn khác.

## 3. So sánh ba hàm aggregate

| Hàm | Kiểu kết quả | Kết quả minh họa cho đơn 1001 | Công dụng điển hình |
|---|---|---|---|
| `string_agg(text, text)` | `text` | `Chuột, Bàn phím, Chuột` | Chuỗi tên, nhãn hiển thị, danh sách ngắn cho báo cáo. |
| `array_agg(expression)` | Mảng PostgreSQL của kiểu phần tử | `{"Chuột","Bàn phím","Chuột"}` | Giữ giá trị có kiểu trong SQL, truyền mảng cho hàm hoặc ứng dụng. |
| `json_agg(expression)` | `json` biểu diễn mảng | `["Chuột","Bàn phím","Chuột"]` | API, trao đổi dữ liệu, lồng objects. |

Một ví dụ so sánh trực tiếp:

```sql
SELECT
    order_id,
    string_agg(product_name, ', ' ORDER BY line_no)
        AS products_text,
    array_agg(product_name ORDER BY line_no)
        AS products_array,
    json_agg(product_name ORDER BY line_no)
        AS products_json
FROM lesson_aggregates.order_items
GROUP BY order_id
ORDER BY order_id;
```

Ở đơn 1001, kết quả nhìn qua có nội dung tương tự nhau, nhưng chúng **không cùng kiểu dữ liệu**.

```sql
SELECT
    pg_typeof(string_agg(product_name, ', ')) AS text_type,
    pg_typeof(array_agg(product_name)) AS array_type,
    pg_typeof(json_agg(product_name)) AS json_type
FROM lesson_aggregates.order_items
WHERE order_id = 1001;
```

Các kiểu tương ứng là **`text`**, **`text[]`** và **`json`** trong ví dụ cột `product_name TEXT`.

**Chọn kiểu theo nơi dùng tiếp**, không chọn chỉ vì cách hiển thị trong `psql` trông dễ đọc.

## 4. string_agg: ghép nhiều giá trị thành một chuỗi

Cú pháp phổ biến:

```sql
string_agg(value_expression, delimiter_expression
           ORDER BY sort_expression)
```

Trong đó:

- `value_expression` là biểu thức chuyển thành chuỗi để ghép, thường kiểu `text`.
- `delimiter_expression` là ký tự/chuỗi phân cách giữa những phần tử.
- `ORDER BY` **nằm bên trong lời gọi aggregate** để quyết định thứ tự ghép.

Ví dụ:

```sql
SELECT
    order_id,
    string_agg(product_name, ' | ' ORDER BY line_no) AS product_list
FROM lesson_aggregates.order_items
GROUP BY order_id
ORDER BY order_id;
```

Kết quả đơn 1001:

```text
Chuột | Bàn phím | Chuột
```

### Dấu phân cách không tự thêm ở hai đầu

Với ba phần tử A, B, C:

```text
string_agg(value, ', ') = A + ', ' + B + ', ' + C
```

Không có dấu phân cách thừa ở đầu/cuối. Dấu phân cách có thể là dấu phẩy, xuống dòng hoặc một chuỗi tùy mục đích hiển thị:

```sql
SELECT
    string_agg(product_name, E'\n' ORDER BY line_no) AS lines
FROM lesson_aggregates.order_items
WHERE order_id = 1001;
```

`E'\n'` là một chuỗi chứa ký tự xuống dòng theo cú pháp escape string của PostgreSQL.

### Ghép giá trị không phải TEXT

Giá tiền kiểu `numeric` cần chuyển sang biểu diễn chuỗi nếu muốn ghép:

```sql
SELECT
    order_id,
    string_agg(unit_price::text, ', ' ORDER BY line_no)
        AS unit_prices
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Hoặc định dạng theo biểu thức:

```sql
SELECT
    order_id,
    string_agg(
        product_name || ' x ' || quantity::text,
        '; ' ORDER BY line_no
    ) AS product_summary
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Ví dụ đơn 1001:

```text
Chuột x 2; Bàn phím x 1; Chuột x 1
```

Chuỗi này thích hợp làm **nội dung mô tả**. Nhưng nếu cần xử lý lại số lượng và giá tiền trong chương trình, dùng JSON hoặc mảng có cấu trúc thường đáng tin hơn việc phải tách chuỗi theo dấu `;`.

### string_agg không phải công cụ CSV hoàn chỉnh

`string_agg(product_name, ',')` chỉ nối văn bản, **không tự escape** dấu phẩy, dấu nháy hoặc xuống dòng trong dữ liệu. Nếu mục tiêu là xuất CSV đúng chuẩn, nên dùng cơ chế CSV phù hợp, ví dụ `COPY ... WITH (FORMAT csv)`, thay vì tự ghép trường một cách đơn giản.

## 5. array_agg: giữ các phần tử trong mảng PostgreSQL

`array_agg(expression)` tạo một **mảng** gồm các giá trị input trong nhóm.

```sql
SELECT
    order_id,
    array_agg(product_name ORDER BY line_no) AS product_names
FROM lesson_aggregates.order_items
GROUP BY order_id
ORDER BY order_id;
```

Đơn 1001 có mảng gồm ba phần tử:

```text
{"Chuột","Bàn phím","Chuột"}
```

Đây là **cú pháp hiển thị mảng của PostgreSQL**, không phải JSON. Trong JSON, chuỗi tương ứng có dấu ngoặc vuông `[...]` thay vì dấu ngoặc nhọn theo cách mảng PostgreSQL thường được in.

### Các phần tử giữ kiểu dữ liệu

```sql
SELECT
    order_id,
    array_agg(quantity ORDER BY line_no) AS quantities,
    pg_typeof(array_agg(quantity)) AS quantity_array_type
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Vì `quantity` là `integer`, kết quả là **`integer[]`**, không phải một chuỗi cần parse thành số.

Bạn có thể sử dụng các hàm/toán tử mảng:

```sql
WITH grouped AS (
    SELECT
        order_id,
        array_agg(product_name ORDER BY line_no) AS names
    FROM lesson_aggregates.order_items
    GROUP BY order_id
)
SELECT
    order_id,
    names,
    cardinality(names) AS number_of_elements,
    'Chuột' = ANY(names) AS has_mouse
FROM grouped
ORDER BY order_id;
```

`cardinality` trả số phần tử của mảng. Biểu thức `= ANY(array)` kiểm tra một giá trị có khớp ít nhất một phần tử theo quy tắc so sánh SQL; cần lưu ý hành vi ba giá trị khi mảng chứa `NULL`.

### Mảng có thể chứa phần tử NULL

`array_agg` **không tự loại `NULL`**. Khác với `string_agg`, nếu bạn tổng hợp `note`:

```sql
SELECT
    order_id,
    array_agg(note ORDER BY line_no) AS notes
FROM lesson_aggregates.order_items
GROUP BY order_id
ORDER BY order_id;
```

Đơn 1001 có một ghi chú `Khuyến mại` và hai ghi chú `NULL`. Mảng kết quả giữ cả ba vị trí, nên **vị trí phần tử có thể tương ứng với `line_no`** khi bạn sắp đúng thứ tự.

Muốn chỉ giữ ghi chú không null:

```sql
SELECT
    order_id,
    array_agg(note ORDER BY line_no)
        FILTER (WHERE note IS NOT NULL) AS nonnull_notes
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Ở ví dụ này, một nhóm không có ghi chú hợp lệ sẽ có kết quả aggregate **`NULL`**, không phải tự động là mảng rỗng. Ta sẽ xử lý sau bằng `COALESCE`.

## 6. json_agg: gom giá trị thành mảng JSON

`json_agg(expression)` trả về một giá trị kiểu **`json`**, có cấu trúc **JSON array**.

```sql
SELECT
    order_id,
    json_agg(product_name ORDER BY line_no) AS products_json
FROM lesson_aggregates.order_items
GROUP BY order_id
ORDER BY order_id;
```

Đơn 1001 có thể hiển thị:

```json
["Chuột", "Bàn phím", "Chuột"]
```

Điểm mạnh là JSON có thể chứa **giá trị số, chuỗi, boolean, null, array và object** trong cùng một cấu trúc. Ví dụ tổng hợp số lượng:

```sql
SELECT
    order_id,
    json_agg(quantity ORDER BY line_no) AS quantities_json
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Kết quả đơn 1001 về ý nghĩa là `[2,1,1]`, các phần tử là **số JSON**, không phải chuỗi `"2"`, `"1"`.

### json_agg giữ JSON null

`json_agg(note ORDER BY line_no)` đưa cả giá trị SQL `NULL` của input thành phần tử **JSON null**:

```sql
SELECT
    order_id,
    json_agg(note ORDER BY line_no) AS notes_json
FROM lesson_aggregates.order_items
GROUP BY order_id
ORDER BY order_id;
```

Đơn 1001 có thể cho:

```json
["Khuyến mại", null, null]
```

Đây là một khác biệt rõ với `string_agg(note, ', ')`: hàm nối chuỗi bỏ qua những giá trị input `NULL`, còn `json_agg` thường **đưa chúng thành phần tử JSON null**.

### json_agg khác jsonb_agg

PostgreSQL còn có **`jsonb_agg`**, trả kết quả kiểu **`jsonb`**:

```sql
SELECT
    order_id,
    json_agg(product_name ORDER BY line_no) AS as_json,
    jsonb_agg(product_name ORDER BY line_no) AS as_jsonb
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

| Đặc điểm | `json_agg` | `jsonb_agg` |
|---|---|---|
| Kiểu trả về | `json` | `jsonb` |
| Dùng làm mảng JSON | Có | Có |
| Bảo toàn thứ tự phần tử array đã sắp | Có | Có |
| Bảo đảm thứ tự thuộc tính trong JSON object | **Không nên dựa vào** | **Không nên dựa vào** |
| Toán tử/tính năng tra cứu JSONB | Cần chuyển kiểu khi dùng toán tử chỉ hỗ trợ JSONB. | Thuận tiện cho nhiều thao tác JSONB trong PostgreSQL. |

**Thứ tự các phần tử trong một JSON array có ý nghĩa**. Ngược lại, thứ tự các **khóa của JSON object** không phải điều nên dùng làm hợp đồng nghiệp vụ; đặc biệt `jsonb` có cách lưu/chuẩn hóa object riêng.

## 7. Quan trọng nhất: ORDER BY phải nằm trong aggregate

Một tập hàng quan hệ không tự mang thứ tự ổn định. Aggregate như `string_agg`, `array_agg` và `json_agg` **nhạy cảm với thứ tự input**: thay đổi thứ tự sẽ thay đổi thứ tự phần tử của kết quả.

### Cách không đủ chắc chắn

```sql
SELECT
    order_id,
    string_agg(product_name, ', ') AS product_list
FROM lesson_aggregates.order_items
GROUP BY order_id
ORDER BY order_id;
```

Câu trên chỉ sắp **các hàng kết quả theo `order_id`**. Nó không yêu cầu chuỗi tên của từng đơn phải theo `line_no`.

PostgreSQL có thể đọc hàng theo thứ tự khác nhau do:

- Thay đổi execution plan hoặc chỉ mục.
- Cách planner tổ chức nhóm/join.
- Thay đổi thứ tự lưu trữ vật lý sau `UPDATE`/`VACUUM` hoặc quá trình nạp dữ liệu.
- Thao tác song song hoặc các thay đổi khác về cách tạo input cho aggregate.

Không nên nói “nó luôn đúng trên máy của tôi” rồi coi đó là hợp đồng thứ tự.

### Cách đúng: đặt ORDER BY trong lời gọi

```sql
SELECT
    order_id,
    string_agg(product_name, ', ' ORDER BY line_no) AS products_text,
    array_agg(product_name ORDER BY line_no) AS products_array,
    json_agg(product_name ORDER BY line_no) AS products_json
FROM lesson_aggregates.order_items
GROUP BY order_id
ORDER BY order_id;
```

Mỗi aggregate tự yêu cầu input theo `line_no`. `ORDER BY order_id` bên ngoài chỉ quyết định đơn 1001 được hiển thị trước đơn 1002.

### Hai nơi ORDER BY, hai ý nghĩa

```text
SELECT
  order_id,
  string_agg(product_name, ', ' ORDER BY line_no)
                        │                │
                        │                └── thứ tự PHẦN TỬ trong chuỗi
                        └── dấu phân cách
FROM ...
GROUP BY order_id
ORDER BY order_id DESC;
         └── thứ tự CÁC HÀNG kết quả (các đơn)
```

**Quy tắc nhớ nhanh:** Khi cần danh sách trong từng nhóm có thứ tự, hãy đặt `ORDER BY` **ngay bên trong** `string_agg`, `array_agg` hoặc `json_agg`.

## 8. ORDER BY trong subquery có thay thế được không?

Một cách viết dễ gây hiểu nhầm:

```sql
SELECT
    order_id,
    array_agg(product_name) AS products
FROM (
    SELECT order_id, product_name
    FROM lesson_aggregates.order_items
    ORDER BY line_no
) AS sorted_items
GROUP BY order_id;
```

Subquery trên có vẻ “đã sắp dữ liệu”, và trong một số trường hợp kết quả thử có thể đúng mong đợi. Nhưng nếu truy vấn ngoài bổ sung `JOIN`, grouping hoặc các thao tác khác, thứ tự hàng thực sự tới aggregate **có thể thay đổi**.

Cách thể hiện ý định đáng tin cậy hơn:

```sql
SELECT
    order_id,
    array_agg(product_name ORDER BY line_no) AS products
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Khi logic cần phép sắp xếp input phức tạp, bạn vẫn có thể dùng CTE/subquery để **tính khóa sắp xếp**. Tuy vậy, nên dùng khóa đó trong `ORDER BY` của aggregate ở tầng cuối:

```sql
WITH prepared AS (
    SELECT
        order_id,
        line_no,
        product_name,
        lower(product_name) AS normalized_name
    FROM lesson_aggregates.order_items
)
SELECT
    order_id,
    array_agg(product_name
              ORDER BY normalized_name, line_no) AS sorted_names
FROM prepared
GROUP BY order_id;
```

Đây là sự khác biệt giữa **tính biểu thức sắp xếp trước** và **bảo đảm thứ tự input của aggregate**.

## 9. Thứ tự ổn định cần khóa phụ khi có giá trị trùng

Giả sử yêu cầu sắp theo `unit_price`, nhưng hai item có cùng giá 120.000. Nếu chỉ viết:

```sql
SELECT
    order_id,
    json_agg(product_name ORDER BY unit_price) AS products
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

hai item có **cùng `unit_price`** không được xác định thứ tự tương đối qua khóa này. Nếu chúng có giá trị JSON khác nhau, những lần chạy khác nhau có thể cho thứ tự không như bạn mong muốn.

Hãy chọn thêm **tie-breaker**:

```sql
SELECT
    order_id,
    json_agg(
        json_build_object(
            'line_no', line_no,
            'product', product_name,
            'price', unit_price
        )
        ORDER BY unit_price, line_no
    ) AS products
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Vì `(order_id, line_no)` là khóa chính của bảng mẫu, `line_no` phân biệt các item **trong một nhóm đơn hàng**. Điều đó cho thứ tự xác định ngay cả khi giá bằng nhau.

### Các nguyên tắc chọn khóa sắp xếp

1. Khóa đầu phản ánh **thứ tự nghiệp vụ**: thời gian, vị trí, mức ưu tiên, `sort_order`.
2. Thêm khóa phụ **duy nhất trong nhóm** khi cần kết quả ổn định tuyệt đối.
3. Với dữ liệu text, nhớ rằng collation quyết định so sánh và thứ tự chữ.
4. Đặt `NULLS FIRST`/`NULLS LAST` rõ nếu sort key có thể null và vị trí null quan trọng.
5. Đừng dùng `ctid` hoặc thứ tự vật lý hàng như một khóa thứ tự nghiệp vụ lâu dài.

Ví dụ:

```sql
SELECT
    order_id,
    array_agg(
        product_name
        ORDER BY unit_price DESC NULLS LAST, line_no ASC
    ) AS names_expensive_first
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

## 10. Collation ảnh hưởng thứ tự chuỗi

Khi sắp theo `product_name`, PostgreSQL áp dụng quy tắc **collation** có hiệu lực. Thứ tự chữ hoa/thường, dấu và ký tự ngôn ngữ có thể phụ thuộc collation và cấu hình server.

```sql
SELECT
    order_id,
    string_agg(product_name, ', ' ORDER BY product_name)
        AS names_by_text_sort
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Nếu cần một cách so sánh byte/codepoint cụ thể cho một phần biểu thức trong PostgreSQL, có thể chỉ định collation tương ứng:

```sql
SELECT
    order_id,
    array_agg(
        product_name
        ORDER BY product_name COLLATE "C", line_no
    ) AS names_c_collation
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

**Không chọn `"C"` mặc định cho mọi giao diện tiếng Việt.** Đối với thứ tự hiển thị cho người dùng, cần chọn collation/ngôn ngữ đúng yêu cầu nghiệp vụ. `"C"` có thể phù hợp hơn khi cần quy tắc kỹ thuật nhất quán theo byte, nhưng không tương đương sắp xếp tự nhiên theo tiếng Việt.

Nếu kết quả array/JSON là hợp đồng giữa nhiều hệ thống, hãy làm rõ **sort rule và tie-breaker** thay vì nói chung chung “sắp xếp theo tên”.

## 11. NULL: ba hàm có hành vi khác nhau

Đối với những input `NULL`:

| Input trong nhóm | `string_agg(note, ', ')` | `array_agg(note)` | `json_agg(note)` |
|---|---|---|---|
| `'A'`, `NULL`, `'B'` | `A, B` | `{"A",NULL,"B"}` | `["A",null,"B"]` |
| `NULL`, `NULL` | `NULL` | Mảng gồm 2 phần tử SQL NULL | `[null,null]` |
| **Không có hàng input nào** | `NULL` | `NULL` | `NULL` |

Khác biệt quan trọng:

- `string_agg` **bỏ qua giá trị input `NULL`**. Nếu tất cả input null hoặc không có hàng, kết quả là `NULL`.
- `array_agg` **giữ giá trị null dưới dạng phần tử mảng**.
- `json_agg` **giữ giá trị null dưới dạng phần tử JSON null**.
- **Không có hàng** khác với **có một hàng mà biểu thức aggregate bằng null**.

Ví dụ đơn 1001:

```sql
SELECT
    string_agg(note, ' | ' ORDER BY line_no) AS notes_text,
    array_agg(note ORDER BY line_no) AS notes_array,
    json_agg(note ORDER BY line_no) AS notes_json
FROM lesson_aggregates.order_items
WHERE order_id = 1001;
```

Kết quả về ý nghĩa:

```text
notes_text  = Khuyến mại
notes_array = {"Khuyến mại",NULL,NULL}
notes_json  = ["Khuyến mại",null,null]
```

### Có một hàng chứa NULL

```sql
SELECT
    string_agg(x.note, ', ') AS s,
    array_agg(x.note) AS a,
    json_agg(x.note) AS j
FROM (VALUES (NULL::text)) AS x(note);
```

Kết quả:

```text
s = SQL NULL
a = {NULL}
j = [null]
```

### Không có hàng

```sql
SELECT
    string_agg(note, ', ') AS s,
    array_agg(note) AS a,
    json_agg(note) AS j
FROM lesson_aggregates.order_items
WHERE order_id = -1;
```

Một aggregate query **không `GROUP BY`** vẫn thường trả **một hàng kết quả**, trong đó ba aggregate ở trên đều là SQL `NULL` vì không có input phù hợp.

Đây là nền tảng để hiểu nhóm không có item khi dùng `LEFT JOIN`.

## 12. LEFT JOIN: hàng mở rộng NULL không phải nhóm rỗng

Muốn liệt kê **mọi đơn**, kể cả đơn 1004 chưa có item:

```sql
SELECT
    o.order_id,
    COUNT(i.line_no) AS item_count,
    string_agg(i.product_name, ', ' ORDER BY i.line_no)
        AS item_names,
    array_agg(i.product_name ORDER BY i.line_no)
        AS item_array,
    json_agg(i.product_name ORDER BY i.line_no)
        AS item_json
FROM lesson_aggregates.orders AS o
LEFT JOIN lesson_aggregates.order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
```

Với đơn **1004**, `LEFT JOIN` tạo **một hàng kết quả trung gian** từ `o`, còn cột `i.*` là `NULL`:

```text
order_id = 1004, i.line_no = NULL, i.product_name = NULL
```

Do đó:

- `COUNT(i.line_no)` = **0** vì `COUNT(expression)` bỏ qua null.
- `string_agg(i.product_name, ', ')` = SQL **NULL**.
- `array_agg(i.product_name)` có thể là **mảng một phần tử NULL**.
- `json_agg(i.product_name)` có thể là **`[null]`**.

Đây là một lỗi API phổ biến: “Đơn không có item” lại được biểu diễn thành một array có đúng một phần tử `null` thay vì **mảng rỗng**.

### Dùng FILTER để bỏ hàng giả từ LEFT JOIN

```sql
SELECT
    o.order_id,
    COUNT(i.line_no) AS item_count,
    array_agg(i.product_name ORDER BY i.line_no)
        FILTER (WHERE i.line_no IS NOT NULL) AS item_array,
    json_agg(i.product_name ORDER BY i.line_no)
        FILTER (WHERE i.line_no IS NOT NULL) AS item_json
FROM lesson_aggregates.orders AS o
LEFT JOIN lesson_aggregates.order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
```

`FILTER (WHERE i.line_no IS NOT NULL)` loại hàng giả phía `i` vì khóa `line_no` **không thể null ở một item thật**. Đối với đơn 1004, aggregate được cấp **0 input**, nên kết quả `array_agg`/`json_agg` là **SQL NULL**.

Tiếp theo, dùng `COALESCE` đổi SQL null sang mảng rỗng đúng kiểu.

## 13. COALESCE: chọn kết quả rỗng đúng kiểu

Các aggregate thông thường như `array_agg`, `json_agg` và `string_agg` thường trả `NULL` khi **không có input**. Nếu API muốn luôn trả danh sách, bạn có thể chuyển thành giá trị rỗng:

```sql
SELECT
    o.order_id,
    COALESCE(
        string_agg(
            i.product_name, ', '
            ORDER BY i.line_no
        ),
        ''
    ) AS item_names,
    COALESCE(
        array_agg(i.product_name ORDER BY i.line_no)
            FILTER (WHERE i.line_no IS NOT NULL),
        ARRAY[]::text[]
    ) AS item_array,
    COALESCE(
        json_agg(i.product_name ORDER BY i.line_no)
            FILTER (WHERE i.line_no IS NOT NULL),
        '[]'::json
    ) AS item_json
FROM lesson_aggregates.orders AS o
LEFT JOIN lesson_aggregates.order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
```

Với đơn 1004:

| Cột | Giá trị |
|---|---|
| `item_names` | Chuỗi rỗng `''` |
| `item_array` | Mảng PostgreSQL rỗng `{}` kiểu `text[]` |
| `item_json` | Mảng JSON rỗng `[]` kiểu `json` |

### Vì sao phải ép kiểu mảng rỗng?

`ARRAY[]` không có phần tử nên PostgreSQL không luôn có đủ ngữ cảnh để suy ra kiểu phần tử. Viết **`ARRAY[]::text[]`** giúp kết quả tương thích với `array_agg(product_name)`.

Tương tự:

```sql
SELECT
    COALESCE(array_agg(quantity), ARRAY[]::integer[]) AS quantities
FROM lesson_aggregates.order_items
WHERE order_id = -1;
```

Với JSONB:

```sql
SELECT
    COALESCE(jsonb_agg(product_name), '[]'::jsonb) AS names
FROM lesson_aggregates.order_items
WHERE order_id = -1;
```

### Rỗng hay NULL là quyết định nghiệp vụ

Không nên tự động biến mọi `NULL` thành chuỗi/mảng rỗng. Có hệ thống phân biệt:

- **`NULL`**: chưa biết, chưa truy xuất, chưa được tính.
- **`[]`/`{}`**: đã biết chắc không có phần tử.

Nếu API yêu cầu danh sách luôn là `[]`, dùng `COALESCE` là hợp lý. Nếu nghiệp vụ cần phân biệt trạng thái *unknown* với *empty*, giữ null và bổ sung thông tin trạng thái khi cần.

## 14. FILTER: chỉ lấy một phần hàng trong từng aggregate

Cú pháp:

```sql
aggregate_function(...) FILTER (WHERE condition)
```

`FILTER` áp dụng **riêng cho từng aggregate** thay vì xóa tất cả hàng của nhóm như `WHERE` ở cấp truy vấn.

Ví dụ tạo hai danh sách trong cùng một lần nhóm:

```sql
SELECT
    order_id,
    string_agg(
        product_name, ', '
        ORDER BY line_no
    ) AS all_products,
    string_agg(
        product_name, ', '
        ORDER BY line_no
    ) FILTER (WHERE quantity >= 2) AS products_with_multiple_units
FROM lesson_aggregates.order_items
GROUP BY order_id
ORDER BY order_id;
```

Đơn 1001:

- `all_products` = `Chuột, Bàn phím, Chuột`.
- `products_with_multiple_units` = `Chuột` vì chỉ dòng thứ nhất có `quantity >= 2`.

### FILTER khác WHERE

```sql
-- WHERE loại hàng trước khi mọi aggregate nhận input.
SELECT
    order_id,
    COUNT(*) AS item_rows,
    string_agg(product_name, ', ' ORDER BY line_no) AS names
FROM lesson_aggregates.order_items
WHERE quantity >= 2
GROUP BY order_id;
```

Truy vấn này **không còn nhìn thấy** các dòng có quantity 1 trong cả `COUNT(*)` và `string_agg`. Trong khi đó, `FILTER` cho phép **mỗi aggregate** có điều kiện riêng.

### FILTER đối với các giá trị NULL thực

Khi muốn loại phần tử note null:

```sql
SELECT
    order_id,
    COALESCE(
        json_agg(note ORDER BY line_no)
            FILTER (WHERE note IS NOT NULL),
        '[]'::json
    ) AS notes_json
FROM lesson_aggregates.order_items
GROUP BY order_id
ORDER BY order_id;
```

Điều kiện `note IS NOT NULL` có nghĩa **loại các item không có ghi chú**, khác với `i.line_no IS NOT NULL` vốn dùng để loại **hàng mở rộng từ LEFT JOIN**.

Hãy chọn điều kiện theo đúng điều muốn lọc: giá trị input null hay sự tồn tại của một hàng nguồn.

## 15. DISTINCT: loại trùng trước khi tổng hợp

Đơn 1001 có hai dòng sản phẩm cùng tên `Chuột`. Nếu muốn danh sách **tên sản phẩm duy nhất**:

```sql
SELECT
    order_id,
    string_agg(
        DISTINCT product_name,
        ', ' ORDER BY product_name
    ) AS distinct_names
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Đơn 1001 có hai tên duy nhất: **Bàn phím** và **Chuột**, được sắp theo `product_name`/collation.

Với mảng:

```sql
SELECT
    order_id,
    array_agg(
        DISTINCT product_name
        ORDER BY product_name
    ) AS unique_products
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Với JSON:

```sql
SELECT
    order_id,
    json_agg(
        DISTINCT product_name
        ORDER BY product_name
    ) AS unique_products_json
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

### DISTINCT khử trùng theo giá trị biểu thức

Nếu hai item có cùng tên `Chuột` nhưng `line_no` và `quantity` khác nhau, `DISTINCT product_name` gộp chúng thành **một tên**. Đây là điều mong muốn khi hiển thị “các sản phẩm khác nhau”, nhưng **không đúng** nếu mục tiêu là mô tả từng dòng đặt hàng.

Với từng dòng, dùng:

```sql
SELECT
    order_id,
    json_agg(
        json_build_object(
            'line_no', line_no,
            'product', product_name,
            'quantity', quantity
        )
        ORDER BY line_no
    ) AS items
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

**DISTINCT là quyết định về danh tính phần tử**, không phải biện pháp sửa mọi trường hợp truy vấn JOIN làm số hàng tăng.

## 16. DISTINCT + ORDER BY: ràng buộc cú pháp quan trọng

Trong PostgreSQL, khi một aggregate dùng **`DISTINCT`**, biểu thức trong **`ORDER BY` của aggregate** phải phù hợp với danh sách đối số aggregate. Bạn không thể tùy tiện sắp kết quả DISTINCT theo một cột khác không thuộc các biểu thức đầu vào được phân biệt.

Ví dụ hợp lệ:

```sql
SELECT
    order_id,
    string_agg(
        DISTINCT product_name,
        ', ' ORDER BY product_name
    ) AS names
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Ví dụ **không hợp lệ**:

```sql
-- Sai: DISTINCT theo product_name nhưng muốn ORDER BY line_no.
SELECT
    order_id,
    string_agg(
        DISTINCT product_name,
        ', ' ORDER BY line_no
    ) AS names
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Vấn đề còn nằm ở ý nghĩa: một tên `Chuột` xuất hiện tại `line_no = 1` và `line_no = 3`, vậy sau khi khử trùng thì dùng **line_no nào** làm khóa sắp xếp?

### Giải pháp: xác định khóa sắp xếp cho từng giá trị duy nhất

Ví dụ muốn **mỗi tên sản phẩm chỉ xuất hiện một lần, theo vị trí xuất hiện đầu tiên trong đơn**:

```sql
WITH distinct_products AS (
    SELECT
        order_id,
        product_name,
        MIN(line_no) AS first_line_no
    FROM lesson_aggregates.order_items
    GROUP BY order_id, product_name
)
SELECT
    order_id,
    string_agg(
        product_name,
        ', ' ORDER BY first_line_no, product_name
    ) AS names_by_first_appearance
FROM distinct_products
GROUP BY order_id
ORDER BY order_id;
```

Ở đây:

1. CTE tạo **một hàng cho mỗi cặp `(order_id, product_name)`**.
2. `MIN(line_no)` xác định vị trí xuất hiện đầu tiên một cách rõ ràng.
3. Aggregate cuối **không cần DISTINCT**, vì nguồn đã được deduplicate.
4. `ORDER BY first_line_no, product_name` sắp danh sách theo quy tắc nghiệp vụ.

Đây là mẫu đáng nhớ: **khử trùng và xác định sort key ở bước trung gian**, rồi aggregate có thứ tự ở bước cuối.

## 17. DISTINCT có cần kết hợp với FILTER không?

Có thể dùng cả hai:

```sql
SELECT
    order_id,
    array_agg(
        DISTINCT product_name
        ORDER BY product_name
    ) FILTER (WHERE quantity >= 2) AS distinct_bulk_names
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

`FILTER` chọn những dòng có số lượng từ 2 trở lên để đưa vào aggregate; `DISTINCT` loại tên trùng trong tập input đã chọn; `ORDER BY` quyết định thứ tự phần tử còn lại.

Không nên đánh đồng thứ tự xử lý logic này với một cam kết về execution plan vật lý. PostgreSQL có thể chọn nhiều cách triển khai tối ưu mà vẫn phải giữ ngữ nghĩa của câu SQL.

### DISTINCT cùng biểu thức phức tạp

Ví dụ bạn muốn phân biệt theo tên đã chuẩn hóa:

```sql
SELECT
    order_id,
    array_agg(
        DISTINCT lower(product_name)
        ORDER BY lower(product_name)
    ) AS normalized_names
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Khi muốn trả lại **tên gốc** nhưng phân biệt theo **tên chuẩn hóa**, bài toán trở nên phức tạp: cần chọn đại diện nào cho mỗi khóa chuẩn hóa. Thường nên giải quyết bằng CTE với `ROW_NUMBER()` hoặc quy tắc `MIN`/`MAX` phù hợp trước khi tổng hợp.

## 18. Tạo JSON objects từ từng dòng

`json_agg(product_name)` chỉ tạo mảng chuỗi. Với API, bạn thường cần một **mảng object** chứa nhiều trường của từng item.

`json_build_object` tạo một JSON object từ các cặp **key/value**:

```sql
SELECT
    order_id,
    json_agg(
        json_build_object(
            'line_no', line_no,
            'product_name', product_name,
            'quantity', quantity,
            'unit_price', unit_price,
            'note', note
        )
        ORDER BY line_no
    ) AS items
FROM lesson_aggregates.order_items
GROUP BY order_id
ORDER BY order_id;
```

Đơn 1001 có kết quả về ý nghĩa:

```json
[
  {
    "line_no": 1,
    "product_name": "Chuột",
    "quantity": 2,
    "unit_price": 120000,
    "note": "Khuyến mại"
  },
  {
    "line_no": 2,
    "product_name": "Bàn phím",
    "quantity": 1,
    "unit_price": 450000,
    "note": null
  },
  {
    "line_no": 3,
    "product_name": "Chuột",
    "quantity": 1,
    "unit_price": 120000,
    "note": null
  }
]
```

Một số lưu ý:

- `unit_price` có kiểu numeric nên biểu diễn thành **JSON number** trong ví dụ, không phải chuỗi tiền tệ.
- `note` null trở thành **JSON null**, trừ khi bạn thiết kế logic bỏ khóa null.
- Thứ tự **object trong array** được quyết định bởi `ORDER BY line_no` của `json_agg`.
- Không nên dùng thứ tự **key** bên trong một object làm tiêu chí nghiệp vụ.

### JSONB version

```sql
SELECT
    order_id,
    jsonb_agg(
        jsonb_build_object(
            'line_no', line_no,
            'product', product_name,
            'quantity', quantity
        )
        ORDER BY line_no
    ) AS items
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Kết quả có kiểu **`jsonb`**. Nếu ứng dụng cần thêm toán tử JSONB ở các bước tiếp theo, chọn `jsonb_agg` có thể tiện lợi.

## 19. JSON composite row, row_to_json và tính rõ ràng của hợp đồng API

PostgreSQL có thể chuyển **một row/composite value** thành JSON:

```sql
SELECT
    order_id,
    json_agg(i ORDER BY i.line_no) AS raw_items
FROM lesson_aggregates.order_items AS i
GROUP BY i.order_id;
```

`i` là cả giá trị composite của hàng `order_items`, không chỉ một cột. Kết quả JSON có thể bao gồm **tất cả các cột** của bảng nguồn.

### Rủi ro khi JSON hóa toàn bộ hàng

Nếu sau này bảng được thêm cột `internal_note` hoặc `supplier_cost`, câu `json_agg(i)` có thể đưa những trường mới vào JSON trả cho client mà bạn không chủ ý.

Với API có hợp đồng schema rõ, thường an toàn hơn khi chọn tường minh:

```sql
SELECT
    i.order_id,
    json_agg(
        json_build_object(
            'lineNo', i.line_no,
            'name', i.product_name,
            'quantity', i.quantity
        )
        ORDER BY i.line_no
    ) AS items
FROM lesson_aggregates.order_items AS i
GROUP BY i.order_id;
```

Điều này cũng cho phép dùng key theo quy ước camelCase của API trong khi SQL column dùng snake_case.

### row_to_json cho record được chọn trước

Khi đã có một derived table hoặc record với đúng các trường:

```sql
SELECT
    row_to_json(x) AS item_json
FROM (
    SELECT line_no, product_name, quantity
    FROM lesson_aggregates.order_items
    WHERE order_id = 1001
) AS x
ORDER BY x.line_no;
```

Truy vấn này trả **nhiều hàng JSON object**, mỗi hàng một item. Muốn **một JSON array**, cần `json_agg` ở một tầng phù hợp, với `ORDER BY` trong aggregate:

```sql
SELECT json_agg(row_to_json(x) ORDER BY x.line_no) AS items
FROM (
    SELECT line_no, product_name, quantity
    FROM lesson_aggregates.order_items
    WHERE order_id = 1001
) AS x;
```

`row_to_json(x)` tạo object từ các cột của record `x`; `json_agg` tiếp tục gom các object vào một JSON array.

## 20. JSON lồng nhau: một khách có nhiều đơn, mỗi đơn có nhiều item

Một API đôi khi muốn kết quả dạng:

```json
{
  "customer_id": 1,
  "customer_name": "An",
  "orders": [
    {
      "order_id": 1001,
      "status": "PAID",
      "items": [
        {"line_no": 1, "name": "Chuột"},
        {"line_no": 2, "name": "Bàn phím"},
        {"line_no": 3, "name": "Chuột"}
      ]
    },
    {
      "order_id": 1002,
      "status": "PENDING",
      "items": [
        {"line_no": 1, "name": "Tai nghe"}
      ]
    }
  ]
}
```

**Cách nên dùng:** tổng hợp từ **cấp chi tiết nhất** lên cấp cao hơn, tránh nhân số dòng do join trực tiếp nhiều quan hệ một-nhiều trong một aggregate duy nhất.

### Bước 1 — Tổng hợp item theo đơn

```sql
WITH items_per_order AS (
    SELECT
        i.order_id,
        jsonb_agg(
            jsonb_build_object(
                'line_no', i.line_no,
                'name', i.product_name,
                'quantity', i.quantity
            )
            ORDER BY i.line_no
        ) AS items
    FROM lesson_aggregates.order_items AS i
    GROUP BY i.order_id
)
SELECT
    o.order_id,
    COALESCE(p.items, '[]'::jsonb) AS items
FROM lesson_aggregates.orders AS o
LEFT JOIN items_per_order AS p
  ON p.order_id = o.order_id
ORDER BY o.order_id;
```

Nhờ `LEFT JOIN` vào **bảng đã tổng hợp sẵn**, đơn 1004 nhận `[]`, thay vì `[null]` do join một-nhiều trực tiếp.

### Bước 2 — Tạo JSON cho từng đơn

```sql
WITH items_per_order AS (
    SELECT
        i.order_id,
        jsonb_agg(
            jsonb_build_object(
                'line_no', i.line_no,
                'name', i.product_name,
                'quantity', i.quantity
            )
            ORDER BY i.line_no
        ) AS items
    FROM lesson_aggregates.order_items AS i
    GROUP BY i.order_id
),
orders_with_items AS (
    SELECT
        o.order_id,
        o.customer_id,
        o.status,
        o.ordered_at,
        jsonb_build_object(
            'order_id', o.order_id,
            'status', o.status,
            'items', COALESCE(ip.items, '[]'::jsonb)
        ) AS order_document
    FROM lesson_aggregates.orders AS o
    LEFT JOIN items_per_order AS ip
      ON ip.order_id = o.order_id
)
SELECT
    customer_id,
    jsonb_agg(
        order_document
        ORDER BY ordered_at, order_id
    ) AS orders
FROM orders_with_items
GROUP BY customer_id
ORDER BY customer_id;
```

Mỗi `order_document` đã chứa item array có thứ tự. Aggregate ngoài tiếp tục tạo **mảng đơn hàng**, được sắp theo thời gian và ID.

### Bước 3 — Giữ cả khách không có đơn

Nếu muốn **mọi khách**, kể cả người không có đơn:

```sql
WITH items_per_order AS (
    SELECT
        i.order_id,
        jsonb_agg(
            jsonb_build_object(
                'line_no', i.line_no,
                'name', i.product_name,
                'quantity', i.quantity
            )
            ORDER BY i.line_no
        ) AS items
    FROM lesson_aggregates.order_items AS i
    GROUP BY i.order_id
),
orders_with_items AS (
    SELECT
        o.order_id,
        o.customer_id,
        o.ordered_at,
        jsonb_build_object(
            'order_id', o.order_id,
            'status', o.status,
            'items', COALESCE(ip.items, '[]'::jsonb)
        ) AS order_document
    FROM lesson_aggregates.orders AS o
    LEFT JOIN items_per_order AS ip
      ON ip.order_id = o.order_id
)
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(
        jsonb_agg(
            o.order_document
            ORDER BY o.ordered_at, o.order_id
        ) FILTER (WHERE o.order_id IS NOT NULL),
        '[]'::jsonb
    ) AS orders
FROM lesson_aggregates.customers AS c
LEFT JOIN orders_with_items AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Trong dữ liệu mẫu, mỗi khách đều có ít nhất một đơn, nhưng SQL đã được viết để **hợp lệ cả khi bổ sung khách chưa có đơn**.

### Vì sao không viết json_agg(json_agg(...))?

PostgreSQL không cho phép tùy tiện **lồng trực tiếp một aggregate vào aggregate khác ở cùng cấp SELECT**. Việc phân tách qua **CTE/subquery** làm rõ hai cấp nhóm:

```text
order_items
    │ jsonb_agg theo order_id
    ▼
items_per_order
    │ JOIN vào orders
    ▼
orders_with_items
    │ jsonb_agg theo customer_id
    ▼
orders_per_customer
```

Đây cũng là cách hạn chế lỗi đếm trùng khi dữ liệu có nhiều quan hệ một-nhiều.

## 21. JOIN nhiều nguồn một-nhiều có thể làm trùng phần tử

Giả sử hệ thống bổ sung bảng `order_comments`, một đơn có **hai comment** và **ba item**. Nếu join trực tiếp cả hai bảng:

```text
orders (1 hàng)
    ├── items (3 hàng)
    └── comments (2 hàng)
                  │
                  ▼
JOIN cả hai bên → có thể tạo 3 × 2 = 6 hàng
```

Nếu sau đó viết `json_agg(i.product_name)`, mỗi item có thể xuất hiện **hai lần** dù bảng `order_items` chỉ lưu một lần.

### Không coi DISTINCT là giải pháp tổng quát

Nếu hai item khác `line_no` nhưng cùng tên `Chuột`, `json_agg(DISTINCT product_name)` chỉ còn một `Chuột`. Nó “sửa” số lượng phần tử bị nhân bản bằng cách **xóa cả những dòng hợp lệ**.

Cách phù hợp hơn:

1. Xác định đơn vị hàng của mỗi nguồn.
2. Tổng hợp `order_items` theo `order_id` trong một CTE/subquery riêng.
3. Tổng hợp `order_comments` theo `order_id` trong CTE/subquery khác.
4. Join **mỗi nguồn đã có tối đa một hàng trên mỗi đơn** với bảng `orders`.

Thứ tự aggregate vẫn cần `ORDER BY` riêng trong mỗi CTE.

### Mẫu SQL tổng quát

```sql
WITH items AS (
    SELECT
        order_id,
        jsonb_agg(
            jsonb_build_object(
                'line_no', line_no,
                'name', product_name
            )
            ORDER BY line_no
        ) AS item_list
    FROM lesson_aggregates.order_items
    GROUP BY order_id
)
SELECT
    o.order_id,
    COALESCE(i.item_list, '[]'::jsonb) AS item_list
FROM lesson_aggregates.orders AS o
LEFT JOIN items AS i USING (order_id);
```

Tư duy **aggregate trước, join sau** đặc biệt hữu ích khi xây response JSON có nhiều collection độc lập.

## 22. json_agg, JSON array và JSON object khác nhau

Hai nhu cầu API:

1. Danh sách có thể trùng khóa/giá trị và thứ tự cần bảo toàn → **JSON array**.
2. Tra cứu giá trị theo tên khóa, không cần thứ tự key → **JSON object**.

`json_agg` tạo **array**, không phải map/object:

```sql
SELECT json_agg(
    json_build_object('line', line_no, 'product', product_name)
    ORDER BY line_no
)
FROM lesson_aggregates.order_items
WHERE order_id = 1001;
```

Nếu muốn object ánh xạ một key tới value, PostgreSQL có `json_object_agg` hoặc `jsonb_object_agg` trong những phiên bản phù hợp. Nhưng cần cẩn thận:

- JSON object **không dùng để bảo đảm thứ tự phần tử** như JSON array.
- Khi key bị trùng, semantics xử lý trùng có thể khác nhau giữa hàm/biến thể/phiên bản.
- Nếu nghiệp vụ có nhiều item cùng `product_name`, dùng tên làm key sẽ làm **mất tính một-nhiều** hoặc phát sinh xung đột.

Ví dụ tạo object trong tình huống **key duy nhất rõ ràng**:

```sql
SELECT
    order_id,
    jsonb_object_agg(line_no::text, product_name) AS product_by_line
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Với đơn 1001, object có các key `"1"`, `"2"`, `"3"`. **Không suy ra thứ tự key hiển thị** là trình tự item. Muốn giữ trình tự, dùng `jsonb_agg` với `ORDER BY line_no`.

## 23. Chuyển kết quả tổng hợp về từng phần tử

Tổng hợp tạo một giá trị cho mỗi nhóm, nhưng ứng dụng có thể muốn **mở lại** thành nhiều dòng.

### Mảng PostgreSQL và unnest

```sql
WITH grouped AS (
    SELECT
        order_id,
        array_agg(product_name ORDER BY line_no) AS names
    FROM lesson_aggregates.order_items
    WHERE order_id = 1001
    GROUP BY order_id
)
SELECT
    g.order_id,
    x.ordinality,
    x.name
FROM grouped AS g
CROSS JOIN LATERAL unnest(g.names)
    WITH ORDINALITY AS x(name, ordinality)
ORDER BY g.order_id, x.ordinality;
```

`WITH ORDINALITY` tạo số thứ tự phần tử khi mở mảng. `ORDER BY ordinality` giúp hiển thị kết quả cuối theo đúng trình tự đã lưu.

### Mảng JSON và jsonb_array_elements

```sql
WITH grouped AS (
    SELECT
        order_id,
        jsonb_agg(
            jsonb_build_object(
                'line_no', line_no,
                'product', product_name
            )
            ORDER BY line_no
        ) AS items
    FROM lesson_aggregates.order_items
    WHERE order_id = 1001
    GROUP BY order_id
)
SELECT
    g.order_id,
    x.ordinality,
    x.item ->> 'product' AS product_name
FROM grouped AS g
CROSS JOIN LATERAL jsonb_array_elements(g.items)
    WITH ORDINALITY AS x(item, ordinality)
ORDER BY x.ordinality;
```

`->>` lấy giá trị JSON dưới dạng text. Nếu cần tính toán số học từ thuộc tính số, nên chuyển kiểu một cách có kiểm soát và validate dữ liệu.

### Chuỗi nối không tự bảo toàn cấu trúc

Với `string_agg`, nếu một `product_name` chứa dấu phân cách `,` hoặc `;`, việc tách chuỗi về danh sách ban đầu có thể không còn chính xác. Nếu cần khả năng **round-trip**, ưu tiên mảng hoặc JSON thay vì chuỗi trang trí.

## 24. Tổng hợp theo một cấp nhóm hay nhiều cấp nhóm?

`GROUP BY` quyết định **một hàng kết quả đại diện cho thực thể nào**:

| Mục tiêu | Cấp nhóm |
|---|---|
| Một chuỗi tên sản phẩm cho mỗi đơn | `GROUP BY order_id` |
| Một mảng tất cả tên sản phẩm của khách | Cần join đơn với item, sau đó `GROUP BY customer_id` |
| Một JSON array đơn hàng cho mỗi khách | Tạo object cho từng đơn, rồi `GROUP BY customer_id` |
| Một cấu trúc khách → đơn → item | Tổng hợp nhiều cấp qua CTE/subquery |
| Một JSON array tất cả sản phẩm trong database | Aggregate không có `GROUP BY` |

Ví dụ tất cả tên sản phẩm đã xuất hiện trong đơn của từng khách:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(
        array_agg(
            i.product_name
            ORDER BY o.ordered_at, o.order_id, i.line_no
        ) FILTER (WHERE i.line_no IS NOT NULL),
        ARRAY[]::text[]
    ) AS all_purchased_product_names
FROM lesson_aggregates.customers AS c
LEFT JOIN lesson_aggregates.orders AS o
  ON o.customer_id = c.customer_id
LEFT JOIN lesson_aggregates.order_items AS i
  ON i.order_id = o.order_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Thứ tự trong mảng là **thời gian đặt đơn → ID đơn → số dòng**. Nếu hai đơn cùng thời điểm, `o.order_id` làm tie-breaker. Nếu khách chưa có đơn/item, kết quả là mảng rỗng vì `FILTER` và `COALESCE`.

### Khi cần danh sách tên duy nhất theo khách

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(
        array_agg(
            DISTINCT i.product_name
            ORDER BY i.product_name
        ) FILTER (WHERE i.product_name IS NOT NULL),
        ARRAY[]::text[]
    ) AS distinct_product_names
FROM lesson_aggregates.customers AS c
LEFT JOIN lesson_aggregates.orders AS o
  ON o.customer_id = c.customer_id
LEFT JOIN lesson_aggregates.order_items AS i
  ON i.order_id = o.order_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Ở truy vấn này, tên được **khử trùng và sắp theo chính tên**, không theo thời điểm mua. Hai yêu cầu **“theo lần mua”** và **“theo danh mục tên duy nhất”** là hai hợp đồng dữ liệu khác nhau.

## 25. Tổng hợp có điều kiện theo trạng thái đơn

Giả sử bạn muốn một khách có hai danh sách: các đơn đã thanh toán và các đơn đang chờ.

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(
        array_agg(
            o.order_id ORDER BY o.ordered_at, o.order_id
        ) FILTER (WHERE o.status = 'PAID'),
        ARRAY[]::bigint[]
    ) AS paid_order_ids,
    COALESCE(
        array_agg(
            o.order_id ORDER BY o.ordered_at, o.order_id
        ) FILTER (WHERE o.status = 'PENDING'),
        ARRAY[]::bigint[]
    ) AS pending_order_ids
FROM lesson_aggregates.customers AS c
LEFT JOIN lesson_aggregates.orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Ở đây:

- Một nguồn `LEFT JOIN` phục vụ **hai aggregate với hai điều kiện khác nhau**.
- `FILTER` theo status chọn input của từng mảng.
- `ORDER BY` bên trong mỗi aggregate đảm bảo trình tự ID theo thời gian đơn.
- `COALESCE` trả mảng rỗng `bigint[]` khi khách không có đơn ở trạng thái tương ứng.

Nếu đưa `WHERE o.status = 'PAID'` ở cấp truy vấn, các đơn `PENDING` sẽ bị loại trước khi aggregate thứ hai được tính. Vì thế, **`FILTER` là công cụ phù hợp** khi cần tổng hợp nhiều nhóm điều kiện trong cùng một lần đọc.

## 26. HAVING và lọc sau khi tổng hợp

`WHERE` lọc input trước nhóm; `HAVING` lọc **những nhóm đã được tổng hợp**.

Ví dụ lấy đơn có ít nhất hai dòng sản phẩm, kèm JSON array:

```sql
SELECT
    order_id,
    COUNT(*) AS item_count,
    json_agg(
        json_build_object(
            'line_no', line_no,
            'product', product_name
        )
        ORDER BY line_no
    ) AS items
FROM lesson_aggregates.order_items
GROUP BY order_id
HAVING COUNT(*) >= 2;
```

Với dữ liệu mẫu, chỉ có đơn **1001** đủ hai dòng.

### Không dùng alias SELECT trong HAVING như ORDER BY

Trong cùng query block, viết:

```sql
HAVING COUNT(*) >= 2
```

thay vì dựa vào alias `item_count` của danh sách `SELECT`. Nếu muốn lọc theo alias một cách rõ ràng, đặt aggregate trong CTE và lọc ở query ngoài:

```sql
WITH per_order AS (
    SELECT
        order_id,
        COUNT(*) AS item_count,
        array_agg(product_name ORDER BY line_no) AS names
    FROM lesson_aggregates.order_items
    GROUP BY order_id
)
SELECT *
FROM per_order
WHERE item_count >= 2
ORDER BY order_id;
```

## 27. Có nên dùng array_agg làm chuỗi bằng array_to_string?

PostgreSQL có `array_to_string` để chuyển mảng thành chuỗi:

```sql
SELECT
    order_id,
    array_to_string(
        array_agg(product_name ORDER BY line_no),
        ', '
    ) AS product_list
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Với danh sách tên không null, kết quả tương tự `string_agg(product_name, ', ' ORDER BY line_no)`.

Nhưng nếu input chứa `NULL`, cách xử lý `array_to_string` có tham số thay thế null tùy cách gọi, còn `array_agg` giữ null bên trong mảng. Vì vậy, không nên giả định **mọi cách kết hợp `array_agg` + `array_to_string` luôn tương đương `string_agg`**.

Nếu chỉ cần chuỗi hiển thị, `string_agg` thường ngắn gọn. Nếu cần mảng để thao tác SQL trước khi chuyển sang chuỗi, `array_agg` có lợi.

## 28. ORDER BY khi tổng hợp các giá trị đã định dạng

Một lỗi khác là **sắp theo chuỗi đã định dạng** thay vì kiểu dữ liệu gốc.

Ví dụ số lượng 2, 10, 100:

```sql
WITH values_to_aggregate(n) AS (
    VALUES (2), (10), (100)
)
SELECT
    string_agg(n::text, ', ' ORDER BY n::text) AS text_order,
    string_agg(n::text, ', ' ORDER BY n) AS numeric_order
FROM values_to_aggregate;
```

`text_order` có thể hiển thị **10, 100, 2** theo thứ tự chuỗi của collation phù hợp, trong khi `numeric_order` là **2, 10, 100**.

**Nguyên tắc:** Biểu thức đưa vào aggregate có thể là chuỗi để hiển thị; **sort key nên giữ kiểu gốc** như số, timestamp hoặc priority integer khi cần thứ tự theo giá trị thật.

Tương tự, không sắp timestamp bằng biểu diễn text định dạng `DD/MM/YYYY` nếu ý định là thứ tự thời gian; hãy `ORDER BY timestamp_column`.

## 29. Giới hạn số phần tử trước khi tổng hợp

Giả sử một khách có hàng triệu sự kiện. Dùng:

```sql
SELECT json_agg(event_payload ORDER BY event_time)
FROM big_events
WHERE customer_id = 1;
```

có thể tạo một JSON array rất lớn, tiêu tốn memory, thời gian sắp xếp và băng thông kết nối. Đây là **mẫu minh họa**, bảng `big_events` không được tạo trong bài.

Nếu API chỉ cần **10 sự kiện mới nhất**, phải giới hạn **những hàng input phù hợp trước khi aggregate**.

Ví dụ với dữ liệu đơn hàng mẫu, dùng một truy vấn con có `LIMIT`:

```sql
SELECT COALESCE(
    json_agg(
        json_build_object(
            'order_id', recent.order_id,
            'ordered_at', recent.ordered_at
        )
        ORDER BY recent.ordered_at DESC, recent.order_id DESC
    ),
    '[]'::json
) AS ten_latest_orders
FROM (
    SELECT
        o.order_id,
        o.ordered_at
    FROM lesson_aggregates.orders AS o
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT 10
) AS recent;
```

Ở đây:

1. Subquery xác định **10 đơn mới nhất** theo thứ tự có tie-breaker.
2. Aggregate tạo array từ **tối đa 10 hàng** đó.
3. `ORDER BY` tiếp tục nằm trong `json_agg` để xác định thứ tự phần tử.

Không viết `LIMIT 10` ở cuối aggregate rồi mong nó cắt JSON array về 10 phần tử: `LIMIT` ngoài chỉ giới hạn **số dòng kết quả**, không giới hạn số phần tử bên trong một giá trị đã được tổng hợp.

### Giới hạn N phần tử cho mỗi nhóm

Khi cần **3 đơn mới nhất của mỗi khách**, dùng window function để đánh số trước:

```sql
WITH ranked AS (
    SELECT
        o.customer_id,
        o.order_id,
        o.ordered_at,
        row_number() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.ordered_at DESC, o.order_id DESC
        ) AS rn
    FROM lesson_aggregates.orders AS o
)
SELECT
    customer_id,
    json_agg(
        json_build_object(
            'order_id', order_id,
            'ordered_at', ordered_at
        )
        ORDER BY ordered_at DESC, order_id DESC
    ) AS latest_orders
FROM ranked
WHERE rn <= 3
GROUP BY customer_id
ORDER BY customer_id;
```

`row_number()` quyết định **những hàng được chọn** trong từng nhóm; `ORDER BY` của `json_agg` quyết định **thứ tự những hàng đã chọn** trong array. Hai bước phục vụ hai mục đích khác nhau.

## 30. Hiệu năng và kích thước kết quả aggregate

Không phải lúc nào việc xây toàn bộ danh sách ở database cũng tốt hơn để ứng dụng xử lý từng hàng.

### Chi phí cần xét

- **Sắp xếp theo nhóm:** `ORDER BY` trong aggregate có thể yêu cầu thêm công việc sắp dữ liệu.
- **Bộ nhớ:** một nhóm rất lớn có thể tạo một chuỗi/mảng/JSON lớn; không nên giả định aggregate có thể stream từng phần ra client.
- **Truyền dữ liệu:** JSON array rất dài có thể tăng kích thước response và thời gian parse.
- **Nhân dòng do join:** nếu input bị nhân lên trước aggregate, chi phí và kích thước đều tăng.
- **Chỉ mục:** có thể giúp tạo hoặc lọc đầu vào theo `order_id`/`line_no`, nhưng không bảo đảm planner bỏ mọi thao tác sort trong aggregate.
- **Giới hạn kích thước giá trị:** các kiểu dữ liệu PostgreSQL có giới hạn kích thước và thực tế có thể hết memory trước khi đạt mức tối đa.

### Đo trước khi tối ưu

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    jsonb_agg(
        jsonb_build_object(
            'name', product_name,
            'quantity', quantity
        )
        ORDER BY line_no
    ) AS items
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

`EXPLAIN ANALYZE` **thực thi truy vấn**, vì vậy ở đây dùng ví dụ `SELECT` trên bảng lab. Khi phân tích workload thực, xem các chỉ số thời gian, sort, I/O, row counts và chênh lệch giữa số hàng đầu vào với số hàng sau tổng hợp.

### Index gắn với dạng truy vấn

Trong bảng mẫu, khóa chính `(order_id, line_no)` tạo một B-tree index theo hai cột, thuận lợi cho một số truy vấn lọc `order_id` và cần xử lý theo `line_no`.

Không có nghĩa aggregate `ORDER BY line_no` lúc nào cũng được phục vụ miễn phí bởi chỉ mục; planner quyết định dựa trên số liệu, kiểu scan và các thao tác phía trước.

Với dữ liệu lớn, nên cân nhắc:

1. Có cần tất cả phần tử hay chỉ N phần tử?
2. Có cần sắp theo nhiều khóa không?
3. Có thể aggregate **sau khi lọc** hoặc **trước khi join một-nhiều khác** không?
4. Có phù hợp trả dữ liệu phân trang thay vì một JSON array khổng lồ không?
5. Kích thước nhóm lớn nhất, không chỉ trung bình, là bao nhiêu?

## 31. Truy vấn lồng aggregate và thứ tự phần tử qua nhiều tầng

Khi xây mảng JSON nhiều cấp, **mỗi tầng collection cần quy tắc thứ tự của riêng mình**.

Ví dụ:

```text
Khách hàng An
  └── orders: theo ordered_at ASC, order_id ASC
        └── items: theo line_no ASC
```

Nếu chỉ sắp item theo `line_no` nhưng quên sắp orders, bạn có thể nhận:

```json
{
  "orders": [
    {"order_id": 1002, "items": [{"line_no": 1}]},
    {"order_id": 1001, "items": [{"line_no": 1}, {"line_no": 2}, {"line_no": 3}]}
  ]
}
```

thay vì 1001 trước 1002, dù **mỗi mảng items đã đúng thứ tự**.

Mỗi lời gọi `jsonb_agg` cần `ORDER BY` phù hợp:

```sql
-- Tầng item:
jsonb_agg(item_object ORDER BY line_no)

-- Tầng order:
jsonb_agg(order_object ORDER BY ordered_at, order_id)
```

Hai dòng này minh họa **biểu thức aggregate trong ngữ cảnh truy vấn tương ứng**, không phải một script SQL độc lập có bảng `item_object`/`order_object` sẵn.

## 32. Kết quả SQL và kiểu dữ liệu trong JDBC

Ứng dụng Java thường nhận kết quả aggregate qua `ResultSet`. Với `string_agg`, nhận text:

```java
String sql = """
    SELECT
        order_id,
        string_agg(product_name, ', ' ORDER BY line_no)
            AS product_names
    FROM lesson_aggregates.order_items
    GROUP BY order_id
    ORDER BY order_id
    """;

try (PreparedStatement ps = connection.prepareStatement(sql);
     ResultSet rs = ps.executeQuery()) {
    while (rs.next()) {
        long orderId = rs.getLong("order_id");
        String productNames = rs.getString("product_names");
        // Dùng productNames cho hiển thị.
    }
}
```

Ví dụ giả định `connection` là một JDBC `Connection` đã mở, code nằm trong phương thức có xử lý `SQLException`. Đây là mảnh Java minh họa; cần import và lifecycle phù hợp trong ứng dụng thật.

### Đọc mảng PostgreSQL

`array_agg(product_name)` trả kiểu PostgreSQL `text[]`, có thể nhận bằng JDBC `java.sql.Array`:

```java
String sql = """
    SELECT
        COALESCE(
            array_agg(product_name ORDER BY line_no),
            ARRAY[]::text[]
        ) AS product_names
    FROM lesson_aggregates.order_items
    WHERE order_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 1001L);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            java.sql.Array jdbcArray = rs.getArray("product_names");
            if (jdbcArray != null) {
                try {
                    Object raw = jdbcArray.getArray();
                    // Với pgJDBC và text[] thường có thể nhận String[].
                    String[] names = (String[]) raw;
                    // Sử dụng names theo thứ tự array.
                } finally {
                    jdbcArray.free();
                }
            }
        }
    }
}
```

Việc cast `String[]` là ví dụ khi driver thực tế trả đúng kiểu đó. Trong code đa driver hoặc khi phần tử là kiểu khác, nên kiểm tra loại object và tài liệu driver, không giả định mọi SQL array đều chuyển thành `String[]`.

### Đọc JSON

Với `json_agg`/`jsonb_agg`, pgJDBC có thể cung cấp biểu diễn dạng text hoặc một object đặc thù driver tùy API/getter được sử dụng. Một mẫu đơn giản là:

```java
String sql = """
    SELECT COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'name', product_name,
                'quantity', quantity
            )
            ORDER BY line_no
        ),
        '[]'::jsonb
    ) AS items_json
    FROM lesson_aggregates.order_items
    WHERE order_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 1001L);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            String jsonText = rs.getString("items_json");
            // Dùng JSON parser đáng tin cậy (Jackson, v.v.)
            // thay vì tự tách theo dấu phẩy/ngoặc.
        }
    }
}
```

### Phân biệt SQL NULL và chuỗi rỗng

`ResultSet.getString(...)` có thể trả Java `null` nếu giá trị SQL là `NULL`. Nếu SQL dùng `COALESCE(..., '')`, kết quả là Java string rỗng, không phải null. Thiết kế DTO/API nên phân biệt hai trạng thái theo hợp đồng.

### Thứ tự phần tử là hợp đồng dữ liệu

Nếu client dựa vào phần tử đầu là “món đầu tiên”, SQL phải có **sort key ổn định**, không chỉ tin vào hàng đang lưu theo index. Điều này đặc biệt quan trọng khi kết quả aggregate được cache hoặc trả từ nhiều replica.

## 33. Bảo mật và hợp đồng JSON

`json_agg` rất tiện để tạo response API, nhưng cần chọn trường tường minh:

```sql
SELECT
    order_id,
    json_agg(
        json_build_object(
            'line_no', line_no,
            'product_name', product_name,
            'quantity', quantity
        )
        ORDER BY line_no
    ) AS public_items
FROM lesson_aggregates.order_items
GROUP BY order_id;
```

Không mặc định dùng `json_agg(i)` để đưa mọi cột bảng vào public API, vì schema có thể chứa chi phí nội bộ, thông tin cá nhân hoặc dữ liệu mới được thêm sau này.

Một số nguyên tắc:

- **Chọn key và value rõ ràng** thay vì xuất toàn bộ bảng.
- **Không đưa secret hoặc trường nhạy cảm** vào JSON chỉ vì chúng nằm cùng hàng.
- Giới hạn số phần tử và kích thước response.
- Lọc theo quyền của người dùng **trước khi aggregate**, không gom dữ liệu của tất cả tenant rồi chỉ lọc ở ứng dụng.
- Khi có nhiều nguồn một-nhiều, tổng hợp theo đúng entity để không trộn dữ liệu không liên quan.
- Nếu JSON là giao diện công khai, duy trì versioning/contract và kiểm tra kiểu number/string/null.

## 34. Những lỗi và hiểu nhầm thường gặp

**“ORDER BY cuối câu SELECT quyết định thứ tự trong string_agg.”** Không. Nó sắp các hàng kết quả; cần `ORDER BY` bên trong lời gọi aggregate.

**“Nếu bảng có PRIMARY KEY(order_id, line_no), array_agg sẽ tự theo line_no.”** Không có cam kết như vậy nếu không nêu thứ tự trong aggregate.

**“SELECT * FROM (SELECT ... ORDER BY ...) bảo đảm mọi aggregate ngoài giữ nguyên thứ tự.”** Không đủ tin cậy khi query ngoài có thêm xử lý, nhất là JOIN hoặc nhóm.

**“Chỉ cần ORDER BY giá tiền thì kết quả luôn ổn định.”** Không nếu nhiều item có cùng giá; thêm tie-breaker duy nhất trong nhóm.

**“DISTINCT giữ item có vị trí nhỏ nhất.”** Không. `DISTINCT` chỉ xác định giá trị trùng; muốn lấy dòng xuất hiện đầu tiên phải định nghĩa quy tắc bằng CTE/window/`MIN`.

**“string_agg, array_agg và json_agg xử lý NULL giống nhau.”** Không. `string_agg` bỏ giá trị null, `array_agg` và `json_agg` giữ phần tử null.

**“Không có input thì array_agg tự trả {}.”** Không. Với nhóm không có input, aggregate thường trả SQL `NULL`, trừ khi có logic xử lý khác.

**“LEFT JOIN đơn không có item thì json_agg luôn ra [].”** Không. Hàng giả phía phải có thể tạo `[null]`; dùng `FILTER` và `COALESCE`.

**“COALESCE(array_agg(...), ARRAY[]) luôn suy ra kiểu.”** Không nên phụ thuộc suy luận không rõ; ép kiểu mảng rỗng như `ARRAY[]::text[]`.

**“json_agg trả kiểu text.”** Không. Nó trả `json`; `jsonb_agg` trả `jsonb`, dù một client có thể đọc biểu diễn text.

**“jsonb không giữ thứ tự array.”** Sai. JSON array có thứ tự phần tử; điều không nên dựa vào là thứ tự key trong JSON object.

**“DISTINCT cùng ORDER BY bất kỳ cột nào cũng hợp lệ.”** Không. PostgreSQL đặt ràng buộc lên các biểu thức sắp xếp trong aggregate DISTINCT; cần tiền xử lý khi sort key khác.

**“Dùng DISTINCT sẽ sửa mọi lỗi phần tử bị nhân bản do JOIN.”** Không. Nó có thể xóa cả các dòng hợp lệ có cùng giá trị.

**“Mọi khi cần JSON lồng nhau cứ viết json_agg(json_agg(...)).”** Không. Tổng hợp ở nhiều cấp thường cần CTE/subquery để tạo nguồn đã nhóm.

**“json_agg cả record luôn an toàn cho API.”** Không. Nó có thể vô tình xuất cột mới/nhạy cảm; chọn trường tường minh.

**“LIMIT 10 cuối query làm JSON array chỉ còn 10 phần tử.”** Không. Nó giới hạn số hàng kết quả, không giới hạn các phần tử đã nằm trong một aggregate.

**“string_agg là cách xuất CSV chuẩn.”** Không. Dấu phân cách có thể tồn tại trong input; xuất CSV cần escaping phù hợp.

**“Giá trị NULL và danh sách rỗng là cùng một trạng thái.”** Không. Cần quyết định theo hợp đồng dữ liệu.

## 35. Quy trình xây aggregate có thứ tự cho hệ thống thực

Khi thiết kế một truy vấn trả danh sách phần tử theo entity, có thể đi theo trình tự:

1. **Chọn entity cần một hàng kết quả**: order, customer, category hoặc group khác.
2. **Chọn nguồn input**: bảng item, view, CTE hay tập đã join.
3. **Xác định có nhân dòng do JOIN hay không** trước khi aggregate.
4. **Chọn biểu diễn đầu ra**: chuỗi text, mảng typed hay JSON array/object.
5. **Quyết định giữ trùng hay khử trùng**; nếu khử trùng phải xác định khóa nhận diện phần tử.
6. **Quyết định cách xử lý NULL** và hàng giả từ outer join.
7. **Định nghĩa thứ tự nghiệp vụ** và khóa phụ bảo đảm ổn định.
8. **Đặt `ORDER BY` trong hàm aggregate**, không chỉ cuối query.
9. **Dùng `FILTER`** cho điều kiện riêng từng aggregate khi cần.
10. **Dùng `COALESCE` đúng kiểu** nếu contract yêu cầu chuỗi/mảng rỗng.
11. **Giới hạn phần tử trước khi tổng hợp** nếu response phải phân trang/top-N.
12. **Đo hiệu năng và kích thước nhóm**, nhất là trên dữ liệu lớn.

Sơ đồ:

```text
Nguồn dữ liệu
      │
      ▼
Lọc đúng entity/tenant và quyền truy cập
      │
      ▼
Kiểm soát JOIN, tránh nhân bản hàng
      │
      ▼
Khử trùng / chọn top-N nếu nghiệp vụ cần
      │
      ▼
GROUP BY entity
      │
      ▼
string_agg / array_agg / json_agg
        └── ORDER BY khóa nghiệp vụ + tie-breaker
      │
      ▼
FILTER + COALESCE theo hợp đồng đầu ra
      │
      ▼
Một hàng cho mỗi entity, danh sách có thứ tự
```

Sơ đồ là hướng tư duy. Trong SQL thực, `FILTER` nằm trong cùng biểu thức aggregate chứ không phải một phép biến đổi luôn diễn ra sau tổng hợp; optimizer được phép chọn execution plan khác.

## 36. Bài tập thực hành

### Bài 1 — So sánh ba hàm

Với đơn 1001, viết ba câu biểu thức dùng `string_agg`, `array_agg` và `json_agg` trên `product_name`, đều sắp theo `line_no`. Giải thích sự khác nhau về kiểu trả về và cách sử dụng trong ứng dụng.

### Bài 2 — ORDER BY đúng vị trí

Vì sao câu:

```sql
SELECT order_id, string_agg(product_name, ', ')
FROM lesson_aggregates.order_items
GROUP BY order_id
ORDER BY order_id;
```

**không bảo đảm** tên sản phẩm được ghép theo `line_no`? Viết lại câu truy vấn đúng và chỉ ra hai mục đích `ORDER BY`.

### Bài 3 — Sắp xếp có tie-breaker

Viết `json_agg` trả danh sách sản phẩm của mỗi đơn theo `unit_price DESC`. Khi nhiều item cùng giá, dùng `line_no ASC` làm khóa phụ. Giải thích vì sao chỉ `ORDER BY unit_price` có thể chưa đủ ổn định.

### Bài 4 — Phân biệt NULL

Tính `string_agg(note, ', ')`, `array_agg(note)` và `json_agg(note)` cho đơn 1001. Hãy mô tả ba kết quả và ý nghĩa của phần tử null trong mảng PostgreSQL/JSON.

### Bài 5 — Đơn không có item

Từ `orders LEFT JOIN order_items`, viết câu trả tất cả đơn và cột `items` là JSON array. Đơn 1004 phải có **`[]`**, không phải `[null]` hay SQL `NULL`. Sử dụng `FILTER` theo khóa của item và `COALESCE`.

### Bài 6 — DISTINCT tên sản phẩm

Tạo danh sách **tên sản phẩm duy nhất** của đơn 1001 bằng cả `string_agg` và `array_agg`. Sắp theo `product_name`. Phân biệt kết quả này với danh sách **mọi dòng item** của cùng đơn.

### Bài 7 — DISTINCT theo lần xuất hiện đầu

Muốn mỗi tên chỉ xuất hiện một lần nhưng thứ tự theo **`MIN(line_no)`** của tên đó, hãy dùng CTE nhóm theo `(order_id, product_name)` rồi `string_agg` ở tầng ngoài. Giải thích tại sao không nên viết `string_agg(DISTINCT product_name, ', ' ORDER BY line_no)`.

### Bài 8 — FILTER nhiều điều kiện

Viết một truy vấn trả:

- Tên mọi sản phẩm của đơn.
- Tên những dòng có `quantity >= 2`.
- Mảng các ghi chú `note` không null.

Dùng ba aggregate cùng một `GROUP BY order_id` với `FILTER` thích hợp.

### Bài 9 — JSON objects

Viết `jsonb_agg` tạo mảng các object có `line_no`, `name`, `quantity`, `price`. Sắp theo `line_no`. Giải thích sự khác nhau giữa việc đưa numeric vào JSON object và chuyển tất cả thành text.

### Bài 10 — JSON nhiều cấp

Thiết kế SQL trả **một hàng cho mỗi khách** với JSON array các đơn, mỗi đơn có JSON array item:

1. Gom item theo `order_id`.
2. Ghép kết quả đã gom với `orders`.
3. Gom đơn theo `customer_id`.
4. Giữ thứ tự item theo `line_no` và đơn theo `ordered_at, order_id`.

Đưa ra cách xử lý khách không có đơn và đơn không có item.

### Bài 11 — Nhân số dòng do JOIN

Giả sử đơn 1001 có ba item và hai comment. Nếu join đồng thời `order_items` và `order_comments` rồi `json_agg(product_name)`, có thể xuất hiện bao nhiêu giá trị trong array? Đề xuất cách **aggregate hai nguồn độc lập trước khi join** thay vì lạm dụng `DISTINCT`.

### Bài 12 — Dùng VALUES để minh họa số và chuỗi

Với `VALUES (2), (10), (100)`, so sánh `string_agg(n::text, ', ' ORDER BY n::text)` và `string_agg(n::text, ', ' ORDER BY n)`. Vì sao cách sắp theo chuỗi không nhất thiết là thứ tự số học?

### Bài 13 — Giới hạn 5 phần tử

Viết truy vấn trả JSON array **5 đơn mới nhất của toàn hệ thống**. Dùng subquery `ORDER BY ordered_at DESC, order_id DESC LIMIT 5`, sau đó `json_agg` với cùng thứ tự bên trong. Giải thích vì sao `LIMIT 5` ở ngoài aggregate không đạt yêu cầu.

### Bài 14 — Top 2 trên từng khách

Dùng `row_number() OVER (PARTITION BY customer_id ORDER BY ordered_at DESC, order_id DESC)` để chọn hai đơn mới nhất của **mỗi khách**. Tổng hợp thành `json_agg` theo `customer_id`. Tại sao vừa cần `row_number` vừa cần `ORDER BY` của aggregate?

### Bài 15 — Mảng và unnest

Tạo `array_agg(product_name ORDER BY line_no)` cho đơn 1001, rồi dùng `unnest(... ) WITH ORDINALITY` để mở lại từng phần tử. Viết `ORDER BY ordinality` để hiển thị đúng thứ tự.

### Bài 16 — JSON array và array elements

Tạo `jsonb_agg(jsonb_build_object(... ) ORDER BY line_no)` cho đơn 1001, sau đó dùng `jsonb_array_elements(... ) WITH ORDINALITY`. Đọc thuộc tính `product` bằng `->>` và giải thích vì sao thứ tự khóa trong JSON object không thay thế ordinality của array.

### Bài 17 — Thiết kế API an toàn

Một bảng item có thêm cột `internal_supplier_cost`. Đội backend đang dùng `json_agg(i)` để trả toàn bộ row cho client. Hãy giải thích nguy cơ và sửa sang `json_agg(json_build_object(...))` chỉ bao gồm trường được phép.

### Bài 18 — Chọn thiết kế phù hợp

Với ba tình huống:

1. Báo cáo ngắn cần một chuỗi tên sản phẩm.
2. Logic PostgreSQL cần kiểm tra phần tử bằng `= ANY(...)`.
3. API cần trả danh sách object tên/số lượng/giá.

Hãy chọn `string_agg`, `array_agg` hoặc `json_agg`/`jsonb_agg` phù hợp. Giải thích cách sắp thứ tự và xử lý nhóm không có hàng ở từng lựa chọn.

## Kết luận

**`string_agg`**, **`array_agg`** và **`json_agg`** đều gom nhiều giá trị của một nhóm thành một kết quả, nhưng phục vụ ba nhu cầu khác nhau: **chuỗi hiển thị**, **mảng có kiểu của PostgreSQL** và **mảng JSON cho dữ liệu có cấu trúc**. `jsonb_agg` là biến thể hữu ích khi muốn làm việc tiếp với kiểu `jsonb`.

Điểm cốt lõi là **thứ tự phần tử phải được xác định trong chính aggregate**: `string_agg(value, separator ORDER BY key)`, `array_agg(value ORDER BY key)`, `json_agg(value ORDER BY key)`. `ORDER BY` ở cuối câu truy vấn chỉ sắp **những hàng kết quả**; khóa sắp xếp bị trùng cần tie-breaker rõ ràng.

Khi xử lý dữ liệu thực, hãy phân biệt **`NULL` với mảng rỗng**, biết `string_agg` bỏ qua input null trong khi `array_agg`/`json_agg` giữ null thành phần tử, và kết hợp **`FILTER` + `COALESCE`** để tránh `[null]` từ `LEFT JOIN`. `DISTINCT` có thể khử trùng nhưng không thay thế việc chọn đúng khóa nhận diện hoặc khắc phục join nhân hàng; khi cần sắp các giá trị duy nhất theo khóa khác, hãy tiền xử lý bằng CTE.

Cuối cùng, với JSON nhiều cấp hoặc tập hàng lớn, hãy **tổng hợp theo từng cấp**, giới hạn phần tử trước khi tạo array và đo chi phí sắp xếp/bộ nhớ. Một aggregate được thiết kế tốt không chỉ tạo kết quả đúng hình thức: nó tạo **danh sách đúng phần tử, đúng thứ tự, đúng kiểu và có hợp đồng dữ liệu ổn định** cho những tầng xử lý tiếp theo.

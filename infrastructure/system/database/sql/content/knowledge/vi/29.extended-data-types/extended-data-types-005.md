# Bung mảng JSON thành các hàng theo phương ngữ

Trong dữ liệu JSON, một đơn hàng có thể chứa nhiều sản phẩm ở trường `items`:

```json
{
  "orderId": 101,
  "customer": "C1",
  "items": [
    {"sku": "BK-01", "qty": 2, "unitPrice": 50.00},
    {"sku": "PEN-02", "qty": 3, "unitPrice": 5.00}
  ]
}
```

Một hàng trong bảng đơn hàng chứa **một mảng JSON gồm hai phần tử**. Khi cần nối với danh mục sản phẩm, kiểm tra tồn kho, tính tổng doanh thu hoặc xuất dữ liệu dạng bảng, ta thường muốn **bung mảng** (*expand/unnest/shred/flatten*) thành **hai hàng SQL**:

| order_id | position | sku | qty | unit_price |
| ---: | ---: | --- | ---: | ---: |
| 101 | 1 | BK-01 | 2 | 50.00 |
| 101 | 2 | PEN-02 | 3 | 5.00 |

Đây là phép biến đổi:

```text
Một hàng cha
   │
   ├── JSON array phần tử #1 ──> một hàng con
   │
   └── JSON array phần tử #2 ──> một hàng con

1 hàng cha + mảng 2 phần tử
           ↓
2 hàng kết quả có cùng order_id
```

**SQL không có một cú pháp bung JSON giống hệt trên mọi hệ quản trị.** Các phương ngữ thường dùng:

- **PostgreSQL:** `jsonb_array_elements`, `jsonb_array_elements_text`, `jsonb_to_recordset`, `LATERAL` và `WITH ORDINALITY`.
- **MySQL 8.0:** `JSON_TABLE` với đường dẫn `'$[*]'` hoặc `'$.items[*]'`, các cột `PATH` và `FOR ORDINALITY`.
- **SQL Server:** `OPENJSON` kết hợp `CROSS APPLY` hoặc `OUTER APPLY`, có thể dùng cấu hình `WITH` để ánh xạ thành các cột.
- **Oracle Database:** `JSON_TABLE` cùng các cột `PATH` và `FOR ORDINALITY`.
- **SQLite:** hàm bảng `json_each` cho một cấp và `json_tree` cho cấu trúc lồng nhau.
- **Một số hệ phân tích:** BigQuery dùng `UNNEST` và các hàm JSON; Snowflake dùng `LATERAL FLATTEN`.

Bài thuộc **Database SQL → Dữ liệu mở rộng → Bung mảng JSON thành các hàng theo phương ngữ**. Trọng tâm là **giữ đúng số hàng, giá trị, thứ tự và khóa hàng cha**, đồng thời nhận diện các trường hợp JSON không có mảng, mảng rỗng, `null`, dữ liệu sai kiểu, mảng lồng nhau và dữ liệu được bung để ghi xuống bảng quan hệ.

---

## 1. Phân biệt JSON object, JSON array và JSON scalar

JSON có nhiều loại giá trị:

| JSON | Loại | Có thể bung trực tiếp thành nhiều phần tử không? |
| --- | --- | --- |
| `[1, 2, 3]` | Mảng | Có: ba phần tử |
| `[{"sku":"A"},{"sku":"B"}]` | Mảng object | Có: hai phần tử |
| `[]` | Mảng rỗng | Có, nhưng tạo **0 hàng phần tử** |
| `{"sku":"A"}` | Object | Không phải mảng; phải xác định cách xử lý |
| `"A"` | Chuỗi scalar | Không phải mảng |
| `42` | Số scalar | Không phải mảng |
| `null` | JSON null | Không phải mảng |
| SQL `NULL` | Giá trị SQL thiếu | Không phải chuỗi JSON `"null"` hay JSON null |

Đối với tài liệu:

```json
{"items":[{"sku":"A"},{"sku":"B"}]}
```

ta cần đưa đường dẫn tới mảng `items`. Với tài liệu gốc đã là:

```json
[{"sku":"A"},{"sku":"B"}]
```

đường dẫn là root array, thường biểu diễn bằng `'$[*]'` trong SQL/JSON path hoặc truyền thẳng array cho hàm bung của PostgreSQL.

### Một phần tử JSON không nhất thiết là object

Hai mảng hợp lệ:

```json
["SQL", "Java", "Python"]
```

```json
[null, {"sku":"BK-01","qty":2}, 7]
```

Mảng đầu chứa chuỗi. Mảng sau chứa **các loại phần tử khác nhau**. Nếu ta giả định mọi phần tử là object và cố ánh xạ `sku`/`qty` thành các cột có kiểu, phải chọn cách **bỏ qua, giữ lại để báo lỗi hoặc từ chối** phần tử không đúng schema.

**Bung mảng chỉ là phép mở rộng cấu trúc. Nó không tự bảo đảm dữ liệu đầu vào đúng nghiệp vụ.**

## 2. Mô hình quan hệ: hàng cha, hàng con và bội số hàng

Giả sử bảng `orders` có các hàng:

| order_id | items |
| ---: | --- |
| 101 | `[{"sku":"A"},{"sku":"B"}]` |
| 102 | `[]` |
| 103 | thuộc tính `items` không tồn tại |

Nếu dùng kiểu nối tương tự `CROSS JOIN` đến hàm bung mảng:

- Order 101 tạo **2 hàng**.
- Order 102 tạo **0 hàng**.
- Order 103 có đường dẫn thiếu; với cách xử lý mặc định thường được thiết kế thành **0 hàng**.

Kết quả chỉ còn order 101. Điều này đúng khi yêu cầu là: **“lấy các phần tử thực sự tồn tại trong mảng”**.

Nếu yêu cầu lại là **“giữ tất cả đơn hàng, kể cả đơn không có item”**, ta phải dùng một dạng **LEFT JOIN/OUTER APPLY** phù hợp. Khi đó order 102 và 103 có thể xuất hiện dưới dạng **một hàng cha với các cột phần tử SQL NULL**, nhưng đó **không phải một item thật**.

### Quy tắc số hàng

Với phép bung inner:

```text
Số hàng kết quả = tổng số phần tử mảng của các hàng cha được chọn
```

Với phép giữ hàng cha kiểu left-outer, khi mỗi hàng cha chỉ bung một mảng:

```text
Số hàng kết quả = tổng MAX(1, số phần tử mảng) theo hàng cha
```

Công thức thứ hai tạo hàng **null-extended** khi mảng có 0 phần tử; không được đếm hàng đó là item.

### Chú ý khi nối thêm bảng khác

Nếu mỗi item lại nối với nhiều khuyến mãi, kết quả có thể **nhân thêm hàng** theo số khuyến mãi khớp. Đó là tính chất JOIN một-nhiều, không phải do JSON bị nhân bản sai. Luôn xác định *grain* của kết quả trước khi tổng hợp.

## 3. Ba việc nên xác định trước khi viết SQL

1. **Nguồn JSON nằm ở đâu?** Cột bảng, JSON literal, JSON dạng chuỗi hay kiểu JSON/JSONB gốc?
2. **Mảng ở đường dẫn nào?** Root `'$[*]'`, `'$.items[*]'` hay mảng lồng như `'$.shipments[*].items[*]'`?
3. **Muốn kết quả ở grain nào?** Một hàng cho mỗi item, một hàng cho mỗi order kể cả không có item, hay một hàng tổng hợp theo SKU?

Cũng cần xác định:

- Mỗi item là scalar hay object?
- Có cần **vị trí trong mảng** để giữ thứ tự?
- Mảng rỗng, thiếu thuộc tính, `null` và sai kiểu xử lý thế nào?
- Khi một cột như `qty` sai kiểu, có **bỏ hàng, trả NULL hay phát lỗi**?
- Có cần ghi xuống bảng quan hệ hoặc chỉ đọc?
- Hệ quản trị và phiên bản là gì?

Các câu trả lời đó quyết định cả cú pháp lẫn ngữ nghĩa.

---

## 4. PostgreSQL: tạo bảng dữ liệu thử nghiệm

Phần thực hành chính dùng **PostgreSQL**, vì `jsonb` và `LATERAL` giúp thấy rõ từng bước. Hãy dùng **database/schema thử nghiệm riêng**, không thực thi trên bảng sản xuất.

Tạo bảng:

```sql
CREATE TABLE lab_json_orders_364 (
    order_id INTEGER PRIMARY KEY,
    payload  JSONB NOT NULL
);
```

Nạp các tình huống có chủ ý:

```sql
INSERT INTO lab_json_orders_364 (order_id, payload)
VALUES
(
    101,
    '{
      "customer":"C1",
      "items":[
        {"sku":"BK-01","qty":2,"unitPrice":50.00},
        {"sku":"PEN-02","qty":3,"unitPrice":5.00}
      ]
    }'::jsonb
),
(
    102,
    '{"customer":"C2","items":[]}'::jsonb
),
(
    103,
    '{"customer":"C3"}'::jsonb
),
(
    104,
    '{"customer":"C4","items":null}'::jsonb
),
(
    105,
    '{
      "customer":"C5",
      "items":[{"sku":"BAG-03","qty":null,"unitPrice":120.00}]
    }'::jsonb
),
(
    106,
    '{"customer":"C6","items":"not-an-array"}'::jsonb
),
(
    107,
    '{
      "customer":"C7",
      "items":[null,{"sku":"PEN-02","qty":1,"unitPrice":5.00}]
    }'::jsonb
);
```

Dữ liệu được chia thành bảy trường hợp:

| order_id | Trạng thái của `items` | Số phần tử mảng |
| ---: | --- | ---: |
| 101 | Hai object hợp lệ | 2 |
| 102 | Mảng rỗng `[]` | 0 |
| 103 | Không có thuộc tính `items` | Không xác định; xử lý như 0 |
| 104 | Thuộc tính `items` có JSON `null` | Không phải mảng |
| 105 | Mảng một object với `qty: null` | 1 |
| 106 | `items` là chuỗi, không phải mảng | Không hợp lệ cho thao tác mong muốn |
| 107 | Mảng gồm JSON `null` và một object | 2 |

Việc tách **mảng rỗng**, **mảng không tồn tại**, **JSON null** và **item bên trong là JSON null** là nền tảng để không đếm sai.

## 5. PostgreSQL: jsonb_array_elements

Hàm:

```sql
jsonb_array_elements(jsonb_array)
```

trả một tập hàng, mỗi hàng chứa **một phần tử JSONB** của mảng đầu vào.

Ví dụ không cần bảng:

```sql
SELECT elem
FROM jsonb_array_elements(
    '[{"sku":"A","qty":2},{"sku":"B","qty":3}]'::jsonb
) AS x(elem);
```

Kết quả logic:

| elem |
| --- |
| `{"qty":2,"sku":"A"}` |
| `{"qty":3,"sku":"B"}` |

PostgreSQL `jsonb` có thể chuẩn hóa biểu diễn object và **không bảo đảm giữ nguyên thứ tự các khóa trong object**. Điều đó khác với **thứ tự các phần tử của array**, vốn có ý nghĩa để lấy ra vị trí.

### Lấy cột trong item

```sql
SELECT
    elem ->> 'sku' AS sku,
    (elem ->> 'qty')::INTEGER AS qty
FROM jsonb_array_elements(
    '[{"sku":"A","qty":2},{"sku":"B","qty":3}]'::jsonb
) AS x(elem);
```

- `elem -> 'sku'` lấy giá trị JSONB của khóa.
- `elem ->> 'sku'` lấy giá trị dưới dạng **text SQL**.
- `::INTEGER` chuyển text sang số nguyên; sẽ lỗi nếu giá trị như `"abc"` không chuyển được.
- `->>` với thuộc tính thiếu hoặc JSON null thường cho SQL NULL, không tự báo lỗi nghiệp vụ.

Ví dụ chỉ phù hợp khi nguồn đã được xác nhận là mảng các object có `qty` là số nguyên hợp lệ.

## 6. PostgreSQL: từ mảng trong một cột thành các hàng với LATERAL

Muốn bung trường `payload.items` cho từng order:

```sql
SELECT
    o.order_id,
    e.elem ->> 'sku' AS sku,
    e.elem ->> 'qty' AS qty_text
FROM lab_json_orders_364 AS o
CROSS JOIN LATERAL
    jsonb_array_elements(o.payload -> 'items') AS e(elem)
WHERE o.order_id = 101;
```

Hai hàng kết quả:

| order_id | sku | qty_text |
| ---: | --- | --- |
| 101 | BK-01 | 2 |
| 101 | PEN-02 | 3 |

### Vì sao cần LATERAL?

Hàm bung của **hàng hiện tại** cần tham chiếu `o.payload`. `LATERAL` cho phép thành phần ở `FROM` phía sau dùng cột của thành phần phía trước:

```text
for each order o:
    evaluate jsonb_array_elements(o.payload -> 'items')
    emit one result row for each array element
```

PostgreSQL cho phép tham chiếu cột của bảng trước trong nhiều table function ngay cả khi không ghi tường minh `LATERAL`. Tuy vậy, viết rõ `CROSS JOIN LATERAL` giúp người học và người đọc code hiểu **mối liên hệ theo từng hàng**.

### Cẩn trọng với dữ liệu không phải mảng

Truy vấn trên chỉ lọc order 101, nơi `items` chắc chắn là mảng. Nếu chạy trên toàn bộ bảy hàng, order 104 có JSON null hoặc 106 có chuỗi và hàm có thể **báo lỗi vì đầu vào không phải array**.

Không nên chỉ nghĩ “array rỗng trả 0 hàng” rồi áp dụng cho **mọi loại JSON**.

## 7. PostgreSQL: chuẩn hóa đầu vào thành mảng an toàn

Một mẫu xử lý khi schema cho phép các hàng thiếu/sai loại mảng:

```sql
SELECT
    o.order_id,
    e.elem
FROM lab_json_orders_364 AS o
CROSS JOIN LATERAL jsonb_array_elements(
    CASE
        WHEN jsonb_typeof(o.payload -> 'items') = 'array'
        THEN o.payload -> 'items'
        ELSE '[]'::jsonb
    END
) AS e(elem)
ORDER BY o.order_id;
```

Điều kiện:

```sql
jsonb_typeof(o.payload -> 'items') = 'array'
```

chỉ đúng khi giá trị ở `items` thực sự là JSON array.

| Giá trị của `items` | `jsonb_typeof` | Mảng được truyền vào hàm |
| --- | --- | --- |
| `[{"sku":"A"}]` | `array` | Mảng gốc |
| `[]` | `array` | `[]` |
| Thuộc tính thiếu | SQL NULL | `[]` |
| JSON `null` | `null` | `[]` |
| `"not-an-array"` | `string` | `[]` |

Mẫu này **chọn bỏ qua mảng sai kiểu** như không có item. Đó là một **quyết định nghiệp vụ**, không phải quy tắc tự động đúng cho mọi ứng dụng. Trong pipeline nhập dữ liệu, thường nên **ghi lỗi hoặc từ chối order 106** thay vì lặng lẽ cho rằng nó có 0 sản phẩm.

### Cách nhận diện hàng sai cấu trúc trước khi bung

```sql
SELECT
    order_id,
    jsonb_typeof(payload -> 'items') AS items_type
FROM lab_json_orders_364
WHERE jsonb_typeof(payload -> 'items') IS DISTINCT FROM 'array'
ORDER BY order_id;
```

Trong mẫu, truy vấn tìm các order 103, 104 và 106 vì trường items thiếu, JSON null hoặc là chuỗi. Ứng dụng có thể muốn phân biệt chúng bằng thêm điều kiện `payload ? 'items'`.

---

## 8. PostgreSQL: WITH ORDINALITY giữ vị trí trong mảng

Thứ tự của một query SQL **không được bảo đảm** nếu không có `ORDER BY`, kể cả khi hàm bung thường trả phần tử theo thứ tự array. Nếu cần phục dựng thứ tự item, hãy lấy **vị trí**.

```sql
SELECT
    o.order_id,
    e.ordinal,
    e.elem ->> 'sku' AS sku,
    e.elem ->> 'qty' AS qty_text
FROM lab_json_orders_364 AS o
CROSS JOIN LATERAL jsonb_array_elements(
    CASE
        WHEN jsonb_typeof(o.payload -> 'items') = 'array'
        THEN o.payload -> 'items'
        ELSE '[]'::jsonb
    END
) WITH ORDINALITY AS e(elem, ordinal)
WHERE o.order_id = 101
ORDER BY o.order_id, e.ordinal;
```

Kết quả:

| order_id | ordinal | sku | qty_text |
| ---: | ---: | --- | --- |
| 101 | 1 | BK-01 | 2 |
| 101 | 2 | PEN-02 | 3 |

### Ordinality bắt đầu từ 1 trong PostgreSQL

`WITH ORDINALITY` tạo một cột số thứ tự tăng từ **1** cho các phần tử của tập mà hàm trả.

Đừng nhầm với nhiều cú pháp JSON path có **chỉ số array từ 0**:

```sql
SELECT
    payload #>> '{items,0,sku}' AS first_sku,
    payload #>> '{items,1,sku}' AS second_sku
FROM lab_json_orders_364
WHERE order_id = 101;
```

Ở đây:

- `items,0` là phần tử **đầu tiên**.
- `items,1` là phần tử **thứ hai**.
- `WITH ORDINALITY` cho hai phần tử tương ứng số **1** và **2**.

Khi lưu vị trí sang bảng quan hệ, hãy quy định dùng **1-based ordinal** hay **0-based offset** và chuyển đổi nhất quán.

### Sau khi lọc, ordinal có thể có khoảng trống

Nếu lọc bỏ item thứ nhất:

```sql
WHERE e.ordinal > 1
```

kết quả còn ordinal 2, không tự đánh số lại thành 1. Ordinal là **vị trí gốc**, không phải số thứ tự sau lọc.

## 9. PostgreSQL: CROSS JOIN LATERAL và LEFT JOIN LATERAL

Hai hình dạng thường được dùng nhất:

```sql
-- Chỉ giữ những order có item thật:
CROSS JOIN LATERAL jsonb_array_elements(...) AS e(elem)
```

và:

```sql
-- Giữ cả order khi hàm bung trả 0 hàng:
LEFT JOIN LATERAL jsonb_array_elements(...) AS e(elem)
    ON TRUE
```

Ví dụ đủ để chạy trên cả bảy order:

```sql
SELECT
    o.order_id,
    e.ordinal,
    e.elem ->> 'sku' AS sku,
    e.elem ->> 'qty' AS qty_text
FROM lab_json_orders_364 AS o
LEFT JOIN LATERAL jsonb_array_elements(
    CASE
        WHEN jsonb_typeof(o.payload -> 'items') = 'array'
        THEN o.payload -> 'items'
        ELSE '[]'::jsonb
    END
) WITH ORDINALITY AS e(elem, ordinal)
    ON TRUE
ORDER BY o.order_id, e.ordinal;
```

Kết quả logic:

| order_id | ordinal | sku | qty_text | Ý nghĩa |
| ---: | ---: | --- | --- | --- |
| 101 | 1 | BK-01 | 2 | Item thứ nhất |
| 101 | 2 | PEN-02 | 3 | Item thứ hai |
| 102 | SQL NULL | SQL NULL | SQL NULL | Không có item, hàng cha được giữ |
| 103 | SQL NULL | SQL NULL | SQL NULL | Thiếu items, hàng cha được giữ |
| 104 | SQL NULL | SQL NULL | SQL NULL | items là JSON null |
| 105 | 1 | BAG-03 | SQL NULL | Có object, nhưng qty JSON null |
| 106 | SQL NULL | SQL NULL | SQL NULL | Sai loại mảng, được chuyển thành rỗng |
| 107 | 1 | SQL NULL | SQL NULL | **Một phần tử JSON null thật** |
| 107 | 2 | PEN-02 | 1 | Một object hợp lệ |

Phân biệt rất quan trọng:

- Order **102** có `ordinal IS NULL` → không có phần tử nào được bung.
- Order **107, ordinal=1** có `ordinal=1` → **có một phần tử mảng thật**, dù nó mang JSON null.
- Item **105, ordinal=1** có `qty_text IS NULL` → vẫn có một item; chỉ trường qty là null.

Không được dùng mỗi `sku IS NULL` để kết luận hàng không có item.

## 10. PostgreSQL: COUNT(*) dễ đếm sai với LEFT JOIN

Nếu muốn **đếm số phần tử trong mỗi mảng**, dùng cột ordinal từ hàm bung:

```sql
SELECT
    o.order_id,
    COUNT(e.ordinal) AS array_element_count
FROM lab_json_orders_364 AS o
LEFT JOIN LATERAL jsonb_array_elements(
    CASE
        WHEN jsonb_typeof(o.payload -> 'items') = 'array'
        THEN o.payload -> 'items'
        ELSE '[]'::jsonb
    END
) WITH ORDINALITY AS e(elem, ordinal)
    ON TRUE
GROUP BY o.order_id
ORDER BY o.order_id;
```

Kết quả:

| order_id | array_element_count |
| ---: | ---: |
| 101 | 2 |
| 102 | 0 |
| 103 | 0 |
| 104 | 0 |
| 105 | 1 |
| 106 | 0 |
| 107 | 2 |

Tại sao không dùng `COUNT(*)`?

Vì `LEFT JOIN` giữ lại **một hàng SQL null-extended** cho order 102/103/104/106; `COUNT(*)` sẽ tính chúng thành **1**, dù mảng không chứa item.

Tại sao dùng `COUNT(e.ordinal)` thay vì `COUNT(e.elem)`?

`ordinal` khác NULL khi có **bất kỳ phần tử thật nào**, kể cả phần tử JSON null. Cột JSONB `elem` chứa giá trị JSON `null` khác với SQL NULL ở hàng được left-extend. Dùng ordinal diễn đạt rõ mục đích **đếm số vị trí phần tử**.

---

## 11. JSON null, SQL NULL và thuộc tính không tồn tại

Cần phân biệt ba tình huống:

```json
{"qty":null}
```

```json
{}
```

```text
Không có hàng phần tử (do LEFT JOIN bung mảng rỗng)
```

Cả ba có thể làm cột `qty_text` nhận SQL NULL sau `->>`, nhưng có nghĩa khác nhau.

### 11.1. JSON null là một giá trị JSON

```sql
SELECT
    jsonb_typeof('null'::jsonb) AS type_of_json_null,
    jsonb_typeof(NULL::jsonb) AS type_of_sql_null;
```

Kết quả:

| type_of_json_null | type_of_sql_null |
| --- | --- |
| `null` (chuỗi kiểu dữ liệu) | SQL NULL |

`jsonb_typeof('null'::jsonb)` trả text `'null'`; đây **không phải** SQL NULL.

### 11.2. Phân biệt key vắng với key có JSON null

```sql
SELECT
    order_id,
    payload ? 'items' AS has_items_key,
    jsonb_typeof(payload -> 'items') AS items_type
FROM lab_json_orders_364
WHERE order_id IN (102, 103, 104, 106)
ORDER BY order_id;
```

Dự kiến:

| order_id | has_items_key | items_type |
| ---: | --- | --- |
| 102 | true | array |
| 103 | false | SQL NULL |
| 104 | true | null |
| 106 | true | string |

Đây là thông tin cần thiết nếu API phân biệt:

- Trường **không được gửi**.
- Trường được gửi với JSON `null` (ví dụ muốn xóa giá trị).
- Trường được gửi với `[]` (ví dụ muốn xóa tất cả item).
- Trường được gửi sai schema.

### 11.3. Phân biệt qty thiếu, JSON null và số hợp lệ

Đối với một item object trong PostgreSQL:

```sql
SELECT
    e.elem ? 'qty' AS has_qty_key,
    jsonb_typeof(e.elem -> 'qty') AS qty_type,
    e.elem ->> 'qty' AS qty_text
FROM jsonb_array_elements(
    '[{"qty":2},{"qty":null},{}]'::jsonb
) AS e(elem);
```

Ba trường hợp:

1. `{"qty":2}` → key tồn tại; type `number`; text `'2'`.
2. `{"qty":null}` → key tồn tại; type `null`; text SQL NULL.
3. `{}` → key thiếu; type SQL NULL; text SQL NULL.

Câu `COALESCE(elem->>'qty','0')` sẽ **gộp** trường hợp thiếu và JSON null thành `'0'`. Chỉ làm vậy nếu nghiệp vụ thật sự định nghĩa cả hai giống nhau.

## 12. jsonb_array_elements_text cho mảng scalar

Nếu mảng chỉ gồm chuỗi:

```json
["SQL","Java","Python"]
```

dùng:

```sql
SELECT
    e.ordinal,
    e.value
FROM jsonb_array_elements_text(
    '["SQL","Java","Python"]'::jsonb
) WITH ORDINALITY AS e(value, ordinal)
ORDER BY e.ordinal;
```

| ordinal | value |
| ---: | --- |
| 1 | SQL |
| 2 | Java |
| 3 | Python |

### Mảng số

```sql
SELECT
    e.ordinal,
    e.value_text::INTEGER AS quantity
FROM jsonb_array_elements_text(
    '[2,3,5]'::jsonb
) WITH ORDINALITY AS e(value_text, ordinal);
```

Trả ba số `2, 3, 5`.

### Mảng có JSON null

```sql
SELECT
    e.ordinal,
    e.value_text
FROM jsonb_array_elements_text(
    '["A",null,"B"]'::jsonb
) WITH ORDINALITY AS e(value_text, ordinal);
```

Phần tử `null` có **ordinal=2** nhưng `value_text` là SQL NULL. Nếu muốn phân biệt JSON null với một hàng do left-join giữ lại, cần ordinal hoặc sử dụng phiên bản `jsonb_array_elements` giữ giá trị JSONB.

### Không ép kiểu tùy tiện

`"abc"::INTEGER` sẽ lỗi khi chuyển kiểu. Khi dữ liệu có thể sai kiểu, kiểm tra dạng JSON trước hoặc dùng một bước staging và cơ chế chuyển đổi an toàn theo DBMS.

---

## 13. PostgreSQL: ánh xạ item object sang cột có kiểu

Với mảng toàn object có schema ổn định, PostgreSQL có hàm:

```sql
jsonb_to_recordset(...)
```

Ví dụ độc lập:

```sql
SELECT
    x.sku,
    x.qty,
    x."unitPrice"
FROM jsonb_to_recordset(
    '[
      {"sku":"BK-01","qty":2,"unitPrice":50.00},
      {"sku":"PEN-02","qty":3,"unitPrice":5.00}
    ]'::jsonb
) AS x(
    sku TEXT,
    qty INTEGER,
    "unitPrice" NUMERIC(12, 2)
);
```

Kết quả có cột SQL đã được khai báo kiểu:

| sku | qty | unitPrice |
| --- | ---: | ---: |
| BK-01 | 2 | 50.00 |
| PEN-02 | 3 | 5.00 |

### Vì sao có dấu ngoặc kép quanh unitPrice?

Khóa JSON `unitPrice` dùng camelCase. PostgreSQL chuyển định danh SQL không có ngoặc kép về chữ thường. Khai báo:

```sql
"unitPrice" NUMERIC(12,2)
```

giúp khớp chính xác tên thuộc tính JSON `unitPrice`. Trong query thật, có thể dùng hàm trích xuất `elem ->> 'unitPrice' AS unit_price` để đưa về tên cột snake_case dễ sử dụng.

### Giới hạn của jsonb_to_recordset

Hàm này phù hợp với **mảng các object**. Nếu mảng chứa scalar hoặc JSON null như order 107, không nên giả định mọi phần tử sẽ tự chuyển thành object rỗng. Giá trị sai kiểu khi chuyển sang `INTEGER`/`NUMERIC` có thể gây lỗi.

Với dữ liệu hỗn hợp hoặc muốn giữ vị trí, cách ổn định là:

1. `jsonb_array_elements ... WITH ORDINALITY`.
2. Kiểm tra `jsonb_typeof(elem)`.
3. Trích field theo schema.
4. Kiểm tra và chuyển kiểu theo chính sách ứng dụng.

## 14. PostgreSQL: xử lý object và dữ liệu sai kiểu có kiểm soát

Nếu dữ liệu có phần tử JSON null hoặc scalar, dùng một câu SELECT để phân loại:

```sql
SELECT
    o.order_id,
    e.ordinal,
    jsonb_typeof(e.elem) AS element_type,
    CASE
        WHEN jsonb_typeof(e.elem) = 'object'
        THEN e.elem ->> 'sku'
        ELSE NULL
    END AS sku,
    CASE
        WHEN jsonb_typeof(e.elem -> 'qty') = 'number'
        THEN (e.elem ->> 'qty')::NUMERIC
        ELSE NULL
    END AS qty_number
FROM lab_json_orders_364 AS o
CROSS JOIN LATERAL jsonb_array_elements(
    CASE
        WHEN jsonb_typeof(o.payload -> 'items') = 'array'
        THEN o.payload -> 'items'
        ELSE '[]'::jsonb
    END
) WITH ORDINALITY AS e(elem, ordinal)
ORDER BY o.order_id, e.ordinal;
```

Trong mẫu:

- Item object có số lượng là JSON number được chuyển thành `NUMERIC`.
- Item `{"qty":null}` nhận `qty_number IS NULL`.
- Phần tử JSON null của order 107 được gắn `element_type='null'` và các trường khác NULL.
- Order 102/103/104/106 không tạo hàng phần tử vì dùng `CROSS JOIN` và mảng thay thế rỗng.

### Phát hiện item không đúng schema

Ví dụ lọc những phần tử không phải object hoặc thiếu SKU chuỗi/qty số:

```sql
WITH expanded AS (
    SELECT
        o.order_id,
        e.ordinal,
        e.elem
    FROM lab_json_orders_364 AS o
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE
            WHEN jsonb_typeof(o.payload -> 'items') = 'array'
            THEN o.payload -> 'items'
            ELSE '[]'::jsonb
        END
    ) WITH ORDINALITY AS e(elem, ordinal)
)
SELECT
    order_id,
    ordinal,
    elem,
    jsonb_typeof(elem) AS element_type
FROM expanded
WHERE jsonb_typeof(elem) IS DISTINCT FROM 'object'
   OR jsonb_typeof(elem -> 'sku') IS DISTINCT FROM 'string'
   OR jsonb_typeof(elem -> 'qty') IS DISTINCT FROM 'number'
ORDER BY order_id, ordinal;
```

Truy vấn có thể phát hiện order 105 với `qty=null` và order 107 phần tử đầu là JSON null.

**Một bộ lọc kiểm tra kiểu JSON chưa thay thế toàn bộ validation nghiệp vụ.** Số `-2` vẫn là JSON number; mã SKU chuỗi rỗng vẫn là JSON string. Cần thêm kiểm tra phạm vi, khóa tham chiếu và quy tắc bản ghi.

---

## 15. PostgreSQL: mảng JSON lồng nhau

JSON có thể có cấu trúc:

```json
{
  "shipments": [
    {
      "shipmentId": "S1",
      "items": [
        {"sku":"A","qty":2},
        {"sku":"B","qty":1}
      ]
    },
    {
      "shipmentId": "S2",
      "items": [
        {"sku":"C","qty":4}
      ]
    }
  ]
}
```

Muốn một hàng cho mỗi item ở mỗi shipment, ta bung **hai cấp**:

```sql
WITH doc AS (
    SELECT
        '{
          "shipments":[
            {"shipmentId":"S1",
             "items":[{"sku":"A","qty":2},{"sku":"B","qty":1}]},
            {"shipmentId":"S2",
             "items":[{"sku":"C","qty":4}]}
          ]
        }'::jsonb AS payload
)
SELECT
    s.shipment_pos,
    s.shipment ->> 'shipmentId' AS shipment_id,
    i.item_pos,
    i.item ->> 'sku' AS sku,
    (i.item ->> 'qty')::INTEGER AS qty
FROM doc AS d
CROSS JOIN LATERAL
    jsonb_array_elements(d.payload -> 'shipments')
    WITH ORDINALITY AS s(shipment, shipment_pos)
CROSS JOIN LATERAL
    jsonb_array_elements(s.shipment -> 'items')
    WITH ORDINALITY AS i(item, item_pos)
ORDER BY s.shipment_pos, i.item_pos;
```

Kết quả:

| shipment_pos | shipment_id | item_pos | sku | qty |
| ---: | --- | ---: | --- | ---: |
| 1 | S1 | 1 | A | 2 |
| 1 | S1 | 2 | B | 1 |
| 2 | S2 | 1 | C | 4 |

### Vì sao phải giữ hai loại vị trí?

`item_pos=1` có thể xuất hiện trong **mỗi shipment**. Định danh vị trí tương đối trong tài liệu là cặp:

```text
(shipment_pos, item_pos)
```

không phải `item_pos` một mình.

Với dữ liệu thực, mỗi cấp có thể thiếu, rỗng hoặc sai kiểu; nên áp dụng cơ chế **kiểm tra mảng** tương tự mục 7 ở từng cấp nếu yêu cầu đầu vào không bảo đảm schema.

## 16. PostgreSQL: lọc mảng và filter sau khi bung

Nếu chỉ muốn item có `qty >= 2`:

```sql
WITH expanded AS (
    SELECT
        o.order_id,
        e.ordinal,
        e.elem
    FROM lab_json_orders_364 AS o
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE
            WHEN jsonb_typeof(o.payload -> 'items') = 'array'
            THEN o.payload -> 'items'
            ELSE '[]'::jsonb
        END
    ) WITH ORDINALITY AS e(elem, ordinal)
)
SELECT
    order_id,
    ordinal,
    elem ->> 'sku' AS sku,
    (elem ->> 'qty')::NUMERIC AS qty
FROM expanded
WHERE jsonb_typeof(elem -> 'qty') = 'number'
  AND (elem ->> 'qty')::NUMERIC >= 2
ORDER BY order_id, ordinal;
```

Mục tiêu là giữ những phần tử có số lượng từ 2 trở lên. Khi dữ liệu có giá trị không chuyển được, một điều kiện `WHERE` kết hợp với phép cast ở điều kiện khác **không phải cơ chế validation an toàn tổng quát** vì optimizer có thể sắp xếp đánh giá biểu thức.

Cách an toàn hơn là dùng `CASE` ngay ở biểu thức chuyển đổi để chỉ cast khi dạng JSON phù hợp:

```sql
WITH expanded AS (
    SELECT
        o.order_id,
        e.ordinal,
        e.elem,
        CASE
            WHEN jsonb_typeof(e.elem -> 'qty') = 'number'
            THEN (e.elem ->> 'qty')::NUMERIC
            ELSE NULL
        END AS qty_num
    FROM lab_json_orders_364 AS o
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE
            WHEN jsonb_typeof(o.payload -> 'items') = 'array'
            THEN o.payload -> 'items'
            ELSE '[]'::jsonb
        END
    ) WITH ORDINALITY AS e(elem, ordinal)
)
SELECT order_id, ordinal, elem ->> 'sku' AS sku, qty_num
FROM expanded
WHERE qty_num >= 2
ORDER BY order_id, ordinal;
```

Nếu schema yêu cầu **số nguyên dương**, cần kiểm tra thêm độ nguyên, miền giá trị và chính sách xử lý giá trị quá lớn thay vì chỉ dùng `NUMERIC >= 2`.

### Không mất vị trí gốc

Giả sử item thứ nhất không đạt điều kiện, item thứ hai đạt. `ordinal` vẫn bằng **2** trong kết quả, vì nó là vị trí mảng trước khi lọc.

---

## 17. PostgreSQL: tổng hợp sau khi bung

Một lý do chính của việc bung item là tính doanh thu theo SKU. Với dữ liệu được kiểm soát:

```sql
SELECT
    e.elem ->> 'sku' AS sku,
    SUM(
        (e.elem ->> 'qty')::NUMERIC
        *
        (e.elem ->> 'unitPrice')::NUMERIC
    ) AS amount
FROM lab_json_orders_364 AS o
CROSS JOIN LATERAL jsonb_array_elements(
    o.payload -> 'items'
) AS e(elem)
WHERE o.order_id = 101
GROUP BY e.elem ->> 'sku'
ORDER BY sku;
```

Với order 101:

| sku | amount |
| --- | ---: |
| BK-01 | 100.00 |
| PEN-02 | 15.00 |

Tổng là **115.00**.

### Tại sao chỉ chọn order 101?

Bởi vì mục 17 dùng phép cast trực tiếp và đầu vào `items` của order 101 đã biết gồm hai object hợp lệ. Trên bảng có order 106 (items là chuỗi) hoặc 107 (item JSON null), muốn tổng hợp toàn hệ phải **chuẩn hóa và validate** như các mục trước.

### Grain của phép tính

Đầu vào sau bung có grain:

```text
(order_id, item_position)
```

Sau `GROUP BY sku`, grain thành:

```text
(sku)
```

Nếu một SKU xuất hiện nhiều lần trong cùng hoặc khác order, `SUM` sẽ cộng các dòng phù hợp. Nếu JOIN với bảng khuyến mãi một-nhiều trước khi tính tổng mà không kiểm soát quan hệ, tổng có thể **bị nhân bản**.

### Đơn giá là tiền

Nếu `unitPrice` dùng cho tiền, nên chuyển thành `NUMERIC/DECIMAL` chính xác phù hợp phạm vi tiền tệ, không tùy tiện dùng `FLOAT` rồi kỳ vọng tính toán thập phân chính xác tuyệt đối.

---

## 18. PostgreSQL: lọc order theo nội dung JSON mà chưa cần bung

Không phải yêu cầu nào cũng cần mở toàn bộ mảng. Nếu chỉ muốn **tìm order có SKU BK-01**, có thể cân nhắc toán tử containment trên `jsonb`:

```sql
SELECT order_id
FROM lab_json_orders_364
WHERE payload @> '{"items":[{"sku":"BK-01"}]}'::jsonb;
```

Toán tử `@>` kiểm tra containment theo ngữ nghĩa `jsonb`. Với dữ liệu mẫu, order 101 khớp.

### Khi nào bung, khi nào tìm trong JSON?

| Mục tiêu | Lựa chọn có thể phù hợp |
| --- | --- |
| Lấy **một hàng cho mỗi item** | Bung bằng `jsonb_array_elements` |
| Đếm/thống kê số item theo order | Bung hoặc thao tác độ dài array nếu đã xác thực |
| Tìm **order có ít nhất một item khớp** | Containment/path predicate hoặc `EXISTS`, tùy yêu cầu |
| Lấy item kèm vị trí trong mảng | Bung với `WITH ORDINALITY` |
| JOIN từng SKU với bảng danh mục | Bung các item ra hàng |
| Tìm một key trong hàng triệu documents | Cân nhắc index JSONB và đo thực tế |

Một index GIN trên `jsonb` có thể hỗ trợ **một số toán tử tìm kiếm JSON**, nhưng không có nghĩa nó làm mọi truy vấn `jsonb_array_elements` hoặc mọi aggregate nhanh.

**Không nên bung toàn bộ JSON chỉ để biết có một phần tử tồn tại**, nếu một predicate phù hợp và index được thiết kế có thể giải quyết nhu cầu gọn hơn.

---

## 19. MySQL 8.0: JSON_TABLE để chuyển array thành quan hệ

Trong MySQL hiện đại, `JSON_TABLE` là cơ chế quan trọng để chuyển tài liệu JSON theo một đường dẫn thành bảng các cột có kiểu.

Một mẫu độc lập:

```sql
SELECT
    jt.ordinal,
    jt.sku,
    jt.qty
FROM JSON_TABLE(
    '[
      {"sku":"BK-01","qty":2},
      {"sku":"PEN-02","qty":3}
    ]',
    '$[*]'
    COLUMNS (
        ordinal FOR ORDINALITY,
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt
ORDER BY jt.ordinal;
```

Kết quả:

| ordinal | sku | qty |
| ---: | --- | ---: |
| 1 | BK-01 | 2 |
| 2 | PEN-02 | 3 |

### Các thành phần

- Đối số đầu tiên là biểu thức JSON nguồn.
- `'$[*]'` chọn **mỗi phần tử của mảng gốc** để tạo một row.
- `COLUMNS(...)` định nghĩa các cột SQL được trích từ mỗi phần tử.
- `FOR ORDINALITY` gắn vị trí **bắt đầu từ 1**.
- `PATH '$.sku'` đọc thuộc tính `sku` bên trong **item hiện tại**, không phải toàn tài liệu.

MySQL `JSON_TABLE` có mặt ở dòng MySQL 8.0 (từ các bản 8.0 đầu); cần kiểm tra phiên bản máy chủ. Không nên copy nguyên cú pháp này cho MySQL 5.7.

## 20. MySQL: JSON_TABLE từ cột của từng order

Giả sử MySQL có bảng:

```sql
CREATE TABLE lab_json_orders_mysql_364 (
    order_id INT PRIMARY KEY,
    payload JSON NOT NULL
);
```

Nạp dữ liệu:

```sql
INSERT INTO lab_json_orders_mysql_364 (order_id, payload)
VALUES
    (101, '{
       "customer":"C1",
       "items":[
         {"sku":"BK-01","qty":2},
         {"sku":"PEN-02","qty":3}
       ]
    }'),
    (102, '{"customer":"C2","items":[]}'),
    (103, '{"customer":"C3"}');
```

Bung thành hàng:

```sql
SELECT
    o.order_id,
    jt.ordinal,
    jt.sku,
    jt.qty
FROM lab_json_orders_mysql_364 AS o
JOIN JSON_TABLE(
    o.payload,
    '$.items[*]'
    COLUMNS (
        ordinal FOR ORDINALITY,
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt ON TRUE
ORDER BY o.order_id, jt.ordinal;
```

Kết quả inner: chỉ order 101 có hai hàng. Order 102 và 103 không có phần tử tại `$.items[*]` nên không tạo item row.

### MySQL JSON_TABLE có ngữ nghĩa lateral

`JSON_TABLE` có thể tham chiếu các cột bảng đứng trước trong `FROM` theo cơ chế được hỗ trợ; không cần, và trong MySQL không dùng cách viết `LATERAL JSON_TABLE(...)` y hệt một derived table PostgreSQL.

### Giữ order không có item bằng LEFT JOIN

```sql
SELECT
    o.order_id,
    jt.ordinal,
    jt.sku,
    jt.qty
FROM lab_json_orders_mysql_364 AS o
LEFT JOIN JSON_TABLE(
    o.payload,
    '$.items[*]'
    COLUMNS (
        ordinal FOR ORDINALITY,
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt ON TRUE
ORDER BY o.order_id, jt.ordinal;
```

Order 102/103 được giữ với cột `jt.ordinal IS NULL`. Nếu muốn đếm **phần tử thật**, dùng `COUNT(jt.ordinal)`, không dùng `COUNT(*)`.

### Đường dẫn từ root so với từ items

Hai cách tương đương về ý tưởng trong dữ liệu đúng schema:

```sql
JSON_TABLE(o.payload, '$.items[*]' COLUMNS (...))
```

và:

```sql
JSON_TABLE(
  JSON_EXTRACT(o.payload, '$.items'),
  '$[*]' COLUMNS (...)
)
```

Cách hai giúp nhìn rõ việc lấy mảng `items` trước rồi mới bung. Khi mảng thiếu hoặc có giá trị không phải array, cần xác định ngữ nghĩa lỗi/không khớp theo MySQL và thiết kế input validation phù hợp.

---

## 21. MySQL: PATH, ON EMPTY, ON ERROR và JSON null

`JSON_TABLE` có thể khai báo cách xử lý khi:

- **Đường dẫn không có dữ liệu** (*ON EMPTY*).
- **Giá trị không chuyển được hoặc phát sinh lỗi chuyển đổi** (*ON ERROR*).

Ví dụ:

```sql
SELECT
    jt.ordinal,
    jt.sku,
    jt.qty
FROM JSON_TABLE(
    '[
       {"sku":"A","qty":2},
       {"sku":"B"},
       {"sku":"C","qty":"bad"}
    ]',
    '$[*]'
    COLUMNS (
        ordinal FOR ORDINALITY,
        sku VARCHAR(40) PATH '$.sku'
            NULL ON EMPTY
            NULL ON ERROR,
        qty INT PATH '$.qty'
            NULL ON EMPTY
            NULL ON ERROR
    )
) AS jt
ORDER BY jt.ordinal;
```

Với chính sách trên, các giá trị qty thiếu/sai kiểu có thể được ánh xạ thành SQL NULL theo quy tắc MySQL. Nhưng **không phải mọi vấn đề chuyển đổi số đều im lặng**: một số truncation hoặc conversion có thể sinh cảnh báo theo phiên bản và SQL mode.

### Khi nào nên dùng ERROR ON ERROR?

Trong nhập liệu chặt chẽ, việc thay qty sai thành NULL có thể che lỗi nguồn. Có thể chọn hướng báo lỗi hoặc tách tầng validation, thay vì cho pipeline đi tiếp với số lượng không xác định.

### JSON null theo phiên bản

MySQL thay đổi hành vi `JSON_TABLE` đối với trường hợp biểu thức JSON path cho JSON `null` ở các phiên bản 8.0: từ MySQL 8.0.21, JSON null được xử lý theo hướng trả SQL NULL phù hợp hơn, trong khi các bản cũ có thể báo lỗi ở tình huống tương ứng. Khi cần tương thích bản cũ, phải kiểm tra chính xác phiên bản.

### Đừng nhầm vị trí mảng với id

`FOR ORDINALITY` trả 1,2,3... trong mỗi lần mở mảng; nó không phải khóa định danh item bền vững nếu ứng dụng cho phép thêm/xóa hoặc đổi thứ tự phần tử. Nếu item có `itemId` độc lập, nên giữ khóa đó cho quan hệ nghiệp vụ.

---

## 22. SQL Server: OPENJSON ở chế độ mặc định

SQL Server hỗ trợ `OPENJSON` để duyệt JSON object hoặc array. Với array, chế độ mặc định trả ba cột:

- `[key]`: vị trí phần tử trong array, dạng khóa văn bản.
- `[value]`: giá trị của phần tử theo biểu diễn SQL phù hợp.
- `[type]`: mã kiểu JSON của giá trị.

Ví dụ:

```sql
-- SQL Server; yêu cầu database compatibility level hỗ trợ OPENJSON.
SELECT
    j.[key] AS index_text,
    j.[value] AS json_element,
    j.[type] AS json_type_code
FROM OPENJSON(
    N'[
      {"sku":"BK-01","qty":2},
      {"sku":"PEN-02","qty":3}
    ]'
) AS j
ORDER BY TRY_CONVERT(INT, j.[key]);
```

Hai object có `[key]` là `'0'` và `'1'`. **OPENJSON dùng chỉ số mảng từ 0** khi trả cột key trong chế độ mặc định.

### Các type code thường gặp

| `type` | Ý nghĩa |
| ---: | --- |
| 0 | JSON null |
| 1 | Chuỗi |
| 2 | Số |
| 3 | Boolean |
| 4 | Array |
| 5 | Object |

Với JSON object dạng phần tử, `j.[type]=5`.

### Chuyển object thành cột

```sql
SELECT
    TRY_CONVERT(INT, j.[key]) AS offset0,
    JSON_VALUE(j.[value], '$.sku') AS sku,
    TRY_CONVERT(
        INT,
        JSON_VALUE(j.[value], '$.qty')
    ) AS qty
FROM OPENJSON(
    N'[
      {"sku":"BK-01","qty":2},
      {"sku":"PEN-02","qty":3}
    ]'
) AS j
WHERE j.[type] = 5
ORDER BY offset0;
```

`JSON_VALUE` trích scalar. `TRY_CONVERT` cho SQL NULL thay vì lỗi với nhiều giá trị không chuyển được, giúp bước đọc bớt mong manh, nhưng **SQL NULL không tự xác định dữ liệu đó hợp lệ hay không**.

### OPENJSON và compatibility level

`OPENJSON` yêu cầu database compatibility level phù hợp, thường là **130 trở lên**. Một SQL Server instance hiện đại nhưng database vẫn ở compatibility level cũ có thể không nhận diện `OPENJSON`. Kiểm tra cấu hình của database cụ thể, không chỉ phiên bản engine.

---

## 23. SQL Server: CROSS APPLY và OUTER APPLY với JSON array

Giả sử bảng SQL Server:

```sql
CREATE TABLE dbo.lab_json_orders_364 (
    order_id INT NOT NULL PRIMARY KEY,
    payload NVARCHAR(MAX) NOT NULL,
    CONSTRAINT ck_json_orders_364
        CHECK (ISJSON(payload) = 1)
);
```

Nạp ba hàng:

```sql
INSERT INTO dbo.lab_json_orders_364 (order_id, payload)
VALUES
    (101, N'{"items":[{"sku":"BK-01","qty":2},
                      {"sku":"PEN-02","qty":3}]}'),
    (102, N'{"items":[]}'),
    (103, N'{"customer":"C3"}');
```

Dùng `CROSS APPLY` để gọi `OPENJSON` trên mảng của từng order:

```sql
SELECT
    o.order_id,
    TRY_CONVERT(INT, j.[key]) AS offset0,
    JSON_VALUE(j.[value], '$.sku') AS sku,
    TRY_CONVERT(INT, JSON_VALUE(j.[value], '$.qty')) AS qty
FROM dbo.lab_json_orders_364 AS o
CROSS APPLY OPENJSON(o.payload, '$.items') AS j
WHERE j.[type] = 5
ORDER BY o.order_id, TRY_CONVERT(INT, j.[key]);
```

`CROSS APPLY` có vai trò tương tự **inner lateral join**: order không có phần tử tương ứng không tạo hàng.

### OUTER APPLY để giữ hàng cha

```sql
SELECT
    o.order_id,
    TRY_CONVERT(INT, j.[key]) AS offset0,
    JSON_VALUE(j.[value], '$.sku') AS sku
FROM dbo.lab_json_orders_364 AS o
OUTER APPLY OPENJSON(o.payload, '$.items') AS j
ORDER BY o.order_id, TRY_CONVERT(INT, j.[key]);
```

Order 102 và 103 được giữ với các cột từ `j` là SQL NULL.

### Lưu ý khi trích field

`OPENJSON` mặc định cho cột `[value]`; khi phần tử là object, JSON được trả dưới dạng text nên `JSON_VALUE(j.[value], '$.sku')` dùng để lấy scalar bên trong nó.

Khi phần tử là JSON null hoặc scalar, cố áp path object có thể cho SQL NULL hoặc gây hành vi không mong muốn tùy dữ liệu và chế độ; vì vậy mẫu inner có `WHERE j.[type] = 5` để chỉ lấy object. Với dữ liệu không đồng nhất, nên giữ cột `type` để phân loại và báo lỗi.

## 24. SQL Server: OPENJSON WITH định nghĩa cột có kiểu

Nếu chắc chắn mảng chỉ gồm object phù hợp, có thể khai báo schema:

```sql
SELECT
    o.order_id,
    x.sku,
    x.qty
FROM dbo.lab_json_orders_364 AS o
CROSS APPLY OPENJSON(
    o.payload,
    '$.items'
) WITH (
    sku NVARCHAR(40) '$.sku',
    qty INT '$.qty'
) AS x
ORDER BY o.order_id, x.sku;
```

`WITH` giúp khai báo cột cần lấy; nhưng nó **không trả các cột mặc định `[key]`, `[value]`, `[type]`**. Nếu cần **vị trí trong mảng**, hãy giữ bước `OPENJSON` mặc định để lấy `[key]` rồi trích thông tin từ `[value]`.

### Một cách giữ vị trí và chuyển kiểu

```sql
SELECT
    o.order_id,
    TRY_CONVERT(INT, j.[key]) AS offset0,
    x.sku,
    x.qty
FROM dbo.lab_json_orders_364 AS o
CROSS APPLY OPENJSON(o.payload, '$.items') AS j
CROSS APPLY OPENJSON(j.[value])
WITH (
    sku NVARCHAR(40) '$.sku',
    qty INT '$.qty'
) AS x
WHERE j.[type] = 5
ORDER BY o.order_id, TRY_CONVERT(INT, j.[key]);
```

Với object hợp lệ, cách này có thể mở một object thành một hàng cột đã định nghĩa. Khi nguồn hỗn hợp, tránh dùng `OPENJSON` trên scalar/null một cách mù quáng và nên có bước lọc/validation rõ ràng.

### Lưu ý tên thuộc tính JSON

JSON path và cách khớp tên thuộc tính của `OPENJSON` có các quy tắc kiểu so sánh **case-sensitive theo BIN2** trong nhiều ngữ cảnh, không nhất thiết theo collation thông thường của bảng. `'$.sku'` và `'$.SKU'` không nên được coi là luôn cùng một thuộc tính.

### Nếu scalar quá dài

`JSON_VALUE` kiểu trả thông thường có giới hạn về độ dài chuỗi scalar trong SQL Server. Với giá trị lớn, cân nhắc `OPENJSON WITH` khai báo `NVARCHAR(MAX)` theo nhu cầu, thay vì mặc định mọi chuỗi JSON có thể đi qua `JSON_VALUE` mà không bị giới hạn.

---

## 25. Oracle Database: JSON_TABLE và FOR ORDINALITY

Trong Oracle, `JSON_TABLE` chuyển cấu trúc JSON thành bảng có các cột xác định bằng SQL/JSON path. Cú pháp gần về ý tưởng với MySQL nhưng **kiểu dữ liệu, cơ chế lỗi, khả năng JSON native và phiên bản khác nhau**.

Ví dụ:

```sql
-- Oracle Database: ví dụ JSON literal.
SELECT
    jt.ordinal,
    jt.sku,
    jt.qty
FROM JSON_TABLE(
    '[
      {"sku":"BK-01","qty":2},
      {"sku":"PEN-02","qty":3}
    ]',
    '$[*]'
    COLUMNS (
        ordinal FOR ORDINALITY,
        sku VARCHAR2(40) PATH '$.sku',
        qty NUMBER PATH '$.qty'
    )
) jt
ORDER BY jt.ordinal;
```

Kết quả:

| ordinal | sku | qty |
| ---: | --- | ---: |
| 1 | BK-01 | 2 |
| 2 | PEN-02 | 3 |

### Phân tích cú pháp

- `'$[*]'`: tạo row từ từng phần tử root array.
- `COLUMNS`: ánh xạ thuộc tính của item thành các cột SQL.
- `FOR ORDINALITY`: số thứ tự từ **1**.
- `VARCHAR2` và `NUMBER`: kiểu dữ liệu Oracle, khác `VARCHAR`/`INT` của MySQL.

### JSON lưu ở kiểu gì?

Tùy phiên bản Oracle, nguồn JSON có thể ở cột văn bản/BLOB có ràng buộc `IS JSON` hoặc kiểu JSON native mới hơn. Không nên dùng một cú pháp DDL cụ thể cho mọi đời Oracle; ví dụ tập trung vào việc **bung array**.

## 26. Oracle: bung mảng từ cột và giữ hàng cha

Giả sử bảng Oracle `orders` có:

```text
order_id NUMBER
payload  CLOB hoặc JSON theo phiên bản
```

Bung array của từng order:

```sql
SELECT
    o.order_id,
    jt.ordinal,
    jt.sku,
    jt.qty
FROM orders o
CROSS APPLY JSON_TABLE(
    o.payload,
    '$.items[*]'
    COLUMNS (
        ordinal FOR ORDINALITY,
        sku VARCHAR2(40) PATH '$.sku',
        qty NUMBER PATH '$.qty'
    )
) jt
ORDER BY o.order_id, jt.ordinal;
```

Muốn giữ order không có phần tử:

```sql
SELECT
    o.order_id,
    jt.ordinal,
    jt.sku,
    jt.qty
FROM orders o
OUTER APPLY JSON_TABLE(
    o.payload,
    '$.items[*]'
    COLUMNS (
        ordinal FOR ORDINALITY,
        sku VARCHAR2(40) PATH '$.sku',
        qty NUMBER PATH '$.qty'
    )
) jt
ORDER BY o.order_id, jt.ordinal;
```

`CROSS APPLY` và `OUTER APPLY` minh họa liên hệ lateral giữa hàng `orders` và mảng JSON của nó ở những phiên bản Oracle hỗ trợ. Một số dạng SQL có thể viết bằng phép join lateral/JSON_TABLE khác theo phiên bản.

### Lỗi và giá trị thiếu

Oracle SQL/JSON path có **lax/strict semantics** và các cơ chế xử lý `ON ERROR`/`ON EMPTY`. Mặc định và giới hạn có thể thay đổi theo clause và phiên bản. Nếu pipeline cần phân biệt **thiếu thuộc tính, JSON null và dữ liệu sai kiểu**, phải quy định hành vi rõ thay vì dựa vào default.

### Nested paths trong Oracle

Oracle `JSON_TABLE` còn có `NESTED PATH` để biểu diễn dữ liệu lồng. Khi dùng nhiều cấp mảng, cần xác định đúng row path của từng cấp và xem cách các nhóm cột lồng được nối theo SQL/JSON semantics, không chỉ nhân cơ học mọi bảng.

Ví dụ định hướng:

```sql
SELECT jt.*
FROM JSON_TABLE(
    '{"shipments":[{"shipmentId":"S1",
      "items":[{"sku":"A"},{"sku":"B"}]}]}',
    '$'
    COLUMNS (
        NESTED PATH '$.shipments[*]'
        COLUMNS (
            shipment_id VARCHAR2(30) PATH '$.shipmentId',
            NESTED PATH '$.items[*]'
            COLUMNS (
                item_pos FOR ORDINALITY,
                sku VARCHAR2(40) PATH '$.sku'
            )
        )
    )
) jt;
```

Cú pháp nested columns cụ thể nên được đối chiếu tài liệu của phiên bản Oracle triển khai trước khi áp dụng rộng.

---

## 27. SQLite: json_each để bung một cấp

SQLite có các hàm JSON như `json_extract` và các **table-valued functions** `json_each`, `json_tree` (khi build SQLite có JSON functionality phù hợp).

`json_each` đi qua các phần tử trực tiếp của array hoặc các thuộc tính trực tiếp của object.

Ví dụ:

```sql
SELECT
    j.key AS offset0,
    j.value,
    j.type
FROM json_each(
    '[{"sku":"BK-01","qty":2},
      {"sku":"PEN-02","qty":3}]'
) AS j
ORDER BY CAST(j.key AS INTEGER);
```

Với array, `key` là **chỉ số từ 0**; với object, `key` là tên thuộc tính. Vì vậy, `json_each` không tự ép input thành array. Cần kiểm tra loại root nếu logic yêu cầu mảng.

### Lấy field từ mỗi object

```sql
SELECT
    CAST(j.key AS INTEGER) AS offset0,
    json_extract(j.value, '$.sku') AS sku,
    json_extract(j.value, '$.qty') AS qty
FROM json_each(
    '[{"sku":"BK-01","qty":2},
      {"sku":"PEN-02","qty":3}]'
) AS j
WHERE j.type = 'object'
ORDER BY offset0;
```

Kết quả:

| offset0 | sku | qty |
| ---: | --- | ---: |
| 0 | BK-01 | 2 |
| 1 | PEN-02 | 3 |

SQLite `json_extract` với một path thường trả **giá trị SQL tương ứng** cho scalar, chứ không luôn trả JSON text. Cần kiểm tra khi xử lý mảng/object và khi chuyển code từ MySQL/SQL Server sang SQLite.

## 28. SQLite: json_each từ cột và LEFT JOIN

Giả sử:

```sql
CREATE TABLE lab_json_orders_sqlite_364 (
    order_id INTEGER PRIMARY KEY,
    payload TEXT NOT NULL CHECK (json_valid(payload))
);

INSERT INTO lab_json_orders_sqlite_364 (order_id, payload)
VALUES
    (101, '{"items":[{"sku":"BK-01","qty":2},
                      {"sku":"PEN-02","qty":3}]}'),
    (102, '{"items":[]}'),
    (103, '{"customer":"C3"}');
```

Bung:

```sql
SELECT
    o.order_id,
    CAST(j.key AS INTEGER) AS offset0,
    json_extract(j.value, '$.sku') AS sku,
    json_extract(j.value, '$.qty') AS qty
FROM lab_json_orders_sqlite_364 AS o
JOIN json_each(o.payload, '$.items') AS j
WHERE j.type = 'object'
ORDER BY o.order_id, offset0;
```

SQLite cho phép table function `json_each` tham chiếu cột `o.payload` của bảng đứng trước trong `FROM` theo cơ chế riêng.

### Giữ order rỗng

```sql
SELECT
    o.order_id,
    j.key AS offset0,
    CASE
        WHEN j.type = 'object'
        THEN json_extract(j.value, '$.sku')
        ELSE NULL
    END AS sku
FROM lab_json_orders_sqlite_364 AS o
LEFT JOIN json_each(o.payload, '$.items') AS j
    ON TRUE
ORDER BY o.order_id, j.key;
```

Order 102 và 103 có hàng cha với `j.key IS NULL`. Nếu muốn đếm các phần tử thật, dùng `COUNT(j.key)` theo từng order; `COUNT(*)` tính cả hàng null-extended.

### Điều kiện nguồn đúng array

Khi cần chống sai loại, SQLite hỗ trợ `json_valid` và `json_type`. Một cách rõ ràng là dùng `CASE` trả mảng rỗng khi đầu vào không đúng:

```sql
SELECT
    o.order_id,
    j.key,
    j.value
FROM lab_json_orders_sqlite_364 AS o
LEFT JOIN json_each(
    CASE
        WHEN json_type(o.payload, '$.items') = 'array'
        THEN json_extract(o.payload, '$.items')
        ELSE '[]'
    END
) AS j ON TRUE
ORDER BY o.order_id, j.key;
```

Vì cột `payload` có CHECK `json_valid`, ta có thể gọi `json_type` trên tài liệu hợp lệ. Nếu cột nguồn **có thể chứa JSON sai cú pháp**, cần kiểm tra `json_valid` **trước** khi gọi các hàm có thể lỗi trên JSON invalid, thay vì chỉ viết hai điều kiện `WHERE` và hy vọng hệ tự đánh giá theo thứ tự mong muốn.

---

## 29. SQLite: json_tree cho dữ liệu lồng nhau

`json_each` đi qua **một cấp**; `json_tree` có thể duyệt **đệ quy** cấu trúc JSON và trả các hàng ở nhiều cấp.

Ví dụ:

```sql
SELECT
    j.id,
    j.parent,
    j.key,
    j.fullkey,
    j.type,
    j.value
FROM json_tree(
    '{
      "shipments":[
        {"shipmentId":"S1",
         "items":[{"sku":"A"},{"sku":"B"}]}
      ]
    }'
) AS j
WHERE j.type = 'text'
ORDER BY j.id;
```

Các cột như:

- `id`: mã nội bộ nhận diện node trong kết quả duyệt.
- `parent`: mã node cha.
- `fullkey`: đường dẫn đầy đủ tới node.
- `type`: loại JSON.
- `value`: giá trị.

**Không dùng `json_tree.id` làm định danh nghiệp vụ bền vững.** SQLite không bảo đảm ý nghĩa liên phiên bản cho cách đánh số node; nếu cần ID ổn định, dữ liệu JSON phải có khóa riêng hoặc ta cần một quy tắc lấy đường dẫn/vị trí phù hợp.

### Khi nào chọn json_tree?

- Cần tìm node ở nhiều cấp mà cấu trúc không cố định.
- Cần duyệt toàn bộ cây JSON để kiểm tra dữ liệu.
- Cần xác định vị trí đường dẫn `fullkey` của các giá trị.

Nếu schema đã biết “shipments → items”, hai bước `json_each` tường minh theo cấp thường dễ kiểm soát grain hơn một lần quét toàn cây và lọc theo text path phức tạp.

### SQLite và chuyển số

SQLite có quy tắc cast mềm trong một số tình huống: `CAST('bad' AS INTEGER)` có thể trả 0 thay vì lỗi như PostgreSQL. Nếu qty là bắt buộc, cần kiểm tra `json_type(j.value,'$.qty')` là kiểu số được chấp nhận, và validate miền giá trị; không xem kết quả cast 0 là xác nhận dữ liệu hợp lệ.

---

## 30. BigQuery: JSON_QUERY_ARRAY kết hợp UNNEST

Trong BigQuery, dữ liệu JSON có thể ở kiểu `JSON` hoặc chuỗi chứa JSON. Một hướng thông dụng để bung mảng là lấy một array rồi `UNNEST`.

Giả sử bảng `orders` có `order_id` và `payload` chứa JSON:

```sql
-- BigQuery Standard SQL: tên bảng orders mang tính minh họa.
SELECT
    o.order_id,
    offset0,
    JSON_VALUE(item, '$.sku') AS sku,
    SAFE_CAST(JSON_VALUE(item, '$.qty') AS INT64) AS qty
FROM orders AS o
CROSS JOIN UNNEST(
    JSON_QUERY_ARRAY(o.payload, '$.items')
) AS item WITH OFFSET AS offset0
ORDER BY o.order_id, offset0;
```

- `JSON_QUERY_ARRAY` lấy mảng ở đường dẫn `$.items` dưới dạng array phù hợp với loại input.
- `UNNEST` tạo một hàng cho mỗi phần tử.
- `WITH OFFSET` cung cấp **chỉ số bắt đầu từ 0**.
- `JSON_VALUE` lấy scalar của item object.
- `SAFE_CAST` trả SQL NULL cho nhiều trường hợp chuyển kiểu không hợp lệ thay vì làm lỗi truy vấn.

Khi `JSON_QUERY_ARRAY` trả SQL NULL hoặc mảng rỗng, `CROSS JOIN UNNEST` không tạo hàng con. Nếu cần giữ order, xem xét dạng **LEFT JOIN UNNEST** và xử lý cột phần tử NULL theo ngữ nghĩa BigQuery.

### JSON_VALUE_ARRAY cho mảng scalar

Với mảng chuỗi thuần:

```sql
SELECT
    offset0,
    value
FROM UNNEST(
    JSON_VALUE_ARRAY('{"tags":["SQL","JSON","ETL"]}', '$.tags')
) AS value WITH OFFSET AS offset0
ORDER BY offset0;
```

Kết quả ba hàng với offset 0,1,2. Với dữ liệu `null` bên trong array, các hàm giá trị scalar-array có giới hạn/quy tắc riêng; cần kiểm tra dữ liệu và chức năng được chọn, không mặc định mọi array JSON đều có thể chuyển thành `ARRAY<STRING>` mà không lỗi.

---

## 31. Snowflake: LATERAL FLATTEN

Snowflake có `FLATTEN` để bung dữ liệu semi-structured, thường lưu ở cột `VARIANT`.

Ví dụ khái quát:

```sql
-- Snowflake; orders.doc được giả định là VARIANT.
SELECT
    o.order_id,
    f.index AS offset0,
    f.value:sku::STRING AS sku,
    TRY_TO_NUMBER(f.value:qty::STRING) AS qty
FROM orders AS o,
LATERAL FLATTEN(
    INPUT => o.doc:items
) AS f
ORDER BY o.order_id, f.index;
```

- `f.value` là phần tử hiện tại.
- `f.index` là vị trí array, bắt đầu từ **0**.
- `f.key` có ý nghĩa với object.
- `f.path` cho biết đường dẫn của phần tử.
- `OUTER => TRUE` là tùy chọn hữu ích khi muốn giữ một hàng placeholder cho expansion rỗng theo semantics Snowflake.

Với JSON lồng, `FLATTEN(RECURSIVE => TRUE)` có thể duyệt đệ quy, nhưng nếu chỉ muốn một cấu trúc xác định, dùng các bước `LATERAL FLATTEN` theo cấp thường giúp diễn đạt rõ mối quan hệ cha–con.

### Vì sao không viết một cú pháp chung cho BigQuery và Snowflake?

BigQuery dùng các kiểu array/JSON và `UNNEST`; Snowflake dùng `VARIANT` và `FLATTEN`. Dù đều tạo một hàng cho mỗi phần tử, cách **lấy vị trí, giá trị, NULL và parent preservation** có thể khác.

---

## 32. Bảng so sánh cú pháp theo phương ngữ

| DBMS | Cách bung mảng | Vị trí phần tử | Giữ hàng cha khi mảng rỗng |
| --- | --- | --- | --- |
| PostgreSQL | `jsonb_array_elements` + `LATERAL` | `WITH ORDINALITY`, **1-based** | `LEFT JOIN LATERAL ... ON TRUE` |
| MySQL 8.0 | `JSON_TABLE(...,'$[*]' COLUMNS(...))` | `FOR ORDINALITY`, **1-based** | `LEFT JOIN JSON_TABLE ... ON TRUE` |
| SQL Server | `OPENJSON` + `CROSS APPLY` | `[key]`, **0-based** cho array, dạng text | `OUTER APPLY OPENJSON(...)` |
| Oracle Database | `JSON_TABLE` với `PATH` | `FOR ORDINALITY`, **1-based** | `OUTER APPLY JSON_TABLE(...)` |
| SQLite | `json_each` | `key`, **0-based** cho array | `LEFT JOIN json_each(...) ON TRUE` |
| BigQuery | `UNNEST(JSON_QUERY_ARRAY(...))` | `WITH OFFSET`, **0-based** | `LEFT JOIN UNNEST(...)` |
| Snowflake | `LATERAL FLATTEN` | `INDEX`, **0-based** | `FLATTEN(OUTER => TRUE)` |

**Bắt đầu từ 0 hay 1 là đặc điểm của cột vị trí, không phải luôn là đặc điểm của JSON path.** Nhiều đường dẫn JSON array dùng index 0 cho phần tử đầu dù `FOR ORDINALITY` sinh 1.

---

## 33. JSON null, mảng rỗng, missing và SQL NULL trên các DBMS

Tập đầu vào cần kiểm tra:

```json
{"items":[]}
```

```json
{}
```

```json
{"items":null}
```

```json
{"items":[null]}
```

```json
{"items":[{}]}
```

Chúng không tương đương:

| Dữ liệu | Có mảng? | Số phần tử mảng | Nếu bung thành hàng phần tử |
| --- | --- | ---: | --- |
| `{"items":[]}` | Có | 0 | Không có hàng |
| `{}` | Không có key | — | Cần quy tắc thiếu key; thường không có hàng |
| `{"items":null}` | Key có JSON null | — | Không phải array; phải xác định xử lý |
| `{"items":[null]}` | Có | 1 | Một hàng chứa giá trị phần tử JSON null |
| `{"items":[{}]}` | Có | 1 | Một hàng object không có các field mong muốn |

### Đếm đúng phần tử

Với các hệ có cột ordinal/offset:

- PostgreSQL `COUNT(ordinal)`.
- MySQL/Oracle `COUNT(ordinal)`.
- SQL Server `COUNT(j.[key])` ở chế độ mặc định.
- SQLite `COUNT(j.key)`.
- BigQuery `COUNT(offset0)` khi dùng LEFT JOIN và offset có thể NULL trên hàng mở rộng rỗng.

Đó là một cách đáng tin cậy để **không tính hàng null-extended của LEFT JOIN** thành item. Cần giữ cột offset thực sự trong truy vấn.

### Phân biệt element JSON null

Một phần tử JSON null thật có thể tạo row với offset/ordinal **không NULL**, nhưng giá trị được trích sang SQL có thể là NULL. Đừng dùng `COUNT(value)` hoặc `WHERE sku IS NOT NULL` nếu mục tiêu là đếm **mọi vị trí trong array**, bao gồm phần tử null.

### Lỗi và phiên bản có thể khác

Một hàm có thể trả 0 hàng khi path không có, trong khi hàm khác báo lỗi khi đầu vào thực chất là scalar. Sự khác biệt của MySQL `JSON_TABLE` qua các phiên bản và các tùy chọn `ON EMPTY`/`ON ERROR` của SQL/JSON là lý do cần **nêu rõ hợp đồng nguồn và phiên bản DBMS** khi viết code production.

---

## 34. JSON path không phải câu SQL: chú ý root và item context

Ba đường dẫn hay gặp:

```text
'$'
'$.items'
'$.items[*]'
```

- `'$'`: toàn bộ tài liệu JSON.
- `'$.items'`: giá trị của khóa `items`.
- `'$.items[*]'`: từng phần tử của mảng ở khóa `items`.

### Trường hợp MySQL/Oracle

```sql
JSON_TABLE(
    doc,
    '$.items[*]'
    COLUMNS (
        sku VARCHAR(40) PATH '$.sku'
    )
)
```

Trong phần `COLUMNS`, `PATH '$.sku'` được đánh giá **tương đối với item row context** do `'$.items[*]'` chọn, không phải lấy `$.sku` ở root của toàn tài liệu nguồn.

### Trường hợp PostgreSQL

```sql
jsonb_array_elements(payload -> 'items')
```

Hàm nhận **giá trị array đã được trích**; việc truy cập `elem ->> 'sku'` áp lên một phần tử.

### Trường hợp SQL Server

```sql
OPENJSON(payload, '$.items')
```

`OPENJSON` bung các phần tử trực tiếp của mảng tại `$.items`. Sau đó `JSON_VALUE(j.[value], '$.sku')` đọc field của object từng phần tử.

Không nên sao chép đường dẫn mà không hiểu **đường dẫn đang áp lên document gốc, array hay item hiện tại**.

---

## 35. Mảng scalar và mảng object cần các chiến lược khác nhau

Mảng scalar:

```json
{"tags":["database","sql","json"]}
```

Kết quả mong muốn:

| tag_position | tag |
| ---: | --- |
| 1 | database |
| 2 | sql |
| 3 | json |

Mảng object:

```json
{"items":[{"sku":"A","qty":2},{"sku":"B","qty":3}]}
```

Kết quả mong muốn:

| item_position | sku | qty |
| ---: | --- | ---: |
| 1 | A | 2 |
| 2 | B | 3 |

Cách trích khác nhau:

- **PostgreSQL:** `jsonb_array_elements_text` cho scalar; `jsonb_array_elements` + `->>` hoặc `jsonb_to_recordset` cho object.
- **MySQL/Oracle JSON_TABLE:** cột scalar có thể khai báo `PATH '$'` khi mỗi row context là chính scalar; với object dùng `PATH '$.sku'`.
- **SQL Server:** `OPENJSON` default `[value]` chứa scalar; với object dùng `JSON_VALUE` hoặc `WITH`.
- **SQLite:** `json_each.value` có thể đã là scalar SQL; với object dùng `json_extract(j.value,'$.sku')`.
- **BigQuery:** `JSON_VALUE_ARRAY` cho mảng scalar phù hợp; `JSON_QUERY_ARRAY` + `UNNEST` + `JSON_VALUE` cho object.
- **Snowflake:** `f.value` là phần tử; truy cập thuộc tính qua `f.value:sku` khi là object.

### Ví dụ MySQL mảng scalar

```sql
SELECT
    jt.ordinal,
    jt.tag
FROM JSON_TABLE(
    '["database","sql","json"]',
    '$[*]'
    COLUMNS (
        ordinal FOR ORDINALITY,
        tag VARCHAR(50) PATH '$'
    )
) AS jt
ORDER BY jt.ordinal;
```

`PATH '$'` chỉ phần tử scalar đang được duyệt.

### Ví dụ SQL Server mảng scalar

```sql
SELECT
    TRY_CONVERT(INT, j.[key]) AS offset0,
    j.[value] AS tag
FROM OPENJSON(N'["database","sql","json"]') AS j
ORDER BY offset0;
```

Không cần `JSON_VALUE` thêm vì `j.[value]` đã là scalar ở chế độ mặc định.

---

## 36. Đếm và tính tổng cần phân biệt JSON element với item nghiệp vụ

Một array có thể có:

```json
[
  {"sku":"A","qty":2},
  null,
  {},
  {"sku":"B","qty":0},
  {"sku":"C","qty":-3}
]
```

Có **5 phần tử JSON**, nhưng số **item hợp lệ** có thể là 1, 2 hoặc 3 tùy yêu cầu:

- Nếu item phải là object có `sku` không rỗng và `qty > 0`, chỉ A hợp lệ.
- Nếu `qty = 0` vẫn là item hợp lệ, B cũng hợp lệ.
- Nếu qty âm biểu diễn trả hàng, C có thể có ý nghĩa trong một luồng khác.

Hãy đặt tên metric rõ:

| Metric | Ý nghĩa |
| --- | --- |
| `array_element_count` | Tổng số vị trí trong JSON array |
| `object_element_count` | Số phần tử có loại JSON object |
| `valid_item_count` | Số object thỏa quy tắc item |
| `distinct_sku_count` | Số SKU phân biệt sau khi chuẩn hóa |
| `total_quantity` | Tổng qty hợp lệ theo quy tắc |
| `total_amount` | Tổng qty × unitPrice của các item được chấp nhận |

### Ví dụ PostgreSQL đếm object hợp lệ theo dạng

```sql
SELECT
    o.order_id,
    COUNT(e.ordinal) AS array_element_count,
    COUNT(*) FILTER (
        WHERE jsonb_typeof(e.elem) = 'object'
    ) AS object_element_count
FROM lab_json_orders_364 AS o
LEFT JOIN LATERAL jsonb_array_elements(
    CASE
        WHEN jsonb_typeof(o.payload -> 'items') = 'array'
        THEN o.payload -> 'items'
        ELSE '[]'::jsonb
    END
) WITH ORDINALITY AS e(elem, ordinal)
    ON TRUE
GROUP BY o.order_id
ORDER BY o.order_id;
```

Trong `FILTER`, hàng null-extended không có `jsonb_typeof(e.elem) = 'object'` nên không bị đếm là object.

**Đừng để một dashboard dùng tên “số sản phẩm” khi thực tế nó đang đếm mọi phần tử JSON, kể cả null/{} không hợp lệ.**

---

## 37. Bung để JOIN với bảng danh mục sản phẩm

Giả sử bảng sản phẩm chuẩn có khóa `sku`:

```sql
CREATE TABLE lab_products_364 (
    sku TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    active BOOLEAN NOT NULL
);

INSERT INTO lab_products_364 (sku, product_name, active)
VALUES
    ('BK-01',  'Sổ tay A', TRUE),
    ('PEN-02', 'Bút xanh', TRUE),
    ('BAG-03', 'Túi vải',  FALSE);
```

Bung items rồi JOIN:

```sql
WITH expanded AS (
    SELECT
        o.order_id,
        e.ordinal,
        e.elem ->> 'sku' AS sku
    FROM lab_json_orders_364 AS o
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE
            WHEN jsonb_typeof(o.payload -> 'items') = 'array'
            THEN o.payload -> 'items'
            ELSE '[]'::jsonb
        END
    ) WITH ORDINALITY AS e(elem, ordinal)
)
SELECT
    x.order_id,
    x.ordinal,
    x.sku,
    p.product_name,
    p.active
FROM expanded AS x
LEFT JOIN lab_products_364 AS p
  ON p.sku = x.sku
ORDER BY x.order_id, x.ordinal;
```

`LEFT JOIN` giữ cả item có SKU không tìm thấy trong danh mục. Khi đó `product_name IS NULL` có thể là dấu hiệu:

- SKU thiếu.
- SKU sai tên/casing.
- Danh mục không có SKU.
- JSON element không phải object.

Cần phân loại nguyên nhân bằng thêm điều kiện/kiểm tra nguồn, không tự khẳng định mọi `NULL` là “sản phẩm đã xóa”.

### Đừng JOIN chỉ theo trường không unique

Nếu bảng danh mục có nhiều phiên bản sản phẩm cùng SKU và JOIN không thêm `version`/`effective_date`, mỗi item có thể nhân lên nhiều hàng. Phép bung làm tạo một hàng theo phần tử; **JOIN phía sau** vẫn phải có quan hệ một-một theo khóa nghiệp vụ nếu muốn giữ grain đó.

---

## 38. Chuyển JSON array thành bảng quan hệ có khóa

Một hệ thống có thể nhận order ở dạng JSON rồi lưu item vào bảng chuẩn hóa:

```sql
CREATE TABLE lab_order_item_rows_364 (
    order_id INTEGER NOT NULL
             REFERENCES lab_json_orders_364(order_id),
    item_ordinal BIGINT NOT NULL,
    sku TEXT NOT NULL,
    qty INTEGER NOT NULL CHECK (qty > 0),
    PRIMARY KEY (order_id, item_ordinal)
);
```

Ví dụ **chỉ lấy order 101**, nơi hai phần tử đều hợp lệ:

```sql
BEGIN;

INSERT INTO lab_order_item_rows_364 (
    order_id, item_ordinal, sku, qty
)
SELECT
    o.order_id,
    e.ordinal,
    e.elem ->> 'sku',
    (e.elem ->> 'qty')::INTEGER
FROM lab_json_orders_364 AS o
CROSS JOIN LATERAL
    jsonb_array_elements(o.payload -> 'items')
    WITH ORDINALITY AS e(elem, ordinal)
WHERE o.order_id = 101;

SELECT *
FROM lab_order_item_rows_364
ORDER BY order_id, item_ordinal;

ROLLBACK;
```

Kết quả trong transaction:

| order_id | item_ordinal | sku | qty |
| ---: | ---: | --- | ---: |
| 101 | 1 | BK-01 | 2 |
| 101 | 2 | PEN-02 | 3 |

`ROLLBACK` giúp bài thực hành không lưu dữ liệu item, trong khi bảng mẫu vẫn tồn tại để dùng tiếp.

### Vì sao khóa (order_id, item_ordinal) chưa hoàn hảo cho mọi nghiệp vụ?

Nếu ứng dụng **chèn một phần tử mới vào đầu array**, mọi ordinal phía sau thay đổi. Khóa theo vị trí phù hợp cho **snapshot của đúng phiên bản document**, nhưng có thể không phù hợp làm ID item bền vững.

Một mô hình tốt hơn khi item có danh tính riêng:

```json
{"itemId":"L-987","sku":"BK-01","qty":2}
```

có thể dùng khóa `(order_id,item_id)`.

### Nếu dùng UPSERT thay vì INSERT thì sao?

Upsert chỉ thêm/sửa những item có trong bản nguồn mới. Khi một item **bị xóa khỏi mảng**, hàng cũ trong bảng quan hệ không tự biến mất nếu pipeline chỉ chạy upsert.

Một đồng bộ snapshot đầy đủ cần **xử lý xóa các item không còn tồn tại** trong phiên bản JSON mới, trong transaction và theo hợp đồng về thứ tự/identity.

---

## 39. JSON array order và tính ổn định của kết quả SQL

JSON array có thứ tự logic; nhưng **kết quả SELECT của SQL không được bảo đảm giữ đúng thứ tự khi không có ORDER BY**.

Ví dụ PostgreSQL:

```sql
SELECT
    e.ordinal,
    e.elem ->> 'sku' AS sku
FROM jsonb_array_elements(
    '[{"sku":"A"},{"sku":"B"},{"sku":"C"}]'::jsonb
) WITH ORDINALITY AS e(elem, ordinal)
ORDER BY e.ordinal;
```

Khi cần báo cáo trên nhiều order:

```sql
ORDER BY order_id, ordinal
```

để kết quả có tính xác định theo từng order và thứ tự item.

### Không dùng ROW_NUMBER tùy ý để suy vị trí gốc

Nếu bung mảng rồi JOIN/WHERE và tính:

```sql
ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY sku)
```

thứ tự đó là **thứ tự theo SKU**, không phải vị trí trong array gốc. Muốn vị trí gốc phải lấy nó từ `WITH ORDINALITY`, `FOR ORDINALITY`, `OPENJSON key`, `json_each key` hoặc `WITH OFFSET` trước khi sắp xếp/tổng hợp.

### Không coi thứ tự object keys là thứ tự array elements

JSON object có các khóa `sku`, `qty`, `unitPrice`. Các hệ có thể lưu/trả thứ tự khóa object khác nhau; điều đó không tương đương việc thay đổi thứ tự phần tử trong array.

---

## 40. Hiệu năng: khi nào bung mảng JSON đắt?

Một bảng có 1 triệu order, mỗi order trung bình 20 item:

```text
1.000.000 order × 20 item ≈ 20.000.000 hàng sau bung
```

Một query `SELECT ... CROSS JOIN JSON_ARRAY_EXPANSION` có thể tạo hàng chục triệu dòng trung gian rồi mới JOIN/GROUP BY. Đây là **cardinality expansion**, không phải một thao tác miễn phí.

### Những yếu tố chi phí

- Kích thước document và số phần tử trên mỗi array.
- Chi phí parse JSON từ text, nếu DBMS chưa lưu dạng nội bộ tối ưu.
- Chi phí chạy hàm bảng lặp cho từng hàng cha.
- Chi phí ép kiểu scalar trong mỗi item.
- Số hàng tạo ra sau bung.
- Join với bảng khác và sort/group trên hàng đã bung.
- Vị trí đặt filter: trước hay sau bung.
- I/O và network nếu trả toàn bộ item về ứng dụng.
- JSON indexes chỉ hỗ trợ một số kiểu predicate; không thay thế mọi chi phí mở rộng.

### Lọc hàng cha trước khi bung

Nếu chỉ cần đơn trong ngày 2026-08-01:

```sql
SELECT ...
FROM orders AS o
CROSS JOIN LATERAL jsonb_array_elements(o.payload -> 'items') AS e(elem)
WHERE o.created_at >= TIMESTAMPTZ '2026-08-01 00:00:00+00'
  AND o.created_at <  TIMESTAMPTZ '2026-08-02 00:00:00+00';
```

Optimizer có thể đẩy điều kiện phù hợp để giảm số hàng cha cần bung, tùy kế hoạch. Dù vậy, nên thiết kế query với **điều kiện lọc thật sự cần thiết ở bảng cha**, không cố bung toàn bộ lịch sử rồi mới lọc theo item hoặc order nếu không cần.

### Đếm item không nhất thiết phải bung

Khi chỉ cần độ dài mảng và đầu vào đã được validate, PostgreSQL có `jsonb_array_length`:

```sql
SELECT
    order_id,
    jsonb_array_length(
        CASE
            WHEN jsonb_typeof(payload -> 'items') = 'array'
            THEN payload -> 'items'
            ELSE '[]'::jsonb
        END
    ) AS element_count
FROM lab_json_orders_364
ORDER BY order_id;
```

Nó diễn đạt trực tiếp mục tiêu **số phần tử**, thay vì tạo một hàng cho mỗi phần tử rồi `COUNT`. Khi cần phân loại tính hợp lệ từng item, vẫn phải xem từng phần tử.

### Tránh SELECT * sau bung

Nếu mỗi order có JSON document lớn, `SELECT o.*` sau khi bung 20 item sẽ lặp lại toàn bộ payload trên 20 dòng kết quả, tăng lượng dữ liệu truyền. Chỉ chọn `order_id` và các cột cần thiết.

---

## 41. Chỉ mục JSON và quan hệ: khác nhau về mục tiêu

Có hai kiểu truy vấn:

1. **Tìm hàng cha có JSON thỏa điều kiện**.
2. **Bung từng phần tử để JOIN/tính tổng**.

Một chỉ mục JSON có thể giúp câu (1) mà không giúp trực tiếp chi phí tạo 20 hàng cho mỗi document của câu (2).

### PostgreSQL GIN ví dụ

```sql
-- Chỉ tạo khi cần và đã cân nhắc workload.
CREATE INDEX lab_json_orders_364_payload_gin
ON lab_json_orders_364 USING GIN (payload);
```

Một số toán tử `jsonb` như containment `@>` có thể tận dụng loại index phù hợp. Nhưng:

- GIN index có chi phí ghi và dung lượng.
- Không làm `jsonb_array_elements` tự trở thành truy vấn index-only.
- Không có nghĩa mọi JSON path predicate được hỗ trợ giống nhau bởi mọi operator class.
- Có thể gây chi phí bảo trì khi payload cập nhật thường xuyên.

### Chuẩn hóa JSON thành bảng con

Nếu ứng dụng liên tục tìm `sku` trong tất cả order, tính aggregate và JOIN sản phẩm, một bảng `order_items(order_id,sku,qty,...)` có index quan hệ có thể phù hợp hơn việc bung JSON trong mọi truy vấn.

Tuy nhiên, bảng chuẩn hóa thêm độ phức tạp đồng bộ khi JSON nguồn thay đổi. Cần quyết định **mô hình nguồn sự thật** và cách cập nhật nhất quán.

---

## 42. Dữ liệu sai kiểu và validation trước khi chuyển thành số

Ví dụ:

```json
[
  {"sku":"A","qty":2},
  {"sku":"B","qty":"2"},
  {"sku":"C","qty":"oops"},
  {"sku":"D","qty":null},
  {"sku":"E"}
]
```

Các giá trị `qty` khác nhau:

- JSON number `2`.
- JSON string `"2"`.
- JSON string `"oops"`.
- JSON null.
- Thiếu key.

Nếu hợp đồng yêu cầu `qty` phải là **JSON integer dương**, không nên mặc định chấp nhận chuỗi `"2"` chỉ vì DBMS có thể ép sang 2. Việc chấp nhận số dạng chuỗi nên là một chính sách được ghi rõ.

### Phân loại trước khi cast

PostgreSQL:

```sql
SELECT
    e.ordinal,
    e.elem ->> 'sku' AS sku,
    jsonb_typeof(e.elem -> 'qty') AS qty_type,
    CASE
        WHEN jsonb_typeof(e.elem -> 'qty') = 'number'
        THEN (e.elem ->> 'qty')::NUMERIC
        ELSE NULL
    END AS qty_number
FROM jsonb_array_elements(
    '[
      {"sku":"A","qty":2},
      {"sku":"B","qty":"2"},
      {"sku":"C","qty":"oops"},
      {"sku":"D","qty":null},
      {"sku":"E"}
    ]'::jsonb
) WITH ORDINALITY AS e(elem, ordinal)
ORDER BY e.ordinal;
```

| ordinal | sku | qty_type | qty_number |
| ---: | --- | --- | ---: |
| 1 | A | number | 2 |
| 2 | B | string | SQL NULL |
| 3 | C | string | SQL NULL |
| 4 | D | null | SQL NULL |
| 5 | E | SQL NULL | SQL NULL |

Tiếp theo mới áp quy tắc `qty > 0`, nguyên vẹn là số nguyên và giới hạn miền để ghi vào cột `INTEGER`.

### SQL Server và BigQuery: chuyển kiểu an toàn hơn

SQL Server có `TRY_CONVERT`/`TRY_CAST`; BigQuery có `SAFE_CAST` để giảm một số lỗi chuyển kiểu. Nhưng nếu hai dạng dữ liệu sai cùng biến thành SQL NULL, bạn cần cột trạng thái lỗi nếu muốn **phân biệt nguyên nhân**.

### MySQL/Oracle JSON_TABLE

Cần cấu hình và hiểu `ON EMPTY`/`ON ERROR` theo phiên bản để tránh âm thầm nhận NULL hoặc mặc định khi nguồn sai. **Không xem việc câu SQL chạy thành công là đủ chứng minh JSON hợp lệ về nghiệp vụ.**

---

## 43. Bảo mật: JSON không phải dữ liệu đáng tin mặc định

Một document từ API hoặc message queue là dữ liệu đầu vào, không phải code SQL. Hãy dùng **prepared statements/parameters** khi truyền JSON vào database, không nối chuỗi tùy ý vào câu SQL.

Ví dụ định hướng trong Java/JDBC:

```java
// Minh họa bind JSON text, không phải lớp repository hoàn chỉnh.
String sql = """
    INSERT INTO incoming_documents (external_id, payload)
    VALUES (?, CAST(? AS jsonb))
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, externalId);
    ps.setString(2, jsonText);
    ps.executeUpdate();
}
```

Câu SQL này là **PostgreSQL** và giả định bảng `incoming_documents` đã tồn tại với cột `payload jsonb`. Điều cần học là **bind giá trị**, không nối payload trực tiếp vào SQL text.

### JSON path động cũng cần kiểm soát

Nếu API cho phép người dùng chọn JSON path, đừng ghép trực tiếp một path tùy ý mà không kiểm tra. Một số DBMS hỗ trợ path dưới dạng tham số, số khác yêu cầu cú pháp đặc thù. Với hệ thống thật:

- Dùng allowlist những path được hỗ trợ.
- Giới hạn kích thước JSON và độ sâu mảng nếu cần.
- Kiểm soát số phần tử tối đa để tránh một request tạo hàng triệu rows.
- Không cho phép người dùng chọn các cột/đối tượng SQL tùy ý bằng cách ghép chuỗi.
- Xác định tenant/order ownership ở **bảng cha** trước khi bung, tránh rò rỉ item giữa người dùng.
- Giới hạn quyền của tiến trình ETL và nơi lưu lỗi dữ liệu đầu vào.

### JSON có thể chứa dữ liệu nhạy cảm

Nếu bung toàn bộ object và log `elem` khi lỗi, bạn có thể ghi số điện thoại, địa chỉ hoặc token ra log. Nên chỉ ghi **order ID, vị trí phần tử, loại lỗi và một phần thông tin không nhạy cảm** đủ để truy vết.

---

## 44. Những bẫy thường gặp khi chuyển phương ngữ

| Nhầm lẫn | Hậu quả | Cách nghĩ đúng |
| --- | --- | --- |
| Dùng `jsonb_array_elements` trong MySQL | Không có hàm PostgreSQL đó | MySQL dùng `JSON_TABLE` |
| Dùng `OPENJSON` trong PostgreSQL | Sai cú pháp | Dùng các hàm `jsonb`/`json` với `LATERAL` |
| Dùng `JSON_TABLE` của Oracle với kiểu `INT`/`VARCHAR` giống hệt MySQL | Có thể sai kiểu/chi tiết cú pháp | Đúng kiểu và phiên bản Oracle |
| Dùng `WITH ORDINALITY` với giả định index 0 | Lệch vị trí một đơn vị | PostgreSQL ordinality bắt đầu từ 1 |
| Dùng `OPENJSON key` như ordinality 1-based | Lệch vị trí | SQL Server array key bắt đầu từ 0 |
| Dùng `json_each.key` mà không biết là array hay object | Nhầm index với tên thuộc tính | Kiểm tra input type |
| Dùng `COUNT(*)` sau LEFT JOIN bung mảng | Đếm order mảng rỗng thành một item | Đếm ordinal/offset không NULL |
| Xem JSON `null` là SQL NULL trong mọi vị trí | Nhầm phần tử thật và hàng được left-extend | Giữ loại JSON và ordinal |
| Gọi hàm bung array trên scalar | Có thể lỗi hoặc hành vi khác mong muốn | Kiểm tra JSON type trước |
| `->> 'qty'::int` không đúng vị trí cast | Dễ có lỗi cú pháp/kiểu | Dùng `(elem ->> 'qty')::INTEGER` |
| Cast `"oops"` sang INT | Lỗi hoặc giá trị chuyển đổi sai tùy DBMS | Validate type, TRY/SAFE conversion |
| MySQL `JSON_TABLE` path root không đúng | 0 hàng hoặc giá trị sai | Phân biệt `'$[*]'` và `'$.items[*]'` |
| SQL Server OPENJSON WITH rồi đọc `[key]` | Cột key không còn ở schema explicit | Dùng default OPENJSON để giữ vị trí |
| Tưởng INNER expansion giữ mọi order | Order mảng rỗng biến mất | Dùng LEFT/OUTER khi cần |
| Tưởng OUTER expansion tạo item rỗng thật | Sai số đếm | Dùng indicator ordinal/offset |
| Không ORDER BY khi cần thứ tự item | Kết quả không có thứ tự bảo đảm | ORDER BY order_id, ordinal |
| Dùng ROW_NUMBER theo SKU để phục dựng array order | Sai vị trí JSON gốc | Lấy chỉ số từ cơ chế bung |
| Dùng ordinal làm ID item vĩnh viễn | Reorder array làm đổi khóa | Dùng itemId ổn định nếu cần |
| Chỉ UPSERT item khi đồng bộ snapshot | Hàng đã bị xóa khỏi JSON vẫn còn | Xử lý DELETE bản ghi vắng |
| JOIN item với nhiều bản sản phẩm | Nhân bản số lượng/doanh thu | Xác định key/grain và tính duy nhất |
| Bung toàn bộ document chỉ để lọc order | Tạo nhiều hàng trung gian | Xem JSON containment/path predicate |
| Cho rằng JSON index tăng tốc mọi phép bung | Hiểu sai phạm vi index | Đo query shape và chi phí expansion |
| Dùng JSON field missing như mặc định 0 | Che dữ liệu sai nguồn | Chính sách validation rõ |
| Không phân biệt JSON type trên BigQuery/Snowflake | Sai hàm/cast | Chọn theo kiểu JSON/VARIANT của DBMS |

---

## 45. Bài tập thực hành

Các bài 1–12 dùng bảng PostgreSQL `lab_json_orders_364`, `lab_products_364` và `lab_order_item_rows_364` đã tạo ở trên. Các bài còn lại hỏi về phương ngữ khác. Hãy dự đoán **số hàng, thứ tự và giá trị NULL** trước khi xem đáp án.

### Bài 1. Bung mảng đơn giản

Order 101 có hai item. Viết PostgreSQL `CROSS JOIN LATERAL jsonb_array_elements` để trả `order_id` và `sku`.

### Bài 2. Giữ vị trí từ 1

Thêm `WITH ORDINALITY` và `ORDER BY` để trả `(order_id, ordinal, sku)` theo đúng thứ tự JSON.

### Bài 3. Mảng rỗng

Tại sao order 102 biến mất khi dùng `CROSS JOIN LATERAL`? Nếu cần giữ order 102, viết dạng JOIN nào?

### Bài 4. Phân biệt thiếu key và JSON null

Order 103 không có `items`, order 104 có `"items":null`. Viết PostgreSQL query để phân biệt bằng toán tử `?` và `jsonb_typeof`.

### Bài 5. Phần tử null thật

Order 107 có hai phần tử, phần tử thứ nhất JSON `null`. Vì sao `COUNT(e.ordinal)` cho kết quả 2, còn kiểm tra `sku IS NOT NULL` chỉ thấy một item?

### Bài 6. Đếm số phần tử mọi order

Viết một truy vấn PostgreSQL giữ mọi order và đếm đúng số phần tử thật, kể cả khi `items` thiếu/sai kiểu.

### Bài 7. Mảng scalar

Với `'["A","B","C"]'::jsonb`, dùng hàm PostgreSQL nào để trả các scalar dạng text? Vị trí của C là bao nhiêu theo ordinality?

### Bài 8. Trích object thành cột typed

Viết `jsonb_to_recordset` để trích `sku text, qty integer` từ mảng object hợp lệ. Tại sao không dùng thẳng với array chứa JSON null ở order 107?

### Bài 9. Validate qty

Giả sử qty có thể là JSON number, JSON string, JSON null hoặc thiếu. Viết `CASE` chỉ chuyển số khi JSON type là `number`.

### Bài 10. Tổng order 101

Tính `SUM(qty * unitPrice)` cho hai item của order 101. Kết quả là bao nhiêu?

### Bài 11. Bung hai cấp

JSON có `shipments[*].items[*]`. Hãy nêu số lần dùng `jsonb_array_elements` và các khóa cần giữ để phân biệt item ở hai shipment.

### Bài 12. Chuẩn hóa item vào bảng quan hệ

Viết một `INSERT ... SELECT` từ order 101 vào bảng `lab_order_item_rows_364`, có `order_id,item_ordinal,sku,qty`. Vì sao chỉ UPSERT các item hiện tại không đủ khi mảng mới bị xóa một phần tử?

### Bài 13. MySQL JSON_TABLE

Viết MySQL 8.0 query bung `$.items[*]` thành `ordinal,sku,qty`. Ordinal bắt đầu từ mấy?

### Bài 14. MySQL scalar array

Với `["red","green"]`, cột `PATH '$'` trong `JSON_TABLE` có ý nghĩa gì? Nếu nhầm dùng `PATH '$.sku'`, điều gì xảy ra?

### Bài 15. SQL Server OPENJSON

Bung `[{"sku":"A"},{"sku":"B"}]` bằng `OPENJSON`. Cột `[key]` của hai phần tử trả giá trị nào? Làm sao lấy `sku` và chuyển key thành INT?

### Bài 16. SQL Server OUTER APPLY

Một order có `items=[]`. Khác biệt giữa `CROSS APPLY OPENJSON` và `OUTER APPLY OPENJSON` là gì?

### Bài 17. OPENJSON WITH

Nếu dùng `OPENJSON(... ) WITH(sku NVARCHAR(40) '$.sku')`, có còn cột mặc định `[key]` để lấy offset không? Nếu cần offset, làm thế nào?

### Bài 18. Oracle JSON_TABLE

Trong Oracle, cú pháp nào lấy vị trí 1-based và ánh xạ SKU? Kiểu chuỗi thường dùng trong ví dụ là gì?

### Bài 19. SQLite json_each

Với `json_each('[10,20,30]')`, `key` có các giá trị nào? Khác gì `WITH ORDINALITY` PostgreSQL?

### Bài 20. SQLite json_tree

Khi muốn duyệt JSON ở nhiều cấp không biết trước, hàm nào phù hợp hơn? Có nên dùng `json_tree.id` làm khóa nghiệp vụ lâu dài không?

### Bài 21. BigQuery UNNEST

Viết hình dạng BigQuery dùng `JSON_QUERY_ARRAY`, `UNNEST` và `WITH OFFSET` để lấy vị trí item. Offset của phần tử đầu là bao nhiêu?

### Bài 22. Snowflake FLATTEN

Một bảng có `doc VARIANT` chứa `items`. Viết `LATERAL FLATTEN(INPUT => doc:items)` và lấy `INDEX`, `VALUE:sku`. Cần tùy chọn nào khi muốn đại diện expansion rỗng?

### Bài 23. Hiệu năng và grain

Một bảng có 2 triệu orders, mỗi order có 10 item. Query bung tất cả rồi JOIN với bảng phân loại có 3 bản phân loại cho mỗi SKU. Hỏi có thể tạo bao nhiêu hàng trung gian và vì sao doanh thu có nguy cơ bị nhân?

### Bài 24. NULL và COUNT(*)

Một phép `LEFT JOIN` bung mảng trả 1 hàng null-extended cho order không có item. `COUNT(*)` và `COUNT(ordinal)` theo order khác nhau thế nào?

### Bài 25. Phát hiện dữ liệu sai schema

Một đơn có `items="oops"` thay vì array. Khi nào nên chuyển nó thành `[]`, khi nào phải phát lỗi? Nêu hậu quả của việc âm thầm coi sai kiểu là mảng rỗng.

---

## 46. Gợi ý lời giải

### Bài 1

```sql
SELECT
    o.order_id,
    e.elem ->> 'sku' AS sku
FROM lab_json_orders_364 AS o
CROSS JOIN LATERAL
    jsonb_array_elements(o.payload -> 'items') AS e(elem)
WHERE o.order_id = 101;
```

Có hai hàng với SKU BK-01 và PEN-02. Chỉ chọn order 101 vì đầu vào là array đúng schema.

### Bài 2

```sql
SELECT
    o.order_id,
    e.ordinal,
    e.elem ->> 'sku' AS sku
FROM lab_json_orders_364 AS o
CROSS JOIN LATERAL
    jsonb_array_elements(o.payload -> 'items')
    WITH ORDINALITY AS e(elem, ordinal)
WHERE o.order_id = 101
ORDER BY o.order_id, e.ordinal;
```

Ordinal là **1, 2**.

### Bài 3

`CROSS JOIN LATERAL` chỉ trả hàng khi hàm bung trả phần tử. Với mảng `[]`, hàm trả 0 hàng nên order 102 biến mất. Để giữ hàng cha:

```sql
LEFT JOIN LATERAL jsonb_array_elements(...) AS e(elem) ON TRUE
```

Hàng giữ lại có các cột `e` là SQL NULL; nó không phải item thật.

### Bài 4

```sql
SELECT
    order_id,
    payload ? 'items' AS has_items,
    jsonb_typeof(payload -> 'items') AS items_type
FROM lab_json_orders_364
WHERE order_id IN (103, 104)
ORDER BY order_id;
```

Order 103: `has_items=false`, `items_type IS NULL`. Order 104: `has_items=true`, `items_type='null'` dưới dạng text.

### Bài 5

`ordinal` nhận 1 và 2 vì mảng 107 **có hai phần tử thật**. Phần tử đầu là JSON null, nên `->>'sku'` không có giá trị. `sku IS NOT NULL` chỉ nhận object ở vị trí 2, không đếm JSON null.

### Bài 6

```sql
SELECT
    o.order_id,
    COUNT(e.ordinal) AS element_count
FROM lab_json_orders_364 AS o
LEFT JOIN LATERAL jsonb_array_elements(
    CASE
        WHEN jsonb_typeof(o.payload -> 'items') = 'array'
        THEN o.payload -> 'items'
        ELSE '[]'::jsonb
    END
) WITH ORDINALITY AS e(elem, ordinal) ON TRUE
GROUP BY o.order_id
ORDER BY o.order_id;
```

Kết quả theo order 101–107: **2, 0, 0, 0, 1, 0, 2**.

### Bài 7

Dùng `jsonb_array_elements_text`:

```sql
SELECT e.ordinal, e.value
FROM jsonb_array_elements_text(
    '["A","B","C"]'::jsonb
) WITH ORDINALITY AS e(value, ordinal)
ORDER BY e.ordinal;
```

C ở vị trí **3**.

### Bài 8

```sql
SELECT x.sku, x.qty
FROM jsonb_to_recordset(
    '[{"sku":"A","qty":2},{"sku":"B","qty":3}]'::jsonb
) AS x(sku TEXT, qty INTEGER);
```

Hàm được dùng cho **array object**. Mảng chứa JSON null/scalar không thể được giả định tự chuyển thành record hợp lệ; cần phân loại phần tử trước.

### Bài 9

```sql
CASE
    WHEN jsonb_typeof(elem -> 'qty') = 'number'
    THEN (elem ->> 'qty')::NUMERIC
    ELSE NULL
END
```

Đây là bước kiểm tra loại JSON cơ bản; vẫn cần validate số nguyên dương/giới hạn miền theo hợp đồng.

### Bài 10

`BK-01`: `2 × 50.00 = 100.00`. `PEN-02`: `3 × 5.00 = 15.00`. Tổng **115.00**.

```sql
SELECT SUM(
    (e.elem ->> 'qty')::NUMERIC
    * (e.elem ->> 'unitPrice')::NUMERIC
) AS total_amount
FROM lab_json_orders_364 AS o
CROSS JOIN LATERAL
    jsonb_array_elements(o.payload -> 'items') AS e(elem)
WHERE o.order_id = 101;
```

### Bài 11

Dùng **hai bước** bung: đầu tiên `shipments`, tiếp theo `items` của shipment hiện tại. Giữ ít nhất `shipment_pos` và `item_pos`, cùng order ID nếu có nhiều order.

### Bài 12

```sql
BEGIN;

INSERT INTO lab_order_item_rows_364 (
    order_id, item_ordinal, sku, qty
)
SELECT
    o.order_id,
    e.ordinal,
    e.elem ->> 'sku',
    (e.elem ->> 'qty')::INTEGER
FROM lab_json_orders_364 AS o
CROSS JOIN LATERAL
    jsonb_array_elements(o.payload -> 'items')
    WITH ORDINALITY AS e(elem, ordinal)
WHERE o.order_id = 101;

ROLLBACK;
```

Upsert không tự xóa hàng item đã mất khỏi snapshot mới; cần bước DELETE/replace được kiểm soát và xem xét khóa item ổn định.

### Bài 13

```sql
SELECT jt.ordinal, jt.sku, jt.qty
FROM JSON_TABLE(
    '{"items":[{"sku":"A","qty":2}]}',
    '$.items[*]'
    COLUMNS (
        ordinal FOR ORDINALITY,
        sku VARCHAR(40) PATH '$.sku',
        qty INT PATH '$.qty'
    )
) AS jt;
```

`FOR ORDINALITY` trong MySQL bắt đầu từ **1**.

### Bài 14

`PATH '$'` trong row context scalar lấy **giá trị phần tử hiện tại**, ví dụ `red` hoặc `green`. `PATH '$.sku'` tìm một thuộc tính object không tồn tại trong chuỗi, có thể cho NULL hoặc hành vi theo `ON EMPTY`.

### Bài 15

`OPENJSON` trả `[key]='0'` và `'1'` cho array. Ví dụ:

```sql
SELECT
    TRY_CONVERT(INT, j.[key]) AS offset0,
    JSON_VALUE(j.[value], '$.sku') AS sku
FROM OPENJSON(
    N'[{"sku":"A"},{"sku":"B"}]'
) AS j
ORDER BY offset0;
```

### Bài 16

`CROSS APPLY` không tạo hàng cho order có mảng rỗng; `OUTER APPLY` giữ **hàng cha** với cột JSON phần tử là SQL NULL.

### Bài 17

Không. Khi dùng `WITH` explicit schema, các cột default `key/value/type` không còn ở kết quả. Nếu cần offset, dùng `OPENJSON` default trước để giữ `[key]`, rồi trích field bằng `JSON_VALUE` hoặc một bước áp schema bổ sung.

### Bài 18

```sql
SELECT jt.ordinal, jt.sku
FROM JSON_TABLE(
    '[{"sku":"A"},{"sku":"B"}]',
    '$[*]'
    COLUMNS (
        ordinal FOR ORDINALITY,
        sku VARCHAR2(40) PATH '$.sku'
    )
) jt;
```

Vị trí là **1,2**; kiểu chuỗi ví dụ là `VARCHAR2` của Oracle.

### Bài 19

`json_each('[10,20,30]')` trả key **0,1,2** cho các phần tử array. PostgreSQL `WITH ORDINALITY` tương ứng **1,2,3**.

### Bài 20

`json_tree` duyệt nhiều cấp. Không dùng `json_tree.id` làm khóa nghiệp vụ bền vững vì đó là mã node nội bộ của kết quả traversal; nên lấy khóa từ dữ liệu hoặc đường dẫn được quy định.

### Bài 21

```sql
SELECT
    o.order_id,
    offset0,
    JSON_VALUE(item, '$.sku') AS sku
FROM orders AS o
CROSS JOIN UNNEST(
    JSON_QUERY_ARRAY(o.payload, '$.items')
) AS item WITH OFFSET AS offset0
ORDER BY o.order_id, offset0;
```

Phần tử đầu có `offset0=0`.

### Bài 22

```sql
SELECT
    o.order_id,
    f.index AS offset0,
    f.value:sku::STRING AS sku
FROM orders AS o,
LATERAL FLATTEN(
    INPUT => o.doc:items,
    OUTER => TRUE
) AS f;
```

`OUTER => TRUE` cho trường hợp expansion rỗng theo cơ chế của Snowflake. Trong báo cáo thực tế cần phân biệt hàng placeholder với item thật qua các cột metadata phù hợp.

### Bài 23

2 triệu × 10 item = **20 triệu item rows**. Nếu mỗi item JOIN với 3 bản phân loại, có thể thành **60 triệu hàng trung gian**. Khi SUM qty/amount sau JOIN mà không điều chỉnh grain, giá trị có thể bị nhân 3.

### Bài 24

Với một order mảng rỗng được giữ bằng LEFT JOIN:

- `COUNT(*) = 1` vì có một hàng cha null-extended.
- `COUNT(ordinal) = 0` vì không có vị trí phần tử thật.

### Bài 25

Nếu nhiệm vụ chỉ là hiển thị danh sách tùy chọn và hợp đồng cho phép coi dữ liệu không chuẩn là rỗng, có thể fallback `[]` **kèm dấu hiệu cảnh báo**.

Trong nhập đơn, tính tiền hay đồng bộ dữ liệu quan trọng, `"items":"oops"` là **sai schema**, nên từ chối hoặc đưa vào khu vực lỗi/quarantine. Bỏ qua im lặng có thể khiến hệ thống coi một đơn có sản phẩm nhưng dữ liệu sai thành **đơn không có item**, làm mất doanh thu hoặc bỏ sót kiểm tra tồn kho.

---

## 47. Dọn môi trường thực hành

Chỉ xóa **những bảng do bài học tạo trong database/schema thử nghiệm riêng**, sau khi kết thúc mọi transaction liên quan.

### PostgreSQL

```sql
DROP TABLE IF EXISTS lab_order_item_rows_364;
DROP TABLE IF EXISTS lab_products_364;
DROP TABLE IF EXISTS lab_json_orders_364;
```

### MySQL

```sql
DROP TABLE IF EXISTS lab_json_orders_mysql_364;
```

### SQL Server

```sql
DROP TABLE IF EXISTS dbo.lab_json_orders_364;
```

### SQLite

```sql
DROP TABLE IF EXISTS lab_json_orders_sqlite_364;
```

Không dùng `DROP` trên bảng ngoài phạm vi lab hoặc schema của ứng dụng khác chỉ vì trùng tên ví dụ.

---

## 48. Tổng kết và quy tắc chuyển phương ngữ

**Bung mảng JSON thành hàng** là chuyển một thuộc tính chứa array thành quan hệ SQL có **một hàng trên mỗi phần tử**. Để làm đúng cần giữ **khóa hàng cha**, nhận diện **vị trí phần tử**, trích **giá trị theo đúng kiểu** và quyết định **có giữ hàng cha rỗng hay không**.

Các quy tắc quan trọng:

1. **Đúng đường dẫn:** phân biệt array gốc `'$[*]'` và mảng bên trong `'$.items[*]'`.
2. **Đúng phương ngữ:** PostgreSQL dùng `jsonb_array_elements`/`LATERAL`; MySQL/Oracle dùng `JSON_TABLE`; SQL Server dùng `OPENJSON`/`APPLY`; SQLite dùng `json_each`/`json_tree`; BigQuery `UNNEST`; Snowflake `FLATTEN`.
3. **Đúng chỉ số:** PostgreSQL `WITH ORDINALITY` và MySQL/Oracle `FOR ORDINALITY` bắt đầu từ **1**; SQL Server/SQLite/BigQuery/Snowflake trong các ví dụ array dùng **0**.
4. **Đúng số hàng:** inner/cross expansion bỏ hàng cha không có phần tử; left/outer expansion giữ một hàng cha null-extended. `COUNT(*)` sau outer expansion **không phải** số item.
5. **Đúng nghĩa NULL:** mảng rỗng, key thiếu, JSON null, phần tử JSON null và field null trong object là những trường hợp khác nhau.
6. **Đúng schema:** không cast mọi `qty` sang số một cách mù quáng; kiểm tra loại JSON, chính sách thiếu/sai kiểu, số nguyên dương và giới hạn giá trị.
7. **Đúng thứ tự:** lấy ordinal/offset khi bung, rồi dùng `ORDER BY`. Không suy vị trí array từ thứ tự trả hàng SQL ngẫu nhiên.
8. **Đúng grain:** sau khi bung có thể phát sinh rất nhiều hàng; JOIN một-nhiều tiếp theo có thể làm nhân bản SUM/COUNT.
9. **Đúng kiến trúc:** nếu thường xuyên JOIN/lọc/tổng hợp item ở quy mô lớn, cân nhắc bảng quan hệ con có khóa/index; nếu lưu từ JSON snapshot, xử lý cả xóa và reorder.
10. **Đúng an toàn:** bind JSON bằng tham số, giới hạn kích thước/tầng lồng, kiểm soát quyền dữ liệu và đo chi phí trên workload thật.

Khi chuyển SQL giữa các hệ quản trị, **đừng dịch từng từ khóa**. Hãy bắt đầu từ hợp đồng dữ liệu: *mỗi order có bao nhiêu item, các loại NULL mang ý nghĩa gì, vị trí bắt đầu từ đâu và hàng cha rỗng có được giữ không*. Sau đó chọn công cụ bung mảng phù hợp với DBMS, phiên bản và yêu cầu nghiệp vụ.

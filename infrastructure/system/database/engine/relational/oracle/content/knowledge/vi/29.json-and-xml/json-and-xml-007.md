# Chỉ mục cho JSON, điều kiện đường dẫn và lựa chọn truy vấn trong Oracle

## 1. Vì sao dữ liệu JSON cần chiến lược chỉ mục?

JSON cho phép một tài liệu chứa nhiều thuộc tính có cấu trúc linh hoạt. Hai hàng trong cùng một bảng có thể có các trường khác nhau, object lồng nhau hoặc mảng có số phần tử khác nhau. Tính linh hoạt này hữu ích cho ứng dụng, nhưng làm cho việc truy vấn và lập chỉ mục khác với bảng quan hệ có cột cố định.

Ví dụ một đơn hàng:

```json
{
  "PONumber": 1600,
  "Reference": "AB-2026-001",
  "Customer": {
    "Name": "Minh Anh",
    "Region": "South"
  },
  "Status": "OPEN",
  "LineItems": [
    {
      "ItemNumber": 1,
      "Part": {"Number": "A100", "Description": "Keyboard"},
      "Quantity": 2,
      "UnitPrice": 45
    },
    {
      "ItemNumber": 2,
      "Part": {"Number": "B200", "Description": "Monitor"},
      "Quantity": 1,
      "UnitPrice": 180
    }
  ]
}
```

Một truy vấn có thể tìm đơn hàng theo `PONumber`, lọc theo `Customer.Region`, kiểm tra có dòng hàng với `Quantity` lớn hơn một ngưỡng, hoặc đọc từng phần tử của `LineItems`.

Nếu không có chỉ mục phù hợp, Oracle có thể phải đọc nhiều hàng rồi đánh giá biểu thức JSON trên từng tài liệu. Với bảng nhỏ, chi phí có thể chấp nhận được. Với hàng triệu tài liệu, truy vấn lặp lại có thể tạo nhiều I/O và CPU.

Oracle hỗ trợ một số cách lập chỉ mục JSON với mục tiêu khác nhau:

- **JSON search index:** chỉ mục tổng quát cho truy vấn JSON linh hoạt, nhiều đường dẫn và điều kiện tồn tại/nội dung.
- **Function-based B-tree index:** chỉ mục có mục tiêu cho một scalar path đã biết, như mã đơn hàng, trạng thái, số tiền hoặc ngày.
- **Virtual column kết hợp B-tree index:** đưa một JSON scalar path thành cột ảo để dùng lại trong SQL, constraint và index.
- **Chỉ mục quan hệ thông thường hoặc composite index:** kết hợp cột quan hệ với biểu thức JSON khi workload thường lọc theo tenant, loại bản ghi hoặc ngày trước khi lọc JSON.

Không có một chỉ mục tốt nhất cho mọi truy vấn. Cần bắt đầu từ predicate thực tế, kiểu dữ liệu của giá trị JSON, tính chọn lọc, tần suất cập nhật và execution plan.

Bài học thuộc chương **JSON và XML**, tập trung vào JSON path expression, điều kiện đường dẫn, `JSON_EXISTS`, `JSON_VALUE`, `JSON_QUERY`, `JSON_TABLE`, JSON search index, function-based index, lựa chọn truy vấn và cách xác nhận optimizer sử dụng chỉ mục.

## 2. Chuẩn bị bảng lưu JSON

Oracle có thể lưu JSON trong các kiểu văn bản như `VARCHAR2`, `CLOB`, `BLOB` và hỗ trợ kiểu dữ liệu JSON native ở các phiên bản mới hơn. Các SQL/JSON function làm việc với dữ liệu JSON theo kiểu lưu trữ và phiên bản được hỗ trợ.

### 2.1. Bảng JSON lưu trong CLOB

```sql
CREATE TABLE purchase_orders (
    order_id NUMBER PRIMARY KEY,
    tenant_id NUMBER NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    po_document CLOB
        CONSTRAINT po_document_is_json CHECK (po_document IS JSON)
);
```

`IS JSON` là điều kiện kiểm tra nội dung cột có phải JSON hợp lệ theo semantics Oracle hay không. Constraint giúp ngăn dữ liệu không phải JSON đi vào cột văn bản được dùng như tài liệu JSON.

Trong hệ thống cũ, JSON có thể được lưu bằng `VARCHAR2` hoặc `BLOB`; cần kiểm tra giới hạn kích thước, character set và cách client truyền dữ liệu.

### 2.2. JSON native type

Oracle Database 21c giới thiệu kiểu dữ liệu JSON native trong các cấu hình hỗ trợ. Ví dụ khái niệm:

```sql
CREATE TABLE native_json_orders (
    order_id NUMBER PRIMARY KEY,
    po_document JSON
);
```

Kiểu JSON native lưu dữ liệu theo định dạng nhị phân được Oracle quản lý, thay vì chỉ lưu văn bản JSON. Khả năng cụ thể phụ thuộc phiên bản và dịch vụ database. Không dùng cú pháp native JSON nếu hệ thống mục tiêu chưa hỗ trợ; CLOB/BLOB kèm `IS JSON` vẫn là mô hình phổ biến ở các phiên bản trước.

### 2.3. JSON là dữ liệu có kiểu, không phải chuỗi tùy ý

Trong tài liệu JSON, các giá trị có kiểu:
- Number: `1600`, `45.5`.
- String: `"OPEN"`.
- Boolean: `true`, `false`.
- JSON null: `null`.
- Object: `{ ... }`.
- Array: `[ ... ]`.

Khi truy vấn, cần giữ đúng kiểu. So sánh số bằng giá trị SQL `NUMBER`, không chuyển số thành chuỗi rồi so sánh theo thứ tự từ điển. Tương tự, không dùng một path scalar nếu path có thể trả về object hoặc array.

## 3. Cú pháp JSON path cơ bản

SQL/JSON path expression chỉ vị trí hoặc tập giá trị trong tài liệu JSON. Path thường bắt đầu bằng `$`, biểu thị root.

Ví dụ với `po_document`:

| Path | Ý nghĩa |
|---|---|
| `$` | Toàn bộ tài liệu |
| `$.PONumber` | Thuộc tính `PONumber` ở root |
| `$.Customer.Name` | Tên khách hàng trong object `Customer` |
| `$.Customer.Region` | Khu vực khách hàng |
| `$.LineItems` | Mảng `LineItems` |
| `$.LineItems[0]` | Phần tử đầu tiên của mảng theo chỉ số path |
| `$.LineItems[*]` | Mọi phần tử trong mảng |
| `$.LineItems[*].Quantity` | Thuộc tính `Quantity` của từng phần tử |
| `$.LineItems[*].Part.Number` | Mã part của từng dòng hàng |

Tên thuộc tính trong path phân biệt chữ hoa/chữ thường theo tên field trong tài liệu JSON. `$.PONumber` và `$.ponumber` không nên được coi là cùng một path.

### 3.1. Truy cập object và array

Object dùng tên field:

```sql
'$.Customer.Region'
```

Array dùng chỉ số hoặc wildcard:

```sql
'$.LineItems[0].Quantity'
'$.LineItems[*].Quantity'
```

`[*]` chọn các phần tử trong mảng. Nếu đường dẫn đi qua object hoặc array không đúng hình dạng mong đợi, kết quả phụ thuộc mode path và semantics của SQL/JSON function.

### 3.2. Strict và lax path mode

Oracle SQL/JSON path hỗ trợ hai mode:
- `lax`: cho phép một số chuyển đổi linh hoạt giữa object/array trong quá trình đi theo path; đây là mode mặc định.
- `strict`: yêu cầu đường dẫn khớp chặt hơn với cấu trúc được mô tả.

Ví dụ:

```sql
JSON_VALUE(po_document, 'strict $.PONumber' RETURNING NUMBER)
```

Dùng `strict` khi cấu trúc dữ liệu được kiểm soát và muốn phát hiện path không khớp. `lax` hữu ích khi tài liệu có biến thể cấu trúc được chấp nhận. Hãy chọn mode có chủ đích, không dựa vào sự linh hoạt ngầm nếu dữ liệu cần hợp đồng chặt chẽ.

### 3.3. Filter expression trong path

Filter expression dùng `?()` để lọc phần tử. Ký hiệu `@` biểu thị phần tử hiện tại đang được xét.

Ví dụ tìm phần tử LineItems có số lượng ít nhất 2:

```sql
'$.LineItems[*]?(@.Quantity >= 2)'
```

Tìm phần tử có mã part là `"A100"`:

```sql
'$.LineItems[*]?(@.Part.Number == "A100")'
```

Tìm dòng hàng vừa có số lượng lớn vừa có giá trị đơn giá cao:

```sql
'$.LineItems[*]?(@.Quantity >= 2 && @.UnitPrice > 100)'
```

Các điều kiện trong cùng filter được đánh giá trên cùng phần tử mảng hiện tại. Đây là điểm quan trọng khi kiểm tra nhiều thuộc tính của một dòng hàng.

### 3.4. Truyền giá trị động vào path bằng PASSING

Không nối chuỗi đầu vào người dùng vào JSON path. Dùng `PASSING` để truyền giá trị SQL an toàn:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_EXISTS(
    po_document,
    '$.LineItems[*]?(@.Quantity >= $minQty)'
    PASSING :min_quantity AS "minQty"
);
```

`:min_quantity` là bind variable của SQL. `$minQty` là biến được tham chiếu trong path; `"minQty"` là tên gán trong `PASSING`.

Lợi ích:
- Tránh nối chuỗi path từ input không tin cậy.
- Dùng bind variable, hỗ trợ cursor sharing.
- Giữ kiểu giá trị theo tham số truyền.
- Tách logic path khỏi dữ liệu đầu vào.

### 3.5. Kết hợp nhiều điều kiện trên array

Nếu cần tìm đơn hàng có một dòng hàng mà cùng dòng đó thỏa cả hai điều kiện, viết một filter:

```sql
JSON_EXISTS(
    po_document,
    '$.LineItems[*]?(@.Part.Number == "A100" && @.Quantity >= 2)'
)
```

Không tách thành hai điều kiện JSON_EXISTS độc lập nếu nghiệp vụ yêu cầu cùng một phần tử:

```sql
-- Hai điều kiện này có thể khớp trên hai phần tử LineItems khác nhau.
JSON_EXISTS(po_document, '$.LineItems[*]?(@.Part.Number == "A100")')
AND JSON_EXISTS(po_document, '$.LineItems[*]?(@.Quantity >= 2)')
```

Điều kiện thứ nhất có thể khớp dòng hàng số 1, điều kiện thứ hai khớp dòng hàng số 2. Khi cần cùng dòng, gộp điều kiện vào một filter expression.

## 4. Chọn SQL/JSON function theo mục tiêu truy vấn

Các hàm SQL/JSON có mục đích khác nhau. Chọn đúng hàm giúp câu SQL rõ ràng và tạo cơ hội cho optimizer dùng chỉ mục phù hợp.

| Hàm/điều kiện | Mục tiêu | Kiểu kết quả |
|---|---|---|
| `JSON_EXISTS` | Kiểm tra path có khớp hay không | Boolean condition trong SQL |
| `JSON_VALUE` | Lấy một scalar | SQL scalar như VARCHAR2, NUMBER |
| `JSON_QUERY` | Lấy object hoặc array JSON | JSON fragment |
| `JSON_TABLE` | Chiếu tài liệu JSON thành hàng/cột quan hệ | Row source dạng bảng |
| `JSON_TEXTCONTAINS` | Tìm nội dung text theo path với JSON search index | Điều kiện tìm kiếm text, tùy hỗ trợ phiên bản |

### 4.1. JSON_EXISTS: kiểm tra sự tồn tại

Dùng `JSON_EXISTS` khi chỉ cần biết một path hoặc điều kiện có khớp hay không:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_EXISTS(po_document, '$.Customer.Region');
```

Tìm đơn hàng có trạng thái OPEN:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_EXISTS(
    po_document,
    '$.Status?(@ == "OPEN")'
);
```

Tìm đơn hàng có dòng hàng số lượng lớn hơn 5:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_EXISTS(
    po_document,
    '$.LineItems[*]?(@.Quantity > 5)'
);
```

`JSON_EXISTS` phù hợp với predicate dạng tồn tại, đặc biệt khi cần kiểm tra object/array lồng nhau mà không cần trả giá trị ra SELECT list.

### 4.2. JSON_VALUE: lấy scalar có kiểu

```sql
SELECT order_id,
       JSON_VALUE(
           po_document,
           '$.PONumber' RETURNING NUMBER
       ) AS po_number
FROM purchase_orders;
```

Lọc theo mã đơn hàng:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_VALUE(
    po_document,
    '$.PONumber' RETURNING NUMBER
) = :po_number;
```

Lọc theo số lượng scalar:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_VALUE(
    po_document,
    '$.Customer.Region' RETURNING VARCHAR2(30)
) = :region;
```

`JSON_VALUE` dành cho một scalar. Nếu path trỏ đến object hoặc array, hãy dùng `JSON_QUERY` hoặc `JSON_TABLE`.

Có thể chỉ định hành vi khi thiếu path hoặc dữ liệu không đúng kiểu:

```sql
JSON_VALUE(
    po_document,
    '$.PONumber'
    RETURNING NUMBER
    NULL ON EMPTY
    ERROR ON ERROR
)
```

Chọn `ERROR ON ERROR` khi dữ liệu sai cấu trúc phải được phát hiện; chọn `NULL ON ERROR` khi hợp đồng ứng dụng cho phép giá trị không đọc được được biểu diễn thành SQL NULL. Không để mặc định hành vi lỗi trở thành điều kiện nghiệp vụ ngầm.

### 4.3. JSON null, field thiếu và SQL NULL

Ba trường hợp cần phân biệt:
- Field không tồn tại trong tài liệu.
- Field tồn tại với giá trị JSON `null`.
- Biểu thức SQL trả về SQL `NULL` do path/type/error behavior.

`JSON_VALUE` thường trả SQL NULL cho JSON null và có thể trả NULL cho field không tồn tại theo `ON EMPTY`/default behavior. Vì vậy, chỉ nhìn kết quả `JSON_VALUE IS NULL` có thể không phân biệt được hai trường hợp.

Nếu cần kiểm tra field có tồn tại, dùng `JSON_EXISTS`:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_EXISTS(po_document, '$.Customer.Region');
```

Nếu cần phân biệt field tồn tại nhưng giá trị JSON null, hãy thiết kế predicate và kiểm thử rõ ràng theo semantics `JSON_EXISTS` và `JSON_VALUE` của phiên bản Oracle.

### 4.4. JSON_QUERY: lấy object hoặc array

```sql
SELECT order_id,
       JSON_QUERY(
           po_document,
           '$.Customer'
           RETURNING CLOB
       ) AS customer_json
FROM purchase_orders;
```

Lấy mảng LineItems:

```sql
SELECT order_id,
       JSON_QUERY(
           po_document,
           '$.LineItems'
           RETURNING CLOB
       ) AS line_items_json
FROM purchase_orders;
```

`JSON_QUERY` dành cho JSON object/array hoặc fragment, không dùng thay `JSON_VALUE` để lấy một số hay chuỗi scalar.

### 4.5. JSON_TABLE: biến JSON thành hàng và cột

Khi cần join, aggregate hoặc xử lý từng phần tử mảng bằng SQL quan hệ, `JSON_TABLE` thường là lựa chọn tự nhiên:

```sql
SELECT p.order_id,
       jt.item_number,
       jt.part_number,
       jt.quantity,
       jt.unit_price
FROM purchase_orders p,
     JSON_TABLE(
         p.po_document,
         '$'
         COLUMNS (
             po_number NUMBER PATH '$.PONumber',
             NESTED PATH '$.LineItems[*]'
             COLUMNS (
                 item_number NUMBER PATH '$.ItemNumber',
                 part_number VARCHAR2(50) PATH '$.Part.Number',
                 quantity NUMBER PATH '$.Quantity',
                 unit_price NUMBER PATH '$.UnitPrice'
             )
         )
     ) jt;
```

Mỗi phần tử `LineItems` trở thành một hàng. Các cột bên trong `NESTED PATH` được lấy tương đối với phần tử hiện tại.

Dùng `JSON_TABLE` khi:
- Cần biến mảng JSON thành nhiều hàng.
- Cần JOIN với bảng quan hệ.
- Cần GROUP BY, SUM, COUNT hoặc analytic function trên phần tử JSON.
- Cần chiếu nhiều scalar path trong một lần đọc tài liệu.

### 4.6. JSON_TEXTCONTAINS: tìm nội dung text

Trong các phiên bản hỗ trợ JSON search index, `JSON_TEXTCONTAINS` có thể dùng để tìm token/text trong nội dung của một path:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_TEXTCONTAINS(
    po_document,
    '$.Customer.Name',
    'Minh'
);
```

Đây là tìm kiếm text theo semantics Oracle Text, không tương đương so sánh scalar chính xác bằng `JSON_VALUE`. Dùng `JSON_VALUE` cho equality/range của scalar và `JSON_TEXTCONTAINS` cho nhu cầu text search được hỗ trợ.

## 5. JSON search index: chỉ mục tổng quát cho truy vấn linh hoạt

JSON search index là domain index được tạo bằng `CREATE SEARCH INDEX ... FOR JSON`. Nó được thiết kế để hỗ trợ nhiều kiểu truy vấn JSON, đặc biệt khi ứng dụng truy vấn nhiều path khác nhau mà không thể tạo một B-tree riêng cho từng path.

### 5.1. Tạo JSON search index

```sql
CREATE SEARCH INDEX po_document_search_ix
ON purchase_orders (po_document)
FOR JSON;
```

Chỉ mục này lập chỉ mục nội dung JSON để hỗ trợ các truy vấn được Oracle hỗ trợ trên tài liệu, ví dụ predicate `JSON_EXISTS` và một số truy vấn text/path.

JSON search index phù hợp khi:
- Có nhiều path khác nhau được truy vấn.
- Truy vấn chứa filter trên object/array lồng nhau.
- Cần tìm kiếm nội dung JSON linh hoạt.
- Không thể dự đoán đầy đủ các path mà ứng dụng sẽ dùng.

### 5.2. Ví dụ dùng search index với JSON_EXISTS

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_EXISTS(
    po_document,
    '$.Customer?(@.Region == "South")'
);
```

Hoặc:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_EXISTS(
    po_document,
    '$.LineItems[*]?(@.Quantity >= 3 && @.UnitPrice > 50)'
);
```

Optimizer có thể dùng JSON search index nếu query shape và điều kiện phù hợp. Việc tạo index không bảo đảm mọi truy vấn JSON đều sử dụng nó; optimizer vẫn dựa vào cost, statistics và khả năng hỗ trợ của index.

### 5.3. Đồng bộ JSON search index

JSON search index được xây dựng trên cơ chế domain index của Oracle Text. Cần chú ý chính sách đồng bộ index sau DML.

Có thể cấu hình đồng bộ khi commit:

```sql
CREATE SEARCH INDEX po_document_search_ix
ON purchase_orders (po_document)
FOR JSON
PARAMETERS ('SYNC (ON COMMIT)');
```

`SYNC (ON COMMIT)` giúp index được đồng bộ khi transaction commit, nhưng có thể tăng thời gian commit và chi phí DML. Với workload ghi lớn, tổ chức có thể chọn cơ chế đồng bộ theo lịch hoặc đồng bộ thủ công theo chính sách vận hành.

Đồng bộ thủ công, khi được cấu hình và cấp quyền phù hợp:

```sql
BEGIN
    CTX_DDL.SYNC_INDEX('PO_DOCUMENT_SEARCH_IX');
END;
/
```

Tên index truyền cho `CTX_DDL` thường được dùng theo tên object trong schema. Cần xác nhận quyền thực thi package và chính sách sync trong môi trường.

### 5.4. Chi phí của JSON search index

Search index không miễn phí:
- Tốn storage cho cấu trúc index và token/path metadata.
- DML trên JSON có thể phát sinh công việc duy trì hoặc sync index.
- Sync on commit có thể tăng commit latency.
- Index build/sync tiêu thụ CPU và I/O.
- Khi tài liệu lớn hoặc cập nhật thường xuyên, cần đánh giá độ trễ index và dung lượng.

Không tạo JSON search index chỉ vì cột có kiểu JSON. Tạo khi workload truy vấn thực tế hưởng lợi.

## 6. Function-based B-tree index cho scalar path

Nếu truy vấn thường xuyên lọc theo một số scalar path đã biết, function-based B-tree index thường gọn và hiệu quả hơn một JSON search index tổng quát.

### 6.1. Tạo index trên JSON_VALUE

Ví dụ `PONumber` là số:

```sql
CREATE INDEX po_number_ix
ON purchase_orders (
    JSON_VALUE(
        po_document,
        '$.PONumber' RETURNING NUMBER
    )
);
```

Truy vấn có biểu thức tương ứng:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_VALUE(
    po_document,
    '$.PONumber' RETURNING NUMBER
) = :po_number;
```

Oracle có thể dùng function-based index để tìm giá trị scalar theo B-tree thay vì đọc và đánh giá JSON trên mọi hàng.

### 6.2. Kiểu dữ liệu phải phù hợp

Nếu `PONumber` là number, dùng `RETURNING NUMBER`:

```sql
JSON_VALUE(po_document, '$.PONumber' RETURNING NUMBER)
```

Nếu `Region` là string, dùng kiểu ký tự phù hợp:

```sql
JSON_VALUE(
    po_document,
    '$.Customer.Region' RETURNING VARCHAR2(30)
)
```

Đừng lập index số nhưng truy vấn như chuỗi. Chuyển kiểu không nhất quán có thể làm thay đổi semantics, gây lỗi dữ liệu hoặc khiến optimizer không khớp biểu thức index.

### 6.3. Biểu thức truy vấn cần khớp biểu thức index

Để optimizer nhận diện function-based index, hãy giữ nhất quán:
- Cột JSON nguồn.
- JSON path.
- Kiểu trả về.
- Các tùy chọn xử lý lỗi/empty được đưa vào biểu thức.
- Các phép biến đổi bổ sung như `UPPER`, `TRIM` nếu có.

Ví dụ index:

```sql
CREATE INDEX po_region_ix
ON purchase_orders (
    JSON_VALUE(
        po_document,
        '$.Customer.Region'
        RETURNING VARCHAR2(30)
        NULL ON EMPTY
        NULL ON ERROR
    )
);
```

Query nên dùng cùng biểu thức:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_VALUE(
    po_document,
    '$.Customer.Region'
    RETURNING VARCHAR2(30)
    NULL ON EMPTY
    NULL ON ERROR
) = :region;
```

Nếu query dùng một expression khác, ví dụ ép kiểu hoặc bọc `UPPER` mà index không có, Oracle có thể không sử dụng index đó. Kiểm tra execution plan thay vì đoán.

### 6.4. Index trên ngày hoặc thời gian

Nếu JSON chứa ngày theo định dạng được kiểm soát, có thể dùng `JSON_VALUE` với kiểu trả về được phiên bản hỗ trợ và expression phù hợp. Cần đặc biệt cẩn thận với format và timezone.

Một cách khác là chuẩn hóa ngày thành ISO-8601 trong JSON rồi dùng kiểu SQL/JSON được hỗ trợ, hoặc tạo virtual column có chuyển đổi rõ ràng. Không so sánh chuỗi ngày tùy ý như thể đó là DATE.

## 7. Virtual column cho JSON path

Khi nhiều truy vấn cùng dùng một path, virtual column giúp đặt tên cho scalar expression và tránh lặp lại biểu thức dài.

### 7.1. Tạo virtual column

```sql
ALTER TABLE purchase_orders ADD (
    po_number GENERATED ALWAYS AS (
        JSON_VALUE(
            po_document,
            '$.PONumber' RETURNING NUMBER
        )
    ) VIRTUAL
);
```

Tạo B-tree index:

```sql
CREATE INDEX po_number_virtual_ix
ON purchase_orders (po_number);
```

Truy vấn:

```sql
SELECT order_id
FROM purchase_orders
WHERE po_number = :po_number;
```

### 7.2. Virtual column kết hợp cột quan hệ

Nếu mọi truy vấn đều lọc theo tenant rồi theo mã đơn hàng, tạo composite index:

```sql
ALTER TABLE purchase_orders ADD (
    po_region GENERATED ALWAYS AS (
        JSON_VALUE(
            po_document,
            '$.Customer.Region' RETURNING VARCHAR2(30)
        )
    ) VIRTUAL
);

CREATE INDEX po_tenant_region_ix
ON purchase_orders (tenant_id, po_region);
```

Truy vấn:

```sql
SELECT order_id
FROM purchase_orders
WHERE tenant_id = :tenant_id
  AND po_region = :region;
```

Thứ tự cột trong composite B-tree index cần phù hợp với predicate và thứ tự lọc phổ biến. Equality trên cột dẫn đầu thường giúp index phục vụ các điều kiện tiếp theo; hãy đánh giá workload thực tế và execution plan.

### 7.3. Virtual column có thể hỗ trợ constraint

Nếu JSON path đại diện cho một mã nghiệp vụ cần duy nhất, có thể cân nhắc unique index trên virtual column:

```sql
CREATE UNIQUE INDEX po_number_unique_ix
ON purchase_orders (po_number);
```

Chỉ làm điều này nếu `PONumber` thực sự phải duy nhất trong phạm vi toàn bảng. Nếu duy nhất theo tenant, dùng composite unique index `(tenant_id, po_number)`.

Cần quyết định semantics cho field thiếu, JSON null và dữ liệu lỗi. B-tree index xử lý SQL NULL theo quy tắc riêng; hàng có key expression NULL có thể không tạo entry trong index một cột. Nếu cần bắt buộc field tồn tại, hãy kiểm soát bằng validation/constraint phù hợp, không dựa vào index để thay thế kiểm tra dữ liệu.

## 8. Chỉ mục và array path

Array tạo ra một thách thức khác: một tài liệu có thể chứa nhiều giá trị cho cùng một path. Ví dụ `LineItems[*].Part.Number` có nhiều mã part trong một tài liệu.

### 8.1. Khi nào JSON search index phù hợp?

Nếu cần tìm tài liệu có bất kỳ phần tử array nào khớp điều kiện:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_EXISTS(
    po_document,
    '$.LineItems[*]?(@.Part.Number == "A100")'
);
```

JSON search index thường là lựa chọn tổng quát để hỗ trợ các truy vấn path/filter linh hoạt như vậy.

### 8.2. Không ép array thành một scalar

`JSON_VALUE` được thiết kế để lấy một scalar. Nếu path có thể khớp nhiều phần tử, đừng giả định `JSON_VALUE` sẽ trả tất cả giá trị trong array. Dùng:
- `JSON_EXISTS` nếu chỉ cần biết có phần tử phù hợp.
- `JSON_TABLE` nếu cần đưa mọi phần tử thành hàng.
- JSON search index cho truy vấn ad hoc path/array được hỗ trợ.

### 8.3. JSON_TABLE để lọc phần tử array

```sql
SELECT DISTINCT p.order_id
FROM purchase_orders p,
     JSON_TABLE(
         p.po_document,
         '$.LineItems[*]'
         COLUMNS (
             part_number VARCHAR2(50) PATH '$.Part.Number',
             quantity NUMBER PATH '$.Quantity'
         )
     ) li
WHERE li.part_number = :part_number
  AND li.quantity >= :minimum_quantity;
```

Cách này hữu ích khi cần join/aggregate trên từng phần tử. Tuy nhiên, `JSON_TABLE` có thể phải đọc và chiếu các phần tử của nhiều tài liệu. Nếu truy vấn chỉ cần kiểm tra tồn tại, `JSON_EXISTS` có thể đơn giản hơn và dễ tận dụng JSON search index hơn.

### 8.4. Multivalue index ở các phiên bản mới

Một số phiên bản Oracle mới hỗ trợ các cơ chế multivalue index cho nhiều scalar value được trích từ một JSON array. Cú pháp, giới hạn path và cách optimizer dùng index phụ thuộc release. Nếu workload chủ yếu lọc một array path đã biết, hãy kiểm tra tài liệu phiên bản mục tiêu về multivalue function-based index trước khi chọn JSON search index tổng quát hoặc `JSON_TABLE`.

Không sao chép cú pháp multivalue index từ release khác mà chưa xác nhận hỗ trợ trên database đích.

## 9. Chọn giữa JSON_EXISTS, JSON_VALUE, JSON_QUERY và JSON_TABLE

Một lỗi phổ biến là dùng một hàm cho mọi kiểu truy vấn. Hãy chọn theo kết quả cần lấy.

### 9.1. Chỉ cần biết có khớp không: JSON_EXISTS

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_EXISTS(
    po_document,
    '$.Customer?(@.Region == "South")'
);
```

Không cần lấy `Region` ra SQL chỉ để so sánh sự tồn tại/điều kiện.

### 9.2. Cần scalar để so sánh hoặc hiển thị: JSON_VALUE

```sql
SELECT order_id,
       JSON_VALUE(po_document, '$.PONumber' RETURNING NUMBER)
FROM purchase_orders
WHERE JSON_VALUE(po_document, '$.PONumber' RETURNING NUMBER) >= :min_po;
```

Đây là lựa chọn phù hợp cho scalar path đã biết và có thể lập function-based index.

### 9.3. Cần object/array JSON: JSON_QUERY

```sql
SELECT JSON_QUERY(
           po_document,
           '$.Customer'
           RETURNING CLOB
       )
FROM purchase_orders;
```

Không chuyển object/array thành chuỗi scalar bằng JSON_VALUE.

### 9.4. Cần phân rã tài liệu thành quan hệ: JSON_TABLE

```sql
SELECT p.order_id,
       jt.part_number,
       SUM(jt.quantity) AS total_quantity
FROM purchase_orders p,
     JSON_TABLE(
         p.po_document,
         '$.LineItems[*]'
         COLUMNS (
             part_number VARCHAR2(50) PATH '$.Part.Number',
             quantity NUMBER PATH '$.Quantity'
         )
     ) jt
GROUP BY p.order_id, jt.part_number;
```

`JSON_TABLE` giúp dùng JOIN, GROUP BY và analytic SQL trên nội dung JSON.

### 9.5. Cần tìm từ trong nội dung text: JSON_TEXTCONTAINS

Dùng khi mục tiêu là tìm kiếm text/token theo path và JSON search index hỗ trợ. Không thay thế equality hoặc range trên scalar.

## 10. Kết hợp cột quan hệ với JSON predicate

Nhiều ứng dụng dùng JSON cho thuộc tính linh hoạt nhưng vẫn có cột quan hệ cho tenant, trạng thái xử lý, thời gian tạo hoặc khóa chính.

Ví dụ:

```sql
SELECT order_id
FROM purchase_orders
WHERE tenant_id = :tenant_id
  AND created_at >= :from_time
  AND JSON_EXISTS(
      po_document,
      '$.Status?(@ == "OPEN")'
  );
```

Có thể có nhiều chiến lược:
- Index B-tree trên `(tenant_id, created_at)` để thu hẹp tập hàng trước.
- JSON search index trên `po_document` để hỗ trợ predicate JSON.
- Function-based index trên `JSON_VALUE(... '$.Status' ...)` nếu trạng thái trong JSON được truy vấn thường xuyên.
- Composite index quan hệ + virtual column nếu workload có mẫu ổn định.

Không nhất thiết mọi predicate phải được phục vụ bởi một index duy nhất. Optimizer có thể chọn một index, kết hợp nhiều access path hoặc full scan tùy cost.

### 10.1. Khi JSON path ổn định và có selectivity cao

Ví dụ trạng thái JSON được truy vấn thường xuyên:

```sql
CREATE INDEX po_status_ix
ON purchase_orders (
    JSON_VALUE(po_document, '$.Status' RETURNING VARCHAR2(20))
);
```

Query:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_VALUE(
    po_document,
    '$.Status' RETURNING VARCHAR2(20)
) = 'OPEN';
```

Nếu status chỉ có hai giá trị và phần lớn bảng là OPEN, B-tree index có thể không đem lại lợi ích như kỳ vọng. Selectivity và clustering factor ảnh hưởng quyết định của optimizer.

### 10.2. Khi tenant là điều kiện dẫn đầu

```sql
CREATE INDEX po_tenant_status_ix
ON purchase_orders (
    tenant_id,
    JSON_VALUE(po_document, '$.Status' RETURNING VARCHAR2(20))
);
```

Truy vấn nên dùng cả hai predicate:

```sql
SELECT order_id
FROM purchase_orders
WHERE tenant_id = :tenant_id
  AND JSON_VALUE(
      po_document,
      '$.Status' RETURNING VARCHAR2(20)
  ) = :status;
```

Đây là lựa chọn khi pattern truy vấn lặp lại và có tính ổn định. Nếu path thay đổi tùy người dùng, JSON search index có thể phù hợp hơn.

## 11. JSON search index và B-tree index: so sánh lựa chọn

| Tiêu chí | JSON search index | Function-based B-tree index |
|---|---|---|
| Phạm vi | Nhiều path và truy vấn JSON linh hoạt | Một expression/path cụ thể |
| Path | Có thể hỗ trợ nhiều path khác nhau | Path được khai báo trong expression |
| Scalar equality/range | Có thể hỗ trợ theo query và release; cần xem plan | Rất phù hợp cho scalar path đã biết |
| Array/filter | Thường phù hợp với JSON_EXISTS và truy vấn path linh hoạt | Cần cơ chế multivalue/index chuyên biệt ở release hỗ trợ |
| Text search | Có thể hỗ trợ JSON_TEXTCONTAINS | Không thay thế full-text search |
| Storage | Có thể lớn do index path/token tổng quát | Thường tập trung vào key expression |
| DML maintenance | Có chi phí sync/maintain domain index | Có chi phí duy trì B-tree mỗi DML |
| Thiết kế | Ít cần tạo index riêng cho từng path | Tạo riêng theo truy vấn quan trọng |
| Khi phù hợp | Ad hoc JSON search, nhiều path | Query ổn định trên một số scalar path |

### 11.1. Không phải lúc nào JSON search index cũng thắng

Nếu ứng dụng chỉ lọc `PONumber = :x` trên một scalar path, B-tree function-based index có thể nhỏ và hiệu quả hơn. Search index tổng quát có thể tạo overhead storage và sync không cần thiết.

### 11.2. Không phải lúc nào B-tree cũng đủ

Nếu người dùng có thể tìm theo nhiều path lồng nhau, array và điều kiện nội dung không cố định, tạo một B-tree cho mỗi path sẽ khó quản lý. JSON search index có thể đáp ứng tốt hơn.

### 11.3. Có thể dùng cả hai

Một bảng có thể có JSON search index cho truy vấn linh hoạt và một số B-tree index cho các path scalar quan trọng. Cần cân đối:
- Storage.
- DML throughput.
- Thời gian sync.
- Chi phí rebuild.
- Khả năng optimizer chọn access path.

Chỉ tạo index khi có workload chứng minh giá trị.

## 12. Index expression, kiểu dữ liệu và xử lý lỗi

Index JSON phụ thuộc chặt vào cách chuyển dữ liệu JSON thành SQL scalar.

### 12.1. Numeric path

```sql
CREATE INDEX po_quantity_ix
ON purchase_orders (
    JSON_VALUE(
        po_document,
        '$.Priority' RETURNING NUMBER
        NULL ON EMPTY
        ERROR ON ERROR
    )
);
```

Query cần biểu thức tương ứng:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_VALUE(
    po_document,
    '$.Priority' RETURNING NUMBER
    NULL ON EMPTY
    ERROR ON ERROR
) >= :min_priority;
```

Nếu có tài liệu chứa chuỗi `"high"` trong field được kỳ vọng là number, `ERROR ON ERROR` làm dữ liệu sai được phát hiện thay vì âm thầm biến thành NULL.

### 12.2. Missing field và NULL index key

Nếu path không tồn tại và expression trả SQL NULL, B-tree index một cột không tạo entry cho key NULL. Điều này có nghĩa truy vấn `... IS NULL` có thể không được phục vụ như một equality lookup thông thường bởi index một cột.

Nếu cần tìm hàng thiếu field, cân nhắc:
- JSON search index với `JSON_EXISTS`/điều kiện phù hợp.
- Virtual column kết hợp một cột NOT NULL trong composite index.
- Thiết kế validation để field bắt buộc luôn tồn tại.
- Một cột trạng thái hoặc cờ riêng nếu truy vấn này quan trọng.

Không tạo biểu thức thay thế NULL tùy tiện nếu giá trị thay thế có thể trùng với dữ liệu hợp lệ.

### 12.3. Kiểm soát dữ liệu sai cấu trúc

Một JSON column có thể hợp lệ về cú pháp nhưng sai schema nghiệp vụ. Ví dụ `Quantity` là chuỗi thay vì number. Có thể:
- Validate ở ứng dụng trước khi ghi.
- Dùng `JSON_VALUE ... ERROR ON ERROR` ở truy vấn/constraint phù hợp.
- Dùng `JSON_TABLE` với kiểu cột rõ ràng.
- Dùng JSON schema validation nếu phiên bản và kiến trúc hỗ trợ.
- Chuẩn hóa field quan trọng thành cột quan hệ.

### 12.4. Đừng bọc expression tùy tiện

Ví dụ:

```sql
WHERE TO_NUMBER(
    JSON_VALUE(po_document, '$.PONumber')
) = :po_number
```

Nếu index được tạo trên `JSON_VALUE(... RETURNING NUMBER)`, expression `TO_NUMBER(JSON_VALUE(...))` có thể không khớp index. Ưu tiên biểu thức JSON_VALUE có kiểu trả về tường minh ngay từ đầu.

## 13. Điều kiện đường dẫn và kiểu dữ liệu

### 13.1. So sánh number với number

```sql
JSON_EXISTS(
    po_document,
    '$.LineItems[*]?(@.Quantity >= 10)'
)
```

Điều kiện path so sánh giá trị số theo kiểu JSON. Nếu dữ liệu thực tế chứa chuỗi `"10"` thay vì number `10`, semantics khác và có thể không khớp như mong đợi.

### 13.2. So sánh string

```sql
JSON_EXISTS(
    po_document,
    '$.Status?(@ == "OPEN")'
)
```

String trong JSON path dùng dấu nháy kép bên trong SQL string literal dấu nháy đơn.

### 13.3. Boolean và null

Các giá trị Boolean JSON là `true` và `false`, không phải chuỗi `"true"` hoặc `"false"`. JSON `null` cũng khác chuỗi `"null"` và khác SQL NULL.

Hãy kiểm thử predicate trên các tài liệu có:
- Field không tồn tại.
- JSON null.
- Giá trị đúng kiểu.
- Giá trị sai kiểu.
- Array rỗng.
- Object lồng nhau không có field.

### 13.4. Filter path so với SQL predicate

Có thể dùng `JSON_EXISTS` filter:

```sql
WHERE JSON_EXISTS(
    po_document,
    '$.LineItems[*]?(@.Quantity > 3)'
)
```

Hoặc dùng `JSON_TABLE` để chiếu `Quantity` ra SQL rồi lọc:

```sql
SELECT DISTINCT p.order_id
FROM purchase_orders p,
     JSON_TABLE(
         p.po_document,
         '$.LineItems[*]'
         COLUMNS (quantity NUMBER PATH '$.Quantity')
     ) jt
WHERE jt.quantity > 3;
```

Chọn filter path nếu chỉ cần kiểm tra tồn tại. Chọn JSON_TABLE khi cần dùng giá trị phần tử trong phép JOIN, projection hoặc aggregate.

## 14. Kiểm tra optimizer có dùng index không

Tạo index không bảo đảm optimizer sẽ dùng nó. Oracle chọn access path dựa trên statistics, cardinality, selectivity, bind values, chi phí I/O/CPU và khả năng hỗ trợ predicate.

### 14.1. Thu thập statistics

Sau khi tạo index hoặc nạp dữ liệu thử nghiệm, có thể thu thập statistics theo chính sách DBA:

```sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'PURCHASE_ORDERS',
        cascade => TRUE
    );
END;
/
```

Trên production, tuân thủ chính sách statistics hiện hành; không chạy gather thủ công diện rộng khi chưa đánh giá tác động.

### 14.2. Xem execution plan

```sql
EXPLAIN PLAN FOR
SELECT order_id
FROM purchase_orders
WHERE JSON_VALUE(
    po_document,
    '$.PONumber' RETURNING NUMBER
) = 1600;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Nếu muốn xem plan thực thi và runtime statistics, chạy truy vấn với thu thập statistics phù hợp rồi dùng:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE'
    )
);
```

### 14.3. Các dấu hiệu cần tìm

Trong execution plan, xem:
- Index range scan hoặc index unique scan trên function-based index.
- Domain index operation cho JSON search index.
- Predicate Information có đúng JSON expression/path không.
- Estimated Rows và Actual Rows có chênh lệch lớn không.
- Buffer gets và elapsed time.
- Có full table scan hay không và nó có thật sự đắt không.

Full table scan không luôn là dấu hiệu xấu. Nếu truy vấn trả về phần lớn bảng hoặc bảng nhỏ, full scan có thể rẻ hơn index lookup.

### 14.4. Kiểm thử bằng dữ liệu đại diện

Benchmark cần:
1. Số lượng tài liệu gần workload thực tế.
2. Tỷ lệ field thiếu/null và biến thể schema tương tự production.
3. Phân bố giá trị và selectivity thực tế.
4. Cùng bind values hoặc tập bind đại diện.
5. Đo cả query latency và chi phí DML/index maintenance.
6. Kiểm tra kết quả đúng với array semantics.
7. So sánh khi index đã sync và statistics đã cập nhật.

Không chỉ đo một query trên vài chục hàng rồi kết luận cho bảng hàng triệu tài liệu.

## 15. Chi phí duy trì chỉ mục JSON

Index giúp đọc nhanh hơn nhưng làm ghi dữ liệu tốn thêm tài nguyên.

### 15.1. B-tree function-based index

Khi JSON document được INSERT hoặc UPDATE, Oracle cần đánh giá expression index và cập nhật key tương ứng. Nếu một bảng có nhiều JSON path index, mỗi DML có thể phải duy trì nhiều B-tree.

### 15.2. JSON search index

Search index cần duy trì cấu trúc path/value và đồng bộ theo chính sách. Index có thể tăng:
- Storage.
- CPU cho indexing và sync.
- I/O.
- Commit latency nếu dùng sync on commit.
- Thời gian rebuild và vận hành.

### 15.3. Chọn index theo workload đọc/ghi

| Workload | Hướng đánh giá |
|---|---|
| Đọc nhiều, JSON ít thay đổi | Có thể đầu tư search index và B-tree path quan trọng |
| Ghi JSON liên tục, ít truy vấn ad hoc | Hạn chế index tổng quát không cần thiết |
| Một số scalar path được lọc thường xuyên | Function-based B-tree index |
| Nhiều path, object/array linh hoạt | JSON search index |
| Cần join và aggregate array | JSON_TABLE, kết hợp predicate/index phù hợp |
| Tenant + scalar path ổn định | Composite index hoặc virtual column |

Không tạo index cho mọi field JSON chỉ vì field tồn tại.

## 16. Lựa chọn truy vấn theo tình huống

### 16.1. Tìm một đơn hàng theo mã scalar

Dùng `JSON_VALUE` và function-based index:

```sql
CREATE INDEX po_number_ix
ON purchase_orders (
    JSON_VALUE(po_document, '$.PONumber' RETURNING NUMBER)
);

SELECT order_id
FROM purchase_orders
WHERE JSON_VALUE(
    po_document,
    '$.PONumber' RETURNING NUMBER
) = :po_number;
```

### 16.2. Tìm tài liệu có trạng thái phù hợp

Nếu path status là path quan trọng và ổn định, dùng B-tree trên JSON_VALUE. Nếu status chỉ là một trong nhiều path truy vấn linh hoạt, search index có thể phù hợp.

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_EXISTS(
    po_document,
    '$.Status?(@ == "OPEN")'
);
```

### 16.3. Tìm bất kỳ dòng hàng nào vượt ngưỡng

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_EXISTS(
    po_document,
    '$.LineItems[*]?(@.Quantity > $q)'
    PASSING :minimum_quantity AS "q"
);
```

Đây là predicate tồn tại trên array. JSON search index là lựa chọn tổng quát để đánh giá trước.

### 16.4. Tìm dòng hàng rồi tính tổng

```sql
SELECT p.order_id,
       SUM(jt.quantity * jt.unit_price) AS line_total
FROM purchase_orders p,
     JSON_TABLE(
         p.po_document,
         '$.LineItems[*]'
         COLUMNS (
             quantity NUMBER PATH '$.Quantity',
             unit_price NUMBER PATH '$.UnitPrice'
         )
     ) jt
GROUP BY p.order_id;
```

Dùng JSON_TABLE vì cần chiếu nhiều phần tử thành hàng và tính toán quan hệ.

### 16.5. Lấy nguyên object Customer

```sql
SELECT order_id,
       JSON_QUERY(po_document, '$.Customer' RETURNING CLOB)
FROM purchase_orders;
```

Dùng JSON_QUERY vì kết quả là object.

### 16.6. Tìm từ trong một trường mô tả

Nếu cần full-text/token search và release hỗ trợ:

```sql
SELECT order_id
FROM purchase_orders
WHERE JSON_TEXTCONTAINS(
    po_document,
    '$.Description',
    'wireless'
);
```

Dùng JSON search index và xác nhận semantics text search theo cấu hình Oracle Text.

## 17. Mẫu thiết kế index hoàn chỉnh

Giả sử workload chính:
- Mọi truy vấn đều lọc `tenant_id`.
- Một số truy vấn lọc theo `PONumber`.
- Một số truy vấn tìm array item theo điều kiện.
- Một số truy vấn tìm text trong mô tả.

Có thể đánh giá thiết kế:

```sql
CREATE INDEX po_tenant_number_ix
ON purchase_orders (
    tenant_id,
    JSON_VALUE(po_document, '$.PONumber' RETURNING NUMBER)
);
```

JSON search index:

```sql
CREATE SEARCH INDEX po_document_search_ix
ON purchase_orders (po_document)
FOR JSON;
```

Query scalar:

```sql
SELECT order_id
FROM purchase_orders
WHERE tenant_id = :tenant_id
  AND JSON_VALUE(
      po_document,
      '$.PONumber' RETURNING NUMBER
  ) = :po_number;
```

Query array:

```sql
SELECT order_id
FROM purchase_orders
WHERE tenant_id = :tenant_id
  AND JSON_EXISTS(
      po_document,
      '$.LineItems[*]?(@.Part.Number == $part)'
      PASSING :part_number AS "part"
  );
```

Query text:

```sql
SELECT order_id
FROM purchase_orders
WHERE tenant_id = :tenant_id
  AND JSON_TEXTCONTAINS(
      po_document,
      '$.Description',
      :search_text
  );
```

Đây là mẫu định hướng, không phải công thức index tối ưu cho mọi bảng. Cần xem optimizer có thể kết hợp index quan hệ và domain index như thế nào trên phiên bản cụ thể, sau đó đo plan và DML overhead.

## 18. Lỗi thường gặp khi viết path và index

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Sai chữ hoa/chữ thường tên field | Path không khớp | Dùng đúng tên field trong JSON |
| Dùng JSON_VALUE cho object/array | Không lấy được fragment mong muốn | Dùng JSON_QUERY hoặc JSON_TABLE |
| Dùng JSON_QUERY cho scalar | Kết quả không đúng mục tiêu | Dùng JSON_VALUE |
| So sánh number dưới dạng string | Sai thứ tự/kiểu hoặc không khớp | `RETURNING NUMBER` |
| Nối input vào JSON path | Rủi ro injection và cursor sharing kém | Dùng PASSING/bind variable |
| Tách hai JSON_EXISTS cho cùng array element | Có thể khớp hai phần tử khác nhau | Gộp điều kiện vào một filter |
| Bọc JSON_VALUE bằng hàm khác | Không khớp expression index | Dùng expression đồng nhất hoặc tạo index đúng expression |
| Không chỉ định kiểu trả về | Chuyển kiểu không rõ ràng | Dùng RETURNING rõ ràng |
| Dùng `NULL ON ERROR` để che dữ liệu sai | Lỗi schema bị biến thành NULL | Chọn ERROR ON ERROR nếu dữ liệu sai phải bị phát hiện |
| Tạo search index nhưng không quản lý sync | Index có thể trễ so với DML | Chọn sync on commit, manual hoặc scheduled |
| Tạo index cho mọi path | Tăng storage và DML overhead | Chỉ index query quan trọng |
| Cho rằng optimizer luôn dùng index | Kết luận sai hiệu năng | Kiểm tra DBMS_XPLAN và statistics |
| Dùng `FETCH FIRST 1 ROW` để che nhiều match | Che lỗi dữ liệu/cardinality | Xác định quy tắc chọn phần tử hoặc bảo đảm uniqueness |

## 19. Bài thực hành tổng hợp

Các ví dụ dùng bảng riêng trong schema lab. Cần quyền tạo bảng/index và một tablespace phù hợp. Search index có thể cần quyền Oracle Text liên quan. Không chạy trên production chỉ để thử.

### Bước 1. Tạo bảng và dữ liệu JSON

```sql
CREATE TABLE lab_purchase_orders (
    order_id NUMBER PRIMARY KEY,
    tenant_id NUMBER NOT NULL,
    po_document CLOB
        CHECK (po_document IS JSON)
);
```

Chèn tài liệu:

```sql
INSERT INTO lab_purchase_orders (
    order_id,
    tenant_id,
    po_document
)
VALUES (
    1,
    10,
    '{
      "PONumber": 1600,
      "Status": "OPEN",
      "Customer": {"Name": "Minh Anh", "Region": "South"},
      "LineItems": [
        {"ItemNumber": 1, "Part": {"Number": "A100"}, "Quantity": 2, "UnitPrice": 45},
        {"ItemNumber": 2, "Part": {"Number": "B200"}, "Quantity": 1, "UnitPrice": 180}
      ]
    }'
);

INSERT INTO lab_purchase_orders (
    order_id,
    tenant_id,
    po_document
)
VALUES (
    2,
    10,
    '{
      "PONumber": 1601,
      "Status": "CLOSED",
      "Customer": {"Name": "Lan", "Region": "North"},
      "LineItems": [
        {"ItemNumber": 1, "Part": {"Number": "A100"}, "Quantity": 5, "UnitPrice": 40}
      ]
    }'
);

COMMIT;
```

### Bước 2. Thử JSON_EXISTS

```sql
SELECT order_id
FROM lab_purchase_orders
WHERE JSON_EXISTS(
    po_document,
    '$.Customer?(@.Region == "South")'
);
```

### Bước 3. Thử JSON_VALUE

```sql
SELECT order_id,
       JSON_VALUE(po_document, '$.PONumber' RETURNING NUMBER) AS po_number
FROM lab_purchase_orders
WHERE JSON_VALUE(po_document, '$.PONumber' RETURNING NUMBER) >= 1600;
```

### Bước 4. Tạo function-based index

```sql
CREATE INDEX lab_po_number_ix
ON lab_purchase_orders (
    JSON_VALUE(po_document, '$.PONumber' RETURNING NUMBER)
);
```

Chạy lại query ở bước 3 và xem execution plan.

### Bước 5. Thử virtual column

```sql
ALTER TABLE lab_purchase_orders ADD (
    po_status GENERATED ALWAYS AS (
        JSON_VALUE(
            po_document,
            '$.Status' RETURNING VARCHAR2(20)
        )
    ) VIRTUAL
);

CREATE INDEX lab_po_status_ix
ON lab_purchase_orders (tenant_id, po_status);
```

Query:

```sql
SELECT order_id
FROM lab_purchase_orders
WHERE tenant_id = 10
  AND po_status = 'OPEN';
```

### Bước 6. Thử JSON_TABLE

```sql
SELECT p.order_id,
       jt.part_number,
       jt.quantity
FROM lab_purchase_orders p,
     JSON_TABLE(
         p.po_document,
         '$.LineItems[*]'
         COLUMNS (
             part_number VARCHAR2(30) PATH '$.Part.Number',
             quantity NUMBER PATH '$.Quantity'
         )
     ) jt;
```

### Bước 7. Thử JSON_EXISTS trên array

```sql
SELECT order_id
FROM lab_purchase_orders
WHERE JSON_EXISTS(
    po_document,
    '$.LineItems[*]?(@.Part.Number == "A100" && @.Quantity >= 3)'
);
```

Chú ý hai điều kiện cùng áp dụng trên một phần tử `LineItems`.

### Bước 8. Tạo JSON search index

```sql
CREATE SEARCH INDEX lab_po_search_ix
ON lab_purchase_orders (po_document)
FOR JSON;
```

Nếu cần đồng bộ on commit và môi trường hỗ trợ, tạo index theo tham số tương ứng:

```sql
CREATE SEARCH INDEX lab_po_search_rt_ix
ON lab_purchase_orders (po_document)
FOR JSON
PARAMETERS ('SYNC (ON COMMIT)');
```

Không tạo đồng thời hai index này trong một bài lab nếu không có mục tiêu so sánh; ví dụ thứ hai minh họa một chính sách sync khác.

### Bước 9. Kiểm tra metadata index

```sql
SELECT index_name,
       index_type,
       status,
       visibility
FROM user_indexes
WHERE table_name = 'LAB_PURCHASE_ORDERS'
ORDER BY index_name;
```

Kiểm tra JSON LOB metadata nếu cần:

```sql
SELECT table_name,
       column_name,
       securefile
FROM user_lobs
WHERE table_name = 'LAB_PURCHASE_ORDERS';
```

### Bước 10. Xem execution plan

```sql
EXPLAIN PLAN FOR
SELECT order_id
FROM lab_purchase_orders
WHERE JSON_VALUE(
    po_document,
    '$.PONumber' RETURNING NUMBER
) = 1600;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

### Bước 11. Đồng bộ search index thủ công nếu đã chọn chế độ manual

```sql
BEGIN
    CTX_DDL.SYNC_INDEX('LAB_PO_SEARCH_IX');
END;
/
```

Chỉ dùng khi index được cấu hình theo chế độ cần đồng bộ thủ công và tài khoản có quyền phù hợp.

### Bước 12. Dọn đối tượng lab

Chỉ khi chắc chắn đây là các đối tượng do bạn tạo và không còn cần dữ liệu:

```sql
DROP INDEX lab_po_search_ix;
DROP INDEX lab_po_number_ix;
DROP INDEX lab_po_status_ix;
DROP TABLE lab_purchase_orders PURGE;
```

Nếu đã tạo index sync on commit ở bước 8, drop index đó trước khi drop bảng:

```sql
DROP INDEX lab_po_search_rt_ix;
```

`DROP TABLE ... PURGE` xóa bảng và dữ liệu, bỏ qua recycle bin. DDL có implicit commit. Không chạy trên đối tượng nghiệp vụ hoặc dữ liệu dùng chung.

## 20. Quy trình chọn chỉ mục JSON

Khi tối ưu một truy vấn JSON, làm theo trình tự:

1. **Viết predicate thật:** xác định path, điều kiện, kiểu dữ liệu và có liên quan array hay không.
2. **Chọn hàm đúng:** `JSON_EXISTS` cho existence/filter, `JSON_VALUE` cho scalar, `JSON_QUERY` cho fragment, `JSON_TABLE` cho relational projection.
3. **Xác định path có ổn định không:** một vài scalar path ổn định thường phù hợp B-tree; nhiều path ad hoc thường phù hợp search index.
4. **Kết hợp cột quan hệ:** xem tenant, trạng thái, thời gian hoặc partition key có thể thu hẹp tập dữ liệu trước không.
5. **Chọn kiểu trả về:** dùng `RETURNING NUMBER`/`VARCHAR2` đúng với dữ liệu.
6. **Quy định lỗi:** quyết định `NULL ON EMPTY`, `ERROR ON ERROR` hoặc hành vi phù hợp.
7. **Tạo ít index cần thiết:** mỗi index đều tăng storage và chi phí DML.
8. **Thu thập statistics:** bảo đảm optimizer có dữ liệu ước lượng phù hợp.
9. **Xem execution plan:** xác nhận access path và predicate thực tế.
10. **Benchmark:** đo read latency, DML throughput, storage và sync overhead trên dữ liệu đại diện.

### 20.1. Ma trận quyết định nhanh

| Câu hỏi | Hướng lựa chọn |
|---|---|
| Chỉ cần kiểm tra path có tồn tại? | `JSON_EXISTS` |
| Cần so sánh một scalar path ổn định? | `JSON_VALUE` + function-based B-tree index |
| Nhiều query ad hoc trên nhiều path? | JSON search index |
| Cần tìm điều kiện trong array? | `JSON_EXISTS` filter; cân nhắc search index |
| Cần mỗi array item thành một hàng? | `JSON_TABLE` |
| Cần trả object/array nguyên dạng? | `JSON_QUERY` |
| Path scalar thường đi cùng tenant_id? | Virtual column hoặc composite index |
| Cần tìm từ trong text? | JSON search index + `JSON_TEXTCONTAINS` khi phù hợp |
| Dữ liệu ghi rất thường xuyên? | Hạn chế số index, đo chi phí maintenance |
| Index không được dùng? | Kiểm tra expression, kiểu dữ liệu, statistics và plan |

## 21. Câu hỏi tự kiểm tra

**Câu 1.** JSON path `$` biểu thị điều gì?

**Trả lời:** Root của tài liệu JSON.

**Câu 2.** `[*]` dùng để làm gì?

**Trả lời:** Chọn các phần tử của array.

**Câu 3.** Ký hiệu `@` trong filter expression là gì?

**Trả lời:** Phần tử hiện tại đang được đánh giá.

**Câu 4.** Khi nào dùng JSON_EXISTS?

**Trả lời:** Khi cần kiểm tra một path hoặc điều kiện có khớp hay không mà không cần lấy scalar ra SQL.

**Câu 5.** JSON_VALUE trả về loại dữ liệu nào?

**Trả lời:** Một scalar SQL với kiểu trả về được chỉ định hoặc kiểu mặc định theo semantics Oracle.

**Câu 6.** JSON_QUERY phù hợp với dữ liệu nào?

**Trả lời:** Object, array hoặc JSON fragment.

**Câu 7.** JSON_TABLE có tác dụng gì?

**Trả lời:** Chiếu dữ liệu JSON thành row source với các cột SQL, hữu ích cho JOIN, GROUP BY và xử lý array.

**Câu 8.** JSON search index phù hợp với workload nào?

**Trả lời:** Truy vấn JSON linh hoạt trên nhiều path, object/array và điều kiện tìm kiếm được hỗ trợ.

**Câu 9.** Function-based B-tree index phù hợp khi nào?

**Trả lời:** Khi có một scalar path ổn định được lọc thường xuyên bằng equality hoặc range.

**Câu 10.** Vì sao kiểu RETURNING cần nhất quán giữa index và query?

**Trả lời:** Vì biểu thức và kiểu dữ liệu phải phù hợp để optimizer nhận diện expression index và tránh chuyển đổi không mong muốn.

**Câu 11.** PASSING giúp gì?

**Trả lời:** Truyền bind value vào JSON path an toàn, không cần nối chuỗi đầu vào vào path.

**Câu 12.** Vì sao gộp hai điều kiện array vào cùng một filter?

**Trả lời:** Để bảo đảm cả hai điều kiện cùng khớp trên một phần tử array.

**Câu 13.** JSON null có giống SQL NULL không?

**Trả lời:** Không. JSON null là giá trị trong tài liệu; SQL NULL là trạng thái null của SQL expression. JSON_VALUE có thể ánh xạ JSON null thành SQL NULL.

**Câu 14.** JSON search index có luôn được dùng không?

**Trả lời:** Không. Optimizer quyết định theo query shape, khả năng hỗ trợ, statistics và cost.

**Câu 15.** Vì sao index làm DML tốn hơn?

**Trả lời:** Oracle phải duy trì key hoặc cấu trúc domain index khi JSON document được INSERT/UPDATE; search index còn có công việc sync.

**Câu 16.** Khi nào nên dùng JSON_TABLE thay cho JSON_EXISTS?

**Trả lời:** Khi cần lấy từng phần tử thành hàng để join, project, aggregate hoặc xử lý quan hệ.

**Câu 17.** Full table scan có luôn xấu không?

**Trả lời:** Không. Với bảng nhỏ hoặc truy vấn trả phần lớn hàng, full scan có thể rẻ hơn index lookup.

**Câu 18.** Tạo index rồi cần làm gì để xác nhận hiệu quả?

**Trả lời:** Thu thập statistics phù hợp, xem DBMS_XPLAN, đo actual rows/buffers/latency và kiểm tra chi phí DML.

## 22. Kết luận

Thiết kế chỉ mục JSON bắt đầu từ hình dạng predicate và giá trị mà truy vấn cần trả. `JSON_EXISTS` phù hợp để kiểm tra sự tồn tại hoặc điều kiện trên path, `JSON_VALUE` lấy scalar có kiểu, `JSON_QUERY` lấy object/array và `JSON_TABLE` biến tài liệu hoặc array thành hàng/cột quan hệ. Path expression cần dùng đúng tên field, array wildcard, filter và kiểu dữ liệu; `PASSING` là cách truyền giá trị động mà không nối chuỗi input vào path.

JSON search index là lựa chọn tổng quát cho nhiều path và truy vấn JSON linh hoạt. Function-based B-tree index phù hợp với một số scalar path ổn định cần equality hoặc range; virtual column giúp đặt tên và tái sử dụng expression, còn composite index có thể kết hợp tenant hoặc cột quan hệ. Với array, dùng JSON_EXISTS khi chỉ cần existence, JSON_TABLE khi cần xử lý từng phần tử; kiểm tra multivalue index theo đúng release nếu workload cần index hóa nhiều scalar value trong một array.

Mỗi index tăng storage và chi phí duy trì. Search index cần chính sách sync; B-tree cần expression và kiểu trả về khớp với query. Sau khi tạo index, thu thập statistics, xem `DBMS_XPLAN` và benchmark cả đọc lẫn ghi trên dữ liệu đại diện. Chỉ giữ những index giúp workload thực tế, không lập chỉ mục mọi field JSON theo thói quen.


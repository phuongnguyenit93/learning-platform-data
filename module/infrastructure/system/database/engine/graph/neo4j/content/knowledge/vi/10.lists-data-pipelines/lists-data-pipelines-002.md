# UNWIND trong Cypher: biến danh sách thành các hàng dữ liệu

## Mục tiêu bài học

Neo4j lưu dữ liệu theo mô hình **property graph**: node biểu diễn thực thể, relationship biểu diễn liên kết và property lưu thuộc tính. Khi truy vấn đồ thị bằng Cypher, dữ liệu đi qua các mệnh đề dưới dạng **luồng hàng**. Một hàng có thể chứa node, relationship, giá trị số, chuỗi, map hoặc danh sách.

Trong chương **Danh sách và luồng dữ liệu**, `UNWIND` giải quyết một nhu cầu rất thường gặp: **một biến đang chứa danh sách nhưng bước tiếp theo cần xử lý từng phần tử như một hàng riêng**. Kỹ thuật này xuất hiện ở truy vấn phân tích, chuyển đổi kết quả của `collect()`, nhập dữ liệu hàng loạt bằng Java Driver hoặc Spring Data Neo4j và tạo node/relationship từ dữ liệu ứng dụng.

Sau khi học, bạn có thể:

- Giải thích cú pháp `UNWIND <list-expression> AS <variable>` và tác động đến số hàng.
- Phân biệt danh sách rỗng, phần tử `null`, phần tử trùng lặp và danh sách lồng nhau.
- Phối hợp `UNWIND` với `WITH`, `WHERE`, `DISTINCT`, `collect()` và `ORDER BY`.
- Đọc, chuyển đổi danh sách map thành các dòng dữ liệu và nhập dữ liệu vào graph bằng `MERGE`.
- Nhận biết rủi ro nhân số hàng, thứ tự không được đảm bảo và chi phí của các danh sách lớn.

## 1. Bản chất của UNWIND

Cú pháp:

~~~cypher
UNWIND listExpression AS item
~~~

`listExpression` phải tạo ra một danh sách; `item` là tên biến mới cho **từng phần tử**. Với **mỗi hàng đầu vào**, `UNWIND` sinh một hàng đầu ra cho mỗi phần tử trong danh sách ở hàng đó. Các biến khác đang có trong hàng đầu vào vẫn được mang theo.

~~~text
Hàng đầu vào
customerId = 'C01'
skus       = ['P01', 'P02', 'P03']
        |
        | UNWIND skus AS sku
        v
Hàng 1: customerId = 'C01', sku = 'P01'
Hàng 2: customerId = 'C01', sku = 'P02'
Hàng 3: customerId = 'C01', sku = 'P03'
~~~

Ví dụ có thể chạy trực tiếp trên Neo4j mà không cần dữ liệu đồ thị có sẵn:

~~~cypher
WITH 'C01' AS customerId, ['P01', 'P02', 'P03'] AS skus
UNWIND skus AS sku
RETURN customerId, sku
ORDER BY sku;
~~~

Kết quả:

| customerId | sku |
| --- | --- |
| C01 | P01 |
| C01 | P02 |
| C01 | P03 |

Biến `skus` là cả danh sách; `sku` lần lượt nhận các giá trị bên trong. `UNWIND` **không tự chọn cột**, **không tự loại trùng** và **không bảo đảm thứ tự xuất hiện của các hàng**. `ORDER BY` ở ví dụ trên là lý do bảng kết quả được sắp xếp theo `sku`.

Một cách nhìn hữu ích:

| Mệnh đề | Chức năng chính | Tác động thường gặp đến số hàng |
| --- | --- | --- |
| `WITH` | Chuyển tiếp, đổi tên, lọc hoặc nhóm dữ liệu trung gian | Giữ nguyên, giảm hoặc gom các hàng tùy biểu thức |
| `collect(x)` | Gom nhiều giá trị thành danh sách trong mỗi nhóm | Giảm số hàng khi tổng hợp |
| `UNWIND xs AS x` | Mở một danh sách thành các hàng | Có thể tăng, giữ nguyên hoặc giảm về 0 hàng |
| `RETURN` | Xuất các hàng cuối của truy vấn | Trả các hàng/cột được chọn |

`UNWIND` không tương đương việc duyệt quan hệ trong đồ thị bằng `MATCH`. Nó xử lý một **giá trị danh sách**; các phần tử được mở ra có thể được dùng để `MATCH` hoặc `MERGE` node/relationship ở giai đoạn tiếp theo.

## 2. UNWIND danh sách giá trị đơn giản

### Mỗi phần tử trở thành một hàng

~~~cypher
UNWIND [5, 10, 15] AS quantity
RETURN quantity, quantity * 2 AS doubleQuantity
ORDER BY quantity;
~~~

Truy vấn có ba hàng đầu ra với `quantity` lần lượt là 5, 10 và 15; cột `doubleQuantity` là 10, 20 và 30. Phép tính được thực hiện trên **giá trị của mỗi hàng**, không phải trên cả danh sách một lần.

### UNWIND giữ các giá trị trùng nhau

~~~cypher
UNWIND ['P01', 'P02', 'P01'] AS sku
RETURN sku
ORDER BY sku;
~~~

Kết quả có **ba hàng**, trong đó `P01` xuất hiện hai lần. Nếu yêu cầu một hàng cho mỗi SKU duy nhất:

~~~cypher
UNWIND ['P01', 'P02', 'P01'] AS sku
WITH DISTINCT sku
RETURN sku
ORDER BY sku;
~~~

Kết quả chỉ gồm `P01` và `P02`. `DISTINCT` là thao tác loại trùng có chủ đích; `UNWIND` không thực hiện việc đó mặc định.

### Danh sách rỗng và null

Những trường hợp sau tác động trực tiếp đến luồng hàng:

| Biểu thức được mở | Số hàng tạo ra | Diễn giải |
| --- | ---: | --- |
| `[1, 2, 3]` | 3 | Một hàng cho mỗi phần tử |
| `[]` | 0 | Không có phần tử nên không phát sinh hàng |
| `[null]` | 1 | Một hàng có giá trị `null` |
| `[1, null, 1]` | 3 | Giữ cả phần tử `null` và hai giá trị 1 |

Ví dụ:

~~~cypher
UNWIND [1, null, 1, 2] AS n
RETURN
  count(*) AS numberOfRows,
  count(n) AS nonNullValues,
  count(DISTINCT n) AS distinctNonNullValues;
~~~

Kết quả là `numberOfRows = 4`, `nonNullValues = 3`, `distinctNonNullValues = 2`. `count(*)` đếm hàng; `count(n)` bỏ qua giá trị `null`.

Một danh sách rỗng **làm dừng luồng hàng ở nhánh truy vấn đó**:

~~~cypher
WITH 'C01' AS customerId, [] AS tags
UNWIND tags AS tag
RETURN customerId, tag;
~~~

Truy vấn trả **0 hàng**, dù `customerId` tồn tại trước `UNWIND`. Đây là nguyên nhân phổ biến khiến dữ liệu “biến mất” trong pipeline khi trường danh sách có thể rỗng.

Nếu biểu thức danh sách có thể là `null` (chẳng hạn property chưa tồn tại), hãy dùng `coalesce(..., [])` để mặc định thành danh sách rỗng:

~~~cypher
WITH {id: 'C01', tags: null} AS record
UNWIND coalesce(record.tags, []) AS tag
RETURN record.id AS customerId, tag;
~~~

Kết quả là 0 hàng, có chủ đích, và không phải cố mở trực tiếp một giá trị không phải danh sách. Khi nghiệp vụ yêu cầu giữ bản ghi gốc dù không có phần tử, cần thiết kế cách xử lý riêng (ví dụ xử lý các trường không có phần tử ở nhánh khác); `UNWIND []` tự nó không giữ hàng.

## 3. Mở danh sách các map

Dữ liệu từ REST API, JSON hoặc chương trình Java thường được biểu diễn dưới dạng danh sách object. Trong Cypher, mỗi object tương ứng với một **map** có các khóa và giá trị.

~~~cypher
UNWIND [
  {sku: 'P01', name: 'Sách Neo4j', price: 120000},
  {sku: 'P02', name: 'Sách Cypher', price: 90000},
  {sku: 'P03', name: 'Sách Graph', price: 150000}
] AS product
RETURN
  product.sku AS sku,
  product.name AS productName,
  product.price AS price
ORDER BY sku;
~~~

Mỗi `product` là một map; có thể truy cập các khóa bằng `product.sku`, `product.name` và `product.price`. Kết quả gồm ba hàng:

| sku | productName | price |
| --- | --- | ---: |
| P01 | Sách Neo4j | 120000 |
| P02 | Sách Cypher | 90000 |
| P03 | Sách Graph | 150000 |

Lọc các hàng ngay sau khi mở danh sách:

~~~cypher
UNWIND [
  {sku: 'P01', price: 120000},
  {sku: 'P02', price: 90000},
  {sku: 'P03', price: 150000}
] AS product
WITH product
WHERE product.price >= 100000
RETURN product.sku AS sku, product.price AS price
ORDER BY price DESC;
~~~

Ở đây `WITH product WHERE ...` lọc hàng có giá từ 100.000; kết quả gồm `P03` và `P01`. Trong Cypher, `WHERE` được gắn với mệnh đề thích hợp như `MATCH` hoặc `WITH`; khi lọc ngay sau `UNWIND`, dùng `WITH ... WHERE ...` như ví dụ này.

## 4. Danh sách lồng nhau: một UNWIND mở một cấp

Nếu phần tử của danh sách cũng là danh sách, một `UNWIND` chỉ mở **cấp ngoài**:

~~~cypher
UNWIND [[1, 2], [], [3, 4]] AS numbers
RETURN numbers;
~~~

Ba hàng đầu ra có giá trị `numbers` lần lượt là `[1, 2]`, `[]` và `[3, 4]` (không giả định thứ tự khi thiếu `ORDER BY`). Muốn lấy từng số, mở thêm một lần:

~~~cypher
UNWIND [[1, 2], [], [3, 4]] AS numbers
UNWIND numbers AS n
RETURN n
ORDER BY n;
~~~

Kết quả có bốn hàng: `1`, `2`, `3`, `4`. Danh sách con rỗng không sinh hàng ở lần mở thứ hai.

### Ví dụ với các dòng sản phẩm của đơn hàng

Giả sử ứng dụng gửi danh sách đơn, mỗi đơn có danh sách `items`:

~~~cypher
UNWIND [
  {
    orderId: 'O01',
    items: [
      {sku: 'P01', quantity: 2},
      {sku: 'P02', quantity: 1}
    ]
  },
  {
    orderId: 'O02',
    items: [{sku: 'P02', quantity: 3}]
  },
  {
    orderId: 'O03',
    items: []
  }
] AS orderData
UNWIND orderData.items AS item
RETURN
  orderData.orderId AS orderId,
  item.sku AS sku,
  item.quantity AS quantity
ORDER BY orderId, sku;
~~~

| orderId | sku | quantity |
| --- | --- | ---: |
| O01 | P01 | 2 |
| O01 | P02 | 1 |
| O02 | P02 | 3 |

`O03` không có hàng vì `items` rỗng. Hai lần `UNWIND` tạo ra quan hệ **một đơn → nhiều dòng sản phẩm** trên luồng dữ liệu, nhưng chưa tạo node hoặc relationship trong đồ thị.

**Cẩn thận với nhân hàng ngoài ý muốn.** Ví dụ hai danh sách độc lập:

~~~cypher
WITH ['C01', 'C02'] AS customerIds, ['P01', 'P02'] AS skus
UNWIND customerIds AS customerId
UNWIND skus AS sku
RETURN customerId, sku
ORDER BY customerId, sku;
~~~

Kết quả có **4 tổ hợp** (2 × 2). Đây là tích Descartes của hai danh sách theo mỗi hàng đầu vào, **không phải** ghép `C01` với `P01` và `C02` với `P02` theo vị trí. Nếu nghiệp vụ yêu cầu các cặp tương ứng, hãy gửi dữ liệu theo danh sách map như `[{customerId: 'C01', sku: 'P01'}, ...]` rồi `UNWIND` một lần.

## 5. Phối hợp WITH, collect và UNWIND trong pipeline

`WITH` tổ chức bước trung gian; `collect()` gom giá trị thành danh sách; `UNWIND` biến phần tử danh sách trở lại thành hàng.

~~~text
Nhiều hàng                Một hàng theo mỗi nhóm             Nhiều hàng
id | sku                  id  | skus                           id | sku
C01| P01    --collect-->  C01 | [P01, P02]  --UNWIND-->      C01| P01
C01| P02                                                    C01| P02
~~~

Có thể minh họa bằng dữ liệu có sẵn ngay trong truy vấn:

~~~cypher
UNWIND [
  {customerId: 'C01', sku: 'P01'},
  {customerId: 'C01', sku: 'P02'},
  {customerId: 'C02', sku: 'P02'}
] AS row
WITH row.customerId AS customerId, collect(row.sku) AS skus
UNWIND skus AS sku
RETURN customerId, sku
ORDER BY customerId, sku;
~~~

`WITH` gom theo `customerId`; `UNWIND` tiếp tục xử lý từng SKU. Ví dụ này cố tình quay lại số hàng ban đầu để minh họa sự chuyển đổi. Trong ứng dụng, chỉ sử dụng `collect()` rồi `UNWIND` khi cần thực hiện một phép xử lý trên danh sách ở giữa; nếu không có phép xử lý như vậy, giữ nguyên các hàng thường đơn giản và tiết kiệm hơn.

### Giữ hoặc khử trùng lặp

Giả sử ứng dụng gửi một danh sách có thể chứa mã trùng:

~~~cypher
UNWIND ['P02', 'P01', 'P02', 'P03'] AS sku
WITH DISTINCT sku
RETURN collect(sku) AS uniqueSkus;
~~~

`DISTINCT` giảm số hàng còn ba SKU khác nhau, sau đó `collect()` tạo danh sách. **Không dựa vào thứ tự trong `uniqueSkus`** khi không có `ORDER BY`.

Muốn danh sách trả về theo thứ tự mã tăng dần:

~~~cypher
UNWIND ['P02', 'P01', 'P02', 'P03'] AS sku
WITH DISTINCT sku
ORDER BY sku
RETURN collect(sku) AS uniqueSkus;
~~~

Kết quả là `['P01', 'P02', 'P03']`. `ORDER BY` trong `WITH` sắp xếp luồng hàng trước mệnh đề ngay sau thực hiện `collect()`.

### Quy tắc về thứ tự

Neo4j **không bảo đảm** `UNWIND` giữ nguyên thứ tự phần tử của danh sách đầu vào. Khi thứ tự có ý nghĩa (xếp hạng, phân trang, kết quả báo cáo), cần sắp xếp rõ bằng `ORDER BY`. Nếu phải giữ **vị trí gốc** của từng phần tử, hãy truyền kèm chỉ số trong dữ liệu đầu vào, ví dụ `[{position: 0, value: 'P02'}, {position: 1, value: 'P01'}]`, rồi sắp xếp theo `position`.

## 6. UNWIND trong nhập dữ liệu property graph

Một tình huống tiêu biểu của `DATABASE_ENGINE_GRAPH_NEO4J` là nhận danh sách bản ghi từ Java Driver hoặc Spring Data Neo4j rồi biến chúng thành node/relationship. **Nên truyền cả danh sách qua tham số truy vấn**, thay vì nối chuỗi Cypher từ các giá trị bên ngoài.

Giả sử tham số `$products` được ứng dụng truyền vào với dữ liệu tương đương:

~~~json
[
  {"sku": "P01", "name": "Sách Neo4j", "price": 120000},
  {"sku": "P02", "name": "Sách Cypher", "price": 90000}
]
~~~

Tạo hoặc cập nhật sản phẩm bằng một truy vấn:

~~~cypher
UNWIND $products AS raw
WITH
  trim(raw.sku) AS sku,
  raw.name AS productName,
  raw.price AS price
WHERE sku IS NOT NULL AND sku <> ''
MERGE (p:Product {sku: sku})
SET p.name = productName,
    p.price = price
RETURN count(p) AS processedRows;
~~~

Giải thích:

1. `UNWIND $products AS raw` tạo một hàng cho mỗi map đầu vào.
2. `WITH` lấy và chuẩn hóa các trường cần thiết; `WHERE` loại SKU rỗng hoặc thiếu.
3. `MERGE` tìm hoặc tạo node `Product` theo `sku`.
4. `SET` cập nhật các property; `count(p)` đếm số hàng đã xử lý, **không nhất thiết là số node mới được tạo hoặc số node duy nhất** khi đầu vào trùng SKU.

Để bảo vệ tính duy nhất của `Product.sku`, có thể tạo constraint riêng cho database trước khi nhập:

~~~cypher
CREATE CONSTRAINT product_sku_unique IF NOT EXISTS
FOR (p:Product) REQUIRE p.sku IS UNIQUE;
~~~

Constraint giúp Neo4j thực thi tính duy nhất, đặc biệt khi nhiều transaction ghi đồng thời. `MERGE` không tự tạo constraint. Với đầu vào chứa nhiều bản ghi trùng `sku` nhưng khác `name` hoặc `price`, kết quả cập nhật có thể phụ thuộc thứ tự xử lý; ứng dụng nên xác định quy tắc xử lý xung đột và khử trùng lặp trước khi ghi.

### Tạo quan hệ từ danh sách đơn hàng lồng nhau

Giả sử `$orders` là danh sách map, mỗi phần tử có `customerId`, `orderId` và danh sách `items`:

~~~json
[
  {
    "customerId": "C01",
    "orderId": "O01",
    "items": [
      {"sku": "P01", "quantity": 2},
      {"sku": "P02", "quantity": 1}
    ]
  },
  {
    "customerId": "C02",
    "orderId": "O02",
    "items": [{"sku": "P02", "quantity": 3}]
  }
]
~~~

Mô hình đích:

~~~text
(:Customer {id})
       |
       +--[:PLACED]--> (:Order {id})
                              |
                              +--[:CONTAINS {quantity}]--> (:Product {sku})
~~~

Truy vấn:

~~~cypher
UNWIND $orders AS rawOrder
WITH
  trim(rawOrder.customerId) AS customerId,
  trim(rawOrder.orderId) AS orderId,
  rawOrder.items AS items
WHERE
  customerId IS NOT NULL AND customerId <> ''
  AND orderId IS NOT NULL AND orderId <> ''
MERGE (c:Customer {id: customerId})
MERGE (o:Order {id: orderId})
MERGE (c)-[:PLACED]->(o)
WITH o, items
UNWIND coalesce(items, []) AS rawItem
WITH
  o,
  trim(rawItem.sku) AS sku,
  rawItem.quantity AS quantity
WHERE
  sku IS NOT NULL AND sku <> ''
  AND quantity IS NOT NULL AND quantity > 0
MERGE (p:Product {sku: sku})
MERGE (o)-[line:CONTAINS]->(p)
SET line.quantity = quantity;
~~~

Các bước này tạo hoặc tìm `Customer` và `Order` trước, rồi mở `items` để tạo hoặc tìm `Product` và quan hệ `CONTAINS`. Nếu `items` rỗng hoặc `null`, các hàng sẽ không đi tiếp sau `UNWIND`; phần tạo khách hàng/đơn hàng nằm ở phía trước. Truy vấn trên giả định mỗi cặp **đơn–sản phẩm** chỉ có một quan hệ `CONTAINS` và `quantity` đã được ứng dụng xác thực là số dương. Nếu một đơn có nhiều dòng cùng SKU, cần xác định việc cộng dồn số lượng thay vì tùy ý ghi đè.

Trong ứng dụng Java, hãy gửi `$products` hoặc `$orders` dưới dạng **query parameters** của Neo4j Java Driver, hoặc tham số của câu truy vấn tùy chỉnh trong Spring Data Neo4j. Không cần dựng một câu lệnh `CREATE` hay `MERGE` riêng cho từng phần tử. Với nhập liệu quy mô lớn, chia dữ liệu thành các lô hợp lý và quản lý transaction phù hợp với giới hạn bộ nhớ, thời gian và tính nhất quán của hệ thống.

## 7. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Không có kết quả sau `UNWIND` | Danh sách ở hàng đầu vào rỗng | Kiểm tra `size(list)` trước khi mở; thiết kế riêng trường hợp không có phần tử |
| Một bản ghi đầu vào xuất hiện nhiều lần | `UNWIND` sinh một hàng cho mỗi phần tử, hoặc hai `UNWIND` độc lập tạo tích số hàng | Kiểm tra ý nghĩa mỗi hàng; dùng danh sách map để giữ các cặp tương ứng |
| Kết quả lặp SKU | Đầu vào có phần tử trùng; `UNWIND` giữ nguyên | Dùng `WITH DISTINCT` khi muốn một giá trị duy nhất |
| Thiếu các phần tử `null` trong kết quả tổng hợp | `count(x)` và `collect(x)` bỏ qua `null` | Dùng `count(*)` nếu muốn đếm số hàng; xử lý `null` trước `collect()` khi cần |
| Kết quả không theo thứ tự đầu vào | `UNWIND` không bảo đảm thứ tự | Thêm `ORDER BY`; mang chỉ số gốc nếu cần |
| `MERGE` báo lỗi property `null` hoặc sai kiểu | Bản ghi thiếu ID hoặc trường nhập sai kiểu | Chuẩn hóa, xác thực và lọc giá trị trước `MERGE` |
| Import chậm, dùng nhiều bộ nhớ | Danh sách quá lớn, nhiều thao tác `MERGE` hoặc dữ liệu bị nhân hàng | Đo bằng `PROFILE` trên dữ liệu thử, chia lô, thêm constraint/index phù hợp |

Một số nguyên tắc để triển khai hiệu quả:

- **Kiểm soát số hàng:** với `N` hàng đầu vào và mỗi hàng có `kᵢ` phần tử, `UNWIND` tạo tổng cộng `k₁ + k₂ + ... + kₙ` hàng; danh sách rỗng góp 0 hàng.
- **Giảm dữ liệu không cần thiết:** lọc, chuẩn hóa và khử trùng lặp ở đúng vị trí trong pipeline. Tuy nhiên, loại trùng chỉ khi nghiệp vụ cho phép, đặc biệt với dữ liệu đơn hàng.
- **Kiểm soát dữ liệu nhập:** tạo uniqueness constraint cho các khóa nghiệp vụ như `Customer.id`, `Order.id`, `Product.sku`; xác định cách xử lý trường trùng hoặc thiếu dữ liệu trước khi ghi.
- **Quan sát kế hoạch:** `EXPLAIN` cho biết kế hoạch truy vấn; `PROFILE` cho biết số hàng thực tế đi qua các toán tử trên dữ liệu thử. Tránh chạy truy vấn ghi với `PROFILE` ngoài ý muốn trong môi trường quan trọng, vì `PROFILE` thực thi truy vấn.

## 8. Bài thực hành

**Bài 1 — Chuyển danh sách điểm thành hàng.** Cho danh sách `[7, 9, 7, null, 10]`. Hãy trả về các điểm **duy nhất**, khác `null`, sắp xếp tăng dần.

Gợi ý:

~~~cypher
UNWIND [7, 9, 7, null, 10] AS score
WITH DISTINCT score
WHERE score IS NOT NULL
RETURN score
ORDER BY score;
~~~

Kết quả kỳ vọng: ba hàng có `score = 7`, `9` và `10`.

**Bài 2 — Tính tổng tiền từ danh sách dòng hàng.** Mỗi dòng gồm `sku`, `quantity` và `unitPrice`. Hãy mở danh sách thành hàng, tính `lineTotal` cho từng dòng, rồi tính tổng giá trị đơn hàng.

~~~cypher
UNWIND [
  {sku: 'P01', quantity: 2, unitPrice: 120000},
  {sku: 'P02', quantity: 1, unitPrice: 90000}
] AS item
WITH
  item.sku AS sku,
  item.quantity * item.unitPrice AS lineTotal
RETURN
  collect({sku: sku, lineTotal: lineTotal}) AS lines,
  sum(lineTotal) AS orderTotal;
~~~

Kết quả kỳ vọng: `orderTotal = 330000`, danh sách `lines` có hai map với `lineTotal` lần lượt là `240000` và `90000` (không giả định thứ tự phần tử nếu chưa sắp xếp).

**Tự kiểm tra:** Nếu `items = []`, một `UNWIND items AS item` sẽ tạo bao nhiêu hàng? Nếu `items = [null]` thì sao? Đáp án: `[]` tạo **0 hàng**; `[null]` tạo **1 hàng** với `item = null`. Hai trường hợp này có tác động khác nhau đến `count(*)` và các bước sau.

## Ghi nhớ

`UNWIND` là mệnh đề **mở danh sách thành các hàng** trong Cypher: mỗi phần tử sinh một hàng, danh sách rỗng sinh không hàng, giá trị trùng vẫn được giữ và thứ tự chỉ được đảm bảo khi sắp xếp rõ. Kết hợp `UNWIND` với `WITH`, `collect()` và `MERGE` giúp xây dựng pipeline chuyển đổi dữ liệu và nhập node/relationship cho Neo4j một cách rõ ràng, nhất là khi ứng dụng Java truyền dữ liệu theo danh sách map.

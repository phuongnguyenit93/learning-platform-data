# Biểu thức tạo danh sách và phép lọc phần tử trong Cypher

## Mục tiêu bài học

Trong Neo4j, dữ liệu được biểu diễn bằng **property graph** gồm node, relationship và property. Ngoài việc tìm quan hệ hoặc đường đi trong đồ thị, truy vấn Cypher thường cần xử lý **list** (danh sách): các mã sản phẩm nhận từ ứng dụng Java, các đơn hàng đã gom bằng `collect()`, hoặc các node trên một đường đi do `nodes(path)` trả về.

Ở chương **Danh sách và luồng dữ liệu** của module `DATABASE_ENGINE_GRAPH_NEO4J`, bài này tập trung vào **biểu thức tạo danh sách** và **phép lọc phần tử**. Công cụ chính là *list comprehension*: tạo một danh sách mới bằng cách duyệt, lọc và biến đổi các phần tử của danh sách đầu vào ngay trong biểu thức Cypher.

Sau bài học, bạn có thể:

- Viết list literal và tạo danh sách bằng `range()`, `collect()` hoặc list comprehension.
- Sử dụng cú pháp `[x IN xs WHERE điều_kiện | biểu_thức]` để lọc và biến đổi phần tử.
- Phân biệt **lọc phần tử trong một list** với **lọc hàng trong pipeline** bằng `WITH ... WHERE`.
- Xử lý danh sách rỗng, giá trị `null`, phần tử trùng và thứ tự phần tử.
- Ứng dụng các biểu thức vào danh sách map, node, đường đi Neo4j và tham số truyền từ Java Driver/Spring Data Neo4j.

## 1. Một danh sách trong Cypher là gì?

Danh sách là một giá trị có thứ tự, chứa không, một hoặc nhiều phần tử. Truy vấn sau tạo ba loại danh sách mà không cần dữ liệu graph có sẵn:

~~~cypher
RETURN
  ['Neo4j', 'Cypher', 'Java'] AS technologies,
  [100, 200, 300] AS prices,
  [{sku: 'P01', price: 100000}, {sku: 'P02', price: 50000}] AS products;
~~~

Các phần tử có thể là giá trị đơn giản như số và chuỗi, hoặc giá trị phức hợp như map. Một list được tạo trong lúc truy vấn còn có thể chứa node hoặc relationship. Tuy nhiên, **không phải mọi danh sách đều có thể lưu nguyên dạng làm property** của node/relationship: property Neo4j chỉ hỗ trợ những kiểu giá trị cho phép lưu trữ, không lưu danh sách map hoặc node tùy ý.

Những nguồn tạo list thường gặp:

| Nguồn | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **List literal** | `['P01', 'P02']` | Khai báo trực tiếp các phần tử |
| **Dãy số** | `range(1, 5)` | Sinh `[1, 2, 3, 4, 5]` |
| **Hàm tổng hợp** | `collect(o.id)` | Gom giá trị từ nhiều hàng thành list |
| **Hàm cho đường đi** | `nodes(p)`, `relationships(p)` | Lấy danh sách node hoặc relationship trên path |
| **Tham số ứng dụng** | `$products`, `$customerIds` | Nhận danh sách qua query parameters |
| **List comprehension** | `[x IN xs | x * 2]` | Sinh list mới từ list có sẵn |

Chẳng hạn, `size(xs)` cho biết độ dài một list:

~~~cypher
WITH ['P01', 'P02', 'P03'] AS skus
RETURN size(skus) AS numberOfSkus, skus[0] AS firstSku;
~~~

Kết quả là `numberOfSkus = 3` và `firstSku = 'P01'`. Truy cập phần tử bằng `xs[index]` dùng chỉ số bắt đầu từ 0; nội dung chính của bài này là **tạo danh sách mới từ các phần tử**, thay vì chọn một vị trí cụ thể.

## 2. Cú pháp list comprehension: duyệt, lọc và biến đổi

List comprehension có dạng tổng quát:

~~~cypher
[item IN sourceList WHERE condition | expression]
~~~

Trong đó:

- `item` là biến đại diện cho **từng phần tử** của `sourceList`.
- `WHERE condition` là phần **tùy chọn**, chỉ giữ phần tử khi biểu thức điều kiện là `true`.
- `| expression` cũng là phần **tùy chọn**, quyết định giá trị phần tử tương ứng trong list kết quả.
- Nếu không có phần `| expression`, phần tử thỏa điều kiện được giữ **nguyên giá trị**.

Ba hình thức cần ghi nhớ:

~~~cypher
WITH [1, 2, 3, 4, 5] AS numbers
RETURN
  [n IN numbers | n * 10] AS multiplied,
  [n IN numbers WHERE n % 2 = 0] AS evenNumbers,
  [n IN numbers WHERE n % 2 = 0 | n * n] AS evenSquares;
~~~

| Biểu thức | Kết quả | Tác dụng |
| --- | --- | --- |
| `[n IN numbers \| n * 10]` | `[10, 20, 30, 40, 50]` | Biến đổi tất cả phần tử |
| `[n IN numbers WHERE n % 2 = 0]` | `[2, 4]` | Chỉ lọc, giữ giá trị gốc |
| `[n IN numbers WHERE n % 2 = 0 \| n * n]` | `[4, 16]` | Lọc trước rồi biến đổi |

Với phép lọc, mỗi phần tử được xét bằng điều kiện riêng. Phần tử không đạt bị bỏ khỏi danh sách mới; **danh sách gốc không bị sửa đổi**.

### Vì sao kết quả vẫn là một list?

~~~cypher
WITH [2, 5, 8, 11] AS numbers
RETURN [n IN numbers WHERE n > 5 | n + 1] AS transformed;
~~~

Truy vấn này trả **một hàng** có cột `transformed = [9, 12]`. Hai phần tử trong list không đồng nghĩa với hai hàng Cypher.

Hãy phân biệt:

~~~text
Danh sách đầu vào:       [2, 5, 8, 11]
                              |
            WHERE n > 5, sau đó n + 1
                              |
List comprehension:           [9, 12]      (một giá trị list)
                              |
                      UNWIND ... AS n
                              |
Các hàng kết quả:              9
                               12          (hai hàng)
~~~

`UNWIND` mở list thành hàng khi giai đoạn tiếp theo cần xử lý từng phần tử như một bản ghi riêng.

## 3. Những cách tạo danh sách mới

### Tạo list từ dãy số bằng `range()`

`range(start, end[, step])` tạo một list các số nguyên. Điểm kết thúc được tính vào dãy nếu bước nhảy đi tới nó:

~~~cypher
WITH range(1, 6) AS numbers
RETURN
  numbers AS original,
  [n IN numbers | n * n] AS squares,
  [n IN numbers WHERE n % 3 = 0 | n * 10] AS multiplesOfThreeTimesTen;
~~~

Kết quả:

- `original = [1, 2, 3, 4, 5, 6]`;
- `squares = [1, 4, 9, 16, 25, 36]`;
- `multiplesOfThreeTimesTen = [30, 60]`.

Trường hợp `range()` sinh list lớn có thể tạo ra nhiều phần tử trung gian, nên cần giới hạn phạm vi và bước nhảy theo yêu cầu thực tế.

### Biến đổi chuỗi và chuẩn hóa giá trị

Với các mã sản phẩm được nhập bằng những cách viết khác nhau:

~~~cypher
WITH [' p01 ', 'P02', ' p03'] AS rawSkus
RETURN [sku IN rawSkus | toUpper(trim(sku))] AS normalizedSkus;
~~~

Kết quả: `['P01', 'P02', 'P03']`. Mỗi phần tử được `trim()` để loại khoảng trắng ở hai đầu, rồi `toUpper()` để viết hoa. Nếu trong dữ liệu có các phần tử `null`, nên xác định quy tắc xử lý trước khi chuẩn hóa.

### Tạo list mới gồm các map

Một phép biến đổi có thể xuất ra **map** thay vì số hoặc chuỗi:

~~~cypher
WITH [
  {sku: 'P01', price: 100000},
  {sku: 'P02', price: 50000}
] AS products
RETURN [
  p IN products
  | {productCode: p.sku, priceWithTax: p.price * 1.1}
] AS priceSummary;
~~~

Kết quả có một list gồm hai map:

~~~text
[
  {productCode: 'P01', priceWithTax: 110000.0},
  {productCode: 'P02', priceWithTax: 55000.0}
]
~~~

Đây là các **map được tạo trong kết quả truy vấn**; ví dụ không tạo node hoặc cập nhật property trong graph. `priceWithTax` chỉ là phép tính minh họa, không phải công thức thuế áp dụng cho mọi nghiệp vụ.

## 4. Lọc phần tử theo điều kiện

### Lọc số, chuỗi và map

Với list số:

~~~cypher
WITH [12, 3, 25, 8, 17] AS quantities
RETURN [q IN quantities WHERE q >= 10] AS largeQuantities;
~~~

Kết quả: `[12, 25, 17]`. Thứ tự của các phần tử được giữ theo list đầu vào.

Với list map gồm các đơn hàng:

~~~cypher
WITH [
  {id: 'O01', status: 'PAID', amount: 250000},
  {id: 'O02', status: 'PENDING', amount: 600000},
  {id: 'O03', status: 'PAID', amount: 750000}
] AS orders
RETURN
  [o IN orders WHERE o.status = 'PAID' | o.id] AS paidOrderIds,
  [o IN orders WHERE o.status = 'PAID' AND o.amount >= 500000
    | {id: o.id, amount: o.amount}] AS largePaidOrders;
~~~

Kết quả:

| Cột | Giá trị |
| --- | --- |
| `paidOrderIds` | `['O01', 'O03']` |
| `largePaidOrders` | `[{id: 'O03', amount: 750000}]` |

`WHERE` trong comprehension được đánh giá trên **mỗi map** `o`. Chỉ những map thỏa điều kiện mới được biến đổi thành kết quả. Bạn có thể kết hợp `AND`, `OR`, các phép so sánh và các hàm Cypher trong điều kiện này.

### Kiểm tra một giá trị có thuộc nhóm cho phép

Toán tử `IN` kiểm tra một giá trị có xuất hiện trong danh sách hay không:

~~~cypher
WITH
  ['PAID', 'SHIPPED'] AS acceptedStatuses,
  [
    {id: 'O01', status: 'PAID'},
    {id: 'O02', status: 'CANCELLED'},
    {id: 'O03', status: 'SHIPPED'}
  ] AS orders
RETURN [
  o IN orders
  WHERE o.status IN acceptedStatuses
  | o.id
] AS acceptedOrderIds;
~~~

Kết quả là `['O01', 'O03']`. Hai cách dùng từ khóa `IN` không được nhầm với nhau:

- `o IN orders`: biến lặp `o` lần lượt nhận từng phần tử trong comprehension.
- `o.status IN acceptedStatuses`: biểu thức kiểm tra trạng thái có thuộc danh sách cho phép.

### Kết hợp lọc và đếm

Một list đã lọc vẫn có thể được truyền cho `size()`:

~~~cypher
WITH [4, 10, 2, 15, 11] AS values
RETURN size([x IN values WHERE x >= 10]) AS numberOfMatchingValues;
~~~

Kết quả là `3`. Đây là số phần tử thỏa điều kiện trong **một list**, không phải số hàng đầu ra. Khi đếm số hàng của một truy vấn đồ thị, có thể dùng `count(*)` hoặc `count(expression)` theo đúng ý nghĩa cần đo.

## 5. Danh sách rỗng, null và phần tử trùng

Các trường hợp biên cần được xử lý rõ vì ảnh hưởng tới kết quả hoặc logic nhập dữ liệu.

### List rỗng cho ra list rỗng

~~~cypher
WITH [] AS numbers
RETURN
  [n IN numbers WHERE n > 0 | n * 2] AS positiveDoubles,
  size(numbers) AS inputSize;
~~~

Kết quả: `positiveDoubles = []`, `inputSize = 0`. Một list rỗng không sinh ra phần tử mới sau comprehension.

### Giá trị null trong list

~~~cypher
WITH [1, null, 3] AS values
RETURN
  [x IN values | x * 2] AS mapped,
  [x IN values WHERE x > 1] AS greaterThanOne,
  [x IN values WHERE x IS NOT NULL | x * 2] AS nonNullDoubles;
~~~

| Cột | Kết quả |
| --- | --- |
| `mapped` | `[2, null, 6]` |
| `greaterThanOne` | `[3]` |
| `nonNullDoubles` | `[2, 6]` |

Biểu thức biến đổi `null * 2` có kết quả là `null`. Trong điều kiện `x > 1`, khi `x = null` thì kết quả không phải `true`, nên phần tử đó **không được giữ lại**. `IS NOT NULL` giúp thể hiện rõ yêu cầu loại phần tử thiếu dữ liệu.

Nếu **cả list đầu vào** bằng `null`, comprehension cũng trả `null`, khác với list rỗng trả `[]`:

~~~cypher
WITH null AS incomingTags
RETURN
  [tag IN incomingTags | tag] AS directResult,
  [tag IN coalesce(incomingTags, []) | tag] AS emptyByDefault;
~~~

Kết quả: `directResult = null` và `emptyByDefault = []`. Với dữ liệu tùy chọn đến từ ứng dụng, `coalesce(list, [])` là cách phổ biến để xác định quy tắc mặc định.

### List comprehension không khử trùng lặp

~~~cypher
WITH ['P01', 'P02', 'P01'] AS skus
RETURN [sku IN skus WHERE sku STARTS WITH 'P'] AS result;
~~~

Kết quả vẫn là `['P01', 'P02', 'P01']`. Nếu nghiệp vụ đòi hỏi SKU duy nhất, hãy thực hiện loại trùng bằng `DISTINCT` ở mức **hàng** rồi `collect()`:

~~~cypher
WITH ['P01', 'P02', 'P01'] AS skus
UNWIND skus AS sku
WITH DISTINCT sku
ORDER BY sku
RETURN collect(sku) AS uniqueSkus;
~~~

Kết quả: `['P01', 'P02']`. `ORDER BY` trước `collect()` làm thứ tự list đầu ra có thể dự đoán. Có thể cân nhắc trùng lặp ngay từ tầng nhập dữ liệu nếu các phần tử có thông tin bổ sung như số lượng hoặc thời gian cập nhật.

## 6. Phân biệt lọc phần tử trong list và lọc hàng Cypher

Trong pipeline Cypher, mệnh đề `WITH` chuyển các biến qua những giai đoạn kế tiếp; `WITH ... WHERE` lọc **hàng**. Trong list comprehension, `WHERE` lọc **phần tử thuộc list trong một hàng**. Kết quả của hai cách có thể tương đương về các giá trị, nhưng có cấu trúc khác nhau.

### Cách A: Giữ một hàng, trả danh sách các ID

~~~cypher
WITH [
  {id: 'O01', status: 'PAID'},
  {id: 'O02', status: 'PENDING'},
  {id: 'O03', status: 'PAID'}
] AS orders
RETURN
  [o IN orders WHERE o.status = 'PAID' | o.id] AS paidOrderIds,
  size(orders) AS originalOrderCount;
~~~

Trả về **một hàng**:

~~~text
paidOrderIds   = ['O01', 'O03']
originalOrderCount = 3
~~~

### Cách B: Mở list, lọc rồi trả từng hàng

~~~cypher
WITH [
  {id: 'O01', status: 'PAID'},
  {id: 'O02', status: 'PENDING'},
  {id: 'O03', status: 'PAID'}
] AS orders
UNWIND orders AS o
WITH o
WHERE o.status = 'PAID'
RETURN o.id AS paidOrderId
ORDER BY paidOrderId;
~~~

Trả về **hai hàng**, một hàng cho `O01` và một hàng cho `O03`.

| Tiêu chí | List comprehension | `UNWIND` + `WITH ... WHERE` |
| --- | --- | --- |
| Dữ liệu sau lọc | Một **giá trị list** trên mỗi hàng đầu vào | Các **hàng kết quả** tương ứng với phần tử còn lại |
| Số hàng ở bước hiện tại | Không đổi do chính comprehension | Có thể tăng, giảm hoặc về 0 |
| Tiếp tục tìm node/relationship bằng từng ID | Cần `UNWIND` nếu muốn xử lý từng ID như hàng | Có thể `MATCH`/`MERGE` trực tiếp theo biến mỗi hàng |
| Trả JSON-like list cho ứng dụng | Phù hợp | Cần `collect()` nếu muốn gom lại |

Hãy chọn list comprehension khi muốn **giữ kết quả dưới dạng list** để trả cho client hoặc làm phép tính tiếp theo. Chọn `UNWIND` khi muốn **mỗi phần tử là một hàng** phục vụ `MATCH`, `MERGE`, tổng hợp hoặc xử lý riêng.

## 7. Kiểm tra điều kiện trên toàn danh sách

Ngoài việc tạo một list mới, Cypher hỗ trợ các *list predicate functions* để đặt câu hỏi về các phần tử. Chúng trả về **giá trị logic** thay vì list.

~~~cypher
WITH [2, 4, 6] AS numbers
RETURN
  all(n IN numbers WHERE n % 2 = 0) AS allEven,
  any(n IN numbers WHERE n > 5) AS anyGreaterThanFive,
  none(n IN numbers WHERE n < 0) AS noneNegative,
  single(n IN numbers WHERE n > 4) AS exactlyOneGreaterThanFour;
~~~

Tất cả bốn cột đều trả `true`:

- `all()`: mọi phần tử có thỏa điều kiện không?
- `any()`: có ít nhất một phần tử thỏa điều kiện không?
- `none()`: có phải không phần tử nào thỏa điều kiện không?
- `single()`: có đúng một phần tử thỏa điều kiện không?

| Hàm | List rỗng `[]`, điều kiện bất kỳ |
| --- | --- |
| `all()` | `true` |
| `any()` | `false` |
| `none()` | `true` |
| `single()` | `false` |

Với phần tử `null`, kết quả của các hàm kiểm tra có thể là `null` khi không thể xác định chắc chắn đúng/sai. Vì vậy, hãy xác định cách xử lý phần tử thiếu dữ liệu trước khi dùng predicate để đưa ra quyết định nghiệp vụ quan trọng.

Nếu cần **giữ danh sách phần tử thỏa điều kiện**, sử dụng comprehension. Nếu chỉ cần **xác nhận điều kiện đúng hoặc sai**, `all()`, `any()`, `none()`, `single()` thường diễn đạt ý định rõ hơn so với tính `size()` của danh sách trung gian.

## 8. Làm việc với node, relationship và đường đi

List comprehension không bị giới hạn ở list literal. Nó có thể xử lý danh sách các node hoặc relationship được tạo từ truy vấn property graph.

Giả sử đồ thị có các node và quan hệ:

~~~text
(:Customer {id})-[:PLACED]->(:Order {id, status, amount})
(:Person {id, name, active})-[:KNOWS]->(:Person)
~~~

### Lọc các đơn hàng sau khi đã gom thành list

~~~cypher
MATCH (c:Customer {id: $customerId})-[:PLACED]->(o:Order)
WITH c, o
ORDER BY o.createdAt DESC, o.id ASC
WITH c, collect(o) AS orders
RETURN
  c.id AS customerId,
  [o IN orders | o.id] AS allOrderIds,
  [o IN orders WHERE o.status = 'PAID' | o.id] AS paidOrderIds,
  [o IN orders WHERE o.amount >= 500000
     | {id: o.id, amount: o.amount}] AS largeOrders;
~~~

Ở đây:

1. `MATCH` tìm các node `Order` có quan hệ `PLACED` từ khách hàng được chọn.
2. `ORDER BY` sắp xếp các hàng theo thời gian tạo và ID trước khi gom.
3. `collect(o)` gom các node `Order` thành một list cho khách hàng.
4. Các comprehension chọn ra những biểu diễn khác nhau của cùng list đơn: mọi ID, ID đã thanh toán và các đơn có giá trị lớn.

Ví dụ giả định graph có thuộc tính `createdAt`, `status` và `amount` phù hợp; truy vấn chỉ trả dữ liệu nếu khách hàng và đơn hàng tồn tại. `collect()` cần cân nhắc về bộ nhớ khi một khách hàng có quá nhiều đơn; nếu chỉ cần vài đơn, nên giới hạn hoặc xử lý hàng trước khi gom.

### Tạo list từ node trên đường đi

Hàm `nodes(path)` trả về danh sách node nằm trên đường đi đã tìm được:

~~~cypher
MATCH p = (a:Person {id: $personId})-[:KNOWS*1..3]->(b:Person)
WITH nodes(p) AS people
RETURN
  [person IN people | person.name] AS namesOnPath,
  [person IN people
    WHERE person.active = true
    | person.name] AS activeNamesOnPath;
~~~

Nếu một đường đi gồm ba node tên `An`, `Bình` và `Chi`, trong đó `An` và `Chi` có `active = true`, kết quả là hai list:

~~~text
namesOnPath       = ['An', 'Bình', 'Chi']
activeNamesOnPath = ['An', 'Chi']
~~~

List comprehension giữ thứ tự các node trên chính path. Tuy nhiên, nếu `MATCH` tìm được **nhiều đường đi**, truy vấn sinh một hàng cho mỗi đường đi; nếu cần sắp xếp các đường đi với nhau, hãy có `ORDER BY` thích hợp ở cấp truy vấn.

### Pattern comprehension: tạo list trực tiếp từ mẫu quan hệ

Cypher còn hỗ trợ *pattern comprehension*: viết mẫu quan hệ trong cặp ngoặc vuông và chiếu thành list:

~~~cypher
MATCH (c:Customer {id: $customerId})
RETURN [
  (c)-[:PLACED]->(o:Order)
  WHERE o.status = 'PAID'
  | o.id
] AS paidOrderIds;
~~~

Với khách hàng đã tìm được, biểu thức tạo list ID của các đơn thỏa mẫu quan hệ và điều kiện. Khác với list comprehension thông thường (duyệt một list có sẵn), pattern comprehension lấy các giá trị từ **mẫu đồ thị**. Nếu không có quan hệ phù hợp, list tương ứng là rỗng; nếu không có node `c` ở `MATCH` ban đầu, toàn truy vấn không có hàng. Không giả định thứ tự các kết quả khi không có cách sắp xếp rõ ràng.

Pattern comprehension thuận tiện cho biểu thức ngắn. Với truy vấn phức tạp cần lọc nhiều bước, tổng hợp và kiểm soát số hàng, có thể dùng `MATCH`/`WITH`/`collect()` hoặc subquery phù hợp để diễn đạt rõ quá trình hơn.

## 9. Kết hợp với tham số Java Driver và Spring Data Neo4j

Một ứng dụng Java thường gửi danh sách map cho Cypher qua **query parameters**. Ví dụ giá trị của tham số `$products`:

~~~json
[
  {"sku": " P01 ", "price": 120000, "name": "Sách Neo4j"},
  {"sku": "P02", "price": 80000, "name": "Sách Cypher"},
  {"sku": "", "price": 500000, "name": "Thiếu mã"},
  {"sku": "P03", "price": 200000, "name": "Sách Java"}
]
~~~

Tham số `$minPrice` có thể là `100000`. Truy vấn tạo một list sản phẩm hợp lệ để trả về ứng dụng:

~~~cypher
WITH coalesce($products, []) AS products
RETURN [
  product IN products
  WHERE
    product.sku IS NOT NULL
    AND trim(product.sku) <> ''
    AND product.price IS NOT NULL
    AND product.price >= $minPrice
  | {
      sku: toUpper(trim(product.sku)),
      name: product.name,
      price: product.price
    }
] AS eligibleProducts;
~~~

Kết quả có hai map: sản phẩm `P01` với giá `120000` và `P03` với giá `200000`. Sản phẩm có giá thấp hơn ngưỡng hoặc thiếu SKU hợp lệ bị loại. Ứng dụng nên kiểm tra trước rằng `sku` là chuỗi, `price` là giá trị số và tham số ngưỡng đúng kiểu, để tránh lỗi khi gọi `trim()` hoặc so sánh.

Nếu bước tiếp theo cần **ghi dữ liệu vào graph**, mở list đã chuẩn hóa thành hàng:

~~~cypher
WITH [
  sku IN coalesce($skus, [])
  WHERE sku IS NOT NULL AND trim(sku) <> ''
  | toUpper(trim(sku))
] AS cleanedSkus
UNWIND cleanedSkus AS sku
WITH DISTINCT sku
MERGE (p:Product {sku: sku})
RETURN count(p) AS distinctProductsTouched;
~~~

Các bước xử lý:

1. List comprehension lọc SKU rỗng và chuẩn hóa giá trị.
2. `UNWIND` chuyển list thành các hàng.
3. `WITH DISTINCT` chỉ giữ một hàng cho mỗi SKU.
4. `MERGE` tìm hoặc tạo node `Product` theo SKU.

`distinctProductsTouched` đếm số hàng SKU riêng biệt được xử lý, **không phải số node vừa tạo mới**. Với hệ thống ghi đồng thời, nên có uniqueness constraint phù hợp trên `:Product(sku)` để bảo đảm tính duy nhất trong database. Truy vấn nhận tham số tương tự có thể chạy qua Neo4j Java Driver hoặc repository/query tùy chỉnh trong Spring Data Neo4j; tránh nối chuỗi Cypher bằng dữ liệu do người dùng nhập.

## 10. Lỗi và ngộ nhận thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Kỳ vọng nhiều hàng nhưng chỉ có một hàng chứa list | List comprehension trả về **giá trị list**, không tách thành hàng | Dùng `UNWIND` nếu cần mỗi phần tử là một hàng |
| Phần tử `null` biến mất sau lọc | Predicate với `null` không trả `true` | Viết rõ điều kiện `IS NULL`/`IS NOT NULL` theo yêu cầu |
| Kết quả là `null` thay vì `[]` | Cả list đầu vào bằng `null` | Dùng `coalesce(sourceList, [])` khi hợp lý |
| Cùng mã xuất hiện nhiều lần | Comprehension bảo toàn phần tử trùng | Dùng `UNWIND` + `DISTINCT` + `collect()` khi nghiệp vụ cần duy nhất |
| Sai thứ tự trong list tạo từ graph | Hàng đầu vào `collect()` chưa được sắp xếp | `ORDER BY` trước bước `collect()` |
| Kiểm tra bằng `any()` trả `null` | Có predicate trên phần tử `null` làm kết quả chưa xác định | Xử lý `null` trước, hoặc quy định cách diễn giải ba trạng thái |
| Tăng bộ nhớ khi trả danh sách rất dài | `collect()` hoặc comprehension tạo list quá lớn | Giới hạn phần dữ liệu cần đưa vào list; kiểm tra kế hoạch và số hàng |
| `WHERE` ngoài comprehension làm mất cả bản ghi | `WITH ... WHERE` lọc **hàng**, không lọc phần tử của list | Đặt điều kiện bên trong `[x IN list WHERE ...]` nếu muốn giữ hàng gốc |

### Một số nguyên tắc thực hành

- **Chọn đúng kiểu kết quả:** một list, một giá trị logic hay nhiều hàng? List comprehension, list predicate và `UNWIND` phục vụ các mục đích khác nhau.
- **Xác định ý nghĩa của `null`:** phân biệt list không có phần tử, list chưa được cung cấp và phần tử thiếu dữ liệu.
- **Chỉ loại trùng khi được phép:** trong dữ liệu đơn hàng, hai dòng cùng SKU có thể có ý nghĩa riêng (chẳng hạn lô hàng hoặc mức giá khác nhau).
- **Kiểm soát kích thước list:** việc tạo và giữ danh sách lớn trong truy vấn có chi phí; đẩy điều kiện lọc xuống các bước đọc graph khi điều đó không làm thay đổi ý nghĩa.
- **Quan sát kế hoạch:** dùng `EXPLAIN` để xem kế hoạch và `PROFILE` trên dữ liệu thử để kiểm tra số hàng qua từng bước, nhất là trước và sau `collect()`/`UNWIND`.

## 11. Bài thực hành

### Bài 1 — Lọc rồi biến đổi số

Cho dãy số từ 1 đến 10. Hãy trả một list chứa **bình phương của các số chia hết cho 3**.

~~~cypher
WITH range(1, 10) AS numbers
RETURN [n IN numbers WHERE n % 3 = 0 | n * n] AS result;
~~~

Kết quả kỳ vọng: `[9, 36, 81]`.

### Bài 2 — Lọc map và giữ lại các trường cần thiết

Cho ba đơn hàng với ID, trạng thái và tổng tiền như bên dưới. Trả về một list chỉ gồm ID và số tiền của những đơn `PAID`.

~~~cypher
WITH [
  {id: 'O01', status: 'PAID', total: 300000},
  {id: 'O02', status: 'PENDING', total: 450000},
  {id: 'O03', status: 'PAID', total: 250000}
] AS orders
RETURN [
  o IN orders
  WHERE o.status = 'PAID'
  | {orderId: o.id, amount: o.total}
] AS paidOrders;
~~~

Kết quả:

~~~text
[
  {orderId: 'O01', amount: 300000},
  {orderId: 'O03', amount: 250000}
]
~~~

### Bài 3 — Dự đoán kết quả với null

~~~cypher
WITH [2, null, 5, 2] AS numbers
RETURN
  [n IN numbers WHERE n >= 2] AS filtered,
  [n IN numbers WHERE n IS NOT NULL | n * 3] AS multiplied,
  size([n IN numbers WHERE n = 2]) AS countTwos;
~~~

Đáp án:

- `filtered = [2, 5, 2]`: `null` không đạt điều kiện `n >= 2`.
- `multiplied = [6, 15, 6]`: loại `null` rồi nhân ba.
- `countTwos = 2`: hai lần xuất hiện số `2` được tính riêng, vì comprehension không tự loại trùng.

### Câu hỏi tự kiểm tra

**Nếu bạn cần tìm node `Product` cho từng SKU hợp lệ, có thể chỉ dùng `[sku IN skus WHERE ...]` rồi `MATCH` trực tiếp không?** Không thể coi list vừa tạo là các hàng riêng. Trước khi `MATCH`/`MERGE` theo từng SKU, thường cần `UNWIND cleanedSkus AS sku` để chuyển list thành những hàng có biến `sku` độc lập.

## Ghi nhớ

List comprehension là công cụ ngắn gọn để **tạo list mới từ list đã có** trong Cypher:

~~~cypher
[x IN source WHERE predicate | projection]
~~~

`WHERE` bên trong biểu thức chọn phần tử, `| projection` biến đổi phần tử, còn kết quả vẫn là **một giá trị list**. Muốn tách thành hàng, dùng `UNWIND`; muốn kiểm tra một điều kiện trên toàn list, cân nhắc `all()`, `any()`, `none()` hoặc `single()`. Khi dùng với `collect()`, `nodes(path)` và tham số từ Java Driver/Spring Data Neo4j, hãy xử lý rõ danh sách rỗng, `null`, giá trị trùng và thứ tự để truy vấn Neo4j đáng tin cậy và dễ bảo trì.

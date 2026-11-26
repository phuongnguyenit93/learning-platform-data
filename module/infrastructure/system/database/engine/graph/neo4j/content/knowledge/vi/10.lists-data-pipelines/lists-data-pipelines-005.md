# Map projection trong Cypher: tạo cấu trúc kết quả theo nhu cầu ứng dụng

## Mục tiêu bài học

Trong Neo4j, dữ liệu liên kết được tổ chức dưới dạng **property graph**: node chứa thuộc tính thực thể, relationship chứa quan hệ và thuộc tính của quan hệ. Một ứng dụng thường không muốn nhận toàn bộ node hoặc relationship từ Neo4j. Ví dụ, trang hồ sơ khách hàng chỉ cần `id`, `name` và ba đơn hàng gần đây; API báo cáo có thể cần tổng tiền, trạng thái cùng danh sách sản phẩm, nhưng không cần mọi thuộc tính nội bộ của graph.

Trong chương **Danh sách và luồng dữ liệu** của module `DATABASE_ENGINE_GRAPH_NEO4J`, **map projection** là công cụ của Cypher để tạo một **map kết quả theo hình dạng mà ứng dụng cần**, dựa trên một biến map, node hoặc relationship đã có. Cú pháp có thể chọn thuộc tính, thêm trường tính toán và lồng các map hoặc list khác. Bài học có liên hệ trực tiếp với cách trả kết quả qua **Neo4j Java Driver** và truy vấn tùy chỉnh trong **Spring Data Neo4j**.

Sau bài này, bạn sẽ:

- Phân biệt **map literal** `{key: value}` với **map projection** `variable { .property, key: expression }`.
- Dùng property selector `.property`, trường tính toán `key: expression` và toán tử `.*`.
- Kết hợp map projection với `MATCH`, `WITH`, `collect()` và list comprehension để tạo kết quả lồng nhau.
- Hiểu cách xử lý thuộc tính thiếu, giá trị `null`, số hàng và thứ tự danh sách.
- Thiết kế payload Cypher thuận tiện cho DTO/API, đồng thời tránh xuất ngoài ý muốn các thuộc tính nội bộ.

## 1. Vì sao cần map projection?

Giả sử đồ thị có một node khách hàng:

~~~text
(:Customer {
  id: 'C01',
  name: 'Lan',
  email: 'lan@example.test',
  loyaltyPoints: 180,
  internalNote: 'Chỉ dùng trong vận hành'
})
~~~

Ứng dụng công khai chỉ cần:

~~~json
{
  "id": "C01",
  "name": "Lan",
  "tier": "GOLD"
}
~~~

Thay vì gửi toàn bộ node `Customer` rồi xử lý dư thừa ở phía ứng dụng, có thể dùng Cypher tạo đúng ba trường:

~~~cypher
MATCH (c:Customer {id: $customerId})
RETURN c {
  .id,
  .name,
  tier: CASE WHEN c.loyaltyPoints >= 100 THEN 'GOLD'
             ELSE 'STANDARD' END
} AS customer;
~~~

Kết quả trả về là **một cột `customer` chứa một map**, với các khóa `id`, `name` và `tier`. Thuộc tính `internalNote` không xuất hiện vì không được chọn. Trong truy vấn này, `c` là node vẫn tồn tại trong đồ thị; map projection chỉ **tạo giá trị trả về**, không sửa node hay ghi dữ liệu mới.

Nếu `MATCH` không tìm thấy node có ID tương ứng, truy vấn trên trả **0 hàng**. Phần xử lý khi cần trả một hàng chứa `null` sẽ được giải thích sau.

## 2. Cú pháp map projection

Hình thức tổng quát:

~~~cypher
mapVariable {
  .propertyA,
  .propertyB,
  customKey: expression
}
~~~

Trong đó, `mapVariable` là **biến đã được ràng buộc** với map, node hoặc relationship. Các mục trong cặp ngoặc nhọn mô tả những khóa cần có ở map kết quả.

Ba dạng mục phổ biến:

| Dạng | Ví dụ | Kết quả |
| --- | --- | --- |
| **Property selector** | `c { .id, .name }` | Tạo khóa `id`, `name` từ các property tương ứng |
| **Key–value entry** | `c { displayName: toUpper(c.name) }` | Tạo khóa `displayName` với giá trị tính từ biểu thức |
| **All-properties selector** | `c { .* }` | Sao chép tất cả property hiện có của đối tượng gốc |

Ngoài ra còn có **variable selector** để đưa giá trị biến cùng tên vào map, chẳng hạn `c { .id, orderCount }` khi `orderCount` đã được định nghĩa trong phạm vi truy vấn. Với một bài API thực tế, dạng `key: expression` thường dễ đọc nhất vì chỉ rõ tên khóa đầu ra.

### Ví dụ tự chạy, không cần dữ liệu graph

Map projection hoạt động cả với một biến đang chứa **map literal**:

~~~cypher
WITH {
  id: 'C01',
  name: 'Lan',
  email: 'lan@example.test',
  loyaltyPoints: 180
} AS c
RETURN c {
  .id,
  .name,
  tier: CASE WHEN c.loyaltyPoints >= 100 THEN 'GOLD'
             ELSE 'STANDARD' END
} AS profile;
~~~

Kết quả:

~~~text
profile = {
  id: 'C01',
  name: 'Lan',
  tier: 'GOLD'
}
~~~

Đây là ví dụ thuần Cypher: `c` là map trong truy vấn, chưa phải node Neo4j. Khi thay bằng `MATCH (c:Customer)`, cú pháp projection vẫn tương tự.

### Map projection và map literal khác nhau thế nào?

Hai câu lệnh sau cùng biểu diễn hai khóa `id` và `name`:

~~~cypher
WITH {id: 'C01', name: 'Lan'} AS c
RETURN
  {id: c.id, name: c.name} AS literalMap,
  c {.id, .name} AS projectedMap;
~~~

- **Map literal** `{id: c.id, name: c.name}` tạo map trực tiếp từ các biểu thức. Không cần một biến map gốc.
- **Map projection** `c {.id, .name}` bám vào biến `c` và lấy nhanh các property cùng tên. Nó đặc biệt thuận tiện khi cần giữ nhiều tên property của node.

Map literal phù hợp khi các trường đến từ nhiều nguồn không có một đối tượng gốc rõ ràng; map projection phù hợp khi bạn đang thiết kế “hình nhìn” của một node, relationship hoặc map hiện có. Cả hai đều tạo **giá trị map**, không tạo node.

## 3. Chọn trường và đặt tên theo hợp đồng API

### Chỉ lấy những property cần thiết

~~~cypher
WITH {
  id: 'P01',
  sku: 'BOOK-001',
  title: 'Học Neo4j',
  costPrice: 60000,
  salePrice: 100000,
  internalSupplierCode: 'SUP-09'
} AS p
RETURN p {.sku, .title, .salePrice} AS publicProduct;
~~~

Kết quả gồm `sku`, `title` và `salePrice`. Các trường như `costPrice`, `internalSupplierCode` không nằm trong map mới.

### Đổi tên trường

Property selector giữ **tên property gốc**. Muốn đổi tên trong output, dùng mục `key: expression`:

~~~cypher
WITH {id: 'C01', name: 'Lan', loyaltyPoints: 180} AS c
RETURN c {
  customerId: c.id,
  displayName: c.name,
  points: c.loyaltyPoints
} AS customerView;
~~~

Map đầu ra:

~~~text
{
  customerId: 'C01',
  displayName: 'Lan',
  points: 180
}
~~~

Đối với ứng dụng Java, cách đặt tên khóa rõ ràng giúp việc chuyển thành DTO hoặc JSON nhất quán hơn. Nếu một property được đổi tên, chỉ cần dùng `customerId: c.id`; không cần thay đổi schema của node đang lưu.

### Trộn property và trường được tính

~~~cypher
WITH {sku: 'P01', price: 100000, quantity: 3} AS line
RETURN line {
  .sku,
  .quantity,
  unitPrice: line.price,
  lineTotal: line.price * line.quantity
} AS orderLine;
~~~

Kết quả là:

~~~text
{
  sku: 'P01',
  quantity: 3,
  unitPrice: 100000,
  lineTotal: 300000
}
~~~

Giá trị `lineTotal` chỉ được tính khi truy vấn chạy; map projection không tự ghi `lineTotal` vào node hoặc relationship.

### Chọn toàn bộ property bằng `.*`

~~~cypher
WITH {id: 'C01', name: 'Lan', email: 'lan@example.test'} AS c
RETURN c {.*} AS copiedProperties;
~~~

`.*` cho phép sao chép toàn bộ property/entry hiện có của biến gốc vào map kết quả. Với **node**, nó lấy các **property của node**, không tự bổ sung labels, ID nội bộ hay các relationship. Các thông tin khác, khi cần, phải được đặt vào trường tính toán:

~~~cypher
MATCH (c:Customer {id: $customerId})
RETURN c {
  .id,
  .name,
  labels: labels(c),
  graphElementId: elementId(c)
} AS debugView;
~~~

Ở đây `labels(c)` và `elementId(c)` được tính thành những khóa mới. Giá trị `elementId(c)` hữu ích cho một số thao tác với thực thể bên trong Neo4j, nhưng không nên mặc định thay thế **business ID ổn định** của ứng dụng như `c.id`.

> Với API công khai, ưu tiên **liệt kê rõ các property được phép trả về**. `c {.*}` có thể vô tình đưa thêm trường nhạy cảm hoặc trường vận hành vào response khi schema phát triển.

## 4. Biến, phạm vi và số hàng trong pipeline

Map projection chỉ tạo một **giá trị trong hàng hiện tại**. Nó không tự gom nhiều hàng và không làm biến đổi số lượng hàng giống `UNWIND` hoặc hàm tổng hợp.

~~~cypher
UNWIND [
  {id: 'C01', name: 'Lan'},
  {id: 'C02', name: 'Minh'}
] AS c
RETURN c {.id, .name} AS customer
ORDER BY customer.id;
~~~

Kết quả có **hai hàng**, mỗi hàng chứa một map ở cột `customer`. Nếu ứng dụng muốn **một hàng chứa danh sách map**, cần gom lại:

~~~cypher
UNWIND [
  {id: 'C01', name: 'Lan'},
  {id: 'C02', name: 'Minh'}
] AS c
WITH c
ORDER BY c.id
RETURN collect(c {.id, .name}) AS customers;
~~~

Kết quả có một hàng, cột `customers` là:

~~~text
[
  {id: 'C01', name: 'Lan'},
  {id: 'C02', name: 'Minh'}
]
~~~

`ORDER BY` trong `WITH` định nghĩa thứ tự hàng được đưa vào `collect()` ngay sau đó. Map projection giúp xác định **cột và cấu trúc của từng phần tử**, còn `collect()` thay đổi **mức gom nhóm** từ nhiều hàng thành danh sách.

### Đổi tên biến rồi projection

~~~cypher
MATCH (c:Customer)
WITH c AS customer
RETURN customer {.id, .name} AS profile;
~~~

Sau `WITH c AS customer`, biến dùng trong projection là `customer`. Nếu ở giữa có `WITH` chỉ giữ `customer.id AS customerId`, biến node `customer` sẽ không còn trong phạm vi để dùng `customer { ... }`. Vì vậy, hãy giữ lại biến gốc khi còn cần chọn property của nó ở bước sau.

### Biểu thức phía sau dấu hai chấm có thể lấy biến khác

~~~cypher
WITH {id: 'O01', status: 'PAID'} AS o, 250000 AS calculatedTotal
RETURN o {
  .id,
  .status,
  total: calculatedTotal
} AS orderSummary;
~~~

Map projection lấy `id` và `status` từ `o`, nhưng trường `total` lấy từ biến `calculatedTotal`. Đây là cách kết hợp dữ liệu node với giá trị trung gian đã tính ở bước `WITH`.

## 5. Tạo cấu trúc kết quả lồng nhau cho khách hàng và đơn hàng

Trong property graph có thể tồn tại mô hình:

~~~text
(:Customer {id, name})
       |
       +--[:PLACED]--> (:Order {id, status, createdAt, total})
                              |
                              +--[:CONTAINS {quantity}]--> (:Product {sku, name, price})
~~~

API có thể muốn một đối tượng khách hàng chứa **danh sách đơn hàng**:

~~~json
{
  "id": "C01",
  "name": "Lan",
  "orders": [
    {"id": "O01", "status": "PAID", "total": 250000},
    {"id": "O02", "status": "PENDING", "total": 100000}
  ]
}
~~~

### Bước 1 — Tạo projection cho từng đơn hàng

~~~cypher
MATCH (c:Customer {id: $customerId})-[:PLACED]->(o:Order)
RETURN
  c.id AS customerId,
  o {.id, .status, .total} AS orderView
ORDER BY orderView.id;
~~~

Mỗi đơn là một hàng; cột `orderView` là map với đúng ba khóa. Với khách có hai đơn, kết quả có hai hàng, **chưa phải** đối tượng JSON lồng nhau ở trên.

### Bước 2 — Gom các projection thành danh sách

~~~cypher
MATCH (c:Customer {id: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, o
ORDER BY o.createdAt DESC, o.id ASC
WITH c, collect(o {.id, .status, .total}) AS orders
RETURN c {
  .id,
  .name,
  orders: orders
} AS customer;
~~~

Phân tích:

1. `MATCH` tìm khách hàng theo business ID.
2. `OPTIONAL MATCH` tìm đơn, đồng thời giữ khách trong pipeline nếu chưa có đơn.
3. `ORDER BY` sắp xếp đơn theo thời gian tạo giảm dần và ID tăng dần để có thứ tự xác định.
4. `collect(o {.id, .status, .total})` gom các map đơn hàng. Khi `o` là `null` vì không có đơn, map projection nhận `null` và `collect()` bỏ qua `null`, nên kết quả list là `[]`.
5. `c {.id, .name, orders: orders}` tạo map gốc chứa cả thông tin khách hàng và list đơn hàng đã tạo.

Với dữ liệu minh họa, output có dạng trong khối JSON ở trên (giả sử thứ tự và giá trị `createdAt` phù hợp). Nếu khách có node nhưng chưa có đơn, `orders` là list rỗng. Nếu khách **không tồn tại**, `MATCH` đầu tiên trả 0 hàng.

### Bước 3 — Chỉ đưa vào một phần danh sách

~~~cypher
MATCH (c:Customer {id: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, o
ORDER BY o.createdAt DESC, o.id ASC
WITH c, collect(o {.id, .status, .total}) AS allOrders
RETURN c {
  .id,
  .name,
  totalOrders: size(allOrders),
  recentOrders: allOrders[..3]
} AS customer;
~~~

`allOrders[..3]` trả tối đa ba phần tử đầu, trong khi `size(allOrders)` vẫn là tổng số đơn. Tuy nhiên, truy vấn phải **gom tất cả đơn trước khi cắt**. Với khách có rất nhiều đơn, nên cân nhắc subquery có `ORDER BY`/`LIMIT` để giới hạn số đơn cần tải trước khi `collect()`, đồng thời tính tổng riêng nếu nghiệp vụ cần cả hai.

## 6. Map projection kết hợp list comprehension

Map projection cũng dùng được trong list comprehension, cho phép biến đổi **nhiều map đầu vào thành một list map đầu ra** ngay trong một biểu thức.

### Dữ liệu đầu vào là list map

~~~cypher
WITH {
  id: 'O01',
  items: [
    {sku: 'P01', quantity: 2, unitPrice: 100000},
    {sku: 'P02', quantity: 1, unitPrice: 50000}
  ]
} AS orderData
RETURN orderData {
  .id,
  items: [
    item IN orderData.items
    | item {
        .sku,
        .quantity,
        lineTotal: item.quantity * item.unitPrice
      }
  ],
  total: reduce(
    sum = 0,
    item IN orderData.items |
    sum + item.quantity * item.unitPrice
  )
} AS orderView;
~~~

Kết quả dự kiến:

~~~text
{
  id: 'O01',
  items: [
    {sku: 'P01', quantity: 2, lineTotal: 200000},
    {sku: 'P02', quantity: 1, lineTotal: 50000}
  ],
  total: 250000
}
~~~

Ở đây:

- Projection bên ngoài dùng biến `orderData`.
- List comprehension duyệt `orderData.items` và tạo map cho **mỗi** `item`.
- Projection bên trong chọn `sku`, `quantity`, cộng thêm `lineTotal`.
- `reduce()` tính tổng trên list các dòng hàng, trả về số `250000`.

Ví dụ không yêu cầu tồn tại node `Order` trong graph. Nếu `items` là trường tùy chọn có thể `null`, dùng `coalesce(orderData.items, [])` ở cả phần comprehension và phần tính tổng, sau khi đã thống nhất quy tắc nghiệp vụ cho trường thiếu.

### Chỉ tạo projection cho phần tử đạt điều kiện

~~~cypher
WITH [
  {sku: 'P01', price: 120000, enabled: true},
  {sku: 'P02', price: 80000, enabled: false},
  {sku: 'P03', price: 150000, enabled: true}
] AS products
RETURN [
  p IN products
  WHERE p.enabled = true
  | p {
      .sku,
      .price,
      displayPrice: toString(p.price) + ' VND'
    }
] AS availableProducts;
~~~

List `availableProducts` chứa đúng hai map, tương ứng `P01` và `P03`. `WHERE` **bên trong comprehension** lọc phần tử của list; nó không loại bỏ hàng truy vấn gốc. Nhờ vậy, API vẫn có thể trả một trường `availableProducts: []` nếu không sản phẩm nào phù hợp.

## 7. Node, relationship và các thông tin không phải property

### Projection trên node

~~~cypher
MATCH (p:Product {sku: $sku})
RETURN p {
  .sku,
  .name,
  .price,
  isAvailable: coalesce(p.stock, 0) > 0
} AS product;
~~~

Trường `isAvailable` được tính từ property `stock`. Nếu property thiếu hoặc bằng `null`, `coalesce(p.stock, 0)` đưa về 0 theo quy ước trong ví dụ.

### Projection trên relationship

Một relationship có thể chứa các property như `quantity` hoặc `createdAt`. Có thể projection từ biến quan hệ tương tự node:

~~~cypher
MATCH (o:Order {id: $orderId})-[line:CONTAINS]->(p:Product)
RETURN line {
  .quantity,
  productSku: p.sku,
  productName: p.name,
  lineTotal: line.quantity * p.price,
  relationshipType: type(line)
} AS orderLine
ORDER BY orderLine.productSku;
~~~

`line` là relationship; `.quantity` lấy property của relationship; `productSku`, `productName` đọc thuộc tính từ node `p`; `type(line)` trả tên loại relationship. Câu lệnh này tạo map theo từng dòng sản phẩm của đơn hàng. Nó không xuất trực tiếp toàn bộ node `p` hay relationship `line`.

### Projection một đường đi thành danh sách tên

~~~cypher
MATCH path = (start:Person {id: $personId})-[:KNOWS*1..3]->(target:Person)
WITH nodes(path) AS pathNodes
RETURN [
  n IN pathNodes
  | n {.id, .name}
] AS peopleOnPath;
~~~

`nodes(path)` tạo list node theo thứ tự trên đường đi; comprehension tạo list các map `{id, name}`. Nếu tìm được nhiều đường đi, truy vấn tạo **một hàng cho mỗi đường đi**, không tự gộp các đường đi vào một danh sách.

## 8. Null, thuộc tính thiếu và hình dạng dữ liệu

Map projection dùng các quy tắc giá trị của Cypher; cần phân biệt **map nguồn bằng null**, **property thiếu** và **biểu thức trả null**.

### Property không có trên node hoặc map

~~~cypher
WITH {id: 'C01', name: 'Lan'} AS c
RETURN c {
  .id,
  .name,
  .phone,
  phoneOrDefault: coalesce(c.phone, 'Chưa cập nhật')
} AS customer;
~~~

Map kết quả chứa khóa `phone` với giá trị `null` và khóa `phoneOrDefault` có giá trị `'Chưa cập nhật'`. Việc chọn thuộc tính không tồn tại không tự sinh ra một chuỗi rỗng.

### Map nguồn bằng null

~~~cypher
OPTIONAL MATCH (c:Customer {id: $customerId})
RETURN c {.id, .name} AS customer;
~~~

Vì `OPTIONAL MATCH` giữ một hàng khi không tìm thấy node, giá trị `c` khi đó là `null`; **map projection của c cũng là null**. Điều này khác với:

~~~cypher
MATCH (c:Customer {id: $customerId})
RETURN c {.id, .name} AS customer;
~~~

Trường hợp `MATCH` thường không tìm thấy khách sẽ trả **0 hàng**, nên phía ứng dụng phải phân biệt hai hợp đồng API này.

### Một projection chứa trường null vẫn là một map

~~~cypher
WITH {id: 'C01', email: null} AS c
RETURN c {.id, .email, emailVerified: false} AS profile;
~~~

Kết quả là map có `id`, `email: null` và `emailVerified: false`. Việc bỏ hoàn toàn các khóa null khỏi JSON là lựa chọn của tầng chuyển đổi/serialization hoặc quy tắc xây dựng map khác; map projection cơ bản không có tùy chọn “ẩn mọi khóa null”.

### Đừng nhầm map với JSON

Kết quả Cypher trả về cho driver là **giá trị map**. Java Driver nhận các giá trị có kiểu riêng; khi ứng dụng chuyển sang JSON, cách biểu diễn ngày, giờ, số, node hoặc giá trị `null` còn phụ thuộc thư viện và hợp đồng API. Việc map projection tạo đúng khóa chỉ giải quyết **hình dạng logic** của dữ liệu trả về.

## 9. Java Driver và Spring Data Neo4j

Một lợi ích quan trọng của map projection là giảm lượng thông tin không cần thiết phải đọc hoặc xử lý trong ứng dụng. Với Neo4j Java Driver, có thể chạy truy vấn có tham số rồi ánh xạ cột map.

Ví dụ Java Driver:

~~~java
String cypher = """
    MATCH (c:Customer {id: $customerId})
    RETURN c {
      .id,
      .name,
      tier: CASE WHEN c.loyaltyPoints >= 100
                 THEN 'GOLD' ELSE 'STANDARD' END
    } AS profile
    """;

try (Session session = driver.session()) {
    List<Map<String, Object>> profiles = session.executeRead(tx ->
        tx.run(cypher, Values.parameters("customerId", "C01"))
          .list(record -> record.get("profile").asMap())
    );

    // Chuyển profiles thành DTO/JSON theo hợp đồng API.
}
~~~

Đoạn mã giả định biến `driver` là một đối tượng `org.neo4j.driver.Driver` đã được tạo và quản lý vòng đời. Các kiểu thường dùng gồm `org.neo4j.driver.Session`, `org.neo4j.driver.Values`, `java.util.List` và `java.util.Map`. Ứng dụng sẽ quyết định trả một kết quả, list kết quả hoặc xử lý khi không tìm được khách.

Nếu muốn trả trực tiếp danh sách đơn trong một cột map, Java có thể truy cập:

~~~java
Map<String, Object> profile = record.get("profile").asMap();
Object customerId = profile.get("id");
Object customerName = profile.get("name");
~~~

Các trường lồng nhau có thể cần ánh xạ tiếp và kiểm tra kiểu dữ liệu. Giữ nguyên tên khóa do Cypher trả về giúp giảm thao tác chuyển đổi không cần thiết.

Với **Spring Data Neo4j**, có thể dùng truy vấn tùy chỉnh để trả về các trường phục vụ DTO hoặc projection của tầng repository. Tuy nhiên, **map projection của Cypher không tự động bảo đảm ánh xạ thành một entity/DTO Java bất kỳ**. Cách ánh xạ phụ thuộc kiểu trả về, phiên bản thư viện và cấu hình converter/repository. Khi cần hợp đồng API phức tạp, cần kiểm tra kỹ mapping, hoặc dùng Java Driver để kiểm soát trực tiếp các cột map từ Cypher.

Hai lưu ý:

- **Tham số hóa**: dùng `$customerId`, `$sku` và các query parameter thay vì nối giá trị do người dùng nhập vào chuỗi Cypher.
- **Kiểm soát dữ liệu xuất**: chỉ chọn các thuộc tính cần thiết, xác định rõ trường tùy chọn, và không phụ thuộc `.*` trong API có dữ liệu nội bộ.

## 10. Độ chính xác và hiệu năng khi xây dựng response

Map projection giúp kết quả rõ ràng nhưng không thay thế thiết kế truy vấn và tối ưu hóa.

| Rủi ro | Biểu hiện | Hướng xử lý |
| --- | --- | --- |
| Trả quá nhiều dữ liệu | `node {.*}` xuất toàn bộ property, kể cả thông tin không cần | Liệt kê tường minh các trường cho phép |
| Đơn hàng lặp trong list | `MATCH` đi qua nhiều quan hệ và tạo nhiều hàng cho cùng `Order` | Xác định một hàng đại diện cho gì; gom theo đơn hoặc dùng `DISTINCT` phù hợp trước `collect()` |
| Thứ tự list không ổn định | `collect()` nhận hàng không được sắp xếp | Dùng `ORDER BY` ngay trước bước gom list |
| Chỉ cần 10 mục nhưng đã gom hàng nghìn mục | `collect()` trước, sau đó mới cắt `[..10]` | Giới hạn đầu vào sớm bằng `ORDER BY`/`LIMIT` hoặc subquery khi phù hợp |
| Sai cấu trúc API khi không tìm thấy node | `MATCH` trả 0 hàng, `OPTIONAL MATCH` có thể trả hàng với `null` | Quy định hợp đồng response, phân biệt “không tìm thấy” và “không có quan hệ” |
| Đánh đồng map projection với lưu dữ liệu | Trông giống object mới nhưng graph không đổi | Dùng `CREATE`/`MERGE`/`SET` nếu nghiệp vụ thực sự cần ghi |
| Đọc nhầm ID nội bộ là business ID | Dùng `elementId(node)` làm định danh ứng dụng lâu dài | Duy trì property khóa nghiệp vụ có constraint phù hợp |
| Mapping Java không như dự kiến | Truy vấn trả map/lồng list nhưng repository chờ entity | Kiểm tra kiểu trả về, converter và mapping; dùng Driver khi cần kiểm soát |

Khi tối ưu truy vấn, nên quan sát kế hoạch bằng `EXPLAIN` và số hàng thực tế bằng `PROFILE` trên dữ liệu thử. Tốn kém có thể đến từ việc mở rộng các relationship, gom list lớn hoặc tìm node thiếu index/constraint phù hợp; bản thân cú pháp `c {.id, .name}` không mặc định loại bỏ mọi chi phí truy cập dữ liệu.

### Kiểm tra số lượng và nhóm trước khi project

Ví dụ, nếu một đơn có nhiều dòng sản phẩm, truy vấn sau có thể tạo nhiều hàng cho cùng một đơn:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
RETURN c {.id, .name} AS customer, o {.id, .status} AS order;
~~~

Một khách có đơn `O01` chứa hai sản phẩm sẽ tạo hai hàng với cùng map `order`. Nếu API cần **mỗi đơn một lần**, hãy thiết kế truy vấn để thu thập các đơn duy nhất trước khi project hoặc trước khi gom vào danh sách:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
WITH DISTINCT c, o
WITH c, collect(o {.id, .status}) AS orders
RETURN c {.id, .name, orders: orders} AS customer;
~~~

`WITH DISTINCT c, o` loại các cặp khách–đơn trùng. `collect()` sau đó tạo list một lần cho mỗi cặp. Truy vấn ví dụ chỉ xét đơn có ít nhất một sản phẩm vì dùng `MATCH` qua `CONTAINS`; nếu muốn cả đơn trống, cần thay đổi cách ghép đồ thị cho đúng nghiệp vụ.

## 11. Bài thực hành

### Bài 1 — Projection đúng ba trường

Cho map:

~~~cypher
WITH {
  id: 'C07',
  name: 'Hà',
  email: 'ha@example.test',
  points: 75,
  privateMemo: 'Nội bộ'
} AS customer
RETURN customer {
  .id,
  .name,
  memberTier: CASE WHEN customer.points >= 100
                   THEN 'GOLD' ELSE 'STANDARD' END
} AS publicProfile;
~~~

Hãy dự đoán các trường xuất hiện. Kết quả chỉ có `id = 'C07'`, `name = 'Hà'` và `memberTier = 'STANDARD'`. `email` và `privateMemo` không có trong output.

### Bài 2 — List các sản phẩm đủ điều kiện

Hãy tạo một list các map sản phẩm chỉ gồm `sku` và `price`, lọc sản phẩm đang bán có giá ít nhất 100.000:

~~~cypher
WITH [
  {sku: 'P01', price: 120000, enabled: true},
  {sku: 'P02', price: 90000, enabled: true},
  {sku: 'P03', price: 200000, enabled: false},
  {sku: 'P04', price: 150000, enabled: true}
] AS products
RETURN [
  p IN products
  WHERE p.enabled = true AND p.price >= 100000
  | p {.sku, .price}
] AS result;
~~~

Kết quả kỳ vọng:

~~~text
[
  {sku: 'P01', price: 120000},
  {sku: 'P04', price: 150000}
]
~~~

### Bài 3 — Khách hàng có list đơn hàng

Yêu cầu: trên graph `Customer-[:PLACED]->Order`, trả một map `customer` có `id`, `name` và list `orders`. Mỗi đơn chỉ trả `id`, `status` và tổng tiền. Khách chưa có đơn vẫn cần xuất hiện với `orders: []`.

~~~cypher
MATCH (c:Customer {id: $customerId})
OPTIONAL MATCH (c)-[:PLACED]->(o:Order)
WITH c, o
ORDER BY o.id
WITH c, collect(o {.id, .status, .total}) AS orders
RETURN c {.id, .name, orders: orders} AS customer;
~~~

Để làm rõ kết quả, giả sử khách `C01` có đơn `O01` đã thanh toán, tổng `250000` và `O02` đang chờ, tổng `100000`. Map trả về có dạng:

~~~text
{
  id: 'C01',
  name: 'Lan',
  orders: [
    {id: 'O01', status: 'PAID', total: 250000},
    {id: 'O02', status: 'PENDING', total: 100000}
  ]
}
~~~

Khi dữ liệu Neo4j khác ví dụ, kết quả thay đổi theo những node/relationship thực có trong graph.

### Câu hỏi tự kiểm tra

1. `c {.id, .name}` tạo node `c` mới hay tạo map? **Tạo map**; graph không đổi.
2. `c {.*}` có tự mang labels và relationship vào response không? **Không**; nó chọn property của đối tượng gốc.
3. Nếu `OPTIONAL MATCH` không tìm thấy `c`, `c {.id}` cho giá trị gì? **`null`**, vì biến nguồn bằng `null`.
4. Projection trong một hàng có làm các đơn hàng gộp thành list không? **Không**; cần `collect()` hoặc biểu thức list thích hợp.
5. Khi cần API trả `orders: []` cho khách có tồn tại nhưng chưa có đơn, nên dùng cách nào? **`MATCH` khách, `OPTIONAL MATCH` đơn, `collect()` các projection**, rồi thêm trường `orders` vào projection khách.

## Ghi nhớ

**Map projection** giúp thiết kế **hình dạng dữ liệu trả về** trực tiếp trong Cypher:

~~~cypher
variable { .property, renamedKey: expression, nested: anotherList }
~~~

Nó tạo map từ node/relationship/map đã có, không ghi dữ liệu mới vào Neo4j. Kết hợp với `WITH`, `collect()`, `UNWIND` và list comprehension để kiểm soát phạm vi biến, số hàng và danh sách lồng nhau. Trong ứng dụng Java, chọn trường một cách tường minh, quy định rõ cách xử lý `null` và kiểm tra mapping giúp xây dựng API ổn định và dễ bảo trì.

# WITH trong Cypher: chuyển tiếp, đổi tên và giới hạn phạm vi biến

## Mục tiêu bài học

Trong Neo4j, dữ liệu được mô hình hóa thành **node**, **relationship** và các thuộc tính (property). Khi truy vấn một property graph, Cypher không chỉ tìm các node hay quan hệ phù hợp mà còn xử lý một **luồng hàng kết quả** qua nhiều mệnh đề. `WITH` là mệnh đề quan trọng để tổ chức luồng này.

Sau bài học, bạn có thể:

- Sử dụng `WITH` để chuyển những biến cần thiết từ giai đoạn truy vấn này sang giai đoạn tiếp theo.
- Đổi tên biến, tính biểu thức trung gian và hiểu vì sao biến không được chuyển tiếp sẽ ra khỏi phạm vi truy cập.
- Kết hợp `WITH` với `WHERE`, `DISTINCT`, hàm tổng hợp, `ORDER BY`, `SKIP`, `LIMIT` và `UNWIND`.
- Đọc lỗi phạm vi biến, tránh đếm trùng do nhân hàng khi đi qua relationship và chọn vị trí xử lý phù hợp trong pipeline.

## 1. `WITH` làm gì trong một truy vấn?

Hãy hình dung một truy vấn Cypher là chuỗi các bước biến đổi dữ liệu:

~~~text
MATCH ...          Tìm mẫu đồ thị và tạo các hàng kết quả
    |
WITH ...           Chọn, đổi tên, tính toán, gom nhóm hoặc lọc hàng
    |
MATCH ...          Mở rộng tìm kiếm bằng những biến còn trong phạm vi
    |
WITH ...           Xử lý kết quả trung gian
    |
RETURN ...         Trả kết quả cho ứng dụng
~~~

`WITH` có hai vai trò gắn chặt với nhau:

1. **Truyền dữ liệu qua các giai đoạn**: mỗi hàng sau `WITH` chứa các biến hoặc biểu thức được liệt kê trong mệnh đề đó.
2. **Xác định phạm vi biến**: những biến không được giữ lại thường không thể tham chiếu ở các mệnh đề tiếp theo. Biến được đổi tên bằng `AS` phải được dùng bằng tên mới.

Ví dụ cấu trúc tổng quát:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, o
MATCH (o)-[:CONTAINS]->(p:Product)
RETURN c.name AS customer, o.id AS orderId, p.sku AS productSku;
~~~

Ở bước thứ hai, `WITH c, o` giữ cả `c` lẫn `o`. Vì vậy bước `MATCH` tiếp theo có thể dùng `o` để tìm sản phẩm và `RETURN` vẫn có thể đọc `c.name`.

`WITH` giống `RETURN` ở khả năng chọn cột và tính biểu thức, nhưng `WITH` **tiếp tục truy vấn** còn `RETURN` **xuất kết quả**. `WITH` không tự tạo một transaction mới hoặc đảm bảo dữ liệu trung gian được ghi thành bảng vật lý; Neo4j vẫn có thể tối ưu kế hoạch thực thi của toàn truy vấn.

## 2. Dữ liệu minh họa: khách hàng, đơn hàng và sản phẩm

Các ví dụ sau sử dụng mô hình:

~~~text
(:Customer)-[:PLACED]->(:Order)-[:CONTAINS {quantity}]->(:Product)
~~~

Mỗi `Customer` đặt nhiều `Order`; mỗi `Order` chứa các `Product` với số lượng nằm trên quan hệ `CONTAINS`. Có thể tạo bộ dữ liệu nhỏ trong **cơ sở dữ liệu thử nghiệm trống** bằng truy vấn sau. Nếu chạy lại lệnh `CREATE`, dữ liệu sẽ bị tạo trùng.

~~~cypher
CREATE
  (lan:Customer {id: 'C01', name: 'Lan'}),
  (minh:Customer {id: 'C02', name: 'Minh'}),
  (o1:Order {id: 'O01', status: 'PAID'}),
  (o2:Order {id: 'O02', status: 'PENDING'}),
  (o3:Order {id: 'O03', status: 'PAID'}),
  (p1:Product {sku: 'P01', price: 100000}),
  (p2:Product {sku: 'P02', price: 50000}),
  (lan)-[:PLACED]->(o1),
  (lan)-[:PLACED]->(o2),
  (minh)-[:PLACED]->(o3),
  (o1)-[:CONTAINS {quantity: 2}]->(p1),
  (o1)-[:CONTAINS {quantity: 1}]->(p2),
  (o2)-[:CONTAINS {quantity: 1}]->(p1),
  (o3)-[:CONTAINS {quantity: 3}]->(p2);
~~~

Từ bộ dữ liệu này, Lan có hai đơn (`O01` và `O02`); Minh có một đơn (`O03`). Tổng giá trị các dòng hàng của đơn đã thanh toán là 250.000 cho Lan và 150.000 cho Minh.

## 3. Chuyển tiếp và đổi tên biến

### Giữ biến cần dùng ở bước sau

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, o
MATCH (o)-[line:CONTAINS]->(p:Product)
RETURN
  c.name AS customer,
  o.id AS orderId,
  p.sku AS productSku,
  line.quantity AS quantity
ORDER BY orderId, productSku;
~~~

Sau `WITH c, o`, cả hai biến vẫn khả dụng. Sau `MATCH` thứ hai, mỗi hàng tương ứng với một dòng sản phẩm trong đơn. Đơn `O01` có hai quan hệ `CONTAINS` nên tạo **hai hàng**, một chi tiết quan trọng khi đếm hoặc tính tổng về sau.

### Đổi tên bằng `AS`

~~~cypher
MATCH (customer:Customer)
WITH customer AS buyer
RETURN buyer.id AS customerId, buyer.name AS customerName
ORDER BY customerId;
~~~

Sau `WITH customer AS buyer`, tên cần dùng trong mệnh đề tiếp theo là `buyer`. Tên cũ `customer` không còn được chuyển tiếp. Tương tự, có thể tạo giá trị mới từ thuộc tính:

~~~cypher
MATCH (c:Customer)
WITH c.id AS customerId, toUpper(c.name) AS displayName
RETURN customerId, displayName
ORDER BY customerId;
~~~

`customerId` và `displayName` lúc này là các giá trị đã tính; biến node `c` không còn nằm trong phạm vi của `RETURN`.

### Bỏ biến là một phần của thiết kế phạm vi

Ví dụ **sai**:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c.name AS customerName
RETURN o.id AS orderId;
~~~

Truy vấn bị lỗi vì `o` không được chuyển tiếp qua `WITH`. Nếu vẫn cần `o.id`, hãy giữ `o` hoặc chuyển thuộc tính thành biến mới:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c.name AS customerName, o.id AS orderId
RETURN customerName, orderId
ORDER BY customerName, orderId;
~~~

Nếu cần giữ node gốc để đi tiếp trong đồ thị, dùng `WITH c, c.name AS customerName`. Cú pháp `WITH *` truyền tiếp toàn bộ biến đang nhìn thấy, nhưng trong truy vấn lớn việc liệt kê rõ các biến cần thiết giúp kiểm soát phạm vi và dễ bảo trì hơn.

> Lưu ý nâng cao: các biến được nhập vào một `CALL` subquery có những quy tắc phạm vi riêng. Quy tắc loại biến ở trên áp dụng trực tiếp cho chuỗi mệnh đề thông thường trong các ví dụ của bài.

## 4. Lọc dữ liệu trước và sau `WITH`

`WHERE` ngay sau `MATCH` thường lọc các mẫu vừa tìm được. `WHERE` đi cùng `WITH` có thể lọc luồng hàng ở giai đoạn trung gian, đặc biệt hữu ích sau phép tổng hợp.

Ví dụ chỉ xét đơn đã thanh toán, sau đó tìm khách có tổng tiền từ 200.000:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)-[line:CONTAINS]->(p:Product)
WHERE o.status = 'PAID'
WITH c, sum(line.quantity * p.price) AS totalPaid
WHERE totalPaid >= 200000
RETURN c.id AS customerId, c.name AS customerName, totalPaid
ORDER BY totalPaid DESC;
~~~

Pipeline này có ba bước:

1. `MATCH ... WHERE o.status = 'PAID'` chỉ giữ các dòng hàng thuộc đơn đã thanh toán.
2. `WITH c, sum(...) AS totalPaid` nhóm các hàng theo node khách hàng `c` và tính tổng tiền.
3. `WHERE totalPaid >= 200000` lọc **sau khi đã có tổng**, nên kết quả chỉ có khách hàng Lan với `totalPaid = 250000`.

Nếu lọc nhầm điều kiện về tổng tiền trước khi `sum(...)` được tính, điều kiện sẽ không có biến tổng cần dùng. Ngược lại, lọc trạng thái đơn càng sớm càng giúp giảm số hàng cần cộng.

Có thể dùng `WITH` liên tiếp để tách các phép tính:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS orderCount
WITH c.id AS customerId, c.name AS customerName, orderCount
WHERE orderCount >= 2
RETURN customerId, customerName, orderCount;
~~~

Kết quả từ bộ dữ liệu thử là khách hàng `C01`, Lan, có `2` đơn. Mỗi `WITH` xác định lại các tên biến được mang sang giai đoạn tiếp theo.

## 5. Tổng hợp, nhóm và tránh đếm trùng

`WITH` hỗ trợ các hàm tổng hợp như `count()`, `sum()`, `avg()`, `min()`, `max()` và `collect()`. Khi có hàm tổng hợp, các biểu thức không tổng hợp được chọn cùng nó đóng vai trò **khóa nhóm**.

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS orderCount
RETURN c.id AS customerId, orderCount
ORDER BY customerId;
~~~

Vì `c` được giữ lại nên `count(o)` được tính **theo từng khách hàng**: `C01 = 2`, `C02 = 1`. Nếu chỉ viết `WITH count(o) AS orderCount`, tất cả hàng đầu vào được gom vào một nhóm chung, nên nhận tổng số đơn của cả truy vấn.

### Khi một đơn tạo nhiều hàng

Xét truy vấn đi từ đơn đến sản phẩm:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
WITH
  c,
  count(o) AS lineCount,
  count(DISTINCT o) AS orderCount
RETURN c.id AS customerId, lineCount, orderCount
ORDER BY customerId;
~~~

| Khách hàng | `lineCount` | `orderCount` |
| --- | ---: | ---: |
| `C01` | 3 | 2 |
| `C02` | 1 | 1 |

`count(o)` đếm số **hàng** mang biến `o`; khi một đơn có nhiều sản phẩm, cùng một đơn xuất hiện nhiều lần. `count(DISTINCT o)` chỉ đếm các node đơn khác nhau. Hãy chọn cách đếm dựa trên ý nghĩa của chỉ số, không mặc định rằng một hàng sau `MATCH` luôn tương ứng một đơn.

`WITH DISTINCT` còn có thể khử trùng lặp toàn bộ tổ hợp giá trị được chuyển tiếp:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(:Order)-[:CONTAINS]->(p:Product)
WITH DISTINCT c, p
RETURN c.id AS customerId, p.sku AS productSku
ORDER BY customerId, productSku;
~~~

Mỗi cặp khách hàng–sản phẩm chỉ xuất hiện một lần, dù khách hàng mua cùng sản phẩm ở nhiều đơn.

## 6. Sắp xếp, phân trang và giới hạn hàng trung gian

`WITH` có thể đi cùng `ORDER BY`, `SKIP`, `LIMIT` để chọn những hàng được đưa sang bước tiếp theo. Ví dụ lấy tối đa năm khách có nhiều đơn nhất, rồi lấy danh sách đơn của nhóm đã chọn:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS orderCount
ORDER BY orderCount DESC, c.id ASC
LIMIT 5
MATCH (c)-[:PLACED]->(selectedOrder:Order)
RETURN
  c.id AS customerId,
  orderCount,
  collect(selectedOrder.id) AS orderIds
ORDER BY orderCount DESC, customerId ASC;
~~~

`LIMIT 5` được áp dụng **sau khi đếm số đơn theo khách**, do đó giới hạn số **khách hàng** trước bước `MATCH` thứ hai. Nếu đặt giới hạn ngay sau những hàng đơn riêng lẻ và trước `count()`, phép đếm chỉ xét phần dữ liệu đã bị cắt và có thể cho kết quả khác.

Để phân trang ổn định, nên dùng `ORDER BY` với khóa phụ có tính phân biệt, chẳng hạn `c.id`, trước `SKIP` và `LIMIT`:

~~~cypher
MATCH (c:Customer)
WITH c
ORDER BY c.id
SKIP 0
LIMIT 10
RETURN c.id AS customerId, c.name AS customerName
ORDER BY customerId;
~~~

`SKIP 0` nghĩa là chưa bỏ hàng nào; khi lấy trang tiếp theo có thể thay bằng `SKIP 10`. Với dữ liệu lớn hoặc thay đổi liên tục, phân trang theo khóa (keyset pagination) có thể ổn định và hiệu quả hơn việc tăng `SKIP` liên tục.

**Thứ tự của danh sách tổng hợp** cần chú ý riêng. `ORDER BY` trong `WITH` bảo đảm mệnh đề ngay sau nhận hàng theo thứ tự đã sắp; nếu muốn `collect()` nhận đơn theo `id`:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, o
ORDER BY o.id
WITH c, collect(o.id) AS orderedOrderIds
RETURN c.id AS customerId, orderedOrderIds
ORDER BY customerId;
~~~

Chỉ `ORDER BY` ở `RETURN` cuối cùng sẽ sắp xếp **hàng kết quả**, không tự sắp xếp các phần tử đã nằm trong một danh sách `collect()`.

## 7. Từ hàng đến danh sách và trở lại với `UNWIND`

Một pipeline thường cần tập hợp kết quả ở một bước rồi mở danh sách để xử lý từng phần tử ở bước sau:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c.id AS customerId, collect(o.id) AS orderIds
UNWIND orderIds AS orderId
RETURN customerId, orderId
ORDER BY customerId, orderId;
~~~

Ở đây `collect(o.id)` tạo danh sách `orderIds` cho mỗi khách; `UNWIND` biến mỗi phần tử của danh sách thành một hàng. Mục đích minh họa là quá trình **hàng → danh sách → hàng**. Trong một truy vấn thực tế không cần tổng hợp, bỏ qua vòng `collect()/UNWIND` sẽ thường đơn giản hơn.

`WITH` cũng hữu ích khi **chuẩn hóa dữ liệu nhập** trước `MERGE`. Giả sử ứng dụng truyền tham số `$orders` là danh sách object với `customerId` và `orderId`:

~~~cypher
UNWIND $orders AS raw
WITH
  trim(raw.customerId) AS customerId,
  trim(raw.orderId) AS orderId
WHERE
  customerId IS NOT NULL AND customerId <> ''
  AND orderId IS NOT NULL AND orderId <> ''
MERGE (c:Customer {id: customerId})
MERGE (o:Order {id: orderId})
MERGE (c)-[:PLACED]->(o);
~~~

Ví dụ `$orders` có thể là `[{customerId: 'C01', orderId: 'O04'}]` được truyền dưới dạng tham số từ Java Driver hoặc lớp truy cập dữ liệu trong Spring Data Neo4j. `WITH` đặt tên cho hai giá trị đã `trim()`; `WHERE` loại các hàng thiếu ID; các `MERGE` phía sau chỉ dùng dữ liệu đã chuẩn hóa. Trong hệ thống thực, nên có uniqueness constraint trên các ID và kiểm soát trường hợp dữ liệu đầu vào mâu thuẫn để bảo đảm tính duy nhất.

## 8. Các lỗi và ngộ nhận thường gặp

| Tình huống | Vì sao xảy ra | Cách xử lý |
| --- | --- | --- |
| `Variable ... not defined` ở `RETURN` hoặc `MATCH` sau `WITH` | Biến trước đó không được chuyển tiếp hoặc đã được đổi tên | Liệt kê lại biến trong `WITH`, hoặc sử dụng alias mới |
| Đếm số đơn lớn hơn thực tế | `MATCH` qua `CONTAINS` tạo nhiều hàng cho một đơn | Dùng `count(DISTINCT o)` khi muốn đếm đơn duy nhất |
| Tính tổng sai sau `LIMIT` | Hàng bị cắt trước khi gom nhóm | Xác định rõ cần giới hạn hàng đầu vào hay giới hạn nhóm sau tổng hợp |
| Danh sách `collect()` có thứ tự không như mong đợi | Chỉ sắp xếp hàng ở `RETURN` cuối | Sắp xếp trước mệnh đề thực hiện `collect()` |
| Dùng `WITH *` ở mọi bước | Khó nhận biết biến đang cần và biến vô tình được giữ | Chỉ chuyển những biến và biểu thức cần dùng |
| Tưởng `WITH` tự làm truy vấn nhanh | Hiệu năng phụ thuộc lượng hàng, phép mở rộng đồ thị và kế hoạch truy vấn | Dùng `EXPLAIN`/`PROFILE` để đo, lọc sớm khi không thay đổi ý nghĩa |

Một số nguyên tắc khi tối ưu:

- **Giữ đúng đơn vị dữ liệu**: một hàng có thể là khách hàng, đơn hàng hoặc dòng sản phẩm tùy vị trí `MATCH`. Trước khi dùng `count()`, hãy xác định một hàng biểu diễn gì.
- **Lọc đúng thời điểm**: điều kiện trên thuộc tính đơn như `o.status` thường đặt sớm; điều kiện trên giá trị tổng hợp như `totalPaid` đặt sau `WITH` tính tổng.
- **Giảm dữ liệu trung gian có chủ đích**: chọn cột, `DISTINCT`, hoặc `LIMIT` khi phù hợp với kết quả cần tìm. `collect()` quá lớn có thể tốn bộ nhớ.
- **Đọc execution plan**: dùng `EXPLAIN` để xem kế hoạch dự kiến và `PROFILE` để quan sát số hàng thực tế qua các toán tử. Không giả định mỗi `WITH` tương ứng một lần vật lý hóa dữ liệu.

## 9. Bài thực hành

**Yêu cầu:** Từ đồ thị minh họa, trả về ID, tên và số đơn của khách có ít nhất hai đơn. Sắp xếp theo số đơn giảm dần, nếu bằng nhau thì theo ID tăng dần. Sử dụng `WITH` để tính và lọc số đơn.

**Gợi ý lời giải:**

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WITH c, count(o) AS orderCount
WHERE orderCount >= 2
RETURN
  c.id AS customerId,
  c.name AS customerName,
  orderCount
ORDER BY orderCount DESC, customerId ASC;
~~~

Với bộ dữ liệu ở phần 2, kết quả kỳ vọng là một hàng: `customerId = 'C01'`, `customerName = 'Lan'`, `orderCount = 2`.

**Tự kiểm tra:** Nếu thay `WITH c, count(o) AS orderCount` bằng `WITH count(o) AS orderCount` thì bạn còn trả được tên khách hàng không? Vì sao? Câu trả lời: **không**, vì `c` không được giữ làm khóa nhóm và cũng không được chuyển tiếp; phép đếm lúc này tính chung trên tất cả hàng đầu vào.

## Ghi nhớ

`WITH` là công cụ định hình **luồng dữ liệu và phạm vi biến** trong Cypher. Hãy nghĩ theo trình tự: bước hiện tại tạo những hàng nào, bước sau cần giữ biến gì, có cần đổi tên, gom nhóm hoặc lọc hàng trước khi tiếp tục đi qua đồ thị hay không. Kiểm soát tốt những điểm này giúp truy vấn Neo4j dễ hiểu, trả đúng kết quả và thuận tiện để tối ưu bằng `EXPLAIN`/`PROFILE`.

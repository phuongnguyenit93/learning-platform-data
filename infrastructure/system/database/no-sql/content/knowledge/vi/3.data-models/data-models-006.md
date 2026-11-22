# So sánh cách biểu diễn cùng một nghiệp vụ trong bốn mô hình NoSQL

Trong NoSQL, **cùng một nghiệp vụ có thể được biểu diễn bằng nhiều cấu trúc dữ liệu khác nhau**. Điểm khác biệt không chỉ là dữ liệu trông như JSON, bảng hay đồ thị: mỗi mô hình xác định cách tìm dữ liệu, cách nhóm dữ liệu được đọc cùng nhau, phạm vi cập nhật và chi phí khi yêu cầu nghiệp vụ thay đổi.

Bài này dùng **duy nhất một ví dụ cửa hàng trực tuyến** để đặt cạnh nhau bốn mô hình NoSQL phổ biến:

1. **Key–value (khóa–giá trị)**.
2. **Document (tài liệu)**.
3. **Wide-column / column-family (cột rộng, họ cột)**.
4. **Graph (đồ thị)**.

Mục tiêu là trả lời: Nếu cùng quản lý khách hàng, sản phẩm và đơn hàng, dữ liệu sẽ được lưu thế nào trong mỗi mô hình? Khi đọc đơn, xem lịch sử mua hàng, cập nhật trạng thái hoặc tìm các mối liên hệ, chúng ta phải làm gì và đánh đổi điều gì?

## 1. Một nghiệp vụ, một bộ dữ liệu, một nhóm yêu cầu

Giả sử cửa hàng có:

- **Khách hàng:** \`U42\` — Nguyễn Lan.
- **Sản phẩm:** \`P101\` — Tai nghe, giá hiện tại 450.000 VND; \`P205\` — Cáp sạc, giá hiện tại 100.000 VND.
- **Đơn hàng:** \`O900\` thuộc \`U42\`, tạo lúc \`2026-11-14T02:30:00Z\`, trạng thái \`PENDING\`.
- **Dòng hàng 1:** 2 chiếc \`P101\`, đơn giá tại thời điểm mua 450.000 VND.
- **Dòng hàng 2:** 1 chiếc \`P205\`, đơn giá tại thời điểm mua 100.000 VND.
- **Tổng tiền:** \`2 × 450.000 + 1 × 100.000 = 1.000.000 VND\`.

Sản phẩm có thể đổi giá sau này, nhưng giá trong đơn hàng đã đặt phải phản ánh **giá chốt tại thời điểm mua**. Đây là một quyết định nghiệp vụ sẽ ảnh hưởng đến cả bốn mô hình.

### Những yêu cầu cần đáp ứng

| Mã | Yêu cầu nghiệp vụ | Kiểu truy cập chính |
| --- | --- | --- |
| Q1 | Lấy chi tiết đơn \`O900\`, gồm các mặt hàng và giá lúc đặt | Truy cập theo \`orderId\` |
| Q2 | Liệt kê 10 đơn mới nhất của \`U42\` | Truy cập theo \`customerId\`, sắp xếp thời gian |
| Q3 | Cập nhật \`O900\` từ \`PENDING\` sang \`PAID\`, không thanh toán lặp | Ghi có điều kiện, cần tính đúng |
| Q4 | Hiển thị thông tin sản phẩm \`P101\` đang bán | Truy cập theo \`productId\` |
| Q5 | Tìm sản phẩm thường được mua cùng \`P101\` | Tổng hợp mối quan hệ giữa các đơn và sản phẩm |

Q1–Q4 đại diện cho nghiệp vụ vận hành hàng ngày. Q5 là yêu cầu khám phá quan hệ, giúp thấy khác biệt rõ hơn giữa các mô hình.

Sơ đồ khái niệm, **chưa gắn với bất kỳ hệ quản trị nào**:

~~~mermaid
flowchart LR
    U["Khách hàng U42"] -->|"đặt"| O["Đơn hàng O900"]
    O -->|"2 chiếc, 450.000/chiếc"| P1["Sản phẩm P101"]
    O -->|"1 chiếc, 100.000/chiếc"| P2["Sản phẩm P205"]
~~~

Quan hệ trên là sự thật nghiệp vụ; không bắt buộc CSDL phải có bảng quan hệ hoặc khóa ngoại vật lý. Mỗi mô hình sẽ chọn cách biểu diễn khác nhau.

## 2. Mô hình key–value: xác định khóa trước, lấy giá trị sau

### 2.1. Cách biểu diễn

Trong key–value store, đơn vị truy cập cơ bản là cặp **key → value**. Key định danh duy nhất một mục dữ liệu; value có thể là chuỗi, số, blob hoặc một tài liệu được tuần tự hóa, tùy sản phẩm CSDL.

Một cách tổ chức đơn giản:

~~~text
customer:U42
  -> {"id":"U42","name":"Nguyễn Lan"}

product:P101
  -> {"id":"P101","name":"Tai nghe","currentPrice":450000}

product:P205
  -> {"id":"P205","name":"Cáp sạc","currentPrice":100000}

order:O900
  -> {
       "id":"O900",
       "customerId":"U42",
       "createdAt":"2026-11-14T02:30:00Z",
       "status":"PENDING",
       "totalVnd":1000000,
       "lines":[
         {"productId":"P101","qty":2,"unitPriceVnd":450000},
         {"productId":"P205","qty":1,"unitPriceVnd":100000}
       ]
     }

customer-orders:U42:2026-11
  -> ["O900", "... các orderId khác theo thứ tự mới nhất ..."]
~~~

\`customer-orders:U42:2026-11\` là một **chỉ mục do ứng dụng tự duy trì**: nó cho biết tháng 11/2026 khách hàng có những đơn nào. Đây không phải khả năng tìm kiếm tự động mà mọi key–value store đều cung cấp.

Một số hệ thống như Redis có kiểu sorted set/list hỗ trợ sắp xếp và lấy dải phần tử; một key–value store chỉ hỗ trợ GET/PUT sẽ phải lưu và cập nhật danh sách này dưới dạng một value, hoặc triển khai chỉ mục theo cách khác. Ví dụ bên dưới sử dụng thao tác khái niệm để tránh nhầm lệnh của sản phẩm cụ thể.

### 2.2. Q1 — Xem chi tiết đơn

~~~text
order = GET("order:O900")
RETURN order
~~~

Vì các dòng hàng đã được nhúng trong value của đơn, một lần lấy theo khóa có thể trả về đủ thông tin thanh toán. Nếu giao diện còn cần tên sản phẩm hiện tại, ứng dụng có thể lấy thêm \`product:P101\` và \`product:P205\`.

**Ưu điểm:** Q1 có đường truy cập ngắn, dễ cache và dễ dự đoán.

**Đánh đổi:** Muốn tìm đơn theo điều kiện không có trong key (ví dụ “tất cả đơn \`PAID\` có tổng tiền trên 500.000”) phải xây thêm chỉ mục, quét dữ liệu nếu hệ quản trị hỗ trợ, hoặc dùng một công cụ truy vấn khác.

### 2.3. Q2 — Xem 10 đơn gần nhất của khách

~~~text
ids = GET_ORDER_IDS("customer-orders:U42:2026-11", limit=10)
orders = MULTI_GET(ids.map(id => "order:" + id))
RETURN orders
~~~

Nếu cần đi qua nhiều tháng, ứng dụng phải lấy dữ liệu từ các bucket tháng phù hợp và gộp kết quả theo thời gian. Nếu chỉ lưu một danh sách vô hạn cho khách hàng, value có thể lớn, cập nhật tranh chấp và phân trang khó.

### 2.4. Q3 — Đổi trạng thái đơn

~~~text
old = GET("order:O900")
IF old.status == "PENDING":
    new = old with status = "PAID"
    COMPARE_AND_SET("order:O900", expectedVersion=old.version, value=new)
~~~

Đây là **mã giả**: \`COMPARE_AND_SET\` chỉ dùng được nếu hệ thống hỗ trợ thao tác cập nhật có điều kiện, versioning hoặc cơ chế tương đương. Cách \`GET\` rồi \`PUT\` đơn thuần có thể làm hai request thanh toán cùng ghi, dẫn tới race condition. Với nghiệp vụ trả tiền, còn cần idempotency key, xác thực giao dịch và quy tắc xử lý trạng thái độc lập với CSDL.

Nếu thao tác thay đổi đồng thời cả \`order:O900\` và một chỉ mục \`orders-by-status:PAID\`, phải xác định cách giữ chúng nhất quán. Một số sản phẩm hỗ trợ giao dịch đa khóa trong phạm vi nhất định, một số không.

### 2.5. Q5 — Sản phẩm mua cùng

Key–value store không tự hiểu \`P101\` có liên hệ với những \`Product\` nào qua các đơn hàng. Một cách tối ưu khi đọc thường xuyên là duy trì giá trị đã tổng hợp:

~~~text
frequently-bought-with:P101
  -> [{"productId":"P205","coPurchaseCount":125}, ...]
~~~

Giá trị này cần pipeline cập nhật sau khi đơn được xác nhận, có quy tắc xử lý đơn hủy/trả hàng và chấp nhận độ trễ cập nhật nếu xử lý bất đồng bộ.

**Tư duy mô hình hóa key–value:** Thiết kế **key theo thao tác đọc/ghi đã biết trước**; thêm khóa phụ hoặc chỉ mục tự duy trì cho truy vấn khác. Rất phù hợp cho tra cứu theo định danh, session, cache và trạng thái đơn giản; truy vấn tổ hợp tự do thường cần cơ chế bổ sung.

## 3. Mô hình document: gom dữ liệu thường được dùng cùng nhau

### 3.1. Cách biểu diễn

Document database lưu tài liệu có cấu trúc lồng nhau, điển hình là JSON-like/BSON. Ta có thể tạo các collection \`customers\`, \`products\` và \`orders\`.

Ví dụ tài liệu trong \`orders\`:

~~~json
{
  "_id": "O900",
  "customerId": "U42",
  "createdAt": "2026-11-14T02:30:00Z",
  "status": "PENDING",
  "totalVnd": 1000000,
  "lines": [
    {
      "productId": "P101",
      "nameAtPurchase": "Tai nghe",
      "quantity": 2,
      "unitPriceVnd": 450000
    },
    {
      "productId": "P205",
      "nameAtPurchase": "Cáp sạc",
      "quantity": 1,
      "unitPriceVnd": 100000
    }
  ]
}
~~~

\`customerId\` và \`productId\` là **tham chiếu logic**. Các dòng hàng \`lines\` là dữ liệu **nhúng (embedded)** vào đơn. Tên và đơn giá tại thời điểm mua được lưu như snapshot để dữ liệu lịch sử không thay đổi khi danh mục sản phẩm thay đổi.

Tài liệu sản phẩm riêng:

~~~json
{
  "_id": "P101",
  "name": "Tai nghe",
  "currentPriceVnd": 450000,
  "active": true
}
~~~

### 3.2. Q1 — Xem chi tiết đơn

Với cú pháp minh họa theo MongoDB:

~~~javascript
db.orders.findOne({ _id: "O900" });
~~~

Thông tin đơn và dòng hàng có thể được đọc trong một tài liệu. Cấu trúc này gần với dữ liệu mà API chi tiết đơn cần trả về.

Đổi lại, nếu nhúng mọi thứ vào tài liệu — hàng nghìn sự kiện giao vận, lịch sử thanh toán, tất cả đánh giá — tài liệu có thể tăng không giới hạn, đọc thừa và gây tranh chấp cập nhật. Chỉ nên nhúng dữ liệu có kích thước và vòng đời phù hợp.

### 3.3. Q2 — Xem lịch sử mua hàng

~~~javascript
db.orders
  .find({ customerId: "U42" }, { _id: 1, createdAt: 1, status: 1, totalVnd: 1 })
  .sort({ createdAt: -1, _id: -1 })
  .limit(10);
~~~

Với workload này, một chỉ mục dạng \`{ customerId: 1, createdAt: -1, _id: -1 }\` thường là ứng viên phù hợp. Chỉ mục cụ thể phải được kiểm tra với kế hoạch truy vấn và sản phẩm sử dụng.

Document store cho phép truy vấn dựa trên trường, nhưng **không có nghĩa mọi điều kiện lọc và sắp xếp đều nhanh**. Truy vấn thiếu chỉ mục hoặc truy vấn cần tổng hợp lớn vẫn có thể tốn kém.

### 3.4. Q3 — Đổi trạng thái có điều kiện

~~~javascript
const result = db.orders.updateOne(
  { _id: "O900", status: "PENDING" },
  { $set: { status: "PAID" } }
);

// Kiểm tra result.matchedCount/result.modifiedCount
// để phân biệt chuyển trạng thái thành công hay trạng thái đã thay đổi.
~~~

Ví dụ dùng cập nhật có điều kiện để tránh hai lần cùng chuyển một đơn từ \`PENDING\` sang \`PAID\`. Trong các sản phẩm hỗ trợ atomic update trên một tài liệu, ranh giới cập nhật này là một lợi thế của việc đặt trạng thái đơn cùng thông tin đơn. Nếu phải đồng thời cập nhật tồn kho và thanh toán tại các tài liệu khác nhau, cần dùng giao dịch phù hợp hoặc quy trình phối hợp nghiệp vụ; không thể suy ra tính nguyên tử đa tài liệu từ một lệnh \`updateOne\`.

### 3.5. Q5 — Sản phẩm thường mua cùng

Vì \`orders.lines\` chứa danh sách sản phẩm, có thể xử lý bằng aggregation: lọc những đơn đã hoàn tất có \`P101\`, mở rộng các phần tử \`lines\`, loại \`P101\`, nhóm theo \`productId\` và đếm. Cách này có thể tận dụng index ban đầu, nhưng quy mô quét, dung lượng trung gian và chi phí tổng hợp sẽ tăng khi dữ liệu lớn.

Nếu Q5 được gọi liên tục, có thể cần **bảng/tài liệu tổng hợp trước** hoặc pipeline phân tích riêng, thay vì chạy lại toàn bộ lịch sử mua hàng mỗi lần hiển thị.

**Tư duy mô hình hóa document:** Chọn **ranh giới tài liệu theo những phần thường được đọc và cập nhật cùng nhau**. Mô hình này thuận tiện cho đối tượng nghiệp vụ có cấu trúc lồng nhau và thuộc tính thay đổi, nhưng vẫn cần chỉ mục, giới hạn kích thước, kiểm soát dữ liệu trùng và thiết kế giao dịch.

## 4. Mô hình wide-column: thiết kế bảng theo truy vấn và khóa phân vùng

### 4.1. Wide-column là gì?

Trong các hệ kiểu Apache Cassandra, ScyllaDB, dữ liệu được tổ chức thành bảng với **partition key** và **clustering columns**. Các hàng cùng partition key có thể được đặt gần nhau theo trật tự clustering để đáp ứng truy vấn theo khóa và khoảng.

Điều này **khác với hệ cơ sở dữ liệu phân tích dạng columnar** như kho dữ liệu đọc từng cột trên nhiều hàng. Từ “wide-column” trong bối cảnh NoSQL nhấn mạnh mô hình bảng phân vùng/họ cột và thiết kế theo đường truy cập; không mặc định nghĩa là truy vấn phân tích theo bất kỳ cột nào cũng nhanh.

Trong mô hình này, chúng ta có thể chủ động tạo **nhiều bảng chứa dữ liệu trùng nhau** để mỗi câu truy vấn quan trọng có một đường đọc hiệu quả.

### 4.2. Cách biểu diễn cùng đơn hàng

Ví dụ CQL mang tính minh họa (theo hướng Cassandra):

~~~sql
-- Q1: lấy thông tin chính của đơn theo orderId
CREATE TABLE order_by_id (
    order_id text PRIMARY KEY,
    customer_id text,
    created_at timestamp,
    status text,
    total_vnd bigint
);

-- Q1: lấy các dòng hàng thuộc cùng một order
CREATE TABLE order_lines_by_order (
    order_id text,
    line_no int,
    product_id text,
    name_at_purchase text,
    quantity int,
    unit_price_vnd bigint,
    PRIMARY KEY ((order_id), line_no)
);

-- Q2: liệt kê đơn theo khách hàng và tháng, mới nhất trước
CREATE TABLE orders_by_customer_month (
    customer_id text,
    month_bucket text,
    created_at timestamp,
    order_id text,
    status text,
    total_vnd bigint,
    PRIMARY KEY ((customer_id, month_bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);

-- Q4: lấy sản phẩm theo ID
CREATE TABLE product_by_id (
    product_id text PRIMARY KEY,
    name text,
    current_price_vnd bigint,
    active boolean
);
~~~

Một đơn \`O900\` được lưu ở **nhiều biểu diễn**:

~~~text
order_by_id
  order_id=O900 -> customer_id=U42, status=PENDING, total=1000000

order_lines_by_order
  partition: order_id=O900
    line_no=1 -> P101, quantity=2, unit_price=450000
    line_no=2 -> P205, quantity=1, unit_price=100000

orders_by_customer_month
  partition: (customer_id=U42, month_bucket=2026-11)
    (2026-11-14T02:30:00Z, O900) -> status=PENDING, total=1000000
~~~

Lưu trạng thái \`PENDING\` trong cả \`order_by_id\` lẫn \`orders_by_customer_month\` giúp Q1 và Q2 truy cập nhanh, nhưng làm phát sinh **chi phí giữ bản sao nhất quán** khi trạng thái đổi.

### 4.3. Q1 — Đọc một đơn

~~~sql
SELECT * FROM order_by_id WHERE order_id = 'O900';

SELECT *
FROM order_lines_by_order
WHERE order_id = 'O900';
~~~

Hai truy vấn tìm đúng partition key, có thể hoạt động hiệu quả với kích thước partition phù hợp. Ứng dụng kết hợp kết quả thành một DTO/API response.

### 4.4. Q2 — Đọc các đơn mới nhất của khách

~~~sql
SELECT order_id, created_at, status, total_vnd
FROM orders_by_customer_month
WHERE customer_id = 'U42' AND month_bucket = '2026-11'
LIMIT 10;
~~~

Clustering order đã lưu các hàng mới nhất lên trước trong partition tháng. Nếu tháng hiện tại có ít hơn 10 đơn, ứng dụng phải truy vấn thêm tháng trước và gộp kết quả.

**Tại sao có \`month_bucket\`?** Nếu một khách hàng có hàng triệu đơn, gom toàn bộ vào một partition có thể gây partition rất lớn và khó vận hành. Phân bucket theo tháng là một khả năng cân nhắc; kích thước bucket đúng phải dựa trên tần suất, thời gian và tải thực tế. Một khách hàng mua cực nhiều có thể cần bucket nhỏ hơn; khách hàng ít mua có thể không cần bucket.

Không nên kỳ vọng truy vấn dạng:

~~~sql
-- Minh họa cách truy vấn không phù hợp với khóa của bảng trên:
SELECT * FROM orders_by_customer_month
WHERE status = 'PAID';
~~~

chạy tốt mà không có thiết kế bổ sung. Với Cassandra-like CQL, thường cần một bảng khác theo \`status\` nếu đây là truy vấn nghiệp vụ quan trọng, hoặc dùng hệ tìm kiếm/phân tích phù hợp.

### 4.5. Q3 — Cập nhật trạng thái và dữ liệu trùng lặp

Trong dữ liệu này, trạng thái xuất hiện ở hai bảng. Việc đổi từ \`PENDING\` sang \`PAID\` đặt ra hai vấn đề:

1. **Điều kiện nghiệp vụ:** chỉ chuyển khi đơn vẫn ở \`PENDING\`. Có thể cân nhắc conditional update/lightweight transaction ở bảng có trách nhiệm giữ trạng thái gốc nếu sản phẩm hỗ trợ, với chi phí và phạm vi áp dụng cụ thể.
2. **Đồng bộ các biểu diễn truy vấn:** thông tin trong bảng lịch sử theo khách cũng phải được cập nhật, qua luồng ghi phối hợp, sự kiện, hoặc cơ chế xử lý lại an toàn khi có lỗi.

Không nên giả định hai câu lệnh \`UPDATE\` trên hai partition/bảng tự động có tính nguyên tử như một transaction SQL. Tùy công nghệ, batch write có thể giúp nhóm thao tác ghi nhưng **không tương đương một giao dịch ACID đa bản ghi nói chung**.

Một lựa chọn khác là chỉ lưu \`orderId\` và thời gian trong bảng \`orders_by_customer_month\`, sau đó lấy trạng thái từ \`order_by_id\`. Cách này giảm bản sao trạng thái nhưng tăng round trip khi Q2 cần hiển thị trạng thái của từng đơn. Đây là đánh đổi giữa **chi phí đọc** và **chi phí đồng bộ khi ghi**.

### 4.6. Q5 — Sản phẩm mua cùng

Bảng hiện tại tối ưu theo \`orderId\` và \`customerId\`, chưa tối ưu truy vấn ngược “các đơn chứa \`P101\`”. Có thể xây thêm bảng như \`order_lines_by_product\` với partition/bucket theo \`productId\`, hoặc thực hiện phân tích từ luồng sự kiện đơn hàng rồi lưu kết quả \`co_purchase_by_product\`.

Nếu sản phẩm \`P101\` bán rất chạy, một partition chỉ theo \`productId\` dễ trở thành partition nóng/rất lớn. Cần xét thêm bucket thời gian, shard và cách tổng hợp.

**Tư duy mô hình hóa wide-column:** **Viết danh sách truy vấn trước rồi thiết kế partition/clustering key cho từng truy vấn chủ đạo**. Tốc độ truy cập theo khóa có thể rất tốt, nhưng truy vấn bất ngờ và cập nhật nhiều biểu diễn dễ phức tạp.

## 5. Mô hình graph: lưu thực thể và quan hệ làm dữ liệu hạng nhất

### 5.1. Cách biểu diễn

Graph database thường dùng **node (đỉnh)**, **relationship/edge (cạnh)** và **property (thuộc tính)**. Thay vì nhúng toàn bộ quan hệ vào một đơn hoặc dựng nhiều chỉ mục thủ công, mô hình này biểu diễn trực tiếp hành động “khách đặt đơn”, “đơn có dòng hàng”, “dòng hàng trỏ tới sản phẩm”.

Đề xuất các loại đỉnh:

- \`Customer {id, name}\`
- \`Order {id, createdAt, status, totalVnd}\`
- \`OrderLine {id, lineNo, quantity, unitPriceVnd, nameAtPurchase}\`
- \`Product {id, name, currentPriceVnd}\`

Và các loại cạnh:

- \`(Customer)-[:PLACED]->(Order)\`
- \`(Order)-[:HAS_LINE]->(OrderLine)\`
- \`(OrderLine)-[:FOR_PRODUCT]->(Product)\`

~~~mermaid
flowchart LR
    U["Customer U42"] -->|PLACED| O["Order O900"]
    O -->|HAS_LINE| L1["OrderLine O900-1<br/>qty=2, price=450000"]
    O -->|HAS_LINE| L2["OrderLine O900-2<br/>qty=1, price=100000"]
    L1 -->|FOR_PRODUCT| P1["Product P101"]
    L2 -->|FOR_PRODUCT| P2["Product P205"]
~~~

Với nghiệp vụ đơn giản, có thể lưu \`quantity\` và \`unitPriceVnd\` trên cạnh \`CONTAINS\` từ Order đến Product. Tuy nhiên, dùng đỉnh \`OrderLine\` riêng giúp biểu diễn mã dòng hàng, lịch sử giá, hoàn tiền theo dòng và các thuộc tính phát triển về sau. Đó là lựa chọn thiết kế, không phải một yêu cầu bắt buộc của mọi graph database.

### 5.2. Tạo dữ liệu minh họa

Ví dụ Cypher theo phong cách Neo4j:

~~~cypher
CREATE (u:Customer {id: 'U42', name: 'Nguyễn Lan'})
CREATE (p1:Product {id: 'P101', name: 'Tai nghe', currentPriceVnd: 450000})
CREATE (p2:Product {id: 'P205', name: 'Cáp sạc', currentPriceVnd: 100000})
CREATE (o:Order {
  id: 'O900',
  createdAt: datetime('2026-11-14T02:30:00Z'),
  status: 'PENDING',
  totalVnd: 1000000
})
CREATE (l1:OrderLine {
  id: 'O900-1', lineNo: 1, quantity: 2,
  unitPriceVnd: 450000, nameAtPurchase: 'Tai nghe'
})
CREATE (l2:OrderLine {
  id: 'O900-2', lineNo: 2, quantity: 1,
  unitPriceVnd: 100000, nameAtPurchase: 'Cáp sạc'
})
CREATE (u)-[:PLACED]->(o)
CREATE (o)-[:HAS_LINE]->(l1)
CREATE (o)-[:HAS_LINE]->(l2)
CREATE (l1)-[:FOR_PRODUCT]->(p1)
CREATE (l2)-[:FOR_PRODUCT]->(p2);
~~~

Lệnh này **chỉ minh họa cách biểu diễn**, giả sử một cơ sở dữ liệu thử nghiệm đang rỗng. Trong hệ thống thực tế, cần thiết lập ràng buộc duy nhất/index cho ID và dùng \`MERGE\` hoặc thao tác tạo có kiểm tra thích hợp để không tạo trùng khi request chạy lại.

### 5.3. Q1 — Xem đơn và các mặt hàng

~~~cypher
MATCH (o:Order {id: 'O900'})-[:HAS_LINE]->(line:OrderLine)
MATCH (line)-[:FOR_PRODUCT]->(p:Product)
RETURN o.id AS orderId, o.status AS status,
       line.lineNo AS lineNo, line.quantity AS quantity,
       line.unitPriceVnd AS purchasePrice, p.id AS productId
ORDER BY lineNo;
~~~

Truy vấn đi từ một đơn được tìm qua ID, rồi **traverse** các cạnh tới các dòng hàng/sản phẩm. Dữ liệu có tính quan hệ được biểu diễn tường minh; đổi lại, với thao tác chỉ cần một đối tượng đơn hàng nhỏ, nó có thể đòi hỏi nhiều bước duyệt quan hệ hơn so với một document đã nhúng sẵn \`lines\`.

### 5.4. Q2 — Xem lịch sử mua hàng

~~~cypher
MATCH (u:Customer {id: 'U42'})-[:PLACED]->(o:Order)
RETURN o.id AS orderId, o.createdAt AS createdAt,
       o.status AS status, o.totalVnd AS totalVnd
ORDER BY createdAt DESC
LIMIT 10;
~~~

Graph thể hiện quan hệ \`Customer → Order\` rõ ràng; tuy nhiên với khách hàng có số đơn rất lớn, chi phí duyệt rồi sắp xếp có thể đáng kể. Cần quan sát thực tế, lập chỉ mục hoặc thiết kế đường truy cập chuyên biệt nếu Q2 là luồng nóng.

### 5.5. Q3 — Chuyển trạng thái an toàn

~~~cypher
MATCH (o:Order {id: 'O900', status: 'PENDING'})
SET o.status = 'PAID'
RETURN o.id AS orderId, o.status AS newStatus;
~~~

Đây là ví dụ cú pháp cập nhật theo điều kiện, **không tự nó chứng minh an toàn chống chạy đồng thời trong mọi tình huống**. Với thanh toán, cần cơ chế transaction/locking/optimistic concurrency mà sản phẩm cung cấp, ràng buộc nghiệp vụ và idempotency key. Cũng phải xử lý việc một request thấy không có dòng phù hợp vì đơn đã thanh toán hay vì đơn không tồn tại.

### 5.6. Q5 — Tìm sản phẩm thường được mua cùng

Đây là trường hợp graph thể hiện thế mạnh: đi từ sản phẩm \`P101\` qua các dòng hàng, các đơn chứa nó, rồi tới những sản phẩm khác trong cùng đơn.

~~~cypher
MATCH (target:Product {id: 'P101'})<-[:FOR_PRODUCT]-(a:OrderLine)
      <-[:HAS_LINE]-(o:Order)-[:HAS_LINE]->(b:OrderLine)
      -[:FOR_PRODUCT]->(other:Product)
WHERE other.id <> target.id AND o.status = 'PAID'
RETURN other.id AS productId,
       other.name AS productName,
       count(DISTINCT o) AS ordersBoughtTogether
ORDER BY ordersBoughtTogether DESC
LIMIT 10;
~~~

Ở đây, \`count(DISTINCT o)\` đếm **số đơn có cả hai sản phẩm**, không phải tổng số chiếc được bán. Nếu một đơn có nhiều dòng cho cùng sản phẩm, \`DISTINCT\` tránh đếm trùng đơn.

Graph thuận tiện khi truy vấn yêu cầu **nhiều bước quan hệ thay đổi linh hoạt**, ví dụ khách nào cùng mua bộ sản phẩm, sản phẩm được gợi ý qua nhiều cấp, tuyến đường liên kết, quyền truy cập phụ thuộc chuỗi quan hệ. Nhưng duyệt qua các node có bậc cạnh rất lớn hoặc mở rộng không giới hạn vẫn có thể tốn tài nguyên. Không mặc định graph luôn nhanh hơn cho mọi truy vấn.

**Tư duy mô hình hóa graph:** Xác định **thực thể, loại quan hệ và đường đi truy vấn**. Phù hợp khi quan hệ là trọng tâm của sản phẩm và cần duyệt nhiều bước; truy cập đơn thuần theo khóa có thể không cần độ phức tạp này.

## 6. Đặt bốn biểu diễn cạnh nhau

### 6.1. Hình dạng dữ liệu

| Khía cạnh | Key–value | Document | Wide-column | Graph |
| --- | --- | --- | --- | --- |
| Đơn vị dữ liệu chính | Key → value | Document có trường và mảng | Row trong partition, sắp theo clustering key | Node và relationship có thuộc tính |
| Biểu diễn \`O900\` | Value tại \`order:O900\` | Document \`orders._id = O900\` | Hàng \`order_by_id\` + các dòng \`order_lines_by_order\` | Node \`Order\` nối tới \`OrderLine\` |
| Biểu diễn \`U42\` đã đặt \`O900\` | Chỉ mục/danh sách khóa phụ | Trường \`customerId\` trong đơn | Bảng \`orders_by_customer_month\` | Cạnh \`PLACED\` |
| Biểu diễn sản phẩm thuộc đơn | Mảng trong value | Mảng \`lines\` lồng nhau | Các hàng cùng partition \`order_id\` | \`OrderLine -[:FOR_PRODUCT]-> Product\` |
| Chạy Q2 nhanh | Khóa chỉ mục tự duy trì | Chỉ mục trên \`customerId\`, \`createdAt\` | Bảng theo \`customerId\` + bucket + clustering | Duyệt cạnh từ Customer, tối ưu truy vấn nếu cần |
| Chạy Q5 | Tạo dữ liệu tổng hợp phụ | Aggregation hoặc tổng hợp trước | Bảng truy vấn bổ sung/pipeline tổng hợp | Duyệt đường quan hệ và đếm |
| Khó khăn chính | Truy vấn ngoài khóa và đồng bộ chỉ mục | Tài liệu phình to, index, ranh giới cập nhật | Nhiều bảng theo truy vấn, duplicate write, partition nóng | Supernode, truy vấn duyệt lớn, độ phức tạp vận hành |

**Lưu ý:** Bảng so sánh là mức **mô hình khái niệm**, không phải cam kết tính năng hoặc benchmark của mọi sản phẩm. Redis, DynamoDB, MongoDB, Cassandra, Neo4j... có khả năng giao dịch, index, TTL, tìm kiếm và cơ chế phân tán khác nhau; cần kiểm tra hệ cụ thể trước khi triển khai.

### 6.2. So sánh qua từng tình huống

| Yêu cầu | Thiết kế thường thuận lợi | Lý do |
| --- | --- | --- |
| Q1: lấy đơn theo ID | Key–value, document; wide-column với partition \`orderId\` | Đường truy cập xác định trước, dữ liệu của đơn nằm gần nhau |
| Q2: lịch sử mua có sắp xếp | Document có index; wide-column có clustering; key–value có index phụ | Truy vấn theo khách và thời gian cần tổ chức/đánh chỉ mục theo đúng điều kiện |
| Q3: cập nhật trạng thái | Mô hình có ranh giới cập nhật và điều kiện phù hợp | Cần an toàn với ghi đồng thời, tránh retry gây thao tác lặp |
| Q4: lấy sản phẩm theo ID | Cả bốn nếu có tra cứu ID phù hợp | Đây là bài toán đơn giản, chưa phải lý do quyết định chọn graph hay document |
| Q5: sản phẩm mua cùng | Graph thường biểu diễn đường quan hệ tự nhiên; các mô hình khác có thể tổng hợp trước | Độ phức tạp đến từ số bước nối giữa đơn và sản phẩm, tần suất truy vấn và quy mô dữ liệu |

Không nên hiểu dòng “thường thuận lợi” là kết luận hiệu năng. Ví dụ, bảng aggregate đã tính trước trong key–value có thể trả Q5 cực nhanh; đổi lại hệ thống phải trả chi phí tính toán, đồng bộ và làm mới dữ liệu.

## 7. Theo dõi một thay đổi nghiệp vụ qua bốn mô hình

Giả sử cửa hàng **đổi giá hiện tại của \`P101\` từ 450.000 lên 470.000 VND**. Đơn \`O900\` đã lập **vẫn có đơn giá 450.000 VND**. Mỗi mô hình sẽ thể hiện cùng một quy tắc:

| Mô hình | Cập nhật giá đang bán | Giữ lịch sử đơn |
| --- | --- | --- |
| Key–value | Ghi value \`product:P101\` mới | Value \`order:O900.lines[0].unitPriceVnd\` không đổi |
| Document | Sửa document \`products\` của \`P101\` | \`orders.lines.unitPriceVnd\` là snapshot, không sửa theo |
| Wide-column | Sửa \`product_by_id.current_price_vnd\` | \`order_lines_by_order.unit_price_vnd\` vẫn là giá mua |
| Graph | Sửa property \`Product.currentPriceVnd\` | \`OrderLine.unitPriceVnd\` lưu snapshot riêng |

Nếu chỉ lưu \`productId\` trong đơn và lúc xem đơn luôn lấy \`currentPrice\` của sản phẩm để tính tiền, **cả bốn mô hình đều có thể sai nghiệp vụ**. Mô hình dữ liệu không thay thế việc xác định thuộc tính nào là **trạng thái hiện tại** và thuộc tính nào phải **bất biến theo lịch sử**.

Xét thay đổi khác: “Cho phép xem mọi sản phẩm mà người thân của khách hàng từng mua rồi được họ đánh giá tốt”. Graph có thể nối trực tiếp \`Customer → KNOWS → Customer → PLACED → Order → Product → REVIEW\`. Với ba mô hình còn lại, ta thường cần nhiều lần truy vấn, chỉ mục tổng hợp hoặc pipeline tính trước. Đây là lý do **kiểu câu hỏi mà sản phẩm cần trả lời** có thể quan trọng hơn vẻ ngoài của dữ liệu.

## 8. Cùng một nghiệp vụ nhưng ranh giới nhất quán khác nhau

Khi đặt và thanh toán đơn \`O900\`, không chỉ cần lưu dữ liệu; hệ thống còn phải tuân thủ các bất biến:

- Một \`orderId\` không được tạo hai đơn khác nhau.
- Tổng tiền của đơn phải phù hợp với dòng hàng và chính sách giá đã chốt.
- Một sự kiện thanh toán được xử lý lặp lại không được ghi nhận thành nhiều lần thu tiền.
- Các bản trình bày dùng để đọc lịch sử có thể phải cập nhật khi đơn chuyển trạng thái.

Khả năng thực hiện các bất biến phụ thuộc **tính năng giao dịch cụ thể và ranh giới dữ liệu**, chứ không thể kết luận từ nhãn “NoSQL”.

### 8.1. Phạm vi cập nhật

| Mô hình | Ranh giới thiết kế thường gặp | Điểm cần kiểm tra trên sản phẩm cụ thể |
| --- | --- | --- |
| Key–value | Một hoặc nhiều key | CAS/conditional write, transaction nhiều key, retry và chỉ mục phụ |
| Document | Một document là đơn vị gom dữ liệu tự nhiên | Atomic update, transaction đa document, cách tránh xung đột |
| Wide-column | Một partition/hàng/bảng được thiết kế theo query | Conditional update, batch semantics, consistency level, cập nhật các bản sao logic |
| Graph | Một nhóm node và relationship trong thao tác duyệt | Transaction, khóa/cạnh tranh cập nhật, ràng buộc duy nhất |

**Ví dụ:** Khi đơn đổi từ \`PENDING\` sang \`PAID\`, nếu bảng \`orders_by_customer_month\` chưa cập nhật kịp, Q1 và Q2 có thể tạm hiển thị trạng thái khác nhau. Thiết kế phải nói rõ mức nhất quán yêu cầu, cơ chế đồng bộ, retry và khả năng tự sửa khi pipeline gặp lỗi. Nếu nghiệp vụ yêu cầu đọc ngay lập tức luôn chính xác, không thể chỉ chấp nhận bất đồng bộ theo mặc định.

### 8.2. Đừng đồng nhất “denormalization” với “dữ liệu sai”

Nhúng snapshot giá, lưu danh sách khóa theo khách hoặc tạo bảng \`orders_by_customer_month\` đều là những cách **lặp dữ liệu có chủ đích** để tối ưu đường đọc. Dữ liệu lặp hữu ích khi xác định rõ:

1. **Nguồn sự thật (source of truth):** trường nào quyết định trạng thái cuối cùng?
2. **Cách phát sinh bản sao:** ghi đồng bộ, sự kiện, CDC, batch hay job định kỳ?
3. **Độ trễ chấp nhận:** Q2 được phép chậm cập nhật bao lâu?
4. **Cơ chế sửa lệch:** khi xử lý lỗi, dữ liệu phụ được tái tạo bằng cách nào?

Không có các quy tắc này, cùng một nghiệp vụ có thể trả kết quả trái ngược ở các API khác nhau.

## 9. Chọn mô hình từ workload, không từ tên công nghệ

Để đánh giá thực tế, hãy viết các câu hỏi nghiệp vụ giống Q1–Q5, ghi lượng truy cập, kích thước dữ liệu, phân bố key và thời gian phản hồi mong muốn. Sau đó tính chi phí đường đọc và đường ghi.

Ví dụ bảng quyết định ban đầu:

| Điều kiện nổi bật của hệ thống | Mô hình nên khảo sát trước | Vẫn phải kiểm tra |
| --- | --- | --- |
| Hầu hết request lấy/ghi đối tượng theo ID, cấu trúc value khá đơn giản | Key–value | Chỉ mục phụ, nguyên tử nhiều key, kích thước value, hot key |
| API thường nhận/trả đối tượng lồng nhau, lọc và index theo một số trường | Document | Kích thước tài liệu, tốc độ tăng mảng nhúng, index và giao dịch |
| Lưu lượng lớn, truy vấn lặp lại theo partition key và dải thời gian xác định | Wide-column | Partition size, skew, clustering, số bảng phụ, nhất quán |
| Giá trị sản phẩm nằm ở quan hệ nhiều cấp, truy vấn đường đi đổi thường xuyên | Graph | Bậc node, độ sâu traversal, khả năng mở rộng, index và transaction |

Trong thực tế, **một sản phẩm có thể dùng nhiều mô hình**: document để lưu đơn, key–value để cache giỏ hàng, hệ tìm kiếm cho tìm kiếm sản phẩm, graph để đề xuất quan hệ. Cách này làm tăng khả năng phục vụ từng truy vấn nhưng cũng tăng vận hành, đồng bộ, quyền truy cập và sự cố liên hệ giữa các hệ thống; chỉ nên thêm thành phần khi có nhu cầu rõ ràng.

### Quy trình thiết kế thực dụng

1. **Viết yêu cầu đọc/ghi trước:** chọn 5–10 truy vấn xuất hiện nhiều nhất, xác định khóa, bộ lọc, sort, phân trang và các cập nhật có điều kiện.
2. **Đánh dấu dữ liệu đi cùng nhau:** trường nào luôn xuất hiện trong Q1; trường nào là lịch sử bất biến; trường nào thay đổi với tần suất độc lập?
3. **Vẽ một bản biểu diễn cho từng mô hình ứng viên:** dùng key, document boundary, partition/clustering key hoặc node/edge cụ thể.
4. **Theo dõi một vòng đời thực:** tạo đơn → xem lịch sử → thanh toán → đổi giá sản phẩm → hoàn/huỷ. Liệt kê tất cả nơi phải ghi/cập nhật.
5. **Tính lượng đọc, ghi và kích thước:** số lượt truy vấn cho mỗi API, số byte nhận/trả, số bản sao logic, index và fan-out.
6. **Thử tải sát thực tế:** kiểm tra p95/p99, truy cập khóa nóng, bản ghi lớn, truy vấn nhiều kết quả và lỗi xảy ra giữa các bước ghi.
7. **Chọn dựa trên điều kiện có thể kiểm chứng:** đáp ứng yêu cầu nghiệp vụ, độ trễ, tính đúng đắn, độ phức tạp và khả năng vận hành của đội ngũ.

## 10. Các lỗi mô hình hóa dễ mắc

**Lỗi 1 — Dùng một cấu trúc cho mọi câu hỏi.** Ví dụ chỉ có key \`order:O900\` nhưng lại yêu cầu truy vấn hàng nghìn đơn theo \`customerId\` và \`status\` mà không có chỉ mục. Cần bổ sung đường truy cập đã biết ngay từ thiết kế.

**Lỗi 2 — Nhúng không giới hạn.** Nhúng mọi sự kiện giao vận vào document đơn giúp xem tất cả trong một lần nhưng có thể làm tài liệu phình to, tác động tốc độ cập nhật và giới hạn kích thước. Hãy phân biệt thông tin cốt lõi của đơn với tập sự kiện tăng dài.

**Lỗi 3 — Chọn partition key chỉ vì dễ viết.** Trong wide-column, partition \`orders_by_customer\` chỉ theo \`customerId\` có thể khổng lồ khi người dùng mua nhiều; partition theo \`status\` có thể khiến mọi đơn \`PAID\` dồn vào một nhóm rất nóng. Chọn partition theo phân bố truy cập và giới hạn thực tế.

**Lỗi 4 — Nghĩ graph tự giải quyết mọi bài toán join.** Traversal nhiều bước là lợi thế về diễn đạt, nhưng truy vấn trên node bậc rất cao hoặc mở rộng qua phần lớn graph vẫn có thể tốn kém. Cần giới hạn độ sâu, điều kiện lọc và đo bằng dữ liệu thật.

**Lỗi 5 — Không phân biệt dữ liệu hiện tại với dữ liệu lịch sử.** Lấy giá đang bán để hiển thị tổng tiền đơn cũ là sai nghiệp vụ dù truy vấn rất nhanh.

**Lỗi 6 — Giả định thao tác đa đối tượng luôn nguyên tử.** Cập nhật trạng thái đơn, tồn kho, thanh toán và chỉ mục phụ đòi hỏi một quy trình nhất quán được thiết kế rõ; một API ghi thành công chưa chứng minh các bước khác đã hoàn tất.

## 11. Bài tập tự vận dụng

Từ đúng cửa hàng ví dụ, hãy bổ sung yêu cầu **Q6: “Trả về 20 đơn có trạng thái \`PAID\` của khách \`U42\`, mới nhất trước”**.

Định hướng cách nghĩ:

- **Key–value:** có cần \`customer-paid-orders:U42\`, hay lấy danh sách đơn rồi lọc? Nếu cập nhật \`PENDING → PAID\` thì đồng bộ danh sách thế nào?
- **Document:** truy vấn \`{customerId: "U42", status: "PAID"}\` kèm sort và limit; nên xét chỉ mục ghép nào?
- **Wide-column:** bảng hiện tại có đáp ứng tốt không, hay cần \`paid_orders_by_customer_month\`/thiết kế theo \`status\`? Trạng thái đổi thì phải cập nhật những đâu?
- **Graph:** duyệt \`Customer -[:PLACED]-> Order\` kèm điều kiện \`o.status = "PAID"\`, sắp xếp; chuyện gì xảy ra khi một người có hàng triệu đơn?

Tự chọn một phương án và giải thích bằng **số thao tác, đường truy cập và chi phí cập nhật**, thay vì chỉ nêu tên loại cơ sở dữ liệu.

## Kết luận

Bốn mô hình diễn đạt cùng sự thật “Nguyễn Lan đặt đơn O900 gồm P101 và P205”, nhưng làm nổi bật các đơn vị dữ liệu khác nhau:

- **Key–value** đặt trọng tâm vào **khóa dùng để tìm giá trị**.
- **Document** đặt trọng tâm vào **ranh giới đối tượng được đọc hoặc sửa cùng nhau**.
- **Wide-column** đặt trọng tâm vào **partition và thứ tự hàng để phục vụ truy vấn đã thiết kế**.
- **Graph** đặt trọng tâm vào **mối quan hệ và đường đi giữa các thực thể**.

Không có mô hình thắng trong mọi tình huống. Cùng một nghiệp vụ chỉ được biểu diễn đúng khi cấu trúc dữ liệu hỗ trợ các truy vấn thực tế, giữ được các bất biến như giá tại thời điểm mua, và có phương án rõ ràng cho truy cập đồng thời, dữ liệu trùng lặp và tăng trưởng.

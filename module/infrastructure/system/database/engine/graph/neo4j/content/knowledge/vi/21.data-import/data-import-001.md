# Lập ánh xạ từ CSV, JSON và nguồn quan hệ sang mô hình đồ thị

## 1. Từ dữ liệu nguồn đến property graph

Khi nhập dữ liệu vào Neo4j, thách thức chính thường không phải là đọc một tệp CSV hay một mảng JSON. Vấn đề khó hơn là **quyết định thực thể nào trở thành node, mối liên hệ nào trở thành relationship, trường nào là property và khóa nào nhận diện được đối tượng qua nhiều lần nhập**.

Neo4j dùng mô hình **property graph**: node có label và property; relationship có kiểu, hướng và có thể có property. Dữ liệu nguồn có thể đến từ:

- **CSV**: bảng phẳng có hàng, cột, header; thường do hệ thống khác xuất ra.
- **JSON**: object lồng nhau, mảng, trường tùy chọn, dữ liệu được gửi từ API hoặc message broker.
- **Cơ sở dữ liệu quan hệ**: các bảng có primary key, foreign key, bảng trung gian và các ràng buộc dữ liệu.

Một hàng dữ liệu không bắt buộc tương ứng với một node. Một mảng JSON cũng không nhất thiết sinh ra node cho mỗi phần tử. **Ánh xạ (mapping)** phải dựa trên câu hỏi nghiệp vụ muốn truy vấn, độ bền của định danh và vòng đời dữ liệu.

Ví dụ, ứng dụng thương mại điện tử cần trả lời:

1. Khách hàng nào đặt đơn hàng O100?
2. Đơn O100 có những dòng hàng nào, số lượng và đơn giá tại thời điểm mua?
3. Sản phẩm P7 xuất hiện trong những đơn nào?
4. Khách hàng nào đã từng mua sản phẩm thuộc danh mục “Thiết bị”?

Nếu nhập tất cả vào một node khổng lồ chứa chuỗi JSON, truy vấn quan hệ và đường đi khó tận dụng khả năng của graph. Ngược lại, nếu biến mỗi giá trị vô hướng thành một node, graph sẽ phình to và truy vấn phải đi qua nhiều relationship không cần thiết.

## 2. Ví dụ nguồn dữ liệu xuyên suốt

Giả sử hệ thống nguồn có bốn bảng quan hệ:

~~~text
customers(customer_id PK, name, tier)
orders(order_id PK, customer_id FK, status, created_at)
products(product_id PK, name, list_price_in_cents)
order_lines(line_id PK, order_id FK, product_id FK,
            quantity, unit_price_in_cents)
~~~

Một tập dữ liệu tối thiểu:

**customers.csv**

~~~csv
customer_id,name,tier
C01,An,GOLD
C02,Bình,STANDARD
~~~

**orders.csv**

~~~csv
order_id,customer_id,status,created_at
O100,C01,PAID,2026-11-20T09:15:00Z
O101,C02,NEW,2026-11-21T08:00:00Z
~~~

**products.csv**

~~~csv
product_id,name,list_price_in_cents
P7,Bàn phím,250000
P9,Chuột,120000
~~~

**order_lines.csv**

~~~csv
line_id,order_id,product_id,quantity,unit_price_in_cents
L1,O100,P7,2,240000
L2,O100,P9,1,120000
L3,O101,P7,1,250000
~~~

Trong ví dụ này, **unit_price_in_cents** của dòng hàng là giá thực tế tại lúc đặt; **list_price_in_cents** của Product là giá niêm yết hiện tại. Không nên bỏ giá trên OrderLine rồi luôn tính lại từ Product, vì thay đổi bảng giá sau này sẽ làm sai lịch sử giao dịch.

Mô hình đồ thị dự kiến:

~~~mermaid
flowchart LR
    C["Customer<br/>customerId, name, tier"]
    O["Order<br/>orderId, status, createdAt"]
    L["OrderLine<br/>lineId, quantity, unitPriceInCents"]
    P["Product<br/>productId, name, listPriceInCents"]
    C -->|PLACED| O
    O -->|HAS_LINE| L
    L -->|FOR_PRODUCT| P
~~~

Node **OrderLine** được giữ như một thực thể riêng vì mỗi dòng có khóa **lineId**, số lượng và đơn giá lịch sử. Nhờ vậy một đơn có thể có hai dòng khác nhau cùng tham chiếu một Product mà không bị gộp nhầm.

## 3. Quy trình thiết kế ánh xạ trước khi chạy lệnh nhập

Một quy trình nhập dữ liệu an toàn nên đi theo thứ tự:

1. **Kiểm kê nguồn**: tệp/bảng/API nào có dữ liệu, kiểu trường, dung lượng, cách cập nhật và quyền truy cập.
2. **Xác định định danh**: khóa nguồn nào ổn định, khóa có duy nhất toàn cục không, có phân biệt tenant hoặc hệ thống nguồn không.
3. **Phác họa graph**: node, label, relationship, hướng, cardinality và property.
4. **Thiết lập quy tắc chuyển đổi**: parse số, thời gian, boolean, chuẩn hóa chuỗi, xử lý null và danh mục giá trị.
5. **Định nghĩa quy tắc toàn vẹn**: uniqueness constraint, khóa ngoại cần đối chiếu, chính sách cho bản ghi mồ côi.
6. **Chọn thứ tự tải**: tạo node đầu mút trước; nối relationship sau khi các khóa đã có.
7. **Chạy thử trên mẫu nhỏ**: đối chiếu số lượng, kiểm tra nhiều lần nhập, thử lỗi và so truy vấn nghiệp vụ.
8. **Vận hành nhập theo lô**: giới hạn transaction, ghi log kết quả và quản lý lần chạy lại.

Đây là quá trình **ETL/ELT có thiết kế mô hình**, không chỉ chuyển đổi định dạng tệp.

### 3.1. Lập bảng ánh xạ có thể kiểm tra

| Nguồn | Ánh xạ đích | Khóa nhận diện | Chuyển đổi chính | Kiểm tra |
|---|---|---|---|---|
| customers.customer_id | `(:Customer {customerId})` | customer_id | trim, giữ dạng chuỗi | Không null, không trùng trong phạm vi nhận diện |
| customers.name, tier | Property Customer | Theo Customer | Chuẩn hóa tên/tier theo nghiệp vụ | Tier thuộc tập cho phép |
| orders.order_id | `(:Order {orderId})` | order_id | trim | Không trùng |
| orders.customer_id | `(:Customer)-[:PLACED]->(:Order)` | customer_id, order_id | Tra node theo FK | Customer đầu mút tồn tại |
| orders.created_at | Order.createdAt | Theo Order | Chuỗi ISO 8601 → datetime | Parse thành công |
| products.product_id | `(:Product {productId})` | product_id | Giữ dạng chuỗi, kể cả số 0 đầu | Không trùng |
| products.list_price_in_cents | Product.listPriceInCents | Theo Product | Chuỗi → integer | Không âm |
| order_lines.line_id | `(:OrderLine {lineId})` | line_id | Giữ khóa nguồn | Không trùng |
| order_lines.order_id | `(:Order)-[:HAS_LINE]->(:OrderLine)` | order_id, line_id | Tra hai node | Order tồn tại |
| order_lines.product_id | `(:OrderLine)-[:FOR_PRODUCT]->(:Product)` | line_id, product_id | Tra hai node | Product tồn tại |
| order_lines.quantity | OrderLine.quantity | Theo OrderLine | Chuỗi → integer | Lớn hơn 0 |
| order_lines.unit_price_in_cents | OrderLine.unitPriceInCents | Theo OrderLine | Chuỗi → integer | Không âm |

Bảng mapping giúp nhóm phát triển, dữ liệu và nghiệp vụ cùng kiểm tra một trường nguồn sẽ đi đâu. Khi schema nguồn đổi, có thể xác định ngay những phép biến đổi và constraint liên quan.

## 4. Chọn node, relationship hay property

### 4.1. Dữ liệu có định danh và vòng đời riêng thường là node

**Customer**, **Order**, **Product** và **OrderLine** đều có khóa riêng. Chúng có thể được tra cứu, cập nhật hoặc nối với các thực thể khác độc lập. Vì vậy, mỗi loại là một ứng viên node.

Một trường như **Customer.name** thường chỉ là property, vì người dùng ít khi cần “đi qua node tên” để truy vấn.

### 4.2. Foreign key thường trở thành relationship, nhưng không theo công thức một-một cứng nhắc

Trong cơ sở dữ liệu quan hệ:

~~~sql
SELECT o.order_id, c.customer_id
FROM orders AS o
JOIN customers AS c ON c.customer_id = o.customer_id;
~~~

Foreign key **orders.customer_id** biểu diễn quan hệ sở hữu đơn. Trong graph, ánh xạ hợp lý là:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
MATCH (o:Order {orderId: $orderId})
MERGE (c)-[:PLACED]->(o);
~~~

Tuy nhiên, nguồn quan hệ còn có thể chứa khóa ngoại chỉ phục vụ kỹ thuật, bảng audit, bảng cấu hình hoặc quan hệ không có giá trị cho truy vấn graph. Chỉ tạo relationship khi nó diễn đạt một liên kết nghiệp vụ thực sự hữu ích.

### 4.3. Bảng trung gian nhiều–nhiều: relationship hay node?

Giả sử bảng **user_groups(user_id, group_id, joined_at)**, mỗi cặp user–group chỉ có một hàng và bản thân membership không có vòng đời độc lập. Có thể ánh xạ:

~~~text
(:User)-[:MEMBER_OF {joinedAt}]->(:Group)
~~~

Nhưng bảng **order_lines** có **line_id** riêng, số lượng, đơn giá lịch sử và có thể chứa nhiều dòng cùng product trong một order. Mô hình **OrderLine node** giúp bảo tồn từng bản ghi và đơn giản hóa khả năng tham chiếu/chỉnh sửa riêng.

| Tiêu chí | Dùng relationship có property | Dùng node trung gian |
|---|---|---|
| Chỉ biểu diễn mối nối giữa hai thực thể | Phù hợp | Có thể tạo thêm cấu trúc không cần thiết |
| Một cặp đầu mút có nhiều bản ghi độc lập | Cần thiết kế identity/cách nối đặc biệt | Thường tự nhiên hơn |
| Bản ghi nối có ID và vòng đời riêng | Có thể thực hiện với mô hình bổ sung | Thường phù hợp |
| Thực thể nối cần liên kết tới bên thứ ba | Có thể trở nên khó biểu diễn | Thuận tiện |
| Truy vấn chỉ cần tồn tại quan hệ | Thường ngắn hơn | Cần thêm một bước duyệt |

Mục tiêu không phải chuyển mọi bảng join thành relationship bằng mọi giá, mà là **bảo tồn đúng danh tính và ngữ nghĩa**.

## 5. Thiết kế khóa ổn định và constraint

### 5.1. Giữ khóa nguồn làm property

Neo4j có định danh nội bộ cho node/relationship, nhưng import nhiều lần và đồng bộ liên hệ với hệ thống ngoài nên sử dụng **khóa nghiệp vụ ổn định** như **customerId**, **orderId**, **productId** và **lineId**.

Không dùng row number trong tệp CSV làm định danh nếu thứ tự hàng có thể đổi. Với mã **"000123"**, phải giữ dạng **chuỗi** nếu số 0 đầu là một phần của định danh. Chỉ chuyển sang integer khi trường thật sự là đại lượng số học.

### 5.2. Tạo ràng buộc trước khi nhập

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT order_id_unique IF NOT EXISTS
FOR (o:Order)
REQUIRE o.orderId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT product_id_unique IF NOT EXISTS
FOR (p:Product)
REQUIRE p.productId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT line_id_unique IF NOT EXISTS
FOR (l:OrderLine)
REQUIRE l.lineId IS UNIQUE;
~~~

Các uniqueness constraint ngăn hai node **cùng nhãn** mang cùng giá trị khóa khi property đó tồn tại. Chúng không tự bắt buộc mọi node phải có property khóa. Cần kiểm tra input và cân nhắc constraint tồn tại/node key nếu phiên bản, edition và nghiệp vụ cho phép.

Có thể xem schema bằng:

~~~cypher
SHOW CONSTRAINTS;
~~~

**Chú ý:** Nếu trong database đã tồn tại node trùng khóa, tạo uniqueness constraint có thể thất bại. Cần phát hiện và xử lý trùng đúng nghiệp vụ trước khi tạo schema.

### 5.3. Khóa chỉ duy nhất trong phạm vi tenant/nguồn

Nếu Customer C01 xuất hiện tại hai hệ thống CRM khác nhau, khóa `customerId = 'C01'` có thể **không duy nhất toàn cục**. Cần định nghĩa namespace, ví dụ:

~~~cypher
CREATE CONSTRAINT customer_source_id_unique IF NOT EXISTS
FOR (c:ExternalCustomer)
REQUIRE (c.sourceSystem, c.externalId) IS UNIQUE;
~~~

~~~cypher
MERGE (c:ExternalCustomer {
    sourceSystem: $sourceSystem,
    externalId: $externalId
})
SET c.name = $name;
~~~

Định danh composite giúp ngăn hai khách hàng của hai hệ thống bị gộp nhầm. Các trường cần chuẩn hóa nhất quán trước import.

## 6. Import CSV: từ hàng phẳng thành node

Neo4j hỗ trợ **LOAD CSV** để đọc dữ liệu dạng CSV từ nguồn được cấu hình cho phép. Với local file import, cú pháp thường là **file:///customers.csv**; đường dẫn được giải quyết trên phía **Neo4j server**, không phải máy tính nơi chạy Neo4j Browser hay ứng dụng Java.

Tùy bản triển khai Neo4j (tự vận hành, Docker, cloud) và cấu hình bảo mật, quyền truy cập file/URL có thể khác nhau. Trong ví dụ này, giả sử bốn tệp nằm trong thư mục import mà server cho phép đọc.

### 6.1. Tạo Customer

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
WITH row
WHERE row.customer_id IS NOT NULL
  AND trim(row.customer_id) <> ''
MERGE (c:Customer {customerId: trim(row.customer_id)})
SET c.name = row.name,
    c.tier = row.tier;
~~~

Ý nghĩa:

- **WITH HEADERS** ánh xạ tên cột thành key của `row`.
- Giá trị CSV được đọc dưới dạng **chuỗi**; `row.customer_id` là một chuỗi định danh.
- **WHERE** loại hàng không có ID hợp lệ. Trên hệ thống thật, những hàng bị loại cần được **ghi nhận ở bước kiểm tra dữ liệu**, không lặng lẽ mất.
- **MERGE** tìm hoặc tạo Customer theo khóa đã được ràng buộc.
- **SET** cập nhật property mô tả khi import lại.

Với dữ liệu trùng một ID nhưng khác tên, câu SET sẽ ghi theo giá trị của lần xử lý sau. Nếu nghiệp vụ cần quy tắc chọn bản ghi mới nhất, phải có timestamp/version và logic giải quyết xung đột.

### 6.2. Tạo Product và chuyển kiểu số

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///products.csv' AS row
WITH row
WHERE row.product_id IS NOT NULL
  AND trim(row.product_id) <> ''
MERGE (p:Product {productId: trim(row.product_id)})
SET p.name = row.name,
    p.listPriceInCents = toInteger(row.list_price_in_cents);
~~~

**toInteger** chuyển chuỗi sang số nguyên. Giá trị đầu vào không hợp lệ có thể dẫn đến lỗi hoặc null tùy biểu thức; không nên trông chờ câu nhập tự sửa mọi dữ liệu. Đối chiếu dữ liệu nguồn trước khi nhập, chẳng hạn giá phải là số nguyên và không âm.

### 6.3. Tạo Order và relationship PLACED

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///orders.csv' AS row
WITH row
WHERE row.order_id IS NOT NULL
  AND trim(row.order_id) <> ''
MATCH (c:Customer {customerId: trim(row.customer_id)})
MERGE (o:Order {orderId: trim(row.order_id)})
SET o.status = row.status,
    o.createdAt = datetime(row.created_at)
MERGE (c)-[:PLACED]->(o);
~~~

Các node Customer được tạo **trước** Order. MATCH tìm Customer đã có, sau đó mới MERGE Order và PLACED. Nếu FK **customer_id** không khớp, hàng đó không đi tiếp trong truy vấn; đây là lý do phải **đối chiếu bản ghi mồ côi** trước/sau import.

**datetime(row.created_at)** yêu cầu chuỗi thời gian theo định dạng Neo4j hỗ trợ, ví dụ **2026-11-20T09:15:00Z**. Nếu nguồn có timezone mơ hồ hoặc định dạng không thống nhất, hãy chuẩn hóa trước khi import.

### 6.4. Tạo OrderLine cùng hai quan hệ

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///order_lines.csv' AS row
WITH row
WHERE row.line_id IS NOT NULL
  AND trim(row.line_id) <> ''
MATCH (o:Order {orderId: trim(row.order_id)})
MATCH (p:Product {productId: trim(row.product_id)})
MERGE (l:OrderLine {lineId: trim(row.line_id)})
SET l.quantity = toInteger(row.quantity),
    l.unitPriceInCents = toInteger(row.unit_price_in_cents)
MERGE (o)-[:HAS_LINE]->(l)
MERGE (l)-[:FOR_PRODUCT]->(p);
~~~

Trong dữ liệu mẫu, truy vấn tạo **3 OrderLine**, **3 HAS_LINE** và **3 FOR_PRODUCT** nếu mọi khóa ngoại đều hợp lệ. Relationship được tạo sau khi hai node đầu mút đã có định danh.

**Lưu ý về MERGE và quan hệ:** Ví dụ giả định mỗi lineId thuộc đúng một Order và đúng một Product, và lần nhập lại không gán nó sang đầu mút khác. Nếu dữ liệu nguồn đổi chủ sở hữu của cùng lineId, dùng MERGE relationship như trên có thể tạo thêm liên kết không mong muốn. Đây là thay đổi dữ liệu cần xử lý bằng quy tắc migration/sync rõ ràng: từ chối xung đột, thay liên kết cũ hoặc tạo phiên bản lịch sử.

### 6.5. Kiểm chứng graph sau import

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
MATCH (o)-[:HAS_LINE]->(l:OrderLine)-[:FOR_PRODUCT]->(p:Product)
RETURN c.customerId AS customerId,
       o.orderId AS orderId,
       l.lineId AS lineId,
       p.productId AS productId,
       l.quantity AS quantity,
       l.unitPriceInCents AS unitPriceInCents
ORDER BY orderId, lineId;
~~~

Với bộ dữ liệu ví dụ, truy vấn trả về **3 hàng theo 3 dòng hàng**, không phải 3 đơn hoặc 3 sản phẩm. Hãy đối chiếu từng **lineId** với nguồn để xác minh mối quan hệ được nối đúng.

## 7. Import JSON: tách dữ liệu lồng nhau thành thực thể và liên kết

JSON thường chứa object lồng nhau:

~~~json
{
  "orderId": "O100",
  "customerId": "C01",
  "status": "PAID",
  "createdAt": "2026-11-20T09:15:00Z",
  "items": [
    {"lineId": "L1", "productId": "P7", "quantity": 2, "unitPriceInCents": 240000},
    {"lineId": "L2", "productId": "P9", "quantity": 1, "unitPriceInCents": 120000}
  ]
}
~~~

Dạng JSON này là **một chứng từ đặt hàng có danh sách dòng hàng**, nhưng khi biểu diễn trong graph cần giữ lại các đối tượng riêng biệt có ID. Không nên mặc định lưu toàn bộ mảng **items** thành một property JSON nếu nghiệp vụ cần tìm sản phẩm qua nhiều đơn.

### 7.1. Truyền JSON đã parse thành tham số Cypher

Neo4j không có câu lệnh Cypher lõi tên **LOAD JSON** tương tự LOAD CSV. Một cách không phụ thuộc plugin là dùng ứng dụng đọc/parse JSON thành **list/map**, truyền nó qua Java Driver như tham số **$orders**, rồi dùng **UNWIND** để tạo graph.

Ví dụ **$orders** là mảng chứa một hoặc nhiều object có cấu trúc như JSON trên. Giả sử Customer và Product đã được nhập, có thể dùng:

~~~cypher
UNWIND $orders AS row
MATCH (c:Customer {customerId: row.customerId})
MERGE (o:Order {orderId: row.orderId})
SET o.status = row.status,
    o.createdAt = datetime(row.createdAt)
MERGE (c)-[:PLACED]->(o)
WITH o, row
UNWIND coalesce(row.items, []) AS item
MATCH (p:Product {productId: item.productId})
MERGE (l:OrderLine {lineId: item.lineId})
SET l.quantity = toInteger(item.quantity),
    l.unitPriceInCents = toInteger(item.unitPriceInCents)
MERGE (o)-[:HAS_LINE]->(l)
MERGE (l)-[:FOR_PRODUCT]->(p)
RETURN count(l) AS importedItemRows;
~~~

Giải thích:

- **UNWIND $orders AS row** biến mỗi object Order thành một hàng.
- MERGE Order theo **orderId** và nối Customer.
- **UNWIND row.items AS item** tạo một hàng cho mỗi dòng hàng, rồi nối đến Product.
- **coalesce(row.items, [])** cho phép danh sách items thiếu/null được coi là danh sách rỗng trong bước mở rộng.
- **count(l)** ở cuối đếm số **hàng item được xử lý**, không phải số Order mới tạo hoặc số node thực tế mới tạo.

Nếu một Order có **items = []**, phần nhập Order phía trước vẫn có thể thực hiện, nhưng hàng đó không đi qua phần cuối sau UNWIND, nên không xuất hiện trong phép đếm **importedItemRows**. Nếu cần báo cáo cả số Order và số item, hãy tách thống kê hoặc dùng một cấu trúc truy vấn khác.

**Quan trọng:** Khi một đầu mút Customer/Product không có, MATCH sẽ loại hàng tương ứng. Để không bỏ sót âm thầm, ứng dụng cần kiểm tra foreign key và tổng số hàng trước khi chạy nhập thật.

### 7.2. Đọc JSON từ tệp hoặc URL qua APOC (tùy chọn)

Một số bản triển khai cài **APOC** và cho phép nạp JSON từ nguồn cấu hình phù hợp:

~~~cypher
CALL apoc.load.json($jsonUrl) YIELD value
RETURN value;
~~~

Đây là thủ tục **APOC**, không phải cú pháp LOAD CSV của Cypher lõi. Việc dùng file local, URL, cấu hình bảo mật và quyền thực thi phụ thuộc phiên bản Neo4j/APOC và môi trường triển khai. Không giả định mọi Neo4j server đều bật hoặc cho phép APOC đọc tùy ý các đường dẫn.

Khi không có APOC, ứng dụng có thể tải JSON từ hệ thống nguồn, parse/validate rồi gửi tham số **list/map** bằng Driver như mục 7.1. Cách này cũng tiện để kiểm soát authentication, retry, xử lý lỗi và batch size.

### 7.3. Không đồng nhất kiểu JSON và property Neo4j

JSON có thể chứa:

- **string, number, boolean, null**;
- **array** các object hoặc giá trị;
- **object lồng nhau**;
- ngày giờ được biểu diễn bằng string.

Neo4j hỗ trợ các kiểu property phù hợp với giá trị nguyên thủy, thời gian và một số loại list; **map/object lồng nhau không thể mặc nhiên lưu trực tiếp như một property node theo cách JSON document store làm**. Cần quyết định:

- Biến object thành **node** nếu có danh tính và cần kết nối.
- Trải các trường con thành **property** nếu nhóm trường ổn định, hữu ích và hợp lệ.
- Lưu JSON gốc ngoài graph hoặc dưới dạng chuỗi riêng nếu thực sự cần lưu payload để tra soát; tránh dùng nó thay cho cấu trúc truy vấn chính.

## 8. Nhập từ nguồn quan hệ: xử lý PK, FK và bảng trung gian

Một migration từ SQL sang graph thường cần **extract** trước khi LOAD CSV hoặc truyền tham số qua Driver. Bốn bảng nguồn có thể được export giữ nguyên tên khóa và các trường nghiệp vụ.

### 8.1. Phân loại bảng nguồn

| Đặc điểm bảng quan hệ | Hướng ánh xạ tham khảo | Điều cần kiểm tra |
|---|---|---|
| Bảng thực thể có PK | Node mang label nghiệp vụ | Khóa duy nhất, loại dữ liệu, vòng đời |
| Cột FK 1–n | Relationship giữa hai node | Hướng, tính bắt buộc, node đầu mút |
| Bảng nối n–n chỉ có hai FK | Relationship giữa hai node | Một cặp có được phép nhiều liên kết không? |
| Bảng nối có payload và PK riêng | Relationship có property hoặc node trung gian | Mỗi bản ghi có identity, audit, vòng đời không? |
| Bảng danh mục nhỏ | Node, property hoặc enum theo nhu cầu truy vấn | Có cần duyệt quan hệ với danh mục? |
| Bảng lịch sử/sự kiện | Event node, property thời gian, hoặc hệ thống lưu lịch sử khác | Khối lượng, TTL, truy vấn thời gian |
| Cột JSON trong SQL | Parse thành property/relationship hoặc giữ payload có kiểm soát | Kiểu dữ liệu và độ biến động của schema |

Đừng xem việc không tạo node cho một bảng SQL là làm mất dữ liệu. Mục tiêu là **bảo tồn thông tin nghiệp vụ và khả năng truy vấn**, với thiết kế graph phù hợp.

### 8.2. Một FK có thể có nhiều nghĩa

Ví dụ bảng **orders** có **customer_id** biểu diễn người đặt hàng và **approved_by_user_id** biểu diễn người duyệt. Hai FK cùng trỏ tới bảng người dùng, nhưng cần relationship có ý nghĩa khác nhau:

~~~text
(:Customer)-[:PLACED]->(:Order)
(:User)-[:APPROVED]->(:Order)
~~~

Không gom tất cả foreign key thành một relationship kiểu **RELATED_TO**, vì sẽ mất ngữ nghĩa và gây khó khăn cho truy vấn Cypher.

### 8.3. Hướng relationship theo câu hỏi truy vấn

Với **PLACED**, chọn hướng **Customer → Order** vì đọc “Customer đã đặt Order” trực quan. Neo4j vẫn hỗ trợ match quan hệ theo cả hai hướng:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order {orderId: $orderId})
RETURN c.customerId AS customerId;
~~~

Chọn một hướng quy ước nhất quán trong mô hình; không cần tạo thêm relationship chiều ngược lại chỉ để truy vấn ngược.

### 8.4. Ràng buộc khóa ngoại không tự được tái tạo

Trong SQL, foreign key có thể ngăn tạo bản ghi trỏ tới PK không tồn tại. Khi nhập Neo4j bằng MATCH, hàng trỏ tới node chưa tồn tại thường **không tạo relationship**. Nếu chỉ chạy lệnh import và không so sánh số hàng, có thể bỏ sót liên kết mà không có lỗi rõ ràng.

Cần xây dựng bước kiểm tra toàn vẹn tham chiếu:

- Liệt kê Order có **customer_id** không tìm thấy trong danh sách Customer.
- Liệt kê OrderLine có **order_id** hoặc **product_id** không khớp.
- Chọn chính sách: **dừng lô**, **cách ly hàng lỗi**, hoặc **tạo placeholder có kiểm soát** nếu nghiệp vụ cho phép.
- Đối chiếu số node và relationship thực tế sau khi import.

Không tạo node placeholder cho mọi FK thiếu chỉ để đạt đủ số hàng, vì có thể che khuất dữ liệu đầu vào bị lỗi.

## 9. Chuẩn hóa kiểu dữ liệu trước khi ghi

CSV đọc chuỗi, còn JSON/SQL có thể mang kiểu số hoặc boolean. Một trường nguồn có thể cần chuyển đổi khác nhau theo kênh nhận.

| Loại dữ liệu nguồn | Property đích | Quy tắc |
|---|---|---|
| `"00128"` là mã định danh | `productId: "00128"` | Giữ string, không làm mất 0 đầu |
| `"2"` là quantity | `quantity: 2` | Parse integer, kiểm tra > 0 |
| `"240000"` là tiền tính theo cent | `unitPriceInCents: 240000` | Dùng integer để tránh sai số tiền tệ |
| `"2026-11-20T09:15:00Z"` | `createdAt` kiểu datetime | Chuẩn hóa timezone và ISO |
| `"true"` hoặc boolean | `active` kiểu boolean | Xác định phép parse rõ ràng |
| Chuỗi rỗng, null, không có key | Null/property vắng hoặc lỗi | Theo quy tắc trường bắt buộc |

Ví dụ chuyển đổi trong Cypher:

~~~cypher
WITH {
    quantityText: '2',
    amountText: '240000',
    timeText: '2026-11-20T09:15:00Z'
} AS raw
RETURN toInteger(raw.quantityText) AS quantity,
       toInteger(raw.amountText) AS amountInCents,
       datetime(raw.timeText) AS createdAt;
~~~

Đoạn này minh họa hàm chuyển kiểu, không phải quy trình kiểm tra input toàn diện.

### 9.1. Null, chuỗi rỗng và trường không có

Trong nhiều nguồn dữ liệu:

- **CSV trống** có thể là **chuỗi rỗng**.
- **JSON null** có nghĩa khác với key **không xuất hiện**.
- **SQL NULL** phản ánh giá trị thiếu theo schema SQL.
- Trong Neo4j, **null không phải một property được lưu như giá trị bình thường**; việc SET property thành null có tác dụng xóa property đó.

Trước khi cập nhật bằng **SET c.name = row.name**, hãy xác định liệu dữ liệu nguồn rỗng có nghĩa **xóa tên cũ**, **giữ tên cũ** hay **báo lỗi**. Trong đồng bộ tăng dần, khác biệt này rất quan trọng.

Một cách tránh ghi đè bằng null khi API không gửi trường:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
SET c.name = coalesce($name, c.name)
RETURN c.customerId AS customerId, c.name AS name;
~~~

Biểu thức trên giữ lại tên hiện tại nếu **$name = null**. Nó chỉ phù hợp khi null được định nghĩa là **không cập nhật**, không phù hợp nếu null phải xóa trường. Với chuỗi rỗng, cần quy tắc riêng.

### 9.2. Chuẩn hóa và nguồn gốc dữ liệu

Ngoài các trường nghiệp vụ, có thể lưu metadata như **sourceSystem**, **externalId**, **lastImportedAt** và **sourceUpdatedAt** khi cần truy vết. Chỉ lưu metadata thực sự phục vụ quản trị hoặc đồng bộ; không cần sao chép mọi trường kỹ thuật của nguồn.

Nếu nguồn có nhiều phiên bản của cùng bản ghi, **nhập lặp bằng MERGE không tự quyết định bản ghi mới hay cũ**. Cần chọn quy tắc phiên bản/timestamp để tránh một bản ghi đến trễ ghi đè dữ liệu mới.

## 10. Thiết kế nhập lặp an toàn và đồng bộ tăng dần

### 10.1. MERGE theo khóa, SET theo thay đổi

~~~cypher
MERGE (c:Customer {customerId: $customerId})
ON CREATE SET c.createdAt = datetime()
SET c.name = $name,
    c.tier = $tier
RETURN c.customerId AS customerId;
~~~

Nếu import lại cùng Customer, MERGE cố sử dụng node theo khóa thay vì luôn tạo node mới như CREATE. Khi ghi đồng thời hoặc retry, uniqueness constraint giúp bảo vệ trạng thái không trùng node theo khóa.

Không nên đưa **name**, **tier** hoặc timestamp thay đổi vào map của MERGE:

~~~cypher
// Không dùng khi name có thể đổi.
MERGE (c:Customer {customerId: $customerId, name: $name});
~~~

Nếu name thay đổi, mẫu cũ không khớp đầy đủ; Neo4j có thể cố tạo thêm node hoặc báo vi phạm uniqueness. Đặt **chỉ khóa nhận diện ổn định** trong MERGE.

### 10.2. Nhập full snapshot khác nhập sự kiện thay đổi

| Kiểu dữ liệu | Ý nghĩa | Cách xử lý cần có |
|---|---|---|
| Full snapshot | Tệp biểu diễn trạng thái tại một thời điểm | Chính sách xử lý node đã biến mất khỏi snapshot |
| Incremental upsert | Chỉ các bản ghi mới hoặc thay đổi | MERGE theo khóa, SET property có chính sách phiên bản |
| Change data capture (CDC) | Sự kiện insert/update/delete từ SQL | Ánh xạ từng loại thay đổi và thứ tự sự kiện |
| Event stream at-least-once | Một sự kiện có thể được gửi lại | Idempotency key, kiểm soát duplicate và retry |
| Backfill lịch sử | Nhiều bản ghi cũ để dựng graph ban đầu | Batching, checkpoint, tách giai đoạn và xác minh |

**Không suy luận rằng bản ghi thiếu trong một lô incremental cần bị xóa.** Chỉ với full snapshot có định nghĩa rõ, ứng dụng mới có thể cân nhắc so sánh và xóa dữ liệu không còn tồn tại, đồng thời phải đánh giá tác động lên relationship.

### 10.3. Xóa cũng cần quy tắc ánh xạ

Nếu SQL nguồn xóa Order, graph cần quyết định:

- Xóa Order và OrderLine liên quan?
- Giữ Order dưới dạng archived/soft delete?
- Giữ lịch sử giao dịch phục vụ báo cáo?
- Xóa những relationship nào và có những node chung nào cần bảo tồn?

Không dùng **DETACH DELETE** hàng loạt chỉ vì nguồn không còn bản ghi; các liên kết có thể chứa thông tin cần giữ lại. Chọn hành vi theo vòng đời nghiệp vụ và chính sách lưu dữ liệu.

## 11. Chia lô, transaction và hiệu năng

Với dữ liệu nhỏ, một lệnh LOAD CSV có thể đủ để minh họa. Với hàng triệu hàng, cần kiểm soát kích thước transaction, mức song song và ghi log lỗi.

Có thể chia dữ liệu thành các lô rồi gọi nhiều transaction qua Java Driver, hoặc sử dụng **CALL ... IN TRANSACTIONS** nếu phiên bản Neo4j và cách gọi truy vấn hỗ trợ cú pháp đó. Ví dụ khái niệm cho Neo4j hỗ trợ biến trong subquery:

~~~cypher
LOAD CSV WITH HEADERS FROM 'file:///products.csv' AS row
CALL (row) {
    WITH row
    WHERE row.product_id IS NOT NULL
      AND trim(row.product_id) <> ''
    MERGE (p:Product {productId: trim(row.product_id)})
    SET p.name = row.name,
        p.listPriceInCents = toInteger(row.list_price_in_cents)
} IN TRANSACTIONS OF 1000 ROWS;
~~~

**Lưu ý phiên bản:** cú pháp nhập biến trong CALL subquery và hỗ trợ chạy **IN TRANSACTIONS** khác nhau giữa các phiên bản Neo4j. Kiểm tra tài liệu của phiên bản đang chạy; một số loại explicit transaction của client không cho phép câu lệnh quản lý transaction theo lô này. Khi dùng cách khác, có thể dùng cơ chế batch của ETL/Driver để thực thi mỗi lô trong transaction riêng.

Các yếu tố quyết định tốc độ nhập:

1. **Constraint/index trên khóa MERGE** giúp tra node theo định danh.
2. **Tải node trước relationship** tránh tìm kiếm đầu mút chưa có.
3. **Kích thước lô** phải phù hợp bộ nhớ, thời gian transaction và tải ghi.
4. **Số worker đồng thời** cần giới hạn khi nhiều bản ghi cùng chạm một node có bậc cao.
5. **Truy vấn nối quan hệ** nên MATCH theo khóa rõ ràng, tránh quét toàn bộ nhãn.
6. **Checkpoint và retry** giúp tiếp tục sau lỗi mà không nhân bản dữ liệu.
7. **Quan sát DB Hits và transaction latency** để tìm bottleneck, thay vì đoán tốc độ theo số dòng CSV.

MERGE tăng khả năng nhập lại an toàn nhưng không bảo đảm mọi thao tác với relationship hoặc payload thay đổi đều tự giải quyết xung đột nghiệp vụ. Bảo vệ từng bất biến theo mô hình dữ liệu và mức đồng thời thực tế.

## 12. Ví dụ ứng dụng Java Driver truyền bản ghi đã chuẩn hóa

Một ứng dụng có thể đọc CSV/JSON/SQL thành danh sách map, xác thực rồi gửi **tham số** cho Neo4j. Đoạn dưới minh họa upsert Customer theo lô; nó không thực hiện bước parse hoặc xác thực dữ liệu nguồn.

~~~java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class CustomerImportService {
    private final Driver driver;

    public CustomerImportService(Driver driver) {
        this.driver = driver;
    }

    public long importCustomers(List<Map<String, Object>> records) {
        String cypher = """
            UNWIND $records AS row
            MERGE (c:Customer {customerId: row.customerId})
            SET c.name = row.name,
                c.tier = row.tier
            RETURN count(c) AS processedRows
            """;

        try (Session session =
                 driver.session(SessionConfig.forDatabase("neo4j"))) {
            return session.executeWrite(tx ->
                tx.run(cypher, Map.of("records", records))
                  .single()
                  .get("processedRows")
                  .asLong()
            );
        }
    }
}
~~~

Lưu ý:

- **Driver** thường được tái sử dụng ở mức ứng dụng; **Session** có vòng đời ngắn.
- **executeWrite** dùng managed transaction; callback có thể chạy lại khi gặp lỗi transient được driver xác định là có thể retry.
- **records** phải được chuẩn hóa, kiểm tra khóa bắt buộc và chia thành các lô phù hợp trước khi gọi.
- **processedRows** đếm số hàng tham số đi qua truy vấn, **không phải số node được tạo mới**.
- Không gọi API bên ngoài có tác dụng phụ bên trong callback có thể retry nếu chưa có cơ chế idempotency.
- Nếu dữ liệu nguồn chứa nhiều bản ghi cùng customerId nhưng giá trị khác nhau, hãy quyết định quy tắc cập nhật trước khi UNWIND.

Với **Spring Data Neo4j**, có thể quản lý transaction qua service/repository hoặc Neo4jClient, nhưng nguyên tắc về định danh, constraint, import theo lô và kiểm chứng tính đúng vẫn giữ nguyên. Một phương thức `save` ở tầng Java không thay thế kế hoạch mapping và uniqueness constraint trong database.

## 13. Kiểm tra dữ liệu đầu vào và đối soát sau import

### 13.1. Kiểm tra nguồn trước khi ghi

Với tệp mẫu, các điều kiện tối thiểu:

- Không có Customer, Order, Product hoặc OrderLine thiếu khóa định danh.
- Không có hai hàng dùng cùng khóa nhưng chứa thông tin mâu thuẫn ngoài ý muốn.
- Mỗi **orders.customer_id** xuất hiện trong Customer.
- Mỗi **order_lines.order_id** xuất hiện trong Order.
- Mỗi **order_lines.product_id** xuất hiện trong Product.
- **quantity** là số nguyên dương; giá tiền là số nguyên không âm.
- **created_at** có format và timezone được thống nhất.
- Header CSV đúng tên dự kiến; encoding UTF-8 được xác nhận.
- JSON có cấu trúc item phù hợp; không giả định một key bắt buộc luôn có.

Khi nguồn lỗi, cần quyết định **dừng lô**, **bỏ hàng có ghi nhận**, hoặc **đưa vào hàng đợi sửa dữ liệu**. Không im lặng bỏ qua bản ghi mồ côi chỉ để quá trình import kết thúc thành công.

### 13.2. Đối soát số node và relationship

~~~cypher
MATCH (c:Customer)
RETURN count(c) AS customerNodes;
~~~

~~~cypher
MATCH (o:Order)
RETURN count(o) AS orderNodes;
~~~

~~~cypher
MATCH (l:OrderLine)
RETURN count(l) AS lineNodes;
~~~

~~~cypher
MATCH (:Customer)-[r:PLACED]->(:Order)
RETURN count(r) AS placedRelationships;
~~~

~~~cypher
MATCH (:Order)-[r:HAS_LINE]->(:OrderLine)
RETURN count(r) AS hasLineRelationships;
~~~

~~~cypher
MATCH (:OrderLine)-[r:FOR_PRODUCT]->(:Product)
RETURN count(r) AS forProductRelationships;
~~~

Với graph chỉ chứa dữ liệu ví dụ, mong đợi **2 Customer**, **2 Order**, **2 Product**, **3 OrderLine**, **2 PLACED**, **3 HAS_LINE** và **3 FOR_PRODUCT**. Nếu database còn dữ liệu khác, phải lọc bằng namespace/bộ định danh của lần import trước khi so sánh.

Đối soát số lượng là bước đầu; **đúng số node nhưng nối sai relationship** vẫn là lỗi. Cần kiểm tra thêm mẫu đường đi và các cặp khóa đầu mút.

### 13.3. Phát hiện node thiếu liên kết kỳ vọng

Ví dụ tìm Order chưa có Customer đặt:

~~~cypher
MATCH (o:Order)
WHERE NOT EXISTS {
    MATCH (:Customer)-[:PLACED]->(o)
}
RETURN o.orderId AS orderId
LIMIT 50;
~~~

Tìm OrderLine chưa trỏ tới Product:

~~~cypher
MATCH (l:OrderLine)
WHERE NOT EXISTS {
    MATCH (l)-[:FOR_PRODUCT]->(:Product)
}
RETURN l.lineId AS lineId
LIMIT 50;
~~~

Những truy vấn này phát hiện bất thường trong graph, nhưng không tìm được hàng nguồn bị loại bỏ hoàn toàn trước khi tạo node. Vì vậy, phải đối chiếu **cả nguồn lẫn graph**.

### 13.4. Kiểm tra nhập lại

Chạy lại cùng dữ liệu thử nghiệm sau khi đã tạo constraint. Nếu ánh xạ được thiết kế idempotent, số node theo khóa nghiệp vụ **không tăng thêm** chỉ vì import lại. Đồng thời xác nhận property và relationship không bị thay đổi ngoài dự kiến.

Thử thêm dữ liệu lỗi có chủ đích trên môi trường test, ví dụ một **lineId** có **orderId** khác lần nhập trước, để kiểm tra hệ thống có phát hiện xung đột hay lặng lẽ tạo thêm relationship.

## 14. Các lỗi ánh xạ thường gặp

| Sai lầm | Hậu quả | Hướng xử lý |
|---|---|---|
| Dùng CREATE cho mọi hàng ở mỗi lần nhập | Node trùng khi chạy lại | MERGE theo khóa và constraint phù hợp |
| Coi số thứ tự hàng CSV là khóa | Đổi thứ tự tệp làm thay đổi identity | Dùng PK/ID nghiệp vụ ổn định |
| Chuyển mọi mã số sang integer | Mất số 0 đầu, gộp nhầm định danh | Phân biệt mã định danh với đại lượng |
| Biến mọi trường JSON thành node | Graph nhiều node vô nghĩa và truy vấn phức tạp | Giữ các trường đơn giản dưới dạng property |
| Nhét mọi JSON vào một property string | Không tận dụng được truy vấn relationship/path | Tách thực thể có identity và liên kết cần truy vấn |
| Gộp mọi join table thành quan hệ đơn | Có thể mất lineId và nhiều dòng cùng cặp đầu mút | Cân nhắc node trung gian |
| Nhập relationship trước node | Thiếu đầu mút, mất quan hệ | Tải node trước, đối chiếu FK |
| Không kiểm tra MATCH bị 0 hàng | Bỏ sót hàng nguồn mà không biết | Đối chiếu orphan và record counts |
| Không tạo uniqueness constraint | Trùng node dưới tải/đồng bộ lại | Tạo schema trước import |
| Chỉ dựa vào count sau import | Không phát hiện nối sai đầu mút | Kiểm tra mẫu đường đi và cặp khóa |
| Ghi null như thể “không cập nhật” | Xóa property cũ ngoài ý muốn | Định nghĩa ngữ nghĩa null rõ ràng |
| Ghi đè giá trị bằng sự kiện đến muộn | Dữ liệu mới trở về trạng thái cũ | Dùng quy tắc version/timestamp |
| Import toàn bộ trong transaction cực lớn | Chậm, tốn bộ nhớ, rollback khó | Chia lô theo giới hạn hệ thống |
| Tạo relationship hai chiều chỉ để đọc ngược | Dư thừa và khó đồng bộ | Chọn một hướng, MATCH ngược khi cần |

## 15. Bài tập vận dụng

### Bài 1. Từ bảng quan hệ sang graph

Nguồn có **students(id, name)**, **courses(id, title)**, **enrollments(student_id, course_id, enrolled_at)**. Mỗi sinh viên chỉ được ghi danh một lần vào mỗi khóa học; bản ghi enrollments không có ID riêng.

**Câu hỏi:** Nên ánh xạ enrollments thành node hay relationship?

**Gợi ý:** Có thể dùng **(Student)-[:ENROLLED_IN {enrolledAt}]->(Course)** nếu mỗi cặp student–course chỉ có một ghi danh và bản ghi không có vòng đời độc lập. Cần xác định chính sách bảo đảm không tạo nhiều quan hệ trùng cùng cặp khi nhập đồng thời.

### Bài 2. Bảo tồn bản ghi order_lines

Nguồn có hai dòng hàng cùng Order và Product, nhưng khác **line_id** và đơn giá.

**Câu hỏi:** Vì sao chỉ dùng **MERGE (Order)-[:HAS_ITEM]->(Product)** có thể làm sai mô hình?

**Gợi ý:** Hai bản ghi độc lập có thể bị gộp thành một relationship nếu mẫu chỉ dùng cặp đầu mút. Dùng **OrderLine node có lineId** là một cách giữ được từng dòng và giá lịch sử.

### Bài 3. JSON lồng nhau

API trả Order với một mảng **items**, mỗi item chứa productId, quantity và unitPriceInCents.

**Câu hỏi:** Để tìm những Order từng có Product P7, dữ liệu nên được ánh xạ thế nào?

**Gợi ý:** Tách Product và OrderLine thành node, tạo relationship để truy vấn qua graph. Dùng **UNWIND** nếu JSON đã được parse thành list/map đưa vào Neo4j bằng Driver.

### Bài 4. Foreign key bị thiếu

Một dòng Order có customer_id = C99 nhưng bảng Customer không có C99.

**Câu hỏi:** Nếu truy vấn nhập dùng MATCH Customer trước MERGE Order, chuyện gì xảy ra?

**Gợi ý:** Hàng không có Customer khớp sẽ không đi tiếp, dẫn đến Order có thể không được tạo. Cần phát hiện orphan từ nguồn và xử lý theo quy tắc trước khi ghi.

### Bài 5. Đổi tên khách hàng sau lần nhập đầu

Lần nhập 1 có C01 = "An", lần nhập 2 có C01 = "An Nguyễn".

**Câu hỏi:** Mẫu MERGE nào tránh sinh thêm Customer chỉ vì thay đổi tên?

**Đáp án tham khảo:**

~~~cypher
MERGE (c:Customer {customerId: 'C01'})
SET c.name = 'An Nguyễn';
~~~

Giữ **customerId** làm định danh, còn **name** là property có thể cập nhật.

### Bài 6. Kiểm tra sau migration

Sau khi nhập bộ dữ liệu mẫu, graph có 3 OrderLine nhưng chỉ có 2 relationship FOR_PRODUCT.

**Câu hỏi:** Có thể khẳng định import thành công vì số node đúng không?

**Gợi ý:** Không. Một OrderLine có thể thiếu Product do lỗi FK, MATCH không khớp hoặc logic import. Cần đối chiếu cả số relationship và truy vấn tìm OrderLine không có FOR_PRODUCT.

## 16. Ghi nhớ

**Lập ánh xạ từ CSV, JSON và nguồn quan hệ sang Neo4j** bắt đầu bằng **ngữ nghĩa dữ liệu**: chọn node cho thực thể có danh tính, relationship cho liên kết có ý nghĩa và property cho thuộc tính cần lưu. Giữ khóa nghiệp vụ ổn định, bảo tồn bội số và lịch sử khi ánh xạ bảng trung gian, thống nhất kiểu dữ liệu và xử lý null.

Để nhập đáng tin cậy, hãy **tạo uniqueness constraint trước**, tải node trước relationship, dùng **MERGE theo khóa**, kiểm tra foreign key/missing data, chia lô phù hợp và đối soát cả số lượng lẫn đường nối. Dù nguồn là CSV qua **LOAD CSV**, JSON thành tham số **UNWIND**, hay bảng SQL được export qua pipeline, một graph tốt phải giữ đúng ý nghĩa nguồn và trả lời được các truy vấn quan hệ mà ứng dụng cần.

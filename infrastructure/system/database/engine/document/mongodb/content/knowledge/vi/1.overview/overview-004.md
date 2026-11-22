# So sánh MongoDB với cơ sở dữ liệu quan hệ và các mô hình NoSQL khác

MongoDB là hệ quản trị cơ sở dữ liệu **hướng tài liệu (document database)**. Dữ liệu được tổ chức thành các tài liệu BSON trong collection, thay vì bắt buộc phân tách thành những hàng nằm trong nhiều bảng quan hệ. MongoDB thuộc nhóm NoSQL, nhưng **NoSQL không phải một mô hình dữ liệu duy nhất**: cơ sở dữ liệu key–value, wide-column, đồ thị và công cụ tìm kiếm cũng có cách tổ chức, truy vấn và đánh đổi riêng.

Bài học này đặt MongoDB cạnh cơ sở dữ liệu quan hệ (như PostgreSQL, MySQL) và những mô hình NoSQL phổ biến, tập trung vào câu hỏi thực tế: **dữ liệu có cấu trúc ra sao, ứng dụng thường đọc/ghi theo cách nào và cần bảo đảm tính đúng đắn đến mức nào?**

## 1. Bức tranh tổng quan về các mô hình lưu trữ

| Mô hình | Ví dụ hệ thống | Đơn vị dữ liệu và cách truy vấn nổi bật | Thường phù hợp khi |
|---|---|---|---|
| Quan hệ (relational) | PostgreSQL, MySQL, SQL Server | Bảng, hàng, cột; SQL, `JOIN`, ràng buộc khóa | Quan hệ phức tạp, tính toàn vẹn chặt chẽ, báo cáo và giao dịch nhiều thực thể |
| Document | MongoDB, Couchbase | Tài liệu JSON-like/BSON; truy vấn theo trường, mảng, tài liệu lồng nhau | Dữ liệu có cấu trúc lồng nhau, thay đổi theo từng loại bản ghi, thường đọc theo một aggregate |
| Key–value | Redis, Amazon DynamoDB (có thêm khả năng truy vấn theo thuộc tính) | Khóa ánh xạ đến giá trị; truy cập chủ yếu theo khóa | Cache, session, trạng thái tra cứu nhanh, workload có khóa truy cập rõ ràng |
| Wide-column / column-family | Apache Cassandra, ScyllaDB, HBase | Partition key, clustering key, hàng/cột có tổ chức theo phân vùng | Ghi phân tán quy mô lớn, truy vấn đã biết trước, phân bố dữ liệu qua nhiều nút |
| Graph | Neo4j, JanusGraph | Đỉnh, cạnh, thuộc tính; truy vấn theo đường đi và quan hệ | Mạng lưới kết nối nhiều bước, gợi ý theo quan hệ, phát hiện gian lận |
| Search engine / search-oriented | Elasticsearch, OpenSearch | Chỉ mục đảo, tìm kiếm văn bản và xếp hạng mức liên quan | Full-text search, tìm kiếm gần đúng, phân tích log và lọc tìm kiếm |

Tên sản phẩm trong bảng là ví dụ tiêu biểu, không phải phân loại tuyệt đối: một hệ thống có thể hỗ trợ nhiều kiểu truy vấn và nhiều kiểu lưu trữ. Chẳng hạn, PostgreSQL có `jsonb`, MongoDB có aggregation và `$lookup`, Redis có nhiều cấu trúc dữ liệu, còn DynamoDB ngoài đọc theo khóa còn hỗ trợ chỉ mục phụ và truy vấn có điều kiện. Vì thế, **khả năng thực tế của phiên bản/cấu hình và workload quan trọng hơn nhãn “SQL” hay “NoSQL”**.

## 2. Cùng một nghiệp vụ: đơn hàng trong SQL và MongoDB

Giả sử một hệ thống bán hàng cần lưu khách hàng, đơn hàng và các dòng sản phẩm. Một đơn hàng có nhiều dòng hàng; sau khi mua, giá và tên sản phẩm tại thời điểm đặt hàng phải được giữ lại để phục vụ hóa đơn và lịch sử.

### 2.1. Thiết kế quan hệ: nhiều bảng liên kết bằng khóa

Ví dụ SQL sau mang tính minh họa và sử dụng kiểu dữ liệu thông dụng:

```sql
CREATE TABLE customers (
    id VARCHAR(40) PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    id VARCHAR(40) PRIMARY KEY,
    customer_id VARCHAR(40) NOT NULL REFERENCES customers(id),
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE order_items (
    order_id VARCHAR(40) NOT NULL REFERENCES orders(id),
    line_no INTEGER NOT NULL,
    sku VARCHAR(40) NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents BIGINT NOT NULL CHECK (unit_price_cents >= 0),
    PRIMARY KEY (order_id, line_no)
);
```

Lược đồ tách các thực thể và dùng `FOREIGN KEY` để ràng buộc liên kết. Muốn lấy chi tiết đơn hàng, ứng dụng có thể dùng `JOIN`:

```sql
SELECT o.id, o.status, c.full_name,
       i.sku, i.product_name, i.quantity, i.unit_price_cents
FROM orders AS o
JOIN customers AS c ON c.id = o.customer_id
JOIN order_items AS i ON i.order_id = o.id
WHERE o.id = 'ord-1001'
ORDER BY i.line_no;
```

Kết quả trả về một hàng cho mỗi dòng sản phẩm. Phía ứng dụng thường gom các hàng đó thành một đối tượng đơn hàng gồm danh sách `items`.

### 2.2. Thiết kế MongoDB: tài liệu đại diện cho một đơn hàng

Một cách mô hình hóa là đặt các dòng hàng **bên trong** tài liệu đơn hàng; khách hàng vẫn có thể được tham chiếu bằng ID:

```javascript
db.orders.insertOne({
  _id: "ord-1001",
  customerId: "cus-42",
  status: "PAID",
  createdAt: ISODate("2026-01-15T10:00:00Z"),
  items: [
    { sku: "book-01", productName: "Sách MongoDB", quantity: 2,
      unitPriceCents: 150000 },
    { sku: "pen-07", productName: "Bút ghi chú", quantity: 1,
      unitPriceCents: 25000 }
  ],
  totalCents: 325000
});
```

Trong MongoDB, `orders` là **collection** và mỗi phần tử là một **document BSON**. BSON hỗ trợ kiểu dữ liệu như ngày giờ, số nguyên, số thập phân và ObjectId; MongoDB không lưu một chuỗi JSON thuần cho mọi tài liệu. Ví dụ dùng số nguyên biểu diễn đơn vị tiền nhỏ nhất (cents) để tránh sai số thường gặp khi dùng số thực dấu phẩy động cho tiền.

Đọc một đơn hàng có thể thực hiện bằng một truy vấn:

```javascript
db.orders.findOne({ _id: "ord-1001" });
```

Ứng dụng nhận cả mảng `items` trong một tài liệu, phù hợp với tình huống màn hình thường hiển thị toàn bộ đơn hàng. Đây là lợi thế của **embedding** khi các phần dữ liệu có cùng vòng đời và thường được đọc cùng nhau.

Tuy vậy, chọn document **không đồng nghĩa phải nhúng tất cả**. Thông tin khách hàng có thể tồn tại ở `customers`, sản phẩm có thể tồn tại ở `products` và các quan hệ vẫn được biểu diễn bằng `customerId`, `sku`. Khi cần kết hợp dữ liệu từ collection khác, MongoDB có thể dùng `$lookup` hoặc thực hiện nhiều truy vấn ở tầng ứng dụng.

### 2.3. Hai mô hình khác nhau ở chỗ nào?

```text
Quan hệ (điển hình)                 MongoDB document (điển hình)

customers                          customers
  cus-42                             cus-42
     |                                  |
orders                              orders
  ord-1001                            ord-1001
     |                                  |
order_items                          +-- items[0]
  (ord-1001, 1)                      +-- items[1]
  (ord-1001, 2)

Nhiều hàng, ghép khi truy vấn      Một tài liệu chứa các dòng hàng
```

Không có mô hình nào mặc nhiên nhanh hoặc tiết kiệm hơn. Trong mô hình quan hệ, join với chỉ mục phù hợp có thể rất hiệu quả; trong MongoDB, nhúng dữ liệu giúp giảm số lượt lấy dữ liệu nhưng có thể làm tài liệu lớn hơn và tăng chi phí cập nhật.

## 3. MongoDB so với cơ sở dữ liệu quan hệ

| Tiêu chí | Cơ sở dữ liệu quan hệ | MongoDB |
|---|---|---|
| Cấu trúc chính | Bảng với cột và kiểu dữ liệu đã khai báo | Collection chứa BSON document, có thể có các trường khác nhau |
| Lược đồ | Thường quy định rõ bằng DDL, khóa và constraint | Linh hoạt hơn; có thể dùng JSON Schema validation ở mức collection |
| Quan hệ | `PRIMARY KEY`, `FOREIGN KEY`, `JOIN` là các cơ chế cốt lõi | Tham chiếu bằng ID hoặc nhúng; có `$lookup`, nhưng không có foreign key tự động như SQL thông dụng |
| Chuẩn hóa | Dễ chuẩn hóa để giảm lặp dữ liệu, chia sẻ thực thể | Có thể nhúng/phi chuẩn hóa có chủ đích để tối ưu thao tác phổ biến |
| Truy vấn | SQL, join đa bảng, group/order/window function tùy hệ | Query API, aggregation pipeline, chỉ mục và `$lookup` |
| Giao dịch | ACID nhiều hàng/bảng là cách dùng phổ biến | Ghi một document có tính nguyên tử; hỗ trợ giao dịch nhiều document, collection và shard với điều kiện triển khai tương ứng |
| Tính toàn vẹn | Khóa ngoại, CHECK, UNIQUE, NOT NULL và transaction | Unique index, validation, transaction; nhiều liên kết nghiệp vụ cần được ứng dụng bảo đảm |
| Mở rộng | Có thể mở rộng dọc, đọc qua replica, partition hoặc sharding tùy sản phẩm | Có replica set và sharding tích hợp; vẫn đòi hỏi chọn shard key phù hợp |
| Thay đổi dữ liệu | Migration thường điều chỉnh schema và dữ liệu | Thường dễ thêm trường, nhưng ứng dụng vẫn cần quản lý phiên bản tài liệu và migration |
| Phân tích, báo cáo | SQL rất mạnh ở các phép kết hợp và tổng hợp phức tạp | Aggregation mạnh với dữ liệu document; báo cáo nhiều chiều có thể cần thiết kế thêm hoặc hệ thống phân tích riêng |

### 3.1. Schema linh hoạt không có nghĩa là không có schema

MongoDB cho phép hai document trong cùng collection có các trường khác nhau:

```javascript
{ _id: "p-1", name: "Bàn phím", attributes: { layout: "US" } }
{ _id: "p-2", name: "Áo khoác", attributes: { size: "M", color: "đen" } }
```

Điều này thuận tiện cho danh mục sản phẩm có thuộc tính riêng theo loại hàng. Tuy nhiên, nếu ứng dụng tùy ý lúc lưu `price`, lúc lưu `unitPrice`, lúc lưu chuỗi và lúc lưu số, code đọc dữ liệu sẽ phức tạp và dễ lỗi. MongoDB có thể kiểm tra cấu trúc bằng **collection validator**, ngoài validation tại API/ứng dụng. Tính linh hoạt chỉ có giá trị khi có **quy ước rõ về tên trường, kiểu dữ liệu, phiên bản tài liệu và cách nâng cấp dữ liệu cũ**.

Ngược lại, RDBMS hiện đại cũng có trường JSON/JSONB và có thể phối hợp dữ liệu quan hệ với thuộc tính linh hoạt. Việc một bản ghi có trường biến đổi không đủ để kết luận phải chọn MongoDB.

### 3.2. `JOIN` so với embedding và `$lookup`

Trong cơ sở dữ liệu quan hệ, liên kết là thực thể nền tảng. Ứng dụng có thể kết hợp khách hàng, đơn hàng, dòng hàng, chương trình khuyến mãi mà không cần sao chép mọi thông tin vào mỗi hàng.

MongoDB hỗ trợ `$lookup` để kết nối collection khi cần, ví dụ lấy tên khách hàng của một đơn hàng:

```javascript
db.orders.aggregate([
  { $match: { _id: "ord-1001" } },
  { $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
  } },
  { $unwind: "$customer" },
  { $project: { status: 1, items: 1, customerName: "$customer.fullName" } }
]);
```

Điều này chứng minh MongoDB **có thể join ở mức truy vấn**, nhưng không nên lấy `$lookup` làm chiến lược mặc định cho mọi quan hệ. Tốc độ phụ thuộc khối lượng dữ liệu, chỉ mục, bộ lọc, cách phân bố dữ liệu và kế hoạch thực thi. Nếu nghiệp vụ đòi hỏi truy vấn ad hoc qua rất nhiều thực thể liên kết, mô hình quan hệ thường tự nhiên và dễ duy trì hơn.

### 3.3. Ví dụ các truy vấn phổ biến

**Lấy đơn hàng mới nhất của một khách hàng:**

```sql
-- SQL
SELECT id, status, created_at
FROM orders
WHERE customer_id = 'cus-42'
ORDER BY created_at DESC
LIMIT 10;
```

```javascript
// MongoDB (mongosh)
db.orders.find(
  { customerId: "cus-42" },
  { status: 1, createdAt: 1 }
).sort({ createdAt: -1 }).limit(10);

// Chỉ mục hữu ích cho bộ lọc + sắp xếp này
db.orders.createIndex({ customerId: 1, createdAt: -1 });
```

**Đếm số đơn hàng theo trạng thái:**

```sql
SELECT status, COUNT(*) AS total
FROM orders
GROUP BY status;
```

```javascript
db.orders.aggregate([
  { $group: { _id: "$status", total: { $sum: 1 } } },
  { $sort: { total: -1 } }
]);
```

SQL và MongoDB đều giải quyết được các bài toán lọc, sắp xếp, đếm và tổng hợp phổ biến. Cần so sánh **truy vấn thực tế trên dữ liệu thực tế** thay vì kết luận chỉ từ cú pháp.

## 4. Khi nào nhúng document, khi nào tham chiếu?

Đây là quyết định thiết kế quan trọng nhất khi sử dụng MongoDB.

### Nên cân nhắc embedding khi

- Thành phần con được **đọc cùng** đối tượng cha trong phần lớn truy vấn, như các dòng hàng của một đơn hàng.
- Quan hệ có số lượng con **hữu hạn và dự đoán được**, ví dụ địa chỉ giao hàng của một hóa đơn hoặc vài thông số cấu hình.
- Dữ liệu con cùng vòng đời với cha, ít cần truy vấn độc lập và cần cập nhật nguyên tử trong **cùng một document**.
- Chấp nhận lưu bản chụp thông tin tại một thời điểm: `productName`, `unitPriceCents` của đơn hàng lịch sử không cần tự đổi theo sản phẩm hiện tại.

### Nên cân nhắc referencing khi

- Dữ liệu con tăng không giới hạn, chẳng hạn hàng triệu sự kiện của một thiết bị hoặc bình luận dưới bài viết.
- Một thực thể được nhiều đối tượng cùng sử dụng và cần một nguồn giá trị hiện tại, như tài khoản người dùng hay tồn kho sản phẩm.
- Dữ liệu con có vòng đời, quyền truy cập, nhịp cập nhật hoặc các truy vấn độc lập khác biệt.
- Quan hệ nhiều–nhiều phức tạp hoặc tài liệu có nguy cơ phình to, gây tốn băng thông và tài nguyên khi đọc/ghi.

**Giới hạn cần nhớ:** mỗi BSON document trong MongoDB có kích thước tối đa **16 MiB**. Mảng nhúng tăng mãi theo thời gian sẽ gặp giới hạn này và gây bất lợi ngay từ trước khi chạm giới hạn. Với log/sự kiện tăng liên tục, nên dùng collection riêng, mô hình bucket/time-series phù hợp hoặc nền tảng chuyên dụng tùy workload.

Một mô hình thực tế có thể kết hợp cả hai: `orders.items` nhúng snapshot dòng hàng; `orders.customerId` tham chiếu khách hàng; `products` và `inventory` là các collection riêng. **Mô hình hóa theo ranh giới nghiệp vụ và truy vấn**, không theo một nguyên tắc “tất cả phải nhúng” hoặc “tất cả phải tách”.

## 5. Giao dịch, tính nguyên tử và tính nhất quán

Một hiểu lầm phổ biến là “NoSQL không có transaction” hoặc “MongoDB không đảm bảo ACID”. Hai nhận định này không đúng ở dạng tuyệt đối.

### 5.1. Cập nhật một document

MongoDB đảm bảo một thao tác ghi lên **một document** có tính nguyên tử, kể cả khi thay đổi nhiều trường hoặc phần tử trong document đó. Ví dụ trừ tồn kho với điều kiện còn hàng:

```javascript
const result = db.inventory.updateOne(
  { _id: "book-01", stock: { $gte: 1 } },
  { $inc: { stock: -1 } }
);

if (result.modifiedCount !== 1) {
  print("Hết hàng hoặc sản phẩm không tồn tại");
}
```

Bộ lọc và cập nhật chạy như một thao tác trên document, nên hai yêu cầu đồng thời không đơn giản cùng đọc một giá trị tồn kho cũ rồi ghi đè nhau. Cần kiểm tra `modifiedCount` và xử lý lỗi ở ứng dụng; ví dụ chưa giải quyết toàn bộ quy trình đặt hàng.

### 5.2. Giao dịch liên quan nhiều document

Nghiệp vụ “tạo đơn hàng + trừ kho + ghi thanh toán nội bộ” có thể liên quan nhiều document. MongoDB **hỗ trợ multi-document transaction** khi triển khai phù hợp (replica set hoặc sharded cluster). Trong transaction, các thay đổi có thể được commit cùng nhau hoặc rollback khi thất bại. Nhưng transaction có chi phí phối hợp và tài nguyên; thiết kế document tốt vẫn nên ưu tiên các ranh giới nguyên tử hợp lý.

RDBMS thường có hệ sinh thái constraint và transaction đa bảng rất thuận tiện cho giao dịch nhiều thực thể. Dù dùng MongoDB hay SQL, cần nghĩ rõ về **điều kiện đồng thời**, retry, lỗi mạng, idempotency và bất biến nghiệp vụ. Thanh toán với hệ thống ngoài còn cần cơ chế tích hợp (như outbox/saga hoặc idempotency key), vì một transaction cơ sở dữ liệu không tự biến API thanh toán bên ngoài thành một phần của transaction.

### 5.3. Replica set, read concern và write concern

MongoDB hỗ trợ **replica set** với một primary nhận các thao tác ghi thông thường và các secondary nhân bản dữ liệu. Đọc từ secondary có thể nhìn thấy dữ liệu chậm hơn primary vì độ trễ replication.

- **Write concern** quy định mức xác nhận của thao tác ghi, ví dụ `w: "majority"` yêu cầu xác nhận theo đa số thành viên có quyền biểu quyết theo cơ chế MongoDB.
- **Read concern** quy định đặc tính dữ liệu mà thao tác đọc được phép nhìn thấy, ví dụ `majority` hoặc `snapshot` trong các ngữ cảnh hỗ trợ.
- **Read preference** chọn nơi đọc (primary hay secondary); nó khác với read concern và ảnh hưởng độ mới của dữ liệu.

Không nên tuyên bố rằng “MongoDB luôn strongly consistent” hoặc “MongoDB luôn eventually consistent” mà bỏ qua các tham số và cách đọc/ghi. Đảm bảo cụ thể phụ thuộc read preference, read/write concern, phiên làm việc (session) và mô hình triển khai. Nếu nghiệp vụ cần read-your-writes, causal consistency hay linearizable read, phải chọn cấu hình và chuỗi thao tác tương ứng, đồng thời kiểm chứng theo tài liệu của phiên bản đang dùng.

### 5.4. CAP không phải bảng xếp hạng sản phẩm

Định lý CAP nói về lựa chọn giữa **consistency** và **availability khi xảy ra network partition** trong hệ phân tán, với định nghĩa kỹ thuật cụ thể. Không thể gắn nhãn “mọi RDBMS là CA” hoặc “mọi NoSQL là AP”. PostgreSQL trên một nút, một cụm MongoDB replica set và một cụm Cassandra có cấu hình replication khác nhau dẫn đến hành vi khác nhau. Ngoài CAP còn phải xét độ trễ, độ bền, cô lập giao dịch và cách xử lý xung đột; khi hệ thống hoạt động bình thường, đây thường là các đánh đổi được gặp hằng ngày.

## 6. MongoDB so với các mô hình NoSQL khác

### 6.1. MongoDB và key–value store (ví dụ Redis)

Một key–value store tối ưu thao tác lấy/ghi theo khóa:

```text
SET session:abc123 "{...}"
GET session:abc123
EXPIRE session:abc123 1800
```

Redis hỗ trợ nhiều cấu trúc dữ liệu và cơ chế bổ sung ngoài chuỗi key–value; các lệnh trên chỉ minh họa trường hợp đơn giản. Với session có thời hạn, cache theo khóa, bộ đếm hoặc dữ liệu trạng thái truy cập lặp lại, key–value thường tự nhiên hơn document database.

MongoDB thuận tiện hơn khi cần **lọc nhiều trường**, tìm trong tài liệu lồng nhau, chỉ mục trên thuộc tính và tổng hợp dữ liệu lâu dài. Redis có thể lưu dữ liệu bền vững nếu được cấu hình, nên không được đánh đồng Redis với “RAM không bao giờ lưu xuống đĩa”. Việc chọn Redis hay MongoDB còn phụ thuộc SLA, kích thước working set, mô hình lưu trữ và chi phí vận hành.

### 6.2. MongoDB và wide-column (ví dụ Cassandra)

Cassandra thường bắt đầu từ **truy vấn cần hỗ trợ** để thiết kế partition key, clustering key và các bảng có thể phi chuẩn hóa. Nó phát huy thế mạnh khi workload gồm nhiều lượt ghi qua cụm phân tán, lưu lượng lớn và mô hình truy vấn có thể dự đoán trước. Ví dụ sự kiện thiết bị tra theo `(device_id, day)` và sắp xếp theo thời gian.

MongoDB thuận tiện hơn với cấu trúc tài liệu lồng nhau, truy vấn linh hoạt theo thuộc tính và thay đổi yêu cầu sản phẩm. Cassandra không cung cấp kiểu join/aggregation ad hoc như RDBMS; ngược lại MongoDB cũng không tự động vượt Cassandra ở mọi workload ghi. Cần tránh partition quá lớn/hot partition, xác định yêu cầu consistency và đo hiệu năng theo truy vấn đã chọn.

### 6.3. MongoDB và graph database (ví dụ Neo4j)

Đối với mạng xã hội, mỗi người có thể có hàng nghìn quan hệ; câu hỏi “bạn của bạn của tôi”, “đường đi ngắn nhất” hay “mẫu liên kết đáng ngờ” đòi hỏi duyệt nhiều bước. Graph database lưu **đỉnh và cạnh** như phần tử cốt lõi và thường có ngôn ngữ truy vấn đường đi riêng (ví dụ Cypher trong Neo4j).

MongoDB có thể lưu ID liên kết trong mảng, dùng `$lookup` và một số toán tử đồ thị như `$graphLookup`. Với quan hệ ít bước hoặc dữ liệu ít kết nối, cách này có thể đủ. Khi đồ thị lớn, liên kết dày và truy vấn nhiều bước chiếm phần lớn workload, graph database đáng được đánh giá chuyên sâu.

### 6.4. MongoDB và search engine (Elasticsearch/OpenSearch)

Tìm theo `_id`, lọc `status`, sắp xếp `createdAt` khác với tìm kiếm văn bản có **stemming, typo tolerance, relevance ranking, autocomplete** và nhiều điều kiện phân tích. MongoDB có chỉ mục và khả năng tìm kiếm văn bản; một số dịch vụ/triển khai còn cung cấp công cụ search chuyên dụng. Elasticsearch/OpenSearch xây dựng quanh chỉ mục tìm kiếm và phân tích, phù hợp khi chất lượng tìm kiếm là yêu cầu trọng tâm.

Một kiến trúc thường gặp là giữ dữ liệu giao dịch ở MongoDB hoặc SQL và đồng bộ các trường cần tìm kiếm sang search index. Lúc đó cần quản lý độ trễ đồng bộ, retry, chỉ mục lỗi thời và khả năng tái xây dựng index; **không nên ngầm giả định hai kho dữ liệu đồng bộ tức thời**.

## 7. Hiệu năng và khả năng mở rộng: những yếu tố cần đo

Không thể suy ra tốc độ từ “document nhanh hơn join” hay “NoSQL mở rộng ngang tốt hơn SQL” mà không biết truy vấn. Những yếu tố quan trọng gồm:

1. **Mẫu truy cập:** đọc một đơn với các `items`, tìm đơn theo `customerId`, tổng hợp doanh thu theo tháng hay duyệt mạng quan hệ nhiều bước?
2. **Chỉ mục:** chỉ mục phục vụ bộ lọc và sắp xếp sẽ giảm dữ liệu phải quét, nhưng mỗi index tiêu tốn RAM/đĩa và tăng chi phí ghi. Dùng `explain()` để xem kế hoạch truy vấn thực tế.
3. **Độ lớn document:** nhúng quá nhiều phần tử khiến payload lớn, cập nhật tốn chi phí và tăng khả năng cạnh tranh trên cùng document.
4. **Kiểu truy vấn theo phân vùng:** khi sharding, phân bố shard key quyết định khả năng phân tải. Khóa có độ phân biệt thấp hoặc tăng đơn điệu có thể gây hot shard; truy vấn không có shard key có thể cần gửi đến nhiều shard.
5. **Tải đồng thời và độ bền:** benchmark phải phản ánh read/write mix, độ trễ p95/p99, write concern, read concern, dữ liệu vừa cache hay không, số index và cấu hình máy.
6. **Chi phí vận hành:** RAM, ổ đĩa, replica, backup/restore, bảo mật, quan sát hệ thống, cập nhật phiên bản và kỹ năng đội ngũ đều là chi phí thực tế.

MongoDB cung cấp replication và sharding; các RDBMS cũng có replication, partitioning, extension hoặc nền tảng distributed SQL. Không nên chọn MongoDB **chỉ vì** dự kiến “sau này cần scale ngang”. Nếu truy vấn phụ thuộc nhiều quan hệ hoặc cần constraint phức tạp, phân tán có thể làm bài toán khó hơn dù hệ quản trị nào được chọn.

## 8. Ma trận lựa chọn theo tình huống

| Tình huống | Lựa chọn nên đánh giá đầu tiên | Lý do và lưu ý |
|---|---|---|
| Sổ cái kế toán, số dư, thanh toán lõi | RDBMS có transaction/constraint mạnh | Bất biến nhiều bảng, kiểm toán và đối soát quan trọng hơn việc linh hoạt thuộc tính |
| Danh mục sản phẩm có nhiều loại thuộc tính | MongoDB document **hoặc** PostgreSQL `jsonb` | Document linh hoạt và dễ trả dữ liệu dạng lồng nhau; vẫn phải quản lý schema/index |
| Đơn hàng với danh sách mặt hàng giới hạn | MongoDB (nhúng snapshot) **hoặc** RDBMS | MongoDB đọc aggregate thuận tiện; SQL phù hợp nếu nhiều truy vấn liên bảng và constraint |
| Session/cache có TTL, truy cập chủ yếu bằng ID | Redis/key–value | Luồng truy cập theo khóa và vòng đời ngắn; quyết định chính sách persistence/cache miss |
| Dòng sự kiện cực lớn, đọc theo thiết bị và thời gian | Cassandra/ScyllaDB, time-series DB hoặc MongoDB time series | So sánh ingest, retention, partition, khả năng query và vận hành trên dữ liệu thật |
| Gợi ý kết bạn, phát hiện chuỗi quan hệ bất thường | Graph database | Truy vấn theo đường đi và kết nối nhiều bước là nghiệp vụ chính |
| Search sản phẩm có lỗi chính tả, xếp hạng độ phù hợp | Search engine chuyên dụng hoặc search tích hợp phù hợp | Chất lượng tìm kiếm, index và đồng bộ là yêu cầu quan trọng |
| Báo cáo tài chính ad hoc, nhiều phép kết hợp | RDBMS/analytics warehouse | SQL và phép tổng hợp đa nguồn thường phù hợp hơn mô hình chỉ đọc một aggregate |

Ma trận là **điểm bắt đầu để thử nghiệm**, không phải quyết định bắt buộc. Ví dụ một ứng dụng thương mại điện tử có thể dùng PostgreSQL cho thanh toán/đơn hàng, MongoDB cho danh mục phong phú, Redis cho cache và OpenSearch cho tìm kiếm. Ngược lại, ứng dụng nhỏ thường hiệu quả hơn khi bắt đầu bằng **một cơ sở dữ liệu phù hợp** và chỉ thêm hệ thống mới khi có bằng chứng về nhu cầu.

## 9. Quy trình ra quyết định cho một dự án

**Bước 1 — Liệt kê nghiệp vụ và bất biến.** Ví dụ: “không bán vượt tồn kho”, “mỗi mã giao dịch chỉ xử lý một lần”, “tên sản phẩm trên hóa đơn không đổi sau khi đặt”. Xác định ranh giới transaction và phần nào cần tham chiếu chính xác.

**Bước 2 — Liệt kê 5–10 truy vấn chủ đạo.** Ghi rõ điều kiện lọc, số bản ghi trả về, tần suất đọc/ghi, sort, thống kê, yêu cầu độ mới của dữ liệu và SLA. Mẫu truy vấn quan trọng hơn sơ đồ đối tượng ban đầu.

**Bước 3 — Vẽ mô hình dữ liệu theo workload.** Với MongoDB, đánh dấu cái gì được embed, cái gì reference; kiểm tra mảng tăng không giới hạn, khả năng cập nhật đồng thời và nhu cầu index. Với SQL, xác định khóa, constraint, bảng liên kết và các query nhiều join.

**Bước 4 — Xác định vận hành và dữ liệu phân tán.** Cần backup/restore ra sao? SLA sau node failure? Cần đọc từ secondary? Có chấp nhận eventual propagation giữa hệ thống chính và search index không? Chọn read/write concern hoặc isolation phù hợp từng nghiệp vụ.

**Bước 5 — Làm prototype và benchmark.** Nạp dữ liệu ở quy mô, phân bố và độ biến động gần thực tế; chạy các truy vấn chủ đạo và workload concurrent. Đo độ trễ p95/p99, throughput, CPU/RAM, dung lượng index, độ phức tạp code và công sức vận hành. Kiểm thử cả khi mất nút hoặc mạng có sự cố nếu hệ thống yêu cầu tính sẵn sàng cao.

**Bước 6 — Chốt quyền sở hữu dữ liệu.** Nếu dùng nhiều hệ thống, cần chỉ định nguồn dữ liệu chuẩn, phương thức đồng bộ, cơ chế sửa sai và cách tái xây dựng bản sao. Tránh để mỗi hệ thống đều được cập nhật độc lập mà không có quy tắc nhất quán.

## 10. Những hiểu lầm cần tránh

| Nhận định thiếu chính xác | Cách hiểu đúng |
|---|---|
| “MongoDB không có schema.” | Schema có thể linh hoạt, nhưng cấu trúc dữ liệu vẫn tồn tại và có thể được validator/ứng dụng kiểm soát. |
| “MongoDB không hỗ trợ transaction hoặc join.” | MongoDB có transaction nhiều document và `$lookup`; cần xét chi phí và điều kiện sử dụng. |
| “RDBMS không lưu được JSON.” | Nhiều RDBMS hiện đại hỗ trợ JSON cùng index và các toán tử truy vấn. |
| “Dùng MongoDB thì cứ nhúng toàn bộ.” | Nhúng có giới hạn kích thước, cập nhật và vòng đời; tham chiếu vẫn cần thiết. |
| “NoSQL luôn nhanh hơn SQL.” | Hiệu năng phụ thuộc truy vấn, mô hình, index, cache, concurrency và cấu hình. |
| “NoSQL không cần quan tâm tính nhất quán.” | Mọi hệ lưu trữ đều cần mô tả rõ những đảm bảo và bất biến nghiệp vụ. |
| “Một sản phẩm NoSQL thay thế mọi sản phẩm khác.” | Key–value, document, wide-column, graph và search tối ưu các kiểu truy cập khác nhau. |

## 11. Bài tập vận dụng

**Tình huống A — Profile người dùng.** Profile gồm tên, cài đặt giao diện và tối đa ba địa chỉ giao hàng. Màn hình profile luôn tải toàn bộ thông tin; mỗi người thường chỉ sửa profile của mình. Hãy đề xuất cách dùng embedding và giải thích vì sao. Điều gì thay đổi nếu một địa chỉ được chia sẻ bởi hàng nghìn tài khoản?

**Tình huống B — Bình luận bài viết.** Một bài viết có thể có hàng triệu bình luận và bình luận được tải theo trang, sắp xếp mới nhất trước. Có nên nhúng tất cả vào một document bài viết? Hãy đề xuất collection, trường tham chiếu và index phù hợp.

**Tình huống C — Đặt hàng và trừ kho.** Khách hàng gửi hai yêu cầu đặt hàng gần như đồng thời trong khi còn một sản phẩm. Hãy phân biệt thao tác trừ kho nguyên tử trong một document với transaction tạo đơn + trừ kho. Nếu cổng thanh toán ngoài đã thu tiền nhưng giao dịch DB lỗi, hệ thống cần thiết kế bù trừ và idempotency như thế nào?

**Tình huống D — Tìm sản phẩm.** Ứng dụng cần lọc theo danh mục, giá và thương hiệu, đồng thời cho phép gõ sai chính tả và xếp hạng kết quả theo độ liên quan. Hãy chỉ ra phần nào MongoDB query/index có thể giải quyết và khi nào cần đánh giá một search engine chuyên dụng.

## Kết luận

MongoDB phù hợp khi dữ liệu có cấu trúc document/lồng nhau, các phần của một aggregate thường được đọc cùng nhau và schema cần thích nghi theo đặc thù từng thực thể. Cơ sở dữ liệu quan hệ thường nổi bật ở mô hình quan hệ chặt chẽ, ràng buộc toàn vẹn, giao dịch đa thực thể và truy vấn SQL đa dạng. Những mô hình NoSQL khác — key–value, wide-column, graph và search — giải quyết các kiểu truy cập riêng mà MongoDB không nhất thiết tối ưu bằng.

Lựa chọn tốt dựa vào **mô hình dữ liệu + truy vấn thật + bất biến nghiệp vụ + vận hành + benchmark**, không dựa vào giả định “SQL cũ, NoSQL mới” hoặc “MongoDB nhanh hơn vì không có join”.

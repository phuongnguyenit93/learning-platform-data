# Các mẫu truy cập dữ liệu trong NoSQL: tra theo khóa, lọc, sắp xếp, tổng hợp và duyệt quan hệ

## 1. Mẫu truy cập dữ liệu là gì?

**Mẫu truy cập (access pattern)** mô tả cách ứng dụng thường xuyên yêu cầu và lấy dữ liệu: biết trước khóa nào, lọc theo điều kiện gì, cần thứ tự ra sao, có phải tính toán trên nhiều bản ghi không và có cần đi qua quan hệ giữa các thực thể không. Đây là một đầu vào quan trọng khi thiết kế NoSQL, bởi mỗi họ cơ sở dữ liệu hỗ trợ và tối ưu các kiểu truy cập khác nhau.

Ví dụ, một ứng dụng bán hàng cần:

- Lấy chi tiết đơn hàng `O1001`.
- Liệt kê các đơn đã thanh toán của khách `C001` trong tháng.
- Hiển thị 20 đơn mới nhất của một khách hàng.
- Tính doanh thu theo khách hàng trong tháng.
- Tìm các sản phẩm mà khách `C001` từng mua thông qua quan hệ khách hàng → đơn hàng → sản phẩm.

Năm yêu cầu này có thể đọc cùng một tập dữ liệu nhưng tương ứng với **năm mẫu truy cập khác nhau**. Việc lưu được dữ liệu vào NoSQL không đồng nghĩa mọi mẫu truy cập đều nhanh: tốc độ còn phụ thuộc khóa, chỉ mục (index), cách phân vùng, bố trí quan hệ và khối lượng dữ liệu phải quét.

### Dữ liệu minh họa

Các ví dụ chính sử dụng cú pháp **MongoDB (`mongosh`)** với collection `orders`. Một document đơn hàng có dạng:

```javascript
{
  _id: "O1001",
  customerId: "C001",
  status: "PAID",
  createdAt: ISODate("2026-11-08T09:30:00Z"),
  total: 780000,
  items: [
    { productId: "P11", quantity: 2, unitPrice: 250000 },
    { productId: "P15", quantity: 1, unitPrice: 280000 }
  ]
}
```

Giả sử `total` là tổng tiền của đơn theo đơn vị VND; `status` nhận các giá trị như `PENDING`, `PAID` và `CANCELLED`. Collection `customers` lưu thông tin khách hàng, còn `products` lưu thông tin sản phẩm. Những ngày, mã và giá trị trong bài chỉ nhằm minh họa.

MongoDB được dùng để diễn đạt rõ các mẫu truy vấn document; phần duyệt quan hệ còn có ví dụ **Cypher/Neo4j**. Cú pháp và đặc tính hiệu năng của MongoDB không tự động áp dụng cho Redis, Cassandra, DynamoDB hay mọi hệ NoSQL khác.

## 2. Tra theo khóa (key lookup / point lookup)

**Mục tiêu:** tìm một bản ghi hoặc một nhóm dữ liệu nhỏ nhờ khóa đã biết.

Ví dụ API `GET /orders/O1001` biết sẵn mã đơn `O1001`. Trong MongoDB, trường `_id` có chỉ mục mặc định:

```javascript
db.orders.findOne({ _id: "O1001" })
```

Trong hệ key–value như Redis, ứng dụng có thể lưu toàn bộ đơn hàng dưới khóa `order:O1001` và đọc bằng:

```text
GET order:O1001
```

Đây là kiểu truy cập trực tiếp thường có chi phí thấp vì hệ thống có thể xác định bản ghi từ khóa, thay vì kiểm tra mọi đơn hàng.

**Phân biệt khóa chính và thuộc tính tìm kiếm:** truy vấn `findOne({ customerId: "C001" })` không phải tra trực tiếp một đơn theo khóa chính; một khách có thể có nhiều đơn. Tương tự, tra khách hàng theo `email` chỉ nhanh khi có chỉ mục thích hợp (và nên có ràng buộc duy nhất nếu email được sử dụng làm định danh nghiệp vụ).

```javascript
db.customers.createIndex({ email: 1 }, { unique: true })
db.customers.findOne({ email: "lan@example.com" })
```

Ở hệ phân tán, **partition key** còn quyết định nút lưu dữ liệu. Truy vấn thiếu partition key có thể buộc hệ thống hỏi nhiều phân vùng. Cũng cần tránh một khóa bị truy cập nóng bất thường (`hot key`), khiến một nút chịu tải vượt trội.

**Khi phù hợp:** màn hình chi tiết, tra trạng thái phiên, giỏ hàng theo mã người dùng, truy xuất cấu hình theo tên khóa.

## 3. Lọc theo điều kiện (filtering / range query)

**Mục tiêu:** lấy các bản ghi thỏa mãn một hoặc nhiều điều kiện. Điều kiện có thể là bằng (`=`), thuộc tập giá trị (`IN`), khoảng thời gian, so sánh số hoặc kết hợp bằng `AND`/`OR`.

Ví dụ: lấy đơn `PAID` của khách `C001` được tạo trong tháng 11/2026:

```javascript
db.orders.find(
  {
    customerId: "C001",
    status: "PAID",
    createdAt: {
      $gte: ISODate("2026-11-01T00:00:00Z"),
      $lt: ISODate("2026-12-01T00:00:00Z")
    }
  },
  { _id: 1, createdAt: 1, total: 1 }
)
```

Trong ví dụ, `customerId` và `status` là điều kiện **bằng**, còn `createdAt` là điều kiện **khoảng**. Dùng khoảng nửa mở `[đầu tháng, đầu tháng kế tiếp)` giúp tránh phụ thuộc vào độ chính xác của mili giây hoặc thời điểm cuối ngày. Hãy xác định rõ múi giờ của báo cáo; ví dụ trên dùng UTC.

Một chỉ mục ghép phù hợp cho truy vấn kiểu này có thể là:

```javascript
db.orders.createIndex({
  customerId: 1,
  status: 1,
  createdAt: -1
})
```

Các trường so sánh bằng được đặt trước trường khoảng để cơ sở dữ liệu thu hẹp vùng chỉ mục cần đọc. Tuy nhiên, thứ tự tốt nhất phụ thuộc **truy vấn thực tế**, độ phân biệt của dữ liệu và yêu cầu sắp xếp; không có một chỉ mục dùng hiệu quả cho mọi tổ hợp điều kiện.

Một số lưu ý khi thiết kế:

- Lọc bằng chỉ mục khác với quét toàn bộ collection rồi kiểm tra từng document. Khi tập dữ liệu lớn, quét toàn bộ có thể rất tốn I/O.
- Một điều kiện hiếm khi xuất hiện thường chọn lọc dữ liệu tốt hơn điều kiện xuất hiện ở hầu hết bản ghi; cần xem cả **selectivity** và số kết quả trả về.
- Trả về đúng các trường cần dùng bằng **projection** có thể giảm dữ liệu truyền về; chỉ mục có thể hoặc không thể bao phủ toàn bộ truy vấn.
- Trong Cassandra hay một số hệ wide-column, phạm vi truy vấn thường bị ràng buộc chặt bởi partition key và clustering columns; không thể suy ra rằng bộ lọc tùy ý sẽ hiệu quả như trong hệ document có secondary index.

**Khi phù hợp:** tìm kiếm đơn theo trạng thái và ngày, danh sách giao dịch theo tài khoản, sự kiện theo khoảng thời gian, bộ lọc nhiều tiêu chí.

## 4. Sắp xếp và lấy Top-N (sorting / ordered reads)

**Mục tiêu:** đọc dữ liệu theo thứ tự có ý nghĩa, chẳng hạn mới nhất trước, giá thấp nhất trước hoặc điểm xếp hạng cao nhất trước. Thực tế thường đi kèm giới hạn kết quả và phân trang.

Ví dụ: lấy 20 đơn `PAID` mới nhất của khách `C001`:

```javascript
db.orders
  .find({ customerId: "C001", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
```

`createdAt: -1` xếp thời gian giảm dần; `_id: -1` dùng làm tiêu chí phụ để **thứ tự ổn định** khi nhiều đơn có cùng thời điểm tạo. Nếu không có quy tắc phụ, thứ tự giữa các bản ghi bằng nhau ở khóa sắp xếp có thể không xác định.

Chỉ mục ghép minh họa:

```javascript
db.orders.createIndex({
  customerId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
})
```

Với điều kiện bằng trên `customerId` và `status`, MongoDB có thể đi theo thứ tự `createdAt`, `_id` trong chỉ mục để đọc một lượng nhỏ bản ghi. Nếu không có chỉ mục tương thích, hệ thống có thể phải tập hợp rồi sắp xếp nhiều kết quả trong bộ nhớ hoặc trên đĩa.

### Phân trang sâu: `skip` và cursor

Trang đầu dùng `limit(20)` khá đơn giản. Nhưng gọi `skip(100000).limit(20)` thường làm việc nhiều vì phải đi qua rất nhiều kết quả trước đó. Khi duyệt danh sách dài, hãy cân nhắc **keyset/cursor pagination**: gửi cặp khóa sắp xếp của phần tử cuối trang trước làm mốc.

```javascript
// Giá trị lấy từ bản ghi cuối của trang trước.
const lastCreatedAt = ISODate("2026-11-08T09:30:00Z");
const lastId = "O1001";

db.orders
  .find({
    customerId: "C001",
    status: "PAID",
    $or: [
      { createdAt: { $lt: lastCreatedAt } },
      { createdAt: lastCreatedAt, _id: { $lt: lastId } }
    ]
  })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
```

Ví dụ này giả định `_id` cùng một kiểu dữ liệu có thể so sánh và dùng thứ tự giảm dần. Cursor cần giữ cả hai thành phần để xử lý trường hợp trùng `createdAt`. Với dữ liệu đang thay đổi, phân trang vẫn có thể thấy tập kết quả dịch chuyển; khi yêu cầu một ảnh chụp nhất quán, ứng dụng phải thiết kế thêm cơ chế phù hợp.

**Khi phù hợp:** feed mới nhất, lịch sử hoạt động, danh sách thông báo, bảng xếp hạng, danh sách đơn hàng có phân trang.

## 5. Tổng hợp dữ liệu (aggregation)

**Mục tiêu:** tính kết quả từ nhiều document, ví dụ đếm, tổng, trung bình, nhỏ nhất/lớn nhất, nhóm theo khách hàng, trạng thái hoặc khoảng thời gian.

Ví dụ: xếp hạng 10 khách hàng có doanh thu từ đơn `PAID` cao nhất trong tháng 11/2026:

```javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID",
      createdAt: {
        $gte: ISODate("2026-11-01T00:00:00Z"),
        $lt: ISODate("2026-12-01T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: "$customerId",
      orderCount: { $sum: 1 },
      revenue: { $sum: "$total" }
    }
  },
  { $sort: { revenue: -1, _id: 1 } },
  { $limit: 10 }
])
```

Luồng xử lý:

1. `$match` giữ lại đơn phù hợp, lý tưởng là thu hẹp dữ liệu trước các bước nặng hơn.
2. `$group` gom theo `customerId` để tính số đơn và tổng doanh thu.
3. `$sort` xếp các nhóm theo doanh thu; `$limit` chỉ trả 10 nhóm đứng đầu.

Có thể tạo chỉ mục phục vụ bước lọc:

```javascript
db.orders.createIndex({ status: 1, createdAt: 1 })
```

Nhưng **có chỉ mục cho `$match` không có nghĩa toàn bộ tổng hợp có chi phí thấp**: hệ thống vẫn có thể phải đọc nhiều đơn, gom nhóm và sắp xếp kết quả. Truy vấn phân tích trên nhiều tháng/nhiều năm khác xa một lần tra đơn theo khóa.

Khi tổng hợp được gọi thường xuyên trên tập dữ liệu rất lớn, có thể cân nhắc:

- **Pre-aggregation / materialized view:** lưu sẵn `dailyRevenueByCustomer` hoặc bộ đếm theo ngày; truy vấn đọc nhanh hơn nhưng mỗi lần dữ liệu thay đổi phải cập nhật kết quả dẫn xuất.
- **Batch hoặc streaming:** tính thống kê theo lịch hay theo sự kiện thay vì quét lại toàn bộ đơn ở mỗi request.
- **Chọn mức nhất quán phù hợp:** số liệu thời gian thực cần cân nhắc độ trễ cập nhật, xử lý sự kiện trùng lặp và khả năng tính lại khi có hoàn tiền/hủy đơn.

**Khi phù hợp:** dashboard, thống kê theo thời gian, tổng doanh thu, đếm lượt truy cập, báo cáo nhóm sản phẩm.

## 6. Duyệt quan hệ (relationship traversal)

**Mục tiêu:** từ một thực thể, lần theo các kết nối sang thực thể khác, có thể qua nhiều bước (`hop`). Ví dụ: từ khách hàng tìm các đơn đã đặt, rồi tìm sản phẩm xuất hiện trong các đơn đó.

Đây là câu hỏi khác với việc lọc đơn theo `customerId`: kết quả cần đi qua **nhiều loại thực thể và quan hệ**.

### Biểu diễn bằng graph database

Giả sử có các node `Customer`, `Order`, `Product` và cạnh `PLACED`, `CONTAINS`:

```text
(Customer C001) -[:PLACED]-> (Order O1001)
                                   |
                             [:CONTAINS]
                                   v
                              (Product P11)
```

Trong Neo4j, truy vấn Cypher đi qua hai quan hệ:

```cypher
MATCH (c:Customer {id: 'C001'})-[:PLACED]->(o:Order)-[:CONTAINS]->(p:Product)
RETURN DISTINCT p.id AS productId, p.name AS productName
ORDER BY productId
LIMIT 50;
```

Điểm bắt đầu là khách `C001`; hệ thống tìm cạnh `PLACED` đến đơn hàng, rồi cạnh `CONTAINS` đến sản phẩm. Nếu phải tìm bạn của bạn, đường đi ngắn nhất hoặc các chuỗi phụ thuộc dài, truy vấn có thể cần nhiều hop và quy tắc tránh lặp.

Chỉ mục trên định danh giúp xác định node bắt đầu:

```cypher
CREATE INDEX customer_id IF NOT EXISTS
FOR (c:Customer) ON (c.id);
```

Chỉ mục đầu vào không thay thế việc kiểm soát **fan-out**: một node có quá nhiều quan hệ, hoặc duyệt không giới hạn số hop, vẫn có thể mở rộng tập kết quả rất nhanh.

### Duyệt quan hệ trong document database

NoSQL document không buộc phải dùng graph để trả lời câu hỏi liên quan nhiều thực thể. Có hai cách thường gặp:

1. **Nhúng dữ liệu (embed):** `orders.items` đã chứa `productId`, số lượng, đơn giá tại thời điểm đặt. Đọc một đơn có thể lấy ngay các dòng hàng mà không cần join.
2. **Lưu tham chiếu (reference):** `productId` trỏ đến document ở collection `products`. Nếu muốn lấy tên sản phẩm hiện tại, MongoDB có thể dùng `$lookup`:

```javascript
db.orders.aggregate([
  { $match: { _id: "O1001" } },
  {
    $lookup: {
      from: "products",
      localField: "items.productId",
      foreignField: "_id",
      as: "productDetails"
    }
  }
])
```

`$lookup` là phép kết hợp dữ liệu giữa collection, không phải cơ chế duyệt cạnh tối ưu cho mọi bài toán nhiều hop. Với quan hệ rộng hoặc truy vấn đường đi phức tạp, cấu trúc graph có thể phù hợp hơn. Ngược lại, nếu ứng dụng chủ yếu đọc **toàn bộ đơn hàng** và các dòng hàng cùng nhau, nhúng items vào document thường đơn giản hơn.

**Khi phù hợp:** đề xuất theo quan hệ, mạng xã hội, phụ thuộc dịch vụ, phân cấp tổ chức, quyền truy cập kế thừa, khám phá sản phẩm liên quan.

## 7. Đặt năm mẫu truy cập cạnh nhau

| Mẫu | Đầu vào điển hình | Đầu ra | Cơ chế cần chú ý | Rủi ro thường gặp |
|---|---|---|---|---|
| **Tra theo khóa** | `orderId`, `sessionId` | Một bản ghi hoặc giá trị | Khóa chính, partition key | Hot key; truy vấn không chứa khóa phân vùng |
| **Lọc** | `customerId`, trạng thái, khoảng ngày | Tập bản ghi thỏa điều kiện | Secondary/compound index; selectivity | Quét toàn bộ collection, trả về quá nhiều dữ liệu |
| **Sắp xếp** | Điều kiện lọc + thứ tự + giới hạn | Trang dữ liệu có thứ tự | Chỉ mục hỗ trợ sort; cursor | Sort tốn bộ nhớ; phân trang sâu bằng offset |
| **Tổng hợp** | Khoảng ngày, nhóm, hàm tính | Số liệu hoặc bảng thống kê | Match sớm, group, pre-aggregation | Quét khối lượng lớn, báo cáo chậm hoặc số liệu trễ |
| **Duyệt quan hệ** | Node gốc, kiểu cạnh, số hop | Node/đường đi liên quan | Adjacency, embed/reference, fan-out | Nổ số đường đi; nhiều lượt join/lookup |

Các mẫu có thể xuất hiện đồng thời. Ví dụ "20 đơn `PAID` gần nhất của khách `C001`" gồm **lọc + sắp xếp + giới hạn**; "10 khách mua nhiều nhất tháng" gồm **lọc + nhóm + tổng hợp + sắp xếp**. Khi phân tích yêu cầu, cần mô tả *toàn bộ chuỗi thao tác* chứ không chỉ đặt một nhãn.

## 8. Từ yêu cầu nghiệp vụ đến thiết kế NoSQL

Không nên chọn loại NoSQL chỉ dựa vào việc dữ liệu nhìn giống JSON, bảng hay đồ thị. Trước tiên, mô tả mỗi thao tác đọc bằng một bộ thông tin cụ thể:

| Câu hỏi | Ví dụ cho màn hình danh sách đơn |
|---|---|
| Người gọi biết sẵn gì? | `customerId = C001` |
| Điều kiện bắt buộc là gì? | `status = PAID` |
| Có điều kiện phạm vi không? | `createdAt` nằm trong tháng |
| Có thứ tự và giới hạn không? | Mới nhất trước, 20 đơn/trang |
| Kích thước và tần suất đọc? | Có thể có hàng triệu đơn; trang danh sách được gọi thường xuyên |
| Mức độ mới và nhất quán mong muốn? | Đơn vừa thanh toán cần xuất hiện đúng thời điểm nghiệp vụ yêu cầu |
| Dữ liệu nằm ở một hay nhiều thực thể? | Danh sách dùng `orders`; màn chi tiết có thể cần `products` |

Từ đó, thiết kế theo các bước:

1. **Xác định truy vấn chủ đạo.** Ưu tiên tối ưu các thao tác quan trọng về độ trễ và tần suất; đồng thời ghi nhận truy vấn hiếm nhưng rất nặng như báo cáo cuối tháng.
2. **Chọn cách nhóm và phân vùng dữ liệu.** Nếu truy vấn luôn bắt đầu bằng `customerId`, việc tổ chức dữ liệu theo khách hàng có thể tạo tính cục bộ; nhưng phải xem phân bố tải và rủi ro khách hàng có quá nhiều đơn.
3. **Quyết định embed hay reference.** Nhúng dữ liệu thường đọc cùng nhau; tham chiếu khi thực thể thay đổi độc lập hoặc cần chia sẻ. Dữ liệu lặp giúp đọc nhanh hơn nhưng có chi phí cập nhật và rủi ro không nhất quán.
4. **Đặt chỉ mục theo điều kiện và thứ tự thực tế.** Chỉ mục có phí lưu trữ và chi phí ghi; không tạo tràn lan cho mọi trường.
5. **Định lượng tải và kiểm tra kế hoạch thực thi.** Xem số bản ghi quét, số trả về, thời gian thực thi, phân vùng liên quan, yêu cầu bộ nhớ và độ trễ ở mức tải dự kiến.

Với MongoDB, có thể xem thông tin thực thi của truy vấn:

```javascript
db.orders
  .find({ customerId: "C001", status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats")
```

Các thông tin như `totalDocsExamined`, `totalKeysExamined`, `nReturned` và kế hoạch dùng chỉ mục giúp hiểu hệ thống đang phải đọc bao nhiêu dữ liệu. Một truy vấn trả 20 document nhưng quét hàng trăm nghìn document thường báo hiệu bố trí chỉ mục hoặc điều kiện truy vấn chưa phù hợp. Với Neo4j, `EXPLAIN` và `PROFILE` hỗ trợ xem kế hoạch duyệt graph.

## 9. Tình huống tổng hợp: thiết kế năm endpoint

Giả sử nhóm phát triển chuẩn bị năm API sau:

| API nghiệp vụ | Mẫu truy cập | Ý tưởng thiết kế ban đầu |
|---|---|---|
| `GET /orders/O1001` | Tra theo khóa | Đọc `orders._id` |
| `GET /customers/C001/orders?status=PAID&from=...&to=...` | Lọc | Index bắt đầu bằng `customerId`, `status`, sau đó `createdAt` |
| `GET /customers/C001/orders/latest?limit=20` | Lọc + sắp xếp | Sắp theo `createdAt`, `_id`; cursor cho trang kế |
| `GET /reports/top-customers?month=2026-11` | Lọc + tổng hợp + sắp xếp | Aggregation theo khoảng tháng; cân nhắc bảng tổng hợp sẵn khi tải tăng |
| `GET /customers/C001/purchased-products` | Duyệt quan hệ | Đọc items từ đơn hoặc lần theo `Customer → Order → Product`, tùy dữ liệu và độ sâu quan hệ |

Điểm cần nhớ là **không có một cấu trúc dữ liệu duy nhất tối ưu đồng thời mọi mẫu truy cập**. Một document chứa đầy đủ đơn hàng rất thuận lợi để đọc chi tiết; chỉ mục ghép hỗ trợ danh sách có lọc và thứ tự; bảng thống kê dẫn xuất phù hợp với báo cáo gọi liên tục; graph hợp lý khi truy vấn dựa trên nhiều bước quan hệ. Mỗi lựa chọn đánh đổi giữa tốc độ đọc, chi phí ghi, dung lượng lưu trữ, độ mới của kết quả và độ phức tạp vận hành.

Khi nhận một yêu cầu tải dữ liệu mới, hãy phát biểu rõ: **"Từ khóa hoặc thực thể bắt đầu nào, áp dụng điều kiện gì, cần thứ tự hoặc phép tổng hợp nào, duyệt qua quan hệ nào, trả về tối đa bao nhiêu dữ liệu?"** Câu trả lời cho những câu hỏi này chính là mô tả access pattern để chọn mô hình và kiểm chứng truy vấn NoSQL phù hợp.

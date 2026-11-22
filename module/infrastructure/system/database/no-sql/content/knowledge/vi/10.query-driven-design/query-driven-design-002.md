# Xác định khóa lọc, thứ tự sắp xếp và giới hạn kết quả

## 1. Vì sao phải thiết kế NoSQL từ truy vấn?

Trong cơ sở dữ liệu NoSQL, mô hình dữ liệu thường được quyết định bởi **những câu hỏi ứng dụng cần trả lời thường xuyên**. Một document có thể biểu diễn nghiệp vụ rất tự nhiên nhưng vẫn gây truy vấn chậm nếu điều kiện lọc không có chỉ mục; một bảng wide-column có thể ghi hiệu quả nhưng không phục vụ được câu hỏi “lấy 20 bản ghi mới nhất của khách hàng này” nếu chọn sai khóa phân vùng.

Ba thành phần phải xác định cùng nhau trước khi chọn cấu trúc lưu trữ là:

1. **Khóa lọc (filter keys):** người dùng tìm theo định danh, tenant, trạng thái, loại, khoảng ngày hay thuộc tính nào? Điều kiện nào luôn có, điều kiện nào tùy chọn?
2. **Thứ tự sắp xếp (sort order):** bản ghi mới trước hay cũ trước? Nếu nhiều bản ghi có cùng giá trị sắp xếp thì dùng trường nào để phá hòa?
3. **Giới hạn kết quả (result limit):** mỗi trang trả tối đa bao nhiêu bản ghi? Có phân trang tiếp không? Cần bao nhiêu dữ liệu mỗi bản ghi?

Ví dụ API:

~~~http
GET /customers/customer-42/orders?status=PAID&limit=20
~~~

Nghiệp vụ mong muốn: “Hiển thị **20 đơn đã thanh toán gần nhất** của khách hàng `customer-42`, theo thời gian tạo giảm dần, và cho phép đọc trang tiếp theo”.

Yêu cầu này hàm chứa một hợp đồng truy vấn:

~~~text
Lọc bằng:
  customerId = "customer-42"  (bắt buộc)
  status     = "PAID"         (bộ lọc được hỗ trợ)

Sắp xếp:
  createdAt DESC
  orderId   DESC             (phá hòa, ổn định)

Giới hạn:
  pageSize = 20
  tiếp tục bằng cursor

Kết quả cần:
  orderId, createdAt, status, totalVnd
~~~

Nếu chỉ lưu đơn hàng dạng document có đầy đủ trường mà không thiết kế đường truy cập, DBMS có thể phải quét lượng lớn dữ liệu và sắp xếp trong bộ nhớ. Ngược lại, nếu chọn khóa và chỉ mục theo các điều kiện trên, việc đọc có thể giới hạn ở một dải dữ liệu phù hợp.

**Nguyên tắc:** mô hình dữ liệu, khóa phân vùng, chỉ mục, thứ tự và phân trang là **một quyết định thiết kế liên quan**, không nên được xác định độc lập.

## 2. Phân biệt khóa lọc, khóa phân vùng và khóa sắp xếp

Cùng một từ “khóa” nhưng có nhiều vai trò:

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| **Định danh/primary key** | Nhận diện một bản ghi hoặc tổ hợp bản ghi | `orderId` |
| **Khóa lọc** | Thuộc tính mà truy vấn dùng để chọn kết quả | `customerId`, `status` |
| **Partition/shard key** | Xác định vị trí phân phối dữ liệu | `customerId`, hoặc `(customerId, month)` |
| **Sort/clustering key** | Quyết định cách xếp bản ghi trong một phạm vi khóa | `createdAt` cùng `orderId` |
| **Index key** | Trường hoặc tổ hợp trường được cấu trúc chỉ mục để tìm kiếm/sắp xếp | `(customerId, status, createdAt, _id)` |
| **Cursor key** | Giá trị định vị trang tiếp theo theo đúng thứ tự truy vấn | `(lastCreatedAt, lastOrderId)` |

Ba điều cần nhớ:

- **Khóa lọc không nhất thiết là primary key.** Ví dụ tra đơn theo `customerId`, trong khi từng đơn vẫn được định danh bằng `orderId`.
- **Một trường lọc không tự có chỉ mục.** Có trường trong JSON không có nghĩa DBMS truy vấn nó hiệu quả.
- **Thứ tự của chuỗi ID không nhất thiết là thứ tự nghiệp vụ.** Nếu sắp theo `createdAt`, cần xử lý cả trường hợp nhiều đơn cùng timestamp.

Cơ chế cụ thể khác nhau giữa các NoSQL DBMS. MongoDB thường sử dụng index cho bộ lọc và sort. Cassandra đặt trọng tâm vào partition key và clustering key. DynamoDB có partition key, sort key và secondary indexes. Vì thế cùng một hợp đồng API có thể dẫn đến nhiều cấu trúc vật lý khác nhau.

## 3. Bắt đầu bằng bảng mẫu truy cập (access-pattern table)

Thay vì liệt kê “chúng ta có các thực thể Customer, Order, Product”, hãy ghi các truy vấn mà hệ thống phải phục vụ.

| ID | Câu hỏi nghiệp vụ | Lọc bắt buộc | Lọc tùy chọn | Sắp xếp | Giới hạn |
|---|---|---|---|---|---|
| Q1 | Lấy một đơn hàng | `orderId` | Không | Không | 1 |
| Q2 | Danh sách đơn của khách hàng | `customerId` | `status` | `createdAt DESC, orderId DESC` | 20/trang |
| Q3 | Đơn của khách hàng trong khoảng ngày | `customerId`, khoảng `createdAt` | `status` | `createdAt DESC, orderId DESC` | 50/trang |
| Q4 | Đơn mới nhất thuộc một trạng thái trong tenant | `tenantId`, `status` | Ngày bắt đầu | `createdAt DESC, orderId DESC` | 100/trang |
| Q5 | Lịch sử sự kiện một thiết bị | `deviceId`, khoảng thời gian | Loại sự kiện | `occurredAt DESC, eventId DESC` | 200/trang |
| Q6 | Thống kê doanh thu tháng | `tenantId` và tháng | Loại đơn | Theo ngày/tháng | Dạng tổng hợp, không phải trang đơn hàng |

Bảng này cho thấy không phải truy vấn nào cũng tối ưu bằng một khóa duy nhất. Q1 tra theo ID, Q2 đọc lịch sử theo khách hàng, Q4 lấy dữ liệu theo tenant/trạng thái, còn Q6 là bài toán tổng hợp. Một DBMS có thể giải quyết bằng các index khác nhau; hệ wide-column có thể cần nhiều bảng được tổ chức theo từng mẫu truy cập.

### 3.1. Phân loại tần suất và yêu cầu hiệu năng

Bên cạnh cấu trúc truy vấn, nên ghi:

- Truy vấn xảy ra bao nhiêu lần mỗi giây ở tải trung bình và cao điểm?
- Số bản ghi trung bình và cực đại thuộc một khách hàng/tenant?
- Tỷ lệ đọc/ghi là bao nhiêu?
- Độ trễ p95/p99 mà API chấp nhận?
- Dữ liệu cần cập nhật tức thời hay được phép trễ một khoảng?
- Kết quả có bao gồm trường lớn như nội dung văn bản dài, mảng con hoặc blob không?
- Có yêu cầu phân quyền để một khách không xem dữ liệu của khách khác không?

Ví dụ Q2 có thể chiếm 70% lượt đọc và cần p95 dưới 100 ms, còn Q6 chạy mỗi giờ và được phép xử lý theo lô. Trong ví dụ này, tối ưu trực tiếp Q2 thường có giá trị hơn thiết kế một index phức tạp chỉ cho báo cáo hiếm khi chạy.

Các số trên chỉ minh họa cách đặt tiêu chí, không phải ngưỡng chung của NoSQL.

## 4. Bước 1: xác định khóa lọc

### 4.1. Điều kiện bằng (equality)

Điều kiện kiểu:

~~~text
customerId = "customer-42"
status = "PAID"
tenantId = "tenant-7"
~~~

thường là điểm khởi đầu hữu ích khi chọn khóa hoặc tiền tố chỉ mục. Trong một index ghép, các trường có điều kiện bằng ở phía trước thường giúp thu hẹp phạm vi tìm kiếm.

Tuy nhiên, cần nhìn **độ phân biệt (cardinality)** và phân bố dữ liệu:

- `customerId` có thể có hàng triệu giá trị, giúp chia truy cập theo khách.
- `status` thường chỉ có vài giá trị như PENDING, PAID, CANCELLED; dùng riêng nó làm partition key có thể tạo các nhóm dữ liệu rất lớn hoặc điểm nóng.
- `tenantId` có thể có hàng nghìn giá trị nhưng một tenant lớn có lưu lượng gấp nhiều lần tenant khác.

**Cardinality cao không luôn đồng nghĩa phân phối tốt.** Một hệ có nhiều tenant nhưng một tenant chiếm phần lớn lưu lượng vẫn có skew nghiêm trọng.

### 4.2. Điều kiện khoảng (range)

Truy vấn thường cần:

~~~text
createdAt >= from AND createdAt < to
price >= minPrice AND price <= maxPrice
score > threshold
~~~

Điều kiện khoảng hữu ích với chỉ mục có thứ tự, clustering key hoặc sort key, **nếu bộ lọc xác định được đúng phạm vi chỉ mục**.

Ví dụ:

~~~text
customerId = customer-42
createdAt >= 2026-11-01T00:00:00Z
createdAt <  2026-12-01T00:00:00Z
~~~

Khoảng nửa mở `[from, to)` dễ ghép các kỳ liên tiếp mà không trùng mốc ranh giới. Khi làm việc với thời gian, nên chuẩn hóa UTC hoặc định nghĩa timezone theo nghiệp vụ trước khi tính ranh giới.

### 4.3. Điều kiện tùy chọn (optional filters)

API có thể cho phép:

~~~text
GET /orders?customerId=customer-42
GET /orders?customerId=customer-42&status=PAID
GET /orders?customerId=customer-42&from=...&to=...
~~~

Đây là **nhiều dạng truy vấn**, dù dùng chung một endpoint. Một compound index tốt cho trường hợp có `status` không nhất thiết tối ưu truy vấn khi `status` bị bỏ qua.

Ví dụ index theo `(customerId, status, createdAt)` tổ chức dữ liệu theo trạng thái **trước** thời gian. Khi lọc đúng một trạng thái, việc lấy mới nhất rất thuận lợi; khi muốn **tất cả trạng thái sắp theo thời gian**, dữ liệu có thể nằm thành nhiều nhóm trạng thái, không còn một dải thời gian toàn cục đơn giản.

Vì thế cần quyết định:

1. Hỗ trợ những tổ hợp bộ lọc nào?
2. Tổ hợp nào xuất hiện nhiều và có SLO chặt?
3. Tổ hợp nào hiếm, được phép đọc chậm hơn hoặc chuyển sang truy vấn báo cáo?
4. Có cần index/bảng đọc riêng cho một biến thể truy vấn quan trọng không?

Không nên hứa hỗ trợ mọi kết hợp bộ lọc tùy ý với độ trễ thấp chỉ bằng một index ghép.

### 4.4. Trường lọc phải phản ánh phân quyền

Một hệ đa tenant có thể truy vấn:

~~~text
tenantId = callerTenant
customerId = requestedCustomer
~~~

`tenantId` không chỉ là cách tối ưu: nó còn liên quan đến **phạm vi dữ liệu được phép đọc**. Ứng dụng phải lấy tenant đã xác thực từ ngữ cảnh bảo mật và kiểm tra quyền; không tin hoàn toàn `tenantId` người dùng tự truyền qua URL.

Ngay cả khi partition key chứa tenant, kiểm tra authorization vẫn cần thực hiện ở tầng ứng dụng và/hoặc chính sách truy cập của hệ lưu trữ.

## 5. Bước 2: xác định thứ tự sắp xếp

### 5.1. Mỗi truy vấn cần thứ tự có ngữ nghĩa rõ

“Lấy đơn gần nhất” còn mơ hồ:

- Gần nhất theo `createdAt` (lúc tạo)?
- Gần nhất theo `paidAt` (lúc thanh toán)?
- Gần nhất theo `updatedAt` (lúc sửa cuối)?
- Gần nhất theo `ingestedAt` (lúc hệ nhận)?
- Hay theo một sequence nghiệp vụ?

Ví dụ một đơn tạo hôm qua nhưng vừa được hoàn tiền có `updatedAt` mới hơn đơn được tạo hôm nay. Nếu mục tiêu là lịch sử giao dịch theo lúc tạo, sắp theo `updatedAt` sẽ sai ngữ nghĩa.

**Tên trường sắp xếp phải thuộc hợp đồng API**, và loại dữ liệu/thời điểm cần nhất quán.

### 5.2. Thứ tự tăng, giảm và giới hạn index

Một dòng thời gian thường yêu cầu:

~~~text
ORDER BY createdAt DESC
~~~

Trong cơ sở dữ liệu có chỉ mục thứ tự, việc quét index thuận hoặc ngược có thể hiệu quả tùy index, bộ lọc và DBMS.

Đối với một index ghép, **thứ tự các cột và chiều sắp xếp** ảnh hưởng khả năng tránh bước sort riêng. Không thể mặc nhiên nghĩ có index trên `createdAt` là mọi truy vấn lọc theo `customerId` và sort theo `createdAt` đều hiệu quả.

### 5.3. Trường phá hòa (tie-breaker) tạo thứ tự ổn định

Giả sử có ba đơn cùng `createdAt` tới mili giây:

| orderId | createdAt |
|---|---|
| order-A | 2026-11-14T08:15:27.123Z |
| order-B | 2026-11-14T08:15:27.123Z |
| order-C | 2026-11-14T08:15:27.123Z |

Sắp theo một mình `createdAt` không xác định thứ tự giữa chúng. Nên dùng thứ tự đầy đủ:

~~~text
createdAt DESC, orderId DESC
~~~

Nếu `orderId` là duy nhất trong phạm vi truy vấn và comparator ổn định, mỗi bản ghi có vị trí xác định. Điều này quan trọng khi phân trang bằng cursor.

**Tie-breaker bảo đảm tính ổn định của dãy sắp xếp**, không chứng minh rằng `order-C` thực sự được tạo sau `order-B` khi timestamp bằng nhau.

### 5.4. Tránh dựa vào thứ tự tự nhiên

Trong nhiều DBMS, truy vấn không khai báo sort **không bảo đảm** bản ghi trả về theo thời gian chèn hoặc theo primary key. Điều này vẫn đúng ngay cả khi kết quả thử nghiệm trên máy phát triển có vẻ luôn đúng.

Không nên định nghĩa API “mới nhất” dựa vào thứ tự ngẫu nhiên của engine hoặc thứ tự duyệt collection.

## 6. Bước 3: xác định giới hạn và hình dạng kết quả

### 6.1. Trả bao nhiêu bản ghi cho một lần đọc?

Một API danh sách cần giới hạn cụ thể:

~~~text
pageSize mặc định: 20
pageSize tối đa: 100
không cho phép truy vấn danh sách không giới hạn qua endpoint này
~~~

Các giá trị chỉ minh họa. Giới hạn phù hợp phụ thuộc kích thước bản ghi, độ trễ mục tiêu, thiết bị client và cách phân trang.

Nếu mỗi kết quả trung bình 2 KB, 20 bản ghi tương đương khoảng 40 KB payload thô trước overhead. Nếu document có mảng nhiều MB nhưng màn hình chỉ cần vài trường, cần **projection** hoặc mô hình đọc gọn để không tải dữ liệu thừa.

### 6.2. LIMIT giảm lượng trả về, nhưng không luôn giảm công việc trước đó

Xem hai tình huống:

~~~text
Tình huống A:
  Index khớp bộ lọc và thứ tự
  -> đọc các mục đầu tiên trong dải phù hợp
  -> trả 20 bản ghi

Tình huống B:
  Không có index phù hợp
  -> đọc/quét rất nhiều bản ghi
  -> lọc và sắp xếp
  -> trả 20 bản ghi
~~~

Cả hai truy vấn đều có `LIMIT 20`, nhưng chi phí rất khác nhau. Một hệ có thể dùng các thuật toán top-K để giảm bộ nhớ khi sort mà vẫn phải xem xét rất nhiều bản ghi ứng viên.

**Giới hạn số kết quả không phải lời hứa giới hạn số bản ghi DBMS phải đọc hoặc xử lý.**

### 6.3. Phân biệt ba loại giới hạn

| Giới hạn | Ý nghĩa | Ví dụ |
|---|---|---|
| Giới hạn số hàng trả về | Số bản ghi API cho người dùng | 20 đơn/trang |
| Giới hạn công việc của truy vấn | Ngân sách truy vấn, timeout, số dữ liệu quét, số phân vùng truy cập | 500 ms timeout hoặc quota thích hợp |
| Giới hạn tổng dữ liệu được phép đọc | Phân quyền, khoảng thời gian, số ngày lịch sử | Chỉ dữ liệu tenant hiện tại trong 90 ngày |

Dùng một mình `LIMIT` chưa thay thế timeout, phân quyền, ranh giới partition hoặc cơ chế kiểm soát workload.

### 6.4. Tách API danh sách khỏi API chi tiết

Có thể thiết kế:

~~~text
GET /customers/{id}/orders
  -> orderId, createdAt, status, totalVnd, cursor

GET /orders/{orderId}
  -> địa chỉ, dòng hàng, lịch sử trạng thái, thông tin chi tiết
~~~

Khi danh sách trả projection nhỏ, chi phí mạng và giải mã thường thấp hơn so với tải toàn bộ document lớn. API chi tiết dùng một truy vấn theo ID hoặc đường đọc dành cho một đơn cụ thể.

## 7. Ví dụ document database: MongoDB

Giả sử collection `orders` chứa:

~~~json
{
  "_id": "order-1001",
  "tenantId": "tenant-7",
  "customerId": "customer-42",
  "status": "PAID",
  "createdAt": "2026-11-14T08:15:27.123Z",
  "totalVnd": 1050000,
  "currency": "VND",
  "items": [
    { "productId": "product-8", "quantity": 2, "unitPriceVnd": 450000 },
    { "productId": "product-21", "quantity": 1, "unitPriceVnd": 150000 }
  ]
}
~~~

Trong MongoDB, trường `createdAt` ở đây được minh họa dưới dạng chuỗi JSON để dễ đọc. Khi triển khai những truy vấn ngày giờ bên dưới, nên lưu bằng **BSON Date** (ví dụ tạo từ `new Date(...)`) và dùng cùng kiểu dữ liệu nhất quán. Trộn chuỗi với Date trong cùng trường có thể gây kết quả lọc/sort không mong muốn.

### 7.1. Truy vấn đơn theo khách hàng và trạng thái

~~~javascript
db.orders.find(
  {
    tenantId: "tenant-7",
    customerId: "customer-42",
    status: "PAID"
  },
  {
    _id: 1,
    status: 1,
    createdAt: 1,
    totalVnd: 1
  }
)
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Ở đây:

- `tenantId`, `customerId` và `status` là điều kiện bằng.
- `createdAt DESC` biểu diễn mới nhất trước.
- `_id DESC` là tie-breaker khi thời gian bằng nhau.
- Projection chỉ lấy các trường cần cho danh sách.
- `limit(20)` giới hạn số document trả về trong lần đọc.

### 7.2. Index ghép tương ứng với truy vấn

Một index có thể cân nhắc:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  customerId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
~~~

Các trường có điều kiện bằng đứng trước, sau đó là trường sort. Với các giá trị bằng đã được xác định, dữ liệu có thể được duyệt theo `createdAt` và `_id` trong đúng nhóm.

Đây là trường hợp thuận lợi của nguyên tắc thường được diễn đạt là **Equality → Sort → Range (ESR)** khi thiết kế compound index MongoDB. Tuy nhiên, ESR là **hướng dẫn cân nhắc**, không phải một công thức bất biến: nếu điều kiện range rất chọn lọc, đôi khi đặt range trước sort có thể hiệu quả hơn dù cần sort riêng. Kết luận nên dựa trên `explain()` và workload.

### 7.3. Nếu trạng thái không còn là bộ lọc thì sao?

Query:

~~~javascript
db.orders.find({
  tenantId: "tenant-7",
  customerId: "customer-42"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Index có `status` trước `createdAt` không nhất thiết cung cấp một thứ tự `createdAt` thống nhất cho **tất cả trạng thái**. Nếu truy vấn này quan trọng, có thể cần index khác:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  customerId: 1,
  createdAt: -1,
  _id: -1
});
~~~

Đổi lại, thêm một index có chi phí dung lượng và bảo trì khi ghi. Không nên tự động tạo rất nhiều index cho mọi tổ hợp lọc; cần ưu tiên query xuất hiện nhiều, có SLO rõ và có lợi ích đo được.

### 7.4. Thêm lọc khoảng thời gian

~~~javascript
const from = new Date("2026-11-01T00:00:00.000Z");
const to = new Date("2026-12-01T00:00:00.000Z");

db.orders.find(
  {
    tenantId: "tenant-7",
    customerId: "customer-42",
    status: "PAID",
    createdAt: { $gte: from, $lt: to }
  },
  {
    _id: 1,
    createdAt: 1,
    status: 1,
    totalVnd: 1
  }
)
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Khoảng thời gian được lọc ngay trong DBMS thay vì lấy toàn bộ dữ liệu về ứng dụng rồi cắt. Cần đối chiếu execution plan để xem phạm vi index quét, số document được đọc và có xuất hiện bước sort tốn kém hay không.

### 7.5. Dùng `explain` để hiểu chi phí

~~~javascript
db.orders.find({
  tenantId: "tenant-7",
  customerId: "customer-42",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.explain("executionStats");
~~~

Những điểm cần quan sát:

- Có sử dụng index phù hợp thay vì quét collection quá rộng không?
- `totalKeysExamined` so với số kết quả trả về thế nào?
- `totalDocsExamined` có cao bất thường không?
- Có giai đoạn sort không được hỗ trợ hiệu quả bởi index không?
- Thời gian thực thi và số kết quả thay đổi ra sao với khách hàng có rất nhiều đơn?

Các chỉ số cụ thể và tên operator phụ thuộc phiên bản MongoDB, cấu hình và kế hoạch truy vấn. Không nên khẳng định một index tốt chỉ vì query thử với 10 document chạy nhanh.

## 8. Phân trang: offset và cursor

### 8.1. Offset pagination

Một cách dễ viết:

~~~javascript
db.orders.find({
  tenantId: "tenant-7",
  customerId: "customer-42"
})
.sort({ createdAt: -1, _id: -1 })
.skip(2000)
.limit(20);
~~~

Ưu điểm: dễ hiểu khi cần tới trang thứ 101. Nhược điểm: offset lớn có thể khiến DBMS vẫn phải đi qua nhiều kết quả trước khi trả trang; khi dữ liệu mới được thêm giữa hai lần đọc, người dùng có thể thấy bản ghi bị lặp hoặc bị bỏ qua.

Offset có thể hợp lý cho dữ liệu nhỏ hoặc trường hợp cần nhảy đến vị trí, nhưng với dòng thời gian tăng liên tục, **keyset/cursor pagination** thường được cân nhắc.

### 8.2. Cursor dựa trên cặp khóa sắp xếp

Giả sử đang sort:

~~~text
createdAt DESC, _id DESC
~~~

Trang đầu trả 20 bản ghi. Lấy giá trị của **bản ghi cuối trang**:

~~~json
{
  "createdAt": "2026-11-14T08:15:27.123Z",
  "id": "order-1001"
}
~~~

Trang sau chỉ lấy những bản ghi đứng **sau vị trí này** trong thứ tự giảm dần, tức cặp khóa nhỏ hơn cursor:

~~~javascript
const cursorTime = new Date("2026-11-14T08:15:27.123Z");
const cursorId = "order-1001";

db.orders.find(
  {
    tenantId: "tenant-7",
    customerId: "customer-42",
    $or: [
      { createdAt: { $lt: cursorTime } },
      { createdAt: cursorTime, _id: { $lt: cursorId } }
    ]
  },
  {
    _id: 1,
    createdAt: 1,
    status: 1,
    totalVnd: 1
  }
)
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Điều kiện này minh họa trường hợp `_id` là **chuỗi** có comparator ổn định. Nếu dùng ObjectId thực, `cursorId` phải cùng kiểu BSON ObjectId; so sánh khác kiểu sẽ dẫn tới kết quả không đúng mong muốn.

Với filter `status`, phải đưa lại **cùng điều kiện status** của trang đầu vào trang sau. Các filter khác cũng phải giữ nguyên. Cursor nên gắn với phiên bản bộ lọc và thứ tự, không thể dùng tùy ý cho một query khác.

### 8.3. Vì sao phải có tie-breaker?

Nếu chỉ dùng `createdAt < cursorTime`, các bản ghi có cùng timestamp với bản ghi cuối trang nhưng chưa được trả **có thể bị bỏ sót**. Nếu dùng `createdAt <= cursorTime`, các bản ghi vừa trả có thể bị lặp.

Cặp `(createdAt, _id)` với `_id` duy nhất giúp xác định đúng ranh giới ngay cả khi timestamp trùng.

### 8.4. Cursor không tự tạo ảnh chụp dữ liệu bất biến

Nếu một bản ghi được thêm mới trong lúc phân trang:

- Bản ghi mới đứng **trước** cursor có thể không xuất hiện ở các trang tiếp theo.
- Bản ghi được nhập muộn nhưng mang timestamp cũ có thể xuất hiện ở trang sau.
- Nếu trường sort của một bản ghi được cập nhật, bản ghi có thể đổi vị trí giữa các lần đọc.

Keyset pagination thường giảm chi phí offset và tăng ổn định khi dữ liệu được chèn thêm, nhưng **không thay thế snapshot/transactional read** nếu nghiệp vụ cần một tập kết quả cố định giữa nhiều lần gọi API.

### 8.5. Cursor phục vụ API nên chứa gì?

Một cursor có thể gồm:

~~~json
{
  "v": 1,
  "lastCreatedAt": "2026-11-14T08:15:27.123Z",
  "lastId": "order-1001",
  "sort": "createdAt_desc_id_desc",
  "filters": {
    "customerId": "customer-42",
    "status": "PAID"
  }
}
~~~

Đây là dạng **giải thích cấu trúc**. API thực tế có thể mã hóa cursor thành chuỗi opaque; nên kiểm tra tính hợp lệ, gắn với tenant đã xác thực, tránh cho người dùng sửa cursor để truy cập dữ liệu trái phép và không đưa thông tin nhạy cảm không cần thiết vào cursor.

Nếu cursor dùng để bảo vệ ràng buộc truy vấn, cần cơ chế xác thực tính toàn vẹn phù hợp; Base64 đơn thuần **không phải chữ ký bảo mật**. Client cũng cần biết cursor có thể hết hạn hoặc không tương thích khi chính sách sort/filter thay đổi.

## 9. Wide-column: khóa lọc và clustering trong Cassandra

Ở Cassandra, mô hình bảng cần thiết kế cụ thể cho những truy vấn được hỗ trợ. Xét bài toán “đơn hàng theo khách hàng trong tháng, mới nhất trước”.

### 9.1. Chọn partition key có giới hạn

Một thiết kế:

~~~sql
CREATE TABLE orders_by_customer_month (
    customer_id text,
    order_month text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_vnd bigint,
    PRIMARY KEY (
        (customer_id, order_month),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id DESC
);
~~~

- `(customer_id, order_month)` là **composite partition key**: một khách hàng trong một tháng là một partition logic.
- `created_at` và `order_id` là **clustering columns**: sắp thứ tự các hàng trong partition.
- `order_id` phân biệt những đơn có timestamp bằng nhau.
- `status` là regular column trong bảng này; chưa trở thành một khóa lọc được tối ưu cho mọi truy vấn.

Tháng là một ví dụ về **time bucket**; có thể cần kỳ ngắn/dài khác dựa trên tải và kích thước phân vùng. Nếu một khách có đơn rất nhiều trong tháng, bucket tháng vẫn có thể quá lớn hoặc nóng.

### 9.2. Truy vấn đúng partition và thứ tự

~~~sql
SELECT order_id, created_at, status, total_vnd
FROM orders_by_customer_month
WHERE customer_id = 'customer-42'
  AND order_month = '2026-11'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Truy vấn có đủ các thành phần partition key; thứ tự dùng đúng clustering order. Đây là mẫu truy vấn phù hợp với thiết kế bảng.

Truy vấn một khoảng:

~~~sql
SELECT order_id, created_at, status, total_vnd
FROM orders_by_customer_month
WHERE customer_id = 'customer-42'
  AND order_month = '2026-11'
  AND created_at >= '2026-11-10T00:00:00Z'
  AND created_at <  '2026-11-15T00:00:00Z'
ORDER BY created_at DESC
LIMIT 50;
~~~

Khi giới hạn trên clustering column đầu, Cassandra có thể đọc một dải bên trong partition; vẫn cần tuân thủ các quy tắc CQL theo phiên bản, đặc biệt khi có nhiều clustering columns và các ràng buộc thứ tự khác.

### 9.3. Điều gì xảy ra nếu muốn lọc `status = PAID`?

Với bảng trên, câu hỏi:

~~~text
Lấy 20 đơn PAID mới nhất của customer-42 trong 2026-11.
~~~

không tự được giải quyết chỉ bằng cách thêm `status = 'PAID'` vào `WHERE`. `status` không nằm trong partition/clustering key phù hợp; tùy Cassandra và index được cấu hình, truy vấn có thể bị từ chối hoặc phải lọc nhiều dữ liệu với hiệu năng không mong muốn.

**Không nên dùng `ALLOW FILTERING` như cách sửa mặc định** cho truy vấn online cần độ trễ ổn định. Nó có thể che giấu thiết kế khóa không phù hợp và tạo chi phí quét khó dự đoán.

Nếu Q2 theo trạng thái là truy vấn chủ đạo, một **bảng đọc thứ hai** có thể được thiết kế:

~~~sql
CREATE TABLE orders_by_customer_status_month (
    customer_id text,
    status text,
    order_month text,
    created_at timestamp,
    order_id uuid,
    total_vnd bigint,
    PRIMARY KEY (
        (customer_id, status, order_month),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id DESC
);
~~~

Truy vấn:

~~~sql
SELECT order_id, created_at, total_vnd
FROM orders_by_customer_status_month
WHERE customer_id = 'customer-42'
  AND status = 'PAID'
  AND order_month = '2026-11'
LIMIT 20;
~~~

Cách này đặt các giá trị lọc bắt buộc vào partition key và sắp thời gian bằng clustering key. Nhưng **trạng thái đơn hàng có thể thay đổi**. Ứng dụng cần thiết kế cách xóa/cập nhật bản ghi trong nhóm trạng thái cũ và ghi vào nhóm mới, kèm bảo đảm nhất quán phù hợp. Không thể cho rằng hai bảng tự được đồng bộ nguyên tử trong mọi trường hợp.

Với hệ cột rộng, **lặp dữ liệu có chủ đích theo mẫu truy vấn** là kỹ thuật phổ biến; đổi lại phải quản lý đồng bộ và số lượng bảng.

### 9.4. Đọc xuyên nhiều bucket thời gian

Nếu API cần 20 đơn mới nhất mà không biết chúng thuộc tháng nào, ứng dụng có thể phải:

1. Đọc tháng hiện tại với `LIMIT 20`.
2. Nếu kết quả chưa đủ, đọc thêm tháng trước.
3. Ghép các kết quả theo `created_at DESC, order_id DESC`.
4. Trả 20 bản ghi và cursor có đủ thông tin về vị trí tháng/khóa.

Nếu truy vấn đồng thời nhiều bucket hoặc nhiều shard, có thể cần merge nhiều dãy đã sắp xếp. **`LIMIT 20` trên từng partition không tự có nghĩa API sẽ trả đúng 20 bản ghi mới nhất trên tất cả partition** nếu không so sánh thứ tự chung.

### 9.5. Khi nào partition quá nhỏ hoặc quá nóng?

- Partition theo `order_id` là tốt khi truy vấn một đơn theo ID, nhưng không giúp truy vấn lịch sử của khách hàng theo thời gian.
- Partition theo `status` có cardinality rất thấp và nhiều ghi, dễ tạo partition lớn hoặc nóng.
- Partition theo `(customer_id, order_month)` giảm tăng trưởng nhưng một khách đặc biệt lớn vẫn có thể nóng.
- Chia thêm hash bucket có thể phân phối ghi, nhưng API phải fan-out để lấy dòng thời gian mới nhất.

Thiết kế phải cân bằng **phân bố tải**, **số partition phải đọc** và **kích thước mỗi partition**.

## 10. DynamoDB: partition key, sort key và giới hạn truy vấn

DynamoDB là một ví dụ NoSQL có **partition key** và **sort key** (với bảng hoặc index khóa ghép), hữu ích để thấy cách giới hạn kết quả có ngữ nghĩa riêng theo sản phẩm.

Giả sử thiết kế:

~~~text
PK = CUSTOMER#customer-42#MONTH#2026-11
SK = 2026-11-14T08:15:27.123Z#ORDER#order-1001
~~~

Dữ liệu theo khách hàng và tháng được nhóm theo partition key; các bản ghi có sort key là chuỗi thời gian chuẩn hóa theo UTC nên có thể truy vấn theo thứ tự từ điển trong phạm vi partition key đó.

Đối với truy vấn danh sách:

~~~text
KeyConditionExpression:
  PK = :customerMonth
  AND SK BETWEEN :startKey AND :endKey

ScanIndexForward = false
Limit = 20
~~~

Ý tưởng:

- Điều kiện bằng trên `PK` giúp xác định nhóm khóa.
- Điều kiện khoảng trên `SK` giới hạn thời gian trong tháng.
- `ScanIndexForward = false` đọc theo sort key giảm dần.
- `Limit = 20` giới hạn **số item được đánh giá trong lượt Query** theo ngữ nghĩa DynamoDB, không nhất thiết là đúng 20 item trả về sau FilterExpression.

**Điểm dễ nhầm:** trong DynamoDB Query, `FilterExpression` được áp dụng sau khi đọc các item thỏa KeyConditionExpression trong lượt đó. Do vậy `Limit = 20` cùng bộ lọc trạng thái có thể trả ít hơn 20 item, thậm chí 0, nhưng vẫn còn `LastEvaluatedKey` để tiếp tục. Không nên cho rằng một trang rỗng chắc chắn là hết dữ liệu.

DynamoDB còn có giới hạn kích thước dữ liệu cho mỗi lượt Query và cơ chế phân trang riêng. Ứng dụng phải xem `LastEvaluatedKey` và lặp truy vấn theo đúng hợp đồng API cho tới khi đủ kết quả hoặc không còn trang, đồng thời đặt giới hạn ngân sách để tránh quét quá nhiều item.

Nếu `status` là điều kiện truy vấn thường xuyên, một **GSI** với khóa phù hợp có thể được cân nhắc. Nhưng GSI có chi phí ghi/lưu trữ và đặc điểm nhất quán cần xem theo tài liệu của dịch vụ; không nên mặc định nó có cùng mức nhất quán với truy vấn bảng gốc.

## 11. Bộ lọc, sắp xếp, giới hạn: một luồng truy vấn hoàn chỉnh

~~~mermaid
flowchart TD
    A["Yêu cầu API"] --> B["Xác định tenant và phạm vi quyền"]
    B --> C["Xác định khóa lọc bắt buộc và tùy chọn"]
    C --> D["Xác định sort và tie-breaker"]
    D --> E["Chọn partition key, sort key hoặc index"]
    E --> F["Lọc trên server và đọc theo thứ tự"]
    F --> G["Giới hạn số kết quả và projection"]
    G --> H["Trả danh sách và cursor"]
    H --> I["Đo thực thi: index, số bản ghi quét, p95/p99"]
    I --> J["Điều chỉnh mô hình từ số liệu"]
~~~

Hình minh họa mô tả thứ tự **ra quyết định khi thiết kế**, không quy định thứ tự thực thi vật lý của mọi toán tử trong DBMS. Bộ tối ưu truy vấn có thể thay đổi thứ tự toán tử miễn giữ ngữ nghĩa của câu truy vấn.

Cần phân biệt:

- **Filter trên server** giúp tránh chuyển nhiều dữ liệu thừa về client.
- **Index/partition phù hợp** mới giúp giới hạn số dữ liệu cần xét trước khi có kết quả.
- **Sort ổn định** đảm bảo phân trang có ranh giới rõ.
- **Limit và projection** bảo vệ độ lớn response.
- **Observability** cho biết thiết kế có thực sự đáp ứng tải hay không.

## 12. Những lỗi thường gặp khi ghép filter, sort và limit

### 12.1. Lấy tất cả dữ liệu rồi lọc ở ứng dụng

Ví dụ cách làm bất lợi:

~~~javascript
const allOrders = await fetchAllOrdersFromDatabase();
const result = allOrders
  .filter(o => o.customerId === customerId && o.status === "PAID")
  .sort((a, b) => b.createdAt - a.createdAt)
  .slice(0, 20);
~~~

Vấn đề là ứng dụng phải tải rất nhiều dữ liệu và giữ trong bộ nhớ trước khi lọc. Với tập nhỏ có thể chạy, nhưng với hàng triệu đơn sẽ tốn mạng, CPU, RAM và tiềm ẩn rò rỉ dữ liệu nếu bộ lọc phân quyền không được áp dụng trong truy vấn nguồn.

Hãy đưa filter, sort và limit xuống DBMS, rồi thiết kế khóa/index để DBMS có thể thực thi hiệu quả.

### 12.2. Chọn trường lọc có độ phân biệt thấp làm partition key

`status = PAID` chỉ có một số ít trạng thái, nên dùng `status` làm partition key duy nhất của bảng có hàng trăm triệu đơn sẽ tạo ít partition rất lớn. Nên xét khóa ghép gồm tenant/customer/time bucket nếu phù hợp truy vấn và phân bố tải.

### 12.3. Index không khớp thứ tự

Index `(customerId, status, createdAt)` thuận lợi khi có `status` bằng, nhưng không tự đảm bảo sắp toàn bộ đơn của một khách theo `createdAt` nếu bỏ điều kiện `status`. Cần liệt kê từng biến thể của truy vấn, thay vì suy ra một index tối ưu cho tất cả.

### 12.4. Dùng LIMIT nhưng không có ORDER BY

~~~text
Lấy 20 đơn bất kỳ ≠ lấy 20 đơn mới nhất.
~~~

Nếu API yêu cầu “mới nhất”, phải đặt sort theo thời điểm có ngữ nghĩa rõ và tie-breaker. Không dựa vào thứ tự chèn tự nhiên.

### 12.5. Sắp trên timestamp không đủ độ phân giải

Nhiều bản ghi có thể có timestamp giống nhau, nhất là mili giây. Phân trang chỉ bằng thời gian có nguy cơ lặp/bỏ sót. Cần sort thêm một ID duy nhất, giữ comparator đồng nhất giữa các trang.

### 12.6. Lọc sau LIMIT

Ví dụ một danh sách 20 bản ghi mới nhất được lấy trước, rồi mới lọc `status = PAID` ở ứng dụng. Nếu trong 20 đơn gần nhất chỉ 3 đơn đã thanh toán, API trả 3 đơn dù còn hàng nghìn đơn PAID cũ hơn.

Theo ngữ nghĩa yêu cầu “20 đơn PAID mới nhất”, **phải lọc PAID trong tập ứng viên trước khi lấy top 20**. Nếu DBMS thực hiện filter sau giai đoạn đọc có `Limit` riêng, như một số cơ chế Query/FilterExpression, ứng dụng phải xử lý phân trang bổ sung theo hợp đồng DBMS.

### 12.7. Chỉ mục quá nhiều

Mỗi index có thể làm tăng dung lượng, chi phí ghi, chi phí build/rebuild và vận hành. Không nên tạo một index cho mọi trường và mọi tổ hợp. Ưu tiên truy vấn có tác động tới người dùng, đo index được chọn và loại bỏ chỉ mục không còn mang giá trị khi được phép thay đổi.

### 12.8. Bỏ qua dữ liệu lệch tải

Một tenant lớn có thể có hàng chục triệu đơn, trong khi các tenant khác chỉ có vài trăm. Benchmark trên khách hàng nhỏ không đại diện cho khách lớn. Cần thử trên trường hợp cực đại dự kiến và xem p99 thay vì chỉ lấy thời gian trung bình.

## 13. Phân trang có trạng thái, dữ liệu thay đổi và tính nhất quán

Trên một dòng thời gian có ghi liên tục, phân trang thường không chỉ là vấn đề hiệu năng.

### 13.1. Có cần đọc một ảnh chụp cố định không?

Hai kiểu nghiệp vụ:

- **Bảng tin hoạt động:** có thể chấp nhận bản ghi mới xuất hiện ở đầu danh sách sau khi người dùng làm mới. Cursor theo sort key thường đáp ứng tốt.
- **Xuất dữ liệu kiểm toán:** cần tập dữ liệu đúng như một mốc thời gian hoặc một phiên nhất quán; có thể cần snapshot semantics hoặc quy trình xuất dữ liệu riêng.

Cursor giúp tiếp tục từ vị trí đã biết nhưng **không tự tạo tính nhất quán snapshot**. Nếu một bản ghi đổi trạng thái giữa hai trang, nó có thể xuất hiện hoặc biến mất khỏi kết quả tùy filter. Quy tắc nghiệp vụ cần được xác định từ đầu.

### 13.2. Khi thứ tự không chỉ dựa trên thời gian vật lý

Một hệ phân tán có thể nhận sự kiện đến muộn: sự kiện A xảy ra lúc 08:00 nhưng tới database lúc 09:00; sự kiện B xảy ra 08:30 và được ghi lúc 08:31. Sắp theo `occurredAt` khác sắp theo `ingestedAt`.

Một ID chứa timestamp không tự bảo đảm thứ tự commit hoặc thứ tự nhân quả. Nếu nghiệp vụ cần trình tự giao dịch chặt chẽ, cần một nguồn sequence/log/transaction có hợp đồng riêng thay vì chỉ dựa trên sort theo timestamp.

### 13.3. Giới hạn theo tenant và thời gian lưu giữ

API có thể chỉ cho đọc dữ liệu trong 90 ngày. Nên áp dụng cả:

- Kiểm tra phạm vi tenant/định danh được quyền đọc.
- Ranh giới khoảng ngày được phép truy vấn.
- Page size tối đa và timeout.
- Quy định cursor không cho vượt phạm vi.
- Chỉ mục hoặc bucket phục vụ đúng đường truy cập.

Giới hạn nghiệp vụ và giới hạn truy vấn cần được áp dụng nhất quán giữa các trang.

## 14. Thử nghiệm hiệu năng cho một mẫu truy vấn

Để đánh giá “khóa lọc + sort + limit” có tốt không, hãy tạo tập dữ liệu đại diện:

- Có nhiều tenant, bao gồm một số tenant rất lớn.
- Số đơn mỗi khách phân bố không đều.
- Nhiều đơn có cùng timestamp để kiểm chứng tie-breaker.
- Một số trạng thái hiếm, một số trạng thái chiếm phần lớn.
- Có cả bản ghi mới và lịch sử nhiều năm.
- Mẫu đọc phản ánh tỷ lệ lọc theo trạng thái và không lọc theo trạng thái.

Sau đó đo:

| Chỉ số | Câu hỏi đánh giá |
|---|---|
| p50/p95/p99 latency | Người dùng nhận trang đầu và trang sâu nhanh đến đâu? |
| Số index keys/documents examined | DBMS có quét quá nhiều dữ liệu để trả 20 bản ghi không? |
| Sort stage hoặc spill | Có cần sắp xếp tốn CPU/RAM/đĩa không? |
| Độ lớn response | Projection đã giới hạn payload phù hợp chưa? |
| Partition count/fan-out | Một truy vấn phải chạm bao nhiêu partition/shard/bucket? |
| Độ lệch theo tenant | Tenant lớn hoặc khóa nóng có làm p99 tăng không? |
| Write amplification | Index/bảng đọc bổ sung làm chi phí ghi tăng bao nhiêu? |
| Cursor correctness | Có lặp/bỏ sót ở ranh giới timestamp bằng nhau không? |
| Timeout và retry | Khi hệ tải cao, client và server xử lý giới hạn ra sao? |

Không chỉ test một trang đầu với 10 đơn. Nên so sánh trang đầu, trang sâu, khách lớn, trạng thái phổ biến và những trường hợp dữ liệu cập nhật trong lúc phân trang.

## 15. Ví dụ thực hành tổng hợp: feed sự kiện thiết bị

Một hệ thống IoT có hàng trăm nghìn thiết bị. Mỗi sự kiện gồm:

~~~json
{
  "eventId": "evt-109",
  "deviceId": "sensor-01",
  "type": "TEMPERATURE",
  "severity": "WARN",
  "occurredAt": "2026-11-14T08:15:27.123Z",
  "ingestedAt": "2026-11-14T08:15:30.005Z",
  "temperatureC": 32.5
}
~~~

API yêu cầu:

~~~http
GET /devices/sensor-01/events?type=TEMPERATURE&severity=WARN&limit=50
~~~

Phải trả **50 sự kiện cảnh báo nhiệt độ mới nhất theo thời gian xảy ra**, có cursor và khả năng lọc trong khoảng ngày.

### 15.1. Xác định hợp đồng

| Phần | Đề xuất |
|---|---|
| Định danh sự kiện | `eventId` bất biến |
| Lọc bắt buộc | `deviceId` |
| Lọc được hỗ trợ | `type`, `severity`, khoảng `occurredAt` |
| Sắp xếp | `occurredAt DESC, eventId DESC` |
| Giới hạn | 50 mặc định, tối đa theo ngân sách API |
| Cursor | `(lastOccurredAt, lastEventId)` và bộ lọc |
| Dữ liệu trả | `eventId`, `type`, `severity`, `occurredAt`, `temperatureC` |
| Vùng dữ liệu | Có thể chia theo thiết bị và time bucket để tránh partition vô hạn |

### 15.2. Phương án document với compound index

Nếu filter `type` và `severity` thường xuất hiện cùng nhau, có thể cân nhắc:

~~~javascript
db.deviceEvents.createIndex({
  deviceId: 1,
  type: 1,
  severity: 1,
  occurredAt: -1,
  eventId: -1
});
~~~

Truy vấn:

~~~javascript
db.deviceEvents.find(
  {
    deviceId: "sensor-01",
    type: "TEMPERATURE",
    severity: "WARN",
    occurredAt: {
      $gte: new Date("2026-11-01T00:00:00Z"),
      $lt: new Date("2026-12-01T00:00:00Z")
    }
  },
  {
    _id: 0,
    eventId: 1,
    type: 1,
    severity: 1,
    occurredAt: 1,
    temperatureC: 1
  }
)
.sort({ occurredAt: -1, eventId: -1 })
.limit(50);
~~~

Nếu API cho phép thiếu `severity` hoặc `type`, phải đánh giá riêng các biến thể, vì trường bị bỏ trống ở giữa tiền tố index có thể ảnh hưởng việc dùng index cho sort.

### 15.3. Phương án wide-column cho một mẫu truy vấn xác định

Giả sử truy vấn gần như luôn yêu cầu cả `type` và `severity`:

~~~sql
CREATE TABLE events_by_device_type_severity_day (
    device_id text,
    event_type text,
    severity text,
    event_day date,
    occurred_at timestamp,
    event_id text,
    temperature_c double,
    PRIMARY KEY (
        (device_id, event_type, severity, event_day),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id DESC
);
~~~

Truy vấn:

~~~sql
SELECT event_id, occurred_at, temperature_c
FROM events_by_device_type_severity_day
WHERE device_id = 'sensor-01'
  AND event_type = 'TEMPERATURE'
  AND severity = 'WARN'
  AND event_day = '2026-11-14'
LIMIT 50;
~~~

Đọc được nhanh trong một partition theo khóa đã chọn. Tuy vậy, nếu cần kết quả xuyên nhiều ngày, ứng dụng phải đọc các bucket liên quan và ghép theo thứ tự. Nếu `severity` thay đổi sau khi ghi, mô hình và đồng bộ dữ liệu cần xử lý việc chuyển nhóm trạng thái.

### 15.4. Phương án nào tốt hơn?

Không thể kết luận chỉ từ cú pháp. Cần xem:

- Một thiết bị có bao nhiêu sự kiện mỗi ngày?
- `severity = WARN` là hiếm hay phổ biến?
- API có hay bỏ trống bộ lọc type/severity không?
- Người dùng thường xem một ngày hay cả năm?
- Có cần phân trang xuyên nhiều bucket không?
- Chỉ mục bổ sung ảnh hưởng tốc độ ghi ở tải đỉnh ra sao?
- Có sự kiện đến trễ với `occurredAt` cũ nhưng `ingestedAt` mới không?

Với document database, nhiều truy vấn khác nhau có thể được phục vụ bởi nhiều index nếu chi phí chấp nhận được. Với wide-column, một số truy vấn có thể cần **bảng đọc riêng**. Mỗi phương án phải được đo trong điều kiện đại diện.

## 16. Bài tập tự luyện

### Bài 1: Đặt câu hỏi trước khi chọn index

API hiển thị 30 sản phẩm đang bán của một cửa hàng:

~~~http
GET /shops/shop-7/products?category=book&sort=price_asc&limit=30
~~~

Hãy xác định:

1. Filter bắt buộc và filter tùy chọn.
2. Thứ tự sắp xếp có tie-breaker để ổn định phân trang.
3. Những trường nào cần trong kết quả danh sách.
4. Một index MongoDB có thể phù hợp cho truy vấn có category.
5. Truy vấn **không có category** cần thêm index hay không.

Hướng cân nhắc: `shopId` và `category` là equality; `price ASC, productId ASC` là sort. Có thể xét index `(shopId, category, price, productId)`; nếu bỏ category mà vẫn muốn sort theo price trên toàn shop, phải kiểm tra một index khác. Cần xét cả lọc `active = true` hoặc inventory availability nếu nghiệp vụ yêu cầu.

### Bài 2: Tìm lỗi trong truy vấn phân trang

Một lập trình viên dùng:

~~~javascript
db.orders.find({ customerId: "customer-42" })
  .sort({ createdAt: -1 })
  .skip(100000)
  .limit(20);
~~~

Hãy giải thích:

- Vì sao trang sâu có thể tốn chi phí?
- Vì sao thiếu tie-breaker có thể làm kết quả không ổn định?
- Nếu dữ liệu được thêm mới giữa hai lần đọc, offset có thể gây vấn đề gì?
- Hãy nêu một cursor hợp lệ cho thứ tự `createdAt DESC, _id DESC`.

### Bài 3: Sửa khóa bảng CQL theo truy vấn

Bảng:

~~~sql
PRIMARY KEY ((status), customer_id, created_at, order_id)
~~~

Hệ thống chủ yếu truy vấn 20 đơn mới nhất **của một khách hàng**. Hãy đánh giá:

- `status` có quá ít giá trị để làm partition key duy nhất không?
- Query phải biết `status` mới chọn được partition hay không?
- Sắp theo `created_at` của một khách có thuận lợi với cấu trúc đó không?
- Có cần dùng `(customer_id, order_month)` làm partition key, rồi thêm bảng riêng theo status nếu truy vấn status quan trọng?

Không có một đáp án cố định nếu chưa biết tải; điều quan trọng là giải thích được khả năng truy vấn, phân bố dữ liệu và chi phí.

### Bài 4: Giới hạn kết quả sau lọc

Trong một DBMS có cơ chế đọc tối đa 20 item rồi mới áp dụng filter `severity = ERROR`, trang đầu trả 0 item nhưng có token tiếp tục. API nên kết luận thế nào?

**Hướng trả lời:** chưa thể kết luận không có lỗi nào. Phải tiếp tục theo token/phân trang của DBMS trong ngân sách đã định để tìm đủ số item phù hợp hoặc tới khi hết dữ liệu.

### Bài 5: Thiết kế endpoint có ba kiểu sort

Một trang danh mục sản phẩm cho phép:

- Mới nhất: `createdAt DESC, productId DESC`.
- Giá thấp trước: `price ASC, productId ASC`.
- Bán chạy: `salesScore DESC, productId DESC`.

Các sort khác nhau có thể cần những index hoặc bảng đọc khác nhau. Hãy lập ma trận theo filter thường dùng và mỗi thứ tự, đánh dấu biến thể truy vấn nào cần tối ưu trước và liệu `salesScore` có thay đổi quá thường xuyên để làm khóa sắp xếp chính hay không.

## 17. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| “Có trường trong document thì lọc theo trường đó sẽ nhanh.” | Hiệu quả phụ thuộc index, độ chọn lọc và số dữ liệu phải quét. |
| “Primary key luôn là khóa lọc tốt nhất cho mọi API.” | Tra theo ID và tra theo tenant/customer/time là các mẫu truy cập khác nhau. |
| “Status có ít giá trị, vậy dùng làm partition key là hợp lý.” | Cardinality thấp có thể gây partition lớn hoặc nóng. |
| “Index có tất cả trường là chắc chắn tối ưu.” | Thứ tự trường, hướng sort, điều kiện bằng/khoảng và kế hoạch truy vấn quyết định khả năng sử dụng. |
| “LIMIT 20 tức DBMS đọc đúng 20 bản ghi.” | DBMS có thể quét, lọc hoặc sort nhiều ứng viên mới trả 20. |
| “Không ORDER BY thì kết quả thường theo lúc chèn.” | Không có bảo đảm thứ tự nếu truy vấn không yêu cầu rõ. |
| “Sort theo timestamp đủ để phân trang.” | Giá trị bằng nhau cần tie-breaker duy nhất và comparator ổn định. |
| “Cursor luôn cho ảnh chụp nhất quán.” | Cursor định vị thứ tự; dữ liệu vẫn có thể thay đổi giữa các lần đọc. |
| “Một index ghép giải quyết mọi tổ hợp bộ lọc.” | Bỏ điều kiện ở giữa tiền tố index có thể làm kế hoạch lọc/sort khác đi. |
| “ALLOW FILTERING là cách tối ưu Cassandra.” | Có thể tạo truy vấn quét tốn kém; nên xem lại mô hình khóa theo truy vấn. |
| “Thêm nhiều bucket luôn tăng hiệu năng.” | Ghi có thể phân tán hơn, nhưng đọc phải fan-out và merge nhiều kết quả. |
| “DynamoDB Query Limit luôn trả đúng số item mong muốn sau FilterExpression.” | Limit áp dụng theo ngữ nghĩa item được đánh giá; cần theo dõi LastEvaluatedKey. |

## 18. Kết luận

Thiết kế NoSQL theo truy vấn phải bắt đầu bằng ba câu hỏi liên kết:

1. **Lọc theo khóa nào?** Xác định điều kiện bằng, điều kiện khoảng, trường bắt buộc, bộ lọc tùy chọn, cardinality, skew và phạm vi quyền.
2. **Sắp theo thứ tự nào?** Chọn trường mang đúng ngữ nghĩa nghiệp vụ, chiều tăng/giảm và tie-breaker duy nhất để phân trang ổn định.
3. **Trả tối đa bao nhiêu kết quả?** Quy định page size, projection, cursor, timeout và chính sách kết quả thay đổi giữa các trang.

Ba câu hỏi này dẫn đến lựa chọn **partition/shard key, clustering/sort key, compound index hoặc bảng đọc chuyên biệt**. MongoDB thường dùng index ghép cho các mẫu lọc và sort; Cassandra gắn khả năng truy vấn với partition/clustering key; DynamoDB có key condition và quy tắc phân trang riêng. Mỗi hệ có những giới hạn cần được kiểm chứng.

**Truy vấn hiệu quả không được quyết định chỉ bởi `LIMIT`, mà bởi khả năng DBMS tìm đúng nhóm dữ liệu và đọc ra đúng thứ tự với ít công việc nhất.** Hãy đo kế hoạch thực thi, số bản ghi/partition phải xét, p95/p99, chi phí index và độ đúng của phân trang trên dữ liệu có phân bố thực tế, rồi điều chỉnh mô hình trước khi tải tăng vượt khả năng phục vụ.

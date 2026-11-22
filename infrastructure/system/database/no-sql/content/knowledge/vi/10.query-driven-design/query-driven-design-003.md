# Chọn đơn vị lưu trữ từ dữ liệu thường được đọc hoặc ghi cùng nhau

Trong NoSQL, câu hỏi thiết kế quan trọng thường không phải là “có những bảng nào?” mà là **“mỗi yêu cầu nghiệp vụ cần lấy hoặc thay đổi những dữ liệu nào cùng lúc?”**. Nếu dữ liệu thường được đọc chung nhưng nằm rải rác trên nhiều đối tượng, một request phải thực hiện nhiều lần truy cập hoặc kết hợp dữ liệu. Nếu dữ liệu luôn cần cập nhật như một đơn vị nhất quán mà lại bị tách ra, một thao tác ghi có thể phải phối hợp nhiều bản ghi, nhiều phân vùng hoặc thậm chí nhiều dịch vụ.

Từ các mẫu đọc/ghi ấy, ta quyết định ranh giới của **đơn vị lưu trữ**: một document trong document database, một item trong key–value/document store, một key chứa cấu trúc dữ liệu, hay một partition cùng các hàng được nhóm theo khóa trong wide-column database. Quyết định này còn bị chi phối bởi **kích thước, tốc độ tăng, quyền sở hữu, tuổi dữ liệu, mức độ tranh chấp khi ghi và các bảo đảm nguyên tử mà hệ thống cung cấp**.

Bài học dùng một hệ thống bán hàng làm ví dụ xuyên suốt, sau đó đối chiếu MongoDB, Redis và Cassandra. Mục tiêu là học cách suy luận từ **truy vấn và thao tác ghi thực tế** sang **ranh giới dữ liệu hợp lý**, chứ không cố áp dụng một kiểu nhúng hoặc tham chiếu cho mọi loại NoSQL.

## 1. “Đơn vị lưu trữ” là gì trong từng mô hình NoSQL?

Một đơn vị lưu trữ ở đây là **phạm vi dữ liệu được ứng dụng quyết định quản lý, đọc hoặc cập nhật cùng nhau**. Khái niệm đó liên quan đến đối tượng lưu trữ vật lý và giao dịch, nhưng không luôn trùng khít với một đơn vị vật lý bên dưới engine.

| Hệ hoặc mô hình | Đơn vị thường được chọn khi thiết kế | Tại sao ranh giới quan trọng? |
|---|---|---|
| **MongoDB / document** | Một document, có thể chứa object/array lồng nhau | Đọc một aggregate qua một document; ghi trong một document có tính nguyên tử ở phạm vi document |
| **DynamoDB / key–value và document** | Một item được xác định bằng primary key | Đọc/cập nhật item theo key; các thay đổi một item có cơ chế nguyên tử/điều kiện, còn nhiều item cần cơ chế phối hợp phù hợp |
| **Redis / key–value** | Một key và value: String, Hash, List, Set... | Truy cập theo key; từng lệnh có ngữ nghĩa cụ thể, các ràng buộc qua nhiều key cần được thiết kế riêng |
| **Cassandra / wide-column** | Một partition key và các hàng theo clustering columns | Partition key quyết định đường định tuyến và phạm vi đọc; số hàng trong partition ảnh hưởng kích thước, phân trang và tải |
| **Graph database** | Node/relationship và vùng lân cận thường được duyệt | Đặt trọng tâm vào các quan hệ cần đi qua; không nhất thiết “nhúng cả đồ thị” vào một record |

Một số thuật ngữ liên quan:

- **Aggregate**: tập các thực thể/giá trị thuộc cùng một ranh giới nghiệp vụ, thường cần bảo vệ một số bất biến khi thay đổi. Đây là khái niệm thiết kế miền, không phải kiểu dữ liệu riêng của MongoDB.
- **Embedding**: đặt dữ liệu con vào document hoặc value cha.
- **Reference**: lưu ID để truy cập một đối tượng có danh tính riêng.
- **Co-location**: tổ chức dữ liệu để các phần thường dùng chung được truy cập thuận lợi; không mặc nhiên đảm bảo cùng node hay cùng một giao dịch.
- **Access pattern**: cách ứng dụng thực sự tìm, lọc, sắp xếp, giới hạn, đọc và ghi dữ liệu.
- **Consistency boundary**: phạm vi mà ta cần các thay đổi được nhìn nhận như một thao tác nhất quán theo hợp đồng nghiệp vụ.

**Dữ liệu được đọc cùng nhau** là một tín hiệu mạnh để cân nhắc đặt gần nhau. **Dữ liệu được ghi cùng nhau và phải giữ bất biến** là tín hiệu để cân nhắc cùng ranh giới cập nhật nguyên tử. Hai tín hiệu thường trùng, nhưng có những trường hợp xung đột: cùng một thông tin xuất hiện ở rất nhiều màn hình trong khi nó chỉ có một nguồn cập nhật chính.

## 2. Bắt đầu từ hành vi người dùng, không từ sơ đồ thực thể

Xét cửa hàng trực tuyến với khách hàng, giỏ hàng, sản phẩm, tồn kho, đơn hàng và thanh toán. Những thao tác chính:

1. Khách mở **Giỏ hàng của tôi**, thấy tên, số lượng từng sản phẩm và tổng tạm tính.
2. Khách bấm **Đặt hàng**. Hệ thống chốt các dòng hàng, đơn giá tại thời điểm mua và tổng tiền của đơn.
3. Khách mở **Chi tiết đơn hàng**, cần xem toàn bộ dòng hàng và tổng tiền lịch sử.
4. Khách mở **Lịch sử đơn hàng**, cần 20 đơn gần đây theo thời gian.
5. Quản trị viên đổi tên hoặc giá sản phẩm trong catalog; đơn đã mua phải giữ nguyên thông tin giao dịch cũ.
6. Hệ thống thanh toán cập nhật trạng thái; hệ thống kho kiểm soát tồn trên nhiều đơn khác nhau.

Chỉ dùng một sơ đồ thực thể như “Customer — Order — Product” chưa đủ để chọn ranh giới lưu. Ta cần ghi lại **những trường được đọc cùng nhau, được ghi cùng nhau, tần suất và mức nhất quán**.

| Access pattern | Dữ liệu thường dùng cùng nhau | Kiểu thao tác | Đặc điểm quan trọng |
|---|---|---|---|
| Xem một giỏ | userId, các SKU, số lượng | Đọc nguyên giỏ, sửa một dòng | Dữ liệu biến động, có TTL hoặc quy tắc hết hạn |
| Chốt một đơn | customerId, dòng hàng, đơn giá tại mua, tổng tiền | Ghi một đơn mới | Các trường phải thống nhất trong đơn |
| Xem chi tiết đơn | orderId, tổng tiền, các dòng hàng | Đọc nguyên đơn | Một đường đọc rất thường gặp |
| Xem 20 đơn mới nhất | customerId, createdAt, orderTotal, paymentStatus | Lọc và sắp xếp nhiều đơn | Chỉ cần trường tóm lược, phải phân trang |
| Đổi tên sản phẩm | productId, title hiện tại | Cập nhật catalog | Một thay đổi phải phản ánh khi đọc catalog |
| Giảm tồn kho | productId, availableStock | Cập nhật theo nhiều đơn đồng thời | Cần kiểm soát cạnh tranh ghi, không được bán quá quy tắc |
| Nhận thanh toán | orderId, payment event, status | Ghi có retry | Cần chống áp dụng cùng sự kiện hai lần |

Để quyết định đúng còn cần biết:

- **Quy mô**: một đơn tối đa vài chục hay hàng trăm nghìn dòng hàng?
- **Mẫu tải**: 90% request chỉ xem chi tiết đơn hay đọc lịch sử? Có giờ cao điểm không?
- **Mức mới**: giá catalog có phải thấy ngay sau khi sửa, còn số liệu thống kê có thể chậm bao lâu?
- **Danh tính**: sản phẩm có tồn tại độc lập với đơn hàng hay chỉ là một dòng hóa đơn?
- **Vòng đời**: hủy đơn, hoàn tiền, lưu chứng từ và xóa dữ liệu diễn ra thế nào?
- **Quyền truy cập**: mỗi khách chỉ đọc đơn của mình hay quản trị viên cần truy vấn toàn cửa hàng?

Đây là đầu vào để chọn document, item, key hoặc partition; không phải phần bổ sung sau khi thiết kế schema.

## 3. Quy tắc đầu tiên: nhóm dữ liệu thường được đọc như một kết quả

Giả sử khi mở chi tiết đơn, API luôn cần:

~~~text
orderId
createdAt
currency
orderTotal
paymentStatus
items[]:
  sku
  titleAtPurchase
  quantity
  unitPriceAtPurchase
~~~

Nếu mỗi dòng hàng lưu thành một document riêng, một request chi tiết đơn phải đọc header rồi lấy nhiều items. Cách này có thể phù hợp khi items tăng rất lớn, nhưng làm tăng việc truy vấn/ghép dữ liệu so với trường hợp một đơn chỉ có vài dòng.

Với giả định **mỗi đơn có số dòng được giới hạn hợp lý** và thường đọc tất cả dòng cùng nhau, một MongoDB document là lựa chọn tự nhiên:

~~~javascript
{
  _id: "order-2026-101",
  customerId: "customer-17",
  createdAt: ISODate("2026-11-14T09:00:00Z"),
  currency: "VND",
  paymentStatus: "PENDING",
  orderTotal: 260000,
  items: [
    {
      sku: "BOOK-01",
      titleAtPurchase: "Sổ tay",
      quantity: 2,
      unitPriceAtPurchase: 80000
    },
    {
      sku: "PEN-02",
      titleAtPurchase: "Bút ký",
      quantity: 1,
      unitPriceAtPurchase: 100000
    }
  ]
}
~~~

Ở đây, **orderTotal = 2 × 80.000 + 1 × 100.000 = 260.000 VND**. Các dòng hàng thuộc cùng hóa đơn, còn giá và tên hiện tại của catalog **không** được dùng để tính lại đơn cũ.

Điểm cần thấy: một document vừa chứa **thực thể đơn** vừa nhúng **các giá trị con thuộc cùng giao dịch**. Khi mở chi tiết, ứng dụng có đủ các trường mà không cần lấy nhiều document sản phẩm để tái dựng hóa đơn.

Đối chiếu nếu chia ra:

~~~text
orders:
  order-2026-101 { customerId, orderTotal, ... }

order_items:
  item-1 { orderId: order-2026-101, sku: BOOK-01, ... }
  item-2 { orderId: order-2026-101, sku: PEN-02, ... }

Đọc chi tiết:
  1) lấy order
  2) lấy items theo orderId
  3) ghép dữ liệu
~~~

**Số lần đọc ít hơn là một lợi thế, nhưng chưa phải bằng chứng mô hình luôn tốt hơn.** Cần xét kích thước document, tần suất cập nhật items, phân trang, bảo mật và khả năng cạnh tranh ghi.

## 4. Quy tắc thứ hai: nhóm những trường cần giữ bất biến trong một lần ghi

Một đơn đặt hàng thường có bất biến nghiệp vụ:

\[
\text{orderTotal}
=\sum_{i=1}^{n}(\text{quantity}_i\times\text{unitPriceAtPurchase}_i)
\]

Nếu ứng dụng ghi header có tổng 260.000 VND nhưng chỉ lưu thành công một dòng hàng 160.000 VND, chi tiết đơn sẽ mâu thuẫn với số tiền được chốt.

Trong MongoDB, **thao tác ghi một document có tính nguyên tử ở phạm vi document**. Khi ứng dụng tạo order với đầy đủ items và orderTotal cùng một thao tác insert, hệ thống không lộ trạng thái “header đã ghi nhưng mới có một phần items” của chính thao tác đó.

Ví dụ ghi một document:

~~~javascript
db.orders.insertOne({
  _id: "order-2026-101",
  customerId: "customer-17",
  createdAt: ISODate("2026-11-14T09:00:00Z"),
  currency: "VND",
  paymentStatus: "PENDING",
  orderTotal: 260000,
  items: [
    {
      sku: "BOOK-01",
      titleAtPurchase: "Sổ tay",
      quantity: 2,
      unitPriceAtPurchase: 80000
    },
    {
      sku: "PEN-02",
      titleAtPurchase: "Bút ký",
      quantity: 1,
      unitPriceAtPurchase: 100000
    }
  ]
});
~~~

Đây là ví dụ minh họa trên database thử nghiệm, giả định ứng dụng đã xác thực khách hàng, kiểm tra giá và lập đơn hợp lệ. Việc nhúng **không tự kiểm tra phép tính tổng tiền**, số lượng âm hay tính hợp lệ của giá. Những bất biến ấy phải được ứng dụng và các cơ chế kiểm tra dữ liệu thực thi.

Khi chuyển trạng thái thanh toán, ta cũng có thể dùng **cập nhật có điều kiện** trên cùng document:

~~~javascript
db.orders.updateOne(
  {
    _id: "order-2026-101",
    paymentStatus: "PENDING"
  },
  {
    $set: {
      paymentStatus: "PAID",
      paidAt: ISODate("2026-11-14T09:02:00Z")
    }
  }
);
~~~

Điều kiện **paymentStatus: "PENDING"** giúp chỉ áp dụng chuyển trạng thái khi đơn còn ở trạng thái mong đợi. Ứng dụng phải kiểm tra **matchedCount/modifiedCount**, xác nhận sự kiện thanh toán hợp lệ và xử lý retry/idempotency của webhook. Cùng document tạo thuận lợi cho một số cập nhật, nhưng **không bảo đảm mọi bước của quy trình thanh toán bên ngoài là nguyên tử**.

### Khi nào việc ghi cùng lúc vẫn nên tách?

Tồn kho của sản phẩm **BOOK-01** bị ảnh hưởng bởi nhiều đơn, không thuộc riêng đơn **order-2026-101**. Nhúng số tồn kho vào từng order sẽ sinh nhiều bản sao dễ sai. Vì thế:

~~~text
Order aggregate:
  header + item snapshots + trạng thái của đơn

Inventory aggregate:
  productId + availableStock + reservation state

Payment provider:
  trạng thái giao dịch và thông tin xác nhận từ hệ ngoài
~~~

Quá trình đặt hàng có thể phải phối hợp nhiều aggregate. Hệ thống cần chọn transaction nếu điều kiện và database hỗ trợ, hoặc thiết kế reservation, workflow, event, retry và bù trừ theo yêu cầu nhất quán. **“Thường ghi trong cùng một use case” không đồng nghĩa “mọi dữ liệu phải nằm trong một document khổng lồ”.**

## 5. Dữ liệu dùng chung khác dữ liệu thuộc một giao dịch

Một sản phẩm trong catalog được nhiều khách xem và nhiều đơn tham chiếu. Hai loại thông tin cần phân biệt:

| Dữ liệu | Danh tính và vòng đời | Nơi lưu hợp lý trong ví dụ |
|---|---|---|
| Tên/giá bán hiện hành của sản phẩm | Thuộc productId, quản lý bởi catalog, có thể đổi | Document **products** độc lập |
| Tên/giá tại lúc mua | Thuộc dòng hàng của giao dịch đã chốt, phải giữ lịch sử | Nhúng trong **orders.items** |
| Số tồn khả dụng | Chia sẻ giữa nhiều đơn, thay đổi thường xuyên | Mô hình tồn kho riêng |
| Số lượng một SKU trong giỏ | Thuộc giỏ của một người, thay đổi trong khi mua | Có thể nằm trong một cart document/Hash |
| Mã đơn, trạng thái thanh toán | Thuộc một order cụ thể | Cùng document order |

Giả sử ngày mai sản phẩm **BOOK-01** đổi tên thành “Sổ tay A5” và giá thành 90.000 VND. Đơn cũ vẫn cần hiển thị giá **80.000 VND** tại thời điểm mua. Vì vậy, **titleAtPurchase** và **unitPriceAtPurchase** không phải bản cache đồng bộ với catalog; chúng là **snapshot lịch sử**.

Một tên sản phẩm dùng trong danh sách giỏ hàng trước khi chốt đơn lại khác: nếu nghiệp vụ yêu cầu hiển thị tên và giá hiện tại, có thể tham chiếu catalog và lấy dữ liệu mới. Nếu cache giá để đọc nhanh, phải định nghĩa rõ độ mới, cách invalidation và thời điểm kiểm tra lại trước khi thu tiền.

**Nhúng thông tin được dùng chung** chỉ phù hợp khi đã biết nó là snapshot bất biến hoặc là dữ liệu dẫn xuất với hợp đồng đồng bộ rõ ràng.

## 6. Ranh giới tốt cho một đường đọc chưa chắc tốt cho đường đọc khác

Chi tiết đơn và lịch sử đơn là hai access pattern khác nhau:

**Chi tiết đơn** dùng **orderId** và cần toàn bộ items. Một document order nhúng items là lựa chọn thuận tiện.

**Lịch sử đơn** dùng **customerId**, cần các đơn mới nhất nhưng chỉ hiển thị vài trường. Nếu backend lấy toàn bộ items của 20 đơn, lượng dữ liệu truyền và decode có thể lớn hơn cần thiết.

Với MongoDB, có thể giữ cùng mô hình order nhưng dùng **projection** khi đọc danh sách:

~~~javascript
db.orders.createIndex({
  customerId: 1,
  createdAt: -1,
  _id: -1
});

db.orders.find(
  { customerId: "customer-17" },
  {
    _id: 1,
    createdAt: 1,
    paymentStatus: 1,
    orderTotal: 1,
    currency: 1
  }
)
.sort({ createdAt: -1, _id: -1 })
.limit(20);
~~~

Index được thiết kế từ điều kiện lọc theo khách hàng và thứ tự của lịch sử đơn. Projection chỉ lấy dữ liệu cần hiển thị. Không nên suy luận rằng query đã **covered by index**: index ở ví dụ chưa mang đủ các trường projected, nên MongoDB vẫn có thể cần đọc document gốc.

Đường đọc chi tiết:

~~~javascript
db.orders.findOne({
  _id: "order-2026-101",
  customerId: "customer-17"
});
~~~

Điều kiện **customerId** đóng vai trò kiểm soát phạm vi chủ sở hữu; API thực tế phải lấy định danh này từ ngữ cảnh xác thực chứ không tin mã khách do request tự khai. **_id duy nhất không tự kiểm soát quyền truy cập**.

Sự khác nhau giữa hai truy vấn cho thấy **đơn vị lưu trữ** và **hình dạng dữ liệu trả về** không bắt buộc trùng nhau. Một document chứa nhiều trường vẫn có thể được đọc chọn lọc; nhưng với document rất lớn, chi phí I/O và cách engine lấy dữ liệu cần được đo thực tế.

## 7. Trường hợp không nên nhúng: một tập con tăng không giới hạn

Đề xuất dễ gặp là nhúng **mọi đơn hàng vào document khách hàng**:

~~~javascript
// Phương án có nguy cơ tăng vô hạn
{
  _id: "customer-17",
  name: "An",
  orders: [
    { orderId: "order-001", ... },
    { orderId: "order-002", ... },
    // ngày càng có nhiều order...
  ]
}
~~~

Ý tưởng xuất phát từ việc một khách thường xem đơn của chính mình. Tuy nhiên:

- Lịch sử đơn có thể tăng không giới hạn theo số năm hoạt động.
- Mỗi đơn mới đòi hỏi thay đổi một document khách hàng.
- Các truy vấn và cập nhật khác của cùng khách có thể tranh chấp trên document lớn.
- Muốn phân trang 20 đơn mới nhất phải thao tác trên mảng ngày càng lớn.
- Xóa/hoàn tiền/cập nhật một đơn trở nên gắn với document chứa cả lịch sử.
- MongoDB có giới hạn kích thước BSON document **16 MiB**, dù rất nhiều vấn đề hiệu năng xuất hiện trước khi chạm giới hạn đó.

Trong ví dụ này, lựa chọn tự nhiên hơn là **một document cho mỗi order**, với **customerId** và index phục vụ lịch sử. Ta đặt gần những gì thuộc **một đơn** rồi dùng index để lấy nhiều đơn của **một khách**.

Điều tương tự áp dụng cho:

- Nhúng mọi bình luận của một bài viết nổi tiếng vào một document bài viết.
- Nhúng mọi giao dịch của tài khoản vào một document tài khoản.
- Nhúng mọi tin nhắn của một phòng chat vào một document phòng.
- Nhúng mọi lần đo IoT của thiết bị vào một document thiết bị.

Các tập này có thể rất lớn, xuất hiện liên tục và cần phân trang theo thời gian. Khi đó đơn vị lưu thường là **một bản ghi sự kiện/tin nhắn/bình luận**, hoặc một **bucket có kích thước được giới hạn**, thay vì một array tăng vô hạn.

## 8. Khi nào tách dữ liệu con thành collection riêng?

Không phải lúc nào một order cũng có số dòng hàng nhỏ. Giả sử sàn giao dịch B2B cho phép **một đơn có hàng trăm nghìn dòng** và giao diện chi tiết chỉ hiển thị 50 dòng mỗi trang.

Trong trường hợp ấy, nhu cầu đã đổi:

~~~text
Đọc order header:
  orderId, status, total, itemCount

Đọc trang items:
  orderId, cursor, limit=50

Sửa/đối soát từng dòng:
  orderId, lineId
~~~

Phương án tách:

~~~javascript
// orders
{
  _id: "bulk-1001",
  customerId: "business-7",
  orderTotal: 950000000,
  itemCount: 120000,
  status: "CONFIRMED"
}

// order_items
{
  _id: "bulk-1001#line-000001",
  orderId: "bulk-1001",
  lineNo: 1,
  sku: "PART-01",
  quantity: 100,
  unitPriceAtPurchase: 2500
}
~~~

Index phục vụ phân trang:

~~~javascript
db.order_items.createIndex({
  orderId: 1,
  lineNo: 1
});

db.order_items.find({
  orderId: "bulk-1001",
  lineNo: { $gt: 500 }
})
.sort({ lineNo: 1 })
.limit(50);
~~~

Lợi ích: đọc header nhanh mà không phải mang theo 120.000 dòng; phân trang được; cập nhật hoặc kiểm tra một dòng có phạm vi dữ liệu nhỏ.

Đánh đổi: order header và items là **nhiều document**. Nếu nghiệp vụ yêu cầu không bao giờ lộ đơn đã xác nhận mà thiếu một dòng, ta cần một **quy trình tạo và chốt đơn** phù hợp, có thể dùng staging, trạng thái **BUILDING → CONFIRMED**, checksum/tổng kiểm tra, transaction trong phạm vi có thể, hoặc workflow idempotent để hoàn tất theo batch. Một phép insert đơn lẻ không còn bảo vệ toàn bộ tập dữ liệu.

**Chọn đơn vị lưu trữ là tìm điểm cân bằng giữa đọc cùng nhau và giới hạn tăng trưởng, không phải cố đặt càng nhiều dữ liệu trong một document càng tốt.**

## 9. Quy mô, độ nóng và tranh chấp ghi thay đổi kết luận thiết kế

Hai nhóm dữ liệu có thể cùng được đọc nhưng có đặc điểm tải khác nhau:

| Đặc điểm | Nhóm một đơn có 5 dòng | Nhóm một phòng chat có 2 triệu tin nhắn |
|---|---|---|
| Tăng trưởng | Thường kết thúc sau khi chốt đơn | Tiếp tục tăng mỗi giây |
| Mẫu đọc | Chi tiết thường đọc toàn bộ items | Đọc các trang gần nhất hoặc theo khoảng |
| Mẫu ghi | Tạo đơn, đổi vài trạng thái | Nhiều người liên tục gửi tin |
| Tranh chấp ghi | Thường giới hạn theo order | Một document phòng dễ thành điểm nóng |
| Phân trang | Có thể không cần với items nhỏ | Cần thiết |
| Ranh giới khả thi | Một order document | Một message document hoặc bucket có giới hạn |

Một phòng chat hợp lý hơn với:

~~~javascript
// conversations
{
  _id: "room-42",
  title: "Nhóm học tập",
  memberCount: 120
}

// messages
{
  _id: "msg-9001",
  conversationId: "room-42",
  sentAt: ISODate("2026-11-14T09:05:00Z"),
  senderId: "user-8",
  text: "Chào mọi người"
}
~~~

Truy vấn một trang tin nhắn:

~~~javascript
db.messages.createIndex({
  conversationId: 1,
  sentAt: -1,
  _id: -1
});

db.messages.find({
  conversationId: "room-42"
})
.sort({ sentAt: -1, _id: -1 })
.limit(50);
~~~

Một index giúp lấy tin nhắn của phòng theo thời gian mà không yêu cầu sửa document phòng cho mỗi tin. Tuy vậy, ứng dụng còn cần kiểm tra người xem có thuộc phòng và được phép truy cập tin nhắn hay không. Nếu workload cực lớn, cần tiếp tục xem phân vùng, lưu dài hạn, shard, chính sách xóa và dữ liệu dẫn xuất như **lastMessagePreview**.

## 10. Trường hợp key–value: chọn một key và cấu trúc cho dữ liệu đọc/ghi cùng nhau

Với Redis, giỏ hàng thường được định vị bằng **userId**. Nếu nghiệp vụ hay thay đổi **số lượng từng SKU**, một Hash có thể thuận tiện:

~~~redis
HSET cart:customer-17 BOOK-01 2 PEN-02 1
HGETALL cart:customer-17
HINCRBY cart:customer-17 BOOK-01 1
HGET cart:customer-17 BOOK-01
EXPIRE cart:customer-17 3600
~~~

Trong ví dụ:

- **cart:customer-17** là một key dùng để định vị toàn giỏ.
- Mỗi **field** là SKU, còn value là số lượng dưới dạng có thể dùng với **HINCRBY**.
- **HGETALL** đọc toàn bộ các dòng ngắn của giỏ.
- **HINCRBY** tăng một field mà không cần ứng dụng đọc rồi ghi lại toàn Hash.
- **EXPIRE** đặt TTL cho key giỏ, phù hợp nếu chính sách muốn hết hạn một giỏ tạm.

Nếu thay toàn bộ Hash bằng một String JSON:

~~~redis
SET cart:customer-17:json "{\"BOOK-01\":2,\"PEN-02\":1}"
GET cart:customer-17:json
~~~

Ứng dụng thường cần **GET → deserialize → sửa → serialize → SET** khi đổi một SKU. Nếu có hai request đồng thời, cần cơ chế chống lost update như WATCH/MULTI, script hoặc thiết kế khác. Redis Hash có ưu thế cho cập nhật field, nhưng không tự đảm bảo số lượng không âm, giá hiện hành, tồn kho hay tính nhất quán giữa nhiều key.

Đây chính là phép suy luận từ thao tác:

> “Người dùng thường xem cả giỏ; mỗi lần chỉ tăng/giảm một SKU” → “đặt các field của giỏ dưới một key, chọn cấu trúc hỗ trợ cập nhật field”.

Tuy nhiên, nếu giỏ có hàng triệu SKU hoặc rất nhiều client cùng thao tác, key đơn lẻ có thể trở thành hotspot hoặc quá lớn. Khi đó cần đổi ranh giới hoặc yêu cầu sản phẩm. Một key là **đơn vị truy cập thuận tiện**, không phải lời cam kết rằng mọi dữ liệu của một người luôn phải nhét trong một key.

## 11. Trường hợp cột rộng: chọn partition theo dữ liệu được đọc theo dải

Với Cassandra, câu hỏi không chỉ là “đọc những trường nào cùng nhau?” mà còn là **“request biết partition key nào, và cần những hàng nào bên trong partition đó?”**

Giả sử nền tảng IoT muốn xem 100 sự kiện mới nhất của một thiết bị trong một ngày. Mỗi sự kiện có **tenantId, deviceId, eventTime, eventId, severity, payload**.

Ta có thể chọn partition theo **tenant + thiết bị + ngày** và clustering theo thời gian giảm dần:

~~~sql
-- Minh họa CQL trên keyspace thử nghiệm đã cấu hình phù hợp.
CREATE TABLE events_by_device_day (
    tenant_id text,
    device_id text,
    bucket_day date,
    event_time timestamp,
    event_id uuid,
    severity text,
    payload text,
    PRIMARY KEY (
        (tenant_id, device_id, bucket_day),
        event_time,
        event_id
    )
) WITH CLUSTERING ORDER BY (event_time DESC, event_id DESC);
~~~

Truy vấn một ngày:

~~~sql
SELECT event_time, event_id, severity, payload
FROM events_by_device_day
WHERE tenant_id = 'factory-a'
  AND device_id = 'sensor-01'
  AND bucket_day = '2026-11-14'
LIMIT 100;
~~~

Ở đây:

1. **Partition key ghép** là **(tenant_id, device_id, bucket_day)**.
2. **Clustering columns** là **event_time, event_id**.
3. Query có đầy đủ partition key, nên xác định được một partition logic.
4. Các event trong partition có thứ tự phù hợp để lấy những điểm mới nhất.

Nếu muốn đọc 30 ngày, ứng dụng phải xét nhiều **bucket_day**. Nếu muốn “mọi cảnh báo CRITICAL của tất cả cảm biến trong 30 ngày”, bảng theo thiết bị không còn là đường đọc tự nhiên. Có thể cần một bảng truy cập theo **tenant + severity + time bucket**, một index phù hợp đã được benchmark hoặc kho phân tích.

### Chọn bucket lớn hay nhỏ?

Giả sử một cảm biến ghi **10 sự kiện/giây**:

\[
10 \times 86\,400 = 864\,000\ \text{sự kiện/ngày}
\]

Một partition theo ngày có thể chứa gần **864.000 hàng** cho cảm biến đó trước khi xét dữ liệu thiếu/trùng. Nếu dùng bucket theo giờ, trung bình còn:

\[
10 \times 3\,600 = 36\,000\ \text{sự kiện/giờ}
\]

Bucket nhỏ giảm số hàng trong một partition, nhưng đọc nhiều ngày sẽ phải chạm nhiều partition hơn. Bucket lớn giúp giảm fan-out cho khoảng dài nhưng có thể tạo partition rộng, áp lực compaction hoặc hot partition.

Ở Cassandra, **partition** không tương đương **document** và việc gom hàng chung partition không tự bảo đảm nguyên tử nhiều hàng giống một document MongoDB. Cần hiểu riêng cơ chế ghi và consistency của sản phẩm; bài học ở đây chỉ dùng partition để minh họa **ranh giới truy cập và phân bố tải**.

## 12. Một tập dữ liệu có thể cần nhiều hình dạng cho nhiều truy vấn

Xét hai yêu cầu:

**Đường đọc A**: “Lấy 100 sự kiện mới nhất của một thiết bị.”

**Đường đọc B**: “Lấy 50 cảnh báo nghiêm trọng mới nhất của một tenant, bất kể thiết bị.”

Nếu chỉ tạo bảng theo **deviceId**, đường đọc B phải quét rất nhiều thiết bị. Nếu chỉ tạo bảng theo **severity**, đường đọc A lại phải lọc qua nhiều dữ liệu không cần thiết.

Một kiến trúc NoSQL có thể tạo **hai read models**:

~~~text
Sự kiện được xác thực và chuẩn hóa
                  |
                  v
            Nguồn ghi chính
                  |
         +--------+---------+
         |                  |
         v                  v
events_by_device_day    alerts_by_tenant_day
  theo device/time       theo tenant/severity/time
         |                  |
         v                  v
  Lịch sử thiết bị      Dashboard cảnh báo
~~~

Mỗi đường đọc có đơn vị lưu và khóa truy cập phù hợp. Đổi lại là:

- Thêm dung lượng lưu bản sao và index.
- Thêm công việc ghi hoặc cập nhật dữ liệu dẫn xuất.
- Có thể có độ trễ giữa nguồn chính và read model.
- Cần retry, chống ghi trùng và đối soát khi pipeline thất bại.
- Cần quản lý xóa dữ liệu ở cả nguồn và các bản sao.

Đây là trường hợp **phi chuẩn hóa có chủ đích theo truy vấn**. Không nên nhân bản mọi dữ liệu khắp nơi; chỉ thêm một đường lưu khi có access pattern rõ, lợi ích đo được và quy tắc đồng bộ chấp nhận được.

## 13. Ba lựa chọn phổ biến: nhúng, tham chiếu, bản sao phục vụ đọc

Khi một UI cần thông tin từ nhiều thực thể, thường có ba lựa chọn:

| Cách tổ chức | Cơ chế | Khi thường phù hợp | Chi phí chính |
|---|---|---|---|
| **Nhúng** | Dữ liệu con nằm trong cùng document/item/key | Cùng vòng đời, giới hạn kích thước, thường đọc/ghi cùng nhau | Document/key lớn, khả năng cập nhật tập trung |
| **Tham chiếu** | Lưu ID, đọc thực thể riêng khi cần | Thực thể chia sẻ, cập nhật độc lập, quan hệ có thể nhiều | Thêm truy vấn hoặc phép ghép |
| **Read model/denormalize** | Lưu bản dữ liệu được sắp sẵn cho một đường đọc | Đường đọc rất thường xuyên, query ghép tốn kém | Đồng bộ, độ mới, đối soát và xóa dữ liệu sao chép |

Không nhất thiết chỉ được chọn một:

~~~javascript
// Một order minh họa kết hợp cả ba ý tưởng:
{
  _id: "order-2026-101",
  customerId: "customer-17",       // tham chiếu khách hàng
  items: [
    {
      productId: "BOOK-01",        // tham chiếu sản phẩm hiện hành
      titleAtPurchase: "Sổ tay",  // snapshot thuộc đơn
      unitPriceAtPurchase: 80000,
      quantity: 2
    }
  ],
  orderTotal: 160000,
  customerDisplayNameSnapshot: "An" // chỉ lưu nếu có lý do nghiệp vụ rõ
}
~~~

Ví dụ này là một **document minh họa độc lập**, không phải order-2026-101 đã được insert ở phần trước; nếu dùng cùng ID trong một database thật, cần chọn một biến thể dữ liệu nhất quán. **customerDisplayNameSnapshot** chỉ phù hợp nếu ứng dụng cần lưu tên tại thời điểm giao dịch; nếu mục tiêu là hiển thị tên hồ sơ mới nhất, cần truy cập nguồn chính hoặc đồng bộ bản sao.

### Có cần $lookup mọi lúc?

MongoDB hỗ trợ **$lookup** và ứng dụng có thể truy vấn hai pha để lấy các ID tham chiếu. Tuy nhiên, nếu một trang trả 20 order và mỗi order lại gọi riêng một truy vấn sản phẩm, có thể dẫn đến **N+1 queries**.

Lựa chọn thay thế gồm:

- Chỉ lấy thông tin đã nhúng đủ cho mục đích trang.
- Gom các **productId** của trang rồi truy vấn theo **$in** một lần.
- Dùng aggregation **$lookup** sau khi lọc/giới hạn tập cần ghép, nếu ngữ nghĩa cho phép.
- Tạo read model nhỏ nếu chi phí ghép quá cao và chấp nhận quy tắc đồng bộ.

Muốn chọn cách nào, phải đo số lệnh database, byte truyền, độ trễ, kích thước index và độ mới dữ liệu yêu cầu. **Một phép nối không tự xấu; một bản sao cũng không tự tốt.**

## 14. Khi đọc chung và ghi chung đưa ra hai quyết định mâu thuẫn

Giả sử trang chi tiết đơn luôn hiển thị **tên người mua mới nhất** cùng order. Nhưng tên người mua thay đổi trong hồ sơ khách hàng và có thể xuất hiện trên hàng nghìn đơn.

Nếu nhúng tên đang thay đổi vào mỗi order:

~~~text
Đọc:
  nhanh vì có sẵn tên

Ghi:
  đổi tên khách phải sửa hàng nghìn order
  có nguy cơ tên hiển thị khác nhau ở các order khi đồng bộ chậm
~~~

Nếu tham chiếu **customerId**:

~~~text
Đọc:
  cần lấy profile hiện tại (trực tiếp hoặc qua cache)

Ghi:
  đổi tên khách chỉ thay nguồn chính
~~~

Vì thế, ưu tiên phải dựa trên **ngữ nghĩa dữ liệu**:

- Tên *hiện tại* của khách → thông thường do hồ sơ khách hàng sở hữu.
- Tên *trên hóa đơn tại lúc mua* → có thể là snapshot thuộc order.
- Tên được cache để giảm truy vấn → cần TTL/invalidation/versioning và chính sách độ mới.

Không thể giải quyết mâu thuẫn này chỉ bằng câu “đọc cùng nhau thì nhúng”. Ta cần hỏi **ai sở hữu dữ liệu, ai sửa, khi nào được phép thấy bản cũ, và bản sao nào có ý nghĩa nghiệp vụ**.

## 15. Ranh giới dữ liệu và ranh giới giao dịch có liên quan, nhưng khác nhau

Một thao tác nghiệp vụ có thể chạm nhiều đơn vị lưu trữ:

~~~text
Khách bấm Đặt hàng
     |
     +--> tạo order với snapshot items
     +--> giữ/giảm tồn kho của nhiều sản phẩm
     +--> xử lý thanh toán qua hệ ngoài
     +--> phát sự kiện để cập nhật dashboard
~~~

Không nên nhét toàn bộ tồn kho, thông tin payment provider và số liệu dashboard vào cùng một document order chỉ để “ghi cùng lúc”.

Trong mỗi phạm vi:

| Phạm vi | Ví dụ bất biến | Hướng xử lý |
|---|---|---|
| **Một document order** | Dòng hàng và tổng đã chốt khớp nhau | Ghi document đầy đủ; cập nhật trạng thái có điều kiện |
| **Một inventory record** | Không giảm tồn vượt quy tắc cho phép | Conditional update/transaction phù hợp với database |
| **Nhiều document trong cùng database** | Chuyển nhiều bản ghi cùng một quyết định nhất quán | Transaction nếu được hỗ trợ, cân nhắc giới hạn và chi phí |
| **Nhiều dịch vụ / cổng thanh toán** | Không thu tiền hai lần, xử lý retry an toàn | Idempotency, trạng thái workflow, sự kiện và đối soát |
| **Read model bất đồng bộ** | Dữ liệu cuối cùng phản ánh nguồn chính | Chống xử lý trùng, replay/backfill, giám sát độ trễ |

Đơn vị lưu trữ nhỏ giúp cô lập tranh chấp nhưng có thể làm tăng số bước phối hợp. Đơn vị lớn giảm số lần đọc/ghi cho aggregate nhưng có thể kéo theo cập nhật trên phạm vi quá rộng.

### Tránh hiểu nhầm về “atomic”

MongoDB bảo đảm cập nhật **một document** có tính nguyên tử, nhưng không tự bảo đảm sự đúng đắn của tổng tiền nếu ứng dụng ghi số sai. Redis cung cấp những **lệnh nguyên tử** với phạm vi/ngữ nghĩa riêng; gọi liên tiếp nhiều lệnh không mặc nhiên thành một transaction duy nhất. Cassandra cung cấp mô hình partition và batch có các bảo đảm riêng; không thể suy ra nhiều hàng trong một partition luôn có ngữ nghĩa tương đương một document MongoDB.

Do đó, trước khi chọn ranh giới cần liệt kê những **bất biến phải được giữ** và xác định tính nguyên tử được yêu cầu **ở thao tác nào**, chứ không dựa vào nhãn “NoSQL có hỗ trợ transaction”.

## 16. Ước tính kích thước và số lần truy cập trước khi chốt

Một bảng ước lượng giúp chuyển tranh luận cảm tính thành quyết định có thể kiểm chứng:

| Yếu tố | Cách hỏi hoặc đo | Tác động lên ranh giới lưu |
|---|---|---|
| **Số phần tử con** | Một order có bao nhiêu items ở p95/p99? | Array lớn có thể cần collection riêng |
| **Kích thước** | Tổng byte trung bình, p99, tốc độ tăng theo tháng | Tránh document/value vượt giới hạn hoặc tốn I/O |
| **Tần suất đọc chung** | Bao nhiêu request cần tất cả trường cùng lúc? | Nếu cao, nhúng có thể giảm truy vấn |
| **Tần suất ghi độc lập** | Trường nào thay đổi mà không cần các trường khác? | Tách hoặc dùng cấu trúc hỗ trợ cập nhật nhỏ |
| **Tranh chấp ghi** | Bao nhiêu client thay cùng document/key? | Document/key nóng cần điều chỉnh ranh giới |
| **Đọc theo chiều ngược** | Có cần tìm tất cả orders chứa một SKU? | Có thể cần index/read model khác |
| **Độ mới của dữ liệu chia sẻ** | Bản copy được phép trễ bao lâu? | Quyết định reference hay denormalize |
| **Tuổi dữ liệu** | Từng phần có retention khác nhau không? | Dữ liệu có vòng đời riêng có thể cần tách |
| **Độ nhạy và phân quyền** | Những trường nào chỉ vai trò đặc biệt được đọc? | Tách phạm vi dữ liệu đôi khi giảm rủi ro lộ thông tin |
| **Chi phí vận hành** | Index, replication, compaction, backup, payload | Đơn vị quá lớn hoặc nhiều bản sao tăng chi phí |

Ví dụ: giỏ hàng trung bình có 8 SKU, p99 là 45 SKU, mỗi ngày hàng nghìn lượt sửa từng SKU và thường đọc cả giỏ. Một document cart hoặc Redis Hash có thể phù hợp.

Nhưng nếu một “giỏ doanh nghiệp” có p99 hàng trăm nghìn SKU, và người dùng chỉ xem trang 50 SKU, đơn vị lưu sẽ cần đánh giá lại. Một hệ thống không nên áp dụng nguyên schema của giỏ khách lẻ cho khối lượng B2B mà không đo tải.

## 17. Đánh đổi về dữ liệu nóng, dữ liệu lạnh và quyền xóa

Hai nhóm thông tin tuy hay được đọc cùng nhau có thể có **thời hạn sống khác nhau**. Ví dụ:

- Giỏ chưa chốt có thể hết hạn sau một thời gian không hoạt động.
- Đơn hàng đã thanh toán có thể phải lưu theo chính sách chứng từ lâu hơn.
- Session xác thực phải được thu hồi riêng khi logout.
- Lịch sử telemetry có thể chuyển sang archive sau khi hết cửa sổ truy vấn nóng.

Nếu đặt session, giỏ và lịch sử đơn trong một document khách hàng vì “đều thuộc khách”, sẽ khó gắn retention và xử lý xóa độc lập. Các bộ dữ liệu này nên được xem theo **mục đích và vòng đời** riêng.

Trong MongoDB, TTL index có thể dùng cho một số loại document phù hợp; nó không tự bảo đảm mọi bản sao, backup hay dữ liệu dẫn xuất được xóa. Redis có TTL ở key theo cơ chế của Redis. Cassandra có TTL với ngữ nghĩa tombstone và compaction. **Không nên chọn cùng một đơn vị lưu chỉ vì có cùng userId nếu thời hạn và quy tắc xóa của chúng không giống nhau.**

Khi có yêu cầu xóa theo người dùng, cần xác định đường truy cập đến các bản ghi chứa userId, read models, cache và archive. Một cách lưu tối ưu để đọc toàn hệ thống có thể không thuận tiện để tìm và xóa dữ liệu của một chủ thể; yêu cầu này phải xuất hiện trong access patterns từ đầu.

## 18. Thiết kế thay đổi khi xuất hiện một truy vấn mới

Giả sử ban đầu sản phẩm chỉ cần:

> Khách xem lịch sử 20 đơn gần nhất của mình.

Index **(customerId, createdAt DESC, _id DESC)** trên orders có thể phục vụ tốt. Sau đó đội vận hành bổ sung:

> Tìm mọi đơn trong 90 ngày qua có chứa SKU **BOOK-01**, lọc theo trạng thái thanh toán và sắp theo thời điểm.

Đây là truy vấn **theo sản phẩm xuyên nhiều đơn**. Dù items nhúng trong document order, MongoDB có thể truy vấn theo **items.sku** và cân nhắc multikey index thích hợp:

~~~javascript
db.orders.find({
  "items.sku": "BOOK-01",
  paymentStatus: "PAID",
  createdAt: {
    $gte: ISODate("2026-08-16T00:00:00Z"),
    $lt: ISODate("2026-11-15T00:00:00Z")
  }
})
.sort({ createdAt: -1, _id: -1 })
.limit(50);
~~~

Việc tạo index nào hiệu quả cho tổ hợp **array + trạng thái + khoảng thời gian + sort** cần dựa trên **query plan** và quy tắc multikey của MongoDB. Không nên mặc định thêm **items.sku** vào index là mọi bước lọc và sắp xếp đều được index phục vụ tối ưu.

Nếu đây chỉ là báo cáo chạy vài lần mỗi tuần, một job phân tích có thể đủ. Nếu đây là API quan trọng gọi hàng nghìn lần mỗi giây, cần đánh giá **read model/order_items_by_sku** hoặc đường lưu riêng để giảm chi phí quét và join.

Khi yêu cầu mới xuất hiện, đừng vội tách toàn bộ orders thành nhiều document. Hãy so sánh tác động lên những đường đọc/ghi hiện có, đo index, tần suất truy cập và chi phí duy trì bản sao mới.

## 19. Quy trình thực hành chọn đơn vị lưu trữ

Một quy trình có thể áp dụng với nhiều loại NoSQL:

**Bước 1 — Viết các câu hỏi nghiệp vụ thành access patterns.** Không chỉ liệt kê thực thể. Với mỗi thao tác, viết rõ input, filter, sort, limit, field cần trả, mức nhất quán và tần suất.

**Bước 2 — Gạch nhóm những trường luôn được đọc chung.** Nếu cùng một tập nhỏ thường được đọc trọn vẹn, cân nhắc đặt gần nhau, nhúng hoặc cùng một key.

**Bước 3 — Gạch nhóm những thay đổi phải nguyên tử.** Chốt những bất biến như tổng tiền, số lượng hoặc trạng thái. Kiểm tra database bảo đảm điều gì ở phạm vi document/item/key/transaction.

**Bước 4 — Tách dữ liệu có danh tính độc lập hoặc chia sẻ rộng.** Sản phẩm, khách hàng, tồn kho hay quyền truy cập thường có nguồn chính và vòng đời riêng.

**Bước 5 — Ước lượng giới hạn tăng trưởng và tải.** Số phần tử p95/p99, byte, tốc độ ghi, hot key, phân trang và partition fan-out. Tránh mảng/partition tăng không giới hạn.

**Bước 6 — Chọn một mô hình đầu tiên có thể giải thích.** Document nhúng, reference, collection liên kết, key có cấu trúc hoặc partition theo access pattern. Ghi rõ tại sao chọn và trường hợp nào khiến quyết định cần xem lại.

**Bước 7 — Thiết kế index và truy vấn thực tế.** Truy vấn bằng khóa nào? Có cần sắp thứ tự, đọc theo range, join, projection hoặc read model không?

**Bước 8 — Xử lý các đường cập nhật và xóa.** Ghi đồng thời, retry, idempotency, migration, retention, phân quyền, dữ liệu dẫn xuất.

**Bước 9 — Quan sát kết quả.** Đo số truy vấn, lượng dữ liệu chuyển, số document/partition phải đọc, độ trễ p95/p99, conflict rate và lag đồng bộ.

~~~mermaid
flowchart TD
    A["Yêu cầu nghiệp vụ"] --> B["Access patterns đọc và ghi"]
    B --> C["Nhóm trường thường đọc cùng nhau"]
    B --> D["Nhóm bất biến cần ghi nhất quán"]
    C --> E["Ứng viên: document/item/key/partition"]
    D --> E
    E --> F{"Tăng trưởng, tải, vòng đời phù hợp?"}
    F -->|Có| G["Thiết kế khóa, index, truy vấn"]
    F -->|Không| H["Tách phần tăng lớn hoặc dữ liệu độc lập"]
    H --> G
    G --> I["Đo kết quả và chi phí"]
    I -->|Chưa đạt| B
    I -->|Đạt| J["Theo dõi khi workload thay đổi"]
~~~

Quy trình này không nhất thiết dẫn đến một schema không thay đổi. Thiết kế theo truy vấn là quá trình đối chiếu mô hình với workload đang tồn tại và nhu cầu mới, sau đó thay đổi có kiểm soát khi bằng chứng cho thấy mô hình cũ không còn đáp ứng.

## 20. Kiểm chứng bằng một kịch bản cụ thể

Với **order-2026-101** ở phần đầu, ta kỳ vọng:

| Tình huống | Kết quả cần thấy | Điều được kiểm chứng |
|---|---|---|
| Đọc chi tiết order-2026-101 | Hai dòng hàng, tổng 260.000 VND, trạng thái PENDING trước khi thanh toán | Đơn và snapshot item đọc cùng một document |
| Đổi catalog BOOK-01 lên 90.000 VND | Đơn cũ vẫn hiển thị giá 80.000 VND cho BOOK-01 | Giá lịch sử độc lập với catalog hiện hành |
| Webhook hợp lệ chuyển PENDING → PAID | Chỉ chuyển theo trạng thái được phép; retry phải được xử lý | Cập nhật trên document và logic idempotency |
| Lấy 20 đơn mới nhất của customer-17 | Thứ tự createdAt DESC, _id DESC; không trả toàn bộ items | Đọc danh sách theo index/projection |
| Đơn B2B có 120.000 dòng | Header đọc riêng, items phân trang | Ranh giới đơn vị lưu được thay đổi theo cardinality |
| Truy vấn tất cả đơn chứa BOOK-01 | Dùng đường lọc/index/read model thích hợp; đo kế hoạch thực thi | Đường đọc mới có thể cần cấu trúc khác |

Một lần query trả đúng kết quả trên vài document mẫu **chưa chứng minh** schema đáp ứng tải production. Cần đo với dữ liệu và độ đồng thời gần thực tế.

Đối với MongoDB, một phép quan sát kỹ thuật:

~~~javascript
db.orders.find(
  { customerId: "customer-17" },
  { _id: 1, createdAt: 1, paymentStatus: 1, orderTotal: 1 }
)
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.explain("executionStats");
~~~

Xem **winningPlan**, **nReturned**, **totalKeysExamined**, **totalDocsExamined** và khả năng có bước sort riêng. Với Redis, đo latency và số lệnh cho đường đọc/ghi giỏ; với Cassandra, đo số partition/bucket, hàng/tombstone phải duyệt và latency. Công cụ khác nhau, nhưng câu hỏi chung là:

> **Để trả đúng một kết quả nghiệp vụ, hệ thống phải chạm bao nhiêu dữ liệu và phối hợp bao nhiêu bước?**

## 21. Những nhầm lẫn dễ gặp

| Nhầm lẫn | Vấn đề thực tế | Cách nhìn đúng |
|---|---|---|
| “Cùng một người dùng thì nhúng vào một document khách hàng” | Order/session/log tăng không giới hạn và có vòng đời khác nhau | Nhóm theo đơn vị thao tác và aggregate, không chỉ theo người sở hữu |
| “Đọc chung thì bắt buộc nhúng” | Dữ liệu chia sẻ có thể thay đổi ở hàng nghìn nơi | Xét nguồn chính, vòng đời và chi phí đồng bộ |
| “Ghi trong một use case thì phải cùng document” | Inventory, order, payment là các miền độc lập | Xác định bất biến và ranh giới giao dịch phù hợp |
| “Document càng lớn càng ít truy vấn nên càng nhanh” | Update/contention, phân trang, I/O, giới hạn kích thước | Đo kích thước và truy cập thực tế |
| “Tham chiếu luôn làm chậm” | Có thể tránh nhân bản dữ liệu và cập nhật hàng loạt | Dùng index, batch read, lookup hoặc cache đúng chỗ |
| “Một schema phục vụ mọi truy vấn” | Đọc theo chiều khác có thể thành quét lớn | Tạo read model/index cho access pattern quan trọng |
| “Đặt cùng partition là nguyên tử như một document” | Ngữ nghĩa nguyên tử khác nhau giữa các hệ | Kiểm tra bảo đảm cụ thể của database |
| “Có snapshot thì phải đồng bộ khi dữ liệu gốc đổi” | Snapshot lịch sử bị ghi đè và mất ý nghĩa | Phân biệt snapshot với cache dẫn xuất |
| “LIMIT nhỏ thì không tốn nhiều I/O” | Có thể phải lọc/quét rất nhiều bản ghi trước khi có kết quả | Đo keys/docs/partition/hàng thực sự đọc |
| “Schema được quyết định một lần” | Mẫu truy vấn, quy mô và nghiệp vụ thay đổi | Quan sát và điều chỉnh mô hình có chủ đích |

## 22. Bài tập áp dụng

### Bài tập 1 — Chi tiết đơn và lịch sử đơn

Một hệ có 500.000 khách hàng; mỗi đơn trung bình 6 dòng, p99 là 45 dòng. Màn hình chi tiết gần như luôn hiển thị toàn bộ items, còn lịch sử đơn chỉ cần tổng tiền, thời điểm và trạng thái. Hãy đề xuất:

- Ranh giới document của đơn và dòng hàng.
- Truy vấn/index cho 20 đơn mới nhất của một khách.
- Lý do không nhúng mọi order vào document customer.
- Tình huống tăng trưởng nào khiến bạn cần tách items ra.

### Bài tập 2 — Đọc chung nhưng cập nhật độc lập

Trang sản phẩm hiển thị **title, category, price, inventory**. Title đổi vài lần mỗi tháng; tồn kho đổi hàng nghìn lần mỗi phút. Hãy phân tích có nên lưu mọi trường trong cùng một document, tách inventory ra hay dùng read model. Nêu ranh giới bất biến và tác động của ghi đồng thời.

### Bài tập 3 — Giỏ hàng trên nhiều thiết bị

Người dùng có thể sửa giỏ từ hai thiết bị cùng lúc, thường tăng/giảm một SKU, giỏ có tối đa 100 SKU. So sánh Redis String JSON, Redis Hash và MongoDB cart document theo thao tác field, chống lost update, TTL và cách đọc toàn giỏ.

### Bài tập 4 — Tin nhắn nhóm

Một nhóm chat có thể tích lũy 10 triệu tin nhắn. Giao diện chỉ hiển thị 50 tin gần nhất, có phân trang về quá khứ. Hãy đề xuất document, key/index và giải thích vì sao mảng **messages[]** nằm trong document nhóm không còn phù hợp.

### Bài tập 5 — Dữ liệu cột rộng

Một thiết bị phát 10 sự kiện/giây. So sánh partition theo **device + ngày** với **device + giờ** về số hàng mỗi partition và số partition cần truy cập để lấy dữ liệu 7 ngày. Nếu cần xem mọi cảnh báo của một tenant, đề xuất thêm một access table.

### Bài tập 6 — Dữ liệu chia sẻ và lịch sử

Giá sản phẩm hôm nay tăng 15%. Khách cần xem giá mới trong catalog nhưng hóa đơn tháng trước phải giữ giá đã mua. Hãy xác định trường nào là dữ liệu dùng chung, trường nào là snapshot và điều gì sẽ sai nếu mọi order luôn join giá hiện hành.

### Bài tập 7 — Giao dịch xuyên aggregate

Quy trình đặt hàng gồm tạo order, giữ tồn kho và thu tiền. Hãy chỉ ra những bất biến cần giữ, những bước nào nằm ngoài một document, nơi cần idempotency/compensation và cách phát hiện một thao tác dở dang sau timeout.

### Bài tập 8 — Chọn mô hình dựa trên bằng chứng

Một đội đề xuất nhúng 100.000 đối tượng con vào mỗi document vì “trang chi tiết cần tất cả”. Hãy đặt các câu hỏi về p95/p99 kích thước, tần suất đọc nguyên tập, cập nhật độc lập, phân trang, contention, giới hạn engine và thời hạn giữ trước khi chấp nhận quyết định. Nêu một truy vấn thử nghiệm và những metrics giúp quyết định.

Khi trả lời các bài tập, hãy theo chuỗi **yêu cầu đọc/ghi → dữ liệu cần đi cùng nhau → bất biến và chủ sở hữu → giới hạn tăng trưởng → document/item/key/partition → truy vấn/index → kết quả quan sát**. Cách suy luận này giúp chọn đơn vị lưu trữ NoSQL từ hành vi thực của hệ thống, đồng thời nhận diện được những trường hợp phải tách hoặc tạo đường đọc khác khi tải và yêu cầu thay đổi.

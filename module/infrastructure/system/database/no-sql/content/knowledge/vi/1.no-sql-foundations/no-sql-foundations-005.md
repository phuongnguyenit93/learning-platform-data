# Luồng từ yêu cầu nghiệp vụ đến truy vấn, mô hình lưu trữ và kết quả quan sát được

Một quyết định thiết kế NoSQL tốt bắt đầu từ câu hỏi **hệ thống phải trả lời điều gì cho người dùng, trong điều kiện nào**, rồi mới đi đến collection, document, key hay index. Cùng một tập dữ liệu có thể được tổ chức theo nhiều cách; cách phù hợp phụ thuộc vào đường đọc/ghi quan trọng, độ lớn dữ liệu, yêu cầu nhất quán và kết quả phải quan sát được.

Trong bài này, ta lần theo một yêu cầu từ ngôn ngữ nghiệp vụ đến một truy vấn MongoDB cụ thể. MongoDB được dùng để minh họa tư duy thiết kế NoSQL dạng document; quy trình phân tích vẫn áp dụng được cho key-value, wide-column hay cơ sở dữ liệu đồ thị, dù cú pháp truy vấn và mô hình lưu trữ sẽ khác.

## 1. Nhìn toàn bộ luồng trước khi chọn công nghệ

~~~mermaid
flowchart TD
    A["Yêu cầu nghiệp vụ: ai cần thấy gì?"] --> B["Hợp đồng truy cập: lọc, sắp xếp, giới hạn, độ mới"]
    B --> C["Access patterns: đọc/ghi nào thường xuyên và quan trọng?"]
    C --> D["Mô hình lưu trữ: document, key, quan hệ, bản sao đọc"]
    D --> E["Index và truy vấn thực thi"]
    E --> F["Kết quả trả về và dữ liệu hiển thị"]
    F --> G["Quan sát: đúng dữ liệu? nhanh? nhất quán?"]
    G -->|Không đạt yêu cầu| B
    G -->|Đạt yêu cầu| H["Ghi nhận hợp đồng và theo dõi khi tải thay đổi"]
~~~

Mỗi mũi tên là một quyết định có thể giải thích:

1. **Nghiệp vụ** xác định ai đang thao tác, hành động nào thành công và điều gì được coi là đúng.
2. **Hợp đồng truy cập** biến mô tả đó thành điều kiện lọc, thứ tự, phân trang, trường trả về và mức độ mới của dữ liệu.
3. **Access pattern** cho biết đường truy cập nào phải tối ưu trước. Ví dụ: tra một đơn theo mã, liệt kê đơn theo khách hàng và ghi trạng thái thanh toán là ba thao tác khác nhau.
4. **Mô hình lưu trữ** quyết định dữ liệu nào đặt cùng nhau, dữ liệu nào tham chiếu nhau và khi nào cần bản sao phục vụ đọc.
5. **Truy vấn và index** hiện thực hợp đồng với chi phí có thể kiểm soát.
6. **Quan sát** đối chiếu dữ liệu trả về, trạng thái giao diện và số liệu thực thi với yêu cầu ban đầu.

NoSQL không có nghĩa là “không cần schema”. Schema vẫn tồn tại trong cấu trúc dữ liệu, quy ước ứng dụng và ràng buộc nghiệp vụ. Sự linh hoạt của document không thể thay cho việc xác định các bất biến như chủ sở hữu đơn hàng hay cách tính tổng tiền.

## 2. Bắt đầu từ một yêu cầu nghiệp vụ cụ thể

Giả sử nhóm sản phẩm đưa ra yêu cầu:

> Khi một khách hàng mở trang **Đơn hàng của tôi**, hiển thị **3 đơn đã thanh toán mới nhất** của chính khách hàng đó. Mỗi dòng có mã đơn, thời điểm đặt, tổng tiền và tối đa 2 tên mặt hàng để xem trước. Khi mở chi tiết, người dùng phải thấy đầy đủ các mặt hàng và mức giá tại thời điểm mua.

Yêu cầu trên vẫn còn nhiều điểm cần làm rõ. Với ví dụ học tập này, ta chốt các giả định sau:

| Khía cạnh | Quy tắc nghiệp vụ được chốt | Tác động kỹ thuật |
|---|---|---|
| Người xem | Chỉ xem đơn thuộc tài khoản đã xác thực | Luôn lọc theo **customerId** lấy từ ngữ cảnh xác thực |
| “Đã thanh toán” | **paymentStatus = PAID**; độc lập với trạng thái giao hàng | Không được lọc nhầm sang **shippingStatus** |
| “Mới nhất” | Giảm dần theo **createdAt**, sau đó theo **_id** để phá hòa | Cần thứ tự xác định ngay cả khi nhiều đơn cùng thời điểm |
| Số lượng | Tối đa 3 đơn ở trang đầu | Áp dụng giới hạn tại cơ sở dữ liệu |
| Xem trước sản phẩm | Tối đa 2 phần tử đầu của **items** | Chỉ trả phần dữ liệu cần hiển thị trong danh sách |
| Mở chi tiết | Hiển thị tất cả mặt hàng của đúng một đơn | Có truy vấn riêng cho chi tiết |
| Giá lịch sử | Tên, số lượng, đơn giá tại thời điểm mua không đổi khi catalog thay đổi | Lưu **snapshot** mặt hàng trong đơn |
| Tiền tệ và thời gian | Tiền VND dưới dạng số nguyên; thời điểm lưu theo UTC | Tránh sai số tiền tệ và nhập nhằng múi giờ |

Để luyện tư duy hiệu năng, có thể đặt mục tiêu giả định “thời gian xử lý truy vấn trang đầu ở phân vị p95 không quá 200 ms dưới tải đã xác định”. Đây là **mục tiêu để kiểm tra**, không phải số liệu đã đo hay cam kết MongoDB tự bảo đảm.

Từ yêu cầu, ta viết ra một hợp đồng dễ kiểm tra:

~~~text
Input:
  customerId = c7 (lấy từ danh tính đã xác thực)
  limit = 3

Filter:
  customerId == c7
  paymentStatus == PAID

Order:
  createdAt DESC, _id DESC

Output per row:
  _id, createdAt, orderTotal, currency, items[0..1]

Detail:
  (_id == orderId) AND (customerId == c7)
  trả về toàn bộ items
~~~

Điểm cốt lõi: trước khi chọn cách lưu, ta đã biết chính xác **truy vấn cần trả lời câu hỏi gì**. Nếu chưa thể viết rõ hợp đồng này, việc tranh luận “nên nhúng hay tham chiếu?” thường diễn ra quá sớm.

## 3. Từ hợp đồng thành access patterns

Không nên lấy tên thực thể “Khách hàng — Đơn hàng — Sản phẩm” làm thiết kế lưu trữ ngay. Trước tiên, hãy liệt kê thao tác thực tế của ứng dụng.

| Access pattern | Đầu vào | Kết quả mong muốn | Đặc điểm tải |
|---|---|---|---|
| Xem danh sách đơn đã trả tiền | customerId, giới hạn, cursor | Đơn mới nhất, ít trường | Đọc thường xuyên, nhạy với độ trễ |
| Xem chi tiết một đơn | customerId, orderId | Một đơn và đầy đủ items | Đọc theo khóa |
| Đánh dấu thanh toán thành công | orderId, định danh sự kiện thanh toán | Cập nhật trạng thái đúng một lần về mặt nghiệp vụ | Ghi phải idempotent |
| Thống kê doanh thu theo ngày | khoảng thời gian, nhóm báo cáo | Tổng hợp số liệu | Đọc quét/tổng hợp, có thể cần đường dữ liệu riêng |

Một collection không nhất thiết phải tối ưu ngang nhau cho cả bốn đường truy cập. Danh sách và chi tiết là hai luồng quan trọng của bài toán; thống kê doanh thu được ghi nhận để tránh lầm tưởng rằng cùng một index phục vụ hiệu quả mọi truy vấn.

Với NoSQL, một câu hỏi định hướng hữu ích là:

> Nếu ứng dụng thực hiện truy vấn này hàng nghìn lần mỗi phút, dữ liệu nào cần nằm gần nhau để số lần đọc, lượng dữ liệu tải về và số lần kết hợp được giới hạn?

“Nằm gần nhau” ở đây có thể là cùng một document, cùng partition, cùng key-space hoặc cùng bản ghi được chuẩn bị sẵn cho một đường đọc; cách hiện thực tùy loại NoSQL.

## 4. Chọn ranh giới document theo đơn vị đọc và cập nhật

Với ví dụ này, một đơn hàng là một **aggregate** tự nhiên: người dùng mở một đơn và cần xem các mặt hàng, tổng tiền, trạng thái thanh toán của nó. Ta có thể lưu một document cho mỗi đơn:

~~~javascript
{
  _id: "o104",
  customerId: "c7",
  paymentStatus: "PAID",
  shippingStatus: "PACKING",
  createdAt: ISODate("2026-10-07T10:00:00Z"),
  orderTotal: 280000,
  currency: "VND",
  items: [
    { sku: "PEN", title: "Bút", quantity: 1, unitPrice: 80000 },
    { sku: "BOOK", title: "Sổ", quantity: 2, unitPrice: 50000 },
    { sku: "BAG", title: "Túi", quantity: 1, unitPrice: 100000 }
  ]
}
~~~

Trong document này, **orderTotal = 80.000 + 2 × 50.000 + 100.000 = 280.000 VND**. Các trường **title** và **unitPrice** trong **items** là snapshot của giao dịch, không phải dữ liệu catalog được tra lại theo giá hiện hành.

Lý do nhúng **items**:

- Chi tiết đơn đọc toàn bộ items cùng lúc; không cần ghép từng mặt hàng từ collection khác chỉ để hiện hóa đơn.
- Khi một đơn được xác nhận, các dòng hàng và tổng tiền thuộc cùng ranh giới nghiệp vụ; cập nhật trong một document có tính nguyên tử ở mức document của MongoDB.
- Giá và tên sản phẩm lịch sử cần bền vững trước thay đổi của catalog.

Nhưng cần nêu rõ điều kiện: thiết kế trên giả định mỗi đơn có số mặt hàng **được giới hạn hợp lý**. Nếu một đơn có thể chứa hàng triệu dòng, việc nhúng toàn bộ sẽ tạo document quá lớn, tăng chi phí đọc/ghi và có nguy cơ chạm giới hạn kích thước document của MongoDB. Khi đó có thể đặt thông tin đầu đơn ở **orders** và dòng hàng ở **order_items**, rồi thiết kế lại đường đọc chi tiết, phân trang dòng hàng và tính nhất quán khi ghi.

Tương tự, **không** nên nhúng tất cả đơn hàng của một khách vào một document khách hàng: lịch sử đơn tăng không giới hạn, nhiều lần thêm đơn cùng cập nhật một document và việc phân trang theo thời gian trở nên khó kiểm soát.

Phân biệt hai loại dữ liệu:

| Dữ liệu | Vai trò | Cách xử lý minh họa |
|---|---|---|
| Product catalog | Giá và tên đang bán, có thể thay đổi | Có nguồn dữ liệu riêng |
| Order items snapshot | Giá, tên, số lượng đã giao dịch | Nhúng trong đơn; giữ ổn định sau khi chốt |
| orderTotal | Giá trị đã chốt của đơn | Ghi cùng đơn; kiểm tra bất biến tổng tiền khi tạo |
| paymentStatus | Trạng thái nghiệp vụ có thể thay đổi | Cập nhật theo luồng thanh toán có kiểm soát |
| customerId | Phân tách chủ sở hữu và đường truy cập | Lưu trên mỗi đơn và luôn kiểm tra khi đọc |

Việc lặp lại **title** và **unitPrice** ở đây là **phi chuẩn hóa có chủ đích để bảo toàn lịch sử giao dịch**. Phi chuẩn hóa phải có lý do nghiệp vụ, quy tắc cập nhật và nhận thức rõ chi phí lưu trữ; nó không đồng nghĩa với nhân bản mọi trường ở khắp nơi.

## 5. Tạo bộ dữ liệu mẫu và truy vấn thực tế

Ví dụ dưới đây dùng cú pháp **mongosh**. Dữ liệu hoàn toàn giả lập và các câu lệnh có thể chạy trong database thử nghiệm.

~~~javascript
db.orders.insertMany([
  {
    _id: "o101", customerId: "c7", paymentStatus: "PAID",
    createdAt: ISODate("2026-10-04T10:00:00Z"),
    orderTotal: 300000, currency: "VND",
    items: [{ sku: "DESK", title: "Bàn nhỏ", quantity: 1, unitPrice: 300000 }]
  },
  {
    _id: "o102", customerId: "c7", paymentStatus: "PAID",
    createdAt: ISODate("2026-10-05T10:00:00Z"),
    orderTotal: 450000, currency: "VND",
    items: [
      { sku: "MUG", title: "Cốc", quantity: 2, unitPrice: 120000 },
      { sku: "LAMP", title: "Đèn", quantity: 1, unitPrice: 210000 }
    ]
  },
  {
    _id: "o103", customerId: "c7", paymentStatus: "PENDING",
    createdAt: ISODate("2026-10-06T10:00:00Z"),
    orderTotal: 100000, currency: "VND",
    items: [{ sku: "BOOK", title: "Sổ", quantity: 2, unitPrice: 50000 }]
  },
  {
    _id: "o104", customerId: "c7", paymentStatus: "PAID",
    createdAt: ISODate("2026-10-07T10:00:00Z"),
    orderTotal: 280000, currency: "VND",
    items: [
      { sku: "PEN", title: "Bút", quantity: 1, unitPrice: 80000 },
      { sku: "BOOK", title: "Sổ", quantity: 2, unitPrice: 50000 },
      { sku: "BAG", title: "Túi", quantity: 1, unitPrice: 100000 }
    ]
  },
  {
    _id: "o105", customerId: "c7", paymentStatus: "PAID",
    createdAt: ISODate("2026-10-08T10:00:00Z"),
    orderTotal: 120000, currency: "VND",
    items: [{ sku: "MUG", title: "Cốc", quantity: 1, unitPrice: 120000 }]
  },
  {
    _id: "o106", customerId: "c9", paymentStatus: "PAID",
    createdAt: ISODate("2026-10-09T10:00:00Z"),
    orderTotal: 990000, currency: "VND",
    items: [{ sku: "CHAIR", title: "Ghế", quantity: 1, unitPrice: 990000 }]
  }
]);
~~~

Trong sáu document này:

- **o103** mới hơn o102 nhưng đang **PENDING**, vì vậy không xuất hiện.
- **o106** là đơn mới nhất toàn bộ collection nhưng thuộc **c9**, vì vậy không xuất hiện với **c7**.
- **o101** đã thanh toán và thuộc c7, nhưng cũ hơn ba đơn hợp lệ mới nhất.

### Truy vấn trang danh sách

~~~javascript
db.orders.find(
  {
    customerId: "c7",
    paymentStatus: "PAID"
  },
  {
    _id: 1,
    createdAt: 1,
    orderTotal: 1,
    currency: 1,
    items: { $slice: 2 }
  }
)
.sort({ createdAt: -1, _id: -1 })
.limit(3);
~~~

Đọc truy vấn từ trong ra ngoài:

1. Điều kiện **customerId** giới hạn đúng chủ sở hữu; ứng dụng phải lấy giá trị này từ token/session đã xác thực, không tin một mã khách bất kỳ do người gọi tự gửi.
2. Điều kiện **paymentStatus** hiện thực chính xác chữ “đã thanh toán”.
3. Phép chiếu chỉ lấy các trường phục vụ danh sách; **$slice: 2** giới hạn phần tử **items** ở dạng xem trước, không xóa dữ liệu gốc.
4. **sort** tạo thứ tự mới nhất và dùng **_id** phá hòa.
5. **limit(3)** giới hạn số document mà truy vấn trả về.

### Kết quả phải quan sát được

Với dữ liệu mẫu, thứ tự và các trường cơ bản được mong đợi là:

| Vị trí | _id | createdAt (UTC) | orderTotal | Mặt hàng xem trước |
|---:|---|---|---:|---|
| 1 | o105 | 2026-10-08 10:00 | 120.000 VND | Cốc |
| 2 | o104 | 2026-10-07 10:00 | 280.000 VND | Bút, Sổ |
| 3 | o102 | 2026-10-05 10:00 | 450.000 VND | Cốc, Đèn |

Điểm đáng chú ý là **o104** có ba dòng hàng trong database, nhưng danh sách chỉ mang về hai dòng đầu. Khi mở chi tiết, giao diện phải thấy cả dòng **Túi**; nếu không, ứng dụng đã dùng nhầm dữ liệu “preview” làm dữ liệu đầy đủ.

### Truy vấn chi tiết

~~~javascript
db.orders.findOne({
  _id: "o104",
  customerId: "c7"
});
~~~

Truy vấn này trả document **o104** với cả ba dòng hàng. Điều kiện **customerId** vẫn quan trọng dù **_id** là duy nhất: tính duy nhất của khóa không tự thực hiện kiểm soát quyền truy cập. Với người dùng **c9**, cùng điều kiện **_id = o104** phải trả **null**.

## 6. Index được suy ra từ điều kiện truy vấn, không phải từ danh sách tên cột

Đường đọc danh sách cần lọc hai trường bằng giá trị chính xác và sắp xếp theo hai trường tiếp theo. Một index ứng viên hợp lý là:

~~~javascript
db.orders.createIndex({
  customerId: 1,
  paymentStatus: 1,
  createdAt: -1,
  _id: -1
});
~~~

Ý nghĩa thứ tự trường:

- **customerId** và **paymentStatus** là các điều kiện bằng nhau, giúp thu hẹp dải khóa.
- **createdAt** và **_id** đi theo thứ tự sắp xếp, giúp database có cơ hội đọc trực tiếp các khóa mới nhất.
- Truy vấn chỉ cần 3 phần tử đầu nên có thể dừng sớm khi kế hoạch thực thi phù hợp.

Index không tự động làm mọi truy vấn nhanh hơn. Nó tốn dung lượng và chi phí cập nhật, và có thể không được query planner chọn nếu thống kê hoặc phân bố dữ liệu khiến kế hoạch khác có lợi hơn. Vì truy vấn còn cần đọc **items**, đây không phải truy vấn được index trên bao phủ hoàn toàn (covered query); một bước đọc document gốc có thể vẫn cần thiết.

Với truy vấn chi tiết, index duy nhất mặc định của **_id** thường đã giúp tìm document mục tiêu. Cơ sở dữ liệu vẫn cần kiểm tra **customerId**; không nhất thiết phải tạo thêm compound index chỉ cho một lookup theo **_id** nếu chưa có bằng chứng cần thiết.

Để xem hành vi thực tế, dùng **explain** trên truy vấn đại diện:

~~~javascript
db.orders.find(
  { customerId: "c7", paymentStatus: "PAID" },
  { _id: 1, createdAt: 1, orderTotal: 1, currency: 1, items: { $slice: 2 } }
)
.sort({ createdAt: -1, _id: -1 })
.limit(3)
.explain("executionStats");
~~~

Các tín hiệu cần diễn giải:

| Tín hiệu | Câu hỏi cần trả lời |
|---|---|
| **winningPlan** và các stage như **IXSCAN**, **FETCH**, **SORT**, **COLLSCAN** | Database đi qua index, đọc document hay quét collection? Có sắp xếp tốn thêm bước không? |
| **nReturned** | Số document trả về có đúng giới hạn không? |
| **totalKeysExamined** | Đã phải duyệt bao nhiêu khóa index? |
| **totalDocsExamined** | Đã phải đọc bao nhiêu document để trả số kết quả đó? |
| **executionTimeMillis** | Lần chạy explain này mất bao lâu trong điều kiện hiện tại? |

Trong một bộ dữ liệu sáu document, việc đo thời gian có rất ít giá trị để suy ra hiệu năng sản xuất. Cần thử trên quy mô, phân bố khách hàng, tỷ lệ thanh toán, kích thước items và tải đồng thời tương tự thực tế. **executionTimeMillis** của một lần chạy không thay thế cho phân vị p95 ở ứng dụng; muốn đánh giá mục tiêu độ trễ phải đo nhiều yêu cầu trong điều kiện tải xác định.

## 7. Phân trang khi dữ liệu tiếp tục phát sinh

Giới hạn trang đầu bằng **limit(3)** mới giải quyết phần đầu tiên. Nếu khách hàng có nhiều đơn, ứng dụng cần phân trang. Dùng **skip** với offset lớn có thể buộc cơ sở dữ liệu đi qua rất nhiều bản ghi trước khi lấy trang cần thiết; dữ liệu được thêm vào trong khi chuyển trang cũng có thể khiến kết quả bị trùng hoặc bỏ sót.

Với thứ tự **createdAt DESC, _id DESC**, có thể dùng **keyset/cursor pagination**. Trang đầu trong ví dụ kết thúc tại:

~~~text
lastCreatedAt = 2026-10-05T10:00:00Z
lastId        = o102
~~~

Trang tiếp theo chỉ lấy các bản ghi có khóa sắp xếp **nhỏ hơn** cặp cuối trang trước:

~~~javascript
db.orders.find({
  customerId: "c7",
  paymentStatus: "PAID",
  $or: [
    { createdAt: { $lt: ISODate("2026-10-05T10:00:00Z") } },
    {
      createdAt: ISODate("2026-10-05T10:00:00Z"),
      _id: { $lt: "o102" }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(3);
~~~

Với dữ liệu mẫu, trang kế tiếp chỉ còn **o101**. Điều kiện thứ hai trong **$or** xử lý trường hợp nhiều đơn có cùng **createdAt**. Trong ứng dụng thực tế, cursor nên mã hóa cả hai giá trị và được kiểm tra ràng buộc với bộ lọc của người dùng. Không để người gọi dùng cursor của khách khác để bỏ qua kiểm soát quyền.

Keyset cải thiện tính ổn định theo thứ tự khóa, nhưng không tự tạo một snapshot bất biến của toàn bộ lịch sử trong lúc dữ liệu đang thay đổi. Nếu yêu cầu là “xuất báo cáo đúng một thời điểm”, bài toán cần thêm cơ chế snapshot hoặc mốc thời gian đọc nhất quán.

## 8. Truy vấn đúng cú pháp vẫn có thể trả kết quả sai nghiệp vụ

Có ít nhất bốn lớp đúng cần phân biệt:

**Đúng tập bản ghi.** Nếu bỏ **customerId**, danh sách có thể chứa đơn khách khác. Nếu lọc **shippingStatus = SHIPPED** thay cho **paymentStatus = PAID**, nghiệp vụ “đã thanh toán” bị hiểu sai.

**Đúng giá trị và lịch sử.** Nếu lấy **unitPrice** từ catalog hiện tại để dựng lại hóa đơn cũ, tổng tiền có thể thay đổi sau chương trình khuyến mãi. Snapshot giao dịch giúp bảo toàn ý nghĩa của số tiền đã thu.

**Đúng thứ tự và hình dạng phản hồi.** Không có thứ tự phá hòa, hai đơn cùng **createdAt** có thể đổi vị trí giữa những lần đọc. Trả toàn bộ items cho màn hình danh sách làm tăng dữ liệu truyền tải; dùng preview cho trang chi tiết lại làm thiếu dữ liệu.

**Đúng thời điểm người dùng quan sát.** Giả sử cổng thanh toán vừa thông báo thành công nhưng webhook cập nhật đơn chưa được xử lý. Truy vấn lọc **PAID** có thể chưa thấy đơn. Đây có thể là vấn đề **luồng cập nhật và độ mới dữ liệu**, không phải lỗi của câu lệnh **find**.

Với tình huống cuối, cần xác định rõ hợp đồng trải nghiệm:

- Nếu UI chỉ xác nhận “đã thanh toán” khi database đã ghi trạng thái phù hợp, có thể thiết kế đường ghi/đọc để người dùng đọc lại dữ liệu vừa được xác nhận theo yêu cầu nhất quán tương ứng.
- Nếu xử lý thanh toán bất đồng bộ, UI cần trạng thái “đang xác nhận”, cơ chế cập nhật tiến trình hoặc đối soát; không nên hiển thị thành công cuối cùng chỉ dựa trên một yêu cầu đang chờ.
- MongoDB có cơ chế lựa chọn **read concern**, **write concern**, read preference và transaction cho các nhu cầu nhất quán khác nhau. Phải chọn theo điều kiện triển khai và yêu cầu nghiệp vụ; không thể kết luận mọi truy vấn NoSQL đều là eventual consistency.

Khi cập nhật một đơn, tính nguyên tử trong một document hữu ích cho các trường của cùng đơn. Nếu giao dịch nghiệp vụ trải qua nhiều document hoặc hệ thống ngoài như cổng thanh toán, cần xử lý riêng ranh giới giao dịch, retry, idempotency và đối soát. Một request được gửi lại không được làm phát sinh hai lần ghi nhận thanh toán.

## 9. Từ truy vấn đến quan sát có bằng chứng

Một vòng kiểm tra đầy đủ không dừng ở việc “lệnh chạy thành công”. Ta cần đối chiếu từng lớp với một bằng chứng cụ thể.

| Lớp | Bằng chứng nên quan sát | Điều chưa thể kết luận chỉ từ bằng chứng đó |
|---|---|---|
| Dữ liệu đầu vào | Có các đơn c7/c9, PAID/PENDING và mốc thời gian như fixture | Dữ liệu sản xuất cũng phân bố giống fixture |
| Đúng nghiệp vụ | Kết quả gồm o105, o104, o102 theo thứ tự; không có o103/o106 | Các trường hợp biên trong hệ thống thật đều đúng |
| Đúng hình dạng | Danh sách o104 chỉ có 2 items; chi tiết o104 có 3 items | Truy vấn đã tối ưu về dung lượng trên tải lớn |
| Đúng quyền | Người dùng c9 không đọc được o104 qua API | Mọi endpoint khác đều đã kiểm soát quyền |
| Kế hoạch truy vấn | **explain** cho thấy các stage và số khóa/document duyệt | Độ trễ p95 dưới tải đồng thời chắc chắn đạt mục tiêu |
| Trải nghiệm cuối | Màn hình hiển thị đúng đơn, tiền, thứ tự và trạng thái cập nhật | Không còn vấn đề về retry, cache hay dữ liệu bất đồng bộ |

Sơ đồ tương quan giữa đầu vào, truy vấn và đầu ra có thể diễn tả như sau:

~~~text
Yêu cầu: "3 đơn đã thanh toán mới nhất của c7"
                     |
                     v
        {customerId: c7, paymentStatus: PAID}
                     |
               SORT + LIMIT 3
                     |
                     v
             [o105, o104, o102]
                     |
       +-------------+--------------+
       |                            |
       v                            v
  Danh sách:                  Mở đơn o104:
  2 items xem trước           3 items đầy đủ
       |                            |
       +-------------+--------------+
                     |
                     v
   Đối chiếu contract + quan sát kế hoạch/tải
~~~

Khi kết quả sai, hãy truy ngược theo thứ tự: quy tắc nghiệp vụ đã diễn giải đúng chưa; bộ lọc và quyền đúng chưa; dữ liệu đã được ghi chưa; projection/sort có làm mất thông tin không; sau cùng mới đến index và tối ưu hiệu năng. **Index có thể giúp truy vấn nhanh hơn, nhưng không sửa được một điều kiện lọc sai.**

## 10. Khi yêu cầu thay đổi, mô hình phải được đánh giá lại

Giả sử xuất hiện thêm yêu cầu:

> Mỗi sáng, quản trị viên cần xem doanh thu đã thanh toán theo ngày và 10 sản phẩm bán chạy nhất trong 30 ngày gần đây, với dữ liệu chậm tối đa 5 phút.

Đường đọc mới không bắt đầu bằng **customerId** và không chỉ lấy vài đơn mới nhất. Index phục vụ danh sách đơn theo khách hàng không mặc nhiên phù hợp với truy vấn tổng hợp doanh thu toàn hệ thống.

Lúc này cần đi lại đúng luồng ban đầu:

1. Xác định **định nghĩa doanh thu**: đếm thời điểm thanh toán hay thời điểm tạo đơn? Hoàn tiền và hủy đơn có được trừ? Múi giờ tính “một ngày” là gì?
2. Xác định **độ mới**: tối đa 5 phút trễ cho phép tạo bảng/document tổng hợp bất đồng bộ; còn nếu phải chính xác tức thì, phương án và chi phí sẽ khác.
3. Xác định **access pattern**: đọc tổng theo ngày và xếp hạng sản phẩm, không phải lấy đơn theo một khách.
4. Đánh giá lựa chọn: aggregation trên orders với index thích hợp và tải cho phép, hoặc tạo **read model/materialized view** lưu sẵn số liệu theo ngày và sản phẩm.
5. Định nghĩa **quy tắc cập nhật read model**: xử lý sự kiện trùng, cập nhật muộn, hoàn tiền, backfill và cách đối soát với đơn gốc.
6. Quan sát **sai lệch dữ liệu và độ trễ đồng bộ**, bên cạnh thời gian chạy truy vấn dashboard.

Một read model được tạo sẵn giúp thay đổi chi phí từ “tính lại khi mỗi người mở dashboard” sang “cập nhật số liệu khi có sự kiện”. Đổi lại, nó đưa vào bài toán đồng bộ và nhất quán của dữ liệu sao chép. Không nên thêm read model chỉ vì “NoSQL khuyến khích phi chuẩn hóa”; cần một truy vấn cụ thể và bằng chứng rằng lợi ích xứng đáng chi phí.

## 11. Tư duy này áp dụng thế nào với các loại NoSQL khác?

| Loại lưu trữ | Câu hỏi thiết kế thường đứng đầu | Minh họa với yêu cầu đơn hàng |
|---|---|---|
| Document database | Những trường nào thường được đọc/cập nhật cùng một aggregate? | Một document cho đơn và snapshot items |
| Key-value | Có thể lấy dữ liệu nhanh bằng khóa nào? Cần duy trì chỉ mục danh sách ở đâu? | Tra chi tiết bằng orderId rất tự nhiên; liệt kê theo khách cần thiết kế thêm cấu trúc truy cập |
| Wide-column | Partition key và clustering order nào phục vụ truy vấn với số partition cần đọc kiểm soát được? | Phân vùng đơn theo customerId, cân nhắc bucket thời gian cho khách có lịch sử rất lớn |
| Graph database | Có cần đi qua nhiều quan hệ và nhiều bước với độ sâu thay đổi? | Hữu ích hơn cho khám phá quan hệ khách–sản phẩm–giới thiệu; danh sách đơn theo thời gian chưa phải lý do đủ mạnh để dùng graph |

Không có một “mô hình NoSQL chuẩn” áp dụng cho mọi workload. Thao tác truy cập, tính nhất quán, độ tăng trưởng, khả năng phân vùng, cách dữ liệu thay đổi và vận hành cụ thể quyết định lựa chọn.

## 12. Bài tập tư duy: đi từ câu nói của người dùng đến bằng chứng

**Tình huống A.** Product đổi yêu cầu thành “hiển thị 3 đơn mới nhất, kể cả đơn chưa thanh toán; riêng đơn chưa thanh toán phải có nhãn cảnh báo”. Hãy chỉ ra phần nào trong filter cần thay đổi, trường nào cần trả thêm, index hiện tại có còn hợp lý không, và kết quả dự kiến từ sáu document mẫu sẽ là gì.

**Tình huống B.** Hai đơn của cùng khách có chính xác cùng **createdAt**. Hãy giải thích vì sao chỉ sắp xếp theo **createdAt** chưa đủ cho phân trang và viết điều kiện cursor cho thứ tự giảm dần theo cặp **(createdAt, _id)**.

**Tình huống C.** Mỗi đơn có thể chứa hàng trăm nghìn dòng hàng vì khách đặt sỉ. Hãy đánh giá lại ranh giới document, đường đọc chi tiết, phân trang items và cách giữ **orderTotal** đúng khi xử lý nhiều lần ghi.

Khi giải các tình huống, hãy trình bày cùng một chuỗi: **yêu cầu được làm rõ → hợp đồng truy cập → mô hình → truy vấn/index → kết quả dự kiến → tín hiệu kiểm chứng**. Đây chính là kỹ năng cốt lõi của tư duy NoSQL: nhìn thấy mối liên hệ giữa điều người dùng cần, dữ liệu ta lưu và điều hệ thống thực sự trả về.

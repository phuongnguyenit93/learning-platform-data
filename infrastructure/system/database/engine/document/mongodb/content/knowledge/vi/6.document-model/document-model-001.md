# Bắt đầu từ nhu cầu truy vấn, tần suất đọc ghi và vòng đời dữ liệu

## 1. Tư duy thiết kế mô hình document trong MongoDB

Khi chuyển sang MongoDB, một sai lầm thường gặp là liệt kê ngay các thực thể như Customer, Product, Order rồi chuyển từng thực thể thành một collection. Cách làm ấy có thể tạo được dữ liệu hợp lệ, nhưng chưa trả lời câu hỏi quan trọng nhất: **ứng dụng sẽ đọc và ghi dữ liệu đó như thế nào?**

MongoDB lưu dữ liệu dưới dạng document BSON. Một document có thể chứa trường đơn, object nhúng và mảng, vì vậy thiết kế không bắt buộc đi theo mô hình “mỗi thực thể một bảng” của cơ sở dữ liệu quan hệ. Việc quyết định **nhúng (embedding)** hay **tham chiếu (referencing)** cần bám theo các thao tác mà ứng dụng thực sự thực hiện:

- Màn hình nào được mở thường xuyên? Mỗi màn hình cần những trường dữ liệu nào?
- Truy vấn có cần lấy nhiều thành phần cùng lúc, theo điều kiện lọc và sắp xếp nào?
- Dữ liệu nào được cập nhật độc lập, dữ liệu nào luôn được ghi cùng nhau?
- Số lượng phần tử trong một mảng có bị giới hạn không? Dữ liệu sẽ tăng nhanh đến mức nào?
- Document tồn tại trong bao lâu? Khi nào được sửa, khóa, lưu trữ, ẩn, ẩn danh hoặc xóa?
- Thao tác nào cần nhất quán ngay lập tức và thao tác nào chấp nhận cập nhật trễ?

**Nguyên tắc nền tảng:** Thiết kế document theo **access patterns** (mẫu truy cập), **read/write workload** (tải đọc ghi) và **data lifecycle** (vòng đời dữ liệu), sau đó mới chốt collection, cấu trúc nhúng/tham chiếu và index.

Trong bài này, ta xây dựng một mô hình cho hệ thống đặt hàng trực tuyến quy mô vừa. Các số liệu tải là **giả định để luyện thiết kế**, không phải số liệu đo của một hệ thống thực tế. Mục tiêu là hiểu cách một yêu cầu sản phẩm được chuyển thành quyết định dữ liệu có thể giải thích và kiểm chứng.

## 2. Bắt đầu bằng các câu hỏi nghiệp vụ, không bắt đầu bằng collection

Giả sử hệ thống bán hàng có các chức năng:

1. Khách duyệt danh mục sản phẩm theo loại và giá.
2. Khách thêm, sửa, xóa món trong giỏ hàng.
3. Khách đặt hàng; hệ thống cần lưu giá và địa chỉ giao tại thời điểm đặt.
4. Khách xem chi tiết đơn và lịch sử đơn gần đây.
5. Nhân viên xử lý các đơn theo trạng thái pending, paid, shipped.
6. Hệ thống ghi nhận lịch sử chuyển trạng thái để phục vụ tra soát.
7. Giỏ hàng bỏ dở hoặc phiên thanh toán tạm có thể hết hạn; đơn đã thanh toán phải được giữ theo chính sách lưu trữ.

Không phải mọi nhu cầu đều được ưu tiên như nhau. Truy vấn danh mục có thể diễn ra hàng trăm lần mỗi giây; tải chi tiết đơn có thể ít hơn; ghi lịch sử trạng thái có thể hiếm nhưng cần chính xác. Quyết định tốt sẽ **tối ưu những đường truy cập quan trọng** đồng thời vẫn giữ đúng nghiệp vụ, thay vì cố giảm số collection bằng mọi giá.

### 2.1. Viết bảng access pattern trước

Một bảng access pattern cần ít nhất: **ai gọi**, **dữ liệu cần lấy**, **bộ lọc/sắp xếp**, **tần suất**, **đường ghi liên quan** và **yêu cầu nhất quán**.

| Mã | Nhu cầu và cách truy vấn | Tải giả định | Điểm cần chú ý |
| --- | --- | --- | --- |
| AP1 | Duyệt sản phẩm theo tenant, category, active; sắp xếp price | 80 lượt đọc/giây lúc cao điểm | Đọc nhiều, cần index; phân trang và chỉ trả trường cần hiển thị |
| AP2 | Xem chi tiết một đơn theo tenant và orderId | 30 lượt đọc/giây | Cần trả dòng hàng, giá, địa chỉ và trạng thái cùng nhau |
| AP3 | Danh sách đơn của khách theo tenant và customerId, mới nhất trước | 20 lượt đọc/giây | Cần index đúng bộ lọc + sort, phân trang ổn định |
| AP4 | Chỉnh sửa số lượng một món trong giỏ | 15 lượt ghi/giây | Một giỏ có thể được sửa nhiều lần; thao tác đơn document nên atomic |
| AP5 | Tạo đơn từ giỏ | 5 lượt ghi/giây | Cần ảnh chụp giá; xử lý tính tiền và tồn kho đúng quy tắc |
| AP6 | Nhân viên xem đơn trạng thái pending theo thời gian tạo | 10 lượt đọc/giây | Lọc status và sort ngày; cân nhắc index riêng |
| AP7 | Chuyển trạng thái đơn, ghi lịch sử thay đổi | 8 lượt ghi/giây | Cần bảo vệ chuyển trạng thái và lịch sử truy vết |
| AP8 | Xóa phiên thanh toán đã hết hạn | Chạy nền theo thời điểm hết hạn | Có thể dùng TTL; chấp nhận độ trễ dọn dẹp |

Các giá trị trên là **giá trị minh họa lúc cao điểm**, không phải cam kết hiệu năng. Chỉ số cụ thể phải được đo bằng log, metrics và kiểm thử tải. Ngoài số lượt/giây, nên thu thập **p95/p99 latency**, tỷ lệ lỗi, kích thước kết quả, số document quét và kiểu truy vấn theo thời gian.

### 2.2. Biểu diễn một truy vấn như hợp đồng dữ liệu

Chẳng hạn, AP3 có thể được mô tả như sau:

~~~yaml
accessPattern: AP3
actor: customer
intent: List recent orders
filter:
  tenantId: equality
  customerId: equality
sort:
  placedAt: descending
  _id: descending
pageSize: 20
fields:
  - orderNo
  - status
  - placedAt
  - total
peakReadRps: 20
consistency: read committed business state
~~~

Hợp đồng giúp trả lời nhiều câu hỏi thiết kế: phải có customerId trên document đơn hàng, cần trường placedAt, danh sách nên trả **bản tóm tắt của đơn** thay vì tải nguyên lịch sử trạng thái, và index có thể bắt đầu bằng tenantId, customerId trước khi tới thứ tự sort.

Thông thường nên viết khoảng 5–15 access pattern quan trọng nhất rồi xem mẫu nào chiếm phần lớn tải hoặc có yêu cầu độ trễ nghiêm ngặt. Các use case ít xảy ra vẫn cần hỗ trợ nhưng không nên buộc mọi lần đọc phổ biến phải trả giá vì chúng.

## 3. Phân tích tải đọc ghi để chọn ranh giới document

### 3.1. Cùng được đọc hay cập nhật độc lập?

Một đơn hàng thường hiển thị cùng các dữ liệu: trạng thái hiện tại, các dòng hàng, số lượng, giá lúc mua, tổng tiền và địa chỉ giao lúc đặt. Những trường đó là **một đơn vị đọc tự nhiên**, nên phù hợp nằm trong document Order khi kích thước được kiểm soát.

Trong khi đó:

- Giá sản phẩm được nhân viên cập nhật độc lập với các đơn cũ.
- Hồ sơ khách hàng được thay đổi độc lập với chi tiết đơn đã phát sinh.
- Lịch sử thay đổi trạng thái có thể tăng theo thời gian và cần lọc/truy xuất riêng.
- Giỏ hàng được cập nhật liên tục nhưng thường nhỏ và có vòng đời ngắn.

Nếu nhúng toàn bộ Product vào mỗi Order, thay đổi nội dung sản phẩm sẽ làm xuất hiện nhiều bản sao không nhất quán. Nếu chỉ tham chiếu Product mà không lưu giá thời điểm mua, đơn hàng cũ có thể bị thay đổi ý nghĩa khi giá sản phẩm đổi.

Giải pháp hợp lý ở đây là **kết hợp**:

- Order giữ **productId** để có thể truy ngược sản phẩm gốc.
- Mỗi line item của Order **nhúng tên hàng, SKU, số lượng và đơn giá tại thời điểm đặt** làm snapshot.
- Product tồn tại độc lập để phục vụ duyệt danh mục và cập nhật giá hiện tại.

Đây là quyết định dựa trên vòng đời của thông tin, không đơn thuần dựa vào quan hệ “Order có nhiều Product”.

### 3.2. Nhúng, tham chiếu hay kết hợp?

| Tiêu chí | Ưu tiên nhúng | Ưu tiên tham chiếu |
| --- | --- | --- |
| Cách đọc | Luôn được đọc cùng document cha | Thường được đọc/tìm riêng |
| Cách ghi | Thay đổi cùng cha, ít cạnh tranh ghi | Cập nhật thường xuyên và độc lập |
| Số lượng phần tử | Nhỏ hoặc có giới hạn rõ | Có thể tăng không giới hạn |
| Vòng đời | Cùng tồn tại và được xóa/giữ với cha | Vòng đời độc lập |
| Tính nhất quán | Muốn cập nhật atomic trong một document | Chấp nhận nhiều document hoặc cần transaction |
| Kích thước | Giữ đủ nhỏ, có ngân sách tăng trưởng | Sẽ lớn, tốn băng thông khi đọc cả cha |
| Ví dụ | Address snapshot, order line items có giới hạn, cấu hình ít mục | Product catalog, customer profile, order events dài hạn |

**Nhúng không có nghĩa là không được lập index trường nhúng.** MongoDB cho phép query/index theo đường dẫn trường con và mảng; tuy nhiên index trên mảng trở thành multikey index và cần xem xét kích thước, số lượng phần tử, khả năng kết hợp với sort.

**Tham chiếu cũng không đồng nghĩa với tự có khóa ngoại.** MongoDB không tự kiểm tra customerId hoặc productId tồn tại ở collection khác khi insert Order. Tầng ứng dụng phải quản lý tính nhất quán tham chiếu theo yêu cầu của nghiệp vụ.

### 3.3. Không nhúng mảng có khả năng tăng vô hạn

Ví dụ mô hình dễ gây vấn đề:

~~~javascript
{
  _id: "order-001",
  status: "shipped",
  events: [
    // Mỗi lần thay trạng thái hoặc thao tác hệ thống
    // lại append một phần tử vào cùng document.
  ]
}
~~~

Nếu một document liên tục tích lũy hàng nghìn, hàng triệu event, kích thước và chi phí cập nhật có thể tăng đáng kể. MongoDB có giới hạn **16 MiB cho một BSON document**. Với dữ liệu phát triển không giới hạn, không nên trông chờ mảng nhúng luôn chứa được tất cả.

Một phương án:

~~~text
orders
  _id
  customerId
  status                 <- trạng thái hiện tại phục vụ đọc nhanh
  items[]                <- số lượng có giới hạn theo quy tắc đặt hàng
  placedAt

order_events
  _id
  orderId                <- tham chiếu tới orders._id
  fromStatus
  toStatus
  occurredAt
  actorId
~~~

Khi cần xem lịch sử, truy vấn order_events theo orderId và thời gian. Khi tải chi tiết đơn bình thường, chỉ đọc orders. Với lịch sử không quá dài và có giới hạn cứng, vẫn có thể nhúng; điểm quyết định là **mức tăng trưởng và mẫu truy cập thực tế**, không phải sở thích mặc định.

### 3.4. Quan hệ một-nhiều cần đặt câu hỏi về cardinality

Trước khi nhúng mảng, hãy ước lượng:

1. Một document cha tối đa có bao nhiêu phần tử con ở thời điểm hiện tại?
2. Sau một năm hay năm năm, giới hạn đó có thay đổi không?
3. Có cần phân trang, lọc hoặc cập nhật một phần tử con độc lập không?
4. Nếu nhiều người cùng ghi vào document cha, có thể xuất hiện tranh chấp/hot document không?
5. Document có thể gần chạm giới hạn 16 MiB hoặc tạo quá nhiều index entry không?

**Giỏ hàng** thường là một mảng nhỏ và có chính sách giới hạn số món nên có thể nhúng items vào Cart. **Nhật ký sự kiện**, bình luận của một bài viết phổ biến hoặc lịch sử giao dịch nhiều năm thường thích hợp tách collection.

## 4. Vòng đời dữ liệu quyết định cách lưu

Thiết kế chỉ dựa vào truy vấn ngày hôm nay sẽ thiếu khi dữ liệu tăng trưởng hoặc thay đổi trạng thái. Cần xem dữ liệu từ lúc tạo tới lúc hết hiệu lực.

| Loại dữ liệu | Khi tạo | Khi hoạt động | Khi hết hiệu lực | Hàm ý thiết kế |
| --- | --- | --- | --- | --- |
| Product | Nhân viên thêm hàng | Sửa giá, tồn kho, mô tả | Ngừng bán, có thể lưu để tra cứu | Collection độc lập, có active; đơn cũ giữ snapshot |
| Customer | Đăng ký | Sửa tên, liên hệ, địa chỉ | Đóng tài khoản/ẩn danh theo chính sách | Không buộc đơn cũ phụ thuộc hồ sơ hiện tại |
| Order | Checkout thành công | Chuyển trạng thái, giao hàng | Hoàn tất/hủy và lưu theo chính sách | Document ổn định, snapshot giao dịch, có trạng thái hiện tại |
| Order event | Có thay đổi quan trọng | Chủ yếu append và truy vấn tra soát | Lưu trữ hoặc xóa theo chính sách audit | Collection sự kiện riêng nếu tăng dài hạn |
| Cart | Người dùng thêm món | Ghi thường xuyên, số món có giới hạn | Đặt hàng hoặc bị bỏ dở | Nhúng items, xác định cách hết hạn |
| Checkout session | Bắt đầu thanh toán | Kiểm tra trạng thái phiên | Hết thời gian sử dụng | TTL có thể phù hợp khi được phép xóa trễ |

### 4.1. Phân biệt trạng thái và lịch sử trạng thái

Order cần trạng thái hiện tại để trả lời nhanh “đơn này đang ở đâu?”. Nhật ký order_events trả lời “ai đã đổi từ trạng thái nào sang trạng thái nào và lúc nào?”. Hai câu hỏi có tần suất, vòng đời và yêu cầu kiểm soát khác nhau.

Một quy tắc chuyển trạng thái minh họa:

~~~text
pending --> paid --> shipped --> completed
    |         |
    +------> cancelled
~~~

Quy tắc thực tế có thể phức tạp hơn, ví dụ hoàn tiền hoặc giao lại. Vấn đề không phải vẽ đúng mọi trạng thái có thể có, mà là nhận diện **thay đổi có điều kiện** cần bảo vệ:

- Khi chuyển pending sang paid, thao tác ghi phải bảo đảm đơn vẫn đang ở pending.
- Nếu cần ghi event và cập nhật Order **cùng thành công hoặc cùng thất bại**, phải thiết kế transaction đa document trong môi trường MongoDB hỗ trợ, hoặc một cơ chế đáng tin cậy tương đương.
- Chỉ thực hiện update trên Order rồi hy vọng event được ghi sau không đáp ứng yêu cầu audit nguyên tử.

### 4.2. TTL chỉ dành cho dữ liệu thực sự được phép hết hạn

MongoDB có **TTL index** để tự động xóa document dựa trên trường thời gian. Đây là công cụ phù hợp cho một số loại phiên tạm, token hết hạn hoặc dữ liệu log có chính sách xóa. Ví dụ:

~~~javascript
const lab = db.getSiblingDB("mongo_access_lab");

lab.getCollection("lab_checkout_sessions").createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0, name: "ttl_checkout_expires_at" }
);

lab.getCollection("lab_checkout_sessions").insertOne({
  sessionId: "checkout-example-001",
  tenantId: "shop-01",
  expiresAt: new Date(Date.now() + 15 * 60 * 1000)
});
~~~

Với expireAfterSeconds bằng 0, document đến hạn khi **expiresAt** đã qua. TTL xóa bởi tiến trình nền, nên **không bảo đảm xóa chính xác ngay tại thời điểm hết hạn**. Ứng dụng vẫn phải kiểm tra expiresAt khi xác nhận phiên còn hiệu lực. TTL không thay thế kiểm tra quyền hoặc trạng thái thanh toán.

TTL thông thường được tạo trên **một trường ngày**. Document thiếu expiresAt hoặc lưu sai kiểu có thể không được dọn như mong muốn. Không áp dụng TTL cho các đơn hàng đã thanh toán chỉ vì chúng cũ: thời hạn lưu giao dịch, bảo hành, đối soát và pháp lý phải được quyết định trước.

### 4.3. Lưu trữ, ẩn danh và schema evolution

Vòng đời không luôn kết thúc bằng delete:

- Order có thể được đánh dấu archived và chuyển sang tầng lưu trữ phù hợp sau một thời gian theo chính sách.
- Dữ liệu cá nhân trong địa chỉ giao hàng có thể cần ẩn danh hoặc giảm bớt trường, trong khi một số thông tin giao dịch phải giữ.
- Product có thể chuyển active từ true sang false mà không xóa document gốc.
- Cấu trúc Order có thể tiến hóa từ **schemaVersion: 1** sang phiên bản mới; mã ứng dụng cần đọc được dữ liệu cũ hoặc có migration phù hợp.

Nếu đặt toàn bộ dữ liệu cá nhân của Customer vào mỗi đơn, xóa/ẩn danh khách hàng có thể trở nên khó kiểm soát. Khi snapshot thông tin giao hàng là cần thiết, phải xác định rõ trường nào được phép lưu, mục đích, thời hạn lưu và quy trình xóa/ẩn danh.

## 5. Mô hình đề xuất cho hệ thống đặt hàng

Từ bảng truy vấn và vòng đời, một thiết kế ban đầu có thể gồm:

~~~text
customers                 products
  _id                       _id
  tenantId                  tenantId
  displayName               category
  contact...                active
                             price

orders
  _id
  tenantId
  customerId ----------> customers._id
  orderNo
  placedAt, updatedAt
  status
  items[]                 <-- snapshot dòng hàng tại lúc đặt
    productId ----------> products._id
    sku
    title
    quantity
    unitPrice
  shippingAddressSnapshot
  total
  schemaVersion

order_events
  _id
  tenantId
  orderId -------------> orders._id
  fromStatus, toStatus, occurredAt

carts
  _id, tenantId, customerId, items[], updatedAt

checkout_sessions
  sessionId, tenantId, expiresAt
~~~

Các mũi tên thể hiện **tham chiếu logic bằng giá trị**, không phải ràng buộc khóa ngoại tự động. Trong ví dụ thực hành, các ID là chuỗi cố định để kết quả chạy lại dễ đọc. Khi đưa vào sản phẩm thật, có thể dùng ObjectId hoặc UUID nếu đáp ứng hợp đồng ID của hệ thống.

### 5.1. Document Order chứa dữ liệu phục vụ màn hình chi tiết

~~~javascript
{
  _id: "o001",
  dataset: "access-pattern-v1",
  tenantId: "shop-01",
  customerId: "c001",
  orderNo: "SO-2026-001",
  placedAt: ISODate("2026-02-01T09:00:00.000Z"),
  updatedAt: ISODate("2026-02-01T09:15:00.000Z"),
  status: "paid",
  items: [
    {
      productId: "p001",
      sku: "BOOK-A5",
      title: "Sổ tay A5",
      quantity: NumberInt(2),
      unitPrice: NumberDecimal("40000.00")
    },
    {
      productId: "p002",
      sku: "PEN-BLUE",
      title: "Bút xanh",
      quantity: NumberInt(1),
      unitPrice: NumberDecimal("10000.00")
    }
  ],
  shippingAddressSnapshot: {
    city: "Hà Nội",
    district: "Cầu Giấy"
  },
  total: NumberDecimal("90000.00"),
  schemaVersion: NumberInt(1)
}
~~~

Màn hình xem chi tiết đơn không cần gọi từng document Product để lấy tên hàng và đơn giá. Các trường **title/sku/unitPrice** là snapshot tại thời điểm mua, vì giá và tên hiện tại của Product có thể đã thay đổi. Nếu cần hiển thị tồn kho hiện tại, đó là dữ liệu khác và có thể phải truy vấn Product riêng.

Document này **không** nhúng toàn bộ lịch sử sự kiện theo thời gian; order_events lưu riêng. Trạng thái hiện tại nằm ngay trên Order để phục vụ các màn hình thường xuyên.

### 5.2. Ràng buộc dữ liệu không biến mất khi dùng document

Thiết kế vẫn phải nêu quy tắc:

1. tenantId có trên tất cả document cần cách ly theo tenant.
2. customerId và productId cùng kiểu với _id của collection đích.
3. Order.items có ít nhất một món, số lượng dương và có giới hạn theo nghiệp vụ.
4. UnitPrice và total dùng kiểu thập phân có chủ đích; total phải khớp quy tắc tính giá (bao gồm thuế, giảm giá, phí vận chuyển nếu có).
5. OrderNo duy nhất theo tenant.
6. Trạng thái phải tuân thủ các chuyển đổi hợp lệ.
7. Đơn đã xác nhận giữ snapshot giao dịch dù Product hoặc Customer thay đổi.

MongoDB hỗ trợ **schema validation** để bắt một số lỗi hình dạng/kiểu dữ liệu, nhưng vẫn cần kiểm tra logic nghiệp vụ ở tầng ứng dụng. Một index chỉ giải quyết tính duy nhất cho các khóa được index; nó không tự kiểm soát mọi quan hệ hoặc quy tắc tính tiền.

## 6. Dựng dữ liệu mẫu có thể chạy lại trong mongosh

Để thử các access pattern, có thể tạo một bộ dữ liệu nhỏ và cố định. Script dưới đây chỉ dùng database **mongo_access_lab**, collection có tiền tố **lab_**, và document mang **dataset: "access-pattern-v1"**. Chạy trong môi trường lab riêng:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_access_lab");
  const tag = "access-pattern-v1";

  const customers = lab.getCollection("lab_customers");
  const products = lab.getCollection("lab_products");
  const orders = lab.getCollection("lab_orders");
  const events = lab.getCollection("lab_order_events");
  const carts = lab.getCollection("lab_carts");

  // Đưa dữ liệu của bài về trạng thái ban đầu.
  events.deleteMany({ dataset: tag });
  orders.deleteMany({ dataset: tag });
  carts.deleteMany({ dataset: tag });
  products.deleteMany({ dataset: tag });
  customers.deleteMany({ dataset: tag });

  customers.insertMany([
    {
      _id: "c001", dataset: tag, tenantId: "shop-01",
      displayName: "Khách A", city: "Hà Nội"
    },
    {
      _id: "c002", dataset: tag, tenantId: "shop-01",
      displayName: "Khách B", city: "Đà Nẵng"
    }
  ]);

  products.insertMany([
    {
      _id: "p001", dataset: tag, tenantId: "shop-01",
      sku: "BOOK-A5", title: "Sổ tay A5",
      category: "stationery", active: true,
      price: NumberDecimal("40000.00")
    },
    {
      _id: "p002", dataset: tag, tenantId: "shop-01",
      sku: "PEN-BLUE", title: "Bút xanh",
      category: "stationery", active: true,
      price: NumberDecimal("10000.00")
    },
    {
      _id: "p003", dataset: tag, tenantId: "shop-01",
      sku: "CUP-WHITE", title: "Ly sứ",
      category: "accessory", active: true,
      price: NumberDecimal("120000.00")
    }
  ]);

  orders.insertMany([
    {
      _id: "o001", dataset: tag, tenantId: "shop-01",
      customerId: "c001", orderNo: "SO-2026-001",
      placedAt: ISODate("2026-02-01T09:00:00.000Z"),
      updatedAt: ISODate("2026-02-01T09:15:00.000Z"),
      status: "paid",
      items: [
        {
          productId: "p001", sku: "BOOK-A5", title: "Sổ tay A5",
          quantity: NumberInt(2), unitPrice: NumberDecimal("40000.00")
        },
        {
          productId: "p002", sku: "PEN-BLUE", title: "Bút xanh",
          quantity: NumberInt(1), unitPrice: NumberDecimal("10000.00")
        }
      ],
      shippingAddressSnapshot: { city: "Hà Nội", district: "Cầu Giấy" },
      total: NumberDecimal("90000.00"),
      schemaVersion: NumberInt(1)
    },
    {
      _id: "o002", dataset: tag, tenantId: "shop-01",
      customerId: "c001", orderNo: "SO-2026-002",
      placedAt: ISODate("2026-02-02T10:00:00.000Z"),
      updatedAt: ISODate("2026-02-02T10:00:00.000Z"),
      status: "pending",
      items: [
        {
          productId: "p003", sku: "CUP-WHITE", title: "Ly sứ",
          quantity: NumberInt(1), unitPrice: NumberDecimal("120000.00")
        }
      ],
      shippingAddressSnapshot: { city: "Hà Nội", district: "Cầu Giấy" },
      total: NumberDecimal("120000.00"),
      schemaVersion: NumberInt(1)
    },
    {
      _id: "o003", dataset: tag, tenantId: "shop-01",
      customerId: "c002", orderNo: "SO-2026-003",
      placedAt: ISODate("2026-02-03T08:00:00.000Z"),
      updatedAt: ISODate("2026-02-04T09:00:00.000Z"),
      status: "shipped",
      items: [
        {
          productId: "p002", sku: "PEN-BLUE", title: "Bút xanh",
          quantity: NumberInt(3), unitPrice: NumberDecimal("10000.00")
        }
      ],
      shippingAddressSnapshot: { city: "Đà Nẵng", district: "Hải Châu" },
      total: NumberDecimal("30000.00"),
      schemaVersion: NumberInt(1)
    }
  ]);

  events.insertMany([
    {
      _id: "e001", dataset: tag, tenantId: "shop-01",
      orderId: "o001", fromStatus: null, toStatus: "pending",
      occurredAt: ISODate("2026-02-01T09:00:00.000Z")
    },
    {
      _id: "e002", dataset: tag, tenantId: "shop-01",
      orderId: "o001", fromStatus: "pending", toStatus: "paid",
      occurredAt: ISODate("2026-02-01T09:15:00.000Z")
    },
    {
      _id: "e003", dataset: tag, tenantId: "shop-01",
      orderId: "o002", fromStatus: null, toStatus: "pending",
      occurredAt: ISODate("2026-02-02T10:00:00.000Z")
    },
    {
      _id: "e004", dataset: tag, tenantId: "shop-01",
      orderId: "o003", fromStatus: null, toStatus: "paid",
      occurredAt: ISODate("2026-02-03T08:00:00.000Z")
    },
    {
      _id: "e005", dataset: tag, tenantId: "shop-01",
      orderId: "o003", fromStatus: "paid", toStatus: "shipped",
      occurredAt: ISODate("2026-02-04T09:00:00.000Z")
    }
  ]);

  carts.insertOne({
    _id: "cart-c001", dataset: tag, tenantId: "shop-01",
    customerId: "c001",
    items: [
      { productId: "p001", quantity: NumberInt(1) }
    ],
    updatedAt: ISODate("2026-02-03T12:00:00.000Z")
  });

  // Các index xuất phát từ mẫu đọc và quy tắc nghiệp vụ.
  orders.createIndex(
    { tenantId: 1, customerId: 1, placedAt: -1, _id: -1 },
    { name: "ix_order_customer_history" }
  );
  orders.createIndex(
    { tenantId: 1, status: 1, placedAt: -1 },
    { name: "ix_order_status_queue" }
  );
  orders.createIndex(
    { tenantId: 1, orderNo: 1 },
    { name: "ux_order_number_per_tenant", unique: true }
  );
  products.createIndex(
    { tenantId: 1, category: 1, active: 1, price: 1 },
    { name: "ix_catalog_category_price" }
  );
  events.createIndex(
    { tenantId: 1, orderId: 1, occurredAt: 1, _id: 1 },
    { name: "ix_order_event_timeline" }
  );
  carts.createIndex(
    { tenantId: 1, customerId: 1 },
    { name: "ux_cart_customer", unique: true }
  );

  printjson({
    customers: customers.countDocuments({ dataset: tag }),
    products: products.countDocuments({ dataset: tag }),
    orders: orders.countDocuments({ dataset: tag }),
    events: events.countDocuments({ dataset: tag }),
    carts: carts.countDocuments({ dataset: tag })
  });
})();
~~~

**Kết quả mong đợi:** 2 customers, 3 products, 3 orders, 5 events, 1 cart. Chạy lại toàn bộ khối đưa dữ liệu của bài về trạng thái logic ban đầu. Các ID và thời điểm được cố định để kết quả dễ đối chiếu. Script này dọn rồi chèn theo nhiều lệnh riêng, không phải transaction; chỉ dùng trong database thực hành riêng.

## 7. Biến access pattern thành query và index

Index có chi phí lưu trữ và chi phí cập nhật mỗi khi ghi. Vì vậy, mỗi index nên gắn với một hoặc nhiều truy vấn quan trọng. Bảng sau ánh xạ những access pattern ở mục 2 vào cấu trúc vừa tạo:

| Access pattern | Query chính | Index đáng cân nhắc |
| --- | --- | --- |
| AP1 – duyệt catalog | tenantId, category, active; sort price | tenantId + category + active + price |
| AP2 – chi tiết đơn | _id và tenantId | Index mặc định _id; kèm tenantId trong filter để bảo vệ phạm vi |
| AP3 – lịch sử đơn khách | tenantId, customerId; sort placedAt và _id giảm dần | tenantId + customerId + placedAt DESC + _id DESC |
| AP6 – hàng chờ xử lý | tenantId, status; sort placedAt giảm dần | tenantId + status + placedAt DESC |
| Lịch sử trạng thái | tenantId, orderId; sort occurredAt tăng dần | tenantId + orderId + occurredAt ASC + _id ASC |
| Tìm giỏ của khách | tenantId, customerId | Unique index trên cặp tenantId, customerId nếu mỗi khách chỉ có một giỏ hoạt động |

### 7.1. AP1: duyệt sản phẩm

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_access_lab");
  printjson(
    lab.getCollection("lab_products")
      .find(
        {
          dataset: "access-pattern-v1",
          tenantId: "shop-01",
          category: "stationery",
          active: true
        },
        { _id: 1, sku: 1, title: 1, price: 1 }
      )
      .sort({ price: 1 })
      .limit(20)
      .toArray()
  );
})();
~~~

Kết quả có p002 (10.000 VND) rồi p001 (40.000 VND). Phép chiếu chỉ lấy các trường phục vụ thẻ sản phẩm; không tải mọi thông tin nếu màn hình không cần.

### 7.2. AP2: chi tiết đơn

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_access_lab");
  printjson(lab.getCollection("lab_orders").findOne({
    _id: "o001",
    tenantId: "shop-01",
    dataset: "access-pattern-v1"
  }));
})();
~~~

Kết quả trả về dòng hàng và giá snapshot cùng trạng thái hiện tại của o001. Sử dụng đúng _id giúp định vị document, nhưng vẫn cần kiểm tra tenantId/ownership từ ngữ cảnh xác thực. Việc khách đoán được một ID không đồng nghĩa họ có quyền truy cập đơn.

### 7.3. AP3: danh sách đơn của khách

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_access_lab");
  printjson(
    lab.getCollection("lab_orders")
      .find(
        {
          dataset: "access-pattern-v1",
          tenantId: "shop-01",
          customerId: "c001"
        },
        { _id: 1, orderNo: 1, status: 1, placedAt: 1, total: 1 }
      )
      .sort({ placedAt: -1, _id: -1 })
      .limit(20)
      .toArray()
  );
})();
~~~

Kết quả theo thứ tự **o002 rồi o001**. Khi dữ liệu lớn, dùng phân trang bằng **cursor** dựa trên cặp (placedAt, _id) để tránh chi phí bỏ qua một lượng lớn document với skip. Với sort giảm dần, trang kế tiếp lấy các bản ghi có placedAt nhỏ hơn cursor, hoặc cùng placedAt nhưng _id nhỏ hơn cursor:

~~~javascript
// Giá trị cursor minh họa lấy từ item cuối của trang trước.
const cursorDate = ISODate("2026-02-02T10:00:00.000Z");
const cursorId = "o002";
const lab = db.getSiblingDB("mongo_access_lab");

lab.getCollection("lab_orders")
  .find({
    dataset: "access-pattern-v1",
    tenantId: "shop-01",
    customerId: "c001",
    $or: [
      { placedAt: { $lt: cursorDate } },
      { placedAt: cursorDate, _id: { $lt: cursorId } }
    ]
  })
  .sort({ placedAt: -1, _id: -1 })
  .limit(20)
  .toArray();
~~~

Kết quả lúc này chỉ còn **o001**. Khi xây API thực tế, cursor cần gắn với bộ lọc đã xác thực và có quy ước mã hóa/giải mã rõ ràng; cách phân trang này không tự tạo snapshot tuyệt đối nếu dữ liệu liên tục được thêm hoặc sửa.

### 7.4. AP6: hàng chờ đơn pending

~~~javascript
db.getSiblingDB("mongo_access_lab")
  .getCollection("lab_orders")
  .find(
    {
      dataset: "access-pattern-v1",
      tenantId: "shop-01",
      status: "pending"
    },
    { _id: 1, orderNo: 1, placedAt: 1, status: 1 }
  )
  .sort({ placedAt: -1 })
  .toArray();
~~~

Kết quả minh họa là o002. Vì status nằm ngay trên Order, màn hình danh sách không cần đọc toàn bộ order_events để suy ra trạng thái cuối.

### 7.5. Xem lịch sử trạng thái của một đơn

~~~javascript
db.getSiblingDB("mongo_access_lab")
  .getCollection("lab_order_events")
  .find(
    {
      dataset: "access-pattern-v1",
      tenantId: "shop-01",
      orderId: "o001"
    },
    { orderId: 1, fromStatus: 1, toStatus: 1, occurredAt: 1 }
  )
  .sort({ occurredAt: 1, _id: 1 })
  .toArray();
~~~

Kết quả có hai event của o001: tạo đơn pending rồi chuyển paid. Đây là truy vấn tương đối ít gặp hơn thao tác xem chi tiết đơn nên không cần nhúng toàn bộ timeline vào mỗi lần trả Order.

### 7.6. Đọc explain để kiểm tra thiết kế index

~~~javascript
db.getSiblingDB("mongo_access_lab")
  .getCollection("lab_orders")
  .find({
    tenantId: "shop-01",
    customerId: "c001"
  })
  .sort({ placedAt: -1, _id: -1 })
  .explain("executionStats");
~~~

Khi đọc kết quả, quan sát **winningPlan**, **totalKeysExamined**, **totalDocsExamined** và **nReturned**. Bộ dữ liệu chỉ có ba đơn rất nhỏ, MongoDB có thể chọn collection scan; điều đó không tự chứng minh index sai. Cần xem **dữ liệu có quy mô đại diện** và các phép đo latency/tài nguyên trước khi kết luận. Khi thêm index mới, cũng phải kiểm tra tác động lên tốc độ ghi và dung lượng index.

## 8. Tần suất ghi ảnh hưởng đến cách cập nhật

### 8.1. Giỏ hàng: nhiều lần ghi trên một document nhỏ

Giỏ hàng có ít món, thường được truy xuất theo customerId và cập nhật từng món. Nhúng items giúp thao tác đơn document atomic.

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_access_lab");
  const result = lab.getCollection("lab_carts").updateOne(
    {
      _id: "cart-c001",
      tenantId: "shop-01",
      dataset: "access-pattern-v1",
      "items.productId": "p001"
    },
    {
      $inc: { "items.$.quantity": 1 },
      $currentDate: { updatedAt: true }
    }
  );
  printjson({ matched: result.matchedCount, modified: result.modifiedCount });
})();
~~~

Mỗi lần chạy tăng quantity của p001 thêm một. Toàn bộ update này thực hiện trên **một document** nên atomic ở phạm vi document đó. Nếu hai client đồng thời sửa cùng cart, ứng dụng vẫn cần quy tắc xử lý xung đột phù hợp; thao tác tăng nguyên tử khác với ghi đè toàn bộ mảng items từ trạng thái cũ của client.

Việc thêm món mới, gộp hai dòng hàng trùng productId và giới hạn tổng số món cũng cần thiết kế để tránh nhân đôi hoặc vượt chính sách giỏ hàng. Khi cart trở thành đơn, phải xác nhận lại giá, tồn kho, khuyến mãi và trạng thái sản phẩm theo quy trình checkout; không tin hoàn toàn giá do client gửi.

### 8.2. Cập nhật trạng thái có điều kiện

Để tránh hai nhân viên chuyển trạng thái trên dữ liệu đã thay đổi, cập nhật trạng thái có thể dùng điều kiện trạng thái cũ:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_access_lab");
  const result = lab.getCollection("lab_orders").updateOne(
    {
      _id: "o002",
      tenantId: "shop-01",
      dataset: "access-pattern-v1",
      status: "pending"
    },
    {
      $set: {
        status: "paid",
        updatedAt: ISODate("2026-02-02T10:05:00.000Z")
      }
    }
  );
  printjson({ matched: result.matchedCount, modified: result.modifiedCount });
})();
~~~

Lần chạy đầu, matchedCount thường là 1; lần chạy tiếp sẽ là 0 vì status không còn pending. Đây là một hình thức **compare-and-set** trên một document. Kết quả không tự ghi sự kiện audit. Nếu một yêu cầu buộc cập nhật Order và thêm document OrderEvent cùng thành công/thất bại, cần dùng **multi-document transaction** trên triển khai MongoDB có hỗ trợ hoặc cơ chế đảm bảo phát sự kiện đáng tin cậy được thiết kế riêng (ví dụ outbox). Không nên tuyên bố nhất quán tuyệt đối khi mới thực hiện hai lệnh ghi độc lập.

### 8.3. Read-heavy và write-heavy đánh đổi khác nhau

**Đường đọc nhiều:** Có thể đáng để giữ dữ liệu thường dùng cùng một document, có index và projection phù hợp, hoặc tạo một biểu diễn tổng hợp phục vụ đọc nếu có chiến lược cập nhật rõ ràng.

**Đường ghi nhiều:** Nhiều bản sao cùng một giá trị sẽ làm thao tác đồng bộ đắt hơn. Document được nhiều tác vụ cùng chỉnh sửa có thể trở thành điểm tranh chấp. Nhiều index cũng làm tăng chi phí ghi vì MongoDB phải duy trì cấu trúc index.

Chẳng hạn, thêm trường **customerDisplayName** vào mọi đơn giúp màn hình danh sách tránh lookup, nhưng khi khách đổi tên, hệ thống phải quyết định: tên trong đơn là snapshot không đổi hay thông tin hiện tại cần được đồng bộ? Hai ý nghĩa đó khác nhau, không thể coi việc nhân bản dữ liệu là tối ưu vô điều kiện.

## 9. Ước lượng tăng trưởng và chi phí vận hành

Một mô hình tốt ở 10.000 document có thể trở nên khó vận hành ở hàng trăm triệu document. Trước khi chốt việc nhúng hay tham chiếu, hãy ước lượng:

~~~text
Số document mới/ngày
  = tốc độ tạo trung bình (document/giây) × 86.400

Dung lượng dữ liệu thô/ngày
  ≈ số document mới/ngày × kích thước BSON trung bình

Dung lượng vận hành thực tế
  = dữ liệu + index + overhead lưu trữ
    + chi phí replication, backup, snapshot, log...
~~~

Ví dụ giả định hệ thống **duy trì trung bình 5 đơn/giây cả ngày**, mỗi Order có kích thước BSON trung bình 2 KiB:

- Số đơn/ngày: **432.000**.
- Dung lượng BSON thô của Order/ngày: **khoảng 844 MiB**.
- Trong 30 ngày: **khoảng 24,7 GiB BSON thô**, chưa tính index, order_events, replication, backup và các thành phần khác.

Con số 5 đơn/giây ở đây là **trung bình liên tục**, không phải giá trị peakRps của bảng minh họa. Không lấy một đỉnh lưu lượng ngắn rồi nhân nguyên cả ngày mà không nói rõ giả định.

Nếu mỗi order sinh nhiều event hơn dự tính, collection order_events có thể tăng nhanh hơn orders. Nếu giỏ hàng chỉ tồn tại vài ngày, thời gian lưu khác nhau sẽ tạo ra độ lớn collection khác nhau. Vì vậy, nên ước lượng **tốc độ sinh**, **kích thước trung bình**, **mức tăng theo thời gian**, **chính sách giữ** và **dung lượng index** cho từng collection.

### 9.1. Khi kích thước buộc đổi mô hình

- Nếu một Order được phép có hàng chục nghìn items, cần đặt lại quy tắc giới hạn đơn hoặc tách cấu trúc, tránh tiếp cận 16 MiB/document.
- Nếu một Product có hàng triệu bình luận, không nhúng toàn bộ bình luận vào Product.
- Nếu thao tác cập nhật cùng một document quá thường xuyên, cân nhắc chia ranh giới ghi hoặc thiết kế aggregate khác.
- Nếu dữ liệu được giữ nhiều năm nhưng chỉ 30 ngày gần đây có truy vấn trực tuyến, có thể tách chiến lược lưu trữ **nóng/lạnh** với quy tắc đồng bộ và truy xuất rõ ràng.

### 9.2. Sharding là một quyết định tiếp theo, không phải cách sửa mô hình thiếu phù hợp

Khi tăng quy mô, cần xem shard key theo **phân bố tải**, **truy vấn có điều kiện shard key**, **tốc độ tăng dữ liệu** và **tính duy nhất**. Nếu mọi truy vấn chính đều lọc theo tenantId, trường này có thể đóng vai trò quan trọng trong đánh giá shard key, nhưng tenant lớn bất thường có thể tạo mất cân bằng. Không chọn shard key chỉ vì đã có trường tenantId trong mọi document.

Nhúng một mảng vô hạn hoặc tạo index sai không trở thành đúng chỉ nhờ sharding. Phải kiểm soát kích thước và đường truy cập trước, rồi mới chọn phương án phân phối dữ liệu theo số liệu tải thực tế.

## 10. Quy trình thiết kế từ workload đến collection

Có thể áp dụng quy trình dưới đây cho một miền nghiệp vụ khác:

**Bước 1 — Ghi access pattern quan trọng.** Với mỗi màn hình, API hoặc tác vụ nền, ghi actor, bộ lọc, sort, projection, page size, tần suất, độ trễ mong muốn. Phân biệt truy vấn tương tác và báo cáo chạy nền.

**Bước 2 — Lập write pattern.** Xác định đối tượng nào được tạo/sửa/xóa thường xuyên, các trường được cập nhật cùng nhau, có concurrent writers hay không và có cần điều kiện phiên bản hoặc trạng thái cũ.

**Bước 3 — Vẽ vòng đời.** Xác định lúc tạo, các trạng thái, giới hạn tăng trưởng, thời hạn giữ, dữ liệu nào cần audit, có yêu cầu ẩn danh/xóa hay lưu trữ không.

**Bước 4 — Chọn ranh giới document.** Đặt dữ liệu được đọc và cập nhật cùng nhau trong một document nếu kích thước và concurrency cho phép; tách dữ liệu độc lập, tăng vô hạn hoặc có vòng đời riêng. Có thể kết hợp snapshot nhúng với tham chiếu tới nguồn.

**Bước 5 — Chốt tính đúng đắn.** Định nghĩa ID, kiểu BSON, validation, unique constraint, transaction boundary, chính sách cập nhật và tính nhất quán giữa dữ liệu được nhân bản.

**Bước 6 — Thiết kế index theo query.** Bắt đầu bằng bộ lọc equality, các điều kiện range/sort theo mẫu thực tế, rồi xác minh qua explain. Tránh lập index cho từng trường chỉ vì nó tồn tại trong schema.

**Bước 7 — Ước lượng tăng trưởng.** Kiểm tra kích thước document, giới hạn mảng, số sự kiện, chi phí index, retention và bản sao dữ liệu. Nêu giả định về trung bình và đỉnh lưu lượng.

**Bước 8 — Đo và điều chỉnh.** Dùng dữ liệu gần với production để đo p95/p99, nReturned, totalDocsExamined, write latency, index size, số lần xung đột. Sửa mô hình hoặc index khi có bằng chứng, đồng thời giữ kế hoạch migration cho dữ liệu cũ.

Không cần tối ưu mọi trường hợp hiếm xảy ra bằng cách tạo một document khổng lồ. Điều quan trọng là biết **query nào được ưu tiên, quyết định nào có chi phí khi viết và thay đổi nào có thể xảy ra trong vòng đời dữ liệu**.

## 11. Những lỗi mô hình hóa thường gặp

| Biểu hiện | Nguyên nhân sâu hơn | Cách tiếp cận |
| --- | --- | --- |
| Tạo collection chỉ bằng cách chuyển từng entity/bảng quan hệ | Chưa khảo sát access pattern | Ghi query và các trường được đọc/ghi cùng nhau trước |
| Nhúng tất cả thông tin liên quan vào một document | Chỉ tối ưu số lần đọc hiện tại | Ước lượng kích thước, tần suất cập nhật và vòng đời con |
| Lưu mọi event vào mảng của Order | Không dự trù tăng trưởng vô hạn | Tách event collection và giữ status hiện tại trên Order |
| Chỉ lưu productId trong order, không lưu giá lúc đặt | Không phân biệt dữ liệu hiện tại với snapshot lịch sử | Nhúng unitPrice, title và dữ liệu giao dịch cần đóng băng |
| Sao chép tên khách vào mọi đơn nhưng không quyết định semantics | Dữ liệu nhân bản thiếu quy tắc cập nhật | Chọn snapshot bất biến hoặc dữ liệu hiện tại với quy trình đồng bộ |
| Index mọi trường | Không đo chi phí ghi và dung lượng | Gắn index với truy vấn cụ thể, kiểm tra explain |
| Dùng skip rất sâu cho trang lịch sử | Chưa cân nhắc tăng trưởng | Dùng cursor theo khóa sort ổn định khi phù hợp |
| Dùng TTL cho đơn hàng có nghĩa vụ lưu | Chỉ nhìn nhu cầu dọn dữ liệu | Phân loại retention, archive, anonymization, purge |
| Ghi Order rồi ghi Event và mặc định cả hai luôn nhất quán | Bỏ qua ranh giới transaction | Thiết kế transaction hoặc cơ chế outbox phù hợp |
| Đặt shard key theo cảm tính | Thiếu thông tin về tải, phân bố tenant và query | Đo traffic, hot keys, phân bố dữ liệu và tính duy nhất |

## 12. Bài tập vận dụng

### Bài 1 — Thiết kế mạng xã hội nhỏ

Một bài đăng có thể có hàng triệu lượt xem, hàng chục nghìn bình luận, tác giả thỉnh thoảng sửa nội dung, và phần bình luận cần phân trang theo thời gian. Hãy lập access pattern cho xem bài đăng, thêm bình luận, đọc 20 bình luận mới nhất và đếm bình luận. Chọn trường nào nên nhúng vào Post, trường nào thuộc Comments, và cách duy trì commentCount nếu cần hiển thị nhanh.

**Gợi ý:** Bình luận tăng không giới hạn và có đường đọc riêng; không nên mặc định nhúng toàn bộ vào Post. Số lượng bình luận lưu trên Post là dữ liệu tổng hợp, cần chiến lược đồng bộ/đối soát.

### Bài 2 — Hệ thống học trực tuyến

Một khóa học có metadata ít đổi, nhiều bài học, và mỗi học viên sinh tiến độ học tập độc lập. Hãy xét truy vấn: xem danh sách bài học, mở bài chi tiết, đánh dấu hoàn thành và tải tiến độ học viên. Nếu mỗi khóa có hàng nghìn bài, bạn chọn cách lưu Lessons và LearnerProgress như thế nào? Những trường nào có thể là snapshot và trường nào không nên đặt chung document?

**Gợi ý:** Tách vòng đời của nội dung khóa học với vòng đời tiến độ riêng theo từng học viên; cân nhắc kích thước danh sách bài và yêu cầu phân trang.

### Bài 3 — Phân tích tải và tăng trưởng

Giả sử hệ thống tạo trung bình 20 order/giây, mỗi order phát sinh trung bình 4 event; Order trung bình 1,5 KiB, Event trung bình 0,5 KiB. Hãy ước lượng số document và dung lượng BSON thô trong một ngày, sau đó liệt kê các thành phần cần bổ sung để ước tính dung lượng vận hành. Điều gì sẽ xảy ra nếu lưu toàn bộ event vào mảng Orders và số event tăng theo thời gian?

### Bài 4 — Thay đổi mô hình khi có yêu cầu mới

Từ dữ liệu mẫu của bài, bổ sung yêu cầu hiển thị “10 sản phẩm bán chạy nhất trong 30 ngày” mỗi phút. Hãy viết access pattern, chỉ ra dữ liệu nguồn (Order.items), trạng thái đơn nào được tính, và đề xuất so sánh **aggregation trực tiếp** với **collection tổng hợp**. Nếu tạo collection tổng hợp, mô tả cách phát hiện dữ liệu chậm hoặc thiếu và đối soát lại.

### Bài 5 — Chọn chiến lược hết hạn

Phân loại session đăng nhập, giỏ hàng bỏ dở, đơn đã thanh toán, dữ liệu audit và file export tạm theo nhu cầu TTL, archive, anonymize hoặc delete. Với từng loại, nêu thời hạn theo một chính sách giả định và lý do. Giải thích tại sao TTL index không phải công cụ bảo đảm session bị từ chối ngay khi thời gian hết hạn.

### Bài 6 — Đọc tải trước khi thêm index

Hãy viết truy vấn xem 20 đơn gần nhất của khách c001 và xem toàn bộ event của o001 trong dữ liệu mẫu. Liên hệ từng truy vấn với index đã tạo, dùng explain("executionStats") để quan sát kế hoạch. Nếu thêm một index mới, hãy nêu truy vấn nào cần nó và chi phí ghi nào phải chấp nhận.

### Bài 7 — Kiểm soát ghi đồng thời

Hai tác vụ cùng cố đổi o002 từ pending sang paid. Sử dụng bộ lọc trạng thái cũ để chỉ một thao tác hợp lệ có thể chuyển trạng thái. Sau đó giải thích vì sao cần thêm giải pháp nhất quán nếu mỗi lần chuyển trạng thái phải ghi một OrderEvent duy nhất trong collection khác.

---

Khi thiết kế MongoDB, hãy giữ thứ tự suy nghĩ: **nhu cầu truy vấn → tải đọc ghi → vòng đời và tăng trưởng → ranh giới document → index và quy tắc nhất quán → đo đạc thực tế**. Cùng một quan hệ nghiệp vụ có thể nên nhúng, tham chiếu hoặc kết hợp tùy cách dữ liệu được sử dụng. Chất lượng của mô hình không nằm ở số collection ít hay nhiều, mà ở việc mô hình đó đáp ứng đúng các thao tác quan trọng và vẫn hoạt động ổn định khi dữ liệu thay đổi theo thời gian.

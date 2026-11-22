# Quyền sở hữu, vòng đời và tần suất thay đổi của dữ liệu liên quan

Trong NoSQL, quyết định **nhúng dữ liệu (embedding)**, **tham chiếu (referencing)** hay **lặp dữ liệu có kiểm soát (denormalization)** không thể chỉ dựa vào việc hai đối tượng “có quan hệ với nhau”. Một đơn hàng liên quan đến khách hàng, sản phẩm, tồn kho và thanh toán; nhưng không có nghĩa mọi thông tin ấy phải nằm trong một document hoặc được cập nhật cùng nhau.

Một thiết kế hợp lý bắt đầu từ ba trục:

1. **Quyền sở hữu (ownership):** Thực thể, aggregate hoặc dịch vụ nào có quyền quyết định giá trị hiện hành và thực hiện thay đổi?
2. **Vòng đời (lifecycle):** Bản ghi được tạo, sửa, hết hạn, xóa hoặc lưu lịch sử theo đối tượng nào?
3. **Tần suất thay đổi (change frequency):** Field hoặc quan hệ được đọc và ghi bao nhiêu lần, tập trung trên những khóa nào, và mỗi lần thay đổi cần cập nhật bao nhiêu bản sao?

Ví dụ, tên Product hiện tại có thể đổi, nhưng tên Product trên một OrderLine đã xác nhận thường phải phản ánh thời điểm giao dịch. `ProductSearchCard` có thể cần đồng bộ tên mới để phục vụ tìm kiếm, còn `OrderLine.nameAtPurchase` lại **không nên** cập nhật theo thay đổi danh mục.

Bài học này sử dụng mô hình document của MongoDB để minh họa cụ thể, đồng thời phân tích những nguyên tắc áp dụng rộng hơn cho hệ NoSQL. Các cơ chế atomicity, unique index, transaction và sharding sẽ khác nhau theo hệ quản trị, cấu hình và phiên bản.

## 1. Dữ liệu liên quan không nhất thiết có cùng chủ sở hữu

Giả sử một hệ thống thương mại có:

~~~text
Customer ───── places ──────> Order
                               │
                               └── has ────────> OrderLine
                                                   │
                                                   └── references ──> Product

Product ───── belongs to ───> Category
Product ───── has ───────────> InventoryByWarehouse
Product ───── receives ──────> Review
Product ───── appears in ───> ProductSearchCard
~~~

Mọi phần đều liên quan, nhưng quan hệ nghiệp vụ khác với ownership.

| Loại dữ liệu | Chủ sở hữu giá trị có hiệu lực | Ghi chú |
|---|---|---|
| Hồ sơ khách hàng hiện tại | Customer/Profile | Tên và thông tin liên hệ có thể được sửa |
| Chi tiết và trạng thái đơn | Order | Phải tuân theo quy tắc cập nhật đơn |
| Dòng hàng và giá đã chốt | Order/OrderLine | Dữ liệu giao dịch theo một thời điểm |
| Thông tin danh mục sản phẩm | Product/Catalog | Tên, SKU, trạng thái hiện hành |
| Tồn kho khả dụng | Inventory | Được nhiều đơn hàng cùng tranh |
| Review | Review hoặc miền đánh giá | Có vòng đời hiển thị, sửa, ẩn riêng |
| Search card | Projection/indexer | Bản sao tối ưu đọc từ các nguồn khác |
| Lịch sử hoạt động | Event/audit subsystem | Chính sách ghi nối tiếp và lưu giữ riêng |

**Ownership** ở đây không chỉ là quyền truy cập đọc/ghi trong database, mà là **thẩm quyền nghiệp vụ đối với sự thật**. Một hệ thống tìm kiếm được phép lưu bản sao tên Product, nhưng không nên tự quyết định tên Product mới thay cho Catalog.

### Nguồn sự thật và bản sao

- **Authoritative source:** nơi định nghĩa giá trị nào là đúng hiện tại.
- **Replica/projection:** nơi biểu diễn lại dữ liệu phục vụ một truy vấn hoặc tác vụ.
- **Snapshot lịch sử:** bản ghi các giá trị tại thời điểm một sự kiện được chốt.
- **Cache:** bản sao tạm thời để giảm độ trễ và tải lên nguồn.

Các loại bản sao trên có hợp đồng cập nhật khác nhau. Không nên gom tất cả vào quy tắc chung “khi nguồn đổi thì đồng bộ mọi chỗ”.

## 2. Ba nghĩa của quyền sở hữu

### 2.1. Sở hữu thuộc tính

Ví dụ `Product.name` thuộc Catalog, `Inventory.available` thuộc Inventory, `Order.totalMinor` thuộc Order. Thậm chí cùng một “Product” trong ngôn ngữ thông thường cũng có những thuộc tính do các miền khác nhau quản lý.

Nếu một nhóm xử lý tồn kho làm thay đổi `available`, họ không nên phải ghi đè toàn bộ Product document chứa cả mô tả và các trường marketing lấy từ phiên bản cũ.

### 2.2. Sở hữu quan hệ

Quan hệ cũng có người sở hữu và quy tắc:

- Order tạo hoặc xóa OrderLine khi đơn còn DRAFT.
- GroupMembership cấp hoặc thu hồi vai trò user trong nhóm.
- Enrollment ghi nhận việc học viên tham gia khóa học.
- Booking quản lý thời điểm giữ chỗ và trạng thái đặt.

Nếu quan hệ có identity, role, timestamp, trạng thái hoặc quyền sửa độc lập, nó có thể là **một thực thể riêng**, không đơn thuần là ID nằm trong mảng.

~~~json
{
  "membershipId": "member-701",
  "tenantId": "tenant-a",
  "userId": "user-9",
  "groupId": "group-3",
  "role": "EDITOR",
  "status": "ACTIVE",
  "joinedAt": "2026-11-14T08:00:00Z"
}
~~~

### 2.3. Sở hữu quyền thay đổi

Một ứng dụng có thể đọc dữ liệu của nhiều miền nhưng **mỗi lệnh cập nhật phải có đường đi có thẩm quyền**.

~~~text
CatalogService   -> Product nguồn
OrderService     -> Order nguồn
InventoryService -> Stock nguồn
SearchConsumer   -> ProductSearchCard projection
~~~

SearchConsumer không nên thay đổi Product nguồn chỉ vì bản sao đang chứa tên khác. Khi bản sao sai, phải **sửa nguồn hoặc đồng bộ lại theo nguồn**, không tạo ra “hai sự thật cạnh tranh”.

## 3. Vòng đời: tạo, tồn tại, lưu giữ và xóa

Vòng đời thường quan trọng hơn độ gần nhau của dữ liệu trong giao diện.

### Dữ liệu phụ thuộc cha

`OrderLine` trong một đơn hàng nhỏ thường có ý nghĩa cùng Order:

~~~javascript
{
  _id: "ord-1001",
  status: "DRAFT",
  lines: [
    { lineId: "L1", productId: "prod-101", quantity: 2 }
  ]
}
~~~

Order quyết định số dòng, số lượng và trạng thái. Nếu không cần truy vấn/tồn tại độc lập, nhúng vào Order có thể hợp lý.

### Dữ liệu tồn tại độc lập

Product tồn tại trước và sau nhiều đơn hàng. Không nên coi Product là child của một Order chỉ vì Order cần thông tin Product. Tương tự, Category dùng chung cho hàng nghìn Product không nên bị xóa chỉ vì một Product bị xóa.

### Dữ liệu có vòng đời lịch sử

Khi Order đã xác nhận, giá, tên sản phẩm và địa chỉ giao hàng ở thời điểm chốt có thể cần giữ riêng, ngay cả khi hồ sơ hiện hành thay đổi. Một bản snapshot như vậy **thuộc vòng đời Order**, không thuộc vòng đời cập nhật thường ngày của Product hoặc Customer.

### Dữ liệu có thời hạn

Cache, session, reservation tạm và telemetry thường có TTL/retention. TTL cleanup có thể chạy bất đồng bộ; không được nhầm việc bản ghi được dọn với **quy tắc nghiệp vụ có hiệu lực đúng thời điểm**.

Ví dụ một reservation hết hạn lúc 10:00 cần bị từ chối theo điều kiện thời gian ở đường ghi nếu nghiệp vụ yêu cầu, kể cả khi job TTL chưa xóa bản ghi.

## 4. Tần suất thay đổi: không chỉ đếm số lần ghi

Khi đánh giá dữ liệu liên quan, cần đo nhiều chiều:

| Chiều | Câu hỏi | Ảnh hưởng |
|---|---|---|
| Đọc thường xuyên | Có bao nhiêu request/giây cần dữ liệu? | Có thể cần cache/projection |
| Ghi thường xuyên | Field bị sửa bao nhiêu lần? | Chi phí index, đồng bộ và contention |
| Cùng đọc | Cha và con có luôn được đọc cùng nhau? | Embedded read có thể có lợi |
| Cùng ghi | Những field nào phải thay đổi nguyên tử? | Xác định aggregate/document boundary |
| Fan-out | Một lần sửa phải cập nhật bao nhiêu bản sao? | Quyết định chi phí denormalization |
| Skew | Một vài khóa có chịu gần hết thay đổi không? | Hot document/partition |
| Tăng trưởng | Mảng quan hệ tăng tới mức nào? | Giới hạn kích thước và phân trang |
| Độ mới | Bản sao được cũ bao lâu? | Consistency contract |

Giả sử một Product được nhắc tới trong **200.000 đơn hàng lịch sử**. Nếu đổi tên Product mà cập nhật mọi OrderLine, chỉ một lần thay đổi có thể tạo lượng lớn thao tác ghi. Nhưng điều quan trọng hơn là các OrderLine **không nên đổi tên lịch sử theo Product hiện tại**.

Ngược lại, một ProductCard cho màn hình tìm kiếm có thể được cập nhật sau khi Product đổi tên. Trong trường hợp này, bản sao có nhiệm vụ phản ánh **trạng thái hiện hành** và cần quy tắc đồng bộ.

## 5. Bốn chiến lược khác nhau

| Chiến lược | Khi thường phù hợp | Ví dụ | Trách nhiệm |
|---|---|---|---|
| **Embedding** | Cùng owner/vòng đời, số lượng giới hạn, cần đọc/ghi cùng | `Order.lines[]` | Kích thước, atomic update, version |
| **Referencing** | Dữ liệu độc lập, được chia sẻ, đổi riêng | `Order.customerId` | Tham chiếu hợp lệ, truy vấn thêm, xóa |
| **Snapshot** | Giữ giá trị tại thời điểm sự kiện | `OrderLine.unitPriceMinor` | Ngữ nghĩa lịch sử, điều chỉnh có kiểm toán |
| **Projection/denormalization** | Đọc thường xuyên, cho phép một mức trễ | `ProductSearchCard` | Đồng bộ, version, retry, rebuild |

Cache có thể xem là một loại bản sao tạm thời, nhưng cần phân biệt cache invalidation với việc duy trì read model được lưu bền vững.

**Embedding không đồng nghĩa với duplication**. Lưu OrderLine trong Order có thể là cấu trúc tự nhiên của aggregate; sao chép Product name hiện hành vào nhiều card là denormalization; lưu tên tại lúc mua là snapshot giao dịch.

## 6. Ví dụ xuyên suốt: Customer, Product và Order

Dữ liệu nguồn:

~~~javascript
// customers
{
  _id: "cus-21",
  tenantId: "shop-a",
  displayName: "Nguyễn Minh",
  defaultAddressId: "addr-7",
  version: NumberLong("3")
}

// products
{
  _id: "prod-101",
  tenantId: "shop-a",
  sku: "KB-RED",
  name: "Bàn phím cơ đỏ",
  currentPriceMinor: NumberLong("350000"),
  status: "ACTIVE",
  version: NumberLong("12")
}
~~~

Khi tạo đơn, một document có thể là:

~~~javascript
// orders
{
  _id: "ord-1001",
  tenantId: "shop-a",
  customerId: "cus-21",
  customerNameAtPurchase: "Nguyễn Minh",
  shippingAddress: {
    recipientName: "Nguyễn Minh",
    city: "Hồ Chí Minh",
    street: "Địa chỉ minh họa"
  },
  lines: [
    {
      lineId: "L1",
      productId: "prod-101",
      skuAtPurchase: "KB-RED",
      nameAtPurchase: "Bàn phím cơ đỏ",
      unitPriceMinor: NumberLong("350000"),
      quantity: 2,
      lineTotalMinor: NumberLong("700000")
    }
  ],
  totalMinor: NumberLong("700000"),
  currency: "VND",
  status: "CONFIRMED",
  confirmedAt: ISODate("2026-11-14T08:00:00Z"),
  version: NumberLong("4")
}
~~~

Ví dụ giả định giá chốt khi xác nhận, không có thuế/giảm giá, và dùng đơn vị tiền nhỏ nhất để minh họa. Trong sản phẩm thực tế, cần xác định chính sách thuế, khuyến mãi, tiền tệ và làm tròn.

### Phân loại từng field

| Field | Ai sở hữu? | Khi nguồn hiện hành thay đổi? |
|---|---|---|
| `Customer.displayName` | Customer | Có thể thay đổi |
| `Order.customerNameAtPurchase` | Order | Thường giữ theo thời điểm giao dịch |
| `Product.name` | Product | Có thể đổi |
| `OrderLine.nameAtPurchase` | Order | Không tự đổi theo Product |
| `Product.currentPriceMinor` | Catalog/Pricing | Có thể đổi |
| `OrderLine.unitPriceMinor` | Order | Giá đã chốt không đổi tùy tiện |
| `Order.shippingAddress` | Order/fulfillment | Chỉ đổi theo quy trình riêng của Order |
| `Inventory.available` | Inventory | Đổi theo nhập/xuất/reservation |
| `Order.status` | Order | Theo state machine của đơn |

Tham chiếu giữ **danh tính** của đối tượng hiện hành; snapshot giữ **giá trị trong ngữ cảnh một giao dịch**. Hai loại dữ liệu có thể cùng nằm trong Order.

## 7. Quyền sở hữu giá trị “đúng” phụ thuộc ngữ cảnh thời gian

Giả sử Product hiện tại có tên `"Bàn phím cơ đỏ – mẫu mới"`, trong khi OrderLine lịch sử lưu `"Bàn phím cơ đỏ"`.

Hai giá trị có thể đều đúng:

- Trang Product hiện tại cần `Product.name`.
- Trang lịch sử Order cần `nameAtPurchase` nếu nghiệp vụ muốn giữ nội dung lúc mua.
- Bộ tìm kiếm Order phải xác định tìm theo tên cũ, tên hiện tại hay cả hai.
- Hóa đơn đã phát hành có thể có quy tắc điều chỉnh riêng.

Không nên viết một job “đồng bộ mọi field tên sản phẩm” nếu không biết **field nào là bản sao hiện hành và field nào là lịch sử**.

### Đặt tên field theo ngữ nghĩa

~~~text
Product.name
OrderLine.productNameAtPurchase
Booking.providerNameAtBooking
Invoice.sellerNameAtIssue
ProductSearchCard.productName
~~~

Cách đặt tên làm rõ đây là trạng thái hiện hành, một bản snapshot hay projection. Nó không thay thế hợp đồng nghiệp vụ, nhưng giúp giảm sai lầm khi phát triển.

## 8. Cùng vòng đời và kích thước nhỏ: nên cân nhắc nhúng

Những ví dụ có thể nhúng:

- Order và danh sách OrderLine giới hạn.
- Survey và câu trả lời được chỉnh sửa cùng lúc.
- Product và một vài thuộc tính kỹ thuật nhỏ.
- Contact và những phương thức liên hệ nhỏ thuộc đúng một owner.
- Workflow draft và các bước được quản lý chung.

### Khi embedding có lợi

1. Dữ liệu con không có vòng đời độc lập.
2. Số phần tử có thể đặt giới hạn.
3. Lệnh thường đọc hoặc sửa cha và con cùng nhau.
4. Các bất biến chung cần được bảo vệ nguyên tử.
5. Không có nhiều writer độc lập tranh chấp document cha.
6. Không cần tìm kiếm/phân trang con như thực thể độc lập với tần suất cao.

Ví dụ Survey:

~~~javascript
{
  _id: "survey-11",
  status: "DRAFT",
  answers: [
    { questionId: "q1", value: "Có" },
    { questionId: "q2", value: "Không" }
  ],
  version: NumberLong("2")
}
~~~

Nếu chuyển `status` thành `SUBMITTED` đòi tất cả câu trả lời hợp lệ, aggregate có thể kiểm tra logic và lưu kết quả trong một document nguyên tử.

Tuy nhiên, **một document write nguyên tử không tự chống lost update** nếu hai writer đọc version cũ rồi ghi đè cả document không có version check. Phải xem cách cập nhật và xử lý cạnh tranh.

## 9. Vòng đời độc lập và chia sẻ rộng: nên cân nhắc reference

Ví dụ một Category có thể được hàng chục nghìn Product dùng chung.

~~~javascript
// category
{
  _id: "cat-keyboards",
  tenantId: "shop-a",
  name: "Bàn phím",
  status: "ACTIVE"
}

// product
{
  _id: "prod-101",
  tenantId: "shop-a",
  categoryId: "cat-keyboards",
  name: "Bàn phím cơ đỏ"
}
~~~

Khi Category đổi tên, không cần sửa mọi Product nguồn nếu chỉ lưu `categoryId`.

### Reference có đánh đổi

- Có thể cần truy vấn thứ hai để lấy Category.
- Nhiều Product trong một danh sách có thể gây **N+1 queries** nếu tra Category từng item.
- Có thể batch theo tập `categoryId`, dùng cache hoặc read model.
- Nếu Category không còn tồn tại, cần xử lý reference mồ côi.
- Phải kiểm tra `tenantId` và quyền truy cập khi follow reference.

Vì thế, **reference giữ ownership rõ ràng**, còn **projection có kiểm soát** có thể giải quyết bài toán đọc nhanh.

## 10. Mảng tăng không giới hạn: dấu hiệu nên tách thực thể

Một Product có thể có:

- 8 biến thể.
- 10.000 review.
- 2 triệu lượt xem.
- Hàng triệu sự kiện click.
- 100.000 thay đổi tồn kho theo thời gian.

Nếu nhúng mọi thứ:

~~~javascript
{
  _id: "prod-101",
  reviews: [ /* không ngừng tăng */ ],
  viewEvents: [ /* không ngừng tăng */ ]
}
~~~

sẽ gặp giới hạn kích thước document, tần suất ghi lớn, khó phân trang và chi phí index cao. Document MongoDB có giới hạn kích thước BSON; ngay trước khi chạm giới hạn vẫn có thể gặp vấn đề memory, cập nhật và contention.

Một thiết kế riêng cho Review:

~~~javascript
{
  _id: "review-981",
  tenantId: "shop-a",
  productId: "prod-101",
  authorId: "cus-21",
  score: 5,
  status: "VISIBLE",
  createdAt: ISODate("2026-11-14T09:00:00Z")
}
~~~

và một projection tổng hợp:

~~~javascript
{
  _id: "shop-a:prod-101",
  productId: "prod-101",
  visibleReviewCount: 275,
  averageScore: 4.6,
  computedAt: ISODate("2026-11-14T09:05:00Z")
}
~~~

Review có thể sửa/ẩn theo quy tắc riêng. `ProductReviewSummary` là giá trị dẫn xuất, không quyết định tính hợp lệ của review gốc.

## 11. Quan hệ N–N thường có vòng đời riêng

Một User có thể ở nhiều Group; Group có nhiều User. Hai mảng đối xứng:

~~~javascript
// user
{ _id: "u-1", groupIds: ["g-1", "g-2"] }

// group
{ _id: "g-1", memberIds: ["u-1", "u-3"] }
~~~

có thể gây lệch nếu thêm member mà chỉ cập nhật một bên. Nếu quan hệ còn có `role`, `joinedAt`, `status`, nó thường xứng đáng là một document riêng:

~~~javascript
{
  _id: "membership-1",
  tenantId: "tenant-a",
  userId: "u-1",
  groupId: "g-1",
  role: "MEMBER",
  status: "ACTIVE",
  joinedAt: ISODate("2026-11-14T09:00:00Z")
}
~~~

Có thể tạo index theo `(tenantId, userId)` và `(tenantId, groupId)` phục vụ hai hướng truy vấn. Nếu một cặp user–group chỉ được có một membership ACTIVE, cần unique/conditional constraint đúng phạm vi và lifecycle, không chỉ truy vấn trước khi insert.

Quan hệ không còn là “chỉ cần nối hai ID” khi có **thuộc tính, vòng đời và bất biến riêng**.

## 12. Tần suất thay đổi và số lượng bản sao tạo write amplification

Giả sử tên Category đổi `U` lần mỗi ngày và được lặp ở `N` ProductCard. Nếu chọn cập nhật tất cả bản sao sau mỗi lần đổi, khối lượng ghi lan truyền ở mức khái niệm:

\[
W_{\text{propagation}} \approx U \times N
\]

Ví dụ 10 lần thay đổi mỗi ngày và 20.000 bản sao cần cập nhật có thể tạo gần **200.000 lần ghi bản sao/ngày**, trước khi tính batching hoặc các tối ưu khác.

Nếu Category chỉ có một nguồn và client đọc tên Category qua một cache dùng chung, số lần ghi đồng bộ có thể giảm đáng kể. Tuy nhiên đọc sẽ cần kết hợp dữ liệu theo `categoryId`.

Bài toán không chỉ có “ít write hơn” mà còn có **read latency, tính sẵn sàng, độ mới dữ liệu và chi phí vận hành**.

### Một bản sao không nên nằm trong phép tính lan truyền

OrderLine lịch sử có `categoryNameAtPurchase` hoặc `productNameAtPurchase` phải giữ giá trị lúc mua theo chính sách. Nó **không phải** một projection hiện hành cần cập nhật hàng loạt.

Phân biệt đúng loại bản sao trước khi ước lượng fan-out.

## 13. Hot document từ việc nhúng dữ liệu thay đổi quá thường xuyên

Giả sử mọi tồn kho của một cửa hàng được nhúng vào một document:

~~~javascript
{
  _id: "inventory:shop-a",
  items: [
    { sku: "A", available: 100 },
    { sku: "B", available: 200 }
    // Hàng nghìn SKU khác
  ]
}
~~~

Nhiều request độc lập cùng ghi những SKU khác nhau vẫn cạnh tranh trên một document lớn, có thể tạo hotspot.

Có thể tách theo `(tenantId, warehouseId, sku)`:

~~~javascript
{
  _id: "shop-a:HCM:sku-A",
  tenantId: "shop-a",
  warehouseId: "HCM",
  sku: "sku-A",
  available: 100,
  reserved: 0
}
~~~

Lợi ích là những SKU độc lập có thể được phân bố và cập nhật độc lập. Đánh đổi: một thao tác giữ **nhiều SKU cùng lúc** giờ có thể cần transaction hoặc reservation workflow nếu yêu cầu all-or-nothing.

**Đơn vị thay đổi thường xuyên** có thể quan trọng hơn sự tiện lợi của việc đọc mọi thứ trong một document.

## 14. Nhúng dữ liệu không biến owner khác thành child

Inventory được nhiều Order cùng sử dụng. Nếu nhúng `available` hiện hành vào từng Order để “đọc nhanh”, các bản sao dễ không khớp và không có một điểm ghi có thẩm quyền để ngăn oversell.

Một thiết kế đúng thường phân vai:

~~~text
Order aggregate:
    lines, total, status, reservation references

Inventory aggregate:
    available, reserved, warehouse, SKU

Product catalog:
    product name, SKU, current descriptive fields

Read model:
    product summary hoặc trạng thái tồn hiển thị có thể trễ
~~~

Khi người dùng đặt hàng, phần quyết định giữ hàng phải truy cập Inventory hoặc cơ chế reservation phù hợp; đọc từ ProductCard có thể chỉ là tín hiệu giao diện.

### Conditional update trong MongoDB

~~~javascript
const quantity = 2;

const result = db.inventory.updateOne(
  {
    _id: "shop-a:HCM:sku-A",
    available: { $gte: quantity }
  },
  {
    $inc: {
      available: -quantity,
      reserved: quantity
    }
  }
);
~~~

Điều kiện và thay đổi trên một document được áp dụng nguyên tử trong phạm vi lệnh ghi. Tuy nhiên, nếu client timeout và retry cùng ý định, lệnh có thể trừ hai lần nếu vẫn còn đủ tồn; cần thêm `reservationId` và cơ chế idempotency.

Nói cách khác, **ownership rõ không tự thay thế concurrency control**, nhưng giúp đặt concurrency control đúng nơi.

## 15. Cùng đọc nhiều và ít thay đổi: projection có thể hợp lý

Một trang tìm kiếm có thể cần hiển thị:

- Tên Product.
- Tên Category.
- Giá hiển thị.
- Điểm review trung bình.
- Có hàng hay không theo mức độ mới được chấp nhận.

Nếu mỗi item kéo dữ liệu từ bốn service, một trang 20 item có thể tạo rất nhiều truy vấn. Một read model:

~~~javascript
{
  _id: "shop-a:prod-101",
  tenantId: "shop-a",
  productId: "prod-101",
  productName: "Bàn phím cơ đỏ",
  categoryName: "Bàn phím",
  displayPriceMinor: 350000,
  ratingAverage: 4.6,
  ratingCount: 275,
  sourceVersions: {
    product: NumberLong("12"),
    category: NumberLong("4"),
    reviewSummary: NumberLong("27")
  }
}
~~~

giúp đọc nhanh. Nhưng nó là **bản sao dẫn xuất**, không phải nơi nhận lệnh sửa Product, Category hay Review.

Khi nguồn đổi, projection phải được cập nhật theo hợp đồng. Nếu một field cần consistency rất mạnh, có thể không nên nằm trong projection trễ hoặc phải được xác minh lại khi thực hiện hành động quan trọng.

## 16. Snapshot lịch sử và nguồn hiện hành

Xem một OrderLine:

~~~javascript
{
  lineId: "L1",
  productId: "prod-101",
  skuAtPurchase: "KB-RED",
  nameAtPurchase: "Bàn phím cơ đỏ",
  unitPriceMinor: 350000,
  quantity: 2
}
~~~

Các field mang hai loại quan hệ:

- `productId`: tham chiếu tới Product có identity ổn định.
- `skuAtPurchase`, `nameAtPurchase`, `unitPriceMinor`: ảnh chụp giá trị khi giao dịch.

Nếu Product đổi tên hoặc giá:

- Product hiện hành đổi.
- SearchCard hiện hành có thể đồng bộ.
- OrderLine snapshot thường không đổi.
- Nếu giao dịch cần điều chỉnh sau này, nên có quy trình điều chỉnh có dấu vết, không ghi đè âm thầm.

### Thời điểm chụp snapshot

Cần ghi rõ `captureAt`: khi thêm vào giỏ, khi xác nhận đơn, khi thanh toán hay khi phát hành hóa đơn?

Giá trong giỏ có thể chỉ là **ước tính**, còn giá khi Order CONFIRMED mới là giá cam kết. Nếu không phân biệt thời điểm, hệ thống có thể lưu một “giá lúc mua” không đúng.

## 17. Event time và recorded time

Dữ liệu có quan hệ thời gian nên phân biệt:

- **Effective/event time:** khi giá trị có hiệu lực hoặc sự kiện xảy ra.
- **Recorded/ingestion time:** khi hệ thống nhận/ghi nhận nó.

Ví dụ:

~~~json
{
  "productId": "prod-101",
  "priceMinor": 370000,
  "effectiveFrom": "2026-11-15T00:00:00Z",
  "recordedAt": "2026-11-15T00:05:00Z"
}
~~~

Nếu bản cập nhật đến muộn, giá tại 00:02 có thể khác giá hiện hệ thống ghi nhận lúc 00:02. Bài toán lịch sử cần chính sách rõ về dữ liệu đến muộn, sửa hồi tố và cách chốt giá khi giao dịch diễn ra.

Một `updatedAt` duy nhất không luôn đủ để trả lời mọi câu hỏi lịch sử.

## 18. Xóa cha và xử lý quan hệ: không có một quy tắc toàn cục

Khi Product bị xóa khỏi catalog, các quan hệ khác nhau có vòng đời khác nhau.

| Dữ liệu liên quan | Hướng thường cân nhắc |
|---|---|
| ProductSearchCard | Ẩn hoặc xóa projection theo nguồn |
| Cache Product | Invalidate hoặc expire |
| OrderLine snapshot | Giữ theo chính sách lịch sử giao dịch |
| Review | Ẩn, giữ, xóa hoặc lưu trữ theo policy riêng |
| Inventory | Đối soát tồn còn lại, ngừng bán và lưu theo workflow |
| Recommendation index | Loại Product khỏi ứng viên |
| Audit/event | Xử lý theo retention và quyền riêng tư áp dụng |

Các chiến lược xóa phổ biến:

1. **Restrict:** chặn xóa khi còn quan hệ cần được bảo vệ.
2. **Cascade:** xóa dữ liệu con cùng vòng đời.
3. **Detach:** bỏ reference nhưng giữ dữ liệu hợp lệ độc lập.
4. **Soft delete:** đánh dấu ngừng hoạt động, vẫn giữ identity.
5. **Tombstone:** giữ dấu vết tối thiểu để tránh tái dùng ID hoặc xử lý event cũ.

Không nên tự động xóa mọi dữ liệu có `productId` khi Product bị xóa. Điều đó có thể phá vỡ lịch sử Order hoặc làm mất dữ liệu mà quy trình vận hành vẫn cần.

## 19. Khi tham chiếu trở thành mồ côi

Một Order có `customerId = "cus-21"` nhưng Customer đã bị xóa, hoặc Review trỏ đến Product không còn hoạt động.

NoSQL không nhất thiết có foreign key constraint ở mọi mô hình. Cần thiết kế:

- Kiểm tra reference khi tạo.
- Quy định quyền xóa và thời điểm xóa.
- Quét/đối soát các reference mồ côi.
- Đọc API có fallback/snapshot phù hợp khi đích không còn.
- Tránh hiển thị dữ liệu của tenant khác nếu ID bị nhầm scope.
- Xử lý event đến trễ sau khi nguồn bị xóa.

Một `productId` ổn định giúp nhận diện, nhưng **không tự bảo đảm tính tồn tại hoặc quyền truy cập** của Product đích.

## 20. Tenant isolation là một phần của ownership

Trong hệ thống đa tenant, việc tham chiếu Product hoặc Customer phải có scope rõ.

~~~javascript
db.orders.findOne({
  tenantId: authenticatedTenantId,
  _id: requestedOrderId
});
~~~

`authenticatedTenantId` cần được lấy từ ngữ cảnh xác thực/ủy quyền, không tin trực tiếp tham số do client cung cấp.

Nếu `productId` chỉ unique trong tenant, một reference có thể cần `(tenantId, productId)`. Nếu ID toàn cục, vẫn phải kiểm tra quyền đọc và owner tenant của thực thể. ID ngẫu nhiên không phải cơ chế phân quyền.

Khi duplicate dữ liệu nhạy cảm như địa chỉ giao hàng hay số điện thoại, số nơi cần áp retention, mã hóa, kiểm toán và xóa/ẩn dữ liệu cũng tăng. **Lợi ích đọc nhanh phải đi cùng chi phí quản lý bản sao.**

## 21. Đồng bộ projection theo event

Một kiến trúc phổ biến:

~~~mermaid
flowchart TD
    A["Catalog service"] --> B["Product source"]
    B --> C["Event / CDC"]
    C --> D["Search card consumer"]
    C --> E["Cache invalidator"]
    C --> F["Recommendation builder"]
    D --> G["ProductSearchCard"]
    E --> H["Product cache"]
    F --> I["Recommendation projection"]
~~~

Trong sơ đồ, Catalog là owner của Product; các consumer tạo ra **những góc nhìn dữ liệu khác nhau**.

### Lỗi thường gặp

**Commit nguồn thành công nhưng event không phát:** Code update Product rồi publish event có khoảng hở khi process chết giữa hai bước. Transactional outbox hoặc CDC phù hợp có thể giảm rủi ro.

**Event gửi lặp:** Consumer xử lý cùng một event hai lần. Cần idempotency, `eventId` hoặc thao tác upsert có điều kiện theo version.

**Event đến sai thứ tự:** Version 13 có thể đến trước version 12. Consumer cần từ chối dữ liệu cũ hơn phiên bản đã áp dụng.

**Xóa nguồn nhưng projection còn tồn tại:** Cần delete/tombstone event, TTL theo chính sách và kiểm tra quyền/khả dụng tại đường ghi quan trọng.

**Projection không rebuild được:** Nếu chứa field mà nguồn không thể khôi phục, nó đã trở thành owner của dữ liệu khác và phải được mô hình hóa như vậy.

### Đồng bộ không nhất thiết là transaction chung

Việc update Product nguồn và cập nhật Search index có thể không nguyên tử, đặc biệt khi có nhiều dịch vụ/engine. Cần định nghĩa mức độ mới chấp nhận được, cơ chế nhận diện lag và cách phục hồi sau lỗi.

## 22. Version giúp chống event cũ ghi đè event mới

Projection có thể lưu:

~~~javascript
{
  _id: "shop-a:prod-101",
  productId: "prod-101",
  name: "Bàn phím cơ đỏ",
  sourceVersion: NumberLong("12")
}
~~~

Với event version 13, ví dụ cập nhật **bản projection đã tồn tại**:

~~~javascript
const incomingVersion = NumberLong("13");

db.productSearchCards.updateOne(
  {
    _id: "shop-a:prod-101",
    sourceVersion: { $lt: incomingVersion }
  },
  {
    $set: {
      name: "Bàn phím cơ đỏ mới",
      sourceVersion: incomingVersion
    }
  }
);
~~~

Nếu event version 12 đến sau, điều kiện `sourceVersion < 12` không thỏa và không ghi đè version 13.

Trường hợp projection **chưa tồn tại** cần một đường tạo riêng với unique identity; không nên vô điều kiện thêm `upsert: true` vào filter có `sourceVersion < incomingVersion` vì có thể xung đột nếu bản ghi đã tồn tại với version mới hơn. Một implementation hoàn chỉnh phải xử lý cả tạo lần đầu, duplicate, out-of-order, delete và rebuild.

Version giúp theo dõi **thứ tự thay đổi từ một nguồn**, nhưng với nhiều nguồn độc lập phải xác định version theo từng field/owner hoặc một cơ chế gộp phù hợp.

## 23. Thời điểm nào bản sao được phép cũ?

Cùng một document có thể được đọc trong các ngữ cảnh khác nhau:

| Ngữ cảnh | Dữ liệu cũ có thể chấp nhận? | Hướng thiết kế |
|---|---|---|
| Danh mục giới thiệu | Có thể trong giới hạn SLO | Projection hoặc cache |
| Số review hiển thị | Thường chấp nhận trễ có kiểm soát | Materialized summary |
| Giá tham khảo | Phụ thuộc sản phẩm và quy tắc hiển thị | Cache với thông báo/cơ chế xác nhận |
| Giá chốt đơn | Phải theo quy tắc xác nhận giao dịch | Nguồn có thẩm quyền + snapshot |
| Tồn để quyết định bán | Không dùng một bản trễ làm quyết định cuối | Conditional reservation ở Inventory |
| Quyền người dùng | Không được dùng bản sao trái chính sách cập nhật quyền | Kiểm tra theo yêu cầu bảo mật |
| Báo cáo theo ngày | Có thể trễ theo SLA | Projection/aggregation |

Khi thông báo “mặt hàng còn 3 chiếc” trên trang tìm kiếm, phải quyết định đó là số tồn chính xác tức thời hay chỉ một thông tin gần đúng. Nếu là gần đúng, lệnh mua vẫn phải qua nơi bảo vệ bất biến tồn kho.

## 24. Khi chia dữ liệu, cần chọn phạm vi nguyên tử phù hợp

Một Order chứa `lines[]` và `totalMinor` có thể được cập nhật nguyên tử ở cấp document nếu mô hình nằm trong một document và sử dụng đúng điều kiện. Nếu tách OrderLine thành nhiều document, muốn tổng luôn khớp ngay có thể cần transaction hoặc cách tính từ dữ liệu nguồn khi đọc.

Ví dụ update Order theo version:

~~~javascript
const result = db.orders.updateOne(
  {
    _id: "ord-1001",
    status: "DRAFT",
    version: NumberLong("1")
  },
  {
    $set: {
      lines: [
        { lineId: "L1", quantity: 2, unitPriceMinor: 350000 },
        { lineId: "L2", quantity: 1, unitPriceMinor: 150000 }
      ],
      totalMinor: 850000
    },
    $inc: { version: NumberLong("1") }
  }
);
~~~

Nếu `matchedCount = 0`, ứng dụng phải xử lý xung đột hoặc trạng thái thay đổi, không xem là thành công.

**Không vì NoSQL mà mặc định phải chấp nhận eventual consistency**. Hệ lưu trữ có thể có transaction nhiều item/document với giới hạn cụ thể. Tuy nhiên, không nên gom tất cả vào một transaction lớn nếu bất biến nghiệp vụ không yêu cầu.

## 25. Xử lý chuyển quyền sở hữu

Một Project được chuyển từ workspace A sang B, hoặc một Provider chuyển sang tổ chức khác. Đây không chỉ là `UPDATE tenantId`.

Cần xác định:

- Các reference từ tenant cũ còn hợp lệ không?
- ID có global unique hay chỉ unique trong tenant?
- Các unique constraint theo tenant mới có thể xung đột không?
- Search/Cache của tenant cũ có được xóa/ẩn kịp không?
- Quyền truy cập lịch sử thay đổi ra sao?
- Event cũ đến muộn có thể vô tình tạo lại projection trong tenant cũ không?
- Dữ liệu giao dịch lịch sử có giữ owner cũ không?

Có thể cần workflow trạng thái trung gian và một kế hoạch di chuyển dữ liệu. Một số record lịch sử phải giữ phạm vi sở hữu gốc, trong khi thực thể cho hoạt động tương lai được tạo/chuyển phù hợp. Không thể quyết định chỉ từ cấu trúc document.

## 26. Truy vấn đọc ảnh hưởng tới mô hình quan hệ

Giả sử các API chính:

1. Đọc Order theo ID kèm toàn bộ dòng hàng.
2. Liệt kê Order của Customer, phân trang.
3. Đọc Product hiện hành.
4. Liệt kê Review của Product theo thời gian.
5. Hiển thị 20 ProductCard với rating.

Hệ quả:

- `Order.lines[]` có thể nhúng nếu số dòng được giới hạn.
- Order giữ `customerId` để query theo Customer.
- Product là document riêng.
- Review là collection riêng vì số lượng tăng và có vòng đời độc lập.
- ProductCard chứa projection dữ liệu từ nhiều nguồn để giảm round-trip.

Ví dụ index theo access pattern:

~~~javascript
db.orders.createIndex({
  tenantId: 1,
  customerId: 1,
  confirmedAt: -1,
  _id: -1
});

db.reviews.createIndex({
  tenantId: 1,
  productId: 1,
  status: 1,
  createdAt: -1
});
~~~

Đây là **index ứng viên**, không phải cấu hình tối ưu được đảm bảo. Cần đo qua query plan, kích thước dữ liệu và tốc độ ghi. Index bổ sung có chi phí lưu trữ và update, nhất là với nhiều field mảng.

## 27. Tần suất ghi ảnh hưởng partitioning

Nếu mọi đơn của một tenant lớn đều ghi vào một partition dựa trên `tenantId`, có thể tạo hot partition. Nếu một Product giữ một mảng lượt xem liên tục append, có thể tạo hot document. Nếu một stock item được nhiều người mua cùng lúc, thêm shard không tự tăng khả năng ghi nguyên tử vào một item duy nhất.

Cần quan sát:

- Request/giây theo tenant, Product, SKU và key.
- Kích thước document trung bình và p99.
- Số lần cập nhật từng document.
- Conflicts/retries.
- Index write amplification.
- Tốc độ phát triển danh sách child.
- Độ trễ projection và chi phí fan-out.
- Latency p95/p99 của các đường đọc/ghi quan trọng.

**Ownership cho biết nơi thay đổi thuộc về; workload cho biết nơi đó có phải điểm nóng không.** Hai thông tin phải được xem cùng nhau.

## 28. Thay đổi mô hình khi quy mô tăng

Ban đầu một Product chỉ có 10 Review, được nhúng trong `products.reviews[]`. Sau một năm, mảng tăng lớn và mỗi Review cần moderating, sửa/xóa độc lập. Muốn tách sang collection riêng, quy trình có thể là:

1. Định nghĩa document Review với identity, productId, tenantId, status, timestamps.
2. Tạo index/validator và kiểm tra quy tắc uniqueness.
3. Backfill mảng hiện có sang collection mới.
4. Bảo đảm review mới đến trong lúc migration không bị bỏ sót bằng cách chuyển writer có kiểm soát hoặc CDC/dual-write đáng tin cậy.
5. Đối soát số lượng, ID, version và trường cần thiết.
6. Chuyển reader sang nguồn mới, có kế hoạch rollback.
7. Ngừng writer cũ và loại cấu trúc nhúng khi an toàn.
8. Duy trì cơ chế sửa dữ liệu thiếu/trùng do quá trình chuyển đổi.

Điểm khó là **ownership chỉ nên chuyển qua một ranh giới rõ ràng**. Hai nơi cùng được phép sửa Review mà không có cơ chế nhất quán sẽ dẫn tới dữ liệu lệch.

### Chuyển từ reference sang snapshot cần dữ liệu lịch sử

Nếu Order cũ chỉ giữ `productId` mà không lưu giá tại lúc mua, không thể tự lấy `Product.currentPriceMinor` hôm nay để tuyên bố là giá năm trước. Cần xem lịch sử giá, event hoặc chứng cứ giao dịch; nếu không có, phải biểu thị dữ liệu không xác định theo chính sách.

Migration không chỉ sao chép byte; phải giữ hoặc khôi phục **ngữ nghĩa dữ liệu**.

## 29. Bảng quyết định tổng hợp

| Câu hỏi | Hướng cân nhắc |
|---|---|
| Child có tồn tại ý nghĩa ngoài parent? | Nếu không, cân nhắc embed |
| Child có owner khác? | Reference hoặc bản sao chỉ đọc |
| Dữ liệu được nhiều entity cùng chia sẻ? | Một nguồn độc lập, có thể cache/projection |
| Child tăng không giới hạn? | Collection riêng, pagination và retention |
| Cần update nguyên tử cùng parent? | Embed hoặc transaction phù hợp |
| Thay đổi thường xuyên và phân bố nóng? | Tách đơn vị ghi nhỏ; tránh hot document |
| Đọc cùng nhau rất thường xuyên? | Embed hoặc read model tối ưu |
| Cần giữ giá trị tại thời điểm sự kiện? | Snapshot có thời điểm chụp rõ |
| Bản sao được trễ? | Event/CDC/cache với SLO độ mới |
| Bản sao sai gây oversell hoặc thanh toán sai? | Quyết định cuối tại nguồn có thẩm quyền |
| Khi parent bị xóa, child vẫn có giá trị? | Không cascade vô điều kiện |
| Quan hệ N–N có role/status riêng? | Relationship entity riêng |
| Dữ liệu nhạy cảm được lặp nhiều nơi? | Tăng kiểm soát quyền, retention và xóa |
| Có thể rebuild bản sao từ nguồn? | Nếu có, bản sao là projection rõ ràng |

Bảng không phải công thức máy móc. Các ràng buộc bất biến và bảo mật cần được đáp ứng trước khi đánh đổi hiệu năng.

## 30. Sai lầm thường gặp

**“Có quan hệ thì nhúng.”** Quan hệ nghiệp vụ không chứng minh cùng ownership/vòng đời.

**“Không lặp dữ liệu mới là thiết kế tốt.”** Snapshot giao dịch, cache và projection là những dạng lặp hợp lý khi có mục đích và hợp đồng.

**“Product đổi tên thì cập nhật cả tên trong Order lịch sử.”** Điều đó có thể làm sai thông tin tại thời điểm mua.

**“Reference luôn rẻ hơn.”** Nó có thể gây N+1 queries, round-trip và phụ thuộc dịch vụ nguồn.

**“Embed luôn nhanh hơn.”** Mảng lớn, hot document và tranh chấp ghi có thể làm giảm hiệu năng.

**“Delete cha là delete hết con.”** Các quan hệ có retention, owner và quyền riêng khác nhau.

**“TTL bảo đảm điều kiện hết hạn chính xác tại giờ đã hẹn.”** TTL cleanup và business deadline là hai vấn đề khác nhau.

**“Event chỉ đến một lần, theo đúng thứ tự.”** Retry, out-of-order và lỗi mạng là những trường hợp phải thiết kế.

**“Read model có đủ dữ liệu nên là nguồn sự thật.”** Dữ liệu dẫn xuất có thể trễ; đường ghi quan trọng cần bảo vệ invariant tại nơi có thẩm quyền.

**“Trung bình ghi ít nên không có hotspot.”** Một vài khóa có thể nhận phần lớn update.

**“Có ID là an toàn.”** Identity không thay thế tenant authorization, lifecycle và integrity check.

## 31. Bài tập áp dụng

### Bài tập A — Customer đổi địa chỉ

Customer có sổ địa chỉ và Order đã CONFIRMED cần giao đến địa chỉ đã chốt.

**Câu hỏi:** Order nên chỉ lưu `addressId` hay một snapshot địa chỉ?

**Hướng suy luận:** snapshot địa chỉ trong Order giúp giữ thông tin giao hàng tại thời điểm chốt; reference có thể giữ thêm để biết nguồn ban đầu. Sửa địa chỉ Order là lệnh nghiệp vụ riêng, không tự xảy ra khi sổ địa chỉ Customer đổi.

### Bài tập B — 2 triệu lượt xem

Product có hàng triệu view event trong một tháng.

**Câu hỏi:** Nên lưu tất cả ở `Product.views[]` không?

**Hướng suy luận:** tần suất ghi lớn, mảng không giới hạn, vòng đời và retention khác Product. Cân nhắc event/time-series riêng và counter projection.

### Bài tập C — Category đổi tên

Một Category có 100.000 Product, đổi tên mỗi quý. Trang danh mục cần đọc nhanh.

**Câu hỏi:** Tham chiếu và projection kết hợp thế nào?

**Hướng suy luận:** Category giữ nguồn, Product giữ categoryId; read model hoặc cache phục vụ hiển thị. Chọn giữa update fan-out và đọc batch/cache theo SLO độ mới và chi phí.

### Bài tập D — Enrollment có điểm và tiến độ

User ghi danh Course, có tiến độ, điểm và trạng thái hoàn thành.

**Câu hỏi:** Chỉ để courseId trong `user.enrolledCourseIds` đã đủ chưa?

**Hướng suy luận:** Enrollment có thuộc tính và vòng đời riêng nên có thể là document độc lập với `userId` và `courseId`. User và Course tồn tại riêng.

### Bài tập E — Event sai thứ tự

Consumer nhận ProductChanged version 15 rồi version 14.

**Câu hỏi:** Làm sao tránh projection bị lùi version?

**Hướng suy luận:** update có điều kiện theo sourceVersion, dedupe và xử lý trường hợp projection chưa tồn tại; không giả định thứ tự nhận qua mạng là thứ tự thay đổi.

### Bài tập F — Xóa Provider

Provider đóng tài khoản nhưng còn Booking đang thực hiện và Booking lịch sử.

**Câu hỏi:** Những dữ liệu nào cần ẩn, giữ hoặc xử lý qua workflow?

**Hướng suy luận:** ẩn search projection, xử lý Booking đang hoạt động theo quy tắc, giữ hoặc giảm thiểu snapshot lịch sử theo policy, đối soát reference và quyền.

### Bài tập G — Flash sale

Một SKU có 5.000 lệnh giữ tồn mỗi giây, Product mô tả chỉ đổi mỗi tháng.

**Câu hỏi:** Có nên nhúng tồn kho vào Product?

**Hướng suy luận:** tần suất và owner khác nhau. Tách Inventory giúp bảo vệ update và tối ưu phân bố độc lập; dùng conditional write, idempotency và reservation workflow khi cần.

## 32. Khung ghi lại quyết định mô hình

Có thể lập tài liệu cho một quan hệ:

~~~yaml
relationship: Order -> Product
source:
  entity: Product
  owner: CatalogService
reference:
  field: productId
  scope: tenantId
  stability: immutable
snapshot:
  owner: Order
  fields:
    - skuAtPurchase
    - nameAtPurchase
    - unitPriceMinor
  captureAt: OrderConfirmed
  updateFromSourceAfterCapture: false
lifecycle:
  productDeactivation: "Order history keeps permitted snapshot"
consistency:
  currentCatalog: "Product source or approved projection"
  orderHistory: "Order snapshot"
readPatterns:
  - "Read order with lines by orderId"
  - "Read current product by productId"
invariants:
  - "Order total matches confirmed lines"
  - "Purchase price does not follow current catalog price"
~~~

Đây là mô tả thiết kế, không phải YAML được MongoDB tự động thực thi. Cần chuyển quyết định thành domain code, storage rules, index, API, event contract và cách vận hành.

## 33. Quy trình quyết định trong thực tế

1. **Xác định quan hệ:** hai thực thể liên quan như thế nào?
2. **Xác định owner:** ai được quyền quyết định từng field và tạo/xóa quan hệ?
3. **Vẽ vòng đời:** data có tồn tại độc lập, cần giữ lịch sử hay TTL không?
4. **Đo workload:** read/write rate, skew, fan-out, cardinality và thời gian giữ.
5. **Phân loại bản sao:** live source, reference, snapshot, cache hay projection?
6. **Xác định bất biến:** quy tắc nào phải đúng ngay trong một transaction?
7. **Chọn cấu trúc:** embed, reference hoặc relationship entity với khả năng truy vấn thực tế.
8. **Thiết kế đồng bộ:** sourceVersion, event/CDC/outbox, idempotency, deletion, rebuild.
9. **Bảo vệ quyền:** tenant scope, kiểm soát field nhạy cảm và retention.
10. **Kiểm thử khi thay đổi đồng thời và lỗi:** duplicate event, out-of-order, nguồn bị xóa, backfill, hot key, failover.
11. **Quan sát vận hành:** projection lag, orphan references, conflicts, p95/p99 và chi phí index.
12. **Lập kế hoạch tiến hóa:** có thể tách mảng lớn hoặc bổ sung snapshot lịch sử về sau không?

## 34. Kết luận

Ba trục thiết kế trả lời ba câu hỏi khác nhau:

- **Quyền sở hữu:** Ai có quyền nói giá trị nào là đúng?
- **Vòng đời:** Dữ liệu phải sống, thay đổi và được xóa cùng với ai?
- **Tần suất thay đổi:** Dữ liệu và quan hệ bị tác động thường xuyên đến đâu, ở bao nhiêu nơi?

Một nguyên tắc thực dụng là:

> **Cùng owner, cùng vòng đời, kích thước giới hạn và thường cần đổi nguyên tử → cân nhắc embedding. Owner hoặc vòng đời độc lập → reference. Giá trị phải phản ánh một thời điểm lịch sử → snapshot. Cần đọc nhanh và chấp nhận trễ → projection/cache với hợp đồng đồng bộ.**

Đây là quy tắc định hướng, không phải một phép thay thế cho phân tích bất biến, sharding và workload thực tế. Trong NoSQL, **lặp dữ liệu không phải tự thân là vấn đề**; vấn đề xuất hiện khi một bản sao không có owner rõ, bị cập nhật sai theo vòng đời hoặc tạo quá nhiều ghi khi dữ liệu nguồn thay đổi. Khi ba trục được xác định tường minh, mô hình quan hệ trở nên dễ giải thích, dễ kiểm soát nhất quán và có khả năng phát triển cùng hệ thống.

# Tối ưu mô hình document theo mẫu truy cập và tần suất cập nhật trong MongoDB

## 1. Từ cấu trúc dữ liệu “đẹp” đến cấu trúc dữ liệu chạy tốt

Một đội phát triển xây hệ thống thương mại điện tử bằng MongoDB. Mỗi sản phẩm có tên, mô tả, thương hiệu, giá, tồn kho, nhiều biến thể, hàng nghìn đánh giá và lịch sử điều chỉnh tồn kho.

Ban đầu họ lưu mọi thứ trong một document:

```javascript
{
  _id: "P1001",
  name: "Tai nghe Bluetooth",
  description: "Mo ta san pham...",
  price: 890000,
  inventory: {
    available: 127,
    reserved: 12
  },
  reviews: [
    /* nhiều nghìn bài đánh giá */
  ],
  stockMovements: [
    /* lịch sử nhập, xuất, điều chỉnh */
  ]
}
```

Đọc trang sản phẩm rất tiện: một lần `findOne()` đã có nhiều thông tin. Nhưng khi lượng truy cập tăng, những vấn đề bắt đầu xuất hiện:

- Tồn kho được cập nhật hàng trăm lần/giờ, trong khi tên và mô tả hầu như không thay đổi.
- Mỗi đánh giá mới làm mảng `reviews` lớn hơn; document có nguy cơ chạm giới hạn 16 MiB.
- Tất cả cập nhật tồn kho, nội dung sản phẩm và đánh giá cạnh tranh trên cùng document.
- Trang danh sách chỉ cần tên, giá, hình ảnh nhưng truy vấn hoặc xử lý nhầm cả dữ liệu chi tiết nặng.
- Index trên trường thường thay đổi làm tăng chi phí ghi.
- Thống kê xếp hạng cần được tính từ nhiều reviews, nhưng không nhất thiết cần tính lại mỗi request.

Đội kỹ thuật tách dữ liệu thành một vài collections theo nhu cầu truy cập. Đọc trang sản phẩm có thể cần nhiều bước hơn, nhưng **throughput ghi tăng, kích thước document ổn định hơn và những dữ liệu lớn có vòng đời độc lập**.

**Bài học:** thiết kế document trong MongoDB không chỉ là chọn `embed` hay `reference` theo quan hệ dữ liệu. Cần thiết kế theo **workload thực tế**, đặc biệt là **đường truy cập nóng (hot read paths), tần suất cập nhật, tăng trưởng mảng, kích thước dữ liệu và mức nhất quán cần thiết**.

### 1.1. Mục tiêu

Sau bài, bạn có thể:

1. Thu thập và diễn tả mẫu truy cập (access patterns) thành các query/update cụ thể.
2. Phân biệt nhóm dữ liệu thường đọc cùng nhau với nhóm dữ liệu thường cập nhật cùng nhau.
3. Chọn **embedding**, **referencing** hoặc **hybrid** cho quan hệ 1–1, 1–N, N–N và dữ liệu tăng trưởng lớn.
4. Giải thích trade-off giữa **read amplification**, **write amplification**, document contention, working set và số lượng round trips.
5. Tách trường nóng khỏi trường lạnh, giới hạn mảng tăng vô hạn, áp dụng **subset/outlier/extended reference/computed/bucket patterns** khi phù hợp.
6. Thiết kế index và projection theo query shape mà không tạo quá nhiều chi phí ghi.
7. Giữ tính đúng đắn khi dữ liệu trùng lặp, dùng atomic update, optimistic concurrency và transaction khi thật sự cần.
8. Đo hiệu quả bằng `explain("executionStats")`, profiler, metrics, benchmark trên workload đại diện.
9. Xây kế hoạch migration schema an toàn, có rollback và tiêu chí thành công.

## 2. Câu hỏi đúng không phải “MongoDB có hỗ trợ quan hệ này không?”

MongoDB lưu document BSON với khả năng biểu diễn nested object và array. Hai collection vẫn có thể liên hệ qua khóa và kết hợp bằng `$lookup`.

Vấn đề cần trả lời:

> **Một phần dữ liệu được đọc cùng với dữ liệu khác bao nhiêu lần, thay đổi cùng nhau bao nhiêu lần, có thể tăng lớn tới đâu và phải nhất quán đến mức nào?**

### 2.1. Bốn chiều quan trọng

| Chiều | Câu hỏi | Tác động tới schema |
|---|---|---|
| **Read locality** | Các trường nào được đọc cùng nhau? | Ưu tiên colocate/embed dữ liệu hay dùng |
| **Update locality** | Những trường nào thay đổi cùng nhau? | Nhóm trường cập nhật cùng một nghiệp vụ |
| **Growth/cardinality** | Một thực thể có thể sinh ra bao nhiêu mục con? | Quyết định bounded array hay collection riêng |
| **Consistency/lifecycle** | Dữ liệu phải nhất quán và được xóa/giữ theo cách nào? | Chọn snapshot, reference, transaction hoặc event history |

### 2.2. Một schema đúng hôm nay có thể sai sau sáu tháng

Một sản phẩm có 4 reviews hợp lý để nhúng mảng reviews. Cùng thiết kế có thể trở nên rất tốn kém khi sản phẩm nổi tiếng có 300.000 reviews.

Không đánh giá mô hình chỉ dựa trên dataset development nhỏ. Cần xét:

- Phân phối kích thước thực tế (p50, p95, p99, max).
- Tốc độ tăng mỗi tháng.
- Sản phẩm/tenant đặc biệt có cardinality lớn bất thường.
- Sự thay đổi của tỷ lệ read/write theo vòng đời.

### 2.3. Một câu trả lời có thể là “hybrid”

Ví dụ sản phẩm:

```text
products
  - tên, ảnh đại diện, mô tả, category
  - ratingSummary
  - 3 featured reviews

productInventory
  - quantity/reserved/version (ghi thường xuyên)

productReviews
  - mỗi review là document độc lập (tăng trưởng lớn)

stockMovements
  - log lịch sử theo document độc lập
```

Như vậy trang danh sách vẫn đọc nhanh từ `products`, còn dữ liệu nóng và dữ liệu lớn có vòng đời cập nhật riêng.

## 3. Hiểu giới hạn và cơ chế dữ liệu liên quan hiệu năng

### 3.1. Document BSON tối đa 16 MiB

MongoDB có giới hạn **kích thước BSON document 16 MiB**. Giới hạn áp dụng cho document lưu trữ, gồm nested objects và arrays.

Nếu mỗi review nhúng có kích thước trung bình 2 KiB, chỉ riêng 8.000 reviews đã xấp xỉ 16 MiB, chưa tính field name, BSON overhead và các trường sản phẩm:

```text
8.000 * 2 KiB = 16.000 KiB ≈ 15,625 MiB
```

Đây là ước lượng thô; **không thiết kế sát giới hạn** bằng phép nhân đơn giản. Kích thước từng review và document thực tế biến đổi lớn.

### 3.2. Một thao tác ghi một document có tính atomic

MongoDB bảo đảm **atomicity ở cấp một document** cho một write đơn lẻ, kể cả cập nhật nhiều field của document đó.

Ví dụ:

```javascript
db.productInventory.updateOne(
  { _id: "P1001" },
  {
    $inc: {
      available: -1,
      reserved: 1
    }
  }
);
```

Hai thay đổi trên cùng document nằm trong một single-document update, nhưng nghiệp vụ vẫn phải kiểm tra điều kiện tồn kho và kết quả matched/modified.

### 3.3. Multi-document transaction có thật nhưng không miễn phí

Khi tách dữ liệu qua nhiều collections, MongoDB hỗ trợ **multi-document transactions** trong những deployment phù hợp. Tuy nhiên transaction có chi phí về session, locking/conflicts, latency và vận hành. Không nên dùng transaction để che một schema thiếu suy nghĩ khi phần dữ liệu có thể nằm trong một document nhỏ và được cập nhật cùng nhau.

### 3.4. Tách document không tự động nhanh hơn

Thêm collection đồng nghĩa có thể cần:

- Thêm một hoặc nhiều queries.
- `$lookup` hoặc application-level composition.
- Index cho foreign keys.
- Phối hợp consistency.
- Nhiều writes nếu denormalization.

Vì vậy **tách dữ liệu chỉ khi lợi ích đo được hoặc rủi ro tăng trưởng rõ ràng lớn hơn chi phí truy cập liên collection**.

## 4. Bắt đầu từ workload: lập access-pattern matrix

Trước khi chọn schema, hãy ghi lại **những thao tác mà ứng dụng thật sự thực hiện**, không chỉ thiết kế entity từ class Java.

### 4.1. Ví dụ workload của catalog

| ID | Thao tác | Đầu vào | Field cần | Tần suất minh họa | Độ trễ mục tiêu |
|---|---|---|---|---|---|
| R1 | Danh sách sản phẩm | category, sort | name, price, thumbnail, ratingSummary | 4.000/phút | p95 dưới 100 ms |
| R2 | Chi tiết sản phẩm | productId | mô tả, ảnh, variants, 3 reviews đầu | 800/phút | p95 dưới 150 ms |
| R3 | Xem reviews | productId, cursor | 20 reviews/page | 120/phút | p95 dưới 200 ms |
| R4 | Lấy tồn kho | productId | available, reserved | 6.000/phút | p95 dưới 50 ms |
| W1 | Trừ/giữ tồn kho | productId, delta | available, reserved, version | 1.500/phút | p95 dưới 50 ms |
| W2 | Thay mô tả | productId | description | 5/ngày | Có thể chậm hơn |
| W3 | Thêm review | productId | review content, rating | 150/phút | Đảm bảo ghi |
| W4 | Cập nhật rating summary | productId | ratingCount, ratingSum | theo W3 | Eventual hoặc transaction |

**Các tần suất và SLO trên chỉ là dữ liệu giả lập**. Hệ thống thực phải lấy từ metrics/log/trace, phân biệt cao điểm và bình thường.

### 4.2. Đọc đường nóng

R1 cần:

```javascript
{
  _id: "P1001",
  name: "Tai nghe Bluetooth",
  price: 890000,
  thumbnail: "/img/p1001.jpg",
  ratingSummary: {
    count: 824,
    average: 4.7
  }
}
```

R1 **không cần** 3.000 reviews, lịch sử stock movements hoặc description dài 20 KiB.

### 4.3. Ghi đường nóng

W1 đổi available/reserved hàng nghìn lần/giờ. Nếu gộp tồn kho cùng product content, mọi ghi nóng chạm document chứa dữ liệu tương đối lạnh.

Đây là cơ hội cân nhắc tách **inventory document** riêng để giảm áp lực concurrent writes và giữ product read model ổn định.

### 4.4. Tần suất không phải yếu tố duy nhất

Hai fields cùng cập nhật thường xuyên có thể vẫn nên tách nếu:

- Được cập nhật bởi các service khác nhau.
- Có quyền truy cập khác nhau.
- Có contention/hot key khác nhau.
- Có chiến lược TTL/retention khác nhau.
- Có yêu cầu consistency khác nhau.

Ngược lại, trường ít thay đổi nhưng **luôn cần trong cùng response và kích thước nhỏ** có thể nhúng.

## 5. Cách thu thập access patterns có bằng chứng

### 5.1. Nguồn dữ liệu

- Application traces: endpoint, duration, số DB calls.
- MongoDB profiler/slow query logs: query shape, plan, runtime.
- `explain()`: index usage, documents/keys examined.
- Metrics: operation rate, WiredTiger cache, disk IOPS, CPU.
- Change streams/business events: loại và tần suất updates.
- Product analytics: user có thật sự mở reviews hay không.
- Batch/ETL calendar: tác vụ ghi đột biến.

### 5.2. Phân nhóm truy vấn theo shape

Hai request:

```javascript
db.products.findOne({ _id: "P1001" });
db.products.findOne({ _id: "P1002" });
```

có **query shape tương tự** dù literal ID khác.

Nên thống kê:

```text
operation=findOne
collection=products
predicate=_id_eq
projection=summary-fields
frequency/min=...
p95Ms=...
```

Không cần ghi PII hoặc toàn bộ query literal vào observability để đánh giá schema.

### 5.3. Không chỉ nhìn trung bình

Ví dụ:

```text
Product reviews array size:
  median: 6
  p95:    200
  p99:    3.000
  max:    190.000
```

Nếu chỉ nhìn median=6, phương án embed toàn bộ reviews có vẻ hợp lý. Nhưng outliers lớn khiến thiết kế có rủi ro 16 MiB và write contention.

Phải xét phân phối, không chỉ average.

## 6. Embed hay Reference?

### 6.1. Embedding

Ví dụ document đơn hàng:

```javascript
{
  _id: "O1001",
  customerId: "C20",
  status: "PAID",
  shippingAddressSnapshot: {
    city: "Da Nang",
    district: "Hai Chau",
    street: "123 Example"
  },
  items: [
    {
      sku: "P1001",
      nameSnapshot: "Tai nghe Bluetooth",
      unitPrice: 890000,
      quantity: 2
    }
  ],
  total: 1780000
}
```

Ưu điểm:

- Đọc một order lấy thông tin giao hàng và các item mà không cần join.
- Các field của order có thể cập nhật trong cùng document atomic.
- Snapshot giữ nguyên giá/tên/địa chỉ tại thời điểm mua hàng.

Nhược điểm:

- Order có số line items cực lớn có thể thành document quá lớn.
- Thông tin product được copy và cần phân biệt lịch sử với thông tin live.
- Nếu một field nhúng phải được cập nhật hàng loạt trong mọi order cũ, write amplification rất lớn.

### 6.2. Referencing

Ví dụ:

```javascript
// products
{ _id: "P1001", name: "Tai nghe Bluetooth" }

// productReviews
{
  _id: "REV5001",
  productId: "P1001",
  rating: 5,
  comment: "Dung rat tot",
  createdAt: ISODate("2026-09-01T10:00:00Z")
}
```

Ưu điểm:

- Dữ liệu nhiều và tăng vô hạn được lưu thành document độc lập.
- Mỗi review có lifecycle/update/index/retention riêng.
- Phân trang theo review không cần tải toàn bộ mảng.

Nhược điểm:

- Trang product cần query thứ hai hoặc `$lookup` nếu muốn reviews.
- Cần index `productId` + sort keys.
- Có thể phải đồng bộ rating summary ở product.
- Atomicity giữa product và review không tự có nếu ghi nhiều documents.

### 6.3. Quy tắc quyết định

**Nghiêng về embed khi:**

- Dữ liệu **được đọc cùng nhau phần lớn thời gian**.
- Mảng/subdocument có kích thước **giới hạn chắc chắn**.
- Các fields thay đổi như **một đơn vị nghiệp vụ**.
- Cần atomic update trên các trường đó.
- Dữ liệu con không có vòng đời độc lập.

**Nghiêng về reference khi:**

- Số lượng phần tử có thể tăng lớn/không giới hạn.
- Dữ liệu con ít được đọc cùng parent.
- Phần tử cần tìm kiếm, phân trang, cập nhật riêng.
- Có cập nhật đồng thời hoặc nhu cầu phân quyền/TTL khác nhau.
- Một thực thể được chia sẻ và cập nhật từ nhiều parent.

### 6.4. Không phải luật bất biến

Một mảng 20 phần tử không tự động nên embed, và một mảng 500 phần tử không tự động phải reference: kích thước phần tử, tốc độ tăng, read access, index và update patterns mới là căn cứ.

## 7. One-to-one: tổ chức trường nóng và lạnh

Giả sử một tài khoản có:

```javascript
{
  _id: "U100",
  displayName: "Customer A",
  profile: {
    biography: "...",
    avatar: "/a.png"
  },
  sessionStats: {
    lastSeenAt: ISODate("2026-11-14T04:00:00Z"),
    requestCount: 100000
  }
}
```

`profile` thay đổi hiếm; `sessionStats` cập nhật liên tục.

### 7.1. Giữ trong một document khi nào?

Nếu mỗi request hiếm khi ghi, update ít cạnh tranh và cần atomic với profile, giữ chung có thể đơn giản hơn.

### 7.2. Tách thành hai documents khi nào?

Nếu hàng nghìn sự kiện mỗi giây cập nhật một user nổi tiếng/robot account, có thể tách:

```javascript
// users
{
  _id: "U100",
  displayName: "Customer A",
  profile: { biography: "...", avatar: "/a.png" }
}

// userSessionStats
{
  _id: "U100",
  lastSeenAt: ISODate("2026-11-14T04:00:00Z"),
  requestCount: 100000
}
```

Với metric có thể chấp nhận eventually consistent, đôi khi ghi vào **time-bucket counters** còn tốt hơn liên tục tăng một document nóng.

### 7.3. Tách one-to-one có chi phí

Trang profile cần thêm query nếu phải hiển thị sessionStats. Nếu tài khoản thường xuyên được đọc cả hai và ít ghi, tách có thể làm latency cao hơn mà không giải quyết vấn đề nào.

## 8. One-to-few: embed có giới hạn

Một sản phẩm có tối đa 5 ảnh chính:

```javascript
{
  _id: "P1001",
  images: [
    { url: "/img/a.jpg", position: 1 },
    { url: "/img/b.jpg", position: 2 }
  ]
}
```

Nếu business rule thực sự giới hạn ảnh tối đa, embedding hợp lý:

- Dữ liệu nhỏ.
- Được đọc cùng product.
- Thay đổi cùng product khi quản lý catalog.
- Đọc một lần, không cần `$lookup`.

**Điều kiện quan trọng là bounded growth.** Nếu người dùng có thể tải ảnh/video tùy ý, đừng lấy “hiện tại chỉ có 5” làm bảo đảm lâu dài.

### 8.1. Không lưu file ảnh lớn trực tiếp trong mỗi document

Thông thường lưu metadata/URL trong document; blob lớn nằm ở object storage hoặc cơ chế lưu file phù hợp. Đừng ép binary payload khổng lồ vào product BSON chỉ vì MongoDB hỗ trợ BSON binary.

## 9. One-to-many lớn: reference và index ở phía con

Với reviews:

```javascript
{
  _id: "REV5001",
  productId: "P1001",
  rating: 5,
  comment: "Tai nghe tot",
  createdAt: ISODate("2026-10-01T10:00:00Z"),
  authorId: "U200"
}
```

### 9.1. Truy vấn các review mới nhất

```javascript
db.productReviews.createIndex({
  productId: 1,
  createdAt: -1,
  _id: -1
});

db.productReviews.find(
  { productId: "P1001" },
  { rating: 1, comment: 1, createdAt: 1, authorId: 1 }
).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
```

Index hỗ trợ equality trên `productId` và sort theo `createdAt`, `_id`.

### 9.2. Tại sao không nhúng cả 100.000 reviews?

- Kích thước parent tăng không giới hạn.
- Mỗi page reviews cần 20 mục, không phải cả array.
- Một review được xóa/sửa độc lập.
- Index trên array nhiều phần tử có thể sinh nhiều index entries.
- Parent trở thành điểm ghi nóng khi review mới liên tục được thêm.

### 9.3. Không nên dùng một mảng `reviewIds` vô hạn thay cho mảng reviews

Ví dụ:

```javascript
{
  _id: "P1001",
  reviewIds: ["R1", "R2", /* ... 200000 IDs ... */]
}
```

Mảng IDs vẫn tăng vô hạn và tạo khó khăn tương tự về kích thước/update. Với quan hệ lớn, để **foreign key trong child** thường dễ mở rộng hơn.

## 10. Many-to-many: quan hệ thật và dữ liệu snapshot

Giả sử users thích nhiều products, và mỗi product được nhiều users yêu thích.

Mô hình một document mỗi relationship:

```javascript
// favorites
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  userId: "U100",
  productId: "P1001",
  createdAt: ISODate("2026-11-14T04:00:00Z")
}
```

### 10.1. Unique index ngăn duplicates

```javascript
db.favorites.createIndex(
  { userId: 1, productId: 1 },
  { unique: true }
);
```

Truy vấn danh sách yêu thích:

```javascript
db.favorites.find({ userId: "U100" })
  .sort({ productId: 1 })
  .limit(50);
```

Nếu muốn sắp theo `createdAt`, cần index phù hợp với query shape riêng.

### 10.2. Không nhét mảng users yêu thích vào product

Một product viral có 2 triệu favorites sẽ tạo mảng `userIds` khổng lồ. Tách relationship docs giúp việc thêm/xóa favorite không cập nhật cùng product hot document.

### 10.3. Đếm favorites

Nếu UI hiển thị `favoriteCount` liên tục, có thể cập nhật bộ đếm tổng hợp song song; nhưng phải xác định consistency và duplicate handling để count không trôi khi retry.

## 11. Dữ liệu lịch sử và dữ liệu live: đừng cập nhật snapshot sai nghĩa

Trong order, `nameSnapshot` và `unitPrice` nên phản ánh **giá/tên lúc đặt**, không tự động thay khi product catalog đổi.

```javascript
{
  _id: "O1001",
  items: [
    {
      productId: "P1001",
      nameSnapshot: "Tai nghe Bluetooth",
      unitPriceSnapshot: 890000,
      quantity: 2
    }
  ]
}
```

### 11.1. Vì sao denormalization ở đây có chủ đích?

Một order cũ cần hiển thị hóa đơn lịch sử, không phải giá hiện tại của product. Trùng lặp tên/giá ở đây là **một business requirement**, không phải dữ liệu sai cần đồng bộ.

### 11.2. Phân biệt bản sao lịch sử với bản sao hiện hành

| Bản sao | Ví dụ | Có cần update khi nguồn thay đổi? |
|---|---|---|
| Historical snapshot | Giá tại thời điểm mua | **Không**, trừ nghiệp vụ sửa chứng từ đúng quy trình |
| Live denormalized field | Product name trong search card | **Có thể có**, theo consistency contract |
| Cached summary | Rating average | **Có**, theo chính sách cập nhật |
| External immutable event | Stock movement | Thường append-only, không thay dữ liệu quá khứ tùy tiện |

Không kết luận “denormalization luôn làm dữ liệu không nhất quán”; vấn đề là **xác định bản sao được phép lệch hay phải đồng bộ**.

## 12. Tần suất cập nhật: vì sao một field nhỏ cũng có thể là vấn đề lớn

Giả sử:

```text
Product description:
  20 KiB, cập nhật 1 lần/tháng.

Inventory available:
  8 bytes, cập nhật 5.000 lần/phút.
```

Field tồn kho rất nhỏ nhưng có tần suất ghi cao. Tác động gồm:

- Nhiều concurrent updates lên cùng document.
- Tài nguyên phục vụ write, journaling/oplog và index maintenance liên quan.
- Khả năng document-level write conflicts trong những tình huống concurrent.
- Tăng lưu lượng replication mà secondary phải apply.
- Hạn chế throughput khi có hot key.

### 12.1. Không suy rằng mọi `$set` đều ghi lại toàn bộ document

WiredTiger và MongoDB sử dụng những cơ chế cập nhật, storage, replication và oplog encoding phụ thuộc phiên bản/workload.

**Không phát biểu “đổi một số nguyên luôn ghi lại nguyên 1 MiB document” như quy luật tuyệt đối.** Vấn đề chính là write workload, contention, index/working-set pressure và sự tăng trưởng document, cần đo trên deployment thật.

### 12.2. Tách hot field chỉ đáng khi giảm tranh chấp hoặc working set

Một product 2 KiB, cập nhật inventory mỗi 10 phút có thể không cần tách. Một product với array lớn và inventory cập nhật hàng trăm lần/giây là ứng viên mạnh để tách.

### 12.3. Hot field nằm trong compound index

Nếu `available` nằm trong nhiều indexes, mỗi lần thay tồn kho có thể cần cập nhật index entries tương ứng.

Ví dụ:

```javascript
db.products.createIndex({ category: 1, available: 1 });
db.products.createIndex({ brand: 1, available: 1 });
db.products.createIndex({ available: -1, price: 1 });
```

Nếu ứng dụng chỉ query tồn kho trực tiếp bằng `_id`, ba index trên có thể là gánh nặng write không cần thiết. **Index được chọn theo query patterns**, không phải “mỗi field một index”.

## 13. Ví dụ: tách inventory khỏi product content

### 13.1. Trước tối ưu

```javascript
// products
{
  _id: "P1001",
  name: "Tai nghe Bluetooth",
  description: "...",
  price: 890000,
  variants: [ /* nhiều variants */ ],
  inventory: {
    available: 127,
    reserved: 12
  }
}
```

### 13.2. Sau tối ưu

```javascript
// products
{
  _id: "P1001",
  name: "Tai nghe Bluetooth",
  description: "...",
  price: 890000,
  category: "audio",
  thumbnail: "/img/p1001.jpg"
}

// productInventory
{
  _id: "P1001",
  available: 127,
  reserved: 12,
  version: NumberLong("42"),
  updatedAt: ISODate("2026-11-14T04:00:00Z")
}
```

### 13.3. Đọc catalog

```javascript
db.products.find(
  { category: "audio" },
  {
    _id: 1,
    name: 1,
    price: 1,
    thumbnail: 1
  }
).limit(20);
```

Query không cần lấy document inventory nếu UI danh sách không hiển thị lượng tồn thực.

### 13.4. Đọc trang chi tiết

Có thể:

1. Đọc product theo ID.
2. Đọc inventory theo cùng ID.
3. Merge ở application.

Hoặc sử dụng `$lookup` nếu muốn một pipeline.

### 13.5. Tại sao không thể tách vô hạn?

Nếu trang detail luôn cần 50 subdocuments thuộc 50 collections khác nhau, chi phí nhiều queries hoặc aggregation có thể vượt lợi ích. Tối ưu phải cân bằng **read locality và update isolation**.

## 14. Atomic reservation: điều kiện tồn kho quan trọng hơn schema đẹp

### 14.1. Sai lầm read-then-write không đồng bộ

Không nên viết:

```javascript
const inv = db.productInventory.findOne({ _id: "P1001" });

if (inv.available > 0) {
  db.productInventory.updateOne(
    { _id: "P1001" },
    { $inc: { available: -1 } }
  );
}
```

Hai requests đồng thời có thể đọc cùng available và đều cho rằng còn hàng.

### 14.2. Conditional atomic update

```javascript
const result = db.productInventory.updateOne(
  {
    _id: "P1001",
    available: { $gte: 1 }
  },
  {
    $inc: {
      available: -1,
      reserved: 1,
      version: 1
    },
    $currentDate: { updatedAt: true }
  }
);

if (result.modifiedCount === 1) {
  print("Reserved one item");
} else {
  print("No inventory available or item not found");
}
```

**Điều kiện `available: {$gte:1}` cùng với `$inc`** được đánh giá trong một single-document update atomic, tránh race của read-then-write đơn giản.

### 14.3. Khi một order giữ nhiều SKUs

Nếu cần giữ tồn kho của **nhiều product documents** như một đơn vị nghiệp vụ, atomicity cấp một document không đủ. Có thể cần transaction với điều kiện kiểm tra từng SKU, hoặc quy trình reservation/saga có trạng thái và compensation rõ.

Không dùng multiple independent `updateOne()` rồi tuyên bố toàn bộ order reservation đã atomic.

## 15. Optimistic concurrency khi cập nhật dữ liệu ít ghi

Ví dụ hai admin cùng sửa mô tả một product. Có thể dùng trường `version`:

```javascript
// Document trước đó:
// { _id:"P1001", description:"Old", version:7 }

const result = db.products.updateOne(
  {
    _id: "P1001",
    version: 7
  },
  {
    $set: {
      description: "New approved description"
    },
    $inc: { version: 1 }
  }
);

if (result.matchedCount === 0) {
  print("Conflict: reload document and resolve");
}
```

### 15.1. Vì sao cần version?

Nếu hai admin cùng đọc version 7, chỉ request đầu cập nhật thành version 8. Request thứ hai không match, tránh ghi đè một cách âm thầm.

### 15.2. Điều kiện thành công không chỉ dựa vào modifiedCount

Trong một số thao tác cập nhật giá trị giống hệt trước đó, `matchedCount` và `modifiedCount` có thể khác. Với optimistic check, cần định nghĩa kết quả theo filter version và trạng thái nghiệp vụ.

### 15.3. Version field không loại bỏ mọi conflict

Vẫn cần quy tắc merge changes và xử lý retry của ứng dụng. Với workflow nhiều documents, transaction hoặc state machine vẫn có thể cần.

## 16. Subset Pattern: giữ phần thường đọc, tách phần còn lại

Sản phẩm có hàng nghìn reviews nhưng trang detail chỉ hiển thị **3 reviews nổi bật**.

### 16.1. Document hybrid

```javascript
// products
{
  _id: "P1001",
  name: "Tai nghe Bluetooth",
  ratingSummary: {
    count: 824,
    sum: 3884,
    average: 4.7136
  },
  featuredReviews: [
    {
      reviewId: "REV1",
      rating: 5,
      excerpt: "Am thanh rat tot"
    },
    {
      reviewId: "REV2",
      rating: 4,
      excerpt: "Pin on"
    }
  ]
}

// productReviews
{
  _id: "REV1",
  productId: "P1001",
  rating: 5,
  comment: "Am thanh rat tot khi nghe nhac..."
}
```

### 16.2. Lợi ích

- Trang detail không cần join để lấy rating và vài review.
- Toàn bộ reviews vẫn được lưu/phân trang riêng.
- Kích thước product document được kiểm soát.

### 16.3. Đánh đổi

- Một review thay đổi có thể cần cập nhật `featuredReviews` snapshot.
- Cần xác định featured policy: mới nhất, nhiều likes, editorial?
- Nếu review bị xóa vì vi phạm, snapshot phải được cập nhật/xóa theo thời hạn yêu cầu.
- UI phải chấp nhận độ trễ cập nhật nếu dùng asynchronous worker.

### 16.4. Giới hạn array subset

Nếu luôn giữ tối đa ba reviews:

```javascript
db.products.updateOne(
  { _id: "P1001" },
  {
    $push: {
      featuredReviews: {
        $each: [{
          reviewId: "REV3",
          rating: 5,
          excerpt: "Rat de su dung"
        }],
        $position: 0,
        $slice: 3
      }
    }
  }
);
```

Ví dụ này chỉ minh họa bounded array. Với “featured theo popularity” cần logic chọn lọc, duplicate prevention và concurrent update riêng; `$push` đơn thuần không tự bảo đảm chính sách đó.

## 17. Outlier Pattern: đừng để vài trường hợp đặc biệt ép toàn bộ schema

Một hệ thống sản phẩm:

```text
95% products:   tối đa 30 reviews
4,9% products:  30–2.000 reviews
0,1% products:  trên 100.000 reviews
```

Nếu embed một số review cho phần lớn products là lợi, có thể dùng **Outlier Pattern**:

```javascript
// products
{
  _id: "P1001",
  reviewPreview: [ /* tối đa 3 */ ],
  hasMoreReviews: true,
  reviewCount: 100234
}
```

Toàn bộ reviews ở collection riêng; một số ít outliers có thể có lộ trình xử lý phù hợp (partition/pagination/caching).

### 17.1. Điểm cần nhớ

Outlier Pattern không nhất thiết là “99% embed toàn bộ, 1% lưu ngoài”. Điều quan trọng là **dùng thiết kế có ngoại lệ rõ ràng** để không đánh đổi hiệu năng toàn hệ thống vì vài document cực lớn.

### 17.2. Cần test đường đọc outlier

Nếu `hasMoreReviews=true`, API phải biết lấy phần còn lại ở đâu. Không để application chỉ đọc mảng embedded rồi trả dữ liệu thiếu cho trường hợp outlier.

### 17.3. Khi nào dùng schema thống nhất?

Nếu chênh lệch kích thước không quá lớn hoặc code complexity quá cao, mô hình **reference tất cả reviews** có thể đơn giản và đáng tin hơn một hybrid quá nhiều nhánh.

## 18. Extended Reference Pattern: copy một ít field để tránh join thường xuyên

Một collection `orderItems` có nhiều order lines. API báo cáo thường cần `productName`, `category` và `brand` bên cạnh `productId`.

### 18.1. Chỉ giữ khóa tham chiếu

```javascript
{
  orderId: "O1001",
  productId: "P1001",
  quantity: 2
}
```

Để hiển thị tên/category phải join hoặc query riêng.

### 18.2. Extended Reference

```javascript
{
  orderId: "O1001",
  productId: "P1001",
  productSnapshot: {
    name: "Tai nghe Bluetooth",
    category: "audio"
  },
  quantity: 2
}
```

Ưu điểm: đường đọc báo cáo có những field thường dùng, giảm số lookup.

### 18.3. Phải xác định semantics

Nếu `productSnapshot` là **lịch sử tại thời điểm mua**: không propagate những thay đổi catalog mới.

Nếu là **bản sao “live” nhằm tối ưu đọc**: phải có đồng bộ/cache invalidation và chấp nhận một mức staleness hoặc yêu cầu consistency.

Không dùng cùng một field name `nameSnapshot` cho cả hai mục đích gây nhầm.

## 19. Computed Pattern: tính trước dữ liệu hay đọc nhiều

Tính rating trung bình:

```javascript
db.productReviews.aggregate([
  { $match: { productId: "P1001" } },
  {
    $group: {
      _id: "$productId",
      count: { $sum: 1 },
      sum: { $sum: "$rating" },
      average: { $avg: "$rating" }
    }
  }
]);
```

Nếu API danh sách chạy aggregation này cho mọi sản phẩm trên mỗi page, chi phí có thể rất cao.

### 19.1. Giữ summary được cập nhật theo writes

```javascript
{
  _id: "P1001",
  ratingSummary: {
    count: 824,
    sum: 3884
  }
}
```

Frontend tính:

```text
average = sum / count
```

hoặc backend project giá trị đã chuẩn hóa.

### 19.2. Mẫu cộng dồn

Khi thêm một review rating 5, về mặt khái niệm:

```javascript
db.products.updateOne(
  { _id: "P1001" },
  {
    $inc: {
      "ratingSummary.count": 1,
      "ratingSummary.sum": 5
    }
  }
);
```

### 19.3. Vấn đề consistency khi ghi hai documents

Nếu insert review thành công nhưng cập nhật summary thất bại, count sai.

Các phương án:

- Multi-document transaction khi cần consistency chặt và workload cho phép.
- Outbox/event-driven worker với **idempotency key**, retry và reconciliation.
- Định kỳ recompute summary từ source-of-truth.
- Eventual consistency được công bố với UI khi phù hợp.

### 19.4. Không tăng count hai lần khi retry

`$inc` là atomic trên một document nhưng **không idempotent** khi cùng tác vụ nghiệp vụ bị xử lý lại.

```text
Event REV1005 processed twice
-> count +2 dù chỉ có 1 review
```

Muốn đúng khi retry, cần unique review identity, processed-event deduplication hoặc transaction/protocol phù hợp.

### 19.5. Khi nào Computed Pattern đáng dùng?

Khi **reads của summary nhiều hơn updates** và computation raw tốn kém. Nếu summary được cập nhật 100.000 lần/giây còn UI chỉ xem một lần/ngày, tính trước từng write có thể không hợp lý; cân nhắc batch recompute.

## 20. Bucket Pattern: nhóm events theo lô bounded

Các sự kiện sensor/click/stock movements có thể rất nhiều. Một document cho mỗi event có ưu điểm update và index độc lập, nhưng có overhead lớn nếu hay đọc liên tục theo thời gian.

### 20.1. Bucket document minh họa

```javascript
{
  _id: "sensor-1:2026-11-14T10",
  sensorId: "sensor-1",
  bucketStart: ISODate("2026-11-14T10:00:00Z"),
  count: 3,
  measurements: [
    { ts: ISODate("2026-11-14T10:00:01Z"), value: 25.0 },
    { ts: ISODate("2026-11-14T10:00:02Z"), value: 25.2 },
    { ts: ISODate("2026-11-14T10:00:03Z"), value: 25.4 }
  ]
}
```

### 20.2. Mục tiêu

- Giảm số lượng documents so với một event/document.
- Cải thiện locality cho các truy vấn đọc nhiều events liền nhau.
- Có thể gộp metadata lặp lại ở bucket level.

### 20.3. Bounded bucket là bắt buộc

Không nhét mọi measurements của một sensor suốt 10 năm vào một bucket. Cần giới hạn theo:

- Thời gian (giờ/ngày).
- Số lượng entries.
- Kích thước BSON.
- Đặc tính query/reporting.

### 20.4. Rủi ro hot bucket

Nhiều writers ghi cùng sensor bucket có thể tranh chấp một document. Bucket size càng lớn không luôn càng tốt. Có thể phân thêm hash/sequence bucket hoặc giảm granular time window khi workload yêu cầu.

### 20.5. MongoDB Time Series collections

MongoDB có **native time series collections** để lưu chuỗi đo theo thời gian với cơ chế bucketing nội bộ; nó có những quy tắc riêng về writes/updates/deletes/indexes và version.

Nếu domain là time series, cần **đánh giá native time series** trước khi tự triển khai bucket pattern thủ công. Không mặc định tự làm buckets luôn nhanh hơn feature được tối ưu trong MongoDB.

## 21. Working set: dữ liệu “nóng” có nằm trong bộ nhớ không?

### 21.1. Working set là gì?

Working set gồm phần dữ liệu/index được truy cập tích cực trong một khoảng thời gian. Nếu nó lớn hơn memory/cache hiệu dụng, query có thể phải đọc nhiều từ disk.

Ví dụ:

```text
Hot catalog fields = 2 GiB
Hot indexes        = 1 GiB
Review full bodies = 80 GiB nhưng hiếm khi đọc
```

Giữ product summaries và indexes nóng nhỏ có thể giúp working set thuận lợi hơn so với thường xuyên fetch documents lớn chứa reviews lạnh.

### 21.2. Projection giúp gì?

```javascript
db.products.find(
  { category: "audio" },
  { name: 1, price: 1, thumbnail: 1 }
);
```

Projection giới hạn field trả về và có thể giảm **network payload**, nhưng không mặc nhiên đảm bảo MongoDB chỉ đọc đúng những bytes field đó từ storage.

Đặc biệt, nếu query không được **covered by index**, storage engine vẫn có thể cần FETCH document. Muốn kết luận disk/cache benefit phải đo query plan và working set thực.

### 21.3. Document splitting và network

Khi tách reviews, catalog query thường không truy cập review documents, giúp tách working sets. Nhưng trang detail phải lấy thêm review nếu cần; đây là trade-off đúng mục tiêu truy cập.

### 21.4. Compression không xóa giới hạn logical document

WiredTiger compression giảm physical storage, nhưng **giới hạn BSON 16 MiB** và chi phí truy cập/cập nhật document vẫn tồn tại. Không dùng tỉ lệ nén để hợp thức hóa mảng không giới hạn.

## 22. Read amplification và write amplification

### 22.1. Read amplification

Một yêu cầu UI đòi một product summary nhưng database phải:

- Đọc nhiều documents.
- Quét nhiều index entries.
- Join nhiều collections.
- Sort tập lớn.
- Fetch nhiều field không cần thiết.

thì read amplification tăng.

### 22.2. Write amplification

Một thay đổi nghiệp vụ nhỏ cần:

- Cập nhật nhiều bản sao denormalized.
- Chạm nhiều index entries.
- Ghi nhiều events/snapshots.
- Thực hiện transaction nhiều documents.
- Phát thêm writes cho các cache/summary.

thì write amplification tăng.

### 22.3. Một mô hình tư duy đơn giản

```text
Total work ≈
  readFrequency  * costPerRead
  +
  writeFrequency * costPerWrite
  +
  consistency/maintenance cost
```

Đây **không phải công thức chi phí chính xác**. Nó giúp ưu tiên đo:

- Nếu readFrequency lớn hơn writeFrequency rất nhiều, denormalization/computed fields có thể có lợi.
- Nếu writes cực kỳ nhiều, quá nhiều bản sao/indexes có thể gây áp lực.
- Nếu consistency chặt, chi phí phối hợp writes phải được tính.

### 22.4. Đừng tối ưu chỉ cho một endpoint

Một schema giúp `GET /products` giảm 5 ms nhưng khiến `POST /orders` chậm thêm 200 ms có thể là bước lùi nếu orders là critical path. SLO/business priority quan trọng hơn microbenchmark isolated.

## 23. Index thiết kế cùng query shape

### 23.1. Index phục vụ read paths

Ví dụ danh sách sản phẩm active, theo category, sort price:

```javascript
db.products.createIndex({
  category: 1,
  active: 1,
  price: 1,
  _id: 1
});

db.products.find(
  { category: "audio", active: true },
  { name: 1, price: 1, thumbnail: 1 }
).sort({
  price: 1,
  _id: 1
}).limit(20);
```

Không khẳng định index này là tối ưu với mọi dữ liệu: cần xem selectivity, histogram, sort, optional filters và kích thước index.

### 23.2. Index cho child collection

```javascript
db.productReviews.createIndex({
  productId: 1,
  createdAt: -1,
  _id: -1
});
```

Nếu thiếu `productId` index, query reviews của một product có thể scan tập reviews lớn.

### 23.3. Index trên trường hay thay đổi

Một update trường được index có thể phải thay đổi index entries. Nếu field `available` được cập nhật rất thường xuyên, không tạo 10 indexes có `available` chỉ vì nó tồn tại trong schema.

### 23.4. Partial index và TTL có mục tiêu

Nếu phần lớn products `archived=true` không cần xuất hiện trong search UI, có thể cân nhắc partial index cho active products:

```javascript
db.products.createIndex(
  { category: 1, price: 1 },
  {
    partialFilterExpression: { active: true }
  }
);
```

Query cần có điều kiện phù hợp để planner sử dụng partial index an toàn.

Nếu dữ liệu child có retention thời gian, TTL index có thể phù hợp **khi business cho phép xóa tự động**. TTL deletion là **bất đồng bộ**, không phải xóa đúng từng mili-giây; cần thiết kế data retention rõ.

### 23.5. Covered query

Nếu tất cả điều kiện filter/sort/projection có thể thỏa từ index theo quy tắc covered query, có thể tránh FETCH documents. Tuy nhiên index chứa nhiều fields cũng tốn storage/write cost.

Không chạy theo “covered bằng mọi giá” rồi tạo compound index dài cho từng biến thể endpoint.

## 24. Kiểm chứng bằng `explain("executionStats")`

### 24.1. Truy vấn danh sách

```javascript
db.products.find(
  { category: "audio", active: true },
  { _id: 1, name: 1, price: 1 }
).sort({
  price: 1,
  _id: 1
}).limit(20).explain("executionStats");
```

### 24.2. Các tín hiệu

| Metric/plan | Câu hỏi |
|---|---|
| `nReturned` | Có bao nhiêu document kết quả? |
| `totalKeysExamined` | Có bao nhiêu index entries được duyệt? |
| `totalDocsExamined` | Có bao nhiêu documents được kiểm tra? |
| `IXSCAN` | Có dùng index scan không? |
| `COLLSCAN` | Có scan collection không? |
| `FETCH` | Có phải tải document sau index không? |
| `SORT` hoặc sort stage | Có phải sort thêm ngoài index không? |
| `executionTimeMillis` | Ước lượng server execution time của thử nghiệm |

### 24.3. Cách đọc định lượng

Ví dụ hai query plans cùng `nReturned=20`:

```text
Plan A:
  keysExamined = 20
  docsExamined = 20

Plan B:
  keysExamined = 150000
  docsExamined = 100000
```

Plan B có nhiều công việc hơn cho query shape đó. Tuy nhiên **chưa đủ kết luận schema B luôn chậm hơn** nếu conditions/data/cache/index version khác nhau.

### 24.4. `explain()` không thay benchmark ứng dụng

`explain` có thể thay đổi execution/plan cache behavior và không mô tả mọi tác động network, driver decode, application merge, concurrency hay GC. Cần đo **end-to-end p95/p99 latency và throughput** dưới workload đại diện.

## 25. Mảng và multikey index: chi phí không chỉ là bytes

Mảng:

```javascript
{
  _id: "P1001",
  tags: ["audio", "bluetooth", "wireless"]
}
```

Index:

```javascript
db.products.createIndex({ tags: 1 });
```

MongoDB tạo **multikey index** khi index field chứa array, với index keys tương ứng phần tử. Mảng càng dài có thể ảnh hưởng kích thước/index maintenance.

### 25.1. Mảng tăng liên tục

Không dùng:

```javascript
db.products.updateOne(
  { _id: "P1001" },
  { $push: { allReviewIds: newReviewId } }
);
```

vô hạn khi product có hàng trăm nghìn reviews.

### 25.2. Giới hạn multikey compound

MongoDB có ràng buộc với **compound multikey index** khi document có nhiều indexed array fields. Không giả định có thể index tùy ý một compound index chứa hai array fields trong cùng document.

Khi schema tạo ra nhiều arrays lớn, cần xem cả **query patterns và index constraints**, không chỉ 16 MiB.

### 25.3. Bounded arrays vẫn hữu ích

Với `tags` tối đa vài chục mục ngắn, embedding có thể hợp lý. Đánh giá lượng dữ liệu, tần suất update và nhu cầu query.

## 26. Subset pagination: không tải cả mảng rồi cắt ở Java

Nếu reviews nằm collection riêng:

```javascript
db.productReviews.find(
  { productId: "P1001" },
  { rating: 1, comment: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 })
 .limit(20);
```

Không:

```javascript
// Chống chỉ định về hiệu năng nếu đọc toàn bộ reviews rất lớn.
const allReviews = db.productReviews.find({
  productId: "P1001"
}).toArray();

const page = allReviews.slice(0, 20);
```

### 26.1. Offset vs keyset

Với page sâu, `skip` lớn có thể đắt. Keyset pagination:

```javascript
const lastCreatedAt = ISODate("2026-10-01T10:00:00Z");
const lastId = "REV5001";

db.productReviews.find({
  productId: "P1001",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
}).sort({
  createdAt: -1,
  _id: -1
}).limit(20);
```

Token/page cursor phải gắn với cùng filter/sort. Khi thay bộ lọc hoặc dữ liệu thay đổi, không tự đảm bảo snapshot.

### 26.2. Thứ tự ổn định

Nếu chỉ sort theo `createdAt`, nhiều reviews có cùng timestamp tạo tie. Thêm `_id` giúp xác định thứ tự tốt hơn.

### 26.3. Nếu review edits ảnh hưởng thứ tự

Chọn sort key theo business semantics: `createdAt` thường bất biến; `updatedAt` thay đổi theo edit có thể làm thứ tự page động hơn.

## 27. Projection, `$slice` và embedded bounded subsets

Nếu một document có mảng nhỏ và UI chỉ cần vài phần tử:

```javascript
db.products.findOne(
  { _id: "P1001" },
  {
    name: 1,
    ratingSummary: 1,
    featuredReviews: { $slice: 3 }
  }
);
```

`$slice` trong projection giới hạn phần tử array trả về; nó có thể giảm payload, nhưng **không sửa vấn đề mảng nguồn cứ tăng vô hạn**.

### 27.1. Khi nào dùng `$slice`?

- Mảng có giới hạn và cần một phần nhỏ.
- Muốn tránh gửi thừa dữ liệu qua network.
- Không muốn query thêm collection khác chỉ cho vài field.

### 27.2. Khi nào không đủ?

Array hàng trăm nghìn phần tử, updated liên tục, chạm 16 MiB và index lớn: chỉ thêm `$slice:3` không giải quyết root cause.

## 28. Computed value: precompute khi reads nhiều, batch khi writes nhiều

Một metric `weeklySales`:

```javascript
{
  productId: "P1001",
  weekStart: ISODate("2026-11-09T00:00:00Z"),
  unitsSold: 583,
  revenue: NumberLong("519000000")
}
```

### 28.1. Cập nhật realtime

Phù hợp khi:

- UI cần gần realtime.
- Tốc độ ghi nằm trong khả năng cập nhật aggregate.
- Có idempotency để tránh double count.

### 28.2. Batch recompute

Phù hợp khi:

- Dashboard chỉ xem mỗi giờ/ngày.
- Nguồn events lớn.
- Chi phí update aggregate từng event quá cao.

### 28.3. Hybrid

```text
Baseline snapshot at 00:00
  + incremental events since 00:00
  = displayed near-real-time metric
```

Như vậy giảm lượng recompute dài hạn mà vẫn đáp ứng độ mới cần thiết, nhưng phức tạp hơn và đòi xử lý duplicate/late events.

### 28.4. Aggregation materialization

MongoDB `$merge`/`$out` có thể dùng để ghi aggregation results vào collection phục vụ đọc, nhưng:

- `$out` và `$merge` có semantics ghi khác nhau.
- Khi dùng `$merge`, những document không còn khớp nguồn **không tự động biến mất**.
- Cần xử lý consistency, refresh schedule và retry.

Không thay summary bằng vật liệu hóa batch mà bỏ qua stale rows.

## 29. Denormalization và bài toán consistency

### 29.1. Một giá trị được copy sang nhiều documents

Ví dụ brand name:

```text
brands:
  B1 -> "Nova Audio"

products:
  P1 -> brandName="Nova Audio"
  P2 -> brandName="Nova Audio"
  P3 -> brandName="Nova Audio"
```

Khi đổi tên brand, cập nhật một `brands` document không tự cập nhật ba `products`.

### 29.2. Chiến lược đồng bộ

**Synchronous updates:** trong một transaction hoặc workflow có kiểm soát. Hợp lý khi số documents ít và invariant chặt, nhưng write latency/cost tăng.

**Asynchronous events:** update source-of-truth rồi phát event; worker cập nhật các bản sao theo eventual consistency.

**Periodic reconciliation:** chạy job đối chiếu những bản sao lệch, hữu ích để sửa drift sau retry/hạ tầng lỗi.

**Read-time join:** không copy field, lookup từ source khi cần dữ liệu mới nhất.

### 29.3. Cập nhật hàng triệu denormalized copies

Nếu field thay đổi thường xuyên và xuất hiện ở 10 triệu documents, mọi lần đổi có thể tạo fan-out writes rất lớn. Nên hạn chế copy những field có:

- Tần suất thay đổi cao.
- Fan-out lớn.
- Yêu cầu đồng bộ chặt.

Trường copy nên ưu tiên **ổn định**, **nhỏ**, **được đọc nhiều**, hoặc chấp nhận lệch tạm thời.

### 29.4. Version và reconciliation

Một phương án:

```javascript
{
  productId: "P1001",
  brandNameCache: "Nova Audio",
  brandVersion: 13
}
```

Khi sự kiện mới tới, worker so version để tránh event cũ ghi đè event mới. Nhưng version phải do source-of-truth cấp một cách nhất quán; không tự dùng Date.now() ở các node rồi giả định timestamp luôn có thứ tự chính xác.

## 30. Thay đổi tần suất cập nhật theo vòng đời

Một document có thể có các giai đoạn:

```text
Order created     -> frequent state transitions
Order completed   -> rare changes
Order archived    -> read-only audit/analytics
```

### 30.1. Active vs historical collections

Trong một số hệ thống, có thể tách:

```text
activeOrders:
  orders đang xử lý, query/write thường xuyên

completedOrders:
  orders đã hoàn tất, hiếm update, retention khác
```

### 30.2. Đánh đổi

Ưu điểm: active working set nhỏ hơn, indexes theo workload riêng.

Nhược điểm:

- Query xuyên hai collections phức tạp hơn.
- Move giữa collections không tự atomic.
- Cần bảo toàn identity, audit trail và references.
- Cần quy trình tránh duplicate/missing khi archival job retry.

Không chuyển order sang archive chỉ vì nó cũ; phải dựa vào lifecycle và yêu cầu truy xuất.

### 30.3. TTL không đồng nghĩa archive

TTL **xóa** documents khi hết hạn theo cơ chế bất đồng bộ. Nếu cần giữ dữ liệu kiểm toán, không tạo TTL index rồi coi đó là “archive”.

## 31. Attribute Pattern và dữ liệu field đa dạng

Catalog có nhiều loại sản phẩm:

```javascript
// Headphones
{ driverSizeMm: 40, batteryHours: 25 }

// Keyboard
{ layout: "US", switchType: "mechanical" }

// Monitor
{ resolution: "4K", refreshHz: 144 }
```

### 31.1. Dynamic fields

MongoDB có thể lưu từng product với fields khác nhau. Tuy nhiên nếu muốn search/filter theo hàng trăm attributes, tạo index cho từng field có thể phức tạp.

### 31.2. Attribute Pattern

```javascript
{
  _id: "P1001",
  category: "audio",
  attributes: [
    { key: "batteryHours", valueNum: 25 },
    { key: "driverSizeMm", valueNum: 40 },
    { key: "color", valueStr: "black" }
  ]
}
```

Có thể phù hợp nếu UI tìm kiếm những attributes linh hoạt, nhưng:

- Mảng attributes tạo multikey indexing costs.
- Query kết hợp key/value cần dùng `$elemMatch` đúng.
- Number và string có semantics khác nhau.
- Không nên chuyển mọi field ổn định sang dạng key/value chỉ vì linh hoạt.

### 31.3. Query đúng theo phần tử mảng

```javascript
db.products.find({
  attributes: {
    $elemMatch: {
      key: "batteryHours",
      valueNum: { $gte: 20 }
    }
  }
});
```

`$elemMatch` đảm bảo điều kiện key và value áp trên **cùng một phần tử** array. Nếu dùng hai dot-path predicates không kiểm soát, hai điều kiện có thể match hai elements khác nhau.

## 32. Polymorphic Pattern: nhiều kiểu document trong một collection

Một collection `activities` có:

```javascript
{
  _id: "ACT1",
  kind: "PURCHASE",
  userId: "U1",
  amount: 890000
}

{
  _id: "ACT2",
  kind: "REVIEW",
  userId: "U1",
  productId: "P1001",
  rating: 5
}
```

Ưu điểm: feed hoạt động chung có thể query theo user/time.

Nhược điểm:

- Query/index mỗi subtype khác nhau.
- Validation phức tạp hơn.
- Một subtype có write volume rất lớn có thể chi phối collection/index.
- TTL/retention có thể khác nhau.

### 32.1. Khi nào tách collection?

Nếu purchase và review có lifecycle, retention, security, hot indexes và throughput khác hẳn, tách collection có thể tốt hơn. Không bắt buộc “một collection cho mọi event” hoặc “một collection cho mỗi subtype” trong mọi workload.

## 33. Time Series vs document thường

MongoDB có **time series collections** phù hợp với measurements có timestamp và metadata (ví dụ deviceId). Chúng dùng tổ chức lưu trữ theo thời gian và có các khả năng/index constraints khác document collection thường.

### 33.1. Ví dụ tạo collection time series

```javascript
db.createCollection("deviceReadings", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "device",
    granularity: "minutes"
  }
});
```

Ví dụ document:

```javascript
{
  measuredAt: ISODate("2026-11-14T04:00:00Z"),
  device: { id: "SENSOR1", site: "HN-A" },
  temperature: 24.5
}
```

### 33.2. Cần phù hợp update patterns

Nếu nghiệp vụ liên tục sửa các measurements cũ theo ID, một time series collection có thể có ràng buộc update/delete khác với collection thường. Không chọn chỉ vì dữ liệu “có timestamp”; phải xác minh feature/version và truy vấn thực.

### 33.3. Khi có query theo thời gian

Một workload:

```text
Tìm 6 giờ cuối của sensor S1
Tính average per 5 minutes
Xóa dữ liệu sau 90 ngày
```

phù hợp để đánh giá native time series + retention. Một workload cần mutable business events theo trạng thái có thể cần collection thông thường.

## 34. Hotspot: một document được nhiều writers cùng cập nhật

Ví dụ counter toàn cầu:

```javascript
{
  _id: "GLOBAL",
  totalPageViews: NumberLong("900000000")
}
```

Mỗi page view gọi:

```javascript
db.counters.updateOne(
  { _id: "GLOBAL" },
  { $inc: { totalPageViews: 1 } }
);
```

`$inc` là atomic, nhưng tất cả requests cùng chạm một document có thể tạo hot key/contestion.

### 34.1. Sharded/striped counters

Một giải pháp nếu business cho phép:

```javascript
// counters
{ _id: "views:00", count: NumberLong("1000") }
{ _id: "views:01", count: NumberLong("1001") }
{ _id: "views:02", count: NumberLong("999") }
```

Mỗi write chọn một shard counter; read cộng các counters để tính tổng.

### 34.2. Trade-off

- Write contention giảm khi phân tán.
- Read cần cộng nhiều docs.
- Nếu tổng phải luôn chính xác trong một transaction và đọc tức thời, complexity tăng.
- Nếu dùng random assignment, phải đảm bảo retry không làm double count.
- Với MongoDB sharded deployment, cần xem **shard key distribution** và balancing; sharding không tự giải quyết hot document có cùng shard key.

### 34.3. Không micro-optimize sớm

Nếu counter chỉ tăng 10 lần/phút, một document `$inc` có thể là thiết kế đơn giản và đúng. Chỉ phân mảnh khi có bằng chứng throughput/latency contention.

## 35. Sharding và mô hình document

### 35.1. Shard key gắn với access pattern

Một collection orders query chủ yếu theo `tenantId` và `orderId`:

```javascript
{ tenantId: "T01", orderId: "O1001" }
```

Chọn shard key cần xem:

- Query routing: query có shard key không?
- Cardinality, skew và monotonically increasing behavior.
- Write distribution.
- Hot tenants và jumbo chunks.
- Unique indexes và constraints.
- Resharding cost.

### 35.2. Schema và shard key phải thiết kế cùng nhau

Nếu tenant ID chỉ nằm trong parent document nhưng child reviews không có tenantId và query thường phải lọc tenant, có thể cần cân nhắc lưu tenantId ở child để giúp routing/authorization.

Ví dụ:

```javascript
{
  _id: "REV5001",
  tenantId: "T01",
  productId: "P1001",
  rating: 5
}
```

Nhưng đây là **denormalization về tenant identity**; cần đảm bảo nó được gán từ authenticated/authoritative source và không được client tự thay.

### 35.3. Không giả định `$lookup` sẽ luôn cùng shard

Trong sharded clusters, `$lookup` có khả năng và chi phí tùy topology, shard keys, indexes và version. Đo thực tế thay vì coi join là miễn phí.

### 35.4. Một document không thể được “chia nhỏ giữa shards” tự động

Sharding phân bố **documents**, không chia một document 20 MiB thành hai nửa để vượt giới hạn BSON. Nếu document lớn vì mảng không giới hạn, phải đổi schema, không chỉ thêm shards.

## 36. Mô hình dữ liệu và cache ở tầng ứng dụng

Một product summary được đọc hàng chục nghìn lần/phút nhưng thay đổi ít có thể cache ở ứng dụng/CDN/Redis tùy kiến trúc.

### 36.1. Cache là một bản sao denormalized

```text
MongoDB products (source of truth)
             |
             v
         API cache
             |
             v
           Client
```

Cache hit giảm database reads, nhưng có:

- TTL/staleness.
- Invalidation khi product đổi.
- Cache stampede.
- Quyền và tenant isolation.
- Rủi ro stale price/inventory.

### 36.2. Không cache tồn kho như dữ liệu quyết định giao dịch

Trang listing có thể hiển thị “còn hàng” gần realtime, nhưng order reservation phải kiểm tra **inventory authoritative** khi ghi. Không giảm available từ cache client rồi coi đủ để đặt đơn.

### 36.3. Data model và cache phải có cùng consistency policy

Nếu product price đổi, hệ thống cần biết:

- MongoDB authoritative value.
- Denormalized search card.
- API/cache layer.
- CDN/edge snapshot.

Một trong các lớp này trễ có thể gây UI hiển thị sai giá. Tối ưu schema không thể tách rời vòng đời bản sao.

## 37. Thiết kế mô hình catalog hoàn chỉnh

### 37.1. Product document

```javascript
{
  _id: "P1001",
  tenantId: "T01",
  sku: "SKU-1001",
  name: "Tai nghe Bluetooth",
  category: "audio",
  brandId: "B1",
  price: 890000,
  currency: "VND",
  thumbnail: "/images/p1001.jpg",
  description: "Mo ta chi tiet",
  featuredReviews: [
    { reviewId: "R1", rating: 5, excerpt: "Rat tot" }
  ],
  ratingSummary: {
    count: 824,
    sum: 3884,
    computedAt: ISODate("2026-11-14T04:00:00Z")
  },
  contentVersion: NumberLong("17"),
  updatedAt: ISODate("2026-11-14T04:00:00Z")
}
```

### 37.2. Inventory document

```javascript
{
  _id: "P1001",
  tenantId: "T01",
  available: 127,
  reserved: 12,
  version: NumberLong("42"),
  updatedAt: ISODate("2026-11-14T04:00:00Z")
}
```

### 37.3. Review documents

```javascript
{
  _id: "R1",
  tenantId: "T01",
  productId: "P1001",
  userId: "U20",
  rating: 5,
  comment: "Rat tot khi nghe nhac",
  createdAt: ISODate("2026-11-01T09:00:00Z")
}
```

### 37.4. Stock movement documents

```javascript
{
  _id: "M100001",
  tenantId: "T01",
  productId: "P1001",
  operationId: "OP90001",
  delta: -1,
  reason: "ORDER_RESERVATION",
  createdAt: ISODate("2026-11-14T04:00:00Z")
}
```

Đây là **event/history**, không thay thế điều kiện atomic khi reserve inventory.

### 37.5. Indexes đề xuất theo query

```javascript
db.products.createIndex(
  { tenantId: 1, category: 1, price: 1, _id: 1 }
);

db.productReviews.createIndex(
  { tenantId: 1, productId: 1, createdAt: -1, _id: -1 }
);

db.stockMovements.createIndex(
  { tenantId: 1, productId: 1, createdAt: -1 }
);

db.stockMovements.createIndex(
  { tenantId: 1, operationId: 1 },
  { unique: true }
);
```

Các indexes là **gợi ý cho các query đã mô tả**, không phải một bộ cấu hình cần tạo nguyên trên mọi project. Cần xem selectivity, existing indexes, sharding, unique constraints và chi phí writes.

### 37.6. Truy vấn trang detail

```javascript
const tenantId = "T01";
const productId = "P1001";

const product = db.products.findOne(
  { _id: productId, tenantId },
  {
    name: 1,
    price: 1,
    description: 1,
    featuredReviews: 1,
    ratingSummary: 1
  }
);

const inventory = db.productInventory.findOne(
  { _id: productId, tenantId },
  { available: 1, reserved: 1 }
);

printjson({ product, inventory });
```

Trong ứng dụng thật, tenantId phải đến từ authenticated context, không phải một literal do client tự chọn.

### 37.7. Không kỳ vọng hai reads có chung snapshot

Hai `findOne` riêng có thể thấy product và inventory ở hai thời điểm khác nhau. Nếu nghiệp vụ cần snapshot nhất quán across documents, phải thiết kế transaction/session/read concern theo yêu cầu.

Đối với UI catalog, eventual consistency có thể chấp nhận; đối với quyết định giữ tồn kho, phải có atomic business check ở write path.

## 38. `$lookup` khi cần compose trong database

```javascript
db.products.aggregate([
  {
    $match: {
      _id: "P1001",
      tenantId: "T01"
    }
  },
  {
    $lookup: {
      from: "productInventory",
      localField: "_id",
      foreignField: "_id",
      as: "inventory"
    }
  },
  {
    $set: {
      inventory: { $first: "$inventory" }
    }
  },
  {
    $project: {
      name: 1,
      price: 1,
      inventory: 1
    }
  }
]);
```

### 38.1. Security và tenant

Ví dụ `$lookup` chỉ join theo `_id` vốn duy nhất ở collection đích; nếu id không global unique hoặc schema đa tenant dùng composite keys, phải join theo **cả tenantId** để tránh trộn dữ liệu. Không coi `$match tenantId` ở product đầu vào là bảo vệ mọi join tự động.

### 38.2. Hiệu năng

`$lookup` không phải “luôn chậm”, nhưng cost phụ thuộc:

- Số documents phía trái.
- Index trên foreign field.
- Cardinality kết quả.
- Pipeline filters, shard topology.
- Memory/working set.

Đo aggregation explain và end-to-end latency. Với màn hình 20 products, có thể dùng batch query inventory theo IDs thay vì 20 independent round trips.

## 39. Batch reads tránh N+1

Một anti-pattern:

```javascript
const products = db.products.find({ category: "audio" })
  .limit(20).toArray();

for (const product of products) {
  const inventory = db.productInventory.findOne({
    _id: product._id
  });
  // 20 round trips riêng nếu chạy tuần tự.
}
```

Thay thế bằng batch:

```javascript
const productIds = products.map(p => p._id);

const inventories = db.productInventory.find({
  _id: { $in: productIds }
}).toArray();

const inventoryByProductId = new Map(
  inventories.map(inv => [inv._id, inv])
);

const cards = products.map(p => ({
  product: p,
  inventory: inventoryByProductId.get(p._id) ?? null
}));

printjson(cards);
```

### 39.1. Cần bảo vệ tenant

Trong multi-tenant application, batch query cũng phải giới hạn `tenantId` theo context và ids hợp lệ; không dùng `$in` gồm IDs bất kỳ client gửi để bỏ qua authorization.

### 39.2. Số ID quá lớn

`$in` với hàng chục nghìn giá trị có thể tốn chi phí; batch pagination, server-side join hoặc lựa chọn khác cần được benchmark.

## 40. Java Sync Driver: cập nhật hot inventory an toàn

Ví dụ Java dùng MongoDB Sync Driver; URI lấy từ environment/secret store. Đoạn code giả định collection đã tồn tại và sản phẩm đã được seed.

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.conversions.Bson;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Filters.gte;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.inc;
import static com.mongodb.client.model.Updates.currentDate;

public class InventoryReservation364 {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> inventory = client
                .getDatabase("catalog_lab_364")
                .getCollection("productInventory");

            String productId = "P1001";
            String tenantId = "T01";
            long qty = 1;

            Bson filter = and(
                eq("_id", productId),
                eq("tenantId", tenantId),
                gte("available", qty)
            );

            Bson update = combine(
                inc("available", -qty),
                inc("reserved", qty),
                inc("version", 1L),
                currentDate("updatedAt")
            );

            UpdateResult result = inventory.updateOne(filter, update);

            if (result.getModifiedCount() == 1L) {
                System.out.println("Reserved successfully");
            } else {
                System.out.println("Not enough inventory or not found");
            }
        }
    }
}
```

### 40.1. Sửa domain logic khi qty không hợp lệ

Code production phải validate `qty > 0`, không vượt giới hạn, authorization cho tenant/product và retry/idempotency của lệnh đặt hàng. Nếu `qty` âm, logic ví dụ có thể chuyển thành cộng hàng sai.

### 40.2. Retry của nghiệp vụ khác driver retryable writes

Ngay cả khi driver hỗ trợ retryable writes theo deployment/session, một request đặt hàng nghiệp vụ bị gửi lại vẫn có thể tạo một **reservation mới** nếu API không có idempotency key.

Để chống double reservation, cần request ID/operation ID duy nhất và state machine/transaction hoặc một protocol phù hợp, không chỉ lặp `updateOne()`.

### 40.3. Tách inventory để phục vụ writes

Document inventory nhỏ, chỉ giữ counters cần thiết; cập nhật không chạm product description hoặc reviews. Nhưng đọc product + inventory vẫn cần compose và schema tách này **không tự bảo đảm multi-document snapshot**.

## 41. Java: batch fetch hai collections

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import java.util.List;
import java.util.ArrayList;
import java.util.Map;
import java.util.HashMap;

// Giả định đã có hai MongoCollection<Document> products, inventory.
// Các IDs và tenantId lấy từ query/authorization context hợp lệ.
String tenantId = "T01";

List<Document> productPage = products
    .find(Filters.and(
        Filters.eq("tenantId", tenantId),
        Filters.eq("category", "audio")
    ))
    .limit(20)
    .into(new ArrayList<>());

List<String> ids = new ArrayList<>();
for (Document p : productPage) {
    ids.add(p.getString("_id"));
}

List<Document> inventoryRows = ids.isEmpty()
    ? new ArrayList<>()
    : inventory.find(Filters.and(
        Filters.eq("tenantId", tenantId),
        Filters.in("_id", ids)
    )).into(new ArrayList<>());

Map<String, Document> byId = new HashMap<>();
for (Document inv : inventoryRows) {
    byId.put(inv.getString("_id"), inv);
}

for (Document p : productPage) {
    Document inv = byId.get(p.getString("_id"));
    System.out.println(
        p.getString("name") + ": " +
        (inv == null ? "unknown" : inv.get("available"))
    );
}
```

Snippet này chỉ minh họa batch composition và dùng lại biến collections đã tạo. Với endpoint thật cần sort/pagination, projection, timeouts, exception handling và kiểm tra tính nhất quán.

## 42. Migration: từ một document lớn sang mô hình hybrid

Giả sử schema cũ:

```javascript
{
  _id: "P1001",
  name: "...",
  inventory: { available: 100 },
  reviews: [ /* all reviews */ ]
}
```

Schema mới:

```text
products
productInventory
productReviews
```

### 42.1. Không chuyển đổi bằng cách xóa và tạo lại production ngay

Không nên:

```javascript
db.products.drop();
// Recreate from an unverified script.
```

Lệnh này nguy hiểm và thường không cần thiết cho online schema migration.

### 42.2. Kế hoạch expand–migrate–contract

**Phase 1 — Expand:** tạo collections/indexes mới; bổ sung code đọc hỗ trợ schema cũ/mới.

**Phase 2 — Backfill:** trích inventory và reviews của documents cũ sang collections mới; dùng idempotent upserts/IDs ổn định.

**Phase 3 — Dual-write hoặc change capture:** trong khoảng chuyển tiếp, đảm bảo updates mới được áp vào cả nguồn cũ và đích mới theo protocol.

**Phase 4 — Verify:** so counts, samples, invariants, retry gaps và business reads.

**Phase 5 — Switch reads:** chuyển dần traffic sang schema mới; monitor latency, errors, reconciliation drift.

**Phase 6 — Contract:** sau khi đạt tiêu chí ổn định và có rollback plan, xóa những fields/copies cũ bằng quy trình được duyệt.

### 42.3. Dual-write không tự atomic

Hai lệnh:

```javascript
db.products.updateOne(...);
db.productInventory.updateOne(...);
```

có thể thành công/thất bại độc lập. Nếu cần atomic, dùng transaction hoặc chuyển đổi qua outbox/event protocol với idempotency và reconciliation.

### 42.4. Backfill với ID ổn định

Ví dụ review ID nên được tạo từ identity nguồn đã có hoặc mapping deterministic, tránh mỗi lần chạy backfill lại tạo một bản sao mới.

Nếu dữ liệu cũ là mảng reviews không có IDs, cần xác định cách tạo IDs một lần, lưu mapping và xử lý thay đổi xen giữa.

### 42.5. Không bỏ qua deletes

Trong migration, rất dễ chỉ backfill create/update nhưng quên deletes, khiến collection mới vẫn chứa review đã xóa. Cần mô tả delete propagation và retention cho cả hai model.

## 43. Versioning schema và compatibility

Một số hệ thống lưu:

```javascript
{
  _id: "P1001",
  schemaVersion: 2,
  name: "Tai nghe Bluetooth",
  inventoryRef: "P1001"
}
```

### 43.1. Vai trò

- Phân biệt những version đã backfill.
- Hỗ trợ code đọc trong thời kỳ rolling deployment.
- Dễ thống kê tiến độ migration.

### 43.2. Không cập nhật version trước khi dữ liệu sẵn sàng

Nếu đánh `schemaVersion: 2` trước khi inventory đã chuyển thành công, code mới có thể đọc thiếu. Version marker phải phản ánh **trạng thái chuyển đổi được xác nhận**, hoặc phải có trạng thái migration chi tiết hơn.

### 43.3. Schema validation

MongoDB có `$jsonSchema` để kiểm tra document shape:

```javascript
db.createCollection("productInventory", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "tenantId", "available", "reserved"
      ],
      properties: {
        tenantId: { bsonType: "string" },
        available: {
          bsonType: ["int", "long"],
          minimum: 0
        },
        reserved: {
          bsonType: ["int", "long"],
          minimum: 0
        }
      }
    }
  }
});
```

Validation giúp ngăn một số trạng thái sai kiểu/giá trị nhưng không thay transaction, optimistic concurrency hoặc authorization.

## 44. Chuẩn bị benchmark trước/sau

### 44.1. Đừng benchmark trên 10 products

Một dataset nhỏ không phản ánh:

- Working set lớn hơn RAM/cache.
- Hot product có 100.000 reviews.
- Phân phối read/write theo peak.
- Disk/cache pressure.
- Multi-tenant skew.
- Replication lag khi write bursts.

### 44.2. Workload benchmark cần đại diện

Ví dụ:

```text
60% GET product list
15% GET product detail
10% GET reviews page
10% inventory updates
 5% create/update reviews
```

Đây là mix minh họa. Cần lấy từ thực tế, test cả steady-state, peak và burst.

### 44.3. Đo trước/sau

| Metric | Trước | Sau | Mục tiêu |
|---|---:|---:|---|
| p95 catalog query | đo | đo | Giảm/không vượt SLO |
| p95 product detail | đo | đo | Không tăng quá mức |
| p95 inventory write | đo | đo | Giảm |
| Write throughput | đo | đo | Tăng |
| CPU/disk IOPS | đo | đo | Không saturate |
| WiredTiger cache pressure | đo | đo | Giảm hoặc ổn định |
| MongoDB read/write ops | đo | đo | Trong capacity |
| Avg/p99 document BSON size | đo | đo | Bounded |
| Index size/growth | đo | đo | Có kiểm soát |
| Replication lag | đo | đo | Không tăng vượt SLO |
| Consistency drift | đo | đo | Trong giới hạn |

### 44.4. Định nghĩa thành công bằng business SLO

Nếu tối ưu làm p95 inventory write tốt hơn nhưng rate stale product price tăng, đây có thể là **regression nghiệp vụ**. Benchmark cần gồm latency, correctness và consistency.

### 44.5. Rollback

Migration thất bại phải có đường quay lại khi dữ liệu đã phát sinh trên schema mới. Một bản backup trước migration không đủ nếu đã nhận orders mới sau thời điểm đó.

Phải thiết kế back-sync, event replay hoặc compatibility layer theo mức độ cần.

## 45. Chẩn đoán hiệu năng theo từng triệu chứng

| Triệu chứng | Giả thuyết | Kiểm tra |
|---|---|---|
| Product detail chậm | Document lớn hoặc join nặng | Document size, projection, explain |
| Inventory update p99 cao | Hot key, write contention, indexes | Write rate theo ID, conflicts, profiler |
| Disk reads cao | Working set vượt cache | Cache eviction, IOPS, pages read |
| Review page chậm | Thiếu compound index, deep skip | explain, scan counts |
| Product document tăng mãi | Array không giới hạn | BSON size distribution |
| Summary rating sai | Double-count, missed event | Reconciliation, idempotency |
| Writes tạo replication lag | Write/index/oplog amplification | Oplog GB/hour, lag, disk |
| CPU tăng sau thêm index | Index maintenance và query mix đổi | Index stats/write metrics |
| Multi-tenant tenant lớn chậm | Skew/hot tenant | Per-tenant cardinality/throughput |
| Migration gây reads thiếu | Backfill/deletes/version chưa đồng bộ | Compare old/new source data |

**Không suy nguyên nhân chỉ từ triệu chứng.** Đọc query plan, application traces, metrics và dữ liệu lịch sử trước khi đổi schema.

## 46. Các anti-pattern thường gặp

| Anti-pattern | Hệ quả | Cách xử lý |
|---|---|---|
| Nhúng array không giới hạn | Chạm 16 MiB, update/index tốn | Child collection và phân trang |
| Tách mọi trường thành collection riêng | Nhiều round trips, phức tạp | Embed bounded data đọc cùng |
| Nhúng inventory ghi nóng vào product lớn | Hot document/working-set pressure | Đánh giá tách hot data |
| Lưu 200.000 review IDs trong product | Parent vẫn tăng vô hạn | Foreign key ở reviews |
| Cache product price nhưng không invalidation | Hiển thị giá cũ | Version/event/cache policy |
| Tự tính rating từ toàn bộ reviews mỗi request | Aggregation quá tốn | Computed summary |
| Increment summary bất chấp retry | Double count | Idempotency + reconciliation |
| Copy field live sang triệu documents | Fan-out writes | Reference hoặc controlled denormalization |
| Chỉ lưu ID trong order không lưu historical price | Hóa đơn thay theo catalog | Embed immutable snapshot |
| Bỏ toàn bộ references vì “MongoDB không có join” | Schema khó quản lý | `$lookup` có index, benchmark |
| Nhiều indexes trên field cập nhật liên tục | Write amplification | Index theo query thực |
| Projection rồi coi chắc chắn giảm disk reads | Vẫn có thể FETCH document | Dùng explain và metrics |
| Query reviews bằng `toArray()` toàn bộ | Băng thông/bộ nhớ lớn | Pagination ở server |
| Dùng `skip` cực sâu | Nhiều vị trí bị bỏ | Keyset pagination |
| Tách data qua nhiều docs mà đòi atomic tự động | Inconsistent writes | Transaction/coordination |
| Coi `$inc` tự idempotent | Retry gây double increment | Unique operation IDs |
| TTL trên dữ liệu cần audit | Xóa bản ghi không mong muốn | Retention/lifecycle design |
| Minimize size mà bỏ qua update frequency | Hot key vẫn chậm | Đo workload và contention |
| Chỉ tối ưu average, bỏ p99 outliers | Tail latency/size rủi ro | Phân tích distribution |
| Sharding để vượt 16 MiB document | Không giải quyết | Chia logical document |
| Tự xây bucket time series không kiểm tra native feature | Phức tạp không cần | Đánh giá time series collection |
| Migrate trực tiếp bằng drop/recreate | Nguy cơ mất dữ liệu/downtime | Expand–migrate–contract |
| Không backfill deletes | Dữ liệu mới bị stale | Delete propagation |
| Chỉ đo `explain` một query | Không phản ánh ứng dụng | Load test full workload |
| Tối ưu reads nhưng tăng write latency nghiêm trọng | Regression toàn hệ thống | Weighted SLO/throughput review |

## 47. Bài tập thực hành

### Bài 1 — Lập access-pattern matrix

Cho hệ thống bán sách có `books`, `authors`, `inventory`, `reviews`, `orders`. Hãy mô tả ít nhất tám thao tác đọc/ghi với tần suất, field cần, độ trễ mục tiêu, mức nhất quán.

### Bài 2 — Embed hay reference?

Một user có 3 địa chỉ giao hàng và mỗi địa chỉ thường đọc cùng profile. Đề xuất schema, nêu điều kiện nào khiến bạn chuyển sang collection `userAddresses` riêng.

### Bài 3 — Reviews tăng lớn

Một sản phẩm có trung bình 8 reviews nhưng tối đa 250.000. So sánh embed toàn bộ, reference toàn bộ và hybrid featured subset. Đánh giá 16 MiB và update patterns.

### Bài 4 — Trường nóng và trường lạnh

Product description cập nhật 1 lần/tháng, inventory 20.000 lần/giờ, rating 200 lần/giờ. Hãy đề xuất boundaries và những phép đo cần làm trước khi tách.

### Bài 5 — Atomic reservation

Viết `updateOne()` chỉ giảm `available` khi đủ số lượng, đồng thời tăng `reserved`. Vì sao read-then-update dễ race?

### Bài 6 — Many-to-many

Thiết kế collection favorites cho nhiều users và products, unique index ngăn duplicate, query list theo user có thứ tự.

### Bài 7 — Historical snapshots

Một order được tạo khi product giá 890.000, tháng sau product giá 990.000. Trong order nên hiển thị giá nào? Phân biệt historical snapshot với live denormalized cache.

### Bài 8 — Extended Reference

Danh sách đơn hàng cần product name/brand, nhưng product metadata ít đổi. Thiết kế read model và kế hoạch đồng bộ khi brand được đổi tên.

### Bài 9 — Computed Pattern

Tính rating `count/sum/average` từ reviews. So sánh recompute mỗi read, update summary ngay trên mỗi event và batch. Hãy giải thích duplicate/retry.

### Bài 10 — Outlier Pattern

Một số users có 100.000 activities, phần lớn dưới 20. Thiết kế schema không để outliers tạo array khổng lồ; nêu cách API xử lý trường hợp đặc biệt.

### Bài 11 — Bucket Pattern

Sensor gửi 5 events/giây. Đề xuất bucket theo phút/giờ với giới hạn số entries. Nếu một sensor có 100 writers đồng thời, rủi ro gì?

### Bài 12 — Time series

So sánh native time series collection và bucket tự làm với workload đọc theo sensor trong khoảng thời gian, retention 90 ngày, late writes.

### Bài 13 — Index và update

Bạn có 5 indexes chứa field `available`, trong khi query tồn kho chủ yếu theo `_id`. Kiểm tra chi phí và đề xuất cách giảm write amplification mà vẫn đáp ứng query cần thiết.

### Bài 14 — `explain`

Query A trả 20 docs, duyệt 25 keys/20 docs. Query B trả 20 docs, duyệt 100.000 keys/70.000 docs. Nêu các tín hiệu cần điều tra và tại sao chưa đủ để kết luận về toàn hệ thống.

### Bài 15 — Projection

Một document lớn 1 MiB, query chỉ project `name` và `price`. Vì sao projection không bảo đảm chỉ đọc vài bytes từ storage? Khi nào covered query giúp?

### Bài 16 — Keyset pagination

Viết query trang tiếp theo của reviews theo `createdAt desc, _id desc`. Giải thích tie-breaker và khi dữ liệu đổi giữa các trang.

### Bài 17 — Schema polymorphism

Một collection lưu purchase và review events. Nêu điều kiện nên giữ chung và điều kiện nên tách dựa trên index, retention, quyền và write volume.

### Bài 18 — Shard key

Một ứng dụng đa tenant chủ yếu query orders theo `tenantId`, có một tenant chiếm 50% writes. Những rủi ro skew/hotspot nào phải khảo sát khi chọn shard key?

### Bài 19 — Hot counter

Một counter toàn cầu được cập nhật 10.000 lần/giây. So sánh một document `$inc`, striped counters và batch aggregation. Hãy giải thích trade-off giữa write throughput và exact reads.

### Bài 20 — Cache consistency

Catalog cache ở API và CDN, inventory authoritative trong MongoDB. Thiết kế khi product price đổi và khi user đặt hàng để không dựa vào stale cache làm quyết định giao dịch.

### Bài 21 — Migration

Schema cũ nhúng all reviews vào products. Viết kế hoạch expand–migrate–contract gồm backfill, dual-write, version marker, delete propagation, monitoring và rollback.

### Bài 22 — Java Sync Driver

Viết Java dùng `Filters.and`, `gte` và `Updates.combine` để reserve inventory atomic. Bổ sung validation cho qty và cơ chế idempotency request.

### Bài 23 — Benchmark

Thiết kế load test 60% reads, 30% writes, 10% reports; báo cáo p95/p99, throughput, disk, cache, document size distribution và replication lag.

### Bài 24 — Consistency

Review insert thành công nhưng rating summary chưa update. Đề xuất hai giải pháp: transaction và eventual consistency + reconciliation. Nêu ưu/nhược và quy tắc xử lý retries.

### Bài 25 — Thiết kế tổng hợp

Thiết kế schema cho sàn bán hàng với sản phẩm, tồn kho, giỏ hàng, đánh giá, đơn hàng và lịch sử thay đổi. Trình bày access-pattern matrix, boundaries, embeddings, references, indexes, write paths, consistency policy và benchmark plan.

## 48. Quy trình ra quyết định theo mẫu truy cập

### Bước 1 — Viết các query thực tế

Không bắt đầu bằng ERD rồi dịch máy móc từng bảng thành collection. Viết:

```text
Endpoint /products
Endpoint /products/{id}
Endpoint /products/{id}/reviews
POST /orders
PATCH /inventory/reserve
GET /reports/sales
```

Ghi rõ fields, filters, sort, limits, tần suất, latency và consistency.

### Bước 2 — Phân loại field

```text
Hot read + cold update:   product name, price, thumbnail
Hot write:                inventory counters
Large & growing:          reviews, stock movements
Historical snapshot:      order line price/name
Computed/derived:         rating summary, sales report
```

### Bước 3 — Chọn ownership và consistency

Xác định nguồn sự thật, bản sao nào cho phép lệch, nghiệp vụ nào cần transaction, event nào cần idempotency và dữ liệu nào không được chỉnh sửa lịch sử.

### Bước 4 — Chọn embed/reference/hybrid

Embed dữ liệu bounded đọc/cập nhật cùng nhau; reference dữ liệu lớn, tăng mạnh hoặc có lifecycle riêng; hybrid để giữ subset/computed values phục vụ hot reads.

### Bước 5 — Thiết kế indexes theo truy vấn

Xây compound indexes cho equality/sort/range/query shape, cân bằng selectivity và chi phí duy trì index khi cập nhật.

### Bước 6 — Định nghĩa growth limits

Giới hạn số phần tử array, kích thước document mục tiêu, outlier handling và storage/retention. Không để mảng phát triển cho tới khi gặp lỗi 16 MiB mới sửa.

### Bước 7 — Đo thực nghiệm

Chạy explain và load tests có dữ liệu tương tự production, đo cả read/write latency, throughput, size/cache/index/oplog/replication.

### Bước 8 — Migration và rollback

Expand–backfill–dual-write/CDC–verify–switch–contract, có khả năng kiểm tra lại dữ liệu và rollback khi ứng dụng đã ghi thêm dữ liệu mới.

### Bước 9 — Theo dõi sau triển khai

Đặt alerts cho document growth, p99 latency, write conflicts, disk/cache pressure và data drift giữa source/copies.

### Bước 10 — Điều chỉnh theo workload mới

Access pattern thay đổi khi sản phẩm có thêm tính năng, số tenant tăng, reports mới hoặc lượng cập nhật tăng. Schema design là **quyết định có thể tiến hóa**, không phải chân lý bất biến.

## 49. Tổng kết

**Tối ưu mô hình document của MongoDB phải xuất phát từ workload.** Trường nào được đọc cùng nhau, trường nào cập nhật cùng nhau, số phần tử có thể tăng bao nhiêu và cần nhất quán đến đâu quan trọng hơn việc dịch một mô hình quan hệ thành JSON giống nguyên bản.

**Embedding** thuận lợi khi dữ liệu nhỏ, bounded và thường được truy cập như một đơn vị. **Referencing** thích hợp với quan hệ nhiều, dữ liệu tăng lớn, cập nhật độc lập hoặc có vòng đời khác nhau. **Hybrid patterns** như Subset, Outlier, Extended Reference, Computed và Bucket giúp cân bằng giữa khả năng đọc nhanh và chi phí ghi/duy trì dữ liệu.

**Tần suất cập nhật quyết định nhiều trade-off ẩn.** Một field tồn kho nhỏ ghi hàng nghìn lần/phút có thể tạo hot document; những bản sao denormalized hoặc index trên field hay đổi làm write amplification tăng. Một array lớn có thể tốn index, cache và tăng kích thước dù UI chỉ cần vài phần tử. Mặt khác, tách dữ liệu quá mức có thể làm xuất hiện N+1 queries, nhiều joins và coordination costs.

**Đừng tối ưu bằng trực giác đơn lẻ.** Dùng `explain("executionStats")` để hiểu query shape; dùng metrics và benchmark có tải đại diện để đo p95/p99, throughput, working set, index maintenance và replication lag. Định nghĩa source-of-truth, idempotency, consistency, migration/rollback rõ ràng trước khi đổi schema production.

Một document model tốt không phải mô hình ít collections nhất hoặc ít field trùng lặp nhất. Đó là mô hình **phục vụ đường truy cập quan trọng với chi phí dự đoán được, cập nhật an toàn và tăng trưởng bền vững**.

## 50. Tài liệu tham khảo

- [MongoDB — Data Modeling Introduction](https://www.mongodb.com/docs/manual/data-modeling/): tư duy thiết kế dữ liệu theo cách ứng dụng truy cập.
- [MongoDB — Data Modeling Design Patterns](https://www.mongodb.com/docs/manual/data-modeling/design-patterns/): các pattern như embedding, referencing, subset, bucket, computed và extended reference.
- [MongoDB — Embedding vs References](https://www.mongodb.com/docs/manual/data-modeling/concepts/embedding-vs-references/): cân nhắc quan hệ và vòng đời dữ liệu.
- [MongoDB — Schema Design Process](https://www.mongodb.com/docs/manual/data-modeling/schema-design-process/): thiết kế với workload, constraints và growth.
- [MongoDB — BSON Document Size Limit](https://www.mongodb.com/docs/manual/reference/limits/): giới hạn 16 MiB và các giới hạn khác.
- [MongoDB — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/): atomic updates một document và multi-document transactions.
- [MongoDB — Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/): đánh index arrays và giới hạn liên quan.
- [MongoDB — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/): query execution statistics.
- [MongoDB — Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/): native time series và các hạn chế.
- [MongoDB — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/): theo dõi thay đổi để đồng bộ những bản sao phù hợp.
- [MongoDB — $lookup Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/): join collections và chi phí cần đo.
- [MongoDB — $merge Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/merge/): materialize computed data và semantics cập nhật.

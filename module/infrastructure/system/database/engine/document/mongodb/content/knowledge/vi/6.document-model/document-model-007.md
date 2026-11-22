# Các mẫu subset, computed, bucket và attribute trong mô hình document MongoDB

## 1. Vì sao cần các mẫu thiết kế document?

MongoDB lưu dữ liệu theo **document BSON**, giúp đặt những trường thường được đọc hoặc cập nhật cùng nhau trong một đơn vị nghiệp vụ. Tuy nhiên, một mô hình document hợp lý khi mới có vài nghìn bản ghi có thể trở nên chậm và khó bảo trì khi dữ liệu tăng: document ngày càng lớn, truy vấn phải đọc nhiều thông tin không cần thiết, báo cáo liên tục tính lại cùng kết quả, hay mỗi sản phẩm có một bộ thuộc tính khác nhau.

Bốn mẫu thiết kế (*schema design patterns*) thường dùng để giải quyết những vấn đề đó là:

| Mẫu | Vấn đề chính cần giải quyết | Ý tưởng cốt lõi |
| --- | --- | --- |
| **Subset** | Truy vấn thường dùng chỉ cần một phần nhỏ của đối tượng lớn. | Giữ phần được dùng thường xuyên trong document chính, lưu phần còn lại riêng. |
| **Computed** | Một giá trị tổng hợp/tính toán bị truy vấn lặp lại với chi phí cao. | Tính trước và lưu kết quả, cập nhật theo chính sách nhất quán. |
| **Bucket** | Có rất nhiều bản ghi nhỏ cùng nhóm theo thời gian/thiết bị/đối tượng. | Gom các sự kiện liên quan thành document có giới hạn rõ ràng. |
| **Attribute** | Nhiều thực thể cùng loại có các thuộc tính tùy biến, khó tạo index theo từng trường. | Biểu diễn thuộc tính động thành các phần tử có cấu trúc chung để truy vấn và lập chỉ mục. |

Đây là **mẫu thiết kế dữ liệu**, không phải loại collection hay tính năng bắt buộc bật trong MongoDB. Một hệ thống có thể kết hợp nhiều mẫu; cũng có thể không cần mẫu nào nếu document đơn giản đã đáp ứng truy vấn và yêu cầu nhất quán.

Điểm xuất phát luôn là **access pattern**: ứng dụng cần đọc/ghi trường nào, trong bao lâu, với tần suất và độ trễ như thế nào. Chọn pattern theo tên gọi mà không mô tả workload sẽ dễ dẫn đến dữ liệu trùng lặp, nhiều thao tác cập nhật hơn và truy vấn khó tối ưu.

### Ví dụ xuyên suốt

Xét một nền tảng bán hàng có các yêu cầu:

- Trang danh sách cần tên, giá, ảnh đại diện và điểm đánh giá của sản phẩm.
- Trang chi tiết cần một vài đánh giá gần nhất; có thể bấm xem toàn bộ đánh giá cũ.
- Bộ lọc theo thông số khác nhau cho laptop, áo, sách và điện thoại.
- Dashboard cần số đơn, tổng doanh thu theo ngày nhưng không nhất thiết chính xác tới từng mili giây.
- Hệ thống thu thập nhiều sự kiện lượt xem hoặc phép đo mỗi ngày.

Các yêu cầu này tương ứng với bốn nhu cầu khác nhau. Ta sẽ dùng chúng để phân biệt subset, computed, bucket và attribute.

## 2. Trước khi áp dụng pattern: ranh giới document và nguồn dữ liệu chuẩn

MongoDB đảm bảo thao tác ghi lên **một document** có tính nguyên tử. Khi tách một thực thể thành nhiều document hoặc sao chép dữ liệu phục vụ đọc, ứng dụng phải quyết định cách giữ nhất quán giữa các bản.

Ví dụ: nếu vừa lưu đánh giá mới trong collection `reviews` vừa thay đổi điểm trung bình trên `products`, đây là hai thao tác trên hai document khác nhau. Không nên mặc định cả hai luôn thành công đồng thời; cần chọn transaction, cập nhật bất đồng bộ, cơ chế retry hoặc hòa giải dữ liệu tùy yêu cầu.

Các thuật ngữ nên thống nhất:

- **Source of truth:** nơi lưu giá trị được xem là chuẩn để tái tạo thông tin khác, ví dụ các review đã được chấp nhận là nguồn để tính thống kê đánh giá.
- **Derived data:** dữ liệu được suy ra từ nguồn, ví dụ `reviewCount`, `averageRating` hoặc danh sách ba review gần nhất.
- **Bounded data:** tập dữ liệu có giới hạn về số phần tử/kích thước, ví dụ năm bình luận hiển thị đầu tiên.
- **Write amplification:** một hành động nghiệp vụ dẫn đến nhiều lần ghi để duy trì dữ liệu phục vụ đọc.

Mọi mẫu bên dưới đều là cách trao đổi chi phí đọc, ghi, lưu trữ và độ phức tạp. Bảng so sánh cuối bài sẽ cho thấy khi nào đánh đổi đó có lợi.

---

## 3. Subset pattern: giữ phần dữ liệu được đọc thường xuyên

### 3.1. Bài toán

Một sản phẩm có hàng nghìn đánh giá. Trang danh sách sản phẩm chỉ cần tên, giá, ảnh đại diện, số sao và vài thông tin cơ bản. Trang chi tiết muốn hiển thị ba đánh giá gần đây; những đánh giá còn lại chỉ xuất hiện khi người dùng mở mục “Xem thêm”.

Nếu nhúng toàn bộ review vào `products.reviews`, document sản phẩm tăng theo số bình luận. Mỗi lần mở danh sách, ứng dụng có thể phải xử lý document lớn, còn các thao tác thêm review liên tục cập nhật chung một document.

MongoDB giới hạn **một BSON document ở 16 MiB**. Nhưng ngay cả khi chưa chạm giới hạn, một mảng lớn có thể tạo áp lực lên cache, đọc/ghi và cạnh tranh cập nhật.

**Subset pattern** giải quyết bằng cách lưu trong document chính **phần nhỏ có ích cho đường truy cập phổ biến**, còn dữ liệu đầy đủ ở collection khác.

### 3.2. Mô hình ví dụ

~~~javascript
// products: phần chính dùng cho list và detail
{
  _id: "P100",
  name: "Laptop 14 inch",
  priceMinor: 19500000,
  thumbnailUrl: "/images/p100-small.webp",
  latestReviewPreview: [
    { reviewId: "R920", rating: 5, text: "Pin tốt" },
    { reviewId: "R918", rating: 4, text: "Nhẹ" },
    { reviewId: "R915", rating: 5, text: "Màn hình đẹp" }
  ],
  reviewPreviewUpdatedAt: ISODate("2026-11-14T02:00:00Z")
}

// reviews: dữ liệu đầy đủ, tăng độc lập
{
  _id: "R920",
  productId: "P100",
  authorId: "U21",
  rating: 5,
  text: "Pin tốt",
  createdAt: ISODate("2026-11-14T01:58:00Z"),
  moderationStatus: "PUBLISHED"
}
~~~

Tại đây:

1. Trang danh sách đọc `products` mà không quét toàn bộ review.
2. Trang chi tiết lấy ngay ba đánh giá gần đây từ `latestReviewPreview`.
3. Phân trang đánh giá gọi collection `reviews` riêng.
4. Chỉ một số trường review được sao chép vào preview; bản đầy đủ vẫn ở `reviews`.

Truy vấn tất cả review đã công bố:

~~~javascript
db.reviews.createIndex({
  productId: 1,
  moderationStatus: 1,
  createdAt: -1,
  _id: -1
});

db.reviews.find({
  productId: "P100",
  moderationStatus: "PUBLISHED"
}).sort({ createdAt: -1, _id: -1 }).limit(20);
~~~

Sắp xếp thêm `_id` giúp tạo thứ tự ổn định nếu nhiều review có cùng `createdAt`. Trong thực tế, chiến lược phân trang nên dùng khóa tiếp tục (*cursor/keyset*) để tránh `skip` rất sâu.

### 3.3. Subset khác projection

~~~javascript
// Projection chỉ chọn trường được trả về
db.products.find(
  { _id: "P100" },
  { name: 1, priceMinor: 1, thumbnailUrl: 1 }
);
~~~

Projection là một kỹ thuật truy vấn có ích. Tuy nhiên, projection **không tự biến một document chứa mảng khổng lồ thành mô hình lưu trữ nhỏ**; trong nhiều trường hợp storage engine vẫn phải đọc các trang chứa document rồi mới lọc trường trả về. Một truy vấn được chỉ mục bao phủ (*covered query*) có thể là ngoại lệ quan trọng.

Subset pattern can thiệp vào **cách lưu**: dữ liệu ít được dùng không nằm chung trong document chính. Vì vậy, khi mô hình hiện tại có hàng trăm trường ít dùng, cần đánh giá cả projection, index, lẫn khả năng tách dữ liệu; không mặc định tách collection luôn tốt hơn.

### 3.4. Cập nhật subset như thế nào?

Giả sử review mới vừa được duyệt xuất bản. Luồng xử lý có thể:

~~~text
Review được duyệt
      |
      v
Ghi trạng thái review vào reviews (nguồn dữ liệu chuẩn)
      |
      +--> Phát sự kiện / công việc cập nhật preview
                    |
                    v
             Tính lại 3 review mới nhất
                    |
                    v
             Cập nhật products.latestReviewPreview
~~~

Một phương án đơn giản là truy vấn các review đã xuất bản mới nhất rồi `$set` preview:

~~~javascript
const latest = db.reviews.find(
  { productId: "P100", moderationStatus: "PUBLISHED" },
  { _id: 1, rating: 1, text: 1, createdAt: 1 }
).sort({ createdAt: -1, _id: -1 }).limit(3).toArray();

const preview = latest.map(r => ({
  reviewId: r._id,
  rating: r.rating,
  text: r.text
}));

db.products.updateOne(
  { _id: "P100" },
  {
    $set: {
      latestReviewPreview: preview,
      reviewPreviewUpdatedAt: new Date()
    }
  }
);
~~~

Đây là ví dụ ý tưởng; nếu nhiều worker cập nhật cùng lúc, một kết quả tính từ snapshot cũ có thể ghi đè preview mới hơn. Hệ thống thực tế cần quản lý thứ tự sự kiện, revision hoặc cơ chế đồng bộ/rebuild phù hợp. Nếu yêu cầu hiển thị ngay và nhất quán tuyệt đối, cần thiết kế một quy trình giao dịch tương ứng thay vì chấp nhận cập nhật bất đồng bộ.

Xóa/ẩn review vì moderation cũng phải cập nhật preview. Chỉ xử lý **thêm** review mà quên **sửa/xóa** sẽ tạo thông tin sai lệch lâu dài.

### 3.5. Khi nào dùng và khi nào tránh?

**Phù hợp khi:**

- Có một phần dữ liệu nhỏ, hữu hạn được hầu hết request sử dụng.
- Phần còn lại lớn, tăng liên tục hoặc có vòng đời cập nhật riêng.
- Đường đọc phổ biến được tối ưu rõ rệt nhờ không kéo dữ liệu lạnh.
- Đội ngũ chấp nhận duy trì bản sao nhỏ và có cơ chế cập nhật/khôi phục.

**Cân nhắc tránh khi:**

- Gần như mọi request đều cần toàn bộ dữ liệu.
- Dữ liệu con nhỏ, có giới hạn và thường cập nhật cùng document cha.
- Đồng bộ subset khó hơn lợi ích hiệu năng.
- Có thể đạt mục tiêu bằng chỉ mục phù hợp, projection và schema đơn giản.

Subset không phải quy tắc “cứ document lớn là tách”. Phải đo mẫu truy cập, kích thước, chi phí ghi và mức chấp nhận dữ liệu trễ.

---

## 4. Computed pattern: lưu kết quả đã tính để giảm phép tính lặp lại

### 4.1. Bài toán

Một sản phẩm có 200.000 review. Mỗi lần tải trang sản phẩm, ứng dụng chạy aggregation để tính:

- Số review đã xuất bản.
- Tổng số sao.
- Điểm trung bình.
- Phân bố số review ở mỗi mức sao.

Nếu lượng truy cập trang rất lớn nhưng review mới không nhiều, tính lại tất cả mỗi lần đọc lãng phí CPU và I/O.

**Computed pattern** lưu sẵn giá trị tính toán trong document để đường đọc phổ biến chỉ phải lấy kết quả:

~~~javascript
{
  _id: "P100",
  name: "Laptop 14 inch",
  reviewStats: {
    count: 1200,
    ratingSum: 5490,
    averageRating: 4.575
  },
  reviewStatsUpdatedAt: ISODate("2026-11-14T02:00:00Z")
}
~~~

Các giá trị trong `reviewStats` là **derived data**. Collection `reviews` hoặc một nhật ký sự kiện hợp lệ vẫn là nguồn để tái tính toán nếu bộ đếm sai.

### 4.2. Tính trước và đọc lại

Từ `reviews`, một phép tổng hợp minh họa:

~~~javascript
db.reviews.aggregate([
  {
    $match: {
      productId: "P100",
      moderationStatus: "PUBLISHED"
    }
  },
  {
    $group: {
      _id: "$productId",
      reviewCount: { $sum: 1 },
      ratingSum: { $sum: "$rating" },
      averageRating: { $avg: "$rating" }
    }
  }
]);
~~~

Nếu mỗi request phải chạy pipeline này trên tập review lớn, chi phí có thể đáng kể. Khi thống kê đã được lưu, API chỉ đọc field cần thiết:

~~~javascript
db.products.find(
  { _id: "P100" },
  { name: 1, reviewStats: 1, reviewStatsUpdatedAt: 1 }
);
~~~

Lợi ích Computed không nằm ở việc aggregation “không tốt”; aggregation vẫn phù hợp với các báo cáo linh hoạt. Điểm chính là **tránh tính lặp lại một phép tính giống nhau** khi tần suất đọc lớn hơn nhiều so với tần suất thay đổi dữ liệu nguồn.

### 4.3. Ba chiến lược duy trì dữ liệu computed

| Chiến lược | Cách làm | Điểm mạnh | Đánh đổi |
| --- | --- | --- | --- |
| **Đồng bộ theo write** | Khi review hợp lệ được thêm/sửa/xóa, cập nhật bộ đếm trong cùng luồng xử lý. | Giá trị mới xuất hiện sớm, dễ đáp ứng nhu cầu tươi dữ liệu hơn. | Nhiều thao tác ghi; cần xử lý nguyên tử xuyên document, retry và xung đột. |
| **Bất đồng bộ theo sự kiện** | Sau thay đổi nguồn, gửi sự kiện cho worker cập nhật thống kê. | Tách tải ghi nguồn khỏi tính toán, linh hoạt về throughput. | Có độ trễ; cần idempotency, thứ tự sự kiện và theo dõi lỗi. |
| **Batch định kỳ** | Mỗi giờ/ngày tính lại thống kê từ nguồn. | Đơn giản cho dashboard không yêu cầu tức thời. | Dữ liệu cũ đến kỳ tiếp theo; batch có thể tốn tài nguyên. |

Có thể kết hợp: tăng bộ đếm gần thời gian thực và chạy job đối soát định kỳ để sửa sai lệch do bug hoặc sự kiện bỏ sót.

### 4.4. Cập nhật bằng `$inc` không tự giải quyết idempotency

Ví dụ tăng tổng sau khi một review mới được **chấp nhận đúng một lần**:

~~~javascript
db.products.updateOne(
  { _id: "P100" },
  {
    $inc: {
      "reviewStats.count": 1,
      "reviewStats.ratingSum": 5
    },
    $set: { reviewStatsUpdatedAt: new Date() }
  }
);
~~~

Toán tử `$inc` có tính nguyên tử trong một document, nhưng nếu cùng một sự kiện được xử lý lại hai lần, giá trị sẽ tăng gấp đôi. Trong hệ thống có retry, worker bị restart hoặc message được giao nhiều lần, phải dùng **idempotency key**, bản ghi xử lý sự kiện duy nhất, hoặc transaction/thiết kế update bảo đảm một sự kiện không được áp dụng hai lần.

Ngoài ra, nếu review bị sửa từ 5 sao thành 3 sao, ta cần giảm `ratingSum` đi 2 chứ không tăng `count`. Nếu review bị xóa hoặc bị ẩn, có thể phải trừ điểm và giảm số lượng. Các phép tính derived nên có bảng chuyển trạng thái rõ ràng, không chỉ có nhánh insert.

Đối với average, một cách ít sai lệch do làm tròn là giữ **count và sum** làm số liệu trung gian rồi tính trung bình khi đọc hoặc cập nhật có kiểm soát:

~~~javascript
const stats = db.products.findOne(
  { _id: "P100" },
  { _id: 0, reviewStats: 1 }
).reviewStats;

const averageRating = stats.count > 0
  ? stats.ratingSum / stats.count
  : null;
~~~

Khi cần xử lý tiền tệ hoặc giá trị yêu cầu độ chính xác thập phân, nên dùng kiểu BSON và quy tắc làm tròn thích hợp, ví dụ `Decimal128` hoặc số đơn vị tiền nhỏ nhất, tránh tính tổng doanh thu bằng floating-point thiếu kiểm soát.

### 4.5. Computed cho dashboard doanh thu

Một ví dụ khác: số đơn thanh toán thành công và tổng doanh thu theo ngày. Không nên mỗi lần mở dashboard lại quét toàn bộ lịch sử giao dịch nếu chủ yếu cần chỉ số ngày/tháng.

~~~javascript
// dailySales: một document cho mỗi ngày và cửa hàng
{
  _id: { sellerId: "S42", date: "2026-11-14" },
  paidOrderCount: 183,
  revenueMinor: NumberLong("72650000"),
  computedAt: ISODate("2026-11-14T10:15:00Z"),
  sourceWatermark: ISODate("2026-11-14T10:10:00Z")
}
~~~

Trường `computedAt` nói khi kết quả được ghi, còn `sourceWatermark` (nếu có) cho biết dữ liệu nguồn đã được xử lý đến mốc nào. Hai thời điểm có thể khác nhau do sự kiện đến trễ.

Các câu hỏi nghiệp vụ phải được quyết định trước: doanh thu là tổng tiền thanh toán hay tiền sau hoàn trả? Đơn bị hủy được tính ra sao? Ngày theo múi giờ nào? Giao dịch đến muộn có được cập nhật ngày cũ không? Computed pattern tối ưu hiệu năng nhưng **không thể thay thế định nghĩa KPI**.

### 4.6. Phân biệt computed value với cache đơn thuần

Một giá trị computed thường được lưu như một phần mô hình dữ liệu phục vụ truy vấn, có quy trình cập nhật và chính sách độ mới. Cache ứng dụng hoặc Redis cũng có thể giữ kết quả, nhưng thường có lifecycle và eviction khác. Một hệ thống có thể lưu computed stats trong MongoDB rồi cache kết quả đọc ở tầng API; hai lớp đó giải quyết các vấn đề riêng.

**Nên dùng Computed khi** phép tính đắt, kết quả được đọc thường xuyên và có thể chấp nhận hoặc quản lý rõ ràng thời gian trễ. **Nên thận trọng** với số dư thanh toán, tồn kho khả dụng hoặc invariant yêu cầu tính đúng đắn tuyệt đối: lưu computed vẫn có thể, nhưng phải thiết kế giao dịch và tính nhất quán tương ứng, không coi eventual consistency là mặc định được phép.

---

## 5. Bucket pattern: gom nhiều bản ghi nhỏ thành đơn vị có giới hạn

### 5.1. Bài toán

Một cảm biến gửi một phép đo mỗi giây. Nếu mỗi phép đo là một document riêng, một ngày tạo 86.400 document cho một thiết bị. Với nhiều thiết bị, lượng document và index entry tăng nhanh. Khi API chủ yếu đọc đồ thị của một thiết bị theo từng giờ, nhóm dữ liệu liên tiếp có thể hữu ích.

**Bucket pattern** gom các bản ghi nhỏ có quan hệ gần nhau thành một document theo tiêu chí như thiết bị và cửa sổ thời gian.

~~~javascript
// sensorBuckets
{
  _id: "sensor-7|2026-11-14T09:00Z|0",
  sensorId: "sensor-7",
  windowStart: ISODate("2026-11-14T09:00:00Z"),
  windowEnd: ISODate("2026-11-14T10:00:00Z"),
  sequence: 0,
  count: 3,
  measurements: [
    { at: ISODate("2026-11-14T09:00:01Z"), value: 23.4 },
    { at: ISODate("2026-11-14T09:00:02Z"), value: 23.5 },
    { at: ISODate("2026-11-14T09:00:03Z"), value: 23.5 }
  ]
}
~~~

Một document chứa metadata chung (`sensorId`, khoảng thời gian), nhiều phép đo và số lượng phần tử. Truy vấn dữ liệu theo thiết bị trong một khoảng thời gian có thể đọc một tập bucket thay vì từng document riêng lẻ.

### 5.2. Chọn tiêu chí bucket

Một bucket có thể được giới hạn theo:

- **Thời gian:** một phút, một giờ, một ngày.
- **Số phần tử:** tối đa 500 hoặc 1.000 phép đo.
- **Dung lượng BSON:** đóng bucket trước khi gần giới hạn 16 MiB.
- **Khóa nhóm:** ví dụ `sensorId`, `tenantId`, `customerId`, loại sự kiện.
- **Kết hợp:** `sensorId` + một giờ + tối đa 1.000 phần tử + ngưỡng kích thước an toàn.

Không có quy tắc “mỗi giờ một bucket” phù hợp cho mọi thiết bị. Nếu thiết bị gửi 10.000 phép đo/giây, một giờ có thể quá lớn; nếu một thiết bị chỉ gửi vài bản ghi mỗi tháng, bucket theo giờ có thể tạo nhiều nhóm thưa.

Giới hạn BSON **16 MiB vẫn áp dụng cho từng bucket**. Bucket không phải cơ chế vượt qua giới hạn document bằng cách đổi tên mảng; nó là cách **chia dữ liệu thành nhiều document được giới hạn**.

### 5.3. Ví dụ cập nhật bucket hiện có

Giả sử hệ thống đã tạo bucket với `count: 0`, và quyết định tối đa 1.000 phép đo/bucket:

~~~javascript
const measurement = {
  at: ISODate("2026-11-14T09:12:00Z"),
  value: 24.1
};

const result = db.sensorBuckets.updateOne(
  {
    _id: "sensor-7|2026-11-14T09:00Z|0",
    count: { $lt: 1000 }
  },
  {
    $push: { measurements: measurement },
    $inc: { count: 1 }
  }
);
~~~

Cặp `$push` và `$inc` trong một update document là nguyên tử. Điều kiện `count: { $lt: 1000 }` tránh ghi tiếp khi bucket đã đủ số lượng **nếu counter được duy trì đúng**. Nếu `matchedCount === 0`, ứng dụng cần phân biệt bucket chưa tồn tại với bucket đã đầy rồi chọn bucket mới theo quy tắc cấp phát.

Ví dụ này **chưa xử lý trọn vẹn** tạo bucket, ghi trùng, nhiều producer cùng lúc hoặc hạn mức byte; trong hệ thống thật cần thiết kế giao thức cấp `sequence`, unique key, idempotency và retry. Trên dữ liệu có phần tử kích thước biến động, số lượng nhỏ hơn 1.000 cũng có thể vượt ngưỡng byte, vì vậy chỉ chặn theo `count` là chưa đủ.

### 5.4. Truy vấn và index

~~~javascript
db.sensorBuckets.createIndex({
  sensorId: 1,
  windowStart: 1,
  sequence: 1
});

db.sensorBuckets.find({
  sensorId: "sensor-7",
  windowStart: {
    $gte: ISODate("2026-11-14T08:00:00Z"),
    $lt: ISODate("2026-11-14T12:00:00Z")
  }
}).sort({ windowStart: 1, sequence: 1 });
~~~

Truy vấn này tìm các bucket có cửa sổ bắt đầu nằm trong khoảng cho trước. Với bài toán hỏi “phép đo chính xác từ 08:15 đến 11:45”, cần tính cả những bucket **giao** khoảng thời gian nhưng bắt đầu trước mốc hỏi, và lọc tiếp các phần tử trong `measurements`. Nếu chỉ lọc `windowStart >= 08:15`, bucket 08:00 có thể bị bỏ sót dù chứa phép đo lúc 08:20.

Một điều kiện tìm bucket giao nhau khi dùng khoảng `[windowStart, windowEnd)`:

~~~javascript
db.sensorBuckets.find({
  sensorId: "sensor-7",
  windowStart: { $lt: ISODate("2026-11-14T11:45:00Z") },
  windowEnd: { $gt: ISODate("2026-11-14T08:15:00Z") }
});
~~~

API phải lọc các measurement nằm ngoài khoảng được yêu cầu sau khi lấy bucket, hoặc dùng aggregation tương ứng. Nếu cần truy vấn từng điểm độc lập, lưu mọi điểm trong một mảng bucket có thể trở thành rào cản.

### 5.5. Đánh đổi của Bucket

**Lợi ích:**

- Giảm số document và metadata lặp lại khi nhiều mẫu nhỏ cùng nhóm.
- Thuận tiện cho thao tác đọc theo nhóm thời gian, thiết bị hoặc phiên.
- Có thể lưu các thống kê bucket như `min`, `max`, `count` để giảm công việc xử lý.
- Tạo đơn vị quản lý retention, chuyển dữ liệu lạnh hoặc phân trang theo nhóm.

**Chi phí và rủi ro:**

- Nhiều producer cập nhật cùng bucket có thể tạo **hot document** và cạnh tranh ghi.
- Việc sửa/xóa một phần tử trong mảng có thể phức tạp hơn sửa document độc lập.
- Phải xử lý bucket đầy, dữ liệu đến trễ, trùng lặp và ranh giới thời gian.
- Index trên các phần tử mảng và kích thước document có thể tăng; query theo từng event không chắc nhanh hơn.
- Nếu TTL hoặc xóa áp dụng ở cấp bucket, cần xác định có được xóa cả nhóm khi chỉ vài phép đo đã hết hạn hay không.

### 5.6. Bucket tự thiết kế khác time series collection

MongoDB có **time series collection** để hỗ trợ workload theo thời gian và tổ chức dữ liệu đo hiệu quả. Đây là tính năng cơ sở dữ liệu có đặc tính riêng về `timeField`, `metaField`, lưu trữ, chỉ mục và các giới hạn cập nhật/xóa tùy phiên bản.

~~~javascript
db.createCollection("sensorReadings", {
  timeseries: {
    timeField: "timestamp",
    metaField: "metadata",
    granularity: "minutes"
  }
});

db.sensorReadings.insertOne({
  timestamp: ISODate("2026-11-14T09:12:00Z"),
  metadata: { sensorId: "sensor-7", siteId: "HCM-01" },
  value: 24.1
});
~~~

Ở đây ứng dụng ghi **mỗi phép đo như một document logic**, MongoDB đảm trách tổ chức lưu trữ time series theo cơ chế phù hợp. Không cần tự quản lý array `measurements` và `sequence` như custom bucket phía trên.

Nên đánh giá time series collection trước nếu bài toán thực sự là phép đo theo thời gian và phiên bản/giới hạn MongoDB đáp ứng. Custom Bucket vẫn hữu ích cho nhóm giao dịch, sự kiện hoặc các quy tắc bucket riêng mà time series collection không phù hợp.

---

## 6. Attribute pattern: chuẩn hóa cách lưu thuộc tính đa dạng

### 6.1. Bài toán

Catalog có laptop, áo và sách. Nếu tạo trường cố định cho mọi biến thể:

~~~javascript
// Laptop
{ _id: "P-L1", category: "laptop", ramGb: 16, storageGb: 512 }

// Áo
{ _id: "P-C1", category: "clothing", size: "M", fabric: "cotton" }

// Sách
{ _id: "P-B1", category: "book", author: "Tác giả A", pageCount: 320 }
~~~

Schema linh hoạt của MongoDB cho phép lưu các trường này. Tuy nhiên, hệ thống cho phép lọc hàng trăm thuộc tính tùy biến theo danh mục và các thuộc tính thường xuyên được thêm mới. Việc thiết kế, quản lý index riêng cho mọi trường động trở nên tốn kém.

**Attribute pattern** đưa những thuộc tính cần truy vấn vào một cấu trúc chung, thường là **mảng object chứa tên và giá trị thuộc tính**.

~~~javascript
{
  _id: "P-L1",
  category: "laptop",
  name: "Laptop 14 inch",
  attributes: [
    { key: "ramGb", numberValue: 16 },
    { key: "storageGb", numberValue: 512 },
    { key: "color", stringValue: "silver" },
    { key: "touchscreen", booleanValue: false }
  ]
}
~~~

Lưu ý đây là **một cách triển khai** Attribute pattern, không phải schema chuẩn bắt buộc. Có hệ thống dùng `k`/`v`, có hệ thống dùng `name`/`value`, hoặc object có `type`/`unit`/`displayName`. Mục tiêu là tạo cấu trúc nhất quán cho các thuộc tính cần lọc.

### 6.2. Vì sao phân loại kiểu giá trị?

Một cách triển khai tưởng đơn giản là:

~~~javascript
attributes: [
  { key: "ramGb", value: "16" },
  { key: "storageGb", value: "512" },
  { key: "color", value: "silver" }
]
~~~

Nhưng khi lưu mọi thứ dưới dạng string, lọc khoảng số học dễ sai. So sánh từ điển của `"16"` và `"8"` không có nghĩa tương đương với so sánh số 16 và 8. Một lược đồ có thể sử dụng `numberValue`, `stringValue`, `dateValue`, `booleanValue` hoặc khai báo kiểu rõ ràng.

~~~javascript
{
  _id: "P-L2",
  category: "laptop",
  attributes: [
    { key: "ramGb", type: "number", numberValue: 32, unit: "GB" },
    { key: "weightKg", type: "number", numberValue: 1.35, unit: "kg" },
    { key: "color", type: "string", stringValue: "black" }
  ]
}
~~~

Nếu dữ liệu đến từ nhiều nguồn, cần **chuẩn hóa đơn vị** trước khi lọc: 1.500 g và 1,5 kg biểu thị cùng khối lượng, nhưng lọc trực tiếp theo số `1500` và `1.5` sẽ gây sai nếu không có đơn vị chuẩn. Tên thuộc tính cũng phải theo từ điển nghiệp vụ: `memory`, `ram`, `ramGb` không nên được xem là một trường chỉ vì con người hiểu gần giống nhau.

### 6.3. Index với Attribute pattern

Ví dụ cần lọc laptop có RAM ít nhất 16 GB:

~~~javascript
db.products.createIndex({
  category: 1,
  "attributes.key": 1,
  "attributes.numberValue": 1
});

db.products.find({
  category: "laptop",
  attributes: {
    $elemMatch: {
      key: "ramGb",
      numberValue: { $gte: 16 }
    }
  }
});
~~~

`attributes` là array, nên index trên các subfield được sử dụng là **multikey index**. Cách kết hợp những trường trong cùng mảng và giới hạn của compound multikey index cần được xem xét theo cấu trúc thực tế.

**Vì sao dùng `$elemMatch`?** Nếu viết:

~~~javascript
// Có thể match hai phần tử KHÁC NHAU trong cùng mảng:
db.products.find({
  "attributes.key": "ramGb",
  "attributes.numberValue": { $gte: 16 }
});
~~~

Document có `ramGb = 8` nhưng `storageGb = 512` có thể thỏa điều kiện trên vì `key` khớp ở phần tử RAM còn giá trị `>= 16` khớp ở phần tử storage. `$elemMatch` yêu cầu **các điều kiện nằm trong cùng một phần tử mảng**, giúp tránh kết quả sai và hỗ trợ MongoDB sử dụng ràng buộc index phù hợp.

Ví dụ lỗi logic:

~~~javascript
{
  _id: "P-L3",
  category: "laptop",
  attributes: [
    { key: "ramGb", numberValue: 8 },
    { key: "storageGb", numberValue: 512 }
  ]
}
~~~

Truy vấn dùng hai dotted path độc lập có thể tìm thấy document này, nhưng truy vấn `$elemMatch` `ramGb >= 16` thì không.

### 6.4. Lọc nhiều thuộc tính

Muốn laptop có RAM ít nhất 16 GB **và** dung lượng lưu trữ ít nhất 512 GB (trong ví dụ đơn vị đã chuẩn hóa), mỗi điều kiện thuộc một phần tử riêng:

~~~javascript
db.products.find({
  category: "laptop",
  $and: [
    {
      attributes: {
        $elemMatch: {
          key: "ramGb",
          numberValue: { $gte: 16 }
        }
      }
    },
    {
      attributes: {
        $elemMatch: {
          key: "storageGb",
          numberValue: { $gte: 512 }
        }
      }
    }
  ]
});
~~~

MongoDB phải đánh giá điều kiện trên các phần tử thuộc tính khác nhau. Một index duy nhất không bảo đảm mọi tổ hợp filter được tối ưu; khi số lượng thuộc tính, bộ lọc và tổ hợp tăng mạnh, cần xem query plan, chi phí multikey index và khả năng dùng công cụ tìm kiếm chuyên dụng.

### 6.5. Khi nào nên giữ trường cố định?

Attribute pattern không bắt buộc chuyển **mọi field** thành phần tử trong mảng.

Các trường như `_id`, `sellerId`, `category`, `status`, `createdAt` hay `priceMinor` thường xuất hiện trên hầu hết sản phẩm và tham gia truy vấn chính. Giữ chúng ở mức gốc giúp schema rõ ràng, tránh phải tìm trong `attributes` để lọc theo điều kiện nghiệp vụ phổ biến.

~~~javascript
{
  _id: "P-L1",
  sellerId: "S42",
  category: "laptop",
  status: "ACTIVE",
  priceMinor: 19500000,
  attributes: [
    { key: "ramGb", numberValue: 16 },
    { key: "storageGb", numberValue: 512 }
  ]
}
~~~

**Mô hình lai** (field cố định + thuộc tính linh hoạt) thường dễ vận hành hơn việc ép mọi trường vào một lược đồ key–value.

### 6.6. Đánh đổi của Attribute

**Lợi ích:** mô hình có thể xử lý nhiều loại thuộc tính, thống nhất bộ lọc động, giảm nhu cầu định nghĩa index riêng cho mọi tên field biến thiên.

**Chi phí:** mỗi thuộc tính lặp lại tên key/type, tăng kích thước document; truy vấn cần `$elemMatch`; validation và indexing phức tạp hơn; việc sắp xếp theo một thuộc tính cụ thể và kết hợp nhiều bộ lọc có thể khó tối ưu. Nếu một document chứa hai phần tử cùng `key` nhưng giá trị khác nhau, ứng dụng phải quy định đó là lỗi, danh sách nhiều giá trị hay giá trị ưu tiên.

**Không nên dùng chỉ vì “MongoDB là schema-less”**. Nếu domain chỉ có 5–10 thuộc tính ổn định, field trực tiếp có thể đơn giản, dễ index và dễ bảo trì hơn. Nếu số thuộc tính động quá lớn và tìm kiếm là trọng tâm, có thể so sánh với wildcard index và giải pháp search; cần đo thay vì giả định Attribute luôn nhanh.

---

## 7. So sánh bốn pattern theo cách dữ liệu được tổ chức

| Câu hỏi | Subset | Computed | Bucket | Attribute |
| --- | --- | --- | --- | --- |
| Đơn vị thay đổi chính | Phần dữ liệu thường đọc so với phần đầy đủ. | Kết quả tính toán từ dữ liệu nguồn. | Nhóm bản ghi liên quan. | Cách biểu diễn thuộc tính biến thiên. |
| Đọc được tối ưu | Đọc phần nóng, ít chạm dữ liệu lạnh. | Đọc giá trị tổng hợp đã tính. | Đọc nhiều sự kiện cùng nhóm. | Lọc theo tên và giá trị thuộc tính động. |
| Ghi phát sinh | Đồng bộ phần preview với nguồn. | Cập nhật/đối soát giá trị derived. | Thêm event vào bucket; quản lý bucket đầy. | Duy trì mảng và index thuộc tính. |
| Rủi ro cốt lõi | Preview cũ hoặc không khớp nguồn. | Bộ đếm trùng/sai, dữ liệu trễ. | Bucket quá lớn, hot document. | Dữ liệu kiểu không chuẩn, điều kiện sai phần tử mảng. |
| Tiêu chí chọn | Dữ liệu được truy cập rất lệch. | Tính toán lặp lại tốn kém. | Sự kiện nhỏ, nhiều, thường đọc theo nhóm. | Thuộc tính đa dạng và cần lọc linh hoạt. |

Có thể nhớ bằng bốn động từ:

- **Subset:** *bớt* dữ liệu trong document được đọc thường xuyên.
- **Computed:** *tính trước* kết quả thường được hỏi.
- **Bucket:** *gom* nhiều bản ghi theo một quy tắc giới hạn.
- **Attribute:** *chuẩn hóa cách biểu diễn* các thuộc tính động.

Bốn mẫu không thay thế cho index, schema validation, ràng buộc duy nhất, transaction hoặc backup. Chúng làm việc ở tầng thiết kế dữ liệu, còn các cơ chế khác giúp đảm bảo kết quả và hiệu năng khi vận hành.

## 8. Kết hợp nhiều pattern trong cùng một ứng dụng

Quay lại hệ thống thương mại điện tử, một thiết kế có thể là:

~~~text
products
  - _id, category, name, priceMinor, status
  - attributes[]               <-- Attribute: RAM, size, color, ...
  - latestReviewPreview[]      <-- Subset: vài review mới nhất
  - reviewStats                <-- Computed: count, sum, average
             |
             +---- reviews
                       - review đầy đủ, tăng không giới hạn

dailySales
  - sellerId, day, totals      <-- Computed: số đơn/doanh thu ngày

viewEventBuckets
  - productId, timeWindow
  - events[]                   <-- Bucket: các lượt xem theo nhóm

orders
  - từng đơn và thông tin thanh toán chuẩn
~~~

Từng nhóm phục vụ một mục đích:

1. Trang danh sách gọi `products`, truy vấn field thường và `reviewStats`.
2. Trang chi tiết có thể hiển thị `latestReviewPreview` ngay; phân trang toàn bộ qua `reviews`.
3. Bộ lọc theo RAM hoặc kích cỡ dùng `attributes` với schema/index phù hợp.
4. Dashboard doanh thu dùng `dailySales`, có timestamp cho độ mới.
5. Phân tích lượt xem đọc theo bucket hoặc xử lý từ nguồn sự kiện đã được lưu giữ.

Một câu hỏi quan trọng: **dữ liệu nào được phép trễ?** Điểm review có thể chậm vài giây, nhưng trạng thái thanh toán không thể tùy ý chậm nếu ảnh hưởng việc giao hàng. Mỗi dạng dữ liệu cần chính sách nhất quán riêng.

## 9. Cập nhật theo transaction hay theo sự kiện?

Khi dùng Subset và Computed, cập nhật thường đi qua nhiều document. Có ba cách tổ chức, không có phương án đúng cho mọi trường hợp.

### 9.1. Transaction nhiều document

Nếu cần cập nhật nguồn và giá trị derived cùng thành công hoặc cùng hủy, MongoDB hỗ trợ multi-document transaction trong cấu hình thích hợp.

~~~text
Bắt đầu transaction
  -> ghi review hợp lệ
  -> cập nhật thống kê/preview
Commit
~~~

Transaction đem lại một ranh giới nhất quán rõ ràng, nhưng thêm chi phí vận hành và khả năng xung đột/retry. Cần giữ transaction ngắn và không đặt các công việc mạng hoặc xử lý dài bên trong. Ngoài ra, thao tác tạo review có thể cần kiểm soát duy nhất một lần theo `reviewId` trước khi tính thống kê.

### 9.2. Event-driven và eventual consistency

Nếu chấp nhận hiển thị trễ trong thời gian ngắn:

~~~text
Write review -> phát sự kiện -> worker xử lý -> cập nhật products
                                            |
                                            +-> lỗi -> retry / dead letter / đối soát
~~~

Yêu cầu gồm event ID duy nhất, idempotency, giám sát hàng đợi, replay và cách xử lý cập nhật đến sai thứ tự. Dữ liệu derived phải có khả năng tính lại từ nguồn để chữa sai lệch.

### 9.3. Batch/rebuild

Một công việc định kỳ có thể tổng hợp nguồn và ghi lại bản computed hoặc subset. Batch đơn giản cho số liệu không cần realtime, nhưng có thể cần nhiều I/O. Khi rebuild, không được để kết quả tính cũ từ batch ghi đè giá trị mới mà luồng sự kiện vừa cập nhật; có thể dùng watermark, version hoặc cơ chế chuyển đổi/đối soát có kiểm soát.

### 9.4. Ví dụ về xử lý review bị chỉnh sửa

Giả sử một review đang có `rating = 5`, sau đó bị sửa thành `rating = 3`:

- `reviews` ghi giá trị mới hoặc lịch sử thay đổi theo chính sách.
- `reviewStats.count` vẫn không đổi nếu review tiếp tục hợp lệ.
- `reviewStats.ratingSum` giảm 2.
- `latestReviewPreview` cập nhật nếu review nằm trong subset đang hiển thị.
- Nếu review chuyển sang `HIDDEN`, cần loại khỏi cả thống kê và preview.
- Nếu cùng message được giao lại, không được trừ thêm 2 lần.

Mẫu nào cũng đòi hỏi xác định **trạng thái cũ, trạng thái mới và sự kiện chuyển tiếp**; không thể chỉ tăng bộ đếm ở mọi lần nhận thông báo.

## 10. Chọn pattern bằng các câu hỏi cụ thể

| Câu hỏi thực tế | Pattern đáng cân nhắc | Vì sao |
| --- | --- | --- |
| Hồ sơ người dùng có 10.000 phiên truy cập, trang profile chỉ cần 3 phiên mới nhất? | Subset | Bản đầy đủ ở collection riêng, phần nóng hữu hạn trong profile. |
| Trang sản phẩm gọi 10.000 lần/giờ, review mới chỉ vài lần/giờ? | Computed | Đọc thống kê tính trước thay vì group review ở mỗi request. |
| Máy cảm biến tạo 500.000 bản ghi nhỏ/ngày, API thường đọc theo giờ? | Bucket hoặc time series collection | Gom hoặc tổ chức dữ liệu theo thời gian để cải thiện đường đọc và lưu trữ. |
| Sản phẩm có hàng trăm trường kỹ thuật khác nhau và filter theo tên thuộc tính? | Attribute | Dùng cấu trúc truy vấn thống nhất cho thuộc tính động. |
| Collection ít trường, tài liệu nhỏ, query đã dùng index tốt? | Có thể không cần pattern | Thêm lớp mô hình hóa có thể chỉ làm tăng phức tạp. |
| Mọi thuộc tính được dùng chung trong mỗi request, thay đổi cùng nhau? | Embedding đơn giản | Không có lợi thế rõ từ tách subset. |
| Giá trị computed là số dư cần đúng ngay sau giao dịch? | Cần thiết kế consistency trước | Không tự chấp nhận eventual consistency chỉ vì dùng Computed. |
| Cập nhật từng sự kiện độc lập với tần suất rất cao? | Cân nhắc document riêng | Bucket có thể biến thành điểm nóng ghi. |

## 11. Đánh giá query plan và hiệu năng trước/sau

Không nên áp dụng mẫu mới chỉ vì tài liệu hướng dẫn nói pattern đó “nhanh hơn”. Hãy đo workload bằng dữ liệu đại diện.

~~~javascript
db.products.find({
  category: "laptop",
  status: "ACTIVE",
  attributes: {
    $elemMatch: {
      key: "ramGb",
      numberValue: { $gte: 16 }
    }
  }
}).explain("executionStats");
~~~

Các chỉ số cần đọc gồm số bản ghi trả về, số khóa/document đã kiểm tra, kế hoạch `IXSCAN`/`COLLSCAN`, thời gian truy vấn trong thử nghiệm và mức tiêu thụ tài nguyên. Trên môi trường thật, theo dõi thêm p95/p99 latency, CPU, bộ nhớ đệm, read/write IOPS, kích thước index và write throughput.

Ví dụ đánh giá:

| Trước khi thay đổi | Sau khi thay đổi | Cần kết luận dựa trên |
| --- | --- | --- |
| Tải sản phẩm nhúng hàng nghìn review | Đọc preview và phân trang review riêng | p95 chi tiết sản phẩm, dung lượng document, số read I/O, chi phí đồng bộ. |
| Tính rating bằng aggregation mỗi request | Đọc `reviewStats` | p95 và CPU giảm bao nhiêu, độ trễ cập nhật chấp nhận được không. |
| Mỗi phép đo là một document | Gom theo bucket có giới hạn | Dung lượng/index, throughput ghi, truy vấn theo khoảng và contention. |
| Hàng trăm field động, nhiều index riêng | Attribute + index theo cặp key/value | Chất lượng query plan, dung lượng index, số filter đồng thời và chi phí ingest. |

**Hiệu năng đọc tốt hơn nhưng ghi sai hoặc dữ liệu không đồng bộ** không phải thành công. Phải đánh giá tính đúng đắn và độ mới cùng với độ trễ.

## 12. Các giới hạn và rủi ro chung

### 12.1. Document tối đa 16 MiB

Subset giúp giảm document chính; Bucket vẫn cần giới hạn; Attribute chứa mảng có thể tăng mạnh khi số thuộc tính quá nhiều. Không được dùng một trong các mẫu này để giả định rằng MongoDB đã bỏ giới hạn 16 MiB.

### 12.2. Dữ liệu trùng lặp và khả năng đối soát

Computed và Subset thường sao chép hoặc lưu giá trị suy ra. Hãy xác định nguồn chuẩn, cơ chế rebuild và cách phát hiện sai lệch; không để hai bản cùng được cập nhật độc lập mà thiếu quy tắc phân xử.

### 12.3. Index có chi phí

Attribute và Bucket có thể cần index multikey hoặc compound index; Subset cần index trên collection con; Computed cần index theo chiều đọc dashboard. Mỗi index tăng dung lượng và làm thao tác ghi tốn hơn. Cần định kỳ đánh giá index không được sử dụng và workload thực tế.

### 12.4. Hot document và tranh chấp cập nhật

Computed counter trên một sản phẩm cực kỳ phổ biến hoặc một bucket nhận hàng nghìn update đồng thời có thể trở thành điểm nóng. Một document có atomic update không đồng nghĩa throughput sẽ tăng vô hạn. Có thể cần partition counter, batch, chia bucket hay thiết kế đường ghi khác; nhưng mỗi phương án lại thêm chi phí tổng hợp và nhất quán.

### 12.5. Schema versioning và migration

Khi chuyển từ embedded reviews sang Subset, hay từ field `ramGb` sang `attributes`, dữ liệu cũ và mới có thể cùng tồn tại trong thời gian triển khai. Ứng dụng cần quy tắc đọc tương thích, backfill, ghi hai định dạng có kiểm soát nếu cần và thời điểm bỏ đường cũ. Migration phải có khả năng kiểm đếm số bản ghi, phát hiện dữ liệu thiếu và rollback hoặc phục hồi theo kế hoạch.

### 12.6. Idempotency và thứ tự sự kiện

Những hệ thống event-driven thường giao sự kiện **ít nhất một lần**, không bảo đảm mỗi event chỉ đến đúng một lần hay đến theo thứ tự nghiệp vụ trên mọi đường xử lý. Đếm bằng `$inc` hoặc `$push` mà không kiểm soát idempotency có thể gây dữ liệu trùng. Cần ràng buộc event ID, thứ tự/version hoặc dựng lại dữ liệu từ nguồn khi cần.

## 13. Các lỗi thiết kế thường gặp và cách sửa

### Lỗi 1: Subset biến thành bản sao toàn bộ

Document `products` giữ 3 review đầu tiên lúc triển khai, rồi tăng thành 20, 100 và cuối cùng chứa mọi review. Subset mất vai trò giảm working set. Sửa bằng cách định nghĩa **giới hạn rõ**, dùng collection `reviews` cho dữ liệu đầy đủ và chính sách cập nhật preview.

### Lỗi 2: Computed count tăng hai lần do retry

Một sự kiện thêm review gửi lại hai lần khiến `reviewCount` tăng 2. Sửa bằng idempotency key, transaction với bản ghi trạng thái đã xử lý hoặc mô hình cập nhật có thể xác minh, cộng với job đối soát.

### Lỗi 3: Bucket theo ngày nhưng không giới hạn bytes

Một thiết bị tăng đột biến dữ liệu, document bucket vượt 16 MiB trước khi kết thúc ngày. Sửa bằng giới hạn kết hợp thời gian, số phần tử và bytes, quy tắc đóng bucket và chuyển sang bucket tiếp theo.

### Lỗi 4: Attribute lọc sai phần tử

Truy vấn dùng hai dotted path riêng và ghép `ramGb` với giá trị `storageGb`, trả laptop RAM 8 GB trong bộ lọc RAM >= 16 GB. Sửa bằng `$elemMatch` cho các điều kiện phải nằm trong cùng phần tử và index theo access pattern.

### Lỗi 5: Đưa tất cả field vào Attribute

Ngay cả `priceMinor`, `status`, `sellerId` đều thành phần tử key–value, làm các truy vấn căn bản phức tạp và index khó tối ưu. Sửa bằng việc giữ field phổ biến ổn định ở document gốc, chỉ chuyển các thuộc tính biến thiên có lý do rõ ràng.

### Lỗi 6: Xem computed result là dữ liệu nguồn

Khi computed stats bị sai, không còn dữ liệu sự kiện để dựng lại. Sửa bằng cách định nghĩa source of truth và retention trước khi tạo computed projection. Nếu bắt buộc hủy nguồn theo quy định lưu trữ, phải có quy trình lưu/kiểm toán phù hợp với yêu cầu đó.

## 14. Bài tập thiết kế: một nền tảng học trực tuyến

Giả sử một nền tảng học có:

- Mỗi khóa học có thể có hàng nghìn nhận xét; trang giới thiệu chỉ cần năm nhận xét mới nhất.
- Trang chủ hiển thị số học viên hoàn thành và điểm đánh giá trung bình.
- Một học viên tạo nhiều sự kiện xem video theo từng phút.
- Mỗi khóa học có metadata tùy theo môn học: cấp độ, ngôn ngữ, chứng chỉ, công cụ thực hành.

**Gợi ý tổ chức:**

~~~javascript
// courses
{
  _id: "COURSE-JAVA-01",
  title: "Java Fundamentals",
  category: "programming",
  stats: {
    completionCount: 1800,
    ratingCount: 430,
    ratingSum: 1910
  },                              // Computed
  latestReviewPreview: [
    { reviewId: "RV1", rating: 5, excerpt: "Dễ hiểu" }
  ],                              // Subset
  attributes: [
    { key: "level", stringValue: "beginner" },
    { key: "language", stringValue: "vi" }
  ]                               // Attribute
}

// courseReviews: review đầy đủ theo courseId
// playbackBuckets: sự kiện playback có giới hạn theo học viên và khoảng giờ
~~~

Các câu hỏi cần trả lời trước khi triển khai:

1. Nếu nhận xét bị ẩn, cập nhật preview và thống kê bằng cách nào?
2. `completionCount` được tính theo học viên duy nhất hay theo số lượt hoàn thành? Làm sao chống cộng trùng khi sự kiện được retry?
3. Nếu một học viên tua video 1.000 lần trong một giờ, bucket có vượt giới hạn số phần tử hoặc document không?
4. Có cần tìm khóa học theo hai thuộc tính khác nhau đồng thời không? Query `$elemMatch` và index sẽ được thiết kế thế nào?
5. Metadata nào nên là field cố định và metadata nào thực sự là thuộc tính linh hoạt?
6. Dữ liệu thống kê được phép chậm bao lâu? Trang công khai và hệ thống cấp chứng chỉ có cùng yêu cầu nhất quán hay không?

Bài tập này nhấn mạnh rằng lựa chọn pattern phải gắn với **định nghĩa nghiệp vụ**, không chỉ với hình dạng JSON.

## 15. Một quy trình thực hành để quyết định

1. **Liệt kê các truy vấn và thao tác ghi trọng yếu.** Ghi lại filter, sort, số document/field cần trả, tần suất, độ trễ mong muốn và yêu cầu consistency.
2. **Đánh dấu dữ liệu tăng trưởng.** Xác định mảng vô hạn, event, file lớn, metadata mở rộng và giá trị tổng hợp tốn kém.
3. **Chọn đường đọc quan trọng nhất.** Nếu 95% request chỉ cần phần nhỏ, cân nhắc Subset; nếu liên tục tính cùng aggregate, cân nhắc Computed.
4. **Xem nhóm bản ghi nhỏ.** Nếu truy vấn thường đọc theo thiết bị/khoảng thời gian, đánh giá Bucket và time series collection; đừng bỏ qua nguy cơ hot document.
5. **Xem tính linh hoạt của thuộc tính.** Nếu nhiều field động cần filter, thử Attribute và index; với field ổn định, giữ schema trực tiếp.
6. **Định nghĩa nguồn chuẩn và cách cập nhật.** Từng bản sao/giá trị derived phải có chủ sở hữu, chính sách stale, rebuild, retry và validation.
7. **Tạo dữ liệu đủ lớn để thử nghiệm.** Đo query plan, p95/p99, storage, index size, write throughput và lỗi dưới đồng thời.
8. **Kiểm tra trường hợp cực trị.** Review bị xóa, event đến muộn/trùng, bucket đầy, sản phẩm có hàng nghìn thuộc tính, nhiều worker cập nhật cùng lúc.
9. **Triển khai có thể quan sát.** Theo dõi tuổi dữ liệu computed/subset, số lỗi đồng bộ, số bucket gần đầy và hiệu năng truy vấn mới.
10. **Đánh giá lại sau tăng trưởng.** Một schema hợp lý ở 10.000 document có thể cần điều chỉnh khi workload và phân phối dữ liệu thay đổi.

## 16. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Subset chỉ là projection.” | Projection chọn dữ liệu trả về; Subset tổ chức lại dữ liệu lưu trữ và nguồn đầy đủ. |
| “Subset nghĩa là không bao giờ lưu trùng.” | Preview thường là bản sao có kiểm soát của dữ liệu trong collection khác. |
| “Computed tự động luôn chính xác.” | Phải xác định update, retry, idempotency, event trễ và đối soát. |
| “Có `$inc` là event xử lý đúng một lần.” | `$inc` nguyên tử trên document nhưng gọi lặp vẫn tăng lặp. |
| “Bucket vượt được 16 MiB.” | Mỗi bucket vẫn là BSON document chịu giới hạn 16 MiB. |
| “Bucket càng lớn càng tiết kiệm.” | Bucket lớn có thể tốn cập nhật, gây contention và khó truy vấn từng điểm. |
| “Bucket pattern là time series collection.” | Một cái là mẫu thiết kế ứng dụng, một cái là khả năng tổ chức dữ liệu theo thời gian của MongoDB. |
| “Attribute phải chuyển tất cả field vào mảng.” | Field ổn định và dùng thường xuyên thường nên ở mức gốc. |
| “Dùng dotted path trên mảng là đủ để các điều kiện cùng phần tử.” | Cần `$elemMatch` khi các ràng buộc phải khớp trên cùng phần tử. |
| “Một index attribute giải quyết mọi tổ hợp filter.” | Multikey index có giới hạn và chi phí; phải kiểm tra query plan thực. |
| “Pattern tối ưu đọc luôn giảm tổng chi phí.” | Thường tăng số lần ghi, storage, index hoặc độ phức tạp đồng bộ. |

## 17. Tổng kết lựa chọn

- Chọn **Subset** khi nhiều request chỉ cần phần nóng, nhỏ và hữu hạn của một đối tượng có phần dữ liệu đầy đủ lớn hơn.
- Chọn **Computed** khi cùng phép tính được đọc rất thường xuyên và có quy trình duy trì, đo độ mới và tái tính toán đáng tin cậy.
- Chọn **Bucket** khi nhiều bản ghi nhỏ tự nhiên được truy cập theo nhóm, nhưng vẫn phải có ranh giới thời gian, số phần tử, kích thước và giải pháp tránh hot document.
- Chọn **Attribute** khi các thuộc tính biến thiên cần được tìm kiếm theo cấu trúc thống nhất, với kiểu dữ liệu, đơn vị và truy vấn mảng được kiểm soát.

Mẫu thiết kế tốt là mẫu làm các đường truy cập quan trọng **đơn giản hơn và đo được hiệu quả**, trong khi tính đúng đắn, giới hạn document và quy trình vận hành vẫn được đảm bảo. Một document model hiệu quả không bắt đầu từ việc “nhét được bao nhiêu JSON”, mà từ việc hệ thống cần đọc, ghi, đối soát và mở rộng dữ liệu như thế nào.

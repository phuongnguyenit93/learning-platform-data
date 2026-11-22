# Mảng tăng không giới hạn, document quá lớn và document bị ghi tập trung

MongoDB cho phép nhúng object và array vào **BSON document**, vì vậy ứng dụng có thể lưu cả một đơn vị nghiệp vụ và lấy về bằng một truy vấn. Tuy nhiên, document không phải vùng chứa vô hạn và cũng không phải một đơn vị ghi có thể mở rộng vô hạn chỉ bằng cách thêm máy chủ. Khi thiết kế ranh giới document không phù hợp với dữ liệu thực tế, ba vấn đề thường xuất hiện cùng nhau:

1. **Mảng tăng không giới hạn (unbounded array):** liên tục thêm phần tử bằng `$push` hoặc `$addToSet` mà không có chính sách giới hạn.
2. **Document quá lớn:** phần dữ liệu nhúng phình to, làm tăng chi phí đọc/ghi và cuối cùng có thể chạm giới hạn **16 MiB BSON/document**.
3. **Document bị ghi tập trung (hot document):** nhiều request cùng sửa một document, tạo cạnh tranh tài nguyên và giới hạn thông lượng dù collection có hàng triệu document khác.

Trong mô hình document, quyết định nhúng hay tham chiếu cần dựa vào **số phần tử tối đa, cách đọc, cách ghi, vòng đời dữ liệu và mức đồng thời**, không chỉ vào việc hai thực thể có quan hệ cha–con.

## 1. Document là ranh giới dữ liệu và ranh giới cập nhật

Ví dụ một đơn hàng có vài dòng sản phẩm:

```javascript
{
  _id: ObjectId("65a12f010000000000000001"),
  customerId: "C100",
  status: "PAID",
  items: [
    { sku: "B01", quantity: 2, unitPrice: NumberDecimal("15.00") },
    { sku: "P02", quantity: 1, unitPrice: NumberDecimal("5.00") }
  ]
}
```

Đây là trường hợp thuận lợi cho **embedding**: dòng hàng thường được đọc cùng đơn hàng, có giới hạn hợp lý, cùng vòng đời với đơn hàng và lưu giá sản phẩm tại thời điểm mua.

Ngược lại, một bài viết có thể nhận hàng triệu bình luận:

```javascript
{
  _id: ObjectId("65a12f010000000000000002"),
  title: "Giới thiệu MongoDB",
  comments: [
    { userId: "u1", text: "...", createdAt: ISODate("2026-01-01") },
    { userId: "u2", text: "...", createdAt: ISODate("2026-01-02") }
    // Bình luận mới sẽ tiếp tục được thêm vào mảng.
  ]
}
```

Mọi bình luận mới đều làm document cha tăng kích thước. Các thao tác sửa, xóa, kiểm duyệt bình luận cũng tác động vào cùng document; truy vấn lấy trang thứ 1.000 của bình luận khó tối ưu hơn khi mỗi bình luận là một document có index riêng.

Ba câu hỏi để phân biệt:

- **Cardinality có trần thật không?** Năm địa chỉ giao hàng khác với hàng triệu comment, log hoặc reaction.
- **Thành phần con có được đọc cùng document cha trong phần lớn thao tác không?** Mảng item đơn hàng khác với comment tải 20 bản ghi mỗi trang.
- **Các thao tác ghi có tập trung vào một cha không?** Profile mỗi user tự cập nhật khác với bài viết viral có hàng nghìn writer đồng thời.

MongoDB bảo đảm **tính nguyên tử của cập nhật một document**, kể cả khi sửa nhiều trường hoặc phần tử mảng trong document đó. Tính nguyên tử hữu ích, nhưng không làm cho mọi mô hình nhúng trở nên tốt ở mọi quy mô.

## 2. Mảng tăng không giới hạn: một anti-pattern phổ biến

**Unbounded array** là array có số phần tử tăng theo hoạt động liên tục của ứng dụng mà không có giới hạn hoặc chính sách tách dữ liệu rõ ràng.

```javascript
db.posts.updateOne(
  { _id: postId },
  {
    $push: {
      comments: {
        authorId: "u42",
        text: "Bài viết hữu ích!",
        createdAt: new Date()
      }
    }
  }
);
```

Câu lệnh hợp lệ. Rủi ro phát sinh khi 10, 10.000 rồi 1.000.000 phần tử đều được thêm vào **một document**.

| Hệ quả | Tác động |
|---|---|
| Kích thước tăng | Mỗi phần tử mới góp thêm dữ liệu BSON, tên trường, mảng và overhead |
| Giới hạn document | Có thể vượt mức BSON tối đa 16 MiB khiến thao tác ghi thất bại |
| Đọc dư dữ liệu | Client tải quá nhiều phần tử nếu truy vấn không projection đúng |
| Index multikey | Index trên phần tử array có thể tăng nhiều khóa index và chi phí duy trì |
| Cập nhật khó phân tán | Nhiều writer cùng sửa một document thay vì những document độc lập |
| Phân trang phức tạp | Khó index/sort/filter từng phần tử độc lập ở quy mô lớn |
| Vòng đời khó tách | Xóa hoặc lưu trữ lạnh một phần dữ liệu cần sửa document lớn |

**Không nên suy luận rằng mỗi `$push` luôn ghi lại nguyên 16 MiB vào ổ đĩa.** WiredTiger có cơ chế cache, page và cập nhật nội bộ. Vấn đề bền vững của mô hình là số phần tử tăng không giới hạn, chi phí duy trì dữ liệu/index, kích thước payload và contention.

### 2.1. Vì sao `$addToSet` không giải quyết vấn đề?

```javascript
db.posts.updateOne(
  { _id: postId },
  { $addToSet: { likedUserIds: userId } }
);
```

`$addToSet` tránh thêm giá trị đã có theo quy tắc so sánh array của MongoDB, nhưng nó vẫn làm mảng tăng theo số **userId khác nhau**. Một triệu lượt thích từ một triệu tài khoản có thể dẫn đến một triệu phần tử. “Không trùng” không đồng nghĩa với “có giới hạn”.

Nếu cần enforce mỗi người chỉ thích một bài viết một lần, có thể dùng collection quan hệ `postLikes` chứa mỗi cặp `(postId, userId)` thành một document, kèm unique index.

### 2.2. Khi nào mảng nhúng vẫn hợp lý?

Nhúng phù hợp với mảng **có trần và có vòng đời đi cùng cha**:

- Vài địa chỉ hoặc phương thức liên hệ của user.
- Dòng hàng của đơn đặt mua có quy tắc giới hạn số item.
- Các bước cố định của một quy trình nhỏ.
- Một số tag hay thuộc tính ít thay đổi.
- Mười hoạt động mới nhất được lưu như cache hiển thị.

Không có quy tắc kiểu “mảng trên 100 phần tử luôn xấu”. Mười phần tử cực lớn vẫn có thể làm document nặng, trong khi vài trăm giá trị nhỏ, ít cập nhật có thể chấp nhận được. Cần xét **số phần tử × kích thước mỗi phần tử × tần suất đọc/ghi**.

## 3. Document quá lớn: giới hạn 16 MiB và ảnh hưởng hiệu năng

Một BSON document trong MongoDB có giới hạn **16 MiB** (16 × 1.048.576 byte). Giới hạn áp dụng cho toàn bộ BSON document, bao gồm field name, giá trị, object/array lồng nhau và overhead biểu diễn BSON; không chỉ số ký tự JSON khi in ra màn hình.

```text
Collection posts:
  post A: metadata + 8 comments       -> nhỏ
  post B: metadata + 90.000 comments  -> tăng rất lớn
  post C: metadata + 5.000.000 comments -> không thể nhúng mãi

Giới hạn 16 MiB áp dụng cho TỪNG document,
không phải tổng kích thước collection.
```

Thêm RAM, ổ đĩa hoặc shard không làm một BSON document được phép lớn hơn 16 MiB. **Sharding phân bố document**, không tự tách một document quá lớn thành các phần nằm trên nhiều shard.

Nếu yêu cầu lưu **tệp nhị phân lớn** như PDF/video, có thể xem xét GridFS (lưu nội dung thành các chunk) hoặc object storage. GridFS không phải giải pháp mặc định cho hàng triệu bình luận cần query/sort/update riêng; trường hợp đó nên là những document con độc lập.

### 3.1. Đo kích thước BSON

Trong `mongosh` có thể đo kích thước một document:

```javascript
const post = db.posts.findOne({ _id: postId });

if (post) {
  const bytes = Object.bsonsize(post);
  print("Document bytes: " + bytes);
  print("Document MiB: " + (bytes / (1024 * 1024)).toFixed(2));
}
```

MongoDB aggregation có biểu thức `$bsonSize`, hữu ích khi muốn tìm những document lớn:

```javascript
db.posts.aggregate([
  {
    $project: {
      title: 1,
      bsonBytes: { $bsonSize: "$$ROOT" },
      commentsCount: {
        $cond: [
          { $isArray: "$comments" },
          { $size: "$comments" },
          0
        ]
      }
    }
  },
  { $sort: { bsonBytes: -1 } },
  { $limit: 10 }
]);
```

Pipeline có thể cần đọc nhiều document, vì vậy hãy thử trên môi trường phù hợp hoặc chạy có kiểm soát đối với collection lớn. `$bsonSize` đo dữ liệu BSON logic, không phải byte nén mà WiredTiger cấp phát trên đĩa.

Thống kê tổng quan:

```javascript
db.posts.stats();
db.posts.dataSize();
db.posts.storageSize();
db.posts.totalIndexSize();
```

`dataSize`, `storageSize` và `totalIndexSize` phản ánh các khía cạnh khác nhau. Chúng không thể dùng thay thế cho kích thước BSON cụ thể của một document.

### 3.2. Projection giảm payload, nhưng không làm mảng trong DB nhỏ đi

```javascript
db.posts.findOne(
  { _id: postId },
  { title: 1, authorId: 1, createdAt: 1 }
);
```

Projection giúp không trả toàn bộ mảng về ứng dụng. Có thể dùng `$slice` để chỉ trả vài phần tử:

```javascript
db.posts.findOne(
  { _id: postId },
  { title: 1, comments: { $slice: -10 } }
);
```

Nhưng **projection chỉ thay đổi kết quả đọc**, không xóa dữ liệu cũ trong document, không nâng giới hạn 16 MiB và không giảm số writer cùng sửa document. Nếu đang có mảng tăng vô hạn, phải sửa **luồng lưu trữ**, không chỉ sửa query.

## 4. Reference pattern: mỗi thành phần con là một document riêng

Với quan hệ một–nhiều có số phần tử không giới hạn, thay mảng nhúng bằng collection riêng:

```javascript
// posts
{
  _id: ObjectId("65a12f010000000000000002"),
  authorId: "u1",
  title: "Giới thiệu MongoDB",
  createdAt: ISODate("2026-03-01T10:00:00Z")
}

// comments
{
  _id: ObjectId("65a12f020000000000000001"),
  postId: ObjectId("65a12f010000000000000002"),
  authorId: "u42",
  text: "Bài viết hữu ích!",
  createdAt: ISODate("2026-03-02T09:00:00Z"),
  status: "VISIBLE"
}
```

Mỗi lần thêm bình luận sẽ tạo một document độc lập:

```javascript
db.comments.insertOne({
  postId,
  authorId: "u42",
  text: "Bài viết hữu ích!",
  createdAt: new Date(),
  status: "VISIBLE"
});
```

Số bình luận tăng không làm kích thước BSON của document `posts` tăng tương ứng. Mỗi comment cũng có vòng đời, quyền truy cập và thao tác sửa/ẩn riêng.

### 4.1. Index cho phân trang bình luận

```javascript
db.comments.createIndex({
  postId: 1,
  createdAt: -1,
  _id: -1
});

db.comments.find({ postId })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
```

Compound index bắt đầu bằng `postId` cho điều kiện equality, sau đó theo `createdAt` và `_id` để hỗ trợ thứ tự mới nhất. `_id` là khóa phụ phá hòa nếu nhiều comment có cùng timestamp.

Khi lấy trang tiếp theo, dùng cursor từ bản ghi cuối trang trước:

```javascript
const lastCreatedAt = ISODate("2026-03-02T09:00:00Z");
const lastId = ObjectId("65a12f020000000000000001");

db.comments.find({
  postId,
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    { createdAt: lastCreatedAt, _id: { $lt: lastId } }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

Ví dụ giả định `lastCreatedAt` và `lastId` là của bản ghi cuối trang trước. **Keyset pagination** thường tránh được chi phí bỏ qua nhiều bản ghi như `skip()` sâu. Vẫn cần quan sát `explain()` và các index thực tế, đặc biệt khi kết hợp điều kiện `status` hay phân quyền.

### 4.2. Chi phí và trách nhiệm khi dùng reference

Reference có thể cần nhiều truy vấn để tải parent và children; đôi khi dùng `$lookup` nếu thật sự cần join. Khi xóa cha, MongoDB không tự áp đặt foreign key/cascade như một RDBMS điển hình: ứng dụng phải có quy trình xóa/ẩn con. Nếu cần cập nhật nhiều document nguyên tử, cân nhắc transaction trong môi trường được hỗ trợ.

Đây là đánh đổi hợp lý cho bình luận, lịch sử hoạt động, giao dịch chi tiết không giới hạn và các dữ liệu có vòng đời độc lập.

## 5. Bounded array: giữ tập nhỏ cần hiển thị

Nếu giao diện chỉ cần 10 hoạt động gần nhất, có thể dùng **bounded array**. Modifier `$push` với `$each`, `$sort` và `$slice` giới hạn số phần tử được giữ:

```javascript
db.userDashboards.updateOne(
  { _id: userId },
  {
    $push: {
      recentActivities: {
        $each: [
          {
            eventId: new ObjectId(),
            label: "Đã đăng nhập",
            createdAt: new Date()
          }
        ],
        $sort: { createdAt: -1 },
        $slice: 10
      }
    }
  }
);
```

Ở đây `$sort: { createdAt: -1 }` xếp phần tử mới nhất lên đầu, còn `$slice: 10` giữ mười phần tử đầu. Một cách khác, nếu chỉ append theo thứ tự đến và không cần sort theo timestamp, là giữ 20 phần tử cuối:

```javascript
db.userDashboards.updateOne(
  { _id: userId },
  {
    $push: {
      recentActions: {
        $each: [newAction],
        $slice: -20
      }
    }
  }
);
```

**Lưu ý:** bounded array bảo vệ khỏi tăng kích thước vô hạn nhưng **không tự giải quyết hot document**. Nếu mỗi giây vẫn có hàng nghìn request sửa `userDashboards[_id=...]`, contention vẫn có thể xảy ra.

### 5.1. Snapshot nhỏ và nguồn dữ liệu lịch sử

Có thể lưu toàn bộ hoạt động tại `activities` rồi duy trì mười hoạt động mới nhất trong `userDashboards.recentActivities` như snapshot:

```text
activities               ← dữ liệu lịch sử chuẩn
   |
   +--> API phân trang theo userId / createdAt
   |
   +--> userDashboards.recentActivities
        (snapshot tối đa 10 mục cho màn hình tổng quan)
```

Nếu việc ghi hai collection không nằm trong một transaction, snapshot có thể trễ hoặc tạm khác dữ liệu gốc. Cần định nghĩa **nguồn dữ liệu chuẩn**, khả năng dựng lại snapshot, retry và mức nhất quán được chấp nhận.

## 6. Bucket pattern: giới hạn mỗi phần lưu trữ

**Bucket pattern** lưu một nhóm sự kiện trong mỗi document, phân theo thiết bị và thời gian hoặc một khóa phân vùng khác. Thay vì document thiết bị chứa toàn bộ lịch sử:

```javascript
{ _id: deviceId, events: [ /* hàng triệu sự kiện */ ] }
```

có thể tạo nhiều bucket:

```javascript
{
  _id: "sensor-101/2026-03-01T10",
  deviceId: "sensor-101",
  hourStart: ISODate("2026-03-01T10:00:00Z"),
  events: [
    { at: ISODate("2026-03-01T10:00:05Z"), temperature: 24.1 },
    { at: ISODate("2026-03-01T10:00:10Z"), temperature: 24.3 }
  ],
  eventCount: 2
}
```

Bucket tiếp theo có thể ứng với giờ khác hoặc được tạo khi bucket đạt ngưỡng phần tử/kích thước. Lợi ích: giảm số document so với lưu từng event, tổ chức dữ liệu theo khoảng truy cập và giới hạn kích thước từng document.

Nhưng không nên cho rằng một bucket là giải pháp hoàn hảo: nếu hàng nghìn writer cùng chèn sự kiện vào **bucket hiện tại** của một thiết bị, bucket đó lại trở thành hot document. Cần chọn cửa sổ thời gian, số partition hoặc chuyển sang document event riêng theo workload.

### 6.1. Kiểm soát bucket đầy bằng điều kiện nguyên tử

Ví dụ cập nhật một bucket đã tồn tại và chưa đủ 500 event:

```javascript
const result = db.buckets.updateOne(
  {
    _id: bucketId,
    eventCount: { $lt: 500 }
  },
  {
    $push: { events: event },
    $inc: { eventCount: 1 }
  }
);

if (result.modifiedCount === 0) {
  // Có thể bucket đã đầy, không tồn tại hoặc điều kiện không còn đúng.
  // Xác minh trạng thái rồi chọn bucket khác.
}
```

Filter và update chạy nguyên tử trên document. Tuy nhiên đây chỉ là **minh họa**: thiết kế hoàn chỉnh phải có cách tạo/chuyển bucket an toàn khi nhiều writer đồng thời, unique key, retry/idempotency, và giới hạn kích thước **từng event**. Giới hạn 500 phần tử không tự bảo đảm dưới 16 MiB nếu mỗi event lớn.

### 6.2. Time-series collection cho dữ liệu đo theo thời gian

MongoDB có **time-series collection** được tối ưu cho dữ liệu telemetry theo timestamp và metadata:

```javascript
db.createCollection("measurements", {
  timeseries: {
    timeField: "measuredAt",
    metaField: "deviceId",
    granularity: "seconds"
  }
});

db.measurements.insertOne({
  deviceId: "sensor-101",
  measuredAt: new Date(),
  temperature: 24.3
});
```

Time-series collection có cơ chế bucket và các giới hạn về update/delete, index, sharding và phiên bản riêng. Nó thích hợp với phép đo có thời gian; không tự động phù hợp cho comment cần kiểm duyệt/sửa từng bản ghi.

## 7. Outlier pattern: xử lý trường hợp cực lớn

Nhiều ứng dụng có phân bố lệch: phần lớn bài viết có ít bình luận nhưng vài bài viral có hàng triệu. **Outlier pattern** nhận diện trường hợp khác biệt để lưu theo cách riêng, hoặc kết hợp nhúng một snapshot nhỏ với toàn bộ dữ liệu con ở collection riêng:

```javascript
// posts: metadata + snapshot nhỏ
{
  _id: postId,
  title: "Bài viết",
  recentComments: [ /* tối đa 10 mục */ ],
  commentCountApprox: 1500000
}

// comments: nguồn lịch sử đầy đủ
{
  _id: commentId,
  postId,
  authorId: "u42",
  text: "...",
  createdAt: ISODate("2026-03-10T12:00:00Z")
}
```

Nếu dùng hai schema (bài nhỏ nhúng, bài lớn tham chiếu), phải xử lý chuyện vượt ngưỡng, migration và đường đọc tương ứng. Đôi khi lưu toàn bộ comment ở collection con từ đầu, giữ `recentComments` như cache, sẽ đơn giản hơn. Chọn mô hình sau khi cân nhắc tần suất đọc và độ phức tạp vận hành.

## 8. Hot document: nguyên tử không đồng nghĩa ghi song song vô hạn

MongoDB hỗ trợ cập nhật nguyên tử trên một document, nhưng nhiều writer cùng sửa một document phải phối hợp để không phá vỡ dữ liệu. Ví dụ lượt thích một bài viral:

```javascript
db.posts.updateOne(
  { _id: viralPostId },
  { $inc: { likeCount: 1 } }
);
```

`$inc` giúp mỗi phép tăng là thao tác nguyên tử. Tuy vậy, nếu mọi request cùng tăng `likeCount` của **một document duy nhất**, hệ thống vẫn có điểm tranh chấp; tăng nhiều node không tự chia phép ghi vào document đó.

### 8.1. Tránh lost update trước khi tối ưu tải

Mẫu dễ mất dữ liệu:

```javascript
// Hai request cùng đọc likeCount = 100.
const current = db.posts.findOne({ _id: postId }).likeCount;

// Cả hai cùng set thành 101: một lượt tăng bị mất.
db.posts.updateOne(
  { _id: postId },
  { $set: { likeCount: current + 1 } }
);
```

Mẫu dùng toán tử nguyên tử:

```javascript
db.posts.updateOne(
  { _id: postId },
  { $inc: { likeCount: 1 } }
);
```

Cách hai đúng hơn về phép cộng đơn giản nhưng vẫn tạo **một điểm ghi**. Các lỗi write conflict, retry, độ trễ và giới hạn throughput có thể xuất hiện dưới tải lớn.

### 8.2. Hot document không nhất thiết là document lớn

| Ví dụ | Nguồn contention |
|---|---|
| Bài viral | Nhiều request tăng lượt xem/thích hay thêm bình luận |
| Bộ đếm toàn hệ thống | Mọi event tăng một trường chung |
| Bucket giờ hiện tại của sensor | Nhiều writer cùng `$push` vào một mảng |
| Trạng thái tài khoản phổ biến | Nhiều tác vụ cập nhật một đối tượng |
| Giỏ hàng được nhiều tác nhân sửa | Các thao tác ghi trên cùng document |
| Document cấu hình dùng làm distributed lock | Nhiều tiến trình tranh quyền sửa/lease |

Document chỉ có vài byte vẫn có thể rất nóng. Ngược lại, document hàng trăm kilobyte chỉ đọc và hiếm khi ghi có thể không gây contention đáng kể.

### 8.3. Trường hợp nên giữ cập nhật nguyên tử ở một document

Ví dụ tồn kho sản phẩm:

```javascript
const result = db.inventory.updateOne(
  {
    _id: sku,
    available: { $gte: quantity }
  },
  { $inc: { available: -quantity } }
);

if (result.modifiedCount !== 1) {
  // Không đủ hàng, sản phẩm không có hoặc điều kiện đã thay đổi.
}
```

Filter cùng update giúp bảo vệ invariant `available >= 0` tại document đó. Nếu nghiệp vụ còn tạo đơn hàng, ghi các trạng thái khác, cần transaction nhiều document hoặc quy trình nghiệp vụ phù hợp. **Không đánh đổi tính đúng đắn của tồn kho** để phân tán ghi khi không có cơ chế giữ invariant tương đương.

## 9. Giảm ghi tập trung: phân tán dữ liệu có chủ đích

### 9.1. Không cập nhật document cha khi không cần thiết

Khi comment được lưu riêng, thêm comment không bắt buộc phải sửa `posts` ngay lập tức:

```javascript
db.comments.insertOne({
  _id: new ObjectId(),
  postId,
  authorId,
  text,
  createdAt: new Date()
});
```

Có thể đếm theo nhu cầu:

```javascript
db.comments.countDocuments({ postId });
```

`countDocuments` có chi phí phụ thuộc index và số bản ghi, nên không thích hợp để gọi với tần suất rất cao ở mọi request lớn. Nhưng một cache/materialized count cập nhật theo batch có thể tránh ghi dồn vào parent. Cần phân biệt **số liệu chuẩn** và **số gần đúng hiển thị**.

### 9.2. Counter partition: chia bộ đếm ra nhiều document

Thay vì một `post.likeCount`, có thể chia thành N document chứa một phần số đếm:

```javascript
{
  _id: "post-123/07",
  postId: "post-123",
  partition: 7,
  count: NumberLong("1200")
}
```

Tạo unique index và phân tán cập nhật:

```javascript
db.counterPartitions.createIndex(
  { postId: 1, partition: 1 },
  { unique: true }
);

const partition = Math.floor(Math.random() * 32);

db.counterPartitions.updateOne(
  { postId: "post-123", partition },
  { $inc: { count: NumberLong("1") } },
  { upsert: true }
);
```

Tính tổng:

```javascript
db.counterPartitions.aggregate([
  { $match: { postId: "post-123" } },
  { $group: { _id: "$postId", total: { $sum: "$count" } } }
]);
```

Bài toán thực tế cần thêm:

- Khởi tạo partition hoặc xử lý duplicate-key/retry khi nhiều writer lần đầu upsert.
- Chọn N đủ phân tán, nhưng không quá lớn gây tốn chi phí đọc tổng.
- Đảm bảo request gửi lại không tăng hai lần nếu cần **idempotency**.
- Đọc tổng nhiều partition không mặc nhiên là snapshot nguyên tử dưới mọi ngữ cảnh.
- Nếu collection sharded, còn cần shard key phù hợp để những partition có thể nằm trên các shard khác nhau.

Đây là **phân chia counter theo nhiều document**, không đồng nghĩa MongoDB tự chuyển tất cả chúng tới những shard vật lý khác nhau.

### 9.3. Event log và materialized view

Có thể lưu mỗi lượt tương tác như một event document với ID ổn định:

```javascript
db.likeEvents.insertOne({
  _id: eventId,
  postId,
  userId,
  createdAt: new Date(),
  action: "LIKE"
});
```

Một consumer nền hoặc change stream có thể xây dựng số đếm từ các sự kiện. Event log có lợi cho audit, đối soát và tính lại chỉ số khi cần. Tuy nhiên, retry giữa bước ghi event và cập nhật projection cần cơ chế chống trùng; unique event ID tại nguồn **không tự bảo đảm** rằng mọi hiệu ứng tiếp theo chỉ được thực thi đúng một lần.

Nếu invariant là mỗi user chỉ thích một bài một lần, tách thành document quan hệ và unique index:

```javascript
db.postLikes.createIndex(
  { postId: 1, userId: 1 },
  { unique: true }
);

db.postLikes.insertOne({
  postId,
  userId,
  createdAt: new Date()
});
```

Index đảm bảo không tồn tại hai cặp `(postId, userId)` giống nhau trong collection theo quy tắc index. Trên sharded collection, unique index chịu giới hạn liên quan đến shard key, cần kiểm tra trước khi triển khai.

### 9.4. Queue và batch khi chấp nhận eventual consistency

Với số lượt xem, telemetry hoặc các chỉ số không cần đồng bộ tức thì, có thể nhận event riêng, nhóm theo cửa sổ thời gian, ghi tổng hợp theo batch và thiết lập quy trình retry/reconciliation. Đổi lại dữ liệu hiển thị có thể trễ. Phải công bố mức nhất quán được chấp nhận thay vì dùng mô hình này cho số dư hay tồn kho nếu chưa có bảo vệ tương ứng.

## 10. Sharding không tự chia một document lớn hoặc nóng

MongoDB sharding phân bố **document của collection** theo shard key, không chia một BSON document lớn thành nhiều phần để né giới hạn 16 MiB.

```text
Thiết kế dồn vào một document:
  posts[_id = viralPostId]
    ├─ comments rất lớn
    ├─ likeCount
    └─ mọi request sửa cùng document
       └─ một điểm ghi, một document trên một shard

Thiết kế phân tán dữ liệu:
  posts[_id = viralPostId]         (metadata)
  comments[commentId1]           (record riêng)
  comments[commentId2]
  counterPartitions[postId, 0]
  counterPartitions[postId, 1]
  ...
```

Tách thành nhiều document tạo cơ hội phân tải, nhưng shard key vẫn quyết định phân bố vật lý:

- Shard key chỉ theo `postId` có thể làm mọi comment thuộc một bài viral tập trung vào cùng vùng khóa.
- Hashed shard key theo `postId` thường phân bố **các bài khác nhau**, nhưng một `postId` duy nhất vẫn có một hash và không tự chia tải của bài đó.
- Thêm bucket/partition vào mô hình khóa có thể phân tán một entity lớn, nhưng tăng độ phức tạp truy vấn và uniqueness.
- Shard key phân bố kém, hoặc khóa tăng đơn điệu, có thể tạo **hot shard** ngay cả khi không có một hot document cụ thể.

**Hot document** là contention trên một document; **hot shard** là tải mất cân bằng giữa các shard. Có thể xảy ra cùng lúc nhưng không đồng nghĩa.

## 11. Bảng lựa chọn mẫu thiết kế

| Workload | Mẫu nên đánh giá | Điều kiện cần chú ý |
|---|---|---|
| Đơn hàng với ít dòng hàng | Embedded array | Số dòng có giới hạn, cùng vòng đời |
| Bài viết với hàng triệu comment | Reference: collection `comments` | Index, phân trang, xóa/ẩn liên quan |
| Giao diện chỉ cần 10 hoạt động mới nhất | Bounded array | `$slice`, source of truth và snapshot |
| Sensor gửi sự kiện liên tục | Event riêng, bucket hoặc time-series | Tốc độ ingest, retention, trần bucket |
| Một số ít bản ghi ngoại lệ rất lớn | Outlier pattern | Cách vượt ngưỡng và migration |
| Video viral có rất nhiều view/like | Counter partitions hoặc event log | Idempotency, delay, đọc tổng |
| Mỗi user thích một post tối đa một lần | Document liên kết + unique index | Uniqueness và shard key |
| Số lượng tồn kho phải luôn không âm | Conditional atomic update | Không mất invariant vì tối ưu tốc độ |
| Lưu tệp nhị phân > 16 MiB | GridFS hoặc object storage | Streaming, lifecycle, backup |
| Mảng tối đa 3 phần tử, cập nhật ít | Embedding | Đọc cùng nhau, byte tổng hợp hợp lý |

Kết luận lựa chọn phải dựa vào workload. Một mảng 200 string ngắn và ít ghi có thể không có vấn đề; một array 20 object lớn, nhận hàng nghìn cập nhật mỗi giây có thể là thiết kế tệ.

## 12. Chẩn đoán trên hệ thống thực

### 12.1. Nhận biết dữ liệu đang phình to

- Kích thước BSON ở nhóm document lớn nhất tăng đều theo thời gian.
- Trường array có số phần tử gắn với tuổi đời tài khoản/bài viết/thiết bị.
- Payload API tăng, dù màn hình chỉ cần vài mục.
- Index multikey trên array tăng dung lượng nhanh.
- Update bắt đầu gặp lỗi khi document tiến gần 16 MiB.

Dùng đo BSON và phân bố độ dài array, kết hợp thống kê collection. Dung lượng file trên hệ thống tệp còn chịu nén và vùng trống có thể tái sử dụng, nên không phản ánh trực tiếp kích thước document.

### 12.2. Nhận biết contention/hot document

- Nhiều lệnh update cùng `_id` chậm khi tải tăng.
- Profiler/monitoring cho thấy thao tác ghi tập trung theo một khóa.
- Write conflict/retry và độ trễ ghi tăng trong những đợt concurrency.
- Một shard chịu phần lớn lưu lượng ghi.
- Tăng tài nguyên không tăng throughput tương ứng vì vẫn có một điểm cập nhật chung.

Một thao tác chậm **không đủ** để kết luận hot document: có thể do thiếu index, disk latency, cache pressure, mạng hoặc transaction dài. Cần đo cùng các yếu tố này.

### 12.3. Phân tích query trước và sau khi tách data

```javascript
db.posts.find(
  { _id: postId },
  { title: 1, createdAt: 1 }
).explain("executionStats");

db.comments.find({ postId })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
  .explain("executionStats");
```

Đọc các trường như `winningPlan`, `totalKeysExamined`, `totalDocsExamined` và `nReturned` để hiểu truy vấn đọc. Để phân tích throughput ghi, cần thêm telemetry về update latency, contention, write conflicts, tần suất ghi vào cùng khóa và phân bố shard; `explain()` của truy vấn đọc không trả lời hết vấn đề ghi.

## 13. Quy trình migration từ unbounded array sang reference

Ví dụ ban đầu:

```javascript
{
  _id: postId,
  title: "MongoDB Patterns",
  comments: [
    { authorId: "u1", text: "Hay!", createdAt: ISODate("2026-01-01") },
    { authorId: "u2", text: "Rõ ràng", createdAt: ISODate("2026-01-02") }
  ]
}
```

Mục tiêu: `posts` chứa metadata, mỗi comment thành một document ở `comments`. Quy trình cần thận trọng với dữ liệu đang được ghi liên tục:

1. **Xác định schema đích:** `postId`, `commentId` ổn định, `createdAt`, `status`, index, quy tắc uniqueness và nguồn dữ liệu chuẩn.
2. **Chuyển luồng ghi mới:** comment mới được insert vào collection con. Nếu có giai đoạn cả hai luồng ghi cùng tồn tại, phải quản lý duplicate và đối soát.
3. **Backfill theo batch:** chuyển bình luận cũ thành document con, dùng định danh ổn định để chạy lại an toàn khi thất bại; không giả định index mảng là ID vĩnh viễn.
4. **Đối soát dữ liệu:** so số lượng, phát hiện duplicate, kiểm tra quyền, trường dữ liệu và phân trang.
5. **Chuyển nguồn đọc:** API dùng truy vấn `comments` có filter/sort/index thay vì tải mảng nhúng.
6. **Loại bỏ mảng cũ hoặc thu về snapshot có giới hạn:** thực hiện sau khi chắc chắn không còn writer dùng schema cũ.
7. **Đo sau migration:** kích thước document, latency đọc/ghi, index size, phân bố truy cập.

Việc loại mảng cũ khỏi document không bảo đảm file WiredTiger trên ổ đĩa thu nhỏ ngay; storage engine có thể giữ dung lượng trống để tái sử dụng. Đó là câu chuyện quản lý lưu trữ khác với mục tiêu sửa mô hình.

## 14. Những sai lầm phổ biến

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Nhúng mọi bản ghi con vào parent | Mảng tăng vô hạn và document lớn | Collection con có tham chiếu parent |
| Chỉ thêm `$slice` vào projection | Giảm payload nhưng DB vẫn phình to | Giới hạn ngay ở luồng ghi hoặc tách data |
| Dùng `$addToSet` cho hàng triệu user ID | Không trùng nhưng vẫn không giới hạn | Collection quan hệ + unique index |
| Cùng lưu comment, likedUserIds và likeCount trong post | Vừa document lớn vừa hot write | Tách quan hệ, counter và snapshot |
| Dùng `$set` sau khi đọc số hiện tại | Lost update | Dùng `$inc` hoặc conditional update |
| Thấy `$inc` nguyên tử rồi bỏ qua contention | Một document vẫn là điểm ghi nóng | Phân nhiều document khi nghiệp vụ cho phép |
| Phân tán counter mà không xử lý retry | Double count / tổng không đúng | Idempotency và reconciliation |
| Nghĩ sharding sẽ chia document 20 MiB | Vẫn vướng 16 MiB | Tách thành nhiều document |
| Dùng hashed shard key trên entity nhưng một entity cực nóng | Cùng giá trị hash có thể vẫn nóng | Phân vùng logic theo nhiều khóa |
| Dùng eventual count cho tồn kho mà không có cơ chế bảo vệ | Có thể bán vượt tồn kho | Conditional atomic update/transaction |

## 15. Bài tập thực hành

### Bài 1 — Bình luận bài viết

Một bài viết có thể có từ 0 đến 5 triệu comment, người dùng tải từng trang 20 comment mới nhất. Hãy thiết kế collection, index và keyset pagination. Giải thích vì sao một mảng `comments: []` duy nhất không phù hợp và vì sao `_id` làm tie-breaker cho các comment cùng `createdAt`.

### Bài 2 — Lịch sử đăng nhập

Document `users` đang lưu toàn bộ lịch sử đăng nhập trong `loginHistory`. Hãy viết câu lệnh `$push` chỉ giữ 10 lần gần nhất, sau đó bổ sung collection `loginEvents` nếu cần audit đầy đủ. Nêu rõ dữ liệu nào là nguồn chuẩn, dữ liệu nào là snapshot và cách sửa snapshot nếu không đồng bộ.

### Bài 3 — Like counter

Một bài viral nhận 100.000 lượt xem mỗi giây. Giải thích vì sao `$inc` bảo đảm cộng đúng tại một document nhưng vẫn có thể gặp contention. Đề xuất 32 counter partitions, mô tả cách đọc tổng, lỗi double count khi retry và chiến lược idempotency.

### Bài 4 — Telemetry và bucket

Một thiết bị gửi 1.000 sự kiện/giây; mỗi sự kiện vài trăm byte và cần lưu 12 tháng. Phân tích vì sao bucket một giờ có nguy cơ quá lớn hoặc quá nóng. So sánh collection event riêng, bucket nhỏ có trần và time-series collection; tính đến retention và truy vấn theo khung thời gian.

### Bài 5 — Tồn kho

Kho chỉ còn một sản phẩm, hai người đặt mua cùng lúc. Viết `updateOne` với điều kiện `available >= 1` và `$inc` giảm một. Giải thích vì sao không nên thay bằng bộ đếm eventual consistency nếu không có giải pháp bảo vệ invariant tương ứng.

## Kết luận

**Mảng tăng không giới hạn** là rủi ro về mô hình dữ liệu; **document quá lớn** gây chi phí đọc/ghi và chạm giới hạn BSON 16 MiB; **hot document** là rủi ro về phân bố ghi và cạnh tranh đồng thời. Ba vấn đề có thể đi cùng nhau, nhưng cần giải quyết đúng nguyên nhân.

Đưa dữ liệu một–nhiều không giới hạn sang **collection tham chiếu**, chỉ nhúng một **bounded array** cho snapshot, dùng **bucket/time-series** cho dữ liệu theo thời gian, hoặc phân tán **counter/event** khi ghi tập trung. Mỗi lựa chọn kéo theo quyết định về indexing, consistency, idempotency và khả năng đối soát. Thiết kế document hiệu quả là thiết kế giữ ranh giới BSON phù hợp với ranh giới nghiệp vụ và tải thực tế.


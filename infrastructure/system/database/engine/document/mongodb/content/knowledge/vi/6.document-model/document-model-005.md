# Phi chuẩn hóa, sao chép dữ liệu và duy trì tính nhất quán trong mô hình document MongoDB

## 1. Vì sao MongoDB thường lưu lặp lại một phần dữ liệu?

MongoDB lưu dữ liệu trong **document BSON**. Một document có thể chứa trường đơn giản, đối tượng lồng nhau và mảng; các document trong cùng collection không bắt buộc có cấu trúc giống hệt nhau. Vì vậy, khi thiết kế mô hình dữ liệu, ta có nhiều lựa chọn hơn việc tách mỗi thực thể thành một bảng riêng rồi kết hợp chúng khi đọc.

Ví dụ, màn hình danh sách đơn hàng thường cần cả mã đơn, tên khách hàng và tên sản phẩm. Nếu lưu theo kiểu tham chiếu hoàn toàn:

```javascript
// customers
{ _id: "C01", name: "Nguyễn An", loyaltyTier: "GOLD" }

// products
{ _id: "P01", name: "Bàn phím cơ", price: NumberDecimal("1200000") }

// orders
{
  _id: "O1001",
  customerId: "C01",
  items: [{ productId: "P01", quantity: 2 }],
  placedAt: ISODate("2026-10-01T09:00:00Z")
}
```

Muốn hiển thị tên khách và tên sản phẩm, ứng dụng phải thực hiện thêm truy vấn hoặc dùng aggregation `$lookup` để lấy dữ liệu ở collection khác. Một lựa chọn khác là **lưu bản sao có chủ đích** của vài trường ngay trong document đơn hàng:

```javascript
{
  _id: "O1001",
  customer: {
    id: "C01",
    nameAtPurchase: "Nguyễn An"
  },
  items: [{
    productId: "P01",
    productNameAtPurchase: "Bàn phím cơ",
    unitPriceAtPurchase: NumberDecimal("1200000"),
    quantity: 2
  }],
  placedAt: ISODate("2026-10-01T09:00:00Z")
}
```

Trong document thứ hai, tên khách và thông tin sản phẩm đã **được sao chép** từ nguồn khác tại thời điểm đặt hàng. Nhờ vậy, trang chi tiết đơn có thể đọc phần lớn thông tin bằng một truy vấn lên `orders`, không cần phụ thuộc vào trạng thái hiện tại của `products`.

Đó là một ví dụ của **phi chuẩn hóa (denormalization)**: chấp nhận lưu lặp hoặc tổ chức dữ liệu theo cách phục vụ mẫu truy cập thực tế, thay vì cố gắng tách mọi thông tin dùng chung thành những thực thể độc lập.

Phi chuẩn hóa không đồng nghĩa “bỏ qua chất lượng dữ liệu”. Nó chuyển một phần công việc từ **lúc đọc** sang **lúc ghi và duy trì dữ liệu**.

## 2. Phân biệt ba khái niệm dễ bị gọi chung là “sao chép”

| Khái niệm | Điều gì được nhân bản/lưu lặp? | Mục tiêu | Ai xử lý tính nhất quán? |
|---|---|---|---|
| **Phi chuẩn hóa dữ liệu** | Cùng một thuộc tính nghiệp vụ xuất hiện ở nhiều document hoặc nhiều vị trí | Đọc nhanh, biểu diễn đúng snapshot, giảm bước kết hợp | Thiết kế ứng dụng, transaction, xử lý bất đồng bộ, quy trình đối soát |
| **Nhúng dữ liệu (embedding)** | Thực thể con hoặc một phần thông tin liên quan nằm trong document cha | Đọc/cập nhật dữ liệu thường dùng chung | Ranh giới nguyên tử một document và logic nghiệp vụ |
| **Replication của MongoDB** | Các thành viên replica set lưu bản sao dữ liệu và áp dụng oplog | Tính sẵn sàng, dự phòng, khả năng đọc từ secondary | Cơ chế nhân bản của MongoDB và các mức read/write concern |

**Điểm cốt lõi:** Việc một tên sản phẩm xuất hiện trong `products` và hàng nghìn document `orders` là **lặp dữ liệu nghiệp vụ**. Nó khác với việc document `orders` được MongoDB sao lưu trên nhiều thành viên replica set. `writeConcern: "majority"` giúp yêu cầu xác nhận nhân bản giữa các thành viên; nó **không tự đồng bộ** tên sản phẩm được lưu lặp ở những collection khác nhau.

## 3. Ba cách tổ chức quan hệ dữ liệu

Giả sử một hệ thống bài viết có tác giả. Màn hình danh sách cần tiêu đề bài, tên hiển thị và ảnh đại diện tác giả.

### 3.1. Chỉ dùng tham chiếu

```javascript
// authors
{
  _id: "A01",
  displayName: "Mai",
  avatarUrl: "/avatars/mai.png",
  biography: "Tác giả chuyên về cơ sở dữ liệu"
}

// posts
{
  _id: "POST01",
  authorId: "A01",
  title: "MongoDB document model",
  publishedAt: ISODate("2026-10-01T09:00:00Z")
}
```

Ưu điểm là tên, ảnh và tiểu sử của tác giả có **một nơi được xem là nguồn chuẩn (source of truth)**. Khi đổi ảnh đại diện, chỉ cần cập nhật `authors`. Nhược điểm là nếu màn hình cần thông tin tác giả, việc đọc có thể phải thực hiện thêm truy vấn hoặc `$lookup`:

```javascript
db.posts.aggregate([
  { $match: { _id: "POST01" } },
  {
    $lookup: {
      from: "authors",
      localField: "authorId",
      foreignField: "_id",
      as: "author"
    }
  },
  { $unwind: "$author" },
  {
    $project: {
      title: 1,
      "author.displayName": 1,
      "author.avatarUrl": 1
    }
  }
]);
```

MongoDB hỗ trợ `$lookup`, nhưng không có nghĩa mọi lần kết hợp dữ liệu đều rẻ. Hiệu năng phụ thuộc lượng dữ liệu, kiểu pipeline, index ở collection liên quan và số document phải xử lý.

### 3.2. Nhúng toàn bộ thông tin liên quan

```javascript
{
  _id: "POST01",
  title: "MongoDB document model",
  author: {
    id: "A01",
    displayName: "Mai",
    avatarUrl: "/avatars/mai.png",
    biography: "Tác giả chuyên về cơ sở dữ liệu"
  }
}
```

Một lần đọc bài viết có thể lấy đủ thông tin tác giả. Tuy nhiên, nếu tác giả có 100.000 bài, mỗi bài chứa nguyên tiểu sử và metadata tác giả, tổng dung lượng tăng đáng kể. Khi tác giả đổi tiểu sử, ứng dụng phải quyết định có cập nhật 100.000 document hay không.

Nhúng toàn bộ thường phù hợp hơn với dữ liệu **thuộc sở hữu của một document cha** và thường được đọc/cập nhật cùng cha, chẳng hạn các dòng hàng nhỏ của một đơn hàng. Nó kém phù hợp với một đối tượng chung có vòng đời độc lập và được tham chiếu bởi số lượng document lớn, chẳng hạn hồ sơ tác giả đầy đủ.

### 3.3. Chỉ sao chép các trường cần để đọc

```javascript
{
  _id: "POST01",
  authorId: "A01",
  authorPreview: {
    displayName: "Mai",
    avatarUrl: "/avatars/mai.png"
  },
  title: "MongoDB document model",
  publishedAt: ISODate("2026-10-01T09:00:00Z")
}
```

`authorId` vẫn liên kết đến tác giả gốc. `authorPreview` là bản sao nhỏ, giúp render danh sách bài nhanh hơn. Khi mở trang tác giả chi tiết, ứng dụng vẫn lấy `authors`. Cách này thường gọi là **mẫu tham chiếu mở rộng (extended reference pattern)**: giữ khóa tham chiếu và sao chép một số trường hay dùng.

Phần khó không nằm ở câu lệnh `find`, mà là **hợp đồng cập nhật**: tên hiển thị đổi thì `authorPreview.displayName` ở bài viết có phải đổi theo không? Nếu phải, hệ thống chấp nhận trễ bao lâu?

### 3.4. So sánh theo mẫu truy cập

| Cách lưu | Số lần truy cập dữ liệu phụ thuộc | Chi phí ghi khi dữ liệu chung đổi | Khi nên cân nhắc |
|---|---|---|---|
| Chỉ tham chiếu | Có thể cần `$lookup`/nhiều lệnh đọc | Thường chỉ ghi nguồn chuẩn | Đối tượng chung, cập nhật thường xuyên, số bản sử dụng lớn |
| Nhúng đầy đủ | Thường đọc trong một document | Có thể phải cập nhật nhiều bản sao | Dữ liệu con có quan hệ sở hữu chặt, kích thước có giới hạn |
| Tham chiếu + bản sao nhỏ | Đọc màn hình phổ biến nhanh, vẫn có thể truy cập nguồn | Phải đồng bộ các trường được sao chép nếu chúng cần luôn mới | Danh sách, thẻ hiển thị, dữ liệu đọc thường xuyên |

Một collection MongoDB không bắt buộc chỉ theo một cách. Có thể nhúng địa chỉ giao hàng dưới dạng snapshot trong `orders`, tham chiếu đến `customers`, đồng thời giữ bản sao `authorPreview` ở `posts`.

## 4. Trước khi sao chép: phân biệt snapshot lịch sử và bản sao cần cập nhật

Không phải mọi dữ liệu bị “lệch” đều là lỗi. Ta cần quyết định **ý nghĩa của bản sao** trước khi viết cơ chế đồng bộ.

### 4.1. Snapshot lịch sử: cố ý không đồng bộ

Khách đặt hàng khi sản phẩm có giá 1.200.000 đồng. Một tháng sau cửa hàng đổi giá thành 1.350.000 đồng. Đơn hàng cũ **không được tự đổi giá**:

```javascript
// products: giá bán hiện tại
{
  _id: "P01",
  name: "Bàn phím cơ",
  currentPrice: NumberDecimal("1350000")
}

// orders: thông tin tại thời điểm chốt giao dịch
{
  _id: "O1001",
  items: [{
    productId: "P01",
    productNameAtPurchase: "Bàn phím cơ",
    unitPriceAtPurchase: NumberDecimal("1200000"),
    quantity: 2
  }]
}
```

`currentPrice` và `unitPriceAtPurchase` là **hai khái niệm nghiệp vụ khác nhau**, mặc dù bản thứ hai được tạo ra bằng cách sao chép giá từ bản thứ nhất tại một thời điểm. Điều này còn áp dụng cho tên sản phẩm trên hóa đơn, thuế suất, địa chỉ giao hàng lúc đặt hoặc điều khoản đã được chấp nhận.

Nếu “đồng bộ tất cả bản sao” một cách máy móc, hệ thống có thể phá vỡ lịch sử giao dịch.

### 4.2. Bản sao hiển thị hiện tại: có thể cần đồng bộ

Trong mạng xã hội, giao diện bài viết có thể yêu cầu luôn hiển thị tên và ảnh hiện tại của tác giả. Khi tác giả đổi tên, các `posts.authorPreview.displayName` trở nên **cũ (stale)**. Ứng dụng phải xác định một trong các mức kỳ vọng:

- **Nhất quán ngay sau mỗi thao tác (strong/atomic requirement theo phạm vi nghiệp vụ):** không cho phép người dùng thấy hai bản trái nhau ở các lệnh đọc liên quan.
- **Nhất quán cuối cùng (eventual consistency):** chấp nhận bản sao cũ trong một thời gian, sau đó cập nhật về cùng giá trị.
- **Không đồng bộ:** bản sao cố ý ghi lại thông tin tại thời điểm tạo bài.

Đừng đặt tên trường chung chung `author.name` mà bỏ qua quyết định này. Các tên như `authorNameAtPublish`, `currentAuthorName` hay `authorPreviewVersion` có thể làm rõ hợp đồng.

### 4.3. Ma trận quyết định ban đầu

| Dữ liệu được sao chép | Có cần giữ giá trị lịch sử? | Có cần bám theo nguồn hiện tại? | Chiến lược gợi ý |
|---|:---:|:---:|---|
| Giá trong đơn hàng | Có | Không | Lưu snapshot, không đồng bộ khi đổi bảng giá |
| Địa chỉ nhận hàng đã xác nhận | Có | Không | Snapshot trong đơn hàng |
| Tên hiển thị tác giả trong bài | Tùy sản phẩm | Thường có | Tham chiếu trực tiếp hoặc bản sao với cơ chế cập nhật |
| Số lượt thích hiển thị | Không | Có, có thể trễ | Counter nguồn rõ ràng, cập nhật nguyên tử hoặc tính tổng hợp |
| Báo cáo doanh thu theo ngày | Báo cáo phải ổn định theo kỳ đã chốt | Có cho kỳ chưa chốt | Dữ liệu tổng hợp, watermark và quy trình tính lại |
| Vai trò/quyền truy cập của người dùng | Không | Thường yêu cầu mới nhất | Tránh phụ thuộc bản sao trễ khi ra quyết định cấp quyền |

Với những dữ liệu tác động quyền truy cập, thanh toán, giới hạn tín dụng hoặc tồn kho, mức nhất quán cần được xác định từ **bất biến nghiệp vụ** (business invariant), không chỉ từ mong muốn giảm truy vấn.

## 5. Cái giá của phi chuẩn hóa

### 5.1. Đọc nhanh hơn, ghi có thể đắt hơn

Giả sử một tác giả có 50.000 bài. Sao chép `displayName` vào mọi bài giúp trang danh sách không phải thực hiện kết hợp với `authors` khi đọc, nhưng đổi tên tác giả có thể dẫn đến 50.000 lần cập nhật document. Đó là **write amplification**: một thay đổi nghiệp vụ sinh nhiều thao tác ghi.

Các chi phí khác cần cân nhắc:

- **Dung lượng:** giá trị trùng lặp chiếm thêm chỗ trên đĩa và trong cache.
- **Index:** nếu index các trường sao chép, mỗi lần thay đổi có thể phải cập nhật thêm khóa index.
- **Vận hành:** cần cơ chế xử lý lỗi cập nhật dở, retry, ghi nhận tiến độ và đối soát.
- **Tải đồng thời:** cùng một nhóm document có thể liên tục bị nhiều quy trình sửa.
- **Độ trễ đọc:** khi bản sao bất đồng bộ, giao diện có thể hiển thị thông tin cũ.
- **Quản trị dữ liệu:** sửa hoặc xóa thông tin nhạy cảm phải xét tất cả vị trí lưu lặp.

Không nên đặt giả định “MongoDB ưu tiên phi chuẩn hóa mọi thứ”. MongoDB hỗ trợ cả mô hình nhúng và mô hình tham chiếu; thiết kế hợp lý phụ thuộc vào mẫu đọc/ghi.

### 5.2. Kích thước document và mảng tăng không giới hạn

MongoDB có giới hạn kích thước **16 MiB cho một BSON document**. Nếu nhúng toàn bộ bình luận của một bài viết vào một document:

```javascript
{
  _id: "POST01",
  title: "Một bài viết rất phổ biến",
  comments: [ /* hàng triệu bình luận */ ]
}
```

mảng `comments` sẽ tăng không giới hạn, khiến document lớn, ghi và truyền dữ liệu nặng, cuối cùng không thể tiếp tục mở rộng. Một lựa chọn tốt hơn là tách `comments` sang collection riêng với `postId` và index phù hợp; chỉ giữ một số bình luận mới nhất nếu màn hình cần:

```javascript
// posts
{
  _id: "POST01",
  title: "Một bài viết rất phổ biến",
  recentComments: [
    { id: "CM09", content: "Rất hữu ích!" }
  ],
  commentCount: 54201
}

// comments
{
  _id: "CM09",
  postId: "POST01",
  content: "Rất hữu ích!",
  createdAt: ISODate("2026-10-20T08:30:00Z")
}
```

Ví dụ này dùng **subset pattern**: giữ một tập con nhỏ để hiển thị nhanh, giữ toàn bộ dữ liệu trong collection riêng. Lúc này `recentComments` và `commentCount` là các giá trị cần có chiến lược đồng bộ hoặc tính lại.

### 5.3. Vấn đề document “nóng”

Nếu hàng nghìn người cùng tăng `likesCount` của một bài viết rất nổi tiếng, một document chứa counter đó có thể trở thành điểm tranh chấp ghi. `$inc` giúp cập nhật nguyên tử đúng giá trị, nhưng không tự loại bỏ giới hạn thông lượng của một điểm ghi tập trung. Khi thực sự cần tải lớn, hệ thống có thể tính toán theo nhóm, gom sự kiện hoặc dùng kỹ thuật counter phân tán; lựa chọn đó phức tạp hơn, vì vậy nên đo trước khi áp dụng.

## 6. Mức nguyên tử: một document khác với nhiều document

### 6.1. Cập nhật một document được bảo vệ bởi tính nguyên tử

MongoDB bảo đảm một thao tác ghi trên **một document** là nguyên tử, kể cả khi thay đổi nhiều trường hoặc nhiều phần tử lồng nhau trong document đó.

```javascript
// Đặt trước tài liệu thử nghiệm.
db.carts.insertOne({
  _id: "CART01",
  totalQuantity: 2,
  items: [{ productId: "P01", quantity: 2 }]
});

// Thêm một đơn vị cùng sản phẩm và tăng tổng số lượng.
db.carts.updateOne(
  { _id: "CART01", "items.productId": "P01" },
  {
    $inc: {
      totalQuantity: 1,
      "items.$.quantity": 1
    }
  }
);
```

Hai thay đổi `totalQuantity` và `items.$.quantity` nằm **trong cùng document** nên hoặc cùng xuất hiện sau thao tác thành công, hoặc không bị quan sát như một trạng thái ghi một nửa document. Toán tử `$` ở đây trỏ đến **phần tử mảng đầu tiên khớp điều kiện**; mô hình cần bảo đảm cấu trúc mảng và điều kiện phù hợp.

Đây là lý do dữ liệu con có quan hệ chặt, thường cập nhật cùng nhau và kích thước có giới hạn là ứng viên tốt cho embedding.

### 6.2. Một `updateMany()` không phải transaction toàn tập

Giả sử bản sao tên tác giả nằm trong nhiều bài:

```javascript
db.posts.updateMany(
  { authorId: "A01" },
  { $set: { "authorPreview.displayName": "Mai Nguyễn" } }
);
```

Mỗi document bài viết được cập nhật nguyên tử, nhưng **toàn bộ lệnh không nguyên tử như một nhóm document**. Nếu lỗi xảy ra trong lúc cập nhật, một số bài có thể đã mang tên mới, số khác vẫn mang tên cũ. Một tiến trình đọc đồng thời có thể thấy các trạng thái hỗn hợp.

Chỉ chạy lại cùng `$set` có thể là thao tác lặp an toàn trong trường hợp đơn giản, nhưng khi tồn tại nhiều lần đổi tên và nhiều tác vụ bất đồng bộ, việc chạy lại một sự kiện cũ có thể **ghi đè dữ liệu mới hơn**. Cần một cơ chế thứ tự phiên bản.

### 6.3. Transaction khi cần một nhóm ghi cùng thành công

MongoDB hỗ trợ **multi-document transactions** trên replica set và sharded cluster đáp ứng điều kiện triển khai. Nếu một thay đổi phải ghi nguyên tử vào một số document có liên quan, transaction là công cụ phù hợp.

Ví dụ Node.js MongoDB driver, nơi `users` là nguồn chuẩn và `userCards` là bản sao dùng để hiển thị:

```javascript
// Ví dụ rút gọn: client là MongoClient đã kết nối.
const database = client.db("social");

await client.withSession(async (session) => {
  await session.withTransaction(async () => {
    await database.collection("users").updateOne(
      { _id: "U01" },
      { $set: { displayName: "Mai Nguyễn" } },
      { session }
    );

    await database.collection("userCards").updateOne(
      { _id: "U01" },
      { $set: { displayName: "Mai Nguyễn" } },
      { session }
    );
  }, {
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });
});
```

Một transaction có thể cam kết cả hai cập nhật hoặc hủy cả hai theo ngữ nghĩa transaction. Điều đó hữu ích khi số document trong phạm vi nhỏ và bất biến nghiệp vụ bắt buộc chúng phải được thay đổi như một đơn vị.

Nhưng transaction **không phải cách miễn phí để cập nhật hàng triệu bản sao**:

- Transaction kéo dài gây thêm chi phí tài nguyên và rủi ro xung đột.
- Có thể gặp lỗi có thể thử lại hoặc kết quả commit chưa rõ do mạng/failover.
- Các lệnh đọc không tự động có cùng mức nhất quán giữa nhiều lệnh chỉ vì ghi dùng transaction; mức read concern và session cũng quan trọng.
- Nếu một thay đổi có fan-out lớn, nên cân nhắc mô hình khác thay vì gom mọi document vào một transaction khổng lồ.

**Sự phân biệt trọng tâm:** tính nguyên tử ở một document là mặc định của thao tác ghi đơn lẻ; giao dịch nhiều document cần ranh giới transaction tường minh.

## 7. Nguồn chuẩn và hợp đồng đồng bộ

Để đồng bộ dữ liệu sao chép có thể dự đoán được, hãy xác định trước:

1. **Nguồn chuẩn:** trường nào được sửa trực tiếp, collection nào là nơi ra quyết định cuối cùng?
2. **Bản sao:** trường nào là giá trị dẫn xuất được phép cập nhật tự động?
3. **Hành vi đọc:** khi bản sao chưa được cập nhật, màn hình có thể hiển thị dữ liệu cũ hay phải đọc từ nguồn?
4. **Ranh giới nhất quán:** cần nguyên tử một document, nhiều document, hay chấp nhận cuối cùng?
5. **Cách sửa lỗi:** thông báo sự kiện, thử lại, đo độ trễ và đối soát định kỳ ra sao?

Ví dụ hợp đồng đối với `users.displayName` và `posts.authorPreview.displayName`:

```text
users.displayName
  = nguồn chuẩn, chỉ service quản lý hồ sơ được sửa
                  |
                  | UserNameChanged(userId, version, displayName)
                  v
posts.authorPreview.displayName
  = bản sao hiển thị, worker cập nhật; có thể trễ tối đa theo SLO của hệ thống
                  |
                  v
đối soát định kỳ: phát hiện bản sao chưa bắt kịp version
```

Quy định “chỉ service quản lý hồ sơ sửa nguồn chuẩn” giúp tránh tình trạng hai nơi sửa dữ liệu độc lập rồi tranh nhau ghi đè.

### 7.1. Bản sao không nên trở thành nguồn chuẩn thứ hai

Giả sử service A sửa `users.displayName` và service B sửa `posts.authorPreview.displayName` trực tiếp. Khi có chênh lệch, hệ thống không biết tên nào mới là đúng. Vì vậy:

- Thao tác người dùng thường sửa **nguồn chuẩn** trước.
- Bản sao được cập nhật từ trạng thái nguồn chuẩn hoặc sự kiện do nguồn phát.
- Nếu bản sao thay đổi độc lập vì một yêu cầu riêng, hãy coi đó là **trường nghiệp vụ khác** và đặt tên phù hợp, chẳng hạn `displayNameAtPublish`.

Đây là quyết định thiết kế có ý nghĩa lớn hơn việc chọn một toán tử MongoDB cụ thể.

## 8. Đồng bộ ngay và đồng bộ bất đồng bộ

### 8.1. Đồng bộ ngay trong đường ghi

Nếu chỉ có vài bản sao cần sửa và yêu cầu nhất quán mạnh, service có thể cập nhật chúng trong một transaction như phần 6.3. Điều kiện phù hợp là tập document nhỏ, đã biết, chi phí chấp nhận được và transaction thực sự bao phủ mọi dữ liệu phải nhất quán.

Ưu điểm: ranh giới commit rõ ràng. Nhược điểm: độ trễ và lỗi của toàn bộ thao tác tăng khi số bước lớn; hai collection không tự duy trì nhất quán ngoài phạm vi transaction.

### 8.2. Đồng bộ cuối cùng qua sự kiện

Với nhiều bài viết cùng sao chép thông tin tác giả, ứng dụng thường tránh cập nhật tất cả bài trong request đổi tên. Một luồng hợp lý:

```text
Người dùng đổi tên
        |
        v
Ghi users.displayName + tăng users.version
        |
        v
Phát sự kiện UserNameChanged(version=N)
        |
        v
Worker nhận sự kiện, tìm các bài của tác giả
        |
        v
Cập nhật authorPreview nếu version hiện tại < N
        |
        v
Đối soát / xử lý lại các phần chưa cập nhật
```

Trong khoảng giữa hai bước, một số bài vẫn hiện tên cũ. Đây là **eventual consistency có chủ đích**, không nhất thiết là lỗi, miễn sản phẩm xác định giới hạn trễ chấp nhận được và cơ chế phục hồi.

### 8.3. Dùng version tránh sự kiện cũ ghi đè mới

Giả sử tác giả đổi tên hai lần:

```text
version 41: "Mai"
version 42: "Mai Nguyễn"
```

Nếu worker xử lý bản 42 trước, sau đó vì retry lại xử lý bản 41, bản sao có thể bị **quay ngược** về tên cũ. Giải pháp là gắn phiên bản tăng đơn điệu ở nguồn:

```javascript
// Một document đã được khởi tạo với version.
{
  _id: "U01",
  displayName: "Mai",
  version: NumberLong(41)
}

// Cập nhật atomically tên và tăng version trên nguồn chuẩn.
db.users.updateOne(
  { _id: "U01" },
  {
    $set: { displayName: "Mai Nguyễn" },
    $inc: { version: NumberLong(1) }
  }
);
```

Worker có thể mang theo `sourceVersion` vào mỗi bản sao:

```javascript
// Mỗi post đã có authorPreview.version dạng số.
// Event mới nhất: userId=U01, version=42, displayName="Mai Nguyễn".
db.posts.updateMany(
  {
    authorId: "U01",
    "authorPreview.version": { $lt: NumberLong(42) }
  },
  {
    $set: {
      "authorPreview.displayName": "Mai Nguyễn",
      "authorPreview.version": NumberLong(42)
    }
  }
);
```

Hai trường trong **một post** được cập nhật nguyên tử. Một sự kiện có `version <= 42` không còn khớp post đã đạt version 42, vì thế không thể ghi tên cũ lên bản sao mới hơn thông qua câu update này.

Đây mới là **một phần** của thiết kế:

- Bản sao mới tạo phải có `version` khởi tạo rõ ràng; document chưa có trường `version` sẽ không khớp toán tử `$lt` như ví dụ.
- Event mới có thể phải cập nhật nhiều đợt; quy trình phải ghi nhận những document chưa đồng bộ và thử lại.
- Nếu worker chết giữa chừng, phát lại event là cần thiết; điều kiện version làm cập nhật lặp an toàn hơn.
- Nếu version được tăng trong nguồn, sự kiện cần dùng **đúng version đã ghi**, tránh tính version mới bằng một lần đọc độc lập dễ gặp tranh chấp.

### 8.4. Ghi sự kiện thế nào để không mất thông báo?

Một lỗi phổ biến:

```text
1. Cập nhật users thành công.
2. Process chết trước khi gửi sự kiện tới queue.
3. Bản sao không bao giờ nhận thông báo đổi tên.
```

**Transactional outbox** là một cách giải quyết: ghi thay đổi nguồn và một bản ghi sự kiện chờ xử lý trong **cùng ranh giới nguyên tử** (cùng document nếu mô hình cho phép, hoặc transaction khi cần nhiều document). Một tiến trình riêng gửi sự kiện, đánh dấu/ghi nhận đã phát và có thể thử lại sau lỗi.

Nếu outbox nằm trong collection khác, cần transaction phù hợp để tránh khoảng trống giữa ghi nguồn và ghi outbox. Nếu một service chỉ gửi message sau khi transaction đã commit, vẫn có cửa sổ mất thông báo khi process chết.

Các luồng gửi sự kiện có thể phát lặp. Thiết kế consumer nên chấp nhận **at-least-once delivery** và thực hiện cập nhật idempotent/so sánh version; không dựa vào giả định “message luôn đến đúng một lần”.

### 8.5. Change streams là lựa chọn theo dõi thay đổi

MongoDB cung cấp **change streams** trên những topology được hỗ trợ (chẳng hạn replica set/sharded cluster), giúp ứng dụng nhận biết các thay đổi đã xảy ra ở collection hoặc database:

```javascript
// Ví dụ quan sát trong mongosh trên topology hỗ trợ change streams.
const stream = db.users.watch([
  { $match: { operationType: "update" } }
]);

while (stream.hasNext()) {
  const change = stream.next();
  printjson(change);
}
```

Change streams hỗ trợ lấy **resume token** để tiếp tục sau khi ngắt kết nối trong điều kiện thích hợp. Chúng không tự viết các bản sao giúp ứng dụng, không tự áp dụng logic nghiệp vụ, và không thay thế việc xử lý sự kiện trùng, trạng thái chậm hoặc đối soát. Khi tài liệu nguồn thay đổi ở rất nhiều trường, consumer vẫn cần xác định chính xác trường sao chép nào phải đồng bộ.

Ngoài ra, cần quản lý vòng đời token, phạm vi theo dõi, quyền truy cập, lag và thời gian lưu oplog. Nếu để consumer ngừng quá lâu khiến không thể resume, ứng dụng cần quy trình **đồng bộ lại từ nguồn chuẩn**.

## 9. Đối soát: bước không thể thiếu khi chấp nhận eventual consistency

Một hàng đợi hoạt động tốt vẫn có thể xảy ra thiếu bản sao do lỗi lập trình, document mới tạo chưa đúng phiên bản, sự kiện hết hạn hoặc tiến trình cập nhật dở. Vì vậy, với dữ liệu cần đồng bộ, nên có **reconciliation**:

1. Kiểm kê các bản sao có `sourceVersion` thấp hơn version ở nguồn chuẩn.
2. Đọc lại giá trị hiện hành từ nguồn.
3. Cập nhật bản sao với điều kiện phiên bản để tránh ghi đè dữ liệu mới hơn.
4. Ghi nhận số bản còn lệch, độ trễ lớn nhất và lỗi xử lý.
5. Lặp lại cho đến khi đạt mức nhất quán đã cam kết.

Ví dụ kiểm tra chênh lệch giữa nguồn và một bản sao ở collection khác bằng aggregation:

```javascript
db.posts.aggregate([
  {
    $lookup: {
      from: "users",
      localField: "authorId",
      foreignField: "_id",
      as: "sourceUser"
    }
  },
  { $unwind: "$sourceUser" },
  {
    $match: {
      $expr: {
        $lt: [
          "$authorPreview.version",
          "$sourceUser.version"
        ]
      }
    }
  },
  {
    $project: {
      _id: 1,
      authorId: 1,
      previewVersion: "$authorPreview.version",
      sourceVersion: "$sourceUser.version"
    }
  }
]);
```

Pipeline trên minh họa **kiểm kê những bản sao có version nhỏ hơn nguồn**, với giả định schema đã khởi tạo các trường version. Trên hệ thống lớn, cần thiết kế batch, index, phân trang và giới hạn tài nguyên, không quét toàn bộ hai collection quá thường xuyên. Đồng thời xử lý riêng bản sao thiếu version, tài liệu nguồn đã bị xóa hoặc dữ liệu có kiểu không phù hợp.

Đối soát khác với “gửi lại mọi sự kiện từ đầu”: nó so sánh **trạng thái hiện hành** và sửa chênh lệch ngay cả khi lịch sử sự kiện không còn đầy đủ.

## 10. Nhất quán giữa bản sao nghiệp vụ và nhân bản replica set

Hai chiều nhất quán thường xuất hiện cùng lúc:

**Chiều A: giữa các document nghiệp vụ.** `users.displayName` và `posts.authorPreview.displayName` có đồng nhất không?

**Chiều B: giữa các nút MongoDB.** Secondary đã áp dụng thao tác mà primary vừa ghi chưa? Đọc có thấy dữ liệu đã majority commit chưa?

Ví dụ:

```text
users.displayName = "Mai Nguyễn"  [nguồn chuẩn]
        |
        | event chưa xử lý
        v
posts.authorPreview.displayName = "Mai"  [bản sao nghiệp vụ cũ]

Replica set của collection users:
    PRIMARY  ---> SECONDARY A ---> SECONDARY B
         (cơ chế sao chép dữ liệu nút)
```

Ngay cả khi bản ghi `users` đã được majority-acknowledged trên replica set, `posts.authorPreview` vẫn có thể cũ do consumer chưa cập nhật. Ngược lại, bản sao nghiệp vụ có thể mới nhưng một truy vấn đọc từ secondary đang lag lại thấy dữ liệu trước đó.

### 10.1. `writeConcern` giúp xác nhận điều gì?

```javascript
db.runCommand({
  update: "users",
  updates: [{
    q: { _id: "U01" },
    u: { $set: { displayName: "Mai Nguyễn" } }
  }],
  writeConcern: { w: "majority" }
});
```

`w: "majority"` yêu cầu xác nhận theo ngưỡng đa số thành viên dữ liệu của replica set. Nó giúp bảo vệ việc ghi trước rủi ro failover, nhưng **không đồng nghĩa mọi document có lưu bản sao của tên đã được sửa**.

### 10.2. `readConcern` và `readPreference` không phải cách thay thế đồng bộ nghiệp vụ

`readPreference` chọn nơi đọc như primary hay secondary. `readConcern` quy định mức đảm bảo dữ liệu được nhìn thấy (`local`, `majority`, và các chế độ khác tùy ngữ cảnh). Dù đọc với `readConcern: "majority"`, ta vẫn có thể thấy `posts.authorPreview` cũ nếu tiến trình đồng bộ nghiệp vụ chưa chạy.

Nếu logic nghiệp vụ yêu cầu “vừa đổi tên thì ngay sau đó tất cả trang bài viết phải hiển thị tên mới”, phương án có thể là:

- Đọc trực tiếp tên từ `users` trên các đường đọc nhạy về độ mới.
- Giới hạn phạm vi transaction nếu số bản sao nhỏ.
- Hoặc thay đổi yêu cầu sản phẩm để cho phép eventual consistency với độ trễ định lượng.

Không thể giải quyết ranh giới này chỉ bằng đổi read concern hay write concern.

## 11. Những lựa chọn thay thế sao chép và khi nào nên dùng

### 11.1. Dùng `$lookup` thay vì lưu một bản sao phải cập nhật liên tục

Nếu tên tác giả đổi thường xuyên, còn số bài rất lớn, truy vấn `$lookup` qua index khóa tác giả có thể đơn giản hơn một luồng cập nhật hàng loạt. Chấp nhận chi phí đọc để giảm rủi ro stale và chi phí write fan-out.

```javascript
db.posts.aggregate([
  { $match: { published: true } },
  { $sort: { publishedAt: -1 } },
  { $limit: 20 },
  {
    $lookup: {
      from: "users",
      localField: "authorId",
      foreignField: "_id",
      as: "author"
    }
  },
  { $unwind: "$author" }
]);
```

Ở ví dụ, lọc/sort/limit giảm số bài cần bổ sung thông tin tác giả, và `$lookup` có thể tận dụng index `_id` ở `users`. Tuy nhiên, pipeline cần được kiểm chứng với mẫu truy cập, dữ liệu và index thực tế; đặt `$limit` trước khi kết hợp chỉ đúng nếu logic màn hình thực sự muốn lấy 20 bài trước rồi mới bổ sung tác giả.

### 11.2. Lưu số liệu tổng hợp đã tính

Dashboard có thể cần tổng doanh thu mỗi ngày. Tính toàn bộ từ collection đơn hàng ở mỗi lượt xem có thể đắt, nên hệ thống lưu document thống kê:

```javascript
{
  _id: "2026-10-20",
  paidOrderCount: 1520,
  revenue: NumberDecimal("248000000"),
  calculatedAt: ISODate("2026-10-20T23:59:00Z")
}
```

Đây là **computed pattern / materialized result**: kết quả dẫn xuất từ đơn hàng, lưu riêng để đọc nhanh. Việc duy trì cần đặc biệt chú ý giao dịch hủy/hoàn tiền, đơn cập nhật muộn, tính lại khi có lỗi và thời điểm chốt số liệu. Với các phép cộng tăng dần, dùng `$inc` giúp cộng nguyên tử trong một document, nhưng không tự giải quyết vấn đề **cộng trùng sự kiện**. Cần theo dõi ID sự kiện, version hoặc có cơ chế tính lại.

### 11.3. Chỉ sao chép tập con nhỏ

Màn hình bài viết chỉ cần ba bình luận gần nhất. Có thể lưu `recentComments` gồm số lượng giới hạn cùng `commentCount`, còn bình luận đầy đủ nằm ở `comments`. Khi một bình luận bị sửa hoặc xóa, cần có chính sách cập nhật preview và count; không nên để mảng preview phát triển vô hạn.

Một ví dụ `$push` với `$slice` giới hạn số phần tử được lưu, dùng khi thứ tự đầu vào đã được thiết kế rõ:

```javascript
db.posts.updateOne(
  { _id: "POST01" },
  {
    $push: {
      recentComments: {
        $each: [{ id: "CM10", content: "Ví dụ dễ hiểu" }],
        $position: 0,
        $slice: 3
      }
    }
  }
);
```

Lệnh này chỉ quản lý **preview**, không tự chèn document bình luận vào collection `comments`. Nếu nghiệp vụ yêu cầu cả hai ghi như một đơn vị, cần transaction hoặc cơ chế khôi phục phù hợp.

## 12. Các mẫu lỗi và cách phòng ngừa

| Tình huống | Nguyên nhân thường gặp | Biện pháp thiết kế |
|---|---|---|
| Tên tác giả trong một số bài không đổi | `updateMany` cập nhật dở hoặc consumer lỗi | Retry idempotent, ghi nhận tiến độ, đối soát |
| Tên cũ ghi đè tên mới | Sự kiện xử lý không theo thứ tự | Version tăng đơn điệu, chỉ áp dụng bản mới hơn |
| Đổi tên thành công nhưng không phát sự kiện | Process chết sau khi ghi nguồn | Outbox trong cùng ranh giới nguyên tử |
| Sự kiện được xử lý hai lần | Message at-least-once hoặc retry | Chống trùng theo event ID/version; thiết kế phép ghi lặp an toàn |
| Tổng số lượt thích bị sai | Đồng thời cập nhật bằng read-modify-write thiếu điều kiện | Dùng `$inc`, ràng buộc nguồn dữ liệu, xử lý sự kiện trùng |
| Đơn cũ tự đổi giá theo bảng giá mới | Nhầm snapshot lịch sử với bản sao cần đồng bộ | Đặt trường `unitPriceAtPurchase` và không cập nhật theo `currentPrice` |
| Trang xem quyền truy cập bị cũ | Quyết định bảo mật dựa trên bản sao eventual | Kiểm tra ở nguồn chuẩn hoặc đường đọc có bảo đảm cần thiết |
| Document quá lớn | Nhúng mảng tăng không giới hạn | Tách collection, tham chiếu hoặc subset giới hạn |
| Đổi tên gây hàng chục nghìn cập nhật | Fan-out của một thuộc tính chung | Cân nhắc reference + `$lookup` thay cho bản sao |
| Secondary chưa thấy dữ liệu mới | Độ trễ nhân bản | Hiểu `readPreference`, `readConcern`, session và yêu cầu nhất quán |

## 13. Quy trình thiết kế phi chuẩn hóa từ yêu cầu thật

Không nên quyết định trước rằng “một màn hình phải ứng với một document”. Thay vào đó, có thể làm theo các bước:

**Bước 1: Liệt kê những thao tác đọc phổ biến.** Màn hình cần các trường nào, tần suất bao nhiêu, có phân trang/sắp xếp ra sao, có cần luôn mới không?

**Bước 2: Liệt kê thao tác ghi.** Trường nào thay đổi thường xuyên? Một thay đổi sẽ ảnh hưởng bao nhiêu document? Dữ liệu lịch sử có được phép thay đổi theo nguồn?

**Bước 3: Xác định ranh giới nguyên tử.** Những trường nào cần cập nhật cùng nhau? Nếu chỉ thuộc một document có kích thước giới hạn, có thể nhúng. Nếu liên quan rất nhiều document độc lập, nên suy xét cẩn thận việc sao chép.

**Bước 4: Quy định nguồn chuẩn.** Dữ liệu nào là gốc, dữ liệu nào là snapshot, dữ liệu nào là bản sao hiển thị, dữ liệu nào là kết quả tính toán? Đặt tên trường phản ánh đúng ý nghĩa.

**Bước 5: Chọn chiến lược duy trì.** Không cập nhật đối với snapshot; update atomically trong một document; transaction cho ít document có liên quan; hoặc event-driven + version + reconciliation khi chấp nhận trễ.

**Bước 6: Thiết kế đường phục hồi.** Nếu request timeout, transaction cần retry, consumer nhận event trùng, hoặc mất event, dữ liệu sẽ trở về trạng thái đúng bằng cách nào?

**Bước 7: Đo trên dữ liệu thực tế.** Theo dõi thời gian đọc, kế hoạch `explain`, dung lượng document/index, số bản sao phải cập nhật, độ trễ đồng bộ và số bản chưa đối soát.

### 13.1. Ví dụ quyết định cho một ứng dụng thương mại điện tử

| Thuộc tính | Nguồn chuẩn | Có sao chép? | Đồng bộ sau khi đơn được tạo? |
|---|---|---|---|
| Giá hiện tại | `products.currentPrice` | Có thể hiển thị trong các bộ nhớ đệm | Theo chính sách làm mới |
| Giá tại lúc mua | Giá được chốt trong bước đặt hàng | Lưu vào `orders.items.unitPriceAtPurchase` | **Không**, đây là snapshot |
| Địa chỉ giao hàng | Địa chỉ khách chọn lúc xác nhận | Lưu vào `orders.shippingAddress` | Không tự đổi theo profile khách |
| Trạng thái kho hiện tại | Hệ thống tồn kho | Nên đọc/ghi tại nơi kiểm soát tồn | Không dựa vào snapshot trễ để quyết định xuất kho |
| Tên sản phẩm trên đơn | Thông tin lúc mua | `productNameAtPurchase` | Không nhất thiết, tùy quy định hóa đơn/lịch sử |
| Tổng tiền đơn hàng | Các dòng giá và chính sách lúc mua | Lưu cùng document đơn hàng | Phải nhất quán với giao dịch chốt, không tự tính theo giá mới |
| Thông tin khách hiện tại trên dashboard | `customers` | Có thể sao chép một số trường | Có, nếu giao diện yêu cầu mới; cần biết độ trễ |

Một mô hình tốt có thể dùng cả **reference** và **snapshot** trong cùng một đơn hàng:

```javascript
{
  _id: "O1001",
  customerId: "C01",
  customerNameAtPurchase: "Nguyễn An",
  items: [{
    productId: "P01",
    productNameAtPurchase: "Bàn phím cơ",
    unitPriceAtPurchase: NumberDecimal("1200000"),
    quantity: 2
  }],
  grandTotalAtPurchase: NumberDecimal("2400000"),
  placedAt: ISODate("2026-10-01T09:00:00Z")
}
```

`customerId` và `productId` giữ khả năng truy xuất thực thể hiện hành; các trường `AtPurchase` bảo toàn trạng thái giao dịch. **Giữ cả tham chiếu lẫn snapshot có chủ đích** thường rõ ràng hơn việc sao chép dữ liệu rồi không quy định cập nhật thế nào.

## 14. Bài tập tự thực hành

### Bài tập 1 — Chọn embed, reference hay sao chép một phần

Thiết kế MongoDB cho các đối tượng:

- Một `course` có nhiều `lessons` và mỗi bài có số lượng section vừa phải.
- Một `video` có hàng triệu `comments`.
- Một `user` có hàng trăm nghìn `posts`, mỗi thẻ bài cần ảnh đại diện và tên tác giả.

Với từng đối tượng, hãy chỉ ra khả năng tăng kích thước document, tần suất đọc, tần suất sửa dữ liệu chung và ranh giới cập nhật nguyên tử. Sau đó mới chọn cách biểu diễn.

### Bài tập 2 — Dự đoán trạng thái sau cập nhật

Giả sử:

```javascript
// authors
{ _id: "A01", displayName: "Mai" }

// posts
{ _id: "P01", authorId: "A01", authorPreview: { displayName: "Mai" } }
{ _id: "P02", authorId: "A01", authorPreview: { displayName: "Mai" } }
```

Ứng dụng chạy:

```javascript
db.authors.updateOne(
  { _id: "A01" },
  { $set: { displayName: "Mai Nguyễn" } }
);
```

Hãy giải thích vì sao `posts.P01` và `posts.P02` vẫn có thể hiển thị `"Mai"`. Nếu cần cập nhật cả ba document như một nhóm nguyên tử, cần ranh giới gì? Nếu có một triệu bài, phương án khác sẽ là gì?

### Bài tập 3 — Sự kiện trễ và version

Hai sự kiện:

```text
UserNameChanged(U01, version=101, name="Mai A")
UserNameChanged(U01, version=102, name="Mai B")
```

Consumer nhận `102` trước `101`. Hãy thiết kế điều kiện update chỉ áp dụng event nếu `incomingVersion > storedVersion`. Giải thích vì sao nếu chỉ dùng `$set: { displayName: ... }` thì có thể sai; trường hợp bản sao chưa có `version` sẽ được khởi tạo hoặc đối soát ra sao?

### Bài tập 4 — Phân biệt hai loại nhất quán

Một đơn hàng mới đã được xác nhận với `writeConcern: "majority"`. Tuy nhiên, dashboard thống kê đơn theo ngày vẫn hiển thị số cũ. Hãy xác định:

1. Bảo đảm nào mà majority write concern đã cung cấp?
2. Vì sao document thống kê đã phi chuẩn hóa vẫn có thể bị chậm?
3. Khi nào nên chấp nhận eventual consistency cho dashboard?
4. Nếu không thể chấp nhận chậm, cần thay đổi ranh giới thao tác hoặc đường đọc như thế nào?

### Bài tập 5 — Thiết kế quy trình phục hồi

Đề xuất cơ chế giúp một hệ thống đồng bộ tên tác giả đến bản sao của hàng nghìn bài viết có thể phục hồi khi:

1. Ghi nguồn thành công nhưng process chết trước khi gửi sự kiện.
2. Consumer xử lý được nửa số bài rồi mất kết nối.
3. Sự kiện phiên bản cũ đến sau sự kiện phiên bản mới.
4. Consumer ngừng đủ lâu để resume token của change stream không còn dùng được.
5. Một bài mới được tạo trong lúc tiến trình đồng bộ đang chạy.

Cần mô tả nguồn chuẩn, version, cơ chế phát lại, thao tác ghi lặp an toàn và đối soát. Không nhất thiết phải viết toàn bộ hệ thống hàng đợi để giải thích chính xác đường khôi phục.

## 15. Ghi nhớ các nguyên tắc thiết kế

**Phi chuẩn hóa là lựa chọn có điều kiện theo mẫu truy cập.** Nó có thể giảm số lần kết hợp dữ liệu và phục vụ đọc hiệu quả, nhưng làm tăng chi phí ghi và nguy cơ bản sao cũ.

**Bản sao lịch sử không giống bản sao hiện hành.** Giá trên đơn hàng là snapshot cần giữ nguyên; tên người dùng hiển thị hiện tại là dữ liệu có thể cần đồng bộ. Đặt tên trường và hợp đồng cập nhật phải phân biệt hai loại này.

**Tính nguyên tử có phạm vi.** Một thao tác cập nhật một document là nguyên tử; một `updateMany()` không tự tạo transaction cho toàn bộ tài liệu; transaction nhiều document cần được dùng có chủ đích.

**Đồng bộ bất đồng bộ cần đường phục hồi.** Nguồn chuẩn, version, retry lặp an toàn, outbox/change streams khi thích hợp và reconciliation mới giúp hệ thống quay về trạng thái đúng sau lỗi.

**Replication của MongoDB không giải quyết phi chuẩn hóa nghiệp vụ.** Replica set sao chép dữ liệu giữa các thành viên; ứng dụng vẫn phải quyết định cách duy trì những trường được sao chép ở nhiều document khác nhau. Khi hiểu rõ hai lớp này, ta có thể thiết kế MongoDB vừa đáp ứng tốc độ đọc, vừa giữ đúng bất biến của dữ liệu.

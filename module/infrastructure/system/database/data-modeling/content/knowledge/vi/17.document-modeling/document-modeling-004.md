# Dữ liệu lồng nhau, mảng và nguy cơ tăng kích thước không giới hạn

## 1. Vấn đề cốt lõi: cấu trúc thuận tiện hôm nay có thể trở thành điểm nghẽn ngày mai

Mô hình tài liệu (*document model*) cho phép một tài liệu chứa nhiều lớp đối tượng và mảng, thường được biểu diễn bằng JSON hoặc định dạng tương tự. Cách này gần với cấu trúc mà ứng dụng dùng để hiển thị dữ liệu: đơn hàng gồm địa chỉ và dòng hàng; bài viết gồm tác giả và thẻ; khóa học gồm thông tin tóm tắt các bài học.

Tuy nhiên, không phải dữ liệu nào “thuộc về” một thực thể cũng nên đặt trực tiếp vào tài liệu của thực thể ấy. Đặc biệt, **mảng có thể tăng liên tục**, các đối tượng lồng nhau có thể chứa dữ liệu rất lớn, còn thao tác ghi đồng thời lên những phần con có thể dồn vào cùng một tài liệu.

Bài này thuộc chương **Mô hình tài liệu** của phạm vi **DATABASE_DATA_MODELING**: rèn kỹ năng chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng, lựa chọn thực thể, quan hệ, ràng buộc, khóa, chỉ mục và lược đồ vật lý để dữ liệu dễ tiến hóa và kiểm chứng. Trọng tâm là hiểu đúng **dữ liệu lồng nhau**, **mảng**, **giới hạn kích thước** và các dấu hiệu cần tách dữ liệu.

Sau khi học, bạn có thể:

- Đọc và thiết kế cấu trúc đối tượng lồng nhau, mảng giá trị và mảng đối tượng có ngữ nghĩa rõ ràng.
- Phân biệt mảng có giới hạn (*bounded*) với mảng có nguy cơ tăng không giới hạn (*unbounded*).
- Ước lượng dung lượng tài liệu và chi phí đọc, ghi, lập chỉ mục trước khi dữ liệu tăng lớn.
- Phát hiện các lỗi truy vấn và cập nhật thường gặp với mảng lồng nhau.
- Chọn giữa nhúng, tham chiếu, chỉ giữ tập con gần đây, chia bucket hoặc lưu lịch sử riêng.
- Kiểm chứng lựa chọn thông qua đường truy cập, ràng buộc nghiệp vụ, thử tải và kế hoạch di trú.

## 2. Những cấu trúc lồng nhau thường gặp

### 2.1. Đối tượng lồng nhau

Đối tượng lồng nhau gom các thuộc tính cùng ngữ nghĩa:

```json
{
  "orderId": "ORD-041",
  "shippingAddress": {
    "recipientName": "Nguyen An",
    "city": "Da Nang",
    "district": "Hai Chau",
    "street": "12 Duong Mau"
  },
  "currency": "VND",
  "status": "DRAFT"
}
```

`shippingAddress` là một giá trị có cấu trúc thuộc đơn hàng. Địa chỉ tại thời điểm đặt đơn có thể cần được giữ nguyên vì thay đổi địa chỉ mặc định của khách không được thay đổi lịch sử giao hàng.

Đối tượng lồng nhau hữu ích khi các trường liên quan chặt chẽ, có cùng vòng đời hoặc thường được đọc/ghi cùng nhau. Tuy nhiên, lồng nhau quá nhiều cấp sẽ khiến đường dẫn phức tạp, làm truy vấn, validation và chuyển đổi schema khó hơn; giới hạn độ sâu và kiểu dữ liệu phụ thuộc hệ quản trị.

### 2.2. Mảng giá trị vô hướng

```json
{
  "productId": "PRD-017",
  "tags": ["database", "backend", "design"],
  "supportedLanguages": ["vi", "en"]
}
```

Mảng thích hợp khi thuộc tính có nhiều giá trị. Cần xác định **mảng có thứ tự hay không**, có được lặp giá trị không, và có giới hạn phần tử không.

Ví dụ, `supportedLanguages` có thể được xem như một tập hợp ngôn ngữ không lặp; `imageOrder` lại có ý nghĩa thứ tự. Nếu yêu cầu là “mỗi giá trị chỉ xuất hiện một lần”, ứng dụng cần quy tắc kiểm tra hoặc thao tác ghi hỗ trợ; mảng JSON tự nó không áp đặt tính duy nhất.

### 2.3. Mảng đối tượng

```json
{
  "orderId": "ORD-041",
  "items": [
    {
      "lineId": "L-01",
      "productId": "PRD-017",
      "quantity": 2,
      "unitPriceMinor": 125000
    },
    {
      "lineId": "L-02",
      "productId": "PRD-088",
      "quantity": 1,
      "unitPriceMinor": 40000
    }
  ],
  "itemsTotalMinor": 290000
}
```

Mỗi phần tử của `items` có nhiều trường thuộc cùng một dòng hàng. Mã `lineId` giúp nhận diện ổn định dòng khi sắp xếp hoặc cập nhật. Nếu cần tham chiếu sản phẩm hiện hành, `productId` vẫn có thể là một khóa tham chiếu, dù `items` được nhúng vào đơn.

**Quan trọng:** khi kiểm tra điều kiện trên một phần tử, phải đảm bảo những điều kiện ấy áp dụng cho **cùng phần tử**; nếu không, truy vấn có thể khớp sai. Phần 6 sẽ minh họa.

### 2.4. Mảng lồng trong đối tượng, đối tượng lồng trong mảng

Mô hình có thể gồm nhiều cấp:

```json
{
  "courseId": "CRS-011",
  "modules": [
    {
      "moduleId": "M-01",
      "title": "Nền tảng dữ liệu",
      "lessons": [
        { "lessonId": "L-01", "title": "Thực thể" },
        { "lessonId": "L-02", "title": "Quan hệ" }
      ]
    }
  ]
}
```

Cấu trúc này thuận tiện nếu danh sách module và bài học ngắn, ổn định và thường hiển thị cùng nhau. Nhưng nếu nội dung mỗi bài dài, có lịch sử phiên bản, quyền chỉnh sửa riêng hoặc khóa học có hàng nghìn bài, đặt toàn bộ nội dung ở nhiều lớp lồng nhau có thể không phù hợp.

Hãy xem các lớp lồng như **một quyết định ranh giới dữ liệu**, không chỉ là cách trình bày JSON.

## 3. Khi nào nhúng là hợp lý, khi nào mảng trở thành rủi ro?

Một phần con là ứng viên tốt để nhúng khi phần lớn điều kiện sau đúng:

1. Nó là thành phần phụ thuộc vào tài liệu cha, không có vòng đời độc lập quan trọng.
2. Nó thường được đọc cùng tài liệu cha.
3. Nó thường được thay đổi cùng tài liệu cha hoặc cần cập nhật nguyên tử cùng cha.
4. Số phần tử và kích thước phần con có **giới hạn nghiệp vụ đáng tin cậy**.
5. Mức ghi đồng thời lên phần con không làm tài liệu cha trở thành điểm nóng.
6. Phân trang, lọc, xóa hoặc phân quyền riêng từng phần tử không phải nhu cầu chủ yếu.

Ví dụ đơn hàng có tối đa 60 dòng, mỗi dòng là metadata nhỏ, và giao diện chi tiết luôn hiển thị các dòng: `items` thường phù hợp để nhúng.

Ngược lại, nếu một bài viết có thể nhận hàng trăm nghìn bình luận, mỗi bình luận được thêm và kiểm duyệt độc lập, cấu trúc này đáng ngờ:

```json
{
  "postId": "POST-101",
  "title": "Mô hình dữ liệu",
  "comments": [
    { "commentId": "C-001", "text": "Bình luận đầu tiên" }
  ]
}
```

Một bài đăng mới có thể chỉ có một bình luận, nhưng sau nhiều năm mảng `comments` có thể tăng đến mức gây tốn kém hoặc vượt giới hạn tài liệu. Việc phải phân trang, sắp xếp và kiểm duyệt bình luận càng cho thấy chúng có đường truy cập riêng.

### 3.1. Phân biệt “một-nhiều” với “mảng có thể nhúng”

| Quan hệ nghiệp vụ | Bội số thường gặp | Khuyến nghị ban đầu | Yếu tố quyết định |
| --- | --- | --- | --- |
| Đơn hàng → địa chỉ giao hàng đã chốt | Một | Nhúng đối tượng | Vòng đời gắn với đơn |
| Đơn hàng → dòng hàng | Nhiều, thường giới hạn | Nhúng mảng | Đọc/ghi cùng đơn, có trần số dòng |
| Bài viết → bình luận | Tăng theo thời gian | Tham chiếu tài liệu riêng | Không giới hạn, phân trang, ghi riêng |
| Khóa học → nội dung bài học | Có thể lớn | Tham chiếu hoặc lai | Kích thước nội dung và xuất bản riêng |
| Người dùng → thông báo | Tăng liên tục | Lưu riêng, nhúng tối đa vài mục gần đây | Tải ghi, thời hạn lưu, phân trang |
| Thiết bị → sự kiện đo | Tăng liên tục, tốc độ cao | Tài liệu riêng hoặc bucket có giới hạn | Dung lượng, tần suất ghi, truy vấn theo thời gian |
| Sản phẩm → 8 ảnh | Ít nhưng dữ liệu nhị phân lớn | Nhúng metadata, lưu tệp riêng | Kích thước byte, vòng đời tệp |

**Bội số một-nhiều không đủ để kết luận.** Luôn cần xem kích thước mỗi phần tử, tốc độ tăng trưởng, tần suất thay đổi, quy tắc nghiệp vụ và cách truy vấn.

## 4. Vì sao mảng tăng không giới hạn gây vấn đề?

### 4.1. Vượt giới hạn kích thước của tài liệu

Một số hệ quản trị tài liệu có giới hạn cụ thể cho kích thước tối đa của một tài liệu và độ sâu lồng nhau. Giới hạn này phụ thuộc vào sản phẩm và phiên bản; cần tra tài liệu chính thức của hệ đang triển khai. Ngay cả khi tài liệu chưa chạm mức tối đa, ứng dụng vẫn có thể gặp độ trễ, tiêu thụ bộ nhớ hoặc chi phí truyền dữ liệu quá cao.

Một ước lượng đơn giản:

```text
B_document ≈ B_fixed + N × B_element + B_overhead

B_fixed     : byte dành cho các trường của tài liệu cha
N           : số phần tử trong mảng
B_element   : số byte trung bình mỗi phần tử
B_overhead  : metadata, tên trường, cách mã hóa, phần dự phòng
```

Công thức giúp đánh giá xu hướng, **không thay thế phép đo trên tài liệu thực**. JSON, BSON, nén trên đĩa, tên khóa, chuỗi UTF-8 và định dạng chỉ mục có chi phí khác nhau.

Ví dụ một thiết bị sinh 2.400 sự kiện/ngày. Giả sử mỗi sự kiện sau mã hóa khoảng 600 byte:

- Một ngày: `2.400 × 600 = 1.440.000 byte`, khoảng **1,37 MiB**.
- Ba mươi ngày: `43.200.000 byte`, khoảng **41,2 MiB**.
- Chín mươi ngày: `129.600.000 byte`, khoảng **123,6 MiB**.

Đây chỉ là **giả định để thiết kế**, chưa tính overhead, các trường cố định và đột biến lưu lượng. Nếu đặt ngân sách vận hành nội bộ cho một tài liệu là 2 MiB, mảng sự kiện liên tục sẽ chạm ngưỡng đó chỉ sau khoảng một ngày rưỡi. Khi cần giữ lịch sử 90 ngày, một tài liệu duy nhất rõ ràng không phải ranh giới phù hợp.

### 4.2. Tài liệu lớn gây lãng phí trên đường đọc

Giả sử trang hồ sơ chỉ hiển thị tên người dùng và 10 thông báo mới. Nếu `users` nhúng toàn bộ 50.000 thông báo, truy vấn phải làm việc với một cấu trúc rất lớn, dù giao diện chỉ cần vài trường.

Phép chiếu (*projection*) có thể giảm dữ liệu trả về, tùy khả năng hệ quản trị, nhưng không xóa đi mọi chi phí lưu trữ, xử lý, bộ nhớ đệm và cập nhật của một tài liệu lớn. Hơn nữa, nhiều API vô tình trả cả tài liệu nếu người viết truy vấn quên giới hạn trường.

### 4.3. Mảng tăng vô hạn làm phức tạp truy vấn và phân trang

Một mảng dài cần được lọc theo nhiều điều kiện, sắp xếp theo ngày và phân trang. Các hệ quản trị có mức hỗ trợ khác nhau; thường khó tổ chức đường truy vấn này hơn so với các tài liệu con có chỉ mục riêng.

Nếu chỉ cần lấy trang 101 của bình luận một bài viết, không nên buộc API tải hoặc xử lý toàn bộ mảng bình luận chỉ để bỏ qua 3.000 phần tử đầu.

### 4.4. Tài liệu cha có thể trở thành điểm nóng ghi

Nhiều người dùng cùng thêm bình luận vào một bài viết có thể cùng tác động lên một tài liệu `posts`. Dù mỗi bình luận nhỏ, mức ghi đồng thời tập trung có thể dẫn đến xung đột, thử lại hoặc giảm thông lượng. Nguy cơ phụ thuộc cách hệ quản trị kiểm soát ghi và cách ứng dụng cập nhật mảng.

Một tập dữ liệu với 20.000 cập nhật/phút phân tán trên 20.000 tài liệu thường có đặc điểm khác hẳn 20.000 cập nhật/phút dồn vào **một** tài liệu. Vì vậy, phải đo **phân phối thao tác ghi theo khóa tài liệu**, không chỉ tổng số lượt ghi.

### 4.5. Di trú càng khó khi mảng đã quá lớn

Nếu ban đầu nhúng bình luận rồi sau này phải tách, hệ thống cần xử lý các bản ghi cũ, bình luận mới đến trong lúc chuyển đổi, định danh trùng, tính nhất quán và các phiên bản ứng dụng vẫn đọc cấu trúc cũ. Tách sớm theo một ranh giới có thể dự đoán được thường dễ hơn xử lý sự cố khi tài liệu chạm giới hạn.

## 5. Không chỉ mảng: những kiểu tăng trưởng khó nhận thấy

Mảng lịch sử là dấu hiệu dễ thấy nhất, nhưng dữ liệu lồng nhau còn có những kiểu tăng trưởng khác:

- **Đối tượng có khóa động:** một bản đồ `countersByUserId` thêm một khóa cho mỗi người dùng sẽ tăng dù không có mảng.
- **Độ sâu động:** cây bình luận hoặc thư mục được nhúng đệ quy có thể vượt ngân sách độ sâu.
- **Chuỗi tích lũy:** trường `auditText` nối thêm sự kiện vào một chuỗi duy nhất sẽ tăng liên tục.
- **Mảng chứa phần tử biến thiên lớn:** bình luận 100 ký tự và tài liệu đính kèm dạng base64 có kích thước khác nhau rất xa.
- **Bản sao nhiều chiều:** mỗi tài liệu chứa danh sách tham chiếu hai chiều, rồi danh sách được sao chép ở nhiều nơi làm tăng dung lượng và gánh nặng đồng bộ.

Ví dụ phản mẫu với khóa động:

```json
{
  "postId": "POST-101",
  "likesByUser": {
    "USR-001": true,
    "USR-002": true,
    "USR-003": true
  }
}
```

Khi số người thích tăng lớn, đối tượng `likesByUser` có vấn đề tương tự mảng không giới hạn. Nếu cần kiểm tra một người đã thích bài và tổng lượt thích, có thể lưu `likes` thành tài liệu liên kết `(postId, userId)` cùng một bộ đếm dẫn xuất được cập nhật có kiểm soát.

## 6. Truy vấn mảng lồng nhau: đúng phần tử, đúng điều kiện

Cú pháp dưới đây **minh họa bằng MongoDB**. Các cơ sở dữ liệu tài liệu khác có ngôn ngữ truy vấn và đặc tính khác nhau. Mục tiêu là hiểu semantics, không ghi nhớ cú pháp của một sản phẩm.

### 6.1. Truy vấn theo đường dẫn

Với tài liệu:

```json
{
  "orderId": "ORD-041",
  "items": [
    { "lineId": "L-01", "sku": "BOOK", "quantity": 1 },
    { "lineId": "L-02", "sku": "PEN", "quantity": 5 }
  ]
}
```

Một truy vấn:

```javascript
db.orders.find({
  "items.sku": "BOOK",
  "items.quantity": { $gte: 3 }
});
```

có thể khớp tài liệu trên, dù dòng `BOOK` chỉ có số lượng 1. Lý do: hai điều kiện theo đường dẫn mảng có thể được thỏa mãn bởi **hai phần tử khác nhau**.

Nếu yêu cầu là “tìm đơn có **một dòng BOOK số lượng ít nhất 3**”, dùng điều kiện áp dụng cho cùng một phần tử:

```javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: "BOOK",
      quantity: { $gte: 3 }
    }
  }
});
```

Tài liệu ví dụ sẽ **không** khớp. Sự khác biệt này rất quan trọng khi lọc danh mục sản phẩm, quyền truy cập, sự kiện hoặc trạng thái nằm trong mảng đối tượng.

### 6.2. Phép chiếu không đồng nghĩa với phân trang phần tử con

```javascript
// Chỉ trả các trường cần thiết ở mức tài liệu.
db.orders.find(
  { orderId: "ORD-041" },
  { _id: 0, orderId: 1, status: 1, itemsTotalMinor: 1 }
);
```

Phép chiếu giúp tránh trả `items` khi màn hình danh sách không cần. Nếu cần hàng nghìn phần tử con được lọc, sắp xếp, phân trang và tìm kiếm độc lập, **tách phần con thành tài liệu riêng** thường đem lại mô hình truy vấn dễ kiểm soát hơn.

Một số hệ quản trị có toán tử trích phần tử mảng hoặc tổng hợp mảng, nhưng không nên xem những toán tử này là giải pháp chung cho mảng tăng không giới hạn.

### 6.3. Chỉ mục trên trường lồng nhau và mảng

Trong một số cơ sở dữ liệu tài liệu, có thể tạo chỉ mục trên đường dẫn trường lồng nhau:

```javascript
// Ví dụ cho bộ lọc đơn hàng theo dòng sản phẩm.
db.orders.createIndex({ "items.sku": 1 });

// Với bình luận được tách tài liệu riêng:
db.comments.createIndex({
  postId: 1,
  moderationStatus: 1,
  createdAt: -1,
  _id: -1
});
```

Chỉ mục trên mảng có thể là **multikey** hoặc cơ chế tương đương; một tài liệu có nhiều giá trị lập chỉ mục, khiến kích thước và chi phí cập nhật chỉ mục tăng. Các hệ quản trị còn có quy tắc giới hạn khi xây chỉ mục phức hợp qua nhiều mảng.

Hãy đo kế hoạch thực thi và thử truy vấn trên dữ liệu lớn, đặc biệt với các điều kiện cần khớp **cùng phần tử**, bộ lọc nhiều cấp và trường có mức chọn lọc thấp. Không tạo chỉ mục cho mọi đường dẫn chỉ vì chúng tồn tại trong JSON.

## 7. Cập nhật mảng: nguyên tử, tranh chấp và bất biến

### 7.1. Thao tác thay đổi phần tử

Ví dụ cú pháp MongoDB:

```javascript
// Thêm một dòng vào mảng của đơn hàng.
db.orders.updateOne(
  { orderId: "ORD-041", status: "DRAFT" },
  {
    $push: {
      items: {
        lineId: "L-03",
        sku: "RULER",
        quantity: 1,
        unitPriceMinor: 15000
      }
    }
  }
);

// Xóa dòng theo định danh ổn định.
db.orders.updateOne(
  { orderId: "ORD-041", status: "DRAFT" },
  { $pull: { items: { lineId: "L-03" } } }
);
```

Đây là ví dụ cú pháp cập nhật mảng, **chưa phải một quy trình sửa đơn hợp lệ hoàn chỉnh**. Nếu có `itemsTotalMinor`, việc thêm/xóa dòng phải cập nhật tổng tiền nhất quán và bảo vệ ràng buộc nghiệp vụ; thao tác tách rời có thể làm dữ liệu sai. Cũng cần kiểm tra trùng `lineId`, trạng thái đơn và quyền sửa.

### 7.2. Tránh thao tác đọc–sửa–ghi đè toàn bộ tài liệu

Mẫu rủi ro:

1. Tiến trình A đọc tài liệu phiên bản 5.
2. Tiến trình B đọc cùng tài liệu phiên bản 5.
3. A sửa mảng và ghi đè toàn bộ tài liệu.
4. B sửa một phần tử khác rồi ghi đè bản đã đọc trước đó; thay đổi của A có thể mất.

Nên dùng thao tác cập nhật đúng trường hoặc phần tử, và dùng **optimistic concurrency control** khi cần bảo vệ bất biến:

```javascript
const result = db.orders.updateOne(
  {
    orderId: "ORD-041",
    status: "DRAFT",
    version: 5
  },
  {
    $set: { status: "CONFIRMED" },
    $inc: { version: 1 },
    $currentDate: { confirmedAt: true }
  }
);

if (result.matchedCount === 0) {
  // Tài liệu đã thay đổi; đọc lại và quyết định xử lý nghiệp vụ.
}
```

Một số hệ quản trị bảo đảm thao tác ghi nguyên tử ở cấp tài liệu, nhưng mức hỗ trợ và cơ chế xung đột khác nhau. **Cập nhật nguyên tử một tài liệu không tự động bảo đảm toàn bộ quy trình nghiệp vụ** nếu còn tồn kho, thanh toán hoặc tài liệu khác liên quan.

### 7.3. Giới hạn mảng tóm tắt ngay khi ghi

Nếu chỉ cần giữ 20 thông báo gần đây để hiển thị nhanh, có thể chủ động giới hạn mảng:

```javascript
// Mảng ở hồ sơ chỉ là bản xem trước giới hạn 20 mục.
db.users.updateOne(
  { userId: "USR-042" },
  {
    $push: {
      recentNotifications: {
        $each: [
          {
            notificationId: "N-900",
            type: "COURSE_UPDATE",
            createdAt: "2026-11-22T08:00:00Z"
          }
        ],
        $slice: -20
      }
    }
  }
);
```

Ở ví dụ này, `$slice: -20` giữ 20 phần tử cuối sau thao tác thêm. **Đây không phải nơi lưu lịch sử đầy đủ**: thông báo cũ bị loại khỏi bản xem trước. Nếu người dùng cần xem toàn bộ, lưu nguồn chính trong collection `notifications` riêng và coi `recentNotifications` là bản sao có giới hạn, kèm quy tắc đồng bộ và đối soát.

Nếu dữ liệu có thể được thêm trễ hoặc sai thứ tự thời gian, không nên mặc nhiên hiểu “20 phần tử được thêm cuối” là “20 sự kiện có thời điểm mới nhất”; cần quy định sắp xếp theo sự kiện và cơ chế cập nhật phù hợp.

### 7.4. Không dùng mảng như một ràng buộc duy nhất toàn hệ thống

Thao tác thêm vào mảng không mặc nhiên ngăn hai yêu cầu nghiệp vụ trùng nhau, đặc biệt khi một phần tử chứa nhiều thuộc tính hoặc có thay đổi về cấu trúc. Với quan hệ “một người chỉ thích một bài một lần”, tài liệu `likes` riêng cùng chỉ mục duy nhất trên `(postId, userId)` thường diễn đạt bất biến rõ hơn.

## 8. Các mẫu thay thế mảng tăng vô hạn

### 8.1. Tách phần tử con thành tài liệu riêng

Thay vì một bài viết chứa mọi bình luận:

```text
posts
  { postId, title, authorId, commentCount }

comments
  {
    commentId, postId, authorId,
    text, createdAt, moderationStatus
  }
```

Lợi ích:

- Mỗi bình luận có định danh, vòng đời và quyền xử lý riêng.
- Có thể lọc, sắp xếp và phân trang theo `postId`.
- Thao tác thêm bình luận không luôn buộc ghi vào tài liệu bài viết.
- Lịch sử có thể được lưu trữ hoặc xóa theo chính sách riêng.

Đổi lại, màn hình chi tiết cần lấy bài viết và các bình luận bằng nhiều lượt truy vấn hoặc phép kết hợp được hệ quản trị hỗ trợ. Nếu `commentCount` nằm ở `posts`, phải xác định nguồn sự thật và cách xử lý khi bộ đếm bị lệch, bị ghi trùng hoặc nhận sự kiện trễ.

### 8.2. Nhúng một tập con có giới hạn (*bounded subset*)

Một tài liệu có thể nhúng 3 đánh giá tiêu biểu hoặc 20 thông báo gần nhất, trong khi dữ liệu đầy đủ được lưu riêng:

```json
{
  "postId": "POST-101",
  "title": "Mô hình dữ liệu",
  "commentPreview": [
    { "commentId": "C-200", "text": "Ví dụ dễ hiểu" },
    { "commentId": "C-199", "text": "Có bài tiếp theo không?" }
  ],
  "commentCount": 1248
}
```

Phải quy định:

1. Số phần tử tối đa trong bản xem trước.
2. Tiêu chí chọn: mới nhất, hữu ích nhất, đã kiểm duyệt hay theo ưu tiên khác.
3. Nguồn sự thật và sự kiện làm thay đổi bản xem trước.
4. Độ trễ đồng bộ được chấp nhận.
5. Cách xử lý khi một bình luận trong bản xem trước bị xóa hoặc ẩn.

Không nên biến bản xem trước thành “danh sách đầy đủ” chỉ vì những ngày đầu số lượng nhỏ.

### 8.3. Chia bucket theo thời gian và giới hạn dung lượng

Dữ liệu chuỗi thời gian có thể chia thành các tài liệu theo thiết bị/ngày/giờ hoặc theo số sự kiện:

```json
{
  "deviceId": "DEV-018",
  "bucketStart": "2026-11-22T08:00:00Z",
  "part": 0,
  "events": [
    { "at": "2026-11-22T08:00:05Z", "value": 28.5 },
    { "at": "2026-11-22T08:00:10Z", "value": 28.8 }
  ],
  "eventCount": 2
}
```

Một bucket theo giờ **chưa chắc** có kích thước hữu hạn trong thực tế: thiết bị lỗi có thể gửi hàng triệu sự kiện trong một giờ. Vì vậy, cần giới hạn bằng **thời gian và số phần tử/byte**, rồi tạo `part` mới khi gần chạm ngân sách.

Đánh đổi: ít tài liệu hơn khi đọc một khoảng thời gian, nhưng cập nhật bucket đang mở có thể trở thành điểm nóng; dữ liệu đến trễ phải được gắn vào bucket đúng; lọc sâu từng sự kiện có thể khó; cần xử lý giới hạn khi nhiều tiến trình cùng thêm phần tử. Đây là mẫu cần đo tải thực tế trước khi chọn.

### 8.4. Tách dữ liệu nóng và dữ liệu lưu trữ

Các sự kiện mới thường được truy vấn nhiều; sự kiện cũ chủ yếu phục vụ kiểm toán hoặc báo cáo. Có thể dùng:

- Collection giao dịch cho dữ liệu mới, với chỉ mục phục vụ truy vấn trực tuyến.
- Kho lưu trữ lâu dài hoặc hệ phân tích cho dữ liệu cũ.
- Chính sách lưu/xóa, định dạng xuất, cách tra cứu và đối soát được xác định.

Việc lưu trữ theo thời gian phải tuân theo yêu cầu nghiệp vụ và pháp lý; không được tự động xóa nhật ký quan trọng chỉ vì chúng làm tài liệu lớn.

### 8.5. Metadata ở tài liệu, nội dung nhị phân ở kho phù hợp

Đối với ảnh, video hoặc tệp đính kèm lớn, thường chỉ nhúng metadata và định danh:

```json
{
  "productId": "PRD-017",
  "images": [
    {
      "assetId": "ASSET-01",
      "alt": "Mặt trước sản phẩm",
      "position": 1
    }
  ]
}
```

Bản thân byte của ảnh có thể lưu ở hệ lưu trữ đối tượng hoặc cơ chế lưu tệp phù hợp. Cần thiết kế quyền truy cập, vòng đời tệp, chính sách xóa và xử lý tài nguyên không còn được tham chiếu.

## 9. Thiết kế schema và ràng buộc cho cấu trúc lồng nhau

Tài liệu linh hoạt **không có nghĩa là không cần hợp đồng dữ liệu**. Khi thiết kế mảng và đối tượng lồng nhau, cần quy định rõ:

| Hạng mục | Ví dụ quy tắc |
| --- | --- |
| Kiểu dữ liệu | `items` phải là mảng đối tượng, `quantity` là số nguyên dương |
| Trường bắt buộc | Mỗi dòng có `lineId`, `productId`, `quantity` |
| Kích thước | Mảng `items` tối đa 60 dòng theo nghiệp vụ |
| Giá trị hợp lệ | `status` thuộc tập trạng thái được quy định |
| Tính duy nhất | Không có hai dòng có cùng `lineId` trong một đơn |
| Trạng thái rỗng | Phân biệt trường không tồn tại, `null` và mảng rỗng `[]` |
| Bất biến | Tổng tiền phù hợp dòng hàng và các điều chỉnh |
| Phiên bản | `schemaVersion` cho cấu trúc, `version` cho cập nhật đồng thời |
| Bảo mật | Không trả dữ liệu con nhạy cảm trong API công khai |

### 9.1. Trường vắng mặt, null và mảng rỗng

Ba biểu diễn sau có thể mang ý nghĩa khác nhau:

```jsonc
{ "userId": "U-1" }                 // Chưa có trường notifications
{ "userId": "U-1", "notifications": null } // Có trường nhưng giá trị null
{ "userId": "U-1", "notifications": [] }   // Biết chắc danh sách đang rỗng
```

Ứng dụng và công cụ truy vấn có thể xử lý chúng khác nhau. Hãy chọn quy ước nhất quán để API và di trú dữ liệu không suy diễn sai, đặc biệt khi triển khai thêm trường mới.

### 9.2. Tài liệu lồng nhau cần định danh phần tử khi cập nhật

Nếu mảng đối tượng có thể thay đổi thứ tự, cập nhật theo vị trí như “phần tử thứ ba” dễ sai khi có thao tác chèn/xóa. Tốt hơn là mỗi phần tử quan trọng có `lineId` ổn định, rồi dùng bộ lọc theo định danh trong thao tác cập nhật được hệ quản trị hỗ trợ.

Dù có định danh, các bất biến như “tổng tiền phải bằng tổng các dòng” vẫn cần được bảo vệ trong cùng thao tác nguyên tử hoặc bằng cơ chế phối hợp phù hợp.

### 9.3. Giới hạn độ sâu và cấu trúc đệ quy

Dữ liệu như cây danh mục hoặc chuỗi phản hồi lồng nhau có thể tạo độ sâu khó dự đoán. Những cấu trúc cần duyệt, tìm kiếm hoặc thay đổi nhánh độc lập có thể phù hợp hơn với tài liệu riêng có `parentId`, hoặc mô hình đồ thị nếu bài toán truy vấn quan hệ nhiều bước là trọng tâm. Cách biểu diễn phải được chọn theo đường truy cập thực tế.

## 10. Bài toán tổng hợp: khóa học, bài học và hoạt động học viên

### 10.1. Yêu cầu nghiệp vụ

Một nền tảng học trực tuyến có các giả định:

- Mỗi khóa thường có 20–50 bài; phần mô tả ngắn, nội dung bài trung bình 30 KiB.
- Mỗi khóa có thể đạt 100.000 học viên.
- Học viên ghi sự kiện xem bài, dừng video, làm bài tập; sự kiện có thể tăng hàng ngày.
- Màn hình giới thiệu khóa chỉ cần tiêu đề, mô tả và 5 bài nổi bật.
- Màn hình học bài cần nội dung đúng một bài và tiến độ của học viên.
- Giáo viên có thể sửa nội dung một bài độc lập và xuất bản phiên bản mới.
- Báo cáo phân tích cần tổng hợp hoạt động hàng triệu sự kiện theo ngày.

### 10.2. Thiết kế dễ gây vấn đề

Nếu tài liệu `course` chứa toàn bộ nội dung bài, toàn bộ tiến độ học viên và tất cả sự kiện xem bài, nó sẽ lớn nhanh và dồn nhiều tác vụ ghi vào một tài liệu. Cụ thể:

- Chỉ riêng 50 bài × 30 KiB đã khoảng **1.500 KiB** nội dung.
- Nếu 100.000 học viên có trạng thái cho 50 bài, có thể tạo **5.000.000 trạng thái tiến độ**.
- Sự kiện thao tác không có giới hạn tự nhiên khi giữ lịch sử dài hạn.

Việc cấu trúc ban đầu dễ biểu diễn bằng JSON không chứng minh nó phù hợp ở quy mô lớn.

### 10.3. Thiết kế có ranh giới theo vòng đời

```text
courses
  {
    courseId, title, description, authorId,
    featuredLessons: [{ lessonId, title, position }], // tối đa 5
    lessonCount, schemaVersion
  }

lessons
  {
    lessonId, courseId, title, content,
    position, publishedVersion
  }

lessonProgress
  {
    learnerId, lessonId, state,
    completedAt, version
  }

learningEvents
  {
    eventId, learnerId, lessonId, eventType,
    occurredAt, receivedAt, payload
  }
```

Lập luận:

- **Nhúng danh sách xem trước 5 bài** vì dữ liệu nhỏ và được đọc cùng thông tin khóa. Phải có quy tắc cập nhật khi tiêu đề hoặc thứ tự bài thay đổi.
- **Nội dung bài** nằm trong tài liệu `lessons` để dễ xuất bản, đọc và cập nhật độc lập.
- **Tiến độ** nằm theo cặp học viên–bài vì có nhiều người ghi đồng thời, truy vấn theo học viên và từng bài. Có thể cân nhắc tài liệu tiến độ theo học viên–khóa nếu giới hạn số bài và đường đọc chứng minh phù hợp.
- **Sự kiện** là các bản ghi riêng hoặc bucket có giới hạn vì tốc độ tăng lớn; dữ liệu phân tích có thể được đồng bộ sang hệ chuyên xử lý tổng hợp.
- **Không nhúng toàn bộ tiến độ hoặc hoạt động vào `courses`.**

### 10.4. Khóa và chỉ mục cần kiểm chứng

| Đường truy cập | Khóa/điều kiện | Chỉ mục hoặc ràng buộc gợi ý |
| --- | --- | --- |
| Danh sách bài theo khóa | `courseId`, sắp xếp `position` | `(courseId, position)` |
| Nội dung một bài | `lessonId` | Khóa định danh duy nhất |
| Tiến độ bài của học viên | `learnerId, lessonId` | Khóa ghép duy nhất cho một tiến độ hiện hành |
| Toàn bộ tiến độ học viên | `learnerId` | Chỉ mục bắt đầu từ `learnerId` |
| Sự kiện của học viên theo ngày | `learnerId, occurredAt` | Chỉ mục theo đường truy vấn, chính sách phân trang |
| Báo cáo nhiều khóa/tháng | Tập sự kiện lớn theo thời gian | Xem xét tập dữ liệu phân tích hoặc bản tổng hợp dẫn xuất |

Đây là gợi ý logic; thứ tự trường và kiểu chỉ mục thực tế phải đo với truy vấn và hệ quản trị đã chọn. Trong hệ đa tổ chức, thêm `tenantId` vào điều kiện, khóa duy nhất và ranh giới truy cập phù hợp.

### 10.5. Những câu hỏi có thể làm thay đổi thiết kế

- Có cần xem **toàn bộ** tiến độ 50 bài trong một lượt đọc không? Tỷ lệ ghi đồng thời trên mỗi học viên là bao nhiêu?
- Có quy định giữ sự kiện học tập trong bao lâu và yêu cầu xóa dữ liệu cá nhân thế nào?
- Khi giáo viên xuất bản khóa theo một phiên bản, người học phải đọc đồng bộ các phiên bản bài không?
- Sự kiện đến trễ hoặc bị gửi trùng có ảnh hưởng báo cáo không? Có cần định danh sự kiện và cơ chế khử trùng?
- Truy vấn chi tiết sự kiện có phổ biến như truy vấn báo cáo tổng hợp không?

Những yêu cầu đó giúp quyết định nên tách hơn nữa, gom theo bucket hay tạo một mô hình đọc bổ sung.

## 11. Di trú từ mảng lớn sang tài liệu riêng

Giả sử hệ thống cũ đã lưu bình luận trong `posts.comments`. Khi tách thành collection `comments`, một lộ trình an toàn về nguyên tắc gồm:

1. **Thiết kế dữ liệu đích:** khóa `commentId` ổn định, `postId`, tác giả, trạng thái, thời gian; chỉ mục cho truy vấn và ràng buộc duy nhất phù hợp.
2. **Xác định nguồn sự thật trong chuyển tiếp:** ghi rõ đường ghi mới, đường đọc mới, các phiên bản ứng dụng cũ và cách xử lý thay đổi xuất hiện trong lúc di trú.
3. **Triển khai đọc tương thích:** kiểm soát giai đoạn hai cấu trúc cùng tồn tại, tránh hiển thị trùng.
4. **Chuyển dữ liệu theo lô có thể chạy lại:** giữ định danh ổn định để retry không tạo thêm bình luận trùng.
5. **Bắt kịp thay đổi đang diễn ra:** có cơ chế nhận các bình luận được thêm/sửa/xóa trong thời gian di trú.
6. **Đối soát:** so sánh số lượng, định danh, trạng thái và dữ liệu bị thiếu; kiểm tra các bài nhiều bình luận nhất.
7. **Chuyển hẳn đường ghi/đọc và gỡ cấu trúc cũ:** chỉ sau khi đo xác nhận độ nhất quán và các phiên bản ứng dụng liên quan đã tương thích.

Nếu dùng `schemaVersion` để phân biệt dạng tài liệu, cần thực sự hỗ trợ phiên bản trong mã đọc và kiểm tra dữ liệu; chỉ tăng số phiên bản không tự chuyển đổi nội dung.

## 12. Kiểm chứng lựa chọn bằng số liệu

Một bản thiết kế đáng tin cậy cần thể hiện **giả định định lượng** thay vì chỉ ghi “mảng này chắc nhỏ”. Bảng khảo sát tối thiểu:

| Chỉ số | Cách xác định | Vì sao quan trọng |
| --- | --- | --- |
| Số phần tử/con trên cha | Trung vị, p95, p99, lớn nhất, trần nghiệp vụ | Phát hiện tài liệu bất thường |
| Kích thước phần tử | Số byte thực trên dữ liệu mẫu, p95/p99 | Dự báo tổng kích thước |
| Tốc độ thêm/xóa | Phần tử/ngày và kịch bản cao điểm | Dự đoán thời điểm chạm ngưỡng |
| Mức ghi đồng thời trên cha | Số cập nhật tập trung theo khóa | Phát hiện điểm nóng |
| Truy vấn phổ biến | Trường, bộ lọc, sắp xếp, trang | Chọn nhúng/tách và chỉ mục |
| Dung lượng/độ sâu | Theo định dạng lưu của hệ quản trị | Kiểm tra giới hạn sản phẩm |
| Thời hạn lưu | Nhu cầu nghiệp vụ và chính sách | Quyết định lưu trữ, xóa, bucket |
| Bất biến và độ trễ đồng bộ | Những gì phải nhất quán tức thời | Thiết kế giao dịch và bản sao |

Sau đó kiểm thử ít nhất ba loại dữ liệu: cha điển hình, cha p99 và cha lớn nhất hợp lý; thêm trường dài, mảng rỗng, trường thiếu và các sự kiện đến trễ. Dùng tải đọc/ghi tương ứng với công việc thật để đo:

- Độ trễ trung vị, p95, p99 cho truy vấn và ghi.
- Số byte đọc/trả về và số tài liệu phải truy cập.
- Kích thước tài liệu lớn nhất, tổng dung lượng chỉ mục.
- Tỷ lệ tranh chấp, thất bại hoặc retry cập nhật.
- Khả năng duy trì bất biến khi ghi đồng thời.
- Chi phí di trú và phục hồi sau gián đoạn.

Không có con số tối ưu chung cho mọi hệ thống. Những giới hạn cuối cùng cần xuất phát từ **SLA, truy vấn, tải thực tế và sản phẩm cơ sở dữ liệu**.

## 13. So sánh nhanh với các mô hình dữ liệu khác

| Nhu cầu | Cách tiếp cận đáng cân nhắc |
| --- | --- |
| Đọc/ghi một aggregate có cấu trúc lồng nhau, phần con hữu hạn | Tài liệu với nhúng có kiểm soát |
| Quan hệ phức tạp, cần khóa ngoại và phép nối linh hoạt | Quan hệ, hoặc tài liệu có tham chiếu và ràng buộc phù hợp |
| Duyệt nhiều bước qua các quan hệ dạng mạng | Đồ thị |
| Tổng hợp sự kiện lớn theo ngày/tháng, quét nhiều bản ghi | Kho phân tích hoặc cấu trúc dữ liệu hướng phân tích |
| Vừa ghi giao dịch, vừa phân tích lượng lớn lịch sử | Có thể tách đường dữ liệu vận hành và phân tích kèm đồng bộ/đối soát |

Đây là định hướng học thuật, không phải giới hạn tuyệt đối của từng sản phẩm. Nhiều cơ sở dữ liệu quan hệ hỗ trợ JSON; một số hệ tài liệu hỗ trợ giao dịch và phép nối. Khi chọn hệ lưu trữ, cần xem khả năng và ràng buộc của phiên bản cụ thể.

## 14. Bài tập ứng dụng

**Tình huống:** Một ứng dụng quản lý sự kiện tổ chức các buổi hội thảo. Mỗi hội thảo có tiêu đề, địa điểm, 10–30 diễn giả, tối đa 1.000 người đăng ký, hàng trăm nghìn lượt mở trang và nhật ký quét vé tại cổng. Thông tin diễn giả thay đổi không thường xuyên; vé có thể được quét cùng lúc ở nhiều cổng; log mở trang được giữ một năm để phân tích.

Hãy quyết định nên nhúng hay tách đối với: danh sách diễn giả, dữ liệu đăng ký, lượt quét vé và log mở trang.

### Gợi ý lập luận

| Nhóm dữ liệu | Bội số/kích thước | Tần suất ghi | Phương án gợi ý |
| --- | --- | --- | --- |
| 10–30 mục tóm tắt diễn giả | Nhỏ, có trần | Thấp | Nhúng metadata cần hiển thị hoặc tham chiếu nếu hồ sơ dùng chung |
| Đăng ký của 1.000 người | Có trần nhưng thường cần tìm kiếm theo người, trạng thái | Có thể tăng cao theo đợt | Tài liệu `registrations` riêng; khóa duy nhất `(eventId, attendeeId)` theo quy tắc |
| Trạng thái quét vé | Theo từng lượt đăng ký | Đồng thời tại nhiều cổng | Ghi vào vé/đăng ký riêng với điều kiện chống quét trùng |
| Lịch sử quét | Tăng theo nghiệp vụ | Cao ở thời điểm vào cổng | Tài liệu sự kiện riêng, có định danh và chính sách giữ |
| Log mở trang | Tăng rất lớn | Cao, liên tục | Event store/time-series/bucket có giới hạn; không nhúng vào `events` |

**Thử thêm điều kiện:** nếu diễn giả là người dùng có tài khoản và cập nhật hồ sơ trên nhiều hội thảo, nên lưu `speakerId` và chỉ nhúng bản tóm tắt phục vụ hiển thị khi có cơ chế cập nhật. Nếu sự kiện cần lưu chương trình “đúng như lúc diễn ra”, có thể giữ snapshot lịch sử khác với hồ sơ diễn giả hiện hành.

**Câu hỏi tự kiểm tra:**

1. Nếu hội thảo có 30 diễn giả nhưng mỗi hồ sơ chứa tệp PDF 10 MiB, chỉ dựa vào số lượng 30 để nhúng có đúng không?
2. Nếu 20.000 lượt mở trang/phút được dồn vào một mảng của tài liệu sự kiện, nguy cơ xuất hiện ở đâu trước: dung lượng hay ghi đồng thời?
3. Nếu danh sách đăng ký được nhúng và ứng dụng phải tìm tất cả người chưa thanh toán, việc lọc/phân trang sẽ khó ở đâu?
4. Nếu chỉ lưu 20 lượt quét gần nhất trong tài liệu hội thảo, phải lưu lịch sử chính ở đâu để phục vụ kiểm toán?
5. Khi một vé bị quét trùng ở hai cổng trong cùng thời điểm, cần bất biến và cập nhật có điều kiện nào?

## 15. Checklist thiết kế dữ liệu lồng nhau và mảng

- [ ] Đã xác định ngữ nghĩa của từng đối tượng/mảng: thứ tự, trùng lặp, rỗng, `null` và trường thiếu.
- [ ] Đã xác định **giới hạn nghiệp vụ** hoặc khả năng tăng liên tục của mỗi mảng/đối tượng khóa động.
- [ ] Đã đo bội số và kích thước p50/p95/p99 cùng trường hợp lớn nhất.
- [ ] Đã ước lượng tốc độ tăng và thời điểm chạm ngân sách kích thước tài liệu.
- [ ] Đã kiểm tra tần suất ghi và độ đồng thời lên **cùng tài liệu cha**.
- [ ] Đã liệt kê các truy vấn cần lọc/phân trang phần tử con độc lập.
- [ ] Đã kiểm tra điều kiện phải áp dụng cho **cùng phần tử mảng**.
- [ ] Đã thiết kế khóa phần tử, validation, chỉ mục và bảo vệ cập nhật đồng thời.
- [ ] Đã phân biệt dữ liệu nguồn chính, snapshot lịch sử và bản xem trước có giới hạn.
- [ ] Đã cân nhắc tách tài liệu con, bucket có giới hạn, lưu trữ lịch sử và tệp nhị phân.
- [ ] Đã có kế hoạch tương thích/di trú nếu cấu trúc cần thay đổi về sau.
- [ ] Đã kiểm chứng bằng dữ liệu và tải gần với kịch bản vận hành, không chỉ dữ liệu mẫu nhỏ.

**Điểm cần nhớ:** Dữ liệu lồng nhau và mảng giúp một tài liệu mô tả trọn vẹn một đơn vị nghiệp vụ. Nhưng **mọi tập con tăng không giới hạn, được truy vấn hoặc cập nhật độc lập, đều phải được xem xét như một ranh giới dữ liệu riêng**. Quyết định đúng cần dựa trên kích thước thực, tốc độ tăng, mức ghi đồng thời, bất biến và đường truy cập — không chỉ dựa vào cấu trúc JSON ban đầu.

# Giới hạn kích thước document, độ lồng nhau và tên trường

MongoDB lưu dữ liệu dưới dạng **BSON document**. BSON (*Binary JSON*) có thể biểu diễn object, array, string, number, date, binary và nhiều kiểu dữ liệu khác. Cấu trúc linh hoạt của BSON giúp ứng dụng lưu được những đối tượng nghiệp vụ có thành phần lồng nhau, nhưng một document không thể tăng kích thước hoặc độ sâu vô hạn; tên trường cũng chịu những quy tắc kỹ thuật riêng.

Ba giới hạn cần ghi nhớ khi thiết kế schema MongoDB là:

| Khía cạnh | Giới hạn hoặc quy tắc quan trọng | Hệ quả thiết kế |
| --- | --- | --- |
| Kích thước một BSON document | **Tối đa 16 MiB = 16.777.216 byte.** | Không đưa mảng hoặc dữ liệu nhị phân tăng không giới hạn vào một document. |
| Độ lồng nhau | **Không quá 100 cấp** BSON document; mỗi object hoặc array lồng nhau làm tăng độ sâu. | Tránh lưu trực tiếp những cây hoặc dữ liệu đệ quy sâu không kiểm soát. |
| Tên trường | Là chuỗi, **không được chứa ký tự null** (`\u0000`); trong cùng document tên trường phải duy nhất. | Cần kiểm soát tên trường khi nhập dữ liệu và thiết kế API. |
| Dấu `.` và tiền tố `$` | MongoDB hiện đại cho phép lưu, nhưng **có nhiều hạn chế về truy vấn, index, shard key và công cụ import/export**. | Nên tránh trong tên trường được ứng dụng tự thiết kế. |
| Trường `_id` | Dành cho định danh chính, duy nhất trong collection và không được thay đổi sau khi tạo. | Chọn định danh ổn định, tránh tạo cấu trúc `_id` khó kiểm soát. |

Giới hạn **16 MiB áp dụng cho từng document**, không phải cho cả collection hoặc database. Một collection có thể chứa số lượng rất lớn các document hợp lệ; ngược lại, một document riêng lẻ vượt giới hạn vẫn không thể lưu bằng cách chỉ tăng dung lượng ổ đĩa hoặc RAM.

## 1. Hiểu giới hạn 16 MiB theo đúng đơn vị

### 1.1. MiB khác MB

Tài liệu MongoDB sử dụng **mebibyte (MiB)**:

```text
1 MiB  = 1.048.576 byte
16 MiB = 16 x 1.048.576 = 16.777.216 byte

1 MB   = 1.000.000 byte (theo hệ thập phân)
```

Do vậy, 16 MiB không đồng nhất với 16 triệu byte. Khi xem cảnh báo, chỉ số hoặc thực hiện phép tính dung lượng, phải dùng đơn vị nhất quán.

### 1.2. Kích thước nào bị giới hạn?

Giới hạn được tính theo **biểu diễn BSON của toàn bộ document**. Nó bao gồm các trường ở mức gốc và trường lồng nhau, giá trị, tên trường, `_id`, phần tử mảng cùng những byte cấu trúc BSON cần thiết. Không thể chỉ tính tổng số ký tự người dùng thấy trong một JSON và coi đó là kích thước BSON.

Một BSON document chứa thông tin độ dài, marker kiểu dữ liệu, tên khóa kết thúc bằng null và các giá trị được mã hóa theo kiểu tương ứng. Vì vậy:

- Một chuỗi Unicode có thể chiếm số byte UTF-8 khác với số ký tự hiển thị.
- Các khóa dài và lặp lại qua nhiều object con làm tăng kích thước.
- Mảng BSON sử dụng các tên khóa chỉ số như `"0"`, `"1"`, `"2"`, ... nên cũng phát sinh overhead.
- Một `ObjectId`, `Date`, `Int32`, `Int64`, `Decimal128` hoặc `Binary` có cách mã hóa khác nhau; kích thước JSON hiển thị không phải kích thước lưu trữ BSON.
- Nội dung nhị phân và các document con đều tính vào cùng giới hạn của document cha.

Ví dụ, document sau có kích thước thực lớn hơn tổng số ký tự trong `name` và `description` vì còn tên trường, `ObjectId`, số nguyên và metadata BSON:

```javascript
{
  _id: ObjectId("66a000000000000000000001"),
  name: "Sổ tay kỹ thuật",
  description: "Tài liệu có hỗ trợ Unicode",
  tags: ["mongodb", "bson", "database"],
  version: NumberInt(1)
}
```

### 1.3. Nén dữ liệu trên đĩa không làm thay đổi giới hạn document

WiredTiger có thể nén các trang dữ liệu lưu trên đĩa. Một document có thể chiếm ít dung lượng vật lý hơn sau nén, nhưng **giới hạn 16 MiB vẫn áp dụng cho BSON document**. Nói cách khác, không thể tạo một document 30 MiB rồi kỳ vọng cơ chế nén của storage engine làm nó trở thành hợp lệ.

Tương tự, tăng RAM, đổi storage engine, dùng replica set hay sharding không biến một document vượt 16 MiB thành document hợp lệ. Những kỹ thuật đó xử lý các khía cạnh khác của lưu trữ và mở rộng.

## 2. Document lớn lên như thế nào trong ứng dụng?

Xét ứng dụng quản lý hồ sơ khách hàng:

```javascript
db.customers.insertOne({
  _id: "C101",
  fullName: "Nguyễn An",
  preferences: {
    language: "vi",
    notifications: { email: true, push: false }
  },
  recentOrders: [
    { orderId: "O1001", amount: 245000 },
    { orderId: "O1002", amount: 389000 }
  ]
});
```

Lưu vài đơn hàng gần đây trong document khách hàng có thể thuận tiện cho một màn hình tổng quan. Tuy nhiên, nếu `recentOrders` thực chất là **mọi đơn hàng từ trước đến nay**, số phần tử sẽ tiếp tục tăng. Cuối cùng, một lần `$push` có thể khiến document vượt kích thước cho phép.

```javascript
db.customers.updateOne(
  { _id: "C101" },
  {
    $push: {
      recentOrders: { orderId: "O1003", amount: 79000 }
    }
  }
);
```

Lệnh ở trên hợp lệ về cú pháp, nhưng thành công hay thất bại còn tùy kích thước document **sau khi cập nhật**. MongoDB không bỏ bớt phần tử cũ chỉ vì mảng đã lớn. Khi thao tác vượt giới hạn, ứng dụng nhận lỗi và cần xử lý theo quy trình nghiệp vụ.

Đây là lý do một mô hình có vẻ hoạt động tốt khi thử nghiệm với 10 phần tử có thể không bền vững nếu về sau mỗi người dùng có hàng triệu bản ghi lịch sử.

### 2.1. Ba loại trường thường gây tăng kích thước bất ngờ

| Trường | Ví dụ | Nguy cơ |
| --- | --- | --- |
| Mảng tích lũy không giới hạn | `events`, `orders`, `comments`, `auditLogs`. | Mỗi lần thêm phần tử làm document cha tăng. |
| Nội dung nhị phân lớn | Ảnh, PDF, video hoặc bản nén gắn trực tiếp. | Một file có thể chiếm gần hết hoặc vượt giới hạn của document. |
| Payload lặp lại | Snapshot chi tiết, JSON từ hệ thống khác, danh sách object chứa nhiều key dài. | Overhead tích lũy và tăng chi phí truyền/đọc/ghi. |

Không phải **mảng** hay **object lồng nhau** đều xấu. Một địa chỉ gồm vài trường hoặc danh sách các dòng hàng của một đơn đặt hàng có giới hạn hợp lý thường là đối tượng phù hợp để embed. Vấn đề là **sự tăng trưởng không có ranh giới** và tần suất truy cập/cập nhật không phù hợp với một document duy nhất.

## 3. Đo kích thước BSON trong `mongosh`

MongoDB cung cấp toán tử aggregation `$bsonSize` để tính số byte của một giá trị object khi mã hóa thành BSON. Ví dụ với collection `customers` ở trên:

```javascript
db.customers.aggregate([
  {
    $project: {
      _id: 1,
      bsonBytes: { $bsonSize: "$$ROOT" }
    }
  },
  { $sort: { bsonBytes: -1 } },
  { $limit: 10 }
]);
```

`$$ROOT` đại diện cho document hiện tại của pipeline. Kết quả cho biết kích thước BSON của từng document được xét, giúp phát hiện những đối tượng đang tăng lên bất thường. Với collection rất lớn, việc tính kích thước rồi sắp xếp toàn bộ có thể tốn tài nguyên; nên chạy trên môi trường/khung giờ thích hợp hoặc thu hẹp tập dữ liệu trước.

Có thể xem kích thước lớn nhất trong một nhóm khách hàng cụ thể:

```javascript
db.customers.aggregate([
  { $match: { accountTier: "ENTERPRISE" } },
  { $project: { documentBytes: { $bsonSize: "$$ROOT" } } },
  { $group: {
      _id: null,
      maxBytes: { $max: "$documentBytes" },
      avgBytes: { $avg: "$documentBytes" },
      count: { $sum: 1 }
  } }
]);
```

Các biểu thức này chỉ minh họa cách đo; ví dụ thứ hai giả định collection có trường `accountTier`. Cần lọc dữ liệu đúng theo schema thực tế.

Một cách đặt ngưỡng cảnh báo mang tính minh họa:

```javascript
const maxDocumentBytes = 16 * 1024 * 1024;
const cautionThreshold = 12 * 1024 * 1024;

print({ maxDocumentBytes, cautionThreshold });
```

Mốc 12 MiB ở đây là **ngưỡng ứng dụng tự chọn**, không phải giới hạn do MongoDB quy định. Hệ thống có thể cần cảnh báo sớm hơn nếu document còn phải tăng nhanh, hoặc thiết kế lại hoàn toàn nếu mảng không có giới hạn. Tránh đợi đến lúc một bản ghi gần 16 MiB mới bắt đầu tách dữ liệu.

### 3.1. Kích thước document khác kích thước collection

Các chỉ số ở cấp collection như kích thước dữ liệu, số bản ghi và dung lượng trên đĩa cho biết bức tranh tổng quan. Chúng **không thay thế** việc kiểm tra kích thước từng document. Một collection 100 GiB có thể được tạo từ hàng triệu document nhỏ, hoặc chứa một số document bất thường gần 16 MiB. Hai trường hợp có cách tối ưu và rủi ro khác nhau.

Đừng dùng `JSON.stringify(document).length` để so với 16 MiB: phép đo đó thường trả số code unit của chuỗi JavaScript, không phản ánh chính xác BSON bytes hoặc kiểu BSON chuyên biệt.

## 4. Làm gì khi nội dung có thể vượt 16 MiB?

Câu trả lời phụ thuộc **bản chất dữ liệu**. Không có một chiến lược tách document áp dụng cho mọi nghiệp vụ.

### 4.1. Tách quan hệ một–nhiều không giới hạn thành collection riêng

Thay vì giữ toàn bộ lịch sử đơn hàng trong một document khách hàng:

```javascript
// customers
{
  _id: "C101",
  fullName: "Nguyễn An",
  lastOrderAt: ISODate("2026-10-01T10:00:00Z")
}

// orders: mỗi đơn là document độc lập
{
  _id: "O1001",
  customerId: "C101",
  createdAt: ISODate("2026-10-01T10:00:00Z"),
  total: NumberDecimal("245000")
}
```

Các đơn hàng có thể tăng không giới hạn mà không làm document khách hàng phình to. Index phù hợp sẽ hỗ trợ truy vấn lịch sử theo khách hàng:

```javascript
db.orders.createIndex({ customerId: 1, createdAt: -1 });

db.orders.find({ customerId: "C101" })
  .sort({ createdAt: -1 })
  .limit(20);
```

**Đánh đổi:** cần thêm truy vấn khi muốn lấy cả khách hàng và đơn hàng, có thể cần `$lookup` hoặc truy vấn riêng, và phải quản lý tính nhất quán khi cập nhật nhiều document. Đổi lại, mỗi thực thể có vòng đời riêng và khả năng tăng trưởng bền vững hơn.

### 4.2. Giữ mảng được giới hạn rõ ràng

Nếu chỉ cần lưu **10 lần truy cập gần nhất** hoặc **20 thông báo gần nhất**, có thể giữ một mảng giới hạn trong document:

```javascript
db.users.updateOne(
  { _id: "U1001" },
  {
    $push: {
      recentViews: {
        $each: [{ productId: "P42", viewedAt: new Date() }],
        $slice: -10
      }
    }
  }
);
```

`$slice: -10` giữ 10 phần tử cuối cùng sau thao tác push theo thứ tự của mảng. Đây chỉ là chiến lược phù hợp khi yêu cầu nghiệp vụ thực sự là *danh sách gần đây*. Nếu cần lịch sử đầy đủ để kiểm toán, các sự kiện lâu hơn phải được lưu ở nơi khác; việc cắt mảng không được làm mất thông tin bắt buộc lưu giữ.

### 4.3. Bucket theo thời gian hoặc kích thước

Một hệ thống thu thập phép đo có thể gom một số lượng mẫu hữu hạn theo thiết bị và khoảng thời gian:

```javascript
{
  deviceId: "SENSOR-01",
  bucketDate: ISODate("2026-11-14T00:00:00Z"),
  readings: [
    { at: ISODate("2026-11-14T00:00:00Z"), temperature: 26.1 },
    { at: ISODate("2026-11-14T00:01:00Z"), temperature: 26.2 }
  ]
}
```

Một bucket có thể đại diện cho một giờ, ngày hoặc một khoảng số lượng phần tử, tùy tốc độ ghi và kích thước mẫu. **Bucket vẫn là một document** nên vẫn phải nằm dưới 16 MiB. Cần thiết kế điểm đóng bucket và xử lý đồng thời thay vì chỉ đổi tên mảng vô hạn thành `bucket`.

MongoDB còn có **time series collection** chuyên cho một số workload đo đạc theo thời gian. Việc chọn bucket tự thiết kế hay time series collection cần dựa trên mẫu truy vấn, retention và khả năng cập nhật dữ liệu.

### 4.4. Dùng GridFS cho file lớn

**GridFS** là một cơ chế lưu và truy xuất file theo các phần (*chunks*) kèm metadata. Nó phù hợp khi ứng dụng cần quản lý những file vượt giới hạn document hoặc muốn dùng khả năng lưu file trong MongoDB. Một file lớn được chia thành nhiều document chunk, mỗi chunk phải hợp lệ theo giới hạn BSON; metadata về file được lưu riêng.

```text
File PDF 80 MiB
       |
       v
GridFS (thông qua driver/API)
       |
       +--> Thông tin file/metadata
       |
       +--> Chunk 0
       +--> Chunk 1
       +--> ...
       `--> Chunk N
```

GridFS **không nới giới hạn của một BSON document**; nó biểu diễn file bằng nhiều document. Không nên tự thiết kế một cơ chế chunk tùy tiện nếu GridFS đáp ứng yêu cầu. Tuy nhiên, nếu workload chủ yếu là phát video, phân phối ảnh công khai hoặc phục vụ file dung lượng rất lớn, object storage và CDN cũng là ứng viên cần so sánh về chi phí, throughput và cách phân phối nội dung.

### 4.5. Tách metadata và nội dung nặng

Ví dụ một bản ghi tài liệu:

```javascript
{
  _id: "DOC-401",
  title: "Quy trình vận hành",
  ownerId: "U12",
  fileId: ObjectId("66b000000000000000000401"),
  sizeBytes: 92000000,
  contentType: "application/pdf"
}
```

API có thể lọc, phân quyền và trả danh sách tài liệu mà không cần kéo theo toàn bộ file. `fileId` dẫn tới GridFS hoặc một kho tệp phù hợp. Khi cập nhật hoặc xóa, ứng dụng phải xử lý vòng đời và tính nhất quán giữa metadata với nội dung file.

## 5. Giới hạn độ lồng nhau: không quá 100 cấp

MongoDB cho phép document và array lồng nhau nhưng không vượt quá **100 cấp**. Mỗi object hoặc array lồng nhau tạo thêm một cấp trong cấu trúc BSON. Đây là giới hạn về **độ sâu**, hoàn toàn khác giới hạn **16 MiB về số byte**.

Một document chỉ vài kilobyte vẫn có thể bị từ chối nếu chứa chuỗi object/array quá sâu. Ngược lại, một document phẳng có một trường binary 20 MiB cũng không hợp lệ vì vượt kích thước, dù độ sâu rất nhỏ.

### 5.1. Độ sâu khác số lượng trường

```javascript
// Ít cấp: các trường là anh em cùng một object
{
  _id: 1,
  title: "MongoDB",
  author: "Team A",
  published: true,
  rating: 5
}

// Nhiều cấp: object nằm bên trong object
{
  _id: 2,
  a: {
    b: {
      c: {
        d: "value"
      }
    }
  }
}

// Mảng và object đều góp phần tăng độ sâu
{
  _id: 3,
  sections: [
    { title: "Phần 1", blocks: [ { type: "text", value: "Nội dung" } ] }
  ]
}
```

Ví dụ thứ ba không quá sâu, nhưng minh họa rằng mảng `sections`, object trong mảng, mảng `blocks` và object `block` đều nằm trên một đường lồng nhau. Độ sâu được xét theo đường đi lồng nhau sâu nhất, không phải cộng mọi object ở những nhánh khác nhau.

### 5.2. Ví dụ cấu trúc đệ quy dễ gặp giới hạn

Các trường hợp thực tế:

- Cây danh mục mà mỗi node chứa toàn bộ danh mục con và danh mục cháu.
- JSON từ parser tạo biểu thức lồng nhau hàng trăm cấp.
- Tài liệu chứa block con, bên trong có layout, group, block và group lặp lại.
- Dữ liệu biểu diễn một chuỗi công việc mà mỗi bước lại chứa toàn bộ bước kế tiếp.
- Object từ API ngoài được nhúng nguyên trạng mà không có giới hạn chiều sâu.

Một ví dụ tạo object có độ lồng nhau lớn để hình dung vấn đề:

```javascript
let value = { leaf: "end" };

for (let i = 0; i < 110; i++) {
  value = { child: value };
}

// Chỉ dùng để minh họa trường hợp vượt độ sâu;
// không đưa cấu trúc này vào schema MongoDB thực tế.
// db.nestedExamples.insertOne(value); // sẽ vượt giới hạn lồng nhau
```

Vì cấu trúc chứa nhiều lớp liên tiếp, việc lặp 110 lần đủ tạo ví dụ vượt giới hạn mà không cần có payload lớn. Đối với ứng dụng thực tế, nên kiểm tra độ sâu của dữ liệu không tin cậy trước khi chuyển nó sang driver hoặc lưu trữ; lỗi cũng có thể phát sinh từ bước encode BSON trong driver.

### 5.3. Thay cây lồng nhau bằng quan hệ giữa các node

Khi một cây phân cấp có thể sâu và phát triển vô hạn, cách lưu **mỗi node một document** thường dễ mở rộng hơn:

```javascript
// categories
{ _id: "CAT-A", name: "Thiết bị", parentId: null }
{ _id: "CAT-B", name: "Máy tính", parentId: "CAT-A" }
{ _id: "CAT-C", name: "Laptop", parentId: "CAT-B" }
```

Mô hình `parentId` không tăng độ sâu của một document khi cây sâu hơn. Đổi lại, việc truy vấn toàn bộ nhánh hoặc tổ tiên có thể cần nhiều lượt đọc hoặc aggregation như `$graphLookup`, và ứng dụng phải ngăn vòng lặp trong quan hệ cha–con.

Một số hệ thống lưu thêm đường dẫn tổ tiên (*materialized path*) hoặc mảng ancestor IDs để tối ưu truy vấn. Những giá trị đó cũng cần giới hạn và cách cập nhật khi chuyển nhánh. Không có mô hình duy nhất tốt cho mọi cây.

## 6. Vì sao nên tránh cấu trúc lồng nhau quá sâu ngay cả khi dưới 100 cấp?

Giới hạn 100 cấp là **mốc tối đa về khả năng lưu trữ**, không phải mục tiêu thiết kế schema. Trong nhiều ứng dụng, chỉ vài cấp được tổ chức có chủ đích đã đủ rõ ràng và dễ truy vấn.

Vấn đề thường xuất hiện trước khi chạm 100 cấp:

1. **Đường dẫn truy vấn dài và dễ nhầm:** trường như `project.layout.sections.blocks.items.settings.color` khó bảo trì khi schema thay đổi.
2. **Cập nhật từng nhánh phức tạp:** cập nhật phần tử sâu trong nhiều mảng có thể cần `$`, `$[]` hoặc `$[identifier]` với `arrayFilters`.
3. **Kiểm soát schema khó hơn:** ứng dụng phải xác thực kiểu dữ liệu và ràng buộc qua nhiều lớp object/array tùy chọn.
4. **Giới hạn document và cạnh tranh ghi:** việc chứa toàn bộ cây trong một document làm mọi thao tác cập nhật cây liên quan tới cùng đơn vị nguyên tử và giới hạn kích thước.
5. **Hiển thị/đọc dữ liệu tốn hơn:** API có thể chỉ cần một node nhưng phải nạp hoặc gửi một phần cây lớn nếu không thiết kế projection và đường truy cập phù hợp.
6. **Cấu trúc đệ quy dễ sinh lỗi ngoài database:** serializer, converter và logic duyệt cây trong ứng dụng cũng có thể gặp giới hạn stack hoặc vòng lặp tham chiếu.

Ví dụ cập nhật một trường lồng nhau vừa phải:

```javascript
db.profiles.updateOne(
  { _id: "U-12" },
  { $set: { "settings.notifications.email": false } }
);
```

Đây là trường hợp hợp lý nếu `settings.notifications.email` đại diện cho đường dẫn cố định có vài cấp. Nếu không biết tại thời điểm viết code một trường nằm ở cấp thứ 5 hay thứ 85, có thể cần xem lại ranh giới dữ liệu thay vì xây thêm chuỗi path động.

## 7. Quy tắc tên trường trong BSON document

Tên trường (*field name* hoặc *key*) là chuỗi dùng để định danh từng giá trị trong object. MongoDB không áp dụng cùng một bộ quy tắc tên cho **field**, **collection** và **database**. Khi đọc tài liệu giới hạn, phải xác định đúng đối tượng đang xét.

### 7.1. Những ràng buộc cơ bản

| Tên trường | Nhận xét |
| --- | --- |
| `firstName` | Thông dụng, rõ nghĩa, dễ truy vấn. |
| `shippingAddress` | Phù hợp để đặt object địa chỉ lồng nhau. |
| `created_at` | Hợp lệ; nên thống nhất một quy ước như camelCase hoặc snake_case. |
| `họTên` | Có thể biểu diễn bằng Unicode; cân nhắc chuẩn hóa tên key giữa các hệ thống. |
| `firstName` và `firstname` | Là hai tên khác nhau; không nên dựa vào khác biệt chữ hoa/thường một cách tùy tiện. |
| Tên chứa ký tự null `\u0000` | **Không hợp lệ**. |
| Hai field có cùng tên trong một document | **Không được lưu theo cách này**; BSON có thể biểu diễn dữ liệu gây trùng khóa từ một số builder nhưng CRUD không bảo đảm xử lý đúng. |
| `_id` | Tên riêng dành cho định danh chính; có các quy tắc bổ sung. |

Ví dụ document không bị trùng tên trường:

```javascript
{
  _id: "P10",
  productName: "Bàn phím cơ",
  priceMinor: NumberLong(890000),
  stock: {
    available: NumberInt(5),
    reserved: NumberInt(2)
  }
}
```

Tên field nên mang ý nghĩa ổn định. Không nên đặt tên theo nhãn giao diện có thể được dịch hoặc theo dữ liệu người dùng nhập trực tiếp. Ví dụ, thay vì dùng `"màu sản phẩm"` làm key được nhiều service xử lý, một tên kỹ thuật thống nhất như `color` và dữ liệu hiển thị riêng có thể dễ bảo trì hơn.

### 7.2. Ký tự null khác chuỗi `"null"`

Ký tự null là byte/character `\u0000`, không phải bốn chữ cái `n`, `u`, `l`, `l`. Tên trường `"nullable"` hoặc `"null"` không chứa ký tự null chỉ vì trông giống từ khóa.

```javascript
const validKey = "null";   // chỉ là chuỗi chữ bình thường
const invalidKey = "a\u0000b"; // chứa ký tự null
```

Việc đặt key bằng cách nối trực tiếp chuỗi từ nguồn không tin cậy có thể vô tình tạo tên trường không hợp lệ hoặc khó truy vấn. Hãy xác thực và ánh xạ key đầu vào trước khi xây document BSON.

## 8. Dấu chấm (`.`): tên literal và đường dẫn lồng nhau khác nhau

Trong truy vấn MongoDB, dấu chấm thường biểu diễn **đường dẫn tới trường lồng nhau**:

```javascript
{
  _id: 1,
  address: {
    city: "Đà Nẵng"
  }
}

// Truy vấn theo đường dẫn: address -> city
db.customers.find({ "address.city": "Đà Nẵng" });
```

Nhưng MongoDB từ 5.0 đã cải thiện hỗ trợ lưu **tên field chứa dấu chấm literal**. Điều đó tạo ra trường hợp dễ nhầm:

```javascript
{
  _id: 2,
  "address.city": "Hà Nội", // một tên field ở mức gốc
  address: { city: "Đà Nẵng" } // một field lồng nhau khác
}
```

`"address.city"` ở mức gốc và `address.city` theo đường dẫn là **hai dữ liệu khác nhau**, dù cú pháp truy vấn theo path thông thường trông giống nhau. Nếu dùng sai toán tử, có thể đọc hoặc cập nhật nhầm field.

### 8.1. Dùng `$getField` để đọc tên chứa dấu chấm literal

Ví dụ với collection dành riêng cho việc thử nghiệm:

```javascript
db.fieldNameExamples.insertOne({
  _id: 1,
  "metrics.cpu": 91,
  metrics: { cpu: 62 }
});

db.fieldNameExamples.aggregate([
  {
    $project: {
      _id: 0,
      literalKeyValue: { $getField: "metrics.cpu" },
      nestedPathValue: "$metrics.cpu"
    }
  }
]);
```

Kết quả kỳ vọng:

```javascript
{
  literalKeyValue: 91,
  nestedPathValue: 62
}
```

`$getField: "metrics.cpu"` tìm đúng key literal chứa dấu chấm. Biểu thức `"$metrics.cpu"` đi theo đường dẫn lồng nhau `metrics` → `cpu`. Đây là khác biệt quan trọng khi ứng dụng nhận dữ liệu có key từ đối tác hoặc hệ thống ngoài.

### 8.2. Dùng `$setField` để sửa tên literal

Nếu muốn cập nhật **key literal** `"metrics.cpu"`, không nên viết `$set: { "metrics.cpu": 95 }`, bởi cách viết đó được hiểu là cập nhật object `metrics` ở đường dẫn `cpu`. Dùng `$setField` trong update pipeline:

```javascript
db.fieldNameExamples.updateOne(
  { _id: 1 },
  [
    {
      $replaceWith: {
        $setField: {
          field: "metrics.cpu",
          input: "$$ROOT",
          value: 95
        }
      }
    }
  ]
);
```

Sau lệnh, key literal `"metrics.cpu"` trở thành `95`; field lồng nhau `metrics.cpu` vẫn giữ giá trị `62`. Các toán tử này được bổ sung từ MongoDB 5.0; ứng dụng chạy bản cũ hơn cần xem giới hạn tương thích của phiên bản.

### 8.3. Tại sao vẫn nên tránh dấu chấm trong tên trường?

MongoDB lưu được field dạng này nhưng tài liệu chính thức không khuyến khích vì một số khả năng bị hạn chế. Những tên có dấu `.` có thể không được index như field bình thường, không dùng làm shard key hoặc trực tiếp dùng `$jsonSchema` như các field thông thường, và dễ bị CSV import/export hiểu nhầm là đường dẫn lồng nhau.

Nếu ứng dụng tự kiểm soát schema, cách dễ bảo trì hơn là:

```javascript
// Khuyến nghị: object lồng nhau có key đơn giản
{
  metrics: {
    cpu: 91,
    memory: 80
  }
}

// Hoặc ánh xạ tên metadata từ ngoài vào một key an toàn
{
  attributes: [
    { originalName: "metrics.cpu", value: 91 }
  ]
}
```

Cách lưu theo mảng `attributes` có chi phí truy vấn và index khác với object trực tiếp; chỉ áp dụng khi thực sự cần giữ nguyên tên đầu vào không ổn định hoặc có ký tự đặc biệt.

## 9. Ký hiệu đô la (`$`): field name và toán tử MongoDB

MongoDB sử dụng `$` trong cú pháp truy vấn, aggregation và update:

```javascript
db.products.find({ price: { $gte: 100000 } });

db.products.updateOne(
  { _id: "P10" },
  { $set: { active: true } }
);
```

`$gte` và `$set` là **toán tử**, không phải tên field do ứng dụng lưu. Trong những phiên bản MongoDB hiện đại, server có thể lưu một field có tên bắt đầu bằng `$`, nhưng cách biểu diễn này khó xử lý và có những hạn chế tương tự field chứa dấu chấm.

Ví dụ document có field literal `"$price"`:

```javascript
db.specialFieldExamples.insertOne({
  _id: 1,
  "$price": 450000,
  productName: "Balo"
});
```

Khi đọc, dùng `$getField` kèm `$literal` để biểu thức không diễn giải chuỗi bắt đầu bằng `$` thành đường dẫn:

```javascript
db.specialFieldExamples.aggregate([
  {
    $project: {
      _id: 0,
      priceValue: {
        $getField: { field: { $literal: "$price" }, input: "$$ROOT" }
      }
    }
  }
]);
```

Thực tế nên chọn `price` thay vì `"$price"` khi có quyền thiết kế đầu vào. Field ở mức gốc bắt đầu bằng `$` còn có nguy cơ trùng tên metadata nội bộ mà MongoDB dành riêng, dẫn đến dữ liệu không được bảo toàn hoặc truy vấn như mong đợi trong một số ngữ cảnh.

## 10. Giới hạn bổ sung với dấu `.` và `$`

Các phiên bản MongoDB từ 5.0 hỗ trợ việc lưu key có dấu `.` hoặc bắt đầu bằng `$` tốt hơn trước, nhưng vẫn phải hiểu rõ các hạn chế. Theo tài liệu MongoDB, các field kiểu này không dùng được trong một số khả năng quan trọng:

| Khả năng | Ràng buộc đối với field có `.` hoặc tiền tố `$` |
| --- | --- |
| Index thông thường | Không thể lập index cho chính những field đặc biệt này theo cách hỗ trợ field thường. |
| Shard key | Không thể dùng chúng làm thành phần shard key. |
| Validation `$jsonSchema` | Không thể áp dụng trực tiếp validation bằng `$jsonSchema` cho những field đó. |
| Field Level Encryption | Không được dùng theo cơ chế này. |
| Subfield trong `_id` dạng object | Không được dùng làm subfield của `_id`. |
| Công cụ import/export | Có thể bị hiểu sai hoặc không bảo toàn đầy đủ trong một số dạng dữ liệu, đặc biệt CSV và Extended JSON. |
| Nhiều phần phân tách bằng dấu chấm | Số thành phần (*words*) phân tách bởi dấu chấm không được vượt mức giới hạn của MongoDB (tối đa 255). |

Giới hạn 255 **liên quan tới số phần tên phân tách bởi dấu chấm**, không nên nhầm thành quy tắc chung rằng mọi field name chỉ được dài tối đa 255 ký tự. Dù có giới hạn kỹ thuật, không nên cố đặt tên key gồm hàng trăm thành phần hoặc tạo path quá dài khó bảo trì.

### 10.1. Rủi ro với driver và server khác phiên bản

Một driver tương thích MongoDB 5.0 có thể chấp nhận tên field chứa dấu `.` hoặc bắt đầu bằng `$` mà driver cũ từng từ chối phía client. Nếu ứng dụng đó kết nối tới **server trước MongoDB 5.0**, thao tác ghi có thể bị server từ chối. Đặc biệt, khi dùng ghi không yêu cầu xác nhận (`w: 0`), có nguy cơ ứng dụng không biết dữ liệu bị từ chối.

Vì thế, khi nâng cấp driver hoặc tiếp nhận nguồn dữ liệu mới, cần kiểm tra **phiên bản server, driver và cấu hình write concern thực tế**, không giả định rằng nếu driver encode BSON được thì server chắc chắn lưu dữ liệu.

### 10.2. Rủi ro khi import/export

- **CSV** thường dùng dấu chấm để biểu diễn path lồng nhau; một key literal `"address.city"` có thể bị diễn giải là object `address` có field `city`.
- **Extended JSON v2** dùng những key đặc biệt như `$date` hoặc `$numberLong` cho biểu diễn kiểu BSON. Trường dữ liệu do ứng dụng đặt cùng tên có thể gây mơ hồ trong một số đường import/export.
- Không nên dùng một file JSON xuất ra rồi nhập lại để khẳng định kiểu dữ liệu và field đặc biệt luôn được bảo toàn. Cần kiểm thử round-trip bằng chính công cụ, định dạng và phiên bản sẽ dùng trong vận hành.

Giải pháp đơn giản nhất vẫn là đặt tên field ổn định, tránh `.`/`$` khi có thể, và chỉ dùng những tính năng đặc biệt này khi có lý do rõ ràng.

## 11. Trường `_id`: định danh chính có quy tắc riêng

Mỗi document trong collection MongoDB có trường `_id` đóng vai trò định danh chính. Nếu ứng dụng không cung cấp, driver hoặc MongoDB thường tạo giá trị `_id` thích hợp theo cơ chế đang sử dụng. Giá trị `_id` phải **duy nhất trong collection**, không được thay đổi sau khi tạo, và có những giới hạn kiểu dữ liệu; cụ thể không dùng array hoặc regular expression làm giá trị `_id`.

```javascript
{
  _id: ObjectId("66c000000000000000000401"),
  orderCode: "O2026-401",
  status: "NEW"
}
```

`_id` có thể là string hoặc một object hợp lệ khi thật sự cần định danh ghép, nhưng nên chọn cấu trúc dễ truy vấn và ổn định:

```javascript
{
  _id: { tenantId: "TENANT-01", externalId: "EXT-9001" },
  status: "ACTIVE"
}
```

Nếu `_id` là object, **không đặt subfield bắt đầu bằng `$`**; các giới hạn về dấu `.` trong field đặc biệt cũng cần được tính tới. Không nên xem `_id` là nơi nhét một bản ghi metadata lớn vì nó là định danh, không phải nội dung chi tiết của đối tượng.

Chỉ số unique dành cho `_id` không đảm bảo tự động tính duy nhất của những field nghiệp vụ khác như `email`, `orderCode` hoặc `(tenantId, externalId)` khi nằm ngoài `_id`. Các ràng buộc đó cần unique index phù hợp, đồng thời phải xét thêm quy tắc của sharded collection nếu có phân mảnh.

## 12. Vì sao duplicate field name là nguy hiểm?

BSON ở cấp định dạng có thể được một số thư viện xây dựng theo cách tạo ra nhiều phần tử mang **cùng tên field** trong một document. Tuy nhiên, MongoDB không hỗ trợ hoạt động CRUD đáng tin cậy trên document có field trùng tên, kể cả khi thao tác insert đôi lúc có vẻ thành công.

Hình dung dữ liệu như sau:

```text
// Ví dụ minh họa tình huống KHÔNG HỢP LỆ về thiết kế:
{ "status": "PENDING", "status": "PAID" }
```

Với JSON được parse bằng nhiều thư viện thông thường, một trong hai giá trị có thể bị ghi đè ngay trước khi dữ liệu đến MongoDB; các hệ thống khác lại có thể giữ cả hai key trong biểu diễn riêng. Sự khác biệt này dẫn đến việc dữ liệu thay đổi ngoài ý muốn trong quá trình serialize, import hoặc truy vấn.

Các nguyên tắc phòng tránh:

1. Không xây BSON document bằng cách ghép trực tiếp tên trường từ dữ liệu người dùng nếu chưa kiểm tra trùng lặp.
2. Phân biệt tên trường sau chuẩn hóa, ví dụ `productCode` và `ProductCode`, theo contract rõ ràng của ứng dụng.
3. Khi nhận JSON từ đối tác, dùng parser hoặc bước validation có thể phát hiện duplicate key nếu yêu cầu tính đúng đắn dữ liệu đòi hỏi.
4. Không dùng field trùng tên như một cách biểu diễn danh sách; hãy dùng mảng hoặc collection con.
5. Với dữ liệu đã tồn tại, cần đánh giá cơ chế đọc/sửa riêng thay vì dựa vào truy vấn thông thường để “tự chọn” một giá trị.

## 13. Tên trường động: lưu dữ liệu từ bên ngoài thế nào?

Giả sử một API nhận metadata do đối tác định nghĩa:

```json
{
  "manufacturer.code": "A-01",
  "$campaign": "summer",
  "label vi": "Sản phẩm nổi bật"
}
```

Nếu copy mọi key vào document MongoDB ở mức gốc, ứng dụng phải đối mặt với tên có dấu chấm, tiền tố `$`, key thay đổi thường xuyên và khả năng đụng trường nội bộ. Một cách tiếp cận là chuyển sang mô hình key–value tách biệt:

```javascript
{
  _id: "P-100",
  name: "Áo khoác",
  externalMetadata: [
    { key: "manufacturer.code", value: "A-01" },
    { key: "$campaign", value: "summer" },
    { key: "label vi", value: "Sản phẩm nổi bật" }
  ]
}
```

Tên bên ngoài hiện là **giá trị string của field `key`**, không phải tên BSON field có ký tự đặc biệt. Từ đó có thể áp dụng quy tắc độ dài, danh sách key được phép, số lượng phần tử tối đa và cách tìm kiếm dữ liệu tùy nghiệp vụ.

Nếu metadata rất lớn hoặc cập nhật độc lập, có thể tách mỗi nhóm metadata thành document khác với khóa tham chiếu `productId`. Mô hình mảng key–value giúp bảo toàn tên gốc, nhưng có chi phí index/query và nguy cơ mảng tăng lớn; không mặc định dùng nó cho mọi hệ thống. Trường hợp có tập field cố định, **object với tên field đơn giản** thường tiện hơn.

### 13.1. Quy ước tên trường thường nên thống nhất

Một quy ước phổ biến với ứng dụng Java/Spring và JSON API là dùng camelCase:

```javascript
{
  _id: "PRODUCT-01",
  productName: "Máy tính bảng",
  categoryId: "TABLET",
  createdAt: ISODate("2026-11-14T02:00:00Z"),
  price: { amountMinor: NumberLong(4500000), currency: "VND" },
  attributes: { screenSizeInches: 11, storageGb: 128 }
}
```

Điều có ý nghĩa không phải camelCase luôn tốt hơn snake_case, mà là **quy ước nhất quán giữa model, serializer, query, index và API**. Tránh dùng nhãn dịch tiếng Việt/tiếng Anh làm key nếu ứng dụng cần một schema độc lập ngôn ngữ. Tên field mô tả ý nghĩa nghiệp vụ và đơn vị đo sẽ giúp giảm nhầm lẫn, ví dụ `priceMinor` thay cho `price` khi cần biểu thị số tiền theo đơn vị nhỏ nhất.

## 14. Độ sâu, số byte và tên trường tác động lẫn nhau

Ba nhóm giới hạn không tách biệt trong thực tế. Một document có thể vi phạm một giới hạn ngay khi hai giới hạn còn lại chưa bị chạm.

| Ví dụ thiết kế | Kích thước | Độ sâu | Vấn đề chính |
| --- | --- | --- | --- |
| Một trường `fileData` chứa binary 25 MiB | Vượt 16 MiB. | Có thể rất nông. | Cần GridFS hoặc kho file phù hợp. |
| Object có 110 lớp `child` nối tiếp | Có thể chỉ vài KiB. | Vượt 100 cấp. | Cần thay đổi mô hình đệ quy. |
| Metadata có key `"source.version"` | Có thể rất nhỏ. | Chỉ một cấp. | Nhầm literal key với dotted path; hạn chế về index/query. |
| Một triệu phần tử nhỏ trong `events` | Có thể vượt 16 MiB và làm cập nhật tốn kém. | Có thể chỉ vài cấp. | Cần lưu event thành document riêng hoặc bucket có giới hạn. |
| Tên field cực dài lặp trong nhiều object con | Tăng BSON overhead. | Có thể vẫn dưới 100. | Kích thước tăng và schema khó bảo trì. |
| Trường `_id` chứa subfield bắt đầu bằng `$` | Có thể rất nhỏ. | Có thể ít cấp. | Vi phạm quy tắc đặt tên riêng của `_id`. |

Một giải pháp có thể xử lý nhiều vấn đề cùng lúc. Ví dụ, chuyển cây lớn từ một document sang collection `nodes` có `parentId` vừa giảm nguy cơ vượt độ sâu, vừa giới hạn kích thước từng document và giúp cập nhật từng node độc lập. Ngược lại, thao tác này khiến truy vấn cây đòi hỏi join/traversal và cần kiểm soát tính nhất quán của quan hệ.

## 15. Xử lý lỗi và giới hạn ở tầng ứng dụng

Không nên trông chờ database từ chối dữ liệu rồi mới thiết kế lại. Với API hoặc service nhận BSON/JSON từ người dùng, có thể đặt các giới hạn nghiệp vụ **chặt hơn** giới hạn của MongoDB:

```text
API upload tài liệu:
  - File vượt ngưỡng -> đưa sang object storage/GridFS theo thiết kế
  - Metadata -> document MongoDB có schema và field cố định

API ghi sự kiện:
  - Một sự kiện -> một document
  - Không tích lũy vô hạn vào user.events[]

API nhận biểu thức/cây:
  - Giới hạn độ sâu đầu vào theo nghiệp vụ (ví dụ 20 cấp)
  - Giới hạn tổng node và kích thước payload
  - Loại bỏ hoặc ánh xạ field name không được hỗ trợ
```

Con số “20 cấp” chỉ là ví dụ giới hạn của ứng dụng, không phải quy định MongoDB. Một biểu thức chỉ cần 6 cấp có thể hợp lý với ngưỡng 20; hệ thống chuyên xử lý cây phức tạp có thể cần một giới hạn khác. Giá trị phải xuất phát từ contract của API và thử nghiệm tải thực tế.

### 15.1. Kiểm soát kích thước trước khi cập nhật

Khi mảng được phép tăng nhưng có giới hạn, có thể áp dụng các phương án:

- **Giới hạn số phần tử:** dùng `$slice` hoặc tách sang collection nếu lịch sử phải giữ đầy đủ.
- **Giới hạn dung lượng payload:** validate dữ liệu được phép nhận; kiểm soát kích thước BSON bằng công cụ/driver phù hợp.
- **Giới hạn độ sâu:** validator tại ingress/mapper để tránh cấu trúc đệ quy quá lớn.
- **Giới hạn tên trường:** validate null, key bất thường, độ dài và reserved fields theo quy ước nội bộ.
- **Quan sát kích thước thực tế:** dùng `$bsonSize` hoặc phép đo BSON ở tầng ứng dụng cho những collection có rủi ro tăng trưởng.

Giới hạn request HTTP không thể thay thế giới hạn BSON: cùng một nội dung có thể có kích thước khác nhau khi serialize sang JSON và BSON. Ngoài ra, request nhỏ có thể kích hoạt cập nhật làm document hiện hữu tăng vượt ngưỡng, ví dụ `$push` thêm một phần tử vào mảng đã gần 16 MiB.

### 15.2. Phân biệt lỗi encode và lỗi ghi trên server

Một cấu trúc không hợp lệ có thể bị từ chối ở nhiều giai đoạn:

1. **Tầng ứng dụng/validation:** vi phạm quy tắc nghiệp vụ, giới hạn payload hoặc tên trường.
2. **Driver/BSON serializer:** không thể mã hóa kiểu dữ liệu hoặc cấu trúc theo quy tắc của driver.
3. **MongoDB server:** từ chối document lớn hơn giới hạn hoặc dữ liệu vi phạm quy tắc của server.
4. **Schema/index constraint:** có thể từ chối do validator hoặc unique index dù document nhỏ và tên trường hợp lệ.

Thông báo lỗi cụ thể tùy ngôn ngữ driver, phiên bản và thao tác. Khi xử lý lỗi, cần ghi nhận loại lỗi có cấu trúc và ngữ cảnh nghiệp vụ cần thiết; tránh ghi toàn bộ payload nhạy cảm chỉ để điều tra.

Đối với một lỗi do **document vượt giới hạn**, không nên retry vô hạn với đúng dữ liệu đó: lần ghi sau vẫn không thay đổi kích thước. Phải giảm dữ liệu theo đúng chính sách hoặc thay đổi mô hình lưu trữ. Với lỗi do cấu trúc quá sâu, việc gửi lại cùng cây không thể sửa ràng buộc độ sâu.

## 16. Bốn tình huống cần quyết định cách mô hình hóa

### Tình huống A — Bài viết có hàng trăm ảnh đính kèm

**Yêu cầu:** lấy tiêu đề/nội dung bài viết, hiển thị danh sách ảnh, tải từng ảnh riêng; ảnh có thể nặng hàng chục MB.

**Thiết kế:** giữ metadata và các tham chiếu tài nguyên trong document bài viết; nội dung ảnh lưu ở GridFS hoặc object storage. Nếu số lượng ảnh tăng vô hạn, cần cân nhắc collection `attachments` riêng thay vì nhúng tất cả metadata vào một mảng quá lớn.

**Đánh đổi:** quản lý xóa/sửa giữa metadata và file phức tạp hơn, nhưng tránh vượt giới hạn 16 MiB và không buộc API đọc bài viết phải chuyển dữ liệu binary nặng.

### Tình huống B — Danh mục nhiều tầng

**Yêu cầu:** category có thể có category con, mỗi node có metadata độc lập; số cấp do người dùng tạo ra.

**Thiết kế:** các node riêng chứa `parentId`, thêm index trên `parentId`; dùng traversal hoặc materialized path cho câu truy vấn phổ biến. Validation ngăn cycle và giới hạn chiều sâu nếu nghiệp vụ cần.

**Đánh đổi:** lấy một nhánh có thể cần nhiều thao tác; bù lại một cây tăng thêm 1.000 node không ép tất cả nội dung vào một document sâu hoặc khổng lồ.

### Tình huống C — Dữ liệu metadata của đối tác có key `a.b` và `$code`

**Yêu cầu:** bảo toàn tên trường do đối tác cung cấp, nhưng vẫn phải truy vấn theo một số thuộc tính chung.

**Thiết kế:** ánh xạ các thuộc tính quan trọng sang field riêng có tên an toàn; giữ key gốc trong giá trị `key`/`value` hoặc trong blob metadata có quy trình chuyển đổi được kiểm soát. Nếu buộc lưu key literal đặc biệt, dùng `$getField`/`$setField` và chấp nhận hạn chế index/shard key.

**Đánh đổi:** cần bước mapping/validation, đổi lại các truy vấn cốt lõi rõ ràng và ít rủi ro khi import/export.

### Tình huống D — Hồ sơ người dùng có lịch sử hành động nhiều năm

**Yêu cầu:** truy vấn 20 sự kiện gần nhất và đôi khi phục hồi tất cả lịch sử theo khoảng thời gian.

**Thiết kế:** mỗi sự kiện là document trong `userEvents`, có `userId` và `occurredAt`, index theo nhu cầu đọc; có thể giữ cache/bản tóm tắt ngắn trong profile nếu cần nhưng không coi bản tóm tắt là lịch sử đầy đủ.

**Đánh đổi:** cần thêm collection/index, nhưng quản lý retention và truy vấn sự kiện độc lập dễ hơn; profile không tăng mãi đến 16 MiB.

## 17. Quy trình quyết định trước khi chốt schema

Đối với mỗi collection mới, hãy trả lời lần lượt:

1. **Đối tượng chính là gì?** Một document có tương ứng với một thực thể/aggregate có vòng đời rõ ràng không?
2. **Các trường nào có thể tăng vô hạn?** Danh sách lịch sử, comments, files, event hoặc cây con có được đặt giới hạn không?
3. **Kích thước BSON thực tế là bao nhiêu?** Đo bằng `$bsonSize` hoặc encoder BSON thích hợp, tính cả metadata và index liên quan.
4. **Độ sâu dữ liệu đến từ đâu?** Nếu data đầu vào có tính đệ quy, ai chịu trách nhiệm giới hạn độ sâu trước khi ghi?
5. **Tên trường do ai kiểm soát?** Do đội phát triển định nghĩa hay do người dùng/đối tác nhập động? Nếu là từ bên ngoài, có validation và mapping không?
6. **Có field đặc biệt `.`/`$` không?** Nếu có, phải chấp nhận hạn chế query, index, shard key, validator, import/export và khả năng tương thích phiên bản.
7. **Quy tắc của `_id` có phù hợp không?** Định danh duy nhất, bất biến, kiểu dữ liệu và cấu trúc rõ ràng.
8. **Cần đọc/ghi gì cùng nhau?** Embed chỉ khi dữ liệu có vòng đời và kích thước phù hợp; reference khi dữ liệu phát triển độc lập.
9. **Giới hạn lỗi được xử lý ra sao?** Khi gần ngưỡng, ứng dụng sẽ từ chối, tách dữ liệu, chuyển file sang kho khác hay áp dụng chính sách retention nào?
10. **Đã thử trường hợp cực trị chưa?** Thử dữ liệu Unicode, mảng lớn, nhiều object con, tên lạ, document gần ngưỡng và thao tác ghi đồng thời.

Một bản thiết kế tốt không chỉ lưu được dữ liệu mẫu hôm nay, mà còn có cách tăng trưởng khi số record, độ sâu và nguồn dữ liệu bên ngoài thay đổi.

## 18. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “MongoDB chỉ lưu tối đa 16 MB dữ liệu.” | **Mỗi document** bị giới hạn 16 MiB; collection/database có thể lớn hơn nhiều. |
| “File nén trên đĩa còn 8 MiB thì BSON 20 MiB cũng lưu được.” | Giới hạn áp dụng cho biểu diễn BSON document, không dựa vào dung lượng trang sau nén. |
| “Tăng RAM sẽ giải quyết lỗi document too large.” | RAM và cache không nới kích thước document. |
| “Có 100 field thì hết giới hạn 100 cấp.” | Số field ngang hàng khác độ sâu lồng nhau; object/array lồng nhau mới làm tăng cấp. |
| “Chỉ object mới tính độ lồng nhau, array không tính.” | Cả object và array đều làm tăng độ sâu khi lồng nhau. |
| “Từ MongoDB 5.0 không được có dấu `.` hoặc `$` trong field.” | MongoDB 5.0+ cho phép nhiều trường hợp lưu chúng nhưng có hạn chế rõ rệt. |
| “`"a.b"` luôn có nghĩa là key literal.” | Trong cú pháp path thông thường, `a.b` biểu diễn trường `b` bên trong `a`; cần `$getField`/`$setField` cho key literal. |
| “`$price` là field thường nên truy vấn như `price`.” | `$` có ý nghĩa cú pháp trong query/aggregation; phải xử lý field literal đúng cách. |
| “JSON parser chấp nhận trùng key thì MongoDB cũng xử lý đúng.” | Document có duplicate field names không được hỗ trợ đáng tin cậy cho CRUD. |
| “GridFS biến một document thành file hơn 16 MiB.” | GridFS chia file thành nhiều document chunk; từng document vẫn phải hợp lệ. |
| “Mọi dữ liệu con nên embed vào một document.” | Dữ liệu con tăng không giới hạn hoặc có vòng đời độc lập thường nên tách bằng reference. |
| “Dùng `JSON.stringify().length` là đủ để đo BSON.” | Kích thước JSON text khác BSON bytes; cần đo theo BSON. |

## 19. Tài liệu tham khảo chính thức

- [MongoDB — Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/): giới hạn kích thước BSON, độ sâu và các quy định field name.
- [MongoDB — Documents](https://www.mongodb.com/docs/manual/core/document/): cấu trúc document, `_id`, field names, BSON.
- [MongoDB — Field Names with Periods and Dollar Signs](https://www.mongodb.com/docs/manual/core/dot-dollar-considerations/): các hạn chế khi đặt tên chứa `.` và `$`.
- [MongoDB — `$getField`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/getfield/): đọc một field literal, kể cả key chứa dấu chấm hoặc tiền tố `$`.
- [MongoDB — `$setField`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/setfield/): cập nhật key literal có ký tự đặc biệt.
- [MongoDB — `$bsonSize`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/bsonsize/): tính kích thước một object ở dạng BSON.
- [MongoDB — GridFS](https://www.mongodb.com/docs/manual/core/gridfs/): lưu và truy xuất file dưới dạng các chunk.

Khi đọc tài liệu theo một phiên bản MongoDB cụ thể, hãy xác minh phiên bản **server** và **driver** đang sử dụng, đặc biệt với các tên trường có `.` hoặc `$`. Giới hạn 16 MiB, 100 cấp và những hạn chế về field name cần được chuyển thành **quy tắc thiết kế schema, validation đầu vào và chiến lược tăng trưởng**, thay vì chỉ ghi nhớ như ba con số kỹ thuật.

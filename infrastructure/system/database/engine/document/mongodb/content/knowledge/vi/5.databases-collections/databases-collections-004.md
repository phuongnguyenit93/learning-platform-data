# Collection thông thường và capped collection trong MongoDB

Trong MongoDB, **collection** là nơi chứa các document BSON. Cùng là collection, nhưng cách quản lý dữ liệu có thể rất khác nhau: một collection thông thường phù hợp với dữ liệu nghiệp vụ cần lưu, truy vấn và cập nhật theo vòng đời riêng; **capped collection** có dung lượng cấp phát giới hạn, hoạt động giống một vùng đệm tuần hoàn, tự ghi đè các document cũ nhất theo cơ chế loại bỏ khi đạt giới hạn.

Việc chọn sai loại collection dẫn đến những hệ quả thực tế: bản ghi có thể tự biến mất trong capped collection, thao tác xóa hoặc sửa kích thước document có thể bị từ chối, và ứng dụng đọc sự kiện có thể bỏ lỡ dữ liệu nếu tiêu thụ quá chậm. Ngược lại, khi cần một luồng log hoặc sự kiện ngắn hạn có giới hạn lưu trữ, cơ chế capped có thể hữu ích hơn việc tự xóa hàng loạt bản ghi sau mỗi lần ghi.

Bài học tập trung vào **collection thông thường và capped collection**: cơ chế lưu trữ, cách tạo và quản lý, giới hạn CRUD, thứ tự document, tailable cursor, tình huống sử dụng và cách thực hành bằng MongoDB Shell.

## 1. Collection là gì?

MongoDB tổ chức dữ liệu theo cấu trúc:

~~~text
MongoDB deployment
└── Database: shop
    ├── Collection: customers
    │   ├── Document {_id: ..., name: "An", ...}
    │   └── Document {_id: ..., name: "Bình", ...}
    ├── Collection: orders
    │   ├── Document {_id: ..., total: ..., ...}
    │   └── ...
    └── Collection: activityBuffer (capped)
        ├── Sự kiện mới hơn
        └── Sự kiện cũ hơn, sẽ bị loại khi đạt giới hạn
~~~

Trong cơ sở dữ liệu quan hệ, ta thường liên tưởng collection tới bảng và document tới hàng. Tuy nhiên, document MongoDB là BSON và có thể chứa object hoặc array lồng nhau; các document cùng collection không nhất thiết có bộ trường giống nhau, trừ khi ứng dụng hoặc database áp dụng schema validation.

Ví dụ hai document trong cùng collection:

~~~javascript
{
  _id: ObjectId("66f1c2a4b1d2e3f405162738"),
  name: "An",
  contact: { email: "an@example.test" }
}

{
  _id: ObjectId("66f1c2a4b1d2e3f405162739"),
  name: "Bình",
  preferences: ["email", "sms"]
}
~~~

Collection cũng có thể có **index**, quy tắc validation, cấu hình collation và những thuộc tính khác. Loại collection quyết định một số giới hạn quan trọng về cách ghi và loại bỏ document.

## 2. Hai loại collection giải quyết hai nhu cầu khác nhau

### 2.1. Collection thông thường

Đây là lựa chọn mặc định trong phần lớn ứng dụng MongoDB. Document tiếp tục tồn tại cho đến khi có thao tác cập nhật, xóa, thay thế, drop collection, hoặc một cơ chế tự động đã được cấu hình rõ ràng, chẳng hạn TTL index.

Ví dụ, collection **orders** trong ứng dụng bán hàng:

~~~javascript
{
  _id: "ORD-1001",
  customerId: "C-001",
  total: 250000,
  status: "PENDING",
  items: [
    { sku: "BOOK-01", quantity: 2 }
  ]
}
~~~

Với loại collection này, ứng dụng có thể sửa trạng thái đơn hàng, thêm trường trackingCode, xóa đơn theo quyền hợp lệ, truy vấn bằng index, hoặc giữ lịch sử lâu dài. MongoDB **không tự xóa document cũ chỉ vì collection ngày càng lớn**.

### 2.2. Capped collection

Capped collection là collection có **giới hạn kích thước lưu trữ được chỉ định khi tạo**. Nó sử dụng cơ chế lưu trữ kiểu vòng tròn: document mới được ghi vào, và khi đạt giới hạn thì các document cũ nhất được loại tự động để dành chỗ cho dữ liệu mới.

Ví dụ, một vùng đệm giữ vài nghìn thông báo trạng thái gần nhất:

~~~javascript
{
  _id: 9001,
  time: ISODate("2026-11-14T03:00:00Z"),
  service: "checkout",
  level: "INFO",
  message: "Request accepted"
}
~~~

Sau một thời gian, hệ thống có thể còn các thông báo gần đây nhưng những thông báo cũ đã biến mất theo giới hạn lưu trữ. Đây là hành vi **được thiết kế sẵn** của capped collection, không phải lỗi mất dữ liệu của MongoDB.

Ví dụ tư duy:

~~~text
Capped collection: tối đa 4 document

Lúc đầu:       [A] [B] [C] [D]
Ghi thêm E:        [B] [C] [D] [E]    (A bị loại)
Ghi thêm F:            [C] [D] [E] [F]    (B bị loại)
~~~

Hình trên minh họa thứ tự logic; MongoDB quản lý file dữ liệu và không nhất thiết tổ chức byte thành một mảng đơn giản như sơ đồ.

## 3. Bảng so sánh tổng quan

| Tiêu chí | Collection thông thường | Capped collection |
|---|---|---|
| Cách tạo | Ngầm khi ghi lần đầu hoặc tạo bằng db.createCollection() | Phải chỉ rõ capped: true và size khi tạo |
| Mục tiêu chính | Lưu dữ liệu nghiệp vụ theo vòng đời tùy ý | Giữ vùng đệm dữ liệu có kích thước giới hạn |
| Giới hạn dung lượng | Không có giới hạn dung lượng cố định do loại collection áp đặt | Có giới hạn size tính bằng byte được cấu hình |
| Giới hạn số document | Không có giới hạn số lượng cố định do loại collection áp đặt | Có thể đặt max; vẫn phải tuân thủ giới hạn size |
| Khi thêm dữ liệu làm vượt giới hạn | Tiếp tục tăng dung lượng nếu hệ thống cho phép | Tự loại document cũ nhất để nhường chỗ |
| Xóa từng document | Có deleteOne(), deleteMany() | Không cho phép xóa document riêng lẻ theo cách thông thường |
| Cập nhật document | Có thể làm document tăng/giảm kích thước nếu thao tác hợp lệ | Không được cập nhật khiến kích thước document thay đổi theo giới hạn của capped |
| Thứ tự tự nhiên | Không phải thứ tự nghiệp vụ ổn định | Được tổ chức để giữ thứ tự chèn, hữu ích khi duyệt tuần tự |
| Tailable cursor | Không hỗ trợ | Hỗ trợ để đọc dữ liệu mới nối tiếp theo thứ tự tự nhiên |
| Index | Hỗ trợ | Hỗ trợ index, nhưng cần cân nhắc chi phí ghi và yêu cầu truy vấn |
| Sharding | Có thể sharding nếu thỏa điều kiện cấu hình | Không hỗ trợ sharding capped collection |
| TTL theo thời điểm | Có thể dùng TTL index khi phù hợp | Không phải lựa chọn để quản lý hạn lưu theo thời gian bằng TTL |
| Tình huống điển hình | Customer, order, product, account, audit dài hạn | Log ngắn hạn, sự kiện tạm thời, vòng đệm quan sát |

**Không có loại nào tốt hơn cho mọi tình huống.** Capped collection đánh đổi khả năng chỉnh sửa và giữ dữ liệu linh hoạt để có cơ chế giới hạn vòng đời tự động theo dung lượng/số lượng.

## 4. Tạo và thao tác với collection thông thường

Các ví dụ trong bài chạy trong **mongosh**. Bạn cần một MongoDB deployment có quyền tạo collection và ghi dữ liệu. Không cần dùng database production; hãy tạo database riêng:

~~~javascript
use collection_lab
~~~

Lệnh use chọn database làm việc trong shell. Database chỉ thực sự hình thành khi có dữ liệu hoặc metadata được tạo.

### 4.1. Tạo collection tường minh

~~~javascript
db.createCollection("customers")

db.customers.insertMany([
  {
    _id: "CUS-001",
    name: "An",
    status: "ACTIVE",
    tags: ["new"]
  },
  {
    _id: "CUS-002",
    name: "Bình",
    status: "ACTIVE",
    tags: []
  }
])
~~~

Khi tạo collection thông thường, không cần khai báo capped hay size. Cũng có thể để MongoDB **tự tạo collection khi insert lần đầu**:

~~~javascript
db.products.insertOne({
  sku: "PEN-01",
  name: "Bút",
  stock: 10
})
~~~

Nếu products chưa tồn tại, lần ghi đầu sẽ tạo một **collection thông thường**, không tự chuyển thành capped.

### 4.2. Các thao tác CRUD

~~~javascript
// Đọc dữ liệu
db.customers.find({ status: "ACTIVE" })

// Cập nhật, có thể thêm trường mới và thay đổi kích thước document
db.customers.updateOne(
  { _id: "CUS-001" },
  { $set: { phone: "0900000000", status: "VERIFIED" } }
)

// Thêm một phần tử vào array
db.customers.updateOne(
  { _id: "CUS-001" },
  { $push: { tags: "vip" } }
)

// Xóa một document theo điều kiện
db.customers.deleteOne({ _id: "CUS-002" })
~~~

Các thao tác trên thuộc vòng đời dữ liệu do ứng dụng điều khiển. Collection không tự loại document theo cơ chế vòng đệm.

### 4.3. Index và thứ tự kết quả

~~~javascript
db.customers.createIndex({ status: 1, name: 1 })

db.customers
  .find({ status: "VERIFIED" })
  .sort({ name: 1 })
~~~

**Không nên dựa vào thứ tự document mặc định của find().** Khi yêu cầu kết quả theo tên, ngày tạo, số thứ tự hay khóa nghiệp vụ, hãy chỉ định sort tường minh và thiết kế index phù hợp. Thứ tự vật lý/tự nhiên có thể thay đổi khi dữ liệu hoặc kế hoạch thực thi truy vấn thay đổi.

## 5. Tạo capped collection

Capped collection cần cấu hình ngay khi tạo:

~~~javascript
db.createCollection("eventBuffer", {
  capped: true,
  size: 1024 * 1024,
  max: 1000
})
~~~

Ý nghĩa:

- **capped: true**: yêu cầu MongoDB tạo capped collection.
- **size: 1024 * 1024**: đặt kích thước giới hạn là 1 MiB, tính theo byte trong ví dụ.
- **max: 1000**: đặt số document tối đa theo cấu hình, tính theo số lượng.

**size là bắt buộc** khi tạo capped collection, còn **max là tùy chọn**. Nếu chỉ đặt size thì việc loại bỏ document dựa vào dung lượng. Nếu đặt cả size và max, collection có thể loại document khi **một trong hai giới hạn đạt tới ngưỡng**; max không cho phép bỏ qua giới hạn size.

Lưu ý rằng size là giới hạn dành cho cơ chế lưu trữ của collection, không phải hạn mức chính xác cho toàn bộ dung lượng ổ đĩa của database. Các index, metadata, journal và những collection khác vẫn chiếm tài nguyên riêng.

### 5.1. Kiểm tra loại collection vừa tạo

~~~javascript
db.eventBuffer.isCapped()
~~~

Kết quả mong đợi là true. Xem metadata:

~~~javascript
db.getCollectionInfos({ name: "eventBuffer" })
~~~

Thông tin trả về có thể có phần options, nơi bạn quan sát các cấu hình capped, size, max đã lưu. Có thể xem thống kê collection:

~~~javascript
db.eventBuffer.stats()
~~~

Các trường thống kê và cách báo kích thước có thể khác nhau theo phiên bản MongoDB hoặc storage engine. Để biết collection có phải capped hay không, **isCapped()** là cách kiểm tra trực tiếp và dễ hiểu.

### 5.2. Lỡ ghi dữ liệu trước khi tạo capped?

Đây là lỗi thường gặp:

~~~javascript
db.events.insertOne({ message: "First event" })

db.createCollection("events", {
  capped: true,
  size: 1048576
})
~~~

Lệnh insert trước đó đã tạo **events** là collection thông thường. Việc gọi createCollection với cùng tên sẽ không tự nâng cấp lại collection và thường báo namespace đã tồn tại. Khi muốn capped collection, hãy tạo đúng cấu hình **trước lần ghi đầu tiên**, hoặc thực hiện kế hoạch chuyển đổi dữ liệu có chủ đích.

MongoDB có cơ chế **convertToCapped** để chuyển collection thông thường sang capped trong những tình huống được hỗ trợ. Việc chuyển đổi có thể loại các document cũ nếu vượt dung lượng mới, nên cần sao lưu, kiểm tra phiên bản/quyền và đánh giá tác động trước khi thực hiện. Đây không phải thao tác nên dùng để sửa nhanh nhầm lẫn trong production.

## 6. Thực hành vòng đời tự loại document

Để nhìn thấy hiệu ứng, tạo một collection capped **riêng cho bài thí nghiệm**, đặt max nhỏ. Các lệnh sau không dùng eventBuffer ở phần trước:

~~~javascript
db.createCollection("tinyEvents", {
  capped: true,
  size: 1024 * 1024,
  max: 4
})
~~~

Ở đây 1 MiB đủ cho vài document nhỏ trong ví dụ; **max: 4** sẽ dễ quan sát hơn giới hạn byte.

Ghi bốn sự kiện:

~~~javascript
db.tinyEvents.insertMany([
  { _id: 1, seq: 1, message: "Event A" },
  { _id: 2, seq: 2, message: "Event B" },
  { _id: 3, seq: 3, message: "Event C" },
  { _id: 4, seq: 4, message: "Event D" }
])

db.tinyEvents
  .find({}, { _id: 1, seq: 1, message: 1 })
  .sort({ $natural: 1 })
~~~

Khi chưa có luồng ghi khác, bốn document sẽ được duyệt theo thứ tự đã chèn. Tiếp tục:

~~~javascript
db.tinyEvents.insertMany([
  { _id: 5, seq: 5, message: "Event E" },
  { _id: 6, seq: 6, message: "Event F" }
])

db.tinyEvents
  .find({}, { _id: 1, seq: 1, message: 1 })
  .sort({ $natural: 1 })

db.tinyEvents.countDocuments({})
~~~

Trong môi trường thí nghiệm chỉ có một nguồn ghi, bạn sẽ thấy những document mới nhất (thông thường có seq 3, 4, 5, 6) và tổng số document là 4. Các document seq 1 và 2 đã bị loại tự động.

Đây là hiện tượng **rollover** của capped collection: viết thêm làm dữ liệu cũ nhất biến mất khi đạt giới hạn. Lệnh insertMany vẫn có thể báo ghi thành công cho tất cả document mới dù một số document cũ đã bị loại ngay trong quá trình ghi.

### 6.1. Giới hạn size và max hoạt động cùng nhau

Hãy tưởng tượng một collection:

~~~javascript
db.createCollection("recentMessages", {
  capped: true,
  size: 2 * 1024 * 1024,
  max: 500
})
~~~

Hai trường hợp:

1. Nếu mỗi document nhỏ, collection có thể đạt 500 document trước khi đạt dung lượng 2 MiB. Document cũ sẽ bị loại theo ngưỡng số lượng.
2. Nếu mỗi document lớn, collection có thể đạt ngưỡng dung lượng trước khi chứa đủ 500 document. Khi đó, số document thực tế được giữ có thể ít hơn 500.

Vì vậy, **max không có nghĩa là collection chắc chắn luôn giữ đủ max document cuối cùng**. Số bản ghi thực tế phụ thuộc kích thước document và giới hạn lưu trữ.

Nếu một document mới quá lớn so với giới hạn hoặc vi phạm điều kiện lưu trữ, thao tác ghi có thể thất bại. Capped collection không làm cho một document quá lớn trở nên hợp lệ.

### 6.2. Capped collection không bảo đảm giữ dữ liệu theo số ngày

Giả sử đặt size bằng 100 MiB cho log:

- Ngày bình thường, ứng dụng ghi ít; 100 MiB có thể giữ dữ liệu nhiều ngày.
- Ngày có sự cố, lượng log tăng đột biến; 100 MiB có thể chỉ giữ được vài giờ.

Điều này có nghĩa capped collection **không cung cấp cam kết giữ đúng 7 ngày** hoặc một khoảng thời gian cố định. Nếu yêu cầu của hệ thống là giữ record đến một hạn xác định, nên thiết kế vòng đời theo thời gian, ví dụ TTL index trên collection thông thường hoặc một cơ chế lưu trữ phù hợp.

Ngay cả TTL index cũng xóa bất đồng bộ qua TTL monitor, nên không dùng TTL để cam kết record biến mất chính xác tại từng mili giây.

## 7. Thứ tự chèn và $natural

Một đặc điểm quan trọng của capped collection là các document được lưu theo thứ tự chèn phục vụ việc duyệt tuần tự. MongoDB hỗ trợ sort bằng **$natural**:

~~~javascript
// Đọc theo thứ tự tự nhiên thuận
db.tinyEvents.find().sort({ $natural: 1 })

// Đọc theo thứ tự tự nhiên ngược
db.tinyEvents.find().sort({ $natural: -1 })
~~~

Trong capped collection, thứ tự tự nhiên thường tương ứng với thứ tự chèn. Điều đó hữu ích khi đọc một log ngắn hạn từ cũ đến mới hoặc từ mới về cũ mà không phải duy trì một trường thứ tự chỉ để quan sát.

Tuy nhiên, cần phân biệt:

- **Thứ tự chèn:** thứ tự MongoDB ghi các document vào collection.
- **Thời điểm sự kiện:** trường timestamp mà ứng dụng gắn vào record; đồng hồ các client khác nhau có thể lệch.
- **Thứ tự nghiệp vụ:** ví dụ orderNumber hoặc eventSequence do hệ thống xác định.

Ba thứ tự này **không nhất thiết trùng nhau** trong hệ thống có nhiều nguồn ghi, dữ liệu đến trễ hoặc xử lý đồng thời. Nếu nghiệp vụ đòi hỏi kết quả sắp xếp ổn định, hãy lưu trường thời gian và khóa thứ tự/khóa phụ phù hợp rồi sử dụng sort tường minh:

~~~javascript
db.eventBuffer.find().sort({
  producedAt: 1,
  eventId: 1
})
~~~

Trong collection thông thường, không nên xem $natural là một hợp đồng thứ tự nghiệp vụ. Việc truy vấn dùng index, cập nhật dữ liệu, bố trí lưu trữ hoặc thay đổi triển khai có thể khiến thứ tự quan sát khác dự kiến.

## 8. Khả năng CRUD và giới hạn riêng của capped collection

### 8.1. Insert

Capped collection nhận insert giống collection thông thường, miễn document hợp lệ và phù hợp giới hạn lưu trữ:

~~~javascript
db.eventBuffer.insertOne({
  level: "INFO",
  message: "Health check passed",
  producedAt: new Date()
})
~~~

Điểm khác biệt là việc insert mới có thể khiến document cũ nhất bị loại tự động. Vì vậy, thao tác ghi thành công **không bảo đảm document đó sẽ được lưu vô thời hạn**.

### 8.2. Update không được tùy ý làm thay đổi kích thước document

Với collection thông thường, bạn thường có thể thêm trường mới:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-001" },
  { $set: { notes: "Khách hàng thường xuyên" } }
)
~~~

Với capped collection, **MongoDB hạn chế cập nhật làm thay đổi kích thước document**, vì điều này không phù hợp cơ chế lưu trữ cố định của capped. Ví dụ cập nhật một message ngắn thành một chuỗi dài hơn hoặc thêm nhiều trường mới có thể thất bại.

Do đó, nên xem capped collection như một **dòng dữ liệu chủ yếu được ghi bổ sung và đọc**, thay vì nơi các record liên tục thay đổi nội dung hoặc kích thước.

Nếu một event cần được chỉnh sửa qua nhiều bước, thông thường nên đưa trạng thái hiện hành vào collection thông thường; capped collection, nếu dùng, chỉ giữ các bản tin phát sinh.

### 8.3. Delete riêng lẻ không được hỗ trợ

Trên collection thông thường:

~~~javascript
db.customers.deleteOne({ _id: "CUS-001" })
~~~

Trên capped collection, thao tác xóa theo từng document hoặc theo filter không được hỗ trợ theo cách thông thường:

~~~javascript
// Không dùng để xóa riêng một event trên capped collection
db.eventBuffer.deleteOne({ level: "INFO" })
~~~

Document trong capped collection biến mất theo **cơ chế tự loại khi ghi vượt giới hạn**, hoặc cả collection bị xóa bởi thao tác quản trị. Việc không cho phép xóa chọn lọc là một giới hạn thiết kế quan trọng.

### 8.4. Drop, truncate và tạo lại

Nếu muốn làm rỗng capped collection cho môi trường thực hành, có thể **drop rồi tạo lại** với cấu hình tương ứng:

~~~javascript
// Chỉ dùng với collection thử nghiệm không cần giữ dữ liệu.
db.tinyEvents.drop()

db.createCollection("tinyEvents", {
  capped: true,
  size: 1024 * 1024,
  max: 4
})
~~~

Lệnh drop xóa toàn bộ collection và index của nó. Đây là thao tác phá hủy dữ liệu, không phải một phép delete theo điều kiện.

Khi cần thay đổi size, max hoặc chuyển loại collection trong hệ thống thật, hãy chuẩn bị kế hoạch di chuyển, sao lưu, tác động tới client và thời gian gián đoạn. Không giả định mọi tùy chọn capped đều có thể cập nhật trực tiếp bằng lệnh sửa metadata thông thường.

### 8.5. Index vẫn tồn tại nhưng không thay đổi cơ chế rollover

Capped collection có thể tạo index để phục vụ truy vấn phù hợp:

~~~javascript
db.eventBuffer.createIndex({
  level: 1,
  producedAt: -1
})
~~~

Index giúp truy vấn theo field nhưng cũng có chi phí lưu trữ và duy trì khi ghi. Index **không giữ document khỏi bị loại** khi capped collection vượt giới hạn và không làm capped collection trở thành nơi lưu dữ liệu lịch sử dài hạn.

Nếu workload chỉ đọc tuần tự toàn bộ sự kiện mới qua tailable cursor, nhiều index phức tạp có thể không cần thiết. Nếu cần lọc nhiều chiều và giữ dữ liệu lâu dài, collection thông thường cùng index được thiết kế phù hợp có thể là lựa chọn tốt hơn.

## 9. Tailable cursor: đọc dữ liệu liên tục từ capped collection

**Cursor** trong MongoDB là cơ chế client duyệt kết quả truy vấn theo từng phần. Một cursor thông thường đi đến cuối tập kết quả rồi kết thúc.

**Tailable cursor** là một loại cursor đặc biệt dùng với capped collection: nó có thể tiếp tục chờ và nhận document mới được thêm vào sau khi đã đọc những document trước đó. Ý tưởng tương tự lệnh tail -f đối với một file log:

~~~text
Ứng dụng A ghi sự kiện
       |
       v
  [capped collection]
       |
       v
Ứng dụng B mở tailable cursor
       |
       +-- Đọc những event đang có
       +-- Đợi event mới
       +-- Đọc event mới
       +-- Tiếp tục khi cursor còn hợp lệ
~~~

Tailable cursor gắn chặt với **thứ tự tự nhiên** của capped collection. Nó không phải cursor có thể tùy ý sort theo bất kỳ index nào; nếu ứng dụng cần thứ tự nghiệp vụ khác, cần thiết kế lại luồng truy cập.

### 9.1. Ví dụ với MongoDB Java Sync Driver

Giả sử MongoDB đã có collection collection_lab.eventBuffer dạng capped và có sẵn ít nhất một document. Ứng dụng Java có dependency MongoDB Java Sync Driver có thể đọc theo dạng tailable:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.CursorType;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

public class TailableEventReader {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> events = client
                    .getDatabase("collection_lab")
                    .getCollection("eventBuffer");

            try (MongoCursor<Document> cursor = events.find()
                    .cursorType(CursorType.TailableAwait)
                    .maxAwaitTime(1, TimeUnit.SECONDS)
                    .iterator()) {

                while (cursor.hasNext()) {
                    Document event = cursor.next();
                    System.out.println(event.toJson());
                }
            }
        }
    }
}
~~~

**Cách hiểu ví dụ:**

1. MongoDB driver mở cursor theo chế độ **TailableAwait**.
2. Khi đã duyệt hết document hiện tại, server có thể chờ ngắn để trả document mới thay vì kết thúc ngay như truy vấn thường.
3. Client duyệt và xử lý document theo dòng dữ liệu được thêm vào capped collection.
4. Nếu cursor hết hiệu lực hoặc bị đóng, đoạn minh họa dừng. Hệ thống thật phải có logic khôi phục/restart đọc tùy yêu cầu của ứng dụng.

Một tailable cursor có thể mất hiệu lực nếu dữ liệu cũ bị rollover vượt qua vị trí đọc, nếu collection bị drop, hoặc nếu kết nối bị lỗi. Với collection trống, một số cách mở tailable cursor cũng có thể không chờ được như mong muốn. Đừng coi đây là cơ chế truyền thông bảo đảm mỗi sự kiện sẽ được xử lý đúng một lần.

### 9.2. Tailable cursor không phải message queue bền vững

Nếu consumer bị dừng lâu, capped collection có thể loại các sự kiện mà nó chưa đọc. Khi khởi động lại, dữ liệu đã bị xóa khỏi vùng đệm **không thể tự lấy lại** chỉ nhờ tailable cursor.

Tailable cursor cũng không tự cung cấp đầy đủ:

- Cơ chế acknowledgement cho từng message.
- Retry, dead-letter queue và điều phối nhiều nhóm consumer.
- Bảo đảm consumer chậm không mất dữ liệu.
- Cam kết exactly-once processing.

Nếu yêu cầu nghiệp vụ là xử lý thanh toán, công việc quan trọng hoặc phân phối message bền vững, cần một thiết kế hàng đợi/stream chuyên dụng hoặc một cơ chế lưu trạng thái tiêu thụ và phục hồi rõ ràng.

### 9.3. Phân biệt với MongoDB Change Streams

**Change Streams** cho phép theo dõi các thay đổi của dữ liệu MongoDB qua API riêng trong môi trường có hỗ trợ, điển hình là replica set hoặc sharded cluster. Change Streams không yêu cầu biến collection nghiệp vụ thành capped collection và cung cấp cơ chế resume token theo hợp đồng của Change Streams.

| Tình huống | Tailable cursor trên capped | Change Streams |
|---|---|---|
Nguồn dữ liệu | Đọc document mới từ một capped collection | Theo dõi các sự kiện thay đổi trên collection/database/deployment hỗ trợ |
| Điều kiện hạ tầng | Capped collection | Replica set hoặc sharded cluster có hỗ trợ |
| Nội dung quan sát | Các document trong collection | Các sự kiện thay đổi, với metadata và thông tin tùy cấu hình |
| Phục hồi | Cần tự thiết kế điểm đọc và chấp nhận dữ liệu có thể đã bị loại | Có resume token, chịu các giới hạn về lịch sử/oplog và thời gian còn dữ liệu |
| Nhu cầu phù hợp | Dòng log/buffer đơn giản, cho phép mất phần cũ | Quan sát insert/update/delete của dữ liệu MongoDB |

Change Streams cũng không biến MongoDB thành message queue vô hạn hoặc bảo đảm giữ mọi thay đổi mãi mãi; khả năng resume vẫn phụ thuộc lịch sử thay đổi còn sẵn và cách client xử lý lỗi.

## 10. Khi nào nên chọn collection thông thường?

Collection thông thường nên là lựa chọn mặc định khi dữ liệu có **giá trị nghiệp vụ kéo dài** hoặc cần thao tác theo từng document.

### 10.1. Dữ liệu khách hàng và hồ sơ

Thông tin khách hàng cần tồn tại, sửa đổi và tra cứu bất kể số lượng khách mới:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-100" },
  {
    $set: {
      name: "Minh",
      preferences: { language: "vi" },
      updatedAt: new Date()
    }
  },
  { upsert: true }
)
~~~

Capped collection không phù hợp vì các hồ sơ cũ có thể tự bị loại khi nhiều hồ sơ mới xuất hiện, đồng thời việc thay đổi kích thước document bị hạn chế.

### 10.2. Đơn hàng, thanh toán, tồn kho

Các record này có thể cần giữ lâu dài, có trạng thái cập nhật, audit và chính sách xóa riêng. Việc một đơn hàng cũ tự bị xóa vì có nhiều đơn hàng mới là hành vi không chấp nhận được.

### 10.3. Dữ liệu có thời hạn lưu rõ ràng

Ví dụ, lưu phiên truy cập đến thời điểm expireAt:

~~~javascript
db.createCollection("sessions")

db.sessions.createIndex(
  { expireAt: 1 },
  { expireAfterSeconds: 0 }
)

db.sessions.insertOne({
  tokenHash: "example-hash",
  userId: "U-001",
  expireAt: new Date(Date.now() + 60 * 60 * 1000)
})
~~~

TTL index hỗ trợ xóa record đã quá hạn theo chính sách thời gian. Việc xóa được thực hiện bất đồng bộ nên đây không phải bộ hẹn giờ xóa chính xác tức thì. Trong những thao tác yêu cầu bảo mật, ứng dụng vẫn phải tự kiểm tra expireAt khi quyết định token còn hiệu lực hay không.

Khác biệt căn bản:

~~~text
Collection thông thường + TTL:
    Hết hạn theo thời gian của từng document
    (xóa bất đồng bộ)

Capped collection:
    Loại document cũ khi ghi mới làm đạt giới hạn
    size hoặc max (không theo lịch hết hạn)
~~~

Nếu không có insert mới, capped collection có thể giữ các document cũ lâu hơn bất kỳ số ngày dự đoán nào.

## 11. Khi nào có thể chọn capped collection?

Capped collection phù hợp hơn khi dữ liệu là **luồng ngắn hạn, có thể loại bỏ phần cũ nhất**, số byte cần dành cho vùng đệm tương đối rõ ràng, và ứng dụng chủ yếu insert/read.

### 11.1. Vùng đệm log gần đây

Ví dụ ứng dụng muốn hiển thị N sự kiện gần nhất trên màn hình vận hành, nhưng log chuẩn đã được lưu ở nơi khác để phục vụ audit hoặc điều tra dài hạn.

~~~javascript
db.createCollection("diagnosticLog", {
  capped: true,
  size: 50 * 1024 * 1024,
  max: 20000
})
~~~

Thiết kế này chỉ có ý nghĩa khi mất sự kiện cũ khỏi vùng đệm **được chấp nhận**. Nếu log phục vụ yêu cầu pháp lý, giám sát bảo mật hoặc phân tích sự cố dài hạn, cần một hệ thống lưu trữ bền vững có retention rõ ràng.

### 11.2. Theo dõi sự kiện ngắn hạn cho công cụ phát triển

Một ứng dụng demo có thể ghi một luồng sự kiện vào capped collection để client dùng tailable cursor quan sát những bản tin mới:

~~~javascript
db.diagnosticLog.insertOne({
  at: new Date(),
  component: "payment-demo",
  level: "DEBUG",
  message: "Simulated request started"
})
~~~

Khi dữ liệu mới tràn vào, các event cũ biến mất nhưng ứng dụng demo vẫn có thể quan sát luồng gần đây. Đây là lựa chọn thuận tiện cho thí nghiệm, không phải một hệ thống event sourcing.

### 11.3. Trường hợp nên cân nhắc giải pháp khác

- **Time-series metrics và cảm biến:** tìm hiểu MongoDB time series collection, retention theo thời gian và mô hình truy vấn theo từng chuỗi đo.
- **Audit bắt buộc, lịch sử tài chính:** collection thông thường hoặc kho lưu trữ có chính sách giữ và sao lưu.
- **Hàng đợi công việc:** hệ thống queue/stream chuyên dụng hoặc thiết kế lưu trạng thái công việc không tự mất.
- **Danh sách bản ghi mới nhất có lọc phức tạp:** collection thông thường với index, TTL hoặc tác vụ bảo trì có thể dễ đáp ứng nghiệp vụ hơn.
- **Dữ liệu cần phân tán bằng sharding:** capped collection không phải lựa chọn hỗ trợ sharding.

Điểm quan trọng là **quy tắc mất dữ liệu** phải phù hợp với nghiệp vụ. Nếu bạn không chấp nhận một bản ghi biến mất khi có nhiều bản ghi mới, đừng chọn capped collection.

## 12. Thiết kế kích thước capped collection

Đặt size quá nhỏ khiến consumer chậm nhanh chóng bị mất dữ liệu. Đặt size quá lớn tiêu tốn dung lượng vùng đệm mà không bổ sung các bảo đảm về thời gian giữ dữ liệu. Cần ước lượng dựa trên thực tế ghi.

### 12.1. Ước lượng sơ bộ theo kích thước

Giả sử:

- Hệ thống ghi trung bình **100 sự kiện/giây**.
- Mỗi document BSON có kích thước trung bình khoảng **500 byte**.
- Muốn vùng đệm lý thuyết chứa khoảng **30 phút** dữ liệu.

Số document dự kiến:

\[
100\ \text{event/s} \times 30 \times 60\ \text{s}
= 180{,}000\ \text{event}
\]

Dung lượng thô:

\[
180{,}000 \times 500\ \text{byte}
= 90{,}000{,}000\ \text{byte}
\approx 85.8\ \text{MiB}
\]

Đây chỉ là phép tính **ước lượng**. Kích thước BSON thực tế có overhead, kích thước mỗi document không cố định và lưu lượng có thể bùng nổ. Có thể thêm biên an toàn và đo thực tế bằng thống kê trên tập dữ liệu có đặc điểm gần production.

Ví dụ cấu hình thí điểm:

~~~javascript
db.createCollection("measuredEvents", {
  capped: true,
  size: 128 * 1024 * 1024
})
~~~

Không nên gọi 128 MiB là cam kết giữ đúng 30 phút; nếu tốc độ ghi tăng gấp nhiều lần, thời gian tồn tại của bản ghi sẽ giảm tương ứng. Muốn bảo đảm retention theo thời gian, phải dùng chính sách lưu giữ khác.

### 12.2. Vì sao cần đo bằng dữ liệu thật?

Các document có message, metadata, stack trace hoặc payload lớn khiến dung lượng mỗi event chênh lệch mạnh. Số lượng index và tài nguyên storage engine cũng ảnh hưởng chi phí vận hành chung.

Quan sát bằng:

~~~javascript
db.measuredEvents.stats()
db.measuredEvents.countDocuments({})
~~~

Trong production, thêm metric về tốc độ insert, kích thước document, tốc độ consumer, tuổi bản ghi lâu nhất còn giữ, lỗi đọc cursor và tình trạng dung lượng đĩa. Mỗi metric trả lời một câu hỏi khác nhau; chỉ biết size cấu hình không đủ để chứng minh mọi consumer luôn bắt kịp.

### 12.3. Size không phải quota toàn hệ thống

Ngay cả khi capped collection có size 128 MiB, ổ đĩa còn chứa index, journal, metadata, những database khác và dữ liệu nội bộ. Không dùng size của một capped collection như bằng chứng rằng toàn bộ container MongoDB chỉ chiếm tối đa 128 MiB trên ổ đĩa.

## 13. Tương tác với ứng dụng Java/Spring Data MongoDB

Một ứng dụng Java dùng MongoDB Java Driver có thể đọc và ghi cả hai loại collection qua API MongoCollection. **Sự khác biệt nằm ở cấu hình collection và các ràng buộc do MongoDB server thực thi**, không nằm ở tên Java class.

### 13.1. Ghi document từ Java

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.Date;

public class WriteDiagnosticEvent {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> events = client
                    .getDatabase("collection_lab")
                    .getCollection("eventBuffer");

            events.insertOne(new Document("level", "INFO")
                    .append("message", "Java client started")
                    .append("producedAt", new Date()));
        }
    }
}
~~~

Đoạn code chỉ thực hiện insert; để **eventBuffer thực sự là capped**, collection phải được tạo đúng cấu hình từ trước. Chỉ gọi getCollection() hoặc insertOne() **không tự tạo capped collection**.

Nếu tên collection chưa tồn tại và có thao tác insert đủ quyền, MongoDB có thể tạo collection thông thường. Vì vậy, trong dự án cần capped, hãy quản lý bước khởi tạo database/collection có chủ đích rồi kiểm tra metadata khi triển khai.

### 13.2. Tạo capped collection bằng MongoTemplate

Với dự án đã cấu hình Spring Data MongoDB, có thể dùng MongoTemplate để tạo:

~~~java
import org.springframework.data.mongodb.core.CollectionOptions;
import org.springframework.data.mongodb.core.MongoTemplate;

public class MongoCollectionSetup {
    private final MongoTemplate mongoTemplate;

    public MongoCollectionSetup(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public void createEventBufferIfMissing() {
        if (!mongoTemplate.collectionExists("eventBuffer")) {
            mongoTemplate.createCollection(
                    "eventBuffer",
                    CollectionOptions.empty()
                            .capped()
                            .size(1024L * 1024L)
                            .maxDocuments(1000L)
            );
        }
    }
}
~~~

Đây là ví dụ API thiết lập collection; mã không phải quy trình migration hoàn chỉnh. Kiểm tra collectionExists rồi createCollection là hai thao tác riêng, vì vậy khi nhiều instance khởi động đồng thời có thể xảy ra race. Với triển khai thực tế, nên có bước quản lý schema/migration một lần, xử lý tình huống collection đã tồn tại và xác minh rằng collection hiện hữu thực sự là capped với options mong muốn.

Đừng chỉ nhìn thấy collectionExists("eventBuffer") bằng true rồi mặc định kiểu và size của collection đó là đúng.

### 13.3. Chọn model riêng cho vùng đệm

Một event phù hợp với capped thường có cấu trúc tương đối ổn định:

~~~javascript
{
  eventId: "evt-2026-001",
  occurredAt: ISODate("2026-11-14T03:15:00Z"),
  source: "checkout",
  level: "INFO",
  message: "Completed",
  code: 200
}
~~~

Các thành phần cần lưu ý:

- **eventId** giúp ứng dụng đối chiếu bản tin; cần xác định cơ chế tạo duy nhất nếu nghiệp vụ cần.
- **occurredAt** mô tả thời điểm nghiệp vụ, không tự quyết định thời điểm document bị loại.
- **level/source** giúp lọc quan sát; việc tạo index tùy workload.
- **message** có thể dài bất thường, làm giảm số event mà capped giữ được; cần đặt giới hạn payload phù hợp.

Ứng dụng nên xử lý lỗi insert và không phụ thuộc vào việc bản ghi vẫn còn sau một khoảng thời gian nhất định.

## 14. Những giới hạn và hiểu lầm thường gặp

| Hiện tượng | Nguyên nhân hoặc cách hiểu đúng | Hướng xử lý |
|---|---|---|
| db.createCollection báo collection đã tồn tại | Có thể đã insert trước khiến MongoDB tạo collection thông thường | Kiểm tra isCapped() và metadata; tạo collection bằng bước khởi tạo có kiểm soát |
| Document cũ tự biến mất | Capped rollover đã loại bản ghi khi size/max đạt giới hạn | Xác nhận đây là chính sách phù hợp; tăng dung lượng nếu cần giữ nhiều hơn, hoặc đổi cách lưu |
| Capped có max 1000 nhưng chỉ giữ 200 document | Kích thước byte đã đạt ngưỡng trước số lượng | Đo kích thước document và điều chỉnh size theo nhu cầu |
| Capped giữ bản ghi quá lâu so với kỳ vọng | Không có lượt ghi mới đủ để gây rollover | Dùng retention theo thời gian ở mô hình phù hợp nếu cần hạn lưu cố định |
| deleteOne/deleteMany trên capped báo lỗi | Capped không hỗ trợ xóa chọn lọc | Dùng collection thông thường nếu cần xóa theo document |
| update có thêm trường bị từ chối | Capped hạn chế thay đổi kích thước document | Dùng cấu trúc event bất biến hoặc chuyển sang collection thông thường |
| Tailable cursor không đọc được khi mở trên collection thường | Tailable cursor chỉ dành cho capped | Xác minh loại collection hoặc chọn API phù hợp |
| Tailable cursor ngừng hoạt động | Kết nối lỗi, cursor invalidated, dữ liệu cũ bị rollover hoặc trường hợp collection trống | Thiết kế reconnect/recovery và chấp nhận giới hạn dữ liệu |
| Kết quả find() không đúng thứ tự timestamp | Thứ tự chèn khác thời gian nghiệp vụ | Thêm trường thứ tự và sort phù hợp |
| Tạo capped với size nhỏ nhưng ổ đĩa vẫn tăng | Giới hạn size không quản lý toàn bộ index, journal, database khác | Theo dõi dung lượng toàn deployment và thiết kế quota/monitoring riêng |
| Dùng capped để đảm bảo 7 ngày retention | Capped giữ theo không gian/số lượng, không theo đồng hồ | Dùng TTL, time series hoặc quy trình lưu trữ khác |
| Không shard được capped collection | Giới hạn loại collection | Chuyển thiết kế lưu dữ liệu sang collection hỗ trợ phân mảnh khi cần |

### 14.1. Một lưu ý về hiệu năng

Capped collection được thiết kế để vận hành với không gian giới hạn và đọc tuần tự thuận tiện. Nhưng không có cơ sở để kết luận mọi thao tác insert hoặc query trên capped **luôn nhanh hơn** collection thông thường.

Hiệu năng phụ thuộc workload, index, kích thước document, concurrency, storage engine, phần cứng và mức độ tràn dữ liệu. Nên đo trên workload thật trước khi lựa chọn chỉ vì kỳ vọng tốc độ.

### 14.2. Một lưu ý về an toàn dữ liệu

Capped collection **không phải backup**, không phải kho lịch sử và không có bảo đảm bảo toàn những record cũ. Nếu ứng dụng đã dùng capped làm nguồn lưu duy nhất cho thông tin quan trọng, việc bản ghi bị loại theo giới hạn là rủi ro của thiết kế.

Ngay cả collection thông thường cũng cần chính sách backup, quyền truy cập, giám sát dung lượng và phục hồi. Khác biệt là document thông thường **không bị loại tự động theo cơ chế giới hạn vòng tròn**.

## 15. Bài tập thực hành

### Bài 1. Phân loại nhu cầu

Chọn loại collection phù hợp nhất và giải thích lý do:

1. Danh sách tài khoản đang hoạt động, có thể sửa email và địa chỉ.
2. Vùng đệm hiển thị 2.000 dòng log mới nhất cho trang debug.
3. Đơn hàng cần lưu lịch sử theo chính sách nghiệp vụ.
4. Session hết hạn sau thời điểm expireAt đã ghi trong document.
5. Bảng thông báo trạng thái thử nghiệm mà người xem có thể bỏ lỡ các thông báo cũ.

**Định hướng:** (1), (3) cần collection thông thường; (2), (5) có thể cân nhắc capped nếu chấp nhận tự loại dữ liệu cũ; (4) dùng collection thông thường với TTL index và kiểm tra hạn hiệu lực ở ứng dụng.

### Bài 2. Quan sát rollover

Tạo capped collection **practiceBuffer** có size bằng 1 MiB và max bằng 3. Ghi 5 document với seq lần lượt từ 1 đến 5. Sau đó:

~~~javascript
db.practiceBuffer.isCapped()

db.practiceBuffer
  .find({}, { seq: 1 })
  .sort({ $natural: 1 })

db.practiceBuffer.countDocuments({})
~~~

**Kết quả kỳ vọng:** isCapped() là true, còn tối đa 3 document. Nếu document nhỏ và không có nguồn ghi khác, các giá trị seq còn lại thường là 3, 4, 5. Giải thích vì sao document seq 1, 2 biến mất mà bạn không gọi deleteOne().

### Bài 3. Giải thích size và max

Một capped collection có:

~~~javascript
{
  capped: true,
  size: 1048576,
  max: 1000
}
~~~

Trong khi trung bình mỗi document khoảng 10 KiB. Liệu chắc chắn giữ được 1.000 document không? Vì sao?

**Định hướng:** không. Giới hạn 1 MiB có thể bị chạm sau khoảng một trăm document cỡ 10 KiB (chỉ là ước lượng), nên số document được giữ sẽ thấp hơn max.

### Bài 4. Đánh giá tailable cursor

Một client đọc sự kiện bằng tailable cursor. Sau đó client offline nhiều giờ, trong lúc producer ghi hàng triệu event mới và capped collection tự loại event cũ.

Trả lời:

1. Client có thể dùng chính cursor cũ để đọc lại mọi event đã bị loại không?
2. Có thể gọi tailable cursor là hàng đợi bảo đảm giao mọi message không?
3. Nếu business yêu cầu không mất sự kiện, bạn sẽ đổi thiết kế theo hướng nào?

**Định hướng:** các sự kiện bị loại không còn để đọc lại; tailable cursor không tự bảo đảm giao nhận bền vững. Cần lưu dữ liệu đủ lâu, theo dõi vị trí tiêu thụ, hoặc dùng hệ thống stream/queue có cơ chế phục hồi phù hợp.

### Bài 5. Chọn cách truy vấn

Bạn có collection thông thường orders và capped collection eventBuffer. Hãy viết truy vấn:

~~~javascript
// Orders theo thời gian tạo mới nhất, có khóa phụ để phân biệt
db.orders.find().sort({ createdAt: -1, _id: -1 })

// Event buffer theo thứ tự tự nhiên từ cũ sang mới
db.eventBuffer.find().sort({ $natural: 1 })
~~~

Giải thích vì sao truy vấn thứ nhất sắp xếp theo **quy tắc nghiệp vụ**, còn truy vấn thứ hai dựa vào **thứ tự lưu trữ** của capped collection. Đồng thời nêu lý do vì sao không nên xem $natural của collection thông thường là thứ tự thời gian ổn định.

## 16. Nguyên tắc lựa chọn trong dự án thực tế

Trước khi tạo một collection, hãy trả lời ba câu hỏi:

1. **Dữ liệu được phép tự biến mất khi vùng đệm đầy hay không?** Nếu không, hãy chọn collection thông thường hoặc một thiết kế lưu trữ dài hạn.
2. **Document có cần được cập nhật, xóa chọn lọc hoặc mở rộng kích thước hay không?** Nếu có, collection thông thường phù hợp hơn.
3. **Ứng dụng cần xem dữ liệu mới theo luồng hay cần truy vấn linh hoạt theo nghiệp vụ?** Capped hỗ trợ tailable cursor theo thứ tự tự nhiên; collection thông thường kết hợp index, Change Streams hoặc một kiến trúc streaming riêng có thể phục vụ nhu cầu khác.

**Collection thông thường** là nơi giữ dữ liệu theo vòng đời do ứng dụng quyết định. **Capped collection** là vùng lưu trữ có giới hạn, tự loại document cũ để dành chỗ cho document mới và hỗ trợ tailable cursor. Nắm được khác biệt này sẽ giúp bạn thiết kế schema MongoDB đúng mục đích, tránh mất dữ liệu ngoài ý muốn và lựa chọn cơ chế đọc sự kiện phù hợp.

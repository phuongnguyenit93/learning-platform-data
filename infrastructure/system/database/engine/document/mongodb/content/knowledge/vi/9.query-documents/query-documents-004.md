# Tập giá trị với $in, $nin và các trường hợp biên trong MongoDB

## 1. Khi nào cần truy vấn theo một tập giá trị?

Trong các ứng dụng dùng MongoDB, một câu truy vấn có thể cần tìm đơn hàng thuộc nhiều trạng thái, sản phẩm có bất kỳ nhãn khuyến mại nào, người dùng thuộc các nhóm cho phép hoặc bản ghi không nằm trong một danh sách chặn. Thay vì viết nhiều phép so sánh bằng, MongoDB cung cấp hai toán tử trong nhóm **query predicate**:

- `$in`: tìm document có trường khớp **ít nhất một giá trị** của danh sách.
- `$nin` (*not in*): tìm document mà trường **không khớp giá trị nào** của danh sách; với nhiều truy vấn, nó cũng khớp document **không có trường được xét**.

Cú pháp:

~~~javascript
db.collection.find({
  field: { $in: [value1, value2] }
});

db.collection.find({
  field: { $nin: [value1, value2] }
});
~~~

Cả hai đều yêu cầu toán hạng là **mảng giá trị**. Chúng có thể áp dụng cho trường đơn, trường mảng, trường nằm trong object lồng nhau và thuộc tính của phần tử trong mảng object.

Bài học thuộc chương **Truy vấn document** của **Database Engine Document MongoDB**. Sau khi hoàn thành, bạn có thể:

1. Chọn `$in`, `$nin`, `$all` hoặc `$elemMatch` theo đúng yêu cầu.
2. Dự đoán kết quả của filter khi trường bị thiếu, bằng `null`, là mảng rỗng hoặc chứa nhiều phần tử.
3. Xử lý danh sách đầu vào rỗng, trùng, sai kiểu và quá lớn.
4. Phân biệt `$in` dạng query predicate với `$in` dạng aggregation expression.
5. Viết truy vấn trên `mongosh`, MongoDB Compass và xem hiệu năng bằng `explain`.

## 2. Hiểu đúng ngữ nghĩa của $in và $nin

Giả sử tập trạng thái S = `["PAID", "SHIPPED"]`:

~~~text
status = "PAID"       $in: có       $nin: không
status = "SHIPPED"    $in: có       $nin: không
status = "NEW"        $in: không    $nin: có
status = "CANCELLED"  $in: không    $nin: có
~~~

| Đặc điểm | `$in` | `$nin` |
|---|---|---|
| Trường scalar | Bằng một giá trị thuộc danh sách | Khác mọi giá trị trong danh sách |
| Trường array | Ít nhất một phần tử thuộc danh sách | Không phần tử nào thuộc danh sách |
| Trường vắng mặt | Không khớp với danh sách giá trị thông thường; `null` cần xét riêng | Được chọn theo ngữ nghĩa của `$nin` |
| Toán hạng rỗng `[]` | Không document nào khớp | Không loại giá trị nào, có thể khớp toàn collection |
| Mức chọn lọc | Có thể cao nếu danh sách nhỏ | Thường thấp, vì khớp cả nhiều giá trị khác và trường thiếu |

**Chú ý:** `$nin` không bảo đảm trường đang xét tồn tại và có giá trị hợp lệ. Nếu nghiệp vụ cần “trường `status` tồn tại và không thuộc danh sách cấm”, hãy thêm điều kiện `$exists: true` hoặc ràng buộc kiểu BSON.

~~~javascript
{
  status: {
    $exists: true,
    $nin: ["CANCELLED", "DRAFT"]
  }
}
~~~

## 3. Bộ dữ liệu thực hành

Sử dụng một MongoDB Server/cluster mà bạn có quyền đọc ghi và mở `mongosh`. Mọi ví dụ ghi bên dưới chỉ dành cho database thực hành:

~~~javascript
use query_set_lab
~~~

Nạp collection `orders`:

~~~javascript
const demoOrders = [
  {
    _id: 1, status: "NEW", category: "books",
    title: "Sách Java",
    tags: ["sale", "new"], priority: NumberInt(1),
    assignee: null,
    customer: { tier: "silver", city: "Hà Nội" },
    items: [
      { sku: "A", qty: NumberInt(1) },
      { sku: "B", qty: NumberInt(3) }
    ]
  },
  {
    _id: 2, status: "PAID", category: "accessories",
    title: "Balo đi học",
    tags: ["gift"], priority: NumberInt(2),
    assignee: "lan",
    customer: { tier: "gold", city: "Đà Nẵng" },
    items: [
      { sku: "A", qty: NumberInt(4) },
      { sku: "C", qty: NumberInt(1) }
    ]
  },
  {
    _id: 3, status: "SHIPPED", category: "stationery",
    title: "Sổ ghi chú",
    tags: ["sale", "vip"], priority: NumberInt(3),
    assignee: "minh",
    customer: { tier: "gold", city: "Hà Nội" },
    items: [{ sku: "B", qty: NumberInt(2) }]
  },
  {
    _id: 4, status: "CANCELLED", category: "stationery",
    title: "Bút chì",
    tags: [], priority: NumberInt(1),
    assignee: "an",
    customer: { tier: "bronze", city: "Huế" },
    items: []
  },
  {
    _id: 5, status: "PAID", category: "books",
    title: "Tài liệu MongoDB",
    priority: null, assignee: "lan",
    customer: { tier: "silver", city: "Huế" },
    items: [{ sku: "D", qty: NumberInt(2) }]
  },
  {
    _id: 6, status: "PAID", category: "accessories",
    title: "Túi vải",
    tags: ["vip"], priority: NumberInt(2),
    assignee: null,
    customer: { tier: "gold", city: "Hà Nội" },
    items: [
      { sku: "A", qty: NumberInt(1) },
      { sku: "B", qty: NumberInt(7) }
    ]
  },
  {
    _id: 7, status: null, category: "home",
    title: "Ly thủy tinh",
    tags: ["sale"], priority: NumberInt(0),
    assignee: "ha",
    customer: { tier: "silver", city: "Huế" },
    items: []
  },
  {
    _id: 8, category: "home",
    title: "Bình giữ nhiệt",
    tags: ["clearance"], priority: NumberInt(1),
    assignee: "an",
    customer: { tier: "bronze", city: "Hà Nội" },
    items: [{ sku: "C", qty: NumberInt(5) }]
  },
  {
    _id: 9, status: "PAID", category: "books",
    title: "Bộ sách cơ sở dữ liệu",
    tags: ["sale", "gift"], priority: NumberInt(3),
    assignee: "linh",
    customer: { tier: "gold", city: "Đà Nẵng" },
    items: [{ sku: "X", qty: NumberInt(2) }]
  },
  {
    _id: 10, status: "SHIPPED", category: "stationery",
    title: "Hộp bút",
    tags: ["gift"], priority: NumberInt(2),
    assignee: "van",
    customer: { tier: "silver", city: "Huế" },
    items: [{ sku: "B", qty: NumberInt(4) }]
  }
];

demoOrders.forEach(order => {
  db.orders.replaceOne(
    { _id: order._id },
    order,
    { upsert: true }
  );
});

db.orders.countDocuments({});
~~~

Với collection mới, lệnh cuối trả về **10**. `replaceOne` với `upsert: true` giúp chạy lại mà không bị trùng `_id`; tuy nhiên, nó **đặt lại nội dung 10 document mẫu** nếu chúng đã được sửa trước đó. Nó không xóa document khác có trong collection. Các danh sách ID kỳ vọng bên dưới giả định collection chỉ chứa 10 bản ghi mẫu.

Những trường hợp biên được cố tình tạo:

- ID 7 có `status: null`, ID 8 **không có field status**.
- ID 4 có `tags: []`, ID 5 **không có field tags**.
- Các trường `tags` là mảng string; `items` là mảng object.
- Field `priority` là số Int32 ở phần lớn bản ghi, nhưng bằng `null` ở ID 5.
- Field `customer` là object có trường lồng nhau `tier` và `city`.

Khi đối chiếu kết quả, hãy dùng projection và `sort`:

~~~javascript
db.orders.find(
  { status: { $in: ["PAID", "SHIPPED"] } },
  { _id: 1, status: 1 }
).sort({ _id: 1 });
~~~

## 4. Dùng $in với một trường scalar

### 4.1. Trạng thái thuộc một trong các giá trị cho phép

~~~javascript
db.orders.find(
  { status: { $in: ["PAID", "SHIPPED"] } },
  { _id: 1, status: 1, title: 1 }
).sort({ _id: 1 });
~~~

Kết quả: ID **2, 3, 5, 6, 9, 10**.

Truy vấn trên tương đương về mặt logic với:

~~~javascript
db.orders.find({
  $or: [
    { status: "PAID" },
    { status: "SHIPPED" }
  ]
});
~~~

Khi các lựa chọn là phép bằng trên cùng một field, `$in` thường dễ đọc hơn một dãy dài các nhánh `$or`. Với các điều kiện khác nhau ở nhiều field, `$or` vẫn phù hợp.

### 4.2. Tập số nguyên

~~~javascript
db.orders.find(
  { priority: { $in: [NumberInt(1), NumberInt(3)] } },
  { _id: 1, priority: 1 }
).sort({ _id: 1 });
~~~

Kết quả: ID **1, 3, 4, 8, 9**.

Danh sách `[1, 3]` là tập các giá trị được chấp nhận. Document có `priority: 0`, `priority: 2` và `priority: null` không khớp.

### 4.3. Nhiều điều kiện được nối bằng AND

~~~javascript
db.orders.find({
  status: { $in: ["PAID", "SHIPPED"] },
  priority: { $gte: 2 }
});
~~~

MongoDB mặc định kết hợp điều kiện trên hai field bằng AND:

~~~text
status thuộc {"PAID", "SHIPPED"}
AND priority >= 2
~~~

Kết quả theo dữ liệu mẫu: ID **2, 3, 6, 9, 10**. ID 5 bị loại vì `priority: null`.

Có thể có nhiều toán tử `$in` trong cùng filter:

~~~javascript
db.orders.find({
  status: { $in: ["PAID", "SHIPPED"] },
  category: { $in: ["books", "stationery"] }
});
~~~

Đây là phép AND giữa hai nhóm lựa chọn, không phải OR giữa hai field.

## 5. Dùng $nin để loại trừ một tập

### 5.1. Trạng thái không nằm trong danh sách cấm

~~~javascript
db.orders.find(
  { status: { $nin: ["PAID", "SHIPPED"] } },
  { _id: 1, status: 1 }
).sort({ _id: 1 });
~~~

Kết quả: ID **1, 4, 7, 8**.

- ID 1 có trạng thái `NEW`.
- ID 4 có trạng thái `CANCELLED`.
- ID 7 có field `status` với giá trị `null`.
- ID 8 không hề có field `status`.

**ID 8 là điểm quan trọng:** `$nin` chọn cả document vắng field. Vì vậy, một filter chỉ có `$nin` không đủ để biểu diễn “các đơn có trạng thái hợp lệ khác PAID/SHIPPED”.

### 5.2. Kết hợp $exists

~~~javascript
db.orders.find(
  {
    status: {
      $exists: true,
      $nin: ["PAID", "SHIPPED"]
    }
  },
  { _id: 1, status: 1 }
).sort({ _id: 1 });
~~~

Kết quả: ID **1, 4, 7**; ID 8 bị loại. Nhưng ID 7 vẫn có mặt vì `$exists: true` chấp nhận field có giá trị null.

Nếu cần status **kiểu string**:

~~~javascript
db.orders.find({
  status: {
    $type: "string",
    $nin: ["PAID", "SHIPPED"]
  }
});
~~~

Kết quả: ID **1, 4**.

### 5.3. Chọn whitelist thay vì blacklist khi nghiệp vụ yêu cầu

Yêu cầu “trạng thái đơn đang hoạt động” có thể nên biểu diễn bằng tập cho phép:

~~~javascript
db.orders.find({
  status: { $in: ["NEW", "PAID", "SHIPPED"] }
});
~~~

Cách này tránh nhận document thiếu `status`, `status: null` hoặc một trạng thái lạ phát sinh trong tương lai. Ngược lại, một `$nin: ["CANCELLED"]` có thể cho qua tất cả các trường hợp ấy. Với các nghiệp vụ cần trạng thái rõ ràng, hãy xác định trước **tập giá trị hợp lệ**.

## 6. Trường mảng: ít nhất một phần tử và không có phần tử nào

### 6.1. $in trên mảng tags

~~~javascript
db.orders.find(
  { tags: { $in: ["sale", "vip"] } },
  { _id: 1, tags: 1 }
).sort({ _id: 1 });
~~~

Kết quả ID **1, 3, 6, 7, 9**. Chỉ cần **một phần tử** trong `tags` nằm trong danh sách là đủ.

ID 3 có cả `sale` và `vip` nhưng vẫn chỉ xuất hiện **một lần** trong kết quả `find()`. MongoDB trả về document khớp, không nhân bản document theo số phần tử khớp.

### 6.2. $nin trên mảng tags

~~~javascript
db.orders.find(
  { tags: { $nin: ["sale", "vip"] } },
  { _id: 1, tags: 1 }
).sort({ _id: 1 });
~~~

Kết quả ID **2, 4, 5, 8, 10**.

Ở đây:

- ID 2 có mảng `["gift"]`, không chứa nhãn cấm.
- ID 4 có mảng rỗng `[]`, không chứa nhãn cấm.
- ID 5 **thiếu field tags**, vẫn khớp `$nin`.
- ID 8 có mảng `["clearance"]`, không chứa nhãn cấm.

Nếu chỉ muốn document có field `tags` kiểu array và không chứa giá trị cấm:

~~~javascript
db.orders.find({
  tags: {
    $type: "array",
    $nin: ["sale", "vip"]
  }
});
~~~

Kết quả ID **2, 4, 8, 10**; ID 5 bị loại. ID 4 vẫn được chọn vì mảng rỗng thỏa yêu cầu “không chứa nhãn cấm”.

### 6.3. $all khác $in

~~~javascript
// Có sale HOẶC vip
db.orders.find({
  tags: { $in: ["sale", "vip"] }
});

// Có sale VÀ vip
db.orders.find({
  tags: { $all: ["sale", "vip"] }
});
~~~

Truy vấn thứ nhất khớp ID `1, 3, 6, 7, 9`. Truy vấn thứ hai chỉ khớp ID **3**.

| Nhu cầu | Toán tử |
|---|---|
| Có ít nhất một giá trị trong tập | `$in` |
| Không có bất kỳ giá trị cấm nào | `$nin` |
| Chứa đầy đủ mọi giá trị yêu cầu | `$all` |
| Một phần tử phải thỏa nhiều điều kiện | `$elemMatch` |

`$all` không yêu cầu mảng phải có **đúng** hai phần tử hoặc có thứ tự giống danh sách filter. Nếu mảng còn thêm nhãn khác thì vẫn có thể khớp.

## 7. Trường hợp biên: mảng rỗng, field thiếu và null

### 7.1. Danh sách so sánh rỗng

~~~javascript
db.orders.find({ status: { $in: [] } });
~~~

**Kết quả:** không document nào khớp, vì không tồn tại giá trị được phép.

~~~javascript
db.orders.find({ status: { $nin: [] } });
~~~

**Kết quả:** không có giá trị nào bị cấm; trên collection mẫu 10 document, cả **10** document có thể khớp, bao gồm document thiếu trường.

Nếu một API nhận danh sách giá trị rỗng, ứng dụng phải định nghĩa rõ “trả rỗng” hay “không áp dụng bộ lọc”. Không nên để hành vi của `$in: []` hoặc `$nin: []` tình cờ quyết định yêu cầu nghiệp vụ.

Đặc biệt tránh dùng `$nin: []` trong lệnh `updateMany`, `deleteMany` khi danh sách do chương trình tạo ra mà chưa kiểm tra, vì nó có thể tác động tới toàn collection.

### 7.2. Danh sách có phần tử trùng

~~~javascript
db.orders.find({
  status: { $in: ["PAID", "PAID", "SHIPPED"] }
});
~~~

Về ngữ nghĩa, tập trên cho kết quả giống `["PAID", "SHIPPED"]`. Các phần tử trùng có thể được loại bỏ ở tầng ứng dụng để giảm kích thước query và giúp dễ theo dõi log.

### 7.3. Bản thân field là mảng rỗng

~~~javascript
db.orders.find({ tags: { $size: 0 } });
~~~

Kết quả ID **4**. Trong khi đó:

~~~javascript
db.orders.find({ tags: { $exists: false } });
~~~

Kết quả ID **5**.

Hai trường hợp là khác nhau: `tags: []` có field kiểu array, còn ID 5 không có field `tags`.

Muốn tìm mảng có phần tử đầu tiên:

~~~javascript
db.orders.find({
  tags: { $type: "array" },
  "tags.0": { $exists: true }
});
~~~

Cách này loại mảng rỗng và document thiếu trường. Không dùng `$nin: []` để thay cho kiểm tra mảng không rỗng.

### 7.4. Phân biệt null và missing

Trong dữ liệu:

~~~javascript
// ID 7
{ _id: 7, status: null }

// ID 8
{ _id: 8, /* không có status */ }
~~~

Các truy vấn chẩn đoán:

~~~javascript
// Bằng null theo ngữ nghĩa equality: null hoặc missing
db.orders.find({ status: null });

// Chỉ field bị thiếu
db.orders.find({ status: { $exists: false } });

// Chỉ field hiện diện có BSON Null
db.orders.find({ status: { $type: "null" } });

// Field tồn tại, kể cả null
db.orders.find({ status: { $exists: true } });

// Field có giá trị không phải null
db.orders.find({ status: { $ne: null } });
~~~

Trên dữ liệu mẫu, `{ status: null }` chọn ID **7, 8**; `$exists: false` chọn ID **8**; `$type: "null"` chọn ID **7**.

`$exists: true` không có nghĩa “khác null”; nó chỉ kiểm tra trường có mặt. Một trường null cũng không đồng nghĩa chuỗi `"null"`.

### 7.5. Null nằm trong danh sách $in hoặc $nin

~~~javascript
db.orders.find({
  status: { $in: [null] }
});

db.orders.find({
  status: { $nin: [null] }
});
~~~

MongoDB có ngữ nghĩa riêng đối với equality-null và field vắng mặt. Khi nghiệp vụ cần phân biệt **null thật** với **missing**, nên viết điều kiện tường minh bằng `$type` hoặc `$exists` thay vì dựa vào suy luận toán học đơn giản rằng `$in: [null]` và `$nin: [null]` luôn là hai tập bù nhau trong mọi tình huống BSON đặc biệt.

Các mẫu filter rõ ý định:

~~~javascript
// Chỉ thiếu field
{ status: { $exists: false } }

// Chỉ BSON Null
{ status: { $type: "null" } }

// Có giá trị không null
{ status: { $ne: null } }

// Status phải là chuỗi và không thuộc tập bị cấm
{ status: { $type: "string", $nin: ["CANCELLED"] } }
~~~

Đối với dữ liệu kế thừa có BSON Undefined hoặc mảng chứa null, cần kiểm tra cách so sánh ở phiên bản MongoDB đang sử dụng, vì những kiểu đặc biệt có quy tắc riêng.

### 7.6. Toán hạng không phải mảng

~~~javascript
// Đúng
{ status: { $in: ["PAID"] } }

// Sai: đối số của $in không phải array
{ status: { $in: "PAID" } }

// Sai: đối số của $nin là object
{ status: { $nin: { value: "PAID" } } }
~~~

MongoDB yêu cầu toán hạng của các query predicate này là mảng. Khi nhận input từ form hoặc API, cần parse và kiểm tra danh sách trước khi chuyển cho driver.

## 8. Kiểu dữ liệu và phép so sánh bằng

MongoDB lưu giá trị theo kiểu BSON. `$in`/`$nin` không tự ép chuỗi thành số hay ObjectId.

### 8.1. String khác Number

~~~javascript
// Trong dữ liệu mẫu priority là số BSON
db.orders.find({
  priority: { $in: [NumberInt(1), NumberInt(2)] }
});

// Danh sách chứa chuỗi "1", "2"
db.orders.find({
  priority: { $in: ["1", "2"] }
});
~~~

Chuỗi `"2"` không tự chuyển thành số `2`. Ngược lại, giữa các **kiểu số BSON**, MongoDB có quy tắc so sánh theo giá trị số; không nên kết luận Int32 và Int64 có cùng giá trị luôn bị xem là khác nhau khi so sánh numeric.

Khi field nghiệp vụ phải có một kiểu, hãy dùng schema validation và chuẩn hóa dữ liệu đầu vào thay vì cho nhiều kiểu sai vào cùng danh sách `$in`.

### 8.2. ObjectId khác chuỗi mã hex

~~~javascript
const id = ObjectId("64a000000000000000000001");

db.someCollection.find({
  _id: { $in: [id] }
});

db.someCollection.find({
  _id: { $in: ["64a000000000000000000001"] }
});
~~~

Hai truy vấn không tương đương nếu field `_id` thực sự lưu ObjectId. `someCollection` chỉ là tên collection minh họa; bộ dữ liệu `orders` ở trên dùng `_id` dạng số.

### 8.3. Date khác chuỗi ISO

~~~javascript
{
  createdAt: {
    $in: [
      ISODate("2026-11-01T00:00:00Z"),
      ISODate("2026-11-02T00:00:00Z")
    ]
  }
}
~~~

Khi `createdAt` là BSON Date, truyền chuỗi ngày giờ không tự trở thành Date. `$in` so sánh **mốc thời gian cụ thể**; nếu muốn tất cả đơn trong một ngày, thường dùng khoảng `$gte` và `$lt`.

### 8.4. Chữ hoa, chữ thường và collation

~~~javascript
db.orders.find({ status: { $in: ["paid"] } });
~~~

Với cách so sánh chuỗi mặc định phân biệt hoa/thường, `"paid"` khác `"PAID"`. Có thể yêu cầu collation phù hợp:

~~~javascript
db.orders.find({
  status: { $in: ["paid", "shipped"] }
}).collation({ locale: "en", strength: 2 });
~~~

Cần chú ý index hỗ trợ truy vấn có collation tương thích. Với enum trạng thái, thường nên quy định cách viết chuẩn ngay khi ghi để tránh việc nhiều dạng chuỗi cùng biểu thị một trạng thái.

## 9. Truy vấn field lồng nhau và mảng object

### 9.1. Dot notation với object

~~~javascript
db.orders.find({
  "customer.tier": { $in: ["gold", "silver"] }
});
~~~

Đường dẫn `customer.tier` cho phép so sánh một trường trong object mà không cần so sánh toàn bộ object `customer`.

~~~javascript
db.orders.find({
  "customer.city": { $nin: ["Hà Nội", "Huế"] }
});
~~~

Nếu `customer.city` bị thiếu, ngữ nghĩa của `$nin` với trường vắng vẫn cần được cân nhắc.

### 9.2. Dot notation với mảng object

~~~javascript
db.orders.find({
  "items.sku": { $in: ["A", "B"] }
});
~~~

Kết quả ID **1, 2, 3, 6, 10**. Truy vấn chọn đơn mà có ít nhất một phần tử `items` có SKU là A hoặc B.

### 9.3. Khi nhiều điều kiện phải nằm trên cùng phần tử

Yêu cầu: có ít nhất một dòng hàng với SKU A/B và số lượng ≥ 3.

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: { $in: ["A", "B"] },
      qty: { $gte: 3 }
    }
  }
});
~~~

Kết quả ID **1, 2, 6, 10**. ID 3 có SKU B nhưng qty = 2.

Nếu viết:

~~~javascript
db.orders.find({
  "items.sku": { $in: ["A", "B"] },
  "items.qty": { $gte: 3 }
});
~~~

hai điều kiện có thể khớp **hai phần tử khác nhau** của mảng. Để tự quan sát, chèn thêm vào collection thực hành:

~~~javascript
db.orders.replaceOne(
  { _id: 11 },
  {
    _id: 11,
    status: "NEW",
    title: "Trường hợp chéo phần tử",
    items: [
      { sku: "A", qty: NumberInt(1) },
      { sku: "Z", qty: NumberInt(10) }
    ]
  },
  { upsert: true }
);
~~~

Với ID 11, truy vấn hai đường dẫn độc lập có thể khớp do phần tử đầu có SKU A và phần tử sau có qty 10; truy vấn dùng `$elemMatch` **không khớp** vì không có phần tử nào thỏa cả hai điều kiện.

Khi xong bài, có thể xóa đúng record thử nghiệm:

~~~javascript
db.orders.deleteOne({ _id: 11 });
~~~

### 9.4. $nin trên thuộc tính của mảng object

~~~javascript
db.orders.find({
  "items.sku": { $nin: ["A", "B"] }
});
~~~

Câu này có nghĩa **không có phần tử** mang SKU A/B; không có nghĩa “tồn tại ít nhất một dòng hàng có SKU khác A/B”. Với yêu cầu thứ hai, dùng điều kiện tồn tại một phần tử:

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: { $exists: true, $nin: ["A", "B"] }
    }
  }
});
~~~

Hai câu có ngữ nghĩa khác nhau, đặc biệt khi một mảng vừa chứa SKU bị cấm vừa chứa SKU được phép.

## 10. Regex trong tập $in

`$in` ở ngữ cảnh **query predicate** có thể nhận JavaScript regular expression literal:

~~~javascript
db.orders.find({
  title: {
    $in: [/^Sách/, /^Bộ sách/, "Balo đi học"]
  }
});
~~~

Dữ liệu mẫu có các title như `Sách Java`, `Bộ sách cơ sở dữ liệu` và `Balo đi học` khớp biểu thức. Ký hiệu `^` là đầu chuỗi; thêm cờ `i` nếu muốn khớp không phân biệt hoa/thường.

**Không đặt object `$regex` bên trong mảng `$in`** như sau:

~~~javascript
// Không phải cách viết đúng của query $in với regex
{
  title: {
    $in: [
      { $regex: "^Sách" }
    ]
  }
}
~~~

Dùng regex literal:

~~~javascript
{ title: { $in: [/^Sách/] } }
~~~

Hoặc dùng `$regex` bên ngoài `$in` khi chỉ cần một pattern:

~~~javascript
db.orders.find({
  title: { $regex: "^sách", $options: "i" }
});
~~~

Các pattern regex quá rộng có thể tốn tài nguyên hoặc khó tận dụng index. Nếu pattern đến từ người dùng, cần kiểm soát chiều dài, cú pháp và chi phí thực thi.

## 11. Query $in khác aggregation expression $in

MongoDB dùng cùng tên `$in` trong hai nhóm toán tử.

### 11.1. Query predicate

~~~javascript
db.orders.find({
  status: { $in: ["PAID", "SHIPPED"] }
});
~~~

Truy vấn trực tiếp theo field. Nếu field là array, một phần tử của array có thể khớp.

### 11.2. Aggregation expression

Cú pháp trong `$project`, `$set`, `$expr` là:

~~~javascript
{
  $in: [<expressionOfValue>, <expressionOfArray>]
}
~~~

Ví dụ:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      status: 1,
      isReady: {
        $in: ["$status", ["PAID", "SHIPPED"]]
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Aggregation expression trả về boolean, yêu cầu **đúng hai đối số** và đối số thứ hai phải là array. Nó không thực hiện regex matching như query predicate `$in`.

Muốn tìm nhãn `sale` trong field `tags` dạng array:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      hasSaleTag: {
        $in: ["sale", { $ifNull: ["$tags", []] }]
      }
    }
  }
]);
~~~

`$ifNull` đưa field thiếu/null về `[]`. Nếu dữ liệu có thể chứa chuỗi thay vì array, cần kiểm tra `$isArray` hoặc chuẩn hóa trước để tránh lỗi đối số không phải array.

Nếu trường `status` là array, biểu thức `$in: ["$status", ["PAID","SHIPPED"]]` so sánh **toàn bộ array** như một giá trị; nó không tự tìm giao giữa các phần tử như query predicate trên field array. Với nhu cầu giao hai mảng, có thể dùng `$setIntersection` khi cả hai nguồn đều là array.

### 11.3. Phủ định expression $in

Trong aggregation, có thể kết hợp `$not` với expression `$in`:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      isOutsideSet: {
        $not: [
          { $in: ["$status", ["PAID", "SHIPPED"]] }
        ]
      }
    }
  }
]);
~~~

Đây là phép phủ định của expression, không nên mặc định mọi trường hợp missing/null đều giống query predicate `$nin`. Khi cần phân biệt kiểu, dùng `$type`, `$ifNull` hoặc điều kiện explicit.

## 12. Index, độ chọn lọc và hiệu năng

### 12.1. Chạy explain cho $in

~~~javascript
db.orders.createIndex({ status: 1 });

db.orders.find({
  status: { $in: ["PAID", "SHIPPED"] }
}).explain("executionStats");
~~~

Quan sát:

- `winningPlan`: kế hoạch MongoDB lựa chọn.
- `IXSCAN`: quét index.
- `COLLSCAN`: quét toàn collection.
- `totalKeysExamined`: số khóa index được duyệt.
- `totalDocsExamined`: số document được kiểm tra.
- `nReturned`: số document trả về.

Với 10 document, query planner có thể chọn `COLLSCAN` dù đã có index; không nên xem đây là lỗi. Cần so sánh trên dữ liệu và workload đại diện cho sản xuất.

### 12.2. Vì sao $nin có thể chậm?

~~~javascript
db.orders.find({
  status: { $nin: ["PAID", "SHIPPED"] }
}).explain("executionStats");
~~~

`$nin` thường **kém chọn lọc** vì có thể khớp phần lớn collection và cả field thiếu. Một index không chắc giúp truy vấn nhanh hơn. Nếu nghiệp vụ chỉ cần một tập trạng thái hợp lệ nhỏ, chuyển sang `$in` với whitelist rõ ràng có thể giúp lựa chọn dữ liệu có chủ đích hơn; hiệu năng vẫn cần được đo.

### 12.3. Danh sách $in có nhiều giá trị

Khi danh sách tăng tới hàng trăm hoặc hàng nghìn phần tử, query có thể phải xử lý nhiều giá trị, gây chi phí parse, truyền qua mạng, tra index và kết hợp kết quả. Hãy:

1. Giới hạn và khử trùng danh sách từ API.
2. Theo dõi kích thước và tính chọn lọc của filter.
3. Kiểm tra explain trên dữ liệu thực.
4. Cân nhắc chia batch khi hợp lý, nhưng chú ý chi phí nhiều lượt gọi.
5. Cân nhắc thiết kế khác nếu danh sách đến từ một collection riêng.

Không tự chọn một ngưỡng cố định rồi khẳng định mọi truy vấn vượt ngưỡng đều chậm; kết quả phụ thuộc index, dữ liệu và cách MongoDB lập kế hoạch.

### 12.4. Collation và index

Truy vấn có collation so sánh chuỗi không phân biệt hoa/thường có thể cần index cấu hình collation tương thích. Nếu không, MongoDB có thể không dùng được index như kỳ vọng cho so sánh string. Với các trạng thái máy có tập giá trị hữu hạn, chuẩn hóa đầu vào thường giúp dữ liệu và filter đơn giản hơn.

## 13. Filter tương ứng trong MongoDB Compass

Kết nối Compass tới cùng server, chọn database `query_set_lab`, collection `orders`, mở tab **Documents**, nhập các filter sau trong Query Bar:

| Yêu cầu | Filter |
|---|---|
| Đơn đã thanh toán hoặc giao hàng | `{"status":{"$in":["PAID","SHIPPED"]}}` |
| Loại PAID và SHIPPED | `{"status":{"$nin":["PAID","SHIPPED"]}}` |
| Status phải tồn tại, đồng thời không bị loại | `{"status":{"$exists":true,"$nin":["PAID","SHIPPED"]}}` |
| Có nhãn sale hoặc vip | `{"tags":{"$in":["sale","vip"]}}` |
| Không có nhãn bị cấm | `{"tags":{"$nin":["sale","vip"]}}` |
| Có đủ sale và vip | `{"tags":{"$all":["sale","vip"]}}` |
| Khách hàng gold hoặc silver | `{"customer.tier":{"$in":["gold","silver"]}}` |
| SKU A/B và qty ≥ 3 trong cùng một dòng | `{"items":{"$elemMatch":{"sku":{"$in":["A","B"]},"qty":{"$gte":3}}}}` |
| Chỉ thiếu field status | `{"status":{"$exists":false}}` |

Nhấn **Find** hoặc **Apply** (tùy phiên bản) và đối chiếu kết quả với mongosh. Nếu số document khác, kiểm tra có đang kết nối đúng server/collection không, đã xóa filter cũ chưa, đã refresh giao diện chưa và có thêm document ngoài bộ mẫu không.

Trình soạn filter JSON trong Compass dùng khóa và chuỗi trong dấu nháy kép. Cú pháp mongosh là JavaScript object nên nhiều ví dụ bỏ dấu nháy quanh khóa. Chức năng **Explain Plan** trong Compass, nếu có, giúp quan sát cách server thực thi filter.

## 14. Sử dụng trong ứng dụng Java

Với MongoDB Java Driver, có thể tạo filter `$in` và `$nin` bằng lớp Filters thay vì nối chuỗi JSON:

~~~java
import static com.mongodb.client.model.Filters.in;
import static com.mongodb.client.model.Filters.nin;
import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.exists;

import java.util.List;
import org.bson.conversions.Bson;

List<String> allowed = List.of("PAID", "SHIPPED");

Bson allowedStatuses = in("status", allowed);
Bson excludedStatuses = nin("status", allowed);

Bson excludedButPresent = and(
    exists("status", true),
    nin("status", allowed)
);
~~~

`allowedStatuses` là điều kiện lấy trạng thái thuộc tập; `excludedStatuses` loại các trạng thái trong tập; `excludedButPresent` thêm yêu cầu field phải tồn tại.

Khi API nhận danh sách:

- Kiểm tra từng giá trị theo tập enum được phép; tránh để client gửi object toán tử tùy ý.
- Quy định việc chuẩn hóa chữ hoa/thường.
- Loại trùng và giới hạn số lượng phần tử.
- Xác định rõ nghĩa của danh sách rỗng.
- Bảo đảm đúng kiểu BSON trước khi xây filter.
- Không ghép chuỗi query JSON trực tiếp từ input không đáng tin cậy.

Những bước này giúp giảm lỗi dữ liệu và nguy cơ NoSQL injection khi filter được tạo từ dữ liệu ngoài.

## 15. Cẩn trọng khi dùng $nin trong thao tác ghi

Trước khi thay đổi dữ liệu theo danh sách giá trị, hãy dùng cùng filter để xem và đếm document:

~~~javascript
const filter = {
  status: { $in: ["NEW", "CANCELLED"] }
};

db.orders.find(filter, { _id: 1, status: 1 });
db.orders.countDocuments(filter);

// Chỉ thực hiện trong database thực hành sau khi xem đúng phạm vi:
db.orders.updateMany(
  filter,
  { $set: { needsReview: true } }
);
~~~

Sau lệnh cập nhật, `matchedCount` và `modifiedCount` có thể khác nhau nếu field đã mang giá trị đích.

**Ví dụ nguy hiểm cần nhận diện:**

~~~javascript
// Không chạy trên dữ liệu thật
db.orders.deleteMany({
  status: { $nin: ["PAID"] }
});
~~~

Lệnh này có thể chọn cả document thiếu `status`, null hoặc có trạng thái mới chưa được dự liệu. Với trường hợp xóa dữ liệu, whitelist trạng thái được phép xóa và thêm các ràng buộc rõ ràng thường an toàn hơn.

Tương tự, `$nin: []` có thể chọn toàn collection. Nếu danh sách cấm được tính động, phải kiểm soát đầu vào trước khi phát lệnh.

## 16. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm | Diễn giải đúng |
|---|---|
| `$in` trên array đòi mảng bằng đúng danh sách | Chỉ cần một phần tử khớp |
| `$nin` trên array nghĩa là có một phần tử nằm ngoài tập | Nó đòi không có phần tử nào nằm trong tập cấm |
| `$nin` không chọn document thiếu field | Nó có thể chọn field missing |
| `$exists: true` loại được null | Nó vẫn chấp nhận field tồn tại với giá trị null |
| `$in: []` nghĩa là không áp dụng filter | Nó không khớp document nào |
| `$nin: []` nghĩa là không khớp document nào | Nó không loại giá trị nào, có thể khớp toàn bộ |
| Field array rỗng giống field missing | Là hai dạng dữ liệu khác nhau |
| `$in` có thể thay `$all` | `$in` là OR, `$all` yêu cầu đầy đủ |
| Điều kiện `items.sku` và `items.qty` tự áp dụng cùng phần tử | Cần `$elemMatch` để ràng buộc cùng phần tử |
| Số `2` và chuỗi `"2"` tự so sánh bằng | Chúng khác kiểu BSON |
| ObjectId bằng chuỗi hex nhìn giống nó | BSON ObjectId khác string |
| Regex `{$regex: ...}` đặt trực tiếp trong mảng `$in` | Query `$in` dùng regex literal `/pattern/` |
| Aggregation `$in` giống hoàn toàn query `$in` | Hai cú pháp và cách xét array khác nhau |
| Có index là `$nin` chắc chắn nhanh | `$nin` thường ít chọn lọc |
| Thêm nhiều giá trị trong danh sách không ảnh hưởng hiệu năng | Danh sách lớn tăng chi phí truy vấn tùy workload |

## 17. Bài thực hành tổng hợp

### Bài 1: Trạng thái thuộc tập

Tìm đơn có trạng thái `PAID` hoặc `SHIPPED`, chỉ trả `_id` và `status`, sắp tăng dần.

~~~javascript
db.orders.find(
  { status: { $in: ["PAID", "SHIPPED"] } },
  { _id: 1, status: 1 }
).sort({ _id: 1 });
~~~

Kết quả ID: **2, 3, 5, 6, 9, 10**.

### Bài 2: Loại trừ có và không có $exists

So sánh:

~~~javascript
db.orders.find({
  status: { $nin: ["PAID", "SHIPPED"] }
});

db.orders.find({
  status: {
    $exists: true,
    $nin: ["PAID", "SHIPPED"]
  }
});
~~~

Kết quả thứ nhất: **1, 4, 7, 8**; thứ hai: **1, 4, 7**. ID 8 thiếu status nên bị loại khi thêm `$exists: true`. ID 7 có status null nên vẫn thỏa điều kiện tồn tại.

### Bài 3: Nhãn ở mảng

Truy vấn:

~~~javascript
db.orders.find({ tags: { $in: ["sale", "vip"] } });
db.orders.find({ tags: { $nin: ["sale", "vip"] } });
db.orders.find({ tags: { $all: ["sale", "vip"] } });
~~~

Kết quả ID tương ứng:

- `$in`: **1, 3, 6, 7, 9**.
- `$nin`: **2, 4, 5, 8, 10**.
- `$all`: **3**.

Giải thích vì sao ID 4 có mảng rỗng và ID 5 thiếu field đều khớp `$nin`.

### Bài 4: Tập rỗng

~~~javascript
db.orders.countDocuments({ status: { $in: [] } });
db.orders.countDocuments({ status: { $nin: [] } });
~~~

Trên collection đúng 10 document, kết quả là **0** và **10**. Nếu ứng dụng muốn coi danh sách rỗng là “bỏ lọc”, nó phải xử lý ở tầng API thay vì gửi `$in: []`.

### Bài 5: Tìm null và missing

~~~javascript
db.orders.find({ status: { $exists: false } });
db.orders.find({ status: { $type: "null" } });
db.orders.find({ status: { $ne: null } });
~~~

Hai truy vấn đầu chọn lần lượt ID **8** và ID **7**. Truy vấn cuối chọn các document có giá trị `status` khác null, không gồm ID 7 và 8.

### Bài 6: Kết hợp với trường lồng nhau

~~~javascript
db.orders.find({
  "customer.tier": { $in: ["gold", "silver"] },
  status: "PAID"
});
~~~

Kết quả ID: **2, 5, 6, 9**.

### Bài 7: Từng phần tử mảng object

~~~javascript
db.orders.find({
  items: {
    $elemMatch: {
      sku: { $in: ["A", "B"] },
      qty: { $gte: 3 }
    }
  }
});
~~~

Kết quả ID: **1, 2, 6, 10**. Hãy tạo ID 11 ở mục 9 và giải thích tại sao filter dùng hai đường dẫn độc lập có thể cho kết quả khác.

### Bài 8: Quan sát index

~~~javascript
db.orders.createIndex({ status: 1 });

db.orders.find({
  status: { $in: ["PAID", "SHIPPED"] }
}).explain("executionStats");

db.orders.find({
  status: { $nin: ["PAID", "SHIPPED"] }
}).explain("executionStats");
~~~

Ghi nhận `nReturned`, `totalDocsExamined`, `IXSCAN` hoặc `COLLSCAN`. Giải thích vì sao bộ dữ liệu 10 document không đủ để kết luận một index sẽ hiệu quả ở production.

### Bài 9: Định nghĩa truy vấn từ yêu cầu

| Yêu cầu | Cách chọn |
|---|---|
| Một trong ba trạng thái được cho phép | `$in` |
| Không chứa nhãn sale/vip | `$nin` |
| Chứa cả sale và vip | `$all` |
| Một phần tử có SKU thuộc tập và qty ≥ 3 | `$elemMatch` kết hợp `$in` |
| Không thuộc trạng thái cấm nhưng field phải có | `$nin` kèm `$exists: true` |
| Field phải là string và khác trạng thái cấm | `$type: "string"` kèm `$nin` |
| Danh sách đầu vào rỗng nghĩa là bỏ lọc | Xử lý trước khi gửi query |
| Tìm mọi document có field null thật | `$type: "null"` |

## 18. Nguyên tắc áp dụng trong dự án

Trước khi viết `$in` hoặc `$nin`, cần xác định **field đang là scalar hay array**, **có thể missing/null không**, và **danh sách đầu vào có thể rỗng hoặc sai kiểu không**. Nếu field là array, hãy phân biệt “có ít nhất một”, “không có bất kỳ”, “có đủ tất cả” và “cùng một phần tử thỏa nhiều điều kiện”. Chúng tương ứng với `$in`, `$nin`, `$all` và `$elemMatch` nhưng không thể thay thế tùy ý.

Trong truy vấn nghiệp vụ có trạng thái hợp lệ rõ ràng, ưu tiên biểu diễn danh sách được phép bằng `$in`; dùng `$nin` khi thực sự muốn loại trừ một tập và đã hiểu cách xử lý field thiếu. Khi dữ liệu tăng, đánh giá hiệu năng dựa trên `explain` và workload thực, nhất là đối với `$nin` có độ chọn lọc thấp.

## Tài liệu tham khảo

- [MongoDB Manual: $in query predicate](https://www.mongodb.com/docs/manual/reference/operator/query/in/)
- [MongoDB Manual: $nin query predicate](https://www.mongodb.com/docs/manual/reference/operator/query/nin/)
- [MongoDB Manual: $exists](https://www.mongodb.com/docs/manual/reference/operator/query/exists/)
- [MongoDB Manual: $in aggregation expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/in/)
- [MongoDB Manual: $regex query](https://www.mongodb.com/docs/manual/reference/operator/query/regex/)

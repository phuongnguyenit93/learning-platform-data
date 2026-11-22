# replaceOne và giới hạn thay thế document, trường _id trong MongoDB

## 1. Mục tiêu bài học

MongoDB cho phép sửa dữ liệu bằng các toán tử cập nhật như `$set`, `$inc`, `$unset` hoặc thay **toàn bộ document** bằng `replaceOne()`. Hai cách này có tác động rất khác nhau: cập nhật từng trường giữ lại những trường không đề cập, còn thay thế document có thể làm mất các trường cũ không xuất hiện trong dữ liệu thay thế.

Đây là một bài học trong chương **Cập nhật document** của **Database Engine Document MongoDB**, tập trung vào phương thức `replaceOne()` và các giới hạn của phép thay thế, đặc biệt là trường định danh bất biến `_id`.

Sau khi học, bạn có thể:

- Phân biệt `replaceOne` với `updateOne`, `updateMany` và `findOneAndReplace`.
- Viết filter, replacement document và các tùy chọn `upsert` đúng mục đích.
- Dự đoán trường nào được giữ, trường nào bị xóa khi thay thế document.
- Giải thích vì sao `_id` không thể bị đổi trong phép replacement; xử lý đúng khi replacement có hoặc không có `_id`.
- Đọc kết quả `matchedCount`, `modifiedCount`, `upsertedId`.
- Tránh ghi đè nhầm dữ liệu khi filter không đủ cụ thể hoặc document được nhiều tiến trình cập nhật.
- Sử dụng `replaceOne` với dữ liệu lồng nhau, mảng, schema validation và ví dụ Java Driver.

Các lệnh ghi dưới đây sử dụng database **`replace_lab`** dành riêng cho thực hành. Không chạy trực tiếp trên collection sản xuất.

## 2. replaceOne là gì?

Cú pháp trong `mongosh`:

~~~javascript
db.collection.replaceOne(
  filter,
  replacement,
  options
);
~~~

Trong đó:

| Tham số | Ý nghĩa | Ví dụ |
|---|---|---|
| `filter` | Điều kiện tìm document cần thay | `{ _id: "sku-100" }` |
| `replacement` | Document BSON mới chứa toàn bộ các trường muốn giữ sau khi thay | `{ name: "Balo", price: NumberDecimal("20.00") }` |
| `options` | Cấu hình bổ sung; thường dùng `upsert` | `{ upsert: true }` |

Mặc định, `replaceOne` chỉ xem xét **một document phù hợp filter**. Nếu có nhiều document khớp, không được dựa vào thứ tự tự nhiên để đoán document nào sẽ bị thay. Hãy dùng filter duy nhất, thường là `_id`, hoặc một khóa unique phù hợp.

Phép thay thế làm việc trên **document**. Nó không thay từng thuộc tính, không gộp object lồng nhau, không nối hai mảng và không tự bảo tồn các field còn thiếu trong replacement.

Ví dụ:

~~~javascript
// Document trước khi thay
{
  _id: "sku-100",
  name: "Áo thun",
  price: NumberDecimal("15.50"),
  stock: NumberInt(12),
  tags: ["new", "summer"],
  supplier: { code: "SUP-A", city: "Hà Nội" }
}
~~~

Lệnh:

~~~javascript
db.products.replaceOne(
  { _id: "sku-100" },
  {
    name: "Áo thun basic",
    price: NumberDecimal("16.00")
  }
);
~~~

Document sau khi thay:

~~~javascript
{
  _id: "sku-100",
  name: "Áo thun basic",
  price: NumberDecimal("16.00")
}
~~~

Các trường `stock`, `tags` và `supplier` **không còn** vì chúng không được đưa vào replacement. Riêng `_id` được giữ lại dù replacement không khai báo, vì `_id` của document hiện hữu là định danh bất biến.

## 3. Chuẩn bị bộ dữ liệu thực hành

Kết nối MongoDB bằng `mongosh` rồi chọn database thực hành:

~~~javascript
use replace_lab
~~~

Tạo dữ liệu mẫu:

~~~javascript
const seedProducts = [
  {
    _id: "sku-100",
    name: "Áo thun",
    category: "fashion",
    price: NumberDecimal("15.50"),
    stock: NumberInt(12),
    tags: ["new", "summer"],
    supplier: {
      code: "SUP-A",
      city: "Hà Nội"
    },
    createdAt: ISODate("2026-11-01T08:00:00Z"),
    version: NumberInt(1)
  },
  {
    _id: "sku-200",
    name: "Balo",
    category: "accessories",
    price: NumberDecimal("32.00"),
    stock: NumberInt(5),
    tags: ["school"],
    supplier: {
      code: "SUP-B",
      city: "Đà Nẵng"
    },
    createdAt: ISODate("2026-11-02T09:00:00Z"),
    version: NumberInt(1)
  },
  {
    _id: "sku-300",
    name: "Sổ tay",
    category: "stationery",
    price: NumberDecimal("4.50"),
    stock: NumberInt(40),
    tags: ["office"],
    supplier: {
      code: "SUP-C",
      city: "Huế"
    },
    createdAt: ISODate("2026-11-03T10:00:00Z"),
    version: NumberInt(1)
  }
];

seedProducts.forEach(product => {
  db.products.replaceOne(
    { _id: product._id },
    product,
    { upsert: true }
  );
});

db.products.find().sort({ _id: 1 });
~~~

Nếu collection ban đầu rỗng, ba sản phẩm sẽ được tạo. Đoạn nạp dữ liệu sử dụng `replaceOne` với `upsert: true` để có thể chạy lại theo `_id`, nhưng **sẽ đặt lại các sản phẩm mẫu** về trạng thái ban đầu. Vì vậy chỉ chạy lại khi muốn làm mới bài thực hành.

Bộ dữ liệu sử dụng `_id` dạng **string** để dễ quan sát. MongoDB cũng thường dùng `ObjectId` làm kiểu `_id` mặc định nếu client không cung cấp định danh. Kiểu dữ liệu của `_id` là một phần của hợp đồng dữ liệu: chuỗi `"sku-100"` và `ObjectId("...")` là các kiểu khác nhau.

## 4. Thay thế một document theo _id

### 4.1. Thay thế với toàn bộ các trường muốn giữ

Giả sử cần sửa `sku-100`, đồng thời **giữ lại** metadata và các field chưa thay đổi. Cách rõ ràng là cung cấp đầy đủ replacement:

~~~javascript
const result = db.products.replaceOne(
  { _id: "sku-100" },
  {
    _id: "sku-100",
    name: "Áo thun basic",
    category: "fashion",
    price: NumberDecimal("16.00"),
    stock: NumberInt(12),
    tags: ["new", "summer"],
    supplier: {
      code: "SUP-A",
      city: "Hà Nội"
    },
    createdAt: ISODate("2026-11-01T08:00:00Z"),
    version: NumberInt(2)
  }
);

printjson(result);
db.products.findOne({ _id: "sku-100" });
~~~

Dữ liệu được thay thế nguyên document. Không có cơ chế tự động “giữ các field lạ” do một client khác bổ sung, trừ khi bạn đã đọc và đưa chúng vào replacement.

Nếu chỉ muốn sửa giá, `updateOne` thường đơn giản và an toàn hơn:

~~~javascript
db.products.updateOne(
  { _id: "sku-100" },
  {
    $set: { price: NumberDecimal("16.00") }
  }
);
~~~

### 4.2. Thay thế khi replacement không chứa _id

MongoDB cho phép replacement **không nêu `_id`** khi thay document đã tồn tại. Khi đó, `_id` hiện có được giữ:

~~~javascript
db.products.replaceOne(
  { _id: "sku-200" },
  {
    name: "Balo chống nước",
    category: "accessories",
    price: NumberDecimal("39.00"),
    stock: NumberInt(8)
  }
);

db.products.findOne({ _id: "sku-200" });
~~~

Kết quả giữ `_id: "sku-200"`; đồng thời các trường `tags`, `supplier`, `createdAt` và `version` của document cũ bị loại bỏ vì không có trong replacement.

**Không hiểu nhầm:** việc server giữ `_id` không đồng nghĩa nó giữ lại toàn bộ những trường không nhắc đến. `_id` là một ngoại lệ do tính bất biến của khóa định danh.

### 4.3. Thay thế với giá trị _id trùng định danh hiện hữu

Replacement có thể ghi rõ `_id`, miễn là bằng định danh của document cần thay thế:

~~~javascript
db.products.replaceOne(
  { _id: "sku-300" },
  {
    _id: "sku-300",
    name: "Sổ tay bìa cứng",
    category: "stationery",
    price: NumberDecimal("5.00"),
    stock: NumberInt(25)
  }
);
~~~

Khi đó `_id` không thay đổi. Việc khai báo `_id` trong replacement giúp người đọc mã nhận thấy rõ định danh được giữ, nhưng ứng dụng vẫn phải bảo đảm không dùng định danh khác.

## 5. Giới hạn cốt lõi: trường _id là bất biến

### 5.1. Không thể đổi _id bằng replaceOne

MongoDB yêu cầu `_id` của một document **không đổi** trong các thao tác cập nhật hay thay thế. Ví dụ sau được thiết kế để **bị từ chối**:

~~~javascript
db.products.replaceOne(
  { _id: "sku-100" },
  {
    _id: "sku-999", // Sai: _id khác document hiện hữu
    name: "Đổi mã sản phẩm",
    price: NumberDecimal("16.00")
  }
);
~~~

Vì filter chọn document có `_id: "sku-100"`, replacement cố biến khóa thành `"sku-999"`. Server thường trả lỗi kiểu:

~~~text
Performing an update on the path '_id' would modify the immutable field '_id'
~~~

Mã lỗi, cách diễn đạt và cấu trúc phản hồi có thể khác theo phiên bản và driver, nhưng nguyên tắc không đổi: **không được cập nhật `_id` của document hiện có**.

Tương tự, không thể sửa `_id` bằng:

~~~javascript
// Cũng không hợp lệ
db.products.updateOne(
  { _id: "sku-100" },
  { $set: { _id: "sku-999" } }
);
~~~

Và không thể dùng `$unset` để xóa `_id` của document hiện có.

### 5.2. Cùng cách hiển thị nhưng khác kiểu vẫn không phải _id giống nhau

Ví dụ một collection sử dụng BSON ObjectId:

~~~javascript
const oid = ObjectId("64a000000000000000000001");
~~~

Giá trị `oid` (BSON ObjectId) **khác** chuỗi:

~~~javascript
"64a000000000000000000001"
~~~

Một replacement cố đổi từ ObjectId sang chuỗi giống biểu diễn hex không giữ được định danh. Bộ lọc và replacement phải giữ **giá trị BSON _id đúng kiểu**.

Nếu ứng dụng Java/REST nhận ID dạng string rồi tìm document có `_id` là ObjectId, cần parse/kiểm tra đúng kiểu ở tầng API, không giả định MongoDB tự ép chuỗi sang ObjectId.

### 5.3. Đổi mã nghiệp vụ khác với đổi _id

Nếu hệ thống cần thay mã hiển thị của sản phẩm, nên cân nhắc dùng một trường nghiệp vụ riêng:

~~~javascript
{
  _id: ObjectId("64a000000000000000000001"),
  sku: "SKU-OLD",
  name: "Áo thun"
}
~~~

Để đổi mã SKU:

~~~javascript
db.products.updateOne(
  { _id: ObjectId("64a000000000000000000001") },
  { $set: { sku: "SKU-NEW" } }
);
~~~

Ví dụ mang tính minh họa trên document có `_id` dạng ObjectId; bộ dữ liệu `replace_lab.products` ở mục 3 dùng `_id` dạng string nên không khớp truy vấn này.

Nếu `sku` có yêu cầu duy nhất, tạo unique index phù hợp và kiểm soát thay đổi tham chiếu từ hệ thống liên quan. Khi thiết kế mới, nên chọn `_id` ổn định và tách mã nghiệp vụ có thể thay đổi.

### 5.4. Nếu thật sự phải “đổi _id” thì sao?

Không có một `replaceOne` đơn lẻ để đổi `_id` đã tồn tại. Về mặt dữ liệu, điều đó đòi hỏi **tạo một document mới có _id mới**, cập nhật các tham chiếu liên quan và xử lý document cũ theo quy trình migration. Đây là thay đổi identity, có thể tác động đến unique index, liên kết ứng dụng, event, cache và tích hợp ngoài.

Không nên đề xuất xóa document cũ rồi chèn lại như một thao tác sửa trường thông thường: có nguy cơ mất dữ liệu khi lỗi giữa hai bước, gián đoạn tham chiếu hoặc vi phạm quy tắc nghiệp vụ. Nếu thật sự cần di chuyển danh tính, phải thiết kế migration và cơ chế nhất quán phù hợp.

## 6. replaceOne khác updateOne như thế nào?

Xét document hiện hữu:

~~~javascript
{
  _id: "sku-100",
  name: "Áo thun",
  price: NumberDecimal("15.50"),
  stock: NumberInt(12),
  tags: ["new", "summer"],
  supplier: { code: "SUP-A", city: "Hà Nội" }
}
~~~

### 6.1. updateOne với $set

~~~javascript
db.products.updateOne(
  { _id: "sku-100" },
  { $set: { price: NumberDecimal("16.00") } }
);
~~~

Kết quả: chỉ `price` thay đổi; `name`, `stock`, `tags`, `supplier` vẫn tồn tại. Có thể dùng `$inc` để tăng/giảm bộ đếm mà không cần đọc và ghi lại cả document:

~~~javascript
db.products.updateOne(
  { _id: "sku-100" },
  { $inc: { stock: NumberInt(1) } }
);
~~~

### 6.2. replaceOne với replacement

~~~javascript
db.products.replaceOne(
  { _id: "sku-100" },
  {
    name: "Áo thun",
    price: NumberDecimal("16.00")
  }
);
~~~

Kết quả: `stock`, `tags`, `supplier` không còn. Sự khác biệt cốt lõi nằm ở **ý nghĩa của payload**, không phải tên phương thức.

| Tiêu chí | `updateOne` với update operators | `replaceOne` |
|---|---|---|
| Đơn vị thay đổi | Các trường/đường dẫn chỉ định | Toàn bộ nội dung document (trừ `_id` bất biến) |
| Field không nhắc tới | Thường giữ nguyên | Bị loại bỏ |
| Object lồng nhau | Có thể cập nhật đường dẫn như `"supplier.city"` | Phải đưa cả object muốn giữ trong replacement |
| Mảng | Có `$push`, `$pull`, `$addToSet`, ... | Thay toàn bộ giá trị array nếu xuất hiện |
| `_id` | Không thể sửa | Không thể sửa |
| Upsert | Có hỗ trợ | Có hỗ trợ |
| Nên dùng khi | Thay đổi một phần, bộ đếm, thao tác mảng | Ghi lại một snapshot document hoàn chỉnh theo hợp đồng |

### 6.3. Không truyền $set vào replaceOne

Cú pháp sau không phù hợp:

~~~javascript
// Sai: replaceOne không nhận update operator document
db.products.replaceOne(
  { _id: "sku-100" },
  { $set: { price: NumberDecimal("16.00") } }
);
~~~

Tham số thứ hai của `replaceOne` là **replacement document**, không phải update document chứa toán tử `$set`. Server/driver sẽ từ chối một replacement có cấu trúc update operator như vậy.

Dùng:

~~~javascript
// Đúng nếu chỉ sửa một field
db.products.updateOne(
  { _id: "sku-100" },
  { $set: { price: NumberDecimal("16.00") } }
);
~~~

Ngược lại, một update không có toán tử (thế hệ cú pháp cũ) không nên được dùng để thay thế document với mongosh/driver hiện đại; `replaceOne` là API rõ ràng cho mục đích này.

## 7. Replace không gộp dữ liệu lồng nhau và mảng

### 7.1. Object lồng nhau

Giả sử ban đầu:

~~~javascript
{
  _id: "sku-100",
  supplier: {
    code: "SUP-A",
    city: "Hà Nội",
    contact: {
      phone: "0900000000",
      email: "supa@example.test"
    }
  }
}
~~~

Nếu gọi:

~~~javascript
db.products.replaceOne(
  { _id: "sku-100" },
  {
    supplier: {
      city: "Đà Nẵng"
    }
  }
);
~~~

Document sau replacement chỉ còn `_id` và `supplier.city`. Các field `supplier.code`, `supplier.contact` cùng những field cấp gốc khác đều biến mất. `replaceOne` **không merge từng tầng**.

Muốn chỉ thay thành phố mà giữ các field khác:

~~~javascript
db.products.updateOne(
  { _id: "sku-100" },
  { $set: { "supplier.city": "Đà Nẵng" } }
);
~~~

### 7.2. Mảng

Với document có:

~~~javascript
{
  _id: "sku-100",
  tags: ["new", "summer"],
  stock: 12
}
~~~

Nếu replacement chỉ chứa:

~~~javascript
{
  tags: ["featured"]
}
~~~

thì sau replace, mảng `tags` là `["featured"]` và field `stock` bị loại. Không có cơ chế ngầm nối thêm vào mảng cũ.

Nếu mục đích là thêm nhãn mà tránh trùng:

~~~javascript
db.products.updateOne(
  { _id: "sku-100" },
  { $addToSet: { tags: "featured" } }
);
~~~

Nếu mục đích là loại một nhãn:

~~~javascript
db.products.updateOne(
  { _id: "sku-100" },
  { $pull: { tags: "summer" } }
);
~~~

Tùy trường hợp, thay toàn bộ mảng có thể đúng (người dùng gửi danh sách hoàn chỉnh mới), còn thao tác thêm/bớt nên dùng các toán tử update tương ứng.

## 8. Kết quả trả về của replaceOne

`replaceOne` không trả về document đã được thay thế. Nó trả về thông tin về thao tác ghi, thường có:

~~~javascript
{
  acknowledged: true,
  matchedCount: 1,
  modifiedCount: 1,
  upsertedId: null,
  upsertedCount: 0
}
~~~

Các trường và cách hiển thị có thể khác theo driver/phiên bản, nhưng ý nghĩa chính:

| Trường | Ý nghĩa |
|---|---|
| `acknowledged` | Server xác nhận đã nhận/xử lý thao tác theo write concern áp dụng |
| `matchedCount` | Số document khớp điều kiện thay thế; thường là 0 hoặc 1 |
| `modifiedCount` | Số document thực sự được sửa theo kết quả server; thường 0 hoặc 1 |
| `upsertedCount` | Số document được chèn mới bởi upsert, thường 0 hoặc 1 |
| `upsertedId` | `_id` của document mới được chèn khi upsert xảy ra |

Khi write concern không yêu cầu acknowledgment, một số thông tin kết quả không khả dụng; các ví dụ trong bài sử dụng mặc định có xác nhận.

### 8.1. Có document khớp và nội dung thay đổi

~~~javascript
db.products.replaceOne(
  { _id: "sku-300" },
  {
    name: "Sổ tay mới",
    price: NumberDecimal("5.50")
  }
);
~~~

Thông thường `matchedCount: 1` và `modifiedCount: 1`.

### 8.2. Không có document khớp, upsert mặc định là false

~~~javascript
db.products.replaceOne(
  { _id: "sku-does-not-exist" },
  {
    name: "Không được chèn",
    price: NumberDecimal("10.00")
  }
);
~~~

Kết quả thường là `matchedCount: 0`, `modifiedCount: 0`, `upsertedCount: 0`. Phép replace không làm gì nếu không có document khớp và không yêu cầu upsert.

### 8.3. Có document khớp nhưng dữ liệu tương đương

Nếu replacement cho ra document có cùng nội dung như trước, server có thể trả `matchedCount: 1`, `modifiedCount: 0`. Do đó:

- `matchedCount` trả lời “có document nào khớp filter không?”
- `modifiedCount` trả lời “đã sửa nội dung của bao nhiêu document?”

Không coi `modifiedCount: 0` luôn là lỗi. Hãy xem cả `matchedCount`, `upsertedCount` và trạng thái dữ liệu để diễn giải đúng.

## 9. Upsert với replaceOne

### 9.1. Upsert hoạt động như thế nào?

`upsert` là viết tắt của *update or insert*. Với `replaceOne`:

- Nếu filter khớp một document, thay thế document đó.
- Nếu filter không khớp và `upsert: true`, chèn một document mới được tạo từ replacement và quy tắc xử lý `_id`.
- Nếu không khớp và `upsert` không bật, không chèn gì.

Ví dụ:

~~~javascript
const result = db.products.replaceOne(
  { _id: "sku-400" },
  {
    _id: "sku-400",
    name: "Bình nước",
    category: "accessories",
    price: NumberDecimal("12.90"),
    stock: NumberInt(15)
  },
  { upsert: true }
);

printjson(result);
db.products.findOne({ _id: "sku-400" });
~~~

Nếu chưa có `sku-400`, kết quả thường có `matchedCount: 0`, `upsertedCount: 1` và `upsertedId: "sku-400"`. Chạy lại với cùng filter thì document `sku-400` đã tồn tại; lệnh thực hiện replacement thay vì tạo document thứ hai.

### 9.2. Replacement thiếu _id khi upsert

Khi replacement không khai báo `_id` và thao tác upsert cần chèn mới, MongoDB phải có `_id` cho document mới. Với filter chứa điều kiện bằng trực tiếp trên `_id`, định danh có thể được lấy từ điều kiện đó:

~~~javascript
db.products.replaceOne(
  { _id: "sku-500" },
  {
    name: "Hộp bút",
    price: NumberDecimal("7.20")
  },
  { upsert: true }
);

db.products.findOne({ _id: "sku-500" });
~~~

Một cách viết rõ ràng, dễ đối chiếu và tránh nhập nhằng hơn là **đặt `_id` mong muốn vào cả filter và replacement** như ví dụ `sku-400`.

Nếu upsert chèn document mà không có `_id` rõ ràng, server sẽ tạo định danh theo quy tắc MongoDB áp dụng. Đừng suy luận rằng mọi field bất kỳ trong filter chắc chắn được sao chép vào replacement. Khi dùng replacement, hãy đưa các field nghiệp vụ bắt buộc vào chính replacement.

### 9.3. Filter không đủ chính xác khi upsert

Giả sử ứng dụng dùng:

~~~javascript
db.products.replaceOne(
  { category: "fashion" },
  {
    name: "Sản phẩm mới",
    category: "fashion",
    price: NumberDecimal("10.00")
  },
  { upsert: true }
);
~~~

Nếu đã có bất kỳ sản phẩm `category: "fashion"`, lệnh có thể **thay một sản phẩm hiện hữu** thay vì chèn sản phẩm mới. Nếu không có, nó có thể chèn một sản phẩm. Một filter quá rộng dẫn đến hai kết quả rất khác nhau.

Với upsert mang ý nghĩa “lưu sản phẩm theo mã duy nhất”, nên dùng `_id` hoặc unique business key, đồng thời bảo đảm unique index phù hợp.

### 9.4. Upsert cạnh tranh giữa nhiều tiến trình

Nếu hai luồng cùng chạy upsert trên một khóa chưa tồn tại, cả hai có thể cùng nhận thấy chưa có document. Để ngăn bản ghi trùng, cần unique index trên khóa nghiệp vụ phù hợp, xử lý khả năng lỗi duplicate key và thiết kế retry có kiểm soát.

`upsert: true` không tự biến mọi filter nghiệp vụ thành một khóa unique. Mặc định, MongoDB có unique index trên `_id` của collection thông thường; với khóa khác phải thiết kế index phù hợp.

## 10. Giới hạn và điều kiện của replacement document

### 10.1. Replacement phải là document hoàn chỉnh hợp lệ

Replacement không phải tập các operator như `$set`/`$inc`. Nó phải chứa cấu trúc BSON hợp lệ và phù hợp schema ứng dụng.

Nếu collection có validator yêu cầu `name`, `price`, `stock`, một replacement thiếu `stock` có thể bị từ chối nếu `validationAction: "error"`. Điều này có lợi vì ngăn replace vô tình làm mất trường bắt buộc, nhưng validator chỉ bảo vệ những trường/quy tắc được khai báo.

### 10.2. Giới hạn kích thước document

MongoDB có giới hạn kích thước BSON document tối đa **16 MiB** đối với document thông thường. Một replacement khổng lồ, chẳng hạn chứa mảng rất lớn, có thể bị từ chối vì vượt kích thước này.

Nếu một document cứ tăng mãi theo số dòng lịch sử hoặc số phần tử mảng, nên cân nhắc mô hình collection con và liên kết bằng khóa, thay vì cố đưa mọi thứ vào cùng một document.

### 10.3. Quy tắc trường bất biến khác trong cấu hình đặc biệt

Ngoài `_id`, cách thay thế còn phụ thuộc cấu hình collection, chẳng hạn sharding và shard key, time series hoặc collection có giới hạn/cơ chế riêng. Các quy tắc cụ thể về quyền thay đổi shard key, routing và loại collection có thể phụ thuộc phiên bản MongoDB và topology.

Vì vậy, không nên suy rộng rằng “chỉ `_id` là giới hạn duy nhất”. Khi thao tác trên sharded collection hoặc collection đặc biệt, cần xem ràng buộc phù hợp với môi trường thực tế.

### 10.4. Validation và quyền truy cập

Một tài khoản cần quyền ghi thích hợp cho thao tác replacement; upsert có thể cần quyền chèn khi phát sinh document mới. Nếu server từ chối vì `not authorized`, đừng xem đó là lỗi filter hay lỗi `_id`.

Khi collection có JSON Schema validation, replacement phải đáp ứng validator. Tùy quyền và công cụ, có thể tồn tại cơ chế bỏ qua document validation cho thao tác quản trị đặc biệt, nhưng không nên sử dụng như cách mặc định để “sửa lỗi” schema.

### 10.5. Index và tính duy nhất

Replacement được kiểm tra đối với các ràng buộc index liên quan. Giữ nguyên `_id` chưa chắc bảo đảm toàn bộ replacement hợp lệ: ví dụ sửa một trường email sang email đã tồn tại có thể vi phạm unique index trên email.

Do vậy, lỗi duplicate key, lỗi document validation và lỗi immutable `_id` là những nhóm lỗi khác nhau, cần phân biệt khi xử lý ở application layer.

## 11. Filter và câu chuyện “thay document nào?”

### 11.1. Không dùng filter rộng khi cần một bản ghi xác định

~~~javascript
// Có thể khớp nhiều sản phẩm trong cùng danh mục
db.products.replaceOne(
  { category: "fashion" },
  { name: "Bản ghi thay thế" }
);
~~~

Dù `replaceOne` chỉ thay **một** document, điều đó không có nghĩa document được chọn là ổn định hay đúng với ý định nghiệp vụ. Trên dữ liệu thường xuyên thay đổi, filter rộng càng dễ gây sai.

Nên có tiêu chí định danh cụ thể:

~~~javascript
db.products.replaceOne(
  { _id: "sku-100" },
  {
    _id: "sku-100",
    name: "Áo thun basic",
    category: "fashion",
    price: NumberDecimal("16.00"),
    stock: NumberInt(12)
  }
);
~~~

### 11.2. Filter có thể kết hợp _id và điều kiện nghiệp vụ

~~~javascript
db.products.replaceOne(
  {
    _id: "sku-100",
    category: "fashion"
  },
  {
    _id: "sku-100",
    name: "Áo thun mới",
    category: "fashion",
    price: NumberDecimal("17.00"),
    stock: NumberInt(9)
  }
);
~~~

Nếu `_id` đúng nhưng `category` trên server đã đổi, lệnh không khớp document nào. Kết quả `matchedCount: 0` có thể chỉ ra bản ghi bị xóa, thay đổi trạng thái hoặc filter không còn đúng.

Các field của filter **không tự được giữ lại** sau replacement: nếu replacement bỏ `category`, field đó biến mất ngay cả khi filter dùng `category` để tìm.

### 11.3. Kiểm tra phạm vi trước khi ghi

~~~javascript
const filter = { _id: "sku-100" };

db.products.findOne(filter);
db.products.countDocuments(filter);
~~~

Khi filter theo unique `_id`, nhiều nhất một document được chọn. Đối với filter phức tạp hơn, nên có unique index hoặc thiết kế khóa nghiệp vụ rõ.

Trên môi trường có nhiều tiến trình ghi đồng thời, việc đọc trước chỉ giúp quan sát; nó không “khóa” document trong khoảng thời gian giữa read và replace.

## 12. Tránh mất cập nhật do đọc rồi thay toàn bộ

### 12.1. Lost update là gì?

Giả sử ban đầu:

~~~javascript
{
  _id: "sku-100",
  name: "Áo thun",
  stock: 12,
  price: 15.50
}
~~~

Diễn biến:

~~~text
T0: Client A đọc document (stock = 12)
T1: Client B tăng stock lên 13 bằng $inc
T2: Client A dùng replaceOne với snapshot cũ (stock = 12)
T3: Kết quả stock quay về 12, thay đổi của B bị ghi đè
~~~

Một lệnh `replaceOne` là thao tác ghi **atomic ở phạm vi một document** nhưng không tự bảo đảm mọi field trong snapshot của client còn mới. Tính atomic không ngăn lost update giữa hai lần ghi hợp lệ liên tiếp.

### 12.2. Chỉ cập nhật trường cần sửa bằng updateOne

Nếu client A chỉ muốn đổi tên:

~~~javascript
db.products.updateOne(
  { _id: "sku-100" },
  { $set: { name: "Áo thun basic" } }
);
~~~

Thao tác này không ghi đè `stock` mà client B đang thay đổi. Với các bộ đếm, dùng `$inc` thay vì đọc giá trị rồi gửi số mới.

### 12.3. Optimistic concurrency bằng version

Khi bắt buộc thay cả document, có thể dùng **version** để phát hiện snapshot cũ. Mọi luồng ghi cần thống nhất cập nhật version.

Ví dụ sau giả định document có trường `version` dạng số nguyên:

~~~javascript
const current = db.products.findOne({ _id: "sku-100" });

if (current) {
  const next = {
    ...current,
    name: "Áo thun basic phiên bản mới",
    version: NumberInt(Number(current.version) + 1)
  };

  const result = db.products.replaceOne(
    {
      _id: current._id,
      version: current.version
    },
    next
  );

  if (result.matchedCount === 0) {
    print("Document đã thay đổi hoặc không còn tồn tại. Cần tải lại.");
  } else {
    print("Thay thế thành công.");
  }
}
~~~

Nếu client khác đã cập nhật `version` từ 1 lên 2 trước khi lệnh replacement chạy, filter với `version: 1` không còn khớp và client nhận `matchedCount: 0` thay vì âm thầm ghi đè.

Điều kiện để cơ chế này hiệu quả: **mọi đường ghi liên quan đều phải tăng version**. Nếu có luồng thay `stock` mà không tăng `version`, snapshot cũ vẫn có thể ghi đè thay đổi của luồng đó.

### 12.4. Không tự động retry khi filter version không khớp

Một lệnh replacement bị từ chối do xung đột version không nên được retry mù quáng với cùng snapshot. Cần tải dữ liệu mới, đối chiếu ý định người dùng và quyết định merge/retry theo nghiệp vụ.

## 13. replaceOne và schema validation

Một JSON Schema validator có thể hạn chế nguy cơ vô tình làm rơi trường bắt buộc khi thay document.

Ví dụ tạo collection riêng:

~~~javascript
use replace_lab

if (db.getCollectionInfos({ name: "validatedProducts" }).length === 0) {
  db.createCollection("validatedProducts", {
    validator: {
      $jsonSchema: {
        bsonType: "object",
        required: ["name", "price", "stock"],
        properties: {
          _id: { bsonType: ["string", "objectId"] },
          name: { bsonType: "string", minLength: 1 },
          price: {
            bsonType: "decimal",
            minimum: NumberDecimal("0")
          },
          stock: {
            bsonType: "int",
            minimum: 0
          }
        }
      }
    },
    validationLevel: "strict",
    validationAction: "error"
  });
}
~~~

Chèn document hợp lệ:

~~~javascript
db.validatedProducts.replaceOne(
  { _id: "valid-001" },
  {
    _id: "valid-001",
    name: "Bút bi",
    price: NumberDecimal("1.50"),
    stock: NumberInt(20)
  },
  { upsert: true }
);
~~~

Thử replacement thiếu `stock`:

~~~javascript
// Dự kiến bị từ chối vì thiếu trường bắt buộc
db.validatedProducts.replaceOne(
  { _id: "valid-001" },
  {
    name: "Bút bi xanh",
    price: NumberDecimal("1.80")
  }
);
~~~

Khi `validationAction: "error"` đang bật, server từ chối replacement không hợp lệ. Document cũ không bị thay thành bản thiếu `stock`.

Schema validation còn có thể giới hạn field, kiểu BSON, mảng và object lồng nhau. Tuy nhiên, nó chỉ kiểm tra các quy tắc đã định nghĩa. Nếu schema không bắt buộc `tags`, phép replacement bỏ mất `tags` vẫn có thể hợp lệ về mặt schema.

### 13.1. Vì sao Decimal128 quan trọng ở đây?

Khi replacement đến từ JSON của API, trường `price` có thể là Double, trong khi validator yêu cầu BSON `decimal`. Khi ghi qua `mongosh`, dùng:

~~~javascript
NumberDecimal("19.90")
~~~

Trong Java, có thể sử dụng `BigDecimal` và `Decimal128`. Không giả định việc biểu diễn `19.90` như JSON number sẽ tự biến thành Decimal128.

## 14. replaceOne trong MongoDB Compass

MongoDB Compass chủ yếu cung cấp giao diện để **xem và sửa document**. Tùy phiên bản, thao tác Edit Document có thể cho chỉnh toàn bộ JSON/Tree và lưu, nhưng cơ chế lưu cụ thể của giao diện không nên được giả định là luôn phát lệnh `replaceOne`.

Để học chính xác semantics của `replaceOne`, chạy ví dụ trong `mongosh` rồi quan sát thay đổi bằng Compass:

1. Kết nối Compass đến server đã dùng trong `mongosh` và mở `replace_lab.products`.
2. Lọc bằng `{"_id":"sku-100"}`; quan sát các trường `name`, `price`, `stock`, `tags`, `supplier`.
3. Chạy lệnh `replaceOne` từ mục 4.2 hoặc một replacement có chủ đích trên một document mẫu.
4. Quay lại Compass, Refresh/Find để xem những field không có trong replacement đã biến mất.
5. Chạy lệnh thử đổi `_id` ở mục 5.1 trong mongosh. Quan sát lỗi, sau đó Refresh Compass để xác nhận định danh cũ vẫn tồn tại.
6. Thử upsert `sku-400` ở mục 9; Refresh danh sách document để kiểm tra bản ghi mới được chèn.
7. Nếu Compass hỗ trợ xem kiểu BSON, đối chiếu trường `price` là Decimal128 khi dùng `NumberDecimal`.

Khi nhập biểu thức filter vào Compass, dùng JSON hợp lệ:

~~~json
{"_id":"sku-100"}
~~~

Nếu đang chỉnh sửa document trực tiếp trong Compass, cần phân biệt thao tác **sửa field**, **xóa field** và **thay toàn bộ document** theo giao diện phiên bản đó. Tác động sau cùng luôn phải kiểm chứng bằng dữ liệu server.

## 15. Dùng replaceOne với MongoDB Java Driver

Java Driver có `replaceOne(filter, replacement)` và các tùy chọn qua `ReplaceOptions`. Ví dụ dùng `Document`:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import com.mongodb.client.model.ReplaceOptions;
import org.bson.Document;
import org.bson.types.Decimal128;

import java.math.BigDecimal;

MongoCollection<Document> products = database.getCollection("products");

Document replacement = new Document("_id", "sku-100")
    .append("name", "Áo thun basic")
    .append("category", "fashion")
    .append("price", new Decimal128(new BigDecimal("16.00")))
    .append("stock", 12);

UpdateResult result = products.replaceOne(
    new Document("_id", "sku-100"),
    replacement,
    new ReplaceOptions().upsert(false)
);

System.out.println("Matched: " + result.getMatchedCount());
System.out.println("Modified: " + result.getModifiedCount());
~~~

Đoạn mã giả định biến `database` là một `MongoDatabase` đã kết nối và có quyền ghi; nó minh họa API, không phải chương trình Java độc lập hoàn chỉnh.

Tham số `replacement` có thể là một POJO được codec/ODM quản lý thay vì `Document`. Khi dùng POJO, cần chú ý mapper bỏ các field `null`/không được load hoặc định nghĩa `_id` không nhất quán, vì replacement có thể làm mất các field mà tầng Java không chứa trong object.

Ví dụ upsert bằng driver:

~~~java
UpdateResult result = products.replaceOne(
    new Document("_id", "sku-600"),
    new Document("_id", "sku-600")
        .append("name", "Hộp đựng tài liệu")
        .append("price", new Decimal128(new BigDecimal("9.90")))
        .append("stock", 3),
    new ReplaceOptions().upsert(true)
);

if (result.getUpsertedId() != null) {
    System.out.println("Created: " + result.getUpsertedId());
}
~~~

Ứng dụng nên xử lý riêng các tình huống không có document khớp, xung đột version, lỗi validation, lỗi trùng unique key và lỗi mạng/timeout. Với các trường nghiệp vụ dễ thay đổi độc lập, `updateOne` cùng update operator thường giúp giảm rủi ro ghi đè.

## 16. Khi nào nên dùng findOneAndReplace?

`replaceOne` trả về **kết quả ghi**, không trả về document trước/sau. Nếu ứng dụng cần nhận document, MongoDB có API `findOneAndReplace` với tùy chọn trả về trước hoặc sau thay thế.

Ví dụ trong `mongosh`:

~~~javascript
const updated = db.products.findOneAndReplace(
  { _id: "sku-300" },
  {
    _id: "sku-300",
    name: "Sổ tay bìa da",
    price: NumberDecimal("6.50"),
    stock: NumberInt(10)
  },
  {
    returnDocument: "after"
  }
);

printjson(updated);
~~~

Nếu cần cả dữ liệu cũ và mới để ghi audit, nên thiết kế quy trình audit/event phù hợp thay vì giả định mọi API luôn trả cả hai. `findOneAndReplace` không thay đổi quy tắc `_id` bất biến hoặc bản chất thay thế toàn document.

| Phương thức | Mục đích | Kết quả thường thấy |
|---|---|---|
| `updateOne` | Cập nhật một document bằng operator/pipeline hợp lệ | Thông tin thao tác ghi |
| `replaceOne` | Thay nội dung một document | Thông tin thao tác ghi |
| `findOneAndReplace` | Thay một document và nhận document theo tùy chọn | Document trước hoặc sau, hoặc null nếu không khớp |
| `updateMany` | Cập nhật nhiều document | Thông tin số lượng khớp/sửa |
| `insertOne` | Chèn một document mới | ID của document được chèn |

Không có `replaceMany` tương đương để dùng một replacement document nhằm thay toàn bộ nhiều document. Khi cần di chuyển dữ liệu hàng loạt, phải xác định mục tiêu, phương án update/bulkWrite và kiểm soát tác động riêng.

## 17. Các lỗi thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| `_id` khác sau replacement | Cố thay khóa bất biến | Giữ đúng `_id` hiện có hoặc bỏ `_id` trong replacement matched |
| `_id` cùng dạng chuỗi nhưng không khớp ObjectId | Khác kiểu BSON | Parse/giữ đúng kiểu định danh |
| Document mất nhiều field sau replace | Replacement không bao gồm field đó | Cung cấp snapshot đầy đủ hoặc dùng `updateOne` |
| Có field lồng nhau mất sau replace | Replacement không merge object | Dùng `$set` với dot notation khi chỉ đổi một nhánh |
| Mảng bị thay hết | Replacement thay giá trị mảng hoàn chỉnh | Dùng `$push`/`$pull`/`$addToSet` nếu thao tác từng phần |
| Truyền `{$set:{...}}` cho `replaceOne` | Sai định dạng replacement | Dùng `updateOne` hoặc document thay thế hợp lệ |
| `matchedCount = 0` | Filter không khớp hoặc document đã thay đổi | Kiểm tra ID, kiểu BSON, version và trạng thái dữ liệu |
| `modifiedCount = 0` dù matched = 1 | Replacement có thể tương đương document hiện hữu | Xem cả result và document thực |
| Chèn document ngoài ý định | Bật `upsert: true` và filter không khớp | Kiểm soát filter, khóa unique và lựa chọn upsert |
| Thay nhầm một sản phẩm | Filter quá rộng khớp nhiều bản ghi | Dùng khóa định danh/unique key |
| Lỗi duplicate key | Upsert cạnh tranh hoặc replacement vi phạm unique index | Kiểm tra unique key, xử lý lỗi và retry có điều kiện |
| Lỗi schema validation | Replacement thiếu field hoặc sai BSON type | Đưa đủ field hợp lệ, không bỏ qua validator tùy tiện |
| Bản ghi mất thay đổi đồng thời | Client thay bằng snapshot cũ | Dùng update operator hoặc optimistic version |
| Lỗi document quá lớn | BSON vượt giới hạn | Thiết kế lại dữ liệu/mảng hoặc tách collection |

## 18. Bài tập thực hành

Thực hiện lần lượt trong database `replace_lab`. Để đảm bảo kết quả độc lập, có thể nạp lại `seedProducts` ở mục 3 khi muốn đưa bộ dữ liệu mẫu về trạng thái ban đầu.

### Bài 1. Quan sát thay thế toàn document

Trước khi thay:

~~~javascript
db.products.findOne({ _id: "sku-100" });
~~~

Thay thế:

~~~javascript
db.products.replaceOne(
  { _id: "sku-100" },
  {
    name: "Áo thun tối giản",
    price: NumberDecimal("18.00")
  }
);
~~~

Đọc lại:

~~~javascript
db.products.findOne({ _id: "sku-100" });
~~~

**Cần giải thích:** Vì sao `_id` còn tồn tại, nhưng `stock`, `tags`, `supplier` và `createdAt` bị mất?

### Bài 2. Thay đổi _id không hợp lệ

~~~javascript
db.products.replaceOne(
  { _id: "sku-100" },
  {
    _id: "sku-100-new",
    name: "Thử đổi ID"
  }
);
~~~

**Kỳ vọng:** Lỗi do `_id` bất biến. Kiểm tra document `sku-100` trước và sau thao tác để xác nhận không đổi định danh.

### Bài 3. Matched và modified

Chạy một replacement với cùng dữ liệu hai lần:

~~~javascript
const p = {
  _id: "sku-300",
  name: "Sổ tay",
  price: NumberDecimal("5.50"),
  stock: NumberInt(25)
};

printjson(db.products.replaceOne({ _id: "sku-300" }, p));
printjson(db.products.replaceOne({ _id: "sku-300" }, p));
~~~

**Cần quan sát:** Có thể thấy lần đầu `modifiedCount: 1` (nếu nội dung khác), lần thứ hai `modifiedCount: 0` khi replacement giống trạng thái hiện tại; `matchedCount` vẫn là 1.

### Bài 4. Không khớp và upsert

~~~javascript
db.products.replaceOne(
  { _id: "sku-700" },
  {
    _id: "sku-700",
    name: "Bìa hồ sơ",
    price: NumberDecimal("3.00")
  }
);
~~~

Khi chưa có `sku-700`, lệnh không chèn. Tiếp tục:

~~~javascript
db.products.replaceOne(
  { _id: "sku-700" },
  {
    _id: "sku-700",
    name: "Bìa hồ sơ",
    price: NumberDecimal("3.00")
  },
  { upsert: true }
);
~~~

**Kỳ vọng:** Lần sau có `upsertedCount: 1` nếu bản ghi chưa tồn tại. Chạy lại sẽ thành replacement.

### Bài 5. So sánh replaceOne và updateOne

Nạp lại dữ liệu mẫu rồi thử:

~~~javascript
db.products.updateOne(
  { _id: "sku-200" },
  { $set: { "supplier.city": "TP. Hồ Chí Minh" } }
);
~~~

Đọc lại field `supplier.code`. Tiếp tục nạp lại mẫu rồi thử:

~~~javascript
db.products.replaceOne(
  { _id: "sku-200" },
  {
    supplier: { city: "TP. Hồ Chí Minh" }
  }
);
~~~

**Cần giải thích:** Vì sao lần thứ hai chỉ còn `_id` và `supplier.city`?

### Bài 6. Optimistic concurrency

Nạp lại mẫu, đọc `sku-100` vào biến `current`, sau đó giả lập một tiến trình khác sửa version:

~~~javascript
const current = db.products.findOne({ _id: "sku-100" });

db.products.updateOne(
  { _id: "sku-100" },
  { $inc: { version: NumberInt(1) } }
);

const result = db.products.replaceOne(
  { _id: "sku-100", version: current.version },
  {
    ...current,
    name: "Snapshot cũ",
    version: NumberInt(Number(current.version) + 1)
  }
);

printjson(result);
~~~

**Kỳ vọng:** `matchedCount: 0` vì version trên server đã thay đổi. Không retry mù quáng; phải đọc lại trước khi quyết định thay.

### Bài 7. Validator chặn replacement thiếu trường

Tạo `validatedProducts` theo mục 13, chèn `valid-001` rồi thử replacement không có `stock`.

**Kỳ vọng:** Khi strict/error, lệnh bị từ chối. So sánh lỗi này với lỗi immutable `_id` và lỗi duplicate key để phân biệt cơ chế.

### Bài 8. Chọn phương thức theo yêu cầu

| Yêu cầu | Lựa chọn thích hợp |
|---|---|
| Sửa duy nhất giá bán | `updateOne` + `$set` |
| Tăng tồn kho khi nhận hàng | `updateOne` + `$inc` |
| Thêm nhãn vào array không trùng | `updateOne` + `$addToSet` |
| Ghi lại một snapshot sản phẩm đã được kiểm soát đầy đủ | `replaceOne` |
| Lưu snapshot theo ID, tạo nếu chưa có | `replaceOne` + `upsert: true` |
| Muốn lấy document mới ngay sau thay | `findOneAndReplace` với return-after |
| Đổi `_id` của document hiện có | Không hỗ trợ qua `replaceOne` |
| Thay một document nhưng phải tránh ghi đè snapshot cũ | `replaceOne` với filter version và protocol tăng version |

## 19. Quy tắc thực hành khi dùng replaceOne

Trước khi gửi một replacement, hãy tự xác định **document nào được chọn**, **payload có đầy đủ những trường cần giữ hay không**, và **`_id` có đúng định danh BSON của document hiện tại không**. Bảo đảm thêm rằng loại thao tác được yêu cầu là thay thế toàn document, thay vì một cập nhật từng trường.

Khi bật upsert, kiểm tra kỹ bộ lọc và unique key. Khi hệ thống có nhiều luồng ghi, ưu tiên toán tử cập nhật từng field; nếu bắt buộc replace snapshot, sử dụng cơ chế phát hiện xung đột như version. Kết hợp schema validation để chặn những replacement thiếu dữ liệu bắt buộc, đồng thời quan sát kết quả `matchedCount`, `modifiedCount` và `upsertedId`.

`replaceOne()` là công cụ hữu ích khi ý định nghiệp vụ thực sự là **định nghĩa lại nội dung của một document**. Hiểu rõ giới hạn toàn document và tính bất biến của `_id` giúp dùng công cụ này mà không làm mất trường hoặc đổi nhầm danh tính của dữ liệu.

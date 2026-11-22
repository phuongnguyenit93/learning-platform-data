# `findOneAndUpdate`, `findOneAndReplace` và lựa chọn document trả về trong MongoDB

Khi ứng dụng cập nhật một document trong MongoDB, đôi khi chỉ cần biết thao tác có thành công hay không. Nhưng cũng có lúc ứng dụng cần **lấy chính document trước hoặc sau khi thay đổi**: chẳng hạn trả về đơn hàng vừa chuyển trạng thái, kiểm tra giá trị cũ trước khi ghi nhận lịch sử, hoặc chọn một tác vụ đang chờ để giao cho worker xử lý.

MongoDB có hai phương thức phù hợp với trường hợp tìm, thay đổi và nhận lại một document:

- **`findOneAndUpdate()`**: tìm một document rồi **cập nhật** các field được chỉ định bằng toán tử như `$set`, `$inc`, `$unset`, `$push`, hoặc bằng update pipeline khi được hỗ trợ.
- **`findOneAndReplace()`**: tìm một document rồi **thay thế nội dung document** bằng một replacement document mới, vẫn tôn trọng quy tắc về trường `_id`.

Cả hai thường trả về **document trước khi thay đổi** theo mặc định. Nếu muốn nhận bản **sau khi thay đổi**, cấu hình `returnDocument: "after"`. Đây là điểm quan trọng nhất để đọc kết quả đúng.

Bài học hướng dẫn cú pháp trong `mongosh`, các tình huống truy vấn, cập nhật, `upsert`, chọn document bằng `sort`, trả về một phần field bằng `projection`, ví dụ Java MongoDB Sync Driver và cách tránh mất dữ liệu khi thay thế document.

## 1. Vị trí của hai phương thức trong nhóm thao tác cập nhật

Trước tiên, cần phân biệt bốn phương thức thường gặp:

| Phương thức | Tác động lên dữ liệu | Giá trị trả về thường dùng | Khi nào nên dùng? |
| --- | --- | --- | --- |
| `updateOne(filter, update)` | Cập nhật một document | Thông tin kết quả như `matchedCount`, `modifiedCount`, `upsertedId` | Chỉ cần biết có bao nhiêu document khớp hoặc được sửa |
| `replaceOne(filter, replacement)` | Thay thế một document | Thông tin kết quả cập nhật | Muốn thay toàn bộ nội dung nhưng không cần document trả về |
| `findOneAndUpdate(filter, update, options)` | Tìm và cập nhật một document | Document trước/sau, hoặc `null` khi không có bản để trả | Cần chính document liên quan đến thao tác cập nhật |
| `findOneAndReplace(filter, replacement, options)` | Tìm và thay một document | Document trước/sau, hoặc `null` khi không có bản để trả | Cần document liên quan đến thao tác thay thế |

Tên `findOneAnd...` nhấn mạnh việc **tìm và thực hiện thao tác sửa đổi trên một document, đồng thời có thể lấy ảnh của document đó**. Chúng không phải tổ hợp hai câu lệnh phía ứng dụng như:

```javascript
// Hai thao tác độc lập: có khoảng thời gian giữa đọc và cập nhật
const oldOrder = db.orders.findOne({ _id: "ord-101" });
db.orders.updateOne(
  { _id: "ord-101" },
  { $set: { status: "paid" } }
);
```

Giữa `findOne()` và `updateOne()`, một ứng dụng khác có thể đã sửa document. `findOneAndUpdate()` giúp thực hiện việc tìm và sửa **một document** như một thao tác đơn lẻ có tính nguyên tử ở cấp document, với điều kiện và ảnh document trả về gắn với thao tác đó.

Sơ đồ khái quát:

```text
filter + update/replacement + options
                   |
                   v
            Tìm document khớp
                   |
         +---------+----------+
         |                    |
     Có document           Không khớp
         |                    |
    Sửa hoặc thay         upsert?
         |              /           \
         |           false          true
         |             |              |
         v            không          tạo mới
    Lựa chọn ảnh       cập nhật          |
   trước / sau          |               |
         +--------------+---------------+
                        |
            Trả về document hoặc null
```

**Phạm vi nguyên tử:** một document. Nếu nghiệp vụ yêu cầu cập nhật nhiều document hoặc nhiều collection như một đơn vị, chỉ dùng `findOneAndUpdate()` không tự tạo ra một giao dịch đa document.

## 2. Dữ liệu thực hành

Chọn database riêng trong `mongosh`:

```javascript
use mongo_update_lab
```

Tạo collection `orders` bằng bộ dữ liệu minh họa:

```javascript
db.orders.insertMany([
  {
    _id: "ord-101",
    customerId: "u101",
    status: "pending",
    total: 150,
    priority: 2,
    shipping: {
      city: "Hà Nội",
      method: "standard"
    },
    items: [
      { sku: "P-1", qty: 2 },
      { sku: "P-2", qty: 1 }
    ]
  },
  {
    _id: "ord-102",
    customerId: "u101",
    status: "pending",
    total: 90,
    priority: 1,
    shipping: {
      city: "Huế",
      method: "express"
    },
    items: [
      { sku: "P-3", qty: 1 }
    ]
  },
  {
    _id: "ord-103",
    customerId: "u102",
    status: "paid",
    total: 220,
    priority: 3,
    shipping: {
      city: "Đà Nẵng",
      method: "standard"
    },
    items: [
      { sku: "P-4", qty: 2 }
    ]
  }
])
```

Các lệnh trong bài có tác dụng **sửa dữ liệu**, nên kết quả ví dụ giả định bắt đầu từ bộ dữ liệu trên. Nếu chạy nhiều ví dụ nối tiếp, trạng thái document sẽ thay đổi; hãy đọc trạng thái hiện tại bằng `findOne()` hoặc sử dụng một bản dữ liệu lab riêng cho từng ví dụ. Không xóa collection đang chứa dữ liệu thực chỉ để chạy lại bài.

## 3. `findOneAndUpdate()`: cập nhật một phần document

### 3.1. Cú pháp tổng quát

```javascript
db.collection.findOneAndUpdate(
  filter,
  update,
  options
)
```

Trong đó:

- **`filter`**: điều kiện để tìm document, giống bộ lọc `find()`.
- **`update`**: tài liệu chứa các update operators (`$set`, `$inc`, v.v.) hoặc update pipeline được hỗ trợ.
- **`options`**: chọn ảnh trước/sau, `sort`, `projection`, `upsert`, `arrayFilters` và các tùy chọn tương thích với phiên bản.

Ví dụ: chuyển một đơn hàng từ `pending` sang `paid` và ghi thời điểm cập nhật:

```javascript
db.orders.findOneAndUpdate(
  { _id: "ord-101", status: "pending" },
  {
    $set: { status: "paid" },
    $currentDate: { updatedAt: true }
  }
)
```

Nếu bộ dữ liệu ban đầu chưa bị thay đổi, document `ord-101` khớp bộ lọc. MongoDB cập nhật `status` và `updatedAt`, nhưng do không cấu hình lựa chọn trả về, giá trị nhận được là **bản trước khi cập nhật**:

```javascript
{
  _id: "ord-101",
  customerId: "u101",
  status: "pending",
  total: 150,
  priority: 2,
  shipping: { city: "Hà Nội", method: "standard" },
  items: [
    { sku: "P-1", qty: 2 },
    { sku: "P-2", qty: 1 }
  ]
}
```

Document trả về còn `status: "pending"` **không có nghĩa cập nhật thất bại**. Đây là ảnh *before*; kiểm tra bản đang lưu:

```javascript
db.orders.findOne({ _id: "ord-101" })
```

Kết quả lưu trữ lúc này có `status: "paid"` và field `updatedAt` kiểu Date.

### 3.2. Trả về document sau khi cập nhật

Muốn nhận ngay document mới, dùng `returnDocument: "after"`:

```javascript
db.orders.findOneAndUpdate(
  { _id: "ord-102", status: "pending" },
  {
    $set: {
      status: "packed",
      "shipping.method": "priority"
    },
    $currentDate: { updatedAt: true }
  },
  { returnDocument: "after" }
)
```

Khi bộ lọc khớp, document trả về có `status: "packed"`, `shipping.method: "priority"` và thời gian `updatedAt` vừa được máy chủ đặt. Các field khác của document như `total`, `priority` và `items` vẫn còn.

Nguyên nhân là `findOneAndUpdate()` với `$set` chỉ sửa các đường dẫn được chỉ định; nó không thay thế toàn bộ document.

### 3.3. `returnDocument`: hai lựa chọn cốt lõi

| Cấu hình | Ý nghĩa | Document trả về khi có bản khớp |
| --- | --- | --- |
| Không chỉ rõ | Mặc định như `"before"` | Ảnh document **trước** thao tác |
| `returnDocument: "before"` | Chỉ định tường minh ảnh trước | Ảnh **trước** thao tác |
| `returnDocument: "after"` | Yêu cầu ảnh sau | Ảnh **sau** thao tác |

```javascript
// Bản trước cập nhật
db.orders.findOneAndUpdate(
  { _id: "ord-101" },
  { $inc: { total: 10 } },
  { returnDocument: "before" }
)

// Bản sau cập nhật
db.orders.findOneAndUpdate(
  { _id: "ord-102" },
  { $inc: { total: 10 } },
  { returnDocument: "after" }
)
```

Hai lệnh độc lập ở trên cố ý sửa hai document khác nhau để dễ quan sát. `$inc` tăng giá trị số hiện tại; nếu dùng lại lệnh trên cùng document, `total` tiếp tục tăng. Không nên chạy lặp lại các phép cộng/trừ như thể chúng là phép cập nhật idempotent.

Ký hiệu `returnDocument` trong API `mongosh` là chuỗi **`"before"`** hoặc **`"after"`**. Một số phiên bản shell/driver cũ có các tùy chọn như `returnNewDocument` hoặc `new`; khi viết code mới nên sử dụng API được tài liệu phiên bản hiện hành hỗ trợ và không trộn tên tùy chọn giữa các driver.

## 4. Cách dùng update operators đúng mục đích

Toán tử cập nhật cho phép thao tác chính xác với field:

| Toán tử | Công dụng | Ví dụ |
| --- | --- | --- |
| `$set` | Gán giá trị cho field hoặc đường dẫn lồng nhau | `{ $set: { status: "paid" } }` |
| `$unset` | Xóa field khỏi document | `{ $unset: { temporaryNote: "" } }` |
| `$inc` | Cộng thêm một lượng số | `{ $inc: { total: 5 } }` |
| `$currentDate` | Gán ngày/giờ hiện tại cho field | `{ $currentDate: { updatedAt: true } }` |
| `$push` | Thêm phần tử vào array | `{ $push: { auditTags: "reviewed" } }` |
| `$addToSet` | Thêm giá trị vào array nếu chưa có giá trị tương đương | `{ $addToSet: { auditTags: "reviewed" } }` |
| `$pull` | Loại những phần tử array thỏa điều kiện | `{ $pull: { auditTags: "obsolete" } }` |

Ví dụ cập nhật hai field trong object lồng nhau mà không làm mất những field khác:

```javascript
db.orders.findOneAndUpdate(
  { _id: "ord-101" },
  {
    $set: {
      "shipping.city": "Hải Phòng",
      "shipping.method": "express"
    }
  },
  { returnDocument: "after" }
)
```

`shipping.city` và `shipping.method` sử dụng **dot notation**. Nếu `shipping` có thêm field `trackingCode`, cách dùng `$set` trên hai đường dẫn con vẫn giữ field đó. Ngược lại, `$set: { shipping: { city: "Hải Phòng" } }` sẽ **thay toàn bộ object** `shipping` bằng object mới chỉ chứa `city`.

### Cập nhật một phần tử array bằng `arrayFilters`

Giả sử cần tăng `qty` cho mặt hàng `P-2` của đơn `ord-101`:

```javascript
db.orders.findOneAndUpdate(
  { _id: "ord-101" },
  { $inc: { "items.$[item].qty": 1 } },
  {
    arrayFilters: [{ "item.sku": "P-2" }],
    returnDocument: "after"
  }
)
```

`$[item]` chọn những phần tử của `items` thỏa `item.sku: "P-2"`. Điều này không đòi hỏi `P-2` luôn đứng ở chỉ số `1`; nếu trong mảng có nhiều phần tử trùng mã, tất cả phần tử phù hợp có thể bị cập nhật. `arrayFilters` là tùy chọn của thao tác **update**, không áp dụng như một phần của replacement document.

Trên các phiên bản MongoDB hỗ trợ **aggregation pipeline update**, tham số `update` có thể là pipeline các stage được cho phép, chẳng hạn `$set` hoặc `$unset` dưới dạng pipeline. Đây là cú pháp khác với tài liệu update operators; không được suy ra rằng mọi stage aggregation đều hợp lệ trong update.

## 5. `findOneAndReplace()`: thay thế toàn bộ nội dung document

`findOneAndReplace()` nhận một **replacement document**, thay cho tài liệu các update operators.

```javascript
db.collection.findOneAndReplace(
  filter,
  replacement,
  options
)
```

Ví dụ dùng một đơn hàng mới ở trạng thái `pending`:

```javascript
db.orders.insertOne({
  _id: "ord-201",
  customerId: "u201",
  status: "pending",
  total: 80,
  shipping: { city: "Hà Nội", method: "standard" },
  items: [{ sku: "P-5", qty: 1 }],
  internalNote: "Cần xác nhận"
})
```

Muốn thay thế document bằng một bản đã xác nhận:

```javascript
db.orders.findOneAndReplace(
  { _id: "ord-201" },
  {
    _id: "ord-201",
    customerId: "u201",
    status: "confirmed",
    total: 80,
    shipping: { city: "Hà Nội", method: "express" },
    items: [{ sku: "P-5", qty: 1 }]
  },
  { returnDocument: "after" }
)
```

Bản sau thay thế **không còn `internalNote`** vì field này không được đưa vào replacement. Đây là khác biệt quan trọng so với `$set` trong `findOneAndUpdate()`.

### 5.1. Replacement là document hoàn chỉnh

Giả sử document cũ:

```javascript
{
  _id: "x1",
  name: "Bình",
  active: true,
  profile: { city: "Huế", language: "vi" }
}
```

Nếu replacement là:

```javascript
{
  name: "Bình",
  active: false
}
```

thì sau khi thay thế, document không còn `profile`. Nếu `_id` bị lược bỏ khỏi replacement, MongoDB giữ lại `_id` hiện hữu của document được thay thế; nếu cung cấp `_id`, giá trị này phải không làm thay đổi `_id` bất biến của document hiện có.

Hãy coi replacement là **bản mô tả toàn bộ nội dung mong muốn** của document, thay vì một danh sách các field cần sửa.

### 5.2. Không dùng `$set` làm replacement

Lệnh sau là cách viết **sai** cho `findOneAndReplace()`:

```javascript
// SAI: replacement không phải update operators
db.orders.findOneAndReplace(
  { _id: "ord-201" },
  { $set: { status: "paid" } }
)
```

Muốn chỉ sửa `status`, dùng `findOneAndUpdate()` với `$set`. Muốn thay toàn bộ document thì truyền object replacement có đầy đủ các field cần giữ.

MongoDB có ràng buộc về các tên field và cấu trúc replacement; không xem replacement là một update pipeline. Những trường hợp đặc biệt như field chứa dấu chấm hoặc ký tự `$` cần đối chiếu với quy định đặt tên field của phiên bản hiện tại.

### 5.3. `_id` không được thay đổi khi thay document

Ví dụ:

```javascript
// Không hợp lệ nếu document khớp có _id = "ord-201"
db.orders.findOneAndReplace(
  { _id: "ord-201" },
  {
    _id: "ord-999",
    status: "confirmed"
  }
)
```

Trường `_id` là định danh bất biến. Nếu ứng dụng cần một định danh khác, phải quyết định đây là thay đổi field nghiệp vụ khác với `_id`, hay là tạo một document mới rồi xử lý vòng đời document cũ theo yêu cầu nghiệp vụ.

## 6. Lựa chọn document trả về với `findOneAndReplace()`

`findOneAndReplace()` có quy tắc lựa chọn ảnh tương tự `findOneAndUpdate()`:

```javascript
// Nhận document trước khi thay thế
db.orders.findOneAndReplace(
  { _id: "ord-201" },
  {
    _id: "ord-201",
    customerId: "u201",
    status: "shipped",
    total: 80,
    shipping: { city: "Hà Nội", method: "express" },
    items: [{ sku: "P-5", qty: 1 }]
  },
  { returnDocument: "before" }
)
```

Giả sử document `ord-201` trước thao tác có `status: "confirmed"`, bản trả về có trạng thái đó, trong khi bản lưu mới là `"shipped"`.

```javascript
// Nhận document sau khi thay thế
db.orders.findOneAndReplace(
  { _id: "ord-201" },
  {
    _id: "ord-201",
    customerId: "u201",
    status: "delivered",
    total: 80,
    shipping: { city: "Hà Nội", method: "express" },
    items: [{ sku: "P-5", qty: 1 }]
  },
  { returnDocument: "after" }
)
```

Lần này giá trị trả về chứa `status: "delivered"`. Lưu ý các ví dụ thay đổi `ord-201` theo trình tự; nếu chạy từng đoạn độc lập trên dữ liệu khác, bản trước và bản sau sẽ phụ thuộc trạng thái thật của collection.

| Tình huống | `findOneAndUpdate()` | `findOneAndReplace()` |
| --- | --- | --- |
| Có document khớp, `"before"` | Trả ảnh trước update | Trả ảnh trước replacement |
| Có document khớp, `"after"` | Trả ảnh sau update | Trả ảnh sau replacement |
| Không có document khớp và `upsert: false` | `null` | `null` |
| Không khớp, `upsert: true`, `"before"` | `null` vì không có ảnh trước | `null` vì không có ảnh trước |
| Không khớp, `upsert: true`, `"after"` | Trả document vừa tạo | Trả document vừa tạo |

**Quy tắc:** Khi kết quả là `null`, đừng vội kết luận thao tác thất bại. `null` cũng xuất hiện khi `upsert` tạo mới nhưng caller yêu cầu ảnh **before**, vốn không tồn tại.

## 7. `upsert`: không tìm thấy thì thêm document mới

Thông thường hai phương thức chỉ sửa document đã tồn tại. Đặt `upsert: true` để tạo mới khi không có document phù hợp.

### 7.1. Upsert với `findOneAndUpdate()`

```javascript
db.orders.findOneAndUpdate(
  { _id: "ord-301" },
  {
    $set: {
      customerId: "u301",
      status: "pending",
      total: 60
    },
    $setOnInsert: {
      createdBy: "lab"
    }
  },
  {
    upsert: true,
    returnDocument: "after"
  }
)
```

Nếu `ord-301` chưa tồn tại, MongoDB tạo document mới và trả về bản mới. Trong ví dụ này, `createdBy` được thêm nhờ `$setOnInsert`, chỉ áp dụng khi nhánh **insert** của upsert diễn ra.

Nếu chạy lặp khi `ord-301` đã tồn tại, `$set` cập nhật các field đã nêu nhưng `$setOnInsert` không chạy lại. Việc có hoặc không có giá trị mới cần được xem trong document thực tế; `$setOnInsert` không thay thế được cơ chế chống trùng cho toàn bộ nghiệp vụ.

### 7.2. Upsert với `findOneAndReplace()`

```javascript
db.orders.findOneAndReplace(
  { _id: "ord-302" },
  {
    _id: "ord-302",
    customerId: "u302",
    status: "pending",
    total: 75,
    shipping: { city: "Đà Nẵng", method: "standard" },
    items: []
  },
  {
    upsert: true,
    returnDocument: "after"
  }
)
```

Khi `ord-302` không tồn tại, document replacement được chèn vào. Nếu document đã tồn tại, **nội dung cũ bị thay** bởi replacement. Không thể dùng `$setOnInsert` bên trong replacement như một update operator; nếu cần logic chỉ đặt field khi chèn, thường `findOneAndUpdate()` thích hợp hơn.

### 7.3. Vì sao `upsert` + ảnh trước có thể trả `null`?

```javascript
db.orders.findOneAndUpdate(
  { _id: "ord-303" },
  {
    $set: {
      customerId: "u303",
      status: "pending"
    }
  },
  {
    upsert: true,
    returnDocument: "before"
  }
)
```

Khi chưa có `ord-303`, kết quả là `null` nhưng bản ghi mới có thể đã được tạo thành công. Tương tự đối với `findOneAndReplace()`.

| Mục đích của caller | Tùy chọn nên chọn |
| --- | --- |
| Cần bản cũ để đối chiếu giá trị trước khi sửa | `returnDocument: "before"` |
| Cần trả ngay đối tượng mới cho API response | `returnDocument: "after"` |
| Upsert và cần biết nội dung bản ghi đã được tạo | `upsert: true, returnDocument: "after"` |
| Chỉ cần số lượng matched/modified hoặc upserted ID | Cân nhắc `updateOne()` hoặc `replaceOne()` |

Khi upsert dựa vào khóa nghiệp vụ (không phải `_id`), nên có **unique index** phù hợp để xử lý trường hợp nhiều request đồng thời cùng cố tạo bản ghi. `upsert` không tự bảo đảm mọi khóa nghiệp vụ đều duy nhất khi không có ràng buộc index.

## 8. `sort`: chọn document nào nếu filter khớp nhiều bản

Tên `findOne...` nói rằng chỉ một document bị thay đổi. Nhưng nếu `filter` khớp nhiều document, **bản nào** sẽ được chọn?

Ví dụ cả `ord-101` và `ord-102` ban đầu có `status: "pending"`. Bộ lọc:

```javascript
{ status: "pending" }
```

không xác định duy nhất một document. Nếu không chỉ rõ `sort`, không nên dựa vào thứ tự lưu trữ hoặc thứ tự tự nhiên để đoán document nào được chọn.

Chọn document có `priority` cao nhất:

```javascript
db.orders.findOneAndUpdate(
  { status: "pending" },
  {
    $set: { status: "processing" },
    $currentDate: { pickedAt: true }
  },
  {
    sort: { priority: -1, _id: 1 },
    returnDocument: "after"
  }
)
```

Trong `sort`:

- `priority: -1`: ưu tiên giá trị lớn trước.
- `_id: 1`: khi cùng `priority`, dùng `_id` làm tiêu chí phụ để chọn ổn định hơn.

`sort` ở đây **chọn document mục tiêu**, không phải sắp xếp một danh sách kết quả, vì phương thức chỉ trả về tối đa một document.

Với `findOneAndReplace()`, `sort` cũng có thể được dùng để chọn document cần thay. Tuy nhiên, replacement phải chứa toàn bộ dữ liệu cần giữ của document được chọn. Nếu filter có thể chọn nhiều document khác nhau, hãy rất thận trọng: một replacement cố định có thể làm mất các field hoặc thay đổi dữ liệu mà ứng dụng chưa đọc. Với thao tác xử lý hàng đợi hoặc chọn job, `findOneAndUpdate()` với các toán tử thường thuận tiện và an toàn về mặt mô hình hơn.

### Điều kiện cập nhật phải gắn với trạng thái mong đợi

Ví dụ để tránh hai worker cùng nhận một công việc:

```javascript
db.jobs.findOneAndUpdate(
  { state: "queued" },
  {
    $set: { state: "running", owner: "worker-A" },
    $currentDate: { startedAt: true }
  },
  {
    sort: { priority: -1, _id: 1 },
    returnDocument: "after"
  }
)
```

Mỗi thao tác tìm và cập nhật một document đủ điều kiện như một thao tác nguyên tử trên document đó. Khi không còn job `queued`, kết quả là `null`. Ví dụ này giả định collection `jobs` đã có dữ liệu theo schema phù hợp.

Cần có cơ chế xử lý worker chết giữa chừng, retry, lease/timeout nếu nghiệp vụ thực tế là hàng đợi phân tán. Việc chọn một job nguyên tử chỉ giải quyết bước **claim**, không thay thế toàn bộ quản lý vòng đời job.

## 9. `projection`: chọn những field được trả về

Khi document có nhiều field, caller có thể chỉ muốn một số field trong ảnh trả về:

```javascript
db.orders.findOneAndUpdate(
  { _id: "ord-101" },
  { $set: { status: "packed" } },
  {
    returnDocument: "after",
    projection: {
      _id: 1,
      status: 1,
      total: 1
    }
  }
)
```

Giá trị trả về chỉ chứa những field được yêu cầu nếu chúng có mặt, chẳng hạn:

```javascript
{
  _id: "ord-101",
  status: "packed",
  total: 150
}
```

Tuy nhiên, document **lưu trong collection không bị cắt còn ba field**. `projection` chỉ giới hạn hình dạng của ảnh được trả về, không thay đổi phạm vi ghi.

Điều tương tự áp dụng cho `findOneAndReplace()`:

```javascript
db.orders.findOneAndReplace(
  { _id: "ord-302" },
  {
    _id: "ord-302",
    customerId: "u302",
    status: "confirmed",
    total: 75,
    shipping: { city: "Đà Nẵng", method: "express" },
    items: []
  },
  {
    returnDocument: "after",
    projection: { status: 1, total: 1, _id: 0 }
  }
)
```

Kết quả chỉ hiển thị `status` và `total`. Bên dưới, replacement vẫn chứa `customerId`, `shipping` và `items`.

**Đừng nhầm `projection` với `replacement`:** projection là quy tắc đọc cho ảnh trả về; replacement là toàn bộ nội dung ghi mới.

## 10. Không có document khớp, `null` và cách nhận biết kết quả

Với bộ lọc không khớp:

```javascript
db.orders.findOneAndUpdate(
  { _id: "ord-999" },
  { $set: { status: "paid" } },
  { returnDocument: "after" }
)
```

Do `upsert` mặc định không bật, lệnh không tạo document `ord-999` và giá trị trả về là `null`.

Một cách xử lý trong `mongosh`:

```javascript
const result = db.orders.findOneAndUpdate(
  { _id: "ord-999", status: "pending" },
  { $set: { status: "paid" } },
  { returnDocument: "after" }
);

if (result === null) {
  print("Không có document phù hợp để cập nhật");
} else {
  print("Đã cập nhật: " + result._id);
  printjson(result);
}
```

Cách diễn giải này đúng khi `upsert: false`. Khi `upsert: true` và `returnDocument: "before"`, `null` **còn có thể có nghĩa vừa insert thành công**. Để biết chắc nhánh thao tác, thiết kế API caller sử dụng `"after"`, hoặc sử dụng thao tác trả metadata phù hợp yêu cầu cụ thể.

Trong một ứng dụng web, nếu không có đơn hàng khớp trạng thái mong đợi, thường cần chuyển kết quả `null` thành phản hồi nghiệp vụ có ý nghĩa, chẳng hạn “Đơn hàng không tồn tại hoặc không còn ở trạng thái pending”, thay vì mặc nhiên ném lỗi kết nối MongoDB.

## 11. Tính nguyên tử và điều kiện kiểm tra trạng thái

Điểm mạnh của `findOneAndUpdate()` không chỉ nằm ở việc lấy bản trước/sau, mà còn ở việc kiểm tra **điều kiện trên document được thay đổi** cùng thao tác cập nhật.

### 11.1. Chuyển trạng thái có điều kiện

```javascript
db.orders.findOneAndUpdate(
  {
    _id: "ord-101",
    status: "pending"
  },
  {
    $set: { status: "paid" },
    $currentDate: { paidAt: true }
  },
  { returnDocument: "after" }
)
```

Nếu request khác đã chuyển `ord-101` sang `cancelled`, bộ lọc có `status: "pending"` không còn khớp. Nhờ đó, thao tác không vô tình chuyển một đơn hàng đã hủy thành `paid`.

Mẫu này thường được gọi là **cập nhật có điều kiện theo trạng thái**. Nó không cần chạy `findOne()` rồi kiểm tra ở phía Java trước khi gửi lệnh sửa, vốn tạo khoảng trống cho thay đổi đồng thời.

### 11.2. Cập nhật bộ đếm kèm điều kiện giới hạn

Giả sử document sự kiện đã có:

```javascript
{
  _id: "event-101",
  capacity: 50,
  booked: 49
}
```

Muốn tăng `booked` khi chưa đủ chỗ:

```javascript
db.events.findOneAndUpdate(
  {
    _id: "event-101",
    $expr: { $lt: ["$booked", "$capacity"] }
  },
  { $inc: { booked: 1 } },
  { returnDocument: "after" }
)
```

Nếu document có `booked: 49` và `capacity: 50`, thao tác trả bản mới với `booked: 50`. Request tiếp theo không khớp điều kiện `$expr` nữa. Ví dụ này giả định document tồn tại trong `db.events` và hai field có kiểu số phù hợp.

Đây là ràng buộc **trong một document**; nếu mỗi lần đặt chỗ còn phải ghi payment/seat reservation ở các collection khác, cần thiết kế thêm để giữ nhất quán giữa các thay đổi liên quan.

### 11.3. Vì sao đọc trước rồi ghi sau không tương đương?

```javascript
// Dễ có race condition giữa hai lệnh:
const event = db.events.findOne({ _id: "event-101" });
if (event && event.booked < event.capacity) {
  db.events.updateOne(
    { _id: "event-101" },
    { $inc: { booked: 1 } }
  );
}
```

Hai request đồng thời có thể cùng đọc số chỗ còn lại trước khi bất kỳ request nào cập nhật. Nếu điều kiện `booked < capacity` chỉ kiểm tra ở client rồi không đưa vào bộ lọc cập nhật, giới hạn có thể bị vượt.

Đưa điều kiện vào chính `findOneAndUpdate()` (hoặc `updateOne()` nếu không cần document trả về) giải quyết vấn đề cập nhật có điều kiện ở cấp document.

## 12. Java MongoDB Sync Driver: lựa chọn `ReturnDocument`

Trong Java Sync Driver, hai phương thức tương ứng nằm trên `MongoCollection<TDocument>`. Thay cho chuỗi `"before"`/`"after"` của `mongosh`, driver dùng enum **`ReturnDocument.BEFORE`** hoặc **`ReturnDocument.AFTER`**.

Các lớp cấu hình:

- `FindOneAndUpdateOptions`: dành riêng cho `findOneAndUpdate()`.
- `FindOneAndReplaceOptions`: dành riêng cho `findOneAndReplace()`.
- `ReturnDocument`: lựa chọn bản trước hoặc bản sau.

Ví dụ đầy đủ với `Document`:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.FindOneAndReplaceOptions;
import com.mongodb.client.model.FindOneAndUpdateOptions;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.ReturnDocument;
import com.mongodb.client.model.Updates;
import org.bson.Document;

public class FindAndModifyExample {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("Missing MONGODB_URI");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase("mongo_update_lab");
            MongoCollection<Document> orders =
                database.getCollection("orders");

            // 1) Cập nhật và nhận document sau thao tác
            FindOneAndUpdateOptions updateOptions =
                new FindOneAndUpdateOptions()
                    .returnDocument(ReturnDocument.AFTER)
                    .projection(
                        Projections.include("_id", "status", "updatedAt")
                    );

            Document updated = orders.findOneAndUpdate(
                Filters.and(
                    Filters.eq("_id", "ord-101"),
                    Filters.eq("status", "pending")
                ),
                Updates.combine(
                    Updates.set("status", "paid"),
                    Updates.currentDate("updatedAt")
                ),
                updateOptions
            );

            if (updated == null) {
                System.out.println(
                    "Không tìm thấy đơn hàng pending phù hợp"
                );
            } else {
                System.out.println("Sau update: " + updated.toJson());
            }

            // 2) Thay thế toàn bộ document, nhận bản trước thay thế
            Document replacement = new Document("_id", "ord-103")
                .append("customerId", "u102")
                .append("status", "archived")
                .append("total", 220)
                .append("priority", 3)
                .append(
                    "shipping",
                    new Document("city", "Đà Nẵng")
                        .append("method", "standard")
                )
                .append(
                    "items",
                    java.util.List.of(
                        new Document("sku", "P-4")
                            .append("qty", 2)
                    )
                );

            FindOneAndReplaceOptions replaceOptions =
                new FindOneAndReplaceOptions()
                    .returnDocument(ReturnDocument.BEFORE);

            Document beforeReplacement = orders.findOneAndReplace(
                Filters.eq("_id", "ord-103"),
                replacement,
                replaceOptions
            );

            if (beforeReplacement == null) {
                System.out.println("Không tìm thấy đơn hàng để thay");
            } else {
                System.out.println(
                    "Trước replace: " + beforeReplacement.toJson()
                );
            }
        }
    }
}
```

Để chạy ví dụ, cần dependency MongoDB Java Sync Driver tương thích, MongoDB có thể kết nối, quyền ghi trên database và biến môi trường `MONGODB_URI`. Bộ dữ liệu `orders` từ mục 2 cần tồn tại, nếu không thao tác chỉ trả về `null` do không có document khớp.

**Lưu ý:** Java Driver trả về `Document` hoặc `null` theo kiểu đồng bộ ở ví dụ này; driver reactive dùng API bất đồng bộ với loại kết quả khác. Đừng sao chép nguyên enum/options giữa Java và `mongosh`: mỗi API có cú pháp riêng nhưng cùng ý nghĩa lựa chọn ảnh trước/sau.

### 12.1. `sort`, `projection` và `upsert` trong Java

```java
import com.mongodb.client.model.FindOneAndUpdateOptions;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.ReturnDocument;
import com.mongodb.client.model.Sorts;

FindOneAndUpdateOptions options = new FindOneAndUpdateOptions()
    .sort(
        Sorts.orderBy(
            Sorts.descending("priority"),
            Sorts.ascending("_id")
        )
    )
    .projection(Projections.include("_id", "status", "priority"))
    .upsert(false)
    .returnDocument(ReturnDocument.AFTER);
```

Trong Java, `Sorts.descending("priority")` được dùng để chọn document có ưu tiên lớn nhất nếu filter khớp nhiều bản; `Projections.include(...)` giới hạn các field trong ảnh trả về; `upsert(false)` ngăn tạo bản mới.

### 12.2. Phân biệt kết quả document và `UpdateResult`

```java
// Trả về thông tin matched/modified/upserted:
var updateResult = orders.updateOne(
    Filters.eq("_id", "ord-101"),
    Updates.set("status", "paid")
);
System.out.println(updateResult.getMatchedCount());

// Trả về một document trước/sau hoặc null:
Document changedOrder = orders.findOneAndUpdate(
    Filters.eq("_id", "ord-101"),
    Updates.set("status", "paid"),
    new FindOneAndUpdateOptions()
        .returnDocument(ReturnDocument.AFTER)
);
```

Với `findOneAndUpdate()`, ta **không** nhận `UpdateResult` để gọi `getMatchedCount()`. Nếu nghiệp vụ cần số lượng khớp/sửa hoặc ID của bản upsert thông qua metadata, API `updateOne()` có thể phù hợp hơn.

## 13. Lỗi thường gặp và cách đọc kết quả

| Tình huống | Nguyên nhân / Ý nghĩa | Cách xử lý |
| --- | --- | --- |
| Đã cập nhật nhưng trả về `status` cũ | Mặc định trả ảnh **before** | Dùng `returnDocument: "after"` nếu cần bản mới |
| Kết quả `null` khi không bật upsert | Không có document nào khớp filter | Kiểm tra `_id`, trạng thái và các điều kiện lọc |
| `upsert: true` nhưng vẫn nhận `null` | Insert mới trong khi yêu cầu ảnh **before** | Dùng `"after"` nếu muốn nhận document mới |
| Field cũ biến mất sau `findOneAndReplace()` | Replacement thiếu field đó | Cung cấp đầy đủ dữ liệu hoặc dùng update operators |
| Truyền `{$set: ...}` vào `findOneAndReplace()` | Replacement không phải update operators | Dùng `findOneAndUpdate()` |
| Cố đổi `_id` khi replacement | `_id` bất biến | Giữ `_id` hiện có hoặc thiết kế thao tác khác |
| Không biết document nào bị sửa khi filter rộng | Filter khớp nhiều bản, không có lựa chọn ổn định | Dùng điều kiện đủ hẹp và `sort` có tie-breaker |
| `projection` trả thiếu field | Chỉ yêu cầu một số field trong ảnh | Kiểm tra projection; document lưu không nhất thiết thiếu field |
| `$inc` nhiều lần làm tăng giá trị liên tục | Toán tử tăng số **không idempotent** | Thiết kế cơ chế retry/chống xử lý trùng nếu cần |
| Cập nhật mảng sai phần tử | Hard-code vị trí hoặc filter không đúng | Dùng positional operator/`arrayFilters` theo yêu cầu |
| Dùng `findOne()` rồi `updateOne()` bị ghi đè trạng thái mới | Hai thao tác rời tạo race condition | Đưa trạng thái mong đợi vào filter của thao tác cập nhật |
| Muốn sửa nhiều document bằng `findOneAndUpdate()` | Phương thức chỉ thay đổi một document | Dùng `updateMany()` hoặc thiết kế giao dịch nhiều document |

### Trường hợp ghi không thành công do quy tắc khác

Việc bộ lọc khớp không có nghĩa lệnh chắc chắn thành công: MongoDB vẫn kiểm tra unique indexes, schema validation, quyền, giới hạn BSON, trạng thái kết nối và các ràng buộc khác. Ví dụ replacement vi phạm validator hoặc cố thay `_id` sẽ báo lỗi thay vì trả ảnh document thành công.

Khi xử lý exception trong ứng dụng, cần phân biệt:

- **`null` như một kết quả hợp lệ**: không có document khớp hoặc không có ảnh trước của upsert.
- **Lỗi thực thi**: vi phạm unique/schema, không đủ quyền, timeout hoặc vấn đề mạng.

Không nên gom hai trường hợp vào một nhánh `catch` chung rồi diễn giải “không tìm thấy document”.

## 14. Chọn phương thức theo yêu cầu nghiệp vụ

| Yêu cầu | Lựa chọn gợi ý | Lý do |
| --- | --- | --- |
| Đổi `status` và nhận document mới | `findOneAndUpdate()` + `"after"` | Sửa một vài field và lấy ảnh sau |
| Ghi nhận document cũ trước khi sửa | `findOneAndUpdate()` + `"before"` | Lấy ảnh trước gắn với thao tác sửa |
| Thay toàn bộ object theo dữ liệu đã duyệt và nhận bản mới | `findOneAndReplace()` + `"after"` | Replacement thể hiện toàn bộ nội dung mong muốn |
| Thay toàn bộ object nhưng chỉ cần số lượng khớp | `replaceOne()` | Trả metadata thay vì ảnh document |
| Cộng một giá trị và chỉ cần `matchedCount` | `updateOne()` | Không cần lấy cả document |
| Tạo nếu thiếu, luôn cần document có dữ liệu mới | `findOneAndUpdate()` hoặc `findOneAndReplace()` với `upsert: true`, `"after"` | Trả bản mới được chèn/cập nhật |
| Chọn một job ưu tiên cao nhất còn chờ | `findOneAndUpdate()` với filter trạng thái và `sort` | Claim một document phù hợp |
| Cập nhật đồng loạt hàng trăm document | `updateMany()` | `findOneAndUpdate()` chỉ sửa tối đa một document |

Không có phương thức nào mặc định phù hợp cho mọi trường hợp. Hãy bắt đầu bằng ba câu hỏi: **(1) có cần giữ các field không được liệt kê không, (2) có cần document trả về không, (3) cần ảnh trước hay sau?** Câu trả lời quyết định dùng update, replacement và `returnDocument`.

## 15. Bài tập thực hành

Các bài tập giả định dùng collection riêng với dữ liệu còn nguyên hoặc được tạo phù hợp. Lệnh cập nhật làm thay đổi dữ liệu; nếu kiểm tra nhiều đáp án liên tiếp, nên tách mỗi bài một collection lab.

### Bài 1. Nhận document sau khi cập nhật

Cho document:

```javascript
{
  _id: "order-A",
  status: "pending",
  total: 120,
  customerId: "u1"
}
```

Hãy đổi `status` thành `paid`, đồng thời nhận document mới và giữ `total`/`customerId`.

**Đáp án:**

```javascript
db.orders.findOneAndUpdate(
  { _id: "order-A", status: "pending" },
  { $set: { status: "paid" } },
  { returnDocument: "after" }
)
```

Vì dùng `$set`, các field khác vẫn còn. Điều kiện `status: "pending"` giúp bảo đảm chỉ chuyển trạng thái khi đơn đang chờ.

### Bài 2. Giải thích vì sao kết quả là trạng thái cũ

```javascript
db.orders.findOneAndUpdate(
  { _id: "order-B" },
  { $set: { status: "shipped" } }
)
```

Lệnh trả về document có `status: "packed"`. Thao tác có chắc thất bại không?

**Đáp án:** Không. Nếu `order-B` đã có `status: "packed"` trước khi chạy, đó là ảnh **before** mặc định. Sau thao tác, document có thể đã được lưu thành `status: "shipped"`. Muốn nhận bản mới, thêm `returnDocument: "after"`.

### Bài 3. Tránh mất field khi thay thế

Document cũ:

```javascript
{
  _id: "u5",
  name: "An",
  active: true,
  profile: { city: "Hà Nội" }
}
```

Nếu gọi:

```javascript
db.users.findOneAndReplace(
  { _id: "u5" },
  { name: "An", active: false },
  { returnDocument: "after" }
)
```

Thì field `profile` còn không? Trường `_id` có bị mất không?

**Đáp án:** `profile` bị loại bỏ vì replacement không có field này. `_id` của document hiện có vẫn được giữ; replacement không thể dùng để thay đổi `_id`. Nếu muốn chỉ đổi `active`, nên dùng `findOneAndUpdate()` với `$set`.

### Bài 4. Upsert và ảnh trả về

Collection chưa có document `{_id:"x10"}`. Lệnh:

```javascript
db.settings.findOneAndUpdate(
  { _id: "x10" },
  { $set: { enabled: true } },
  { upsert: true, returnDocument: "before" }
)
```

Giá trị trả về dự kiến là gì? Document `x10` có được tạo không?

**Đáp án:** Giá trị trả về là `null` do không có document trước thao tác; bản `x10` mới vẫn được tạo nếu upsert thành công. Dùng `returnDocument: "after"` khi cần ảnh vừa tạo.

### Bài 5. Chọn một tác vụ ưu tiên

Collection `jobs` có nhiều document `state: "queued"`, mỗi document có `priority`. Hãy nhận job ưu tiên cao nhất và chuyển nó sang `running` trong một thao tác.

**Đáp án:**

```javascript
db.jobs.findOneAndUpdate(
  { state: "queued" },
  { $set: { state: "running" } },
  {
    sort: { priority: -1, _id: 1 },
    returnDocument: "after"
  }
)
```

Việc đưa trạng thái vào filter và đặt tiêu chí sắp xếp cho phép chọn job thích hợp và nhận ảnh mới của job được chọn.

### Bài 6. Cập nhật khi chưa vượt sức chứa

Với document `{_id:"event-1", capacity:10, booked:9}`, hãy tăng `booked` thêm 1 **chỉ khi còn chỗ**, trả document sau thao tác.

**Đáp án:**

```javascript
db.events.findOneAndUpdate(
  {
    _id: "event-1",
    $expr: { $lt: ["$booked", "$capacity"] }
  },
  { $inc: { booked: 1 } },
  { returnDocument: "after" }
)
```

Sau thao tác thành công, `booked` bằng 10; lần tiếp theo cùng điều kiện không khớp.

## 16. Ghi nhớ về lựa chọn ảnh trước/sau

**`findOneAndUpdate()`** là lựa chọn tự nhiên khi muốn sửa một phần document mà vẫn giữ các field khác; **`findOneAndReplace()`** dành cho trường hợp thực sự muốn thay cả nội dung document. Cả hai có thể trả ảnh trước hoặc sau bằng `returnDocument`. Mặc định là ảnh **before**; chọn **after** nếu cần document đã cập nhật để trả cho ứng dụng.

Khi viết lệnh thực tế, hãy kiểm tra kỹ **filter**, khả năng khớp nhiều document và `sort`, điều kiện trạng thái để tránh race condition, sự khác nhau giữa `null` do không khớp và `null` do upsert với ảnh trước, cũng như những field sẽ biến mất trong replacement. Phân biệt rõ **update operators**, **replacement**, **ảnh trả về** và **metadata thao tác** giúp ứng dụng cập nhật MongoDB chính xác và tránh hiểu sai kết quả.

# Thực hiện vòng CRUD và quan sát document bằng mongosh hoặc Compass

MongoDB lưu dữ liệu dưới dạng **document BSON** trong **collection**. Trước khi thao tác với `MongoRepository` hay `MongoTemplate` của Spring Data MongoDB, bạn nên thực hiện trực tiếp một vòng **Create – Read – Update – Delete (CRUD)** và quan sát document thực sự được lưu như thế nào. Bài thực hành này dùng `mongosh` để minh họa lệnh có thể chạy lại, đồng thời chỉ ra thao tác tương đương trong MongoDB Compass.

Sau bài học, bạn có thể:

- Kết nối MongoDB bằng `mongosh` hoặc Compass và chọn đúng database/collection.
- Tạo document, đọc theo bộ lọc, cập nhật có điều kiện và xóa chính xác dữ liệu cần xóa.
- Phân biệt `_id` kiểu `ObjectId` với chuỗi, quan sát kiểu BSON của trường và document lồng nhau.
- Đọc kết quả `acknowledged`, `insertedId`, `matchedCount`, `modifiedCount`, `deletedCount` để xác nhận thao tác.
- Dùng bộ lọc, projection, sort, limit và `explain` để kiểm tra dữ liệu và cách truy vấn.
- Đối chiếu thao tác thủ công với mapping và API tương ứng trong Spring Data MongoDB.

## 1. Chuẩn bị môi trường thực hành

Bạn cần một MongoDB server đang chạy và một trong hai công cụ:

| Công cụ | Cách sử dụng | Điểm mạnh |
| --- | --- | --- |
| **mongosh** | Gõ lệnh JavaScript trong MongoDB Shell | Dễ sao chép, lưu lại, lặp lại và kiểm tra kết quả từng bước |
| **MongoDB Compass** | Giao diện đồ họa, vào collection để xem và sửa document | Dễ quan sát cấu trúc BSON, lọc dữ liệu, sửa từng trường và xem query plan |

Trong ví dụ, giả sử MongoDB local đang lắng nghe tại `127.0.0.1:27017` và **không yêu cầu xác thực**. Cấu hình này chỉ phù hợp với môi trường local/training đã được cô lập.

Mở terminal:

```bash
mongosh "mongodb://127.0.0.1:27017"
```

Nếu server có xác thực, dùng URI phù hợp hoặc truyền `--username` và `--authenticationDatabase` để mongosh hỏi mật khẩu; không đưa mật khẩu thật vào ví dụ hoặc commit mật khẩu vào repository. Với MongoDB Atlas hay server từ xa, dùng URI được cấp, đúng cấu hình xác thực và TLS tương ứng.

Trong Compass, mở **New Connection**, dán connection string, chọn **Connect**. Phần còn lại của bài dùng cùng server và database nên có thể quan sát từ cả hai công cụ. Nếu ứng dụng Spring Boot cũng truy cập MongoDB, cần bảo đảm cả ba cùng kết nối đến đúng database.

### 1.1. Chọn database và collection thử nghiệm

Trong `mongosh`:

```javascript
use spring_data_training

db.getName();                       // "spring_data_training"
show collections

const books = db.getCollection("crud_lab_books");
const labRun = "setup-007-" + new ObjectId().toHexString();
print("Mã lần thực hành: " + labRun);
```

Collection `crud_lab_books` chỉ dùng cho bài tập này. Mỗi lần chạy, `labRun` có giá trị mới để phân biệt dữ liệu của bạn với các lần thử trước. **Giữ nguyên phiên mongosh** cho các lệnh tiếp theo để dùng lại hai biến `books` và `labRun`.

MongoDB có thể tạo collection khi bạn ghi document đầu tiên; chỉ gọi `getCollection` chưa nhất thiết tạo collection trong database. Nếu `show collections` chưa thấy tên mới trước khi insert, đó là hành vi bình thường.

**Quy tắc an toàn khi thực hành:** mọi truy vấn sửa/xóa trong bài đều có điều kiện theo `labRun`. Không chạy `deleteMany({})`, `drop()` hoặc lệnh xóa trên collection dữ liệu thật.

## 2. Create — tạo document

### 2.1. Tạo ba document bằng `insertMany`

Chạy trong phiên `mongosh` đã khai báo `books` và `labRun`:

```javascript
const batch = books.insertMany([
  {
    labRun: labRun,
    sku: "BK-101",
    title: "Nhập môn MongoDB",
    priceVnd: 129000,
    stock: 10,
    tags: ["database", "beginner"],
    publisher: { name: "NXB Công nghệ", country: "VN" },
    createdAt: new Date()
  },
  {
    labRun: labRun,
    sku: "BK-102",
    title: "Thiết kế document",
    priceVnd: 99000,
    stock: 2,
    tags: ["database", "design"],
    publisher: { name: "NXB Công nghệ", country: "VN" },
    createdAt: new Date()
  },
  {
    labRun: labRun,
    sku: "BK-103",
    title: "Thực hành aggregation",
    priceVnd: 149000,
    stock: 0,
    tags: ["database", "aggregation"],
    publisher: { name: "NXB Phần mềm", country: "VN" },
    createdAt: new Date()
  }
]);

printjson(batch);
const firstId = batch.insertedIds[0];
```

Kết quả sẽ có `acknowledged: true` và `insertedIds` chứa định danh của ba document. Vì không truyền `_id`, driver thông thường tự cấp giá trị kiểu BSON `ObjectId`. Giá trị chính xác thay đổi theo mỗi lần chạy.

Các trường đã tạo minh họa nhiều kiểu BSON:

| Trường | Kiểu dự kiến | Ý nghĩa |
| --- | --- | --- |
| `_id` | ObjectId | Định danh duy nhất trong collection |
| `labRun`, `sku`, `title` | String | Nhãn đợt thực hành, mã sách, tên sách |
| `priceVnd`, `stock` | Kiểu số BSON | Giá nguyên theo VND và lượng tồn; kiểu số cụ thể phụ thuộc giá trị/driver |
| `tags` | Array | Danh sách chuỗi |
| `publisher` | Document lồng nhau | Thông tin đơn vị xuất bản |
| `createdAt` | Date | Mốc thời gian do `new Date()` cung cấp |

Chú ý: **JSON hiển thị chỉ là biểu diễn** của dữ liệu. BSON có nhiều kiểu cụ thể hơn JSON, ví dụ `ObjectId`, `Date`, `Int32`, `Int64`, `Decimal128`. Khi cần làm việc với tiền tệ hoặc số nguyên lớn trong ứng dụng, phải chọn kiểu dữ liệu thích hợp thay vì dựa vào cách giao diện hiển thị.

### 2.2. Tạo thêm một document bằng `insertOne`

```javascript
const single = books.insertOne({
  labRun: labRun,
  sku: "BK-104",
  title: "Spring Data MongoDB",
  priceVnd: 189000,
  stock: 5,
  tags: ["spring", "database"],
  publisher: { name: "NXB Phần mềm", country: "VN" },
  createdAt: new Date()
});

printjson(single.insertedId);
books.countDocuments({ labRun: labRun }); // Dự kiến: 4
```

`insertOne` trả về một `insertedId`; `insertMany` trả về `insertedIds`. Nếu tự cung cấp `_id` trùng với document đã có trong cùng collection, lệnh chèn bị từ chối với lỗi duplicate key (thường là `E11000`).

## 3. Read — tìm, lọc, sắp xếp và xem document

### 3.1. Đọc một document theo `_id`

```javascript
const oneBook = books.findOne({ _id: firstId });
printjson(oneBook);
```

`firstId` đang là một `ObjectId`. Không tự thay bằng chuỗi hex trong bộ lọc vì BSON ObjectId và BSON String là hai kiểu khác nhau. Nếu chỉ có chuỗi hex hợp lệ, chuyển đổi rõ ràng:

```javascript
const idText = firstId.toHexString();
books.findOne({ _id: new ObjectId(idText) });
```

### 3.2. Đọc nhiều document với điều kiện

`find` trả về **cursor**, chưa phải một mảng. Trong mongosh, có thể dùng `toArray()` để hiện kết quả của tập nhỏ:

```javascript
books.find({ labRun: labRun }).toArray();

// Sách còn ít nhất một sản phẩm trong kho:
books.find({
  labRun: labRun,
  stock: { $gte: 1 }
}).toArray();

// Tìm sách có tag "database":
books.find({
  labRun: labRun,
  tags: "database"
}).toArray();

// Tìm theo trường lồng nhau (dot notation):
books.find({
  labRun: labRun,
  "publisher.country": "VN"
}).toArray();
```

Các toán tử thường gặp:

| Toán tử | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `$eq` | `{ stock: { $eq: 0 } }` | Bằng giá trị |
| `$gte` / `$lte` | `{ stock: { $gte: 1 } }` | Lớn hơn/bằng hoặc nhỏ hơn/bằng |
| `$in` | `{ sku: { $in: ["BK-101", "BK-103"] } }` | Thuộc một tập giá trị |
| `$and` / `$or` | `{ $or: [{stock: 0}, {stock: 2}] }` | Ghép điều kiện |
| `$exists` | `{ updatedAt: { $exists: true } }` | Kiểm tra sự hiện diện của trường |

Trong câu lệnh thật, luôn kết hợp điều kiện phù hợp với `labRun` hoặc khóa nghiệp vụ để tránh nhận dữ liệu của những lần thử khác.

### 3.3. Projection, sort và limit

Chỉ lấy các trường cần hiển thị, sắp xếp theo tồn kho giảm dần và giới hạn 3 kết quả:

```javascript
books.find(
  { labRun: labRun },
  { _id: 0, sku: 1, title: 1, stock: 1 }
).sort({ stock: -1, sku: 1 }).limit(3).toArray();
```

Giải thích:

- Bộ lọc đầu tiên chọn đúng dữ liệu của lần thực hành.
- Projection `{ _id: 0, sku: 1, title: 1, stock: 1 }` trả về ba trường hiển thị và ẩn `_id`.
- `sort({ stock: -1, sku: 1 })` xếp `stock` giảm dần, rồi `sku` tăng dần khi trùng `stock`.
- `limit(3)` chỉ lấy tối đa ba document.

Projection thông thường không được trộn tùy tiện trường bao gồm (`1`) với trường loại trừ (`0`); `_id` là ngoại lệ thường dùng. Với dataset lớn, tránh gọi `toArray()` không giới hạn vì có thể tiêu tốn nhiều bộ nhớ ở client.

### 3.4. Đếm và quan sát các trường

```javascript
books.countDocuments({ labRun: labRun }); // Dự kiến: 4
books.distinct("publisher.name", { labRun: labRun });

const current = books.findOne({ _id: firstId });
printjson({
  idType: typeof current._id,
  idIsObjectId: current._id instanceof ObjectId,
  dateIsDate: current.createdAt instanceof Date,
  tagsIsArray: Array.isArray(current.tags)
});
```

`typeof` trên một đối tượng `ObjectId` trả về kiểu JavaScript `"object"`; sử dụng kiểm tra `instanceof ObjectId` khi cần phân biệt rõ. `printjson` trong mongosh và giao diện Compass có thể hiển thị cùng một giá trị theo cách khác nhau nhưng loại BSON lưu ở database vẫn là yếu tố quyết định khi so khớp truy vấn.

## 4. Update — thay đổi document có kiểm soát

### 4.1. `updateOne` với `$set` và `$inc`

Giảm tồn kho của `BK-101` đi 2, đồng thời ghi thời gian cập nhật:

```javascript
const updated = books.updateOne(
  {
    labRun: labRun,
    sku: "BK-101",
    stock: { $gte: 2 }
  },
  {
    $inc: { stock: -2 },
    $set: { updatedAt: new Date() }
  }
);

printjson({
  matchedCount: updated.matchedCount,
  modifiedCount: updated.modifiedCount
});

books.findOne(
  { labRun: labRun, sku: "BK-101" },
  { _id: 0, sku: 1, stock: 1, updatedAt: 1 }
);
// Dự kiến: stock = 8 sau lần chạy đầu tiên.
```

Bộ lọc `stock: { $gte: 2 }` và thao tác `$inc` diễn ra nguyên tử trên **một document**: hai yêu cầu đồng thời không thể cùng vượt qua điều kiện dựa trên một giá trị tồn kho cũ để trừ quá mức, nếu chúng đều dùng điều kiện ghi này.

**Chú ý tính lặp lại:** chạy lại lệnh trên sẽ giảm tiếp 2 nếu vẫn còn đủ tồn. Đây là cập nhật mang tính tích lũy, **không idempotent**. Trong nghiệp vụ thật, khi retry do timeout hoặc xử lý sự kiện lặp, cần thiết kế khóa idempotency hay điều kiện trạng thái thích hợp.

Phân biệt giá trị trả về:

| Trường | Ý nghĩa |
| --- | --- |
| `matchedCount` | Số document khớp bộ lọc (với `updateOne`, tối đa 1) |
| `modifiedCount` | Số document thực sự bị thay đổi |
| `upsertedId` | ID được tạo nếu dùng `upsert: true` và một document mới được chèn |

`matchedCount = 1` và `modifiedCount = 0` có thể xảy ra khi `$set` gán lại cùng giá trị đã có. `matchedCount = 0` có thể do không có ID/SKU tương ứng hoặc điều kiện trạng thái không đạt; không nên mặc định là lỗi kết nối.

### 4.2. `updateMany` theo bộ lọc

Đánh dấu nguồn của **đúng những document trong lần thực hành hiện tại**:

```javascript
const many = books.updateMany(
  { labRun: labRun },
  { $set: { source: "setup-007" } }
);

printjson(many);
books.countDocuments({
  labRun: labRun,
  source: "setup-007"
}); // Dự kiến: 4
```

Lệnh `updateMany` có thể thay đổi nhiều document. Tính nguyên tử vẫn được bảo đảm **cho từng document**, không đồng nghĩa toàn bộ nhiều document được cập nhật như một transaction duy nhất. Nếu nhiều document cần cùng commit/rollback, phải xem xét transaction nhiều document trên hạ tầng MongoDB phù hợp.

### 4.3. Phân biệt update và replace

- `$set`, `$inc`, `$push`, `$unset` là các **update operators**: chỉ thay đổi phần được nêu.
- `replaceOne(filter, replacement)` thay **toàn bộ nội dung document** (trừ quy tắc `_id`): những trường không có trong replacement sẽ biến mất.
- `upsert: true` cho phép tạo document khi không có kết quả khớp; đây là hành vi cần quyết định rõ, tránh vô tình tạo bản ghi mới.

Ví dụ chỉ đổi tiêu đề bằng một cập nhật an toàn:

```javascript
books.updateOne(
  { labRun: labRun, sku: "BK-102" },
  { $set: { title: "Thiết kế document với MongoDB" } }
);
```

Không viết `updateOne(filter, { title: "..." })` như một bản thay thế trong MongoDB hiện đại: lệnh update yêu cầu operator hoặc update pipeline. Dùng `replaceOne` khi thực sự muốn thay thế document.

### 4.4. Cập nhật mảng và trường lồng nhau

Đánh dấu `BK-103` có thêm tag:

```javascript
books.updateOne(
  { labRun: labRun, sku: "BK-103" },
  {
    $addToSet: { tags: "practice" },
    $set: { "publisher.country": "VN" }
  }
);
```

`$addToSet` tránh chèn giá trị tag trùng trong phép cập nhật này, còn `$push` luôn thêm phần tử. Dùng dot notation để sửa riêng `publisher.country`; nếu `$set` toàn bộ `publisher` bằng một object mới, các trường lồng nhau không được đưa vào object có thể bị mất.

## 5. Delete — xóa có điều kiện và xác nhận kết quả

### 5.1. Xóa một document

```javascript
const deletedOne = books.deleteOne({
  labRun: labRun,
  sku: "BK-104"
});
printjson(deletedOne); // Dự kiến: deletedCount = 1

books.countDocuments({ labRun: labRun }); // Dự kiến: 3
```

`deleteOne` xóa tối đa một document khớp bộ lọc. Nếu lọc không đủ cụ thể và có nhiều document khớp, MongoDB sẽ chọn một document trong số đó; vì vậy nên lọc bằng `_id` hoặc một khóa duy nhất rõ ràng khi cần xóa chính xác.

### 5.2. Dọn dữ liệu của riêng lần thực hành

Sau khi hoàn thành quan sát bằng Compass và bài tập, xóa **chỉ những document mang marker `labRun` của phiên hiện tại**:

```javascript
const beforeCleanup = books.countDocuments({ labRun: labRun });
print("Số document chuẩn bị xóa: " + beforeCleanup);

const cleanup = books.deleteMany({ labRun: labRun });
printjson({ deletedCount: cleanup.deletedCount });

books.countDocuments({ labRun: labRun }); // Dự kiến: 0
```

Nếu muốn tiếp tục xem document bằng Compass, **chưa chạy bước dọn dữ liệu**. Đặc biệt, không thay bộ lọc trên bằng `{}` vì điều đó có thể xóa toàn bộ document trong collection. `deleteMany` xóa các document khớp nhưng không xóa collection hay các index của nó.

## 6. Quan sát cùng dữ liệu bằng MongoDB Compass

Mở Compass và kết nối vào **cùng URI** mà `mongosh` đang sử dụng. Trong thanh điều hướng bên trái:

1. Chọn database `spring_data_training`.
2. Chọn collection `crud_lab_books`, mở tab **Documents**.
3. Nhập vào ô **Filter** đối tượng JSON tương ứng với marker mà `mongosh` đã in:

   ```json
   { "labRun": "setup-007-THAY_BANG_GIA_TRI_DA_IN" }
   ```

4. Áp dụng bộ lọc để chỉ nhìn thấy dữ liệu của lần chạy hiện tại.
5. Mở một document, kiểm tra `_id`, `tags`, `publisher`, `createdAt` và các giá trị mới sau thao tác cập nhật.

Chuỗi `setup-007-THAY_BANG_GIA_TRI_DA_IN` là **placeholder**: phải thay bằng toàn bộ chuỗi được in sau lệnh `print("Mã lần thực hành: " + labRun)`. Nếu dùng sai marker, Compass sẽ không thấy document nào dù kết nối thành công.

### 6.1. Tạo document trong Compass

Trong tab **Documents**, dùng chức năng **Add Data** / **Insert Document** (tên nút có thể khác theo phiên bản). Ví dụ tạo một bản ghi thử trực tiếp:

```json
{
  "labRun": "setup-007-THAY_BANG_GIA_TRI_DA_IN",
  "sku": "BK-COMPASS",
  "title": "Nhập dữ liệu từ Compass",
  "priceVnd": 75000,
  "stock": 1,
  "tags": ["compass"]
}
```

Sau khi nhấn **Insert**, quan sát `_id` do công cụ/server sinh ra. Document này cũng dùng đúng `labRun` nên có thể được dọn bằng bước `deleteMany({ labRun: labRun })`. Nếu đã tạo document Compass, các con số "dự kiến 3/4" trong các phần trước cần cộng thêm 1 từ thời điểm đó.

### 6.2. Tìm, sắp xếp và giới hạn kết quả

Từ cùng collection, sử dụng các ô lọc và tùy chọn của tab **Documents**:

| Điều muốn xem | Filter / Project / Sort tương ứng |
| --- | --- |
| Tất cả document của lần thực hành | Filter: `{ "labRun": "..." }` |
| Sách còn hàng | Filter: `{ "labRun": "...", "stock": { "$gt": 0 } }` |
| Sách của nhà xuất bản ở Việt Nam | Filter: `{ "labRun": "...", "publisher.country": "VN" }` |
| Chỉ xem tên và tồn kho | Project: `{ "title": 1, "stock": 1, "_id": 0 }` |
| Sắp xếp lượng tồn giảm dần | Sort: `{ "stock": -1 }` |
| Chỉ xem một số document | Điều chỉnh **Limit** nếu phiên bản Compass hiển thị tùy chọn này |

Ở các ô nhập JSON, cần dùng đúng cú pháp JSON/Extended JSON mà giao diện phiên bản đó chấp nhận. Truy vấn theo `ObjectId` có thể dùng dạng Extended JSON:

```json
{ "_id": { "$oid": "665f1f2a4b6c7d8e9f001234" } }
```

Giá trị ID ở đây chỉ là ví dụ; khi tìm document thật phải thay bằng `_id` mà bạn thấy. Trong `mongosh`, cách tương đương là `{ _id: ObjectId("...") }`.

### 6.3. Sửa và xóa từ giao diện

Để thử **Update**, lọc theo `labRun` và `sku`, mở document rồi dùng chức năng **Edit Document** hoặc biểu tượng chỉnh sửa, sửa `stock` từ giá trị hiện tại sang giá trị mới và lưu. Kiểm tra lại bằng:

```javascript
books.findOne(
  { labRun: labRun, sku: "BK-102" },
  { _id: 0, sku: 1, stock: 1 }
);
```

Để thử **Delete**, lọc đúng document `BK-COMPASS` đã tạo từ giao diện, chọn chức năng xóa và xác nhận. Sau đó kiểm tra bằng:

```javascript
books.countDocuments({
  labRun: labRun,
  sku: "BK-COMPASS"
}); // 0 nếu đã xóa đúng document.
```

Thao tác chỉnh sửa trực tiếp bằng Compass có thể bỏ qua quy tắc nghiệp vụ do ứng dụng Java thực thi. Chỉ làm vậy trên dữ liệu thử nghiệm; trong môi trường thật cần thống nhất cách cập nhật qua aggregate/service phù hợp.

### 6.4. Schema và Explain Plan

Ngoài tab Documents, Compass thường có các công cụ phân tích schema và kế hoạch thực thi truy vấn (tên tab/tính năng tùy phiên bản):

- **Schema**: xem các field xuất hiện, kiểu dữ liệu, phân bố giá trị trong **mẫu document** mà công cụ phân tích; đây không phải kiểm tra schema tuyệt đối trên toàn collection.
- **Explain Plan**: quan sát các stage của kế hoạch truy vấn, có thể thấy collection scan hoặc index scan và thống kê truy vấn tương ứng.
- **Indexes**: xem các index hiện hữu, trong đó có chỉ mục mặc định trên `_id`.

Không kết luận một index "tốt" chỉ vì có tên xuất hiện trong giao diện; hãy so sánh với mẫu truy vấn, tính chọn lọc và số document/key đã quét.

## 7. Quan sát query plan bằng mongosh

Với một bộ lọc thường dùng:

```javascript
books.find({
  labRun: labRun,
  sku: "BK-101"
}).explain("executionStats");
```

Khi chưa có index phù hợp, kế hoạch có thể cần duyệt nhiều document trong collection. Nếu muốn thử index ngay trên collection thực hành:

```javascript
books.createIndex(
  { labRun: 1, sku: 1 },
  { name: "idx_lab_run_sku" }
);

books.find({
  labRun: labRun,
  sku: "BK-101"
}).explain("executionStats");
```

Khi đọc kết quả, chú ý `winningPlan`, `totalKeysExamined`, `totalDocsExamined` và `nReturned`. MongoDB có thể chọn cách thực thi khác nhau tùy thống kê, phiên bản và lượng dữ liệu; tập ví dụ chỉ vài document nên chưa đủ để đo lợi ích index về hiệu năng. Trong ứng dụng thật, index nên được thiết kế theo truy vấn và kiểm thử bằng dữ liệu/tải đại diện.

**Ghi nhớ:** `explain` là công cụ quan sát cơ chế truy vấn. Nó không thay thế kiểm thử độ trễ, giám sát ứng dụng hoặc phân tích các truy vấn tốn tài nguyên trong môi trường vận hành.

## 8. Đối chiếu với Spring Data MongoDB

Khi thao tác qua Spring Data MongoDB, Java object được ánh xạ tới BSON document. Cùng một collection vừa chỉnh sửa qua `mongosh`/Compass có thể được đọc từ `MongoRepository` hoặc `MongoTemplate` nếu kết nối đến đúng database.

Ví dụ entity rút gọn đại diện cho các field chính:

```java
import java.util.Date;
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "crud_lab_books")
public class LabBook {
    @Id
    private ObjectId id;
    private String labRun;
    private String sku;
    private String title;
    private long priceVnd;
    private int stock;
    private List<String> tags;
    private Publisher publisher;
    private Date createdAt;
    private Date updatedAt;
    private String source;

    protected LabBook() {}

    public ObjectId getId() { return id; }
    public String getSku() { return sku; }
    public String getLabRun() { return labRun; }
    public String getTitle() { return title; }
    public int getStock() { return stock; }

    public static class Publisher {
        private String name;
        private String country;

        protected Publisher() {}
        public String getName() { return name; }
        public String getCountry() { return country; }
    }
}
```

Vì `@Id` ánh xạ `id` sang `_id`, repository dùng đúng kiểu ID của Java:

```java
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface LabBookRepository
        extends MongoRepository<LabBook, ObjectId> {
    List<LabBook> findByLabRun(String labRun);
    List<LabBook> findByLabRunAndStockGreaterThan(
        String labRun, int stock
    );
}
```

Trong service, `findByLabRun(...)` tương ứng về ý nghĩa với `books.find({ labRun: ... })`; `findById(...)` tương ứng với bộ lọc `_id`. Với `MongoTemplate`:

```java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public boolean reduceStock(
        MongoTemplate template, String labRun, String sku) {
    Query query = Query.query(
        Criteria.where("labRun").is(labRun)
                .and("sku").is(sku)
                .and("stock").gte(1)
    );
    Update update = new Update()
        .inc("stock", -1)
        .currentDate("updatedAt");

    return template.updateFirst(query, update, LabBook.class)
                   .getModifiedCount() == 1;
}
```

Lệnh trên giữ điều kiện kiểm tra tồn kho ngay trong thao tác cập nhật. Nếu sửa entity bằng `repository.save(entity)` sau khi đã đọc, hãy cân nhắc ghi đè thay đổi đồng thời; khi cần có thể dùng `@Version` và cơ chế optimistic locking.

**Lưu ý mapping:** `save` thường ghi lại trạng thái document từ entity. Nếu entity chỉ định nghĩa một vài field trong khi document thực tế có nhiều field khác, lưu lại entity có thể làm mất những field không được ánh xạ. Khi chỉ cần thay một trường trên dữ liệu đã có, hãy chọn thao tác cập nhật có điều kiện phù hợp hoặc dùng mapping đầy đủ.

### Bảng đối chiếu thao tác

| Nhu cầu | mongosh | Spring Data MongoDB |
| --- | --- | --- |
| Tạo một document | `insertOne(document)` | `repository.insert(entity)` hoặc `mongoTemplate.insert(entity)` |
| Lấy theo ID | `findOne({ _id: id })` | `repository.findById(id)` hoặc `mongoTemplate.findById(id, Type.class)` |
| Tìm nhiều document | `find(filter)` | Derived query của repository hoặc `mongoTemplate.find(query, Type.class)` |
| Cập nhật trường | `updateOne(filter, { $set: ... })` | `mongoTemplate.updateFirst(query, update, Type.class)` |
| Xóa theo điều kiện | `deleteOne(filter)` | `mongoTemplate.remove(query, Type.class)` hoặc xóa theo ID qua repository |
| Quan sát kết quả cập nhật | `matchedCount` / `modifiedCount` | `UpdateResult.getMatchedCount()` / `getModifiedCount()` |

Trong ứng dụng, ưu tiên gom thao tác trong service rõ trách nhiệm; code Java phải kiểm tra input, quyền truy cập, chuyển đổi kiểu ID và xử lý lỗi phù hợp.

## 9. Lỗi thường gặp khi thực hành CRUD

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `ECONNREFUSED` khi kết nối | MongoDB chưa chạy hoặc host/port sai | Kiểm tra server, URI, port và network |
| `Authentication failed` | Sai tài khoản, mật khẩu hoặc auth database | Kiểm tra cấu hình xác thực, tránh lộ bí mật trong log |
| `find()` không trả dữ liệu | Nhầm database, collection, `labRun` hoặc kiểu BSON | Kiểm tra `db.getName()`, tên collection, marker và `_id` |
| Truy vấn `_id` bằng chuỗi không khớp | Document dùng BSON ObjectId | Dùng `ObjectId("...")` hoặc đúng kiểu khi query |
| Lỗi `E11000 duplicate key` | `_id` hoặc unique index bị trùng | Đọc tên index trong lỗi; sửa chiến lược sinh/kiểm tra định danh |
| `matchedCount = 0` | Không có document thỏa bộ lọc hoặc điều kiện ghi | Đọc lại theo `labRun`, `sku`, điều kiện `stock` |
| `modifiedCount = 0` dù matched là 1 | Gán giá trị giống giá trị đang có | So sánh trước/sau, kiểm tra update operators |
| Dữ liệu xuất hiện khác nhau ở Compass và mongosh | Không cùng cluster/database hoặc bộ lọc khác | So sánh URI, database, collection và filter |
| Sửa document lồng nhau làm mất trường | Thay toàn bộ object con hoặc dùng replace sai | Sửa bằng dot notation hoặc cập nhật chủ động toàn object |
| Xóa nhầm nhiều dữ liệu | Bộ lọc xóa quá rộng | Luôn xem `countDocuments(filter)` trước và dùng marker/ID cụ thể |

MongoDB không thực thi mọi quy tắc nghiệp vụ thay cho ứng dụng. Ví dụ cập nhật `stock` thành số âm vẫn có thể thành công nếu không có điều kiện ghi, validator hoặc quy tắc khác ngăn lại. Dữ liệu thử nghiệm giúp bạn quan sát chính xác hành vi của lệnh, còn ứng dụng cần bổ sung lớp kiểm tra và kiểm thử thích hợp.

## 10. Bài tập tự luyện

**Bài 1 — CRUD đầy đủ.** Tạo một document mới với `sku: "BK-EX-01"` và `labRun` hiện tại, đọc lại theo ID, sửa `stock` từ 3 thành 5 và xóa chỉ document đó. Sau mỗi bước, quan sát kết quả bằng cả mongosh và Compass.

**Bài 2 — Lọc và projection.** Viết truy vấn lấy các sách có `stock >= 1`, chỉ hiển thị `sku`, `title`, `priceVnd`, sắp xếp giá giảm dần. Giải thích tại sao phải giữ bộ lọc `labRun`.

**Bài 3 — Thử cập nhật có điều kiện.** Cho `BK-103` tồn kho 0. Thử `$inc: {stock: -1}` với bộ lọc `stock: {$gte: 1}`; giải thích vì sao kết quả `matchedCount` bằng 0. Sau đó thêm hàng bằng `$inc: {stock: 5}` và thử lại.

**Bài 4 — Quan sát kiểu.** Dùng Compass xem `ObjectId`, ngày tháng, mảng `tags` và document con `publisher`. Viết lại bộ lọc theo `_id` trong mongosh, nêu khác biệt giữa giá trị ObjectId và chuỗi hex.

**Bài 5 — Kết nối Java.** Tạo repository `LabBookRepository`, gọi `findByLabRun` với marker đang dùng và so sánh số document với `countDocuments` trong mongosh. Thử cập nhật tồn kho qua `MongoTemplate` rồi refresh Compass.

**Bài 6 — Đọc kế hoạch truy vấn.** Chạy `explain("executionStats")` cho truy vấn `labRun + sku` trước và sau khi tạo index ghép. So sánh `totalDocsExamined` và `totalKeysExamined`; giải thích vì sao kết quả trên vài document không đủ để kết luận về hiệu năng ở production.

### Tự kiểm tra kết quả

Nếu chạy tuần tự các lệnh chính của bài **và chưa thêm/xóa/sửa dữ liệu từ Compass**:

1. Sau `insertMany`: có **3** document theo `labRun`.
2. Sau `insertOne`: có **4** document.
3. Sau `updateOne` đầu tiên: `BK-101.stock` từ **10 xuống 8**.
4. Sau `updateMany`: cả **4** document có `source: "setup-007"`.
5. Sau `deleteOne` cho `BK-104`: còn **3** document.
6. Sau `deleteMany({labRun})` ở bước dọn dữ liệu: còn **0** document của lần thực hành đó.

Các lệnh sửa tích lũy như `$inc` thay đổi kết quả khi chạy lại. Hãy dùng marker mới cho mỗi lần làm từ đầu và kiểm tra dữ liệu trước khi cập nhật hoặc dọn dẹp.

### Ghi nhớ

Vòng **Create – Read – Update – Delete** giúp bạn kiểm tra toàn bộ đường đi của dữ liệu từ lệnh ghi đến document BSON được lưu. `mongosh` thuận tiện để chạy lệnh chính xác và xem kết quả; Compass thuận tiện để trực quan hóa document, kiểu dữ liệu, truy vấn và chỉ mục. Khi chuyển sang Spring Data MongoDB, các nguyên tắc vẫn giữ nguyên: **lọc đúng dữ liệu, dùng đúng kiểu BSON, kiểm tra số document được tác động, cập nhật có điều kiện và xác nhận kết quả** trước khi đưa thao tác vào logic nghiệp vụ.

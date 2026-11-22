# Unique index: dữ liệu trùng, null và trường không tồn tại

Trong MongoDB, **unique index** không chỉ giúp tìm kiếm dữ liệu: nó còn thực thi một **ràng buộc tính duy nhất (uniqueness constraint)** đối với các giá trị khóa được lập chỉ mục. Nhờ đó, database có thể ngăn hai tài khoản sử dụng cùng username, ngăn hai bản ghi có cùng mã đơn hàng hoặc bảo đảm một mã SKU chỉ xuất hiện một lần trong phạm vi cửa hàng. Tuy nhiên, khi field có thể **`null`**, **không tồn tại (missing)**, là **array**, hoặc là một phần của **compound index**, hành vi thường không giống suy đoán từ SQL.

Bài thuộc chương **Index chuyên biệt** của module *Database Engine Document MongoDB*, tập trung vào ba vấn đề cốt lõi: **giá trị trùng được xử lý ra sao, `null` khác missing thế nào, và cần thiết kế index gì để đúng với nghiệp vụ**. Bài cũng mở rộng sang **unique sparse index**, **unique partial index**, **compound unique index**, **collation**, **multikey**, **sharding** và việc triển khai trên collection đang có dữ liệu.

Sau bài học, bạn có thể:

1. Tạo và giải thích kết quả của single-field/compound unique index.
2. Nhận diện lỗi **`E11000 duplicate key`** khi insert, update, replace và upsert.
3. Giải thích chính xác vì sao **unique index thông thường chỉ cho phép một khóa `null`/missing** trên một field.
4. Chọn **sparse** hay **partialFilterExpression** để cho phép nhiều document thiếu field mà vẫn hạn chế giá trị trùng.
5. Thiết kế uniqueness theo phạm vi **tenant**, **trạng thái**, **case-insensitive** hoặc nhiều field.
6. Hiểu các giới hạn của unique multikey index và unique index trên sharded collection.
7. Khảo sát dữ liệu trùng trước khi tạo index, triển khai có kế hoạch và xử lý race condition đúng ở ứng dụng.

> **Phiên bản và môi trường:** Ví dụ chủ yếu dùng các API đã phổ biến trong MongoDB 7.0/8.0 và những phiên bản mới tương thích. Một số khả năng quản trị index hoặc ràng buộc trên sharded collection phụ thuộc phiên bản/FCV; khi áp dụng production hãy xem **MongoDB Database Manual của server đang chạy**. Mọi đoạn demo bên dưới dùng database riêng `unique_index_lab`; không chạy lệnh xóa, tạo index hoặc sửa dữ liệu lên collection production nếu chưa xác định quyền sở hữu và tác động.

## 1. Unique index là gì?

Một index thông thường giúp MongoDB định vị document theo giá trị khóa. Thêm tùy chọn **`unique: true`** khiến database **không chấp nhận hai document khác nhau sinh ra cùng một giá trị index key**, theo ngữ nghĩa loại index và các tùy chọn như collation, partial filter.

~~~javascript
db.getSiblingDB("unique_index_lab").users.createIndex(
  { username: 1 },
  { unique: true }
)
~~~

Trong ví dụ:

- `{ username: 1 }` là index key specification; `1` nghĩa là hướng tăng dần.
- `{ unique: true }` là index option thực thi tính duy nhất.
- Nếu document mới có username trùng với document đã có trong cùng phạm vi index, write sẽ thất bại.
- MongoDB kiểm tra ràng buộc **khi ghi**, không chỉ lúc chạy câu lệnh truy vấn.
- Tính duy nhất được đánh giá theo **giá trị khóa BSON** và các tùy chọn index; không nhất thiết giống thao tác so sánh chuỗi tùy ý của ứng dụng.

### 1.1. Khác index thông thường thế nào?

| Đặc điểm | Index thường | Unique index |
|---|---|---|
| Hỗ trợ lọc/tìm kiếm | Có | Có |
| Hai document khác nhau có cùng indexed key | Được phép | Bị cấm trong phạm vi index |
| Ngăn insert trùng business key | Không | Có |
| Ngăn update đổi khóa sang giá trị đã có | Không | Có |
| Chặn duplicate khi tạo index trên dữ liệu cũ | Không | Có; index build thất bại nếu dữ liệu hiện tại vi phạm |
| Cho phép nhiều field missing trong single-field index thông thường | Có | Không, trừ khi dùng cấu hình như sparse/partial thích hợp |

**Unique index không tạo foreign key**, không kiểm tra một giá trị có tồn tại trong collection khác, và không thay thế schema validation để đảm bảo field bắt buộc đúng kiểu.

### 1.2. Phân biệt `_id` và business key

MongoDB tự tạo **unique index trên `_id`** khi tạo collection thông thường. `_id` là định danh của document, nhưng nghiệp vụ có thể cần thêm uniqueness:

~~~javascript
// Hai document có _id khác nhau nhưng username trùng.
{ _id: "U-1", username: "an" }
{ _id: "U-2", username: "an" }
~~~

Nếu collection chỉ có index mặc định trên `_id`, hai document trên không vi phạm tính duy nhất của `_id`. Muốn username duy nhất cần một index độc lập trên `username`.

Ngược lại, đặt `unique: true` trên username không tự làm username **bắt buộc**, không buộc nó là string, không chuẩn hóa hoa/thường hay khoảng trắng. Những yêu cầu đó phải được xử lý bằng **schema validation**, quy tắc ứng dụng và/hoặc **collation** phù hợp.

## 2. Bộ dữ liệu và cách chạy ví dụ

Để tránh lẫn dữ liệu, mỗi thí nghiệm sẽ dùng một collection có tên khác nhau trong `unique_index_lab`. Ví dụ A sẽ tạo `usersBasic`, ví dụ B tạo `usersSparse`, ví dụ C tạo `usersPartial`... Mỗi ví dụ được thiết kế để chạy lần đầu trên collection **chưa tồn tại** hoặc **đang trống**.

~~~javascript
const lab = db.getSiblingDB("unique_index_lab")
~~~

Nếu chạy lại một thí nghiệm trên cùng collection, bạn có thể gặp duplicate `_id` hoặc unique index, vì dữ liệu từ lần trước vẫn còn. Có thể chọn tên collection lab mới hoặc chủ động reset **chính collection demo** khi chắc chắn đó không phải dữ liệu người khác. Không dùng `db.dropDatabase()` trên môi trường chia sẻ chỉ để thực hành.

Để xem các index:

~~~javascript
lab.usersBasic.getIndexes()
~~~

Để quan sát kết quả và loại lỗi, dùng `try/catch`:

~~~javascript
try {
  // Lệnh ghi được thử nghiệm ở đây.
} catch (err) {
  print("code=" + err.code)
  print("codeName=" + err.codeName)
  print(err.message)
}
~~~

Thông báo lỗi, thông tin khóa gây trùng và hình dạng exception có thể khác nhau theo MongoDB version/driver. Trong nhiều tình huống duplicate key, code là **11000** và tên lỗi là **`DuplicateKey`**.

## 3. Single-field unique index và dữ liệu trùng

### 3.1. Tạo index trước khi insert

~~~javascript
const lab = db.getSiblingDB("unique_index_lab")

lab.usersBasic.createIndex(
  { username: 1 },
  { unique: true, name: "ux_username" }
)

lab.usersBasic.insertOne({
  _id: "U1",
  username: "an",
  displayName: "An"
})

lab.usersBasic.insertOne({
  _id: "U2",
  username: "binh",
  displayName: "Bình"
})
~~~

Hai insert hợp lệ vì `"an"` và `"binh"` khác nhau.

### 3.2. Insert dữ liệu có cùng khóa

~~~javascript
try {
  lab.usersBasic.insertOne({
    _id: "U3",
    username: "an",
    displayName: "An khác"
  })
} catch (err) {
  print(err.code)      // Thường là 11000.
  print(err.codeName)  // Thường là DuplicateKey.
  print(err.message)
}
~~~

`U3` có `_id` khác U1, nhưng unique index trên `username` từ chối vì cả hai có khóa `username = "an"`. Điều này khác duplicate `_id`: lỗi vẫn có thể là 11000 nhưng index name/key gây trùng khác nhau.

### 3.3. Update cũng có thể vi phạm

~~~javascript
try {
  lab.usersBasic.updateOne(
    { _id: "U2" },
    { $set: { username: "an" } }
  )
} catch (err) {
  print(err.message)
}
~~~

MongoDB không cho U2 đổi username thành giá trị đã thuộc U1. Khi write thất bại, thao tác đó không tạo trạng thái hai document trùng username.

Hành vi tương tự có thể xảy ra với:

- `replaceOne` có replacement mang khóa đã tồn tại;
- `updateMany` khiến nhiều document đổi về cùng giá trị;
- `upsert` tạo document mới có khóa trùng do race condition;
- `bulkWrite` chứa nhiều thao tác cạnh tranh một unique key;
- tác vụ import/restore/migration chèn dữ liệu không đạt uniqueness.

Không chỉ `insertOne` mới có thể nhận lỗi unique constraint.

### 3.4. Vì sao không nên chỉ “find trước, insert sau”?

Một kiểu code dễ gặp:

~~~javascript
const existing = lab.usersBasic.findOne({ username: "lan" })

if (!existing) {
  lab.usersBasic.insertOne({
    _id: "U4",
    username: "lan"
  })
}
~~~

Đoạn code này có **race condition**:

~~~text
Client A: find("lan") -> không thấy
Client B: find("lan") -> không thấy
Client A: insert("lan") -> thành công
Client B: insert("lan") -> trùng khóa, bị chặn
~~~

**Unique index mới là điểm bảo vệ tính duy nhất ở database**. Việc kiểm tra trước khi insert chỉ giúp UX (ví dụ “username đã được sử dụng”); nó không thay thế việc xử lý `E11000` ở đường ghi.

Ứng dụng nên phân loại lỗi 11000 dựa trên **index/key gây trùng**, trả lỗi nghiệp vụ phù hợp, và không retry vô hạn cùng dữ liệu trùng.

## 4. Điểm quan trọng nhất: `null` khác field không tồn tại

MongoDB phân biệt:

~~~javascript
// Field có mặt, giá trị là BSON null.
{ _id: "A", email: null }

// Field hoàn toàn không có.
{ _id: "B" }

// Field có mặt, kiểu string.
{ _id: "C", email: "an@example.test" }
~~~

Ở tầng document:

- `email: null`: field **tồn tại** với giá trị BSON **null**.
- Missing: field `email` **không có trong document**.
- `email: ""`: field tồn tại với **chuỗi rỗng**, cũng không phải null.
- `email: "null"`: string có bốn ký tự; không phải BSON null.

Nhưng khi MongoDB tạo **single-field unique index thông thường** trên `email`, cả document có `email: null` và document **không có `email`** đều có **index entry mang giá trị khóa null**. Vì vậy chỉ có thể có **một document** thuộc nhóm này trong phạm vi index.

### 4.1. Thực nghiệm: một null, một missing

~~~javascript
const lab = db.getSiblingDB("unique_index_lab")

lab.usersNull.createIndex(
  { email: 1 },
  { unique: true, name: "ux_email" }
)

lab.usersNull.insertOne({ _id: "N1", email: null })

try {
  lab.usersNull.insertOne({ _id: "N2" })
} catch (err) {
  print(err.code)    // Thường 11000.
  print(err.message) // Khóa null trùng.
}
~~~

`N2` thiếu `email`, nhưng bị từ chối vì `N1` đã chiếm unique index key `null`. Thứ tự ngược cũng cho kết quả tương tự:

~~~javascript
// Tạo một collection lab khác.
lab.usersMissingFirst.createIndex(
  { email: 1 },
  { unique: true }
)

lab.usersMissingFirst.insertOne({ _id: "M1" })

try {
  lab.usersMissingFirst.insertOne({ _id: "M2", email: null })
} catch (err) {
  print(err.message)
}
~~~

Document thiếu field đã tạo unique key null; insert có explicit `null` sau đó cũng va chạm.

### 4.2. Bảng dự đoán cho unique index trên một field

Giả sử collection ban đầu trống và có index `{email:1}` unique, không sparse/partial:

| Thao tác theo thứ tự | Giá trị khóa trên index | Kết quả |
|---|---|---|
| Insert `{_id:1,email:"a@example.test"}` | `"a@example.test"` | Thành công. |
| Insert `{_id:2,email:"b@example.test"}` | `"b@example.test"` | Thành công. |
| Insert `{_id:3,email:"a@example.test"}` | `"a@example.test"` | **Duplicate key**. |
| Insert `{_id:4,email:null}` | `null` | Thành công, nếu chưa có null/missing. |
| Insert `{_id:5}` | `null` | **Duplicate key** vì `_id:4` đã giữ key null. |
| Insert `{_id:6,email:""}` | `""` | Thành công, nếu chưa có chuỗi rỗng. |
| Insert `{_id:7,email:""}` | `""` | **Duplicate key** vì trùng chuỗi rỗng. |

**Kết luận quan trọng:** unique index đơn trường **không đồng nghĩa** “có thể có bao nhiêu email thiếu cũng được, miễn email có giá trị là duy nhất”. Đó là yêu cầu **khác** và cần index khác, thường là **partial** hoặc **sparse**.

### 4.3. `null` trong truy vấn không giống nhận định về uniqueness

Trong MongoDB query language, equality `{email: null}` thông thường khớp document có `email: null` **hoặc** không có field `email`:

~~~javascript
lab.usersNull.find({ email: null })
~~~

Muốn phân biệt hai trạng thái trong dữ liệu:

~~~javascript
// Email hoàn toàn không có:
lab.usersNull.find({ email: { $exists: false } })

// Email có mặt và có BSON type null:
lab.usersNull.find({ email: { $type: "null" } })

// Email có mặt, không phải null:
lab.usersNull.find({
  email: { $exists: true, $ne: null }
})
~~~

Truy vấn phân biệt missing/null giúp **phân tích dữ liệu**, nhưng không tự thay đổi cách index unique thông thường tạo khóa. Một code filter có vẻ phân biệt được missing/null không làm database tự phân biệt chúng khi **lập index key**.

## 5. Unique index khi dữ liệu cũ đã bị trùng

Tạo unique index trên collection đang có hai document cùng khóa sẽ thất bại:

~~~javascript
const lab = db.getSiblingDB("unique_index_lab")

lab.usersDirty.insertMany([
  { _id: "D1", username: "mai" },
  { _id: "D2", username: "mai" },
  { _id: "D3", username: "hung" }
])

try {
  lab.usersDirty.createIndex(
    { username: 1 },
    { unique: true }
  )
} catch (err) {
  print("Index build failed: " + err.message)
}
~~~

MongoDB **không tự xóa hoặc gộp** document trùng để hoàn thành index build. Phải giải quyết dữ liệu vi phạm trước, hoặc sửa lại định nghĩa business key/index cho đúng nghiệp vụ.

### 5.1. Tìm các giá trị trùng bằng aggregation

~~~javascript
lab.usersDirty.aggregate([
  {
    $group: {
      _id: "$username",
      count: { $sum: 1 },
      ids: { $push: "$_id" }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $sort: { count: -1 } }
])
// Một nhóm _id = "mai", count = 2, ids = ["D1", "D2"].
~~~

Với collection lớn, `$push` **mọi ID** vào một array có thể vượt giới hạn bộ nhớ/kích thước document kết quả; nên tách bước **đếm nhóm trùng** và bước **lấy mẫu ID** hoặc xử lý theo batch. Ví dụ dưới đây đếm mà không giữ toàn bộ ID:

~~~javascript
lab.usersDirty.aggregate([
  { $group: { _id: "$username", count: { $sum: 1 } } },
  { $match: { count: { $gt: 1 } } },
  { $sort: { count: -1 } },
  { $limit: 20 }
])
~~~

**Phải tìm cả nhóm null/missing**. Một aggregation `$group` theo `"$email"` có thể gom các document có giá trị null và thiếu field vào cùng nhóm tương ứng, nhưng báo cáo dữ liệu nên phân loại rõ **explicit null** và **missing** để quyết định chính sách.

### 5.2. Khi nào được xóa dữ liệu trùng?

Không có quy tắc “giữ document mới nhất” dùng được cho mọi domain. Với user/account hoặc order, hai document trùng business key có thể đang chứa giao dịch, audit hay liên kết khác nhau. Cần:

1. Xác định **source of truth** và định nghĩa thế nào là “trùng thật”.
2. Xem reference từ collection khác và logic nghiệp vụ liên quan.
3. Chọn merge/rename/archive/reassign key/xóa dựa trên policy.
4. Lưu ánh xạ ID nếu cần chuyển references.
5. Chặn/điều phối những writers còn tạo giá trị trùng trong lúc dọn dữ liệu.
6. Chỉ tạo unique index khi dữ liệu đã đạt bất biến.

Nếu một job xóa document theo `username` mà không dùng ID cụ thể, nó có thể xóa cả bản đúng. Việc “dọn duplicate trước khi xây index” thường là **data migration có kiểm soát**, không phải một `deleteMany` vô điều kiện.

## 6. Unique sparse index: cho phép nhiều document **thiếu field**

**Sparse index** chỉ lập chỉ mục cho document có chứa indexed field phù hợp; với single-field index, document **hoàn toàn thiếu field** sẽ không có index entry. Vì thế một **unique sparse index** cho phép **nhiều document thiếu field**, nhưng **explicit `null` vẫn được lập chỉ mục** khi field có mặt.

~~~javascript
const lab = db.getSiblingDB("unique_index_lab")

lab.usersSparse.createIndex(
  { email: 1 },
  {
    unique: true,
    sparse: true,
    name: "ux_email_sparse"
  }
)
~~~

### 6.1. Thử insert missing, null và string

~~~javascript
// Hai document không có email: được phép.
lab.usersSparse.insertOne({ _id: "S1", name: "An" })
lab.usersSparse.insertOne({ _id: "S2", name: "Bình" })

// Email explicit null thứ nhất: được phép.
lab.usersSparse.insertOne({ _id: "S3", email: null })

// Email explicit null thứ hai: trùng index key null.
try {
  lab.usersSparse.insertOne({ _id: "S4", email: null })
} catch (err) {
  print(err.code)      // Thường 11000.
  print(err.message)
}

// Hai email khác nhau: được phép.
lab.usersSparse.insertOne({
  _id: "S5",
  email: "an@example.test"
})
lab.usersSparse.insertOne({
  _id: "S6",
  email: "binh@example.test"
})

// Email trùng S5: bị từ chối.
try {
  lab.usersSparse.insertOne({
    _id: "S7",
    email: "an@example.test"
  })
} catch (err) {
  print(err.message)
}
~~~

Kết quả tổng quát:

| Dạng `email` | Unique **không sparse** | Unique **sparse** |
|---|---|---|
| Không có `email` | Tạo key null; chỉ một document trong nhóm null/missing. | **Không vào index**; nhiều document thiếu field được phép. |
| `email: null` | Tạo key null; chỉ một trong nhóm null/missing. | **Có vào index**; chỉ một explicit null. |
| `email: "a@example.test"` | Chỉ một khóa giá trị này. | Chỉ một khóa giá trị này. |
| `email: ""` | Chỉ một chuỗi rỗng. | Chỉ một chuỗi rỗng. |

**Điểm mấu chốt:** `sparse: true` không có nghĩa “bỏ qua null”. Nó bỏ qua document **thiếu field** trong trường hợp single-field index, còn document chứa `null` vẫn bị ràng buộc.

### 6.2. Khi nào sparse phù hợp?

Sparse có thể phù hợp khi:

- Field **thật sự không tồn tại** trên phần lớn document chưa hoàn tất đăng ký.
- Nghiệp vụ chấp nhận nhiều document thiếu field nhưng chỉ cho phép **tối đa một document có explicit null**.
- Schema và writers quy định rõ “chưa có giá trị” phải **bỏ field**, không ghi `null`.

Nếu hệ thống đồng thời dùng cả missing lẫn explicit null để biểu diễn “chưa có email”, unique sparse có thể vẫn tạo lỗi không mong muốn. Khi đó **unique partial index** thường linh hoạt và diễn đạt đúng nghiệp vụ hơn.

### 6.3. Sparse và hiệu năng truy vấn

Vì sparse index **không chứa mọi document**, MongoDB không thể luôn dùng nó cho một truy vấn mà việc sử dụng index sẽ khiến kết quả thiếu các document không được index. Query planner cân nhắc điều kiện truy vấn; có thể dùng `hint` trong tình huống đặc biệt nhưng phải hiểu tác động đến kết quả.

Ví dụ: đếm mọi document trong collection bằng cách chỉ quét sparse index có thể **bỏ sót document thiếu email**. Không xem sparse index như một bản liệt kê đầy đủ mọi `_id`.

## 7. Unique partial index: quy định chính xác document nào được ràng buộc

**Partial index** chỉ chứa document thỏa **`partialFilterExpression`**. Kết hợp `unique: true` sẽ thực thi uniqueness **chỉ trong tập document được lập chỉ mục**. Đây là công cụ mạnh để biểu diễn “email phải duy nhất khi thực sự là string”, hoặc “username duy nhất chỉ với tài khoản ACTIVE”.

### 7.1. Chỉ ràng buộc email kiểu string, bỏ qua missing/null

~~~javascript
const lab = db.getSiblingDB("unique_index_lab")

lab.usersPartial.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    },
    name: "ux_email_when_string"
  }
)
~~~

Với thiết kế này:

- Document **thiếu email** không thỏa partial filter ⇒ không vào index.
- Document có `email: null` không thỏa `$type: "string"` ⇒ không vào index.
- Document có email string, kể cả `""`, thỏa filter ⇒ phải unique.
- Document có kiểu email không phải string, ví dụ số, **cũng không vào index** — cần schema validation nếu kiểu số là dữ liệu không hợp lệ.

~~~javascript
lab.usersPartial.insertMany([
  { _id: "P1", name: "An" },
  { _id: "P2", name: "Bình" },
  { _id: "P3", email: null },
  { _id: "P4", email: null },
  { _id: "P5", email: "an@example.test" },
  { _id: "P6", email: "binh@example.test" }
])

try {
  lab.usersPartial.insertOne({
    _id: "P7",
    email: "an@example.test"
  })
} catch (err) {
  print(err.code) // 11000.
}
~~~

Các document P1–P6 hợp ràng buộc index, dù có hai missing và hai explicit null. P7 bị từ chối vì `"an@example.test"` đã tồn tại trong **tập được index**.

> **Phân biệt index và schema:** Partial unique index nói rằng **nếu email là string thì string phải unique**. Nó **không** nói rằng email buộc phải là string. Nên dùng thêm schema validation nếu muốn bác bỏ email là số/object/array hoặc chuỗi rỗng.

### 7.2. Vì sao `$exists: true` chưa đủ để bỏ qua null?

Một partial filter khác:

~~~javascript
lab.usersExists.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $exists: true }
    }
  }
)
~~~

Nó chỉ loại **document thiếu `email`**. Với `email: null`, field vẫn **tồn tại**, nên document đi vào index và explicit null vẫn phải unique:

~~~javascript
lab.usersExists.insertOne({ _id: "E1" })
lab.usersExists.insertOne({ _id: "E2" }) // Được phép: cùng thiếu email.

lab.usersExists.insertOne({ _id: "E3", email: null })

try {
  lab.usersExists.insertOne({ _id: "E4", email: null })
} catch (err) {
  print(err.code) // 11000 vì cả E3/E4 có email hiện diện và null.
}
~~~

Do đó, khi yêu cầu là **“bỏ qua cả missing và null”**, hãy xác định kiểu/giá trị hợp lệ một cách rõ ràng, ví dụ `$type: "string"` kết hợp schema. Không chỉ thay `sparse` bằng `partialFilterExpression: { email: { $exists: true } }` rồi mong hành vi null thay đổi.

### 7.3. So sánh non-sparse, sparse và partial

| Index | Missing nhiều document | `null` nhiều document | String trùng nhau |
|---|---|---|---|
| `{email:1}, unique:true` | **Không** | **Không** | **Không** |
| `{email:1}, unique:true, sparse:true` | **Có** | **Không** | **Không** |
| Unique + partial `{email:{$exists:true}}` | **Có** | **Không** | **Không** |
| Unique + partial `{email:{$type:"string"}}` | **Có** | **Có** | **Không** |

Đây là bảng cho trường hợp **email là field đơn** và không có điều kiện collation khác. Với **array/multikey** hoặc compound index, ngữ nghĩa phát sinh index keys phức tạp hơn; xem các phần sau.

### 7.4. Partial uniqueness theo trạng thái nghiệp vụ

Giả sử tài khoản đã xóa mềm được phép giữ username trùng với tài khoản hiện tại; nhưng trong số tài khoản đang ACTIVE, username phải duy nhất.

~~~javascript
lab.accountsActive.createIndex(
  { username: 1 },
  {
    unique: true,
    partialFilterExpression: {
      status: "ACTIVE"
    },
    name: "ux_username_active"
  }
)
~~~

Thử:

~~~javascript
lab.accountsActive.insertMany([
  { _id: "A1", username: "lan", status: "DELETED" },
  { _id: "A2", username: "lan", status: "DELETED" },
  { _id: "A3", username: "lan", status: "ACTIVE" }
])

try {
  lab.accountsActive.insertOne({
    _id: "A4",
    username: "lan",
    status: "ACTIVE"
  })
} catch (err) {
  print(err.code) // 11000: trùng username trong nhóm ACTIVE.
}
~~~

Nếu update A1 từ `DELETED` sang `ACTIVE` mà username vẫn là `"lan"`, thao tác sẽ **bị chặn** vì document này vừa bắt đầu tham gia unique partial index và đụng khóa của A3.

**Hệ quả thiết kế:** Partial index không chỉ kiểm tra tại insert. **Update làm một document đi vào/ra tập partial filter** có thể thêm/xóa index keys và gây duplicate key tương ứng.

### 7.5. Index partial và query planner

Một query muốn sử dụng partial index phải có điều kiện bảo đảm kết quả truy vấn **không cần các document ngoài tập được index**. Ví dụ với index partial `status: "ACTIVE"`:

~~~javascript
// Query có cùng điều kiện lọc:
lab.accountsActive.find({
  status: "ACTIVE",
  username: "lan"
})
~~~

Đây là một ứng viên hợp lý để dùng partial index. Ngược lại:

~~~javascript
// Query này muốn tìm cả ACTIVE lẫn DELETED:
lab.accountsActive.find({ username: "lan" })
~~~

Server không thể mặc định trả kết quả đầy đủ chỉ bằng index chứa **ACTIVE**. Vì vậy partial index không chỉ là kỹ thuật constraint; nó còn ảnh hưởng cách thiết kế index cho các access patterns đọc. Dùng `explain()` trên dữ liệu đại diện thay vì giả định mọi query trên `username` đều dùng index partial.

### 7.6. Cú pháp và giới hạn partialFilterExpression

MongoDB chỉ cho phép một **tập nhất định các biểu thức** trong `partialFilterExpression`; không phải mọi aggregation expression hoặc query operator đều được hỗ trợ. Những mẫu thông dụng gồm equality, `$exists: true`, so sánh range, `$type`, `$and`, `$or` và `$in` ở các phiên bản có hỗ trợ.

Không đặt tùy tiện `$expr` hoặc mọi phép kiểm tra regex phức tạp vào partial filter mà chưa tra tài liệu. Ngoài ra, không được dùng **`sparse: true` và `partialFilterExpression` đồng thời trên cùng index**. Nếu cần điều kiện phức tạp hơn sparse, dùng partial index và định nghĩa logic một lần.

## 8. Compound unique index: uniqueness trên **bộ giá trị**, không từng field riêng

Một **compound unique index** có từ hai indexed fields trở lên:

~~~javascript
lab.ordersPerTenant.createIndex(
  { tenantId: 1, orderNo: 1 },
  {
    unique: true,
    name: "ux_tenant_orderNo"
  }
)
~~~

MongoDB yêu cầu **tổ hợp (`tenantId`, `orderNo`)** là duy nhất. Điều đó **không** có nghĩa mỗi `tenantId` chỉ có một order hoặc `orderNo` phải là duy nhất trên toàn hệ thống.

~~~javascript
lab.ordersPerTenant.insertMany([
  { _id: "T1-O1", tenantId: "T1", orderNo: "001" },
  { _id: "T1-O2", tenantId: "T1", orderNo: "002" },
  { _id: "T2-O1", tenantId: "T2", orderNo: "001" }
])

try {
  lab.ordersPerTenant.insertOne({
    _id: "T1-O1-DUP",
    tenantId: "T1",
    orderNo: "001"
  })
} catch (err) {
  print(err.code) // 11000: trùng cặp T1 / 001.
}
~~~

Hai tenant có thể có cùng số đơn `"001"` vì **tenantId khác nhau**. Ngược lại, trong T1 không thể có hai `orderNo = "001"`.

### 8.1. Null/missing trong compound unique index

Đối với compound index, một field thiếu/null có thể tạo **thành phần null** của tuple index key. Constraint kiểm tra **toàn bộ tuple**, không chỉ số document thiếu một field.

Ví dụ:

~~~javascript
lab.compoundNull.createIndex(
  { tenantId: 1, email: 1 },
  { unique: true }
)

lab.compoundNull.insertOne({
  _id: "C1",
  tenantId: "T1"
})
// Index key tương ứng: ("T1", null)

lab.compoundNull.insertOne({
  _id: "C2",
  tenantId: "T2"
})
// Index key tương ứng: ("T2", null), khác C1.

try {
  lab.compoundNull.insertOne({
    _id: "C3",
    tenantId: "T1",
    email: null
  })
} catch (err) {
  print(err.code) // Trùng tuple ("T1", null).
}
~~~

Vì vậy:

- **Có thể có nhiều document thiếu email** trên toàn collection nếu **các field khác trong tuple khác nhau**.
- **Không thể có hai document sinh cùng tuple**, chẳng hạn cùng `tenantId = "T1"` và email missing/null.
- Nếu toàn bộ field trong index đều missing/null, chỉ một document có thể giữ tuple toàn null.

### 8.2. Một bảng ví dụ compound null

Giả sử có unique index `{tenantId:1,email:1}` không sparse/partial:

| Document | Tuple key | Hợp lệ sau các bước trước? |
|---|---|---|
| `{tenantId:"A",email:"x@test"}` | `("A","x@test")` | Có. |
| `{tenantId:"B",email:"x@test"}` | `("B","x@test")` | Có; tenant khác. |
| `{tenantId:"A",email:"x@test"}` lần nữa | `("A","x@test")` | Không; duplicate tuple. |
| `{tenantId:"A"}` | `("A",null)` | Có nếu tuple chưa xuất hiện. |
| `{tenantId:"B"}` | `("B",null)` | Có; khác tuple. |
| `{tenantId:"A",email:null}` | `("A",null)` | Không; trùng document thiếu email của tenant A. |
| `{tenantId:"C",email:null}` | `("C",null)` | Có; khác tuple. |

**Đây là khác biệt lớn so với unique index đơn trường:** single-field unique trên email có thể cho **một khóa null trên toàn collection**; compound unique có thể có nhiều tuple chứa null miễn các thành phần khác khiến tuple khác nhau.

### 8.3. Cạm bẫy: compound **sparse** không bỏ qua email missing nếu tenantId có mặt

Một người muốn “email là duy nhất trong từng tenant nhưng có thể thiếu” có thể thử:

~~~javascript
lab.badSparseComposite.createIndex(
  { tenantId: 1, email: 1 },
  { unique: true, sparse: true }
)
~~~

Đây **không** là giải pháp mặc định đúng. Với compound sparse index gồm các trường tăng/giảm thông thường, document có thể được lập chỉ mục khi **ít nhất một indexed field hiện diện**. Nếu `tenantId` luôn có, document **thiếu email** vẫn có thể được index với tuple `(tenantId, null)`, gây duplicate key cho document thiếu email thứ hai trong cùng tenant.

Khi muốn chỉ áp uniqueness nếu email thực sự là string, hãy dùng **compound unique partial index**:

~~~javascript
lab.accountsTenant.createIndex(
  { tenantId: 1, email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    },
    name: "ux_tenant_email_when_string"
  }
)
~~~

Nếu ứng dụng bảo đảm `tenantId` bắt buộc và đúng kiểu (bằng schema validation), index này thực thi: “**Trong cùng tenant, mỗi email string chỉ thuộc một account**; các account chưa có email được phép nhiều”. Nếu `tenantId` thiếu, những document có email string vẫn được index với thành phần null; do đó phải kiểm soát schema `tenantId`, không mặc nhiên coi index tự làm nó bắt buộc.

### 8.4. Thứ tự field trong compound index

Hai index `{tenantId:1,email:1}` và `{email:1,tenantId:1}` đều có khả năng ràng buộc uniqueness trên cặp giá trị, nhưng **khác thứ tự field** ảnh hưởng **khả năng tối ưu query theo prefix**.

Ví dụ thường xuyên truy vấn:

~~~javascript
lab.accountsTenant.find({
  tenantId: "T1",
  email: "an@example.test"
})
~~~

Index với `tenantId` trước phù hợp để truy vấn theo tenant rồi email. Nếu các request còn thường liệt kê toàn bộ account của một tenant, prefix `tenantId` có thể hữu ích. Việc chọn thứ tự cần dựa trên **access pattern**, selectivity và index workload, không chỉ uniqueness constraint.

## 9. Case-insensitive uniqueness với collation

Một ứng dụng có thể coi `"An"`, `"an"` và `"AN"` là cùng một username. Nhưng nếu chỉ tạo unique index với **simple/binary collation** mặc định, những chuỗi này có thể tạo **các khóa khác nhau** và đều được lưu.

### 9.1. Unique index theo quy tắc ngôn ngữ

MongoDB hỗ trợ **collation** cho so sánh chuỗi theo locale và mức độ phân biệt. Ví dụ:

~~~javascript
const lab = db.getSiblingDB("unique_index_lab")

lab.usersCaseInsensitive.createIndex(
  { username: 1 },
  {
    unique: true,
    collation: {
      locale: "en",
      strength: 2
    },
    name: "ux_username_case_insensitive"
  }
)

lab.usersCaseInsensitive.insertOne({
  _id: "CI1",
  username: "An"
})

try {
  lab.usersCaseInsensitive.insertOne({
    _id: "CI2",
    username: "an"
  })
} catch (err) {
  print(err.code) // 11000: case-insensitive duplicate.
}
~~~

Với `strength: 2`, collation thường **không phân biệt chữ hoa/thường**, nhưng **có phân biệt dấu/phân biệt biến thể trọng âm** theo quy tắc locale. `strength: 1` còn giảm mức phân biệt hơn; không được tùy tiện chọn mức 1 nếu tên hiển thị hoặc mã nghiệp vụ cần phân biệt dấu.

**Locale quan trọng.** Việc so sánh các ký tự khác nhau giữa tiếng Việt, tiếng Anh và các ngôn ngữ khác phải được thiết kế và thử nghiệm theo chính sách sản phẩm. MongoDB không tự biết “username của ứng dụng” cần coi những biến thể nào tương đương.

### 9.2. Index collation và query collation

Khi truy vấn muốn tận dụng index có collation khác mặc định của collection, query thường cần chỉ định collation phù hợp:

~~~javascript
lab.usersCaseInsensitive.find({
  username: "AN"
}).collation({
  locale: "en",
  strength: 2
})
~~~

Không chỉ tạo unique index là tất cả phép `find()` tự trở thành case-insensitive nếu query đang dùng collation khác. **Index quyết định uniqueness theo collation của chính nó; query dùng collation riêng khi so sánh và chọn index**. Hãy chọn chiến lược nhất quán cho cả ghi, đọc và kiểm tra tài khoản tồn tại.

### 9.3. Giá trị chuẩn hóa và collation giải quyết hai bài toán liên quan

Một cách khác là lưu `usernameCanonical` được **chuẩn hóa** ở tầng ứng dụng theo quy tắc định nghĩa rõ, rồi đặt unique index trên field đó:

~~~javascript
{
  _id: "U-100",
  usernameDisplay: "An",
  usernameCanonical: "an"
}
~~~

~~~javascript
lab.usersCanonical.createIndex(
  { usernameCanonical: 1 },
  { unique: true }
)
~~~

Cách này cần:

- Quy tắc chuẩn hóa cố định (trim, case-fold, Unicode normalization nếu nghiệp vụ yêu cầu).
- Áp dụng **cùng quy tắc** ở tất cả writers/importers.
- Backfill dữ liệu cũ, kiểm tra collision trước khi tạo index.
- Bảo vệ `usernameCanonical` bằng validation/cách ghi có kiểm soát để không bị thiếu hoặc không đồng bộ.

**Không** tự cho rằng chỉ `toLowerCase()` giải quyết mọi khác biệt Unicode trong đa ngôn ngữ. Collation cũng cần được chọn theo locale và yêu cầu nghiệp vụ, không phải công thức phổ quát cho email/username.

### 9.4. Email có thật sự case-insensitive không?

Về nghiệp vụ, nhiều hệ thống muốn xử lý email như định danh không phân biệt hoa/thường, nhưng chuẩn email và quy tắc provider có những khác biệt. Đừng tự gộp các địa chỉ bằng các “mẹo” như bỏ mọi dấu chấm trong phần local-part hoặc bỏ mọi chuỗi sau dấu `+` cho tất cả domain. Nếu sản phẩm muốn định nghĩa định danh email canonical, cần **văn bản quy tắc rõ ràng** và chính sách migration khi hai account hiện có bị chuẩn hóa thành cùng khóa.

## 10. Unique multikey index: array không giống một field scalar

Một index trên field chứa array trở thành **multikey index**. Unique multikey index có ngữ nghĩa dễ nhầm: MongoDB áp ràng buộc uniqueness **giữa các document khác nhau**, không nhất thiết cấm một document chứa **các phần tử lặp** trong chính array của nó.

### 10.1. Ví dụ unique index trên tags

~~~javascript
const lab = db.getSiblingDB("unique_index_lab")

lab.uniqueTags.createIndex(
  { tags: 1 },
  { unique: true }
)

lab.uniqueTags.insertOne({
  _id: "T1",
  tags: ["red", "blue", "red"]
})
~~~

Trong **một document T1**, giá trị `"red"` xuất hiện hai lần trong array, nhưng unique multikey index **không tự bác bỏ** chỉ vì lặp trong cùng document. Các index entries trùng do cùng document được xử lý theo ngữ nghĩa index.

~~~javascript
try {
  lab.uniqueTags.insertOne({
    _id: "T2",
    tags: ["green", "red"]
  })
} catch (err) {
  print(err.code) // 11000 vì "red" đã xuất hiện ở T1.
}
~~~

T2 không thể dùng `"red"` vì có **document khác** đã chiếm index key đó. Nếu muốn “tags trong cùng document không được trùng”, riêng unique index **không đảm bảo bất biến đó**; cần kiểm soát qua mô hình/validator phù hợp và cách cập nhật, hoặc dùng `$addToSet` khi nghiệp vụ thực sự là tập hợp giá trị (cần lưu ý dữ liệu cũ đã trùng không tự được sửa).

### 10.2. Không nhầm index unique với quy tắc một item trên mỗi SKU

Giả sử một order chứa:

~~~javascript
{
  _id: "O-1",
  items: [
    { sku: "BK-01", qty: 1 },
    { sku: "BK-01", qty: 2 }
  ]
}
~~~

Unique index trên `"items.sku"`:

~~~javascript
lab.ordersUniqueItems.createIndex(
  { "items.sku": 1 },
  { unique: true }
)
~~~

**Không bảo đảm** SKU chỉ xuất hiện một lần **trong cùng order**. Ngược lại, index đó có thể vô tình chặn SKU BK-01 ở **một order khác**, vì uniqueness áp dụng xuyên documents của collection.

Nếu cần đảm bảo không có hai line items cùng SKU trong một order:

- Có thể dùng logic ứng dụng/validator đảm bảo tính nhất quán của mảng theo schema đã định.
- Dùng update có điều kiện phù hợp, và cân nhắc `$addToSet` chỉ khi equality trên phần tử đúng với định nghĩa “trùng” của bạn.
- Nếu line items cần quản lý độc lập, mô hình hóa thành **một collection `orderLines`** với unique compound index `{orderId:1,sku:1}`; khi đó uniqueness áp dụng giữa các **line documents** và phù hợp business rule.

### 10.3. Compound multikey và parallel arrays

MongoDB giới hạn compound multikey index khi nhiều indexed fields nằm trong **những array độc lập** (parallel arrays). Ví dụ document có cả `colors: ["red","blue"]` và `sizes: ["S","M"]` thì index compound trên cả hai array có thể không hợp lệ.

Với cùng một array of embedded documents, các đường dẫn như `"items.sku"` và `"items.qty"` có một số cơ chế index khác; vẫn cần kiểm tra giới hạn multikey cụ thể. Không dùng unique multikey index để thay thế một ràng buộc nghiệp vụ phức tạp chỉ dựa trên hình dạng array.

## 11. Trên sharded collection, unique index có giới hạn riêng

Ở một **sharded collection**, MongoDB phân phối dữ liệu qua nhiều shard. Việc thực thi uniqueness xuyên shard chỉ đơn giản khi hệ thống xác định được một khóa duy nhất nằm trong phạm vi routing cần thiết.

Theo hướng dẫn sharding của MongoDB, đối với các sharded collections thông thường:

- Các **unique indexes** trên sharded collection cần có **shard key làm prefix** của index key, trừ các ngoại lệ được tài liệu mô tả.
- Một **hashed index** không thể được chỉ định là **unique** theo cách thông thường.
- Index `_id` là unique, nhưng nếu `_id` **không phải shard key** thì trên sharded collection có thể chỉ được thực thi **tại từng shard**, không tự đảm bảo tính duy nhất `_id` xuyên các shard. Ứng dụng phải quản lý ID không trùng hoặc thiết kế shard key phù hợp.
- Việc thay đổi shard key, resharding hoặc tạo unique index trên dữ liệu đã sharded cần theo quy tắc và hạn chế của server version đang dùng.

### 11.1. Ví dụ multi-tenant với shard key

Giả sử một collection được shard theo `tenantId` và cần username duy nhất **trong từng tenant**:

~~~javascript
// Ý tưởng index (chỉ triển khai khi phù hợp shard key thực tế):
db.getSiblingDB("unique_index_lab").tenantUsers.createIndex(
  { tenantId: 1, username: 1 },
  { unique: true }
)
~~~

Shard key `tenantId` là **prefix** của compound unique index, và constraint được diễn đạt đúng: username có thể trùng giữa hai tenant khác nhau, nhưng không trùng trong cùng tenant.

Ngược lại, một unique index chỉ trên `{username:1}` không có prefix shard key `tenantId` có thể **không được hỗ trợ** trên collection sharded đó. Nếu bài toán đòi username duy nhất trên toàn hệ thống mà shard key là tenant, cần xem xét kiến trúc identity hoặc cách phân phối dữ liệu khác, không thể mặc định tạo một index unique toàn cục bất kỳ.

### 11.2. Những câu cần hỏi trước khi deploy

1. Collection đã sharded chưa? Shard key hiện tại là gì và có hashed components không?
2. Uniqueness cần trên **toàn hệ thống** hay **trong từng tenant/organization**?
3. Có thể dùng shard key làm prefix index mà vẫn hỗ trợ query pattern không?
4. Có dữ liệu trùng giữa các shard hoặc quá trình migration chưa?
5. Có giới hạn khác với unique + partial/sparse/collation trên phiên bản server đang dùng không?

Nếu các yêu cầu uniqueness không tương thích với shard key, nên giải quyết ở **bước thiết kế dữ liệu**, không đợi đến khi tạo index production mới phát hiện giới hạn.

## 12. Unique index không thay thế schema validation

Một index:

~~~javascript
lab.usersPartial.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
)
~~~

chỉ hạn chế **email string trùng nhau**. Nó vẫn có thể cho phép:

~~~javascript
{ _id: "X1", email: 123 }
{ _id: "X2", email: 123 }
{ _id: "X3", email: null }
{ _id: "X4" }
~~~

vì các giá trị đó **không thỏa** filter `$type: "string"`. Nếu chúng không hợp nghiệp vụ, phải áp dụng **validator**.

Ví dụ: email có thể **vắng mặt**, nhưng nếu có phải là string (không cho null/số):

~~~javascript
lab.createCollection("usersValidated", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      properties: {
        email: {
          bsonType: "string",
          minLength: 1
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})

lab.usersValidated.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
)
~~~

Lúc này:

- Document thiếu email **được phép** (field không có trong `required`).
- Document có `email: null` hoặc `email: 123` bị **schema validation** từ chối.
- Document có email string rỗng bị từ chối bởi `minLength:1`.
- Document có email string hợp kiểu, không rỗng nhưng **trùng với email string đã tồn tại** bị **unique index** từ chối.

Hai lớp bảo vệ có trách nhiệm khác nhau: **schema validation** quyết định tài liệu **hợp cấu trúc/giá trị**, còn **unique index** quyết định giá trị khóa có **được dùng bởi document khác** hay không. Chúng bổ trợ nhau.

### 12.1. Khi nào cần required?

Nếu muốn email **bắt buộc cho mọi user**, thay validator thành:

~~~javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["email"],
    properties: {
      email: { bsonType: "string", minLength: 1 }
    }
  }
}
~~~

Nhưng thay đổi đó có thể khiến document cũ thiếu email trở thành invalid. Phải triển khai tương thích, backfill và chỉ bật enforcement sau khi writers/dữ liệu đáp ứng. Việc tạo unique index thành công **không chứng minh** toàn bộ dữ liệu cũ đã có email.

### 12.2. Chỉ unique trong nhóm ACTIVE

Nếu dùng partial unique index theo `status:"ACTIVE"`, document không có status hoặc status khác sẽ **không được index**. Schema validation có thể yêu cầu `status` là một giá trị enum chính xác, hạn chế trường hợp bỏ sót vì lỗi chính tả như `"ACTVE"` hay sai kiểu. Do đó một giải pháp đầy đủ cho domain thường gồm:

~~~text
Validator: mọi user có status thuộc enum được công nhận.
Index: username unique khi status = ACTIVE.
Application: xử lý xung đột khi kích hoạt tài khoản.
Migration: dọn dữ liệu cũ trước khi bật ràng buộc.
~~~

Không thể chỉ có một partial unique index rồi mặc định những document nằm ngoài filter đều hợp nghiệp vụ.

## 13. Triển khai unique index trên collection đang chạy

Tạo unique index trong một collection mới, rỗng, thường đơn giản. Trên collection production hàng triệu document, có thể đã có **dữ liệu trùng**, **null**, **missing**, **kiểu sai** hoặc **các writers đang tiếp tục tạo duplicate**. Tạo index không có kế hoạch vừa có thể thất bại, vừa có thể làm một số luồng ứng dụng bắt đầu trả lỗi ngay khi index được tạo thành công.

Một phương pháp triển khai là **define → inventory → migrate → prevent → build → verify → observe**.

### 13.1. Bước 1 — Định nghĩa chính xác khóa duy nhất

Trước hết phải trả lời:

- Khóa nào phải unique: `username`, `emailCanonical`, `sku` hay bộ `(tenantId, orderNo)`?
- Uniqueness có hiệu lực trong **toàn collection** hay chỉ khi `status = "ACTIVE"`?
- Trường bị thiếu có hợp lệ không? Explicit null có hợp lệ không?
- Chuỗi rỗng có được coi như “chưa nhập” không?
- Phân biệt hoa/thường, dấu, Unicode normalization ra sao?
- Có nhiều tenants không? Uniqueness có cần toàn cầu khi collection được shard không?
- Field có phải là array? Có thể có nhiều phần tử trùng trong một document không?

Lập một “hợp đồng khóa” rõ ràng:

~~~text
Business key: emailCanonical
Phạm vi: các user có emailCanonical là string
Độ duy nhất: toàn collection
Missing: cho phép nhiều
Null: cho phép nhiều (nhưng validator sản phẩm có thể cấm explicit null)
Chuỗi rỗng: cấm bằng schema validation
Chuẩn hóa: theo quy tắc canonical của sản phẩm
Index: {emailCanonical:1}, unique + partial type string
Mở rộng: chưa sharding; cần thiết kế lại nếu shard key không tương thích
~~~

Với ví dụ trên, có thể viết index:

~~~javascript
db.getSiblingDB("unique_index_lab").usersPolicy.createIndex(
  { emailCanonical: 1 },
  {
    unique: true,
    partialFilterExpression: {
      emailCanonical: { $type: "string" }
    },
    name: "ux_emailCanonical_string"
  }
)
~~~

Đây là **mô tả chính sách**, không phải đảm bảo mọi document đều hợp chính sách: muốn cấm email số/array/chuỗi rỗng, cần validation cùng quy tắc ứng dụng.

### 13.2. Bước 2 — Kiểm kê duplicate, null, missing và kiểu

Trước khi tạo index, phân nhóm dữ liệu:

~~~javascript
const lab = db.getSiblingDB("unique_index_lab")
const collection = lab.usersDirty

const missingUsername = collection.countDocuments({
  username: { $exists: false }
})

const nullUsername = collection.countDocuments({
  username: { $type: "null" }
})

const stringUsername = collection.countDocuments({
  username: { $type: "string" }
})

printjson({
  missingUsername,
  nullUsername,
  stringUsername
})
~~~

Lưu ý: khi field có thể là **array**, toán tử `$type` ở query có thể khớp **phần tử trong array** thuộc kiểu yêu cầu, chứ không nhất thiết chứng minh **toàn field** có đúng BSON type string. Nếu schema cho phép dữ liệu không chuẩn, hãy điều tra kiểu toàn field hoặc dùng schema validation `bsonType` cùng cơ chế kiểm kê thích hợp. Không tự coi `$type:"string"` trong query là lệnh cấm array.

Để tìm duplicate username string theo đúng giá trị hiện có:

~~~javascript
collection.aggregate([
  { $match: { username: { $type: "string" } } },
  {
    $group: {
      _id: "$username",
      count: { $sum: 1 }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $sort: { count: -1 } },
  { $limit: 50 }
])
~~~

Nếu business key dùng collation case-insensitive hoặc trường canonical, phải phát hiện **collision theo đúng quy tắc mới**, không chỉ nhóm raw strings. Hai chuỗi `"AN"` và `"an"` có thể khác theo binary grouping nhưng trùng trong unique index case-insensitive.

### 13.3. Bước 3 — Làm sạch dữ liệu có nguồn gốc rõ

Khi phát hiện hai account cùng email:

1. Xác định hai bản ghi thực sự là cùng người hay hai tài khoản khác nhau đã sử dụng trùng dữ liệu.
2. Xem liên kết tới orders, invoices, activities và quyền truy cập.
3. Nếu merge, cần thống nhất ID chuẩn, cập nhật reference theo kế hoạch và giữ audit.
4. Nếu rename/canonicalize, cần thông báo cho producer và tránh tái tạo collision.
5. Với missing/null, xác định “cho phép thiếu” hay “bắt buộc bổ sung”; **không điền một email placeholder dùng chung** nếu định đặt unique index, vì placeholder chung sẽ tự gây duplicate.
6. Chạy migration theo lô có checkpoint, condition filter và rollback/reconciliation.

Không xóa bớt document chỉ để câu lệnh `createIndex` chạy được, nếu chưa xác định chính sách giữ dữ liệu.

### 13.4. Bước 4 — Kiểm soát writers trước khi build

Trong thời gian làm sạch dữ liệu, các ứng dụng cũ có thể tiếp tục tạo duplicate. Những biện pháp cần phối hợp:

- Triển khai code writers theo chính sách mới và xử lý `E11000`.
- Cân nhắc khóa/cửa sổ bảo trì hoặc giảm các producers liên quan trong giai đoạn chuyển đổi.
- Kiểm soát job import, batch, data sync và tài khoản quản trị.
- Nếu dùng canonical field, tất cả producers phải cùng tính nó theo một quy tắc.
- Cập nhật schema validation nếu cần để cấm kiểu dữ liệu sai, nhưng phải làm theo quy trình tương thích với dữ liệu cũ.

Kiểm tra “không còn duplicate tại thời điểm T” **không ngăn** một writer cũ tạo duplicate ngay sau đó. Tạo index là điểm enforcement ở database, nhưng build cũng phải được điều phối với traffic và các thay đổi dữ liệu đang diễn ra theo hướng dẫn của MongoDB.

### 13.5. Bước 5 — Tạo index, xác minh và theo dõi

~~~javascript
const lab = db.getSiblingDB("unique_index_lab")

lab.usersPolicy.createIndex(
  { emailCanonical: 1 },
  {
    unique: true,
    partialFilterExpression: {
      emailCanonical: { $type: "string" }
    },
    name: "ux_emailCanonical_string"
  }
)

printjson(lab.usersPolicy.getIndexes())
~~~

Khi build index trên production, theo dõi **thời gian build, tài nguyên CPU/memory/I/O, replication, các lỗi duplicate key và các đặc điểm commit của index build**. Nếu build thất bại vì duplicate, không giả định index đã tồn tại và đang enforce. Phải kiểm tra index list thật trước khi tiếp tục rollout.

Sau khi thành công:

- Xem `getIndexes()` để xác minh **key pattern**, `unique`, `partialFilterExpression`, `collation`, `sparse` và tên index.
- Thực hiện thử nghiệm ghi phù hợp trong **môi trường test** để xác minh semantics.
- Theo dõi lỗi duplicate key theo service/version/job.
- Xác định phản hồi API thích hợp (ví dụ trả mã xung đột nghiệp vụ thay vì lỗi 500 chung).
- Nếu hệ thống có đa tenant/sharding, xác nhận phạm vi uniqueness đúng thiết kế.

### 13.6. Hidden index có vô hiệu uniqueness không?

**Không.** Hidden index được ẩn khỏi query planner để đánh giá tác động truy vấn khi chuẩn bị bỏ index, nhưng **unique constraint của hidden unique index vẫn tiếp tục được thực thi**. Không dùng `hideIndex()` như một cách tạm nới lỏng uniqueness.

Để bỏ ràng buộc unique thực sự cần thay đổi index policy theo quy trình hỗ trợ, thường liên quan việc **drop/recreate** đúng index hoặc cơ chế chuyển đổi được phiên bản MongoDB hỗ trợ. Đây là thay đổi dữ liệu/sản phẩm có rủi ro; không tự drop index production khi vừa gặp một lỗi duplicate key.

### 13.7. Rollback khi index làm phát sinh lỗi nghiệp vụ

Rollback có hai mặt:

- **Code rollback:** ứng dụng cũ có thể tiếp tục cố chèn dữ liệu trùng và gặp lỗi nếu unique index vẫn tồn tại.
- **Index rollback:** bỏ unique index cho phép phát sinh duplicate mới, có thể phá bất biến được sử dụng bởi code mới.

Vì vậy một kế hoạch rollback tốt cần xác định **trạng thái nào vẫn an toàn về dữ liệu**, không chỉ ghi “chạy `dropIndex` khi có lỗi”. Nếu business policy sai, có thể cần sửa rule/partial filter hoặc kế hoạch migration thứ hai, không chỉ tắt ràng buộc.

## 14. Xử lý `E11000` đúng trong ứng dụng

MongoDB áp unique constraint ở server, nên ứng dụng vẫn phải giả định **bất cứ write nào thay đổi khóa được index đều có thể bị từ chối**.

### 14.1. Một API tạo user

Một luồng điển hình:

~~~text
POST /users
  |
  +-- validate input và normalize field theo policy
  +-- insert user (có unique index)
          |
          +-- OK -> trả user mới
          |
          +-- E11000 -> xác định index/key trùng,
                         trả lỗi nghiệp vụ "username đã tồn tại"
          |
          +-- lỗi khác -> xử lý theo nhóm lỗi riêng
~~~

Có thể kiểm tra trước để giảm trải nghiệm lỗi:

~~~javascript
lab.usersBasic.findOne({ username: "an" })
~~~

Nhưng **không** dựa vào việc kiểm tra trước như bằng chứng cuối cùng do race condition. Insert vẫn có thể trả duplicate key giữa hai request đồng thời.

### 14.2. Không retry vô hạn lỗi duplicate key

Một `insertOne` bị E11000 với username `"an"` sẽ không tự thành công nếu gửi lại payload y hệt nhiều lần. Có thể có một ngoại lệ nghiệp vụ: request lặp lại với **cùng idempotency key** và document đã được tạo bởi lần trước, khi đó server/app có thể xác nhận đó là **cùng tác vụ đã hoàn thành**. Tuy nhiên “trùng username” chưa đủ để kết luận hai request là giống nhau; cần đối soát `requestId`/business identity.

### 14.3. Upsert có thể cạnh tranh trên unique key

~~~javascript
lab.usersBasic.updateOne(
  { username: "newuser" },
  {
    $setOnInsert: {
      createdAt: new Date(),
      displayName: "New User"
    }
  },
  { upsert: true }
)
~~~

Nếu hai client đồng thời upsert cùng username chưa tồn tại, unique index giúp ngăn tạo hai documents trùng. Tuy nhiên, một client có thể vẫn nhận duplicate key do timing và cách filter/update, thay vì cả hai lời gọi đều tự merge êm ái.

Để xử lý, cần:

- Unique index bảo vệ khóa thật sự.
- Filter theo đúng identity và thiết kế modifier không cố đổi indexed key theo cách mâu thuẫn.
- Khi E11000 xảy ra, đọc lại trạng thái và xác định có cần retry dưới dạng **update có điều kiện** không.
- Không retry không giới hạn; không xem E11000 là một thành công nếu trạng thái thực không đúng.

### 14.4. Ví dụ MongoDB Java Sync Driver

Trong Java Sync Driver, có thể dùng `createIndex` với `IndexOptions` và bắt mã lỗi:

~~~java
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.IndexOptions;
import org.bson.Document;

import static com.mongodb.client.model.Indexes.ascending;

// Giả sử database là một MongoDatabase đã kết nối tới môi trường lab.
MongoCollection<Document> users = database.getCollection("users");

users.createIndex(
    ascending("username"),
    new IndexOptions().unique(true)
);

try {
    users.insertOne(
        new Document("_id", "U-JAVA-1")
            .append("username", "an")
    );
} catch (MongoWriteException ex) {
    if (ex.getError().getCode() == 11000) {
        // Trả lỗi nghiệp vụ thích hợp; tránh log thông tin nhạy cảm.
        System.err.println("Duplicate unique key");
    } else {
        throw ex;
    }
}
~~~

Đây là ví dụ **lệnh trực tiếp**. Khi `bulkWrite()` hoặc index build thất bại, exception có thể là loại khác (ví dụ `MongoBulkWriteException` cho bulk, `MongoCommandException` cho command). Không bắt một class exception rồi mặc định mọi thao tác ghi/index đều dùng class đó. Tên API và cấu trúc lỗi cần kiểm tra theo Java driver version của dự án.

### 14.5. Khóa unique và upsert trong multi-tenant Java

Một collection đa tenant thường cần:

~~~java
users.createIndex(
    new Document("tenantId", 1).append("username", 1),
    new IndexOptions().unique(true)
);
~~~

Khi tạo user, filter/identity phải bao gồm **tenantId**. Nếu application quên tenantId trong query tìm trước hoặc upsert, nó có thể đọc/chỉnh account của tenant khác hoặc suy luận sai về uniqueness. **Index bảo vệ constraint theo tuple**, còn việc cô lập dữ liệu tenant trong các query là trách nhiệm thiết kế authorization và application.

## 15. Một bảng quyết định nhanh

| Yêu cầu nghiệp vụ | Lựa chọn index | Điều cần chú ý |
|---|---|---|
| Username luôn có, duy nhất trên collection | `{username:1}` unique | Schema validation buộc username string/non-empty; xử lý case normalization. |
| Email tùy chọn; **chỉ thiếu field** được lặp, null tối đa một | Unique **sparse** trên email | Explicit null vẫn được index. |
| Email tùy chọn; **missing và null** có thể lặp, string phải unique | Unique **partial** `email:{$type:"string"}` | Kiểm soát kiểu bằng validator; chuỗi rỗng vẫn là string. |
| Email nullable nhưng muốn index tất cả field **được khai báo**, kể cả null | Unique partial `email:{$exists:true}` | Null chỉ có tối đa một. |
| Mỗi tenant có thể dùng cùng username như tenant khác | Unique compound `{tenantId:1,username:1}` | Tuple unique; null/missing cũng nằm trong tuple. |
| Email tùy chọn và unique **trong từng tenant** | Unique compound + partial theo email hợp lệ | Compound sparse có thể không loại missing email nếu tenantId luôn có. |
| Chỉ tài khoản ACTIVE cần unique username | Unique partial theo `status:"ACTIVE"` | Chuyển trạng thái vào ACTIVE cũng bị kiểm tra. |
| Không phân biệt hoa/thường | Unique index có collation thích hợp hoặc canonical key | Đảm bảo query, writers và migration thống nhất quy tắc. |
| Tags array phải unique **xuyên documents** | Unique multikey index | Lặp phần tử **trong cùng document** có thể vẫn được phép. |
| SKU phải không trùng **trong mỗi order** | Mô hình line items riêng + unique `{orderId,sku}` hoặc ràng buộc array riêng | Unique multikey trên `items.sku` không thay thế quy tắc trong cùng document. |
| Unique trên sharded collection | Unique index với shard key prefix theo quy tắc server | Kiểm tra trường hợp `_id` và hashed shard keys. |

## 16. Các lỗi suy luận thường gặp

| Suy luận sai | Cách hiểu đúng |
|---|---|
| “Unique index chỉ ảnh hưởng insert.” | Update, replace và upsert có thể tạo index key trùng và bị chặn. |
| “Không có field thì không tham gia unique index.” | Với **non-sparse single-field unique**, missing tạo khóa null. |
| “`null` và missing giống nhau trong mọi tình huống.” | Chúng khác ở document/query `$exists`; chỉ một số cách lập index coi chúng có key null tương đương. |
| “Unique trên email cho phép bao nhiêu email thiếu cũng được.” | Non-sparse single-field unique chỉ cho một document có key null/missing. |
| “Sparse cho phép nhiều explicit null.” | **Không**: sparse single-field bỏ qua missing nhưng index explicit null. |
| “Partial `$exists:true` sẽ bỏ qua null.” | **Không**: field null vẫn tồn tại và được index. |
| “Partial `$type:"string"` cấm email sai kiểu.” | Không: document ngoài partial filter không bị constraint unique kiểm tra; cần validator riêng. |
| “Partial `$type:"string"` luôn chứng minh field không thể là array.” | Query `$type` có ngữ nghĩa với array elements; muốn cấm array, dùng BSON schema phù hợp. |
| “Compound unique có nghĩa từng field phải unique.” | Ràng buộc trên **tuple** nhiều field. |
| “Compound unique sparse loại mọi document thiếu một field.” | Nếu field khác trong compound index có mặt, document vẫn có thể được index. |
| “Một null trong compound unique nghĩa là cả collection chỉ có một null.” | Các tuple chứa null có thể khác nhau ở field còn lại. |
| “Unique index kiểm tra chữ hoa/thường theo chính sách app.” | Phụ thuộc **collation hoặc canonical key** được cấu hình. |
| “Unique multikey cấm tag lặp trong cùng document.” | Nó chủ yếu ràng buộc key **giữa documents**, không đảm bảo mảng tự unique. |
| “Unique index trên `items.sku` đảm bảo mỗi order có một SKU.” | Có thể chặn SKU dùng trong order khác mà không cấm lặp ở cùng order. |
| “`_id` luôn được bảo vệ global trên mọi shard dù không là shard key.” | Với sharded collection, phạm vi `_id` unique có ngoại lệ cần xem tài liệu. |
| “Hashed index có thể gắn `unique:true` như mọi index.” | MongoDB không hỗ trợ unique hashed index theo cách thông thường. |
| “Tạo unique index sẽ tự dọn duplicate.” | Index build thất bại khi dữ liệu có key trùng; phải migrate dữ liệu. |
| “Ẩn một unique index sẽ cho phép ghi dữ liệu trùng.” | Hidden index vẫn thực thi uniqueness. |
| “`E11000` thì retry là hết lỗi.” | Thường là xung đột dữ liệu bền vững; cần thay identity hoặc xác định request idempotent. |
| “Tìm trước khi insert đủ để chống hai request đồng thời.” | Chỉ index unique ở database chặn race ở thời điểm ghi. |
| “Unique index thay thế validator.” | Unique kiểm tra ràng buộc key; validator kiểm tra kiểu/giá trị/field bắt buộc. |

### 16.1. Phân biệt “không có giá trị” và “giá trị không hợp lệ”

Giả sử giao diện đăng ký cho phép bỏ qua email. Có ít nhất bốn cách client có thể gửi:

~~~javascript
{ _id: "A" }
{ _id: "B", email: null }
{ _id: "C", email: "" }
{ _id: "D", email: " " }
~~~

Nếu sản phẩm coi cả bốn là “chưa có email”, database không tự xử lý chúng giống nhau:

- Missing tạo index key null ở **non-sparse** nhưng bị loại khỏi **sparse**.
- Explicit `null` vẫn vào index sparse, nhưng có thể bị loại bởi **partial `$type:"string"`**.
- Chuỗi rỗng `""` là **string**, nên được index bởi partial kiểu string; chỉ một giá trị rỗng được phép khi unique.
- Chuỗi gồm khoảng trắng `" "` là một giá trị string khác với chuỗi rỗng (tùy collation), nên uniqueness có thể không báo lỗi dù nghiệp vụ không muốn chấp nhận.

Giải pháp tốt là định nghĩa **normalization + validation + indexing** cùng nhau. Ví dụ khi client cung cấp email rỗng thì ứng dụng chuẩn hóa thành **field missing** thay vì giữ chuỗi rỗng, nếu đó là chính sách đã thống nhất; hoặc validator cấm chuỗi rỗng và yêu cầu người dùng sửa dữ liệu.

### 16.2. Không tự chọn unique index trước khi biết nhu cầu giữ lịch sử

Một username có thể được phép tái sử dụng sau khi user xóa tài khoản; nhưng nếu audit logs đang dùng username làm reference, việc tái sử dụng có thể gây nhầm danh tính. Partial unique theo `status:"ACTIVE"` giải quyết ràng buộc “chỉ account đang active không trùng”, nhưng **không** tự giải quyết semantics lịch sử.

Nên tham chiếu user bằng **ID bất biến** và lưu snapshot tên khi cần, thay vì dùng tên có thể tái sử dụng làm foreign key nghiệp vụ.

### 16.3. Transaction không làm unique index bớt nghiêm ngặt

Đặt hai inserts trùng key trong một transaction không khiến MongoDB cho chúng cùng tồn tại. Một transaction có thể gặp duplicate key và bị abort; ứng dụng phải phân loại lỗi và áp dụng retry đúng cách. Một **write concern** mạnh hơn cũng không thay thế unique index; nó điều khiển mức xác nhận ghi, không tự phát hiện business-key duplication.

## 17. Bài tập thực hành và đáp án gợi ý

Mỗi bài dựa trên **một collection mới, trống** và chỉ xét những document được nêu trong đề; không cộng dồn dữ liệu của các bài. Có thể chạy trong `unique_index_lab` với tên collection riêng cho từng bài.

### Bài 1 — Unique đơn trường, null rồi missing

Cho index:

~~~javascript
db.c1.createIndex({ email: 1 }, { unique: true })
~~~

Thực hiện:

~~~javascript
db.c1.insertOne({ _id: 1, email: null })
db.c1.insertOne({ _id: 2 })
~~~

**Câu hỏi:** thao tác nào lỗi? Vì sao?

**Đáp án:** Insert thứ nhất thành công; thứ hai bị **duplicate key** vì non-sparse unique index đơn trường coi missing và explicit null có cùng index key `null`.

### Bài 2 — Đảo thứ tự insert

Vẫn index `{email:1}` unique, nhưng insert:

~~~javascript
db.c2.insertOne({ _id: 1 })
db.c2.insertOne({ _id: 2, email: null })
~~~

**Đáp án:** Insert thứ hai cũng bị chặn. Không quan trọng null xuất hiện trước hay missing xuất hiện trước; cả hai tranh một key null.

### Bài 3 — Unique sparse

~~~javascript
db.c3.createIndex(
  { email: 1 },
  { unique: true, sparse: true }
)

db.c3.insertOne({ _id: 1 })
db.c3.insertOne({ _id: 2 })
db.c3.insertOne({ _id: 3, email: null })
db.c3.insertOne({ _id: 4, email: null })
~~~

**Đáp án:** Hai document missing được phép; explicit null đầu tiên được phép; explicit null thứ hai bị E11000. Sparse loại missing nhưng **không loại null hiện diện**.

### Bài 4 — Unique partial kiểu string

~~~javascript
db.c4.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
)

db.c4.insertOne({ _id: 1 })
db.c4.insertOne({ _id: 2, email: null })
db.c4.insertOne({ _id: 3, email: null })
db.c4.insertOne({ _id: 4, email: "a@test" })
db.c4.insertOne({ _id: 5, email: "a@test" })
~~~

**Đáp án:** Bốn insert đầu hợp unique index; insert thứ năm bị duplicate string. Tuy nhiên, nếu nghiệp vụ cấm `email:null`, chỉ index là **chưa đủ** — cần schema validation.

### Bài 5 — Chuỗi rỗng có được bỏ qua không?

Với partial unique index `email: {$type:"string"}`, hai document đều có `email: ""` có được insert không?

**Đáp án:** Không. `""` có kiểu string nên được index, và giá trị trùng gây duplicate key. Muốn cấm chuỗi rỗng ngay từ đầu, dùng validator như `minLength:1` hoặc quy tắc tương đương theo domain.

### Bài 6 — Compound unique theo tenant

Tạo unique index `{tenantId:1,username:1}` rồi insert:

~~~javascript
{ _id: 1, tenantId: "A", username: "lan" }
{ _id: 2, tenantId: "B", username: "lan" }
{ _id: 3, tenantId: "A", username: "lan" }
~~~

**Đáp án:** Hai document đầu được phép vì tuple khác nhau; document thứ ba bị từ chối vì trùng tuple `("A","lan")`.

### Bài 7 — Compound index, thiếu email

Với unique index `{tenantId:1,email:1}`, xét:

~~~javascript
{ _id: 1, tenantId: "A" }
{ _id: 2, tenantId: "B" }
{ _id: 3, tenantId: "A", email: null }
~~~

**Đáp án:** Hai document đầu có tuple `("A",null)` và `("B",null)`, nên được phép. Document thứ ba trùng tuple `("A",null)` với document 1, nên lỗi duplicate key.

### Bài 8 — Compound sparse có giúp bỏ email missing không?

Một hệ thống đặt unique sparse index `{tenantId:1,email:1}`. `tenantId` luôn tồn tại; người dùng chưa đăng ký email bị thiếu field. Có cho phép vô hạn user thiếu email trong cùng tenant không?

**Đáp án:** **Không mặc nhiên.** Vì tenantId hiện diện, compound sparse index có thể lập entry cho document với email missing và tuple `(tenantId,null)`. Chọn unique compound **partial** theo điều kiện email hợp lệ, đồng thời validate tenantId.

### Bài 9 — Case-insensitive uniqueness

Collection có index:

~~~javascript
db.c9.createIndex(
  { username: 1 },
  {
    unique: true,
    collation: { locale: "en", strength: 2 }
  }
)
~~~

Insert username `"An"` rồi `"an"` có được không?

**Đáp án:** Không. Với collation này, chúng được xem là tương đương về case trong khóa unique. Query muốn tận dụng index theo cùng cách so sánh thường cần collation phù hợp.

### Bài 10 — Unique index và array trùng nội bộ

Unique multikey index trên `{tags:1}`. Một document có `tags:["red","red"]` có tự bị từ chối chỉ vì hai phần tử bằng nhau không?

**Đáp án:** Không. Unique multikey index kiểm tra ràng buộc giữa **các document khác nhau**; sự lặp trong chính array không phải điều nó tự loại bỏ. Một document thứ hai chứa `"red"` sẽ xung đột với document đầu.

### Bài 11 — Update sang một key trùng

Đang có:

~~~javascript
{ _id: 1, username: "an" }
{ _id: 2, username: "binh" }
~~~

Unique index trên username. Lệnh:

~~~javascript
db.c11.updateOne(
  { _id: 2 },
  { $set: { username: "an" } }
)
~~~

**Đáp án:** Bị duplicate key; unique constraint áp dụng cả khi **update** làm giá trị indexed field đổi.

### Bài 12 — Kích hoạt tài khoản với partial index

Unique partial index trên username với filter `{status:"ACTIVE"}`. Có một account `{username:"lan",status:"ACTIVE"}` và một account `{username:"lan",status:"DELETED"}`. Điều gì xảy ra nếu account DELETED chuyển thành ACTIVE mà không đổi username?

**Đáp án:** Update có thể bị **duplicate key**, vì document thứ hai giờ đi vào tập unique index và xung đột với account đang ACTIVE.

### Bài 13 — Tạo index trên dữ liệu trùng

Collection chứa hai document có `username:"an"`; index chưa có. Gọi:

~~~javascript
db.c13.createIndex(
  { username: 1 },
  { unique: true }
)
~~~

**Đáp án:** Index build thất bại. MongoDB không tự chọn bản ghi cần giữ; phải xử lý dữ liệu trùng theo nghiệp vụ và tạo lại index.

### Bài 14 — Race condition

Hai request cùng `findOne({username:"mai"})` và đều nhận null. Cả hai cùng insert user với username `"mai"`. Làm sao đảm bảo không sinh hai tài khoản trùng?

**Đáp án:** Tạo unique index trên business key đúng quy tắc; một insert sẽ thành công còn request kia có thể nhận E11000. Xử lý lỗi đó ở ứng dụng. Check trước chỉ cải thiện UX, **không bảo vệ được race**.

### Bài 15 — Sharding và unique index

Collection sharded theo `tenantId`. Ứng dụng muốn username duy nhất **trong tenant**. Đề xuất unique index nào hợp lý hơn: `{username:1}` hay `{tenantId:1,username:1}`?

**Đáp án:** `{tenantId:1,username:1}` phù hợp vì tuple định nghĩa đúng nghiệp vụ và shard key là prefix theo quy tắc unique index trên sharded collection. Vẫn phải xét shard key thực tế và các giới hạn MongoDB version.

### Bài 16 — Query null và missing

Cho:

~~~javascript
{ _id: 1, email: null }
{ _id: 2 }
{ _id: 3, email: "a@test" }
~~~

Viết hai query tách biệt: (1) chỉ field thiếu, (2) explicit BSON null.

**Đáp án:**

~~~javascript
// Missing:
db.c16.find({ email: { $exists: false } })

// Explicit null:
db.c16.find({ email: { $type: "null" } })
~~~

`{email:null}` thường khớp **cả missing và explicit null**, nên không dùng nó để phân biệt hai nhóm.

## 18. Tình huống thiết kế tổng hợp: tài khoản đa tenant

Giả sử hệ thống SaaS có các yêu cầu:

1. Mỗi account thuộc **một tenant**, `tenantId` bắt buộc.
2. `username` bắt buộc; trong tenant username không được trùng **không phân biệt hoa/thường**.
3. `email` tùy chọn. Nhiều account chưa có email, và người dùng có thể chưa xác nhận địa chỉ.
4. Khi `emailVerified: true`, email phải hợp lệ và không được trùng **trong tenant** ở các account đã xác minh.
5. Khi account bị khóa, lịch sử vẫn cần giữ; không được làm sai liên kết bằng username.

Một hướng triển khai (phải cân nhắc chính sách email và schema thực tế):

~~~javascript
const lab = db.getSiblingDB("unique_index_lab")

// Username unique trong mỗi tenant, so sánh không phân biệt case.
lab.saasAccounts.createIndex(
  { tenantId: 1, username: 1 },
  {
    unique: true,
    collation: { locale: "en", strength: 2 },
    name: "ux_tenant_username_ci"
  }
)

// Email unique trong mỗi tenant CHỈ khi account đã xác minh
// và email là string. Giả định các writers/validator đảm bảo
// trường tenantId và email đúng kiểu.
lab.saasAccounts.createIndex(
  { tenantId: 1, email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      emailVerified: true,
      email: { $type: "string" }
    },
    name: "ux_tenant_verified_email"
  }
)
~~~

Điểm cần hiểu:

- Index thứ nhất bảo vệ **username theo tenant**; nó không tự ngăn `username` thiếu hoặc sai kiểu trong mọi tình huống. Dùng validator để buộc `tenantId`/`username` tồn tại và hợp lệ.
- Index thứ hai chỉ bảo vệ **email của các account thỏa partial filter**, không bắt account chưa verified phải có email.
- Nếu hai account chưa verified cùng email rồi **cùng được xác minh**, operation làm account thứ hai đi vào tập indexed có thể bị E11000. Ứng dụng phải chuẩn bị xử lý trạng thái này.
- Nếu email là định danh global, phải sửa phạm vi uniqueness. Nếu collection sharded, cần xét giới hạn shard key prefix.
- Chỉ dựa vào `emailVerified: true` của client là không đủ; việc xác minh email phải là nghiệp vụ server đáng tin cậy.
- Các reference quan trọng tới account nên dùng **ID bất biến**, không dùng username có thể đổi hoặc tái sử dụng.

### 18.1. Vì sao không dùng một unique index cho mọi yêu cầu?

Vì có ít nhất **hai bất biến khác nhau**:

~~~text
Unique(username | tenantId, bất kể account verified hay không)

Unique(email | tenantId, chỉ khi emailVerified = true
                   và email thuộc kiểu được công nhận)
~~~

Một index chỉ có một key pattern và một bộ option/filter. Nhiều bất biến độc lập thường cần **nhiều indexes** kết hợp validator/logic nghiệp vụ. Đổi lại, mỗi index tăng chi phí lưu trữ và cập nhật, nên phải đo workload thực.

### 18.2. Quy trình cập nhật email

Giả sử một account muốn đổi từ `old@example.test` sang `new@example.test`:

1. Ứng dụng ghi email candidate vào field tạm, không tự đánh dấu verified.
2. Xác minh quyền sở hữu qua quy trình thích hợp.
3. Khi chuyển `emailVerified` sang true và email mới trở thành khóa trong partial index, MongoDB kiểm tra uniqueness.
4. Nếu nhận E11000, không xác minh trùng, cần xử lý xung đột theo chính sách sản phẩm.
5. Cập nhật các field liên quan theo một write nguyên tử trên cùng account nếu có thể, không tạo trạng thái “email verified” mà email chưa được lưu đúng.

Unique index là rào chắn cuối cùng bảo vệ key; nó không tự thực hiện quy trình xác minh danh tính.

## 19. Tài liệu MongoDB chính thức

Các nguồn sau thuộc **MongoDB Database Manual** và tài liệu driver. Khi áp dụng, hãy chọn đúng nhánh server/FCV của deployment; URL `/docs/manual/` có thể được MongoDB chuyển hướng sang bản tài liệu hiện hành.

- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — ngữ nghĩa unique single-field, compound, null/missing, multikey và sharded collection.
- [Sparse Indexes](https://www.mongodb.com/docs/manual/core/index-sparse/) — tài liệu về việc bỏ qua document missing và giới hạn của sparse.
- [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/) — `partialFilterExpression`, kết hợp unique, khả năng dùng trong query.
- [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/) — index trên arrays và unique multikey constraints.
- [Case-Insensitive Indexes](https://www.mongodb.com/docs/manual/core/index-case-insensitive/) — collation và index không phân biệt hoa/thường.
- [Collation](https://www.mongodb.com/docs/manual/reference/collation/) — locale, strength và quy tắc so sánh string.
- [`db.collection.createIndex()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.createIndex/) — cú pháp tạo index, key pattern và options.
- [`db.collection.getIndexes()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.getIndexes/) — đọc cấu hình index thực tế.
- [`$exists` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/exists/) — phân biệt field có mặt và missing.
- [`$type` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/type/) — truy vấn BSON type và lưu ý về array.
- [Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/) — query equality với null và tìm missing fields.
- [Sharding and Unique Indexes](https://www.mongodb.com/docs/manual/core/sharding-shard-key/) — các điều kiện sharding/shard key liên quan uniqueness.
- [Index Builds on Populated Collections](https://www.mongodb.com/docs/manual/core/index-creation/) — tạo index trên dữ liệu hiện có, tác động vận hành.
- [MongoDB Java Sync Driver — Indexes](https://www.mongodb.com/docs/drivers/java/sync/current/indexes/) — `IndexOptions` và tạo index qua driver.
- [MongoDB 8.0 — Unique Indexes](https://www.mongodb.com/docs/v8.0/core/index-unique/) — tham chiếu cố định theo nhánh 8.0.

**Kết luận:** Với unique index, không đủ để hỏi “field này có duy nhất không?”. Phải hỏi thêm **giá trị nào tham gia index, null/missing có được phép lặp không, uniqueness áp dụng cho từng field hay tuple, và có điều kiện trạng thái/tenant/collation không**. **Non-sparse unique**, **unique sparse** và **unique partial** có hành vi rất khác nhau khi field bị thiếu hoặc bằng null. Hãy thiết kế constraint theo bất biến nghiệp vụ, kiểm kê/migrate dữ liệu cũ trước khi tạo index, và luôn xử lý `E11000` như một kết quả hợp lệ của hệ thống có nhiều thao tác đồng thời.

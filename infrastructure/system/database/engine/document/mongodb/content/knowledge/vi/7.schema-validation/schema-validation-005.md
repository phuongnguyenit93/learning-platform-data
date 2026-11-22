# Kết hợp biểu thức truy vấn với schema validation trong MongoDB

MongoDB cho phép mỗi document trong một collection có cấu trúc linh hoạt. Sự linh hoạt này hữu ích khi dữ liệu thay đổi theo nghiệp vụ, nhưng cũng có thể tạo ra document thiếu trường bắt buộc, sai kiểu hoặc mâu thuẫn giữa các thuộc tính. **Schema validation** giúp đặt ra hợp đồng dữ liệu ngay tại database: các thao tác ghi không thỏa quy tắc có thể bị từ chối hoặc được ghi kèm cảnh báo.

Hai cách mô tả quy tắc thường được sử dụng là:

- **`$jsonSchema`**: kiểm tra hình dạng document, các field bắt buộc, kiểu BSON, giá trị cho phép, ràng buộc về chuỗi, số và cấu trúc object/mảng.
- **Biểu thức truy vấn MongoDB (query expressions)**: dùng các điều kiện giống bộ lọc `find()`, các toán tử logic và, khi được phiên bản hỗ trợ, `$expr` để diễn tả quan hệ giữa các field.

Ta có thể **kết hợp cả hai trong cùng một `validator`**. Ví dụ: `$jsonSchema` yêu cầu `capacity` và `enrolled` là số nguyên không âm, còn `$expr` yêu cầu `enrolled <= capacity`. Một nhánh `$or` khác có thể yêu cầu `publishedAt` tồn tại khi `status` là `published`.

Bài học thuộc phần **Schema validation**, sử dụng collection `courses` để giải thích từ cú pháp, cách triển khai, cách kiểm thử đến các giới hạn thực tế.

## 1. Validator được MongoDB sử dụng như thế nào?

Một collection có thể khai báo `validator` khi tạo hoặc cập nhật cấu hình validator bằng `collMod`. Về mặt khái niệm, MongoDB kiểm tra trạng thái document được ghi dựa trên biểu thức validator:

```text
Ứng dụng gửi insert / update
            |
            v
     Document sau thao tác
            |
            v
  Validator của collection
       /           \
    hợp lệ       không hợp lệ
      |               |
    ghi dữ liệu      validationAction
                   /             \
                "error"         "warn"
                 từ chối       vẫn ghi + cảnh báo
```

Validation có thể áp dụng cho thao tác `insert` và `update`, tùy `validationLevel`; nó không tự động chỉnh sửa hoặc xóa các document lịch sử khi ta thay đổi quy tắc.

Cấu trúc khi tạo collection:

```javascript
db.createCollection("courses", {
  validator: {
    // Biểu thức kiểm tra document
  },
  validationLevel: "strict",
  validationAction: "error"
})
```

Cấu trúc khi thay đổi collection đã tồn tại:

```javascript
db.runCommand({
  collMod: "courses",
  validator: {
    // Bộ quy tắc mới
  },
  validationLevel: "strict",
  validationAction: "error"
})
```

Một `validator` không phải một câu lệnh `find()` để lấy dữ liệu và cũng không phải migration script. Nó là **điều kiện chấp nhận trạng thái dữ liệu** khi MongoDB xử lý thao tác ghi.

## 2. Phân công công việc giữa `$jsonSchema` và biểu thức truy vấn

Giả sử mỗi khóa học có các thuộc tính sau:

```javascript
{
  _id: "course-101",
  code: "MDB-101",
  name: "MongoDB cơ bản",
  status: "published",
  capacity: NumberInt(30),
  enrolled: NumberInt(12),
  startsAt: ISODate("2026-12-01T00:00:00Z"),
  endsAt: ISODate("2027-01-15T00:00:00Z"),
  publishedAt: ISODate("2026-11-01T00:00:00Z"),
  tags: ["database", "mongodb"]
}
```

Ta muốn bảo đảm:

| Quy tắc nghiệp vụ | Cách diễn tả phù hợp |
| --- | --- |
| Phải có `code`, `name`, `status`, `capacity`, `enrolled`, `startsAt`, `endsAt` | `$jsonSchema.required` |
| `code` và `name` là chuỗi | `$jsonSchema.properties.*.bsonType` |
| `capacity`, `enrolled` là số nguyên BSON không âm | `bsonType: "int"` và `minimum: 0` |
| `status` thuộc `draft`, `published`, `archived` | `$jsonSchema.enum` |
| `startsAt`, `endsAt` là BSON Date | `bsonType: "date"` |
| `code` theo mẫu ba chữ hoa, gạch nối, ba chữ số | `code: { $regex: "^[A-Z]{3}-[0-9]{3}$" }` hoặc `pattern` của JSON Schema |
| `enrolled` không vượt `capacity` | `$expr: { $lte: ["$enrolled", "$capacity"] }` |
| `endsAt` phải sau `startsAt` | `$expr: { $gt: ["$endsAt", "$startsAt"] }` |
| Nếu `status: "published"` thì `publishedAt` phải là Date | `$or` kết hợp `status: { $ne: "published" }` với `publishedAt: { $type: "date" }` |
| `tags`, nếu có, là mảng các chuỗi | `bsonType: "array"` và `items` |

Về phương pháp, `$jsonSchema` phù hợp để định nghĩa **hợp đồng hình dạng/kiểu**; biểu thức truy vấn phù hợp cho **điều kiện giá trị hoặc quan hệ**. Nhiều điều kiện có thể diễn tả được theo cả hai cách. Hãy chọn cách khiến quy tắc dễ đọc và dễ bảo trì nhất.

## 3. Xây dựng validator kết hợp bằng `$and`

Trước hết, chọn database thực hành:

```javascript
use mongo_validation_lab
```

Tạo biến `courseValidator` trong `mongosh`:

```javascript
const courseValidator = {
  $and: [
    {
      $jsonSchema: {
        bsonType: "object",
        required: [
          "code",
          "name",
          "status",
          "capacity",
          "enrolled",
          "startsAt",
          "endsAt"
        ],
        properties: {
          code: {
            bsonType: "string",
            minLength: 1,
            description: "code phải là chuỗi không rỗng"
          },
          name: {
            bsonType: "string",
            minLength: 1
          },
          status: {
            enum: ["draft", "published", "archived"]
          },
          capacity: {
            bsonType: "int",
            minimum: 0
          },
          enrolled: {
            bsonType: "int",
            minimum: 0
          },
          startsAt: {
            bsonType: "date"
          },
          endsAt: {
            bsonType: "date"
          },
          publishedAt: {
            bsonType: "date"
          },
          tags: {
            bsonType: "array",
            items: { bsonType: "string" }
          }
        }
      }
    },
    {
      code: { $regex: "^[A-Z]{3}-[0-9]{3}$" }
    },
    {
      $expr: {
        $and: [
          { $lte: ["$enrolled", "$capacity"] },
          { $gt: ["$endsAt", "$startsAt"] }
        ]
      }
    },
    {
      $or: [
        { status: { $ne: "published" } },
        { publishedAt: { $type: "date" } }
      ]
    }
  ]
};
```

Tạo collection bằng validator:

```javascript
db.createCollection("courses", {
  validator: courseValidator,
  validationLevel: "strict",
  validationAction: "error"
})
```

Ví dụ giả định collection `courses` chưa tồn tại. Nếu đã tạo trước đó, hãy dùng một tên collection thực hành khác hoặc thay validator qua `collMod`; không chạy `drop()` trên collection chứa dữ liệu cần giữ.

### Đọc từng lớp của `$and`

Biểu thức ngoài cùng:

```javascript
{
  $and: [
    { $jsonSchema: { /* ... */ } },
    { code: { $regex: "..." } },
    { $expr: { /* ... */ } },
    { $or: [ /* ... */ ] }
  ]
}
```

Document được xem là hợp lệ khi **tất cả các nhánh** đều khớp:

1. Có các field bắt buộc và đúng kiểu BSON.
2. Mã khóa học đúng mẫu.
3. Số đăng ký không vượt sức chứa; ngày kết thúc sau ngày bắt đầu.
4. Khóa học ở trạng thái `published` có ngày xuất bản hợp lệ.

Không nên dựa vào việc các nhánh `$and` chạy theo thứ tự được viết hoặc được "short-circuit" giống chương trình JavaScript. Validator là một biểu thức do database đánh giá; mục tiêu là tổng điều kiện đúng, không phải tạo chuỗi bước thực thi.

### `$jsonSchema` chưa thay thế được mọi quy tắc nghiệp vụ

`$jsonSchema` đã xác nhận cả `capacity` và `enrolled` là số nguyên không âm. Tuy nhiên, kiểm tra `minimum: 0` riêng từng field không chứng minh `enrolled <= capacity`: một document có `capacity: 10` và `enrolled: 15` vẫn thỏa điều kiện `minimum`. Phần so sánh **giữa hai field** được diễn tả bằng `$expr`.

Tương tự, `startsAt` và `endsAt` đều là Date chưa bảo đảm thứ tự thời gian. `$expr` biểu diễn ràng buộc này.

## 4. Biểu thức truy vấn: equality, comparison, regex và logic

Query expressions trong validator dùng các toán tử quen thuộc khi viết bộ lọc. Ví dụ một số điều kiện đơn giản:

```javascript
// Chỉ chấp nhận loại tiền VND
{ currency: "VND" }

// Tổng tiền từ 0 trở lên
{ total: { $gte: 0 } }

// Cho phép ba trạng thái được liệt kê
{ status: { $in: ["draft", "published", "archived"] } }

// Mã có cấu trúc nhất định
{ code: { $regex: "^[A-Z]{3}-[0-9]{3}$" } }
```

Các biểu thức này hữu ích khi kiểm tra **giá trị**, nhưng phải chú ý cách MongoDB xử lý trường thiếu hoặc không cùng kiểu. Ví dụ:

```javascript
{ score: { $gte: 0 } }
```

không tự thay thế được quy tắc `score` **bắt buộc là số nguyên**. Một validator rõ ràng nên kết hợp với:

```javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["score"],
    properties: {
      score: { bsonType: "int", minimum: 0 }
    }
  }
}
```

Với biểu thức logic:

- `$and`: tất cả điều kiện cần đúng.
- `$or`: ít nhất một nhánh cần đúng.
- `$nor`: không nhánh nào được khớp.
- `$expr`: dùng biểu thức aggregation được hỗ trợ để so sánh/biến đổi các giá trị trong **cùng document**.

Ví dụ quy tắc "không chấp nhận trạng thái archived khi còn người đăng ký":

```javascript
{
  $or: [
    { status: { $ne: "archived" } },
    { enrolled: 0 }
  ]
}
```

Biểu thức này thể hiện quan hệ điều kiện: trạng thái khác `archived`, **hoặc** số đăng ký bằng `0`. Nếu status là `archived` và enrolled dương thì không hợp lệ. Nếu status/enrolled bắt buộc và đúng kiểu theo `$jsonSchema`, ý nghĩa của điều kiện rõ ràng hơn.

### Biểu diễn điều kiện “nếu A thì B”

Trong logic:

```text
A => B  tương đương  (!A) OR B
```

Với "nếu đã xuất bản thì cần ngày xuất bản":

```javascript
{
  $or: [
    { status: { $ne: "published" } },
    { publishedAt: { $type: "date" } }
  ]
}
```

Nếu `status: "draft"`, nhánh đầu đúng và `publishedAt` có thể không có. Nếu `status: "published"`, nhánh đầu sai, nên nhánh thứ hai phải đúng. Trong ví dụ đầy đủ, `$jsonSchema` cũng quy định `publishedAt` là Date **khi field xuất hiện**.

### Khi dùng `$exists` cần hiểu null

```javascript
{ publishedAt: { $exists: true } }
```

chỉ xác nhận field **hiện diện**. Document `{publishedAt: null}` vẫn thỏa `$exists: true`. Nếu yêu cầu thật sự là BSON Date, nên dùng `{publishedAt: {$type: "date"}}` cùng schema.

`{ field: null }` cũng không phải cách phát biểu chắc chắn “field tồn tại và bằng null”, vì phép equality với `null` thường khớp cả document thiếu field. Hãy dùng kiểu/ràng buộc phù hợp với mục đích.

## 5. `$expr`: kiểm tra quan hệ giữa các field trong cùng document

Trong truy vấn MongoDB, `$expr` cho phép đặt biểu thức aggregation vào điều kiện. Một ví dụ độc lập cho collection đặt chỗ:

```javascript
{
  $expr: {
    $lte: ["$seatsBooked", "$seatsAvailable"]
  }
}
```

Ký hiệu `"$seatsBooked"` là **tham chiếu giá trị field** của document, còn chuỗi `"seatsBooked"` không có ký hiệu `$` sẽ chỉ là một hằng string. Đây là điểm dễ nhầm khi bắt đầu kết hợp query expressions với validation.

Biểu thức thời gian:

```javascript
{
  $expr: {
    $gt: ["$endsAt", "$startsAt"]
  }
}
```

Vì cả hai field đã được `$jsonSchema` yêu cầu mang kiểu Date, biểu thức này diễn đạt quan hệ thời gian thay vì so sánh chuỗi ngày theo thứ tự từ điển.

Có thể nhóm nhiều phép so sánh:

```javascript
{
  $expr: {
    $and: [
      { $gte: ["$enrolled", 0] },
      { $lte: ["$enrolled", "$capacity"] },
      { $gt: ["$endsAt", "$startsAt"] }
    ]
  }
}
```

Ở đây `$and` nằm **bên trong `$expr`**, sử dụng cú pháp biểu thức aggregation; còn `$and` bao ngoài `validator` kết hợp các **điều kiện truy vấn**. Hai cách nhìn tương tự nhau nhưng không được thay thế tùy ý giữa các vị trí cú pháp.

Các toán tử được phép dùng trong validator còn phụ thuộc quy tắc của MongoDB. Không phải mọi toán tử trong `find()` hay aggregation đều hợp lệ; ví dụ các toán tử yêu cầu thực thi JavaScript tùy ý, truy vấn toàn văn hoặc near-geospatial có các hạn chế riêng. Hãy kiểm tra tài liệu `collMod`/schema validation của đúng phiên bản trước khi đưa biểu thức ít phổ biến vào validator.

## 6. Thực hành: ghi document hợp lệ và không hợp lệ

Các lệnh sau giả định đã tạo thành công `courses` với `courseValidator` ở mục 3.

### 6.1. Một document hợp lệ

```javascript
db.courses.insertOne({
  _id: "course-101",
  code: "MDB-101",
  name: "MongoDB căn bản",
  status: "published",
  capacity: NumberInt(30),
  enrolled: NumberInt(12),
  startsAt: ISODate("2026-12-01T00:00:00Z"),
  endsAt: ISODate("2027-01-15T00:00:00Z"),
  publishedAt: ISODate("2026-11-01T00:00:00Z"),
  tags: ["database", "mongodb"]
})
```

Document này đáp ứng toàn bộ các nhánh: đúng kiểu, đúng mã khóa học, số học viên không vượt giới hạn, khoảng thời gian đúng thứ tự và có ngày xuất bản.

### 6.2. Sai kiểu dữ liệu

```javascript
db.courses.insertOne({
  code: "MDB-102",
  name: "Kiểu dữ liệu BSON",
  status: "draft",
  capacity: "30", // String, không phải BSON int
  enrolled: NumberInt(0),
  startsAt: ISODate("2026-12-01T00:00:00Z"),
  endsAt: ISODate("2026-12-20T00:00:00Z")
})
```

Với `validationAction: "error"`, document bị từ chối do `capacity` không có `bsonType: "int"`. Dù `"30"` trông giống số, MongoDB không tự xem đó là kiểu int.

### 6.3. Đúng kiểu nhưng vi phạm quan hệ giữa field

```javascript
db.courses.insertOne({
  code: "MDB-103",
  name: "Thực hành truy vấn",
  status: "draft",
  capacity: NumberInt(10),
  enrolled: NumberInt(12), // Lớn hơn capacity
  startsAt: ISODate("2026-12-01T00:00:00Z"),
  endsAt: ISODate("2026-12-20T00:00:00Z")
})
```

Các giá trị số đều là int và không âm, nhưng điều kiện `$expr.$lte` không thỏa. Trường hợp này minh họa lý do cần kết hợp query expression thay vì chỉ kiểm tra BSON type.

### 6.4. Vi phạm điều kiện phụ thuộc trạng thái

```javascript
db.courses.insertOne({
  code: "MDB-104",
  name: "Cấu trúc document",
  status: "published",
  capacity: NumberInt(20),
  enrolled: NumberInt(0),
  startsAt: ISODate("2026-12-01T00:00:00Z"),
  endsAt: ISODate("2026-12-20T00:00:00Z")
  // Thiếu publishedAt
})
```

Document có đủ các field thuộc danh sách `required` của schema, nhưng nhánh `$or` vẫn sai do `status` là `published` và `publishedAt` không phải Date.

### 6.5. Sai định dạng mã

```javascript
db.courses.insertOne({
  code: "mdb101", // Không khớp ^[A-Z]{3}-[0-9]{3}$
  name: "Tổng quan MongoDB",
  status: "draft",
  capacity: NumberInt(20),
  enrolled: NumberInt(0),
  startsAt: ISODate("2026-12-01T00:00:00Z"),
  endsAt: ISODate("2026-12-20T00:00:00Z")
})
```

Giá trị `code` là string nhưng không đúng mẫu regex. Lỗi này thuộc nhánh điều kiện truy vấn `$regex`, không phải nhánh kiểm tra kiểu.

Các ví dụ cố ý dùng mã khác nhau để tránh trùng `_id`. Nếu chạy lặp lại lệnh insert hợp lệ có cùng `_id`, lỗi duplicate key xảy ra độc lập với schema validation.

## 7. Validation với `update`: kiểm tra trạng thái document sau khi sửa

Giả sử document `course-101` đang có `capacity: 30` và `enrolled: 12`. Một yêu cầu giảm sức chứa xuống 10:

```javascript
db.courses.updateOne(
  { _id: "course-101" },
  { $set: { capacity: NumberInt(10) } }
)
```

sẽ vi phạm `enrolled <= capacity`, do đó bị validation từ chối với cấu hình `strict` + `error`. MongoDB đánh giá **document kết quả**, không chỉ các field xuất hiện trong `$set`.

Một cập nhật thỏa điều kiện:

```javascript
db.courses.updateOne(
  { _id: "course-101" },
  {
    $set: {
      capacity: NumberInt(40),
      enrolled: NumberInt(15)
    }
  }
)
```

Nếu thay đổi từ `draft` sang `published` và muốn giữ hợp đồng dữ liệu, nên cập nhật trạng thái và ngày xuất bản trong cùng một thao tác:

```javascript
db.courses.updateOne(
  { code: "MDB-105" },
  {
    $set: {
      status: "published",
      publishedAt: new Date()
    }
  }
)
```

Ví dụ cập nhật này chỉ có tác dụng nếu document `MDB-105` tồn tại; nếu không, `matchedCount` bằng 0. Với một document thuộc trạng thái `draft` đang có nhưng thiếu `publishedAt`, chỉ đổi `status` có thể không qua validator.

MongoDB hỗ trợ tính nguyên tử của một thao tác cập nhật trong **một document**, giúp bảo đảm các field liên quan có thể cùng chuyển sang trạng thái hợp lệ. Nếu nghiệp vụ có ràng buộc **giữa nhiều document** (chẳng hạn tổng số học viên ở nhiều collection không vượt một hạn mức), một validator đơn lẻ không giải quyết được toàn bộ bài toán; cần thiết kế giao dịch, mô hình dữ liệu hoặc cơ chế kiểm soát ở tầng ứng dụng phù hợp.

## 8. Thay đổi validator bằng `collMod`

Khi collection đã có dữ liệu, có thể cập nhật validator thay vì xóa và tạo lại. Ví dụ chính sách mới quy định khóa học `archived` phải có `enrolled: 0`. Ta có thể mở rộng validator đã khai báo trong phiên `mongosh` hiện tại:

```javascript
const updatedCourseValidator = {
  $and: [
    courseValidator,
    {
      $or: [
        { status: { $ne: "archived" } },
        { enrolled: NumberInt(0) }
      ]
    }
  ]
};

db.runCommand({
  collMod: "courses",
  validator: updatedCourseValidator,
  validationLevel: "strict",
  validationAction: "warn"
})
```

Lưu ý:

- `courseValidator` là biến được tạo ở mục 3, tồn tại nếu đang cùng phiên `mongosh`. Khi mở phiên mới, cần tạo lại biến hoặc lấy/biên soạn validator đầy đủ.
- `collMod` nhận **toàn bộ biểu thức validator mới**; nó không tự động nối một điều kiện mới vào validator cũ.
- Chế độ `warn` ở đây minh họa cách quan sát lỗi trong giai đoạn chuyển đổi. Thao tác ghi vi phạm có thể vẫn được phép; ứng dụng không nên coi `warn` là biện pháp cưỡng chế.
- Trước khi đặt `validationAction: "error"`, cần phát hiện và xử lý những document lịch sử không đáp ứng quy tắc mới.

Sau thay đổi, đọc metadata:

```javascript
db.getCollectionInfos({ name: "courses" })
```

Hoặc chỉ lấy các tùy chọn:

```javascript
const infos = db.getCollectionInfos({ name: "courses" });
if (infos.length !== 1) {
  throw new Error("Không tìm thấy đúng một collection courses");
}
printjson(infos[0].options);
```

Khi đã hoàn thành chuyển đổi, có thể nâng chế độ cưỡng chế:

```javascript
db.runCommand({
  collMod: "courses",
  validationLevel: "strict",
  validationAction: "error"
})
```

Điều này thay đổi mức kiểm soát ghi, không chỉnh sửa các document cũ.

### `validationLevel`: `strict`, `moderate`, `off`

| Giá trị | Ảnh hưởng |
| --- | --- |
| `strict` | Kiểm tra các insert và update thông thường theo validator |
| `moderate` | Kiểm tra insert và update đối với document trước đó hợp lệ; nới kiểm tra update đối với document vốn đã không hợp lệ |
| `off` | Không áp dụng document validation |

`moderate` có thể dùng khi bộ dữ liệu cũ chưa đáp ứng schema mới và cần giai đoạn nâng cấp. Tuy nhiên, nó không tự đưa dữ liệu cũ về đúng schema.

### `validationAction`: `error` và `warn`

| Giá trị | Nếu document vi phạm |
| --- | --- |
| `error` | MongoDB từ chối thao tác ghi |
| `warn` | MongoDB cho ghi và ghi thông tin cảnh báo |

Một số phiên bản còn có những giá trị action mới hơn, nên cần đối chiếu tài liệu máy chủ đang dùng trước khi triển khai.

## 9. Kết hợp nhiều nhánh `$or` và `$and` trong quy tắc thực tế

Hãy xét collection `payments` với mô hình:

```javascript
{
  paymentId: "PAY-101",
  method: "card",
  status: "settled",
  amount: NumberDecimal("120.50"),
  card: {
    token: "tok_example"
  },
  settledAt: ISODate("2026-11-10T09:00:00Z")
}
```

Yêu cầu:

1. `paymentId`, `method`, `status` và `amount` phải có kiểu hợp lệ.
2. `method` chỉ là `card` hoặc `bank`.
3. Nếu dùng `card`, phải có `card.token` là string.
4. Nếu `status` là `settled`, phải có `settledAt` là Date.

Một phần validator tương ứng:

```javascript
const paymentValidator = {
  $and: [
    {
      $jsonSchema: {
        bsonType: "object",
        required: ["paymentId", "method", "status", "amount"],
        properties: {
          paymentId: { bsonType: "string" },
          method: { enum: ["card", "bank"] },
          status: { enum: ["pending", "settled", "failed"] },
          amount: {
            bsonType: "decimal",
            minimum: NumberDecimal("0.00")
          },
          settledAt: { bsonType: "date" },
          card: {
            bsonType: "object",
            properties: {
              token: { bsonType: "string" }
            }
          }
        }
      }
    },
    {
      $or: [
        { method: { $ne: "card" } },
        { "card.token": { $type: "string" } }
      ]
    },
    {
      $or: [
        { status: { $ne: "settled" } },
        { settledAt: { $type: "date" } }
      ]
    }
  ]
};
```

Hai `$or` độc lập nằm trong `$and`, vì cả hai quy tắc điều kiện đều phải được thỏa. Nếu gộp tất cả vào một `$or` lớn, document có thể vượt qua nhờ một nhánh đúng dù vi phạm yêu cầu còn lại.

Ví dụ này cũng cho thấy đối với tiền tệ, `NumberDecimal` và `bsonType: "decimal"` phù hợp hơn việc lưu số tiền dưới string hoặc dùng số dấu phẩy động nhị phân khi nghiệp vụ cần độ chính xác thập phân.

## 10. Thiết lập schema validation qua Java Sync Driver

Trong Java, MongoDB Sync Driver dùng các lớp `Bson` và `Document` để mô tả validator. Có thể biểu diễn bộ quy tắc kết hợp giống `mongosh`, rồi truyền cho `CreateCollectionOptions`.

Đoạn mã sau minh họa phiên bản đơn giản của quy tắc khóa học, gồm kiểu và hai quan hệ giữa field:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.CreateCollectionOptions;
import com.mongodb.client.model.ValidationAction;
import com.mongodb.client.model.ValidationLevel;
import com.mongodb.client.model.ValidationOptions;
import org.bson.Document;

public class CourseValidationSetup {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        Document schema = Document.parse("""
            {
              "$jsonSchema": {
                "bsonType": "object",
                "required": [
                  "code", "capacity", "enrolled", "startsAt", "endsAt"
                ],
                "properties": {
                  "code": { "bsonType": "string" },
                  "capacity": { "bsonType": "int", "minimum": 0 },
                  "enrolled": { "bsonType": "int", "minimum": 0 },
                  "startsAt": { "bsonType": "date" },
                  "endsAt": { "bsonType": "date" }
                }
              }
            }
            """);

        Document relation = Document.parse("""
            {
              "$expr": {
                "$and": [
                  { "$lte": ["$enrolled", "$capacity"] },
                  { "$gt": ["$endsAt", "$startsAt"] }
                ]
              }
            }
            """);

        Document validator = new Document(
            "$and", java.util.List.of(schema, relation));

        ValidationOptions validation = new ValidationOptions()
            .validator(validator)
            .validationLevel(ValidationLevel.STRICT)
            .validationAction(ValidationAction.ERROR);

        CreateCollectionOptions options =
            new CreateCollectionOptions().validationOptions(validation);

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database =
                client.getDatabase("mongo_validation_lab");
            database.createCollection("javaCourses", options);
        }
    }
}
```

Ví dụ dùng Java text block (Java 15+) và cần dependency MongoDB Java Sync Driver phù hợp. Nó **tạo collection mới**, nên sẽ lỗi nếu `javaCourses` đã tồn tại. Khi collection đã có, hãy dùng `collMod` qua `runCommand` với quyền và kế hoạch thay đổi phù hợp.

Trong ứng dụng Spring Data MongoDB, có thể cấu hình validator qua API tương ứng của Spring Data. Dù dùng driver trực tiếp hay framework, nguồn thực thi validation cuối cùng là MongoDB server. Hãy bảo đảm phiên bản driver/server hỗ trợ các toán tử đã dùng.

## 11. Phạm vi và giới hạn của việc kết hợp

### 11.1. Validator không thay thế unique index

Nếu cần `code` duy nhất giữa mọi document, `$jsonSchema` hoặc query expression trên một document không thể kiểm tra một cách đáng tin cậy rằng mã đó chưa tồn tại ở document khác. Hãy dùng **unique index**:

```javascript
db.courses.createIndex(
  { code: 1 },
  { unique: true, name: "code_unique" }
)
```

Trước khi tạo unique index trên dữ liệu hiện có, cần xử lý các giá trị trùng. Nếu index được tạo thành công, MongoDB áp dụng ràng buộc unique độc lập với validation.

### 11.2. Validator không thực thi phép tra cứu collection khác

Quy tắc như “`studentId` phải tồn tại trong collection `students`” không thể giải quyết bằng cách viết một validator thông thường gọi `$lookup` sang collection khác. Các quan hệ tham chiếu cần được ứng dụng quản lý, thiết kế dữ liệu phù hợp hoặc dùng transaction khi cần cập nhật nhiều document/collection.

### 11.3. Không phải toàn bộ JSON Schema chuẩn đều có sẵn

MongoDB hỗ trợ **một tập con và phần mở rộng cho BSON** của JSON Schema. `bsonType` là phần mở rộng quan trọng để kiểm tra kiểu như `objectId`, `date`, `int`, `long`, `decimal`. Không nên chép nguyên một schema dành cho thư viện JSON Schema bên ngoài rồi mặc định tất cả keyword đều được MongoDB chấp nhận.

### 11.4. Không phải mọi biểu thức truy vấn đều được phép

Validator không cho phép dùng một số toán tử truy vấn chuyên biệt và các cơ chế thực thi mã tùy ý. `$expr` có hỗ trợ theo quy định của MongoDB nhưng không đồng nghĩa mọi toán tử aggregation bên trong `$expr` đều được phép; một số toán tử hoặc kết hợp bị hạn chế. Cần đối chiếu với phiên bản máy chủ và thử biểu thức trên môi trường tương đương trước khi phát hành.

### 11.5. Hiệu năng và độ phức tạp

MongoDB cần đánh giá validator khi xử lý thao tác ghi chịu validation. Một schema đơn giản với một vài phép so sánh thường dễ kiểm soát hơn một biểu thức phức tạp gồm nhiều nhánh, phép biến đổi chuỗi và điều kiện lồng nhau. Với hệ thống ghi nhiều, hãy đánh giá ảnh hưởng hiệu năng, giữ thông báo lỗi và rule rõ ràng, tránh biểu thức tốn tài nguyên không cần thiết.

### 11.6. Chuyển đổi schema cho dữ liệu lịch sử

Khi thay validator sau khi đã có dữ liệu:

1. Thống kê document không đáp ứng quy tắc mới.
2. Xác định cách sửa dữ liệu đúng nghiệp vụ; tránh tự điền giá trị giả chỉ để qua validation.
3. Cân nhắc giai đoạn `validationAction: "warn"` hoặc `validationLevel: "moderate"` nếu cần chuyển đổi dần.
4. Chỉ áp `strict` và `error` sau khi đã kiểm soát tác động của các thao tác ghi hiện tại.

Một số thao tác với quyền và tùy chọn thích hợp có thể sử dụng `bypassDocumentValidation`; do vậy validator cần đi cùng thiết kế phân quyền và kiểm tra ứng dụng. Những thay đổi validation cũng không tự động kiểm tra lại toàn bộ document đã ghi trước đó.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Chèn số `30` nhưng bị báo sai kiểu | Schema dùng `bsonType: "int"`, trong khi client gửi BSON Double/Long/Decimal | Xem kiểu BSON thực tế; thống nhất kiểu và cách khởi tạo (`NumberInt` trong mongosh) |
| Chỉ kiểm tra `minimum` nhưng vẫn có `enrolled > capacity` | Ràng buộc giữa field không được khai báo | Bổ sung `$expr` so sánh hai field |
| Có `publishedAt: null` mà vẫn qua kiểm tra hiện diện | `$exists: true` không kiểm tra kiểu hoặc non-null | Kiểm tra `$type: "date"` và schema |
| Gộp hai quy tắc vào một `$or` khiến một quy tắc bị bỏ qua | Nhầm ý nghĩa `$or` và `$and` | Đặt các điều kiện bắt buộc trong `$and`; chỉ dùng `$or` cho lựa chọn hợp lệ |
| Update một field không liên quan vẫn bị từ chối | Document sau update còn vi phạm validator ở field khác | Sửa dữ liệu cũ hoặc lập kế hoạch migration; kiểm tra `validationLevel` |
| `collMod` thành công nhưng document cũ vẫn sai | Validation không tự migrate document | Cần thao tác cập nhật dữ liệu riêng |
| Dùng query operator trong validator bị lỗi | Toán tử không được phép hoặc khác phiên bản | Xem quy định validator ở server hiện tại |
| `warn` mà ứng dụng vẫn ghi document sai | `warn` là chế độ quan sát, không chặn ghi | Chuyển `error` khi dữ liệu và ứng dụng đã sẵn sàng |
| Muốn kiểm tra trùng `code` bằng `$jsonSchema` | Kiểm tra duy nhất liên document nằm ngoài phạm vi schema | Dùng unique index |

Đối với lỗi ghi do validation, MongoDB thường trả về thông tin kiểu `Document failed validation` (thường gắn với mã lỗi 121). Tùy server và driver, chi tiết lỗi có thể chứa phần mô tả quy tắc không đạt. Nên ghi nhận mã lỗi và chi tiết đủ để sửa dữ liệu, nhưng tránh đưa dữ liệu nhạy cảm vào log.

## 13. Bài tập thực hành

### Bài 1: thêm điều kiện chỉ cho phép điểm trong khoảng

Collection `exams` có schema bắt buộc `score` là BSON int. Hãy bổ sung điều kiện truy vấn sao cho chỉ nhận điểm từ 0 đến 100.

**Đáp án tham khảo:**

```javascript
{
  $and: [
    {
      $jsonSchema: {
        bsonType: "object",
        required: ["score"],
        properties: {
          score: { bsonType: "int" }
        }
      }
    },
    {
      score: { $gte: 0, $lte: 100 }
    }
  ]
}
```

Cũng có thể dùng `minimum: 0`, `maximum: 100` trực tiếp trong `$jsonSchema`. Ví dụ kết hợp được trình bày để rèn cách đọc hai loại điều kiện.

### Bài 2: kiểm tra ngày bắt đầu và kết thúc

Collection `events` có `startAt` và `endAt` đều là BSON Date. Viết một nhánh `$expr` chỉ chấp nhận `endAt > startAt`.

**Đáp án tham khảo:**

```javascript
{
  $expr: {
    $gt: ["$endAt", "$startAt"]
  }
}
```

Khi đưa vào validator hoàn chỉnh, nên kết hợp thêm `$jsonSchema` bảo đảm cả hai field tồn tại và đúng kiểu.

### Bài 3: điều kiện phụ thuộc trạng thái

Một đơn hàng có `status` thuộc `pending`, `paid`, `cancelled`. Nếu `status: "paid"`, phải có `paidAt` là BSON Date. Viết biểu thức truy vấn tương ứng.

**Đáp án tham khảo:**

```javascript
{
  $or: [
    { status: { $ne: "paid" } },
    { paidAt: { $type: "date" } }
  ]
}
```

Thêm `$jsonSchema` để bắt buộc status và giới hạn tập giá trị, tránh việc trạng thái bị thiếu hoặc sai kiểu được coi là hợp lệ.

### Bài 4: phát hiện validator sai logic

Một người viết:

```javascript
{
  $or: [
    {
      $jsonSchema: {
        bsonType: "object",
        required: ["amount"],
        properties: {
          amount: { bsonType: "decimal" }
        }
      }
    },
    { amount: { $gt: 0 } }
  ]
}
```

Mục tiêu là “`amount` phải là Decimal128 **và** lớn hơn 0”. Biểu thức trên có đúng không?

**Đáp án:** Không. `$or` chỉ cần một điều kiện đúng, vì vậy một document có `amount` là Decimal128 nhưng bằng 0 có thể qua, hoặc một giá trị số khác kiểu nhưng lớn hơn 0 cũng có thể qua. Sửa `$or` thành `$and`, hoặc dùng `bsonType: "decimal"` kết hợp `minimum` phù hợp và quy tắc lớn hơn 0.

### Bài 5: kết hợp kiểm tra cấu trúc và ràng buộc mảng

Mỗi document `teams` phải có `members` là mảng string, ít nhất một phần tử, và `active: true`. Hãy viết validator kết hợp.

**Đáp án tham khảo:**

```javascript
{
  $and: [
    {
      $jsonSchema: {
        bsonType: "object",
        required: ["members", "active"],
        properties: {
          members: {
            bsonType: "array",
            minItems: 1,
            items: { bsonType: "string" }
          },
          active: { bsonType: "bool" }
        }
      }
    },
    { active: true }
  ]
}
```

Ở đây `active: true` là điều kiện giá trị; `bsonType: "bool"` chỉ kiểm tra kiểu. Hai quy tắc bổ sung cho nhau.

## 14. Tóm lược quy tắc thiết kế

Khi cần vừa kiểm soát kiểu dữ liệu vừa kiểm tra ràng buộc nghiệp vụ trong một document, hãy đi theo thứ tự:

1. **Mô tả cấu trúc bằng `$jsonSchema`**: field bắt buộc, kiểu BSON, `enum`, giới hạn số/chuỗi, object và array.
2. **Viết các điều kiện truy vấn còn thiếu**: `$in`, `$regex`, `$or`, `$nor` hoặc `$expr` để kiểm tra giá trị và quan hệ field.
3. **Dùng `$and` để kết hợp các quy tắc bắt buộc** và dùng `$or` cho các lựa chọn thay thế hoặc mệnh đề “nếu ... thì ...”.
4. **Tạo collection hoặc cập nhật `validator` bằng `collMod`**, chủ động chọn `validationLevel` và `validationAction`.
5. **Thử document hợp lệ, sai kiểu, thiếu field và vi phạm quan hệ**, cùng với thao tác update làm thay đổi trạng thái document.
6. **Phân biệt validation với các cơ chế khác**: unique index cho ràng buộc duy nhất liên document; logic ứng dụng/transaction cho quan hệ nhiều document; migration cho dữ liệu cũ.

Điểm cốt lõi là `$jsonSchema` và biểu thức truy vấn có **vai trò bổ trợ**: một bên bảo vệ hình dạng và kiểu BSON, bên kia diễn đạt các quy tắc giá trị và quan hệ mà việc khai báo kiểu riêng lẻ chưa thể bao quát.

# Thay đổi tùy chọn collection bằng `collMod` trong phạm vi được hỗ trợ

Trong MongoDB, một **collection** không chỉ chứa các document mà còn có thể mang theo cấu hình liên quan đến kiểm tra cấu trúc dữ liệu, chỉ mục, lưu giữ dữ liệu và một số tính năng của máy chủ. Các cấu hình này thường được đặt khi tạo collection hoặc index. Khi yêu cầu nghiệp vụ thay đổi, ta không nhất thiết phải xóa collection để tạo lại: lệnh **`collMod`** cho phép sửa **một số tùy chọn được MongoDB hỗ trợ** ngay trên collection hiện có.

Từ khóa quan trọng là **một số**. `collMod` không phải lệnh tổng quát để sửa mọi thuộc tính của collection; loại collection, tính năng, phiên bản máy chủ và điều kiện của từng tùy chọn quyết định việc thay đổi có được phép hay không. Bài học tập trung vào cách nhận diện phạm vi hỗ trợ, thao tác an toàn và đọc kết quả qua `mongosh`.

## 1. `collMod` là gì?

`collMod` là **database command** dùng để sửa các thuộc tính được hỗ trợ của một collection hoặc view đang tồn tại trong database hiện tại.

Cú pháp khái quát:

```javascript
db.runCommand({
  collMod: "<ten_collection_hoac_view>",
  // Các tùy chọn có thể sửa trong phiên bản MongoDB đang dùng
})
```

Ví dụ thay đổi chế độ xử lý document không đạt quy tắc validation:

```javascript
use mongo_lab

db.runCommand({
  collMod: "registrations",
  validationAction: "warn"
})
```

Khi thành công, phản hồi có `ok: 1`. Khi thất bại, máy chủ trả về `ok: 0` cùng mã lỗi và mô tả, chẳng hạn collection không tồn tại, không đủ quyền, tùy chọn không hỗ trợ hoặc giá trị tùy chọn không hợp lệ.

**Phân biệt ba thao tác:**

| Thao tác | Khi nào dùng? | Ví dụ |
| --- | --- | --- |
| `db.createCollection()` | Tạo một collection mới cùng các tùy chọn ban đầu | `db.createCollection("registrations", {...})` |
| `db.runCommand({ collMod: ... })` | Sửa tùy chọn hỗ trợ trên collection/view đang có | Sửa validator, đổi TTL của index |
| `db.collection.updateOne()/updateMany()` | Sửa **document dữ liệu** trong collection | Đổi `status` của đăng ký |

`collMod` tác động đến **cấu hình của collection hoặc index**, không tự chuyển đổi toàn bộ dữ liệu đang lưu thành schema mới. Ví dụ, bổ sung validator không làm các document cũ xuất hiện field mới, cũng không tự sửa các giá trị có kiểu sai.

## 2. Những gì có thể sửa và những gì không thể sửa tùy ý

MongoDB bổ sung một số khả năng `collMod` qua từng phiên bản. Bảng sau định hướng phạm vi thường gặp; tài liệu của **phiên bản server đang vận hành** vẫn là căn cứ quyết định cuối cùng.

| Nhóm | Các thay đổi tiêu biểu | Giới hạn cần nhớ |
| --- | --- | --- |
| Document validation | `validator`, `validationLevel`, `validationAction` | Quy tắc chỉ ảnh hưởng các thao tác ghi chịu validation; không tự quét/sửa dữ liệu quá khứ |
| Index TTL | `index.expireAfterSeconds` cho index đủ điều kiện | Phải chỉ đúng index và thỏa điều kiện về loại index; dữ liệu có thể bị xóa theo TTL |
| Trạng thái index | `index.hidden` để ẩn/hiện index | Ẩn khỏi query planner không đồng nghĩa xóa index |
| Chuyển index sang unique | Quy trình `prepareUnique` và chuyển unique trên phiên bản hỗ trợ | Cần kiểm tra dữ liệu trùng và làm đúng quy trình; không phải mọi index đều đổi được |
| View | `viewOn`, `pipeline` | Thay đổi định nghĩa view, không sửa document nguồn; có giới hạn riêng của view |
| Một số tính năng mới | Tùy chọn time series, change stream pre/post images, capped collection, v.v. | Phụ thuộc phiên bản, loại collection và quy định của từng tính năng |

**Những việc không nên hiểu là nhiệm vụ của `collMod`:**

- Đổi tên collection: dùng thao tác `renameCollection` hoặc API đổi tên tương ứng.
- Đổi collection thường thành capped hoặc time series một cách tùy ý: đây là các lựa chọn cấu trúc có giới hạn, không phải cờ có thể bật/tắt tự do.
- Đổi **default collation** của collection sau khi tạo: không được coi là tùy chọn tùy ý sửa qua `collMod`; hãy thiết kế collection/index phù hợp nếu cần quy tắc so sánh khác.
- Tạo index mới hoặc thay đổi tùy ý khóa index: dùng lệnh quản lý index như `createIndex()`, và cân nhắc tạo index thay thế.
- Đổi shard key: phải theo quy trình dành riêng cho sharding và phiên bản hỗ trợ, không dùng `collMod` như lối tắt.
- Xóa collection, xóa document, chuyển tên database: dùng đúng lệnh cho từng nghiệp vụ.

Trong nhóm database và collection, nguyên tắc là **xác định rõ tùy chọn nào thuộc phạm vi sửa đổi được trước khi chạy lệnh**.

## 3. Chuẩn bị môi trường thực hành và xem cấu hình hiện tại

Các ví dụ dùng database `mongo_lab`, collection `registrations` và tài liệu đăng ký khóa học. Chỉ chạy thao tác tạo, ghi hoặc sửa trên database thực hành có quyền thích hợp.

```javascript
use mongo_lab

db.createCollection("registrations", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["studentId", "courseCode", "active"],
      properties: {
        studentId: { bsonType: "string" },
        courseCode: { bsonType: "string" },
        active: { bsonType: "bool" },
        registeredAt: { bsonType: "date" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "warn"
})
```

Vì collection đang sử dụng chế độ `warn`, document vi phạm quy tắc có thể vẫn được ghi và máy chủ ghi cảnh báo. Để thực hành trên collection mới có thể kiểm soát được, đừng chạy lại `createCollection()` khi collection đã tồn tại; cần kiểm tra trạng thái trước hoặc sử dụng tên lab khác.

Thêm hai document hợp lệ:

```javascript
db.registrations.insertMany([
  {
    _id: "reg-101",
    studentId: "u101",
    courseCode: "MDB101",
    active: true,
    registeredAt: new Date("2026-01-10T08:00:00Z")
  },
  {
    _id: "reg-102",
    studentId: "u102",
    courseCode: "MDB101",
    active: false,
    registeredAt: new Date("2026-01-11T08:00:00Z")
  }
])
```

### Đọc lại metadata của collection

```javascript
db.getCollectionInfos({ name: "registrations" })
```

Kết quả cho biết metadata của collection, trong đó có `options` với các tùy chọn đã cấu hình, ví dụ `validator`, `validationLevel` và `validationAction`. Để quan sát gọn hơn:

```javascript
const infos = db.getCollectionInfos({ name: "registrations" });
if (infos.length !== 1) {
  throw new Error("Không tìm thấy đúng một collection registrations");
}
printjson(infos[0].options);
```

Khi cần xem index:

```javascript
db.registrations.getIndexes()
```

`getIndexes()` hiển thị tên, khóa, tính unique, TTL hoặc trạng thái hidden nếu có. Đây là thông tin quan trọng trước khi sửa index bằng `collMod`.

Ngoài `db.runCommand()`, có thể xác định database tường minh:

```javascript
db.getSiblingDB("mongo_lab").runCommand({
  collMod: "registrations",
  validationAction: "warn"
})
```

Cách này hữu ích khi phiên làm việc đang đứng ở database khác, vì `collMod` sẽ thao tác trên collection thuộc **database nhận lệnh**.

## 4. Thay đổi `validator`: điều chỉnh quy tắc dữ liệu

**Document validation** cho phép kiểm soát kiểu và hình dạng document được ghi vào collection. Validator có thể dùng biểu thức truy vấn MongoDB hoặc `$jsonSchema`.

Giả sử yêu cầu mới: ngoài ba field bắt buộc `studentId`, `courseCode`, `active`, mỗi đăng ký có thể có `status` thuộc một trong ba giá trị `enrolled`, `completed`, `cancelled`. Ta thêm điều kiện này bằng `collMod`:

```javascript
db.runCommand({
  collMod: "registrations",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["studentId", "courseCode", "active"],
      properties: {
        studentId: {
          bsonType: "string",
          description: "Mã học viên phải là chuỗi"
        },
        courseCode: {
          bsonType: "string",
          description: "Mã khóa học phải là chuỗi"
        },
        active: {
          bsonType: "bool",
          description: "Trạng thái active phải là boolean"
        },
        registeredAt: {
          bsonType: "date"
        },
        status: {
          enum: ["enrolled", "completed", "cancelled"]
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "warn"
})
```

`status` ở đây **chưa** nằm trong `required`; các document trước đó vẫn có thể tồn tại mà chưa có `status`. Quy tắc chỉ kiểm tra giá trị khi field đó có mặt. Nếu đổi `required` thành:

```javascript
required: ["studentId", "courseCode", "active", "status"]
```

thì các document cũ thiếu `status` không tự được sửa. Chúng có thể bị từ chối khi có các thao tác ghi chịu validation trong chế độ `strict` + `error`.

**Lưu ý cách áp dụng:** Khi gửi `validator` mới, hãy ghi đầy đủ toàn bộ quy tắc mong muốn. Không nên cho rằng `collMod` sẽ tự “ghép thêm” riêng trường `status` vào validator cũ; đối tượng validator mới là cấu hình thay thế.

### Bổ sung field cho các document cũ trước khi bắt buộc

Trong môi trường lab, có thể cập nhật dữ liệu chưa có `status`:

```javascript
db.registrations.updateMany(
  { status: { $exists: false } },
  { $set: { status: "enrolled" } }
)
```

Sau khi dữ liệu đã được điều chỉnh phù hợp, mới cân nhắc bổ sung `status` vào `required` và chuyển sang `validationAction: "error"`. Trên dữ liệu thật, giá trị mặc định phải phản ánh nghiệp vụ; không được mặc định mọi đăng ký cũ là `enrolled` nếu chúng thực tế đã hoàn thành hoặc hủy.

## 5. `validationLevel` và `validationAction`: mức kiểm tra và cách phản ứng

Đây là hai nhóm tùy chọn khác nhau:

- **`validationLevel`** quyết định document nào được kiểm tra.
- **`validationAction`** quyết định MongoDB làm gì khi một thao tác ghi vi phạm validator.

### 5.1. `validationLevel`

| Giá trị | Ý nghĩa điển hình |
| --- | --- |
| `strict` | Kiểm tra các insert và các update thông thường trên document theo validator |
| `moderate` | Kiểm tra insert và update đối với document hiện đang hợp lệ; không áp quy tắc tương tự cho update trên document vốn đã không hợp lệ |
| `off` | Không áp document validation |

`moderate` hữu ích trong giai đoạn chuyển đổi schema vì cho phép một số document cũ chưa đạt validator tiếp tục được cập nhật. Điều này không đồng nghĩa chúng đã hợp lệ hoặc hệ thống đã hoàn thành migration.

Ví dụ đổi sang `moderate`:

```javascript
db.runCommand({
  collMod: "registrations",
  validationLevel: "moderate"
})
```

Nếu mong muốn tất cả thao tác ghi tiếp theo phải chịu validator, `strict` là lựa chọn rõ ràng hơn sau khi đã xử lý dữ liệu cũ.

### 5.2. `validationAction`

| Giá trị | Khi document không hợp lệ |
| --- | --- |
| `warn` | Cho phép thao tác ghi và ghi cảnh báo validation vào log máy chủ |
| `error` | Từ chối thao tác ghi vi phạm validator |

Một số phiên bản MongoDB mới còn cung cấp các hành vi khác, chẳng hạn ghi log bổ sung khi từ chối. Chỉ sử dụng giá trị có trong tài liệu của phiên bản MongoDB đang chạy.

Chuyển sang chế độ từ chối dữ liệu không hợp lệ:

```javascript
db.runCommand({
  collMod: "registrations",
  validationLevel: "strict",
  validationAction: "error"
})
```

Giờ thử một document có `active` sai kiểu:

```javascript
db.registrations.insertOne({
  studentId: "u103",
  courseCode: "MDB101",
  active: "true",
  status: "enrolled"
})
```

`active` là string `"true"`, trong khi validator yêu cầu BSON boolean `true` hoặc `false`, nên trong điều kiện thông thường thao tác bị từ chối bởi document validation.

Sửa lại:

```javascript
db.registrations.insertOne({
  studentId: "u103",
  courseCode: "MDB101",
  active: true,
  status: "enrolled"
})
```

Thao tác này phù hợp với validator. Nếu collection có các index unique hoặc ràng buộc khác, những ràng buộc đó vẫn được áp dụng độc lập.

### Validation không tự sửa lịch sử

Đổi `validationAction` từ `warn` sang `error` **không hồi tố kiểm tra rồi xóa document cũ**. Một document từng được chèn trong thời gian `warn` vẫn ở trong collection sau khi nâng chế độ, ngay cả khi nó không đạt validator mới. Những document như vậy cần được phát hiện, đánh giá và sửa bằng thao tác dữ liệu có kiểm soát.

Cũng cần biết rằng một số thao tác/luồng ghi có quyền đặc biệt có thể sử dụng cơ chế `bypassDocumentValidation` theo điều kiện của MongoDB. Validator giúp bảo vệ hợp đồng dữ liệu, nhưng không thay thế kiểm tra quyền và logic ứng dụng.

## 6. `collMod` đối với index TTL: thay đổi thời hạn lưu giữ

**TTL index (Time To Live)** cho phép MongoDB tự động xóa document sau thời gian tính từ giá trị trường ngày tháng được lập chỉ mục. Ví dụ collection `sessionEvents` chứa sự kiện phiên đăng nhập; ban đầu chỉ giữ 7 ngày.

### Tạo index TTL ban đầu

```javascript
db.sessionEvents.createIndex(
  { createdAt: 1 },
  {
    name: "createdAt_ttl",
    expireAfterSeconds: 604800
  }
)
```

Giá trị `604800` là số giây trong 7 ngày. Document phù hợp có `createdAt` là kiểu `Date`; các document không có ngày hợp lệ có thể không được TTL tự động xóa như mong đợi.

Ví dụ document:

```javascript
db.sessionEvents.insertOne({
  eventType: "login",
  userId: "u101",
  createdAt: new Date()
})
```

### Đổi từ 7 ngày sang 14 ngày

```javascript
db.runCommand({
  collMod: "sessionEvents",
  index: {
    name: "createdAt_ttl",
    expireAfterSeconds: 1209600
  }
})
```

Đây là ví dụ điển hình về sửa **option của index hiện có** mà không cần drop và tạo lại index. Tên index phải khớp index thực tế; đọc trước bằng:

```javascript
db.sessionEvents.getIndexes()
```

Đối với phiên bản hỗ trợ, `collMod` cũng có thể chuyển một single-field index phù hợp thành TTL index bằng cách thêm `expireAfterSeconds`. Việc này có điều kiện về phiên bản và loại index; không nên mặc định mọi index đều có thể đổi sang TTL. Cũng đừng nhầm option `index.expireAfterSeconds` trong ví dụ này với các tùy chọn TTL ở cấp collection dành riêng cho **time-series collection**.

### Tác động thực tế khi sửa TTL

Giả sử đổi ngược từ 14 ngày xuống 1 ngày:

```javascript
db.runCommand({
  collMod: "sessionEvents",
  index: {
    name: "createdAt_ttl",
    expireAfterSeconds: 86400
  }
})
```

Các document cũ hơn ngưỡng mới có thể nhanh chóng trở thành đối tượng bị xóa bởi tiến trình TTL. TTL deletion diễn ra **bất đồng bộ**, không có bảo đảm từng document bị xóa chính xác tại giây hết hạn. Giảm TTL trên collection lớn có thể gây khối lượng xóa đáng kể và ảnh hưởng hiệu năng.

Do vậy, trước khi đổi TTL trên môi trường thật, cần xác định phạm vi dữ liệu sẽ hết hạn, chủ động tính toán ảnh hưởng đến dung lượng, thao tác xóa và nhu cầu giữ lịch sử. Không dùng TTL như cơ chế yêu cầu xóa chính xác tức thời.

## 7. Ẩn và hiện index bằng `index.hidden`

MongoDB hỗ trợ **hidden index** trên các phiên bản tương ứng. Index bị ẩn vẫn tồn tại và tiếp tục được bảo trì khi dữ liệu thay đổi, nhưng query planner không xét nó để chọn kế hoạch truy vấn. Tính năng này hữu ích khi đánh giá liệu một index có còn cần cho truy vấn hay không.

Tạo index thử nghiệm:

```javascript
db.registrations.createIndex(
  { courseCode: 1 },
  { name: "courseCode_1" }
)
```

Ẩn index:

```javascript
db.runCommand({
  collMod: "registrations",
  index: {
    name: "courseCode_1",
    hidden: true
  }
})
```

Hiện lại:

```javascript
db.runCommand({
  collMod: "registrations",
  index: {
    name: "courseCode_1",
    hidden: false
  }
})
```

Sau mỗi lần, xem `db.registrations.getIndexes()` và kiểm tra hành vi truy vấn phù hợp. Cần phân biệt:

- **Ẩn index**: index vẫn chiếm không gian, vẫn được cập nhật và vẫn có thể duy trì ràng buộc của nó.
- **Xóa index**: loại bỏ cấu trúc index; phải xây dựng lại nếu muốn sử dụng về sau.
- **Vô hiệu hóa TTL**: không được suy ra từ `hidden: true`; ẩn index không phải một cách an toàn để tắt cơ chế hết hạn.

Không thể áp dụng mọi thao tác ẩn cho các index đặc biệt, chẳng hạn `_id`. Đừng cố sửa index hệ thống nếu không có hỗ trợ tường minh.

## 8. Chỉnh sửa định nghĩa view bằng `collMod`

Một **view** là cách biểu diễn kết quả truy vấn trên collection/view nguồn thông qua pipeline. View không tự giữ bản sao document như collection thường. Trong phạm vi được MongoDB hỗ trợ, `collMod` có thể cập nhật `viewOn` và `pipeline` cho view đã có.

Tạo view ban đầu chỉ hiển thị các đăng ký còn hoạt động:

```javascript
db.createView(
  "activeRegistrations",
  "registrations",
  [
    { $match: { active: true } },
    { $project: { studentId: 1, courseCode: 1, active: 1 } }
  ]
)
```

Khi yêu cầu mới cần thêm `status` vào kết quả:

```javascript
db.runCommand({
  collMod: "activeRegistrations",
  viewOn: "registrations",
  pipeline: [
    { $match: { active: true } },
    {
      $project: {
        studentId: 1,
        courseCode: 1,
        active: 1,
        status: 1
      }
    }
  ]
})
```

Đọc lại định nghĩa:

```javascript
db.getCollectionInfos({ name: "activeRegistrations" })
```

Lúc này các truy vấn qua `db.activeRegistrations.find()` nhìn thấy cấu trúc do pipeline mới cung cấp. Document trong `registrations` **không bị thay đổi** bởi thao tác chỉnh view.

Lưu ý rằng view có các ràng buộc riêng đối với namespace, pipeline và quyền truy cập. Không thể suy ra từ khả năng đổi pipeline rằng có thể tùy ý đổi default collation hoặc biến view thành collection chứa dữ liệu bằng `collMod`.

## 9. Các khả năng theo phiên bản cần xác định trước

Ngoài validator, TTL, hidden index và view, có những tham số `collMod` chỉ tồn tại trong một số dòng phiên bản hoặc áp dụng với kiểu collection cụ thể:

**Thay đổi cấu hình time-series collection.** MongoDB có thể cho phép sửa một số thiết lập như thời hạn giữ dữ liệu hay độ hạt của bucket trong điều kiện nhất định. Hướng thay đổi, tên option và ràng buộc có thể khác qua các phiên bản; không được áp cú pháp dành cho time series lên collection thường chỉ vì cùng dùng `collMod`.

**Pre/post images cho change stream.** Trên phiên bản hỗ trợ, có thể bật lưu hình ảnh trước/sau thay đổi bằng tùy chọn `changeStreamPreAndPostImages`:

```javascript
db.runCommand({
  collMod: "registrations",
  changeStreamPreAndPostImages: { enabled: true }
})
```

Đây là tính năng cần phiên bản tương thích (xuất hiện từ MongoDB 6.0), chính sách lưu giữ và việc sử dụng change stream phù hợp; không mặc định có trên mọi triển khai.

**Chuyển đổi non-unique index thành unique.** Các bản MongoDB hỗ trợ có quy trình chuyển đổi index hiện hữu với bước chuẩn bị (`prepareUnique`), kiểm tra và xử lý dữ liệu trùng trước khi hoàn tất `unique`. Không nên chạy trực tiếp lệnh chuyển đổi trên dữ liệu thật khi chưa xác minh version, điều kiện index và số lượng giá trị trùng.

**Capped collection.** Một số phiên bản hỗ trợ thay đổi giới hạn kích thước/số document của collection dạng capped bằng những tham số chuyên biệt. Đây không phải quyền chuyển một collection thường thành capped tùy ý.

Trong thực tế, có thể xác định phiên bản bằng:

```javascript
db.version()
db.adminCommand({ buildInfo: 1 })
```

Sau đó đối chiếu phần `collMod` dành cho **đúng phiên bản và loại collection** đang dùng trước khi triển khai các tham số ít phổ biến.

## 10. Trình tự thay đổi tùy chọn trên môi trường thật

Với một thay đổi metadata có thể ảnh hưởng dữ liệu hoặc hiệu năng, hãy thực hiện theo một quy trình có thể quan sát và khôi phục:

1. **Xác nhận database, tên collection và loại đối tượng.** Dùng `db.getName()`, `db.getCollectionInfos({name:"..."})`. Phân biệt collection thường, time series, capped và view.
2. **Xác định phiên bản server và quyền.** `collMod` cần quyền tương ứng trên namespace mục tiêu. Nếu dùng tài khoản hạn chế, lỗi `Unauthorized` cần được giải quyết theo cơ chế phân quyền thay vì tắt bảo mật.
3. **Ghi lại cấu hình trước thay đổi.** Lưu kết quả `getCollectionInfos()` và `getIndexes()` vào biên bản triển khai phù hợp, đồng thời bảo vệ các thông tin nội bộ. Đối với thay đổi có rủi ro xóa dữ liệu như TTL, cần kế hoạch sao lưu/phục hồi dữ liệu.
4. **Đánh giá ảnh hưởng.** Validator mới có chặn hoạt động ghi hiện tại? TTL mới có khiến hàng loạt document đủ điều kiện xóa? Ẩn index có làm truy vấn chậm đi? View mới có thay đổi cấu trúc kết quả mà ứng dụng đang dùng?
5. **Thử trên môi trường tương đương.** Sử dụng tập dữ liệu đại diện, kiểm tra đường ghi/đọc liên quan. Khi sửa validator, thử giá trị đúng/sai kiểu và document cũ. Khi sửa index, quan sát kế hoạch truy vấn và hiệu năng.
6. **Chạy `collMod` trong cửa sổ thay đổi phù hợp.** Giữ payload gọn, chỉ chứa những tùy chọn đã quyết định sửa. Thực hiện qua kênh có ghi nhận người thao tác và kết quả.
7. **Đọc lại metadata và hành vi.** Xác nhận option đã được áp dụng, kết hợp kiểm tra truy vấn/ghi có liên quan. `ok: 1` chỉ nói command thành công, không khẳng định tác động nghiệp vụ đã đúng.
8. **Theo dõi và chuẩn bị phương án quay lại.** Với validator hoặc hidden index, có thể gửi một `collMod` khác để khôi phục tùy chọn cũ nếu còn hỗ trợ. Dữ liệu đã bị xóa vì TTL không thể khôi phục chỉ bằng cách tăng `expireAfterSeconds` trở lại.

### Mẫu thao tác có xác nhận kết quả trong `mongosh`

```javascript
const targetDB = db.getSiblingDB("mongo_lab");
const name = "registrations";

const metadataBefore = targetDB.getCollectionInfos({ name });
if (metadataBefore.length !== 1 || metadataBefore[0].type !== "collection") {
  throw new Error("Không tìm thấy collection mục tiêu");
}

print("Trước thay đổi:");
printjson(metadataBefore[0].options);

const result = targetDB.runCommand({
  collMod: name,
  validationAction: "warn"
});

if (result.ok !== 1) {
  throw new Error("collMod thất bại: " + tojson(result));
}

print("Sau thay đổi:");
printjson(targetDB.getCollectionInfos({ name })[0].options);
```

Mẫu này cố ý đọc metadata trước và sau để người học nhìn thấy trạng thái của collection. Trong công cụ triển khai tự động, nên bổ sung điều kiện kiểm tra option cụ thể, ghi log an toàn và xử lý lỗi phù hợp.

## 11. Lỗi thường gặp khi dùng `collMod`

| Tình huống | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `NamespaceNotFound` hoặc không tìm thấy collection | Sai database, sai tên hoặc collection chưa được tạo | Xác minh `db.getName()` và `getCollectionInfos()` |
| `Unauthorized` | Tài khoản thiếu quyền `collMod` trên namespace | Dùng vai trò/quyền được quản trị viên cấp đúng phạm vi |
| Tùy chọn không được chấp nhận | MongoDB version không hỗ trợ, sai loại collection hoặc cú pháp sai | Đọc tài liệu lệnh `collMod` của đúng phiên bản và kiểm tra type |
| Lỗi về `index` | Tên index sai, loại index không phù hợp, option không được phép | Xem `getIndexes()`, xác nhận index đã tồn tại và được hỗ trợ |
| Document cũ vẫn không hợp lệ | Thay validator không tự sửa dữ liệu đã ghi | Lập kế hoạch migration dữ liệu riêng |
| Ghi dữ liệu thất bại sau khi nâng validation | `strict` + `error` chặn các thao tác vi phạm | Đọc chi tiết lỗi validation, sửa dữ liệu đầu vào hoặc quy tắc nếu yêu cầu nghiệp vụ thay đổi |
| Dữ liệu bị xóa sau khi giảm TTL | Nhiều document đã quá ngưỡng mới | Khôi phục từ sao lưu nếu cần; tăng TTL trở lại chỉ ảnh hưởng những document còn tồn tại |
| Truy vấn chậm sau khi ẩn index | Query planner không còn sử dụng index đó | So sánh kế hoạch truy vấn, cân nhắc `hidden: false` |
| Ứng dụng lỗi sau khi đổi view | Pipeline/projection mới không còn trả field mà ứng dụng mong đợi | Khôi phục định nghĩa view tương thích hoặc cập nhật hợp đồng phía ứng dụng |

Đặc biệt, **collection options và dữ liệu trong collection là hai lớp khác nhau**. Một lệnh `collMod` thành công không bảo đảm mọi document cũ đã đạt schema, dữ liệu bị TTL xóa có thể phục hồi, hay chương trình dùng view/index vẫn hoạt động như trước.

## 12. Bài tập thực hành

### Bài 1: chuyển validator từ ghi cảnh báo sang từ chối

Collection `registrations` đã có validator yêu cầu `active` là boolean và đang dùng `validationAction: "warn"`. Hãy viết lệnh để từ chối các thao tác ghi không đạt validator.

**Lời giải:**

```javascript
db.runCommand({
  collMod: "registrations",
  validationLevel: "strict",
  validationAction: "error"
})
```

Thử insert `{studentId:"u200", courseCode:"MDB101", active:"false"}` trên môi trường lab để thấy lỗi. Thay `"false"` bằng boolean `false` thì dữ liệu phù hợp về kiểu.

### Bài 2: thay đổi TTL mà không tạo lại index

Collection `sessionEvents` có TTL index tên `createdAt_ttl`, hiện giữ dữ liệu 7 ngày. Hãy đổi sang 30 ngày.

**Lời giải:**

```javascript
db.runCommand({
  collMod: "sessionEvents",
  index: {
    name: "createdAt_ttl",
    expireAfterSeconds: 2592000
  }
})
```

Đọc lại `db.sessionEvents.getIndexes()` và xác nhận `expireAfterSeconds` đã bằng `2592000`. Đổi thời hạn không làm các document từng bị TTL xóa quay trở lại.

### Bài 3: ẩn một index để đánh giá kế hoạch truy vấn

Collection `registrations` có index `courseCode_1`. Hãy ẩn index, sau đó hiện lại.

**Lời giải:**

```javascript
db.runCommand({
  collMod: "registrations",
  index: { name: "courseCode_1", hidden: true }
})

db.runCommand({
  collMod: "registrations",
  index: { name: "courseCode_1", hidden: false }
})
```

Trong hệ thống thật, nên quan sát truy vấn và tải hệ thống giữa hai thời điểm thay vì chạy hai lệnh liên tiếp ngay lập tức.

### Bài 4: xác định khi nào `collMod` không phù hợp

Một nhóm muốn (a) thêm trường bắt buộc vào validator; (b) đổi tên `registrations` thành `enrollments`; (c) chuyển collection thường thành capped; (d) sửa pipeline view.

**Lời giải:**

- (a) Có thể chỉnh validator bằng `collMod`, đồng thời xem xét dữ liệu cũ.
- (b) Dùng thao tác đổi tên collection, không dùng `collMod`.
- (c) Không coi đây là thuộc tính có thể chuyển tùy ý bằng `collMod`; phải thiết kế lại theo quy trình phù hợp.
- (d) Có thể dùng `collMod` đối với view nếu thỏa điều kiện của MongoDB.

## Kết luận

`collMod` là công cụ thay đổi **metadata được hỗ trợ** của collection hoặc view đang tồn tại. Các trường hợp thực hành quan trọng nhất là chỉnh **document validator**, đổi **`validationLevel`/`validationAction`**, sửa tùy chọn **TTL index**, **ẩn/hiện index** và cập nhật **pipeline view**. Từng nhóm đều có giới hạn riêng theo phiên bản và loại đối tượng.

Trước mỗi lần dùng `collMod`, hãy đọc trạng thái hiện tại, chỉ rõ tùy chọn muốn đổi, dự đoán ảnh hưởng đến dữ liệu và ứng dụng, rồi kiểm tra lại metadata cùng hành vi sau khi lệnh hoàn tất. Nhờ đó, ta thay đổi cấu hình collection có kiểm soát mà không nhầm lẫn với cập nhật document hoặc các thao tác tái cấu trúc database.

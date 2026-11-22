# Cập nhật validator, triển khai tương thích và giới hạn bypassDocumentValidation

MongoDB cho phép các document trong một collection có cấu trúc khác nhau. Tuy nhiên, hệ thống production vẫn cần hợp đồng dữ liệu: field nào bắt buộc, kiểu BSON nào hợp lệ, giá trị nào được chấp nhận, và khi hợp đồng thay đổi thì phải xử lý dữ liệu cũ ra sao. **Schema validation** giúp MongoDB thực thi những quy tắc đó tại thời điểm ghi. Thay đổi validator vì thế là một **thay đổi tương thích dữ liệu** cần triển khai có kiểm soát, không chỉ là chạy một command quản trị.

Bài học này thuộc chương **Schema validation**, tập trung vào ba vấn đề liên quan: **cập nhật validator bằng `collMod`**, **triển khai phù hợp với các phiên bản ứng dụng và document cũ**, và **giới hạn của `bypassDocumentValidation`**. Ví dụ dùng `mongosh` trên database thực hành `schema_lab`.

Sau bài học, bạn có thể:

1. Đọc và sửa `validator`, `validationLevel`, `validationAction` của collection.
2. Giải thích sự khác nhau giữa `strict`, `moderate`, `off` và mức `constraint` của MongoDB 9.0.
3. Triển khai schema theo các pha **expand → observe → migrate → enforce → clean up**.
4. Tìm document không đạt schema bằng `$jsonSchema` kết hợp `$nor`.
5. Phân biệt `bypassDocumentValidation` với thay đổi validator, tắt validation và bỏ qua những ràng buộc khác.
6. Nhận diện nguy cơ khi rollback ứng dụng, nâng phiên bản server, import dữ liệu và nâng mức enforcement.

> **Phiên bản:** Các ví dụ phổ biến dưới đây áp dụng cho MongoDB 7.0/8.0. `validationAction: "errorAndLog"` được bổ sung ở MongoDB **8.1**; `validationLevel: "constraint"` và `prepareConstraintValidationLevel` có từ MongoDB **9.0**. Với production, hãy đối chiếu chính xác MongoDB Server version, FCV và nhánh tài liệu trước khi sử dụng.

## 1. Schema validation trong kiến trúc MongoDB

Một **collection validator** là biểu thức logic dùng để kiểm tra document khi insert/update trong phạm vi được chỉ định. Thường gặp nhất là `$jsonSchema`, nhưng MongoDB cũng hỗ trợ những query expressions phù hợp.

~~~text
Client / Java Driver / mongosh
             |
             v
MongoDB Server nhận write command
             |
             +-- kiểm tra quyền và cú pháp lệnh
             +-- chọn phạm vi validation theo validationLevel
             +-- kiểm tra document theo validator
             |        |
             |        +-- hợp lệ -> tiếp tục ghi
             |        +-- không hợp lệ, action=error -> từ chối
             |        +-- không hợp lệ, action=warn -> ghi và log cảnh báo
             |
             +-- các ràng buộc khác: unique index, giới hạn BSON...
             v
      Storage engine lưu dữ liệu
~~~

Đây là **rào chắn tại lúc ghi**, không phải công cụ tự động chuyển đổi dữ liệu cũ. `collMod` sửa validator không tự tìm và chỉnh tất cả document đang lưu. Nếu collection có dữ liệu cũ không đạt quy tắc mới, tác động lên document đó còn phụ thuộc `validationLevel`.

### 1.1. Validator kiểm tra được những gì?

| Quy tắc | Ví dụ |
|---|---|
| Field bắt buộc | `required: ["name", "email"]` |
| Kiểu BSON | `bsonType: "string"`, `bsonType: "date"` |
| Nhiều kiểu hợp lệ | `bsonType: ["int", "long"]` |
| Giá trị giới hạn | `enum: ["ACTIVE", "DISABLED"]` |
| Số tối thiểu/tối đa | `minimum: 0`, `maximum: 100` |
| Độ dài chuỗi | `minLength: 3` |
| Mẫu chuỗi | `pattern: "^..."` |
| Object lồng | `properties.address.properties.city` |
| Mảng | `items`, `minItems`, `maxItems` |
| Điều kiện logic | Các query operators được validator hỗ trợ. |

Ví dụ rule cho một user:

~~~javascript
const userSchemaV1 = {
  $jsonSchema: {
    bsonType: "object",
    required: ["name", "status"],
    properties: {
      name: {
        bsonType: "string",
        minLength: 1,
        description: "name must be a non-empty string"
      },
      status: {
        enum: ["ACTIVE", "DISABLED"]
      },
      email: {
        bsonType: "string",
        description: "email must be a string if present"
      }
    }
  }
}
~~~

Ở đây `name` và `status` bắt buộc, còn `email` **không bắt buộc** nhưng nếu có phải là chuỗi. Sự phân biệt giữa field thiếu và field `email: null` rất quan trọng: `null` là một giá trị BSON, không phải chuỗi, nên sẽ không thỏa `bsonType: "string"`. Nếu muốn cho phép null, phải định nghĩa tường minh, chẳng hạn `bsonType: ["string", "null"]`.

### 1.2. Điều validator không tự bảo đảm

- **Tính duy nhất trên toàn collection:** muốn email duy nhất, dùng **unique index**; `required` không thay thế unique index.
- **Khóa ngoại:** lưu `customerId` không tự xác nhận có document customer tương ứng.
- **Transaction nhiều document:** schema validation không làm cho hai collection được update nguyên tử cùng nhau.
- **Quyền truy cập:** validator không thay thế authorization.
- **Toàn bộ nghiệp vụ:** điều kiện liên quan đến thanh toán, các dịch vụ ngoài hay luồng trạng thái phức tạp vẫn cần xử lý ở tầng phù hợp.
- **Dữ liệu cũ:** thay rule không tự backfill hoặc tự xác nhận mọi document hiện tại hợp lệ.

Ngay cả khi một thao tác được phép **bypass**, các ràng buộc độc lập như unique index và quyền ghi vẫn có hiệu lực.

## 2. Bộ ba `validator`, `validationLevel`, `validationAction`

Hãy xem cấu hình như ba câu hỏi:

~~~javascript
{
  validator: { /* document hợp lệ khi nào? */ },
  validationLevel: "strict",      // kiểm tra những thao tác nào?
  validationAction: "error"       // vi phạm thì xử lý ra sao?
}
~~~

### 2.1. Ý nghĩa của validationLevel

| Level | Insert mới | Update document đang hợp lệ | Update document đang không hợp lệ |
|---|---|---|---|
| **`strict`** | Kiểm tra | Kiểm tra | Kiểm tra |
| **`moderate`** | Kiểm tra | Kiểm tra | Không bắt buộc qua validation |
| **`off`** | Không kiểm tra | Không kiểm tra | Không kiểm tra |
| **`constraint`** (9.0+) | Kiểm tra | Kiểm tra | Không cho phép collection tồn tại document sai schema sau khi nâng mức thành công |

**`strict`** là mặc định. Khi update một legacy document vốn vi phạm rule mới, MongoDB sẽ kiểm tra **trạng thái document sau update**. Một lệnh chỉ sửa `lastSeenAt` vẫn có thể bị từ chối nếu document tiếp tục thiếu field bắt buộc.

**`moderate`** áp dụng validation lên insert và update của các document **vốn đã hợp schema**. Document **vốn không hợp schema** có thể tiếp tục được sửa mà không phải vượt qua validation. Mục đích là giúp hệ thống tiếp tục hoạt động với dữ liệu cũ trong giai đoạn chuyển đổi; nó không tự sửa dữ liệu, cũng không bảo đảm dữ liệu invalid cuối cùng sẽ biến mất.

**`off`** tắt việc kiểm tra schema đối với inserts/updates; biểu thức validator có thể vẫn được lưu trong metadata. Đây là một chế độ điều khiển cả collection, không giống bypass riêng một operation.

**`constraint`** xuất hiện từ MongoDB **9.0** với invariant mạnh hơn: khi nâng mức, MongoDB kiểm tra mọi document trong collection và không cho phép dùng `bypassDocumentValidation`. Phần 9 giải thích quy trình và những hạn chế của mức này.

### 2.2. Ý nghĩa của validationAction

| Action | Kết quả nếu một thao tác thuộc phạm vi validation tạo document invalid | Ghi chú phiên bản |
|---|---|---|
| **`error`** | Từ chối write. | Mặc định và phổ biến. |
| **`warn`** | Cho phép write, ghi warning vào MongoDB log. | Phù hợp giai đoạn quan sát. |
| **`errorAndLog`** | Từ chối write **và** ghi log lỗi. | Có từ MongoDB 8.1. |

`validationLevel` quyết định **có kiểm tra hay không**; `validationAction` quyết định **xử lý như thế nào nếu không đạt**. Chẳng hạn `moderate + warn` không có nghĩa mỗi update lên document invalid đều sinh warning, vì update trên document đã invalid có thể nằm ngoài phạm vi cần kiểm tra.

### 2.3. So sánh một số tổ hợp

| Tổ hợp | Hệ quả thực tế |
|---|---|
| **strict + error** | Chặn invalid inserts/updates mới; document cũ invalid vẫn có thể tồn tại cho tới khi được sửa. |
| **strict + warn** | Log những vi phạm khi ghi, nhưng vẫn cho phép dữ liệu invalid tiếp tục đi vào collection. |
| **moderate + error** | Insert và update của document đang hợp lệ bị kiểm tra; legacy document invalid vẫn có thể được cập nhật. |
| **moderate + warn** | Cảnh báo chỉ trên phạm vi được kiểm tra; thiếu cảnh báo không chứng minh dữ liệu sạch. |
| **off + error** | Không kiểm tra schema, dù action còn là error. |
| **constraint + error** (9.0+) | Collection được kiểm tra toàn bộ khi nâng mức; bypass bị chặn. |

### 2.4. Ví dụ rule mới khiến document cũ invalid

Ban đầu hệ thống cho phép:

~~~javascript
{ _id: "U1", name: "An", email: "an@example.test" }
{ _id: "U2", name: "Bình" }
~~~

Nếu rule mới yêu cầu `email`, document `U2` **không tự biến mất** khi chạy `collMod`. Với `strict + error`, một update như sau có thể thất bại vì kết quả vẫn không có email:

~~~javascript
db.getSiblingDB("schema_lab").users.updateOne(
  { _id: "U2" },
  { $set: { lastSeenAt: new Date() } }
)
~~~

Với `moderate + error`, document `U2` vốn invalid có thể được update mà chưa sửa email. Mặt trái là phần dữ liệu sai vẫn có thể tồn tại kéo dài.

## 3. Xem cấu hình hiện tại trước khi sửa

Sử dụng `getCollectionInfos` để đọc collection options:

~~~javascript
const lab = db.getSiblingDB("schema_lab")
const infoList = lab.getCollectionInfos({ name: "users" })

if (infoList.length === 0) {
  print("Collection users chưa tồn tại")
} else {
  printjson(infoList[0].options)
}
~~~

Hoặc bằng database command:

~~~javascript
lab.runCommand({
  listCollections: 1,
  filter: { name: "users" }
})
~~~

Kết quả có thể chứa `options.validator`, `options.validationLevel` và `options.validationAction`. Những option đang ở giá trị mặc định đôi khi **không hiển thị tường minh**; khi đọc lại cần đối chiếu mặc định của server version. Lưu cấu hình cũ trước mỗi rollout để có khả năng rollback.

### 3.1. Tạo collection thực hành với validator ban đầu

Chạy các lệnh sau trong một **database thử nghiệm chưa có collection users**:

~~~javascript
const lab = db.getSiblingDB("schema_lab")

const oldValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: ["name"],
    properties: {
      name: { bsonType: "string", minLength: 1 }
    }
  }
}

lab.createCollection("users", {
  validator: oldValidator,
  validationLevel: "strict",
  validationAction: "error"
})

lab.users.insertMany([
  { _id: "U1", name: "An", email: "an@example.test" },
  { _id: "U2", name: "Bình" },
  { _id: "U3", name: "Chi", email: 123 }
])
~~~

Ba document đều hợp schema **cũ**, vì chỉ có `name` bị ràng buộc. Với schema **mới** yêu cầu `email` là string, `U2` thiếu email và `U3` có email sai kiểu.

## 4. Thay validator bằng `collMod`

Đối với collection **đã tồn tại**, dùng `collMod`:

~~~javascript
const lab = db.getSiblingDB("schema_lab")

const nextValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: ["name", "email"],
    properties: {
      name: { bsonType: "string", minLength: 1 },
      email: { bsonType: "string" }
    }
  }
}

lab.runCommand({
  collMod: "users",
  validator: nextValidator,
  validationLevel: "strict",
  validationAction: "warn"
})
~~~

Lệnh đặt một **biểu thức validator đầy đủ** và chuyển sang chế độ cảnh báo để quan sát. `collMod` trả kết quả có `ok: 1` nếu thành công; hãy **readback** metadata bằng `getCollectionInfos`.

### 4.1. `collMod` không migrate dữ liệu cũ

Ngay sau command, `U2` và `U3` vẫn tồn tại với giá trị cũ. Ở các mức `strict` và `moderate`, MongoDB không tự quét rồi sửa document cũ. Thay đổi ảnh hưởng đến **các lần insert/update sau đó**.

Ví dụ cùng một write làm document invalid:

- `strict + warn`: operation có thể ghi thành công và log warning.
- `strict + error`: operation bị từ chối.
- `moderate + error`: behavior khác nhau tùy document trước update có đạt rule hay không.

### 4.2. Đổi action/level mà giữ nguyên validator

Nếu muốn đổi sang từ chối invalid writes sau khi đã dọn dữ liệu:

~~~javascript
lab.runCommand({
  collMod: "users",
  validationLevel: "strict",
  validationAction: "error"
})
~~~

Chỉ những option chỉ định được thay đổi. Ngược lại, khi gửi `validator` mới, hãy xem đó là **thay thế biểu thức validator**, không mặc định MongoDB sẽ merge sâu các `properties` hay `required` từ rule cũ. Vì vậy nên quản lý **toàn bộ schema canonical** theo version trong repository, tránh làm mất các rule trước do vô ý.

### 4.3. Đọc lại cấu hình

~~~javascript
const options = lab.getCollectionInfos({ name: "users" })[0].options

printjson({
  validator: options.validator,
  validationLevel: options.validationLevel,
  validationAction: options.validationAction
})
~~~

Readback này chứng minh collection options đã thay đổi, **không** chứng minh mọi document đang lưu thỏa schema mới.

### 4.4. Quyền và tác động vận hành

`collMod` đòi hỏi privilege `collMod` phù hợp; built-in role `dbAdmin` có quyền cần thiết để sửa collection thông thường. Theo MongoDB Manual, command này lấy **collection lock** trong thời gian thực thi. Cần xem tải và chọn thời điểm thay đổi thích hợp, đặc biệt trong hệ thống có traffic và các thao tác DDL khác.

Không thể đặt validator trên các collection ở database `admin`, `local`, `config` hoặc các collection `system.*` theo các giới hạn được tài liệu nêu. Một số collection chuyên biệt có quy tắc riêng; đừng sao chép command sang namespace khác mà chưa kiểm tra.

## 5. Tìm các document đang vi phạm schema mới

MongoDB cho phép sử dụng biểu thức `$jsonSchema` trong query để phân loại document mà không cần thay validator trước:

~~~javascript
const lab = db.getSiblingDB("schema_lab")
const nextValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: ["name", "email"],
    properties: {
      name: { bsonType: "string", minLength: 1 },
      email: { bsonType: "string" }
    }
  }
}

// Các document hợp schema:
lab.users.find(nextValidator)

// Các document KHÔNG hợp schema:
lab.users.find({ $nor: [nextValidator] })

// Đếm document invalid:
lab.users.countDocuments({ $nor: [nextValidator] })
~~~

Trong dữ liệu mẫu, truy vấn invalid tìm được `U2` và `U3`. `$nor` phủ định điều kiện full schema. Đây là công cụ quan trọng để lập kế hoạch **backfill** và đo kết quả trước/sau migration.

Một số truy vấn chẩn đoán theo field:

~~~javascript
const missingEmail = lab.users.countDocuments({
  email: { $exists: false }
})

const emailNotString = lab.users.countDocuments({
  email: { $exists: true, $not: { $type: "string" } }
})

printjson({ missingEmail, emailNotString })
~~~

Hai con số trên chỉ phân loại một số nguyên nhân. Nếu schema còn ràng buộc regex, nested object, enum, độ dài..., hãy dùng **full `$jsonSchema`** để xác định tập invalid. Với collection lớn, scan có thể tốn I/O/CPU; đo trên môi trường tương đương, dùng sampling/batching và tránh kéo toàn bộ document về client chỉ để đếm.

### 5.1. Khác nhau giữa kiểm tra dữ liệu và thay đổi hợp đồng

| Thao tác | Sửa validator? | Sửa document? | Mục đích |
|---|---:|---:|---|
| `find({$nor:[schema]})` | Không | Không | Tìm dữ liệu không đạt rule. |
| `countDocuments({$nor:[schema]})` | Không | Không | Đo quy mô phải sửa. |
| `collMod` với `validator` | Có | Không | Thay hợp đồng lúc ghi. |
| `updateOne`/backfill | Không | Có | Sửa document hiện có. |
| `collMod` với `validationAction` | Có | Không | Đổi cách xử lý write invalid. |

Nếu `collMod` trả `ok: 1`, bạn mới xác minh được **metadata thay đổi**. Không được báo “tất cả dữ liệu đã được migrate” nếu chưa thực hiện và đối soát data migration.

## 6. Triển khai tương thích: expand → observe → migrate → enforce

Giả sử môi trường production có nhiều instance ứng dụng cùng ghi collection `users`:

- **App v1** chỉ yêu cầu `name`; `email` có thể vắng mặt.
- **App v2** sẽ yêu cầu `email` bắt buộc và là chuỗi.
- Database đã có document `U2` thiếu email và `U3` dùng kiểu số.
- Khi rolling deployment, trong một khoảng thời gian **v1 và v2 cùng chạy**.

Bật ngay `strict + error` cho validator mới có thể khiến request từ App v1 thất bại và khiến update trên các document legacy bị từ chối. Vì vậy cần có chuỗi chuyển đổi hợp đồng.

### 6.1. Pha 0 — Kiểm kê và định nghĩa bất biến

Trước khi ghi collection options:

1. Xác định **schema đích**, phần thay đổi nào nới lỏng và phần nào siết chặt.
2. Liệt kê **tất cả writers**: web app, cron job, batch import, ETL, data sync, admin tools, ứng dụng đời cũ.
3. Ghi **MongoDB Server version, FCV, driver versions** và topology để tra cứu đúng tài liệu.
4. Đếm invalid documents theo rule mới, phân loại missing/type/value mismatch.
5. Xác định nguồn dữ liệu nào đáng tin để backfill. **Không bịa giá trị** chỉ để qua validation.
6. Định nghĩa cổng chuyển pha: số invalid, tỷ lệ invalid writes, mức tương thích của writers, latency và error rate.
7. Lưu cấu hình validator trước đó, kế hoạch rollback ứng dụng và migration data.

Nếu nghiệp vụ cho phép user **chưa hoàn tất onboarding** thiếu email, quy tắc “mọi user luôn phải có email” có thể sai. Khi đó nên thiết kế schema có điều kiện dựa trên trạng thái user thay vì ép nhập email giả.

### 6.2. Pha 1 — Expand ứng dụng để chịu được cả dữ liệu cũ và mới

Triển khai phiên bản ứng dụng có thể:

- **Đọc dữ liệu legacy** với `email` thiếu hoặc sai kiểu mà không crash; xử lý/đánh dấu bản ghi cần bổ sung.
- **Ghi dữ liệu mới** theo schema đích; không phụ thuộc server chặn mới sửa.
- Có đường cập nhật document legacy theo chính sách nghiệp vụ phù hợp.
- Tương thích trong khoảng thời gian **v1 và v2 cùng hoạt động**.
- Cập nhật cả các producers ít được chú ý: async consumer, import tool, scheduled jobs, data maintenance.

Nếu chỉ kiểm tra endpoint `POST /users` mà bỏ qua `PUT/PATCH`, `replaceOne` hoặc job `bulkWrite` thì sau khi enforce vẫn có thể gặp lỗi không lường trước. Không bật rule chặt ngay khi một instance v2 lên; hãy chắc chắn **toàn bộ writers** cần thiết đã tương thích.

### 6.3. Pha 2 — Cài schema đích ở `strict + warn`

Trên môi trường phù hợp, triển khai:

~~~javascript
const lab = db.getSiblingDB("schema_lab")

const nextValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: ["name", "email"],
    properties: {
      name: { bsonType: "string", minLength: 1 },
      email: { bsonType: "string" }
    }
  }
}

lab.runCommand({
  collMod: "users",
  validator: nextValidator,
  validationLevel: "strict",
  validationAction: "warn"
})
~~~

Vì action là `warn`, document invalid **vẫn có thể được chèn/cập nhật**. MongoDB ghi warning cho các thao tác vi phạm trong phạm vi validation. Đây là một giai đoạn **quan sát tương thích**, không phải enforcement.

Theo dõi warning theo **namespace**, thời gian và phiên bản ứng dụng nếu có instrumentation. Log có thể chứa chi tiết document/field nhạy cảm, nên cần chính sách giới hạn truy cập và redaction. Dùng `$nor: [nextValidator]` để đếm invalid thực tế; **không dựa riêng vào số warning**.

Điều kiện chuyển pha cần phản ánh workload thật. Ví dụ một job chỉ chạy cuối tuần chưa được kiểm tra nếu chỉ quan sát 30 phút traffic buổi sáng.

### 6.4. Pha 3 — Migrate/backfill dữ liệu cũ

Sau khi có nguồn dữ liệu đáng tin, sửa document cũ **theo từng lô**. Ví dụ trong database lab, giả sử email của U2 và U3 đã được chủ dữ liệu xác minh:

~~~javascript
const lab = db.getSiblingDB("schema_lab")

lab.users.updateOne(
  { _id: "U2", email: { $exists: false } },
  { $set: { email: "binh@example.test" } }
)

lab.users.updateOne(
  { _id: "U3", email: 123 },
  { $set: { email: "chi@example.test" } }
)

const remaining = lab.users.countDocuments({
  $nor: [nextValidator]
})
print("Remaining invalid documents: " + remaining)
~~~

**Đây là dữ liệu minh họa, không phải hướng dẫn sinh email mặc định.** Trong dữ liệu thật, nếu chưa biết email đúng thì cần quy trình thu thập/chấp thuận bổ sung, hoặc schema thể hiện rõ trạng thái chưa có email.

Với nhiều triệu bản ghi, áp dụng:

- **Batching/checkpoint** theo `_id` hoặc khoảng khóa có tính xác định.
- Điều kiện filter bảo vệ dữ liệu vừa được client khác sửa.
- Backfill **idempotent**, có thể chạy lại sau lỗi mà không gây thay đổi không mong muốn.
- Đo tốc độ đọc/ghi, replication lag, tải storage và số write conflicts.
- Lưu số lượng đã xử lý/thất bại, nhóm cần can thiệp thủ công.
- Không dựa vào `updateMany` như một transaction nguyên tử trên toàn collection.

Không quên dữ liệu nằm trong nested objects/arrays: thay đổi schema con có thể khiến nhiều document lớn không hợp lệ và khó backfill bằng một lệnh `$set` đơn giản.

### 6.5. Pha 4 — Enforce với `strict + error`

Khi tất cả writers đã tương thích và invalid documents được xử lý:

~~~javascript
const lab = db.getSiblingDB("schema_lab")
const invalidCount = lab.users.countDocuments({
  $nor: [nextValidator]
})

if (invalidCount > 0) {
  throw new Error("Still invalid: " + invalidCount)
}

lab.runCommand({
  collMod: "users",
  validationLevel: "strict",
  validationAction: "error"
})
~~~

Cần hiểu giới hạn của phép đếm: nếu một producer cũ vẫn có thể ghi dưới `warn` **giữa lúc đếm và lúc enforce**, dữ liệu invalid mới có thể xuất hiện. Vì vậy cổng chuyển pha không chỉ là một con số bằng 0: phải kiểm soát writers, kiểm tra thời gian rollout và thực hiện thay đổi có kế hoạch.

Sau khi enforce, invalid writes mới trong phạm vi schema validation bị từ chối. Tuy nhiên, `strict + error` **không mang ý nghĩa server đã scan và chứng nhận toàn bộ dữ liệu tồn tại**; việc kiểm tra invalid trước đó là trách nhiệm triển khai. Từ MongoDB 9.0 có mức `constraint` cho invariant mạnh hơn.

### 6.6. Pha 5 — Theo dõi và bỏ hỗ trợ legacy khi đã đủ điều kiện

Sau rollout:

- Theo dõi lỗi `DocumentValidationFailure` theo endpoint/job/app version.
- Theo dõi số document không hợp rule, cảnh báo log còn tồn, tác vụ không tương thích.
- Giữ đường rollback validator và ứng dụng trong cửa sổ theo dõi.
- Chỉ loại bỏ code đọc legacy khi đã xác nhận không còn dữ liệu cần hỗ trợ.
- Lưu **schema version**, ngày triển khai và migration reference cho người vận hành sau.

Trong môi trường nhiều service, **rollback app** cần được kiểm tra tương thích với **schema mới**. Không tự quay về writer v1 đã từng tạo user thiếu email khi `strict + error` vẫn đang bật.

## 7. `moderate` như một chiến lược chuyển tiếp khác

Nếu số lượng legacy invalid rất lớn nhưng cần bắt đầu chặn invalid inserts mới, `moderate + error` là lựa chọn có thể cân nhắc:

~~~javascript
db.getSiblingDB("schema_lab").runCommand({
  collMod: "users",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["name", "email"],
      properties: {
        name: { bsonType: "string" },
        email: { bsonType: "string" }
      }
    }
  },
  validationLevel: "moderate",
  validationAction: "error"
})
~~~

Khi đó:

1. **Insert** mới phải hợp rule.
2. Update lên document **đang hợp lệ** phải tạo document hợp rule.
3. Update lên document **đã invalid** có thể không phải qua validation.

Ví dụ `U2` thiếu email, một job chỉ muốn cập nhật `lastSeenAt` có thể tiếp tục làm việc. Tuy nhiên, `moderate` không đảm bảo nó sẽ sửa email trong tương lai; thậm chí những cập nhật khác lên document invalid có thể tạo thêm vi phạm.

### 7.1. Chọn `moderate` hay `strict + warn`?

| Mục tiêu | Phương án khởi đầu có thể phù hợp | Điều kiện đi kèm |
|---|---|---|
| Quan sát mọi write vi phạm schema mới | **strict + warn** | Chấp nhận write invalid, thu log và dọn dữ liệu. |
| Chặn invalid document mới, nhưng chưa sửa xong legacy | **moderate + error** | Có lịch backfill và đo invalid; không để thành trạng thái vĩnh viễn. |
| Tất cả writers và dữ liệu đã tương thích | **strict + error** | Đối soát dữ liệu và theo dõi lỗi sau deploy. |
| Tạm không áp rule trên inserts/updates | **off** | Chỉ khi có lý do và thời hạn rõ; rủi ro dữ liệu mới invalid. |
| Đảm bảo toàn collection sạch và chặn bypass, server 9.0+ | **constraint** | Quét/migrate dữ liệu, chuẩn bị và nâng mức riêng. |

Không nên chọn `moderate` chỉ vì nó khiến error count giảm: error count thấp không đồng nghĩa chất lượng dữ liệu đã cải thiện.

## 8. `bypassDocumentValidation`: ngoại lệ trên từng thao tác

`bypassDocumentValidation` là một option của những write commands được hỗ trợ. Khi bật trên một operation và user có quyền tương ứng, MongoDB có thể **bỏ qua collection schema validator** cho thao tác đó. Một mục đích chính đáng là phục hồi/nhập dữ liệu lịch sử chưa hợp schema hiện tại, đi cùng kế hoạch remediation.

Nó **không phải**:

- một thay đổi vĩnh viễn của collection;
- một cờ tự động áp dụng cho toàn session/application;
- cách làm mọi field trở nên hợp lệ;
- cách vượt qua unique index, giới hạn BSON, quyền ghi hoặc quy tắc command;
- giải pháp thay thế cho migration có kiểm soát.

### 8.1. Ví dụ bypass một insert

Giả sử collection có rule yêu cầu `name` và `email` là chuỗi với `strict + error`. Insert sau thông thường thất bại:

~~~javascript
const lab = db.getSiblingDB("schema_lab")

lab.users.insertOne({
  _id: "U-LEGACY",
  name: "Legacy User"
  // Thiếu email.
})
// Lỗi Document failed validation.
~~~

Một account **được cấp quyền bypass** có thể thực hiện command `insert` với option:

~~~javascript
lab.runCommand({
  insert: "users",
  documents: [
    {
      _id: "U-LEGACY",
      name: "Legacy User"
    }
  ],
  bypassDocumentValidation: true
})
~~~

Document invalid được chèn nếu command thỏa các điều kiện còn lại, quyền đầy đủ và collection **không ở trạng thái chặn bypass** như `constraint` MongoDB 9.0.

Bypass chỉ áp dụng cho **operation này**. Một lần update tương lai dưới `strict + error` phải tạo document hợp schema hoặc lại cần bypass. Nếu có email đúng đã xác minh, sửa document:

~~~javascript
lab.users.updateOne(
  { _id: "U-LEGACY", email: { $exists: false } },
  { $set: { email: "verified@example.test" } }
)
~~~

Vì trạng thái sau update có email string, lệnh sửa có thể được chấp nhận ngay cả khi trước đó document invalid. Trong production, giá trị email phải được xác minh; không được tự tạo địa chỉ giả để “qua rule”.

### 8.2. Các nhóm operation hỗ trợ option bypass

Theo tài liệu MongoDB Database Manual, có các nhóm:

| Nhóm | Command / phương thức được liệt kê |
|---|---|
| Chèn dữ liệu | `insert` command và API tương ứng hỗ trợ option. |
| Cập nhật dữ liệu | `update` command và API tương ứng. |
| Tìm và sửa | `findAndModify` command, `db.collection.findAndModify()`. |
| Aggregation ghi kết quả | `aggregate` có `$out` hoặc `$merge`. |
| Công cụ đặc biệt | `applyOps`, `mapReduce` ở phiên bản còn hỗ trợ. |

Một số driver và shell helper đặt option ở vị trí khác với cú pháp database command. Không được suy rằng **mọi hàm CRUD** đều nhận option giống nhau. Luôn đọc API của driver cùng phiên bản và Manual của server trước khi dùng.

Ví dụ `update` database command:

~~~javascript
lab.runCommand({
  update: "users",
  updates: [
    {
      q: { _id: "U-LEGACY" },
      u: { $set: { importBatch: "B-2026-11" } },
      multi: false
    }
  ],
  bypassDocumentValidation: true
})
~~~

Lệnh này sửa một field **không liên quan email** và cố ý bỏ qua validation. Nếu document còn invalid, việc thêm `importBatch` không làm nó hợp lệ. Mỗi bypass như vậy phải có mục đích, giới hạn thời gian và đường xử lý tồn đọng.

### 8.3. Quyền cần có

Khi bật authorization, account phải có **quyền ghi cần thiết** và action **`bypassDocumentValidation`** trên tài nguyên liên quan. MongoDB liệt kê built-in roles **`dbAdmin`** và **`restore`** có action bypass. Tuy nhiên, có action bypass **không đồng nghĩa** được thực hiện mọi loại ghi trên mọi collection: vẫn cần kiểm tra các quyền command khác.

Tài khoản ứng dụng chỉ cần đọc/ghi dữ liệu hợp lệ thường **không nên có privilege bypass**. Có thể sử dụng một tài khoản migration/restore được cấp đúng tài nguyên, ghi nhận mục đích, batch, người thực hiện và thu hồi quyền sau công việc. Không khắc phục lỗi validation bằng cách cấp role quá rộng như `root` cho toàn bộ ứng dụng.

### 8.4. Những ràng buộc bypass không thể vượt qua

| Ràng buộc | Bypass có bỏ qua? |
|---|---|
| Validator của collection (khi level hỗ trợ) | **Có**, cho đúng operation, có quyền phù hợp. |
| Unique index, duplicate key | **Không**. |
| Giới hạn BSON document 16 MiB | **Không**. |
| Quyền authentication/insert/update | **Không**. |
| Ràng buộc type của chính command/namespace | **Không**. |
| Logic validation do ứng dụng/driver thực hiện trước khi gọi server | Không nhất thiết. |
| Write concern, transaction, replication | **Không**. |
| Foreign key logic hay quy tắc nghiệp vụ | Không liên quan; phải xử lý riêng. |
| MongoDB 9.0 `constraint` / `prepareConstraintValidationLevel` | **Không thể bypass**, kể cả có privilege. |

Nếu collection có unique index trên `email`, việc đặt `bypassDocumentValidation: true` vẫn **không** cho phép tạo hai document có cùng email. Nếu không có quyền insert, có privilege bypass cũng **không đủ** để ghi.

### 8.5. Quy trình ngoại lệ có kiểm soát

Một ca restore/migration cần bypass nên ghi lại:

1. Collection và batch dữ liệu được phép bypass.
2. Lý do vì sao dữ liệu cần được giữ trước khi hợp schema.
3. Số document, các trường không hợp lệ và cách xử lý sau import.
4. Account/role sử dụng và thời hạn.
5. Scan bằng `$nor` trước và sau; danh sách tồn đọng có owner.
6. Khi nào tắt đường bypass và xác minh ứng dụng không còn sử dụng nó.

Nếu có thể, nên import vào **staging collection** trước, làm sạch rồi ghi vào collection đích. Đây thường là giải pháp minh bạch hơn so với cho phép ứng dụng production bypass mãi mãi.

## 9. Giới hạn bypass ở MongoDB 9.0: mức `constraint`

MongoDB 9.0 bổ sung `validationLevel: "constraint"` để cho phép **đảm bảo mạnh hơn trên toàn collection**. Khác với `strict`, mức này yêu cầu mọi document hiện có phải hợp validator tại thời điểm nâng lên; server thực hiện scan khi chuyển mức.

Theo MongoDB Manual 9.0:

1. `constraint` chỉ hoạt động với `validationAction: "error"` hoặc `"errorAndLog"`; `warn` không hợp lệ.
2. Khi level là `constraint`, **không được dùng `bypassDocumentValidation`**, kể cả user có quyền bypass.
3. Khi `prepareConstraintValidationLevel: true`, server cũng chặn những write đặt `bypassDocumentValidation: true`; đồng thời không cho sửa validator tùy ý.
4. Bypass bị chặn **ngay cả với document thực tế hợp lệ** nếu command chủ động mang `bypassDocumentValidation: true`.
5. Muốn sửa validator khi đang ở `constraint`, cần hạ về `strict`, cập nhật rule, rồi đi qua quá trình nâng `constraint` trở lại.
6. Khi nâng lên `constraint`, collection được kiểm tra toàn bộ; nếu có document vi phạm, command nâng mức sẽ thất bại.

Đây là một thay đổi quan trọng so với cách hiểu cũ rằng “hễ có privilege thì có thể bypass mọi validator”. Không được bỏ qua khác biệt phiên bản này trong runbook.

### 9.1. Quy trình minh họa nâng lên constraint

**Chỉ dùng trên MongoDB 9.0+** sau khi đọc tài liệu và xác minh server/FCV:

~~~javascript
const lab = db.getSiblingDB("schema_lab")

// Giả định đã cài validator đúng, đang strict + error,
// tất cả writers tương thích và toàn bộ dữ liệu hợp schema.

// Bước chuẩn bị: chặn bypass và sửa validator.
lab.runCommand({
  collMod: "users",
  prepareConstraintValidationLevel: true
})

// Bước nâng: MongoDB xác nhận tài liệu hiện có.
lab.runCommand({
  collMod: "users",
  validationLevel: "constraint",
  validationAction: "error"
})
~~~

Không đặt `validator` mới cùng command đang nâng sang `constraint`; hãy hoàn tất mọi thay đổi validator và backfill trước. Trên collection lớn, scan có thể tốn thời gian và ảnh hưởng tài nguyên, nên cần đánh giá cửa sổ vận hành, thời gian giữ lock, replication và kế hoạch phục hồi trước khi áp dụng.

Nếu quá trình nâng thất bại vì document invalid, phải phân tích và khắc phục các document đó theo schema. Không nên vội chuyển sang bypass bởi prepare/constraint được thiết kế để **khóa đường bypass**.

### 9.2. Khôi phục khả năng bypass khi thật sự cần

Trong MongoDB 9.0, tài liệu mô tả việc muốn cho phép bypass trở lại cần:

- Nếu collection đã ở `constraint`: đổi `validationLevel` trở lại `strict`.
- Nếu đang ở pha chuẩn bị `prepareConstraintValidationLevel: true`: hủy trạng thái prepare theo `collMod`.

Đó là thay đổi **chính sách collection** có hệ quả về đảm bảo dữ liệu, nên cần phê duyệt và ghi nhận giống mọi thay đổi validator khác. Không đặt lệnh hạ mức trong đường chạy tự động chỉ để một import đi qua.

### 9.3. Tương thích khi nâng/hạ phiên bản MongoDB

| Tính năng | Dòng phát hành cần nhớ |
|---|---|
| `strict`, `moderate`, `off` | Có ở các nhánh MongoDB trước 9.0, gồm 7.0/8.0. |
| `validationAction: "error"`, `"warn"` | Tùy chọn phổ biến trong các dòng trước 8.1. |
| `validationAction: "errorAndLog"` | Được giới thiệu ở **MongoDB 8.1**. |
| `validationLevel: "constraint"` | Được giới thiệu ở **MongoDB 9.0**. |
| `prepareConstraintValidationLevel` | Được giới thiệu ở **MongoDB 9.0**. |

Nếu collection sử dụng option chỉ được hỗ trợ trong bản mới, việc downgrade MongoDB Server có thể cần thay đổi option trước. Luôn đọc release notes và downgrade guide đúng phiên bản; **mongosh bản mới không bổ sung khả năng server bị thiếu**.

## 10. Lỗi validation và cách ứng dụng xử lý

### 10.1. DocumentValidationFailure khác lỗi xung đột ghi

Khi một write bị từ chối bởi `validationAction: "error"`, MongoDB thường trả lỗi **`DocumentValidationFailure`**, mã **121**. Tùy phiên bản, thông tin lỗi có thể có `failingDocumentId`, `details`, `schemaRulesNotSatisfied` và tên field/rule không đáp ứng.

~~~javascript
const lab = db.getSiblingDB("schema_lab")

try {
  lab.users.insertOne({
    _id: "U-BAD",
    name: "Mai"
    // Thiếu email.
  })
} catch (err) {
  print("code=" + err.code)
  print("codeName=" + err.codeName)
  print(err.message)
}
~~~

Đây là **lỗi hợp đồng dữ liệu**, khác với:

- **`DuplicateKey`** (thường mã 11000): vi phạm unique index.
- **Write conflict / transient transaction error**: tranh chấp đồng thời, có thể cần retry theo ngữ cảnh.
- **Network timeout**: chưa rõ server có nhận/hoàn thành thao tác hay không.
- **Write concern timeout**: yêu cầu xác nhận ghi chưa đạt trong thời hạn.
- **Unauthorized**: account thiếu quyền.

Không retry vô hạn một document vẫn thiếu email. Retry giúp ích với một số lỗi tạm thời, nhưng không khiến dữ liệu sai schema trở thành đúng. Ứng dụng phải sửa input hoặc xử lý nghiệp vụ theo rule.

### 10.2. Một batch có thể thành công một phần

Các lệnh `insertMany`/`bulkWrite` không mặc nhiên là transaction nguyên tử cho cả batch. Dưới `strict + error`, có thể có một số document hợp lệ được ghi trong khi một số khác bị từ chối. Hành vi phụ thuộc `ordered/unordered` và API driver.

~~~javascript
db.getSiblingDB("schema_lab").users.insertMany(
  [
    { _id: "U-OK-1", name: "Hà", email: "ha@example.test" },
    { _id: "U-NO-EMAIL", name: "Nam" },
    { _id: "U-OK-2", name: "Vy", email: "vy@example.test" }
  ],
  { ordered: false }
)
~~~

Với `ordered: false`, những phần tử hợp lệ có thể vẫn thành công dù document `U-NO-EMAIL` bị reject; driver có thể trả bulk error tổng hợp. Trong migration, cần đọc **kết quả từng phần** và retry idempotent theo identity, không gửi lại cả batch mà không kiểm tra dữ liệu đã ghi.

### 10.3. Quan sát sau rollout

Các chỉ số cần thu thập:

| Nguồn | Điều có thể biết | Giới hạn |
|---|---|---|
| MongoDB validation warning logs | Thao tác được kiểm tra nhưng tạo document invalid ở action `warn`. | Có thể chứa thông tin nhạy cảm; không phải ảnh chụp đầy đủ mọi legacy data. |
| Lỗi `DocumentValidationFailure` | Write bị chặn do rule trong action `error`. | Không thể suy ra toàn collection sạch chỉ vì không có lỗi. |
| `$nor: [schema]` scan | Document hiện tại không hợp schema được truy vấn. | Có thể tốn tài nguyên, cần đối soát theo thời gian. |
| `getCollectionInfos` | Validator/level/action đang cấu hình trên collection. | Chỉ là metadata, không kiểm tra dữ liệu. |
| Application metrics | Endpoint/job/client version phát sinh lỗi, ảnh hưởng người dùng. | Phải gắn correlation đúng, tránh chỉ log message string. |
| Bulk write result | Số document thành công/thất bại trong một batch. | Cần xét ordered/unordered, write concern và retries. |

**Không kết luận “không có warning nghĩa là không có invalid document”.** Legacy data có thể đã tồn tại; `moderate` có thể bỏ qua validation đối với update của document invalid; hoặc job gây lỗi không chạy trong khoảng giám sát.

### 10.4. Không phụ thuộc chuỗi error message

Hình dạng nội dung `errInfo`/`details` và văn bản mô tả lỗi có thể thay đổi theo MongoDB version. Code nên kiểm tra mã lỗi/kiểu exception phù hợp driver, dùng metadata khi có, và phản hồi thân thiện cho người dùng cuối mà không làm lộ chi tiết document hoặc schema nhạy cảm.

## 11. Các bẫy khi thay đổi JSON Schema

### 11.1. `required` và `properties` làm hai việc khác nhau

~~~javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["name"],
    properties: {
      name: { bsonType: "string" },
      email: { bsonType: "string" }
    }
  }
}
~~~

Document phải có `name`. `email` được phép vắng mặt, nhưng nếu có phải là string. Đưa email vào `required` là một **breaking change** đối với document và producer cũ.

### 11.2. Missing, null và sai kiểu

Giả sử rule vừa có `required: ["email"]` vừa có `email: { bsonType: "string" }`:

| Document | `required` | `bsonType: "string"` | Kết quả theo hai rule |
|---|---|---|---|
| `{}` | Không đạt | Không áp khi field thiếu | Invalid. |
| `{email: null}` | Đạt vì có field | Không đạt | Invalid. |
| `{email: 42}` | Đạt | Không đạt | Invalid. |
| `{email: "a@example.test"}` | Đạt | Đạt | Hợp hai rule này. |

Nếu muốn hỗ trợ null trong một pha chuyển tiếp, có thể dùng `bsonType: ["string", "null"]` rồi siết lại khi không còn document dùng null. Nhưng đây cũng cần rollout như mọi thay đổi kiểu dữ liệu khác.

### 11.3. Kiểu BSON khác kiểu trong JavaScript

`bsonType: "int"` chỉ nhận BSON Int32; `"long"` là Int64, `"double"` là số double, `"decimal"` là Decimal128. Shell/driver có thể ghi số thành kiểu BSON khác nhau. Với collection đã có nhiều kiểu số, đừng thay ngay sang một `bsonType` hẹp mà chưa đo dữ liệu hiện tại. Dùng `NumberInt`, `NumberLong` hoặc hỗ trợ nhiều kiểu theo nghiệp vụ:

~~~javascript
{
  $jsonSchema: {
    properties: {
      quantity: { bsonType: ["int", "long"] }
    }
  }
}
~~~

Đây chỉ là ví dụ một field; schema toàn phần còn phải quyết định `required` và các giá trị giới hạn. Không nhầm `bsonType` với `type` tiêu chuẩn JSON Schema: MongoDB có hệ kiểu BSON riêng.

### 11.4. `additionalProperties: false` dễ chặn `_id`

MongoDB document thường có `_id`. Nếu schema đặt `additionalProperties: false` mà không khai báo `_id` trong `properties`, document có `_id` sẽ bị xem là có field không cho phép.

Ví dụ rủi ro:

~~~javascript
{
  $jsonSchema: {
    bsonType: "object",
    additionalProperties: false,
    properties: {
      name: { bsonType: "string" }
    }
  }
}
~~~

Ví dụ điều chỉnh:

~~~javascript
{
  $jsonSchema: {
    bsonType: "object",
    additionalProperties: false,
    properties: {
      _id: { bsonType: ["objectId", "string"] },
      name: { bsonType: "string" }
    }
  }
}
~~~

Chỉ cho phép những kiểu `_id` thực sự dùng ở collection; ví dụ trên minh họa cú pháp. Việc chặn field lạ có thể gây lỗi ở rolling deployment khi app version mới thêm field chưa được validator chấp nhận. Cần lên kế hoạch expand schema trước khi deploy writer có field mới.

### 11.5. Regex và điều kiện phức tạp

`pattern` hữu ích cho một số quy tắc đơn giản, nhưng regex **không xác nhận email có người sở hữu thật**. Tương tự, validator không tự tạo unique constraint. Những biểu thức quá phức tạp cũng có thể làm đường ghi tăng chi phí kiểm tra. Cần cân bằng giữa **ràng buộc dữ liệu chung**, **validation theo nghiệp vụ** và **hiệu năng**.

### 11.6. Update/replace/pipeline đều cần tương thích

Tùy level, MongoDB kiểm tra **kết quả sau thao tác**:

- `updateOne` chỉ sửa `lastSeenAt` vẫn có thể bị reject nếu document legacy thiếu email.
- `replaceOne` có thể làm mất field bắt buộc nếu code dựng document mới thiếu field cũ.
- `findOneAndUpdate` có thể chịu validation giống các lệnh cập nhật theo phạm vi tương ứng.
- Aggregation kết thúc bằng `$merge`/`$out` và các job import có thể ghi vào collection được validate.
- Những writer ít được dùng trong ngày thường (maintenance, restore, scheduled jobs) vẫn thuộc phạm vi rollout.

Đổi validator rồi chỉ kiểm thử `insertOne` là chưa đủ để đảm bảo ứng dụng tương thích.

## 12. Rollback và quản lý cấu hình

### 12.1. Lưu schema cũ trước rollout

~~~javascript
const lab = db.getSiblingDB("schema_lab")
const info = lab.getCollectionInfos({ name: "users" })[0]
printjson(info.options)
~~~

Nên lưu bản schema canonical theo version trong repository, đi kèm ngày deploy, lý do thay đổi, kết quả đối soát và chủ sở hữu. Không tin vào trí nhớ khi cần rollback giữa sự cố.

### 12.2. Ví dụ khôi phục validator v1

Giả sử validator ban đầu chỉ yêu cầu `name`:

~~~javascript
const previousValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: ["name"],
    properties: {
      name: { bsonType: "string", minLength: 1 }
    }
  }
}

lab.runCommand({
  collMod: "users",
  validator: previousValidator,
  validationLevel: "strict",
  validationAction: "error"
})
~~~

Ví dụ này rollback **metadata validator**, **không hoàn tác dữ liệu đã backfill**, không xóa field được app mới tạo và không phục hồi side effects ngoài database. Nếu migration đã đổi kiểu hoặc xóa field, phải có kế hoạch data rollback riêng, tránh ghi đè cập nhật hợp lệ của người dùng sau thời điểm migration.

### 12.3. Tạm chuyển về warn khi có sự cố

Một phương án khẩn cấp là chuyển sang `warn` để giảm write errors trong giai đoạn sửa app:

~~~javascript
lab.runCommand({
  collMod: "users",
  validationAction: "warn"
})
~~~

Thao tác này **cho phép tiếp tục sinh invalid documents**, nên chỉ phù hợp nếu nghiệp vụ và chính sách vận hành chấp nhận. Phải có thời hạn, owner và quy trình dọn dữ liệu. Với `constraint` MongoDB 9.0, `warn` không phải action hợp lệ; cần tuân theo quy trình hạ level và thay rule được hỗ trợ.

### 12.4. Metadata rollback khác downgrade server

Nếu đã dùng tính năng MongoDB 8.1/9.0 như `errorAndLog` hoặc `constraint`, không thể kết luận server có thể downgrade chỉ nhờ một lệnh `collMod`. Phải xem **upgrade/downgrade guide** theo phiên bản và FCV. Điều này đặc biệt quan trọng khi schema change được triển khai cùng nâng cấp MongoDB Server.

## 13. Quy trình triển khai theo vai trò

| Giai đoạn | Việc cần xác minh | Owner thường gặp |
|---|---|---|
| Thiết kế | Hợp đồng schema, thay đổi breaking/non-breaking, kiểu BSON, ngoại lệ nghiệp vụ. | Developer + data owner. |
| Kiểm kê | Mọi writers, server/driver version, validator hiện tại, dữ liệu legacy. | Developer + DBA/SRE. |
| Chuẩn bị | Source schema canonical, script backfill idempotent, test/rollback plan. | Developer + DBA. |
| Expand | Reader chịu được legacy, writer mới chỉ sinh dữ liệu hợp lệ. | Application team. |
| Observe | `strict + warn`, đọc warnings và đếm invalid theo schema mới. | DBA/SRE + ứng dụng. |
| Migrate | Sửa theo lô, checkpoint, xác minh nguồn dữ liệu, đối soát. | Data owner + migration team. |
| Enforce | All writers compatible, invalid count được kiểm soát, `strict + error`. | DBA/SRE qua change plan. |
| Tùy chọn 9.0 | Nếu cần bảo đảm mạnh, chuẩn bị và scan để nâng `constraint`. | DBA/SRE. |
| Sau rollout | Theo dõi lỗi, drift, cleanup legacy, giới hạn bypass. | Operations + application. |

Để tránh validator drift, có thể so sánh collection options thực tế với schema versioned trong source trong pipeline triển khai, nhưng phải hiểu các option mặc định có thể không hiển thị tường minh trong `getCollectionInfos`. Readback metadata và đối soát document là **hai loại bằng chứng khác nhau**.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “`collMod` đã chạy thì dữ liệu cũ tự hợp lệ.” | Chỉ cập nhật metadata; phải kiểm kê/backfill riêng. |
| “`strict` bảo đảm không còn document invalid trong collection.” | Document cũ có thể tồn tại cho tới khi sửa; `constraint` 9.0 có bất biến mạnh hơn. |
| “`moderate` giống `warn`.” | Moderate quyết định phạm vi kiểm tra; warn quyết định cách xử lý vi phạm. |
| “`warn` là không có validation.” | Vẫn kiểm tra và log khi vi phạm, nhưng không reject. |
| “Đổi sang `error` sẽ tự dọn dữ liệu.” | Không; phải sửa document hoặc thay rule theo nghiệp vụ. |
| “Không có warning là toàn bộ dữ liệu sạch.” | Legacy data và thao tác không được kiểm tra có thể vẫn tồn tại. |
| “Bypass là cờ của cả collection hoặc session.” | Bypass là option theo từng write operation được hỗ trợ. |
| “Mọi API của mọi driver nhận bypass giống nhau.” | Cần xem command/driver/version. |
| “Có role readWrite là có quyền bypass.” | Cần privilege `bypassDocumentValidation` riêng cùng quyền ghi thích hợp. |
| “Bypass bỏ qua duplicate key.” | Unique index vẫn được thực thi. |
| “MongoDB 9.0 constraint vẫn bypass được nếu có quyền.” | `constraint` và prepare chặn bypass theo thiết kế. |
| “Rollback validator đồng nghĩa rollback dữ liệu.” | Schema metadata và biến đổi dữ liệu là hai việc khác nhau. |
| “Field có trong `required` chắc chắn đúng kiểu.” | Required chỉ kiểm tra sự tồn tại; thêm type/value rules nếu cần. |
| “`additionalProperties: false` không liên quan `_id`.” | Phải cho phép `_id` trong properties. |
| “MongoDB schema validation thay thế logic nghiệp vụ.” | Nó là một lớp bảo vệ tại ghi, không thay thế tất cả business validation. |

## 15. Bài tập tự kiểm tra

### Bài 1 — Breaking schema change

App v1 tạo user với `name`, có thể thiếu `email`. Validator mới yêu cầu `email` và bật `strict + error` trong khi app v1 còn chạy. Điều gì có thể xảy ra?

**Đáp án:** Insert từ app v1 có thể bị từ chối, và các update lên document legacy còn thiếu email cũng có thể lỗi. Cần expand writers/readers, quan sát, backfill và enforce theo giai đoạn.

### Bài 2 — Strict và moderate

Một document đã invalid theo rule mới. Một client chỉ `$set` một field không liên quan. Dưới `strict + error` và `moderate + error` có gì khác nhau?

**Đáp án:** Strict kiểm tra kết quả sau update và có thể reject. Moderate có thể không áp validation lên document vốn invalid, nên update có thể thành công mà document vẫn sai.

### Bài 3 — Tìm dữ liệu không hợp schema

Cho biến `nextValidator` chứa `{$jsonSchema:{...}}`. Viết query lấy các document không thỏa rule.

~~~javascript
db.getSiblingDB("schema_lab").users.find({
  $nor: [nextValidator]
})
~~~

`$nor` phủ định toàn bộ schema predicate. Muốn đếm, dùng `countDocuments` với filter tương tự.

### Bài 4 — ByPass và unique index

Collection có unique index trên `email`. Client cố insert email trùng với `bypassDocumentValidation: true`. Unique index còn hoạt động không?

**Đáp án:** **Có.** Bypass chỉ bỏ qua collection schema validator trong điều kiện được hỗ trợ; duplicate key vẫn là lỗi.

### Bài 5 — Quyền bypass

Một account có quyền `readWrite` thông thường nhưng không có action `bypassDocumentValidation`. Account có thể yêu cầu bypass trong một `insert` không?

**Đáp án:** Trong deployment bật authorization, **không**; cần thêm privilege bypass phù hợp. Không nên tự cấp role quản trị rộng để xử lý lỗi validation ứng dụng.

### Bài 6 — MongoDB 9.0 constraint

Collection đang `constraint`. Account có privilege bypass gửi write **hợp schema**, nhưng vẫn đặt `bypassDocumentValidation: true`. Kết quả là gì?

**Đáp án:** Command bị **từ chối** vì ở `constraint` bypass không được phép, kể cả document dự định ghi là hợp lệ.

### Bài 7 — Null và missing

Schema yêu cầu field `email` tồn tại và có `bsonType: "string"`. Ba document: `{}`, `{email:null}`, `{email:"an@example.test"}`. Document nào thỏa hai rule?

**Đáp án:** Chỉ document thứ ba. Document đầu thiếu required; document thứ hai có field nhưng sai kiểu.

### Bài 8 — Rollback ứng dụng

Sau khi bật validator v2 yêu cầu email, hệ thống muốn rollback ứng dụng về v1. Có an toàn nếu chỉ rollback application image không?

**Đáp án:** **Chưa chắc.** Writer v1 có thể tạo dữ liệu invalid; cần chiến lược tương thích ngược hoặc rollback metadata theo quy trình, và hiểu rằng dữ liệu đã migrate không tự trở về trạng thái trước.

### Bài 9 — Warning bằng 0

Hệ thống bật `moderate + warn` và cả ngày không có warning. Có thể kết luận collection không có dữ liệu invalid không?

**Đáp án:** **Không.** Document đã invalid có thể không được kiểm tra khi update; dữ liệu cũ có thể chưa từng được sửa. Cần scan schema và đánh giá mọi writers.

### Bài 10 — Có nên bypass kéo dài?

Một job import cần bypass để ghi hàng nghìn document legacy. Sau import, team định giữ bypass trong tất cả job ghi vì “đỡ lỗi”. Rủi ro là gì?

**Đáp án:** Rào chắn schema bị vô hiệu về thực tế với job đó, tài liệu invalid tích tụ, các update tương lai bị reject, và khó biết mức độ lệch schema. Cần scope riêng, count invalid, remediation plan và thu hồi quyền.

## 16. Tài liệu chính thức để đọc sâu

Tài liệu MongoDB thay đổi theo nhánh server. Với sản phẩm production, hãy mở **nhánh phiên bản đang chạy**, đọc cả release notes nếu dùng tính năng mới. Các link `/docs/manual/` thường dẫn đến tài liệu hiện hành ở thời điểm tra cứu.

- [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — khái niệm và phạm vi.
- [Modify Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/update-schema-validation/) — sửa validator đang tồn tại bằng `collMod`.
- [`collMod` database command](https://www.mongodb.com/docs/manual/reference/command/collmod/) — cú pháp, quyền hạn, option và tác động locking.
- [View Existing Validation Rules](https://www.mongodb.com/docs/manual/core/schema-validation/view-existing-validation-rules/) — `getCollectionInfos`, `listCollections`.
- [Specify Validation Level](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-level/) — `strict`, `moderate` và `constraint`.
- [Choose How to Handle Invalid Documents](https://www.mongodb.com/docs/manual/core/schema-validation/handle-invalid-documents/) — `error`, `warn` và `errorAndLog`.
- [Query for and Modify Valid or Invalid Documents](https://www.mongodb.com/docs/manual/core/schema-validation/use-json-schema-query-conditions/) — dùng `$jsonSchema` kết hợp `$nor` để tìm legacy data.
- [Bypass Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/bypass-document-validation/) — operation được hỗ trợ, privilege, giới hạn bypass.
- [Privilege Actions](https://www.mongodb.com/docs/manual/reference/privilege-actions/) — các action liên quan tới `collMod` và `bypassDocumentValidation`.
- [Tips for JSON Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/json-schema-tips/) — kiểu BSON, `_id` và `additionalProperties`.
- [MongoDB 8.0 — collMod](https://www.mongodb.com/docs/v8.0/reference/command/collmod/), [8.0 — Validation Level](https://www.mongodb.com/docs/v8.0/core/schema-validation/specify-validation-level/), [8.0 — Bypass](https://www.mongodb.com/docs/v8.0/core/schema-validation/bypass-document-validation/) — tham chiếu cố định nhánh 8.0.
- [MongoDB 7.0 — collMod](https://www.mongodb.com/docs/v7.0/reference/command/collmod/) — so sánh với dòng 7.0.

Một thay đổi validator được triển khai tốt khi **hợp đồng mới phản ánh đúng nghiệp vụ**, **tất cả writers đã tương thích**, **dữ liệu cũ được đối soát và xử lý**, và **trạng thái enforcement được đọc lại**. `bypassDocumentValidation` chỉ là ngoại lệ trên một số thao tác được kiểm soát, không thay thế migration. Luôn tách bạch bốn vấn đề: quy tắc dữ liệu là gì, những thao tác nào bị kiểm tra, vi phạm bị chặn hay cảnh báo, và phiên bản server có hỗ trợ chính sách mong muốn hay không.

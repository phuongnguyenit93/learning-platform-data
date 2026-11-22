# required, validationLevel và validationAction

> **Chương:** Collection và schema  
> **Module:** `SPRING_DATA_MONGODB`

MongoDB cho phép các document trong cùng collection có cấu trúc khác nhau. Sự linh hoạt này hữu ích khi dữ liệu phát triển nhanh, nhưng không đồng nghĩa ứng dụng nên chấp nhận mọi hình dạng dữ liệu. Khi nhiều service cùng ghi đơn hàng, một writer vô tình bỏ `tenantId`, ghi `totalMinor` thành String thay vì số hoặc đặt `status` ngoài tập được hỗ trợ có thể làm repository đọc sai, aggregation tính tổng thiếu và update thất bại. **Collection validation** giúp đưa các bất biến cốt lõi xuống phía MongoDB, để chúng được áp dụng bất kể writer dùng repository, `MongoTemplate` hay driver.

MongoDB cho phép khai báo `validator` cho collection, thường là `$jsonSchema`, và hai tùy chọn điều khiển: **`validationLevel`** và **`validationAction`**. Ba thứ có nhiệm vụ khác nhau:

- **`required`** trong `$jsonSchema`: những field bắt buộc phải **xuất hiện** trong document hoặc object tương ứng.
- **`validationLevel`**: MongoDB áp phép kiểm tra validator lên các lệnh insert/update trong trường hợp nào, đặc biệt với dữ liệu legacy vốn đã sai schema.
- **`validationAction`**: nếu kiểm tra phát hiện vi phạm, server **từ chối ghi** hay **cho phép nhưng cảnh báo**.

Bài nằm trong module `SPRING_DATA_MONGODB`, nơi thực hành kết nối và ánh xạ document, thao tác MongoDB qua `MongoTemplate` hoặc repository, truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng. Trọng tâm bài này là tạo, vận hành và kiểm thử **collection validator** nhất quán với model Java và thực tế dữ liệu.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Viết `$jsonSchema` với `bsonType`, `required`, `properties`, `enum` và ràng buộc số; phân biệt **thiếu field**, **giá trị null** và **sai BSON type**.
2. Giải thích chính xác hành vi `strict`, `moderate` và `off` của `validationLevel`.
3. Phân biệt `validationAction: "error"` và `"warn"`, hiểu rủi ro khi dùng `warn` trên production.
4. Tạo collection với validator, đổi cấu hình qua `collMod`, đọc lại `listCollections` và đối soát document legacy.
5. Tích hợp schema validation với Spring Data MongoDB mà không nhầm với `@Document`, `@Field`, Bean Validation hay unique index.
6. Viết integration test xác nhận server thực sự từ chối/cho phép các lệnh ghi theo từng tổ hợp cấu hình.
7. Lập kế hoạch triển khai từng giai đoạn để không khóa nhầm dữ liệu cũ hoặc cho phép dữ liệu lỗi tiếp tục sinh ra.

## 2. Ba lớp kiểm soát là ba câu hỏi độc lập

Giả sử hệ thống yêu cầu mỗi đơn hàng phải có `tenantId`, `orderNo`, `status` và `totalMinor`. Ta cần trả lời:

| Thành phần | Câu hỏi nó giải quyết | Ví dụ |
| --- | --- | --- |
| `validator` / `$jsonSchema.required` | Document hợp lệ trông như thế nào? | Phải có `tenantId`, `orderNo`, `status`, `totalMinor` |
| `validationLevel` | Những lần ghi nào bị đưa vào kiểm tra validator? | `strict` kiểm tra cả update trên document legacy không hợp lệ |
| `validationAction` | Khi validator báo sai, MongoDB phản ứng thế nào? | `error` từ chối ghi; `warn` cho ghi nhưng phát cảnh báo server |

Sơ đồ:

```text
Application / repository / MongoTemplate / driver
                     |
                     v
              INSERT hoặc UPDATE
                     |
                     v
         validationLevel áp dụng?
             |                |
            Không             Có
             |                |
             v                v
      Xử lý ghi bình thường  Đánh giá validator
                              |
                        +-----+------+
                        |            |
                       Hợp lệ      Vi phạm
                        |            |
                        v            v
                 Ghi bình thường  validationAction
                                    |
                         +----------+----------+
                         |                     |
                        error                 warn
                         |                     |
                         v                     v
                   Từ chối ghi         Ghi được, tạo cảnh báo
```

Đây là sơ đồ **hành vi validation**, không thay thế các kiểm tra độc lập khác. Ví dụ, một insert có `validationAction:"warn"` nhưng trùng `_id` vẫn thất bại do unique index của `_id`. Validator không vô hiệu hóa quyền truy cập, unique index, write concern hoặc quy tắc bất biến của MongoDB.

## 3. Bộ dữ liệu dùng xuyên suốt

Collection `orders` trong ứng dụng nhiều tenant lưu mỗi đơn như một document:

```javascript
{
  _id: "ORD-101",
  tenantId: "TENANT-A",
  orderNo: "A-2026-101",
  status: "NEW",
  totalMinor: NumberLong(150000),
  createdAt: ISODate("2026-11-20T02:00:00Z"),
  metadata: {
    source: "checkout",
    importedBy: "service-order"
  }
}
```

Quy ước bài học:

- `_id` là BSON String có giá trị ổn định; ví dụ `"ORD-101"`, không cần tự chuyển thành ObjectId.
- `tenantId` và `orderNo` là String **bắt buộc**; tenant phải được xác minh từ phân quyền của server.
- `status` chỉ thuộc một tập trạng thái đã xác định, chẳng hạn `NEW`, `PAID`, `CANCELLED`.
- `totalMinor` là BSON **Int64 (long)** không âm, theo đơn vị tiền nguyên nhỏ nhất được quy định bởi hệ thống.
- `createdAt` là BSON Date (UTC instant), khác với String chứa ngày tháng.
- `metadata` là object tùy chọn; nếu xuất hiện thì kiểm tra những field cần thiết bên trong.

Đây là **schema minh họa cho bài học**, không phải đề nghị rằng mọi dự án đều phải dùng String ID hoặc chỉ có ba trạng thái. Trong production, cần chốt schema từ hợp đồng nghiệp vụ, độ chính xác tiền tệ, chuyển đổi dữ liệu và yêu cầu tương thích.

## 4. Xây $jsonSchema với required và bsonType

MongoDB hỗ trợ một tập con/biến thể của JSON Schema dành cho BSON thông qua `$jsonSchema`. Những thuộc tính thường gặp gồm `bsonType`, `required`, `properties`, `enum`, `minimum` và `maximum`.

Một validator đơn giản:

```javascript
const orderSchema = {
  bsonType: "object",
  required: [
    "tenantId",
    "orderNo",
    "status",
    "totalMinor",
    "createdAt"
  ],
  properties: {
    _id: {
      bsonType: "string",
      description: "ID của đơn hàng theo hợp đồng hiện hành"
    },
    tenantId: {
      bsonType: "string",
      minLength: 1
    },
    orderNo: {
      bsonType: "string",
      minLength: 1
    },
    status: {
      bsonType: "string",
      enum: ["NEW", "PAID", "CANCELLED"]
    },
    totalMinor: {
      bsonType: "long",
      minimum: 0
    },
    createdAt: {
      bsonType: "date"
    },
    metadata: {
      bsonType: "object",
      properties: {
        source: { bsonType: "string" },
        importedBy: { bsonType: "string" }
      }
    }
  }
};
```

### 4.1. required là array tên field, không phải cờ ở từng property

Trong `$jsonSchema` của MongoDB:

```javascript
{
  bsonType: "object",
  required: ["tenantId", "status"],
  properties: {
    tenantId: { bsonType: "string" },
    status: { bsonType: "string" }
  }
}
```

Hai field này được yêu cầu hiện diện ở **object hiện tại**. Không dùng dạng:

```javascript
// PHẢN VÍ DỤ: không phải cú pháp required đúng của JSON Schema.
{
  properties: {
    status: {
      required: true
    }
  }
}
```

`required` trong JSON Schema là **một danh sách tên field** trên object chứa nó; nếu cần field bắt buộc bên trong object lồng nhau, khai báo `required` trong schema của **object con**.

### 4.2. required không đồng nghĩa non-null

Ví dụ:

```javascript
{
  bsonType: "object",
  required: ["reviewerNote"],
  properties: {
    reviewerNote: { }
  }
}
```

Document `{ reviewerNote: null }` vẫn thỏa điều kiện **field có hiện diện**, vì schema không cấm BSON null. Nếu muốn **có field và phải là String**, kết hợp cả `required` và `bsonType`:

```javascript
{
  bsonType: "object",
  required: ["reviewerNote"],
  properties: {
    reviewerNote: { bsonType: "string" }
  }
}
```

Kết quả:

| Giá trị đầu vào | `required` thỏa? | `bsonType:"string"` thỏa? | Kết luận |
| --- | --- | --- | --- |
| Thiếu `reviewerNote` | Không | Không áp kiểm tra kiểu trên field vắng mặt | Không hợp lệ |
| `reviewerNote: null` | Có | Không | Không hợp lệ |
| `reviewerNote: 123` | Có | Không | Không hợp lệ |
| `reviewerNote: ""` | Có | Có | Hợp lệ về kiểu, nhưng chuỗi rỗng vẫn được phép |
| `reviewerNote: "OK"` | Có | Có | Hợp lệ |

Nếu chuỗi rỗng cũng không chấp nhận, thêm `minLength: 1` và quy tắc xử lý khoảng trắng theo nghiệp vụ; `minLength` không tự trim chuỗi.

### 4.3. Required trong object lồng nhau

Ví dụ `metadata` là tùy chọn; nhưng **nếu có metadata**, `source` bắt buộc:

```javascript
{
  bsonType: "object",
  properties: {
    metadata: {
      bsonType: "object",
      required: ["source"],
      properties: {
        source: { bsonType: "string", minLength: 1 },
        importedBy: { bsonType: "string" }
      }
    }
  }
}
```

Vì `metadata` không nằm trong `required` của root, document thiếu toàn bộ `metadata` vẫn hợp lệ. Nhưng nếu `metadata: {}` thì không hợp lệ, vì nó thiếu `source`. Đây là cách mô tả **điều kiện bên trong object** khác với yêu cầu hiện diện của object ở cấp ngoài.

### 4.4. bsonType là BSON, không phải Java type

Một số ánh xạ thường gặp:

| MongoDB `bsonType` | Ví dụ BSON | Java/Spring Data thường dùng |
| --- | --- | --- |
| `string` | `"ORD-101"` | `String` |
| `bool` | `true` / `false` | `Boolean` / `boolean` |
| `int` | BSON Int32 | `Integer` / `int` |
| `long` | BSON Int64 | `Long` / `long` |
| `double` | BSON Double | `Double` / `double` |
| `decimal` | BSON Decimal128 | `Decimal128` / `BigDecimal` với converter phù hợp |
| `date` | BSON Date | `Instant` / `Date` với mapping phù hợp |
| `objectId` | BSON ObjectId | `ObjectId`; `String` ID có thể được chuyển tùy annotation/mapping |
| `object` | BSON subdocument | Object/record Java |
| `array` | BSON array | `List<T>` |

**Cảnh báo phổ biến:** JSON `150000` và Java `long` không đảm bảo mọi writer/driver đều tạo cùng BSON type. Ví dụ một số đường đi có thể lưu số nguyên nhỏ thành BSON Int32, còn `bsonType:"long"` từ chối Int32. Nếu cần cho phép cả Int32 và Int64 trong giai đoạn migration, có thể dùng `bsonType: ["int","long"]` tạm thời, rồi chuẩn hóa về một kiểu canonical. Với tiền tệ, kiểu số và cách làm tròn phải được xác nhận kỹ.

### 4.5. Có nên dùng additionalProperties: false?

`additionalProperties: false` buộc document không có field nằm ngoài danh sách schema cho phép. Nó hữu ích trong một số hệ thống có hợp đồng dữ liệu rất chặt, nhưng có thể **phá khả năng tương thích** khi framework lưu field như `_class` hoặc service khác ghi metadata hợp lệ mà schema chưa biết.

Trong bài này, ta **không bật** `additionalProperties:false`. Nếu muốn bật, hãy liệt kê các field được phép bao gồm `_id` và những discriminator/mapping fields do Spring Data hoặc hệ thống tạo, đồng thời lập kế hoạch rollout khi mở rộng schema. Không nên bật chỉ để “làm schema sạch” mà chưa biết tất cả writer.

## 5. Tạo collection với validator

Trên database thực hành `shop`, dùng `db.createCollection`:

```javascript
use shop

db.createCollection("orders", {
  validator: {
    $jsonSchema: orderSchema
  },
  validationLevel: "strict",
  validationAction: "error"
})
```

Ở đây biến `orderSchema` chính là object khai báo ở mục 4, chạy trong cùng phiên `mongosh`. Lệnh tạo collection phải thực hiện **trước khi đã có collection trùng tên**; nếu `orders` đã tồn tại, không dùng `createCollection` để ghi đè. Với collection đang hoạt động, sử dụng `collMod` sau khi có kế hoạch thay đổi dữ liệu.

Thêm document hợp lệ:

```javascript
db.orders.insertOne({
  _id: "ORD-101",
  tenantId: "TENANT-A",
  orderNo: "A-2026-101",
  status: "NEW",
  totalMinor: NumberLong(150000),
  createdAt: ISODate("2026-11-20T02:00:00Z")
})
```

Trường hợp vi phạm:

```javascript
// Thiếu status => không thỏa required.
db.orders.insertOne({
  _id: "ORD-BAD-1",
  tenantId: "TENANT-A",
  orderNo: "A-BAD-1",
  totalMinor: NumberLong(150000),
  createdAt: ISODate("2026-11-20T02:00:00Z")
})
```

Với `validationLevel:"strict"` và `validationAction:"error"`, MongoDB từ chối insert không hợp lệ. Lỗi thường thuộc dạng **document failed validation**, với error code `121` trong các trường hợp thông dụng; phần thông tin chi tiết có thể bao gồm validator nào không được thỏa. Đừng viết logic nghiệp vụ dựa trên việc parse một chuỗi thông báo lỗi có format cố định; dùng loại lỗi/code và thông tin có cấu trúc khi API/driver cung cấp.

### 5.1. Validator không phải unique index

Ngay cả khi `orderNo` được đánh dấu `required` và `bsonType:"string"`, hai đơn vẫn có thể dùng cùng `orderNo` nếu không có ràng buộc duy nhất. Nếu nghiệp vụ yêu cầu unique theo tenant:

```javascript
db.orders.createIndex(
  { tenantId: 1, orderNo: 1 },
  { unique: true, name: "uq_tenant_order_no" }
)
```

Đây là **index riêng**. Một duplicate `orderNo` có thể lỗi theo unique index ngay cả khi document thỏa hoàn toàn `$jsonSchema`. Với dữ liệu legacy có trùng khóa, index có thể không tạo thành công cho đến khi dọn dữ liệu trùng.

## 6. validationLevel: strict, moderate và off

`validationLevel` trả lời câu hỏi: **lệnh ghi nào phải được đánh giá theo validator?** MongoDB có những mức cơ bản:

| validationLevel | Insert mới | Update document hiện tại **đang hợp lệ** | Update document hiện tại **đang không hợp lệ** |
| --- | --- | --- | --- |
| `strict` | Kiểm tra | Kiểm tra | **Kiểm tra** |
| `moderate` | Kiểm tra | Kiểm tra | **Không áp kiểm tra validator** cho document vốn không hợp lệ |
| `off` | Bỏ qua validator | Bỏ qua validator | Bỏ qua validator |

**Điểm cốt lõi:** `moderate` **không có nghĩa chỉ cảnh báo**. Nó là mức quyết định **phạm vi kiểm tra**. Khi một document vốn hợp lệ bị cập nhật thành không hợp lệ, `moderate` vẫn kiểm tra và kết quả bị xử lý theo `validationAction`.

### 6.1. strict: kiểm tra mọi insert và update liên quan

Với collection sử dụng:

```javascript
{
  validationLevel: "strict",
  validationAction: "error"
}
```

Một document legacy thiếu `status` vẫn có thể **tồn tại** nếu nó được tạo trước khi validator được bật. Nhưng khi ứng dụng cập nhật document ấy, MongoDB kiểm tra **document sau khi update**. Nếu nó vẫn thiếu `status`, lệnh update không hợp lệ sẽ bị từ chối.

Ví dụ:

```javascript
// Giả định ORD-LEGACY được tạo trước khi bật validator,
// không có status trong BSON.
db.orders.updateOne(
  { _id: "ORD-LEGACY" },
  { $set: { note: "Đã kiểm tra dữ liệu cũ" } }
)
```

Nếu output vẫn không thỏa schema, `strict + error` sẽ từ chối cả thao tác sửa `note` này. Đây là nguyên nhân migration có thể gặp lỗi “bị khóa đường cập nhật” sau khi bật `strict` quá sớm.

Ngược lại, nếu update **đồng thời sửa đầy đủ các field còn thiếu và sai** để document sau ghi thỏa validator, một lệnh hợp lệ có thể thực hiện được. Vì vậy `strict` không bắt buộc phải xóa mọi document cũ trước, nhưng phải thiết kế đường sửa dữ liệu theo trạng thái cuối hợp lệ.

### 6.2. moderate: hỗ trợ giai đoạn chuyển tiếp cho legacy

Với:

```javascript
{
  validationLevel: "moderate",
  validationAction: "error"
}
```

MongoDB vẫn từ chối **insert mới không hợp lệ**. Nó cũng từ chối việc **làm hỏng một document đang hợp lệ**. Nhưng nếu document **đã không hợp lệ trước update**, những update trên document đó không bị kiểm tra bởi validator theo cơ chế `moderate`.

Hình dung:

```text
LEGACY-1 (thiếu status, đã không hợp lệ)
   |
   +-- $set note = "processed"
   |      moderate: không áp kiểm tra validator
   |      => được phép ghi (nếu không bị ràng buộc khác chặn)
   |
   +-- $set status = "NEW", các field khác cũng hợp lệ
          => document chuyển thành hợp lệ
          => các update tiếp theo được kiểm tra.

ORD-101 (ban đầu hợp lệ)
   |
   +-- $unset status
          moderate: có kiểm tra vì document ban đầu hợp lệ
          => vi phạm required; error từ chối.
```

**Rủi ro:** `moderate` có thể cho phép một writer cũ tiếp tục cập nhật **document legacy không hợp lệ** mà không sửa lỗi schema. Vì vậy nó chỉ là một phần của chiến lược chuyển tiếp, không phải cơ chế tự động làm sạch dữ liệu.

### 6.3. off: bỏ qua collection validation

`validationLevel:"off"` tắt việc thực thi validator cho thao tác ghi thuộc phạm vi đó. Nó không xóa định nghĩa validator khỏi collection, nhưng bỏ qua kiểm tra schema trong khi mức này đang áp dụng. Điều đó khác với việc đổi `validationAction:"warn"`: `warn` vẫn chạy đánh giá validator và tạo cảnh báo khi vi phạm.

Không nên để `off` vô thời hạn sau khi đã thống nhất một hợp đồng schema. Khi cần tạm ngừng để migration, giới hạn thời gian, quyền thực hiện, log thay đổi và theo dõi dữ liệu mới phát sinh.

### 6.4. validationLevel không phải chế độ validate toàn bộ collection tức thì

Đổi `strict` hoặc `moderate` không đồng nghĩa MongoDB tự quét và sửa mọi document đã lưu. Các document sai schema **vẫn tồn tại** cho đến khi được sửa/xóa; việc bật validator chủ yếu ảnh hưởng **các thao tác ghi tiếp theo**. Cần công cụ audit và kế hoạch migration riêng.

## 7. validationAction: error và warn

Nếu `validationLevel` khiến thao tác được kiểm tra và kết quả không hợp lệ, `validationAction` quyết định phản ứng.

### 7.1. error: từ chối vi phạm

```javascript
db.runCommand({
  collMod: "orders",
  validationLevel: "strict",
  validationAction: "error"
})
```

Đối với lệnh insert/update bị đánh giá là không hợp lệ, MongoDB không chấp nhận thay đổi đó. Trong driver, lệnh ghi thường phát sinh exception, và ứng dụng cần trả lỗi nghiệp vụ phù hợp thay vì làm như thao tác đã thành công.

Đừng suy luận một bulk write **nhiều document** sẽ tự rollback tất cả vì một document không thỏa validator. Một bulk không có transaction vẫn có thể thành công **một phần**; validation chỉ từ chối thao tác vi phạm.

### 7.2. warn: cho ghi nhưng cảnh báo

```javascript
db.runCommand({
  collMod: "orders",
  validationLevel: "strict",
  validationAction: "warn"
})
```

Khi một document vi phạm validator:

- MongoDB **cho phép** thao tác ghi (nếu không vướng các ràng buộc khác).
- Server ghi cảnh báo về việc validation thất bại vào cơ chế log tương ứng.
- Driver có thể báo **ghi thành công**: ứng dụng không nhận exception chỉ vì document sai validator.

**Không nhầm `warn` với “log lỗi nhưng vẫn reject”.** `warn` không phải chế độ chặn dữ liệu sai. Vì thế khi đưa `warn` vào rollout, phải có **monitoring** và lịch khắc phục dữ liệu thực sự; không để cấu hình ấy trở thành lớp bảo vệ duy nhất của dữ liệu quan trọng.

### 7.3. Bảng tình huống kết hợp

| validationLevel | validationAction | Document mới vi phạm | Update document cũ đã không hợp lệ | Dùng khi |
| --- | --- | --- | --- | --- |
| `strict` | `error` | Từ chối | Từ chối nếu kết quả vẫn sai | Hợp đồng đã được áp dụng đầy đủ |
| `strict` | `warn` | Cho phép, cảnh báo | Cho phép, cảnh báo nếu kết quả vẫn sai | Quan sát mức độ vi phạm trước khi bật chặn |
| `moderate` | `error` | Từ chối | Có thể cho phép vì vốn đã không hợp lệ | Migration dần, bảo vệ dữ liệu mới và dữ liệu đã chuẩn |
| `moderate` | `warn` | Cho phép, cảnh báo | Có thể ghi mà không kiểm tra validator | Giai đoạn chuyển tiếp đặc biệt, cần giám sát rõ |
| `off` | `error` hoặc `warn` | Không kiểm tra schema | Không kiểm tra schema | Tạm tắt validation có kiểm soát |

Bảng mô tả **kết quả từ validator**, không bao gồm duplicate key, permission, immutable field hay lỗi định dạng BSON độc lập. Với `moderate + warn`, việc update một document đã không hợp lệ không nhất thiết tạo cảnh báo schema, vì thao tác đó có thể **không nằm trong phạm vi đánh giá**.

### 7.4. Ghi chú về phiên bản server

Hai hành động `error` và `warn` là các giá trị cơ bản được dùng trong bài. Một số bản MongoDB mới có thể bổ sung giá trị/hành vi khác tùy phiên bản server và môi trường triển khai; khi sử dụng lựa chọn mới, phải đối chiếu **tài liệu của chính phiên bản MongoDB đang chạy**, không giả định mọi cluster đều hỗ trợ.

## 8. Thay đổi validator và chính sách bằng collMod

Collection hiện có cần sửa bằng lệnh `collMod` (với quyền phù hợp):

```javascript
db.runCommand({
  collMod: "orders",
  validator: {
    $jsonSchema: orderSchema
  },
  validationLevel: "moderate",
  validationAction: "warn"
})
```

Sau khi audit dữ liệu và hoàn tất sửa writer:

```javascript
db.runCommand({
  collMod: "orders",
  validationLevel: "moderate",
  validationAction: "error"
})
```

Khi dữ liệu cũ đã được chuẩn hóa:

```javascript
db.runCommand({
  collMod: "orders",
  validationLevel: "strict",
  validationAction: "error"
})
```

Các ví dụ trên sử dụng `orderSchema` từ mục 4. Để **đổi validator**, cung cấp field `validator` mới; để chỉ đổi mức/hành động, có thể đưa riêng các option cần thay. Tác động của thay đổi cần được kiểm tra ở môi trường staging: writer phiên bản cũ có thể bắt đầu gặp lỗi hoặc thay đổi ngữ nghĩa dữ liệu khi validator nghiêm ngặt hơn.

### 8.1. Xem cấu hình server đang thực thi

```javascript
db.getCollectionInfos({ name: "orders" })
```

Kiểm tra các trường cấu hình collection được trả về, thường gồm `options.validator`, `options.validationLevel` và `options.validationAction` khi được đặt. Tránh chỉ nhìn file cấu hình Java rồi khẳng định collection đã được bảo vệ: có thể migration chưa chạy hoặc một môi trường được tạo từ trước với validator khác.

Với nhiều môi trường, nên có **schema deployment process** versioned, kèm so sánh định nghĩa validator mong muốn và định nghĩa thực trên MongoDB.

### 8.2. collMod không sửa document đã lưu

Sau `collMod`:

```javascript
db.orders.findOne({ _id: "ORD-LEGACY" })
```

nếu ORD-LEGACY đang thiếu `status`, field ấy vẫn thiếu; `collMod` chỉ đổi **quy tắc đánh giá trong tương lai**, không tự điền field. Để đạt trạng thái strict toàn bộ, cần **kiểm kê, backfill, normalize và xác minh** từng nhóm dữ liệu trước khi tăng mức chặn.

## 9. Update cũng bị kiểm tra dựa trên document cuối

Một hiểu nhầm phổ biến là `required` chỉ áp dụng cho `insertOne`, còn `$set` chỉ sửa một field thì được miễn.

Giả sử ORD-101 hợp lệ:

```javascript
db.orders.updateOne(
  { _id: "ORD-101", tenantId: "TENANT-A" },
  { $unset: { status: "" } }
)
```

Với `strict + error` (hoặc `moderate + error` khi ORD-101 vốn hợp lệ), lệnh trên vi phạm `required:["status"]` và bị từ chối. MongoDB đánh giá **document sau khi áp update**, chứ không chỉ xem đường dẫn `status` có xuất hiện trong `$set` hay không.

### 9.1. $set null vào field required

```javascript
db.orders.updateOne(
  { _id: "ORD-101", tenantId: "TENANT-A" },
  { $set: { status: null } }
)
```

Field `status` vẫn tồn tại nên qua được phần `required`, **nhưng vi phạm `bsonType:"string"` và `enum`**. Đây là lý do phải kết hợp yêu cầu hiện diện, kiểu BSON và ràng buộc giá trị.

### 9.2. ReplaceOne và save của Spring Data

Một replacement chỉ chứa:

```javascript
{
  tenantId: "TENANT-A",
  orderNo: "A-2026-101",
  totalMinor: NumberLong(150000)
}
```

sẽ thiếu `status` và `createdAt`. Nếu cố dùng làm replacement cho một order hợp lệ, nó bị validator từ chối khi validation áp dụng và hành động là `error`. Ngoài ra, replacement có thể **làm mất field legacy/unknown** nếu dùng entity Java chưa ánh xạ tất cả field.

Validator giúp từ chối **một số** replacement sai schema, nhưng **không bảo đảm** giữ những field mà schema chưa yêu cầu. Nếu chỉ cập nhật `status` hoặc một metadata, ưu tiên `$set` có điều kiện và optimistic locking/CAS khi cần; đừng dựa vào validator để ngăn mọi lost update.

### 9.3. Delete và read không phải insert/update

Collection validator chủ yếu kiểm soát **ghi document mới và cập nhật document**; nó không tự ẩn document sai schema khỏi `find`/aggregation, cũng không tự tạo filter phân quyền. Xóa document là vấn đề riêng với quyền/retention. Khi bật strict, các bản ghi legacy vẫn có thể được đọc, khiến downstream phải xử lý null/missing cho tới khi migration kết thúc.

## 10. bypassDocumentValidation: ngoại lệ có kiểm soát

Một số lệnh ghi MongoDB hỗ trợ `bypassDocumentValidation`. Khi caller có **quyền phù hợp** và chủ động bật tùy chọn này, có thể bỏ qua validation cho tác vụ cụ thể, tùy lệnh và phiên bản server.

Ví dụ minh họa cách một lệnh có thể chứa option:

```javascript
db.runCommand({
  insert: "orders",
  documents: [
    {
      _id: "ORD-IMPORT",
      tenantId: "TENANT-A",
      orderNo: "A-IMPORT",
      status: "NEW",
      totalMinor: NumberLong(5000),
      createdAt: ISODate("2026-11-20T04:00:00Z")
    }
  ],
  bypassDocumentValidation: true
})
```

Document trong ví dụ **đã hợp lệ**, để không cổ vũ ghi dữ liệu lỗi. `bypassDocumentValidation` không phải cách xử lý thường nhật cho lỗi schema; nếu bật tùy tiện, nó phá vỡ bảo đảm mà ứng dụng mong có từ collection validator.

Quy tắc vận hành:

- Chỉ cấp đặc quyền bypass cho migration/operational role thực sự cần.
- Log ai thực hiện, khoảng dữ liệu, mục đích và thời điểm.
- Kiểm tra hậu migration và **đưa dữ liệu về schema hợp lệ**.
- Không bật bypass mặc định cho repository hoặc `MongoTemplate` của API thông thường.

Đừng coi collection validation là cơ chế bảo mật tenant/authorization: validator không chứng minh user được sửa một `tenantId` nào. Phân quyền, filter tenant, index và validator phải được thiết kế **bổ sung cho nhau**.

## 11. Audit dữ liệu cũ trước khi chuyển sang strict

Trước khi áp `strict + error` cho collection lâu năm, cần biết **đã có bao nhiêu document không hợp lệ** và chúng vi phạm điều gì.

### 11.1. Dùng cùng $jsonSchema để tìm document sai

`$jsonSchema` có thể được sử dụng như query predicate. Nếu đã có biến `orderSchema` ở `mongosh`:

```javascript
// Kiểm tra số document hiện không thỏa schema.
db.orders.countDocuments({
  $nor: [
    { $jsonSchema: orderSchema }
  ]
})
```

Và xem mẫu để lên kế hoạch migration:

```javascript
db.orders.find(
  {
    $nor: [
      { $jsonSchema: orderSchema }
    ]
  },
  {
    tenantId: 1,
    orderNo: 1,
    status: 1,
    totalMinor: 1,
    createdAt: 1
  }
).limit(20)
```

`$nor` ở đây lấy **những document không khớp với validator**. Lệnh chỉ **đọc**, không làm document hợp lệ hơn. Với collection lớn, scan toàn bộ bằng `$jsonSchema` có thể tốn tài nguyên: lên lịch, đo chi phí và lấy mẫu theo tenant/batch phù hợp.

### 11.2. Thống kê kiểu BSON của field quan trọng

Nếu `totalMinor` từng được lưu bằng số, String, BSON Decimal128:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        statusType: { $type: "$status" },
        amountType: { $type: "$totalMinor" }
      },
      documents: { $sum: 1 }
    }
  },
  { $sort: { documents: -1 } }
])
```

Kết quả giúp phân biệt `missing`, `null`, `string`, `int`, `long`, `decimal`... Không được kết luận dữ liệu sạch chỉ vì Java converter hiện đọc được một số giá trị: MongoDB validator đánh giá **BSON thực sự lưu trên server**, không đánh giá type của DTO sau khi convert.

### 11.3. Không backfill bằng giá trị đoán bừa

Document thiếu `status` không nhất thiết là đơn ở trạng thái `NEW`. Có thể đó là dữ liệu từ hệ thống cũ với một trạng thái khác, hoặc là bản ghi cần kiểm tra thủ công. Trước khi điền:

- Xác định nguồn sự thật của `status` và `createdAt`.
- Kiểm tra quy tắc tài chính cho `totalMinor`, đơn vị tiền, phí, hoàn tiền.
- Đánh dấu bản ghi không thể suy ra giá trị để xử lý riêng, không hợp thức hóa bằng dữ liệu giả.
- Duy trì checkpoint, log số lượng trước/sau và khả năng phục hồi nếu migration thất bại.

Khi đã chứng minh một tập nhỏ chỉ thiếu thông tin **được suy ra chắc chắn**, có thể chạy update có filter:

```javascript
// CHỈ khi đã chứng minh dữ liệu của nguồn LEGACY-X
// thiếu status luôn tương ứng trạng thái NEW.
db.orders.updateMany(
  {
    legacySource: "LEGACY-X",
    status: { $exists: false }
  },
  {
    $set: { status: "NEW" }
  }
)
```

Trên collection có `strict + error`, câu update vẫn có thể thất bại nếu document còn sai **các field khác**. Trong giai đoạn migration, có thể chuẩn hóa **tất cả field cần sửa trong một lần** hoặc áp quy trình chuyển tiếp có `moderate`/quyền bypass được kiểm soát. Tránh sửa từng field rồi hy vọng validator bỏ qua document cuối vẫn sai.

### 11.4. Có nên chuyển totalMinor từ String sang Long?

Ví dụ document legacy:

```javascript
{
  _id: "ORD-OLD-2",
  tenantId: "TENANT-A",
  orderNo: "A-OLD-2",
  status: "PAID",
  totalMinor: "150000",
  createdAt: ISODate("2026-11-01T02:00:00Z")
}
```

`$toLong` hoặc `$convert` trong update pipeline có thể được dùng để chuẩn hóa, nhưng **không phải mọi String đều chuyển được**. Cần kiểm tra giá trị không âm, khả năng overflow, đơn vị tiền và xử lý lỗi:

```javascript
// Chỉ dùng với batch dữ liệu đã xác nhận có String hợp lệ.
db.orders.updateMany(
  {
    totalMinor: { $type: "string" },
    legacySource: "LEGACY-X"
  },
  [
    {
      $set: {
        totalMinor: { $toLong: "$totalMinor" }
      }
    }
  ]
)
```

Nếu một String như `"unknown"` không chuyển được, lệnh có thể lỗi. Với migration có dữ liệu bẩn, dùng quy trình **quarantine/đối soát** hoặc `$convert` với `onError` có chính sách rõ; **không** gán mặc định 0 rồi gọi đó là số tiền hợp lệ.

## 12. Chiến lược triển khai tăng dần

Đối với một collection đang có nhiều writer, rollout theo pha giúp tránh tình huống service cũ bị chặn ghi bất ngờ:

**Pha A — Khảo sát.** Đọc cấu hình hiện tại, đo tỷ lệ sai schema, liệt kê các writer, chốt schema canonical và danh sách ngoại lệ hợp lệ.

**Pha B — Cập nhật writer.** Đảm bảo repository, `MongoTemplate`, các job nhập liệu và service cũ có thể ghi document thỏa schema. Triển khai kiểm thử cơ bản trong CI; kiểm tra mapping của Long, Date, enum, null và các field do hệ thống khác tạo.

**Pha C — Quan sát với warn.** Bật `strict + warn` nếu mục đích là **thấy mọi vi phạm ghi mới và update**, kể cả document legacy. Bổ sung cảnh báo log/metric và đối soát với audit.

**Pha D — Chặn dữ liệu mới bằng moderate + error.** Khi đã tin các writer mới đáp ứng schema, bật `moderate + error` nếu còn document cũ không hợp lệ và cần tiếp tục update chúng. Tác vụ thay đổi document đã hợp lệ vẫn phải thỏa validator.

**Pha E — Sửa legacy.** Chạy migration phân lô, bảo đảm không còn field thiếu/sai BSON type, kiểm tra lại bằng `$jsonSchema` và đối soát dữ liệu nghiệp vụ. Kiểm tra cả những writer chưa được nâng cấp.

**Pha F — Khóa strict + error.** Bật `strict + error` khi không còn ngoại lệ chưa xử lý, có test và quy trình rollback được phê duyệt. Giám sát lỗi validation sau triển khai.

Các pha là **một lộ trình tham khảo**, không phải chuỗi bắt buộc cho mọi deployment. Nếu collection mới hoàn toàn không có legacy, có thể tạo ngay với `strict + error`. Nếu dữ liệu nhạy cảm không thể cho phép ghi sai ngay cả trong giai đoạn quan sát, ưu tiên thẩm định writer trên staging và bật chặn phù hợp thay vì mặc định dùng `warn` ở production.

### 12.1. Vì sao rollout nhiều phiên bản khó?

Giả sử hai service cùng ghi:

```text
Order Service V2: ghi totalMinor dưới BSON Long, có createdAt.
Order Service V1: ghi totalMinor dưới BSON String, thiếu createdAt.
                 |
                 v
        Validator strict + error
                 |
             V2 thành công
             V1 bị từ chối ghi
```

Nếu deploy collection validator **trước khi mọi writer đã chuyển**, V1 có thể gặp lỗi sản xuất. Vì vậy schema validation cần được coi là **thay đổi hợp đồng chung của hệ thống**, không chỉ thay đổi một annotation trong service Java.

### 12.2. Nhánh rollback không phải tắt rồi quên

Khi validator gây gián đoạn, rollback có thể gồm đổi `validationAction` sang `warn` hoặc tạm chỉnh `validationLevel` dưới sự phê duyệt vận hành, nhưng phải:

- Ghi lại chính xác cấu hình trước/sau.
- Xác định phạm vi dữ liệu có thể bị ghi sai trong khoảng nới lỏng.
- Audit và sửa những document đó trước khi bật chặn lại.
- Đảm bảo rollback không trở thành mặc định dài hạn.

Nếu nguyên nhân là schema triển khai sai (ví dụ vô tình cấm `_class`), nên **sửa schema đúng** và kiểm thử trước, thay vì duy trì `off`.

## 13. Spring Data MongoDB: mapping không thay thế collection validation

Trong Java, `@Document` chỉ định collection, `@Id` đánh dấu định danh, `@Field` ánh xạ property, còn Bean Validation (nếu được cấu hình) chạy ở phía ứng dụng theo đường gọi cụ thể. Không annotation nào trong số đó **tự có nghĩa MongoDB đã được cài `$jsonSchema`**.

### 13.1. Model Java tương ứng

File `OrderDocument.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id String id,
    String tenantId,
    String orderNo,
    String status,
    Long totalMinor,
    Instant createdAt
) {}
```

Model này hữu ích cho repository và `MongoTemplate`. Nhưng nếu gọi:

```java
OrderDocument invalid = new OrderDocument(
    "ORD-INVALID",
    "TENANT-A",
    "A-INVALID",
    null,               // status thiếu về nghĩa nghiệp vụ
    150000L,
    Instant.parse("2026-11-20T02:00:00Z"));

repository.save(invalid);
```

thì còn tùy mapping/configuration, phía Java có thể loại field null hoặc gửi BSON null. Dù trường hợp nào, với validator yêu cầu `status` là String hợp lệ, MongoDB sẽ **từ chối ghi** khi `strict + error` áp dụng. Đây là lớp bảo vệ phía server ngay cả khi một đường ứng dụng quên validation.

### 13.2. Bean Validation và MongoDB validator khác nhau

| Tiêu chí | Bean Validation (ví dụ `@NotNull`) | MongoDB `$jsonSchema` |
| --- | --- | --- |
| Nơi thực thi | JVM, ở những đường gọi có áp validation | MongoDB server, với ghi thuộc phạm vi validation |
| Kiểu dữ liệu kiểm tra | Property Java và constraint validator | BSON thực lưu trong MongoDB |
| Bảo vệ writer ngoài Java service? | Không | Có, nếu writer không bypass và validator áp dụng |
| `@NotNull` tự cài `required` vào collection? | Không mặc định | `required` phải được cấu hình server |
| Có thể kiểm tra update một phần từ driver? | Không nếu không tự gọi validation tương ứng | Có, dựa trên document sau update khi mức validation áp dụng |
| Hỗ trợ thông báo lỗi trải nghiệm người dùng | Thường dễ mô tả theo field input | Lỗi server cần được chuyển thành phản hồi nghiệp vụ |

Với REST API, validate ở application layer vẫn rất quan trọng để trả thông báo rõ, kiểm tra quyền và quy tắc nghiệp vụ không thể biểu đạt hoàn toàn bằng JSON Schema. MongoDB validator là **lưới an toàn phía persistence**, không phải lý do bỏ toàn bộ validation ở service.

### 13.3. @Id String và bsonType của _id

Một entity có `@Id String id` có thể được Spring Data MongoDB chuyển thành BSON ObjectId nếu chuỗi có định dạng hợp lệ theo mapping mặc định. Nếu collection validator yêu cầu:

```javascript
_id: { bsonType: "string" }
```

nhưng writer lưu `_id` thành BSON ObjectId, lệnh có thể bị từ chối. Để schema/Java thống nhất, chọn chiến lược ID và kiểm thử raw BSON. Với nhu cầu buộc String, Spring Data cung cấp các cách khai báo ID tường minh như `@MongoId`; cần xác nhận kiểu target và mapping của phiên bản framework đang dùng.

### 13.4. createdAt: Date BSON so với String

`Instant` thường được converter của Spring Data lưu thành BSON Date theo cấu hình mapping chuẩn. Tuy nhiên, một tác vụ nhập JSON thô có thể gửi:

```javascript
{ createdAt: "2026-11-20T02:00:00Z" }
```

Đó là **String**, không phải BSON Date. Với `bsonType:"date"`, validator từ chối. Khi nhận dữ liệu từ hệ thống bên ngoài, hãy parse ngày theo múi giờ/chính sách của sản phẩm trước khi ghi; không dựa vào hình thức string trông giống ISO timestamp.

## 14. Cấu hình collection validator qua MongoTemplate / MongoDB driver

Schema validation được cài ở **database**, thường thông qua migration/deployment script. Spring Data MongoDB cung cấp các API liên quan tới schema/collection options ở những phiên bản tương ứng; một cách tường minh để nhìn thấy lệnh server là gửi `create` hoặc `collMod` qua `MongoTemplate.getDb().runCommand(...)`.

### 14.1. Áp cấu hình cho collection đã tồn tại

File `OrderSchemaMaintenance.java` (đoạn minh họa dùng trong chương trình migration có quyền được duyệt):

```java
package com.example.shop.orders;

import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;

public final class OrderSchemaMaintenance {

    private OrderSchemaMaintenance() {}

    public static Document schema() {
        return new Document("bsonType", "object")
            .append("required", List.of(
                "tenantId", "orderNo", "status",
                "totalMinor", "createdAt"))
            .append("properties", new Document()
                .append("tenantId",
                    new Document("bsonType", "string")
                        .append("minLength", 1))
                .append("orderNo",
                    new Document("bsonType", "string")
                        .append("minLength", 1))
                .append("status",
                    new Document("bsonType", "string")
                        .append("enum", List.of(
                            "NEW", "PAID", "CANCELLED")))
                .append("totalMinor",
                    new Document("bsonType", "long")
                        .append("minimum", 0))
                .append("createdAt",
                    new Document("bsonType", "date")));
    }

    public static void enableStrictValidation(
            MongoTemplate template) {

        Document command = new Document("collMod", "orders")
            .append("validator",
                new Document("$jsonSchema", schema()))
            .append("validationLevel", "strict")
            .append("validationAction", "error");

        template.getDb().runCommand(command);
    }
}
```

Mã không tự tạo collection. Nếu `orders` chưa tồn tại, `collMod` không phải cách khởi tạo; cần tạo collection với validator như mục 5 hoặc dùng lệnh `create` tương ứng. Nếu collection đã tồn tại, migration phải kiểm tra quyền, định nghĩa schema, tương thích dữ liệu và lưu version deployment trước khi chạy `enableStrictValidation(...)`.

Để đọc cấu hình hiện tại trong Java, có thể dùng:

```java
Document info = template.getDb()
    .listCollections()
    .filter(new Document("name", "orders"))
    .first();

if (info == null) {
    throw new IllegalStateException(
        "Collection orders chưa tồn tại");
}

Document options = info.get("options", Document.class);
System.out.println(options);
```

Đoạn này nằm trong method có `template` đã inject. `listCollections` được trả về qua driver; cấu trúc options có thể khác tùy option nào được cấu hình và phiên bản server. Đừng ghi toàn bộ thông tin nhạy cảm hoặc internal schema vào log không có kiểm soát ở môi trường production.

### 14.2. Không chạy collMod theo từng HTTP request

`collMod` là thao tác quản trị schema ở cấp collection, không phải một lệnh ghi domain thông thường. **Không** gọi `enableStrictValidation` trong controller khi nhận request tạo đơn, và không đặt tùy tiện vào mọi lần truy vấn repository.

Thay vào đó:

1. Quản lý schema như một thay đổi được version hóa trong quy trình deploy/migration.
2. Áp dụng bởi tài khoản có quyền phù hợp và có log/approval.
3. Kiểm tra `listCollections`/audit để xác nhận môi trường đã ở trạng thái mong muốn.
4. Tách tài khoản ứng dụng thông thường khỏi quyền quản trị schema nếu yêu cầu bảo mật cho phép.

### 14.3. MongoJsonSchema và CollectionOptions

Ở các phiên bản Spring Data MongoDB hỗ trợ, `MongoJsonSchema` và `CollectionOptions` có thể dùng để định nghĩa schema/option collection với DSL thay cho tài liệu BSON thủ công. Tuy nhiên, **ý nghĩa server vẫn là `$jsonSchema` + `validationLevel` + `validationAction`**. Cần đối chiếu chính xác API builder với phiên bản Spring Data đang dùng trước khi copy code; một builder ở phiên bản mới có thể khác overload hoặc kiểu enum ở phiên bản cũ.

Bài cố ý trình bày lệnh BSON tường minh để có thể so sánh trực tiếp với cấu hình thật trên MongoDB, thay vì giả định mọi version Spring Data có cùng một fluent DSL.

## 15. Kiểm thử tích hợp với MongoDB thật

Chỉ kiểm thử một `OrderDocument` trong Java không chứng minh server đang có `validator`. Có thể model và Bean Validation đều chặn dữ liệu ở JVM, trong khi writer khác dùng driver trực tiếp vẫn ghi được dữ liệu sai. **Integration test phải tạo/cập nhật validator trên MongoDB thực**, gửi các insert/update **bằng raw driver** và kiểm tra lỗi hoặc document sau ghi.

Ví dụ sử dụng JUnit 5, AssertJ, MongoDB Java Driver và Spring Boot `@DataMongoTest`. Package annotation dưới đây theo cách tổ chức thường gặp ở Spring Boot 3.x; với major version khác, xác minh lại package/dependencies. Cần cấu hình MongoDB test cô lập (ví dụ Testcontainers) và quyền tạo/drop/collMod collection trong test database.

### 15.1. Fixture, schema và helper cài chính sách

File `OrderCollectionValidationIntegrationTest.java`:

```java
package com.example.shop.orders;

import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import java.time.Instant;
import java.util.Date;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DataMongoTest
class OrderCollectionValidationIntegrationTest {

    @Autowired
    MongoTemplate template;

    private MongoCollection<Document> collection() {
        return template.getCollection("orders");
    }

    private static Document schema() {
        return new Document("bsonType", "object")
            .append("required", List.of(
                "tenantId", "orderNo", "status",
                "totalMinor", "createdAt"))
            .append("properties", new Document()
                .append("tenantId",
                    new Document("bsonType", "string")
                        .append("minLength", 1))
                .append("orderNo",
                    new Document("bsonType", "string")
                        .append("minLength", 1))
                .append("status",
                    new Document("bsonType", "string")
                        .append("enum", List.of(
                            "NEW", "PAID", "CANCELLED")))
                .append("totalMinor",
                    new Document("bsonType", "long")
                        .append("minimum", 0))
                .append("createdAt",
                    new Document("bsonType", "date")));
    }

    private static Document validOrder(String id) {
        return new Document("_id", id)
            .append("tenantId", "TENANT-A")
            .append("orderNo", "A-" + id)
            .append("status", "NEW")
            .append("totalMinor", 150000L)
            .append("createdAt", Date.from(
                Instant.parse("2026-11-20T02:00:00Z")));
    }

    private void configure(String level, String action) {
        template.getDb().runCommand(
            new Document("collMod", "orders")
                .append("validator",
                    new Document("$jsonSchema", schema()))
                .append("validationLevel", level)
                .append("validationAction", action));
    }

    private Document findById(String id) {
        return collection()
            .find(Filters.eq("_id", id))
            .first();
    }

    @BeforeEach
    void startWithCollectionWithoutValidator() {
        // TUYỆT ĐỐI chỉ sử dụng database TEST cô lập.
        collection().drop();
        template.getDb().runCommand(
            new Document("create", "orders"));
    }

    @Test
    void strictErrorAcceptsValidAndRejectsMissingRequiredField() {
        configure("strict", "error");

        collection().insertOne(validOrder("ORD-OK"));
        assertThat(findById("ORD-OK")).isNotNull();

        Document missingStatus = validOrder("ORD-NO-STATUS");
        missingStatus.remove("status");

        assertThatThrownBy(
            () -> collection().insertOne(missingStatus))
            .isInstanceOfSatisfying(
                MongoWriteException.class,
                ex -> assertThat(ex.getError().getCode())
                    .isEqualTo(121));

        assertThat(findById("ORD-NO-STATUS")).isNull();
    }

    @Test
    void requiredPlusBsonTypeRejectsNullAndWrongNumericType() {
        configure("strict", "error");

        Document nullStatus = validOrder("ORD-NULL");
        nullStatus.put("status", null);

        assertThatThrownBy(
            () -> collection().insertOne(nullStatus))
            .isInstanceOf(MongoWriteException.class);

        Document wrongAmount = validOrder("ORD-STRING-AMOUNT");
        wrongAmount.put("totalMinor", "150000");

        assertThatThrownBy(
            () -> collection().insertOne(wrongAmount))
            .isInstanceOf(MongoWriteException.class);

        Document int32Amount = validOrder("ORD-INT-AMOUNT");
        int32Amount.put("totalMinor", 150000); // Java Integer -> BSON Int32

        assertThatThrownBy(
            () -> collection().insertOne(int32Amount))
            .isInstanceOf(MongoWriteException.class);
    }

    @Test
    void strictErrorRejectsUpdatingAnAlreadyInvalidLegacyDocument() {
        // Legacy được seed TRƯỚC khi bật validator.
        Document legacy = validOrder("ORD-LEGACY-STRICT");
        legacy.remove("status");
        collection().insertOne(legacy);

        configure("strict", "error");

        assertThatThrownBy(() -> collection().updateOne(
            Filters.eq("_id", "ORD-LEGACY-STRICT"),
            Updates.set("note", "attempted")))
            .isInstanceOf(MongoWriteException.class);

        Document stored = findById("ORD-LEGACY-STRICT");
        assertThat(stored).isNotNull();
        assertThat(stored.containsKey("note")).isFalse();
        assertThat(stored.containsKey("status")).isFalse();
    }

    @Test
    void moderateErrorAllowsUpdatingExistingInvalidLegacyDocument() {
        Document legacy = validOrder("ORD-LEGACY-MODERATE");
        legacy.remove("status");
        collection().insertOne(legacy);

        configure("moderate", "error");

        UpdateResult updated = collection().updateOne(
            Filters.eq("_id", "ORD-LEGACY-MODERATE"),
            Updates.set("note", "permitted-in-moderate"));

        assertThat(updated.getMatchedCount()).isEqualTo(1L);
        assertThat(findById("ORD-LEGACY-MODERATE")
            .getString("note"))
            .isEqualTo("permitted-in-moderate");

        // moderate vẫn kiểm tra INSERT mới.
        Document newInvalid = validOrder("ORD-NEW-INVALID");
        newInvalid.remove("status");
        assertThatThrownBy(
            () -> collection().insertOne(newInvalid))
            .isInstanceOf(MongoWriteException.class);
    }

    @Test
    void moderateErrorStillProtectsValidDocumentsFromBecomingInvalid() {
        configure("moderate", "error");
        collection().insertOne(validOrder("ORD-VALID"));

        // Document ĐANG hợp lệ nên update vẫn bị kiểm tra.
        assertThatThrownBy(() -> collection().updateOne(
            Filters.eq("_id", "ORD-VALID"),
            Updates.unset("status")))
            .isInstanceOf(MongoWriteException.class);

        assertThat(findById("ORD-VALID").getString("status"))
            .isEqualTo("NEW");
    }

    @Test
    void strictWarnAllowsInvalidDocumentToBeWritten() {
        configure("strict", "warn");

        Document missingStatus = validOrder("ORD-WARN");
        missingStatus.remove("status");
        collection().insertOne(missingStatus);

        // Không exception: warn KHÔNG chặn ghi sai.
        assertThat(findById("ORD-WARN")).isNotNull();
        assertThat(findById("ORD-WARN")
            .containsKey("status")).isFalse();

        // Cảnh báo nằm phía MongoDB server logs;
        // test này không giả định driver trả warning riêng.
    }

    @Test
    void strictErrorRejectsUnsetOnExistingValidDocument() {
        configure("strict", "error");
        collection().insertOne(validOrder("ORD-UNSET"));

        assertThatThrownBy(() -> collection().updateOne(
            Filters.eq("_id", "ORD-UNSET"),
            Updates.unset("tenantId")))
            .isInstanceOf(MongoWriteException.class);

        assertThat(findById("ORD-UNSET")
            .getString("tenantId"))
            .isEqualTo("TENANT-A");
    }

    @Test
    void collectionOptionsAreStoredOnMongoDbServer() {
        configure("strict", "error");

        Document info = template.getDb()
            .listCollections()
            .filter(Filters.eq("name", "orders"))
            .first();

        assertThat(info).isNotNull();
        Document options = info.get("options", Document.class);
        assertThat(options).isNotNull();
        assertThat(options.getString("validationLevel"))
            .isEqualTo("strict");
        assertThat(options.getString("validationAction"))
            .isEqualTo("error");
        assertThat(options).containsKey("validator");
    }
}
```

**Cảnh báo bắt buộc:** `collection().drop()` trong `@BeforeEach` **xóa toàn bộ collection `orders` của database hiện đang kết nối**. Chỉ chạy khi test profile chắc chắn dùng một MongoDB/database **cô lập**, không dùng chung với developer khác và tuyệt đối không trỏ production. Nếu test chạy song song trên cùng database, các lần drop có thể tranh chấp; cấu hình test isolation theo từng class/job.

Ở đây không kiểm tra mọi giá trị trả về của MongoDB logs trong test `warn` vì cảnh báo validator thuộc phía server. Trong production, phải cấu hình giám sát logs/metrics phù hợp, không coi một insert thành công là bằng chứng validator đã cho phép dữ liệu theo hợp đồng.

### 15.2. Những điểm test đã chứng minh

| Test | Bảo đảm kiểm tra |
| --- | --- |
| `strictErrorAcceptsValid...` | Document đủ schema được ghi; thiếu field required bị reject |
| `requiredPlusBsonType...` | `null`, String/Int32 không được xem là BSON String/Long hợp lệ |
| `strictErrorRejectsUpdating...` | Legacy invalid bị strict kiểm tra khi update |
| `moderateErrorAllowsUpdating...` | Legacy invalid có thể cập nhật trong moderate, nhưng insert invalid mới vẫn bị chặn |
| `moderateErrorStillProtects...` | Document đã hợp lệ không được cập nhật thành invalid |
| `strictWarnAllowsInvalid...` | Warn không chặn ghi vi phạm |
| `strictErrorRejectsUnset...` | Update cũng phải giữ required |
| `collectionOptionsAreStored...` | Cấu hình thật trên MongoDB có validator, level, action |

### 15.3. Kiểm thử ứng dụng Spring Data

Sau khi raw-driver tests đã chứng minh server hoạt động, cần thêm test gọi `MongoTemplate.insert(...)` hoặc `OrderRepository.save(...)` với entity hợp lệ/sai. Ví dụ:

```java
OrderDocument valid = new OrderDocument(
    "ORD-SPRING",
    "TENANT-A",
    "A-SPRING",
    "NEW",
    50000L,
    Instant.parse("2026-11-20T02:00:00Z"));

template.insert(valid);

Document stored = template.getCollection("orders")
    .find(new Document("_id", "ORD-SPRING"))
    .first();

assertThat(stored).isNotNull();
assertThat(stored.get("totalMinor"))
    .isInstanceOf(Long.class);
assertThat(stored.get("createdAt"))
    .isInstanceOf(Date.class);
```

Đoạn này là **một phần trong test được đặt đúng context**, với `template`, `OrderDocument`, `Instant`, `Date` và `assertThat` đã import. Test có thể thất bại nếu converter thực tế khác mong đợi; đó chính là mục tiêu: kiểm tra BSON mà application đã ghi có thỏa validator không.

### 15.4. Ma trận kiểm thử bổ sung

| Trường hợp | Kỳ vọng |
| --- | --- |
| `required` nhưng field String rỗng | `required` thỏa; cần `minLength` để chặn rỗng |
| Field optional null | Theo schema của field; optional không đồng nghĩa null hợp lệ |
| Object `metadata` có field required lồng nhau | Thiếu field con phải bị chặn khi object tồn tại |
| Field `_id` bị đổi kiểu bởi converter | Raw BSON và schema phải tương thích |
| String ISO date thay vì BSON Date | Bị từ chối với `bsonType:"date"` |
| `status` không thuộc enum | Bị từ chối khi validation áp dụng/action error |
| `totalMinor` âm | Bị từ chối do `minimum:0` |
| `moderate` cập nhật legacy từ invalid thành valid | Document có thể được sửa; update tiếp theo phải thỏa schema |
| `off` cho ghi sai | Chứng minh validator không còn chặn trong mức off |
| `strict+warn` cập nhật document sai | Ghi được, log warning nếu được kiểm tra và vi phạm |
| Writer có quyền bypass | Chỉ dùng khi được phép và có audit |
| Bulk nhiều document có một ghi lỗi | Không mặc định rollback toàn bộ nếu không có transaction |
| Đổi `collMod` giữa hai test/môi trường | Đọc lại level/action để tránh giả định |

## 16. Xử lý lỗi server trong service Java

Khi `validationAction:"error"`, write bị từ chối ở server. Tùy gọi qua driver thô, `MongoTemplate` hay repository, application có thể nhận loại exception khác nhau do **Spring Data exception translation**.

Vì vậy, service nên:

1. Xác nhận đây là lỗi validation bằng **thông tin có cấu trúc** mà driver/Spring cung cấp (ví dụ lỗi server code `121` khi xuất hiện), thay vì chỉ so sánh thông báo lỗi nguyên văn.
2. Không báo thao tác thành công hoặc ghi event nghiệp vụ thành công khi insert/update thực tế thất bại.
3. Trả lỗi client phù hợp, thông thường phản ánh request không đáp ứng schema, nhưng không tiết lộ validator nội bộ nhạy cảm.
4. Giữ ID/correlation ID để điều tra writer nào gây lỗi; log thông tin an toàn.
5. Phân biệt validation error với duplicate key `11000`, write concern failure, network timeout và optimistic-lock conflict; chúng đòi hỏi cách xử lý khác nhau.

### 16.1. Một phản ví dụ không nên làm

```java
// PHẢN VÍ DỤ: bắt mọi lỗi ghi và coi là bị trùng mã.
try {
    repository.save(order);
} catch (RuntimeException ex) {
    throw new IllegalArgumentException(
        "Đơn hàng đã tồn tại", ex);
}
```

Đoạn này trộn lẫn duplicate key, validator, kết nối và lỗi vận hành. Một request thiếu `status` không phải “đơn hàng đã tồn tại”. Cần có lớp xử lý lỗi theo loại thực, không giả định mọi exception khi ghi MongoDB là một conflict giống nhau.

### 16.2. Không log toàn bộ document lỗi

Thông tin validator có thể chứa tên field hoặc một phần dữ liệu vi phạm. Hãy hạn chế log các trường định danh nội bộ, loại lỗi và correlation ID; không đẩy payload chứa thông tin cá nhân, token hoặc trường nhạy cảm ra log giám sát không được kiểm soát.

## 17. Những hiểu nhầm thường gặp về schema validation

| Hiểu nhầm | Sự thật |
| --- | --- |
| `required: ["status"]` cấm cả giá trị null | `required` chỉ yêu cầu field hiện diện; cần `bsonType`/constraint để cấm null |
| Field có `properties.status.bsonType:"string"` là tự bắt buộc | `properties` kiểm tra kiểu nếu field có mặt; phải đưa `status` vào `required` nếu không cho phép thiếu |
| `validationLevel:"moderate"` chỉ log và vẫn cho mọi ghi | Moderate quyết định **những update nào bị kiểm tra**; `validationAction` mới quyết định reject/warn |
| `moderate + error` cho phép insert mới sai schema | Insert mới vẫn được kiểm tra và sẽ bị từ chối |
| `moderate + error` không bao giờ chặn update | Update trên document vốn hợp lệ vẫn bị kiểm tra |
| `strict` sẽ tự sửa mọi document legacy | Không; nó áp quy tắc vào ghi tiếp theo |
| `warn` nghĩa là ghi sai bị chặn và có log | `warn` cho phép ghi vi phạm, đồng thời ghi cảnh báo |
| `validationLevel:"off"` xóa schema khỏi collection | Validator vẫn có thể tồn tại, nhưng việc kiểm tra bị bỏ qua |
| Chỉ `insert` bị validate, `$set` được miễn | Các update thuộc phạm vi validation được đánh giá theo trạng thái document sau ghi |
| `@Document` tự cài validator ở server | Không; cần cấu hình collection rõ ràng |
| `@NotNull` bảo vệ mọi writer ngoài Java | Không; Bean Validation được áp ở JVM theo đường gọi |
| `bsonType:"long"` chấp nhận mọi số nguyên | Nó chỉ chấp nhận BSON Int64, không tự đồng nhất Int32/String |
| Validator bảo đảm `orderNo` duy nhất | Unique key là trách nhiệm của unique index phù hợp |
| Validator bảo đảm caller chỉ được ghi tenant của mình | Authorization và tenant-scoped query phải được thực hiện riêng |
| Bật `additionalProperties:false` luôn tốt hơn | Có thể chặn `_class`, metadata mở rộng và producer hợp lệ |
| Driver báo insert thành công nghĩa là validator pass | Trong chế độ `warn`, ghi sai schema vẫn có thể thành công |
| Đổi `collMod` nghĩa là document cũ đã hợp lệ | Cần kiểm kê, migration và xác minh riêng |

### 17.1. Default không nên bị hiểu ngầm

Khi không chỉ định các tùy chọn, MongoDB có giá trị mặc định theo server cho validation level/action; các triển khai thông dụng mặc định tương ứng `strict` và `error`. Dù vậy, trong tài liệu triển khai và migration nên **đặt tường minh** hai option này để tránh việc reviewer phải đoán trạng thái, đồng thời **đọc lại cấu hình từ collection**.

### 17.2. BSON validator không phải JSON Schema đầy đủ trên web

MongoDB `$jsonSchema` sử dụng cú pháp JSON Schema được điều chỉnh cho BSON và tập keyword được hỗ trợ bởi phiên bản server. Không được dán một schema từ công cụ JSON Schema/HTTP API rồi kỳ vọng mọi keyword đều chạy trong MongoDB. Ví dụ `bsonType` là đặc trưng dành cho BSON; một số keyword quen thuộc ở JSON Schema tiêu chuẩn có thể không được hỗ trợ hoặc khác nghĩa.

Trong dự án có schema tự động sinh từ Java, hãy kiểm tra output BSON, các enum/kiểu lồng nhau và hành vi thực tế bằng integration tests. Không đặt niềm tin vào tên class tạo schema mà không xem được validator trên MongoDB.

## 18. Hiệu năng, index và giới hạn triển khai

Validation phía server bổ sung công việc cho các lệnh insert/update bị kiểm tra. Schema càng phức tạp, tài liệu càng lớn, lượng ghi càng cao thì chi phí kiểm tra có thể càng đáng kể. **Không có quy tắc chung rằng validation luôn chậm hoặc nhanh**, cần đo trên workload đại diện.

### 18.1. Những gì nên đo

- Throughput và latency của insert/update/replace trước và sau khi bật validator.
- Tỷ lệ lỗi validator theo collection, writer, phiên bản dịch vụ và loại trường bị vi phạm.
- Số lượng legacy invalid còn lại và tốc độ backfill.
- Chi phí bulk write và tình trạng **thành công một phần** khi một operation vi phạm.
- Tác động của collection schema mới lên migration, import và các job xử lý dữ liệu.
- Kích thước tài liệu, độ sâu array/object và số field phải kiểm tra.

### 18.2. Validator không thay thế index

Một điều kiện như `tenantId` là String không rỗng **không giúp tìm theo tenant nhanh hơn**. Nếu API thường truy vấn:

```javascript
db.orders.find({
  tenantId: "TENANT-A",
  status: "PAID"
})
```

cần phân tích index theo mẫu đọc, chẳng hạn ứng viên:

```javascript
db.orders.createIndex(
  { tenantId: 1, status: 1 },
  { name: "idx_tenant_status" }
)
```

Đây là index cho **hiệu năng truy vấn**, không phải schema validator. Tạo index cần cân nhắc chi phí ghi và đo bằng `explain("executionStats")` trên dữ liệu đại diện.

### 18.3. Kiểm tra schema không tự bảo đảm tính nhất quán đa document

Nếu một thao tác tạo Order đồng thời tạo Payment ở collection khác, validator chỉ kiểm tra **document thuộc collection có validator**. Nó không đảm bảo cả hai ghi được commit cùng nhau. Nếu cần atomicity đa document, phải thiết kế MongoDB transaction (khi deployment hỗ trợ) hoặc cơ chế eventual consistency/outbox phù hợp.

Validator cũng không tự cập nhật `@Version`, ngăn lost update giữa hai writer hoặc triển khai kiểm soát chuyển trạng thái nghiệp vụ. Các trường hợp đó cần expected-version/CAS, transaction hoặc service state machine riêng.

### 18.4. Schema quá nghiêm có thể chặn tiến hóa dữ liệu

Ví dụ một service mới bổ sung field `shippingPreferences`. Nếu validator có `additionalProperties:false` và chưa cho phép field mới, service đó có thể bị từ chối ghi. Khi thay đổi schema:

1. Lập kế hoạch tương thích **reader cũ / writer mới**.
2. Mở rộng schema cho phép field mới trước khi writer bắt đầu gửi.
3. Giữ các field cũ trong giai đoạn chuyển tiếp.
4. Backfill và kiểm thử dữ liệu nếu ràng buộc `required` mới được thêm.
5. Chỉ siết schema sau khi toàn bộ writer và reader đã được điều phối.

Đây là cách triển khai **expand → migrate → contract**, phù hợp khi có nhiều service cùng sử dụng collection.

## 19. Checklist vận hành trước khi bật strict + error

1. **Hợp đồng rõ ràng:** xác định field bắt buộc, field tùy chọn, nullable, enum, kiểu BSON và unit tiền.
2. **Đã kiểm kê schema hiện tại:** có bao nhiêu document missing/null/sai kiểu, thuộc writer nào.
3. **Đã xác minh collection thật:** cấu hình trong `listCollections` đúng với migration dự kiến.
4. **Không nhầm null với missing:** required và bsonType đều được kiểm thử.
5. **Không quên nested objects:** required phải đặt đúng cấp và không mở rộng validation vô ý.
6. **Có kế hoạch legacy:** biết update nào sẽ bị strict chặn và cần sửa dữ liệu như thế nào.
7. **Tất cả writer phù hợp:** Java repository, raw driver, import, batch, integration, script vận hành.
8. **Có regression tests:** insert, update, replace, bulk, null, sai BSON, strict/moderate/warn.
9. **Có giám sát warn:** không chỉ dựa vào status thành công của driver.
10. **Có phân quyền bypass:** tài khoản thông thường không được tùy ý bypass.
11. **Có phân biệt unique/index:** validator không bảo đảm ID business key duy nhất.
12. **Có rollback có kiểm soát:** biết cách đổi lại policy và audit dữ liệu sinh trong cửa sổ rollback.
13. **Có phương án schema evolution:** ghi field mới, backfill, bỏ field cũ đúng thứ tự.
14. **Có đo chi phí ghi:** đảm bảo validation overhead chấp nhận được trong tải thật.
15. **Không dùng production cho test:** đặc biệt các test có `drop()`, `deleteMany` hoặc `collMod`.

## 20. Bài tập vận dụng

Một hệ thống quản lý tồn kho sử dụng collection `stock_movements`. Mỗi document có dạng:

```javascript
{
  _id: "MOVE-001",
  tenantId: "TENANT-X",
  sku: "SKU-001",
  movementType: "IN",
  quantity: NumberLong(10),
  occurredAt: ISODate("2026-11-20T02:00:00Z"),
  source: {
    system: "warehouse",
    batchId: "IMPORT-18"
  }
}
```

Yêu cầu:

1. Viết `$jsonSchema` bắt buộc `tenantId`, `sku`, `movementType`, `quantity`, `occurredAt`. Yêu cầu `tenantId/sku` là String không rỗng, `quantity` là BSON Int64 dương, `occurredAt` là BSON Date.
2. Giới hạn `movementType` trong `IN`, `OUT`, `ADJUST`. Giải thích vì sao `required` không thay thế `enum`.
3. `source` được phép thiếu; nếu tồn tại, bắt buộc `source.system`. Viết `required` ở đúng cấp.
4. Tạo collection với `validationLevel:"strict"`, `validationAction:"error"`.
5. Thử insert document thiếu `sku`, `sku:null`, `sku:""`, `quantity:"10"` và `quantity:NumberLong(-1)`. Dự đoán ràng buộc nào gây lỗi.
6. Giả sử trước khi bật validator đã có document thiếu `movementType`. So sánh hành vi của `strict+error` và `moderate+error` khi chạy `$set:{note:"reviewed"}` trên document ấy.
7. Dùng `collMod` đổi sang `strict+warn`, thử ghi document không hợp lệ và chỉ rõ vì sao driver có thể báo thành công.
8. Viết truy vấn audit dùng `$nor + $jsonSchema` để đếm document sai schema.
9. Viết `MongoTemplate` migration helper đổi level/action; đọc lại options để xác nhận cấu hình đã áp vào server.
10. Viết integration test kiểm tra document hợp lệ, sai type, legacy invalid và update làm thiếu required; bảo đảm chạy trên test database.
11. Thiết kế rollout nhiều phiên bản khi một warehouse service cũ ghi `quantity` là BSON Int32 và service mới ghi BSON Int64.
12. Đề xuất một unique key/index phù hợp nếu mỗi `movementId` phải duy nhất theo tenant, rồi giải thích vì sao validator không đủ thay thế index.

### 20.1. Gợi ý schema

```javascript
const movementSchema = {
  bsonType: "object",
  required: [
    "tenantId", "sku", "movementType", "quantity", "occurredAt"
  ],
  properties: {
    tenantId: { bsonType: "string", minLength: 1 },
    sku: { bsonType: "string", minLength: 1 },
    movementType: {
      bsonType: "string",
      enum: ["IN", "OUT", "ADJUST"]
    },
    quantity: { bsonType: "long", minimum: 1 },
    occurredAt: { bsonType: "date" },
    source: {
      bsonType: "object",
      required: ["system"],
      properties: {
        system: { bsonType: "string", minLength: 1 },
        batchId: { bsonType: "string" }
      }
    }
  }
};
```

Schema này mô tả `quantity` dương cho mọi loại movement. Nếu nghiệp vụ `ADJUST` cần cho phép giá trị âm, phải thay hợp đồng thành kiểm tra có điều kiện theo `movementType`, hoặc thiết kế field `direction` tách biệt. Không sửa thành `minimum:-999999` chỉ để làm test xanh khi chưa chốt ý nghĩa nghiệp vụ.

## 21. Tài liệu tham khảo

- MongoDB Manual — [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/): tổng quan kiểm tra document khi ghi.
- MongoDB Manual — [Specify Validation Level](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-level/): `strict`, `moderate` và hành vi với document legacy.
- MongoDB Manual — [Specify Validation Action](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-action/): cách phản ứng với vi phạm validator.
- MongoDB Manual — [`$jsonSchema`](https://www.mongodb.com/docs/manual/reference/operator/query/jsonSchema/): cú pháp schema và các keyword.
- MongoDB Manual — [`db.createCollection()`](https://www.mongodb.com/docs/manual/reference/method/db.createCollection/): tạo collection với validator và options.
- MongoDB Manual — [`collMod`](https://www.mongodb.com/docs/manual/reference/command/collMod/): thay đổi cấu hình collection.
- MongoDB Manual — [`bypassDocumentValidation`](https://www.mongodb.com/docs/manual/core/schema-validation/bypass-document-validation/): ngoại lệ kiểm tra document và quyền sử dụng.
- Spring Data MongoDB — [Reference Documentation](https://docs.spring.io/spring-data/mongodb/reference/): MongoTemplate, mapping, collection schema và integration với MongoDB.
- Spring Data MongoDB — [MongoTemplate API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoTemplate.html): thực thi thao tác dữ liệu, truy cập database và các API liên quan.

## Ghi nhớ

**`required` định nghĩa field phải có; `validationLevel` quyết định insert/update nào được kiểm tra; `validationAction` quyết định vi phạm bị từ chối hay chỉ cảnh báo.** Trong MongoDB, `required` **không tự cấm null** nếu không có ràng buộc kiểu; `strict` đánh giá update trên cả document legacy đang sai, còn `moderate` cho phép cập nhật document vốn đã sai mà không áp kiểm tra validator, nhưng vẫn kiểm tra insert mới và update trên document vốn hợp lệ. `warn` cho phép ghi vi phạm nên không thay cho `error`. Khi dùng Spring Data MongoDB, phải kiểm tra BSON thật, vận hành validator bằng migration có kiểm soát, audit/backfill dữ liệu cũ và xác minh cấu hình server trước khi bật chính sách nghiêm ngặt trên production.

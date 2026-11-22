# Lỗi schema validation, sai kiểu BSON và giá trị không thể chuyển đổi

MongoDB cho phép dữ liệu dạng document linh hoạt, nhưng **linh hoạt không đồng nghĩa mọi giá trị đều hợp lệ trong mọi ngữ cảnh**. Một ứng dụng có thể ghi được document chứa `amount: "149000"` hôm qua, rồi hôm nay bị từ chối khi triển khai `$jsonSchema` yêu cầu `amount` là Decimal128. Một phép aggregation có thể chạy tốt trên 999.999 records nhưng dừng ở record thứ một triệu vì `$toDate` không hiểu chuỗi `"31/02/2026"`. Một Java service có thể đọc được dữ liệu bằng `mongosh` nhưng `ClassCastException` khi gọi `Document.getLong("quantity")` với document thực chứa BSON Int32.

Những lỗi đó trông giống nhau ở tầng API — HTTP 500, import thất bại, job dừng hoặc write bị từ chối — nhưng **nguyên nhân và cách xử lý hoàn toàn khác nhau**:

- **Schema validation:** MongoDB server từ chối insert/update vì document không đáp ứng validator của collection.
- **Sai kiểu BSON:** dữ liệu có BSON type khác với type mà query, index, aggregation, driver hoặc ứng dụng trông đợi.
- **Không thể chuyển đổi:** dữ liệu đầu vào không thể chuyển sang type đích, vượt phạm vi cho phép hoặc có biểu diễn không hợp lệ.
- **Codec/mapping lỗi:** Java Driver hoặc Spring Data không thể encode/decode hay chuyển đổi dữ liệu sang class Java tương ứng.

Bài học **“Lỗi schema validation, sai kiểu BSON và giá trị không thể chuyển đổi”** thuộc chương **Xử lý sự cố** hướng dẫn quy trình điều tra, tìm document sai kiểu, phân biệt những loại lỗi dễ nhầm, sửa dữ liệu theo lô, triển khai schema constraints an toàn và kiểm thử để ngăn tái phát.

> **Nguyên tắc xử lý:** Trước khi sửa, phải biết lỗi xảy ra ở đâu, document nào vi phạm, validator/operation nào đang áp dụng và giá trị đầu vào nào không thể chuyển đổi. Không tắt validator, gọi `bypassDocumentValidation` hoặc ép kiểu hàng loạt chỉ để hết thông báo lỗi.

---

## 1. Ba tầng lỗi thường gặp

Một luồng xử lý:

```text
HTTP / Worker / Import Job
           │
           ▼
Java application / Spring Data
           │
      BSON encode
           │
           ▼
MongoDB command
           │
      Query / Update
           │
      Schema validator
           │
           ▼
Storage / Replication
           │
      BSON decode
           │
           ▼
Application result
```

Lỗi có thể xuất hiện ở **bất kỳ tầng nào**.

| Hiện tượng | Nơi phát sinh thường gặp | Ví dụ |
|---|---|---|
| `Document failed validation` | MongoDB server | `amount` là String nhưng validator yêu cầu Decimal128 |
| `ConversionFailure` hoặc lỗi `$to*` | Aggregation/update pipeline | `$toInt("N/A")` |
| `Cannot apply $inc ... non-numeric` | MongoDB update execution | `$inc` trên field String |
| `ClassCastException` | Java application | `getLong()` với BSON Int32 |
| `CodecConfigurationException` | MongoDB Java Driver | Chưa có codec cho POJO/custom type |
| `MappingException`/conversion error | Spring Data mapping | Field BSON không phù hợp Java property |
| `DuplicateKey` | Unique index | Giá trị business key trùng |
| JSON parse error | Import/export hoặc app parser | Extended JSON bị xử lý như JSON thường |
| Insert too large | BSON document/message limit | Document vượt kích thước hỗ trợ |

Không coi tất cả là schema validation: unique index, authorization, document size, malformed BSON và application mapping là những cơ chế riêng.

## 2. Triệu chứng từ góc nhìn người vận hành

Một số dấu hiệu:

```text
HTTP 400/422 hoặc 500 tăng đột ngột
Bulk import dừng ở một số record cụ thể
MongoDB write code 121
Aggregation chạy lâu rồi báo không chuyển được kiểu
Một số tenant gặp lỗi, tenant khác bình thường
Dữ liệu mới ghi được nhưng batch cập nhật lịch sử thất bại
Deployment Spring Data mới bắt đầu decode lỗi
Dashboard tổng tiền thay đổi sau backfill
```

Cần tránh việc thấy “cùng API bị lỗi” rồi kết luận nguyên nhân nằm ở MongoDB Server. Kiểm tra **trace của request, driver exception và command** để xác định chính xác tầng phát sinh.

### 2.1. Phân loại nhanh theo thời điểm

- **Ngay trước khi gửi command:** có thể là input validation, serializer, BSON codec.
- **Trong insert/update trên server:** validator, unique index, update operator hoặc authorization.
- **Trong aggregation:** `$convert`, `$to*`, `$dateFromString`, `$arrayToObject`, arithmetic.
- **Khi nhận kết quả ở Java:** codec/POJO mapping, cast type, null.
- **Chỉ khi backfill dữ liệu cũ:** dữ liệu hỗn hợp kiểu hoặc legacy records.
- **Chỉ sau khi đổi validator:** schema mới chưa tương thích với dữ liệu/write paths cũ.

Phân loại này giúp chọn công cụ chẩn đoán thay vì thay mọi thứ cùng lúc.

## 3. Quy trình ứng cứu trong 15 phút đầu

Khi một luồng ghi quan trọng đột ngột thất bại:

1. **Xác định phạm vi:** database, collection, tenant, endpoint, tỷ lệ lỗi.
2. **Giữ bằng chứng:** timestamp, trace ID, server version, operation type, error code/name và thông tin validator có thể đọc được.
3. **Kiểm tra thay đổi gần đây:** application release, validator `collMod`, migration, driver/schema version, imports.
4. **Phân biệt lỗi có thể retry và lỗi dữ liệu vĩnh viễn:** không retry vô hạn record sai.
5. **Giảm tác động:** pause import job có lỗi, giới hạn traffic lỗi hoặc rollback release theo phương án được hỗ trợ.
6. **Đọc metadata và dữ liệu mẫu an toàn:** không dump toàn bộ PII vào logs.
7. **Chạy truy vấn tìm lớp dữ liệu bị ảnh hưởng** trên môi trường được phép.
8. **Xác định remediation:** sửa producer, sửa mapper, chuyển đổi legacy data, hoặc thay validator theo business contract.
9. **Kiểm thử trên staging với fixture lỗi thật đã được ẩn danh.**
10. **Theo dõi và đối soát lại trước khi đóng incident.**

Không chỉnh collection validator hoặc chạy `updateMany` trên production chỉ vì đã nhận code 121.

## 4. Tình huống mẫu xuyên suốt

Collection `commerce.orders` có các document:

```javascript
{
  _id: "ORD-1001",
  tenantId: "T-01",
  orderNo: "A-1001",
  amount: NumberDecimal("249900.00"),
  quantity: NumberInt(2),
  status: "PAID",
  createdAt: ISODate("2026-11-14T04:00:00Z")
}
```

Nhưng dữ liệu legacy có thể là:

```javascript
{
  _id: "ORD-1002",
  tenantId: "T-01",
  orderNo: "A-1002",
  amount: "249900",
  quantity: "2",
  status: "paid",
  createdAt: "14/11/2026 11:00"
}
```

Và dữ liệu nhập lỗi:

```javascript
{
  _id: "ORD-1003",
  tenantId: "T-02",
  orderNo: "A-1003",
  amount: "không có",
  quantity: 1.5,
  status: null,
  createdAt: "2026-13-40"
}
```

Mục tiêu:

- `amount` là BSON Decimal128 và không âm;
- `quantity` là số nguyên thích hợp với domain;
- `status` thuộc tập enum được phê duyệt;
- `createdAt` là BSON Date;
- `tenantId`, `orderNo` là String không rỗng theo nghiệp vụ;
- Mọi chuyển đổi đều có audit, không làm sai tiền hoặc ngày.

Những ví dụ dưới đây dùng **collection thử nghiệm**, không yêu cầu sửa production.

## 5. MongoDB lưu type theo BSON, không theo kiểu nhìn trên màn hình

BSON có các types như:

| BSON type | Ví dụ mongosh | Type trong Java thường gặp |
|---|---|---|
| String | `"249900"` | `String` |
| Int32 | `NumberInt(2)` | `Integer` |
| Int64 | `NumberLong("9007199254740993")` | `Long` |
| Double | `2.5` | `Double` |
| Decimal128 | `NumberDecimal("249900.00")` | `Decimal128` |
| Boolean | `true` | `Boolean` |
| Date | `ISODate("2026-11-14T04:00:00Z")` | `java.util.Date` hoặc mapping thích hợp |
| ObjectId | `ObjectId("507f1f77bcf86cd799439011")` | `ObjectId` |
| Array | `["a", "b"]` | `List<?>` |
| Object | `{a: 1}` | `Document` hoặc POJO |
| Null | `null` | `null` |
| Binary | `BinData(...)` | `Binary`, UUID tùy representation |
| Timestamp | BSON Timestamp | `BsonTimestamp` |

**Giá trị `"123"` không phải số 123** chỉ vì giao diện hiển thị các ký tự số. `ISODate(...)` cũng không tương đương một String trông giống ISO 8601.

### 5.1. `NumberInt`, `NumberLong`, `NumberDecimal`

MongoDB có nhiều kiểu số; ứng dụng phải hiểu range và độ chính xác:

- **Int32:** số nguyên 32-bit có dấu.
- **Int64:** số nguyên 64-bit có dấu.
- **Double:** floating-point nhị phân, có giới hạn độ chính xác.
- **Decimal128:** dạng decimal phù hợp những trường hợp cần decimal semantics.

Dùng `Double` cho tiền có thể gây lỗi làm tròn; dùng `Int32` cho count lớn có thể bị overflow; dùng JavaScript Number cho Int64 rất lớn có thể mất chính xác.

### 5.2. Int64 và JavaScript Number

Giá trị:

```javascript
NumberLong("9007199254740993")
```

lớn hơn số nguyên an toàn tối đa của IEEE 754 double (`2^53 - 1`). Nếu một script xuất/nhập chuyển giá trị đó thành JavaScript Number thông thường, giá trị có thể bị làm tròn.

Không dùng `JSON.stringify`/`JSON.parse` thông thường như một cơ chế bảo toàn mọi BSON type.

## 6. Schema validation hoạt động như thế nào?

MongoDB hỗ trợ **collection-level validation rules**, thường dùng `$jsonSchema` hoặc query expressions theo tính năng được hỗ trợ.

Một validator có thể yêu cầu:

- Document là object;
- Những fields bắt buộc tồn tại;
- Field có `bsonType` mong muốn;
- Các giá trị thuộc enum;
- Chuỗi có độ dài/pattern phù hợp;
- Số nằm trong min/max;
- Array có items đúng type;
- Nested object có cấu trúc xác định.

Ví dụ validator:

```javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["tenantId", "orderNo", "amount", "createdAt"],
    properties: {
      tenantId: { bsonType: "string" },
      orderNo: { bsonType: "string" },
      amount: {
        bsonType: "decimal",
        minimum: NumberDecimal("0")
      },
      quantity: { bsonType: "int" },
      createdAt: { bsonType: "date" },
      status: {
        enum: ["NEW", "PAID", "CANCELLED"]
      }
    }
  }
}
```

**Một field không có trong `required` có thể không tồn tại**, ngay cả khi `properties` mô tả type cần dùng khi field xuất hiện.

### 6.1. MongoDB `$jsonSchema` không phải mọi tính năng JSON Schema

MongoDB triển khai một tập các toán tử/keywords được hỗ trợ cho BSON; không tự giả định mọi keyword của chuẩn JSON Schema bên ngoài đều hợp lệ. Dùng đúng tài liệu MongoDB Server version đang chạy.

### 6.2. Validator và unique index khác nhau

`$jsonSchema` có thể quy định `orderNo` là String, nhưng không tự ngăn hai documents có cùng `(tenantId, orderNo)`. **Unique index** là một cơ chế riêng cho uniqueness và cần test riêng.

## 7. Tạo collection thử nghiệm có validator

**Chỉ chạy trên database staging hoặc lab riêng đã được phép tạo dữ liệu.**

```javascript
const lab = db.getSiblingDB("schema_validation_lab");

lab.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["tenantId", "orderNo", "amount", "createdAt"],
      properties: {
        tenantId: {
          bsonType: "string",
          minLength: 1
        },
        orderNo: {
          bsonType: "string",
          minLength: 1
        },
        amount: {
          bsonType: "decimal",
          minimum: NumberDecimal("0")
        },
        quantity: {
          bsonType: "int",
          minimum: 1
        },
        status: {
          enum: ["NEW", "PAID", "CANCELLED"]
        },
        createdAt: {
          bsonType: "date"
        },
        tags: {
          bsonType: "array",
          items: { bsonType: "string" }
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

Thử ghi bản hợp lệ:

```javascript
lab.orders.insertOne({
  _id: "TEST-OK-001",
  tenantId: "T-01",
  orderNo: "A-1001",
  amount: NumberDecimal("249900.00"),
  quantity: NumberInt(2),
  status: "PAID",
  createdAt: new Date(),
  tags: ["priority"]
});
```

Thử bản sai:

```javascript
lab.orders.insertOne({
  _id: "TEST-BAD-001",
  tenantId: "T-01",
  orderNo: "A-1002",
  amount: "249900",
  quantity: "2",
  status: "paid",
  createdAt: "2026-11-14"
});
```

Bản thứ hai vi phạm nhiều rules và phải bị từ chối khi validator/action áp dụng. **Không dùng trường hợp test này trên collection production.**

## 8. Đọc validator hiện có mà không thay đổi dữ liệu

Trước khi kết luận, cần xác nhận validator trên collection thực:

```javascript
db.getSiblingDB("commerce").getCollectionInfos({
  name: "orders"
});
```

Trong output, tìm:

```text
options.validator
options.validationLevel
options.validationAction
```

Có thể dùng command đọc metadata tương đương theo quyền/version phù hợp.

### 8.1. Vì sao phải đọc actual metadata?

Ứng dụng có thể khai báo schema Java/annotation nhưng database chưa triển khai validator đó. Ngược lại, DBA có thể đã dùng `collMod` tạo rule mới mà application release chưa biết.

Cần phân biệt:

```text
Desired schema trong source
          │
          ▼
Migration đã triển khai?
          │
          ▼
Actual collection validator
```

Chỉ trạng thái trên MongoDB server mới quyết định server sẽ từ chối write nào.

### 8.2. Ghi phiên bản

Lưu metadata về:

- MongoDB Server version/FCV;
- Cluster topology;
- Database/collection;
- Validator definition;
- Thời điểm thay đổi;
- Application release và driver;
- Các schema migration gần nhất.

Việc xảy ra lỗi sau release không chứng minh release đó gây lỗi nếu DB validator đã được thay đổi độc lập.

## 9. Ý nghĩa lỗi `DocumentValidationFailure` — code 121

Một lỗi phổ biến khi MongoDB từ chối document là:

```text
code: 121
codeName: DocumentValidationFailure
errmsg: Document failed validation
```

Đối với insert/update thuộc phạm vi validator, server có thể trả **validation details** trong thông tin lỗi, tùy phiên bản và đường gọi.

Ví dụ cấu trúc minh họa:

```javascript
{
  code: 121,
  codeName: "DocumentValidationFailure",
  errmsg: "Document failed validation",
  errInfo: {
    failingDocumentId: "TEST-BAD-001",
    details: {
      operatorName: "$jsonSchema",
      schemaRulesNotSatisfied: [
        {
          operatorName: "properties",
          propertiesNotSatisfied: [
            {
              propertyName: "amount",
              details: [
                {
                  operatorName: "bsonType",
                  specifiedAs: { bsonType: "decimal" },
                  reason: "type did not match",
                  consideredValue: "249900",
                  consideredType: "string"
                }
              ]
            }
          ]
        }
      ]
    }
  }
}
```

**Không phụ thuộc cứng vào cấu trúc ví dụ**: error details có thể thay đổi theo MongoDB version, driver và kiểu vi phạm. Thông tin lỗi có thể chứa **giá trị dữ liệu thật** trong `consideredValue`, nên không ghi toàn bộ raw exception ra log công khai.

### 9.1. Code 121 chỉ nói validator đã từ chối

Nó không tự nói **field nào phải sửa** nếu chưa đọc details/validator. Có thể lỗi do `required`, `bsonType`, enum, `additionalProperties`, `minimum`, nested objects, hoặc kết hợp rules.

### 9.2. Việc một lệnh insert lỗi không có nghĩa database bị hỏng

MongoDB đang thực thi chính sách dữ liệu. Hành động đúng có thể là sửa ứng dụng/record, không phải tắt validation.

### 9.3. Code 121 không phải duplicate key

Nếu bị unique index từ chối, thường thấy duplicate key error code riêng như `11000`. Cần điều tra unique constraint, không sửa bằng cách giảm nghiêm ngặt của `$jsonSchema`.

## 10. Chẩn đoán validation details theo từng cấp

Khi gặp lỗi có cấu trúc:

```text
$jsonSchema
  └── required
         └── missingProperties: ["tenantId"]
```

=> Dữ liệu thiếu field bắt buộc.

```text
$jsonSchema
  └── properties
         └── amount
               └── bsonType expected decimal, actual string
```

=> Sai type.

```text
$jsonSchema
  └── properties
         └── status
               └── enum mismatch
```

=> Giá trị ngoài tập cho phép.

```text
$jsonSchema
  └── properties
         └── items
               └── elementsNotSatisfied
```

=> Một hoặc nhiều phần tử array sai rule.

### 10.1. Tìm field gốc, không chỉ thông báo tổng

Nếu validator có nested object:

```javascript
shipping: {
  bsonType: "object",
  required: ["address"],
  properties: {
    address: {
      bsonType: "object",
      required: ["countryCode"],
      properties: {
        countryCode: { bsonType: "string" }
      }
    }
  }
}
```

Lỗi có thể nằm tại `shipping.address.countryCode`, không phải field `shipping` tổng thể. Lưu **property path** trong diagnostic đã được redact.

### 10.2. Lưu trace an toàn

Nên lưu:

```text
traceId
requestId
jobId
namespace
operation=insert/update/bulk
errorCode=121
schemaVersion
fieldPath (được cho phép)
expectedType
actualType
tenant scope (theo policy)
```

Không log toàn bộ document hoặc raw considered values nếu chứa PII, token, địa chỉ, thông tin thanh toán.

## 11. `validationLevel`: strict, moderate và off

MongoDB có các mức validation theo release:

| Level | Tư duy |
|---|---|
| `strict` | Kiểm tra các inserts và updates thuộc phạm vi, kể cả update đối với existing invalid docs |
| `moderate` | Kiểm tra inserts và updates trên những existing documents vốn đã hợp lệ; updates vào những existing invalid docs không bị áp validator theo cùng cách |
| `off` | Không áp dụng collection validation rules |

Mức `moderate` có thể giúp rollout validator trên collection chứa legacy invalid records, nhưng **không làm records cũ tự đúng**, và cũng có thể cho phép cập nhật records cũ tiếp tục ở trạng thái không hợp lệ.

### 11.1. `moderate` không phải schema repair

Một dữ liệu cũ:

```javascript
{ _id: 1, amount: "N/A" }
```

có thể tồn tại từ trước. `validationLevel: "moderate"` không biến `"N/A"` thành Decimal128. Nó chỉ thay cách rule được áp dụng với một số updates.

### 11.2. Khi nào cân nhắc moderate?

Trong một rollout có kiểm soát:

1. Xác định số lượng legacy invalid records.
2. Sửa write paths mới.
3. Dùng `moderate` tạm nếu có lý do nghiệp vụ và được phê duyệt.
4. Backfill/remediate dữ liệu cũ theo batch.
5. Đối soát invalid count về 0 theo contract.
6. Chuyển lên strict theo migration plan.
7. Theo dõi lỗi.

Không dùng moderate vĩnh viễn chỉ để che dữ liệu không nhất quán khi business yêu cầu strict.

## 12. `validationAction`: error, warn và tùy chọn theo phiên bản

MongoDB phân biệt **có kiểm tra schema không** và **điều gì xảy ra khi vi phạm**.

- `error`: từ chối write vi phạm validation.
- `warn`: cho phép write đi qua nhưng tạo cảnh báo tương ứng theo logging/observability.
- Một số release mới còn hỗ trợ lựa chọn báo lỗi và ghi log kết hợp; phải xác minh version trước khi dùng.

### 12.1. Chế độ warn hữu ích cho shadow validation

Một lộ trình:

```text
Deploy validator with warn
          │
          ▼
Observe violation rate
          │
          ▼
Fix producer and legacy cases
          │
          ▼
Test strict behavior in staging
          │
          ▼
Switch validationAction to error
```

Nhưng việc dùng `warn` có thể để dữ liệu sai tiếp tục được ghi. Chỉ phù hợp khi risk assessment chấp thuận và có kế hoạch kết thúc.

### 12.2. Không gọi warning log là báo cáo đầy đủ

Log có retention/sampling/quyền truy cập riêng; không tự đảm bảo mọi vi phạm đều có thể đếm chính xác nếu không thiết kế metrics/monitoring phù hợp. Dùng staging tests và kiểm chứng dữ liệu thực để xác nhận.

## 13. Điều chỉnh validator qua `collMod` là thay đổi production

Một lệnh ví dụ:

```javascript
db.runCommand({
  collMod: "orders",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["tenantId", "amount"],
      properties: {
        tenantId: { bsonType: "string" },
        amount: { bsonType: "decimal" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

**Không chạy lệnh này trên production chỉ để test.** `collMod` có thể thay đổi quy tắc chấp nhận writes của toàn collection.

### 13.1. Thay validator không tự sửa existing data

Một validator strict mới có thể được gắn vào collection vẫn chứa invalid legacy documents. Khi updates chạm các records đó, writes có thể bị từ chối.

### 13.2. Không triển khai validator trước khi cập nhật tất cả writers

Một ứng dụng API đã gửi Decimal128, nhưng một job import cũ vẫn gửi String. Nếu chuyển strict đột ngột, job sẽ thất bại.

Cần inventory:

- REST/API;
- Workers;
- Scheduled jobs;
- ETL/import;
- Admin scripts;
- Change stream processors;
- Third-party connectors;
- Test automation.

### 13.3. Validator migration phải có rollback riêng

Revert application code không tự revert database validator. Mọi thay đổi `collMod` nên có ID, owner, trước/sau definition, thời gian, audit và kế hoạch ứng phó.

## 14. `bypassDocumentValidation`: vì sao không dùng như cách chữa lỗi?

Một số MongoDB write commands và drivers có tùy chọn `bypassDocumentValidation` khi người gọi có privileges phù hợp.

Mục đích có thể là một số hoạt động migration/restore được kiểm soát, **không phải phương án mặc định để bỏ qua schema contract**.

### 14.1. Rủi ro

- Ghi records vi phạm business invariant;
- Ứng dụng mới không decode được;
- Updates về sau lại bị strict validator từ chối;
- Analytics/tổng tiền sai;
- Tạo nợ dữ liệu khó sửa;
- Mất audit nếu lạm dụng.

### 14.2. Khi nào mới cân nhắc?

Chỉ khi có kế hoạch rõ ràng:

- Dữ liệu phải được giữ nguyên để khôi phục/chuyển đổi;
- Có approval, access control;
- Có destination/namespace phù hợp;
- Có remediation plan sau import;
- Có validation/reconciliation về sau;
- Không dùng để vượt qua bảo mật hoặc ràng buộc nghiệp vụ.

### 14.3. Không bypass unique indexes bằng validator option

`bypassDocumentValidation` liên quan collection document validation, **không cho phép bỏ qua unique index, authorization hoặc mọi loại constraint**.

## 15. Phân biệt field missing và field null

Hai documents:

```javascript
{ _id: 1, amount: null }
{ _id: 2 }
```

khác nhau:

- Document 1 có field `amount` với giá trị BSON Null.
- Document 2 không có field `amount`.

Tác động:

- Required field rule kiểm tra **sự hiện diện**.
- `bsonType` kiểm tra type khi field có giá trị.
- Query equality `amount: null` có semantics đặc biệt liên quan null/missing.
- Partial indexes và application mapping có thể phân biệt hai trường hợp.

### 15.1. Tìm field missing

```javascript
db.orders.find({
  amount: { $exists: false }
});
```

### 15.2. Tìm explicit null

```javascript
db.orders.find({
  amount: { $type: "null" }
});
```

### 15.3. Tìm cả null và missing theo semantics query

```javascript
db.orders.find({
  amount: null
});
```

Không dùng filter thứ ba để đếm **chỉ explicit null**.

### 15.4. `required` không tự cấm null

Schema:

```javascript
required: ["amount"],
properties: {
  amount: { bsonType: ["decimal", "null"] }
}
```

cho phép field tồn tại với null. Nếu business yêu cầu Decimal128 không-null, chỉ khai báo `"decimal"` và bảo đảm `required`.

## 16. `$type` trong query và aggregation

`$type` là công cụ chủ lực để tìm dữ liệu sai kiểu.

### 16.1. Query chọn BSON type

```javascript
db.orders.find({
  amount: { $type: "string" }
});
```

```javascript
db.orders.find({
  quantity: { $type: "double" }
});
```

### 16.2. Báo cáo phân bố type bằng aggregation

```javascript
db.orders.aggregate([
  {
    $project: {
      amountType: { $type: "$amount" }
    }
  },
  {
    $group: {
      _id: "$amountType",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

Bản ghi không có `amount` được biểu diễn là type `"missing"` trong ngữ cảnh aggregation `$type`, giúp phân biệt với `"null"`.

### 16.3. Khác biệt với arrays

Trong query predicate, `$type` có những semantics đặc biệt khi field là array: có thể match nếu phần tử array thỏa type. Còn aggregation expression:

```javascript
{ $type: "$tags" }
```

trả về type của **giá trị field tổng thể**, ví dụ `"array"`.

Không dùng cùng một cách hiểu cho hai ngữ cảnh khi thống kê arrays chứa dữ liệu hỗn hợp.

### 16.4. Làm thống kê nhiều fields

```javascript
db.orders.aggregate([
  {
    $project: {
      amountType: { $type: "$amount" },
      quantityType: { $type: "$quantity" },
      createdAtType: { $type: "$createdAt" },
      statusType: { $type: "$status" }
    }
  },
  {
    $group: {
      _id: {
        amount: "$amountType",
        quantity: "$quantityType",
        createdAt: "$createdAtType",
        status: "$statusType"
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } },
  { $limit: 100 }
]);
```

Pipeline chỉ đọc nhưng có thể tốn CPU/I/O trên collection lớn. Chạy theo quy trình được phép, cân nhắc tenant/range filters và thời gian tải thấp.

## 17. Kiểm tra dữ liệu không đáp ứng `$jsonSchema`

`$jsonSchema` có thể được sử dụng như query predicate trong phạm vi MongoDB hỗ trợ. Trên môi trường thử hoặc dưới kế hoạch đọc dữ liệu phù hợp, có thể tìm documents không khớp schema:

```javascript
const expectedSchema = {
  bsonType: "object",
  required: ["tenantId", "amount"],
  properties: {
    tenantId: { bsonType: "string" },
    amount: { bsonType: "decimal" }
  }
};

db.orders.find({
  $nor: [
    { $jsonSchema: expectedSchema }
  ]
}).limit(20);
```

Lưu ý:

- Đây là **schema minh họa**, không nhất thiết trùng với validator thật;
- `limit(20)` chỉ lấy tối đa 20 kết quả, không chứng minh tổng số invalid;
- Truy vấn có thể cần scan nhiều documents;
- Validator có thể kết hợp các toán tử khác, không chỉ `$jsonSchema`;
- Không in toàn bộ document PII ra log.

### 17.1. Đối chiếu theo tenant/range

Nếu lỗi mới chỉ xuất hiện ở tenant T-01:

```javascript
db.orders.find({
  tenantId: "T-01",
  amount: { $type: "string" }
}).limit(20);
```

Đi từ phạm vi nhỏ nhất có thể hỗ trợ chẩn đoán, rồi mở rộng khi cần.

### 17.2. Không sửa dữ liệu trong cùng câu chẩn đoán

Giai đoạn đầu ưu tiên **read-only queries** và tạo báo cáo invalid IDs/categories. Chỉ sau approval mới dùng update pipeline.

## 18. Những type mismatches không nhất thiết tạo error

MongoDB có thể **không throw** khi filter so sánh không match như kỳ vọng.

Ví dụ:

```javascript
db.orders.find({
  amount: { $gte: NumberDecimal("100000") }
});
```

Nếu collection có `amount` là String, query có thể loại những records đó theo BSON comparison/type-bracketing semantics, thay vì báo “amount is string”.

Hệ quả:

- Dashboard thiếu orders mà không có exception;
- Tổng doanh thu bị thiếu;
- Sorting trộn kiểu cho ra thứ tự không như người dùng mong đợi;
- Unique/partial indexes có ảnh hưởng ngữ nghĩa;
- Code Java cast sai khi nhận mixed types.

**Không có exception không có nghĩa dữ liệu đúng.** Test phải bao gồm type distribution và business aggregates.

## 19. Tổng quan các toán tử chuyển đổi

MongoDB cung cấp:

- `$convert`: chuyển đổi với điều kiện `onError` và `onNull` khi hỗ trợ;
- `$toInt`, `$toLong`, `$toDouble`, `$toDecimal`;
- `$toString`;
- `$toDate`;
- `$toObjectId`;
- `$toBool`;
- `$dateFromString` cho việc parse String sang Date;
- `$isNumber` để kiểm tra numeric types trong aggregation;
- `$type` để phân loại.

Phần lớn các toán tử rút gọn `$to*` có thể **gây lỗi toàn bộ aggregation** khi gặp giá trị không chuyển đổi được, thay vì âm thầm trả null. `$convert` cho phép xử lý lỗi rõ ràng hơn.

### 19.1. Không mặc định `$convert` hỗ trợ mọi cặp types

Khả năng convert giữa types phụ thuộc toán tử, input và MongoDB version. Ví dụ không thể tùy ý biến object/array phức tạp thành số nguyên bằng `$toInt`.

### 19.2. Chuyển đổi là thay đổi ngữ nghĩa

Việc `"01"` thành `1` làm mất số 0 đầu; `"false"` thành boolean có thể không như kỳ vọng; Date không có timezone có thể được hiểu khác. Chỉ convert khi business contract rõ ràng.

## 20. `$convert` với `onError` và `onNull`

Ví dụ preview chuyển `amount` sang Decimal128:

```javascript
db.orders.aggregate([
  {
    $project: {
      orderNo: 1,
      amountOriginal: "$amount",
      amountType: { $type: "$amount" },
      amountDecimal: {
        $convert: {
          input: "$amount",
          to: "decimal",
          onError: "__CONVERSION_ERROR__",
          onNull: null
        }
      }
    }
  },
  { $limit: 100 }
]);
```

Kết quả:

| `amount` đầu vào | Preview `amountDecimal` |
|---|---|
| `"249900.00"` | Decimal128 hợp lệ |
| `NumberInt(12)` | Decimal128 tương ứng nếu hỗ trợ |
| `"N/A"` | `"__CONVERSION_ERROR__"` |
| `null` | `null` |
| Field missing | `null` theo `onNull` |

Dùng string sentinel chỉ trong **preview/diagnostic pipeline**. Không ghi `"__CONVERSION_ERROR__"` vào field mà validator yêu cầu Decimal128.

### 20.1. Tại sao không dùng `onError: 0`?

Nếu dữ liệu `"N/A"` không chuyển được mà biến thành 0, hệ thống có thể ghi doanh thu sai. Việc “không có giá trị” không nhất thiết bằng số 0.

### 20.2. `onNull` cũng cần business decision

Nếu `amount` là bắt buộc, trả null giúp phân loại record thiếu, nhưng không hợp lệ để ghi target cuối. Cần remediation hoặc quarantine records.

### 20.3. `$convert` không tự là migration

Pipeline `$project` chỉ đọc. Để thay đổi dữ liệu thật phải có explicit update/merge/import operation với preflight, backup, audit và test.

## 21. `$toInt`: những lỗi thường gặp

Thử:

```javascript
db.orders.aggregate([
  {
    $project: {
      quantityAsInt: { $toInt: "$quantity" }
    }
  }
]);
```

Với dữ liệu:

```text
"2"       → Có thể chuyển thành Int32 2
"2.5"     → String không phải integer hợp lệ cho $toInt
"N/A"     → Không thể chuyển
1000000000000 → Có thể vượt phạm vi Int32
2.9       → Numeric conversion có thể cắt phần thập phân
null      → Theo ngữ nghĩa chuyển đổi null
```

**Không áp dụng cắt phần thập phân cho business domain khi dữ liệu phải là số lượng nguyên.** Một `quantity: 2.9` có thể là dữ liệu lỗi, không phải 2 sản phẩm.

### 21.1. Kiểm tra giá trị trước khi convert

```javascript
db.orders.aggregate([
  {
    $project: {
      quantityOriginal: "$quantity",
      quantityConverted: {
        $convert: {
          input: "$quantity",
          to: "int",
          onError: "__BAD_INT__",
          onNull: "__MISSING_INT__"
        }
      }
    }
  },
  {
    $match: {
      quantityConverted: {
        $in: ["__BAD_INT__", "__MISSING_INT__"]
      }
    }
  }
]);
```

Dùng output này để lập danh sách cần xử lý, không tự xóa records.

## 22. `$toLong` và vấn đề số rất lớn

Giá trị Int64 hữu ích cho counters lớn hoặc epoch timestamps theo domain, nhưng vẫn có giới hạn 64-bit.

Ví dụ preview:

```javascript
db.orders.aggregate([
  {
    $project: {
      id: "$_id",
      original: "$quantity",
      longValue: {
        $convert: {
          input: "$quantity",
          to: "long",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

Vấn đề:

- Một String chứa số vượt range Int64 không thể chuyển đúng.
- Một Decimal128 có phần lẻ không tự phù hợp số nguyên.
- JavaScript Number đã làm tròn trước đó thì `$toLong` không thể khôi phục chữ số gốc.
- Một chuỗi `"000123"` khi chuyển Long mất leading zeros, có thể không hợp lệ nếu đó là mã định danh.

### 22.1. Không convert business ID sang số chỉ vì trông giống số

Mã `orderNo: "000123"` nên giữ là String nếu leading zeros có ý nghĩa. Sai type có thể làm hỏng lookup và uniqueness.

## 23. Decimal128 và các giá trị tiền tệ

Tình huống:

```javascript
{ _id: 1, amount: NumberDecimal("123.45") }
{ _id: 2, amount: 123.45 }
{ _id: 3, amount: "123.45" }
```

Ba documents có representations khác nhau. Nếu business yêu cầu Decimal128:

1. Thống kê các types;
2. Xác định đơn vị tiền;
3. Kiểm tra dấu thập phân, thousands separators, currency;
4. Xử lý giá trị lỗi;
5. Chuyển đổi theo phương pháp không mất precision;
6. Đối soát tổng trước/sau;
7. Bật validator sau khi writers phù hợp.

### 23.1. Rủi ro khi nguồn là Double

Chuyển một Double sang Decimal128 không tự khôi phục **giá trị decimal lý tưởng** trước khi Double bị làm tròn. Nếu hệ thống đã dùng floating point cho tiền, có thể cần domain-specific reconciliation với ledger/source records.

### 23.2. Không ép về Decimal128 một cách mù quáng

Các dữ liệu:

```text
"1,234.56"
"1.234,56"
"1 234,56"
"VND 1234"
""
"N/A"
```

có thể dùng các quy ước locale khác nhau. Một conversion chung không biết locale sẽ dễ hiểu sai giá trị.

### 23.3. Java `BigDecimal` và `Decimal128`

Nếu Java dùng `BigDecimal`, cần codec/converter có quy tắc mapping rõ. Một trường BSON Decimal128 khi dùng `Document` thường được decode thành `org.bson.types.Decimal128`, không mặc định là `java.math.BigDecimal`.

## 24. `$toDate` và chuỗi ngày không hợp lệ

Ví dụ:

```javascript
db.orders.aggregate([
  {
    $project: {
      original: "$createdAt",
      createdAtDate: {
        $convert: {
          input: "$createdAt",
          to: "date",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

Dữ liệu `"2026-11-14T04:00:00Z"` có thể parse được theo quy tắc hỗ trợ. Nhưng:

```text
"14/11/2026"
"31/02/2026"
"2026-13-01"
"next Tuesday"
```

không nên được tự suy đoán.

### 24.1. `$dateFromString` cho định dạng có quy ước rõ

Khi biết đầu vào theo pattern cố định:

```javascript
db.orders.aggregate([
  {
    $project: {
      raw: "$createdAtText",
      parsed: {
        $dateFromString: {
          dateString: "$createdAtText",
          format: "%d/%m/%Y",
          timezone: "Asia/Ho_Chi_Minh",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

Chỉ dùng format/timezone này nếu **business contract thật** quy định ngày dạng `dd/MM/yyyy` tại múi giờ đó.

### 24.2. Mơ hồ ngày tháng

`"03/04/2026"` có thể được hiểu là ngày 3 tháng 4 hoặc tháng 3 ngày 4. Không để migration đoán; phải có nguồn xác thực.

### 24.3. UTC và thời gian địa phương

MongoDB Date lưu một thời điểm theo UTC, còn hiển thị local timezone thuộc ứng dụng/UI. Test timezone phải kiểm tra **instant** đúng, không chỉ chuỗi ngày hiển thị giống nhau.

### 24.4. Lỗi date ở biên

Nên test:

- Leap year;
- Ngày không tồn tại;
- DST nếu locale có;
- Timestamp âm;
- Milliseconds precision;
- Field trống/null;
- Date nằm ngoài phạm vi business;
- Epoch seconds vs epoch milliseconds.

Nhầm epoch seconds với milliseconds có thể tạo ngày năm 1970 dù conversion vẫn không throw.

## 25. `$toObjectId` và định danh không hợp lệ

MongoDB ObjectId có representation/giới hạn riêng. Một chuỗi đủ 24 ký tự hex hợp lệ có thể được convert sang ObjectId; không phải mọi String đều có thể.

```javascript
db.orders.aggregate([
  {
    $project: {
      customerIdRaw: "$customerId",
      customerObjectId: {
        $convert: {
          input: "$customerId",
          to: "objectId",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
```

Dữ liệu:

```text
"507f1f77bcf86cd799439011"  → có thể chuyển
"customer-1001"              → không phải ObjectId dạng hex
""
null
```

### 25.1. Không đổi mọi business ID thành ObjectId

Nếu `customerId = "C-1001"` là một định danh doanh nghiệp, nó nên giữ String theo schema. Không bắt buộc tất cả IDs MongoDB phải là ObjectId.

### 25.2. Test join/reference sau conversion

Nếu collection A đã đổi `customerId` từ String sang ObjectId nhưng collection B chưa đổi, `$lookup` có thể trả rỗng dù cả hai nhìn “cùng ID” ở giao diện. Test BSON type ở **cả hai phía join**.

## 26. `$toBool`: bẫy chuỗi `"false"`

Một sai lầm nghiêm trọng là coi:

```javascript
{ $toBool: "$active" }
```

như parser có hiểu từ tiếng Anh.

Trong MongoDB conversion semantics, một String không rỗng như `"false"` có thể chuyển thành Boolean `true`, vì `$toBool` không hoạt động như `Boolean.parseBoolean` của Java.

### 26.1. Cách an toàn

Nếu đầu vào chỉ được phép:

```text
"true"
"false"
"1"
"0"
```

hãy định nghĩa mapping explicit:

```javascript
db.users.aggregate([
  {
    $project: {
      activeRaw: "$active",
      activeNormalized: {
        $switch: {
          branches: [
            {
              case: { $eq: ["$active", "true"] },
              then: true
            },
            {
              case: { $eq: ["$active", "false"] },
              then: false
            }
          ],
          default: "__INVALID_BOOL__"
        }
      }
    }
  }
]);
```

Nếu business còn cho phép `"TRUE"`, `"False"` hay số 0/1, thêm mapping có kiểm soát cùng tests. Không âm thầm biến mọi input không nhận diện thành false.

## 27. Array và nested object mismatches

Ví dụ validator:

```javascript
{
  $jsonSchema: {
    bsonType: "object",
    properties: {
      tags: {
        bsonType: "array",
        items: { bsonType: "string" }
      }
    }
  }
}
```

Các giá trị:

```javascript
tags: ["priority", "gift"]   // hợp lệ
tags: "priority"             // sai kiểu tổng thể
tags: ["priority", 7]        // sai kiểu phần tử
tags: null                   // không hợp lệ nếu chỉ array
```

### 27.1. Không tự wrap scalar thành array khi business không yêu cầu

Chuyển `"priority"` thành `["priority"]` có vẻ hợp lý trong một số schema, nhưng cần xác nhận đó là dữ liệu đã được lưu sai representation hay một giá trị có ý nghĩa khác.

### 27.2. Nested object thiếu field

```javascript
{
  shipping: {
    address: {
      countryCode: "VN"
    }
  }
}
```

Nếu `shipping.address` từng được lưu là String, migration cần parse/normalize an toàn. Không chỉ `$set: {"shipping.address.countryCode":"VN"}` khi `shipping.address` là scalar vì thao tác có thể lỗi.

### 27.3. Field path chứa dấu chấm

Trong MongoDB, cú pháp path `"shipping.address"` thường dùng để truy cập nested field theo dot notation; nhưng schema/key naming có các trường hợp đặc biệt với field names chứa dấu chấm hoặc `$`. Không thao tác các tên field bất thường bằng suy đoán; xem quy tắc server version và dùng công cụ migration tương ứng.

## 28. `additionalProperties: false`: vì sao `_id` thường bị bỏ quên?

Một schema rất chặt:

```javascript
{
  $jsonSchema: {
    bsonType: "object",
    additionalProperties: false,
    required: ["tenantId"],
    properties: {
      tenantId: { bsonType: "string" }
    }
  }
}
```

có thể từ chối document do MongoDB thêm `_id`, vì `_id` không được liệt kê trong `properties`.

### 28.1. Định nghĩa đúng phạm vi

Nếu muốn cấm fields ngoài danh sách, cần cho phép `_id`:

```javascript
{
  $jsonSchema: {
    bsonType: "object",
    additionalProperties: false,
    required: ["tenantId"],
    properties: {
      _id: {},
      tenantId: { bsonType: "string" }
    }
  }
}
```

Vẫn phải cân nhắc fields thêm bởi application/ODM, audit timestamps, version columns, và các dữ liệu đang triển khai song song.

### 28.2. Cứng quá cũng có rủi ro backward compatibility

Nếu app version mới thêm một optional field nhưng validator vẫn cấm, writes sẽ bị từ chối. Đối với rolling deployments, thường cần **expand → migrate → enforce** thay vì khóa schema trước khi thay toàn bộ writers.

## 29. Mixed numeric types và các toán tử cập nhật

Ví dụ:

```javascript
db.orders.updateOne(
  { _id: "ORD-1002" },
  { $inc: { quantity: 1 } }
);
```

Nếu `quantity` là String `"2"`, `$inc` không tự parse nó thành số và có thể báo lỗi. Nếu field missing, `$inc` có semantics riêng để tạo field; nếu null, thường không xử lý như numeric value.

### 29.1. Tìm kiểu bất thường trước update

```javascript
db.orders.aggregate([
  {
    $match: {
      quantity: { $exists: true }
    }
  },
  {
    $project: {
      quantity: 1,
      quantityType: { $type: "$quantity" }
    }
  },
  {
    $match: {
      quantityType: {
        $nin: ["int", "long"]
      }
    }
  }
]);
```

Đây là ứng viên read-only để điều tra, không tự sửa.

### 29.2. `$set` không tương đương `$inc`

Thay `quantity` bằng số 0 để `$inc` không lỗi có thể làm mất giá trị thật. Cần recover/parse dữ liệu nguồn có căn cứ.

### 29.3. Các toán tử arithmetic khác cũng có yêu cầu type

`$multiply`, `$divide`, `$sum` và các toán tử khác có semantics/handling non-numeric riêng. Không giả định mọi phép toán đều throw hoặc đều bỏ qua dữ liệu sai giống nhau; đọc đúng operator reference và test fixtures.

## 30. Lỗi chuyển đổi trong aggregation có thể làm hỏng cả job

Pipeline:

```javascript
db.orders.aggregate([
  {
    $project: {
      value: { $toDecimal: "$amount" }
    }
  },
  {
    $group: {
      _id: null,
      total: { $sum: "$value" }
    }
  }
]);
```

Nếu gặp `"N/A"`, aggregation có thể dừng và trả lỗi conversion thay vì chỉ loại một record.

### 30.1. Cách điều tra an toàn

Trước khi dùng `$toDecimal` trên toàn bộ data:

```javascript
db.orders.aggregate([
  {
    $project: {
      amountType: { $type: "$amount" },
      converted: {
        $convert: {
          input: "$amount",
          to: "decimal",
          onError: "__INVALID__",
          onNull: "__MISSING__"
        }
      }
    }
  },
  {
    $group: {
      _id: {
        type: "$amountType",
        conversion: {
          $cond: [
            {
              $in: [
                "$converted",
                ["__INVALID__", "__MISSING__"]
              ]
            },
            "needs_review",
            "convertible"
          ]
        }
      },
      count: { $sum: 1 }
    }
  }
]);
```

### 30.2. Sentinel có thể trùng dữ liệu thật?

Chọn diagnostic sentinel và schema output phù hợp; dùng tagged object/state hoặc phân loại theo type để tránh nhầm với dữ liệu hợp lệ. Không dùng sentinel String như business value cuối.

### 30.3. Tập dữ liệu lớn cần giới hạn tài nguyên

Một `$convert` chạy qua hàng trăm triệu records có thể tốn CPU. Có thể chia theo tenant/time `_id` ranges, chạy canary, monitor p99, disk/cache và tránh giờ cao điểm.

## 31. Lỗi codec và Java Driver không phải lỗi validator

Một Java chương trình:

```java
Document order = collection.find(
    Filters.eq("_id", "ORD-1001")
).first();

Long quantity = order.getLong("quantity");
```

Nếu BSON `quantity` thực là Int32, `Document#getLong` mong đợi Java `Long` và có thể ném `ClassCastException`.

### 31.1. Đọc type trước khi cast

```java
Object raw = order.get("quantity");

if (raw instanceof Integer value) {
    long quantity = value.longValue();
} else if (raw instanceof Long value) {
    long quantity = value;
} else {
    throw new IllegalArgumentException(
        "Unexpected BSON mapping for quantity: " +
        (raw == null ? "null" : raw.getClass().getSimpleName())
    );
}
```

Ví dụ dùng Java pattern matching cho `instanceof` theo Java version hỗ trợ; với runtime cũ, thay bằng cast truyền thống.

### 31.2. `Number` không bao trùm mọi BSON numeric type

`Integer`, `Long`, `Double` là `Number`, nhưng `org.bson.types.Decimal128` có API chuyển ra `BigDecimal` riêng. Không ép `Decimal128` sang `Number` rồi mong luôn hoạt động.

Ví dụ:

```java
import org.bson.types.Decimal128;
import java.math.BigDecimal;

Object rawAmount = order.get("amount");

if (rawAmount instanceof Decimal128 decimal) {
    BigDecimal amount = decimal.bigDecimalValue();
    // Kiểm tra range/scale/business invariant trước khi dùng.
}
```

Một số Decimal128 special values và trường hợp không biểu diễn được dưới `BigDecimal` cần xử lý theo business contract, không nuốt exception.

### 31.3. `getString` trên numeric field

```java
String amount = order.getString("amount");
```

không có nghĩa driver sẽ tự convert Decimal128 thành String. Khi sai type, có thể gặp lỗi cast. Dùng dữ liệu typed đúng hoặc conversion ở tầng ứng dụng có validation.

## 32. Java BSON encoding và codec errors

Các lỗi khác có thể xảy ra **trước khi MongoDB nhận command**:

- Không tìm thấy codec phù hợp với POJO/custom class;
- UUID representation chưa được cấu hình phù hợp;
- Mapping type generic/phức tạp không được hỗ trợ;
- Custom codec ném exception;
- BSON document vượt giới hạn;
- Dữ liệu vòng tham chiếu/cấu trúc không encode được.

Ví dụ:

```java
MongoCollection<MyCustomPojo> collection = ...;
collection.insertOne(new MyCustomPojo());
```

Nếu codec registry không biết cách serialize `MyCustomPojo`, có thể gặp `CodecConfigurationException`. Tạo thêm index/đổi validator không chữa được lỗi này; cần cấu hình POJO codecs hoặc mapping chính xác.

### 32.1. Cách phân biệt

Một dấu hiệu: **không có server write command tương ứng** vì encode đã thất bại ở client. Dùng driver command monitoring/tracing đã redact để xác minh ở đâu dừng, không giả định chỉ từ HTTP response.

### 32.2. UUID và binary subtype

UUID có những representation/binary subtype settings theo driver. Chuyển đổi driver có thể khiến cùng bytes được hiểu khác nếu cấu hình không tương thích. Nên test round-trip fixture với dữ liệu thật đã ẩn danh, không tự parse UUID bằng String ở mọi đường.

## 33. Spring Data MongoDB: entity có thể không khớp dữ liệu thật

Ví dụ:

```java
@Document(collection = "orders")
public class OrderEntity {

    @Id
    private String id;

    @Field("amount")
    private BigDecimal amount;

    private Integer quantity;
    private Instant createdAt;
}
```

Nếu MongoDB chứa:

```javascript
{
  _id: "ORD-1002",
  amount: "N/A",
  quantity: "2",
  createdAt: "14/11/2026"
}
```

Spring Data cần mapping/converters thích hợp. Một số field có thể convert được, một số khác ném exception, tùy Spring Data version, registered converters và property types.

### 33.1. Java Bean Validation khác MongoDB `$jsonSchema`

Các annotation như `@NotNull`, `@Positive`, `@Email` thuộc hệ validation của Java/Spring khi được kích hoạt đúng. Chúng **không tự bảo đảm mọi writes trực tiếp qua MongoDB hoặc scripts** bị server từ chối.

Ngược lại, collection validator ở MongoDB không tự điều chỉnh Java entity class hoặc conversion settings.

### 33.2. `@Field` alias cần được xét

Nếu Java property `createdAt` map tới BSON `"created_at"`:

```java
@Field("created_at")
private Instant createdAt;
```

MongoDB validator trên `"createdAt"` có thể kiểm tra sai field nếu actual document dùng `"created_at"`. Phải so physical BSON field names khi thiết kế migration.

### 33.3. Custom converters có thể che sai kiểu

Một converter chuyển mọi String thành số 0 khi parse lỗi làm ứng dụng “chạy được” nhưng sai dữ liệu. Converter cần rõ input domain, lỗi, audit và test; với dữ liệu tiền/định danh, **fail rõ ràng thường tốt hơn fallback sai**.

## 34. `MongoWriteException` và `MongoBulkWriteException`

Trong Java Sync Driver, cách bắt lỗi phụ thuộc API/driver version.

Ví dụ đơn lẻ:

```java
import com.mongodb.MongoWriteException;

try {
    collection.insertOne(document);
} catch (MongoWriteException ex) {
    int code = ex.getError().getCode();

    if (code == 121) {
        // Schema validation failure.
        // Lưu metadata đã redact và trả domain validation error phù hợp.
    }

    throw ex;
}
```

### 34.1. Bulk writes có thể lỗi từng phần

```java
import com.mongodb.MongoBulkWriteException;
import com.mongodb.bulk.BulkWriteError;

try {
    collection.bulkWrite(
        writeModels,
        new BulkWriteOptions().ordered(false)
    );
} catch (MongoBulkWriteException ex) {
    for (BulkWriteError error : ex.getWriteErrors()) {
        int requestIndex = error.getIndex();
        int code = error.getCode();

        // Map requestIndex -> business record ID được quản lý an toàn.
        recordFailedWrite(requestIndex, code);
    }

    throw ex;
}
```

`writeModels`, `recordFailedWrite` là phần ứng dụng cần hiện thực. Ví dụ nhấn mạnh **không được coi toàn bộ batch đã thất bại hoặc đã thành công** khi có partial success.

### 34.2. Ordered vs unordered

- **Ordered:** có thể dừng sau lỗi của một write model, các writes trước đó vẫn có thể thành công.
- **Unordered:** có thể xử lý những writes độc lập khác sau lỗi và báo nhiều write errors.
- **Không phải transaction atomic cho cả batch** nếu không nằm trong transaction phù hợp.

### 34.3. Đừng retry vô hạn code 121

Validation failure thường là lỗi dữ liệu/quy tắc cố định; retry y nguyên sẽ lại lỗi. Chỉ retry khi underlying data hoặc schema đã được xử lý và có cơ chế idempotency.

## 35. Một số lỗi khác trông giống schema failure

| Lỗi | Dấu hiệu | Hướng xử lý |
|---|---|---|
| Duplicate key (`11000`) | Unique index conflict | Kiểm tra business key và dữ liệu trùng |
| Validator failure (`121`) | `$jsonSchema` hoặc validator khác | Đọc collection options và violation details |
| Conversion error | `$to*`/`$convert` không chuyển được | Preview + phân loại bad values |
| Type mismatch trong update | `$inc` trên non-numeric | Kiểm tra `$type` của field |
| Path conflict | Update nested field trên scalar hoặc path trùng | Kiểm tra cấu trúc document |
| BSON encoding error | Driver không serialize được | Codec/POJO/UUID |
| ClassCastException | Java lấy sai type | Xem actual BSON type và mapping |
| Document too large | Vượt giới hạn BSON document | Thiết kế lại data model |
| Unauthorized | Thiếu quyền | Sửa IAM/RBAC, không bypass |
| Write concern error | ACK/durability condition chưa đạt | Reconciliation, không kết luận chưa ghi |
| Network timeout | Kết quả write có thể không biết | Kiểm tra idempotency và operation status |

Không dựa vào một substring `"validation"` trong log để phân loại mọi trường hợp. Cần error code, command và thời điểm lỗi.

## 36. Quy trình tìm dữ liệu legacy sai type

Một quy trình read-only trước khi chỉnh sửa:

### Bước 1 — Ghi schema mong muốn

```text
amount: Decimal128, >= 0, required
quantity: Int32 >= 1, required
createdAt: BSON Date, required
status: one of NEW, PAID, CANCELLED
```

### Bước 2 — Đếm theo type

```javascript
db.orders.aggregate([
  { $group: {
      _id: { $type: "$amount" },
      count: { $sum: 1 }
  }},
  { $sort: { count: -1 } }
]);
```

### Bước 3 — Lấy sample đã hạn chế quyền/trường

```javascript
db.orders.find(
  { amount: { $type: "string" } },
  { _id: 1, tenantId: 1, amount: 1 }
).limit(20);
```

Không đưa output này vào logs public vì `amount`/tenant cũng có thể nhạy cảm theo policy.

### Bước 4 — Preview conversion

```javascript
db.orders.aggregate([
  { $match: { amount: { $type: "string" } } },
  { $project: {
      amountPreview: {
        $convert: {
          input: "$amount",
          to: "decimal",
          onError: null,
          onNull: null
        }
      }
  }}
]);
```

### Bước 5 — Phân loại

```text
Convertible safely
Needs locale-specific parsing
Ambiguous
Missing
Null
Out of range
Invalid business value
```

### Bước 6 — Remediation + audit

Chỉ sau approval mới thực thi cập nhật, có backup/snapshot hoặc recovery point phù hợp và đo được số record thay đổi.

## 37. Hai pha chuyển dữ liệu: preview trước, update sau

Một pattern có thể:

```text
Read source
    │
    ▼
Preview / parse / classify
    │
    ├── VALID_CONVERTIBLE
    ├── AMBIGUOUS
    ├── INVALID
    └── MISSING
             │
             ▼
Approved conversion plan
             │
             ▼
Staging migration
             │
             ▼
Data reconciliation
             │
             ▼
Production canary
             │
             ▼
Batch update with checkpoints
             │
             ▼
Enable strict validator
```

### 37.1. Không update tất cả bằng một lệnh không kiểm chứng

Sai:

```javascript
db.orders.updateMany(
  {},
  [
    { $set: { amount: { $toDecimal: "$amount" } } }
  ]
);
```

Chỉ một invalid String có thể khiến operation gặp conversion error; ngoài ra lệnh quá rộng có thể gây tải lớn và phức tạp để khôi phục.

### 37.2. Filter theo type và partition

Ví dụ trên staging:

```javascript
db.orders.updateMany(
  {
    tenantId: "T-01",
    amount: { $type: "string" }
  },
  [
    {
      $set: {
        amountDecimalCandidate: {
          $convert: {
            input: "$amount",
            to: "decimal",
            onError: null,
            onNull: null
          }
        }
      }
    }
  ]
);
```

Lệnh này chỉ tạo **candidate field**, không thay `amount` gốc. Nhưng vẫn là thao tác ghi; cần xác định validator/collection cho phép candidate field, write concern, capacity và monitoring. Giá trị `null` phải được thống kê, không coi là conversion success.

### 37.3. Nếu validator cấm field mới

Có thể cần staging collection/schema expansion hợp lệ, hoặc migration program khác. Không tự bypass validator production để thêm field khi chưa có phê duyệt.

### 37.4. Sau preview, mới quyết định thay field chính

Một cách an toàn hơn là có **mapping từ input ID → parsed value được xác nhận**, rồi ghi với filter type/version guard để tránh overwrite updates mới.

## 38. Tránh race condition giữa migration và ứng dụng

Ví dụ:

```text
T1 Migration đọc amount = "100.00"
T2 User sửa amount thành Decimal128("120.00")
T3 Migration ghi Decimal128("100.00")
```

Migration đã ghi đè dữ liệu mới.

### 38.1. Dùng guard khi update

Nếu business key và source version có sẵn:

```javascript
db.orders.updateOne(
  {
    _id: "ORD-1002",
    migrationVersion: 3,
    amount: "100.00"
  },
  {
    $set: {
      amount: NumberDecimal("100.00"),
      migrationVersion: 4
    }
  }
);
```

Nếu document đã thay đổi, filter không match. Ứng dụng phải xử lý trường hợp `matchedCount=0` bằng re-read/reclassify, không tự coi là success.

### 38.2. Không dùng check-then-update tách rời mà không guard

Đọc source ở Java rồi quyết định write sau vài giây có thể bị stale. Điều kiện phải nằm trong **chính thao tác atomic** khi cần concurrency control.

### 38.3. Idempotency

Một migration nên có thể chạy lại mà không làm hỏng dữ liệu. `$set` về giá trị cuối đã xác minh thường dễ kiểm soát hơn `$inc` hoặc các thao tác phụ thuộc lần chạy.

## 39. Chạy migration theo batch và checkpoint

Trên collection vài trăm triệu documents:

- Chia theo tenant;
- Chia theo `_id` hoặc time ranges;
- Giới hạn số writes/giây;
- Ghi số records attempted/acknowledged/failed;
- Giữ resume checkpoint sau khi batches được xác nhận;
- Theo dõi CPU, cache, disk I/O và replication lag;
- Có stop condition và rollback.

Ví dụ:

```text
Batch ID: 2026-11-14-T01-005
Range: tenant=T-01, _id from A100 to A200
Eligible: 500
Converted: 475
Invalid: 20
Ambiguous: 5
Acknowledged updates: 475
Checkpoint: committed through A200 with exception list
```

Không nâng checkpoint vượt qua records unresolved nếu không có retry/dead-letter tracking phù hợp.

### 39.1. Bulk partial failure

Với unordered bulk, một vài documents có thể bị schema validation từ chối trong khi documents khác đã update. Cần map errors về record IDs, giữ state để retry sau remediation.

### 39.2. Không để migration chiếm hết tài nguyên production

Một job sửa hàng triệu records tác động journal, oplog, index maintenance, replication và cache. Cần throttling và dừng khi read/write p99 của API quan trọng vượt ngưỡng.

## 40. Bảo vệ dữ liệu trước remediation

Trước khi sửa type trên production:

1. Có backup/recovery point phù hợp.
2. Kiểm chứng khả năng restore theo RPO/RTO cần thiết.
3. Đảm bảo không thay đổi dữ liệu ngoài namespace/phạm vi đã duyệt.
4. Lưu thống kê trước.
5. Chạy canary trên một tập IDs nhỏ.
6. Đối soát sau.
7. Có cách phục hồi nếu conversion sai.
8. Xác định owner và thời gian change.

### 40.1. Backup không phải cơ chế undo từng record tức thì

Restore snapshot cũ có thể làm mất những writes mới hơn. Nếu remediation sai, có thể cần reverse patch từ before-values hoặc reconciliation, chứ không chỉ restore toàn database.

### 40.2. Không lưu raw before-values ở nơi thiếu bảo mật

Dữ liệu cũ cũng chứa PII/secrets. Nếu cần audit trước-sau, dùng kho bảo mật phù hợp, hạn chế quyền và retention.

## 41. Từ schema lỏng đến schema strict: expand-and-contract

Một chiến lược rollout:

```text
Current:
  Legacy data mixed BSON types
  Old and new writers coexist
             │
             ▼
Phase 1: Observe
  type distribution + validation warn
             │
             ▼
Phase 2: Update writers
  all services produce canonical types
             │
             ▼
Phase 3: Backfill
  convert eligible legacy documents
  quarantine ambiguous records
             │
             ▼
Phase 4: Reconcile
  counts, sums, key invariants
             │
             ▼
Phase 5: Enforce
  strict validator + error action
             │
             ▼
Phase 6: Monitor
  rejects, p99, job errors
```

### 41.1. Schema compatibility với rolling deploy

Nếu application version cũ còn gửi String nhưng version mới gửi Decimal128, bật strict quá sớm khiến pods cũ thất bại. Chỉ chuyển enforcement khi **tất cả writers** đã được nâng cấp hoặc ngừng.

### 41.2. Dùng intermediate field khi cần

Trong một số migration:

```javascript
{
  amountLegacy: "249900.00",
  amountDecimal: NumberDecimal("249900.00")
}
```

giúp app phiên bản mới đọc field mới trong khi version cũ còn tồn tại. Nhưng phải xác định source of truth và conflict resolution, tránh dual-write vô hạn.

### 41.3. Contract sau khi rollback window đóng

Chỉ bỏ field legacy và siết `additionalProperties` khi không còn app/consumer phụ thuộc, data đã đối soát, backup/rollback path rõ ràng.

## 42. Nhiều writer và validator drift

Một hệ thống có:

```text
API Service A: amount Decimal128
Batch Job B: amount String
CDC Consumer C: amount Double
Admin Script D: amount NumberInt
```

Nếu chỉ sửa API A, lỗi sẽ quay lại.

### 42.1. Inventory producers

Tạo bảng:

| Producer | Kiểu đang ghi | Mục tiêu | Owner | Trạng thái |
|---|---|---|---|---|
| Checkout API | Decimal128 | Decimal128 | Payments team | PASS |
| CSV Import | String | Decimal128 | Operations | TODO |
| CDC consumer | Double | Decimal128 | Data team | TODO |
| Admin script | Int32 | Decimal128 | DBA | TODO |
| Backfill worker | Mixed | Decimal128 | Platform | TODO |

### 42.2. Đồng bộ hợp đồng

Mỗi producer cần dùng schema contract chung và test fixtures. Nếu dữ liệu có nhiều languages/SDKs, phải kiểm tra serializers riêng; không giả định Java converter và Node parser xử lý Decimal128 như nhau.

## 43. Dữ liệu lỗi trong Kafka/CDC hoặc restore

Một schema validator mới có thể làm **replay các events cũ** thất bại vì event payload không phù hợp contract hiện tại.

Ví dụ:

```text
Old event: amount = "100.00"
Current MongoDB validator: amount must be Decimal128
Replay → rejected
```

### 43.1. Event schema versioning

Consumer nên biết event version để chuyển đổi phù hợp trước khi ghi MongoDB. Không ép tất cả historical events vào current schema mà không có conversion plan.

### 43.2. Poison messages

Một event vĩnh viễn sai có thể chặn cả partition nếu consumer retry vô hạn. Cần dead-letter hoặc quarantine với reason code, manual remediation và khả năng replay có kiểm soát.

### 43.3. Restore có thể đưa dữ liệu legacy quay lại

Một backup cũ được restore vào ứng dụng mới có thể chứa mixed BSON types; validator/index definitions cũng tùy artifact/method. Sau restore phải test:

- Actual schema validator;
- Type distribution;
- Java decoding;
- Unique/TTL behavior;
- Application business flows.

**Backup restore thành công không đồng nghĩa schema mới tương thích với dữ liệu phục hồi.**

## 44. Kiểm thử validation bằng trường hợp tốt và xấu

Một bộ test nên có ít nhất:

| Case | `amount` | Expected |
|---|---|---|
| Hợp lệ | `NumberDecimal("100.00")` | Pass |
| String numeric | `"100.00"` | Fail strict decimal |
| Int32 | `NumberInt(100)` | Fail strict decimal nếu schema chỉ decimal |
| Null | `null` | Fail nếu required decimal non-null |
| Missing | không có field | Fail nếu required |
| Negative | `NumberDecimal("-1")` | Fail minimum 0 |
| Text rỗng | `""` | Fail |
| Not a number | `"N/A"` | Fail |
| Nested object | `{value:100}` | Fail |
| Array | `[100]` | Fail |
| Decimal rất lớn | Decimal128 hợp lệ | Phụ thuộc domain bounds |
| Duplicate business key | Same tenant + orderNo | Unique index phải từ chối |

### 44.1. Test ở hai lớp

- **Application:** validator/mapper xử lý input và trả lỗi nghiệp vụ rõ.
- **MongoDB:** database thực sự từ chối invalid writes khi bỏ qua lớp app, nếu business yêu cầu.

Unit test mock repository không chứng minh collection-level `$jsonSchema` đang hoạt động.

### 44.2. Tạo collection lab riêng

Các test insert/update thất bại phải dùng database/collection thử, không ghi dữ liệu lỗi vào production.

## 45. Java integration test cho code 121

Một dạng test logic:

```java
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static org.junit.jupiter.api.Assertions.*;

@Test
void rejectsWrongBsonType() {
    MongoCollection<Document> collection =
        testDatabase.getCollection("validated_orders");

    Document invalid = new Document("_id", "TEST-INVALID-1")
        .append("tenantId", "T-01")
        .append("orderNo", "A-TEST")
        .append("amount", "100.00")
        .append("createdAt", new java.util.Date());

    MongoWriteException ex = assertThrows(
        MongoWriteException.class,
        () -> collection.insertOne(invalid)
    );

    assertEquals(121, ex.getError().getCode());
}
```

Đây là **minh họa test**, cần JUnit dependencies, test fixture collection có validator, MongoDB server thực và lifecycle cleanup phù hợp.

### 45.1. Không assert chuỗi error message nguyên văn

Thông báo/nested details có thể khác giữa driver/server versions. Với test ổn định, ưu tiên code/category và expected postcondition. Có thể test field path khi contract của ứng dụng định nghĩa lớp mapping riêng.

### 45.2. Phải có negative test cho uniqueness

Một write trùng business key bị từ chối bởi unique index có code khác, không nên được phân loại thành 121.

## 46. Test Spring Data mapping và converters

Ví dụ entity:

```java
@Document("validated_orders")
class OrderEntity {
    @Id String id;
    String tenantId;
    BigDecimal amount;
    Integer quantity;
    Instant createdAt;
}
```

Các test cần bao gồm:

1. Java → BSON encode đúng type.
2. BSON → Java decode đúng class.
3. Mixed legacy type đọc được hay thất bại có kiểm soát.
4. Custom converters có round-trip.
5. Date timezone chính xác.
6. Decimal scale/precision được bảo toàn theo business rules.
7. Null/missing behavior.
8. `@Field` aliases.
9. Repository query/aggregation trên dữ liệu mixed.
10. Exception được map thành API error phù hợp.

### 46.1. Dùng actual MongoDB cho integration test

Một mock `MongoTemplate` có thể chỉ test Java logic, không chứng minh MongoDB validator, unique index hoặc BSON decoding thực. Với rủi ro dữ liệu, cần integration test trên MongoDB test deployment đúng feature/version.

### 46.2. Không tự sửa schema để một test PASS

Nếu test cho thấy Decimal128 được decode sai, cần sửa converter hoặc nguồn dữ liệu theo contract. Không chuyển tất cả tiền thành Double chỉ vì POJO hiện dùng Double.

## 47. Tối ưu truy vấn kiểm tra dữ liệu lỗi

Tìm lỗi trên collection khổng lồ có thể làm CPU/I/O tăng mạnh.

### 47.1. Chọn phân vùng

Ví dụ:

```javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "T-01",
      createdAt: {
        $gte: ISODate("2026-11-01T00:00:00Z"),
        $lt: ISODate("2026-12-01T00:00:00Z")
      }
    }
  },
  {
    $project: {
      type: { $type: "$amount" }
    }
  },
  {
    $group: {
      _id: "$type",
      count: { $sum: 1 }
    }
  }
]);
```

Nếu `createdAt` cũng mixed String/Date, filter Date có thể bỏ sót records legacy. Khi đó phân vùng bằng `_id`/tenant/shard key hoặc một khóa ổn định hơn phù hợp contract.

### 47.2. Không scan toàn bộ data trong giờ peak

Có thể:

- Dùng secondary phù hợp read preference/lag nếu nghiệp vụ cho phép;
- Chạy khi tải thấp;
- Giới hạn concurrency;
- Dùng sampling có thống kê, sau đó full reconciliation;
- Tạo staging copy;
- Theo dõi p95/p99 của API.

### 47.3. `limit` không thay tổng kiểm kê

`limit(20)` giúp xem sample, nhưng không cho biết tổng invalid records. Phải có metric đếm/đối soát theo partition khi cần bằng chứng.

## 48. Dùng `explain()` nhưng không suy mọi lỗi là do index

Khi query trên field mixed types:

```javascript
db.orders.find({
  amount: { $gte: NumberDecimal("100000") }
}).explain("executionStats");
```

`explain` giúp xem query plan, keys/docs examined và latency, nhưng **không chứng minh giá trị dữ liệu hợp lệ**. Một query nhanh có thể nhanh vì nó bỏ qua toàn bộ String records.

Phải kết hợp:

- Type distribution;
- Schema violation count;
- Business total reconciliation;
- Query plan;
- Application integration tests.

### 48.1. Mixed types và sort order

MongoDB có thứ tự so sánh giữa các BSON types. Nếu một field có cả String và numeric, sort có thể không tương ứng với thứ tự số học mà business muốn.

Không “sửa” bằng cách thêm index trước khi chuẩn hóa dữ liệu và định nghĩa query contract.

## 49. Bảo mật khi điều tra lỗi dữ liệu

Validation details có thể tiết lộ giá trị:

```text
consideredValue = "someone@example.com"
```

hoặc nested objects chứa thông tin nhạy cảm.

Một incident response đúng cần:

- Chỉ log field names/type/error code khi có thể;
- Redact raw values;
- Tách customer identifiers khỏi logs công khai;
- Dùng trace ID thay raw document;
- Hạn chế quyền read toàn collection;
- Không tắt TLS verification;
- Không dùng root chỉ vì API user không có quyền;
- Bảo vệ before/after exports;
- Có retention cho diagnostic artifacts;
- Không gửi samples thật đến môi trường không được phép.

### 49.1. Không biến lỗi schema thành security bypass

Nếu validator ngăn ghi document thiếu tenantId, không sửa bằng cách bỏ `tenantId` khỏi required chỉ để import dữ liệu không xác thực. Đây có thể là lỗi phân quyền và tính đúng đắn xuyên tenant.

## 50. Monitoring và alert cho schema/type incidents

Một dashboard nên có:

### 50.1. Số lượng và tỷ lệ lỗi

- Writes attempted/s;
- Schema validation rejects/s;
- Conversion errors/s;
- BSON codec/mapping errors/s;
- Duplicate key errors/s;
- Failed records theo importer/job;
- Error rate theo collection, tenant scope và producer version.

### 50.2. Chất lượng dữ liệu

- Type distribution per field;
- Missing/null required fields;
- Invalid enum count;
- Decimal conversion failure count;
- Date parse failure count;
- Legacy records còn lại;
- Partition reconciliation mismatches;
- Documents quarantined;
- Last successful schema migration.

### 50.3. Vận hành

- Read/write p95/p99;
- CPU/disk/cache;
- Replication lag;
- Bulk partial failures;
- Retry count;
- Dead-letter queue depth;
- Data backfill throughput;
- Schema version deploy timeline.

### 50.4. Alert theo tác động

Một cảnh báo:

```text
Schema validation failure rate > 1%
AND write traffic > minimum threshold
FOR 10 minutes
```

chỉ là ví dụ; chọn ngưỡng theo product SLO. Với hành vi ghi tiền/quyền truy cập, một số validation violations có thể cần cảnh báo lập tức.

### 50.5. Không xây dashboard từ một nguồn không đầy đủ

Server logs, application exceptions và MongoDB metrics có phạm vi khác nhau. Một số lỗi codec không bao giờ tới server, vì vậy dashboard chỉ theo MongoDB code 121 sẽ bỏ qua chúng.

## 51. Runbook xử lý sự cố schema validation

```text
INCIDENT ID:
TIME:
ENVIRONMENT:
NAMESPACE:
ERROR RATE:
BUSINESS IMPACT:
OWNER:

SYMPTOM:
  MongoDB 121 / conversion / Java codec / other

CHANGE HISTORY:
  App version:
  Driver/Spring version:
  Validator migration:
  Import source:

EVIDENCE:
  Trace IDs:
  Error code/name:
  Redacted details:
  Actual collection validator:
  BSON type distribution:
  Affected document keys:
  Counts by tenant/time:

CLASSIFICATION:
  Wrong producer type
  Legacy data
  Invalid business value
  Schema conflict
  Driver mapping
  Aggregation conversion
  Security / permissions

CONTAINMENT:
  Pause offending job:
  Error response:
  Retry strategy:
  Rollback criteria:

REMEDIATION:
  Data fix version:
  App fix version:
  Staging tests:
  Backup / recovery point:
  Canary range:
  Write rate limit:

POSTCONDITIONS:
  Invalid count:
  Conversion error count:
  Business totals:
  Index/validator:
  API p95/p99:
  CDC/replication:

DECISION:
  GO / HOLD / ROLLBACK / RECOVER

CLOSURE:
  Evidence links:
  Approval:
  Follow-up:
```

### 51.1. Runbook phải có stop condition

Ví dụ:

```text
If invalid count increases,
business totals diverge,
or critical API write p99 exceeds guardrail:
  STOP data backfill.
```

### 51.2. Không dùng một command “fix tất cả”

Mỗi nhóm lỗi cần remediation riêng. `amount:"N/A"` không thể giải quyết như `amount:"249900.00"` nếu không có nguồn xác thực.

## 52. Bảng quyết định sửa lỗi theo nguyên nhân

| Nguyên nhân | Việc nên làm | Việc không nên làm |
|---|---|---|
| Missing required field | Xác định nguồn dữ liệu, bổ sung theo contract | Tự điền giá trị giả không có nghĩa |
| String numeric convertible | Parse có validation, audit và benchmark | Chuyển mọi lỗi thành 0 |
| Invalid decimal/locale | Xác định locale/đơn vị, quarantine nếu mơ hồ | Guess dấu phẩy/dấu chấm |
| BSON Int32 vs Java Long | Sửa mapping/converter hoặc canonicalize type | Ép cast không kiểm tra |
| Date string invalid | Dùng format/timezone xác định hoặc reject | Parse tùy đoán |
| ObjectId mismatch | Giữ business ID đúng type; convert khi hợp contract | Đổi mọi String ID thành ObjectId |
| `"false"` string | Map boolean explicit | `$toBool` mù |
| Enum sai case | Chuẩn hóa theo business semantics | Lowercase/uppercase mọi thứ không test |
| Unique conflict | Dedupe theo policy | Delete record tùy tiện |
| TTL unexpected | Kiểm tra retention/index | Tắt TTL production ngay |
| Validator drift | Versioned migration + catalog verify | Chỉ sửa annotation Java |
| Legacy invalid records | Backfill có checkpoint, staging tests | Bật strict rồi bỏ mặc |
| Conversion failure aggregation | `$convert.onError`, phân loại records | `$to*` toàn tập rồi retry mãi |
| CodecConfigurationException | Cấu hình codec/POJO đúng | Tắt validator |
| Bulk partial failure | Map write indexes/IDs, reconcile | Báo batch thành công toàn phần |
| Unauthorized | Sửa IAM/RBAC | Dùng root dài hạn hoặc bypass auth |

## 53. Kiểm thử tình huống lỗi theo quy trình

### 53.1. Test matrix

| Test | Input | Expected |
|---|---|---|
| Insert hợp lệ | Decimal128 + Date | Success |
| Insert sai amount type | String | Code 121 khi strict schema |
| Update legacy invalid | Old String document | Behavior theo validationLevel |
| Required field missing | Không có tenantId | Validation failure |
| Enum out of range | `"paid"` | Validation failure |
| Negative numeric | Decimal128(-1) | Minimum rule failure |
| Array element wrong | tags chứa số | Items rule failure |
| Additional property | Extra field | Fail nếu cấm |
| Conversion invalid | `"N/A"` → decimal | `onError` branch |
| Date ambiguous | `"03/04/2026"` | Reject/parse theo explicit format |
| ObjectId malformed | `"abc"` | Conversion failure |
| Bool string | `"false"` | Không tự map sai thành true |
| Java `getLong` on Int32 | Integer | Type mismatch được phát hiện |
| Unordered bulk | Một record lỗi | Partial errors được theo dõi |
| Concurrent update | Revision thay đổi | Guard tránh overwrite |
| Retry after timeout | Write outcome unknown | Reconciliation/idempotency |
| Restore legacy backup | Mixed types | Migration plan rõ |
| Re-enable strict | All writers upgraded | No unexpected rejects |

### 53.2. Có cả positive và negative tests

Chỉ kiểm tra input hợp lệ không đủ. Phải chứng minh invalid data bị từ chối đúng nơi và application trả lỗi có thể hiểu được mà không lộ dữ liệu.

### 53.3. Không viết test vào production

Tạo database/collection riêng, test identities và teardown được phê duyệt. Một test cố tình vi phạm unique index/TTL trên production có thể ảnh hưởng dữ liệu thật.

## 54. Bài tập 1 — Nhận diện tầng lỗi

Cho bốn tình huống:

1. Server trả code 121 khi insert.
2. Java `Document.getLong()` ném `ClassCastException`.
3. Aggregation `$toDate` lỗi.
4. Unique index trả `11000`.

Hãy xác định tầng gây lỗi, thông tin cần thu thập và remediation phù hợp. Giải thích vì sao không thể “sửa” cả bốn bằng `validationAction:"warn"`.

## 55. Bài tập 2 — Tìm type distribution

Collection `orders` có `amount` hỗn hợp.

1. Viết `$group` theo `$type`.
2. Viết query lấy sample String values.
3. Phân biệt missing với null.
4. Thêm báo cáo theo tenant.
5. Giới hạn tác động lên production thế nào?

## 56. Bài tập 3 — `$jsonSchema` hợp lệ

Viết schema yêu cầu:

- `tenantId`: String không rỗng;
- `orderNo`: String, required;
- `amount`: Decimal128 không âm;
- `quantity`: Int32 >= 1;
- `createdAt`: Date;
- `status`: một trong `NEW`, `PAID`, `CANCELLED`.

Tạo bộ input hợp lệ/không hợp lệ và nêu expected error category.

## 57. Bài tập 4 — Legacy invalid và moderate

Một collection có 2 triệu documents String amount, nhưng cần áp validator Decimal128.

1. Strict ảnh hưởng update các records cũ ra sao?
2. Moderate có lợi/hạn chế gì?
3. Có cần sửa producers trước không?
4. Đo số invalid records thế nào?
5. Khi nào chuyển strict?

## 58. Bài tập 5 — Chuyển Decimal128

Các input:

```text
"249900"
"249900.00"
"249,900"
"N/A"
""
null
NumberInt(249900)
```

Thiết kế `$convert` preview và bảng phân loại. Đề xuất business policy cho giá trị không thể chuyển đổi; không thay chúng bằng 0 nếu chưa xác định ý nghĩa.

## 59. Bài tập 6 — Ngày và timezone

Có các strings:

```text
"14/11/2026"
"2026-11-14T04:00:00Z"
"03/04/2026"
"2026-02-30"
```

1. Giá trị nào rõ ràng, giá trị nào mơ hồ?
2. Dùng `$dateFromString` khi nào?
3. Chọn timezone ra sao?
4. Làm sao kiểm chứng instant sau conversion?
5. Tại sao epoch seconds/milliseconds cần phân biệt?

## 60. Bài tập 7 — Boolean trap

Nguồn:

```javascript
{ active: "true" }
{ active: "false" }
{ active: 0 }
{ active: 1 }
{ active: "" }
{ active: null }
```

Hãy viết mapping explicit sang true/false, quyết định giá trị nào invalid, và giải thích nguy cơ dùng `$toBool` trực tiếp.

## 61. Bài tập 8 — Int32/Int64

1. Khác biệt giữa Int32, Int64, Double, Decimal128.
2. Khi nào số 2^53+1 bị làm tròn?
3. Vì sao ID `"000123"` không nên tự convert thành `123`?
4. `Document.getLong()` có xử lý `NumberInt` không?
5. Viết Java mapping có type checks.

## 62. Bài tập 9 — Nested validator

Document:

```javascript
{
  shipping: {
    address: {
      countryCode: 100
    }
  }
}
```

Schema yêu cầu `countryCode` String.

1. Xác định property path lỗi.
2. Lập thông tin log an toàn.
3. Làm thế nào không lộ địa chỉ của người dùng?
4. Nếu `shipping.address` là scalar, update nested path có thể gặp vấn đề gì?

## 63. Bài tập 10 — `additionalProperties`

Một schema bật `additionalProperties:false` nhưng quên `_id`.

1. Tại sao insert có thể fail?
2. Viết schema đã sửa.
3. Rolling deployment thêm optional field bị ảnh hưởng thế nào?
4. Khi nào nên enforce chặt?
5. Có thể dùng schema này thay authorization không?

## 64. Bài tập 11 — Bulk partial failure

Bulk có 500 `UpdateOneModel`, 12 records sai type, `ordered(false)`.

1. Có thể có bao nhiêu records thành công?
2. Đọc `MongoBulkWriteException` thế nào?
3. Map error index về business ID?
4. Khi nào retry?
5. Ghi checkpoint ra sao?

## 65. Bài tập 12 — Concurrent backfill

Worker đọc amount String `"100.00"`; ứng dụng cập nhật thành Decimal128 `"120.00"` trước khi worker ghi.

1. Race condition gì?
2. Viết filter có expected old value/revision.
3. Xử lý matchedCount=0.
4. Chọn checkpoint/idempotency.
5. Khi nào cần CDC catch-up?

## 66. Bài tập 13 — Spring Data mapping

Entity có `BigDecimal amount`, DB legacy có `amount:"N/A"`.

1. Xác định lỗi ở Java converter hay MongoDB validator.
2. Viết integration test BSON → Java.
3. Vì sao custom converter trả BigDecimal.ZERO có thể sai?
4. Làm thế nào báo lỗi nghiệp vụ phù hợp?
5. Kiểm tra `@Field` aliases.

## 67. Bài tập 14 — Restore từ backup cũ

Sau restore, collection chứa Decimal128 và String amount; ứng dụng mới bật strict validator.

1. Dữ liệu cũ có tự bị sửa không?
2. Tại sao updates có thể fail?
3. Viết preflight scan.
4. Kế hoạch backfill và validator rollout.
5. Có cần xác minh backup tool/driver compatibility không?

## 68. Bài tập 15 — Tính đúng đắn tổng doanh thu

Nguồn:

```text
1000 orders hợp lệ Decimal128
50 orders String numeric
10 orders "N/A"
```

Một aggregation chỉ `$sum` numeric values có thể cho ra tổng thiếu.

1. Vì sao không có lỗi vẫn sai?
2. Đếm/đối soát từng nhóm.
3. Xử lý 10 records không xác định.
4. Chọn expected financial total từ nguồn nào?
5. Kiểm thử sau migration.

## 69. Bài tập 16 — Monitoring

Thiết kế dashboard:

- Schema rejects/s;
- Conversion failures;
- Codec errors;
- Failed data import records;
- Type distribution;
- Retry/dead-letter;
- Application write p95/p99;
- Replication lag;
- Data completeness.

Giải thích nguồn nào có thể bỏ sót lỗi do BSON encoding thất bại ở client.

## 70. Bài tập 17 — Tạo runbook incident

Tình huống: Sau deploy, checkout API lỗi 8% với code 121.

Hãy viết runbook:

1. Phạm vi và impact;
2. Evidence cần giữ;
3. Cách xác định validator mới;
4. So sánh producer versions;
5. Containment không phá dữ liệu;
6. Staging reproduction;
7. Fix/rollback gate;
8. Postcondition.

## 71. Bài tập 18 — Quyết định GO/NO-GO

Một migration có:

```text
Producer đã sửa: PASS
Legacy invalid count: 2.500
Ambiguous amount: 17
Backup restore drill: NOT DONE
Business totals: MISMATCH
Strict validator ready: YES
```

1. Có được chuyển strict trên production không?
2. Những blockers nào?
3. Cần remediation và data approval gì?
4. Có cần backup/restore test không?
5. Khi nào được công bố completed?

## 72. Checklist chẩn đoán sự cố

### Bằng chứng

- [ ] Đã ghi operation/namespace/time/tenant scope.
- [ ] Có error code/name, không chỉ một message.
- [ ] Phân biệt server validation, aggregation conversion và Java codec.
- [ ] Đã đọc actual collection validator/options.
- [ ] Có server/driver/Spring versions.
- [ ] Có release/migration timeline.
- [ ] Logs đã redact PII/secrets.

### Dữ liệu

- [ ] Đã thống kê BSON type distribution.
- [ ] Đã phân biệt missing/null.
- [ ] Đã kiểm tra numeric range/precision.
- [ ] Đã kiểm tra Date/timezone/format.
- [ ] Đã kiểm tra ObjectId và business IDs.
- [ ] Đã kiểm tra arrays/nested objects.
- [ ] Đã kiểm tra enum/unique/TTL riêng.
- [ ] Đã phân loại convertible/ambiguous/invalid.
- [ ] Có business rules cho remediation.

### Vận hành

- [ ] Đã xác định các producers.
- [ ] Đã đánh giá write/replication impact.
- [ ] Không retry vô hạn permanent errors.
- [ ] Không bật bypass/disable validator tùy tiện.
- [ ] Có backup và recovery path.
- [ ] Có rollback/stop conditions.
- [ ] Đã phân biệt copied/attempted/acknowledged.
- [ ] Có owner chịu trách nhiệm.

## 73. Checklist trước khi backfill và siết schema

- [ ] Chạy preview conversion trên staging.
- [ ] Có fixture cho dữ liệu khó.
- [ ] Producer mới ghi canonical BSON types.
- [ ] Dữ liệu mơ hồ có queue xử lý.
- [ ] Có batch size, rate limit và checkpoint.
- [ ] Có idempotency/version guard.
- [ ] Có đối soát counts và business totals.
- [ ] Có backup/restore đã kiểm chứng khi cần.
- [ ] Có thông tin ACL/KMS/PII đúng.
- [ ] Có owner cho sự cố.
- [ ] Tất cả writers đã tương thích validator mới.
- [ ] Có plan chuyển warn/moderate sang strict/error.
- [ ] Có integration tests trên MongoDB thật.
- [ ] Có monitoring sau rollout.
- [ ] Có điều kiện hoàn tất/đóng rollback window.

## 74. Tài liệu tham khảo chính thức

Dùng tài liệu **đúng phiên bản MongoDB Server, Java Driver và Spring Data MongoDB**:

- [MongoDB Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [Specify JSON Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/)
- [Schema Validation Options](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-level/)
- [MongoDB `$jsonSchema`](https://www.mongodb.com/docs/manual/reference/operator/query/jsonSchema/)
- [MongoDB JSON Schema Validation Errors](https://www.mongodb.com/docs/manual/core/schema-validation/handle-invalid-documents/)
- [MongoDB BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/)
- [MongoDB Comparison and Sort Order](https://www.mongodb.com/docs/manual/reference/bson-type-comparison-order/)
- [MongoDB `$type` Query](https://www.mongodb.com/docs/manual/reference/operator/query/type/)
- [MongoDB `$type` Aggregation](https://www.mongodb.com/docs/manual/reference/operator/aggregation/type/)
- [MongoDB `$convert`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/convert/)
- [MongoDB `$toInt`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toInt/)
- [MongoDB `$toLong`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toLong/)
- [MongoDB `$toDecimal`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toDecimal/)
- [MongoDB `$toDate`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toDate/)
- [MongoDB `$toObjectId`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toObjectId/)
- [MongoDB `$toBool`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/toBool/)
- [MongoDB `$dateFromString`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/dateFromString/)
- [MongoDB Extended JSON](https://www.mongodb.com/docs/manual/reference/mongodb-extended-json/)
- [MongoDB `collMod`](https://www.mongodb.com/docs/manual/reference/command/collMod/)
- [MongoDB Update with Aggregation Pipeline](https://www.mongodb.com/docs/manual/tutorial/update-documents-with-aggregation-pipeline/)
- [MongoDB Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/)
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [MongoDB Java Driver BSON Guide](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/bson/)
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/)
- [Spring Data MongoDB Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html)
- [MongoDB Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/)

## Kết luận

Xử lý sự cố schema validation và sai kiểu BSON trong MongoDB là bài toán **điều tra đúng tầng, hiểu đúng dữ liệu và sửa có kiểm soát**.

Khi gặp **code 121**, hãy đọc actual collection validator và validation details để biết field/rule nào bị vi phạm. Khi aggregation lỗi `$to*`, hãy dùng `$convert` với `onError`/`onNull` để phân loại đầu vào trước khi quyết định cách sửa, không ép mọi giá trị thành 0 hay null. Khi Java Driver/Spring Data báo `ClassCastException`, `CodecConfigurationException` hoặc mapping error, hãy đối chiếu actual BSON types với class/converter; đừng mặc định database validator là nguyên nhân.

Những nguồn gây lỗi phổ biến nhất gồm **String thay cho Decimal128, Int32/Int64 khác nhau, Date được lưu dạng String, ObjectId nhầm với business ID, `"false"` bị hiểu sai khi đổi Boolean, null/missing và arrays/nested objects sai cấu trúc**. Bên cạnh lỗi có exception, mixed types còn có thể khiến query/aggregation trả kết quả thiếu hoặc sort không đúng nghiệp vụ mà **không báo lỗi**.

Một hệ thống bền vững cần canonical BSON schema, các producer cùng tuân thủ hợp đồng, dữ liệu legacy được chuyển đổi bằng **preview → phân loại → staging → canary → batch repair → reconciliation**, với checkpoint, concurrency guard, backup và rollback. Chỉ sau khi hoàn tất đối soát mới siết validator, cùng monitoring cho code 121, conversion failures, mapping errors, p95/p99 và data quality.

**Mục tiêu không chỉ là làm cho thao tác ghi ngừng báo lỗi, mà là bảo đảm mỗi document sau sửa vẫn mang đúng ý nghĩa nghiệp vụ, đúng kiểu BSON và có thể được mọi ứng dụng đọc/ghi an toàn.**


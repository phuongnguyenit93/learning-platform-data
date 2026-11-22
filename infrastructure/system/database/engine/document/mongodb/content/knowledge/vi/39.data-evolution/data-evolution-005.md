# Tạo ràng buộc mới sau khi làm sạch dữ liệu cũ trong MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chương:** Tiến hóa dữ liệu  
> **Bài học:** Tạo ràng buộc mới sau khi làm sạch dữ liệu cũ

## 1. Bài toán: dữ liệu đã tồn tại không tuân theo hợp đồng mới

Một hệ thống đơn hàng đã hoạt động vài năm với collection `orders`. Ban đầu, ứng dụng cho phép các document linh hoạt:

```javascript
// Document ghi từ ứng dụng phiên bản cũ
{
  _id: ObjectId("66a000000000000000000427"),
  tenantId: "TENANT-01",
  externalOrderId: "ORD-100",
  status: "paid",
  amountCents: "150000",
  email: null
}

// Document ghi từ ứng dụng phiên bản mới
{
  _id: ObjectId("66a000000000000000000428"),
  tenantId: "TENANT-01",
  externalOrderId: "ORD-100",
  status: "PAID",
  amountCents: NumberLong("150000"),
  email: "customer@example.test",
  schemaVersion: NumberInt(2)
}
```

Hai document có **cùng khóa đơn hàng** trong một tenant. Chúng cũng khác kiểu BSON và giá trị enum. Đội phát triển muốn từ giờ bảo đảm:

1. `externalOrderId` là String không rỗng và **duy nhất trong mỗi tenant**.
2. `status` chỉ thuộc `CREATED`, `PAID` hoặc `CANCELLED`.
3. `amountCents` là BSON Int64, không âm và không bị làm tròn.
4. `tenantId` bắt buộc có mặt.
5. Dữ liệu legacy phải được giữ lại đúng ý nghĩa, không bị xóa hay chuyển tiền sai chỉ để vượt qua validator.

Thử ngay:

```javascript
db.orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  { unique: true }
);
```

có thể thất bại vì khóa trùng. Còn thêm validator `strict + error` có thể làm các API cập nhật document cũ bắt đầu báo `DocumentValidationFailure`, **dù MongoDB không tự kiểm/sửa mọi document cũ khi chỉ mới thêm validator**.

Bài học tập trung vào một câu hỏi vận hành:

> **Làm thế nào chuyển một collection đang có dữ liệu cũ và traffic ghi liên tục sang hợp đồng dữ liệu mới, bảo đảm không tạo thêm dữ liệu xấu, không mất dữ liệu hiện hữu và có khả năng khôi phục khi sự cố?**

Câu trả lời không phải “chạy lệnh tạo constraint sau một câu `updateMany`”, mà là **định nghĩa quy tắc → audit → ngăn vi phạm mới → sửa dữ liệu cũ theo lô → kiểm tra lại → siết ràng buộc → theo dõi**.

### 1.1. Kết quả học tập

Sau bài, bạn có thể:

- Phân biệt các lớp ràng buộc MongoDB: `$jsonSchema`, unique/partial unique index, TTL, shard-key rules và bất biến nghiệp vụ ngoài database.
- Audit dữ liệu đã tồn tại theo thiếu field, `null`, BSON type sai, enum sai và duplicate keys.
- Xác định quyền quyết định “sửa”, “hợp nhất”, “quarantine”, “giữ nguyên” thay vì xóa tùy tiện.
- Xây quy trình **expand–migrate–contract** cho nhiều phiên bản ứng dụng cùng hoạt động.
- Bảo vệ hệ thống khỏi race: dữ liệu xấu mới xuất hiện trong khi backfill vẫn đang chạy.
- Dùng `prepareUnique` → `dryRun` → `unique` để chuyển index có sẵn sang unique trên MongoDB hỗ trợ.
- Dùng `validationAction:"warn"/"error"` và `validationLevel:"moderate"/"strict"` theo giai đoạn.
- Hiểu `validationLevel:"constraint"` của MongoDB 9.0 và giới hạn theo version.
- Thiết kế migration idempotent, compare-and-set, theo batch, có thống kê và khả năng tiếp tục sau crash.
- Xử lý null/missing, collation, compound key, sharded collections, TTL và dữ liệu nhạy cảm.
- Thực hành toàn bộ chuỗi trên MongoDB **test namespace riêng** với cleanup có giới hạn.
- Lập kế hoạch đo rủi ro, triển khai, giám sát và rollback/forward-fix.

## 2. Thế nào là một “ràng buộc” trong MongoDB?

Trong mô hình quan hệ, người học thường quen `NOT NULL`, `UNIQUE`, `CHECK`, `FOREIGN KEY`. MongoDB có công cụ tương đương một phần, nhưng ranh giới không hoàn toàn giống.

| Nhu cầu | Công cụ MongoDB | Lưu ý |
| --- | --- | --- |
| Field bắt buộc có mặt | `$jsonSchema.required` | Required **không tự cấm null** |
| Field đúng BSON type | `$jsonSchema.properties.<field>.bsonType` | `int` khác `long`, `double`, `decimal` |
| Enum hoặc giới hạn giá trị | `enum`, `minimum`, `maximum`, `minLength` | Chỉ áp trên operations chịu validation |
| Nested object/array đúng cấu trúc | `properties`, `items`, `minItems` | Phải kiểm mảng null/missing và mixed types |
| Không trùng khóa giữa documents | Unique index | Có quy tắc riêng về null/missing/collation/sharding |
| Không trùng khóa trên tập con | Partial unique index | Chỉ ràng buộc documents thỏa filter |
| Tự hết hạn dữ liệu | TTL index | Là chính sách xóa, không chỉ kiểm schema |
| Cập nhật có điều kiện an toàn | Atomic update, version/CAS | Cần khi writers cạnh tranh |
| Bất biến xuyên documents | Transaction/logic nghiệp vụ | Validator không tự làm foreign-key transaction |
| Quyền truy cập tenant | RBAC + application authorization | Không được suy từ validator |

### 2.1. Ràng buộc cấu trúc khác ràng buộc nghiệp vụ

Ví dụ:

```javascript
{
  amountCents: NumberLong("150000"),
  status: "PAID",
  tenantId: "TENANT-01"
}
```

Một validator có thể chứng minh `amountCents` là Int64 không âm. Nó không chứng minh một payment thực tế đã được thanh toán hoặc tổng tiền đúng với các line items ở collection khác. Ràng buộc “không đơn hàng nào bị ghi nhận thanh toán hai lần” có thể cần unique business ID, transaction, idempotency và kiểm soát external payment.

### 2.2. “Dữ liệu sạch” phải được định nghĩa theo ràng buộc đích

Không có khái niệm “sạch tuyệt đối”. Một String `"42"` là dữ liệu hợp lệ nếu trường là mã định danh, nhưng không hợp lệ nếu hợp đồng yêu cầu BSON Int64. Email `null` có thể hợp lệ nếu optional; có thể vi phạm nếu bắt buộc.

Trước migration, viết rõ:

- Field nào bắt buộc?
- Missing và explicit `null` có ý nghĩa khác nhau không?
- Kiểu BSON nào được chấp nhận?
- Key duy nhất ở phạm vi global, tenant, hay chỉ active records?
- Các ngoại lệ legacy có được giữ không?
- Thế nào là lỗi không thể tự sửa?
- Tiêu chí cắt sang ràng buộc mới là gì?

Nếu chưa thể trả lời, **chưa nên chạy bulk update hay unique index build**.

## 3. Tình trạng ban đầu: lập bản đồ dữ liệu trước khi sửa

### 3.1. Một biểu đồ sự biến đổi

```text
                       Collection hiện hữu
                               |
                 +-------------+--------------+
                 |                            |
                 v                            v
             Audit shape                 Audit uniqueness
       missing/null/type/enum          duplicate/collation/tenant
                 |                            |
                 +-------------+--------------+
                               |
                      Policy nghiệp vụ
                  sửa / hợp nhất / cách ly
                               |
                     Ngăn lỗi ghi mới
                 app writer + validator/index
                               |
                      Backfill có kiểm soát
                               |
                       Đối soát độc lập
                               |
                 Bật ràng buộc đích cuối cùng
                               |
                   Giám sát và rollback plan
```

Tách **phát hiện**, **phán quyết nghiệp vụ** và **thực thi sửa**. Đội DBA không nên quyết định “bản ghi thứ hai là trùng nên xóa” khi dữ liệu liên quan thanh toán, công nợ hoặc lịch sử pháp lý.

### 3.2. Thu thập metadata có giới hạn

Trên database và collection được phép:

```javascript
const d = db.getSiblingDB("commerce");
const c = d.getCollection("orders");

printjson({
  database: d.getName(),
  collection: c.getName(),
  countEstimate: c.estimatedDocumentCount(),
  indexes: c.getIndexes()
});

printjson(d.getCollectionInfos({ name: "orders" }));
```

Cần lưu:

- MongoDB server version, FCV và topology.
- Index key patterns, unique/partial/sparse/TTL, collation và tên index.
- Validator, validation level/action đang có.
- Khả năng sharding, shard key và vùng phân phối dữ liệu.
- Số lượng documents và tốc độ tăng.
- P95/p99 read/write, lỗi ghi, CPU/RAM/IOPS/disk free và replication lag.
- Những ứng dụng, batch jobs, ETL, admin scripts có quyền ghi.
- Quy trình backup/PITR và diễn tập restore.

`estimatedDocumentCount()` là **ước lượng** dựa trên metadata; không dùng nó thay đối soát exact count nếu nghiệp vụ đòi hỏi chính xác.

### 3.3. Ghi nhận schema versions đang cùng tồn tại

Document evolution có thể như:

| Version | Dữ liệu | Writer |
| --- | --- | --- |
| v1 | `status:"paid"`, `amount:"1500"` | Ứng dụng cũ |
| v2 | `status:"PAID"`, `amountCents:Int64` | API mới |
| v2-beta | `amountCents:Double` | Import job lỗi |
| Không có version | Thiếu field | Archive/legacy data |

`schemaVersion` chỉ là metadata do ứng dụng quản lý. Nếu documents cũ không có field này, không nên tự suy ra version chỉ dựa vào một field duy nhất khi có nhiều kiểu dữ liệu tương tự.

### 3.4. Kiểm quyền và phạm vi

Collection test là nơi phù hợp để học; production cần change owner/approval. Không dùng `admin`/`local`/`config` để tạo test data. Không đọc và in toàn bộ customer documents vào log. Audit có thể dùng aggregate counts và mẫu ID đã mask.

## 4. Audit thiếu field, null và BSON type sai

### 4.1. Null và missing không đồng nghĩa

Bộ dữ liệu:

```javascript
[
  { _id: "missing" },
  { _id: "explicit-null", externalOrderId: null },
  { _id: "empty", externalOrderId: "" },
  { _id: "valid", externalOrderId: "A-100" },
  { _id: "wrong-type", externalOrderId: NumberInt(100) }
]
```

Các truy vấn:

```javascript
// Khớp cả missing và explicit null trong fixture scalar:
db.orders.find({ externalOrderId: null });

// Chỉ field không tồn tại:
db.orders.find({
  externalOrderId: { $exists: false }
});

// Field có mặt, kể cả null:
db.orders.find({
  externalOrderId: { $exists: true }
});

// BSON null thực sự trong fixture scalar:
db.orders.find({
  externalOrderId: { $type: "null" }
});
```

Để audit dữ liệu bẩn, phải đếm riêng:

1. Missing.
2. Explicit null.
3. Empty String.
4. Whitespace-only String.
5. Kiểu khác String.
6. Dữ liệu String hợp lệ nhưng trùng business key.
7. Dữ liệu String có casing/Unicode khác contract.

Không coi `{externalOrderId:null}` là thống kê riêng explicit null.

### 4.2. Đếm field thiếu và kiểu không phù hợp

```javascript
const missingId = c.countDocuments({
  externalOrderId: { $exists: false }
});

const explicitNullId = c.countDocuments({
  externalOrderId: { $type: "null" }
});

const emptyId = c.countDocuments({
  externalOrderId: ""
});

printjson({
  missingId,
  explicitNullId,
  emptyId
});
```

Trên một collection có field dạng array, `$type` trong query có thể khớp kiểu **phần tử mảng**. Audit cần kết hợp xác nhận BSON type của field nguyên khối và validator để tránh đánh đồng các trường hợp.

### 4.3. Nhìn phân phối BSON types qua aggregation

```javascript
c.aggregate([
  {
    $group: {
      _id: { $type: "$amountCents" },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

`$type` dạng **aggregation expression** trả `"missing"` cho field thiếu, `"null"` cho BSON Null, `"int"`, `"long"`, `"double"`, `"decimal"`, `"string"` theo kiểu lưu.

Đây là aggregation có thể scan nhiều documents; trong production hãy:

- Chọn thời điểm tải thấp hoặc analytical replica/snapshot phù hợp.
- Chia theo tenant/time/`_id` khi cần.
- Giới hạn `maxTimeMS` và quan sát I/O.
- Không chạy nhiều full scans trùng nhau mỗi phút.
- Lưu kết quả aggregate counts thay vì toàn bộ PII.

### 4.4. Audit enum

```javascript
c.aggregate([
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

Có thể thấy `PAID`, `paid`, `Paid`, `SETTLED`, `" "`, `null`, missing. Không dùng `$toUpper` trên toàn bộ database rồi xem là dữ liệu sạch: `SETTLED` có thể mang nghĩa khác `PAID`, các trạng thái lịch sử có thể không tồn tại trong enum mới.

### 4.5. Audit theo target validator

Khi đã có một **target validator được thống nhất**, có thể tìm documents không thỏa nó:

```javascript
const targetValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: [
      "tenantId",
      "externalOrderId",
      "status",
      "amountCents"
    ],
    properties: {
      tenantId: {
        bsonType: "string",
        minLength: 1
      },
      externalOrderId: {
        bsonType: "string",
        minLength: 1
      },
      status: {
        enum: ["CREATED", "PAID", "CANCELLED"]
      },
      amountCents: {
        bsonType: "long",
        minimum: 0
      }
    }
  }
};

// Trên collection đã chọn đúng phạm vi:
c.find({
  $nor: [targetValidator]
}).limit(20);

const totalInvalid = c.countDocuments({
  $nor: [targetValidator]
});
```

`$nor` đảo kết quả của `$jsonSchema` query predicate; nó giúp đánh giá **document-level validity**. Nhưng collection rất lớn có thể cần scan tốn kém; count phải chạy theo capacity plan.

**Đừng dùng find-invalidation để kết luận uniqueness**: `$jsonSchema` kiểm từng document, không biết có document khác trùng khóa hay không.

## 5. Audit duplicate keys trước unique index

### 5.1. Xác định key nghiệp vụ

Ví dụ yêu cầu: mỗi tenant không được có hai orders cùng `externalOrderId`.

Key phải là:

```javascript
{ tenantId: 1, externalOrderId: 1 }
```

chứ không chỉ:

```javascript
{ externalOrderId: 1 }
```

nếu hai tenants có thể dùng cùng mã `ORD-100`.

### 5.2. Audit duplicates bằng aggregation

```javascript
c.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        externalOrderId: "$externalOrderId"
      },
      count: { $sum: 1 },
      exampleId: { $first: "$_id" }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $sort: { count: -1 } },
  { $limit: 50 }
], { allowDiskUse: true });
```

Điều này là **audit ví dụ**, không phải cách chạy vô điều kiện trên production. `$group` có thể scan toàn collection, tốn CPU/RAM/temp disk; kết quả có thể gồm keys có null/missing, và một số records sai kiểu.

Tránh `$push:"$_id"` không giới hạn cho nhóm có hàng triệu duplicates; BSON document có giới hạn kích thước. Nếu muốn danh sách IDs, phân chia nhóm/batch hoặc truy vấn theo key đã xác định.

### 5.3. Key chuẩn hóa và vấn đề collation

Hai String:

```text
"  ORD-100 "
"ord-100"
"ORD-100"
```

có thể được xem là cùng business ID **nếu** contract yêu cầu trim + uppercase; MongoDB binary/string comparison mặc định không tự thực hiện đầy đủ mọi quy tắc business.

Hai cách:

- **Canonical field:** lưu `externalOrderIdCanonical` được chuẩn hóa theo một thuật toán versioned, kiểm unique trên nó.
- **Collation index:** dùng collation phù hợp nếu yêu cầu là case/accent comparison theo các quy tắc được hỗ trợ.

Trước khi dùng collation, thử với Unicode, locale, trim/whitespace, normalization, diacritics. Collation không thay cho mọi business normalization.

### 5.4. Duplicates không đồng nghĩa data cần xóa

Giả sử hai orders có cùng key nhưng khác payment references:

```javascript
[
  {
    _id: ObjectId("66a000000000000000000427"),
    tenantId: "T-1",
    externalOrderId: "ORD-100",
    paymentId: "PAY-A",
    status: "PAID"
  },
  {
    _id: ObjectId("66a000000000000000000428"),
    tenantId: "T-1",
    externalOrderId: "ORD-100",
    paymentId: "PAY-B",
    status: "PAID"
  }
]
```

Không có đủ thông tin để quyết định đây là đơn bị tạo trùng hay hai nghiệp vụ độc lập bị gán cùng ID. Cần domain owner, payment ledger, audit trail và quy trình đền bù/đối soát.

## 6. Phân loại lỗi và quyết định cách xử lý

Một bảng remediation có ích:

| Nhóm | Ví dụ | Hướng xử lý cần xác minh |
| --- | --- | --- |
| Giá trị có thể chuyển an toàn | `amountCents:"1500"` có contract rõ là cents | Parse String → Int64 có range check |
| Casing enum xác định rõ | `"paid"` đồng nghĩa `"PAID"` theo domain | Map versioned có log |
| Missing bắt buộc nhưng suy ra từ nguồn | `tenantId` có thể truy từ authoritative account | Backfill theo source, kiểm ownership |
| Missing không thể suy ra | Không có mã đơn hàng từ nguồn nào | Quarantine/manual decision |
| Duplicate key cùng business record | Hai writes retry tạo cùng order | Reconcile/canonical record với references |
| Duplicate key khác business record | Hai payments khác nhau chung external ID | Tạo ID riêng/đổi contract với domain owner |
| Giá trị tài chính bất thường | Số tiền âm hoặc không xác định đơn vị | Điều tra; không thay bằng 0 cho “hợp lệ” |
| Date String sai timezone | `"14/11/26"` mơ hồ | Xác định locale/zone; không đoán |
| Field rác nhạy cảm | Token/PII nằm trong notes | Remediation theo chính sách bảo mật |
| Legacy exception được giữ | Archived event không còn thuộc schema orders | Versioned validator hoặc tách collection |

### 6.1. Ba kết quả remediation

Mỗi record cần dẫn đến một trong ba trạng thái có thể kiểm toán:

1. **FIXED:** chuyển đổi có quy tắc rõ, value được đối soát.
2. **QUARANTINED:** chưa đủ bằng chứng, tách vào workflow xử lý thủ công hoặc gắn trạng thái hợp lệ để không ảnh hưởng hợp đồng mới.
3. **BLOCKED:** thiếu điều kiện để bật constraint, không ép triển khai.

“Quarantine” không nhất thiết là chuyển document sang collection khác. Nếu chuyển, cần transactional/cutover protocol để không mất references, không tự `deleteMany` theo cảm tính.

### 6.2. Không sửa dữ liệu chỉ để làm đẹp thống kê

Sai:

```javascript
// KHÔNG dùng trên dữ liệu thật:
db.orders.updateMany(
  { amountCents: { $exists: false } },
  { $set: { amountCents: NumberLong(0) } }
);
```

Đặt 0 có thể làm sai doanh thu và thay đổi nghĩa nghiệp vụ.

Đúng hơn: xác minh authoritative source, đơn vị tiền, khoảng giá trị, lineage và policy; nếu chưa biết, để record vào manual review và **hoãn contract**.

## 7. Định nghĩa hợp đồng đích bằng `$jsonSchema`

### 7.1. Một validator có ý nghĩa rõ

Ví dụ schema đích:

```javascript
const targetOrderValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: [
      "tenantId",
      "externalOrderId",
      "status",
      "amountCents"
    ],
    properties: {
      tenantId: {
        bsonType: "string",
        minLength: 1
      },
      externalOrderId: {
        bsonType: "string",
        minLength: 1,
        maxLength: 100
      },
      status: {
        enum: ["CREATED", "PAID", "CANCELLED"]
      },
      amountCents: {
        bsonType: "long",
        minimum: 0
      },
      email: {
        bsonType: ["string", "null"]
      },
      createdAt: {
        bsonType: "date"
      }
    }
  }
};
```

Điểm cần hiểu:

- `required` kiểm field có mặt, **không tự loại null**.
- `amountCents` chỉ chấp nhận BSON Int64, không mặc định nhận Int32/Double/String.
- `email` optional nhưng nếu có thì String hoặc BSON Null.
- `createdAt` optional trong mẫu; nếu bắt buộc, phải thêm vào `required`.
- Những field không liệt kê trong `properties` vẫn có thể được chấp nhận vì chưa đặt `additionalProperties:false`.
- Không khóa tất cả field lạ trước khi audit metadata `_id`, schemaVersion và các clients cũ.

### 7.2. Required và nullable là hai quyết định độc lập

| Schema | Missing | Explicit null | String |
| --- | --- | --- | --- |
| Optional `bsonType:"string"` | Hợp lệ | Từ chối | Hợp lệ |
| Required `bsonType:"string"` | Từ chối | Từ chối | Hợp lệ |
| Optional `bsonType:["string","null"]` | Hợp lệ | Hợp lệ | Hợp lệ |
| Required `bsonType:["string","null"]` | Từ chối | Hợp lệ | Hợp lệ |

Trước khi làm sạch, phải hỏi **những field null có phải là lỗi không?** Nếu không, đừng đổi chúng thành String rỗng để tránh unique index conflict.

### 7.3. Tiền tệ và kiểu số

Nếu dữ liệu có:

```javascript
{ amountCents: NumberInt(1500) }
{ amountCents: NumberLong("1500") }
{ amountCents: NumberDouble("1500") }
{ amountCents: "1500" }
```

và hợp đồng là `bsonType:"long"`, cần migration cho ba dòng còn lại. Không dùng `NumberLong(parseFloat(...))` trên những giá trị có thể vượt phạm vi integer an toàn của JavaScript. Với tiền tệ, xét decimal representation, đơn vị và giới hạn miền giá trị.

### 7.4. Array và nested object cần validator riêng

Ví dụ orders có line items:

```javascript
{
  lines: [
    { sku: "BOOK-A", quantity: NumberInt(2) }
  ]
}
```

Có thể mở rộng target:

```javascript
const lineRules = {
  bsonType: "array",
  minItems: 1,
  items: {
    bsonType: "object",
    required: ["sku", "quantity"],
    properties: {
      sku: {
        bsonType: "string",
        minLength: 1
      },
      quantity: {
        bsonType: "int",
        minimum: 1
      }
    }
  }
};
```

Dữ liệu legacy `lines:[]`, `lines:null`, hoặc `lines:[{quantity:"2"}]` sẽ vi phạm. Đây là **ngưỡng tương thích cao hơn**; đừng thêm cùng lúc với nhiều constraints khác nếu chưa audit.

### 7.5. `$jsonSchema` không tự làm unique

Hai documents riêng lẻ đều hợp lệ có thể vẫn có cùng externalOrderId. Validator là **document-level constraint**; unique index mới là ràng buộc giữa các records.

## 8. Xác định thứ tự thay đổi trong hệ thống đang có ghi liên tục

### 8.1. Vì sao audit rồi cleanup chưa đủ?

```text
T0: Audit -> thấy 40 duplicate groups
T1: Migration xử lý 40 groups
T2: App cũ ghi thêm duplicate mới
T3: create unique index -> duplicate key error
```

Dù migration ở T1 rất chính xác, dữ liệu đã bẩn trở lại. Đây là **race giữa việc làm sạch và writes mới**.

### 8.2. Nguyên tắc “khóa cửa rồi dọn nhà”

Để đạt trạng thái cuối:

1. Deploy các writers tuân theo contract mới, bao gồm batch jobs/importers.
2. Bật biện pháp server-side chặn một phần lỗi mới sớm nhất có thể.
3. Chỉ sau đó làm sạch historical violations.
4. Đối soát dữ liệu một lần nữa khi writes vẫn chạy.
5. Finalize constraint với cơ chế server đảm bảo không lọt race.
6. Giữ monitoring vì những code paths hiếm có thể lộ lỗi sau nhiều ngày.

Đối với unique index **đã tồn tại ở dạng non-unique**, `prepareUnique` (MongoDB 6.0+) là công cụ hữu ích để chặn duplicate keys mới trong khi duplicate cũ còn tồn tại. Đối với schema, `validationLevel:"moderate"` + `validationAction:"error"` chặn insert invalid mới và việc chuyển một document valid thành invalid, trong khi hỗ trợ sửa documents vốn invalid.

### 8.3. Không phải ràng buộc nào cũng có “prepare” tương đương

Nếu chưa có non-unique index phù hợp, bạn có thể:

- Tạo index nền cần thiết theo quy trình được hỗ trợ;
- kiểm tra dữ liệu;
- dùng unique index mới khi đã bảo đảm không trùng;
- hoặc tổ chức giai đoạn quiesce writes/tạm ngừng các writers liên quan nếu không chứng minh được tính chống race.

Không giả định application-level `findOne` rồi `insertOne` là phương án chống duplicate tuyệt đối: hai requests đồng thời đều có thể nhìn thấy chưa tồn tại và cùng insert. Cần unique index hoặc protocol atomic tương đương.

## 9. Convert non-unique index thành unique với `prepareUnique`

### 9.1. Điều kiện phiên bản và index

MongoDB **6.0+** hỗ trợ chuyển một index non-unique hiện có thành unique thông qua `collMod`.

Điều kiện thực hành:

- Existing index có key pattern/tên xác định.
- Không phải index/time-series case không hỗ trợ `prepareUnique`.
- Thỏa giới hạn unique index của topology, đặc biệt sharded collection.
- Dữ liệu có thể còn duplicates lúc `prepareUnique:true`; xử lý các duplicates trước khi finalize.
- Không thay/drop index đồng thời với conversion.
- Có quyền `collMod` phù hợp.

Không áp lệnh vào deployment cũ hơn hoặc một MongoDB tier không hỗ trợ.

### 9.2. Bước A — Xem index hiện có

```javascript
db.orders.getIndexes();
```

Giả sử có:

```javascript
{
  name: "tenant_external_lookup",
  key: { tenantId: 1, externalOrderId: 1 }
}
```

Không tạo lại một index cùng key/name vô điều kiện. Lưu definition và kiểm index đúng namespace, collation/partialFilter.

### 9.3. Bước B — Chặn duplicates mới

```javascript
db.runCommand({
  collMod: "orders",
  index: {
    name: "tenant_external_lookup",
    prepareUnique: true
  }
});
```

Sau khi lệnh thành công, MongoDB **chặn những writes tạo thêm duplicate index-key values**, dù duplicates cũ chưa được xử lý.

**Quan trọng:** `prepareUnique:true` không tự sửa hoặc xóa bất cứ duplicate document cũ nào. Và đây là một lệnh `collMod` riêng: không gộp `prepareUnique` với thay đổi khác của cùng index trong một lệnh.

### 9.4. Bước C — Dry run kiểm duplicates

```javascript
db.runCommand({
  collMod: "orders",
  index: {
    name: "tenant_external_lookup",
    unique: true
  },
  dryRun: true
});
```

Nếu có duplicates, MongoDB trả `CannotConvertIndexToUnique` và thông tin conflicts khi có thể. Nếu danh sách vượt giới hạn response (tài liệu hiện hành nêu khoảng 8 MB), server có thể báo quá nhiều conflicts thay vì trả toàn bộ IDs.

Vì thế không nên dựa hoàn toàn vào output dry-run để làm hệ thống audit/triage duplicates quy mô lớn.

### 9.5. Bước D — Sửa historical conflicts

Mỗi conflict phải có quyết định nghiệp vụ. Các lựa chọn:

- Đổi key sai thành key thật tìm được từ source.
- Hợp nhất bản ghi duplicate khi chứng minh cùng một nghiệp vụ.
- Đánh dấu một record chỉ là audit/legacy và chuyển namespace nếu policy cho phép.
- Từ chối hoàn tất unique nếu các record thực ra đại diện hai nghiệp vụ không thể gộp.

**Không chạy `deleteOne()` trên payment/order thực chỉ vì thấy duplicate trong dry-run.**

### 9.6. Bước E — Dry run lại và finalize

```javascript
// Đã sửa conflicts, tiếp tục kiểm:
db.runCommand({
  collMod: "orders",
  index: {
    name: "tenant_external_lookup",
    unique: true
  },
  dryRun: true
});

// Khi lệnh trên ok và change ticket cho phép:
db.runCommand({
  collMod: "orders",
  index: {
    name: "tenant_external_lookup",
    unique: true
  }
});
```

Finalization scan/check theo semantics server. Xác minh `getIndexes()` có `unique:true`, chạy negative integration test trên namespace lab và theo dõi `DuplicateKey` từ ứng dụng.

### 9.7. Dừng chuyển đổi khi chưa sẵn sàng

Nếu `prepareUnique` đã bật nhưng chưa thể hoàn tất, không “quên” trạng thái trung gian. Lưu owner, TTL của change ticket, current index definition, lỗi còn lại.

Trên phiên bản hỗ trợ, có thể kết thúc preparation bằng:

```javascript
db.runCommand({
  collMod: "orders",
  index: {
    name: "tenant_external_lookup",
    prepareUnique: false
  }
});
```

Đây là **rollback cho giai đoạn chuẩn bị**, có thể cho writes duplicate mới xuất hiện lại; phải được phê duyệt. Không thể áp `unique:false` như cách đơn giản tắt một unique index đã finalize. Khi index đã unique, việc bỏ constraint có thể đòi hỏi thay/rebuild index theo kế hoạch riêng.

## 10. Nếu cần tạo unique index mới từ đầu

Không phải collection nào cũng có non-unique index đúng key. Ví dụ:

```javascript
db.orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  {
    name: "tenant_external_unique",
    unique: true
  }
);
```

Nếu dữ liệu đang có duplicates, build sẽ lỗi. Nếu writers vẫn tạo duplicates trong lúc build, kết quả còn phụ thuộc race. Quy trình an toàn:

1. Deploy writers đúng contract.
2. Audit và sửa duplicates theo batch.
3. Dùng biện pháp serialization/quiesce tương ứng nếu không bảo đảm được race.
4. Dự trù memory, CPU, disk, IOPS, replication và commit quorum cho index build.
5. Chạy `createIndex` trên namespace được phê duyệt.
6. Kiểm kết quả thành công, definition và behavior.
7. Theo dõi các write errors do unique mới.

Một **online index build** vẫn có lock periods ở đầu/cuối, resource costs và replicated index build coordination. Không gọi một DDL lớn trong giờ peak chỉ vì nó có chữ “online”.

### 10.1. Hidden index không tắt unique

Một hidden index vẫn:

- Được cập nhật khi writes.
- Chiếm disk và tài nguyên.
- Enforce unique nếu là unique index.
- Thực hiện TTL expiration nếu là TTL index.

Hidden chỉ làm index **không được query planner chọn**. Nó không giúp “thử bật unique mà không ảnh hưởng writes”. Thậm chí một hidden unique index mới vẫn có thể làm writes bị từ chối.

## 11. Null, missing, optional ID và unique indexes

### 11.1. Single-field unique index

Với index thông thường:

```javascript
db.users.createIndex(
  { email: 1 },
  { unique: true }
);
```

MongoDB đưa missing và BSON Null vào semantics của index key null. Single-field unique index chỉ có thể có **một document với null index entry**. Nhiều users thiếu email có thể làm index build thất bại.

Không tự thêm unique email trên collection có hàng triệu users email optional.

### 11.2. Compound unique index

```javascript
db.orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  { unique: true }
);
```

Ràng buộc áp trên **tổ hợp key values**. Missing field trở thành null-like index key component. Một key `{tenantId:"T1",externalOrderId:null}` có thể trùng với document khác có cùng `tenantId` và externalOrderId thiếu.

Audit đúng phạm vi compound key, không chỉ check số lượng null toàn collection.

### 11.3. Partial unique khi business field optional

Nếu nhiều người dùng không có email nhưng mọi **String email đã khai báo** phải unique:

```javascript
db.users.createIndex(
  { email: 1 },
  {
    name: "unique_string_email",
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
);
```

Khi đó unique chỉ áp trên documents thỏa partial filter. Missing/Null không vào index này, nhưng những giá trị ngoài String vẫn cần validator xử lý.

Đây là contract khác với “mọi user bắt buộc có email”. Không dùng partial unique để lách yêu cầu required data. Nếu uniqueness theo tenant, cân nhắc key compound `{tenantId:1,email:1}` và shard-key requirements.

### 11.4. Sparse unique không đồng nghĩa partial unique

Sparse index bỏ qua documents thiếu indexed field theo semantics của index, nhưng có thể vẫn index field hiện diện với `null`. Vì vậy `sparse:true` không mặc định cho phép vô hạn documents `{email:null}`.

Partial filter có thể diễn tả tập được ràng buộc rõ ràng hơn, nhưng phải kiểm phiên bản và query coverage. Query planner có thể không chọn partial index khi query không bảo đảm match filter.

### 11.5. Mảng và unique multikey

Một unique multikey index giữ uniqueness giữa **các documents**, không bảo đảm mọi phần tử trong cùng một array không lặp lại. Nếu contract yêu cầu array không duplicate, dùng validator `uniqueItems:true` và logic ghi phù hợp; không dựa vào unique index đơn lẻ.

## 12. Sharded collections: giới hạn ràng buộc unique

Đối với sharded collection, unique index có ràng buộc chặt về **shard key**. Với ranged sharding, unique indexes hợp lệ thông thường là:

- Index trên shard key;
- compound index có shard key là **prefix**;
- `_id` index theo semantics đặc biệt: nếu `_id` không là shard key, uniqueness có thể chỉ được enforce trên từng shard.

Ví dụ nếu shard key:

```javascript
{ tenantId: 1 }
```

một ứng viên unique phù hợp có thể là:

```javascript
{ tenantId: 1, externalOrderId: 1 }
```

Nhưng nếu shard key là `{region:1,tenantId:1}`, index `{tenantId:1,externalOrderId:1}` **không chứa shard key prefix**. Không nên khẳng định nó được enforce global unique mà không kiểm topology/server rules.

Ngoài ra:

- Hashed indexes không hỗ trợ `unique:true` theo cách tùy ý.
- Shard key refinement/resharding có ảnh hưởng tới các unique indexes được phép.
- Các constraints của compound/multikey/partial indexes có thể giới hạn lựa chọn.
- Trong sharded cluster, phải làm DDL qua `mongos` và kiểm tất cả shards.
- `prepareUnique` có thể từ chối index không tương thích shard key.

**Không chia một nghiệp vụ “global unique” thành unique cục bộ per shard mà không thiết kế lại invariant**.

## 13. Bật schema validation theo nhiều giai đoạn

### 13.1. Action và level khác nhau

| Thuộc tính | Giá trị | Tác dụng |
| --- | --- | --- |
| `validationAction` | `warn` | Cho ghi vi phạm nhưng ghi cảnh báo |
| `validationAction` | `error` | Từ chối ghi invalid |
| `validationAction` | `errorAndLog` | Từ chối và log; MongoDB 8.1+ |
| `validationLevel` | `moderate` | Validate inserts và updates trên existing valid docs |
| `validationLevel` | `strict` | Validate mọi inserts/updates, nhưng không retro-scan khi chỉ bật |
| `validationLevel` | `constraint` | MongoDB 9.0+, bảo đảm tất cả documents tuân theo sau upgrade thành công |

`warn` không phải phương pháp bảo đảm invariants; nó là **giai đoạn quan sát**. `moderate` cho phép migration từng bước khi existing invalid docs vẫn cần được update.

### 13.2. Giai đoạn A — Writers hiểu schema mới

Trước tiên:

- Deploy API/server/batch writers tạo đúng field và BSON type.
- Cho phép code đọc cả dữ liệu cũ và mới trong giai đoạn chuyển.
- Đặt schemaVersion khi có contract/version rõ.
- Cập nhật import jobs, admin scripts và driver mappings.
- Dùng feature flags/canary cho đường ghi.
- Viết idempotent retries và xử lý lỗi validator/duplicate key.
- Đánh giá rollback app cũ có còn ghi data theo schema cũ hay không.

Không bật ràng buộc strict cho production khi vẫn còn writer cũ sẽ tạo dữ liệu bị chặn.

### 13.3. Giai đoạn B — Quan sát với `warn`

```javascript
db.runCommand({
  collMod: "orders",
  validator: targetOrderValidator,
  validationLevel: "moderate",
  validationAction: "warn"
});
```

Đây là ví dụ thứ tự. Với `moderate`, updates trên **document vốn invalid** có thể không bị validate, vì vậy log warning không đại diện đầy đủ mọi legacy update.

Nếu mục đích quan sát **mọi write** để tìm client lỗi, có thể cân nhắc `strict + warn` trong giai đoạn staging/prod có kiểm soát; nó không từ chối writes nhưng có thể tăng log volume. Chọn level/action theo mục đích, traffic và policy bảo vệ dữ liệu nhạy cảm.

### 13.4. Giai đoạn C — Chặn dữ liệu sai mới

```javascript
db.runCommand({
  collMod: "orders",
  validator: targetOrderValidator,
  validationLevel: "moderate",
  validationAction: "error"
});
```

Semantics:

- Insert invalid mới bị từ chối.
- Update một existing document **đã valid** thành invalid bị từ chối.
- Update existing invalid document có thể được chấp nhận để phục vụ remediation.

Giai đoạn này tốt hơn việc chờ dọn xong toàn bộ history rồi mới bắt đầu chặn lỗi ghi mới.

### 13.5. Giai đoạn D — Backfill và audit lại

Trong lúc `moderate + error`:

- Sửa dữ liệu legacy có rule rõ.
- Kiểm false positives/false negatives trong target validator.
- Đếm invalid còn lại theo partition và toàn collection.
- Theo dõi lỗi từ writers.
- Không dùng bypassDocumentValidation làm giải pháp thường trực.
- Không cho những dòng dữ liệu “không biết sửa” biến mất khỏi kiểm toán.

### 13.6. Giai đoạn E — Chuyển `strict + error`

```javascript
db.runCommand({
  collMod: "orders",
  validationLevel: "strict",
  validationAction: "error"
});
```

Điều kiện nên có:

- Audit invalid documents = 0 theo phép đo đáng tin.
- Các writer/ETL đều tương thích.
- Negative tests xác nhận writes sai bị chặn.
- Error rate gần baseline và đủ headroom.
- Kế hoạch phục hồi rules cũ nếu code paths hiếm gây lỗi.

**`strict` không tự kiểm và sửa dữ liệu cũ khi switch**. Nếu vẫn còn legacy invalid docs, chúng có thể tồn tại nhưng việc update sau đó sẽ bị chặn.

### 13.7. MongoDB 9.0: `constraint` khi cần bảo đảm toàn collection

MongoDB 9.0 giới thiệu `validationLevel:"constraint"`:

- Có thể bảo đảm mọi document trong collection tuân theo validator sau khi upgrade thành công.
- Với existing collection, cần chuẩn bị bằng `prepareConstraintValidationLevel:true`.
- Upgrade chạy kiểm tra existing documents; fail nếu có document invalid.
- `validationAction` phải là `error` hoặc `errorAndLog`.
- Trong level constraint, không thay validator trực tiếp; cần downgrade level theo tài liệu.
- Bypass validation bị hạn chế.

Ví dụ **chỉ dành cho MongoDB 9.0+ sau khi đã audit**:

```javascript
db.runCommand({
  collMod: "orders",
  prepareConstraintValidationLevel: true
});

db.runCommand({
  collMod: "orders",
  validationLevel: "constraint",
  validationAction: "error"
});
```

Không gộp thay đổi validator với lệnh upgrade `constraint`, và không copy trên MongoDB 6/7/8. Bước scan toàn bộ dữ liệu có chi phí CPU/I/O; triển khai theo change window/metrics phù hợp.

## 14. `moderate` và `strict` với document legacy

Giả sử:

```javascript
{
  _id: "legacy-1",
  status: "paid",
  amountCents: "1500"
}
```

Validator mới yêu cầu enum uppercase và amount Int64.

| Thao tác | `moderate+error` | `strict+error` |
| --- | --- | --- |
| Insert document mới đúng schema | Accept | Accept |
| Insert document mới sai schema | Reject | Reject |
| Update document đang valid thành invalid | Reject | Reject |
| Update legacy invalid chỉ sửa `reviewedAt` | Có thể accept | Reject |
| Update legacy invalid để nó thành valid | Accept | Accept |
| Document legacy không có update | Vẫn tồn tại | Vẫn tồn tại |
| Đặt rule mới bằng `collMod` | Không tự sửa legacy | Không tự sửa legacy |

Cần hiểu chi tiết: `moderate` kiểm tra update dựa trên trạng thái **document trước khi update**. Không kết luận “mọi update invalid đều bị chặn” khi mới chuyển moderate.

## 15. Backfill an toàn: một document, một quyết định, có điều kiện

### 15.1. Không sửa vô hạn theo `updateMany({})`

Ví dụ nguy hiểm:

```javascript
// Sai cho dữ liệu thật: có thể đổi nghĩa tiền.
db.orders.updateMany(
  {},
  {
    $set: {
      status: "PAID",
      amountCents: NumberLong(0)
    }
  }
);
```

Không có một giá trị chung hợp lệ cho mọi order. Bulk update không có phân loại/rules có thể phá business invariants và làm tăng oplog, replication lag, disk IOPS.

### 15.2. Compare-and-set theo old value/version

Một record:

```javascript
{
  _id: ObjectId("66a000000000000000000427"),
  tenantId: "T-1",
  externalOrderId: "A-100",
  status: "paid",
  amountCents: "1500",
  version: NumberInt(7)
}
```

Sau khi xác minh `"1500"` chính là số cents có thể chuyển:

```javascript
const updateResult = db.orders.updateOne(
  {
    _id: ObjectId("66a000000000000000000427"),
    tenantId: "T-1",
    status: "paid",
    amountCents: "1500",
    version: NumberInt(7)
  },
  {
    $set: {
      status: "PAID",
      amountCents: NumberLong("1500"),
      migrationVersion: "constraint-v2"
    },
    $inc: {
      version: 1
    }
  }
);

printjson({
  matched: updateResult.matchedCount,
  modified: updateResult.modifiedCount
});
```

`matchedCount:0` có thể cho biết record đã thay đổi hoặc đã migrate, không phải lý do để bỏ CAS rồi ghi đè. Cần đọc lại, so dữ liệu mới và quyết định retry/skip/conflict.

### 15.3. Viết hàm chuyển có biên rõ

Ví dụ Java 17:

```java
import java.math.BigInteger;

static long parseCents(String raw) {
    if (raw == null || !raw.matches("^[0-9]+$")) {
        throw new IllegalArgumentException(
            "Cents must be a nonnegative integer string"
        );
    }

    return new BigInteger(raw).longValueExact();
}
```

`longValueExact()` ném lỗi nếu giá trị vượt miền Int64; đó là điều tốt hơn silently truncating. Nhưng ngay cả khi parse thành công, bạn vẫn phải xác nhận **đơn vị đầu vào là cents**, không phải VND/dollars.

### 15.4. Migration có thể lặp lại mà không gây tác dụng phụ

Một migration idempotent thường có:

- Predicate chỉ chọn records chưa migrate.
- `migrationVersion` hoặc field marker phù hợp.
- CAS trên old value/version.
- Deterministic transformation.
- Progress checkpoint theo key.
- Retry có giới hạn.
- Log conflict IDs và reason code.
- Không thực hiện email/payment side effects trong bulk retry callback.

Không dựa vào thứ tự natural collection hoặc pagination `skip` với dataset liên tục được ghi; dùng keyset pagination theo `_id` hoặc partition/window với index phù hợp.

### 15.5. Mô hình batch

```text
Read <= N candidates by _id/partition
               |
               v
Transform using audited rule
               |
               v
Validate transformed BSON
               |
               v
Write CAS updates (bounded bulk)
               |
       +-------+-------+
       |               |
       v               v
    Modified         Conflict/no-match
       |               |
       v               v
   Record success    Re-read/review
       |
       v
Persist progress checkpoint
       |
       v
Throttle, monitor, next batch
```

Chỉ checkpoint migration progress khi các updates tương ứng đã được xác nhận theo durability contract phù hợp. Nếu đã áp dụng một phần nhưng chưa checkpoint, retry phải không tạo duplicate/ghi đè nhờ CAS/idempotency.

## 16. Làm sạch duplicates: chọn theo nghiệp vụ trước khi ghi

### 16.1. Bốn câu hỏi

Khi tìm hai documents cùng key:

1. Chúng có cùng semantic identity không?
2. Có cùng payment/order lifecycle không?
3. Có reference từ collections/services khác không?
4. Nếu hợp nhất/đổi ID, downstream có biết mapping không?

Không thể chọn “giữ `_id` nhỏ nhất” làm rule toàn hệ thống nếu ID chỉ phản ánh thời điểm tạo document, không phải độ chính xác nghiệp vụ.

### 16.2. Pattern xử lý an toàn

| Tình huống | Hướng xử lý |
| --- | --- |
| Hai bản giống hệt do retry | Chọn canonical theo audit, xử lý references, lưu lineage |
| Hai bản khác nhau nhưng ID trùng do import bug | Gán business ID đúng từ source có kiểm toán |
| Một bản là legacy history cần giữ | Tách active/current vs historical schema hoặc version |
| Không thể phân biệt | Block conversion và manual review |
| Duplicate do normalization | Chuẩn hóa key theo contract thống nhất, audit conflicts mới |

### 16.3. Đổi key trên một document cần CAS

```javascript
db.orders.updateOne(
  {
    _id: legacyId,
    tenantId: "T-1",
    externalOrderId: "A-100",
    version: NumberInt(3)
  },
  {
    $set: {
      externalOrderId: "A-100-LEGACY",
      duplicateResolutionId: "resolution-ticket-427"
    },
    $inc: { version: 1 }
  }
);
```

Tên `A-100-LEGACY` ở đây chỉ là **minh họa** khi domain owner đã quyết định key mới chính xác. **Không** tự gắn suffix vào mọi duplicate production rồi tuyên bố đã hết xung đột nghiệp vụ.

### 16.4. Nếu phải hợp nhất hai documents

Cần thiết kế:

- Transaction khi thay đổi nhiều MongoDB documents có quan hệ và topology hỗ trợ.
- Mapping old `_id` → canonical `_id`.
- Reconciliation references.
- Audit/history retention.
- Idempotency khi transaction hoặc job retry.
- Compensation cho effects bên ngoài MongoDB.
- Legal/audit policy nếu xóa bản ghi thật.

Unique index giúp tránh trùng trong tương lai, **không quyết định bản nào là canonical**.

## 17. Chuỗi triển khai expand–migrate–contract

### 17.1. Expand: ứng dụng tương thích ngược

Trong release A:

- Reader hiểu cả `status:"paid"` và `status:"PAID"`.
- Writer mới ghi `"PAID"` và amount BSON Int64.
- Các downstream consumers chấp nhận cả hai dạng trong thời gian chuyển.
- Đưa telemetry về writes sai shape/duplicate attempts.
- Nếu cần thêm field mới, để optional trong giai đoạn đầu.
- Dựng non-unique index phục vụ audit/prepareUnique nếu cần.
- Dùng validation warn để quan sát lỗi mới.

### 17.2. Guard: chặn lỗi mới trước khi dọn

Trong release B:

- Xác minh mọi active writer đã chuyển.
- Bật `moderate + error` cho schema.
- Dùng `prepareUnique` cho index đủ điều kiện.
- Theo dõi validation failures/DuplicateKey.
- Chỉ tiếp tục khi các clients cũ không bị outage hoặc đã được thay thế.
- Có rollback plan cho stage này.

### 17.3. Migrate: sửa dữ liệu lịch sử

Trong release C:

- Audit and partition candidates.
- Backfill theo business rules.
- Quarantine những records không thể tự sửa.
- Resolve unique conflicts.
- Chạy dryRun/audit lại nhiều lần.
- So counts/value sums/relations trước–sau.

### 17.4. Contract: siết ràng buộc

Trong release D:

- Finalize unique index.
- Chuyển validator `strict + error`.
- Nếu MongoDB 9.0+ cần guarantee all-existing-valid, xem `constraint` khi đã chuẩn bị.
- Đóng đường viết kiểu cũ và loại code fallback sau khi có bằng chứng.
- Giữ previous version/read compatibility trong khoảng rollback có kế hoạch.
- Quan sát ít nhất một chu kỳ nghiệp vụ quan trọng.

### 17.5. Vì sao cần nhiều release?

Trong rolling deployment, có lúc app v1 và v2 cùng chạy. Nếu database contract được siết trước khi app v1 ngừng ghi, application v1 gặp errors. Nếu bỏ logic đọc legacy trước khi backfill hoàn tất, API đọc sẽ sai.

```text
        Application v1 ---------+
                                |
        Application v2 ---------+---> MongoDB
                                |
        Backfill job -----------+
                                |
        Reporting/ETL ----------+
```

Mọi **writer** cần nằm trong inventory; không chỉ web API chính.

## 18. Trường hợp đa phiên bản và changes đang diễn ra

### 18.1. Dual-read, dual-write cần hợp đồng rõ

Trong một khoảng chuyển:

```javascript
{
  amount: "1500",
  amountCents: NumberLong("1500")
}
```

Có thể cần dual-write. Nhưng nếu application cập nhật một field mà bỏ field còn lại, sẽ xuất hiện inconsistency.

Các lựa chọn:

- Đặt một field canonical; field cũ được duy trì chỉ cho compatibility.
- Dùng transaction/update một document atomically khi dual-write.
- So reconciliation metrics giữa hai field.
- Không backfill mù trên field mới đã được writer khác cập nhật.

### 18.2. Change streams không thay thế audit/gap recovery

Khi backfill trên collection liên tục thay đổi, change stream có thể giúp theo dõi writes và đối soát. Nhưng resume token chỉ hợp lệ khi oplog history còn, consumer có checkpoint/idempotency và không bỏ gap.

Không dựa vào “scan một lần rồi xem từ bây giờ” nếu có khoảng hở giữa snapshot và stream bắt đầu. Với migration quan trọng, dùng cơ chế cutover/backfill được kiểm chứng hoặc quiesce writes khi cần.

### 18.3. Transaction lớn không phải giải pháp mặc định

Một transaction bao toàn collection có thể:

- kéo dài hàng giờ;
- giữ snapshot/history;
- tăng cache/disk pressure;
- gây write conflicts;
- cản trở vận hành và failover.

Thông thường dùng **nhiều atomic updates nhỏ với CAS**, checkpoint và reconciliation. Dùng transaction ngắn cho nhóm operations thực sự phải atomic.

## 19. Bảo đảm không tái xuất hiện vi phạm sau migration

Một lỗi phổ biến: báo “invalid count = 0” lúc 12:00 nhưng đến 12:05 có writer cũ sinh record sai. Để ngăn:

- Validator server-side áp trên mọi writers theo cấu hình.
- Unique index ràng buộc duplicate key.
- Quyền bypassDocumentValidation được cấp tối thiểu.
- Có exception flow có thời hạn, audit.
- Monitoring dựa trên error rate, không chỉ một lần count.
- Kiểm code phiên bản cũ, import scripts và admin tools.
- Cố định contract trong integration/CI tests.
- Có versioned deployment checklist trước rollback ứng dụng.

### 19.1. Validation bypass

Một số MongoDB operations hỗ trợ `bypassDocumentValidation` khi role có quyền. Nếu một migration job sử dụng bypass vì lý do được phê duyệt:

1. Giới hạn tài khoản và thời gian.
2. Ghi audit mỗi operation.
3. Không cấp bypass cho application phổ thông.
4. Chạy reconciliation sau khi job kết thúc.
5. Xem giới hạn `constraint` 9.0: không thể bypass theo semantics của level này.

Dùng bypass để “cho pass” là phản tác dụng nếu mục tiêu bài toán là dữ liệu sạch bền vững.

### 19.2. Error codes và phân loại

| Lỗi | Ý nghĩa thường gặp | Phản ứng |
| --- | --- | --- |
| `DuplicateKey` / E11000 | Unique index chặn trùng key | Kiểm business ID, idempotency và existing record |
| `DocumentValidationFailure` / code 121 | Validator từ chối document | Phân loại field/type, client version |
| `CannotConvertIndexToUnique` | Existing duplicate entries | Audit/remediate, dryRun lại |
| Write concern timeout | Không đạt acknowledgement mong muốn | Không coi chắc chắn write bị rollback; readback/reconcile |
| Network/server selection error | Kết quả operation có thể chưa rõ | Retry có idempotency và backoff |
| Permission/unsupported option | Role, version, tier/topology không phù hợp | Dừng rollout, không vòng qua bằng admin tùy tiện |

Không xây hệ thống production phụ thuộc text error message nguyên văn; driver/server có thể thay wording. Dùng error class, codeName/code và context phù hợp.

## 20. TTL: ràng buộc retention là trường hợp có thể mất dữ liệu

Không phải “ràng buộc” nào chỉ từ chối writes. TTL index **xóa documents** khi đến hạn.

Ví dụ:

```javascript
db.sessions.createIndex(
  { expiresAt: 1 },
  {
    name: "session_ttl",
    expireAfterSeconds: 0
  }
);
```

Trước khi bật trên dữ liệu legacy:

- Kiểm `expiresAt` là BSON Date, không phải String.
- Kiểm field thiếu/null không có cùng expiration behavior.
- Kiểm timezone/UTC và backfill dates có business meaning.
- Tính số documents đã eligible ngay tại thời điểm tạo/đổi index.
- Kiểm legal hold và retention requirements.
- Kiểm IOPS/replication lag khi một lượng lớn deletes xảy ra.
- Backup những data cần giữ hợp pháp.

Nếu giảm TTL từ 90 ngày xuống 7 ngày, lượng lớn documents có thể eligible để bị xóa ngay, gây I/O burst. Đổi lại TTL sau đó **không tự khôi phục documents đã xóa**.

Bài lab **không tạo TTL index** vì không cần cơ chế xóa tự động để minh họa tạo ràng buộc sau cleanup.

## 21. Chọn validator dạng strict hay constraint sau khi sạch

| Tiêu chí | `strict + error` | `constraint + error` (9.0+) |
| --- | --- | --- |
| New inserts invalid | Bị chặn | Bị chặn |
| Updates invalid | Bị chặn | Bị chặn |
| Tự kiểm toàn bộ existing docs khi nâng level | Không | Có, trong upgrade procedure |
| Guarantee mọi existing docs thỏa rule | Không chỉ bằng việc set strict | Có sau upgrade thành công |
| Thay validator trực tiếp | Có thể qua `collMod` | Cần downgrade về strict trước |
| Bypass validation theo quyền | Có thể tùy operation/role | Bị hạn chế |
| Chi phí khi nâng trên collection rất lớn | Không retro-scan mặc định | Có thể full scan, tốn tài nguyên |

Quyết định:

- Nếu dùng MongoDB 8.0 hoặc thấp hơn: không có `constraint`, dựa vào audit/reconciliation + `strict`.
- Nếu dùng MongoDB 9.0+ và cần guarantee mạnh: chuẩn bị, audit, capacity plan và upgrade theo tài liệu.
- Nếu vẫn còn legacy invalid docs: chưa upgrade `constraint` thành công được; cần dọn dứt điểm hoặc thay đổi contract hợp lệ.

## 22. Kế hoạch rollback trước khi bật ràng buộc

### 22.1. Rollback schema validator

Trước thay đổi, export:

```javascript
db.getCollectionInfos({ name: "orders" });
```

Lưu nguyên văn:

- validator trước đây;
- validationLevel;
- validationAction;
- các option liên quan.

Khi cần rollback, dùng `collMod` khôi phục definition trước. Nhưng những writes đã bị từ chối **không tự chạy lại**; ứng dụng cần idempotent retry/reconciliation.

### 22.2. Rollback `prepareUnique`

Trước finalize có thể quay lại `prepareUnique:false` nếu version/conditions cho phép. Điều đó có thể cho duplicates mới sinh ra và cần quyết định có chấp nhận trạng thái đó không.

### 22.3. Rollback một unique index đã finalize

Không dùng `unique:false` làm thao tác đổi cờ đơn giản. Muốn bỏ unique constraint có thể cần drop/rebuild index non-unique hoặc một migration khác, gây I/O và tạm mất invariant. Trong production, thiết kế thay đổi có **khả năng forward-fix** thay vì giả định mọi constraint đảo ngược tức thì.

### 22.4. Rollback dữ liệu đã transform

Nếu chuyển `amount:"1500"` sang `amountCents:Long(1500)`, có thể reverse trong trường hợp nguồn còn và phép chuyển là đơn ánh. Nhưng nếu:

- normalize nhiều String về cùng một canonical value;
- merge duplicates;
- xóa fields/records;
- convert timezone không đủ thông tin;
- tính lại money từ quy tắc không đảo ngược;

thì không thể khôi phục bằng một script ngược ngắn. Cần backup/PITR, lineage và business-level compensation.

### 22.5. Phân biệt “rollback deployment” với “rollback data”

Roll back ứng dụng không đồng nghĩa dữ liệu mới quay về shape cũ. Trước khi deploy app cũ, kiểm ứng dụng cũ **đọc được dữ liệu đã migrate** và các writes cũ có bị validator chặn không.

## 23. Giám sát và tiêu chí chuyển giai đoạn

### 23.1. Dashboard gợi ý

```text
+-----------------------------+-----------------------------+
| Invalid docs remaining      | Duplicate key groups        |
+-----------------------------+-----------------------------+
| Backfill rows/s & conflicts | Job retries / stalled       |
+-----------------------------+-----------------------------+
| Validation failures/min     | DuplicateKey errors/min     |
+-----------------------------+-----------------------------+
| Application write p95/p99   | API error rate              |
+-----------------------------+-----------------------------+
| CPU / WiredTiger cache      | Disk IOPS / queue / free    |
+-----------------------------+-----------------------------+
| Replication lag             | Index conversion state      |
+-----------------------------+-----------------------------+
| Schema versions observed    | Legacy writer requests      |
+-----------------------------+-----------------------------+
| Reconciliation mismatches   | Business-level totals       |
+-----------------------------+-----------------------------+
```

### 23.2. Một tập metric ứng dụng minh họa

```text
mongo_data_migration_candidates_total
mongo_data_migration_processed_total
mongo_data_migration_conflicts_total
mongo_data_migration_manual_review_total
mongo_data_invalid_documents
mongo_data_duplicate_key_groups
mongo_data_schema_version_distribution
mongo_validation_errors_total
mongo_duplicate_key_errors_total
mongo_migration_write_latency_seconds
mongo_migration_last_success_timestamp_seconds
mongo_migration_reconciliation_mismatches
```

Đây là **tên tự định nghĩa**, không phải metric names MongoDB tự xuất. Khi count invalid đòi full scan, không chạy count nặng mỗi vài giây; sử dụng sampling/counters từ migration kết hợp audit định kỳ.

### 23.3. Các điều kiện “Go/No-Go”

Ví dụ phải hoàn tất trước `strict + error`:

- Không còn active writer dùng old schema.
- Số invalid records là 0 theo audit có phạm vi rõ.
- Không còn duplicate groups thuộc target unique index.
- Migration conflicts/manual-review backlog đã được quyết định.
- Index convert dryRun thành công.
- Không có replication lag bất thường.
- Write p95/p99 nằm trong SLO.
- Có backup và kế hoạch data recovery thực tế.
- Các tenant/partitions quan trọng đã được đối soát.
- Các tests tiêu cực xác nhận lỗi bị chặn trong môi trường tương đương.

**Đây là tiêu chí triển khai sản phẩm**, không phải Content QA của tài liệu; STEP 4 chỉ tạo bài học.

## 24. Lab an toàn: từ collection có duplicate tới unique + strict validator

### 24.1. Điều kiện

Bài thực hành yêu cầu:

- MongoDB **6.0+** self-managed test hoặc dịch vụ hỗ trợ `collMod.prepareUnique`.
- Quyền tạo collection, index, `collMod` và CRUD trên **database test**.
- Không dùng collection production, không thay server/FCV.
- Không tạo lượng lớn dữ liệu và không cố gây disk pressure.
- Mỗi lượt dùng **tên collection ngẫu nhiên** và `runId` riêng.
- Chỉ sửa/xóa các records có `_id` và `runId` thuộc lượt thử.
- Không chạy `dropDatabase()` hoặc cleanup không giới hạn.

**Mọi lệnh tiếp theo là ví dụ dành cho test deployment được cấp quyền**, không phải script để copy trực tiếp lên production.

### 24.2. Tạo namespace riêng

```javascript
const lab = db.getSiblingDB("mongo_evolution_row427_lab");
const runId = "row427_" + new ObjectId().toHexString();
const name = "orders_" + runId;
const tenantId = "tenant_" + runId;

if (lab.getCollectionNames().includes(name)) {
  throw new Error("Namespace already exists; refuse overwrite");
}

lab.createCollection(name);
const orders = lab.getCollection(name);

printjson({
  database: lab.getName(),
  collection: orders.getName(),
  tenantId,
  runId
});
```

Lưu các biến trong cùng `mongosh` session. Nếu shell reconnect, phải xác minh namespace/runId của chính lượt thử trước khi tiếp tục; không đoán lại một tenant.

### 24.3. Tạo ba documents: một schema invalid và một duplicate

```javascript
const legacyId = new ObjectId();
const canonicalId = new ObjectId();
const thirdId = new ObjectId();

orders.insertMany([
  {
    _id: legacyId,
    runId,
    tenantId,
    externalOrderId: "A-100",
    status: "paid",
    amountCents: "1500",
    schemaVersion: NumberInt(1)
  },
  {
    _id: canonicalId,
    runId,
    tenantId,
    externalOrderId: "A-100",
    status: "PAID",
    amountCents: NumberLong("1500"),
    schemaVersion: NumberInt(2)
  },
  {
    _id: thirdId,
    runId,
    tenantId,
    externalOrderId: "A-200",
    status: "CREATED",
    amountCents: NumberLong("2500"),
    schemaVersion: NumberInt(2)
  }
]);

print("ownedDocuments=" +
  orders.countDocuments({ runId }));
```

Trong lab, ta **định nghĩa sẵn** hai document A-100 là records giả; việc đổi code của legacy record là hoạt động demo được phép. Với production phải có business owner quyết định.

### 24.4. Xây non-unique index trước

```javascript
orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  { name: "tenant_external_lookup" }
);

printjson(orders.getIndexes());
```

Index này giúp phục vụ lookup, chưa enforce uniqueness.

### 24.5. Audit duplicates có scope

```javascript
const duplicates = orders.aggregate([
  { $match: { runId, tenantId } },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        externalOrderId: "$externalOrderId"
      },
      count: { $sum: 1 }
    }
  },
  { $match: { count: { $gt: 1 } } }
]).toArray();

printjson(duplicates);

if (duplicates.length !== 1 ||
    duplicates[0].count !== 2) {
  throw new Error("Unexpected lab duplicates");
}
```

Ở đây mỗi lượt có đúng một tenant ngẫu nhiên, giúp không chạm records của lượt khác. Dataset chỉ 3 records.

### 24.6. Đặt target validator

```javascript
const validator = {
  $jsonSchema: {
    bsonType: "object",
    required: [
      "runId",
      "tenantId",
      "externalOrderId",
      "status",
      "amountCents"
    ],
    properties: {
      runId: {
        bsonType: "string"
      },
      tenantId: {
        bsonType: "string",
        minLength: 1
      },
      externalOrderId: {
        bsonType: "string",
        minLength: 1
      },
      status: {
        enum: ["CREATED", "PAID", "CANCELLED"]
      },
      amountCents: {
        bsonType: "long",
        minimum: 0
      }
    }
  }
};
```

### 24.7. Stage warn để thấy legacy invalid

```javascript
const warnResult = lab.runCommand({
  collMod: name,
  validator,
  validationLevel: "strict",
  validationAction: "warn"
});

if (warnResult.ok !== 1) {
  throw new Error("Cannot activate validator warning phase");
}

const invalidBefore = orders.countDocuments({
  runId,
  $nor: [validator]
});

print("invalidBefore=" + invalidBefore);

if (invalidBefore !== 1) {
  throw new Error("Expected one legacy invalid doc");
}
```

Ở đây chọn `strict+warn` để cảnh báo mọi write invalid (nếu có) khi test. `collMod` không sửa document cũ. Trên production, log warning có thể chứa dữ liệu nhạy cảm và làm tăng log volume.

### 24.8. Chặn schema invalid mới nhưng cho legacy cleanup

```javascript
const guardResult = lab.runCommand({
  collMod: name,
  validator,
  validationLevel: "moderate",
  validationAction: "error"
});

if (guardResult.ok !== 1) {
  throw new Error("Cannot activate moderate error phase");
}
```

Nếu nhập một document mới invalid, MongoDB sẽ từ chối. Nhưng legacy record có thể tiếp tục được migrate từ trạng thái invalid.

### 24.9. Chuẩn bị chuyển index sang unique

```javascript
const prepare = lab.runCommand({
  collMod: name,
  index: {
    name: "tenant_external_lookup",
    prepareUnique: true
  }
});

if (prepare.ok !== 1) {
  throw new Error("Cannot prepare unique conversion");
}
```

**Sau bước này, duplicate key mới bị chặn**, nhưng cặp A-100 cũ vẫn tồn tại cho đến khi migration sửa.

### 24.10. Thử duplicate mới bị chặn

```javascript
let duplicateBlocked = false;

try {
  orders.insertOne({
    _id: new ObjectId(),
    runId,
    tenantId,
    externalOrderId: "A-100",
    status: "CREATED",
    amountCents: NumberLong("100")
  });
} catch (e) {
  if (e.code === 11000) {
    duplicateBlocked = true;
  } else {
    throw e;
  }
}

if (!duplicateBlocked) {
  throw new Error("Expected DuplicateKey after prepareUnique");
}

print("PASS: duplicate new insert blocked");
```

Trong test, mã lỗi 11000 là `DuplicateKey`. Với production cần xử lý qua driver error categories và không phụ thuộc chuỗi thông báo lỗi.

### 24.11. Thử unique dry run báo xung đột

```javascript
const dryBefore = lab.runCommand({
  collMod: name,
  index: {
    name: "tenant_external_lookup",
    unique: true
  },
  dryRun: true
});

printjson({
  ok: dryBefore.ok,
  codeName: dryBefore.codeName
});

if (dryBefore.ok === 1) {
  throw new Error(
    "Expected existing duplicate to prevent finalization"
  );
}
```

Không tự parse nguyên văn error message; format output có thể thay đổi theo version và số conflicts.

### 24.12. Sửa đúng legacy record trong lab

Đối với data demo, ta đã định nghĩa legacy A-100 cần đổi thành A-100-LEGACY và chuẩn hóa amount/status.

```javascript
const updateLegacy = orders.updateOne(
  {
    _id: legacyId,
    runId,
    tenantId,
    externalOrderId: "A-100",
    status: "paid",
    amountCents: "1500",
    schemaVersion: NumberInt(1)
  },
  {
    $set: {
      externalOrderId: "A-100-LEGACY",
      status: "PAID",
      amountCents: NumberLong("1500"),
      schemaVersion: NumberInt(2)
    }
  }
);

printjson({
  matched: updateLegacy.matchedCount,
  modified: updateLegacy.modifiedCount
});

if (updateLegacy.matchedCount !== 1) {
  throw new Error("Legacy record changed; stop and inspect");
}
```

Lưu ý: tất cả thao tác sửa đều có `_id` + `runId` và old-value filters. Đây là quy tắc **demo**, không phải giấy phép gán suffix tự động cho duplicate production.

### 24.13. Đối soát sau cleanup

```javascript
const invalidAfter = orders.countDocuments({
  runId,
  $nor: [validator]
});

const dupAfter = orders.aggregate([
  { $match: { runId, tenantId } },
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        externalOrderId: "$externalOrderId"
      },
      count: { $sum: 1 }
    }
  },
  { $match: { count: { $gt: 1 } } }
]).toArray();

printjson({
  invalidAfter,
  duplicateGroups: dupAfter.length,
  ownedDocuments: orders.countDocuments({ runId })
});

if (invalidAfter !== 0 || dupAfter.length !== 0) {
  throw new Error("Do not finalize constraints");
}
```

Phải xác nhận cả schema validity lẫn key uniqueness. Đây là ví dụ nhỏ; production cần kiểm bổ sung business invariants, cross-collection references và concurrency.

### 24.14. Dry run đạt và finalize unique

```javascript
const dryAfter = lab.runCommand({
  collMod: name,
  index: {
    name: "tenant_external_lookup",
    unique: true
  },
  dryRun: true
});

if (dryAfter.ok !== 1) {
  throw new Error("Unique dry run still failed");
}

const finalize = lab.runCommand({
  collMod: name,
  index: {
    name: "tenant_external_lookup",
    unique: true
  }
});

if (finalize.ok !== 1) {
  throw new Error("Unique conversion failed");
}

printjson(orders.getIndexes());
```

Chỉ sau lệnh finalize thành công, index mới có `unique:true`. Từ thời điểm này, không coi rollback chỉ là sửa một option.

### 24.15. Bật strict validator

```javascript
const strict = lab.runCommand({
  collMod: name,
  validator,
  validationLevel: "strict",
  validationAction: "error"
});

if (strict.ok !== 1) {
  throw new Error("Cannot activate strict validator");
}

printjson(
  lab.getCollectionInfos({ name })
);
```

Mọi inserts/updates tiếp theo chịu strict validation theo rules.

### 24.16. Negative test ràng buộc mới

```javascript
// 1. Duplicate key phải bị chặn.
let duplicateRejected = false;
try {
  orders.insertOne({
    _id: new ObjectId(),
    runId,
    tenantId,
    externalOrderId: "A-200",
    status: "PAID",
    amountCents: NumberLong("10")
  });
} catch (e) {
  if (e.code !== 11000) throw e;
  duplicateRejected = true;
}

if (!duplicateRejected) {
  throw new Error("Unique index did not reject duplicate");
}

// 2. Sai BSON type/enum phải bị chặn.
let invalidRejected = false;
try {
  orders.insertOne({
    _id: new ObjectId(),
    runId,
    tenantId,
    externalOrderId: "A-300",
    status: "paid",
    amountCents: "100"
  });
} catch (e) {
  if (e.code !== 121) throw e;
  invalidRejected = true;
}

if (!invalidRejected) {
  throw new Error("Validator did not reject bad document");
}

print("PASS: unique and strict validator reject bad writes");
```

Đây là lỗi **được mong đợi trong test namespace**. Không thực hiện những test cố ý tạo duplicate hoặc invalid record trên collection production.

### 24.17. Cleanup theo ownership

Trước hết in phạm vi:

```javascript
print("DB=" + lab.getName());
print("COLLECTION=" + orders.getName());
print("RUN=" + runId);
print("TENANT=" + tenantId);

const owned = orders.find(
  { runId, tenantId },
  { _id: 1, runId: 1, tenantId: 1 }
).toArray();

printjson({
  ownedCount: owned.length,
  ownedIds: owned.map((d) => d._id)
});
```

Sau khi xác nhận đúng 3 documents do lượt test tạo:

```javascript
for (const item of owned) {
  orders.deleteOne({
    _id: item._id,
    runId,
    tenantId
  });
}

print("remaining=" +
  orders.countDocuments({ runId, tenantId }));
```

Không `dropDatabase()` và không `deleteMany({})` trên database có thể dùng chung. Collection/index/validator demo còn tồn tại sau cleanup; môi trường test có thể có cơ chế thu hồi namespaces ngẫu nhiên theo owner/retention. Chỉ người có quyền quản lý lab mới quyết định drop đúng collection sau khi xác minh không còn sử dụng.

## 25. Thiết kế migration worker Java và rollback tương thích

### 25.1. Tách logic chuyển đổi khỏi lệnh MongoDB

Một application migration worker nên có:

```text
CandidateReader
   -> BusinessRuleResolver
   -> BsonTypeConverter
   -> ValidationChecker
   -> ConditionalMongoWriter
   -> ProgressStore
   -> Metrics/AuditLogger
```

Không gộp toàn bộ logic vào một aggregation update pipeline khó review nếu chuyển đổi có ngoại lệ nghiệp vụ.

### 25.2. Ví dụ Java Sync Driver dùng CAS

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;

import org.bson.Document;

import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

static UpdateResult migrateOne(
        MongoCollection<Document> orders,
        Object id,
        String tenantId,
        String oldAmount,
        int expectedVersion,
        long exactCents) {

    return orders.updateOne(
        and(
            eq("_id", id),
            eq("tenantId", tenantId),
            eq("amountCents", oldAmount),
            eq("version", expectedVersion)
        ),
        combine(
            set("amountCents", exactCents),
            set("migrationVersion", "constraint-v2"),
            inc("version", 1)
        )
    );
}
```

`long` trong Java Driver thông thường serialize thành BSON Int64. Kiểm bằng `BsonDocument` hoặc `$type` readback nếu hợp đồng cần chính xác.

### 25.3. Nếu update matched=0

Có thể:

- Record đã được migrate bởi worker khác.
- Ứng dụng vừa sửa amount/status.
- Version tăng.
- Document đã bị xóa/đổi owner.
- Mapping của migration không còn đúng.

Phải đọc lại và phân loại. Không retry vô hạn bằng filter chỉ `_id` vì dễ ghi đè dữ liệu mới.

### 25.4. Writer vẫn hoạt động khi migration chạy

Cần coordinated contract:

- Writers mới sinh đúng schema.
- Legacy readers chịu được both shapes.
- Backfill chỉ sửa record theo expected old fields.
- Nếu concurrent write đã sửa record, migration bỏ qua hoặc reconcile.
- Khi total invalid = 0 và all writers migrated, mới contract.
- Nếu có change stream/outbox, giữ checkpoint và không tự mất oplog history.

## 26. Kiểm thử hồi quy trước và sau ràng buộc

Những test dưới đây thuộc **chiến lược của hệ thống được bài học mô tả**; worker STEP 4 không chạy lượt Content QA.

### 26.1. Ma trận insert/update

| Test | Kỳ vọng sau strict + unique |
| --- | --- |
| Insert đúng schema, key mới | Thành công |
| Insert status lowercase | Validator reject |
| Insert amount String | Validator reject |
| Insert amount negative | Validator reject |
| Insert tenantId missing | Validator reject |
| Insert externalOrderId null | Validator reject |
| Insert trùng tenant+externalOrderId | DuplicateKey |
| Insert cùng externalOrderId khác tenant | Thành công nếu contract per tenant |
| Update valid → invalid | Validator reject |
| Update legacy invalid sau strict | Reject cho đến khi sửa thành valid |
| Update amount với Int32 khi target Long | Reject |
| Upsert không tạo required fields | Validator reject ở nhánh insert |
| Replace thiếu required fields | Reject |
| Concurrent duplicate inserts | Chỉ một key được chấp nhận |
| Retry cùng idempotency key | Không tạo business effect trùng |

### 26.2. Kiểm correctness trên dữ liệu

- Số đơn hàng trước/sau.
- Tổng doanh thu/amount theo tenant trước/sau với đối soát authoritative source.
- Số keys đổi và lý do từng key.
- Số records quarantine.
- Tỷ lệ lỗi do validation/index.
- Số documents chưa migrate.
- Quan hệ references giữa collections.
- Thời điểm và actor của mỗi remediation.
- Reconciliation của downstream projections.

Không coi “invalid count = 0” là bằng chứng đủ nếu data bị “sửa” bằng cách xóa hàng triệu records.

### 26.3. Các boundary tests bắt buộc

- Null vs missing.
- String rỗng/whitespace.
- Case/accent/Unicode normalization.
- NumberInt vs NumberLong vs Decimal128/Double.
- Int64 overflow/precision.
- Required field thiếu trong upsert.
- Parallel inserts cùng key.
- Chuyển key trong update dẫn đến duplicate.
- Legacy document còn sai trong giai đoạn moderate.
- Index build/dryRun khi còn duplicate.
- Rollback app version sau khi strict đã bật.

## 27. Runbook sự cố thường gặp

### 27.1. Convert unique báo `CannotConvertIndexToUnique`

**Triệu chứng:** dryRun/finalization thất bại.

**Điều tra:**

1. Xác minh đúng index name/keyPattern và namespace.
2. Kiểm duplicate groups, null/missing, normalization.
3. Kiểm shard key/unique restrictions.
4. Xem concurrent writes/index changes.
5. Nếu conflicts quá nhiều, không dựa toàn bộ vào error response.
6. Giữ `prepareUnique` nếu đã bật và muốn tiếp tục chặn duplicates mới.
7. Chạy remediation theo domain decision, dryRun lại.

Không giảm ràng buộc bằng cách bỏ unique requirement mà không hỏi business owner.

### 27.2. Bật validator xong API báo code 121

**Triệu chứng:** `DocumentValidationFailure` tăng sau rollout.

**Điều tra:**

- App version nào ghi?
- Operation insert, update, replace hay upsert?
- Document trước update valid hay invalid?
- Field/type/enum nào vi phạm?
- Có import/ETL/cron còn ghi format cũ?
- Có dùng `strict` quá sớm không?
- Có log PII trong error output không?

**Mitigation:** rollback writer code, sửa schema mapping, hoặc tạm lùi validator level/action nếu đã được phê duyệt. Không blanket bypass cho mọi client.

### 27.3. Có dữ liệu duplicate mới sau audit

Đây thường là dấu hiệu guard chưa đủ hoặc có writers ngoài inventory. Kiểm:

- Index có `prepareUnique` hoặc unique thật chưa?
- Scope index có đúng tenant không?
- PartialFilter có bỏ qua records không mong muốn?
- Có collections/shards khác nằm ngoài scope không?
- Admin jobs có bypass/ghi trực tiếp không?
- Normalization của application và database có đồng nhất không?

Không chỉ chạy audit lại rồi tiếp tục migration; phải **chặn nguồn tạo lỗi**.

### 27.4. Migration làm tăng replication lag

Biện pháp:

- Giảm batch size/throughput.
- Xem write concern và secondary I/O.
- Dừng các batch jobs cạnh tranh tài nguyên.
- Giữ headroom cho oplog/journal/indexes.
- Không tăng concurrency vô hạn.
- Tiếp tục từ checkpoint sau khi cluster ổn định.

Không giảm durability/write concern một cách phản xạ nếu nghiệp vụ cần majority acknowledgment.

### 27.5. Đổi unique key làm mất liên kết downstream

Triệu chứng: read model, báo cáo hoặc đối tác không tìm được order theo externalOrderId cũ.

Nguyên nhân: migration thay business ID mà không có mapping/cutover plan.

Phục hồi cần:

- Mapping oldKey → newKey.
- Reconciliation references/caches/search indexes.
- Audit event hoặc outbox theo policy.
- Reprocess idempotently.
- Nếu phải rollback, xem dữ liệu mới đã phát sinh sau key change.

### 27.6. `strict` còn invalid docs nhưng không báo lúc bật

Không phải bug. `strict` không retro-scan all docs khi set. Một update bất kỳ trên invalid doc mới gây lỗi. Cần audit `$nor:[validator]` hoặc, trên MongoDB 9.0+, xem `constraint` khi cần bảo đảm all documents valid.

## 28. Một mẫu kế hoạch production change

```yaml
changeId: mongo-orders-constraint-v2
owner: orders-platform
scope:
  database: commerce
  collection: orders
  environment: production
objective:
  - tenant_external_order_id_unique
  - strict_order_schema
preconditions:
  - verified_server_fcv_topology
  - inventory_all_writers
  - backup_restore_tested
  - no_unrelated_major_ddl
  - capacity_headroom
  - migration_rules_approved
baseline:
  - p95_read_write
  - validation_failure_rate
  - duplicate_groups
  - invalid_documents
  - replication_lag
  - disk_free_iops
phases:
  - expand_application_read_write
  - schema_warn
  - schema_moderate_error
  - prepare_unique
  - backfill_and_resolve_conflicts
  - audit_and_unique_dry_run
  - finalize_unique
  - schema_strict_error
successCriteria:
  - zero_invalid_documents
  - zero_duplicate_groups
  - no_unexpected_write_errors
  - business_reconciliation_pass
rollback:
  - restore_previous_validator_if_required
  - revert_prepare_unique_before_finalization_if_approved
  - plan_forward_fix_after_unique_finalization
  - restore_data_using_backup_or_lineage_when_needed
```

Đây là mẫu **change ticket** do con người quản lý, không phải file MongoDB thực thi. Trước change, lưu cả các lệnh/definitions chính xác, change times và người phê duyệt; không copy ticket chung chung mà bỏ điều kiện quan trọng của deployment.

## 29. Bài tập tự luyện

### Bài A — Required hay nullable?

Một collection có:

```javascript
{}
{email:null}
{email:""}
{email:"a@example.test"}
```

Thiết kế validator cho hai hợp đồng:

1. Email optional nhưng nếu có phải String không rỗng.
2. Email required, cho phép Null trong giai đoạn chuyển.

Giải thích `required`, `bsonType` và `minLength` ảnh hưởng từng document.

### Bài B — Unique theo tenant

```javascript
[
  {tenantId:"T1", code:"A"},
  {tenantId:"T2", code:"A"},
  {tenantId:"T1", code:"A"}
]
```

1. Có bao nhiêu duplicate groups theo `{tenantId,code}`?
2. Nếu tạo unique index chỉ `{code:1}`, dữ liệu nào xung đột?
3. Nếu collection sharded theo `{region:1,tenantId:1}`, unique key cần xét điều gì?
4. Vì sao không thể chỉ sửa trùng bằng một `deleteMany`?

### Bài C — `prepareUnique`

Giả sử có non-unique index và 500 duplicates:

1. `prepareUnique:true` có cho phép bạn tiếp tục giữ 500 duplicates cũ không?
2. Duplicate mới có bị chặn không?
3. `dryRun:true` làm gì?
4. Khi nào chạy `unique:true`?
5. Nếu cần dừng trước finalize, rollback preparation thế nào?

### Bài D — Dữ liệu sai BSON type

Có:

```javascript
{amountCents:"1000"}
{amountCents:NumberInt(1000)}
{amountCents:NumberLong("1000")}
{amountCents:NumberDouble("1000")}
```

Hợp đồng yêu cầu Int64 không âm. Thiết kế audit, phép chuyển đổi có kiểm overflow/precision và tests sau readback.

### Bài E — Race giữa cleanup và writes

```text
12:00 Audit duplicates=20
12:05 Fix duplicates=0
12:06 App cũ inserts duplicate mới
12:07 Unique build fails
```

Hãy thiết kế thứ tự deploy writers, validator, index preparation và migration để loại bỏ race.

### Bài F — Migrate tiền tệ

Một record chứa `amount:"1500"` nhưng không rõ đơn vị. Vì sao `NumberLong("1500")` có thể đúng kiểu mà vẫn sai nghiệp vụ? Cần nguồn dữ liệu và approval nào?

### Bài G — Partial unique email

Nhiều users không có email, một số có `email:null`, số khác có String. Hãy tạo index chỉ unique những String emails và nêu những điều validator/normalization còn phải đảm bảo.

### Bài H — Moderate và strict

Một existing document invalid chỉ được cập nhật `reviewedAt`. Dự đoán hành vi dưới:

- `moderate + error`;
- `strict + error`;
- `strict + warn`;
- `constraint + error` trên MongoDB 9.0 sau upgrade thành công.

### Bài I — Data cleanup idempotency

Một migration job chết sau khi đã sửa 60/100 records nhưng trước khi checkpoint. Khi restart:

1. Làm sao không ghi đè records đã migrate?
2. Có cần version/old-value filter không?
3. Tại sao không dùng `skip` pagination trên collection thay đổi?
4. Mẫu progress/audit record nào hữu ích?

### Bài J — Thay enum

Dữ liệu cũ có `"paid"`, `"settled"`, `"PAID"`, `"refund"`. Thiết kế mapping chỉ khi business owner xác nhận nghĩa từng giá trị. Những values không có ánh xạ phải được xử lý thế nào?

### Bài K — Chỉ số thành công

Sau cleanup, invalid count giảm từ 80.000 về 0 nhưng total document count cũng giảm 80.000. Đó là thành công không? Đề xuất các bước đối soát business và lineage.

### Bài L — TTL trên legacy data

Nhiều session records có `expiresAt` là String/Null, một số Date đã cũ hơn 30 ngày.

1. Thêm TTL index có xóa hết mọi record ngay không?
2. Nếu đổi TTL 90 ngày → 7 ngày, rủi ro gì?
3. Validator có giúp bảo vệ kiểu Date không?
4. Vì sao TTL rollback không khôi phục data đã mất?

### Bài M — Quay lại app cũ

Sau khi đã bật strict validator, deployment ứng dụng mới lỗi và đội muốn rollback app về phiên bản 1. Phiên bản 1 ghi `amountCents` dưới dạng String.

1. Điều gì xảy ra với writes?
2. Có thể giảm validationAction trong incident không? Rủi ro?
3. Cần thiết kế expand/contract để rollback code an toàn thế nào?
4. Khi nào nên forward-fix thay vì rollback?

### Bài N — MongoDB 9.0 constraint

Một collection có 2 triệu documents và validator strict, audit thấy 30 invalid documents.

1. Có thể nâng `constraint` ngay không?
2. `prepareConstraintValidationLevel` để làm gì?
3. Upgrade có quét toàn collection không?
4. Vì sao phải dự báo CPU/I/O và thời gian?
5. Muốn đổi validator sau `constraint` phải làm gì?

### Bài O — Sự cố uniqueness trên sharded cluster

Collection sharded theo `{tenantId:1}`. Đội muốn đảm bảo `externalOrderId` unique toàn hệ thống, không phân biệt tenant.

1. Unique `{tenantId:1,externalOrderId:1}` bảo đảm invariant nào?
2. Nó có enforce global externalOrderId unique không?
3. Tại sao shard key rules quan trọng?
4. Có thể cân nhắc collection định danh tập trung/transaction hoặc thiết kế routing nào khác?

### Bài P — Chuẩn bị change ticket

Thiết kế đầy đủ:

- DDL hiện có, validator và indexes snapshot.
- Business owner quyết định remediation.
- Test và môi trường.
- Deployment order.
- Migration progress/metrics.
- Rollback/forward-fix plan.
- Thời điểm go/no-go.
- Backup và diễn tập restore.
- Điều kiện kết thúc change.

## 30. Tài liệu tham khảo MongoDB chính thức

Để triển khai, đối chiếu **đúng server version, featureCompatibilityVersion, sharding topology, driver và quyền hạn**:

- [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — mô hình validator trong MongoDB.
- [Specify Validation Level](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-level/) — `moderate`, `strict` và `constraint` MongoDB 9.0+.
- [Handle Invalid Documents](https://www.mongodb.com/docs/manual/core/schema-validation/handle-invalid-documents/) — `warn`, `error` và `errorAndLog` MongoDB 8.1+.
- [Modify Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/update-schema-validation/) — thay rules qua `collMod`.
- [`$jsonSchema`](https://www.mongodb.com/docs/manual/reference/operator/query/jsonSchema/) — kiểm BSON types, required, enum và nested fields.
- [Find Documents that Don't Match Schema](https://www.mongodb.com/docs/manual/core/schema-validation/query-for-schema-validation/) — audit existing documents theo rule.
- [Convert Existing Index to Unique Index](https://www.mongodb.com/docs/manual/core/index-unique/convert-to-unique/) — `prepareUnique`, `dryRun` và finalize.
- [`collMod` Command](https://www.mongodb.com/docs/manual/reference/command/collMod/) — index/validator/TTL options.
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — missing/null, compound uniqueness và multikey.
- [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/) — partialFilterExpression và partial unique.
- [Maintain Uniqueness in Sharded Clusters](https://www.mongodb.com/docs/manual/tutorial/maintain-uniqueness-in-sharded-clusters/) — shard key prefix và giới hạn unique.
- [TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/) — tự động xóa và rủi ro đổi retention.
- [Index Builds on Populated Collections](https://www.mongodb.com/docs/manual/core/index-creation/) — resource cost, locking và replicated builds.
- [MongoDB BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/) — Int32, Int64, Decimal128, Date, Null và các kiểu khác.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — acknowledgement semantics và timeout không rõ outcome.
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — thay đổi atomic nhiều documents khi phù hợp.
- [MongoDB Atlas Monitoring](https://www.mongodb.com/docs/atlas/monitor-cluster-metrics/) — giám sát tài nguyên managed deployments.

**Ghi chú phiên bản:** `collMod` chuyển index non-unique thành unique được hỗ trợ từ MongoDB 6.0; `validationAction:"errorAndLog"` từ MongoDB 8.1; `validationLevel:"constraint"` từ MongoDB 9.0. Các mốc này không thay cho việc kiểm tra phiên bản/FCV/tier hiện có trước khi chạy production.

## 31. Kết luận

Tạo ràng buộc trên MongoDB collection đã có dữ liệu là một **migration về cả kỹ thuật và hợp đồng nghiệp vụ**.

1. **Định nghĩa chính xác invariant** trước khi sửa: required/nullable/BSON type, per-tenant uniqueness, retention và exception policy.
2. **Audit có phân loại**: missing, null, wrong type, enum, normalization, duplicates; không lấy một con số `countDocuments` làm toàn bộ bằng chứng.
3. **Ngăn lỗi mới** trước khi dọn hết lỗi cũ: deploy writers đúng contract, dùng `moderate + error` và `prepareUnique` khi phiên bản/index cho phép.
4. **Làm sạch theo business source of truth**, không tự xóa duplicates hoặc thay financial values bằng 0. Backfill theo batch, CAS, idempotency và checkpoint.
5. **Đối soát lại** cả document validity, uniqueness, business totals và references; ghi audit cho các record không thể tự sửa.
6. **Bật ràng buộc đích có kiểm soát**: `unique:true` sau dryRun; `strict + error` sau audit; cân nhắc `constraint` trên MongoDB 9.0+ khi cần bảo đảm toàn collection.
7. **Giữ khả năng phục hồi**: backup/restore, rollback config và forward-fix; hiểu rằng data đã xóa/merge hoặc unique đã finalize không tự quay lại bằng một nút bấm.
8. **Theo dõi sau rollout** cả lỗi validator/duplicate, p95/p99, replication, disk, schema versions và kết quả nghiệp vụ.

**Nguyên tắc cốt lõi:** ràng buộc mới không phải một lệnh “dọn rác tự động”. Nó là một cam kết dài hạn rằng **dữ liệu quá khứ đã được đối soát và mọi đường ghi tương lai đều tuân theo cùng một hợp đồng** — kể cả khi ứng dụng được deploy, rollback, retry, scale-out hoặc gặp sự cố.

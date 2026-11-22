# Kiểm thử BSON, null, trường thiếu, mảng và schema validation trong MongoDB

> **Module:** Database Engine Document MongoDB  
> **Chương:** Kiểm thử  
> **Bài học:** Kiểm thử BSON, null, trường thiếu, mảng và schema validation

## 1. Vì sao những trường hợp “nhỏ” này làm hỏng dữ liệu thật?

Một ứng dụng Java nhận hồ sơ đơn hàng qua API và ghi MongoDB. Trong môi trường phát triển, dữ liệu thường có dạng:

```javascript
{
  _id: ObjectId("66a000000000000000000414"),
  orderCode: "LAB-414",
  amountCents: NumberLong("125000"),
  contact: {
    email: "demo@example.test"
  },
  tags: ["paid", "priority"],
  lines: [
    { sku: "BOOK-A", quantity: NumberInt(2) }
  ],
  cancelledAt: null
}
```

Khi có dữ liệu thật, cùng collection có thể chứa:

- `amountCents` là `int` ở document cũ, `long` ở document mới, `double` do lỗi chuyển đổi và `string` do API nhập sai.
- `contact` có khi là object, khi là `null`, khi hoàn toàn vắng mặt.
- `tags` có thể là mảng rỗng, bị thiếu, chứa `null`, có phần tử lặp hoặc thậm chí là một chuỗi thay vì mảng.
- `lines` có nhiều phần tử; truy vấn bằng dot notation có thể ghép các điều kiện từ **hai phần tử khác nhau**.
- `cancelledAt: null` có ý nghĩa “chưa hủy”, còn field thiếu có nghĩa “client cũ chưa gửi thông tin”.
- Validator mới có thể từ chối update trên document cũ dù lệnh chỉ sửa một field không liên quan.
- Ứng dụng Java dùng `Document.get("field")`, thấy `null` rồi **không biết field thật sự null hay missing**.

Nếu unit test chỉ so sánh JSON như chuỗi, nhiều lỗi không được phát hiện: BSON có kiểu số và thời gian riêng, MongoDB có semantics truy vấn `null`/array riêng, validator kiểm tra **document sau thao tác ghi**, và driver Java có cơ chế codec chuyển kiểu.

Bài học trình bày cách xây dựng **bộ kiểm thử có kết quả kỳ vọng rõ ràng** cho MongoDB, từ `mongosh` tới Java Sync Driver/JUnit 5, và cách kiểm chứng validation trên collection đã có dữ liệu.

### 1.1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt các kiểu BSON quan trọng: `int`, `long`, `double`, `decimal`, `date`, `timestamp`, `objectId`, `binData`, `null`, `array` và `object`.
2. Viết test giữ nguyên BSON type qua serialize → insert → read.
3. Phân biệt **null**, **field thiếu**, **undefined legacy**, chuỗi rỗng, 0, false, object rỗng và array rỗng.
4. Dự đoán và kiểm thử `{field: null}`, `$exists`, `$type`, `$ne`, `$ifNull`.
5. Kiểm thử truy vấn mảng theo phần tử, vị trí, mảng đầy đủ và cùng một phần tử bằng `$elemMatch`.
6. Viết validator dùng `$jsonSchema`, `bsonType`, `required`, `items`, `enum` và các giới hạn giá trị.
7. Hiểu hành vi của `validationLevel: strict/moderate/constraint` và `validationAction: error/warn/errorAndLog` theo phiên bản.
8. Kiểm thử insert, update, replace, upsert, partial update và dữ liệu legacy.
9. Xây integration tests Java với collection riêng, dữ liệu giả, không ảnh hưởng các test khác.
10. Áp dụng kiểm thử hồi quy khi schema, mapper hoặc driver đổi phiên bản.

## 2. Bốn nguyên tắc thiết kế kiểm thử MongoDB

### 2.1. Kiểm tra **BSON**, không chỉ JSON nhìn thấy

```text
HTTP JSON
   |
   v
Java DTO / Jackson
   |
   v
MongoDB Java Driver / Codec
   |
   v
BSON bytes
   |
   v
MongoDB validation + query engine
   |
   v
BSON decoded to Java objects
   |
   v
Application business behavior
```

Một value hiển thị là `42` trong JSON có thể đi thành BSON `int32`, `int64` hoặc `double`. String `"2026-11-14T00:00:00Z"` không tự là BSON Date nếu mapper chưa chuyển kiểu. Cần test ở các ranh giới này.

### 2.2. Kiểm tra **trạng thái**, không chỉ một giá trị

Với field `notes`, ít nhất có các trạng thái:

| Trạng thái | Document | Có field? | BSON type |
| --- | --- | --- | --- |
| Thiếu | `{}` | Không | `missing` trong aggregation expression |
| Null | `{notes: null}` | Có | `null` |
| Chuỗi rỗng | `{notes: ""}` | Có | `string` |
| Chuỗi có nội dung | `{notes: "x"}` | Có | `string` |
| Mảng rỗng | `{notes: []}` | Có | `array` |
| Object rỗng | `{notes: {}}` | Có | `object` |
| Boolean false | `{notes: false}` | Có | `bool` |
| Số không | `{notes: NumberInt(0)}` | Có | `int` |

**Không gộp các trạng thái này thành “falsy/empty”** trong application hoặc test assertion, trừ khi business contract cố ý làm vậy.

### 2.3. Chạy test với MongoDB thực khi kiểm semantics server

Một mock repository không thể bảo đảm hành vi thật của:

- `{field: null}` hoặc `$exists`;
- numeric BSON type và codec;
- `$elemMatch` với các phần tử mảng;
- `$jsonSchema` khi insert/update;
- unique/partial/multikey indexes;
- lỗi `DocumentValidationFailure` và server version.

Unit test vẫn hữu ích cho business logic thuần, nhưng các quy tắc nói trên cần **integration test với MongoDB Server** tương thích deployment production.

### 2.4. Dữ liệu kiểm thử phải độc lập và khôi phục được

- Dùng dữ liệu **giả**, không chứa PII hay thông tin khách hàng.
- Tạo database/collection riêng hoặc tên collection ngẫu nhiên cho từng test.
- Gắn `runId` duy nhất vào mọi test document.
- Không dùng `deleteMany({})` hoặc `dropDatabase()` trên môi trường chia sẻ.
- Không sửa FCV, server-level parameters hay index production chỉ để test.
- Ghi lại server/driver version, BSON types, query và kết quả mong đợi.

## 3. BSON là gì và vì sao type quan trọng?

BSON (Binary JSON) là định dạng document được MongoDB lưu/truyền. Ngoài các loại JSON quen thuộc, BSON có một số kiểu riêng.

### 3.1. Bảng kiểu dữ liệu thường gặp

| BSON | Ví dụ trong `mongosh` | Java Sync Driver dùng thường gặp | Rủi ro kiểm thử |
| --- | --- | --- | --- |
| `string` | `"hello"` | `String` | Unicode, normalization, collation |
| `int` (Int32) | `NumberInt(42)` | `Integer` | Tràn miền số 32-bit |
| `long` (Int64) | `NumberLong("42")` | `Long` | Mất chính xác khi qua JS Number |
| `double` | `NumberDouble("3.14")` | `Double` | Floating-point rounding, NaN |
| `decimal` | `NumberDecimal("12.50")` | `Decimal128` | Precision, scale và chuyển BigDecimal |
| `bool` | `true` | `Boolean` | False khác missing/null |
| `date` | `ISODate("2026-11-14T00:00:00Z")` | `java.util.Date` hoặc codec khác | UTC, milliseconds, timezone |
| `timestamp` | `Timestamp({t: ..., i: ...})` | `BsonTimestamp` | Không giống Date, thường dùng internals/oplog |
| `objectId` | `ObjectId()` | `ObjectId` | Không tự là String |
| `binData` | `BinData(...)` | `Binary` / `BsonBinary` | UUID subtype, bytes, encoding |
| `null` | `null` | `null` / `BsonNull` | Khác field thiếu |
| `array` | `[1, 2]` | `List` / `BsonArray` | Thứ tự, type từng phần tử, multikey |
| `object` | `{a:1}` | `Document` / `BsonDocument` | Field nested và thiếu |

Trong Java, `org.bson.Document` là map mềm kiểu `String → Object`. `BsonDocument` chứa các `BsonValue` có type rõ, phù hợp khi cần assert đúng BSON type.

### 3.2. Cùng số 42 không có nghĩa cùng BSON type

```javascript
const sample = {
  int32: NumberInt(42),
  int64: NumberLong("42"),
  doubleNumber: NumberDouble("42"),
  decimalNumber: NumberDecimal("42.00")
};

db.sample.insertOne(sample);
```

Dùng aggregation để nhìn type thực được lưu:

```javascript
db.sample.aggregate([
  {
    $project: {
      int32Type: { $type: "$int32" },
      int64Type: { $type: "$int64" },
      doubleType: { $type: "$doubleNumber" },
      decimalType: { $type: "$decimalNumber" }
    }
  }
]);
```

Kết quả kỳ vọng là `int`, `long`, `double`, `decimal` theo các field tương ứng.

**Lưu ý:** MongoDB query comparison có quy tắc so sánh số theo nhóm numeric, nên một predicate equality có thể không phân biệt chặt Int32/Int64/Double. Nếu bài toán yêu cầu **đúng BSON type**, hãy kiểm tra `$type` hoặc codec/validator, không dùng kết quả `find({x:42})` làm bằng chứng type giống nhau.

### 3.3. Số lớn và JavaScript

Số nguyên có độ lớn vượt khoảng an toàn của IEEE-754 double (`Number.MAX_SAFE_INTEGER` trong JavaScript) có thể bị mất chữ số nếu truyền qua JS Number.

Sai:

```javascript
// Không lấy con số nguyên 64-bit cực lớn từ JS Number
// rồi giả định chính xác tuyệt đối.
const unsafe = 9007199254740993;
```

Đúng hơn:

```javascript
const exact = NumberLong("9007199254740993");
```

Trong Java:

```java
Document d = new Document()
    .append("count32", 42)
    .append("count64", 42L);
```

`42` là `Integer` và thường serialize thành BSON Int32; `42L` là `Long` và thường thành BSON Int64. Khi dùng `Document`, đọc `getInteger("count64")` có thể gây lỗi cast; hãy biết loại dữ liệu đang đọc hoặc dùng `BsonDocument` khi test type.

### 3.4. Decimal128 cho tiền tệ

```java
import org.bson.types.Decimal128;
import java.math.BigDecimal;

Decimal128 amount = new Decimal128(
    new BigDecimal("123456.78")
);

Document d = new Document("price", amount);
```

Không đi đường:

```java
new BigDecimal(0.1)
```

nếu nghiệp vụ cần biểu diễn thập phân đúng ý định: `double 0.1` không có representation nhị phân chính xác. Ưu tiên `new BigDecimal("0.10")`, hoặc lưu tiền ở đơn vị nhỏ nhất bằng integer với miền giá trị rõ ràng.

**Kiểm thử tiền tệ:** value, type, scale/rounding theo business contract, số âm, tràn miền và serialization round-trip.

### 3.5. Ngày giờ: BSON Date khác String

```javascript
{
  atDate: ISODate("2026-11-14T00:00:00.000Z"),
  atString: "2026-11-14T00:00:00.000Z"
}
```

Hai giá trị nhìn giống nhau nhưng type khác. Date là milliseconds từ Unix epoch theo UTC; MongoDB không lưu timezone gốc trong BSON Date.

Kiểm thử:

- Input từ timezone Asia/Ho_Chi_Minh có ra đúng instant UTC không?
- Round-trip có giữ milliseconds không?
- Giá trị `null`/missing cho optional date?
- Sort/filter trên Date có dùng index, không so lexicographic String?
- DST khi business dùng timezone địa phương khác có được xử lý ở application?

Không dùng `Timestamp` của BSON để thay Date cho thời điểm nghiệp vụ; `Timestamp` chứa seconds và increment với semantics riêng.

### 3.6. ObjectId, String và UUID

```javascript
{
  _id: ObjectId("66a000000000000000000414")
}
```

khác với:

```javascript
{
  _id: "66a000000000000000000414"
}
```

Mặc dù hiển thị chung 24 ký tự hex, `ObjectId` và `String` là hai kiểu khác nhau trong query/index.

Với UUID, BSON Binary subtype (chuẩn và legacy) ảnh hưởng kết quả đọc giữa driver. Kiểm thử `UuidRepresentation.STANDARD` và di trú legacy subtype nếu dữ liệu cũ có UUID, không đoán mọi 16-byte binary đều là cùng một UUID.

### 3.7. Extended JSON không phải JSON thông thường

MongoDB Extended JSON biểu diễn các kiểu BSON:

```json
{
  "i64": { "$numberLong": "42" },
  "money": { "$numberDecimal": "15.50" },
  "createdAt": {
    "$date": "2026-11-14T00:00:00Z"
  },
  "objectId": {
    "$oid": "66a000000000000000000414"
  }
}
```

Nếu test đổi dữ liệu sang JSON thường bằng Jackson hoặc frontend, thông tin kiểu có thể bị mất.

Hai dạng quan trọng:

- **Canonical Extended JSON:** giữ tag type chi tiết.
- **Relaxed Extended JSON:** dễ đọc nhưng có thể không giữ phân biệt mọi type khi đi qua parser không tương thích.

Đừng so sánh `toJson()` như chuỗi tuyệt đối nếu khác nhau về thứ tự key/định dạng Extended JSON; nên assert trên BSON values và business values.

## 4. Null, missing, empty, false và zero: ma trận kiểm thử cơ sở

### 4.1. Bộ fixture rõ ràng

Trong một collection lab:

```javascript
[
  { _id: "missing" },
  { _id: "explicit-null", value: null },
  { _id: "empty-string", value: "" },
  { _id: "zero", value: NumberInt(0) },
  { _id: "false", value: false }
]
```

Hãy ghi expected IDs **trước khi chạy** query.

### 4.2. Truy vấn `{value: null}`

```javascript
db.c.find({ value: null });
```

MongoDB khớp:

- `"missing"` — không có field.
- `"explicit-null"` — field có BSON Null.

Nó không khớp chuỗi rỗng, 0 hay false.

**Đây là khác biệt trọng yếu so với nhiều SQL query semantics** và là nguồn lỗi khi application dùng cùng một filter cho “chưa khai báo” và “đã khai báo null”.

### 4.3. Truy vấn field **không tồn tại**

```javascript
db.c.find({
  value: { $exists: false }
});
```

Chỉ khớp `"missing"` trong bộ fixture trên.

`$exists:false` là kiểm tra **sự hiện diện** của field, không phải kiểm tra `null`.

### 4.4. Truy vấn field **tồn tại, kể cả null**

```javascript
db.c.find({
  value: { $exists: true }
});
```

Khớp `"explicit-null"`, `"empty-string"`, `"zero"` và `"false"`.

Một field có value `null` vẫn **tồn tại**, không được xem là missing.

### 4.5. Truy vấn BSON Null đúng nghĩa

```javascript
db.c.find({
  value: { $type: "null" }
});
```

Trong fixture scalar, chỉ khớp `"explicit-null"`. Có thể dùng BSON type number 10:

```javascript
db.c.find({
  value: { $type: 10 }
});
```

Cẩn thận khi field là **array**: query predicate `$type` có thể match type của **phần tử trong array**, không chỉ type của field toàn bộ. Tránh đưa array chứa null vào fixture scalar rồi suy ra count luôn bằng 1.

### 4.6. `$ne: null`

```javascript
db.c.find({
  value: { $ne: null }
});
```

Với fixture scalar, trả các document mà field tồn tại và khác null: `"empty-string"`, `"zero"`, `"false"`.

Đừng tự đổi:

```javascript
{ value: { $ne: null } }
```

thành một biểu thức SQL không tương đương; nếu có array/mixed types, cần test thêm theo semantics query operator.

### 4.7. Bảng kết quả kỳ vọng

| Bộ lọc | ID khớp trong fixture 5 document |
| --- | --- |
| `{value:null}` | `missing`, `explicit-null` |
| `{value:{$exists:false}}` | `missing` |
| `{value:{$exists:true}}` | `explicit-null`, `empty-string`, `zero`, `false` |
| `{value:{$type:"null"}}` | `explicit-null` |
| `{value:{$ne:null}}` | `empty-string`, `zero`, `false` |
| `{value:""}` | `empty-string` |
| `{value:0}` | `zero` với bộ fixture này |
| `{value:false}` | `false` |

Không đưa document `{value:[null]}` vào bảng này: **array traversal** tạo thêm các trường hợp khớp, được kiểm riêng ở phần mảng.

## 5. Null trong Java: `Document.get()` không đủ

### 5.1. Phân biệt missing và explicit null

```java
Document missing = new Document("_id", "missing");

Document explicitNull = new Document("_id", "explicit-null")
    .append("value", null);

System.out.println(missing.get("value"));       // null
System.out.println(explicitNull.get("value"));  // null
```

Hai kết quả giống nhau. Muốn phân biệt:

```java
boolean missingHasField = missing.containsKey("value");
boolean nullHasField = explicitNull.containsKey("value");

// false vs true
```

Tương đương với `BsonDocument`:

```java
BsonDocument missingBson = new BsonDocument();

BsonDocument nullBson = new BsonDocument(
    "value", BsonNull.VALUE
);

boolean hasField = nullBson.containsKey("value");
boolean isNullValue = nullBson.get("value").isNull();
```

Kiểm thử phải assert **cả presence và value**.

### 5.2. POJO codec và mapper có thể biến mất trạng thái missing

Một DTO:

```java
public class Profile {
    private String nickname;
    // getters/setters
}
```

không tự giữ được cả ba trạng thái:

1. JSON không chứa key `nickname`.
2. JSON chứa `"nickname":null`.
3. Java field `nickname == null` sau deserialization.

Kết quả phụ thuộc Jackson configuration, POJO codec annotations, field defaults và mapper update semantics.

Nếu nghiệp vụ cần phân biệt **PATCH: không đổi field** với **PATCH: đặt field null**, phải thiết kế command/DTO có field presence rõ ràng (ví dụ một wrapper thể hiện absent/present, JSON Patch, hoặc tracking set of supplied fields). Không chỉ dựa vào `Optional<String>` hay Java `null` mà chưa kiểm thử đường serialization.

### 5.3. `$set:null` khác `$unset`

```javascript
db.c.updateOne(
  { _id: "case-1" },
  { $set: { nickname: null } }
);
```

Sau lệnh, `nickname` **tồn tại với giá trị null**.

```javascript
db.c.updateOne(
  { _id: "case-1" },
  { $unset: { nickname: "" } }
);
```

Sau lệnh, `nickname` **không tồn tại**.

Nếu validator có `required:["nickname"]`, thao tác `$unset` có thể bị từ chối; `$set:null` chỉ được chấp nhận khi property cho phép BSON Null.

### 5.4. `$ifNull` cố ý gộp null và missing

Trong aggregation:

```javascript
{
  $project: {
    normalized: {
      $ifNull: ["$nickname", "anonymous"]
    }
  }
}
```

`$ifNull` coi field missing/undefined như null. Phù hợp khi nghiệp vụ muốn fallback, **không phù hợp khi cần phân biệt hai trạng thái**.

Dùng aggregation `$type` nếu cần phân loại:

```javascript
db.c.aggregate([
  {
    $project: {
      valueType: { $type: "$value" }
    }
  }
]);
```

Kết quả expression type cho field thiếu là `"missing"`, còn BSON Null là `"null"`.

### 5.5. BSON Undefined là kiểu legacy

BSON có kiểu `undefined` (type 6) nhưng đã **deprecated**. Không dùng `undefined` làm sentinel mới. Một hệ thống cũ vẫn có thể tồn tại dữ liệu kiểu này; cần kiểm tra theo server/driver version và migrate có kiểm soát.

Đừng coi mọi JSON `undefined` trong JavaScript là BSON Null. Các phiên bản driver và cấu hình serialization có thể có hành vi khác nhau; muốn kiểm kiểu thực phải đọc BSON sau khi persist.

## 6. Trường lồng nhau: dot notation và field thiếu

### 6.1. Ba trạng thái profile

```javascript
[
  { _id: "p-missing" },
  { _id: "p-null", profile: null },
  { _id: "p-object", profile: { city: "HCM" } },
  { _id: "p-empty", profile: {} }
]
```

Truy vấn:

```javascript
{ "profile.city": { $exists: false } }
```

có thể match:

- profile thiếu;
- profile null;
- profile object nhưng thiếu city.

Ngược lại:

```javascript
{ "profile.city": "HCM" }
```

match document có nested city phù hợp.

### 6.2. Vì sao `{"profile.city":null}` cần test kỹ?

Với dotted path, việc path không tồn tại có thể dẫn đến null-query match theo semantics query, nhưng nếu parent là array, object, null hoặc shape bất thường, kết quả có thể khác trực giác application.

Đừng dùng `{"profile.city":null}` để kết luận duy nhất “city được đặt null”. Nếu business cần phân biệt explicit null trên một nested object, nên quy định schema parent là object, dùng `$type`/`$exists` và kiểm với fixtures cho parent missing/null/array.

### 6.3. Không so sánh nguyên object tùy tiện

```javascript
db.c.find({
  profile: {
    city: "HCM",
    country: "VN"
  }
});
```

So sánh embedded document nguyên vẹn có thể phụ thuộc **cấu trúc và thứ tự field**, khác với:

```javascript
db.c.find({
  "profile.city": "HCM",
  "profile.country": "VN"
});
```

Nếu ứng dụng chỉ muốn kiểm các fields con, dùng dot notation/`$elemMatch` phù hợp thay vì equality nguyên object thiếu kiểm thử.

## 7. Kiểm thử mảng: membership, equality, order và size

### 7.1. Fixture mảng cơ bản

```javascript
[
  { _id: "a1", tags: ["java", "mongodb"] },
  { _id: "a2", tags: ["mongodb", "java"] },
  { _id: "a3", tags: ["java"] },
  { _id: "a4", tags: [] },
  { _id: "a5" }
]
```

### 7.2. Match một phần tử

```javascript
db.c.find({ tags: "java" });
```

Khớp `a1`, `a2`, `a3`: predicate scalar với field dạng array thường khớp khi có phần tử phù hợp.

### 7.3. Match **toàn bộ mảng theo thứ tự**

```javascript
db.c.find({
  tags: ["java", "mongodb"]
});
```

Trong fixture trên, khớp `a1`, không khớp `a2` vì thứ tự khác và không khớp `a3` vì thiếu phần tử. Array equality không đồng nghĩa set equality.

### 7.4. Match mảng chứa đủ phần tử, không bắt thứ tự

```javascript
db.c.find({
  tags: {
    $all: ["java", "mongodb"]
  }
});
```

Khớp `a1` và `a2` trong fixture. `$all` chủ yếu kiểm membership, không phải **số lần xuất hiện** hoặc thứ tự.

### 7.5. Match chính xác độ dài

```javascript
db.c.find({
  tags: { $size: 0 }
});
```

Chỉ khớp `a4`. Field missing `a5` không giống mảng rỗng.

`$size` nhận số phần tử cụ thể; nó không hỗ trợ một range kiểu `{$size:{$gt:2}}`. Nếu cần tìm độ dài lớn hơn 2, có thể thiết kế field `tagsCount` được duy trì nhất quán hoặc dùng expression theo yêu cầu/tài nguyên.

### 7.6. Match theo vị trí

```javascript
db.c.find({
  "tags.0": "java"
});
```

Khớp `a1` và `a3`; không khớp `a2` vì phần tử đầu là mongodb.

Indexing cho positional/dot-notation array queries cần hiểu multikey semantics. Không xem array như một scalar một giá trị duy nhất trong index.

### 7.7. Field chứa String khác field chứa Array

```javascript
{
  _id: "bad",
  tags: "java"
}
```

Truy vấn `{tags:"java"}` có thể **cũng match** document này. Nếu yêu cầu tags phải là array, riêng query membership **không kiểm được schema**. Dùng validator `bsonType:"array"` hoặc query type/filter bổ sung.

## 8. `$elemMatch`: nhiều điều kiện phải cùng đúng trên **một phần tử**

### 8.1. Lỗi kinh điển với mảng object

Fixture:

```javascript
{
  _id: "order-cross-match",
  lines: [
    { sku: "BOOK-A", quantity: NumberInt(1) },
    { sku: "BOOK-B", quantity: NumberInt(8) }
  ]
}
```

Truy vấn sai nếu mục tiêu là tìm **một line BOOK-A có quantity >= 5**:

```javascript
db.orders.find({
  "lines.sku": "BOOK-A",
  "lines.quantity": { $gte: 5 }
});
```

**Có thể match document trên!** Điều kiện sku khớp phần tử thứ nhất, quantity khớp phần tử thứ hai. Hai predicates không bị buộc phải thỏa trên cùng phần tử.

### 8.2. Truy vấn đúng với `$elemMatch`

```javascript
db.orders.find({
  lines: {
    $elemMatch: {
      sku: "BOOK-A",
      quantity: { $gte: 5 }
    }
  }
});
```

Document `order-cross-match` **không match**, vì không có một phần tử nào vừa `sku:"BOOK-A"` vừa `quantity >=5`.

Một document khác:

```javascript
{
  _id: "order-match",
  lines: [
    { sku: "BOOK-A", quantity: NumberInt(6) }
  ]
}
```

thì match.

### 8.3. Mảng số và các khoảng điều kiện

Fixture:

```javascript
{
  _id: "s-range",
  scores: [65, 105]
}
```

Truy vấn:

```javascript
{
  scores: {
    $gt: 80,
    $lt: 100
  }
}
```

có thể match khi hai điều kiện do **hai phần tử** khác nhau đáp ứng: `105 > 80` và `65 < 100`.

Nếu muốn một score nằm trong khoảng:

```javascript
{
  scores: {
    $elemMatch: {
      $gt: 80,
      $lt: 100
    }
  }
}
```

Fixture `[65,105]` không match. Đây là một trong các kiểm thử hồi quy quan trọng nhất khi chuyển query từ scalar sang array.

### 8.4. `$elemMatch` còn buộc field là array

Nếu field có dạng:

```javascript
{ _id: "object", lines: { sku: "BOOK-A", quantity: 6 } }
```

thì `$elemMatch` sẽ **không match** vì `lines` không phải array. Dot notation có thể match fields trong object đơn; test cả hai để phát hiện dữ liệu sai shape.

### 8.5. Mảng có object, scalar và null trộn nhau

Ví dụ dữ liệu lỗi:

```javascript
{
  lines: [
    { sku: "A", quantity: 1 },
    null,
    "invalid-element"
  ]
}
```

Đừng chỉ test mảng object “đẹp”. Khi schema cho phép mảng hỗn hợp, query result có thể bất ngờ; validator `items` giúp chặn element sai kiểu ngay từ write path.

## 9. Mảng chứa null, mảng rỗng và field missing

### 9.1. Bốn trường hợp khác nhau

```javascript
[
  { _id: "array-missing" },
  { _id: "array-null", items: null },
  { _id: "array-empty", items: [] },
  { _id: "array-with-null", items: [null] }
]
```

Điểm cần kiểm:

- `$exists:false` chỉ nhận field thiếu.
- `$size:0` nhận array rỗng, không nhận null/missing.
- Query `{items:null}` có semantics null/missing **và array element matching**, nên có thể nhận cả array chứa null.
- `$type:"null"` với array có thể match **phần tử null** trong array theo semantics của query predicate.
- `$type:"array"` giúp yêu cầu field là array trong các trường hợp tiêu chuẩn.

Do đó nếu test chỉ có field null/missing mà không có `[]` và `[null]`, vẫn chưa bao phủ lỗi đặc trưng của array.

### 9.2. Nested array, object và exact-match

Thêm các cases:

```javascript
[
  { _id: "nested-array", items: [["A"], ["B"]] },
  { _id: "array-object", items: [{ code: "A" }] },
  { _id: "wrong-scalar", items: "A" }
]
```

Truy vấn scalar có thể match phần tử trong array hoặc field scalar; exact array equality có quy tắc thứ tự riêng. Với array lồng sâu, không dựa vào trực giác “MongoDB tự duyệt mọi cấp” mà không kiểm truy vấn cụ thể.

### 9.3. `$type` dạng query khác `$type` dạng aggregation expression

Query predicate:

```javascript
db.c.find({
  items: { $type: "string" }
});
```

có thể match array chứa String element.

Aggregation expression:

```javascript
db.c.aggregate([
  {
    $project: {
      itemsType: { $type: "$items" }
    }
  }
]);
```

trả kiểu của **giá trị expression**: array sẽ là `"array"`, và field thiếu sẽ là `"missing"`.

Hai cú pháp `$type` có ngữ cảnh semantics khác nhau; test nào cần kiểm type của field **nguyên khối** nên ưu tiên BSON readback/aggregation expression hoặc validator.

## 10. Cập nhật mảng và kiểm thử tính idempotent

### 10.1. `$push` và `$addToSet` khác nhau

```javascript
db.c.updateOne(
  { _id: "a1" },
  { $push: { tags: "java" } }
);
```

`$push` có thể thêm phần tử đã tồn tại, tạo duplicate.

```javascript
db.c.updateOne(
  { _id: "a1" },
  { $addToSet: { tags: "java" } }
);
```

`$addToSet` chỉ thêm khi phần tử chưa có theo equality semantics. Nhưng nó **không dọn duplicates đã tồn tại** trong mảng. Với các embedded documents, equality và thứ tự field có thể có ảnh hưởng riêng.

### 10.2. `$pull`

```javascript
db.c.updateOne(
  { _id: "a1" },
  { $pull: { tags: "java" } }
);
```

Xóa các phần tử phù hợp. Nếu test kỳ vọng chỉ xóa “một phần tử đầu tiên”, cần hiểu `$pull` sẽ loại bỏ tất cả các phần tử match trong mảng.

### 10.3. Positional update và `arrayFilters`

```javascript
db.orders.updateOne(
  { _id: "order-match" },
  {
    $set: {
      "lines.$[line].checked": true
    }
  },
  {
    arrayFilters: [
      {
        "line.sku": "BOOK-A",
        "line.quantity": { $gte: 5 }
      }
    ]
  }
);
```

Bài test cần chứng minh:

- Chỉ các elements đúng filter bị đổi.
- Phần tử khác giữ nguyên.
- Không tạo/đổi field ngoài dự kiến.
- Các update có thể bị schema validation từ chối nếu kết quả sai kiểu.
- Với concurrent updates, cần điều kiện version/transaction nếu business invariant yêu cầu.

### 10.4. Mảng và dedup không phải chuyện index giải quyết hết

Một unique multikey index có semantics unique giữa **các documents**, nhưng không phải công cụ bảo đảm mọi phần tử của cùng một array đều khác nhau. Nếu yêu cầu cấm duplicate trong array, cân nhắc:

- `uniqueItems:true` trong validator khi phù hợp.
- `$addToSet` cho writes.
- Logic application kiểm type/canonicalization.
- Tests cho duplicated scalar/object elements và concurrent writers.

## 11. Schema validation: MongoDB kiểm cái gì?

### 11.1. `$jsonSchema` không phải Java DTO validator

MongoDB cho phép khai báo validator ngay trong collection:

```javascript
db.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["orderCode", "amountCents"],
      properties: {
        orderCode: { bsonType: "string" },
        amountCents: { bsonType: "long" }
      }
    }
  }
});
```

Validator chạy ở phía MongoDB Server trên các insert/update thuộc phạm vi validation. Nó bảo vệ cả khi một service khác ghi trực tiếp không qua Java DTO validator.

Nhưng MongoDB `$jsonSchema` **không hỗ trợ toàn bộ JSON Schema draft thông thường** theo cùng cách. Kiểm tài liệu MongoDB Server cho keywords cụ thể và cú pháp `bsonType`.

### 11.2. `required` chỉ kiểm **sự hiện diện**

Ví dụ:

```javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["nickname"],
    properties: {
      nickname: {
        bsonType: ["string", "null"]
      }
    }
  }
}
```

- `{}` → **invalid** vì nickname missing.
- `{nickname:null}` → **valid** vì field có và type null được cho phép.
- `{nickname:""}` → **valid** về type nếu không yêu cầu minLength.
- `{nickname:5}` → **invalid** vì sai type.

Nếu đổi property thành `bsonType:"string"`:

- `{nickname:null}` cũng **invalid**;
- `{nickname:"x"}` valid;
- `{}` vẫn invalid do required.

Muốn **optional nhưng không null**, chỉ bỏ nickname khỏi `required` và để `bsonType:"string"`.

### 11.3. Ma trận 4 hợp đồng cho field

| Required? | Allowed type | Missing | Null | String |
| --- | --- | --- | --- | --- |
| Không | `string` | Hợp lệ | Sai | Hợp lệ |
| Có | `string` | Sai | Sai | Hợp lệ |
| Không | `["string","null"]` | Hợp lệ | Hợp lệ | Hợp lệ |
| Có | `["string","null"]` | Sai | Hợp lệ | Hợp lệ |

Đây là một bảng test thiết yếu cho mỗi optional/nullable field.

### 11.4. Value constraints

```javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["orderCode", "amountCents"],
    properties: {
      orderCode: {
        bsonType: "string",
        minLength: 3,
        maxLength: 40,
        pattern: "^[A-Z0-9-]+$"
      },
      amountCents: {
        bsonType: ["int", "long"],
        minimum: 0
      },
      status: {
        enum: ["CREATED", "PAID", "CANCELLED"]
      }
    }
  }
}
```

Các ca cần test:

- String rỗng, quá ngắn/quá dài.
- Ký tự Unicode, dấu cách và ký tự điều khiển.
- Số -1, 0 và giá trị boundary.
- Int32/Int64/Double/Decimal128 có cùng số biểu diễn.
- Enum đúng/sai chữ hoa.
- Required field missing/null.

Đừng chỉ test happy path với một document hợp lệ.

## 12. Validator cho array và object nested

### 12.1. Tập hợp các phần tử phải có shape đúng

```javascript
const orderValidator = {
  $jsonSchema: {
    bsonType: "object",
    required: [
      "runId",
      "orderCode",
      "amountCents",
      "lines"
    ],
    properties: {
      runId: {
        bsonType: "string",
        minLength: 1
      },
      orderCode: {
        bsonType: "string",
        minLength: 1
      },
      amountCents: {
        bsonType: ["int", "long"],
        minimum: 0
      },
      note: {
        bsonType: ["string", "null"]
      },
      tags: {
        bsonType: "array",
        uniqueItems: true,
        items: {
          bsonType: "string",
          minLength: 1
        }
      },
      lines: {
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
      }
    }
  }
};
```

Giải thích:

- `lines` bắt buộc có mặt và phải là array.
- `minItems:1` ngăn array rỗng.
- `items` kiểm từng phần tử phải là object.
- Mỗi object cần `sku` và `quantity`.
- `quantity` phải BSON Int32 và tối thiểu 1.
- `tags` là optional array, nhưng nếu có thì từng phần tử là String không rỗng, không trùng theo `uniqueItems`.
- `note` là optional nullable string.
- Không đặt `additionalProperties:false` ở cấp root nếu chưa cân nhắc `_id` và các fields hợp lệ khác: `_id` luôn được MongoDB cấp/lưu và có thể làm validator từ chối ghi.

### 12.2. Ma trận test cho `lines`

| Giá trị `lines` | Expected | Vì sao |
| --- | --- | --- |
| Thiếu | Reject | `required` |
| `null` | Reject | Không phải array |
| `[]` | Reject | `minItems:1` |
| `"BOOK-A"` | Reject | Sai BSON type |
| `[null]` | Reject | Element không phải object |
| `["BOOK-A"]` | Reject | Element không phải object |
| `[{}]` | Reject | Thiếu sku/quantity |
| `[{sku:"BOOK-A"}]` | Reject | Thiếu quantity |
| `[{sku:"BOOK-A",quantity:"2"}]` | Reject | Sai type quantity |
| `[{sku:"BOOK-A",quantity:0}]` | Reject | Min 1 |
| `[{sku:"BOOK-A",quantity:NumberInt(1)}]` | Accept | Đúng type và bound |
| `[{sku:"BOOK-A",quantity:NumberLong("1")}]` | Reject | Validator chỉ cho `int` |
| `[{sku:"BOOK-A",quantity:NumberInt(1)}, null]` | Reject | Mọi element phải hợp lệ |

Đây là các ca giá trị biên, không phải kết quả từ việc chạy code trên production.

### 12.3. Object rỗng và object thừa fields

```javascript
{ profile: {} }
```

khác:

```javascript
{ profile: null }
```

và:

```javascript
{ }
```

Nếu profile optional và property chỉ có `bsonType:"object"`:

- Missing được chấp nhận.
- Null bị từ chối.
- Object rỗng được chấp nhận trừ khi có `required` bên trong object.

Muốn cấm field lạ, có thể dùng `additionalProperties:false` **ở đúng cấp** nhưng phải tính cả `_id` khi áp root-level validation và mọi metadata hợp lệ. Cấm field lạ quá sớm có thể phá rollout backward-compatible.

### 12.4. Mảng nhiều cấp và `items`

Schema:

```javascript
{
  properties: {
    matrix: {
      bsonType: "array",
      items: {
        bsonType: "array",
        items: {
          bsonType: "int"
        }
      }
    }
  }
}
```

Buộc matrix là array của arrays của Int32. Không dùng một `items:{bsonType:"int"}` nếu shape cần là 2 chiều.

Nếu muốn mỗi hàng có số phần tử cố định, cần thêm `minItems`/`maxItems` ở cấp hàng. Nếu business invariant phức tạp hơn, kiểm tra bằng code/transaction thay vì nhồi toàn bộ logic vào validator khó kiểm soát.

## 13. Action và level của validator không đồng nghĩa

### 13.1. `validationAction`: lỗi hay cảnh báo

| Action | Hành vi chính |
| --- | --- |
| `error` | Từ chối ghi invalid; default |
| `warn` | Cho phép ghi invalid, nhưng ghi cảnh báo vào MongoDB log |
| `errorAndLog` | Từ chối invalid và log vi phạm; từ MongoDB 8.1 |

Với `warn`, một insert invalid **có thể thành công**. Nếu test chỉ assert lệnh không ném exception, nó **không chứng minh data đúng schema**.

`errorAndLog` có thêm tác động log volume và rủi ro lộ thông tin; chỉ dùng khi version hỗ trợ và có chính sách xử lý logs.

### 13.2. `validationLevel`: document nào phải được validate

| Level | Hành vi |
| --- | --- |
| `off` | Tắt schema validation |
| `moderate` | Validate inserts và updates trên existing valid documents; updates trên existing invalid documents có thể được chấp nhận |
| `strict` | Validate mọi inserts/updates; default |
| `constraint` | MongoDB 9.0+, yêu cầu mọi document đều phù hợp và có cơ chế kiểm legacy docs khi bật |

**Không nhầm `strict` với “đã sửa toàn bộ dữ liệu cũ”**. Khi chỉ đặt validator strict trên một collection đã có invalid documents, MongoDB không tự quét và migrate chúng ngay. Nhưng update vào legacy invalid document có thể lỗi.

### 13.3. Thử `moderate` với legacy document

Trình tự:

1. Insert document sai **trước khi thêm validator**.
2. Dùng `collMod` thiết lập `validationLevel:"moderate"`, `validationAction:"error"`.
3. Update một field không liên quan trên legacy invalid document.
4. Quan sát update có thể thành công vì document vốn invalid trước update.
5. Insert document mới invalid → bị từ chối.
6. Update một document đang valid thành invalid → bị từ chối.
7. Chuyển sang `strict`.
8. Update document legacy invalid thêm lần nữa → bị từ chối cho đến khi được sửa hợp lệ.

Bước 4 **không phải lỗ hổng ngẫu nhiên**; đó là semantics moderate để hỗ trợ migration dần dữ liệu legacy.

### 13.4. MongoDB 9.0 `constraint`

Theo tài liệu MongoDB 9.0:

- `constraint` cần `validationAction:"error"` hoặc `"errorAndLog"`.
- Khi bật trên collection đã tồn tại, cần quy trình chuẩn bị bằng `prepareConstraintValidationLevel`.
- MongoDB kiểm tra các existing documents; nếu có vi phạm, upgrade thất bại.
- Trong level này không thể tự ý đổi validator; muốn đổi cần downgrade level theo thủ tục.
- Bypass document validation bị hạn chế.

```javascript
// CHỈ LÀ VÍ DỤ THỨ TỰ TRÊN MONGODB 9.0+
// Đã có validator strict và dữ liệu được sửa hợp lệ.
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

Không chạy lệnh 9.0 này trên MongoDB 6/7/8 hoặc collection production chưa audit. Scan legacy docs có thể tốn tài nguyên.

### 13.5. `bypassDocumentValidation` cần kiểm soát

Một số MongoDB CRUD commands/driver options hỗ trợ `bypassDocumentValidation` khi caller có privilege phù hợp.

Bài test cần phân biệt:

- Write thường bị validator từ chối.
- Write có bypass chỉ hoạt động khi quyền, server/version và level cho phép.
- Đường ghi production không được vô tình bật bypass toàn cục.
- `constraint` có quy tắc riêng ngăn bypass.

Không dùng bypass để “cho test pass” vì nó khiến test không còn chứng minh validator hoạt động.

## 14. Validator áp dụng cho insert, update và replace

### 14.1. Insert mới

```javascript
db.orders.insertOne({
  runId: "lab",
  orderCode: "ORD-1",
  amountCents: NumberInt(150),
  lines: [{ sku: "BOOK-A", quantity: NumberInt(2) }]
});
```

Nếu đúng validator, insert thành công.

### 14.2. Partial update có thể fail vì document cũ sai

Legacy:

```javascript
{
  _id: "old-1",
  amountCents: "150",
  status: "PAID"
}
```

Với strict validator yêu cầu `amountCents` numeric, lệnh:

```javascript
db.orders.updateOne(
  { _id: "old-1" },
  { $set: { updatedAt: new Date() } }
);
```

có thể thất bại vì **document sau update vẫn vi phạm validator**, dù `updatedAt` không phải field lỗi.

### 14.3. Replace làm mất fields không được gửi lại

```javascript
db.orders.replaceOne(
  { _id: "ORD-1" },
  { status: "PAID" }
);
```

Nếu validator yêu cầu `orderCode`, `amountCents` và `lines`, replacement thiếu các fields này sẽ bị từ chối. Không dùng `replaceOne` khi muốn partial update mà client chỉ giữ một phần document.

### 14.4. Upsert chịu validation như insert

```javascript
db.orders.updateOne(
  { orderCode: "ORD-NEW" },
  { $set: { status: "CREATED" } },
  { upsert: true }
);
```

Nếu không match và tạo document mới, document upserted phải thỏa validator. Một filter có vài fields không bảo đảm document kết quả có mọi required field. Test cả nhánh **matched update** và **insert via upsert**.

### 14.5. Mối quan hệ với atomicity và bulkWrite

- Một single-document update được MongoDB áp dụng atomically, không để lại một document “nửa update” khi validation fail.
- `insertMany` hoặc `bulkWrite` trên nhiều documents có thể **thành công một phần** trước khi gặp lỗi, tùy ordered/unordered behavior.
- Validator không biến nhiều-document operation thành transaction.

Test bulk errors phải đọc `insertedCount`/per-item errors và truy vấn lại state thực, không mặc định “một bad doc làm rollback tất cả”.

## 15. Validator không thể thay mọi bất biến nghiệp vụ

### 15.1. Unique giữa documents

`$jsonSchema` không thể tự đảm bảo hai documents khác nhau không có cùng `orderCode`.

Cần unique index phù hợp:

```javascript
db.orders.createIndex(
  { tenantId: 1, orderCode: 1 },
  { unique: true }
);
```

Khi test, phải xét giá trị null/missing, normalization, collation và sharding constraints.

### 15.2. Unique index với null và missing

Với **single-field unique index thông thường**, một document missing field và một document có `field:null` đều có thể tạo index key null tương ứng. MongoDB chỉ cho phép một index entry null như thế theo single-field unique semantics, nên insert tiếp có thể gặp duplicate key.

Với **compound unique indexes**, quy tắc phụ thuộc tổ hợp key values; các tổ hợp có null/missing có thể trùng hoặc không trùng. Không suy luận đơn giản “unique luôn cho nhiều missing” hay “unique luôn cấm tất cả null” trên mọi index shape.

### 15.3. Sparse và partial unique indexes

Một **sparse unique** index bỏ qua documents thiếu indexed field (theo semantics index), nhưng documents có field null vẫn có thể được index, do đó null còn có thể conflict.

Một **partial unique** index chỉ index những documents thỏa filter:

```javascript
db.people.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
);
```

Đây là một lựa chọn khi chỉ muốn email String hợp lệ được kiểm tra unique. Nhưng vẫn phải:

- Thiết kế normalization/case-folding.
- Kiểm non-string values và validator.
- Kiểm sharded unique restrictions nếu dùng sharding.
- Kiểm tất cả write paths và race.
- Không dùng index như thay thế authorization/tenant scope.

### 15.4. Business invariant ngoài phạm vi một document

Các quy tắc như “tổng quantity đã đặt không vượt inventory” giữa nhiều documents cần atomic conditional update hoặc transaction khi thích hợp. `$jsonSchema` chỉ mô tả cấu trúc/giá trị của document, không tự kiểm mọi liên hệ giữa collections.

## 16. Bộ ca kiểm thử tối thiểu cho BSON và schema

Đây là **test matrix dành cho ứng dụng**, không phải lượt đánh giá nội dung bài học.

| Nhóm | Positive case | Negative/boundary case |
| --- | --- | --- |
| Int32 | `NumberInt(42)` | `NumberLong("42")` nếu schema chỉ cho `int` |
| Int64 | `NumberLong("42")` | Double `42.0` và string `"42"` |
| Decimal128 | Giá trị thập phân chính xác | Input float gây rounding |
| Date | BSON Date UTC | ISO timestamp string |
| ObjectId | BSON ObjectId | 24-char hex String |
| Null | Present null khi được phép | Null khi `bsonType:"string"` |
| Missing | Optional field vắng | Missing required field |
| Empty | Chuỗi/mảng rỗng khi contract cho phép | `minLength`/`minItems` thất bại |
| Array membership | Một element đúng | Scalar lẫn với array |
| Array exact | Đúng elements và thứ tự | Thứ tự đảo |
| `$elemMatch` | Cùng element thỏa tất cả | Các điều kiện nằm trên hai elements |
| Array items | Mọi phần tử đúng type | Có 1 element null/string sai |
| Array duplicate | Không trùng | `uniqueItems:true` bị vi phạm |
| Nested object | Đúng nested paths | Parent missing/null/wrong type |
| Validator strict | Valid insert/update | Invalid insert/update bị reject |
| Validator moderate | Update existing invalid theo semantics | Insert invalid mới bị reject |
| Validator warn | Invalid được nhận + log | Test không được tưởng là “valid” |
| Upsert | Tạo document đủ required fields | Insert branch thiếu field |
| Replace | Full replacement hợp lệ | Replacement mất required field |
| Index | Unique hợp lệ | Duplicate null/missing/tenant scope |
| Upgrade | Old + new codecs cùng đọc được | Serialization thay BSON type |

Đối với mọi test thất bại, đừng chỉ assert exception. Cần **đọc lại document** và kiểm dữ liệu không bị thay đổi ngoài ý muốn.

## 17. Kiểm thử Java bằng JUnit 5 và MongoDB Sync Driver

### 17.1. Dependency và môi trường

Ví dụ Maven cấu trúc:

```xml
<dependencies>
  <dependency>
    <groupId>org.mongodb</groupId>
    <artifactId>mongodb-driver-sync</artifactId>
    <version>VERSION_DA_CHOT</version>
  </dependency>

  <dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>VERSION_DA_CHOT</version>
    <scope>test</scope>
  </dependency>
</dependencies>
```

Dùng bản tương thích theo dependency management/BOM của project, không tự ghim version từ ví dụ.

Chạy integration tests trên MongoDB Server **được cấp cho testing**, bằng biến môi trường:

```text
MONGODB_TEST_URI=<URI của MongoDB test>
```

Không đặt URI chứa username/password trong source hay commit Git. Bộ test không cần thay cấu hình server, không chạy `dropDatabase()` và không dùng dữ liệu production.

### 17.2. Một lớp integration test tự chứa

Ví dụ Java 17, JUnit Jupiter, MongoDB Java Sync Driver:

```java
import com.mongodb.MongoWriteException;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;

import org.bson.BsonDocument;
import org.bson.BsonType;
import org.bson.Document;
import org.bson.types.Decimal128;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Assumptions;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

import static com.mongodb.client.model.Filters.*;
import static org.junit.jupiter.api.Assertions.*;

class BsonContract414IT {
    private MongoClient client;
    private MongoDatabase database;
    private MongoCollection<Document> collection;
    private String collectionName;
    private String runId;

    @BeforeEach
    void setup() {
        String uri = System.getenv("MONGODB_TEST_URI");
        Assumptions.assumeTrue(
            uri != null && !uri.isBlank(),
            "Chỉ chạy khi đã cấu hình MongoDB test"
        );

        client = MongoClients.create(uri);
        database = client.getDatabase("mongo_bson_row414_lab");
        runId = "row414_" +
            UUID.randomUUID().toString().replace("-", "");
        collectionName = "cases_" + runId;

        database.createCollection(collectionName);
        collection = database.getCollection(collectionName);
    }

    @AfterEach
    void cleanup() {
        try {
            if (collection != null && runId != null) {
                // Chỉ xóa dữ liệu có runId của lượt test.
                collection.deleteMany(eq("runId", runId));
                // Namespace ngẫu nhiên có thể được dọn bởi job
                // quản trị lab sau khi xác nhận ownership.
            }
        } finally {
            if (client != null) client.close();
        }
    }

    private Document fixture(String id) {
        return new Document("_id", id)
            .append("runId", runId);
    }

    @Test
    void nullAndMissingAreDifferent() {
        collection.insertMany(List.of(
            fixture("missing"),
            fixture("null").append("value", null),
            fixture("string").append("value", "ok")
        ));

        assertEquals(2, collection.countDocuments(eq("value", null)));
        assertEquals(
            1,
            collection.countDocuments(exists("value", false))
        );
        assertEquals(
            1,
            collection.countDocuments(
                type("value", BsonType.NULL)
            )
        );

        Document missing = collection.find(
            eq("_id", "missing")
        ).first();

        Document explicitNull = collection.find(
            eq("_id", "null")
        ).first();

        assertNotNull(missing);
        assertNotNull(explicitNull);

        assertFalse(missing.containsKey("value"));
        assertTrue(explicitNull.containsKey("value"));
        assertNull(explicitNull.get("value"));
    }

    @Test
    void preservesBsonNumericTypes() {
        collection.insertOne(
            fixture("typed")
                .append("i32", 42)
                .append("i64", 42L)
                .append(
                    "price",
                    new Decimal128(new BigDecimal("12.50"))
                )
        );

        MongoCollection<BsonDocument> bsonCollection =
            database.getCollection(
                collectionName, BsonDocument.class
            );

        BsonDocument result = bsonCollection.find(
            eq("_id", "typed")
        ).first();

        assertNotNull(result);
        assertEquals(BsonType.INT32, result.get("i32").getBsonType());
        assertEquals(BsonType.INT64, result.get("i64").getBsonType());
        assertEquals(
            BsonType.DECIMAL128,
            result.get("price").getBsonType()
        );
    }

    @Test
    void elemMatchRequiresSameArrayElement() {
        collection.insertMany(List.of(
            fixture("cross").append(
                "lines",
                List.of(
                    new Document("sku", "A").append("qty", 1),
                    new Document("sku", "B").append("qty", 8)
                )
            ),
            fixture("same").append(
                "lines",
                List.of(
                    new Document("sku", "A").append("qty", 8)
                )
            )
        ));

        assertEquals(
            2,
            collection.countDocuments(
                and(
                    eq("lines.sku", "A"),
                    gte("lines.qty", 5)
                )
            )
        );

        assertEquals(
            1,
            collection.countDocuments(
                elemMatch(
                    "lines",
                    and(eq("sku", "A"), gte("qty", 5))
                )
            )
        );
    }

    @Test
    void jsonSchemaRejectsMissingAndNullRequiredString() {
        Document validator = new Document("$jsonSchema",
            new Document("bsonType", "object")
                .append("required", List.of("name"))
                .append(
                    "properties",
                    new Document("name",
                        new Document("bsonType", "string"))
                )
        );

        database.runCommand(
            new Document("collMod", collectionName)
                .append("validator", validator)
                .append("validationLevel", "strict")
                .append("validationAction", "error")
        );

        assertThrows(
            MongoWriteException.class,
            () -> collection.insertOne(fixture("missing"))
        );

        assertThrows(
            MongoWriteException.class,
            () -> collection.insertOne(
                fixture("null").append("name", null)
            )
        );

        collection.insertOne(
            fixture("valid").append("name", "An")
        );

        assertEquals(
            1,
            collection.countDocuments(eq("_id", "valid"))
        );
        assertEquals(
            0,
            collection.countDocuments(eq("_id", "missing"))
        );
    }
}
```

### 17.3. Phạm vi của mã test

- Cần MongoDB test Server thật; nếu thiếu `MONGODB_TEST_URI`, JUnit assumption bỏ qua các test.
- Mỗi test dùng collection riêng với tên ngẫu nhiên, mỗi test document có `runId`.
- `cleanup()` chỉ delete test records theo runId; **không drop database** và không đụng records của lượt khác.
- Trong ví dụ BSON numeric, Int32/Int64/Decimal128 được kiểm bằng `BsonDocument`, không dùng JSON string.
- Nếu một test thất bại trước cleanup, collection lab có thể còn lại: cần job quản lý dọn namespaces theo prefix/owner/retention.
- Nếu dùng sharded/managed deployment hoặc thiếu quyền `collMod`, tách riêng schema validation integration tests vào môi trường được cấp quyền.
- Test validation chỉ chặn **insert mới**; phần moderate/legacy cần một bộ test riêng.

## 18. Test dữ liệu legacy khi validator được thêm sau

### 18.1. Tại sao không tạo validator trước mọi fixture?

Nếu muốn kiểm behavior khi thêm validator vào collection đã có dữ liệu sai, phải theo đúng thứ tự:

```text
Create collection (no validator)
          |
Insert valid document
Insert invalid legacy document
          |
Apply collMod validator
          |
Test strict vs moderate behavior
          |
Fix legacy data
          |
Verify later updates/validator state
```

Nếu luôn tạo collection với validator ngay từ đầu, sẽ không tái hiện trường hợp production có legacy invalid data.

### 18.2. Script `mongosh` minh họa

```javascript
const lab = db.getSiblingDB("mongo_bson_row414_lab");
const name = "legacy_row414_" +
  new ObjectId().toHexString();

lab.createCollection(name);
const c = lab.getCollection(name);

const runId = "row414_" + new ObjectId().toHexString();

c.insertMany([
  {
    _id: "valid-" + runId,
    runId,
    name: "An"
  },
  {
    _id: "invalid-" + runId,
    runId,
    name: NumberInt(99)
  }
]);

const validator = {
  $jsonSchema: {
    bsonType: "object",
    required: ["name"],
    properties: {
      name: { bsonType: "string" }
    }
  }
};

lab.runCommand({
  collMod: name,
  validator,
  validationLevel: "moderate",
  validationAction: "error"
});
```

Thử update invalid legacy document:

```javascript
c.updateOne(
  { _id: "invalid-" + runId, runId },
  { $set: { reviewed: true } }
);
```

Với `moderate`, update trên document vốn invalid có thể được chấp nhận.

Thử insert invalid mới:

```javascript
try {
  c.insertOne({
    _id: "new-invalid-" + runId,
    runId,
    name: NumberInt(99)
  });
  print("UNEXPECTED: invalid new insert accepted");
} catch (e) {
  print("Expected validation error: " + e.codeName);
}
```

Sau đó chuyển `strict`:

```javascript
lab.runCommand({
  collMod: name,
  validationLevel: "strict",
  validationAction: "error"
});

try {
  c.updateOne(
    { _id: "invalid-" + runId, runId },
    { $set: { reviewedAgain: true } }
  );
  print("UNEXPECTED: strict accepted invalid document");
} catch (e) {
  print("Expected strict validation error: " + e.codeName);
}
```

Đừng chạy script trên collection production: nó cố ý tạo dữ liệu sai và có thao tác `collMod`.

### 18.3. Sửa legacy data theo business meaning

Trong lab, bạn biết `name:99` là sai và có thể sửa thành giá trị giả. Trong production, không được đoán một số tài khoản/giá trị tài chính rồi tự sửa chỉ để pass schema.

Một migration tốt cần:

- phân loại các nhóm lỗi type/field;
- xác định source of truth;
- đọc theo batch nhỏ có giới hạn;
- ghi có điều kiện theo `_id` và version/old value;
- báo conflicts và records không thể tự sửa;
- kiểm số lượng và business invariants trước/sau;
- chỉ chuyển validator strict sau khi dữ liệu và writers đáp ứng contract.

## 19. Lab `mongosh` có assertions kiểm null, mảng và BSON

### 19.1. Chuẩn bị namespace riêng

Đoạn lab chạy trên test deployment; mỗi lượt tạo collection mới. Không chạy trong `admin`, `local`, `config` hoặc collection có dữ liệu người dùng.

```javascript
const lab = db.getSiblingDB("mongo_bson_row414_lab");
const runId = "row414_" + new ObjectId().toHexString();
const collectionName = "cases_" + runId;

if (lab.getCollectionNames().includes(collectionName)) {
  throw new Error("Namespace already exists; refusing overwrite");
}

lab.createCollection(collectionName);
const c = lab.getCollection(collectionName);

printjson({
  database: lab.getName(),
  collectionName,
  runId
});
```

### 19.2. Assertions nhỏ, không cần thư viện bên ngoài

```javascript
function assertCount(description, filter, expected) {
  const actual = c.countDocuments(filter);

  if (actual !== expected) {
    throw new Error(
      description +
      ": expected=" + expected + ", actual=" + actual
    );
  }

  print("PASS: " + description + " -> " + actual);
}

function assertValue(description, actual, expected) {
  if (actual !== expected) {
    throw new Error(
      description + ": expected=" + expected +
      ", actual=" + actual
    );
  }

  print("PASS: " + description);
}
```

### 19.3. Null/missing scalar tests

```javascript
c.insertMany([
  { _id: runId + "-missing", runId },
  { _id: runId + "-null", runId, value: null },
  { _id: runId + "-empty", runId, value: "" },
  { _id: runId + "-zero", runId, value: NumberInt(0) },
  { _id: runId + "-false", runId, value: false }
]);

assertCount(
  "null query includes missing",
  { runId, value: null },
  2
);

assertCount(
  "missing only",
  { runId, value: { $exists: false } },
  1
);

assertCount(
  "present including null",
  { runId, value: { $exists: true } },
  4
);

assertCount(
  "BSON null only on scalar fixture",
  { runId, value: { $type: "null" } },
  1
);

assertCount(
  "not equal null",
  { runId, value: { $ne: null } },
  3
);
```

Lưu ý: nếu thêm `{value:[null]}` vào cùng collection với `runId` như trên, một số count đổi vì semantics array traversal. Vì thế phân nhóm fixture và expected results là quan trọng.

### 19.4. BSON type assertions bằng aggregation

```javascript
const typedId = runId + "-typed";

c.insertOne({
  _id: typedId,
  runId,
  i32: NumberInt(42),
  i64: NumberLong("42"),
  dbl: NumberDouble("42"),
  dec: NumberDecimal("42.50"),
  createdAt: ISODate("2026-11-14T00:00:00Z"),
  refId: ObjectId("66a000000000000000000414")
});

const actualType = c.aggregate([
  { $match: { _id: typedId, runId } },
  {
    $project: {
      i32: { $type: "$i32" },
      i64: { $type: "$i64" },
      dbl: { $type: "$dbl" },
      dec: { $type: "$dec" },
      createdAt: { $type: "$createdAt" },
      refId: { $type: "$refId" }
    }
  }
]).toArray()[0];

assertValue("int32 type", actualType.i32, "int");
assertValue("int64 type", actualType.i64, "long");
assertValue("double type", actualType.dbl, "double");
assertValue("decimal type", actualType.dec, "decimal");
assertValue("date type", actualType.createdAt, "date");
assertValue("ObjectId type", actualType.refId, "objectId");
```

### 19.5. Mảng cơ bản

Để tránh trộn các cases scalar với các array semantics, dùng field khác là `tags`:

```javascript
c.insertMany([
  {
    _id: runId + "-tags-a",
    runId,
    tags: ["java", "mongodb"]
  },
  {
    _id: runId + "-tags-b",
    runId,
    tags: ["mongodb", "java"]
  },
  {
    _id: runId + "-tags-c",
    runId,
    tags: ["java"]
  },
  {
    _id: runId + "-tags-empty",
    runId,
    tags: []
  }
]);

assertCount(
  "array contains java",
  { runId, tags: "java" },
  3
);

assertCount(
  "exact ordered array",
  { runId, tags: ["java", "mongodb"] },
  1
);

assertCount(
  "array $all regardless of order",
  {
    runId,
    tags: { $all: ["java", "mongodb"] }
  },
  2
);

assertCount(
  "empty array only",
  {
    runId,
    tags: { $size: 0 }
  },
  1
);
```

Các document khác ở lab không có field `tags` nên không match các filters trên.

### 19.6. Kiểm thử cross-element false positive

```javascript
c.insertMany([
  {
    _id: runId + "-cross",
    runId,
    lines: [
      { sku: "BOOK-A", qty: NumberInt(1) },
      { sku: "BOOK-B", qty: NumberInt(8) }
    ]
  },
  {
    _id: runId + "-same",
    runId,
    lines: [
      { sku: "BOOK-A", qty: NumberInt(8) }
    ]
  }
]);

assertCount(
  "dot notation may match across elements",
  {
    runId,
    "lines.sku": "BOOK-A",
    "lines.qty": { $gte: 5 }
  },
  2
);

assertCount(
  "$elemMatch uses one element",
  {
    runId,
    lines: {
      $elemMatch: {
        sku: "BOOK-A",
        qty: { $gte: 5 }
      }
    }
  },
  1
);
```

Kết quả 2 vs 1 là một invariant đáng lưu trong regression tests khi refactor query builder hoặc chuyển sang Spring Data criteria.

### 19.7. Dọn test records theo runId

Đầu tiên kiểm tra:

```javascript
print("DB=" + lab.getName());
print("COLLECTION=" + c.getName());
print("RUN=" + runId);

const owned = c.find(
  { runId },
  { _id: 1, runId: 1 }
).toArray();

printjson({
  ownedCount: owned.length,
  ownedIds: owned.map(x => x._id)
});
```

Chỉ sau khi xác nhận đúng collection/runId của chính mình:

```javascript
for (const item of owned) {
  c.deleteOne({
    _id: item._id,
    runId
  });
}

print("remaining=" + c.countDocuments({ runId }));
```

**Không dùng `deleteMany({})` hoặc `dropDatabase()`** trên database dùng chung. Collection thử nghiệm có thể còn sau cleanup; quyền thu hồi namespace thuộc quản trị lab theo chính sách và định danh ownership.

## 20. Kiểm thử validator ngay trong lab

### 20.1. Một collection riêng có validator

Chỉ chạy trên namespace mới **được xác nhận chưa tồn tại**:

```javascript
const validatorName =
  "validated_" + runId;

if (lab.getCollectionNames().includes(validatorName)) {
  throw new Error("Validator namespace already exists");
}

lab.createCollection(validatorName, {
  validator: orderValidator,
  validationLevel: "strict",
  validationAction: "error"
});

const validated = lab.getCollection(validatorName);
```

Ở đây `orderValidator` là object đã khai báo ở phần 12.1. Vì yêu cầu `runId`, mọi fixture phải có nó.

### 20.2. Một trường hợp hợp lệ

```javascript
validated.insertOne({
  _id: runId + "-valid",
  runId,
  orderCode: "ORD-414",
  amountCents: NumberInt(10000),
  tags: ["java", "mongodb"],
  lines: [
    { sku: "BOOK-A", quantity: NumberInt(2) }
  ],
  note: null
});
```

Kỳ vọng: insert thành công.

### 20.3. Một tập dữ liệu không hợp lệ

```javascript
const invalidCases = [
  {
    name: "missing-lines",
    document: {
      runId,
      orderCode: "ORD-MISSING",
      amountCents: NumberInt(100)
    }
  },
  {
    name: "null-lines",
    document: {
      runId,
      orderCode: "ORD-NULL",
      amountCents: NumberInt(100),
      lines: null
    }
  },
  {
    name: "empty-lines",
    document: {
      runId,
      orderCode: "ORD-EMPTY",
      amountCents: NumberInt(100),
      lines: []
    }
  },
  {
    name: "wrong-amount-type",
    document: {
      runId,
      orderCode: "ORD-STRING-AMOUNT",
      amountCents: "100",
      lines: [{ sku: "A", quantity: NumberInt(1) }]
    }
  },
  {
    name: "wrong-line-type",
    document: {
      runId,
      orderCode: "ORD-LONG-QTY",
      amountCents: NumberInt(100),
      lines: [{ sku: "A", quantity: NumberLong("1") }]
    }
  },
  {
    name: "duplicated-tag",
    document: {
      runId,
      orderCode: "ORD-DUP-TAGS",
      amountCents: NumberInt(100),
      tags: ["java", "java"],
      lines: [{ sku: "A", quantity: NumberInt(1) }]
    }
  },
  {
    name: "null-note-not-a-problem",
    // Đây là case HỢP LỆ vì note optional nullable.
    document: {
      runId,
      orderCode: "ORD-NULL-NOTE",
      amountCents: NumberInt(100),
      note: null,
      lines: [{ sku: "A", quantity: NumberInt(1) }]
    }
  }
];
```

Điều kiện kỳ vọng phải được gắn rõ:

```javascript
for (const entry of invalidCases) {
  const document = {
    _id: runId + "-" + entry.name,
    ...entry.document
  };

  const expectedAccepted =
    entry.name === "null-note-not-a-problem";

  let accepted = false;

  try {
    validated.insertOne(document);
    accepted = true;
  } catch (e) {
    if (e.code !== 121) {
      throw e;  // lỗi khác cần được điều tra
    }
  }

  if (accepted !== expectedAccepted) {
    throw new Error(
      "Unexpected validator result for " + entry.name
    );
  }

  print("PASS validator case: " + entry.name);
}
```

Error code **121** là `DocumentValidationFailure` trong MongoDB Server thông dụng; khi viết integration tests theo driver/version khác, kiểm error category/codeName và readback thay vì phụ thuộc hoàn toàn vào error message có thể thay đổi.

### 20.4. Một error validation không nên làm thay đổi document cũ

Thử:

```javascript
const validId = runId + "-valid";

try {
  validated.updateOne(
    { _id: validId, runId },
    { $set: { amountCents: "WRONG" } }
  );
  throw new Error("Unexpected successful invalid update");
} catch (e) {
  if (e.code !== 121) throw e;
}

const after = validated.findOne({
  _id: validId,
  runId
});

if (typeof after.amountCents === "string") {
  throw new Error("Invalid update changed persisted state");
}
```

Mục tiêu là kiểm **không chỉ response lỗi** mà còn document không bị sửa một phần. Với kiểm type nghiêm hơn, dùng aggregation `$type` thay vì JavaScript `typeof`.

### 20.5. Cleanup validator collection

Chỉ xóa những documents của runId:

```javascript
const ownValidatedIds = validated.find(
  { runId },
  { _id: 1 }
).toArray();

for (const item of ownValidatedIds) {
  validated.deleteOne({
    _id: item._id,
    runId
  });
}

print(
  "remainingValidated=" +
  validated.countDocuments({ runId })
);
```

**Không drop toàn bộ lab database** vì nó có thể chứa dữ liệu của lượt test khác. Nếu muốn thu hồi collection và validator, thực hiện theo quy trình quản trị namespace ngẫu nhiên riêng sau khi xác minh.

## 21. Cách viết tests dạng parameterized và property-based

### 21.1. Parameterized test cho boundary values

Thay vì viết 50 phương thức giống nhau, JUnit 5 hỗ trợ:

```java
@ParameterizedTest(name = "quantity={0}")
@ValueSource(ints = {-1, 0, 1, 2, Integer.MAX_VALUE})
void quantityBoundary(int quantity) {
    boolean accepted = quantity >= 1;

    // Tạo một valid order, gán quantity vào lines[0].
    // Insert vào collection đã bật validator và so kết quả
    // với accepted; xác minh không có partial mutation.
}
```

Đây là **skeleton** của test; cần test setup và validator tương ứng. Dùng generator có seed để lỗi tái hiện được.

### 21.2. Property-based tests

Từ các bất biến, tạo dữ liệu ngẫu nhiên có kiểm soát:

- Với mọi `quantity` Int32 >= 1, line hợp lệ nếu các fields khác hợp lệ.
- Với mọi `quantity <= 0`, line invalid.
- Với mọi optional String `note`, missing/null/String được phép theo schema; number/array không được phép.
- Với mọi mảng `lines`, chỉ valid khi không rỗng và mọi element đúng schema.
- Với mọi pair of array elements, `$elemMatch` không được match khi điều kiện phân tán trên các elements.

Một generator phải cố ý tạo **invalid shape**, không chỉ random String/number hợp lệ. Phải log seed và testcase tối giản khi thất bại.

### 21.3. Mutation testing cho predicates

Một regression test tốt có thể phát hiện ai đó đổi:

```javascript
{
  lines: {
    $elemMatch: { sku: "A", qty: { $gte: 5 } }
  }
}
```

thành:

```javascript
{
  "lines.sku": "A",
  "lines.qty": { $gte: 5 }
}
```

Fixture cross-element sẽ phát hiện sai khác ngay. Tương tự, đổi `$unset` thành `$set:null` phải làm test field-presence thất bại nếu contract yêu cầu missing.

## 22. Test với Spring Data MongoDB và Java application

### 22.1. Mapper có thể thay semantics

Trong Spring Data MongoDB, entity mapping, converters và repository query derivation thêm một lớp xử lý:

```text
HTTP JSON
    |
Jackson DTO
    |
Spring Data MappingMongoConverter
    |
BSON / Java Driver
    |
MongoDB Server
```

Các chỗ cần integration tests:

- `@Id`: String → ObjectId có bị chuyển theo annotation/mapping?
- `BigDecimal`: lưu String hay Decimal128 theo converter/config?
- `Instant`/`LocalDateTime`: timezone/UTC xử lý thế nào?
- Optional fields: bỏ field hay ghi null?
- `List<T>`: empty/null/missing có khác nhau sau round-trip?
- `@Field`: tên persisted có đúng không?
- `@Version`: optimistic locking có giữ type/version không?
- Query method tên dài có tạo `$elemMatch` hay chỉ dot conditions?
- Validation errors có được chuyển thành exception class đúng để API trả 4xx/5xx phù hợp?

Không suy luận từ Java class rằng BSON lưu giống chính xác tên/kiểu của field.

### 22.2. `@DataMongoTest` và MongoDB thật

Spring Boot có slice test `@DataMongoTest`, nhưng cấu hình môi trường quyết định kết nối tới MongoDB thật, embedded/mock hay container. Hãy dùng test MongoDB version khớp production nếu kiểm server semantics.

Một test chỉ mock `MongoRepository` không chứng minh validator hoặc mảng query thực sự hoạt động. Trong CI, có thể dùng container ephemeral hoặc test server được cấp quyền; đảm bảo data isolation và teardown.

### 22.3. Tests API PATCH

Một endpoint:

```text
PATCH /profiles/123
{ "nickname": null }
```

khác:

```text
PATCH /profiles/123
{}
```

Kết quả đúng tùy contract:

- Missing key trong PATCH = giữ nguyên.
- Present null = xóa bằng `$unset` hoặc đặt null bằng `$set`, phải quyết định rõ.
- Present String = cập nhật.
- Present empty String = hợp lệ/không hợp lệ theo validator.

Cần kiểm từ HTTP request → DTO → Mongo update → readback. Test repository thuần không bao phủ mapping của JSON missing/null.

## 23. Type strictness và query correctness

### 23.1. Type validation không thể được thay bằng “query vẫn match”

MongoDB hỗ trợ numeric comparisons qua các BSON numeric types, khiến query này:

```javascript
db.c.find({ amountCents: 42 });
```

có thể tìm giá trị lưu với type numeric khác nhau. Điều đó **không bảo đảm client đọc lại như Long** hoặc validator sẽ chấp nhận tất cả.

Một test tốt kiểm đồng thời:

1. Query có tìm document không?
2. BSON type của field là gì?
3. Java mapping có đọc đúng không?
4. Business arithmetic có giữ precision không?

### 23.2. Sort và index với mixed BSON types

MongoDB BSON type comparison order khiến các giá trị khác kiểu có thứ tự khác theo nhóm type. Nếu field được lưu lẫn String và Number, sort/range queries có thể cho kết quả không như số học mong muốn.

Đừng chỉ test query với 100% records numeric. Tạo fixtures:

```javascript
[
  { amountCents: NumberInt(2) },
  { amountCents: NumberLong("10") },
  { amountCents: "100" },
  { amountCents: null }
]
```

và xác định contract: input String là lỗi phải bị từ chối, không nên cho business sort “sửa” vấn đề.

### 23.3. NaN và Infinity

Nếu hệ thống dùng `double`, cần xem cách xử lý NaN/Infinity, serialize/compare, validator và frontend JSON. JSON chuẩn không biểu diễn các giá trị này như number thông thường.

Với tiền tệ hoặc scoring cần miền giá trị hữu hạn, hãy chuẩn hóa/validate ở application và BSON schema hợp lý; không chỉ kiểm `instanceof Double`.

### 23.4. Collation và Unicode

String equality/sort có thể phụ thuộc collation. Với dữ liệu tiếng Việt, tests nên xét:

- Dấu tiếng Việt/không dấu.
- Chữ hoa/chữ thường.
- Unicode composed/decomposed.
- Dấu cách đầu/cuối.
- Normalization business-defined trước unique lookup.

Không dùng một test string ASCII để khẳng định unique index và equality query đã đúng với tên người, địa chỉ hoặc mã định danh Unicode.

## 24. Indexes làm thay đổi hiệu năng và một số ràng buộc

### 24.1. Index không sửa dữ liệu sai shape

Một multikey index trên `tags` hỗ trợ query array nhưng không bắt field phải là array. Nếu một document có `tags:"java"`, query có thể vẫn match trong khi contract yêu cầu array.

Cần cả validator lẫn query tests.

### 24.2. Missing/null trong unique indexes

Khi bổ sung unique index vào collection legacy, hai documents với giá trị missing/null có thể làm index build lỗi. Đây không phải lỗi “MongoDB không hiểu null”, mà là hệ quả index key semantics.

Quy trình an toàn:

1. Audit missing/null/duplicate theo scope thực.
2. Chọn business uniqueness contract.
3. Cân nhắc sparse/partial index khi hợp lệ.
4. Migration dữ liệu cũ nếu cần.
5. Xây index có capacity headroom.
6. Test concurrent inserts và duplicate key errors.

### 24.3. Partial index phải khớp query filter

Ví dụ partial index:

```javascript
db.c.createIndex(
  { email: 1 },
  {
    name: "emails_nonnull",
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
);
```

Query planner chỉ được chọn partial index khi nó có thể bảo đảm kết quả từ index là đầy đủ theo filter query. Một filter chỉ chứa `{email:{$exists:true}}` không nhất thiết phù hợp với partial filter string.

Tương tự, **query correctness** không được phụ thuộc vào việc index đang có hay không; indexes tối ưu khả năng tìm, nhưng dữ liệu và predicates phải đúng trước.

## 25. Regression tests khi nâng MongoDB/driver

### 25.1. Compatibility matrix

| Trục | Ví dụ kiểm thử |
| --- | --- |
| MongoDB Server | Release hiện tại và target upgrade |
| FCV | Feature đang được bật và điều kiện nâng cấp |
| Java Driver | Codec behavior, BSON mappings, exception types |
| Java runtime | Decimal, Date/Instant, timezone, UUID |
| Spring Data/Boot | Entity conversions, repository predicates |
| JSON library | Missing/null/empty/numeric coercion |
| Topology | Standalone test vs replica set/sharded production |
| Index/collation | Unique, partial/multikey, query plan |
| Validator version | `strict/moderate/constraint`, actions |

Không chạy một suite chỉ trên một MongoDB phiên bản ngẫu nhiên rồi coi là đủ chứng minh behavior trên production deployment khác.

### 25.2. Snapshot/golden data có thể hữu ích

Nếu có dữ liệu được phép sử dụng, giữ các **fixture đã ẩn danh**, có kiểm soát và version:

```text
fixtures/
  bson-types-v1.extjson
  null-missing-v1.extjson
  arrays-v1.extjson
  legacy-invalid-v1.extjson
```

Đây là ví dụ về tổ chức test assets, không phải yêu cầu tạo thêm files trong nhiệm vụ hiện tại.

Chọn Extended JSON canonical khi cần bảo toàn BSON type và đọc bằng thư viện BSON phù hợp. Không đưa records có PII/credentials thật vào repository.

### 25.3. Differential testing

Có thể chạy cùng query/test cases trên:

- Server version đang vận hành.
- Server version dự kiến nâng cấp.
- Driver version hiện tại.
- Driver version mới.

So:

- BSON types sau round-trip.
- Kết quả query IDs.
- Validator accepted/rejected cases.
- Error codes/categories.
- Serialization của ObjectId/Decimal128/Date/UUID.
- Query execution behavior và compatibility.

Khi thấy khác biệt, phân loại **breaking change, bug, dữ liệu sai contract hoặc test fixture thiếu**, thay vì tự chỉnh expected output cho pass.

## 26. Chạy tests trong CI/CD an toàn

### 26.1. Môi trường cô lập

Ưu tiên:

- MongoDB container phiên bản pin phù hợp trong CI; hoặc
- ephemeral test database được cấp riêng; hoặc
- MongoDB test cluster với account/quota/namespace tách biệt.

Các tests trong bài không cần `rs.initiate()`; schema/query tests cơ bản có thể chạy trên một MongoDB Server test đơn, nhưng nếu ứng dụng thực chạy trên sharded cluster, cần thêm tests về sharding/index constraints.

### 26.2. Điều kiện pass/fail

Đối với một test:

1. Fixture được tạo với **BSON type rõ**.
2. Query/operation thực thi trên MongoDB.
3. Assert result IDs/counts/exceptions.
4. Read-back persisted data, kiểm value/type/presence.
5. Xóa theo `runId` ở namespace test.
6. Ghi server/driver version và error context nếu fail.

Nếu cleanup không chạy do process crash, test data có thể còn; môi trường CI phải có retention/teardown của namespace thuộc chính job, không xóa nhầm dữ liệu job khác.

### 26.3. Không dùng fixed sleep để “đợi MongoDB sửa data”

Schema validation là thao tác server-side trong write path. Nếu write được acknowledged, có thể query/readback kết quả theo read/write concern phù hợp. Không dùng `Thread.sleep(5000)` để che sự cố eventual consistency hoặc test race.

Riêng tests liên quan replica set replication và read preference cần xác định consistency/majority concerns. Nhưng `null`, `$elemMatch` và validator single-document có thể test đồng bộ với collection primary trong lab.

### 26.4. Chẩn đoán lỗi có trách nhiệm

Khi test fail:

- Ghi namespace, runId, server/driver version và test ID.
- Ghi BSON type/shape đã mask, không log PII.
- Phân biệt validation error, duplicate key, wrong codec, permission và network failure.
- Không tự bật profiler level 2 hoặc database-wide debug logs trên production.
- Không chạy lại test lên data thật để “xác nhận” khi đã có fixture đủ.

## 27. Các phản ví dụ cần đưa vào bộ hồi quy

| Anti-pattern | Rủi ro | Test có thể phát hiện |
| --- | --- | --- |
| Java `get("field")==null` nghĩa missing | Gộp missing/null | `containsKey` presence test |
| Chỉ test JSON số `42` | Bỏ sai Int32/Int64 | BSON type round-trip |
| Dùng Double cho money | Rounding | Decimal128/long exactness |
| Serialize Date thành ISO String | Range/sort sai type | Aggregation `$type` |
| ObjectId biến thành String | Find theo `_id` thất bại | ObjectId vs String test |
| `{x:null}` để tìm only null | Match missing | Scalar null/missing fixture |
| `$exists:true` để tìm non-null | Match explicit null | Presence/null test |
| `tags:"java"` để chứng minh tags là array | String scalar cũng có thể match | Validator array type test |
| Exact-array equality cho membership | Phụ thuộc thứ tự | `$all`/contains tests |
| Dotted array predicates thay `$elemMatch` | Cross-element false positives | Two-element regression fixture |
| `$push` thay `$addToSet` | Duplicates | Repeated update test |
| `uniqueItems` nhưng bỏ test object duplicates | Dữ liệu trùng/semantic | Array duplicate fixtures |
| Validator chỉ có `required` | Null vẫn có thể được phép | Required+type matrix |
| Tạo validator rồi kỳ vọng legacy tự được sửa | Invalid docs còn tồn tại | Existing-docs test |
| Bật strict khi app cũ chưa chuyển | Write errors | Multi-version writer tests |
| `warn` rồi nghĩ dữ liệu đã bị chặn | Invalid vẫn được ghi | Assert persisted data |
| BulkWrite fail và cho rằng rollback toàn bộ | Partial success | Readback after errors |
| Unique index cho field optional không audit null | DuplicateKey | Missing/null uniqueness fixtures |
| Mapper tự cast `Long` sang `Integer` an toàn | ClassCast/overflow | Codec and boundary tests |
| Dùng production database để chạy tests | Có thể sửa/xóa data thật | Isolated namespace/credentials |
| Ignore error code và chỉ log `e.message` | Khó phân loại lỗi | Error category assertions |
| Test chỉ trên một driver/server version | Upgrade regression | Compatibility matrix |
| Assert bằng mock repository | Không kiểm được server semantics | Integration tests |

## 28. Tình huống thiết kế: Profile API hỗ trợ PATCH

Một API lưu:

```javascript
{
  _id: ObjectId("66a000000000000000000414"),
  displayName: "An",
  nickname: "Anh",
  channels: ["email", "sms"],
  preferences: {
    marketing: false
  }
}
```

Business rules:

1. `displayName` required, String không rỗng.
2. `nickname` optional, **nếu có thì String hoặc Null**.
3. `channels` optional array String, không trùng.
4. `preferences.marketing` optional Boolean.
5. PATCH thiếu key = giữ nguyên; PATCH `nickname:null` = đặt explicit null; PATCH `nickname:""` = từ chối.

### 28.1. Các request cần test

```json
{}
```

Kỳ vọng: document không đổi.

```json
{"nickname": null}
```

Kỳ vọng: nickname tồn tại với BSON Null (theo contract đã chọn).

```json
{"nickname": ""}
```

Kỳ vọng: reject, persisted nickname không đổi.

```json
{"channels": []}
```

Kỳ vọng: hợp lệ nếu schema cho phép array rỗng.

```json
{"channels": ["email", "email"]}
```

Kỳ vọng: reject nếu validator có `uniqueItems:true`.

```json
{"preferences": {"marketing": false}}
```

Kỳ vọng: False phải được giữ, không bị mapper bỏ vì nghĩ “không có giá trị”.

### 28.2. Những gì cần kiểm sau API response

- HTTP status và error mapping.
- MongoDB document sau write.
- Presence của các fields.
- BSON type của value.
- Nested object còn các fields khác không.
- Validation action/level đúng.
- Không có partial update ngoài ý muốn.
- Concurrent PATCH có cần version/optimistic lock không.

Đây là kiểm thử **end-to-end contract**, không chỉ kiểm regex của input.

## 29. Bài tập tự luyện

### Bài A — Null và missing

Cho:

```javascript
[
  { _id: 1 },
  { _id: 2, x: null },
  { _id: 3, x: "" },
  { _id: 4, x: NumberInt(0) }
]
```

Dự đoán IDs của:

1. `{x:null}`.
2. `{x:{$exists:false}}`.
3. `{x:{$exists:true}}`.
4. `{x:{$type:"null"}}`.
5. `{x:{$ne:null}}`.

Giải thích vì sao SQL `IS NULL` và MongoDB equality-to-null không thể thay thế máy móc trong ứng dụng.

### Bài B — BSON number

Một REST API gửi:

```json
{"amount": 42}
```

Yêu cầu MongoDB lưu BSON Int64.

1. Chỗ nào trong mapper/driver có thể tạo Int32?
2. Viết test với `BsonDocument`.
3. Vì sao `find({amount:42})` chưa đủ chứng minh đúng type?
4. Nếu amount vượt 2^53, tránh mất chính xác khi qua JavaScript thế nào?

### Bài C — Nullable required

Validator:

```javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["comment"],
    properties: {
      comment: { bsonType: ["string", "null"] }
    }
  }
}
```

Các giá trị `{}`, `{comment:null}`, `{comment:""}`, `{comment:7}` có hợp lệ không? Muốn cấm chuỗi rỗng cần thêm keyword nào?

### Bài D — Array equality

Cho:

```javascript
[
  { tags: ["a", "b"] },
  { tags: ["b", "a"] },
  { tags: ["a"] },
  { tags: [] },
  {}
]
```

Dự đoán kết quả của:

1. `{tags:"a"}`.
2. `{tags:["a","b"]}`.
3. `{tags:{$all:["a","b"]}}`.
4. `{tags:{$size:0}}`.

### Bài E — `$elemMatch`

```javascript
{
  lines: [
    { sku: "A", qty: 1 },
    { sku: "B", qty: 10 }
  ]
}
```

Tại sao:

```javascript
{"lines.sku":"A","lines.qty":{$gte:5}}
```

có thể match, còn:

```javascript
{lines:{$elemMatch:{sku:"A",qty:{$gte:5}}}}
```

không match?

### Bài F — Array chứa null

So sánh:

```javascript
{}
{items:null}
{items:[]}
{items:[null]}
```

Thiết kế test có thể phân biệt cả bốn bằng presence/type/size và readback. Giải thích vì sao predicate `$type` dạng query có thể khác aggregation expression trên arrays.

### Bài G — Nested validator

Viết `$jsonSchema` cho:

```javascript
{
  lines: [
    { sku: "A", qty: NumberInt(2) }
  ]
}
```

với:

- lines required nonempty array;
- mọi element là object;
- sku required nonempty String;
- qty required positive Int32.

Tạo ít nhất sáu invalid fixtures.

### Bài H — Legacy migration

Collection có document:

```javascript
{ _id: 1, amountCents: "1000" }
```

Đội muốn bật validator yêu cầu `amountCents` là `long`.

1. `strict` có tự đổi dữ liệu cũ không?
2. `moderate` cho phép loại update nào trên document legacy?
3. Khi nào `strict` bắt đầu từ chối update?
4. Lên kế hoạch backfill có compare-and-set/idempotency ra sao?

### Bài I — Validator warn

Một collection đặt `validationAction:"warn"`, `validationLevel:"strict"`. Insert invalid trả thành công.

1. Đó có phải bug không?
2. Test nên kiểm error hay persisted data/log?
3. Vì sao không dùng warn làm hàng rào bảo vệ production cuối cùng?
4. Cần theo dõi log volume và PII như thế nào?

### Bài J — Unique optional field

Hai document cùng thiếu `email`, một document có `email:null`. Dự kiến thêm single-field unique index.

1. Có thể gặp lỗi nào?
2. Sparse unique xử lý missing/null thế nào?
3. Partial unique chỉ index String có phù hợp business rule không?
4. Vì sao cần test collation/case normalization?

### Bài K — PATCH semantics

Một PATCH request không gửi `nickname`, request khác gửi `nickname:null`.

1. Thiết kế DTO nào giữ được field presence?
2. Mapping sang `$set` hay `$unset` theo contract?
3. Viết hai tests readback MongoDB.
4. Nếu validator có `required:["nickname"]`, điều gì xảy ra với `$unset`?

### Bài L — Upgrade regression

Ứng dụng đổi MongoDB Java Driver và Spring Data version, dữ liệu BSON Int64 đọc lại thành kiểu khác.

1. Cần so những lớp serialization nào?
2. Integration test nào phát hiện lỗi?
3. Vì sao so JSON string chưa đủ?
4. Cần pin MongoDB Server version trong CI như thế nào?

### Bài M — Bulk write một phần

Trong một batch insert 5 documents, document thứ ba invalid theo schema và `ordered:true`.

1. Có chắc cả 5 đều rollback không?
2. Phải đọc gì từ bulk exception/result?
3. Sau lỗi nên truy vấn lại dữ liệu nào?
4. Khi nào cần transaction?

### Bài N — Mảng và uniqueItems

Một array đã có duplicates trước khi validator được thêm; ứng dụng sau đó chỉ update `updatedAt`.

1. Với `strict+error`, update có thể thành công không?
2. Với `moderate+error`, hành vi khác thế nào?
3. `$addToSet` có tự xóa duplicates cũ không?
4. Thiết kế migration array dedup như thế nào để không mất business meaning?

### Bài O — Test an toàn

Thiết kế một JUnit suite chạy trên CI có:

- 1 namespace ngẫu nhiên mỗi test.
- runId/owner rõ.
- Test BSON types, null/missing, arrays, validators.
- Cleanup trong `finally`/`@AfterEach`.
- Không dùng credentials production.
- Một báo cáo failure ghi type/query/expected/actual, không có PII.

## 30. Tài liệu tham khảo chính thức

Các tài liệu cần đối chiếu theo đúng phiên bản MongoDB Server, FCV, Java Driver và Spring Data được triển khai:

- [MongoDB BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/) — danh sách kiểu BSON và các đặc tính.
- [MongoDB Java Sync Driver — BSON Data Format](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/document-data-format-bson/) — BSON với Java.
- [MongoDB Java Sync Driver — Documents](https://www.mongodb.com/docs/drivers/java/sync/current/data-formats/documents/) — `Document`, `BsonDocument` và type mappings.
- [Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/) — `null`, missing và các phép kiểm tra.
- [`$exists`](https://www.mongodb.com/docs/manual/reference/operator/query/exists/) — field present/missing.
- [`$type` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/type/) — match type của field/array elements.
- [`$type` Aggregation Expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/type/) — `missing` vs `null` và expression semantics.
- [Query an Array](https://www.mongodb.com/docs/manual/tutorial/query-arrays/) — scalar membership, exact array match, `$all` và array positions.
- [Query an Array of Embedded Documents](https://www.mongodb.com/docs/manual/tutorial/query-array-of-documents/) — dot notation và `$elemMatch`.
- [`$elemMatch`](https://www.mongodb.com/docs/manual/reference/operator/query/elemMatch/) — buộc nhiều điều kiện cùng một array element.
- [`$addToSet`](https://www.mongodb.com/docs/manual/reference/operator/update/addToSet/) — xử lý phần tử trùng khi update.
- [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — khai báo rules, MongoDB JSON Schema.
- [Specify JSON Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/) — `bsonType`, `required`, `properties` và arrays.
- [Specify Validation Level](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-level/) — strict, moderate và constraint (MongoDB 9.0+).
- [Handle Invalid Documents](https://www.mongodb.com/docs/manual/core/schema-validation/handle-invalid-documents/) — warn/error/errorAndLog (8.1+).
- [`collMod`](https://www.mongodb.com/docs/manual/reference/command/collMod/) — sửa validator trên collection hiện hữu.
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — null/missing và multikey index semantics.
- [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/) — predicate giới hạn index.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — CRUD, BSON codec, error handling và compatibility.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/) — parameterized/integration tests.

**Lưu ý phiên bản:** `validationAction:"errorAndLog"` là tính năng mới từ MongoDB 8.1; `validationLevel:"constraint"` là tính năng MongoDB 9.0. Không sao chép cú pháp/version-specific behavior sang cluster cũ mà không kiểm tra khả năng hỗ trợ và FCV.

## 31. Kết luận

**Kiểm thử MongoDB đúng nghĩa phải nhìn thấy BSON và kiểm tra các trạng thái dữ liệu, không chỉ nhìn JSON hoặc response HTTP.**

- BSON `int`, `long`, `double`, `decimal`, `date` và `objectId` có semantics riêng; test phải giữ đúng type qua write/read.
- `null` khác **missing**. `{field:null}` thường match cả hai, còn `$exists`, `$type` và field presence giúp phân biệt.
- Mảng có semantics membership/order/size riêng. Với nhiều điều kiện trên **một phần tử**, `$elemMatch` là công cụ tránh cross-element false positives.
- `$jsonSchema` giúp bảo vệ document shape, types, required/optional/nullable fields và từng phần tử mảng.
- `strict`, `moderate` và `warn/error` tạo những hành vi khác nhau; thêm validator không tự sửa dữ liệu cũ.
- JUnit 5 + Java Sync Driver integration tests nên dùng namespace độc lập, fixtures có BSON type rõ, assertions về result và persisted state, cùng cleanup theo runId.
- Khi nâng cấp driver/server hoặc thay schema, bộ test cần có **boundary, legacy, null/missing, arrays và negative cases** để phát hiện regression.

**Nguyên tắc cốt lõi:** một document hợp lệ không chỉ là document “đọc được”. Nó phải có **đúng field, đúng trạng thái hiện diện, đúng BSON type, đúng cấu trúc mảng và đúng bất biến mà ứng dụng dựa vào**. Một bộ kiểm thử đáng tin cậy làm cho những quy tắc đó trở nên có thể quan sát, tái hiện và bảo vệ qua mỗi lần thay đổi MongoDB.

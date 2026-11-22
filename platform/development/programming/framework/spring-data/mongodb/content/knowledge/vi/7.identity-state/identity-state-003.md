# String có thể chuyển thành ObjectId và lỗi truy vấn khác kiểu

> **Chương:** Định danh và trạng thái  
> **Module:** `SPRING_DATA_MONGODB` — sử dụng Spring Data MongoDB để ánh xạ document và truy cập MongoDB qua `MongoTemplate` hoặc repository, đồng thời thiết kế truy vấn, kiểm thử và chẩn đoán lỗi dữ liệu.  
> **Mục tiêu:** Giải thích vì sao trường Java `String id` không đảm bảo MongoDB lưu `_id` dưới kiểu BSON `string`; phân biệt `@Id` với `@MongoId`; tìm nguyên nhân `findById()` trả rỗng; chọn kiểu định danh nhất quán và xử lý an toàn dữ liệu có `_id` lẫn kiểu.

## 1. Vấn đề: ID trông giống nhau nhưng truy vấn ra kết quả khác

MongoDB lưu document dưới dạng **BSON**. Mỗi document trong collection thường có trường `_id` được lập chỉ mục duy nhất. BSON chứa thông tin **kiểu dữ liệu**, nên hai giá trị hiển thị cùng dãy ký tự vẫn có thể khác nhau:

~~~javascript
// _id là BSON ObjectId (12 byte, hiển thị dưới dạng 24 ký tự hex).
{ _id: ObjectId("507f1f77bcf86cd799439011"), kind: "object-id" }

// _id là BSON string, có nội dung trông giống ObjectId.
{ _id: "507f1f77bcf86cd799439011", kind: "string-id" }
~~~

Hai document trên có thể cùng tồn tại trong một collection: `ObjectId("507f...")` **khác** chuỗi `"507f..."` đối với so khớp `_id`, dù nội dung biểu diễn bằng mắt giống nhau. MongoDB không tự đổi chuỗi sang `ObjectId` khi thực hiện một truy vấn `mongosh` thông thường.

Ví dụ:

~~~javascript
db.identity_type_demo_003.findOne({
  _id: "507f1f77bcf86cd799439011"
});
// Chỉ khớp document có _id thuộc kiểu string.

db.identity_type_demo_003.findOne({
  _id: ObjectId("507f1f77bcf86cd799439011")
});
// Chỉ khớp document có _id thuộc kiểu objectId.
~~~

Trong **Spring Data MongoDB**, có thêm một lớp ánh xạ có khả năng chuyển đổi giữa Java `String` và BSON `ObjectId`. Vì thế, cùng một biến Java `String id` nhưng cách khai báo `@Id`/`@MongoId` có thể khiến truy vấn được gửi xuống MongoDB với **kiểu BSON khác nhau**.

## 2. Hiểu chính xác BSON `ObjectId`

`ObjectId` là kiểu BSON riêng, thường được dùng làm `_id` mặc định. Giá trị `ObjectId` gồm **12 byte**, thường hiển thị bằng **24 ký tự hexadecimal** (0–9, a–f). Chuỗi dài 24 ký tự chưa chắc là mã ObjectId hợp lệ: tất cả ký tự phải là chữ số hex. Và ngay cả khi là mã hex hợp lệ, vẫn **không chứng minh** dữ liệu đang được lưu theo kiểu BSON `objectId`.

| Giá trị | Kiểu BSON | Ý nghĩa |
| --- | --- | --- |
| `ObjectId("507f1f77bcf86cd799439011")` | `objectId` | ID kiểu ObjectId |
| `"507f1f77bcf86cd799439011"` | `string` | Chuỗi 24 ký tự hex |
| `"order-001"` | `string` | ID nghiệp vụ không phải dạng ObjectId |
| `123` | Thường là kiểu số trong BSON | ID số, không bằng chuỗi `"123"` |

Độ dài hoặc hình thức hiển thị không thay thế việc kiểm tra **BSON type**. Khi điều tra lỗi truy vấn, luôn xác định cả **giá trị** và **kiểu** ở phía MongoDB.

### 2.1. Bộ dữ liệu thực hành biệt lập

Các ví dụ sử dụng `mongosh` trên database thử nghiệm. Hãy chạy trên môi trường học tập, không dùng collection nghiệp vụ:

~~~javascript
use spring_data_mongodb_lab

const demo = db.identity_type_demo_003;
const HEX_ID = "507f1f77bcf86cd799439011";

// Nếu bạn đã chạy bài trước đó, hãy tạo collection thử khác
// hoặc dọn đúng các document do mình tạo trước khi nạp lại.
demo.insertMany([
  {
    _id: ObjectId(HEX_ID),
    kind: "object-id",
    description: "Document lưu _id bằng BSON ObjectId"
  },
  {
    _id: HEX_ID,
    kind: "string-id",
    description: "Document lưu _id bằng BSON string"
  },
  {
    _id: "order-001",
    kind: "business-id",
    description: "ID nghiệp vụ không thể chuyển thành ObjectId"
  }
]);
~~~

Hai document đầu tiên cố tình có cùng biểu diễn `507f1f77bcf86cd799439011` nhưng khác kiểu. Vì tính duy nhất của `_id` được xét theo giá trị BSON, cả hai lần chèn đều có thể thành công. Nếu chạy lại `insertMany`, bạn sẽ gặp `E11000 duplicate key` do dữ liệu đã có sẵn; không dùng `drop()` trên collection không thuộc phạm vi thử nghiệm.

### 2.2. Truy vấn minh họa sự khác biệt

~~~javascript
// Truy vấn bằng chuỗi: kind = "string-id".
demo.findOne({ _id: HEX_ID });

// Truy vấn bằng ObjectId: kind = "object-id".
demo.findOne({ _id: ObjectId(HEX_ID) });

// Chuỗi nghiệp vụ: kind = "business-id".
demo.findOne({ _id: "order-001" });

// Đếm các document có kiểu _id khác nhau.
demo.countDocuments({ _id: { $type: "string" } });   // 2
demo.countDocuments({ _id: { $type: "objectId" } }); // 1
~~~

`$type` kiểm tra trực tiếp kiểu BSON. Với dữ liệu mẫu ban đầu, có hai chuỗi (hex và `order-001`) và một ObjectId. Khi dùng `find({ _id: { $type: "objectId" } })`, kết quả chỉ gồm document có `_id` thực sự mang kiểu ObjectId.

Bạn cũng có thể quan sát kiểu của từng giá trị trong một lần truy vấn:

~~~javascript
demo.aggregate([
  {
    $project: {
      _id: 1,
      kind: 1,
      idBsonType: { $type: "$_id" }
    }
  },
  { $sort: { kind: 1 } }
]);
// idBsonType: "string" hoặc "objectId".
~~~

Đây là bước kiểm chứng đáng tin cậy khi hai bản ghi có chuỗi ID trông giống nhau trên giao diện.

## 3. Quy tắc ánh xạ `_id` của Spring Data MongoDB

Khi thao tác qua `MongoTemplate` hoặc repository, Spring Data sử dụng `MappingMongoConverter` để chuyển đổi giữa đối tượng Java và document BSON. Theo quy tắc ánh xạ mặc định:

- Thuộc tính được đánh dấu `@Id` của Spring Data (`org.springframework.data.annotation.Id`) được ánh xạ vào `_id`.
- Thuộc tính tên `id` không có annotation đặc biệt cũng thường được nhận diện là identifier và ánh xạ vào `_id`.
- Với identifier Java kiểu `String` theo cơ chế `@Id` thông thường, Spring Data **thử chuyển** giá trị thành BSON `ObjectId` nếu có thể. Nếu không chuyển được, giá trị được lưu như `string`.
- `@MongoId` cho phép điều khiển kiểu đích thay vì phụ thuộc cơ chế tự thử chuyển nói trên.

Điều quan trọng là **kiểu Java của property** và **kiểu BSON thực tế của `_id`** không nhất thiết giống nhau. Điều này cũng ảnh hưởng đến **bộ lọc truy vấn** được Spring Data tạo ra, không chỉ đến thao tác `insert` và `save`.

### 3.1. `@Id String`: chuyển được thì dùng `ObjectId`

~~~java
package com.example.identity;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "identity_type_demo_003")
public class AutoIdDocument {
    @Id
    private String id;
    private String kind;

    protected AutoIdDocument() { }

    public AutoIdDocument(String id, String kind) {
        this.id = id;
        this.kind = kind;
    }

    public String getId() { return id; }
    public String getKind() { return kind; }
}
~~~

Giả sử ứng dụng lưu bằng:

~~~java
String hexId = "507f1f77bcf86cd799439011";

template.insert(
    new AutoIdDocument(hexId, "object-id")
);
~~~

Với cấu hình mapping mặc định, `hexId` là chuỗi có thể chuyển thành `ObjectId` nên `_id` **được lưu dưới kiểu BSON ObjectId**. Nếu truyền `"order-001"` vào cùng thuộc tính `@Id String id`, giá trị không chuyển được thành ObjectId và sẽ được lưu dưới dạng BSON string.

> **Chú ý về ví dụ:** Collection thực hành phần 2 đã có document ObjectId tương ứng. Đoạn `insert` ở đây chỉ dùng để minh họa kết quả ánh xạ, **không chạy lại trực tiếp trên collection đã nạp dữ liệu**, vì sẽ gây lỗi trùng `_id`.

Một hệ thống sử dụng `@Id String` có thể vô tình sinh dữ liệu **hai kiểu ID trong một collection** nếu ID lúc thì là chuỗi hex 24 ký tự, lúc lại là mã nghiệp vụ. Đó là lý do việc chọn `String` trong entity chưa đủ để xác định chính sách lưu trữ.

### 3.2. `@MongoId` mặc định: giữ kiểu Java thực tế

~~~java
package com.example.identity;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "identity_type_demo_003")
public class StringIdDocument {
    @MongoId
    private String id;
    private String kind;

    protected StringIdDocument() { }

    public StringIdDocument(String id, String kind) {
        this.id = id;
        this.kind = kind;
    }

    public String getId() { return id; }
    public String getKind() { return kind; }
}
~~~

`@MongoId` mặc định sử dụng `FieldType.IMPLICIT`, nghĩa là giữ kiểu giá trị thực tế của thuộc tính; với `String id`, `_id` được lưu là BSON string **ngay cả khi** chuỗi trông như mã ObjectId hợp lệ.

Có thể chỉ rõ ý định bằng annotation:

~~~java
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@MongoId(FieldType.STRING)
private String id;
~~~

`@MongoId(FieldType.STRING)` thể hiện rõ chính sách “ID là chuỗi nghiệp vụ”; đặc biệt hữu ích khi ID có khả năng tình cờ trùng định dạng 24 ký tự hex.

### 3.3. `@MongoId(FieldType.OBJECT_ID)`: ép kiểu đích là ObjectId

Khi ứng dụng muốn giữ API Java `String` nhưng lưu trữ `_id` dưới BSON `ObjectId`:

~~~java
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "identity_type_demo_003")
public class ExplicitObjectIdDocument {
    @MongoId(FieldType.OBJECT_ID)
    private String id;
    private String kind;

    protected ExplicitObjectIdDocument() { }

    public ExplicitObjectIdDocument(String id, String kind) {
        this.id = id;
        this.kind = kind;
    }

    public String getId() { return id; }
    public String getKind() { return kind; }
}
~~~

Với một giá trị `String` hex hợp lệ, mapping sẽ cố chuyển thành `ObjectId` để lưu và truy vấn. Phía API nhận ID từ người dùng nên **xác thực định dạng trước khi dùng**; đừng giả định một chuỗi ID nghiệp vụ bất kỳ đều là ObjectId hợp lệ. Nếu toàn hệ thống bắt buộc dùng ObjectId, dùng property `org.bson.types.ObjectId` còn giúp biểu diễn hợp đồng kiểu dữ liệu rõ ràng.

### 3.4. So sánh ba lựa chọn ánh xạ

| Khai báo Java | `_id` khi giá trị ID là chuỗi hex hợp lệ | `_id` khi giá trị là `"order-001"` | Ghi chú |
| --- | --- | --- | --- |
| `@Id String id` | Thử chuyển thành BSON `objectId` | Lưu BSON `string` | Có thể sinh dữ liệu lẫn kiểu |
| `@MongoId String id` | BSON `string` | BSON `string` | Giữ kiểu Java |
| `@MongoId(FieldType.STRING) String id` | BSON `string` | BSON `string` | Đặt chính sách chuỗi tường minh |
| `@MongoId(FieldType.OBJECT_ID) String id` | Thử chuyển thành BSON `objectId` | Không nên dùng ID không hợp lệ | Cần kiểm soát đầu vào |
| `@Id ObjectId id` | BSON `objectId` | Không thể gán `"order-001"` trực tiếp | Hợp với mô hình ID ObjectId nhất quán |

Điểm cốt lõi: chọn một chính sách cho **toàn bộ collection và vòng đời entity**, gồm lúc tạo, đọc, sửa, xóa và tham chiếu từ các document khác. Không nên thay đổi annotation chỉ để “làm cho một truy vấn chạy” khi chưa xem dữ liệu cũ trong MongoDB.

## 4. Vì sao `findById()` có thể trả về `null` / `Optional.empty()`?

Giả sử collection chứa **cả hai** document:

~~~javascript
{ _id: ObjectId("507f1f77bcf86cd799439011"), kind: "object-id" }
{ _id: "507f1f77bcf86cd799439011", kind: "string-id" }
~~~

Ở phía Spring Data:

~~~java
String id = "507f1f77bcf86cd799439011";

// Theo @Id String: converter thử dùng ObjectId cho truy vấn.
AutoIdDocument objectDoc = template.findById(id, AutoIdDocument.class);
// Với dữ liệu mẫu: kind = "object-id".

// Theo @MongoId String: converter giữ BSON string.
StringIdDocument stringDoc = template.findById(id, StringIdDocument.class);
// Với dữ liệu mẫu: kind = "string-id".
~~~

Hai lời gọi có cùng biến Java `String` và cùng collection, nhưng **metadata của entity khác nhau**. `MongoTemplate` áp dụng converter theo kiểu entity đích khi tạo query. Trong trường hợp này:

~~~text
AutoIdDocument  (@Id String):
  _id = ObjectId("507f1f77bcf86cd799439011")

StringIdDocument (@MongoId String):
  _id = "507f1f77bcf86cd799439011"
~~~

Nếu collection **chỉ** có bản ghi `_id` BSON string mà entity dùng `@Id String`, thì `findById(hexId, AutoIdDocument.class)` có thể trả về `null` dù bạn nhìn thấy document có chuỗi ID giống hệt. Tương tự, khi collection chỉ chứa ObjectId mà entity cố định `@MongoId(FieldType.STRING)`, truy vấn có thể không khớp.

### 4.1. Repository cũng chịu tác động của mapping

~~~java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface AutoIdRepository
        extends MongoRepository<AutoIdDocument, String> {
}

public interface StringIdRepository
        extends MongoRepository<StringIdDocument, String> {
}
~~~

~~~java
String hexId = "507f1f77bcf86cd799439011";

// Thường nhắm đến document BSON objectId.
var a = autoIdRepository.findById(hexId);

// Nhắm đến document BSON string.
var b = stringIdRepository.findById(hexId);
~~~

`MongoRepository.findById()` sử dụng metadata mapping tương ứng với domain class, nên việc generic ID là `String` **không bảo đảm** truy vấn đến BSON string. Ngoài ra, `existsById()` và `deleteById()` cũng cần được kiểm tra trong cùng ngữ cảnh mapping; với kiểu `_id` không tương thích, các thao tác này có thể không ảnh hưởng document bạn tưởng là đích.

### 4.2. `Criteria.where("id")` và `Criteria.where("_id")` không phải “cửa thoát” tự động

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

String id = "507f1f77bcf86cd799439011";

// MappingMongoConverter ánh xạ property Java id sang _id.
Query mapped = Query.query(Criteria.where("id").is(id));

AutoIdDocument result = template.findOne(mapped, AutoIdDocument.class);
~~~

Spring Data ánh xạ **tên trường** và **kiểu dữ liệu** trong `Query` dựa trên entity. Vì vậy đổi chuỗi field trong `Criteria` từ `"id"` sang `"_id"` không phải cách bảo đảm giá trị giữ nguyên kiểu `String` khi vẫn truy vấn qua một entity mapping có quy tắc chuyển đổi ID.

Khi cần kiểm chứng BSON chính xác, hãy dùng `mongosh` hoặc API MongoDB Java Driver trực tiếp. Khi cần hành vi ổn định ở tầng Spring Data, giải pháp đúng là lựa chọn mapping nhất quán với kiểu lưu trữ.

## 5. So sánh truy vấn trực tiếp và truy vấn qua Spring Data

### 5.1. `mongosh` không tự chuyển kiểu trong điều kiện bằng

~~~javascript
const raw = "507f1f77bcf86cd799439011";

// Chỉ khớp chuỗi.
demo.findOne({ _id: raw });

// Chỉ khớp BSON ObjectId.
demo.findOne({ _id: ObjectId(raw) });

// Xem trực tiếp kiểu _id của từng bản ghi.
demo.find({}, { _id: 1, kind: 1 });
~~~

### 5.2. Java Driver: chọn đúng kiểu điều kiện

Nếu đang xử lý một trường hợp dữ liệu lẫn kiểu và cần xem chính xác BSON mà không để Spring Data tự ánh xạ:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.bson.types.ObjectId;

String hexId = "507f1f77bcf86cd799439011";
MongoCollection<Document> rawCollection = template.getDb()
    .getCollection("identity_type_demo_003");

// Document có _id kiểu BSON string.
Document stringMatch = rawCollection
    .find(Filters.eq("_id", hexId))
    .first();

// Document có _id kiểu BSON objectId.
Document objectIdMatch = rawCollection
    .find(Filters.eq("_id", new ObjectId(hexId)))
    .first();
~~~

Ở đây `template.getDb().getCollection(...)` trả về API của MongoDB Java Driver, và `Filters.eq()` nhận giá trị có kiểu rõ ràng. Mã trên dùng cho **chẩn đoán hoặc thao tác có chủ đích**; trong logic nghiệp vụ thông thường, ưu tiên mô hình entity và repository có kiểu ID nhất quán.

### 5.3. Kiểm tra chuỗi có thể chuyển thành ObjectId

~~~java
import org.bson.types.ObjectId;

String rawId = "507f1f77bcf86cd799439011";

if (ObjectId.isValid(rawId)) {
    ObjectId objectId = new ObjectId(rawId);
    // Chỉ dùng objectId khi hợp đồng lưu trữ yêu cầu BSON ObjectId.
}
~~~

`ObjectId.isValid(rawId)` chỉ kiểm tra **định dạng chuỗi có thể biểu diễn ObjectId**. Nó **không truy cập database** và không chứng minh document với ID ấy được lưu dưới kiểu BSON ObjectId. Ví dụ `rawId` có định dạng hợp lệ nhưng document có thể vẫn là `{ _id: rawId }`.

Đừng chuyển mọi chuỗi 24 ký tự thành ObjectId theo thói quen. Đầu tiên phải biết collection/entity đang áp dụng quy tắc định danh nào.

## 6. Lỗi truy vấn khác kiểu không chỉ nằm ở `find`

Kiểu `_id` không tương thích có thể ảnh hưởng toàn bộ CRUD:

| Thao tác | Hậu quả nếu filter dùng sai BSON type |
| --- | --- |
| `findOne` / `findById` | Không tìm thấy document; trả về `null` hoặc `Optional.empty()` |
| `countDocuments` / `existsById` | Trả về 0 hoặc `false` dù document cùng giá trị hiển thị tồn tại |
| `updateOne` / `MongoTemplate.updateFirst` | `matchedCount = 0`; không cập nhật |
| `deleteOne` / `deleteById` | `deletedCount = 0` hoặc không xóa bản ghi mong muốn |
| `replaceOne` | Không khớp document hiện có |
| `upsert: true` | Có thể tạo thêm document BSON `_id` kiểu khác, dẫn đến bản ghi trùng về mặt nghiệp vụ |
| `save` | Có thể ghi một document khác thay vì ghi lên document bạn nghĩ đang có, tùy metadata và kiểu ID |

Ví dụ sau dễ tạo ra lỗi logic:

~~~javascript
// Đã có document:
{ _id: "507f1f77bcf86cd799439011", status: "DRAFT" }

// Bộ lọc BSON ObjectId sẽ không khớp chuỗi _id ở trên.
db.identity_type_demo_003.updateOne(
  { _id: ObjectId("507f1f77bcf86cd799439011") },
  { $set: { status: "PUBLISHED" } }
);
// Nếu chỉ tồn tại document string: matchedCount = 0.
~~~

Trong bộ dữ liệu thử nghiệm của phần 2 **có cả** ObjectId và chuỗi, nên thao tác trên lại khớp document ObjectId khác. Đây là rủi ro lớn hơn việc trả rỗng: yêu cầu có thể **đọc hoặc ghi vào sai bản ghi**, nếu hai kiểu `_id` được phép cùng tồn tại và cùng mang một nội dung biểu diễn.

Đặc biệt cẩn thận với `upsert: true`: cùng một “mã” ở tầng nghiệp vụ có thể sinh hai document hợp lệ ở MongoDB vì `_id` khác kiểu BSON. Unique index mặc định trên `_id` không tự phát hiện sự trùng lặp ý nghĩa nghiệp vụ này.

## 7. Cách chẩn đoán khi ứng dụng tìm không thấy document

Giả sử HTTP endpoint nhận `GET /orders/507f1f77bcf86cd799439011` và `repository.findById(id)` trả về rỗng, nhưng người vận hành thấy document tương ứng trong MongoDB UI.

### Bước 1 — Xác nhận đúng database và collection

~~~javascript
db.getName();
db.getCollectionNames();
db.identity_type_demo_003.findOne({});
~~~

Trong ứng dụng Spring Data, kiểm tra `@Document(collection = "...")` hoặc quy tắc tên collection, database trong connection URI, active profile và `MongoTemplate` đang được inject. Trỏ sai môi trường cũng gây triệu chứng “truy vấn không thấy” nhưng không liên quan chuyển đổi ID.

### Bước 2 — Xem kiểu BSON gốc

~~~javascript
const id = "507f1f77bcf86cd799439011";

db.identity_type_demo_003.findOne({ _id: id });
db.identity_type_demo_003.findOne({ _id: ObjectId(id) });

db.identity_type_demo_003.aggregate([
  {
    $match: {
      _id: { $in: [id, ObjectId(id)] }
    }
  },
  {
    $project: {
      _id: 1,
      kind: 1,
      idType: { $type: "$_id" }
    }
  }
]);
~~~

Nếu chỉ một cách truy vấn có kết quả, đã xác định được hướng lệch kiểu. Nếu cả hai đều có kết quả, collection chứa **hai document có cùng biểu diễn ID** nhưng khác kiểu. Nếu đều rỗng, kiểm tra giá trị ID, database, collection và dữ liệu thực tế.

### Bước 3 — Soát annotation và kiểu ID trong Java

~~~text
@Id String id
    => có thể chuyển hex String sang ObjectId

@MongoId String id
    => mặc định giữ String

@MongoId(FieldType.STRING) String id
    => yêu cầu kiểu đích String

@MongoId(FieldType.OBJECT_ID) String id
    => thử chuyển sang ObjectId

@Id ObjectId id
    => biểu diễn ObjectId rõ trong Java
~~~

Đồng thời xem generic type của repository, ví dụ `MongoRepository<OrderDocument, String>` hay `MongoRepository<OrderDocument, ObjectId>`. Generic này ảnh hưởng kiểu ID tại API, nhưng **chính metadata mapping của entity** quyết định phép chuyển đổi với trường `_id`.

### Bước 4 — Kiểm tra điểm ghi dữ liệu

Tìm luồng dữ liệu đã tạo document:

- Thao tác qua `MongoRepository.save()` hoặc `MongoTemplate.insert()` của entity có `@Id String`?
- Import qua `mongosh`, MongoDB Compass, driver thô hoặc job ETL gán `_id` dưới dạng chuỗi?
- Một phiên bản ứng dụng trước từng dùng `@MongoId(FieldType.STRING)`, còn phiên bản mới chuyển sang `@Id`?
- Có nhiều service chia sẻ collection nhưng khai báo kiểu ID khác nhau?

Nếu nơi ghi và nơi đọc dùng hai quy tắc mapping, lỗi sẽ tái phát dù sửa tạm một query. Cần làm thống nhất **cả đường ghi lẫn đường đọc**.

### Bước 5 — Kiểm tra kết quả thao tác, không đoán theo HTTP status

Với cập nhật hoặc xóa, xem `matchedCount`, `modifiedCount`, `deletedCount` và chính document trả về. Một API trả 200 không chứng minh filter đã khớp bản ghi; hãy gắn kiểm tra kết quả vào nghiệp vụ.

## 8. Thiết kế định danh nhất quán ngay từ đầu

Chọn kiểu ID theo **hợp đồng dữ liệu**, rồi áp dụng xuyên suốt mapper, repository, DTO, sự kiện và nơi lưu tham chiếu.

### Lựa chọn A — Toàn bộ `_id` là BSON ObjectId

~~~java
package com.example.identity;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("orders")
public class OrderDocument {
    @Id
    private ObjectId id;
    private String state;

    public ObjectId getId() { return id; }
    public String getState() { return state; }
}
~~~

Repository:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, ObjectId> {
}
~~~

Khi nhận ID dạng chuỗi từ API, kiểm tra và chuyển đổi tại ranh giới:

~~~java
import org.bson.types.ObjectId;

public ObjectId parseOrderId(String rawId) {
    if (rawId == null || !ObjectId.isValid(rawId)) {
        throw new IllegalArgumentException("Invalid MongoDB ObjectId");
    }
    return new ObjectId(rawId);
}
~~~

Đây là lựa chọn rõ ràng nếu MongoDB là nơi cấp ID chính. Giá trị gửi ra API có thể dùng `objectId.toHexString()`; không cần ép kiểu dữ liệu bên trong entity thành `String` chỉ vì URL chứa văn bản.

### Lựa chọn B — Toàn bộ `_id` là BSON string

~~~java
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document("orders")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;
    private String state;

    public String getId() { return id; }
    public String getState() { return state; }
}
~~~

Repository tương ứng:

~~~java
public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {
}
~~~

Lựa chọn này phù hợp khi `_id` là UUID ở dạng chuỗi, mã đơn hàng do hệ thống cấp hoặc mã từ nguồn bên ngoài. Dù có một mã vô tình dài đúng 24 ký tự hex, `@MongoId(FieldType.STRING)` vẫn giữ kiểu BSON string.

**Quy ước bắt buộc:** không dùng đồng thời hai class `OrderDocument` có cùng tên trong một file; các khai báo trên là **hai thiết kế thay thế** cho từng dự án. Hãy chọn một thiết kế trước khi lưu dữ liệu.

### Lựa chọn C — Java dùng `String`, MongoDB dùng BSON ObjectId

~~~java
@Document("orders")
public class OrderDocument {
    @MongoId(FieldType.OBJECT_ID)
    private String id;
    private String state;
}
~~~

Thiết kế này hữu ích khi tầng Java muốn biểu diễn ID là `String` nhưng storage dùng ObjectId. Tuy nhiên API vẫn phải xác thực chuỗi 24 ký tự hex và nhất quán quy tắc mapping ở tất cả repository/template.

| Tiêu chí | ObjectId thực (`ObjectId id`) | Chuỗi thực (`@MongoId(FieldType.STRING)`) |
| --- | --- | --- |
| Kiểu BSON mong muốn | `objectId` | `string` |
| Sinh ID | MongoDB/driver có thể sinh ObjectId | Ứng dụng thường chủ động cấp ID nghiệp vụ |
| Nhận ID từ HTTP | Parse chuỗi hex thành `ObjectId` | Dùng trực tiếp chuỗi sau validation nghiệp vụ |
| Nguy cơ chuyển kiểu ngầm | Thấp khi kiểu entity chuẩn xác | Thấp khi dùng `@MongoId` rõ ràng |
| Dùng mã ngoại lai không phải hex | Không phù hợp làm ObjectId | Phù hợp |

Không có kiểu nào luôn “tốt hơn” cho mọi hệ thống. Sự nhất quán giữa **dữ liệu đã lưu** và **metadata ánh xạ** quan trọng hơn việc chọn hình thức hiển thị ID.

## 9. Đã có dữ liệu lẫn `ObjectId` và `string`: xử lý thế nào?

Nếu production đã chứa `_id` khác kiểu, **đừng chỉ thay `@Id` thành `@MongoId`** rồi triển khai ngay. Thay annotation sẽ làm thay đổi kiểu filter do Spring Data tạo; các bản ghi cũ có thể không được tìm thấy hoặc không được cập nhật.

Một lộ trình an toàn gồm các bước sau.

### 9.1. Kiểm kê trước khi thay đổi

Trên database được phép phân tích, thống kê kiểu:

~~~javascript
db.orders.aggregate([
  {
    $group: {
      _id: { $type: "$_id" },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
~~~

Đối chiếu với nguồn sinh dữ liệu: entity nào ghi, job import nào ghi, có document nào tham chiếu ID bằng `String` hoặc `ObjectId` trong những trường khác không. Kiểm tra xem một giá trị hex có đồng thời tồn tại ở cả hai kiểu, vì đây là **trùng lặp logic** mà unique index `_id` không chặn.

### 9.2. Định nghĩa trạng thái đích

Ví dụ chọn `_id` BSON string cho toàn hệ thống vì ID là mã đơn hàng. Quy ước:

1. Tất cả writer mới sử dụng `@MongoId(FieldType.STRING)`.
2. Các điểm đọc cũ cần được hỗ trợ trong thời gian chuyển đổi theo một cơ chế tương thích được kiểm soát.
3. Mọi nơi lưu khóa tham chiếu phải cùng quy ước biểu diễn.
4. Các API có kết quả không rõ ràng do hai loại `_id` trùng biểu diễn phải có quy tắc giải quyết trước khi migration.

### 9.3. Không thể `$set` trực tiếp `_id`

MongoDB không cho phép cập nhật giá trị `_id` của document hiện có bằng `$set`:

~~~javascript
// Sai: không thể thay _id bằng cập nhật thông thường.
db.orders.updateOne(
  { _id: ObjectId("507f1f77bcf86cd799439011") },
  { $set: { _id: "507f1f77bcf86cd799439011" } }
);
~~~

Đổi kiểu `_id` về cơ bản đòi hỏi **tạo document mới với ID đích**, xác thực dữ liệu, cập nhật tham chiếu liên quan nếu có và sau đó mới xử lý document cũ. Nếu hai kiểu đã cùng tồn tại, không thể chèn document đích với `_id` trùng kiểu/giá trị mà không có chính sách gộp, từ chối hoặc ưu tiên.

Không tự động chép/xóa dữ liệu production theo ví dụ: cần phương án backup, xử lý đồng thời ghi, idempotency, kiểm tra uniqueness và rollback thích hợp. Transaction MongoDB có thể giúp đảm bảo tính nguyên tử cho một số thao tác cùng cluster nếu topology và điều kiện cho phép, nhưng không tự giải quyết các tham chiếu ở hệ thống ngoài.

### 9.4. Kiểm chứng sau migration

- Thống kê lại `$type` của `_id`, xác nhận không còn kiểu ngoài quy ước.
- So sánh số lượng document và các khóa nghiệp vụ trước/sau.
- Kiểm tra `findById`, `existsById`, `updateFirst`, `deleteById` và `save` qua entity/repository chính thức.
- Kiểm tra truy vấn aggregation, sự kiện, API và các collection chứa reference đến ID cũ.
- Theo dõi lỗi “not found” bất thường và số lượng upsert trong giai đoạn chuyển đổi.

Mục đích là khôi phục **một quy tắc định danh xuyên suốt**, tránh vận hành lâu dài với hai cách diễn giải cho cùng một mã.

## 10. Kiểm thử hồi quy để tránh lặp lỗi

Đây là trường hợp phù hợp để viết **integration test** với MongoDB thật hoặc MongoDB Testcontainers, vì logic phụ thuộc chuyển đổi BSON của MongoDB driver và Spring Data converter. Mock repository thường không phát hiện được sai kiểu `_id`.

Ví dụ khung kiểm thử:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@SpringBootTest
class IdTypeMappingIntegrationTest {
    private static final String COLLECTION = "identity_type_demo_003";
    private static final String HEX = "507f1f77bcf86cd799439011";

    @Autowired MongoTemplate template;

    @Test
    void idMappingDeterminesWhichBsonTypeIsQueried() {
        // Chuẩn bị fixture trong một database test riêng.
        // Mỗi lần chạy phải bảo đảm chỉ các document fixture thuộc bài này.
        var collection = template.getDb().getCollection(COLLECTION);
        collection.deleteMany(new Document("_id",
            new Document("$in", java.util.List.of(HEX, new ObjectId(HEX)))));
        collection.insertOne(new Document("_id", HEX)
            .append("kind", "string-id"));
        collection.insertOne(new Document("_id", new ObjectId(HEX))
            .append("kind", "object-id"));

        AutoIdDocument mappedToObjectId =
            template.findById(HEX, AutoIdDocument.class);
        StringIdDocument mappedToString =
            template.findById(HEX, StringIdDocument.class);

        assertThat(mappedToObjectId).isNotNull();
        assertThat(mappedToObjectId.getKind()).isEqualTo("object-id");
        assertThat(mappedToString).isNotNull();
        assertThat(mappedToString.getKind()).isEqualTo("string-id");
    }
}
~~~

Test trên phụ thuộc những class mapping ở mục 3, kết nối MongoDB test đã cấu hình và quyền ghi collection. **Chỉ chạy trên database test riêng**: thao tác chuẩn bị sẽ xóa hai document có ID tương ứng trong collection. Trong bộ test thực tế, ưu tiên mỗi test có collection/namespace riêng, dọn fixture bằng `try/finally` hoặc lifecycle test và không dùng ID cố định trùng dữ liệu người khác.

Nên bổ sung trường hợp `@Id String` với ID không phải hex (`order-001`), `@MongoId(FieldType.STRING)` với ID hex và kiểm tra BSON qua driver trực tiếp. Các case này làm rõ hành vi lưu/đọc sau khi nâng cấp Spring Data.

## 11. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân cần xem xét | Cách xác minh |
| --- | --- | --- |
| `findById(hex)` trả `Optional.empty()` nhưng Compass có document | Entity chuyển `String` thành ObjectId, database lưu BSON string (hoặc ngược lại) | `mongosh` tìm lần lượt bằng `String` và `ObjectId`; kiểm tra `$type` |
| `findById("order-001")` được, nhưng `findById(hex)` không được | `@Id String` chỉ chuyển những ID hợp lệ sang ObjectId | Kiểm tra hai dạng ID bằng `$type` |
| `updateFirst` có `matchedCount = 0` | Bộ lọc `_id` sai BSON type hoặc sai database | So sánh filter thô với truy vấn Spring Data |
| `upsert` tạo bản ghi giống mã có sẵn | `_id` dùng kiểu BSON khác, không vi phạm unique index `_id` | Đếm các ID theo `$type`, tìm cả hai biến thể |
| Sau khi đổi `@Id` thành `@MongoId`, nhiều bản ghi không tìm thấy | Quy tắc query của ứng dụng đã thay đổi, dữ liệu cũ chưa migrate | Kiểm tra BSON `_id` cũ và mới; lập kế hoạch migration |
| ID là chuỗi nhưng API gửi `ObjectId` khác giá trị | Parse ID chưa phù hợp hợp đồng dữ liệu | Dùng `ObjectId.isValid` chỉ khi ứng dụng thực sự dùng ObjectId |
| `findById` rỗng cho mọi ID | Có thể sai database/collection, chứ không chỉ sai kiểu | Kiểm tra URI, `@Document`, dữ liệu thô, quyền |

## 12. Bài thực hành

### Bài 1 — Phân loại kiểu

Cho hai document:

~~~javascript
{ _id: ObjectId("64a1f34b60cc1200441a0222"), state: "NEW" }
{ _id: "64a1f34b60cc1200441a0222", state: "PAID" }
~~~

Câu hỏi: Hai document có vi phạm unique index `_id` không? Truy vấn nào tìm được `state: "PAID"`?

**Đáp án:** Không, vì `_id` khác kiểu BSON. Truy vấn `findOne({ _id: "64a1f34b60cc1200441a0222" })` tìm đúng document string, còn `ObjectId("...")` tìm document `NEW`.

### Bài 2 — Thay đổi annotation

Một service lưu `@Id String id` với giá trị `"64a1f34b60cc1200441a0222"`. Sau đó refactor thành `@MongoId(FieldType.STRING) String id` nhưng không migrate dữ liệu. Điều gì có thể xảy ra?

**Đáp án:** Bản ghi cũ được lưu bằng BSON ObjectId theo mapping `@Id`, nhưng query mới cố dùng BSON string. `findById` có thể trả rỗng; các thao tác khác có thể không khớp, và một lời gọi upsert có thể tạo bản ghi thứ hai. Cần kiểm kê kiểu dữ liệu, quyết định quy ước ID và migrate hoặc hỗ trợ tương thích có chủ đích.

### Bài 3 — Chọn chính sách định danh

Một hệ thống có ID như `"order-001"`, `"order-002"` và đôi lúc một mã external dài đúng 24 ký tự hex. Nên dùng loại ID nào để giữ dữ liệu nhất quán?

**Đáp án tham khảo:** `@MongoId(FieldType.STRING) String id` là lựa chọn trực quan nếu tất cả mã được xem là chuỗi nghiệp vụ. Đừng dùng `@Id String` rồi mong “mọi ID đều là BSON string”.

### Bài 4 — Sửa câu query

Database thực tế lưu:

~~~javascript
{ _id: ObjectId("64a1f34b60cc1200441a0222"), total: 100 }
~~~

Hãy viết lệnh `mongosh` tìm chính xác document đó và giải thích tại sao `{ _id: "64a1f34b60cc1200441a0222" }` không khớp.

**Đáp án:**

~~~javascript
db.orders.findOne({
  _id: ObjectId("64a1f34b60cc1200441a0222")
});
~~~

Vì MongoDB so sánh theo kiểu BSON, điều kiện chuỗi và ObjectId là hai giá trị khác nhau.

## Tài liệu tham khảo

- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): quy tắc ánh xạ `_id` và chuyển đổi `String`/`ObjectId` trong `MappingMongoConverter`.
- [Spring Data MongoDB — `@MongoId` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/MongoId.html): `FieldType.IMPLICIT`, `STRING`, `OBJECT_ID` và chính sách chuyển đổi identifier.
- [MongoDB Manual — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/): kiểu BSON và biểu diễn `ObjectId`.
- [MongoDB Manual — `$type` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/type/): tìm document theo kiểu BSON.
- [Spring Data MongoDB — Template CRUD Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): truy vấn, cập nhật và các API của `MongoTemplate`.

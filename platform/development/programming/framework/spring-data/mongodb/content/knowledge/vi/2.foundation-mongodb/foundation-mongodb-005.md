# Phân biệt trường không tồn tại, `null`, chuỗi rỗng và array rỗng trong MongoDB

## 1. Vì sao cần phân biệt?

MongoDB lưu tài liệu theo BSON. Hai document cùng thuộc một collection có thể có tập trường khác nhau; một trường cũng có thể mang các kiểu giá trị khác nhau. Vì vậy, **không có trường** (`missing`), **có trường với giá trị `null`**, **chuỗi `""`** và **mảng `[]`** là bốn trạng thái dữ liệu khác nhau. Việc gộp chúng dễ gây lỗi khi lọc dữ liệu, cập nhật một phần, ánh xạ sang Java hoặc phân tích số liệu.

Trong Spring Data MongoDB, sự khác biệt này ảnh hưởng trực tiếp đến `Criteria`, `MongoTemplate`, repository, cách ghi thuộc tính Java và cách đọc lại document. Ví dụ: một ứng dụng quản lý người dùng cần phân biệt người chưa khai báo biệt danh, người chủ động xóa biệt danh và người gửi chuỗi rỗng; với danh sách vai trò, “chưa biết danh sách” có thể khác “đã xác nhận không có vai trò nào”.

| Trạng thái | Document minh họa | Ý nghĩa ở mức BSON | Câu hỏi nghiệp vụ cần quyết định |
|---|---|---|---|
| Trường không tồn tại | `{ "_id": 1 }` | Không có khóa `value` | Chưa gửi, chưa áp dụng hay đã xóa trường? |
| `null` tường minh | `{ "_id": 2, "value": null }` | Khóa có mặt, giá trị BSON Null (type 10) | Đã xác định là chưa có giá trị hay cố ý xóa? |
| Chuỗi rỗng | `{ "_id": 3, "value": "" }` | Khóa có mặt, giá trị BSON String dài 0 ký tự | Người dùng nhập rỗng có hợp lệ không? |
| Mảng rỗng | `{ "_id": 4, "value": [] }` | Khóa có mặt, giá trị BSON Array có 0 phần tử | Danh sách đã biết và hiện không có phần tử? |

**Không có quy ước nghiệp vụ mặc định cho bốn trạng thái này.** Nhóm phát triển phải thống nhất ý nghĩa và quy tắc chuẩn hóa theo từng field. `""` không tương đương `null`; `[]` không tương đương trường bị thiếu. Số `0`, Boolean `false` và chuỗi chỉ có khoảng trắng `" "` cũng không phải các trạng thái rỗng nói trên.

## 2. Dữ liệu mẫu để quan sát truy vấn

Chạy trong `mongosh` trên một database thử nghiệm:

```javascript
db.valueStatesDemo.insertMany([
  { _id: 1, label: "missing" },
  { _id: 2, label: "explicit null", value: null },
  { _id: 3, label: "empty string", value: "" },
  { _id: 4, label: "empty array", value: [] },
  { _id: 5, label: "nonempty string", value: "hello" },
  { _id: 6, label: "array of strings", value: ["hello"] },
  { _id: 7, label: "array containing empty string", value: [""] },
  { _id: 8, label: "zero", value: 0 }
]);

db.valueStatesDemo.find({}, { _id: 1, value: 1 }).sort({ _id: 1 });
```

Trường `value` được cố ý dùng với nhiều kiểu để so sánh hành vi của MongoDB. Với hệ thống thật, nên thiết kế một field có kiểu dữ liệu ổn định hoặc khai báo rõ những kiểu được phép.

## 3. Truy vấn bốn trạng thái

| Mục tiêu | Bộ lọc MongoDB | Kết quả `_id` từ dữ liệu mẫu |
|---|---|---|
| Trường hoàn toàn không tồn tại | `{ value: { $exists: false } }` | `1` |
| Trường có tồn tại, dù giá trị là gì | `{ value: { $exists: true } }` | `2, 3, 4, 5, 6, 7, 8` |
| Giá trị là BSON `null` tường minh | `{ value: { $type: "null" } }` | `2` |
| `null` **hoặc** trường không tồn tại | `{ value: null }` | `1, 2` |
| Chuỗi rỗng theo phép so khớp thông thường | `{ value: "" }` | `3, 7` |
| Mảng không có phần tử | `{ value: { $size: 0 } }` | `4` |
| Giá trị không phải `null` và trường có tồn tại | `{ value: { $ne: null } }` | `3, 4, 5, 6, 7, 8` |

### 3.1. `$exists` kiểm tra sự hiện diện của khóa

```javascript
db.valueStatesDemo.find({ value: { $exists: false } }); // _id = 1
db.valueStatesDemo.find({ value: { $exists: true } });  // _id = 2..8
```

`$exists: true` **bao gồm cả** giá trị `null`, `""` và `[]`. Đừng dùng `$exists: true` để suy ra “có dữ liệu hữu ích”. Ngược lại, `$exists: false` chỉ chọn trường thiếu, không chọn trường có giá trị `null`.

### 3.2. `{ value: null }` không có nghĩa “chỉ null”

```javascript
db.valueStatesDemo.find({ value: null });                  // _id = 1, 2
db.valueStatesDemo.find({ value: { $type: 10 } });         // _id = 2
db.valueStatesDemo.find({ value: { $type: "null" } });     // _id = 2
db.valueStatesDemo.find({ value: { $exists: true, $eq: null } }); // _id = 2
```

MongoDB coi bộ lọc bằng `null` thông thường là điều kiện khớp cả **null tường minh** và **trường thiếu**. Trong trường hợp field chỉ chứa giá trị đơn, dùng `$type: 10` (tên kiểu `"null"`) hoặc kết hợp `$exists: true` với `$eq: null` để tìm null tường minh. **Nếu field có thể là mảng chứa `null`**, các điều kiện truy vấn này còn có thể khớp phần tử null bên trong mảng. Khi cần khẳng định **giá trị của chính field** là BSON Null, dùng `$expr` kiểm tra `{ $type: "$value" }` bằng `"null"`. Tương tự, `{ value: { $ne: null } }` chỉ lấy document có trường tồn tại và có giá trị không phải null; đừng giả định nó lấy cả trường thiếu.

### 3.3. Chuỗi rỗng khác mảng rỗng

```javascript
db.valueStatesDemo.find({ value: "" });             // _id = 3, 7
db.valueStatesDemo.find({ value: [] });             // _id = 4 trong tập mẫu
db.valueStatesDemo.find({ value: { $size: 0 } });   // _id = 4
```

Khi field là **mảng**, MongoDB thường so khớp điều kiện bằng một phần tử của mảng. Vì vậy `{ value: "" }` khớp cả `{ value: [""] }`. Truy vấn `$size: 0` tìm mảng có đúng 0 phần tử, không lấy `null`, chuỗi rỗng hay trường thiếu. `$size` đòi hỏi giá trị là mảng nhưng không tận dụng trực tiếp chỉ mục để so sánh độ dài; với tần suất lọc lớn có thể cần thêm trường số lượng phần tử được duy trì nhất quán.

**Lưu ý về `$type` trong truy vấn:** `{ value: { $type: "string" } }` có thể khớp một mảng chứa phần tử kiểu string, không chỉ field là chuỗi đơn. Cần kiểm tra kiểu **giá trị của chính field** khi dữ liệu có kiểu hỗn hợp.

### 3.4. Phân biệt chính xác bằng `$expr` và `$type`

Biểu thức aggregation `{ $type: "$value" }` trả về chuỗi `"missing"` khi field vắng mặt; các giá trị còn lại trong ví dụ có kiểu `"null"`, `"string"`, `"array"` hoặc `"int"`. Kết hợp `$expr` để kiểm tra kiểu của toàn bộ field:

```javascript
// Chỉ field có giá trị BSON Null, không lấy mảng [null]
db.valueStatesDemo.find({
  $expr: { $eq: [{ $type: "$value" }, "null"] }
}); // _id = 2

// Chỉ chuỗi rỗng đơn, không lấy mảng [""]
db.valueStatesDemo.find({
  $expr: {
    $and: [
      { $eq: [{ $type: "$value" }, "string"] },
      { $eq: ["$value", ""] }
    ]
  }
}); // _id = 3

// Chỉ field có kiểu array và không có phần tử
db.valueStatesDemo.find({
  $expr: {
    $eq: [
      { $cond: [{ $isArray: "$value" }, { $size: "$value" }, -1] },
      0
    ]
  }
}); // _id = 4

// Phân loại toàn bộ trường ngay trên server
db.valueStatesDemo.aggregate([
  { $project: {
      label: 1,
      valueKind: { $type: "$value" }
  } },
  { $sort: { _id: 1 } }
]);
```

Ở biểu thức tính độ dài, `$isArray` và `$cond` bảo vệ `$size` khỏi lỗi khi gặp chuỗi, số, `null` hoặc trường thiếu. Không dùng `$type: "missing"` trong bộ lọc truy vấn thông thường; `"missing"` là **kết quả của toán tử biểu thức** `$type` trong trường hợp này, không phải một BSON type lưu trong document.

## 4. Thực hiện với Spring Data MongoDB

`MongoTemplate` cho phép tạo truy vấn bằng `Query` và `Criteria`. Ví dụ dưới đây dùng collection `valueStatesDemo` và lớp `org.bson.Document` để quan sát giá trị BSON gần với dữ liệu gốc:

```java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.BasicQuery;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public class ValueStateQueries {
    private final MongoTemplate template;

    public ValueStateQueries(MongoTemplate template) {
        this.template = template;
    }

    public void demonstrate() {
        Query missing = Query.query(Criteria.where("value").exists(false));
        Query present = Query.query(Criteria.where("value").exists(true));
        Query nullOrMissing = Query.query(Criteria.where("value").is(null));
        Query explicitNull = Query.query(Criteria.where("value").type(10));
        Query emptyArray = Query.query(Criteria.where("value").size(0));
        Query ordinaryEmptyString = Query.query(Criteria.where("value").is(""));

        // Java 17+: kiểm tra chuỗi rỗng đơn bằng $expr.
        Query scalarEmptyString = new BasicQuery("""
            { "$expr": { "$and": [
                { "$eq": [ { "$type": "$value" }, "string" ] },
                { "$eq": [ "$value", "" ] }
            ] } }
            """);
        Query scalarNull = new BasicQuery("""
            { "$expr": { "$eq": [ { "$type": "$value" }, "null" ] } }
            """);

        long nMissing = template.count(missing, "valueStatesDemo"); // 1
        long nNull = template.count(explicitNull, "valueStatesDemo"); // 1
        long nNullOrMissing =
            template.count(nullOrMissing, "valueStatesDemo"); // 2
        long nEmptyArray = template.count(emptyArray, "valueStatesDemo"); // 1
        long nOrdinaryEmptyString =
            template.count(ordinaryEmptyString, "valueStatesDemo"); // 2
        long nScalarEmptyString =
            template.count(scalarEmptyString, "valueStatesDemo"); // 1
        long nScalarNull = template.count(scalarNull, "valueStatesDemo"); // 1

        // present: có đủ cả null, chuỗi rỗng, array rỗng...
        template.find(present, Document.class, "valueStatesDemo");
    }
}
```

Lưu ý các API truy vấn như `Criteria.where("value").is(null)` hoặc phương thức repository dẫn đến so sánh với null có thể kế thừa ngữ nghĩa “null **hoặc** missing” của MongoDB. Nếu nghiệp vụ cần null tường minh, phải biểu đạt rõ điều kiện kiểu BSON null. Với repository, hãy xem câu truy vấn được tạo ra bằng cách logging hoặc kiểm thử tích hợp thay vì dựa vào tên phương thức để suy luận.

## 5. Khi cập nhật document: `$unset` khác `$set`

Đây là nguồn phát sinh sai khác phổ biến khi nhận dữ liệu từ API cập nhật một phần:

```javascript
// Xóa hoàn toàn khóa khỏi document
db.valueStatesDemo.updateOne({ _id: 5 }, { $unset: { value: "" } });

// Giữ khóa, đặt giá trị null tường minh
db.valueStatesDemo.updateOne({ _id: 5 }, { $set: { value: null } });

// Giữ khóa, đặt chuỗi rỗng
db.valueStatesDemo.updateOne({ _id: 5 }, { $set: { value: "" } });

// Giữ khóa, đặt mảng rỗng
db.valueStatesDemo.updateOne({ _id: 5 }, { $set: { value: [] } });
```

Các lệnh trên là **những thao tác minh họa độc lập**; nếu chạy liên tiếp trên cùng `_id`, trạng thái cuối là `[]`. Trong Spring Data MongoDB:

```java
import org.bson.Document;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

Query byId = Query.query(Criteria.where("_id").is(5));

template.updateFirst(
    byId, new Update().unset("value"), Document.class, "valueStatesDemo");
template.updateFirst(
    byId, new Update().set("value", null), Document.class, "valueStatesDemo");
template.updateFirst(
    byId, new Update().set("value", ""), Document.class, "valueStatesDemo");
template.updateFirst(
    byId, new Update().set("value", java.util.List.of()),
    Document.class, "valueStatesDemo");
```

Với API `PATCH`, cần thiết kế hợp đồng rõ ràng: **không gửi field** có thể mang nghĩa “giữ nguyên”; **gửi `null`** có thể mang nghĩa “xóa giá trị”, “ghi null” hoặc “từ chối”, tùy đặc tả. Nếu dùng DTO chỉ có một thuộc tính `String` nullable, việc phân biệt “không gửi” và “gửi null” có thể bị mất ngay ở lớp giải mã JSON; khi cần hãy theo dõi sự hiện diện của khóa, dùng cấu trúc chuyên biệt cho PATCH hoặc sử dụng `JsonNode`/`Map` để xử lý.

## 6. Ánh xạ đối tượng Java không tự bảo tồn mọi trạng thái

Khi MongoDB được đọc vào một POJO Java có `String value`, giá trị của thuộc tính có thể là `null` ở cả trường hợp BSON null và trường thiếu. Chỉ nhìn thuộc tính Java sau khi deserialize thường **không thể biết** trước đó khóa có tồn tại trong document hay không. Với collection hỗn hợp, kiểu Java không phù hợp (ví dụ `List<String>` nhưng BSON đang lưu chuỗi) cũng có thể dẫn đến lỗi chuyển đổi hoặc kết quả phụ thuộc converter.

Khi ghi POJO, Spring Data MongoDB theo mặc định thường bỏ qua các thuộc tính `null`. Ở các phiên bản hỗ trợ, `@Field(write = Field.Write.ALWAYS)` yêu cầu ghi cả giá trị null:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document("members")
public class Member {
    @Id
    private String id;

    // Ghi BSON null khi nickname == null.
    @Field(write = Field.Write.ALWAYS)
    private String nickname;
}
```

Ví dụ chỉ minh họa lựa chọn ghi null; để sử dụng cần constructor/getter/setter hoặc cơ chế ánh xạ phù hợp của dự án. Hãy kiểm tra phiên bản Spring Data MongoDB đang dùng và document BSON thực tế, đặc biệt khi có converter tùy biến, default value, record/constructor binding hoặc update một phần. Với `List`, Java `null` và `Collections.emptyList()` biểu đạt hai trạng thái khác nhau; chỉ tạo danh sách rỗng theo mặc định nếu đó là quy ước nghiệp vụ mong muốn.

Nếu cần giữ nguyên sự khác biệt giữa missing và BSON null khi đọc, có thể truy cập `Document` hoặc đọc thêm trạng thái hiện diện bằng `containsKey("value")`:

```java
Document raw = template.findById(2, Document.class, "valueStatesDemo");
if (raw != null) {
    boolean present = raw.containsKey("value");
    Object value = raw.get("value"); // Có thể là null dù present == true
    System.out.println("present=" + present + ", value=" + value);
}
```

## 7. Tổng hợp dữ liệu: cẩn thận với `$ifNull`

Trong aggregation, `$ifNull` xử lý cả **giá trị null** và **giá trị thiếu** như null để dùng fallback. Nó không tự động thay thế chuỗi rỗng hay mảng rỗng:

```javascript
db.valueStatesDemo.aggregate([
  {
    $project: {
      label: 1,
      originalType: { $type: "$value" },
      normalized: { $ifNull: ["$value", "not provided"] }
    }
  }
]);
```

Với dữ liệu mẫu, `_id: 1` (missing) và `_id: 2` (null) đều nhận fallback `"not provided"`. Trong khi đó `_id: 3` vẫn có chuỗi `""` và `_id: 4` vẫn có `[]`. Nếu báo cáo cần bốn nhóm riêng, phân loại theo `$type` trước khi chuẩn hóa:

```javascript
db.valueStatesDemo.aggregate([
  {
    $project: {
      state: {
        $switch: {
          branches: [
            { case: { $eq: [{ $type: "$value" }, "missing"] },
              then: "missing" },
            { case: { $eq: [{ $type: "$value" }, "null"] },
              then: "explicit-null" },
            { case: { $and: [
                { $eq: [{ $type: "$value" }, "string"] },
                { $eq: ["$value", ""] }
              ] },
              then: "empty-string" },
            { case: { $isArray: "$value" },
              then: "array" }
          ],
          default: "other"
        }
      }
    }
  },
  { $group: { _id: "$state", count: { $sum: 1 } } },
  { $sort: { _id: 1 } }
]);
```

Nhánh `"array"` trong ví dụ gộp mảng rỗng và không rỗng; nếu cần tách tiếp, kiểm tra kích thước sau khi xác nhận giá trị là array.

## 8. Quy tắc schema và chỉ mục

MongoDB có thể chấp nhận kiểu hỗn hợp, nhưng ứng dụng thường hưởng lợi từ hợp đồng schema rõ ràng. Dùng validator `$jsonSchema` để quy định trường bắt buộc và kiểu hợp lệ. Ví dụ một object buộc có `tags` và yêu cầu đó là array:

```javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["tags"],
    properties: {
      tags: {
        bsonType: "array",
        items: { bsonType: "string" }
      }
    }
  }
}
```

Quy tắc trên **chấp nhận** `tags: []`; **không chấp nhận** field thiếu, `tags: null` hay `tags: ""`. Nếu nghiệp vụ cấm mảng rỗng, bổ sung `minItems: 1`. Nếu cho phép null tường minh nhưng bắt buộc khóa tồn tại, có thể dùng danh sách `bsonType` được phép, ví dụ `["array", "null"]`, kết hợp `required`. Validator cần được cấu hình vào collection khi tạo hoặc cập nhật cấu hình collection.

Đối với chỉ mục, truy vấn `$exists: true` có đặc điểm khác `$exists: false`; **sparse index** bỏ qua document thiếu trường nhưng vẫn có thể chứa document với giá trị null tường minh. Một **partial index** với điều kiện phù hợp có thể hữu ích cho truy vấn thường xuyên theo trạng thái hiện diện, nhưng phải xét bộ lọc truy vấn và chọn index thực tế. Đừng mặc định rằng điều kiện `$size: 0` sẽ được tăng tốc bởi chỉ mục của chính array. Hãy dùng `explain("executionStats")` trên dữ liệu và khối lượng thực tế trước khi tối ưu.

## 9. Kiểm thử những tình huống dễ nhầm

Khi viết integration test với MongoDB thật (hoặc môi trường test có hành vi tương đương), hãy tạo riêng các document cho từng trạng thái và kiểm tra cả kết quả lọc lẫn BSON được ghi:

| Tình huống | Kết quả cần kiểm tra |
|---|---|
| Query `is(null)` / `{value:null}` | Lấy cả missing và null tường minh |
| Query `type(10)` | Lấy null tường minh; nếu có mảng chứa null, cần kiểm tra thêm |
| Query `exists(false)` | Chỉ lấy missing |
| Query `is("")` | Có thể lấy cả chuỗi rỗng và array chứa `""` |
| Query `size(0)` | Chỉ lấy array rỗng |
| Ghi với `unset` | `Document.containsKey("value")` là `false` |
| Ghi với `set("value", null)` | Khóa tồn tại và giá trị là BSON null |
| Mapping POJO có thuộc tính `null` | Xác minh hành vi ghi theo annotation/converter đang dùng |
| DTO PATCH thiếu khóa so với khóa có `null` | Logic cập nhật thực hiện đúng hợp đồng API |

Một ca kiểm thử chỉ có các giá trị “không rỗng” sẽ không phát hiện được các lỗi này. Nên bổ sung cả mảng chứa chuỗi rỗng, số `0` và Boolean `false` để tránh nhầm “falsy” với missing.

## 10. Nguyên tắc áp dụng vào thiết kế

1. **Định nghĩa ý nghĩa dữ liệu** cho từng field: missing, null, empty string, empty array được phép khi nào và hệ thống phải phản ứng ra sao.
2. **Chọn điều kiện truy vấn khớp yêu cầu:** `$exists` để kiểm tra khóa; `$type: "null"` để tìm BSON null với lưu ý về phần tử mảng; `$size: 0` để tìm mảng rỗng; dùng `$expr` khi cần kiểm tra kiểu của toàn bộ field.
3. **Thống nhất thao tác ghi:** `$unset` xóa khóa, `$set: null` giữ khóa với null, `$set: ""` và `$set: []` ghi hai kiểu rỗng khác nhau.
4. **Kiểm tra ranh giới Java–BSON:** POJO, converter, annotation và DTO PATCH có thể làm mất thông tin hiện diện của khóa.
5. **Bảo vệ bằng kiểm thử và schema:** kiểm thử đủ bốn trạng thái, thêm validator và đo truy vấn thực tế khi cần.

Phân biệt chính xác bốn trạng thái ngay từ hợp đồng dữ liệu giúp các lớp repository, `MongoTemplate`, aggregation, index và API cập nhật thống nhất về ý nghĩa của dữ liệu.

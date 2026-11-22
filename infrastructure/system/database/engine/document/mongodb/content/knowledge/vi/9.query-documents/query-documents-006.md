# Kiểm tra trường bằng $exists, $type và truy vấn null trong MongoDB

## 1. Tại sao cần phân biệt trường thiếu, null và sai kiểu?

MongoDB lưu document bằng BSON và cho phép các document trong cùng collection có cấu trúc không hoàn toàn giống nhau. Một bản ghi người dùng có thể lưu email thành chuỗi, bản ghi khác có **email: null**, bản ghi cũ thiếu hẳn email, còn một lần import không đúng quy ước có thể đưa email thành Number hoặc Array. Các trường hợp này đòi hỏi cách truy vấn khác nhau.

~~~javascript
{ _id: "u01", email: "an@example.test" }
{ _id: "u02", email: null }
{ _id: "u03" }
{ _id: "u04", email: "" }
{ _id: "u05", email: [] }
~~~

| Document | Trạng thái của email | Điểm cần nhớ |
| --- | --- | --- |
| u01 | Trường tồn tại, String có nội dung | Có giá trị bình thường |
| u02 | Trường tồn tại, BSON Null | Null là một giá trị được lưu |
| u03 | **Không có trường email** | Field missing |
| u04 | Trường tồn tại, String rỗng | Không phải null hay missing |
| u05 | Trường tồn tại, Array rỗng | Có trường nhưng sai kiểu nếu ứng dụng yêu cầu String |

Trong nhóm **truy vấn document**, ba kỹ thuật chính giải quyết các câu hỏi khác nhau:

- **$exists:** Trường hoặc đường dẫn trường có tồn tại không?
- **$type:** Giá trị trong BSON thuộc kiểu nào, và toán tử đang xét cả field hay phần tử mảng?
- **Truy vấn null:** Muốn tìm field thiếu, field chứa null, hay những field tồn tại có giá trị khác null?

Sau bài này, bạn sẽ biết dùng các toán tử trên để lọc dữ liệu, phát hiện sai kiểu, kiểm kê trước migration và tránh các lỗi “truy vấn đúng cú pháp nhưng lấy sai document”.

> Các ví dụ chạy bằng **mongosh** trên database thực hành riêng **mongo_query_lab**. Những giá trị đặc biệt như String rỗng, NumberInt(0), Boolean false, Array rỗng và BSON Null được giữ riêng để thấy kết quả so sánh rõ ràng.

## 2. Ba trạng thái cơ bản của field

### 2.1. Field missing: không có khóa

~~~javascript
{ _id: "a01", profile: { name: "An" } }
~~~

Document trên **không có profile.email**, dù profile vẫn tồn tại. Field missing là trạng thái thiếu đường dẫn thuộc tính, khác với một thuộc tính đã được lưu bằng Null.

### 2.2. Explicit null: có khóa, giá trị BSON Null

~~~javascript
{ _id: "a02", profile: { email: null } }
~~~

Trong BSON, **Null** có mã type **10** và alias **"null"**. Đây là một giá trị thực sự được lưu trong document.

### 2.3. Có field nhưng giá trị rỗng hoặc sai kiểu

~~~javascript
{ flag: "" }       // String rỗng
{ flag: false }    // Boolean false
{ flag: 0 }        // Number
{ flag: [] }       // Array rỗng
{ flag: {} }       // Object rỗng
~~~

Tất cả ví dụ đều **có field flag**. Việc một giá trị là falsy theo JavaScript không làm MongoDB coi field đó là missing.

Một trường có thể có ba trạng thái nghiệp vụ có chủ đích: **không áp dụng** (missing), **có áp dụng nhưng chưa biết** (null) và **đã có giá trị**. Nếu ứng dụng cần phân biệt ba ý nghĩa này, không nên chuẩn hóa mọi trường hợp thành chuỗi rỗng.

## 3. Tạo bộ dữ liệu thực hành có thể chạy lại

Ta sử dụng collection **lab_field_checks** gồm 12 document có _id từ **d01** đến **d12**. Mọi document đều có **dataset: "field-checks-v1"** để truy vấn và dọn dữ liệu đúng phạm vi.

Chạy toàn bộ đoạn sau trong mongosh:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_query_lab");
  const c = lab.getCollection("lab_field_checks");
  const tag = "field-checks-v1";

  // Chỉ dọn dữ liệu của bài, không drop database hoặc collection.
  c.deleteMany({ dataset: tag });

  c.insertMany([
    {
      _id: "d01", dataset: tag,
      flag: "active",
      qty: NumberInt(3),
      profile: { email: "an@example.test" },
      tags: ["red", "blue"]
    },
    {
      _id: "d02", dataset: tag,
      flag: null,
      qty: NumberInt(0),
      profile: { email: null },
      tags: []
    },
    {
      _id: "d03", dataset: tag,
      // Không có flag hoặc qty.
      profile: {},
      tags: ["legacy"]
    },
    {
      _id: "d04", dataset: tag,
      flag: "",
      qty: null
      // Không có profile và tags.
    },
    {
      _id: "d05", dataset: tag,
      flag: false,
      qty: NumberLong(40),
      profile: { email: "" },
      tags: ["red", null]
    },
    {
      _id: "d06", dataset: tag,
      flag: NumberInt(0),
      qty: NumberDecimal("19.25"),
      profile: { email: NumberInt(123) },
      tags: [7]
    },
    {
      _id: "d07", dataset: tag,
      flag: [],
      qty: NumberDouble(3.5),
      profile: null
    },
    {
      _id: "d08", dataset: tag,
      flag: [null],
      qty: NumberInt(8),
      profile: { email: ["support@example.test", null] },
      tags: []
    },
    {
      _id: "d09", dataset: tag,
      flag: ["active", null],
      // Không có qty.
      profile: { email: ["team@example.test"] },
      tags: ["blue"]
    },
    {
      _id: "d10", dataset: tag,
      flag: ["active"],
      qty: true,
      profile: { email: "hello@example.test" },
      tags: ["red"]
    },
    {
      _id: "d11", dataset: tag,
      flag: {},
      qty: NumberInt(-5),
      profile: { email: ["list@example.test"] },
      tags: []
    },
    {
      _id: "d12", dataset: tag,
      flag: "pending",
      qty: NumberInt(10),
      profile: { name: "Chưa có email" },
      tags: ["legacy"]
    }
  ]);

  print("Số document: " + c.countDocuments({ dataset: tag }));
})();
~~~

**Kết quả mong đợi:** **12 document**. Script sử dụng ID cố định và dọn theo nhãn dataset, nên chạy lại trong môi trường thực hành riêng sẽ trả dữ liệu về trạng thái đầu. Việc dọn/chèn là nhiều lệnh riêng, không phải một transaction; không dùng cách này cho hệ thống production đang có ghi đồng thời.

### 3.1. Bảng trạng thái của flag

| ID | Giá trị flag | Kiểu của toàn field |
| --- | --- | --- |
| d01 | "active" | string |
| d02 | null | null |
| d03 | Missing | missing |
| d04 | "" | string |
| d05 | false | bool |
| d06 | NumberInt(0) | int |
| d07 | [] | array |
| d08 | [null] | array |
| d09 | ["active", null] | array |
| d10 | ["active"] | array |
| d11 | {} | object |
| d12 | "pending" | string |

Đặc biệt chú ý **d08–d10**: kiểu của toàn field là **array**, nhưng các phần tử nằm trong mảng có thể thuộc kiểu **null** hoặc **string**. Đây là nguồn gốc nhiều lỗi khi dùng **$type** trong find.

### 3.2. Hàm hiển thị ID khớp truy vấn

Để ví dụ gọn và dễ so sánh, định nghĩa một hàm trong phiên mongosh:

~~~javascript
function showMatchedIds(label, filter) {
  const c = db.getSiblingDB("mongo_query_lab")
    .getCollection("lab_field_checks");

  const ids = c.find(
      { $and: [{ dataset: "field-checks-v1" }, filter] },
      { _id: 1 }
    )
    .sort({ _id: 1 })
    .toArray()
    .map(doc => doc._id);

  print(label + ": " + JSON.stringify(ids));
  return ids;
}
~~~

Các ví dụ tiếp theo gọi hàm này. Nếu bạn mở phiên mongosh mới, chạy lại định nghĩa hàm trước khi gọi. Mọi bộ lọc vẫn có thể truyền trực tiếp vào **db.collection.find()**.

## 4. $exists: kiểm tra field có tồn tại

### 4.1. $exists: true

Cú pháp:

~~~javascript
{ fieldName: { $exists: true } }
~~~

MongoDB trả document có field chỉ định, **kể cả khi giá trị của field là null, false, 0, chuỗi rỗng, array rỗng hoặc object rỗng**.

~~~javascript
showMatchedIds(
  "Có flag",
  { flag: { $exists: true } }
);
~~~

**Kết quả mong đợi:** **d01, d02, d04, d05, d06, d07, d08, d09, d10, d11, d12** — tổng cộng **11**. Document **d02** có flag null vẫn khớp; chỉ d03 không khớp.

### 4.2. $exists: false

~~~javascript
showMatchedIds(
  "Thiếu flag",
  { flag: { $exists: false } }
);
~~~

**Kết quả mong đợi:** chỉ **d03**. Bộ lọc này không tìm những field được lưu bằng Null.

Phân biệt rõ:

~~~javascript
{ flag: { $exists: false } }  // Không có khóa flag.
{ flag: { $exists: true } }   // Có khóa flag, kể cả null.
~~~

Một lỗi thường gặp là dùng **$exists: false** để tìm mọi trường chưa có giá trị nghiệp vụ; nó không bao gồm explicit null hoặc chuỗi rỗng.

### 4.3. Kiểm tra đường dẫn lồng nhau bằng dot notation

~~~javascript
showMatchedIds(
  "Có profile.email",
  { "profile.email": { $exists: true } }
);

showMatchedIds(
  "Thiếu profile.email",
  { "profile.email": { $exists: false } }
);
~~~

Kết quả dự kiến:

- **Có profile.email:** d01, d02, d05, d06, d08, d09, d10, d11.
- **Thiếu profile.email:** d03, d04, d07, d12.

Document d03 có profile là object rỗng nhưng không có email. Document d04 không có profile; d07 có profile bằng null; d12 có profile.name nhưng không có profile.email.

Nếu chỉ kiểm tra **profile** thay vì **profile.email**:

~~~javascript
showMatchedIds(
  "Không có profile",
  { profile: { $exists: false } }
);
// d04.
~~~

**Parent tồn tại không chứng minh child tồn tại.** Với document lồng nhau, phải kiểm tra đúng đường dẫn cần sử dụng.

### 4.4. $exists không phải SQL EXISTS

Trong MongoDB, **$exists** là query predicate trên một field. Nó không chạy truy vấn con và không tương đương toán tử **EXISTS(subquery)** của SQL.

~~~javascript
{ profile: { $exists: true } }
~~~

chỉ hỏi collection hiện tại có field profile trong mỗi document hay không.

## 5. Truy vấn null: field thiếu có thể cùng khớp

### 5.1. Bộ lọc bằng null

~~~javascript
showMatchedIds(
  "flag bằng null",
  { flag: null }
);
~~~

**Kết quả mong đợi:** **d02, d03, d08, d09**.

| ID | Lý do khớp |
| --- | --- |
| d02 | flag hiện diện và bằng BSON Null |
| d03 | Không có field flag |
| d08 | flag là array chứa phần tử null |
| d09 | flag là array chứa String và null |

Bộ lọc equality **{ flag: null }** khớp trường có giá trị Null **hoặc field missing**. Với trường Array, phép so sánh scalar còn có thể khớp một phần tử null trong mảng.

Cách viết **{ flag: { $eq: null } }** diễn đạt cùng mục đích equality.

### 5.2. Kết hợp null với $exists: true

~~~javascript
showMatchedIds(
  "flag tồn tại và bằng null",
  { flag: { $exists: true, $eq: null } }
);
~~~

**Kết quả mong đợi:** **d02, d08, d09**. Điều kiện $exists: true loại **d03** nhưng **không loại array chứa null**.

Đây là điểm cần nhớ: điều kiện **field tồn tại và khớp null** chưa đủ để bảo đảm **toàn field là scalar BSON Null**.

### 5.3. Dùng $type: "null"

~~~javascript
showMatchedIds(
  "flag có kiểu Null theo query predicate",
  { flag: { $type: "null" } }
);
~~~

**Kết quả mong đợi:** **d02, d08, d09**.

**$type: "null"** và **$type: 10** cùng chỉ BSON Null. Trong find, $type còn xét **phần tử Array**; vì thế d08 và d09 cũng khớp.

Nếu dữ liệu của một field được bảo đảm không bao giờ là Array, $type: "null" thường đủ để tìm explicit null. Nếu dữ liệu có thể chứa Array, cần dùng kỹ thuật ở mục 7 để kiểm tra **kiểu của toàn field**.

### 5.4. Dùng $ne: null

~~~javascript
showMatchedIds(
  "flag khác null",
  { flag: { $ne: null } }
);
~~~

**Kết quả mong đợi:** **d01, d04, d05, d06, d07, d10, d11, d12** — tổng cộng **8**.

Theo query semantics của MongoDB, **$ne: null** tìm field **hiện diện và không khớp null**. Mảng chứa null cũng bị loại khi so sánh scalar null. Các giá trị String rỗng, false, 0, Array rỗng, Object rỗng vẫn khác null.

Đừng suy ra **$ne: null** là “giá trị đã hợp lệ”: nếu nghiệp vụ đòi chuỗi có nội dung, d04 vẫn chưa đáp ứng; nếu nghiệp vụ đòi scalar String, d05–d07, d10–d11 cũng chưa đáp ứng.

**Lưu ý khác biệt:** Với giá trị thông thường, ví dụ **{ flag: { $ne: "active" } }**, toán tử $ne còn có thể khớp document thiếu field. Cần ghi nhớ hành vi đặc biệt được MongoDB mô tả cho **$ne: null**.

### 5.5. Bảng so sánh

| Điều kiện lọc flag | Ý nghĩa | ID khớp |
| --- | --- | --- |
| **{ flag: { $exists: false } }** | Field missing | d03 |
| **{ flag: { $exists: true } }** | Có field | Tất cả trừ d03 |
| **{ flag: null }** | Null, missing hoặc mảng chứa null | d02, d03, d08, d09 |
| **{ flag: { $type: "null" } }** | Có giá trị null hoặc phần tử mảng null | d02, d08, d09 |
| **{ flag: { $ne: null } }** | Trường hiện diện, khác null | d01, d04–d07, d10–d12 |

Các bộ lọc trên giải quyết mục đích khác nhau. Hãy diễn đạt yêu cầu nghiệp vụ trước khi chọn toán tử.

## 6. $type: kiểm tra kiểu BSON

### 6.1. Cú pháp

~~~javascript
{ field: { $type: "string" } }
{ field: { $type: 2 } }
{ field: { $type: ["int", "long", "decimal", "double"] } }
~~~

Hai bộ lọc đầu cùng tìm BSON String. Với mảng các alias, MongoDB tìm field thuộc **ít nhất một kiểu được liệt kê**; hành vi với trường là Array được nêu ở mục 6.3.

| BSON type | Alias | Mã |
| --- | --- | ---: |
| Double | "double" | 1 |
| String | "string" | 2 |
| Object | "object" | 3 |
| Array | "array" | 4 |
| Binary | "binData" | 5 |
| ObjectId | "objectId" | 7 |
| Boolean | "bool" | 8 |
| Date | "date" | 9 |
| Null | "null" | 10 |
| Int32 | "int" | 16 |
| Int64 | "long" | 18 |
| Decimal128 | "decimal" | 19 |

Alias đặc biệt **"number"** chấp nhận nhóm BSON numeric: int, long, double và decimal. Nó không bao gồm Boolean hoặc chuỗi chứa chữ số.

### 6.2. Thực hành kiểm tra trường qty

~~~javascript
showMatchedIds(
  "qty Int32",
  { qty: { $type: "int" } }
);

showMatchedIds(
  "qty Decimal128",
  { qty: { $type: "decimal" } }
);

showMatchedIds(
  "qty thuộc nhóm number",
  { qty: { $type: "number" } }
);
~~~

| Kiểu qty | ID khớp |
| --- | --- |
| int | d01, d02, d08, d11, d12 |
| long | d05 |
| double | d07 |
| decimal | d06 |
| number | d01, d02, d05, d06, d07, d08, d11, d12 |
| bool | d10 |
| null | d04 |
| missing | d03, d09 (dùng $exists: false hoặc aggregation $type) |

Trong schema thực tế, **Decimal128**, **Double**, **Int32**, **Int64** đều có đặc tính lưu trữ khác nhau. Nếu trường tiền tệ phải là Decimal128, không nên chấp nhận một giá trị Double chỉ vì số hiển thị tương tự.

### 6.3. Hành vi đặc biệt khi field là Array

Toán tử **$type dùng trong query predicate** có thể khớp khi **một phần tử Array** thuộc kiểu cần tìm:

~~~javascript
showMatchedIds(
  "flag là String hoặc Array chứa String",
  { flag: { $type: "string" } }
);

showMatchedIds(
  "flag là Array",
  { flag: { $type: "array" } }
);
~~~

Kết quả:

- **$type: "string"** → **d01, d04, d09, d10, d12**.
- **$type: "array"** → **d07, d08, d09, d10**.

**d09 và d10 không phải scalar String**; chúng là Array chứa String. Nếu schema yêu cầu field flag phải là **một String ở cấp field**, bộ lọc **{ flag: { $type: "string" } }** một mình là chưa đủ để xác nhận hợp lệ.

### 6.4. $type query predicate và $type aggregation expression

MongoDB có **hai ngữ cảnh dùng $type**:

| Ngữ cảnh | Ví dụ | Hành vi |
| --- | --- | --- |
| Query predicate trong find | **{ flag: { $type: "string" } }** | Có thể khớp array chứa phần tử String |
| Query predicate trong find | **{ flag: { $type: "array" } }** | Khớp field có kiểu Array |
| Aggregation expression | **{ $type: "$flag" }** | Trả alias kiểu của **toàn field** |
| Aggregation expression trên field thiếu | **{ $type: "$missingField" }** | Trả chuỗi **"missing"** |
| Aggregation expression trên Array | **{ $type: "$flag" }** | Trả chuỗi **"array"**, không duyệt từng phần tử |

Do đó, **"missing" không phải một BSON type hợp lệ cho $type query predicate**. Trong find, muốn tìm field thiếu dùng **$exists: false**; trong biểu thức aggregation có thể so sánh kết quả **$type** với chuỗi **"missing"**.

## 7. Phân biệt chính xác scalar null, String và missing

### 7.1. Dùng $expr và aggregation $type trong find

Muốn kiểm tra **kiểu của toàn field**, thay vì kiểu phần tử Array, dùng **$expr** với aggregation expression:

~~~javascript
showMatchedIds(
  "Chỉ scalar BSON Null",
  { $expr: { $eq: [{ $type: "$flag" }, "null"] } }
);
// d02.

showMatchedIds(
  "Chỉ scalar BSON String",
  { $expr: { $eq: [{ $type: "$flag" }, "string"] } }
);
// d01, d04, d12.

showMatchedIds(
  "Field missing bằng $type expression",
  { $expr: { $eq: [{ $type: "$flag" }, "missing"] } }
);
// d03.
~~~

Với **d08/d09**, kiểu toàn field là **array**, vì vậy không khớp điều kiện scalar Null dù các mảng chứa phần tử null. Với **d09/d10**, kiểu toàn field là array, không khớp scalar String dù chứa phần tử String.

### 7.2. Xem kiểu từng document bằng aggregation

~~~javascript
db.getSiblingDB("mongo_query_lab")
  .getCollection("lab_field_checks")
  .aggregate([
    { $match: { dataset: "field-checks-v1" } },
    {
      $project: {
        _id: 1,
        flagType: { $type: "$flag" },
        qtyType: { $type: "$qty" },
        emailType: { $type: "$profile.email" }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

Một số trường hợp đáng chú ý:

| ID | flagType | qtyType | emailType |
| --- | --- | --- | --- |
| d01 | string | int | string |
| d02 | null | int | null |
| d03 | missing | missing | missing |
| d04 | string | null | missing |
| d06 | int | decimal | int |
| d07 | array | double | missing |
| d08 | array | int | array |
| d09 | array | missing | array |
| d10 | array | bool | string |
| d11 | object | int | array |

Aggregation **$type** đặc biệt hữu ích khi kiểm kê schema trước khi áp đặt chuẩn mới, vì nó cho thấy kiểu của cả field thay vì chỉ kiểm tra một phần tử trong mảng.

### 7.3. Thống kê phân bố BSON type

~~~javascript
db.getSiblingDB("mongo_query_lab")
  .getCollection("lab_field_checks")
  .aggregate([
    { $match: { dataset: "field-checks-v1" } },
    {
      $group: {
        _id: { $type: "$flag" },
        count: { $sum: 1 }
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

Kết quả:

| Kiểu của flag | Số document |
| --- | ---: |
| array | 4 |
| bool | 1 |
| int | 1 |
| missing | 1 |
| null | 1 |
| object | 1 |
| string | 3 |
| **Tổng** | **12** |

Đây là kiểu báo cáo hữu ích để trả lời câu hỏi: “Bao nhiêu document đang lưu giá thành String, Double hay Decimal128?” hoặc “Schema mới sẽ ảnh hưởng bao nhiêu document legacy?”.

### 7.4. Tìm profile.email là scalar String có nội dung

Theo bảng dữ liệu, **profile.email** của d01, d05 và d10 là String scalar. Trong đó d05 là chuỗi rỗng. Ta dùng aggregation expression kiểm tra đồng thời **kiểu là string** và **giá trị khác chuỗi rỗng**:

~~~javascript
db.getSiblingDB("mongo_query_lab")
  .getCollection("lab_field_checks")
  .aggregate([
    { $match: { dataset: "field-checks-v1" } },
    {
      $match: {
        $expr: {
          $and: [
            { $eq: [{ $type: "$profile.email" }, "string"] },
            { $ne: ["$profile.email", ""] }
          ]
        }
      }
    },
    { $project: { _id: 1, "profile.email": 1 } },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

**Kết quả mong đợi:** **d01, d10**. Ở đây **$ne** trong **$expr** là aggregation expression dạng **mảng hai biểu thức**; nó khác cú pháp predicate **{ field: { $ne: value } }**.

Phép kiểm tra trên mới khẳng định field là String scalar không rỗng, **chưa bảo đảm email hợp lệ theo chính sách nghiệp vụ**. Muốn xác thực email cần thêm ràng buộc phù hợp ở tầng ứng dụng/schema.

## 8. Kết hợp các toán tử khi làm sạch dữ liệu cũ

### 8.1. Phân loại missing trước migration

~~~javascript
db.getSiblingDB("mongo_query_lab")
  .getCollection("lab_field_checks")
  .find(
    {
      dataset: "field-checks-v1",
      "profile.email": { $exists: false }
    },
    { _id: 1, profile: 1 }
  )
  .sort({ _id: 1 })
  .toArray();
~~~

Kết quả: **d03, d04, d07, d12**. Cần phân tích vì sao email thiếu trước khi bổ sung: khách thực sự không cung cấp, dữ liệu nhập thiếu, hoặc thông tin đã được ẩn danh. Không tự phát sinh một địa chỉ giả nếu ứng dụng sẽ dùng email để liên hệ.

### 8.2. Phát hiện kiểu không phù hợp

Giả sử schema mới yêu cầu **flag chỉ được phép là scalar String hoặc scalar Null**; missing được chấp nhận trong giai đoạn chuyển đổi. Dùng aggregation phân loại type:

~~~javascript
db.getSiblingDB("mongo_query_lab")
  .getCollection("lab_field_checks")
  .aggregate([
    { $match: { dataset: "field-checks-v1" } },
    { $addFields: { flagType: { $type: "$flag" } } },
    {
      $match: {
        flagType: { $nin: ["string", "null", "missing"] }
      }
    },
    { $project: { _id: 1, flag: 1, flagType: 1 } },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

**Kết quả mong đợi:** d05, d06, d07, d08, d09, d10, d11. Những document này chứa Boolean, Number, Array hoặc Object. Nếu schema mới bắt buộc một String, còn phải xử lý thêm d02 (null), d03 (missing) và d04 (String rỗng) tùy quy tắc nghiệp vụ.

### 8.3. Thay null bằng giá trị có căn cứ

Giả sử đã xác minh từ một nguồn nghiệp vụ rằng trạng thái đúng của d02 phải là **pending**:

~~~javascript
db.getSiblingDB("mongo_query_lab")
  .getCollection("lab_field_checks")
  .updateOne(
    {
      _id: "d02",
      dataset: "field-checks-v1",
      flag: { $type: "null" }
    },
    { $set: { flag: "pending" } }
  );
~~~

Phép cập nhật chọn rõ _id và trạng thái giá trị trước khi sửa. Nhưng nếu không có bằng chứng rằng flag phải là pending, **không được tự đặt mặc định** chỉ để document qua validation.

### 8.4. $set null và $unset tạo hai trạng thái khác nhau

~~~javascript
const c = db.getSiblingDB("mongo_query_lab")
  .getCollection("lab_field_checks");

c.updateOne(
  { _id: "d01", dataset: "field-checks-v1" },
  { $set: { flag: null } }
);

c.updateOne(
  { _id: "d02", dataset: "field-checks-v1" },
  { $unset: { flag: "" } }
);
~~~

Sau đó:

- d01 vẫn **có flag** nhưng bằng Null → **$exists: true**.
- d02 **không còn field flag** → **$exists: false**.
- Cả hai có thể khớp **{ flag: null }**, dù ngữ nghĩa lưu trữ khác nhau.

Chạy lại seed ở mục 3 sau khi thực hành để trả dữ liệu về trạng thái ban đầu.

## 9. Các trường hợp đặc biệt cần nhớ

### 9.1. $exists không dùng trực tiếp trong $expr

Trong aggregation, bạn có thể lọc document bằng:

~~~javascript
{ $match: { flag: { $exists: false } } }
~~~

Tuy nhiên **$exists** là query predicate, không phải một aggregation expression đặt tùy ý trong **$expr** hay **$project**. Nếu cần kiểm tra missing bằng biểu thức, dùng:

~~~javascript
{
  $eq: [
    { $type: "$flag" },
    "missing"
  ]
}
~~~

### 9.2. Array và scalar không có cùng ý nghĩa

Ví dụ:

~~~javascript
{ flag: "active" }
{ flag: ["active"] }
~~~

Hai document có cấu trúc khác nhau. Query **{ flag: "active" }** có thể khớp cả hai vì so sánh scalar có thể khớp phần tử Array. Nếu hợp đồng schema đòi một String ở cấp field, cần kiểm tra loại của toàn field hoặc áp dụng MongoDB **$jsonSchema** thích hợp.

### 9.3. Dữ liệu BSON Undefined cũ

BSON có kiểu **Undefined** đã bị khuyến nghị ngừng sử dụng. Kể từ **MongoDB 8.0**, phép equality với null không còn tự khớp giá trị BSON Undefined như trong các phiên bản cũ. Không nên đồng nhất:

- JavaScript undefined trong biến ứng dụng.
- Trường hoàn toàn không tồn tại.
- Trường lưu BSON Null.
- Trường lưu BSON Undefined từ dữ liệu cũ.

Khi kiểm tra một collection lịch sử, xác minh phiên bản MongoDB và kiểu BSON thực tế trước khi viết migration. Việc dùng **undefined** làm giá trị dữ liệu mới chỉ làm quy ước khó đoán hơn.

### 9.4. BSON Number cần quy ước rõ

MongoDB phân biệt Int32, Int64, Double và Decimal128. Trường qty của lab cố tình chứa cả bốn để minh họa. Khi cần đối chiếu một field tiền tệ có đúng Decimal128, hãy dùng bộ lọc hoặc schema theo đúng BSON type; nếu dữ liệu nhập về là String, trước khi chuyển đổi phải kiểm tra định dạng, độ chính xác, dấu thập phân và trường hợp không thể parse.

### 9.5. Null không thay thế điều kiện nghiệp vụ

Trường email có type String chưa chắc là email hợp lệ; trường amount có type Decimal128 chưa chắc là số tiền đúng; status có String chưa chắc thuộc tập trạng thái cho phép. **$exists** và **$type** giúp kiểm tra cấu trúc, còn validation nghiệp vụ và phân quyền phải được thiết kế riêng.

## 10. Chỉ mục và hiệu năng cho truy vấn tồn tại

Truy vấn **$exists** thường xuất hiện khi kiểm kê document legacy, đo độ đầy đủ của dữ liệu hoặc hỗ trợ migration. Với collection lớn, hiệu năng phụ thuộc index, phân bố dữ liệu và độ chọn lọc.

### 10.1. Sparse index cho field có thể thiếu

~~~javascript
db.getSiblingDB("mongo_query_lab")
  .getCollection("lab_field_checks")
  .createIndex(
    { "profile.email": 1 },
    { name: "ix_email_sparse_lab", sparse: true }
  );
~~~

**Sparse index** chỉ có entry cho document có field được index, **bao gồm document có field bằng null** và bỏ qua document thiếu field. Do vậy, nó có thể hữu ích cho query **{ "profile.email": { $exists: true } }** khi phù hợp với kế hoạch thực thi.

Ngược lại, sparse index **không có entry cho document thiếu field**, nên không thể dùng riêng index ấy để trả về đầy đủ kết quả **$exists: false**. Truy vấn cần dữ liệu missing có thể phải quét collection. Dùng **hint** ép sparse index khi cần document thiếu trường có thể khiến kết quả không đầy đủ.

### 10.2. Partial index và index thường

**Partial index** có thể chứa chỉ những document khớp điều kiện lọc được chỉ định; nó hữu ích khi truy vấn thường chỉ áp dụng cho một tập con. Tuy nhiên MongoDB chỉ dùng partial index khi có thể bảo đảm trả đủ kết quả theo predicate truy vấn.

Index thường (không sparse) có thể chứa entry cho document thiếu field và explicit null theo cách biểu diễn khóa index, nên bộ máy truy vấn có thể cần đọc document (**FETCH**) để phân biệt. Không nên hứa rằng mọi điều kiện **$exists:true/false** đều được giải quyết chỉ bằng một index.

### 10.3. Quan sát explain

~~~javascript
db.getSiblingDB("mongo_query_lab")
  .getCollection("lab_field_checks")
  .find({
    dataset: "field-checks-v1",
    "profile.email": { $exists: true }
  })
  .explain("executionStats");
~~~

Đọc **winningPlan**, **totalKeysExamined**, **totalDocsExamined**, **nReturned**. Với 12 document, MongoDB có thể chọn **COLLSCAN** dù có index; điều đó không tự chứng minh index sai. Cần đánh giá trên tải và kích thước dữ liệu đại diện, kể cả chi phí duy trì index ở các thao tác ghi.

## 11. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| **{ field: null }** trả cả document không có field | Equality null khớp null hoặc missing | Dùng $exists: false để tìm missing hoặc $type expression kiểm tra scalar Null |
| **$exists: true** trả document có null, 0, false, "" | $exists chỉ kiểm tra sự hiện diện | Bổ sung điều kiện kiểu và giá trị |
| **$type: "string"** trả document có Array | $type query có thể khớp phần tử Array | Dùng $expr + aggregation $type nếu cần scalar String |
| **$type: "null"** trả Array chứa null | Array có phần tử BSON Null | Dùng aggregation $type kiểm tra toàn field |
| **$ne: null** trả String rỗng hoặc 0 | Rỗng/0 không phải BSON Null | Cần thêm validation nghiệp vụ |
| Truy vấn đường dẫn profile.email không có dữ liệu | Parent có thể tồn tại nhưng child thiếu | Kiểm tra riêng profile và profile.email |
| Dùng **$type: "missing"** trong find bị lỗi | "missing" không phải một BSON type query | Dùng $exists: false hoặc aggregation $type |
| Dùng $exists trong $expr bị lỗi | $exists không phải aggregation expression | Dùng { $type: "$field" } để phát hiện "missing" |
| Giá/điểm được lưu cả String và Decimal128 | Writer không thống nhất kiểu BSON | Thống kê kiểu, lập migration và schema validation |
| Sparse index không giúp tìm missing | Index bỏ qua document thiếu field | Đọc explain và chọn access pattern/index phù hợp |
| Kết quả ID khác ví dụ | Dữ liệu đã bị sửa hoặc kết nối sai database | Chạy lại seed và kiểm tra database, collection, dataset |

## 12. Bài tập thực hành

### Bài 1 — Phân biệt field missing và null

Viết truy vấn tìm: document thiếu flag; document có flag; document flag là scalar Null; document flag có kiểu khác null; document flag bằng Array rỗng. Ghi lại tập _id và giải thích vì sao **d02** khác **d03**.

### Bài 2 — Dự đoán bốn truy vấn

Chạy:

~~~javascript
showMatchedIds("A", { flag: null });
showMatchedIds("B", { flag: { $exists: false } });
showMatchedIds("C", { flag: { $type: "null" } });
showMatchedIds("D", { flag: { $ne: null } });
~~~

Tự giải thích vì sao d08/d09 khớp A/C nhưng không khớp B/D; và vì sao d03 khớp A/B.

### Bài 3 — Kiểm tra kiểu số

Tìm từng nhóm document có qty là **Int32**, **Int64**, **Double**, **Decimal128**, **Boolean**, **Null** hoặc **missing**. Dùng alias **"number"** rồi đối chiếu với tổng số document numeric. Vì sao d10 có qty = true mà không được tính là số?

### Bài 4 — Truy vấn embedded document

Viết truy vấn tìm: document không có profile; có profile nhưng không có profile.email; profile.email là scalar String; profile.email là scalar String không rỗng; profile.email là scalar Null; profile.email là Array. So sánh **$type query predicate** với **$type aggregation** trên trường email.

### Bài 5 — Thay đổi ý nghĩa bằng update

Sử dụng **$set: { flag: null }** trên d01 và **$unset: { flag: "" }** trên d02. Dùng **$exists**, **{ flag: null }** và **$type** để quan sát sự khác nhau. Chạy lại script seed trước bài sau.

### Bài 6 — Lập kế hoạch sửa dữ liệu sai kiểu

Giả sử yêu cầu **qty là Int32 không âm**. Lập bảng các document hiện tại thuộc nhóm missing, null, sai kiểu hoặc số âm. Nêu rõ trường hợp nào có thể chuyển đổi an toàn khi có căn cứ, trường hợp nào phải lấy lại dữ liệu từ nguồn nghiệp vụ. Không ép Double/Decimal128 về Int32 tùy tiện làm mất số thập phân.

### Bài 7 — Phân tích hiệu năng

Tạo sparse index trên profile.email, dùng **explain("executionStats")** cho **$exists: true** và **$exists: false**. Giải thích vì sao index chỉ chứa document có field không thể thay thế việc đọc những document thiếu field.

## 13. Tham khảo chính thức

- MongoDB Manual — [Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/).
- MongoDB Manual — [$exists Query Predicate](https://www.mongodb.com/docs/manual/reference/operator/query/exists/).
- MongoDB Manual — [$type Query Predicate](https://www.mongodb.com/docs/manual/reference/operator/query/type/).
- MongoDB Manual — [$type Aggregation Expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/type/).
- MongoDB Manual — [BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/).
- MongoDB Manual — [Sparse Indexes](https://www.mongodb.com/docs/manual/core/index-sparse/).
- MongoDB Manual — [Migrate Undefined Data and Queries](https://www.mongodb.com/docs/manual/reference/bson-types/migrate-undefined/).

Điểm cốt lõi khi kiểm tra một field là **nói rõ muốn kiểm tra sự tồn tại, null, kiểu BSON hay tính hợp lệ nghiệp vụ**. **$exists** kiểm tra khóa; **$type query** có thể khớp phần tử trong mảng; **$type aggregation** cho biết kiểu của toàn giá trị và nhãn **missing**; còn **{ field: null }** có thể khớp cả field thiếu hoặc mảng chứa null. Chọn đúng cách truy vấn giúp việc đọc, sửa và chuyển đổi dữ liệu MongoDB an toàn và nhất quán hơn.

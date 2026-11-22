# Nullability, giá trị mặc định và trường không tồn tại

> **Chương:** Kiểu dữ liệu  
> **Module:** `SPRING_DATA_MONGODB` — sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác dữ liệu qua `MongoTemplate` hoặc repository.  
> **Mục tiêu:** Phân biệt BSON `null`, trường không tồn tại và giá trị rỗng; viết đúng bộ lọc; hiểu cách Spring Data MongoDB đọc/ghi `null`; đặt giá trị mặc định ở đúng tầng; xử lý cập nhật, index, validation và dữ liệu cũ nhất quán.

## 1. Một trường MongoDB có thể ở nhiều trạng thái khác nhau

MongoDB lưu dữ liệu dưới dạng document BSON. Không giống một bảng có các cột cố định, mỗi document trong một collection có thể có tập trường khác nhau. Với trường `note`, cần phân biệt ít nhất ba trạng thái:

1. **Có trường, giá trị BSON `null`:** `{ note: null }`.
2. **Không tồn tại trường:** `{ }` (không có khóa `note`).
3. **Có trường, chứa giá trị cụ thể:** `{ note: "" }`, `{ note: "x" }`, `{ note: 0 }`, `{ note: false }` hay `{ note: [] }`.

Trong Java, hai document thứ nhất và thứ hai có thể đều trở thành `String note == null` khi được ánh xạ vào một thuộc tính `String` thông thường. Vì vậy **đối tượng Java chỉ mang giá trị null chưa đủ để xác định trường BSON gốc có thực sự tồn tại hay không**.

### 1.1. Bảng phân biệt trạng thái

| Dữ liệu BSON | Trường hiện diện? | Có phải BSON null? | Có phải giá trị rỗng/không? |
| --- | --- | --- | --- |
| `{ note: null }` | Có | Có | Không phải chuỗi rỗng |
| `{ }` | Không | Không có giá trị để kiểm tra | Không có trường |
| `{ note: "" }` | Có | Không | Chuỗi rỗng |
| `{ retryCount: 0 }` | Có | Không | Số 0 hợp lệ |
| `{ active: false }` | Có | Không | Boolean false hợp lệ |
| `{ tags: [] }` | Có | Không | Mảng rỗng |
| `{ settings: {} }` | Có | Không | Document con rỗng |

Giá trị `0`, `false`, `""` và `[]` đều mang thông tin có thể quan trọng trong nghiệp vụ; không nên gom tất cả thành “không có dữ liệu”.

### 1.2. Nạp dữ liệu thử nghiệm

Thực hành trên database riêng qua `mongosh`:

~~~javascript
use spring_data_mongodb_lab

const workitems = db.workitems_null_demo_008;

// Chỉ chạy trên collection thử nghiệm đang trống.
workitems.insertMany([
  {
    _id: "w001",
    title: "Đăng ký",
    note: null,
    active: false,
    retryCount: 0,
    tags: [],
    status: "NEW"
  },
  {
    _id: "w002",
    title: "Chờ xử lý",
    active: true,
    status: "NEW"
    // Không có note, retryCount và tags.
  },
  {
    _id: "w003",
    title: "Hoàn thành",
    note: "Đã duyệt",
    active: true,
    retryCount: 2,
    tags: ["urgent"],
    status: "DONE"
  },
  {
    _id: "w004",
    title: "Để trống ghi chú",
    note: "",
    active: false,
    retryCount: 0,
    tags: [],
    status: null
  }
]);
~~~

Bốn document dùng `_id` cố định để dễ đối chiếu kết quả. Nếu chạy lại `insertMany`, bạn sẽ gặp lỗi trùng `_id`; chỉ làm mới collection thử nghiệm do mình sở hữu. Các câu truy vấn trong mục tiếp theo giả định dữ liệu **chưa bị sửa** bởi các ví dụ cập nhật ở mục sau.

## 2. Truy vấn `null`, missing và giá trị có mặt

### 2.1. `{ field: null }` bao gồm cả trường không tồn tại

~~~javascript
// Kết quả: w001 (note:null) và w002 (không có note).
workitems.find({ note: null });
~~~

Đây là điểm khác biệt quan trọng: phép so sánh `{ note: null }` ở MongoDB tìm **hai trường hợp**, gồm trường hiện diện với BSON null và trường thiếu. Nếu nghiệp vụ muốn “ghi chú đã được đặt rõ ràng thành null” thì bộ lọc này quá rộng.

### 2.2. Chỉ tìm BSON null bằng `$type`

~~~javascript
// Kết quả: chỉ w001.
workitems.find({ note: { $type: "null" } });

// Tương đương khi dùng mã BSON type Null = 10.
workitems.find({ note: { $type: 10 } });
~~~

`$type: "null"` chỉ khớp giá trị BSON null của trường đang xét. Ví dụ ở đây `note` là trường scalar; với trường mảng, toán tử `$type` trong query còn có quy tắc khớp phần tử mảng, cần kiểm tra riêng nếu mô hình cho phép mảng chứa `null`.

### 2.3. Chỉ tìm trường thiếu bằng `$exists: false`

~~~javascript
// Kết quả: chỉ w002.
workitems.find({ note: { $exists: false } });

// Kết quả: w001, w003, w004; bao gồm note:null.
workitems.find({ note: { $exists: true } });
~~~

`$exists` hỏi **khóa có xuất hiện hay không**; nó không hỏi giá trị có khác null hay không. `$exists: true` bao gồm BSON null, chuỗi rỗng và các giá trị khác.

### 2.4. Chỉ tìm trường có giá trị khác null

~~~javascript
// Kết quả: w003 và w004.
workitems.find({ note: { $ne: null } });
~~~

Với phép so sánh đặc biệt `$ne: null`, MongoDB chọn document mà trường tồn tại và **không bằng null**. Do đó chuỗi rỗng `""` ở `w004` vẫn được chọn. Với các giá trị khác `null`, `$ne` nói chung có thể khớp cả document không có trường; đừng suy rộng quy tắc của `$ne: null` sang mọi `$ne`.

### 2.5. Chỉ tìm chuỗi rỗng

~~~javascript
// Kết quả: chỉ w004.
workitems.find({ note: "" });
~~~

Một chuỗi rỗng không đồng nghĩa với BSON null, dù nhiều biểu mẫu giao diện có thể hiển thị cả hai dưới dạng ô trắng.

### 2.6. Bảng đối chiếu truy vấn trên dữ liệu mẫu

| Bộ lọc | Kết quả `_id` | Ý nghĩa |
| --- | --- | --- |
| `{ note: null }` | w001, w002 | BSON null **hoặc** missing |
| `{ note: { $type: "null" } }` | w001 | BSON null |
| `{ note: { $exists: false } }` | w002 | Không có khóa |
| `{ note: { $exists: true } }` | w001, w003, w004 | Có khóa, kể cả null |
| `{ note: { $ne: null } }` | w003, w004 | Có giá trị khác null |
| `{ note: "" }` | w004 | Chuỗi rỗng |
| `{ active: false }` | w001, w004 | Boolean false |
| `{ retryCount: 0 }` | w001, w004 | Số 0 |
| `{ tags: [] }` | w001, w004 | Mảng rỗng |

**Tự kiểm chứng:** chạy `countDocuments(filter)` với cùng bộ lọc và quan sát kết quả. Nếu số lượng khác bảng, collection đã bị thay đổi bởi các ví dụ ghi hoặc có thêm dữ liệu.

## 3. Sửa trường thành `null` và xóa hẳn trường là hai thao tác khác nhau

MongoDB không xem `$set: { field: null }` và `$unset: { field: "" }` là tương đương.

~~~javascript
// Trước thao tác: w002 không có note.
workitems.updateOne(
  { _id: "w002" },
  { $set: { note: null } }
);
// Sau thao tác: w002 có trường note, giá trị BSON null.

// Xóa hẳn khóa note ra khỏi document.
workitems.updateOne(
  { _id: "w002" },
  { $unset: { note: "" } }
);
// Sau thao tác: w002 lại không có note.
~~~

Hai lệnh trên chạy liên tiếp sẽ đưa `w002` về trạng thái ban đầu. `$unset` không thể hiện “đặt một giá trị bằng null”; nó loại trường khỏi document. Khi thực hiện `updateOne()`, hãy đọc `matchedCount` và `modifiedCount` để phân biệt không tìm thấy document với thao tác không làm thay đổi dữ liệu.

### 3.1. Tác động đến nghiệp vụ

Giả sử `note` thể hiện lý do từ chối:

- **Missing:** hệ thống cũ chưa có tính năng ghi lý do, hoặc người dùng chưa từng được hỏi.
- **BSON null:** người dùng hoặc workflow đã xác nhận không có lý do.
- **Chuỗi rỗng:** người dùng gửi văn bản rỗng; có thể bị coi là dữ liệu không hợp lệ.
- **Chuỗi có nội dung:** đã có lý do.

Đây là ví dụ về **quy ước nghiệp vụ**, không phải ngữ nghĩa cố định mà MongoDB áp đặt. Hãy định nghĩa trước xem API `PATCH` có coi `null` là “xóa trường” hay “ghi null”, rồi giữ quy ước đó qua mọi client.

### 3.2. Đừng dùng falsy check để xác định trường thiếu

Trong JavaScript, điều kiện:

~~~javascript
if (!payload.retryCount) {
  // Sai nếu nghiệp vụ cần phân biệt 0, null và field vắng mặt.
}
~~~

sẽ coi `0`, `null` và `undefined` đều là falsy. Thay vào đó:

~~~javascript
const hasRetryCount = Object.prototype.hasOwnProperty.call(
  payload,
  "retryCount"
);

if (hasRetryCount) {
  // Trường có mặt, kể cả khi giá trị là 0 hoặc null.
}
~~~

Tương tự, một DTO Java mà tất cả thuộc tính là `String`/`Integer` nullable nhưng không lưu **tình trạng có mặt của trường** thường không đủ để biểu diễn đầy đủ ngữ nghĩa của HTTP PATCH.

## 4. Spring Data MongoDB ghi thuộc tính Java null thế nào?

Spring Data MongoDB dùng `MappingMongoConverter` để chuyển đổi giữa entity Java và BSON document. Trong các phiên bản có `@Field(write = ...)` (Spring Data MongoDB 3.3 trở lên), chiến lược mặc định của thuộc tính nullable thông thường là **`Field.Write.NON_NULL`**:

- Nếu giá trị thuộc tính **khác Java null**, converter ghi giá trị tương ứng.
- Nếu giá trị thuộc tính **là Java null**, converter mặc định **không ghi trường đó** khi chuyển entity thành document.
- Nếu cần lưu **BSON null tường minh**, dùng `@Field(write = Field.Write.ALWAYS)` trên thuộc tính.

### 4.1. Entity mặc định: Java null có thể biến thành missing

~~~java
package com.example.workitems;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "workitems_null_demo_008")
public class WorkItemDefault {
    @Id
    private String id;

    private String title;
    private String note;  // Mặc định: null không được ghi.

    protected WorkItemDefault() { }

    public WorkItemDefault(String id, String title, String note) {
        this.id = id;
        this.title = title;
        this.note = note;
    }

    public String getId() { return id; }
    public String getTitle() { return title; }
    public String getNote() { return note; }
}
~~~

Với một document mới được viết bằng converter mặc định:

~~~java
template.insert(new WorkItemDefault(
    "w005", "Chưa có ghi chú", null
));
~~~

Kết quả BSON điển hình là:

~~~javascript
{
  _id: "w005",
  title: "Chưa có ghi chú"
  // Không có note.
}
~~~

Ví dụ giả định `w005` chưa tồn tại. Trường `note` không được ghi chỉ vì giá trị Java là `null`; điều này khác với suy nghĩ “Java null phải luôn trở thành `note: null`”.

### 4.2. Dùng `@Field(write = ALWAYS)` để ghi BSON null

~~~java
package com.example.workitems;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "workitems_null_demo_008")
public class WorkItemExplicitNull {
    @Id
    private String id;

    private String title;

    @Field(write = Field.Write.ALWAYS)
    private String note;

    protected WorkItemExplicitNull() { }

    public WorkItemExplicitNull(String id, String title, String note) {
        this.id = id;
        this.title = title;
        this.note = note;
    }

    public String getId() { return id; }
    public String getTitle() { return title; }
    public String getNote() { return note; }
}
~~~

~~~java
template.insert(new WorkItemExplicitNull(
    "w006", "Đã xác nhận không có ghi chú", null
));
~~~

Kết quả BSON điển hình:

~~~javascript
{
  _id: "w006",
  title: "Đã xác nhận không có ghi chú",
  note: null
}
~~~

Hai class trên là **hai lựa chọn mapping để so sánh**, không phải gợi ý tạo hai repository dùng chung collection trong dự án thật. Chỉ dùng `write = ALWAYS` khi nghiệp vụ cần phân biệt rõ BSON null và missing. Ghi nhiều trường null không cần thiết sẽ làm tăng dung lượng document và có thể tác động đến index.

**Lưu ý:** `@Field(write = ALWAYS)` chi phối quá trình chuyển **entity thành document** của Spring Data MongoDB. Nó không tự sửa các document đã tồn tại, không ép các client `mongosh`/driver khác ghi null và không định nghĩa mặc định ở cấp MongoDB server.

### 4.3. Đọc BSON null và missing vào Java

Với thuộc tính tham chiếu `String note`, sau khi hydrate entity, cả hai trường hợp sau có thể cho cùng `getNote() == null`:

~~~javascript
{ _id: "w001", note: null }
{ _id: "w002" }
~~~

Chỉ nhìn giá trị `note` trong entity không thể khôi phục lịch sử rằng MongoDB lưu null hay thiếu khóa. Nếu cần kiểm tra **field presence**, truy vấn BSON trực tiếp hoặc dùng aggregation `$type` như mục 8.

~~~java
import com.mongodb.client.model.Filters;
import org.bson.Document;

Document raw = template.getDb()
    .getCollection("workitems_null_demo_008")
    .find(Filters.eq("_id", "w002"))
    .first();

if (raw != null) {
    boolean present = raw.containsKey("note");
    boolean explicitNull = present && raw.get("note") == null;
    // present=false: missing; explicitNull=true: BSON null.
}
~~~

Đoạn này dùng MongoDB Java Driver trực tiếp thông qua `template.getDb()`; nó kiểm tra sự hiện diện của khóa trên document thô. API mapping bình thường vẫn phù hợp cho hầu hết CRUD, nhưng sẽ làm mất sự phân biệt giữa hai trạng thái nếu model Java chỉ có một giá trị nullable.

## 5. Java default khác với default được lưu trong MongoDB

Có ít nhất bốn tầng tạo hoặc diễn giải giá trị mặc định. Chúng phục vụ những mục đích khác nhau:

| Nơi khai báo default | Khi nào áp dụng? | Có ghi vào MongoDB không? |
| --- | --- | --- |
| Field initializer / constructor Java | Khi tạo object Java | Chỉ khi entity sau cùng được persist với giá trị đó |
| Service/factory nghiệp vụ | Khi tạo bản ghi theo quy tắc ứng dụng | Có, nếu service đưa giá trị vào thao tác ghi |
| `$setOnInsert` của MongoDB | Khi lệnh `upsert` tạo document mới | Có, ở phía server |
| `$ifNull` trong aggregation | Khi đọc và tính kết quả projection | Không, chỉ tạo giá trị trong kết quả truy vấn |

### 5.1. Khởi tạo trong entity Java

~~~java
@Document("workitems_null_demo_008")
public class WorkItemWithDefaults {
    @Id
    private String id;

    private String status = "NEW";
    private int retryCount = 0;
    private boolean active = false;
    private java.util.List<String> tags = new java.util.ArrayList<>();

    protected WorkItemWithDefaults() { }

    public WorkItemWithDefaults(String id) {
        this.id = id;
    }

    // Getter/setter hoặc phương thức nghiệp vụ phù hợp.
}
~~~

Khi code tạo object mới, `status` có giá trị `"NEW"`, `retryCount` là `0`, `active` là `false` và `tags` là danh sách rỗng. Nếu sau đó insert/save đối tượng này, converter có thể ghi các giá trị đó vào document.

Tuy nhiên, field initializer **không phải** quy tắc default do MongoDB server áp đặt cho mọi writer. Ví dụ `mongosh` vẫn có thể insert `{ _id: "w100" }` mà không cần `status` khi collection không có schema validation bắt buộc.

Khi đọc document **thiếu trường**, cơ chế khởi tạo object và property population có thể giữ giá trị khởi tạo Java; với entity dùng constructor binding/record, dữ liệu thiếu có thể được truyền khác đi và cần xem quy tắc mapping thực tế. Khi đọc document có **trường tường minh bằng null**, converter có thể áp giá trị null vào thuộc tính tham chiếu.

Do đó, **đừng dùng field initializer làm cơ chế migration ngầm**. Một object đọc ra có `status = "NEW"` không chứng minh document gốc có trường `status`.

### 5.2. Primitive và wrapper: giá trị 0/false có thể bị hiểu nhầm

~~~java
private int retryCount;      // Không biểu diễn được Java null.
private Integer retryCount;  // Có thể là null, 0, 1, ...

private boolean active;      // Không biểu diễn được Java null.
private Boolean active;      // Có thể là null, false, true.
~~~

Kiểu primitive luôn phải có một giá trị Java. Tùy đường khởi tạo, việc đọc một document thiếu trường có thể để lại `0` hoặc `false`, khiến ứng dụng không còn biết đó là **mặc định Java** hay **giá trị do người dùng đã ghi**. Với constructor nhận primitive, document thiếu/null còn có thể gây vấn đề binding tùy converter và định nghĩa constructor.

Wrapper `Integer`/`Boolean` cho phép biểu diễn Java null, nhưng **Java null vẫn không tự phân biệt BSON null với missing**. Khi nghiệp vụ có ba trạng thái, cần lưu thông tin hiện diện hoặc truy vấn BSON trực tiếp.

### 5.3. Đặt default ở service hoặc factory

Khi một trạng thái phải tồn tại trong **mọi document mới**, nên chuẩn hóa ngay lúc tạo dữ liệu:

~~~java
public WorkItemWithDefaults createNewWorkItem(String id) {
    // Constructor thiết lập các giá trị ban đầu của entity.
    return new WorkItemWithDefaults(id);
}
~~~

Đây là một quy tắc phía ứng dụng; nếu có nhiều service/job ghi vào cùng collection, các writer phải cùng tuân thủ hoặc database cần schema validation để từ chối dữ liệu thiếu chuẩn. Một default chỉ áp dụng ở service A không đảm bảo dữ liệu do service B sinh ra cũng hợp lệ.

## 6. Giá trị mặc định khi `upsert` với `$setOnInsert`

MongoDB có toán tử `$setOnInsert` dành cho trường chỉ cần khởi tạo khi `upsert` **tạo document mới**:

~~~javascript
workitems.updateOne(
  { _id: "w200" },
  {
    $set: {
      title: "Công việc được tạo hoặc cập nhật",
      active: true
    },
    $setOnInsert: {
      status: "NEW",
      retryCount: 0,
      tags: [],
      createdAt: new Date()
    }
  },
  { upsert: true }
);
~~~

Nếu `w200` chưa tồn tại, MongoDB chèn document mới và áp dụng cả `$set` lẫn `$setOnInsert`. Nếu `w200` đã tồn tại, chỉ `$set` được áp dụng; `$setOnInsert` không ghi đè trạng thái, lịch sử retry hoặc thời điểm tạo cũ.

**Lưu ý:**

- Nếu muốn sửa giá trị ở mỗi lần upsert, dùng `$set`; nếu chỉ muốn giá trị lúc tạo, dùng `$setOnInsert`.
- Không đặt **cùng một đường dẫn trường** vào cả `$set` và `$setOnInsert` trong một thao tác vì có thể dẫn tới lỗi xung đột cập nhật.
- Tạo ID hoặc khóa nghiệp vụ có unique index thích hợp để giảm nguy cơ tạo bản ghi trùng khi nhiều yêu cầu đồng thời.
- `$setOnInsert` chỉ hoạt động cho lệnh upsert tương ứng; nó không tạo default cho mọi lệnh `insertOne` từ client khác.

Với Spring Data MongoDB:

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

Query query = Query.query(Criteria.where("id").is("w201"));

Update update = new Update()
    .set("title", "Công việc mới")
    .setOnInsert("status", "NEW")
    .setOnInsert("retryCount", 0)
    .setOnInsert("createdAt", java.time.Instant.now());

template.upsert(query, update, WorkItemDefault.class);
~~~

`Query`/`Update` được ánh xạ theo entity. `Instant` được Spring Data chuyển đổi sang BSON Date bằng các converter tương ứng; ví dụ giả định cấu hình chuyển đổi ngày giờ mặc định phù hợp. Nếu metadata entity hoặc version có trường tên khác, kiểm tra mapping thực tế.

## 7. Viết truy vấn null và missing bằng `MongoTemplate`

Spring Data MongoDB hỗ trợ `Criteria` với các toán tử null có chủ đích:

~~~java
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

// WorkItemDefault ở mục 4.1 được ánh xạ đến collection ví dụ.

// Khớp BSON null HOẶC trường thiếu.
List<WorkItemDefault> nullOrMissing = template.find(
    Query.query(Criteria.where("note").isNull()),
    WorkItemDefault.class
);

// Chỉ BSON null (Criteria.isNullValue() từ Spring Data MongoDB 3.3+).
List<WorkItemDefault> explicitNull = template.find(
    Query.query(Criteria.where("note").isNullValue()),
    WorkItemDefault.class
);

// Chỉ thiếu khóa note.
List<WorkItemDefault> missing = template.find(
    Query.query(Criteria.where("note").exists(false)),
    WorkItemDefault.class
);

// Trường tồn tại với giá trị khác null.
List<WorkItemDefault> nonNull = template.find(
    Query.query(Criteria.where("note").ne(null)),
    WorkItemDefault.class
);
~~~

`Criteria.where("note").is(null)` cũng diễn tả so sánh null thông thường (null hoặc missing), nhưng `isNull()` nêu ý định rõ hơn. Khi cần **chỉ BSON null**, `isNullValue()` sử dụng kiểm tra BSON type, không giống phép so sánh null thông thường.

| Mục đích | `mongosh` | Spring Data `Criteria` |
| --- | --- | --- |
| Null hoặc missing | `{ note: null }` | `where("note").isNull()` |
| Chỉ BSON null | `{ note: { $type: "null" } }` | `where("note").isNullValue()` |
| Chỉ missing | `{ note: { $exists: false } }` | `where("note").exists(false)` |
| Có khóa, kể cả null | `{ note: { $exists: true } }` | `where("note").exists(true)` |
| Có giá trị khác null | `{ note: { $ne: null } }` | `where("note").ne(null)` |

Trong repository, các phương thức suy diễn tên truy vấn có thể hữu ích, nhưng khi nghiệp vụ bắt buộc phân biệt null với missing, hãy kiểm tra truy vấn BSON thực sự do repository tạo hoặc dùng `MongoTemplate` để thể hiện chính xác `$exists`/`$type`.

### 7.1. `Update.set()` và `Update.unset()` trong Spring Data

~~~java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.query.Update;

Query byId = Query.query(Criteria.where("id").is("w002"));

// Ghi BSON null tường minh.
UpdateResult setNull = template.updateFirst(
    byId,
    new Update().set("note", null),
    WorkItemDefault.class
);

// Xóa hẳn trường note.
UpdateResult removeField = template.updateFirst(
    byId,
    new Update().unset("note"),
    WorkItemDefault.class
);
~~~

Đây là **update operator**, không phải thao tác serialize toàn bộ entity, vì vậy `Update.set("note", null)` có thể ghi BSON null ngay cả khi thuộc tính entity không có `@Field(write = ALWAYS)`. Nếu chạy hai lệnh nối tiếp, kết quả cuối cùng là trường `note` bị loại bỏ.

## 8. Gán mặc định lúc đọc bằng aggregation

### 8.1. `$ifNull` gộp BSON null và missing

~~~javascript
workitems.aggregate([
  {
    $project: {
      _id: 1,
      title: 1,
      displayNote: {
        $ifNull: ["$note", "(không có ghi chú)"]
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Với dữ liệu gốc:

- `w001` (`note: null`) → `"(không có ghi chú)"`.
- `w002` (không có `note`) → `"(không có ghi chú)"`.
- `w003` (`note: "Đã duyệt"`) → `"Đã duyệt"`.
- `w004` (`note: ""`) → `""`, vì chuỗi rỗng vẫn là giá trị khác null.

`$ifNull` coi giá trị undefined và trường missing như null; nó **không cập nhật document trong collection**. Nó chỉ biến đổi kết quả của aggregation. Nếu nghiệp vụ muốn phân biệt missing với null, `$ifNull` không đủ.

### 8.2. `$type` trong aggregation cho phép nhận dạng missing

Khác với `$type` trong query predicate, `$type` ở **aggregation expression** có thể trả về chuỗi `"missing"` khi trường không tồn tại:

~~~javascript
workitems.aggregate([
  {
    $project: {
      title: 1,
      noteType: { $type: "$note" },
      noteState: {
        $switch: {
          branches: [
            {
              case: { $eq: [{ $type: "$note" }, "missing"] },
              then: "MISSING"
            },
            {
              case: { $eq: [{ $type: "$note" }, "null"] },
              then: "EXPLICIT_NULL"
            }
          ],
          default: "VALUE_PRESENT"
        }
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Kết quả ban đầu: `w001 → EXPLICIT_NULL`, `w002 → MISSING`, `w003/w004 → VALUE_PRESENT`. Cách này thích hợp cho báo cáo chất lượng dữ liệu, kiểm tra migration hoặc xử lý trạng thái thiếu dữ liệu trong aggregation.

### 8.3. Đừng nhầm giá trị hiển thị với giá trị lưu trữ

Một trang báo cáo dùng `$ifNull: ["$retryCount", 0]` có thể hiển thị `0` cho document thiếu `retryCount`. Tuy nhiên truy vấn dữ liệu gốc `{ retryCount: 0 }` vẫn không khớp document đó. Nếu yêu cầu mặc định phải tồn tại thật trong database, cần backfill hoặc đặt giá trị ở đường ghi.

## 9. API PATCH: missing, null và giá trị mới

Với HTTP PATCH, nhiều hệ thống chọn quy ước:

| JSON input | Hành động |
| --- | --- |
| `{}` | Không thay đổi `note` |
| `{"note":null}` | Xóa `note` hoặc ghi BSON null theo quy định API |
| `{"note":""}` | Ghi chuỗi rỗng (nếu được chấp nhận) |
| `{"note":"Đã kiểm tra"}` | Ghi chuỗi mới |

Nếu DTO chỉ có `String note` và không lưu field presence, cả `{}` lẫn `{"note":null}` đều có thể thành `note == null`. Ứng dụng mất khả năng phân biệt “người dùng không gửi trường” và “người dùng chủ động gửi null”.

Một cách triển khai rõ ràng là nhận JSON tree và dùng `has()`:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public void patchNote(String id, JsonNode body) {
    // Không gửi note: giữ nguyên.
    if (!body.has("note")) {
        return;
    }

    JsonNode value = body.get("note");
    Update update = new Update();

    if (value.isNull()) {
        // Quy ước của API này: null nghĩa là loại bỏ khóa.
        update.unset("note");
    } else if (value.isTextual()) {
        update.set("note", value.textValue());
    } else {
        throw new IllegalArgumentException(
            "note must be string or null"
        );
    }

    var result = template.updateFirst(
        Query.query(Criteria.where("id").is(id)),
        update,
        WorkItemDefault.class
    );

    if (result.getMatchedCount() == 0) {
        throw new IllegalArgumentException("Work item not found");
    }
}
~~~

Đây là ví dụ phương thức trong service đã được inject `MongoTemplate template`. Nó minh họa ngữ nghĩa PATCH, chưa bao gồm HTTP controller, xử lý ngoại lệ REST hoặc kiểm tra quyền. Nếu API chọn “null phải lưu BSON null”, thay `update.unset("note")` bằng `update.set("note", null)`.

**Không dùng `save()` của entity chứa nhiều thuộc tính nullable như thao tác PATCH chung** nếu bạn chỉ muốn sửa một vài trường. Việc serialize lại toàn bộ entity có thể làm thay đổi sự hiện diện của những trường không liên quan, đặc biệt khi mapper mặc định bỏ qua null. Dùng `Update` với các toán tử đúng trường cần sửa sẽ rõ ý định hơn.

## 10. Index, tính duy nhất và `null`/missing

Các trạng thái null/missing cũng ảnh hưởng đến index.

### 10.1. Unique index đơn trường coi missing và null là một khóa null

Giả sử collection `users` có unique index đơn trường:

~~~javascript
db.users_index_demo_008.createIndex(
  { email: 1 },
  { unique: true }
);
~~~

Đối với unique index đơn trường thông thường, MongoDB lưu một entry kiểu null cho document **thiếu `email`** hoặc **`email: null`**. Vì thế index chỉ chấp nhận **một** document có entry null; document thiếu email tiếp theo hoặc chứa email null có thể bị từ chối với `E11000 duplicate key`.

Điều đó thường trái với mong muốn “email là trường tùy chọn nhưng nếu đã có thì phải duy nhất”.

### 10.2. Unique sparse index và partial index

`sparse` bỏ qua document không có trường được index nhưng vẫn index trường **có mặt với null**:

~~~javascript
// Minh họa trên collection thử nghiệm riêng.
db.users_sparse_demo_008.createIndex(
  { email: 1 },
  { unique: true, sparse: true }
);
~~~

Hệ quả: có thể có nhiều document thiếu `email`, nhưng các document có `email: null` vẫn cạnh tranh một khóa null trong unique sparse index.

Để chỉ áp dụng unique constraint cho email **kiểu chuỗi**, có thể dùng **partial unique index**:

~~~javascript
db.users_partial_demo_008.createIndex(
  { email: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email: { $type: "string" }
    }
  }
);
~~~

Với quy ước `email` là scalar string, index này bỏ qua email missing và BSON null; những document có email string vẫn bị ràng buộc unique. Cần kết hợp validation để không cho dữ liệu email sai kiểu lọt vào; index không tự kiểm tra định dạng email hay chuẩn hóa chữ hoa/chữ thường.

Nếu collection đã có dữ liệu trùng lặp, MongoDB sẽ không tạo được unique index cho đến khi xung đột được xử lý. Việc đổi index trên production cần kiểm kê dữ liệu và đánh giá query performance trước.

## 11. Schema validation và Bean Validation

MongoDB không bắt buộc mọi document trong collection có cùng tập trường nếu không cấu hình validation phù hợp. Để phân biệt **bắt buộc tồn tại** và **được phép null**, MongoDB cung cấp `$jsonSchema`.

### 11.1. `required` kiểm tra sự hiện diện; `bsonType` kiểm tra kiểu

Ví dụ tạo **collection mới, tách biệt với dữ liệu mẫu phần 1**:

~~~javascript
db.createCollection("workitems_schema_demo_008", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["title", "status"],
      properties: {
        title: {
          bsonType: "string",
          description: "Bắt buộc là chuỗi"
        },
        status: {
          bsonType: "string",
          enum: ["NEW", "DONE", "CANCELLED"]
        },
        note: {
          bsonType: ["string", "null"],
          description: "Có thể thiếu, là string hoặc là BSON null"
        }
      }
    }
  }
});
~~~

Trong schema này:

- `title` và `status` là trường **bắt buộc** theo `required`.
- `status` phải là chuỗi thuộc tập `NEW/DONE/CANCELLED`; BSON null bị từ chối.
- `note` không nằm trong `required`, nên có thể **vắng mặt**. Nếu có mặt, phải là string hoặc BSON null.
- Schema chỉ **kiểm tra** document, không tự điền `status = "NEW"` khi trường thiếu.

Nếu chỉ đưa `status` vào `required` nhưng không giới hạn `bsonType`, một document có `status: null` vẫn đáp ứng yêu cầu “trường tồn tại”. Vì vậy muốn “không được null”, cần kiểm tra cả presence và type.

### 11.2. Validation ở Java là một lớp khác

Ví dụ:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class WorkItemRequest {
    @NotBlank
    private String title;

    @NotNull
    private String status;
}
~~~

Các annotation Jakarta Bean Validation có tác dụng khi **cơ chế validation được kích hoạt** ở controller/service hoặc callback phù hợp. Chúng không tự trở thành MongoDB server-side `$jsonSchema`, và client khác có thể ghi thẳng vào MongoDB nếu database không có validator.

Ngoài ra, `@NotNull` không tương đương với `@NotBlank`: một chuỗi `""` là **khác null** nhưng rỗng. Thiết kế validation phải phù hợp quy ước nghiệp vụ.

## 12. Sửa dữ liệu cũ thiếu trường: backfill có chủ đích

Khi phiên bản mới của ứng dụng thêm trường `retryCount`, một số document cũ có thể chưa có trường này. Nếu yêu cầu tất cả bản ghi phải lưu mặc định `0`, dùng bộ lọc missing:

~~~javascript
// Chỉ điền mặc định cho document thiếu retryCount.
workitems.updateMany(
  { retryCount: { $exists: false } },
  { $set: { retryCount: 0 } }
);
// Với dữ liệu gốc: chỉ w002 được cập nhật.
~~~

Lệnh này **không đổi** document `retryCount: null` nếu có. Nếu nghiệp vụ muốn coi null và missing là cùng trạng thái cần backfill, dùng bộ lọc `{ retryCount: null }` nhưng cần hiểu nó khớp cả hai trường hợp.

### 12.1. Kế hoạch migration

Trước khi chạy trên dữ liệu thực tế:

1. Thống kê số lượng **missing**, **BSON null** và **giá trị thực** theo từng trường.
2. Xác định default hợp lệ cho từng trạng thái; đặc biệt không ghi đè `0`, `false` hoặc chuỗi rỗng nếu chúng có ý nghĩa.
3. Kiểm tra tất cả luồng ghi (repository, `MongoTemplate`, job import, driver thô) cùng sử dụng quy ước mới.
4. Chạy backfill trên dữ liệu thử nghiệm, kiểm tra số document thay đổi và kiểm chứng truy vấn nghiệp vụ.
5. Chạy migration production theo kế hoạch vận hành, có backup và khả năng khôi phục, sau đó mới cân nhắc bật schema validation hoặc index ràng buộc.

Các ứng dụng có thể triển khai **compatibility read** tạm thời bằng `$ifNull` để không gián đoạn tính năng khi backfill chưa hoàn tất. Nhưng biểu diễn đọc tạm thời không tự thay thế việc sửa dữ liệu nếu lưu trữ nhất quán là mục tiêu.

### 12.2. Thống kê hiện trạng bằng aggregation

~~~javascript
workitems.aggregate([
  {
    $project: {
      retryCountType: { $type: "$retryCount" }
    }
  },
  {
    $group: {
      _id: "$retryCountType",
      total: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Khi chạy trên dữ liệu mẫu **trước backfill**, bạn sẽ thấy ba document có giá trị số và một document có kiểu `"missing"`. Kết quả có thể là `"int"` hoặc `"long"` tùy kiểu số BSON được ghi; không nên ép giả định tất cả số Java/MongoDB đều có cùng BSON type.

## 13. Kiểm thử nullability trong Spring Data MongoDB

Lỗi null/missing thường không xuất hiện trong unit test chỉ mock repository, vì mock không chạy `MappingMongoConverter` và MongoDB query engine. Với tình huống quan trọng, dùng **integration test** trên MongoDB Testcontainers hoặc MongoDB test instance độc lập.

### 13.1. Những trường hợp cần xác nhận

| Kịch bản kiểm thử | Điều cần xác minh |
| --- | --- |
| Converter ghi `String note = null` mặc định | BSON document không có `note` |
| Converter ghi `@Field(write = ALWAYS)` với `note = null` | BSON document có `note: null` |
| `Criteria.isNull()` | Khớp cả null và missing |
| `Criteria.isNullValue()` | Chỉ khớp BSON null |
| `Criteria.exists(false)` | Chỉ khớp document thiếu trường |
| `Update.set("note", null)` | Trường tồn tại với BSON null |
| `Update.unset("note")` | Trường không còn tồn tại |
| Upsert có `$setOnInsert` | Default chỉ được đặt khi tạo mới |
| Đọc từ entity có field initializer | Không nhầm giá trị Java được gán mặc định với giá trị BSON thực |

### 13.2. Ví dụ kiểm tra BSON thô sau khi insert

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;

@SpringBootTest
class WorkItemNullMappingTest {
    @Autowired MongoTemplate template;

    @Test
    void defaultMappingOmitsNullButAlwaysWritesExplicitNull() {
        // Chỉ chạy với MongoDB test riêng; _id thuộc fixture của test.
        template.insert(new WorkItemDefault(
            "fixture-default-008", "Default", null
        ));
        template.insert(new WorkItemExplicitNull(
            "fixture-always-008", "Explicit", null
        ));

        var collection = template.getDb()
            .getCollection("workitems_null_demo_008");

        Document defaultDoc = collection
            .find(Filters.eq("_id", "fixture-default-008"))
            .first();
        Document explicitDoc = collection
            .find(Filters.eq("_id", "fixture-always-008"))
            .first();

        assertThat(defaultDoc).isNotNull();
        assertThat(defaultDoc.containsKey("note")).isFalse();

        assertThat(explicitDoc).isNotNull();
        assertThat(explicitDoc.containsKey("note")).isTrue();
        assertThat(explicitDoc.get("note")).isNull();
    }
}
~~~

Đây là **ví dụ học tập** dựa trên hai entity ở mục 4 và một MongoDB test đã cấu hình. Trong dự án thật hãy dùng collection riêng cho từng test hoặc dọn fixture trong lifecycle/`try-finally`, tránh chạy nhiều lần với `_id` cố định gây duplicate key.

Nếu ứng dụng dùng reactive access, ý nghĩa BSON của null/missing vẫn giống nhau; test cần subscribe/`StepVerifier` trên `Mono`/`Flux` của `ReactiveMongoTemplate` hoặc `ReactiveMongoRepository` để bảo đảm thao tác thực thi.

## 14. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân hay gặp | Hướng kiểm tra |
| --- | --- | --- |
| `find({ note: null })` trả nhiều document hơn dự kiến | MongoDB khớp cả missing | Đổi sang `$type: "null"` khi chỉ muốn BSON null |
| Đọc document thiếu trường được `null` trong Java | Mapping không giữ thông tin field presence | Dùng driver thô/`$type` để xem dữ liệu BSON gốc |
| Sau `save()` trường từng là `null` biến mất | Converter mặc định không ghi thuộc tính Java null khi serialize | Xem `@Field(write = ALWAYS)`, dùng `Update` khi chỉ sửa một trường |
| API PATCH `{}` lại xóa ghi chú | DTO không phân biệt absent với explicit null | Kiểm tra field presence trước khi xây `Update` |
| `retryCount = 0` bị thay bằng giá trị mặc định khác | Code xem 0 là “chưa nhập” | Phân biệt missing/null và 0 trước khi mặc định |
| `$ifNull` hiển thị 0 nhưng bộ lọc `{ retryCount: 0 }` không khớp | Default chỉ áp dụng trong aggregation | Backfill nếu nghiệp vụ yêu cầu lưu thực |
| Lỗi `E11000` cho email tùy chọn | Unique index đơn trường coi missing và null như một khóa | Xem index hiện có; cân nhắc sparse/partial index |
| Validator từ chối `note: null` | `bsonType` không cho phép `null` | Dùng `bsonType: ["string", "null"]` khi null hợp lệ |
| Validator vẫn chấp nhận `status: null` | Chỉ có `required` mà không ràng buộc kiểu | Dùng cả `required` và `bsonType: "string"` |
| Trạng thái entity lúc đọc là `NEW` dù BSON thiếu `status` | Khởi tạo Java hoặc constructor gán mặc định | Xem document thô; không suy trạng thái lưu từ entity |

Trong quá trình chẩn đoán, nên kiểm tra theo thứ tự: **document BSON thô → filter chính xác → metadata mapping/constructor → luồng ghi/serialize → validation và index**. Đừng sửa annotation hoặc chạy backfill trước khi xác định dữ liệu thực đang là null hay missing.

## 15. Bài thực hành

Các câu hỏi sau giả định dữ liệu gốc gồm `w001` đến `w004` ở mục 1 và **chưa chạy update**.

### Bài 1 — Tìm ba nhóm trạng thái của `note`

Viết ba truy vấn tìm lần lượt: (a) BSON null, (b) missing, (c) có giá trị khác null.

**Đáp án:**

~~~javascript
workitems.find({ note: { $type: "null" } });   // w001
workitems.find({ note: { $exists: false } }); // w002
workitems.find({ note: { $ne: null } });      // w003, w004
~~~

### Bài 2 — Giữ nguyên giá trị `false` và `0`

Bạn nhận document `w001` có `active: false`, `retryCount: 0`. Một hàm JavaScript đặt mặc định bằng `if (!doc.retryCount)`. Vì sao nguy hiểm?

**Đáp án:** Điều kiện đánh giá số `0` là falsy nên có thể ghi đè một số đếm hợp lệ. Nếu cần mặc định **chỉ khi trường thiếu**, kiểm tra sự hiện diện của khóa; nếu cần xử lý cả null, kiểm tra null riêng.

### Bài 3 — PATCH có chủ đích

Với `PATCH /workitems/w003` và payload `{"note": null}`, yêu cầu nghiệp vụ là **xóa hẳn trường `note`**. Hãy viết lệnh MongoDB:

~~~javascript
workitems.updateOne(
  { _id: "w003" },
  { $unset: { note: "" } }
);
~~~

Nếu yêu cầu nghiệp vụ là “ghi BSON null tường minh”, thay `$unset` bằng `$set: { note: null }`.

### Bài 4 — Mặc định chỉ khi tạo document mới

Hãy bổ sung mặc định `status: "NEW"` khi `updateOne(..., { upsert: true })` tạo document, mà không ghi đè `status` của document cũ.

**Đáp án:**

~~~javascript
workitems.updateOne(
  { _id: "w300" },
  {
    $set: { title: "Bản ghi mới hoặc cũ" },
    $setOnInsert: { status: "NEW" }
  },
  { upsert: true }
);
~~~

### Bài 5 — Vì sao unique index gây lỗi?

Collection có `{ unique: true }` trên `email` và đã chứa một document không có `email`. Tại sao insert thêm một document thiếu `email` có thể bị từ chối? Hãy đề xuất thiết kế index khi email là tùy chọn nhưng email kiểu string phải duy nhất.

**Đáp án:** Unique index đơn trường tạo entry null cho missing/null, nên hai document sẽ xung đột. Có thể dùng partial unique index với `partialFilterExpression: { email: { $type: "string" } }` kết hợp schema validation cho kiểu và định dạng email.

## Tài liệu tham khảo

- [MongoDB Manual — Query for Null or Missing Fields](https://www.mongodb.com/docs/manual/tutorial/query-for-null-fields/): ý nghĩa `{field:null}`, `$ne:null`, `$exists` và `$type`.
- [MongoDB Manual — `$exists`](https://www.mongodb.com/docs/manual/reference/operator/query/exists/): kiểm tra trường có tồn tại.
- [MongoDB Manual — `$ifNull`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/ifnull/): mặc định khi đọc trong aggregation.
- [MongoDB Manual — `$type` aggregation expression](https://www.mongodb.com/docs/manual/reference/operator/aggregation/type/): giá trị `"missing"` khi trường không có.
- [MongoDB Manual — `$setOnInsert`](https://www.mongodb.com/docs/manual/reference/operator/update/setoninsert/): mặc định khi upsert tạo document mới.
- [Spring Data MongoDB — `@Field` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/Field.html): `Field.Write.NON_NULL` và `Field.Write.ALWAYS`.
- [Spring Data MongoDB — `Criteria` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/query/Criteria.html): `isNull()`, `isNullValue()`, `exists()`.
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): constructor, property population, collection và null.
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) và [Sparse Indexes](https://www.mongodb.com/docs/manual/core/index-sparse/): tác động của null/missing lên index.
- [MongoDB Manual — JSON Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/json-schema-tips/): `required` và `bsonType` khi cần cho phép null.

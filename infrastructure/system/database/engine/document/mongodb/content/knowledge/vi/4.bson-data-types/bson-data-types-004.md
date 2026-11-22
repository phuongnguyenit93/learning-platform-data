# Chuỗi, boolean, object và mảng lồng nhau trong MongoDB

MongoDB lưu dữ liệu dưới dạng **document BSON (Binary JSON)**. Khi làm việc trong `mongosh`, document trông gần giống một đối tượng JavaScript hoặc JSON, nhưng dữ liệu thực được mã hóa bằng BSON với kiểu rõ ràng. Để thiết kế và truy vấn document chính xác, cần hiểu bốn kiểu thường xuyên xuất hiện cùng nhau: **chuỗi (string)**, **boolean**, **object/document nhúng** và **array/mảng**, đặc biệt khi object và mảng lồng nhiều cấp.

Bài học sử dụng collection `learners` trong database thực hành. Tất cả lệnh minh họa có thể chạy trong `mongosh` sau khi kết nối tới MongoDB có quyền đọc/ghi. Giá trị tên, email và mã khóa học chỉ là dữ liệu mẫu.

## 1. Nhìn từ JSON đến BSON

Xét document mô tả một học viên:

```javascript
{
  _id: "u101",
  name: "Linh",
  active: true,
  profile: {
    location: {
      city: "Hà Nội",
      country: "VN"
    },
    notifications: {
      email: false,
      push: true
    }
  },
  interests: ["MongoDB", "Java"],
  courses: [
    {
      code: "MDB101",
      completed: false,
      results: [
        { part: "quiz", score: 9 },
        { part: "lab", score: 8 }
      ]
    },
    {
      code: "JAVA101",
      completed: true,
      results: [
        { part: "lab", score: 7 }
      ]
    }
  ]
}
```

Phân tích cấu trúc:

| Đường dẫn field | Giá trị ví dụ | Kiểu trong BSON | Vai trò |
| --- | --- | --- | --- |
| `name` | `"Linh"` | String | Văn bản |
| `active` | `true` | Boolean | Trạng thái đúng/sai |
| `profile` | `{ location: ..., notifications: ... }` | Object/document | Gộp dữ liệu thuộc một thực thể |
| `profile.location.city` | `"Hà Nội"` | String | Chuỗi ở trong object lồng nhau |
| `profile.notifications.email` | `false` | Boolean | Cờ ở trong object lồng nhau |
| `interests` | `["MongoDB", "Java"]` | Array | Danh sách chuỗi |
| `courses` | `[{...}, {...}]` | Array | Danh sách object |
| `courses[0].results` | `[{part:"quiz",...},...]` | Array | Mảng object nằm trong object của mảng |

Sơ đồ các cấp của document:

```text
learner (document)
├── _id: "u101"                      String
├── name: "Linh"                    String
├── active: true                    Boolean
├── profile                         Object
│   ├── location                    Object
│   │   ├── city: "Hà Nội"          String
│   │   └── country: "VN"           String
│   └── notifications               Object
│       ├── email: false            Boolean
│       └── push: true              Boolean
├── interests                       Array<String>
│   ├── [0] "MongoDB"
│   └── [1] "Java"
└── courses                         Array<Object>
    ├── [0]                         Object
    │   ├── code: "MDB101"          String
    │   ├── completed: false        Boolean
    │   └── results                 Array<Object>
    │       ├── [0] {part:"quiz", score:9}
    │       └── [1] {part:"lab", score:8}
    └── [1]                         Object
        ├── code: "JAVA101"
        ├── completed: true
        └── results                 Array<Object>
            └── [0] {part:"lab", score:7}
```

MongoDB không yêu cầu mọi document trong cùng collection phải có tập field giống nhau nếu chưa áp dụng schema validation. Tuy nhiên, một field nên có **kiểu nhất quán** giữa các document để tránh việc truy vấn, index và mã ứng dụng phải xử lý nhiều trường hợp bất ngờ.

## 2. String: chuỗi ký tự

String dùng cho tên, mô tả, email, mã định danh dạng văn bản, nhãn và những giá trị bản chất là chữ. BSON lưu string dưới dạng **UTF-8**, nên có thể chứa tiếng Việt, dấu và ký tự Unicode.

```javascript
{
  name: "Nguyễn Thị Linh",
  language: "vi",
  courseCode: "MDB101",
  notes: "Đã hoàn thành phần đọc document",
  active: "true"   // Chú ý: đây là chuỗi, KHÔNG phải boolean
}
```

Trong cú pháp JavaScript của `mongosh`, cả dấu nháy đơn và dấu nháy kép đều có thể tạo string. Khi trình bày dưới dạng JSON thuần, tên khóa và chuỗi dùng dấu nháy kép.

Ví dụ phân biệt string và number:

```javascript
{ studentCode: "00125" }  // Mã định danh: giữ được số 0 đầu
{ studentCode: 125 }      // Kiểu số: không biểu đạt nguyên vẹn "00125"
```

Mã định danh như mã học viên hoặc mã bưu chính thường nên để string nếu không mang ý nghĩa tính toán. Trái lại, các giá trị cần so sánh số học như `score` hoặc `quantity` phải được lưu dưới kiểu số thích hợp, không lưu `"9"` thay cho `9`.

### Truy vấn chuỗi

```javascript
db.learners.find({ name: "Linh" })
db.learners.find({ "profile.location.city": "Hà Nội" })
```

Phép so sánh string thông thường tuân theo quy tắc so sánh/collation của truy vấn; không nên giả định tự động bỏ qua chữ hoa, chữ thường hoặc dấu tiếng Việt. Khi cần so sánh theo ngôn ngữ hoặc không phân biệt chữ hoa/chữ thường, hãy dùng collation được cấu hình phù hợp hoặc biểu thức truy vấn có chủ đích.

Ví dụ tìm tên bắt đầu bằng chữ `L` với regex:

```javascript
db.learners.find({ name: { $regex: "^L", $options: "i" } })
```

Trong chuỗi JavaScript, các ký tự đặc biệt như dấu nháy, dấu gạch chéo ngược và dấu xuống dòng phải được escape theo cú pháp chuỗi:

```javascript
{ note: "Học viên nói: \"Em đã hiểu BSON\"" }
```

## 3. Boolean: đúng hoặc sai

Boolean của BSON có đúng hai giá trị:

- `true`: đúng, bật, có.
- `false`: sai, tắt, không.

```javascript
{
  active: true,
  emailVerified: false,
  settings: {
    newsletter: true,
    pushNotification: false
  }
}
```

Phân biệt rõ:

| Cách viết | Kiểu | Có phải boolean? |
| --- | --- | --- |
| `true` | Boolean | Có |
| `false` | Boolean | Có |
| `"true"` | String | Không |
| `"false"` | String | Không |
| `1` | Số | Không |
| `0` | Số | Không |
| `null` | Null | Không |
| Field không tồn tại | Thiếu field | Không |

MongoDB **không tự coi** chuỗi `"true"` như boolean `true` trong truy vấn equality:

```javascript
db.learners.find({ active: true })      // Tìm boolean true
db.learners.find({ active: "true" })    // Tìm string "true"
```

Trạng thái `false`, `null` và **không có field** mang nghĩa khác nhau. Ví dụ `emailVerified: false` có thể nghĩa là đã biết chưa xác thực, còn field `emailVerified` vắng mặt có thể nghĩa là dữ liệu chưa được thu thập. Khi thiết kế ứng dụng, cần quy ước ý nghĩa cho từng tình huống.

Kiểm tra field có tồn tại:

```javascript
db.learners.find({ active: { $exists: true } })
db.learners.find({ active: { $exists: false } })
```

Kiểm tra kiểu boolean thực sự:

```javascript
db.learners.find({ active: { $type: "bool" } })
```

Lưu ý `{ someField: null }` có thể khớp cả document có giá trị `null` lẫn document thiếu field đó; do vậy không dùng điều kiện này để thay cho kiểm tra boolean `false`.

## 4. Object: document nhúng

Một object là nhóm field con được đặt trong một field của document cha. Trong BSON, đó là **embedded document**. Ví dụ:

```javascript
{
  name: "Linh",
  profile: {
    location: {
      city: "Hà Nội",
      country: "VN"
    },
    notifications: {
      email: false,
      push: true
    }
  }
}
```

Ở đây `profile`, `location` và `notifications` đều là object. Một object có thể chứa string, boolean, số, null, object khác hoặc mảng. Lợi ích chính là dữ liệu liên quan được lưu cùng một document, thuận tiện khi ứng dụng thường đọc/cập nhật chúng cùng nhau.

### Truy cập field qua dot notation

Trong bộ lọc và các toán tử cập nhật MongoDB, **dot notation** viết tên field con theo đường dẫn, các phần nối bằng dấu chấm:

```javascript
db.learners.find({
  "profile.location.city": "Hà Nội"
})

db.learners.find({
  "profile.notifications.email": false
})
```

Tên đường dẫn phải đặt trong chuỗi khi dùng như khóa có dấu `.`. Truy vấn chỉ field con sẽ cho phép object cha chứa thêm field khác.

So sánh hai cách:

```javascript
// Truy vấn field con: chỉ yêu cầu city khớp
db.learners.find({
  "profile.location.city": "Hà Nội"
})

// So sánh toàn bộ embedded document ở field location
db.learners.find({
  "profile.location": {
    city: "Hà Nội",
    country: "VN"
  }
})
```

Điều kiện thứ hai là **equality với toàn bộ object** tại `profile.location`. Nó đòi hỏi cả nội dung và thứ tự field của embedded document khớp giá trị cung cấp; thêm field hoặc đổi thứ tự cũng có thể làm mất kết quả khớp. Khi chỉ cần kiểm tra vài thuộc tính, dot notation linh hoạt và dễ bảo trì hơn.

### Cập nhật một field bên trong object

```javascript
db.learners.updateOne(
  { _id: "u101" },
  { $set: { "profile.location.city": "Đà Nẵng" } }
)
```

`$set` với đường dẫn cụ thể thay đổi `city` mà vẫn giữ `country` và `notifications`. Ngược lại:

```javascript
db.learners.updateOne(
  { _id: "u101" },
  { $set: { profile: { nickname: "L" } } }
)
```

Lệnh thứ hai **thay toàn bộ giá trị** của field `profile` bằng object mới, khiến các field cũ bên dưới `profile` không còn. Vì thế, khi chỉ cần sửa một thuộc tính, hãy cập nhật đúng đường dẫn của nó.

## 5. Array: danh sách có thứ tự

Array của BSON giữ thứ tự phần tử và cho phép truy cập theo **chỉ số bắt đầu từ 0**:

```javascript
{
  interests: ["MongoDB", "Java", "Spring"],
  flags: [true, false, true],
  scores: [7, 8, 9]
}
```

`interests[0]` là `"MongoDB"`, `interests[1]` là `"Java"`. Về mặt BSON, mảng có thể chứa nhiều kiểu khác nhau, nhưng trong thiết kế thực tế nên giữ các phần tử cùng ý nghĩa và kiểu khi có thể:

```javascript
// Hợp lý: danh sách các tên kỹ năng
{ interests: ["MongoDB", "Java"] }

// Hợp lệ về BSON, nhưng khó xử lý nhất quán trong ứng dụng
{ interests: ["MongoDB", true, { name: "Java" }] }
```

### Truy vấn một phần tử trong mảng

```javascript
db.learners.find({ interests: "MongoDB" })
```

Điều kiện trên tìm document có mảng `interests` chứa phần tử `"MongoDB"`; không cần cung cấp cả mảng.

```javascript
db.learners.find({ interests: { $all: ["MongoDB", "Java"] } })
db.learners.find({ "interests.0": "MongoDB" })
db.learners.find({ interests: { $size: 2 } })
```

- `$all`: mảng phải chứa mọi giá trị được liệt kê, không buộc theo cùng thứ tự.
- `interests.0`: kiểm tra phần tử có chỉ số `0` (đầu mảng).
- `$size`: yêu cầu kích thước mảng khớp chính xác.

So sánh với truy vấn equality bằng cả mảng:

```javascript
db.learners.find({ interests: ["MongoDB", "Java"] })
```

Với equality trên nguyên mảng, số phần tử và thứ tự phải khớp. `["Java", "MongoDB"]` là mảng khác.

## 6. Object nằm trong array và array nằm trong object

Một mô hình phổ biến là document người học có một mảng `courses`, trong mỗi phần tử `courses` lại có mảng `results`. Đây là hai cấp mảng–object lồng nhau:

```javascript
{
  courses: [
    {
      code: "MDB101",
      completed: false,
      results: [
        { part: "quiz", score: 9 },
        { part: "lab", score: 8 }
      ]
    },
    {
      code: "JAVA101",
      completed: true,
      results: [
        { part: "lab", score: 7 }
      ]
    }
  ]
}
```

Có thể truy vấn field trong object nằm trong mảng:

```javascript
db.learners.find({ "courses.code": "MDB101" })
db.learners.find({ "courses.completed": true })
db.learners.find({ "courses.results.part": "quiz" })
db.learners.find({ "courses.results.score": { $gte: 9 } })
```

Các điều kiện này cho biết **có ít nhất một phần tử phù hợp** trên đường dẫn được xét. Khi nhiều điều kiện xuất hiện đồng thời, cần cẩn thận về yêu cầu chúng thuộc **cùng một phần tử** hay thuộc những phần tử khác nhau.

### Vấn đề cùng phần tử: tại sao cần `$elemMatch`?

Giả sử yêu cầu: “Tìm học viên có **một khóa học** mang mã `MDB101` và `completed: true`”.

Viết như sau có thể cho kết quả ngoài ý muốn:

```javascript
db.learners.find({
  "courses.code": "MDB101",
  "courses.completed": true
})
```

Vì đây là hai điều kiện tách rời trên đường dẫn mảng, `code` có thể khớp ở phần tử `courses[0]`, còn `completed` lại khớp ở `courses[1]`. Với dữ liệu mẫu, một học viên có thể khớp dù khóa `MDB101` chưa hoàn thành.

Để yêu cầu **cùng một object trong `courses`** thỏa cả hai điều kiện, dùng `$elemMatch`:

```javascript
db.learners.find({
  courses: {
    $elemMatch: {
      code: "MDB101",
      completed: true
    }
  }
})
```

Mở rộng: “Có khóa `MDB101` với **một kết quả quiz có điểm từ 9 trở lên**”:

```javascript
db.learners.find({
  courses: {
    $elemMatch: {
      code: "MDB101",
      results: {
        $elemMatch: {
          part: "quiz",
          score: { $gte: 9 }
        }
      }
    }
  }
})
```

`$elemMatch` bên ngoài liên kết `code` với cùng một khóa học; `$elemMatch` bên trong liên kết `part` và `score` với cùng một object kết quả. Không có hai lớp này, các điều kiện có thể được thỏa bởi những phần tử khác nhau trong từng mảng.

## 7. Mảng lồng mảng

Array cũng có thể chứa array:

```javascript
{
  board: [
    ["A1", "A2", "A3"],
    ["B1", "B2", "B3"]
  ]
}
```

Giả sử `board` là lưới hàng/cột. Trong JavaScript:

```javascript
const board = [
  ["A1", "A2", "A3"],
  ["B1", "B2", "B3"]
];
print(board[1][2]);  // "B3"
```

Khi truy vấn đường dẫn BSON có chỉ số mảng, các chỉ số cũng bắt đầu từ 0:

```javascript
db.grids.find({ "board.1.2": "B3" })
```

Đây là truy vấn các document trong collection `grids` có phần tử ở hàng thứ hai, cột thứ ba bằng `"B3"`. Nếu muốn thực hành với `grids`, có thể thêm dữ liệu bằng `db.grids.insertOne({ board: [["A1","A2","A3"],["B1","B2","B3"]] })`.

Mảng lồng sâu phù hợp với dữ liệu thật sự có cấu trúc như ma trận. Nếu từng phần tử có ý nghĩa nghiệp vụ riêng, object với field đặt tên rõ ràng thường dễ đọc hơn dựa vào vị trí `[1][2]`.

## 8. Thực hành trọn vẹn với `mongosh`

Chọn database thực hành:

```javascript
use bson_lab
```

### Bước 1: tạo dữ liệu có đủ bốn kiểu

```javascript
db.learners.insertMany([
  {
    _id: "u101",
    name: "Linh",
    active: true,
    profile: {
      location: { city: "Hà Nội", country: "VN" },
      notifications: { email: false, push: true }
    },
    interests: ["MongoDB", "Java"],
    courses: [
      {
        code: "MDB101",
        completed: false,
        results: [
          { part: "quiz", score: 9 },
          { part: "lab", score: 8 }
        ]
      },
      {
        code: "JAVA101",
        completed: true,
        results: [
          { part: "lab", score: 7 }
        ]
      }
    ]
  },
  {
    _id: "u102",
    name: "Mai",
    active: false,
    profile: {
      location: { city: "Đà Nẵng", country: "VN" },
      notifications: { email: true, push: false }
    },
    interests: ["MongoDB"],
    courses: [
      {
        code: "MDB101",
        completed: true,
        results: [
          { part: "quiz", score: 10 },
          { part: "lab", score: 9 }
        ]
      }
    ]
  }
])
```

Nếu chạy lại `insertMany` trên cùng database, `_id` đã tồn tại sẽ gây lỗi duplicate key. Khi thực hành lại, hãy dùng giá trị `_id` khác hoặc chủ động dọn dữ liệu mẫu trong môi trường riêng.

### Bước 2: tìm dữ liệu theo string và boolean

```javascript
// Học viên đang hoạt động ở Hà Nội
db.learners.find({
  active: true,
  "profile.location.city": "Hà Nội"
})

// Học viên không bật thông báo email
db.learners.find({
  "profile.notifications.email": false
})
```

Với dữ liệu mẫu ban đầu, cả hai truy vấn này đều tìm được `u101`.

### Bước 3: tìm theo mảng và object trong mảng

```javascript
// Có quan tâm MongoDB
db.learners.find({ interests: "MongoDB" })

// Có ít nhất một khóa học MDB101 đã hoàn thành
db.learners.find({
  courses: {
    $elemMatch: {
      code: "MDB101",
      completed: true
    }
  }
})
```

Truy vấn đầu khớp cả `u101` và `u102`; truy vấn thứ hai khớp `u102` (vì với `u101`, `MDB101` có `completed: false`).

### Bước 4: lấy một số field bằng projection

```javascript
db.learners.find(
  { active: true },
  {
    _id: 0,
    name: 1,
    "profile.location.city": 1,
    interests: 1
  }
)
```

Projection giúp chỉ lấy các field cần thiết. Phần `profile.location.city` vẫn được trả về trong cấu trúc object lồng nhau, thay vì biến thành tên khóa phẳng có dấu chấm.

### Bước 5: cập nhật boolean và một field object

```javascript
db.learners.updateOne(
  { _id: "u101" },
  {
    $set: {
      active: false,
      "profile.notifications.email": true
    }
  }
)
```

Cập nhật này đổi trạng thái của `u101` và cờ thông báo email mà không xóa các field sibling.

### Bước 6: thêm phần tử vào mảng

```javascript
db.learners.updateOne(
  { _id: "u101" },
  { $push: { interests: "Data Modeling" } }
)
```

`$push` thêm một phần tử vào cuối mảng `interests`; nếu muốn tránh thêm giá trị trùng, cân nhắc `$addToSet` cho trường hợp phù hợp.

### Bước 7: cập nhật object ở trong mảng bằng `arrayFilters`

Ví dụ đánh dấu `MDB101` đã hoàn thành, không phụ thuộc khóa học đứng ở vị trí thứ mấy:

```javascript
db.learners.updateOne(
  { _id: "u101" },
  { $set: { "courses.$[course].completed": true } },
  {
    arrayFilters: [
      { "course.code": "MDB101" }
    ]
  }
)
```

`$[course]` là toán tử vị trí có lọc. MongoDB cập nhật những phần tử mảng `courses` thỏa điều kiện `course.code`; nếu nhiều phần tử thỏa thì có thể cập nhật nhiều phần tử của cùng một document. Cách này rõ ràng hơn cập nhật cứng `"courses.0.completed"` khi thứ tự khóa học có thể thay đổi.

Với hai cấp mảng, có thể lọc cả khóa học và kết quả:

```javascript
db.learners.updateOne(
  { _id: "u101" },
  { $set: { "courses.$[course].results.$[result].passed": true } },
  {
    arrayFilters: [
      { "course.code": "MDB101" },
      { "result.part": "lab" }
    ]
  }
)
```

Lệnh trên thêm/cập nhật field `passed: true` cho những object kết quả có `part: "lab"` thuộc khóa `MDB101` của `u101`.

### Bước 8: quan sát document sau cập nhật

```javascript
db.learners.findOne({ _id: "u101" })
```

Quan sát cấu trúc `profile`, `interests` và `courses` sau các thao tác; các object và mảng không liên quan vẫn được giữ nguyên.

## 9. Đọc các kiểu này trong Java MongoDB Driver

Trong Java Sync Driver, `org.bson.Document` biểu diễn object BSON bằng cấu trúc gần như một `Map<String, Object>`. Có thể lồng `Document`, `List`, `String` và `Boolean`:

```java
import org.bson.Document;
import java.util.List;

public class NestedBsonExample {
    public static void main(String[] args) {
        Document learner = new Document("_id", "u201")
            .append("name", "An")
            .append("active", true)
            .append("profile", new Document("city", "Huế")
                .append("notifications",
                    new Document("email", false)))
            .append("interests", List.of("MongoDB", "Java"))
            .append("courses", List.of(
                new Document("code", "MDB101")
                    .append("completed", false)));

        String name = learner.getString("name");
        Boolean active = learner.getBoolean("active");
        Document profile = learner.get("profile", Document.class);
        String city = profile.getString("city");
        List<String> interests = learner.getList("interests", String.class);
        List<Document> courses = learner.getList("courses", Document.class);

        System.out.println(name + " - " + city + " - active=" + active);
        System.out.println(interests.get(0));
        System.out.println(courses.get(0).getString("code"));
    }
}
```

Đây là ví dụ xây dựng và đọc `Document` trong bộ nhớ; chưa kết nối server. Để lưu nó, ứng dụng cần một `MongoCollection<Document>` được lấy từ client/database phù hợp và gọi `insertOne(learner)`.

`getBoolean` có thể trả về `null` nếu field vắng mặt; phương thức đọc theo kiểu cụ thể cũng có thể không phù hợp nếu document thực tế chứa sai kiểu. Ở ứng dụng có dữ liệu đến từ nhiều nguồn, hãy dùng schema validation hoặc lớp mapping/kiểm tra đầu vào để tránh ép kiểu sai.

## 10. Thiết kế document lồng nhau: nên dùng khi nào?

MongoDB thuận tiện cho dữ liệu có cấu trúc phân cấp, nhưng không phải mọi quan hệ đều nên lồng vào một document.

| Trường hợp | Thiết kế thường phù hợp | Lý do |
| --- | --- | --- |
| Tên và thông báo của một học viên | Object `profile` | Thường đọc/cập nhật cùng học viên |
| Danh sách sở thích ngắn | Array string `interests` | Kích thước nhỏ, ý nghĩa đơn giản |
| Một số kết quả học tập thuộc một khóa | Array object `results` | Mỗi kết quả có nhiều thuộc tính liên quan |
| Hàng triệu sự kiện theo thời gian của một người | Collection riêng, tham chiếu theo ID | Mảng tăng vô hạn làm document phình to |
| Quan hệ dùng chung giữa nhiều thực thể | Cân nhắc reference sang document khác | Giảm sao chép và tránh cập nhật nhiều bản |

MongoDB đặt giới hạn kích thước cho một BSON document (thông thường **16 MiB**) và giới hạn độ sâu lồng nhau (thông thường **100 cấp**). Bởi vậy, không nên coi một document như nơi chứa vô hạn bản ghi con. Với mảng tăng trưởng liên tục, có thể cần tách sang collection liên quan, phân trang hoặc áp dụng mô hình dữ liệu khác.

Một số nguyên tắc thực tế:

1. **Tính nhất quán của kiểu:** Trường `active` nên luôn là boolean; trường `interests` nên luôn là mảng string nếu đó là hợp đồng dữ liệu của ứng dụng.
2. **Ranh giới cập nhật:** Khi thường đọc/ghi một nhóm dữ liệu cùng nhau, embedded document có thể giúp thao tác tự nhiên và các thay đổi trong một document có tính nguyên tử.
3. **Mảng có giới hạn:** Những mảng như danh sách sở thích hoặc một tập kết quả hữu hạn thường phù hợp; mảng lịch sử lớn và tăng mãi cần được xem xét lại.
4. **Tránh phụ thuộc chỉ số:** Khi phần tử có mã định danh nghiệp vụ, dùng `$elemMatch` và `arrayFilters` thay vì ngầm cho rằng nó luôn ở vị trí `0`.
5. **Chọn truy vấn theo ngữ nghĩa:** Nếu nhiều điều kiện phải cùng khớp một object trong mảng, dùng `$elemMatch`; nếu chỉ kiểm tra field con, dùng dot notation.
6. **Schema validation:** BSON có kiểu dữ liệu, nhưng collection không tự bảo đảm mọi document theo cùng schema. Với hệ thống dài hạn, có thể áp dụng validator `$jsonSchema` và kiểm tra dữ liệu từ phía ứng dụng.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Hệ quả | Cách hiểu đúng |
| --- | --- | --- |
| `"false"` tương đương `false` | Truy vấn boolean bỏ sót document lưu chuỗi | Chuỗi và boolean là kiểu khác nhau |
| Field thiếu tương đương `false` | Xử lý trạng thái sai, bỏ qua dữ liệu chưa có | Phân biệt missing, null và boolean |
| `{ profile: { city: "Huế" } }` luôn tìm được mọi object có `city: "Huế"` | Không khớp nếu `profile` có thêm field hoặc thứ tự khác | Dùng `"profile.city": "Huế"` để tìm theo field con |
| `"courses.code"` và `"courses.completed"` cùng khớp thì là cùng một khóa | Có thể khớp hai phần tử mảng khác nhau | Dùng `$elemMatch` |
| Mảng là tập hợp không thứ tự | So sánh nguyên mảng và truy cập theo index sai | Array giữ thứ tự; index bắt đầu từ 0 |
| `$set: { profile: {...} }` chỉ sửa vài field bên trong `profile` | Mất các field con cũ | Dùng `$set` với dot notation |
| Thấy `{...}` trong shell là dữ liệu JSON thuần | Bỏ qua đặc điểm về kiểu BSON, `ObjectId`, `Date` | JSON là cách biểu diễn quen thuộc; MongoDB lưu BSON |

## 12. Bài tập tự luyện

### Bài 1: phân biệt kiểu

Xét document:

```javascript
{
  title: "MongoDB",
  published: "false",
  details: {
    reviewed: false,
    tags: ["document", "BSON"]
  }
}
```

Hỏi: `published` có phải boolean không? Viết truy vấn tìm document có `details.reviewed` bằng boolean `false`.

**Gợi ý đáp án:** `published` là string. Bộ lọc:

```javascript
db.articles.find({ "details.reviewed": false })
```

### Bài 2: truy vấn cùng phần tử của mảng

Xét:

```javascript
{
  name: "Minh",
  tasks: [
    { code: "A", done: false },
    { code: "B", done: true }
  ]
}
```

Hỏi: Vì sao bộ lọc `{ "tasks.code": "A", "tasks.done": true }` vẫn có thể khớp document? Viết lại để yêu cầu task `A` đã hoàn thành.

**Gợi ý đáp án:** Hai điều kiện có thể khớp hai phần tử khác nhau. Viết:

```javascript
db.users.find({
  tasks: {
    $elemMatch: { code: "A", done: true }
  }
})
```

Document mẫu không khớp bộ lọc `$elemMatch` này vì task `A` có `done: false`.

### Bài 3: cập nhật object mà không xóa field khác

Document:

```javascript
{
  _id: "u301",
  settings: { theme: "light", newsletter: false }
}
```

Hỏi: Làm thế nào chỉ đổi `newsletter` thành `true` mà giữ `theme`?

**Gợi ý đáp án:**

```javascript
db.learners.updateOne(
  { _id: "u301" },
  { $set: { "settings.newsletter": true } }
)
```

### Bài 4: đọc mảng lồng nhau

Với:

```javascript
{
  groups: [
    { name: "G1", members: ["An", "Bình"] },
    { name: "G2", members: ["Chi", "Dũng"] }
  ]
}
```

Hỏi: Viết truy vấn tìm document có **cùng một group** tên `G2` và chứa member `"Chi"`.

**Gợi ý đáp án:**

```javascript
db.teams.find({
  groups: {
    $elemMatch: {
      name: "G2",
      members: "Chi"
    }
  }
})
```

Trong đó `members: "Chi"` khớp một phần tử của mảng string nằm trong object group được chọn bởi `$elemMatch`.

## Kết luận

Khi đọc một document MongoDB, hãy xác định **kiểu dữ liệu ở từng cấp**. String chứa văn bản; boolean chỉ gồm `true`/`false`; object tổ chức nhóm field; array lưu danh sách có thứ tự và có thể chứa các object hoặc array khác. **Dot notation** truy cập các field sâu, còn **`$elemMatch`** bảo đảm các điều kiện cùng áp dụng lên một phần tử mảng. Với cập nhật, `$set` theo đường dẫn và `arrayFilters` giúp sửa đúng phần tử mà không vô tình thay cả object hoặc mảng.

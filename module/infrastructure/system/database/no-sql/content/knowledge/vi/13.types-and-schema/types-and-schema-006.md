# Collection, mảng, tập hợp và thứ tự phần tử trong NoSQL

Một chương trình có thể lưu **nhiều giá trị** trong cùng một thuộc tính: danh sách bài học, các thẻ phân loại, nhóm quyền hoặc thứ tự những sản phẩm được ưu tiên. Trong NoSQL, quyết định lưu các giá trị này dưới dạng **mảng/danh sách có thứ tự**, **tập hợp không trùng**, **ánh xạ khóa–giá trị**, hay **nhiều bản ghi độc lập** ảnh hưởng trực tiếp đến schema, truy vấn, thao tác cập nhật và tính nhất quán.

Ví dụ, một khóa học có các bài học phải xem theo thứ tự:

~~~json
{
  "courseId": "course-01",
  "lessonIds": ["lesson-a", "lesson-b", "lesson-c"]
}
~~~

Trong khi đó, những thẻ của khóa học có thể chỉ cần trả lời “khóa học mang thẻ Java và NoSQL không?”:

~~~json
{
  "courseId": "course-01",
  "tags": ["java", "nosql"]
}
~~~

Hai trường đều có thể biểu diễn bằng **JSON array**, nhưng **hợp đồng nghiệp vụ khác nhau**: `lessonIds` cần giữ thứ tự; `tags` thường cần tính duy nhất, không cần vị trí. Nếu lựa chọn thao tác ghi sai, hệ thống có thể tạo thẻ trùng, đổi nhầm vị trí bài học hoặc phụ thuộc một thứ tự mà database không bảo đảm.

Bài học làm rõ ý nghĩa của **collection, array/list, set, map và ordered collection**, sau đó áp dụng vào các kiểu dữ liệu và thao tác trong MongoDB, Redis, Cassandra và DynamoDB.

## 1. Từ “collection” có nhiều nghĩa, cần phân biệt từ đầu

Trong tài liệu NoSQL, **collection** không phải lúc nào cũng chỉ một thứ.

| Ngữ cảnh | “Collection” nghĩa là gì? | Ví dụ |
| --- | --- | --- |
| **Document database** | Không gian có tên chứa nhiều document | Collection `courses` chứa các tài liệu khóa học trong MongoDB |
| **Kiểu dữ liệu collection** | Một giá trị có nhiều phần tử nằm trong trường hoặc cấu trúc dữ liệu | Mảng `lessonIds`, tập hợp `tags`, map `preferences` |
| **Ngôn ngữ lập trình** | Abstraction cho cấu trúc chứa nhiều phần tử | `List<E>`, `Set<E>` trong Java |
| **Kiểu lưu trữ riêng của key–value store** | Dữ liệu nhiều phần tử được quản lý tại một key | Redis List, Redis Set, Redis Sorted Set |

**Collection trong MongoDB** và **set trong Redis** không phải hai cách gọi cùng một cấu trúc. Một collection MongoDB chứa các document có thể truy vấn và lập chỉ mục; Redis Set là một kiểu giá trị không trùng phần tử được lưu tại **một khóa Redis**.

Cũng không nên nhầm “collection” ở đây với “collection trong bộ nhớ Java”. Chẳng hạn, một `HashSet` bên Java có thể được tuần tự hóa thành **mảng JSON** và lưu trong MongoDB. Tính duy nhất khi ở trong `HashSet` **không tự trở thành ràng buộc duy nhất của mảng trong database**.

Để học hiệu quả, ta tách hai cấp:

~~~text
Cấp 1: tập bản ghi của hệ lưu trữ
  Database
    └── collection: courses
           ├── document course-01
           └── document course-02

Cấp 2: giá trị nhiều phần tử bên trong một document
  course-01
    ├── lessonIds: ["lesson-a", "lesson-b"]  ← mảng có thứ tự
    ├── tags: ["java", "nosql"]             ← mảng nhưng dùng như tập hợp
    └── preferences: { "lang": "vi" }      ← object/map
~~~

Sự khác biệt giữa **cấp chứa bản ghi** và **kiểu của một field** rất quan trọng khi thiết kế chỉ mục, phân vùng, validation và cập nhật.

## 2. Phân loại theo bốn câu hỏi nghiệp vụ

Trước khi chọn cấu trúc, hãy trả lời:

1. **Thứ tự có ý nghĩa không?** Bài học trước/sau, thứ hạng, ưu tiên và lịch phát cần thứ tự. Tags hoặc nhóm kỹ năng có thể không cần.
2. **Phần tử trùng có hợp lệ không?** Giỏ hàng thường lưu mỗi SKU một dòng có số lượng; playlist âm nhạc có thể cố ý có cùng bài nhiều lần; danh sách quyền thường không nên lặp một quyền.
3. **Phần tử được tìm theo vị trí hay theo danh tính?** `items[2]` nhạy với việc thêm/xóa trước nó, còn `lineId = "L03"` thường ổn định hơn.
4. **Danh sách có tăng vô hạn và được truy vấn độc lập không?** Một tập vài thẻ có thể nhúng; hàng triệu sự kiện liên quan đến một người dùng thường nên lưu ở nhiều record.

### Bảng so sánh ngữ nghĩa

| Cấu trúc logic | Giữ thứ tự? | Cho phép giá trị trùng? | Truy cập theo | Ví dụ |
| --- | --- | --- | --- | --- |
| **Array/list/sequence** | Có, thứ tự phần tử là một phần giá trị | Thường có | Chỉ số, thứ tự hoặc ID của phần tử | Thứ tự bài học, bước workflow |
| **Set** | **Không cam kết thứ tự chèn** theo ngữ nghĩa tập hợp | Không, với quy tắc so sánh phần tử xác định | Thành viên: có/không | Thẻ, vai trò, nhóm ID duy nhất |
| **Sorted set / ordered set** | Có, theo **khóa sắp xếp/điểm** | Thành viên thường duy nhất; điểm có thể trùng | Giá trị và thứ hạng/điểm | Bảng xếp hạng, công việc theo ưu tiên |
| **Map/dictionary** | Không nên dựa vào thứ tự khóa nếu hợp đồng không cam kết | Khóa duy nhất trong cùng map | Khóa | Cài đặt `theme → dark` |
| **Nhiều document/row riêng** | Không có thứ tự tự nhiên đáng tin | Phụ thuộc key và ràng buộc | Khóa, chỉ mục, truy vấn và sort | Nhật ký sự kiện, hàng hóa, bình luận |

“Có thứ tự” ở đây nói về **ý nghĩa của cấu trúc lưu trữ**. Đối với tập document trong collection, việc engine trả một thứ tự nào đó **không phải cam kết**. Muốn trả kết quả có thứ tự, thường phải **sắp xếp tường minh** theo field ổn định và khóa phụ.

## 3. Mảng và danh sách: thứ tự là dữ liệu

**Array** là cấu trúc có dãy phần tử tại vị trí 0, 1, 2, ... trong nhiều API. **List** trong các sản phẩm thường cũng diễn tả dãy có thứ tự, dù chi tiết về chèn/xóa/tìm kiếm và hiệu năng khác nhau.

Ví dụ danh sách bài học:

~~~json
{
  "_id": "course-01",
  "lessonIds": [
    "lesson-intro",
    "lesson-index",
    "lesson-query"
  ]
}
~~~

Ở đây:

- Vị trí 0 phải là `lesson-intro`.
- Vị trí 1 phải là `lesson-index`.
- Vị trí 2 phải là `lesson-query`.
- Nếu đưa `lesson-query` lên trước, ý nghĩa của lộ trình học thay đổi.

**Hai mảng có cùng các giá trị nhưng khác thứ tự không nhất thiết tương đương**:

~~~json
["lesson-intro", "lesson-index", "lesson-query"]
~~~

~~~json
["lesson-query", "lesson-index", "lesson-intro"]
~~~

Chúng có cùng tập giá trị, nhưng khác **sequence**. Nếu trường `lessonIds` là thứ tự học, chỉ một dãy đúng theo yêu cầu sản phẩm.

### 3.1. Mảng có thể chứa giá trị trùng

~~~json
{
  "_id": "playlist-01",
  "tracks": [
    "track-a",
    "track-b",
    "track-a"
  ]
}
~~~

Nếu hệ thống playlist cho phép phát lại bài A hai lần, đây là dữ liệu hợp lệ. Dùng **set** để lưu dãy này sẽ làm mất một lần xuất hiện của `track-a` và làm mất vị trí tương ứng.

Vì vậy, “loại bỏ trùng lặp” không phải cải tiến mặc định. Nó chỉ đúng nếu nghiệp vụ quy định mỗi giá trị xuất hiện tối đa một lần.

### 3.2. Array có thể chứa object

~~~json
{
  "_id": "course-01",
  "lessons": [
    {
      "lessonId": "lesson-intro",
      "title": "Giới thiệu NoSQL",
      "durationMinutes": 15
    },
    {
      "lessonId": "lesson-index",
      "title": "Chỉ mục",
      "durationMinutes": 25
    }
  ]
}
~~~

Mỗi phần tử là một object lồng nhau. Trong mô hình tài liệu, đây là cách **nhúng các thành phần có vòng đời gần nhau**.

Nếu mỗi bài học được chỉnh sửa bởi nhóm riêng, có nội dung lớn, quyền riêng và số lượng có thể tăng nhiều, có thể chỉ nhúng **mảng các ID có thứ tự** rồi lưu nội dung bài học ở collection `lessons`. Đó là chiến lược **tham chiếu kết hợp thứ tự cục bộ**.

### 3.3. Chỉ số không phải định danh ổn định

Giả sử `lesson-index` đang ở `lessonIds[1]`. Sau khi thêm `lesson-setup` vào đầu, `lesson-index` chuyển sang chỉ số 2.

~~~text
Ban đầu:
[0] lesson-intro
[1] lesson-index
[2] lesson-query

Sau khi thêm ở đầu:
[0] lesson-setup
[1] lesson-intro
[2] lesson-index
[3] lesson-query
~~~

API chỉnh sửa bài học không nên dựa lâu dài vào “bài học số 1” để xác định một đối tượng. Nên dùng **`lessonId` bất biến**, còn vị trí là thuộc tính có thể thay đổi.

## 4. Set: tính duy nhất quan trọng hơn thứ tự

**Set (tập hợp)** diễn tả những phần tử khác nhau. Một thành viên có hoặc không nằm trong tập; **số lần gửi yêu cầu thêm cùng phần tử không khiến tập xuất hiện nhiều bản sao**, theo quy tắc so sánh của hệ.

Ví dụ:

~~~text
Tags của course-01: {java, nosql, database}
Thêm "java" lần nữa: vẫn {java, nosql, database}
~~~

Ứng dụng thường dùng set cho:

- Tags và nhóm phân loại.
- Vai trò người dùng, phạm vi quyền, nhóm tính năng.
- Danh sách ID đã chọn, đăng ký hoặc theo dõi nếu thứ tự không quan trọng.
- Tập thiết bị đang thuộc một nhóm.
- Tập khóa đã xử lý nhằm hỗ trợ idempotency, nếu có thêm quy tắc thời hạn lưu giữ.

### 4.1. Set không bảo đảm thứ tự hiển thị

Nếu một hệ trả thành viên như:

~~~text
{java, nosql, database}
~~~

thì lần khác có thể trả:

~~~text
{database, java, nosql}
~~~

nếu kiểu set không cam kết thứ tự. Hai kết quả vẫn biểu diễn **cùng tập hợp**.

Một số implementation **sắp xếp nội bộ** hoặc trả dữ liệu theo thứ tự có quy luật. Điều đó không làm ngữ nghĩa của một set trở thành “thứ tự chèn”: **muốn thứ tự hiển thị xác định, hãy sort theo tiêu chí rõ ràng**.

### 4.2. Điều kiện “bằng nhau” phải được định nghĩa

Trong tập tag, `"Java"` và `"java"` có phải một phần tử không? Điều này phụ thuộc **chuẩn hóa** và quy tắc so sánh:

~~~text
Input: " Java ", "JAVA", "java"
Normalize theo chính sách ứng dụng:
  trim whitespace
  chuyển kiểu chữ theo quy tắc đã chọn
  kiểm soát Unicode/locale khi cần
Kết quả set:
  {"java"}
~~~

Không nên tùy tiện bỏ dấu tiếng Việt, chuẩn hóa Unicode hoặc áp dụng lowercase theo một locale bất kỳ nếu sản phẩm coi hai chuỗi đó là danh tính khác nhau. Cần ghi rõ hợp đồng: loại bỏ khoảng trắng ở đâu, có phân biệt hoa/thường không, có cho phép tag rỗng không.

Đối với set các **object**, quy tắc bình đẳng có thể phức tạp hơn set các chuỗi. Nếu mục tiêu là “mỗi user chỉ xuất hiện một lần”, dùng **userId ổn định** làm thành viên thay vì dựa vào việc so sánh toàn bộ object người dùng.

### 4.3. Set có thể là ràng buộc logic dù database lưu array

MongoDB có **BSON array**, nhưng không có một BSON Set riêng tương ứng với Redis Set. Ta vẫn có thể biểu diễn tags bằng một mảng và áp đặt quy tắc “không trùng”.

~~~json
{
  "_id": "course-01",
  "tags": ["java", "nosql", "database"]
}
~~~

Thao tác thêm bằng toán tử chuyên dụng và validation ứng dụng có thể giúp duy trì quy tắc đó. Nhưng **mảng không tự biến thành set** chỉ vì field tên là `tags`.

## 5. Sorted set: thứ tự theo tiêu chí, không theo vị trí chèn

Một **sorted set** giữ các thành viên riêng biệt nhưng đồng thời hỗ trợ sắp theo **score**, mức ưu tiên hoặc một khóa thứ tự khác.

Ví dụ bảng xếp hạng:

~~~text
Thành viên      Điểm
usr-binh        200
usr-mai         350
usr-an          350
~~~

Nếu có hai người cùng điểm, hệ cần thêm **quy tắc tie-breaker**. Một số implementation dùng thứ tự chữ của member khi điểm trùng; ứng dụng có thể cần một tiêu chí khác như thời điểm đạt điểm hay ID.

Cần phân biệt ba khái niệm:

1. **Insertion order:** thứ tự phần tử được thêm vào.
2. **Business order:** thứ tự do người dùng chủ động sắp, như lộ trình bài học.
3. **Score order:** thứ tự tính từ giá trị như điểm, ưu tiên hoặc deadline.

Một set chỉ có tính duy nhất không tự trả lời yêu cầu “ai đứng thứ nhất?”. Còn một list giữ insertion order không tự trở thành bảng xếp hạng khi điểm thay đổi. Hãy chọn cấu trúc theo **loại thứ tự** nghiệp vụ.

## 6. Map/dictionary: collection theo khóa thay vì theo vị trí

**Map** lưu các cặp khóa–giá trị:

~~~json
{
  "preferences": {
    "language": "vi",
    "theme": "dark",
    "timezone": "Asia/Ho_Chi_Minh"
  }
}
~~~

Ý nghĩa truy cập là `preferences.theme`, không phải “phần tử thứ hai của preferences”. Các khóa trong cùng object/map cần tuân theo quy tắc về tính duy nhất của định dạng và hệ lưu trữ.

Một số công cụ giữ thứ tự trường khi serialize, nhưng **thứ tự khóa của object/map không nên được dùng làm thứ tự nghiệp vụ**, trừ khi hệ cụ thể bảo đảm và mô hình đã quy định rõ. Trong JSON, thứ tự thành viên object không nên làm căn cứ để diễn giải “bước đầu tiên” hay “mức ưu tiên cao nhất”.

Nếu ứng dụng cần danh sách bước workflow, dùng:

~~~json
{
  "steps": [
    { "id": "verify", "name": "Xác minh" },
    { "id": "approve", "name": "Phê duyệt" },
    { "id": "publish", "name": "Xuất bản" }
  ]
}
~~~

thay vì gán ý nghĩa thứ tự cho các key của:

~~~json
{
  "steps": {
    "verify": {},
    "approve": {},
    "publish": {}
  }
}
~~~

Map phù hợp khi các key có **danh tính ổn định** và cần tra cứu riêng; list phù hợp khi **thứ tự giữa phần tử** là một phần của dữ liệu.

## 7. Bốn tình trạng của một field collection

Với field `tags`, những trạng thái sau có thể khác nhau:

~~~json
{ "_id": "course-a" }
~~~

~~~json
{ "_id": "course-b", "tags": null }
~~~

~~~json
{ "_id": "course-c", "tags": [] }
~~~

~~~json
{ "_id": "course-d", "tags": ["java"] }
~~~

| Trạng thái | Ý nghĩa có thể đặt ra |
| --- | --- |
| **Thiếu field** | Chưa có dữ liệu hoặc bản ghi theo schema cũ |
| **`null`** | Giá trị chưa xác định hoặc được đặt null có chủ ý |
| **`[]`** | Một collection rỗng, đã biết không có phần tử |
| **Mảng có phần tử** | Đã lưu danh sách/tập các giá trị |

Không nên tự xem **missing = null = empty list** nếu nghiệp vụ dùng chúng cho các tình trạng khác nhau. Khi xây API, cần quyết định có chuẩn hóa về mảng rỗng để client dễ dùng hay không, và việc chuẩn hóa đó diễn ra lúc ghi, đọc hoặc migration.

**Một số hệ có native set không cho phép empty set.** Khi đó “không có thành viên” có thể cần được biểu diễn bằng field vắng mặt hoặc một cấu trúc khác. Đừng mặc định các loại collection trong mọi NoSQL có cùng quy tắc với JSON array.

## 8. MongoDB: mảng và thao tác thêm, xóa, cập nhật

Ví dụ sau dùng `mongosh` và một database thử nghiệm riêng. Các lệnh chỉ sửa một collection minh họa. Trong môi trường thật, tránh chạy lệnh xóa collection hoặc cập nhật hàng loạt khi chưa kiểm tra dữ liệu.

### 8.1. Tạo tài liệu thử nghiệm

~~~javascript
const lab = db.getSiblingDB("nosql_collections_lab");

lab.courses.drop();

lab.courses.insertOne({
  _id: "course-01",
  title: "NoSQL co ban",
  lessonIds: ["lesson-intro", "lesson-index", "lesson-query"],
  tags: ["java", "nosql"],
  lessons: [
    { lessonId: "lesson-intro", minutes: 10, published: true },
    { lessonId: "lesson-index", minutes: 20, published: true },
    { lessonId: "lesson-query", minutes: 25, published: false }
  ],
  preferences: {
    language: "vi",
    theme: "dark"
  },
  version: 1
});

printjson(lab.courses.findOne({ _id: "course-01" }));
~~~

Tài liệu có ba kiểu hình thái:

- `lessonIds`: mảng ID **có thứ tự**.
- `tags`: mảng được ứng dụng muốn sử dụng như **set**.
- `preferences`: object/map.
- `lessons`: **array of embedded documents**, trong đó mỗi phần tử có `lessonId` để nhận diện độc lập với vị trí.

### 8.2. $push: thêm phần tử vào cuối mảng

~~~javascript
lab.courses.updateOne(
  { _id: "course-01" },
  {
    $push: {
      lessonIds: "lesson-review"
    }
  }
);
~~~

`$push` thêm giá trị vào mảng, kể cả khi giá trị đó **đã có**. Nếu request bị gửi hai lần do timeout, mảng có thể chứa hai `lesson-review`. Vì vậy, với danh sách mà bài học không được trùng, cần có cơ chế **idempotency hoặc ràng buộc logic bổ sung**, chứ không nên tin `$push` tự ngăn trùng.

### 8.3. $addToSet: thêm thành viên nếu chưa có

~~~javascript
lab.courses.updateOne(
  { _id: "course-01" },
  {
    $addToSet: {
      tags: "java"
    }
  }
);

// Thêm nhiều giá trị bằng $each.
lab.courses.updateOne(
  { _id: "course-01" },
  {
    $addToSet: {
      tags: { $each: ["database", "java", "redis"] }
    }
  }
);
~~~

`$addToSet` chỉ thêm **giá trị chưa có** trong mảng theo quy tắc so sánh MongoDB. Một số điểm dễ nhầm:

1. Nó **không xóa phần tử trùng đã tồn tại từ trước**.
2. Nếu dùng với field chứa giá trị không phải mảng, thao tác có thể lỗi thay vì tự chuyển thành mảng hợp lệ.
3. Nó **không cam kết thứ tự** các giá trị mới được thêm.
4. Với **embedded document**, việc xác định “bằng nhau” có thể phụ thuộc toàn bộ nội dung và thứ tự field của document; không nên dùng để áp đặt duy nhất theo một field như `lessonId`.
5. Nó **không tự chuẩn hóa** `"Java"` và `"java"` thành cùng tag.

Điều này minh họa rõ: `$addToSet` là một **toán tử cập nhật mảng**, không biến `tags` thành kiểu Set độc lập có đầy đủ mọi bảo đảm của một native set.

### 8.4. $pull: xóa theo giá trị/điều kiện

~~~javascript
lab.courses.updateOne(
  { _id: "course-01" },
  {
    $pull: {
      tags: "redis"
    }
  }
);
~~~

Với mảng đối tượng:

~~~javascript
lab.courses.updateOne(
  { _id: "course-01" },
  {
    $pull: {
      lessons: { lessonId: "lesson-query" }
    }
  }
);
~~~

`$pull` xóa **mọi phần tử** khớp điều kiện trong mảng. Nếu chỉ muốn xóa đúng một thực thể logic, nên bảo đảm `lessonId` duy nhất trong mảng hoặc dùng cấu trúc lưu trữ khác có khóa riêng.

### 8.5. $pop và vị trí đầu/cuối

Trong MongoDB:

~~~javascript
// Xóa phần tử cuối mảng.
lab.courses.updateOne(
  { _id: "course-01" },
  { $pop: { lessonIds: 1 } }
);

// Xóa phần tử đầu mảng.
lab.courses.updateOne(
  { _id: "course-01" },
  { $pop: { lessonIds: -1 } }
);
~~~

`$pop` xóa dựa trên **vị trí** chứ không theo ID. Nếu một writer khác vừa đổi thứ tự, lệnh có thể xóa phần tử khác với dự định nghiệp vụ. Với thao tác xóa bài học cụ thể, nên nhận diện bằng `lessonId`.

### 8.6. Chèn vào vị trí xác định

MongoDB hỗ trợ modifier `$position` khi dùng `$push` cùng `$each`:

~~~javascript
lab.courses.updateOne(
  { _id: "course-01" },
  {
    $push: {
      lessonIds: {
        $each: ["lesson-setup"],
        $position: 0
      }
    }
  }
);
~~~

Lệnh chèn `lesson-setup` vào đầu mảng và đẩy các phần tử hiện có sang sau. Đây là thao tác **mang ngữ nghĩa thứ tự**. Tuy nhiên, nếu application cần chống trùng và cập nhật đồng thời, cần thêm điều kiện/version hoặc mã thao tác không lặp.

### 8.7. MongoDB $sort trên mảng không đồng nghĩa với thứ tự do người dùng tự chọn

Modifier `$sort` trong cập nhật `$push` có thể sắp các phần tử của mảng theo một quy tắc:

~~~javascript
// Ví dụ độc lập: sắp mảng scores theo số tăng dần.
lab.courses.updateOne(
  { _id: "course-01" },
  {
    $push: {
      scores: {
        $each: [80, 60, 90],
        $sort: 1
      }
    }
  }
);
~~~

Lệnh tạo/sắp mảng `scores` theo số. Nhưng **thứ tự bài học** có thể là thứ tự do biên tập viên tự chọn, không phải thứ tự chữ/số tự nhiên. Khi đó không được dùng `$sort` theo ID để “sửa” danh sách, vì sẽ thay đổi ý nghĩa của curriculum.

MongoDB còn hỗ trợ modifier `$slice` để giới hạn số phần tử giữ lại khi dùng `$push` và `$each`; kỹ thuật này hữu ích cho **mảng gần nhất có giới hạn**, không thay thế cho lịch sử đầy đủ.

## 9. MongoDB: truy vấn mảng và ngữ nghĩa thành viên

### 9.1. Kiểm tra phần tử thuộc mảng

~~~javascript
// Tìm khóa học có tag "nosql".
lab.courses.find({
  tags: "nosql"
});
~~~

Đối với mảng các giá trị vô hướng, mẫu truy vấn này có thể khớp nếu mảng chứa phần tử `"nosql"`. Đây là câu hỏi **membership**, không phải so sánh nguyên mảng với chuỗi.

### 9.2. Kiểm tra có đủ nhiều phần tử

~~~javascript
// Khóa học chứa cả hai tag.
lab.courses.find({
  tags: { $all: ["java", "nosql"] }
});
~~~

`$all` hữu ích khi yêu cầu **tập bao hàm** nhiều thành viên. Nó không buộc mảng có đúng hai phần tử và không yêu cầu chúng ở cùng thứ tự.

Ngược lại, nếu so sánh **nguyên mảng**:

~~~javascript
lab.courses.find({
  lessonIds: [
    "lesson-intro",
    "lesson-index",
    "lesson-query"
  ]
});
~~~

đây là so khớp **giá trị mảng theo cấu trúc và thứ tự**; không chỉ là hỏi mảng có đủ ba thành viên. Vì lệnh cập nhật ở các phần trước đã làm thay đổi `lessonIds`, ví dụ này có thể không còn khớp sau khi đã thử chèn/xóa. Hãy chạy lại seed nếu muốn kiểm tra trạng thái ban đầu.

### 9.3. $size và điều kiện theo số phần tử

~~~javascript
lab.courses.find({
  tags: { $size: 2 }
});
~~~

`$size` kiểm tra độ dài mảng; nó không phải phép kiểm tra **số thành viên khác nhau** nếu mảng đang có phần tử trùng. Ví dụ `["java", "java"]` có độ dài 2 nhưng chỉ có một giá trị phân biệt.

Muốn ràng buộc mảng không trùng trong dữ liệu lịch sử, cần giải pháp phù hợp như validation/truy vấn đối chiếu hoặc chuyển dữ liệu; `$size` riêng lẻ không làm được điều đó.

### 9.4. $elemMatch: hai điều kiện trên cùng một phần tử

Một mảng có các đối tượng bài học:

~~~json
[
  { "lessonId": "lesson-intro", "minutes": 10, "published": true },
  { "lessonId": "lesson-query", "minutes": 25, "published": false }
]
~~~

Truy vấn dưới đây có thể khớp **hai phần tử khác nhau**:

~~~javascript
lab.courses.find({
  "lessons.published": true,
  "lessons.minutes": { $gte: 20 }
});
~~~

Một bài đã publish có thể ngắn 10 phút, còn bài dài 25 phút chưa publish. Nếu muốn **cùng một bài vừa published vừa có thời lượng ≥20**, dùng:

~~~javascript
lab.courses.find({
  lessons: {
    $elemMatch: {
      published: true,
      minutes: { $gte: 20 }
    }
  }
});
~~~

Sự khác biệt giữa **“trong mảng có A và có B”** với **“tồn tại một phần tử thỏa cả A và B”** rất quan trọng đối với mảng object. Một kết quả có thể đúng ở truy vấn đầu nhưng không đúng ở truy vấn thứ hai.

## 10. Cập nhật phần tử theo ID, không theo chỉ số tạm thời

Giả sử biên tập viên muốn thay thời lượng của `lesson-index` từ 20 lên 30 phút. Nếu dùng `lessons.1.minutes`, thao tác chỉ đúng khi phần tử đó vẫn đứng ở chỉ số 1. Nếu người khác đã đổi thứ tự, có thể sửa nhầm bài.

Sử dụng **array filters**:

~~~javascript
lab.courses.updateOne(
  { _id: "course-01" },
  {
    $set: {
      "lessons.$[lesson].minutes": 30
    }
  },
  {
    arrayFilters: [
      { "lesson.lessonId": "lesson-index" }
    ]
  }
);
~~~

Toán tử `$[lesson]` hướng thao tác tới phần tử thỏa điều kiện. Nếu có nhiều phần tử trùng `lessonId`, nhiều phần tử có thể cùng được cập nhật. Vì vậy, **quy tắc duy nhất của lessonId trong cùng course** vẫn phải được hệ thống bảo vệ.

Đối với thay đổi thuộc tính, thao tác dựa trên **identity** thường an toàn hơn thao tác dựa trên **position**. Đối với thay đổi thứ tự, chính vị trí hoặc field `position` mới là thông tin nghiệp vụ cần cập nhật.

## 11. Thứ tự phần tử dưới ghi đồng thời

Bài toán “đưa bài C lên đầu” nghe đơn giản nhưng có thể xảy ra hai thao tác cạnh tranh:

~~~text
Trạng thái ban đầu, version 7:
[A, B, C]

Editor 1 muốn:
[C, A, B]

Editor 2 muốn:
[B, A, C]
~~~

Nếu cả hai đọc version 7 rồi ghi đè toàn bộ mảng, người ghi sau có thể làm mất thay đổi người ghi trước. Một cách phổ biến là **optimistic concurrency control** với field `version`.

### 11.1. Cập nhật toàn bộ dãy có điều kiện

~~~javascript
const result = lab.courses.updateOne(
  {
    _id: "course-01",
    version: 7
  },
  {
    $set: {
      lessonIds: [
        "lesson-query",
        "lesson-intro",
        "lesson-index"
      ]
    },
    $inc: {
      version: 1
    }
  }
);

if (result.matchedCount === 0) {
  print("Conflict: reload course before retrying.");
}
~~~

Ví dụ giả định document đang ở version 7; dữ liệu seed đầu bài có version 1, nên muốn chạy nguyên lệnh này phải điều chỉnh version theo trạng thái đang có. Điểm quan trọng là **điều kiện version**, không phải con số cụ thể.

Khi Editor 1 cập nhật thành công version 7 → 8, thao tác của Editor 2 dựa trên version 7 không khớp. Ứng dụng cần **tải lại thứ tự hiện tại**, cho người dùng xử lý xung đột hoặc áp dụng một chiến lược merge nghiệp vụ rõ ràng. Không nên âm thầm ghi đè.

### 11.2. Thứ tự được mô hình hóa bằng field position

Khi số phần tử lớn hoặc mỗi bài học là một document độc lập, có thể lưu:

~~~json
{
  "_id": "course-01|lesson-index",
  "courseId": "course-01",
  "lessonId": "lesson-index",
  "position": 200
}
~~~

Dữ liệu sắp bằng `position ASC`, rồi `lessonId ASC` làm khóa phụ nếu position trùng.

Ưu điểm: có thể cập nhật vị trí của từng phần tử mà không phải ghi lại cả mảng lớn. Đổi lại:

- Cần xử lý **va chạm position** khi hai người thêm vào cùng chỗ.
- Nếu dùng số thứ tự 100, 200, 300 để chừa khoảng trống, sớm muộn có thể phải **đánh số lại**.
- Nếu vị trí cần liên tục 1, 2, 3, việc chèn ở đầu có thể dẫn tới cập nhật nhiều bản ghi.
- Thay vị trí của nhiều bài là thao tác **nhiều document**, không mặc nhiên có tính nguyên tử như sửa một mảng trong một document.
- Cần keyset pagination với thứ tự toàn phần như `(position, lessonId)`.

Đừng dùng `updatedAt` hoặc thứ tự vật lý trong storage để suy ra thứ tự biên tập, vì chúng đo thứ khác.

### 11.3. Fractional indexing và rủi ro precision

Một chiến lược khác là cấp khóa thứ tự nằm giữa hai phần tử:

~~~text
A: 100
B: 200

Chèn X vào giữa:
A: 100
X: 150
B: 200
~~~

Nếu liên tục chèn vào khoảng rất nhỏ, độ chính xác của số dấu phẩy động và va chạm khóa có thể trở thành vấn đề. Các thuật toán **fractional indexing**, **lexicographic order keys** hoặc cấu trúc CRDT cho danh sách cộng tác có thể giải quyết những tình huống phức tạp hơn, nhưng cần cơ chế điều phối, khử trùng và chuẩn hóa thứ tự phù hợp.

Trong nhiều ứng dụng nhỏ, **mảng ID có version** là đủ đơn giản và đáng tin cậy hơn một hệ thống sắp xếp phân tán phức tạp.

## 12. Redis: List, Set và Sorted Set là ba kiểu dữ liệu khác nhau

Redis cung cấp các cấu trúc được quản lý tại key. Chúng không phải collection tài liệu như MongoDB.

### 12.1. Redis List: có thứ tự, có thể trùng

~~~redis
RPUSH course:01:lessons lesson-intro lesson-index lesson-query
LRANGE course:01:lessons 0 -1
~~~

`RPUSH` thêm vào cuối danh sách. `LRANGE 0 -1` đọc toàn bộ phần tử theo thứ tự hiện tại. Redis List thích hợp với danh sách cần thứ tự ở cấp key, nhưng không được mặc định đây là giải pháp tối ưu cho mọi thao tác sửa ngẫu nhiên giữa danh sách dài.

~~~redis
LPUSH notifications:u01 alert-3
LRANGE notifications:u01 0 9
~~~

`LPUSH` thêm vào đầu, nên danh sách dạng “mới nhất trước” có thể thuận tiện cho một số bài toán. Tuy nhiên, lặp lại cùng lệnh `LPUSH` sẽ tạo mục trùng; cần cơ chế idempotency nếu nghiệp vụ không cho phép trùng thông báo.

### 12.2. Redis Set: thành viên duy nhất, không có insertion order

~~~redis
SADD course:01:tags java nosql database
SADD course:01:tags java
SISMEMBER course:01:tags java
SMEMBERS course:01:tags
SCARD course:01:tags
~~~

- `SADD` thêm thành viên mới, không tạo bản sao khi thêm giá trị đã có.
- `SISMEMBER` kiểm tra membership.
- `SMEMBERS` đọc tập thành viên **không có thứ tự được bảo đảm**.
- `SCARD` cho biết số thành viên duy nhất.

Không nên lấy thứ tự của `SMEMBERS` để xếp thứ tự bài học. Muốn hiển thị tags theo chữ, application có thể sort sau khi đọc; đó là thứ tự hiển thị được tính ra, **không phải thứ tự lưu/chèn** của set.

### 12.3. Redis Sorted Set: thành viên duy nhất, sắp theo score

~~~redis
ZADD leaderboard:course-01 150 usr-an 280 usr-mai 220 usr-binh

ZRANGE leaderboard:course-01 0 -1 WITHSCORES

ZREVRANGE leaderboard:course-01 0 2 WITHSCORES
~~~

`ZADD` gắn score với mỗi member. Khi cùng member được thêm với score mới, nó sẽ cập nhật score theo cú pháp mặc định, không tạo hai bản sao độc lập của member đó.

Redis Sorted Set hỗ trợ xếp hạng theo score; khi score bằng nhau, thứ tự giữa các member được xác định theo quy tắc của Redis, **không phải thứ tự người dùng nhấp hoặc thứ tự request đến**. Nếu ứng dụng muốn tie-breaker nghiệp vụ khác, cần thiết kế dữ liệu và điều kiện sắp xếp riêng.

### 12.4. Redis Stream không đồng nghĩa List

Redis Streams giữ các entry mang ID có cấu trúc phù hợp cho nhật ký/sự kiện và mô hình consumer; đó là mục đích khác với một List được sửa tùy ý. Không nên dùng “cấu trúc có thứ tự” như lý do để coi **List**, **Stream**, và **Sorted Set** là ba tên gọi của cùng một kiểu.

## 13. Cassandra CQL: list, set và map ở cấp cột

Trong mô hình wide-column dùng CQL, một cột có thể mang kiểu collection như `list<T>`, `set<T>` hoặc `map<K,V>`. Ví dụ minh họa:

~~~sql
CREATE TABLE course_metadata (
    course_id text PRIMARY KEY,
    lesson_ids list<text>,
    tags set<text>,
    preferences map<text, text>
);
~~~

Chèn một record:

~~~sql
INSERT INTO course_metadata (
    course_id, lesson_ids, tags, preferences
) VALUES (
    'course-01',
    ['lesson-intro', 'lesson-index', 'lesson-query'],
    {'java', 'nosql'},
    {'language': 'vi', 'theme': 'dark'}
);
~~~

Các trường có ý nghĩa khác nhau:

- `lesson_ids list<text>`: **có thứ tự**, có thể có phần tử trùng theo ngữ nghĩa list.
- `tags set<text>`: **không trùng phần tử** và không biểu diễn insertion order của người dùng.
- `preferences map<text, text>`: truy cập giá trị theo key.

### 13.1. Cập nhật collection trong CQL

Một số thao tác biểu diễn ý tưởng:

~~~sql
UPDATE course_metadata
SET lesson_ids = lesson_ids + ['lesson-review']
WHERE course_id = 'course-01';

UPDATE course_metadata
SET tags = tags + {'redis'}
WHERE course_id = 'course-01';

UPDATE course_metadata
SET tags = tags - {'nosql'}
WHERE course_id = 'course-01';
~~~

Ngữ nghĩa hiệu năng, thứ tự đồng thời, kích thước tối đa được khuyến nghị và các hạn chế về cập nhật collection trong Cassandra phụ thuộc version và cấu trúc cụ thể. Không nên dùng CQL list để lưu **nhật ký sự kiện không giới hạn** chỉ vì list có thể chứa nhiều phần tử.

Với một dãy rất dài có khả năng mở rộng thường xuyên, hãy cân nhắc **mỗi phần tử thành một row** được phân vùng theo khóa hợp lý và sắp bằng clustering columns, thay vì một collection-value lớn trong một row. Khi đó thứ tự truy vấn phụ thuộc thiết kế clustering và điều kiện đọc chứ không phải vị trí phần tử trong list.

### 13.2. Không nhầm set với “sort theo thứ tự chèn”

Một hệ có thể lưu/đọc thành viên set theo **thứ tự so sánh giá trị** trong một số thao tác, nhưng **set vẫn không bảo đảm thứ tự được thêm vào**. Nếu bài học cần thứ tự do biên tập viên chọn, hãy lưu rõ sequence/position.

Cũng cần phân biệt **CQL collection value** với **table**: set ở một cột không phải bảng con có thể query/paginate độc lập giống hàng triệu row.

## 14. DynamoDB: List và Set có ngữ nghĩa riêng

DynamoDB có các kiểu thuộc tính như:

- **L (List):** danh sách có thứ tự, phần tử có thể khác kiểu.
- **M (Map):** thuộc tính con theo tên.
- **SS (String Set), NS (Number Set), BS (Binary Set):** tập hợp các giá trị cùng nhóm kiểu được hỗ trợ; không bảo đảm thứ tự và không có phần tử trùng theo ngữ nghĩa set.

Biểu diễn kiểu DynamoDB JSON cho một item minh họa:

~~~json
{
  "PK": { "S": "COURSE#01" },
  "SK": { "S": "META" },
  "lessonIds": {
    "L": [
      { "S": "lesson-intro" },
      { "S": "lesson-index" },
      { "S": "lesson-query" }
    ]
  },
  "tags": {
    "SS": ["java", "nosql"]
  },
  "preferences": {
    "M": {
      "language": { "S": "vi" },
      "theme": { "S": "dark" }
    }
  }
}
~~~

Đây là **biểu diễn wire-format có chú thích kiểu**, không phải JSON thông thường của ứng dụng. Trong SDK, kiểu dữ liệu có thể được chuyển đổi qua object/list phù hợp, nhưng ý nghĩa storage vẫn phải được hiểu rõ.

Những điểm cần nhớ:

1. **Set không duy trì thứ tự**; thứ tự của các phần tử trong `SS` khi giao tiếp qua JSON không được dùng làm thứ tự nghiệp vụ.
2. Set của DynamoDB không nhận **empty set** như một giá trị set hợp lệ, mặc dù List/Map có thể rỗng theo quy tắc của dịch vụ.
3. DynamoDB có các thao tác `ADD`/`DELETE` thích hợp cho tập hợp trong một số trường hợp, và có cách cập nhật list như `list_append`. Không nên tưởng hai kiểu hỗ trợ cùng mọi thao tác.
4. Một thuộc tính List được sắp theo vị trí, nhưng **thay đổi chỉ số** dưới nhiều writer cần điều kiện/version hoặc cơ chế tránh ghi đè.
5. Item có giới hạn kích thước; một list hoặc map tăng liên tục có thể khiến mô hình không mở rộng được.

Trong DynamoDB, thiết kế query quan trọng thường nằm ở **partition key, sort key và chỉ mục phụ**. Một thuộc tính List/Set **không tự cho phép truy vấn hiệu quả tất cả item theo từng phần tử trong list**, trừ khi có đường index hoặc cấu trúc dữ liệu phù hợp.

## 15. Duy nhất trong phạm vi nào?

Cần phân biệt **duy nhất giữa các phần tử của một field** và **duy nhất giữa nhiều document/row**.

Giả sử có hai khóa học:

~~~json
{
  "_id": "course-a",
  "tags": ["java", "nosql"]
}
~~~

~~~json
{
  "_id": "course-b",
  "tags": ["java", "database"]
}
~~~

Trong mỗi khóa học, tags không trùng. Nhưng tag `"java"` có thể xuất hiện ở **nhiều khóa học**; đây không phải dữ liệu trùng cần xóa. Phạm vi duy nhất là **trong một tập tags của một course**, không phải toàn collection.

Trái lại, nếu yêu cầu “mỗi user chỉ đăng ký một lần vào một course”, có thể cần ràng buộc duy nhất trên cặp:

~~~text
(userId, courseId)
~~~

Một collection riêng sẽ thể hiện tự nhiên hơn:

~~~json
{
  "_id": "course-01|usr-007",
  "courseId": "course-01",
  "userId": "usr-007",
  "enrolledAt": "2026-11-14T08:00:00Z"
}
~~~

**Không nên mặc định unique index trên một trường mảng bảo đảm không có giá trị lặp trong chính mảng đó.** Trong MongoDB, unique multikey index chủ yếu áp đặt ràng buộc giữa các document đối với key được index; các giá trị trùng xuất hiện trong một mảng của **cùng document** không bị loại bỏ theo cách người mới học thường tưởng.

Muốn ràng buộc một tag xuất hiện tối đa một lần trong cùng course, có thể dùng thao tác cập nhật có điều kiện, chuẩn hóa input, validation và quy trình xử lý dữ liệu cũ; hoặc chuyển thành những document riêng có khóa duy nhất `(courseId, tag)`.

## 16. Khi nào mảng nhúng không còn phù hợp?

Một mảng nhỏ được đọc cùng document cha là tiện lợi, nhưng không phải mọi quan hệ một–nhiều đều nên nhúng.

### Ví dụ tăng trưởng

Giả sử mỗi user có:

- 5–20 thẻ kỹ năng.
- 10 bài học yêu thích.
- 500.000 sự kiện hoạt động.
- 100.000 thông báo.
- Một danh sách 50 bước workflow do người dùng sắp xếp.

Không nên dùng cùng một cấu trúc cho tất cả.

| Dữ liệu | Cấu trúc thường đáng cân nhắc | Lý do |
| --- | --- | --- |
| Thẻ kỹ năng | Set hoặc mảng nhỏ được quản lý như set | Ít phần tử, membership quan trọng |
| Bài học yêu thích | Set ID nhỏ hoặc collection liên kết riêng | Cần duy nhất, có thể cần truy vấn độc lập |
| Sự kiện hoạt động | Nhiều row/document với khóa thời gian | Tăng liên tục; cần phân trang, retention và index |
| Thông báo | Collection riêng hoặc chỉ giữ cửa sổ nhỏ trong document | Có nhiều trạng thái đọc/chưa đọc và số lượng tăng |
| Bước workflow | Mảng có thứ tự + version hoặc row có `position` | Thứ tự là dữ liệu nghiệp vụ |

Nếu một mảng tăng không giới hạn, các vấn đề dễ xuất hiện:

1. **Giới hạn kích thước document/item** của sản phẩm.
2. **Chi phí đọc** khi chỉ cần vài phần tử nhưng payload lớn.
3. **Chi phí cập nhật** và tranh chấp trên một document rất “nóng”.
4. **Khó phân trang** và truy vấn từng phần tử độc lập.
5. **Khó đặt quyền/TTL/index riêng** cho từng phần tử.
6. **Khó chia phân vùng** khi mọi phần tử bị gắn vào một khóa cha.

Ví dụ MongoDB có giới hạn kích thước BSON document (thường 16 MiB cho một document), còn DynamoDB có giới hạn kích thước item riêng. **Không dùng giới hạn tối đa làm mục tiêu thiết kế**; một document chưa chạm giới hạn vẫn có thể không phù hợp với workload.

## 17. Mô hình lại quan hệ lớn bằng collection liên kết

Thay vì nhúng toàn bộ những user theo dõi một course:

~~~json
{
  "_id": "course-01",
  "followerIds": [
    "... hàng trăm nghìn ID ..."
  ]
}
~~~

có thể lưu một record cho mỗi quan hệ:

~~~json
{
  "_id": "course-01|usr-007",
  "courseId": "course-01",
  "userId": "usr-007",
  "followedAt": "2026-11-14T08:00:00Z"
}
~~~

Nếu muốn liệt kê người theo dõi mới nhất:

~~~javascript
// Collection riêng cho quan hệ theo dõi:
lab.course_follows.createIndex({
  courseId: 1,
  followedAt: -1,
  _id: -1
});

lab.course_follows.find({
  courseId: "course-01"
})
  .sort({ followedAt: -1, _id: -1 })
  .limit(20)
  .toArray();
~~~

Ở đây thứ tự được xác định bởi **`followedAt` rồi `_id`**, không phải vị trí trong mảng. Có thể phân trang theo cặp khóa sắp xếp nếu dữ liệu lớn.

Lưu ý rằng ví dụ collection `course_follows` chưa được seed trong phần thực hành ban đầu. Đoạn lệnh minh họa cách thiết kế index và truy vấn khi chọn mô hình quan hệ riêng, không ngụ ý đã có dữ liệu để trả về.

### 17.1. Một user có thể xuất hiện hai lần không?

Nếu ràng buộc `(courseId, userId)` là duy nhất, dùng khóa item ổn định hoặc unique index (trong phạm vi hỗ trợ). Nếu nghiệp vụ cho phép user **hủy theo dõi rồi theo dõi lại**, cần quyết định:

- Một quan hệ hiện hành duy nhất, cập nhật `followedAt` khi theo dõi lại?
- Hay cần lưu **lịch sử từng lần** theo dõi/bỏ theo dõi thành nhiều sự kiện có `eventId` riêng?

Đây là sự khác biệt giữa **set trạng thái hiện tại** và **log sự kiện có thứ tự**, không chỉ khác cách lưu JSON.

## 18. Schema validation cho các trường collection

Một schema linh hoạt vẫn cần đặt ra quy tắc dữ liệu.

Giả sử hợp đồng khóa học yêu cầu:

~~~text
courseId:
  bắt buộc, định danh ổn định

lessonIds:
  list các chuỗi ID
  có thứ tự
  mỗi lessonId tối đa một lần (theo hợp đồng ứng dụng)
  tối đa 200 phần tử trong mô hình nhúng hiện tại

tags:
  tập tag được chuẩn hóa
  không trùng theo quy tắc so sánh đã thống nhất
  tối đa 30 thành viên
  thứ tự không có ý nghĩa

preferences:
  map nhỏ có các key được phép
  chỉ chứa kiểu dữ liệu đã định nghĩa
~~~

Một số ràng buộc có thể đặt trong **database schema validator**; một số cần xử lý ở application, đặc biệt ràng buộc **tập các ID không trùng** và tính hợp lệ của thứ tự nghiệp vụ.

### 18.1. Ràng buộc về kiểu

Với mảng `lessonIds`, có thể yêu cầu:

- Field là **array**.
- Mọi phần tử là **string**.
- Không có chuỗi rỗng.
- Số lượng phần tử trong ngưỡng.
- Không có ID trùng nếu nghiệp vụ yêu cầu.
- Những ID tham chiếu phải trỏ tới bài học tồn tại và user có quyền xem.

Database có thể kiểm tra kiểu và độ dài cơ bản; điều kiện “tất cả ID đều tồn tại ở collection khác” thường cần cơ chế ứng dụng hoặc giao dịch riêng. Không nên suy rằng việc lưu mảng ID tự tạo **foreign key**.

### 18.2. Ràng buộc về thứ tự

Một mảng có thứ tự không tự bảo đảm **đúng logic chương trình học**. Ví dụ, bài nâng cao có thể phải xuất hiện sau bài nền tảng. Đây là một ràng buộc cấp nghiệp vụ:

~~~text
lesson-prerequisite phải đứng trước lesson-advanced
~~~

Cần xác định dữ liệu prerequisite và thuật toán kiểm tra quan hệ phụ thuộc. Thứ tự array chỉ thể hiện quyết định hiện tại, không tự chứng minh thứ tự đó hợp lệ.

### 18.3. Chuyển schema từ list sang set

Giả sử hệ cũ lưu:

~~~json
["Java", "java", "NoSQL", "nosql"]
~~~

Sau khi thống nhất tags không phân biệt hoa/thường, muốn chuyển thành một tập có các giá trị chuẩn:

~~~json
["java", "nosql"]
~~~

Migration phải:

1. Công bố chính sách normalize.
2. Chạy phép biến đổi có thể lặp lại (*idempotent*).
3. Xử lý trường hợp dữ liệu null, field thiếu hoặc kiểu sai.
4. Đồng bộ writer mới để không tạo lại dạng cũ.
5. Đối chiếu số trường hợp trùng/khác biệt sau chuyển đổi.
6. Nếu đổi sang native set của database, lưu ý **mất thứ tự** là hành vi chủ động.

Không nên chuyển một danh sách bài học có thứ tự sang set chỉ vì muốn xóa trùng: nó sẽ làm mất thông tin thứ tự quan trọng.

## 19. Tính nguyên tử và idempotency của thao tác collection

Một số thao tác thay đổi collection-value nằm **trong một document/item**. Trong MongoDB, cập nhật một document có tính nguyên tử. Nhưng điều đó không tự bảo đảm toàn bộ nghiệp vụ đúng.

### 19.1. Hai kiểu thao tác khác nhau khi retry

**Thao tác idempotent về giá trị:**

~~~text
Thêm tag "java" vào set
Chạy lại nhiều lần → "java" vẫn chỉ xuất hiện một lần
~~~

**Thao tác không idempotent mặc định:**

~~~text
Thêm "lesson-a" vào cuối list
Chạy lại hai lần → ["lesson-a", "lesson-a"] có thể xuất hiện
~~~

Nếu hệ gửi lại request do timeout, cần phân biệt:

- **Đặt trạng thái đích:** “lessonIds phải bằng dãy X” kèm version.
- **Thực hiện hành động:** “thêm bài học X vào vị trí Y” với mã thao tác duy nhất.
- **Bảo vệ ràng buộc:** “nếu X chưa tồn tại thì mới thêm”, có tính tới ghi đồng thời.
- **Cập nhật tập:** set membership thường thuận lợi cho thao tác thêm/xóa lặp lại, nhưng phải kiểm tra đúng ngữ nghĩa của sản phẩm.

### 19.2. Duy nhất theo phần tử không giải quyết race đa document

Nếu bảng đăng ký là collection riêng, hai request có thể cùng kiểm tra “chưa đăng ký” rồi cùng tạo document. Một lần check trước khi ghi không đủ. Cần **khóa duy nhất** hoặc conditional insert trong database để bảo vệ bất biến `(courseId, userId)`.

Tương tự, nếu một phần tử ở collection riêng có field `position`, hai writer có thể cùng chọn vị trí 200. Hệ cần ràng buộc/transaction hoặc cách xử lý va chạm phù hợp, không chỉ sắp xếp ở client.

## 20. Chỉ mục và truy vấn trên mảng/tập hợp

Một trường chứa nhiều phần tử có thể cần truy vấn kiểu “chứa giá trị này”. Trong MongoDB:

~~~javascript
lab.courses.createIndex({ tags: 1 });

lab.courses.find({
  tags: "java"
});
~~~

Khi chỉ mục đặt trên trường mảng, MongoDB có thể dùng **multikey index**. Đây là đường truy cập phục vụ truy vấn membership; nó không biến dữ liệu thành native Set và không tự loại duplicate trong một document.

Các câu hỏi cần tách:

| Câu hỏi | Ngữ nghĩa | Ví dụ truy vấn |
| --- | --- | --- |
| Có phần tử “java”? | Membership | `{tags: "java"}` |
| Có cả “java” và “nosql”? | Set inclusion | `{tags: {$all: ["java","nosql"]}}` |
| Mảng có đúng 3 phần tử? | Sequence length | `{tags: {$size: 3}}` |
| Toàn bộ dãy bằng [A,B,C]? | Equality có thứ tự | `{lessonIds: ["A","B","C"]}` |
| Có cùng một bài học đã publish và dài ≥20 phút? | Predicate trên **cùng phần tử** | `$elemMatch` |
| Thẻ nằm ở vị trí số 1? | Chỉ số phần tử | Truy cập theo index nếu schema thực sự cần |

Nếu ứng dụng thường hỏi “khóa học nào có tag X?” trên hàng triệu khóa học, index mảng có thể phù hợp. Nhưng nếu cần nhiều truy vấn phân tích phức tạp trên từng tag, tần suất cập nhật rất cao hoặc dữ liệu cực lớn, một collection liên kết `(tag, courseId)` có thể thuận tiện hơn.

**Hiệu năng membership của Set trong bộ nhớ** thường khác **chi phí truy vấn theo mảng trong database**. Không nên lấy độ phức tạp thao tác `HashSet.contains` rồi suy rằng mọi truy vấn `tags = X` trong MongoDB là O(1); thực tế còn có index, kích thước dữ liệu, phân bố và I/O.

## 21. Tương tác với ứng dụng Java: List và Set không tự bảo đảm schema

Java có những interface phổ biến:

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class CollectionSemantics {
    public static void main(String[] args) {
        List<String> lessons = new ArrayList<>();
        lessons.add("intro");
        lessons.add("query");
        lessons.add("intro");
        System.out.println(lessons); // [intro, query, intro]

        Set<String> tags = new HashSet<>();
        tags.add("java");
        tags.add("nosql");
        tags.add("java");
        System.out.println(tags.size()); // 2

        Set<String> orderedTags = new LinkedHashSet<>();
        orderedTags.add("java");
        orderedTags.add("nosql");
        System.out.println(orderedTags); // [java, nosql]
    }
}
~~~

Ý nghĩa:

- `List` bảo toàn vị trí phần tử và có thể chứa trùng.
- `HashSet` loại giá trị trùng theo `equals`/`hashCode` nhưng **không bảo đảm thứ tự duyệt**.
- `LinkedHashSet` duy trì **thứ tự chèn khi ở trong Java**, nhưng nếu lưu sang **native Set không thứ tự** của database, không nên kỳ vọng thứ tự đó tồn tại sau khi đọc lại.

Khi chuyển đổi giữa Java object và database:

1. Chọn trường DB đúng ngữ nghĩa: BSON array, Redis Set, DynamoDB SS, Cassandra set, v.v.
2. Kiểm tra serializer/mapper có giữ **kiểu và thứ tự** theo hợp đồng không.
3. Xác nhận cách so sánh phần tử khi đọc/ghi (chuỗi, số, object).
4. Xác định hành vi với null/empty/missing.
5. Không để chi tiết implementation collection ở application thay thế **ràng buộc lưu trữ**.

Một API nhận `List<String>` không chứng minh các phần tử trong database sẽ không trùng. Và một field Redis Set không thể được dùng để tái tạo trình tự người dùng đã chọn chỉ vì Java client trả một danh sách kết quả.

## 22. Lựa chọn cấu trúc bằng bảng quyết định

| Yêu cầu nghiệp vụ | Cấu trúc ban đầu đáng chọn | Lý do |
| --- | --- | --- |
| Khóa học có 12 bài cần đúng thứ tự | **Array/list** các lessonId | Thứ tự là một phần của dữ liệu |
| Một bài nhạc có thể lặp trong playlist | **List** cho phép trùng | Lặp là hành vi có chủ đích |
| Tag của khóa học không được trùng | **Set**, hoặc array được quản lý như set | Membership và duy nhất quan trọng hơn vị trí |
| Bảng xếp hạng theo điểm | **Sorted Set** hoặc bảng có score và sort | Thứ tự theo score, cần tie-breaker |
| Cài đặt theo tên thuộc tính | **Map/object** | Truy cập bằng khóa |
| 500.000 bình luận của một bài | **Collection/row riêng** | Phân trang, tăng trưởng và cập nhật độc lập |
| Lịch sử sự kiện cần biết thứ tự thời gian | **Nhiều event record** với timestamp + ID | Thứ tự bền vững, phân trang/retention |
| Danh sách quyền người dùng | **Set hoặc liên kết riêng có ràng buộc** | Duy nhất; kiểm tra quyền không dựa thứ tự |
| Người tham gia khóa học có lịch sử tham gia/rời | **Event log + trạng thái hiện tại** | Set hiện tại không thể thay thế lịch sử |
| Quy trình có nhiều editor sửa thứ tự cùng lúc | **Ordered list + version** hoặc item có order key | Tránh lost update và biểu diễn xung đột |

Quyết định nên căn cứ vào **kích thước tối đa, số lần đọc/ghi, kiểu truy vấn, quyền, vòng đời và tính nhất quán** — không chỉ vì kiểu dữ liệu nào có cú pháp ngắn hơn.

## 23. Những lỗi thiết kế thường gặp

### 23.1. Dùng set để lưu thứ tự người dùng chọn

Một giao diện kéo thả sắp lại bài học, nhưng backend lưu trong Redis Set. Lần đọc khác có thể không cùng thứ tự. Giải pháp: **List, Sorted Set với order key, hoặc records có position** theo hợp đồng.

### 23.2. Dùng list cho những phần tử đáng ra phải duy nhất

Request “thêm tag” được gửi lại sau timeout và `$push` tạo `["java", "java"]`. Giải pháp: chuẩn hóa tag, dùng `$addToSet` hoặc native set/khóa duy nhất phù hợp, có cơ chế xử lý dữ liệu trùng đã tồn tại.

### 23.3. Giả định thứ tự document là ổn định

Truy vấn `find({status:"PUBLISHED"})` không có sort rồi hiển thị theo thứ tự database trả về. Kết quả có thể thay đổi khi index/plan/dữ liệu thay đổi. Giải pháp: **sort tường minh** theo field nghiệp vụ và khóa phụ.

### 23.4. Dùng chỉ số mảng như ID của phần tử

Client gửi “sửa bài thứ 2”, nhưng một editor đã chèn bài ở đầu. Lệnh sửa theo index tác động sai phần tử. Giải pháp: dùng `lessonId` ổn định, còn index chỉ phục vụ thao tác hiển thị/reorder.

### 23.5. Tạo một mảng tăng vô hạn

Nhúng toàn bộ đơn hàng và lịch sử vào document của user. Khi dữ liệu lớn, mọi thao tác đọc/ghi đều chịu ảnh hưởng; có thể chạm giới hạn lưu trữ. Giải pháp: tách record độc lập với khóa truy vấn và phân trang.

### 23.6. Tin rằng JSON object có “thứ tự khóa”

Dùng thứ tự các key trong `preferences` để quyết định bước workflow. Giải pháp: danh sách có thứ tự hoặc field `position`; object/map chỉ nên thể hiện ánh xạ theo tên key nếu không có hợp đồng khác.

### 23.7. Không định nghĩa null/missing/empty

Ứng dụng mới cho `tags: []`, dữ liệu cũ thiếu `tags`, truy vấn xử lý không thống nhất. Giải pháp: hợp đồng schema rõ ràng và quá trình migration/compatibility khi cần.

### 23.8. Tưởng unique index giải quyết duplicate nội bộ của array

Unique multikey index không phải phép “xóa trùng trong mảng của một document”. Giải pháp: validator/toán tử cập nhật/chuyển dữ liệu hoặc mô hình quan hệ riêng có khóa duy nhất đúng phạm vi.

### 23.9. Chuyển native set sang list khi truyền API rồi phụ thuộc thứ tự tình cờ

Ứng dụng nhận `SS` hoặc Redis Set và render theo thứ tự trả về. Thứ tự có thể không ổn định; API cần sort theo tiêu chí rõ ràng nếu thứ tự hiển thị cần xác định.

### 23.10. Sửa toàn bộ mảng mà không kiểm tra version

Hai người cùng kéo thả, lần ghi sau đè thứ tự của lần ghi trước. Giải pháp: optimistic concurrency, quy tắc xử lý conflict hoặc cấu trúc hỗ trợ cộng tác theo yêu cầu.

## 24. Bài tập thực hành

### Bài 1: chọn kiểu dữ liệu

Chọn **list, set, sorted set, map hoặc record riêng** cho từng tình huống:

1. Các bài học do giáo viên kéo thả sắp xếp.
2. Tập vai trò `ADMIN`, `EDITOR` của một tài khoản.
3. Bảng xếp hạng học viên theo số điểm.
4. Một triệu bản ghi truy cập của khóa học.
5. Các tùy chọn `language`, `theme`, `timezone`.

**Gợi ý:** (1) list/ordered records; (2) set; (3) sorted set hoặc records có score; (4) records riêng; (5) map.

### Bài 2: phân biệt list với set

Cho hai dãy:

~~~text
A = ["a", "b", "a"]
B = ["b", "a"]
~~~

Nếu coi chúng là **list**, có bằng nhau không? Nếu chỉ xem tập thành viên duy nhất, có cùng thành viên không?

**Gợi ý:** Không bằng nhau như list vì khác số lần xuất hiện và thứ tự. Cùng tập thành viên phân biệt là `{a,b}`.

### Bài 3: thứ tự MongoDB

Một tài liệu có `lessonIds = ["A", "B", "C"]`. Thêm `"X"` vào vị trí 0 bằng toán tử nào? Thứ tự mới ra sao?

**Gợi ý:**

~~~javascript
db.courses.updateOne(
  { _id: "course-01" },
  {
    $push: {
      lessonIds: {
        $each: ["X"],
        $position: 0
      }
    }
  }
);
~~~

Dãy mới theo ý nghĩa ví dụ là `["X", "A", "B", "C"]` nếu không có cập nhật cạnh tranh.

### Bài 4: addToSet có dọn trùng sẵn không?

Nếu `tags = ["java", "java", "nosql"]` và gọi:

~~~javascript
db.courses.updateOne(
  { _id: "course-01" },
  { $addToSet: { tags: "java" } }
);
~~~

mảng sẽ tự trở thành `["java","nosql"]` không?

**Gợi ý:** **Không.** `$addToSet` không bổ sung thêm giá trị đã có, nhưng không chủ động loại duplicate cũ. Cần kế hoạch làm sạch dữ liệu nếu muốn đạt ràng buộc không trùng.

### Bài 5: điều kiện trong cùng phần tử

Mảng:

~~~json
[
  { "id": "l1", "published": true, "minutes": 10 },
  { "id": "l2", "published": false, "minutes": 30 }
]
~~~

Tìm một lesson vừa `published = true` vừa `minutes >= 20`. Vì sao không nên dùng hai field path độc lập?

**Gợi ý:** Vì chúng có thể khớp trên hai object khác nhau. Dùng `$elemMatch` với cả hai điều kiện trên cùng một phần tử.

### Bài 6: ứng dụng Java và Redis

Java sử dụng `LinkedHashSet<String>` và hiển thị tags theo thứ tự thêm. Sau khi lưu sang Redis Set rồi đọc bằng `SMEMBERS`, có được kỳ vọng thứ tự chèn vẫn giữ nguyên không?

**Gợi ý:** Không. Thứ tự của LinkedHashSet là chi tiết trong Java; Redis Set không có insertion-order guarantee. Muốn trình tự cố định, dùng List hoặc một quy tắc sắp xếp rõ ràng.

### Bài 7: xử lý ghi đồng thời

Editor A và B cùng tải một mảng bài học ở version 3. A ghi thành công và tăng version thành 4. B vẫn gửi ghi với điều kiện version 3. Ứng dụng nên làm gì khi update của B không khớp?

**Gợi ý:** Báo conflict, tải lại version 4, cho phép xử lý hợp nhất hoặc thao tác lại; không âm thầm ghi đè toàn bộ mảng mới.

### Bài 8: native set và empty collection

DynamoDB item có `tags` kiểu String Set. Người dùng xóa tag cuối cùng. Có thể mặc định lưu `SS: []` làm empty set hợp lệ không?

**Gợi ý:** Không. DynamoDB không hỗ trợ empty set; cần dùng biểu diễn được chấp nhận như loại bỏ field hoặc thay thiết kế, đồng thời giữ ngữ nghĩa empty/missing theo hợp đồng.

### Bài 9: thiết kế dữ liệu lớn

Một ứng dụng có khóa học với 500.000 người theo dõi, cần truy vấn 20 người theo dõi mới nhất, xóa quan hệ theo ID và phân trang sâu. Nhúng mọi follower ID vào array của document khóa học có phù hợp không?

**Gợi ý:** Không phù hợp với yêu cầu tăng trưởng và truy vấn độc lập. Tạo collection quan hệ với khóa `(courseId,userId)` cùng chỉ mục theo `courseId, followedAt, ID` thường là hướng đáng cân nhắc.

### Bài 10: mô hình hybrid

Khóa học có nội dung bài học lưu riêng, nhưng cần hiển thị đúng thứ tự các bài. Hãy thiết kế tài liệu khóa học và tài liệu bài học.

**Một phương án:**

~~~json
{
  "_id": "course-01",
  "lessonIds": ["l1", "l3", "l2"],
  "version": 5
}
~~~

~~~json
{
  "_id": "l3",
  "courseId": "course-01",
  "title": "Truy vấn dữ liệu",
  "contentRef": "content-l3"
}
~~~

Ứng dụng đọc `lessonIds` để lấy thứ tự rồi tải nội dung bài từ collection `lessons`. **Không tin kết quả `$in` tự bảo toàn thứ tự của mảng IDs**; khi hydrate, phải sắp lại theo `lessonIds`. Nếu mỗi course có rất nhiều bài, cần xem xét lưu `position` ở từng record và truy vấn/pagination theo position.

## 25. Tóm kết cách chọn cấu trúc đúng

Khi gặp một field chứa nhiều phần tử trong NoSQL, đừng chỉ hỏi “có thể lưu array JSON được không?”. Hãy xác định:

- **Đơn vị dữ liệu:** collection chứa nhiều document hay collection-valued field nằm trong một document?
- **Tính duy nhất:** phần tử được phép trùng hay phải duy nhất, và **duy nhất trong phạm vi nào**?
- **Thứ tự:** thứ tự do người dùng chọn, thứ tự chèn, thời gian, score hay không cần thứ tự?
- **Định danh phần tử:** cập nhật theo ID ổn định hay theo vị trí dễ thay đổi?
- **Truy vấn:** cần kiểm tra membership, đọc toàn bộ dãy, tìm trên từng object, hoặc phân trang phần tử riêng?
- **Tăng trưởng và cạnh tranh ghi:** dữ liệu có thể rất lớn, có nhiều writer hoặc yêu cầu cập nhật nguyên tử không?
- **Khả năng của hệ lưu trữ:** BSON array, Redis List/Set/Sorted Set, Cassandra list/set/map và DynamoDB List/Set có những bảo đảm khác nhau.

**List bảo toàn ý nghĩa của trình tự; Set bảo toàn tính duy nhất; Sorted Set gắn thứ tự với tiêu chí xếp hạng; Map truy cập bằng khóa; nhiều record riêng phục vụ dữ liệu lớn hoặc vòng đời độc lập.** Khi chọn đúng cấu trúc, ứng dụng không chỉ lưu được giá trị mà còn giữ được **ngữ nghĩa, truy vấn và tính nhất quán** mà nghiệp vụ yêu cầu.

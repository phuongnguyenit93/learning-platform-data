# Tạo, liệt kê, chọn và xóa database hoặc collection trong MongoDB

MongoDB tổ chức dữ liệu theo cấu trúc **deployment → database → collection → document**. Trước khi viết truy vấn CRUD, người học cần biết đang thao tác trên database nào, collection nào đã tồn tại, cách tạo đối tượng mới và tác động của việc xóa. Đây là nhóm thao tác nền tảng nhưng cũng liên quan trực tiếp đến phân quyền, triển khai và an toàn dữ liệu: một lệnh `dropDatabase()` chạy nhầm ngữ cảnh có thể xóa toàn bộ dữ liệu của ứng dụng.

Bài học sử dụng **mongosh** để minh họa. Ví dụ giả định bạn đã có một MongoDB server có thể truy cập, chạy các lệnh trong một **môi trường lab riêng** và có quyền phù hợp. Không chạy phần xóa trên database đang chứa dữ liệu cần giữ lại.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích quan hệ giữa database, collection và document.
2. **Chọn** database trong mongosh bằng `use` hoặc `db.getSiblingDB()` và hiểu rằng chọn chưa chắc đã tạo.
3. **Tạo** database khi khởi tạo collection hoặc ghi document đầu tiên; tạo collection tường minh qua `db.createCollection()`.
4. **Liệt kê** database và collection bằng lệnh tương tác hoặc API có thể dùng trong script.
5. **Kiểm tra** ngữ cảnh hiện tại, sự tồn tại và metadata của collection trước khi thao tác.
6. **Xóa** một collection hoặc toàn database có chủ đích, hiểu phạm vi dữ liệu bị mất.
7. Phân biệt xóa document với xóa collection, xóa database; xử lý một số lỗi và quyền truy cập thường gặp.

## 2. Mô hình phân cấp: database, collection và document

~~~mermaid
flowchart TD
    Deployment["MongoDB deployment"] --> DB1["Database: training_store"]
    Deployment --> DB2["Database: analytics"]
    DB1 --> C1["Collection: books"]
    DB1 --> C2["Collection: members"]
    DB1 --> C3["Collection: borrow_records"]
    DB2 --> C4["Collection: daily_reports"]
    C1 --> D1["Document {_id, title, ...}"]
    C1 --> D2["Document {_id, title, ...}"]
~~~

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Deployment | Máy chủ standalone, replica set hoặc sharded cluster cung cấp MongoDB | Một MongoDB server cục bộ hoặc cluster đã triển khai |
| Database | Không gian logic chứa các collection; đồng thời là phạm vi phân quyền và quản trị | `training_store` |
| Collection | Tập hợp các document, có thể có validator, index và các tùy chọn lưu trữ riêng | `books` |
| Document | Bản ghi BSON gồm các field; thường chứa `_id` duy nhất trong collection | `{_id: "b-001", title: "MongoDB Basics"}` |

Nếu quen SQL, có thể hình dung database gần giống database, collection gần giống table và document gần giống row. Tuy nhiên MongoDB cho phép cấu trúc document linh hoạt, có array/object lồng nhau và nhiều cơ chế schema validation, index, collection type khác với bảng quan hệ.

**Database có tên không đồng nghĩa với database đã tồn tại vật lý.** MongoDB có thể trả về đối tượng tham chiếu database để bạn viết lệnh, nhưng chưa tạo tài nguyên lưu trữ cho database đó.

### Một ví dụ xuyên suốt

Ta dùng hệ thống quản lý thư viện học tập:

~~~text
training_store (database)
  books (collection)
    {_id: "b-001", title: "MongoDB Basics", year: 2025}
  members (collection)
    {_id: "m-001", name: "Lan"}
  borrow_records (collection)
    {_id: "r-001", bookId: "b-001", memberId: "m-001"}
~~~

`training_store` là tên chỉ dùng trong bài thực hành. Nếu môi trường của bạn đã có database cùng tên, hãy chọn tên lab khác và thay nhất quán trong mọi lệnh.

## 3. Chuẩn bị mongosh và xác nhận nơi đang kết nối

### 3.1. Mở kết nối

Ví dụ máy lab có MongoDB lắng nghe trên loopback:

~~~bash
mongosh "mongodb://127.0.0.1:27017"
~~~

Ở môi trường được quản lý, dùng connection string do người quản trị cấp, cấu hình TLS và xác thực theo hướng dẫn của môi trường. Không đưa mật khẩu vào tài liệu, commit, log hoặc ảnh chụp màn hình. Không mở MongoDB không có xác thực ra Internet chỉ để thực hành.

Trong mongosh:

~~~javascript
// Kiểm tra kết nối tới server.
db.runCommand({ ping: 1 })

// Xem database được chọn trong shell.
db.getName()

// Hiển thị tên host/địa chỉ kết nối theo thông tin shell.
db.getMongo()
~~~

Kết quả của `ping` thành công thường chứa `ok: 1`. Lệnh `db.getName()` chỉ trả tên database trong **ngữ cảnh hiện tại**, chưa chứng minh database đó có dữ liệu hay đã được tạo.

### 3.2. Chỉ thao tác trong database lab

Trước khi chạy ví dụ ghi, xóa hoặc tạo collection, luôn xác nhận:

~~~javascript
db.getName()
~~~

Không suy đoán database hiện tại dựa vào lịch sử lệnh đã chạy trước đó: nhiều shell, nhiều phiên kết nối hoặc nhiều file script có thể chọn những ngữ cảnh khác nhau.

## 4. Chọn database: `use` và `getSiblingDB()`

### 4.1. Dùng lệnh `use` trong mongosh

~~~javascript
use training_store
db.getName()
~~~

Khi đó `db` trong các lệnh mongosh tiếp theo trỏ đến `training_store`:

~~~javascript
// Sau "use training_store":
db.getCollectionNames()
db.books.findOne()
~~~

`use` là **mongosh shell helper**, không phải cú pháp JavaScript thông thường. Bạn gõ `use training_store` trực tiếp tại prompt; không đặt nó trong hàm JavaScript hay dùng như một câu lệnh MongoDB wire protocol.

### 4.2. Dùng `db.getSiblingDB()` trong JavaScript

Khi viết script hoặc muốn làm việc với một database khác mà không phụ thuộc `use`:

~~~javascript
const trainingDb = db.getSiblingDB("training_store")

print(trainingDb.getName())          // training_store
printjson(trainingDb.getCollectionNames())
~~~

Bạn cũng có thể gọi trực tiếp:

~~~javascript
db.getSiblingDB("training_store").books.findOne()
~~~

`getSiblingDB()` trả về handle cho database đích trên cùng kết nối; việc tạo handle **không tự tạo database trên storage**. Đây là cách thuận tiện để script chỉ rõ database mà nó quản lý, tránh phụ thuộc vị trí người chạy shell đang đứng.

### 4.3. Chọn không giống tạo

~~~javascript
use temporary_empty_demo
db.getName()            // "temporary_empty_demo"
show dbs                // Có thể chưa thấy temporary_empty_demo.
show collections        // Chưa có collection.
~~~

Chỉ gõ `use temporary_empty_demo` không làm database xuất hiện trong danh sách. MongoDB thường tạo database thực tế khi có collection được tạo hoặc có dữ liệu ghi lần đầu. Việc liệt kê còn phụ thuộc quyền của tài khoản và tình trạng triển khai.

**Ghi nhớ:** `use` = chọn ngữ cảnh; `createCollection` hoặc một thao tác ghi phù hợp = tạo đối tượng thực sự.

## 5. Tạo database trong MongoDB

Không có một lệnh shell chuyên biệt tương đương `CREATE DATABASE name` theo kiểu SQL thông dụng để tạo database rỗng như đối tượng bền vững. Thay vào đó, bạn **chọn tên** rồi **tạo collection hoặc ghi document**.

### 5.1. Cách 1 — Tạo database bằng collection tường minh

~~~javascript
use training_store

db.createCollection("books")
db.getCollectionNames()
~~~

Nếu database chưa tồn tại, lệnh tạo collection giúp database này hình thành. Collection `books` lúc đó có thể rỗng, nhưng là một collection đã được tạo tường minh.

`db.createCollection(name, options)` hữu ích khi cần tạo collection với option đặc biệt, dù MongoDB có thể tự tạo collection trong những tình huống đơn giản.

### 5.2. Cách 2 — Tạo database/collection ngầm khi ghi document

~~~javascript
use training_store

db.members.insertOne({
  _id: "m-001",
  name: "Lan",
  joinedAt: new Date(),
  active: true
})
~~~

Nếu `members` chưa có, thao tác ghi có thể **tự tạo collection `members`**, đồng thời tạo database `training_store` nếu chưa tồn tại. Sau đó:

~~~javascript
show collections
show dbs
~~~

Lệnh insert với cùng `_id` chạy lại sẽ báo trùng khóa; đừng coi đó là lỗi MongoDB không tạo được collection.

### 5.3. So sánh hai kiểu tạo

| Tiêu chí | `db.createCollection("books")` | `db.books.insertOne({...})` |
|---|---|---|
| Khi nào thực sự tạo collection? | Khi gọi thành công | Khi ghi lần đầu vào tên collection chưa có, nếu thao tác ghi được phép |
| Có cần document ban đầu? | Không | Có |
| Cấu hình collection options khi tạo? | Có | Không truyền collection options thông qua `insertOne` |
| Phù hợp | Khởi tạo schema, validator, capped/time-series hoặc quản lý cấu hình | Collection thông thường, tạo ngầm trong ứng dụng |
| Khi collection đã tồn tại | Thường báo lỗi namespace đã tồn tại | Ghi document mới nếu hợp lệ |

Ở môi trường production, việc tạo collection nên có quy trình thay đổi schema/index/validation rõ ràng; để ứng dụng tự tạo mọi collection từ lỗi đánh máy tên có thể gây khó kiểm soát.

## 6. Tạo collection tường minh và cấu hình ban đầu

### 6.1. Collection thông thường

~~~javascript
use training_store

db.createCollection("borrow_records")

// Liệt kê để xác nhận.
db.getCollectionNames()
~~~

Để viết tên collection linh hoạt, đặc biệt tên có dấu gạch nối:

~~~javascript
db.getCollection("books").findOne()
// Ví dụ collection tên "book-events":
db.getCollection("book-events").findOne()
~~~

Không nên dùng `db.book-events`: JavaScript hiểu dấu gạch nối như phép trừ giữa hai biểu thức, không phải tên collection.

### 6.2. Tạo collection có schema validation

Ví dụ collection `catalog_items` yêu cầu tên, loại tài liệu và thời điểm tạo:

~~~javascript
db.createCollection("catalog_items", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["title", "kind", "createdAt"],
      properties: {
        title: {
          bsonType: "string",
          minLength: 1
        },
        kind: {
          enum: ["BOOK", "MAGAZINE"]
        },
        createdAt: {
          bsonType: "date"
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})
~~~

Ghi dữ liệu hợp lệ:

~~~javascript
db.catalog_items.insertOne({
  _id: "cat-001",
  title: "MongoDB Handbook",
  kind: "BOOK",
  createdAt: new Date()
})
~~~

Ghi thiếu `createdAt` có thể bị validator từ chối nếu sử dụng cấu hình trên. Một **collection có validator không nhất thiết giống mọi collection khác trong cùng database**; mỗi collection mang options phù hợp loại dữ liệu.

Nếu cần thay đổi validator trên collection hiện có, MongoDB cung cấp cơ chế quản trị như `collMod`. Không gọi lại `createCollection` để kỳ vọng nó tự sửa options của collection đã tồn tại.

### 6.3. Tạo index sau khi tạo collection

~~~javascript
db.books.createIndex(
  { isbn: 1 },
  {
    name: "uq_books_isbn",
    unique: true,
    partialFilterExpression: { isbn: { $type: "string" } }
  }
)

db.books.getIndexes()
~~~

Đây là bước **bổ sung**, không phải thành phần tự động có sẵn khi gọi `createCollection("books")`. Mọi collection thông thường có index cho `_id`; các index phục vụ nghiệp vụ cần được thiết kế riêng. Với ví dụ trên, unique index bảo đảm giá trị ISBN dạng chuỗi không trùng trong `books`. Việc tạo unique index có thể thất bại nếu dữ liệu cũ vi phạm ràng buộc.

### 6.4. Collection chuyên biệt cần chọn khi tạo

MongoDB có các loại collection và option riêng. Ví dụ collection dạng capped với kích thước giới hạn:

~~~javascript
db.createCollection("recent_lab_events", {
  capped: true,
  size: 1024 * 1024,
  max: 1000
})
~~~

Capped collection có hành vi và hạn chế khác collection thường, ví dụ giới hạn dung lượng/số document theo cấu hình. Không dùng capped collection như cơ chế retention chung cho mọi nghiệp vụ nếu chưa hiểu việc ghi đè dữ liệu cũ và các ràng buộc thao tác của nó.

Với dữ liệu time series, MongoDB có tùy chọn tạo **time-series collection** dành cho chuỗi đo thời gian; cú pháp và khả năng hỗ trợ phụ thuộc phiên bản. Khi mục tiêu chỉ là học tạo/liệt kê/xóa collection, bắt đầu với collection thường trước rồi nghiên cứu loại chuyên biệt sau.

## 7. Liệt kê các database

### 7.1. Lệnh tương tác trong mongosh

~~~javascript
show dbs
~~~

`show dbs` hiển thị danh sách database mà phiên kết nối có thể liệt kê. Nó **không chuyển** ngữ cảnh của `db` và có thể không hiển thị database vừa được `use` nhưng chưa tạo collection hay ghi dữ liệu.

Một server MongoDB thường có một số database nội bộ/đặc biệt:

| Database | Mục đích |
|---|---|
| `admin` | Một số tác vụ quản trị và cơ chế xác thực/quyền |
| `local` | Dữ liệu cục bộ của instance, ví dụ metadata phục vụ replication |
| `config` | Một số metadata/cấu hình hệ thống, đặc biệt trong cluster |

Chúng không phải database lab tùy ý. Không xóa hoặc thay đổi các database hệ thống vì thấy chúng xuất hiện trong kết quả `show dbs`.

### 7.2. Lệnh dùng trong script

Thay vì shell helper, có thể gọi command:

~~~javascript
db.adminCommand({
  listDatabases: 1,
  nameOnly: true
})
~~~

Lọc riêng database tên `training_store`:

~~~javascript
db.adminCommand({
  listDatabases: 1,
  nameOnly: true,
  filter: { name: "training_store" }
})
~~~

Kết quả là một object chứa danh sách database (khi thao tác thành công). Cách này phù hợp script và kiểm tra metadata ở mức command hơn là phân tích output text của `show dbs`.

Quyền của tài khoản ảnh hưởng kết quả: có môi trường chỉ cho phép thấy những database được cấp quyền, hoặc command bị từ chối nếu không đủ đặc quyền. **Danh sách rỗng không luôn có nghĩa deployment không chứa database nào**.

### 7.3. Danh sách và kích thước database

Một số thao tác liệt kê có thể cung cấp size/status tổng quan. Tuy nhiên:

- Database logic không trùng với một thư mục/dung lượng storage thuần túy theo cách có thể cộng máy móc.
- Dung lượng đang cấp phát, dữ liệu BSON logic, index và phần trống tái sử dụng là các khái niệm khác nhau.
- Trong replica set hoặc sharded cluster, số liệu tùy node, shard và cách command thu thập.

Muốn đánh giá dung lượng, cần thêm `db.stats()`, `db.collection.stats()` và metric hạ tầng; `show dbs` chủ yếu để định danh những database đang thấy được.

## 8. Liệt kê các collection của database đang chọn

### 8.1. Lệnh shell

~~~javascript
use training_store
show collections
~~~

Ví dụ bạn có thể thấy:

~~~text
books
borrow_records
catalog_items
members
recent_lab_events
~~~

Danh sách phụ thuộc những lệnh tạo đã chạy thành công; không bắt buộc phải giống hệt ví dụ.

### 8.2. Các phương thức mongosh

~~~javascript
// Danh sách tên collection (array).
db.getCollectionNames()

// Metadata về các collection.
db.getCollectionInfos()

// Chỉ tìm metadata collection tên books.
db.getCollectionInfos({ name: "books" })
~~~

`getCollectionInfos()` giúp xem tên, loại collection và các tùy chọn được trả về. Đừng kỳ vọng kết quả chỉ gồm collection do ứng dụng tạo: tùy phiên bản, quyền và loại namespace, có thể xuất hiện object hoặc metadata đặc biệt.

Ví dụ làm việc với database khác mà không cần `use`:

~~~javascript
const store = db.getSiblingDB("training_store")
const names = store.getCollectionNames()

printjson(names)
print(names.includes("books"))
~~~

Đây là mẫu hợp lý cho **script kiểm tra sự tồn tại**. Tuy nhiên, kiểm tra trước rồi tạo sau không bảo đảm không có một tiến trình khác tạo cùng tên giữa hai bước; hệ thống triển khai song song vẫn cần xử lý lỗi namespace đã tồn tại.

### 8.3. Dùng MongoDB command

~~~javascript
db.runCommand({
  listCollections: 1,
  nameOnly: true
})
~~~

Đây là command cấp thấp tương ứng. Kết quả có thể có `cursor` và được trả theo batch; không nên giả định một kết quả command luôn chứa toàn bộ collection nếu số lượng lớn. Khi viết script, `getCollectionNames()` hoặc driver API thường tiện hơn và tự xử lý nhiều chi tiết của cursor.

### 8.4. Kiểm tra dữ liệu trong collection

Liệt kê collection cho biết tên, không cho biết collection có document hay không. Có thể kiểm tra:

~~~javascript
db.books.findOne()
db.books.countDocuments({})
db.books.getIndexes()
~~~

Trong ứng dụng có dữ liệu lớn, không dùng đếm toàn bộ collection liên tục như một health-check giá rẻ; chi phí truy vấn phụ thuộc collection/index và trạng thái workload. Chọn phương pháp giám sát theo yêu cầu cụ thể.

## 9. Kiểm tra database và collection tồn tại như thế nào?

MongoDB không có một thuộc tính `db.exists` chung trong mongosh. Có thể kết hợp những cách sau.

### 9.1. Kiểm tra tên trong danh sách

~~~javascript
const store = db.getSiblingDB("training_store")

const exists = store.getCollectionNames().includes("books")
print(exists)
~~~

Kết quả `true` cho biết collection tên `books` xuất hiện trong danh sách mà tài khoản được phép xem tại thời điểm kiểm tra.

### 9.2. Kiểm tra metadata collection

~~~javascript
const store = db.getSiblingDB("training_store")
const infos = store.getCollectionInfos({ name: "books" })

printjson(infos)
~~~

Nếu cần xác thực cấu hình, có thể kiểm tra `options`, `type` hoặc metadata được trả trong `getCollectionInfos()`, tùy phiên bản MongoDB và quyền truy cập.

### 9.3. Kiểm tra database ở mức command

~~~javascript
const result = db.adminCommand({
  listDatabases: 1,
  nameOnly: true,
  filter: { name: "training_store" }
})

printjson(result)
~~~

Không dùng `db.getSiblingDB("training_store") !== null` làm phép thử: việc trả handle không đồng nghĩa database đã tồn tại trên server.

### 9.4. Quy tắc kiểm tra trước thay đổi cấu trúc

Với script triển khai:

1. Xác định **đúng cluster**, database và môi trường.
2. Đọc danh sách và metadata object dự kiến thao tác.
3. Xác nhận script được thiết kế xử lý object đã tồn tại, thiếu object hoặc lỗi quyền.
4. Thực thi bước tạo/sửa qua API phù hợp.
5. Đọc lại metadata để xác nhận kết quả thực tế.

Đây là quy trình quản trị cấu trúc, khác với việc để người dùng cuối thực thi lệnh drop trong request API thường ngày.

## 10. Xóa collection bằng `drop()`

Khi không còn cần một collection, MongoDB cho phép xóa **toàn bộ collection cùng các document và index gắn với nó**.

### 10.1. Cú pháp cơ bản

~~~javascript
use training_store

// Chỉ chạy trong lab sau khi xác nhận tên.
db.getCollection("recent_lab_events").drop()
~~~

Lệnh có thể trả `true` khi xóa thành công và `false` nếu collection không tồn tại (tùy hành vi shell/phiên bản). Trong script nghiêm túc, cần kiểm tra kết quả hoặc lỗi, sau đó đọc lại danh sách collection.

~~~javascript
db.getCollectionNames()
~~~

**Tác động của drop collection:**

- Xóa document của collection.
- Xóa các index thuộc collection.
- Loại bỏ validator/options của collection, vì chính collection không còn.
- Là thao tác thay đổi metadata/DDL có thể ảnh hưởng query, cursor hoặc change stream đang dùng.
- Có thể ảnh hưởng các ứng dụng phụ thuộc collection, không chỉ một màn hình riêng.

Trong replica set hoặc sharded cluster, drop là thao tác có ý nghĩa trên toàn phạm vi mà collection thuộc về; không dùng nó như cách “xóa trên một node” hay mẹo dọn disk thủ công.

### 10.2. Sự khác biệt giữa `deleteMany({})` và `drop()`

Hai lệnh nhìn qua đều có thể khiến collection không còn document, nhưng **khác mục tiêu và hậu quả**:

| Lệnh | Document | Collection/validator | Index | Khi nào cân nhắc |
|---|---|---|---|---|
| `db.books.deleteMany({})` | Xóa tất cả document khớp filter rỗng | Collection vẫn tồn tại | Index vẫn tồn tại | Cần giữ cấu trúc, chỉ làm sạch dữ liệu |
| `db.books.drop()` | Xóa toàn bộ cùng collection | Collection bị loại bỏ | Index của collection bị loại bỏ | Muốn xóa hẳn namespace |
| `db.dropDatabase()` | Xóa tất cả document ở mọi collection thuộc database | Xóa cả database và collection bên trong | Xóa index liên quan | Muốn hủy toàn bộ database có chủ đích |

`deleteMany({})` trên collection lớn có thể tốn thời gian, tạo tải và là một tập thao tác xóa; không coi nó tự động là thao tác atomic cho toàn collection. Khi cần giữ index và options, chọn giải pháp phù hợp với quy mô dữ liệu và yêu cầu vận hành.

### 10.3. Khi collection không tồn tại

~~~javascript
const store = db.getSiblingDB("training_store")

print(store.getCollectionNames().includes("not_a_real_collection"))
~~~

Nếu cần drop idempotent trong script, phải thiết kế để trường hợp collection vắng mặt được xử lý rõ ràng, nhưng vẫn kiểm tra đúng namespace. **Không dùng mẫu “nếu không có thì bỏ qua” để che giấu việc cấu hình sai cluster hoặc sai tên database.**

### 10.4. Các trường hợp không nên dùng drop

- Muốn xóa một bản ghi: dùng `deleteOne(filter)`.
- Muốn xóa một tập document theo điều kiện: dùng `deleteMany(filter)` có filter chặt chẽ.
- Muốn xóa dữ liệu hết hạn theo chính sách: nghiên cứu TTL/archival và retention.
- Muốn đổi tên collection: nghiên cứu `renameCollection`, không tự động drop rồi tạo lại.
- Muốn thu hồi dung lượng disk sau khi xóa nhiều document: cần hiểu storage space reuse và compaction; drop không phải lựa chọn mặc định nếu phải giữ schema/dữ liệu.

## 11. Xóa cả database bằng `dropDatabase()`

Đây là thao tác **có phạm vi rộng nhất trong bài**. Nó xóa database được chọn cùng các collection, document và index của database đó. Không có thao tác “undo” đơn giản trong mongosh; việc khôi phục thường phụ thuộc backup/snapshot và kế hoạch phục hồi.

### 11.1. Cú pháp

~~~javascript
use training_store
db.getName()      // Đọc lại: phải là training_store.

// CẢNH BÁO: Lệnh sau xóa toàn bộ database training_store.
// Chỉ chạy khi đây là lab được phép xóa.
db.dropDatabase()
~~~

Một cách thể hiện rõ database đích mà không dựa vào `use`:

~~~javascript
const targetDb = db.getSiblingDB("training_store")
print(targetDb.getName())

// CẢNH BÁO: Chạy lệnh sau sẽ xóa tất cả collection trong training_store.
targetDb.dropDatabase()
~~~

Những lệnh trên là **ví dụ thao tác xóa thực sự**, không phải lệnh kiểm tra. Khi làm trong shell, đọc tên database và danh sách collection trước rồi chỉ chạy dòng drop nếu bạn chủ động muốn hủy toàn bộ dữ liệu lab.

### 11.2. Vì sao dùng `getSiblingDB` có thể an toàn hơn trong script?

Trong một chuỗi lệnh dài, biến `db` trỏ đến ngữ cảnh hiện hành và có thể bị thay đổi khi dùng `use`. Viết:

~~~javascript
const targetDb = db.getSiblingDB("training_store")
~~~

làm database đích rõ ràng hơn trong code. Nhưng **đây không phải cơ chế bảo vệ tự động**: nếu tên database nhập sai hoặc connection string trỏ nhầm production, `targetDb.dropDatabase()` vẫn có hậu quả tương ứng. An toàn đến từ kiểm tra môi trường, quyền tối thiểu, xác minh đích và quy trình phê duyệt phù hợp.

### 11.3. Xác minh sau khi drop

Trong lab có thể:

~~~javascript
db.adminCommand({
  listDatabases: 1,
  nameOnly: true,
  filter: { name: "training_store" }
})
~~~

Nếu database đã bị drop và không được tạo lại, danh sách thường không còn database đó. Tuy nhiên, một tiến trình khác có thể tạo lại database/collection sau thao tác, và quyền liệt kê cũng có thể ảnh hưởng kết quả. Nếu cần đánh giá thao tác một cách chặt chẽ, kết hợp kết quả command với log/audit/metadata của môi trường.

### 11.4. Drop không phải backup/restore

Replica set sao chép thay đổi hợp lệ của database, bao gồm cả thao tác xóa được thực hiện. Vì thế **replication không đồng nghĩa khả năng hoàn tác drop**. Một backup hoặc snapshot có khả năng phục hồi, cùng quy trình thử restore, mới là phần cần có khi dữ liệu quan trọng.

## 12. Quy trình thực hành đầy đủ: tạo → liệt kê → chọn → xóa

Để tránh nhầm các ví dụ độc lập, phần này dùng database khác tên `db_lifecycle_lab` và thực hiện trình tự có thể lặp lại trên môi trường mới.

### Bước 1 — Chọn database chưa có

~~~javascript
use db_lifecycle_lab
db.getName()
~~~

Lúc này mới chọn ngữ cảnh; database có thể chưa xuất hiện trong `show dbs`.

### Bước 2 — Tạo một collection rỗng

~~~javascript
db.createCollection("notes")
show collections
~~~

### Bước 3 — Ghi document để quan sát dữ liệu

~~~javascript
db.notes.insertMany([
  {
    _id: "n-001",
    title: "Khái niệm database",
    createdAt: new Date(),
    tags: ["database", "mongodb"]
  },
  {
    _id: "n-002",
    title: "Khái niệm collection",
    createdAt: new Date(),
    tags: ["collection", "mongodb"]
  }
])
~~~

### Bước 4 — Tạo collection khác bằng insert ngầm

~~~javascript
db.topics.insertOne({
  _id: "t-001",
  name: "MongoDB",
  active: true
})
~~~

### Bước 5 — Liệt kê database và collection

~~~javascript
show dbs
show collections

db.getCollectionNames()
db.getCollectionInfos({ name: "notes" })
~~~

### Bước 6 — Chọn database khác rồi quay lại

~~~javascript
use admin
db.getName() // admin

const lab = db.getSiblingDB("db_lifecycle_lab")
lab.getCollectionNames()
lab.notes.findOne({ _id: "n-001" })
~~~

Đây là bước quan trọng: gọi `lab.notes.findOne()` thao tác trên `db_lifecycle_lab` dù ngữ cảnh `db` đang là `admin`.

### Bước 7 — Xóa riêng một collection

~~~javascript
// Chỉ chạy khi db_lifecycle_lab là database thử nghiệm có thể hủy.
const lab = db.getSiblingDB("db_lifecycle_lab")

print(lab.getName())
printjson(lab.getCollectionNames())

lab.getCollection("topics").drop()

printjson(lab.getCollectionNames())
~~~

Sau đó `notes` vẫn tồn tại; `topics` đã bị xóa nếu drop thành công.

### Bước 8 — Xóa cả database thử nghiệm

~~~javascript
// Chỉ chạy sau khi chắc chắn toàn bộ db_lifecycle_lab có thể xóa.
const labToDrop = db.getSiblingDB("db_lifecycle_lab")

print(labToDrop.getName())
printjson(labToDrop.getCollectionNames())

labToDrop.dropDatabase()
~~~

### Bước 9 — Kiểm tra kết quả

~~~javascript
db.adminCommand({
  listDatabases: 1,
  nameOnly: true,
  filter: { name: "db_lifecycle_lab" }
})
~~~

**Điểm tự kiểm chứng:** Sau `use` mà chưa tạo, database có thể không hiển thị; sau `createCollection` hoặc insert thì collection hiện diện; sau `drop()` chỉ mất một collection; sau `dropDatabase()` mất toàn bộ database đích.

## 13. Lệnh shell và command tương ứng

MongoDB có nhiều lớp giao diện. Bảng này giúp phân biệt lệnh gõ trong terminal mongosh với lời gọi JavaScript và database command.

| Công việc | Mongosh helper / method | Command hoặc cách dùng trong script |
|---|---|---|
| Chọn database | `use training_store` | `db.getSiblingDB("training_store")` |
| Xem database hiện tại | `db.getName()` | `db.getName()` |
| Liệt kê database | `show dbs` | `db.adminCommand({listDatabases: 1})` |
| Tạo collection | `db.createCollection("books")` | `db.runCommand({create: "books"})` |
| Liệt kê collection | `show collections` | `db.getCollectionNames()` hoặc `listCollections` |
| Xem metadata collection | `db.getCollectionInfos()` | `db.runCommand({listCollections: 1})` |
| Xóa collection | `db.books.drop()` | `db.runCommand({drop: "books"})` |
| Xóa database hiện tại | `db.dropDatabase()` | `db.runCommand({dropDatabase: 1})` |

Ghi nhớ:

- `use` và `show` là shell helpers tiện cho phiên tương tác.
- `db.getSiblingDB()`, `db.createCollection()` và `db.dropDatabase()` là những API của mongosh.
- `listDatabases`, `create`, `listCollections`, `drop`, `dropDatabase` là những database commands.
- Trong Java/Node.js/Python driver, cách gọi cụ thể khác mongosh; dùng API của driver phù hợp thay vì chép nguyên `show dbs` vào code ứng dụng.

Ví dụ command tạo collection trong database đã chọn:

~~~javascript
const store = db.getSiblingDB("training_store")
store.runCommand({ create: "script_created_collection" })
~~~

Đây chỉ là một cách tương đương ở mức command; trong code học tập thông thường, `createCollection()` dễ đọc hơn.

## 14. Quyền truy cập và các database đặc biệt

MongoDB có cơ chế **authentication** và **role-based access control (RBAC)**. Không phải mọi tài khoản được phép:

- Liệt kê tất cả database.
- Xem metadata của mọi collection.
- Tạo collection.
- Drop một collection hoặc toàn database.

Ví dụ, tài khoản chỉ đọc có thể truy vấn document và metadata trong phạm vi được cấp, nhưng không có quyền tạo/xóa collection. Tài khoản ứng dụng cần quyền phù hợp nghiệp vụ; không nên cấp quyền quản trị toàn cluster chỉ để thử `show dbs` hoặc chạy CRUD.

### Tại sao một lệnh có thể báo Unauthorized?

~~~text
MongoServerError: not authorized ...
~~~

Lỗi quyền khác lỗi “namespace chưa tồn tại”:

- **Unauthorized / insufficient privileges:** tài khoản không được phép làm thao tác.
- **NamespaceExists:** collection đã tồn tại và không thể tạo lại cùng tên theo lệnh đó.
- **NamespaceNotFound:** đối tượng mục tiêu không tồn tại ở những command yêu cầu nó phải có.
- **DuplicateKey:** ghi document vi phạm unique index, chẳng hạn trùng `_id`.
- **Connection/timeout error:** không giao tiếp được hoặc không nhận xác nhận đúng hạn; cần kiểm tra kết quả thay vì tự suy luận thao tác đã/thất bại hoàn toàn.

Không sửa lỗi Unauthorized bằng cách bật quyền quản trị tối đa cho tài khoản ứng dụng. Xác định đúng thao tác, database đích và permission tối thiểu hoặc nhờ người vận hành cấp quyền phù hợp.

### `admin`, `local` và `config`

Những database này phục vụ chức năng hệ thống và cluster, không phải nơi tạo dữ liệu bài thực hành. `db.dropDatabase()` là lệnh phá hủy phạm vi database hiện hành nên **không bao giờ chọn một database hệ thống rồi thử drop để xem kết quả**.

## 15. Những sai lầm thường gặp

### Sai lầm 1 — Nghĩ `use` đã tạo database

~~~javascript
use demo_not_written_yet
show dbs
~~~

Không thấy tên trong `show dbs` có thể hoàn toàn bình thường. Tạo collection hoặc ghi document thành công rồi kiểm tra lại.

### Sai lầm 2 — Nghĩ collection rỗng không tồn tại

~~~javascript
db.createCollection("empty_but_real")
db.empty_but_real.findOne()  // Có thể trả null.
db.getCollectionNames()      // Vẫn có tên collection.
~~~

`findOne()` trả `null` không đủ để chứng minh collection chưa tồn tại. Nó có thể là collection rỗng hoặc không có document khớp filter.

### Sai lầm 3 — Nhầm database đang chọn

~~~javascript
use admin
db.dropDatabase()
~~~

Đây là **minh họa thao tác nguy hiểm, không thực thi**. Vấn đề là `db.dropDatabase()` luôn hướng vào ngữ cảnh `db` hiện tại. Trước mọi thao tác xóa, đọc lại `db.getName()`, xác nhận kết nối và dùng tên database tường minh khi thích hợp.

### Sai lầm 4 — Nhầm xóa document với xóa collection

~~~javascript
db.books.deleteOne({ _id: "b-001" }) // Xóa một document khớp.
db.books.deleteMany({})              // Xóa mọi document của books.
db.books.drop()                       // Xóa toàn bộ collection books.
~~~

Ba lệnh này không thể thay thế nhau. Mức ảnh hưởng tăng từ document → toàn bộ nội dung collection → cả collection cùng cấu trúc/index.

### Sai lầm 5 — Thấy `show dbs` thiếu tên và tự kết luận không có quyền

Tên database có thể chưa được tạo, hoặc quyền liệt kê bị giới hạn. Kiểm tra bằng tài khoản và command phù hợp thay vì lập tức yêu cầu toàn quyền.

### Sai lầm 6 — Gọi `createCollection` nhiều lần như một lệnh idempotent

~~~javascript
db.createCollection("books")
db.createCollection("books") // Có thể gặp NamespaceExists.
~~~

Khi viết migration, phải nêu rõ chiến lược nếu collection đã tồn tại: kiểm tra metadata, xác nhận các options kỳ vọng và chỉ sửa thông qua cơ chế phù hợp. Không coi lỗi “đã tồn tại” là bằng chứng collection có cấu hình đúng.

### Sai lầm 7 — Drop để “giải phóng dung lượng” nhưng quên hệ quả

Drop xóa collection, document, indexes và metadata. Không dùng drop thay thế cho chiến lược retention, archival, phân vùng dữ liệu, index cleanup hay quản trị storage capacity khi nghiệp vụ vẫn cần collection.

## 16. Script kiểm tra an toàn trước khi thao tác DDL

Trong script triển khai, thường nên đọc trạng thái trước và phân biệt rõ bước quan sát với bước thay đổi.

~~~javascript
// Đọc và báo cáo trạng thái; đoạn này không tự xóa gì.
const targetDb = db.getSiblingDB("training_store")
const targetName = "books"

print("Current target database: " + targetDb.getName())
print("Target collection: " + targetName)

const collections = targetDb.getCollectionNames()
const found = collections.includes(targetName)

print("Collection exists: " + found)
printjson(targetDb.getCollectionInfos({ name: targetName }))
~~~

Mẫu này giúp người vận hành có đủ thông tin để đưa ra quyết định, nhưng **không có tác dụng khóa trạng thái**: tài khoản khác vẫn có thể tạo/xóa collection sau khi kiểm tra. Trong thao tác thực tế, cần kết hợp quyền, change management, xử lý lỗi và xác minh sau thao tác.

Nếu cần lập quy trình xóa production, nên có:

1. Kiểm tra đúng connection/deployment, database và collection.
2. Xác định người chịu trách nhiệm, phạm vi phụ thuộc và dữ liệu cần giữ.
3. Xác minh backup có thể khôi phục và mục tiêu RPO/RTO.
4. Ngăn hoặc điều phối luồng ghi/đọc liên quan trong khoảng thay đổi theo kế hoạch.
5. Thực hiện lệnh xóa trong cửa sổ bảo trì phù hợp, ghi log/audit.
6. Kiểm tra metadata, ứng dụng, dashboard và tài nguyên sau thao tác.

Đối với môi trường học tập, vẫn nên tập thói quen xác minh database đích trước khi drop; các bước quản trị production là kiến thức vận hành mở rộng.

## 17. Khía cạnh kiến trúc: tác động khi chạy trên replica set và sharded cluster

Các lệnh trong bài trông giống nhau ở mức mongosh, nhưng topology ảnh hưởng cách chúng được triển khai và quan sát.

### 17.1. Standalone

Tất cả thao tác hướng đến một MongoDB server. Mất server có thể làm mất khả năng phục vụ; bảo vệ dữ liệu phụ thuộc storage/backup và cấu hình tương ứng.

### 17.2. Replica set

Các thay đổi dữ liệu và metadata hợp lệ được nhân bản theo cơ chế replication của deployment. Một lệnh drop đã được chấp nhận không nên được xem là “chỉ xóa trên primary nhưng secondary giữ bản backup”. Secondary không thay thế kế hoạch sao lưu.

### 17.3. Sharded cluster

Một collection có thể phân phối dữ liệu qua nhiều shard. Tạo/drop collection hay database có thể liên quan metadata cluster và quá trình phối hợp giữa các node. Người dùng cần kết nối qua thành phần truy cập cluster phù hợp, tuân thủ khuyến cáo phiên bản và hiểu rằng drop có phạm vi logic của toàn collection/database.

### 17.4. Tính sẵn sàng và thao tác DDL

Không chạy tạo/xóa cấu trúc liên tục như một phần mặc định của request người dùng. DDL có thể ảnh hưởng những client đang truy vấn, index, schema validation hoặc change stream. Hãy đưa thay đổi cấu trúc vào migration có log, xử lý lỗi, tính tương thích ứng dụng và khả năng phục hồi.

## 18. Bài thực hành tổng hợp: quản lý không gian dữ liệu

**Bối cảnh:** Một ứng dụng đào tạo có database `academy_practice` chứa:

- `courses`: danh mục khóa học.
- `learners`: học viên.
- `enrollments`: đăng ký của học viên.

### Phần A — Chọn và tạo

1. Kết nối MongoDB lab; ghi lại database hiện tại.
2. Chọn `academy_practice` mà chưa ghi dữ liệu; quan sát nó có xuất hiện trong danh sách database hay không.
3. Tạo `courses` tường minh bằng `createCollection`.
4. Tạo `learners` bằng `insertOne` với một học viên mẫu.
5. Tạo `enrollments` tường minh và gắn một validator đơn giản có `courseId`, `learnerId`, `joinedAt`.

### Phần B — Liệt kê và đối chiếu

1. Dùng `show dbs` và `listDatabases` để liệt kê database.
2. Dùng `show collections`, `getCollectionNames()` và `getCollectionInfos()` trên `academy_practice`.
3. Dùng `getSiblingDB` để đọc `academy_practice.courses` ngay cả khi `db` đang chọn một database khác.
4. Kiểm tra tên collection tồn tại, số document và danh sách index của nó.

### Phần C — Xóa theo hai phạm vi

1. Chỉ trong lab, xóa riêng `enrollments` bằng `drop()`.
2. Chứng minh `courses` và `learners` vẫn hiện diện.
3. Xác nhận cả ba collection đều không chứa dữ liệu cần giữ.
4. Drop toàn bộ `academy_practice`; kiểm tra tên database không còn trong danh sách hiện hành.

### Câu hỏi cần giải thích

- Vì sao `use academy_practice` không chắc làm xuất hiện database ngay?
- Lệnh nào nên dùng nếu cần collection rỗng nhưng đã cấu hình validator?
- Tại sao `getSiblingDB` phù hợp script hơn khi nhiều database cùng được truy cập?
- `findOne() === null` có chứng minh collection chưa tồn tại không?
- Nếu chỉ muốn xóa một học viên, vì sao không dùng `drop()`?
- Tại sao phải tạo lại index/validator khi drop rồi tạo mới cùng tên collection?
- Nếu lệnh xóa đang hướng vào production thay vì lab, dấu hiệu nào giúp phát hiện trước khi thực thi?
- Replica set có thể được dùng như một bản backup để “khôi phục lại” collection vừa drop không?

## 19. Câu hỏi ôn tập nhanh

**Câu 1.** `use sales` có tạo ngay database `sales` không?

**Đáp án:** Không nhất thiết. Đây là lệnh chọn ngữ cảnh database trong mongosh. Database thường được hình thành khi tạo collection hoặc có thao tác ghi phù hợp.

**Câu 2.** Cách liệt kê database trong mongosh là gì?

**Đáp án:** `show dbs`; trong script có thể dùng `db.adminCommand({listDatabases: 1})`, tùy quyền.

**Câu 3.** Cách liệt kê collection của database hiện tại?

**Đáp án:** `show collections` hoặc `db.getCollectionNames()`; xem metadata bằng `db.getCollectionInfos()`.

**Câu 4.** Khác biệt giữa `db.books.drop()` và `db.books.deleteMany({})`?

**Đáp án:** `drop()` loại bỏ collection và index/metadata của collection, còn `deleteMany({})` xóa document khớp nhưng giữ namespace cùng index/validator.

**Câu 5.** Có thể tạo database bằng cách gọi `db.getSiblingDB("new_db")` không?

**Đáp án:** Câu lệnh này chỉ lấy handle; chưa tạo tài nguyên dữ liệu cho database.

**Câu 6.** Khi cần khởi tạo collection có validator, dùng gì?

**Đáp án:** `db.createCollection("name", {validator: ...})` (trong phạm vi options được phiên bản hỗ trợ), sau đó kiểm tra metadata và thử ghi dữ liệu hợp lệ.

**Câu 7.** Vì sao không nên chạy `dropDatabase()` chỉ sau khi nhìn thấy một collection không còn cần?

**Đáp án:** Vì nó xóa toàn bộ các collection của database đích; muốn chỉ xóa một collection phải dùng `collection.drop()`.

**Câu 8.** Lệnh `show dbs` không liệt kê database mong muốn. Nguyên nhân có thể là gì?

**Đáp án:** Database mới chỉ được chọn nhưng chưa thực sự tạo, tài khoản bị giới hạn quyền liệt kê, hoặc đang kết nối sai deployment.

**Câu 9.** Nếu tạo collection tên `book-events`, truy cập thế nào?

**Đáp án:** Dùng `db.getCollection("book-events")`; cú pháp dấu chấm với dấu gạch nối không phù hợp.

**Câu 10.** Điều gì nên kiểm tra ngay trước thao tác xóa database?

**Đáp án:** Đúng connection/deployment, tên database, danh sách collection, tính cần thiết của dữ liệu và phương án backup/restore theo quy trình môi trường.

## 20. Bảng ghi nhớ lệnh thiết yếu

| Mục đích | Lệnh |
|---|---|
| Chọn database | `use training_store` |
| Chọn database tường minh trong script | `const d = db.getSiblingDB("training_store")` |
| Xem tên database hiện tại | `db.getName()` |
| Liệt kê database | `show dbs` |
| Liệt kê database bằng command | `db.adminCommand({listDatabases: 1})` |
| Tạo collection rỗng | `db.createCollection("books")` |
| Tạo collection khi insert đầu tiên | `db.books.insertOne({...})` |
| Liệt kê tên collection | `show collections` hoặc `db.getCollectionNames()` |
| Xem metadata collection | `db.getCollectionInfos({name: "books"})` |
| Truy cập collection với tên đặc biệt | `db.getCollection("book-events")` |
| Xóa một document | `db.books.deleteOne(filter)` |
| Xóa tất cả document nhưng giữ collection | `db.books.deleteMany({})` |
| Xóa collection cùng index | `db.books.drop()` |
| Xóa toàn bộ database đang chọn | `db.dropDatabase()` |

Trình tự nên nhớ khi làm việc với MongoDB là **kết nối đúng deployment → xác định database → chọn/tạo collection → kiểm tra metadata → thao tác dữ liệu → xác minh kết quả**. Riêng các thao tác drop, luôn xác định rõ phạm vi ảnh hưởng và khả năng phục hồi trước khi thực thi.

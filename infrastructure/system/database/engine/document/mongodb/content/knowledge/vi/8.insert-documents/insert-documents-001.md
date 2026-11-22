# MongoDB: insertOne, insertMany và cấu trúc kết quả ghi

Khi ứng dụng cần thêm dữ liệu mới vào MongoDB, hai thao tác cơ bản là **insertOne()** để thêm một document và **insertMany()** để thêm nhiều document trong một lần gọi. Cả hai đều hướng tới một **collection**, nhận dữ liệu theo cấu trúc BSON và trả lại thông tin về thao tác ghi nếu yêu cầu được xác nhận.

Điểm cần hiểu là **“đã gửi lệnh”, “đã được xác nhận ghi” và “mọi document đều đã được thêm” không phải lúc nào cũng là cùng một trạng thái**. Trong những tình huống trùng khóa duy nhất, sai validation, mất kết nối hoặc write concern khác nhau, ứng dụng cần đọc đúng kết quả hoặc lỗi để biết phần dữ liệu nào đã được lưu.

Bài học sử dụng **mongosh** làm môi trường ví dụ chính, sau đó liên hệ với Java, Node.js và Python để phân biệt các API result của từng driver.

## 1. Thao tác insert nằm ở đâu trong mô hình MongoDB?

MongoDB tổ chức dữ liệu theo các cấp:

~~~text
Database: bookstore
└── Collection: books
    ├── Document: { _id, isbn, title, price, stock }
    ├── Document: { _id, isbn, title, price, stock }
    └── Document: { _id, isbn, title, price, stock }
~~~

Trong **mongosh**, chọn database và truy cập collection:

~~~javascript
use bookstore

db.books
~~~

Để thêm dữ liệu vào **bookstore.books**, có thể dùng:

~~~javascript
db.books.insertOne({
  isbn: "9786040000001",
  title: "Nhập môn MongoDB",
  price: 190000,
  stock: 12
});
~~~

Hoặc thêm nhiều cuốn sách:

~~~javascript
db.books.insertMany([
  {
    isbn: "9786040000002",
    title: "Mô hình dữ liệu document",
    price: 240000,
    stock: 6
  },
  {
    isbn: "9786040000003",
    title: "Truy vấn và index",
    price: 260000,
    stock: 9
  }
]);
~~~

Cả hai lệnh đều là **write operation**. Chúng thêm document mới và không được dùng để sửa document đang tồn tại. Nếu muốn cập nhật field của document đã có, cần dùng các thao tác update hoặc replace phù hợp.

### So sánh nhanh

| Khía cạnh | insertOne() | insertMany() |
| --- | --- | --- |
| Đầu vào | Một document | Một array các document |
| Mục đích | Thêm đúng một bản ghi | Thêm một nhóm bản ghi |
| Kết quả thành công trong mongosh | acknowledged, insertedId | acknowledged, insertedIds |
| Nguyên tử | Một document | Theo từng document, không nguyên tử cho toàn batch |
| Cấu hình thứ tự | Không áp dụng | ordered: true hoặc false |
| Khi có lỗi | Lệnh thất bại và báo lỗi | Có thể đã thêm thành công một phần batch |
| Sử dụng điển hình | Tạo một người dùng, đơn hàng, bài viết | Import dữ liệu, tạo nhiều sự kiện, nạp dữ liệu ban đầu |

## 2. Trước khi insert: document và field _id

Mỗi document trong một collection MongoDB thông thường có field **_id** làm khóa định danh.

Ví dụ dữ liệu ứng dụng gửi:

~~~javascript
{
  sku: "BOOK-001",
  title: "Nhập môn MongoDB",
  price: 190000
}
~~~

Nếu không cung cấp **_id**, driver hoặc MongoDB có thể tạo giá trị định danh. Với thao tác thông thường trong mongosh, giá trị được tạo phổ biến là **ObjectId**:

~~~javascript
{
  _id: ObjectId("674000000000000000000001"),
  sku: "BOOK-001",
  title: "Nhập môn MongoDB",
  price: 190000
}
~~~

ObjectId ở ví dụ là giá trị minh họa. Mỗi lần insert thực tế thường tạo một ObjectId khác.

### 2.1. _id có thể do ứng dụng cung cấp

MongoDB không bắt buộc mọi _id phải là ObjectId. Ứng dụng có thể chọn giá trị string hoặc kiểu phù hợp khác:

~~~javascript
db.products.insertOne({
  _id: "BOOK-001",
  title: "Nhập môn MongoDB",
  price: 190000
});
~~~

Cách này hữu ích nếu mã nghiệp vụ được thiết kế làm khóa chính và có thể bảo đảm tính ổn định, duy nhất của mã trong collection.

Nếu collection đã có document với **_id: "BOOK-001"**, insert mới dùng cùng _id sẽ gặp **duplicate key error**, thay vì tự thay thế bản ghi cũ.

### 2.2. _id được bảo vệ bằng unique index

Collection thông thường có unique index trên **_id**. Vì thế hai document trong cùng collection không thể có cùng giá trị _id theo ràng buộc đó.

~~~javascript
db.products.insertOne({
  _id: "BOOK-001",
  title: "Sách A"
});

db.products.insertOne({
  _id: "BOOK-001",
  title: "Sách B"
});
~~~

Giả sử collection ban đầu chưa có khóa đó, lệnh thứ nhất thành công. Lệnh thứ hai báo lỗi trùng khóa với mã thường gặp **E11000** (error code **11000**).

Hai collection khác nhau vẫn có thể có document với cùng _id; phạm vi nhận diện và unique index ở đây là **collection**.

### 2.3. _id không đại diện cho thứ tự insert

ObjectId thường có thành phần thời gian và có thể giúp suy đoán một số thông tin, nhưng **không nên xem _id là bằng chứng tuyệt đối về thứ tự ghi**. ID có thể được tạo ở các client khác nhau trước khi gửi, hoặc ứng dụng sử dụng một kiểu _id khác.

Nếu cần thứ tự sự kiện nghiệp vụ, hãy thiết kế field **createdAt**, sequence hoặc khóa sắp xếp phù hợp và hiểu rõ độ tin cậy của nguồn thời gian.

## 3. insertOne(): thêm một document

Cú pháp trong mongosh:

~~~javascript
db.collection.insertOne(
  <document>,
  <options>
);
~~~

Trong đó:

- **document** là đối tượng cần thêm.
- **options** là đối tượng tùy chọn, chẳng hạn **writeConcern** hoặc các tùy chọn được hỗ trợ bởi phiên bản hiện tại.

Ví dụ:

~~~javascript
use bookstore

const result = db.books.insertOne({
  isbn: "9786040000101",
  title: "MongoDB cho lập trình viên Java",
  author: {
    name: "Nguyễn An",
    country: "VN"
  },
  categories: ["database", "backend"],
  price: NumberDecimal("215000.00"),
  stock: 10,
  createdAt: new Date()
});

printjson(result);
~~~

Một kết quả thành công điển hình:

~~~javascript
{
  acknowledged: true,
  insertedId: ObjectId("674000000000000000000101")
}
~~~

Mỗi lần chạy, **insertedId** có thể khác.

### 3.1. Ý nghĩa của acknowledged

**acknowledged** cho biết thao tác được xác nhận theo **write concern** được áp dụng. Với yêu cầu ghi đã được xác nhận, trường này thường là **true**.

Không nên suy luận từ **acknowledged: true** rằng dữ liệu nhất định đã được sao chép tới mọi thành viên replica set hoặc không thể bị rollback trong bất kỳ tình huống nào. Mức xác nhận và kỳ vọng về độ bền phụ thuộc **write concern**, topology và trạng thái deployment.

### 3.2. Ý nghĩa của insertedId

**insertedId** là giá trị _id của document mới được insert theo API result.

Nếu ứng dụng không gửi _id, MongoDB driver thường tạo _id trước khi insert. Nếu ứng dụng đã gửi _id, kết quả phản ánh giá trị đã dùng:

~~~javascript
db.books.insertOne({
  _id: "BOOK-JAVA-01",
  title: "Java và MongoDB"
});
~~~

Kết quả minh họa:

~~~javascript
{
  acknowledged: true,
  insertedId: "BOOK-JAVA-01"
}
~~~

**insertedId không phải số lượng document**. Với insertOne(), một lệnh thêm tối đa một document, còn insertedId dùng để định vị document được thêm.

### 3.3. Kiểm tra document sau khi insert

Có thể dùng ID nhận được để đọc lại:

~~~javascript
const writeResult = db.books.insertOne({
  title: "Tìm hiểu BSON",
  price: NumberDecimal("149000.00")
});

const saved = db.books.findOne({
  _id: writeResult.insertedId
});

printjson(saved);
~~~

Nếu ứng dụng cần kiểm tra bản ghi đã lưu thực sự chứa những field nào, một thao tác readback như trên giúp quan sát document sau khi ghi. Nhưng việc đọc lại không phải là thành phần bắt buộc của mọi thao tác insert; bạn cần cân nhắc chi phí và mức nhất quán của việc đọc.

Trong replica set, read preference/read concern và thời điểm đồng bộ của secondary cũng ảnh hưởng đến khả năng nhìn thấy kết quả khi đọc qua các thành viên khác nhau.

### 3.4. Insert có thể tạo collection chưa tồn tại

Với collection thông thường, insert đầu tiên có thể làm MongoDB tạo collection nếu nó chưa tồn tại:

~~~javascript
use bookstore

db.publisherNotes.insertOne({
  title: "Ghi chú phát hành",
  content: "Bản thử nghiệm"
});
~~~

Không vì thế mà nên phụ thuộc hoàn toàn vào cơ chế tạo collection ngầm định khi cần cấu hình **schema validation**, **collation**, **capped collection**, hoặc các tùy chọn chuyên biệt. Những trường hợp đó thường cần tạo collection và cấu hình tường minh trước.

## 4. insertMany(): thêm nhiều document trong một lời gọi

Cú pháp:

~~~javascript
db.collection.insertMany(
  [ <document1>, <document2>, ... ],
  <options>
);
~~~

Đầu vào phải là **array chứa các document**.

Ví dụ:

~~~javascript
use bookstore

const result = db.books.insertMany([
  {
    isbn: "9786040000201",
    title: "Kiến trúc MongoDB",
    price: NumberDecimal("250000.00"),
    stock: 8
  },
  {
    isbn: "9786040000202",
    title: "BSON và kiểu dữ liệu",
    price: NumberDecimal("180000.00"),
    stock: 14
  },
  {
    isbn: "9786040000203",
    title: "Thiết kế index",
    price: NumberDecimal("230000.00"),
    stock: 7
  }
]);

printjson(result);
~~~

Kết quả **mongosh** thường có cấu trúc:

~~~javascript
{
  acknowledged: true,
  insertedIds: {
    "0": ObjectId("674000000000000000000201"),
    "1": ObjectId("674000000000000000000202"),
    "2": ObjectId("674000000000000000000203")
  }
}
~~~

Các ObjectId trên chỉ dùng minh họa kết quả.

### 4.1. insertedIds là gì?

**insertedIds** trong kết quả mongosh ánh xạ **chỉ số của document trong array đầu vào** đến giá trị _id được dùng cho document đó.

~~~text
Array đầu vào:
  [0] sách "Kiến trúc MongoDB"
  [1] sách "BSON và kiểu dữ liệu"
  [2] sách "Thiết kế index"

insertedIds:
  "0" -> _id của document ở chỉ số 0
  "1" -> _id của document ở chỉ số 1
  "2" -> _id của document ở chỉ số 2
~~~

Đừng nhầm key **"0", "1", "2"** với giá trị của field _id. Đây chỉ là **chỉ số đầu vào**; giá trị tương ứng mới là _id được dùng khi insert.

Trong một số driver, cùng ý tưởng được biểu diễn bằng map hoặc list thay vì object như mongosh. Khi gặp lỗi một phần, cách nhận thông tin về ID và số thao tác thành công có thể khác với trường hợp toàn bộ batch thành công.

### 4.2. Trường hợp cung cấp _id trước

~~~javascript
db.books.insertMany([
  {
    _id: "B-001",
    title: "Cuốn sách thứ nhất"
  },
  {
    _id: "B-002",
    title: "Cuốn sách thứ hai"
  }
]);
~~~

Kết quả minh họa:

~~~javascript
{
  acknowledged: true,
  insertedIds: {
    "0": "B-001",
    "1": "B-002"
  }
}
~~~

Việc chủ động gán _id có thể giúp phối hợp các service hoặc triển khai idempotency, nhưng vẫn cần xử lý trường hợp ID bị dùng lại và kiểm tra kết quả ghi.

### 4.3. Insert nhiều document không phải một thao tác nguyên tử trên toàn batch

Giả sử có ba document:

~~~text
D1 = sản phẩm A
D2 = sản phẩm B
D3 = sản phẩm C
~~~

MongoDB bảo đảm atomicity cho **từng document** khi ghi. Nhưng **insertMany không tự biến D1, D2, D3 thành một transaction toàn phần**.

Nếu D1 đã được ghi, D2 gặp lỗi duplicate key và D3 chưa được ghi hoặc còn tiếp tục tùy tùy chọn **ordered**, kết quả có thể chỉ có một phần document xuất hiện trong collection.

Nếu nghiệp vụ yêu cầu **cả ba thành công hoặc không document nào được thêm**, cần một multi-document transaction trên deployment hỗ trợ, hoặc chọn mô hình dữ liệu khác phù hợp.

## 5. ordered: true và ordered: false

Tùy chọn quan trọng của **insertMany()** là **ordered**.

- **ordered: true** là mặc định. Các thao tác được xử lý theo thứ tự và dừng khi gặp lỗi ghi.
- **ordered: false** cho phép MongoDB/driver tiếp tục xử lý những document khác khi có lỗi ghi ở một document, trong phạm vi những lỗi cho phép tiếp tục. Thứ tự thực thi không được bảo đảm như khi ordered true.

### 5.1. ordered: true — dừng ở lỗi đầu tiên

Giả sử collection **inventoryOrdered** còn trống. Thực hiện:

~~~javascript
db.inventoryOrdered.insertMany(
  [
    { _id: "P-001", sku: "BOOK-001" },
    { _id: "P-001", sku: "BOOK-002" },
    { _id: "P-003", sku: "PEN-003" }
  ],
  { ordered: true }
);
~~~

Document thứ hai trùng _id với document thứ nhất. Với thứ tự đã cho:

~~~text
[0] _id = P-001  -> Thêm thành công
[1] _id = P-001  -> Lỗi duplicate key
[2] _id = P-003  -> Không tiếp tục xử lý vì ordered=true
~~~

Lệnh có thể ném lỗi dù document đầu tiên đã được lưu. Đây là ví dụ về **partial success**.

Một hiểu lầm thường gặp là “insertMany báo lỗi nên không document nào được ghi”. Kết luận đó sai nếu không dùng transaction bao ngoài.

### 5.2. ordered: false — tiếp tục những document độc lập

Dùng một collection thử nghiệm khác, ban đầu trống:

~~~javascript
db.inventoryUnordered.insertMany(
  [
    { _id: "P-001", sku: "BOOK-001" },
    { _id: "P-001", sku: "BOOK-002" },
    { _id: "P-003", sku: "PEN-003" }
  ],
  { ordered: false }
);
~~~

Kết quả điển hình:

~~~text
[0] _id = P-001  -> Thành công
[1] _id = P-001  -> Lỗi duplicate key
[2] _id = P-003  -> Vẫn được xử lý và có thể thành công
~~~

Lệnh vẫn có thể báo lỗi tổng hợp (bulk write error). **ordered: false không có nghĩa bỏ qua lỗi như thể thành công hoàn toàn**, cũng không có nghĩa sẽ tiếp tục bất chấp mọi lỗi nghiêm trọng như mất kết nối hoặc sự cố toàn cluster.

Với unordered insert, MongoDB có quyền tổ chức hoặc sắp xếp lại thứ tự xử lý để tối ưu. Vì vậy không viết nghiệp vụ phụ thuộc vào thứ tự document được chèn khi **ordered: false**.

### 5.3. So sánh trong tình huống lỗi

| Thuộc tính | ordered: true | ordered: false |
| --- | --- | --- |
| Giá trị mặc định | Có | Không |
| Xử lý theo thứ tự input | Có | Không bắt buộc |
| Gặp lỗi ghi một document | Dừng những thao tác tiếp theo trong chuỗi ordered | Tiếp tục những thao tác đủ điều kiện được xử lý |
| Có thể thành công một phần | Có | Có |
| Có bảo đảm toàn batch nguyên tử | Không | Không |
| Mục tiêu sử dụng | Cần dừng khi lỗi, muốn kiểm soát thứ tự | Nạp dữ liệu độc lập, muốn tiếp tục dù một số document lỗi |
| Cần xử lý lỗi tổng hợp | Có | Có |

### 5.4. Khi nào chọn ordered: false?

Giả sử nhập dữ liệu khảo sát từ các hệ thống độc lập. Một record trùng ID không nên ngăn các record hợp lệ khác được ghi. Có thể dùng **ordered: false**, sau đó tập hợp lỗi, kiểm tra số bản ghi thành công và xử lý các bản ghi chưa thêm.

Ngược lại, nếu thứ tự có ý nghĩa nghiệp vụ và việc gặp lỗi phải ngừng toàn chuỗi, **ordered: true** phù hợp hơn. Tuy nhiên, chỉ dùng ordered true vẫn **không tạo rollback** cho những document đã insert trước lỗi.

## 6. Cấu trúc kết quả ghi: đọc đúng từng trường

Tên field xuất hiện trong **mongosh**, Node.js, PyMongo hoặc Java có thể khác nhau. Cần phân biệt **kết quả thành công được driver trả về** và **phản hồi thô của server**.

### 6.1. Kết quả thành công trong mongosh

**insertOne()**:

~~~javascript
{
  acknowledged: true,
  insertedId: ObjectId("674000000000000000000301")
}
~~~

**insertMany()**:

~~~javascript
{
  acknowledged: true,
  insertedIds: {
    "0": ObjectId("674000000000000000000302"),
    "1": ObjectId("674000000000000000000303")
  }
}
~~~

| Field | Có trong lệnh | Ý nghĩa |
| --- | --- | --- |
| acknowledged | insertOne / insertMany | Thao tác có được xác nhận theo write concern không |
| insertedId | insertOne | _id của document được thêm trong trường hợp thành công |
| insertedIds | insertMany | Các _id gắn với vị trí document đầu vào trong trường hợp thành công |

Trong mongosh, đừng mặc định **insertMany()** luôn trả thêm **insertedCount** giống Node.js Driver. Các wrapper có API khác nhau.

### 6.2. Kết quả tùy driver

| Công cụ | Kết quả insertOne thành công | Kết quả insertMany thành công |
| --- | --- | --- |
| **mongosh** | acknowledged, insertedId | acknowledged, insertedIds |
| **Node.js Driver** | acknowledged, insertedId | acknowledged, insertedCount, insertedIds |
| **PyMongo** | acknowledged, inserted_id | acknowledged, inserted_ids |
| **Java Sync Driver** | wasAcknowledged(), getInsertedId() | wasAcknowledged(), getInsertedIds() |

Trong Java, **getInsertedIds()** trả về map với key là chỉ số đầu vào; trong PyMongo, **inserted_ids** là danh sách theo thứ tự document đầu vào. Node.js dùng object/map ID theo index và còn cung cấp **insertedCount** ở successful result.

Không nên chuyển nguyên một đoạn code dùng **result.insertedIds** từ Node.js sang Python hoặc Java mà không điều chỉnh API của driver.

### 6.3. Write result khác số document còn tồn tại

Số lượng document được thêm trong một kết quả ghi không nhất thiết bằng số document đang tồn tại mãi về sau. Sau khi insert, thao tác khác có thể xóa, thay thế hoặc di chuyển dữ liệu theo các cơ chế hợp lệ.

**insertedCount** của Node.js Driver là thông tin về **thao tác insert được xác nhận**, không phải phép đếm toàn collection và không phải một snapshot vĩnh viễn của hệ thống.

Nếu muốn đếm số document hiện tại, dùng truy vấn đếm phù hợp với filter và các lựa chọn nhất quán, chẳng hạn:

~~~javascript
db.books.countDocuments({
  category: "Database"
});
~~~

Lệnh đếm thực hiện truy vấn mới, không phải thành phần của result insert.

## 7. Một thao tác insert có thể thất bại vì những lý do nào?

### 7.1. Trùng unique key

MongoDB có thể từ chối document nếu vi phạm unique index, phổ biến nhất là trùng **_id**.

~~~javascript
db.accounts.insertOne({
  _id: "ACC-001",
  email: "an@example.test"
});

db.accounts.insertOne({
  _id: "ACC-001",
  email: "binh@example.test"
});
~~~

Lệnh thứ hai, nếu lệnh đầu đã thành công, thường báo lỗi:

~~~text
E11000 duplicate key error
~~~

Nếu collection có unique index trên **email**, các document có _id khác nhau cũng có thể vi phạm uniqueness khi email trùng.

### 7.2. Schema validation

Collection có thể áp dụng validation rule, ví dụ chỉ cho phép giá là số decimal hoặc yêu cầu một số field bắt buộc.

Nếu document không hợp lệ, server có thể từ chối thao tác với **document validation failure**. Khi dùng insertMany, lỗi validation ở một document cũng có thể dẫn đến partial success tùy thứ tự xử lý và chế độ ordered.

Ví dụ tạo collection với validation:

~~~javascript
db.createCollection("catalogValidated", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["sku", "title", "price"],
      properties: {
        sku: { bsonType: "string" },
        title: { bsonType: "string" },
        price: { bsonType: "decimal" }
      }
    }
  }
});
~~~

Insert hợp lệ:

~~~javascript
db.catalogValidated.insertOne({
  sku: "BOOK-101",
  title: "Nhập môn BSON",
  price: NumberDecimal("179000.00")
});
~~~

Insert sau có thể bị từ chối vì **price** là string:

~~~javascript
db.catalogValidated.insertOne({
  sku: "BOOK-102",
  title: "Sai kiểu dữ liệu",
  price: "179000"
});
~~~

Sự tồn tại của **_id** được MongoDB xử lý độc lập với validation trên những field nghiệp vụ đã định nghĩa.

### 7.3. Kích thước hoặc định dạng BSON không hợp lệ

Một BSON document thông thường có giới hạn kích thước **16 MiB**. Ghi document quá lớn hoặc dữ liệu không thể mã hóa hợp lệ thành BSON có thể thất bại.

Trong một số tình huống, lỗi xuất hiện **ở driver trước khi gửi request**; trong tình huống khác, server có thể từ chối. Vì vậy không nên giả định mọi lỗi insert đều được trả về dưới một hình thức giống nhau.

### 7.4. Lỗi kết nối, quyền hoặc write concern

Một số trường hợp khác:

- User không có quyền insert vào collection.
- Server không sẵn sàng hoặc connection bị ngắt.
- Primary thay đổi trong lúc ghi.
- Write concern yêu cầu mức xác nhận chưa đạt hoặc timeout.
- Transaction chứa insert bị abort.

Với lỗi mạng không rõ kết quả, ứng dụng có thể rơi vào trạng thái **không chắc server đã thực hiện insert hay chưa**. Không thể luôn kết luận “không thấy success response thì chắc chắn chưa ghi”. Phải thiết kế cơ chế retry và đối chiếu an toàn.

## 8. Xử lý bulk write error và partial success

Giả sử application insert một batch gồm 4 document:

~~~text
D0: hợp lệ
D1: vi phạm unique index
D2: hợp lệ
D3: hợp lệ
~~~

**ordered: true** có thể dẫn đến D0 thành công, D1 thất bại và D2/D3 chưa được xử lý.

**ordered: false** có thể dẫn đến D0, D2, D3 thành công và D1 thất bại. Nhưng nếu gặp lỗi mạng hoặc loại lỗi làm dừng batch, kết quả cần được xác minh theo tình huống thực tế.

### 8.1. Bắt lỗi trong mongosh

Ví dụ dùng collection thử nghiệm với các _id có chủ đích:

~~~javascript
try {
  db.bulkDemo.insertMany(
    [
      { _id: "BATCH-001", value: 1 },
      { _id: "BATCH-001", value: 2 },
      { _id: "BATCH-003", value: 3 }
    ],
    { ordered: false }
  );

  print("Batch hoàn toàn thành công");
} catch (error) {
  print("Có lỗi insertMany:");
  print(error.message);

  // Quan sát các thuộc tính mà phiên bản mongosh cung cấp.
  printjson(error);
}
~~~

Ví dụ giả định collection không có các ID này từ trước. Tùy phiên bản mongosh và driver, đối tượng lỗi có thể chứa **writeErrors**, số thao tác đã insert, index của thao tác lỗi hoặc chi tiết khác. Không nên viết code production dựa trên hình dạng lỗi mà chưa đối chiếu API phiên bản đang dùng.

### 8.2. Đối chiếu dữ liệu đã lưu

Sau khi gặp lỗi một phần, có thể kiểm tra các _id cụ thể:

~~~javascript
db.bulkDemo.find({
  _id: {
    $in: ["BATCH-001", "BATCH-003"]
  }
});
~~~

Kết quả đọc này giúp xác minh trạng thái hiện tại trong collection. Trong hệ thống có nhiều writer, cần tính đến các thao tác khác đang xảy ra và lựa chọn mức nhất quán khi đọc.

Nếu cần xử lý chính xác một batch lớn, hãy cấp cho từng input **một khóa định danh ổn định**, lưu mapping giữa input và _id, rồi ghi nhận trạng thái đã xử lý. Chỉ dựa vào vị trí trong array có thể không đủ khi chương trình cần retry sau lỗi mạng.

### 8.3. Phân biệt lỗi từng document với lỗi tổng thể

| Loại lỗi | Tình huống | Điều cần lưu ý |
| --- | --- | --- |
| Duplicate key | Một _id hoặc unique value đã tồn tại | Document đó bị từ chối; các document khác có thể đã ghi |
| Validation error | Document không thỏa schema | Tùy ordered, các document khác có thể được xử lý |
| Lỗi encode BSON | Giá trị client không thể tuần tự hóa | Có thể xảy ra trước khi gửi request |
| Write concern error | Mức xác nhận yêu cầu chưa đạt | Write có thể đã được áp dụng dù ứng dụng nhận lỗi |
| Network/server error | Mất kết nối hoặc thay đổi topology | Trạng thái ghi có thể không chắc chắn |
| Transaction abort | Transaction không được commit | Các thay đổi thuộc transaction không được commit |

Không nên xử lý tất cả các lỗi như “chưa có gì được ghi”. Trạng thái thực tế phụ thuộc loại lỗi, topology và chế độ ghi.

## 9. Write concern và acknowledged

MongoDB có cơ chế **write concern** mô tả mức xác nhận thao tác ghi mà client yêu cầu. Ví dụ phổ biến:

- **w: 1**: primary xác nhận đã xử lý thao tác ghi theo yêu cầu.
- **w: "majority"**: chờ xác nhận theo quy tắc majority của replica set.
- **j: true**: yêu cầu cơ chế xác nhận liên quan đến journal theo cấu hình.
- **wtimeout**: giới hạn thời gian chờ đáp ứng write concern.

Không nên đồng nhất **acknowledged: true** với **majority acknowledged**: giá trị true còn phụ thuộc loại write concern mà lệnh hoặc client cấu hình.

### 9.1. Ví dụ chỉ định writeConcern trong mongosh

~~~javascript
db.auditEvents.insertOne(
  {
    eventType: "LOGIN",
    occurredAt: new Date()
  },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
~~~

Ví dụ yêu cầu mức xác nhận majority và thời gian chờ nhất định. Nếu không thể đáp ứng write concern trong điều kiện hiện tại, thao tác có thể báo **write concern error**. Điều đó không tự chứng minh document chưa được ghi vào primary.

### 9.2. Unacknowledged write

Khi sử dụng write concern **w: 0**, client không yêu cầu server trả xác nhận kết quả ghi theo cơ chế thông thường.

Trong các driver, successful result của thao tác không được xác nhận thường có **acknowledged: false** hoặc thuộc tính tương ứng, và một số accessor như insertedId/insertedIds có thể không được phép đọc.

Ví dụ khái niệm:

~~~text
Client gửi insert với w: 0
        |
        v
Không chờ xác nhận thao tác ghi từ server
        |
        v
Client không có bằng chứng phản hồi để kết luận từng document đã được ghi
~~~

**w: 0 không phù hợp khi ứng dụng phải biết chắc từng insert đã thành công.** Trong hệ thống nghiệp vụ, cần cân nhắc write concern và độ tin cậy mà người dùng mong đợi trước khi tối ưu độ trễ.

## 10. Ví dụ ứng dụng Java: InsertOneResult và InsertManyResult

MongoDB Java Sync Driver có các kiểu result riêng và cách gọi khác với mongosh.

### 10.1. insertOne() bằng Java

~~~java
import com.mongodb.MongoClientSettings;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;

import com.mongodb.client.result.InsertOneResult;
import org.bson.Document;
import org.bson.BsonValue;

public class InsertOneExample {
    public static void main(String[] args) {
        String uri = "mongodb://localhost:27017";

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("bookstore");
            MongoCollection<Document> books = db.getCollection("books");

            Document book = new Document("isbn", "9786040000301")
                    .append("title", "Java làm việc với MongoDB")
                    .append("price", 199000)
                    .append("stock", 5);

            InsertOneResult result = books.insertOne(book);

            System.out.println("Acknowledged: " + result.wasAcknowledged());

            if (result.wasAcknowledged()) {
                BsonValue id = result.getInsertedId();
                System.out.println("Inserted ID: " + id);
            }
        }
    }
}
~~~

**InsertOneResult** cung cấp:

- **wasAcknowledged()**: thao tác có được xác nhận không.
- **getInsertedId()**: giá trị BSON của _id khi có kết quả được xác nhận.

Nếu được cấu hình unacknowledged, một số phương thức đọc thông tin cụ thể có thể không sử dụng được. Vì vậy code minh họa kiểm tra **wasAcknowledged()** trước.

Ví dụ giả định MongoDB đang chạy, cấu hình kết nối cho phép ghi và project có dependency Java Sync Driver phù hợp.

### 10.2. insertMany() bằng Java

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.InsertManyOptions;
import com.mongodb.client.result.InsertManyResult;

import org.bson.Document;
import org.bson.BsonValue;

import java.util.Arrays;
import java.util.List;
import java.util.Map;

public class InsertManyExample {
    public static void main(String[] args) {
        try (MongoClient client = MongoClients.create(
                "mongodb://localhost:27017")) {

            MongoDatabase db = client.getDatabase("bookstore");
            MongoCollection<Document> books = db.getCollection("books");

            List<Document> documents = Arrays.asList(
                new Document("isbn", "9786040000401")
                    .append("title", "Bài học A"),
                new Document("isbn", "9786040000402")
                    .append("title", "Bài học B")
            );

            InsertManyResult result = books.insertMany(
                documents,
                new InsertManyOptions().ordered(false)
            );

            System.out.println("Acknowledged: " + result.wasAcknowledged());

            if (result.wasAcknowledged()) {
                Map<Integer, BsonValue> ids = result.getInsertedIds();

                for (Map.Entry<Integer, BsonValue> entry : ids.entrySet()) {
                    System.out.println(
                        "Input index = " + entry.getKey()
                        + ", _id = " + entry.getValue()
                    );
                }
            }
        }
    }
}
~~~

**getInsertedIds()** trả về map gắn **index của document đầu vào** với _id BSON. Điều này giúp kết nối kết quả insert với danh sách input ban đầu.

Nếu batch xảy ra lỗi, phương thức **insertMany** có thể ném **MongoBulkWriteException** hoặc ngoại lệ thích hợp, thay vì trả **InsertManyResult** thành công như ví dụ. Chương trình cần có nhánh xử lý lỗi riêng nếu muốn hỗ trợ partial success.

### 10.3. Java xử lý bulk exception

Ví dụ mẫu xử lý lỗi đối với một lệnh insertMany:

~~~java
import com.mongodb.MongoBulkWriteException;

// Các import MongoDB Java khác giống ví dụ phía trên.

try {
    books.insertMany(
        documents,
        new InsertManyOptions().ordered(false)
    );
} catch (MongoBulkWriteException e) {
    System.out.println(
        "Số insert được ghi nhận: "
        + e.getWriteResult().getInsertedCount()
    );

    e.getWriteErrors().forEach(error -> {
        System.out.println(
            "Input index = " + error.getIndex()
            + ", error code = " + error.getCode()
        );
    });
}
~~~

Đây là **đoạn code minh họa xử lý exception trong ngữ cảnh đã tạo books/documents**. Nó không bao phủ mọi lỗi (ví dụ network exception), không bảo đảm các chỉ số thành công có thể tái tạo từ mỗi thông báo lỗi và không thay thế việc thiết kế retry/idempotency cho hệ thống thật.

## 11. Ví dụ Node.js: result có insertedCount

Node.js Driver thường cung cấp các trường result khác biệt đôi chút.

~~~javascript
import { MongoClient } from "mongodb";

const client = new MongoClient("mongodb://localhost:27017");

async function run() {
  await client.connect();

  try {
    const books = client.db("bookstore").collection("books");

    const one = await books.insertOne({
      isbn: "9786040000501",
      title: "Node.js và MongoDB"
    });

    console.log(one.acknowledged);
    console.log(one.insertedId);

    const many = await books.insertMany(
      [
        { isbn: "9786040000502", title: "Sách Node A" },
        { isbn: "9786040000503", title: "Sách Node B" }
      ],
      { ordered: true }
    );

    console.log(many.acknowledged);
    console.log(many.insertedCount);
    console.log(many.insertedIds);
  } finally {
    await client.close();
  }
}

run().catch(console.error);
~~~

Khi **insertMany** thành công và được xác nhận, Node.js result thường chứa:

~~~javascript
{
  acknowledged: true,
  insertedCount: 2,
  insertedIds: {
    "0": ObjectId("674000000000000000000501"),
    "1": ObjectId("674000000000000000000502")
  }
}
~~~

Hai ID ở trên là minh họa. Trường **insertedCount** thuận tiện để biết số document đã được chèn trong successful result; **insertedIds** dùng để đối chiếu từng document theo index.

Đối với lỗi hàng loạt, Node.js có thể trả một **MongoBulkWriteError** kèm thông tin lỗi và kết quả từng phần, tùy API và phiên bản. Không thể dựa vào nhánh **then/success** để xử lý một batch đã báo lỗi.

## 12. Ví dụ Python/PyMongo: snake_case và danh sách ID

PyMongo dùng tên thuộc tính theo phong cách Python.

~~~python
from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017")
books = client["bookstore"]["books"]

one = books.insert_one({
    "isbn": "9786040000601",
    "title": "Python và MongoDB"
})

print("Acknowledged:", one.acknowledged)
print("Inserted ID:", one.inserted_id)

many = books.insert_many(
    [
        {"isbn": "9786040000602", "title": "Sách Python A"},
        {"isbn": "9786040000603", "title": "Sách Python B"}
    ],
    ordered=False
)

print("Acknowledged:", many.acknowledged)
print("Inserted IDs:", many.inserted_ids)
~~~

**inserted_ids** là **list ID theo thứ tự document trong input**. Ví dụ:

~~~python
[
    ObjectId("674000000000000000000601"),
    ObjectId("674000000000000000000602")
]
~~~

Nếu **insert_many** phát sinh lỗi ghi ở một hoặc nhiều document, PyMongo có thể ném **BulkWriteError**. Để xử lý thông tin, chương trình có thể đọc chi tiết ngoại lệ:

~~~python
from pymongo.errors import BulkWriteError

try:
    books.insert_many(
        [
            {"_id": "P-001", "title": "A"},
            {"_id": "P-001", "title": "B"},
            {"_id": "P-003", "title": "C"}
        ],
        ordered=False
    )
except BulkWriteError as error:
    details = error.details

    print("nInserted:", details.get("nInserted"))
    print("writeErrors:", details.get("writeErrors", []))
~~~

Giả sử collection chưa chứa các _id này, một record trùng _id sẽ tạo lỗi. **nInserted** và **writeErrors** phản ánh thông tin driver nhận được cho lệnh ghi, không thay thế việc đối chiếu nếu gặp lỗi kết nối không rõ kết quả.

## 13. Hiệu năng và kích thước batch

insertMany giúp giảm số lượt gọi giữa client và server so với việc thực hiện nhiều insertOne tuần tự, nhưng không vì thế mà batch càng lớn càng tốt.

### 13.1. Lý do dùng insertMany

Nếu ứng dụng có 1.000 sự kiện độc lập:

~~~text
Cách A:
  1.000 lần gọi insertOne riêng biệt

Cách B:
  Tập hợp sự kiện thành các batch
  Gọi insertMany theo từng batch
~~~

Batch có thể giảm overhead mạng và tận dụng xử lý hàng loạt của driver/server. Với dữ liệu độc lập và xử lý lỗi phù hợp, **ordered: false** cũng có thể giúp tăng tính linh hoạt khi một phần document bị từ chối.

### 13.2. Giới hạn và chia batch

MongoDB có giới hạn kích thước BSON document và giới hạn cho một write batch. Driver có thể **tự chia request lớn thành nhiều batch** theo các giới hạn của server/protocol.

Vì thế:

- Không giả định một lần gọi API insertMany tương ứng đúng một gói tin mạng.
- Không gom toàn bộ dữ liệu cực lớn vào một array vô hạn trong RAM.
- Chọn kích thước batch phù hợp với số lượng document, kích thước document, tốc độ xử lý lỗi và giới hạn tài nguyên.
- Giữ mapping giữa document đầu vào với khóa định danh để có thể xử lý một phần batch thất bại.

Ngay cả khi API driver gửi nhiều batch nội bộ, tính nguyên tử vẫn là **từng document** trừ khi các thao tác được bao trong transaction phù hợp.

### 13.3. ordered=false không phải là transaction song song

Tùy chọn **ordered: false** cho phép các thao tác không bị ràng buộc thứ tự xử lý nghiêm ngặt, nhưng không có nghĩa mỗi document được xử lý trong một transaction độc lập có thể rollback cả lô. Nó là lựa chọn về **cách xử lý batch khi có lỗi và thứ tự thực thi**, không phải cam kết về tính nguyên tử toàn batch.

### 13.4. Ảnh hưởng của index

Mỗi document insert phải cập nhật những index liên quan. Nếu collection có nhiều index, chi phí ghi có thể cao hơn, dù index giúp tăng tốc truy vấn. Khi import khối lượng dữ liệu lớn, chiến lược index cần cân đối giữa chi phí nạp dữ liệu, bảo đảm uniqueness và nhu cầu đọc.

Không được loại bỏ unique index chỉ để tăng tốc import nếu điều đó làm mất ràng buộc quan trọng của nghiệp vụ.

## 14. Insert và transaction: khi nào cần all-or-nothing?

Giả sử quy trình nghiệp vụ bắt buộc tạo đồng thời:

- Một document **orders**.
- Một document **orderAudits**.
- Một document **inventoryReservations**.

Nếu insert thành công ở hai collection nhưng thất bại ở collection còn lại, hệ thống có thể rơi vào trạng thái thiếu nhất quán theo yêu cầu nghiệp vụ.

Có thể dùng **multi-document transaction** trên deployment hỗ trợ để nhóm những thao tác cần commit hoặc abort cùng nhau.

### Ví dụ Node.js với session

~~~javascript
import { MongoClient } from "mongodb";

const client = new MongoClient("mongodb://localhost:27017");

async function createOrder() {
  await client.connect();

  const session = client.startSession();

  try {
    const database = client.db("bookstore");

    await session.withTransaction(async () => {
      await database.collection("orders").insertOne(
        {
          _id: "ORD-1001",
          customerId: "CUS-101",
          status: "CREATED",
          createdAt: new Date()
        },
        { session }
      );

      await database.collection("orderAudits").insertOne(
        {
          orderId: "ORD-1001",
          action: "CREATE",
          occurredAt: new Date()
        },
        { session }
      );
    });

    console.log("Transaction committed");
  } finally {
    await session.endSession();
    await client.close();
  }
}

createOrder().catch(console.error);
~~~

Ví dụ cần MongoDB replica set hoặc sharded cluster có hỗ trợ transaction và cấu hình kết nối phù hợp. Một mongod standalone đơn lẻ không phải môi trường thực hành transaction này.

**Không gửi email hay gọi cổng thanh toán bên trong callback transaction mà mặc định chúng sẽ rollback nếu transaction abort.** Callback có thể được retry và những tác động ngoài MongoDB cần cơ chế idempotency/điều phối riêng.

### Khi không cần transaction

Không phải mọi insertMany đều cần transaction. Nếu nạp các document sự kiện độc lập, xử lý từng document thành công hoặc thất bại riêng có thể đúng với nghiệp vụ. Khi đó **ordered: false**, ghi nhận lỗi và đối chiếu batch là lựa chọn hợp lý.

Chỉ nên dùng transaction khi có **bất biến yêu cầu nhiều document phải cùng commit hoặc cùng abort**, vì transaction có chi phí vận hành và cơ chế retry riêng.

## 15. Chống tạo trùng và retry an toàn

Lỗi mạng có thể xảy ra **sau khi server đã thực thi insert nhưng trước khi client nhận phản hồi**. Trong trường hợp đó, ứng dụng không biết chắc document đã lưu hay chưa.

Nếu retry bằng cách tạo một ObjectId mới cho cùng sự kiện nghiệp vụ, hệ thống có thể tạo bản ghi trùng về ý nghĩa dù _id khác nhau.

### 15.1. Khóa định danh ổn định

Ví dụ mỗi yêu cầu tạo đơn có một **requestId** duy nhất do client hoặc server xác định ổn định:

~~~javascript
db.orders.createIndex(
  { requestId: 1 },
  { unique: true }
);

db.orders.insertOne({
  requestId: "REQ-2025-1001",
  customerId: "CUS-101",
  status: "CREATED",
  createdAt: new Date()
});
~~~

Nếu một request bị gửi lại với cùng **requestId**, unique index giúp ngăn nhiều document cùng lưu một mã yêu cầu. Ứng dụng cần phân biệt:

- Duplicate key do **retry đúng request đã thành công trước đó**.
- Duplicate key do **hai request khác nhau bị gán cùng requestId**.
- Lỗi ghi thực sự chưa tạo được document.

Không nên tự động diễn giải mọi duplicate key là “thành công” mà chưa xác minh khóa, nội dung và quy tắc idempotency.

### 15.2. Retryable writes

Một số driver hỗ trợ **retryable writes** theo mặc định trong những topology đủ điều kiện. Cơ chế này có thể xử lý một số lỗi tạm thời mà không tạo thao tác lặp không mong muốn, theo các điều kiện do MongoDB và driver quy định.

Tuy vậy, **retryable writes không thay thế khóa nghiệp vụ/idempotency**. Ứng dụng vẫn phải đối phó với tình huống người dùng gửi cùng hành động hai lần hoặc request được tạo lại với session/ID mới.

### 15.3. Quy trình xử lý kết quả đáng tin cậy

~~~text
Tạo document + khóa nghiệp vụ ổn định
            |
            v
        Gửi insert
            |
      +-----+------+
      |            |
   Thành công     Lỗi
      |            |
  Lưu ID        Xác định loại lỗi
                   |
          +--------+---------+
          |                  |
   Duplicate key       Mạng/write concern
          |                  |
   Đối chiếu khóa      Trạng thái có thể mơ hồ
   và nội dung         -> tra cứu, retry an toàn
          |
     Trả trạng thái nghiệp vụ phù hợp
~~~

Không dùng **insertedId** đơn lẻ làm chứng cứ về việc một nghiệp vụ đã hoàn tất nếu quy trình còn phụ thuộc những thao tác khác.

## 16. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| insertOne tự cập nhật nếu _id đã tồn tại | insertOne thêm document mới; trùng khóa dẫn đến lỗi |
| insertMany là transaction vì gửi một lệnh API | Mỗi document được ghi nguyên tử riêng; cả batch không mặc nhiên all-or-nothing |
| insertMany báo lỗi nghĩa là không gì được ghi | Có thể thành công một phần trước hoặc bên cạnh lỗi |
| ordered=false bỏ qua lỗi và trả success | Lệnh vẫn có thể báo lỗi tổng hợp; cần xử lý partial success |
| ordered=true tự rollback các insert trước lỗi | Nó dừng ở lỗi đầu tiên nhưng không tự rollback document đã ghi |
| insertedIds là danh sách vị trí được ghi theo thứ tự bất biến ở mọi driver | Dạng result khác nhau; mongosh/Node.js dùng mapping theo index, PyMongo dùng list |
| insertedId là số document | insertedId là khóa _id của document được thêm |
| _id luôn là ObjectId | Ứng dụng có thể dùng string, UUID và các loại hợp lệ khác |
| acknowledged=true đồng nghĩa majority acknowledged | Mức xác nhận phụ thuộc write concern |
| Lỗi network luôn nghĩa là server chưa insert | Có thể server đã ghi nhưng phản hồi bị mất |
| Dùng w:0 vẫn biết chắc từng record đã được lưu | Không yêu cầu acknowledgement nên không có bằng chứng phản hồi cho kết luận đó |
| insertMany luôn gửi đúng một request tới server | Driver có thể chia batch theo giới hạn hệ thống |
| Unique index hiểu các document trùng nghĩa nghiệp vụ | Index bảo vệ giá trị key được cấu hình, không tự suy ra quan hệ nghiệp vụ |
| Có insertedId thì toàn workflow tạo đơn đã xong | Insert chỉ xác nhận phần ghi document đó, không tự xác nhận thanh toán hay hành động ngoài database |

## 17. Bài thực hành với mongosh

Các bài sau sử dụng database thử nghiệm **insert_lab**. Hãy chạy trên môi trường học tập tách biệt với dữ liệu production.

### Bài 1: thêm một document và đọc result

~~~javascript
use insert_lab

const one = db.students.insertOne({
  studentCode: "SV001",
  fullName: "Nguyễn Mai",
  active: true,
  createdAt: new Date()
});

printjson(one);

db.students.findOne({ _id: one.insertedId });
~~~

Trả lời:

1. **acknowledged** có giá trị gì?
2. **insertedId** có phải field studentCode không?
3. Khi không cung cấp _id, document lưu sẽ có _id như thế nào?
4. Có thể sử dụng **one.insertedId** để truy vấn record vừa thêm không?

### Bài 2: thêm nhiều document

~~~javascript
const many = db.students.insertMany([
  {
    studentCode: "SV002",
    fullName: "Trần Bình",
    active: true
  },
  {
    studentCode: "SV003",
    fullName: "Lê An",
    active: false
  }
]);

printjson(many);
~~~

Quan sát các key **"0"** và **"1"** của **insertedIds**, rồi xác định document đầu vào mà chúng tương ứng.

### Bài 3: trùng _id với ordered=true

~~~javascript
try {
  db.orderedExercise.insertMany(
    [
      { _id: "EX-01", score: 10 },
      { _id: "EX-01", score: 20 },
      { _id: "EX-03", score: 30 }
    ],
    { ordered: true }
  );
} catch (error) {
  print(error.message);
}

db.orderedExercise.find().sort({ _id: 1 });
~~~

Chạy trên collection chưa có các _id này để thấy rõ kết quả. Hãy giải thích vì sao **EX-03** không được thêm dù bản thân document này không trùng khóa.

### Bài 4: trùng _id với ordered=false

~~~javascript
try {
  db.unorderedExercise.insertMany(
    [
      { _id: "EX-01", score: 10 },
      { _id: "EX-01", score: 20 },
      { _id: "EX-03", score: 30 }
    ],
    { ordered: false }
  );
} catch (error) {
  print(error.message);
}

db.unorderedExercise.find().sort({ _id: 1 });
~~~

Hãy chỉ ra sự khác biệt với Bài 3. Vì sao việc có document **EX-03** không đồng nghĩa toàn batch thành công?

### Bài 5: dùng _id chủ động

~~~javascript
const result = db.lessons.insertOne({
  _id: "MONGODB-INSERT-01",
  title: "insertOne và insertMany"
});

printjson(result);
~~~

So sánh **insertedId** ở Bài 5 với Bài 1. Trả lời khi nào chọn _id do client tạo thay vì ObjectId tự sinh.

### Bài 6: thiết kế retry

Giả sử service gửi yêu cầu tạo người dùng:

~~~text
requestId = REQ-001
email = member@example.test
~~~

MongoDB đã lưu document nhưng client mất kết nối trước khi nhận response. Service không biết chắc request thành công hay chưa.

Hãy đề xuất:

1. Khóa nghiệp vụ nào nên được giữ ổn định qua retry?
2. Unique index cần đặt trên field nào để bảo vệ quy tắc không tạo trùng?
3. Khi retry nhận duplicate key, cần xác minh điều gì?
4. Tại sao tạo ObjectId mới mỗi lần retry có thể dẫn tới bản ghi trùng?
5. Trường hợp nào ứng dụng nên đọc lại trạng thái trước khi trả kết quả cho người dùng?

**Điểm cần ghi nhớ:** insertOne và insertMany giúp thêm dữ liệu mới vào collection, nhưng khi xây dựng hệ thống thật cần hiểu **ranh giới nguyên tử theo document, thứ tự xử lý batch, cấu trúc result của driver, write concern và khả năng ghi thành công một phần**. Chỉ khi phân biệt được các khía cạnh này, ứng dụng mới xử lý insert và retry một cách đáng tin cậy.

## Tài liệu tham khảo

- [MongoDB Manual — db.collection.insertOne()](https://www.mongodb.com/docs/manual/reference/method/db.collection.insertOne/)
- [MongoDB Manual — db.collection.insertMany()](https://www.mongodb.com/docs/manual/reference/method/db.collection.insertMany/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Java Sync Driver — Insert Documents](https://www.mongodb.com/docs/drivers/java/sync/current/usage-examples/insertOne/)
- [PyMongo — insert_one and insert_many](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/write/insert/)

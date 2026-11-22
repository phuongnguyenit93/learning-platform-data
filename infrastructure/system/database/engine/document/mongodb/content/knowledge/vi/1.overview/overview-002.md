# MongoDB: Database, Collection, Document, Field và Namespace

MongoDB là hệ quản trị cơ sở dữ liệu hướng tài liệu (document database). Thay vì bắt đầu từ bảng và hàng như khi học cơ sở dữ liệu quan hệ, MongoDB tổ chức dữ liệu thành **database → collection → document → field**. Mỗi collection còn có một **namespace** để MongoDB phân biệt nó với các collection khác trong hệ thống.

Nắm được năm khái niệm này giúp bạn đọc đúng cấu trúc dữ liệu, viết truy vấn chính xác và quyết định nên đặt thông tin ở đâu khi thiết kế ứng dụng.

## 1. Bức tranh tổng thể: dữ liệu nằm ở đâu?

Giả sử xây dựng hệ thống bán sách. Một triển khai MongoDB có thể chứa database **bookstore**; trong database đó có các collection **books**, **customers** và **orders**; mỗi collection chứa các document; mỗi document chứa các field.

~~~text
MongoDB deployment
└── Database: bookstore
    ├── Collection: books                  Namespace: bookstore.books
    │   ├── Document: sách A
    │   │   ├── _id
    │   │   ├── title
    │   │   ├── price
    │   │   ├── author
    │   │   │   ├── name
    │   │   │   └── country
    │   │   └── tags
    │   └── Document: sách B
    ├── Collection: customers              Namespace: bookstore.customers
    │   └── Document: khách hàng A
    └── Collection: orders                 Namespace: bookstore.orders
        └── Document: đơn hàng A
~~~

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Database** | Nhóm logic các collection có liên quan | bookstore |
| **Collection** | Tập hợp các document trong cùng một database | books |
| **Document** | Bản ghi dữ liệu dạng cấu trúc BSON | Một cuốn sách có mã ISBN, tên, giá và tác giả |
| **Field** | Cặp tên–giá trị bên trong document | title, price, author.name |
| **Namespace** | Tên định danh đầy đủ của collection theo database | bookstore.books |

Đây là **cấu trúc logic** để làm việc với dữ liệu. Các khái niệm trên không nhất thiết tương ứng với một thư mục hay một tệp vật lý trên ổ đĩa.

## 2. Database: không gian tổ chức dữ liệu

**Database** là đơn vị tổ chức logic chứa các collection. Một MongoDB deployment có thể quản lý nhiều database; các database có thể có collection trùng tên mà vẫn độc lập về định danh.

Ví dụ:

~~~text
bookstore.books
bookstore.orders
analytics.events
analytics.reports
~~~

Trong trường hợp này, **bookstore** và **analytics** là hai database; **books**, **orders**, **events**, **reports** là các collection.

### Chọn database trong mongosh

Trong MongoDB Shell (**mongosh**), lệnh sau chuyển ngữ cảnh hiện tại sang database **bookstore**:

~~~javascript
use bookstore
~~~

Có thể kiểm tra ngữ cảnh và liệt kê collection:

~~~javascript
db.getName()
db.getCollectionNames()
show dbs
~~~

Cần phân biệt ba hành động:

- **use bookstore** chỉ chọn database để thực hiện lệnh tiếp theo. Nó không tự bảo đảm rằng database đã được lưu thành một database có dữ liệu.
- Một database có thể xuất hiện khi dữ liệu hoặc collection được tạo thực sự, chẳng hạn sau thao tác ghi hợp lệ.
- **show dbs** liệt kê các database mà tài khoản hiện tại có quyền nhìn thấy; kết quả cũng phụ thuộc vào việc database đã có dữ liệu hay metadata được tạo hay chưa.

Bạn cũng có thể truy cập database khác mà không thay đổi cách tư duy về cấu trúc dữ liệu:

~~~javascript
const reportingDb = db.getSiblingDB("analytics");
reportingDb.getCollectionNames();
~~~

### Khi nào nên tách database?

Tách database hữu ích khi có những vùng dữ liệu khác nhau về ứng dụng, quyền truy cập, yêu cầu quản trị hoặc vòng đời vận hành. Tuy nhiên, **database không tự tạo ranh giới bảo mật tuyệt đối**: quyền truy cập cần được cấu hình bằng cơ chế xác thực và phân quyền của MongoDB.

Không nên mặc định tạo một database mới cho từng loại document. Nếu các loại dữ liệu thuộc cùng một ứng dụng và cần được quản lý chung, nhiều collection trong một database thường là điểm khởi đầu dễ hiểu.

## 3. Collection: nhóm các document

**Collection** là tập hợp document nằm trong một database. Collection gần với khái niệm *table* trong cơ sở dữ liệu quan hệ, nhưng các document trong collection **không bắt buộc có bộ field giống hệt nhau**.

Ví dụ, hai document trong collection **books** có thể khác nhau:

~~~javascript
{
  title: "MongoDB căn bản",
  price: 180000,
  authors: ["Nguyễn An"]
}

{
  title: "Thiết kế dữ liệu document",
  price: 240000,
  authors: ["Trần Bình"],
  ebookAvailable: true,
  editions: [1, 2]
}
~~~

Document thứ hai có thêm **ebookAvailable** và **editions**. Đây là đặc điểm của mô hình dữ liệu linh hoạt (*flexible schema*). Tuy nhiên, linh hoạt không đồng nghĩa với việc nên để mọi document có cấu trúc tùy ý: ứng dụng vẫn cần thống nhất về ý nghĩa field, kiểu dữ liệu và những ràng buộc cần thiết.

### Tạo và xem collection

~~~javascript
use bookstore

// Tạo collection một cách tường minh.
db.createCollection("books");

// Xem danh sách collection trong database hiện tại.
show collections

// Lấy đối tượng collection để truy vấn.
db.getCollection("books")
~~~

Trong các trường hợp ghi thông thường, MongoDB có thể tự tạo collection khi insert document đầu tiên vào một collection chưa tồn tại:

~~~javascript
db.customers.insertOne({
  name: "Lê Minh",
  memberSince: new Date()
});
~~~

Để cấu hình loại collection hoặc các tùy chọn đặc biệt, việc tạo tường minh có thể cần thiết.

### Collection quản lý những gì?

- **Tập document** thuộc cùng một miền dữ liệu, chẳng hạn sách hoặc đơn hàng.
- **Index** phục vụ truy vấn và ràng buộc; index được định nghĩa cho collection, không tạo riêng cho mỗi document.
- **Validation rules** khi cần kiểm soát kiểu dữ liệu, field bắt buộc và cấu trúc được chấp nhận.
- Các tùy chọn riêng của collection tùy yêu cầu, ví dụ những loại collection chuyên biệt.

MongoDB thường tạo index trên field **_id** khi collection được tạo. Field này là cơ sở để định danh document trong collection. Khi dùng sharding, cần hiểu thêm các quy tắc riêng về phạm vi thực thi tính duy nhất của index.

Ví dụ thêm index duy nhất cho mã ISBN:

~~~javascript
db.books.createIndex(
  { isbn: 1 },
  { unique: true }
);
~~~

Index này giúp tránh hai document trong collection **books** có cùng giá trị **isbn** theo quy tắc của unique index. Một collection có thể có nhiều index cho các nhu cầu truy vấn khác nhau.

### Collection khác với một thư mục chứa JSON

Collection có các thao tác quản trị, index, truy vấn và chính sách xác thực/quyền. MongoDB lưu dữ liệu dưới dạng BSON và quản lý storage bằng engine của nó; việc so sánh collection với “thư mục chứa nhiều tệp JSON” chỉ là hình ảnh minh họa, không mô tả cách hệ thống lưu trữ thực tế.

## 4. Document: đơn vị dữ liệu cơ bản

**Document** là đơn vị dữ liệu dạng tập hợp các cặp **field–value**. Có thể hình dung document gần giống một object trong JavaScript hoặc một đối tượng dữ liệu trong ứng dụng Java, nhưng dữ liệu MongoDB được biểu diễn bằng **BSON (Binary JSON)**.

Ví dụ document biểu diễn một cuốn sách trong collection **bookstore.books**:

~~~javascript
{
  _id: ObjectId("6739a00a21f4b2a1c10e1111"),
  isbn: "9786040000123",
  title: "Nhập môn MongoDB",
  price: NumberDecimal("199000.00"),
  stock: 12,
  available: true,
  publishedAt: ISODate("2024-09-15T00:00:00Z"),
  author: {
    name: "Nguyễn An",
    country: "VN"
  },
  tags: ["database", "mongodb", "backend"],
  description: null
}
~~~

Document trên có:

- Các field đơn giản như **isbn**, **title**, **stock**, **available**.
- Một **embedded document** ở field **author**, chứa hai field con **name** và **country**.
- Một **array** ở field **tags**.
- Các kiểu BSON như **ObjectId**, **Decimal128** và **Date**.
- Một field **description** có giá trị **null**.

Ví dụ này dùng cú pháp hiển thị của mongosh. Khi xuất dữ liệu sang JSON thông thường hoặc Extended JSON, cách biểu diễn các kiểu BSON đặc biệt có thể khác.

### Vai trò của field _id

Mỗi document thuộc một collection thông thường cần có field **_id** làm định danh. Nếu client không cung cấp, driver hoặc MongoDB thường tạo giá trị tự động (phổ biến là **ObjectId**).

~~~javascript
db.books.insertOne({
  isbn: "9786040000123",
  title: "Nhập môn MongoDB",
  stock: 12
});
~~~

Sau khi insert, document đã lưu có thêm **_id**, dù thao tác insert ban đầu không khai báo field này.

**_id** không bắt buộc là ObjectId: có thể dùng những kiểu hợp lệ khác, chẳng hạn string, khi thiết kế có lý do rõ ràng. Tuy vậy, thay đổi chiến lược định danh cần được cân nhắc vì **_id** là giá trị định danh ổn định và không thể cập nhật bằng thao tác update thông thường.

Một giá trị **_id** có ý nghĩa trong phạm vi collection. Hai collection khác nhau có thể chứa document có cùng **_id**, vì namespace của chúng khác nhau.

### BSON khác JSON ra sao?

JSON thông thường có các kiểu phổ biến như string, number, boolean, null, object và array. BSON còn hỗ trợ các kiểu dữ liệu phục vụ database, trong đó có:

| Nhóm dữ liệu | Minh họa trong mongosh | Khi dùng |
| --- | --- | --- |
| String | "Nhập môn MongoDB" | Văn bản, mã định danh dạng chữ |
| Int32 / Int64 | NumberInt(12), NumberLong("9000000000") | Số nguyên theo phạm vi cần thiết |
| Double | 3.14 | Giá trị số thực khi phù hợp |
| Decimal128 | NumberDecimal("199000.00") | Giá trị thập phân cần độ chính xác, chẳng hạn tiền |
| Boolean | true | Trạng thái đúng/sai |
| Date | ISODate("2024-09-15T00:00:00Z") | Mốc thời gian |
| ObjectId | ObjectId("6739a00a21f4b2a1c10e1111") | Định danh thường dùng |
| Array | ["database", "mongodb"] | Danh sách giá trị |
| Embedded document | { name: "Nguyễn An" } | Nhóm dữ liệu con |
| Null | null | Giá trị null được lưu rõ ràng |

Không nên coi mọi số trong MongoDB là cùng một kiểu. Cùng một giá trị hiển thị có thể thuộc kiểu BSON khác nhau; điều này ảnh hưởng đến tính toán, chuyển đổi dữ liệu và cách ứng dụng xử lý.

**Giới hạn kích thước:** Một BSON document thông thường có kích thước tối đa **16 MiB**. Với dữ liệu lớn như tệp nhị phân, cần thiết kế phương thức lưu trữ thích hợp, ví dụ GridFS cho những trường hợp phù hợp, thay vì cố nhồi mọi nội dung vào một document.

### Embedded document và tham chiếu

MongoDB cho phép lưu dữ liệu liên quan trực tiếp trong document cha:

~~~javascript
{
  orderNumber: "ORD-1001",
  customer: {
    name: "Lê Minh",
    phone: "0900000000"
  },
  items: [
    { isbn: "9786040000123", quantity: 2, unitPrice: 199000 },
    { isbn: "9786040000456", quantity: 1, unitPrice: 150000 }
  ]
}
~~~

Cách này phù hợp khi các thành phần thường được đọc cùng nhau và có vòng đời gắn bó. Với quan hệ có số lượng phần tử rất lớn hoặc dữ liệu cần cập nhật độc lập, có thể lưu document ở collection riêng rồi tham chiếu bằng ID.

Ví dụ, một đơn hàng có thể lưu **customerId** trỏ đến document khách hàng ở **bookstore.customers**. MongoDB không tự biến mọi field chứa ID thành một khóa ngoại như hệ quản trị quan hệ; ứng dụng và thiết kế dữ liệu quyết định cách quản lý tính nhất quán. Aggregation có thể kết hợp dữ liệu giữa các collection bằng những cơ chế như **$lookup** khi phù hợp.

## 5. Field: tên và giá trị bên trong document

**Field** là một cặp gồm **tên field (key)** và **giá trị (value)**. Tên field dùng để xác định thông tin cần đọc, lọc hoặc cập nhật; giá trị có thể là kiểu BSON đơn giản hoặc cấu trúc lồng nhau.

Ví dụ:

~~~javascript
{
  title: "Nhập môn MongoDB",
  stock: 12,
  author: {
    name: "Nguyễn An",
    country: "VN"
  },
  tags: ["mongodb", "backend"]
}
~~~

Trong document này, **title**, **stock**, **author**, **tags** là field cấp cao nhất. **name** và **country** là field của document lồng trong **author**.

### Field và dot notation

MongoDB hỗ trợ **dot notation** để truy cập đường dẫn field lồng nhau:

~~~javascript
// Lọc các sách có tác giả thuộc VN.
db.books.find({ "author.country": "VN" });

// Chỉ trả về title và tên tác giả, ẩn _id.
db.books.find(
  { stock: { $gt: 0 } },
  { _id: 0, title: 1, "author.name": 1 }
);

// Cập nhật field con, giữ lại các field khác trong author.
db.books.updateOne(
  { isbn: "9786040000123" },
  { $set: { "author.country": "VN" } }
);
~~~

Trong ví dụ trên:

- **author** là field có giá trị là embedded document.
- **author.country** là *đường dẫn field* dùng để truy cập **country** bên trong **author**.
- **$gt** là toán tử “lớn hơn”, **$set** là toán tử cập nhật. Các ký hiệu bắt đầu bằng **$** ở đây là cú pháp toán tử của MongoDB.

**author.country không phải namespace.** Nó là tên đường dẫn trong một document. Namespace định danh collection ở cấp database, còn dot notation này truy cập cấu trúc bên trong document.

### Array cũng là giá trị của một field

~~~javascript
{
  title: "Nhập môn MongoDB",
  tags: ["database", "mongodb", "backend"],
  reviews: [
    { user: "an", stars: 5 },
    { user: "binh", stars: 4 }
  ]
}
~~~

Các truy vấn có thể tìm phần tử của array:

~~~javascript
// Khớp document nếu array tags có phần tử "mongodb".
db.books.find({ tags: "mongodb" });

// Tìm document có ít nhất một review có stars = 5.
db.books.find({ "reviews.stars": 5 });
~~~

Nếu cần buộc **nhiều điều kiện phải thỏa trên cùng một phần tử array**, dùng toán tử phù hợp như **$elemMatch**:

~~~javascript
db.books.find({
  reviews: {
    $elemMatch: { user: "an", stars: 5 }
  }
});
~~~

### Field không tồn tại khác field mang giá trị null

Hai document sau có ý nghĩa khác nhau:

~~~javascript
{ name: "An", email: null }
{ name: "Bình" }
~~~

Document đầu có field **email** được lưu với giá trị **null**. Document thứ hai **không có field email**.

Trong MongoDB, truy vấn sau thông thường khớp **cả field null lẫn field không tồn tại**:

~~~javascript
db.customers.find({ email: null });
~~~

Cần dùng toán tử phù hợp để phân biệt:

~~~javascript
// Chỉ document có field email, dù giá trị có thể là null.
db.customers.find({ email: { $exists: true } });

// Chỉ document có email mang kiểu BSON Null.
db.customers.find({ email: { $type: "null" } });

// Chỉ document không có field email.
db.customers.find({ email: { $exists: false } });
~~~

Sự khác biệt này rất quan trọng khi kiểm tra dữ liệu thiếu, tạo validation rule hoặc viết điều kiện nghiệp vụ.

### Đặt tên field và giữ schema nhất quán

Nên dùng tên field ngắn, rõ nghĩa, thống nhất cách viết, chẳng hạn **createdAt**, **customerId**, **totalAmount**. Không nên tạo cả **phone**, **phoneNumber** và **telephone** cho cùng một ý nghĩa nếu không có lý do rõ ràng.

MongoDB có quy tắc riêng đối với field name, đặc biệt là ký tự **.** và dấu **$**. Một số phiên bản hỗ trợ lưu các tên chứa ký tự đó, nhưng thao tác truy vấn/cập nhật, đường dẫn, export/import và tooling có thể phức tạp. Với schema ứng dụng thông thường, nên tránh sử dụng **.** hoặc tên bắt đầu bằng **$** làm tên field thực, để chúng không bị nhầm với dot notation và cú pháp toán tử.

## 6. Namespace: tên đầy đủ của collection

**Namespace** thường được viết theo mẫu:

~~~text
<database-name>.<collection-name>
~~~

Ví dụ:

~~~text
bookstore.books
bookstore.customers
bookstore.orders
analytics.events
~~~

Trong **bookstore.books**:

- **bookstore** là tên database.
- **books** là tên collection.
- **bookstore.books** là namespace đầy đủ của collection đó.

Namespace có vai trò định danh đối tượng trong phạm vi MongoDB deployment. Hai collection cùng tên nhưng thuộc database khác nhau có namespace khác nhau:

~~~text
bookstore.orders     -> Đơn hàng của hệ thống bán sách
archive.orders       -> Đơn hàng được lưu trong database archive
~~~

Hai tên trên không chỉ về cùng một collection. Tương tự, **bookstore.books** và **bookstore.customers** là hai namespace khác nhau dù cùng thuộc một database.

### Xem namespace trong mongosh

~~~javascript
use bookstore

db.getName();                  // "bookstore"
db.books.getName();            // "books"
db.books.getFullName();        // "bookstore.books"
~~~

Có thể làm việc với collection tên không tiện viết theo cú pháp thuộc tính thông thường thông qua **getCollection**:

~~~javascript
db.getCollection("order-items").findOne();
~~~

### Phân biệt namespace, field path và _id

Ba khái niệm thường cùng dùng dấu chấm hoặc mã định danh, nhưng ý nghĩa khác nhau:

| Biểu thức | Ý nghĩa | Cấp độ |
| --- | --- | --- |
| bookstore.books | Namespace của collection **books** | Database + collection |
| author.country | Đường dẫn đến field con trong document | Document + field |
| _id: ObjectId(...) | Định danh của một document | Document |
| bookstore.orders | Namespace của collection **orders** | Database + collection |

Nếu gặp biểu thức **bookstore.books.author.country** trong sơ đồ giải thích, hãy hiểu **bookstore.books** định vị collection và **author.country** mô tả đường dẫn field *bên trong* document của collection đó. Đây chỉ là cách ghép để diễn giải, không phải một namespace collection mới.

Trong chương trình Java, bạn có thể lưu namespace thành hai cấu phần **databaseName** và **collectionName**. Driver thường nhận hai tên này riêng biệt:

~~~java
MongoDatabase database = mongoClient.getDatabase("bookstore");
MongoCollection<Document> books = database.getCollection("books");
~~~

Ở ví dụ này, giá trị namespace logic của collection **books** là **bookstore.books**. Mã ví dụ giả định **mongoClient** đã được tạo và các lớp MongoDB Java Driver cần thiết đã được import.

### Lưu ý khi đặt tên

Chọn tên database và collection có ý nghĩa, ổn định, dễ tìm kiếm và tuân thủ giới hạn đặt tên của phiên bản MongoDB đang dùng. Không tự tạo collection ứng dụng với những tên dành riêng cho hệ thống, chẳng hạn các tên bắt đầu bằng **system.**. Tránh thiết kế phụ thuộc vào các ký tự đặc biệt khó xử lý trên nhiều môi trường.

Đổi tên collection sẽ đổi namespace mà ứng dụng sử dụng; mã truy vấn, quyền, cấu hình và các tiến trình liên quan có thể cần cập nhật theo. Vì vậy namespace là một phần của hợp đồng dữ liệu giữa ứng dụng và database.

## 7. Ví dụ hoàn chỉnh: từ database đến field

Giả sử cần lưu danh mục sách. Các bước trong **mongosh** cho thấy cách từng khái niệm xuất hiện trong thao tác thật.

### Bước 1: Chọn database và tạo collection

~~~javascript
use bookstore

db.createCollection("books");
~~~

Lúc này:

- Database được chọn: **bookstore**.
- Collection được tạo: **books**.
- Namespace của collection: **bookstore.books**.

### Bước 2: Thêm hai document

~~~javascript
db.books.insertMany([
  {
    isbn: "9786040000123",
    title: "Nhập môn MongoDB",
    category: "Database",
    price: NumberDecimal("199000.00"),
    stock: 12,
    author: { name: "Nguyễn An", country: "VN" },
    tags: ["mongodb", "backend"],
    createdAt: new Date()
  },
  {
    isbn: "9786040000456",
    title: "Thiết kế dữ liệu document",
    category: "Database",
    price: NumberDecimal("249000.00"),
    stock: 5,
    author: { name: "Trần Bình", country: "VN" },
    tags: ["mongodb", "modeling"],
    createdAt: new Date(),
    ebookAvailable: true
  }
]);
~~~

Sau thao tác ghi:

- Collection **bookstore.books** có hai document (nếu thao tác thành công trên collection ban đầu rỗng).
- Mỗi document có field **_id** do hệ thống/client tạo khi không được cung cấp.
- Hai document cùng có **isbn**, **title**, **price** nhưng document thứ hai có thêm **ebookAvailable**.
- **author** là embedded document; **tags** là array.

### Bước 3: Đọc và lọc dữ liệu

~~~javascript
// Đọc tất cả sách, chỉ hiện title và price.
db.books.find(
  {},
  { _id: 0, title: 1, price: 1 }
);

// Tìm sách có tác giả từ VN và còn hàng.
db.books.find({
  "author.country": "VN",
  stock: { $gt: 0 }
});

// Tìm chính xác một ISBN.
db.books.findOne({ isbn: "9786040000123" });
~~~

Ở đây, **db** đại diện database hiện tại, **books** là collection, điều kiện trong **find** lọc document, còn từng tên như **stock** và **author.country** chỉ field.

### Bước 4: Cập nhật một field

~~~javascript
db.books.updateOne(
  { isbn: "9786040000123" },
  {
    $inc: { stock: -1 },
    $set: { "author.country": "VN" }
  }
);
~~~

**$inc** thay đổi giá trị số của field **stock**; **$set** gán giá trị field con. Động tác này cập nhật một document được chọn theo ISBN, chứ không đổi namespace hoặc tạo collection khác.

### Bước 5: Kiểm tra tên collection

~~~javascript
db.getName();
db.books.getName();
db.books.getFullName();
~~~

Từ đó có thể đối chiếu:

~~~text
Database             bookstore
Collection           books
Namespace            bookstore.books
Một document         cuốn sách ISBN 9786040000123
Field cấp cao nhất   isbn, title, category, price, stock, author, tags, createdAt
Field lồng nhau      author.name, author.country
~~~

Đây là chuỗi xác định thông tin quan trọng khi đọc tài liệu API hoặc log lỗi: **đang làm việc với database nào, collection nào, document nào và field nào**.

## 8. Liên hệ với cơ sở dữ liệu quan hệ

Nếu đã quen SQL, có thể dùng bảng sau như cầu nối ban đầu:

| Cơ sở dữ liệu quan hệ | MongoDB | Điểm cần nhớ |
| --- | --- | --- |
| Database/schema (tùy hệ quản trị) | Database | Chức năng phân nhóm logic có điểm tương đồng; cách quản trị không giống hoàn toàn |
| Table | Collection | Collection cho phép document có cấu trúc khác nhau |
| Row | Document | Document có thể chứa object và array lồng nhau |
| Column | Field | Field có thể vắng mặt hoặc có cấu trúc phức tạp |
| Primary key | _id | Dùng nhận diện document; kiểu dữ liệu có thể được chọn |
| Fully qualified table name | Namespace | Thường có dạng database.collection |

Không nên suy ra từ bảng so sánh rằng mỗi field đều là một cột cố định, hoặc một document luôn được chuẩn hóa thành nhiều bảng. MongoDB thường thiết kế schema xoay quanh **cách ứng dụng đọc và cập nhật dữ liệu**.

Ví dụ hệ thống đơn hàng:

- Trong SQL, đơn hàng và dòng hàng thường là hai bảng liên kết.
- Trong MongoDB, các dòng hàng có thể là array **items** nằm trong document đơn hàng, nếu mô hình truy cập và kích thước phù hợp.
- Nếu danh sách liên quan tăng không giới hạn hoặc có vòng đời riêng, có thể chọn nhiều collection và lưu tham chiếu.

Các lựa chọn này thuộc thiết kế mô hình dữ liệu; chúng không thay đổi định nghĩa cơ bản của database, collection, document, field và namespace.

## 9. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Chạy **use bookstore** nghĩa là đã tạo database có dữ liệu | Lệnh này chủ yếu chọn ngữ cảnh; dữ liệu/collection cần được tạo thực tế |
| Collection bắt buộc có schema cứng như table | Document có thể khác field; nên dùng quy ước và validation khi cần |
| Mỗi document là một file JSON riêng | Document là đơn vị dữ liệu BSON do MongoDB quản lý |
| Mọi document trong MongoDB có _id duy nhất trên toàn hệ thống | Định danh được xét theo collection; nhiều collection có thể chứa cùng giá trị _id |
| **author.country** là một namespace | Đây là đường dẫn field lồng nhau; namespace ví dụ là **bookstore.books** |
| Field thiếu và field null giống nhau | Chúng khác nhau; truy vấn **{ email: null }** cần đặc biệt lưu ý vì có thể khớp cả hai |
| Có thể cập nhật _id giống field bình thường | _id là định danh bất biến trong thao tác update thông thường |
| Linh hoạt schema nghĩa là không cần kiểm soát dữ liệu | Cấu trúc nhất quán và kiểm tra kiểu dữ liệu vẫn cần thiết để ứng dụng tin cậy |

Một nguyên tắc hữu ích khi đọc truy vấn MongoDB là luôn xác định theo thứ tự: **database hiện tại → collection đích → điều kiện chọn document → field được đọc hoặc cập nhật**. Trật tự này làm rõ phần nào của hệ thống đang được tác động.

## 10. Bài thực hành tự khám phá

Thực hành trong một database thử nghiệm riêng để nhận diện năm khái niệm. Các lệnh sau phù hợp với **mongosh**:

~~~javascript
use school_demo

db.students.insertOne({
  studentCode: "SV001",
  fullName: "Nguyễn Mai",
  active: true,
  contact: {
    city: "Đà Nẵng",
    email: null
  },
  skills: ["Java", "MongoDB"]
});

db.students.find(
  { "contact.city": "Đà Nẵng" },
  { _id: 0, studentCode: 1, fullName: 1, skills: 1 }
);

db.students.getFullName();
~~~

Từ ví dụ này, bạn có thể nhận diện:

1. **Database:** school_demo.
2. **Collection:** students.
3. **Namespace:** school_demo.students.
4. **Document:** bản ghi của sinh viên có **studentCode** bằng **SV001**.
5. **Field:** **fullName**, **active**, **contact**, **skills**; **contact.city** và **contact.email** là đường dẫn field lồng nhau.

Thử thêm một sinh viên không có field **contact.email**, sau đó so sánh kết quả truy vấn với **$exists** và **$type**. Bài thực hành này giúp quan sát trực tiếp sự khác nhau giữa **field không tồn tại** và **field có giá trị null**, đồng thời củng cố cách sử dụng namespace và dot notation.

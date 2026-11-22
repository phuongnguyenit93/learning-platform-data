# Kết nối bằng mongosh và thao tác với MongoDB Compass

## 1. Mục tiêu thực hành

Bài học thuộc phần **Môi trường thực hành** của **Database Engine Document MongoDB**. Sau khi hoàn thành, bạn có thể:

- Phân biệt MongoDB Server, `mongosh` và MongoDB Compass; chọn công cụ phù hợp cho từng thao tác.
- Kết nối đến MongoDB chạy trên máy cá nhân hoặc một cluster MongoDB Atlas bằng connection string.
- Dùng `mongosh` để xác nhận kết nối, chọn database, tạo dữ liệu và thực hiện CRUD, aggregation, index.
- Thao tác với cùng dữ liệu qua giao diện MongoDB Compass; kiểm tra thay đổi qua lại giữa hai công cụ.
- Nhận diện và xử lý các lỗi kết nối, xác thực và quyền truy cập thường gặp.

Các lệnh mẫu được thiết kế để chạy trên **database thực hành riêng**. Khi làm với database của tổ chức, cần chọn đúng môi trường và quyền trước khi thực hiện các thao tác ghi hoặc xóa.

## 2. Ba thành phần trong một môi trường MongoDB

| Thành phần | Vai trò | Cách nhận biết |
|---|---|---|
| **MongoDB Server** (`mongod` hoặc cluster do Atlas quản lý) | Lưu trữ dữ liệu và thực thi truy vấn | Có host, port, tài khoản và các database |
| **mongosh** | Chương trình dòng lệnh để gửi lệnh tới MongoDB Server; hỗ trợ JavaScript tương tác | Gõ `mongosh` trong terminal, xuất hiện dấu nhắc shell |
| **MongoDB Compass** | Ứng dụng giao diện đồ họa để xem document, lọc, sửa, chạy aggregation, quan sát index | Mở ứng dụng và điền connection string |

Cả `mongosh` và Compass đều là **client**. Cài đặt hai công cụ không có nghĩa MongoDB Server đã chạy. Có thể kết nối hai client đến **cùng một server, database và collection** để so sánh kết quả.

MongoDB lưu dữ liệu theo cấu trúc:

~~~text
MongoDB Server / Cluster
└── Database: bookshop
    ├── Collection: books
    │   ├── Document: { _id: "bk001", title: "...", ... }
    │   └── Document: { _id: "bk002", title: "...", ... }
    └── Collection khác (nếu có)
~~~

Database tương tự vùng chứa dữ liệu; collection là nhóm document; document có cấu trúc gần với JSON nhưng được lưu theo định dạng BSON, hỗ trợ thêm các kiểu như `ObjectId`, `Date` và `Decimal128`.

## 3. Chuẩn bị trước khi kết nối

Bạn cần:

1. **Một MongoDB Server có thể truy cập**: cài và chạy MongoDB Community Server tại máy cá nhân, dùng Docker có ánh xạ cổng, hoặc tạo cluster MongoDB Atlas. Server phải thực sự hoạt động trước khi kết nối.
2. **mongosh**: cài MongoDB Shell phù hợp hệ điều hành. Thử `mongosh --version` trong terminal; nếu báo không tìm thấy lệnh, kiểm tra cài đặt và biến `PATH`.
3. **MongoDB Compass**: cài và mở ứng dụng. Giao diện hoặc tên nút có thể khác nhau theo phiên bản, nhưng các chức năng Connection, Documents, Aggregations và Indexes có cùng mục đích.
4. **Thông tin kết nối**: địa chỉ host, cổng, tên database nếu cần, tài khoản/mật khẩu nếu server bật xác thực, và cấu hình mạng/TLS cho kết nối từ xa.

Nếu sử dụng server trên máy cá nhân với cấu hình mặc định, địa chỉ thông dụng là `127.0.0.1:27017`. Trong môi trường Docker, địa chỉ này chỉ hoạt động từ máy host khi cổng container đã được ánh xạ phù hợp. Nếu sử dụng Atlas, lấy connection string từ nút **Connect** của cluster, tạo **database user** có quyền cần thiết và cho phép địa chỉ IP của máy truy cập trong mục cấu hình mạng của dự án.

### 3.1. Connection string là gì?

Hai dạng URI phổ biến:

~~~text
mongodb://HOST:PORT/DATABASE?option=value
mongodb+srv://CLUSTER_HOST/DATABASE?option=value
~~~

- `mongodb://`: thường dùng cho kết nối trực tiếp tới server hoặc danh sách server. Cổng mặc định của MongoDB là `27017`.
- `mongodb+srv://`: dùng bản ghi DNS SRV để khám phá các máy chủ của cluster; thường được Atlas cung cấp sẵn. Dạng này phụ thuộc DNS và thường sử dụng TLS theo cấu hình cluster.
- `DATABASE` sau dấu `/` xác định database mặc định của phiên làm việc; nó **không tự tạo** database.
- Các option như `authSource=admin` quy định database dùng để xác thực khi tài khoản được tạo ở một database khác.

Ví dụ kết nối local không bật xác thực:

~~~text
mongodb://127.0.0.1:27017/bookshop
~~~

Nếu phải đưa username và password trực tiếp vào URI, các ký tự đặc biệt trong thông tin đăng nhập cần được percent-encode đúng quy tắc URI. Trong thực hành, nên dùng hộp thoại xác thực của Compass hoặc tùy chọn nhập mật khẩu tương tác của `mongosh` để tránh để lộ mật khẩu trong lịch sử terminal, script và ảnh chụp.

## 4. Kết nối và kiểm tra bằng mongosh

### 4.1. Kết nối đến MongoDB local

Chạy trong **terminal hệ điều hành**:

~~~bash
mongosh "mongodb://127.0.0.1:27017/bookshop"
~~~

Nếu server yêu cầu tài khoản, có thể truyền username và để `mongosh` hỏi mật khẩu:

~~~bash
mongosh "mongodb://127.0.0.1:27017/bookshop" \
  --username demoUser \
  --authenticationDatabase admin \
  --password
~~~

Ví dụ trên là cú pháp terminal có ký tự nối dòng `\` kiểu Bash. Trên **PowerShell/Windows**, hãy nhập toàn bộ lệnh trên một dòng hoặc dùng cách nối dòng của PowerShell. Đổi `demoUser` và `admin` theo tài khoản thực tế; `admin` chỉ đúng khi user đã được tạo trong authentication database đó.

Khi kết nối thành công, dấu nhắc của `mongosh` xuất hiện. Từ đây, nhập **các lệnh MongoDB Shell**, không nhập thêm tiền tố `mongosh`:

~~~javascript
db.runCommand({ ping: 1 })
db.getName()
show dbs
show collections
~~~

Ý nghĩa:

- `db.runCommand({ ping: 1 })`: kiểm tra server trả lời; thông thường kết quả có `ok: 1`.
- `db.getName()`: xem database hiện tại, dự kiến là `bookshop`.
- `show dbs`: liệt kê các database mà tài khoản được phép thấy; database trống có thể chưa xuất hiện.
- `show collections`: xem các collection trong database hiện tại.

Bạn cũng có thể chuyển database ngay trong shell:

~~~javascript
use bookshop
db.getName()
~~~

`use bookshop` chỉ **chuyển ngữ cảnh**. MongoDB thường chưa hiện database này trong danh sách cho tới khi có dữ liệu hoặc collection được tạo.

Kết thúc phiên bằng:

~~~javascript
exit
~~~

### 4.2. Kết nối MongoDB Atlas

Trong Atlas, mở phần kết nối tới cluster, chọn phương thức **Shell**, sao chép host `mongodb+srv://...` mà Atlas cung cấp. Mẫu lệnh:

~~~bash
mongosh "mongodb+srv://cluster0.example.mongodb.net/bookshop" --username demoUser --password
~~~

`cluster0.example.mongodb.net` chỉ là **địa chỉ minh họa**, cần thay bằng host thực tế của cluster. Nếu lệnh kết nối không thành công, kiểm tra theo thứ tự: cluster đang hoạt động, database user và mật khẩu đúng, mạng hiện tại được cho phép, DNS phân giải được SRV record, và có kết nối Internet.

Ngay sau khi kết nối, xác nhận bằng:

~~~javascript
db.runCommand({ ping: 1 })
db.getName()
~~~

Với Atlas, tài khoản ứng dụng không nhất thiết có quyền xem tất cả database hoặc quản lý người dùng. Chỉ cần quyền đọc/ghi trong database thực hành là đủ cho các bài CRUD bên dưới.

## 5. Tạo bộ dữ liệu mẫu từ mongosh

Để thao tác thực tế và đối chiếu trong Compass, ta sử dụng database `bookshop` và collection `books`. Mỗi document mô tả một cuốn sách với trường dạng chuỗi, số, mảng và object lồng nhau.

Trong phiên `mongosh`, chạy:

~~~javascript
use bookshop

var sampleBooks = [
  {
    _id: "bk001",
    title: "MongoDB căn bản",
    author: "Minh",
    category: "Database",
    price: 280000,
    stock: 12,
    tags: ["mongodb", "nosql"],
    publisher: { name: "Tech Books", city: "Hà Nội" }
  },
  {
    _id: "bk002",
    title: "MongoDB Aggregation",
    author: "Linh",
    category: "Database",
    price: 340000,
    stock: 5,
    tags: ["mongodb", "aggregation"],
    publisher: { name: "Tech Books", city: "TP. Hồ Chí Minh" }
  },
  {
    _id: "bk003",
    title: "Java Backend",
    author: "Nam",
    category: "Backend",
    price: 320000,
    stock: 9,
    tags: ["java", "spring"],
    publisher: { name: "Practical Lab", city: "Đà Nẵng" }
  },
  {
    _id: "bk004",
    title: "Thiết kế REST API",
    author: "Hà",
    category: "Backend",
    price: 260000,
    stock: 0,
    tags: ["api", "rest"],
    publisher: { name: "Practical Lab", city: "Hà Nội" }
  },
  {
    _id: "bk005",
    title: "Index cho ứng dụng",
    author: "Linh",
    category: "Database",
    price: 300000,
    stock: 7,
    tags: ["index", "performance"],
    publisher: { name: "Tech Books", city: "Đà Nẵng" }
  }
];

sampleBooks.forEach(book => {
  db.books.replaceOne({ _id: book._id }, book, { upsert: true });
});

db.books.countDocuments({});
~~~

Đoạn này dùng `replaceOne` với `upsert: true`: nếu chưa có document với `_id` tương ứng thì tạo mới, nếu đã có thì thay lại bằng dữ liệu mẫu. Nhờ vậy chạy lại không bị lỗi trùng `_id`, nhưng cũng **đặt lại** các thay đổi đã thực hiện trên 5 document mẫu. Không chạy lại đoạn tạo dữ liệu khi muốn giữ kết quả sửa của bài tập.

Trong một database mới, `countDocuments({})` trả về `5` sau khi nạp mẫu. Nếu collection từng chứa document khác, tổng số có thể lớn hơn 5.

Ở đây dùng `_id` dạng **string** (`"bk001"`, ...), giúp đối chiếu dễ trên Compass. Với document không tự chỉ định `_id`, MongoDB thường sinh `ObjectId` tự động; khi truy vấn phải giữ đúng kiểu dữ liệu của `_id`.

## 6. Thao tác CRUD trong mongosh

CRUD gồm **Create** (tạo), **Read** (đọc), **Update** (cập nhật) và **Delete** (xóa). Các ví dụ sau sử dụng chính collection `db.books` đã tạo.

### 6.1. Create: thêm một document

~~~javascript
db.books.insertOne({
  _id: "bk006",
  title: "Thực hành MongoDB Compass",
  author: "An",
  category: "Tooling",
  price: 220000,
  stock: 4,
  tags: ["compass", "gui"],
  publisher: { name: "Tech Books", city: "Hà Nội" }
});
~~~

Kết quả trả về có `acknowledged: true` và `insertedId: "bk006"` nếu ghi thành công. Nếu thực hiện lại mà chưa xóa document `bk006`, server sẽ trả lỗi trùng khóa `_id` (thường chứa `E11000 duplicate key`). Để làm lại bài, kiểm tra document đã tồn tại trước khi chèn tiếp.

### 6.2. Read: tìm và chiếu trường

Tìm một document theo khóa:

~~~javascript
db.books.findOne({ _id: "bk001" })
~~~

Tìm tất cả sách về Database, giá từ 300.000 trở lên; chỉ lấy tên và giá, sắp theo giá giảm dần:

~~~javascript
db.books.find(
  { category: "Database", price: { $gte: 300000 } },
  { _id: 0, title: 1, price: 1 }
).sort({ price: -1 }).limit(10)
~~~

Trong truy vấn trên:

- Filter kết hợp hai điều kiện bằng logic AND mặc định.
- `$gte` nghĩa là **greater than or equal** (lớn hơn hoặc bằng).
- Projection `{ _id: 0, title: 1, price: 1 }` ẩn `_id` và chỉ giữ hai trường được chọn.
- `sort({ price: -1 })` sắp giảm dần; `1` là tăng dần.
- `limit(10)` giới hạn số document được trả về.

Truy vấn thuộc tính nằm trong object và tìm giá trị trong mảng:

~~~javascript
db.books.find({ "publisher.city": "Hà Nội" })
db.books.find({ tags: "mongodb" })
~~~

MongoDB dùng **dot notation** để truy cập `publisher.city`. Khi `tags` là mảng, điều kiện `{ tags: "mongodb" }` khớp những document có phần tử bằng `"mongodb"`.

Đếm sách có hàng trong kho:

~~~javascript
db.books.countDocuments({ stock: { $gt: 0 } })
~~~

### 6.3. Update: cập nhật có chủ đích

Tăng số lượng tồn của `bk002` thêm 2 và đánh dấu sách nổi bật:

~~~javascript
db.books.updateOne(
  { _id: "bk002" },
  {
    $inc: { stock: 2 },
    $set: { featured: true }
  }
);

db.books.findOne({ _id: "bk002" });
~~~

`$inc` cộng thêm vào giá trị số hiện tại; `$set` thay hoặc bổ sung trường. Kết quả `updateOne` có `matchedCount` và `modifiedCount` giúp biết có document khớp và có thay đổi thực tế không.

**Chú ý:** thao tác thay toàn document và thao tác cập nhật trường không giống nhau. `replaceOne` thay phần lớn document hiện có, còn `updateOne` với `$set` giữ nguyên các trường không được chỉ định. Không được cố thay `_id` của document hiện hữu.

### 6.4. Delete: xóa đúng document

~~~javascript
db.books.deleteOne({ _id: "bk004" });
db.books.findOne({ _id: "bk004" });
~~~

Khi xóa thành công, `deletedCount` là `1` và truy vấn kiểm tra trả về `null`. Nếu đã xóa từ lần trước, `deletedCount` có thể là `0`.

Trong dữ liệu thực, tránh chạy `deleteMany({})` hoặc `dropDatabase()` khi chưa xác định chắc chắn database và phạm vi dữ liệu: các lệnh này có thể xóa diện rộng.

## 7. Aggregation và index cơ bản trong mongosh

Aggregation xử lý nhiều document qua các **stage**. Ví dụ dưới đây chỉ xét sách còn tồn kho, sau đó tính số đầu sách và giá trung bình theo danh mục:

~~~javascript
db.books.aggregate([
  { $match: { stock: { $gt: 0 } } },
  {
    $group: {
      _id: "$category",
      soDauSach: { $sum: 1 },
      giaTrungBinh: { $avg: "$price" }
    }
  },
  { $sort: { soDauSach: -1, _id: 1 } }
]);
~~~

- `$match` lọc đầu vào trước khi tổng hợp.
- `$group` gom theo `category`, với `_id` là khóa của nhóm.
- `$sum: 1` đếm document; `$avg: "$price"` tính giá trung bình.
- `$sort` sắp thứ tự kết quả.

Index có thể hỗ trợ MongoDB tìm và sắp xếp nhanh hơn ở khối dữ liệu thích hợp. Thử tạo **compound index**:

~~~javascript
db.books.createIndex({ category: 1, price: -1 });
db.books.getIndexes();

db.books.find({
  category: "Database",
  price: { $gte: 300000 }
}).explain("executionStats");
~~~

Phần `explain` hiển thị kế hoạch thực thi và chỉ số như `totalDocsExamined`, `totalKeysExamined`. Có thể gặp `IXSCAN` khi dùng index hoặc `COLLSCAN` khi quét collection. Với **5–6 document mẫu**, query planner hoàn toàn có thể chọn quét collection; đừng kết luận index bị lỗi chỉ từ kết quả trên tập dữ liệu rất nhỏ. Số lần đọc và thời gian chạy còn phụ thuộc dữ liệu, phiên bản server và kế hoạch được chọn.

## 8. Kết nối bằng MongoDB Compass

Mở MongoDB Compass và thực hiện theo các bước:

1. Vào khu vực **New Connection** hoặc danh sách connection, chọn tạo kết nối.
2. Nhập URI cho cùng MongoDB Server đã dùng trong `mongosh`. Với local: `mongodb://127.0.0.1:27017/bookshop`.
3. Nếu server yêu cầu xác thực, nhập thông tin ở phần Authentication hoặc sử dụng chuỗi URI phù hợp. Khi dùng Atlas, lấy URI do Atlas cung cấp và kiểm tra cấu hình mạng/TLS.
4. Chọn **Connect** (hoặc **Save & Connect** nếu muốn lưu cấu hình) để mở danh sách database.
5. Mở database `bookshop`, tiếp đó mở collection `books` để xem các document trong tab **Documents**.

Ở các phiên bản Compass khác nhau, vị trí nút có thể thay đổi. Điều cần kiểm tra là **host/cluster, database và collection** có khớp phiên `mongosh` hay không.

Nếu chưa thấy `bookshop` sau khi kết nối, hãy xác nhận đã nạp dữ liệu từ mục 5, làm mới danh sách database, và kiểm tra xem đang kết nối đúng server không. Nếu người dùng hiện tại chỉ có quyền trong một database nhất định, danh sách có thể không hiển thị mọi database của cluster.

### 8.1. Lọc, chọn trường và sắp xếp document

Trong tab **Documents**, phần Query Bar của Compass thường cung cấp các ô Filter, Project, Sort, Skip, Limit và nút Find/Apply. Hãy nhập các biểu thức dưới đây vào đúng ô:

| Ô trong Compass | Giá trị nhập | Ý nghĩa |
|---|---|---|
| **Filter** | `{"category":"Database","price":{"$gte":300000}}` | Sách Database có giá từ 300.000 |
| **Project** | `{"_id":0,"title":1,"price":1}` | Chỉ hiện tên và giá |
| **Sort** | `{"price":-1}` | Giá giảm dần |
| **Limit** | `10` | Lấy tối đa 10 document |

Nhấn **Find** hoặc **Apply** để chạy truy vấn. Kết quả nên bao gồm `bk002` và `bk005` (nếu chưa sửa/xóa chúng).

Biểu thức ở Compass có thể nhập dưới dạng JSON với **dấu ngoặc kép** quanh tên trường và chuỗi. Trong `mongosh`, đây là các object JavaScript nên khóa có thể không cần dấu ngoặc kép. Đây là khác biệt về **cách nhập**, không phải khác biệt về ngữ nghĩa truy vấn.

Thử thêm một Filter để tìm theo object lồng nhau:

~~~json
{"publisher.city":"Hà Nội"}
~~~

Hoặc tìm sách có thẻ `mongodb`:

~~~json
{"tags":"mongodb"}
~~~

### 8.2. Thêm, sửa và xóa document trong Compass

**Thêm mới:** trong tab Documents, chọn **Add Data → Insert Document** (hoặc nút tương đương), chuyển sang chế độ JSON khi cần và nhập:

~~~json
{
  "_id": "bk007",
  "title": "Ghi chú từ Compass",
  "author": "An",
  "category": "Tooling",
  "price": 190000,
  "stock": 3,
  "tags": ["compass"],
  "publisher": {
    "name": "Practical Lab",
    "city": "Hà Nội"
  }
}
~~~

Chọn **Insert** để ghi. Dữ liệu nhập là JSON hợp lệ: dấu nháy kép, số không có dấu phân cách hàng nghìn và không có dấu phẩy thừa. Trường `_id` phải duy nhất trong collection. Không cần khai báo schema bắt buộc cho mỗi document trong collection mặc định, trừ khi server đã cấu hình quy tắc validation.

**Sửa:** lọc bằng `{"_id":"bk007"}`, chọn hành động Edit (thường là biểu tượng bút chì), đổi `stock` từ `3` thành `8` rồi xác nhận **Update/Save**. Làm mới kết quả để thấy giá trị mới.

**Xóa:** với Filter `{"_id":"bk007"}`, chọn Delete của đúng document và xác nhận trong hộp thoại. Kiểm tra lại Filter phải không còn document đó. Hành động xóa trong Compass tác động trực tiếp đến server giống như lệnh xóa từ `mongosh`.

Nếu Compass cho chọn dạng bảng hay dạng cây (Table/Tree/JSON), việc đổi chế độ chỉ ảnh hưởng cách hiển thị; document lưu trong MongoDB vẫn là một.

### 8.3. Tạo Aggregation Pipeline trong Compass

Mở tab **Aggregations** của collection `books`, tạo một pipeline mới. Tùy phiên bản, bạn có thể nhập toàn bộ pipeline trong **Text View** hoặc thêm từng stage trong trình chỉnh sửa. Dạng JSON của pipeline:

~~~json
[
  {
    "$match": {
      "stock": { "$gt": 0 }
    }
  },
  {
    "$group": {
      "_id": "$category",
      "soDauSach": { "$sum": 1 },
      "giaTrungBinh": { "$avg": "$price" }
    }
  },
  {
    "$sort": {
      "soDauSach": -1,
      "_id": 1
    }
  }
]
~~~

Nếu giao diện yêu cầu chọn stage operator riêng, hãy chọn lần lượt `$match`, `$group`, `$sort` và nhập **phần nội dung tương ứng của từng stage** thay vì dán cả mảng pipeline vào một ô. Chạy pipeline và đối chiếu với `db.books.aggregate([...])` trong `mongosh`.

Compass có thể hiển thị preview của mỗi stage, hữu ích để nhìn thấy dữ liệu đã bị lọc hoặc nhóm như thế nào. Kết quả phụ thuộc trạng thái collection tại thời điểm thực hành.

### 8.4. Quan sát và tạo index trong Compass

Trong tab **Indexes**:

1. Xem danh sách index hiện có, bao gồm index mặc định trên `_id` và index `{category: 1, price: -1}` nếu đã tạo ở mục 7.
2. Nếu chưa có, mở **Create Index**, thêm trường `category` theo thứ tự ascending, trường `price` theo thứ tự descending, rồi xác nhận.
3. Quay lại Documents, chạy truy vấn theo `category` và `price`. Nếu Compass cung cấp **Explain Plan**, mở để xem kế hoạch thực thi.

Không tạo lặp các index có cùng key pattern chỉ để thử giao diện. Index giúp một số truy vấn nhưng cũng tốn dung lượng và chi phí cập nhật khi ghi dữ liệu; cần đánh giá trên workload và kích thước dữ liệu thực tế.

Một số phiên bản Compass còn có tab **Schema**, cho phép lấy mẫu document và quan sát kiểu trường hoặc phân bố giá trị. Chức năng này hỗ trợ khám phá cấu trúc dữ liệu, không thay thế schema validation nếu ứng dụng cần ràng buộc dữ liệu.

## 9. Kiểm chứng hai client đang làm việc trên cùng dữ liệu

Bài thử sau cho thấy `mongosh` và Compass cùng thao tác trên database ở server:

1. Trong **Compass**, thêm document `bk007` như ở mục 8.2, nhưng chưa xóa.
2. Trong **mongosh** đang kết nối cùng server/database, chạy:

   ~~~javascript
   db.books.findOne({ _id: "bk007" })
   ~~~

3. Trong `mongosh`, tăng tồn kho của document đó:

   ~~~javascript
   db.books.updateOne(
     { _id: "bk007" },
     { $inc: { stock: 2 } }
   );
   ~~~

4. Quay lại **Compass**, làm mới tab Documents và lọc `{"_id":"bk007"}`. Nếu giá trị ban đầu là `3`, bây giờ `stock` phải là `5`.
5. Trong Compass, đổi `stock` thành `8`; sau đó chạy lại `db.books.findOne({ _id: "bk007" })` trong mongosh. Kết quả phải phản ánh giá trị `8`.
6. Xóa `bk007` trong Compass; xác nhận `findOne` trong mongosh trả về `null`.

Nếu hai bên không thấy dữ liệu giống nhau, hãy đối chiếu URI, hostname, database hiện tại (`db.getName()`), tên collection và Filter. Dữ liệu không được đồng bộ *giữa hai ứng dụng* bằng một bước đặc biệt; cả hai đơn giản cùng đọc/ghi lên server.

## 10. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `mongosh: command not found` hoặc `mongosh is not recognized` | Chưa cài mongosh hoặc đường dẫn thực thi chưa nằm trong `PATH` | Kiểm tra phiên bản, cài đúng công cụ và mở lại terminal |
| `ECONNREFUSED 127.0.0.1:27017` | MongoDB Server local chưa chạy hoặc đang nghe cổng khác | Kiểm tra tiến trình/service `mongod`, cổng và ánh xạ Docker |
| `Server selection timed out` | Không liên lạc được host/cluster, sai địa chỉ, firewall hoặc mạng chặn | Kiểm tra URI, DNS, VPN, firewall, trạng thái server và Atlas IP access list |
| `Authentication failed` | Sai username/mật khẩu hoặc `authSource` | Xác minh database user và authentication database, nhập lại mật khẩu |
| `not authorized on ...` | Đăng nhập được nhưng thiếu role cho thao tác | Kiểm tra quyền đọc/ghi của tài khoản đối với database/collection |
| Không phân giải được `mongodb+srv` | DNS không truy vấn được bản ghi SRV hoặc hostname sai | Sao chép URI chuẩn từ Atlas, kiểm tra DNS và kết nối mạng |
| Lỗi TLS/chứng chỉ | Cấu hình TLS hoặc độ tin cậy chứng chỉ chưa đúng | Kiểm tra URI, chứng chỉ và thiết lập TLS của server/cluster; không tắt xác thực TLS để “chữa nhanh” |
| Compass trống dù mongosh có dữ liệu | Khác host/database/collection, bộ lọc còn hiệu lực, UI chưa refresh | So sánh URI, chạy `db.getName()`, xóa Filter, refresh |
| `E11000 duplicate key error` | Đã tồn tại document có cùng `_id` hoặc khóa unique khác | Kiểm tra document/index trước khi thêm; dùng update/upsert đúng mục đích |

Để khoanh vùng, nên kiểm tra **từ kết nối tới quyền và dữ liệu**: server có trả `ping` không → đang ở đúng database không → nhìn thấy collection không → có quyền query không → bộ lọc có đúng kiểu dữ liệu không.

Đặc biệt, `"bk001"` (string) và `ObjectId("...")` là những kiểu khác nhau. Khi dùng Compass, Filter phải phù hợp với kiểu `_id` được lưu; không đổi một giá trị string thành ObjectId chỉ vì trường đó có tên `_id`.

## 11. Thực hành tự kiểm tra

Thực hiện lần lượt trên database `bookshop`:

1. Kết nối bằng `mongosh`, chạy `ping` và ghi lại database đang chọn.
2. Nạp lại năm sách mẫu ở mục 5, rồi dùng Compass mở collection `books`.
3. Lọc sách có `category` là `Database` và `price` từ `300000`; sắp giá giảm dần. Với dữ liệu mẫu, kết quả là **MongoDB Aggregation (340.000)** và **Index cho ứng dụng (300.000)**.
4. Tìm sách được xuất bản ở **Hà Nội** qua `publisher.city`, và tìm sách có thẻ `mongodb` qua trường `tags`.
5. Dùng `mongosh` tăng tồn kho `bk002` từ `5` lên `7`; refresh Compass để kiểm tra.
6. Chạy aggregation nhóm theo `category` cho các sách `stock > 0` và xem sự khác nhau giữa hai nhóm.
7. Xem compound index `category`/`price` trong Compass; thử Explain và giải thích vì sao trên dữ liệu nhỏ chưa chắc thấy `IXSCAN`.
8. Thêm một document có `_id` mới bằng Compass, đọc lại bằng `mongosh` rồi xóa document đó sau khi xác nhận.

Lệnh đối chiếu nhanh:

~~~javascript
db.runCommand({ ping: 1 });
db.getName();
db.books.find({ category: "Database", price: { $gte: 300000 } })
        .sort({ price: -1 });
db.books.find({ "publisher.city": "Hà Nội" });
db.books.find({ tags: "mongodb" });
db.books.findOne({ _id: "bk002" });
db.books.getIndexes();
~~~

Các bước nạp dữ liệu mẫu và cập nhật tồn kho nên được thực hiện đúng thứ tự. Nếu chạy lại đoạn `replaceOne(..., {upsert:true})`, dữ liệu mẫu được đặt lại như ban đầu.

## 12. Ghi nhớ khi sử dụng trong dự án thực tế

- **Dùng mongosh** khi cần kiểm tra kết nối nhanh, thực thi lệnh có thể lặp lại, viết script bảo trì có kiểm soát hoặc quan sát phản hồi MongoDB trực tiếp.
- **Dùng Compass** khi muốn duyệt document trực quan, thử Filter/Projection/Sort, dựng pipeline từng stage hoặc khảo sát index và kiểu dữ liệu.
- **Luôn kiểm tra đúng môi trường** (local, staging, production), đúng database và collection trước mọi thao tác ghi/xóa. Tài khoản thực hành nên được cấp quyền tối thiểu cần dùng.
- **Không đưa mật khẩu** hoặc URI chứa thông tin đăng nhập vào repository, lịch sử lệnh chia sẻ, tài liệu công khai hoặc ảnh chụp. Cân nhắc lưu connection profile trên máy cá nhân theo chính sách bảo mật của tổ chức.
- **Chạy truy vấn thử bằng Filter trước khi update/delete** trên dữ liệu quan trọng; chú ý số lượng document khớp và phản hồi `matchedCount`, `modifiedCount`, `deletedCount`.
- **Phân biệt giao diện với dữ liệu thật**: một thay đổi đã lưu trong Compass tác động tới MongoDB Server và sẽ hiện ở mongosh khi client truy vấn lại cùng server.

Với cùng một connection string và quyền truy cập thích hợp, bạn có thể linh hoạt chuyển giữa thao tác dòng lệnh và giao diện đồ họa mà không phải xuất/nhập dữ liệu giữa mongosh và Compass.

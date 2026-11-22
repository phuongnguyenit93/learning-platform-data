# Trường `_id`, `ObjectId` và định danh của document

Trong MongoDB, mỗi document trong một collection cần có trường `_id` để xác định chính xác document đó. Khi làm việc với Spring Data MongoDB, trường này thường được ánh xạ vào thuộc tính `id` của Java entity. Hiểu rõ `_id`, kiểu BSON `ObjectId` và quy tắc chuyển đổi kiểu giúp tránh lỗi truy vấn không tìm thấy dữ liệu, khóa trùng và cập nhật nhầm document.

Sau bài này, bạn có thể:

- Giải thích vai trò của `_id`, chỉ mục duy nhất mặc định và tính bất biến của định danh.
- Đọc, tạo, truy vấn `ObjectId` và hiểu giới hạn của phần thời gian nằm trong nó.
- Chọn và ánh xạ định danh bằng `@Id`, `@MongoId` trong Spring Data MongoDB.
- Phân biệt `ObjectId` với chuỗi 24 ký tự hex, dùng kiểu phù hợp khi truy vấn và thiết kế API.
- Quyết định khi nào dùng định danh kỹ thuật, khóa nghiệp vụ và cách kiểm tra lỗi liên quan.

## 1. `_id` là gì?

Ví dụ một document trong collection `books`:

```javascript
{
  _id: ObjectId("665f1f2a4b6c7d8e9f001234"),
  title: "MongoDB căn bản",
  isbn: "978-604-00-0000-1",
  stock: 12
}
```

`_id` là khóa định danh của document **trong phạm vi một collection**. MongoDB tự tạo một chỉ mục duy nhất cho `_id` (thường mang tên `_id_`), giúp truy vấn và ngăn hai document trong cùng collection có cùng giá trị `_id` theo quy tắc so sánh BSON. Hai collection khác nhau có thể chứa document với cùng `_id`.

Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa thực tế |
| --- | --- |
| Có mặt khi lưu | Một document đã được lưu luôn có `_id`. Nếu không cung cấp, driver hoặc MongoDB sẽ sinh giá trị, thông thường là `ObjectId`. |
| Duy nhất trong collection | Chèn document trùng `_id` bị từ chối vì vi phạm chỉ mục duy nhất. |
| Không thể đổi sau khi chèn | Cập nhật hay thay thế document không được thay giá trị `_id`. Để đổi định danh, cần quy trình tạo document mới và xử lý tham chiếu tương ứng. |
| Có kiểu BSON | `_id` không bắt buộc là `ObjectId`; có thể dùng chuỗi, số, UUID/Binary hoặc một kiểu BSON hợp lệ khác theo giới hạn của MongoDB. Không dùng mảng làm giá trị `_id`. |
| Không phải khóa ngoại tự động | MongoDB không tự kiểm tra quan hệ khi document khác lưu một `_id` tham chiếu đến nó. Ứng dụng phải đảm bảo tính toàn vẹn cần thiết. |

Đừng đồng nhất `_id` với khóa nghiệp vụ như ISBN, mã nhân viên hoặc email. `_id` xác định bản ghi; khóa nghiệp vụ có thể có quy tắc khác, chẳng hạn thay đổi theo thời gian, cần duy nhất theo tenant hoặc phải chuẩn hóa chữ hoa/chữ thường.

## 2. `ObjectId`: cấu trúc và ý nghĩa

`ObjectId` là kiểu BSON dài **12 byte**, thường được biểu diễn thành **24 ký tự hexadecimal** khi hiển thị. Một `ObjectId` theo cách sinh thông dụng có cấu trúc:

| Thành phần | Độ dài | Vai trò |
| --- | ---: | --- |
| Timestamp | 4 byte | Số giây tính từ Unix epoch, phản ánh thời điểm tạo định danh với độ phân giải 1 giây. |
| Giá trị ngẫu nhiên | 5 byte | Thành phần thường được tạo một lần cho tiến trình, giúp giảm khả năng trùng giữa các môi trường tạo ID. |
| Bộ đếm | 3 byte | Giá trị tăng theo lần sinh định danh, hỗ trợ phân biệt nhiều ID được tạo gần nhau. |

Ví dụ chuỗi `665f1f2a4b6c7d8e9f001234` chỉ là **dạng biểu diễn** của giá trị BSON `ObjectId`. Nó không tự động trở thành `ObjectId` chỉ vì dài 24 ký tự. Một document lưu `_id` dưới dạng String và một document lưu `_id` dưới dạng ObjectId có **hai định danh khác kiểu** ngay cả khi chuỗi ký tự nhìn giống nhau.

Có thể tạo và đọc timestamp trong `mongosh`:

```javascript
const id = new ObjectId();
print(id.toHexString());   // Ví dụ: chuỗi 24 ký tự hex
print(id.getTimestamp());  // Ngày/giờ UTC từ 4 byte timestamp
```

### Không nhầm timestamp trong `ObjectId` với `createdAt`

`ObjectId` thường tăng gần theo thời điểm tạo nên tiện cho một số kiểu sắp xếp gần đúng. Tuy nhiên, nó **không bảo đảm thứ tự tạo chính xác tuyệt đối**: độ phân giải chỉ tới giây, nhiều máy có đồng hồ khác nhau và ID có thể được sinh trước khi document thực sự được ghi vào database. Vì vậy:

- Dùng trường `createdAt` riêng khi cần thời gian tạo record phục vụ nghiệp vụ, kiểm toán hoặc lọc chính xác.
- Dùng `updatedAt` riêng khi cần theo dõi thời gian thay đổi.
- Không suy đoán `ObjectId` là mã bí mật hoặc token phân quyền: ai có ID vẫn phải vượt qua kiểm tra quyền truy cập.

## 3. Thực hành với `mongosh`

### 3.1. Để MongoDB tự sinh `_id`

```javascript
use library

const result = db.books.insertOne({
  title: "Spring Data MongoDB",
  stock: 8
});

const bookId = result.insertedId;
printjson(bookId);
printjson(db.books.findOne({ _id: bookId }));
```

Khi không khai báo `_id`, thao tác insert thông thường sinh `ObjectId`. Giá trị được trả về qua `insertedId` có thể dùng trực tiếp cho truy vấn, tránh nhập lại bằng tay.

### 3.2. Định danh chuỗi và `ObjectId` là hai kiểu khác nhau

```javascript
const hex = "665f1f2a4b6c7d8e9f001234";

db.books.insertOne({ _id: new ObjectId(hex), title: "ID kiểu ObjectId" });
db.books.insertOne({ _id: hex, title: "ID kiểu String" });

db.books.findOne({ _id: new ObjectId(hex) }); // Document thứ nhất
db.books.findOne({ _id: hex });               // Document thứ hai
```

Hai thao tác insert hợp lệ vì `_id` khác **kiểu BSON**, dù chữ hiển thị giống nhau. Truy vấn bằng chuỗi sẽ không khớp với `ObjectId` tương ứng, và ngược lại. Đây là nguyên nhân thường gặp khi truy vấn trực tiếp trên MongoDB nhưng ứng dụng Spring Data lại trả dữ liệu khác dự kiến.

### 3.3. Kiểm tra trùng định danh

```javascript
db.books.insertOne({ _id: "book-001", title: "Bản A" });
db.books.insertOne({ _id: "book-001", title: "Bản B" });
// Lệnh thứ hai thất bại với lỗi duplicate key (E11000).
```

Thao tác này chỉ mang tính minh họa trên dữ liệu thử nghiệm. Khi cần tạo bản ghi mới, xử lý lỗi trùng ID rõ ràng; tránh tự động thay bằng `save`/upsert nếu yêu cầu là "chỉ tạo khi chưa tồn tại".

## 4. Ánh xạ `_id` trong Spring Data MongoDB

Spring Data MongoDB ánh xạ Java entity sang BSON document, hỗ trợ `MongoRepository` và `MongoTemplate`. Các annotation trong ví dụ:

| Annotation | Công dụng |
| --- | --- |
| `@Document(collection = "books")` | Chỉ định collection chứa entity. |
| `@Id` | Đánh dấu thuộc tính làm định danh ánh xạ tới `_id`; có cơ chế chuyển đổi String ↔ ObjectId khi khả thi. |
| `@MongoId` | Đánh dấu thuộc tính `_id` với quyền kiểm soát kiểu lưu rõ ràng hơn; mặc định giữ kiểu khai báo thay vì ép String thành ObjectId theo `@Id`. |
| `@MongoId(FieldType.OBJECT_ID)` | Yêu cầu lưu định danh theo kiểu BSON ObjectId, dùng khi chủ động muốn chuyển đổi kiểu. |

### 4.1. Cách 1: lưu ID bằng `ObjectId` trong Java

Đây là lựa chọn dễ hiểu khi ứng dụng dùng `ObjectId` làm định danh kỹ thuật:

```java
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "books")
public class Book {
    @Id
    private ObjectId id;
    private String title;

    protected Book() {} // Dành cho việc ánh xạ dữ liệu

    public Book(String title) {
        this.title = title;
    }

    public ObjectId getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }
}
```

Khai báo repository với **đúng kiểu ID của entity**:

```java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface BookRepository extends MongoRepository<Book, ObjectId> {
}
```

Sử dụng:

```java
Book saved = bookRepository.insert(new Book("Spring Data MongoDB"));
ObjectId id = saved.getId(); // ID được gán khi insert

Book found = bookRepository.findById(id)
    .orElseThrow(() -> new IllegalStateException("Không tìm thấy sách"));
```

Khi nhận một ID qua REST path dưới dạng chuỗi, nên kiểm tra/parse tại biên API:

```java
String pathId = "665f1f2a4b6c7d8e9f001234";
if (!ObjectId.isValid(pathId)) {
    throw new IllegalArgumentException("Định dạng ObjectId không hợp lệ");
}
ObjectId id = new ObjectId(pathId);
Book book = bookRepository.findById(id)
    .orElseThrow(() -> new IllegalStateException("Không tìm thấy sách"));
```

Trong ứng dụng thật, API nên trả `400 Bad Request` khi ID sai định dạng và `404 Not Found` khi ID hợp lệ nhưng không có document. Kiểm tra phân quyền đối với document phải thực hiện độc lập với việc ID có hợp lệ hay không.

### 4.2. Cách 2: Java dùng `String` nhưng MongoDB lưu `ObjectId` khi có thể

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "books")
public class BookWithStringId {
    @Id
    private String id;
    private String title;
}
```

Với `@Id String id`, Spring Data MongoDB thường chuyển chuỗi có định dạng `ObjectId` hợp lệ thành BSON `ObjectId` khi lưu/truy vấn. Chuỗi không thể chuyển đổi thì được lưu như BSON String. Khi ID được tạo tự động cho entity này, Java có thể nhận dạng chuỗi của `ObjectId` được sinh.

Hệ quả: hai ID đầu vào cùng có kiểu Java `String` có thể được lưu bằng **hai kiểu BSON khác nhau**. Đừng dựa vào việc "trông giống 24 ký tự hex" để kết luận trường trong database có kiểu String; hãy kiểm tra giá trị thực hoặc chọn cách ánh xạ tường minh.

### 4.3. Cách 3: giữ ID dạng String với `@MongoId`

Nếu định danh nghiệp vụ là `"book-001"`, `"vn-hcm-001"`, hoặc muốn lưu ngay cả chuỗi 24 ký tự hex **dưới dạng BSON String**, có thể khai báo:

```java
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "catalog_items")
public class CatalogItem {
    @MongoId
    private String id;
    private String title;

    protected CatalogItem() {}

    public CatalogItem(String id, String title) {
        this.id = id;
        this.title = title;
    }
}
```

Ở trường hợp này, ứng dụng chủ động cấp ID chuỗi khi tạo entity. Nếu cần ObjectId nhưng vẫn muốn giữ thuộc tính Java là String, `@MongoId(FieldType.OBJECT_ID)` là tùy chọn tường minh; khi đó cần bảo đảm giá trị String có thể chuyển đổi hợp lệ. Tránh trộn nhiều chiến lược định danh trong cùng một collection nếu không có yêu cầu và kiểm thử chuyển đổi rõ ràng.

## 5. Tìm kiếm, cập nhật và tính bất biến

Khi đã chọn kiểu ID, sử dụng nhất quán trong repository và query:

```java
// Nếu Book.id là ObjectId:
ObjectId id = new ObjectId("665f1f2a4b6c7d8e9f001234");
bookRepository.findById(id);
bookRepository.existsById(id);
```

Với `MongoTemplate`, truy vấn trên entity để bộ ánh xạ Spring Data có đủ ngữ cảnh xử lý field và giá trị:

```java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

ObjectId id = new ObjectId("665f1f2a4b6c7d8e9f001234");
Query query = Query.query(Criteria.where("id").is(id));
Book found = mongoTemplate.findOne(query, Book.class);
```

Trong ví dụ, thuộc tính `id` của `Book` được ánh xạ tới trường MongoDB `_id`. Khi dùng driver MongoDB trực tiếp hoặc viết truy vấn JSON thô, tên trường thực là `_id` và giá trị phải có kiểu BSON đúng.

Không thể cập nhật `_id` của document đã tồn tại:

```javascript
// Ví dụ cố đổi _id sẽ bị MongoDB từ chối.
db.books.updateOne(
  { _id: "book-001" },
  { $set: { _id: "book-002" } }
);
```

Nếu mã nghiệp vụ cần thay đổi, mô hình thường phù hợp hơn là giữ `_id` ổn định và đặt mã đó ở field riêng (có unique index nếu cần). Điều này tránh phải cập nhật các document đang tham chiếu tới ID cũ.

Phân biệt hai thao tác ở tầng Spring Data:

- `insert(entity)` dùng cho **tạo mới**. Nếu `_id` đã tồn tại, MongoDB từ chối với lỗi duplicate key.
- `save(entity)` có thể cập nhật/thay thế document đã tồn tại khi ID đã được gán (phụ thuộc trạng thái entity và cơ chế versioning). Không dùng `save` như biện pháp tránh lỗi trùng khi yêu cầu nghiệp vụ phải ngăn ghi đè.

Đối với cập nhật đồng thời, có thể dùng `@Version` (optimistic locking) hoặc thao tác cập nhật có điều kiện phù hợp; riêng chỉ mục `_id` chỉ bảo đảm tính duy nhất của định danh, không giải quyết xung đột nội dung.

## 6. Chọn chiến lược định danh

| Chiến lược | Phù hợp khi | Điểm cần cân nhắc |
| --- | --- | --- |
| `ObjectId` | Cần ID kỹ thuật sinh tự động, không mang nghĩa nghiệp vụ, dùng rộng rãi với MongoDB. | API thường biểu diễn bằng hex String; phải parse đúng kiểu. Timestamp không thay thế `createdAt`. |
| String ID có cấu trúc | Cần mã rõ nghĩa, đã có sẵn từ hệ thống khác hoặc dùng khóa ngoại lai từ dịch vụ khác. | Bảo đảm sinh duy nhất, tránh đổi giá trị và tránh chuỗi quá dài làm tăng dung lượng chỉ mục. |
| UUID (BSON Binary) | Hệ thống đã chuẩn hóa UUID hoặc cần sinh định danh độc lập giữa nhiều hệ thống. | Thống nhất representation/codec; UUID dạng chuỗi và UUID dạng BSON Binary là hai kiểu khác nhau. |
| Khóa nghiệp vụ đặt ở field riêng | ISBN, SKU, email hoặc mã thay đổi theo quy trình. | Tạo unique index theo quy tắc nghiệp vụ, có thể cần chỉ mục ghép với `tenantId`. |

Ví dụ hệ thống nhiều tenant có thể giữ `_id: ObjectId(...)`, `tenantId` và `sku` là các field riêng, rồi tạo chỉ mục duy nhất theo cặp:

```javascript
db.products.createIndex(
  { tenantId: 1, sku: 1 },
  { unique: true, name: "uniq_tenant_sku" }
);
```

Như vậy, cùng SKU có thể xuất hiện ở hai tenant khác nhau nhưng không được lặp trong một tenant. Phạm vi duy nhất của `_id` vẫn là collection; chỉ mục ghép thể hiện **quy tắc nghiệp vụ** khác.

**Lưu ý khi sharding:** trong một collection được sharding, nếu `_id` không phải shard key thì việc bảo đảm tính duy nhất của `_id` trên toàn cụm cần được thiết kế cẩn thận; ràng buộc `_id` có thể chỉ được thực thi trên từng shard. Không mặc định rằng cơ chế chỉ mục `_id` giải quyết mọi bài toán duy nhất xuyên shard.

## 7. Kiểm tra chỉ mục và chẩn đoán lỗi

Kiểm tra chỉ mục có sẵn và kế hoạch thực thi bằng `mongosh`:

```javascript
db.books.getIndexes();

db.books.find({
  _id: new ObjectId("665f1f2a4b6c7d8e9f001234")
}).explain("executionStats");
```

Kết quả `explain` phụ thuộc phiên bản MongoDB và bộ thực thi truy vấn. Quan sát `winningPlan`, `totalKeysExamined`, `totalDocsExamined` và số kết quả trả về để đánh giá thay vì chỉ tìm một tên stage cố định.

Khi truy vấn ID không ra kết quả hoặc insert lỗi, kiểm tra theo thứ tự:

1. **Đúng collection/database chưa?** Một `_id` hợp lệ ở collection A không đồng nghĩa tồn tại ở collection B.
2. **Đúng kiểu BSON chưa?** Dùng `ObjectId("...")` cho dữ liệu ObjectId và chuỗi thuần cho dữ liệu String; kiểm tra `@Id`/`@MongoId` trong entity.
3. **ID có tồn tại chưa?** `ObjectId.isValid(...)` chỉ kiểm tra định dạng, không kiểm tra sự tồn tại.
4. **Có vi phạm unique index không?** Lỗi `E11000 duplicate key` có thể do `_id` hoặc một chỉ mục unique khác; đọc tên index trong thông báo.
5. **Có đang sửa `_id` không?** MongoDB từ chối cập nhật làm thay đổi định danh.
6. **Có dùng `save` cho thao tác tạo mới không?** Xem lại khả năng ghi đè/upsert và cân nhắc `insert`.

Khi viết kiểm thử tích hợp, nên bao phủ ít nhất: tạo document không có ID, truy vấn lại bằng ID được trả về, thử insert trùng ID, và kiểm tra truy vấn khác kiểu String/ObjectId. Với Spring Data, có thể dùng Testcontainers MongoDB hoặc MongoDB thử nghiệm để xác nhận **BSON type thực tế**, thay vì chỉ kiểm tra chuỗi ID bên Java.

## 8. Bài tập tự luyện

1. Tạo hai document có `_id` lần lượt là `ObjectId("665f1f2a4b6c7d8e9f001234")` và `"665f1f2a4b6c7d8e9f001234"`. Viết hai truy vấn riêng để lấy đúng từng document; giải thích vì sao MongoDB cho phép cả hai tồn tại.
2. Viết entity `Customer` với `@Id ObjectId id`, repository tương ứng và API nhận path ID dưới dạng chuỗi. Xử lý riêng trường hợp ID sai định dạng và document không tồn tại.
3. Viết entity `InventoryItem` dùng `@MongoId String id` với mã do nghiệp vụ cấp; thử ID dài 24 ký tự hex và xác minh nó vẫn được lưu dưới dạng BSON String.
4. Thiết kế dữ liệu sản phẩm nhiều tenant: đề xuất `_id`, `tenantId`, `sku`, các chỉ mục unique cần có và cách xử lý khi SKU của sản phẩm được phép đổi.

### Ghi nhớ

`_id` là định danh ổn định và duy nhất của document trong collection. `ObjectId` là một **kiểu BSON**, còn chuỗi hex chỉ là cách biểu diễn nó. Khi sử dụng Spring Data MongoDB, khai báo và giữ nhất quán kiểu ID từ entity, repository, query đến API; dùng `@Id` hoặc `@MongoId` theo chủ đích chuyển đổi. Đặt khóa nghiệp vụ ở field riêng khi quy tắc nghiệp vụ khác với quy tắc định danh document.

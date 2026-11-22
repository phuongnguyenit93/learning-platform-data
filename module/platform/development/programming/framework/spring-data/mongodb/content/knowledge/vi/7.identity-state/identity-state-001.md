# Quy tắc ánh xạ thuộc tính id và @Id vào _id

## 1. Mục tiêu và bối cảnh

Trong MongoDB, mỗi document ở một collection có trường định danh `_id`. Trong Java, lập trình viên thường dùng thuộc tính `id`. Spring Data MongoDB làm nhiệm vụ nối hai biểu diễn này: hiểu thuộc tính nào đại diện cho khóa của document, chuyển giá trị sang kiểu BSON thích hợp và chuyển ngược lại khi đọc.

Đây là kiến thức nền tảng của chương **Định danh và trạng thái** thuộc module **SPRING_DATA_MONGODB**. Khi sử dụng Spring Data MongoDB để kết nối và ánh xạ document, viết truy vấn bằng `MongoTemplate` hoặc repository, kiểm thử và chẩn đoán dữ liệu, một lỗi nhỏ về kiểu `_id` có thể khiến truy vấn không tìm thấy bản ghi dù chuỗi ID nhìn giống hệt nhau.

Sau bài này, bạn có thể:

1. Giải thích quan hệ giữa property Java `id`, annotation `@Id` và trường BSON `_id`.
2. Phân biệt ID kiểu `String` với ID kiểu `ObjectId`, đặc biệt khi một chuỗi có dạng 24 ký tự thập lục phân.
3. Chọn `@Id`, `@MongoId` hoặc quy ước đặt tên phù hợp và dự đoán BSON thực tế.
4. Hiểu cách Spring Data sinh/đọc định danh, viết query và repository theo ID.
5. Phát hiện lỗi do lệch kiểu ID và thiết kế kiểm thử khi thay đổi quy tắc định danh.

**Thông điệp cốt lõi:** `id` là tên thuộc tính trong Java; `_id` là tên trường định danh trong MongoDB; **kiểu BSON lưu trong `_id` mới quyết định cách MongoDB so khớp dữ liệu**.

## 2. Trường _id có gì đặc biệt?

Một document đơn giản trong collection `books`:

```javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  title: "MongoDB căn bản",
  price: 180000
}
```

MongoDB dùng `_id` làm khóa định danh của document và mặc định tạo unique index `_id_` cho collection thông thường. Nếu ứng dụng không cung cấp `_id` khi insert, driver/server có thể tạo giá trị định danh, thường là BSON `ObjectId`.

Những điểm cần phân biệt:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `_id` | Tên trường định danh mà MongoDB dùng |
| `ObjectId("...")` | Một kiểu dữ liệu BSON dùng làm định danh; không phải tên trường |
| `id` | Tên property Java phổ biến, có thể được Spring Data ánh xạ vào `_id` |
| `@Id` | Annotation của Spring Data đánh dấu property định danh |
| `@MongoId` | Annotation MongoDB-specific giúp kiểm soát kiểu lưu ID |
| Index `_id_` | Index mặc định hỗ trợ tính duy nhất và tra cứu khóa |

**Không đồng nhất `_id` với ObjectId.** MongoDB có thể lưu `_id` là String, số nguyên hoặc một số kiểu BSON hợp lệ khác, tùy thiết kế. Tuy nhiên, lựa chọn kiểu phải thống nhất với code, dữ liệu đã có và những collection tham chiếu đến ID.

MongoDB không cho phép thay đổi giá trị `_id` của một document hiện hữu bằng thao tác update thông thường. Vì thế, định danh nên **ổn định trong suốt vòng đời document**; các thuộc tính nghiệp vụ dễ đổi như email hoặc số điện thoại không nên mặc nhiên đóng vai trò `_id`.

## 3. Những quy tắc ánh xạ ID mặc định của Spring Data MongoDB

`MappingMongoConverter` dựa vào metadata entity để chuyển property Java thành document. Các quy tắc quan trọng:

1. Property được đánh dấu `@Id` ánh xạ vào trường MongoDB `_id`, **dù property Java có tên khác `id`**.
2. Nếu không khai báo property `@Id` hoặc `@MongoId`, property Java có tên `id` thường được nhận diện theo quy ước là ID và ánh xạ vào `_id`.
3. `@MongoId` cũng đánh dấu property định danh, nhưng cung cấp lựa chọn cụ thể hơn về **kiểu BSON đích**.
4. Với `@Id` và property kiểu `String`, Spring Data MongoDB có thể chuyển chuỗi biểu diễn ObjectId hợp lệ sang BSON ObjectId; nếu không chuyển được, giá trị chuỗi có thể được lưu như BSON String.
5. Việc xác định trường ID **không có nghĩa** mọi document bắt buộc chứa trường Java tên `id`. Có thể khai báo property `documentKey` rồi đánh dấu `@Id`; nó vẫn lưu dưới `_id`.

Quy tắc về chuyển kiểu áp dụng theo phiên bản, converter và cấu hình của dự án. Đối với dữ liệu quan trọng, hãy xác nhận bằng việc đọc BSON thực tế và kiểm thử round trip ở phiên bản Spring Data đang sử dụng.

### 3.1. Cùng BSON nhưng hai tên property Java

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("books")
public record BookA(@Id String id, String title) {}

@Document("books")
public record BookB(@Id String documentKey, String title) {}
```

Hai ví dụ này minh họa cách **ánh xạ ID**, không phải lời khuyên dùng hai class khác nhau để cùng thao tác với một collection trong ứng dụng thực tế.

| Java model | Java ID property | BSON field |
| --- | --- | --- |
| `BookA` | `id` | `_id` |
| `BookB` | `documentKey` | `_id` |

Với `BookB`, dùng `documentKey` trong mã Java và phương thức query có context của entity. Tên `documentKey` không làm MongoDB xuất hiện thêm field định danh riêng.

### 3.2. Quy ước theo tên khi không dùng annotation

```java
import org.springframework.data.mongodb.core.mapping.Document;

@Document("books")
public record BookByConvention(String id, String title) {}
```

Ở đây, property `id` được ánh xạ vào `_id` theo quy ước của mapper. Tuy nhiên, dùng `@Id` tường minh giúp người đọc code hiểu ý định rõ hơn, đặc biệt khi model có nhiều field như `bookId`, `externalId`, `referenceId`.

**Không đánh dấu mọi trường chứa chữ "Id".** Ví dụ `authorId` có thể chỉ là khóa tham chiếu đến tác giả, được lưu thành `authorId` bình thường; nó không tự trở thành `_id` của sách.

### 3.3. Những điều không nên suy luận

- `@Field("id")` không được dùng như cách thay thế chung cho `@Id`; annotation này chủ yếu chỉ định tên trường lưu trữ.
- Tên field `_id` trong mongosh **không đồng nghĩa** mọi object Java đều phải khai báo property tên `_id`.
- Chỉ sửa `@Id`/`@MongoId` trong source không tự đổi kiểu các khóa hiện có trong database.
- Một property tên `id` không tự làm cho mã định danh có ý nghĩa nghiệp vụ, có thể hiển thị công khai hoặc đoán được.

## 4. Trường hợp dễ gây nhầm: @Id String và kiểu ObjectId

### 4.1. Hai giá trị nhìn giống nhau nhưng không bằng nhau

```javascript
// BSON ObjectId:
{ _id: ObjectId("507f1f77bcf86cd799439011") }

// BSON String:
{ _id: "507f1f77bcf86cd799439011" }
```

MongoDB so khớp theo cả **giá trị và kiểu BSON**. Vì vậy, truy vấn:

```javascript
db.books.findOne({
  _id: "507f1f77bcf86cd799439011"
});
```

không khớp bản ghi có `_id` là `ObjectId("507f1f77bcf86cd799439011")`, dù nội dung chuỗi tương tự.

### 4.2. Quy tắc chuyển đổi khi dùng @Id String

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("books")
public record Book(@Id String id, String title) {}
```

Ví dụ sau minh họa hành vi mặc định phổ biến của `MappingMongoConverter`:

| Giá trị Java `id` | Dạng lưu dự kiến ở MongoDB |
| --- | --- |
| `"507f1f77bcf86cd799439011"` | `ObjectId("507f1f77bcf86cd799439011")` |
| `"BOOK-001"` | `"BOOK-001"` (BSON String) |
| `null` khi insert | MongoDB/driver có thể sinh ID, thường là ObjectId |

Điểm cần nhớ: chỉ khai báo `@Id String` **không bảo đảm** BSON `_id` luôn là String. Khi ID do ứng dụng tự cấp có thể tình cờ gồm đúng 24 ký tự hex, điều này gây lỗi khó nhìn thấy ở ứng dụng khác dùng driver trực tiếp hoặc dịch vụ không qua Spring Data.

Giải pháp là chọn chính sách định danh rõ ràng và nhất quán ngay từ đầu, đặc biệt nếu ID đến từ một hệ thống ngoài, định dạng URL hay dữ liệu chuyển đổi lịch sử.

## 5. Dùng @MongoId khi muốn kiểm soát kiểu ID

`@MongoId` nằm trong package `org.springframework.data.mongodb.core.mapping`. Nó cũng đánh dấu property ánh xạ vào `_id`, nhưng có tùy chọn `FieldType` để diễn đạt kiểu dữ liệu BSON mong muốn.

### 5.1. Giữ ID chuỗi là BSON String

```java
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document("books")
public record BookWithStringId(
    @MongoId(FieldType.STRING) String id,
    String title
) {}
```

Với ID chuỗi do nghiệp vụ cấp:

```java
new BookWithStringId(
    "507f1f77bcf86cd799439011",
    "Sách có ID dạng chuỗi"
);
```

Document dự kiến dùng:

```javascript
{
  _id: "507f1f77bcf86cd799439011",
  title: "Sách có ID dạng chuỗi"
}
```

Đây là lựa chọn phù hợp nếu toàn hệ thống dùng ID dạng String, kể cả khi chúng trông giống ObjectId. Với `@MongoId` không khai báo `FieldType`, cơ chế xử lý mặc định giữ kiểu dữ liệu tự nhiên hơn thay vì áp quy tắc ép ID String giống `@Id`; cách dùng tường minh `FieldType.STRING` giúp dễ đọc và kiểm tra hơn.

### 5.2. Muốn BSON ObjectId một cách có chủ đích

```java
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("books")
public record BookWithObjectId(
    @Id ObjectId id,
    String title
) {}
```

Java `ObjectId` tương ứng trực tiếp với BSON ObjectId. Khi thao tác với mã hóa/giải mã JSON ngoài ứng dụng, thường cần chuyển thành chuỗi hiển thị 24 ký tự hex. Nếu API nhận ID từ client, nên kiểm tra định dạng trước khi tạo `ObjectId`.

Spring Data còn cho phép thể hiện ý định dùng ObjectId qua `@MongoId(FieldType.OBJECT_ID)` trên property tương thích, nhưng việc này vẫn cần xem xét khả năng chuyển kiểu dữ liệu đầu vào. Đối với mô hình vốn muốn dùng ObjectId, sử dụng trực tiếp kiểu `ObjectId` thường ít gây nhầm lẫn hơn.

### 5.3. Bảng chọn cấu hình ID

| Cách khai báo | Ý định | Lưu ý |
| --- | --- | --- |
| `String id` không annotation | Dùng quy ước nhận diện `id` | Kém rõ ràng; cần kiểm thử chuyển đổi |
| `@Id String id` | ID kiểu String trong Java, có chuyển ObjectId khi phù hợp | Dữ liệu có thể có cả BSON String và ObjectId |
| `@Id ObjectId id` | Dùng ObjectId làm định danh | Dịch vụ/API phải chuyển kiểu hợp lý |
| `@MongoId(FieldType.STRING) String id` | Giữ định danh BSON String | Phù hợp ID nghiệp vụ hoặc ID bên ngoài |
| `@MongoId(FieldType.OBJECT_ID) String id` | Đề nghị ánh xạ sang BSON ObjectId | Cần kiểm tra giá trị không hợp lệ và round trip |

**Đừng chuyển đổi kiểu ID trên collection đã có dữ liệu mà không có kế hoạch migration.** Chuỗi và ObjectId cùng nội dung hiển thị vẫn là hai khóa khác nhau trong MongoDB.

## 6. Sinh ID khi insert và ảnh hưởng đến vòng đời entity

### 6.1. Một ví dụ có ID chưa được cấp

Giả sử entity là class có property ID có thể ghi:

```java
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("books")
public class MutableBook {
    @Id
    private ObjectId id;
    private String title;

    public MutableBook(String title) {
        this.title = title;
    }

    public ObjectId getId() {
        return id;
    }

    public void setId(ObjectId id) {
        this.id = id;
    }

    public String getTitle() {
        return title;
    }
}
```

Khi gọi:

```java
MutableBook book = new MutableBook("Thiết kế document");
mongoTemplate.insert(book);
ObjectId generatedId = book.getId();
```

Nếu ID chưa có, trong luồng insert thông thường MongoDB driver có thể sinh BSON ObjectId và Spring Data có thể điền lại ID vào entity theo cơ chế lưu trữ của phiên bản đang dùng. Với **entity mutable** như ví dụ, có thể kiểm tra `getId()` sau lệnh ghi. Với object bất biến, kết quả/đối tượng được trả về và khả năng cập nhật trường ID cần được xem theo contract API thực tế.

Không nên mặc định ID tự sinh sẽ có kiểu phù hợp với mọi property ID. Nếu doanh nghiệp dùng ID kiểu số hoặc ID từ hệ thống ngoài, ứng dụng có thể phải cấp giá trị theo quy tắc riêng.

### 6.2. Insert và save có ý nghĩa khác nhau

```java
mongoTemplate.insert(book); // Ý định thêm document mới.
mongoTemplate.save(book);   // Lưu hoặc thay thế/upsert theo ID, tùy trạng thái.
```

`insert` nhằm tạo document mới, nên khi trùng `_id` sẽ gặp lỗi khóa trùng. `save` có semantics khác, có thể thay thế/upsert theo ID; dùng sai có nguy cơ ghi đè dữ liệu ngoài ý định nếu đối tượng chứa dữ liệu cũ hoặc thiếu field.

Đối với repository:

```java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface BookRepository
    extends MongoRepository<BookWithObjectId, ObjectId> {
}
```

`repository.save(entity)` quyết định entity «mới» hay «đã tồn tại» dựa trên cơ chế nhận diện trạng thái của Spring Data (thường xét ID hoặc `@Version`, có thể tùy biến qua `Persistable`). Vì thế, ID được ứng dụng cấp trước khi lưu có thể làm thay đổi nhánh thực thi. Khi API có ý nghĩa «tạo mới hoặc báo trùng», nên thiết kế và kiểm thử rõ semantics đó, thay vì suy ra từ tên `save`.

### 6.3. ID không phải @Version

`_id` xác định **document nào**, còn `@Version` hỗ trợ **kiểm soát đồng thời** trên những entity thích hợp. Cả hai đều ảnh hưởng đến việc Spring Data xác định trạng thái entity, nhưng chúng giải quyết hai vấn đề khác nhau:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("inventory")
public class InventoryItem {
    @Id
    private ObjectId id;

    @Version
    private Long version;

    private int quantity;
}
```

Ví dụ chỉ nhằm chỉ ra hai annotation tách biệt. `@Version` cần được sử dụng với luồng lưu/update tương thích để có optimistic locking; nó không làm `_id` trở thành field thay đổi mỗi lần ghi. Cập nhật trực tiếp qua driver hoặc lệnh update không tuân quy tắc version có thể bỏ qua cơ chế này.

## 7. Truy vấn ID bằng mongosh, MongoTemplate và repository

### 7.1. So khớp đúng kiểu BSON

Giả sử MongoDB đang có document sau:

```javascript
db.books.insertOne({
  _id: ObjectId("507f1f77bcf86cd799439011"),
  title: "Spring Data MongoDB"
});
```

Truy vấn đúng bằng mongosh:

```javascript
db.books.findOne({
  _id: ObjectId("507f1f77bcf86cd799439011")
});
```

Truy vấn có giá trị hiển thị giống nhưng kiểu khác sẽ không tìm thấy:

```javascript
db.books.findOne({
  _id: "507f1f77bcf86cd799439011"
});
```

### 7.2. Tìm bằng MongoTemplate

Với entity `BookWithObjectId`:

```java
import org.bson.types.ObjectId;

ObjectId bookId = new ObjectId("507f1f77bcf86cd799439011");
BookWithObjectId book =
    mongoTemplate.findById(bookId, BookWithObjectId.class);
```

`findById` dựa trên metadata entity để tìm theo ID. Không cần viết tên field `_id` thủ công ở API này.

Nếu dùng `Query`:

```java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("id").is(bookId)
);
BookWithObjectId result =
    mongoTemplate.findOne(query, BookWithObjectId.class);
```

Khi `Query` gắn với `BookWithObjectId.class`, Spring Data sử dụng metadata để ánh xạ property Java `id` thành BSON `_id`. Cách này thuận tiện khi cần kết hợp ID với điều kiện khác.

### 7.3. Tìm bằng MongoRepository

```java
// Giả sử repository là bean BookRepository đã được inject.
ObjectId id = new ObjectId("507f1f77bcf86cd799439011");
var maybeBook = repository.findById(id);
```

Kiểu generic ID phải phù hợp model: `MongoRepository<BookWithObjectId, ObjectId>` khác với `MongoRepository<BookWithStringId, String>`. Repository API sẽ sử dụng metadata và converter, nhưng không thể biến một kho dữ liệu đã lưu lẫn kiểu thành đồng nhất chỉ nhờ khai báo generic.

### 7.4. Khi dùng ID do nghiệp vụ cấp

```java
import org.springframework.data.mongodb.core.mapping.MongoId;
import org.springframework.data.mongodb.core.mapping.FieldType;

@Document("purchase_orders")
public record PurchaseOrder(
    @MongoId(FieldType.STRING) String id,
    String customerId
) {}
```

Lệnh tìm:

```javascript
db.purchase_orders.findOne({
  _id: "PO-2026-0001"
});
```

Trong Java, có thể khai báo `MongoRepository<PurchaseOrder, String>` rồi gọi `findById("PO-2026-0001")`. Chọn ID nghiệp vụ cho `_id` khi giá trị **ổn định, được cấp duy nhất, ít phụ thuộc việc sửa format** và đáp ứng phạm vi duy nhất của collection. Nếu `orderNo` chỉ duy nhất trong từng tenant, một ID kỹ thuật độc lập cùng unique compound index trên `(tenantId, orderNo)` có thể dễ vận hành hơn.

## 8. Những sai lầm về _id trong thiết kế hệ thống

### 8.1. Đánh đồng ID của MongoDB với ID công khai

`ObjectId` là một kiểu khóa lưu trữ; không phải cơ chế phân quyền. API nhận `id` từ client vẫn phải kiểm tra quyền truy cập tới document. Một endpoint lấy đơn hàng chỉ theo `_id` mà không kiểm tra tenant/owner có thể gây lộ dữ liệu.

```java
Query query = Query.query(
    Criteria.where("id").is(orderId)
        .and("tenantId").is(authenticatedTenantId)
);
var order = mongoTemplate.findOne(query, OrderDocument.class);
```

Đoạn code giả định `OrderDocument` có các property `id` và `tenantId` cùng những kiểm tra quyền phù hợp từ tầng dịch vụ. Index `_id_` vẫn giúp chọn bản ghi theo khóa; điều kiện tenant hạn chế phạm vi nghiệp vụ.

### 8.2. Dùng _id làm khóa phân trang mà quên thứ tự nghiệp vụ

`ObjectId` có thành phần thời gian, nhưng không phải cam kết tuyệt đối về thứ tự sự kiện nghiệp vụ giữa các máy hay trong cùng một thời điểm. Nếu yêu cầu «đơn mới nhất», dùng trường thời gian nghiệp vụ (ví dụ `createdAt`) và thêm `_id` làm khóa phá hòa:

```javascript
db.orders.find({ tenantId: "tenant-a" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20);
```

Khi dùng sort này trong hệ thống lớn, cần xem lại compound index phù hợp. Không nên chỉ dựa vào thứ tự của `_id` để suy ra ngày đặt, ngày thanh toán hoặc ngày xử lý.

### 8.3. Đổi ID khi đổi thông tin nghiệp vụ

Giả sử mã đơn có thể thay đổi do nhập sai hoặc hệ thống liên kết bên ngoài điều chỉnh. Nếu lấy `orderNo` làm `_id`, yêu cầu sửa mã đơn trở nên khó vì `_id` không cập nhật như field thường.

Thiết kế thay thế:

```javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenantId: "tenant-a",
  orderNo: "ORD-0007",
  status: "NEW"
}
```

Với thiết kế này, `_id` ổn định. `orderNo` là thuộc tính nghiệp vụ có thể được cập nhật theo quy tắc và ràng buộc unique nếu cần.

### 8.4. Không thống nhất kiểu giữa khóa và reference

```javascript
// orders
{ _id: ObjectId("507f1f77bcf86cd799439011") }

// order_events: lưu sai kiểu của khóa tham chiếu
{ orderId: "507f1f77bcf86cd799439011", event: "CREATED" }
```

Nếu phép ghép/truy vấn mong đợi `orderId` kiểu ObjectId thì chuỗi sẽ không khớp. Hãy giữ **quy ước kiểu BSON nhất quán** giữa `orders._id` và `order_events.orderId`, cũng như trong DTO, message queue và các tác vụ migration.

## 9. Thay đổi quy tắc ID trên collection đã có dữ liệu

Khi dự án chuyển từ `@Id String` sang `@MongoId(FieldType.STRING)`, không thể suy ra các document cũ sẽ được đổi kiểu:

```javascript
// Document A đã tồn tại với _id ObjectId.
{ _id: ObjectId("507f1f77bcf86cd799439011"), title: "A" }

// Document B đã tồn tại với _id String.
{ _id: "507f1f77bcf86cd799439011", title: "B" }
```

Hai document này có hai khóa khác nhau dù biểu diễn chữ giống nhau. Việc sửa annotation không hợp nhất chúng; đổi kiểu `_id` thực tế đòi hỏi chiến lược di chuyển bản ghi và các tham chiếu liên quan.

Quy trình phân tích trước migration:

1. Xác định **kiểu BSON thật** của `_id` trong từng collection và từng giai đoạn dữ liệu.
2. Thống kê nguồn tạo ID: Spring Data, driver, import, batch, hệ thống tích hợp hoặc script.
3. Tìm các collection tham chiếu đến khóa, kiểm tra type và quy tắc đọc/ghi.
4. Xác định trạng thái cuối cùng muốn đạt: toàn bộ String hay toàn bộ ObjectId.
5. Lập kế hoạch chuyển document và tham chiếu vì không thể `$set` lại `_id` tại chỗ; cân nhắc downtime, đồng bộ hai chiều, rollback và ràng buộc unique.
6. Kiểm thử đọc/ghi đồng thời với các phiên bản dịch vụ đang triển khai.

**Lưu ý:** Không chạy lệnh cập nhật tự phát `{$set: {_id: ...}}` để «sửa» collection. MongoDB không cho thay khóa `_id` của document hiện hữu theo cách đó. Với hệ thống production, chuyển kiểu ID thường là thay đổi dữ liệu có ảnh hưởng rộng, cần kế hoạch triển khai cụ thể.

## 10. Kiểm tra kiểu thực tế và chẩn đoán lỗi

### 10.1. Xem BSON type ở MongoDB

```javascript
db.books.aggregate([
  {
    $project: {
      _id: 1,
      idBsonType: { $type: "$_id" },
      title: 1
    }
  },
  { $limit: 20 }
]);
```

Kết quả có thể ghi `idBsonType: "objectId"` hoặc `idBsonType: "string"`. Để kiểm tra phân bố trên toàn collection, dùng pipeline `$group` theo kiểu BSON (có thể tốn tài nguyên khi collection lớn, nên xem xét môi trường và tải trước khi chạy):

```javascript
db.books.aggregate([
  { $group: {
      _id: { $type: "$_id" },
      count: { $sum: 1 }
  }},
  { $sort: { count: -1 } }
]);
```

### 10.2. Xác minh round trip của converter

Giả sử đã inject được `MongoConverter` trong một ứng dụng Spring:

```java
import org.bson.Document;
import org.springframework.data.mongodb.core.convert.MongoConverter;

public void inspectIdMapping(MongoConverter converter) {
    BookWithStringId entity = new BookWithStringId(
        "507f1f77bcf86cd799439011",
        "Sách thử nghiệm"
    );

    Document bson = new Document();
    converter.write(entity, bson);

    Object storedId = bson.get("_id");
    System.out.println(storedId.getClass().getName());

    BookWithStringId loaded =
        converter.read(BookWithStringId.class, bson);
    System.out.println(loaded.id());
}
```

Với `@MongoId(FieldType.STRING)`, ID trong `Document` dự kiến là `String`. Thử đổi entity thử nghiệm sang `Book` dùng `@Id String` và xác minh hành vi chuyển đổi với chuỗi 24 ký tự hex, chuỗi tùy ý và ID rỗng. Thao tác này kiểm tra conversion trong bộ nhớ, chưa kiểm tra lưu trữ trên server.

### 10.3. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `findById` trả rỗng dù nhìn thấy _id trong mongosh | Kiểu String/ObjectId không khớp | Xem `$type` và kiểu ID của entity |
| Lưu entity đầu tiên tạo khóa không như dự kiến | Quy tắc `@Id String` chuyển giá trị hợp lệ sang ObjectId | Xem BSON thực tế; cân nhắc `@MongoId(FieldType.STRING)` |
| Hai dịch vụ cùng ID chuỗi nhưng không tìm được document của nhau | Một dịch vụ dùng String, dịch vụ khác ép ObjectId | Thống nhất contract về BSON type |
| Tạo entity mới nhưng `save` lại thay dữ liệu | ID đã được cấp; cơ chế xác định new/existing và save semantics | Xem nhánh insert/save, `@Version` và `Persistable` |
| Truy vấn reference hoặc `$lookup` không khớp | Kiểu field tham chiếu khác kiểu `_id` | Kiểm tra đồng thời hai bên |
| Đổi kiểu ID gây lỗi dữ liệu cũ | Annotation thay đổi nhưng BSON cũ không đổi | Thiết kế migration và kiểm tra tương thích |
| Muốn thay `_id` bằng `$set` nhưng MongoDB báo lỗi | `_id` không được update tại chỗ | Chọn khóa ổn định; nếu cần thì di chuyển dữ liệu |

### 10.4. Dữ liệu quan sát khác với metadata

Metadata mapping cho biết Spring Data **dự kiến** lưu ID thế nào. Một collection có thể đã chứa document do ứng dụng cũ, ETL hoặc driver khác ghi. Vì vậy, khi gỡ lỗi phải đối chiếu:

```text
Java entity & annotation
        |
        v
MappingMongoConverter / kiểu ID dự kiến
        |
        v
BSON document thực sự lưu ở MongoDB
        |
        v
Query/ID type mà client gửi vào
        |
        v
Kết quả truy vấn và kiểm thử tích hợp
```

Nếu converter ghi đúng mà truy vấn sai, kiểm tra cách tạo điều kiện theo `_id`, quá trình chuyển String/ObjectId và việc gọi API driver trực tiếp. Nếu BSON từ dữ liệu cũ khác kỳ vọng, ưu tiên phân tích migration thay vì tiếp tục sửa tên field trong repository.

## 11. Thực hành có lời giải

Sử dụng các entity minh họa ở những phần trước; mỗi bài dưới đây là độc lập.

### Bài 1. Dự đoán trường và kiểu được lưu

**Đề bài.** Với model:

```java
@Document("samples")
record Sample(
    @Id String id,
    String externalId
) {}
```

Hãy xác định tên trường MongoDB khi tạo `new Sample("507f1f77bcf86cd799439011", "EXT-01")` và mô tả kiểu dự kiến của ID.

**Lời giải.** Property `id` ánh xạ thành `_id`; property `externalId` vẫn mang tên `externalId`. Theo quy tắc mặc định của `@Id String`, giá trị 24 ký tự hex hợp lệ có thể được lưu thành BSON ObjectId:

```javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  externalId: "EXT-01"
}
```

### Bài 2. Buộc lưu ID dạng String

**Đề bài.** Ứng dụng cần giữ toàn bộ mã do đối tác cung cấp ở dạng BSON String, kể cả chuỗi có dạng ObjectId. Chọn annotation phù hợp.

**Lời giải:**

```java
@Document("partner_orders")
record PartnerOrder(
    @MongoId(FieldType.STRING) String id,
    String partner
) {}
```

Như vậy `_id` lưu dạng BSON String theo chủ đích. Vẫn cần kiểm tra trùng ID, chuẩn hóa đầu vào và phân quyền.

### Bài 3. Tại sao mongosh không tìm thấy?

**Đề bài.** Document có `_id: ObjectId("507f1f77bcf86cd799439011")`. Lệnh sau trả về `null`:

```javascript
db.books.findOne({ _id: "507f1f77bcf86cd799439011" });
```

**Lời giải.** BSON String không bằng BSON ObjectId. Truy vấn:

```javascript
db.books.findOne({
  _id: ObjectId("507f1f77bcf86cd799439011")
});
```

Trong Spring Data, xác định đúng kiểu ID entity và dùng `repository.findById(...)` hoặc `mongoTemplate.findById(...)` với kiểu phù hợp.

### Bài 4. Khi mã đơn cần được đổi

**Đề bài.** Một hệ thống cho phép điều chỉnh `orderNo` sau khi tạo. Nên lấy `orderNo` hay khóa kỹ thuật làm `_id`?

**Lời giải.** Với yêu cầu này, nên dùng một `_id` kỹ thuật ổn định và lưu `orderNo` thành property nghiệp vụ. Nếu `orderNo` phải duy nhất trong tenant, thêm unique compound index trên `{ tenantId: 1, orderNo: 1 }`, dựa trên thiết kế tenant/shard key của hệ thống. Đổi `orderNo` sẽ không đòi đổi khóa `_id`; những tham chiếu tới đơn vẫn ổn định.

### Bài 5. Kiểm tra một collection chứa ID lẫn kiểu

**Đề bài.** Dữ liệu được import từ hai hệ thống: một hệ lưu `_id` kiểu String, hệ kia dùng ObjectId. Làm cách nào đánh giá rủi ro trước khi đổi annotation?

**Lời giải.** Đầu tiên, thống kê kiểu `_id` bằng `$type` và truy nguyên các nguồn ghi. Tiếp theo, tìm mọi tham chiếu tới ID, thống nhất kiểu đích rồi tạo kế hoạch migration và test tương thích. Không nên chỉ đổi `@Id` thành `@MongoId` rồi kết luận dữ liệu đã được chuẩn hóa.

## 12. Checklist khi review định danh

| Câu hỏi | Bằng chứng cần xác nhận |
| --- | --- |
| Property Java nào là ID? | `@Id`, `@MongoId` hoặc quy ước tên `id` |
| Trường vật lý nào lưu ID? | BSON `_id` trong document thật |
| Kiểu ID lưu trữ là gì? | `$type`: `objectId`, `string` hay kiểu khác |
| String ID có bị chuyển thành ObjectId không? | Test với chuỗi hex hợp lệ và chuỗi nghiệp vụ |
| ID được sinh ở đâu? | Ứng dụng, Spring Data/driver hay hệ thống ngoài |
| Khi trùng ID thì sao? | Insert duplicate key, xử lý lỗi và idempotency |
| Truy vấn theo ID có xét quyền không? | Điều kiện tenant/owner và test phân quyền |
| Reference lưu cùng kiểu với _id không? | BSON của hai collection và contract tích hợp |
| Khi đổi model có cần migration không? | Dữ liệu cũ, index, API và các phụ thuộc |

### Ghi nhớ

1. `_id` là trường định danh của MongoDB; `id` là tên property Java thường được ánh xạ vào trường đó.
2. `@Id` đánh dấu property bất kể tên Java, nhưng `@Id String` **không bảo đảm** kiểu BSON luôn là String.
3. `@MongoId(FieldType.STRING)` giúp diễn đạt rõ ý định lưu ID chuỗi; `ObjectId` là lựa chọn tự nhiên khi hệ thống chọn BSON ObjectId.
4. Chuỗi 24 ký tự hex và BSON ObjectId có cùng biểu diễn chữ **không phải cùng kiểu**; cần thống nhất ID trong lưu trữ, query và reference.
5. `_id` là khóa ổn định, không được cập nhật tại chỗ; `@Version` là cơ chế kiểm soát đồng thời riêng.
6. Xác minh mapping bằng BSON thật, converter round trip và integration test trước khi đổi chiến lược định danh.

# Tùy chỉnh lookup và bộ chuyển đổi giá trị tham chiếu

Trong **Spring Data MongoDB**, các document có thể liên kết bằng một giá trị định danh thay vì nhúng toàn bộ dữ liệu. Cơ chế `@DocumentReference` hỗ trợ lưu tham chiếu dưới dạng **ID**, **một giá trị nghiệp vụ** hoặc **một BSON document nhỏ chứa nhiều trường**. Điểm quan trọng là phải thống nhất hai chiều: **giá trị được ghi vào document nguồn** và **truy vấn dùng để tìm document đích**.

Ở chế độ mặc định, `@DocumentReference` lưu ID của đối tượng được tham chiếu rồi dùng ID đó để tìm đối tượng. Khi cần tham chiếu theo mã nhà xuất bản, mã từ hệ thống ngoài, cặp khóa tenant–mã hoặc truy vấn ngược từ collection khác, ta có thể thay đổi `lookup` và dùng **writing converter trả về `DocumentPointer`**. Khả năng này thuộc tầng mapping của Spring Data MongoDB; MongoDB Server vẫn là nơi chạy query, index và aggregation.

Bài học thuộc chương **Tham chiếu tài liệu** của module `SPRING_DATA_MONGODB`. Sau bài, bạn có thể:

- Giải thích `@DocumentReference`, `lookup`, `#target`, `#self` và cách Spring Data đọc tham chiếu.
- Tùy chỉnh tham chiếu theo **một khóa không phải `_id`** và đăng ký `Converter<ĐốiTượng, DocumentPointer<...>>` để ghi đúng giá trị.
- Dùng **pointer dạng document** cho khóa ghép; tạo **tham chiếu ngược** với `@ReadOnlyProperty`.
- Phân biệt `@DocumentReference`, `@DBRef`, tham chiếu ID thủ công và `$lookup`.
- Chọn index, kiểm soát kiểu BSON, tính nhất quán, lazy loading, giới hạn reactive và kiểm thử dữ liệu thực.

## 1. Từ tham chiếu mặc định đến lookup tùy chỉnh

Giả sử ứng dụng quản lý sách và nhà xuất bản. Một nhà xuất bản được nhiều sách sử dụng và có vòng đời độc lập, nên thường được lưu ở collection riêng:

```javascript
// publishers
{ _id: "PUB-001", code: "NXB-A", name: "Nhà xuất bản A" }

// books
{ _id: "BOOK-001", title: "Học MongoDB", publisher: "PUB-001" }
```

Với ánh xạ mặc định:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.DocumentReference;

@Document(collection = "publishers")
public record Publisher(
        @Id String id,
        String code,
        String name
) {}

@Document(collection = "books")
public class Book {
    @Id
    private String id;

    private String title;

    @DocumentReference
    private Publisher publisher;

    protected Book() {}

    public Book(String id, String title, Publisher publisher) {
        this.id = id;
        this.title = title;
        this.publisher = publisher;
    }

    public Publisher getPublisher() {
        return publisher;
    }
}
```

Trong cấu hình mặc định, giá trị tham chiếu của `publisher` được lấy từ `Publisher.id`. Khi đọc, Spring Data tạo truy vấn tương đương:

```javascript
db.publishers.findOne({ _id: "PUB-001" });
```

Lookup mặc định về mặt ý nghĩa là:

```java
@DocumentReference(lookup = "{ '_id' : ?#{#target} }")
```

`#target` ở đây là **giá trị tham chiếu lưu trong document `books`**, ví dụ `"PUB-001"`. Spring Data dùng metadata của loại đích để phân giải thành `Publisher` khi nạp `Book`. Việc tham chiếu được nạp **eager theo mặc định**; `lazy = true` chỉ hoãn truy vấn tới khi truy cập.

**Nhớ rằng:** `@DocumentReference` không tạo foreign key của MongoDB và **không tự lưu cascade**. Phải lưu `Publisher` riêng trước khi tham chiếu đến nó. Nếu đối tượng đích bị xóa, ứng dụng cần quyết định có cho tham chiếu mồ côi, ẩn liên kết, từ chối xóa hay giữ bản chụp lịch sử.

### 1.1. So sánh các cách biểu diễn liên kết

| Cách | Giá trị trong document nguồn | Ai chịu trách nhiệm tải đối tượng liên quan? |
| --- | --- | --- |
| Trường `String publisherId` | ID thông thường, ví dụ `"PUB-001"` | Service tự gọi repository, `MongoTemplate` hoặc aggregation |
| `@DocumentReference` mặc định | ID của thực thể đích | Spring Data phân giải tham chiếu khi đọc entity |
| `@DocumentReference(lookup = ...)` | ID, scalar khác hoặc document pointer tùy mapping | Spring Data dựng filter từ `lookup` |
| `@DBRef` | BSON DBRef theo cấu trúc có `$ref` và `$id` | Spring Data DBRef resolver |
| `$lookup` aggregation | Không định nghĩa kiểu lưu tham chiếu; dùng field có sẵn | MongoDB Server thực hiện phép kết hợp trong pipeline |

Khi cần kiểm soát số truy vấn hoặc dữ liệu liên quan có thể rất lớn, **ID thủ công và tải theo batch** có thể phù hợp hơn một trường đối tượng được phân giải tự động.

## 2. Hiểu cú pháp `lookup`, `#target` và `#self`

`lookup` nhận một **chuỗi biểu diễn BSON/JSON query**. Spring Data xử lý các vị trí SpEL trước khi gửi query tới MongoDB Server. Một số mẫu:

| Biểu thức | Ý nghĩa |
| --- | --- |
| `"{ '_id' : ?#{#target} }"` | So `_id` của document đích với giá trị pointer đã lưu |
| `"{ 'code' : ?#{#target} }"` | Tìm theo mã nghiệp vụ `code` bằng pointer scalar |
| `"{ 'tenantId' : ?#{tenant}, 'externalCode' : ?#{code} }"` | Lấy `tenant` và `code` từ pointer dạng document |
| `"{ 'publisherId' : ?#{#self._id} }"` | Tìm document đích theo `_id` của document nguồn khi xây tham chiếu ngược |

- **`#target`:** pointer đang được đọc, tức giá trị thực lưu của field tham chiếu. Nếu là document, có thể truy cập trường con của pointer.
- **`#self`:** document nguồn đang được ánh xạ; thường dùng cho **tham chiếu ngược** không lưu danh sách ID ở phía nguồn.
- **`?#{...}`:** vị trí đánh giá biểu thức SpEL. Hãy giữ kiểu giá trị nhất quán với BSON của field đích, đặc biệt giữa `String` và `ObjectId`.

Không nên ghép trực tiếp dữ liệu người dùng vào chuỗi annotation để tạo query động. `lookup` là **cấu hình mapping tĩnh**; với bộ lọc thay đổi theo request, hãy dùng `MongoTemplate`/repository hoặc aggregation và tham số hóa giá trị ở tầng nghiệp vụ.

## 3. Ví dụ chính: tham chiếu Publisher theo `code`

Giả sử `Publisher.id` chỉ phục vụ nội bộ, còn mã `code` như `"NXB-A"` là khóa ổn định mà các book lưu lại. Mong muốn:

```javascript
// Collection: publishers
{ _id: "PUB-001", code: "NXB-A", name: "Nhà xuất bản A" }

// Collection: books
{ _id: "BOOK-001", title: "Học MongoDB", publisher_code: "NXB-A" }
```

Lúc đọc `Book.publisher`, ứng dụng phải tìm:

```javascript
db.publishers.findOne({ code: "NXB-A" });
```

Và lúc ghi `Book`, ứng dụng phải lưu **`Publisher.code`**, không phải `Publisher.id`.

### 3.1. Khai báo mapping đọc

Giữ `Publisher` như ở mục 1. Trong `Book`, thay khai báo field `publisher` bằng:

```java
import org.springframework.data.mongodb.core.mapping.DocumentReference;
import org.springframework.data.mongodb.core.mapping.Field;

@Field("publisher_code")
@DocumentReference(lookup = "{ 'code' : ?#{#target} }")
private Publisher publisher;
```

`@Field("publisher_code")` điều khiển **tên field BSON trong `books`**. `lookup` điều khiển **cách tìm trong `publishers`**. Chúng là hai khái niệm riêng biệt: nếu bỏ `@Field` thì thuộc tính thường được lưu dưới tên `publisher`, nhưng truy vấn theo `code` vẫn do `lookup` quyết định.

Chỉ thêm `lookup` như trên **chưa đủ** để bảo đảm ghi đúng `"NXB-A"`. Spring Data không thể tự suy ra từ biểu thức `#target` rằng phải lấy `Publisher.code` thay vì `Publisher.id`; cần định nghĩa phía ghi.

### 3.2. Viết bộ chuyển đổi `DocumentPointer`

`DocumentPointer<T>` biểu diễn **giá trị sẽ được lưu** làm pointer. Để lưu một chuỗi mã thay vì ID:

```java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;
import org.springframework.data.mongodb.core.mapping.DocumentPointer;

@WritingConverter
public class PublisherPointerConverter
        implements Converter<Publisher, DocumentPointer<String>> {

    @Override
    public DocumentPointer<String> convert(Publisher source) {
        if (source.code() == null || source.code().isBlank()) {
            throw new IllegalArgumentException(
                    "Mã nhà xuất bản phải có trước khi tạo tham chiếu");
        }
        return () -> source.code();
    }
}
```

Điều quan trọng là **kết quả của converter** có kiểu `DocumentPointer<String>`: hàm `getPointer()` (được biểu diễn bằng lambda) trả lại chính chuỗi `"NXB-A"`. Spring Data lưu chuỗi này trong `books.publisher_code`. Khi đọc, `#target` nhận `"NXB-A"` và query tìm `publishers.code == "NXB-A"`.

`@WritingConverter` nói rõ converter dùng theo **chiều ghi**. Nó **không phải** bộ chuyển trực tiếp `String → Publisher`; Spring Data tự đọc entity `Publisher` từ document trả về bởi query lookup. Không tạo converter hai chiều một cách máy móc nếu không có nhu cầu và quy tắc rõ ràng.

### 3.3. Đăng ký converter để Spring Data thực sự sử dụng

Chỉ khai báo class `PublisherPointerConverter` hoặc thêm `@WritingConverter` **chưa đủ**: converter phải được đăng ký vào `MongoCustomConversions` hoặc cơ chế cấu hình converter tương đương của dự án. Ví dụ với Java configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions;

@Configuration
public class MongoReferenceConfiguration {

    @Bean
    public MongoCustomConversions mongoCustomConversions() {
        return MongoCustomConversions.create(adapter ->
                adapter.registerConverter(new PublisherPointerConverter()));
    }
}
```

Ví dụ trên minh họa một dự án chưa khai báo các converter khác. Nếu ứng dụng **đã có** `MongoCustomConversions` hoặc một cấu hình `AbstractMongoClientConfiguration`, hãy **đăng ký converter mới vào cấu hình hiện có** để không bỏ mất converter và quy tắc chuyển đổi khác. Cách cấu hình cụ thể phụ thuộc phiên bản Spring Data MongoDB/Spring Boot mà dự án sử dụng.

Có thể đọc tài liệu chính thức về document references tại:
`https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/document-references.html`.

### 3.4. Lưu riêng đối tượng đích trước, sau đó lưu nguồn

Ví dụ trong một service đã inject `MongoTemplate`:

```java
Publisher publisher = mongoTemplate.insert(
        new Publisher("PUB-001", "NXB-A", "Nhà xuất bản A"));

mongoTemplate.insert(
        new Book("BOOK-001", "Học MongoDB", publisher));
```

Sau khi ghi, kiểm tra BSON thô trong `mongosh`:

```javascript
db.books.findOne(
  { _id: "BOOK-001" },
  { _id: 1, publisher_code: 1 }
);
// Mong đợi: { _id: "BOOK-001", publisher_code: "NXB-A" }
```

Không mong đợi cả object `Publisher` được nhúng trong `books`. Khi đọc lại qua `mongoTemplate.findById("BOOK-001", Book.class)`, Spring Data dùng `lookup` và khôi phục `Book.publisher` thành object `Publisher` đã lưu.

Lưu `Book` **không tự tạo hoặc cập nhật `Publisher`**. Hãy viết rõ thứ tự lưu và xác định cách xử lý nếu mã `code` chưa tồn tại, bị đổi hoặc trùng.

## 4. Tùy chỉnh pointer dạng BSON document

Một chuỗi scalar chỉ đủ khi có **một khóa tra cứu duy nhất**. Trong hệ thống nhiều tenant, cùng mã `externalCode` có thể xuất hiện ở các tenant khác nhau. Khi đó, chỉ tìm theo `externalCode` có thể trả sai dữ liệu của tenant khác.

Giả sử:

```javascript
// suppliers
{ _id: "SUP-1", tenantId: "TENANT-A", externalCode: "ABC",
  name: "Nhà cung cấp A" }
{ _id: "SUP-2", tenantId: "TENANT-B", externalCode: "ABC",
  name: "Nhà cung cấp B" }
```

Ứng dụng muốn mỗi sản phẩm lưu pointer có hai thuộc tính:

```javascript
// products
{
  _id: "PROD-1",
  name: "Bàn làm việc",
  supplier_ref: { tenant: "TENANT-A", code: "ABC" }
}
```

### 4.1. Mapping theo hai field

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "suppliers")
public record Supplier(
        @Id String id,
        String tenantId,
        String externalCode,
        String name
) {}
```

Trong entity `Product`, khai báo:

```java
import org.springframework.data.mongodb.core.mapping.DocumentReference;
import org.springframework.data.mongodb.core.mapping.Field;

@Field("supplier_ref")
@DocumentReference(
        lookup = "{ 'tenantId' : ?#{tenant}, "
               + "'externalCode' : ?#{code} }")
private Supplier supplier;
```

`tenant` và `code` trong SpEL là **các trường trong pointer document**, tương đương truy cập `#target.tenant` và `#target.code`. Spring Data dựng filter có cả hai điều kiện; MongoDB Server áp dụng phép so khớp trên hai field.

### 4.2. Writing converter trả về `DocumentPointer<Document>`

Đây là **ví dụ độc lập** với converter `PublisherPointerConverter` ở mục 3. Đối tượng `Supplier` được chuyển thành một BSON document nhỏ:

```java
import org.bson.Document;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;
import org.springframework.data.mongodb.core.mapping.DocumentPointer;

@WritingConverter
public class SupplierPointerConverter
        implements Converter<Supplier, DocumentPointer<Document>> {

    @Override
    public DocumentPointer<Document> convert(Supplier source) {
        return () -> new Document("tenant", source.tenantId())
                .append("code", source.externalCode());
    }
}
```

Đăng ký cùng các converter khác trong `MongoCustomConversions`:

```java
return MongoCustomConversions.create(adapter -> {
    adapter.registerConverter(new PublisherPointerConverter());
    adapter.registerConverter(new SupplierPointerConverter());
});
```

Đây là **phần thân minh họa của một phương thức cấu hình**, không phải một lớp Java hoàn chỉnh đứng độc lập. Cần kiểm tra đầu vào `tenantId`/`externalCode` hợp lệ và ổn định trước khi tạo reference. Với trường khóa ghép, index nên hỗ trợ đúng query:

```javascript
db.suppliers.createIndex(
  { tenantId: 1, externalCode: 1 },
  { unique: true }
);
```

Unique index trên cặp field giúp ngăn tham chiếu **mơ hồ** khi hai document trong cùng tenant có cùng mã. Nếu dữ liệu cũ đã trùng, phải giải quyết trước khi tạo index.

### 4.3. Pointer theo điều kiện bổ sung

Có thể thêm bộ lọc trong lookup, chẳng hạn chỉ tải nhà cung cấp đang hoạt động:

```java
@DocumentReference(
        lookup = "{ 'tenantId' : ?#{tenant}, "
               + "'externalCode' : ?#{code}, 'active' : true }")
private Supplier supplier;
```

Khi `active = false`, document thực thể vẫn tồn tại nhưng **lookup không trả về** nhà cung cấp đó. Hãy xác định rõ nghiệp vụ mong đợi: trường liên kết có thể không được giải quyết dù ID/mã vẫn hợp lệ. Kiểm soát quyền truy cập tenant ở tầng dịch vụ vẫn cần thiết; **lọc tenant trong lookup không tự thay thế authorization**.

## 5. Tham chiếu ngược: `#self` và `@ReadOnlyProperty`

Không phải lúc nào document nguồn cũng lưu sẵn danh sách pointer. Chẳng hạn, mỗi cuốn sách có `publisherId`, nhưng một nhà xuất bản có thể có **hàng triệu sách**. Không nên duy trì mảng `bookIds` tăng vô hạn trong document `publishers`.

Có thể tạo thuộc tính chỉ phục vụ truy vấn ở phía `Publisher`:

```java
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.ReadOnlyProperty;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.DocumentReference;

@Document(collection = "publishers")
public class PublisherWithBooks {
    @Id
    private String id;

    private String code;

    @ReadOnlyProperty
    @DocumentReference(
            lookup = "{ 'publisherId' : ?#{#self._id} }",
            sort = "{ 'title' : 1 }")
    private List<BookWithPublisherId> books;

    public List<BookWithPublisherId> getBooks() {
        return books;
    }
}

@Document(collection = "books")
class BookWithPublisherId {
    @Id
    private String id;

    private String title;
    private String publisherId;
}
```

Với dữ liệu:

```javascript
// publishers
{ _id: "PUB-001", code: "NXB-A" }

// books
{ _id: "BOOK-001", title: "Java", publisherId: "PUB-001" }
{ _id: "BOOK-002", title: "MongoDB", publisherId: "PUB-001" }
```

Khi Spring Data nạp `PublisherWithBooks`, biểu thức `#self._id` lấy ID từ document `publishers` hiện tại, sau đó tìm các `BookWithPublisherId` có `publisherId == "PUB-001"`. `@ReadOnlyProperty` làm thuộc tính `books` **không được ghi như một mảng pointer trong publisher**. Đây là liên kết **suy ra khi đọc**.

Để hỗ trợ lookup trên server:

```javascript
db.books.createIndex({ publisherId: 1, title: 1 });
```

**Rủi ro quan trọng:** `List<BookWithPublisherId>` là một collection tham chiếu được giải quyết khi truy cập, **không phải một API phân trang tự động**. Nếu nhà xuất bản có hàng triệu cuốn sách, tải toàn bộ danh sách là không phù hợp. Khi đó nên chỉ giữ `publisherId` trên `Book` rồi truy vấn phân trang:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface BookWithPublisherIdRepository
        extends MongoRepository<BookWithPublisherId, String> {

    Page<BookWithPublisherId> findByPublisherId(
            String publisherId, Pageable pageable);
}
```

Trong API thông thường, có thể dùng `findByPublisherId("PUB-001", PageRequest.of(0, 20))`. Khi không cần tổng số phần tử, một `Slice` hoặc chiến lược keyset pagination có thể hạn chế chi phí đếm/`skip`. Lựa chọn phụ thuộc số lượng bản ghi, kiểu trang và truy vấn thực tế.

### 5.1. Vì sao kiểu BSON phải khớp?

Giả sử `publishers._id` thực lưu dưới dạng BSON `ObjectId` nhưng `books.publisherId` là BSON `String` có nội dung 24 ký tự hex. Hai giá trị đó **không bằng nhau** trong MongoDB; query ngược theo `#self._id` có thể trả mảng rỗng.

Với `@Id String id`, Spring Data MongoDB có thể chuyển chuỗi 24-hex hợp lệ thành BSON ObjectId khi ghi ID, trong khi một field String thường như `publisherId` có thể vẫn là BSON String. Do đó phải **thống nhất kiểu BSON** của ID và khóa tham chiếu, không chỉ nhìn kiểu Java hoặc chuỗi hiển thị.

Một cách tránh nhập nhằng cho ID nghiệp vụ là dùng `@MongoId String id` ở document được chủ động lưu `_id` dạng String, hoặc dùng `ObjectId` ở cả hai đầu. Nếu dữ liệu đã lưu khác kiểu, thay annotation chưa đủ: cần khảo sát và di trú có kiểm soát.

## 6. Tải tham chiếu: eager, lazy, số truy vấn và thứ tự

### 6.1. Mặc định eager và lựa chọn lazy

`@DocumentReference` giải quyết tham chiếu **eager theo mặc định**. Có thể hoãn bằng:

```java
@DocumentReference(lazy = true)
private Publisher publisher;
```

Khi lazy, Spring Data tạo cơ chế trì hoãn phân giải và thực hiện truy vấn khi đối tượng liên quan được truy cập. Điều này có thể giảm công việc cho request chỉ cần `Book.title` nhưng không cần `Publisher.name`.

Tuy nhiên, lazy có các chi phí:

- Truy cập property trong vòng lặp có thể sinh ra nhiều lần đọc bổ sung, dẫn tới **N+1 queries**.
- Logging, debugger, serializer JSON hoặc `toString()` có thể vô tình kích hoạt tải dữ liệu.
- Proxy có thể gặp ràng buộc của class Java, final type, constructor và khả năng truy cập module JDK, đặc biệt ở Java 16+.
- Đóng vòng đời xử lý hoặc đổi context rồi mới truy cập lazy có thể gây hành vi bất ngờ cần được kiểm thử trong ứng dụng thực.

Không chọn lazy chỉ vì nhìn annotation “nhẹ” hơn; hãy kiểm tra số lần round-trip và nhu cầu thực tế của endpoint.

### 6.2. Bộ sưu tập tham chiếu và thứ tự

Nếu một field khai báo `List<Publisher>` hoặc `List<Book>` với `@DocumentReference`, Spring Data có thể kết hợp các lookup của collection bằng toán tử **`$or`** để tải liên kết theo nhóm. Framework cố gắng khôi phục thứ tự ban đầu theo lookup trong phạm vi có thể. Với filter không phải equality hoặc điều kiện phức tạp, **không nên phụ thuộc vào thứ tự tự khôi phục**; khi cần, dùng:

```java
@DocumentReference(
        lookup = "{ 'publisherId' : ?#{#self._id} }",
        sort = "{ 'title' : 1 }")
private List<BookWithPublisherId> books;
```

`sort` ở đây được áp dụng theo query phía server. Một mảng liên kết dài vẫn có chi phí đáng kể dù được sắp xếp; muốn phân trang thực sự, dùng query repository hoặc `MongoTemplate` với `limit`/`Pageable`.

### 6.3. Khi nào tải thủ công tốt hơn?

Giả sử một trang hiển thị 40 cuốn sách, mỗi cuốn có nhà xuất bản. Nếu mỗi lần đọc object dẫn tới một lookup riêng, có thể xuất hiện nhiều truy vấn mạng. Nếu chỉ cần tên nhà xuất bản, một hướng khác là:

1. Truy vấn 40 cuốn sách và lấy các mã nhà xuất bản duy nhất.
2. Dùng `PublisherRepository.findByCodeIn(...)` để tải các publisher theo một nhóm mã.
3. Tạo bản đồ `code → publisher` và ghép dữ liệu trong service.

Hoặc thiết kế aggregation `$lookup` nếu phù hợp:

```javascript
db.books.aggregate([
  { $match: { active: true } },
  { $limit: 40 },
  {
    $lookup: {
      from: "publishers",
      localField: "publisher_code",
      foreignField: "code",
      as: "publisherDetails"
    }
  }
]);
```

`$lookup` chạy tại MongoDB Server; `@DocumentReference` do Spring Data phân giải khi ánh xạ object. Hai cách có mô hình thực thi khác nhau nên không mặc định cách nào luôn nhanh hơn. Hãy so sánh query plan, số document trả về, byte qua mạng và tải server trên dữ liệu gần thực tế.

## 7. Index, khóa ổn định và tính nhất quán

Khi tùy chỉnh lookup để tìm theo trường khác `_id`, cần tự hỏi:

1. **Field tra cứu có unique không?** Nếu kỳ vọng mỗi mã trỏ tới đúng một publisher, index unique là một ràng buộc hữu ích.
2. **Field có bị đổi không?** Đổi `code` trong document đích sẽ khiến pointer cũ ngừng khớp trừ khi có quy trình cập nhật các nguồn.
3. **BSON type có khớp không?** `"123"` (String) và `123` (Number) là khác nhau; String hex và ObjectId cũng vậy.
4. **Có lọc thêm trạng thái hay tenant không?** Mỗi điều kiện trong `lookup` cần index và chính sách nghiệp vụ tương ứng.
5. **Số lượng bản ghi và tần suất truy vấn lớn tới đâu?** Hãy đo trước khi quyết định eager/lazy hoặc dùng một query tổng hợp.

Ví dụ dùng mã `code` làm khóa:

```javascript
db.publishers.createIndex({ code: 1 }, { unique: true });

db.publishers.find({ code: "NXB-A" })
  .explain("executionStats");
```

Nếu dữ liệu cũ có mã trùng, tạo unique index sẽ thất bại. Hãy làm sạch dữ liệu và thiết kế cách xử lý thay đổi mã trước khi triển khai. Một reference dùng mã dễ đọc có thể thuận tiện nhưng cũng khiến **đổi mã nghiệp vụ** trở thành thay đổi liên kết. Với trường có thể thay đổi thường xuyên, ID kỹ thuật bất biến thường là pointer bền vững hơn.

### 7.1. Tham chiếu không tự bảo đảm giao dịch

Một `Book` đang trỏ tới `Publisher` không ngăn người khác xóa `Publisher`. Tương tự, đổi mã publisher và cập nhật hàng nghìn book không trở thành nguyên tử chỉ vì dùng `@DocumentReference`.

Nếu nghiệp vụ yêu cầu tính nhất quán giữa nhiều document, hãy thiết kế thao tác ghi phù hợp:

- Có thể từ chối đổi mã hoặc dùng khóa ID bất biến.
- Có thể giữ một bản chụp tên nhà xuất bản lịch sử trong `Book` khi cần xuất hóa đơn/biên bản.
- Với thao tác thật sự cần commit/rollback nhiều document, xem xét **MongoDB transaction** trên deployment hỗ trợ và cấu hình transaction manager Spring Data đúng loại.
- Khi thay đổi dữ liệu với số lượng lớn, cân nhắc quy trình migration, trạng thái chuyển tiếp, retry và đối soát liên kết.

Không dựa vào `@DocumentReference` để “cascading save” hoặc áp ràng buộc foreign key giống hệ quản trị quan hệ.

### 7.2. Chẩn đoán một tham chiếu không giải quyết được

Thứ tự kiểm tra hợp lý:

1. Đọc **BSON gốc** của document nguồn: pointer có phải `"NXB-A"` hay lại là `"PUB-001"`?
2. Kiểm tra **query lookup thực tế**: nó tìm theo `code`, `_id`, hay cặp `tenantId`/`externalCode`?
3. Chạy query tương đương trong `mongosh` để xem có 0, 1 hay nhiều kết quả.
4. So sánh **BSON type** của pointer và field đích; xem xét `@Id`/`@MongoId` và converter.
5. Xác minh converter đã **được đăng ký**; đừng chỉ kiểm tra annotation có trong code.
6. Kiểm tra field thật trong BSON khi dùng `@Field`, điều kiện soft-delete/active và index.
7. Nếu gặp hành vi chỉ xảy ra khi serialize/log, kiểm tra việc vô tình kích hoạt lazy proxy.

Không log toàn bộ document chứa dữ liệu nhạy cảm trong production chỉ để dò lỗi; có thể log mã truy vấn đã ẩn dữ liệu, số lượng query, thời gian và loại lỗi.

## 8. Giới hạn khi dùng reactive access

Spring Data MongoDB có `ReactiveMongoTemplate` và `ReactiveMongoRepository` cho I/O không chặn. Tuy nhiên, **theo tài liệu Spring Data MongoDB 4.5 và 5.1, cơ chế đọc `@DocumentReference` chưa được hỗ trợ trong reactive infrastructure**. Không nên giả định trường `@DocumentReference` được tự động phân giải trong một luồng reactive chỉ vì repository trả về `Mono`/`Flux`.

Nếu ứng dụng của bạn dùng reactive, một cách rõ ràng là **lưu mã/ID thủ công** và chủ động truy vấn collection đích bằng `ReactiveMongoTemplate` hoặc reactive repository:

```java
import reactor.core.publisher.Mono;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

// BookRow chứa field publisherCode thay cho @DocumentReference.
public Mono<Publisher> loadPublisher(
        ReactiveMongoTemplate template,
        String publisherCode
) {
    Query query = Query.query(
            Criteria.where("code").is(publisherCode));
    return template.findOne(query, Publisher.class);
}
```

Đây là **đoạn phương thức minh họa trong một service**, cần đặt vào class Java phù hợp. Với nhiều item, hãy tổ chức batch/query/aggregation thích hợp để không tạo N+1 trong `Flux`. Đối chiếu tài liệu **đúng phiên bản Spring Data** mà dự án sử dụng, vì khả năng của framework có thể thay đổi trong tương lai.

Không gọi blocking `MongoTemplate` trên event loop reactive để thay thế việc phân giải tham chiếu. Reactive chỉ thay đổi mô hình điều phối I/O, không tự tạo index hoặc giảm số truy vấn MongoDB Server.

## 9. Kiểm thử mapping và custom lookup trên MongoDB thật

Unit test gọi trực tiếp `PublisherPointerConverter.convert(...)` giúp kiểm tra kết quả pointer, nhưng **chưa chứng minh** Spring Data đã đăng ký converter, đã ghi đúng BSON, hay lookup thật có thể tải được publisher. Nên có **integration test** chạy với MongoDB test instance riêng, ví dụ Testcontainers, kết hợp `@DataMongoTest` và cấu hình converter phù hợp.

### 9.1. Kiểm thử chiều ghi và chiều đọc

Ví dụ bên dưới sử dụng các class `Publisher`, `Book`, `PublisherPointerConverter` và `MongoReferenceConfiguration` được định nghĩa ở mục 1 và 3. Lưu ý khi tích hợp: `Book` phải sử dụng khai báo `@Field("publisher_code") @DocumentReference(lookup = ...)` của mục 3.1, không còn khai báo `@DocumentReference` mặc định.

```java
import static com.mongodb.client.model.Filters.eq;
import static org.assertj.core.api.Assertions.assertThat;

import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;

@DataMongoTest
@Import(MongoReferenceConfiguration.class)
class CustomDocumentReferenceTest {

    @Autowired
    MongoTemplate template;

    @Test
    void storesCodePointerAndResolvesPublisher() {
        Publisher publisher = template.insert(
                new Publisher("PUB-101", "NXB-TEST", "Nhà xuất bản Test"));

        template.insert(
                new Book("BOOK-101", "Kiểm thử MongoDB", publisher));

        // Đọc BSON raw, không đi qua cơ chế mapping của Book.
        Document rawBook = template.getCollection("books")
                .find(eq("_id", "BOOK-101"))
                .first();

        assertThat(rawBook).isNotNull();
        assertThat(rawBook.getString("publisher_code"))
                .isEqualTo("NXB-TEST");
        assertThat(rawBook.containsKey("publisher")).isFalse();

        // Kiểm tra query lookup đã phân giải thành Publisher.
        Book loaded = template.findById("BOOK-101", Book.class);
        assertThat(loaded).isNotNull();
        assertThat(loaded.getPublisher()).isNotNull();
        assertThat(loaded.getPublisher().code()).isEqualTo("NXB-TEST");
        assertThat(loaded.getPublisher().id()).isEqualTo("PUB-101");
    }
}
```

**Quan trọng:** `@DataMongoTest` chỉ khởi tạo test slice và các thành phần MongoDB cần thiết; nó **không tự đảm bảo có MongoDB Server** ở mọi môi trường. Hãy cấp MongoDB test instance thật, database riêng, dọn dữ liệu giữa các test. `@Import` giúp cấu hình converter của bài được đưa vào test. Nếu dự án đã có cách cấu hình converter riêng, dùng cách đó thay vì tạo thêm bean `MongoCustomConversions` xung đột.

Test này kiểm tra đồng thời:

1. **Chiều ghi:** BSON thô chứa `publisher_code: "NXB-TEST"`.
2. **Chiều đọc:** `lookup` theo `code` tìm được đúng `Publisher`.
3. **Không nhúng:** document book không chứa cả object `publisher`.
4. **Không nhầm ID:** pointer không phải `"PUB-101"`.

### 9.2. Trường hợp biên cần kiểm tra

| Ca kiểm thử | Dữ liệu | Kết quả cần đánh giá |
| --- | --- | --- |
| Mã đúng và duy nhất | Một `Publisher` có `code = "NXB-A"` | Lookup tìm chính xác đối tượng |
| Converter chưa đăng ký | Book ghi theo mapping thiếu converter | Test BSON raw cho thấy sai giá trị hoặc ghi lỗi; không xem chỉ đọc entity là đủ |
| Mã publisher thay đổi | Book vẫn lưu pointer cũ | Xác định chính sách cập nhật pointer, giữ alias hoặc dùng ID bất biến |
| Có hai publisher cùng mã | Dữ liệu cũ vi phạm tính duy nhất | Unique index/migration ngăn kết quả tham chiếu mơ hồ |
| Publisher đã bị xóa | Pointer còn trong book | Hành vi khi thiếu liên kết được xử lý theo quy tắc nghiệp vụ |
| Pointer có kiểu BSON khác | String ở nguồn, ObjectId ở đích | Lookup không tự ép thành cùng kiểu; phát hiện bằng test raw |
| Khóa ghép tenant–code | Hai tenant cùng code | Không được trả publisher của tenant khác |
| Reverse lookup nhiều book | `publisherId` được lưu ở book | `@ReadOnlyProperty` không ghi mảng book vào publisher |
| Lazy reference | Chỉ lấy tiêu đề book rồi truy cập publisher | Xác định thời điểm query phát sinh, phát hiện N+1 nếu có |
| Book từ dữ liệu nhập cũ | Tên field hoặc hình dạng pointer khác | Kiểm tra tương thích và chiến lược migration |

### 9.3. Kiểm tra index và query ở MongoDB Server

Với custom lookup tìm publisher theo code:

```javascript
db.publishers.getIndexes();

db.publishers.find({ code: "NXB-TEST" })
  .explain("executionStats");
```

Quan sát `totalDocsExamined`, `totalKeysExamined`, kiểu plan và số kết quả. Với collection nhỏ, MongoDB Server có thể chọn `COLLSCAN` ngay cả khi index tồn tại; muốn đánh giá hiệu năng, tạo dữ liệu thử đủ lớn và sát phân phối dữ liệu thật.

Đối với khóa ghép, kiểm tra thêm:

```javascript
db.suppliers.find({
  tenantId: "TENANT-A",
  externalCode: "ABC"
}).explain("executionStats");
```

Query này cần khớp kiểu BSON của pointer `tenant`/`code` đã ghi. Khi số kết quả khác mong đợi, hãy kiểm tra dữ liệu raw và index trước khi tăng log debug.

## 10. Những lỗi dễ mắc khi tùy chỉnh tham chiếu

| Sai lầm | Dấu hiệu | Hướng sửa |
| --- | --- | --- |
| Đổi `lookup` sang `code` nhưng không đổi cách ghi pointer | Book còn lưu `publisherId`, lookup theo `code` không tìm thấy | Tạo `DocumentPointer` writing converter hoặc dùng biểu thức lookup phù hợp với dữ liệu đã lưu |
| Có class converter nhưng chưa đăng ký | BSON vẫn mang cấu trúc mặc định hoặc ghi lỗi | Đăng ký qua `MongoCustomConversions` và kiểm tra bằng test raw |
| Tạo một bean `MongoCustomConversions` mới mà bỏ các converter đang dùng | Mapping `Decimal128`, ngày tháng hoặc kiểu tùy chỉnh khác bị đổi | Hợp nhất converter vào cấu hình hiện tại |
| Tìm bằng khóa không unique | Một mã có nhiều đối tượng đích | Tạo unique index/đổi khóa; xử lý dữ liệu trùng trước |
| Khóa đích thay đổi thường xuyên | Pointer mồ côi sau khi đổi mã | Dùng ID bất biến hoặc quản lý migration/snapshot |
| `String` và `ObjectId` không khớp | `#self._id` trả ObjectId trong khi field đích là String | Thống nhất kiểu BSON; thử query raw |
| Lạm dụng lazy trong vòng lặp | Tăng số query và độ trễ | Batch ID, dùng repository query/aggregation hoặc điều chỉnh DTO |
| Đưa danh sách vô hạn vào reverse reference | Một request tải hàng nghìn/hàng triệu đối tượng | Dùng phân trang theo khóa nguồn; không tải toàn bộ collection |
| Dùng `@DocumentReference` như foreign key | Xóa document đích vẫn còn pointer | Xây chính sách xóa/đối soát; transaction nếu thật sự cần |
| Giả định reactive tự phân giải reference | Đọc entity reactive không có hành vi mong đợi | Dùng khóa ID/mã và reactive query tường minh theo phiên bản hỗ trợ |
| Giả định reference tự kiểm tra quyền | Trả dữ liệu publisher/supplier sai tenant | Kiểm tra authorization độc lập và thiết kế boundary rõ ràng |

## 11. Bài tập thực hành: khóa liên kết theo mã đối tác

Hệ thống bán hàng nhận dữ liệu từ nhiều nhà cung cấp. Mỗi nhà cung cấp có một mã `partnerCode`; mã chỉ duy nhất **trong một tenant**. Một sản phẩm thuộc về một nhà cung cấp nhưng trang sản phẩm không cần hiển thị chi tiết nhà cung cấp trong mọi request.

Dữ liệu:

```javascript
// suppliers
{ _id: "S1", tenantId: "T-A", partnerCode: "P-7",
  name: "Đơn vị A", active: true }
{ _id: "S2", tenantId: "T-B", partnerCode: "P-7",
  name: "Đơn vị B", active: true }

// products
{ _id: "PR-1", tenantId: "T-A", name: "Bàn làm việc",
  supplierRef: { tenant: "T-A", code: "P-7" } }
```

Yêu cầu:

1. Khai báo `@DocumentReference` sao cho `supplierRef` được phân giải bằng cả `tenantId` và `partnerCode`.
2. Viết một `@WritingConverter` trả về `DocumentPointer<Document>` với hai trường `tenant` và `code`.
3. Quy định unique index nào nên có ở `suppliers` và giải thích vì sao chỉ index trên `partnerCode` là chưa đủ.
4. Đề xuất cách hiển thị tên nhà cung cấp cho 100 sản phẩm mà không phát sinh N+1 query.
5. Kiểm tra tình huống nhà cung cấp bị khóa `active = false` hoặc đổi `partnerCode`.

Một phương án tham khảo:

```java
@DocumentReference(lookup =
        "{ 'tenantId' : ?#{tenant}, 'partnerCode' : ?#{code} }")
private Supplier supplier;
```

Và writing converter:

```java
@WritingConverter
class SupplierReferenceConverter
        implements Converter<Supplier, DocumentPointer<Document>> {

    @Override
    public DocumentPointer<Document> convert(Supplier supplier) {
        return () -> new Document("tenant", supplier.tenantId())
                .append("code", supplier.partnerCode());
    }
}
```

Trong đoạn code trên, `Supplier` là class minh họa của bài tập có phương thức `tenantId()` và `partnerCode()`; cần khai báo/import kiểu khi đặt vào project thực. Không đăng ký đồng thời nhiều converter có cùng source/target mà không có chiến lược rõ, vì việc chọn converter có thể mơ hồ. Index phù hợp để bảo đảm khóa tra cứu duy nhất:

```javascript
db.suppliers.createIndex(
  { tenantId: 1, partnerCode: 1 },
  { unique: true }
);
```

Để hiển thị 100 sản phẩm, có thể gom các khóa `(tenantId, partnerCode)` cần thiết và truy vấn `suppliers` theo nhóm hoặc dùng aggregation `$lookup` với điều kiện đúng kiểu dữ liệu; so sánh hiệu năng thay vì mặc định eager/lazy là tốt nhất.

Trong ví dụ này, nếu mã đối tác có thể thay đổi, nên cân nhắc dùng `_id` ổn định hoặc cung cấp bảng ánh xạ/alias. `@DocumentReference` không tự cập nhật pointer cũ.

## 12. Checklist áp dụng vào dự án

Trước khi dùng custom document reference, hãy tự trả lời:

1. **Pointer được lưu là gì?** ID, String nghiệp vụ hay BSON document với nhiều field?
2. **Lookup phải tìm trường nào ở document đích?** `_id`, `code` hay khóa ghép?
3. **Tầng ghi đã được cấu hình chưa?** Nếu dùng scalar/khóa ghép khác ID, `DocumentPointer` converter có được đăng ký không?
4. **Có ràng buộc unique cho khóa tra cứu không?** Một pointer phải giải quyết ra đúng thực thể nào?
5. **Các kiểu BSON có thống nhất không?** Đặc biệt là `@Id String` so với `ObjectId` và field tham chiếu thông thường.
6. **Quan hệ có cần phân trang hay tải theo batch không?** Eager/lazy hoặc `List` có tạo quá nhiều round-trip không?
7. **Nguồn chuẩn và vòng đời liên kết thế nào?** Đổi mã, xóa entity và dữ liệu lịch sử xử lý ra sao?
8. **Có yêu cầu nhiều tenant, phân quyền hoặc dữ liệu nhạy cảm không?** Lookup chưa thay thế kiểm soát truy cập.
9. **Ứng dụng blocking hay reactive?** Khả năng đọc document reference của phiên bản Spring Data đang dùng có hỗ trợ không?
10. **Đã kiểm thử trên MongoDB thật chưa?** Có kiểm tra BSON raw, kết quả lookup, index, dữ liệu thiếu/trùng và số query?

**Quy tắc ghi nhớ:** `@DocumentReference.lookup` định nghĩa **cách đọc** liên kết; `Converter<ĐốiTượng, DocumentPointer<...>>` xác định **giá trị pointer được ghi**. `#target` trỏ tới giá trị tham chiếu lưu trong document, còn `#self` hỗ trợ lookup ngược theo document nguồn. Mọi cấu hình chỉ đáng tin khi **BSON ở hai đầu khớp nhau, khóa tra cứu được đánh index phù hợp, converter đã đăng ký và hành vi đọc/ghi được kiểm chứng trong MongoDB thực**.

### Tài liệu tham khảo

- [Spring Data MongoDB — Using Document References](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/document-references.html): `@DocumentReference`, `lookup`, `DocumentPointer`, lookup ngược và các lưu ý hiệu năng.
- [Spring Data MongoDB — Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html): cơ chế đăng ký và định hướng writing/reading converter.

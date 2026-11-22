# Chọn hoặc loại trường trả về và ngoại lệ của _id

## 1. Bối cảnh và mục tiêu

Một document MongoDB có thể chứa nhiều trường phục vụ các nghiệp vụ khác nhau. Màn hình danh sách sản phẩm thường chỉ cần tên, giá và mã sản phẩm; trang chi tiết có thể cần mô tả, tồn kho, nhà cung cấp và nhiều thông tin khác. Nếu mọi truy vấn đều tải toàn bộ document, ứng dụng có thể truyền và ánh xạ dữ liệu không cần thiết, đồng thời có nguy cơ công bố nhầm trường nội bộ.

**Projection** là cách chỉ định các trường MongoDB trả về cho một truy vấn. Trong truy vấn **find**, projection có hai cách viết cơ bản: **chọn (inclusion)** các trường muốn giữ và **loại (exclusion)** các trường không muốn nhận. Riêng trường khóa **_id** là ngoại lệ quan trọng: nó được trả về mặc định, ngay cả khi ta chỉ chọn một số trường khác, và có thể được loại riêng mà không vi phạm quy tắc không trộn inclusion/exclusion.

Chủ đề này thuộc chương **Projection và DTO** trong module **SPRING_DATA_MONGODB**. Nó liên quan trực tiếp đến ánh xạ document, MongoTemplate, repository và cách trả response DTO. Thiết kế projection còn ảnh hưởng đến aggregation, index, kiểm thử, hiệu năng truy vấn và các đường truy cập dữ liệu reactive.

Sau bài học, bạn cần:

1. Hiểu các chế độ projection trong MongoDB find.
2. Nhớ chính xác quy tắc mặc định và ngoại lệ của trường **_id**.
3. Sử dụng **@Query(fields = ...)** và **MongoTemplate Query.fields()**.
4. Chọn field cho DTO/interface projection, tránh ánh xạ nhầm entity thiếu dữ liệu.
5. Phân biệt chọn field nhúng với lọc phần tử mảng và phép biến đổi trong aggregation.
6. Đánh giá projection theo nguyên tắc API an toàn và hiệu năng thực tế.
7. Kiểm thử hình dạng BSON được trả về, không chỉ test giá trị getter của DTO.

## 2. Document mẫu: products

Giả sử collection **products** có document:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  sku: "BOOK-001",
  name: "Sổ tay Spring Data MongoDB",
  priceMinor: NumberLong("159000"),
  active: true,
  description: "Tài liệu hướng dẫn về lưu trữ document.",
  tags: ["JAVA", "SPRING", "MONGODB"],
  supplier: {
    code: "SUP-01",
    internalNote: "Chính sách chiết khấu nội bộ."
  },
  createdAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

Ở đây, priceMinor là số nguyên đơn vị tiền nhỏ nhất theo hợp đồng nghiệp vụ; createdAt là BSON Date; _id là BSON ObjectId. Một API danh sách có thể cần _id, sku, name, priceMinor nhưng không cần description, tags hay supplier.internalNote.

Entity minh họa bằng Java record:

~~~java
package com.example.catalog;

import java.time.Instant;
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
public record ProductDocument(
    @Id ObjectId id,
    String sku,
    String name,
    long priceMinor,
    boolean active,
    String description,
    List<String> tags,
    Supplier supplier,
    Instant createdAt
) {
    public record Supplier(String code, String internalNote) {}
}
~~~

Tên collection do **@Document** xác định. Property Java id được ánh xạ thành BSON _id nhờ **@Id**. Trong ví dụ, các property còn lại trùng tên BSON field; ứng dụng có **@Field** có thể dùng tên BSON khác.

## 3. Hai vai trò của filter và projection

Lệnh find có thể nhận một filter và một projection:

~~~javascript
db.products.find(
  { active: true },       // Filter: chọn document nào?
  { sku: 1, name: 1 }    // Projection: trả field nào?
);
~~~

Filter chọn các document khớp active = true. Projection làm kết quả chỉ còn những field được yêu cầu, ngoài ngoại lệ _id. **Projection không sửa document đã lưu**, không tạo collection khác và không biến điều kiện lọc thành phép update.

~~~mermaid
flowchart LR
    A["products document đầy đủ"] --> B["Filter active = true"]
    B --> C["Projection sku, name"]
    C --> D["BSON kết quả thu gọn"]
    D --> E["Spring Data mapping / DTO"]
~~~

Với find projection đơn giản, **1** biểu thị giữ trường (inclusion) và **0** biểu thị bỏ trường (exclusion).

### 3.1. Inclusion: chọn đúng trường cần dùng

~~~javascript
db.products.find(
  { active: true },
  { sku: 1, name: 1, priceMinor: 1 }
);
~~~

Một kết quả:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  sku: "BOOK-001",
  name: "Sổ tay Spring Data MongoDB",
  priceMinor: NumberLong("159000")
}
~~~

_id xuất hiện dù projection không ghi _id: 1. Trong inclusion mode, **MongoDB trả _id mặc định**. Những field khác như description, active, tags, supplier hay createdAt không được trả vì không có trong danh sách chọn.

### 3.2. Exclusion: loại một số trường

~~~javascript
db.products.find(
  { active: true },
  { description: 0, "supplier.internalNote": 0 }
);
~~~

Ở chế độ này, kết quả giữ mọi trường còn lại, trong đó có _id, sku, name, priceMinor, active, tags, supplier.code và createdAt. Hai field được chỉ định bị loại.

Điểm cần chú ý: **exclusion không phải whitelist**. Nếu collection được bổ sung field privateCost vào ngày mai, projection trên vẫn có thể trả privateCost. Vì vậy, với API công khai, nên ưu tiên inclusion rõ ràng hơn việc cố liệt kê mọi field phải loại.

## 4. Ngoại lệ của _id trong MongoDB

Đây là quy tắc trọng tâm: **_id được trả mặc định, nhưng được phép loại riêng bằng _id: 0**. MongoDB chấp nhận việc include những trường khác đồng thời exclude _id. Nó cũng cho phép exclude những trường khác và chỉ định _id tường minh.

| Projection | Chế độ | Kết quả |
| --- | --- | --- |
| { name: 1 } | Inclusion | name và _id |
| { name: 1, _id: 1 } | Inclusion | name và _id |
| { name: 1, _id: 0 } | Inclusion + ngoại lệ _id | Chỉ name |
| { description: 0 } | Exclusion | Tất cả trừ description, vẫn có _id |
| { description: 0, _id: 0 } | Exclusion + ngoại lệ _id | Tất cả trừ description và _id |
| { description: 0, _id: 1 } | Exclusion, khai báo _id | Tất cả trừ description, vẫn có _id |
| { _id: 0 } | Chỉ loại _id | Mọi field khác |
| {} | Không giới hạn | Document đầy đủ, có _id |

### 4.1. Chọn name nhưng không trả _id

~~~javascript
db.products.find(
  { active: true },
  { name: 1, _id: 0 }
);
~~~

Kết quả:

~~~javascript
{ name: "Sổ tay Spring Data MongoDB" }
~~~

Tổ hợp **name: 1, _id: 0** hợp lệ. Đây là ngoại lệ được MongoDB thiết kế riêng cho field _id.

### 4.2. Loại cả description và _id

~~~javascript
db.products.find(
  { active: true },
  { description: 0, _id: 0 }
);
~~~

Kết quả có mọi field ngoài description và _id. Nếu sau này có field mới, nó vẫn có thể xuất hiện.

### 4.3. Khi nào nên giữ ID?

Giữ ID khi cần tạo liên kết tới trang chi tiết, gọi API cập nhật/xóa, phân biệt document có cùng tên hoặc gắn khóa ổn định cho cache/giao diện. Bỏ ID khi xuất báo cáo không cần định danh, API cố ý dùng mã công khai riêng hoặc tác vụ chỉ cần giá trị tổng hợp.

Không nên bỏ _id chỉ để tiết kiệm vài byte nếu quy trình sau đó cần tìm lại document. Ngược lại, cũng không nên vô tình công bố ID kỹ thuật nếu hợp đồng API không cho phép.

## 5. Không được trộn inclusion và exclusion tùy ý

Đối với projection find thông thường, MongoDB không cho phép vừa include một field vừa exclude một field khác **trừ _id**.

Hợp lệ:

~~~javascript
{ sku: 1, name: 1, _id: 0 }
{ description: 0, "supplier.internalNote": 0, _id: 0 }
{ sku: 1, name: 1 }
{ description: 0 }
~~~

Không hợp lệ theo quy tắc cơ bản:

~~~javascript
{ sku: 1, description: 0 }
{ name: 1, "supplier.internalNote": 0 }
~~~

Trường hợp đầu yêu cầu chỉ giữ sku nhưng đồng thời loại description. Trường hợp thứ hai cũng trộn include/exclude ngoài _id. Chọn một trong hai chiến lược thay vì cố trộn.

### 5.1. Sửa projection để chỉ trả ba field công khai

**Sai:**

~~~javascript
{ sku: 1, name: 1, priceMinor: 1, "supplier.internalNote": 0 }
~~~

**Đúng nếu không cần _id:**

~~~javascript
{ sku: 1, name: 1, priceMinor: 1, _id: 0 }
~~~

**Đúng nếu cần _id:**

~~~javascript
{ sku: 1, name: 1, priceMinor: 1 }
~~~

Trong inclusion, không cần exclude internalNote vì nó không được chọn. Đây là cách đơn giản để biểu diễn hợp đồng dữ liệu công khai.

## 6. Projection với @Query(fields = ...)

Spring Data MongoDB có annotation:

~~~java
import org.springframework.data.mongodb.repository.Query;
~~~

Thuộc tính **value** biểu diễn filter, còn **fields** biểu diễn projection. Ví dụ:

~~~java
@Query(
    value = "{ 'active': true }",
    fields = "{ 'sku': 1, 'name': 1, 'priceMinor': 1 }"
)
List<ProductCardView> findActiveCards();
~~~

Trường _id không được nhắc đến nên mặc định vẫn được trả. Nếu không cần _id:

~~~java
@Query(
    value = "{ 'active': true }",
    fields = "{ 'sku': 1, 'name': 1, 'priceMinor': 1, '_id': 0 }"
)
List<ProductExportView> findActiveForExport();
~~~

Nếu filter nhận một tham số:

~~~java
@Query(
    value = "{ 'sku': ?0 }",
    fields = "{ 'name': 1, '_id': 0 }"
)
Optional<ProductNameView> findNameBySku(String sku);
~~~

**?0** là placeholder cho tham số method đầu tiên. Nó không liên quan tới số 0 trong projection: **?0** biểu thị vị trí tham số, còn **_id: 0** yêu cầu loại trường _id.

### 6.1. Interface projection

~~~java
import org.bson.types.ObjectId;

public interface ProductCardView {
    ObjectId getId();
    String getSku();
    String getName();
    long getPriceMinor();
}

public interface ProductExportView {
    String getSku();
    String getName();
    long getPriceMinor();
}

public interface ProductNameView {
    String getName();
}
~~~

ProductCardView có getId vì truy vấn không loại _id. ProductExportView và ProductNameView không cần ID. Những interface trên là **view đọc dữ liệu**, không phải entity để save lại.

### 6.2. Repository đầy đủ

~~~java
package com.example.catalog;

import java.util.List;
import java.util.Optional;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface ProductRepository
        extends MongoRepository<ProductDocument, ObjectId> {

    @Query(
        value = "{ 'active': true }",
        fields = "{ 'sku': 1, 'name': 1, 'priceMinor': 1 }"
    )
    List<ProductCardView> findActiveCards();

    @Query(
        value = "{ 'active': true }",
        fields = "{ 'sku': 1, 'name': 1, 'priceMinor': 1, '_id': 0 }"
    )
    List<ProductExportView> findActiveForExport();

    @Query(
        value = "{ 'sku': ?0 }",
        fields = "{ 'name': 1, '_id': 0 }"
    )
    Optional<ProductNameView> findNameBySku(String sku);
}
~~~

Ví dụ dùng chữ ký repository để biểu thị rõ mỗi endpoint cần kiểu kết quả nào. Khi projection thiếu trường mà return type vẫn là ProductDocument, framework có thể tạo object thiếu dữ liệu hoặc không materialize được, đặc biệt với primitive và constructor bắt buộc.

### 6.3. Exclusion với @Query

~~~java
@Query(
    value = "{ 'active': true }",
    fields = "{ 'description': 0, 'supplier.internalNote': 0 }"
)
List<ProductDocument> findWithoutDescriptions();
~~~

Đây là ví dụ cú pháp; **không nên dùng kết quả ProductDocument một phần để save** hoặc trả nguyên entity đó ra API công khai. Với API có hợp đồng rõ, hãy dùng inclusion kết hợp interface projection/DTO.

## 7. MongoTemplate: include và exclude qua Query.fields()

MongoTemplate hỗ trợ xây projection không cần nhúng JSON string vào annotation:

~~~java
import java.util.List;
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<Document> loadCards(MongoTemplate template) {
    Query query = Query.query(Criteria.where("active").is(true));

    query.fields()
        .include("sku")
        .include("name")
        .include("priceMinor")
        .exclude("_id");

    return template.find(query, Document.class, "products");
}
~~~

Ở đây, MongoTemplate trả về Document thô để minh họa kết quả projection có đúng sku, name và priceMinor mà không có _id. Trong mã nghiệp vụ thực tế, thường nên ánh xạ sang một DTO cho mục đích đọc.

Exclusion:

~~~java
Query query = Query.query(Criteria.where("active").is(true));
query.fields()
    .exclude("description")
    .exclude("supplier.internalNote")
    .exclude("_id");

List<Document> results =
    mongoTemplate.find(query, Document.class, "products");
~~~

Nhớ rằng trường nào không được exclude vẫn có thể xuất hiện trong kết quả.

### 7.1. Một lỗi ở API builder

~~~java
// Không hợp lệ: trộn inclusion/exclusion ngoài _id.
query.fields()
    .include("name")
    .exclude("description");
~~~

API Java có thể cho phép xây object query, nhưng server có thể từ chối projection vì trái quy tắc cơ bản. Hãy chỉ dùng include, chỉ dùng exclude hoặc include kết hợp exclude("_id").

### 7.2. Chọn collection bằng entity hoặc tên

~~~java
// Collection suy từ @Document(collection = "products").
List<ProductDocument> mapped =
    mongoTemplate.find(query, ProductDocument.class);

// Collection được chỉ định trực tiếp.
List<Document> raw =
    mongoTemplate.find(query, Document.class, "products");
~~~

Khi query được mapping qua metadata ProductDocument, @Field và @Id có thể ảnh hưởng tên field BSON. Khi thao tác với Document thô hoặc driver, cần sử dụng chính xác tên field thực đã lưu.

## 8. Khác biệt giữa _id BSON và id Java

Entity có thể có:

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;

@Id
private ObjectId id;
~~~

MongoDB lưu trường **_id**, trong khi object Java có property **id**. Quy tắc include mặc định và ngoại lệ exclude áp dụng cho **_id BSON**, dù ứng dụng có dùng một property Java tên khác.

Nếu projection loại _id nhưng interface vẫn khai báo getId, ID sẽ không có dữ liệu để ánh xạ theo hợp đồng. Thiết kế view phù hợp: giữ _id khi cần định danh, hoặc bỏ accessor ID khi query chủ động loại _id.

### 8.1. ID trong DTO công khai

MongoDB có thể lưu:

~~~javascript
{ _id: ObjectId("507f1f77bcf86cd799439011") }
~~~

API có thể công bố:

~~~json
{
  "id": "507f1f77bcf86cd799439011"
}
~~~

Đây là việc **chuyển biểu diễn** ObjectId sang chuỗi hex phục vụ HTTP/JSON. Không nhầm chuỗi hex JSON với BSON ObjectId. Nếu API không muốn công bố ID kỹ thuật, có thể dùng một public ID riêng nhưng phải thiết kế quan hệ giữa hai loại ID.

## 9. DTO là hợp đồng dữ liệu được công bố

Projection quyết định MongoDB trả field gì, còn **DTO** quyết định service hoặc API trình bày dữ liệu theo cấu trúc nào. Hai cơ chế phối hợp nhưng không thay thế nhau.

~~~mermaid
flowchart LR
    A["MongoDB products"] --> B["Projection: _id, sku, name, priceMinor"]
    B --> C["ProductCardView"]
    C --> D["ProductCardDto"]
    D --> E["JSON response"]
~~~

Một DTO độc lập với lớp ObjectId Java:

~~~java
public record ProductCardDto(
    String id,
    String sku,
    String name,
    long priceMinor
) {}
~~~

Mapping ở service:

~~~java
import java.util.List;

public List<ProductCardDto> listCards() {
    return repository.findActiveCards().stream()
        .map(p -> new ProductCardDto(
            p.getId().toHexString(),
            p.getSku(),
            p.getName(),
            p.getPriceMinor()
        ))
        .toList();
}
~~~

Đoạn mã giả định repository là dependency của service và document hợp lệ có ID. DTO giúp API kiểm soát tên trường và kiểu ID, đồng thời tránh trả trực tiếp một ProductDocument chứa dữ liệu nội bộ.

### 9.1. DTO không cần ID

~~~java
public record ProductExportDto(
    String sku,
    String name,
    long priceMinor
) {}
~~~

Với DTO này, projection có thể include sku, name, priceMinor và **exclude _id**. Không viết code gọi getId khi kiểu kết quả đã loại ID.

### 9.2. Vì sao nên ưu tiên inclusion với public API?

Giả sử dự án có projection exclusion:

~~~javascript
{ description: 0, "supplier.internalNote": 0 }
~~~

Sau đó developer thêm supplier.bankAccount và internalCost. Những field mới có thể được trả cùng kết quả dù chưa được rà soát để công bố.

Với inclusion:

~~~javascript
{ sku: 1, name: 1, priceMinor: 1, _id: 1 }
~~~

Chỉ những trường đã chọn được trả, kể cả khi document được mở rộng sau này. Đây là cách giữ **response contract ổn định** và hạn chế nguy cơ lộ field ngoài dự kiến.

### 9.3. Dùng class/record projection trực tiếp

Spring Data hỗ trợ nhiều dạng projection, bao gồm interface projection và class-based DTO tùy phiên bản/cơ chế constructor binding. Nếu trả về record DTO trực tiếp từ repository, constructor phải có các tham số có thể ánh xạ từ kết quả. Một DTO bất kỳ không tự materialize đúng khi thiếu field bắt buộc.

**Cách dễ kiểm soát** là repository trả interface projection, service chuyển sang record DTO, nhất là khi cần chuyển ObjectId sang String hoặc chuẩn hóa giá trị hiển thị.

## 10. Projection trên embedded object

Trong document mẫu, supplier là một object:

~~~javascript
{
  supplier: {
    code: "SUP-01",
    internalNote: "Chính sách nội bộ"
  }
}
~~~

Muốn lấy riêng mã nhà cung cấp:

~~~javascript
db.products.find(
  { active: true },
  { "supplier.code": 1, _id: 0 }
);
~~~

Kết quả minh họa:

~~~javascript
{
  supplier: {
    code: "SUP-01"
  }
}
~~~

**supplier.code** là dot notation chọn một field trong subdocument. Nó không yêu cầu đọc thêm collection và không biến code thành field top-level.

Trong repository:

~~~java
@Query(
    value = "{ 'active': true }",
    fields = "{ 'supplier.code': 1, '_id': 0 }"
)
List<SupplierCodeView> findSupplierCodes();
~~~

Interface lồng nhau có thể phản ánh cấu trúc BSON:

~~~java
public interface SupplierCodeView {
    SupplierView getSupplier();

    interface SupplierView {
        String getCode();
    }
}
~~~

Nếu muốn **loại** một field lồng nhau nhưng giữ các field khác:

~~~javascript
db.products.find(
  { active: true },
  { "supplier.internalNote": 0 }
);
~~~

Với exclusion, supplier.code vẫn được trả. Nếu sau này supplier có field mới, field ấy cũng có thể xuất hiện.

### 10.1. Khi Java dùng @Field khác tên BSON

Ví dụ:

~~~java
import org.springframework.data.mongodb.core.mapping.Field;

@Field("supplier_code")
private String supplierCode;
~~~

Spring Data có thể mapping property supplierCode thành BSON supplier_code trong các đường truy vấn/projection theo entity metadata. Khi truy vấn bằng mongosh hoặc MongoDB Java Driver trực tiếp, phải dùng **supplier_code**. Với custom converters hoặc nested mapping phức tạp, cần kiểm thử tên BSON thực sự được gửi xuống server.

## 11. Array projection không đồng nghĩa lọc phần tử

Document khác có một mảng variants:

~~~javascript
{
  sku: "KIT-001",
  variants: [
    { color: "RED", stock: NumberInt(0) },
    { color: "BLUE", stock: NumberInt(5) }
  ]
}
~~~

Projection:

~~~javascript
db.products.find(
  { sku: "KIT-001" },
  { "variants.color": 1, _id: 0 }
);
~~~

MongoDB có thể trả **cả hai phần tử** variants, nhưng mỗi phần tử chỉ giữ color. Việc chọn field trên array **không có nghĩa** lọc các phần tử theo stock hoặc color.

Ngay cả truy vấn:

~~~javascript
db.products.find(
  { "variants.stock": { $gt: 0 } },
  { "variants.color": 1, _id: 0 }
);
~~~

cũng chỉ chọn **document có ít nhất một variant còn hàng**. Phép projection trên đường dẫn variants.color không tự thu nhỏ mảng thành những variant còn hàng.

MongoDB có toán tử projection **$elemMatch** để trả một phần tử mảng phù hợp điều kiện. Khi cần lọc nhiều phần tử hoặc biến đổi mảng phức tạp, aggregation với **$filter** và **$project** thường dễ kiểm soát hơn.

### 11.1. $slice có quy tắc kết hợp riêng

~~~javascript
db.products.find(
  { active: true },
  { tags: { $slice: 2 } }
);
~~~

$slice trong projection có thể giới hạn tags còn hai phần tử đầu, nhưng không thay đổi mảng đã lưu. **Trong các phiên bản MongoDB từ 4.4, $slice được xem là exclusion projection** đối với quy tắc phối hợp include/exclude, nên không nên tự ghép nó với name: 1 rồi giả định hợp lệ. Với các kết quả cần biến đổi phức tạp, sử dụng aggregation và kiểm thử trên phiên bản server thực tế.

## 12. Find projection so với aggregation $project

Find projection đơn giản:

~~~javascript
db.products.find(
  { active: true },
  { sku: 1, name: 1, priceMinor: 1, _id: 0 }
);
~~~

Aggregation $project có thể đổi tên hoặc tính toán field:

~~~javascript
db.products.aggregate([
  { $match: { active: true } },
  {
    $project: {
      _id: 0,
      sku: 1,
      displayName: "$name",
      priceMinor: 1
    }
  }
]);
~~~

Ở đây displayName được tạo từ name. Đây là **biến đổi kết quả**, không chỉ chọn field cũ. Một pipeline còn có thể chứa $group, $lookup, $filter và nhiều stage khác.

Vì vậy, khi cần tính toán phức tạp, ghép dữ liệu, lọc array hoặc định hình báo cáo, **@Aggregation** hay **MongoTemplate.aggregate** thường phù hợp hơn @Query(fields). Đừng đưa mọi biểu thức aggregation vào một find projection mà không xét quy tắc riêng của từng loại truy vấn.

## 13. Projection và hiệu năng

Projection thường giúp:

- Giảm số byte BSON truyền từ server đến client.
- Giảm khối lượng chuyển đổi BSON thành object Java.
- Tránh tải những trường lớn không dùng đến.
- Làm rõ những field API cần, qua đó giảm nguy cơ chuyển tiếp dữ liệu dư thừa.

Nhưng **trả ít field không đồng nghĩa MongoDB luôn đọc ít dữ liệu từ đĩa hơn**. Nếu server phải fetch document gốc để lấy một field, projection vẫn có thể giảm dữ liệu truyền đi nhưng không nhất thiết tránh việc truy cập document.

### 13.1. Covered query

Giả sử workload thường lọc active và chỉ trả sku, name, priceMinor. Ta có thể đánh giá một index như:

~~~javascript
db.products.createIndex({
  active: 1,
  sku: 1,
  name: 1,
  priceMinor: 1
});
~~~

Truy vấn:

~~~javascript
db.products.find(
  { active: true },
  { sku: 1, name: 1, priceMinor: 1, _id: 0 }
).explain("executionStats");
~~~

Vì filter và projection chỉ cần những field có trong index, query **có thể** được xử lý như một **covered query** (chỉ dùng index mà không cần fetch document), tùy đặc điểm index và kế hoạch thực thi.

### 13.2. Ngoại lệ _id ảnh hưởng covered query

Index ví dụ không có _id. Nếu projection chỉ là:

~~~javascript
{ sku: 1, name: 1, priceMinor: 1 }
~~~

MongoDB vẫn phải trả _id theo mặc định, và index vừa nêu có thể không đủ để cung cấp _id. Khi API thực sự không cần ID, thêm **_id: 0** có thể giúp truy vấn đủ điều kiện được index bao phủ.

Không nên mặc định loại _id ở mọi nơi: nếu client cần định danh, phải giữ ID và xem xét index phù hợp hoặc chấp nhận FETCH sau khi đo. Index chứa quá nhiều field cũng tăng chi phí lưu trữ và cập nhật.

### 13.3. Chỉ số cần quan sát

| Chỉ số / thành phần | Cần hiểu gì? |
| --- | --- |
| winningPlan | Query planner chọn kế hoạch nào? |
| totalKeysExamined | Số index key đã đọc |
| totalDocsExamined | Số document gốc phải duyệt |
| nReturned | Số document trả sau lọc |
| FETCH stage | Có cần lấy document gốc không? |
| executionTimeMillis | Thời gian quan sát tại thời điểm test |

Với covered query đúng nghĩa, totalDocsExamined có thể bằng 0. Không nên khẳng định index luôn giúp chỉ dựa vào một test nhỏ; cần đo với dữ liệu, sort, filter và workload thực tế.

### 13.4. Projection không thay thế pagination

Trả 100.000 document, dù mỗi document chỉ gồm name, vẫn có thể tạo tải mạng và chi phí xử lý lớn. Nên kết hợp projection với giới hạn số bản ghi, Sort/Pageable hoặc chiến lược phân trang theo khóa theo nhu cầu.

## 14. Dùng Sort và Pageable với projection

Một repository có thể khai báo:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

@Query(
    value = "{ 'active': true }",
    fields = "{ 'sku': 1, 'name': 1, 'priceMinor': 1 }"
)
Page<ProductCardView> findActiveCards(Pageable pageable);
~~~

Sử dụng:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

PageRequest request = PageRequest.of(
    0,
    20,
    Sort.by(Sort.Order.desc("createdAt"), Sort.Order.desc("id"))
);

Page<ProductCardView> page =
    repository.findActiveCards(request);
~~~

Field dùng để sort không nhất thiết phải được trả ra trong projection. Tuy nhiên, nếu dùng keyset cursor theo field sort, cần thiết kế cách lấy các khóa cursor tương ứng. Page có thể thực hiện count query để tính tổng số phần tử; nếu không cần tổng số, Slice có thể phù hợp hơn. Sort trên field không có index vẫn có thể tốn nhiều tài nguyên.

## 15. Projection không phải biện pháp bảo mật duy nhất

Đối với API công khai, **inclusion whitelist** là bước quan trọng:

~~~java
@Query(
    value = "{ 'active': true }",
    fields = "{ '_id': 1, 'sku': 1, 'name': 1, 'priceMinor': 1 }"
)
List<ProductCardView> findPublicCards();
~~~

Các trường supplier.internalNote và privateCost mới bổ sung sẽ không tự xuất hiện khi chỉ include các field đã được duyệt. DTO công khai tiếp tục quy định kiểu và tên của dữ liệu được serialize.

Tuy nhiên, không thể dựa vào projection rồi kết luận ứng dụng đã có phân quyền. Một method MongoTemplate khác có thể đọc nhiều field hơn; user MongoDB có thể có quyền truy cập toàn collection; các tenant khác có thể bị đọc nếu filter thiếu **tenantId**.

Phải kiểm tra riêng:

1. Caller có quyền xem document thuộc tenant và phạm vi dữ liệu đó không?
2. Projection có chỉ lấy những field được phép công bố không?
3. DTO/serializer có thể làm lộ các field mới ngoài dự kiến không?
4. Có đường repository, MongoTemplate hay aggregation khác bỏ qua policy không?

### 15.1. Không save lại entity chỉ được tải một phần

Nếu repository trả ProductDocument nhưng fields chỉ tải name và sku, các field còn lại có thể thành null, giá trị primitive mặc định hoặc gây lỗi materialization với constructor bất biến.

**Không gọi repository.save() với một entity partial như thể nó là bản ghi đầy đủ.** Một thao tác replace có thể xóa những field không được tải. Nếu chỉ cần cập nhật name, hãy dùng thao tác update theo field có điều kiện, hoặc lấy entity đầy đủ trước khi áp dụng thay đổi theo chính sách concurrency của hệ thống.

## 16. Kiểm thử projection trên BSON thực

Một test chỉ gọi getName() trên interface chưa đủ để chứng minh MongoDB không trả trường nội bộ. Nên kiểm tra kết quả **Document BSON thô** và đối chiếu với kiểu projection/DTO ở service.

Ví dụ với MongoTemplate trong JUnit 5 và MongoDB test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.bson.Document;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class ProductProjectionTest {

    @Autowired
    MongoTemplate template;

    @Test
    void inclusionExcludesIdAndInternalData() {
        String sku = "TEST-" + UUID.randomUUID();
        ProductDocument inserted = template.insert(new ProductDocument(
            null,
            sku,
            "Projection test",
            159_000L,
            true,
            "Tài liệu dài",
            List.of("JAVA"),
            new ProductDocument.Supplier("SUP-T", "Private"),
            Instant.parse("2025-06-01T09:00:00Z")
        ));

        try {
            Query query = Query.query(Criteria.where("sku").is(sku));
            query.fields()
                .include("sku")
                .include("name")
                .include("priceMinor")
                .exclude("_id");

            List<Document> results =
                template.find(query, Document.class, "products");

            assertThat(results).hasSize(1);
            Document raw = results.get(0);
            assertThat(raw.containsKey("_id")).isFalse();
            assertThat(raw.containsKey("sku")).isTrue();
            assertThat(raw.containsKey("name")).isTrue();
            assertThat(raw.containsKey("priceMinor")).isTrue();
            assertThat(raw.containsKey("description")).isFalse();
            assertThat(raw.containsKey("supplier")).isFalse();
        } finally {
            template.remove(
                Query.query(Criteria.where("_id").is(inserted.id())),
                ProductDocument.class
            );
        }
    }
}
~~~

Test chỉ chạy với **database dành riêng cho test**, không chạy trên production. Sử dụng SKU ngẫu nhiên giúp tránh trùng bản ghi đã có. Ví dụ dùng Document.class để xác nhận chính xác các field được server trả, không phụ thuộc khả năng materialize một entity partial.

### 16.1. Ma trận test ngoại lệ _id

| Projection | Kỳ vọng |
| --- | --- |
| { name: 1 } | Có name và _id |
| { name: 1, _id: 0 } | Có name, không có _id |
| { description: 0 } | Không có description, vẫn có _id |
| { description: 0, _id: 0 } | Không có description và _id |
| { name: 1, description: 0 } | Bị từ chối theo quy tắc projection cơ bản |
| { "supplier.code": 1, _id: 0 } | Có supplier.code, không có internalNote |
| { name: 1, priceMinor: 1, _id: 0 } | Có hai field yêu cầu, không có ID |

Nếu project có @Field và custom converters, thêm fixture đọc BSON thô để phát hiện tên field không khớp. Với method @Query(fields), kiểm thử cả giá trị view và khả năng DTO được tạo đúng.

## 17. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Chỉ chọn name nhưng kết quả còn _id | _id được include mặc định | Thêm _id: 0 nếu không cần ID |
| Server báo projection không hợp lệ | Trộn include và exclude ngoài _id | Chọn một chế độ projection |
| getId không có giá trị | Truy vấn đã loại _id | Giữ _id hoặc sửa hợp đồng view/DTO |
| API lộ field được thêm gần đây | Dùng exclusion thay vì inclusion | Chọn whitelist field và DTO công khai |
| Supplier trả quá nhiều dữ liệu | Include cả supplier | Chỉ include supplier.code |
| Mảng không được lọc theo phần tử | Chọn đường dẫn field chỉ thay đổi hình dạng | Dùng $elemMatch hoặc aggregation $filter |
| DTO nhận null/default không mong muốn | Thiếu field cần cho constructor/primitive | Chọn đúng field, dùng DTO phù hợp |
| Save làm mất field khác | Save entity vừa đọc partial | Dùng update có điều kiện hoặc tải đầy đủ |
| Projection ít trường nhưng query vẫn chậm | Filter/index/sort chưa phù hợp hoặc FETCH | Đo explain("executionStats") |
| Query không được index bao phủ | _id mặc định hoặc field ngoài index | Xem projection và thiết kế index |
| Tên field sai | Nhầm property Java và field BSON @Field | Kiểm tra mapping và raw BSON |
| Lọc đúng field nhưng sai tenant | Projection không bảo vệ quyền | Bổ sung policy/filter tenant đã xác thực |

Quy trình điều tra:

1. Xác nhận database, collection và document BSON thực tế.
2. Xác định filter và projection tách biệt.
3. Kiểm tra projection đang ở inclusion hay exclusion mode.
4. Xem _id có được include mặc định hay đã bị loại.
5. Đối chiếu các đường dẫn embedded/array và @Field mapping.
6. Kiểm tra shape của view/DTO có đúng field đã chọn không.
7. Với query chậm, xem index và explain thay vì chỉ nhìn kích thước response.
8. Thêm test hồi quy cho cách chọn/loại field, đặc biệt field nhạy cảm.

## 18. Bài tập thực hành

### Bài tập 1: _id có xuất hiện?

~~~javascript
db.products.find({}, { name: 1, priceMinor: 1 });
~~~

**Câu hỏi:** kết quả có _id không?

**Đáp án:** Có. MongoDB include _id mặc định trong inclusion projection. Nếu không cần định danh, thêm **_id: 0**.

### Bài tập 2: sửa một projection không hợp lệ

~~~javascript
{ name: 1, priceMinor: 1, description: 0 }
~~~

**Câu hỏi:** vì sao sai và sửa thế nào nếu chỉ cần name, priceMinor?

**Đáp án:** trộn inclusion với exclusion cho field thường. Sửa thành **{ name: 1, priceMinor: 1, _id: 0 }** nếu không cần ID, hoặc bỏ _id: 0 nếu vẫn cần ID.

### Bài tập 3: chọn hay loại?

API công khai có field sku, name, priceMinor. Collection bổ sung một field privateCost. Nên dùng inclusion hay exclusion?

**Đáp án:** inclusion whitelist. Nó không tự trả privateCost khi thêm field mới. Exclusion chỉ loại những field đã biết và được liệt kê.

### Bài tập 4: @Query(fields)

Viết method tìm sản phẩm active, trả sku/name/priceMinor và không có _id.

~~~java
@Query(
    value = "{ 'active': true }",
    fields = "{ 'sku': 1, 'name': 1, 'priceMinor': 1, '_id': 0 }"
)
List<ProductExportView> findForExport();
~~~

### Bài tập 5: array

Document có variants là mảng object. Nếu projection chỉ chọn **variants.color**, có chắc chỉ trả các variant màu đỏ không?

**Đáp án:** Không. Projection đường dẫn field không phải filter phần tử. Dùng phép lọc mảng phù hợp nếu cần trả những phần tử thỏa điều kiện.

### Bài tập 6: covered query

Index chỉ có active, sku, name, priceMinor. Query lọc active và include ba field còn lại nhưng không ghi _id: 0. Điều gì có thể cản trở covered query?

**Đáp án:** _id được MongoDB trả mặc định, trong khi index không chứa _id. Thêm _id: 0 khi không cần ID, rồi đo explain để xác nhận có thể tránh FETCH.

### Bài tập 7: entity partial

Một repository đọc ProductDocument chỉ gồm sku và name, rồi service sửa name và gọi save. Rủi ro gì?

**Đáp án:** các field chưa tải có thể null/default và bị xóa khi ghi thay thế. Không save entity partial; dùng DTO projection và thao tác update có điều kiện theo field cần sửa.

### Bài tập 8: DTO công khai

Thiết kế endpoint trả ID, sku, name, priceMinor nhưng không bao giờ trả supplier hoặc description.

**Gợi ý:** dùng inclusion **_id, sku, name, priceMinor**, trả ProductCardView rồi map sang ProductCardDto. Kiểm thử BSON raw không chứa supplier/description và kiểm tra chính sách phân quyền, tenant độc lập với projection.

## 19. Nguyên tắc cần nhớ

1. **Projection find dùng 1 để chọn và 0 để loại** field theo quy tắc cơ bản.
2. **Không trộn inclusion và exclusion trên field thường**; ngoại lệ là **_id**.
3. **_id được trả về mặc định**, kể cả khi chỉ chọn vài field; thêm **_id: 0** để loại.
4. **@Query(fields = ...)** và **MongoTemplate Query.fields()** đều áp dụng cùng nguyên tắc projection.
5. **DTO/view phải phản ánh đúng các field được tải**; không dùng entity partial để save.
6. **Chọn field của subdocument không phải lọc phần tử array**, và aggregation phù hợp với biến đổi phức tạp.
7. **Với public API, ưu tiên inclusion whitelist** để không vô tình lộ field mới.
8. **Projection giảm dữ liệu truyền và mapping**, nhưng có tránh FETCH hay không phụ thuộc index; _id mặc định có thể ảnh hưởng covered query.
9. **Kiểm thử BSON và explain** giúp xác nhận cả hình dạng kết quả, tính an toàn và hiệu năng.

Làm chủ cách chọn hoặc loại trường cùng ngoại lệ của **_id** giúp ứng dụng **SPRING_DATA_MONGODB** trả DTO gọn, tránh lộ dữ liệu, khai thác MongoTemplate/repository đúng cách và nâng cao khả năng kiểm thử, bảo trì, tối ưu truy vấn MongoDB.

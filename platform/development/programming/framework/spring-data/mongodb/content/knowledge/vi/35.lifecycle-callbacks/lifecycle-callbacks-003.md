# BeforeSaveCallback với entity và Document đã chuyển đổi

## 1. Tình huống: cần bổ sung dữ liệu ngay trước khi ghi MongoDB

Một dịch vụ quản lý catalog lưu sản phẩm trong MongoDB bằng Spring Data MongoDB. Entity Java có trường **displayName** nhưng collection cần thêm trường BSON **search_display** đã chuẩn hóa để phục vụ chức năng tìm kiếm. Dịch vụ cũng muốn gắn **write_schema** vào document để xác định định dạng dữ liệu đang được ghi.

Yêu cầu nghe đơn giản: “Khi save sản phẩm, tự thêm hai trường này trước khi MongoDB nhận dữ liệu”. Tuy nhiên, lựa chọn callback không đúng có thể khiến kết quả trong Java khác với document thực tế đã lưu.

Trong Spring Data MongoDB, **BeforeSaveCallback** là một điểm mở rộng rất cụ thể:

- Nhận **entity Java** đã qua bước chuyển đổi.
- Nhận **org.bson.Document** đang chuẩn bị được ghi.
- Nhận **tên collection**.
- Có thể sửa **Document** để thay đổi BSON ghi xuống server.
- Trả lại entity, nhưng việc sửa field persistent của entity ở thời điểm này **không được áp dụng trở lại vào Document đã chuyển đổi**.

Vì thế:

**Muốn sửa thuộc tính persistent của entity trước chuyển đổi → BeforeConvertCallback.**

**Muốn sửa document BSON sau chuyển đổi nhưng trước khi ghi → BeforeSaveCallback.**

Đây là nguyên tắc trung tâm của bài **BeforeSaveCallback với entity và Document đã chuyển đổi**, thuộc chương **Vòng đời và callback** của module **SPRING_DATA_MONGODB**. Phạm vi module bao gồm kết nối MongoDB, ánh xạ document, repository, MongoTemplate, truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng.

### 1.1. Sau bài học, bạn sẽ làm được

1. Xác định chính xác vị trí BeforeSaveCallback trong pipeline ghi.
2. Viết callback với chữ ký **onBeforeSave(T entity, Document document, String collection)**.
3. Phân biệt field Java với tên trường BSON sau mapping như **@Field("tenant_id")**.
4. Thực hiện enrichment/masking/chỉnh sửa cấu trúc document đúng lúc.
5. Tránh lỗi “đã đổi entity nhưng dữ liệu MongoDB không đổi”.
6. Hiểu tương tác với **BeforeConvertCallback, BeforeSaveEvent, AfterSaveCallback, auditing**.
7. Biết operation nào gọi callback và operation nào bỏ qua callback.
8. Thiết kế callback an toàn với insert/save, transactions, retries và multi-tenant.
9. Triển khai **ReactiveBeforeSaveCallback** khi sử dụng ReactiveMongoTemplate.
10. Kiểm thử cả entity lẫn BSON raw sau khi ghi bằng MongoDB thật.

## 2. Hai biểu diễn của một đối tượng: entity và BSON Document

Java entity được ánh xạ thành dữ liệu BSON để gửi tới MongoDB:

~~~mermaid
flowchart LR
    A["CatalogProduct Java"] --> B["MappingMongoConverter"]
    B --> C["org.bson.Document"]
    C --> D["MongoDB Java Driver"]
    D --> E["Collection catalog_products"]
~~~

Ví dụ entity:

~~~java
package com.example.catalog;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "catalog_products")
public record CatalogProduct(
    @Id ObjectId id,
    @Field("tenant_id") String tenantId,
    String sku,
    @Field("display_name") String displayName,
    String status,
    Instant createdAt
) {}
~~~

Một entity có thể chứa:

~~~java
CatalogProduct product = new CatalogProduct(
    new ObjectId(),
    "shop-a",
    "BOOK-101",
    "  Spring Data MongoDB  ",
    "ACTIVE",
    Instant.parse("2025-06-01T09:00:00Z")
);
~~~

Sau bước chuyển đổi, BSON document có dạng:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenant_id: "shop-a",
  sku: "BOOK-101",
  display_name: "  Spring Data MongoDB  ",
  status: "ACTIVE",
  createdAt: ISODate("2025-06-01T09:00:00Z"),
  _class: "com.example.catalog.CatalogProduct"
}
~~~

Đây là BSON **minh họa**, không phải khẳng định mọi deployment luôn có **_class**. Trường type discriminator phụ thuộc cấu hình MongoTypeMapper, mapping context và các lựa chọn converter.

### 2.1. Tại sao tên field có thể khác Java?

Spring Data MongoDB có thể áp dụng:

- **@Id** để lưu ObjectId dưới key **_id**.
- **@Field** để ánh xạ **tenantId → tenant_id**.
- **@Field** để ánh xạ **displayName → display_name**.
- Converters để đổi Java types sang BSON types phù hợp.
- Mapping metadata cho nested objects, enums, numbers và type hints.

Vì vậy, trong BeforeSaveCallback, **Document chứa key đã ánh xạ**, không phải luôn chứa tên Java property. Viết **document.put("displayName",...)** sẽ dễ tạo một BSON field mới ngoài ý muốn thay vì sửa **display_name**.

### 2.2. Entity Java và Document không phải cùng một object

~~~text
Java entity:
    displayName = "  Spring Data MongoDB  "

Converted Document:
    display_name = "  Spring Data MongoDB  "
~~~

Document được tạo từ thông tin entity trong giai đoạn conversion. Khi đã tạo xong, việc đổi property entity **không tự gây chuyển đổi lần hai**.

Đây là nguồn gốc của lỗi thường gặp khi sử dụng BeforeSaveCallback.

## 3. BeforeSaveCallback đứng ở đâu trong lifecycle?

Pipeline ghi theo mapping path, giản lược:

~~~mermaid
sequenceDiagram
    participant S as Service/Repository
    participant T as MongoTemplate
    participant BC as BeforeConvertCallback
    participant C as MongoConverter
    participant BS as BeforeSaveCallback
    participant D as MongoDB Driver
    S->>T: insert hoặc save(entity)
    T->>BC: onBeforeConvert(entity, collection)
    BC-->>T: entity đã xử lý
    T->>C: convert entity thành Document
    C-->>T: Document đã ánh xạ
    T->>BS: onBeforeSave(entity, Document, collection)
    BS->>BS: Có thể sửa trực tiếp Document
    BS-->>T: Trả entity
    T->>D: Gửi Document để ghi
    D-->>T: Kết quả ghi
    T-->>S: Kết quả save/insert
~~~

Trong một hệ thống có Spring **ApplicationEvents** và EntityCallbacks, BeforeConvertEvent/BeforeSaveEvent và callback có thể cùng tồn tại. Sơ đồ tập trung vào các điểm chuyển đổi và callback, lược bỏ chi tiết sự kiện, ID generation, auditing và AfterSave.

### 3.1. Bảng thời điểm

| Điểm mở rộng | Thời điểm | Đối tượng nên sửa |
| --- | --- | --- |
| BeforeConvertCallback | Trước MappingMongoConverter | Entity Java |
| BeforeSaveCallback | Sau convert, trước lệnh insert/save | **Document BSON** |
| AfterSaveCallback | Sau khi MongoDB ghi thành công | Entity trả về / side effect phù hợp |
| AfterConvertCallback | Sau khi đọc và chuyển Document thành entity | Entity đã load |

**Chỉ thay đổi Document trong BeforeSaveCallback mới ảnh hưởng trực tiếp đến dữ liệu được ghi ở thời điểm đó.** Thay đổi persistent field của entity trong BeforeSaveCallback là quá muộn cho conversion.

### 3.2. “BeforeSave” không phải “BeforeConvert”

Tên callback dễ khiến ta hiểu sai rằng mọi property mutation đều được save. Javadoc Spring Data MongoDB nhấn mạnh: callback được gọi **sau khi entity đã chuyển thành Document**; Document là kết quả được dùng để ghi, còn thay đổi persistent entity trong callback không được xét lại.

### 3.3. Thời điểm callback trong transaction

Nếu lệnh save nằm trong MongoDB transaction, callback thực thi khi xử lý lệnh ghi **trong transaction**, không phải sau commit. Một lỗi về sau vẫn có thể khiến transaction rollback; side effect bên ngoài do callback thực hiện không được rollback cùng MongoDB.

## 4. Chữ ký API chính thức

~~~java
package org.springframework.data.mongodb.core.mapping.event;

import org.bson.Document;
import org.springframework.data.mapping.callback.EntityCallback;

@FunctionalInterface
public interface BeforeSaveCallback<T> extends EntityCallback<T> {

    T onBeforeSave(T entity, Document document, String collection);
}
~~~

Đoạn trên là **chữ ký minh họa của interface framework**, không phải code để định nghĩa lại interface trong project. Ứng dụng import interface do Spring Data MongoDB cung cấp.

Ba tham số:

| Tham số | Ý nghĩa | Gợi ý sử dụng |
| --- | --- | --- |
| entity | Domain object ở thời điểm save | Đọc thông tin nghiệp vụ, kiểm tra thông tin đầu vào |
| document | **org.bson.Document** đã được chuyển đổi | Chỉnh sửa field BSON sẽ ghi |
| collection | Tên collection đích | Kiểm soát phạm vi nếu callback có nhiều trường hợp |

Giá trị trả về là **T**, có thể là cùng entity hoặc một instance khác. Nhưng **đổi persistent field trong T không khiến MongoConverter chuyển đổi lại Document**. Vì vậy, ở callback này chỉ nên thay entity đối với các thuộc tính transient hoặc trường hợp có hợp đồng rõ ràng về object trả về.

### 4.1. Đừng nhầm các kiểu Document

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.mapping.Document;
~~~

Hai type trên **khác nhau**:

- **org.bson.Document** là lớp dữ liệu BSON Java Driver.
- **org.springframework.data.mongodb.core.mapping.Document** là annotation gắn trên entity.

Nếu một Java file cần cả hai, nên import org.bson.Document và dùng annotation fully qualified cho entity, hoặc đặt chúng ở hai file riêng. Java không thể import hai type cùng simple name mà không có phân biệt.

### 4.2. Registration

Một bean Spring thực thi BeforeSaveCallback và có generic type phù hợp được callback infrastructure nhận diện:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.data.mongodb.core.mapping.event.BeforeSaveCallback;
import org.bson.Document;

@Component
public class CatalogProductBeforeSave
        implements BeforeSaveCallback<CatalogProduct> {

    @Override
    public CatalogProduct onBeforeSave(
            CatalogProduct entity,
            Document document,
            String collection) {

        return entity;
    }
}
~~~

Không cần tự gọi **onBeforeSave** từ mỗi service. Dùng callback ở Spring ApplicationContext và để MongoTemplate/repository mapping lifecycle gọi ở điểm phù hợp.

## 5. Ví dụ chính: thêm search_display và write_schema vào Document

Yêu cầu:

1. Trường **display_name** giữ nguyên giá trị người dùng nhập, phục vụ UI.
2. Trường **search_display** chứa một bản normalized để phục vụ tìm kiếm.
3. Trường **write_schema** có giá trị số nguyên biểu thị version cấu trúc.
4. Hai field bổ sung **không cần tồn tại trong CatalogProduct entity**.

Ví dụ callback:

~~~java
package com.example.catalog;

import java.text.Normalizer;
import java.util.Locale;
import org.bson.Document;
import org.springframework.stereotype.Component;
import org.springframework.data.mongodb.core.mapping.event.BeforeSaveCallback;

@Component
public class CatalogProductBeforeSave
        implements BeforeSaveCallback<CatalogProduct> {

    @Override
    public CatalogProduct onBeforeSave(
            CatalogProduct entity,
            Document document,
            String collection) {

        if (!"catalog_products".equals(collection)) {
            return entity;
        }

        String displayName = document.getString("display_name");

        if (displayName == null) {
            document.remove("search_display");
        } else {
            String normalized = Normalizer.normalize(
                displayName, Normalizer.Form.NFKC)
                .trim()
                .toLowerCase(Locale.ROOT);

            document.put("search_display", normalized);
        }

        document.put("write_schema", 1);

        return entity;
    }
}
~~~

**Điểm quyết định**:

~~~java
document.put("search_display", normalized);
document.put("write_schema", 1);
~~~

Đây là các thay đổi trên **Document đã convert**, vì thế chúng được dùng trong lệnh ghi cuối cùng.

### 5.1. Vì sao đọc document.getString("display_name") thay vì entity.displayName()?

Nếu mục tiêu là tạo trường derived từ **giá trị BSON sắp được lưu**, đọc Document giúp quan sát dữ liệu đã qua mapping/converter. Trong bài, displayName là String nên cả hai có thể giống nhau. Khi có custom converter hoặc alias field, Document phản ánh dạng lưu trữ thực tế.

Không dùng getString cho field không chắc là String BSON; với BSON Date, nested Document hoặc Decimal128, cần đọc theo kiểu tương ứng.

### 5.2. Không tự động bỏ dấu tiếng Việt

Normalizer.NFKC và lower-case trong ví dụ **không loại bỏ toàn bộ dấu tiếng Việt**; ví dụ tên **Sách** vẫn mang dấu. Nếu ứng dụng cần tìm kiếm accent-insensitive hoặc fuzzy, phải thiết kế normalization/collation/search engine theo mục tiêu nghiệp vụ và kiểm thử ngôn ngữ.

### 5.3. Schema version không phải mã migration tự động

**write_schema=1** là metadata lưu kèm document. Việc đặt version không tự migrate các document đã tồn tại, không tự tạo index và không buộc code mới đọc được mọi phiên bản cũ. Cần xử lý version đọc, migration/backfill và chiến lược tương thích riêng.

### 5.4. Index cho trường bổ sung

Nếu service cần truy vấn theo **search_display**, có thể cần index:

~~~javascript
db.catalog_products.createIndex(
  { tenant_id: 1, search_display: 1 },
  { name: "idx_catalog_tenant_search_display" }
);
~~~

Trường **search_display** không khai báo trong Java entity nhưng vẫn có thể được index trên MongoDB. Cần migration index và query/criteria dùng đúng BSON field. Không thêm index trên mọi field tự động chỉ vì callback tạo ra nó.

## 6. Kết quả sau insert: hai biểu diễn có thể khác nhau

Service gọi:

~~~java
CatalogProduct product = new CatalogProduct(
    new ObjectId(),
    "shop-a",
    "BOOK-101",
    "  Spring Data MongoDB  ",
    "ACTIVE",
    Instant.parse("2025-06-01T09:00:00Z")
);

mongoTemplate.insert(product);
~~~

Document được ghi có thể chứa:

~~~javascript
{
  _id: ObjectId("..."),
  tenant_id: "shop-a",
  sku: "BOOK-101",
  display_name: "  Spring Data MongoDB  ",
  search_display: "spring data mongodb",
  write_schema: 1,
  status: "ACTIVE",
  createdAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

**Đừng kỳ vọng CatalogProduct entity sau insert tự có property search_display/write_schema**, bởi hai property này không tồn tại trong Java type. Chúng thuộc persisted BSON document. Spring Data mặc định ánh xạ những field có metadata tương ứng; các field raw bổ sung có thể bị bỏ qua khi đọc lại thành CatalogProduct.

### 6.1. Document sau mapping không phải source of truth của entity Java

Một entity có thể đã được convert ra Document, sửa bởi callback, ghi thành công rồi trả về từ save. Đối tượng entity trả về không bắt buộc phản ánh mọi thay đổi raw Document nếu chưa có bước đọc lại và mapping thích hợp.

### 6.2. Nếu API cần trả search_display

Nên định nghĩa:

- DTO response tự tính normalized string theo cùng quy tắc.
- DTO projection đọc trường BSON nếu trường được mapping.
- Hoặc một lời gọi query đọc lại BSON khi thật sự cần.

**Không dựa vào tác dụng phụ của BeforeSaveCallback để đồng bộ mọi trạng thái Java trong bộ nhớ.**

## 7. Sai lầm kinh điển: chỉ sửa entity trong BeforeSaveCallback

Giả sử sử dụng một class mutable:

~~~java
public class MutableCatalogProduct {

    private String displayName;

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String value) {
        this.displayName = value;
    }
}
~~~

Callback **không đúng** nếu muốn thay đổi BSON của displayName:

~~~java
@Component
public class WrongBeforeSave
        implements BeforeSaveCallback<MutableCatalogProduct> {

    @Override
    public MutableCatalogProduct onBeforeSave(
            MutableCatalogProduct entity,
            Document document,
            String collection) {

        entity.setDisplayName(
            entity.getDisplayName().trim());

        return entity;
    }
}
~~~

Ở thời điểm này, converter đã tạo Document từ displayName cũ. Setter có thể thay đổi Java object đang được giữ trong bộ nhớ, nhưng **không thay đổi nội dung của Document đã được dùng để ghi**.

### 7.1. Hệ quả dễ gây khó hiểu

~~~text
Trước callback:
  entity.displayName = "  Name  "
  document.displayName = "  Name  "

Sau callback chỉ gọi entity.setDisplayName("Name"):
  entity.displayName = "Name"
  document.displayName = "  Name  "

MongoDB nhận:
  document.displayName = "  Name  "
~~~

Màn hình ứng dụng có thể đang giữ object Java đã trim nên tưởng dữ liệu được lưu sạch, nhưng lần đọc lại từ MongoDB mới phát hiện các khoảng trắng vẫn còn.

### 7.2. Nếu cần sửa một persistent field trước mapping

Chọn **BeforeConvertCallback**:

~~~java
import java.util.Locale;
import org.springframework.stereotype.Component;
import org.springframework.data.mongodb.core.mapping.event.BeforeConvertCallback;

@Component
public class CatalogSkuBeforeConvert
        implements BeforeConvertCallback<CatalogProduct> {

    @Override
    public CatalogProduct onBeforeConvert(
            CatalogProduct entity, String collection) {

        if (!"catalog_products".equals(collection)) {
            return entity;
        }

        if (entity.sku() == null
                || entity.sku().isBlank()) {
            throw new IllegalArgumentException(
                "SKU is required");
        }

        String normalizedSku =
            entity.sku().trim().toUpperCase(Locale.ROOT);

        return new CatalogProduct(
            entity.id(),
            entity.tenantId(),
            normalizedSku,
            entity.displayName(),
            entity.status(),
            entity.createdAt()
        );
    }
}
~~~

Đây là **record immutable**, nên callback tạo instance mới thay vì sửa setter. Vì nó chạy **trước MongoConverter**, Document được tạo từ SKU đã chuẩn hóa.

### 7.3. Nếu cố ý sửa Document để thay cùng field

Trường hợp đã có BSON, có thể:

~~~java
String raw = document.getString("display_name");
if (raw != null) {
    document.put("display_name", raw.trim());
}
~~~

Khi đó **BSON được trim**, nhưng **CatalogProduct entity vẫn có displayName cũ**. Nếu ứng dụng muốn Java object và MongoDB nhất quán, ưu tiên normalize entity ở BeforeConvertCallback hoặc xử lý trước khi gọi save.

### 7.4. Quy tắc chọn callback

| Mục tiêu | Nên chọn |
| --- | --- |
| Trim SKU và entity sau save cũng có SKU mới | BeforeConvertCallback |
| Sinh giá trị cần converter ánh xạ vào BSON | BeforeConvertCallback |
| Bổ sung trường chỉ tồn tại trong BSON | BeforeSaveCallback |
| Xóa/ẩn field BSON theo policy sau mapping | BeforeSaveCallback, nhưng phải kiểm soát đọc/ghi |
| Chỉ làm sạch DTO trước HTTP response | Mapping ở service/DTO, không phải save callback |
| Ghi log thành công sau thao tác | AfterSaveCallback hoặc infrastructure phù hợp |

## 8. Tương tác với @Field và nested BSON

Khi entity có:

~~~java
@Field("tenant_id")
String tenantId;

@Field("display_name")
String displayName;
~~~

callback phải dùng **tenant_id** và **display_name** nếu muốn sửa đúng hai key:

~~~java
String tenant = document.getString("tenant_id");
String name = document.getString("display_name");
~~~

Nếu dùng document.put("tenantId", ...), MongoDB có thể chứa **cả tenant_id và tenantId**:

~~~javascript
{
  tenant_id: "shop-a",
  tenantId: "shop-a"
}
~~~

Đây là dữ liệu không đúng schema, không phải việc converter tự sửa tên field hai lần.

### 8.1. Nested Document

Giả sử entity ánh xạ:

~~~javascript
{
  tenant_id: "shop-a",
  supplier: {
    code: " SUP-01 ",
    country: "VN"
  }
}
~~~

Nếu nested BSON là **org.bson.Document**:

~~~java
Document supplier = document.get(
    "supplier", Document.class);

if (supplier != null) {
    String code = supplier.getString("code");

    if (code != null) {
        supplier.put("code", code.trim());
    }
}
~~~

Đây là thao tác trên **nested Document đã được convert**. Nếu custom converter lưu supplier thành String hoặc một BSON type khác, cast trên có thể không hợp lệ. Luôn xác minh hình dạng dữ liệu thực trước khi sửa.

### 8.2. Array chứa Documents

~~~java
Object rawLines = document.get("lines");

if (rawLines instanceof java.util.List<?> lines) {
    for (Object rawLine : lines) {
        if (rawLine instanceof Document line) {
            String label = line.getString("label");
            if (label != null) {
                line.put("label", label.trim());
            }
        }
    }
}
~~~

Đừng mặc định một array luôn chứa Document: nó có thể chứa scalar values, DBRefs, một cấu trúc khác do converter tạo hoặc null.

### 8.3. Field names động

Khi sửa field tên động trong Document, cần lưu ý MongoDB có những quy tắc dành cho tên chứa dấu **.**, dấu **$**, đường dẫn lồng nhau và một số operators. **Document.put("a.b", value)** tạo key literal trong Map, không đồng nghĩa cập nhật nested path **a → b**.

Khi cần nested field, thao tác trên Document con đã được đọc hoặc dùng cơ chế update phù hợp, không tự suy diễn đường dẫn.

## 9. Cần lưu ý gì với @Id, _id và _class?

MongoDB sử dụng trường **_id** để định danh document, còn Spring Data thường ánh xạ Java property có **@Id** sang trường này.

~~~java
@Id
ObjectId id;
~~~

Trường BSON tương ứng:

~~~javascript
{ _id: ObjectId("507f1f77bcf86cd799439011") }
~~~

Trong **BeforeSaveCallback**, không nên tùy tiện thay đổi **_id**:

~~~java
// Không nên:
document.put("_id", new ObjectId());
~~~

Điều này có thể làm entity Java đang giữ ID khác với document được ghi, gây sai liên kết và xung đột khi thao tác save/update sau đó. Với collection đã có document, **_id** là trường định danh bất biến của document.

### 9.1. Sinh ID ở đâu?

Nếu cần sinh ID nghiệp vụ, nên quyết định trước khi convert, chẳng hạn trong service hoặc **BeforeConvertCallback**, phù hợp với cơ chế ID generation của Spring Data và mapping hiện hành.

Không dùng BeforeSaveCallback để đổi ID của document đã được converter xác định mà không có một hợp đồng rõ ràng về object trả về, save mode và idempotency.

### 9.2. Không xóa _class theo cảm tính

Spring Data MongoDB có thể lưu type hint như:

~~~javascript
{ _class: "com.example.catalog.CatalogProduct" }
~~~

Xóa hoặc sửa **_class** trong callback mà chưa hiểu **DefaultMongoTypeMapper** có thể làm mất thông tin kiểu khi đọc polymorphic data. Nếu muốn thay đổi chính sách type hints, cấu hình converter/type mapper ở đúng tầng thay vì sửa ngầm từng document.

### 9.3. Không tự can thiệp @Version

Nếu entity dùng optimistic locking:

~~~java
@Version
Long version;
~~~

Spring Data có quy tắc riêng về giá trị version, điều kiện update và callback. Không sửa thẳng **version** trong Document như một bộ đếm tùy ý, vì có thể khiến optimistic-lock check không đồng nhất với dữ liệu persist.

## 10. Tương tác với auditing

Spring Data MongoDB hỗ trợ auditing qua những annotation như:

~~~java
@CreatedDate
private Instant createdAt;

@LastModifiedDate
private Instant modifiedAt;
~~~

Khi auditing được bật, **AuditingEntityCallback** hoạt động ở giai đoạn **BeforeConvertCallback** với order đã định nghĩa (thường 100 trong tài liệu Spring Data), tức là thông tin auditing được đi qua converter trước giai đoạn BeforeSave.

### 10.1. Ví dụ đường đi auditing

~~~mermaid
flowchart TD
    A["Entity mới"] --> B["Auditing BeforeConvertCallback"]
    B --> C["createdAt/modifiedAt trên entity"]
    C --> D["MongoConverter"]
    D --> E["Document có các trường ngày BSON"]
    E --> F["Custom BeforeSaveCallback"]
    F --> G["MongoDB insert/save"]
~~~

Điều này khác việc một callback BeforeSave chỉ gọi setter trên entity.modifiedAt. Setter chạy **sau conversion**, nên có thể thay entity trong memory mà không thay field persisted.

### 10.2. Nếu muốn điều chỉnh ngày từ server?

Spring Data mapping callbacks và các update operators như **$currentDate** là hai cơ chế khác nhau. Đối với full insert/save, auditing callback có thể phù hợp; đối với query-based update, cần xác định cách cập nhật timestamp riêng.

Không giả định auditing callback chạy cho mọi **updateFirst/findAndModify/bulk update** giống entity save.

### 10.3. Ưu tiên cơ chế sẵn có

Đừng tự viết một BeforeSaveCallback chỉ để mô phỏng @CreatedDate/@LastModifiedDate nếu auditing đã giải quyết đúng nhu cầu. Chỉ dùng callback bổ sung cho những quy tắc BSON thật sự đặc thù.

## 11. BeforeSaveCallback khác BeforeSaveEvent như thế nào?

Spring Data MongoDB còn có hệ thống **lifecycle ApplicationEvents**, chẳng hạn:

~~~java
import org.springframework.data.mongodb.core.mapping.event.AbstractMongoEventListener;
import org.springframework.data.mongodb.core.mapping.event.BeforeSaveEvent;

public class ProductBeforeSaveListener
        extends AbstractMongoEventListener<CatalogProduct> {

    @Override
    public void onBeforeSave(
            BeforeSaveEvent<CatalogProduct> event) {
        // Có thể truy cập event.getSource()
        // và event.getDocument() theo API framework.
    }
}
~~~

Đây là một ví dụ riêng cho **event listener**, không phải implementation của BeforeSaveCallback. Hai cơ chế có điểm tương đồng về lifecycle nhưng khác về cách tích hợp.

| Tiêu chí | BeforeSaveCallback | BeforeSaveEvent listener |
| --- | --- | --- |
| Cơ chế | Spring Data EntityCallback | Spring ApplicationEvent |
| Chữ ký | onBeforeSave(entity, Document, collection) | onBeforeSave(BeforeSaveEvent<T>) |
| Return | Trả entity T | Listener thường void |
| Thứ tự | Callback chain xác định bằng ordering | Phụ thuộc event multicaster/listener setup |
| Mutation có thứ tự đáng tin | Phù hợp hơn cho dữ liệu trước ghi | Có nguy cơ bất đồng bộ nếu multicaster được cấu hình async |
| Reactive counterpart | ReactiveBeforeSaveCallback | Không thay bằng event sync rồi mặc định non-blocking |

### 11.1. Vì sao EntityCallbacks được khuyến nghị cho thay đổi entity?

EntityCallbacks được Spring Data xây dựng để xử lý các checkpoint với thứ tự rõ trong chuỗi xử lý, bao gồm API imperative và reactive. Các event listeners đi qua **ApplicationEventMulticaster**, có thể được cấu hình executor bất đồng bộ và mất đảm bảo thời điểm mutation hoàn tất trước ghi.

Vì vậy, nếu bắt buộc sửa BSON trước khi gửi tới driver, **BeforeSaveCallback** là lựa chọn tự nhiên hơn event listener mà hoạt động phụ thuộc vào scheduling của multicaster.

### 11.2. Khi cả hai tồn tại

Theo tài liệu Spring Data, lifecycle store-specific ApplicationEvents vẫn được phát ở các điểm tương ứng; chúng được phát **trước** EntityCallbacks tiềm năng được đăng ký. Khi thực hành, đừng xây quy tắc dữ liệu phụ thuộc ngầm vào việc một event listener khác sẽ sửa field theo một thứ tự chưa được bảo đảm.

### 11.3. Event cho embedded values

Các lifecycle events thông thường phát cho **root-level types**, không phải tự động cho mọi embedded object như một aggregate độc lập. Nếu muốn chỉnh sửa field nested trong cùng root BSON, xử lý đúng ở callback của root entity hoặc ở converter/schema model.

## 12. Khi có nhiều BeforeSaveCallback: thứ tự thực thi

Một ứng dụng có thể có nhiều callback cùng target **CatalogProduct**:

- Callback A thêm search_display.
- Callback B loại bỏ trường bị cấm.
- Callback C thêm metadata nguồn ghi.

Nếu cùng sửa một field, callback nào chạy sau có thể ghi đè kết quả trước đó. Spring Data EntityCallback hỗ trợ **Ordered** hoặc **@Order** để sắp thứ tự.

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.bson.Document;
import org.springframework.data.mongodb.core.mapping.event.BeforeSaveCallback;

@Component
@Order(100)
public class SearchFieldBeforeSave
        implements BeforeSaveCallback<CatalogProduct> {

    @Override
    public CatalogProduct onBeforeSave(
            CatalogProduct entity,
            Document document,
            String collection) {

        String name = document.getString("display_name");
        if (name != null) {
            document.put("search_display",
                name.trim().toLowerCase(java.util.Locale.ROOT));
        }
        return entity;
    }
}
~~~

Một callback thứ hai:

~~~java
@Component
@Order(200)
public class WriteSourceBeforeSave
        implements BeforeSaveCallback<CatalogProduct> {

    @Override
    public CatalogProduct onBeforeSave(
            CatalogProduct entity,
            Document document,
            String collection) {

        document.put("write_source", "CATALOG_SERVICE");
        return entity;
    }
}
~~~

Order nhỏ hơn thường được thực thi trước. **Hai class trên là ví dụ thay thế/độc lập với callback chính ở phần 5**; không đăng ký cả bộ mà không xem tác dụng chồng lấp.

### 12.1. Thứ tự khác phase

**@Order không đổi vị trí BeforeSave thành BeforeConvert.** Một callback BeforeSave dù chạy sớm trong nhóm của nó vẫn nhận Document đã được convert.

### 12.2. Quy tắc thiết kế khi có nhiều callback

1. Phân công rõ callback sở hữu field nào.
2. Tránh hai callback cùng sửa một key BSON trừ khi có hợp đồng ordering.
3. Giữ callback deterministic và không phụ thuộc I/O bên ngoài.
4. Đặt @Order có chủ đích, document lý do.
5. Kiểm thử toàn bộ chain bằng dữ liệu MongoDB thực.

### 12.3. Auditing order không thay đổi thứ tự toàn pipeline

AuditingEntityCallback có order trong nhóm **BeforeConvertCallback**. Một @Order(50) trên BeforeSaveCallback không khiến nó chạy trước auditing ở phase trước conversion.

## 13. Đăng ký callback bằng @Component hoặc @Bean

Spring Data tìm EntityCallback beans đã đăng ký trong **ApplicationContext** của Spring.

### 13.1. Component scanning

~~~java
@Component
public class CatalogProductBeforeSave
        implements BeforeSaveCallback<CatalogProduct> {
    // ...
}
~~~

Class phải được component scan nhận diện. Nếu package nằm ngoài vùng scan của Spring Boot application, annotation **@Component** có thể chưa đủ để bean có mặt.

### 13.2. @Bean với kiểu generic rõ ràng

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.mapping.event.BeforeSaveCallback;

@Configuration
class CatalogCallbackConfiguration {

    @Bean
    BeforeSaveCallback<CatalogProduct> productBeforeSaveCallback() {
        return (entity, document, collection) -> {
            document.put("write_schema", 1);
            return entity;
        };
    }
}
~~~

Đây là cách đăng ký thay thế cho @Component, không dùng song song với một callback khác có cùng trách nhiệm trừ khi cố ý.

### 13.3. Khuyến nghị class concrete

Spring Data phân loại callback theo generic target type. Khi dùng lambda hoặc type erased quá tổng quát, runtime có thể không xác định domain type hiệu quả như một class concrete. Với callback quan trọng và nhiều domain types, ưu tiên implementation class rõ **BeforeSaveCallback<CatalogProduct>**.

### 13.4. Không cần gọi callback bằng tay

Nếu muốn chuẩn hóa một DTO khi API nhận request, hãy gọi hàm chuẩn hóa trong service/validator. Không gọi trực tiếp **onBeforeSave** như một bước bổ sung ngoài lifecycle, vì điều đó dễ khiến logic thực thi hai lần hoặc nhận Document chưa được convert đúng.

## 14. Phạm vi collection và domain type

Generic **BeforeSaveCallback<CatalogProduct>** định nghĩa target domain type. Callback còn nhận **collection** thực mà thao tác ghi đang dùng.

~~~java
if (!"catalog_products".equals(collection)) {
    return entity;
}
~~~

Guard này hữu ích nếu cùng entity được ghi vào collection khác có schema/index policy riêng. Tuy nhiên, **không được dựa duy nhất vào tên collection để bảo đảm authorization hoặc phân loại dữ liệu**.

### 14.1. Collection override

Một số MongoTemplate overload cho phép chọn collection name cụ thể. Nếu service gọi save(entity, "catalog_products_archive"), callback nhận collection tương ứng; có thể phải:

- Giữ cùng quy tắc BSON.
- Dùng schema policy riêng.
- Hoặc bỏ qua callback cho archive collection.

Quyết định dựa trên hợp đồng nghiệp vụ. Không để archive data trở thành trường hợp không được validate chỉ vì callback lặng lẽ return.

### 14.2. Multiple tenants cùng collection

Đối với collection dùng chung:

~~~javascript
{
  tenant_id: "shop-a",
  sku: "BOOK-101"
}
~~~

**collection name không phân biệt tenant**. Callback có thể đọc document.getString("tenant_id") để áp policy phù hợp, nhưng tenantId phải được service xác định từ authentication/authorization context đáng tin cậy.

### 14.3. Không nhầm generic callback với schema validator

Spring Data chỉ gọi callback trên những đường ghi tích hợp mapping phù hợp. Các lệnh raw driver, ứng dụng khác hoặc admin script có thể không gọi. Muốn bảo vệ bất biến ở mức collection cho mọi writer, cần cân nhắc **MongoDB schema validation**, unique index và quyền ghi.

## 15. Insert/save có callback; update theo Query thì sao?

Đây là giới hạn quan trọng của bài.

~~~java
mongoTemplate.insert(product);
mongoTemplate.save(product);
repository.save(product);
repository.insert(product);
~~~

Các thao tác ghi **entity qua mapping lifecycle** như insert/save có cơ chế kích hoạt BeforeConvert/BeforeSave callbacks theo tích hợp tương ứng.

Nhưng update theo query:

~~~java
Query query = Query.query(
    Criteria.where("sku").is("BOOK-101")
);

Update update = new Update()
    .set("displayName", "Tên mới");

mongoTemplate.updateFirst(
    query, update, CatalogProduct.class);
~~~

Không cần tạo một CatalogProduct entity mới và convert nó thành một Document đầy đủ. MongoDB nhận **update operators** hoặc pipeline update. Vì vậy **BeforeSaveCallback không tự được gọi cho kiểu update này**.

### 15.1. Vì sao đây là rủi ro cho derived field?

Giả sử trước update:

~~~javascript
{
  display_name: "Old Product",
  search_display: "old product"
}
~~~

Service chạy:

~~~java
new Update().set("displayName", "New Product");
~~~

Sau update:

~~~javascript
{
  display_name: "New Product",
  search_display: "old product"
}
~~~

Nếu field search_display được duy trì **chỉ qua BeforeSaveCallback**, nó có thể bị cũ khi có một write path sử dụng updateFirst.

### 15.2. Chiến lược không để field derived bị cũ

1. **Quy định mọi update liên quan phải cập nhật cả hai field** trong service.
2. Tạo helper dùng chung để tính normalized value cho insert/save và update.
3. Với trường hợp phù hợp, sử dụng aggregation pipeline update ở MongoDB Server để cập nhật derived field theo biểu thức server-side.
4. Dùng dữ liệu snapshot riêng hoặc một quy trình reindex/backfill khi chấp nhận eventual consistency.
5. Viết integration test trên **cả insert/save lẫn updateFirst/findAndModify/bulk writes**.

Không sửa bằng cách tự gọi BeforeSaveCallback trực tiếp với một Document giả bên ngoài converter rồi hy vọng nó trở thành lifecycle update tự động.

### 15.3. Những đường ghi khác

| Operation | Có thể dựa vào BeforeSaveCallback? |
| --- | --- |
| MongoTemplate.insert(entity) | **Có**, với mapped entity lifecycle |
| MongoTemplate.save(entity) | **Có**, với mapped entity lifecycle |
| Repository.save(entity) | **Có**, khi delegate qua store mapping lifecycle |
| Repository.insert(entity) | **Có**, ở integration thông thường |
| MongoTemplate.updateFirst(Query, Update, type) | **Không**, không convert nguyên entity để save |
| MongoTemplate.updateMulti(...) | **Không**, tương tự |
| MongoTemplate.findAndModify(Query, Update, ...) | **Không**, operator update không phải entity save |
| BulkOperations.updateOne/updateMulti | **Không mặc định**, là lệnh operator/bulk |
| Raw MongoCollection.insertOne(Document) | **Không**, bỏ qua Spring Data EntityCallbacks |
| mongoTemplate.remove(...) | **Không**, xóa document |

Với **insertAll**, **saveAll** hoặc các overload có tối ưu bulk/driver khác nhau, cần kiểm chứng behavior theo phiên bản và API cụ thể; không tự suy rằng toàn bộ đường ghi đều là từng save(entity) theo cùng callback semantics.

### 15.4. Index/transaction không gọi BeforeSaveCallback

Tạo index, count, aggregation read, query explain hoặc begin/commit transaction không có thao tác convert entity để lưu Document theo lifecycle này.

## 16. Idempotency và việc callback có thể chạy nhiều lần

Một save có thể được thực hiện lại vì:

- HTTP request được người dùng gửi lại.
- Application retry sau timeout.
- Transaction được thử lại khi có transient error.
- Scheduler chạy lại job.
- Entity được save lần nữa trong một workflow khác.

Nếu callback chạy:

~~~java
document.put("tags",
    document.getList("tags", String.class)
        .stream()
        .map(tag -> tag + "-indexed")
        .toList());
~~~

thì việc đọc document đã ghi rồi save lại có thể tạo các giá trị như **java-indexed-indexed**.

### 16.1. Chọn transformation idempotent

Chuẩn hóa từ dữ liệu nguồn ổn định:

~~~java
String displayName = document.getString("display_name");
if (displayName != null) {
    document.put("search_display",
        displayName.trim().toLowerCase(java.util.Locale.ROOT));
}
~~~

Cùng một input sẽ tạo cùng output. Không append một suffix hoặc tự tăng counter trong callback mà không có quy tắc tránh lặp.

### 16.2. Random UUID và clock

~~~java
// Không nên dùng cho một operation ID cần ổn định qua retry:
document.put("operation_id", java.util.UUID.randomUUID().toString());
~~~

Một callback có thể chạy lại và tạo operationId mới, khiến hệ thống mất khả năng nhận diện cùng một business request. Operation ID/idempotency key nên do business layer xác định và lưu cùng nghiệp vụ qua transaction/unique index khi cần.

Timestamp như writeProcessedAt có thể phù hợp nếu ngữ nghĩa là “thời điểm mỗi lần ghi”; nhưng không dùng nó như bằng chứng một order đã được xử lý đúng một lần.

### 16.3. Side effects bên ngoài không thuộc transaction

~~~java
@Override
public CatalogProduct onBeforeSave(
        CatalogProduct entity,
        Document doc,
        String collection) {

    // Không nên gọi payment gateway, gửi email,
    // publish message broker trực tiếp tại đây.
    return entity;
}
~~~

Callback được gọi **trước** khi MongoDB write hoàn tất. Nếu ghi thất bại, transaction rollback hoặc client retry, side effect ngoài hệ thống không tự được hoàn tác. Dùng **outbox, after-commit workflow hoặc state machine** cho side effects có yêu cầu bền vững.

## 17. Exception từ callback

Callback có thể ném exception khi gặp dữ liệu không hợp lệ:

~~~java
if (entity.tenantId() == null
        || entity.tenantId().isBlank()) {
    throw new IllegalArgumentException(
        "tenantId is required");
}
~~~

Khi callback ném exception, thao tác save qua lifecycle thông thường **không tiếp tục bình thường tới write**, và caller nhận lỗi qua call stack tương ứng.

### 17.1. Không dựa vào callback làm security boundary duy nhất

Spring callback không được chạy khi writer khác dùng raw MongoDB Driver hoặc script. Nếu muốn:

- Bắt buộc tenantId có mặt.
- SKU unique trong tenant.
- Field không âm.
- Không có giá trị BSON nguy hiểm.

thì cần một tổ hợp **service validation, MongoDB schema validator, unique index và access control**. BeforeSaveCallback chỉ là một điểm thực thi thuận tiện trong ứng dụng.

### 17.2. Lỗi trong callback không đồng nghĩa rollback mọi công việc khác

Nếu service đã ghi một collection khác rồi mới gọi save(entity) gặp callback exception, các ghi trước đó **không tự rollback** nếu không có MongoDB transaction. Callback không phải transaction manager.

### 17.3. Thông tin lỗi cần tránh rò dữ liệu

Đừng đưa raw Document hoặc toàn bộ Customer/order sensitive fields vào exception message hay log. Chỉ log identifier được phép, loại lỗi và một số metadata cần để chẩn đoán.

## 18. Performance: callback không phải nơi chạy thêm I/O

Một BeforeSaveCallback được gọi nhiều lần có thể nằm trên hot write path. Nếu mỗi save lại làm thêm một query hoặc gọi HTTP:

~~~java
// Phản ví dụ:
CustomerDocument customer =
    customerRepository.findById(entity.customerId()).orElseThrow();

document.put("customer_name", customer.displayName());
~~~

thì số round trips có thể tăng, callback trở nên khó kiểm thử và có thể phát sinh vòng gọi callback nếu nó tiếp tục save các entity khác.

### 18.1. Phù hợp với xử lý nhỏ, deterministic

Thích hợp:

- Trim/normalize một số field BSON.
- Thêm một derived field có quy tắc xác định.
- Bỏ một field nhạy cảm đã được xác định rõ.
- Thêm metadata/schema version có kiểm soát.

Không nên:

- Query hàng chục collection.
- Gọi payment gateway/HTTP.
- Chạy aggregation nặng.
- Ghi ra collection khác như một tác dụng phụ.
- Sleep hoặc giữ lock lâu.
- Serialize một object graph rất lớn không cần thiết.

### 18.2. Chú ý throughput

Với 10.000 saves/s, callback chạy logic O(N) theo mảng lớn trên mỗi document có thể tiêu thụ CPU đáng kể. Đo thời gian callback và kích thước payload; tránh tự copy document nhiều lần nếu không cần.

### 18.3. Không giả định event multicaster là một callback đồng bộ

Một BeforeSaveCallback được framework xử lý theo callback chain có thứ tự; một BeforeSaveEvent listener có thể chịu ảnh hưởng scheduling của event multicaster. Nếu dữ liệu cần được thay đổi **trước write**, đừng đổi sang async event chỉ để “tối ưu” mà làm mất ràng buộc thời điểm.

## 19. An toàn dữ liệu: xóa field khỏi BSON một cách có chủ đích

Một BeforeSaveCallback có thể xóa một trường không được phép lưu. Giả sử một mapping legacy vẫn có dữ liệu **rawAccessToken**, nhưng chính sách bảo mật quyết định không persist giá trị đó vào collection.

~~~java
@Override
public CatalogProduct onBeforeSave(
        CatalogProduct entity,
        Document document,
        String collection) {

    document.remove("raw_access_token");
    return entity;
}
~~~

Ví dụ chỉ minh họa **Document.remove**; CatalogProduct mẫu không có rawAccessToken. Không được dùng một chính sách bảo mật quan trọng chỉ dựa trên một callback mà tất cả đường ghi ngoài framework có thể bỏ qua.

### 19.1. Thiết kế tốt hơn: không map secrets ngay từ đầu

Nếu một trường tuyệt đối không được lưu:

- Không đưa nó vào persistent entity.
- Có thể dùng **@Transient** cho property ở Java nếu vẫn phải giữ tạm trong memory.
- Tách request DTO chứa secrets khỏi persistence model.
- Cấu hình converter để chỉ lưu dữ liệu đã được cho phép.
- Áp MongoDB schema validation và quyền ghi phù hợp khi cần.

Nếu secrets bắt buộc phải lưu thì cần encryption/key management đúng quy trình, không chỉ xóa field “cho an toàn”.

### 19.2. Nếu field đã nằm trong database cũ?

Xóa field ở Document trước một lần save mới không đảm bảo toàn bộ document cũ đã được dọn. Cần migration/backfill/retention policy để xử lý dữ liệu lịch sử, đồng thời đánh giá tác động đến backup và các replica.

### 19.3. Không log BSON nguyên vẹn

Tránh:

~~~java
log.debug("Saving {}", document.toJson());
~~~

Nếu Document chứa dữ liệu cá nhân/token, log có thể trở thành kho dữ liệu nhạy cảm. Chỉ log những field được phê duyệt và cắt độ dài phù hợp.

## 20. Callback và quy tắc business: đừng đặt sai lớp trách nhiệm

Những logic thích hợp cho callback:

- Bổ sung search key thuần túy từ một field đã có.
- Chuẩn hóa metadata dạng BSON.
- Ghi schema version tĩnh.
- Bỏ một field BSON theo quy tắc schema rõ ràng.

Những logic thường nên đặt ở service/domain:

- Kiểm tra quyền người dùng được cập nhật tenant nào.
- Quyết định một order có được phép chuyển trạng thái hay không.
- Xác định số lượng tồn kho còn đủ để bán.
- Gửi thông báo/thu tiền.
- Khóa business operation chống gửi trùng.
- Phối hợp nhiều collection bằng transaction.

### 20.1. Vì sao callback không bảo vệ unique?

Hai request đồng thời có thể cùng chạy callback kiểm tra một SKU “chưa tồn tại”. Cả hai có thể đều hợp lệ theo lần đọc đó. **MongoDB unique index** mới bảo vệ tính duy nhất ở server khi cạnh tranh.

### 20.2. Vì sao callback không thay authorization?

Nếu client tự truyền tenantId và service không kiểm tra, callback chỉ đọc **tenant_id** cũng không biết người dùng có thực sự được phép ghi cho tenant đó. Cần xác thực/ủy quyền ở tầng service và áp filter đúng tenant khi update.

### 20.3. Tách pure function để dùng chung

Để tránh quy tắc normalized search được triển khai khác nhau giữa BeforeSaveCallback và Update builder:

~~~java
import java.text.Normalizer;
import java.util.Locale;

public final class SearchNormalizer {

    private SearchNormalizer() {}

    public static String normalize(String value) {
        if (value == null) {
            return null;
        }
        return Normalizer.normalize(
            value, Normalizer.Form.NFKC)
            .trim()
            .toLowerCase(Locale.ROOT);
    }
}
~~~

Sau đó cả callback và service update đều gọi **SearchNormalizer.normalize**. Khi quy tắc thay đổi, có một nơi để kiểm thử và cập nhật.

### 20.4. Metadata do server hay app sở hữu?

Một trường như write_source hoặc write_schema có thể do app ghi trong callback. Các trường như updatedAt có thể được ghi bằng auditing hoặc MongoDB $currentDate. Cần ghi rõ nguồn tạo giá trị, múi giờ/clock và ý nghĩa của nó, tránh hai cơ chế cùng ghi đè.

## 21. BeforeSaveCallback với transaction và session

Giả sử một service:

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager"
)
public void publishProduct(CatalogProduct product) {
    mongoTemplate.save(product);
    outboxRepository.insert(buildOutbox(product));
}
~~~

Trong một MongoDB deployment hỗ trợ transaction và cấu hình **MongoTransactionManager** đúng, các thao tác mapping save và outbox repository có thể tham gia cùng ClientSession/transaction.

BeforeSaveCallback chạy khi MongoTemplate xử lý **save(product)**, tức là **trước khi toàn bộ transaction commit**.

### 21.1. Điều gì nếu rollback?

Giả sử callback thêm search_display, sau đó insert outbox lỗi khiến transaction rollback:

~~~text
BeforeSaveCallback: sửa Document
MongoDB: nhận lệnh save trong transaction
Outbox insert: lỗi
Transaction: abort
=> Không commit cả save lẫn outbox trong transaction
~~~

Tuy nhiên, callback đã chạy trong JVM. Nếu nó ghi file/gửi email hoặc đẩy message ra ngoài, side effect ấy **không tự rollback**.

### 21.2. Retry toàn bộ transaction

Khi transaction transiently failed và retry từ đầu, callback có thể được gọi lại. Vì vậy, callback nên **deterministic/idempotent**, không sinh operation ID mới mỗi lần chạy nếu nghiệp vụ đòi ID ổn định.

### 21.3. Raw driver trong transaction

Nếu code dùng raw MongoCollection trực tiếp với một MongoClient/session khác, BeforeSaveCallback không tự được gọi chỉ vì một Spring @Transactional đang bao quanh method. Mọi guarantee phụ thuộc chính xác đường ghi và session integration.

### 21.4. Transaction không tự gọi callback cho query updates

Một updateFirst chạy **trong transaction** vẫn là query-based update, không tự tạo entity converted Document qua BeforeSaveCallback. Transaction bảo vệ việc commit/rollback, không thay đổi loại lifecycle hook được gọi.

## 22. ReactiveBeforeSaveCallback: cùng phase, khác return type

Trong reactive stack, Spring Data MongoDB có interface tương ứng:

~~~java
package org.springframework.data.mongodb.core.mapping.event;

import org.bson.Document;
import org.reactivestreams.Publisher;
import org.springframework.data.mapping.callback.EntityCallback;

@FunctionalInterface
public interface ReactiveBeforeSaveCallback<T>
        extends EntityCallback<T> {

    Publisher<T> onBeforeSave(
        T entity, Document document, String collection);
}
~~~

Đây là **chữ ký minh họa của framework**, không phải file cần tự định nghĩa lại. Reactive version trả **Publisher<T>**, thường là Mono<T>.

### 22.1. Ví dụ reactive callback

~~~java
package com.example.catalog;

import java.text.Normalizer;
import java.util.Locale;
import org.bson.Document;
import org.reactivestreams.Publisher;
import org.springframework.stereotype.Component;
import org.springframework.data.mongodb.core.mapping.event.ReactiveBeforeSaveCallback;
import reactor.core.publisher.Mono;

@Component
public class ReactiveCatalogProductBeforeSave
        implements ReactiveBeforeSaveCallback<CatalogProduct> {

    @Override
    public Publisher<CatalogProduct> onBeforeSave(
            CatalogProduct entity,
            Document document,
            String collection) {

        if ("catalog_products".equals(collection)) {
            String name = document.getString("display_name");

            if (name != null) {
                document.put("search_display",
                    Normalizer.normalize(
                        name, Normalizer.Form.NFKC)
                        .trim()
                        .toLowerCase(Locale.ROOT));
            }
            document.put("write_schema", 1);
        }

        return Mono.just(entity);
    }
}
~~~

Khi dùng **ReactiveMongoTemplate** hoặc reactive repository qua lifecycle mapping, reactive callback được áp dụng trong reactive processing chain.

### 22.2. Imperative callback không tự áp dụng cho reactive

Spring Data EntityCallback API được phân biệt theo kiểu API:

- **BeforeSaveCallback<T>** cho imperative mapping.
- **ReactiveBeforeSaveCallback<T>** cho reactive mapping.

Nếu ứng dụng có cả hai stack, cần đăng ký callback tương ứng trên từng đường ghi. Đừng kỳ vọng một @Component implements BeforeSaveCallback tự chạy khi **ReactiveMongoTemplate.save**.

### 22.3. Mono.just không tự tạo phép ghi độc lập

~~~java
return Mono.just(entity);
~~~

Đây là Publisher phát entity trở lại pipeline callback. **Không tự subscribe()** để ép ghi BSON, vì thao tác ghi vẫn do ReactiveMongoTemplate/repository tiếp tục khi caller subscribe vào publisher save.

### 22.4. Không block trong reactive callback

~~~java
// Không nên:
CustomerDocument customer =
    blockingCustomerRepository.findById(id).orElseThrow();
~~~

Đặt I/O blocking ở reactive callback có thể làm nghẽn thread xử lý reactive. Nếu cần truy vấn bất đồng bộ, hãy cân nhắc chuyển logic đó ra **service reactive** và compose trong Mono/Flux với lifecycle/error rõ ràng, thay vì giấu N+1 trong mapping callback.

### 22.5. Khi reactive save được subscribe hai lần

Một publisher save có thể được subscribe hai lần trong một luồng xử lý sai và kích hoạt hai lần ghi/callback. **Reactive không tự tạo idempotency**. Nếu cùng một business operation có thể phát lại, dùng operation ID/unique constraint và thiết kế ở tầng service.

## 23. Kiểm thử đơn vị callback mà không cần MongoDB

Đầu tiên có thể kiểm tra một hàm onBeforeSave thuần:

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;

class CatalogProductBeforeSaveUnitTest {

    @Test
    void enrichesConvertedDocumentButReturnsEntity() {
        CatalogProduct entity = new CatalogProduct(
            new ObjectId(),
            "shop-a",
            "BOOK-101",
            "  MongoDB Guide  ",
            "ACTIVE",
            Instant.parse("2025-06-01T09:00:00Z")
        );

        Document bson = new Document()
            .append("_id", entity.id())
            .append("tenant_id", entity.tenantId())
            .append("sku", entity.sku())
            .append("display_name", entity.displayName());

        CatalogProductBeforeSave callback =
            new CatalogProductBeforeSave();

        CatalogProduct result = callback.onBeforeSave(
            entity, bson, "catalog_products");

        assertThat(result).isSameAs(entity);
        assertThat(bson.getString("search_display"))
            .isEqualTo("mongodb guide");
        assertThat(bson.getInteger("write_schema"))
            .isEqualTo(1);
        assertThat(bson.getString("display_name"))
            .isEqualTo("  MongoDB Guide  ");
    }
}
~~~

**Test này xác minh logic callback** khi Document đã có key BSON. Nhưng nó chưa chứng minh Spring Data thực sự gọi callback đúng chỗ, chưa kiểm tra mapping @Field và không chứng minh data đã persist. Cần integration test sau đây.

### 23.1. Unit test không nên tự gọi converter nếu không cần

Nếu mục tiêu chỉ kiểm tra normalization, cung cấp Document phù hợp như phần trên giúp test nhỏ, không phụ thuộc MongoDB. Nếu mục tiêu là kiểm chứng **mapping + lifecycle + database**, cần một test gọi **MongoTemplate.insert/save** thực.

### 23.2. Kiểm thử null/missing

Thử Document không có **display_name**, hoặc có giá trị null. Callback chính ở phần 5 phải **remove("search_display")** và không phát sinh NullPointerException.

### 23.3. Kiểm thử collection khác

Khi truyền collection **catalog_products_archive**, callback trả entity mà không sửa Document. Nếu chính sách schema yêu cầu archive cũng có search_display, điều kiện collection ở callback phải được điều chỉnh có chủ đích.

## 24. Integration test: đọc lại raw BSON sau insert

Một test MongoDB thật phải xác minh ba thứ:

1. Spring Data gọi **BeforeConvertCallback** trước conversion.
2. Spring Data gọi **BeforeSaveCallback** sau conversion và ghi trường mới vào Document.
3. Các field trong MongoDB đúng **BSON key names**, không chỉ đúng Java property.

### 24.1. @DataMongoTest với @Import callbacks

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
@Import({
    CatalogSkuBeforeConvert.class,
    CatalogProductBeforeSave.class
})
class CatalogProductCallbackIntegrationTest {

    @Autowired
    MongoTemplate template;

    @Test
    void savesMappedFieldsAndBeforeSaveBsonFields() {

        ObjectId id = new ObjectId();
        CatalogProduct product = new CatalogProduct(
            id,
            "shop-a",
            "  book-101 ",
            "  Sách MongoDB  ",
            "ACTIVE",
            Instant.parse("2025-06-01T09:00:00Z")
        );

        try {
            template.insert(product);

            Document raw = template
                .getCollection("catalog_products")
                .find(new Document("_id", id))
                .first();

            assertThat(raw).isNotNull();
            assertThat(raw.getString("tenant_id"))
                .isEqualTo("shop-a");
            assertThat(raw.getString("sku"))
                .isEqualTo("BOOK-101");
            assertThat(raw.getString("display_name"))
                .isEqualTo("  Sách MongoDB  ");
            assertThat(raw.getString("search_display"))
                .isEqualTo("sách mongodb");
            assertThat(raw.getInteger("write_schema"))
                .isEqualTo(1);
            assertThat(raw.containsKey("displayName"))
                .isFalse();

            CatalogProduct loaded =
                template.findById(id, CatalogProduct.class);

            assertThat(loaded).isNotNull();
            assertThat(loaded.sku())
                .isEqualTo("BOOK-101");
            assertThat(loaded.displayName())
                .isEqualTo("  Sách MongoDB  ");

        } finally {
            template.remove(
                Query.query(Criteria.where("_id").is(id)),
                CatalogProduct.class
            );
        }
    }
}
~~~

**Giải thích:**

- BeforeConvertCallback chuyển SKU thành chữ hoa.
- Converter ánh xạ **tenantId → tenant_id**, **displayName → display_name**.
- BeforeSaveCallback thêm **search_display/write_schema** trên Document đã chuyển đổi.
- MongoDB lưu các field bổ sung.
- Đọc CatalogProduct vẫn có **displayName gốc**, vì callback chỉ thêm trường khác vào BSON.

### 24.2. Vì sao dùng @Import?

**@DataMongoTest** là test slice. Không nên mặc định mọi @Component ở mọi package của ứng dụng sẽ được scan trong slice này. @Import đăng ký tường minh các callback cần kiểm thử, giúp test xác nhận chính xác wiring.

### 24.3. Database test riêng

Ví dụ yêu cầu MongoDB test instance tương thích, cấu hình bởi dự án (có thể qua Testcontainers). Không chạy bài test này trên production. Cần isolation giữa tests và không dùng tenant/ID của người dùng thật.

### 24.4. Đọc raw BSON khác đọc entity

~~~java
Document raw = template.getCollection(
    "catalog_products").find(new Document("_id", id)).first();
~~~

Raw collection cho thấy các key BSON đã được ghi. Trong khi đó:

~~~java
CatalogProduct loaded =
    template.findById(id, CatalogProduct.class);
~~~

trả entity đã được converter map theo model. Dùng **cả hai** để phát hiện trường hợp callback thêm field mà entity không expose hoặc converter ánh xạ sai field name.

## 25. Integration test: query update không kích hoạt BeforeSaveCallback

Test phần trước chứng minh đường **insert(entity)**. Cần thêm một test để phát hiện rủi ro khi hệ thống cập nhật bằng operator:

~~~java
import org.springframework.data.mongodb.core.query.Update;

@Test
void queryBasedUpdateCanLeaveBeforeSaveDerivedFieldStale() {
    ObjectId id = new ObjectId();

    CatalogProduct product = new CatalogProduct(
        id,
        "shop-a",
        "BOOK-102",
        "Old Name",
        "ACTIVE",
        Instant.parse("2025-06-01T09:00:00Z")
    );

    try {
        template.insert(product);

        Query byId = Query.query(
            Criteria.where("_id").is(id)
        );

        template.updateFirst(
            byId,
            new Update().set("displayName", "New Name"),
            CatalogProduct.class
        );

        Document raw = template
            .getCollection("catalog_products")
            .find(new Document("_id", id))
            .first();

        assertThat(raw).isNotNull();
        assertThat(raw.getString("display_name"))
            .isEqualTo("New Name");

        // BeforeSaveCallback đã chạy cho insert,
        // nhưng không chạy cho operator updateFirst.
        assertThat(raw.getString("search_display"))
            .isEqualTo("old name");

        // Full entity save ở bước khác có thể cập nhật lại
        // field derived thông qua callback.
        CatalogProduct reloaded =
            template.findById(id, CatalogProduct.class);

        assertThat(reloaded).isNotNull();
        template.save(reloaded);

        Document afterSave = template
            .getCollection("catalog_products")
            .find(new Document("_id", id))
            .first();

        assertThat(afterSave).isNotNull();
        assertThat(afterSave.getString("search_display"))
            .isEqualTo("new name");

    } finally {
        template.remove(
            Query.query(Criteria.where("_id").is(id)),
            CatalogProduct.class
        );
    }
}
~~~

Đặt method trên trong **CatalogProductCallbackIntegrationTest** của phần 24. Đây là kiểm thử tích hợp quan trọng: nó chứng minh sự khác biệt giữa **entity save lifecycle** và **query update lifecycle**.

### 25.1. Bài học thiết kế

Nếu search_display phải luôn đồng bộ với display_name, **không đủ** để chỉ triển khai BeforeSaveCallback. Mọi đường cập nhật display_name cần cập nhật search_display theo cùng một quy tắc hoặc chuyển field derived sang cơ chế khác phù hợp.

### 25.2. Không xem full save là giải pháp mặc định cho mọi update

Một phương án chữa cháy là sau updateFirst lập tức findById rồi save. Nhưng điều đó tạo thêm round trips và có thể gây lost updates nếu không xử lý concurrency/version. Nên thiết kế một lệnh update cập nhật đầy đủ fields hoặc một cơ chế đồng bộ chuyên biệt, thay vì luôn full-save từ snapshot có nguy cơ cũ.

### 25.3. Nếu mapper tạo field khác?

Test dùng raw BSON để xác nhận **display_name**, không chỉ assert một Java getter. Nếu đổi annotation @Field, custom converter hoặc naming strategy, test sẽ phát hiện đường mapping không khớp.

## 26. Reactive test và callback lifecycle

Khi dùng **ReactiveMongoTemplate**, ví dụ service:

~~~java
import reactor.core.publisher.Mono;

public Mono<CatalogProduct> saveReactive(
        ReactiveMongoTemplate template,
        CatalogProduct entity) {
    return template.insert(entity);
}
~~~

**Mono<CatalogProduct>** là publisher được trả ra; nó thường chưa thực hiện insert cho tới khi có subscription. Callback reactive tham gia vào quá trình xử lý khi thực thi publisher.

### 26.1. Dùng StepVerifier

~~~java
StepVerifier.create(
    reactiveTemplate.insert(
        new CatalogProduct(
            new ObjectId(),
            "shop-a",
            "BOOK-103",
            "  Reactive MongoDB  ",
            "ACTIVE",
            Instant.parse("2025-06-01T09:00:00Z")
        )
    )
)
.assertNext(saved -> {
    assertThat(saved.sku()).isEqualTo("BOOK-103");
})
.verifyComplete();
~~~

Ví dụ giả định có **reactiveTemplate** được inject và **reactor-test** dependency. Nếu callback reactive chỉ sửa raw Document và không sửa entity, **assert trên saved entity chưa chứng minh raw BSON đã được bổ sung**. Cần test đọc BSON raw tương tự phần 24 hoặc dùng một projection/raw query thích hợp.

### 26.2. Reactive callbacks không phải reactive transactions

Một callback returning Mono không tự khởi động MongoDB transaction. Nếu cần các thao tác MongoDB khác cùng commit/rollback, phải sử dụng **ReactiveMongoTransactionManager** và compose chúng trong đúng transaction context.

### 26.3. Kiểm thử lỗi

ReactiveBeforeSaveCallback có thể trả:

~~~java
return Mono.error(
    new IllegalArgumentException("Invalid BSON"));
~~~

Khi đó publisher save phát tín hiệu lỗi và không tiếp tục đường ghi bình thường. Test nên dùng StepVerifier.expectError(...) và xác minh không có document mới khi callback fail trong môi trường được kiểm soát.

### 26.4. Không tạo hai subscription để test một lần ghi

~~~java
Mono<CatalogProduct> write = reactiveTemplate.insert(product);

// Tránh subscribe riêng hai lần rồi cho rằng chỉ có một insert.
write.subscribe();
StepVerifier.create(write).verifyComplete();
~~~

Ở đây publisher có thể thực thi insert hai lần; lần thứ hai còn có thể gặp duplicate key trên _id. Trong test, chỉ có **một subscription chịu trách nhiệm thực hiện thao tác**, rồi đọc lại bằng một publisher tiếp nối khi cần.

## 27. Các lỗi thường gặp khi sử dụng BeforeSaveCallback

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Sửa setter nhưng BSON không đổi | BeforeSave sau conversion | Sửa Document hoặc dùng BeforeConvert |
| MongoDB có cả tenantId và tenant_id | Dùng tên Java thay BSON key | Đọc mapping @Field, sửa tenant_id |
| search_display bị cũ sau updateFirst | Query update không gọi BeforeSaveCallback | Đồng bộ field trong update path |
| Raw BSON có field mới nhưng entity không có | Field không được khai báo/mapped ở entity | DTO/projection hoặc mapping thích hợp |
| Callback không chạy | Bean không thuộc ApplicationContext | Kiểm tra @Component/@Bean/@Import |
| Callback chạy hai lần | Đăng ký trùng @Bean + @Component hoặc save hai lần | Rà soát wiring và caller |
| @Order không có hiệu lực như mong đợi | Nhầm BeforeConvert phase với BeforeSave phase | Thiết kế order trong từng callback type |
| Test unit pass nhưng MongoDB thiếu field | Chỉ gọi callback bằng tay, chưa test lifecycle | @DataMongoTest + raw BSON readback |
| Field _id lệch entity | Sửa _id sau converter | Sinh ID trước conversion, không sửa tùy tiện |
| Type mapping đọc lỗi | Xóa/đổi _class không kiểm soát | Cấu hình type mapper đúng |
| Optimistic lock không như kỳ vọng | Tự sửa version BSON | Dùng @Version/Spring Data semantics |
| Timestamp không đổi khi updateFirst | Auditing callback không chạy trên query updates | Cập nhật timestamp trực tiếp trong Update |
| Save dữ liệu có stale search metadata | Một số writer bỏ qua callback | Schema/migration và write-path strategy |
| Reactive write không kích hoạt sync callback | Hai callback APIs tách biệt | ReactiveBeforeSaveCallback |
| Reactive callback làm ứng dụng chậm | Gọi blocking HTTP/repository | Dùng service reactive, bỏ I/O khỏi callback |
| Email đã gửi dù transaction abort | Callback có side effect ngoài MongoDB | Outbox/after-commit workflow |
| Dữ liệu độc hại vẫn được ghi | Writer khác không đi qua callback | Schema validation, quyền ghi |
| Unique SKU vẫn trùng | Callback validate trước nhưng có race | MongoDB unique index |
| Nested field không được sửa | Nhầm tên/path hoặc nested type khác | Kiểm tra raw BSON và Document con |
| Callback ném lỗi làm save thất bại | Validation/mapping assumptions sai | Phân loại lỗi và sửa input/schema |
| Latency ghi tăng | Callback làm việc nặng hoặc query N+1 | Pure transformation, profiling |
| Bean callback gây lỗi với type khác | Generic type quá rộng/erased | Dùng implementation typed rõ |

### 27.1. Quy trình chẩn đoán nhanh

1. Xác định thao tác là **insert/save(entity)** hay **updateFirst/bulk/raw driver**.
2. Kiểm tra bean BeforeSaveCallback có trong ApplicationContext không.
3. Xác minh entity generic type đúng và collection guard không bỏ qua.
4. Đọc schema Java: **@Id, @Field, converter, nested mapping**.
5. Đọc raw Document trước khi callback thay đổi hoặc dùng unit test tạo Document đại diện.
6. Xác định logic sửa **entity** hay **Document**.
7. Kiểm tra đã có BeforeConvertCallback/auditing/BeforeSaveEvent khác chưa.
8. Xem @Order giữa các callbacks cùng phase.
9. Đọc raw BSON ở MongoDB sau insert/save và so sánh entity đọc lại.
10. Kiểm thử thêm query update, transaction rollback, reactive và retry.

## 28. Câu hỏi thiết kế hay gặp

### 28.1. Trả một entity mới từ BeforeSaveCallback có cập nhật BSON không?

**Không tự động.** Dù interface cho phép trả một entity khác, bước convert sang Document đã xảy ra. Nếu field persistent của entity mới khác với Document, dữ liệu ghi vẫn theo Document đã chuyển đổi/sửa. Muốn persisted entity thay đổi thì xử lý ở BeforeConvertCallback.

### 28.2. Có thể sửa Document và entity cùng lúc không?

Có thể về mặt Java, nhưng phải rõ hai trạng thái được điều chỉnh thế nào. Nếu cần cả saved BSON lẫn entity trả về đồng bộ, thiết kế ở BeforeConvert hoặc business layer thường dễ quản lý hơn. Tránh nhân đôi logic trên hai object và dựa vào side effects không được tài liệu bảo đảm.

### 28.3. Có thể dùng BeforeSaveCallback để thêm field không có trong entity không?

**Có.** Đó là một use case phù hợp: sửa raw Document và driver lưu nó. Nhưng entity khi đọc lại sẽ không tự có getter cho field không được mapping.

### 28.4. Có thể dùng BeforeSaveCallback thay @Field không?

Không nên. **@Field** thuộc metadata mapping giữa property Java và BSON name. BeforeSaveCallback phù hợp cho trường hợp phải bổ sung/chỉnh sửa BSON sau mapping. Đừng chuyển mọi quy tắc mapping cơ bản sang mutation thủ công trong callback.

### 28.5. Callback có tự gọi cho embedded item khi root được save không?

Không nên coi mọi embedded item đều nhận một callback root độc lập. Với dữ liệu embedded đã convert thành nested Document, callback của root có thể thao tác trên nội dung con, hoặc custom converter xử lý mapping theo mô hình đã chọn.

### 28.6. Có thể dùng callback để đảm bảo SKU duy nhất không?

Không. Callback tự kiểm tra query rồi save vẫn chịu race giữa nhiều writer. Cần unique index tương ứng, ví dụ **{tenant_id:1,sku:1} unique**.

### 28.7. Có thể gọi MongoTemplate trong callback để tra cứu thêm dữ liệu không?

Có thể viết Java như vậy nhưng thường **không nên**: tạo I/O ẩn, tăng latency, làm rối transaction context và có nguy cơ đệ quy callback khi ghi thêm entity khác. Đưa logic liên quan nhiều database operations ra service.

### 28.8. Nếu dữ liệu có custom converter?

Document trong BeforeSaveCallback là kết quả của converter đã chạy. Kiểm tra **kiểu BSON thực**, không giả định Java String/enum/Instant luôn giữ nguyên cấu trúc. Nếu conversion contract cần thay đổi, cân nhắc custom converter ở tầng mapping.

### 28.9. BeforeSaveCallback có chạy ở SaveAll?

Các API lưu nhiều entity có thể đi qua các đường thực thi khác nhau theo Spring Data version và tối ưu bulk. Không suy từ tên **saveAll** rằng mọi phần tử đều chạy y hệt một lời gọi save riêng biệt; viết integration test đúng API được dùng ở production.

### 28.10. Có thể viết BeforeSaveCallback chỉ vì muốn logging không?

Có thể dùng callback cho telemetry nhẹ, nhưng log không nên chứa toàn bộ dữ liệu nhạy cảm, và callback không bảo đảm transaction đã commit thành công. Nếu metrics cần phản ánh **completed writes**, nên quan sát sau write/commit ở tầng phù hợp thay vì đếm “before save invoked”.

## 29. Bài tập thực hành

### Bài tập 1: xác định thời điểm callback

Một CatalogProduct có displayName="  A  ". Spring Data đã convert entity thành Document. Trong BeforeSaveCallback, bạn gọi entity.setDisplayName("A") trên một entity mutable. MongoDB có chắc lưu "A" không?

**Đáp án:** Không. Document đã tạo trước đó không tự được convert lại; phải sửa Document hoặc chuyển normalization sang BeforeConvertCallback.

### Bài tập 2: chữ ký phương thức

Hoàn thành interface đúng:

~~~java
public class ProductCallback
        implements BeforeSaveCallback<CatalogProduct> {

    @Override
    public CatalogProduct onBeforeSave(
            CatalogProduct entity,
            Document document,
            String collection) {
        return entity;
    }
}
~~~

**Đáp án:** Nhận entity, **org.bson.Document**, collection; trả CatalogProduct.

### Bài tập 3: tên BSON đã được ánh xạ

Entity có:

~~~java
@Field("tenant_id")
private String tenantId;
~~~

Để lấy tenant trong Document, bạn dùng key nào?

**Đáp án:** **tenant_id**, không mặc định là tenantId.

### Bài tập 4: bổ sung trường derived

Cho Document đã có:

~~~javascript
{ display_name: "  MongoDB Essentials  " }
~~~

Viết hai dòng tạo search_display từ tên:

~~~java
String name = document.getString("display_name");
document.put("search_display",
    name.trim().toLowerCase(java.util.Locale.ROOT));
~~~

**Đáp án:** search_display trở thành **mongodb essentials**. Khi production, cần kiểm tra null/type và quy tắc Unicode.

### Bài tập 5: sửa field persistent

Bạn muốn SKU được upper-case trong cả entity sau lưu lẫn BSON. Chọn BeforeSaveCallback hay BeforeConvertCallback?

**Đáp án:** BeforeConvertCallback để trả entity với SKU mới **trước khi conversion**. Có thể áp dụng một hàm normalize thuần từ domain/service.

### Bài tập 6: kết quả sau save

BeforeSaveCallback thêm Document.write_schema=1 nhưng entity không có property tương ứng. Repository.save trả entity có tự có getter writeSchema mới không?

**Đáp án:** Không. Raw BSON có thể chứa write_schema, nhưng Java type không tự mở rộng property.

### Bài tập 7: nested document

Document có:

~~~javascript
{ supplier: { code: " SUP-01 " } }
~~~

Muốn trim code, có thể gọi document.put("supplier.code", "SUP-01") không?

**Đáp án:** Không nên. Document.put với chuỗi có dấu chấm có thể tạo key literal, không thao tác nested document như path update. Lấy **supplier** dưới dạng Document rồi sửa field **code**.

### Bài tập 8: callback order

Hai BeforeSaveCallback cùng sửa search_display, có thể đảm bảo callback nào thắng chỉ bằng thứ tự tên class không?

**Đáp án:** Không. Dùng **@Order/Ordered** có chủ đích và tốt hơn là phân công một callback sở hữu field đó.

### Bài tập 9: auditing

Bạn thay entity.updatedAt trong BeforeSaveCallback, nhưng BSON không đổi. Giải thích?

**Đáp án:** Callback chạy sau converter. Dùng auditing/BeforeConvertCallback để sửa persistent field trước mapping hoặc sửa Document/update operator theo hợp đồng.

### Bài tập 10: insert vs updateFirst

Service dùng MongoTemplate.insert nên search_display được tạo. Sau đó MongoTemplate.updateFirst set displayName mới. search_display có tự được tính lại không?

**Đáp án:** Không. Query-based update không kích hoạt BeforeSaveCallback của entity save. Phải đồng bộ derived field ở đường update.

### Bài tập 11: raw driver

Service dùng trực tiếp MongoCollection.insertOne(new Document(...)). BeforeSaveCallback<CatalogProduct> có tự chạy không?

**Đáp án:** Không. Raw driver bỏ qua Spring Data entity mapping callback infrastructure.

### Bài tập 12: xóa _class

Một callback xóa _class để giảm kích thước document. Có an toàn với mọi entity polymorphic không?

**Đáp án:** Không. _class có thể được converter dùng làm type hint. Thay chính sách type hints phải thực hiện trong cấu hình mapping và được kiểm thử.

### Bài tập 13: schema version

BeforeSaveCallback put("write_schema", 3). Các document phiên bản 1 trong database có tự được migration không?

**Đáp án:** Không. Callback chỉ áp dụng trên đường ghi tương ứng; dữ liệu đã lưu cần migration/backfill riêng.

### Bài tập 14: unique index

Hai request cùng callback kiểm tra SKU chưa tồn tại trước insert. Callback có đảm bảo không trùng SKU không?

**Đáp án:** Không. Pre-check chịu race. Cần unique index ở MongoDB.

### Bài tập 15: exception

BeforeSaveCallback ném IllegalArgumentException. Trong đường MongoTemplate.insert bình thường, MongoDB có nhận được lệnh insert đó không?

**Đáp án:** Pipeline save không tiếp tục tới bước write bình thường; caller nhận exception. Nhưng không được suy rằng các lệnh ghi khác đã thực hiện trước đó cũng rollback nếu không có transaction.

### Bài tập 16: transaction

Callback gửi email; sau đó outbox insert trong cùng transaction MongoDB thất bại. Email có được rollback không?

**Đáp án:** Không. Email không thuộc MongoDB transaction. Dùng outbox hoặc workflow sau commit và idempotency.

### Bài tập 17: reactive

Một ứng dụng chỉ đăng ký BeforeSaveCallback<CatalogProduct> đồng bộ, rồi gọi ReactiveMongoTemplate.save. Có thể mặc định callback đồng bộ sẽ được gọi không?

**Đáp án:** Không. Cần **ReactiveBeforeSaveCallback<CatalogProduct>** khi muốn cùng logic ở reactive mapping path.

### Bài tập 18: Publisher lifecycle

Trong ReactiveBeforeSaveCallback, developer tự gọi subscribe() để thực hiện thêm một update rồi return Mono.just(entity). Vấn đề?

**Đáp án:** Có subscription độc lập, dễ gây race/error/cancel không gắn với save pipeline. Đừng dùng callback để điều phối nhiều I/O không kiểm soát.

### Bài tập 19: performance

Mỗi BeforeSaveCallback gọi một HTTP API để lấy category name. Khi ghi 2.000 sản phẩm, rủi ro gì?

**Đáp án:** I/O ẩn, latency lớn, nhiều điểm lỗi và khó quản lý transaction. Chuẩn bị dữ liệu ở service hoặc denormalized read model, dùng callback cho biến đổi BSON ngắn.

### Bài tập 20: kiểm thử đúng

Unit test gọi callback trực tiếp và thấy Document được sửa. Có đủ kết luận MongoDB lưu đúng key BSON không?

**Đáp án:** Không. Cần integration test gọi MongoTemplate.insert/save, sau đó đọc **raw Document** từ collection và assert field thực.

### Bài tập 21: search metadata

Một sản phẩm được cập nhật cả qua repository.save và MongoTemplate.updateFirst. Muốn search_display luôn khớp display_name, hãy đề xuất thiết kế.

**Đáp án:** Dùng một hàm normalize chung; BeforeSaveCallback duy trì field khi entity insert/save, còn đường update phải set cả displayName/search_display hoặc dùng pipeline update phù hợp. Viết test cho cả hai con đường.

### Bài tập 22: security boundary

Callback loại bỏ field raw_access_token trong Document. Có đủ để đảm bảo không writer nào lưu field đó?

**Đáp án:** Không. Writer dùng raw driver hoặc hệ thống ngoài có thể bỏ qua callback. Tách secrets khỏi persistence model, áp policy, validation/permissions và migration dữ liệu cũ.

## 30. Checklist trước khi dùng BeforeSaveCallback trong production

- **Mục đích:** có thật sự cần thay Document sau converter hay nên dùng BeforeConvert?
- **Chữ ký:** sử dụng đúng BeforeSaveCallback<T> với org.bson.Document chưa?
- **Thời điểm:** hiểu Document đã được convert và persistent entity mutation quá muộn chưa?
- **Mapping:** đã xác nhận @Field/@Id/custom converters và tên BSON chưa?
- **Nested:** kiểm tra kiểu Document/List thực trước khi sửa chưa?
- **Null/type:** callback xử lý missing/null/kiểu BSON khác đúng chưa?
- **_id:** không thay đổi ID đã ánh xạ tùy tiện chưa?
- **_class:** không xóa type hints nếu chưa kiểm soát mapping chưa?
- **@Version:** không ghi đè version do Spring Data quản lý chưa?
- **Auditing:** có tránh trùng logic với BeforeConvert/auditing chưa?
- **Scope:** callback generic type/collection được đăng ký đúng chưa?
- **Ordering:** nhiều callbacks cùng phase có @Order rõ chưa?
- **AppEvent:** không phụ thuộc một async BeforeSaveEvent để đảm bảo mutation trước write chưa?
- **Insert/save:** mọi đường ghi entity yêu cầu callback đã được kiểm thử chưa?
- **Updates:** updateFirst/findAndModify/bulk/raw driver có chiến lược riêng chưa?
- **Derived fields:** có bảo đảm search/metadata fields không bị stale không?
- **Idempotency:** callback deterministic, không tạo side effect khi retry chưa?
- **Transaction:** không gửi HTTP/message/email trước commit trong callback chưa?
- **Security:** callback không thay validation, authorization hay unique index chưa?
- **Sensitive data:** raw BSON/log không chứa dữ liệu cấm chưa?
- **Performance:** không có blocking I/O, DB query N+1 hoặc công việc CPU lớn chưa?
- **Reactive:** dùng ReactiveBeforeSaveCallback nếu thao tác qua ReactiveMongoTemplate chưa?
- **Testing:** có unit test cho mutation lẫn integration test readback raw BSON chưa?
- **Boundary testing:** đã test callback khi collection khác, field thiếu và entity immutable chưa?
- **Regression:** đã kiểm thử thay đổi @Field/custom converters làm sai key BSON chưa?
- **Operations:** metadata/index/schema migration đồng bộ với callback chưa?

## 31. Tổng kết

1. **BeforeSaveCallback** nhận **entity Java, org.bson.Document đã chuyển đổi, tên collection** và được gọi trước khi ghi document qua entity mapping lifecycle.
2. **Thay đổi Document mới ảnh hưởng trực tiếp BSON sẽ persist**. Sửa persistent field của entity tại thời điểm BeforeSave không tự chạy conversion lại.
3. **BeforeConvertCallback** phù hợp khi muốn thay persistent entity trước khi ánh xạ; với immutable record có thể trả instance mới.
4. **@Field/@Id/custom converters** quyết định key BSON mà callback nhìn thấy; tên Java property không phải luôn là key trong Document.
5. Callback có thể thêm **search_display, write_schema** hoặc điều chỉnh nested BSON, nhưng phải có schema contract và kiểm thử raw BSON.
6. **BeforeSaveCallback không thay @Id, @Version, auditing hoặc converter**; không tự sửa các field framework quản lý tùy tiện.
7. **EntityCallbacks khác ApplicationEvents**: callbacks cung cấp thứ tự thực thi rõ trong mapping pipeline, còn event multicaster có thể được cấu hình bất đồng bộ.
8. **@Order** điều khiển thứ tự nhiều callbacks cùng phase, không làm BeforeSave chạy trước BeforeConvert.
9. **insert/save(entity)** và **query-based updateFirst/findAndModify/bulk/raw-driver writes** không có cùng lifecycle callback; derived fields phải được quản lý trên mọi write path.
10. **Transaction không biến callback thành after-commit hook**; side effect bên ngoài callback không tự rollback, callback có thể chạy lại khi retry.
11. **ReactiveBeforeSaveCallback** trả Publisher<T> và áp dụng cho reactive mapping; callback đồng bộ không tự thay thế nó.
12. **Schema validation, unique index và authorization** vẫn cần khi muốn bảo vệ dữ liệu trước mọi writer, vì callback không chạy trên mọi MongoDB command.
13. **Unit test** chứng minh logic sửa Document, còn **MongoDB integration test** chứng minh mapping và persisted BSON đúng.
14. **Đọc cả raw Document và entity sau lưu** là cách hiệu quả nhất để phát hiện sự khác biệt giữa Document đã sửa và Java object được trả về.

Hiểu rõ **BeforeSaveCallback với entity và Document đã chuyển đổi** giúp ứng dụng **SPRING_DATA_MONGODB** chọn đúng lifecycle hook, bổ sung hoặc hiệu chỉnh BSON một cách có kiểm soát và tránh lỗi dữ liệu âm thầm khi chuyển đổi entity, thao tác qua repository/MongoTemplate hoặc mở rộng sang reactive access.

### Tài liệu tham khảo

- [Spring Data MongoDB — BeforeSaveCallback API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/BeforeSaveCallback.html) — chữ ký onBeforeSave và quy tắc Document sau conversion.
- [Spring Data MongoDB — ReactiveBeforeSaveCallback API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/mapping/event/ReactiveBeforeSaveCallback.html) — Publisher<T>, Document và collection cho reactive.
- [Spring Data MongoDB — Lifecycle Events](https://docs.spring.io/spring-data/mongodb/reference/mongodb/lifecycle-events.html) — EntityCallbacks, mapping events, auditing và thứ tự lifecycle.
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html) — @Document, @Field, @Id, custom conversions.
- [Spring Data MongoDB — MongoTemplate CRUD](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html) — insert/save/updateFirst/findAndModify và auditing/version.
- [Spring Data MongoDB — Client Sessions and Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — transaction, ClientSession và reactive transaction manager.
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — bảo vệ cấu trúc dữ liệu ở database.

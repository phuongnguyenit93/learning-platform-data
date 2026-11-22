# Kiểu trả về và số document được sửa

## 1. Câu hỏi quan trọng sau một thao tác ghi

Trong chương **Ghi qua repository** của **Spring Data MongoDB**, một phương thức repository có thể trả về **entity**, **danh sách entity**, **boolean**, **số nguyên**, hoặc **không trả kết quả** (`void`). Điều dễ nhầm là kiểu trả về **không tự nói hết** số document thực sự đã bị thay đổi trên MongoDB.

Ví dụ, hệ thống bán hàng cần giải quyết các yêu cầu:

1. Lưu một sản phẩm và trả lại sản phẩm đã được Spring Data ánh xạ.
2. Lưu một nhóm sản phẩm và biết đã xử lý các entity nào.
3. Đổi trạng thái từ `PENDING` sang `ACTIVE` cho những sản phẩm thuộc một tenant.
4. Xóa các sản phẩm đã bị đánh dấu `DELETED` và báo số document đã xóa.
5. Phân biệt **không có document phù hợp**, **có document nhưng giá trị không đổi**, và **ghi thành công vào document**.

Các yêu cầu trên không có cùng câu trả lời. `save(...)` trả về entity đã lưu; `saveAll(...)` trả một iterable các entity; `deleteById(...)` thường trả `void`; một **derived delete query** có thể trả `long`; còn một phương thức có `@Update` có thể trả số document được update. Khi cần biết chi tiết **matched/modified/upserted**, `MongoTemplate` với `UpdateResult` thường là lựa chọn trực tiếp hơn.

### Mục tiêu bài học

- Đọc đúng hợp đồng kiểu trả về của các thao tác ghi qua repository.
- Phân biệt **entity được trả về**, **số document tìm thấy**, **số document thực sự thay đổi** và **số document bị xóa**.
- Dùng derived delete, `@Update`, `MongoRepository.save/saveAll` và `MongoTemplate` đúng mục đích.
- Thiết kế API trả kết quả ghi rõ ràng, không suy diễn thành công từ `void` hoặc một số đếm không phù hợp.
- Hiểu tác động của version, concurrent writes, no-op update, upsert, tenant và idempotency.
- Kiểm thử kết quả trên MongoDB thật để phát hiện sai lệch do mapping và cách thực thi.

> Ngữ cảnh: Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x. Các API repository và hành vi khi lỗi có thể khác theo phiên bản; khi cần một bảo đảm chính xác về số liệu, hãy kiểm thử đường ghi và quan sát MongoDB command/result trên phiên bản triển khai.

## 2. Bảng tổng quan: kiểu trả về không đồng nghĩa kiểu đếm

| API/phương thức | Kiểu trả về thường dùng | Ý nghĩa chính | Có trả số document bị thay đổi? |
|---|---|---|---|
| `repository.save(entity)` | `S extends T` | Entity sau thao tác lưu | **Không** |
| `repository.saveAll(entities)` | `Iterable<S>` hoặc kiểu cụ thể hơn | Các entity sau khi lưu | **Không trực tiếp** |
| `repository.deleteById(id)` | `void` | Yêu cầu xóa theo ID | **Không** |
| `repository.delete(entity)` | `void` | Yêu cầu xóa entity | **Không** |
| `repository.deleteAll(...)` | `void` | Yêu cầu xóa nhiều entity | **Không** |
| Derived `long deleteByStatus(status)` | `long` | Số document bị xóa theo query | **Có, theo semantics delete** |
| Derived `List<T> removeByStatus(status)` | `List<T>` | Các entity bị chọn để xóa | **Trả entity, không phải số đếm** |
| Repository method có `@Update` | `void` hoặc `long/Long` | Thực hiện update theo query | **Có thể trả số cập nhật** |
| `mongo.updateFirst/updateMulti` | `UpdateResult` | Kết quả cập nhật MongoDB | **Có cả matched/modified** |
| `mongo.remove(query, Type.class)` | `DeleteResult` | Kết quả xóa theo query | **Có `deletedCount`** |
| `mongo.findAndModify(...)` | Entity hoặc `null` | Tìm và sửa một document nguyên tử | **Trả document, không phải count** |

Trong bảng, “số document cập nhật” của repository `@Update` phải được hiểu theo **hợp đồng của API/phiên bản**, thay vì tự động coi là số bản ghi khớp filter. Khi nghiệp vụ cần đồng thời `matchedCount` và `modifiedCount`, nên lấy kết quả mức MongoDB qua `MongoTemplate`.

**Điểm phân biệt đầu tiên:** một thao tác trả lại **một entity** không chứng minh chỉ có một document liên quan đến tất cả công việc khác trong request; và một thao tác trả `void` không có nghĩa “0 document bị sửa”.

## 3. Định nghĩa bốn loại số liệu và hai loại kết quả

Một câu lệnh cập nhật MongoDB có thể tạo ra các số liệu sau:

| Khái niệm | Tên API điển hình | Cách diễn giải |
|---|---|---|
**Matched** | `UpdateResult.getMatchedCount()` | Có bao nhiêu document thỏa điều kiện của lệnh update |
**Modified** | `UpdateResult.getModifiedCount()` | Có bao nhiêu document thực sự thay đổi do update |
**Upserted** | `UpdateResult.getUpsertedId()` | ID mới được tạo khi upsert, nếu có |
**Deleted** | `DeleteResult.getDeletedCount()` | Có bao nhiêu document thực sự bị xóa |
**Saved entity** | Kết quả `save(...)` | Object Java được trả về sau lưu, không phải số đếm |
**Saved entities** | Kết quả `saveAll(...)` | Iterable của các object Java sau lưu, không bảo đảm số liệu ở cấp command |

Ví dụ có ba document với `status = ACTIVE`. Gọi:

~~~javascript
db.catalog_products.updateMany(
  { tenantId: "tenant-a", status: "ACTIVE" },
  { $set: { status: "ACTIVE" } }
);
~~~

Giả sử không có field khác bị thay đổi, có thể nhận:

~~~text
matchedCount  = 3
modifiedCount = 0
~~~

MongoDB **tìm thấy ba document**, nhưng gán lại đúng giá trị cũ nên **không có document nào thay đổi**. Không nên coi `modifiedCount = 0` đồng nghĩa “không tồn tại document” hoặc “query bị lỗi”.

Một ví dụ khác:

~~~javascript
db.catalog_products.updateMany(
  { tenantId: "tenant-a", status: "PENDING" },
  { $set: { status: "ACTIVE" } }
);
~~~

Nếu hai document đang `PENDING` và cập nhật thành công, `matchedCount` và `modifiedCount` có thể cùng bằng 2. Nhưng các số liệu đó chỉ phản ánh **lệnh đã thực hiện**, không nói rõ API có gửi email, ghi audit event hoặc hoàn tất toàn bộ quy trình nghiệp vụ hay chưa.

**Số document** khác với **số thao tác được gửi**. Một `updateMulti` là một lệnh có thể sửa nhiều document; một bulk plan có 10 write models không bảo đảm 10 document được sửa.

## 4. Entity và repository mẫu

Các ví dụ dùng collection `catalog_products`. Một sản phẩm thuộc đúng một tenant; tên và số lượng tồn kho có tên field BSON khác property Java để minh họa Spring Data mapping.

**CatalogProduct.java**

~~~java
package com.example.catalog;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "catalog_products")
public class CatalogProduct {
    @MongoId(FieldType.STRING)
    private String id;

    private String tenantId;
    private String sku;

    @Field("display_name")
    private String name;

    @Field("stock_qty")
    private long stock;

    private String status;

    protected CatalogProduct() {
        // Dành cho Spring Data materialization.
    }

    public CatalogProduct(
            String id, String tenantId, String sku,
            String name, long stock, String status) {
        this.id = id;
        this.tenantId = tenantId;
        this.sku = sku;
        this.name = name;
        this.stock = stock;
        this.status = status;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getSku() { return sku; }
    public String getName() { return name; }
    public long getStock() { return stock; }
    public String getStatus() { return status; }

    public void setName(String name) { this.name = name; }
    public void setStock(long stock) { this.stock = stock; }
    public void setStatus(String status) { this.status = status; }
}
~~~

`@MongoId(FieldType.STRING)` cố định BSON type của `_id` là String. `@Field("stock_qty")` đổi tên property `stock` thành `stock_qty`, còn `name` thành `display_name`. Các truy vấn typed dùng `CatalogProduct.class` có thể viết theo property Java; raw MongoDB shell hoặc raw driver phải dùng tên BSON.

Một document:

~~~json
{
  "_id": "p-101",
  "tenantId": "tenant-a",
  "sku": "BOTTLE-500",
  "display_name": "Bình nước 500 ml",
  "stock_qty": 12,
  "status": "PENDING"
}
~~~

**CatalogProductRepository.java**

~~~java
package com.example.catalog;

import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;
import org.springframework.data.mongodb.repository.Update;

public interface CatalogProductRepository
        extends MongoRepository<CatalogProduct, String> {

    // Derived delete: trả số document đã bị xóa.
    long deleteByTenantIdAndStatus(String tenantId, String status);

    // Derived delete: trả các entity được chọn để xóa.
    List<CatalogProduct> removeByTenantIdAndStatus(
            String tenantId, String status);

    // Repository update: query chọn các document, update sửa chúng.
    @Query("{ 'tenantId': ?0, 'status': ?1 }")
    @Update("{ '$set': { 'status': ?2 } }")
    long changeStatus(
            String tenantId, String previousStatus, String nextStatus);
}
~~~

Ở ví dụ này, `@Update` có import `org.springframework.data.mongodb.repository.Update`, **khác** class `org.springframework.data.mongodb.core.query.Update` dùng cùng `MongoTemplate`. Hai kiểu trùng tên nhưng có chức năng khác nhau; cần chú ý import.

Phương thức `changeStatus` dùng `@Query` để chỉ định filter, vì tên `changeStatus` tự nó không phải tên phương thức suy diễn kiểu `findBy...`. Placeholder `?0`, `?1`, `?2` được bind theo thứ tự tham số.

## 5. save: trả entity, không trả số document đã sửa

`MongoRepository.save(S entity)` có kiểu trả về:

~~~java
<S extends T> S save(S entity);
~~~

Khi tạo mới:

~~~java
CatalogProduct created = products.save(new CatalogProduct(
        "p-101", "tenant-a", "BOTTLE-500",
        "Bình nước 500 ml", 12, "PENDING"));

String id = created.getId();
~~~

Trong ví dụ, `products` là bean `CatalogProductRepository`. Kết quả `created` là **entity sau khi lưu**, không phải giá trị `1` biểu thị một document được insert.

### 5.1. Vì sao trả entity lại hữu ích?

- ID có thể được sinh hoặc điền sau thao tác lưu tùy kiểu khóa và mapping.
- Một số metadata được framework thiết lập trong quá trình lưu, ví dụ version hoặc auditing khi cấu hình phù hợp.
- Service có thể xây DTO response từ object đã được trả.
- Contract trở nên rõ ràng hơn việc gọi `save` rồi bỏ qua kết quả khi ứng dụng cần ID.

Tuy nhiên, **entity trả về không mặc nhiên là snapshot bất biến** của MongoDB cho mọi trường hợp cạnh tranh. Một request khác có thể cập nhật document sau khi `save` hoàn thành. Đừng dùng object trả về để suy ra trạng thái sẽ mãi không thay đổi.

### 5.2. Save có thể insert hoặc lưu lại document hiện hữu

~~~java
CatalogProduct existing = products.findById("p-101")
        .orElseThrow();
existing.setName("Bình giữ nhiệt 500 ml");

CatalogProduct saved = products.save(existing);
~~~

Kết quả vẫn là `CatalogProduct`, không phải số document modified. Với entity chưa khai báo `@Version` như ở mục 4, việc lưu trạng thái cũ có thể **ghi đè** thay đổi của request khác; `save` không diễn đạt rõ “chỉ sửa field `name`”.

Không nên tạo object chỉ chứa ID và tên rồi gọi `save` để cập nhật một field. Nếu quá trình save thay thế document, các field khác có thể bị mất hoặc mang giá trị mặc định. Dùng lệnh cập nhật có điều kiện khi mục tiêu chỉ thay đổi một phần document.

### 5.3. Nếu cần biết một document có thay đổi không?

`save` không trả `matchedCount` hoặc `modifiedCount`. Khi nghiệp vụ cần phân biệt:

- Không có ID nào phù hợp;
- Có ID nhưng giá trị đã là giá trị mong muốn;
- Có ID và field thực sự thay đổi;

hãy chuyển sang `MongoTemplate.updateFirst(...)` nhận `UpdateResult`, hoặc dùng thiết kế response riêng dựa trên kết quả write đã được xác minh. **Không kiểm tra `save(...) != null` rồi coi đó là “một document đã thay đổi”.**

## 6. saveAll: trả tập entity, không phải báo cáo modifiedCount

`saveAll(Iterable<S> entities)` trả về một `Iterable<S>` hoặc kiểu cụ thể hơn tùy interface/implementation. Ví dụ:

~~~java
List<CatalogProduct> input = List.of(
        new CatalogProduct("p-201", "tenant-a", "SKU-201",
                "Cốc sứ", 20, "PENDING"),
        new CatalogProduct("p-202", "tenant-a", "SKU-202",
                "Sổ tay", 15, "PENDING"));

Iterable<CatalogProduct> result = products.saveAll(input);
~~~

Đây là tập entity được trả về sau khi gọi lưu. **Kích thước iterable không phải `modifiedCount`**:

- Trong tập có thể có entity mới và entity đã tồn tại.
- Có thể có entity được save dù giá trị không đổi.
- `saveAll` không có hợp đồng trả một tổng số MongoDB matches/modifieds.
- Một lỗi giữa quá trình lưu có thể khiến một số document đã được ghi trước khi exception xuất hiện, trừ khi có transaction phù hợp.
- Implementation có thể tối ưu khi toàn bộ entity là mới hoặc thực hiện nhiều save riêng khi có entity hiện hữu; không mặc định mỗi call luôn phát một MongoDB bulk command.

Nếu cần cập nhật hàng nghìn document với những điều kiện khác nhau và thu nhận thống kê write tổng hợp, cân nhắc `BulkOperations` hoặc chia thành các phép cập nhật có điều kiện. Nhưng **`BulkWriteResult` cũng không phải danh sách kết quả chi tiết theo ID**; cần thiết kế đối soát khi nghiệp vụ đòi hỏi phản hồi từng item.

### 6.1. Không suy ra count từ số input

~~~java
int requested = input.size();
Iterable<CatalogProduct> returned = products.saveAll(input);

// requested là số object gửi vào, KHÔNG phải số document thực sự modified.
~~~

Với 100 object, không thể khẳng định 100 document đã thay đổi chỉ vì `requested = 100` và method trả về bình thường. Ngoài ra, nếu một số object có cùng ID, chính sách xử lý trùng, version và thứ tự lưu cũng ảnh hưởng kết quả.

## 7. deleteById/delete/deleteAll trả void: không biết deletedCount

Các thao tác kế thừa từ `CrudRepository`/`MongoRepository` như:

~~~java
products.deleteById("p-101");
products.delete(existing);
products.deleteAll();
~~~

thường có kiểu trả về `void`. Caller không nhận trực tiếp số document đã xóa:

- `deleteById("p-101")` không trả về 1 hay 0 cho biết ID có thực sự tồn tại.
- `delete(existing)` không trả tổng số document xóa.
- `deleteAll()` không trả tổng số document bị xóa từ collection.

Không thể dùng:

~~~java
// Không hợp lệ: deleteById trả void.
long deleted = products.deleteById("p-101");
~~~

Một lời gọi `deleteById` hoàn thành mà không ném lỗi **không đồng nghĩa** với việc document có tồn tại trước đó. Các đường xóa khác nhau có thể có xử lý version/lifecycle khác nhau; khi dùng `@Version`, cần kiểm tra rõ xóa bằng **entity đã đọc** và xóa **chỉ theo ID**. Trong Spring Data MongoDB, xóa theo ID có thể bỏ qua kiểm soát optimistic locking mà xóa entity theo phiên bản có thể áp dụng.

### 7.1. Đừng thêm existsById chỉ để đo số xóa

Mẫu sau **không đáng tin khi chạy đồng thời**:

~~~java
boolean existed = products.existsById("p-101");
products.deleteById("p-101");

// existed chỉ phản ánh lần đọc trước đó, không phải deletedCount.
~~~

Một request khác có thể xóa document giữa hai thao tác. Nếu cần trả số document thực sự bị xóa bởi **chính lệnh xóa**, dùng derived delete trả count hoặc `MongoTemplate.remove(...)` nhận `DeleteResult`. Không suy diễn count từ phép đọc xảy ra trước.

## 8. Derived delete query: chọn count hay entity bị xóa

Spring Data MongoDB cho phép suy diễn thao tác xóa từ tên phương thức như `deleteBy...` hoặc `removeBy...`. **Kiểu trả về** quyết định cách ứng dụng nhận kết quả.

### 8.1. Trả số document đã xóa

Repository:

~~~java
long deleteByTenantIdAndStatus(String tenantId, String status);
~~~

Service:

~~~java
package com.example.catalog;

import org.springframework.stereotype.Service;

@Service
public class CatalogCleanupService {
    private final CatalogProductRepository products;

    public CatalogCleanupService(CatalogProductRepository products) {
        this.products = products;
    }

    public long purgeDeleted(String tenantId) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("tenantId không hợp lệ");
        }
        return products.deleteByTenantIdAndStatus(tenantId, "DELETED");
    }
}
~~~

Giá trị trả về diễn đạt **số document bị xóa theo query**, không phải số lần gọi API hay số entity đã truyền từ client. Một kết quả `0` có thể đơn giản nghĩa là không có bản ghi `DELETED` nào phù hợp tại thời điểm lệnh thực thi.

### 8.2. Trả lại các entity bị chọn để xóa

Repository cũng có thể khai báo:

~~~java
List<CatalogProduct> removeByTenantIdAndStatus(
        String tenantId, String status);
~~~

Hình thức này phục vụ những trường hợp cần **dữ liệu của các entity được chọn để xóa** cho xử lý tiếp theo. Tuy nhiên, việc trả entity có thể yêu cầu đọc/materialize các document trước khi xóa, không phải chỉ trả một `deletedCount` rẻ.

Hệ quả:

- Với hàng chục nghìn document, giữ toàn bộ entity trong `List` có thể tốn bộ nhớ và tăng round trip.
- Khoảng thời gian giữa đọc dữ liệu để trả về và thao tác xóa có thể có thay đổi cạnh tranh; **đừng coi danh sách entity trả về là audit log atomically consistent trong mọi tình huống**.
- Nếu cần bản ghi lịch sử không thể mất, hãy thiết kế audit/outbox hoặc transaction phù hợp, không mặc định “trả entity bị xóa” là chứng từ bền vững.
- Nếu chỉ cần số xóa, chọn kiểu `long` thay vì cố lấy danh sách rồi gọi `size()`.

**Lưu ý cú pháp:** `deleteBy` và `removeBy` có vai trò tương tự trong tên query, nhưng return type làm thay đổi việc caller nhìn thấy số đếm hay entity. Hãy xác minh đặc tả của phiên bản Spring Data đang dùng, nhất là khi kết hợp projection/custom query.

## 9. @Update trên repository: trả void hoặc số document cập nhật

Khác với các thao tác CRUD mặc định chỉ cung cấp entity hoặc void, Spring Data MongoDB hỗ trợ **repository update methods** với annotation `@Update`.

Ví dụ đã khai báo:

~~~java
@Query("{ 'tenantId': ?0, 'status': ?1 }")
@Update("{ '$set': { 'status': ?2 } }")
long changeStatus(
        String tenantId, String previousStatus, String nextStatus);
~~~

Nếu có ba sản phẩm `PENDING` của `tenant-a`, lời gọi:

~~~java
long updated =
        products.changeStatus("tenant-a", "PENDING", "ACTIVE");
~~~

trả số document cập nhật theo hợp đồng `@Update` của framework; trong cách triển khai thông dụng của Spring Data MongoDB 4.x, kiểu `long` phản ánh **số document đã được sửa**, không phải một collection các entity mới.

### 9.1. @Update có thể sửa nhiều document

Trong repository MongoDB, `@Update` mô tả một cập nhật áp dụng cho **các document phù hợp với query**, không tự giới hạn chỉ một document vì tên method dùng số ít. Cần hiểu nó theo semantics **multi-update** của API, và phải lọc cẩn thận:

~~~javascript
db.catalog_products.updateMany(
  { tenantId: "tenant-a", status: "PENDING" },
  { $set: { status: "ACTIVE" } }
);
~~~

Nếu filter chỉ có `status = "PENDING"` nhưng ứng dụng có nhiều tenant, lệnh có thể cập nhật **sản phẩm của mọi tenant**. Điều kiện tenant/quyền phải đặt trong query của lệnh ghi, không chỉ kiểm tra sau đó.

### 9.2. Vì sao return long của @Update chưa đủ trong mọi trường hợp?

Với một giá trị gán không đổi, có thể xảy ra:

~~~text
Filter khớp:      3 document
Giá trị muốn gán: status = "ACTIVE"
Giá trị đang có:  "ACTIVE" cho cả 3 document

matchedCount  = 3
modifiedCount = 0
~~~

Vì vậy cần xác định **con số API đang báo là loại nào**. `@Update` giúp biết số cập nhật theo contract của nó, nhưng không cung cấp song song hai field `matchedCount` và `modifiedCount` trên một object như `UpdateResult`. Nếu cần phân biệt “khớp nhưng không thay đổi”, dùng `MongoTemplate` ở mục 10.

### 9.3. Chữ ký trả void cũng hợp lệ cho thao tác không cần count

Ví dụ một phương thức repository:

~~~java
@Query("{ 'tenantId': ?0, 'status': ?1 }")
@Update("{ '$set': { 'status': ?2 } }")
void changeStatusWithoutCount(
        String tenantId, String previousStatus, String nextStatus);
~~~

Đoạn này được đặt **bên trong cùng repository interface**, không phải method Java độc lập. Trả `void` phù hợp nếu caller không cần biết số document bị tác động, nhưng có thể che đi các lỗi nghiệp vụ kiểu “không có bản ghi nào ở trạng thái kỳ vọng”.

Trong luồng yêu cầu xác nhận/chuyển trạng thái, ưu tiên return count hoặc dùng `UpdateResult` để phân loại kết quả thay vì chỉ gọi method `void` rồi báo thành công vô điều kiện.

### 9.4. @Update không trả entity đã thay đổi

Đừng khai báo `CatalogProduct` hoặc `List<CatalogProduct>` làm kiểu trả về của method `@Update` rồi kỳ vọng framework thực hiện update và trả post-image của tất cả document. Những nhu cầu khác nhau cần API khác:

- Cần **số document cập nhật**: `@Update` trả `long` hoặc `MongoTemplate.update...`.
- Cần **một entity sau cập nhật nguyên tử**: `MongoTemplate.findAndModify(...)` với `FindAndModifyOptions.returnNew(true)`.
- Cần **danh sách entity sau cập nhật**: phải thiết kế bước đọc bổ sung, và hiểu rằng tập dữ liệu có thể thay đổi giữa update và read nếu không có bảo đảm thích hợp.
- Cần **báo cáo cập nhật theo từng item**: lưu operation ID hoặc đối soát theo khóa; một tổng count không đủ.

## 10. MongoTemplate.UpdateResult: phân biệt matchedCount và modifiedCount

Khi nghiệp vụ cần câu trả lời đầy đủ hơn từ MongoDB, `MongoTemplate` nhận `Query` và `Update` rồi trả `UpdateResult`.

**CatalogUpdateService.java**

~~~java
package com.example.catalog;

import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class CatalogUpdateService {
    private final MongoTemplate mongo;

    public CatalogUpdateService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public UpdateResult activatePending(String tenantId) {
        Query filter = Query.query(
                Criteria.where("tenantId").is(tenantId)
                        .and("status").is("PENDING"));

        Update update = new Update().set("status", "ACTIVE");
        return mongo.updateMulti(filter, update, CatalogProduct.class);
    }

    public UpdateResult renameProduct(
            String tenantId, String id, String name) {
        Query filter = Query.query(
                Criteria.where("id").is(id)
                        .and("tenantId").is(tenantId));
        return mongo.updateFirst(
                filter, new Update().set("name", name),
                CatalogProduct.class);
    }
}
~~~

`mongo.updateMulti(...)` có thể cập nhật nhiều document; `updateFirst(...)` cập nhật tối đa một document phù hợp. Trong ví dụ `renameProduct`, Spring Data ánh xạ `Criteria.where("id")` sang BSON `_id` và `Update.set("name", ...)` sang `display_name` khi xử lý `CatalogProduct.class`.

Đọc kết quả:

~~~java
UpdateResult result =
        catalogUpdateService.activatePending("tenant-a");

long matched = result.getMatchedCount();
long modified = result.getModifiedCount();
~~~

### 10.1. Diễn giải theo từng tổ hợp

| Matched | Modified | Ý nghĩa có thể có | Hành động tiếp theo |
|---:|---:|---|---|
0 | 0 | Không document nào phù hợp filter | Kiểm tra ID/tenant/trạng thái kỳ vọng nếu cần phân biệt |
1 | 1 | Một document khớp và đã thay đổi | Có thể trả thành công theo contract |
1 | 0 | Document khớp nhưng không cần đổi giá trị | Có thể trả “không thay đổi”, không nhất thiết lỗi |
5 | 3 | Năm document khớp, ba document thực sự thay đổi | Phải hiểu query/update và các field được đặt |

Không phải mọi tổ hợp đều xuất hiện trong cùng một use case. Ví dụ filter `status = PENDING` rồi set `status = ACTIVE` thường khiến mỗi document khớp thay đổi trạng thái, nếu không có yếu tố đặc biệt. Ngược lại, lọc theo tenant rồi set trạng thái sẵn có dễ có `matchedCount > modifiedCount`.

Nếu write concern là **unacknowledged**, khả năng lấy các số liệu chi tiết có thể bị hạn chế hoặc API có thể không cung cấp counts đáng tin cậy. Hệ thống cần báo count chính xác phải thiết kế write concern phù hợp; không tắt acknowledgement chỉ để tăng throughput rồi vẫn hứa số cập nhật chính xác.

### 10.2. Sửa field bằng giá trị đã có

~~~java
Query allActive = Query.query(
        Criteria.where("tenantId").is("tenant-a")
                .and("status").is("ACTIVE"));

Update sameValue = new Update().set("status", "ACTIVE");

UpdateResult result = mongo.updateMulti(
        allActive, sameValue, CatalogProduct.class);
~~~

Giả sử ba document thuộc tenant đã `ACTIVE` và entity không có cơ chế ghi bổ sung làm thay field khác, kết quả dự kiến là **matched = 3, modified = 0**. Đây là ví dụ tốt để tránh gộp hai khái niệm vào cùng từ “updated”.

### 10.3. Tìm-and-sửa một document, lấy post-image

Nếu client cần object sau khi chỉnh, không chỉ con số:

~~~java
import org.springframework.data.mongodb.core.FindAndModifyOptions;

Query filter = Query.query(
        Criteria.where("id").is("p-101")
                .and("tenantId").is("tenant-a"));

CatalogProduct after = mongo.findAndModify(
        filter,
        new Update().set("name", "Tên mới"),
        FindAndModifyOptions.options().returnNew(true),
        CatalogProduct.class);
~~~

`after` có thể là `null` khi không có document khớp. Vì vậy cần xử lý null và trả response phù hợp. `findAndModify` là thao tác nguyên tử cho một document, nhưng **không tự tạo một số đếm cho toàn bộ tập kết quả**.

## 11. DeleteResult: số document bị xóa là số khác với modifiedCount

Với thao tác xóa tường minh trong template:

~~~java
import com.mongodb.client.result.DeleteResult;

Query deletedItems = Query.query(
        Criteria.where("tenantId").is("tenant-a")
                .and("status").is("DELETED"));

DeleteResult result = mongo.remove(
        deletedItems, CatalogProduct.class);

long deleted = result.getDeletedCount();
~~~

`deletedCount` là số document xóa thực tế theo lệnh, **không phải** số document được sửa field. Một phép soft-delete:

~~~java
UpdateResult softDeleted = mongo.updateMulti(
        Query.query(Criteria.where("tenantId").is("tenant-a")
                .and("status").ne("DELETED")),
        new Update().set("status", "DELETED"),
        CatalogProduct.class);
~~~

đổi một field trong document; nó là **update**, không phải physical delete, nên sử dụng `matchedCount/modifiedCount` chứ không phải `deletedCount`.

Chính sách khi xóa cũng quan trọng: nếu những document khác tham chiếu đến sản phẩm, xóa không tự thực thi foreign-key cascade. Khi cần audit, soft-delete, TTL hoặc đối soát quan hệ, đừng dựa vào số `deletedCount` như bằng chứng toàn bộ ràng buộc nghiệp vụ đã được thỏa.

## 12. Đừng dùng repository.count() để đo số cập nhật

`repository.count()` trả về **số document hiện có** trong collection theo semantics của repository, không phải số document được thay đổi bởi lệnh gần nhất.

Ví dụ:

~~~java
long before = products.count();
products.changeStatus("tenant-a", "PENDING", "ACTIVE");
long after = products.count();
long difference = after - before;
~~~

Kết quả `difference = 0` vẫn hoàn toàn hợp lý dù 100 document đã đổi `status`; tổng số document không đổi khi chỉ cập nhật một field.

Ngay cả nếu đếm theo trạng thái:

~~~java
long pendingBefore = /* query count theo trạng thái PENDING */;
// Thực hiện cập nhật ...
long pendingAfter = /* query count lần nữa */;
~~~

hiệu số **không chắc là số document mà chính request đã sửa** khi có request khác đồng thời insert, delete hoặc đổi trạng thái. Đây là vấn đề *time-of-check/time-of-use* và ranh giới quan sát của các lần đọc.

Đo kết quả bằng **return count từ thao tác ghi** hoặc **MongoDB write result**, không suy diễn từ hai truy vấn đếm trước/sau. Với quy trình nhiều bước, lưu operation ID và log/audit nghiệp vụ phù hợp nếu cần đối soát.

## 13. Concurrency: count không thay thế điều kiện ghi

Giả sử một lệnh giảm tồn kho phải thỏa:

\[
\text{stock}_{\text{before}} \ge \text{quantityToSell}.
\]

Không nên:

~~~java
CatalogProduct product = products.findById("p-101").orElseThrow();
if (product.getStock() >= 3) {
    product.setStock(product.getStock() - 3);
    products.save(product);
}
~~~

Hai request có thể cùng đọc `stock = 5`, cùng trừ 3 và cuối cùng ghi lại `stock = 2`; hệ thống đã chấp nhận hai đơn nhưng chỉ trừ một lần. **Return entity từ `save` không phát hiện lỗi này** khi không có cơ chế khóa/version.

### 13.1. Cập nhật có điều kiện trong MongoTemplate

~~~java
package com.example.catalog;

import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public class StockWriteService {
    private final MongoTemplate mongo;

    public StockWriteService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public boolean deduct(
            String tenantId, String id, long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount phải dương");
        }

        Query filter = Query.query(
                Criteria.where("id").is(id)
                        .and("tenantId").is(tenantId)
                        .and("stock").gte(amount));

        UpdateResult result = mongo.updateFirst(
                filter,
                new Update().inc("stock", -amount),
                CatalogProduct.class);

        return result.getMatchedCount() == 1;
    }
}
~~~

MongoDB đánh giá **điều kiện đủ hàng** và thực hiện `$inc` trên **cùng một document** trong một thao tác nguyên tử. Hai request không thể đồng thời trừ mỗi lần 3 từ stock 5 mà cả hai cùng khớp điều kiện trên cùng document. Với một phép `inc` khác 0, document khớp sẽ được sửa, nhưng API vẫn nên dựa trên semantics của kết quả cần báo.

`matchedCount == 0` có thể nghĩa là ID không tồn tại, sai tenant hoặc không đủ hàng. Nếu client cần phân biệt chính xác, có thể đọc bổ sung **sau** lệnh ghi để giải thích, không dùng lần đọc đó để bảo vệ lệnh đã thực hiện.

### 13.2. Optimistic locking với @Version

Với entity có `@Version`, repository `save` có thể phát hiện khi object đã bị thay đổi kể từ lần đọc:

~~~java
package com.example.catalog;

import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "versioned_products")
public class VersionedProduct {
    @MongoId(FieldType.STRING)
    private String id;
    private String name;
    @Version
    private Long version;

    protected VersionedProduct() {}

    public VersionedProduct(String id, String name) {
        this.id = id;
        this.name = name;
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public Long getVersion() { return version; }
    public void setName(String name) { this.name = name; }
}
~~~

Service/test minh họa:

~~~java
VersionedProduct saved =
        mongo.insert(new VersionedProduct("v-101", "Ban đầu"));

VersionedProduct a =
        mongo.findById("v-101", VersionedProduct.class);
VersionedProduct b =
        mongo.findById("v-101", VersionedProduct.class);

a.setName("Request A");
mongo.save(a);

b.setName("Request B");
// Với optimistic locking và acknowledged write, save này
// có thể ném OptimisticLockingFailureException do version cũ.
mongo.save(b);
~~~

Phải chọn acknowledged write concern và dùng các đường ghi tôn trọng version. Lệnh update tùy chỉnh hoặc raw driver có thể bỏ qua kiểm tra version nếu không đặt điều kiện tường minh. `@Update` trên repository không tự biến mọi cập nhật thành compare-and-set theo version từ DTO của client.

**Ý nghĩa return type:** `save` vẫn trả một entity khi thành công hoặc ném exception khi vi phạm optimistic locking; nó **không đổi thành `boolean`** cho biết version có hợp lệ hay không. Tầng service phải chuyển exception thành response xung đột hoặc retry có kiểm soát.

## 14. Upsert và bulk: một số tổng hợp có thể che chi tiết

### 14.1. Upsert có thể tạo mới thay vì sửa

`MongoTemplate.upsert(query, update, Type.class)` yêu cầu MongoDB cập nhật nếu có document khớp, ngược lại có thể tạo document mới.

~~~java
Query byBusinessKey = Query.query(
        Criteria.where("tenantId").is("tenant-a")
                .and("sku").is("BOTTLE-500"));

Update update = new Update()
        .set("name", "Bình nước")
        .setOnInsert("status", "PENDING");

UpdateResult result = mongo.upsert(
        byBusinessKey, update, CatalogProduct.class);
~~~

Nếu update khớp document hiện có, `matchedCount` có thể bằng 1; nếu **tạo mới** do upsert, `getUpsertedId()` cho biết ID được tạo theo kết quả driver. Trong trường hợp upsert tạo mới, **không được gộp `upserted = 1` vào `modifiedCount`** rồi gọi đó là một document “đã sửa”.

Với model dùng `@MongoId(FieldType.STRING)`, cần thiết kế chính sách ID thật rõ: khi upsert theo (`tenantId`, `sku`) mà chưa cung cấp `_id`, MongoDB có thể sinh một ID BSON ObjectId. Điều này có thể mâu thuẫn với yêu cầu ID String của entity. Trong production cần xác định khóa ổn định, unique index và cách tạo ID đúng schema trước khi triển khai upsert hàng loạt.

### 14.2. BulkWriteResult tổng hợp nhiều lệnh

Nếu ứng dụng dùng `MongoTemplate.bulkOps(...)`, `execute()` trả `BulkWriteResult` trong đường thành công. Một batch có thể gồm 2 insert, 3 update và 1 delete. Số liệu tổng hợp gồm:

~~~java
int inserted = result.getInsertedCount();
int matched = result.getMatchedCount();
int modified = result.getModifiedCount();
int deleted = result.getDeletedCount();
int upserted = result.getUpserts().size();
~~~

Đây là ví dụ có sẵn biến `result` kiểu `com.mongodb.bulk.BulkWriteResult`, không phải code tạo bulk đầy đủ. Các số này không tự nói **document ID nào** thất bại hoặc không khớp. Với partial success, exception có thể được ném thay vì có một kết quả success đầy đủ.

Không retry toàn bộ một batch `$inc` sau timeout mà không có idempotency, vì những item đã được cập nhật trước đó có thể bị cộng/trừ hai lần. Nếu nghiệp vụ cần báo kết quả theo từng item, hãy dùng ID sự kiện, checkpoint, đối soát và retry có điều kiện.

## 15. Trình bày kết quả ghi ở tầng API

Trong REST API, tránh trả số MongoDB raw mà không định nghĩa ý nghĩa. Ví dụ một response có thể công bố:

~~~json
{
  "requestedStatus": "ACTIVE",
  "matchedDocuments": 12,
  "modifiedDocuments": 10
}
~~~

Tuy nhiên, response trên chỉ phù hợp khi service **thực sự có cả matched và modified** từ `UpdateResult`; không nên tự bịa `matchedDocuments` từ giá trị `long` của repository `@Update`.

Một DTO rõ ràng:

~~~java
package com.example.catalog;

public record WriteSummary(
        long matchedDocuments,
        long modifiedDocuments) {
}
~~~

Service xây response:

~~~java
public WriteSummary activate(String tenantId) {
    UpdateResult result = catalogUpdateService.activatePending(tenantId);
    return new WriteSummary(
            result.getMatchedCount(),
            result.getModifiedCount());
}
~~~

Đoạn này minh họa phương thức trong service có bean `catalogUpdateService` kiểu `CatalogUpdateService` đã định nghĩa ở mục 10. DTO không chứa ID hoặc chi tiết document nếu endpoint chỉ cần thống kê.

### 15.1. Phân biệt kết quả kỹ thuật và kết quả nghiệp vụ

| Thông tin | Có thể kết luận từ write result? |
|---|---|
Một document khớp filter | Có, từ matchedCount khi acknowledged |
Một document bị thay đổi giá trị | Có, từ modifiedCount khi được hỗ trợ |
Document mới được upsert | Có, từ upsertedId |
Bao nhiêu document bị xóa | Có, từ deletedCount |
Đã gửi email xác nhận thành công | **Không** |
Đã hoàn tất transaction nhiều collection | **Không**, nếu chỉ có write result đơn lẻ |
Không còn request nào có thể sửa document | **Không** |
Client sẽ luôn thấy ngay dữ liệu mới trên mọi replica | **Không**, phụ thuộc read preference/consistency |

Một backend nên đặt tên field API theo đúng semantics. Ví dụ `modifiedDocuments` không nên được đặt tên `processedOrders` nếu một đơn hàng phải qua nhiều bước ngoài MongoDB.

### 15.2. Trả 0 có thể vẫn là kết quả hợp lệ

Một request “đưa tất cả sản phẩm `PENDING` thành `ACTIVE`” được gọi lại có thể trả `0`, vì không còn document ở trạng thái `PENDING`. Điều đó có thể là **idempotent success** theo contract nghiệp vụ, không nhất thiết HTTP 404 hoặc 409.

Ngược lại, request “xác nhận đúng một đơn hàng theo ID và version kỳ vọng” mà không khớp document nào có thể cần trả **409 Conflict** hoặc **404 Not Found** tùy khả năng xác định nguyên nhân và chính sách bảo mật. Không có một mapping HTTP mặc định phù hợp cho mọi count bằng 0.

## 16. Hiệu năng, index và số truy vấn thực tế

Mục tiêu của `@Update`/derived delete với return count thường là tránh **đọc toàn bộ document về Java** chỉ để biết có bao nhiêu bản ghi được tác động. Nhưng số lượng document cập nhật còn phụ thuộc filter và index.

Ví dụ:

~~~javascript
db.catalog_products.createIndex(
  { tenantId: 1, status: 1 },
  { name: "idx_tenant_status" }
);
~~~

Index này có thể hỗ trợ tìm các sản phẩm của một tenant theo trạng thái. Nhưng nếu mỗi update sửa chính `status`, MongoDB cũng phải cập nhật index tương ứng. Chỉ tạo index sau khi đánh giá tỷ lệ đọc/ghi và mức chọn lọc trên workload.

### 16.1. Quan sát lệnh thực tế

Trong integration test, MongoDB Java Driver `CommandListener` có thể ghi nhận `CommandStartedEvent` và nội dung `update`/`delete` command:

~~~json
{
  "update": "catalog_products",
  "updates": [
    {
      "q": {
        "tenantId": "tenant-a",
        "status": "PENDING"
      },
      "u": { "$set": { "status": "ACTIVE" } },
      "multi": true
    }
  ]
}
~~~

Đây là **BSON command minh họa**, lược bớt field phụ của driver; không phải cam kết byte-for-byte. Truy vấn repository có thể được tối ưu theo implementation, và các command thực tế có thể được chia khác nhau.

Quan sát thêm:

- Số command gửi tới server và số round trip.
- `matchedCount`, `modifiedCount`, `deletedCount` cùng exception trên đường lỗi.
- Query plan, số document examined, index được sử dụng.
- p95 latency, write concern, replication lag và tải server.
- Khi xóa trả danh sách entity, có hay không bước tìm trước khi xóa và payload tạo ra.

Không bật log BSON raw production nếu filter hoặc update chứa email, ID nhạy cảm, thông tin tài chính hay dữ liệu cá nhân chưa được che phù hợp.

### 16.2. Count không biến updateMany thành transaction

Một phương thức cập nhật 1.000 document có thể trả số modified khi thành công; nó **không tự bảo đảm** tất cả document được cập nhật nguyên tử như một đơn vị. MongoDB bảo đảm nguyên tử ở cấp **mỗi document**; với nhiều document, cần transaction được cấu hình đúng nếu nghiệp vụ yêu cầu all-or-nothing.

Ngay cả khi transaction tồn tại, cần xử lý lỗi commit không rõ kết quả, retry có điều kiện và kết quả đọc sau commit. Con số trả về từ một lệnh update không thay cho xác nhận toàn bộ workflow xuyên collection.

## 17. Kiểm thử với MongoDB thật

Mock repository chỉ giúp chứng minh service gọi đúng method, nhưng **không xác minh** derived delete trả count thật, `@Update` áp dụng cho mấy document, mapping BSON hay sự khác nhau giữa matched/modified. Nên kiểm thử trên MongoDB thực, ví dụ dùng Testcontainers. Trong Spring Boot 3.x, `@DataMongoTest` nạp test slice cho MongoDB, nhưng **không tự cung cấp MongoDB server**.

### 17.1. Integration test cho saveAll, @Update và derived delete

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import com.mongodb.client.result.UpdateResult;

@DataMongoTest
class RepositoryWriteCountTest {
    @Autowired CatalogProductRepository products;
    @Autowired MongoTemplate mongo;

    private CatalogProduct item(String id, String tenant, String status) {
        return new CatalogProduct(
                id, tenant, id, "Product " + id, 10, status);
    }

    @BeforeEach
    void prepare() {
        // Chỉ chạy trên MongoDB test cô lập.
        products.deleteAll();
        products.saveAll(List.of(
                item("p-1", "tenant-a", "PENDING"),
                item("p-2", "tenant-a", "PENDING"),
                item("p-3", "tenant-a", "ACTIVE"),
                item("p-4", "tenant-b", "PENDING")));
    }

    @Test
    void saveReturnsEntityAndSaveAllDoesNotReturnModifiedCount() {
        CatalogProduct created = products.save(
                item("p-5", "tenant-a", "PENDING"));
        assertThat(created.getId()).isEqualTo("p-5");

        Iterable<CatalogProduct> returned = products.saveAll(List.of(
                item("p-6", "tenant-a", "ACTIVE"),
                item("p-7", "tenant-a", "ACTIVE")));
        assertThat(returned).hasSize(2);
        // Số 2 ở đây là số entity được trả,
        // không phải modifiedCount trong một UpdateResult.
    }

    @Test
    void annotatedUpdateReportsAffectedDocuments() {
        long changed = products.changeStatus(
                "tenant-a", "PENDING", "ACTIVE");
        assertThat(changed).isEqualTo(2);

        long repeated = products.changeStatus(
                "tenant-a", "PENDING", "ACTIVE");
        assertThat(repeated).isZero();

        assertThat(products.findById("p-4").orElseThrow().getStatus())
                .isEqualTo("PENDING");
    }

    @Test
    void matchedAndModifiedCanDiffer() {
        Query allActive = Query.query(
                Criteria.where("tenantId").is("tenant-a")
                        .and("status").is("ACTIVE"));
        UpdateResult result = mongo.updateMulti(
                allActive,
                new Update().set("status", "ACTIVE"),
                CatalogProduct.class);

        assertThat(result.getMatchedCount()).isEqualTo(1);
        assertThat(result.getModifiedCount()).isZero();
    }

    @Test
    void derivedDeleteReturnsCountOfDeletedDocuments() {
        long removed = products.deleteByTenantIdAndStatus(
                "tenant-a", "PENDING");

        assertThat(removed).isEqualTo(2);
        assertThat(products.findById("p-1")).isEmpty();
        assertThat(products.findById("p-2")).isEmpty();
        assertThat(products.findById("p-4")).isPresent();
    }
}
~~~

Điểm quan trọng của test:

- Chỉ hai document `PENDING` thuộc `tenant-a` được cập nhật; document `p-4` của `tenant-b` không bị ảnh hưởng.
- Khi gọi lại update với filter `PENDING`, không còn document thỏa nên count bằng 0.
- Lệnh set lại `ACTIVE` trên document vốn đã `ACTIVE` có matched = 1 nhưng modified = 0.
- Derived delete trả số document bị xóa, còn `saveAll` trả entity.

Test `@Update` ở đây chỉ kiểm tra trường hợp **giá trị thực sự đổi**; đó là cách tránh nhầm lẫn khi thử suy diễn modified/matched từ một phép gán giá trị cũ.

### 17.2. Kiểm thử delete trả entity và dữ liệu cạnh tranh

Các test bổ sung:

1. Dùng `removeByTenantIdAndStatus` trên một tập nhỏ; kiểm tra các entity được trả, sau đó xác minh document thực sự không còn.
2. Tạo vài nghìn document rồi quan sát memory/command count của derived delete trả `List` so với trả `long`.
3. Cho hai request cùng xóa theo điều kiện; không giả định cả hai đều nhận cùng số deleted.
4. Với entity có `@Version`, kiểm tra `save` stale và khác biệt với đường xóa theo ID.
5. Cho một request sửa `status` trong lúc request khác update theo `previousStatus`; xác minh chỉ document còn khớp điều kiện mới bị sửa.
6. Test upsert tạo mới và so sánh `getUpsertedId()` với `matchedCount/modifiedCount`.
7. Gắn `CommandListener` để quan sát repository update/delete thực tế, đặc biệt filter tenant và `multi`.
8. Test unacknowledged/timeout chỉ khi môi trường test được thiết kế đúng; không dùng cấu hình ghi thiếu an toàn ở production để kiểm thử tùy tiện.

Khi chạy song song, **không để `deleteAll()` xóa collection dùng chung giữa các test**. Cần cơ chế cô lập database, collection hoặc dữ liệu theo ID. Các test này là ví dụ để chạy trong môi trường kiểm thử riêng.

## 18. Những lỗi thường gặp

| Sai lầm | Hậu quả | Hướng sửa |
|---|---|---|
Xem `save` trả entity là “1 document đã sửa” | Phân loại insert/update/no-op sai | Đọc semantics của save, dùng UpdateResult khi cần count |
Xem kích thước `saveAll` output là modifiedCount | Báo số document thay đổi sai | Tách kết quả entity với kết quả write |
Xem `deleteById` trả void là đã xóa đúng một document | Không biết ID có tồn tại hay không | Derived delete count hoặc DeleteResult |
Đếm `count()` trước/sau để suy ra modified count | Update không đổi tổng; concurrency làm sai hiệu số | Dùng write result trực tiếp |
Nhầm `matchedCount` với `modifiedCount` | No-op update bị hiểu là không tìm thấy | Thiết kế response chứa đúng hai số |
Quên `tenantId` trong `@Update` query | Sửa dữ liệu tenant khác | Đưa tenant đáng tin cậy vào filter |
Cho rằng `@Update` mặc định cập nhật một document | Sửa toàn bộ bản ghi phù hợp | Hiểu multi-update, test số affected |
Khai báo entity return cho `@Update` | Contract không tương thích | Dùng long/void hoặc findAndModify phù hợp |
Đổi sang derived delete trả List để lấy `size()` | Đọc nhiều entity, tốn memory | Dùng long khi chỉ cần số deleted |
Cho rằng `@Version` tự bảo vệ mọi custom update | Lost update hoặc ghi đè từ đường ghi khác | Filter version kỳ vọng và kiểm tra kết quả |
Không phân biệt upsert tạo mới với update hiện hữu | Thống kê sửa dữ liệu sai | Đọc upsertedId riêng |
Retry toàn bộ bulk tăng counter khi timeout | Có thể áp dụng hai lần | Idempotency/event ID/reconcile |
Dùng `modifiedCount = 0` làm lỗi 404 trong mọi API | Có document nhưng giá trị không đổi | Định nghĩa semantics no-op/idempotent |
Chỉ test mock repository | Không thấy BSON thực hoặc số affected | Integration test MongoDB thật |
Giả định count là bằng chứng toàn bộ workflow hoàn tất | Thiếu audit/email/transaction | Tách technical write result và business result |

## 19. Bài tập vận dụng

**Bài 1 — Phân loại kiểu trả về.** Với `save`, `saveAll`, `deleteById`, `deleteByTenantIdAndStatus` và `changeStatus`, lập bảng chỉ rõ kiểu Java, kết quả có thể quan sát và điều gì không thể suy ra từ return value.

**Bài 2 — Matched và modified.** Seed 3 sản phẩm ACTIVE cùng tenant. Gọi `MongoTemplate.updateMulti` gán trạng thái ACTIVE lần nữa và giải thích vì sao kết quả `matched = 3`, `modified = 0` trong trường hợp không có field phụ bị cập nhật.

**Bài 3 — @Update và multi-update.** Tạo hai sản phẩm PENDING cho tenant-a và một sản phẩm PENDING cho tenant-b. Gọi `changeStatus` rồi kiểm tra count, trạng thái cuối của cả ba và command `multi`.

**Bài 4 — Derived delete.** Thử hai phương thức xóa theo trạng thái: một trả `long`, một trả `List<CatalogProduct>`. So sánh output, số query và memory khi số document tăng. Giải thích khi nào cần audit riêng.

**Bài 5 — Void không phải số 0.** Gọi `deleteById` với ID tồn tại và ID không tồn tại. Viết service cần trả deleted count bằng `MongoTemplate.remove` thay vì giả định kết quả từ void.

**Bài 6 — Concurrency.** Có tồn kho 5, hai request cùng muốn trừ 3. So sánh read-modify-save không version với `updateFirst` có `stock >= 3`. Dùng test đồng thời để chứng minh chỉ một request trừ được hàng.

**Bài 7 — Optimistic locking.** Thêm model có `@Version Long`. Cho hai luồng đọc cùng version, save lần lượt và quan sát optimistic locking exception. Thiết kế cách chuyển thành response 409 phù hợp.

**Bài 8 — Upsert và số liệu.** Chạy `upsert` với business key chưa tồn tại, sau đó chạy lại khi đã tồn tại. Ghi `matchedCount`, `modifiedCount` và `upsertedId`. Thêm unique index để kiểm thử cạnh tranh tạo mới.

**Bài 9 — API contract.** Viết DTO response cho cập nhật trạng thái hàng loạt chứa hai trường `matchedDocuments`/`modifiedDocuments`. Xác định cách trả khi hai số bằng 0, khi matched lớn hơn modified và khi write timeout.

**Bài 10 — Hiệu năng.** Tạo ít nhất vài chục nghìn document trong test riêng, so sánh derived delete trả entity list, derived delete trả long và MongoTemplate.remove. Đo số lệnh, memory, latency và bảo đảm không làm lộ dữ liệu tenant khác.

## 20. Ghi nhớ

**Kiểu trả về của repository biểu đạt hợp đồng API, không tự động là số document đã được sửa.** `save` trả entity, `saveAll` trả các entity, còn các thao tác CRUD xóa mặc định thường trả `void`. **Derived delete** có thể trả `long` để báo số xóa hoặc trả các entity được chọn để xóa; **`@Update`** có thể dùng `long/Long` khi cần số document được cập nhật theo semantics của framework.

Khi cần phân biệt **document khớp query** và **document thực sự đổi**, dùng `MongoTemplate` với `UpdateResult.getMatchedCount()/getModifiedCount()`. Khi xóa vật lý, dùng `DeleteResult.getDeletedCount()`; khi upsert tạo mới, đọc `getUpsertedId()` riêng. Đừng dùng `count()` trước/sau làm phép đo số cập nhật.

Trong luồng ghi có cạnh tranh, **filter điều kiện, unique index, optimistic locking, acknowledged write concern và idempotency** là những yếu tố quyết định tính đúng đắn. Luôn định nghĩa rõ response khi modified = 0, tránh sửa nhầm tenant, và xác minh BSON/số liệu bằng integration test trên MongoDB thật. Báo cáo số document chỉ có giá trị khi người đọc biết chính xác nó đang đo **matched, modified, inserted, upserted hay deleted**.

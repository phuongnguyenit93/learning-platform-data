# @Indexed, @CompoundIndex và annotation chỉ mục chuyên biệt

## 1. Bài toán: khai báo chỉ mục ở Java có đủ chưa?

Một hệ thống thương mại điện tử lưu hàng triệu sản phẩm trong MongoDB. Màn hình quản trị thường truy vấn:

- Tìm một sản phẩm theo **tenantId + sku**.
- Liệt kê sản phẩm đang bán của một tenant, sắp theo **updatedAt giảm dần**.
- Tìm đơn hàng theo **tenantId + status + createdAt**.
- Tự hết hạn token hoặc session sau một khoảng thời gian.
- Tìm tài liệu theo từ khóa, hoặc cửa hàng gần một tọa độ địa lý.

Các truy vấn này có thể chạy được dù collection chưa có index, nhưng lúc dữ liệu lớn, MongoDB có thể phải đọc quá nhiều document. Chỉ mục (*index*) giúp tìm đúng dữ liệu nhanh hơn khi hình dạng truy vấn và thứ tự khóa phù hợp. Đổi lại, index tiêu tốn dung lượng và làm phát sinh công việc cập nhật khi ghi.

Trong Spring Data MongoDB, chúng ta có thể mô tả ý định tạo index ở entity bằng:

- **@Indexed** cho một field.
- **@CompoundIndex / @CompoundIndexes** cho nhiều field theo thứ tự.
- **@TextIndexed**, **@GeoSpatialIndexed**, **@HashIndexed**, **@WildcardIndexed** cho những loại truy vấn chuyên biệt.

Tuy nhiên, một nguyên tắc cực kỳ quan trọng là: **annotation khai báo metadata không đồng nghĩa index chắc chắn đã tồn tại trên MongoDB Server**. Việc tạo index còn phụ thuộc cấu hình auto-index-creation, quá trình khởi tạo ứng dụng và chiến lược migration.

Bài **@Indexed, @CompoundIndex và annotation chỉ mục chuyên biệt** thuộc chương **Chỉ mục** trong module **SPRING_DATA_MONGODB**. Module sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác qua MongoTemplate hoặc repository; việc hiểu index giúp thiết kế truy vấn, aggregation, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.

Sau bài học, bạn có thể:

1. Đặt annotation index đúng vị trí trên entity và hiểu tên field Java/BSON.
2. Chọn single-field hay compound index cho truy vấn thực tế.
3. Phân biệt unique, sparse, partial và TTL index, tránh mất dữ liệu hoặc khóa nhầm.
4. Sử dụng text, 2dsphere, hashed, wildcard index trong ngữ cảnh phù hợp.
5. Quyết định khi nào tạo index tự động, lúc startup hay bằng migration có kiểm soát.
6. Đọc danh sách index trên MongoDB, sử dụng explain và đo kết quả.
7. Kiểm thử ràng buộc index với repository/MongoTemplate trên MongoDB thật.

## 2. Dữ liệu mẫu cho chương Chỉ mục

Collection **products**:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenant_id: "shop-a",
  sku: "BOOK-001",
  name: "Spring Data MongoDB",
  active: true,
  priceMinor: NumberLong("199000"),
  updatedAt: ISODate("2025-06-01T09:00:00Z"),
  tags: ["JAVA", "MONGODB"]
}
~~~

Hai tình huống:

1. **sku** có thể trùng giữa **shop-a** và **shop-b**, nhưng không được trùng trong cùng tenant.
2. Các sản phẩm active của một tenant được xem theo updatedAt mới nhất, nên cần kiểm tra khả năng dùng index cho cả **filter lẫn sort**.

Entity tối giản:

~~~java
package com.example.catalog;

import java.time.Instant;
import java.util.List;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "products")
public class ProductDocument {

    @Id
    private ObjectId id;

    @Field("tenant_id")
    private String tenantId;

    private String sku;
    private String name;
    private boolean active;
    private long priceMinor;
    private Instant updatedAt;
    private List<String> tags;

    public ObjectId getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getSku() { return sku; }
    public boolean isActive() { return active; }
    public long getPriceMinor() { return priceMinor; }
    public Instant getUpdatedAt() { return updatedAt; }
}
~~~

Đây là class minh họa các field liên quan đến index; trong ứng dụng thực cần bổ sung constructor/validation theo cách ánh xạ Spring Data mà dự án dùng.

### 2.1. Index lưu trên collection chứ không nằm trong object Java

Khi khai báo index trên ProductDocument, Spring Data sử dụng mapping metadata để xác định index của collection **products**. MongoDB quản lý index trên dữ liệu BSON thực tế, không dựa vào việc query được gọi từ repository hay MongoTemplate.

Một index dùng chung cho mọi lệnh truy vấn lên collection có cùng cấu trúc filter/sort, kể cả truy vấn từ mongosh và MongoDB Java Driver thuần.

## 3. MongoDB index vận hành như thế nào?

Index thông thường của MongoDB là cấu trúc tối ưu cho việc tìm kiếm/sắp xếp theo khóa, thay vì buộc server đọc tất cả document.

~~~mermaid
flowchart LR
    A["Repository / MongoTemplate query"] --> B["MongoDB query planner"]
    B --> C{"Index phù hợp?"}
    C -->|Có| D["IXSCAN và các bước bổ sung"]
    C -->|Không hoặc không có lợi| E["COLLSCAN"]
    D --> F["Trả document / projection"]
    E --> F
~~~

Một index có thể giúp:

- Lọc theo equality/range nhanh hơn.
- Phục vụ sort trong một số hình dạng truy vấn.
- Hỗ trợ unique constraint.
- Hỗ trợ cơ chế đặc biệt như TTL, text search, geospatial search.

Đổi lại:

- Mỗi insert/update/delete có thể cần duy trì các index liên quan.
- Index tiêu tốn disk/memory.
- Tạo index trên collection lớn có chi phí vận hành.
- Index sai thứ tự có thể không phù hợp filter/sort thực tế.

**Có index không bảo đảm query planner luôn dùng nó**, và **IXSCAN không tự đồng nghĩa truy vấn nhanh**. Hãy đo số document/key phải duyệt, thời gian và nhu cầu sort/fetch.

### 3.1. Index mặc định trên _id

MongoDB tạo unique index trên **_id** cho collection bình thường. Nếu ProductDocument đã có @Id, không cần thêm một @Indexed(unique=true) khác chỉ để đảm bảo _id duy nhất.

~~~javascript
db.products.getIndexes();
~~~

Một collection vừa tạo có thể có:

~~~javascript
{ key: { _id: 1 }, name: "_id_", unique: true }
~~~

Hình dạng kết quả getIndexes có thể chứa thêm version, options và metadata khác tùy server.

## 4. @Indexed: một property, một chỉ mục đơn

Annotation:

~~~java
import org.springframework.data.mongodb.core.index.Indexed;

public class ProductDocument {
    @Indexed
    private String sku;
}
~~~

Đây là mẫu khai báo để Spring Data có thể tạo index tăng dần cho **sku** khi cơ chế tạo index được kích hoạt.

Tương đương về ý định:

~~~javascript
db.products.createIndex({ sku: 1 });
~~~

Index này **không tự ràng buộc tenantId**. Trong multi-tenant system, nếu cần SKU duy nhất theo tenant, không nên đánh dấu sku là unique toàn collection; cần compound unique index.

### 4.1. Đặt tên rõ ràng

~~~java
@Indexed(name = "idx_products_sku")
private String sku;
~~~

Tên cố định giúp nhận diện trong getIndexes, migration và giám sát. Nhưng nếu index đã có cùng key pattern với tên/options khác, thay đổi annotation không đảm bảo server tự đổi tên index cũ.

### 4.2. Chiều tăng/giảm

~~~java
import org.springframework.data.mongodb.core.index.IndexDirection;

@Indexed(
    name = "idx_products_updated_desc",
    direction = IndexDirection.DESCENDING
)
private Instant updatedAt;
~~~

Index giảm dần minh họa:

~~~javascript
db.products.createIndex(
  { updatedAt: -1 },
  { name: "idx_products_updated_desc" }
);
~~~

Với single-field index thông thường, MongoDB có thể duyệt index theo chiều ngược nên không phải mọi trường hợp sort DESC đều cần riêng một index DESC. Chiều của từng khóa trở nên quan trọng hơn trong **compound sort hỗn hợp hướng**.

### 4.3. Hai @Indexed không tạo một compound index

~~~java
@Indexed
private String tenantId;

@Indexed
private String sku;
~~~

Đây là **hai index đơn** trên tenantId và sku, không phải index ghép **{ tenantId: 1, sku: 1 }**.

MongoDB có những chiến lược kết hợp index trong một số truy vấn, nhưng không nên xem đó là giải pháp thay thế mặc định cho một compound index được thiết kế đúng theo workload.

## 5. @Indexed(unique = true): bảo vệ khóa nghiệp vụ

~~~java
@Indexed(name = "uk_products_sku", unique = true)
private String sku;
~~~

Ý nghĩa: không cho hai document trong toàn collection có cùng giá trị sku theo quy tắc unique index.

~~~javascript
db.products.createIndex(
  { sku: 1 },
  { unique: true, name: "uk_products_sku" }
);
~~~

### 5.1. Vì sao kiểm tra exists trước khi insert không đủ?

Nếu hai request đồng thời làm:

~~~java
if (!repository.existsBySku(sku)) {
    repository.insert(product);
}
~~~

cả hai có thể cùng thấy SKU chưa tồn tại rồi cùng insert. Đây là một race condition (**check-then-act**).

**Unique index trên MongoDB** mới bảo vệ tính duy nhất khi có cạnh tranh. Ứng dụng vẫn validate trước để cung cấp lỗi đẹp, nhưng phải bắt lỗi duplicate key ở đường ghi.

### 5.2. Lỗi khi đã có dữ liệu trùng

Nếu collection đã có hai product cùng sku, việc tạo **unique index** trên sku sẽ không thành công cho tới khi dữ liệu được sửa.

**Không xóa bản ghi trùng tự động chỉ để tạo index cho qua**. Hãy xác định bản ghi chuẩn, merge/migration theo quy tắc nghiệp vụ, sao lưu và triển khai có kiểm soát.

### 5.3. Unique trên field optional

Với unique single-field index thông thường, các document không có field và document có giá trị null có quy tắc index riêng, có thể dẫn đến lỗi trùng khi có nhiều record cùng thiếu/null. **Đừng mặc định unique index cho phép vô hạn document không có field**.

Tùy yêu cầu, cân nhắc **partial unique index** để chỉ áp đặt ràng buộc trên tập document có field hợp lệ hoặc trạng thái cần bảo vệ.

## 6. @CompoundIndex: kết hợp nhiều property theo thứ tự

Với hệ thống multi-tenant, yêu cầu SKU chỉ cần unique **trong mỗi tenant**.

~~~java
import org.springframework.data.mongodb.core.index.CompoundIndex;

@Document(collection = "products")
@CompoundIndex(
    name = "uk_products_tenant_sku",
    def = "{ 'tenant_id': 1, 'sku': 1 }",
    unique = true
)
public class ProductDocument {
    // tenantId được ánh xạ BSON tenant_id; sku giữ nguyên.
}
~~~

Lệnh MongoDB tương ứng về ý định:

~~~javascript
db.products.createIndex(
  { tenant_id: 1, sku: 1 },
  {
    name: "uk_products_tenant_sku",
    unique: true
  }
);
~~~

Ví dụ:

| tenant_id | sku | Được insert? |
| --- | --- | --- |
| shop-a | BOOK-001 | Có, nếu khóa chưa tồn tại |
| shop-b | BOOK-001 | Có, vì tenant khác |
| shop-a | BOOK-002 | Có |
| shop-a | BOOK-001 lần thứ hai | **Không**, duplicate compound key |

### 6.1. Annotation đặt ở type

**@CompoundIndex** thường đặt trên entity class hoặc một type nhúng phù hợp với mapping. Giá trị **def** xác định key pattern và thứ tự các thành phần.

Không hiểu rằng mọi trường dùng trong def đều cần @Indexed riêng. Thêm @Indexed cho từng field khi không cần có thể tạo index dư, tăng chi phí ghi.

### 6.2. Java property và tên BSON

Entity dùng **@Field("tenant_id")** cho property tenantId. Trong cấu hình index, Spring Data có cơ chế mapping đường dẫn property sang tên BSON. Các cấu hình def tùy trường hợp có thể đi qua resolver của Spring Data; với chỉ mục bảo mật/unique, **phải xác minh kết quả getIndexes thực tế** để chắc index nằm trên **tenant_id**, không phải một field ngoài ý muốn.

Đừng chỉ nhìn annotation rồi suy rằng server index đã đúng tên hoặc đúng options.

## 7. Nhiều @CompoundIndex và @CompoundIndexes

Một entity có thể có nhiều mẫu truy vấn:

1. Tìm theo tenant + sku.
2. Liệt kê active sản phẩm của tenant theo updatedAt.

Khai báo nhiều index ghép:

~~~java
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.index.CompoundIndexes;

@Document(collection = "products")
@CompoundIndexes({
    @CompoundIndex(
        name = "uk_products_tenant_sku",
        def = "{ 'tenant_id': 1, 'sku': 1 }",
        unique = true
    ),
    @CompoundIndex(
        name = "idx_products_tenant_active_updated",
        def = "{ 'tenant_id': 1, 'active': 1, 'updatedAt': -1 }"
    )
})
public class ProductDocument {
    // Các field như phần 2.
}
~~~

Trong các thế hệ Spring Data hỗ trợ repeatable annotation, có thể khai báo nhiều @CompoundIndex trực tiếp; **@CompoundIndexes** vẫn cho thấy rõ tập index trên một class.

Lưu ý: đây là **biến thể thay thế** cho annotation @CompoundIndex của phần trước, không chép cả hai ví dụ vào cùng class rồi vô tình tạo các index trùng nhau.

### 7.1. Vì sao thứ tự key quan trọng?

Index:

~~~javascript
{ tenant_id: 1, active: 1, updatedAt: -1 }
~~~

phù hợp để cân nhắc cho truy vấn:

~~~javascript
db.products.find({
  tenant_id: "shop-a",
  active: true
}).sort({ updatedAt: -1 }).limit(20);
~~~

Vì hai field đầu được filter bằng equality, MongoDB có thể duyệt theo updatedAt để phục vụ sort và limit.

Nhưng cùng index này không mặc nhiên tối ưu:

~~~javascript
db.products.find({ active: true });
~~~

vì **tenant_id** là khóa dẫn đầu chưa được ràng buộc. Quy tắc prefix thường rất quan trọng khi đánh giá compound index.

### 7.2. Equality, sort, range

Một nguyên tắc thực hành là cân nhắc thứ tự **equality → sort → range**, nhưng đây là **heuristic**, không phải công thức đúng cho mọi workload. Thứ tự tối ưu phụ thuộc độ chọn lọc, filter thực tế, sort, limit và index đã có.

Ví dụ:

~~~javascript
db.orders.find({
  tenantId: "shop-a",
  status: "PAID",
  createdAt: {
    $gte: ISODate("2025-06-01T00:00:00Z"),
    $lt: ISODate("2025-07-01T00:00:00Z")
  }
}).sort({ createdAt: -1 });
~~~

Index để đánh giá:

~~~javascript
{ tenantId: 1, status: 1, createdAt: -1 }
~~~

Hãy xác nhận bằng explain và dữ liệu đại diện thay vì chỉ áp quy tắc máy móc.

### 7.3. Sort hỗn hợp

Ví dụ sort:

~~~javascript
.sort({ priceMinor: 1, updatedAt: -1 })
~~~

Index với hướng hỗn hợp:

~~~javascript
{ priceMinor: 1, updatedAt: -1 }
~~~

có ý nghĩa khác index **{ priceMinor: 1, updatedAt: 1 }**. Với nhiều field sort, tương quan chiều của key và sort cần được xét theo khả năng duyệt xuôi/ngược của index.

## 8. Index trên nested object và mảng

MongoDB hỗ trợ index theo đường dẫn field lồng nhau, ví dụ:

~~~javascript
db.products.createIndex({ "supplier.region": 1 });
~~~

Nếu entity có embedded object Supplier:

~~~java
public class SupplierInfo {
    private String code;

    @Indexed(name = "idx_supplier_region")
    private String region;
}
~~~

và ProductDocument chứa:

~~~java
private SupplierInfo supplier;
~~~

Spring Data index resolver có thể dùng thông tin path lồng nhau để tạo index trên collection chính. Quy tắc tên index trong nested type và prefix phụ thuộc context ánh xạ; phải kiểm tra **getIndexes** để xác nhận tên/key thực.

### 8.1. Multikey index

~~~java
@Indexed(name = "idx_products_tags")
private List<String> tags;
~~~

Khi một field là array, MongoDB có thể tạo **multikey index**. Nó giúp tìm document có phần tử phù hợp, ví dụ:

~~~javascript
db.products.find({ tags: "JAVA" });
~~~

Nhưng multikey index có những giới hạn khi kết hợp nhiều array paths trong cùng compound index, về sort và phạm vi match trên array. **Không mặc định một compound index có thể chứa hai array field độc lập trong mọi document**.

Với embedded array và nhiều điều kiện cần áp dụng lên **cùng phần tử**, nên hiểu semantics **$elemMatch** và cách MongoDB tạo index bounds.

## 9. Sparse index: chỉ chứa document có field

Một index sparse có thể được khai báo:

~~~java
@Indexed(name = "idx_optional_code_sparse", sparse = true)
private String optionalCode;
~~~

Nó hướng tới việc không index những document **thiếu field optionalCode**. Ví dụ câu lệnh:

~~~javascript
db.products.createIndex(
  { optionalCode: 1 },
  { sparse: true }
);
~~~

**Sparse không có nghĩa bỏ qua mọi giá trị null.** Document có field được khai báo với giá trị null có thể vẫn được index theo semantics của loại index đó. Vì vậy, nếu muốn unique trên dữ liệu đã cung cấp/đạt điều kiện, cần hiểu rõ null/missing và nhiều trường hợp nên chọn partial index.

### 9.1. Sparse ảnh hưởng tới việc planner dùng index

Vì sparse index bỏ qua một số document, MongoDB không thể dùng nó để trả kết quả đầy đủ cho những truy vấn cần cả document không có field mà không có ràng buộc thích hợp.

Đừng ép query dùng sparse index qua hint rồi kết luận collection chỉ có những document được trả. Index không phải mô hình toàn bộ document.

## 10. Partial index: index một tập con theo điều kiện

Partial index sử dụng **partialFilterExpression** để chỉ đưa những document thỏa một điều kiện vào index.

Giả sử chỉ cần tìm/đảm bảo unique mã hiển thị cho những sản phẩm đang active.

~~~javascript
db.products.createIndex(
  { tenant_id: 1, displayCode: 1 },
  {
    name: "uk_active_tenant_display_code",
    unique: true,
    partialFilterExpression: { active: true }
  }
);
~~~

Annotation compound có thể khai báo:

~~~java
@CompoundIndex(
    name = "uk_active_tenant_display_code",
    def = "{ 'tenant_id': 1, 'displayCode': 1 }",
    unique = true,
    partialFilter = "{ 'active': true }"
)
public class ProductDocument {
    // Các field tương ứng.
}
~~~

**Ý nghĩa:** ràng buộc unique compound key được áp dụng **cho các document thỏa active=true**. Document inactive nằm ngoài phạm vi partial index nên không bị ràng buộc bởi chính index này.

### 10.1. Đổi active có thể gây duplicate key

Hai document inactive có thể cùng displayCode. Khi một trong hai hoặc cả hai chuyển sang active, MongoDB phải cập nhật index; thao tác làm vi phạm unique constraint có thể bị từ chối.

Chính sách ứng dụng cần xử lý lỗi cả ở đường **insert và update**, không chỉ khi tạo mới.

### 10.2. Truy vấn phải phù hợp với partial filter

Một partial index chỉ chứa tập con. MongoDB thường chỉ có thể dùng nó một cách an toàn khi query chứa/bao hàm điều kiện phù hợp để không bỏ sót document.

Ví dụ:

~~~javascript
db.products.find({
  tenant_id: "shop-a",
  active: true,
  displayCode: "TOP-01"
});
~~~

có cơ hội dùng index hơn truy vấn không có active=true nếu dữ liệu inactive cũng phải được xét.

### 10.3. Sparse và partial không phải hai option để cộng tùy tiện

Với MongoDB index options, **sparse và partialFilterExpression có ràng buộc kết hợp**; không khai báo cả hai chỉ vì muốn index ít document hơn. Hãy chọn một cơ chế đúng requirement và xác minh server có chấp nhận option tương ứng.

### 10.4. Khi nào dùng partial thay vì sparse?

| Mong muốn | Hướng cân nhắc |
| --- | --- |
| Bỏ document thiếu field | Sparse có thể đủ |
| Chỉ index document active | Partial filter |
| Unique chỉ khi trường đạt kiểu/điều kiện | Partial filter theo schema/điều kiện phù hợp |
| Tránh index dữ liệu đã soft-delete | Partial filter theo deleted/active |
| Mọi document đều phải thỏa unique | Unique index đầy đủ, không lọc |

Không dùng partial index để che giấu dữ liệu sai: nó chủ động thay đổi phạm vi ràng buộc.

## 11. TTL index qua @Indexed

TTL (*time-to-live*) index cho phép MongoDB tự xóa document đã hết hạn theo thời gian.

Ví dụ collection **login_sessions** có field createdAt và một chính sách hết hạn sau một khoảng cố định:

~~~java
@Document(collection = "login_sessions")
public class LoginSessionDocument {

    @Id
    private String id;

    @Indexed(expireAfterSeconds = 3600)
    private Instant createdAt;
}
~~~

Ví dụ trên sử dụng **expireAfterSeconds** để minh họa và có thể bị đánh dấu deprecated ở Spring Data phiên bản mới. Những phiên bản mới có **expireAfter** dạng duration expression; hãy chọn cú pháp đúng với phiên bản đang triển khai và xác minh index được tạo.

MongoDB index tương ứng:

~~~javascript
db.login_sessions.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 3600 }
);
~~~

Document có createdAt = 10:00Z về nguyên tắc đủ điều kiện hết hạn sau 11:00Z, nhưng **không được giả định bị xóa đúng 11:00:00Z**. TTL monitor chạy bất đồng bộ và có thể có độ trễ phụ thuộc tải, deployment và cấu hình.

### 11.1. TTL index không phải scheduler chính xác

Không dùng TTL làm cơ chế duy nhất để:

- Gửi thông báo hết hạn chính xác từng giây.
- Hủy quyền truy cập đúng tại thời điểm hết hạn.
- Kích hoạt workflow nghiệp vụ đúng giờ.

Ứng dụng nên **kiểm tra thời điểm hết hạn khi đọc/xác thực**. TTL là cơ chế dọn dữ liệu, không thay thế authorization.

### 11.2. TTL chỉ hoạt động với kiểu thời gian phù hợp

TTL index thông thường cần field dạng BSON Date (hoặc array chứa Date theo semantics MongoDB). Nếu entity lưu:

~~~javascript
{ createdAt: "2025-06-01T10:00:00Z" }
~~~

thì không được kỳ vọng một TTL index thông thường hiểu đây là một thời điểm để xóa. Hãy dùng BSON Date/Instant được map đúng và kiểm thử.

### 11.3. TTL một field khác compound index

TTL thông thường là **single-field index** với option expireAfterSeconds; không gắn TTL vào compound index tùy ý rồi mong MongoDB tự hết hạn theo nhiều khóa.

Nếu dữ liệu nhiều tenant cần retention khác nhau, hãy thiết kế một field **expiresAt** cho từng document hoặc một collection/retention policy phù hợp. Không cố biến một compound index tenant+createdAt thành TTL nếu server không hỗ trợ.

### 11.4. Cách tiếp cận expiresAt

~~~java
@Document(collection = "login_sessions")
public class LoginSessionDocument {

    @Id
    private String id;

    @Indexed(expireAfterSeconds = 0)
    private Instant expiresAt;
}
~~~

Chính sách này dùng **expiresAt** là thời điểm document đủ điều kiện bị xóa, với TTL expireAfterSeconds=0. Vẫn có độ trễ dọn vật lý: phiên hết hạn phải bị từ chối ở tầng nghiệp vụ ngay cả khi document còn tồn tại.

## 12. @TextIndexed: tìm kiếm văn bản

MongoDB có **text index** phục vụ tìm kiếm nội dung chữ theo các quy tắc tokenization/language của text search.

~~~java
import org.springframework.data.mongodb.core.index.TextIndexed;

@Document(collection = "articles")
public class ArticleDocument {

    @Id
    private String id;

    @TextIndexed(weight = 5)
    private String title;

    @TextIndexed(weight = 1)
    private String body;
}
~~~

Spring Data có thể tổng hợp các trường có **@TextIndexed** thành một text index của collection. Trọng số (*weight*) giúp biểu thị field nào quan trọng hơn cho scoring.

MongoDB tương ứng về ý tưởng:

~~~javascript
db.articles.createIndex(
  { title: "text", body: "text" },
  { weights: { title: 5, body: 1 } }
);
~~~

### 12.1. Một text index trên collection

MongoDB có giới hạn về số **text index** trong mỗi collection: thông thường chỉ cho phép **một text index**, nhưng index đó có thể gồm nhiều field. Vì thế, không coi mỗi @TextIndexed là một chỉ mục text độc lập có thể được tạo vô hạn.

### 12.2. Truy vấn text qua Spring Data

~~~java
import org.springframework.data.mongodb.core.query.TextCriteria;
import org.springframework.data.mongodb.core.query.TextQuery;

TextCriteria criteria = TextCriteria
    .forDefaultLanguage()
    .matching("mongodb");

TextQuery query = TextQuery.queryText(criteria)
    .sortByScore();

List<ArticleDocument> articles =
    mongoTemplate.find(query, ArticleDocument.class);
~~~

Ví dụ trên yêu cầu text search và sắp xếp theo score qua các API Spring Data tương ứng. Nếu dữ liệu có ngôn ngữ khác nhau, phải thiết kế language/analyzer phù hợp, không giả định tokenization mặc định xử lý tiếng Việt giống các ngôn ngữ khác.

### 12.3. Text search không phải tìm mọi substring

Không đồng nhất text index với:

~~~javascript
db.articles.find({ body: /mongo/i });
~~~

Tìm regex/substring và $text có semantics khác nhau. Text index cũng không tự cung cấp fuzzy search/autocomplete như một công cụ search chuyên biệt. Với yêu cầu tìm kiếm ngôn ngữ tự nhiên/độ liên quan phức tạp, có thể cần giải pháp search phù hợp như Atlas Search.

### 12.4. @Language và @TextScore

Spring Data có hỗ trợ metadata cho language/text score trong các phiên bản phù hợp. **@Language** có thể liên quan tới xử lý ngôn ngữ của text index, còn **@TextScore** giúp ánh xạ score khi query trả metadata tương ứng.

Không gắn @TextScore rồi kỳ vọng mọi truy vấn find tự tính score. Chỉ một số truy vấn text tương ứng mới có score để ánh xạ.

## 13. @GeoSpatialIndexed: chỉ mục 2dsphere và GeoJSON

Trường hợp địa điểm cửa hàng:

~~~javascript
{
  name: "Cửa hàng A",
  location: {
    type: "Point",
    coordinates: [106.70, 10.78]
  }
}
~~~

Trong GeoJSON, tọa độ theo thứ tự **longitude, latitude** (kinh độ rồi vĩ độ), không phải ngược lại.

~~~java
import org.springframework.data.mongodb.core.geo.GeoJsonPoint;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexType;
import org.springframework.data.mongodb.core.index.GeoSpatialIndexed;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "stores")
public class StoreDocument {

    private String name;

    @GeoSpatialIndexed(type = GeoSpatialIndexType.GEO_2DSPHERE)
    private GeoJsonPoint location;
}
~~~

Index tương ứng:

~~~javascript
db.stores.createIndex({ location: "2dsphere" });
~~~

### 13.1. 2d khác 2dsphere

| Index | Mục tiêu phổ biến |
| --- | --- |
| 2d | Tọa độ phẳng/legacy hoặc trường hợp chuyên biệt |
| 2dsphere | Dữ liệu địa lý trên bề mặt Trái Đất; GeoJSON và spherical queries |

Không mặc định chọn loại index dựa vào kiểu Java mà không kiểm tra hình dạng BSON, đơn vị bán kính/khoảng cách và loại truy vấn.

### 13.2. Truy vấn địa lý

~~~javascript
db.stores.find({
  location: {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.70, 10.78]
      },
      $maxDistance: 5000
    }
  }
});
~~~

Trong tình huống phù hợp với GeoJSON/2dsphere, $maxDistance được hiểu theo mét. Không thay đổi thứ tự tọa độ hoặc áp dụng đơn vị từ một API khác mà không kiểm chứng.

Với Spring Data MongoDB, có thể dùng **NearQuery**, **geoNear aggregation**, các repository geo methods hoặc MongoTemplate tùy yêu cầu.

### 13.3. Bảo vệ vị trí nhạy cảm

Geo index chỉ giúp tìm kiếm dữ liệu địa lý; không tự thực thi quyền truy cập hoặc làm mờ vị trí. Các tọa độ người dùng/kho hàng nhạy cảm cần chính sách authorization, retention và projection riêng.

## 14. @HashIndexed: truy vấn equality và khóa băm

MongoDB hỗ trợ **hashed index** trên giá trị được băm để phục vụ một số dạng truy vấn equality và phân phối shard key tương ứng.

~~~java
import org.springframework.data.mongodb.core.index.HashIndexed;

@Document(collection = "tracking_events")
public class TrackingEventDocument {

    @HashIndexed
    private String deviceId;
}
~~~

Ý tưởng index:

~~~javascript
db.tracking_events.createIndex({ deviceId: "hashed" });
~~~

### 14.1. Hashed index không dành cho range sort

Giá trị được băm không giữ trật tự so sánh của dữ liệu gốc. Vì vậy:

- Tra cứu equality trên khóa có thể là một use case phù hợp.
- Truy vấn **deviceId > một giá trị** không được tối ưu như index B-tree theo trật tự gốc.
- Không dùng hashed index để đáp ứng yêu cầu sort theo deviceId.
- Hashed index **không hỗ trợ unique constraint** giống một unique index thường.

Để bảo vệ tính duy nhất, hãy dùng unique index phù hợp trên khóa gốc thay vì coi hash index là công cụ chống trùng.

### 14.2. Sharding không chỉ là một annotation

Chọn hashed shard key cần phân tích cardinality, truy vấn theo tenant/khóa, phân phối ghi và yêu cầu range query. Gắn @HashIndexed không tự sharding collection hoặc quyết định chiến lược phân vùng của cluster.

## 15. @WildcardIndexed: truy vấn field chưa biết trước

Một sản phẩm có thể có metadata động tùy loại:

~~~javascript
{
  sku: "LAPTOP-01",
  attributes: {
    ramGb: 16,
    cpu: "i7",
    keyboardLayout: "US"
  }
}
~~~

Một document khác:

~~~javascript
{
  sku: "SHIRT-01",
  attributes: {
    size: "L",
    color: "navy"
  }
}
~~~

Nếu trước đó không biết những field nào sẽ xuất hiện trong **attributes**, MongoDB có loại **wildcard index**.

~~~java
import java.util.Map;
import org.springframework.data.mongodb.core.index.WildcardIndexed;

@Document(collection = "products")
public class ProductDocument {

    @WildcardIndexed
    private Map<String, Object> attributes;
}
~~~

Đối với property nested phù hợp, ý định index ở MongoDB có dạng:

~~~javascript
db.products.createIndex({ "attributes.$**": 1 });
~~~

Kiểm tra **getIndexes()** sau khi index resolver chạy để xác nhận đường dẫn BSON thực. Các field được @Field đổi tên cũng cần được kiểm tra.

### 15.1. Wildcard index không dành cho mọi truy vấn

Wildcard index hữu ích khi cấu trúc field linh hoạt, nhưng có giới hạn:

- Khả năng đáp ứng compound filter và sort phức tạp.
- Dung lượng index tăng khi có rất nhiều field động.
- Một số điều kiện không được tối ưu giống index cụ thể.
- Query planner có thể chọn kế hoạch khác nhau khi phân bố field không đều.

Với field thường được truy vấn nhất, **index cụ thể** có thể hiệu quả hơn wildcard index rộng.

### 15.2. Không index mọi field nhạy cảm theo thói quen

Wildcard index trên toàn document có thể tạo thêm lưu trữ và đường truy cập cho những field không cần tìm kiếm. Nên giới hạn phạm vi vào **attributes** hoặc một nhánh phù hợp và kiểm soát số lượng field, kích thước document, retention và quyền truy cập.

### 15.3. Wildcard không thay schema validation

Map<String,Object> chứa thuộc tính tùy biến vẫn cần validation về loại dữ liệu, giới hạn kích thước và số lượng key. Wildcard index không chuẩn hóa JSON/BSON và không chứng minh dữ liệu hợp lệ.

## 16. Bảng so sánh các annotation index

| Annotation | Đặt ở đâu | Loại chỉ mục | Bài toán |
| --- | --- | --- | --- |
| @Indexed | Property | Single-field, có thể unique/sparse/TTL | Equality/range/sort, một số ràng buộc |
| @CompoundIndex | Type/class | Compound theo thứ tự key | Tenant + business key; filter + sort |
| @CompoundIndexes | Type/class | Nhiều compound indexes | Nhiều query patterns |
| @TextIndexed | Property | Text index, có thể nhiều field | Tìm kiếm từ khóa văn bản |
| @GeoSpatialIndexed | Property | 2d hoặc 2dsphere | Vị trí/địa lý |
| @HashIndexed | Property | Hashed index | Equality/shard-key pattern phù hợp |
| @WildcardIndexed | Property/type được hỗ trợ | Wildcard path index | Field động/nested metadata |

**Annotation không tạo một kiểu query mới**. Khi index đã tồn tại, repository, MongoTemplate và Java Driver đều sử dụng query planner của MongoDB.

### 16.1. Annotation và phiên bản

Một số option/annotation mới có thể không tồn tại trong những phiên bản Spring Data cũ. Đặc biệt, TTL duration option, xử lý nested/map và một số index options cần được xác minh với API dependency thực tế.

Đừng chép option từ tài liệu phiên bản mới vào dự án cũ rồi coi lỗi compile là lỗi MongoDB Server.

## 17. Auto-index-creation: annotation không tự xuất hiện ở database

Từ Spring Data MongoDB **3.0**, tính năng **tự động tạo index từ annotation không bật mặc định**. Khi chỉ khai báo:

~~~java
@Indexed(unique = true)
private String sku;
~~~

không có gì đảm bảo index được tạo lúc startup nếu cơ chế tạo index không bật hoặc không có migration riêng.

### 17.1. Cấu hình Spring Boot

Trong nhiều phiên bản Spring Boot có cấu hình:

~~~yaml
spring:
  data:
    mongodb:
      auto-index-creation: true
~~~

Đây là **cấu hình ví dụ**, cần đối chiếu phiên bản Spring Boot và auto-configuration đang sử dụng. Nó cho phép Spring Data tạo các index được khai báo cho entity thuộc mapping context.

### 17.2. Cấu hình Java khi tự dùng MongoClientConfiguration

~~~java
import org.springframework.data.mongodb.config.AbstractMongoClientConfiguration;

public class MongoConfig extends AbstractMongoClientConfiguration {

    @Override
    protected String getDatabaseName() {
        return "catalog";
    }

    @Override
    protected boolean autoIndexCreation() {
        return true;
    }
}
~~~

Ví dụ minh họa hook của Spring Data; cấu hình ứng dụng thực còn phải khai báo nguồn kết nối và đăng ký đúng cách. **Không thêm AbstractMongoClientConfiguration song song chỉ để bật index nếu tạo ra các bean kết nối trùng lặp với Spring Boot**.

### 17.3. Auto-index tạo lúc nào?

Spring Data có thể tạo index cho những entity được mapping context nhận diện lúc khởi tạo/first access, tùy cấu hình. Nhưng **không nên coi đây là migration đầy đủ**:

- Không tự xóa các index cũ không còn trong annotation.
- Không tự bảo đảm đổi tất cả option/names của index đã có.
- Không tự khôi phục mọi index nếu collection bị xóa/tạo lại trong lúc runtime.
- Không thay thế review index trên collection lớn.
- Có thể gặp lỗi startup nếu unique index phải tạo trên dữ liệu đã trùng.

Trong production, nhiều dự án chọn migration có version và rollout có kiểm soát, thay vì để mọi instance ứng dụng cùng thực hiện tạo index ở startup.

### 17.4. Local có index, production không có

Nếu local bật auto-index-creation=true còn production không bật và chưa có migration, repository vẫn có thể trả dữ liệu đúng nhưng explain cho thấy COLLSCAN.

**Sự hiện diện annotation trong source không chứng minh server index tồn tại.** Cần đọc getIndexes trong chính deployment cần kiểm tra.

## 18. Tạo index chủ động bằng MongoTemplate

Spring Data cung cấp **IndexOperations** để tạo index tường minh:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;

public void ensureTenantSkuIndex(MongoTemplate template) {
    template.indexOps(ProductDocument.class).ensureIndex(
        new Index()
            .on("tenantId", Sort.Direction.ASC)
            .on("sku", Sort.Direction.ASC)
            .unique()
            .named("uk_products_tenant_sku")
    );
}
~~~

Khi dùng **indexOps(ProductDocument.class)**, mapping metadata có thể chuyển property Java thành field BSON phù hợp. Vẫn cần kiểm tra getIndexes để xác nhận key **tenant_id** và các options thực tế.

### 18.1. IndexDefinition

IndexOperations.ensureIndex nhận một **IndexDefinition**. Các builder/index definition có thể mô tả:

- Key pattern và hướng sort.
- Unique, sparse, partial.
- TTL khi server hỗ trợ.
- Tên index.
- Một số options như collation hoặc language theo khả năng version.

Không mặc định mọi method builder tồn tại ở mọi phiên bản Spring Data.

### 18.2. Partial index programmatic

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.index.Index;
import org.springframework.data.mongodb.core.index.PartialIndexFilter;
import org.springframework.data.mongodb.core.query.Criteria;

Index index = new Index()
    .on("tenantId", Sort.Direction.ASC)
    .on("displayCode", Sort.Direction.ASC)
    .unique()
    .partial(PartialIndexFilter.of(
        Criteria.where("active").is(true)
    ))
    .named("uk_active_tenant_display_code");

template.indexOps(ProductDocument.class).ensureIndex(index);
~~~

Ví dụ giả định **displayCode** đã được thêm vào entity và Spring Data version có API partial tương ứng. Nếu chỉ có mẫu entity ở phần 2, cần mở rộng schema trước.

### 18.3. ensureIndex không thay thế migration

“Ensure” hướng đến việc tạo/đảm bảo có index mong muốn, **không có nghĩa tự thay đổi mọi index cũ cùng tên, tự dọn dữ liệu duplicate hoặc tự drop index không tương thích**.

Quy trình production:

1. Đọc index hiện tại.
2. Đánh giá dữ liệu trùng và chi phí tạo index.
3. Tạo index mới theo kế hoạch.
4. Xác minh query chuyển sang dùng index mới.
5. Chỉ cân nhắc dọn index cũ sau khi đo ổn định.

Không tự động drop index trong startup hook chỉ vì annotation đã đổi.

## 19. IndexResolver: đọc index metadata từ entity

**MongoPersistentEntityIndexResolver** dùng metadata mapping để xác định các index đã khai báo.

~~~java
import org.springframework.data.mongodb.core.index.IndexDefinition;
import org.springframework.data.mongodb.core.index.MongoPersistentEntityIndexResolver;
import org.springframework.data.mongodb.core.mapping.MongoMappingContext;

public void ensureDeclaredIndexes(
        MongoTemplate template,
        MongoMappingContext mappingContext) {

    var resolver =
        new MongoPersistentEntityIndexResolver(mappingContext);

    for (IndexDefinition definition :
            resolver.resolveIndexFor(ProductDocument.class)) {
        template.indexOps(ProductDocument.class)
            .ensureIndex(definition);
    }
}
~~~

Mẫu này mô tả **annotation → IndexDefinition → ensureIndex**. Không chạy resolver/ensureIndex tùy tiện theo mỗi HTTP request, vì tạo index là thay đổi schema và có chi phí.

### 19.1. Map-like properties

Index resolver không thể suy đoán tất cả key runtime của một Map chứa field động. Một số cấu trúc cần @WildcardIndexed hoặc index definition chỉ rõ đường dẫn. Việc quét entity không thay thế hiểu biết về dữ liệu BSON thực.

### 19.2. Thời điểm kích hoạt

Trong cấu hình của nhiều ứng dụng, cơ chế ensure index được gọi khi application context đã sẵn sàng và mapping metadata đầy đủ. Trong môi trường nhiều instance, nên điều phối qua migration runner hoặc lifecycle có kiểm soát để tránh race và tải trùng.

**IndexResolver không sửa dữ liệu cũ**: nó chỉ biến metadata thành index definitions.

## 20. Kiểm tra index thật: getIndexes/listIndexes

Sau khi tạo:

~~~javascript
db.products.getIndexes();
~~~

Một kết quả rút gọn có thể gồm:

~~~javascript
[
  {
    name: "_id_",
    key: { _id: 1 },
    unique: true
  },
  {
    name: "uk_products_tenant_sku",
    key: { tenant_id: 1, sku: 1 },
    unique: true
  },
  {
    name: "idx_products_tenant_active_updated",
    key: { tenant_id: 1, active: 1, updatedAt: -1 }
  }
]
~~~

Kết quả trên là ví dụ giản lược; metadata MongoDB có thể chứa nhiều options khác.

### 20.1. Java Driver

~~~java
import org.bson.Document;

for (Document index :
        mongoTemplate.getCollection("products").listIndexes()) {
    System.out.println(index.toJson());
}
~~~

Đây là API đọc metadata index. Không mở public endpoint trả toàn bộ index/schema nếu không có mục đích và phân quyền rõ ràng.

### 20.2. Đọc cả key lẫn options

Với unique compound index, hãy xác minh:

- **Key pattern**, field và thứ tự.
- **unique**, **sparse**, **partialFilterExpression**.
- **collation** khi uniqueness cần phân biệt/không phân biệt hoa thường.
- **expireAfterSeconds** cho TTL.
- **Index type**: text, 2dsphere, hashed, wildcard.
- **Name** để truy vết vận hành.

Đúng tên nhưng sai key/options vẫn có thể khiến hệ thống mất ràng buộc hoặc không đạt hiệu năng.

## 21. Explain: đánh giá index có giúp truy vấn không

Repository có method:

~~~java
List<ProductDocument> findTop20ByTenantIdAndActiveOrderByUpdatedAtDesc(
    String tenantId, boolean active
);
~~~

Truy vấn MongoDB tương tự:

~~~javascript
db.products.find({
  tenant_id: "shop-a",
  active: true
})
.sort({ updatedAt: -1 })
.limit(20)
.explain("executionStats");
~~~

Index ứng viên:

~~~javascript
{ tenant_id: 1, active: 1, updatedAt: -1 }
~~~

| Chỉ số | Câu hỏi |
| --- | --- |
| winningPlan | Planner có chọn index mong muốn? |
| IXSCAN/COLLSCAN | Quét index hay collection? |
| totalKeysExamined | Duyệt bao nhiêu index key? |
| totalDocsExamined | Đọc bao nhiêu document? |
| nReturned | Trả bao nhiêu document? |
| SORT | Có cần sort thêm trong RAM/engine? |
| executionTimeMillis | Độ trễ với dữ liệu đại diện? |

### 21.1. Examined và returned

Nếu chỉ trả 20 document nhưng quét hàng triệu document, index có thể chưa phù hợp. Tuy vậy, không chỉ dựa vào một tỷ lệ: cần xét filter, projection, sort, dữ liệu và mục tiêu báo cáo.

### 21.2. Covered query

Một số truy vấn có thể được phục vụ chỉ từ index, không cần fetch document gốc khi filter và những field trả về đều nằm trong index và đáp ứng các ràng buộc khác.

~~~javascript
db.products.find(
  { tenant_id: "shop-a", sku: "BOOK-001" },
  { _id: 0, tenant_id: 1, sku: 1 }
);
~~~

Không mặc định query repository trả đủ ProductDocument là covered, vì nhiều field không nằm trong index. Mapping DTO ở Java cũng không chắc giảm các field BSON mà database đã trả.

### 21.3. Hint cần có bằng chứng

MongoDB có **hint** để chọn index trong một số truy vấn. Ép một index không phù hợp có thể làm query chậm, đặc biệt với sparse/partial index. Chỉ dùng khi đã đo đạc và quản lý vòng đời index ổn định.

## 22. Collation và unique không phân biệt hoa thường

Giả sử hai email:

~~~text
Alice@example.com
alice@example.com
~~~

phải được xem là trùng. Unique index với collation mặc định **không nhất thiết coi hai chuỗi là bằng nhau**. Có thể dùng normalization hoặc index collation phù hợp:

~~~javascript
db.accounts.createIndex(
  { tenantId: 1, email: 1 },
  {
    unique: true,
    name: "uk_tenant_email_ci",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
~~~

**Collation ảnh hưởng phép so sánh chuỗi**; truy vấn muốn sử dụng index hiệu quả thường cần collation tương thích với index.

### 22.1. Tương thích Spring Data

Một số index options có thể được khai báo qua annotation hoặc index builder tùy phiên bản. Nếu uniqueness/collation là ràng buộc quan trọng, hãy dùng IndexDefinition/migration tường minh khi cần và kiểm thử các trường hợp chỉ khác chữ hoa thường.

### 22.2. Normalization là chính sách riêng

Chuyển email về chữ thường trước khi lưu có thể hỗ trợ một contract, nhưng phải xét chính sách ứng dụng. Không xem mọi chuỗi tiếng Việt, tên người và business key có cùng quy tắc case folding.

## 23. Thay đổi index trên production: xem như schema migration

Với collection có hàng chục triệu document, tạo index là một **thay đổi hạ tầng dữ liệu**, không chỉ là thêm một annotation trong pull request.

### 23.1. Quy trình đề xuất

1. **Xác định workload:** filter, sort, projection, tần suất và dữ liệu thực.
2. **Đo baseline:** explain, latency, index size và chi phí ghi.
3. **Đề xuất index:** key order, unique, partial, TTL hoặc loại chuyên biệt.
4. **Kiểm tra dữ liệu cũ:** null/missing, trùng, kiểu BSON, mapping @Field.
5. **Thử trên staging với dữ liệu đại diện**, bao gồm ghi đồng thời.
6. **Lập kế hoạch build:** dung lượng, CPU/disk, server version và tính sẵn sàng.
7. **Tạo qua migration có kiểm soát** thay vì mặc định mọi app instance tự chạy startup.
8. **Xác minh getIndexes:** đúng keys, name và options.
9. **Đo lại query plan:** query có dùng index dự kiến, latency cải thiện không?
10. **Quan sát write performance** rồi mới cân nhắc bỏ index không cần thiết.

### 23.2. Đổi annotation không tự nâng cấp index đang tồn tại

Nếu đổi:

~~~java
@Indexed(unique = false)
private String sku;
~~~

thành:

~~~java
@Indexed(unique = true)
private String sku;
~~~

không được giả định một index không unique trước đây tự biến thành unique, hoặc dữ liệu trùng tự được loại. Cần kiểm tra option hiện tại và cách triển khai migration phù hợp với MongoDB Server.

### 23.3. Không tự drop index ngoài kế hoạch

~~~javascript
db.products.dropIndex("idx_old_name");
~~~

Đây là lệnh có tác dụng thật, **không nên chạy trên production chỉ vì một annotation đã bị xóa trong source**. Index có thể vẫn đang phục vụ một query khác. Trước khi drop, cần đối chiếu metrics/query plans và chuẩn bị rollback.

## 24. Kiểm thử tích hợp compound unique index

Unit test chỉ mock repository không thể chứng minh MongoDB Server đã tạo index hay unique constraint hoạt động. Cần **MongoDB test instance** và đọc metadata thực.

### 24.1. Entity thử nghiệm

~~~java
package com.example.catalog;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "index_test_products")
@CompoundIndex(
    name = "uk_test_tenant_sku",
    def = "{ 'tenantId': 1, 'sku': 1 }",
    unique = true
)
public record IndexedProduct(
    @Id ObjectId id,
    String tenantId,
    String sku,
    String name
) {}
~~~

Ở đây không có @Field đổi tên tenantId, nên index definition dùng đúng BSON key **tenantId**.

### 24.2. Test JUnit 5 với MongoTemplate

~~~java
package com.example.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class ProductIndexIntegrationTest {

    @Autowired MongoTemplate template;

    @Test
    void compoundUniqueWorksWithinTenant() {
        // Test chủ động ensure index, không phụ thuộc auto-index flag.
        template.indexOps(IndexedProduct.class).ensureIndex(
            new Index()
                .on("tenantId", Sort.Direction.ASC)
                .on("sku", Sort.Direction.ASC)
                .unique()
                .named("uk_test_tenant_sku")
        );

        IndexedProduct first = new IndexedProduct(
            new ObjectId(), "shop-test-a", "BOOK-001", "A"
        );
        IndexedProduct otherTenant = new IndexedProduct(
            new ObjectId(), "shop-test-b", "BOOK-001", "B"
        );
        IndexedProduct duplicate = new IndexedProduct(
            new ObjectId(), "shop-test-a", "BOOK-001", "Duplicate"
        );

        try {
            template.insert(first);
            template.insert(otherTenant);

            assertThatThrownBy(() -> template.insert(duplicate))
                .isInstanceOf(DuplicateKeyException.class);

            long countA = template.count(
                Query.query(Criteria.where("tenantId").is("shop-test-a")),
                IndexedProduct.class
            );
            assertThat(countA).isEqualTo(1L);

            boolean hasUniqueIndex = false;
            for (Document index :
                    template.getCollection(
                        "index_test_products").listIndexes()) {
                if ("uk_test_tenant_sku".equals(
                        index.getString("name"))) {
                    hasUniqueIndex = Boolean.TRUE.equals(
                        index.getBoolean("unique")
                    );
                }
            }
            assertThat(hasUniqueIndex).isTrue();
        } finally {
            template.remove(
                Query.query(Criteria.where("_id").in(
                    List.of(
                        first.id(),
                        otherTenant.id(),
                        duplicate.id()
                    )
                )),
                IndexedProduct.class
            );
        }
    }
}
~~~

Test:

- Chủ động tạo index để không phụ thuộc auto-index-creation.
- Chèn cùng SKU ở hai tenant khác nhau, hợp lệ.
- Chèn trùng SKU trong cùng tenant, kỳ vọng DuplicateKeyException.
- Đọc metadata để xác nhận index là unique.
- Dọn fixture theo các ID đã tạo.

**Chỉ chạy test trên MongoDB test riêng.** Nếu chạy test song song, cần tạo tenant/SKU riêng hoặc database cô lập để tránh xung đột giữa các fixture.

### 24.3. Kiểm thử metadata annotation độc lập

Test trên chứng minh unique constraint **sau khi ensureIndex tường minh**, nhưng chưa chứng minh @CompoundIndex annotation đã được index resolver đọc.

Nếu muốn test annotation:

1. Dùng MongoPersistentEntityIndexResolver để đọc IndexedProduct metadata.
2. Kiểm tra IndexDefinition có key pattern tenantId+sku và unique option.
3. Dùng definition được đọc để tạo index trong database test.
4. Đọc getIndexes và xác nhận key/options.

Cách tách này giúp phân biệt lỗi annotation/config với lỗi server index.

## 25. Kiểm thử TTL và partial unique

### 25.1. TTL không nên test bằng sleep rất ngắn

Test tạo một session hết hạn rồi đợi 100ms và assert document đã biến mất thường không ổn định, vì TTL monitor chạy bất đồng bộ.

Kiểm thử tốt hơn:

- Xác minh index trên **expiresAt** có **expireAfterSeconds=0**.
- Xác minh expiresAt lưu dưới BSON Date.
- Kiểm thử ứng dụng từ chối session khi expiresAt đã qua.
- Nếu cần test cleanup vật lý, dùng polling với timeout đủ rộng trong test integration, không đòi xóa chính xác theo mili giây.

**TTL để dọn dữ liệu, không phải tiêu chuẩn xác thực session còn hiệu lực.**

### 25.2. Partial unique phải test chuyển trạng thái

Với unique index chỉ áp dụng cho active=true:

1. Hai document inactive có cùng displayCode có thể cùng tồn tại nếu không có constraint khác.
2. Chuyển document thứ nhất sang active có thể thành công.
3. Chuyển document thứ hai sang active với cùng tenant/displayCode sẽ bị unique constraint từ chối.
4. Kiểm tra query active=true có cơ hội dùng partial index hay không.

Test quan trọng vì partial unique tác động cả **insert lẫn update** đưa document vào tập được index.

## 26. Reactive repository và index

**ReactiveMongoRepository** sử dụng cùng collection, cùng indexes và query planner như repository đồng bộ.

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveProductRepository
        extends ReactiveMongoRepository<ProductDocument, ObjectId> {

    Mono<ProductDocument> findByTenantIdAndSku(
        String tenantId, String sku
    );

    Flux<ProductDocument> findByTenantIdAndActive(
        String tenantId, boolean active
    );
}
~~~

Nếu database có compound index **tenant_id + sku**, findByTenantIdAndSku từ reactive repository có cơ hội dùng cùng index đó, miễn Spring Data ánh xạ truy vấn đúng và MongoDB planner lựa chọn index.

### 26.1. Reactive không miễn chi phí index

Non-blocking I/O không làm một COLLSCAN bớt tiêu tốn CPU/disk trên server. Query plan không tối ưu vẫn làm reactive application nhận kết quả chậm.

### 26.2. ReactiveMongoTemplate indexOps

Spring Data có API indexOps reactive. Việc tạo index qua ReactiveMongoTemplate có thể trả Mono, và **cần có subscription/await theo lifecycle** để lệnh thực sự thực hiện.

Với migration, hãy đảm bảo cơ chế startup chờ hoàn thành trước khi nhận traffic theo chính sách dự án. Đừng chỉ tạo Mono rồi bỏ nó, hoặc gọi block() trên event loop WebFlux.

## 27. Những sai lầm thường gặp

| Hiện tượng / giả định | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Có @Indexed nhưng explain COLLSCAN | Index chưa tạo hoặc planner không dùng | getIndexes, kiểm tra config và query plan |
| Hai field đều @Indexed mà query chậm | Hai index đơn không thành compound | Thiết kế @CompoundIndex theo workload |
| SKU của hai tenant bị từ chối | Unique trên sku toàn collection | Compound unique tenant+sku |
| Unique index tạo không thành công | Dữ liệu cũ trùng, null/missing không phù hợp | Migration dữ liệu an toàn |
| Partial unique không áp dụng inactive | Filter partial cố ý loại inactive | Kiểm tra invariant nghiệp vụ |
| Session hết hạn vẫn còn | TTL monitor bất đồng bộ | Kiểm tra expiresAt trong nghiệp vụ |
| TTL không xóa timestamp dạng String | Field không phải BSON Date | Sửa schema/di chuyển dữ liệu |
| Text search khác regex | Text tokenization khác substring | Chọn đúng text/regex/search |
| Geo query trả vị trí sai | Đảo longitude/latitude hoặc sai đơn vị | Kiểm tra GeoJSON và 2dsphere |
| Hashed index không hỗ trợ sort | Hash không giữ thứ tự | Dùng B-tree index phù hợp |
| Wildcard index lớn | Quá nhiều field động | Giới hạn phạm vi, index cụ thể |
| Query không dùng partial index | Filter không bao hàm điều kiện partial | Kiểm tra predicate và explain |
| Nested field index sai | @Field hoặc path/prefix khác | getIndexes, raw BSON |
| Bật auto-index gây lỗi startup | Duplicate data/index conflict | Migration có kiểm soát |
| Annotation đổi nhưng index cũ còn | Index creation không tự drop/recreate | Lập kế hoạch index migration |
| Ghi chậm sau khi thêm nhiều index | Mỗi lần ghi phải cập nhật nhiều index | Review và gỡ index thừa có kiểm soát |
| API reactive vẫn chậm | Query plan server không tối ưu | Tối ưu filter/index |

### 27.1. Quy trình chẩn đoán một truy vấn chậm

1. Xác định filter, sort, projection và limit thật.
2. Xác minh collection và tên field BSON (nhất là @Field).
3. Đọc getIndexes, không đoán từ annotation.
4. Kiểm tra index key order, unique, partial, sparse, TTL, collation.
5. Chạy explain("executionStats") với dữ liệu đại diện.
6. Đọc IXSCAN/COLLSCAN, keysExamined/docsExamined, SORT/FETCH.
7. Đo latency với cùng limit và tải phù hợp.
8. Nếu index sai, cân nhắc sửa query hoặc index mới.
9. Đo chi phí ghi/lưu trữ sau khi thêm index.
10. Kiểm thử hồi quy và rollout từng bước.

## 28. Bài tập thực hành

### Bài tập 1: single-field

Cần tìm product theo SKU, không yêu cầu unique. Khai báo?

~~~java
@Indexed(name = "idx_products_sku")
private String sku;
~~~

**Giải thích:** annotation cần được tạo thật trên MongoDB bằng auto-index hoặc migration.

### Bài tập 2: unique theo tenant

SKU được phép trùng giữa shop-a/shop-b nhưng không trùng trong cùng tenant. Dùng annotation nào?

~~~java
@CompoundIndex(
    name = "uk_tenant_sku",
    def = "{ 'tenant_id': 1, 'sku': 1 }",
    unique = true
)
~~~

**Đáp án:** compound unique tenant+sku, không unique sku đơn.

### Bài tập 3: hai @Indexed

~~~java
@Indexed private String tenantId;
@Indexed private String status;
~~~

Hai dòng có tạo compound index {tenantId:1,status:1} không?

**Đáp án:** Không. Chúng là hai index đơn.

### Bài tập 4: compound filter và sort

Query thường filter tenant, active và sort updatedAt DESC. Index ứng viên?

**Đáp án:** { tenant_id: 1, active: 1, updatedAt: -1 }. Đo explain để xác nhận lợi ích.

### Bài tập 5: sparse và null

optionalCode có @Indexed(sparse=true, unique=true). Có thể khẳng định mọi document có optionalCode=null không bị index không?

**Đáp án:** Không. Sparse không đồng nghĩa bỏ explicit null. Phải hiểu null/missing và cân nhắc partial unique.

### Bài tập 6: soft delete

Chỉ muốn unique displayCode khi product active. Index phù hợp?

**Đáp án:** compound unique có partialFilterExpression: {active:true}; cần test inactive→active gây duplicate.

### Bài tập 7: TTL

Session có expiresAt là BSON Date. Muốn cleanup sau thời điểm đó:

~~~java
@Indexed(expireAfterSeconds = 0)
private Instant expiresAt;
~~~

**Giải thích:** TTL dọn vật lý bất đồng bộ, không bảo đảm tức thời.

### Bài tập 8: session hết hạn

Session còn trong database 20 giây sau expiresAt. Có được truy cập không?

**Đáp án:** Không. Service phải kiểm tra expiresAt khi xác thực.

### Bài tập 9: text

Article cần tìm theo title và body, title quan trọng hơn?

**Đáp án:** @TextIndexed ở hai field với weight phù hợp; TextCriteria/$text; kiểm tra language và tokenization.

### Bài tập 10: geospatial

Store lưu GeoJsonPoint theo longitude/latitude. Index cho $near spherical?

**Đáp án:** @GeoSpatialIndexed(type=GeoSpatialIndexType.GEO_2DSPHERE), xác minh 2dsphere index.

### Bài tập 11: hashed

Hashed index trên deviceId có bảo đảm deviceId unique không?

**Đáp án:** Không. Hashed index không thay unique constraint.

### Bài tập 12: wildcard

Product có attributes động gồm ramGb, color, size. Khi nào wildcard index hữu ích?

**Đáp án:** Khi truy vấn nhiều field không biết trước trong một nhánh metadata, sau khi đo index size và xem có cần index cụ thể cho field phổ biến.

### Bài tập 13: auto creation

Entity có annotation index nhưng production getIndexes chỉ có _id. Vì sao?

**Đáp án:** Index metadata chưa được tạo nếu auto-index-creation tắt hoặc migration chưa chạy.

### Bài tập 14: thay unique option

Thay @Indexed(unique=false) thành unique=true có đủ để bảo vệ production?

**Đáp án:** Không. Phải kiểm tra dữ liệu trùng, index cũ và migration đúng key/options.

### Bài tập 15: explain

Index tồn tại nhưng query trả 20 document trong khi totalDocsExamined rất lớn. Xử lý?

**Đáp án:** So sánh filter/sort/projection, key order, index options và explain; đo trước khi thêm index.

### Bài tập 16: collation

Email Alice@example.com và alice@example.com phải được coi trùng. Unique index mặc định luôn đủ không?

**Đáp án:** Không. Cần normalization/collation phù hợp và test ràng buộc.

## 29. Checklist production

- **Query:** có filter/sort/limit thực tế chứng minh nhu cầu index chưa?
- **Key order:** compound index có đúng prefix và chiều sort chưa?
- **Mapping:** @Field/@Id có dẫn tới BSON field đúng chưa?
- **Unique:** duy nhất toàn collection hay theo tenant?
- **Null/missing:** optional field có cần partial hoặc sparse không?
- **Partial:** filter có đúng chính sách active/soft-delete không?
- **TTL:** field lưu BSON Date và hiểu cleanup bất đồng bộ không?
- **Text:** ngôn ngữ, scoring và semantics text search phù hợp chưa?
- **Geo:** đúng GeoJSON longitude/latitude, 2dsphere, đơn vị chưa?
- **Hashed:** không dùng cho range/sort hoặc unique chưa?
- **Wildcard:** đã giới hạn metadata và kiểm soát dung lượng chưa?
- **Creation:** annotation đã được IndexResolver/auto-index/migration thực thi chưa?
- **Rollout:** đã kiểm tra dữ liệu cũ, chi phí build, index conflicts chưa?
- **Runtime:** getIndexes có đúng keys/options không?
- **Performance:** explain có cải thiện keys/docs examined và latency không?
- **Write load:** số index có làm ghi chậm quá mức không?
- **Testing:** đã test duplicate key, partial transition, TTL metadata và mapping chưa?
- **Reactive:** index có được tạo trước traffic và query plan được kiểm tra chưa?

## 30. Tổng kết

1. **@Indexed** mô tả single-field index; nhiều @Indexed riêng không tự tạo compound index.
2. **@CompoundIndex** mô tả nhiều field theo thứ tự, đặc biệt quan trọng với tenant+business key hoặc filter+sort.
3. **Unique index** bảo vệ ràng buộc tại MongoDB; check exists ở Java không đủ chống race.
4. **Sparse/partial index** thay đổi tập document được index; cần hiểu null/missing và phạm vi unique.
5. **TTL index** dọn dữ liệu bất đồng bộ, không thay kiểm tra hạn ở nghiệp vụ.
6. **@TextIndexed** phục vụ text search, không phải regex/substring bất kỳ.
7. **@GeoSpatialIndexed** phục vụ tìm kiếm địa lý, cần đúng GeoJSON/2dsphere.
8. **@HashIndexed** hỗ trợ các use case equality/shard key, không thay unique hoặc ordered index.
9. **@WildcardIndexed** hỗ trợ field động nhưng có chi phí và giới hạn.
10. **Annotation không đảm bảo index tồn tại trên server**; cần auto-index-creation hoặc migration và kiểm tra getIndexes.
11. **IndexOperations/IndexResolver** hỗ trợ tạo index rõ ràng; migration production cần kế hoạch.
12. **Hiệu quả index phải đo trên workload và explain**, không chỉ bởi code compile.
13. **Repository đồng bộ/reactive dùng chung indexes**, nhưng quy trình triển khai index cần quản lý riêng.
14. **Kiểm thử MongoDB thật** cần chứng minh constraint, metadata/options, mapping và hiệu năng truy vấn.

Nắm vững **@Indexed, @CompoundIndex và annotation chỉ mục chuyên biệt** giúp dịch vụ **SPRING_DATA_MONGODB** chuyển từ truy vấn đúng nhưng chậm sang thiết kế index có căn cứ, bảo vệ bất biến dữ liệu và quản lý vòng đời schema an toàn, hiệu quả hơn.

### Tài liệu tham khảo

- [Spring Data MongoDB — Index Creation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html) — auto-index creation, index resolver và annotations.
- [Spring Data MongoDB — @Indexed API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/index/Indexed.html) — unique, sparse, TTL và partial.
- [Spring Data MongoDB — @CompoundIndex API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/index/CompoundIndex.html) — def, unique, partial filter và index name.
- [MongoDB Manual — Indexes](https://www.mongodb.com/docs/manual/indexes/) — index planner, compound, text, geospatial, hashed, wildcard.
- [MongoDB Manual — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/) — ràng buộc TTL và cleanup.

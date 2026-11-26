# #n1ql.filter và lọc đúng kiểu entity trong Spring Data Couchbase

> **Mục tiêu:** Hiểu `#{#n1ql.filter}` giúp Spring Data Couchbase giới hạn document theo **loại entity** như thế nào; phân biệt discriminator với metadata Couchbase, điều kiện nghiệp vụ và điều kiện phân quyền; viết `@Query` đúng khi nhiều loại document nằm chung collection; xử lý dữ liệu thiếu trường loại và kiểm tra kết quả khi dùng Repository, chỉ mục hoặc API reactive.

Trong module **SPRING_DATA_COUCHBASE**, Spring Data ánh xạ Java object thành JSON document tại một **bucket/scope/collection** của Couchbase. Repository và `CouchbaseTemplate` giúp truy cập document bằng mapping; truy vấn SQL++ cho phép tìm theo thuộc tính, JSON lồng nhau và mảng. Khi đã biết document ID, đường Key/Value thường phù hợp; khi cần tìm theo điều kiện, Query Service xử lý câu SQL++ thông qua các chỉ mục.

Vì Couchbase lưu JSON bán cấu trúc, cùng một collection có thể chứa nhiều **loại dữ liệu**. Ví dụ collection `documents` có thể lưu cả `Product` và `Promotion`. Hai document có cùng trường `category`, nhưng một bên là sản phẩm để bán, bên kia là chương trình khuyến mại. Repository trả `Product` không nên vô tình đọc cả `Promotion` chỉ vì cả hai khớp điều kiện `category = "keyboard"`.

Spring Data Couchbase cung cấp biểu thức **Spring Expression Language (SpEL)** `#{#n1ql.filter}` nhằm tạo điều kiện lọc theo thông tin kiểu entity do mapping quản lý. Tên `n1ql` được giữ theo tên cũ **N1QL**; ngôn ngữ truy vấn Couchbase hiện được gọi là **SQL++**.

**Phân biệt ba câu hỏi:**

| Câu hỏi | Cơ chế cần xét | Ví dụ |
| --- | --- | --- |
| Đây có phải document của entity `Product` không? | **Type discriminator**, hỗ trợ bởi `#{#n1ql.filter}` | Loại `Promotion` khi query `ProductRepository` |
| Đây có phải sản phẩm keyboard đang bán không? | **Điều kiện nghiệp vụ SQL++** | `category = $category AND active = true` |
| Người gọi có quyền nhìn thấy document này không? | **Authorization/tenant filter** của ứng dụng | `tenantId = $trustedTenantId`, quyền truy cập theo vai trò |

**`#n1ql.filter` chỉ giải quyết câu hỏi về kiểu entity** theo quy tắc mapping. Nó không tự kiểm tra trạng thái hoạt động, quyền của người dùng, tenant hay khóa định danh nghiệp vụ.

## 1. Bộ dữ liệu mẫu: nhiều loại document trong cùng collection

Giả sử ứng dụng có bucket `catalog`, scope `commerce` và collection `documents`. Hai kiểu entity `Product` và `Promotion` cùng được lưu ở đây để làm rõ bài toán. Đây là một **thiết kế minh họa**, không phải khuyến nghị mọi hệ thống phải trộn tất cả entity trong một collection.

**Document ID: `product::KB-100` — sản phẩm**

```json
{
  "_class": "catalog-product",
  "sku": "KB-100",
  "category": "keyboard",
  "name": "Bàn phím cơ TKL",
  "price": 1500000,
  "active": true,
  "tenantId": "shop-a"
}
```

**Document ID: `product::KB-200` — sản phẩm**

```json
{
  "_class": "catalog-product",
  "sku": "KB-200",
  "category": "keyboard",
  "name": "Bàn phím không dây",
  "price": 1900000,
  "active": false,
  "tenantId": "shop-a"
}
```

**Document ID: `product::KB-300` — sản phẩm của tenant khác**

```json
{
  "_class": "catalog-product",
  "sku": "KB-300",
  "category": "keyboard",
  "name": "Bàn phím gọn nhẹ",
  "price": 950000,
  "active": true,
  "tenantId": "shop-b"
}
```

**Document ID: `promotion::BLACKFRIDAY` — chương trình khuyến mại**

```json
{
  "_class": "catalog-promotion",
  "code": "BLACKFRIDAY",
  "category": "keyboard",
  "name": "Khuyến mại bàn phím",
  "active": true,
  "discountRate": 0.15,
  "tenantId": "shop-a"
}
```

**Document ID: `legacy::KB-OLD` — dữ liệu nhập thủ công, thiếu type**

```json
{
  "sku": "KB-OLD",
  "category": "keyboard",
  "name": "Bàn phím đời cũ",
  "price": 400000,
  "active": true,
  "tenantId": "shop-a"
}
```

Các giá trị `"_class": "catalog-product"` và `"_class": "catalog-promotion"` trên **minh họa** một cấu hình dùng alias kiểu trong Spring Data. **Không giả định mọi ứng dụng thực tế đều có chính xác các chuỗi này**: giá trị discriminator có thể là tên class đầy đủ, alias hoặc tên trường khác tùy cách mapping được cấu hình. Khi tự chèn JSON ngoài Spring Data, cần bảo đảm type information tương thích với converter.

Nếu chạy một câu SQL++ không lọc kiểu:

```sql
SELECT META(d).id AS documentId,
       d.category,
       d.name
FROM `catalog`.`commerce`.`documents` AS d
WHERE d.category = "keyboard"
ORDER BY documentId;
```

thì **cả năm** document đều có thể được chọn: ba `Product`, một `Promotion` và một document legacy không có discriminator. Nhưng `ProductRepository` cần trả đúng loại entity mà nó quản lý, không thể lấy trường `category` làm bằng chứng rằng document là `Product`.

### Vì sao hai loại dữ liệu có thể trùng tên trường?

Document là JSON: tên trường `name`, `category` và `active` không được dành riêng cho một Java class. Bất kỳ document nào có thể chứa các trường đó. Nếu bộ lọc chỉ dùng:

```sql
WHERE d.category = "keyboard" AND d.active = true
```

thì `Promotion` vẫn có thể thỏa. Đối với repository dự kiến trả `Product`, điều kiện theo **loại entity** cần được áp dụng độc lập với điều kiện nghiệp vụ.

## 2. Type discriminator là gì? Có phải metadata Couchbase không?

**Discriminator** là thông tin phân biệt loại document mà Spring Data dùng trong ánh xạ object. Theo cấu hình mặc định thường gặp, Spring Data ghi một thuộc tính JSON như `_class` khi lưu entity.

Đừng nhầm trường này với **metadata nội tại** của Couchbase:

| Đặc điểm | Discriminator `_class` (thường gặp) | Metadata `META(d)` |
| --- | --- | --- |
| Nằm ở đâu? | Thường là một trường JSON body | Metadata do Couchbase quản lý ngoài body |
| Mục đích | Hỗ trợ xác định/khôi phục kiểu Java | ID, CAS, expiration và thông tin document |
| Có thể đọc bằng | `d._class` nếu field được lưu như vậy | `META(d).id`, `META(d).cas` |
| Có phụ thuộc converter Spring Data? | Có | Không phụ thuộc tên class Java |
| `#n1ql.filter` thường dựa vào | **Type discriminator** của mapping | Không phải một so sánh CAS/ID |

Ví dụ truy vấn quan sát:

```sql
SELECT META(d).id AS documentId,
       META(d).cas AS documentCas,
       d._class AS storedType,
       d.category
FROM `catalog`.`commerce`.`documents` AS d
WHERE d.category = "keyboard";
```

Ở các document mẫu, `storedType` có thể là `"catalog-product"`, `"catalog-promotion"` hoặc **MISSING** (document legacy). `META(d).id` vẫn có ID cho mọi document. `META(d).cas` có giá trị hiện tại do Couchbase quản lý; nó không phải trường thể hiện loại entity.

**Hai điều cần nhớ:**

- Trường type do Spring Data ghi **có thể thay đổi theo cấu hình converter**, trong khi `META(d).id` là document key thực.
- `_class` có thể là một field JSON hợp lệ, nhưng **không nên hardcode giả định về nó** khi có sẵn biểu thức mapping `#{#n1ql.filter}` dành cho Repository.

## 3. Định nghĩa hai entity dùng chung collection

Ví dụ Java minh họa dùng annotation `@TypeAlias` để biểu đạt tên kiểu ngắn. Với Spring Data, alias giúp tránh phụ thuộc vào tên class Java đầy đủ trong dữ liệu lưu, nhưng vẫn cần cấu hình mapping và converter nhất quán.

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.repository.Collection;
import org.springframework.data.couchbase.repository.Scope;

@Document
@TypeAlias("catalog-product")
@Scope("commerce")
@Collection("documents")
public class Product {
    @Id
    private String id;
    private String sku;
    private String category;
    private String name;
    private Long price;
    private Boolean active;
    private String tenantId;

    public Product() {}
    // Bổ sung getters/setters hoặc constructor theo convention dự án.
}
```

Entity chương trình khuyến mại dùng cùng scope/collection:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.TypeAlias;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.repository.Collection;
import org.springframework.data.couchbase.repository.Scope;

@Document
@TypeAlias("catalog-promotion")
@Scope("commerce")
@Collection("documents")
public class Promotion {
    @Id
    private String id;
    private String code;
    private String category;
    private String name;
    private Boolean active;
    private Double discountRate;
    private String tenantId;

    public Promotion() {}
    // Bổ sung getters/setters hoặc constructor theo convention dự án.
}
```

Bucket `catalog` được chọn từ cấu hình kết nối Spring Data. Annotation `@Scope` và `@Collection` định tuyến entity tới cùng collection `documents`. Khi lưu đúng thông qua converter, Spring Data có thể ghi discriminator tương ứng với alias của mỗi loại.

**Lưu ý kỹ thuật:** `@TypeAlias` chỉ có hiệu lực đúng khi Spring Data biết entity và mapping context/converter được cấu hình phù hợp. Hãy xác minh trường type thực tế sau khi lưu một document mẫu; không tự mặc định mọi phiên bản và tùy biến converter đều ghi `_class` với cùng giá trị.

## 4. `#{#n1ql.filter}` xuất hiện ở đâu trong `@Query`?

Trong phương thức Repository trả về **full entity**, Spring Data Couchbase cung cấp mẫu thường dùng:

```java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository
        extends CouchbaseRepository<Product, String> {

    @Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
         + "AND category = $category")
    List<Product> findByCategoryWithTypeFilter(
        @Param("category") String category
    );
}
```

Gọi:

```java
List<Product> keyboards =
    repository.findByCategoryWithTypeFilter("keyboard");
```

Với mapping và type alias của dữ liệu mẫu được lưu nhất quán qua Spring Data, danh sách nghiệp vụ chứa ba sản phẩm **KB-100**, **KB-200**, **KB-300**. Document `Promotion` mang `category = "keyboard"` vẫn không thuộc loại `Product`. Document legacy `KB-OLD` thiếu discriminator phù hợp cũng có thể bị loại theo cách Spring Data tạo type filter.

### Đọc đúng ba lớp của câu truy vấn

```text
#{#n1ql.selectEntity}  WHERE  #{#n1ql.filter}   AND  category = $category
└───── Spring Data ───┘         └─────┬──────┘       └────────┬────────┘
  Sinh SELECT / FROM         Điều kiện kiểu       Điều kiện nghiệp vụ
                            (Spring Data)        (giá trị binding)
```

- `#{#n1ql.selectEntity}` tạo phần `SELECT/FROM` thích hợp để ánh xạ entity, bao gồm thông tin cần cho ID và CAS.
- `WHERE` là từ khóa SQL++ do người viết đặt **một lần**.
- `#{#n1ql.filter}` là SpEL sinh **điều kiện theo kiểu entity** mà Spring Data quản lý.
- `AND category = $category` là điều kiện nghiệp vụ, giá trị `$category` được ràng buộc từ tham số `@Param("category")`.

**Không thêm một từ khóa `WHERE` ngay trước `AND category ...`** nếu đã có `WHERE #{#n1ql.filter}`. Câu SQL++ chỉ có một mệnh đề `WHERE`, bên trong có thể kết hợp nhiều điều kiện bằng `AND`/`OR`.

### Minh họa ý nghĩa SQL++ sau khi Spring Data xử lý SpEL

Không có lý do để hardcode chuỗi mà `#n1ql.filter` sinh ra, nhưng với mô hình `_class` minh họa, có thể hiểu logic tương đương ở mức nghiệp vụ như sau:

```sql
-- Minh họa ý nghĩa; KHÔNG phải lời cam kết về SQL++ do Spring Data sinh.
SELECT META(d).id AS documentId, d.sku, d.category
FROM `catalog`.`commerce`.`documents` AS d
WHERE d._class = "catalog-product"
  AND d.category = "keyboard";
```

**Không sao chép truy vấn minh họa thành định nghĩa cố định cho `#n1ql.filter`.** Spring Data có thể dùng tên thuộc tính discriminator khác, biểu thức type khác hoặc xử lý entity hierarchy tùy metadata và phiên bản. Điều quan trọng là Repository có thêm **bộ lọc kiểu** mà câu `WHERE category = ...` đơn thuần không thể hiện.

### Cách viết cho Repository khác

Khi Repository quản lý `Promotion`, cùng một mẫu dùng mapping của `Promotion`:

```java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PromotionRepository
        extends CouchbaseRepository<Promotion, String> {

    @Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
         + "AND category = $category")
    List<Promotion> findByCategory(
        @Param("category") String category
    );
}
```

Gọi `promotionRepository.findByCategory("keyboard")` chỉ cần trả các document thuộc loại `Promotion`, ở dữ liệu mẫu là chương trình `BLACKFRIDAY`. **Cùng điều kiện nghiệp vụ không có nghĩa cùng tập kết quả**, vì mỗi Repository có metadata entity khác nhau.

## 5. Kết hợp filter kiểu với điều kiện nghiệp vụ

`#n1ql.filter` không tự kiểm tra `active`. Để lấy các sản phẩm keyboard đang hoạt động:

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND category = $category "
     + "AND active = true")
List<Product> findActiveByCategory(
    @Param("category") String category
);
```

Trong dữ liệu mẫu, **KB-100** và **KB-300** là `Product` đang hoạt động thuộc keyboard; KB-200 bị loại vì `active = false`. `Promotion BLACKFRIDAY` có `active = true` và `category = "keyboard"` nhưng vẫn không phải `Product`.

### Khác nhau giữa type filter, `WHERE` và phép chiếu

| Thành phần | Tác dụng | Không tự làm gì? |
| --- | --- | --- |
| `#{#n1ql.filter}` | Xác định document thuộc kiểu entity nào | Không xác định hoạt động, giá, quyền truy cập |
| `AND active = true` | Lọc trạng thái kinh doanh | Không phân biệt `Product` và `Promotion` |
| `AND category = $category` | Lọc danh mục theo dữ liệu người gọi | Không áp dụng type discriminator |
| `#{#n1ql.selectEntity}` | Chiếu các trường/metadata cần dựng entity | Không thay cho toàn bộ điều kiện `WHERE` |

Một truy vấn chỉ có `WHERE #{#n1ql.filter}` có thể trả **mọi document của loại entity đó**, kể cả đã tắt hoặc thuộc tenant khác. Không được nhầm “đúng loại entity” với “được phép sử dụng cho tác vụ đang làm”.

### Viết điều kiện có `OR` đúng ngoặc

Giả sử cần lấy `Product` đang hoạt động nếu thuộc danh mục keyboard **hoặc** có giá không quá 1 triệu. Câu sau có thể sai ý định:

```java
// KHÔNG đúng ý định: một nhánh OR có thể vượt qua type filter.
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND active = true AND category = $category "
     + "OR price <= $maxPrice")
List<Product> incorrectOr(
    @Param("category") String category,
    @Param("maxPrice") long maxPrice
);
```

SQL++ áp dụng ưu tiên `AND` trước `OR`. Vì vậy, nhánh `price <= $maxPrice` có thể được đánh giá độc lập với discriminator. Nếu một document kiểu khác có trường `price` thỏa điều kiện, nó có thể lọt vào tập kết quả trước khi mapper cố dựng `Product`.

Cách đúng là **giữ toàn bộ điều kiện nghiệp vụ trong ngoặc sau type filter**:

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND active = true "
     + "AND (category = $category OR price <= $maxPrice)")
List<Product> findActiveMatchingCategoryOrPrice(
    @Param("category") String category,
    @Param("maxPrice") long maxPrice
);
```

Với dữ liệu mẫu và lời gọi `("keyboard", 1000000L)`, kết quả `Product` đang hoạt động là KB-100 và KB-300. KB-200 không hoạt động. Document `Promotion` bị loại bởi discriminator.

**Quy tắc bảo trì:** khi thêm `OR`, `ANY` hoặc những điều kiện phức tạp, đặt ngoặc sao cho **mọi nhánh hợp lệ đều phải đi qua bộ lọc kiểu entity** và các ràng buộc bảo mật.

## 6. Type filter không phải tenant filter hoặc phân quyền

Trong dữ liệu mẫu, `KB-100` và `KB-200` thuộc `tenantId = "shop-a"`, còn `KB-300` thuộc `tenantId = "shop-b"`. Cả ba đều mang type `Product`.

Nếu một request của `shop-a` gọi:

```java
repository.findByCategoryWithTypeFilter("keyboard");
```

thì **`#n1ql.filter` không tự loại sản phẩm của `shop-b`**. Type discriminator chỉ xác định loại entity, không chứng minh caller được xem document.

Để phục vụ mô hình multi-tenant, yêu cầu tenant phải được ràng buộc từ **security context đã xác thực**, không được tin trực tiếp tham số tenant do client tự khai báo:

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND tenantId = $tenantId "
     + "AND category = $category "
     + "AND active = true")
List<Product> findVisibleActiveProducts(
    @Param("tenantId") String trustedTenantId,
    @Param("category") String category
);
```

Service minh họa:

```java
public List<Product> listVisibleKeyboards() {
    String tenantId = currentTenantProvider.requireAuthorizedTenant();
    return productRepository.findVisibleActiveProducts(
        tenantId, "keyboard"
    );
}
```

`currentTenantProvider` chỉ là tên phụ thuộc minh họa; ứng dụng thật phải lấy tenant từ thông tin xác thực/ủy quyền và bảo đảm các thao tác ghi, đọc theo ID, query khác cũng kiểm soát tenant. Không có phương thức có sẵn mặc định tên `requireAuthorizedTenant()` trong Spring Data.

Với caller đã được phép truy cập `shop-a`, kết quả còn **KB-100**. KB-200 bị loại vì không active; KB-300 bị loại vì khác tenant. `Promotion` bị loại bởi `#n1ql.filter`.

### Bộ lọc tenant vẫn không phải toàn bộ authorization

Nếu hệ thống có nhiều mức quyền, ví dụ sản phẩm nháp chỉ quản trị viên được xem, còn cần thêm điều kiện theo role hoặc chính sách truy cập. Dùng mỗi `tenantId` cũng chưa đủ nếu caller không được phép xem mọi document trong tenant.

Các thao tác `findById` qua KV không tự thừa hưởng điều kiện `WHERE` trong `@Query`. Vì vậy, phải bảo vệ cả **đường truy cập theo ID** và **đường tìm kiếm theo thuộc tính**. `#n1ql.filter` không phải cơ chế cô lập dữ liệu an toàn để thay thế thiết kế quyền truy cập.

## 7. Khi document thiếu discriminator hoặc discriminator không khớp

Tài liệu Couchbase có thể được tạo từ nhiều nguồn: ứng dụng Spring Data, Couchbase SDK, Query Workbench, tiến trình nhập CSV/JSON hoặc một phiên bản phần mềm cũ. Những cách ghi khác nhau **không nhất thiết dùng cùng converter và type key**.

Trong bộ dữ liệu mẫu, document `legacy::KB-OLD` thiếu `_class`. Câu SQL++ thuần:

```sql
SELECT META(d).id AS id,
       d.sku,
       d.category,
       d._class AS storedType
FROM `catalog`.`commerce`.`documents` AS d
WHERE d.category = "keyboard";
```

có thể trả document legacy dù không có `storedType` trong JSON result vì biểu thức `d._class` là **MISSING**. Nhưng một truy vấn Spring Data có type filter có thể không chọn document này.

### Một bảng chẩn đoán theo trạng thái dữ liệu

| Document | Trường phân loại | Điều kiện `category = "keyboard"` | Repository `Product` có type filter |
| --- | --- | --- | --- |
| KB-100 | Alias `catalog-product` | TRUE | Phù hợp |
| KB-200 | Alias `catalog-product` | TRUE | Phù hợp |
| KB-300 | Alias `catalog-product` | TRUE | Phù hợp, nhưng vẫn cần tenant filter |
| BLACKFRIDAY | Alias `catalog-promotion` | TRUE | Bị loại theo kiểu |
| KB-OLD | `MISSING` | TRUE | Có thể bị loại vì thiếu type key |

Đây là kết quả **theo mô hình type mapping trong bài**, không phải lời cam kết cho mọi converter tùy biến. Khi thấy Repository và Workbench trả số lượng khác nhau, đừng vội xóa `#n1ql.filter`: hãy xác định nguyên nhân dữ liệu không đồng nhất.

### Các bước xác minh

1. Lưu **một** `Product` bằng chính `ProductRepository.save(...)` trong môi trường test.
2. Dùng Query Workbench đọc JSON body và kiểm tra trường phân loại thực tế của document vừa lưu.
3. Đối chiếu với các document được nhập bằng SDK, script hoặc phiên bản cũ.
4. Xác minh Repository chọn đúng bucket/scope/collection.
5. Chạy câu `@Query` có `#n1ql.filter` và một câu SQL++ thuần tương đương về điều kiện nghiệp vụ để so sánh.
6. Nếu thấy khác biệt, rà soát alias, cấu hình type key và cách converter quản lý class/hierarchy trước khi sửa dữ liệu.

### Chiến lược xử lý dữ liệu legacy

Khi dữ liệu cũ thiếu type discriminator, có ba hướng cần đánh giá:

- **Chuẩn hóa dữ liệu:** chuyển document sang định dạng mà Spring Data converter mong đợi thông qua quy trình migration có kiểm thử.
- **Tách collection:** đưa từng loại document vào collection riêng để giảm sự nhập nhằng về schema, nhưng vẫn giữ metadata mapping và điều kiện truy vấn phù hợp.
- **Đường truy cập legacy chuyên biệt:** dùng SDK/SQL++ được kiểm soát để đọc dữ liệu cũ và chuyển đổi, thay vì ép kết quả chưa có type key vào một Repository full entity có hợp đồng khác.

Đừng sửa hàng loạt `_class` sang một chuỗi cố định chỉ để làm query trả dữ liệu: có thể biến document của loại khác thành `Product` giả hoặc phá vỡ ứng dụng còn dùng discriminator cũ.

Nếu migration cần cập nhật từng document, cân nhắc **CAS**, log kiểm toán, idempotency và cách xử lý chạy song song. Trước khi thay đổi type key, sao lưu dữ liệu theo quy trình vận hành của hệ thống và thử trong môi trường cách ly.

## 8. `@TypeAlias`, đổi tên class và kế thừa entity

Khi không dùng alias, Spring Data thường lưu tên class Java trong trường phân loại; ví dụ một giá trị có thể giống `com.example.catalog.Product`. Nếu đổi package hoặc tên class sau khi triển khai, dữ liệu cũ có thể chứa tên không còn tương ứng với mapping mới.

`@TypeAlias("catalog-product")` cho phép biểu diễn một tên loại ổn định hơn, nhưng **không tự di chuyển dữ liệu cũ** từ tên class đầy đủ sang alias. Sau khi áp dụng alias, cần kiểm chứng converter nhận diện cả dữ liệu cũ và mới hoặc thực hiện migration tương thích.

### Đổi tên entity không phải đổi tên nghiệp vụ

Giả sử class `Product` sau này được đổi thành `CatalogItem`:

```java
@Document
@TypeAlias("catalog-product")
@Scope("commerce")
@Collection("documents")
public class CatalogItem {
    @Id
    private String id;
    private String category;

    public CatalogItem() {}
    // getters/setters...
}
```

Nếu hệ thống vẫn dùng alias cũ nhất quán và converter biết class mới, việc đổi tên Java **có thể ít gây biến động type key** hơn trường hợp lưu FQCN. Tuy nhiên, phải kiểm thử cả đọc document cũ và `#n1ql.filter` trong Repository mới; không nên coi `@TypeAlias` là bảo đảm di chuyển class tự động.

### Hệ phân cấp class và interface

Giả sử `DigitalProduct extends Product` hoặc Repository quản lý kiểu cha. Một số mapper có thể dùng type information để khôi phục subtype; trong khi điều kiện `#n1ql.filter` của Repository có thể được sinh theo metadata của entity đang quản lý.

Không suy diễn rằng `ProductRepository` luôn tìm **mọi subtype** chỉ vì Java có quan hệ kế thừa. Kiểm thử trực tiếp các tình huống:

- Document chỉ có type alias của `Product`.
- Document có type alias của `DigitalProduct`.
- Repository trả `Product` hay một kiểu con.
- Collection có document cùng field nhưng không thuộc hệ phân cấp.

Khi nghiệp vụ cần truy vấn tất cả các subtype, chọn chiến lược mapping hoặc truy vấn chuyên biệt phù hợp với **phiên bản Spring Data**, thay vì dựa vào một phép so sánh alias tự viết không phản ánh type hierarchy.

### Tùy biến type key

Một số dự án thay tên trường phân biệt loại hoặc sử dụng converter tùy biến. Nếu thay `_class` bằng một khóa khác, các câu SQL++ tự viết dạng `WHERE d._class = "..."` có thể lỗi ngữ nghĩa hoặc trả rỗng.

Ở tầng Repository, `#{#n1ql.filter}` có lợi vì liên kết với metadata mapping của Spring Data, giảm việc hardcode key và giá trị. Tuy nhiên, nếu bạn tự viết câu `SELECT/FROM`, phải bảo đảm keyspace và phần filter vẫn được phân giải đúng trong cấu hình tùy biến.

## 9. `#n1ql.selectEntity`, `#n1ql.fields` và shape của kết quả

Trong một `@Query` trả về entity, type filter chỉ quyết định **document nào** được chọn. Còn ánh xạ kết quả cần phép chiếu phù hợp. Mẫu đầy đủ:

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND category = $1")
List<Product> findProducts(String category);
```

`#{#n1ql.selectEntity}` sinh phần **`SELECT/FROM`** theo mapping; nó không chỉ là tên collection. Nó bao gồm các biểu thức cần cho việc dựng entity, trong đó có ID/CAS theo cơ chế Spring Data.

Nếu cần tự khai báo `SELECT/FROM` theo cú pháp được tài liệu của phiên bản hỗ trợ, có thể dùng `#{#n1ql.fields}` để sinh **danh sách trường**, chứ không phải cả câu truy vấn:

```java
@Query("SELECT #{#n1ql.fields} "
     + "FROM #{#n1ql.collection} "
     + "WHERE #{#n1ql.filter} AND category = $1")
List<Product> findProductsWithExplicitSelect(String category);
```

Đoạn này mang tính minh họa cho dạng cú pháp Spring Data được tài liệu hóa; khi cấu hình scope/collection hoặc query context, cần xác minh `#n1ql.collection` trỏ đúng keyspace. Với query entity thông thường, `#n1ql.selectEntity` là lựa chọn ngắn hơn, ít sai hơn.

### Những cách kết hợp cần tránh

| Cách khai báo | Vấn đề |
| --- | --- |
| `SELECT #{#n1ql.selectEntity} FROM ...` | Chồng từ khóa `SELECT/FROM` lên macro đã tạo chúng |
| `#{#n1ql.fields} WHERE ...` | Thiếu `SELECT` và `FROM` |
| `SELECT * FROM ... WHERE ...` trả `List<Product>` | Dạng row và metadata có thể không hợp đồng mapping full entity |
| `#{#n1ql.selectEntity} WHERE category = $1` không có type filter | Câu SQL++ có thể hợp lệ nhưng không giữ ràng buộc loại document |
| `#{#n1ql.selectEntity} WHERE #{#n1ql.filter} AND ...` | Mẫu nhất quán cho full entity với điều kiện nghiệp vụ |

`SELECT *` và `SELECT d.*` là các phép chiếu SQL++ hợp lệ trong những tình huống phù hợp, nhưng **không mặc định cung cấp alias ID/CAS và metadata mà Spring Data cần để khôi phục đầy đủ entity**.

### Khi câu query không trả full entity

Nếu chỉ cần báo cáo:

```sql
SELECT d.category AS category, COUNT(*) AS total
FROM `catalog`.`commerce`.`documents` AS d
WHERE d._class = "catalog-product"
GROUP BY d.category;
```

thì mỗi hàng là thống kê của một nhóm, **không phải một Product document** có ID/CAS riêng. Không dùng `#n1ql.selectEntity` để ép kết quả `GROUP BY COUNT(*)` thành `List<Product>`.

Có thể thiết kế DTO/projection:

```java
public record CategoryCount(String category, long total) {}
```

Ánh xạ kết quả qua cơ chế API đã kiểm chứng của phiên bản Spring Data hoặc Couchbase Java SDK. Khi tự viết SQL++ scalar/aggregate, quyết định có đưa discriminator vào điều kiện dựa trên **phạm vi báo cáo**: đếm riêng `Product` khác với đếm tất cả document trong collection.

## 10. Chỉ mục cho điều kiện discriminator và điều kiện nghiệp vụ

`#n1ql.filter` giúp truy vấn chọn đúng loại document, nhưng **không tự tạo secondary index**. Khi dùng SQL++ tìm sản phẩm theo loại, tenant, category và trạng thái, Query Service cần đường truy cập phù hợp với workload.

Ví dụ một chỉ mục minh họa với type key `_class`:

```sql
CREATE INDEX idx_documents_type_tenant_category_active
ON `catalog`.`commerce`.`documents`(
    _class,
    tenantId,
    category,
    active
);
```

Chỉ mục này chỉ có ý nghĩa khi dữ liệu thực sự dùng `_class` làm type key và truy vấn thường lọc các thuộc tính tương ứng. Với trường phân biệt kiểu tùy biến, biểu thức index phải thay đổi cho khớp. Thứ tự khóa còn phụ thuộc độ chọn lọc, cách lọc equality/range, thứ tự sắp xếp và các truy vấn khác, nên **không coi đây là chỉ mục tối ưu bắt buộc**.

Để hiểu kế hoạch, dùng `EXPLAIN`:

```sql
EXPLAIN
SELECT d.sku, d.category, d.price
FROM `catalog`.`commerce`.`documents` AS d
WHERE d._class = "catalog-product"
  AND d.tenantId = "shop-a"
  AND d.category = "keyboard"
  AND d.active = true;
```

Ví dụ `EXPLAIN` dùng discriminator đúng như bộ dữ liệu mô phỏng; để đánh giá Repository thật, cần đối chiếu **SQL++ cuối cùng** do Spring Data sinh, bao gồm biểu thức `#n1ql.filter` và phần `SELECT` entity. Query optimizer có thể chọn chỉ mục khác nếu thống kê dữ liệu, query context hoặc phép chiếu khác.

### Chỉ mục thông thường và document thiếu type key

Một secondary index có khóa đầu `_class` có thể không lập mục cho document **MISSING** trường khóa đầu. Đây không nhất thiết là lỗi nếu mục đích index là tăng tốc truy vấn Spring Data **chỉ lấy document có type hợp lệ**.

Nhưng khi cần tìm document legacy thiếu type key bằng:

```sql
SELECT META(d).id
FROM `catalog`.`commerce`.`documents` AS d
WHERE d._class IS MISSING;
```

thì index trên `_class` có thể **không hỗ trợ tốt** điều kiện đó. Truy vấn migration hoặc kiểm tra chất lượng dữ liệu có nhu cầu index khác với truy vấn Repository thường ngày. Đừng kết luận không có document legacy chỉ vì một kiểu index hoặc kế hoạch truy vấn không phù hợp.

### Khi nào cần tách collection?

Nếu `Product` và `Promotion` có nhu cầu index rất khác nhau, schema ít giao nhau hoặc vòng đời TTL khác nhau, chia chúng vào **hai collection riêng** có thể giúp thiết kế, phân quyền và vận hành rõ ràng hơn. Tuy nhiên, việc tách collection không tự thay `#n1ql.filter` trong một `@Query` hiện có; Repository vẫn cần đúng mapping và cú pháp.

Khi chọn chia collection, cân nhắc:

- Quy ước bucket/scope/collection cho từng domain.
- Chi phí tạo/duy trì index theo từng collection.
- Quyền truy cập và môi trường multi-tenant.
- TTL theo từng loại document.
- Đường dẫn dữ liệu và migration từ collection cũ.
- Giao dịch khi thao tác trên nhiều document hoặc collection.

## 11. Scan consistency: lọc kiểu đúng nhưng chưa thấy document mới

Khi lưu một `Product` mới bằng Repository, Key/Value API có thể xác nhận ghi trước khi chỉ mục SQL++ bắt kịp. Vì vậy, kết quả tìm kiếm qua `@Query` có thể khác đọc theo ID trong thời gian ngắn, **dù discriminator đã được ghi đúng**.

```java
Product saved = productRepository.save(newProduct);

// Khi có ID, cách đọc Key/Value trực tiếp thường phù hợp.
productRepository.findById(saved.getId());

// Truy vấn theo thuộc tính có thể phải dựa vào chỉ mục.
productRepository.findByCategoryWithTypeFilter("keyboard");
```

Đoạn này giả định entity có `getId()` và đã được chuẩn bị đầy đủ trước khi `save`.

| Scan consistency | Kỳ vọng | Đánh đổi |
| --- | --- | --- |
| `NOT_BOUNDED` | Không bắt buộc đợi index cập nhật các ghi mới nhất | Thường có độ trễ thấp, nhưng có thể chưa thấy document vừa ghi |
| `REQUEST_PLUS` | Query Service chờ index bắt kịp các thay đổi trước thời điểm truy vấn | Có thể tăng độ trễ |

Đối với luồng nghiệp vụ “vừa tạo rồi đọc lại **chính document ID đó**”, ưu tiên Key/Value. Đối với trang tìm kiếm hay dashboard, chọn scan consistency dựa trên yêu cầu độ mới và tải hệ thống.

**Quan trọng:** `#n1ql.filter` không kiểm soát scan consistency. Một truy vấn có type filter chính xác vẫn có thể tạm thời chưa thấy document; ngược lại, `REQUEST_PLUS` không biến một document có discriminator sai thành đúng loại entity.

### Kết hợp với CAS, TTL và giao dịch

- **CAS:** nhận diện phiên bản document để phát hiện cập nhật xung đột; không có nhiệm vụ phân biệt `Product` và `Promotion`.
- **TTL:** quyết định khi nào một document hết hạn; type filter không giữ cho document sống lâu hơn.
- **Transactions:** hỗ trợ nhóm thao tác cần tính nguyên tử và kiểm soát nhất quán; một `@Query` có type filter không tạo transaction tự động.
- **Query index:** quyết định việc tìm kiếm bằng thuộc tính nhanh đến đâu và mới đến mức nào; type discriminator chỉ là một điều kiện trong truy vấn.

Khi thay type key của một document đang hoạt động, cần xem xét tác động đến các repository khác, tính nhất quán khi ghi và các truy vấn đang chạy song song. Không dùng câu `UPDATE` hàng loạt thay đổi loại document nếu chưa có kế hoạch migration và kiểm thử.

## 12. Repository reactive và `CouchbaseTemplate`

### Với Repository reactive

Reactive repository cũng sử dụng SpEL `#n1ql` theo kiểu tương ứng:

```java
import reactor.core.publisher.Flux;
import org.springframework.data.couchbase.repository.Query;
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import org.springframework.data.repository.query.Param;

public interface ReactiveProductRepository
        extends ReactiveCouchbaseRepository<Product, String> {

    @Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
         + "AND category = $category AND active = true")
    Flux<Product> findActiveByCategory(
        @Param("category") String category
    );
}
```

`Flux<Product>` thể hiện cách tiêu thụ kết quả không chặn, nhưng **không đổi ngữ nghĩa SQL++ hay type discriminator**. Dù truy vấn đồng bộ hay reactive, nếu dữ liệu không có discriminator phù hợp, việc lọc kiểu vẫn là vấn đề cần giải quyết ở mapping/data migration.

### Với `CouchbaseTemplate`

`CouchbaseTemplate` thích hợp cho truy cập document theo entity và xây dựng điều kiện linh hoạt theo API Spring Data. Tuy nhiên, **không mặc định rằng mọi truy vấn Template tự chèn đúng cùng một type filter trong mọi kiểu thao tác**; các thao tác mapper-driven và truy vấn SQL++ thô có thể khác hành vi.

Khi tự viết SQL++ qua SDK `Cluster.query`, không có `#{#n1ql.filter}`: **SDK không có Spring Data SpEL context**. Muốn lọc theo type trong câu SQL++ thuần, cần tự viết điều kiện dựa trên quy tắc type key thực tế:

```sql
-- Điều kiện minh họa cho JSON alias trong bài.
SELECT d.sku, d.name
FROM `catalog`.`commerce`.`documents` AS d
WHERE d._class = "catalog-product"
  AND d.active = true;
```

Không lấy chuỗi `"_class"` và `"catalog-product"` từ ví dụ rồi sử dụng vô điều kiện trên mọi project: trước hết kiểm tra converter và alias mà ứng dụng thực sự ghi.

### Derived query có cần `#n1ql.filter` trong mã không?

Phương thức suy diễn từ tên như `findByCategory(String category)` được Spring Data tạo câu truy vấn theo metadata repository; không đặt `#{#n1ql.filter}` trực tiếp trong tên phương thức.

Khi chuyển một phương thức derived sang **`@Query` viết tay**, phải xem điều kiện kiểu entity nào cần giữ; mẫu `WHERE #{#n1ql.filter} AND ...` giúp biểu đạt rõ điều này. Hãy so sánh kết quả thực tế của hai dạng và kiểm tra SQL++ được sinh ở phiên bản Spring Data dùng trong dự án, thay vì giả định mọi trình tạo truy vấn có cùng đường xử lý nội bộ.

## 13. Lỗi thường gặp khi lọc kiểu entity

| Triệu chứng | Nguyên nhân có thể | Cách khắc phục |
| --- | --- | --- |
| Workbench tìm 5 document keyboard nhưng `ProductRepository` chỉ tìm 3 | Workbench chỉ lọc `category`, Repository còn lọc loại entity | So sánh discriminator và phân biệt kết quả đúng với yêu cầu |
| Workbench tìm thấy document legacy nhưng Repository không thấy | JSON thiếu type key hoặc có alias không tương thích | Kiểm tra converter, migration hoặc đường truy cập legacy riêng |
| `List<Product>` cố ánh xạ một `Promotion` | `@Query` viết tay thiếu type filter hoặc có điều kiện `OR` vượt qua filter | Thêm `#{#n1ql.filter}` đúng chỗ, đặt ngoặc cho các nhánh `OR` |
| Tất cả document bị loại sau khi thêm `filter` | Repository mapping và discriminator lưu trong JSON không khớp | Kiểm tra `@TypeAlias`, cấu hình converter và source dữ liệu |
| Đã đổi package Java, tài liệu cũ không còn được nhận | Discriminator lưu tên class cũ | Dùng chiến lược alias tương thích hoặc migration có kiểm thử |
| Repository Product trả document tenant khác | Type filter không phải điều kiện tenant | Thêm ràng buộc tenant tin cậy và kiểm tra quyền |
| `WHERE #{#n1ql.filter} WHERE category = ...` báo lỗi SQL++ | Viết hai mệnh đề `WHERE` | Chỉ viết một `WHERE`; nối điều kiện bằng `AND` |
| `SELECT #{#n1ql.selectEntity} FROM ...` báo lỗi | `selectEntity` đã bao gồm `SELECT/FROM` | Bắt đầu câu bằng macro rồi tới `WHERE` |
| Tự viết `SELECT *` khiến entity có metadata sai | Phép chiếu không theo hợp đồng entity mapping | Dùng `#{#n1ql.selectEntity}` cho full entity |
| Tạo index trên `category` nhưng query vẫn chậm | Điều kiện type/tenant/active và Fetch chưa được tính tới | Dùng `EXPLAIN` trên SQL++ cuối cùng, xem workload thật |
| `findById` đọc được document mới nhưng `@Query` chưa thấy | Index bất đồng bộ, scan consistency không chờ | Xem `NOT_BOUNDED`/`REQUEST_PLUS`; dùng KV cho ID đã biết |
| Thử `_class = "catalog-product"` luôn trả rỗng | Type key hoặc alias trong dự án không giống ví dụ | Đọc document được lưu qua Spring Data để xác định field thực |
| Truy vấn native SDK chứa `#{#n1ql.filter}` không chạy | SDK Query Service không phân giải Spring Data SpEL | Viết SQL++ thuần theo type mapping thực |
| Entity con không xuất hiện trong Repository entity cha | Cách tạo type filter/hierarchy không bao gồm subtype đó | Kiểm chứng quy tắc inheritance/alias của phiên bản đang dùng |
| Dữ liệu hiện đúng kiểu nhưng caller không có quyền | Type discriminator không kiểm soát authorization | Thực thi chính sách truy cập ở mọi đường đọc/ghi |

### Quy trình debug theo ba lớp

Đối với một query trả rỗng hoặc chọn nhầm document, hãy lần lượt xem:

1. **Lớp dữ liệu:** JSON body có discriminator không? Giá trị alias/type key thực tế là gì? Document được tạo bằng Repository hay import? Có đúng bucket/scope/collection không?
2. **Lớp truy vấn:** `#n1ql.selectEntity` sinh phép chiếu gì? `#n1ql.filter` có nằm trong `WHERE` không? Các nhánh `AND/OR` có giữ filter? Tham số `$category`, `$tenantId` được binding đúng không?
3. **Lớp vận hành:** index có phục vụ điều kiện thật không? `EXPLAIN` chọn kế hoạch gì? Scan consistency có phù hợp với ghi vừa xảy ra không? Người dùng có quyền truy cập document không?

Một test có thể nhìn thấy document nhờ dữ liệu cũ trong cùng collection dù mapping mới đã sai; vì vậy nên tạo **dữ liệu mới qua chính converter hiện tại** rồi so sánh với dữ liệu được nhập bên ngoài. Khi log SQL++ hoặc tham số, tránh ghi thông tin bí mật/tenant nhạy cảm ra log tùy tiện.

## 14. Bài thực hành có đáp án

Các bài sau dùng **năm document** trong phần 1. Kết quả Repository giả định dữ liệu có discriminator tương thích với `@TypeAlias` đã mô tả và đã được chỉ mục SQL++ phản ánh đầy đủ.

### Bài 1 — Đếm các tập document khác nhau

**Yêu cầu:** Dự đoán số document khớp với từng điều kiện.

| Điều kiện | Số document kỳ vọng | Document |
| --- | ---: | --- |
| `category = "keyboard"` (không lọc type) | 5 | KB-100, KB-200, KB-300, BLACKFRIDAY, KB-OLD |
| Type `catalog-product` và `category = "keyboard"` | 3 | KB-100, KB-200, KB-300 |
| Type `catalog-product`, `active = true`, category keyboard | 2 | KB-100, KB-300 |
| Type `catalog-product`, tenant `shop-a`, active, keyboard | 1 | KB-100 |

**Giải thích:** Type, active và tenant là **ba bộ lọc khác nhau**. Tính đúng đắn không nằm ở việc có nhiều hay ít hàng hơn, mà ở tập document đúng yêu cầu.

### Bài 2 — Viết Repository tìm sản phẩm đang hoạt động theo danh mục

**Yêu cầu:** Trả full entity `Product`, có binding danh mục và giữ bộ lọc loại entity.

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND category = $category "
     + "AND active = true")
List<Product> findEnabledInCategory(
    @Param("category") String category
);
```

**Đáp án khi gọi `findEnabledInCategory("keyboard")`:** KB-100 và KB-300. Điều kiện type bảo vệ trước `Promotion`; điều kiện `active` loại KB-200; không có tenant filter nên cả hai tenant vẫn có thể xuất hiện.

### Bài 3 — Sửa truy vấn có `OR` vượt qua filter

**Đầu bài:**

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND category = $1 OR active = true")
List<Product> unsafeGrouping(String category);
```

**Vấn đề:** nhánh `active = true` có thể không còn phụ thuộc vào bộ lọc entity. Một `Promotion` có `active = true` có thể lọt vào kết quả truy vấn.

**Đáp án:**

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND (category = $1 OR active = true)")
List<Product> safeGrouping(String category);
```

Phần type filter luôn đứng ngoài hai nhánh nghiệp vụ, bảo đảm những document được chọn vẫn phải thuộc entity `Product`. Tuy nhiên, nếu yêu cầu là “active và thuộc category”, hãy dùng `AND active = true AND category = $1` thay vì `OR`; việc đặt ngoặc không tự thay thế thiết kế nghiệp vụ.

### Bài 4 — Bảo vệ tenant trong Repository

**Yêu cầu:** Tenant `shop-a` được xác minh từ security context. Chỉ trả các sản phẩm đang hoạt động thuộc tenant đó và danh mục truyền vào.

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND tenantId = $tenantId "
     + "AND category = $category "
     + "AND active = true")
List<Product> findAuthorizedProducts(
    @Param("tenantId") String trustedTenantId,
    @Param("category") String category
);
```

**Đáp án:** Khi gọi với tenant đã được xác thực `shop-a` và category keyboard, chỉ có KB-100. Không nhận tùy ý `trustedTenantId` từ một tham số HTTP mà không kiểm tra quyền. Đồng thời phải bảo vệ đường `findById` theo ID.

### Bài 5 — Giải thích document legacy không xuất hiện

Một nhân viên nhập JSON `legacy::KB-OLD` bằng Workbench, không có `_class`. Câu SQL++ thuần theo `category` tìm thấy nó, nhưng một phương thức `@Query` có `#{#n1ql.filter}` không thấy.

**Đáp án:** Document legacy thiếu discriminator phù hợp với metadata type của `Product`. Đây không nhất thiết là lỗi tham số hay index. Cần xác minh bằng cách lưu một `Product` qua Spring Data rồi so sánh JSON; sau đó chọn migration được kiểm thử, hoặc đường đọc legacy riêng. Không nên bỏ type filter trên Repository chỉ để đón mọi JSON cùng trường `category`.

### Bài 6 — Tìm đúng index cho truy vấn thường dùng

**Yêu cầu:** Ứng dụng thường lọc `Product` theo tenant, category và active. Hãy đề xuất một index để **đánh giá** và câu `EXPLAIN`.

```sql
CREATE INDEX idx_documents_report_candidate
ON `catalog`.`commerce`.`documents`(
    _class, tenantId, category, active
);
```

```sql
EXPLAIN
SELECT d.sku, d.category
FROM `catalog`.`commerce`.`documents` AS d
WHERE d._class = "catalog-product"
  AND d.tenantId = "shop-a"
  AND d.category = "keyboard"
  AND d.active = true;
```

**Đáp án phân tích:** Đây là index ứng viên với type key của ví dụ. Việc có dùng đúng index, có covering không và hiệu năng thực tế ra sao phải được kiểm tra bằng `EXPLAIN` và dữ liệu production-like. Không kết luận chỉ từ bốn phép so sánh trong bộ dữ liệu năm document.

### Bài 7 — Đổi Java class nhưng giữ document cũ

`Product` được đổi tên thành `CatalogItem`; dữ liệu cũ lưu tên class Java đầy đủ trong `_class`. Có nên chỉ thêm `@TypeAlias("catalog-product")` trên class mới rồi coi như xong?

**Đáp án:** Không. Alias mới không tự sửa discriminator đã lưu. Cần lập kế hoạch tương thích/migration hoặc converter có thể nhận thông tin kiểu cũ, rồi kiểm thử cả truy vấn `#n1ql.filter`, đọc entity và thao tác ghi với `@Version`/CAS nếu có.

### Bài 8 — Kiểm thử tích hợp theo tập dữ liệu tối thiểu

Tạo một môi trường test có Couchbase Server/Capella, Spring Data và index phù hợp, sau đó:

1. Lưu hai `Product` và một `Promotion` bằng đúng Repository/converter.
2. Kiểm tra type key thực sự lưu trong JSON (không tự giả định giá trị `_class`).
3. Chạy SQL++ thuần lọc `category`, rồi chạy `ProductRepository` có `#n1ql.filter`; so sánh tập ID.
4. Thêm document legacy thiếu discriminator; quan sát khác biệt Workbench/Repository.
5. Thêm `active` và tenant filter, kiểm tra không trả document tenant khác.
6. Thử câu có `OR` trước và sau khi đặt ngoặc; kiểm tra điều kiện kiểu không thể bị bỏ qua.
7. Dùng `EXPLAIN` với type key/index thực tế và đo kết quả sau khi ghi mới theo scan consistency được chọn.
8. Kiểm tra reactive repository nếu ứng dụng dùng WebFlux; xác minh cùng quy tắc lọc kiểu.

Đây là **quy trình thực hành được đề xuất**, không phải các phép kiểm thử đã chạy trong tài liệu này. Khi so sánh tập kết quả, nên so sánh **document ID** thay vì dựa vào thứ tự hàng nếu không có `ORDER BY`.

## 15. Tự kiểm tra kiến thức

1. **`#n1ql.filter` dùng để lọc gì?** Loại document/entity theo metadata mapping của Spring Data.
2. **Nó có tự bảo đảm `active = true` không?** Không; cần điều kiện nghiệp vụ riêng.
3. **Discriminator `_class` có phải `META().id` không?** Không; một bên thường là trường JSON, một bên là metadata document.
4. **Có nên hardcode `_class = "catalog-product"` vào mọi `@Query`?** Không; nếu có macro `#n1ql.filter`, hãy dùng metadata mapping thay vì giả định alias.
5. **Tại sao cùng trường `category` không chứng minh hai document có cùng kiểu entity?** JSON là bán cấu trúc, nhiều loại document có thể dùng chung tên trường.
6. **Vì sao Workbench thấy document legacy nhưng Repository không thấy?** Có thể thiếu hoặc khác discriminator.
7. **`#n1ql.filter` có thay tenant filter không?** Không; quyền và tenant phải được kiểm soát riêng.
8. **Điều kiện `OR` có thể gây lỗi gì?** Một nhánh có thể vượt qua type/tenant filter nếu đặt ngoặc sai.
9. **`#n1ql.selectEntity` khác `#n1ql.filter` thế nào?** Biểu thức đầu tạo `SELECT/FROM` cho entity, biểu thức sau tạo điều kiện lọc kiểu.
10. **Index có được tạo tự động từ `#n1ql.filter` không?** Không; phải thiết kế và quản lý chỉ mục phù hợp.
11. **`@TypeAlias` có tự di chuyển document cũ không?** Không; cần kế hoạch tương thích hoặc migration.
12. **Repository reactive có bỏ qua type filter không?** Không; ngữ nghĩa của SpEL và SQL++ giữ nguyên.
13. **`REQUEST_PLUS` có sửa type key không phù hợp không?** Không; nó chỉ điều chỉnh độ mới của chỉ mục truy vấn.
14. **Có thể bỏ type filter trong báo cáo không?** Có thể nếu chủ đích là báo cáo toàn collection và kiểu trả về phù hợp; phải quyết định rõ phạm vi dữ liệu.

## Tài liệu tham khảo chính thức

- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): `@Query`, SpEL `#n1ql.selectEntity`, `#n1ql.filter`, tham số và Repository mapping.
- [Spring Data Couchbase — Entity Mapping](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): document entity, metadata, `@Id`, `@Version` và cách mapping dữ liệu.
- [Spring Data Couchbase — Collections](https://docs.spring.io/spring-data/couchbase/reference/couchbase/collections.html): ánh xạ bucket/scope/collection.
- [Spring Data Commons — Object Mapping](https://docs.spring.io/spring-data/commons/reference/object-mapping.html): metadata kiểu entity và `@TypeAlias` trong Spring Data.
- [Couchbase Server — SQL++ SELECT](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/selectintro.html): truy vấn theo JSON field và ý nghĩa mệnh đề `WHERE`.
- [Couchbase Server — Indexing](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/indexing.html): secondary index, thiết kế truy vấn và `EXPLAIN`.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/n1ql-queries-with-sdk.html): truy vấn qua SDK và tham số hóa giá trị.

**Ghi nhớ:** `#{#n1ql.filter}` là cơ chế Spring Data Couchbase hỗ trợ **lọc đúng loại entity** khi truy vấn SQL++ bằng `@Query`. Nó cần được đặt trong `WHERE` cùng với các điều kiện nghiệp vụ và không thể thay thế bộ lọc tenant, kiểm tra quyền hay chỉ mục. Khi dữ liệu được tạo từ nhiều nguồn, hãy xác minh type discriminator thực tế, alias và converter trước khi kết luận Repository sai. Kết hợp `#{#n1ql.selectEntity}` để ánh xạ full entity, parameter binding cho giá trị đầu vào và `EXPLAIN`/scan consistency để kiểm soát hiệu năng, độ mới dữ liệu.

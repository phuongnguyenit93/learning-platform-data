# #n1ql.bucket, #n1ql.scope và #n1ql.collection trong Spring Data Couchbase

> **Mục tiêu bài học:** Hiểu cách Spring Data Couchbase xác định **bucket, scope, collection** khi tạo truy vấn SQL++; phân biệt các biến SpEL `#{#n1ql.bucket}`, `#{#n1ql.scope}` và `#{#n1ql.collection}` với `#{#n1ql.selectEntity}`, `#{#n1ql.fields}` và tham số `$1/$name`; viết truy vấn `@Query` đúng keyspace và giải quyết tình huống dùng nhầm collection, query context hoặc tên định danh động.

Trong module **SPRING_DATA_COUCHBASE**, lập trình viên xây dựng tầng truy cập Couchbase bằng **document mapping**, Repository, `CouchbaseTemplate` và truy vấn **SQL++**. Cùng một hệ thống có thể chứa hàng triệu JSON document, được tổ chức theo **bucket → scope → collection**. Tổ chức dữ liệu đúng keyspace là bước đầu để các thao tác tìm kiếm, index, TTL, CAS, transaction và API reactive hoạt động trên đúng đối tượng.

SQL++ là tên hiện dùng của ngôn ngữ trước đây gọi là **N1QL**. Spring Data vẫn giữ tên `#n1ql` trong một số biểu thức **Spring Expression Language (SpEL)** để tương thích API. Vì vậy, `#{#n1ql.collection}` là biến SpEL của **Spring Data**, không phải cú pháp SQL++ thuần có thể gửi trực tiếp đến Couchbase Query Service.

Một câu SQL++ có thể **hợp lệ về cú pháp nhưng đọc nhầm collection**. Với ứng dụng đa scope, lỗi này nguy hiểm hơn chỉ trả danh sách rỗng: nó có thể đọc dữ liệu của domain khác hoặc, nếu sai cả điều kiện quyền truy cập, làm lộ dữ liệu không thuộc phạm vi được phép.

| Thành phần | Vai trò | Ví dụ trong bài |
| --- | --- | --- |
| Bucket | Container lưu trữ cấp cao của Couchbase | `catalog` |
| Scope | Nhóm logic các collection trong bucket | `commerce` |
| Collection | Nơi chứa JSON document và là đơn vị đặt index | `products` |
| Keyspace đầy đủ | Đường dẫn ba cấp trong SQL++ | `catalog.commerce.products` |
| `#{#n1ql.bucket}` | Biểu thức SpEL cho tên bucket theo mapping | Không thay thế một giá trị tìm kiếm |
| `#{#n1ql.scope}` | Biểu thức SpEL cho tên scope theo mapping | Không phải SQL++ `$scope` |
| `#{#n1ql.collection}` | Biểu thức SpEL cho tên collection theo mapping | Không phải SQL++ `$collection` |

## 1. Phân cấp bucket, scope, collection

Couchbase phân cấp dữ liệu theo mô hình:

```text
Cluster
└── bucket: catalog
    ├── scope: commerce
    │   ├── collection: products
    │   └── collection: promotions
    └── scope: inventory
        ├── collection: stock_events
        └── collection: reservations
```

Trong ví dụ này, `products` và `promotions` ở cùng scope `commerce` nhưng là **hai collection riêng**. Một câu truy vấn vào `catalog.commerce.products` không tự tìm document ở `catalog.commerce.promotions`.

### Đường dẫn keyspace trong SQL++

SQL++ thường biểu diễn keyspace đủ ba cấp bằng các định danh được quote bởi **backtick**:

```sql
SELECT p.sku, p.name
FROM `catalog`.`commerce`.`products` AS p
WHERE p.active = true;
```

Trong đó:

- `catalog` là bucket;
- `commerce` là scope;
- `products` là collection;
- `p` là **alias của nguồn dữ liệu** ở trong câu SQL++, không phải tên collection hay tên biến Java.

Các dấu backtick bao quanh **định danh**. Chúng khác dấu nháy của **giá trị chuỗi**, ví dụ `"keyboard"` hoặc `'keyboard'`. Tên bucket, scope và collection là một phần của cấu trúc câu truy vấn; không được coi chúng như tham số giá trị.

### Vì sao cần phân biệt cả ba cấp?

Hai scope có thể chứa collection cùng tên:

```text
catalog.commerce.products
catalog.archive.products
```

Chỉ biết “collection là `products`” chưa đủ để xác định nguồn chính xác nếu query context không được khai báo hoặc không đúng. Đồng thời, index trên `catalog.commerce.products` không phải index của `catalog.archive.products`.

## 2. Dữ liệu mẫu và entity ánh xạ đến collection

Giả sử ứng dụng bán hàng có ba product document trong `catalog.commerce.products`.

**Document ID `product::KB-101`**

```json
{
  "sku": "KB-101",
  "name": "Bàn phím cơ TKL",
  "category": "keyboard",
  "price": 1450000,
  "active": true,
  "stock": 12
}
```

**Document ID `product::KB-202`**

```json
{
  "sku": "KB-202",
  "name": "Bàn phím không dây",
  "category": "keyboard",
  "price": 1950000,
  "active": true,
  "stock": 4
}
```

**Document ID `product::MS-301`**

```json
{
  "sku": "MS-301",
  "name": "Chuột văn phòng",
  "category": "mouse",
  "price": 420000,
  "active": false,
  "stock": 0
}
```

Collection `catalog.commerce.promotions` chứa một document **khác loại**:

**Document ID `promotion::KBDISCOUNT`**

```json
{
  "code": "KBDISCOUNT",
  "name": "Giảm giá bàn phím",
  "category": "keyboard",
  "active": true,
  "discountPercent": 10
}
```

Trong `catalog.inventory.stock_events` có thể có một sự kiện tồn kho `sku = "KB-101"`, nhưng nó **không phải Product** và không thuộc collection `products`. Các JSON trên chỉ mô tả trường nghiệp vụ; khi được lưu qua Spring Data Couchbase, converter có thể ghi thêm trường type discriminator, ví dụ `_class`.

### Entity Product

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.repository.Scope;
import org.springframework.data.couchbase.repository.Collection;

@Document
@Scope("commerce")
@Collection("products")
public class Product {
    @Id
    private String id;

    @Version
    private long version;

    private String sku;
    private String name;
    private String category;
    private Long price;
    private Boolean active;
    private Integer stock;

    public Product() {}

    // Getter/setter hoặc constructor tùy convention dự án.
}
```

`@Document` đánh dấu entity Spring Data Couchbase. `@Scope("commerce")` và `@Collection("products")` xác định scope/collection của entity. Bucket `catalog` được chọn qua cấu hình Spring Data/SDK của ứng dụng, không phải được lấy từ tên class `Product`.

`@Id` ánh xạ document key như `product::KB-101`; key này không cần xuất hiện dưới field JSON `id`. `@Version` có thể ánh xạ CAS để hỗ trợ optimistic locking. Vì vậy, khi trả về full entity bằng SQL++, Spring Data cần phép chiếu có metadata phù hợp, không chỉ `sku` và `price`.

### Repository tương ứng

```java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface ProductRepository
        extends CouchbaseRepository<Product, String> {
}
```

Khi dùng `repository.findById("product::KB-101")`, Spring Data có thể đọc bằng đường **Key/Value** trực tiếp theo ID và mapping. Khi tìm bằng category hoặc price, một `@Query` dùng SQL++ sẽ phụ thuộc keyspace và chỉ mục của Query Service.

## 3. Ba biến SpEL `#n1ql.bucket`, `#n1ql.scope`, `#n1ql.collection`

Spring Data Couchbase cung cấp các biểu thức SpEL dựa trên metadata entity:

| Biểu thức | Đại diện | Điều không nên giả định |
| --- | --- | --- |
| `#{#n1ql.bucket}` | Tên bucket đã được Spring Data xác định | Không tự mang nghĩa “toàn bộ đường dẫn ba cấp” |
| `#{#n1ql.scope}` | Tên scope tương ứng entity | Không chỉ ra collection nếu dùng riêng |
| `#{#n1ql.collection}` | Tên collection tương ứng entity | Không thay thế được bucket/scope ngoài query context |

Các biểu thức được Spring Data xử lý **trước khi SQL++ chạy**. Trong các phiên bản hỗ trợ chúng, giá trị được dùng làm **định danh query** đã được Spring Data chuẩn bị theo metadata; chúng không giống các chuỗi Java tùy ý được nối vào câu lệnh.

Ví dụ, đối với `Product` ở trên, ý nghĩa của ba biến tương ứng:

```text
#n1ql.bucket      -> catalog
#n1ql.scope       -> commerce
#n1ql.collection  -> products
```

Đây là sơ đồ **giá trị tên logic**, không phải lời cam kết về văn bản SQL++ cuối cùng. Thư viện có thể quote định danh và áp dụng **query context** phù hợp với phiên bản/cấu hình. Trước khi tự lắp đường dẫn từ các biến, hãy xác minh cú pháp trong phiên bản Spring Data Couchbase thực tế.

### Điểm dễ nhầm: `#n1ql.collection` không tự là một URI đầy đủ

Không có quy tắc chung rằng chỉ cần thay:

```sql
FROM products
```

vào mọi môi trường sẽ luôn tìm đúng `catalog.commerce.products`. Tên collection không chứa bucket/scope và có thể được hiểu theo **query context** hiện tại. Nếu query context chưa được đặt, đặt sai scope, hoặc trong cùng bucket có nhiều scope với collection `products`, kết quả có thể khác kỳ vọng hoặc câu query không chạy.

Trong một `@Query` trả full entity, cách ít rủi ro nhất thường là dùng `#{#n1ql.selectEntity}` để Spring Data tự tạo phần `SELECT/FROM` theo metadata thực tế.

## 4. Dùng `#{#n1ql.selectEntity}` khi truy vấn trả full entity

Trong `ProductRepository`, phương thức sau tìm các sản phẩm đang hoạt động của một danh mục:

```java
import java.util.List;
import org.springframework.data.couchbase.repository.Query;
import org.springframework.data.repository.query.Param;

@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND category = $category AND active = true")
List<Product> findActiveInCategory(
    @Param("category") String category
);
```

Đây là **khai báo phương thức bên trong interface `ProductRepository`**. Cú pháp `#{#n1ql.selectEntity}` được Spring Data xử lý thành phần `SELECT/FROM` tương thích với entity và collection của Repository.

Gọi:

```java
List<Product> keyboards =
    productRepository.findActiveInCategory("keyboard");
```

Với ba document mẫu và mapping Spring Data phù hợp, kết quả gồm KB-101 và KB-202. MS-301 có `active = false` và `category = "mouse"` nên bị loại. Document khuyến mại `KBDISCOUNT` nằm ở **collection khác**, không phải nguồn của câu truy vấn này.

### Vì sao không cần tự ghép ba biến?

`#n1ql.selectEntity` không chỉ biết tên keyspace; nó còn tạo phép chiếu phù hợp với ánh xạ document:

- JSON body của entity;
- document ID cần cho `@Id`;
- CAS nếu mapper sử dụng `@Version`;
- tên/alias phép chiếu mà Spring Data kỳ vọng.

Để trả về full entity, việc tự chọn `SELECT p.sku, p.price` rồi cố ánh xạ thành `Product` là không đủ. `#n1ql.selectEntity` giảm nguy cơ sai cả **FROM** lẫn **metadata**.

### `#{#n1ql.filter}` có vai trò gì?

`#n1ql.filter` tạo điều kiện lọc kiểu entity/discriminator theo mapping của Spring Data. Nếu một collection chứa nhiều Java entity, filter này giúp tránh đọc nhầm document chỉ vì các field JSON trùng tên.

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND price <= $maxPrice")
List<Product> findBelowPrice(
    @Param("maxPrice") long maxPrice
);
```

**Không nhầm `filter` với bucket/scope/collection**: keyspace chỉ ra **tập document nguồn**, còn discriminator xác định **kiểu entity trong nguồn ấy**. Filter cũng không thay điều kiện tenant hoặc kiểm tra phân quyền.

### Chỉ viết một `WHERE`

```java
// Đúng: FROM được tạo bởi selectEntity, một WHERE, nhiều điều kiện.
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND category = $1")
List<Product> good(String category);

// Sai cấu trúc: selectEntity đã sinh SELECT/FROM.
@Query("SELECT #{#n1ql.selectEntity} "
     + "FROM #{#n1ql.collection} WHERE category = $1")
List<Product> bad(String category);
```

Không đặt `SELECT`/`FROM` thêm một lần nữa trước hoặc sau `selectEntity`. Lỗi khác là viết `WHERE #{#n1ql.filter} WHERE category ...`, khiến SQL++ có hai mệnh đề `WHERE`.

## 5. Khi nào dùng `#{#n1ql.fields}` và `#{#n1ql.collection}`?

Nếu cần tự viết phần `SELECT/FROM` của một truy vấn trả full entity, Spring Data có biến `#n1ql.fields` tạo **danh sách phép chiếu** phục vụ mapping. Khác với `selectEntity`, nó **không tạo từ khóa `SELECT` hoặc mệnh đề `FROM`**.

Ví dụ dạng query được tài liệu Spring Data Couchbase mô tả:

```java
@Query("SELECT #{#n1ql.fields} "
     + "FROM #{#n1ql.collection} "
     + "WHERE #{#n1ql.filter} AND category = $1")
List<Product> findByCategoryWithExplicitSelect(String category);
```

Điều kiện quan trọng là tên collection rút gọn trong `FROM` được giải nghĩa đúng theo **query context** của ứng dụng. Khi cần truy vấn đủ ba cấp, phải xây đường dẫn hợp lệ với bucket/scope/collection của version đang chạy.

### So sánh các biểu thức theo phạm vi

| Biểu thức | Bao gồm | Người viết phải thêm |
| --- | --- | --- |
| `#{#n1ql.selectEntity}` | `SELECT/FROM` và phép chiếu cần thiết | `WHERE`, `ORDER BY`, điều kiện nghiệp vụ khi cần |
| `#{#n1ql.fields}` | Các biểu thức trong danh sách `SELECT` | `SELECT`, `FROM`, `WHERE` khi cần |
| `#{#n1ql.collection}` | Tên collection từ mapping | Các cấp keyspace ngoài phạm vi query context nếu cần |
| `#{#n1ql.bucket}` | Tên bucket từ mapping | Scope/collection nếu cần đến collection con |
| `#{#n1ql.scope}` | Tên scope từ mapping | Bucket/collection nếu cần keyspace đầy đủ |

Ví dụ khái niệm về đường dẫn đầy đủ:

```text
bucket        scope        collection
   │           │               │
catalog  .  commerce  .       products
   └───────────┴───────────────┘
             keyspace
```

Tùy cách Spring Data cung cấp các biến keyspace ở version cụ thể, một query có thể dùng các biểu thức SpEL để lắp đường dẫn:

```java
// Mẫu cần kiểm chứng trên phiên bản đang dùng và query context thực tế.
@Query("SELECT #{#n1ql.fields} "
     + "FROM #{#n1ql.bucket}.#{#n1ql.scope}.#{#n1ql.collection} "
     + "WHERE #{#n1ql.filter} AND active = true")
List<Product> findActiveWithExplicitKeyspace();
```

**Chú ý:** đây là mẫu minh họa cách tham chiếu từng cấp keyspace. Hành vi escape tên, alias của `fields` và cách xử lý `FROM` có thể khác giữa version Spring Data/SDK. Không sao chép mẫu vào production mà chưa chạy test tích hợp đối chiếu câu SQL++ cuối cùng. Nếu không có lý do phải tự viết `FROM`, dùng `#{#n1ql.selectEntity}` là lựa chọn đáng ưu tiên.

### Phân biệt tên keyspace và alias trong query

```sql
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE p.category = "keyboard";
```

`p` chỉ là alias cục bộ của SQL++. `#n1ql.collection` không phải tên alias `p`; nó đại diện cho tên collection của entity. Nếu phép chiếu Spring Data sinh ra tham chiếu một alias nhất định, không tùy ý thay alias ở `FROM` mà không xét tác động đến ánh xạ.

## 6. Query context và collection được viết không đủ cấp

Một SQL++ query có thể dùng keyspace đầy đủ hoặc được thực thi với **query context** xác định bucket/scope mặc định. Đây là hai cách diễn đạt nguồn dữ liệu khác nhau:

```sql
-- Không phụ thuộc vào query context cho việc xác định keyspace.
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE p.active = true;
```

```sql
-- Chỉ đúng khi query context tương ứng đã được thiết lập.
SELECT p.sku
FROM `products` AS p
WHERE p.active = true;
```

Ở câu thứ hai, `products` là tên collection rút gọn. Query Service phải biết **bucket/scope hiện tại** để xác định đó là `catalog.commerce.products`. Nếu query context là `catalog.archive`, cùng tên `products` sẽ chỉ tới nguồn khác hoặc có thể trả lỗi nếu collection không tồn tại.

### Query context đến từ đâu?

Tùy môi trường, query context có thể được chỉ định trong Query Workbench, câu lệnh hoặc tùy chọn của Couchbase SDK, hoặc được Spring Data thiết lập theo cấu hình mapping. Không suy luận rằng “ứng dụng đã kết nối bucket `catalog`” cũng có nghĩa mọi query đang mặc định dùng scope `commerce`.

Khi gỡ lỗi, cần xác minh cả bốn yếu tố:

1. Bucket mà ứng dụng kết nối/chọn để thao tác.
2. Scope được map vào entity hoặc được đặt trong query context.
3. Collection được map vào entity hoặc được viết sau `FROM`.
4. Quyền và index của **đúng** collection mà Query Service truy vấn.

### Không dùng `#n1ql.collection` để đoán query context

Biết Spring Data trả tên collection `products` **không chứng minh** câu query rút gọn có thể chạy trong một SDK call tự viết mà không có query context. Một câu `Cluster.query(...)` trực tiếp qua SDK không tự xử lý SpEL `#{#n1ql.collection}` và có thể không dùng ngữ cảnh của Spring Data Repository.

Đối với công cụ ngoài Spring Data, dùng **đường dẫn keyspace đủ cấp** hoặc thiết lập query context tường minh theo API của công cụ ấy.

## 7. `@Scope`, `@Collection` và sự thay đổi keyspace

Spring Data Couchbase có thể đọc mapping keyspace từ entity. Để minh họa, một entity `Promotion` được lưu tại `catalog.commerce.promotions`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.repository.Scope;
import org.springframework.data.couchbase.repository.Collection;

@Document
@Scope("commerce")
@Collection("promotions")
public class Promotion {
    @Id
    private String id;
    private String code;
    private String name;
    private String category;

    public Promotion() {}

    // Getter/setter hoặc constructor theo convention dự án.
}
```

Repository này có **metadata entity khác** với `ProductRepository`:

```java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;
import org.springframework.data.couchbase.repository.Query;

public interface PromotionRepository
        extends CouchbaseRepository<Promotion, String> {

    @Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
         + "AND category = $1")
    List<Promotion> findByCategory(String category);
}
```

Mặc dù chuỗi `@Query` có hình thức giống `ProductRepository`, `selectEntity` và các biến keyspace dùng metadata của **Promotion**, vì vậy Repository nhắm tới `promotions` thay vì `products`. Với dữ liệu mẫu, `promotionRepository.findByCategory("keyboard")` chọn `KBDISCOUNT`, không chọn KB-101 hay KB-202.

### Đổi annotation không di chuyển document

Giả sử thay:

```java
@Scope("commerce")
@Collection("products")
```

thành:

```java
@Scope("archive")
@Collection("products")
```

Việc sửa source code **không tự chuyển các document đang lưu** từ `catalog.commerce.products` sang `catalog.archive.products`. Phương thức Repository mới có thể bắt đầu truy vấn collection khác, trả rỗng hoặc trả dữ liệu không giống trước. Để đổi keyspace production, cần quy trình migration dữ liệu, index, quyền, TTL và kiểm thử đọc/ghi theo kế hoạch riêng.

### Về `_default` scope và collection

Couchbase có scope/collection mặc định mang tên `_default`. Một số ứng dụng cũ dùng trực tiếp bucket như keyspace, trong khi ứng dụng mới dùng scope/collection tùy biến:

```text
catalog._default._default
catalog.commerce.products
```

Hai địa chỉ này **không cùng là collection products**. Nếu entity không khai báo `@Scope`/`@Collection`, hành vi mặc định phải được xác định theo cấu hình và phiên bản Spring Data đang dùng; không tự suy luận sẽ dùng `commerce.products` chỉ vì bucket được đặt là `catalog`.

Khi chuyển một ứng dụng từ truy vấn ở default collection sang `commerce.products`, cần cập nhật đồng bộ mapping, phương thức Repository, các câu SQL++ viết tay, index, quyền và bước migration. Biến SpEL giúp giảm hardcode, nhưng không thay thế công việc chuyển dữ liệu.

## 8. Khác biệt giữa SpEL keyspace và tham số SQL++

Ba biến `#n1ql.bucket`, `#n1ql.scope`, `#n1ql.collection` là **biểu thức Spring** phục vụ dựng truy vấn. Trái lại, `$1` hay `$category` là **placeholder giá trị SQL++**. Chúng không hoán đổi cho nhau.

### Đúng: ràng buộc một giá trị nghiệp vụ

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND category = $category AND price <= $maxPrice")
List<Product> findInBudget(
    @Param("category") String category,
    @Param("maxPrice") long maxPrice
);
```

Nếu caller gọi `findInBudget("keyboard", 1600000L)`, kết quả trên dữ liệu mẫu là KB-101. `$category` là giá trị `"keyboard"`; `$maxPrice` là số `1600000`. Câu query vẫn nhắm tới **collection của entity**, không phải một collection mang tên `keyboard`.

### Sai: dùng tham số giá trị thay tên collection

```sql
-- Không phải cách chọn collection động.
SELECT p.sku
FROM $collection AS p
WHERE p.category = $category;
```

`$collection` không phải macro biến thành định danh `catalog.commerce.products`. Nó là một placeholder giá trị và không thay cấu trúc `FROM` theo cách mong muốn.

Đây cũng là lý do không nên tạo query bằng cách ghép trực tiếp tên collection do người dùng nhập:

```java
// KHÔNG AN TOÀN: tên collection không được kiểm soát.
String sql = "SELECT p.sku FROM " + requestCollection
           + " AS p WHERE p.category = $category";
```

Điều kiện `p.category = $category` có được binding an toàn cũng không sửa được rủi ro từ phần `FROM` đã bị ghép bằng chuỗi không tin cậy.

### Tên keyspace động cần một tập lựa chọn tin cậy

Trong một số hệ thống, cùng một ứng dụng có nhiều collection cần đọc theo mục đích nghiệp vụ. Nếu buộc phải chọn collection động, hãy giới hạn lựa chọn bằng enum hoặc bảng ánh xạ do ứng dụng sở hữu:

```java
public enum CatalogView {
    ACTIVE_PRODUCTS,
    PROMOTIONS
}

public final class AllowedKeyspaces {
    private AllowedKeyspaces() {}

    public static String fullKeyspace(CatalogView view) {
        return switch (view) {
            case ACTIVE_PRODUCTS -> "`catalog`.`commerce`.`products`";
            case PROMOTIONS -> "`catalog`.`commerce`.`promotions`";
        };
    }
}
```

Đây là ví dụ Java 17+ dùng switch expression. Hai chuỗi keyspace được **hardcode như hằng đã kiểm soát bởi ứng dụng**, không phải tạo từ request tùy ý. Còn các giá trị nghiệp vụ, như `category` và `maxPrice`, vẫn phải truyền bằng parameter binding.

Khi ứng dụng có Repository dành riêng cho từng loại entity, thường **không cần** dựng keyspace động: `ProductRepository` và `PromotionRepository` với metadata mapping riêng đơn giản và dễ kiểm tra hơn.

### Tại sao không đưa tham số người dùng vào `#{...}`?

SpEL có thể chèn **nội dung vào chuỗi truy vấn** trước khi SQL++ thực thi. Nó không phải cơ chế binding giá trị an toàn nếu dùng để nội suy tên bucket/collection đến từ request. Các biến `#n1ql...` về keyspace có giá trị vì được lấy từ **metadata mapping mà ứng dụng kiểm soát**, không phải một chuỗi có thể đổi tùy ý bởi người dùng.

**Ranh giới bảo mật:** whitelist cho định danh/cú pháp; binding `$name`/`$1` cho giá trị. Khi scope/collection gắn với tenant, cần kiểm tra cả authorization của tenant và quyền đọc keyspace tại Couchbase; whitelist đơn thuần không phải toàn bộ hệ thống phân quyền.

## 9. Trường hợp truy vấn nhiều collection

Một báo cáo có thể cần sản phẩm từ `commerce.products` và sự kiện tồn kho từ `inventory.stock_events`. Trong SQL++ thuần, hai keyspace được chỉ định riêng:

```sql
SELECT p.sku,
       p.name,
       e.delta AS stockChange
FROM `catalog`.`commerce`.`products` AS p
JOIN `catalog`.`inventory`.`stock_events` AS e
  ON e.sku = p.sku
WHERE p.active = true;
```

Ví dụ này giả định collection `stock_events` có trường `sku` và `delta`. Nếu một SKU có nhiều sự kiện tồn kho, câu JOIN có thể trả **nhiều hàng cho cùng một sản phẩm**; không được giả định một hàng JOIN tương đương một entity `Product`.

### Giới hạn quan trọng của `#n1ql.collection`

Biểu thức `#n1ql.collection` trong `ProductRepository` đại diện collection được mapping cho **Product**, không tự tạo tên collection thứ hai `stock_events`. Truy vấn đa collection phải định nghĩa nguồn dữ liệu bổ sung theo cách SQL++ hỗ trợ và bảo đảm quyền/index cho **cả hai collection**.

Nếu kết quả là một báo cáo `sku + stockChange`, nên ánh xạ vào **DTO/projection báo cáo** được hỗ trợ, hoặc thực thi query qua SDK và dựng DTO. Đừng cố gắn `#{#n1ql.selectEntity}` vào một phép JOIN nhiều hàng rồi mặc định mọi hàng trả về là một `Product` duy nhất với CAS/ID chính xác.

### Index cho truy vấn nhiều collection

Couchbase quản lý secondary index theo keyspace. Index trên `commerce.products` không hỗ trợ toàn bộ điều kiện JOIN ở `inventory.stock_events` nếu phía events cần quét theo `sku`. Cần xem `EXPLAIN` trên query thực tế và tối ưu theo điều kiện lọc/join, kích thước dữ liệu và số lượng hàng kết quả.

### Có nên dùng query chéo scope cho mọi nghiệp vụ?

Không. Với yêu cầu đọc một product theo ID, đường KV là phù hợp hơn. Với dashboard tồn kho tổng hợp, SQL++ JOIN có thể đúng bài toán nhưng cần đánh giá số event, độ trễ index và độ mới dữ liệu. Với nhiều thao tác cập nhật cần tính nguyên tử, xem xét cơ chế transaction và mô hình dữ liệu trước khi quyết định cách đọc/ghi.

## 10. Chỉ mục gắn với keyspace: cùng tên collection không dùng chung index

Một query SQL++ thường cần **secondary index** trên collection mà nó truy cập. Với truy vấn sản phẩm đang hoạt động theo category và mức giá:

```sql
SELECT p.sku, p.price
FROM `catalog`.`commerce`.`products` AS p
WHERE p.category = "keyboard"
  AND p.active = true
  AND p.price <= 1600000;
```

Có thể cân nhắc index:

```sql
CREATE INDEX idx_products_category_active_price
ON `catalog`.`commerce`.`products`(
    category, active, price
);
```

Đây là **index ứng viên** để đánh giá trên dữ liệu thực, không phải cấu hình mặc định tối ưu cho mọi workload. Thứ tự trường và nhu cầu index phụ thuộc độ chọn lọc, range predicate, sắp xếp và phép chiếu thực tế.

Nếu cũng có `catalog.archive.products`, chỉ mục trên `catalog.commerce.products` **không tự là chỉ mục của `catalog.archive.products`**. Vì vậy, query nhắm sai scope có thể trả rỗng, lỗi “không có index phù hợp” hoặc số liệu khác dự kiến.

### Kiểm tra bằng `EXPLAIN`

```sql
EXPLAIN
SELECT p.sku, p.name, p.price
FROM `catalog`.`commerce`.`products` AS p
WHERE p.category = "keyboard"
  AND p.active = true
  AND p.price <= 1600000;
```

Trong kế hoạch, hãy xem Query Service chọn index nào, số lượng bản ghi ước lượng, có cần Fetch body và có phải sắp xếp thêm không.

Khi chạy `@Query` từ Repository, SQL++ cuối cùng có thể:

- thêm điều kiện type discriminator nhờ `#{#n1ql.filter}`;
- chiếu toàn entity cùng ID/CAS qua `#{#n1ql.selectEntity}`;
- có mệnh đề `ORDER BY`/`LIMIT` và tham số do người gọi cung cấp;
- resolve keyspace thông qua cấu hình scope/collection của Spring Data.

Vì vậy, một phép `EXPLAIN SELECT p.sku` thuần **không luôn đại diện chính xác** cho chi phí ánh xạ full entity của Repository. Cần đối chiếu query thực tế hoặc một câu SQL++ tương đương đầy đủ.

### Đừng dùng primary index như giải pháp thay thế thiết kế

Primary index có thể giúp thử query đơn giản trong môi trường phát triển nhưng không phải câu trả lời mặc định cho mọi truy vấn production. Nếu chỉ dùng primary index để “chạy được”, ứng dụng có thể phải quét quá nhiều document. Thiết kế secondary index theo collection và workload rõ ràng thường giúp kiểm soát chi phí tốt hơn.

### Query context và lỗi index dễ bị đánh đồng

Nếu log ghi “index not found” hoặc query rất chậm, đừng vội tạo thêm index trên bucket dự đoán. Trước tiên xác định:

1. SQL++ thực sự truy vấn `catalog.commerce.products` hay keyspace khác?
2. Query context trong Workbench/SDK có giống môi trường Spring Data không?
3. Index đã được tạo **trên đúng collection** và ở trạng thái sẵn sàng?
4. Điều kiện lọc có khớp key của index, kể cả type discriminator hoặc trường dùng trong `ANY`?
5. User/service account có quyền Query và quyền truy cập index/keyspace thích hợp?

## 11. Scan consistency, TTL, CAS và transaction khi thay đổi collection

Việc truy vấn đúng collection là điều kiện cần nhưng **chưa bảo đảm kết quả chứa ghi mới nhất**. Couchbase cập nhật index của Query Service bất đồng bộ so với một số thao tác Key/Value.

Ví dụ sau khi lưu `Product`:

```java
Product saved = productRepository.save(product);

// Đọc theo ID bằng API Repository thường đi qua Key/Value.
Product reread = productRepository.findById(saved.getId())
    .orElseThrow();

// Tìm theo category qua SQL++ có thể phụ thuộc độ mới của index.
List<Product> matches =
    productRepository.findActiveInCategory("keyboard");
```

Các đoạn mã giả định entity có getter `getId()` và service đã chuẩn bị `product` hợp lệ. Dưới scan consistency `NOT_BOUNDED`, truy vấn theo category có thể chưa thấy document vừa ghi. `REQUEST_PLUS` yêu cầu Query Service đợi index cập nhật các thay đổi trước thời điểm truy vấn, nhưng có thể tăng độ trễ.

| Mối quan tâm | Cơ chế | Có được giải quyết bởi `#n1ql.collection` không? |
| --- | --- | --- |
| Chọn đúng nơi lưu | Mapping bucket/scope/collection | **Có liên quan trực tiếp** |
| Thấy ghi mới trong tìm kiếm | Query scan consistency | **Không** |
| Phát hiện ghi đè do concurrent update | CAS/`@Version` | **Không** |
| Quy định thời điểm document hết hạn | TTL/expiry | **Không** |
| Nhiều cập nhật cần nguyên tử | Couchbase transaction | **Không** |
| Giảm chi phí tìm theo thuộc tính | Secondary index | **Không tự tạo index** |

### TTL theo vòng đời document

Một document hết hạn TTL sẽ không tồn tại vĩnh viễn chỉ vì entity vẫn được map đến collection ấy. Nếu các sản phẩm tồn tại dài hạn còn sự kiện tồn kho chỉ giữ 30 ngày, việc tổ chức chúng ở collection khác nhau có thể hỗ trợ chính sách vận hành riêng. Tuy nhiên, cần thiết lập expiry và chính sách lưu thực tế; việc tách collection **không tự động cấu hình TTL**.

### CAS khi lưu entity

`@Version` ở entity `Product` có thể dùng CAS để phát hiện xung đột khi hai tác nhân cùng sửa một document. Đổi `@Scope`/`@Collection` khiến thao tác nhắm tới **keyspace khác**; CAS của một document ở collection cũ không tự quản lý một document “cùng ID” trong collection mới.

Do đó, migration giữa collection cần kế hoạch xử lý các cập nhật diễn ra đồng thời, không chỉ sửa annotation rồi lưu lại entity theo dữ liệu cũ.

### Transactions có tạo keyspace tự động không?

Không. Transaction có thể liên quan nhiều document/collection trong phạm vi mà Couchbase hỗ trợ, nhưng **không tự tạo bucket/scope/collection**, không thay đổi một đường dẫn `FROM` sai và không tự di chuyển dữ liệu sau khi sửa mapping. Cần thiết kế thứ tự thao tác, xử lý retry và kiểm thử các điều kiện lỗi thực tế.

## 12. Reactive Repository và `CouchbaseTemplate` vẫn dùng cùng metadata

Repository reactive sử dụng cùng kiểu entity với scope/collection mapping:

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

`Flux<Product>` làm thay đổi mô hình nhận kết quả nhưng **không làm tên collection hay query context đổi nghĩa**. Cùng metadata `Product` vẫn cần ánh xạ về `commerce.products`, cùng điều kiện type discriminator và index tương ứng.

### Với `CouchbaseTemplate`

`CouchbaseTemplate` cho phép thực hiện thao tác dựa trên mapping entity và xây điều kiện linh hoạt. Khi dùng API mapping-driven, cần xác minh nó chọn đúng collection của entity. Khi dùng SQL++ thô, người viết vẫn chịu trách nhiệm keyspace, tham số và hình dạng phép chiếu theo cách API hỗ trợ.

Không giả định rằng mọi phương thức Template đều chèn cùng một `#n1ql.filter` hoặc tự hiểu macro SpEL như Repository `@Query`. Những chuỗi SQL++ truyền thẳng tới Query Service không có sẵn trình phân giải SpEL của `@Query`.

### Với Couchbase Java SDK

Một ví dụ SDK tìm theo category không cần SpEL:

```java
import java.util.List;
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryResult;
import static com.couchbase.client.java.query.QueryOptions.queryOptions;

public class ProductSearchService {
    private final Cluster cluster;

    public ProductSearchService(Cluster cluster) {
        this.cluster = cluster;
    }

    public List<JsonObject> findSkus(String category) {
        String sql = """
            SELECT p.sku, p.name
            FROM `catalog`.`commerce`.`products` AS p
            WHERE p.category = $category AND p.active = true
            ORDER BY p.sku
            """;
        QueryResult result = cluster.query(
            sql,
            queryOptions().parameters(
                JsonObject.create().put("category", category)
            )
        );
        return result.rowsAsObject();
    }
}
```

Ví dụ trên dùng Java 17+ vì có text block; `Cluster` phải được cấu hình và tái sử dụng theo vòng đời ứng dụng. Chuỗi SQL++ **khai báo đầy đủ bucket/scope/collection**, còn `$category` là placeholder giá trị. SDK không tự thay thế `#{#n1ql.collection}` vì nó không phải Spring Data Repository.

Nếu cần ánh xạ thành `Product` đầy đủ thay vì `JsonObject` chiếu hai trường, sử dụng cơ chế mapping/entity phù hợp hoặc tự đọc đủ metadata với một chiến lược có kiểm chứng; không mặc định DTO gồm `sku` và `name` là một full entity có ID/CAS.

## 13. Bảng lỗi thường gặp khi chọn bucket, scope và collection

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Workbench trả đúng dữ liệu nhưng Repository trả rỗng | Query context, mapping collection hoặc discriminator khác | Xác nhận SQL++ thực tế, `@Scope`/`@Collection` và type key |
| SQL++ không nhận `#{#n1ql.collection}` | Đưa SpEL nguyên văn vào Query Workbench/SDK | Chỉ dùng SpEL trong `@Query` của Spring Data; Workbench dùng đường dẫn SQL++ thuần |
| `FROM products` không xác định được keyspace | Chưa đặt query context hoặc đặt sai bucket/scope | Dùng keyspace đầy đủ hoặc thiết lập query context đúng |
| Index đã tạo nhưng query vẫn báo thiếu index | Index nằm ở collection/scope khác với nguồn `FROM` | Kiểm tra đường dẫn index và keyspace thực tế |
| Sửa `@Collection("products")` sang `@Collection("archived_products")` rồi mất dữ liệu | Sửa mapping không tự chuyển document | Dùng quy trình migration và tạo index trên collection mới |
| `#n1ql.bucket` trỏ đúng bucket nhưng query vẫn sai | Bucket không đồng nghĩa collection trong scope tùy biến | Kiểm tra cả `#n1ql.scope`, `#n1ql.collection` và query context |
| Truy vấn trả một document `Promotion` thay vì `Product` | Câu SQL++ thô dùng chung collection/field, thiếu type filter | Dùng Repository đúng entity, `#n1ql.filter` hoặc điều kiện loại tin cậy |
| `SELECT *` trả JSON nhưng entity thiếu ID/CAS | Phép chiếu không theo hợp đồng full entity | Dùng `#n1ql.selectEntity` hoặc phép chiếu entity được thư viện hỗ trợ |
| Câu `@Query` có hai `FROM` | Thêm `FROM` sau `#n1ql.selectEntity` | Dùng macro ở đầu query hoặc tự viết `SELECT #{#n1ql.fields} FROM ...` |
| Dùng `FROM $collection` không chạy như mong muốn | Placeholder SQL++ là giá trị, không phải định danh | Chọn keyspace từ metadata hoặc whitelist rồi tạo cú pháp có kiểm soát |
| Query của tenant A đọc nhầm dữ liệu tenant B | Chỉ định đúng collection nhưng không có ràng buộc tenant | Bảo vệ quyền truy cập ở cả KV và SQL++, không chỉ dựa vào keyspace |
| Truy vấn JOIN nhân nhiều hàng cho một SKU | Collection sự kiện có nhiều bản ghi trên cùng SKU | Dùng DTO/report hoặc tổng hợp theo nghiệp vụ; không coi mỗi row là một entity |
| API SDK không hiểu `#n1ql.filter` | SDK không có SpEL context của Spring Data | Tự khai báo SQL++ đúng với schema/type mapping thực |
| Vừa lưu được theo ID nhưng `@Query` chưa thấy | Index cập nhật bất đồng bộ theo consistency | Dùng KV khi có ID hoặc cấu hình scan consistency phù hợp |
| Truy vấn collection có tên giống nhau ở hai scope trả kết quả khác | `FROM` rút gọn phụ thuộc query context | Chỉ rõ keyspace đầy đủ và đối chiếu môi trường |
| Đổi cách phân cấp scope làm phép thử cũ lỗi | Môi trường test không có cùng scope/collection/index | Đồng bộ tạo keyspace, migration, quyền và index giữa các môi trường |

### Quy trình xử lý lỗi theo thứ tự

1. **Xác định document gốc:** ID nào, body JSON nào, document thực sự nằm trong collection nào?
2. **Xác định mapping:** entity nào được Repository quản lý, có `@Scope`/`@Collection` đúng không, bucket được cấu hình là gì?
3. **Xác định SpEL:** `selectEntity`, `fields`, `bucket`, `scope`, `collection` và `filter` đã được Spring Data phân giải đúng chưa?
4. **Xác định SQL++ cuối cùng:** `FROM` trỏ tới đâu, có alias, type discriminator, tenant filter và tham số đúng không?
5. **Xác định query context:** có đang dùng tên collection rút gọn không? Workbench, Spring Data và SDK có cùng context không?
6. **Xác định vận hành:** quyền, index, `EXPLAIN`, TTL, scan consistency và dữ liệu vừa ghi.

Khi log câu truy vấn, ẩn thông tin nhạy cảm của user/tenant và các giá trị tham số theo chính sách bảo mật. Câu SQL++ có thể được sử dụng để xác định nguồn dữ liệu, nhưng không nên ghi bừa bãi document body hoặc khóa truy cập.

## 14. Bài thực hành có đáp án

Các bài sau dùng dữ liệu mẫu ở phần 2. Khi kiểm thử Repository, nên lưu document bằng Spring Data converter của dự án để có discriminator phù hợp và tạo index cần thiết. Các phép tính/kết quả được suy ra từ dữ liệu mẫu, không phải kết quả chạy trên một cluster thật trong bài viết này.

### Bài 1 — Viết đường dẫn keyspace đầy đủ

**Yêu cầu:** Tìm SKU và giá của sản phẩm đang hoạt động trong bucket `catalog`, scope `commerce`, collection `products`.

```sql
SELECT p.sku, p.price
FROM `catalog`.`commerce`.`products` AS p
WHERE p.active = true
ORDER BY p.sku;
```

**Đáp án:** Hai hàng KB-101 (1.450.000) và KB-202 (1.950.000). MS-301 bị loại do `active = false`. Document `KBDISCOUNT` không xuất hiện vì ở collection `promotions`.

### Bài 2 — Viết `@Query` không hardcode `FROM`

**Yêu cầu:** Repository trả full entity `Product` thuộc category do caller truyền. Sử dụng phép chiếu phù hợp mapping.

```java
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND category = $category")
List<Product> findByCategoryMapped(
    @Param("category") String category
);
```

**Đáp án:** Gọi `findByCategoryMapped("keyboard")` tìm KB-101, KB-202. `selectEntity` sinh `SELECT/FROM` theo entity; `filter` lọc type; `$category` binding giá trị. Không cần tự viết tên bucket/scope/collection trong method này.

### Bài 3 — Phân biệt `selectEntity` và `fields`

**Yêu cầu:** Dạng nào sau đây hợp lý cho `List<Product>`?

```java
// A
@Query("#{#n1ql.selectEntity} WHERE #{#n1ql.filter} "
     + "AND active = true")
List<Product> queryA();

// B
@Query("SELECT #{#n1ql.fields} "
     + "FROM #{#n1ql.collection} "
     + "WHERE #{#n1ql.filter} AND active = true")
List<Product> queryB();

// C
@Query("SELECT #{#n1ql.selectEntity} "
     + "FROM #{#n1ql.collection} "
     + "WHERE active = true")
List<Product> queryC();
```

**Đáp án:** A là mẫu đơn giản đúng mục đích full entity. B minh họa cách tự cung cấp `SELECT/FROM` nhưng phải xác minh query context và version. C sai vì `selectEntity` đã tạo `SELECT/FROM`, không thể lồng lại vào `SELECT`.

### Bài 4 — Query context thay đổi nguồn dữ liệu như thế nào?

**Tình huống:** Có hai collection `catalog.commerce.products` và `catalog.archive.products`. Truy vấn ghi:

```sql
SELECT p.sku
FROM `products` AS p;
```

**Đáp án:** Không thể kết luận nó đang đọc `commerce.products` chỉ từ câu SQL++ này. Kết quả phụ thuộc query context; nếu không có context phù hợp có thể lỗi, nếu context khác có thể đọc dữ liệu khác. Dùng keyspace ba cấp để chắc chắn hoặc đặt query context tường minh và kiểm thử.

### Bài 5 — Chọn collection động một cách an toàn

**Tình huống:** User nhập `collection=promotions` qua HTTP. Có nên nội suy chuỗi này vào `FROM` bằng `String.concat` hoặc SpEL?

**Đáp án:** Không. Giá trị từ user không được dùng làm định danh SQL++ nếu chưa qua cơ chế kiểm soát. Khi nghiệp vụ cho phép hai lựa chọn, ánh xạ enum/whitelist cố định đến hai keyspace đã được ứng dụng phê duyệt, đồng thời kiểm tra authorization. Giá trị `category` hoặc `maxPrice` vẫn được binding bằng `$name`.

### Bài 6 — Sửa câu query đang dùng sai placeholder

**Đầu bài:**

```sql
SELECT p.sku
FROM $collection AS p
WHERE p.category = $category;
```

**Đáp án sửa:** Chọn `FROM` theo keyspace cố định:

```sql
SELECT p.sku
FROM `catalog`.`commerce`.`products` AS p
WHERE p.category = $category;
```

Sau đó SDK/Repository binding `$category` như một **giá trị**. Không binding `$collection` để thay tên collection.

### Bài 7 — Chỉ mục trên collection nào?

**Yêu cầu:** Có hai collection tên `products` ở scope `commerce` và `archive`. Truy vấn trong ứng dụng luôn tìm sản phẩm đang hoạt động ở `commerce.products` theo `category` và `price`. Hãy đề xuất index để đánh giá.

```sql
CREATE INDEX idx_commerce_products_filter
ON `catalog`.`commerce`.`products`(
    category, active, price
);
```

**Đáp án phân tích:** Index nằm ở `commerce.products`, không phải `archive.products`. Dùng `EXPLAIN` trên query chính xác, đối chiếu thêm filter kiểu và phép chiếu entity. Không khẳng định index này là tối ưu khi chưa có số liệu thực tế.

### Bài 8 — Phân biệt readback theo ID và query theo category

**Tình huống:** Vừa lưu KB-404 vào `catalog.commerce.products`. `findById("product::KB-404")` đọc được document, nhưng `@Query` tìm theo category chưa thấy.

**Đáp án:** Trước tiên xác minh mapping và đường dẫn collection. Nếu cả hai đúng, khả năng khác biệt do **index chưa cập nhật** dưới scan consistency `NOT_BOUNDED`. Cân nhắc `REQUEST_PLUS` cho yêu cầu thấy ghi mới hoặc dùng KV khi đã có ID. Đổi `#n1ql.collection` sang một chuỗi khác không giải quyết vấn đề độ mới index.

### Bài 9 — Khi nào cần projection thay full entity?

**Yêu cầu:** Join `commerce.products` với `inventory.stock_events` để trả danh sách SKU và số thay đổi tồn kho, có thể nhiều sự kiện cho một SKU. Nên trả `List<Product>` và dùng `selectEntity` không?

**Đáp án:** Thường không. Kết quả JOIN là **hàng báo cáo**, có thể nhiều hàng cho cùng product. Cần DTO/projection hoặc JSON row mapping tương ứng với `sku` và `stockChange`, không cố giả định mỗi hàng có document ID/CAS của một entity duy nhất.

### Bài 10 — Kiểm tra migration giữa scope

**Yêu cầu:** Chuyển Product từ `catalog._default._default` sang `catalog.commerce.products`. Lập checklist tối thiểu trước khi đổi annotation.

**Đáp án tham khảo:** Xác định document nguồn/đích và ID; tạo scope/collection đích; chuyển dữ liệu bảo đảm mapping type và CAS/TTL theo chính sách; tạo index và quyền cho đích; cập nhật Repository/Template/SDK query; kiểm thử tìm theo ID và `@Query`; xác nhận scan consistency; chuẩn bị rollback và xử lý concurrent writes. Chỉ sửa `@Collection` không thực hiện migration.

## 15. Câu hỏi tự kiểm tra

1. **`#n1ql.bucket` đại diện cấp nào?** Bucket theo metadata mapping, không tự là đường dẫn ba cấp.
2. **`#n1ql.scope` dùng để làm gì?** Xác định scope tương ứng entity theo Spring Data.
3. **`#n1ql.collection` có phải alias SQL++ như `p` không?** Không, nó đại diện tên collection của entity.
4. **Đâu là keyspace đầy đủ của sản phẩm trong bài?** `catalog.commerce.products`.
5. **`selectEntity` khác ba biến keyspace thế nào?** Nó tạo phần `SELECT/FROM` và phép chiếu cần cho full entity; các biến keyspace chỉ biểu diễn thành phần tên nguồn.
6. **`fields` có tự thêm `FROM` không?** Không; phải viết `SELECT/FROM` và xác minh context nếu dùng riêng.
7. **`$category` có thể thay `#n1ql.collection` không?** Không; một bên là giá trị, bên kia là định danh do Spring Data xử lý.
8. **Tại sao `FROM products` chưa chắc trỏ đúng collection?** Vì thiếu bucket/scope và phụ thuộc query context.
9. **Tại sao có index nhưng query báo thiếu index?** Có thể query vào keyspace khác index được tạo.
10. **Đổi `@Collection` có tự chuyển dữ liệu không?** Không.
11. **`#n1ql.filter` có thay điều kiện tenant và authorization không?** Không; nó chủ yếu lọc loại entity.
12. **SDK `Cluster.query` có phân giải `#{#n1ql.bucket}` không?** Không; đó là biểu thức Spring Data.
13. **Reactive repository có tự đổi tên collection không?** Không; mapping vẫn xác định keyspace.
14. **CAS và TTL có được cấu hình bằng `#n1ql.scope` không?** Không; đây là các cơ chế phiên bản và thời hạn sống document.
15. **Khi có document ID và cần đọc nhanh, có nhất thiết dùng SQL++ không?** Không; Key/Value thường thích hợp hơn.

## Tài liệu tham khảo chính thức

- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): `@Query`, SpEL `#n1ql`, phép chiếu entity và tham số.
- [Spring Data Couchbase — Collections](https://docs.spring.io/spring-data/couchbase/reference/couchbase/collections.html): ánh xạ bucket, scope, collection trong domain object và Repository.
- [Spring Data Couchbase — Entity Mapping](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Document`, `@Id`, `@Version` và metadata document.
- [Couchbase Server — Buckets, Scopes and Collections](https://docs.couchbase.com/server/current/learn/data/scopes-and-collections.html): mô hình tổ chức dữ liệu nhiều cấp.
- [Couchbase Server — SQL++ SELECT](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/selectintro.html): keyspace trong `FROM` và cấu trúc truy vấn.
- [Couchbase Server — Indexing](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/indexing.html): index theo keyspace và phân tích kế hoạch.
- [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/n1ql-queries-with-sdk.html): tham số hóa, query context và truy vấn bằng SDK.

**Ghi nhớ:** **`#{#n1ql.bucket}`, `#{#n1ql.scope}` và `#{#n1ql.collection}` là SpEL đại diện các cấp keyspace theo metadata Spring Data Couchbase**; chúng không phải tham số giá trị SQL++ hay cơ chế chọn nguồn dữ liệu tùy ý từ HTTP request. Với `@Query` trả full entity, thường nên dùng **`#{#n1ql.selectEntity} WHERE #{#n1ql.filter} AND ...`** để bảo toàn phép chiếu và loại document. Khi tự viết `FROM`, phải hiểu query context, đúng bucket/scope/collection, quyền và index của nguồn thực tế; sau đó mới đánh giá hiệu năng, scan consistency, TTL/CAS và transaction.

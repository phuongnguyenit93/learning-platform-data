# Ánh xạ lớp Java bằng @Document và @Id trong Spring Data Couchbase

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của `@Document`, `@Id` và `@Field` khi ánh xạ Java object sang Couchbase document.
2. Phân biệt **document key** ở metadata Couchbase với các thuộc tính trong **JSON body**.
3. Tạo một entity có khóa ổn định, ánh xạ tên field, đối tượng lồng nhau và cấu hình scope/collection.
4. Lưu, đọc và sửa entity qua Spring Data Couchbase repository; hiểu trường hợp dùng Key-Value (KV) và SQL++.
5. Nhận biết các sai sót thường gặp liên quan đến ID, vòng đời entity, `@Version` (CAS), TTL và index.

Trong module **SPRING_DATA_COUCHBASE**, mục đích của document mapping là biến lớp Java thành cấu trúc JSON để làm việc với repository, `CouchbaseTemplate` và truy vấn SQL++. Đây là nền tảng trước khi tối ưu bucket/scope/collection, index, nhất quán hay lựa chọn API reactive.

## 1. Từ lớp Java đến document Couchbase

Trong Couchbase, một document có hai phần cần tách bạch:

- **Document key (ID):** định danh document trong một collection; dùng cho thao tác KV như get, upsert, replace và remove.
- **JSON body:** các trường dữ liệu ứng dụng như tên, giá, trạng thái và danh sách thuộc tính. Couchbase còn quản lý metadata như CAS và expiry.

Spring Data Couchbase cung cấp cơ chế mapping giữa entity Java và JSON body; `@Id` ánh xạ thuộc tính Java sang **document key**. Các trường trong entity được ghi vào JSON theo quy tắc mapping, trừ những trường đặc biệt như ID, CAS version hoặc field bị đánh dấu `@Transient`.

~~~mermaid
flowchart LR
    A["Java Product\n@Id id\n@Field displayName\npriceVnd"] -->|"Spring Data mapping"| B["Couchbase collection"]
    B --> K["Metadata\nKey: product::coffee250\nCAS, expiry"]
    B --> J["JSON body\ndisplay_name\npriceVnd\n_class"]
    B -->|"đọc theo key"| A
~~~

Một annotation không thay thế chức năng của annotation khác:

| Annotation | Import | Ý nghĩa |
| --- | --- | --- |
| `@Document` | `org.springframework.data.couchbase.core.mapping.Document` | Đánh dấu lớp được ánh xạ như entity Couchbase; nên khai báo tường minh dù framework có thể nhận diện một số entity không có annotation này |
| `@Id` | `org.springframework.data.annotation.Id` | Chọn một thuộc tính làm **document key**; cần thiết với entity Couchbase |
| `@Field` | `org.springframework.data.couchbase.core.mapping.Field` | Khai báo field dữ liệu và có thể đổi tên field trong JSON; annotation này không bắt buộc với mọi thuộc tính |
| `@Scope`, `@Collection` | `org.springframework.data.couchbase.core.mapping` | Chỉ định scope/collection mặc định cho entity, có thể bị cấu hình hoặc lời gọi cụ thể ghi đè |
| `@Version` | `org.springframework.data.annotation.Version` | Ánh xạ CAS metadata để hỗ trợ optimistic locking |
| `@Transient` | `org.springframework.data.annotation.Transient` | Không lưu thuộc tính đó vào document |

**Điểm dễ nhầm:** `@Document` của Couchbase khác với `@Document` của Spring Data MongoDB; `@Id` của Spring Data khác với `jakarta.persistence.Id` dùng trong JPA. Đọc đúng package import quan trọng hơn tên annotation trùng nhau.

## 2. Ví dụ hoàn chỉnh: entity Product

Giả sử một cửa hàng lưu sản phẩm trong bucket **shop**, scope **catalog**, collection **products**. Bucket được cấu hình ở tầng kết nối; scope và collection được chọn trên entity.

~~~java
package com.example.shop.catalog;

import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("catalog")
@Collection("products")
public class Product {

    @Id
    private String id;

    @Field
    private String sku;

    @Field("display_name")
    private String displayName;

    @Field
    private long priceVnd;

    @Field
    private List<String> tags = new ArrayList<>();

    @Version
    private Long version;

    protected Product() {
        // Constructor cho Spring Data khi materialize entity.
    }

    public Product(String sku, String displayName, long priceVnd) {
        if (sku == null || !sku.matches("[a-z0-9-]+")) {
            throw new IllegalArgumentException("SKU không hợp lệ");
        }
        if (displayName == null || displayName.isBlank() || priceVnd < 0) {
            throw new IllegalArgumentException("Thông tin sản phẩm không hợp lệ");
        }
        this.id = "product::" + sku;
        this.sku = sku;
        this.displayName = displayName;
        this.priceVnd = priceVnd;
    }

    public String getId() { return id; }
    public String getSku() { return sku; }
    public String getDisplayName() { return displayName; }
    public long getPriceVnd() { return priceVnd; }
    public List<String> getTags() { return List.copyOf(tags); }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        this.displayName = newName;
    }

    public void changePrice(long newPriceVnd) {
        if (newPriceVnd < 0) {
            throw new IllegalArgumentException("Giá không thể âm");
        }
        this.priceVnd = newPriceVnd;
    }
}
~~~

Đây là ví dụ tối giản dành cho học tập: SKU được chuẩn hóa thành chữ thường/số/dấu gạch ngang trước khi tạo `Product`; ứng dụng thật cần quy ước khóa và kiểm tra hợp lệ ở biên API. Việc dùng số nguyên `long` là một lựa chọn minh họa cho đơn vị VND, tránh vấn đề làm tròn số thực; hệ thống đa tiền tệ cần kiểu tiền và quy tắc tính toán riêng.

### Giải mã các annotation trong ví dụ

- `@Document` báo rõ đây là root entity được lưu thành document.
- `@Id private String id` giữ Couchbase key, ví dụ `product::coffee250`; trường `id` này **không phải** một field JSON thông thường.
- `@Field("display_name")` ánh xạ thuộc tính `displayName` sang tên `display_name` trong JSON.
- `sku`, `priceVnd`, `tags` là dữ liệu nghiệp vụ trong body. `List<String>` được ánh xạ thành mảng JSON.
- `@Version Long version` được Spring Data dùng với CAS để phát hiện bản ghi đã bị thay đổi bởi tiến trình khác; không tự set hay tự tăng version.
- `@Scope("catalog")` và `@Collection("products")` chọn nơi lưu theo định nghĩa của entity. Chúng **không tạo** scope/collection và không thiết lập bucket `shop`.

Với `new Product("coffee250", "Cà phê hạt 250 g", 120000)`, bạn có thể hình dung document sau khi lưu như sau:

~~~text
Bucket: shop
Scope: catalog
Collection: products
Document key: product::coffee250
~~~

~~~json
{
  "_class": "com.example.shop.catalog.Product",
  "sku": "coffee250",
  "display_name": "Cà phê hạt 250 g",
  "priceVnd": 120000,
  "tags": []
}
~~~

Phần JSON trên là **minh họa mapping mặc định**: `_class` là thông tin loại entity do Spring Data dùng trong một số hoạt động mapping/query; không nên giả định nó luôn tồn tại nếu hệ thống đã tùy biến type mapper. Trường `id` và `version` được quản lý tương ứng qua document key và CAS metadata nên không cần xuất hiện như hai field JSON trong ví dụ.

## 3. Thiết kế @Id: khóa bền vững và duy nhất

`@Id` xác định khóa truy cập KV. Hai document trong **cùng collection** không thể cùng tồn tại dưới cùng một document key; cùng chuỗi key ở collection khác là định danh thuộc không gian khác. Khóa Couchbase là chuỗi, tối đa **250 byte**.

Ví dụ cách đặt key có chủ ý:

| Đối tượng | Ví dụ key | Đánh giá |
| --- | --- | --- |
| Product | `product::coffee250` | Dễ xây dựng lại từ SKU bất biến |
| Order | `order::01JXZ8...` | Tiền tố loại dữ liệu cộng ID đơn ổn định |
| Cart tạm | `cart::session-7a29` | Phải gắn với quy tắc TTL và bảo mật |
| Product lấy tên làm ID | `product::ca-phe-hat` | Dễ đổi tên gây đổi key; nên tránh nếu tên hay thay đổi |

Nguyên tắc:

1. **Ổn định:** key của entity không nên đổi trong vòng đời; cập nhật thuộc tính nghiệp vụ mà không thay `@Id`.
2. **Nhất quán:** quyết định dùng key có tiền tố, ID ngẫu nhiên hay ID miền và áp dụng đồng bộ ở nơi tạo/đọc.
3. **An toàn:** không ghép trực tiếp PII, token, mật khẩu hoặc chuỗi do client nhập mà chưa xác thực/chuẩn hóa.
4. **Tránh collision:** khi có nhiều tenant, cân nhắc collection tách riêng hoặc cơ chế phân vùng khóa rõ ràng.
5. **Lựa chọn thao tác:** nếu biết key chính xác, truy cập bằng KV nhanh và không cần secondary index cho thuộc tính đó.

### Gán key bằng ứng dụng

Ở ví dụ `Product`, constructor tạo `id = "product::" + sku`. Cách này có lợi khi SKU là định danh miền không đổi: muốn xem sản phẩm theo SKU, chỉ cần dựng key và gọi `findById`.

Nếu ID là ngẫu nhiên, có thể tạo tại service lúc sinh entity:

~~~java
String id = "order::" + java.util.UUID.randomUUID();
~~~

Trong thiết kế này, entity Order cần nhận `id` qua constructor, và service nên lưu/idempotency theo yêu cầu nghiệp vụ; tuyệt đối không tạo ID mới mỗi lần cập nhật một document cũ.

### Sinh key bằng annotation khi cần

Spring Data Couchbase có cơ chế `@GeneratedValue` trong package `org.springframework.data.couchbase.core.mapping.id`. Một ví dụ tối giản dùng thuộc tính:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.id.GeneratedValue;
import org.springframework.data.couchbase.core.mapping.id.GenerationStrategy;
import org.springframework.data.couchbase.core.mapping.id.IdAttribute;

@Document
class Customer {
    @Id
    @GeneratedValue(strategy = GenerationStrategy.USE_ATTRIBUTES)
    private String id;

    @IdAttribute
    private String customerCode;

    // Constructor và các field khác...
}
~~~

Khi `id` chưa có giá trị, Spring Data có thể tạo key từ thuộc tính có `@IdAttribute`. Có thêm `@IdPrefix`, `@IdSuffix` và tùy chọn delimiter nếu cần key ghép; việc tạo sẽ bị bỏ qua khi `id` đã được gán. **Đánh giá tính ổn định và collision trước khi dùng trên dữ liệu thật**. Cơ chế `GenerationStrategy.UNIQUE` cũng tồn tại nhưng tài liệu chính thức khuyến nghị chủ yếu cho test/scaffolding. Không nhầm `@GeneratedValue` này với chiến lược ID của JPA hoặc auto-increment trong SQL.

## 4. Đọc, lưu và cập nhật entity qua Repository

Khai báo repository theo đúng loại entity và key:

~~~java
package com.example.shop.catalog;

import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface ProductRepository extends CouchbaseRepository<Product, String> {
    // CRUD theo document key có sẵn từ interface.
}
~~~

Sử dụng ở service (đã cấu hình kết nối Couchbase và nơi lưu):

~~~java
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }

    public Product create(String sku, String name, long priceVnd) {
        Product product = new Product(sku, name, priceVnd);
        return products.save(product);
    }

    public Product getBySku(String sku) {
        return products.findById("product::" + sku)
            .orElseThrow(() -> new IllegalArgumentException("Không tìm thấy sản phẩm"));
    }

    public Product rename(String sku, String newName) {
        Product product = getBySku(sku);
        product.rename(newName);
        return products.save(product);
    }
}
~~~

Đây là ví dụ service rút gọn, chưa thêm cơ chế phân biệt *create nếu chưa tồn tại* với *update nếu đã tồn tại*. **`save` không tự bảo đảm nghiệp vụ tạo mới duy nhất** trong mọi trường hợp: nếu hệ thống cần chống việc tạo trùng SKU một cách chặt chẽ, hãy dùng phép insert có ngữ nghĩa chỉ tạo mới và xử lý lỗi key đã tồn tại; nếu thao tác ghi có thể lặp do retry, thiết kế idempotency phù hợp.

Cần phân biệt đường đi dữ liệu:

| Thao tác | Đường đi thường dùng | Có cần secondary index không? |
| --- | --- | --- |
| `findById("product::coffee250")` | KV theo document key | Không |
| `save(product)` / `deleteById(id)` | KV cho một document có key | Không |
| `findByDisplayName("...")` (nếu tự khai báo) | SQL++ theo thuộc tính JSON | Có, cần index phù hợp |
| Trả danh sách sản phẩm lọc giá/sắp xếp | SQL++ | Có, cần index và truy vấn phù hợp |

Với nhu cầu đọc theo SKU, key tiền tố giúp tránh tìm `sku` bằng query. Nếu có nhiều người tìm theo `display_name`, cần chỉ mục trên đúng JSON field `display_name` và kiểm tra truy vấn Spring Data phát sinh. `@Document` và `@Field` tự chúng **không tạo chỉ mục truy vấn SQL++**.

### Tìm bằng CouchbaseTemplate

Ngoài repository, `CouchbaseTemplate` hỗ trợ CRUD entity và truy vấn linh hoạt. Ví dụ đọc trực tiếp theo ID:

~~~java
import org.springframework.data.couchbase.core.CouchbaseTemplate;

public Product loadProduct(CouchbaseTemplate template, String id) {
    return template.findById(Product.class).one(id);
}
~~~

API template có thể chỉ định scope/collection động khi cần theo hệ thống cấu hình; thao tác nên được kiểm chứng với phiên bản Spring Data Couchbase đang dùng. Repository và template sử dụng cùng khái niệm entity/key/mapping; chuyển sang reactive repository/template thay đổi kiểu xử lý I/O, **không thay đổi** ý nghĩa của `@Document` hay `@Id`.

## 5. Constructor, field lồng nhau và mapping JSON

### Cách Spring Data khởi tạo lại entity

Spring Data phải tạo lại đối tượng khi đọc document. Với POJO mutable, cách dễ hiểu là có constructor không tham số (có thể `protected`) và field được framework ánh xạ. Nếu cần constructor duy nhất chứa mọi field, Spring Data có thể chọn constructor đó; khi có nhiều constructor phức tạp, dùng `@PersistenceCreator` và cấu hình thông tin tên tham số thích hợp.

**Đừng đặt logic làm đổi ID hoặc gọi dịch vụ bên ngoài trong constructor dùng để materialize.** Constructor trong ví dụ Product chỉ khởi tạo entity mới qua nghiệp vụ; constructor rỗng để framework đọc dữ liệu có sẵn.

### Đối tượng con có thể nằm trong cùng JSON

Ví dụ thông tin kích thước sản phẩm có thể là value object:

~~~java
public record Dimensions(int widthCm, int heightCm, int depthCm) {}
~~~

Nếu thêm field `@Field private Dimensions dimensions;` trong Product và được mapping phù hợp, JSON có thể chứa:

~~~json
{
  "dimensions": {
    "widthCm": 12,
    "heightCm": 18,
    "depthCm": 8
  }
}
~~~

Đối tượng con không cần có `@Document` và `@Id` riêng nếu nó là **giá trị nằm trong cùng một document**. Với quan hệ có vòng đời/ghi độc lập, lưu tham chiếu document key đến entity khác thay vì tự động nhúng toàn bộ object graph. Các kiểu `Map`, `List`, `String`, số và boolean có mapping tự nhiên; các kiểu đặc biệt như tiền tệ hay thời gian cần xác nhận biểu diễn JSON và converter tương ứng trước khi triển khai.

### Khác biệt tên Java và tên JSON

~~~java
@Field("display_name")
private String displayName;
~~~

Trong SQL++ phải tham chiếu `display_name`, còn khi viết Java sử dụng `displayName`. Thay đổi annotation này trên dữ liệu đang chạy là một **thay đổi schema logic**: những document cũ có field `displayName` sẽ không tự chuyển thành `display_name`. Lập kế hoạch migration hoặc đọc tương thích khi đổi tên field.

## 6. Metadata: CAS, TTL, durability và collection

Dù bài tập trọng tâm là `@Document` và `@Id`, cần biết những giới hạn kết nối tới vận hành.

**CAS với `@Version`:** Couchbase gán CAS cho document và thay đổi khi document được mutation. Khi load Product, Spring Data điền CAS vào field `version`; khi lưu, framework dùng nó để hỗ trợ optimistic locking. Hai request đồng thời đọc rồi sửa cùng document: request đến sau có thể nhận `OptimisticLockingFailureException` thay vì ghi đè âm thầm. Cần đọc lại, kiểm tra nghiệp vụ và thử lại toàn bộ chu trình có giới hạn, hoặc trả lỗi xung đột cho client; không chỉnh `version` bằng tay.

**TTL qua `@Document`:** document tạm có thể dùng `@Document(expiry = 3600)` để đặt thời hạn hết hạn sau mutation theo đơn vị giây, hoặc `expiryExpression` từ cấu hình. Không nên dùng TTL cho Product hay Order cần giữ lâu nếu chưa có chính sách lưu trữ rõ ràng.

**Durability:** có thể yêu cầu mức độ bền vững khi ghi thông qua cấu hình/`@Document` tùy phiên bản, ví dụ `durabilityLevel = DurabilityLevel.MAJORITY`. Đây là tiêu chí đảm bảo ghi được xác nhận theo số replica, **khác** với optimistic locking, TTL và tính nhất quán khi truy vấn bằng index.

**Bucket/scope/collection:** giả sử bucket `shop` đã cấu hình, entity `@Scope("catalog") @Collection("products")` trỏ vào `shop.catalog.products`. Các annotation có thể đặt ở repository, và template có thể chọn scope/collection khi gọi; mức ưu tiên phụ thuộc cơ chế override. Vì vậy, khi dữ liệu “đi nhầm collection”, kiểm tra configuration, repository và template trước khi kết luận do `@Document`.

## 7. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `findById` trả rỗng dù thấy JSON trong UI | Khóa khác, scope/collection khác hoặc cấu hình bucket khác | Kiểm tra đầy đủ bucket.scope.collection và chính xác document key |
| Entity mới không có ID hợp lệ | Quên `@Id` hoặc chưa gán/generate ID | Dùng một field `@Id`, thống nhất chiến lược tạo key trước khi lưu |
| Đọc entity bị thiếu thuộc tính | Tên field JSON không trùng mapping, rename thiếu migration | So sánh JSON body và `@Field("...")`, rà soát dữ liệu cũ |
| Tìm theo thuộc tính bị lỗi/timeout | Truy vấn SQL++ thiếu index hoặc index không phù hợp | Tạo index đúng với điều kiện WHERE/ORDER BY và chạy EXPLAIN |
| Ghi đồng thời báo `OptimisticLockingFailureException` | CAS thay đổi sau khi đọc | Đọc lại và kiểm tra lại nghiệp vụ; retry có giới hạn hoặc báo xung đột |
| Lấy JSON thủ công thấy `_class` | Type metadata do Spring Data lưu theo mapping | Hiểu ý nghĩa của metadata; không tự xóa nếu còn phụ thuộc mapping/query |
| Document tự biến mất sau một thời gian | TTL, expiry expression hoặc bucket/collection policy | Kiểm tra expiry và chính sách lưu trữ |
| Dùng `@Id` JPA nhưng mapping không như mong đợi | Sai package import | Dùng `org.springframework.data.annotation.Id` |
| Đổi SKU dẫn đến mất liên kết | Key được xây dựng từ SKU nhưng nghiệp vụ cho đổi SKU | Giữ SKU bất biến hoặc dùng ID độc lập làm key, SKU là thuộc tính có ràng buộc riêng |

Lưu ý khác: ID của Couchbase không phải *foreign key* như cơ sở dữ liệu quan hệ; annotation mapping không tự đảm bảo các document tham chiếu vẫn tồn tại. Cần giải quyết ở dịch vụ nghiệp vụ hoặc quy trình dữ liệu.

## 8. Thực hành: tự ánh xạ một Customer

**Yêu cầu:** thiết kế entity Customer lưu ở bucket `shop`, scope `crm`, collection `customers`; khóa `customer::u100`; body gồm `email`, `full_name`, `active`. Muốn đọc theo ID mà không cần secondary index, và khi hai request sửa đồng thời thì một bên nhận tín hiệu xung đột.

**Đáp án tham khảo:**

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("crm")
@Collection("customers")
public class Customer {
    @Id
    private String id;

    @Field
    private String email;

    @Field("full_name")
    private String fullName;

    @Field
    private boolean active;

    @Version
    private Long version;

    protected Customer() {}

    public Customer(String userId, String email, String fullName) {
        this.id = "customer::" + userId;
        this.email = email;
        this.fullName = fullName;
        this.active = true;
    }

    public String getId() { return id; }
    public String getEmail() { return email; }
    public String getFullName() { return fullName; }

    public void updateName(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        this.fullName = name;
    }
}
~~~

Truy cập `CustomerRepository extends CouchbaseRepository<Customer, String>` và gọi `findById("customer::u100")`. Khi thiết kế thao tác *tạo mới* cần bảo vệ ID trùng; khi sửa, đọc entity cùng CAS trước khi save.

**Câu hỏi tự kiểm tra:**

1. Nếu JSON của Customer không có field `id`, repository có đọc được bằng `findById` không? **Có**, vì key nằm ngoài body JSON.
2. Đổi `@Field("full_name")` sang `@Field("name")` có tự chuyển dữ liệu cũ không? **Không**, cần migration/chiến lược tương thích.
3. `@Document` có tự tạo index trên `email` không? **Không**. Query theo email phải có index được thiết kế phù hợp.
4. Có nên gán `version = version + 1` khi sửa? **Không**, CAS do Couchbase và Spring Data quản lý.
5. Khi chuyển qua reactive repository, ID và cấu trúc JSON có thay đổi không? **Không**; sự khác biệt là API truy cập bất đồng bộ và xử lý I/O.

## 9. Checklist trước khi đưa entity vào ứng dụng

- [ ] Xác định entity root và collection thực sự cần lưu; chỉ annotate root `@Document`.
- [ ] Import đúng `@Id` của Spring Data, kiểm tra key được tạo ổn định và không vượt giới hạn.
- [ ] Thiết kế tên field JSON bền vững; dùng `@Field` khi cần khác tên Java.
- [ ] Cấu hình đúng bucket, scope, collection và repository/template.
- [ ] Cấu hình mapping kiểu dữ liệu/constructor, `@Version` nếu có ghi đồng thời.
- [ ] Tách thao tác KV theo key và query SQL++ theo thuộc tính; tạo chỉ mục khi có query.
- [ ] Kiểm chứng lưu/đọc một document, update đồng thời, trường dữ liệu cũ và chính sách TTL.

## Tài liệu tham khảo chính thức

- [Spring Data Couchbase — Modeling Entities](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Document`, `@Id`, `@Field`, object mapping và optimistic locking.
- [Spring Data Couchbase — Auto generating keys](https://docs.spring.io/spring-data/couchbase/reference/couchbase/autokeygeneration.html): chiến lược sinh document key và các annotation liên quan.
- [Spring Data Couchbase — Collection Support](https://docs.spring.io/spring-data/couchbase/reference/couchbase/collections.html): `@Scope`, `@Collection` và thứ tự ưu tiên cấu hình.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): thao tác theo ID và truy vấn SQL++.
- [Couchbase — Key-Value Operations](https://docs.couchbase.com/server/current/guides/kv-operations.html): truy cập document bằng key.

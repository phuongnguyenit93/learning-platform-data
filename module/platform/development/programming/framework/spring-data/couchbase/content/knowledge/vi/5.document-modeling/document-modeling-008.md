# Constructor, @PersistenceCreator và khởi tạo entity bất biến trong Spring Data Couchbase

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **hai giai đoạn ánh xạ** từ Couchbase document thành Java entity: tạo instance và nạp các thuộc tính còn lại.
2. Chọn đúng constructor hoặc factory method bằng quy tắc của Spring Data, sử dụng `@PersistenceCreator` khi cần phân biệt nhiều đường khởi tạo.
3. Thiết kế **entity bất biến** với `final` fields, constructor đầy đủ, static factory và phương thức tạo bản sao thay vì setter.
4. Dùng `@Id`, `@Field`, `@Version`, record/value object và collection bất biến mà vẫn đọc–ghi được bằng repository.
5. Chẩn đoán lỗi thiếu tên tham số, kiểu JSON không tương thích, field mới được bổ sung, constructor có side effect và cập nhật trên CAS cũ.
6. Biết khi nào cần kiểm thử mapping trên Couchbase thật, kể cả khi dùng `CouchbaseTemplate`, transaction hoặc API reactive.

Bài thuộc chương **Mô hình tài liệu** của module **SPRING_DATA_COUCHBASE**. Spring Data Couchbase ánh xạ Java object với JSON trong Couchbase, hỗ trợ repository, `CouchbaseTemplate`, SQL++, bucket/scope/collection, CAS, TTL, giao dịch và API reactive. Trong các khả năng đó, **constructor được dùng để dựng entity từ dữ liệu lưu trữ** là một chi tiết dễ bị bỏ qua nhưng ảnh hưởng trực tiếp đến tính đúng đắn, khả năng bảo trì và an toàn khi nâng cấp schema.

## 1. Vì sao constructor quan trọng với document mapping?

Một API đọc sản phẩm từ Couchbase thường trông rất đơn giản:

~~~java
Product product = productRepository.findById("product::coffee250")
    .orElseThrow();
~~~

Tuy nhiên, sau khi Couchbase trả về JSON body và metadata, Spring Data cần:

1. Xác định **kiểu Java cần dựng**, dựa trên kiểu mà repository/template yêu cầu và thông tin type mapping nếu cần.
2. Chọn **constructor hoặc static factory method** để tạo instance.
3. Ánh xạ từng đối số constructor từ trường tương ứng trong document, bao gồm các tùy biến tên `@Field`. Các thuộc tính đặc biệt như `@Id` và `@Version` được lấy từ document key/CAS metadata.
4. Nạp những persistent property **chưa được constructor tiêu thụ** bằng cơ chế property population thích hợp.
5. Trả về entity đã materialize cho service.

~~~mermaid
flowchart LR
    A["Couchbase\nkey + CAS + JSON"] --> B["Mapping context"]
    B --> C["Chọn constructor\nhoặc factory"]
    C --> D["Tạo instance"]
    D --> E["Nạp property còn lại"]
    E --> F["Java entity"]
~~~

Nếu entity có **setter** và constructor không tham số, bước cuối có thể gán từng field sau khi tạo object. Nếu entity có **`final` fields**, một constructor chứa đủ dữ liệu cho phép tạo instance hoàn chỉnh ngay từ đầu. Đây là lý do Spring Data khuyến nghị mô hình bất biến và constructor đầy đủ khi phù hợp với thiết kế miền.

Điểm cần phân biệt: JSON **không chứa constructor**, còn `@Document` **không tự quyết định gọi một constructor cụ thể** khi lớp có nhiều đường khởi tạo. Framework phải lựa chọn theo những quy tắc ánh xạ được công bố.

## 2. Quy tắc Spring Data chọn đường khởi tạo

Theo tài liệu Spring Data Couchbase/Spring Data Commons hiện hành, quá trình chọn đường khởi tạo được mô tả bằng các trường hợp sau (thứ tự ưu tiên có ý nghĩa):

| Trường hợp | Đường khởi tạo được chọn | Điểm cần chú ý |
| --- | --- | --- |
| Có đúng **một static factory method** gắn `@PersistenceCreator` | Factory method đó | Tham số factory phải giải quyết được từ dữ liệu persistence |
| Lớp chỉ có **một constructor** | Constructor duy nhất | Có thể dùng ngay cả khi không có constructor rỗng |
| Có nhiều constructor, đúng **một constructor** gắn `@PersistenceCreator` | Constructor được đánh dấu | Giải quyết sự mơ hồ giữa constructor nghiệp vụ và constructor persistence |
| Java `record` | **Canonical constructor** | Tên component tương ứng tên thuộc tính |
| Có constructor không tham số và không có đường ưu tiên hơn | Constructor không tham số | Sau đó nạp các field; constructor khác có thể bị bỏ qua |

Nếu có nhiều constructor nhưng không có đường được chọn rõ ràng theo những quy tắc này, mapping có thể không tìm được constructor phù hợp hoặc hành vi không như bạn dự tính. Tránh thiết kế phụ thuộc vào đoán định: chỉ định tường minh hoặc sắp xếp lại các constructor.

**`@PersistenceCreator` cần import đúng:**

~~~java
import org.springframework.data.annotation.PersistenceCreator;
~~~

Không nhầm với `@PersistenceContext` của JPA; trong mã Spring Data cũ có thể gặp tên `@PersistenceConstructor` từng được sử dụng. Khi dùng các ví dụ hiện đại, hãy chọn `@PersistenceCreator` và kiểm tra phiên bản dependency thực tế.

### Một constructor duy nhất: không cần constructor rỗng

~~~java
public class Category {
    private final String code;
    private final String label;

    public Category(String code, String label) {
        this.code = code;
        this.label = label;
    }

    public String getCode() { return code; }
    public String getLabel() { return label; }
}
~~~

Nếu Spring Data cần materialize `Category` như object lồng nhau và đây là constructor duy nhất có tham số được ánh xạ, nó có thể dựng object trực tiếp từ `code` và `label`. Bạn **không phải thêm constructor rỗng chỉ vì đang làm việc với JSON**.

Tuy nhiên, việc lấy đúng giá trị đòi hỏi **tên tham số constructor** có thể được xác định; đây là bước dễ thiếu trong quá trình build.

## 3. Tên tham số constructor và @Field

Đối số constructor được gắn với **tên property Java**, rồi mapping context áp dụng tên field Couchbase tương ứng. Xét:

~~~java
@Field("display_name")
private final String displayName;

@Field("price_vnd")
private final long priceVnd;

@PersistenceCreator
public Product(String displayName, long priceVnd) {
    this.displayName = displayName;
    this.priceVnd = priceVnd;
}
~~~

JSON chứa:

~~~json
{
  "display_name": "Cà phê hạt",
  "price_vnd": 150000
}
~~~

- Tên tham số Java là **`displayName`** và **`priceVnd`**, khớp tên thuộc tính Java.
- Mapping biết `displayName` nằm ở JSON key `display_name` vì `@Field`.
- Đổi tên tham số Java thành `name` nhưng không có property tương ứng có thể khiến Spring Data không giải quyết được đối số.
- Nếu dữ liệu cũ có tên JSON khác, constructor không tự đóng vai trò migration.

Để tên tham số Java có mặt trong bytecode, thường cần biên dịch với **`-parameters`** hoặc cung cấp metadata qua `@ConstructorProperties`:

~~~java
import java.beans.ConstructorProperties;

@ConstructorProperties({"displayName", "priceVnd"})
public Product(String displayName, long priceVnd) {
    this.displayName = displayName;
    this.priceVnd = priceVnd;
}
~~~

Đoạn ví dụ trên chỉ minh họa metadata; với lớp thực tế hãy chọn một cách cấu hình nhất quán. Nếu dự án dùng Spring Boot/Maven/Gradle, xác nhận compiler có phát sinh parameter metadata thay vì suy từ việc tên tham số còn hiển thị trong source.

**Đừng đặt tên tham số theo JSON nếu property Java khác tên.** `@Field("display_name")` xử lý sự khác biệt tên lưu trữ; constructor nên đi theo property `displayName`.

## 4. Bắt đầu từ POJO mutable: dễ hiểu nhưng dễ tạo trạng thái chưa hợp lệ

Một entity thông dụng:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
public class Product {
    @Id
    private String id;

    @Field("display_name")
    private String displayName;

    @Field("price_vnd")
    private long priceVnd;

    protected Product() {}

    public Product(String id, String displayName, long priceVnd) {
        this.id = id;
        this.displayName = displayName;
        this.priceVnd = priceVnd;
    }

    public void setDisplayName(String name) {
        this.displayName = name;
    }
}
~~~

Spring Data có thể tạo instance bằng constructor rỗng và nạp properties sau đó. Nhưng trong khoảng thời gian object được khởi tạo, nó chưa có trạng thái miền hoàn chỉnh; thêm setter public cũng khiến code ứng dụng có thể bỏ qua những quy tắc như “giá không âm” hoặc “mã hàng không được rỗng”.

Kiểu mutable vẫn hữu ích trong những tình huống đơn giản, đặc biệt khi thư viện khác yêu cầu một số quy ước nhất định. Tuy nhiên, nếu muốn một entity luôn thỏa bất biến cơ bản, bạn có thể chuyển sang **constructor đủ thuộc tính và tạo bản sao khi thay đổi**.

## 5. Ví dụ trọng tâm: entity Product bất biến

Giả sử sản phẩm nằm trong bucket `shop`, scope `catalog`, collection `products`. Bucket được cấu hình qua kết nối; scope và collection được chỉ định trên entity.

Ví dụ sử dụng **Java 17+** và Spring Data Couchbase hiện đại. `Product` có các field `final`, không có setter; ID được tạo trước khi lưu để tránh phải sinh và gán vào đối tượng bất biến sau đó.

~~~java
package com.example.shop.catalog;

import java.util.List;
import java.util.Objects;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("catalog")
@Collection("products")
public final class Product {

    @Id
    private final String id;

    @Version
    private final Long version;

    @Field("display_name")
    private final String displayName;

    @Field("price_vnd")
    private final long priceVnd;

    @Field
    private final Packaging packaging;

    @Field
    private final List<String> tags;

    // Constructor cho Spring Data: có đầy đủ persistent properties.
    @PersistenceCreator
    public Product(
            String id,
            Long version,
            String displayName,
            long priceVnd,
            Packaging packaging,
            List<String> tags) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("ID không hợp lệ");
        }
        if (displayName == null || displayName.isBlank()) {
            throw new IllegalArgumentException("Tên sản phẩm không hợp lệ");
        }
        if (priceVnd < 0) {
            throw new IllegalArgumentException("Giá không thể âm");
        }
        this.id = id;
        this.version = version;
        this.displayName = displayName;
        this.priceVnd = priceVnd;
        this.packaging = Objects.requireNonNull(packaging, "packaging");
        this.tags = List.copyOf(Objects.requireNonNull(tags, "tags"));
    }

    // Factory nghiệp vụ: gọi bằng dữ liệu cần thiết khi tạo mới.
    public static Product create(
            String sku, String displayName,
            long priceVnd, Packaging packaging) {
        if (sku == null || !sku.matches("[a-z0-9-]+")) {
            throw new IllegalArgumentException("SKU không hợp lệ");
        }
        return new Product(
            "product::" + sku,
            null, // CAS chưa được đọc từ Couchbase
            displayName, priceVnd, packaging, List.of()
        );
    }

    // Thay đổi tạo một đối tượng mới, giữ nguyên ID và CAS đã đọc.
    public Product rename(String newName) {
        return new Product(
            id, version, newName, priceVnd, packaging, tags
        );
    }

    public Product changePrice(long newPriceVnd) {
        return new Product(
            id, version, displayName, newPriceVnd, packaging, tags
        );
    }

    public Product addTag(String tag) {
        if (tag == null || !tag.matches("[a-z0-9-]+")) {
            throw new IllegalArgumentException("Tag không hợp lệ");
        }
        if (tags.contains(tag)) {
            return this;
        }
        if (tags.size() >= 20) {
            throw new IllegalStateException("Quá nhiều nhãn");
        }
        var next = new java.util.ArrayList<>(tags);
        next.add(tag);
        return new Product(
            id, version, displayName, priceVnd, packaging, next
        );
    }

    public String getId() { return id; }
    public Long getVersion() { return version; }
    public String getDisplayName() { return displayName; }
    public long getPriceVnd() { return priceVnd; }
    public Packaging getPackaging() { return packaging; }
    public List<String> getTags() { return tags; }
}
~~~

Bốn quyết định thiết kế đáng chú ý:

1. **`@Id` trên `final String id`:** đây là document key Couchbase. Constructor nhận ID đã được service/factory tạo, nên khi đọc lại Spring Data có thể truyền key vào constructor.
2. **`@Version` trên `final Long version`:** đây là CAS do Couchbase quản lý. Constructor nhận CAS để khôi phục phiên bản đúng; không tăng `version` bằng tay như biến đếm.
3. **`@Field` và constructor parameters:** Java dùng `displayName`, JSON dùng `display_name`; Spring Data giải quyết qua mapping metadata.
4. **`List.copyOf(tags)`:** giữ bản sao collection không cho thay đổi qua getter; nếu phần tử là đối tượng mutable thì còn phải thiết kế bất biến của phần tử.

`@PersistenceCreator` trong ví dụ làm rõ constructor được dùng. Vì lớp chỉ có một constructor, annotation này không bắt buộc nhưng hữu ích cho người đọc và an toàn khi tương lai thêm constructor. Một lựa chọn còn gọn hơn là **chỉ để một all-args constructor và nhiều static factory không gắn annotation**; Spring Data thường tự chọn constructor duy nhất.

### 5.1. Value object lồng nhau bằng record

~~~java
package com.example.shop.catalog;

import org.springframework.data.couchbase.core.mapping.Field;

public record Packaging(
    @Field("weight_grams") int weightGrams,
    @Field String material
) {
    public Packaging {
        if (weightGrams <= 0 || material == null || material.isBlank()) {
            throw new IllegalArgumentException("Đóng gói không hợp lệ");
        }
    }
}
~~~

`record` phù hợp với value object nhỏ, bất biến, có canonical constructor theo các component. Spring Data hỗ trợ chọn canonical constructor của Java record khi materialize; `@Field("weight_grams")` thể hiện tên JSON khác tên component Java. Hãy xác nhận việc dùng annotation trên record component với phiên bản Java/Spring Data đang chạy bằng kiểm thử ghi–đọc thực tế.

Khi lưu một Product với key `product::coffee250`, JSON body minh họa:

~~~json
{
  "_class": "com.example.shop.catalog.Product",
  "display_name": "Cà phê hạt 250 g",
  "price_vnd": 150000,
  "packaging": {
    "weight_grams": 250,
    "material": "paper"
  },
  "tags": ["coffee", "organic"]
}
~~~

`_class` có thể được Spring Data type mapper lưu trong body theo cấu hình. `id` là document key và `version` đại diện CAS metadata, nên ví dụ không đưa hai giá trị này vào JSON body.

## 6. Dùng repository với entity bất biến

~~~java
package com.example.shop.catalog;

import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface ProductRepository
        extends CouchbaseRepository<Product, String> {
}
~~~

Service phải nhận **đối tượng mới** do `rename` hoặc `changePrice` tạo ra:

~~~java
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final ProductRepository products;

    public CatalogService(ProductRepository products) {
        this.products = products;
    }

    public Product createProduct() {
        Product product = Product.create(
            "coffee250",
            "Cà phê hạt 250 g",
            150000,
            new Packaging(250, "paper")
        );
        return products.save(product);
    }

    public Product rename(String id, String name) {
        Product current = products.findById(id)
            .orElseThrow(() -> new IllegalArgumentException("Không có sản phẩm"));

        Product next = current.rename(name);
        return products.save(next);
    }
}
~~~

**Vì sao phải dùng `return products.save(...)`?** Entity bất biến không thể tự nhận các thuộc tính mà persistence quản lý bằng setter. Tùy API/version, thao tác lưu có thể trả một instance mang trạng thái metadata mới như CAS. Luôn dùng instance được repository trả về cho những lần cập nhật tiếp theo, và kiểm chứng round-trip trên Couchbase thực tế.

Cách dùng sai:

~~~java
Product current = products.findById(id).orElseThrow();
current.rename("Tên mới"); // Bỏ kết quả: current không đổi.
products.save(current);    // Có thể ghi lại dữ liệu cũ.
~~~

Cách dùng đúng:

~~~java
Product current = products.findById(id).orElseThrow();
Product renamed = current.rename("Tên mới");
Product saved = products.save(renamed);
~~~

`findById(id)` thường đi qua KV theo document key, không cần secondary index. Repository query như `findByDisplayName(...)` dùng SQL++ theo thuộc tính JSON, cần chỉ mục thích hợp; việc immutable hay mutable **không thay đổi** đường truy cập đó.

### 6.1. CAS và phiên bản bất biến

Giả sử hai request cùng load Product tại CAS A:

- Request 1 tạo bản sao `changePrice(155000)` mang version A, rồi lưu thành công; Couchbase cấp CAS mới.
- Request 2 tạo bản sao `rename(...)` cũng mang version A, rồi lưu. Nếu dùng optimistic locking với `@Version`, nó có thể nhận `OptimisticLockingFailureException`.
- Request 2 **phải đọc lại document hiện hành**, tạo bản sao mới, kiểm tra lại quy tắc nghiệp vụ và lưu lại nếu vẫn hợp lệ.

~~~java
// Mẫu xử lý conflict ở tầng HTTP/service, mã minh họa:
try {
    Product current = products.findById(id).orElseThrow();
    return products.save(current.rename(newName));
} catch (org.springframework.dao.OptimisticLockingFailureException ex) {
    throw new IllegalStateException(
        "Sản phẩm đã thay đổi, vui lòng tải lại", ex
    );
}
~~~

Retry có thể áp dụng cho thao tác idempotent sau khi **đọc lại và tái đánh giá**. Không lặp vô hạn và không đưa thanh toán/gửi thông báo vào nhánh có thể chạy lại mà không có cơ chế idempotency. `@Version` bảo vệ xung đột ở **cấp document**, không phải riêng một field.

### 6.2. Tạo mới duy nhất không đồng nghĩa save vô điều kiện

Một `id` ổn định cho phép đọc nhanh, nhưng `save` không phải hợp đồng “insert only” trong mọi tình huống. Nếu yêu cầu chống ghi đè do hai request cùng tạo Product, dùng thao tác insert có ngữ nghĩa chỉ tạo mới và xử lý trường hợp key đã tồn tại. Kiểm chứng cách repository/template được cấu hình trên phiên bản cụ thể; khi cần kiểm soát insert KV tường minh có thể dùng API phù hợp của template/SDK.

## 7. Khi nào @PersistenceCreator thực sự cần thiết?

### 7.1. Nhiều constructor phục vụ hai mục đích

Một lớp thường cần constructor **ngắn** cho nghiệp vụ và constructor **đầy đủ** cho persistence. Không nên để framework đoán.

~~~java
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;

@Document
public class Customer {
    @Id
    private final String id;
    private final String fullName;
    private final boolean active;

    // Constructor nghiệp vụ.
    public Customer(String id, String fullName) {
        this(id, fullName, true);
    }

    // Constructor được Spring Data sử dụng để khôi phục dữ liệu.
    @PersistenceCreator
    public Customer(String id, String fullName, boolean active) {
        if (id == null || id.isBlank() ||
                fullName == null || fullName.isBlank()) {
            throw new IllegalArgumentException("Dữ liệu Customer không hợp lệ");
        }
        this.id = id;
        this.fullName = fullName;
        this.active = active;
    }

    public String getId() { return id; }
    public String getFullName() { return fullName; }
    public boolean isActive() { return active; }
}
~~~

Không có `@PersistenceCreator`, việc bổ sung constructor rỗng hoặc nhiều overload có thể khiến quá trình materialize chọn đường khác với ý định. Nếu dùng `@PersistenceCreator`, hãy giữ đúng **một đường được đánh dấu**.

### 7.2. Dùng static factory để không cần constructor overload

Một thiết kế khác dễ quản lý hơn là chỉ có một constructor đầy đủ, còn các biến thể nghiệp vụ là static factory:

~~~java
@Document
public class Coupon {
    @Id private final String id;
    private final String code;
    private final boolean enabled;

    public Coupon(String id, String code, boolean enabled) {
        this.id = id;
        this.code = code;
        this.enabled = enabled;
    }

    public static Coupon create(String code) {
        return new Coupon("coupon::" + code, code, true);
    }
}
~~~

Spring Data có một constructor để materialize, còn ứng dụng gọi `Coupon.create(...)` khi tạo mới. Cách này tránh phải đánh dấu `@PersistenceCreator` chỉ để phân biệt nhiều constructor.

### 7.3. @PersistenceCreator trên static factory method

Spring Data có thể sử dụng **static factory method được gắn `@PersistenceCreator`**. Ví dụ:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.couchbase.core.mapping.Document;

@Document
public class Warehouse {
    @Id
    private final String id;
    private final String region;

    private Warehouse(String id, String region) {
        this.id = id;
        this.region = region;
    }

    @PersistenceCreator
    public static Warehouse fromStoredState(String id, String region) {
        return new Warehouse(id, region);
    }

    public static Warehouse create(String code, String region) {
        return new Warehouse("warehouse::" + code, region);
    }
}
~~~

Điểm quan trọng là **tham số của factory dành cho persistence** vẫn phải tương ứng với dữ liệu ánh xạ, chứ không phải factory nghiệp vụ bất kỳ. Không đặt một static factory cần thời gian hiện tại, yêu cầu mạng, hoặc tạo ID mới làm persistence creator; đọc document cũ sẽ làm thay đổi trạng thái ngoài ý muốn.

## 8. Record, class final và bất biến thực sự

`record` rút gọn constructor và value semantics:

~~~java
public record GeoPoint(double latitude, double longitude) {
    public GeoPoint {
        if (!Double.isFinite(latitude) || !Double.isFinite(longitude)
                || latitude < -90 || latitude > 90
                || longitude < -180 || longitude > 180) {
            throw new IllegalArgumentException("Tọa độ không hợp lệ");
        }
    }
}
~~~

Với value object lồng trong entity, record thường rõ ràng. Dùng record làm **root entity** cũng có thể phù hợp vì Spring Data chọn canonical constructor; tuy nhiên, root có `@Id`, `@Version`, ID/metadata do store quản lý, và nhu cầu thay đổi trạng thái phải được kiểm chứng với converter/repository phiên bản thật. Nếu record chứa `List` hoặc `Map`, cần **defensive copy** để tránh dữ liệu bên trong bị thay đổi ngoài ý muốn.

Bất biến **không đồng nghĩa** với mọi field đều có `final`:

~~~java
private final List<OrderLine> lines;
~~~

Nếu constructor chỉ gán `this.lines = lines`, caller vẫn giữ reference tới một `ArrayList` rồi có thể thêm phần tử sau khi entity đã được tạo. Cách làm an toàn hơn:

~~~java
this.lines = List.copyOf(lines);
~~~

Nhưng nếu `OrderLine` là class mutable, nội dung phần tử vẫn có thể đổi; hãy dùng record hoặc class con bất biến và bảo vệ vòng đời aggregate.

## 9. Constructor với dữ liệu thiếu và schema thay đổi

Couchbase có schema linh hoạt. Một document cũ có thể **không có field** mới được thêm vào class Java.

Ví dụ phiên bản 1:

~~~json
{
  "display_name": "Cà phê 250 g",
  "price_vnd": 150000
}
~~~

Phiên bản 2 thêm:

~~~java
@Field
private final String currency;
~~~

Nếu persistence constructor yêu cầu `currency` và kiểm tra `currency != null`, việc đọc document cũ có thể thất bại. Nếu `currency` là primitive hoặc dùng logic mặc định không rõ ràng, ứng dụng có thể âm thầm materialize sai.

**Quy trình an toàn khi bổ sung field bắt buộc:**

1. Thống kê document đang thiếu field hoặc có `NULL`/giá trị sai kiểu.
2. Quy định default nghiệp vụ có căn cứ (ví dụ nếu mọi giá cũ chắc chắn là VND mới mặc định `"VND"`).
3. Chọn **migration dữ liệu** trước khi triển khai constructor mới, hoặc thực hiện giai đoạn reader tương thích thông qua converter/constructor có xử lý dữ liệu cũ.
4. Cập nhật code ghi dữ liệu mới để luôn có field.
5. Kiểm chứng readback, search query, export và rollback với document đại diện cho các phiên bản cũ.

Nếu cho phép một giá trị cũ bị thiếu một cách hợp lệ, thể hiện nó bằng wrapper/optional semantics ở miền ứng dụng, không tự giả định rằng mọi field vắng mặt đều bằng `null` có thể bỏ qua.

### 9.1. Constructor dùng giá trị mặc định: điều nên tránh

~~~java
// Lỗi thiết kế: cứ đọc lại document là tính lại createdAt.
public Order(String id, String status) {
    this.id = id;
    this.status = status;
    this.createdAt = java.time.Instant.now();
}
~~~

Thời điểm tạo đơn là thông tin lịch sử. Nếu constructor persistence tự sinh lại, mỗi lần đọc dữ liệu cũ có thể có `createdAt` mới, khiến báo cáo và trạng thái nghiệp vụ sai. Hãy:

- Cho `createdAt` vào constructor đầy đủ và ánh xạ dữ liệu đã lưu.
- Dùng static factory nghiệp vụ `create(...)` để đặt thời gian **khi tạo document mới**.
- Dùng migration tường minh cho document thiếu `createdAt`, không mặc định thời gian hiện tại lúc đọc.

Nguyên tắc này còn áp dụng cho ID, trạng thái mặc định, tổng tiền và các giá trị đã được chốt: **materialization phải khôi phục trạng thái, không tự thực thi một giao dịch nghiệp vụ mới**.

### 9.2. @Transient và giá trị dẫn xuất

Một thuộc tính `@Transient` không được Spring Data lấy từ JSON. Dù constructor có nhận nó, giá trị đến từ persistence có thể là null/mặc định. Tránh đưa field transient bắt buộc vào persistence constructor nếu không có logic xử lý riêng.

~~~java
@Transient
private String displayLabelCache;
~~~

Nên tính `displayLabelCache` từ `displayName` và `priceVnd` khi cần, hoặc dựng trong phương thức thuần. Không nhầm `org.springframework.data.annotation.Transient` với từ khóa Java `transient` hay `@JsonIgnore` của Jackson: các cơ chế đó thuộc những ngữ cảnh serialization khác nhau.

## 10. Generated ID, @Version và wither trong đối tượng bất biến

Entity bất biến tạo trước `@Id` ở factory là cách đơn giản. Nhưng có hệ thống cần **ID do cơ chế persistence tạo**. Khi đó field `final` không thể được cập nhật bằng setter thông thường.

Spring Data Commons hỗ trợ một số cách materialize/poplulate giá trị immutable:

- Constructor đầy đủ nhận cả ID được tạo;
- Phương thức dạng **`withId(...)`** tạo bản sao với ID mới;
- Cơ chế property population tạo bản sao qua persistence constructor khi phù hợp.

Ví dụ mô hình `withId`:

~~~java
@Document
public class Ticket {
    @Id
    private final String id;

    private final String title;

    public Ticket(String id, String title) {
        this.id = id;
        this.title = title;
    }

    public Ticket withId(String newId) {
        return new Ticket(newId, title);
    }

    public String getId() { return id; }
    public String getTitle() { return title; }
}
~~~

Đây là **cơ chế tạo bản sao**, không tự là chiến lược sinh ID. Nếu muốn Spring Data Couchbase sinh key, phải cấu hình `@GeneratedValue` theo API của Spring Data Couchbase hoặc tạo khóa ở service. Tránh suy từ tên field `id` rằng framework tự phát sinh key.

Tương tự, `@Version Long` là nơi nhận CAS; khi entity bất biến, constructor đầy đủ cần xử lý version do store quản lý. Trong ví dụ Product ở trên, các phương thức `rename` và `changePrice` giữ CAS cũ để kiểm tra optimistic locking khi lưu, và code gọi **phải giữ instance sau save** để cập nhật tiếp.

**Không sửa CAS bằng tay** nhằm vượt qua lỗi conflict. Đọc lại document, xác minh quy tắc và thực hiện cập nhật hợp lệ trên phiên bản mới.

## 11. Hiệu năng và giới hạn kỹ thuật của cách tạo instance

Theo hướng dẫn Spring Data, **constructor-only materialization** có thể giảm công đoạn gán property so với khởi tạo rỗng rồi thiết lập từng thuộc tính. Spring Data còn có cơ chế sinh instantiator/property accessor để hạn chế chi phí reflection khi class thỏa điều kiện phù hợp.

Những yếu tố có thể khiến framework phải dùng đường reflection hoặc hạn chế tối ưu hóa:

- Class là **non-static inner class** và giữ reference ngầm tới instance ngoài.
- Constructor persistence là private hoặc class không phù hợp với generated instantiator.
- Kiểu/cấu trúc và access modifier không thỏa điều kiện sử dụng generated property accessor.
- Môi trường Java module/JPMS không cho phép quyền truy cập reflection cần thiết.
- Constructor không cung cấp tên tham số hoặc có kiểu dữ liệu không chuyển được từ JSON.

Đây là các tiêu chí để **kiểm chứng**, không phải lý do đổi public API hoặc tắt encapsulation một cách tùy tiện. Đường reflection fallback trong nhiều trường hợp vẫn hoạt động; quan trọng nhất là tính đúng đắn của mapping và khả năng tương thích dữ liệu. Nếu cần tối ưu, đo độ trễ và CPU bằng workload thực thay vì coi việc có `final` luôn làm hệ thống nhanh hơn.

### Khi nào nên chọn mutable POJO?

| Hoàn cảnh | Gợi ý |
| --- | --- |
| Aggregate có bất biến phức tạp và ít setter hợp lệ | Ưu tiên immutable entity + domain methods tạo bản sao |
| Value object nhỏ như địa chỉ, kích thước, tiền | Record/immutable class |
| Dự án cũ có nhiều converter/constructor phản chiếu theo quy ước | Có thể giữ mutable POJO để tương thích, rồi chuyển từng bước |
| Field bắt buộc thay đổi thường xuyên do import/migration | Chọn schema tương thích và converter rõ ràng trước khi khóa chặt constructor |
| Document rất lớn, nhiều writer cập nhật một field con | Đánh giá ranh giới aggregate, CAS và sub-document; immutable Java không tự giải quyết hot document |

## 12. CouchbaseTemplate, SQL++, transaction và reactive có thay đổi constructor không?

`CouchbaseTemplate` và repository đều đi qua cơ chế mapping của Spring Data khi thao tác với entity:

~~~java
import org.springframework.data.couchbase.core.CouchbaseTemplate;

public Product loadProduct(CouchbaseTemplate template, String id) {
    return template.findById(Product.class).one(id);
}
~~~

Biết document key thì đường KV thường phù hợp; không cần secondary index để đọc một document theo ID. Khi truy vấn theo `display_name` hoặc thuộc tính khác, SQL++ cùng index thích hợp được sử dụng, nhưng kết quả phải chứa **metadata/field đủ để mapping entity**.

Ví dụ projection dùng cho màn hình danh sách:

~~~sql
SELECT META(p).id AS documentKey,
       p.display_name AS displayName,
       p.price_vnd AS priceVnd
FROM `shop`.`catalog`.`products` AS p
WHERE p.price_vnd > 100000
ORDER BY p.price_vnd ASC
LIMIT 20;
~~~

Đây là **projection**, không phải payload đủ để materialize `Product` ở ví dụ trên vì còn thiếu Packaging, tags, CAS/type metadata và tên alias phù hợp. Dùng DTO/projection cho màn hình danh sách; nếu muốn dựng entity đầy đủ bằng repository query tùy chỉnh, phải tuân theo yêu cầu ánh xạ của Spring Data.

- **CAS:** thuộc metadata document và được ánh xạ vào `@Version`; giữ phiên bản đúng trong immutable instance.
- **TTL:** áp dụng cho toàn document, không thay đổi việc chọn constructor. Nếu document hết hạn, `findById` không có dữ liệu để materialize.
- **Transaction:** phối hợp nhiều document nếu nghiệp vụ yêu cầu; constructor không làm hai lần `save` tự thành giao dịch nguyên tử.
- **Reactive repository/template:** sử dụng I/O không chặn, nhưng vẫn phải materialize entity theo constructor/converter và vẫn cần xử lý optimistic locking.
- **Bucket/scope/collection:** phải chỉ đến đúng nơi lưu; constructor không giúp tìm document ở collection khác.

Đừng gắn side effect vào persistence constructor với suy nghĩ rằng nó chỉ chạy khi tạo bản ghi mới. Mỗi lần đọc, query hoặc chuyển đổi dữ liệu đều có thể gọi constructor đó; side effect gây lỗi lặp và làm kết quả truy vấn không thuần.

## 13. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân khả dĩ | Cách khắc phục |
| --- | --- | --- |
| Spring Data không chọn constructor dự định | Nhiều constructor không có `@PersistenceCreator` hoặc có constructor rỗng | Đánh dấu đúng constructor, hoặc dùng một all-args constructor và static factories |
| Đối số constructor không được nạp | Thiếu `-parameters`/metadata tên hoặc tên không khớp property | Kiểm tra compiler, `@ConstructorProperties`, tên property Java |
| JSON có `display_name` nhưng Java nhận null | Mapping `@Field` không khớp JSON, hoặc dữ liệu cũ chưa migrate | Đối chiếu body và annotation; migration có kiểm chứng |
| Read document cũ ném `IllegalArgumentException` | Constructor mới yêu cầu field trước đây không có | Di trú dữ liệu, reader tương thích hoặc default có căn cứ |
| Mỗi lần đọc `createdAt` lại thay đổi | Constructor persistence gọi `Instant.now()` | Giữ thời gian trong JSON và tạo mới chỉ qua factory nghiệp vụ |
| Đã gọi `rename` nhưng save không đổi tên | Entity bất biến trả instance mới bị bỏ qua | Dùng kết quả `current.rename(...)` và `save(...)` |
| List `final` nhưng bên ngoài vẫn sửa được | Chỉ final reference, không defensive copy | Dùng `List.copyOf` và phần tử bất biến |
| Tải entity cũ rồi cập nhật bị xung đột | `@Version` phát hiện CAS đã thay đổi | Đọc lại, kiểm tra lại nghiệp vụ, retry có giới hạn |
| Đọc record hoặc nested class lỗi | Constructor/record mapping, converter hoặc non-static inner class | Dùng top-level hoặc static nested, kiểm thử round-trip |
| `findById` trả rỗng dù code constructor đúng | Sai document key hoặc bucket/scope/collection | Kiểm tra keyspace, ID thực tế và quyền truy cập |
| Query projection không dựng được entity | Thiếu field cần thiết cho constructor hoặc metadata | Dùng DTO/projection hoặc SELECT phù hợp với mapper |
| Generated ID không có trên instance cũ | Entity bất biến cần instance mới sau khi lưu/sinh ID | Nhận kết quả trả về, dùng constructor hoặc wither phù hợp |
| `@Transient` luôn null sau read | Transient không tham gia persistence | Tính lại hoặc nạp từ ngữ cảnh request, không xem là field lưu trữ |

## 14. Bài thực hành: đơn hàng bất biến có CAS

Thiết kế `Order` tại `shop.sales.orders` với các yêu cầu:

- Document key `order::125`, tổng tiền VND, trạng thái `DRAFT` hoặc `CONFIRMED`.
- Danh sách tối đa 50 dòng hàng, mỗi dòng có `sku`, `unitPriceVnd`, `quantity`.
- Constructor persistence khôi phục được **mọi trạng thái** kể cả `CONFIRMED`; factory nghiệp vụ tạo đơn mới với danh sách rỗng.
- Khi thêm dòng, trả một **Order mới**; tổng tiền phải phản ánh đúng danh sách.
- Dùng `@Version` để tránh ghi đè một Order do người khác vừa sửa.

### Lời giải tham khảo

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.PersistenceCreator;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
public final class Order {
    @Id
    private final String id;

    @Version
    private final Long version;

    @Field
    private final String status;

    @Field("total_amount_vnd")
    private final long totalAmountVnd;

    @Field
    private final List<OrderLine> lines;

    @PersistenceCreator
    public Order(
            String id, Long version, String status,
            long totalAmountVnd, List<OrderLine> lines) {
        if (id == null || id.isBlank() ||
                (!"DRAFT".equals(status) && !"CONFIRMED".equals(status)) ||
                totalAmountVnd < 0 || lines == null || lines.size() > 50) {
            throw new IllegalArgumentException("Trạng thái Order không hợp lệ");
        }
        this.id = id;
        this.version = version;
        this.status = status;
        this.totalAmountVnd = totalAmountVnd;
        this.lines = List.copyOf(lines);
    }

    public static Order draft(String id) {
        return new Order(id, null, "DRAFT", 0, List.of());
    }

    public Order addLine(OrderLine line) {
        if (!"DRAFT".equals(status) || line == null || lines.size() == 50) {
            throw new IllegalStateException("Không thể thêm dòng");
        }
        long nextTotal = Math.addExact(
            totalAmountVnd,
            Math.multiplyExact(line.unitPriceVnd(), line.quantity())
        );
        var nextLines = new ArrayList<>(lines);
        nextLines.add(line);
        return new Order(id, version, status, nextTotal, nextLines);
    }

    public String getId() { return id; }
    public Long getVersion() { return version; }
    public String getStatus() { return status; }
    public long getTotalAmountVnd() { return totalAmountVnd; }
    public List<OrderLine> getLines() { return lines; }
}

// Đặt OrderLine trong tệp riêng (hoặc static nested type).
public record OrderLine(String sku, long unitPriceVnd, int quantity) {
    public OrderLine {
        if (sku == null || sku.isBlank() ||
                unitPriceVnd < 0 || quantity <= 0) {
            throw new IllegalArgumentException("Dòng hàng không hợp lệ");
        }
    }
}
~~~

Đây là ví dụ tối giản. Trong dự án thật, bổ sung `@Scope("sales")`/`@Collection("orders")` nếu dùng collection này, kiểm tra tổng tiền ngay khi materialize (không chỉ khi thêm dòng), cùng quy tắc thuế/giảm giá/currency. `Math.addExact`/`multiplyExact` giúp phát hiện tràn số nguyên; trong thanh toán phức tạp cần kiểu tiền và quy tắc chính xác riêng.

Với `OrderRepository extends CouchbaseRepository<Order, String>`:

~~~java
Order order = Order.draft("order::125")
    .addLine(new OrderLine("coffee250", 150000, 2));

Order saved = repository.save(order);
Order reloaded = repository.findById(saved.getId()).orElseThrow();

Order revised = reloaded.addLine(
    new OrderLine("cup01", 50000, 1)
);
Order updated = repository.save(revised);
~~~

Mỗi bước dùng **instance mới**, đặc biệt sau `save` để tránh sử dụng CAS cũ.

### Tự kiểm tra

1. **Entity chỉ có một constructor đầy đủ có cần constructor rỗng không?** Không, nếu Spring Data giải quyết được tham số.
2. **Vì sao constructor tham số `displayName` dù JSON dùng `display_name`?** Đối số gắn với property Java; `@Field` xử lý tên lưu trữ.
3. **Khi nào `@PersistenceCreator` hữu ích nhất?** Khi có nhiều constructor hoặc một factory được chọn riêng cho persistence.
4. **Vì sao `record` phù hợp với value object?** Có canonical constructor và state bất biến ở mức component, nhưng collection bên trong vẫn cần defensive copy.
5. **Gọi `product.rename("A")` rồi bỏ kết quả có cập nhật object cũ không?** Không.
6. **`@Version Long` có phải schema version không?** Không; nó biểu diễn CAS để kiểm tra optimistic locking.
7. **Nếu document cũ thiếu `currency` nhưng constructor mới bắt buộc non-null, chuyện gì có thể xảy ra?** Lỗi materialization; cần migration hoặc đọc tương thích.
8. **Có nên phát sinh ID mới trong constructor persistence mỗi lần đọc?** Không. ID hiện có phải được khôi phục, factory mới được tạo key khi tạo entity mới.
9. **Dùng reactive repository có thay đổi constructor được chọn không?** Không; mapping vẫn tuân theo quy tắc entity.
10. **Có cần secondary index để `findById("order::125")` không?** Không, đây là truy cập KV theo key.

## 15. Checklist triển khai

- [ ] Chọn rõ class root (`@Document`) và các value object lồng nhau.
- [ ] Kiểm tra số lượng constructor; dùng `@PersistenceCreator` đúng nơi hoặc chỉ giữ một all-args constructor.
- [ ] Bảo đảm tên tham số constructor có metadata (`-parameters`/`@ConstructorProperties`) và tương ứng với property Java.
- [ ] Khi có `@Field("...")`, đối chiếu tên JSON với property Java và tài liệu dữ liệu cũ.
- [ ] Khôi phục ID, CAS, thời gian tạo và trạng thái từ dữ liệu đã lưu; để factory nghiệp vụ quyết định giá trị cho entity mới.
- [ ] Dùng `final`, defensive copy và immutable value object khi muốn bất biến thực sự.
- [ ] Mọi thao tác thay đổi trên entity bất biến trả instance mới, và service sử dụng kết quả sau `save`.
- [ ] Kiểm thử khi constructor gặp document thiếu field, sai kiểu, null và schema version cũ.
- [ ] Có xử lý `OptimisticLockingFailureException` và giới hạn retry khi cập nhật đồng thời.
- [ ] Chọn repository, template, SQL++ và reactive theo workload; mỗi đường phải materialize entity nhất quán.
- [ ] Kiểm tra đủ keyspace bucket/scope/collection, type metadata và index khi truy vấn ngoài ID.
- [ ] Chạy kiểm thử **ghi thật–đọc thật** cho POJO, constructor có annotation, record và collection bất biến.

## Tài liệu tham khảo chính thức

- [Spring Data Couchbase — Modeling Entities](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): chọn constructor, `@PersistenceCreator`, bất biến, property population và mapping Couchbase.
- [Spring Data Commons — Object Mapping Fundamentals](https://docs.spring.io/spring-data/commons/reference/object-mapping.html): constructor resolution, record, wither, metadata tham số và điều kiện tối ưu hóa.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): truy cập entity theo key và query.
- [Spring Data Couchbase — Auto-generating Keys](https://docs.spring.io/spring-data/couchbase/reference/couchbase/autokeygeneration.html): cách sinh ID cho entity.
- [Spring Data Couchbase — Collections](https://docs.spring.io/spring-data/couchbase/reference/couchbase/collections.html): scope/collection mapping.
- [Spring Data Couchbase — Transactions](https://docs.spring.io/spring-data/couchbase/reference/couchbase/transactions.html): phối hợp nhiều document và yêu cầu nhất quán.

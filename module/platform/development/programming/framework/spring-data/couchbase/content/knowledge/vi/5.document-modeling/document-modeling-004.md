# Đối tượng lồng nhau, danh sách, tập hợp và ánh xạ trong Spring Data Couchbase

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Biểu diễn **đối tượng Java lồng nhau** thành JSON object và phân biệt chúng với document Couchbase độc lập.
2. Ánh xạ `List<T>`, `Set<T>` và `Map<String, V>` vào các cấu trúc JSON phù hợp, hiểu điểm khác nhau về thứ tự, tính duy nhất và khóa.
3. Xây dựng entity `@Document` có value object, danh sách phần tử con, tập hợp nhãn và map thuộc tính mở rộng.
4. Đọc/ghi cấu trúc lồng nhau bằng repository hoặc `CouchbaseTemplate`; truy vấn trường con và mảng bằng SQL++.
5. Xử lý dữ liệu khuyết thiếu, kiểu không tương thích, đồng thời ghi, tăng trưởng document và yêu cầu lập chỉ mục.

Trong phần **Mô hình tài liệu** của module **SPRING_DATA_COUCHBASE**, document mapping kết nối lớp Java với JSON trong Couchbase. Khả năng lưu đối tượng lồng nhau và collection giúp giảm số lượt đọc, nhưng cần được đặt trong thiết kế aggregate và mẫu truy cập dữ liệu; repository, template, SQL++, CAS, TTL, giao dịch và reactive API chỉ phát huy tác dụng khi cấu trúc document đáp ứng nhu cầu đọc/ghi thật.

## 1. Bốn cấu trúc Java và cách nhìn trong JSON

Couchbase lưu JSON, không lưu nguyên đồ thị đối tượng Java trong bộ nhớ. JSON có object, array, string, number, boolean và null, nhưng không có kiểu `Set` hay khái niệm Java generic ở mức lưu trữ. Spring Data Couchbase cung cấp converter để chuyển dữ liệu qua lại.

| Mô hình Java | Biểu diễn JSON thường dùng | Đặc tính cần giữ |
| --- | --- | --- |
| `Address address` | Object lồng `"address": { ... }` | Đối tượng con cùng vòng đời với document gốc |
| `List<OrderLine> items` | Mảng các object `"items": [ { ... } ]` | **Có thứ tự**, cho phép trùng phần tử |
| `Set<String> tags` | Mảng chuỗi `"tags": ["sale", "coffee"]` | **Không trùng** trong Java; JSON array không tự bảo vệ tính duy nhất |
| `Map<String, String> attributes` | Object `"attributes": {"origin":"VN"}` | Key động dạng chuỗi, mỗi key một giá trị |

~~~mermaid
flowchart LR
    A["Java Product @Document"] --> C["Couchbase document"]
    A --> B["Dimensions<br/>value object"]
    A --> L["List&lt;PriceTier&gt;"]
    A --> S["Set&lt;String&gt;"]
    A --> M["Map&lt;String,String&gt;"]
    B -.->|object JSON| C
    L -.->|array JSON| C
    S -.->|array JSON| C
    M -.->|object JSON| C
~~~

Với một document gốc, các giá trị lồng nhau được ghi trong **cùng body** và nhận một **document key/CAS/expiry** ở cấp root. Việc lồng `Address`, `PriceTier` hoặc `Map` không tự tạo thêm document trong collection. **Chỉ khi chủ động tạo entity có `@Id` riêng và lưu riêng**, chúng mới là các document độc lập.

## 2. Khi nào nên nhúng đối tượng vào cùng document?

Một đối tượng con phù hợp để nhúng khi nó thường được đọc cùng root, được quản lý qua root, kích thước có giới hạn và quy tắc nghiệp vụ yêu cầu cập nhật thống nhất.

Ví dụ một `Product` có thông tin đóng gói, tập nhãn, các bậc giá số lượng và thông số mô tả:

- **Dimensions:** chiều rộng/cao/sâu của chính sản phẩm; đọc cùng Product.
- **List<PriceTier>:** vài bậc giá đã biết với thứ tự có ý nghĩa cho UI/logic.
- **Set<String>:** nhãn phân loại không muốn trùng trong Java.
- **Map<String, String>:** ít thuộc tính tùy biến như `origin`, `roast`, `material`.

Ngược lại, hàng triệu bình luận, lịch sử click, sự kiện kho hoặc đơn hàng độc lập **không nên nhúng không giới hạn** vào Product. Các thực thể có vòng đời riêng, quyền cập nhật riêng hoặc mức tranh chấp ghi lớn thường cần document khác và tham chiếu qua key.

**Phân biệt hai ranh giới:** aggregate là đơn vị đảm bảo bất biến nghiệp vụ; document là đơn vị lưu trữ và thao tác nguyên tử. Thiết kế tốt thường khiến một aggregate nhỏ nằm trong một document, nhưng hai khái niệm này không đồng nghĩa trong mọi hệ thống.

## 3. Ví dụ đầy đủ: Product chứa object, List, Set và Map

Giả sử có bucket `shop`, scope `catalog`, collection `products`. Bucket được cấu hình qua kết nối ứng dụng; annotation `@Scope` và `@Collection` gắn entity với nơi lưu mặc định.

### 3.1. Root entity Product.java

~~~java
package com.example.shop.catalog;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

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

    @Field("display_name")
    private String displayName;

    @Field
    private Dimensions dimensions;

    @Field("price_tiers")
    private List<PriceTier> priceTiers = new ArrayList<>();

    @Field
    private Set<String> tags = new LinkedHashSet<>();

    @Field
    private Map<String, String> attributes = new LinkedHashMap<>();

    @Version
    private Long version;

    protected Product() {
        // Constructor cho cơ chế materialize của Spring Data.
    }

    public Product(String sku, String displayName, Dimensions dimensions) {
        if (sku == null || !sku.matches("[a-z0-9-]+")) {
            throw new IllegalArgumentException("SKU không hợp lệ");
        }
        if (displayName == null || displayName.isBlank() || dimensions == null) {
            throw new IllegalArgumentException("Thông tin sản phẩm chưa đầy đủ");
        }
        this.id = "product::" + sku;
        this.displayName = displayName;
        this.dimensions = dimensions;
    }

    public void addPriceTier(PriceTier tier) {
        if (tier == null || priceTiers.size() >= 20) {
            throw new IllegalArgumentException("Bậc giá không hợp lệ hoặc quá giới hạn");
        }
        boolean exists = priceTiers.stream()
            .anyMatch(t -> t.getMinQuantity() == tier.getMinQuantity());
        if (exists) {
            throw new IllegalArgumentException("Trùng ngưỡng số lượng");
        }
        priceTiers.add(tier);
        priceTiers.sort(Comparator.comparingInt(PriceTier::getMinQuantity));
    }

    public void addTag(String tag) {
        if (tag == null || !tag.matches("[a-z0-9-]+")) {
            throw new IllegalArgumentException("Tag không hợp lệ");
        }
        tags.add(tag);  // Set giữ mỗi nhãn tối đa một lần.
    }

    public void setAttribute(String key, String value) {
        if (key == null || !key.matches("[a-z][a-z0-9_]*")
                || value == null || value.length() > 200) {
            throw new IllegalArgumentException("Attribute không hợp lệ");
        }
        if (!attributes.containsKey(key) && attributes.size() >= 30) {
            throw new IllegalArgumentException("Quá nhiều thuộc tính mở rộng");
        }
        attributes.put(key, value);
    }

    public String getId() { return id; }
    public String getDisplayName() { return displayName; }
    public Dimensions getDimensions() { return dimensions; }
    public List<PriceTier> getPriceTiers() { return List.copyOf(priceTiers); }
    public Set<String> getTags() { return Set.copyOf(tags); }
    public Map<String, String> getAttributes() { return Map.copyOf(attributes); }
}
~~~

Các giới hạn 20 bậc giá, 30 thuộc tính và 200 ký tự trong ví dụ là **quy tắc minh họa**, cần điều chỉnh theo workload thật. Không có `Repository` riêng cho Dimensions hay PriceTier: mọi thay đổi của chúng thuộc thao tác trên Product.

### 3.2. Value object Dimensions.java

~~~java
package com.example.shop.catalog;

import org.springframework.data.couchbase.core.mapping.Field;

public class Dimensions {

    @Field("width_mm")
    private int widthMm;

    @Field("height_mm")
    private int heightMm;

    @Field("depth_mm")
    private int depthMm;

    protected Dimensions() {}

    public Dimensions(int widthMm, int heightMm, int depthMm) {
        if (widthMm <= 0 || heightMm <= 0 || depthMm <= 0) {
            throw new IllegalArgumentException("Kích thước phải dương");
        }
        this.widthMm = widthMm;
        this.heightMm = heightMm;
        this.depthMm = depthMm;
    }

    public int getWidthMm() { return widthMm; }
    public int getHeightMm() { return heightMm; }
    public int getDepthMm() { return depthMm; }
}
~~~

Dimensions là POJO được nhúng, **không cần** `@Document` hay `@Id`. Cơ chế mapping vẫn có thể ánh xạ `@Field` ở lớp con. Với các value object bất biến thực sự, có thể dùng constructor phù hợp hoặc Java record; cần thử round-trip với phiên bản Spring Data Couchbase đang dùng.

### 3.3. Phần tử danh sách PriceTier.java

~~~java
package com.example.shop.catalog;

import org.springframework.data.couchbase.core.mapping.Field;

public class PriceTier {

    @Field("min_qty")
    private int minQuantity;

    @Field("unit_price_vnd")
    private long unitPriceVnd;

    protected PriceTier() {}

    public PriceTier(int minQuantity, long unitPriceVnd) {
        if (minQuantity <= 0 || unitPriceVnd < 0) {
            throw new IllegalArgumentException("Ngưỡng hoặc giá không hợp lệ");
        }
        this.minQuantity = minQuantity;
        this.unitPriceVnd = unitPriceVnd;
    }

    public int getMinQuantity() { return minQuantity; }
    public long getUnitPriceVnd() { return unitPriceVnd; }
}
~~~

### 3.4. Tạo đối tượng và hình dạng document

~~~java
Product product = new Product(
    "coffee250",
    "Cà phê hạt 250 g",
    new Dimensions(90, 160, 55)
);
product.addPriceTier(new PriceTier(1, 150000));
product.addPriceTier(new PriceTier(10, 138000));
product.addTag("coffee");
product.addTag("organic");
product.addTag("coffee"); // Không tạo thêm bản sao.
product.setAttribute("origin", "VN");
product.setAttribute("roast", "medium");
~~~

Sau khi được repository lưu, JSON body tương ứng có thể là:

~~~text
Bucket:      shop
Scope:       catalog
Collection:  products
Document ID: product::coffee250
~~~

~~~json
{
  "_class": "com.example.shop.catalog.Product",
  "display_name": "Cà phê hạt 250 g",
  "dimensions": {
    "width_mm": 90,
    "height_mm": 160,
    "depth_mm": 55
  },
  "price_tiers": [
    {"min_qty": 1, "unit_price_vnd": 150000},
    {"min_qty": 10, "unit_price_vnd": 138000}
  ],
  "tags": ["coffee", "organic"],
  "attributes": {
    "origin": "VN",
    "roast": "medium"
  }
}
~~~

Đây là **cấu trúc JSON minh họa** theo cách map thông thường; `_class` có thể xuất hiện tùy cấu hình type mapper. Document key `product::coffee250` và CAS `version` không phải các field nghiệp vụ trong JSON body. Thứ tự hai phần tử `tags` trên minh họa lần ghi này, **không phải bảo đảm thứ tự của `Set`** khi hệ thống chuyển đổi, đọc lại và sử dụng các triển khai Set khác nhau.

## 4. Đối tượng lồng nhau: object cùng document

Khai báo:

~~~java
@Field
private Dimensions dimensions;
~~~

Thông thường tạo ra:

~~~json
{
  "dimensions": {
    "width_mm": 90,
    "height_mm": 160,
    "depth_mm": 55
  }
}
~~~

Tên field ở mọi cấp tuân theo mapping. Vì vậy trong SQL++ bạn tham chiếu `dimensions.width_mm`, không dùng trực tiếp tên Java `widthMm` nếu đã gắn `@Field("width_mm")`.

### Object lồng nhau không phải document có key riêng

- `Product.id` là key của root document.
- `dimensions` là một object JSON trong body và không có CAS/TTL riêng.
- Thay đổi Dimensions rồi gọi `save(product)` tác động lên document Product.
- Không thể gọi `findById` riêng cho một Dimensions không được lưu thành entity độc lập.

Nếu muốn đọc một Dimensions mà không tải Product hoặc nếu nhiều Product chia sẻ một thực thể có vòng đời riêng, phải cân nhắc tách sang document khác với key và cơ chế truy cập riêng; không thể đạt điều đó chỉ bằng cách thêm `@Document` vào lớp con mà không thiết kế cách lưu và tham chiếu.

### Constructor, record và lớp nested

Spring Data cần có cách khởi tạo và nạp các thuộc tính khi đọc dữ liệu: constructor không tham số, constructor được chọn bởi cơ chế persistence hoặc Java record với canonical constructor phù hợp. Tránh lớp **inner không static** vì nó giữ tham chiếu ngầm đến instance lớp ngoài; dùng class top-level hoặc `static class` cho value object. Nếu dùng `record Dimensions(...)`, kiểm chứng tên property, converter và cách xử lý null khi đọc tài liệu cũ.

## 5. List: duy trì thứ tự và cho phép lặp

`List<PriceTier>` ánh xạ tự nhiên thành mảng JSON. Mảng JSON có thứ tự, nên đây là lựa chọn tốt khi vị trí/bậc ưu tiên là một phần của ý nghĩa nghiệp vụ. Spring Data có thể khôi phục phần tử với kiểu được khai báo `PriceTier`.

~~~java
@Field("price_tiers")
private List<PriceTier> priceTiers = new ArrayList<>();
~~~

| Tính chất | List trong Java | JSON array |
| --- | --- | --- |
| Thứ tự | Có, theo index | Có, theo vị trí |
| Trùng lặp | Cho phép | Cho phép |
| Truy cập phần tử | `list.get(0)` | `price_tiers[0]` |
| Kiểu phần tử | Generic `PriceTier` | JSON không mang generic Java |
| Số phần tử | Phụ thuộc bộ nhớ/quy tắc ứng dụng | Phụ thuộc dung lượng document và giới hạn hệ thống |

Ví dụ `List<String>` thành `["coffee", "tea"]`, `List<Integer>` thành `[1, 2]`, và `List<PriceTier>` thành `[{"min_qty": 1, ...}]`. Với `List<List<String>>` hoặc nhiều mức lồng nhau, JSON có thể mô tả tương ứng nhưng việc ánh xạ kiểu phức tạp cần được thử nghiệm.

**Lưu ý khi cập nhật danh sách:** nếu nhiều client cùng tải document, thêm phần tử và `save`, thao tác sau có thể ghi đè trạng thái trước nếu không quản lý xung đột. `@Version` cho root giúp kiểm tra CAS; khi có xung đột, đọc lại và đánh giá lại quy tắc trước khi thử ghi.

Đừng dùng một mảng tăng mãi cho comment, event hay lịch sử thay đổi chỉ vì `List` được mapping tiện. Mỗi lần đọc toàn bộ document sẽ mang cả mảng; mutation/retry và chỉ mục trở nên tốn kém theo kích thước.

## 6. Set: tính duy nhất thuộc Java, không thuộc JSON array

`Set<String>` dùng khi một nhãn chỉ được xuất hiện một lần trong mô hình nghiệp vụ:

~~~java
@Field
private Set<String> tags = new LinkedHashSet<>();
~~~

~~~java
tags.add("coffee");
tags.add("organic");
tags.add("coffee"); // Trả false, Set vẫn chỉ có hai phần tử.
~~~

JSON chỉ có array, nên dữ liệu thường được lưu như `["coffee", "organic"]`. Khi làm việc với Set:

1. **Không dựa vào thứ tự:** `HashSet` không có thứ tự được đảm bảo; `LinkedHashSet` giữ thứ tự chèn trong bộ nhớ, nhưng việc round-trip qua converter không nên được xem là hợp đồng duy trì thứ tự giao diện. Nếu cần thứ tự ổn định, dùng `List` và tự ràng buộc duy nhất.
2. **Tính duy nhất theo `equals`/`hashCode`:** `Set<String>` ổn khi phân biệt chuỗi; với `Set<Tag>` cần định nghĩa phép so sánh phù hợp hoặc dùng loại giá trị bất biến.
3. **JSON không tự từ chối giá trị trùng:** dữ liệu viết qua SDK khác/SQL++ có thể chứa `["coffee","coffee"]`. Khi đọc lại thành Set, phần trùng có thể bị loại theo converter; không nên trông chờ bảo toàn chính xác mảng đầu vào.
4. **Thử nghiệm mapping thực tế:** các bản Spring Data/SDK và converter tùy biến có thể có khác biệt trong cách khởi tạo collection. Viết round-trip test cho `Set` thay vì dựa vào suy đoán về class triển khai trả về.

Ví dụ một Set chứa `ProductOption` mutable dễ có lỗi nếu thuộc tính dùng trong `hashCode()` bị sửa sau khi thêm vào Set. Nên dùng value object bất biến hoặc key chuỗi ổn định.

## 7. Map: object JSON có các key động

`Map<String, String>` phù hợp khi tên thuộc tính không cố định, nhưng giá trị cùng một kiểu và số mục có giới hạn:

~~~java
@Field
private Map<String, String> attributes = new LinkedHashMap<>();
~~~

~~~json
{
  "attributes": {
    "origin": "VN",
    "roast": "medium",
    "packaging": "paper"
  }
}
~~~

Khi mapping, mỗi entry thành một cặp tên–giá trị trong JSON object. **Key JSON là chuỗi**; vì vậy `Map<String, V>` là lựa chọn rõ ràng. Không mặc định `Map<Integer, V>` hay map có key là object tùy ý sẽ được chuyển qua lại như mong muốn; các trường hợp đó cần quy tắc chuyển đổi có kiểm chứng.

### Map của giá trị lồng nhau

Bạn có thể mô hình hóa:

~~~java
@Field("warehouses")
private Map<String, WarehouseInfo> warehouses;
~~~

~~~json
{
  "warehouses": {
    "hn": {"zone": "north", "priority": 1},
    "hcm": {"zone": "south", "priority": 2}
  }
}
~~~

Đây vẫn là **một** document; `WarehouseInfo` là object con, và `hn`/`hcm` chỉ là các key bên trong map. Nếu số lượng kho, trạng thái tồn kho hoặc tốc độ thay đổi lớn, tốt hơn là tách dữ liệu kho thành aggregate/document riêng.

### Khi nào không nên dùng Map?

Không nên thay mọi field cố định bằng `Map<String, Object>` chỉ để có “schema linh hoạt”. Map kiểu quá rộng làm mất kiểm tra kiểu ở thời điểm biên dịch, gây khó khăn khi chuyển đổi số và object lồng nhau, dễ sinh biến thể dữ liệu khó truy vấn và khó tạo index. Với cấu trúc ổn định như `address.city`, dùng POJO có `@Field` rõ ràng thường tốt hơn.

Nếu key đến từ người dùng, cần giới hạn độ dài, ký tự, số mục và danh sách key được phép. Tên key động còn tác động đến SQL++: **giá trị** có thể parameterize an toàn, nhưng tên đường dẫn truy vấn phải được kiểm soát hoặc chọn từ whitelist; không nối thẳng input thành biểu thức SQL++.

## 8. Khác biệt giữa null, thiếu field và collection rỗng

Trong JSON và Java có nhiều trạng thái trông giống nhau nhưng mang ý nghĩa khác:

| JSON hiện có | Java có thể nhận | Ý nghĩa nên quyết định |
| --- | --- | --- |
| `"tags": []` | Set/List rỗng | Đã có trường, hiện không có phần tử |
| `"tags": null` | `null` hoặc giá trị qua converter | Có trường với JSON null |
| Không có `tags` | `null`, giá trị khởi tạo hoặc mặc định theo constructor/mapping | Trường chưa từng được ghi/đã bị loại |
| `"attributes": {}` | Map rỗng | Có object nhưng không có entry |
| `"dimensions": {}` | Object với nhiều field mặc định/khuyết | Có object nhưng thiếu dữ liệu bắt buộc |
| `"price_tiers": [{...}]` | Danh sách giá trị con | Phải kiểm tra hình dạng từng phần tử |

Theo quy tắc mapping mặc định, các thuộc tính Java `null` thường không được viết vào body; tài liệu từ SDK/SQL++ khác vẫn có thể chứa JSON null rõ ràng. Do đó, **MISSING** và **NULL** là hai trường hợp khác nhau trong SQL++, và code Java phải có chiến lược xử lý.

Một lỗi phổ biến: entity mới khởi tạo `tags = new LinkedHashSet<>()`, nhưng document cũ thiếu field `tags`; tùy constructor/mapping, đối tượng sau đọc có thể không rỗng như mong đợi. Cần xác nhận với integration test. Khi viết API nghiệp vụ, bạn có thể chuẩn hóa collection sau khi đọc hoặc dùng migration; đừng giả định rằng mọi dữ liệu cũ đều có schema của lớp Java hiện tại.

**Khuyến nghị về ràng buộc:** cấu trúc lồng nhau nên có invariant do aggregate root bảo vệ: `dimensions` luôn khác null, `priceTiers` không có trùng ngưỡng, `tags` tối đa N mục, và `attributes` chỉ chứa key/giá trị hợp lệ.

## 9. Dùng repository và template để đọc/ghi cấu trúc lồng nhau

Repository của root:

~~~java
package com.example.shop.catalog;

import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface ProductRepository extends CouchbaseRepository<Product, String> {
}
~~~

Service thao tác thông qua root:

~~~java
import org.springframework.stereotype.Service;

@Service
public class ProductCatalogService {
    private final ProductRepository products;

    public ProductCatalogService(ProductRepository products) {
        this.products = products;
    }

    public Product createExample() {
        Product product = new Product(
            "coffee250", "Cà phê hạt 250 g",
            new Dimensions(90, 160, 55)
        );
        product.addPriceTier(new PriceTier(1, 150000));
        product.addPriceTier(new PriceTier(10, 138000));
        product.addTag("coffee");
        product.addTag("organic");
        product.setAttribute("origin", "VN");
        return products.save(product);
    }

    public Product addTag(String productId, String tag) {
        Product product = products.findById(productId)
            .orElseThrow(() -> new IllegalArgumentException("Không có sản phẩm"));
        product.addTag(tag);
        return products.save(product);
    }
}
~~~

Với document key có sẵn, `findById` thường đi theo đường **Key-Value**, không cần secondary index trên `tags` hay `attributes`. Spring Data mapping làm nhiệm vụ chuyển `Product` thành body JSON và đọc trở lại khi bạn gọi repository.

`CouchbaseTemplate` dùng cùng hệ thống mapping:

~~~java
import org.springframework.data.couchbase.core.CouchbaseTemplate;

public Product find(CouchbaseTemplate template, String id) {
    return template.findById(Product.class).one(id);
}
~~~

Đây là thao tác đọc root theo key; không tạo repository cho object con. Với nhu cầu cập nhật một vài đường dẫn lồng nhau ở tần suất cao, SDK Couchbase có thao tác **sub-document**; nhưng cần cân nhắc CAS, mục tiêu bảo vệ invariant và cách đồng bộ với entity mapper. Việc gọi sub-document trực tiếp không tự động tuân theo các quy tắc nghiệp vụ trong phương thức `Product.addTag`.

**Lưu ý tạo mới:** `save` không mặc nhiên thay cho thao tác *insert only*. Nếu phải ngăn tạo trùng `productId`, dùng ngữ nghĩa insert có kiểm soát và xử lý key đã tồn tại. Nếu nhiều client cùng sửa các danh sách/map, dùng optimistic locking với `@Version` và xử lý xung đột.

## 10. Truy vấn trường lồng nhau, mảng và map bằng SQL++

Mẫu query cần dựa trên tên **field JSON thực tế**. Dữ liệu ví dụ đặt tại `shop.catalog.products`.

### 10.1. Lọc trường của object lồng

~~~sql
SELECT META(p).id AS productId, p.display_name, p.dimensions
FROM `shop`.`catalog`.`products` AS p
WHERE p.dimensions.width_mm >= 80
ORDER BY p.dimensions.width_mm;
~~~

Index ứng viên cho mẫu truy cập thường xuyên:

~~~sql
CREATE INDEX ix_products_width
ON `shop`.`catalog`.`products`(dimensions.width_mm);
~~~

Một index đơn không bảo đảm đáp ứng mọi bộ lọc/sắp xếp; cần kiểm tra `EXPLAIN` và workload thật.

### 10.2. Tìm Product có ít nhất một PriceTier thỏa điều kiện

~~~sql
SELECT META(p).id AS productId, p.display_name
FROM `shop`.`catalog`.`products` AS p
WHERE ANY tier IN p.price_tiers
      SATISFIES tier.min_qty >= 10 END;
~~~

Có thể tạo **array index** theo thuộc tính phần tử, thay vì index toàn bộ mảng:

~~~sql
CREATE INDEX ix_products_tier_min_qty
ON `shop`.`catalog`.`products`
(DISTINCT ARRAY tier.min_qty FOR tier IN price_tiers END);
~~~

Index dạng này chỉ là phương án khởi đầu; optimizer, kích thước dữ liệu và các điều kiện bổ sung quyết định việc index có giúp truy vấn hay không. Dùng `EXPLAIN`, so sánh latency và kiểm tra index được chọn.

### 10.3. Tìm theo tags

~~~sql
SELECT META(p).id AS productId, p.display_name
FROM `shop`.`catalog`.`products` AS p
WHERE ANY tag IN p.tags SATISFIES tag = "organic" END;
~~~

Khi truy vấn theo tag thường xuyên, cân nhắc một array index tương ứng:

~~~sql
CREATE INDEX ix_products_tags
ON `shop`.`catalog`.`products`
(DISTINCT ARRAY tag FOR tag IN tags END);
~~~

### 10.4. Tìm theo Map hoặc liệt kê key

Map `attributes` là JSON object, nên key đã biết có thể truy cập bằng đường dẫn hoặc cú pháp bracket:

~~~sql
SELECT META(p).id AS productId, p.attributes["origin"] AS origin
FROM `shop`.`catalog`.`products` AS p
WHERE p.attributes.origin = "VN";
~~~

Nếu `origin` là key được thống nhất trong schema và truy vấn thường xuyên, bạn có thể tạo index theo `attributes.origin`. Với key động, SQL++ có hàm `OBJECT_NAMES(p.attributes)` để liệt kê key; đừng cho phép người dùng tự ghép tên key vào query.

**Truy vấn không đồng nghĩa với materialize entity:** các câu `SELECT` chỉ trả projection và document ID hiển thị, không phải toàn bộ body dùng để dựng Product. Khi muốn trả về `Product` bằng repository/`CouchbaseTemplate`, truy vấn SQL++ tùy biến cần chọn đúng field và metadata cần thiết theo cơ chế mapping của Spring Data (bao gồm ID và type metadata khi được yêu cầu).

## 11. Đọc/ghi đồng thời, transaction, TTL và API reactive

| Vấn đề | Tác động lên cấu trúc lồng nhau | Cách xử lý phù hợp |
| --- | --- | --- |
| **CAS / `@Version`** | Hai thao tác sửa `tags`, `priceTiers`, `attributes` cùng ghi một document root | Giữ `@Version` trên root; xử lý `OptimisticLockingFailureException` bằng đọc–kiểm tra–ghi lại có giới hạn |
| **Atomicity** | Một lần mutation document cập nhật nhiều field lồng nhau | Bất biến trong document được commit nguyên tử theo một mutation |
| **Transaction** | Một nghiệp vụ phải đổi Product và aggregate Inventory độc lập | Cân nhắc transaction đa document hoặc workflow bù, theo yêu cầu nhất quán |
| **TTL** | Product root có expiry | TTL áp dụng cho **document**, không tự hết hạn riêng một item trong List/Map |
| **Reactive API** | Nhiều request đọc/ghi Product đồng thời | Reactive giúp xử lý I/O không chặn, không thay đổi hình dạng JSON hay tự giải quyết CAS |
| **Index/SQL++** | Lọc sâu vào mảng/map cần index thích hợp | Thiết kế chỉ mục theo truy vấn, kiểm tra độ tươi index và `EXPLAIN` |

Nếu `PriceTier` có quy tắc ràng buộc lẫn nhau, các phép thay đổi nên đi qua root Product. Nếu muốn các writer cập nhật từng tag mà không cần tải toàn bộ Product, một API sub-document có thể giảm dữ liệu truyền, nhưng phải bảo vệ đồng thời ghi và tránh phá bất biến khi nhiều phần khác của Product cũng được cập nhật.

**Đừng dùng một JSON document làm toàn bộ cơ sở dữ liệu.** Dù JSON cho phép nesting nhiều cấp, kích thước document, lượng đọc/ghi và xung đột CAS tăng cùng khối dữ liệu. Đặt giới hạn số phần tử và xác định phần nào phải tách theo vòng đời độc lập.

## 12. Dữ liệu lỗi, thay đổi schema và conversion

### 12.1. Thay đổi kiểu List/Set/Map sau khi đã có dữ liệu

Giả sử document cũ lưu:

~~~json
{
  "tags": "coffee"
}
~~~

Nhưng code mới mong `Set<String> tags` (JSON array). Mapping có thể thất bại hoặc tạo kết quả không như mong đợi; **không giả định** converter tự biến string thành tập hợp. Hãy chạy migration sang:

~~~json
{
  "tags": ["coffee"]
}
~~~

Tương tự, nếu `attributes` cũ là mảng `[{"key":"origin","value":"VN"}]`, đổi Java sang `Map<String,String>` không làm JSON cũ biến thành object. Cần đọc tương thích có kiểm soát hoặc di trú dữ liệu.

### 12.2. Trường số và độ chính xác

JSON number không gắn trực tiếp loại Java `int`, `long`, `BigDecimal` hay kiểu tiền tệ. Chọn kiểu theo miền nghiệp vụ; với tiền VND nguyên, ví dụ dùng `long`. Với kiểu thời gian, enum, decimal có yêu cầu chính xác, object đặc biệt hoặc converter tùy biến, hãy xác nhận biểu diễn JSON và kiểm thử đọc–ghi qua Spring Data phiên bản thực tế.

### 12.3. Custom converter

Spring Data Couchbase cho phép đăng ký `@WritingConverter` và `@ReadingConverter` cho kiểu không có biểu diễn JSON phù hợp. Converter viết nên tạo kiểu được mapping hiểu (giá trị cơ bản, map, list hoặc cấu trúc Couchbase tương thích), và converter đọc phải xử lý dữ liệu cũ một cách có chủ đích.

Không nên viết custom converter cho `List<String>` hay `Map<String,Integer>` cơ bản nếu mapping mặc định đã đáp ứng. Chỉ thêm converter khi có yêu cầu thực: wrapper giá trị, định dạng thời gian, mã hóa enum, hoặc tương thích schema.

### 12.4. Bài kiểm thử round-trip bắt buộc đối với cấu trúc phức tạp

Với mỗi entity mới, tạo một document mẫu trong môi trường kiểm thử, rồi:

1. Lưu Product với `dimensions`, `priceTiers`, `tags`, `attributes`.
2. Đọc lại bằng `findById` và so giá trị, kiểu, số phần tử, thứ tự của List và tính duy nhất của Set.
3. Kiểm tra JSON body thực tế (tên field, array/object, metadata) bằng Couchbase UI hoặc SDK.
4. Thử document cũ thiếu field, field rỗng, null và sai kiểu; xác định hành vi mong muốn.
5. Gửi hai thao tác cập nhật song song lên cùng Product; xác nhận CAS báo xung đột và code không mất dữ liệu.
6. Dùng `EXPLAIN` với các query trên mảng/map, đo hiệu năng và kiểm tra độ tươi index khi cần đọc ngay sau ghi.

Không cần tạo test mô phỏng chính mapper; bài kiểm thử có giá trị là **ghi thật–đọc thật** với Couchbase phiên bản dùng trong môi trường của bạn.

## 13. Các lỗi thiết kế phổ biến

| Dấu hiệu | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Một giá trị con không có document riêng | Đối tượng được nhúng dưới root | Chỉ tách thành document có `@Id` riêng nếu cần vòng đời độc lập |
| `Set<String>` đổi thứ tự sau khi đọc | Không có hợp đồng thứ tự ổn định của Set | Dùng List nếu UI/logic cần thứ tự |
| Hai đối tượng trong `Set<ValueObject>` vẫn trùng về nghiệp vụ | `equals`/`hashCode` không định nghĩa theo định danh giá trị | Dùng value object bất biến với equality phù hợp |
| `Map<Integer, V>` không round-trip như dự kiến | JSON object key là chuỗi | Dùng `Map<String,V>` hoặc converter có kiểm chứng |
| Map tồn tại hàng nghìn key động | Không giới hạn số entry và schema quá linh hoạt | Chuẩn hóa thành object có kiểu hoặc document con riêng |
| Query trả rỗng dù data có giá trị | Dùng `minQuantity` thay vì JSON `min_qty` | Truy vấn theo tên thực trong `@Field` |
| Thêm entry làm update ghi đè nhau | Hai writer lưu snapshot document root cũ | Dùng `@Version`/CAS và retry cả chu trình |
| Phần tử của List tự biến mất khi TTL hết hạn | TTL thực ra áp dụng cho cả root document | Đưa phần tử có thời hạn độc lập sang document riêng |
| Mapper lỗi khi đọc document cũ | Field đổi từ string sang array hoặc object | Di trú/đọc tương thích và kiểm thử round-trip |
| `Map<String,Object>` tạo dữ liệu khó kiểm soát | Thiếu hợp đồng kiểu và converter | Ưu tiên value object/DTO hoặc Map typed, giới hạn key |

## 14. Bài thực hành: thiết kế giỏ hàng

**Đề bài:** một giỏ hàng có `cartId`, địa chỉ giao hàng tạm, danh sách các dòng hàng, tập mã ưu đãi đã áp dụng và map tùy chọn `gift_message`, `delivery_note`. Hãy xác định cấu trúc Java và JSON, đồng thời chỉ ra đâu là root document.

**Gợi ý thiết kế:**

~~~java
@Document(expiry = 3600)
public class Cart {
    @Id
    private String id;

    @Field("delivery_address")
    private Address deliveryAddress;

    @Field
    private List<CartLine> lines;

    @Field("applied_codes")
    private Set<String> appliedCodes;

    @Field
    private Map<String, String> options;

    @Version
    private Long version;
}
~~~

Trong đó `Address` và `CartLine` là value object con (có constructor/mapping phù hợp), `Cart` là aggregate root với document key, CAS và TTL. Trường `lines` dùng List để giữ thứ tự thêm hàng; `appliedCodes` dùng Set để tránh áp cùng mã hai lần trong mô hình Java; `options` dùng Map vì tên tùy chọn thay đổi nhưng giá trị đều là chuỗi.

~~~json
{
  "delivery_address": {
    "city": "Hồ Chí Minh",
    "district": "Bình Thạnh"
  },
  "lines": [
    {"sku": "coffee250", "quantity": 2},
    {"sku": "cup01", "quantity": 1}
  ],
  "applied_codes": ["WELCOME10"],
  "options": {
    "gift_message": "Chúc mừng sinh nhật",
    "delivery_note": "Gọi trước khi giao"
  }
}
~~~

**Phân tích:** TTL 3.600 giây trong ví dụ là chính sách của **toàn bộ Cart**. Nếu chỉ mã ưu đãi có hạn 15 phút trong khi Cart phải sống lâu hơn, cần lưu thời gian hiệu lực và kiểm tra nghiệp vụ hoặc tách dữ liệu cần expiry độc lập; thêm `@Document(expiry=900)` lên lớp giá trị con không làm một phần mảng tự hết hạn.

### Câu hỏi tự kiểm tra

1. **`List` và `Set` khi lưu có cùng dạng JSON không?** Thường đều là array; sự khác nhau về trùng lặp và thứ tự nằm ở mô hình Java.
2. **`Map<String,String>` chuyển sang JSON gì?** Một object có key chuỗi và value chuỗi.
3. **`Address` nhúng có cần `@Id`?** Không, trừ khi nó được thiết kế và lưu thành entity độc lập.
4. **Để tìm giỏ có dòng `sku="coffee250"`, dùng SQL++ gì?** `ANY x IN lines SATISFIES x.sku = "coffee250" END`; cần đánh giá array index nếu truy vấn thường xuyên.
5. **`@Version` đặt ở Cart hay CartLine?** Ở root Cart khi một document chứa toàn bộ danh sách và CAS áp dụng ở cấp document.
6. **`Map<String,Object>` có là lựa chọn tốt cho mọi schema mở không?** Không; đánh đổi type safety, migration, index và tính ổn định dữ liệu.
7. **Dùng reactive repository có đổi biểu diễn JSON không?** Không; nó đổi giao diện xử lý bất đồng bộ/I-O, không thay đổi bản chất object/list/set/map mapping.

## 15. Checklist áp dụng

- [ ] Chọn root và giới hạn phần dữ liệu con theo bất biến, vòng đời và mẫu truy cập.
- [ ] Dùng POJO/record lồng nhau cho value object; xác minh constructor và converter.
- [ ] Dùng List khi cần thứ tự hoặc cho phép lặp; Set khi muốn duy nhất và không phụ thuộc thứ tự.
- [ ] Chỉ dùng Map với key chuỗi/giới hạn rõ; ưu tiên kiểu value cụ thể thay vì Object chung chung.
- [ ] Đặt `@Field("...")` nhất quán và viết SQL++ theo tên field JSON.
- [ ] Xác định cách xử lý null, missing, collection rỗng và dữ liệu cũ.
- [ ] Dùng `@Version`/CAS và đánh giá cạnh tranh ghi nếu nhiều writer sửa cùng root.
- [ ] Kiểm tra hiệu năng, kích thước document, số phần tử, array index và TTL.
- [ ] Chạy round-trip integration test cho List, Set, Map và object lồng nhau trên Couchbase thật.

## Tài liệu tham khảo chính thức

- [Spring Data Couchbase — Modeling Entities](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): Map/List, object composition, converter, `@Document`, `@Field` và CAS.
- [Couchbase — The Couchbase Data Model](https://docs.couchbase.com/server/current/learn/data/document-data-model.html): lựa chọn nhúng hay tham chiếu và ảnh hưởng tới mẫu truy cập.
- [Couchbase — SQL++ Array Indexing](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/indexing-arrays.html): `ANY ... SATISFIES` và index cho mảng.
- [Couchbase — SQL++ Object Functions](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/objectfun.html): thao tác với key và value của object JSON.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): cách truy cập theo ID và truy vấn SQL++.

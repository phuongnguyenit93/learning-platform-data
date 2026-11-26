# Java record và giới hạn cần kiểm tra khi entity có metadata thay đổi trong Spring Data Couchbase

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao `record` phù hợp với **value object** và có thể dùng làm **root entity Couchbase** trong những điều kiện nhất định.
2. Ánh xạ record qua `@Document`, `@Id`, `@Field`, `@Version` và canonical constructor của Java.
3. Phân biệt dữ liệu **bất biến trong object Java** với metadata **có thể đổi sau khi ghi** của Couchbase, đặc biệt là CAS và expiry.
4. Thiết kế thao tác thay đổi bằng cách **tạo record mới**, giữ đúng document key và phiên bản CAS đã đọc; nhận lại instance sau `save`.
5. Xác định những điểm cần kiểm chứng khi dùng generated ID, version, collection lồng nhau, schema evolution, SQL++ projection và API reactive.
6. Viết kiểm thử đọc–ghi và ghi đồng thời để quyết định **record**, immutable class hay mutable entity là lựa chọn đúng.

Đây là bài thuộc chương **Mô hình tài liệu** của module **SPRING_DATA_COUCHBASE**. Module dùng Spring Data để ánh xạ Java document, thao tác bằng repository/`CouchbaseTemplate`, truy vấn SQL++ và vận hành Couchbase theo bucket/scope/collection, index, TTL, CAS, transaction hoặc reactive API. Record không thay đổi các khả năng này; nó thay đổi **cách object Java được tạo và cách ứng dụng nhận trạng thái mới**.

## 1. Bản chất của record: bất biến tham chiếu, không phải bất biến toàn hệ thống

Java `record` là một loại class đặc biệt dùng biểu diễn dữ liệu. Các component sinh ra field `private final`, accessor, canonical constructor cùng `equals`, `hashCode` và `toString`.

Ví dụ:

~~~java
public record ProductSummary(String sku, String displayName, long priceVnd) {
    public ProductSummary {
        if (sku == null || sku.isBlank()
                || displayName == null || displayName.isBlank()
                || priceVnd < 0) {
            throw new IllegalArgumentException("ProductSummary không hợp lệ");
        }
    }
}
~~~

Bạn đọc dữ liệu bằng `summary.sku()` chứ không mặc nhiên có `summary.getSku()`. Không có setter vì các component không thể được gán lại sau khi khởi tạo.

Nhưng điều đó **chỉ bảo đảm bất biến nông** (*shallow immutability*):

~~~java
public record Basket(List<String> skus) {}

List<String> source = new ArrayList<>(List.of("coffee250"));
Basket basket = new Basket(source);

source.add("cup01");       // Có thể làm thay đổi nội dung basket.skus().
basket.skus().add("tea01"); // Cũng có thể thay đổi danh sách nếu là ArrayList.
~~~

Với collection mutable, record chỉ giữ một reference bất biến. Để phòng ngừa sửa qua reference, dùng defensive copy ở compact constructor:

~~~java
public record Basket(List<String> skus) {
    public Basket {
        skus = List.copyOf(Objects.requireNonNull(skus, "skus"));
    }
}
~~~

`List.copyOf` tạo danh sách không thể thêm/xóa phần tử và từ chối phần tử `null`. Nếu phần tử là object mutable, cần chọn value object bất biến hoặc sao chép sâu khi thật sự cần.

**Giới hạn quan trọng:** record không khiến JSON trong Couchbase bất biến. Một process khác vẫn có thể cập nhật document qua SDK/SQL++; CAS thay đổi dù record Java của bạn không hề bị sửa. Đó là lý do phải tách biệt **object state** và **persistence metadata**.

## 2. Phân biệt record, entity và metadata Couchbase

Một document Couchbase có:

- **Document key:** định danh document trong một collection, dùng cho các lệnh KV.
- **JSON body:** các field miền nghiệp vụ; có thể được ánh xạ thành record components.
- **CAS:** số phiên bản opaque do Couchbase quản lý, thay đổi khi document bị mutation; Spring Data có thể ánh xạ qua `@Version`.
- **Expiry / TTL:** thời điểm hết hạn hoặc chính sách thời hạn của document; không phải Java record component mặc định.
- **Thông tin kiểu ánh xạ:** ví dụ `_class` trong JSON body nếu Spring Data type mapper ghi nó; khác document key/CAS.

~~~mermaid
flowchart LR
    R["Java record Product\nid, cas, name, price"] -->|"save"| K["Couchbase document"]
    K --> M["Metadata: key / CAS / expiry"]
    K --> B["JSON body: display_name / price_vnd / _class"]
    K -->|"read + mapping"| R2["Record Product mới"]
    R2 -->|"rename() tạo bản sao"| R3["Record mới, giữ key/CAS"]
    R3 -->|"save, CAS kiểm tra"| K
~~~

Đối với entity record, annotation quyết định component nào đi đến đâu:

| Record component | Annotation | Nguồn/đích |
| --- | --- | --- |
| `String id` | `@Id` của Spring Data | Document key (metadata), **không tự là field JSON** |
| `Long cas` | `@Version` | CAS (metadata), dùng cho optimistic locking |
| `String displayName` | `@Field("display_name")` | Field JSON `display_name` |
| `long priceVnd` | `@Field("price_vnd")` | Field JSON `price_vnd` |
| `List<String> tags` | `@Field` | Mảng JSON `tags` |
| `Instant createdAt` | `@Field("created_at")` | Field JSON với biểu diễn do converter quyết định |

**Không sử dụng `@Version` như schema version.** Một trường JSON `schema_version` mô tả phiên bản cấu trúc dữ liệu và do ứng dụng quản lý; CAS mô tả phiên bản ghi vật lý của *một document*. Một record cùng key được lưu lại sẽ có CAS mới ngay cả khi schema không đổi.

## 3. Khi nào record là lựa chọn tốt?

| Đối tượng | Có nên dùng record? | Lý do và ràng buộc |
| --- | --- | --- |
| Value object nhúng: `Dimensions`, `Money`, `AddressSnapshot` | **Rất phù hợp** | Giá trị nhỏ, khởi tạo đầy đủ, ít metadata do store thay đổi |
| DTO/API response, SQL++ projection | **Phù hợp** | Truyền dữ liệu đọc, không cần lifecycle `@Id`/`@Version` |
| Root entity có ID tạo trước, update theo copy-on-write | **Có thể** | Phải kiểm tra cách mapper nạp/trả CAS và ghi entity bất biến |
| Root entity cần auto-generated key sau save | **Cần thử kỹ** | `id` final; framework phải tạo instance mới hoặc dùng cơ chế immutable property population |
| Aggregate có nhiều thao tác cập nhật trạng thái | **Cân nhắc** | Mỗi thay đổi tạo record mới; có thể phù hợp, nhưng dễ làm mất CAS nếu copy sai |
| Đối tượng kế thừa base class có state | **Không phù hợp trực tiếp** | Record là final và không extend class nghiệp vụ khác |
| Entity có field mutable và cần sửa tại chỗ bằng setter | **Không phù hợp với lối viết đó** | Không có setters; phải đổi thiết kế cập nhật |

Không có quy tắc “cứ Spring Data là phải dùng POJO mutable” hay “mọi entity nên đổi thành record”. Đối với root có metadata **thay đổi khi save** và các ràng buộc vận hành đặc biệt, hãy đánh giá phiên bản Spring Data Couchbase hiện dùng qua integration test, không suy từ khả năng compile.

## 4. Ví dụ root entity record: ID ứng dụng tạo sẵn, CAS do Couchbase cấp

Giả sử sản phẩm nằm trong bucket `shop`, scope `catalog`, collection `products`. Bucket được cấu hình tại kết nối; scope/collection được khai báo trên entity.

### 4.1. Product.java

~~~java
package com.example.shop.catalog;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("catalog")
@Collection("products")
public record Product(
    @Id String id,
    @Version Long cas,
    @Field("display_name") String displayName,
    @Field("price_vnd") long priceVnd,
    @Field List<String> tags,
    @Field("created_at") Instant createdAt
) {
    // Compact canonical constructor: chạy cả khi tạo mới lẫn khi đọc document.
    public Product {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("Document key không hợp lệ");
        }
        if (displayName == null || displayName.isBlank() || priceVnd < 0) {
            throw new IllegalArgumentException("Thông tin sản phẩm không hợp lệ");
        }
        Objects.requireNonNull(createdAt, "createdAt");
        tags = List.copyOf(Objects.requireNonNull(tags, "tags"));
    }

    // Factory NGHIỆP VỤ: chỉ dùng khi tạo product mới.
    public static Product create(
            String sku, String name, long priceVnd) {
        if (sku == null || !sku.matches("[a-z0-9-]+")) {
            throw new IllegalArgumentException("SKU không hợp lệ");
        }
        return new Product(
            "product::" + sku,
            null, // Chưa có CAS do Couchbase trả về.
            name,
            priceVnd,
            List.of(),
            Instant.now()
        );
    }

    public Product rename(String newName) {
        return new Product(id, cas, newName, priceVnd, tags, createdAt);
    }

    public Product changePrice(long newPriceVnd) {
        return new Product(id, cas, displayName, newPriceVnd, tags, createdAt);
    }

    public Product addTag(String tag) {
        if (tag == null || !tag.matches("[a-z0-9-]+")) {
            throw new IllegalArgumentException("Tag không hợp lệ");
        }
        if (tags.contains(tag)) {
            return this;
        }
        if (tags.size() >= 20) {
            throw new IllegalStateException("Quá nhiều tag");
        }
        var next = new ArrayList<>(tags);
        next.add(tag);
        return new Product(id, cas, displayName, priceVnd, next, createdAt);
    }
}
~~~

**Những quyết định quan trọng:**

1. `@Id` lấy **document key** từ `id`. Constructor không sinh ID khi đọc; factory tạo `product::` + SKU chỉ lúc tạo mới.
2. `@Version` đánh dấu **CAS**. Dùng `Long` để biểu diễn trạng thái chưa có phiên bản bằng `null`; không đặt giá trị CAS tùy ý.
3. `rename`, `changePrice` và `addTag` tạo bản sao **giữ nguyên `id` và `cas`** của snapshot đã đọc. Đổi `cas` bằng phép cộng hoặc tự lấy timestamp sẽ phá cơ chế optimistic locking.
4. `createdAt` có mặt trong canonical constructor. Không gọi `Instant.now()` mỗi lần materialize document cũ.
5. `tags = List.copyOf(tags)` tạo bản sao phòng ngừa mutation ngoài ý muốn. Các phần tử ở đây là `String` bất biến.
6. Constructor từ chối dữ liệu không hợp lệ; đây là lợi ích, nhưng cũng khiến việc đọc **document cũ thiếu field** có thể thất bại cho tới khi migration.

**Giới hạn cần xác minh:** cách Spring Data Couchbase sử dụng record component có `@Id`/`@Version`, khôi phục CAS và cấp bản sao với CAS mới sau ghi phụ thuộc tương thích của mapper với phiên bản framework đang chạy. Đoạn mã thể hiện một thiết kế cần kiểm thử tích hợp, không phải cam kết rằng mọi phiên bản Spring Data Couchbase đều hỗ trợ trọn vẹn lifecycle này.

### 4.2. Document và metadata sau khi lưu

Với `Product.create("coffee250", "Cà phê hạt 250 g", 150000)`, body JSON có thể có dạng:

~~~text
Bucket:        shop
Scope:         catalog
Collection:    products
Document key:  product::coffee250
CAS:           Couchbase cấp sau mutation
~~~

~~~json
{
  "_class": "com.example.shop.catalog.Product",
  "display_name": "Cà phê hạt 250 g",
  "price_vnd": 150000,
  "tags": [],
  "created_at": "2026-11-25T03:15:00Z"
}
~~~

`_class` là ví dụ về thông tin type mapper trong JSON; có thể khác theo cấu hình. `created_at` ở đây minh họa dạng ISO-8601; biểu diễn thời gian thực tế phải kiểm tra với converter được dùng. `id` và `cas` không xuất hiện trong body vì chúng thuộc document key và CAS metadata.

Dữ liệu sau khi đọc lại có thể được biểu diễn trong Java thành một **instance record mới**, với `id() = "product::coffee250"` và `cas()` mang giá trị CAS mà Spring Data chuyển về kiểu `Long`.

## 5. Canonical constructor: lợi thế và rủi ro khi materialize

Java record có **canonical constructor** tương ứng chính xác với các component. Spring Data Commons có quy tắc ưu tiên canonical constructor của record khi xác định đường khởi tạo persistence. Bạn không cần tự thêm constructor rỗng; record cũng không thể dùng kiểu setter-based population như POJO mutable.

Ví dụ:

~~~java
public record Dimensions(int widthMm, int heightMm, int depthMm) {
    public Dimensions {
        if (widthMm <= 0 || heightMm <= 0 || depthMm <= 0) {
            throw new IllegalArgumentException("Kích thước phải dương");
        }
    }
}
~~~

Khi JSON có đủ `widthMm`, `heightMm`, `depthMm`, mapper có thể dùng canonical constructor tạo object con. Nếu dữ liệu thiếu `heightMm`, constructor có thể nhận giá trị mặc định hoặc lỗi chuyển đổi theo mapper; những kiểm tra `> 0` trong ví dụ giúp phát hiện dữ liệu thiếu/sai thay vì tạo object có kích thước vô nghĩa.

### 5.1. @PersistenceCreator có cần trên record?

Không cần đánh dấu `@PersistenceCreator` cho canonical constructor chỉ để Spring Data nhận ra record thông thường. Khi thiết kế các constructor/factory phức tạp, Spring Data cũng có cơ chế `@PersistenceCreator`:

~~~java
import org.springframework.data.annotation.PersistenceCreator;
~~~

Nhưng đừng gắn annotation đó lên một factory **chỉ dành cho tạo mới**, ví dụ factory sinh ID ngẫu nhiên hoặc lấy thời gian hiện tại. Nếu persistence materialize bằng factory ấy, dữ liệu đọc từ Couchbase có thể bị sửa ý nghĩa.

Với root record, cách dễ dự đoán nhất thường là:

- Canonical constructor chứa đầy đủ **persistent components**.
- Static factory nghiệp vụ tạo object mới, bao gồm ID và timestamp ban đầu.
- Các phương thức thay đổi trả record mới, giữ metadata đã đọc.
- Query/projection có payload đủ để mapper dựng canonical constructor.

### 5.2. Tên Java và tên JSON

~~~java
public record ProductView(
    @Field("display_name") String displayName,
    @Field("price_vnd") long priceVnd
) {}
~~~

Constructor component dùng **tên Java** `displayName`, còn field lưu trữ trong Couchbase dùng `display_name`. Spring Data ánh xạ thông qua metadata `@Field`. Record giữ tên component trong metadata của Java; vẫn phải xác nhận cấu hình compiler/module access và converter thích hợp với môi trường thực.

`@Field` ở đây là annotation của `org.springframework.data.couchbase.core.mapping.Field`, không phải annotation của thư viện MongoDB/JPA. API Jackson dùng để tạo HTTP JSON có thể áp dụng quy tắc khác; response DTO không mặc nhiên giống JSON body của Couchbase.

## 6. Repository: save trả về trạng thái mới, record cũ không đổi

Định nghĩa repository cho root:

~~~java
package com.example.shop.catalog;

import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface ProductRepository extends CouchbaseRepository<Product, String> {
}
~~~

Service minh họa:

~~~java
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final ProductRepository products;

    public ProductService(ProductRepository products) {
        this.products = products;
    }

    public Product create(String sku, String name, long priceVnd) {
        Product newProduct = Product.create(sku, name, priceVnd);
        return products.save(newProduct);
    }

    public Product rename(String key, String newName) {
        Product current = products.findById(key)
            .orElseThrow(() -> new IllegalArgumentException("Không thấy Product"));

        Product next = current.rename(newName);
        return products.save(next);
    }
}
~~~

Không làm như sau:

~~~java
Product loaded = products.findById(key).orElseThrow();
loaded.rename("Tên mới");       // BỎ KẾT QUẢ: loaded không đổi.
products.save(loaded);          // Có thể ghi lại trạng thái cũ.
~~~

Cách đúng:

~~~java
Product loaded = products.findById(key).orElseThrow();
Product next = loaded.rename("Tên mới");
Product saved = products.save(next);
~~~

**Vì sao quan trọng?** CAS của Couchbase có thể đổi sau mỗi mutation, còn `cas` là một final record component. Framework không thể gọi `setCas(...)` trên instance cũ. Hãy kiểm tra **instance được trả về từ `save`** có metadata mới và liệu nó có cùng reference với instance truyền vào không; đừng dựa vào việc framework sửa record tại chỗ.

Trên một số đường ghi, giải pháp an toàn nhất khi cần chắc chắn CAS mới là **đọc lại document theo key**; phải đo overhead và xác minh cách repo/template phiên bản đang dùng trả metadata. Không bao giờ tự sinh một CAS mới trong Java.

### 6.1. Lifecycle các instance record

| Thời điểm | `id()` | `cas()` | Đối tượng Java |
| --- | --- | --- | --- |
| Factory tạo mới | `product::coffee250` | `null` | Record mới, chưa persist |
| Sau `save` thành công | Cùng key | CAS mới (cần xác minh trả về) | Có thể là instance mới |
| `findById` đọc lại | Cùng key | CAS thực tế của document | Record materialize mới |
| `rename` trên bản vừa đọc | Cùng key | Giữ CAS hiện tại | Bản sao mới, chưa ghi |
| `save` bản sao | Cùng key | Dùng CAS cũ để kiểm tra, Couchbase cấp CAS mới | Cần dùng kết quả/đọc lại |
| Writer khác sửa trước | Cùng key | CAS của bạn đã cũ | Có thể lỗi optimistic locking |

Đây là **đường đi logic cần kiểm chứng**, không phải chi tiết rằng `save` bắt buộc phải trả instance khác trên mọi phiên bản. Kết luận chắc chắn là **record cũ không thể bị thay đổi giá trị component tại chỗ**.

### 6.2. Không nhầm save với insert-only

`save` có ngữ nghĩa tạo/cập nhật tùy trạng thái entity và cơ chế persistence của phiên bản. Nếu yêu cầu “một SKU chỉ được tạo đúng một lần”, hãy dùng thao tác có ngữ nghĩa **insert-only** và xử lý key đã tồn tại. Với entity có `@Version Long cas`, việc `cas == null` có thể là dấu hiệu “chưa lưu”; đừng tự điền một CAS bất kỳ để ép framework nhận đó là update.

## 7. CAS / @Version: record không giải quyết ghi đồng thời

Giả sử hai request đọc cùng document ở CAS A:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant DB as Couchbase
    participant B as Request B
    A->>DB: get(product::coffee250)
    B->>DB: get(product::coffee250)
    DB-->>A: Product CAS=A
    DB-->>B: Product CAS=A
    A->>DB: save(rename, expected CAS=A)
    DB-->>A: Thành công, CAS=B
    B->>DB: save(changePrice, expected CAS=A)
    DB-->>B: CAS mismatch / conflict
~~~

Không có `@Version` hoặc cơ chế CAS phù hợp, một writer ghi snapshot cũ có thể **ghi đè thay đổi** của writer khác. Với `@Version`, Spring Data Couchbase có thể sử dụng CAS để thực hiện optimistic locking; khi xung đột, tầng ứng dụng xử lý `OptimisticLockingFailureException`.

Ví dụ mẫu xử lý **báo xung đột**:

~~~java
import org.springframework.dao.OptimisticLockingFailureException;

public Product renameSafely(String key, String name) {
    try {
        Product current = products.findById(key).orElseThrow();
        Product changed = current.rename(name);
        return products.save(changed);
    } catch (OptimisticLockingFailureException conflict) {
        throw new IllegalStateException(
            "Product đã được cập nhật bởi request khác", conflict
        );
    }
}
~~~

Nếu cần **retry**, phải đọc lại document, xây lại record, đánh giá lại điều kiện nghiệp vụ và chỉ thử trong số lần giới hạn. Không retry bằng cách gọi lại `save(staleRecord)` nhiều lần. Tránh chạy lặp side effect như gửi email, trừ tiền hoặc publish sự kiện nếu chưa có idempotency.

### 7.1. Vì sao equals/hashCode sinh tự động của record cần chú ý?

Record sinh `equals` và `hashCode` từ **toàn bộ components**, bao gồm `cas`, danh sách, giá và tên. Hai record có cùng document key nhưng CAS khác nhau có thể **không bằng nhau** theo `equals`.

~~~java
// Cùng id nhưng khác version hoặc displayName:
boolean sameIdentity = first.id().equals(second.id());
// sameIdentity có thể true trong khi first.equals(second) là false.
~~~

Bởi vậy:

- Đừng dùng `record.equals()` như phép kiểm tra **cùng entity identity** khi entity có metadata/trạng thái thay đổi.
- Tránh dùng record root làm **key của HashMap/HashSet có vòng đời qua nhiều lần save** nếu code dựa vào identity bằng document key.
- Khi đối chiếu entity sau cập nhật, kiểm tra `id()` cho định danh và so trạng thái/CAS một cách tường minh.

Đây không phải lỗi của record: đó là khác biệt giữa **value equality** và **entity identity**.

## 8. Generated ID và @Version là điểm cần kiểm chứng kỹ nhất

### 8.1. Nếu ID được tạo trước khi save

Cách ít phức tạp là ứng dụng tạo key ổn định trong factory:

~~~java
Product p = Product.create("coffee250", "Cà phê hạt", 150000);
// p.id() = "product::coffee250"; p.cas() = null
Product saved = repository.save(p);
~~~

Không cần đợi store gán một ID vào field final. `@Id` chỉ chọn component dùng làm document key, **không tự sinh** key nếu thiếu cơ chế rõ ràng.

### 8.2. Nếu dùng @GeneratedValue của Spring Data Couchbase

Spring Data Couchbase có annotation `@GeneratedValue` và các chiến lược tạo key. Với record root có `@Id String id` final, mapper có thể phải **tạo một record mới chứa ID đã sinh** hoặc sử dụng cơ chế immutable property population phù hợp. Không có setter để gán ID vào bản cũ.

Vì vậy trước khi dùng record cùng generated ID, cần xác minh:

1. Cơ chế tạo key trên **đúng phiên bản** Spring Data Couchbase.
2. Record dùng canonical constructor có thể nhận ID/CAS đã tạo hay không.
3. `save` trả lại đúng instance/giá trị ID đã sinh hay phải đọc lại.
4. `isNew` detection có phân biệt create/update đúng với `@Version` nullable.
5. Repository, template và reactive API có cùng kết quả với cấu hình đó không.

Nếu một tình huống không được framework hỗ trợ ổn định, đừng cố “lách” bằng reflection sửa `final`. Thay vào đó **tạo ID ở service trước khi xây record**, hoặc dùng immutable class có phương thức `withId`/`withVersion` và kiểm thử mapping, hoặc chuyển sang entity mutable có kiểm soát.

### 8.3. Với record, CAS cũng cần một bản sao mới

Ngay cả khi ID đã có từ đầu, `@Version Long cas` là metadata sẽ thay đổi. Record không thể cập nhật component `cas` tại chỗ. Muốn thực hiện nhiều lần cập nhật nối tiếp, service phải giữ record **được cập nhật CAS qua mapper** hoặc đọc lại từ store.

Không nên:

~~~java
// Sai: tự tăng CAS như version nghiệp vụ.
Product fakeNewVersion = new Product(
    old.id(), old.cas() + 1,
    old.displayName(), old.priceVnd(), old.tags(), old.createdAt()
);
~~~

CAS là opaque token do Couchbase quản lý, **không phải bộ đếm tăng 1** do ứng dụng tự ghi. Câu trên còn có thể ném lỗi khi `old.cas() == null`.

### 8.4. TTL là metadata không có trong record

Khi khai báo `@Document(expiry = 3600)` cho một entity được phép hết hạn, thời gian hết hạn áp dụng cho **document**, không cần field `expiry` trong JSON. Việc đưa một component `expiresAt` vào record có ý nghĩa **nghiệp vụ**, không tự áp TTL cho Couchbase trừ khi bạn cấu hình/áp dụng expiry tương ứng qua API.

Nếu TTL thay đổi khi ghi lại, record được materialize thường không chứa toàn bộ ngữ cảnh expiry nếu ứng dụng chỉ ánh xạ `@Id` và `@Version`. Những hệ thống cần giữ chính xác thời điểm hết hạn phải có chiến lược đọc/ghi expiry rõ ràng qua SDK/template và kiểm thử, không suy từ bất biến Java.

## 9. Value object record lồng nhau thường đơn giản hơn root record

Record phát huy ưu thế rõ nhất khi **không trực tiếp mang metadata do Couchbase thay đổi**:

~~~java
package com.example.shop.catalog;

import org.springframework.data.couchbase.core.mapping.Field;

public record Dimensions(
    @Field("width_mm") int widthMm,
    @Field("height_mm") int heightMm,
    @Field("depth_mm") int depthMm
) {
    public Dimensions {
        if (widthMm <= 0 || heightMm <= 0 || depthMm <= 0) {
            throw new IllegalArgumentException("Kích thước phải dương");
        }
    }
}
~~~

Trong entity:

~~~java
@Field
private Dimensions dimensions;
~~~

Body JSON có thể chứa:

~~~json
{
  "dimensions": {
    "width_mm": 90,
    "height_mm": 160,
    "depth_mm": 55
  }
}
~~~

`Dimensions` không phải root document, không cần `@Document`, `@Id` hay `@Version`. Nếu muốn thay `widthMm`, ứng dụng tạo `new Dimensions(...)` rồi ghi bản Product chứa value object mới. CAS vẫn thuộc root Product, không thuộc Dimensions.

### 9.1. List và Map trong record

Nếu record chứa `List<OrderLine>` hoặc `Map<String, String>`, phải phòng ngừa mutable reference:

~~~java
public record CartSnapshot(
    List<CartLine> lines,
    Map<String, String> notes
) {
    public CartSnapshot {
        lines = List.copyOf(Objects.requireNonNull(lines, "lines"));
        notes = Map.copyOf(Objects.requireNonNull(notes, "notes"));
    }
}

public record CartLine(String sku, int quantity) {
    public CartLine {
        if (sku == null || sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("CartLine không hợp lệ");
        }
    }
}
~~~

Đặt hai record `public` vào **hai tệp Java khác nhau** (hoặc dùng record lồng nhau phù hợp). `Map.copyOf` không bảo đảm thứ tự iteration; nếu thứ tự entry quan trọng cho UI, chọn biểu diễn có thứ tự rõ ràng như `List`.

Cấu trúc JSON vẫn là array/object như với POJO. Record không làm converter tự kiểm soát tính duy nhất của mọi phần tử hay áp TTL riêng lên item lồng nhau.

## 10. Schema evolution: constructor bất biến có thể từ chối dữ liệu cũ

Couchbase cho phép nhiều phiên bản JSON cùng tồn tại. Record là một kiểu cố định có canonical constructor với đúng số component; điều này làm những yêu cầu bắt buộc trở nên rõ ràng, nhưng cũng tạo **rủi ro materialization** khi schema thay đổi.

Ví dụ document cũ:

~~~json
{
  "display_name": "Cà phê hạt 250 g",
  "price_vnd": 150000,
  "created_at": "2026-11-20T01:00:00Z"
}
~~~

Record mới đòi `tags`:

~~~java
public Product {
    tags = List.copyOf(Objects.requireNonNull(tags, "tags"));
}
~~~

Nếu JSON cũ thiếu `tags`, mapper có thể đưa `null` vào constructor và ném lỗi. **Không nên gọi đó là lỗi Couchbase**; đó là xung đột giữa dữ liệu cũ và hợp đồng đối tượng mới.

Lựa chọn xử lý:

| Cách | Khi áp dụng | Điều cần thận trọng |
| --- | --- | --- |
| Migration JSON trước khi triển khai | Có thể chuyển dữ liệu theo lô và kiểm soát writer | Kiểm chứng số lượng/missing; không ghi đè dữ liệu mới |
| Canonical constructor có default hợp lệ | Trường mới thật sự là optional, mặc định có ý nghĩa | Phân biệt missing, JSON null và dữ liệu sai |
| Reading converter tương thích nhiều schema | Dữ liệu cũ nhiều biến thể cần chuẩn hóa khi đọc | Phải có test cho từng version và mapping metadata |
| DTO đọc cũ, chuyển sang miền mới | Cần decouple persistence schema và model bất biến | Có lớp chuyển đổi rõ ràng và kế hoạch loại schema cũ |

Ví dụ **chỉ khi quy tắc miền cho phép** mặc định danh sách rỗng:

~~~java
public Product {
    if (id == null || id.isBlank() || priceVnd < 0) {
        throw new IllegalArgumentException("Product không hợp lệ");
    }
    tags = tags == null ? List.of() : List.copyOf(tags);
    Objects.requireNonNull(createdAt, "createdAt");
}
~~~

Cẩn thận: `null` có thể đến từ JSON `null` **hoặc** field không tồn tại, tùy converter. Nếu hai trường hợp cần cách xử lý khác nhau, đừng ép cả hai thành list rỗng mà không phân biệt ở tầng dữ liệu.

### 10.1. Đổi tên field bằng @Field không tự migration

~~~java
@Field("display_name") String displayName
~~~

Không tự biến JSON cũ `"displayName": "..."` thành `"display_name": "..."`. Khi record mới yêu cầu non-null, một phép rename schema chưa di trú có thể gây lỗi đọc ngay lập tức. Phải chuẩn bị reader tương thích hoặc migration và kiểm tra SQL++/index theo tên field thật.

### 10.2. Primitive và boxed type

`long priceVnd` không biểu diễn được “chưa có giá” bằng `null`. Trong một số mapping, field số thiếu có thể dẫn đến lỗi hoặc giá trị mặc định `0`; nếu `0` là giá trị hợp lệ, lỗi dữ liệu có thể khó nhận biết.

Với trường optional, cân nhắc `Long`/kiểu miền có quy tắc rõ. Với trường bắt buộc, migration và validation phải xác nhận dữ liệu hiện hữu trước khi đổi constructor.

### 10.3. Đừng sinh lại thời điểm hoặc khóa khi đọc

Sai:

~~~java
public Product {
    id = id == null ? "product::" + UUID.randomUUID() : id;
    createdAt = Instant.now();
}
~~~

Canonical constructor chạy khi **đọc lại** document. Việc tính lại ID/thời gian tại đây có thể khiến object Java không còn phản ánh key và lịch sử thực tế của Couchbase.

Đúng: factory mới sinh key/createdAt, còn canonical constructor khôi phục những giá trị đã lưu. Nếu dữ liệu cũ thiếu `createdAt`, dùng migration có căn cứ, không mặc định bằng thời điểm đọc.

## 11. SQL++, repository projection và record DTO

Record rất tiện cho **projection đọc** vì không có vòng đời cập nhật metadata:

~~~java
public record ProductListItem(
    String documentKey,
    String displayName,
    long priceVnd
) {}
~~~

Một truy vấn SQL++ minh họa cho màn hình catalog:

~~~sql
SELECT META(p).id AS documentKey,
       p.display_name AS displayName,
       p.price_vnd AS priceVnd
FROM `shop`.`catalog`.`products` AS p
WHERE p.price_vnd > 100000
ORDER BY p.price_vnd ASC
LIMIT 20;
~~~

Đây là dữ liệu để ánh xạ **DTO/projection**, không phải một entity `Product` đầy đủ. Truy vấn thiếu `tags`, `created_at` và metadata CAS/type có thể làm materialization của record root thất bại hoặc tạo dữ liệu không đầy đủ. Khi dùng `@Query` trả entity, tuân thủ quy tắc chọn trường/metadata của Spring Data Couchbase, không chỉ lấy ba cột màn hình cần.

`findById("product::coffee250")` thường đi qua đường KV theo key và không cần secondary index. Truy vấn theo `display_name`/`price_vnd` dùng SQL++ và cần index theo workload. **Record không thay đổi lựa chọn KV so với SQL++**, chỉ thay đổi cách converter dựng kết quả.

Một DTO record dùng cho HTTP JSON với Jackson cũng **không mặc nhiên** giống document JSON do Spring Data Couchbase ghi. Dùng lớp phản hồi riêng khi cần kiểm soát field bảo mật, tên hiển thị và API contract.

## 12. Khi nào immutable class thay record sẽ phù hợp hơn?

Record ngắn gọn nhưng có giới hạn:

- **Không thể kế thừa class** chứa state/behavior; record là final.
- Không có field instance tùy ý ngoài record components; các thông tin persistence quan trọng phải được thể hiện trong component hoặc quản lý ở lớp khác.
- `equals/hashCode` theo toàn bộ state, đôi khi không phù hợp với entity identity chỉ dựa vào key.
- Không có setter; framework phải hỗ trợ tái tạo instance khi ID/CAS được cấp hoặc thay đổi.
- Schema thay đổi làm canonical constructor phải xử lý thêm component; dữ liệu cũ có thể không đáp ứng.
- Nested object vẫn cần defensive copy nếu chứa mutable elements.
- Một số cơ chế mapping/converter/version cụ thể có thể chưa được kiểm thử đầy đủ với record trong phiên bản đang dùng.

Một **immutable class thông thường** có thể cung cấp API `withId`, `withVersion`, constructor `@PersistenceCreator` tường minh hoặc `equals` dựa trên identity theo quy tắc miền. Nó cho phép điều khiển property population/lifecycle nhiều hơn:

~~~java
@Document
public final class ProductEntity {
    @Id
    private final String id;

    @Version
    private final Long version;

    private final String name;

    public ProductEntity(String id, Long version, String name) {
        this.id = id;
        this.version = version;
        this.name = name;
    }

    public ProductEntity withId(String newId) {
        return new ProductEntity(newId, version, name);
    }

    public ProductEntity withVersion(Long newVersion) {
        return new ProductEntity(id, newVersion, name);
    }
}
~~~

Các `with...` trên là **phương thức tạo bản sao theo thiết kế**, không phải bảo đảm rằng mọi bản Spring Data Couchbase sẽ tự gọi chúng. Cần kiểm tra tích hợp nếu framework dự kiến dùng cơ chế đó để gán ID/CAS.

Với entity mutable, có thể dùng field cập nhật nội bộ và bảo vệ invariant bằng phương thức miền. Chọn cách ít phức tạp nhất vẫn đáp ứng **tính đúng đắn của lifecycle**, không đổi record chỉ vì cú pháp ngắn.

## 13. Metadata thay đổi khác với chuyển trạng thái nghiệp vụ

Đây là điểm dễ lẫn nhất khi thiết kế entity bất biến:

| Loại thay đổi | Có phải ghi vào JSON body? | Cách tiếp cận |
| --- | --- | --- |
| `displayName` đổi | Có | Tạo record mới, giữ ID/CAS cũ, lưu dưới cùng key |
| `priceVnd` đổi | Có | Kiểm tra nghiệp vụ, copy-on-write, CAS |
| CAS đổi sau mutation | Không, là metadata | Nhận qua mapper/SDK, **không tự tính** |
| Expiry đổi | Metadata document | Cấu hình TTL/SDK/template phù hợp |
| Document key đổi | Không thể chỉ sửa field JSON | Tạo document key mới và xử lý tham chiếu/migration |
| `schema_version` tăng | Nếu dùng thì là field nghiệp vụ/format trong JSON | Nâng schema/migration có kiểm soát |
| `_class`/type alias thay | Type mapping trong JSON body | Cần tương thích đọc hoặc migration |
| Thêm field bắt buộc | JSON body mới | Chuyển dữ liệu cũ trước khi constructor mới từ chối |

**Ví dụ:** khi đổi `displayName`, record được tạo lại là chuyện Java. Nhưng CAS mới chỉ tồn tại sau ghi vào Couchbase; không đồng bộ CAS đúng thì lần cập nhật thứ hai có thể thất bại. Ngược lại, việc thêm `@Field("expiry") Instant expiresAt` chỉ tạo một trường JSON nghiệp vụ, không đồng nghĩa thiết lập TTL thật.

## 14. Kiểm thử tích hợp bắt buộc cho record root

Không nên chỉ viết unit test gọi `new Product(...)`. Mục tiêu là xác nhận **Spring Data Couchbase phiên bản dự án thực sự ánh xạ, lưu, đọc và cập nhật metadata đúng**.

### 14.1. Danh sách kiểm thử tối thiểu

| Kịch bản | Cách kiểm tra | Kết quả cần đạt |
| --- | --- | --- |
| Lưu Product mới | Factory `cas=null`, `repository.save` | Key đúng, JSON body đúng, không mất field |
| Đọc lại Product | `findById` | Constructor nhận ID và CAS, `tags` không null |
| Metadata sau save | So `saved.cas()` và record đọc lại | Không dựa vào record cũ; biết cách có CAS hiện hành |
| Rename/cập nhật giá | `saved.rename` rồi `save` | Cùng key, trạng thái mới, CAS thay đổi |
| Ghi đồng thời | Hai bản từ cùng CAS cùng save | Có cơ chế conflict theo CAS khi hỗ trợ `@Version` |
| Document cũ thiếu tags | Chèn JSON cũ vào collection thử nghiệm | Default/migration hoặc lỗi có chủ đích |
| Document cũ sai kiểu | `price_vnd` là string hoặc null | Lỗi rõ ràng, không âm thầm mất tiền |
| Record nested | Product có Dimensions hoặc List value records | Ghi–đọc đúng giá trị lồng nhau |
| Generated ID (nếu dùng) | Save record ID chưa gán | ID mới và CAS có thể truy xuất hợp lệ |
| TTL | Đặt expiry ngắn trên entity thử nghiệm | Document hết hạn theo chính sách, không phải một field |
| Reactive API (nếu dùng) | Save/get/update với reactive repository | Mapping và CAS tương đương đường blocking |

### 14.2. Pseudocode JUnit cho ghi–đọc và CAS

Giả sử ứng dụng đã có `ProductRepository`, cấu hình Couchbase test riêng và test fixture có ID duy nhất:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.dao.OptimisticLockingFailureException;

// Giả định: @SpringBootTest với Couchbase test đã kết nối,
// repo được inject và test fixture dùng key riêng biệt.
@Test
void productRecordRoundTripAndCas() {
    Product inserted = repository.save(
        Product.create("coffee-test-01", "Cà phê test", 150000)
    );

    Product loaded = repository.findById(inserted.id()).orElseThrow();

    assertEquals("Cà phê test", loaded.displayName());
    assertEquals(150000, loaded.priceVnd());
    assertEquals(List.of(), loaded.tags());
    assertNotNull(loaded.cas());

    Product copy1 = repository.findById(inserted.id()).orElseThrow();
    Product copy2 = repository.findById(inserted.id()).orElseThrow();

    Product updated = repository.save(copy1.rename("Cà phê mới"));
    assertEquals("Cà phê mới", updated.displayName());

    assertThrows(
        OptimisticLockingFailureException.class,
        () -> repository.save(copy2.changePrice(160000))
    );
}
~~~

Đây là **phác thảo kiểm thử tích hợp**, không phải test độc lập có thể chạy ngay khi thiếu test environment, import `List`, fixture cleanup và injection repository. Hãy dùng Testcontainers/môi trường Couchbase kiểm thử và database cô lập để tránh đụng dữ liệu thật. Nếu `save` không trả CAS phù hợp ở bản framework đang dùng, kiểm tra bằng lần đọc lại; đó là dấu hiệu cần điều chỉnh mô hình record/root, không nên giả vờ CAS đã tự có.

### 14.3. Kiểm tra JSON/metadata bằng SDK

Cùng một key có thể được đọc bằng Couchbase Java SDK để đối chiếu:

~~~java
var collection = cluster.bucket("shop")
    .scope("catalog")
    .collection("products");

var result = collection.get("product::coffee-test-01");
var body = result.contentAsObject();

System.out.println(body.getString("display_name"));
System.out.println(result.cas());
~~~

Giá trị `result.cas()` là metadata của document, còn `body.getString("display_name")` là field JSON. Document key được cung cấp bằng đối số `get(...)`, **không cần có field `id` trong body**.

So CAS đọc bằng SDK với CAS đi vào record `@Version` để xác định cơ chế mapping ở phiên bản đang dùng.

## 15. Các lỗi thường gặp và cách khắc phục

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Record compile nhưng `save`/read thất bại | Mapper/constructor/version không hỗ trợ tình huống cụ thể | Kiểm tra phiên bản, converter và integration test; cân nhắc immutable class |
| `cas()` luôn null sau save | Record cũ không thể mutate, mapper không trả instance có CAS | Dùng kết quả `save`, đọc lại, xác minh ánh xạ `@Version` |
| Save lần thứ hai bị conflict | Dùng record mang CAS cũ | Tải lại, copy trạng thái mới và xử lý concurrency |
| Rename không có hiệu lực | Bỏ kết quả trả từ `rename` | Lưu record mới thay vì record cũ |
| Giá trị tags bị đổi ngoài ý muốn | Chỉ `final` reference, không defensive copy | `List.copyOf`, dùng phần tử bất biến |
| Document cũ đọc lỗi ở compact constructor | Thiếu field `tags` hoặc `created_at` | Migration/schema compatibility |
| `@Version` bị dùng làm schema version | Nhầm CAS với field nghiệp vụ | Tách `schemaVersion` dạng field JSON |
| ID tự đổi khi đọc lại | Sinh ID trong canonical constructor | Chỉ sinh ở factory tạo mới |
| Test so hai record cùng key bị false | `equals` tính CAS và field khác | So `id()` để xác định entity identity |
| Lấy SQL++ projection để dựng Product root | Thiếu field/cas cần cho constructor | Dùng DTO record cho projection hoặc SELECT theo mapping |
| Thiếu dữ liệu record component mới | Schema đã đổi mà chưa migrate | Quy định default có căn cứ hoặc reading converter |
| Record cần setter cho ID do store sinh | Không có setter và không có cơ chế tạo bản sao phù hợp | Tạo ID trước, dùng immutable class/wither hoặc entity mutable |
| TTL hết hạn dù record không đổi | Expiry thuộc Couchbase metadata | Kiểm tra chính sách TTL, không suy từ Java object |
| Dùng `record.equals` làm key map qua nhiều lần update | Value equality thay đổi theo state/CAS | Dùng document key dạng `String` làm map key |

## 16. Bài thực hành: giỏ hàng bất biến với snapshot có CAS

**Đề bài:** một ứng dụng cần lưu giỏ hàng trong `shop.sales.carts` theo key `cart::u100`. Một giỏ có `customerId`, danh sách `CartLine`, thời gian tạo và CAS. Giỏ hàng có TTL 1 giờ; thêm dòng không được thay đổi record gốc. Hai request cùng đọc rồi sửa giỏ phải được phát hiện xung đột khi sử dụng `@Version`.

Hãy thiết kế:

1. Record `CartLine` với `sku`, `quantity` được kiểm tra.
2. Root record `Cart` có `@Document(expiry = 3600)`, `@Id`, `@Version`, `@Scope`, `@Collection`.
3. Factory tạo mới, phương thức `addLine` trả record mới, giữ nguyên key và CAS.
4. Test `save` → `findById` → `addLine` → `save` và test hai writer đồng thời.

### Lời giải gợi ý

~~~java
package com.example.shop.sales;

public record CartLine(String sku, int quantity) {
    public CartLine {
        if (sku == null || sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("Dòng giỏ hàng không hợp lệ");
        }
    }
}
~~~

~~~java
package com.example.shop.sales;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document(expiry = 3600)
@Scope("sales")
@Collection("carts")
public record Cart(
    @Id String id,
    @Version Long cas,
    @Field String customerId,
    @Field List<CartLine> lines,
    @Field("created_at") Instant createdAt
) {
    public Cart {
        if (id == null || id.isBlank()
                || customerId == null || customerId.isBlank()) {
            throw new IllegalArgumentException("Định danh giỏ hàng không hợp lệ");
        }
        lines = List.copyOf(Objects.requireNonNull(lines, "lines"));
        Objects.requireNonNull(createdAt, "createdAt");
    }

    public static Cart create(String customerId) {
        return new Cart(
            "cart::" + customerId,
            null,
            customerId,
            List.of(),
            Instant.now()
        );
    }

    public Cart addLine(CartLine line) {
        if (line == null || lines.size() >= 30) {
            throw new IllegalArgumentException("Không thể thêm dòng");
        }
        var updated = new ArrayList<>(lines);
        updated.add(line);
        return new Cart(id, cas, customerId, updated, createdAt);
    }
}
~~~

Đây là một ví dụ học tập: cần giới hạn/chuẩn hóa `customerId`, quyết định cách gộp hai dòng cùng SKU và không đặt thông tin nhạy cảm trong document key. `@Document(expiry = 3600)` là TTL ở cấp **toàn document**; nó không làm một `CartLine` riêng lẻ hết hạn sau 1 giờ. Nếu mỗi thao tác ghi làm mới expiry, hãy kiểm chứng chính sách thực tế theo API/version, không suy từ code Java.

Repository và luồng thao tác:

~~~java
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CartRepository extends CouchbaseRepository<Cart, String> {
}

// Tạo (hoặc dùng insert-only nếu không được phép ghi đè key).
Cart inserted = carts.save(Cart.create("u100"));

// Đọc để có CAS do Couchbase cung cấp.
Cart current = carts.findById(inserted.id()).orElseThrow();

// Tạo record mới, giữ CAS hiện tại và lưu.
Cart updated = carts.save(
    current.addLine(new CartLine("coffee250", 2))
);
~~~

**Trường hợp hai writer:** đọc `Cart a` và `Cart b` cùng key trước khi có ghi; sau `save(a.addLine(...))`, thử `save(b.addLine(...))`. Kỳ vọng phát hiện conflict khi `@Version`/CAS hoạt động đúng trên bản Spring Data Couchbase sử dụng. Nếu không có conflict, xem lại mapping và chiến lược ghi; **đừng suy đoán** record tự cung cấp optimistic locking.

### Tự kiểm tra

1. **Record có setter cho `cas` không?** Không; phải materialize instance mới khi metadata đổi.
2. **`@Id` được lưu trong JSON body hay ở metadata?** Là document key do Couchbase quản lý, không tự là field JSON.
3. **Có thể tự tăng `cas` để cập nhật record không?** Không. CAS do Couchbase cấp, dùng như token kiểm tra.
4. **Vì sao `List.copyOf` cần có trong compact constructor?** Tránh một `List` mutable bên ngoài đổi dữ liệu của record.
5. **Vì sao `Cart.create` dùng `Instant.now()` còn canonical constructor không?** Factory tạo đối tượng mới; constructor persistence phải khôi phục thời gian đã lưu.
6. **Hai record cùng ID nhưng CAS khác nhau có `equals` bằng nhau không?** Không nhất thiết; record so toàn bộ components.
7. **TTL của Cart có tự áp riêng cho từng CartLine không?** Không, TTL là metadata cấp document.
8. **Khi cần generated ID sau save, điều gì phải được thử?** Framework có trả/tạo được bản sao record chứa ID và CAS mới không.
9. **SQL++ projection ba cột có tự dựng được root record với sáu component không?** Không nên giả định; dùng DTO hoặc SELECT đầy đủ theo mapper.
10. **Reactive repository có thay đổi rủi ro CAS/immutable không?** Không; chỉ thay cách xử lý I/O.

## 17. Checklist quyết định đưa record entity vào dự án

- [ ] Xác định record là **value object**, **DTO** hay **root entity** có lifecycle metadata.
- [ ] Kiểm tra phiên bản Java và Spring Data Couchbase có hỗ trợ mapping record component/annotation đang dùng.
- [ ] Với root, gắn đúng `@Id` và `@Version` nếu cần CAS; không nhầm `version` với schema version.
- [ ] Ưu tiên ID ứng dụng tạo sẵn nếu generated ID trên immutable record chưa được kiểm chứng.
- [ ] Không sinh ID, thời gian tạo hoặc side effect trong canonical constructor.
- [ ] Dùng defensive copy cho List/Map/Set và value object bất biến bên trong.
- [ ] Mọi phương thức thay đổi trạng thái trả record mới và **giữ đúng ID + CAS**.
- [ ] Luôn dùng kết quả `save` hoặc đọc lại để lấy metadata hiện hành trước cập nhật tiếp.
- [ ] Kiểm thử CAS conflict bằng hai snapshot độc lập, có xử lý retry hợp lệ.
- [ ] Kiểm thử document thiếu field, JSON null, sai kiểu, rename `@Field` và schema cũ.
- [ ] Không dựa vào `record.equals` cho entity identity qua nhiều phiên bản.
- [ ] Hiểu TTL là metadata của document, không phải trường JSON mặc định.
- [ ] Dùng DTO record cho SQL++ projection; đừng ép projection thiếu field vào root entity.
- [ ] Chỉ tạo index cho truy vấn theo thuộc tính; `findById` theo KV không cần secondary index.
- [ ] Nếu mapper/lifecycle khó dự đoán, cân nhắc immutable class có withers hoặc POJO mutable được kiểm soát.

## Tài liệu tham khảo chính thức

- [Java Language Specification — Record Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10): canonical constructor, final components và quy tắc record.
- [Spring Data Commons — Object Mapping Fundamentals](https://docs.spring.io/spring-data/commons/reference/object-mapping.html): constructor resolution, Java record, immutable property population, wither và mapping.
- [Spring Data Couchbase — Modeling Entities](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Document`, `@Id`, `@Version`, `@Field`, type metadata và entity lifecycle.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): truy cập KV theo ID, query và entity save.
- [Spring Data Couchbase — Auto Generating Keys](https://docs.spring.io/spring-data/couchbase/reference/couchbase/autokeygeneration.html): chiến lược tạo key và giới hạn cần thử với ID bất biến.
- [Spring Data Couchbase — Collection Support](https://docs.spring.io/spring-data/couchbase/reference/couchbase/collections.html): bucket/scope/collection mapping.
- [Couchbase — Key-Value Operations](https://docs.couchbase.com/server/current/guides/kv-operations.html): document key, CAS, mutation và expiry.

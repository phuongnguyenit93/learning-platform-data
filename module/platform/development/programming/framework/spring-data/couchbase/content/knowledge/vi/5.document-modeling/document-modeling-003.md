# Ánh xạ tên trường bằng @Field và loại bỏ trường với @Transient trong Spring Data Couchbase

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **tên thuộc tính Java** và **tên trường JSON trong Couchbase** có thể giống hoặc khác nhau.
2. Dùng `@Field` để đánh dấu field lưu trữ và đổi tên JSON mà không đổi tên thuộc tính trong code.
3. Dùng `@Transient` của **Spring Data** để loại thuộc tính ra khỏi quá trình ánh xạ và lưu/đọc document.
4. Phân biệt `@Transient` với từ khóa `transient` của Java, `@JsonIgnore` của Jackson, `@Id` và `@Version`.
5. Tìm đúng tên field khi viết SQL++, thiết kế index, kiểm tra CRUD và lên kế hoạch đổi tên field đã có dữ liệu.

Trong phần **Mô hình tài liệu** của module **SPRING_DATA_COUCHBASE**, ánh xạ field là cầu nối giữa mô hình Java và JSON mà Couchbase lưu trong bucket/scope/collection. Lựa chọn đúng mapping giúp repository, `CouchbaseTemplate`, truy vấn SQL++ và các quy trình vận hành đọc cùng một dữ liệu theo một quy ước nhất quán.

## 1. Hai tên gọi của cùng một thuộc tính

Xét lớp Java có `displayName` nhưng hệ thống quy định JSON dùng `display_name`. Nếu không cấu hình riêng, Spring Data Couchbase thường dùng **tên thuộc tính Java** để đặt tên field JSON. Annotation `@Field("display_name")` chỉ định tên field lưu trữ khác.

~~~java
import org.springframework.data.couchbase.core.mapping.Field;

@Field("display_name")
private String displayName;
~~~

Khi ánh xạ thành body của document:

~~~json
{
  "display_name": "Cà phê Arabica 250 g"
}
~~~

Tên được sử dụng theo từng ngữ cảnh:

| Ngữ cảnh | Tên sử dụng | Ví dụ |
| --- | --- | --- |
| Trường và getter/setter trong Java | Tên Java | `displayName`, `getDisplayName()` |
| Tên field ở JSON body | Tên Couchbase từ `@Field` | `display_name` |
| SQL++ tự viết | **Tên JSON thực tế** | `p.display_name` |
| Derived repository query | Tên thuộc tính entity Java | `findByDisplayName(...)` |
| Chỉ mục SQL++ | **Tên JSON thực tế** | `CREATE INDEX ... (display_name)` |

Chú ý: `@Field` không đổi tên document key. Key được ánh xạ qua `@Id` và được Couchbase quản lý ngoài JSON body. Annotation `@Version` giữ CAS metadata khi dùng optimistic locking, cũng không phải một field JSON thông thường.

## 2. Bộ annotation dùng trong bài

| Annotation / từ khóa | Import / nguồn | Tác dụng đối với persistence |
| --- | --- | --- |
| `@Document` | `org.springframework.data.couchbase.core.mapping.Document` | Đánh dấu entity gốc được ánh xạ thành Couchbase document |
| `@Id` | `org.springframework.data.annotation.Id` | Ánh xạ document key |
| `@Field` | `org.springframework.data.couchbase.core.mapping.Field` | Đánh dấu thuộc tính lưu trữ; tùy chọn tên JSON khác tên Java |
| `@Transient` | `org.springframework.data.annotation.Transient` | Loại thuộc tính khỏi mô hình persistence của Spring Data |
| `@Version` | `org.springframework.data.annotation.Version` | Ánh xạ CAS metadata để hỗ trợ chống ghi đè đồng thời |
| Java `transient` | Từ khóa Java, không có import | Thuộc cơ chế Java Serialization; **không dùng thay thế** Spring Data `@Transient` |
| Jackson `@JsonIgnore` | `com.fasterxml.jackson.annotation.JsonIgnore` | Điều khiển JSON qua Jackson, thường là HTTP request/response; không có nghĩa là loại field khỏi Couchbase mapping |

**Điểm cần nhớ:** `@Field` là tùy chọn đối với nhiều thuộc tính. Tuy nhiên, khai báo rõ `@Field` trong entity thường giúp code thể hiện ý định lưu trữ và dễ tìm chỗ quy định schema. Trong ví dụ sau, `@Field` không có đối số và `@Field("...")` được đặt cạnh nhau để thấy sự khác biệt.

## 3. Ví dụ từ Java entity đến JSON thực tế

Giả sử ứng dụng lưu sản phẩm trong bucket `shop`, scope `catalog`, collection `products`. Bucket được cấu hình trong kết nối; `@Scope` và `@Collection` dưới đây chọn nơi lưu mặc định cho entity.

~~~java
package com.example.shop.catalog;

import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
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

    @Field("price_vnd")
    private long priceVnd;

    @Field
    private boolean active;

    @Field
    private List<String> tags = new ArrayList<>();

    @Version
    private Long version;

    @Transient
    private String requestTraceId;

    @Transient
    private String displayHintCache;

    protected Product() {
        // Spring Data dùng khi khởi tạo đối tượng từ document.
    }

    public Product(String sku, String displayName, long priceVnd) {
        if (sku == null || !sku.matches("[a-z0-9-]+")) {
            throw new IllegalArgumentException("SKU không hợp lệ");
        }
        if (displayName == null || displayName.isBlank() || priceVnd < 0) {
            throw new IllegalArgumentException("Dữ liệu sản phẩm không hợp lệ");
        }
        this.id = "product::" + sku;
        this.displayName = displayName;
        this.priceVnd = priceVnd;
        this.active = true;
    }

    public String getId() { return id; }
    public String getDisplayName() { return displayName; }
    public long getPriceVnd() { return priceVnd; }
    public boolean isActive() { return active; }
    public List<String> getTags() { return List.copyOf(tags); }

    public void changeDisplayName(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        this.displayName = newName;
        this.displayHintCache = null;
    }

    public void addTag(String tag) {
        if (tag == null || tag.isBlank()) {
            throw new IllegalArgumentException("Nhãn không hợp lệ");
        }
        this.tags.add(tag);
    }

    public void attachRequestTraceId(String traceId) {
        this.requestTraceId = traceId;
    }

    public String displayHint() {
        if (displayHintCache == null) {
            displayHintCache = displayName + " • " + priceVnd + " VND";
        }
        return displayHintCache;
    }
}
~~~

Ví dụ dùng kiểu `long` để biểu diễn giá VND nguyên và giữ code dễ đọc. Ứng dụng thật cần quy tắc tiền tệ, kiểm tra dữ liệu đầu vào và chính sách làm tròn riêng. `requestTraceId` ở đây minh họa dữ liệu gắn với lượt xử lý tạm thời, không phải thông tin nghiệp vụ cần lưu.

Sau khi lưu sản phẩm có ID `product::coffee250`, body JSON có thể trông như sau:

~~~text
Bucket:      shop
Scope:       catalog
Collection:  products
Document ID: product::coffee250
~~~

~~~json
{
  "_class": "com.example.shop.catalog.Product",
  "display_name": "Cà phê Arabica 250 g",
  "price_vnd": 175000,
  "active": true,
  "tags": ["coffee", "arabica"]
}
~~~

Ở mapping thông thường, Spring Data có thể thêm `_class` làm metadata loại đối tượng trong body; tên hoặc sự xuất hiện của thông tin loại này có thể thay đổi theo cấu hình mapper. **Không** có `id`, `version`, `requestTraceId` hay `displayHintCache` trong body ví dụ:

- `id` là **document key**, không phải field JSON `id`.
- `version` đại diện **CAS metadata**.
- Hai field `@Transient` không tham gia lưu trữ.
- Tên `display_name` và `price_vnd` đến trực tiếp từ `@Field("...")`.

### Khi đọc lại sẽ có những gì?

Spring Data dùng JSON body để nạp `displayName`, `priceVnd`, `active`, `tags`; document key/CAS đi vào hai thuộc tính tương ứng. Hai thuộc tính `@Transient` **không được tái tạo từ document**, nên trong đối tượng vừa đọc có thể là `null` hoặc giá trị mặc định do constructor/khởi tạo field đặt sẵn.

Với `displayHintCache`, việc gọi `displayHint()` lần đầu sẽ tính lại chuỗi. Đây là cách phù hợp với dữ liệu có thể suy ra từ những field đã lưu. Với `requestTraceId`, service phải gắn lại theo ngữ cảnh request nếu còn cần, thay vì trông chờ repository tải nó từ Couchbase.

## 4. @Field: đổi tên, giữ tên và chiến lược đặt tên

### 4.1. Đổi tên JSON nhưng giữ tên Java

~~~java
@Field("display_name")
private String displayName;

@Field("price_vnd")
private long priceVnd;
~~~

Lợi ích là bạn có thể dùng camelCase tự nhiên trong Java, đồng thời thống nhất snake_case cho JSON và SQL++. Tên trong `@Field("...")` phải khớp **chính xác**, bao gồm chữ hoa/chữ thường, với tên lưu trong Couchbase.

### 4.2. Dùng tên mặc định

~~~java
@Field
private boolean active;
~~~

Trường JSON mặc định là `active`. Bỏ annotation vẫn có thể được ánh xạ theo convention mặc định của Spring Data Couchbase. Nhưng **đừng suy luận** rằng mọi field không có `@Field` sẽ tự biến mất khỏi document: mặc định nhiều thuộc tính entity vẫn được lưu.

### 4.3. Trường lồng nhau

Một value object có thể được nhúng vào cùng document, và các field con vẫn có thể đặt tên JSON riêng:

~~~java
public class Packaging {
    @Field("weight_grams")
    private int weightGrams;

    @Field
    private String material;

    protected Packaging() {}

    public Packaging(int weightGrams, String material) {
        this.weightGrams = weightGrams;
        this.material = material;
    }
}
~~~

Nếu entity Product có thuộc tính `@Field private Packaging packaging;`, body có thể chứa:

~~~json
{
  "packaging": {
    "weight_grams": 250,
    "material": "paper"
  }
}
~~~

`Packaging` là giá trị con, không cần `@Document` và `@Id` riêng khi vòng đời của nó gắn liền với Product. Khi một đối tượng có quyền sửa, vòng đời và bất biến độc lập, cân nhắc lưu thành aggregate riêng và tham chiếu bằng ID.

### 4.4. FieldNamingStrategy

Spring Data cung cấp cơ chế `FieldNamingStrategy` để quy định cách đặt tên field khi không có khai báo tên cụ thể. Chiến lược mặc định giữ tên property Java; hệ thống có thể tùy biến toàn cục trong mapping context.

Tuy vậy, một tên được chỉ định rõ bằng `@Field("...")` vẫn là hợp đồng schema quan trọng. Khi dự án có nhiều nhóm dịch vụ hoặc dữ liệu đã tồn tại, ưu tiên **quy ước có thể kiểm chứng** thay vì đổi naming strategy toàn cục mà không xem tác động đến các document cũ.

## 5. @Transient: field không thuộc trạng thái lưu trữ

`@Transient` của Spring Data cho biết thuộc tính không được xem là một persistent property. Do đó, nó không được ghi vào body và cũng không được nạp từ body khi entity được materialize qua Spring Data.

Các trường hợp phù hợp:

- **Cache tính toán:** chuỗi hiển thị, kết quả tạm có thể tính lại từ dữ liệu gốc.
- **Thông tin request:** correlation/trace ID, thuộc tính chỉ hữu ích trong một lượt xử lý.
- **Trạng thái giao diện:** thông báo, gợi ý hiển thị, cờ tạm của một workflow.
- **Giá trị dẫn xuất:** tổng tạm tính có thể tính lại từ danh sách sản phẩm, nếu nghiệp vụ không yêu cầu lưu snapshot của tổng.

Ví dụ rõ nhất:

~~~java
@Field("unit_price_vnd")
private long unitPriceVnd;  // phải lưu

@Transient
private String formattedPrice; // có thể tự tính lại: "175.000 VND"
~~~

### @Transient không phải công cụ bảo vệ bí mật trong API

Một field bị loại khỏi Couchbase vẫn có thể xuất hiện trong HTTP JSON nếu Jackson dùng getter hoặc quy tắc serialization riêng. Ví dụ `getRequestTraceId()` có thể được Jackson phát hiện dù field gắn `@Transient`.

Đừng dùng `@Transient` như một cam kết rằng nội dung sẽ không rò rỉ ra API hoặc log. Nếu cần kiểm soát response, sử dụng **DTO riêng** hoặc cơ chế Jackson phù hợp (như `@JsonIgnore`). Nếu dữ liệu nhạy cảm không cần thiết, không nên giữ nó trong entity.

### Vì sao không dùng từ khóa transient của Java?

~~~java
// Không đủ để chỉ dẫn Spring Data persistence:
private transient String requestTraceId;

// Ý định rõ ràng, đúng annotation của Spring Data:
@Transient
private String requestTraceId;
~~~

Từ khóa `transient` thuộc cơ chế **Java Serialization**; tài liệu Spring Data nhấn mạnh mapping không dựa vào từ khóa đó để xác định thuộc tính cần loại bỏ. Cũng không nên lẫn `org.springframework.data.annotation.Transient` với `jakarta.persistence.Transient` của JPA hoặc `@JsonIgnore` của Jackson.

### Không ghi nhưng có thể vẫn tồn tại trong dữ liệu cũ

Giả sử tài liệu JSON cũ đã chứa `requestTraceId`. Sau khi thêm `@Transient`:

- Spring Data **không đọc/ghi thuộc tính** này trong mô hình entity mới.
- **Các document cũ không tự được di trú hàng loạt** chỉ vì code đổi annotation.
- Một thao tác thay thế toàn bộ body trong tương lai có thể loại field cũ, nhưng cơ chế ghi từng field/SQL++ hoặc những document chưa từng sửa có thể vẫn giữ nó.

Nếu field cũ phải bị xóa vì chính sách bảo mật hoặc giảm dung lượng, hãy có kế hoạch migration riêng, rà soát dữ liệu, backup và kiểm chứng đầy đủ.

## 6. @Field quyết định tên trong SQL++ và chỉ mục

Dùng `@Field("price_vnd")` có nghĩa truy vấn SQL++ phải dùng **`price_vnd`**, dù Java gọi là `priceVnd`. Giả sử bucket/scope/collection là `shop.catalog.products`:

~~~sql
CREATE INDEX ix_products_active_price
ON `shop`.`catalog`.`products`(active, price_vnd);
~~~

Truy vấn cho danh sách sản phẩm đang bán, giá không vượt 200.000 VND:

~~~sql
SELECT META(p).id AS documentId,
       p.display_name AS displayName,
       p.price_vnd AS priceVnd
FROM `shop`.`catalog`.`products` AS p
WHERE p.active = TRUE
  AND p.price_vnd <= 200000
ORDER BY p.price_vnd ASC
LIMIT 20;
~~~

Ở đây `displayName` và `priceVnd` **sau `AS`** chỉ là tên cột trả về của projection; trong phần `WHERE`, `ORDER BY` và `CREATE INDEX` phải dùng tên field lưu trữ thực tế.

Bảng ánh xạ giúp bạn kiểm tra query:

| Entity Java | JSON thực tế | Cú pháp SQL++ |
| --- | --- | --- |
| `displayName` | `display_name` | `p.display_name` |
| `priceVnd` | `price_vnd` | `p.price_vnd` |
| `active` | `active` | `p.active` |
| `id` gắn `@Id` | Couchbase document key, ngoài JSON body | `META(p).id` |
| `requestTraceId` gắn `@Transient` | Không được persistence lưu | Không dùng như điều kiện query trên dữ liệu mới |

**Không nên tạo index trên field `@Transient` rồi kỳ vọng có dữ liệu để lọc.** Chỉ mục chỉ nhìn vào JSON thực tế đã được lưu; field không có trong body sẽ không mang giá trị mà bạn dự đoán từ đối tượng Java.

Khi dùng derived repository query, bạn viết tên **property Java**, ví dụ:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface ProductRepository extends CouchbaseRepository<Product, String> {
    List<Product> findByDisplayName(String displayName);
}
~~~

Spring Data ánh xạ thuộc tính đã biết sang field lưu trữ trong truy vấn được tạo. Nhưng nếu tự viết `@Query` SQL++ thủ công, bạn phải dùng tên JSON như `display_name` và bảo đảm SELECT phù hợp với mapping entity, bao gồm document ID và metadata loại đối tượng khi cơ chế mapping yêu cầu. Đối với truy vấn nhiều document, tạo index phù hợp và kiểm tra `EXPLAIN`; riêng `findById(...)` thường đi qua KV theo key và không cần secondary index.

**Về độ tươi:** index được cập nhật theo cơ chế index của Couchbase; truy vấn SQL++ có thể có độ trễ quan sát khác so với đọc KV trực tiếp. Nhu cầu đọc ngay sau ghi phải được thiết kế với scan consistency phù hợp hoặc đọc theo ID.

## 7. Thử luồng ghi, đọc và tính lại field transient

Service dưới đây minh họa entity được tạo, gắn thông tin request tạm và lưu bằng repository:

~~~java
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Product create(String sku, String name, long priceVnd, String traceId) {
        Product product = new Product(sku, name, priceVnd);
        product.addTag("new");
        product.attachRequestTraceId(traceId);
        return repository.save(product);
    }

    public Product load(String sku) {
        return repository.findById("product::" + sku)
            .orElseThrow(() -> new IllegalArgumentException("Không có sản phẩm"));
    }
}
~~~

Ví dụ khi gọi:

~~~java
Product created = service.create(
    "coffee250", "Cà phê Arabica 250 g", 175000, "req-8392"
);
Product reloaded = service.load("coffee250");

System.out.println(reloaded.getDisplayName()); // Cà phê Arabica 250 g
System.out.println(reloaded.displayHint());     // Tính từ field đã lưu
~~~

Vì `requestTraceId` không có getter trong ví dụ đầy đủ, service không đưa nó vào giao diện public của entity; nhưng dù có getter, `requestTraceId` sau khi đọc lại vẫn không mang giá trị `req-8392` do persistence không lưu nó. Một trường transient được khởi tạo sẵn hoặc tính lại khi gọi getter có thể có giá trị mới; điều này không có nghĩa nó đã được lưu.

Đây là mô hình học tập, không phải API bảo đảm *create only*. `save` phải được sử dụng với hiểu biết về ngữ nghĩa tạo/sửa, CAS và khả năng retry; nếu cần chống trùng khóa tuyệt đối, dùng thao tác insert có ngữ nghĩa chỉ tạo mới và xử lý xung đột.

## 8. Đổi tên field khi dữ liệu đã có: bài toán migration

Giả sử phiên bản cũ lưu:

~~~json
{
  "displayName": "Cà phê Arabica 250 g",
  "priceVnd": 175000
}
~~~

Phiên bản mới đổi mapping thành:

~~~java
@Field("display_name")
private String displayName;

@Field("price_vnd")
private long priceVnd;
~~~

**Chỉ đổi annotation không tự đổi tên key JSON trong document đã lưu.** Khi đọc dữ liệu cũ, `display_name` có thể bị coi là không có, dẫn đến Java `displayName == null`; `priceVnd` kiểu nguyên thủy có thể nhận mặc định `0`. Đây là lỗi nguy hiểm vì chương trình vẫn có thể chạy nhưng dữ liệu sai.

Quy trình an toàn khi đổi tên field:

1. **Khảo sát:** thống kê số document đang dùng tên cũ và tên mới; xác định client hoặc job nào còn đọc/ghi tên cũ.
2. **Định nghĩa tương thích:** chọn triển khai reader chấp nhận cả hai dạng trong giai đoạn chuyển đổi hoặc chạy migration có kiểm soát trước khi bật code mới.
3. **Di trú dữ liệu:** cập nhật JSON theo batch, giữ document key, kiểm tra CAS/ghi đồng thời và tránh bỏ sót document mới được tạo trong lúc chuyển đổi.
4. **Đồng bộ query/index:** đổi tên field ở SQL++, index, export, dashboard và các dịch vụ phụ thuộc.
5. **Kiểm chứng:** so số lượng document, tỷ lệ missing, đối chiếu giá trị và bảo đảm rollback; sau đó loại dần code tương thích.

Ví dụ SQL++ **minh họa một lần migration**, chỉ chạy trên môi trường thử nghiệm sau khi chuẩn bị backup và kế hoạch triển khai:

~~~sql
UPDATE `shop`.`catalog`.`products` AS p
SET p.display_name = p.displayName,
    p.price_vnd = p.priceVnd
UNSET p.displayName,
      p.priceVnd
WHERE p.display_name IS MISSING
  AND p.displayName IS NOT MISSING
  AND p.price_vnd IS MISSING
  AND p.priceVnd IS NOT MISSING;
~~~

Điều kiện trên chỉ bao phủ những document có **cả hai** field cũ và chưa có **cả hai** field mới. Dataset thực tế có thể chứa document mới một phần hoặc thiếu field; cần phân nhóm và di trú riêng thay vì coi truy vấn ví dụ là giải pháp cho mọi dữ liệu. Việc mutation bằng SQL++ còn có thể xung đột với writer đang hoạt động; lên lịch, đo lường và xác thực trước khi mở rộng.

### Khi muốn xóa field đã chuyển thành @Transient

Đổi một property từ `@Field` thành `@Transient` cũng là **thay đổi hợp đồng dữ liệu**. Cần rà soát phần code/query/index và quyết định có xóa dữ liệu cũ khỏi document hay lưu tạm để hỗ trợ rollback. Với field có thông tin nhạy cảm, chính sách xóa phải bao gồm bản sao, backup, read model và log liên quan theo yêu cầu hệ thống.

## 9. Chẩn đoán những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| Java field đọc ra `null` dù JSON có dữ liệu | JSON lưu `displayName` nhưng mapping đòi `display_name` | Xem trực tiếp body, so với `@Field` và quá trình migration |
| Truy vấn theo giá không trả dữ liệu | SQL++ dùng `priceVnd` thay vì `price_vnd` | So tên field thực tế, sửa query/index và chạy `EXPLAIN` |
| Thông tin tạm biến mất sau `findById` | Field gắn `@Transient` không được lưu | Tính lại/gắn lại ở service nếu còn cần |
| Field không gắn `@Field` vẫn xuất hiện trong JSON | Mapping mặc định vẫn persist thuộc tính | Dùng `@Transient` nếu có chủ đích loại khỏi document |
| Thêm từ khóa Java `transient` nhưng field vẫn được lưu | Nhầm Java Serialization với Spring Data persistence | Dùng `org.springframework.data.annotation.Transient` |
| Field transient xuất hiện trong HTTP response | Jackson là hệ thống serialization khác | Dùng response DTO hoặc quy tắc Jackson thích hợp |
| Document cũ vẫn chứa field đã @Transient | Code đổi annotation không tự quét và di trú dữ liệu | Chạy migration có kiểm chứng nếu cần loại dữ liệu cũ |
| Document mới không đọc được ở repository | Sai ID hoặc scope/collection | Kiểm tra `@Id`, `@Scope`, `@Collection`, key thực tế |
| Ghi đồng thời bị `OptimisticLockingFailureException` | `@Version` phát hiện CAS thay đổi | Đọc lại, xác thực nghiệp vụ và retry có giới hạn |
| Đổi tên Java property khiến query hỏng | Derived method dùng tên Java; SQL++ dùng tên JSON | Kiểm tra từng đường đi query và mapping |

Đặc biệt, đừng đánh đồng ba thao tác: `@Field` **đổi tên trong persistence**, `@Transient` **loại khỏi persistence**, còn `@JsonIgnore` **kiểm soát một kênh serialization khác**. Đặt đúng annotation theo vấn đề cần giải quyết.

## 10. Bài thực hành có lời giải

Một hệ thống bán hàng có entity `Customer`, yêu cầu:

- Lưu ở `shop.crm.customers`, key `customer::u100`.
- Java property là `fullName`, `email`, `active`; JSON cần `full_name`, `email`, `active`.
- Field `lastViewedPage` chỉ dùng để làm đẹp giao diện theo phiên.
- Field `supportCorrelationId` chỉ dùng để nối log trong request hiện tại.
- Khi thay đổi `fullName`, dữ liệu mới phải được lưu; hai field tạm không được lưu.

**Lời giải gợi ý:**

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
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

    @Field("full_name")
    private String fullName;

    @Field
    private String email;

    @Field
    private boolean active;

    @Version
    private Long version;

    @Transient
    private String lastViewedPage;

    @Transient
    private String supportCorrelationId;

    protected Customer() {}

    public Customer(String customerCode, String fullName, String email) {
        this.id = "customer::" + customerCode;
        this.fullName = fullName;
        this.email = email;
        this.active = true;
    }

    public String getId() { return id; }
    public String getFullName() { return fullName; }

    public void rename(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        this.fullName = name;
    }

    public void attachSupportCorrelationId(String id) {
        this.supportCorrelationId = id;
    }
}
~~~

Khi persist entity này, JSON body mặc định gồm `full_name`, `email`, `active` và có thể có metadata loại `_class`; document key `customer::u100` nằm ngoài body. Các field `@Transient` không được lưu. Đọc bằng repository theo ID sẽ tải lại thuộc tính được persist; dữ liệu phục vụ phiên phải được gắn lại theo ngữ cảnh.

### Tự kiểm tra

1. **`@Field("full_name")` có đổi tên field Java `fullName` không?** Không; chỉ quy định tên lưu trữ.
2. **Thiếu `@Field` có nghĩa là field không lưu?** Không; nhiều property vẫn được mapping theo convention mặc định.
3. **Dùng `@Transient` có xóa field tương ứng của mọi document cũ không?** Không; phải tính đến migration.
4. **Một trường `@Transient` có được Jackson serialize ra API không?** Có thể, tùy getter và cấu hình Jackson; nên dùng DTO khi cần kiểm soát.
5. **Truy vấn SQL++ nên lọc `fullName` hay `full_name`?** `full_name`, vì đó là field JSON thực tế.
6. **Có cần index để `findById("customer::u100")` không?** Không cần secondary index cho truy cập KV theo key.
7. **Với field cache tính toán, nên lưu vào Couchbase hay @Transient?** Nếu có thể tính lại và không phải snapshot nghiệp vụ cần bảo toàn, `@Transient` thường phù hợp; nếu có yêu cầu lịch sử/đồng bộ lâu dài, cần thiết kế field được persist rõ ràng.

## 11. Checklist áp dụng vào dự án thật

- [ ] Phân biệt rõ tên Java, tên JSON và document key.
- [ ] Import `@Field` của Spring Data Couchbase và `@Transient` của Spring Data.
- [ ] Định nghĩa naming convention, tránh thay đổi tên field tùy tiện sau khi đã có dữ liệu.
- [ ] Chỉ dùng `@Transient` cho trạng thái không cần khôi phục từ document.
- [ ] Tách kiểm soát persistence khỏi kiểm soát JSON HTTP, log và bảo mật.
- [ ] Viết SQL++/index theo tên field lưu trữ; derived query theo tên thuộc tính Java.
- [ ] Kiểm tra CRUD trên document thật và so sánh body trước/sau save/load.
- [ ] Xem xét CAS, TTL, transaction và các writer khác trước khi migration hoặc sửa dữ liệu hàng loạt.
- [ ] Có kế hoạch tương thích và kiểm thử dữ liệu cũ khi đổi tên/xóa field.

## Tài liệu tham khảo

- [Spring Data Couchbase — Modeling Entities](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): cấu trúc entity, `@Field`, `@Transient`, constructor và nguyên tắc object mapping.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): derived query và các đường đi truy cập theo ID/query.
- [Spring Data Couchbase — Collection Support](https://docs.spring.io/spring-data/couchbase/reference/couchbase/collections.html): `@Scope`, `@Collection` và cách xác định nơi lưu.
- [Spring Data Couchbase — Transactions](https://docs.spring.io/spring-data/couchbase/reference/couchbase/transactions.html): giao dịch, optimistic locking và tính nhất quán khi ghi.
- [Couchbase — SQL++ CREATE INDEX](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/createindex.html): index trên các field JSON thực tế.
- [Spring Data Commons — Object Mapping Fundamentals](https://docs.spring.io/spring-data/commons/reference/object-mapping.html): quy tắc mapping property và phân biệt `@Transient` với Java `transient`.

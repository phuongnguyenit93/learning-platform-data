# Phân biệt khóa tài liệu với một trường id trong nội dung JSON của Spring Data Couchbase

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **document key** do Couchbase quản lý với trường **`id`** nằm trong phần nội dung JSON.
2. Giải thích cách `@Id` của Spring Data Couchbase ánh xạ document key và khi nào cần thêm một thuộc tính nghiệp vụ có tên JSON là `id`.
3. Đọc document bằng Key-Value, repository hoặc `CouchbaseTemplate`; viết SQL++ sử dụng đúng `META().id` và `document.id`.
4. Thiết kế khóa ổn định, tránh trùng key, nhầm collection và đồng bộ sai giữa khóa với mã nghiệp vụ.
5. Hiểu hệ quả đối với chỉ mục, tham chiếu, CAS, TTL, giao dịch, migration, API reactive và kiểm thử.

Chủ đề thuộc chương **Mô hình tài liệu** của module **SPRING_DATA_COUCHBASE**. Spring Data Couchbase cung cấp document mapping, repository, `CouchbaseTemplate` và SQL++; tất cả các công cụ đó đều cần biết **định danh lưu trữ thực sự** của document. Trong Couchbase, từ *ID* có thể xuất hiện ở nhiều nơi, nhưng chúng không mang cùng một ý nghĩa.

## 1. Mô hình đúng: document key và JSON body là hai lớp khác nhau

Couchbase lưu mỗi mục dưới dạng một **cặp key–value** trong một collection:

- **Document key** là chuỗi khóa định danh một mục trong collection. Couchbase dùng khóa này cho các lệnh Key-Value (KV) như `get`, `insert`, `replace` và `remove`.
- **Value (JSON body)** là nội dung ứng dụng tự định nghĩa. Một field bất kỳ trong JSON có thể tên là `id`, `productId`, `sku`, `externalCode` hoặc hoàn toàn không có field liên quan đến định danh.
- **Metadata** bao gồm key, CAS và thông tin expiry. SQL++ cung cấp hàm `META()` để xem metadata.
- Một số field do **Spring Data thêm vào JSON body**, chẳng hạn `_class` trong cấu hình mapping thông thường, vẫn là dữ liệu trong body; đừng nhầm với metadata key/CAS do Couchbase quản lý.

Giả sử document nằm trong:

~~~text
Bucket:       shop
Scope:        catalog
Collection:   products
Document key: product::coffee250
~~~

Nhưng body lại có dạng:

~~~json
{
  "id": "SKU-ARABICA-250",
  "display_name": "Cà phê Arabica 250 g",
  "price_vnd": 175000
}
~~~

**Hai giá trị `product::coffee250` và `SKU-ARABICA-250` độc lập.** Giá trị trước xác định document khi gọi KV, còn giá trị sau là dữ liệu trong JSON, có thể đại diện mã hàng của hệ thống đối tác.

~~~mermaid
flowchart TB
    D["Một document trong shop.catalog.products"]
    D --> M["Metadata do Couchbase quản lý"]
    D --> B["JSON body"]
    M --> K["Document key = product::coffee250"]
    M --> C["CAS và expiry"]
    B --> I["Field id = SKU-ARABICA-250"]
    B --> N["display_name, price_vnd, ..."]
~~~

Nếu chỉ xem phần body bằng một công cụ xuất JSON, bạn có thể không thấy document key. Nếu chỉ xem document key trong giao diện quản trị, bạn có thể tưởng nó là trường `id` trong body. Cả hai kết luận đều có thể sai.

## 2. Ba trường hợp phổ biến: thiếu, trùng hoặc khác giá trị

Couchbase **không yêu cầu** JSON body phải có field `id`.

| Trường hợp | Document key | JSON body | Ý nghĩa |
| --- | --- | --- | --- |
| Không có `id` trong body | `product::a1` | `{"name":"Cà phê"}` | Hoàn toàn hợp lệ; chỉ dùng metadata key để định danh |
| `id` trong body giống key | `product::a1` | `{"id":"product::a1","name":"Cà phê"}` | Có bản sao khóa trong JSON, do ứng dụng chủ động lưu |
| `id` trong body khác key | `product::a1` | `{"id":"SKU-250","name":"Cà phê"}` | `id` là mã nghiệp vụ hoặc dữ liệu bên ngoài, độc lập với key |

Ví dụ nếu hai document cùng lưu:

~~~json
{"id": "SKU-250", "name": "Sản phẩm A"}
~~~

và:

~~~json
{"id": "SKU-250", "name": "Sản phẩm B"}
~~~

thì Couchbase vẫn có thể lưu cả hai **nếu document key khác nhau**. Tính duy nhất của **key** không tự biến field `id` trong body thành một trường unique.

Một hệ thống có thể quy định `body.id` luôn bằng key, nhưng đó là **quy ước ứng dụng**, không phải điều Couchbase tự cưỡng chế. Nếu cần chống trùng một mã nghiệp vụ khác key, bạn phải thiết kế cơ chế riêng (ví dụ dùng chính mã đó làm key, có document đặt chỗ duy nhất, hoặc một quy trình ghi có điều kiện); secondary index thông thường không tự bảo đảm tính duy nhất của giá trị.

## 3. Phạm vi, độ dài và tính bất biến của document key

### 3.1. Key là duy nhất trong một collection

Danh tính đầy đủ của một document bao gồm **keyspace + document key**, chẳng hạn:

~~~text
shop.catalog.products + product::coffee250
~~~

Cùng chuỗi `product::coffee250` có thể tồn tại trong collection khác, ví dụ `shop.archive.products`, mà không phải cùng một document. Khi cấu hình Spring Data Couchbase sai scope hoặc collection, `findById` có thể trả rỗng dù bạn nhìn thấy chuỗi key đó ở nơi khác.

**Không gọi một chuỗi key là định danh toàn cluster** nếu không kèm rõ bucket/scope/collection của nó.

### 3.2. Key không đổi tại chỗ

Couchbase không hỗ trợ đổi key hiện tại bằng cách sửa một field trong JSON. Khi sản phẩm đổi tên hoặc mã hàng, cập nhật `display_name` hay `body.id` **không thay đổi document key**.

Nếu thật sự cần chuyển document từ `product::old` sang `product::new`, ứng dụng phải tạo một document dưới key mới, cập nhật các tham chiếu có liên quan và chỉ xóa key cũ khi bảo đảm chuyển đổi thành công. Quy trình này có thể cần transaction hoặc workflow idempotent tùy ràng buộc hệ thống.

### 3.3. Key có giới hạn byte và phải được chuẩn hóa

Tài liệu Couchbase Server hiện hành mô tả giới hạn **246 byte** cho key thông thường, với trường hợp truy cập collection mặc định theo chế độ tương thích cũ có thể **250 byte**. Một số tài liệu SDK/Spring Data phiên bản khác vẫn ghi mốc 250 byte nói chung. Vì vậy, kiểm tra quy định của **phiên bản Server và cách truy cập collection** đang sử dụng; nên thiết kế key ngắn hơn giới hạn đáng kể.

Độ dài tính theo **byte**, không theo số ký tự Unicode: một chuỗi có dấu tiếng Việt có thể cần nhiều byte UTF-8 hơn số ký tự hiển thị. Tránh tạo key từ tên người dùng, email, token, số điện thoại hoặc dữ liệu nhạy cảm; dùng ID ổn định và chuẩn hóa tại biên hệ thống.

### 3.4. Mẫu khóa có chủ đích

| Đối tượng | Key ví dụ | Đánh giá |
| --- | --- | --- |
| Product | `product::coffee250` | Tốt nếu mã `coffee250` ổn định, duy nhất |
| Order | `order::5f7d...` | ID phát sinh ổn định, không gắn với trạng thái đơn |
| Customer | `customer::u100` | Không phụ thuộc email/số điện thoại có thể đổi |
| Cart tạm | `cart::session-a18` | Cần chính sách TTL và xử lý phiên |
| Product lấy tên làm key | `product::ca-phe-ngon-nhat` | Rủi ro nếu tên có thể đổi |

Tiền tố `product::`, `order::` chỉ là quy ước dễ quan sát; Couchbase không tự suy ra kiểu entity, collection hoặc quyền truy cập từ tiền tố.

## 4. Spring Data Couchbase: @Id là document key

Để Spring Data biết key, khai báo `@Id` từ đúng package:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
public class Product {
    @Id
    private String documentKey;

    @Field("display_name")
    private String displayName;
}
~~~

`@Id` ánh xạ `documentKey` sang **document key** của Couchbase. Java property không nhất thiết phải mang tên `id`, dù tài liệu Spring Data khuyên dùng tên `id` vì dễ hiểu. Tên trường Java là lựa chọn thiết kế; **vai trò key do annotation quyết định**.

Quan trọng: property `@Id` **không mặc nhiên tạo field `id` trong JSON body**. Khi Spring Data ghi document, nó dùng giá trị `@Id` làm key của thao tác KV. Một số phiên bản/cấu hình còn hỗ trợ chủ động ghi giá trị ID vào body bằng annotation mapping bổ sung; đừng coi điều đó là hành vi mặc định. Nếu muốn body có trường `id` khác nghĩa, nên biểu diễn bằng property nghiệp vụ riêng.

### 4.1. Ví dụ có cả @Id và JSON id

Ví dụ sau minh họa cách giữ **documentKey** làm khóa lưu trữ và `externalSku` làm field JSON có tên `id`:

~~~java
package com.example.shop.catalog;

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
    private String documentKey;

    @Field("id")
    private String externalSku;

    @Field("display_name")
    private String displayName;

    @Field("price_vnd")
    private long priceVnd;

    @Version
    private Long version;

    protected Product() {
        // Constructor cho Spring Data materialize entity.
    }

    public Product(
            String documentKey, String externalSku,
            String displayName, long priceVnd) {
        if (documentKey == null || documentKey.isBlank()
                || externalSku == null || externalSku.isBlank()
                || displayName == null || displayName.isBlank()
                || priceVnd < 0) {
            throw new IllegalArgumentException("Product không hợp lệ");
        }
        this.documentKey = documentKey;
        this.externalSku = externalSku;
        this.displayName = displayName;
        this.priceVnd = priceVnd;
    }

    public String getDocumentKey() { return documentKey; }
    public String getExternalSku() { return externalSku; }
    public String getDisplayName() { return displayName; }
    public long getPriceVnd() { return priceVnd; }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        this.displayName = newName;
    }

    public void changeExternalSku(String newSku) {
        if (newSku == null || newSku.isBlank()) {
            throw new IllegalArgumentException("Mã ngoài không hợp lệ");
        }
        this.externalSku = newSku;
    }
}
~~~

Ứng dụng sử dụng bucket `shop` do cấu hình kết nối cung cấp; `@Scope` và `@Collection` chỉ định nơi lưu mặc định của entity.

Lệnh khởi tạo:

~~~java
Product product = new Product(
    "product::coffee250",
    "SKU-ARABICA-250",
    "Cà phê Arabica 250 g",
    175000
);
~~~

Khi `ProductRepository.save(product)` thành công, một JSON body minh họa là:

~~~json
{
  "_class": "com.example.shop.catalog.Product",
  "id": "SKU-ARABICA-250",
  "display_name": "Cà phê Arabica 250 g",
  "price_vnd": 175000
}
~~~

Phía ngoài JSON, document key là `product::coffee250`. `_class` có thể xuất hiện trong body do Spring Data type mapper mặc định; nó không phải Couchbase document key. `version` được `@Version` ánh xạ từ **CAS metadata**, không phải `schema_version` hay một field JSON trong ví dụ.

Nếu gọi `product.changeExternalSku("SKU-NEW")` rồi lưu lại **cùng entity**, document key vẫn là `product::coffee250`. Trường JSON `id` có thể đổi thành `SKU-NEW`; vì vậy không dựa vào `body.id` để xác định đường đọc KV trừ khi đó là quy ước đã được ứng dụng xác thực.

### 4.2. Khi nào nên đặt hai giá trị bằng nhau?

Một số hệ thống dùng API công khai yêu cầu JSON response có `id` bằng document key. Điều đó **không có nghĩa** bạn bắt buộc lưu thêm `id` vào Couchbase.

Có thể dựng response DTO từ hai nguồn:

~~~java
public record ProductResponse(
    String id,
    String externalSku,
    String displayName,
    long priceVnd
) {}

public ProductResponse toResponse(Product product) {
    return new ProductResponse(
        product.getDocumentKey(),
        product.getExternalSku(),
        product.getDisplayName(),
        product.getPriceVnd()
    );
}
~~~

Nhờ vậy, API có `id = product::coffee250` nhưng Couchbase body vẫn có `id = SKU-ARABICA-250`; hoặc nếu không cần field `id` trong body, bạn bỏ `externalSku` và chỉ xuất `getDocumentKey()` trong DTO. **HTTP JSON do Jackson serialize không phải bản sao bắt buộc của JSON body trong Couchbase.**

Nếu có yêu cầu tương thích cũ buộc lưu lặp key trong body, đặt quy tắc đối chiếu, kiểm thử round-trip và chính sách migration rõ ràng. Dữ liệu trùng lặp là trách nhiệm bảo trì của ứng dụng.

## 5. Repository: findById dùng @Id, không dùng body.id

Khai báo repository:

~~~java
package com.example.shop.catalog;

import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface ProductRepository extends CouchbaseRepository<Product, String> {
    List<Product> findByExternalSku(String externalSku);
}
~~~

Hai lời gọi này có ý nghĩa khác nhau:

~~~java
// Đúng: đối số là Couchbase document key.
Product fromKey = products.findById("product::coffee250")
    .orElseThrow();

// Đây là derived query theo externalSku (field JSON tên "id").
List<Product> fromBodyField =
    products.findByExternalSku("SKU-ARABICA-250");
~~~

| Lời gọi | Giá trị dùng để tìm | Cơ chế thường dùng | Cần secondary index? |
| --- | --- | --- | --- |
| `findById("product::coffee250")` | Document key | KV | Không |
| `findByExternalSku("SKU-ARABICA-250")` | Field JSON `id` | SQL++ | Có, thiết kế theo truy vấn |
| `deleteById("product::coffee250")` | Document key | KV | Không |
| `existsById("product::coffee250")` | Document key | KV | Không |

**Dễ sai ở method `findById`:** đây là phương thức dành riêng của Spring Data repository, luôn truy cập thuộc tính ID được gắn `@Id`, ngay cả khi thuộc tính Java đó có tên `documentKey` hay `pk`. Nó không tự chuyển sang truy vấn field JSON `id`.

Nếu entity thực sự có property Java tên `id` nhưng **không** gắn `@Id`, việc tự viết method tên `findById` rất dễ đụng tên dành riêng. Khi cần truy vấn property nghiệp vụ, đặt tên rõ như `findByExternalSku` hoặc một derived method khác không trùng với API ID có sẵn.

### 5.1. CouchbaseTemplate cũng dùng key

~~~java
import org.springframework.data.couchbase.core.CouchbaseTemplate;

public Product loadByDocumentKey(
        CouchbaseTemplate template, String key) {
    return template.findById(Product.class).one(key);
}
~~~

`CouchbaseTemplate` dựa trên metadata entity để biết scope, collection và `@Id`. Đối số ở `one(key)` là **document key**, không phải field JSON `id`.

Dùng template hoặc repository **không làm tự đồng bộ** `documentKey` và `externalSku`; đó là hai property được ánh xạ tới hai vị trí khác nhau. Khi áp dụng API reactive, cách materialize và ý nghĩa ID vẫn như vậy; reactive chỉ thay đổi cách điều phối I/O không chặn.

### 5.2. Nếu đọc qua Couchbase Java SDK thuần

SDK cho phép thấy rõ ranh giới metadata và body:

~~~java
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.GetResult;
import com.couchbase.client.java.json.JsonObject;

// cluster được tạo và quản lý tại tầng kết nối.
Collection collection = cluster.bucket("shop")
    .scope("catalog").collection("products");

String documentKey = "product::coffee250";
GetResult result = collection.get(documentKey);

JsonObject body = result.contentAsObject();
String bodyId = body.getString("id"); // "SKU-ARABICA-250"
long cas = result.cas();

System.out.println(documentKey); // "product::coffee250"
System.out.println(bodyId);      // "SKU-ARABICA-250"
System.out.println(cas);         // CAS hiện tại
~~~

SDK không cần field `id` trong body để tìm document. `collection.get(key)` biết nơi lưu và key từ lời gọi; `contentAsObject()` chỉ giải mã phần JSON. Ví dụ trên bỏ qua quản lý lifecycle/đóng kết nối để tập trung vào phân biệt ID.

## 6. SQL++: META(p).id và p.id là hai biểu thức khác nhau

Trong SQL++, `META(p).id` trả về **document key** của nguồn `p`, còn `p.id` truy cập **field `id` trong JSON body**.

Ví dụ truy vấn một document đã biết key trong `shop.catalog.products`:

~~~sql
SELECT META(p).id AS documentKey,
       p.`id` AS bodyId,
       p.display_name AS displayName
FROM `shop`.`catalog`.`products` AS p
USE KEYS "product::coffee250";
~~~

Kết quả dự kiến khi body có `"id": "SKU-ARABICA-250"`:

~~~json
[
  {
    "documentKey": "product::coffee250",
    "bodyId": "SKU-ARABICA-250",
    "displayName": "Cà phê Arabica 250 g"
  }
]
~~~

`USE KEYS` chọn các document theo Couchbase key. Trong cú pháp `META(p).id`, `p` là **alias của keyspace**, không phải tên biến Java.

### 6.1. Nếu JSON body không chứa id?

Ví dụ một document khác có key `product::tea100` và body:

~~~json
{
  "display_name": "Trà xanh 100 g",
  "price_vnd": 99000
}
~~~

Khi chạy:

~~~sql
SELECT META(p).id AS documentKey,
       p.`id` AS bodyId
FROM `shop`.`catalog`.`products` AS p
USE KEYS "product::tea100";
~~~

`documentKey` vẫn là `product::tea100`. Biểu thức `p.id` là **MISSING**; trong một projection SQL++ thông thường, thuộc tính `bodyId` có thể **không xuất hiện** trong dòng kết quả, thay vì bắt buộc có `null`. `MISSING` khác `NULL` và khác chuỗi rỗng.

### 6.2. Hai cách lọc khác nhau

Theo key lưu trữ:

~~~sql
SELECT META(p).id AS documentKey, p.display_name
FROM `shop`.`catalog`.`products` AS p
USE KEYS $documentKey;
~~~

Theo mã nghiệp vụ trong JSON:

~~~sql
SELECT META(p).id AS documentKey,
       p.`id` AS externalSku,
       p.display_name
FROM `shop`.`catalog`.`products` AS p
WHERE p.`id` = $externalSku;
~~~

Truy vấn thứ hai là **query theo thuộc tính**, nên cần index phù hợp nếu thực thi thường xuyên trên dữ liệu lớn:

~~~sql
CREATE INDEX ix_products_external_sku
ON `shop`.`catalog`.`products`(`id`);
~~~

Đây là ví dụ index đơn giản; nếu còn bộ lọc theo trạng thái, phạm vi tenant hay sắp xếp, cần thiết kế lại theo workload và dùng `EXPLAIN`.

**Index không biến field JSON thành document key.** Sau khi tạo index, `collection.get("SKU-ARABICA-250")` vẫn tìm theo key bằng chuỗi đó và sẽ không tự tìm ra `product::coffee250`. Tương tự, index thông thường không bảo vệ tính duy nhất của `p.id`.

### 6.3. Lấy ID khi viết projection

Khi xuất dữ liệu để tạo file, API response hoặc đọc qua SQL++, hãy quyết định bạn muốn ID nào:

~~~sql
SELECT META(p).id AS storageKey,
       p.`id` AS externalCode,
       p.display_name AS displayName
FROM `shop`.`catalog`.`products` AS p
WHERE p.price_vnd > 0
LIMIT 20;
~~~

Nếu dùng `SELECT p.*` chỉ để xuất các field trong body, có thể bỏ lỡ key lưu trữ. Nếu chỉ lấy `p.id`, một hệ thống nhập dữ liệu có thể nhầm mã ngoài thành Couchbase key. Khi materialize lại **entity Spring Data** bằng query tùy chỉnh, SELECT còn phải trả đủ các field và metadata ID/type theo cơ chế mapper; projection ở trên là dữ liệu để đọc, không mặc nhiên là `Product` đầy đủ.

### 6.4. Không dùng update body.id để đổi key

Ví dụ phép sửa field JSON:

~~~sql
UPDATE `shop`.`catalog`.`products` AS p
USE KEYS "product::coffee250"
SET p.`id` = "SKU-ARABICA-NEW"
RETURNING META(p).id AS documentKey, p.`id` AS bodyId;
~~~

Nếu thao tác thành công, `documentKey` **vẫn là** `product::coffee250`. Đây chỉ là mutation JSON body. Nếu entity được load sẵn với `@Version`, một mutation bên ngoài Spring Data sẽ làm CAS của document thay đổi; lần `save` tiếp theo với phiên bản cũ có thể bị từ chối.

Trong dự án thật, sửa mã nghiệp vụ cần kiểm tra ràng buộc duy nhất, quyền cập nhật và các hệ thống phụ thuộc trước khi gọi query UPDATE; câu lệnh trên chỉ minh họa sự phân biệt giữa hai ID.

## 7. Tham chiếu giữa các document phải dùng đúng key

Giả sử Order có:

~~~json
{
  "order_code": "SO-125",
  "customerId": "customer::u100",
  "lines": [
    {
      "productId": "product::coffee250",
      "externalSkuAtPurchase": "SKU-ARABICA-250",
      "quantity": 2
    }
  ]
}
~~~

Ở đây:

- `productId` là **document key của Product** theo quy ước của ứng dụng.
- `externalSkuAtPurchase` là **mã hiển thị/historical snapshot** lưu cùng Order.
- Hai giá trị có thể giống nhau hoặc khác nhau; ứng dụng phải định nghĩa rõ.

Một phép lookup join qua key:

~~~sql
SELECT META(o).id AS orderKey,
       META(p).id AS productKey,
       p.display_name
FROM `shop`.`sales`.`orders` AS o
USE KEYS "order::125"
LEFT JOIN `shop`.`catalog`.`products` AS p
ON KEYS o.lines[0].productId;
~~~

Ví dụ này chỉ tra **dòng đầu tiên** để minh họa cú pháp `JOIN ON KEYS`. Khi Order có nhiều dòng, phải thiết kế truy vấn cho mảng hoặc đọc KV nhiều key một cách có giới hạn; không giả định join một biểu thức đơn trả đủ tất cả Product.

Nếu lưu `productId = "SKU-ARABICA-250"` nhưng key thật là `product::coffee250`, lookup theo key **không tìm được document**. Nếu muốn lưu mã ngoài làm reference, phải có bước ánh xạ mã ngoài sang key qua index/bảng tra, hoặc đổi thiết kế dùng chính mã ngoài ổn định làm key từ đầu.

Couchbase không tự tạo khóa ngoại từ các trường có tên `productId` hay `customerId`; ứng dụng quản lý tính hợp lệ, mục tiêu nhất quán, cách xóa và xử lý reference bị mất.

## 8. Khi nào nên sao chép key vào JSON body?

Thông thường, nếu toàn bộ ứng dụng làm việc bằng Spring Data/Couchbase SDK và biết key thông qua metadata, **không cần ghi trùng** document key vào body. Tuy nhiên, có trường hợp sao chép có mục đích:

| Tình huống | Có nên lưu trong body? | Lý do |
| --- | --- | --- |
| CRUD bằng `@Id` và `findById` | Thường không cần | Key đã có ở metadata |
| Xuất JSON cho hệ thống chỉ nhận payload, không nhận metadata key | Có thể cần | Hệ thống ngoài cần biết danh tính; DTO/export có thể bổ sung key lúc xuất |
| Lưu mã nghiệp vụ khác key | Có | Là dữ liệu miền, ví dụ `externalSku` hoặc `order_code` |
| SQL++ lọc theo mã nghiệp vụ | Có | Cần field để query/index, trừ khi mã đó chính là key và truy cập theo key |
| Hiển thị ID trong HTTP response | Không nhất thiết | Có thể dựng DTO từ `@Id` |
| Dùng chung nhiều dịch vụ với schema độc lập | Tùy hợp đồng | Chọn tên field rõ nghĩa và quy tắc đồng bộ |

Nếu bắt buộc lưu `body.id` bằng key, hãy quy định **một nguồn sự thật**, kiểm tra đồng nhất khi ghi và chuẩn bị migration cho dữ liệu không khớp. Không để hai trường được sửa độc lập rồi tin rằng framework tự sửa trường còn lại.

**Một cách giảm nhầm lẫn:** nếu JSON body chứa mã nghiệp vụ, đặt tên đúng như `externalSku`, `businessId`, `orderCode` hoặc `legacyId` thay vì `id` chung chung. Trong bài, field JSON `id` được giữ cố ý để thấy rõ ranh giới và hỗ trợ những schema bên ngoài đã có sẵn.

## 9. Đổi document key và di trú dữ liệu cũ

Giả sử phiên bản cũ lưu Product với:

~~~text
Key:   coffee250
Body:  {"id":"SKU-ARABICA-250", "display_name":"Cà phê"}
~~~

Phiên bản mới yêu cầu quy ước:

~~~text
Key:   product::coffee250
Body:  {"id":"SKU-ARABICA-250", "display_name":"Cà phê"}
~~~

Đây là **thay đổi key**, không phải sửa JSON field `id`. Lộ trình cần cân nhắc:

1. **Khảo sát:** đếm document theo key cũ/mới, kiểm tra reference, index, TTL, mapping class và writer đang hoạt động.
2. **Chọn chiến lược tương thích:** reader tạm thời biết thử key mới rồi fallback key cũ; writer mới phải có quy tắc duy nhất để tránh hai bản nguồn sự thật.
3. **Sao chép có điều kiện:** tạo document dưới key mới bằng ngữ nghĩa không ghi đè, xử lý xung đột/ghi đồng thời và quy định cách giữ expiry; không giả định CAS của document cũ trở thành CAS của document mới.
4. **Chuyển reference:** cập nhật các trường `productId` đang trỏ tới key cũ, hoặc duy trì alias/lookup có thời hạn.
5. **Đối chiếu:** kiểm tra số lượng, giá trị nghiệp vụ, link tham chiếu, quyền truy cập và log lỗi.
6. **Dừng đọc key cũ và xóa có kiểm soát:** chỉ sau khi mọi caller đã chuyển và cơ chế rollback được chuẩn bị.

Nếu quá trình copy–update–delete phải nguyên tử theo yêu cầu nghiệp vụ và số document tham gia cho phép, có thể dùng transaction đa document được cấu hình đúng. Nếu quy mô hoặc độ trễ không phù hợp, dùng workflow có idempotency, retry, ghi nhận trạng thái chuyển đổi và bước bù.

**Không nên coi việc sửa trường `id` qua SQL++ là migration key.** SQL++ chỉ sửa nội dung trường JSON khi dùng `SET p.id = ...`; document vẫn nằm dưới key cũ.

### Trường hợp ngược lại: di trú từ JSON id sang document key

Khi import JSON từ hệ thống khác:

~~~json
{"id":"SKU-ARABICA-250", "display_name":"Cà phê"}
~~~

bạn phải quyết định document key ở **lúc ghi**. Có thể chọn `product::coffee250` do ứng dụng tạo và giữ `id` làm mã ngoài, hoặc chọn `product::SKU-ARABICA-250` nếu mã ngoài thật sự ổn định. Đừng tin rằng Couchbase sẽ tự lấy field `id` làm key khi bạn chỉ gửi body JSON mà không cung cấp key/chiến lược tạo key.

Cơ chế `@GeneratedValue` của Spring Data Couchbase có thể tạo key từ thuộc tính hoặc chiến lược khác, nhưng nó là **cấu hình tường minh**; không đồng nghĩa với việc JSON tự sinh khóa từ một trường tên `id`.

## 10. CAS, TTL, index, transaction và reactive API liên hệ thế nào?

| Cơ chế | Thuộc phần nào? | Hệ quả thực hành |
| --- | --- | --- |
| **Document key** | Metadata, duy nhất trong collection | Dùng cho KV/Repository `findById`; bất biến đối với một document hiện có |
| **CAS** | Metadata cho trạng thái document | `@Version` giúp optimistic locking; không phải field body `id` |
| **TTL / expiry** | Thuộc document | Hết hạn xóa document theo key, bất kể body có `id` hay không |
| **Type hint `_class`** | Thông tin mapper thường lưu trong JSON body | Hỗ trợ chọn loại entity, không phải Couchbase key |
| **SQL++ secondary index** | Index dựa trên trường/biểu thức truy vấn | Lọc theo body `id` cần index phù hợp; KV theo key không cần |
| **Transaction** | Phối hợp mutation nhiều document | Không sửa quy tắc identity; cần khi nghiệp vụ yêu cầu commit đồng bộ |
| **Reactive API** | Cách thực hiện I/O | Không tự chuyển `body.id` thành key hay giải quyết reference sai |
| **Bucket/scope/collection** | Không gian lưu trữ và phân quyền | Cùng chuỗi key ở collection khác là document khác |

Nếu vừa sửa body `id` vừa sửa các field khác của **cùng một document**, một mutation document có thể ghi chúng nguyên tử. Nhưng nếu muốn đồng thời cập nhật Product và các Order trỏ tới key, đó là nhiều document và phải có thiết kế nhất quán riêng.

Với SQL++ qua secondary index, dữ liệu truy vấn có thể được quan sát trễ hơn thao tác KV theo key do cơ chế cập nhật index. Nếu vừa ghi document rồi cần nhìn thấy ngay theo `body.id`, đánh giá scan consistency; cách trực tiếp nhất khi đã biết key vẫn là KV theo key.

## 11. Những lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Khả năng xảy ra | Cách kiểm tra |
| --- | --- | --- |
| `findById("SKU-ARABICA-250")` trả rỗng | Truyền body `id` thay vì document key | Xem key thực tế trên UI/SDK hoặc `META(p).id` |
| `p.id` trong SQL++ là MISSING | Body không có trường `id` | Truy vấn `META(p).id`; kiểm tra JSON body |
| Hai document có `body.id` giống nhau | Body `id` không được cưỡng chế unique | Thiết kế key/uniqueness nghiệp vụ, không chỉ tạo index |
| Đổi `body.id` nhưng key không đổi | UPDATE chỉ sửa JSON | Đổi key phải tạo document mới và xử lý reference |
| API trả ID dù body không có `id` | DTO/Jackson lấy ID từ entity metadata | Kiểm tra lớp response, không suy ra từ payload HTTP |
| `findById` đọc sai dữ liệu hoặc không tìm thấy | Sai collection, scope hoặc bucket | Đối chiếu keyspace và key của lệnh |
| SQL++ `SELECT p.*` thiếu key | Query chỉ chọn body | Thêm `META(p).id AS documentKey` |
| Reference Product bị gãy sau migration | Order lưu key cũ nhưng Product đổi key | Kiểm kê và chuyển reference hoặc duy trì alias |
| Ghi đồng thời bị `OptimisticLockingFailureException` | CAS thay đổi sau khi đọc | Đọc lại, kiểm tra nghiệp vụ và retry có giới hạn |
| Sự khác biệt giữa độ dài key cho phép | Khác phiên bản/collection và tính theo byte | Kiểm tra tài liệu Server thực tế; chuẩn hóa key ngắn |
| Truy vấn body `id` chậm | Thiếu index hoặc lựa chọn query không phù hợp | Tạo index đúng workload, dùng `EXPLAIN` |
| Sau khi thay `@Id` dữ liệu cũ không tìm thấy | Đã đổi cách ứng dụng tính key, chưa migrate | Lập lộ trình tương thích/copy/reference |

## 12. Thực hành: phân biệt ba định danh của đơn hàng

**Đề bài:** một hệ thống thương mại điện tử có Order lưu tại `shop.sales.orders`. Người dùng nhìn thấy **mã đơn** `SO-2026-125`, hệ thống thanh toán có **mã giao dịch** `PAY-8821`, còn Couchbase lưu document theo key `order::125`.

Hãy thiết kế Java entity, JSON, cách đọc theo key, cách tìm theo mã đơn và query phân biệt hai giá trị.

### 12.1. Entity đề xuất

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("sales")
@Collection("orders")
public class Order {
    @Id
    private String documentKey;

    @Field("order_code")
    private String orderCode;

    @Field("payment_reference")
    private String paymentReference;

    @Field
    private String status;

    @Version
    private Long version;

    protected Order() {}

    public Order(
            String documentKey,
            String orderCode,
            String paymentReference) {
        if (documentKey == null || documentKey.isBlank()
                || orderCode == null || orderCode.isBlank()) {
            throw new IllegalArgumentException("Định danh không hợp lệ");
        }
        this.documentKey = documentKey;
        this.orderCode = orderCode;
        this.paymentReference = paymentReference;
        this.status = "NEW";
    }

    public String getDocumentKey() { return documentKey; }
    public String getOrderCode() { return orderCode; }
    public String getPaymentReference() { return paymentReference; }
}
~~~

Một JSON body minh họa:

~~~json
{
  "_class": "com.example.shop.sales.Order",
  "order_code": "SO-2026-125",
  "payment_reference": "PAY-8821",
  "status": "NEW"
}
~~~

**Document key `order::125` nằm ở metadata và không có trong body ví dụ.** Mã đơn và mã giao dịch là hai trường nghiệp vụ riêng, có thể thay đổi theo chính sách mà không tự đổi document key. Nếu trong thực tế `Order` được khai báo ở package khác ví dụ, `_class` có thể mang tên class khác hoặc được tùy biến.

### 12.2. Hai đường đọc

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository extends CouchbaseRepository<Order, String> {
    List<Order> findByOrderCode(String orderCode);
}
~~~

~~~java
Order order = orderRepository.findById("order::125")
    .orElseThrow();  // KV theo document key

List<Order> byBusinessCode =
    orderRepository.findByOrderCode("SO-2026-125");
// Query theo field JSON order_code, cần index phù hợp.
~~~

### 12.3. SQL++ phân biệt key và mã đơn

~~~sql
SELECT META(o).id AS documentKey,
       o.order_code AS orderCode,
       o.payment_reference AS paymentReference
FROM `shop`.`sales`.`orders` AS o
USE KEYS "order::125";
~~~

Index cho nhu cầu tìm theo mã đơn:

~~~sql
CREATE INDEX ix_orders_code
ON `shop`.`sales`.`orders`(order_code);
~~~

Chỉ mục này hỗ trợ truy vấn theo `order_code` khi phù hợp với optimizer; nó không tự bảo đảm một mã đơn là duy nhất. Nếu mã đơn bắt buộc duy nhất, hệ thống phải thiết kế ràng buộc ở tầng phát sinh định danh/quy trình ghi.

### 12.4. Câu hỏi tự kiểm tra

1. **Nếu JSON body không có field `id`, document có hợp lệ không?** Có. Key tồn tại độc lập ở metadata.
2. **`@Id private String documentKey` có bắt buộc tạo field `documentKey` trong JSON?** Không; nó gắn với document key.
3. **`findById("SO-2026-125")` có tự tìm theo `order_code` không?** Không; đối số là Couchbase key.
4. **`META(o).id` và `o.id` có giống nhau không?** Không mặc định. Một cái lấy key, một cái lấy field JSON nếu có.
5. **Khi sửa `o.id` bằng SQL++, key của document có đổi không?** Không.
6. **Hai document có cùng `body.id` có tự bị Couchbase từ chối không?** Không, miễn chúng dùng key khác trong cùng collection.
7. **`@Version` liên hệ với body `id` thế nào?** `@Version` ánh xạ CAS metadata và phục vụ chống ghi đè đồng thời; không xác định danh tính.
8. **Làm sao lấy key để xuất dữ liệu từ SQL++?** Chọn `META(alias).id AS documentKey`.
9. **Tại sao khi đọc không thấy key trong JSON?** Vì API có thể chỉ trả body; key thuộc metadata/lời gọi KV.
10. **Dùng reactive repository có làm thay đổi ID storage không?** Không; nó thay giao diện I/O, không thay quy tắc ánh xạ key.

## 13. Checklist trước khi triển khai

- [ ] Phân biệt document key, thuộc tính Java `@Id`, field JSON `id`, mã nghiệp vụ và CAS.
- [ ] Kiểm tra bucket/scope/collection trước khi kết luận một key có tồn tại hay không.
- [ ] Chọn khóa ngắn, ổn định, không nhúng dữ liệu nhạy cảm; xác nhận giới hạn byte theo phiên bản Server.
- [ ] Dùng `@Id` đúng package Spring Data và quy định rõ quy tắc sinh key.
- [ ] Chỉ lưu field JSON `id` khi có mục đích; tránh sao chép key không cần thiết.
- [ ] Dùng `findById`/KV theo key; dùng SQL++/index khi truy vấn một field trong body.
- [ ] Trong SQL++, phân biệt `META(p).id` với `p.id`; kiểm tra `MISSING` và `NULL`.
- [ ] Xử lý tham chiếu và lookup theo đúng key, không nhầm mã bên ngoài.
- [ ] Khi đổi key, có kế hoạch tạo document mới, chuyển reference, idempotency và cleanup.
- [ ] Đo p95/latency và index consistency ở đường query body ID.
- [ ] Kiểm thử round-trip từ entity sang document thực, đọc bằng SDK, repository và SQL++.

## Tài liệu tham khảo chính thức

- [Couchbase Server — Data: Items, Keys, and Values](https://docs.couchbase.com/server/current/learn/data/data.html): định danh key–value, phạm vi collection, giới hạn key theo phiên bản và metadata.
- [Couchbase Server — SQL++ META()](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/metafun.html): `META().id`, CAS và các thuộc tính metadata.
- [Couchbase Server — SQL++ USE KEYS](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/hints.html): chọn document theo key đã biết.
- [Spring Data Couchbase — Modeling Entities](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Id`, `@Document`, mapping giữa Java và JSON.
- [Spring Data Couchbase — Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): KV theo ID và SQL++ khi truy vấn bằng thuộc tính.
- [Spring Data Couchbase — Auto generating keys](https://docs.spring.io/spring-data/couchbase/reference/couchbase/autokeygeneration.html): tạo document key tường minh.
- [Spring Data Couchbase — Query Methods and Reserved Names](https://docs.spring.io/spring-data/couchbase/reference/repositories/query-methods-details.html): ý nghĩa dành riêng của `findById` và các phương thức theo ID.

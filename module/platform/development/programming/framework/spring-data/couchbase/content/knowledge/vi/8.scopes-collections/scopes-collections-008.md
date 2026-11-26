# Tổ chức nhiều loại dữ liệu trong một bucket với Spring Data Couchbase

Một ứng dụng thực tế hiếm khi chỉ lưu một loại document. Hệ thống bán hàng có **khách hàng, sản phẩm, đơn hàng, phiên đăng nhập và sự kiện kiểm toán**; mỗi loại có cách truy vấn, phân quyền và vòng đời khác nhau. Couchbase cho phép đặt tất cả trong **một bucket**, rồi dùng **scope** và **collection** để tổ chức theo nghiệp vụ mà không phải tạo bucket riêng cho từng loại dữ liệu.

Bài này thuộc chương **Scope và Collection** của module `SPRING_DATA_COUCHBASE`. Chúng ta sẽ thiết kế cấu trúc nhiều loại dữ liệu trong một bucket, ánh xạ bằng Spring Data Couchbase, tạo truy vấn SQL++ và chỉ mục, rồi đánh giá tác động đến TTL, CAS, transaction, API reactive và vận hành.

Sau bài học, bạn có thể:

- Phân biệt rõ trách nhiệm của bucket, scope và collection khi lưu nhiều loại document.
- Lựa chọn giữa **mỗi loại một collection** và **nhiều loại chung một collection**.
- Thiết kế key, mapping entity, repository và query phù hợp với từng tập dữ liệu.
- Quyết định nơi đặt chỉ mục, quyền, TTL và giới hạn tách biệt trong cùng bucket.
- Lập kế hoạch thay đổi cấu trúc dữ liệu mà không làm ứng dụng đọc nhầm collection.

## 1. Ba tầng tổ chức dữ liệu

Trong Couchbase Server, đường dẫn thông dụng tới một tập document có dạng:

```text
<bucket>.<scope>.<collection>
```

Ví dụ `shop.commerce.orders` nghĩa là collection `orders` trong scope `commerce` thuộc bucket `shop`.

| Tầng | Vai trò | Đặc tính cần hiểu |
| --- | --- | --- |
| **Bucket** | Không gian lưu trữ cấp cao | Có cấu hình tài nguyên và nhiều chính sách cấp bucket; các collection trong cùng bucket chia sẻ các tài nguyên đó. |
| **Scope** | Nhóm collection theo ranh giới logic | Thuận tiện quản lý miền nghiệp vụ, tổ chức quyền và ngữ cảnh truy vấn. |
| **Collection** | Tập document để ứng dụng đọc/ghi | Có không gian key riêng, có thể có chỉ mục, quyền và cấu hình thời hạn hết hạn phù hợp. |
| **Document** | Bản ghi JSON hoặc giá trị được lưu theo ID | Không bị ép một schema cứng chỉ vì cùng collection. |

Bucket được tạo sẽ có scope `_default` và collection `_default` bên trong. Những collection do ứng dụng tạo có thể nằm trong scope `_default` hoặc scope tự tạo. Một scope tự tạo **không có** collection đặc biệt tên `_default`.

Ví dụ, `shop._default._default` là nơi mặc định; `shop.commerce.orders` là nơi rõ ràng cho đơn hàng. Hai collection có thể cùng chứa key `order::1001` mà **không** đại diện cho một document duy nhất.

## 2. Thiết kế mẫu: một bucket cho hệ thống bán hàng

Hãy xét ứng dụng gồm bốn nhóm chức năng: bán hàng, danh mục sản phẩm, đăng nhập và vận hành. Một phương án cấu trúc:

```text
bucket: shop
├── scope: commerce
│   ├── collection: customers
│   ├── collection: orders
│   └── collection: carts
├── scope: catalog
│   ├── collection: products
│   └── collection: categories
├── scope: identity
│   └── collection: sessions
└── scope: operations
    ├── collection: audit_events
    └── collection: jobs
```

Mỗi tầng phục vụ một quyết định:

- `shop` là bucket chung, tránh việc tạo một bucket mới cho mọi entity.
- `commerce` và `catalog` là hai miền nghiệp vụ có truy vấn và nhóm bảo trì khác nhau.
- `identity` chứa session có vòng đời ngắn, cần quyền truy cập hẹp.
- `operations` lưu sự kiện và trạng thái công việc phục vụ giám sát, xử lý sự cố.
- Các collection `orders`, `products`, `sessions` tách được chỉ mục và một số chính sách cho từng loại dữ liệu.

Bảng quyết định ban đầu:

| Loại document | Keyspace đề xuất | Truy cập thường gặp | Vòng đời |
| --- | --- | --- | --- |
| Khách hàng | `shop.commerce.customers` | Tìm theo ID, email | Dài hạn; lưu ý dữ liệu cá nhân. |
| Đơn hàng | `shop.commerce.orders` | ID, customerId, createdAt, status | Dài hạn; thường cần lưu lịch sử. |
| Giỏ hàng | `shop.commerce.carts` | Theo customerId hoặc cartId | Có thể hết hạn sau thời gian không hoạt động. |
| Sản phẩm | `shop.catalog.products` | SKU, categoryId, trạng thái bán | Cập nhật thường xuyên, nhiều truy vấn lọc. |
| Phiên đăng nhập | `shop.identity.sessions` | Đọc/ghi theo session ID | Ngắn hạn, dùng expiry. |
| Sự kiện kiểm toán | `shop.operations.audit_events` | Theo subjectId, thời điểm, action | Theo chính sách lưu giữ và kiểm toán. |

Đây là **một phương án**, không phải quy định Couchbase rằng mỗi entity bắt buộc có một collection. Thiết kế tốt dựa trên nhu cầu truy cập, bảo mật, chỉ mục và vòng đời.

## 3. Hai chiến lược tổ chức nhiều loại document

### 3.1. Một collection cho mỗi nhóm document

Với cách này, `OrderDocument` lưu ở `commerce.orders`, `CustomerDocument` ở `commerce.customers`, `ProductDocument` ở `catalog.products`.

**Ưu điểm:**

- Câu SQL++ chỉ rõ nguồn dữ liệu theo nghiệp vụ.
- Chỉ mục theo trường của từng loại, tránh index không cần thiết cho các loại khác.
- Có thể cấp quyền theo scope/collection tùy role.
- Dễ quản lý TTL của nhóm dữ liệu có vòng đời khác nhau.
- Key giống nhau ở các collection không đụng nhau.

**Hạn chế:**

- Cần tạo, quản lý và triển khai nhiều scope/collection/index.
- Các truy vấn cần dữ liệu từ nhiều collection phải chỉ rõ từng keyspace và thiết kế truy vấn hoặc luồng KV phù hợp.
- Nếu tạo collection riêng cho mọi đối tượng nhỏ, số tài nguyên và công sức quản trị có thể tăng không cần thiết.

### 3.2. Nhiều loại document trong cùng một collection

Couchbase không áp đặt schema cố định cho collection. Có thể đặt đơn hàng và hóa đơn vào một collection tên `commerce.records`:

```json
{
  "type": "order",
  "customerId": "customer::42",
  "status": "CONFIRMED",
  "total": 1250000
}
```

```json
{
  "type": "invoice",
  "orderId": "order::1001",
  "invoiceNumber": "INV-2026-001",
  "paid": true
}
```

Khi truy vấn, cần xác định loại:

```sql
SELECT META(r).id AS documentId, r.status, r.customerId
FROM `shop`.`commerce`.`records` AS r
WHERE r.type = "order" AND r.customerId = "customer::42";
```

**Ưu điểm:** ít tài nguyên quản trị hơn, phù hợp khi các loại document có yêu cầu truy cập và vòng đời gần nhau hoặc được xử lý chung.

**Nhược điểm:** phải phân biệt loại document chặt chẽ; các index, quyền hoặc TTL theo collection khó tách biệt nếu những loại dữ liệu trong đó có nhu cầu khác nhau. Truy vấn và mapping có thể phức tạp khi cùng collection chứa nhiều schema.

Ngoài field nghiệp vụ `type`, Spring Data Couchbase có thể ghi metadata phân biệt Java entity (thường là `_class`) và dùng nó trong các truy vấn do repository sinh. **Không nên coi field `type` do ứng dụng tự đặt là tự động thay thế metadata mapping của Spring Data.** Khi đọc/ghi từ SDK thô hoặc di chuyển document, cần bảo đảm các field mà tầng truy cập Spring Data mong đợi.

### 3.3. Chọn chiến lược nào?

| Tiêu chí | Nhiều collection | Chung một collection |
| --- | --- | --- |
| Truy vấn thường xuyên theo loại riêng | Dễ giới hạn keyspace và index theo loại | Cần điều kiện lọc loại thích hợp. |
| Vai trò truy cập khác nhau | Phân quyền ở cấp collection thuận lợi | Quyền collection không tách các loại document. |
| TTL khác nhau đáng kể | Có thể cấu hình theo collection | Chủ yếu điều khiển expiry trên từng document. |
| Ít loại, dữ liệu quy mô nhỏ | Có thể tăng số tài nguyên cần quản lý | Đơn giản hơn nếu schema/quyền tương đồng. |
| Cần thao tác liên quan nhiều loại | Có thể cần JOIN hoặc nhiều lời gọi KV | Cùng tập dữ liệu nhưng vẫn phải xử lý quan hệ. |
| Tách nhóm vận hành và ownership | Rõ ràng theo domain/team | Dễ phát sinh phụ thuộc chung. |

Một quy tắc thực hành: **tách collection khi sự khác biệt về truy cập, chỉ mục, quyền hoặc vòng đời là đáng kể**. Không tách chỉ vì mỗi Java class có tên khác nhau.

## 4. Thiết kế key: không gian key độc lập nhưng vẫn cần quy ước

Trong một collection, document ID phải duy nhất. Hai collection khác nhau có thể có ID trùng nhau. Dù vậy, quy ước key vẫn giúp debug và liên kết dữ liệu.

Ví dụ:

```text
commerce.customers
  customer::42
  customer::43

commerce.orders
  order::1001
  order::1002

catalog.products
  product::SKU-123

identity.sessions
  session::opaque-identifier
```

Các tiền tố như `order::` không phải cú pháp bắt buộc của Couchbase. Chúng hữu ích khi ứng dụng cần phân biệt kiểu ID trong log, hệ thống import/export hoặc khi nhiều loại document được lưu chung một collection.

**Tách biệt hai khái niệm:**

1. `keyspace` xác định nơi lưu: `shop.commerce.orders`.
2. `document ID` xác định document trong nơi đó: `order::1001`.

Không nên dùng document key để giả định entity tồn tại trong toàn bucket. Muốn đọc một document, cần biết đúng **collection + ID**.

### Quan hệ giữa các document

Đơn hàng có thể lưu ID khách hàng thay vì nhúng toàn bộ thông tin khách:

```json
{
  "customerId": "customer::42",
  "status": "CONFIRMED",
  "items": [
    { "productId": "product::SKU-123", "quantity": 2 }
  ]
}
```

Cách này giữ document đơn hàng gọn và tránh lặp thông tin khách hàng thay đổi thường xuyên. Nhưng nó **không tự tạo khóa ngoại** như trong cơ sở dữ liệu quan hệ. Ứng dụng phải xác định cách kiểm tra tham chiếu, cập nhật dữ liệu nhất quán và xử lý trường hợp document liên quan không còn tồn tại.

Với những dữ liệu được đọc cùng nhau và ít thay đổi độc lập, **nhúng (embedding)** có thể phù hợp hơn lưu tham chiếu. Chọn dựa trên mẫu truy cập chứ không áp dụng một quy tắc duy nhất.

## 5. Mapping mỗi loại dữ liệu bằng Spring Data Couchbase

Spring Data Couchbase hỗ trợ `@Scope` và `@Collection` để chỉ rõ nơi lưu theo entity. Import chính xác là:

```java
import org.springframework.data.couchbase.repository.Scope;
import org.springframework.data.couchbase.repository.Collection;
```

Ví dụ các entity bên dưới giả sử bucket đã cấu hình là `shop`.

### 5.1. Entity đơn hàng

```java
import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.repository.Scope;
import org.springframework.data.couchbase.repository.Collection;

@Document
@Scope("commerce")
@Collection("orders")
public class OrderDocument {

    @Id
    private String id;

    private String customerId;
    private String status;
    private Instant createdAt;

    public OrderDocument() {}

    // Constructor, getters và setters cho các field được lược bỏ.
}
```

### 5.2. Entity khách hàng

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.repository.Scope;
import org.springframework.data.couchbase.repository.Collection;

@Document
@Scope("commerce")
@Collection("customers")
public class CustomerDocument {

    @Id
    private String id;

    private String displayName;
    private String email;

    public CustomerDocument() {}

    // Getters và setters được lược bỏ.
}
```

### 5.3. Entity sản phẩm

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.repository.Scope;
import org.springframework.data.couchbase.repository.Collection;

@Document
@Scope("catalog")
@Collection("products")
public class ProductDocument {

    @Id
    private String id;

    private String categoryId;
    private String displayName;
    private boolean active;

    public ProductDocument() {}

    // Getters và setters được lược bỏ.
}
```

Với mapping này, ba loại document nằm tại:

| Entity | Bucket | Scope | Collection |
| --- | --- | --- | --- |
| `OrderDocument` | `shop` | `commerce` | `orders` |
| `CustomerDocument` | `shop` | `commerce` | `customers` |
| `ProductDocument` | `shop` | `catalog` | `products` |

Lưu ý annotation **không tạo scope hoặc collection trên server**. Trước khi chạy ứng dụng, cần chuẩn bị tài nguyên và quyền truy cập phù hợp.

### 5.4. Repository độc lập theo loại

```java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByCustomerId(String customerId);

    List<OrderDocument> findByStatus(String status);
}

public interface CustomerRepository
        extends CouchbaseRepository<CustomerDocument, String> {
}

public interface ProductRepository
        extends CouchbaseRepository<ProductDocument, String> {

    List<ProductDocument> findByCategoryId(String categoryId);
}
```

Các repository trên sử dụng metadata entity để định tuyến tới các collection khác nhau khi không có ghi đè có ưu tiên cao hơn. Việc có ba repository **không yêu cầu ba bucket**.

Các method `findById` thường dùng Key/Value (KV) khi đã biết ID. Các finder như `findByCustomerId` thường sinh truy vấn SQL++ và cần chỉ mục phù hợp trên collection đích.

## 6. Cấu hình bucket chung và lựa chọn scope

Một cấu hình Spring Boot tối giản cho bucket chung:

```yaml
spring:
  couchbase:
    connection-string: couchbase://localhost
  data:
    couchbase:
      bucket-name: shop
```

Thông tin username/password cần được cung cấp qua cấu hình bảo mật hoặc môi trường chạy; ví dụ trên chỉ thể hiện phần liên quan đến cấu trúc dữ liệu.

Nếu phần lớn entity thuộc scope `commerce`, bạn có thể đặt scope mặc định:

```yaml
spring:
  data:
    couchbase:
      bucket-name: shop
      scope-name: commerce
```

Khi đó, entity **không có `@Scope`** có thể lấy scope từ cấu hình nền. Entity có `@Scope("catalog")` vẫn dùng scope `catalog` vì annotation có độ ưu tiên cao hơn cấu hình chung.

Điều này cho phép ứng dụng sử dụng **một bucket** nhưng nhiều scope, mà không phải đổi tên bucket theo từng loại dữ liệu.

### Thứ tự ưu tiên khi có nhiều nơi lựa chọn

Spring Data Couchbase có cơ chế định tuyến scope/collection với thứ tự ưu tiên từ cao xuống thấp:

1. `inScope()/inCollection()` của fluent operation trên Template.
2. `withScope()/withCollection()` của đối tượng Template/repository hỗ trợ.
3. Annotation trên phương thức repository.
4. Annotation trên repository interface.
5. Annotation trên entity.
6. Cấu hình mặc định.

Vì thế, không thể chỉ nhìn `application.yml` rồi kết luận mọi document đều được lưu vào cùng scope.

## 7. CouchbaseTemplate khi cần truy cập nhiều collection trong một service

Trong nhiều trường hợp, repository đủ cho CRUD; khi cần kiểm soát rõ từng thao tác, `CouchbaseTemplate` có thể chọn scope/collection bằng fluent API.

Ví dụ đọc một đơn hàng:

```java
OrderDocument order = couchbaseTemplate
    .findById(OrderDocument.class)
    .inScope("commerce")
    .inCollection("orders")
    .one("order::1001");
```

Đọc một sản phẩm:

```java
ProductDocument product = couchbaseTemplate
    .findById(ProductDocument.class)
    .inScope("catalog")
    .inCollection("products")
    .one("product::SKU-123");
```

Hai lời gọi dùng **cùng Template**, cùng bucket `shop`, nhưng đọc hai keyspace khác nhau. API này phù hợp khi một service phải điều phối nhiều nhóm dữ liệu hoặc khi cần chọn collection ở runtime.

Một repository mở rộng `DynamicProxyable<RepositoryType>` cũng có thể lựa chọn động bằng `withScope()/withCollection()`. Tuy nhiên, nếu entity luôn thuộc collection cố định, annotation trên entity hoặc repository thường dễ theo dõi hơn.

## 8. SQL++ và chỉ mục theo collection

Khi tách nhiều loại document thành collection riêng, mỗi truy vấn SQL++ phải trỏ tới đúng keyspace.

### 8.1. Truy vấn đơn hàng theo khách hàng

```sql
SELECT META(o).id AS documentId,
       o.customerId,
       o.status,
       o.createdAt
FROM `shop`.`commerce`.`orders` AS o
WHERE o.customerId = "customer::42"
ORDER BY o.createdAt DESC
LIMIT 20;
```

Một chỉ mục khởi đầu có thể là:

```sql
CREATE INDEX ix_orders_customer_created
ON `shop`.`commerce`.`orders`(customerId, createdAt DESC);
```

Chỉ mục thực tế cần được điều chỉnh dựa trên câu truy vấn cuối cùng, kế hoạch thực thi `EXPLAIN` và điều kiện lọc kiểu entity mà Spring Data có thể thêm.

### 8.2. Truy vấn sản phẩm theo danh mục

```sql
SELECT META(p).id AS productId,
       p.displayName,
       p.categoryId
FROM `shop`.`catalog`.`products` AS p
WHERE p.categoryId = "category::electronics"
  AND p.active = TRUE;
```

Chỉ mục phục vụ loại truy vấn này:

```sql
CREATE INDEX ix_products_category_active
ON `shop`.`catalog`.`products`(categoryId, active);
```

Không có lý do bắt buộc phải đưa field `customerId` của đơn hàng vào index của `catalog.products`; mỗi collection có tập index riêng phục vụ các truy vấn thực tế của nó.

### 8.3. Truy vấn nhiều collection

Khi báo cáo cần dữ liệu từ cả đơn hàng và khách hàng, có thể cân nhắc JOIN SQL++, hai lời gọi KV trong ứng dụng hoặc một mô hình đọc tổng hợp riêng.

Ví dụ về ý tưởng JOIN theo key khách hàng:

```sql
SELECT META(o).id AS orderId,
       o.status,
       c.displayName AS customerName
FROM `shop`.`commerce`.`orders` AS o
JOIN `shop`.`commerce`.`customers` AS c
  ON KEYS o.customerId
WHERE o.status = "CONFIRMED";
```

Câu này dùng key khách hàng ở `o.customerId` để lấy document từ collection `customers`. Khi triển khai, kiểm tra cú pháp, quyền đọc và kế hoạch truy vấn của phiên bản Couchbase đang dùng. Không mặc định rằng JOIN từ nhiều collection luôn nhanh hoặc luôn là lựa chọn tốt nhất.

**Quy tắc:** tạo index theo collection được truy vấn. Index trên `shop.commerce.orders` không tự phục vụ `shop.catalog.products` hay `shop.commerce.customers`.

## 9. TTL: các loại dữ liệu có thời hạn sống khác nhau

Nhiều loại dữ liệu trong cùng bucket thường có yêu cầu hết hạn khác nhau:

| Collection | Nhu cầu TTL | Gợi ý |
| --- | --- | --- |
| `commerce.orders` | Giữ lâu để phục vụ nghiệp vụ | Không áp dụng expiry ngắn tùy tiện. |
| `commerce.carts` | Giỏ không hoạt động có thể hết hạn | Dùng expiry phù hợp nghiệp vụ, cân nhắc collection `maxTTL`. |
| `identity.sessions` | Phiên đăng nhập thường ngắn hạn | Đặt expiry khi ghi hoặc chính sách collection phù hợp. |
| `operations.audit_events` | Theo chính sách lưu giữ | Xác định retention trước khi áp dụng TTL. |

Couchbase cho phép đặt `maxTTL` ở **bucket** và **collection**; scope **không có** thuộc tính `maxTTL`. Trên một số cấu hình, giá trị collection `maxTTL = 0` nghĩa là kế thừa chính sách bucket; `-1` có thể dùng để ngăn kế thừa giá trị bucket theo khả năng của phiên bản. Một `maxTTL` khác 0 có thể đặt giới hạn trên cho expiry của document. Vì vậy cần kiểm tra chính sách thực tế thay vì suy rằng “0 nghĩa là mọi document chắc chắn không hết hạn”.

Ví dụ Java SDK đặt expiry khi ghi một session vào collection đã tồn tại:

```java
import java.time.Duration;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import static com.couchbase.client.java.kv.UpsertOptions.upsertOptions;

Collection sessions = cluster
    .bucket("shop")
    .scope("identity")
    .collection("sessions");

sessions.upsert(
    "session::opaque-id",
    JsonObject.create()
        .put("userId", "customer::42")
        .put("state", "ACTIVE"),
    upsertOptions().expiry(Duration.ofMinutes(30))
);
```

Đoạn mã dùng Java SDK để minh họa expiry tại thời điểm ghi. Nếu hệ thống dùng Spring Data repository hoặc Template, hãy thiết kế cách đặt expiry phù hợp với API đó và chính sách collection; tránh cho rằng chỉ tách collection đã tự đặt thời hạn sống.

**Lưu ý:** hết hạn document là một cơ chế quản lý vòng đời; với dữ liệu kiểm toán hoặc nghiệp vụ quan trọng, cần cân nhắc yêu cầu lưu giữ pháp lý và khôi phục trước khi cho phép tự xóa.

## 10. Phân quyền và mức độ cô lập trong một bucket

Couchbase hỗ trợ cấp quyền theo phạm vi thích hợp, bao gồm scope và collection, tùy role của tài khoản ứng dụng. Khi dùng một bucket chung, bạn có thể thiết kế:

| Dịch vụ | Collection cần truy cập | Phạm vi quyền nên xem xét |
| --- | --- | --- |
| Order Service | `commerce.orders`, có thể cần đọc `commerce.customers` | Chỉ những thao tác, collection cần thiết. |
| Catalog Service | `catalog.products`, `catalog.categories` | Quyền đọc/ghi theo nghiệp vụ danh mục. |
| Identity Service | `identity.sessions` | Quyền KV/Query cần thiết cho session. |
| Audit Reader | `operations.audit_events` | Thường chỉ đọc/truy vấn đối với vai trò xem báo cáo. |

**Collection giúp tạo ranh giới phân quyền logic**, nhưng không tự mang lại cách ly tài nguyên vật lý. Nếu cấp role quá rộng ở cấp bucket, tài khoản vẫn có thể đọc các collection ngoài nhu cầu của dịch vụ.

Với hệ thống đa tenant, có thể cân nhắc scope theo tenant khi số tenant và cách vận hành cho phép. Nếu có quá nhiều tenant hoặc thường xuyên tạo/xóa tenant, việc tạo collection riêng cho mọi tenant có thể tăng mạnh tài nguyên quản trị và vấp giới hạn phiên bản. Khi đó cần đánh giá mô hình dùng chung collection với `tenantId`, index và kiểm tra authorization chặt chẽ ở ứng dụng.

**Không nhận trực tiếp tên scope/collection tùy ý từ request mà không kiểm tra quyền.** Lựa chọn keyspace ở runtime phải xuất phát từ ánh xạ được hệ thống kiểm soát.

## 11. CAS, transaction và tính nhất quán giữa các loại dữ liệu

### 11.1. CAS nằm trên từng document

Couchbase dùng CAS (*Compare-And-Swap*) để hỗ trợ phát hiện xung đột khi cập nhật document. Trong Spring Data, `@Version` là một cơ chế cần tìm hiểu để quản lý optimistic locking.

Ví dụ ý tưởng:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.repository.Scope;
import org.springframework.data.couchbase.repository.Collection;

@Document
@Scope("commerce")
@Collection("orders")
public class OrderDocument {

    @Id
    private String id;

    @Version
    private long version;

    private String status;

    // Constructor, getters và setters được lược bỏ.
}
```

Mỗi document được quản lý trong collection của chính nó. Hai document cùng key ở hai collection không chia sẻ CAS hay trạng thái version.

### 11.2. Transaction không tự phát sinh khi tách collection

Đôi khi việc đặt hàng liên quan nhiều document: đơn hàng mới, giỏ hàng, lượng hàng tồn. Việc ghi lần lượt vào nhiều collection bằng các lệnh `save` độc lập **không tự thành một transaction**.

Nếu nghiệp vụ đòi hỏi các thao tác phải nguyên tử, cần chọn API transaction Couchbase phù hợp và xem xét điều kiện hỗ trợ của Spring Data/SDK, vấn đề retry và giới hạn hiệu năng. Việc bố trí nhiều collection không thay thế được thiết kế transaction.

### 11.3. Query SQL++ có thể chậm thấy dữ liệu mới

KV `findById` thường đọc trực tiếp theo key, còn finder theo thuộc tính sử dụng SQL++ và chỉ mục. Sau một lệnh ghi thành công, index có thể cần thời gian để cập nhật; truy vấn SQL++ sau ghi có thể chưa thấy document mới với mức scan consistency mặc định.

Cần phân biệt ba nguyên nhân khác nhau:

1. **Sai collection**: truy vấn nhắm tới keyspace khác nơi document được ghi.
2. **Thiếu index/quyền**: Query Service không thực hiện được hoặc dùng kế hoạch không phù hợp.
3. **Độ trễ index**: document đã có trong KV nhưng chưa được nhìn thấy theo consistency của truy vấn.

Việc tách collection làm cho bước kiểm tra keyspace càng cần thiết.

## 12. Dùng repository reactive khi nhiều loại dữ liệu cùng bucket

Spring Data Couchbase hỗ trợ `ReactiveCouchbaseRepository` để ứng dụng làm việc theo Reactor.

Ví dụ repository session:

```java
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;
import org.springframework.data.couchbase.repository.Scope;
import org.springframework.data.couchbase.repository.Collection;
import reactor.core.publisher.Flux;

@Scope("identity")
@Collection("sessions")
public interface SessionRepository
        extends ReactiveCouchbaseRepository<SessionDocument, String> {

    Flux<SessionDocument> findByUserId(String userId);
}
```

Với entity tương ứng:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Document;

@Document
public class SessionDocument {

    @Id
    private String id;

    private String userId;
    private String state;

    public SessionDocument() {}

    // Getters và setters được lược bỏ.
}
```

Repository reactive vẫn phải có scope/collection hợp lệ và index phù hợp cho query finder. Trả về `Mono` hoặc `Flux` không khiến Couchbase tự tạo collection hay thay đổi TTL.

Một ứng dụng có thể kết hợp **repository đồng bộ** cho nghiệp vụ truyền thống và **API reactive** cho các luồng xử lý bất đồng bộ, nhưng cần đặt ranh giới rõ ràng; không nên gọi `block()` trong event loop của ứng dụng reactive.

## 13. Mỗi collection không phải một bucket thu nhỏ

Tạo nhiều collection trong cùng bucket có lợi cho tổ chức logic, nhưng cần hiểu phạm vi cô lập.

**Các phần có thể khác nhau giữa collection** gồm tên keyspace, tập document, index, quyền truy cập theo collection, và một số chính sách expiry/replication tùy phiên bản, khả năng cấu hình.

**Các phần vẫn thuộc mức bucket hoặc cluster** gồm nhiều tài nguyên lưu trữ chung và chính sách vận hành cấp bucket. Collection không tự có quota bộ nhớ, cấu hình replica, mức ưu tiên tài nguyên hoặc chính sách backup độc lập tương đương một bucket.

Vì vậy, nếu một workload cần:

- Cấu hình lưu trữ hoặc tài nguyên tách biệt rõ;
- Khả năng kiểm soát tác động của tải nặng từ ứng dụng khác;
- Chính sách quản trị/bảo mật và chu kỳ vận hành tách ở cấp bucket;

thì cần đánh giá tạo **bucket riêng** thay vì chỉ tạo thêm scope hoặc collection. Ngược lại, nhiều entity cùng yêu cầu hạ tầng tương tự thường có thể chia sẻ một bucket và tách theo collection.

### Vấn đề giới hạn tài nguyên

Couchbase có giới hạn về số scope/collection và tài nguyên liên quan; các mức giới hạn có thể phụ thuộc phiên bản/phân phối và môi trường. Không thiết kế theo giả định rằng có thể tạo vô hạn collection. Với hệ thống nhiều tenant, hãy kiểm tra giới hạn chính thức của phiên bản đang chạy trước khi chọn cách “mỗi tenant một collection”.

## 14. Chuẩn bị triển khai và quan sát vận hành

### 14.1. Tạo tài nguyên trước khi chạy ứng dụng

Mapping `@Scope` và `@Collection` **không tự tạo** resource. Người vận hành có thể tạo scope/collection qua Console, SDK quản trị, CLI, REST hoặc SQL++.

Ví dụ DDL minh họa:

```sql
CREATE SCOPE `shop`.`commerce`;
CREATE COLLECTION `shop`.`commerce`.`orders`;
CREATE COLLECTION `shop`.`commerce`.`customers`;

CREATE SCOPE `shop`.`catalog`;
CREATE COLLECTION `shop`.`catalog`.`products`;
```

Các lệnh này giả định bucket `shop` đã tồn tại và tài khoản thực thi có quyền quản trị. Trong quy trình deployment, cần kiểm tra tài nguyên hiện có, xử lý trường hợp đã tạo trước đó và tránh tự chạy DDL ở mỗi lần ứng dụng khởi động.

### 14.2. Quy trình triển khai đề xuất

1. **Chốt mô hình:** tài liệu hóa bucket, scope, collection, owner, loại document, key pattern và retention.
2. **Provision resource:** tạo scope/collection theo quy trình quản trị và môi trường.
3. **Cấp quyền:** service account chỉ có quyền cần thiết trên đúng keyspace.
4. **Tạo index:** dựa trên truy vấn SQL++ thực tế của từng collection.
5. **Cập nhật code:** khai báo entity, repository, Template và query theo keyspace tương ứng.
6. **Kiểm thử:** KV theo key, finder SQL++, expiry, quyền, CAS và các luồng nhiều document.
7. **Quan sát:** theo dõi kích thước dữ liệu, chỉ mục, độ trễ truy vấn, lỗi quyền và truy cập nhầm collection.

Không nên đặt tên collection phụ thuộc tên class Java tạm thời nếu model nghiệp vụ có thể tồn tại lâu hơn thiết kế mã nguồn hiện tại. Dùng tên ổn định và có quy ước.

## 15. Khi cần tách dữ liệu từ collection cũ

Giả sử phiên bản đầu lưu khách hàng, đơn hàng và sản phẩm chung trong `shop._default._default`, phân biệt bằng field `type`. Sau đó, muốn chuyển sang ba collection nghiệp vụ.

**Các bước quan trọng:**

1. **Kiểm kê dữ liệu cũ:** xác định document theo loại, key, metadata Spring Data, expiry và những nơi đang đọc/ghi.
2. **Tạo keyspace đích:** `commerce.orders`, `commerce.customers`, `catalog.products`.
3. **Chuẩn bị index, quyền và TTL** tại từng collection mới.
4. **Chọn phương pháp migrate:** công cụ ETL, SDK, SQL++ hoặc pipeline tương ứng; bảo toàn key, nội dung và thuộc tính cần giữ.
5. **Kiểm soát ghi đồng thời:** nếu ứng dụng vẫn tiếp tục ghi, cần cơ chế dual-write, đồng bộ, chuyển đổi theo giai đoạn hoặc khoảng dừng ghi phù hợp nghiệp vụ.
6. **Đổi mapping:** cập nhật `@Scope/@Collection`, repository, Template và các câu SQL++ có keyspace viết cứng.
7. **Đối soát:** kiểm tra số lượng, lấy mẫu nội dung, tập key, index, query, quyền và hành vi expiry.
8. **Dọn dữ liệu cũ có kiểm soát:** thực hiện khi có phương án rollback và đã xác nhận các luồng ứng dụng không còn phụ thuộc collection cũ.

**Đổi annotation không phải thao tác migrate.** Nếu cùng một key hiện diện ở collection cũ và mới, đây vẫn là hai document độc lập.

## 16. Những lỗi thiết kế thường gặp

| Dấu hiệu | Nguyên nhân thường gặp | Giải pháp |
| --- | --- | --- |
| Hầu hết document nằm trong `_default._default` dù có nhiều entity. | Mapping thiếu collection hoặc đang dùng cấu hình mặc định. | Xác định keyspace dự kiến, thêm mapping rõ ràng khi cần. |
| `findById` không tìm thấy ID có trên Console. | Đang đọc sai scope/collection. | So sánh đầy đủ bucket.scope.collection và key. |
| Query finder của Order chạy, nhưng Product bị lỗi index. | Chưa tạo index trên `catalog.products`. | Xem câu SQL++ thực tế và tạo index tại đúng collection. |
| Session không hết hạn như mong muốn. | Chưa đặt expiry hoặc hiểu sai cách kế thừa `maxTTL`. | Kiểm tra expiry document, collection và bucket. |
| Service đọc được dữ liệu nghiệp vụ khác. | Role cấp quá rộng, dù collection đã tách. | Rà soát RBAC và quyền ứng dụng. |
| Có nhiều collection nhưng hiệu năng vẫn ảnh hưởng nhau. | Các collection dùng chung tài nguyên bucket/cluster. | Xem hạ tầng, workload, index, cân nhắc bucket riêng nếu cần. |
| Dữ liệu cũ mất khỏi kết quả sau khi đổi annotation. | Đổi mapping mà chưa chuyển document. | Lập kế hoạch migration và đối soát dữ liệu. |
| Một collection chứa nhiều schema khiến query kết quả sai. | Thiếu điều kiện phân biệt loại hoặc metadata không nhất quán. | Dùng type discriminator và mapping/index được kiểm chứng. |
| Dùng một collection cho mọi tenant nhưng thiếu kiểm tra tenantId. | Không có ranh giới authorization theo tenant. | Áp dụng kiểm soát tenant ở ứng dụng và quyền phù hợp. |

## 17. Bài tập tình huống

**Tình huống:** Bạn cần thiết kế lưu trữ cho một ứng dụng đặt hàng có 100.000 đơn hàng, 10.000 sản phẩm, phiên đăng nhập ngắn hạn và dữ liệu kiểm toán. Dự án dùng một bucket `shop`.

**Câu 1:** Có bắt buộc tạo bốn bucket tương ứng bốn loại dữ liệu không?

**Đáp án:** Không. Có thể đặt các loại dữ liệu trong cùng bucket và tách bằng scope/collection, nếu nhu cầu tài nguyên và quản trị cấp bucket phù hợp.

**Câu 2:** Vì sao session và đơn hàng nên cân nhắc hai collection riêng?

**Đáp án:** Vòng đời và quyền truy cập khác nhau; session thường cần expiry ngắn, đơn hàng cần giữ lâu hơn và có chỉ mục nghiệp vụ riêng.

**Câu 3:** `shop.commerce.orders` và `shop.catalog.products` đều chứa key `item::1`. Có xung đột không?

**Đáp án:** Không. Key chỉ phải duy nhất trong từng collection. Tuy vậy, nên có quy ước ID rõ ràng để tránh nhầm khi vận hành.

**Câu 4:** Nếu `OrderRepository.findByCustomerId(...)` không chạy sau khi tách collection, kiểm tra gì?

**Đáp án:** Mapping scope/collection, câu SQL++ do repository sinh ra, quyền và index trên `shop.commerce.orders`.

**Câu 5:** Đặt `maxTTL` cho scope `identity` có phải cách chính xác để mọi session hết hạn không?

**Đáp án:** Không. Scope không hỗ trợ `maxTTL`. Phải đặt expiry trên document hoặc chính sách `maxTTL` ở collection/bucket phù hợp.

**Câu 6:** Đổi `@Collection("orders")` trên entity có tự đưa document cũ từ `_default._default` sang `commerce.orders` không?

**Đáp án:** Không. Phải chuyển dữ liệu và kiểm tra độc lập.

## Kết luận

**Tổ chức nhiều loại dữ liệu trong một bucket** là bài toán thiết kế dựa trên nhu cầu nghiệp vụ: bucket cung cấp không gian lưu trữ chung, scope nhóm các collection, còn collection tạo ranh giới cho tập document, index và quyền truy cập. Trong Spring Data Couchbase, `@Scope`, `@Collection`, repository và `CouchbaseTemplate` phải thống nhất với keyspace đã provision.

Giữ nhiều loại document chung một collection có thể hợp lý nếu chúng có kiểu truy cập và vòng đời tương đồng. Tách collection hữu ích khi cần chính sách, chỉ mục, phân quyền hoặc tính rõ ràng khác nhau. Dù chọn cách nào, đừng nhầm ranh giới logic của collection với cách ly tài nguyên cấp bucket; hãy kiểm tra kỹ TTL, CAS, giao dịch, reactive và quá trình chuyển dữ liệu khi hệ thống phát triển.

## Tài liệu tham khảo

- [Couchbase — Scopes and Collections](https://docs.couchbase.com/server/current/learn/data/scopes-and-collections.html): phân cấp bucket/scope/collection, quy tắc đặt tên, RBAC và giới hạn vận hành.
- [Couchbase — Expiration](https://docs.couchbase.com/server/current/learn/data/expiration.html): document expiry, kế thừa `maxTTL` ở bucket/collection và giới hạn của scope.
- [Spring Data Couchbase — Collection Support](https://docs.spring.io/spring-data/couchbase/reference/couchbase/collections.html): mapping scope/collection bằng annotation và API của Template.
- [Spring Data Couchbase — Couchbase Repositories](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): KV theo ID, SQL++ finder và yêu cầu chỉ mục.
- [Couchbase — SQL++ Language Reference](https://docs.couchbase.com/server/current/n1ql/n1ql-language-reference/index.html): cú pháp query, keyspace và cách truy vấn dữ liệu.


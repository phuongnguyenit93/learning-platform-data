# Bucket, scope và collection trong tổ chức dữ liệu Couchbase

> **Chương:** Nền tảng Couchbase  
> **Ngữ cảnh:** Spring Data Couchbase — xây dựng tầng truy cập dữ liệu bằng document mapping, repository, CouchbaseTemplate và SQL++; chuẩn bị nền tảng cho thiết kế chỉ mục, TTL, CAS, giao dịch, hiệu năng và API reactive.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **bucket**, **scope**, **collection** và **document** về phạm vi, trách nhiệm, cấu hình và quyền truy cập.
- Chọn cấu trúc dữ liệu phù hợp cho hệ thống nhiều miền nghiệp vụ, nhiều tenant hoặc nhiều vòng đời dữ liệu.
- Tạo và truy cập collection bằng Couchbase Java SDK, SQL++ và Spring Data Couchbase.
- Biết những thiết lập nào thường nằm ở bucket, scope hoặc collection; hiểu quan hệ giữa collection và chỉ mục, TTL, CAS, transaction.
- Nhận ra các lỗi thường gặp khi đổi đường dẫn dữ liệu, thiết kế nhiều collection và triển khai ứng dụng.

## 2. Mô hình phân cấp

Couchbase lưu dữ liệu dưới dạng **document**, thường là JSON. Trên một cluster, document được tổ chức theo thứ tự:

~~~text
Cluster
└── Bucket: commerce
    ├── Scope: sales
    │   ├── Collection: orders
    │   │   ├── Document ID: order::1001
    │   │   └── Document ID: order::1002
    │   └── Collection: payments
    └── Scope: catalog
        ├── Collection: products
        └── Collection: categories
~~~

Ba tầng tổ chức có vai trò khác nhau:

| Tầng | Trả lời câu hỏi | Ví dụ | Trách nhiệm điển hình |
|---|---|---|---|
| **Bucket** | Dữ liệu thuộc vùng lưu trữ/tài nguyên nào? | `commerce` | Cấu hình lưu trữ, dung lượng, bản sao dữ liệu và chính sách ở cấp bucket |
| **Scope** | Các tập dữ liệu thuộc miền logic nào? | `sales` | Nhóm collection cùng miền nghiệp vụ, ranh giới thuận tiện cho quyền và truy vấn |
| **Collection** | Đây là loại dữ liệu nào được quản lý cùng nhau? | `orders` | Chứa document, là đích KV, SQL++ và chỉ mục |
| **Document** | Bản ghi cụ thể nào? | `order::1001` | JSON hoặc giá trị hỗ trợ khác, document ID, CAS, expiry và metadata |

Đường dẫn đầy đủ đến một collection là:

~~~text
bucket.scope.collection
commerce.sales.orders
~~~

Đường dẫn này gọi là **keyspace** của collection khi sử dụng SQL++. Một document được định vị bằng **bucket + scope + collection + document ID**. Do đó, hai collection khác nhau có thể cùng chứa document ID `1001` mà không đụng khóa; ngược lại, trong *một* collection, document ID phải duy nhất.

**Không nhầm tầng tổ chức với topology:** bucket không phải một server, và collection không bị cố định ở một node. Data Service phân phối dữ liệu của bucket lên các Data node của cluster.

~~~mermaid
flowchart TD
    C["Couchbase Cluster"]
    B["Bucket: commerce"]
    S1["Scope: sales"]
    S2["Scope: catalog"]
    O["Collection: orders"]
    P["Collection: payments"]
    PR["Collection: products"]
    CA["Collection: categories"]
    C --> B
    B --> S1
    B --> S2
    S1 --> O
    S1 --> P
    S2 --> PR
    S2 --> CA
~~~

## 3. Bucket: vùng chứa dữ liệu và tài nguyên

**Bucket** là ranh giới lưu trữ cấp cao để tổ chức document trong cluster. Khi thiết kế bucket, cần quan tâm đến:

- **Loại bucket và cơ chế lưu trữ:** tùy phiên bản, tính năng triển khai và yêu cầu sử dụng. Chẳng hạn bucket kiểu Couchbase dùng để lưu trữ bền vững; một số triển khai còn cung cấp lựa chọn kiểu Ephemeral cho dữ liệu được giữ trong bộ nhớ. Không giả định mọi loại bucket có cùng khả năng persistence, recovery hay transaction.
- **Giới hạn tài nguyên:** bucket có các thiết lập dung lượng bộ nhớ và mức sử dụng lưu trữ; đặt quá nhiều bucket làm tăng chi phí quản trị và chia nhỏ tài nguyên.
- **Replica dữ liệu:** phân phối bản sao phân vùng trên Data node nhằm tăng khả năng khôi phục khi node hỏng; replica không thay thế backup.
- **Durability và chính sách dữ liệu:** ứng dụng có thể chọn yêu cầu độ bền khi ghi; thiết lập hiệu lực chi tiết phụ thuộc phiên bản, loại bucket và cơ chế ghi.
- **Expiry/TTL:** một số thiết lập thời gian sống áp dụng ở mức bucket và có thể liên quan đến cấu hình collection hoặc từng document.
- **Quản lý và bảo mật:** bucket là đơn vị quan trọng khi cấp quyền, giám sát và vận hành.

Các document trong một bucket được phân phối qua **vBucket** (phân vùng logic) trên các Data node. Replica vBucket được dùng cho tính sẵn sàng của dữ liệu. Cách phân vùng không làm thay đổi đường dẫn logic `commerce.sales.orders` của ứng dụng.

### Khi nào tạo bucket riêng?

Cân nhắc tách bucket khi cần **chính sách tài nguyên, lưu trữ hoặc vận hành độc lập**. Ví dụ, hệ thống có dữ liệu nghiệp vụ quan trọng và một tập dữ liệu tạm có cách lưu trữ/khôi phục hoàn toàn khác nhau. Quyết định dựa trên nhu cầu cách ly thực tế.

**Không cần tạo một bucket cho mỗi loại document.** Với phần lớn miền nghiệp vụ chung tài nguyên, có thể dùng các scope và collection bên trong một bucket để tránh phân mảnh cấu hình.

### Bucket khác cơ sở dữ liệu quan hệ thế nào?

Bucket đôi khi được so sánh với một database, scope với schema, collection với table. Phép so sánh này giúp hình dung **đường dẫn**, nhưng không đồng nhất ý nghĩa:

- Collection chứa các document JSON có thể khác cấu trúc; nó không tự ép mọi record theo một schema cột cố định.
- Quan hệ giữa document không mặc nhiên có foreign key, cascade hoặc các ràng buộc như hệ quản trị quan hệ.
- Truy vấn SQL++ có thể kết hợp collection và cấu trúc JSON linh hoạt, nhưng việc thiết kế chỉ mục và tính nhất quán cần hiểu riêng.

## 4. Scope: nhóm collection theo miền logic

**Scope** là đơn vị nhóm collection bên trong một bucket. Tổ chức theo scope giúp giữ một miền chức năng rõ ràng, chẳng hạn:

- `sales`: `orders`, `payments`, `refunds`.
- `catalog`: `products`, `categories`.
- `identity`: `users`, `sessions`.

Scope tạo điểm đặt tên và phân quyền tiện lợi. Tùy mô hình RBAC của Couchbase, quyền truy cập có thể được giới hạn tới bucket, scope hoặc collection. Ví dụ service chỉ đọc catalog không cần quyền ghi vào collection orders.

Scope cũng hữu ích khi truy vấn: có thể đặt **query context** là một scope để viết tên collection ngắn gọn hơn. Tuy nhiên, trong tài liệu kỹ thuật và SQL++ chia sẻ giữa nhiều môi trường, ghi đầy đủ `bucket.scope.collection` thường dễ đọc và ít gây nhầm lẫn.

**Scope không phải** bucket con có quota bộ nhớ/replica tách biệt hoàn toàn. Những chính sách ở cấp bucket vẫn ảnh hưởng các scope bên trong. Nếu cần cách ly tài nguyên vật lý hoặc chính sách lưu trữ riêng, phải đánh giá bucket/cluster và cấu hình triển khai phù hợp.

## 5. Collection: tập document theo loại dữ liệu

**Collection** là đơn vị mà API KV và nhiều truy vấn SQL++ nhắm tới trực tiếp. Thay vì trộn mọi thứ vào một collection rồi dùng trường `type` để phân biệt, có thể tổ chức:

~~~text
commerce.sales.orders
commerce.sales.payments
commerce.catalog.products
~~~

Một document trong `orders`:

~~~json
{
  "type": "order",
  "tenantId": "tenant-42",
  "customerId": "customer::87",
  "status": "PAID",
  "createdAt": "2026-11-25T02:15:00Z",
  "total": 1490000,
  "currency": "VND",
  "items": [
    {"productId": "sku::A1", "quantity": 2, "unitPrice": 745000}
  ]
}
~~~

Đường dẫn của document là `commerce.sales.orders` + ID `order::1001`. ID là metadata của document, **không tự xuất hiện** thành trường `id` trong JSON. Truy vấn SQL++ lấy ID qua `META(o).id`.

**Collection không tự đảm bảo schema đồng nhất.** Cùng một collection vẫn có thể chứa nhiều dạng document, nên ứng dụng phải có chiến lược kiểm tra dữ liệu, phiên bản schema và migration. Trường `type` trong JSON ở ví dụ là lựa chọn nghiệp vụ, không phải điều kiện bắt buộc của Couchbase.

### Vì sao chọn collection riêng?

- Cô lập tập dữ liệu ở mức tên, quyền truy cập và chỉ mục.
- Thiết kế GSI theo truy vấn của từng loại document; query service biết chính xác keyspace cần đọc.
- Quản lý vòng đời dữ liệu và một số chính sách expiry ở cấp collection khi môi trường hỗ trợ.
- Hạn chế việc mọi truy vấn phải thêm `WHERE type = ...` trên một collection quá rộng.

Chi phí đi kèm là số collection/index lớn hơn, chính sách quản lý nhiều hơn và công việc migration phức tạp hơn. Không nên tạo collection vô hạn theo từng người dùng, đơn hàng hoặc thực thể nhỏ.

## 6. Thiết kế mô hình tổ chức dữ liệu theo bài toán

Giả sử xây dựng một hệ thống thương mại điện tử dùng Spring Data Couchbase.

### Phương án nền tảng

~~~text
Bucket: commerce
├── Scope: catalog
│   ├── Collection: products
│   └── Collection: categories
├── Scope: sales
│   ├── Collection: orders
│   └── Collection: payments
└── Scope: customers
    └── Collection: profiles
~~~

Cách thiết kế này chia **miền nghiệp vụ** ở scope và **loại document** ở collection. Nó phù hợp khi các miền dùng chung bucket và chính sách tài nguyên.

| Phương án | Khi phù hợp | Cân nhắc |
|---|---|---|
| Một bucket, nhiều scope theo miền | Nhiều nhóm chức năng dùng chung tài nguyên | Dễ nhìn cấu trúc, quyền theo miền |
| Một scope, nhiều collection theo loại | Ứng dụng nhỏ, ít miền nghiệp vụ | Đơn giản nhưng dễ phải tổ chức lại khi tăng quy mô |
| Bucket riêng cho miền đặc biệt | Cần quota, lưu trữ, replica hoặc vận hành độc lập | Tốn quản trị và tài nguyên hơn |
| Scope/collection cho mỗi tenant | Số tenant ít, có nhu cầu cách ly logic/quyền rõ ràng | Số lượng keyspace, index và tác vụ vận hành tăng theo tenant |
| Tenant chung collection, phân biệt bằng `tenantId` | Nhiều tenant, cách ly ở tầng ứng dụng | Bắt buộc chặn truy cập chéo tenant bằng thiết kế API/quyền và điều kiện truy vấn chặt chẽ |

### Multi-tenant không có một đáp án duy nhất

Với hàng nghìn tenant nhỏ, mô hình một collection cho mỗi tenant có thể tạo số lượng collection/index khó vận hành và chạm giới hạn theo phiên bản. Một collection chung với `tenantId` trong khóa/index thường phù hợp hơn về quản trị, nhưng yêu cầu mọi đường đọc/ghi phải ràng buộc tenant chặt chẽ.

Ngược lại, tenant cần chính sách độc lập, quyền riêng hoặc quản trị vòng đời riêng có thể đáng để cân nhắc scope, collection hoặc bucket riêng. **Tách tên collection không mặc nhiên bảo đảm cách ly bảo mật** nếu tài khoản ứng dụng vẫn có quyền trên toàn bucket.

### Chọn document ID

Trong một collection, nên tạo ID ổn định và có quy ước dễ quản lý:

~~~text
orders / order::1001
products / sku::A1
profiles / customer::87
~~~

Nếu nhiều tenant chung collection, cần xem xét đưa tenant vào quy ước khóa:

~~~text
tenant::42::order::1001
tenant::99::order::1001
~~~

Khi đọc theo ID, ứng dụng vẫn phải xác thực tenant của người gọi; tên khóa không thay thế kiểm soát quyền. Với trường hợp cần định tuyến theo tenant hoặc truy vấn phạm vi tenant, hãy cân nhắc đặc tính phân phối của khóa, chỉ mục và mẫu truy cập thực tế.

## 7. Tạo bucket, scope, collection và phân quyền

Có thể tạo bucket, scope và collection từ giao diện Couchbase, công cụ dòng lệnh hoặc API quản trị phù hợp với môi trường. Luồng vận hành thông thường:

1. Tạo bucket `commerce` với loại lưu trữ, dung lượng, replica và chính sách cần thiết.
2. Trong bucket, tạo scope `sales` và `catalog`.
3. Trong `sales`, tạo collection `orders` và `payments`; trong `catalog`, tạo `products`.
4. Cấp quyền tối thiểu cho từng ứng dụng; tài khoản ứng dụng không cần quyền tạo/xóa bucket hay index nếu chỉ đọc/ghi document.
5. Cấu hình chỉ mục cho truy vấn theo field và thử đọc/ghi từ SDK.

**Mặc định tồn tại `_default` scope và `_default` collection** trong bucket được tạo theo mô hình collection. Một ứng dụng cũ có thể vẫn đang sử dụng `_default._default` mà không khai báo rõ, nên cần kiểm tra trước khi đổi cấu hình.

Không nên thao tác xóa collection/bucket tùy tiện: xóa container sẽ làm dữ liệu bên trong không còn truy cập được theo đường cũ và có thể gây mất dữ liệu. Việc phục hồi phụ thuộc backup/snapshot và khả năng của môi trường.

## 8. Truy cập collection bằng Couchbase Java SDK

Java SDK thể hiện rõ ba cấp đường dẫn. Ví dụ ngắn sau tập trung vào các handle và thao tác KV:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Bucket;
import com.couchbase.client.java.Scope;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import java.time.Duration;

public class OrderKvExample {
    public static void main(String[] args) {
        // Dùng cấu hình an toàn của môi trường thực tế thay cho giá trị minh họa.
        Cluster cluster = Cluster.connect(
                "couchbase://localhost", "app-user", "example-password");

        try {
            Bucket bucket = cluster.bucket("commerce");
            bucket.waitUntilReady(Duration.ofSeconds(10));

            Scope scope = bucket.scope("sales");
            Collection orders = scope.collection("orders");

            JsonObject order = JsonObject.create()
                    .put("type", "order")
                    .put("tenantId", "tenant-42")
                    .put("status", "PAID")
                    .put("total", 1490000);

            orders.upsert("order::1001", order);
            JsonObject loaded = orders.get("order::1001").contentAsObject();
            System.out.println(loaded.getString("status"));
        } finally {
            cluster.disconnect();
        }
    }
}
~~~

Trong môi trường thực tế, dùng kết nối TLS/Capella đúng endpoint, đưa thông tin xác thực vào secret manager hoặc biến cấu hình bảo vệ, và tái sử dụng đối tượng cluster/SDK hợp lý thay vì tạo kết nối mới cho mỗi HTTP request.

**Điểm quan trọng:** `orders.get("order::1001")` chỉ tìm trong `commerce.sales.orders`. Nó không tự tìm trong `commerce.sales.payments` ngay cả khi collection này có document ID giống hệt. Thao tác KV định tuyến đến Data Service theo keyspace và ID, không cần GSI.

## 9. Truy vấn SQL++ và chỉ mục theo từng collection

SQL++ dùng đường dẫn collection để xác định nguồn dữ liệu:

~~~sql
SELECT
    META(o).id AS documentId,
    o.tenantId,
    o.status,
    o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "tenant-42"
  AND o.status = "PAID"
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Truy vấn trên cần chỉ mục phù hợp nếu muốn phục vụ hiệu quả ở quy mô lớn. Ví dụ:

~~~sql
CREATE INDEX ix_orders_tenant_status_created
ON `commerce`.`sales`.`orders`(
    tenantId, status, createdAt DESC
);
~~~

Để xem Couchbase có dùng chỉ mục này hay không:

~~~sql
EXPLAIN
SELECT META(o).id AS documentId, o.tenantId, o.status, o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = "tenant-42"
  AND o.status = "PAID"
ORDER BY o.createdAt DESC
LIMIT 20;
~~~

Trong kết quả, xem IndexScan, Fetch, Order và index đã chọn. Truy vấn ở trên vẫn có thể cần Fetch để lấy `total` và các trường không nằm trong chỉ mục. **Covering index** là lựa chọn tối ưu khi tránh Fetch đáng giá chi phí lưu trữ và cập nhật index; cần đo thực tế trước khi thêm trường.

Phân biệt ba tình huống:

- `GET` theo document ID: KV, **không cần** primary/secondary index.
- SQL++ lọc theo field: thường dùng **secondary index** phù hợp của collection được truy vấn.
- SQL++ không có index thích hợp: có thể lỗi “không có index” hoặc có kế hoạch kém hiệu quả, tùy index hiện hữu và biểu thức truy vấn.

**Chỉ mục của `commerce.sales.orders` không tự áp dụng cho `commerce.sales.payments`** dù cùng tên field. Collection xác định ranh giới chỉ mục; Query Service xử lý và Index Service duy trì GSI cho từng keyspace.

### Truy vấn nhiều collection

SQL++ hỗ trợ kết hợp dữ liệu từ nhiều collection khi truy vấn và quyền cho phép. Ví dụ:

~~~sql
SELECT
    META(o).id AS orderId,
    o.total,
    p.paymentStatus
FROM `commerce`.`sales`.`orders` AS o
JOIN `commerce`.`sales`.`payments` AS p
  ON p.orderId = META(o).id
WHERE o.tenantId = "tenant-42";
~~~

Đây là ví dụ logic: khóa liên hệ `orderId` do ứng dụng quản lý. Hiệu năng và dạng JOIN thực tế phụ thuộc phiên bản Couchbase, cú pháp được hỗ trợ, GSI và kế hoạch truy vấn; cần đánh giá `EXPLAIN` trên cả hai phía. Không có ràng buộc khóa ngoại tự động được tạo chỉ vì hai document có cùng ID liên quan.

## 10. Mapping bucket/scope/collection trong Spring Data Couchbase

Spring Data Couchbase giúp chuyển Java object sang document, dùng repository cho CRUD, CouchbaseTemplate cho thao tác có kiểm soát hơn, và SQL++ khi truy vấn theo field. Cần hiểu ba lớp cấu hình:

| Khía cạnh | Ví dụ | Ý nghĩa |
|---|---|---|
| Bucket cho ứng dụng | `commerce` | Bucket mà Spring Data/SDK kết nối |
| Scope của entity | `@Scope("sales")` | Phạm vi collection của entity |
| Collection của entity | `@Collection("orders")` | Nơi entity được lưu |
| ID của entity | `@Id` | Khóa document dùng trong KV |
| Trường document | `@Field` hoặc mapping tương đương | Tên trường JSON trong document |

### Ví dụ entity

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Field;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("sales")
@Collection("orders")
public class OrderDocument {
    @Id
    private String id;

    @Field
    private String tenantId;

    @Field
    private String status;

    @Field
    private Long total;

    public OrderDocument() {}

    public OrderDocument(String id, String tenantId,
                         String status, Long total) {
        this.id = id;
        this.tenantId = tenantId;
        this.status = status;
        this.total = total;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getStatus() { return status; }
    public Long getTotal() { return total; }
}
~~~

Repository:

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByTenantIdAndStatus(
            String tenantId, String status);
}
~~~

Ví dụ sử dụng:

~~~java
OrderDocument order = new OrderDocument(
        "order::1001", "tenant-42", "PAID", 1490000L);

// Thao tác theo ID thường sử dụng đường KV đến collection được mapping.
orderRepository.save(order);
OrderDocument loaded = orderRepository.findById("order::1001")
        .orElseThrow();

// Derived query theo trường thường cần SQL++ và GSI thích hợp.
List<OrderDocument> paidOrders =
        orderRepository.findByTenantIdAndStatus("tenant-42", "PAID");
~~~

**Chú ý tính tương thích phiên bản:** annotation, cú pháp cấu hình và mức hỗ trợ scope/collection cần phù hợp phiên bản Spring Boot + Spring Data Couchbase đang dùng. Ví dụ trên minh họa dòng Spring Data Couchbase có hỗ trợ `@Scope` và `@Collection`.

### Repository tự sinh truy vấn cần kiểm tra gì?

Spring Data Couchbase có thể dùng thông tin phân biệt loại entity, thường là field `_class`, khi sinh SQL++ từ repository. Vì thế truy vấn Java:

~~~java
findByTenantIdAndStatus("tenant-42", "PAID")
~~~

không nhất thiết tương đương hoàn toàn với câu lệnh SQL++ thủ công chỉ có `tenantId` và `status`. Cần:

1. Xác nhận query thực tế nhắm đúng `commerce.sales.orders`.
2. Xác nhận các điều kiện mapping tự thêm, chẳng hạn field phân biệt entity.
3. Thiết kế index phù hợp với query được thực thi và kiểm tra `EXPLAIN`.
4. Đảm bảo tài khoản ứng dụng có quyền tương ứng trên collection/index cần dùng.

Nếu entity bị cấu hình sai scope/collection, lỗi có thể là collection không tìm thấy hoặc thao tác trả về không có document dù ID tồn tại **ở collection khác**.

### CouchbaseTemplate và collection

`CouchbaseTemplate` cung cấp thao tác dựa trên entity và các API truy cập mức thấp hơn tùy phiên bản. Khi ứng dụng cần truy cập nhiều collection, hãy tổ chức entity mapping hoặc lựa chọn scope/collection trong API được phiên bản đó hỗ trợ. Không giả định một template mặc định có thể tự tìm đúng collection chỉ từ ID.

Cần phân biệt rõ: **tên repository** là lớp Java; **tên collection** là tên keyspace trên Couchbase. Hai tên không bắt buộc trùng nhau.

## 11. TTL, CAS, transaction và ranh giới collection

### 11.1. TTL/expiry

TTL quy định document sẽ hết hạn sau khoảng thời gian hoặc tại mốc thời gian nhất định. Couchbase hỗ trợ expiry trên từng document, và tùy phiên bản/cấu hình có thể có thiết lập ở bucket hoặc collection.

Các trường hợp ứng dụng:

- `sessions`: document phiên đăng nhập có thời hạn.
- `carts`: giỏ hàng không hoạt động được làm sạch sau một khoảng thời gian.
- `orders`: đơn hàng thường được giữ lâu hơn, có thể không nên đặt TTL ngắn.

**Đừng dùng một chính sách TTL giống nhau cho tất cả collection.** Thiết kế `sessions` và `orders` trong các collection riêng giúp nêu rõ kỳ vọng vòng đời dữ liệu. TTL trên một collection cũng **không tự động thay đổi** TTL của collection khác.

Cần kiểm chứng quy tắc ưu tiên giữa expiry của thao tác ghi, cấu hình cấp bucket/collection, cập nhật document và các tính năng như preserve-expiry theo đúng phiên bản SDK/server. Không coi TTL là công cụ tuân thủ lưu trữ thay cho chính sách backup, lưu trữ và xóa dữ liệu đã được kiểm chứng.

### 11.2. CAS (Compare-And-Swap)

CAS là token phiên bản của **mỗi document**. Sau khi đọc một document, ứng dụng có thể dùng CAS cho phép ghi có điều kiện: nếu document đã bị người khác thay đổi, thao tác bị từ chối thay vì âm thầm ghi đè.

CAS thuộc metadata của document; nó không phải thuộc tính của toàn bucket/scope/collection và không biến nhiều document thành một giao dịch.

Ví dụ SDK minh họa cập nhật có điều kiện:

~~~java
import static com.couchbase.client.java.kv.ReplaceOptions.replaceOptions;
import com.couchbase.client.java.kv.GetResult;

GetResult current = orders.get("order::1001");
JsonObject updated = current.contentAsObject()
        .put("status", "SHIPPED");

orders.replace(
        "order::1001",
        updated,
        replaceOptions().cas(current.cas())
);
~~~

Nếu CAS không còn khớp, cần xử lý xung đột theo nghiệp vụ (đọc lại, hợp nhất hoặc báo lỗi), không retry vô hạn với dữ liệu cũ.

### 11.3. Transaction

Khi một nghiệp vụ phải cập nhật nhiều document, chẳng hạn tạo đơn và ghi trạng thái thanh toán, cần xem xét cơ chế transaction nếu yêu cầu tính nguyên tử. Việc document nằm khác collection **không tự ngăn cản** mọi transaction: phạm vi hỗ trợ phụ thuộc API transaction, loại bucket, cấu hình dịch vụ và phiên bản Couchbase.

Transaction có chi phí thực thi và điều kiện sử dụng. Nó không tự thay thế thiết kế ID, tính bất biến nghiệp vụ hoặc các biện pháp idempotency khi ứng dụng gọi lại thao tác.

### 11.4. Nhất quán khi truy vấn theo collection

Sau khi ghi một document qua KV, SQL++ dùng GSI có thể chưa thấy thay đổi ngay vì quá trình cập nhật chỉ mục bất đồng bộ. Đây là vấn đề **scan consistency**, không phải do document ở sai collection nếu mapping đã đúng.

Với luồng cần đọc ngay sau ghi, có thể cân nhắc đọc KV theo ID, hoặc cấu hình consistency tương ứng trong Query/SDK như `request_plus` hay cơ chế dựa trên mutation state khi hỗ trợ. Chỉ bật mức chờ mạnh hơn ở đường truy vấn thực sự cần vì có thể làm tăng độ trễ.

## 12. Bảo mật và phân quyền theo đường dữ liệu

Tổ chức tốt giúp cấp quyền tối thiểu:

| Thành phần | Nhu cầu | Định hướng quyền |
|---|---|---|
| API quản lý sản phẩm | Đọc/ghi `commerce.catalog.products` | Chỉ cấp quyền cần thiết cho collection catalog |
| API đơn hàng | Đọc/ghi `commerce.sales.orders` | Không tự động được quyền sửa `catalog.products` |
| Dịch vụ báo cáo | Truy vấn nhiều collection | Cấp quyền đọc/truy vấn tương ứng, hạn chế ghi |
| Công cụ migration/index | Thay đổi keyspace/index | Dùng tài khoản vận hành riêng, tránh chia quyền quản trị cho ứng dụng |

RBAC phải phù hợp với cả thao tác KV, SQL++ và quản lý index. Nếu một truy vấn JOIN collection khác nhưng tài khoản thiếu quyền đọc ở collection đó, truy vấn có thể không thành công dù collection chính truy cập bình thường.

Phân quyền ở Couchbase là **một lớp kiểm soát**. Với hệ thống dùng chung tài khoản ứng dụng cho nhiều tenant, mã nguồn vẫn phải bảo vệ điều kiện `tenantId`, xử lý ID được cung cấp bởi người dùng và ngăn rò rỉ dữ liệu chéo tenant.

## 13. Di chuyển và thay đổi cấu trúc keyspace

Khi đổi từ `_default._default` sang `sales.orders`, đừng chỉ đổi annotation trong Java rồi cho rằng dữ liệu sẽ tự chuyển. Đây là thay đổi **đường dẫn lưu trữ**.

Một kế hoạch migration thận trọng có thể gồm:

1. Xác định collection nguồn, collection đích, toàn bộ endpoint/repository/query sử dụng keyspace cũ.
2. Tạo scope/collection đích và quyền phù hợp; tạo các index cần thiết trước khi chuyển ứng dụng sang truy vấn mới.
3. Sao chép hoặc chuyển document sang collection đích qua công cụ/batch phù hợp; bảo toàn ID, dữ liệu, expiry và các metadata cần thiết theo yêu cầu nghiệp vụ.
4. Kiểm tra số lượng, dữ liệu mẫu, document ID, quyền truy cập và query plan; có phương án xử lý dữ liệu được ghi trong lúc migration.
5. Chuyển ứng dụng theo kế hoạch có thể kiểm soát; theo dõi lỗi collection không tồn tại, document không tìm thấy và truy vấn thiếu index.
6. Chỉ dọn collection cũ khi đã xác minh đầy đủ, có bản sao lưu và thống nhất thời điểm dừng đường cũ.

**Không có quy tắc “đổi tên collection = di chuyển document”** áp dụng chung cho mọi phiên bản. Thao tác rename/move nếu được cung cấp cần kiểm tra khả năng, phạm vi và hệ quả cụ thể.

## 14. Những lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| `DocumentNotFound` dù nhìn thấy ID trong console | ID nằm ở bucket/scope/collection khác | In/log keyspace đang dùng, đối chiếu nơi dữ liệu thực tồn tại |
| `CollectionNotFound` | Collection chưa tạo, cấu hình sai hoặc metadata SDK chưa cập nhật | Kiểm tra tên chính xác, triển khai schema và kết nối |
| SQL++ không có kết quả nhưng KV đọc thấy | Truy vấn sai keyspace, khác điều kiện lọc hoặc GSI chưa bắt kịp | Kiểm tra FROM, mapping entity, scan consistency |
| Query thiếu chỉ mục | Chưa tạo GSI ở collection đang truy vấn | Tạo index theo truy vấn, đọc `EXPLAIN` |
| Ứng dụng có thể truy cập sai tenant | Quyền ứng dụng quá rộng hoặc thiếu điều kiện tenant | Siết RBAC và xác thực quyền trên mọi đường truy cập |
| Số index/collection tăng nhanh | Chia collection quá nhỏ, nhất là per-user/per-tenant | Cân nhắc mô hình chung với `tenantId` và index phù hợp |
| Ghi chậm sau khi tạo nhiều collection/index | Index maintenance và tài nguyên bị phân tán | Xác định index thực dùng, bỏ index dư theo quy trình quản trị |
| Document biến mất theo thời gian | TTL/expiry được bật ở document, collection hoặc bucket | Kiểm tra cấu hình expiry và thao tác ghi/update |

**Thứ tự chẩn đoán thực dụng:** xác nhận bucket → scope → collection → document ID → quyền truy cập → phương thức KV hay SQL++ → chỉ mục → consistency/TTL → tài nguyên cluster. Cách này tránh sửa Query/Index Service khi lỗi thực tế chỉ là sai đường dẫn dữ liệu.

## 15. Bài tập ứng dụng

### Bài tập 1: Thiết kế hệ thống đặt hàng

Bạn cần lưu `products`, `orders`, `payments`, `sessions` trong cùng ứng dụng. Hãy đề xuất bucket/scope/collection, giải thích vì sao `sessions` có thể cần vòng đời ngắn hơn `orders`, và cho biết có cần tách bucket riêng không.

**Gợi ý:** dùng một bucket `commerce` nếu tài nguyên/chính sách giống nhau; tách scope theo miền nghiệp vụ và các collection riêng; cân nhắc expiry tại collection chứa session. Tách bucket khi có nhu cầu cách ly tài nguyên hoặc chính sách vận hành thực sự.

### Bài tập 2: Hai document cùng ID

`commerce.sales.orders` chứa `1001`; `commerce.sales.payments` cũng chứa `1001`. Điều này có hợp lệ không? Lệnh `orders.get("1001")` đọc document nào?

**Đáp án:** hợp lệ, vì document ID chỉ cần duy nhất trong một collection; lệnh đọc document `1001` của `orders`, không tìm sang `payments`.

### Bài tập 3: Repository chuyển collection

Bạn chuyển entity `OrderDocument` từ `_default._default` sang `sales.orders` và API `findById` bắt đầu báo thiếu document. Hãy liệt kê các bước kiểm tra.

**Gợi ý:** xác minh annotation/cấu hình bucket, collection đích đã có, ID đúng, dữ liệu đã migration, quyền tài khoản và query/index có liên quan; không vội quy lỗi cho Spring Data.

### Bài tập 4: Tối ưu truy vấn

Ứng dụng cần tìm đơn của một tenant theo trạng thái và thời gian mới nhất. Viết truy vấn SQL++ trên `commerce.sales.orders`, tạo secondary index khởi đầu cho `tenantId`, `status`, `createdAt`, và dùng `EXPLAIN` đánh giá việc scan/fetch/sort.

### Bài tập 5: Phân tách tenant

Hệ thống có 20 tenant lớn và dự kiến tăng lên hàng chục nghìn tenant nhỏ. Bạn sẽ áp dụng chiến lược collection theo tenant hay collection chung có `tenantId`? Nêu các yếu tố về giới hạn keyspace, index, quyền truy cập, chi phí vận hành và mục tiêu cách ly trước khi quyết định.

## 16. Tổng kết

**Bucket** xác định vùng lưu trữ và chính sách tài nguyên; **scope** nhóm collection theo miền logic; **collection** là ranh giới quản lý document, đường KV, truy vấn SQL++ và chỉ mục. Đối với Spring Data Couchbase, tổ chức keyspace đúng ngay từ đầu giúp document mapping và repository hoạt động nhất quán, CouchbaseTemplate truy cập đúng dữ liệu, chỉ mục có phạm vi rõ ràng và cơ chế TTL/CAS/giao dịch được áp dụng đúng yêu cầu nghiệp vụ.

Khi thiết kế, hãy bắt đầu từ câu hỏi **“Dữ liệu thuộc miền nào, được đọc/ghi theo cách nào và cần chính sách nào?”** rồi mới quyết định tách bucket, scope hoặc collection.

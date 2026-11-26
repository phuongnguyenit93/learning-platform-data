# Ví dụ xuyên suốt: ứng dụng quản lý khách hàng và đơn hàng

## 1. Mục tiêu và câu chuyện nghiệp vụ

Bài học thuộc chương **Tổng quan** của module **Spring Data Couchbase (SPRING_DATA_COUCHBASE)**. Thay vì học riêng từng annotation hay API, chúng ta xây một mô hình nhỏ xuyên suốt: hệ thống bán hàng cần **quản lý khách hàng, tạo đơn hàng, xem lịch sử đơn và đổi trạng thái đơn**. Qua đó, ta kết nối các khái niệm document mapping, Repository, `CouchbaseTemplate`, truy vấn SQL++, bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và reactive.

Sau bài học, bạn có thể:

- Thiết kế ranh giới giữa document khách hàng và document đơn hàng theo vòng đời nghiệp vụ.
- Đặt document ID và phân chia bucket, scope, collection có chủ đích.
- Ánh xạ Java class sang JSON document với Spring Data Couchbase; tạo Repository và service phù hợp.
- Phân biệt `findById` theo KV với truy vấn lịch sử đơn hàng theo SQL++ và index.
- Phát hiện lost update bằng `@Version`/CAS khi hai nhân viên cùng sửa một đơn.
- Giải thích khi nào cần transaction đa document, lúc nào TTL phù hợp, và lý do có thể chọn API reactive.
- Nhận biết các rủi ro production: tính duy nhất email, tính tiền, xác thực, consistency, phân trang và khả năng quan sát.

**Phạm vi ví dụ:** Hệ thống chỉ quản lý khách hàng và đơn, không xây toàn bộ nghiệp vụ tồn kho, thanh toán hay vận chuyển. Các đoạn mã Java nhằm minh họa luồng thiết kế trong một dự án Spring Boot tương thích; cần hoàn thiện kiểm thử tích hợp, quản lý lỗi, phân quyền và cấu hình phiên bản trước khi dùng production.

## 2. Yêu cầu nghiệp vụ và đường truy cập cần tối ưu

Giả sử nhóm sản phẩm đưa ra các chức năng:

| Mã | Chức năng | Đầu vào | Đường truy cập mong muốn |
| --- | --- | --- | --- |
| UC1 | Đăng ký khách hàng | Họ tên, email | Tạo document với ID mới |
| UC2 | Xem hồ sơ | Customer ID | KV theo document key |
| UC3 | Tìm khách theo email | Email | SQL++ theo field và secondary index |
| UC4 | Tạo đơn hàng | Customer ID, danh sách SKU/số lượng | Đọc khách theo key, kiểm tra nghiệp vụ, tạo một document đơn |
| UC5 | Xem chi tiết đơn | Order ID | KV theo document key |
| UC6 | Xem lịch sử đơn | Customer ID, phân trang | SQL++ theo customer ID + ngày tạo |
| UC7 | Xác nhận đơn | Order ID và trạng thái hiện tại | Đọc–đổi–ghi với CAS/optimistic locking |
| UC8 | Quản lý session tạm | Session ID | KV + expiry/TTL |

Ba câu hỏi quan trọng từ đầu:

1. **Có biết khóa chính xác không?** UC2 và UC5 nên đọc KV; không cần SQL++ chỉ để tìm một document đã có ID.
2. **Có cần lọc/sắp xếp nhiều document không?** UC3 và UC6 cần SQL++, chỉ mục và chiến lược phân trang.
3. **Có thể có hai request cùng ghi không?** UC7 cần CAS; nếu một thao tác tác động **nhiều document**, phải xác định thêm transaction hoặc workflow bù trừ.

Đây là thiết kế hướng theo **access pattern**: mỗi API phải giải thích được vì sao dùng cơ chế truy cập đó.

## 3. Chọn bucket, scope, collection và document ID

Giả sử cluster có bucket `shop`; trong đó:

~~~mermaid
flowchart TB
    B["Bucket: shop"]
    B --> CRM["Scope: crm"]
    B --> SALES["Scope: sales"]
    B --> AUTH["Scope: auth"]
    CRM --> C["Collection: customers"]
    SALES --> O["Collection: orders"]
    AUTH --> SES["Collection: sessions"]
    C --> CD["ID: customer::c-1001"]
    O --> OD["ID: order::ord-5001"]
    SES --> SD["ID: session::<opaque-id>"]
~~~

Tên trên là **thiết kế minh họa**, không phải tài nguyên Spring Data tự tạo ra. Bucket/scope/collection cần được tạo và cấp quyền tại Couchbase phù hợp với môi trường. Một document được xác định bởi **bucket + scope + collection + ID**; hai collection có thể cùng chuỗi ID nhưng không đại diện cùng một document.

### 3.1. Chọn ID theo nhu cầu đọc

| Entity | Document ID ví dụ | Quy ước |
| --- | --- | --- |
| Khách hàng | `customer::c-1001` | Định danh bất biến do hệ thống cấp |
| Đơn hàng | `order::ord-5001` | ID duy nhất cho từng đơn |
| Session | `session::opaque-random-value` | Định danh ngẫu nhiên, khó đoán |

Tiền tố `customer::` và `order::` là **quy ước ứng dụng** để phân biệt loại khóa, không phải cấu trúc bắt buộc của Couchbase. Không dùng email làm khóa khách hàng vì email có thể đổi; không đưa bí mật hay dữ liệu nhạy cảm vào ID. Trong thực tế có thể tạo ID bằng UUID/ULID hoặc dịch vụ cấp ID, miễn đáp ứng tính duy nhất và ổn định.

### 3.2. Vì sao tách khách hàng và đơn hàng?

Khách hàng có thể có hàng nghìn đơn hàng theo năm. Nếu embed tất cả đơn vào một JSON document khách hàng, document sẽ tăng liên tục, gây tốn chi phí đọc/ghi và tăng tranh chấp cập nhật. Vì thế:

- **Customer document** chứa hồ sơ và các thuộc tính có vòng đời tương đối ổn định.
- **Order document** tồn tại độc lập, chứa `customerId` để tìm các đơn của khách.
- **Order lines** thường được **embed trong đơn hàng** như bản chụp SKU, số lượng và đơn giá tại thời điểm đặt. Khi tên hoặc giá hiện tại của sản phẩm thay đổi, đơn cũ vẫn thể hiện lịch sử đã chốt.

Couchbase không tự áp đặt khóa ngoại giữa `Order.customerId` và metadata key của Customer. Service phải kiểm tra khách hàng và quyết định chính sách khi khách bị vô hiệu hóa/xóa. SQL++ có thể truy vấn liên quan nhiều document, nhưng không nên dùng JOIN thay cho quyết định ranh giới aggregate.

## 4. Hai JSON document và dữ liệu bất biến

### 4.1. Document khách hàng

Địa chỉ: `shop.crm.customers`; metadata ID: `customer::c-1001`.

~~~json
{
  "fullName": "Nguyen An",
  "email": "an@example.com",
  "status": "ACTIVE",
  "tier": "STANDARD",
  "preferences": {
    "language": "vi",
    "marketingEmails": false
  }
}
~~~

Document ID là metadata, **không bắt buộc phải có field `id` bên trong JSON**. JSON thực tế do Spring Data Couchbase ghi có thể chứa metadata loại Java entity, chẳng hạn một trường phân biệt kiểu, tùy converter và cấu hình.

### 4.2. Document đơn hàng

Địa chỉ: `shop.sales.orders`; metadata ID: `order::ord-5001`.

~~~json
{
  "customerId": "c-1001",
  "createdAt": "2026-11-25T03:10:00Z",
  "status": "CREATED",
  "currency": "VND",
  "lines": [
    { "sku": "SKU-A", "quantity": 2, "unitPriceVnd": 120000 },
    { "sku": "SKU-B", "quantity": 1, "unitPriceVnd": 90000 }
  ],
  "totalVnd": 330000
}
~~~

**Chọn kiểu tiền:** Với VND không có phần thập phân trong ví dụ, dùng `long` chứa số đơn vị VND; không dùng `double` cho tiền. Trong hệ thống nhiều loại tiền, nên dùng đơn vị nhỏ nhất của từng loại hoặc kiểu decimal theo hợp đồng dữ liệu rõ ràng, cùng quy tắc làm tròn.

**Dữ liệu nguồn có thẩm quyền:** Client chỉ nên gửi SKU và số lượng. `unitPriceVnd` phải được lấy từ nguồn giá do server tin cậy, vì chấp nhận đơn giá do trình duyệt tự gửi có thể tạo đơn sai tiền. Bài này giả định một bước định giá nội bộ đã được thực hiện trước khi lưu Order.

~~~mermaid
flowchart LR
    HTTP["HTTP: customerId, SKU, quantity"] --> VALID["Validation & authorization"]
    VALID --> PR["Server-side price lookup"]
    PR --> CALC["Tính tổng và tạo snapshot lines"]
    CALC --> REP["OrderRepository.save"]
    REP --> CB[("Order document trong Couchbase")]
~~~

## 5. Cấu hình Spring Boot và mapping tới collection

Ví dụ phụ thuộc cho Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-couchbase'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Cấu hình kết nối minh họa:

~~~yaml
spring:
  couchbase:
    connection-string: couchbase://localhost
    username: YOUR_COUCHBASE_USERNAME
    password: YOUR_COUCHBASE_PASSWORD
  data:
    couchbase:
      bucket-name: shop
~~~

Đây là placeholder; thông tin đăng nhập thực cần đến từ environment/secret. Mọi collection và index phải được chuẩn bị trên cluster, cùng quyền truy cập phù hợp. Spring Boot/Spring Data có khác biệt cấu hình theo phiên bản, nên cần kiểm tra tài liệu tương ứng.

Với các phiên bản Spring Data Couchbase hỗ trợ mapping theo scope và collection, có thể dùng annotation trên entity:

~~~java
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;

@Document
@Scope("crm")
@Collection("customers")
public class CustomerDocument {
    // Các field được trình bày ở phần sau.
}
~~~

Tương tự, Order dùng `@Scope("sales")` và `@Collection("orders")`. Nếu phiên bản đang dùng có quy tắc mapping khác, phải điều chỉnh configuration/annotation tương ứng. **Chỉ đặt `bucket-name: shop` không tự chuyển mọi entity sang `crm.customers` hoặc `sales.orders`.**

## 6. Xây entity CustomerDocument

Ví dụ Java entity được ánh xạ sang collection khách hàng:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Field;

@Document
@Scope("crm")
@Collection("customers")
public class CustomerDocument {

    @Id
    private String id;

    @Field
    private String fullName;

    @Field
    private String email;

    @Field
    private String status;

    @Field
    private String tier;

    @Version
    private Long version;

    public CustomerDocument() {}

    public CustomerDocument(String id, String fullName,
                            String email, String status, String tier) {
        this.id = id;
        this.fullName = fullName;
        this.email = email;
        this.status = status;
        this.tier = tier;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getFullName() { return fullName; }
    public void setFullName(String fullName) { this.fullName = fullName; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public String getTier() { return tier; }
    public void setTier(String tier) { this.tier = tier; }

    public Long getVersion() { return version; }
    public void setVersion(Long version) { this.version = version; }
}
~~~

- `@Document` đánh dấu kiểu Java để Spring Data Couchbase mapping.
- `@Id` là metadata document key; `@Field` ánh xạ field dữ liệu sang JSON.
- `@Version` cho phép optimistic locking dựa trên **CAS** của Couchbase. Đây là metadata do server quản lý, không phải cột version JPA hoặc bộ đếm do code tự tăng.
- `status` và `tier` là **giá trị nghiệp vụ**. Nên có quy ước hằng/enum rõ để tránh sai chính tả; ví dụ đơn giản dùng String nhằm tập trung vào truy cập dữ liệu.

Có thể dùng class immutable, record hoặc custom converter tùy phiên bản Spring Data và chiến lược mapping. Ví dụ trên dùng constructor không tham số cùng getter/setter để diễn đạt dễ hiểu.

## 7. Xây entity OrderDocument và OrderLine

Order là aggregate riêng, chứa danh sách dòng hàng ngay trong một document.

~~~java
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
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
    private String customerId;

    @Field
    private String createdAt;

    @Field
    private String status;

    @Field
    private String currency;

    @Field
    private List<OrderLine> lines;

    @Field
    private long totalVnd;

    @Version
    private Long version;

    public OrderDocument() {}

    public OrderDocument(
            String id, String customerId, String createdAt,
            String status, String currency,
            List<OrderLine> lines, long totalVnd) {
        this.id = id;
        this.customerId = customerId;
        this.createdAt = createdAt;
        this.status = status;
        this.currency = currency;
        this.lines = lines;
        this.totalVnd = totalVnd;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getCustomerId() { return customerId; }
    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }
    public String getCreatedAt() { return createdAt; }
    public void setCreatedAt(String createdAt) {
        this.createdAt = createdAt;
    }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public String getCurrency() { return currency; }
    public void setCurrency(String currency) { this.currency = currency; }
    public List<OrderLine> getLines() { return lines; }
    public void setLines(List<OrderLine> lines) { this.lines = lines; }
    public long getTotalVnd() { return totalVnd; }
    public void setTotalVnd(long totalVnd) { this.totalVnd = totalVnd; }
    public Long getVersion() { return version; }
    public void setVersion(Long version) { this.version = version; }
}
~~~

~~~java
public class OrderLine {
    private String sku;
    private int quantity;
    private long unitPriceVnd;

    public OrderLine() {}

    public OrderLine(String sku, int quantity, long unitPriceVnd) {
        this.sku = sku;
        this.quantity = quantity;
        this.unitPriceVnd = unitPriceVnd;
    }

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public int getQuantity() { return quantity; }
    public void setQuantity(int quantity) { this.quantity = quantity; }
    public long getUnitPriceVnd() { return unitPriceVnd; }
    public void setUnitPriceVnd(long unitPriceVnd) {
        this.unitPriceVnd = unitPriceVnd;
    }
}
~~~

Trong dự án Java, đặt `OrderLine` trong file riêng, hoặc dùng nested static class theo thiết kế codebase. Khi ghi Order, `lines` được serialize thành JSON array lồng nhau. `createdAt` trong ví dụ là chuỗi ISO 8601 theo UTC, chẳng hạn `2026-11-25T03:10:00Z`; dùng định dạng **cố định, chuẩn hóa** để truy vấn và sắp xếp theo thời gian. Nếu chọn kiểu `Instant`, phải xác nhận converter, format lưu trữ và index của stack.

**Phân biệt tính nguyên tử:** cập nhật các field trong một document Order là thao tác ở phạm vi một document. Việc cập nhật Order và trừ Stock ở một document khác cần kế hoạch consistency/transaction riêng, dù tất cả đều là Spring Data entities.

## 8. Định nghĩa Repository và tách KV khỏi SQL++

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface CustomerRepository
        extends CouchbaseRepository<CustomerDocument, String> {

    List<CustomerDocument> findByEmail(String email);
}
~~~

~~~java
import java.util.List;
import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {

    List<OrderDocument> findByCustomerIdOrderByCreatedAtDesc(
            String customerId);
}
~~~

Spring Data hiện thực phần lớn các phương thức này từ interface:

- `customers.findById("customer::c-1001")` là **lookup theo document ID**, thường đi qua Data Service/KV và không cần secondary index.
- `customers.findByEmail("an@example.com")` là **derived query theo thuộc tính JSON**, thường dùng SQL++ và index.
- `orders.findByCustomerIdOrderByCreatedAtDesc("c-1001")` tìm nhiều đơn rồi sắp xếp theo ngày; cần SQL++ và index phù hợp.

Phương thức lịch sử đơn trả `List` để minh họa cú pháp. Với hệ thống thực, **không lấy toàn bộ lịch sử không giới hạn**; dùng phân trang/`Pageable` hoặc query có `LIMIT` cùng chính sách tiếp tục trang được kiểm thử. Với dữ liệu thay đổi liên tục, offset pagination có thể lặp/bỏ sót item, nên cân nhắc keyset/cursor theo thứ tự ổn định.

## 9. Luồng UC1–UC3: tạo, đọc và tìm khách hàng

### 9.1. Tạo khách với ID mới

~~~java
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class CustomerService {
    private final CustomerRepository customers;

    public CustomerService(CustomerRepository customers) {
        this.customers = customers;
    }

    public CustomerDocument register(String fullName, String email) {
        String id = "customer::" + UUID.randomUUID();

        CustomerDocument customer = new CustomerDocument(
                id, fullName, email, "ACTIVE", "STANDARD");

        return customers.save(customer);
    }

    public Optional<CustomerDocument> findById(String rawCustomerId) {
        return customers.findById("customer::" + rawCustomerId);
    }

    public List<CustomerDocument> searchByEmail(String email) {
        return customers.findByEmail(email);
    }

    public CustomerDocument updateEmail(
            String rawCustomerId, String email) {
        CustomerDocument current = findById(rawCustomerId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Customer not found"));

        current.setEmail(email);
        return customers.save(current);
    }
}
~~~

Ví dụ `register` đặt ID random để giảm nguy cơ tạo trùng. Cần thêm validation cho email/họ tên, chống input quá dài và xử lý exception/response ở Controller. `updateEmail` dùng `@Version` để phát hiện optimistic locking conflict khi có request khác sửa cùng document; không được retry bằng cách ghi đè tùy tiện.

**Quy tắc email duy nhất là yêu cầu nghiệp vụ riêng.** `findByEmail` và secondary index thông thường **không tự bảo đảm unique email**. Nếu email là định danh duy nhất bắt buộc, cần thiết kế tạo/cập nhật email an toàn trước cạnh tranh, chẳng hạn document ánh xạ email đã chuẩn hóa → customer ID với thao tác tạo có điều kiện và cơ chế xử lý nhiều document phù hợp. Đừng dùng mẫu “query chưa thấy email rồi save” để kết luận chắc chắn không trùng, vì hai request có thể cùng qua bước kiểm tra.

### 9.2. Một request GET theo key

~~~text
GET /customers/c-1001

CustomerController
  -> CustomerService.findById("c-1001")
  -> CustomerRepository.findById("customer::c-1001")
  -> Spring Data mapping -> SDK KV get
  -> Couchbase trả document JSON + metadata
  -> Java CustomerDocument -> HTTP response
~~~

Nếu không có document, chuyển thành HTTP 404 theo hợp đồng API; không trả lỗi kết nối database như 404. Ngoài ra, ID khách hàng đến từ URL phải được xác thực và phân quyền trước khi trả hồ sơ.

### 9.3. Tìm theo email khác hoàn toàn GET theo key

~~~sql
SELECT META(c).id AS documentId, c.fullName, c.email, c.status
FROM `shop`.`crm`.`customers` AS c
WHERE c.email = $email;
~~~

Index minh họa:

~~~sql
CREATE INDEX ix_customers_email
ON `shop`.`crm`.`customers`(email);
~~~

Truy vấn SQL++ trên minh họa ý tưởng, **không phải nguyên văn query Spring Data Repository chắc chắn sinh**. Query của Spring Data có thể bổ sung điều kiện metadata type/discriminator để mapping. Xác nhận kế hoạch với `EXPLAIN`, kiểm tra độ chọn lọc và test trên dữ liệu đại diện. Truyền email dưới dạng **tham số**, không ghép SQL++ từ input.

## 10. Luồng UC4: tạo đơn hàng từ yêu cầu người dùng

Đây là luồng liên kết Customer và Order nhưng chưa cập nhật tồn kho. Request minh họa:

~~~http
POST /customers/c-1001/orders
Content-Type: application/json

{
  "items": [
    { "sku": "SKU-A", "quantity": 2 },
    { "sku": "SKU-B", "quantity": 1 }
  ]
}
~~~

Request không chứa `unitPriceVnd` hoặc `totalVnd` để client không có quyền tự định giá. Một service định giá nội bộ (không triển khai trong ví dụ này) tạo các `OrderLine` với đơn giá tin cậy. Luồng nghiệp vụ:

~~~mermaid
sequenceDiagram
    participant C as OrderController
    participant S as OrderService
    participant CR as CustomerRepository
    participant PR as PricingGateway
    participant OR as OrderRepository
    participant DB as Couchbase
    C->>S: placeOrder(customerId, item requests)
    S->>CR: findById(customerKey)
    CR->>DB: KV get customer
    DB-->>CR: CustomerDocument
    S->>S: Kiểm tra tồn tại, ACTIVE, quyền
    S->>PR: Báo giá SKU/số lượng phía server
    PR-->>S: Các OrderLine đã định giá
    S->>S: Tính tổng bằng số nguyên
    S->>OR: save(new OrderDocument)
    OR->>DB: KV write order
    DB-->>OR: Kết quả ghi
    S-->>C: Order ID và trạng thái CREATED
~~~

### 10.1. Tính tổng bằng số nguyên và chống tràn

Một utility tính tổng:

~~~java
import java.util.List;

public final class OrderTotals {
    private OrderTotals() {}

    public static long calculate(List<OrderLine> lines) {
        if (lines == null || lines.isEmpty()) {
            throw new IllegalArgumentException("Order must contain items");
        }

        long total = 0L;
        for (OrderLine line : lines) {
            if (line == null || line.getSku() == null
                    || line.getSku().isBlank()
                    || line.getQuantity() <= 0
                    || line.getUnitPriceVnd() < 0) {
                throw new IllegalArgumentException("Invalid order line");
            }

            long lineTotal = Math.multiplyExact(
                    (long) line.getQuantity(),
                    line.getUnitPriceVnd());

            total = Math.addExact(total, lineTotal);
        }
        return total;
    }
}
~~~

`Math.multiplyExact` và `Math.addExact` phát hiện tràn `long` bằng exception thay vì âm thầm tạo tổng sai. Service định giá cần bảo đảm giá không âm, đồng tiền, chính sách giảm giá, thuế và phí được thống nhất. Với hệ thống có nhiều currency, phải tính tổng theo từng đơn vị thích hợp, không cộng nhầm các currency.

### 10.2. Service tạo Order

Để giữ ví dụ ngắn và tập trung vào persistence, `placeOrder` dưới đây nhận **danh sách OrderLine đã được hệ thống định giá tin cậy**, không nhận trực tiếp nội dung chưa xác thực từ HTTP.

~~~java
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final CustomerRepository customers;
    private final OrderRepository orders;

    public OrderService(CustomerRepository customers,
                        OrderRepository orders) {
        this.customers = customers;
        this.orders = orders;
    }

    public OrderDocument placeOrder(
            String rawCustomerId,
            List<OrderLine> trustedPricedLines) {

        CustomerDocument customer = customers.findById(
                "customer::" + rawCustomerId
        ).orElseThrow(() ->
                new IllegalArgumentException("Customer not found"));

        if (!"ACTIVE".equals(customer.getStatus())) {
            throw new IllegalStateException("Customer is inactive");
        }

        long totalVnd = OrderTotals.calculate(trustedPricedLines);

        OrderDocument order = new OrderDocument(
                "order::" + UUID.randomUUID(),
                rawCustomerId,
                Instant.now().toString(),
                "CREATED",
                "VND",
                List.copyOf(trustedPricedLines),
                totalVnd);

        return orders.save(order);
    }

    public OrderDocument getOrder(String orderId) {
        return orders.findById("order::" + orderId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Order not found"));
    }
}
~~~

**Hai giới hạn của ví dụ:**

1. Việc khách đang `ACTIVE` tại thời điểm đọc **không tự đảm bảo** trạng thái đó vẫn không đổi ở mọi thời điểm kế tiếp. Nếu quy tắc nghiệp vụ bắt buộc kiểm tra nguyên tử giữa nhiều document, phải thiết kế transaction/điều kiện phù hợp.
2. Nếu client retry `POST` sau timeout, code tạo UUID mới và **có thể tạo hai đơn**. Production nên thiết kế **idempotency key** cho yêu cầu tạo đơn, lưu trạng thái xử lý và xử lý xung đột tạo cùng yêu cầu. Không dựa vào việc một lần gọi trả timeout để kết luận chưa ghi.

Ngoài ra, đối tượng `trustedPricedLines` phải là kết quả snapshot được sao chép/đóng băng theo quy tắc nghiệp vụ để tránh thành phần khác sửa số lượng hoặc giá sau khi tính tổng.

## 11. Luồng UC5–UC6: xem chi tiết và lịch sử đơn

### 11.1. Xem chi tiết đơn theo ID

~~~text
GET /orders/ord-5001
  -> OrderService.getOrder("ord-5001")
  -> OrderRepository.findById("order::ord-5001")
  -> KV get trong shop.sales.orders
  -> OrderDocument
~~~

Với order ID đã biết, **không cần secondary index**. Tuy nhiên, tầng HTTP phải kiểm tra người dùng có quyền xem đơn; việc biết ID không tự cấp quyền.

### 11.2. Lịch sử đơn theo khách hàng dùng SQL++

Với yêu cầu:

~~~text
GET /customers/c-1001/orders?limit=20
~~~

Ta cần lọc `customerId` và sắp theo `createdAt`. SQL++ minh họa:

~~~sql
SELECT META(o).id AS documentId,
       o.customerId, o.createdAt, o.status,
       o.currency, o.totalVnd
FROM `shop`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
ORDER BY o.createdAt DESC, META(o).id DESC
LIMIT 20;
~~~

Index khởi đầu minh họa:

~~~sql
CREATE INDEX ix_orders_customer_created
ON `shop`.`sales`.`orders`(customerId, createdAt DESC);
~~~

Điều kiện `customerId` là **field body của Order**, khác với metadata ID. Đây là đường SQL++/Query Service; index, phân trang, projection và `ORDER BY` phải được kiểm tra trong `EXPLAIN`. Nếu muốn tối ưu cả sắp xếp theo ID làm tie-breaker, cần đối chiếu query plan và khả năng index cụ thể; index trên chỉ là điểm xuất phát.

Câu SQL++ trên chỉ lấy một số field nhằm trình bày danh sách; để ánh xạ đầy đủ thành `OrderDocument`, Spring Data có thể cần projection/metadata bổ sung. Không đưa query projection này vào `@Query` rồi mặc định mapper luôn tái tạo đủ `lines` và mọi field. Có thể trả DTO riêng cho danh sách, còn chi tiết đọc KV theo ID.

### 11.3. Quy tắc phân trang

- Giới hạn kích thước trang ngay ở truy vấn, không đọc toàn bộ lịch sử rồi `subList` trong Java.
- Sắp xếp phải ổn định, nên có tiêu chí phụ khi nhiều đơn cùng thời gian tạo.
- Phân trang kiểu `OFFSET` đơn giản nhưng có thể chậm ở vị trí sâu và lặp/bỏ sót dữ liệu khi có đơn mới chèn vào.
- Với feed lớn, cân nhắc keyset pagination theo `createdAt` và ID, có cursor đủ thông tin và kiểm thử index tương ứng.
- Không để client tùy ý yêu cầu số lượng không giới hạn.

## 12. Luồng UC7: xác nhận đơn và xung đột CAS

Giả sử đơn ở trạng thái `CREATED`. Hai nhân viên đồng thời bấm “Xác nhận”. Nếu không có cơ chế version, request thứ hai có thể ghi dựa trên dữ liệu cũ.

~~~text
T0: A đọc order::ord-5001 (CAS = V1; status = CREATED)
T1: B đọc order::ord-5001 (CAS = V1; status = CREATED)
T2: A đổi status = CONFIRMED, save -> thành công, CAS = V2
T3: B đổi status = CONFIRMED, save với V1 -> xung đột CAS
~~~

Với `@Version`, Spring Data Couchbase có thể phát hiện thay đổi concurrent trên cùng document. Đây là **optimistic locking**. Bản thân CAS không ngăn hai request khác nhau tạo hai đơn mới nếu mỗi request tạo ID khác; vấn đề đó cần idempotency ở chức năng tạo đơn.

Ví dụ service cập nhật:

~~~java
public OrderDocument confirmOrder(String rawOrderId) {
    OrderDocument order = orders.findById(
            "order::" + rawOrderId
    ).orElseThrow(() ->
            new IllegalArgumentException("Order not found"));

    if (!"CREATED".equals(order.getStatus())) {
        throw new IllegalStateException(
                "Order cannot be confirmed from this state");
    }

    order.setStatus("CONFIRMED");
    return orders.save(order);
}
~~~

Đặt method này trong `OrderService` đã có field `orders`. Khi một request gặp optimistic locking exception:

1. Nếu API yêu cầu thao tác do người dùng chủ động xác nhận, thường trả **HTTP 409 Conflict** hoặc thông báo đơn đã bị thay đổi.
2. Nếu nghiệp vụ cho phép retry, phải đọc lại document, đánh giá trạng thái mới rồi áp dụng lại thay đổi; **không retry vô hạn với entity cũ**.
3. Tránh đặt lời gọi thanh toán/gửi email ở giữa đoạn có thể retry, vì retry có thể nhân đôi tác dụng phụ. Có thể tách bằng outbox/idempotent consumer nếu cần.

**Một document cập nhật nguyên tử không đồng nghĩa một workflow nhiều document đã nguyên tử.** Cần phân biệt CAS với transaction.

## 13. Khi nào cần transaction đa document?

Mô hình hiện tại tạo một Order document sau khi đọc Customer; nếu chỉ có đúng một ghi Order, đó là một mutation trên document đơn. Nhưng một hệ thống thực có thể cần:

~~~text
Đặt hàng:
  1. Kiểm tra khách hàng ACTIVE
  2. Trừ số lượng tồn kho trong Inventory document
  3. Tạo Order document
  4. Ghi trạng thái thanh toán/giữ hàng
~~~

Nếu business invariant yêu cầu “tồn kho và đơn phải nhất quán hoặc cùng thất bại”, không thể chỉ gọi `inventoryRepository.save` rồi `orderRepository.save` như hai lệnh độc lập và mặc định có rollback toàn bộ.

Couchbase có khả năng transaction đa document trong các phiên bản hỗ trợ, với API ở SDK và tích hợp Spring Data tùy bộ phiên bản/cấu hình. Trước khi áp dụng, cần làm rõ:

- Các document tham gia transaction thuộc những collection nào?
- Tất cả thao tác đọc/ghi liên quan có thực sự chạy trong **transaction context**?
- Cần mức cô lập, durability, timeout và cơ chế retry nào?
- Timeout sau commit có thể khiến client không biết trạng thái cuối; có idempotency key để tra cứu không?
- External payment API có nằm ngoài transaction database không? Nếu có, cần xử lý nghiệp vụ xuyên hệ thống bằng idempotency/outbox/saga phù hợp.

Không suy rằng annotation `@Transactional` ở một method Spring bất kỳ tự đảm bảo transaction Couchbase nếu transaction manager và các API chưa được cấu hình tương thích. Tương tự, một lệnh CAS không thay thế transaction nhiều document.

### 13.1. Sơ đồ ranh giới workflow

~~~mermaid
flowchart TD
    A["Place order request"] --> V["Validate customer and price"]
    V --> T{"Cần atomicity nhiều document?"}
    T -->|Không| O["Save Order document"]
    T -->|Có| C["Couchbase transaction qua API hỗ trợ"]
    C --> INV["Update inventory + create Order"]
    O --> EV["Ghi kết quả/đáp ứng"]
    INV --> EV
    EV --> OUT["External effects qua cơ chế đáng tin cậy, idempotent"]
~~~

Ví dụ là sơ đồ quyết định, không phải một transaction implementation hoàn chỉnh; phần giao dịch phải được viết và kiểm thử dựa trên phiên bản SDK/Spring Data đang sử dụng.

## 14. TTL, session và dữ liệu nào không nên tự hết hạn

**Không nên đặt TTL mặc định ngắn cho Customer hoặc Order** chỉ vì Couchbase hỗ trợ expiry. Đơn hàng thường cần giữ theo chính sách kế toán, chăm sóc khách hàng và yêu cầu lưu trữ. TTL hữu ích với **session đăng nhập, mã tạm, cache** hoặc giỏ hàng khách vãng lai có vòng đời rõ ràng.

Ví dụ SDK KV đặt expiry cho session 30 phút trong collection `shop.auth.sessions` (minh họa API Couchbase Java SDK 3.x):

~~~java
import java.time.Duration;
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.kv.UpsertOptions;

public class SessionGateway {
    private final Collection sessions;

    public SessionGateway(Cluster cluster) {
        sessions = cluster.bucket("shop")
                .scope("auth")
                .collection("sessions");
    }

    public void put(String opaqueSessionId, String rawCustomerId) {
        JsonObject payload = JsonObject.create()
                .put("customerId", rawCustomerId);

        sessions.upsert(
                "session::" + opaqueSessionId,
                payload,
                UpsertOptions.upsertOptions()
                        .expiry(Duration.ofMinutes(30))
        );
    }
}
~~~

- `opaqueSessionId` phải là giá trị ngẫu nhiên an toàn và được xử lý theo yêu cầu bảo mật của hệ thống; không in session token ra log.
- `expiry` là metadata document, **khác với** một trường JSON `expiresAt` tự định nghĩa.
- Việc cập nhật session qua API khác có thể giữ hoặc thay expiry theo option/phiên bản; cần có hợp đồng rõ ràng.
- Expiry phục vụ vòng đời dữ liệu, không phải hệ thống lịch tác vụ được bảo đảm kích hoạt đúng từng mili giây.

Một session còn tồn tại trong database cũng không đủ để cấp quyền; ứng dụng vẫn phải kiểm tra token, thiết bị, logout/revocation và chính sách xác thực.

## 15. Reactive: chuyển luồng ví dụ khi dùng WebFlux

Nếu ứng dụng dùng Spring MVC và nhiều thành phần I/O đồng bộ, Repository đồng bộ như trên là lựa chọn dễ đọc. Nếu toàn bộ HTTP pipeline dùng WebFlux, có thể chọn `ReactiveCouchbaseRepository` hoặc `ReactiveCouchbaseTemplate` để giữ truy cập I/O không chặn.

Repository reactive:

~~~java
import reactor.core.publisher.Flux;
import org.springframework.data.couchbase.repository.ReactiveCouchbaseRepository;

public interface ReactiveOrderRepository
        extends ReactiveCouchbaseRepository<OrderDocument, String> {

    Flux<OrderDocument> findByCustomerId(String customerId);
}
~~~

Service reactive cho hai đường đọc:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public class ReactiveOrderReadService {
    private final ReactiveOrderRepository orders;

    public ReactiveOrderReadService(ReactiveOrderRepository orders) {
        this.orders = orders;
    }

    public Mono<OrderDocument> getOrder(String rawOrderId) {
        return orders.findById("order::" + rawOrderId);
    }

    public Flux<OrderDocument> listOrders(String rawCustomerId) {
        return orders.findByCustomerId(rawCustomerId);
    }
}
~~~

Trong ví dụ trên, `getOrder` thường đọc theo KV, `listOrders` truy vấn theo field `customerId` và index. `Flux<OrderDocument>` là luồng kết quả nhiều document; cần giới hạn/phân trang trước khi cho UI đọc khối lượng lớn.

Một pipeline reactive tạo đơn vẫn phải **định giá ở phía server, validate customer, tính tổng và gọi save**. Không dùng `Mono.just(syncRepository.findById(...))` để giả làm truy cập non-blocking; lệnh đồng bộ vẫn chạy trước khi Publisher được tạo. Không gọi `block()` trong WebFlux event loop, không tự `subscribe()` trong service rồi bỏ qua lỗi.

**Reactive không thay đổi business invariant**: CAS, TTL, transaction, quyền truy cập, chính sách index và idempotency vẫn bắt buộc. Nó giúp sử dụng thread hiệu quả khi có nhiều thao tác chờ I/O, không bảo đảm một query thiếu index chạy nhanh.

## 16. Dùng CouchbaseTemplate hoặc Java SDK ở đâu trong ứng dụng này?

Repository đáp ứng CRUD và truy vấn đơn giản. Tuy nhiên, có thể bổ sung một lớp persistence bằng `CouchbaseTemplate` cho bộ lọc đơn hàng có nhiều điều kiện tùy chọn, hoặc dùng Java SDK để thực hiện thao tác KV chuyên biệt.

| Nhu cầu | API có thể chọn | Điều cần nhớ |
| --- | --- | --- |
| Lấy khách theo ID, tạo khách | `CouchbaseRepository` | Theo KV/document mapping |
| Tìm khách theo email | Repository derived query | SQL++ + index, không tự bảo đảm email unique |
| Lọc đơn với nhiều bộ lọc động | `CouchbaseTemplate` hoặc custom repository | Xây query rõ ràng, mapping/projection đúng |
| Đọc document thô và metadata CAS | Couchbase Java SDK | Cần hiểu JSON/schema và handling exception |
| Cập nhật một phần document | SDK sub-document API khi phù hợp | Không ghi đè field khác; xử lý CAS và expiry |
| Tìm văn bản mô tả sản phẩm | SDK Search/FTS nếu có collection sản phẩm | Search index riêng, không thay index SQL++ |
| Luồng I/O WebFlux | Reactive Repository/Template/SDK | Kiểm soát concurrency/backpressure |

Ví dụ đọc trực tiếp Order JSON bằng SDK:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.json.JsonObject;

public class RawOrderGateway {
    private final Collection orders;

    public RawOrderGateway(Cluster cluster) {
        this.orders = cluster.bucket("shop")
                .scope("sales")
                .collection("orders");
    }

    public JsonObject getRaw(String rawOrderId) {
        return orders.get("order::" + rawOrderId)
                .contentAsObject();
    }
}
~~~

SDK trả về JSON body, **không tự áp dụng toàn bộ converter/annotation mapping của Spring Data**. Nếu một code path dùng SDK `upsert` chỉ với vài field, nó có thể vô tình xóa field khác và metadata type do Spring Data cần. Hai cách truy cập có thể kết hợp nhưng phải thống nhất keyspace, schema, CAS, TTL, durability, mapping và quyền truy cập.

## 17. Tính nhất quán: vừa tạo đơn rồi truy vấn lịch sử không thấy

Một trường hợp dễ gây nhầm lẫn:

~~~text
T0: orders.save(newOrder) hoàn tất
T1: orders.findById(orderId) -> đọc theo KV
T2: orders.findByCustomerIdOrderByCreatedAtDesc(customerId)
    -> truy vấn theo SQL++/secondary index
~~~

Đường KV không cần secondary index để tìm document theo ID. Trong khi đó, SQL++ phụ thuộc index cho truy vấn field. Index có thể cập nhật bất đồng bộ so với mutation, vì vậy kết quả query với scan consistency mặc định **có thể tạm thời chưa chứa đơn vừa tạo**.

Nếu yêu cầu UX là “vừa đặt hàng xong phải thấy đơn ngay”, có các phương án:

1. Sau khi tạo đơn, dùng chính kết quả `save`/Order ID để hiển thị trang xác nhận; không phụ thuộc ngay vào query lịch sử.
2. Nếu bắt buộc query danh sách ngay sau ghi, chọn mức scan consistency phù hợp như `request_plus` hoặc consistency theo mutation token khi API/phiên bản hỗ trợ, và chấp nhận độ trễ thêm.
3. Nếu chấp nhận cập nhật sau một khoảng ngắn, thiết kế thông điệp hoặc cơ chế refresh rõ ràng, nhưng không được dùng kết quả search/index cũ để quyết định thanh toán hoặc trừ tồn kho.

Transaction và CAS giải quyết những bài toán khác; chúng không tự làm mọi secondary/Search index cập nhật tức thì ở mọi đường truy cập.

## 18. HTTP API contract và xử lý lỗi

Có thể xây REST API như sau:

| Method + path | Thành công | Lỗi nghiệp vụ tiêu biểu |
| --- | --- | --- |
| `POST /customers` | 201 + customer ID | 400 input sai; 409 nếu quy tắc định danh/email bị xung đột |
| `GET /customers/{id}` | 200 + customer | 404 không tìm thấy; 403 không có quyền |
| `PATCH /customers/{id}/email` | 200 + customer mới | 404 không tìm thấy; 409 optimistic locking conflict |
| `GET /customers?email=...` | 200 + danh sách phù hợp | 400 email input không hợp lệ |
| `POST /customers/{id}/orders` | 201 + order ID | 400 items sai; 404/409 với customer; 409 idempotency conflict |
| `GET /orders/{id}` | 200 + order | 404 hoặc 403 |
| `GET /customers/{id}/orders` | 200 + trang lịch sử | 400 tham số phân trang sai |
| `POST /orders/{id}/confirm` | 200 + trạng thái mới | 404; 409 trạng thái không hợp lệ/CAS conflict |

Phân biệt **404 do không có document** với **503/timeout do database không sẵn sàng**; không biến tất cả exception thành “không tìm thấy”. Tùy mô hình phân quyền, có thể chủ động trả 404 thay vì 403 để tránh lộ tồn tại tài nguyên; đó là quyết định bảo mật API.

### 18.1. Lỗi kỹ thuật cần được ánh xạ rõ

| Vấn đề | Hậu quả nếu bỏ qua | Phản ứng phù hợp |
| --- | --- | --- |
| CAS mismatch | Mất cập nhật hoặc trả lỗi khó hiểu | Chuyển thành 409 hoặc retry có kiểm soát |
| Query thiếu index | Lịch sử đơn lỗi/chậm | Kiểm tra query plan, index và lỗi SQL++ |
| Couchbase timeout | Không rõ ghi đã commit hay chưa | Tra idempotency/status trước khi retry |
| Client gửi giá sản phẩm | Đơn sai tiền | Server-side pricing |
| Khách bị vô hiệu hóa | Tạo đơn trái quy tắc | Kiểm tra trạng thái và transaction khi cần |
| Truy cập đơn của người khác | Lộ thông tin | Authorization ở service/API |
| Danh sách lịch sử quá lớn | Tăng bộ nhớ và độ trễ | Giới hạn/pagination tại query |
| TTL sai | Session sống quá lâu hoặc hết hạn sớm | Quy chuẩn expiry theo loại document |

## 19. Kiểm thử tích hợp và kiểm chứng hiệu năng

Bài học không chạy thử Couchbase trực tiếp. Khi đưa ví dụ vào dự án, cần chuẩn bị cluster/test environment, đúng bucket/scope/collection, tài khoản và index. Có thể dùng Testcontainers nếu môi trường và phiên bản hỗ trợ; quan trọng là phép thử thực sự đi qua Couchbase, không chỉ mock Repository rồi kết luận mapping/query đúng.

### 19.1. Bộ kiểm thử cần có

1. **Mapping:** Lưu Customer, Order có nested lines; đọc lại JSON/entity, xác nhận key và converter.
2. **CRUD/KV:** Tạo customer, đọc đúng key, đọc key không tồn tại, xóa có quyền và quy tắc nghiệp vụ.
3. **SQL++:** Tìm customer theo email và list order theo customer ID; xác nhận index đúng scope/collection và projection.
4. **CAS:** Hai bản đọc cùng document, một bản ghi trước, bản còn lại phải nhận optimistic locking conflict.
5. **Idempotency:** Gửi lại request đặt hàng cùng khóa; chỉ có một đơn được coi là kết quả cuối cùng.
6. **Consistency:** Ghi Order rồi thử query lịch sử ở các mức scan consistency đã chọn.
7. **TTL:** Session hết hạn theo expiry thực tế; cập nhật session không vô tình thay đổi chính sách.
8. **Transaction:** Khi có tồn kho đa document, mô phỏng lỗi giữa các mutation và xác nhận kết quả commit/rollback hoặc workflow bù trừ.
9. **Bảo mật:** Một khách không được đọc Order của khách khác bằng ID.
10. **Tải:** Đọc theo key, query lịch sử, xung đột CAS và thời gian chờ ở mức traffic đại diện.

### 19.2. Những metric hữu ích

| Metric | Điều cần nhận biết |
| --- | --- |
| KV read/write latency p95/p99 | Độ trễ thao tác biết key |
| Query latency, `EXPLAIN`, scan/fetch | Hiệu quả SQL++ và index |
| CAS conflict rate | Document/aggregate bị tranh chấp |
| Retry, timeout, ambiguous result | Tải khuếch đại và trạng thái ghi chưa rõ |
| Query index freshness | Độ trễ nhìn thấy đơn mới trong danh sách |
| Document size, số order mỗi customer | Ranh giới aggregate và phân trang có phù hợp không |
| JVM heap/GC và connection usage | Nút thắt ở ứng dụng |
| CPU/tài nguyên Data/Query/Index Service | Nút thắt ở Couchbase cluster |

## 20. Bài tập thực hành và tự đánh giá

### Bài tập A — Lịch sử đơn hàng

Người dùng `c-1001` có 10.000 đơn. Màn hình chỉ cần 20 đơn mới nhất.

**Hỏi:** Có nên đọc toàn bộ document Order bằng `findByCustomerId` rồi `stream().limit(20)` trong Java?

**Gợi ý:** Không. Truy vấn có `WHERE customerId`, `ORDER BY createdAt DESC` và `LIMIT 20`; dùng index phù hợp, phân trang có thứ tự ổn định và giới hạn dữ liệu truyền.

### Bài tập B — Email đã tồn tại

Hai request đồng thời đăng ký cùng email. Cả hai gọi `findByEmail` và đều thấy danh sách rỗng, rồi mỗi request `save` một Customer với UUID khác nhau.

**Hỏi:** Vì sao vẫn xuất hiện hai khách cùng email?

**Gợi ý:** Lookup rồi insert không phải ràng buộc nguyên tử trên email; secondary index thường không tự áp đặt uniqueness. Cần chiến lược định danh/điều kiện tạo và xử lý ghi đồng thời.

### Bài tập C — Xác nhận đơn bằng hai tab

Hai nhân viên cùng đọc đơn `CREATED` và cùng xác nhận. Một người lưu trước.

**Hỏi:** `@Version` giúp gì và service cần làm gì khi nhận conflict?

**Gợi ý:** CAS phát hiện thay đổi trên document. Trả 409 hoặc đọc lại và đánh giá trạng thái mới; tránh retry mù quáng.

### Bài tập D — Thêm tồn kho

Hệ thống nay cần giảm `Inventory` khi lưu `Order`.

**Hỏi:** Gọi lần lượt `inventory.save` rồi `order.save` đã đủ chưa?

**Gợi ý:** Chưa nếu cần cả hai cùng thành công. Xác định transaction đa document và idempotency; thanh toán ngoài database có thể cần outbox/saga.

### Bài tập E — Reactive

Ứng dụng chuyển sang WebFlux và viết `Mono.just(orderRepository.findById(id))`.

**Hỏi:** Đoạn này có non-blocking không?

**Gợi ý:** Không. Lời gọi Repository đồng bộ chạy trước khi tạo Mono. Dùng Reactive Repository/Template hoặc cô lập blocking theo cơ chế chuyển tiếp có kiểm soát.

## 21. Checklist triển khai

- [ ] Đã quyết định bucket, scope, collection cho Customer, Order, Session và tạo đúng tài nguyên.
- [ ] Document ID ổn định, không chứa bí mật; ID ở metadata và field nghiệp vụ được phân biệt.
- [ ] Customer và Order tách thành aggregate riêng; order lines là snapshot hợp lý.
- [ ] Các Java entity được mapping đúng collection; converter và metadata type tương thích.
- [ ] `findById` dùng KV; query theo email/customerId có secondary index và `EXPLAIN` đạt yêu cầu.
- [ ] Giá và tổng tiền được xác thực/tính tại server với quy tắc số nguyên, chống tràn.
- [ ] Có validation, authorization, idempotency key và response lỗi rõ cho thao tác đặt hàng.
- [ ] Cập nhật trạng thái dùng CAS/`@Version`, xử lý conflict đúng nghiệp vụ.
- [ ] Nếu ghi nhiều document bắt buộc atomic, đã xác minh transaction API và retry semantics.
- [ ] TTL chỉ được áp dụng cho dữ liệu phù hợp; Customer/Order có chính sách lưu trữ riêng.
- [ ] Mức query consistency đáp ứng UX “vừa tạo đơn đã thấy” ở những luồng bắt buộc.
- [ ] API reactive (nếu dùng) giữ pipeline non-blocking và kiểm soát đồng thời.
- [ ] Đã kiểm thử mapping, SQL++, conflict, TTL, error path và tải đại diện.

## 22. Kết luận

Ví dụ quản lý **khách hàng và đơn hàng** cho thấy cách Spring Data Couchbase kết nối **document mapping**, **Repository**, **CouchbaseTemplate** và **Couchbase Java SDK** thành một tầng truy cập có chủ đích: biết document ID thì đọc/ghi KV, cần tìm nhiều bản ghi thì dùng SQL++ với index, sửa cùng một document thì bảo vệ bằng CAS, còn workflow ghi nhiều document phải xem xét transaction và idempotency.

Thiết kế tốt bắt đầu từ **nghiệp vụ và access pattern**. Khi đặt đúng ranh giới Customer/Order, chọn bucket/scope/collection rõ ràng, snapshot giá tin cậy, kiểm soát concurrency, TTL và query consistency, ứng dụng có cơ sở để phát triển dễ dàng trong Spring đồng thời đáp ứng tính đúng đắn, hiệu năng và khả năng vận hành thực tế.

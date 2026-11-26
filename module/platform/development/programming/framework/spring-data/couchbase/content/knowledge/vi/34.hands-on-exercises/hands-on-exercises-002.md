# Thiết kế khóa đơn hàng và kiểm tra yêu cầu tạo lặp trong Spring Data Couchbase

> **Chương:** Bài thực hành  
> **Học phần:** `SPRING_DATA_COUCHBASE` — xây dựng tầng truy cập Couchbase bằng Spring Data với document mapping, repository, `CouchbaseTemplate` và SQL++; kết hợp bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và API reactive để quản lý hiệu năng, tính nhất quán và khả năng vận hành.

## 1. Mục tiêu và sản phẩm đầu ra

Bài này giải quyết tình huống rất thực tế: **người dùng nhấn “Đặt hàng” hai lần, HTTP client retry sau timeout hoặc hai bản sao ứng dụng nhận cùng một lệnh tạo đơn đồng thời**. Mục tiêu không chỉ “không sinh ID trùng”, mà phải có một *hợp đồng nghiệp vụ* giúp nhận biết yêu cầu nào thực sự là cùng một thao tác.

Sau thực hành, bạn có thể:

1. Thiết kế document key đơn hàng ổn định, có namespace tenant và không lộ dữ liệu cá nhân.
2. Phân biệt **document ID**, **order number**, **Idempotency-Key** và **request fingerprint**.
3. Chuẩn hóa request thành một biểu diễn ổn định trước khi băm fingerprint.
4. Dùng thao tác **create-only `insert`** thay vì `existsById` rồi `save/upsert`.
5. Kết hợp Spring Data `@Document`, `@Id`, `@Version`, `@Scope`, `@Collection` với `CouchbaseTemplate.insertById`.
6. Dùng `CouchbaseRepository.findById` (KV) để đọc lại bản ghi khi gặp duplicate.
7. Trả **201 Created** cho lệnh mới, **200 OK** cho replay cùng nội dung, **409 Conflict** khi một key được tái sử dụng với nội dung khác.
8. Phân loại lỗi timeout **ambiguous** mà không vội khẳng định thao tác chưa xảy ra.
9. Viết integration tests kiểm tra yêu cầu lặp, hai requests cạnh tranh, payload khác nhau và timeout.
10. Biết giới hạn của một-document idempotency: transaction nhiều document, external payment, expiry, backup/DR và business dedup không tự được giải quyết.

### 1.1. Sản phẩm HTTP

~~~http
POST /tenants/LAB1/orders
Idempotency-Key: checkout-20261125-a1b2c3
Content-Type: application/json

{
  "customerCode": "CUS001",
  "sku": "BOOK001",
  "quantity": 2
}
~~~

Từ một request hợp lệ, API tạo đúng **một document đơn hàng** ở Couchbase collection `sales.orders`. Gửi lại cùng tenant, cùng key và cùng payload sẽ **trả về đơn hàng đã tạo** thay vì tạo đơn thứ hai. Gửi cùng key nhưng thay `quantity` phải bị từ chối.

### 1.2. Tiêu chí thành công

| Thử nghiệm | Kết quả mong đợi |
|---|---|
| Lần đầu tạo đơn với key mới | `201 Created`, có `orderId` |
| Lặp cùng key và cùng business payload | `200 OK`, cùng `orderId`, không nhân số đơn |
| Lặp cùng key nhưng payload khác | `409 Conflict`, document gốc không bị ghi đè |
| Cùng payload nhưng dùng key khác | Được coi là **command khác** trong contract bài học |
| Hai requests đồng thời cùng key | Chỉ tối đa một insert thành công; request còn lại phải được xử lý duplicate/pending/unknown có kiểm soát |
| Mutation timeout ambiguous | Không sinh ID mới, không kết luận chắc chắn chưa commit |
| KV `get(id)` thấy document phù hợp | Có thể đối chiếu trạng thái hiện có; không dùng SQL++ stale để phủ nhận |

**Phạm vi:** một document `OrderDocument` lưu phần cốt lõi của lệnh tạo đơn. Bài không thực hiện trừ tồn kho, thanh toán hoặc gửi email thật. Những side effect đó cần workflow/transaction/idempotency riêng.

## 2. Vì sao CRUD thông thường dễ tạo đơn lặp?

Giả sử client gửi:

~~~text
T0: Người dùng bấm Đặt hàng.
T1: Server tạo UUID-A, insert order::UUID-A.
T2: Couchbase đã lưu order A.
T3: HTTP response bị mất; client thấy timeout.
T4: Client bấm lại hoặc gateway tự retry.
T5: Server tạo UUID-B, insert order::UUID-B.
T6: Có hai đơn cho một lần checkout.
~~~

**Couchbase không làm sai**: `UUID-A` và `UUID-B` là hai document IDs khác nhau. Database chỉ biết hai yêu cầu insert hợp lệ; nó không biết rằng nghiệp vụ muốn xử lý chúng như **một lệnh**.

Tình huống còn có thể phát sinh khi:

- Mobile app timeout, người dùng bấm lại.
- Gateway/load balancer retry POST vì upstream disconnect.
- Consumer nhận lại message sau khi chưa ack.
- Một background job được chạy hai lần.
- Hai instances của service cùng xử lý một checkout key.
- Java SDK đã dispatch mutation nhưng response không đến caller.

Muốn chống lặp, **identity của business command phải ổn định qua retry**; identity của mỗi HTTP attempt có thể khác.

## 3. Bốn loại định danh không nên đánh đồng

| Định danh | Mục đích | Có đổi khi retry cùng command? |
|---|---|---|
| **Idempotency-Key** | Caller gắn một khóa cho một business command | **Không** |
| **Document ID** | Khóa KV để Couchbase định tuyến và bảo đảm không có hai documents cùng ID trong một collection | **Không** |
| **Order number** | Mã hiển thị cho khách hàng, theo quy tắc kinh doanh | Không, sau khi tạo |
| **Request/trace ID** | Theo dõi một lần HTTP attempt trong logs | **Có thể có** |

Bài lab chọn thiết kế **document ID được suy ra từ tenant + Idempotency-Key**. Điều này giúp dùng `insert` như phép **đăng ký command atomically theo một key**.

~~~text
Tenant: LAB1
Idempotency-Key: checkout-20261125-a1b2c3
Hash: SHA-256 của chính Idempotency-Key

Document ID:
order::LAB1::<64 ký tự hex SHA-256>
~~~

Không lưu Idempotency-Key thô vào document key. Dữ liệu khách hàng/email/số điện thoại cũng không nằm trong key.

### 3.1. Tại sao không dùng email hoặc giỏ hàng làm ID?

Một người có thể đặt hai đơn giống hệt vào hai ngày khác nhau. Nếu dùng `email+sku+quantity` làm document ID, hai lệnh độc lập có thể va nhau, khiến request hợp lệ bị coi là retry. Ngược lại, cùng checkout nhưng payload đổi thì **không nên âm thầm tạo đơn mới dưới cùng key**.

**Idempotency key xác định command**, còn fingerprint xác định **nội dung command**. Hai khái niệm này cần tồn tại đồng thời.

### 3.2. Hạn mức key Couchbase và phân vùng tenant

Couchbase document key có giới hạn kích thước theo SDK/Server, thường tối đa **250 bytes** đối với KV document ID. Với prefix `order::`, tenant ID tối đa 32 ký tự ASCII và hash SHA-256 hex 64 ký tự, key trong lab luôn ngắn và dễ kiểm soát.

ID chỉ unique trong **một collection**. Nếu hai collections khác nhau đều chứa cùng chuỗi key, đó là hai documents độc lập. Đối với multi-tenant, tenant prefix là một lớp phân vùng identity; **authorization vẫn phải được thực thi riêng**.

## 4. Sơ đồ xử lý idempotent create

~~~mermaid
flowchart TD
    A["POST /tenants/{tenant}/orders<br/>Idempotency-Key"]
    B["Validate và normalize payload"]
    C["Derive deterministic document ID<br/>+ request fingerprint"]
    D["Couchbase KV INSERT create-only"]
    E{"Kết quả insert?"}
    F["201 Created<br/>Trả order mới"]
    G["KV get theo cùng ID"]
    H{"Fingerprint và tenant khớp?"}
    I["200 OK<br/>Trả order đã có"]
    J["409 Conflict<br/>Key đã gắn với nội dung khác"]
    K["Kết quả chưa xác minh<br/>503/contract tương ứng"]
    A --> B --> C --> D --> E
    E -->|"Success"| F
    E -->|"DocumentExists"| G
    E -->|"Ambiguous"| G
    E -->|"Lỗi khác"| K
    G --> H
    H -->|"Có"| I
    H -->|"Không"| J
    G -.->|"Không đọc được / chưa thấy"| K
~~~

Sơ đồ chỉ minh họa đường quyết định. Lỗi khác không tự động được đánh đồng là ambiguous: validation/configuration/query/keyspace lỗi cần phân loại riêng. Khi insert **ambiguous**, một lần đọc hiện thấy document phù hợp chứng minh nó **đang tồn tại** theo KV, nhưng **không phải bằng chứng mutation ban đầu đã đạt mọi mức durability yêu cầu** trong mọi cấu hình/fallback.

### 4.1. Race condition và điểm tuyến tính hóa

Nếu hai instances A và B cùng gọi `insert(orderId)`, server không tạo hai documents cùng ID trong cùng collection. Một request có thể được ghi thành công, request kia nhận duplicate, error trong lúc pending hoặc outcome chưa rõ tùy timing.

Không cần lock trong Java theo từng process để bảo vệ single key; lock chỉ trong process A **không điều phối** process B. Điểm quyết định đúng phải là **KV insert create-only tại server**.

## 5. Những thiết kế sai nên nhận diện trước khi viết code

### 5.1. Sai: tạo UUID mới ở mỗi HTTP attempt

~~~java
// SAI nếu đây là identity của cùng một checkout.
String orderId = "order::" + UUID.randomUUID();
repository.save(new OrderDocument(/* ... */));
~~~

Nếu client retry, ID lại khác → Couchbase thấy một document khác. UUID hoàn toàn phù hợp cho **một business command mới**, nhưng phải được tạo **một lần và giữ qua retries**, không tạo trong handler cho từng attempt của cùng command.

### 5.2. Sai: `existsById` rồi `save`

~~~java
// SAI: check-then-write không atomic.
if (!repository.existsById(orderId)) {
    repository.save(order);
}
~~~

Hai requests có thể cùng thấy không tồn tại rồi chạy tiếp. Chỉ tạo được một bản khi operation cuối cùng có **insert-only semantics**; pre-check không bảo đảm điều đó. Nếu code sau đó gọi upsert, request thứ hai còn có thể ghi đè bản đầu.

### 5.3. Sai: dùng `upsert` để “chữa lỗi tạo trùng”

~~~java
// SAI cho contract Create-only.
template.upsertById(OrderDocument.class).one(order);
~~~

`upsert` nghĩa là *create or replace*. Khi hai payload khác nhau cùng ID, request sau có thể sửa/xóa thông tin request trước thay vì trả 409.

### 5.4. Sai: dùng SQL++ không thấy row làm bằng chứng chưa tạo

GSI cập nhật bất đồng bộ. `SELECT ... WHERE checkoutId = ...` theo `NOT_BOUNDED` có thể chưa thấy document vừa được KV commit. Khi đã biết ID, dùng **KV `findById(id)`**. Ngay cả KV not-found một lần trong tình huống SyncWrite pending/ambiguous cũng chưa đủ chứng minh lần ghi trước sẽ không hoàn tất sau đó.

## 6. Chuẩn bị dự án và môi trường lab

### 6.1. Stack và công cụ

- Java 21 hoặc JDK tương thích Spring Boot version bạn chọn.
- Spring Boot với `Spring Web`, `Spring Data Couchbase`, `Validation` và `Spring Boot Test`.
- Couchbase Server/Capella hỗ trợ bucket, scope và collection.
- Maven hoặc Gradle do Spring Initializr sinh BOM phù hợp.
- Couchbase Web Console hoặc công cụ quản trị **chỉ dành cho lab**.
- HTTP client như `curl`, HTTP files của IDE hoặc Postman.

Không cố định tổ hợp Spring Boot, Spring Data Couchbase và Couchbase Java SDK bằng cách tự chọn ngẫu nhiên từng version. Dùng BOM tương thích và kiểm tra method signatures theo dependency thực tế.

### 6.2. Dependencies Maven

Ví dụ phần dependencies trong project **đã được Spring Initializr tạo**:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-couchbase</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đây là fragment, không phải `pom.xml` đầy đủ; parent/BOM, version Java và build plugins do Initializr cung cấp. Bài không ép một patch version cụ thể mà chưa có build thực tế.

### 6.3. Cấu trúc file Java

~~~text
src/main/java/com/example/order/
  OrderApplication.java
  CreateOrderRequest.java
  OrderResponse.java
  OrderDocument.java
  OrderIdentity.java
  OrderRepository.java
  OrderService.java
  OrderController.java
  OrderExceptionHandler.java
src/main/resources/application.yml
src/test/java/com/example/order/
  OrderIdempotencyIT.java
~~~

Từng snippet Java bên dưới là một file độc lập trong `package com.example.order;`. Hãy giữ đúng tên class/record và imports khi chép vào project.

## 7. Keyspace và dữ liệu đơn hàng

Trong lab, chuẩn bị:

~~~text
Bucket: commerce_lab
Scope:  sales
Collection: orders
Key example:
order::LAB1::407a...<64 ký tự hex>
~~~

Tạo bucket/scope/collection bằng công cụ quản trị được phép. Tài khoản runtime nên có quyền **Data Reader/Data Writer** trên keyspace tương ứng; không dùng admin account của lab làm credential lâu dài cho app.

Không tạo primary index chỉ để thực hiện insert/findById: **KV không cần SQL++/GSI**. Những bài mở rộng tìm kiếm theo `status` hoặc `customerCode` mới cần index phù hợp.

### 7.1. Lược đồ document

Một order sau khi được lưu:

~~~json
{
  "tenantId": "LAB1",
  "customerCode": "CUS001",
  "sku": "BOOK001",
  "quantity": 2,
  "fingerprint": "e305...<SHA-256 hex>",
  "status": "CREATED",
  "createdAt": "2026-11-25T03:00:00Z"
}
~~~

`id` là **document key của Couchbase**; `@Version`/CAS là metadata, có thể không là field JSON tương ứng. Spring Data có thể thêm discriminator `_class`; đừng dùng một câu SQL++ không có đủ predicate rồi coi document mất.

### 7.2. Cấu hình Spring Boot

~~~yaml
spring:
  couchbase:
    connection-string: "${CB_CONNECTION_STRING}"
    username: "${CB_USERNAME}"
    password: "${CB_PASSWORD}"
  data:
    couchbase:
      bucket-name: commerce_lab

server:
  port: 8080
~~~

`CB_CONNECTION_STRING` trên lab local có thể là `couchbase://127.0.0.1`; Capella thường cần `couchbases://...` và certificate trust chain hợp lệ. Không tắt xác minh TLS để “sửa” lỗi handshake.

Ứng dụng:

~~~java
package com.example.order;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

## 8. Thiết kế DTO: chỉ client được quyết định nội dung lệnh

Không cho caller tự đặt các trường `id`, `fingerprint`, `createdAt`, `version` hoặc `status` khi tạo order. Dùng DTO khác Entity.

~~~java
package com.example.order;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public record CreateOrderRequest(
    @NotBlank
    @Pattern(regexp = "[A-Za-z0-9_-]{3,40}")
    String customerCode,

    @NotBlank
    @Pattern(regexp = "[A-Za-z0-9_-]{3,40}")
    String sku,

    @Min(1) @Max(1000)
    int quantity
) {}
~~~

Đơn lab chỉ có một SKU và quantity để tập trung vào idempotency. Giá bán thực, khuyến mại và tồn kho phải được lấy/kiểm tra ở server, không tin price truyền từ client.

DTO phản hồi:

~~~java
package com.example.order;

public record OrderResponse(
    String orderId,
    String tenantId,
    String customerCode,
    String sku,
    int quantity,
    String status,
    String version,
    String createdAt
) {}
~~~

Service cần phân biệt **đơn mới tạo** và **đơn có sẵn được phát lại**:

~~~java
package com.example.order;

public record CreateOrderResult(
    OrderResponse body,
    boolean newlyCreated
) {}
~~~

`newlyCreated=true` để controller trả 201; `false` cho phép trả 200. Chúng là **quy tắc API lab**; các API production có thể chọn replay cùng status/body lần đầu theo contract khác, miễn không phát side effect mới.

## 9. Entity Spring Data: mapping và CAS

~~~java
package com.example.order;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.couchbase.core.mapping.Collection;
import org.springframework.data.couchbase.core.mapping.Document;
import org.springframework.data.couchbase.core.mapping.Scope;

@Document
@Scope("sales")
@Collection("orders")
public class OrderDocument {

    @Id
    private String id;

    @Version
    private Long version;

    private String tenantId;
    private String customerCode;
    private String sku;
    private int quantity;
    private String fingerprint;
    private String status;
    private String createdAt;

    public OrderDocument() {}

    public OrderDocument(
            String id, String tenantId,
            String customerCode, String sku,
            int quantity, String fingerprint,
            String status, String createdAt) {
        this.id = id;
        this.tenantId = tenantId;
        this.customerCode = customerCode;
        this.sku = sku;
        this.quantity = quantity;
        this.fingerprint = fingerprint;
        this.status = status;
        this.createdAt = createdAt;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public Long getVersion() { return version; }
    public void setVersion(Long version) { this.version = version; }

    public String getTenantId() { return tenantId; }
    public void setTenantId(String tenantId) {
        this.tenantId = tenantId;
    }

    public String getCustomerCode() { return customerCode; }
    public void setCustomerCode(String customerCode) {
        this.customerCode = customerCode;
    }

    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }

    public int getQuantity() { return quantity; }
    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }

    public String getFingerprint() { return fingerprint; }
    public void setFingerprint(String fingerprint) {
        this.fingerprint = fingerprint;
    }

    public String getStatus() { return status; }
    public void setStatus(String status) {
        this.status = status;
    }

    public String getCreatedAt() { return createdAt; }
    public void setCreatedAt(String createdAt) {
        this.createdAt = createdAt;
    }
}
~~~

### 9.1. `@Version` không phải bộ đếm nghiệp vụ

`@Version Long` biểu diễn Couchbase CAS token, không phải trường `version++`. Spring Data nhận metadata CAS khi đọc/ghi; không tự đặt nó bằng thời gian hoặc một số counter.

Trong bài create-only, `@Version` không cần thiết cho tính duy nhất của `insert`, nhưng có ích khi sau này cập nhật `OrderDocument.status` qua `replace` có điều kiện. CAS **không** thay thế durability hay idempotency.

### 9.2. Không áp TTL cho đơn hàng lâu dài trong lab

Order là dữ liệu nghiệp vụ cần đối soát; nếu tự cho expiry 60 giây, một retry hợp lệ sau 61 giây có thể tạo lại đơn. Bài không đặt TTL cho `orders`. Nếu tách một idempotency record có TTL, retention của nó phải bao phủ cửa sổ retry/reconciliation và không phá dữ liệu nguồn.

## 10. Thiết kế thuật toán key và fingerprint

Đặt yêu cầu rõ:

- Tenant ID chỉ dùng ký tự ASCII trong `[A-Z0-9_-]` sau khi normalize; độ dài 2–32.
- `Idempotency-Key` dài 8–128, gồm `[A-Za-z0-9._~-]`, **case-sensitive** và không được trim/đổi chữ hoa chữ thường.
- `customerCode`, `sku` được trim và uppercase để những khác biệt định dạng mà domain cho phép quy về cùng lệnh.
- `quantity` là số nguyên dương; không so raw JSON text.
- **Fingerprint có version prefix** để sau này thay schema vẫn kiểm soát compatibility.
- Hash bằng SHA-256; `orderId` dùng hash của Idempotency-Key, `fingerprint` dùng hash của canonical payload.

### 10.1. Vì sao băm hai thứ khác nhau?

~~~text
tenant = LAB1
idempotencyKey = checkout-20261125-a1b2c3

orderId = "order::" + tenant + "::"
        + SHA256(idempotencyKey)

fingerprint = SHA256(
    version + tenant + normalized customerCode
    + normalized sku + quantity
)
~~~

Khi cùng key nhưng payload thay đổi, **document ID vẫn giữ nguyên**, còn fingerprint khác; đó là tín hiệu **409 Conflict**. Khi key khác, ID khác, kể cả payload trùng nhau: một khách hàng được phép đặt hai đơn giống hệt nếu đó là hai commands có chủ đích.

Không khẳng định SHA-256 giúp bảo mật tuyệt đối trước đoán key: nếu idempotency key có entropy thấp hoặc có thể đoán, hash không thay thế quyền truy cập. Production nên yêu cầu key đủ entropy; cân nhắc HMAC trong các tình huống cần chống enumeration.

## 11. OrderIdentity: chuẩn hóa không phụ thuộc request attempt

Đây là helper Java có thể chạy mà không cần kết nối Couchbase:

~~~java
package com.example.order;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Locale;
import java.util.regex.Pattern;

public final class OrderIdentity {
    private static final Pattern TENANT =
        Pattern.compile("[A-Z0-9_-]{2,32}");
    private static final Pattern KEY =
        Pattern.compile("[A-Za-z0-9._~-]{8,128}");
    private static final Pattern CODE =
        Pattern.compile("[A-Z0-9_-]{3,40}");

    private OrderIdentity() {}

    public record NewOrder(
        String orderId,
        String tenantId,
        String customerCode,
        String sku,
        int quantity,
        String fingerprint
    ) {}

    public static NewOrder of(
            String rawTenant,
            String idempotencyKey,
            CreateOrderRequest body) {

        String tenant = uppercase(rawTenant);
        if (!TENANT.matcher(tenant).matches()) {
            throw new IllegalArgumentException("Tenant ID không hợp lệ");
        }
        if (idempotencyKey == null ||
                !KEY.matcher(idempotencyKey).matches()) {
            throw new IllegalArgumentException(
                "Idempotency-Key không hợp lệ");
        }
        if (body == null) {
            throw new IllegalArgumentException("Thiếu body");
        }

        String customer = uppercase(body.customerCode());
        String sku = uppercase(body.sku());
        if (!CODE.matcher(customer).matches() ||
                !CODE.matcher(sku).matches()) {
            throw new IllegalArgumentException(
                "customerCode/sku không hợp lệ");
        }
        if (body.quantity() < 1 || body.quantity() > 1000) {
            throw new IllegalArgumentException(
                "quantity phải trong [1,1000]");
        }

        // Đặt tenant vào ID để cách ly namespace, không lộ key thô.
        String orderId = "order::" + tenant
                + "::" + sha256Hex(idempotencyKey);

        // Framing độ dài loại bỏ ambiguity do nối chuỗi,
        // version prefix hỗ trợ thay schema ở tương lai.
        String canonical = "order-create-v1\n"
                + framed(tenant)
                + framed(customer)
                + framed(sku)
                + body.quantity() + "\n";

        return new NewOrder(
            orderId, tenant, customer, sku,
            body.quantity(), sha256Hex(canonical)
        );
    }

    private static String uppercase(String value) {
        return value == null
            ? ""
            : value.trim().toUpperCase(Locale.ROOT);
    }

    private static String framed(String value) {
        return value.length() + ":" + value + "\n";
    }

    public static String sha256Hex(String value) {
        try {
            byte[] bytes = MessageDigest
                .getInstance("SHA-256")
                .digest(value.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(bytes);
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }
}
~~~

### 11.1. Những gì thuật toán này đảm bảo

- Hai attempts cùng tenant/key → cùng `orderId`.
- Hai payload tương đương sau chuẩn hóa → cùng fingerprint.
- Cùng key nhưng quantity khác → fingerprint khác.
- Hai tenants khác nhau → keyspace định danh khác.
- Code đã validate không có dấu phân cách/Unicode khó lường trong `tenant`, và hash giữ độ dài ID ổn định.

### 11.2. Những gì nó *không* tự đảm bảo

- Hai idempotency keys khác nhau không thể cùng đại diện một đơn: **chưa có business dedup**.
- Email/payment/stock external side effects không lặp: **chưa có workflow bảo vệ**.
- Các chuỗi hiển thị là định danh an toàn qua authentication: **chưa có authorization**.
- Bảo đảm không mất dữ liệu sau mất cluster: **cần durability/backup/DR**.
- Canonicalization version có thể thay dễ dàng mà không ảnh hưởng retry cũ: **phải có chính sách compatibility**.

### 11.3. Khi request schema thay đổi

Nếu thêm coupon, deliveryAddress hoặc currency, cần xác định field đó có ảnh hưởng business command không. Những field có ảnh hưởng phải nằm trong fingerprint; nếu không, caller có thể dùng cùng key nhưng một nội dung mới được coi là replay.

Khi thay format canonical, phải giữ khả năng so request cũ trong cửa sổ replay, ví dụ versioned canonicalizer hoặc lưu danh sách fields/hash algorithm đã áp dụng trên record. Không triển khai fingerprint mới rồi tự báo 409 cho tất cả retries cũ.

## 12. Repository và Template: tách đường create và đường read

Repository:

~~~java
package com.example.order;

import org.springframework.data.couchbase.repository.CouchbaseRepository;

public interface OrderRepository
        extends CouchbaseRepository<OrderDocument, String> {
}
~~~

`findById(orderId)` đọc theo KV ID qua Data Service và không yêu cầu GSI. `save` có thể chọn insert/replace theo entity state và `@Version`, nhưng để **hợp đồng create-only dễ review**, bài sử dụng `CouchbaseTemplate.insertById`:

~~~java
OrderDocument inserted = template
    .insertById(OrderDocument.class)
    .one(newDocument);
~~~

Sự phân chia này có dụng ý:

| Tác vụ | API | Ý nghĩa |
|---|---|---|
| Đăng ký một lệnh tạo đơn mới | `CouchbaseTemplate.insertById` | Atomic create-only cùng document ID |
| Kiểm tra đơn đã có khi duplicate | `OrderRepository.findById` | KV get theo ID, không phụ thuộc GSI |
| Cập nhật trạng thái sau này | `repository.save` với CAS hoặc `Template.replaceById` | Chống lost update |
| Tìm theo status/customerCode | Derived SQL++ query hoặc template query | Cần GSI, scan consistency thích hợp |
| Tạo hoặc ghi đè không kiểm tra | `upsertById` | **Không phù hợp** contract tạo đơn trong bài |

### 12.1. Spring Data mapping vẫn áp dụng

Vì Template được gọi với `OrderDocument.class`, framework dùng metadata `@Id`, `@Scope`, `@Collection` và mapping converter. Không trộn trực tiếp SDK `JsonObject` với Spring entity rồi giả định mọi annotation tự được áp dụng ở cả hai đường.

### 12.2. Minimum durability của bucket

Trong lab 1 Data node/0 replica, dùng create-only mặc định để học idempotency; đó **không** chứng minh chịu mất node. Nếu muốn kiểm thử mức ghi `MAJORITY` hoặc `PERSIST_TO_MAJORITY`, cần bucket type/topology/replicas phù hợp và đặt level trên metadata/Template hoặc SDK cho đúng operation. Durability là **yêu cầu xác nhận ghi**, không thay tính tạo một lần theo ID.

## 13. OrderService: phân biệt tạo mới, replay và xung đột

`OrderService` gọi `insertById` để lưu **chính xác một document theo ID**, rồi dùng repository `findById` khi cần đối chiếu yêu cầu lặp.

~~~java
package com.example.order;

import java.time.Instant;
import java.util.Locale;
import java.util.Optional;

import com.couchbase.client.core.error.AmbiguousTimeoutException;
import com.couchbase.client.core.error.DocumentExistsException;
import com.couchbase.client.core.error.DurabilityAmbiguousException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.couchbase.core.CouchbaseTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final CouchbaseTemplate template;
    private final OrderRepository repository;

    public OrderService(CouchbaseTemplate template,
                        OrderRepository repository) {
        this.template = template;
        this.repository = repository;
    }

    public CreateOrderResult create(
            String rawTenant,
            String idempotencyKey,
            CreateOrderRequest request) {
        OrderIdentity.NewOrder identity =
                OrderIdentity.of(rawTenant, idempotencyKey, request);

        OrderDocument candidate = new OrderDocument(
            identity.orderId(),
            identity.tenantId(),
            identity.customerCode(),
            identity.sku(),
            identity.quantity(),
            identity.fingerprint(),
            "CREATED",
            Instant.now().toString()
        );

        try {
            // Create-only: không kiểm tra exists rồi upsert.
            OrderDocument saved = template
                    .insertById(OrderDocument.class)
                    .one(candidate);
            return new CreateOrderResult(toResponse(saved), true);
        } catch (RuntimeException failure) {
            if (hasCause(failure, DocumentExistsException.class)
                    || hasCause(failure, DuplicateKeyException.class)) {
                return inspectExisting(identity);
            }
            if (hasCause(failure, AmbiguousTimeoutException.class)
                    || hasCause(failure, DurabilityAmbiguousException.class)) {
                // Response có thể đã mất SAU KHI server commit.
                return inspectExisting(identity);
            }
            // Auth, config, network errors khác không mặc nhiên
            // là duplicate hoặc ambiguous.
            throw failure;
        }
    }

    public OrderResponse get(String rawTenant, String orderId) {
        String tenant = rawTenant == null
            ? ""
            : rawTenant.trim().toUpperCase(Locale.ROOT);

        if (!tenant.matches("[A-Z0-9_-]{2,32}")
                || orderId == null
                || !orderId.matches(
                    "order::[A-Z0-9_-]{2,32}::[a-f0-9]{64}")
                || !orderId.startsWith(
                    "order::" + tenant + "::")) {
            throw new NotFound("Không tìm thấy đơn hàng.");
        }

        OrderDocument existing = repository.findById(orderId)
                .orElseThrow(() ->
                    new NotFound("Không tìm thấy đơn hàng."));
        if (!tenant.equals(existing.getTenantId())) {
            throw new NotFound("Không tìm thấy đơn hàng.");
        }
        return toResponse(existing);
    }

    private CreateOrderResult inspectExisting(
            OrderIdentity.NewOrder identity) {

        final Optional<OrderDocument> found;
        try {
            // KV theo ID; không đi qua SQL++/GSI.
            found = repository.findById(identity.orderId());
        } catch (RuntimeException readFailure) {
            throw new Unconfirmed(
                "Không thể xác minh kết quả tạo đơn.",
                readFailure
            );
        }

        if (found.isEmpty()) {
            // Có thể mutation cũ đang pending khi timeout.
            throw new Unconfirmed(
                "Document chưa thấy khi đối soát, kết quả còn chưa rõ."
            );
        }

        OrderDocument existing = found.get();
        if (!identity.tenantId().equals(existing.getTenantId())
                || !identity.fingerprint().equals(
                    existing.getFingerprint())) {
            throw new Conflict(
                "Idempotency-Key đã gắn với payload khác."
            );
        }

        // Không insert lần hai, không đổi createdAt.
        return new CreateOrderResult(toResponse(existing), false);
    }

    private static boolean hasCause(
            Throwable root, Class<? extends Throwable> expected) {
        Throwable cursor = root;
        for (int i = 0; i < 16 && cursor != null; i++) {
            if (expected.isInstance(cursor)) return true;
            if (cursor.getCause() == cursor) break;
            cursor = cursor.getCause();
        }
        return false;
    }

    private static OrderResponse toResponse(OrderDocument doc) {
        return new OrderResponse(
            doc.getId(),
            doc.getTenantId(),
            doc.getCustomerCode(),
            doc.getSku(),
            doc.getQuantity(),
            doc.getStatus(),
            String.valueOf(doc.getVersion()),
            doc.getCreatedAt()
        );
    }

    public static class Conflict extends RuntimeException {
        public Conflict(String message) { super(message); }
    }

    public static class NotFound extends RuntimeException {
        public NotFound(String message) { super(message); }
    }

    public static class Unconfirmed extends RuntimeException {
        public Unconfirmed(String message) { super(message); }
        public Unconfirmed(String message, Throwable cause) {
            super(message, cause);
        }
    }
}
~~~

### 13.1. Tại sao không dùng `repository.save` trong create?

Với Spring Data Couchbase, `save` quyết định insert/replace tùy entity state và `@Version`. Điều đó hữu ích cho CRUD, nhưng ở bài idempotency ta muốn **create-only** hiển thị rõ ngay trong code. `template.insertById(OrderDocument.class).one(candidate)` diễn đạt chính xác ý định này. Nếu dùng Repository `save` trên entity mới, phải test kỹ semantics insert và lỗi trùng ID ở phiên bản Spring Data đang chạy.

### 13.2. Vì sao cần phân loại exception có chọn lọc?

Spring Data có thể dịch/bọc SDK exceptions. `hasCause` tìm `DocumentExistsException`/`DuplicateKeyException` và hai nhóm ambiguous. Những exception khác được truyền tiếp; không được bắt mọi `DataAccessException` rồi biến thành 409 hoặc replay. Nếu duplicate được framework dịch sang lớp khác trong version đang dùng, **điều chỉnh sau integration test** và ghi nguyên nhân rõ.

### 13.3. Vì sao replay không ghi đè?

Lệnh insert thứ hai không thành công, rồi service đọc document đã tồn tại. Timestamp mới sinh trong candidate không được dùng để thay `createdAt` cũ. Nếu business workflow khác đã chuyển `status` sang `PAID` hợp lệ, replay chỉ trả **trạng thái hiện có**, không ép `CREATED` lại.

### 13.4. Một lần KV readback có giới hạn

Trong nhánh ambiguous, đọc thấy record có fingerprint phù hợp là bằng chứng nó **đang hiện diện ở KV**, nhưng **không chứng minh chính mutation trước đã đạt mọi mức durability** trong mọi cấu hình/fallback. Đọc not-found một lần cũng không chứng minh thao tác cũ sẽ không commit nếu SyncWrite còn pending. Nếu chưa rõ, service trả `Unconfirmed` để caller giữ nguyên key và workflow đối soát tiếp tục.

## 14. Controller: REST 201 Created và 200 replay

~~~java
package com.example.order;

import java.net.URI;
import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/tenants/{tenantId}/orders")
public class OrderController {
    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<OrderResponse> create(
            @PathVariable String tenantId,
            @RequestHeader("Idempotency-Key") String key,
            @Valid @RequestBody CreateOrderRequest body) {

        CreateOrderResult result =
            service.create(tenantId, key, body);

        URI location = URI.create(
            "/tenants/" + result.body().tenantId()
                + "/orders/" + result.body().orderId()
        );

        if (result.newlyCreated()) {
            return ResponseEntity.created(location)
                .body(result.body());
        }
        return ResponseEntity
            .status(HttpStatus.OK)
            .location(location)
            .body(result.body());
    }

    @GetMapping("/{orderId}")
    public OrderResponse get(
            @PathVariable String tenantId,
            @PathVariable String orderId) {
        return service.get(tenantId, orderId);
    }
}
~~~

### 14.1. Idempotency-Key bắt buộc

Nếu thiếu header, Spring MVC trả 400. Nếu key không phù hợp regex/độ dài, `OrderIdentity` từ chối trước khi có mutation. Header phân biệt chữ hoa/chữ thường **ở giá trị**, không phải tên header. Client phải giữ nguyên value qua mọi retries của cùng checkout.

### 14.2. Tenant từ URL chưa phải bằng chứng ủy quyền

Code lab kiểm tra document thuộc tenant mà caller cung cấp, nhưng **không có authentication/authorization**. Khi triển khai production, tenant phải lấy hoặc đối chiếu với user identity/session được xác minh; không cho caller truy cập tenant khác bằng cách sửa URL.

## 15. ExceptionHandler: conflict khác kết quả chưa xác minh

~~~java
package com.example.order;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class OrderExceptionHandler {

    @ExceptionHandler(OrderService.Conflict.class)
    public ResponseEntity<ProblemDetail> conflict(
            OrderService.Conflict error) {
        return fail(HttpStatus.CONFLICT,
            "ORDER_KEY_CONFLICT",
            "Idempotency-Key đã gắn với nội dung khác.");
    }

    @ExceptionHandler(OrderService.NotFound.class)
    public ResponseEntity<ProblemDetail> missing(
            OrderService.NotFound error) {
        return fail(HttpStatus.NOT_FOUND,
            "ORDER_NOT_FOUND", "Không tìm thấy đơn hàng.");
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ProblemDetail> invalid(
            IllegalArgumentException error) {
        return fail(HttpStatus.BAD_REQUEST,
            "INVALID_ORDER_REQUEST", "Request không hợp lệ.");
    }

    @ExceptionHandler(OrderService.Unconfirmed.class)
    public ResponseEntity<ProblemDetail> unconfirmed(
            OrderService.Unconfirmed error) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(
            HttpStatus.SERVICE_UNAVAILABLE,
            "Chưa xác minh được kết quả tạo đơn. "
                + "Hãy giữ nguyên Idempotency-Key."
        );
        body.setProperty("code", "ORDER_OUTCOME_UNCONFIRMED");
        return ResponseEntity
            .status(HttpStatus.SERVICE_UNAVAILABLE)
            .header("Retry-After", "2")
            .body(body);
    }

    private ResponseEntity<ProblemDetail> fail(
            HttpStatus status, String code, String detail) {
        ProblemDetail body =
            ProblemDetail.forStatusAndDetail(status, detail);
        body.setProperty("code", code);
        return ResponseEntity.status(status).body(body);
    }
}
~~~

`Retry-After: 2` là chính sách minh họa, **không phải cam kết mutation sẽ hoàn tất sau hai giây**. `503 ORDER_OUTCOME_UNCONFIRMED` không có nghĩa “đơn chưa được tạo”; đó là tình huống **cần đối soát**.

Một timeout/connection/configuration error khác chưa được phân loại sẽ đi theo error handling chung, không được tự đổi thành 409. Khi muốn `202 Accepted`, phải có inbox/queue bền đã thực sự nhận command và status endpoint; một timeout Couchbase chưa tạo được contract đó.

## 16. Gửi HTTP lần đầu và phát lại cùng lệnh

### 16.1. Lần đầu

~~~http
POST /tenants/LAB1/orders HTTP/1.1
Host: localhost:8080
Idempotency-Key: checkout-20261125-a1b2c3
Content-Type: application/json

{
  "customerCode": "CUS001",
  "sku": "BOOK001",
  "quantity": 2
}
~~~

Phản hồi minh họa:

~~~http
HTTP/1.1 201 Created
Location: /tenants/LAB1/orders/order::LAB1::<SHA256_HEX>
Content-Type: application/json
~~~

~~~json
{
  "orderId": "order::LAB1::<SHA256_HEX>",
  "tenantId": "LAB1",
  "customerCode": "CUS001",
  "sku": "BOOK001",
  "quantity": 2,
  "status": "CREATED",
  "version": "<CAS_TOKEN>",
  "createdAt": "2026-11-25T03:00:00Z"
}
~~~

`<SHA256_HEX>` và `<CAS_TOKEN>` chỉ là placeholders trong response mẫu; thực tế server trả key hash và CAS giá trị thật.

### 16.2. Replay cùng tenant, key, payload

~~~http
POST /tenants/LAB1/orders HTTP/1.1
Host: localhost:8080
Idempotency-Key: checkout-20261125-a1b2c3
Content-Type: application/json

{
  "customerCode": "CUS001",
  "sku": "BOOK001",
  "quantity": 2
}
~~~

Kỳ vọng `200 OK`, cùng `orderId`, cùng `createdAt` như bản gốc; **không có insert mới thành công**.

### 16.3. Tái sử dụng key với payload khác

~~~http
POST /tenants/LAB1/orders HTTP/1.1
Host: localhost:8080
Idempotency-Key: checkout-20261125-a1b2c3
Content-Type: application/json

{
  "customerCode": "CUS001",
  "sku": "BOOK001",
  "quantity": 5
}
~~~

Kỳ vọng `409 Conflict`, mã lỗi `ORDER_KEY_CONFLICT` và document gốc vẫn có `quantity=2`.

### 16.4. Cùng payload nhưng key mới

Dùng `Idempotency-Key: checkout-20261125-NEWREQ` thì `orderId` mới; đây được coi là **đơn hàng mới** trong contract của bài học. Nếu sản phẩm muốn chặn lặp do client lỡ tạo key mới cho mỗi click, phải sửa client giữ command key qua retry hoặc thêm business dedup policy; Couchbase không đoán được ý định caller.

## 17. Tìm theo ID không cần GSI

Đường chống lặp trong bài:

~~~text
tenant + Idempotency-Key
    -> deterministic document ID
    -> Couchbase KV INSERT
    -> nếu trùng, KV GET theo cùng ID
    -> so tenant và fingerprint
~~~

Không cần secondary index cho insert/findById. Nếu thêm tìm kiếm theo khách hàng/trạng thái, lúc đó cần SQL++/GSI:

~~~sql
CREATE INDEX ix_orders_customer_status
ON `commerce_lab`.`sales`.`orders`
    (tenantId, customerCode, status);
~~~

~~~sql
SELECT META(o).id AS orderId, o.customerCode, o.status
FROM `commerce_lab`.`sales`.`orders` AS o
WHERE o.tenantId = "LAB1"
  AND o.customerCode = "CUS001"
  AND o.status = "CREATED";
~~~

GSI cập nhật bất đồng bộ từ DCP. Vì vậy `NOT_BOUNDED` SQL++ không thấy order mới **chưa chứng minh** mutation thất bại. `REQUEST_PLUS` chờ index mới hơn nhưng không nâng durability của mutation trước. Để đối soát command biết ID, dùng KV get, không dùng một câu SQL++ mặc định.

## 18. Hai requests đồng thời: điều gì thực sự được bảo đảm?

~~~mermaid
sequenceDiagram
    participant A as App instance A
    participant B as App instance B
    participant KV as Couchbase Data Service
    A->>KV: INSERT order::LAB1::HASH
    B->>KV: INSERT order::LAB1::HASH
    KV-->>A: SUCCESS
    KV-->>B: DOCUMENT_EXISTS hoặc trạng thái khác theo timing
    B->>KV: GET theo cùng ID
    KV-->>B: Order đã tạo bởi A
    Note over A,B: Fingerprint khớp -> replay
~~~

Đây là trường hợp điển hình, **không** cam kết B luôn nhận duplicate ngay. Nếu SyncWrite đang pending, caller có thể gặp `DurableWriteInProgressException`, timeout, ambiguous hoặc chưa đọc được. Test concurrency phải xác minh **trạng thái cuối cùng**, đồng thời ghi nhận các outcomes trung gian.

### 18.1. Tại sao lock trong một pod không đủ?

~~~java
// Không điều phối được request ở pod B:
synchronized (this) {
    // chỉ bảo vệ một JVM instance
}
~~~

Idempotency qua `insert` cùng deterministic key là tính chất **phía database**, hoạt động với nhiều ứng dụng instances. Khi command cần nhiều documents atomic, một key insert không thay thế transaction.

### 18.2. Điều test cần xác minh

- Cùng tenant, key và payload → cùng key/document ID.
- Không tạo hai documents cho cùng ID/command.
- Replay không làm thay `createdAt`.
- Payload khác cùng key không bị “last write wins”.
- Pending/ambiguous được đánh dấu chờ xác minh, không retry bằng ID khác.
- Nếu backend bị lỗi, không trả 201 giả.

## 19. Unit test cho thuật toán identity, không cần Couchbase

Đầu tiên kiểm chứng phần thuần Java. Một test không cần Spring Boot hay server giúp phát hiện lỗi normalization/key derivation trước khi đưa vào các tình huống concurrency phức tạp.

~~~java
package com.example.order;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class OrderIdentityTest {

    @Test
    void sameKeyAndCanonicalPayloadHaveSameIdentity() {
        String key = "checkout-20261125-a1b2c3";

        var first = OrderIdentity.of(
            "lab1", key,
            new CreateOrderRequest("cus001", "book001", 2)
        );
        var retry = OrderIdentity.of(
            "LAB1", key,
            new CreateOrderRequest("CUS001", "BOOK001", 2)
        );

        assertEquals(first.orderId(), retry.orderId());
        assertEquals(first.fingerprint(), retry.fingerprint());
        assertEquals("LAB1", first.tenantId());
    }

    @Test
    void sameKeyDifferentPayloadRetainsIdButChangesFingerprint() {
        String key = "checkout-20261125-a1b2c3";
        var original = OrderIdentity.of(
            "LAB1", key,
            new CreateOrderRequest("CUS001", "BOOK001", 2)
        );
        var altered = OrderIdentity.of(
            "LAB1", key,
            new CreateOrderRequest("CUS001", "BOOK001", 5)
        );

        assertEquals(original.orderId(), altered.orderId());
        assertNotEquals(
            original.fingerprint(), altered.fingerprint());
    }

    @Test
    void differentKeysAndTenantsHaveDifferentIds() {
        var body = new CreateOrderRequest(
            "CUS001", "BOOK001", 2
        );

        var one = OrderIdentity.of(
            "LAB1", "checkout-key-00001", body);
        var anotherKey = OrderIdentity.of(
            "LAB1", "checkout-key-00002", body);
        var anotherTenant = OrderIdentity.of(
            "LAB2", "checkout-key-00001", body);

        assertNotEquals(one.orderId(), anotherKey.orderId());
        assertNotEquals(one.orderId(), anotherTenant.orderId());
    }

    @Test
    void invalidKeyIsRejectedBeforeDatabaseCall() {
        assertThrows(IllegalArgumentException.class, () ->
            OrderIdentity.of(
                "LAB1", "bad key with spaces",
                new CreateOrderRequest("CUS001", "BOOK001", 2)
            )
        );
    }
}
~~~

**Kỳ vọng:** toàn bộ test này chạy mà không cần Couchbase. Nó chứng minh **tính quyết định của hàm key/fingerprint**, chưa chứng minh `insert` atomic, mapping Spring Data hay hành vi của server khi timeout.

### 19.1. Tăng độ bao phủ của unit test

Thử thêm:

- `Idempotency-Key` khác chữ hoa/thường → key khác (theo contract case-sensitive).
- SKU `"book001"` và `"BOOK001"` → fingerprint giống (vì lab chủ ý normalize).
- Tenant khác với cùng key → `orderId` khác.
- `quantity=0`, tenant quá dài, key rỗng hoặc ký tự xuống dòng → bị từ chối.
- Trường fingerprint mới trong schema version 2 → không vô tình “trùng” schema v1.

## 20. Integration test với Couchbase lab: same key, same payload

Để xác minh atomic insert và Spring Data exception mapping, cần chạy integration tests **trên bucket lab được phép**, với collection và credentials riêng; đừng trỏ CI mặc định vào production.

~~~java
package com.example.order;

import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
@EnabledIfEnvironmentVariable(named = "RUN_CB_IT", matches = "true")
class OrderIdempotencyIT {
    @Autowired OrderService service;
    @Autowired OrderRepository repository;

    @Test
    void replayReturnsOriginalOrderAndChangedPayloadConflicts() {
        String key = "test-" + UUID.randomUUID();
        var payload = new CreateOrderRequest(
            "CUS001", "BOOK001", 2
        );

        CreateOrderResult created =
            service.create("LAB1", key, payload);
        String id = created.body().orderId();

        try {
            assertTrue(created.newlyCreated());

            CreateOrderResult replay =
                service.create("LAB1", key, payload);

            assertFalse(replay.newlyCreated());
            assertEquals(id, replay.body().orderId());
            assertEquals(
                created.body().createdAt(),
                replay.body().createdAt()
            );

            assertThrows(OrderService.Conflict.class, () ->
                service.create(
                    "LAB1", key,
                    new CreateOrderRequest(
                        "CUS001", "BOOK001", 5
                    )
                )
            );

            OrderDocument original =
                repository.findById(id).orElseThrow();
            assertEquals(2, original.getQuantity());
        } finally {
            // Dọn document chỉ khi biết chắc ID của bài test.
            // Nếu outcome chưa rõ, lưu evidence để đối soát
            // trước khi cleanup.
            repository.deleteById(id);
        }
    }
}
~~~

Bài không chạy test này; người học cần cung cấp `CB_CONNECTION_STRING`, `CB_USERNAME`, `CB_PASSWORD`, bucket `commerce_lab`/scope `sales`/collection `orders` và đặt `RUN_CB_IT=true` trên môi trường thử nghiệm.

### 20.1. Đây là contract test của cả REST và persistence

Test trên gọi service trực tiếp: nó kiểm tra insert/readback và business decisions. Để kiểm tra HTTP status 201/200/409, bổ sung `MockMvc`/`WebTestClient` hoặc chạy bộ HTTP requests ở mục 16.

### 20.2. Duplicate exception phải được kiểm chứng

Nếu lần thứ hai ném exception khác ngoài `DocumentExistsException` hoặc `DuplicateKeyException`, test sẽ thất bại. Điều này hữu ích: cần xem **Spring Data exception translation thực tế** và cập nhật `hasCause` theo version, không lặng lẽ thay handler thành catch-all.

### 20.3. Tên test không đồng nghĩa “đã chạy thành công”

Một đoạn `@Test` trong tài liệu là **mã mẫu**, không phải bằng chứng đã có cluster/test execution. Kết luận chính thức chỉ được đưa ra sau khi chạy trên dependency versions cụ thể và lưu test report.

## 21. Kiểm thử hai lệnh cạnh tranh thật sự

Nếu chỉ chạy request tuần tự, bạn chưa xác minh race khi hai app instances cùng insert. Tạo concurrent clients **chỉ trên lab**, có hạn mức:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

// Giả sử service và repository được inject.
String key = "parallel-test-" + java.util.UUID.randomUUID();
var payload = new CreateOrderRequest(
    "CUS001", "BOOK001", 2
);
var identity = OrderIdentity.of("LAB1", key, payload);

var executor = Executors.newFixedThreadPool(2);
var start = new CountDownLatch(1);

Callable<Object> call = () -> {
    start.await();
    try {
        return service.create("LAB1", key, payload);
    } catch (RuntimeException error) {
        // Lưu đầy đủ classification để báo cáo,
        // không giả định mọi request đều thành công.
        return error;
    }
};

try {
    Future<Object> a = executor.submit(call);
    Future<Object> b = executor.submit(call);
    start.countDown();

    Object resultA = a.get(10, TimeUnit.SECONDS);
    Object resultB = b.get(10, TimeUnit.SECONDS);

    // Quan sát resultA/resultB và error classes ở đây.
    // Assertion quan trọng: trạng thái CUỐI CÙNG
    // ở chính ID không thể có hai documents.
    var stored = repository.findById(
        identity.orderId()).orElseThrow();

    assert stored.getFingerprint()
        .equals(identity.fingerprint());
} finally {
    executor.shutdownNow();
}
~~~

**Đây là đoạn code minh họa logic concurrency**, không phải test JUnit hoàn chỉnh. Trong test thực, dùng `Assertions.assertEquals` thay vì Java `assert` (vì assert có thể bị tắt), lưu hai outcomes và cleanup sau khi đã đối soát.

### 21.1. Điều nên đo hơn số HTTP 200

Có thể xuất hiện `Unconfirmed`, timeout hoặc pending-write error tùy thời điểm. Việc hai callers không đồng thời nhận 200 **không tự chứng minh** server tạo trùng. Quan trọng là:

- Cùng key chỉ có một document.
- Document cuối có fingerprint mong đợi.
- Trạng thái không xác định được lưu để retry/reconcile đúng.
- Không có side effect ngoài database bị phát lại.

### 21.2. Không tạo test load vô hạn

Một bài concurrency idempotency không cần 10.000 requests/s. Hãy bắt đầu hai callers, sau đó tăng có giới hạn và xem SDK/cluster metrics; tránh khiến lab quá tải rồi kết luận sai rằng insert không atomic.

## 22. Lab mô phỏng response loss và ambiguous timeout

Một lỗi thực tế không phải chỉ “node ngừng phục vụ”; response có thể mất **sau commit**.

~~~mermaid
sequenceDiagram
    participant Client as API client
    participant Service as Order service
    participant Data as Couchbase Data Service
    Client->>Service: POST + Idempotency-Key K
    Service->>Data: INSERT orderId(K)
    Data->>Data: Commit document
    Data--xService: Response không tới caller
    Service-->>Client: Timeout / trạng thái chưa xác minh
    Client->>Service: Retry cùng K và payload
    Service->>Data: INSERT orderId(K)
    Data-->>Service: Document exists
    Service->>Data: KV get(orderId(K))
    Data-->>Service: Order có fingerprint khớp
    Service-->>Client: 200, trả record ban đầu
~~~

Chỉ dùng test proxy/fault injection **có phê duyệt trên lab**, không cô lập node hoặc tắt network production để minh họa. Nếu mô phỏng bằng mock ở service, ghi rõ đó chỉ là kiểm tra business state machine, **không chứng minh SDK/server thật phát `AmbiguousTimeoutException` theo một fault cụ thể**.

### 22.1. Những trường hợp phải tách riêng

| Tình huống | Diễn giải đúng |
|---|---|
| Response mất sau commit, readback thấy record | Có bản hiện tại để đối soát, replay đúng key |
| Request chưa dispatch, unambiguous timeout | Có thể retry có kiểm soát với cùng key |
| SyncWrite còn pending khi caller timeout | Một lần KV not-found chưa đủ kết luận thất bại |
| Backend tạm không truy cập được sau timeout | Trả trạng thái chưa xác minh, không đổi ID |
| Replica không đủ majority | Có thể không đáp ứng durability, không tự hạ level |
| HTTP gateway trả 504 sớm hơn SDK | HTTP timeout không hủy chắc chắn KV mutation |

### 22.2. Reconciliation cần nguồn bền nếu workflow dài

Ví dụ `OrderService.Unconfirmed` được trả trong HTTP request hiện tại. Nếu nghiệp vụ phải tiếp tục tự đối soát sau khi app crash, cần **record trạng thái lệnh hoặc inbox bền phù hợp** với owner, deadline, retry policy và cảnh báo. Chỉ ném exception và ghi log không bảo đảm command sẽ được xử lý về sau.

## 23. Sai lầm của reactive retry khi tạo ID trong subscription

Nếu ứng dụng triển khai bằng `ReactiveCouchbaseTemplate` hoặc Couchbase Java SDK reactive, `Mono` là một publisher có thể được subscribe nhiều lần. Cách làm sau rất nguy hiểm:

~~~java
// PHẢN VÍ DỤ: mỗi subscription sinh ID mới.
Mono<?> unsafe = Mono.defer(() ->
    orders.reactive().insert(
        "order::" + java.util.UUID.randomUUID(),
        json,
        insertOptions()
    )
).retryWhen(reactor.util.retry.Retry.max(3));
~~~

Khi lần đầu đã commit nhưng response mất, retry có thể tạo một document khác. Thiết kế đúng là tính **stable ID bên ngoài publisher** từ tenant+Idempotency-Key, rồi mọi subscription dùng cùng ID. Tuy nhiên, `retryWhen` vẫn không nên retry mọi exception vì pending/ambiguous outcomes cần đối soát.

### 23.1. Một phương án có kiểm soát

~~~java
String stableId = OrderIdentity.of(
    tenantId, idempotencyKey, request
).orderId();

Mono<?> controlled = orders.reactive().insert(
    stableId, json, insertOptions()
).retryWhen(
    reactor.util.retry.Retry.backoff(
        2, java.time.Duration.ofMillis(150)
    ).filter(error ->
        error instanceof
        com.couchbase.client.core.error.UnambiguousTimeoutException
    )
);
~~~

Code là **minh họa Java SDK reactive**, giả sử `orders`, `json`, `insertOptions` và inputs đã khai báo/import hợp lệ. Trong production phải phối hợp total deadline, cancellation, duplicate handling, error translation và business reconciliation.

### 23.2. `Mono.timeout` không tương đương rollback

Một `Mono.timeout` hoặc request HTTP bị cancel có thể khiến caller ngừng chờ, trong khi server đã nhận mutation và có thể commit. **Cancellation không tự đảm bảo không có side effect**.

## 24. TTL và xóa document có thể phá idempotency

Bài giữ `OrderDocument` không có TTL. Giả sử team muốn “dọn dữ liệu cho nhẹ” và bật TTL 24 giờ:

~~~text
T0: Tạo orderId(K), server trả 201.
T1: TTL hết hạn, document bị xóa.
T2: Client/gateway gửi lại K rất muộn.
T3: INSERT orderId(K) lại thành công.
T4: Có thể tái thực hiện business command cũ.
~~~

TTL không phải idempotency policy. Một cách thiết kế thường gặp trong production là giữ **order record** dài hạn theo retention và, nếu tách marker, giữ **idempotency record** ít nhất bằng cửa sổ replay có thể xảy ra.

### 24.1. Soft delete khác physical delete

Nếu user hủy order, có thể chuyển `status=CANCELLED` thay vì xóa vĩnh viễn, để cùng key tiếp tục trỏ đến command đã xử lý. Nếu cần GDPR/retention xóa vật lý, phải cân nhắc hệ quả của replay và thiết kế tombstone hoặc dedup ledger phù hợp với chính sách dữ liệu.

### 24.2. Reuse key sau kỳ hạn

Nếu business công bố “idempotency key có hiệu lực 24 giờ”, hết kỳ hạn thì semantics có thể khác. Phải định nghĩa rõ: giữ đủ lâu để các retries/queued messages thực tế không tạo đơn lặp ngoài ý muốn. Không tự đặt TTL ngắn hơn cửa sổ retry của mạng/gateway.

## 25. Durability giúp bảo vệ cái gì trong bài thực hành?

Một thao tác `insert` mặc định có thể trả success mà không đợi synchronous durability nếu bucket minimum không yêu cầu mạnh hơn. Muốn một order đã xác nhận có cơ sở chịu mất một Data node phù hợp topology, có thể chọn `MAJORITY` hoặc persistence level theo RPO:

~~~java
import com.couchbase.client.core.msg.kv.DurabilityLevel;

// Với CouchbaseTemplate và cluster hỗ trợ:
OrderDocument inserted = template
    .insertById(OrderDocument.class)
    .withDurability(DurabilityLevel.MAJORITY)
    .one(candidate);
~~~

**Điều kiện:** bucket type, số Data nodes/replicas, disk/network health, minimum durability và policy fallback phải hỗ trợ level. Một Data node và 0 replica không có khả năng bảo vệ khi node duy nhất mất hoàn toàn, dù majority có thể là 1/1.

| Câu hỏi | Cơ chế |
|---|---|
| Có thể tạo hai documents cùng ID không? | KV `insert` create-only |
| Cùng command được HTTP retry có tạo ID khác không? | Deterministic ID + Idempotency-Key |
| Cùng key nhưng payload khác có bị ngăn không? | Fingerprint + conflict |
| Write được ack khi đủ bao nhiêu copies/persistence? | Durability level + bucket policy |
| Read ID thấy record mới ngay sau commit? | KV get từ Data Service |
| SQL++ query theo status đủ mới chưa? | GSI/DCP và query scan consistency |
| Hai updates cạnh tranh có ghi đè sai không? | CAS/`@Version` |
| Mất cả cluster còn dữ liệu không? | Backup/DR ngoài phạm vi một mutation |

Không tăng durability để sửa một lỗi `409 Conflict`; không dùng `REQUEST_PLUS` để thay idempotency.

## 26. Case study A — Double-click nhưng client tạo key mới mỗi lần

**Bối cảnh:** Frontend tạo `Idempotency-Key: UUID.randomUUID()` **ngay trong hàm gửi HTTP**. Người dùng nhấn hai lần rất nhanh.

~~~text
Click 1 -> key K1 -> order::LAB1::SHA256(K1)
Click 2 -> key K2 -> order::LAB1::SHA256(K2)

Hai IDs khác nhau -> hai lệnh mới hợp lệ theo contract.
~~~

**Sai lầm:** đổ lỗi cho `CouchbaseTemplate.insertById` vì có hai orders.

**Thiết kế lại:** tạo key khi bắt đầu **một checkout session/command**, lưu nó qua double-click, offline retry và gateway timeout; chỉ tạo key mới khi người dùng chủ động bắt đầu một đơn hàng mới. Disable nút trong lúc chờ là UX hữu ích nhưng **không thay** idempotency khi request đi qua nhiều pod, mạng chập chờn hoặc trình duyệt reload.

**Assertion:** hai HTTP attempts của cùng checkout giữ nguyên key; backend chỉ có một document ID.

## 27. Case study B — Một key bị dùng cho hai giỏ hàng khác nhau

**Bối cảnh:** Client giữ key từ checkout trước nhưng đổi `sku`/`quantity`, rồi gửi lại.

~~~text
Tenant: LAB1, Key: K
Request 1: sku=BOOK001, quantity=2
Request 2: sku=BOOK001, quantity=5
~~~

Hai requests có cùng `orderId` nhưng **khác fingerprint**.

**Hành vi đúng:** request 1 tạo record; request 2 đọc record sau duplicate và trả `409 ORDER_KEY_CONFLICT`, không ghi đè `quantity=2`.

**Sai lầm:** dùng `upsert` hoặc chỉ so order ID mà không so fingerprint, vì khi đó request 2 có thể sửa request 1 hoặc bị coi là replay dù nội dung khác.

**Bài học:** Idempotency-Key bảo vệ identity command; fingerprint bảo vệ **nội dung đã gắn với key**.

## 28. Case study C — Gateway trả 504 sau khi Couchbase đã commit

**Bối cảnh:** Data Service đã commit order, nhưng mạng làm mất response. Gateway trả 504 cho app. App thử lại sau đó.

**Các kết quả có thể thấy:**

| Lần thử lại | Điều ứng dụng biết | Hành động |
|---|---|---|
| `insert` trả `DocumentExists` | Key đã có | KV get + fingerprint; nếu khớp, replay |
| `insert` trả timeout ambiguous | Chưa chắc outcome | Thử readback an toàn, rồi reconciliation nếu cần |
| `get` hiện document khớp | Document hiện tồn tại | Có thể trả current order theo contract |
| `get` chưa thấy document | Có thể pending/failover | Chưa khẳng định mutation trước chắc sẽ không commit |
| `get` thấy khác fingerprint | Key đã bị dùng cho command khác | Conflict, không overwrite |

**Sai lầm phổ biến:** response timeout → xóa key cũ → tạo UUID mới → phát lại payment. Đúng là giữ key, phân loại lỗi, bảo vệ side effects và có workflow đối soát.

## 29. Case study D — Tenant khác dùng cùng Idempotency-Key

**Bối cảnh:** Tenant LAB1 và LAB2 đều gửi key `checkout-20261125-a1b2c3`.

Vì document ID có tenant namespace:

~~~text
order::LAB1::<SHA256(K)>
order::LAB2::<SHA256(K)>
~~~

hai commands không va nhau. Tuy nhiên, chỉ prefix tenant trong ID **không** thay quyền truy cập. Nếu một user thuộc LAB1 tự sửa URL sang LAB2 mà API không kiểm tra security principal, họ có thể gửi/đọc data LAB2.

**Khắc phục:** tenant từ authentication context, RBAC và kiểm tra ownership trong service. Nếu dùng SQL++ list, luôn có tenant predicate và quyền tương ứng; tránh `findAll` trả mọi tenants.

## 30. Ma trận kiểm thử hoàn chỉnh

| ID | Điều kiện | Input/biến | Kết quả cần kiểm tra |
|---|---|---|---|
| T01 | Command mới | Tenant LAB1, key K1, payload P1 | 201, có một document ID |
| T02 | Replay tuần tự | Tenant LAB1, key K1, payload P1 | 200, cùng ID và createdAt |
| T03 | Key bị tái sử dụng | LAB1, K1, payload P2 | 409, không thay P1 |
| T04 | Lệnh mới hợp lệ | LAB1, K2, payload P1 | ID mới, không coi là retry |
| T05 | Tenant khác | LAB2, K1, payload P1 | ID khác LAB1 |
| T06 | Normalize có chủ đích | `cus001` vs `CUS001` | Cùng fingerprint theo lab |
| T07 | Key phân biệt hoa/thường | `Key-Abc123` vs `key-Abc123` | ID khác nhau |
| T08 | Thiếu header | Không có Idempotency-Key | 400 trước mutation |
| T09 | Key không hợp lệ | Có khoảng trắng hoặc quá dài | 400 trước mutation |
| T10 | Quantity không hợp lệ | `0` hoặc vượt 1000 | 400 trước mutation |
| T11 | Hai callers đồng thời | Cùng K/P | Một document cuối; không overwrite |
| T12 | Concurrency khác payload | Cùng K, P1/P2 | Một payload thắng insert, payload khác conflict/pending được xử lý |
| T13 | SDK response mất sau commit | Fault proxy tại lab | Retry cùng key không tạo duplicate |
| T14 | Pending SyncWrite/ambiguous | Fault trong lab | Không coi not-found một lần là rollback |
| T15 | Index lag | KV record có, SQL++ `NOT_BOUNDED` chưa thấy | Dùng KV theo ID để đối soát |
| T16 | Restart ứng dụng | K/P giữ qua app restart | Replay vẫn cùng document |
| T17 | Retention | Xóa/expire record trong lab | Ghi nhận nguy cơ replay sau retention |
| T18 | Authorization | User LAB1 truy cập LAB2 | Từ chối khi đã bổ sung security |
| T19 | Durability | Cluster có replica phù hợp | Requested/effective level và p99 được ghi nhận |
| T20 | External side effect | Payment mock/consumer idempotent | Một business command không nhân charge/event |

### 30.1. Mục T11/T12 không yêu cầu mọi caller nhận 200 ngay

Ở thời điểm tranh chấp hoặc khi có SyncWrite pending, một caller có thể tạm bị lỗi. Acceptance criterion nên là **không tạo nhiều record/sai payload** và **unknown outcomes được đối soát**, không ép tất cả attempts có HTTP success trong một khoảng deadline bất khả thi.

### 30.2. T13/T14 chỉ thử trên môi trường được phép

Không chặn mạng/hard failover production để học. Nếu dùng proxy mô phỏng response loss, lưu rõ nó chỉ mô phỏng **cửa sổ response bị mất** chứ không tái tạo mọi chi tiết failover server thật.

## 31. Bảo mật, quan sát và vận hành

### 31.1. Bảo mật Idempotency-Key và document key

- Không lấy email, phone, access token, password hoặc raw payment data làm document ID.
- Idempotency-Key nên được caller tạo bằng giá trị có entropy đủ cao, giới hạn độ dài và ký tự.
- SHA-256 của key giúp che key thô trong document ID nhưng **không phải mã hóa/HMAC**; key có entropy thấp vẫn có thể bị đoán.
- Giới hạn tenant trong key và gắn authorization vào authenticated principal.
- Giới hạn rate/concurrency theo tenant/client để tránh spam hàng triệu key và documents.
- Không đưa raw key, fingerprint đầy đủ, request body chứa PII vào logs trừ khi chính sách cho phép và đã redacted.
- TLS và credential storage theo môi trường; không dùng admin credentials cho runtime app.

### 31.2. Logging/tracing mẫu

~~~text
timestamp=2026-11-25T03:10:00Z
service=order-api
operation=CREATE_ORDER
tenant=LAB1
keyHashPrefix=redacted
documentIdHash=redacted
attemptId=req-98765
decision=REPLAY_MATCH
httpStatus=200
databasePath=KV_INSERT_THEN_KV_GET
durationMs=...
retryClassification=DUPLICATE
~~~

Đây là schema đề xuất; SDK không tự phát toàn bộ các field. Correlation ID của từng HTTP attempt có thể khác, trong khi stable business key/dedup ID giữ nguyên.

### 31.3. Metrics nên có

| Metric/SLI | Dùng làm gì? |
|---|---|
| `order_create_new_total` | Số command mới tạo thành công |
| `order_replay_match_total` | Số retries hợp lệ được nhận diện |
| `order_key_conflict_total` | Một key bị dùng với fingerprint khác |
| `order_unconfirmed_total` | Outcome chưa rõ cần reconciliation |
| `order_reconciliation_open` | Backlog còn chưa kết luận |
| KV insert/find p95, p99 | Data Service latency |
| SDK retries/timeouts | Network/cluster health |
| HTTP 201/200/409/503 | Hợp đồng API và user impact |
| Duplicate payment/event count | Business side effect correctness |

Những tên metrics là **đề xuất đặt trong ứng dụng**, không phải mặc định Couchbase Server. Không đo business duplicates chỉ bằng `DocumentExistsException` vì response-lost and replay có thể dẫn đến nhiều loại kết quả.

### 31.4. Ranh giới vận hành khi có quá nhiều 503

Nếu tỉ lệ ambiguous tăng:

1. Xác định cụm/node/replica health và timeout ở HTTP/gateway/SDK.
2. Kiểm tra có thay bucket minimum durability hoặc cấu hình fallback không.
3. Giới hạn retry/backoff, tránh retry storm.
4. Đảm bảo mọi lệnh cần đối soát vẫn giữ stable IDs và fingerprints.
5. Không tự hạ `MAJORITY` xuống `NONE` để “cho endpoint hết lỗi” khi chưa đánh giá RPO.
6. Escalate DBA/SRE khi replication/persistence không đáp ứng.
7. Xác minh business outcomes sau incident, không chỉ nhìn error rate trở lại bình thường.

## 32. Các mở rộng có ràng buộc nghiệp vụ mạnh hơn

### 32.1. Unique order number độc lập

`orderId` là Couchbase document key, còn order number hiển thị có thể là `ORD-2026-000123`. Nếu order number được cấp từ sequence/counter riêng, cần bảo vệ uniqueness/atomicity và retry; **không suy rằng UUID/hash key tự tạo số thứ tự liên tục**.

### 32.2. Inventory reservation

Một order insert không đồng thời trừ kho. Nếu muốn bảo đảm không bán vượt tồn kho, cần CAS/transaction phù hợp cho inventory hoặc workflow reservation có idempotency. Hai KV writes riêng cùng `PERSIST_TO_MAJORITY` không tự tạo atomicity nhiều document.

### 32.3. Payment và outbox

Nếu `POST /orders` còn charge payment, thao tác external đó không nằm trong transaction của Couchbase. Dùng idempotency key của gateway và đối soát gateway reference. Khi phát event, cân nhắc outbox/inbox, retry idempotent consumer và thiết kế bền; không gửi email hoặc charge lại chỉ vì HTTP timeout.

### 32.4. Cross-region recovery

Durability và replica nội cluster không phải backup/DR. Nếu mất cluster hoặc mất site, cần backup/restore, replication liên cluster theo semantics phù hợp và RPO/RTO thực đo. Hash idempotency key chỉ giúp tái tính identity, **không tự khôi phục document đã mất**.

### 32.5. Khi cần tách command record khỏi order document

Một số hệ thống không muốn document key hiển thị phụ thuộc Idempotency-Key. Khi đó có thể lưu:

~~~text
idempotency::<tenant>::<hash(key)> -> orderId, fingerprint, status
order::<ULID/UUID>                 -> order body
~~~

Nhưng **hai documents cần atomicity/coordination** để không tồn tại marker trỏ tới order chưa được tạo. Có thể cân nhắc Couchbase Transactions khi khả dụng, kèm recovery/reconciliation. Bài chọn **một document ID suy từ key** để giảm bài toán atomicity và làm rõ phép insert-only.

## 33. Bài tập tự luyện

### Bài A — thiết kế key

Thiết kế document key để hai tenants có thể dùng cùng Idempotency-Key mà không va nhau. Tại sao không nên nhúng email/phone vào key?

### Bài B — fingerprint

Cho cùng key và payload khác `quantity`. Nên tạo order mới, trả replay hay trả conflict? Tại sao phải hash nội dung chuẩn hóa thay vì raw JSON text?

### Bài C — check-then-write

Hai pods cùng đọc `existsById=false`. Vì sao có race? Hãy thay bằng một operation KV chính xác và mô tả expected outcomes.

### Bài D — cùng payload khác key

Người dùng mua cùng sản phẩm với số lượng giống nhau hai lần có chủ đích. Vì sao hai keys khác nhau vẫn có thể tạo hai orders hợp lệ?

### Bài E — Version/CAS

`@Version` giúp gì khi update order status? Nó có ngăn create trùng như `insert` không? Có biến thành persistence majority không?

### Bài F — exception translation

Spring Data Template ném một `DataAccessException` bọc `DocumentExistsException`. Bạn sẽ phân loại thế nào mà không coi lỗi TLS/permission là duplicate?

### Bài G — timeout ambiguous

SDK timeout sau khi request đã tới server. Một lần KV get trả not-found. Có thể khẳng định chưa commit không? Nêu state machine xử lý.

### Bài H — hai callers đồng thời

Hãy thiết kế concurrency test cho cùng key/payload và khác payload. Những điều cần assert ở **database state cuối** là gì?

### Bài I — retention

Nếu order document bị xóa vật lý sau một ngày, một retry muộn cùng key có thể gây điều gì? Nêu cách bảo vệ theo retention/idempotency contract.

### Bài J — reactive retry

Vì sao `Mono.defer(() -> insert(randomUUID(), body))` + `retryWhen` nguy hiểm? Hãy tính document ID trước khi tạo publisher và chọn retry classification.

### Bài K — GSI freshness

KV findById trả order nhưng SQL++ `NOT_BOUNDED` chưa thấy. Đây có phải durability failure? Hãy chọn phép đọc phù hợp để đối soát.

### Bài L — saga

Nếu order insert thành công nhưng payment gateway timeout, có nên gửi lại charge với một key mới? Thiết kế bước đối soát order/payment tham chiếu cùng operation ID.

### Bài M — multi-tenant security

Tenant LAB1 và LAB2 có thể dùng cùng key; một user LAB1 có được GET order LAB2 khi biết ID không? Cần thêm kiểm tra ở đâu?

### Bài N — business acceptance

Viết bộ tiêu chí chấm điểm cho 201/200/409/503, trường hợp bad header, concurrent requests, failover và kiểm soát side effects ngoài DB.

## 34. Checklist nghiệm thu

- [ ] Có bucket/scope/collection lab riêng, không đụng dữ liệu production.
- [ ] Spring Boot/Java SDK versions tương thích theo BOM.
- [ ] Credentials, TLS và RBAC runtime được cấu hình đúng.
- [ ] `Idempotency-Key` bắt buộc; tạo một lần cho **mỗi business command**.
- [ ] Idempotency key giữ nguyên qua HTTP retry, double-click và app restart.
- [ ] Key có giới hạn length/characters và đủ entropy theo threat model.
- [ ] `orderId` xác định từ tenant + hash(key), không chứa PII thô.
- [ ] `fingerprint` được hash từ canonical business payload có version.
- [ ] Cùng key/payload → cùng ID/fingerprint; cùng key/payload khác → conflict.
- [ ] Tạo mới dùng **`insertById`**, không dùng check-then-upsert.
- [ ] Duplicate được đọc lại bằng **KV findById**, không dựa SQL++ stale.
- [ ] Replay trả record ban đầu/hiện tại mà không thực hiện insert thứ hai.
- [ ] HTTP 201 mới tạo, 200 replay, 409 mismatch, 503 unconfirmed theo contract.
- [ ] Không gộp timeout ambiguous với unambiguous hoặc duplicate.
- [ ] Không sinh ID mới khi chưa xác minh kết quả ghi.
- [ ] Có chính sách reconciliation với owner nếu workflow vượt một HTTP request.
- [ ] Nếu có SyncWrites, bucket replica/topology đáp ứng durability level.
- [ ] Không bật TTL tùy tiện khiến một key cũ có thể được tái sử dụng.
- [ ] Có unit tests cho identity/fingerprint và integration tests cho create/replay/conflict.
- [ ] Concurrency test xác minh **database state cuối**, không chỉ HTTP codes.
- [ ] Không dùng `upsert`, local lock hoặc GSI index để thay create-only atomicity.
- [ ] CAS được dùng cho update sau tạo; transaction cho nhiều documents nếu cần.
- [ ] Payment/event delivery có idempotency/đối soát riêng.
- [ ] Tenant authentication/authorization chống truy cập chéo.
- [ ] Metrics/logs không lộ key/PII nhưng đủ correlation để điều tra.
- [ ] Backup/DR và retention phù hợp RPO/RTO của order.

## 35. Tổng kết

**Một yêu cầu tạo đơn được xử lý idempotent khi hệ thống định danh ổn định business command, không chỉ khi database có UUID hoặc replica.** Bài thực hành sử dụng `tenant + Idempotency-Key` để tạo một `OrderDocument.id` xác định và dùng `CouchbaseTemplate.insertById` nhằm đảm bảo create-only ở một key. `OrderRepository.findById` cho phép đọc lại bằng KV khi gặp duplicate hoặc cần đối soát một kết quả chưa rõ.

**Fingerprint là lớp thứ hai bắt buộc:** cùng key và payload chuẩn hóa phải trả về đơn đã có, còn cùng key với payload khác phải bị từ chối. `@Version`/CAS giúp cập nhật có điều kiện về sau nhưng không thay create-only insert; durability giúp bảo vệ mutation đã được xác nhận nhưng không làm idempotent HTTP requests; SQL++ scan consistency giúp chỉ mục bắt kịp nhưng không thay KV readback theo ID.

Khi gặp timeout ambiguous, không tự chọn kết luận “đã thất bại”. Hãy giữ key, kiểm tra record hiện có, giới hạn retry và đối soát cho đến khi có kết quả nghiệp vụ. Những hệ thống có inventory, payment, event bus hay nhiều clusters cần mở rộng bằng transaction/workflow, outbox, idempotency và DR tương ứng. **At-most-one order document theo một key không tự có nghĩa exactly-once mọi side effect.**

## Tài liệu tham khảo chính thức

1. [Spring Data Couchbase — Template and Direct Operations](https://docs.spring.io/spring-data/couchbase/reference/couchbase/template.html): fluent `insertById`, `replaceById` và tùy chọn durability.
2. [Spring Data Couchbase — Repository](https://docs.spring.io/spring-data/couchbase/reference/couchbase/repository.html): CRUD theo ID, mapping và query derivation.
3. [Spring Data Couchbase — Entity Mapping](https://docs.spring.io/spring-data/couchbase/reference/couchbase/entity.html): `@Document`, `@Id`, `@Version` và CAS.
4. [Spring Data Couchbase — Collection Support](https://docs.spring.io/spring-data/couchbase/reference/couchbase/collections.html): `@Scope`, `@Collection` và keyspace.
5. [Spring Boot — Couchbase Auto-Configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html): `spring.couchbase.*` và bucket name.
6. [Couchbase Java SDK — KV Operations](https://docs.couchbase.com/java-sdk/current/howtos/kv-operations.html): `insert`, `replace`, document IDs, mutation options, CAS.
7. [Couchbase Java SDK — Error Handling](https://docs.couchbase.com/java-sdk/current/howtos/error-handling.html): ambiguous/unambiguous timeout, retries và idempotence.
8. [Couchbase Server — Durability](https://docs.couchbase.com/server/current/learn/data/durability.html): synchronous durability, majority, persistence và failure behavior.
9. [Couchbase Java SDK — SQL++ Queries](https://docs.couchbase.com/java-sdk/current/howtos/sqlpp-queries-with-sdk.html): query/index consistency; phân biệt với KV.
10. [Spring Data Couchbase — API Reference](https://docs.spring.io/spring-data/couchbase/reference/): tra cứu API theo version.

**Giới hạn bài học:** code và test snippets là tài liệu hướng dẫn; chưa được build, chạy integration tests hoặc thao tác Couchbase thật trong bước soạn bài. Cần xác minh Spring Data/SDK/Server version, transaction semantics, exception translation và security trước khi áp dụng trong môi trường có dữ liệu thật. Vòng Content QA chuyên môn thuộc STEP 6 riêng.








# Phân biệt bảo vệ biên ứng dụng và ràng buộc dữ liệu thực tế trong JPA

Trong một ứng dụng sử dụng **Jakarta Persistence (JPA)**, bảo mật dữ liệu không chỉ là đặt `@Valid` trên request DTO, thêm `@NotNull` vào entity hay kiểm tra người dùng đã đăng nhập trước khi gọi `EntityManager.persist()`.

Một request có thể **được xác thực hợp lệ** nhưng vẫn tham chiếu tới đơn hàng của người khác. Một entity có thể **vượt qua Bean Validation** nhưng vẫn vi phạm khóa ngoại. Một transaction có thể **kiểm tra dữ liệu đúng ở thời điểm đọc**, nhưng sai ở thời điểm ghi vì một transaction khác vừa cập nhật cùng resource. Ngược lại, database có thể **cho phép INSERT** vì tất cả các constraints đều hợp lệ, trong khi người thực hiện hoàn toàn không có quyền tạo dữ liệu đó.

Vì vậy cần phân biệt rõ:

- **Bảo vệ biên ứng dụng** (*application boundary protection*): xác thực danh tính, phân quyền, giới hạn input, xác định tenant từ nguồn tin cậy, kiểm soát fields được chỉnh sửa, chống injection, quản lý response và xử lý lỗi. Nó trả lời: **Ai được phép yêu cầu điều gì, trên đối tượng nào, thông qua luồng nào?**
- **Quy tắc domain và kiểm tra object graph**: giữ trạng thái đối tượng hợp lệ khi các thao tác nghiệp vụ diễn ra, ví dụ không submit một đơn rỗng hoặc không gắn một sản phẩm của tenant khác. Nó trả lời: **Trạng thái và chuyển trạng thái nào được nghiệp vụ chấp nhận?**
- **Ràng buộc dữ liệu thực tế** (*database-enforced constraints*): những quy tắc được DBMS thực thi ở thời điểm SQL/commit, như `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`, `NOT NULL`, `CHECK`; khi được thiết kế đúng có thể có thêm **Row-Level Security (RLS)**, database grants và transaction isolation/locking. Nó trả lời: **Có thể ngăn một trạng thái dữ liệu không hợp lệ hoặc truy cập trái phép ngay tại nơi lưu trữ không?**

> **Nguyên tắc:** Không đặt toàn bộ niềm tin ở một lớp. **Biên ứng dụng** bảo vệ hành vi và danh tính, **domain** bảo vệ ý nghĩa nghiệp vụ, **database** bảo vệ các bất biến có thể cưỡng chế ở mức lưu trữ. Các lớp chồng lên nhau nhưng không thay thế nhau.

Bài học thuộc chương **Bảo mật dữ liệu** trong module **Data Persistence Relational Access ORM JPA**. Ta sẽ xây dựng ví dụ hệ thống nhiều tenant, phân biệt xác thực và ủy quyền với data validation, sử dụng JPA an toàn, chống thao túng ID/field, bảo vệ quan hệ cross-tenant, chống race condition, viết database constraints và Row-Level Security, áp dụng least privilege, xử lý bulk DML, kiểm thử nhiều đường ghi và thiết kế một chiến lược phòng thủ nhiều lớp.

---

## 1. Ba câu hỏi trước mọi thao tác dữ liệu

Giả sử API nhận:

```http
POST /api/orders/9001/submit
Authorization: Bearer <access-token>
Content-Type: application/json

{}
```

Ta cần trả lời ba câu hỏi **khác nhau**.

| Câu hỏi | Ví dụ | Lớp phụ trách chính |
| --- | --- | --- |
| **Ai đang thực hiện?** | Token thuộc người dùng nào, ở tenant nào? | Authentication ở application boundary |
| **Có quyền thao tác không?** | Người dùng này được submit Order#9001? | Authorization ở service/resource boundary |
| **Dữ liệu sau thao tác có hợp lệ không?** | Order có lines, FK đúng, không trùng reference? | Domain + JPA mapping + DB constraints |

Một token hợp lệ **không chứng minh** người dùng có quyền trên mọi Order ID.

Một câu `SELECT` trả được Order#9001 **không chứng minh** người dùng có quyền submit.

Một `UPDATE` thành công ở database **không chứng minh** thao tác được phép theo chính sách tổ chức.

### 1.1. Tính đúng đắn và tính bảo mật giao nhau nhưng không đồng nhất

Một record:

```text
Order#9001
  tenantId = "tenant-B"
  customerId = 700
  status = SUBMITTED
```

có thể hoàn toàn hợp lệ về FK và `CHECK`. Nhưng nếu caller của `tenant-A` truy cập nó, đó vẫn là lỗi **phân quyền đối tượng**.

Ngược lại, caller của tenant-B có thể được phép tạo Order nhưng yêu cầu trùng `reference`; đây là lỗi **data integrity**, không nhất thiết là vi phạm authorization.

### 1.2. Confidentiality, integrity và availability

- **Confidentiality**: không đọc được đơn hàng, PII hoặc dữ liệu tenant khác.
- **Integrity**: không tạo được dữ liệu mâu thuẫn, tham chiếu sai hoặc sửa trái phép.
- **Availability**: không bị cạn pool/DB vì query không giới hạn, lock kéo dài hoặc input quá lớn.

Ràng buộc database thường đặc biệt mạnh ở **integrity**; authorization và query scoping đặc biệt quan trọng với **confidentiality**; phân trang, giới hạn payload, timeout và quotas giúp bảo vệ **availability**.

### 1.3. Một permission không phải một database constraint đơn giản

Quy tắc “chỉ người quản lý có thể duyệt đơn trên 10 triệu đồng” phụ thuộc:

- Danh tính và vai trò người thực hiện.
- Quan hệ tổ chức và delegation.
- Trạng thái hiện tại của Order.
- Hạn mức và workflow của tổ chức.
- Thời điểm/quy trình phê duyệt.

`NOT NULL`, `FOREIGN KEY` hay một `CHECK` đơn giản trên Order không thể tự biết toàn bộ bối cảnh đó. Biên ứng dụng và domain service vẫn phải thực thi chính sách.

## 2. Sơ đồ phòng thủ nhiều lớp

```text
        Untrusted HTTP / message / import
                      |
                      v
          Authenticate caller identity
                      |
                      v
          Authorize action and tenant
                      |
                      v
           Parse + validate request DTO
                      |
                      v
        Application / domain service
            |             |
            |             +-- domain invariants
            |             +-- ownership rules
            |             +-- allowed transitions
            |
            v
         JPA EntityManager
            |
            +-- parameterized JPQL / Criteria
            +-- controlled entity mutations
            +-- optimistic/pessimistic locking
            +-- flush + transaction
            |
            v
              Database
            |
            +-- FK / UNIQUE / CHECK / NOT NULL
            +-- transaction isolation / locks
            +-- grants / RLS when configured
            |
            v
         Durable consistent state
```

**Mỗi lớp thấy một phần sự thật khác nhau.** Một DTO validator biết input nhưng thường không biết trạng thái DB. Database biết rows và constraints nhưng có thể không biết caller đang thực hiện quy trình phê duyệt nào. Application service là nơi phối hợp các thông tin đó.

## 3. Một bảng đối chiếu trách nhiệm

| Ràng buộc hoặc nguy cơ | Biên ứng dụng | Domain/JPA | Database |
| --- | --- | --- | --- |
| Token không hợp lệ | **Chặn** | Không phải nhiệm vụ chính | Không tự biết JWT |
| User không có quyền với Order ID | **Kiểm tra** | Query scoping, domain rules | RLS/grants có thể bổ sung |
| JSON thiếu `customerId` | DTO validation | Constructor/domain checks | FK/NOT NULL bảo vệ cuối |
| `quantity < 1` | DTO validation | Domain/Bean Validation | **CHECK(quantity >= 1)** |
| Customer ID không tồn tại | Có thể báo 404 | Resolve/reference check | **FOREIGN KEY** |
| Order tenant-A trỏ Customer tenant-B | Tenant checks | Association invariant | Composite FK nếu thiết kế |
| Mã đơn trùng trong tenant | Có thể báo sớm | Domain/repository check | **UNIQUE(tenant_id, reference)** |
| Hai requests đồng thời dùng cùng mã đơn | Không đủ nếu check-before-insert | Transaction policy | **UNIQUE** quyết định cuối |
| Client tự gửi `status=APPROVED` | DTO allowlist | Transition method | CHECK chỉ giới hạn enum values |
| SQL/JPQL injection | Parameter binding, allowlist | Repository query design | DB permissions giảm hậu quả |
| Query đọc quá nhiều bản ghi | Page-size limit | Projection/pagination | Statement timeout/quota/indexes |
| Bulk update bỏ qua entity callbacks | Giới hạn đường gọi | Service/transaction design | Constraints/RLS vẫn có tác dụng |
| Sửa giá trị nhạy cảm trong log | Logging/redaction policy | DTO/report design | Encryption/auditing tùy yêu cầu |

Nhìn vào bảng sẽ thấy: **một cơ chế có thể xuất hiện ở nhiều lớp nhưng vai trò không giống nhau**. Ví dụ kiểm tra mã đơn trùng trong service giúp trả thông báo dễ hiểu; unique constraint mới là cơ chế cuối cùng cưỡng chế tính duy nhất dưới concurrency.

## 4. Mô hình ví dụ: cửa hàng nhiều tenant

Giả sử ứng dụng SaaS có hai khách hàng tổ chức:

```text
tenant-A:
  User alice
  Customer#101
  Order#9001

tenant-B:
  User bob
  Customer#202
  Order#9002
```

Các thực thể chính:

```text
Tenant
  id
   |
   +-- Customer
   |     id, tenantId, name
   |
   +-- PurchaseOrder
         id, tenantId, reference,
         customerId, status, version
```

Các quy tắc:

1. Caller của tenant-A không được đọc/sửa Order thuộc tenant-B.
2. Mỗi Order thuộc đúng một tenant.
3. Customer của Order phải cùng tenant.
4. Mỗi tenant không được có hai Orders trùng `reference`.
5. Chỉ actor có quyền `ORDER_SUBMIT` trên Order mới được submit.
6. Order chỉ được chuyển `DRAFT -> SUBMITTED` nếu các điều kiện nghiệp vụ thỏa mãn.
7. Không được bỏ qua phân quyền bằng cách gửi ID của entity khác.
8. Các ràng buộc lưu trữ phải đứng vững trước concurrent requests và những writers không đi qua cùng HTTP controller.

### 4.1. Vì sao chọn mô hình nhiều tenant?

Tenant isolation làm rõ khác biệt giữa:

- **Input hợp lệ:** `orderId=9002` là số dương.
- **Object tồn tại:** Order#9002 có trong DB.
- **Object được phép truy cập:** alice thuộc tenant-A **không được** thấy Order#9002 của tenant-B.

Ba điều kiện này không đồng nghĩa nhau.

## 5. Authentication: danh tính phải đến từ nguồn đáng tin

Một sai lầm nguy hiểm là lấy tenant ID trực tiếp từ request body:

```json
{
  "tenantId": "tenant-B",
  "customerId": 202,
  "reference": "PO-001"
}
```

rồi viết:

```java
String tenantId = request.tenantId();
order.setTenantId(tenantId);
```

Nếu caller đang đăng nhập ở tenant-A nhưng sửa JSON thành tenant-B, ứng dụng có thể ghi dữ liệu sang tenant khác.

### 5.1. Cách đúng về nguyên tắc

```text
Verified identity / security principal
                  |
                  v
        trusted tenant context
                  |
                  v
        application service
                  |
                  v
         scoped JPA query
```

Ứng dụng có thể sử dụng authentication framework, session/JWT đã được xác thực chữ ký, tenant membership đã được kiểm chứng hoặc một trusted service identity tùy kiến trúc.

**Không tin một chuỗi tenantId do client gửi chỉ vì nó có vẻ đúng định dạng.**

### 5.2. Tenant claim cũng có điều kiện

Nếu một token có tenant claim nhưng membership/permissions có thể bị thu hồi, hệ thống cần chính sách về thời gian hiệu lực, token refresh, revocation hoặc server-side verification.

Một claim được ký hợp lệ không tự bảo đảm quyền chưa thay đổi kể từ lúc token được phát hành.

### 5.3. Service-to-service authentication

Message consumer, batch job và internal API cũng là các entrypoints. Không nên giả định “không qua HTTP” đồng nghĩa có toàn quyền.

Mỗi entrypoint cần trusted identity, permissions/scope và dữ liệu nguồn thích hợp.

## 6. Authorization: kiểm tra hành động trên đúng đối tượng

Một bộ lọc URL có thể xác nhận người dùng có role `USER` hoặc `ORDER_EDITOR`. Nhưng quyền thao tác thường phụ thuộc **đối tượng cụ thể**.

### 6.1. IDOR/BOLA

Một endpoint:

```http
GET /api/orders/9001
```

có thể bị đổi thành:

```http
GET /api/orders/9002
```

Nếu controller chỉ kiểm tra user đã đăng nhập rồi gọi:

```java
return em.find(PurchaseOrder.class, orderId);
```

application có thể trả Order của tenant khác. Đây là dạng **Broken Object Level Authorization (BOLA)**, thường còn gọi là IDOR trong ngữ cảnh tham chiếu object trực tiếp.

### 6.2. Query có tenant predicate

Một query rõ ràng hơn:

```java
public PurchaseOrder findVisibleOrder(
        long orderId,
        String trustedTenantId) {

    return em.createQuery(
        """
        SELECT o
        FROM PurchaseOrder o
        WHERE o.id = :orderId
          AND o.tenantId = :tenantId
        """,
        PurchaseOrder.class
    )
    .setParameter("orderId", orderId)
    .setParameter("tenantId", trustedTenantId)
    .getResultStream()
    .findFirst()
    .orElse(null);
}
```

`trustedTenantId` được lấy từ context đã xác thực, không từ request body tùy ý.

### 6.3. Query scoping không thay đầy đủ quyền nghiệp vụ

Một người dùng thuộc tenant-A có thể xem Order tenant-A nhưng chưa chắc có quyền **submit** hoặc **delete** Order đó.

Cần thêm policy:

```java
authorization.requireCanSubmit(actor, order);
```

Chính sách có thể xét role, trạng thái, owner, hạn mức và ủy quyền.

### 6.4. Hành vi 404 và 403

Một ứng dụng có thể trả 404 cho resource không tồn tại **hoặc không được tiết lộ sự tồn tại**, nhằm tránh lộ thông tin qua response. Trong trường hợp khác, 403 thể hiện rõ quyền bị từ chối.

Lựa chọn HTTP status phải nhất quán với security policy/API contract; JPA không tự quyết định điều này.

### 6.5. Đừng chỉ kiểm tra quyền trên collection endpoint

`GET /orders` có tenant filter không có nghĩa `GET /orders/{id}`, `PATCH`, export CSV hoặc download attachment cũng đã an toàn.

**Mỗi điểm truy cập object đều cần authorization phù hợp**, kể cả child endpoints.

## 7. DTO và allowlist fields: chống mass assignment

Một entity có thể chứa nhiều fields mà client không được tự chỉnh:

```java
@Entity
public class PurchaseOrder {

    @Id
    private Long id;

    private String tenantId;

    private String reference;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    private BigDecimal approvedTotal;

    private Long approvedByUserId;

    @Version
    private Long version;
}
```

Nếu deserialize body trực tiếp thành entity rồi gọi `merge()`:

```json
{
  "id": 9001,
  "tenantId": "tenant-B",
  "status": "APPROVED",
  "approvedTotal": 1,
  "approvedByUserId": 1,
  "version": 0
}
```

client có thể cố thao túng những fields nội bộ, bỏ qua workflow hoặc thay đổi graph không được phép.

### 7.1. DTO chỉ nhận những fields cho phép

```java
package com.example.orders.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record ChangeOrderReferenceRequest(
    @NotBlank
    @Size(max = 60)
    String reference
) {}
```

Service chỉ thực hiện **một hành động đã được cho phép**:

```java
order.changeReference(request.reference());
```

không copy toàn bộ properties bằng reflection hoặc merge graph từ client.

### 7.2. DTO không thay authorization

Request chỉ có `reference` vẫn có thể nhắm vào `orderId` của người khác. DTO bảo vệ **field-level allowlist**, còn service phải xác minh actor có quyền trên order.

### 7.3. Tách commands theo mục đích

Thay vì một DTO rộng cho mọi thao tác:

```text
UpdateOrderRequest:
  status, tenantId, price, reference,
  customerId, approvedBy, items, ...
```

có thể dùng:

```text
ChangeOrderReferenceRequest
AddOrderLineRequest
SubmitOrderRequest
CancelOrderRequest
ApproveOrderRequest
```

Mỗi command có policy và invariants riêng, dễ kiểm tra hơn một “update entity” tổng quát.

### 7.4. Không tin ID child trong payload

Nếu request truyền `lineId=500` để xóa một dòng hàng, service phải xác minh line thực sự **thuộc Order được truy cập và thuộc tenant được phép**, không chỉ `em.find(OrderLine.class, 500L)` rồi delete.

## 8. Input validation là cần thiết nhưng không phải security boundary đầy đủ

Ví dụ:

```java
public record CreateOrderRequest(
    @NotNull Long customerId,
    @NotBlank @Size(max = 60) String reference
) {}
```

DTO validation giúp phát hiện:

- Thiếu Customer ID.
- Mã đơn trống.
- Chuỗi quá dài.
- Dữ liệu sai format/type khi deserialize.

Nhưng một request:

```json
{
  "customerId": 202,
  "reference": "PO-001"
}
```

vẫn có thể vượt qua validation nếu Customer#202 có thật nhưng **thuộc tenant khác**.

### 8.1. Phân biệt các loại validation

| Loại | Ví dụ | Công cụ |
| --- | --- | --- |
| Syntax/shape | Chuỗi không trống, ID không null | Jakarta Bean Validation trên DTO |
| Domain | Order ở DRAFT mới được submit | Domain methods/service |
| Reference existence | Customer có tồn tại? | Repository trong transaction |
| Tenant relation | Customer cùng tenant với Order? | Service + composite FK |
| Authorization | Actor có quyền trên Order? | Security policy/service/RLS |
| Data integrity | Không trùng reference | DB unique constraint |
| Concurrency | Hai requests cùng cập nhật version | Transaction + optimistic locking |

### 8.2. @Valid không tự truy vấn database

```java
public void create(@Valid CreateOrderRequest request)
```

không bảo đảm Customer ID tồn tại hoặc user có quyền truy cập Customer.

### 8.3. @NotNull không bảo vệ ownership

Trên entity:

```java
@NotNull
@ManyToOne(optional = false)
@JoinColumn(nullable = false)
private Customer customer;
```

các khai báo trên không mặc nhiên chứng minh Customer thuộc cùng tenant.

### 8.4. Validation messages có thể tiết lộ dữ liệu

Không trả raw SQL errors, full entity state, access token hay tên bảng/cột nhạy cảm ra API. Error handling cần ổn định và không tiết lộ sự tồn tại của resource khi policy yêu cầu.

## 9. Domain invariant: bảo vệ cả những đường gọi không qua controller

Giả sử workflow:

```text
DRAFT -> SUBMITTED -> APPROVED
     \-> CANCELLED
```

Một đơn rỗng không thể SUBMITTED; đơn đã APPROVED không được sửa giá; cancel có thể phụ thuộc payment status.

### 9.1. Dùng domain method thay public setters

```java
public void submit() {
    if (status != OrderStatus.DRAFT) {
        throw new IllegalStateException(
            "Only DRAFT orders can be submitted"
        );
    }

    if (lines.isEmpty()) {
        throw new IllegalStateException(
            "Order must contain at least one line"
        );
    }

    status = OrderStatus.SUBMITTED;
}
```

Domain method bảo vệ invariant dù được gọi từ controller, batch import hay message consumer.

### 9.2. Authorization vẫn nằm ngoài domain khi cần identity context

`submit()` có thể quyết định chuyển trạng thái hợp lệ hay không. Nhưng câu hỏi **actor nào được phép gọi `submit()`** thường do application/service authorization đảm nhận.

Một domain entity không nên tùy tiện đọc HTTP SecurityContext hoặc query user sessions.

### 9.3. Domain method không bảo vệ SQL viết ngoài JPA

Một JDBC script có thể:

```sql
UPDATE purchase_orders
SET status = 'SUBMITTED'
WHERE id = 9001;
```

và bỏ qua `order.submit()`. Đó là lý do các invariants quan trọng cần thêm DB constraints, quyền truy cập, transaction policy hoặc một quy trình ghi tập trung phù hợp.

### 9.4. Không nhầm domain invariant với DB CHECK

Một `CHECK` có thể cấm status ngoài tập `DRAFT/SUBMITTED/APPROVED`, nhưng không tự kiểm tra mọi **chuyển trạng thái từ giá trị cũ sang giá trị mới** nếu cần lịch sử/actor context.

## 10. JPA metadata và Bean Validation không tự tạo đầy đủ DB constraints

Ví dụ:

```java
@NotBlank
@Column(
    name = "reference",
    nullable = false,
    length = 60
)
private String reference;
```

Ba mức ý nghĩa:

- `@NotBlank`: Bean Validation trên chuỗi, có thể chạy explicit hoặc trong lifecycle integration nếu được cấu hình.
- `nullable=false`: JPA column metadata, có thể được dùng để sinh DDL hoặc định nghĩa mapping intent.
- `length=60`: column length metadata cho schema generation; không phải một phương thức “chặn mọi chuỗi hơn 60 ký tự” trong Java ở mọi đường code.

**Database production chỉ có những constraints đã thực sự được tạo và được DBMS thực thi.** Nếu production dùng migrations, entity annotation không tự chạy `ALTER TABLE`.

### 10.1. Một bảng phân biệt

| JPA/Validation metadata | Ý nghĩa | Bảo vệ DB cuối cùng tương ứng |
| --- | --- | --- |
| `@NotNull` | Field/reference không null khi được validate | `NOT NULL` |
| `@NotBlank` | Chuỗi phải có ký tự không phải whitespace | Cần check/validation riêng nếu DB phải cưỡng chế |
| `@Column(nullable=false)` | Mapping/schema hint | `NOT NULL` phải tồn tại thật |
| `@Column(unique=true)` | Schema metadata | `UNIQUE` constraint/index phải tồn tại thật |
| `@JoinColumn(nullable=false)` | FK column metadata | `NOT NULL` và FK constraint thích hợp |
| `@Version` | Optimistic locking khi managed updates | Version column + provider SQL behavior |
| `@Valid` | Cascade Bean Validation | Không tương đương `ON DELETE CASCADE`/FK |
| `CascadeType.PERSIST` | Cascade JPA lifecycle | Không tương đương data validation |

### 10.2. Tại sao phải kiểm tra schema thực tế?

Một migration chưa chạy có thể khiến entity ghi `unique=true` nhưng DB không có unique constraint. Khi có hai writers đồng thời, duplicate vẫn xảy ra.

Không kết luận “đã có constraint” chỉ bằng cách đọc Java source.

## 11. Thiết kế database schema có bảo vệ tenant

Ta dùng PostgreSQL-flavored DDL để minh họa. Cú pháp phải điều chỉnh theo DBMS/migrations của dự án.

```sql
CREATE TABLE tenants (
    id VARCHAR(80) PRIMARY KEY
);

CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    name VARCHAR(160) NOT NULL,

    CONSTRAINT fk_customer_tenant
        FOREIGN KEY (tenant_id)
        REFERENCES tenants(id),

    CONSTRAINT uq_customer_tenant_id
        UNIQUE (tenant_id, id)
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    customer_id BIGINT NOT NULL,
    reference VARCHAR(60) NOT NULL,
    status VARCHAR(24) NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL,
    version BIGINT NOT NULL,

    CONSTRAINT fk_order_tenant
        FOREIGN KEY (tenant_id)
        REFERENCES tenants(id),

    CONSTRAINT fk_order_customer_same_tenant
        FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customers(tenant_id, id),

    CONSTRAINT uq_order_reference_per_tenant
        UNIQUE (tenant_id, reference),

    CONSTRAINT ck_order_total_nonnegative
        CHECK (total_amount >= 0),

    CONSTRAINT ck_order_status
        CHECK (
            status IN (
                'DRAFT',
                'SUBMITTED',
                'APPROVED',
                'CANCELLED'
            )
        )
);

CREATE INDEX idx_orders_tenant_status_id
    ON purchase_orders(tenant_id, status, id);
```

### 11.1. Vì sao UNIQUE(tenant_id, reference)?

`reference="PO-001"` có thể hợp lệ ở cả tenant-A và tenant-B, nhưng không được trùng **trong cùng tenant**.

Nếu unique chỉ trên `reference`, hai tenants có thể ảnh hưởng nhau không cần thiết.

Nếu unique chỉ do Java code kiểm tra, concurrent inserts có thể lọt qua.

### 11.2. Vì sao composite foreign key?

Nếu chỉ có FK:

```sql
FOREIGN KEY (customer_id)
REFERENCES customers(id)
```

DB bảo đảm Customer tồn tại nhưng **không bảo đảm cùng tenant**.

Ràng buộc:

```sql
FOREIGN KEY (tenant_id, customer_id)
REFERENCES customers(tenant_id, id)
```

yêu cầu cặp tenant–customer hợp lệ; một Order tenant-A không thể trỏ Customer tenant-B chỉ bằng việc chọn customer ID của B.

### 11.3. Vì sao Customer cần UNIQUE(tenant_id, id)?

Một composite FK tham chiếu cặp cột cần một candidate key/unique key thích hợp ở bảng đích. Dù `id` đã unique, composite target thường phải được khai báo ràng buộc unique tương ứng để DBMS chấp nhận composite FK.

### 11.4. Composite FK không bảo vệ mọi permission

Nó ngăn cross-tenant relationship trong database, nhưng chưa chứng minh actor có quyền **đọc/sửa Customer đó**. Hai User trong cùng tenant có thể có vai trò khác nhau.

### 11.5. Schema cần quản lý bằng migration

DDL ở trên là illustration. Trong dự án production, dùng migrations versioned, kiểm soát index, thời gian khóa bảng, backfill và backward compatibility.

## 12. Trách nhiệm của foreign key

Một FK:

```sql
FOREIGN KEY (customer_id)
REFERENCES customers(id)
```

bảo vệ **reference integrity** tại thời điểm database kiểm tra constraint.

Nếu request chỉ kiểm tra:

```java
Customer customer =
    em.find(Customer.class, customerId);

if (customer != null) {
    // Tiếp tục...
}
```

thì việc Customer có thể bị transaction khác xóa sau SELECT vẫn là tình huống cần xem.

### 12.1. Service check giúp phản hồi sớm

Service có thể trả lỗi “Customer không hợp lệ” trước khi persist.

### 12.2. FK bảo vệ cuối cùng

Nếu một writer khác xóa Customer trước khi Order được commit, DB FK có thể từ chối INSERT/UPDATE theo transaction/locking semantics.

### 12.3. FK không tự kiểm tra domain eligibility

Một Customer bị đánh dấu inactive vẫn là row có thật. FK vẫn đúng. Nếu không cho Order mới tham chiếu inactive Customer, service/domain phải bảo vệ; nếu cần cưỡng chế ở DB, cần cơ chế khác được thiết kế riêng chứ không chỉ FK.

### 12.4. Không suy FK có nghĩa thao tác đã được ủy quyền

Một hacker có thể chọn Customer ID hợp lệ trong cùng tenant; FK không biết quyền của hacker trên Customer đó.

## 13. UNIQUE và race condition: check-before-insert là chưa đủ

Giả sử hai requests đồng thời tạo cùng mã đơn:

```text
T1: SELECT exists reference='PO-001' -> false
T2: SELECT exists reference='PO-001' -> false

T1: INSERT (tenant-A, PO-001)
T2: INSERT (tenant-A, PO-001)

T1: COMMIT
T2: COMMIT
```

Nếu chỉ có Java check, DB có thể nhận hai bản ghi.

Với:

```sql
UNIQUE (tenant_id, reference)
```

chỉ một transaction có thể tạo một trạng thái committed phù hợp; transaction còn lại sẽ bị chặn hoặc thất bại theo constraint/transaction behavior.

### 13.1. Kiểm tra trước vẫn có giá trị

Ứng dụng có thể:

```java
boolean exists = em.createQuery(
    """
    SELECT COUNT(o)
    FROM PurchaseOrder o
    WHERE o.tenantId = :tenantId
      AND o.reference = :reference
    """,
    Long.class
)
.setParameter("tenantId", tenantId)
.setParameter("reference", reference)
.getSingleResult() > 0;
```

để báo lỗi thân thiện. Nhưng **không sử dụng kết quả đó như bằng chứng duy nhất**.

### 13.2. Xử lý lỗi race sau DB constraint

Nếu insert thất bại vì unique constraint, transaction phải được rollback theo framework/transaction policy; có thể chuyển thành `409 Conflict` theo API contract.

Không nên catch persistence exception rồi tiếp tục thực hiện các ghi khác trong cùng transaction mà không hiểu transaction đã rollback-only hay chưa.

### 13.3. Retry phải có chính sách

Một duplicate reference do người dùng chọn có thể cần người dùng đổi mã, không phải tự retry vô hạn. Một conflict do optimistic locking có thể cần reload/re-evaluate. Mỗi loại lỗi cần policy khác nhau.

## 14. CHECK và NOT NULL: bảo vệ bất biến cục bộ

Với dữ liệu tiền:

```sql
CONSTRAINT ck_order_total_nonnegative
CHECK (total_amount >= 0)
```

DB bảo đảm không commit giá trị âm cho cột tương ứng, kể cả khi thao tác dùng native SQL/JDBC hoặc bypass Bean Validation.

### 14.1. Domain check vẫn nên có

```java
public void changeTotal(BigDecimal total) {
    if (total == null || total.signum() < 0) {
        throw new IllegalArgumentException(
            "total must be non-negative"
        );
    }
    this.totalAmount = total;
}
```

Domain method giúp thất bại sớm với thông báo phù hợp, trước khi SQL chạy.

### 14.2. Cẩn thận với SQL NULL semantics

Một `CHECK(total_amount >= 0)` không thay thế `NOT NULL`. Theo SQL three-valued logic, khi biểu thức CHECK trả UNKNOWN vì null, kết quả có thể không bị từ chối.

Do đó cần **cả `NOT NULL` lẫn `CHECK`** nếu yêu cầu là “không null và không âm”.

### 14.3. CHECK không thể diễn đạt mọi invariant liên bảng

Ví dụ “Order SUBMITTED phải có ít nhất một OrderLine” phụ thuộc existence của row trong bảng khác. Một `CHECK` bình thường trên Order thường không trực tiếp thể hiện được quy tắc liên bảng này.

Cần domain logic/transaction design; trong một số hệ thống có thể cần triggers, stored procedures, deferred constraints hoặc mô hình dữ liệu khác.

### 14.4. Database constraint cũng có giới hạn theo DBMS

Cú pháp và semantics của CHECK/deferrable constraints/conditional uniqueness có thể khác nhau. Không suy mọi DBMS áp dụng cùng cơ chế chỉ vì JPA entity dùng annotation giống nhau.

## 15. Một application service kiểm tra cả identity, scope và domain

Ví dụ Spring service sử dụng JPA. Đây là code minh họa, giả định có `PurchaseOrder`, `OrderStatus`, `AuthorizationPolicy`, `ActorContext` và entity methods thích hợp.

```java
package com.example.orders.application;

import com.example.orders.domain.PurchaseOrder;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SubmitOrderService {

    @PersistenceContext
    private EntityManager em;

    private final AuthorizationPolicy authorization;

    public SubmitOrderService(
            AuthorizationPolicy authorization) {
        this.authorization = authorization;
    }

    @Transactional
    public void submit(
            long orderId,
            ActorContext actor) {

        // actor phải do lớp xác thực tin cậy tạo ra.
        String tenantId = actor.trustedTenantId();

        PurchaseOrder order = em.createQuery(
            """
            SELECT o
            FROM PurchaseOrder o
            WHERE o.id = :orderId
              AND o.tenantId = :tenantId
            """,
            PurchaseOrder.class
        )
        .setParameter("orderId", orderId)
        .setParameter("tenantId", tenantId)
        .getResultStream()
        .findFirst()
        .orElseThrow(() ->
            new ResourceNotVisibleException()
        );

        // Quyền cụ thể, không chỉ quyền đăng nhập.
        authorization.requireCanSubmit(actor, order);

        // Domain invariant: DRAFT, đủ lines...
        order.submit();

        // SQL/DB constraints có thể thất bại ở flush.
        em.flush();
    }
}
```

### 15.1. Các lớp trong ví dụ

1. `ActorContext` từ trusted security context, không tự dựng từ request body.
2. Query có predicate `tenantId` để không đọc Order khác tenant.
3. `requireCanSubmit` xác định quyền cụ thể trên Order.
4. `order.submit()` kiểm tra business transition.
5. JPA dirty checking và `@Version` nếu được cấu hình.
6. Database kiểm tra constraints khi flush/commit.

### 15.2. Những điều ví dụ chưa tự giải quyết

- Permission có thể thay đổi đồng thời.
- Một membership update khác có thể race với submit.
- Ràng buộc cần đọc thêm Lines có thể tạo LAZY queries.
- Remote authorization policy có thể có consistency riêng.
- Transaction commit vẫn có thể thất bại sau `em.flush()`.

Với thao tác nhạy cảm, phải lựa chọn transaction isolation/locking và authorization consistency policy dựa trên nghiệp vụ.

### 15.3. Vì sao không làm tất cả trong controller?

Controller không phải entrypoint duy nhất. Nếu business checks nằm trong service, batch jobs/message consumers cũng có khả năng tái sử dụng một operation được bảo vệ.

### 15.4. Phân quyền cần được áp dụng nhất quán

Không để một phương thức `submitFromAdmin()` bỏ qua mọi kiểm tra chỉ vì tên gọi là “admin”. Quyền đặc biệt phải có một chính sách rõ và audit phù hợp.

## 16. JPQL parameter binding và chống injection

Một rủi ro ở biên dữ liệu là đưa input không tin cậy trực tiếp vào câu query.

### 16.1. Không nối chuỗi giá trị từ request

Sai:

```java
String jpql =
    "SELECT o FROM PurchaseOrder o " +
    "WHERE o.reference = '" + reference + "'";

return em.createQuery(
    jpql, PurchaseOrder.class
).getResultList();
```

Nếu `reference` chứa dấu nháy hoặc cú pháp đặc biệt, query có thể bị thay đổi ý nghĩa.

### 16.2. Dùng tham số

Đúng:

```java
return em.createQuery(
    """
    SELECT o
    FROM PurchaseOrder o
    WHERE o.reference = :reference
      AND o.tenantId = :tenantId
    """,
    PurchaseOrder.class
)
.setParameter("reference", reference)
.setParameter("tenantId", trustedTenantId)
.getResultList();
```

`setParameter()` tách **giá trị dữ liệu** khỏi query structure theo contract JPA.

### 16.3. Parameter binding không dùng cho tên cột

Một client gửi:

```text
sortBy=createdAt
```

không thể dùng bind parameter để thay một identifier hoặc keyword:

```sql
ORDER BY :columnName
```

và kỳ vọng DB hiểu `:columnName` là tên cột.

Dùng **allowlist**:

```java
String sortProperty = switch (requestedSort) {
    case "createdAt" -> "o.createdAt";
    case "reference" -> "o.reference";
    default -> throw new IllegalArgumentException(
        "Unsupported sort field"
    );
};
```

Rồi ứng dụng mới xây `ORDER BY` từ những giá trị code đã kiểm soát, không từ raw input. Có thể dùng Criteria API để xây sort expressions rõ hơn.

### 16.4. Native SQL cũng phải parameterize

```java
em.createNativeQuery(
    """
    SELECT *
    FROM purchase_orders
    WHERE tenant_id = :tenantId
      AND reference = :reference
    """,
    PurchaseOrder.class
)
.setParameter("tenantId", trustedTenantId)
.setParameter("reference", reference);
```

Đây là kiểu dùng named parameters phổ biến qua JPA provider; với native query cần bảo đảm hỗ trợ parameter syntax theo JPA/provider đang dùng. Với portability cao nhất cho native SQL, cân nhắc positional parameters hoặc JDBC prepared statements theo contract thích hợp.

### 16.5. Không lưu raw SQL lỗi vào response

Khi có query syntax error hoặc constraint exception, client chỉ nên nhận thông báo có chủ đích; internal logs phải tránh secrets và PII.

## 17. Query filtering không giống database RLS

Một cách phổ biến để cô lập tenant là thêm:

```jpql
WHERE o.tenantId = :trustedTenantId
```

trong tất cả query liên quan.

Đây là **application-enforced row scoping**, không phải Row-Level Security của database.

### 17.1. Rủi ro quên predicate

Một developer mới viết:

```java
em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).getResultList();
```

có thể vô tình trả Orders mọi tenant nếu DB account có quyền đọc tất cả và không có isolation khác.

### 17.2. Đóng gói repository APIs

Một hướng là repository không expose method `findAll()` không scope cho đường nghiệp vụ, mà dùng:

```java
findByIdVisibleToActor(...)
listForTenant(...)
findOrderLineWithinOrder(...)
```

Điều này giảm rủi ro quên điều kiện, nhưng không thay một ràng buộc ở DB nếu có writer khác hoặc native SQL bypass repository.

### 17.3. JPA filters provider-specific

Hibernate có filter/multitenancy extensions để tự áp predicates theo cấu hình. Chúng hữu ích nhưng không phải một cơ chế authorization chuẩn của JPA.

Không tự xem filter provider là bảo đảm tuyệt đối nếu:

- Filter không bật trên mọi session.
- Bulk/native SQL bypass hoặc xử lý khác.
- Một entrypoint quên set tenant.
- Cache key/invalidation không phù hợp.

### 17.4. Khi cần isolation mạnh hơn

Database roles, schemas riêng, databases riêng hoặc Row-Level Security có thể bổ sung một lớp bảo vệ không phụ thuộc mọi query repository đều viết đúng.

## 18. Row-Level Security (RLS): hàng rào tại database

**Row-Level Security** là tính năng của một số DBMS, chẳng hạn PostgreSQL, không phải một API bảo mật đa tenant tiêu chuẩn của Jakarta Persistence.

Với PostgreSQL, có thể cấu hình policies trên bảng:

```sql
ALTER TABLE purchase_orders
ENABLE ROW LEVEL SECURITY;

ALTER TABLE purchase_orders
FORCE ROW LEVEL SECURITY;

CREATE POLICY order_tenant_policy
ON purchase_orders
FOR ALL
USING (
    tenant_id =
    current_setting('app.tenant_id', true)
)
WITH CHECK (
    tenant_id =
    current_setting('app.tenant_id', true)
);
```

Đây là ví dụ cho một chính sách tenant đơn giản, không phải thiết kế RLS hoàn chỉnh cho mọi sản phẩm.

### 18.1. USING và WITH CHECK

- **`USING`** kiểm soát những rows phù hợp policy khi đọc hoặc tác động tới rows hiện hữu, tùy loại statement.
- **`WITH CHECK`** kiểm soát giá trị rows mới hoặc được cập nhật phải thỏa policy.

Một policy chỉ đọc có thể bảo vệ SELECT mà không đủ cho INSERT/UPDATE; cần thiết kế chính sách cho các thao tác được phép.

### 18.2. Setting tenant ở phạm vi transaction

Trong PostgreSQL, có thể đặt một cấu hình transaction-local phù hợp:

```sql
SELECT set_config('app.tenant_id', 'tenant-A', true);
```

Tham số thứ ba `true` yêu cầu setting ở phạm vi transaction hiện tại.

Trong JDBC/JPA, giá trị tenant phải được truyền theo cách tránh injection và nhất quán với **connection đang thực thi SQL**, ví dụ dùng prepared parameter cho `set_config` trong transaction.

### 18.3. Vì sao cần transaction-local với connection pool?

Nếu dùng session-level setting không được reset, một physical connection có thể quay về pool khi vẫn giữ tenant-A. Request tenant-B lấy lại connection đó và có nguy cơ chạy dưới context sai.

Một chính sách cần bảo đảm:

- Tenant được thiết lập trước mọi SQL tương ứng.
- Setting là transaction-local hoặc được reset chắc chắn.
- Toàn transaction dùng đúng connection/context theo thiết kế.
- Không chạy query ngoài transaction với context không xác định.
- RLS policy **fail closed** khi setting không có.
- Pool/driver/provider integration được kiểm thử thật.

### 18.4. RLS không tự biết caller thực sự là ai

Nếu application dùng một DB role có quyền tự đặt `app.tenant_id` thành bất kỳ giá trị nào, RLS chỉ kiểm tra **giá trị setting**, không xác minh độc lập JWT của người dùng.

Nếu attacker chiếm được quyền chạy SQL tùy ý trong app hoặc application đặt tenant từ body chưa xác thực, họ có thể thao túng context. Do đó trusted identity và input handling ở biên vẫn thiết yếu.

### 18.5. Quyền BYPASSRLS và table owner

Trên PostgreSQL, roles có quyền `BYPASSRLS` và một số superuser/owner behaviors có thể bypass policies; `FORCE ROW LEVEL SECURITY` thay đổi hành vi của table owner nhưng không làm mọi quyền đặc biệt biến mất.

App runtime role không nên được cấp quyền vượt RLS khi chính sách dựa vào RLS.

### 18.6. RLS không thay các constraints

RLS không thay `UNIQUE`, `FOREIGN KEY`, `CHECK` và `NOT NULL`. Nó phục vụ row access policy; schema constraints phục vụ integrity.

### 18.7. Bảo vệ transaction không chỉ bằng RLS

Một service vẫn phải kiểm tra nghiệp vụ: không submit order rỗng, không vượt hạn mức, không phê duyệt sai vai trò. RLS tenant policy đơn giản chỉ bảo vệ tenant scoping.

## 19. Cấp quyền database theo least privilege

Nếu production application chỉ cần dữ liệu nghiệp vụ, DB account của nó thường không cần:

```text
DROP TABLE
ALTER TABLE
CREATE ROLE
CREATE EXTENSION
SUPERUSER
BYPASSRLS
```

### 19.1. Tách application và migration roles

```text
CI/CD migration identity
  -> CREATE / ALTER / DROP có kiểm soát

Application runtime identity
  -> SELECT / INSERT / UPDATE / DELETE
     trên tables/procedures cần thiết

Reporting identity
  -> SELECT giới hạn theo nhu cầu
```

### 19.2. Vì sao có ích?

Nếu application bị injection hoặc configuration error, một DB role có ít quyền có thể giảm phạm vi tác động.

Không biến least privilege thành “đã hết rủi ro”; application role có quyền UPDATE toàn bộ rows vẫn có thể gây hại nếu không có authorization/RLS constraints phù hợp.

### 19.3. Privileges có thể chi tiết hơn theo thao tác

Tùy DBMS, có thể cấp quyền theo bảng/cột, dùng views hoặc stored procedures để giới hạn hành động. Đây là lớp bảo vệ database-specific cần phối hợp với JPA mappings và use cases.

### 19.4. Không để migration admin credentials trong runtime config

Tách secrets, rotation, storage và access control. Không ghi password/token/connection strings có credentials vào SQL log hay artifacts debug.

## 20. Transaction và TOCTOU: kiểm tra trước không đủ khi dữ liệu thay đổi

**Time-of-check to time-of-use (TOCTOU)** xuất hiện khi ứng dụng kiểm tra trạng thái, sau đó sử dụng kết quả ấy như thể dữ liệu không thể đổi.

Ví dụ:

```text
T1: read Order#9001 status=DRAFT
T2: update Order#9001 status=CANCELLED, commit
T1: submit Order#9001 based on stale state
```

### 20.1. @Version và optimistic locking

```java
@Version
@Column(nullable = false)
private Long version;
```

Với managed entity updates, JPA provider sử dụng version để phát hiện update trên state đã cũ theo optimistic locking semantics.

Một dạng SQL minh họa:

```sql
UPDATE purchase_orders
SET status = 'SUBMITTED',
    version = 6
WHERE id = 9001
  AND version = 5;
```

Nếu không còn row phù hợp, provider có thể phát hiện optimistic conflict theo lifecycle/transaction.

### 20.2. @Version không bảo vệ mọi điều kiện authorization

Giả sử role của actor bị thu hồi trong bảng `memberships` nhưng Order không bị update version. `@Version` trên Order **không tự phát hiện** role đã bị thay đổi.

Nếu business yêu cầu quyền phải còn hiệu lực đến thời điểm commit, cần một transaction/locking/authorization consistency strategy phù hợp.

### 20.3. Conditional update

Một thao tác đơn giản có thể dùng điều kiện ngay trong SQL:

```sql
UPDATE purchase_orders
SET status = 'SUBMITTED'
WHERE id = :orderId
  AND tenant_id = :tenantId
  AND status = 'DRAFT';
```

Sau đó kiểm tra số rows affected. Đây là **state transition guard ở database statement**.

Nhưng lưu ý: nếu thực hiện bằng JPQL bulk DML thì entity callbacks, managed state và version semantics khác với managed entity update; không tự coi hai cách hoàn toàn tương đương.

### 20.4. Khi cần lock

Một số quy tắc như hạn mức tồn kho/chi tiêu cần:

- Atomic conditional update.
- Optimistic locking.
- Pessimistic lock.
- Transaction isolation thích hợp.
- Unique/FK constraints.
- Hoặc một protocol cấp phát theo resource.

Không dùng duy nhất câu `SELECT COUNT(...)` rồi tin trạng thái sẽ giữ nguyên đến lúc commit.

## 21. Row ownership và child associations

Một API:

```http
DELETE /api/orders/9001/lines/500
```

có ít nhất ba đối tượng cần xét:

1. Actor thuộc tenant nào?
2. Order#9001 có thuộc phạm vi actor không?
3. Line#500 có thật sự thuộc Order#9001 không?

### 21.1. Sai: xóa line theo ID bất kỳ

```java
OrderLine line = em.find(OrderLine.class, lineId);
em.remove(line);
```

Nếu chỉ kiểm tra orderId ở URL nhưng không kiểm tra membership, client có thể nhắm đến một line của Order khác.

### 21.2. Query có cả parent và tenant predicates

```java
OrderLine line = em.createQuery(
    """
    SELECT l
    FROM OrderLine l
    JOIN l.order o
    WHERE l.id = :lineId
      AND o.id = :orderId
      AND o.tenantId = :tenantId
    """,
    OrderLine.class
)
.setParameter("lineId", lineId)
.setParameter("orderId", orderId)
.setParameter("tenantId", trustedTenantId)
.getResultStream()
.findFirst()
.orElseThrow(() ->
    new ResourceNotVisibleException()
);
```

Sau đó vẫn phải kiểm tra quyền xóa line và business state của Order.

### 21.3. DB FK kiểm tra quan hệ tồn tại, không bảo vệ permission

FK đảm bảo `order_lines.order_id` tham chiếu Order hiện hữu. Nó không nhất thiết biết caller có quyền xóa Line#500.

### 21.4. Quan hệ nhiều tenant cần composite FK tương ứng

Nếu OrderLine có `tenant_id` riêng, có thể thiết kế composite FK tới `(tenant_id, order_id)` để ngăn child tenant-A trỏ parent tenant-B. Nếu schema không giữ tenant trên child, isolation phải được bảo vệ bằng cấu trúc tham chiếu/layer khác.

## 22. JPA cascade và orphanRemoval không phải security policy

Một parent mapping:

```java
@OneToMany(
    mappedBy = "order",
    cascade = {
        CascadeType.PERSIST,
        CascadeType.MERGE
    },
    orphanRemoval = true
)
private List<OrderLine> lines;
```

có thể tự lan truyền lifecycle operations và xóa orphan lines theo mapping semantics.

### 22.1. Điều cascade không làm

- Không kiểm tra actor có quyền xóa child.
- Không kiểm tra tenant từ security principal.
- Không kiểm tra child có được chuyển sang parent khác không.
- Không bảo đảm URL orderId khớp child thuộc về.
- Không ngăn mass assignment qua detached graph.

### 22.2. Không expose mutable collection cho client

Nếu request được bind thành entity rồi merge, việc bỏ thiếu một collection có thể bị diễn giải thành thay đổi graph và tạo side effects với orphanRemoval.

### 22.3. Chỉ thay đổi graph qua commands

Ví dụ:

```java
order.removeLine(line);
```

sau khi service kiểm tra authorization và domain invariants. Helper cập nhật cả hai phía quan hệ; database FK/orphan removal đảm bảo lifecycle lưu trữ phù hợp.

### 22.4. Không cascade REMOVE tới shared entities

Đừng đặt `CascadeType.ALL` trên `@ManyToOne Product` dùng chung chỉ để “lưu dễ hơn”, vì có thể cascade REMOVE gây tác động tới dữ liệu không thuộc aggregate.

## 23. Bulk DML, native SQL và bypass các rào chắn ở entity

JPQL bulk update:

```java
int updated = em.createQuery(
    """
    UPDATE PurchaseOrder o
    SET o.status = :status
    WHERE o.tenantId = :tenantId
      AND o.status = :oldStatus
    """
)
.setParameter("status", OrderStatus.CANCELLED)
.setParameter("tenantId", trustedTenantId)
.setParameter("oldStatus", OrderStatus.DRAFT)
.executeUpdate();
```

### 23.1. Bulk DML bỏ qua những gì?

Bulk JPQL DML không đi qua từng managed entity update theo cách dirty checking thông thường; không tự gọi entity callbacks trên từng row hoặc tự đồng bộ mọi entity đang managed.

Do đó nếu security/domain policy được đặt chỉ trong:

```java
@PreUpdate
void validateAccess() { ... }
```

thì bulk DML có thể bỏ qua. Authorization cũng **không nên** được gắn độc quyền vào JPA lifecycle callback.

### 23.2. Authorization phải xảy ra trước bulk operation

Với batch action, service cần xác thực actor có quyền thực hiện hành động hàng loạt, xác định tập rows được phép và dùng predicates phù hợp.

Một `WHERE tenant_id = :tenantId` là lớp scoping cơ bản; nếu permissions ở mức order/owner cụ thể thì phải đưa vào policy/query hoặc kiểm tra theo quy trình thích hợp.

### 23.3. DB constraints vẫn có vai trò

Unique/FK/CHECK/NOT NULL vẫn được database áp dụng cho DML theo semantics của DB, kể cả khi JPA callbacks không chạy.

RLS cũng có thể áp dụng nếu DB role/context/policy được cấu hình đúng.

### 23.4. Native SQL càng cần kỷ luật

Một câu `UPDATE purchase_orders SET status=...` thiếu WHERE có thể tác động mọi tenant. Parameter binding không tự thêm tenant predicate.

Cần giới hạn quyền DB, kiểm soát query templates, review, tests và transactional safeguards.

### 23.5. Persistence context có thể stale

Sau bulk DML:

```java
em.flush();
int rows = query.executeUpdate();
em.clear();
```

mẫu này chỉ phù hợp khi `clear()` là chủ đích (mọi entities hiện managed sẽ bị detach). Một transaction phức tạp có thể cần thiết kế flush/reload cẩn thận hơn.

## 24. Soft delete: bảo mật khác với hiển thị

Một hệ thống có field:

```java
@Column(nullable = false)
private boolean deleted;
```

và thay DELETE thật bằng:

```sql
UPDATE purchase_orders
SET deleted = true
WHERE id = :id;
```

### 24.1. deleted=true không phải physical deletion

Row vẫn nằm trong database và có thể được nhìn thấy bởi:

- Native SQL queries không filter.
- Admin tools.
- Audit/report jobs.
- Database backups.
- Một số joins/queries khác.

Nếu yêu cầu pháp lý là xóa dữ liệu thực hoặc hạn chế lưu PII, soft delete không tự đáp ứng.

### 24.2. Filter deleted rows phải nhất quán

Repository có thể dùng `WHERE o.deleted = false`. Hibernate có soft-delete/filter extensions; chúng là cơ chế provider-specific, cần kiểm tra với native SQL và bulk queries.

### 24.3. Unique constraints với soft delete

Nếu muốn tái sử dụng `reference` sau khi một Order bị soft delete, cần quy tắc uniqueness rõ ràng.

Một filtered/partial unique index như:

```sql
CREATE UNIQUE INDEX uq_active_order_reference
ON purchase_orders(tenant_id, reference)
WHERE deleted = false;
```

là ví dụ **PostgreSQL-specific**, không phải một annotation `@UniqueConstraint` portable JPA giải quyết đầy đủ mọi trường hợp. DBMS khác có phương án khác.

### 24.4. Security policy và retention policy khác nhau

Không trả một soft-deleted row qua API không tự bảo đảm dữ liệu đã bị purge, mã hóa hoặc đáp ứng retention.

## 25. Audit và khả năng quy trách nhiệm

Bảo mật dữ liệu còn cần biết:

- Ai thực hiện một thay đổi?
- Hành động gì?
- Trên resource nào?
- Trước/sau trạng thái ở mức cần audit?
- Giao dịch đã commit hay rollback?
- Log có bị giả mạo hoặc sửa trái phép không?

### 25.1. Entity listeners có thể hỗ trợ audit fields

```java
@PrePersist
void onCreate() {
    createdAt = Instant.now();
}
```

nhưng callback không có đủ context để xác minh mọi authorization. Nó cũng không tự tạo một audit trail bất biến với xác nhận sau commit.

### 25.2. Bulk DML và external writers

Một bulk UPDATE hoặc SQL job có thể không kích hoạt entity listeners, nên chỉ dựa vào callbacks cho audit quan trọng có thể tạo lỗ hổng coverage.

### 25.3. Audit không chỉ là log thông thường

Một HTTP log có thể ghi “requested submit” nhưng transaction rollback. Nếu nghiệp vụ cần bằng chứng thay đổi durable, có thể sử dụng transactional audit table, CDC hoặc transactional outbox theo thiết kế phù hợp.

### 25.4. Không ghi secrets/PII thừa

Audit nên lưu tối thiểu các thông tin cần thiết, có quyền truy cập riêng và retention policy. Tránh log raw tokens, passwords, personal identifiers hoặc payload toàn phần một cách thiếu kiểm soát.

## 26. Encryption và bảo vệ dữ liệu nhạy cảm

Constraints bảo vệ tính hợp lệ của dữ liệu nhưng **không tự giữ bí mật giá trị**.

Một cột:

```sql
email VARCHAR(255) NOT NULL UNIQUE
```

vẫn có thể chứa PII ở dạng đọc được bởi người có quyền DB.

### 26.1. Các lớp bảo vệ dữ liệu nhạy cảm

- Encryption in transit (TLS).
- Encryption at rest của storage/database.
- Application-level encryption cho trường đặc biệt nhạy cảm khi yêu cầu.
- Password hashing với thuật toán phù hợp (không lưu plaintext password).
- Access controls trên bảng/cột/schema.
- Masking/redaction ở API/logs.
- Key management và rotation.

### 26.2. AttributeConverter không tự biến dữ liệu thành an toàn

JPA `AttributeConverter` có thể mã hóa/chuyển đổi giá trị trước khi lưu, nhưng bảo mật thực tế phụ thuộc algorithm, nonce/IV, key management, rotation, threat model và quyền truy cập.

Không gọi Base64 encoding hoặc một phép biến đổi reversible đơn giản không có key là “mã hóa”.

### 26.3. Tìm kiếm và uniqueness trên dữ liệu mã hóa

Nếu mã hóa email ngẫu nhiên có nonce, cùng email có thể tạo ciphertext khác nhau; DB UNIQUE trên ciphertext **không còn cưỡng chế uniqueness của plaintext**.

Có thể cần blind index/hash được thiết kế chuyên biệt với threat model và key management, chứ không tự dùng `@Column(unique=true)` trên ciphertext rồi coi là đủ.

### 26.4. Phân quyền vẫn thiết yếu

Ngay cả khi database có encryption at rest, application đã giải mã vẫn có thể vô tình trả dữ liệu tenant khác. Encryption không thay thế authorization.

## 27. Chiến lược transaction cho những thao tác nhạy cảm

Một action như approve payment/refund có thể yêu cầu nhiều bước:

```text
Authenticate actor
    |
Authorize approval limit
    |
Load Order and current state
    |
Check amount / business policy
    |
Apply state transition
    |
Persist audit record
    |
Commit atomically
```

### 27.1. Đặt operation tại transactional service

Không rải kiểm tra qua nhiều controllers mà mỗi controller tự thực hiện một nửa policy.

### 27.2. Đảm bảo kiểm tra và ghi phù hợp cùng transaction

Đọc dữ liệu ở một transaction rồi ghi ở transaction khác có thể làm check stale. Tuy nhiên chỉ đặt `@Transactional` không tự bảo đảm mọi invariant nhiều hàng dưới concurrency.

### 27.3. Khi authorization dùng dữ liệu từ DB

Nếu quyền dựa vào một row `approval_limits` hoặc `memberships` có thể thay đổi đồng thời, cần xác định:

- Quyền ở thời điểm request hay đến thời điểm commit?
- Có dùng snapshot/isolation nào?
- Có lock/version membership không?
- Có kiểm tra lại trước write không?
- Có rule thu hồi quyền tức thời không?

Không có một câu trả lời chung; yêu cầu nghiệp vụ và threat model quyết định.

### 27.4. Transaction rollback khi lỗi

Một FK/UNIQUE/optimistic lock exception có thể làm transaction rollback-only. Không tiếp tục các thao tác ghi sau lỗi nếu transaction đã không còn an toàn.

### 27.5. External side effects

Không gọi payment gateway hoặc gửi email không thể rollback như một phần “DB transaction” rồi cho rằng cả hai được commit/rollback cùng nhau. Dùng idempotency, outbox và workflow phù hợp khi cần.

## 28. Query đọc và query ghi đều cần security scope

Đọc có thể làm lộ dữ liệu; ghi có thể làm hỏng dữ liệu. Cả hai phải xét object scope.

### 28.1. Đọc một Order

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.id = :id
  AND o.tenantId = :tenantId
```

### 28.2. Liệt kê Orders

```jpql
SELECT o
FROM PurchaseOrder o
WHERE o.tenantId = :tenantId
ORDER BY o.id
```

Với pagination:

```java
query.setMaxResults(50);
```

### 28.3. Đếm Orders

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
WHERE o.tenantId = :tenantId
```

Nếu count query quên tenant predicate, response có thể tiết lộ số lượng records của tenants khác, kể cả khi danh sách rows đã được lọc.

### 28.4. Aggregate báo cáo

```jpql
SELECT SUM(o.totalAmount)
FROM PurchaseOrder o
WHERE o.tenantId = :tenantId
```

Một aggregate có thể làm lộ thông tin nhạy cảm dù không trả từng row. Không chỉ bảo vệ `findById()`.

### 28.5. Ghi hàng loạt

```jpql
UPDATE PurchaseOrder o
SET o.status = :status
WHERE o.tenantId = :tenantId
  AND o.id IN :orderIds
```

Cần xác minh actor có quyền thao tác **toàn bộ tập IDs**, xử lý trường hợp một phần IDs không tồn tại/không thuộc scope và kiểm tra số rows affected theo business contract.

### 28.6. Export và search

CSV export, BI/report API, admin search, autocomplete cũng phải áp filter/scope, giới hạn dữ liệu và kiểm soát quyền. Đây là những con đường rò rỉ dễ bị quên vì không nằm trong REST CRUD chính.

## 29. Database owner constraints khác application ownership

Khái niệm “owner” có thể mang nghĩa khác nhau:

- **FK ownership:** entity nào chứa join column trong mapping.
- **Aggregate ownership:** domain root nào chịu trách nhiệm lifecycle.
- **Resource ownership:** user/team nào có quyền quản lý dữ liệu.
- **DB role/table ownership:** database principal nào sở hữu schema object.

Chúng **không đồng nghĩa**.

### 29.1. JPA owning side

`OrderLine.order` sở hữu FK trong quan hệ hai chiều `@OneToMany(mappedBy="order")`. Điều này không cho biết user nào được sửa OrderLine.

### 29.2. Aggregate root

`PurchaseOrder` có methods `addLine/removeLine` để giữ invariant. Điều này không chứng minh bất kỳ caller nào gọi method cũng có quyền.

### 29.3. Database table owner

DB role sở hữu bảng có thể có privileges đặc biệt. Nó không đại diện “chủ sở hữu đơn hàng” trong nghiệp vụ.

### 29.4. Đừng dùng một từ “owner” mà không nêu loại

Khi review security/mapping, luôn xác định loại ownership đang được nói tới để tránh thiết kế sai lớp.

## 30. Đặt ranh giới cho background jobs và imports

Một batch import có thể bỏ qua controller validation nhưng vẫn dùng JPA:

```java
for (ImportRow row : rows) {
    PurchaseOrder order = mapRow(row);
    em.persist(order);
}
```

### 30.1. Vấn đề

Nếu batch tin mọi `tenantId` trong file CSV, một file được upload có thể tạo cross-tenant writes.

### 30.2. Chính sách phù hợp

- Xác định identity của job/người yêu cầu.
- Tenant phải đến từ trusted job scope hoặc được xác minh.
- Validate các fields của từng row.
- Resolve các reference entities trong đúng tenant.
- Dùng domain methods cho transitions.
- Giữ DB constraints/FK/UNIQUE.
- Quản lý transaction theo chunks.
- Ghi audit/correlation ID.
- Không bỏ qua authorization chỉ vì “internal”.

### 30.3. Event consumers cũng vậy

Một event có thể đến từ service được tin nhưng payload vẫn cần schema validation, identity/resource scoping và idempotency. Trust boundary không tự biến mất khi chuyển từ HTTP sang message queue.

### 30.4. DBA/scripts là đường ghi khác

Nếu nhiều writers trực tiếp ghi DB, các ràng buộc quan trọng phải được DB cưỡng chế hoặc có một data access architecture bảo đảm tất cả writers tuân thủ policy tương ứng.

## 31. Chính sách đa tenant theo kiến trúc lưu trữ

Một số chiến lược:

| Kiến trúc | Ý tưởng | Điểm cần bảo vệ |
| --- | --- | --- |
| Shared database, shared schema | Có cột `tenant_id` | Query scoping, FK/UNIQUE theo tenant, RLS tùy DB |
| Shared database, schema per tenant | Mỗi tenant có schema riêng | Connection/schema switching, quyền DB, migration cho từng schema |
| Database per tenant | Mỗi tenant DB riêng | Routing datasource, credentials, migrations, backups, isolation |
| Hybrid | Dữ liệu lớn/nhạy cảm tách riêng | Quy tắc routing và transaction rõ |

### 31.1. Shared schema

Đơn giản vận hành, nhưng một query thiếu tenant condition có thể ảnh hưởng nhiều khách hàng. Composite FKs/RLS và kiểm thử isolation đặc biệt quan trọng.

### 31.2. Schema per tenant

Không có nghĩa chỉ cần đặt `search_path` từ input client. Phải xác thực tenant và quản lý connection pool/schema context chắc chắn.

### 31.3. Database per tenant

Có thể cung cấp isolation mạnh hơn, nhưng vẫn cần authorization ở application và quản lý secrets/config/routing. Một bug chọn nhầm datasource vẫn nguy hiểm.

### 31.4. Multi-tenancy provider features

Hibernate/EclipseLink có cơ chế multitenancy riêng. Chọn chúng phải hiểu current tenant resolver, connection provider, caching và interaction với transactions. Không mặc nhiên coi provider feature là giải pháp authorization hoàn chỉnh.

## 32. Chuẩn hóa lỗi mà không làm lộ dữ liệu

API có thể gặp:

| Trường hợp | Phản hồi thường cân nhắc | Lưu ý |
| --- | --- | --- |
| Chưa xác thực | 401 | Không tiết lộ dữ liệu |
| Đã xác thực nhưng bị cấm | 403 hoặc 404 theo policy | Tránh existence leak |
| DTO sai | 400/422 | Chỉ trả field errors được phép |
| Entity không tồn tại/không nhìn thấy | 404 | Không phân biệt tenant khác nếu cần ẩn |
| UNIQUE conflict | 409 | Không trả SQL constraint raw |
| Optimistic conflict | 409 | Có thể yêu cầu reload/retry |
| DB tạm thời không sẵn sàng | 5xx phù hợp | Retry policy có giới hạn |
| Authorization backend lỗi | Fail closed theo policy | Không mặc định cho phép |

Đây là **ví dụ thiết kế HTTP API**, không phải quy định tự động của JPA.

### 32.1. Phân loại exceptions

- `jakarta.validation.ConstraintViolationException`: Bean Validation.
- JPA optimistic exceptions: xung đột version/lifecycle.
- DB constraint exceptions qua provider/JDBC: FK/UNIQUE/CHECK/NOT NULL.
- Security exceptions: authentication/authorization.

Không đưa tất cả vào một `catch (Exception)` rồi luôn trả 200 hoặc luôn trả “not found”.

### 32.2. Không leak stack traces

Raw DB errors có thể chứa table/column names, SQL literals hoặc dữ liệu nhạy cảm. Client chỉ cần lỗi có ý nghĩa và correlation ID phù hợp.

### 32.3. Logging phù hợp

Internal logs có thể ghi operation ID, tenant ID đã được phép log theo policy, error category và trace ID; tránh ghi token/password, PII hoặc toàn bộ SQL bind values một cách mặc định.

## 33. Kiểm thử bảo vệ biên ứng dụng

Nhóm test đầu tiên chứng minh caller không thể vượt qua các điểm truy cập.

### 33.1. Test authentication

- Không có token.
- Token hết hạn/không hợp lệ.
- Token sai audience.
- Service identity không có scope.
- Tenant context không được xác định.

Kỳ vọng từ chối theo contract.

### 33.2. Test object-level authorization

Cho tenant-A và tenant-B có Orders riêng:

```text
Actor alice / tenant-A
  GET Order tenant-A -> allowed nếu role phù hợp
  GET Order tenant-B -> denied/not visible
  PATCH Order tenant-B -> denied
  DELETE Line thuộc tenant-B -> denied
```

### 33.3. Test field-level authorization

Gửi các fields nội bộ trong JSON:

```json
{
  "reference": "PO-NEW",
  "tenantId": "tenant-B",
  "status": "APPROVED",
  "approvedByUserId": 1
}
```

Theo contract, ứng dụng nên từ chối unknown fields hoặc bỏ qua chúng một cách an toàn; dù theo hướng nào, **chúng không được làm thay đổi những fields bị cấm**.

### 33.4. Test nested IDs

Request trên Order A nhưng line ID thuộc Order B phải bị từ chối; không chỉ test Order ID ở URL.

### 33.5. Test aggregate endpoints

Search, COUNT, SUM, export và pagination đều phải áp cùng authorization/tenant scope.

### 33.6. Test SQL injection

Dữ liệu như dấu nháy, Unicode và các mẫu input bất thường phải được xử lý như **giá trị**, không thay đổi query structure. Dynamic sort/table names chỉ nhận allowlisted identifiers.

## 34. Kiểm thử ràng buộc dữ liệu thực tại database

Nhóm test thứ hai phải chạy với **database có constraints thật**, không chỉ mock repository.

### 34.1. Foreign key test

Thử lưu Order với `customer_id` không tồn tại. Database phải từ chối theo FK.

### 34.2. Cross-tenant composite FK test

Customer#202 thuộc tenant-B; thử INSERT:

```sql
INSERT INTO purchase_orders (
    tenant_id,
    customer_id,
    reference,
    status,
    total_amount,
    version
)
VALUES (
    'tenant-A',
    202,
    'PO-X',
    'DRAFT',
    0,
    0
);
```

Kỳ vọng composite FK ngăn state không hợp lệ, giả định fixtures/DDL đúng.

### 34.3. Unique test

Tạo hai Orders trong tenant-A cùng reference. DB phải từ chối trạng thái duplicate. Kiểm tra tenant-B có thể dùng cùng reference nếu rule cho phép.

### 34.4. CHECK test

Thử total_amount âm, status ngoài tập. DB từ chối ngay cả khi SQL được phát từ JDBC ngoài JPA.

### 34.5. Null test

Thử null ở các cột bắt buộc. DB phải có `NOT NULL` thực sự.

### 34.6. Test với migrations

Nếu production dùng Flyway/Liquibase, integration test nên chạy cùng migrations và giữ `jakarta.persistence.schema-generation.database.action=none` khi xác nhận schema production contract.

### 34.7. Không chỉ test H2 rồi kết luận PostgreSQL an toàn

DDL/constraints/locking/RLS và enum types có thể khác. Với những tính năng như PostgreSQL RLS hoặc partial indexes, test cần đúng DBMS phù hợp.

## 35. Concurrency tests: chứng minh Java check không đủ

### 35.1. Hai transactions tạo trùng reference

```text
Start:
  No Order(tenant-A, PO-77)

Transaction T1:
  check absent
  insert

Transaction T2:
  check absent
  insert

Concurrent commits:
  only one should succeed with UNIQUE in place
```

Test phải kiểm soát timing bằng latch/barrier thích hợp, mở các transactions độc lập và xác minh **committed DB state**, không chỉ kết quả in-memory.

### 35.2. Hai transactions sửa cùng Order

Với `@Version` trên Order:

- T1 đọc version 3.
- T2 đọc version 3.
- T1 cập nhật và commit version mới.
- T2 cập nhật dựa trên state cũ.

Kỳ vọng optimistic conflict theo semantics/provider.

### 35.3. Quyền thay đổi trong khi transaction đang mở

Test một membership bị thu hồi khi user đang submit. Expected outcome phụ thuộc security policy: permission snapshot tại thời điểm request hay phải còn tại commit.

Quan trọng là **định nghĩa contract** rồi chọn locking/isolation/authorization mechanism phù hợp, không khẳng định `@Transactional` tự giải quyết.

### 35.4. RLS và connection pool test

Nếu dùng PostgreSQL RLS:

- Transaction tenant-A chỉ thấy rows A.
- Transaction tenant-B chỉ thấy rows B.
- Không có tenant setting thì fail closed.
- Reuse physical connection không giữ tenant context cũ.
- Queries ngoài expected transaction không thấy tenant rows.
- App role không có `BYPASSRLS`/quyền đặc biệt không cần thiết.
- INSERT/UPDATE không thể đổi tenantId của row trái policy.

## 36. Kiểm thử các đường ghi bypass JPA callbacks

Các tình huống cần test:

1. Persist/merge một managed entity qua JPA.
2. JPQL bulk update.
3. Native SQL update.
4. JDBC batch import.
5. External writer/ETL.
6. Migration script thay đổi records.
7. Admin tool.
8. Message consumer với payload không tin cậy.

### 36.1. Mục tiêu của test

Không nhất thiết mọi đường đều phải dùng cùng domain methods; nhưng **những invariants được tuyên bố là dữ liệu không bao giờ được vi phạm** phải có cơ chế thực thi tương ứng và kiểm chứng được.

### 36.2. Không đẩy mọi quy tắc vào trigger nếu không cần

Database triggers có thể bảo vệ các invariants đặc biệt, nhưng tăng độ khó debug, versioning và portability. Dùng trigger khi có lý do kiến trúc; không thay toàn bộ application authorization bằng trigger không có user context đáng tin.

### 36.3. Data import phải giữ tenant isolation

Một import job có quyền ghi cross-tenant cần chính sách tường minh về scope, audit và validation, thay vì vô tình được miễn mọi kiểm tra.

## 37. Threat modeling tối thiểu cho JPA application

Một cuộc review đơn giản có thể bắt đầu từ:

| Tài sản | Mối đe dọa | Lớp bảo vệ |
| --- | --- | --- |
| Orders của tenant khác | BOLA/IDOR | AuthZ + tenant-scoped query + RLS |
| Quan hệ Order–Customer | Cross-tenant FK | Domain check + composite FK |
| Reference uniqueness | Concurrent duplicate | UNIQUE constraint |
| Tổng tiền | Client sửa giá | DTO allowlist + server pricing + CHECK |
| Status workflow | Bypass submit/approve | Domain method + AuthZ + transaction |
| DB query | Injection | Bind params + allowlist + least privilege |
| Thông tin nhạy cảm | Leaks từ API/logs | Field authorization + redaction + encryption |
| Cache state | Stale/cross-tenant data | Cache key/invalidation/tenant-safe cache config |
| Data export | Truy xuất hàng loạt | Scoped query + quotas + audit |
| Migrations | DROP/ALTER nhầm | CI/CD controls + separate DB role + backup |
| Background import | Bypass HTTP checks | Trusted identity + service policy + DB constraints |

### 37.1. Một feature có thể có nhiều tài sản và entrypoints

Không chỉ test REST endpoints. GraphQL, admin UI, scheduled jobs, listeners, event consumers và direct SQL integrations đều nằm trong threat model nếu chúng có quyền đọc/ghi dữ liệu.

### 37.2. Cần test cả negative paths

Một ứng dụng có thể pass test “alice xem Order của alice” nhưng fail test “alice sửa Order của bob”. Security tests phải kiểm tra **những điều bị cấm**.

### 37.3. Quan sát và cảnh báo

- Tần suất unauthorized access attempts.
- Cross-tenant query anomalies.
- DB constraint violations bất thường.
- Query timeout/large export.
- Membership/role changes.
- RLS policy errors.
- Các hành động quyền cao.
- Data export volume.

Telemetry cần tránh biến thành nguồn rò rỉ PII.

## 38. Bảng chọn lớp bảo vệ đúng

| Quy tắc | Nên kiểm tra sớm ở đâu? | Cần cưỡng chế cuối ở đâu? |
| --- | --- | --- |
| Caller được xác thực | Security filter/gateway | Không chỉ dựa vào DB row constraint |
| Actor được đọc Order | Resource authorization/query scoping | DB RLS nếu có |
| Actor được approve Order | Application policy/domain workflow | Có thể cần DB role/stored procedure theo threat model |
| Tenant trong request đáng tin | Security context resolution | RLS/composite FK khi phù hợp |
| Reference không trống | DTO + domain/Bean Validation | NOT NULL; CHECK bổ sung nếu cần |
| Reference duy nhất theo tenant | Domain check để báo lỗi sớm | UNIQUE(tenant_id, reference) |
| Customer cùng tenant | Service/domain | Composite FK |
| Quantity > 0 | DTO + entity constructor | CHECK(quantity > 0) |
| Không vượt tồn kho | Service transactional command | Atomic update/locking/protocol |
| Version chưa stale | Service/current state | @Version + provider/DB update condition |
| Dữ liệu bị xóa phải ẩn | Repository/API policy | RLS/view/retention policy tùy yêu cầu |
| Không ai được sửa bảng schema | Deployment controls | DB GRANT/REVOKE |
| API không lộ PII | Response projection/redaction | Column/row privilege, encryption tùy trường hợp |

Câu hỏi không phải “chỉ chọn một trong hai”, mà là **có thể và cần bảo vệ bằng nhiều cơ chế bổ sung hay không**.

## 39. Những lỗi thiết kế thường gặp

### Lỗi 1 — Coi authentication là authorization

Token hợp lệ không cấp quyền với mọi Order ID.

### Lỗi 2 — Dùng tenantId từ request body làm nguồn sự thật

Client có thể tự đổi tenant target.

### Lỗi 3 — Chỉ thêm @Valid rồi tin dữ liệu đã an toàn

Bean Validation không tự xác thực caller, resolve tenant permission hoặc chống race.

### Lỗi 4 — Coi @Column(unique=true) là DB constraint đã triển khai

Migration có thể chưa tạo unique index/constraint thực tế.

### Lỗi 5 — Chỉ SELECT xem reference tồn tại rồi INSERT

Hai transactions vẫn có thể cùng thấy chưa tồn tại.

### Lỗi 6 — Chỉ dùng FK(customer_id) trong shared-schema multi-tenancy

Không ngăn Order tenant-A tham chiếu Customer tenant-B.

### Lỗi 7 — Coi FK là kiểm tra user permission

FK chỉ quan tâm quan hệ lưu trữ, không biết actor có quyền.

### Lỗi 8 — Deserialize JSON trực tiếp vào entity và merge

Dễ bị mass assignment và thay đổi collection/tenant/status ngoài ý muốn.

### Lỗi 9 — Controller kiểm tra quyền nhưng batch job không kiểm tra

Business operation bị bypass qua entrypoint khác.

### Lỗi 10 — Authorize parent nhưng không kiểm tra child membership

Client có thể gửi line ID thuộc Order khác.

### Lỗi 11 — Một endpoint lọc tenant nhưng COUNT/export không lọc

Có thể làm lộ số lượng/tổng giá trị hoặc dữ liệu raw.

### Lỗi 12 — Ghép chuỗi JPQL từ input không tin cậy

Có nguy cơ injection; dùng `setParameter` cho values.

### Lỗi 13 — Thử bind tên cột để làm dynamic sorting

Identifiers cần allowlist/Criteria, không phải query parameter value.

### Lỗi 14 — Đặt authorization duy nhất trong @PreUpdate

Bulk DML và external writers có thể bypass entity callbacks.

### Lỗi 15 — Cho rằng @Version bảo vệ thay đổi membership/role

Version của Order không tự giám sát bảng permission khác.

### Lỗi 16 — Gọi @Transactional rồi nghĩ mọi race đã biến mất

Isolation và locking semantics phải phù hợp invariant cụ thể.

### Lỗi 17 — RLS dùng session variable không reset trên pooled connections

Tenant context có thể leak qua các requests.

### Lỗi 18 — Có RLS nhưng app role được BYPASSRLS

Chính sách row access có thể bị vượt qua.

### Lỗi 19 — Set tenant context từ input chưa xác thực rồi tin RLS

RLS không thể tự xác minh tính đúng của nguồn setting.

### Lỗi 20 — Coi soft delete là xóa dữ liệu vĩnh viễn

Row còn ở database/backups và có thể được truy cập qua SQL khác.

### Lỗi 21 — Coi Base64 là encryption

Encoding không cung cấp confidentiality.

### Lỗi 22 — Mã hóa cột rồi tin UNIQUE trên ciphertext kiểm tra plaintext

Với encryption ngẫu nhiên, cùng plaintext có thể tạo ciphertext khác nhau.

### Lỗi 23 — Log SQL bind values chứa token/PII

Observability trở thành nguồn rò rỉ.

### Lỗi 24 — Trả raw SQL constraint exception cho client

Có thể tiết lộ cấu trúc DB hoặc dữ liệu nhạy cảm.

### Lỗi 25 — App runtime dùng quyền DBA

Một lỗi ứng dụng có thể tác động toàn schema.

### Lỗi 26 — Không test actual migration constraints

Java annotations trông đúng nhưng DB thật thiếu constraint.

### Lỗi 27 — Dùng cùng EntityManager để xác nhận DB round-trip

L1 cache có thể che lỗi đọc/ghi; cần xác minh trong transaction/EM mới.

### Lỗi 28 — Chỉ test happy path

Không phát hiện tenant escape, BOLA, duplicate race hoặc bulk bypass.

### Lỗi 29 — Cho rằng native SQL tự được tenant-filter

Trừ khi có chính sách/layer riêng, query phải có predicate hoặc RLS phù hợp.

### Lỗi 30 — Tối ưu hiệu năng bằng cách bỏ kiểm tra quyền

Một query nhanh hơn nhưng làm lộ dữ liệu là regression bảo mật nghiêm trọng.

## 40. Bài tập thực hành

### Bài 1 — Authentication hay authorization?

Alice có token hợp lệ và gọi GET Order của Bob.

**Đáp án:** Authentication pass nhưng object-level authorization phải từ chối nếu Alice không có quyền.

### Bài 2 — Bean Validation

Request có `customerId=202`, ID là Long dương nhưng Customer thuộc tenant-B.

**Đáp án:** DTO validation có thể pass; service phải kiểm tra tenant/ownership, composite FK có thể bảo vệ quan hệ lưu trữ.

### Bài 3 — DDL và @Column

Entity có `@Column(unique=true)` nhưng database chưa tạo unique constraint.

**Đáp án:** Chưa có bảo đảm uniqueness ở DB; cần migration và integration test.

### Bài 4 — Race duplicate

Hai requests đồng thời tạo cùng `(tenantId, reference)`.

**Đáp án:** UNIQUE(tenant_id, reference) cần cưỡng chế cuối; Java check không đủ.

### Bài 5 — NULL với CHECK

Database có `CHECK(total_amount >= 0)` nhưng cột cho phép null.

**Đáp án:** Cần `NOT NULL` nếu muốn cấm null; CHECK có thể cho UNKNOWN đi qua.

### Bài 6 — Cấu trúc Cross-tenant

Order có `tenantId=A` và `customerId` của B.

**Đáp án:** Domain check và composite FK bảo vệ; FK chỉ trên customer_id chưa đủ.

### Bài 7 — BOLA

Client thay `orderId` trong URL và API trả Order tenant khác.

**Đáp án:** Lỗi object-level authorization; thêm tenant/resource scoping và kiểm tra quyền phù hợp.

### Bài 8 — Child ID

URL là `/orders/100/lines/501`, nhưng Line#501 thuộc Order#200.

**Đáp án:** Phải kiểm tra parent-child membership trong query/service; không xóa theo line ID đơn độc.

### Bài 9 — Mass assignment

Payload gửi `tenantId`, `status` và `approvedByUserId` để cập nhật reference.

**Đáp án:** DTO chỉ nhận reference; không bind/merge arbitrary entity fields.

### Bài 10 — JPQL injection

Repository nối `reference` trực tiếp vào JPQL query.

**Đáp án:** Dùng `:reference` + `setParameter` để bind value.

### Bài 11 — Sort injection

Request gửi một chuỗi arbitrary làm tên cột ORDER BY.

**Đáp án:** Allowlist sort properties hoặc Criteria API; không concatenate raw identifier.

### Bài 12 — @Version

Membership của actor bị thu hồi, nhưng Order version không đổi.

**Đáp án:** @Version trên Order không tự phát hiện thay đổi quyền; cần policy/concurrency mechanism riêng.

### Bài 13 — Bulk update

Một JPQL bulk UPDATE sửa tất cả Orders và không chạy `@PreUpdate` của từng entity.

**Đáp án:** Đúng theo bulk DML semantics; kiểm tra authorization/domain policy trước lệnh và giữ DB constraints.

### Bài 14 — RLS

PostgreSQL có policy theo `app.tenant_id` nhưng app set giá trị đó trực tiếp từ JSON body.

**Đáp án:** Không an toàn. Context phải từ trusted identity; RLS không tự xác thực claim.

### Bài 15 — Connection pooling

Một connection giữ `tenant-A` session variable khi được trả về pool.

**Đáp án:** Rủi ro cross-tenant leak; dùng transaction-local scope hoặc reset chắc chắn và test reuse.

### Bài 16 — RLS vs FK

Có RLS trên Orders nhưng Order vẫn tham chiếu Customer tenant khác.

**Đáp án:** RLS không mặc nhiên bảo vệ relational invariant; cần composite FK và domain checks.

### Bài 17 — Audit

Controller log “approve started” nhưng transaction rollback.

**Đáp án:** Log request không phải bằng chứng durable approval; cần audit transaction/commit semantics phù hợp.

### Bài 18 — Soft delete

User yêu cầu xóa dữ liệu cá nhân, hệ thống chỉ set `deleted=true`.

**Đáp án:** Chưa chứng minh physical deletion/retention compliance; cần policy cụ thể.

### Bài 19 — Encryption

Email mã hóa ngẫu nhiên rồi đặt UNIQUE trên ciphertext.

**Đáp án:** Không tự bảo đảm uniqueness theo plaintext; cần phương án index riêng có kiểm soát nếu nghiệp vụ yêu cầu.

### Bài 20 — Least privilege

Application runtime cần ghi Orders nhưng đang giữ quyền DROP TABLE.

**Đáp án:** Thu hẹp DB role, tách migration identity khỏi runtime identity.

## 41. Câu hỏi tự kiểm tra

**1. Bảo vệ biên ứng dụng chịu trách nhiệm gì?**

Authentication, authorization, input handling, query scoping, field allowlisting và response safety.

**2. Database constraint chịu trách nhiệm gì?**

Cưỡng chế các ràng buộc dữ liệu có thể biểu đạt ở mức lưu trữ và transaction.

**3. Authentication có tự cấp quyền trên entity ID không?**

Không.

**4. DTO @Valid có kiểm tra Customer thuộc tenant nào không?**

Không tự động; cần logic/dữ liệu tương ứng.

**5. FK có tự kiểm tra role của người dùng không?**

Không.

**6. @Column(nullable=false) có tự đổi schema production không?**

Không, cần DDL/migration tương ứng.

**7. Vì sao DB UNIQUE quan trọng dưới concurrency?**

Vì check-before-insert có thể race.

**8. Composite FK giúp gì trong shared-schema multi-tenancy?**

Ngăn tham chiếu sang parent thuộc tenant khác khi thiết kế key đúng.

**9. Vì sao không tin tenantId trong JSON?**

Client có thể tự thay đổi target tenant.

**10. BOLA/IDOR là gì?**

Truy cập object bằng ID mà thiếu kiểm tra quyền trên object cụ thể.

**11. Mass assignment là gì?**

Client tác động fields nội bộ không được phép qua binding/copy/merge quá rộng.

**12. Vì sao DTO command có lợi?**

Chỉ cho phép những fields và hành động đã xác định.

**13. Parameter binding bảo vệ điều gì?**

Ngăn giá trị untrusted thay đổi cú pháp/ý nghĩa query structure.

**14. Có bind được tên cột ORDER BY như value không?**

Không; dùng allowlist/Criteria.

**15. Domain method submit() làm gì?**

Bảo vệ business transition và aggregate invariants.

**16. Domain method có biết caller được quyền không?**

Không tự động, trừ khi domain được cung cấp ngữ cảnh và policy phù hợp.

**17. @Version bảo vệ điều gì?**

Stale managed entity updates theo optimistic locking semantics.

**18. @Version trên Order có kiểm tra membership table không?**

Không.

**19. Bulk JPQL UPDATE có gọi @PreUpdate từng entity không?**

Không theo lifecycle entity-level thông thường.

**20. DB constraints có còn hiệu lực với native SQL không?**

Có, nếu đã được tạo và áp dụng cho DML tương ứng.

**21. RLS có thuộc Jakarta Persistence chuẩn không?**

Không; đó là tính năng DBMS-specific.

**22. USING và WITH CHECK trong PostgreSQL RLS khác nhau thế nào?**

Một bên giới hạn rows được truy cập/thao tác, bên kia kiểm tra rows mới/sau update theo policy.

**23. Vì sao setting tenant trên pooled connection phải cẩn thận?**

Context có thể rò sang request tenant khác nếu không scope/reset đúng.

**24. RLS có tự xác thực JWT của caller không?**

Không.

**25. Có RLS thì không cần application authorization nữa?**

Không. RLS là lớp bổ sung; quyền nghiệp vụ và trusted context vẫn cần.

**26. Least privilege nghĩa là gì?**

Chỉ cấp quyền DB cần thiết cho từng principal/use case.

**27. Runtime app có nên có quyền DBA không?**

Thông thường không.

**28. Soft delete có xóa row khỏi backup không?**

Không.

**29. Encryption có thay authorization không?**

Không.

**30. Base64 có phải encryption không?**

Không.

**31. Cần bảo vệ những API nào ngoài GET by ID?**

List, search, COUNT, aggregate, export, child endpoints, bulk mutations và jobs.

**32. Vì sao test với database thật?**

Để xác minh constraints, transactions và DB-specific features thực sự được áp dụng.

**33. Test RLS cần kiểm tra gì về connection pool?**

Tenant context không leak khi physical connection được tái sử dụng.

**34. Một SQL nhanh nhưng thiếu tenant predicate có được gọi là tối ưu tốt không?**

Không; nó làm suy giảm confidentiality.

**35. Quy tắc cốt lõi cần nhớ là gì?**

Bảo vệ danh tính và quyền ở biên, giữ invariants ở domain, cưỡng chế data constraints tại database và kiểm thử mọi đường truy cập/ghi.

## 42. Kịch bản tổng hợp: tạo và submit Order an toàn

Một yêu cầu nghiệp vụ:

> Alice thuộc tenant-A tạo Order tham chiếu Customer#101, sau đó submit. Mã Order phải duy nhất trong tenant, Customer phải cùng tenant, Order phải có ít nhất một dòng và chỉ Alice hoặc người có quyền được phép submit.

### 42.1. Luồng tạo Order

```text
POST /api/orders
      |
      v
Verify authentication token
      |
      v
Derive trusted tenant and actor
      |
      v
Validate CreateOrderRequest fields
      |
      v
BEGIN TRANSACTION
      |
      v
Find Customer with tenant scope
      |
      v
Verify Customer eligibility
      |
      v
Construct PurchaseOrder via factory
      |
      v
Add lines via domain methods
      |
      v
Check domain invariants
      |
      v
EntityManager.persist()
      |
      v
FLUSH / COMMIT
      |
      +-- FK / composite FK
      +-- UNIQUE tenant+reference
      +-- CHECK / NOT NULL
      +-- RLS if active
      |
      v
Return resource identity
```

### 42.2. Luồng submit

```text
POST /api/orders/{id}/submit
      |
      v
Authenticate actor
      |
      v
BEGIN TRANSACTION
      |
      v
Load Order with tenant scope
      |
      v
Authorize ORDER_SUBMIT on this Order
      |
      v
Check current state/version
      |
      v
order.submit()
      |
      v
Dirty checking / optimistic update
      |
      v
DB constraints + transaction commit
      |
      v
Return success
```

### 42.3. Một tập hậu điều kiện

Sau commit thành công:

- Order thuộc tenant-A.
- Customer reference đúng tenant theo DB.
- Reference không trùng trong tenant-A.
- Business state là trạng thái được phép.
- Actor đã được authorization policy chấp nhận.
- Không có partial insert nếu transaction rollback.
- Nếu hai requests cạnh tranh, DB constraints/version mechanism bảo vệ invariant tương ứng.
- Query/read response không tiết lộ dữ liệu của tenant khác.

### 42.4. Các negative tests bắt buộc

- Alice gửi Customer ID thuộc tenant-B.
- Alice gửi tenantId=B trong JSON.
- Alice dùng Order ID của tenant-B.
- Alice gửi `status=APPROVED` vào create payload.
- Hai requests trùng reference cùng lúc.
- Một reader dùng JPQL query thiếu tenant predicate.
- Một native SQL path bypasses entity listeners.
- RLS transaction thiếu setting.
- Reuse connection pool giữa tenant-A và tenant-B.
- Một Order có child line trỏ parent khác.
- Một transaction sửa stale version.
- Một export query quên tenant filter.

### 42.5. Không có một annotation giải quyết hết

`@NotNull`, `@Valid`, `@Version` và `@JoinColumn` rất có ích trong hệ thống JPA. Nhưng tổng thể an toàn đến từ:

```text
Trusted Identity
    + Authorization
    + Controlled Commands
    + Domain Invariants
    + Scoped Queries
    + Transactions/Locking
    + Database Constraints
    + Optional DB Access Policies
    + Tests and Observability
```

## 43. Kết luận

**Bảo vệ biên ứng dụng** và **ràng buộc dữ liệu thực tế** là hai lớp khác nhau của cùng một chiến lược bảo mật và toàn vẹn dữ liệu.

Những nguyên tắc quan trọng nhất:

1. **Xác thực không đồng nghĩa phân quyền.** Luôn kiểm tra quyền trên resource cụ thể, không chỉ token/role chung.
2. **Tenant phải đến từ nguồn đáng tin**, không mặc nhiên từ request body.
3. **Dùng DTO/commands giới hạn fields được sửa**, tránh deserialize và merge toàn bộ entity graph không tin cậy.
4. **Giữ business invariants trong domain/application services**, để controller và background jobs dùng cùng quy tắc.
5. **Phân biệt Bean Validation với database constraints.** `@NotNull`, `@Valid` và `@Column` không tự là proof rằng DB production đã có FK/UNIQUE/CHECK phù hợp.
6. **Tạo FK, UNIQUE, CHECK và NOT NULL thực sự trong migrations**. Đặc biệt unique constraints cần thiết khi nhiều transactions cùng ghi.
7. **Thiết kế composite FK/unique theo tenant** khi cần ngăn tham chiếu hoặc trùng mã vượt ranh giới tenant.
8. **Parameterize query values và allowlist identifiers**, bảo vệ cả JPQL lẫn native SQL.
9. **Không đặt authorization chỉ trong JPA callbacks**, vì bulk DML, native SQL và external writers có thể đi đường khác.
10. **Dùng @Version/atomic updates/locking đúng invariant**, không cho rằng một lần SELECT kiểm tra trước có giá trị vĩnh viễn.
11. **RLS, database grants và least privilege là phòng thủ bổ sung**, không thay trusted identity hoặc authorization nghiệp vụ.
12. **Cẩn thận với RLS tenant context và connection pooling**; context sai có thể tạo cross-tenant leak.
13. **Không coi soft delete, encryption hoặc audit log là giải pháp tự đủ** cho retention, confidentiality hay authorization.
14. **Kiểm thử cả đường hợp lệ và đường bị cấm**, bao gồm concurrency, bulk SQL, database constraints, tenant isolation và nhiều entrypoints.
15. **Bảo vệ tính đúng đắn khi tối ưu hiệu năng**: bỏ kiểm tra quyền hoặc predicate tenant để giảm query không phải cải tiến.

Mục tiêu cuối cùng là xây dựng một hệ thống mà **người dùng chỉ thực hiện được những hành động được phép, object graph luôn tuân thủ các quy tắc nghiệp vụ, và database không thể lưu các trạng thái vi phạm những bất biến đã được chuyển thành ràng buộc thực tế**.

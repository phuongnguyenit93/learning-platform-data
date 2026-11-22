# Dùng DTO cho dữ liệu nhận vào và dữ liệu trả ra

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Nhóm kiến thức:** Bảo mật dữ liệu

Một entity JPA được thiết kế để mô tả và quản lý dữ liệu được lưu trữ, còn dữ liệu mà ứng dụng **cho phép client gửi vào hoặc nhận về** là một hợp đồng hoàn toàn khác. Nếu API nhận thẳng entity hoặc serialize entity làm response, các thuộc tính nội bộ như **ownerId**, **role**, **passwordHash**, **internalCost**, **deleted**, **version**, **audit metadata** và các quan hệ lazy có thể vô tình trở thành một phần của API công khai. Đây là nguồn gốc của nhiều lỗi bảo mật: **mass assignment/overposting**, rò rỉ dữ liệu cá nhân, lộ internal identifiers, thay đổi field mà người dùng không có quyền, serialize graph quá rộng và truy vấn ngoài ý muốn.

**Data Transfer Object (DTO)** là một cấu trúc dữ liệu dành riêng cho một ranh giới giao tiếp. Trong một ứng dụng JPA, thông thường nên dùng ít nhất hai nhóm DTO:

- **Input DTO:** chỉ nhận những field mà caller được phép cung cấp cho một use case cụ thể, ví dụ CreateProductRequest và UpdateProductPriceRequest.
- **Output DTO:** chỉ xuất những field mà caller được phép nhìn thấy, ví dụ ProductPublicResponse và ProductAdminResponse.

Một API tạo sản phẩm nên nhận:

~~~json
{
  "name": "Bàn phím cơ",
  "sku": "KB-001",
  "price": 1290000.00
}
~~~

chứ không nhận toàn bộ object lưu trữ:

~~~json
{
  "id": 9001,
  "name": "Bàn phím cơ",
  "sku": "KB-001",
  "price": 1290000.00,
  "internalCost": 650000.00,
  "ownerTenantId": "another-tenant",
  "approved": true,
  "deleted": false,
  "createdBy": "administrator",
  "version": 43
}
~~~

Ngay cả khi client cố gửi những field nhạy cảm này, API không được biến chúng thành quyền ghi entity một cách tự động. Một thiết kế tốt sử dụng **DTO allowlist + domain methods + authorization + database constraints** ở những tầng tương ứng.

Bài học này trình bày **vì sao không để JPA entity là API contract**, cách thiết kế và ánh xạ input/output DTO, kiểm tra dữ liệu, phòng overposting và lộ dữ liệu, xử lý quan hệ lazy/projection, multi-tenancy, partial update, concurrency, mapping tools, hiệu năng, testing và những sai lầm thường gặp.

## 1. Đặt đúng vai trò: Entity, DTO và Domain

### 1.1. Entity JPA phục vụ persistence

Entity có thể chứa:
- Mapping bảng/cột bằng @Entity, @Table, @Column;
- @Id, @GeneratedValue và @Version;
- Các quan hệ @ManyToOne, @OneToMany, @ManyToMany;
- Lazy proxy và collections;
- Các field kỹ thuật: deletedAt, createdBy, internalStatus;
- Invariants và domain methods;
- Metadata liên quan audit, indexing hoặc schema.

Những đặc điểm này có giá trị trong persistence layer nhưng **không có nghĩa client cần thấy hoặc có quyền sửa chúng**.

### 1.2. DTO phục vụ use case và contract

Ví dụ các DTO khác nhau cho một entity Product:

~~~text
                   Product entity
                  /      |       \
                 /       |        \
                v        v         v
    CreateProductRequest  UpdatePriceRequest  ProductPublicResponse
       client → API          client → API          API → client

                                              ProductAdminResponse
                                                  API → admin
~~~

Dù cùng truy cập Product, mỗi DTO có scope riêng. Tên field, kiểu dữ liệu, validation và mức chi tiết có thể khác theo quyền và use case.

### 1.3. DTO không nhất thiết là một class mutable

Với Java 17+, có thể dùng record:

~~~java
public record CreateProductRequest(
    String name,
    String sku,
    BigDecimal price
) {}
~~~

Với frameworks có khả năng binding records, record gọn và giúp DTO có state bất biến ở mức reference. Tuy nhiên:
- Record không tự bảo đảm dữ liệu hợp lệ;
- Nested objects/collections vẫn có thể mutable;
- Record không tự authorize caller;
- Không dùng record làm nơi chứa passwords/plain secrets vô thời hạn chỉ vì immutable.

Với các phiên bản Java/framework cũ, DTO có thể là class với fields/getters/setters/constructors.

### 1.4. Tại sao entity và DTO thay đổi theo nhịp khác nhau?

Schema thêm field **internalRiskScore** không có nghĩa API công khai nên thêm field đó. Ngược lại API đổi tên trường **displayPrice** có thể chỉ là thay đổi presentation, không cần rename database column **price**.

Tách entity và DTO giúp:
- Tránh leak field mới mặc nhiên;
- Version API độc lập schema;
- Củng cố quyền đọc/ghi theo use case;
- Giảm việc serialize lazy relations;
- Dễ viết validation/error contracts;
- Dễ tối ưu query projections;
- Dễ review bảo mật khi thêm fields.

### 1.5. DTO không phải một phép mã hóa dữ liệu

DTO là **định nghĩa rõ dữ liệu đi qua boundary**, không tự mã hóa, băm, che giấu hay phân quyền. Nếu DTO chứa passwordHash hoặc dữ liệu người khác, việc dùng record không ngăn rò rỉ. Bảo mật đến từ **việc chọn đúng fields, xác thực quyền, kiểm tra context và không tiết lộ thông tin ngoài phạm vi**.

## 2. Mô hình ví dụ: Product trong một hệ thống nhiều tenant

Để minh họa, dùng một hệ thống catalog có dữ liệu khách hàng, giá bán công khai và một số thông tin chỉ dành cho nhân viên quản lý.

### 2.1. Entity Product

~~~java
package com.example.catalog.persistence;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

@Entity
@Table(
    name = "products",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_products_tenant_sku",
        columnNames = {"tenant_id", "sku"}
    )
)
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE)
    private Long id;

    @Version
    private Long version;

    @Column(name = "tenant_id", nullable = false, updatable = false)
    private String tenantId;

    @Column(nullable = false, length = 200)
    private String name;

    @Column(nullable = false, length = 64)
    private String sku;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal sellingPrice;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal internalCost;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 24)
    private ProductStatus status;

    @Column(nullable = false)
    private boolean deleted;

    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    @Column(nullable = false)
    private Instant updatedAt;

    protected Product() {}

    public Product(
            String tenantId,
            String name,
            String sku,
            BigDecimal sellingPrice,
            BigDecimal internalCost,
            Instant now) {

        this.tenantId = Objects.requireNonNull(tenantId);
        this.name = requireText(name, "name");
        this.sku = requireText(sku, "sku");
        changeSellingPrice(sellingPrice);
        this.internalCost = requireNonnegative(
            internalCost, "internalCost"
        );
        this.status = ProductStatus.DRAFT;
        this.deleted = false;
        this.createdAt = Objects.requireNonNull(now);
        this.updatedAt = now;
    }

    private static String requireText(
            String value, String field) {

        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field);
        }
        return value.trim();
    }

    private static BigDecimal requireNonnegative(
            BigDecimal value, String field) {

        if (value == null || value.signum() < 0) {
            throw new IllegalArgumentException(field);
        }
        return value;
    }

    public void rename(String nextName, Instant now) {
        this.name = requireText(nextName, "name");
        this.updatedAt = now;
    }

    public void changeSellingPrice(
            BigDecimal nextPrice) {
        this.sellingPrice = requireNonnegative(
            nextPrice, "sellingPrice"
        );
    }

    public void activate(Instant now) {
        if (sellingPrice.signum() <= 0) {
            throw new IllegalStateException(
                "Sản phẩm cần giá dương để kích hoạt"
            );
        }
        this.status = ProductStatus.ACTIVE;
        this.updatedAt = now;
    }

    public Long getId() { return id; }
    public Long getVersion() { return version; }
    public String getTenantId() { return tenantId; }
    public String getName() { return name; }
    public String getSku() { return sku; }
    public BigDecimal getSellingPrice() { return sellingPrice; }
    public BigDecimal getInternalCost() { return internalCost; }
    public ProductStatus getStatus() { return status; }
    public boolean isDeleted() { return deleted; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
}
~~~

Enum:

~~~java
public enum ProductStatus {
    DRAFT,
    ACTIVE,
    ARCHIVED
}
~~~

Đây là entity minh họa. Trong hệ thống thực tế, cần hoàn thiện transaction policy, audit handling, precision/scale, unique constraints, domain lifecycle và schema migration. Điểm bảo mật là **tenantId**, **internalCost**, **deleted**, **version** và các thông tin trạng thái nội bộ không phải tất cả đều thuộc API public.

### 2.2. Database constraints vẫn cần

Ví dụ DDL PostgreSQL về mặt ý tưởng:

~~~sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    name VARCHAR(200) NOT NULL,
    sku VARCHAR(64) NOT NULL,
    selling_price NUMERIC(19,2) NOT NULL,
    internal_cost NUMERIC(19,2) NOT NULL,
    status VARCHAR(24) NOT NULL,
    deleted BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,

    CONSTRAINT uk_products_tenant_sku
        UNIQUE (tenant_id, sku),

    CONSTRAINT ck_products_selling_price
        CHECK (selling_price >= 0),

    CONSTRAINT ck_products_internal_cost
        CHECK (internal_cost >= 0)
);
~~~

SQL column names trong ví dụ phải khớp effective JPA naming strategy hoặc @Column mappings; DDL cần migrations thực tế và các yêu cầu phiên bản DB/provider.

**DTO validation không thay database NOT NULL/CHECK/UNIQUE/FK**, đặc biệt khi có SQL jobs hoặc writers ngoài JPA.

### 2.3. Các lớp DTO cần thiết

Có thể tách:
- **CreateProductRequest:** name, sku, sellingPrice.
- **UpdateProductPriceRequest:** sellingPrice.
- **ProductPublicResponse:** id, name, sku, sellingPrice.
- **ProductManagementResponse:** id, name, sku, sellingPrice, status, updatedAt, version.
- **ProductCostResponse:** internalCost, chỉ có ở use case dành cho role được phép.

Không cần một DTO “FullProductDto” chung chứa tất cả fields rồi hy vọng mỗi controller tự nhớ ẩn những gì không nên hiện.

## 3. Mối đe dọa lớn nhất khi nhận entity: mass assignment/overposting

**Mass assignment** xảy ra khi application tự động bind nhiều fields từ input bên ngoài lên object lưu trữ mà không kiểm soát allowlist. Trong nhiều trường hợp đây là nguyên nhân dẫn đến **Broken Object Property Level Authorization**.

### 3.1. API nhận thẳng entity

Một controller nguy hiểm:

~~~java
@PostMapping("/products")
public Product create(@RequestBody Product product) {
    return repository.save(product);
}
~~~

Client có thể thử gửi:

~~~json
{
  "name": "Bàn phím",
  "sku": "KB-001",
  "sellingPrice": 1000,
  "internalCost": 0,
  "tenantId": "tenant-victim",
  "status": "ACTIVE",
  "deleted": false,
  "version": 0
}
~~~

Ngay cả khi một số fields bị JPA đánh dấu insertable=false/updatable=false, vẫn **không được coi đó là lớp authorization**. Binding object, domain callbacks, cascade và đường ghi khác vẫn có thể gây side effects hoặc thay đổi state không mong muốn.

### 3.2. @Column(updatable=false) không thay input DTO

~~~java
@Column(updatable = false)
private String tenantId;
~~~

Cấu hình này nói về việc provider có đưa cột vào SQL UPDATE hay không; nó không:
- Xác thực tenant từ user;
- Chặn client set field trong Java object;
- Bảo vệ INSERT nếu insertable vẫn true;
- Ngăn endpoint khác xử lý field sai;
- Kiểm tra caller có quyền sửa Product hay không.

**Authorization phải là quyết định nghiệp vụ/server-side**, không giao cho một cờ persistence mapping.

### 3.3. Cách an toàn: DTO allowlist

~~~java
public record CreateProductRequest(
    String name,
    String sku,
    BigDecimal sellingPrice
) {}
~~~

Chỉ ba fields được mô tả cho create use case. **tenantId** được lấy từ authenticated context, **internalCost** từ một workflow quản lý riêng hoặc policy, **status** do domain quyết định và **version** do JPA quản lý.

### 3.4. Không dùng BeanUtils.copyProperties một cách rộng

Nguy hiểm:

~~~java
BeanUtils.copyProperties(request, managedProduct);
~~~

nếu request DTO chung chứa nhiều fields và tool copy theo property name. Trong code khác, một mapper tự động có thể copy **ownerId**, **approved**, **deleted** hoặc associations nếu mapping rules không được kiểm soát.

Ngay cả khi request hiện không có field nhạy cảm, việc **thêm property mới sau này** có thể vô tình thay đổi behavior của một “copy all” mapper.

### 3.5. Allowlist thay vì denylist

Denylist: “Copy tất cả trừ passwordHash, tenantId, internalCost”. Khi entity thêm field mới **bankAccount**, developer có thể quên bổ sung denylist.

Allowlist: “Create chỉ dùng name, sku, sellingPrice”. Field mới mặc định **không đi qua API**, cho đến khi có quyết định thiết kế và review.

### 3.6. Không thể chỉ bỏ field khỏi HTML form

Nếu frontend không hiển thị status hoặc ownerTenantId, client vẫn có thể tự gửi JSON tùy ý. Server phải xác định **allowed fields** độc lập UI.

### 3.7. Không suy quyền từ client-supplied role

Không nên nhận:

~~~json
{
  "requestedRole": "ADMIN",
  "tenantId": "tenant-victim"
}
~~~

rồi dùng hai fields đó như thông tin ủy quyền. Role/tenant hiệu lực phải đến từ authentication/authorization context được server tin cậy và kiểm tra theo chính sách.

## 4. Lộ dữ liệu khi trả JPA entity trực tiếp

### 4.1. Response trả entity có thể thêm fields theo thời gian

~~~java
@GetMapping("/products/{id}")
public Product get(@PathVariable Long id) {
    return repository.findById(id).orElseThrow();
}
~~~

Ban đầu Product chỉ có id/name/price. Sau sáu tháng, entity thêm:
- internalCost;
- vendorDiscount;
- supplierAccount;
- auditInternalNote.

Nếu serializer tự nhận các getters mới, **response có thể bị mở rộng ngoài ý muốn** mà không ai sửa controller. Đây là rủi ro data exposure.

### 4.2. @JsonIgnore chỉ là mitigation ở serialization layer

Có thể gắn:

~~~java
@JsonIgnore
private BigDecimal internalCost;
~~~

nhưng điều đó:
- Gắn entity vào một serializer;
- Không định nghĩa nhiều view rõ ràng (public/admin/internal);
- Có thể tạo khác biệt giữa JSON serializer và event serialization khác;
- Không bảo vệ input binding nếu không có policy riêng;
- Dễ bị ảnh hưởng bởi refactor/annotations/mixins.

**DTO response explicit** thường là ranh giới dễ review hơn.

### 4.3. Serialization có thể kích hoạt truy vấn lazy

Nếu Product có Category và OrderLines lazy, serializer duyệt getters có thể:
- Phát thêm SQL không dự đoán;
- Gây N+1;
- Truy cập collections chứa dữ liệu nhạy cảm;
- Ném LazyInitializationException sau transaction;
- Tạo vòng tham chiếu vô hạn trong quan hệ hai chiều.

DTO mapping/projection chọn chính xác những fields cần trả và tải dữ liệu trước lúc response.

### 4.4. “Đã load entity” không đồng nghĩa “được phép trả tất cả”

Repository có quyền đọc row để áp business logic, nhưng người dùng API có thể chỉ được xem một vài fields. Phải áp **property-level visibility policy**; DTO giúp giới hạn projection, còn authorization bảo đảm caller được truy cập row/operation.

### 4.5. Một ví dụ về các response scopes

Public:

~~~json
{
  "id": 42,
  "name": "Bàn phím",
  "sku": "KB-001",
  "sellingPrice": 1290000.00
}
~~~

Management:

~~~json
{
  "id": 42,
  "name": "Bàn phím",
  "sku": "KB-001",
  "sellingPrice": 1290000.00,
  "status": "DRAFT",
  "version": 4,
  "updatedAt": "2026-11-15T03:00:00Z"
}
~~~

Cost review (chỉ khi được phép):

~~~json
{
  "id": 42,
  "internalCost": 650000.00,
  "currency": "VND"
}
~~~

Các DTO trên thể hiện ba hợp đồng khác nhau. Một token chỉ được phép xem giá bán không tự được quyền xem internalCost vì cùng một Product ID.

## 5. Thiết kế Input DTO theo từng hành động

Không nên dùng một request DTO duy nhất cho tất cả thao tác tạo, đổi giá, đổi trạng thái, xóa và xem Product. Mỗi use case có **quyền ghi, validation và workflow khác nhau**.

### 5.1. CreateProductRequest

~~~java
package com.example.catalog.api.dto;

import jakarta.validation.constraints.*;
import java.math.BigDecimal;

public record CreateProductRequest(

    @NotBlank
    @Size(max = 200)
    String name,

    @NotBlank
    @Pattern(regexp = "[A-Z0-9-]{3,64}")
    String sku,

    @NotNull
    @PositiveOrZero
    @Digits(integer = 17, fraction = 2)
    BigDecimal sellingPrice
) {}
~~~

Ý nghĩa:
- Client chỉ gửi được name, sku, sellingPrice theo contract DTO.
- Không nhận **id**, **tenantId**, **internalCost**, **status**, **deleted**, **version**.
- @PositiveOrZero không tự cấm null, vì vậy cần @NotNull khi giá bắt buộc.
- @NotBlank cấm null, chuỗi rỗng và toàn khoảng trắng.
- @Digits giúp kiểm soát phần thập phân nhưng cần đồng bộ database precision/scale và chính sách làm tròn tiền.

Validation phải phản ánh yêu cầu thật; ví dụ price bằng 0 có thể chỉ hợp lệ ở trạng thái DRAFT, trong khi ACTIVE đòi giá dương.

### 5.2. UpdateProductPriceRequest

~~~java
public record UpdateProductPriceRequest(
    @NotNull
    @PositiveOrZero
    @Digits(integer = 17, fraction = 2)
    BigDecimal sellingPrice
) {}
~~~

DTO không chứa name, sku, internalCost hoặc status. Một endpoint chỉ dùng DTO này sẽ có đường ghi hẹp: **đổi giá bán**.

### 5.3. RenameProductRequest

~~~java
public record RenameProductRequest(
    @NotBlank
    @Size(max = 200)
    String name
) {}
~~~

Tách DTO theo command giúp audit rõ, giảm vô tình reset giá và đơn giản hóa permission checks.

### 5.4. Activation là hành động, không phải chỉnh một enum tùy ý

Có thể thiết kế:

~~~text
POST /products/{id}/activate
~~~

Client yêu cầu activate, còn server kiểm tra:
1. Caller được quyền activate;
2. Product thuộc tenant được phép;
3. Trạng thái hiện tại phù hợp;
4. Giá hiện tại dương;
5. Workflow phê duyệt nếu có.

Sau đó service gọi domain method **product.activate(now)**. Không cần nhận raw status="ACTIVE" rồi copy thẳng vào entity.

### 5.5. Field ID tham chiếu cũng cần authorization

Một field hợp lệ theo cấu trúc:

~~~json
{
  "categoryId": 500
}
~~~

có thể vẫn trái quyền nếu Category#500 thuộc tenant khác. @NotNull/@Positive không xác nhận Category có thuộc tenant của caller hay không. Application service phải load/reference Category theo đúng tenant và visibility policy.

### 5.6. DTO riêng cho internal jobs

Một hệ thống có thể dùng:
- CreateProductRequest cho public API;
- ImportProductCommand cho ETL;
- AdminCorrectProductRequest cho quản trị.

Internal jobs cũng phải validate dữ liệu và authorization/scope khi phù hợp; “internal” không có nghĩa mọi payload đều đáng tin.

## 6. Thiết kế Output DTO theo đối tượng nhận

### 6.1. Public response

~~~java
package com.example.catalog.api.dto;

import java.math.BigDecimal;

public record ProductPublicResponse(
    Long id,
    String name,
    String sku,
    BigDecimal sellingPrice
) {}
~~~

DTO không chứa internalCost, tenantId, deleted hoặc version.

### 6.2. Management response

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record ProductManagementResponse(
    Long id,
    String name,
    String sku,
    BigDecimal sellingPrice,
    String status,
    Long version,
    Instant updatedAt
) {}
~~~

ManagementResponse chỉ được trả sau kiểm tra quyền quản lý. Version có thể hỗ trợ optimistic concurrency contract, nhưng client không được tùy ý ghi đè field version của JPA.

### 6.3. Response giá vốn

~~~java
public record ProductCostResponse(
    Long id,
    BigDecimal internalCost
) {}
~~~

Endpoint này cần permission riêng như PRODUCT_COST_READ. Không chỉ vì DTO tồn tại mà mọi caller đều được nhận giá vốn.

### 6.4. Nguyên tắc data minimization

Không đưa passwordHash, API key digest, reset token, refresh token, private keys hoặc dữ liệu cá nhân không liên quan vào DTO chỉ vì chúng có mặt trong entity. Admin cũng không cần mặc nhiên xem những dữ liệu có thể gây rủi ro.

### 6.5. Không phải cứ có DTO là đã an toàn

Nếu ProductPublicResponse được tạo từ Product của tenant khác thì vẫn là rò rỉ dữ liệu. Cần phối hợp:
- Authentication;
- Object-level authorization;
- Property-level authorization;
- Tenant/resource scoping;
- Explicit response mapping;
- Tests cho cả allowed/denied callers.

## 7. Mapping tường minh để giới hạn field

### 7.1. Entity → public response

~~~java
public final class ProductPublicMapper {

    private ProductPublicMapper() {}

    public static ProductPublicResponse toResponse(
            Product entity) {

        return new ProductPublicResponse(
            entity.getId(),
            entity.getName(),
            entity.getSku(),
            entity.getSellingPrice()
        );
    }
}
~~~

Đây là **allowlist explicit**. Nếu entity thêm getInternalCost(), response không tự xuất field mới.

### 7.2. Entity → management response

~~~java
public final class ProductManagementMapper {

    private ProductManagementMapper() {}

    public static ProductManagementResponse toResponse(
            Product entity) {

        return new ProductManagementResponse(
            entity.getId(),
            entity.getName(),
            entity.getSku(),
            entity.getSellingPrice(),
            entity.getStatus().name(),
            entity.getVersion(),
            entity.getUpdatedAt()
        );
    }
}
~~~

Mapper không phải authorization engine. Chỉ gọi mapper này ở use case đã được phép trả thông tin quản lý.

### 7.3. Input DTO → domain action

~~~java
public Product createProduct(
        CreateProductRequest request,
        String authorizedTenantId,
        BigDecimal trustedInternalCost,
        Instant now) {

    return new Product(
        authorizedTenantId,
        request.name(),
        request.sku(),
        request.sellingPrice(),
        trustedInternalCost,
        now
    );
}
~~~

TenantId lấy từ authenticated context đã kiểm chứng. InternalCost đến từ server-side policy/internal source được phép, không từ public JSON.

### 7.4. Update managed entity bằng domain method

~~~java
Product product = repository
    .findByIdAndTenantIdAndDeletedFalse(
        productId,
        authenticatedTenantId
    )
    .orElseThrow(ProductNotFoundException::new);

product.changeSellingPrice(
    request.sellingPrice()
);
~~~

Cách này thay đổi đúng một thuộc tính của **managed entity**. Không tạo detached Product có ID do client gửi rồi merge toàn bộ các fields chỉ để cập nhật một giá trị.

### 7.5. Version và concurrency contract

Một ứng dụng có thể đọc current version rồi kiểm tra expected version từ client:

~~~java
if (!Objects.equals(
        product.getVersion(),
        expectedVersion)) {

    throw new ProductVersionConflictException();
}
~~~

Kiểm tra sớm này **không thay** optimistic locking ở JPA flush/commit vì trạng thái có thể thay đổi đồng thời sau lúc check. Expected version là concurrency precondition, không phải quyền sửa JPA version column.

### 7.6. Tránh blanket property copying

~~~java
BeanUtils.copyProperties(request, managedProduct);
~~~

có thể làm các fields ngoài use case bị ghi nếu request class mở rộng về sau. Với MapStruct hoặc framework mapping khác, phải thiết kế allowlist/update method rõ; không dựa vào một exclude-list dễ quên khi thêm field mới.

## 8. Controller: nhận DTO, validate, gọi service, trả DTO

Ví dụ dùng Spring Boot 3, Spring Web và Jakarta Validation. Các class/service được giải thích tiếp theo; import tương ứng theo package thực tế.

### 8.1. POST và GET

~~~java
@RestController
@RequestMapping("/products")
public class ProductController {

    private final CreateProductService createService;
    private final ProductReader reader;

    public ProductController(
            CreateProductService createService,
            ProductReader reader) {
        this.createService = createService;
        this.reader = reader;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ProductPublicResponse create(
            @Valid @RequestBody CreateProductRequest request) {

        return createService.create(request);
    }

    @GetMapping("/{id}")
    public ProductPublicResponse get(
            @PathVariable Long id) {
        return reader.findPublicById(id);
    }
}
~~~

Hai nguyên tắc:
- Không nhận **@RequestBody Product entity**.
- Không trả trực tiếp **Product entity** từ controller.

### 8.2. @Valid thực hiện điều gì?

Khi Jakarta Bean Validation được tích hợp:
1. Spring bind JSON vào CreateProductRequest;
2. Chạy constraints của DTO;
3. Nếu vi phạm, xử lý request binding/validation error;
4. Nếu hợp lệ, gọi service.

Nhưng **@Valid không xác thực quyền tạo Product**, không tự chọn tenant và không ngăn race UNIQUE từ transaction khác. DTO và validation chỉ là hai lớp của một kiến trúc bảo mật.

### 8.3. Error response cũng không được lộ entity

Controller success path trả DTO nhưng exception handler lại serialize Throwable/SQL parameters vẫn có thể làm lộ dữ liệu. Error handler chỉ nên trả **mã lỗi, mô tả an toàn và correlation ID**, không serialize entity hoặc stack trace công khai.

### 8.4. API version có thể độc lập database schema

API v1 dùng sellingPrice, API v2 thêm currency hoặc priceBreakdown. Không cần đổi JPA entity property hoặc SQL column mỗi khi response representation thay đổi. Tách DTO giúp API contract thay đổi có chủ đích.

## 9. Application service: authorization trước khi query/ghi

DTO **không thay thế authorization**. Service phải kiểm tra caller, tenant, resource ownership và operation.

### 9.1. CreateProductService minh họa

~~~java
@Service
public class CreateProductService {

    private final ProductJpaRepository repository;
    private final TenantContext tenantContext;
    private final InternalCostPolicy costPolicy;
    private final Clock clock;

    public CreateProductService(
            ProductJpaRepository repository,
            TenantContext tenantContext,
            InternalCostPolicy costPolicy,
            Clock clock) {

        this.repository = repository;
        this.tenantContext = tenantContext;
        this.costPolicy = costPolicy;
        this.clock = clock;
    }

    @Transactional
    public ProductPublicResponse create(
            CreateProductRequest request) {

        String tenantId =
            tenantContext.requireAuthorizedTenant(
                "PRODUCT_CREATE"
            );

        BigDecimal trustedCost =
            costPolicy.initialCostForDraft(tenantId);

        Product product = new Product(
            tenantId,
            request.name(),
            request.sku(),
            request.sellingPrice(),
            trustedCost,
            clock.instant()
        );

        repository.save(product);

        return ProductPublicMapper.toResponse(product);
    }
}
~~~

**TenantContext**, **InternalCostPolicy** và repository là dependencies do ứng dụng định nghĩa; đoạn code minh họa ranh giới, không phải project compile-ready nếu thiếu implementations.

**Lưu ý transaction:** Với Spring @Transactional thông thường, commit xảy ra sau thân method. Nếu UNIQUE constraint fail tại commit, exception phải được xử lý ở outer boundary. Không coi việc method body return là bằng chứng commit thành công.

### 9.2. TenantContext phải đáng tin

Tenant context có thể lấy từ:
- Principal đã xác thực;
- Token claims sau kiểm tra chữ ký, issuer, audience và expiry;
- Session được kiểm chứng;
- Internal service identity đã authenticate.

**Không lấy raw tenantId từ JSON** làm cơ sở ghi vào tenant tùy ý.

### 9.3. Truy vấn có tenant scope

~~~java
public interface ProductJpaRepository
        extends JpaRepository<Product, Long> {

    Optional<Product> findByIdAndTenantIdAndDeletedFalse(
        Long id,
        String tenantId
    );
}
~~~

Một service đọc cần:
- Kiểm tra quyền PRODUCT_READ;
- Xác định tenant được phép;
- Query theo ID, tenantId và điều kiện deleted=false;
- Map sang public DTO;
- Trả not-found/forbidden theo security policy mà không lộ tenant khác.

Không gọi findById(id) rồi serialize object trước khi kiểm tra ownership.

### 9.4. Object-level authorization, IDOR và BOLA

Nếu Product#42 thuộc Tenant A và Product#43 thuộc Tenant B, user A chỉ thay URL từ 42 thành 43 không được nhận dữ liệu B. Đây là **Broken Object Level Authorization**, không chỉ là vấn đề serializer.

DTO giới hạn fields nhưng không chặn truy cập nhầm object. Query-scoping và authorization phải chặn truy cập sai ngay cả khi response chỉ có ID và name.

### 9.5. Property-level authorization

Một người có PRODUCT_READ có thể được xem sellingPrice nhưng không có PRODUCT_COST_READ. Người có PRODUCT_PRICE_UPDATE không tự được sửa internalCost hoặc status.

Thiết kế phối hợp:
- Endpoint có permission riêng;
- Request DTO chứa đúng writable fields;
- Output DTO chứa đúng readable fields;
- Service kiểm tra quyền theo resource;
- Positive và negative authorization tests.

### 9.6. Được xem object không đồng nghĩa được phép mọi thao tác

Một user được xem Product của tenant mình nhưng không có quyền xóa. **Row-level access** và **action-level permission** đều quan trọng.

### 9.7. Phân biệt 403 và 404

Khi đối tượng tồn tại nhưng caller không được phép xem, API có thể trả 403 hoặc 404 để tránh lộ sự tồn tại theo security policy. Không tiết lộ “sản phẩm 43 thuộc Tenant B” cho caller không có quyền biết.

## 10. Update DTO: chỉ sửa field được phép

### 10.1. Nhận entity trong PUT/PATCH là rủi ro

Nguy hiểm:

~~~java
@PutMapping("/{id}")
public Product update(
        @PathVariable Long id,
        @RequestBody Product input) {

    input.setId(id);
    return repository.save(input);
}
~~~

Rủi ro:
- Client kiểm soát fields không được phép;
- Fields không được gửi có thể thành null/default;
- Merge detached entity có thể ghi đè state;
- Tenant/owner/status có thể bị thao túng;
- Associations có thể bị thay qua nested objects;
- Optimistic locking bị xử lý sai.

### 10.2. Update một field trong transaction

~~~java
@Transactional
public ProductPublicResponse updatePrice(
        long productId,
        UpdateProductPriceRequest request) {

    String tenantId = tenantContext
        .requireAuthorizedTenant("PRODUCT_PRICE_UPDATE");

    Product product = repository
        .findByIdAndTenantIdAndDeletedFalse(
            productId, tenantId
        )
        .orElseThrow(ProductNotFoundException::new);

    product.changeSellingPrice(
        request.sellingPrice()
    );

    return ProductPublicMapper.toResponse(product);
}
~~~

Product là managed entity. JPA dirty checking đồng bộ thay đổi theo transaction/flush policy; không cần tạo entity detached mới từ JSON rồi merge.

### 10.3. Đổi trạng thái phải qua domain transition

Nếu status cần workflow phê duyệt, không gọi setStatus(request.status()) từ raw input. Dùng activate(), archive(), restore() với authorization và business invariants.

### 10.4. Input DTO hẹp hỗ trợ audit

Endpoint chỉ đổi sellingPrice có thể audit:
- Operation PRODUCT_PRICE_UPDATE;
- Product ID;
- Actor ID từ authenticated context;
- Old/new price nếu policy cho phép;
- Timestamp và request ID.

Không cần ghi toàn bộ Product entity hoặc raw request khác.

### 10.5. Không merge nested graph do client gửi

Nguy hiểm:

~~~json
{
  "name": "Sản phẩm",
  "category": {
    "id": 8,
    "tenantId": "another-tenant",
    "approved": true
  }
}
~~~

Thay vào đó, DTO nhận categoryId. Service load Category bằng ID và authorized tenant rồi gán managed association theo policy.

## 11. PATCH: phân biệt field vắng mặt, null và giá trị

Một bài toán của partial update: **không gửi field** khác với **gửi null để xóa field**, và cũng khác **gửi giá trị mới**.

### 11.1. Ba payload khác nhau

Không gửi name:

~~~json
{
  "sellingPrice": 150000.00
}
~~~

Gửi name null:

~~~json
{
  "name": null
}
~~~

Gửi name mới:

~~~json
{
  "name": "Bàn phím mới"
}
~~~

Nếu dùng record:

~~~java
public record PatchProductRequest(
    String name,
    BigDecimal sellingPrice
) {}
~~~

thì binding JSON thông thường có thể tạo Java null cho cả **field vắng mặt** và **explicit null**. DTO record như trên không tự giữ presence information.

### 11.2. Null là không đổi hay xóa?

Nếu Product có optional description:
- Field absent: giữ nguyên;
- description=null: xóa description;
- description có string: thay description.

Một mapper:

~~~java
if (request.description() != null) {
    product.changeDescription(request.description());
}
~~~

không hỗ trợ xóa description bằng null. Không nhất thiết sai, nhưng phải đúng với API contract.

### 11.3. Các cách biểu diễn presence

Có thể dùng:
- **JSON Merge Patch** theo RFC 7396;
- **JSON Patch** theo RFC 6902;
- Wrapper biểu diễn absent/null/value;
- DTO có flag clearDescription;
- Endpoint hành động riêng cho xóa description.

Cần chọn semantics dễ hiểu, validation rõ và có thể test.

### 11.4. JSON Merge Patch

JSON Merge Patch thường xem member absent là giữ nguyên, member null là xóa member trong document:

~~~json
{
  "description": null
}
~~~

Khi chuyển sang JPA entity phải:
1. Kiểm tra content type/parser;
2. Giới hạn writable paths;
3. Authorization theo operation/property;
4. Validate trạng thái cuối;
5. Gọi domain methods;
6. Không reflection-copy mọi fields từ patch lên entity.

Một patch tới tenantId/status/internalCost không được ghi chỉ vì JSON syntax hợp lệ.

### 11.5. JSON Patch cần path allowlist

Hợp lệ theo một use case:

~~~json
[
  {
    "op": "replace",
    "path": "/sellingPrice",
    "value": 150000.00
  }
]
~~~

Không được phép:

~~~json
[
  {
    "op": "replace",
    "path": "/tenantId",
    "value": "tenant-victim"
  },
  {
    "op": "replace",
    "path": "/deleted",
    "value": false
  }
]
~~~

Allowed patch paths là **allowlist về quyền ghi**, không phải khả năng tùy ý của patch engine.

### 11.6. Validate toàn state sau patch

Giá 0 có thể thỏa @PositiveOrZero nhưng sai khi Product đang ACTIVE và domain yêu cầu giá dương. Kiểm tra domain invariants trên **trạng thái tổng thể**, không chỉ DTO field.

### 11.7. PUT cũng không cho phép ghi internal fields

PUT thường là replacement theo public API contract, nhưng chỉ gồm **writable public properties**. HTTP method PUT không trao quyền sửa tenantId, version hoặc internalCost.

## 12. Bảo vệ khỏi mass assignment qua JSON deserialization

### 12.1. Không tin frontend

Frontend ẩn field role hoặc tenantId không ngăn client tự gửi JSON chứa những fields ấy. Server phải nhận loại DTO xác định, chỉ dùng fields allowlisted và kiểm tra authorization.

### 12.2. Unknown JSON properties: reject hay ignore?

Client gửi:

~~~json
{
  "name": "Bàn phím",
  "sku": "KB-001",
  "sellingPrice": 1000,
  "approved": true
}
~~~

Hai policy:
- **Reject unknown fields:** trả lỗi, dễ phát hiện misuse/thăm dò;
- **Ignore unknown fields:** hỗ trợ forward compatibility trong một số APIs.

Dù chọn cách nào, approved không được tự trở thành writable entity property. Thiết lập JSON mapper/framework policy có chủ đích và kiểm thử thực tế.

### 12.3. Jackson annotations không thay DTO

Ví dụ @JsonIgnore, @JsonProperty(access = READ_ONLY), @JsonView và @JsonIgnoreProperties có thể giúp kiểm soát serialization/binding, nhưng:
- Gắn persistence entity vào một serializer;
- Khó quản lý nhiều audiences khác nhau;
- Không bảo vệ các writers ngoài JSON;
- Dễ bị ảnh hưởng bởi cấu hình/mixins/refactors;
- Không thay object/property authorization.

DTO explicit thường dễ review hơn khi có fields nhạy cảm.

### 12.4. Denylist dễ thiếu field mới

Exclude-list “copy tất cả trừ passwordHash/tenantId” có thể bỏ sót newSecurityFlag, approvedBy, bankAccount được thêm về sau. Allowlist ở mapper khiến field mới **chưa được xuất/ghi** cho đến khi được quyết định.

### 12.5. Giới hạn độ lớn request và nested graph

Client có thể gửi hàng chục nghìn nested objects, arrays hoặc chuỗi quá dài, tạo resource exhaustion qua parsing, validation, cascade và SQL. Cần:
- Request body size limit;
- Max collection size;
- Max nesting depth khi parser hỗ trợ;
- Bean Validation @Size;
- Business batch limits;
- Rate limiting/quotas;
- Không deserialize trực tiếp recursive JPA graph.

### 12.6. Negative test overposting

Một HTTP test nên thử gửi fields id, tenantId, internalCost, status, deleted, version và nested associations trái quyền. Sau request, kiểm tra database bằng context đáng tin và xác nhận các fields bảo mật **không bị thay đổi**; response không được lộ chúng.

### 12.7. DTO admin vẫn cần quyền riêng

AdminUpdateProductRequest có internalCost không có nghĩa bất cứ ai truy cập /admin đều được sửa. Service phải xác thực permission và ghi audit theo business policy.

## 13. Validation của Input DTO: cần nhưng không đủ

### 13.1. Jakarta Bean Validation

~~~java
public record ProductInput(
    @NotBlank
    @Size(max = 200)
    String name,

    @NotBlank
    @Pattern(regexp = "[A-Z0-9-]{3,64}")
    String sku,

    @NotNull
    @PositiveOrZero
    @Digits(integer = 17, fraction = 2)
    BigDecimal sellingPrice
) {}
~~~

Tại HTTP boundary có thể dùng @Valid; ở application/internal pipeline có thể dùng Validator:

~~~java
Set<ConstraintViolation<ProductInput>> errors =
    validator.validate(input);
~~~

Validator.validate trả **tập violations**; không tự xác định caller có quyền tạo Product.

### 13.2. Chọn constraints đúng ngữ nghĩa

| Yêu cầu | Bean Validation thường dùng | Lưu ý |
|---|---|---|
| Không null | @NotNull | Không cấm chuỗi rỗng |
| Chuỗi không trắng | @NotBlank | Phù hợp tên/SKU |
| Độ dài text/collection | @Size | Nên có limits ở server |
| Số không âm | @PositiveOrZero | Thêm @NotNull khi bắt buộc |
| Số lớn hơn 0 | @Positive | Null vẫn cần @NotNull |
| Số nguyên trong khoảng | @Min/@Max | Kiểm tra kiểu dữ liệu |
| BigDecimal digits | @Digits | Không tự định nghĩa rounding |
| Pattern ký tự | @Pattern | Không thay authorization |
| Nested DTO | @Valid ở nested property | Kiểm soát graph size |
| Email syntax | @Email | Không chứng minh email ownership |
| Rule giữa nhiều fields | Class-level/domain invariant | Validate state tổng thể |

### 13.3. Cấu trúc hợp lệ vẫn có thể sai quyền

categoryId=123 là số dương nhưng Category#123 có thể thuộc tenant khác. Validation không có nhiệm vụ xác minh authorization. Application phải query reference theo scope được phép.

### 13.4. Database constraints vẫn cần

DTO @NotNull/@PositiveOrZero không thay SQL NOT NULL/CHECK. Một writer JDBC/ETL hoặc migration có thể bypass Java validation. UNIQUE constraint ở DB bảo vệ concurrent duplicate SKU.

### 13.5. Normalization có policy riêng

Với SKU:
- Có trim không?
- Có chuyển uppercase không?
- Unicode normalization nào?
- Database collation có phân biệt hoa thường không?
- Có chặn control characters hoặc quá dài không?

Input DTO validation, domain normalization và DB unique indexes phải thống nhất. Đừng để một endpoint uppercase SKU nhưng batch import lại lưu lowercase và tạo business duplicates.

### 13.6. Các tầng validation

~~~text
HTTP JSON / queue message
           |
           v
Input DTO constraints
           |
           v
Application authorization
           |
           v
Domain invariants / methods
           |
           v
JPA Bean Validation callbacks (nếu cấu hình)
           |
           v
Database constraints
           |
           v
COMMIT
~~~

Mỗi tầng có phạm vi riêng. Nếu một tầng từ chối dữ liệu, transaction outcome và exception phải được xử lý theo policy.

### 13.7. Không serialize invalidValue bừa bãi

Jakarta ConstraintViolation có thể chứa invalidValue. Với password, token hoặc PII, log/response raw violation có thể lộ dữ liệu. Trả field name, error code và message an toàn.

### 13.8. Create, Update và Activate có thể dùng DTO riêng

Validation groups có thể dùng, nhưng DTO theo use case bộc lộ những field nào được phép ghi và thường dễ review hơn một input class rất lớn.

## 14. DTO lồng nhau và quan hệ JPA

### 14.1. Entity graph không phải JSON graph

Giả sử Product có:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "category_id")
private Category category;

@OneToMany(mappedBy = "product")
private List<ProductImage> images;
~~~

Trả entity có thể khiến serializer duyệt Category, rồi Category.products, rồi Product..., gây recursive serialization, N+1 hoặc lộ dữ liệu không cần thiết.

### 14.2. Nested output DTO

~~~java
public record ProductDetailResponse(
    Long id,
    String name,
    BigDecimal sellingPrice,
    CategoryBriefResponse category,
    List<ProductImageResponse> images
) {}

public record CategoryBriefResponse(
    Long id,
    String name
) {}

public record ProductImageResponse(
    Long id,
    String url,
    int displayOrder
) {}
~~~

Chỉ đưa fields cần thiết. Nếu Category có internalNote hoặc supplier contract, nested DTO không mặc nhiên expose chúng.

### 14.3. Nested input không cần nested entity

~~~java
public record CreateProductWithCategoryRequest(
    @NotBlank String name,
    @NotBlank String sku,
    @NotNull @PositiveOrZero BigDecimal price,
    @NotNull Long categoryId
) {}
~~~

Service:
1. Lấy authorized tenant;
2. Query Category theo ID và tenant scope;
3. Xác nhận Category active/được phép dùng;
4. Tạo Product và gán Category qua domain method;
5. Persist trong transaction.

Không deserialize Category với owner/status do client gửi rồi merge.

### 14.4. Chống IDOR ở mọi nested reference

categoryId, supplierId, imageId, warehouseId và assignedUserId đều có thể là indirect object references. Kiểm tra quyền và tenant của **mọi relation được thêm, thay, xóa**.

### 14.5. Tránh serialize quan hệ vòng

A có B, B có A. DTO có thể cho A chứa BBriefResponse, còn BBriefResponse chỉ chứa id/name hoặc không chứa collection A. Không cần serialize toàn bộ persistence graph.

### 14.6. LazyInitializationException là dấu hiệu boundary chưa rõ

Nếu controller trả entity và transaction đã đóng, serializer truy cập lazy relation có thể lỗi. Bật Open Session in View không phải giải pháp mặc định: nó có thể che N+1 và để view layer truy cập DB ngoài kiểm soát.

Nên query đúng data, map sang DTO trong boundary phù hợp và không để JSON serializer tùy ý duyệt entity graph.

### 14.7. Mapper cũng có thể tạo N+1

~~~java
new ProductDetailResponse(
    product.getId(),
    product.getName(),
    product.getSellingPrice(),
    mapCategory(product.getCategory()),
    mapImages(product.getImages())
);
~~~

Khi Category/Images lazy, các getters có thể tạo nhiều SELECT. DTO mapping giúp giới hạn output nhưng **không tự tối ưu SQL**. Phải thiết kế fetch plan hoặc projection theo response shape.

### 14.8. Pagination của nested collections

Product có 10.000 images thì không nên đưa tất cả vào một response mặc định. Có thể tạo endpoint phân trang images hoặc giới hạn rõ số items.

### 14.9. URL output cũng cần policy

Nếu ProductImage.url được tạo từ input:
- Kiểm tra scheme/host khi cần;
- Không trả token dài hạn/internal storage URL không phù hợp;
- Nếu ký URL tạm thời, đặt TTL/scope;
- Tránh log secret trong query string;
- Không server-side fetch URL user-supplied tùy ý khi chưa có SSRF protections.

DTO giúp chọn field, nhưng không tự kiểm tra URL hoặc quyền truy cập nội dung.

## 15. Projection trực tiếp: đọc đúng fields cần trả

Với danh sách nhiều Products, nạp entity đầy đủ rồi map DTO có thể lãng phí. JPA có thể dùng **constructor projection** chỉ chọn những fields phục vụ response.

### 15.1. JPQL constructor projection

~~~java
public record ProductListItemResponse(
    Long id,
    String name,
    BigDecimal sellingPrice
) {}
~~~

JPQL:

~~~java
List<ProductListItemResponse> items =
    em.createQuery(
        """
        select new com.example.catalog.api.dto.ProductListItemResponse(
            p.id, p.name, p.sellingPrice
        )
        from Product p
        where p.tenantId = :tenantId
          and p.deleted = false
          and p.status = :status
        order by p.id
        """,
        ProductListItemResponse.class
    )
    .setParameter("tenantId", authorizedTenantId)
    .setParameter("status", ProductStatus.ACTIVE)
    .setMaxResults(50)
    .getResultList();
~~~

Đây là JPQL constructor expression; package/class/constructor types phải khớp. JPQL dùng **JPA property names**, không phải SQL column names.

### 15.2. Projection không tự xác thực quyền

Nếu query bỏ tenant predicate, DTO chỉ chứa id/name/price vẫn có thể lộ dữ liệu tenant khác. **Scope ở query và authorization là bắt buộc**.

### 15.3. Chỉ chọn những fields cần dùng

Projection trên chỉ lấy id/name/sellingPrice, không nạp internalCost và lazy graph. Điều này thường giảm lượng dữ liệu chuyển qua JDBC và công mapping/serialization. Tuy nhiên DB có thể đọc physical pages/indexes theo execution plan; không suy rằng database tuyệt đối không chạm dữ liệu nhạy cảm ở storage.

### 15.4. CriteriaBuilder.construct

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();

CriteriaQuery<ProductListItemResponse> cq =
    cb.createQuery(ProductListItemResponse.class);

Root<Product> root = cq.from(Product.class);

cq.select(cb.construct(
    ProductListItemResponse.class,
    root.get("id"),
    root.get("name"),
    root.get("sellingPrice")
));

cq.where(
    cb.equal(root.get("tenantId"), authorizedTenantId),
    cb.isFalse(root.get("deleted"))
);

List<ProductListItemResponse> items =
    em.createQuery(cq)
      .setMaxResults(50)
      .getResultList();
~~~

Root.get nhận **persistent attribute names**; tên SQL physical column thuộc mapping metadata.

### 15.5. Spring Data interface projections

~~~java
public interface ProductSummaryView {
    Long getId();
    String getName();
    BigDecimal getSellingPrice();
}
~~~

Spring Data có thể dùng interface/DTO projections tùy repository/query method. Nested projections có thể phát thêm joins hoặc data loading nên phải kiểm tra SQL.

### 15.6. Page response

~~~java
public record PageResponse<T>(
    List<T> items,
    long total,
    int page,
    int size
) {}
~~~

Nếu cần total, count query phải áp **cùng tenant/visibility predicates**. Không nạp all Products rồi filter client-side; vừa tốn bộ nhớ vừa dễ lộ dữ liệu sai scope.

### 15.7. Sort/filter allowlist

Public API chỉ hỗ trợ sort key như name, sellingPrice, createdAt. Không ghép raw user input vào SQL identifier hoặc JPQL expression. Dùng whitelist mapping và kiểm tra field visibility; sort theo internalCost có thể tiết lộ thông tin gián tiếp dù output không chứa cost.

### 15.8. Khi nào load entity, khi nào projection?

| Use case | Entity load rồi map | DTO projection |
|---|---|---|
| Update có business methods | Phù hợp | Không đủ state để update |
| Cần JPA dirty checking | Có | Không |
| Public product list | Có thể dư dữ liệu | Thường phù hợp |
| Complex domain invariants | Entity có domain behavior | DTO chỉ là dữ liệu |
| Query report | Có thể tốn memory | Thường tốt hơn |
| Read-only response | Có thể dùng | Giảm footprint |
| Authorization | Vẫn bắt buộc | Vẫn bắt buộc |
| Lazy relations | Cần fetch plan | Chọn fields rõ |

Không dùng DTO constructor projection làm entity cho em.persist/em.merge chỉ vì nó có ID; DTO không phải managed entity.

## 16. MapStruct và mapping framework: tự động hóa có kiểm soát

Khi DTO nhiều fields hoặc một project có nhiều endpoints, mapping thủ công có thể dài. **MapStruct** có thể tạo mapper compile-time từ interface; nhưng cần thiết kế allowlist và authorization như khi viết code bằng tay.

### 16.1. Output mapper với explicit fields

Một MapStruct interface minh họa:

~~~java
import org.mapstruct.BeanMapping;
import org.mapstruct.Mapper;
import org.mapstruct.Mapping;
import org.mapstruct.ReportingPolicy;

@Mapper(
    componentModel = "spring",
    unmappedTargetPolicy = ReportingPolicy.ERROR
)
public interface ProductApiMapper {

    @BeanMapping(ignoreByDefault = true)
    @Mapping(target = "id", source = "id")
    @Mapping(target = "name", source = "name")
    @Mapping(target = "sku", source = "sku")
    @Mapping(
        target = "sellingPrice",
        source = "sellingPrice"
    )
    ProductPublicResponse toPublic(Product product);
}
~~~

Ý nghĩa:
- Chỉ fields được liệt kê mới được mapping trong method này;
- Không tự đưa internalCost vào ProductPublicResponse;
- componentModel spring để dùng mapper như Spring bean khi cấu hình processor đúng;
- ReportingPolicy.ERROR giúp phát hiện một số unmapped target, nhưng **ignoreByDefault** cố ý cho phép bỏ qua fields không liệt kê trong method; không nên tuyên bố cùng lúc rằng mọi field mới sẽ tự gây compile error với cấu hình này.

### 16.2. Không để mapper tự kiểm tra authorization

Mapper chỉ chuyển dữ liệu theo mappings. Nó không biết principal, permissions, tenant policy trừ khi app cung cấp context; kể cả có context, authorization ở service/read boundary phải rõ ràng. Tránh nghĩ “toAdmin DTO” tự bảo vệ endpoint.

### 16.3. Input mapping nên dùng domain methods

Product entity minh họa có constructor và methods giữ invariants, không có public setters cho internal fields. Đây là lợi thế: request mapper khó tự ghi state bảo mật nếu API entity được thiết kế hẹp.

Với UpdateProductPriceRequest, service gọi:

~~~java
product.changeSellingPrice(request.sellingPrice());
~~~

đơn giản và minh bạch hơn tạo một auto-update method copy các properties tùy ý vào managed Product.

### 16.4. Nếu dùng @MappingTarget

MapStruct có khả năng update một object đích hiện có, ví dụ:

~~~java
void updateEntity(
    UpdateProductRequest source,
    @MappingTarget Product target
);
~~~

Nhưng nếu Product có setters rộng, method này có thể mở đường ghi ngoài ý muốn. Cần:
- Liệt kê mappings explicit;
- Không map id, tenantId, status, deleted, internalCost;
- Kiểm tra null strategy;
- Chọn domain methods khi workflow có invariants;
- Viết negative tests cho overposting;
- Không dùng update mapping thay authorization.

### 16.5. NullValuePropertyMappingStrategy không phải quyền ghi

Một mapper có option ignore null có thể dùng cho partial updates. Nhưng ignore null không phân biệt absent với explicit null trong JSON theo mọi DTO. Nó không ngăn client cố sửa property không được phép nếu target mappings được mở rộng sai.

### 16.6. Tránh mapping recursion

Nếu entity hai chiều Category.products/Product.category, auto mapper có thể đệ quy vô hạn hoặc kích hoạt nhiều lazy queries. Response DTO nên dùng nested brief projection, IDs hoặc explicit graph depth. **Không map toàn entity graph mặc định**.

### 16.7. DTO classes và compiler warnings

Compile-time mapper giúp phát hiện type mismatch và một số thiếu mappings, nhưng:
- Security rules không tự được compiler kiểm chứng;
- Cấu hình reporting/ignore có thể bỏ warnings;
- Optional fields/normalization cần tests;
- API contract thay đổi phải review.

MapStruct là **công cụ giảm boilerplate**, không phải một authorization framework.

## 17. Dữ liệu nhạy cảm, PII và DTO response

### 17.1. Password và credential fields

Một User entity có thể chứa passwordHash, resetTokenHash hoặc MFA state. **Không bao giờ** trả password hash vì “đã hash nên an toàn” — hash vẫn là dữ liệu nhạy cảm và có thể tạo cơ hội brute force/offline attacks nếu bị lộ.

### 17.2. DTO tạo tài khoản cần riêng

~~~java
public record RegisterUserRequest(
    @NotBlank String email,
    @NotBlank String password,
    @NotBlank String displayName
) {}

public record UserProfileResponse(
    Long id,
    String email,
    String displayName
) {}
~~~

Trong service, validate password policy, xử lý password bằng password hasher phù hợp, không ghi plaintext vào DB/log. Sau khi đăng ký, chỉ trả profile DTO. Cần xác minh email ownership bằng workflow riêng; @Email chỉ kiểm tra cú pháp tương đối.

### 17.3. Không giữ plaintext secret trong events

Một event như UserCreated không nên chứa password plaintext. Audit logs, tracing, error messages và queue payload phải có data minimization tương tự HTTP response.

### 17.4. Redaction và masking

Nếu một support DTO cần hiển thị một phần số điện thoại hoặc account number, tạo field maskedPhone/maskedAccount với policy rõ. Không đưa full value vào DTO rồi trông đợi frontend che bằng CSS.

### 17.5. Trường public hôm nay có thể thành sensitive ngày mai

Một business field có thể thay đổi classification theo vùng pháp lý, tenant hoặc sản phẩm. DTO theo audience giúp review khi thay policy mà không phải sửa mọi nơi có Entity getter.

### 17.6. Encryption không thay authorization

Database field được encrypt-at-rest không có nghĩa mọi endpoint được quyền trả plaintext sau decryption. DTO mapping phải chọn fields phù hợp và service phải xác minh quyền đọc.

### 17.7. Logging request/response body

Middleware log toàn bộ HTTP JSON có thể ghi password, address, phone, financial fields dù controller dùng DTO an toàn. Cần:
- Redaction/field allowlist;
- Content-type/body limits;
- Log level và retention;
- Tránh log secrets trong URLs;
- Phân quyền truy cập logs;
- Không serialize Throwable/entity trong error logs thiếu kiểm soát.

### 17.8. Data minimization cả ở database query

Nếu API công khai chỉ cần id, name, sellingPrice, một DTO projection giúp tránh lấy internalCost từ DB vào application memory không cần thiết. Điều này bổ sung cho security policy, đồng thời có thể cải thiện performance.

## 18. Concurrency, @Version và DTO

DTO giúp quyết định client được gửi thông tin gì; nó cũng giúp định nghĩa **precondition** khi nhiều người sửa cùng một Product.

### 18.1. @Version trên entity

~~~java
@Version
private Long version;
~~~

JPA dùng version field để hỗ trợ optimistic locking cho managed entity updates. Khi transaction sửa entity từ stale version, provider có thể ném OptimisticLockException ở flush/commit.

**Version là metadata quản lý concurrency**, không phải một field mà client được set vào entity tùy ý bằng mass assignment.

### 18.2. Output có thể chứa version công khai cho use case phù hợp

~~~java
public record ProductEditResponse(
    Long id,
    String name,
    BigDecimal sellingPrice,
    Long version
) {}
~~~

Chỉ endpoint chỉnh sửa được phép mới cần version nếu UI dùng optimistic conflict detection. API public read-only không nhất thiết có version.

### 18.3. Input nên biểu diễn expected version

Một update request:

~~~java
public record UpdateProductPriceRequestWithVersion(
    @NotNull @PositiveOrZero BigDecimal sellingPrice,
    @NotNull Long expectedVersion
) {}
~~~

Service có thể kiểm tra expectedVersion bằng JPA managed entity hiện tại, rồi gọi domain method. **Không copy expectedVersion vào entity.version**.

### 18.4. HTTP If-Match

Một API có thể dùng ETag/If-Match thay vì đưa version trong JSON body:
- GET trả ETag đại diện version;
- PUT/PATCH yêu cầu If-Match;
- Nếu không khớp, server trả 412 Precondition Failed theo HTTP semantics;
- Nếu conflict xuất hiện ở JPA flush, transaction rollback và response phù hợp.

ETag có thể là opaque token thay vì lộ raw database version. Policy phải thống nhất giữa cache/HTTP/JPA concurrency.

### 18.5. Không retry stale detached DTO bằng merge vô điều kiện

Nếu client sửa name ở version 5, trong lúc đó admin đã đổi price ở version 6, tự tạo entity detached từ DTO rồi merge có thể ghi đè price cũ thành giá không mong muốn. Với input DTO hẹp, service nạp current entity và chỉ áp field được phép, đồng thời kiểm tra version/intent.

### 18.6. DTO không loại bỏ race UNIQUE

Hai CreateProductRequest đều hợp lệ và đều muốn SKU KB-001. Cả hai có thể qua validation và pre-check, nhưng database UNIQUE vẫn quyết định một transaction thất bại. Cần map constraint violation thành business conflict phù hợp; không thử giải quyết concurrency bằng DTO validation.

### 18.7. Khi domain invariant phụ thuộc nhiều fields

Ví dụ Product ACTIVE phải có sellingPrice > 0. Một price update DTO chỉ có sellingPrice, nhưng service cần kiểm tra **current status** để tránh cập nhật ACTIVE về 0. Validation field riêng không đủ; domain method phải bảo vệ invariant.

## 19. Response lỗi: không lộ thông tin persistence

### 19.1. Không trả JPA exception raw

Nguy hiểm nếu API trả:

~~~json
{
  "error": "org.hibernate.exception.ConstraintViolationException",
  "sql": "insert into products ...",
  "constraint": "uk_products_tenant_sku",
  "details": "tenant_id=tenant-private, sku=KB-001"
}
~~~

Response có thể lộ tên bảng/cột, tenant identity, SQL và giá trị đã tồn tại. Client thường không cần những chi tiết đó.

### 19.2. Error DTO ổn định

~~~java
public record ApiError(
    String code,
    String message,
    String requestId,
    List<FieldErrorDto> fields
) {}

public record FieldErrorDto(
    String field,
    String code,
    String message
) {}
~~~

Ví dụ response:

~~~json
{
  "code": "PRODUCT_SKU_CONFLICT",
  "message": "Mã sản phẩm không thể sử dụng.",
  "requestId": "req-7f4c",
  "fields": [
    {
      "field": "sku",
      "code": "CONFLICT",
      "message": "Mã sản phẩm đã được sử dụng."
    }
  ]
}
~~~

Chỉ dùng thông điệp cụ thể nếu security policy cho phép tiết lộ sự tồn tại của SKU trong scope caller. Trong một số use case, response chung sẽ thích hợp hơn để tránh enumeration.

### 19.3. DTO validation error

Khi @NotBlank name fail, handler có thể trả:
- code=VALIDATION_FAILED;
- field=name;
- message an toàn;
- requestId.

Không return nguyên BindingResult/ConstraintViolation objects vì chúng có thể chứa rejected values hoặc nội bộ serializer state.

### 19.4. SQL constraint error không luôn do user

DB CHECK/NOT NULL violation có thể là bug server hoặc schema drift. Không map mọi DataIntegrityViolationException thành HTTP 400. Phân loại theo constraint/operation/context; lỗi không rõ phải log nội bộ và trả response an toàn.

### 19.5. Authorization failure và not-found

Nếu Product thuộc tenant khác, không trả:
- tenantId của chủ sở hữu;
- Tên Product;
- Cost;
- “Bạn không được xem sản phẩm có SKU X ở tenant Y”.

Chọn 403/404 theo policy, bảo đảm response không biến thành kênh dò sự tồn tại tài nguyên.

### 19.6. Không leak persistence errors qua log-level response

Một global exception handler không nên làm:

~~~java
return ResponseEntity.status(500)
    .body(exception.toString());
~~~

Thay bằng ApiError generic cùng correlation ID. Stack traces và SQLState chỉ nằm trong logs được phân quyền và đã kiểm soát dữ liệu nhạy cảm.

### 19.7. DTO error cũng có API version

Error codes ổn định hơn raw messages có thể dịch ngôn ngữ. Client nên dựa vào code/field được công bố, không parse English exception messages từ Hibernate/DB.

## 20. Đầu vào DTO trong các use case có quan hệ quyền phức tạp

### 20.1. Thêm Product vào Category

~~~java
public record AssignProductCategoryRequest(
    @NotNull Long categoryId
) {}
~~~

Service cần xác minh:
- Caller có PRODUCT_CATEGORY_EDIT cho Product;
- Product thuộc authorized tenant;
- Category thuộc tenant/scope cho phép;
- Category active;
- Quan hệ hợp lệ;
- Không tạo cross-tenant FK;
- Audit nếu cần.

### 20.2. Chuyển quyền sở hữu là command đặc biệt

Một input:

~~~json
{
  "ownerTenantId": "tenant-b"
}
~~~

không nên được nhận trong generic UpdateProductRequest. Nếu business cho phép transfer ownership, nên có use case riêng với:
- High-privilege authorization;
- Source/target tenant checks;
- Audit;
- Reference/cascade policy;
- Transaction consistency;
- Explicit transfer command.

### 20.3. Hành động xóa/khôi phục

Field deleted không được phép sửa tùy ý từ public JSON. Xóa và restore thường cần:
- Endpoint action;
- Permission riêng;
- Soft delete policy;
- Retention/legal hold checks;
- Audit;
- Versioning/concurrency;
- Không cho người dùng thông thường tự set deleted=false.

### 20.4. Approve/reject workflow

Nếu Product cần moderation, field approvedBy hoặc status không thuộc DTO create/update chung. Chỉ moderation service được gán approver từ authenticated principal và ghi thời gian server.

### 20.5. Reference IDs phải chống race

Khi client gửi categoryId hợp lệ, Category có thể bị xóa hoặc disable trước transaction commit. Authorization/service pre-check cần kết hợp database FK, transaction isolation hoặc state checks tùy nghiệp vụ. DTO không bảo đảm reference còn hợp lệ tại thời điểm commit.

## 21. DTO trong event và message boundaries

HTTP không phải ranh giới duy nhất. Nếu publish JPA entity trực tiếp lên Kafka/RabbitMQ hoặc serialize trong outbox, có thể lộ fields nhạy cảm và ràng buộc consumers vào persistence model.

### 21.1. Không publish entity trực tiếp

Nguy hiểm:

~~~java
eventPublisher.publish(product);
~~~

nếu event serializer tự duyệt toàn entity. Khi entity thêm internalCost hoặc newSecretField, message payload có thể tự mở rộng. Lazy relations cũng có thể phát query hoặc fail.

### 21.2. Event DTO rõ contract

~~~java
public record ProductCreatedEventV1(
    String eventId,
    String productPublicId,
    String sku,
    String name,
    Instant occurredAt
) {}
~~~

Chỉ đưa fields consumer được phép dùng; trong một số hệ, SKU cũng có thể nhạy cảm và phải xem theo trust boundary.

### 21.3. Internal event không tự an toàn

Một internal consumer có thể chạy ở môi trường khác, có retention lâu hơn, được truy cập bởi nhiều services. **Internal** không đồng nghĩa private. Cần event schema review, permission, encryption/trust policy và data minimization.

### 21.4. Outbox và transaction boundary

Nếu tạo Product rồi publish event trước database commit, event có thể xuất hiện dù transaction rollback. Một **transactional outbox** ghi event DTO/record vào cùng DB transaction; publisher đọc outbox sau commit và gửi đi. Cần idempotent consumers vì delivery có thể lặp.

### 21.5. Không để event consumer merge raw entity

Một consumer nhận ProductUpdatedEvent rồi hydrate thành Product JPA entity detached và merge có thể overwrite fields không nằm trong event. Nên xử lý **command/event fields allowlisted** và domain transitions với version/idempotency.

### 21.6. Event versioning

ProductCreatedEventV1 có thể giữ nguyên trong khi database Product schema thay đổi. Nếu consumer cần field mới, dùng backward-compatible evolution hoặc event V2 theo policy. Tách event DTO khỏi entity giúp giảm coupling.

## 22. DTO và ranh giới bảo mật giữa microservices

### 22.1. Service-to-service request cũng không nên nhận entity

Một service khác gửi:

~~~json
{
  "productId": 42,
  "internalCost": 100
}
~~~

không có nghĩa nó được phép thay giá vốn. Service nhận phải xác thực caller identity/scope và chỉ chấp nhận commands được cho phép. DTO phù hợp với trust boundary của nội bộ.

### 22.2. Không tái sử dụng JPA entity như shared library schema

Nếu nhiều microservices dùng chung Product entity class:
- Thay đổi @Column/mapping kéo theo releases;
- Lazy proxies hoặc ORM dependencies bị lộ;
- JSON representation phụ thuộc internal persistence fields;
- Consumer có thể hiểu nhầm version/status;
- Security review trở nên khó.

Shared API schema/DTO contract hoặc event schema thường phù hợp hơn là chia sẻ ORM entity giữa bounded contexts.

### 22.3. Không để tenant metadata do upstream tự khai tùy ý

Nếu upstream gửi tenantId, downstream phải xác định nó có được tin trong context hay không; thường cần delegated identity/scopes, mTLS/service auth hoặc signed claims. Việc có trường tenantId trong internal DTO không tự cấp quyền tenant.

### 22.4. Contract tests cần đi cùng authorization tests

Một JSON schema test có thể xác nhận fields/types, nhưng không chứng minh caller A không thể nhận cost field của tenant B. Cần negative authorization test trên service boundary.

### 22.5. DTO không thay transport security

HTTPS/mTLS, authentication, network policies, encryption at rest và audit vẫn cần khi threat model yêu cầu. DTO giới hạn payload, không thay toàn bộ hệ thống bảo mật.

## 23. Kiểm thử đơn vị: DTO, validation và mapper

DTO security có thể và cần được kiểm chứng. Không nên chỉ nhìn thấy record/class DTO rồi kết luận chắc chắn không lộ dữ liệu.

### 23.1. Validate CreateProductRequest

Ví dụ JUnit 5 với Jakarta Validator:

~~~java
import jakarta.validation.*;
import org.junit.jupiter.api.Test;
import java.math.BigDecimal;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.*;

class CreateProductRequestValidationTest {

    @Test
    void rejectsBlankNameAndNegativePrice() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            CreateProductRequest input =
                new CreateProductRequest(
                    "  ",
                    "KB-001",
                    new BigDecimal("-5.00")
                );

            Set<ConstraintViolation<CreateProductRequest>> errors =
                validator.validate(input);

            assertTrue(errors.stream().anyMatch(v ->
                v.getPropertyPath().toString().equals("name")
            ));

            assertTrue(errors.stream().anyMatch(v ->
                v.getPropertyPath().toString()
                    .equals("sellingPrice")
            ));
        }
    }
}
~~~

Test cần Jakarta Bean Validation provider đúng dependency. Đây là DTO unit test, không chứng minh SQL CHECK hoặc tenant authorization.

### 23.2. Null khác zero

~~~java
@Test
void nullAndZeroHaveDifferentOutcomes() {
    CreateProductRequest missing =
        new CreateProductRequest("Item", "KB-001", null);

    CreateProductRequest zero =
        new CreateProductRequest(
            "Item", "KB-002", BigDecimal.ZERO
        );

    assertFalse(validator.validate(missing).isEmpty());
    assertTrue(validator.validate(zero).isEmpty());
}
~~~

Đoạn này giả định validator là fixture đã khởi tạo. @PositiveOrZero cho phép zero; domain ACTIVE có thể yêu cầu giá > 0.

### 23.3. Test manual mapper

~~~java
@Test
void publicMapperExposesOnlyWhitelistedFields() {
    Product product = new Product(
        "tenant-a",
        "Bàn phím",
        "KB-001",
        new BigDecimal("1000.00"),
        new BigDecimal("650.00"),
        Instant.parse("2026-01-01T00:00:00Z")
    );

    ProductPublicResponse response =
        ProductPublicMapper.toResponse(product);

    assertEquals("KB-001", response.sku());
    assertEquals(
        new BigDecimal("1000.00"),
        response.sellingPrice()
    );
}
~~~

Test bảo đảm mapper trả đúng giá bán. Để xác nhận **không lộ field** qua JSON, cần test serializer thực tế.

### 23.4. Test JSON output shape

~~~java
@Test
void publicJsonHidesInternalFields() throws Exception {
    ProductPublicResponse dto =
        new ProductPublicResponse(
            42L,
            "Bàn phím",
            "KB-001",
            new BigDecimal("1000.00")
        );

    String json = objectMapper.writeValueAsString(dto);

    assertFalse(json.contains("internalCost"));
    assertFalse(json.contains("tenantId"));
    assertFalse(json.contains("deleted"));
    assertFalse(json.contains("version"));
}
~~~

Dùng **ObjectMapper được cấu hình như production**, vì naming strategy, mixins hoặc serialization modules có thể khiến output khác.

### 23.5. Test mapping không trigger lazy graph

Public mapper chỉ cần ID/name/sku/sellingPrice, không cần Category/images. Có thể test bằng Hibernate SQL statistics/JDBC proxy để đo queries và bảo đảm mapper không truy cập graph ngoài ý muốn. Không suy việc gọi getter không gây SQL nếu mapping/fetch behavior chưa được xác nhận.

### 23.6. Test expectedVersion là precondition

Nếu client gửi expectedVersion=4 trong khi DB version=5, service trả conflict. Không bao giờ gán entity.version=4 từ DTO để “qua validation”; @Version thuộc cơ chế concurrency JPA.

## 24. HTTP tests: overposting, IDOR và response leakage

### 24.1. Request có fields ngoài DTO

~~~java
@Test
void extraInternalFieldsAreNotWritable() throws Exception {
    String body = """
        {
          "name": "Bàn phím",
          "sku": "KB-001",
          "sellingPrice": 1000,
          "internalCost": 0,
          "tenantId": "tenant-victim",
          "status": "ACTIVE",
          "deleted": false,
          "version": 999
        }
        """;

    mockMvc.perform(
        post("/products")
            .contentType(MediaType.APPLICATION_JSON)
            .content(body)
    )
    .andExpect(status().is4xxClientError());
}
~~~

Expected 4xx chỉ phù hợp nếu API chọn **reject unknown fields**. Với policy ignore, test nên kỳ vọng response thành công và kiểm tra DB không ghi internal fields. **Mục tiêu bảo mật là không để field ngoài allowlist bị ghi**, không phải một HTTP status cố định.

### 24.2. Test tenant không lấy từ JSON

Authenticated user thuộc tenant-a, JSON cố gửi tenantId=tenant-b. Sau request:
- Nếu reject unknown → request fail;
- Nếu ignore unknown → stored Product phải thuộc tenant-a;
- Không bao giờ được lưu tenant-b do client khai.

Kiểm tra bằng trusted query/EntityManager sau commit, không chỉ xem response.

### 24.3. Public GET không leak

~~~java
mockMvc.perform(get("/products/42"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(42))
    .andExpect(jsonPath("$.internalCost").doesNotExist())
    .andExpect(jsonPath("$.tenantId").doesNotExist())
    .andExpect(jsonPath("$.deleted").doesNotExist());
~~~

Fixture phải có Product#42 thuộc caller và quyền đọc. Ngoài positive test còn cần negative tests.

### 24.4. Test permission đọc giá vốn

- User có PRODUCT_READ nhưng thiếu PRODUCT_COST_READ → cost endpoint không được trả internalCost;
- User có PRODUCT_COST_READ đúng tenant → có thể nhận cost response;
- Public endpoint không trả cost ngay cả cho admin nếu public contract chỉ gồm fields tối thiểu.

### 24.5. Test object-level authorization

Tạo Product#42 tenant-a và Product#43 tenant-b. User A:
- GET 42 thành công;
- GET 43 bị từ chối/che giấu;
- PATCH 43 không sửa DB;
- Không có error detail tiết lộ tenant-b hoặc giá vốn.

### 24.6. Test nested reference thuộc tenant khác

Gửi categoryId thuộc tenant-b trong CreateProductRequest của tenant-a. Service phải reject hoặc che giấu theo policy. Một foreign key đơn giản chỉ chứng minh reference tồn tại, không tự kiểm tra cross-tenant rule.

### 24.7. Test PATCH allowlist

JSON Patch thay /sellingPrice được phép cho authorized caller; patch /tenantId, /internalCost hoặc /deleted không được ghi. Test phải kiểm tra database state sau request.

### 24.8. Test absent/null/value

Với optional description:
- Không gửi description → giữ nguyên;
- description=null → xóa nếu contract cho phép;
- description có string → thay mới.

Nếu một DTO nullable đơn giản không biểu diễn được absent vs null, test sẽ giúp phát hiện vấn đề contract.

### 24.9. Test payload size/depth limits

Gửi nested collection rất lớn hoặc JSON cực sâu; API phải từ chối có kiểm soát chứ không cascade/persist khối dữ liệu vượt chính sách.

### 24.10. Error response không lộ SQL

Gây validation/UNIQUE error. Assert public response không chứa raw SQL, stack trace, Hibernate exception class, internal tenant ID, rejected password hoặc token.

## 25. Integration tests JPA và database

### 25.1. Database thực và migrations thật

Nên kiểm thử trên PostgreSQL/Testcontainers hoặc DB gần production với migrations:
- NOT NULL;
- CHECK selling_price >= 0;
- UNIQUE(tenant_id,sku);
- Foreign keys;
- Optimistic locking.

Không chỉ dựa vào H2 auto-generated schema.

### 25.2. Test DTO validation không thay CHECK

Dùng JDBC INSERT price âm vào database test. SQL CHECK phải từ chối ngay cả khi không có Java DTO validation.

### 25.3. Concurrent duplicate SKU

Hai CreateProductRequest trong cùng tenant có thể đều qua validation và pre-check. UNIQUE database phải ngăn duplicate; service/handler map conflict thành response ổn định, không lộ constraint name/raw SQL.

### 25.4. Test update giữ internal fields

Tạo Product internalCost=650, status=DRAFT, tenantId=tenant-a. Gọi price update sellingPrice=1200 rồi kiểm tra DB:
- Price mới đúng;
- InternalCost vẫn 650;
- TenantId vẫn tenant-a;
- Status vẫn DRAFT;
- JPA version được quản lý theo expected behavior.

Đây là regression test cho blanket copy và detached merge nguy hiểm.

### 25.5. Optimistic conflict

Dùng hai EntityManagers/transactions độc lập, B commit @Version trước khi A flush. Assert A nhận conflict và dữ liệu B không bị ghi đè.

### 25.6. Projection phải scope theo tenant

Database chứa Product tenant-a và tenant-b. Query ProductListItemResponse cho tenant-a chỉ trả rows được phép, deleted=false và status policy. Count query phải dùng cùng tenant/visibility predicates.

### 25.7. N+1 và lazy fetch

Bật provider SQL statistics trong test để biết DTO mapping có phát thêm SELECT do Category/images hay không. Không assert một raw SQL string tuyệt đối qua mọi dialect.

### 25.8. Cache response có security scope

Nếu cache ProductManagementResponse, cache key/authorization phải phân biệt tenant, audience và permission. Không trả cached admin response cho public caller chỉ vì cùng Product ID.

### 25.9. Transaction boundary

Nếu service trả DTO trước khi @Transactional proxy commit, lỗi UNIQUE ở commit phải được handler bắt tại outer boundary. Test bằng request thật, không chỉ assert service method body return.

### 25.10. Outbox và event DTO

Khi create rollback, không có ProductCreated event committed trong outbox. Message consumers dùng event DTO, không serialize toàn entity.

### 25.11. Schema mới không tự lộ field

Thêm internalRiskScore vào Product entity. Public JSON snapshot/regression test vẫn không có field này nếu DTO không thay đổi. Đây là kiểm chứng trực tiếp lợi ích tách entity và API.

## 26. Quy tắc kiến trúc để không để entity đi qua boundary

Một nhóm guardrails có thể được thực thi bằng code review, static analysis hoặc architecture tests.

### 26.1. Controller không dùng JPA Entity làm public request/response

Trong API package:
- Không có @RequestBody trên entity JPA;
- Không trả entity JPA trực tiếp;
- Không expose lazy proxy từ controller;
- Không trả repository.findAll() như JSON mà không scope/DTO.

Một số hệ có serializer/binding policy riêng, nhưng DTO explicit thường dễ review hơn.

### 26.2. Java getter không phải quyền đọc HTTP

Entity.getInternalCost() có thể dùng trong domain/internal report; việc getter public không có nghĩa caller API được xem giá vốn. Authorization và response DTO quyết định dữ liệu được trả.

### 26.3. Tổ chức code theo ownership

Một cách phân tách:
- API sở hữu request/response DTOs;
- Application sở hữu commands/services;
- Domain giữ invariants;
- Persistence adapter sở hữu JPA mapping/repository;
- Mapper nằm ở boundary rõ.

Không phải mọi dự án phải có cùng package names; điều quan trọng là **trách nhiệm không bị trộn**.

### 26.4. DTO cho từng audience

Không dùng một FullProductDto với boolean includeSensitiveFields tràn khắp controllers nếu security policy dễ nhầm. Chọn ProductPublicResponse, ProductManagementResponse và ProductCostResponse với permissions rõ.

### 26.5. Không tự thêm Serializable cho mọi DTO

DTO dùng cho HTTP JSON không mặc nhiên cần Java Serializable. Nếu dùng Java serialization, phải xét deserialization risks, class compatibility và schema evolution; tên “DTO” không tự là lý do dùng Serializable.

### 26.6. API contract testing

OpenAPI/JSON Schema có thể sinh từ DTO để:
- Xác nhận fields/types;
- Phát hiện breaking changes;
- Review fields mới;
- Bảo đảm internalCost không tự xuất trong public contract;
- Giữ API version độc lập database schema.

Schema contract test không thay authorization test; một payload đúng schema vẫn có thể lộ dữ liệu sai tenant.

### 26.7. Bộ security regression

Nên kiểm tra overposting, excessive response fields, BOLA/IDOR, property-level permission, cross-tenant references, PATCH paths, unknown JSON fields, error leakage, cache scope, tenant-filtered projections và event DTO minimization.

## 27. Anti-pattern và hướng xử lý

| Anti-pattern | Rủi ro | Thay bằng |
|---|---|---|
| @RequestBody Product entity | Mass assignment | Input DTO allowlist |
| Trả trực tiếp entity từ GET | Lộ field nội bộ | Output DTO explicit |
| Repository.findAll rồi serialize | Lộ rows khác tenant | Scoped query + DTO |
| Chỉ @JsonIgnore trên entity | Serialization coupling | DTO theo audience |
| Một DTO chứa mọi entity property | Ranh giới giả | DTO theo use case |
| Một response dùng chung admin/public | Expose dữ liệu vượt quyền | Public/Management/Cost DTO |
| Copy toàn DTO vào managed entity | Ghi nhầm internal fields | Domain methods + allowlist |
| BeanUtils.copyProperties không kiểm soát | Overposting sau khi thêm field | Explicit field mapping |
| Auto mapper map mọi property | Field mới tự writable | Allowlist + tests |
| Nhận tenantId từ raw JSON | Cross-tenant corruption | Authenticated tenant context |
| Dùng @Column(updatable=false) làm quyền | Không authorize caller | Service authorization |
| Coi @Valid đã bảo mật | BOLA vẫn tồn tại | Resource/property checks |
| findById không scope theo tenant | IDOR | Query tenant-aware |
| Client set role/status/approvedBy | Privilege escalation | Server-side workflow |
| Client ghi @Version | Sai optimistic semantics | Expected-version precondition |
| Merge detached DTO entity | Lost update/internal field overwrite | Managed entity + domain method |
| PATCH mọi JSON path | Sửa tenantId/deleted | Path allowlist |
| PATCH null không phân biệt absent | Thay đổi semantics | Presence-aware model |
| Nested entity từ client | Cross-tenant association | ID + scoped lookup |
| Serialize lazy graph | N+1/recursion/leak | DTO/projection/fetch plan |
| Bật OSIV chỉ để serialize | Layering mờ, query ngoài ý muốn | Map trong transaction |
| @JsonView coi như authorization | Wrong view/scope | Service permission |
| Trả raw SQL error | Lộ schema/PII | Safe ApiError DTO |
| Log invalidValue | Lộ password/token | Redaction và field codes |
| Publish entity như event | Coupling và data leakage | Versioned event DTO |
| Projection không tenant filter | Data exposure | Authorized predicates |
| Cache chỉ theo Product ID | Cross-tenant/audience leakage | Scoped cache keys |
| Public sort theo internalCost | Lộ thông tin gián tiếp | Sort/filter allowlist |
| Thay field entity tự mở API | Breaking changes/leak | Explicit DTO version |
| Dùng UUID thay authorization | IDOR vẫn có thể xảy ra | Ownership checks |
| Chỉ test happy path | Bỏ sót regressions | Negative authorization tests |

Dù ID khó đoán, nó có thể bị lộ qua links, logs hoặc các luồng nghiệp vụ khác. **Không bao giờ lấy “ID không đoán được” làm biện pháp duy nhất bảo vệ object.**

## 28. Bảng so sánh các cách tạo DTO

| Cách | Ưu điểm | Hạn chế | Phù hợp |
|---|---|---|---|
| Manual mapper | Explicit allowlist, dễ đọc | Boilerplate | API bảo mật |
| JPQL constructor | Chỉ đọc selected fields | Constructor/query coupling | Public lists |
| Criteria construct | Dynamic queries | Dài dòng | Dynamic reports |
| Spring Data interface projection | Ít code | Nested queries cần kiểm tra | Simple read endpoints |
| MapStruct explicit | Compile-time mapping | Cần config allowlist | Nhiều DTOs |
| Reflection property copy | Viết nhanh | Overposting | Tránh ở boundary nhạy cảm |
| Entity + @JsonIgnore | Legacy mitigation | Serializer coupling | Hỗ trợ tạm thời |
| Entity + @JsonView | Multiple views | Policy phức tạp | Chỉ nếu kiểm soát chặt |
| Generic PATCH mapper | Linh hoạt | Paths, tri-state và auth khó | Chỉ với allowlist |
| Versioned event DTO | Contract rõ ràng | Phải quản lý evolution | Async messaging |

### 28.1. Chọn theo threat model

Nếu entity chứa nhiều fields nhạy cảm, response public rất nhỏ, manual mapper hoặc DTO projection dễ review. Nếu có hàng chục screens, MapStruct explicit có thể giảm boilerplate. **Ít code nhất không đồng nghĩa an toàn nhất**.

### 28.2. Chọn theo workload

Với list nhiều Products, DTO projection giảm entity graph loading. Nhưng nếu update có domain invariants, nạp managed entity và gọi domain methods vẫn phù hợp. DTO projection là dữ liệu, không phải entity để merge.

### 28.3. Chọn theo audience và ownership

Một công cụ mapping tốt vẫn không tự quyết định role nào được đọc internalCost. Service và authorization policy phải sở hữu quyết định, mapper chỉ thực thi danh sách fields đã chọn.

## 29. Bài tập thực hành

Các bài tập yêu cầu giải thích **field nào được phép nhận, field nào được phép trả, authorization ở đâu, mapping đến entity ra sao và kiểm thử thế nào**. Không chỉ viết một class có hậu tố Dto.

### Bài 1. Phân biệt Entity và DTO

Cho Product entity có id, tenantId, name, sku, sellingPrice, internalCost, status, deleted và version. Hãy thiết kế CreateProductRequest và ProductPublicResponse. Giải thích vì sao hai DTO không giống Product entity.

### Bài 2. Mass assignment

Controller nhận @RequestBody Product, client gửi status=ACTIVE, deleted=false, tenantId=tenant-victim. Mô tả các rủi ro. Thay controller bằng CreateProductRequest allowlist và server-side tenant context.

### Bài 3. @Column(updatable=false)

Entity có @Column(updatable=false) trên tenantId. Có thể coi đó là biện pháp authorization để client gửi tenantId tùy ý không? Giải thích cả INSERT và những xử lý Java trước UPDATE.

### Bài 4. @JsonIgnore vs DTO

Một team gắn @JsonIgnore cho internalCost nhưng trả Product entity. Khi entity thêm supplierBankAccount, rủi ro gì xuất hiện? Thiết kế explicit ProductPublicResponse.

### Bài 5. Public và admin views

Public user được thấy id, name, sellingPrice; admin được thấy status, version; finance được thấy internalCost. Viết ba DTO types và nêu quyền tương ứng cần kiểm tra.

### Bài 6. @NotNull, @NotBlank và @PositiveOrZero

CreateProductRequest có name, sku, sellingPrice. Chọn constraints phù hợp. Input name="   ", price=-10 và price=null được xử lý khác nhau thế nào?

### Bài 7. Validation không phải authorization

Client gửi categoryId=123 hợp lệ về số, nhưng Category thuộc tenant khác. Vì sao @NotNull/@Positive không giải quyết? Viết pseudocode service query Category theo authenticated tenant.

### Bài 8. Không lấy tenant từ client

User thuộc tenant-a gửi JSON tenantId=tenant-b. Nếu parser ignore unknown field, Product mới phải có tenantId nào? Nếu parser reject unknown field, expected response là gì? Kiểm chứng bằng test database.

### Bài 9. Update một field

Một endpoint chỉ đổi sellingPrice. Thiết kế UpdateProductPriceRequest và service nạp managed Product theo ID+tenant rồi gọi changeSellingPrice. Vì sao không merge Product detached chứa mọi fields?

### Bài 10. Ghi đè entity qua merge

Client gửi Product ID=42, name mới nhưng không có internalCost/status. Repository.save có thể merge detached state. Những field nào có nguy cơ bị thay bằng null/default? Cách tránh?

### Bài 11. Thêm field mới vào entity

Sau deploy, Product thêm internalRiskScore. Nếu controller trả entity, có thể xảy ra chuyện gì khi serializer nhìn thấy getter mới? Nếu controller trả ProductPublicResponse explicit, response thay đổi không?

### Bài 12. Từ create đến activate

DRAFT cho phép price=0, ACTIVE yêu cầu price>0. Thiết kế CreateProductRequest, endpoint activate và domain method. Vì sao không nhận status=ACTIVE trong generic create request?

### Bài 13. Đổi tên sản phẩm

Viết RenameProductRequest chỉ có name và service update. Nếu client gửi thêm deleted=true, phải xử lý theo unknown field policy mà không cho sửa deleted.

### Bài 14. Nested category entity

Một request JSON chứa category:{id,tenantId,approved}. Vì sao không nên deserialize thành managed Category rồi merge? Thiết kế DTO chỉ nhận categoryId và checks cần có.

### Bài 15. Nested output Category

Product có Category với internalSupplierNotes. Thiết kế CategoryBriefResponse chỉ có id/name. Tại sao không nhúng Category entity trực tiếp vào ProductDetailResponse?

### Bài 16. Vòng tham chiếu JPA

Category.products và Product.category là quan hệ hai chiều. Nếu serializer duyệt entities, có thể gây vòng/SQL nào? Thiết kế nested DTO loại bỏ cycle.

### Bài 17. LazyInitializationException

Controller trả Product entity sau transaction, serializer gọi getImages(). Nêu những lỗi có thể xảy ra. Sửa bằng fetch plan/projection/DTO mapping có kiểm soát.

### Bài 18. N+1 trong DTO mapper

Mapper gọi getCategory().getName() cho 1.000 Products. SQL count có thể tăng như thế nào? Đề xuất projection hoặc batch fetching và cách đo.

### Bài 19. JPQL constructor DTO

Viết JPQL select new ProductListItemResponse(p.id,p.name,p.sellingPrice) có tenant/deleted/status filters. Vì sao query không nên select p.internalCost?

### Bài 20. Criteria DTO projection

Dùng CriteriaBuilder.construct để tạo ProductListItemResponse. Tại sao root.get("sellingPrice") là property Java chứ không phải SQL column selling_price?

### Bài 21. Interface projection

Tạo Spring Data interface với getId/getName/getSellingPrice. Nếu thêm nested Category projection, những vấn đề JOIN/lazy nào cần test?

### Bài 22. Sort/filter leak

Public API không trả internalCost nhưng cho sort=internalCost. Việc này có thể làm lộ thông tin gián tiếp không? Thiết kế sort key allowlist.

### Bài 23. Pagination tenant scope

Data query có tenantId predicate, count query không có. API trả total count của tất cả tenants. Đây có phải data leak không? Sửa query consistency.

### Bài 24. Product IDOR

User tenant-a thay URL từ Product#42 sang Product#43 của tenant-b. DTO công khai chỉ có name/price. Đã an toàn chưa? Thiết kế test 403/404 và DB unchanged.

### Bài 25. Property-level permission

User được PRODUCT_READ nhưng không có PRODUCT_COST_READ. Thiết kế hai endpoints khác nhau và kiểm tra caller không thể lấy cost qua bất kỳ response/error path nào.

### Bài 26. JSON unknown fields

Một CreateProductRequest nhận JSON có approved=true. So sánh reject unknown và ignore unknown policies. Trong cả hai trường hợp, điều gì tuyệt đối không được xảy ra ở database?

### Bài 27. PATCH absent và null

Product.description hiện là "mô tả cũ". Gửi PATCH {} và PATCH {"description":null}. Viết expected behavior nếu API dùng JSON Merge Patch semantics. Plain nullable record có giữ được khác biệt không?

### Bài 28. JSON Patch path allowlist

Client gửi replace /sellingPrice, /tenantId, /deleted. Operation nào có thể được phép ở public endpoint đổi giá? Thiết kế path validation và service.

### Bài 29. Domain invariant sau PATCH

Product ACTIVE có price=100. Client PATCH sellingPrice=0. @PositiveOrZero vẫn pass. Domain cần chặn ở đâu, và response nên biểu diễn lỗi thế nào?

### Bài 30. Version và ETag

Product hiện version=8, client gửi expectedVersion=7. Nên ghi entity.version=7 hay trả precondition/conflict? Giải thích vai trò @Version ở flush/commit.

### Bài 31. Concurrent duplicate SKU

Hai requests cùng SKU đều qua DTO validation và existsBySku pre-check. Vì sao DB UNIQUE vẫn bắt buộc? Thiết kế error DTO an toàn khi lỗi xảy ra tại commit.

### Bài 32. Mã lỗi và SQL leakage

Hibernate exception chứa table name, constraint và SKU. API nên trả những fields nào trong ApiError? Những gì chỉ nên nằm trong logs bảo mật?

### Bài 33. Bean Validation invalidValue

Request chứa password/token sai định dạng. Error handler serialize ConstraintViolation object gồm invalidValue. Rủi ro gì? Thiết kế FieldErrorDto với field/code/message.

### Bài 34. RegisterUserRequest và UserProfileResponse

User entity có passwordHash và resetTokenHash. Thiết kế DTO đăng ký và DTO trả profile. Tại sao ngay cả admin API không nên mặc nhiên trả passwordHash?

### Bài 35. Password policy

Client gửi password plaintext trong RegisterUserRequest. Service phải làm gì trước lưu? Vì sao không thể dựa vào DTO record immutable để bảo vệ plaintext trong logs/memory?

### Bài 36. MapStruct allowlist

Viết interface ProductApiMapper dùng @BeanMapping(ignoreByDefault=true) và chỉ map id/name/sku/sellingPrice. Nếu Product thêm internalCost mới, output có tự lộ không?

### Bài 37. MapStruct @MappingTarget

Một mapper cập nhật entity từ generic ProductUpdateDto. Nêu rủi ro id/tenantId/status bị ghi. Đề xuất tách domain methods hoặc explicit mappings.

### Bài 38. Client gửi URL

ProductImageRequest chứa imageUrl. Nếu server tải URL do user cung cấp, cần bảo vệ những gì (SSRF, scheme/host, network restrictions)? DTO tự kiểm tra được hay cần policy/service?

### Bài 39. DTO trong event

Một service publish toàn bộ Product entity lên Kafka. Khi thêm internalCost hoặc token field, consumer có thể nhận gì? Thiết kế ProductCreatedEventV1 chỉ có fields cần thiết.

### Bài 40. Outbox và transaction

Service persist Product, publish event, sau đó DB UNIQUE lỗi và rollback. Consumer thấy event như thế nào? Đề xuất outbox ghi event DTO cùng transaction và idempotent consumer.

### Bài 41. Cache cross-tenant

Product#42 của tenant-a có Public DTO và Admin DTO. Cache chỉ dùng key 42 có thể tạo lỗi gì? Đề xuất cache scoping theo tenant/audience/permission/version.

### Bài 42. Schema evolution

JPA entity đổi tên internal column và thêm một field mới. API public không cần thay đổi. Giải thích cách DTO tách API contract khỏi schema migrations.

### Bài 43. Error path lộ entity

Success GET trả DTO an toàn, nhưng catch block trả exception.getMessage chứa SQL/internal field. Viết safe error response và test không có raw SQL/stack trace.

### Bài 44. Test chống overposting

Dùng MockMvc gửi tenantId=tenant-victim, internalCost=0, status=ACTIVE vào CreateProductRequest. Trình bày hai expected outcomes khi parser reject hoặc ignore unknown; test DB states trong cả hai trường hợp.

### Bài 45. Thiết kế API Product hoàn chỉnh

Thiết kế hệ thống với:
1. CreateProductRequest;
2. UpdateProductPriceRequest;
3. RenameProductRequest;
4. ProductPublicResponse;
5. ProductManagementResponse;
6. ProductCostResponse;
7. Entity Product có @Version, tenantId, internalCost;
8. Service authorization trên tenant/object/action;
9. DTO mapper allowlist hoặc projection;
10. PATCH semantics absent/null/value;
11. Database UNIQUE/CHECK/FK;
12. Error DTO an toàn;
13. Auditing/outbox event DTO;
14. HTTP/unit/integration security tests.

Yêu cầu giải thích **vì sao mỗi DTO chỉ có những fields đã chọn**, không chỉ liệt kê class signatures.

## 30. Checklist thiết kế DTO an toàn trong ứng dụng JPA

### 30.1. Chọn đúng mô hình và dữ liệu

1. **Entity có đang bị dùng trực tiếp làm @RequestBody không?**
2. **Entity có đang bị trả trực tiếp từ controller không?**
3. **Có tách input DTO và output DTO theo mục đích không?**
4. **Có DTO riêng cho public/admin/finance nếu audience khác không?**
5. **Fields trong mỗi DTO có được chọn theo nhu cầu thật không?**
6. **Có tránh dùng một FullEntityDto chứa mọi property không?**
7. **Có nhận ra DTO là API contract, không phải JPA managed entity không?**
8. **Có tránh đưa entity associations/proxies trực tiếp vào DTO không?**
9. **Có explicit schema/versioning cho external events không?**
10. **Khi entity thêm field nhạy cảm, DTO có mặc nhiên không đổi không?**

### 30.2. Input và mass assignment

11. **Request DTO có bỏ id/tenantId/internalCost/role/deleted/version khi client không được ghi không?**
12. **TenantId có đến từ authenticated context thay vì JSON không?**
13. **Actor/approvedBy có lấy từ server identity thay vì request không?**
14. **Có dùng allowlist mapping thay vì blanket property copy không?**
15. **Nếu dùng MapStruct, các mappings được kiểm soát rõ không?**
16. **Có tránh merge detached entity từ raw request chỉ để update một field không?**
17. **Có load managed entity trước khi gọi domain method không?**
18. **Có tách endpoints cho đổi giá, đổi tên, activate và delete không?**
19. **Unknown JSON property policy có được định nghĩa/test không?**
20. **Frontend ẩn field có bị coi nhầm là security control không?**
21. **Có hạn chế nested object/array sizes để chống resource exhaustion không?**
22. **Có tránh gửi nested entity graph từ client rồi cascade/merge không?**

### 30.3. Authorization theo object, property, relationship

23. **Có xác thực principal/caller cho mỗi endpoint không?**
24. **Có kiểm tra permission trên từng operation không?**
25. **Có check ownership/tenant trước khi trả object không?**
26. **Repository query có tenant/soft-delete/visibility predicates không?**
27. **Có chống IDOR khi caller tự thay path ID không?**
28. **Có permission riêng cho internalCost hay dữ liệu nhạy cảm không?**
29. **Có tránh expose tồn tại tài nguyên tenant khác qua lỗi không?**
30. **Khi nhận categoryId/supplierId, có scope lookup theo tenant không?**
31. **Có kiểm tra quyền đối với mọi nested reference được thay đổi không?**
32. **Có chính sách chuyển ownership/tenant như use case riêng không?**
33. **Có tránh dùng annotation @Column(updatable=false) thay authorization không?**
34. **Có xét concurrent changes giữa pre-check và commit không?**

### 30.4. Validation và domain rules

35. **Có dùng @Valid hoặc Validator cho request DTO thích hợp không?**
36. **Có dùng @NotBlank, @NotNull, @PositiveOrZero, @Digits đúng không?**
37. **Có kết hợp Bean Validation với database constraints không?**
38. **Có định nghĩa normalization SKU/email và DB collation không?**
39. **Có kiểm tra cross-field/cross-state invariants sau update không?**
40. **Có phân biệt validation với access control không?**
41. **Có tránh log invalidValue/secret trong validation error không?**
42. **Có chọn money scale/rounding policy rõ ràng không?**
43. **Có ràng buộc kích thước request/collections/nesting không?**
44. **Có kiểm tra category/reference thuộc tenant trước khi gán association không?**

### 30.5. Output, serialization và hiệu năng

45. **Output DTO có liệt kê explicit readable fields không?**
46. **Có không trả passwordHash/resetTokenHash/API secrets không?**
47. **Có tránh serialize managed JPA entity graph không?**
48. **Có tránh circular references ở nested DTOs không?**
49. **Có query/fetch plan phù hợp với response shape không?**
50. **Có đo N+1 khi mapper truy cập lazy relations không?**
51. **Có dùng DTO projection cho list/report khi phù hợp không?**
52. **DTO projection query có tenant/visibility predicate không?**
53. **Count query của pagination có cùng security scope không?**
54. **Có whitelist public sort/filter keys không?**
55. **Có phân trang/giới hạn nested collections không?**
56. **Có kiểm tra output serialization bằng ObjectMapper production không?**
57. **Có tránh dùng Open Session in View chỉ để khắc phục trả entity không?**

### 30.6. PATCH, PUT và concurrency

58. **Có quy định PATCH semantics absent/null/value rõ không?**
59. **Plain nullable DTO có làm mất presence information không?**
60. **JSON Patch paths có allowlist không?**
61. **JSON Merge Patch có chặn internal fields không?**
62. **PUT chỉ replace writable fields chứ không phải toàn entity không?**
63. **ExpectedVersion/If-Match có được xử lý như precondition không?**
64. **Có tránh client gán trực tiếp JPA @Version không?**
65. **Có xử lý OptimisticLockException ở flush/commit không?**
66. **Có tránh retry stale detached snapshot vô điều kiện không?**
67. **Có database UNIQUE cho business keys để chống race không?**

### 30.7. Errors, audit và dữ liệu nhạy cảm

68. **Error response có stable code/field/requestId không?**
69. **Có tránh public response chứa raw SQL/stack trace/provider class không?**
70. **Có phân loại constraint error theo context thay vì trả 400 cho mọi lỗi không?**
71. **Có redaction cho HTTP logs, validation values và tracing không?**
72. **Có audit những thay đổi nhạy cảm theo actor server-side không?**
73. **Có tránh publish event trước commit hoặc dùng outbox không?**
74. **Event payload có version và data minimization không?**
75. **Có bảo vệ URLs/tokens trong nested response không?**
76. **Có security policy cho stored/cached DTOs không?**
77. **Cache key có tenant, audience và permission scope khi cần không?**

### 30.8. Kiểm thử và vận hành

78. **Có unit tests Bean Validation và mapper fields không?**
79. **Có JSON serialization test cho public DTO không?**
80. **Có HTTP overposting tests với extra fields không?**
81. **Có negative IDOR tests với hai tenants không?**
82. **Có property-level permission tests cho internalCost không?**
83. **Có PATCH absent/null/path tests không?**
84. **Có nested reference cross-tenant tests không?**
85. **Có JPA integration test bảo đảm fields ngoài DTO không bị sửa không?**
86. **Có test concurrency UNIQUE và @Version không?**
87. **Có DB migration tests cho NOT NULL/CHECK/FK/UNIQUE không?**
88. **Có tests cho pagination count/filter scope không?**
89. **Có query count/N+1 tests khi cần không?**
90. **Có kiểm tra error JSON không lộ SQL/PII không?**
91. **Có tests cho event/outbox không chứa entity secrets không?**
92. **Có test cache hit không leak management DTO sang public caller không?**
93. **Có review breaking API changes khi entity/refactor không?**
94. **Có giới hạn request bodies và nested graph depth không?**
95. **Có một nơi ownership rõ cho authorization/data visibility decisions không?**

## 31. Cây quyết định sử dụng Input/Output DTO

~~~text
              Một API JPA cần đọc hoặc ghi dữ liệu
                            |
                            v
                 Input từ client hay output?
                        /          \
                      Input        Output
                        |             |
                        v             v
              Chọn use case    Chọn audience
              cụ thể           public/admin/finance
                        |             |
                        v             v
              Request DTO       Response DTO
              writable fields   readable fields
                        |             |
                        v             v
              Bind + validate   Authorized query
                        |             |
                        v             v
              Authentication    Tenant/row scope
              + authorization           |
                        |               v
                        v        DTO projection
             Load managed        hoặc entity→mapper
             entity đúng tenant         |
                        |               v
                        v        Không serialize
             Domain methods       raw JPA entity
                        |               |
                        +-------+-------+
                                |
                                v
                      Transaction/DB constraints
                                |
                                v
                     Safe error/response contract
                                |
                                v
                       Security regression tests
~~~

## 32. Bảng tra cứu nhanh theo tình huống

| Tình huống | Input DTO | Output DTO | Lưu ý bảo mật |
|---|---|---|---|
| Tạo Product | CreateProductRequest | ProductPublicResponse | Tenant server-side |
| Đổi giá bán | UpdateProductPriceRequest | ProductPublicResponse | Permission đổi giá |
| Đổi tên | RenameProductRequest | ProductPublicResponse | Chỉ name writable |
| Kích hoạt Product | Action request hoặc body nhỏ | ProductManagementResponse | Domain transition/permission |
| Xem list public | Không cần | ProductListItemResponse | Tenant/status filters |
| Xem detail public | Không cần | ProductDetailResponse | Nested brief DTO |
| Xem giá vốn | Không cần | ProductCostResponse | PRODUCT_COST_READ |
| Admin điều chỉnh | Admin request theo command | Management DTO | Audit và role |
| Gán Category | Category ID request | Product detail DTO | Cross-tenant reference check |
| Đăng ký user | RegisterUserRequest | UserProfileResponse | Không trả passwordHash |
| Đổi mật khẩu | ChangePasswordRequest | Empty/success response | Không log secret |
| PATCH description | Presence-aware patch DTO | Product detail DTO | Absent/null semantics |
| Concurrency update | Expected version/If-Match | Version/ETag nếu cần | JPA @Version |
| Async publish | Command/event data | ProductCreatedEventV1 | Không publish entity |
| Report/export | Filters DTO | Dedicated export DTO | Row/field authorization |
| Error | Không áp dụng | ApiError | Không lộ SQL/PII |

## 33. Tổng kết

**Dùng DTO cho dữ liệu nhận vào và dữ liệu trả ra** là một biện pháp thiết kế quan trọng khi xây dựng API với JPA, đặc biệt đối với các entity có nhiều fields nội bộ, quan hệ phức tạp hoặc dữ liệu đa tenant.

### 33.1. Bốn ranh giới cần nhớ

1. **Input boundary:** Chỉ nhận fields client được phép cung cấp. Create/Update/PATCH dùng DTO phù hợp với từng use case, không bind nguyên Product entity và không copy mọi field vào managed state.
2. **Authorization boundary:** Xác thực caller, kiểm tra tenant/resource/action/property permissions. DTO không tự ngăn IDOR/BOLA và không thay domain rules.
3. **Persistence boundary:** Entity JPA, @Version, relationships, dirty checking, database constraints và transaction lifecycle vẫn có trách nhiệm riêng; input DTO không tự thay UNIQUE/FK/CHECK hoặc optimistic locking.
4. **Output boundary:** Chỉ trả readable fields qua explicit response DTO/projection. Không serialize entity graph hoặc sensitive fields theo mặc định.

### 33.2. Ví dụ ngắn

Input:

~~~java
public record CreateProductRequest(
    @NotBlank String name,
    @NotBlank String sku,
    @NotNull @PositiveOrZero BigDecimal sellingPrice
) {}
~~~

Server-side creation:

~~~java
Product product = new Product(
    authorizedTenantId,
    request.name(),
    request.sku(),
    request.sellingPrice(),
    trustedInternalCost,
    clock.instant()
);
~~~

Output:

~~~java
public record ProductPublicResponse(
    Long id,
    String name,
    String sku,
    BigDecimal sellingPrice
) {}
~~~

Mapping:

~~~java
return new ProductPublicResponse(
    product.getId(),
    product.getName(),
    product.getSku(),
    product.getSellingPrice()
);
~~~

Những fields như tenantId, internalCost, status, deleted hoặc @Version không được client sửa chỉ vì chúng tồn tại trong entity. Nếu API quản trị cần xem hoặc thao tác chúng, phải có **DTO/use case và authorization riêng**.

### 33.3. DTO không phải lớp bảo mật duy nhất

~~~text
JSON/Request
   |
   v
Input DTO allowlist
   |
   v
Bean Validation + size limits
   |
   v
Authentication + authorization
   |
   v
Domain methods + invariants
   |
   v
JPA Entity + DB constraints + transaction
   |
   v
Authorized query / explicit projection
   |
   v
Output DTO allowlist
   |
   v
Safe JSON/API response
~~~

Nếu thiếu authorization, DTO vẫn có thể lộ dữ liệu của người khác. Nếu thiếu domain rules, DTO hợp lệ có thể tạo trạng thái nghiệp vụ sai. Nếu thiếu database constraints, SQL writers ngoài JPA có thể làm hỏng dữ liệu. Nếu thiếu tests, một refactor hoặc mapper config mới có thể đưa field nhạy cảm trở lại response.

**Nguyên tắc cuối cùng:** **Entity mô tả dữ liệu được lưu và vòng đời persistence; Input DTO mô tả dữ liệu caller được phép yêu cầu thay đổi; Output DTO mô tả dữ liệu caller được phép nhận.** Ba hợp đồng này nên được thiết kế rõ ràng, phối hợp authorization, domain validation, JPA/SQL constraints và kiểm thử bảo mật để tránh overposting, dữ liệu bị lộ và phụ thuộc không cần thiết vào ORM internals.






















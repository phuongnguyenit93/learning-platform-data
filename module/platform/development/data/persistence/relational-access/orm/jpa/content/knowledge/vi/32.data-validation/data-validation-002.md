# Tích hợp Bean Validation với vòng đời JPA

Trong ứng dụng Java dùng Jakarta Persistence (JPA), entity không chỉ là một object được ánh xạ xuống bảng cơ sở dữ liệu. Nó còn mang các quy tắc về dữ liệu hợp lệ: mã sản phẩm không được rỗng, giá không được âm, tên có giới hạn độ dài, ngày kết thúc phải sau ngày bắt đầu, hoặc một đơn hàng chỉ được xác nhận khi đã có thông tin cần thiết.

**Jakarta Bean Validation** cung cấp cách mô tả những quy tắc này bằng annotation như `@NotNull`, `@NotBlank`, `@Size`, `@Positive`, `@DecimalMin`, `@Valid` và các constraint tùy chỉnh. Khi có Bean Validation provider và tích hợp được bật, **JPA có thể tự thực hiện validation tại các sự kiện vòng đời entity** trước những thao tác ghi dữ liệu tương ứng.

Ví dụ:

```java
import jakarta.persistence.*;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;

@Entity
@Table(name = "catalog_product")
public class CatalogProduct {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotBlank
    @Size(max = 64)
    @Column(nullable = false, length = 64)
    private String sku;

    @NotBlank
    @Size(max = 200)
    @Column(nullable = false, length = 200)
    private String name;

    @NotNull
    @DecimalMin("0.00")
    @Digits(integer = 12, fraction = 2)
    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    @Version
    private Long version;

    protected CatalogProduct() {
    }

    // Constructor, getters và phương thức nghiệp vụ
    // được bổ sung ở ví dụ đầy đủ phía dưới.
}
```

Nếu ứng dụng tạo một `CatalogProduct` có `name` chỉ chứa dấu cách hoặc `price` âm, Bean Validation có thể phát hiện vi phạm khi JPA chuẩn bị thực hiện INSERT/UPDATE. Ứng dụng nhận thông tin về các constraints vi phạm, thay vì chỉ chờ database báo lỗi cột hoặc một giá trị bất hợp lệ đi sâu vào hệ thống.

Tuy nhiên, cần phân biệt rõ:

- **Bean Validation không phải một transaction manager.**
- **Annotation validation không thay database constraints.**
- **Mỗi lần gọi setter không tự kích hoạt JPA lifecycle validation.**
- **`persist`, `merge` hay `remove` không đồng nghĩa validation chắc chắn xảy ra ngay tại dòng code đó.**
- **Bulk JPQL/Criteria DML và native SQL không đi qua toàn bộ entity lifecycle validation.**
- **Một entity hợp lệ về hình dạng dữ liệu chưa chắc hợp lệ về quy tắc nghiệp vụ trong môi trường đồng thời.**

Bài học thuộc chương **Kiểm tra dữ liệu** của module *Data Persistence Relational Access ORM JPA*, tập trung vào cách Bean Validation gắn với **`pre-persist`, `pre-update` và `pre-remove`**, thời điểm `flush`/`commit`, validation groups, cascading, transaction rollback và kiểm thử thực tế.

> **Tư duy xuyên suốt:** Bean Validation giúp phát hiện **vi phạm constraints trên entity state** tại các ranh giới phù hợp. Nhưng tính đúng đắn của dữ liệu cuối cùng vẫn cần **domain rules, database constraints và transaction/concurrency control** phối hợp.

---

## 1. Mục tiêu học tập

Sau khi học xong, bạn có thể:

1. Phân biệt Bean Validation, JPA mapping constraints, database constraints và domain validation.
2. Khai báo các constraints chuẩn trên persistent fields/properties của entity.
3. Hiểu **khi nào JPA tự validate entity** tại sự kiện pre-persist, pre-update, pre-remove.
4. Phân biệt validation ở `persist`/`merge` với thời điểm thực thi `flush`/`commit`.
5. Cấu hình `ValidationMode.AUTO`, `CALLBACK` và `NONE`.
6. Cấu hình **validation groups** theo pre-persist, pre-update, pre-remove và dùng groups có chủ đích.
7. Hiểu cách `@Valid` kích hoạt cascading validation, khác với JPA cascade persist/merge/remove.
8. Viết custom constraint/`ConstraintValidator` và biết khi nào nên dùng class-level constraint.
9. Đọc `jakarta.validation.ConstraintViolationException` và thông tin từng violation.
10. Xử lý rollback đúng khi validation thất bại, không tiếp tục transaction lỗi.
11. Biết vì sao bulk JPQL/Criteria/native SQL không tự chạy entity-level validation.
12. Thiết kế các lớp kiểm tra ở API, service/domain, entity lifecycle và database.
13. Kiểm thử bằng Validator trực tiếp và bằng JPA thật với hai transaction/EntityManager.
14. Tránh những anti-pattern như validation truy vấn DB bên trong callback, mặc định UNIQUE được Bean Validation bảo đảm, hoặc đặt constraint trên giá trị chỉ được database tạo ra sau INSERT.

---

## 2. Bean Validation là gì và nằm ở đâu trong kiến trúc?

Bean Validation là một đặc tả để diễn đạt, kiểm tra và báo cáo constraints của Java objects. API chuẩn nằm trong namespace:

```java
jakarta.validation.*
jakarta.validation.constraints.*
```

Một số thành phần quan trọng:

| Thành phần | Vai trò |
|---|---|
| `@NotNull` | Giá trị không được `null` |
| `@NotBlank` | Chuỗi ký tự không được null hoặc chỉ chứa khoảng trắng |
| `@NotEmpty` | Chuỗi, collection, map hoặc array không được rỗng |
| `@Size` | Giới hạn độ dài/kích thước |
| `@Positive`, `@PositiveOrZero` | Ràng buộc số dương/không âm |
| `@DecimalMin`, `@DecimalMax` | Giới hạn số theo biểu diễn thập phân |
| `@Digits` | Giới hạn số chữ số phần nguyên/phần lẻ |
| `@Past`, `@Future` | Ràng buộc thời gian |
| `@Email`, `@Pattern` | Kiểm tra định dạng chuỗi |
| `@AssertTrue`, `@AssertFalse` | Ràng buộc boolean |
| `@Valid` | Cascading validation vào đối tượng/thành phần chứa |
| `Validator` | API chủ động kiểm tra Java objects |
| `ConstraintValidator` | Logic triển khai custom constraint |
| `ConstraintViolation` | Thông tin một vi phạm |
| `ConstraintViolationException` | Exception mang tập violations |
| Validation groups | Chọn bộ constraints cần kiểm tra ở ngữ cảnh cụ thể |

Khi dùng với JPA, Bean Validation có thể được **JPA provider gọi tự động** trong lifecycle events nếu tích hợp khả dụng và không bị tắt.

### 2.1. Bốn lớp kiểm tra cần tách biệt

```text
HTTP / API Boundary
    |
    +-- Request DTO validation
    |   @Valid, @NotBlank, @Size...
    |
    v
Application / Domain Layer
    |
    +-- Business invariants
    |   Có được chuyển trạng thái?
    |   Có đủ tồn kho? Có quyền sửa?
    |
    v
JPA Entity Lifecycle
    |
    +-- Bean Validation trước INSERT/UPDATE/DELETE
    |   theo mode và groups đã cấu hình
    |
    v
Relational Database
    |
    +-- NOT NULL, UNIQUE, CHECK, FOREIGN KEY
    +-- Locks, isolation, transaction commit
```

Cùng một quy tắc có thể xuất hiện ở nhiều lớp, nhưng **không phải bản sao chức năng thừa**:

- DTO validation cho phản hồi sớm và thông báo thân thiện.
- Domain validation bảo vệ **quyết định nghiệp vụ**.
- JPA lifecycle validation là lớp chặn thêm trước entity-level writes.
- Database constraints bảo vệ dữ liệu khỏi **mọi writer**, gồm cả raw SQL, batch jobs và dịch vụ ngoài JPA.

### 2.2. “Valid object” không đồng nghĩa “valid transaction”

Một entity Product có `@Positive price` và `@NotBlank name` có thể hợp lệ hoàn toàn, nhưng hai transactions đồng thời trừ tồn kho dựa trên snapshot cũ vẫn làm oversell. Bean Validation không thay `@Version`, atomic conditional UPDATE, pessimistic locking hoặc database isolation.

### 2.3. “Valid request” không đồng nghĩa “valid persistent entity”

Request DTO có thể hợp lệ ở đầu HTTP request, nhưng service có thể gán thêm giá trị từ database, merge nested entities hoặc thay đổi state trước khi flush. Lifecycle validation giúp kiểm tra **entity state thực tế được đưa tới persistence pipeline**, không chỉ input ban đầu.

---

## 3. Chuẩn Jakarta Validation và provider thực thi

Phân biệt hai phần:

1. **Jakarta Validation API**: annotation và interfaces chuẩn, ví dụ `jakarta.validation.Validator`.
2. **Validation provider**: implementation thực thi constraints, ví dụ Hibernate Validator.

Có API jar thôi **chưa đồng nghĩa** đã có provider hoàn chỉnh được JPA tích hợp.

### 3.1. Với Spring Boot

Một tổ hợp điển hình:

```text
spring-boot-starter-data-jpa
spring-boot-starter-validation
Database JDBC driver
```

Trong một dự án Maven dùng dependency management của Spring Boot, các dependency có thể được khai báo:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
</dependencies>
```

Đây là ví dụ để hiểu thành phần cần có, **không phải hướng dẫn ép một phiên bản thư viện cụ thể**. Dự án cần khớp namespace `jakarta.*` hoặc `javax.*` với phiên bản Spring/JPA đang dùng.

### 3.2. Với JPA độc lập

Cần:

- Jakarta Persistence provider.
- Jakarta Validation API.
- Bean Validation provider.
- Các dependency mà provider cần.
- Persistence unit/datasource/transaction manager.
- Configuration cho validation mode và groups nếu không dùng mặc định.

Ví dụ tọa độ Maven có thể gồm:

```xml
<dependency>
    <groupId>jakarta.validation</groupId>
    <artifactId>jakarta.validation-api</artifactId>
</dependency>

<dependency>
    <groupId>org.hibernate.validator</groupId>
    <artifactId>hibernate-validator</artifactId>
</dependency>
```

Trong Maven không có parent/BOM, dependency versions cần được khai báo hoặc quản lý riêng. Hibernate Validator là **Bean Validation provider**, còn Hibernate ORM là **JPA provider**; chúng là hai nhiệm vụ khác nhau, dù cùng hệ sinh thái tên Hibernate.

### 3.3. Legacy javax vs Jakarta namespace

Dự án JPA cũ có thể dùng:

```java
javax.persistence.*
javax.validation.*
```

Dự án Jakarta hiện đại dùng:

```java
jakarta.persistence.*
jakarta.validation.*
```

Không trộn ngẫu nhiên `javax.validation.constraints.NotNull` với một stack JPA/Validation provider chỉ cấu hình cho `jakarta.validation.*` và kỳ vọng tích hợp đầy đủ.

### 3.4. Không nhầm Hibernate Validator với Hibernate-specific constraints

Ví dụ `@NotNull` nằm trong chuẩn Jakarta Validation. Một constraint provider-specific có thể nằm dưới `org.hibernate.validator.constraints.*`. Muốn code portable, ưu tiên chuẩn trước; khi dùng extension phải ghi rõ dependency/provider/version.

---

## 4. Annotation đặt lên entity như thế nào?

Xét entity `CatalogProduct` tự chứa hơn:

```java
package com.example.catalog.domain;

import jakarta.persistence.*;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(
    name = "catalog_product",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_catalog_product_sku",
            columnNames = "sku"
        )
    }
)
public class CatalogProduct {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotBlank
    @Size(max = 64)
    @Column(name = "sku", nullable = false, length = 64)
    private String sku;

    @NotBlank
    @Size(max = 200)
    @Column(name = "product_name", nullable = false, length = 200)
    private String name;

    @NotNull
    @DecimalMin("0.00")
    @Digits(integer = 12, fraction = 2)
    @Column(
        name = "unit_price",
        nullable = false,
        precision = 14,
        scale = 2
    )
    private BigDecimal price;

    @NotNull
    @Enumerated(EnumType.STRING)
    @Column(name = "product_status", nullable = false)
    private ProductStatus status;

    @NotNull
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @NotNull
    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Version
    @Column(name = "row_version", nullable = false)
    private Long version;

    protected CatalogProduct() {
    }

    public CatalogProduct(
            String sku,
            String name,
            BigDecimal price
    ) {
        this.sku = sku;
        this.name = name;
        this.price = price;
        this.status = ProductStatus.DRAFT;
    }

    @PrePersist
    void beforeInsert() {
        Instant now = Instant.now();

        if (createdAt == null) {
            createdAt = now;
        }

        updatedAt = now;
    }

    @PreUpdate
    void beforeUpdate() {
        updatedAt = Instant.now();
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public ProductStatus getStatus() {
        return status;
    }

    public Long getVersion() {
        return version;
    }

    public void rename(String nextName) {
        this.name = nextName;
    }

    public void changePrice(BigDecimal nextPrice) {
        this.price = nextPrice;
    }

    public void publish() {
        if (status != ProductStatus.DRAFT) {
            throw new IllegalStateException(
                "Only drafts can be published"
            );
        }

        status = ProductStatus.PUBLISHED;
    }
}
```

Enum:

```java
public enum ProductStatus {
    DRAFT,
    PUBLISHED,
    ARCHIVED
}
```

### 4.1. Tại sao vẫn có domain methods dù đã @NotBlank/@DecimalMin?

Annotation mô tả những giá trị hợp lệ. Domain methods có thể thực hiện logic chuyển trạng thái: chỉ DRAFT mới được PUBLISHED, một sản phẩm đã ARCHIVED không được sửa giá tùy ý, hoặc phải có ảnh trước khi publish.

Ví dụ `publish` kiểm tra trạng thái; `@NotBlank` không biết workflow state machine đó.

### 4.2. Có cần setter public cho mọi field?

Không. Với field access, JPA có thể quản lý persistent fields mà không cần public setters. Hạn chế setters giúp tầng application không thay đổi entity vượt qua domain methods; Bean Validation không thay thế encapsulation.

### 4.3. Tại sao createdAt có @NotNull dù constructor không gán?

Ví dụ dùng `@PrePersist` để điền giá trị trước INSERT. Trong tích hợp JPA–Bean Validation thông thường, entity lifecycle callbacks được xử lý trong pipeline tương ứng trước khi automatic validation kiểm tra entity state chuẩn bị ghi. Vì vậy `createdAt` được khởi tạo trước validation ở sự kiện ghi. Tuy nhiên **đừng tự suy luận tương tự cho database defaults chạy sau INSERT**.

### 4.4. Cẩn thận clock và audit

`Instant.now()` ở application node có thể khác database clock. Nếu nghiệp vụ yêu cầu thời gian nguồn DB hoặc monotonic ordering, cần strategy audit khác. `@PreUpdate` không thay database trigger và không tự chạy trên bulk JPQL/native SQL updates.

---

## 5. JPA lifecycle và thời điểm validation

Một entity trải qua những trạng thái chính:

```text
Transient / New
       |
       | persist()
       v
Managed (new entity)
       |
       | flush / INSERT
       | -> pre-persist lifecycle pipeline
       | -> Bean Validation nếu bật
       | -> INSERT
       v
Managed + persistent
       |
       | thay đổi fields
       v
Managed + dirty
       |
       | flush / UPDATE
       | -> pre-update lifecycle pipeline
       | -> Bean Validation nếu bật
       | -> UPDATE
       v
Managed + synchronized
       |
       | remove()
       v
Removed
       |
       | flush / DELETE
       | -> pre-remove lifecycle pipeline
       | -> Bean Validation chỉ theo groups được cấu hình
       | -> DELETE
       v
Database row deleted
```

Sơ đồ trên mô tả **ngữ nghĩa và các điểm tích hợp**, không ấn định chính xác mọi callback chạy tại một dòng API cố định. Ví dụ `@PrePersist` có thể được provider gọi trong lúc `persist`, còn INSERT có thể diễn ra trước/sau flush tùy ID generation strategy và provider. Việc automatic validation có thể được quan sát ở `flush` hoặc `commit` thay vì ngay tại `persist`.

### 5.1. Ba sự kiện validation liên quan

| Sự kiện | Entity operation | Groups mặc định khi có Bean Validation integration |
|---|---|---|
| **pre-persist** | Chuẩn bị INSERT entity | `jakarta.validation.groups.Default` |
| **pre-update** | Chuẩn bị UPDATE entity | `jakarta.validation.groups.Default` |
| **pre-remove** | Chuẩn bị DELETE entity | **Không có groups** mặc định |

Đây là điểm quan trọng: **JPA thường không tự áp các Default constraints cho thao tác xóa**. Việc này hợp lý vì dữ liệu cũ không hợp lệ vẫn cần có thể được xóa để làm sạch hệ thống.

### 5.2. Pre-persist: kiểm tra entity mới

Nếu gọi:

```java
CatalogProduct product = new CatalogProduct(
    "BOOK-JPA",
    "  ",
    new BigDecimal("-10.00")
);

em.persist(product);
em.flush();
```

automatic validation có thể phát hiện:

- `name` vi phạm `@NotBlank`.
- `price` vi phạm `@DecimalMin("0.00")`.

Provider không nên đưa một entity vi phạm constraints đã bật vào database qua entity-level insert như thể nó hợp lệ.

### 5.3. Pre-update: kiểm tra state chuẩn bị UPDATE

```java
CatalogProduct product =
    em.find(CatalogProduct.class, productId);

product.rename("");
em.flush();
```

Nếu entity được nhận là dirty và provider chuẩn bị UPDATE, pre-update validation kiểm tra state có `name=""` và có thể ném violation exception trước khi UPDATE.

### 5.4. Pre-remove: mặc định không chạy Default group

```java
CatalogProduct product =
    em.find(CatalogProduct.class, productId);

em.remove(product);
em.flush();
```

Default constraints như `@NotBlank name` không được bật mặc định cho pre-remove. Nếu business cần ngăn xóa sản phẩm đã PUBLISHED hoặc đã có orders, không nên mặc định Bean Validation sẽ chặn; cần domain/service guard và DB FK constraints phù hợp.

### 5.5. Post-persist/update/remove không phải mặc định các điểm Bean Validation

JPA có `@PostPersist`, `@PostUpdate`, `@PostRemove` cho entity lifecycle callbacks, nhưng automatic validation integration theo các groups cấu hình được gắn với pre-persist, pre-update, pre-remove, **không phải cứ mỗi post callback sẽ chạy lại toàn bộ constraints**.

### 5.6. Không phải mọi setter đều phát sinh pre-update

```java
product.rename("New name");
product.rename("Newer name");
```

Hai lần gọi setter không có nghĩa validate hai lần. JPA validation thường gắn với provider chuẩn bị một UPDATE ở flush, chứ không phải method interceptor trên mọi setter.

---

## 6. Persist: validation có nhất thiết xảy ra ngay khi gọi em.persist không?

**Không nên phụ thuộc vào điều đó.**

```java
CatalogProduct product = new CatalogProduct(
    "BOOK-1",
    "",
    new BigDecimal("-5")
);

em.persist(product);
// Có provider chưa gửi INSERT và chưa ném validation exception tại đây.

em.flush();
// Đây thường là điểm có thể quan sát validation failure.
```

Tùy provider và ID generation strategy:

- `persist` chuyển entity sang managed state.
- `@PrePersist` callback có thể chạy sớm.
- INSERT có thể xảy ra theo lifecycle/ID generation timing.
- Bean Validation được thực hiện trong pipeline ghi theo mode/groups.
- Exception có thể được ném ở persist, flush hoặc transaction commit.

### 6.1. Vì sao test nên chủ động flush?

Nếu test muốn khẳng định integration pre-persist validation hoạt động, nên **buộc một đồng bộ trước khi assert**:

```java
tx.begin();

em.persist(invalidProduct);

assertThrows(
    ConstraintViolationException.class,
    () -> em.flush()
);
```

Mẫu này phù hợp khi target provider thực hiện validation ở flush; ở một stack có INSERT/validation sớm trong `persist`, test cần đặt khối kiểm tra quanh **persist + flush** hoặc theo behavior đã kiểm chứng. Không viết test cứng dựa vào một timing mà spec/provider không cam kết giống nhau trong mọi trường hợp.

### 6.2. Flush không phải commit

`em.flush()` có thể thực hiện validation/INSERT/UPDATE trong DB transaction, nhưng transaction vẫn có thể rollback. Validation pass không đồng nghĩa business operation đã commit thành công.

### 6.3. Nếu em.persist một entity hợp lệ rồi sửa thành không hợp lệ trước flush?

```java
CatalogProduct product = new CatalogProduct(
    "BOOK-1",
    "Java Persistence",
    new BigDecimal("30.00")
);

em.persist(product);
product.rename(" ");
em.flush();
```

Điều quan trọng là **entity state tại lifecycle validation point** và thao tác mà provider thực hiện. Không chỉ kiểm tra snapshot từ lúc constructor/persist rồi tin state sẽ giữ nguyên.

---

## 7. Merge: detached entity được validate ở đâu?

`EntityManager.merge` không làm detached instance tự trở thành managed. Nó copy state vào một managed instance được trả về, theo JPA semantics.

```java
CatalogProduct managedCopy =
    em.merge(detachedProduct);
```

Nếu detached product có invalid values:

- Vi phạm có thể xuất hiện khi merge/flush/commit tùy event/implementation.
- Automatic validation thường được áp lên **entity state được quản lý và chuẩn bị ghi**, không phải “mỗi lần gọi merge là chạy Validator.validate(detached) trước tiên”.
- Với `@Version`, detached stale state còn có thể gây optimistic conflict độc lập với validation.

### 7.1. Không tiếp tục sửa detached object rồi kỳ vọng JPA theo dõi

```java
CatalogProduct managed = em.merge(detached);
detached.rename("Name after merge");
// Không tự chắc chắn rằng thay đổi này đi vào managed instance.
```

Tiếp tục với `managed` nếu nghiệp vụ cần thêm thay đổi trong persistence context.

### 7.2. Merge có thể copy field bạn không muốn

Nếu client gửi một entity JSON thiếu các fields mà mapper biến thành `null`, merge có thể đưa null vào managed state và trigger validation, hoặc trước đó đã phá domain semantics.

Một cách an toàn hơn trong phần lớn APIs:

1. Nhận request DTO.
2. Validate request DTO.
3. Load managed entity theo ID và quyền.
4. Gọi domain methods chỉ áp những field được cho phép.
5. Để JPA validate state trước ghi.
6. Commit/rollback theo outcome.

### 7.3. Merge không thay expected-version contract

Nếu người dùng sửa bản cũ, `@Version` hoặc một explicit expectedVersion check vẫn cần để phát hiện lost update. Bean Validation chỉ trả lời “state có thỏa constraints không”, không tự biết người dùng đang dựa trên revision cũ.

---

## 8. Remove: vì sao validation mặc định thường không chặn delete?

Giả sử database còn một Product legacy có name rỗng do dữ liệu lịch sử.

Nếu mỗi lần xóa entity đều chạy `@NotBlank` và từ chối, ứng dụng có thể **không thể dọn dữ liệu không hợp lệ**. Vì vậy default mapping thông thường là:

- pre-persist: Default group.
- pre-update: Default group.
- pre-remove: no validation groups.

### 8.1. Khi thực sự cần kiểm tra trước xóa

Ví dụ chỉ cho phép xóa sản phẩm DRAFT chưa có Orders. Đây là **business rule**, có thể xử lý tại service:

```java
@Transactional
public void deleteDraftProduct(long productId) {
    CatalogProduct product =
        em.find(CatalogProduct.class, productId);

    if (product == null) {
        return;
    }

    if (product.getStatus() != ProductStatus.DRAFT) {
        throw new IllegalStateException(
            "Only drafts can be deleted"
        );
    }

    em.remove(product);
}
```

Nếu status có thể được cập nhật đồng thời, cần concurrency strategy như `@Version`, pessimistic lock hoặc atomic conditional DELETE theo domain contract.

### 8.2. Pre-remove group riêng là tùy chọn

JPA cho phép cấu hình validation groups cho pre-remove. Nhưng một constraint như `@NotBlank` không đồng nghĩa business deletion rule. Đừng kích hoạt toàn bộ Default constraints chỉ vì muốn chặn một vài xóa không hợp lệ.

### 8.3. FK constraints vẫn là hàng rào cuối

Nếu Product có các OrderLines tham chiếu và FK không cho delete, database có thể từ chối dù pre-remove validation không chạy. FK và Bean Validation giải quyết hai loại ràng buộc khác nhau.

---

## 9. Các nhóm annotation validation thông dụng

### 9.1. Kiểm tra null/rỗng

| Constraint | Áp dụng điển hình | Điều thực sự kiểm tra |
|---|---|---|
| `@NotNull` | Object reference, giá tiền, enum | Giá trị không phải `null` |
| `@NotBlank` | `CharSequence` | Không null, không chỉ có whitespace |
| `@NotEmpty` | String, collection, map, array | Không null và có kích thước/dài > 0 |
| `@Size(min=..., max=...)` | String, collection, map, array | Độ dài/kích thước nằm trong khoảng; null thường hợp lệ |

Ví dụ:

```java
@NotNull
private String description;
```

cho phép `description=""`. Nếu muốn cấm rỗng/trắng, dùng `@NotBlank` theo kiểu dữ liệu phù hợp.

```java
@NotEmpty
private List<String> tags;
```

chỉ yêu cầu collection không rỗng; nó **không tự kiểm tra mỗi phần tử string không blank**.

### 9.2. Kiểm tra số

```java
@NotNull
@DecimalMin("0.00")
@Digits(integer = 12, fraction = 2)
private BigDecimal price;
```

- `@NotNull` chặn giá trị thiếu.
- `@DecimalMin("0.00")` cho phép 0, không cho âm.
- `@Digits` giới hạn chữ số phần nguyên và phần lẻ.
- `BigDecimal` thích hợp hơn floating point trong nhiều use cases tiền tệ.

Không nhầm `@Digits` với một guarantee database rounding hay currency scale. Database column `precision/scale` và nghiệp vụ làm tròn vẫn cần thiết kế riêng.

### 9.3. Kiểm tra chuỗi định dạng

```java
@NotBlank
@Email
private String email;

@Pattern(regexp = "[A-Z0-9-]{3,32}")
private String sku;
```

`@Email` kiểm tra một số tính chất hình thức, **không xác minh mailbox tồn tại, email đã được kiểm soát hay DNS/MX luôn hợp lệ**. Với regex `@Pattern` cần chú ý hiệu năng của regex và độ dài input.

### 9.4. Kiểm tra ngày giờ

```java
@NotNull
@Future
private Instant campaignStartsAt;

@PastOrPresent
private Instant createdAt;
```

Constraints thời gian dùng nguồn thời gian của Validator provider/context. Nếu nhiều application nodes có clock drift hoặc business rule phụ thuộc DB clock, cần định nghĩa timestamp source và test đúng.

### 9.5. Kiểm tra boolean

```java
@AssertTrue(message = "Terms must be accepted")
private boolean acceptedTerms;
```

Có thể phù hợp với request DTO. Nhưng đừng dùng một field persisted `acceptedTerms` chỉ để mô phỏng trạng thái UI nhất thời nếu không phải domain state cần lưu.

### 9.6. Chỉ đặt @Valid không có nghĩa list phải có phần tử

```java
@Valid
private List<OrderLine> lines;
```

`@Valid` kích hoạt validation các phần tử có thể tiếp cận, nhưng không yêu cầu `lines` khác null hoặc không rỗng. Để bắt buộc có ít nhất một line, thêm `@NotEmpty` hoặc `@Size(min=1)` theo contract.

---

## 10. Bean Validation constraints và JPA @Column: khác nhau thế nào?

Một ví dụ:

```java
@NotBlank
@Size(max = 120)
@Column(name = "product_name", nullable = false, length = 120)
private String name;
```

| Annotation | Loại | Tác dụng chính |
|---|---|---|
| `@NotBlank` | Bean Validation | Kiểm tra blank/null trong Java validation |
| `@Size(max=120)` | Bean Validation | Kiểm tra độ dài object value |
| `@Column(nullable=false)` | JPA mapping/schema hint | Mô tả cột không cho null khi tạo schema, không phải validator thay thế |
| `@Column(length=120)` | JPA mapping/schema hint | Mô tả kích thước cột kiểu chuỗi khi sinh schema |
| `NOT NULL` trong DB | Database constraint | Chặn mọi SQL INSERT/UPDATE có null |
| Giới hạn column length trong DB | Database schema | Có thể chặn/cắt/điều chỉnh quá dài tùy DB/dialect |

### 10.1. @NotNull không đồng nghĩa NOT NULL constraint luôn tồn tại

Bean Validation có thể được dùng ở Java layer kể cả khi database column nullable. Nếu schema được tạo/migrate độc lập, database có thể chưa có NOT NULL dù entity có `@NotNull`.

### 10.2. @Column(nullable=false) không tự phát ConstraintViolation

Nếu bạn chỉ có:

```java
@Column(nullable = false)
private String name;
```

không nên mặc định JPA sẽ ném `jakarta.validation.ConstraintViolationException` cho `name=null`. Database có thể từ chối tại SQL INSERT với một persistence/JDBC exception khác.

### 10.3. @Size(max=120) không tự bảo đảm varchar(120) ở DB

JPA provider/DDL tooling có thể dùng metadata của Bean Validation để hỗ trợ schema generation trong một số integrations, nhưng **không phải thay thế migration/DB constraint review**. Nếu schema đã tồn tại, chỉ thay annotation Java không tự alter table an toàn trong production.

### 10.4. @Column(unique=true) không phải Bean Validation uniqueness check

`@Column(unique = true)` hoặc `@UniqueConstraint` mô tả schema uniqueness. Không có một built-in `@Unique` portable trong Jakarta Validation tự làm database-level atomic uniqueness. Unique constraint phải có ở DB và được kiểm tra khi ghi.

---

## 11. Automatic validation mode: AUTO, CALLBACK, NONE

JPA cho phép cấu hình validation mode của persistence unit.

| Mode | Ý nghĩa |
|---|---|
| `AUTO` | Khi có Bean Validation provider khả dụng, JPA tích hợp tự động theo specification; nếu không có provider, có thể tiếp tục mà không tự validate |
| `CALLBACK` | Yêu cầu automatic Bean Validation callbacks; nếu provider cần thiết không có, persistence unit setup/deployment có thể thất bại |
| `NONE` | Tắt automatic lifecycle Bean Validation integration của JPA |

### 11.1. AUTO: chế độ thường dùng

```xml
<validation-mode>AUTO</validation-mode>
```

Trong ứng dụng có provider, pre-persist/pre-update validation groups mặc định được kích hoạt theo contract. Nếu không có Bean Validation provider, đừng kỳ vọng lỗi validation tự phát sinh chỉ vì entity có annotations.

### 11.2. CALLBACK: muốn fail fast khi thiếu provider

```xml
<validation-mode>CALLBACK</validation-mode>
```

Hữu ích nếu team muốn bảo đảm rằng application deployment **không silently mất lớp validation tự động** do thiếu dependency.

### 11.3. NONE: khi có lý do rõ

```xml
<validation-mode>NONE</validation-mode>
```

Có thể dùng khi application tự quản lý việc validate, hoặc migration/batch process cần tắt integration theo một chiến lược có kiểm soát.

**Nhưng NONE không có nghĩa annotation biến mất.** Bạn vẫn có thể chủ động gọi `Validator.validate(entity)` để kiểm tra. Nó chỉ tắt automatic JPA lifecycle validation.

### 11.4. persistence.xml minh họa

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.0">

    <persistence-unit name="catalogPU">
        <class>com.example.catalog.domain.CatalogProduct</class>

        <validation-mode>CALLBACK</validation-mode>

        <properties>
            <property
                name="jakarta.persistence.validation.group.pre-persist"
                value="jakarta.validation.groups.Default"/>
            <property
                name="jakarta.persistence.validation.group.pre-update"
                value="jakarta.validation.groups.Default"/>
        </properties>
    </persistence-unit>
</persistence>
```

Đây là đoạn cấu hình minh họa ý định, không phải toàn bộ persistence unit production. Phiên bản XML schema, provider, datasource, transaction type và classpath phải khớp project.

### 11.5. Cấu hình bằng persistence unit properties

Cũng có thể dùng cấu hình property tương ứng như:

```text
jakarta.persistence.validation.mode
jakarta.persistence.validation.group.pre-persist
jakarta.persistence.validation.group.pre-update
jakarta.persistence.validation.group.pre-remove
```

Khả năng bind các properties này trong Spring Boot framework, provider settings hoặc XML phụ thuộc cách ứng dụng khởi tạo `EntityManagerFactory`. Tránh giả định một property tùy ý trong `application.properties` luôn được chuyển thành JPA persistence-unit property nếu chưa kiểm chứng.

---

## 12. Cấu hình validation groups theo sự kiện vòng đời

Validation **group** là tập constraints được chọn để chạy. Khi không chỉ định groups, constraint thuộc `Default`.

Ví dụ:

```java
@NotBlank
private String name;
```

tương đương constraint dùng `Default` group.

Nếu chỉ muốn ràng buộc một field khi publish:

```java
@NotNull(groups = PublishChecks.class)
private Instant publishedAt;
```

`PublishChecks` là marker interface:

```java
package com.example.catalog.validation;

public interface PublishChecks {
}
```

### 12.1. JPA groups configuration

Có thể cấu hình trong persistence unit:

```xml
<property
    name="jakarta.persistence.validation.group.pre-persist"
    value="jakarta.validation.groups.Default"/>

<property
    name="jakarta.persistence.validation.group.pre-update"
    value="jakarta.validation.groups.Default"/>

<property
    name="jakarta.persistence.validation.group.pre-remove"
    value="com.example.catalog.validation.BeforeDeleteChecks"/>
```

Danh sách group class names có thể được cấu hình theo định dạng được JPA spec hỗ trợ; nhiều groups có thể được khai báo bằng danh sách class names tương ứng. Cần chắc class nằm trên classpath và nhóm có annotation hợp lệ.

### 12.2. Cảnh báo: group config áp dụng cho persistence unit, không tự biết status

Nếu cấu hình:

```text
pre-update = Default, PublishChecks
```

thì **mọi entity thuộc phạm vi validation pre-update** có constraints trong `PublishChecks` đều được kiểm tra khi update, không chỉ products đang PUBLISHED.

Với sản phẩm DRAFT, `publishedAt=null` có thể hoàn toàn hợp lệ; cấu hình nhóm PublishChecks cho mọi UPDATE sẽ từ chối DRAFT một cách không mong muốn.

### 12.3. Nhóm theo operation, không đồng nghĩa nhóm theo state

JPA pre-update chỉ có nghĩa **có một UPDATE**. Nó không có nghĩa **đang publish**. Muốn validate các quy tắc riêng cho transition “publish”, nên:

- Dùng service/domain method `publish()`.
- Gọi `validator.validate(product, PublishChecks.class)` trước transition/commit khi phù hợp.
- Hoặc dùng class-level constraint đánh giá status hiện tại.
- Vẫn để JPA Default group kiểm tra invariant chung trước write.

### 12.4. Nhóm riêng cho delete có thể hữu ích nhưng dễ lạm dụng

Nếu pre-remove groups được bật, validator có thể chặn xóa vì constraint đã định nghĩa. Nhưng business rule “có đơn hàng thì không được xóa” thường phụ thuộc DB association và FK constraints, không nên đưa mọi logic tra cứu database vào Bean Validation validator callback.

---

## 13. Ví dụ groups cho DRAFT và PUBLISHED

Giả sử có một Product có thể được lưu dạng draft chưa có mô tả, nhưng khi publish phải có mô tả và giá hợp lệ.

Định nghĩa:

```java
public interface PublishChecks {
}
```

Entity:

```java
@Entity
public class Article {

    @Id
    @GeneratedValue
    private Long id;

    @NotBlank
    @Size(max = 200)
    private String title;

    @Size(max = 20000)
    private String body;

    @NotNull
    @Enumerated(EnumType.STRING)
    private ArticleStatus status = ArticleStatus.DRAFT;

    @NotBlank(groups = PublishChecks.class)
    public String getPublishableBody() {
        return body;
    }

    protected Article() {
    }

    public void publish(Validator validator) {
        Set<ConstraintViolation<Article>> violations =
            validator.validate(this, PublishChecks.class);

        if (!violations.isEmpty()) {
            throw new ConstraintViolationException(violations);
        }

        if (status != ArticleStatus.DRAFT) {
            throw new IllegalStateException(
                "Article cannot be published from this state"
            );
        }

        status = ArticleStatus.PUBLISHED;
    }
}
```

Đây là ví dụ **ý tưởng** để thấy group operation và validation trực tiếp. Trong thiết kế production, thường không truyền `Validator` infrastructure vào domain entity; service sẽ gọi Validator, còn entity giữ state-transition method. `ArticleStatus` là enum do dự án định nghĩa.

### 13.1. Service phân tách trách nhiệm tốt hơn

```java
@Transactional
public void publish(long articleId) {
    Article article = em.find(Article.class, articleId);

    if (article == null) {
        throw new ArticleNotFoundException(articleId);
    }

    if (article.getStatus() != ArticleStatus.DRAFT) {
        throw new IllegalStateException("Not a draft");
    }

    Set<ConstraintViolation<Article>> violations =
        validator.validate(article, PublishChecks.class);

    if (!violations.isEmpty()) {
        throw new ConstraintViolationException(violations);
    }

    article.publish(); // Domain method chỉ thực hiện transition.
}
```

Đoạn này giả định `Article` có `getStatus()`/`publish()` và `Validator` được inject vào service. Tình huống concurrent publication vẫn cần `@Version` hoặc locking, vì Bean Validation không tự phát hiện hai requests publish đồng thời.

### 13.2. Group trên getter với JPA field access?

Bean Validation có thể đánh giá constraints trên field hoặc getter độc lập với JPA field/property access. Tuy nhiên codebase nên chọn một conventions rõ để tránh đặt duplicate constraints trên cùng property và bị validate hai lần.

### 13.3. Quan trọng: @NotBlank(groups=PublishChecks.class) không chạy trong pre-update Default

Nếu pre-update chỉ validate Default group, một UPDATE chuyển Article sang PUBLISHED có thể vẫn pass mặc dù publish body không hợp lệ **nếu service bỏ qua validate PublishChecks**. Đừng giả định JPA tự đoán group theo trạng thái.

### 13.4. Alternative: class-level constraint phụ thuộc status

Có thể viết một custom class-level constraint `@ValidPublishedArticle` kiểm tra:

```text
Nếu status = PUBLISHED:
    body phải nonblank
Nếu status = DRAFT:
    body có thể trống
```

Vì là constraint thuộc Default group, JPA pre-update Default validation sẽ kiểm tra nó cho mọi entity updates, nhưng việc cập nhật đến PUBLISHED sẽ fail nếu body trống. Đây là cách giữ invariant phụ thuộc state ở entity-level, không phải chỉ ở API publish operation.

---

## 14. @GroupSequence và thứ tự validation

Có những trường hợp chỉ muốn chạy những constraints tốn kém hơn khi basic checks đã pass.

Ví dụ marker groups:

```java
public interface BasicChecks {
}

public interface DetailedChecks {
}
```

Định nghĩa sequence:

```java
@GroupSequence({
    BasicChecks.class,
    DetailedChecks.class
})
public interface FullProductChecks {
}
```

Khi gọi:

```java
validator.validate(product, FullProductChecks.class);
```

provider kiểm tra nhóm theo thứ tự của sequence. Nếu nhóm trước có violations, các nhóm sau trong sequence không cần được đánh giá.

### 14.1. Vì sao dùng group sequence?

- Tránh kiểm tra định dạng chuyên sâu khi field cơ bản đã null/rỗng.
- Giảm xử lý constraints đắt.
- Tách workflow validation thành nhiều tầng có ngữ nghĩa.

### 14.2. Không nhầm sequence với transaction steps

Group sequence chỉ điều phối **validation groups**, không tự flush, tạo transaction, lock row hoặc commit.

### 14.3. Cẩn thận khi redefine Default group sequence trên class

Có những quy tắc cụ thể khi đặt `@GroupSequence` trực tiếp lên một bean class, gồm việc sequence phải bao gồm chính bean class theo contract. Nếu chỉ cần một marker group sequence độc lập, dùng interface như ví dụ trước thường đơn giản hơn.

### 14.4. Không dùng group sequence để truy vấn DB phục vụ uniqueness

Nó không tự giúp tránh race condition nếu custom constraint query DB “SKU chưa tồn tại”. Unique constraint ở database vẫn cần thiết.

---

## 15. @Valid: cascading validation qua object graph

Một entity Order có các OrderLines:

```java
@Entity
@Table(name = "sales_order")
public class SalesOrder {

    @Id
    @GeneratedValue
    private Long id;

    @NotNull
    private String customerCode;

    @NotEmpty
    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<@Valid OrderLine> lines =
        new ArrayList<>();

    // Methods thêm/xóa line giữ hai phía association đồng bộ.
}
```

Child entity:

```java
@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    @GeneratedValue
    private Long id;

    @NotNull
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    private SalesOrder order;

    @NotNull
    @Positive
    @Column(nullable = false)
    private Integer quantity;

    @NotNull
    @DecimalMin("0.00")
    private BigDecimal unitPrice;
}
```

Ở đây:

- `@NotEmpty` yêu cầu Order có ít nhất một line.
- `List<@Valid OrderLine>` khai báo cascading Bean Validation tới phần tử.
- `cascade = CascadeType.ALL` là **JPA persistence cascade**, không phải Bean Validation cascade.
- `@NotNull order` và `@ManyToOne(optional=false)` là hai lớp khai báo khác nhau.

### 15.1. @Valid khác CascadeType.PERSIST

| Annotation | Thuộc cơ chế | Tác động |
|---|---|---|
| `@Valid` | Bean Validation | Kiểm tra constraints của nested object/element |
| `@OneToMany(cascade=PERSIST)` | JPA | Cho phép persist child theo parent |
| `@OneToMany(cascade=ALL)` | JPA | Các persistence operations liên quan có thể cascade |
| `@NotEmpty` | Bean Validation | Yêu cầu collection có phần tử |
| `@NotNull` | Bean Validation | Yêu cầu tham chiếu không null |

Bạn có thể bật JPA cascade mà không có Bean Validation cascade, hoặc ngược lại. Đừng tưởng `cascade = CascadeType.ALL` tự validate từng field của child theo mọi groups.

### 15.2. @Valid có tạo một vòng lặp vô hạn khi mapping hai chiều?

Bean Validation providers có cơ chế quản lý graph traversal/cycles theo specification để tránh validate vô hạn một object graph lặp. Tuy nhiên graph lớn/cyclic vẫn có thể tốn CPU và làm truy cập association phức tạp hơn.

### 15.3. Lazy associations và traversable resolver

JPA integration cung cấp cơ chế `TraversableResolver` để Bean Validation xác định một thuộc tính/association có thể được truy cập/cascade phù hợp hay không. Lazy associations **chưa được load** không mặc nhiên bị fetch toàn bộ chỉ để validate.

Vì thế:

- Đừng giả định `@Valid` trên `@OneToMany(fetch=LAZY)` sẽ buộc tải mọi child của một aggregate lớn trước mỗi UPDATE.
- Đừng giả định một collection chưa load đã được validate như collection đã load.
- Test behavior với provider/mapping/lazy state mục tiêu.
- Khi invariant đòi kiểm tra tất cả children, service/domain query và transaction strategy phải bảo đảm đã có dữ liệu cần thiết.

### 15.4. Không dùng @Valid để thay aggregate consistency

Một Order có thể có 10 Lines hợp lệ riêng lẻ, nhưng tổng tiền do Order lưu không bằng tổng Lines. `@Valid` chỉ validate những constraints đã khai báo; không tự suy ra tổng tiền phải khớp.

Cần class-level constraint hoặc domain method kiểm tra aggregate invariant, cùng transaction/locking khi nhiều writers đồng thời.

---

## 16. Cascading validation trên @Embedded

Một Address value object:

```java
@Embeddable
public class PostalAddress {

    @NotBlank
    @Size(max = 200)
    private String street;

    @NotBlank
    @Size(max = 100)
    private String city;

    @NotBlank
    @Size(max = 12)
    private String postalCode;

    protected PostalAddress() {
    }
}
```

Entity:

```java
@Entity
public class Customer {

    @Id
    private Long id;

    @Valid
    @Embedded
    private PostalAddress shippingAddress;
}
```

`@Valid` cho phép cascade Bean Validation vào Address, nếu đối tượng có mặt và traversal được phép.

### 16.1. @Embedded không tự là @Valid

Một embedded mapping nghĩa là thành phần được persist như phần state của owner. Việc cascade Bean Validation là một khái niệm riêng. Khai báo `@Valid` khi muốn validate các constraints bên trong embedded component.

### 16.2. @Valid không tự yêu cầu shippingAddress tồn tại

Nếu shippingAddress bắt buộc:

```java
@NotNull
@Valid
@Embedded
private PostalAddress shippingAddress;
```

Nếu địa chỉ là optional, bỏ `@NotNull` và chỉ cascade validation khi object khác null.

### 16.3. @AttributeOverride không sửa Bean Validation rule

JPA `@AttributeOverride` thay đổi mapping cột của embedded field, không tự thay `@NotBlank`/`@Size` được định nghĩa trong `PostalAddress`.

---

## 17. Container element constraints

Các phiên bản Jakarta Validation hiện đại hỗ trợ constraints trên container element types, ví dụ:

```java
@ElementCollection
private List<@NotBlank String> tags =
    new ArrayList<>();

@ElementCollection
private Map<@NotBlank String, @Positive Integer> limits =
    new HashMap<>();
```

Ý định:

- Mỗi tag không được blank.
- Mỗi key của map không được blank.
- Mỗi value trong map phải positive.

### 17.1. @NotEmpty trên collection khác element constraint

```java
@NotEmpty
private List<@NotBlank String> tags;
```

`@NotEmpty` kiểm tra collection có phần tử, còn `@NotBlank` trên type argument kiểm tra từng phần tử.

### 17.2. Provider phải có value extractors phù hợp

Jakarta Validation có cơ chế value extraction cho nhiều container types chuẩn. Với custom generic container, có thể cần provider/value extractor hỗ trợ. Không mặc định mọi custom `Box<T>` được validate sâu mà không cấu hình.

### 17.3. Entity lifecycle update có nhận ra collection-only changes?

Một thay đổi chỉ trong collection hoặc join table có thể không tạo UPDATE trên owner entity row theo mọi mapping/provider. **Không dựa vào pre-update validation owner như cách duy nhất bảo vệ mọi thay đổi collection**.

Nếu tags bắt buộc không rỗng ở mỗi thao tác thay đổi collection, cần kiểm soát domain methods/service validation và database constraints phù hợp.

### 17.4. JPA association semantics vẫn độc lập

Một `List<@Valid OrderLine>` có thể pass Bean Validation dù owning side của bidirectional association chưa được đồng bộ đúng, dẫn tới FK/mapping không như mong muốn. Phải giữ relationship ownership và collection state đồng bộ.

---

## 18. Custom constraint: khi chuẩn không diễn tả đủ yêu cầu

Giả sử SKU phải có 3–32 ký tự, chỉ gồm A–Z, chữ số và dấu gạch ngang.

### 18.1. Định nghĩa annotation

```java
package com.example.catalog.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.*;

@Target({
    ElementType.FIELD,
    ElementType.METHOD,
    ElementType.ANNOTATION_TYPE,
    ElementType.PARAMETER,
    ElementType.TYPE_USE
})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = SkuCodeValidator.class)
public @interface SkuCode {

    String message() default "Invalid SKU code";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
```

### 18.2. Implement validator

```java
package com.example.catalog.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import java.util.regex.Pattern;

public class SkuCodeValidator
        implements ConstraintValidator<SkuCode, String> {

    private static final Pattern SKU =
        Pattern.compile("[A-Z0-9-]{3,32}");

    @Override
    public boolean isValid(
            String value,
            ConstraintValidatorContext context
    ) {
        // Nullability do @NotBlank/@NotNull quyết định.
        return value == null
            || SKU.matcher(value).matches();
    }
}
```

### 18.3. Sử dụng

```java
@NotBlank
@SkuCode
private String sku;
```

### 18.4. Vì sao validator cho null pass?

Nhiều constraint chỉ kiểm tra một khía cạnh và để `@NotNull`/`@NotBlank` chịu trách nhiệm nullability. Điều này giúp tái sử dụng constraint cho field optional.

Tuy nhiên, **@NotBlank đã tự từ chối null**; kết hợp như trên sẽ đảm bảo cả tồn tại và đúng format.

### 18.5. Không đặt side effects trong validator

`ConstraintValidator.isValid` nên là một phép kiểm tra ổn định, không gửi email, ghi DB hoặc thay đổi entity state. JPA có thể gọi validator ở flush/commit, và nhiều lần theo lifecycle; validator có side effect sẽ làm transaction khó dự đoán.

### 18.6. Thread-safety

Bean Validation provider có thể tái sử dụng `ConstraintValidator` instances. Tránh mutable per-request fields và không viết logic phụ thuộc vào instance được tạo riêng cho mỗi validation call.

---

## 19. Class-level constraint: kiểm tra quan hệ giữa nhiều fields

Một chiến dịch có:

```text
startAt
endAt
```

Quy tắc: nếu cả hai tồn tại, `endAt` phải sau `startAt`. Không field-level constraint đơn giản nào tự nhìn cả hai fields.

### 19.1. Định nghĩa annotation

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = CampaignDateRangeValidator.class)
public @interface ValidCampaignDateRange {

    String message() default
        "Campaign end time must be after start time";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
```

### 19.2. Gắn trên entity

```java
@Entity
@ValidCampaignDateRange
public class Campaign {

    @Id
    private Long id;

    @NotNull
    private Instant startAt;

    @NotNull
    private Instant endAt;

    protected Campaign() {
    }

    public Instant getStartAt() {
        return startAt;
    }

    public Instant getEndAt() {
        return endAt;
    }
}
```

### 19.3. Validator thực hiện quy tắc hai field

```java
public class CampaignDateRangeValidator
        implements ConstraintValidator<
            ValidCampaignDateRange,
            Campaign
        > {

    @Override
    public boolean isValid(
            Campaign campaign,
            ConstraintValidatorContext context
    ) {
        if (campaign == null) {
            return true;
        }

        Instant start = campaign.getStartAt();
        Instant end = campaign.getEndAt();

        // @NotNull xử lý hai field chưa có dữ liệu.
        return start == null
            || end == null
            || end.isAfter(start);
    }
}
```

### 19.4. Violation path class-level

Với class-level constraint, default violation path có thể là bean-level, không phải `endAt`. Nếu muốn API trả lỗi gắn với field `endAt`, có thể dùng `ConstraintValidatorContext` để vô hiệu default violation và tạo node cho property theo API tiêu chuẩn.

### 19.5. Tại sao tránh query database trong class-level validator?

Một validator kiểm tra “campaign có trùng khoảng ngày với campaign khác trong DB không?” bằng SELECT có rủi ro:

- Gây N+1 queries khi validate hàng loạt.
- Gây truy cập DB trong flush callback, dễ làm lifecycle phức tạp.
- Query thấy snapshot khác với điều kiện ghi.
- Bị race: hai transactions cùng query không thấy trùng rồi cùng INSERT.
- Nếu cố mutate data/flush trong validator, có thể gây re-entrant persistence operations khó kiểm soát.

Đối với invariant đa row, dùng service transaction, locks/isolation hoặc database constraint thích hợp. Bean Validation vẫn hữu ích cho **quy tắc thuần dựa trên object state**.

---

## 20. Vì sao kiểm tra uniqueness bằng Bean Validation không đủ?

Giả sử service có:

```java
if (!productRepository.existsBySku(sku)) {
    repository.save(new CatalogProduct(sku, ...));
}
```

Hai transactions đồng thời:

```text
Tx A: SELECT exists(sku="BOOK-JPA") -> false
Tx B: SELECT exists(sku="BOOK-JPA") -> false
Tx A: INSERT
Tx B: INSERT
```

Nếu database không có UNIQUE constraint, cả hai có thể tạo duplicate SKUs. Kể cả một custom Bean Validation annotation `@UniqueSku` chạy query DB, race vẫn tồn tại.

### 20.1. Database uniqueness là hàng rào chính

```sql
ALTER TABLE catalog_product
ADD CONSTRAINT uk_catalog_product_sku
UNIQUE (sku);
```

Cú pháp cụ thể tùy database và migration state. Unique constraint được database thực thi atomically theo concurrency semantics của nó.

### 20.2. Bean Validation có thể hỗ trợ thông báo sớm

Một validation/query trước có thể cải thiện UX: “SKU đã tồn tại”. Nhưng kết quả đó **chỉ là precheck**, không phải bằng chứng chắc chắn INSERT sẽ thành công. Cần xử lý unique constraint violation tại database.

### 20.3. Phân biệt hai ConstraintViolationException có tên giống nhau

Rất dễ nhầm:

- `jakarta.validation.ConstraintViolationException`: **Bean Validation** vi phạm constraints, chứa `ConstraintViolation<?>`.
- `org.hibernate.exception.ConstraintViolationException`: một **Hibernate ORM/JDBC exception** cho lỗi ràng buộc database; package và payload khác.

Tương tự, Spring có thể translate lỗi DB constraint thành `DataIntegrityViolationException`, trong khi Bean Validation exception có thể đi theo một wrapper khác. Đừng catch theo tên class ngắn “ConstraintViolationException” mà bỏ qua package/causes.

### 20.4. UNIQUE constraint vẫn không validate business state machine

Một SKU có thể unique nhưng Product không được publish vì thiếu ảnh. Database uniqueness và Bean Validation giải quyết hai loại invariant khác nhau.

---

## 21. ConstraintViolationException: lấy thông tin gì?

Exception chuẩn Bean Validation:

```java
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
```

Ví dụ xử lý:

```java
catch (ConstraintViolationException ex) {
    for (ConstraintViolation<?> violation
            : ex.getConstraintViolations()) {

        String path =
            violation.getPropertyPath().toString();

        String message =
            violation.getMessage();

        String template =
            violation.getMessageTemplate();

        System.out.println(path + ": " + message);
    }

    throw ex;
}
```

Mỗi `ConstraintViolation<?>` có thể chứa:

| Trường | Ví dụ |
|---|---|
| `getPropertyPath()` | `name`, `price`, `lines[0].quantity` |
| `getMessage()` | “must not be blank” |
| `getMessageTemplate()` | `{jakarta.validation.constraints.NotBlank.message}` |
| `getInvalidValue()` | Giá trị không hợp lệ (cần cẩn trọng bảo mật) |
| `getRootBean()` | Object được validate |
| `getRootBeanClass()` | Type của object gốc |
| `getConstraintDescriptor()` | Metadata constraint |
| `getLeafBean()` | Object tại nơi violation xảy ra |

Tên path cụ thể khi nested objects/containers có thể khác tùy graph và provider, nhưng API property path có cấu trúc rõ.

### 21.1. Không lộ dữ liệu nhạy cảm trong log/API

`getInvalidValue()` có thể là email, token, địa chỉ, thông tin thanh toán hoặc toàn object. Không serialize nguyên mọi violation ra HTTP/log production. Chỉ trả field/message được whitelist và mã lỗi phù hợp.

### 21.2. Message interpolation

Bean Validation hỗ trợ message templates và interpolation, có thể tích hợp localization/resource bundles. Ví dụ:

```java
@NotBlank(message = "{catalog.product.name.required}")
private String name;
```

Message có thể lấy từ resource bundle; cần kiểm chứng configuration của provider/i18n. Không dùng message text làm machine-readable error code cố định — message có thể đổi theo locale.

### 21.3. Group information có sẵn

`ConstraintDescriptor` cho biết groups của constraint. Hữu ích khi điều tra một vi phạm chỉ xảy ra trong `PublishChecks` nhưng không xảy ra trong Default.

### 21.4. Không dựa vào thứ tự violations

Tập violations thường không có thứ tự business ưu tiên ổn định. Nếu API cần sắp xếp field/message, service/controller nên sort rõ trước khi trả.

---

## 22. Exception xảy ra lúc flush hay commit?

Giả sử:

```java
@Transactional
public void updateProduct(long id) {
    CatalogProduct product =
        em.find(CatalogProduct.class, id);

    product.changePrice(new BigDecimal("-2.00"));
}
```

Trong một Spring method:

1. Application đổi Java field.
2. Method body có thể chạy hết mà không exception.
3. Transaction interceptor bắt đầu flush/commit.
4. Bean Validation có thể phát hiện `price < 0`.
5. Commit không thành công, lỗi được ném về caller qua transaction boundary.

### 22.1. Vì sao catch bên trong method có thể bỏ sót?

```java
@Transactional
public void updateProduct(long id) {
    try {
        product.changePrice(new BigDecimal("-2.00"));
        // Không có flush ở đây.
    } catch (ConstraintViolationException ex) {
        // Có thể không bao giờ chạy nhánh này.
    }
}
```

Violation thường không xuất hiện lúc setter; nó có thể xuất hiện khi transaction manager hoàn tất transaction sau khi method body return.

### 22.2. Muốn kiểm tra sớm?

Có thể dùng Validator trực tiếp:

```java
Set<ConstraintViolation<CatalogProduct>> violations =
    validator.validate(product);

if (!violations.isEmpty()) {
    throw new ConstraintViolationException(violations);
}
```

hoặc chủ động `em.flush()` khi cần đồng bộ và quan sát lỗi DB/validation sớm. Tuy nhiên:

- `flush` vẫn chưa commit.
- Query tiếp theo có thể tạo thêm lỗi.
- Version/constraint conflicts khác có thể chỉ rõ ở commit.
- Không nên flush chỉ để “chắc chắn đã commit”.

### 22.3. Rollback

Khi automatic Bean Validation phát hiện entity không hợp lệ trong lifecycle ghi, transaction bị đánh dấu rollback/không thể commit thành công theo contract tương ứng. Ứng dụng cần rollback transaction attempt, không catch rồi tiếp tục ghi như thể chưa có vấn đề.

### 22.4. Spring wrappers

Tùy provider/transaction manager, nguyên nhân Bean Validation có thể được bọc trong transaction/persistence exceptions khi commit. Khi xử lý lỗi, truy nguyên **cause chain có kiểm soát**, không kết luận mọi `RollbackException` hay `TransactionSystemException` đều do Bean Validation.

---

## 23. Transaction sau validation failure: không tiếp tục như bình thường

Không nên:

```java
try {
    em.flush();
} catch (ConstraintViolationException ex) {
    product.changePrice(new BigDecimal("20.00"));
    em.flush();  // Không có đảm bảo transaction còn sử dụng được.
}
```

Khi flush-time validation thất bại, transaction có thể đã rollback-only, persistence context có thể không còn trạng thái phù hợp để tiếp tục. Cách an toàn:

1. Ghi nhận violations ở mức phù hợp, không lộ dữ liệu nhạy cảm.
2. Rollback transaction hiện tại.
3. Không tiếp tục commit một phần thay đổi pending.
4. Sửa request/state ở một attempt mới.
5. Dùng transaction/persistence context mới khi retry.
6. Kiểm tra lại authorization và concurrency version nếu dữ liệu có thể thay đổi.

### 23.1. Bean Validation failure thường không phải lỗi transient cần retry tự động

Một `name=""` sẽ vẫn vi phạm sau 10 retries nếu input không đổi. Đừng retry liên tục như với deadlock/serialization failure.

### 23.2. Khi nào retry có thể có lý?

Nếu vi phạm do dữ liệu phụ thuộc trạng thái ngoài, cần làm rõ source/trigger. Tuy nhiên, phần lớn annotation constraints kiểm tra state deterministic: **sửa dữ liệu** thay vì retry.

### 23.3. Không phát side effects trước commit

Nếu service đã gửi email “Sản phẩm đã xuất bản” trước khi JPA flush rồi Bean Validation thất bại, email đã gửi không rollback cùng DB. Dùng transactional outbox/after-commit nếu workflow yêu cầu.

### 23.4. Cảnh báo về external cache

Nếu code đã cập nhật Redis hoặc search index trước commit, DB rollback không tự hoàn nguyên cache/index. Cần sự kiện sau commit hoặc reconciliation riêng.

---

## 24. Cấu hình fail-fast và thông báo lỗi

Một số Bean Validation providers hỗ trợ **fail-fast**: trả lỗi ngay khi tìm thấy một violation thay vì tập hợp tất cả. Đây thường là extension/configuration của provider, **không phải điều khiển chuẩn JPA tự có ở mọi stack**.

### 24.1. Lợi ích

- Giảm chi phí nếu validation graph rất lớn.
- Tránh chạy những constraints tiếp theo khi đã có lỗi.
- Có thể phù hợp với backend bulk processing.

### 24.2. Hạn chế

- API có thể trả một lỗi một lần, UX kém hơn nếu người dùng cần sửa nhiều trường.
- “Vi phạm đầu tiên” không nên được coi có thứ tự ổn định giữa providers.
- Không thay group sequence khi muốn ordering có ý nghĩa nghiệp vụ.

### 24.3. Không giải quyết vấn đề transaction timing

Fail-fast thay cách duyệt constraints, không làm exception nhất thiết xuất hiện tại setter thay vì flush/commit.

---

## 25. Jakarta Validation Validator: gọi chủ động ở service

Trong nhiều use cases, muốn phản hồi sớm **trước khi đưa entity vào persistence context**.

```java
import jakarta.validation.Validator;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.ConstraintViolationException;
import java.util.Set;

public class ProductValidationService {

    private final Validator validator;

    public ProductValidationService(Validator validator) {
        this.validator = validator;
    }

    public void validate(CatalogProduct product) {
        Set<ConstraintViolation<CatalogProduct>> violations =
            validator.validate(product);

        if (!violations.isEmpty()) {
            throw new ConstraintViolationException(violations);
        }
    }
}
```

### 25.1. Điều này có thay JPA automatic validation không?

Không nhất thiết. Manual validation giúp kiểm tra sớm, nhưng entity có thể tiếp tục bị thay đổi sau đó. Automatic pre-persist/pre-update validation (nếu bật) là một lớp bổ sung tại persistence boundary.

### 25.2. Manual validation không flush

`validator.validate(product)` đánh giá constraints object graph theo group/traversal, không tự INSERT/UPDATE database row.

### 25.3. Validate custom group

```java
validator.validate(
    product,
    PublishChecks.class
);
```

Không mặc định constraints trong Default sẽ cũng được kiểm tra khi chỉ truyền `PublishChecks.class`, trừ khi groups/inheritance/sequence được định nghĩa để bao gồm chúng.

### 25.4. Validate property và value

Validator API cũng cung cấp `validateProperty`/`validateValue` cho những nhu cầu cụ thể. Nhưng chúng không tương đương full object graph validation và không thể tự xử lý mọi class-level/cross-field invariant.

### 25.5. ValidatorFactory

Trong một ứng dụng không dùng DI container, có thể xây:

```java
ValidatorFactory factory =
    Validation.buildDefaultValidatorFactory();

try {
    Validator validator = factory.getValidator();
    // ...
} finally {
    factory.close();
}
```

ValidatorFactory có vòng đời tài nguyên riêng; không tạo/đóng factory trên từng field validation request nếu không cần. Với Spring, thường inject Validator đã được framework cấu hình.

---

## 26. @Valid trên REST request DTO khác automatic JPA validation

Một request DTO:

```java
public record CreateProductRequest(
    @NotBlank @Size(max = 64) String sku,
    @NotBlank @Size(max = 200) String name,
    @NotNull @DecimalMin("0.00") BigDecimal price
) {
}
```

Controller Spring:

```java
@PostMapping("/products")
public ResponseEntity<?> create(
        @Valid @RequestBody CreateProductRequest request
) {
    Long id = productService.create(request);
    return ResponseEntity.status(201).body(id);
}
```

Ở đây, `@Valid` trên request argument yêu cầu tầng web/framework kiểm tra DTO trước khi gọi service theo cấu hình phù hợp. Còn JPA automatic validation kiểm tra **entity** ở persistence lifecycle.

### 26.1. Hai cơ chế có timing khác

| DTO validation | JPA entity validation |
|---|---|
| Thường tại HTTP binding/controller boundary | Tại entity pre-persist/pre-update/pre-remove pipeline |
| Trả lỗi sớm trước DB transaction | Có thể phát sinh ở flush/commit |
| Validate request shape/field constraints | Validate managed entity state |
| Không yêu cầu EntityManager | Yêu cầu JPA integration/lifecycle event |
| Không tự bảo vệ SQL writes | Không tự validate bulk/native DML |

### 26.2. Có cần duplication?

Có thể chấp nhận một số constraints được lặp ở DTO và entity:

- DTO phục vụ thông báo gần người dùng.
- Entity đảm bảo các writers không đi qua REST DTO vẫn có validation trước entity-level writes.
- DB constraints bảo vệ tất cả nguồn ghi.

Không nên dùng entity trực tiếp làm API request model nếu nó chứa fields như `id`, `tenantId`, `status`, `version` mà client không được tự tùy ý sửa.

### 26.3. @Validated của Spring

Trong Spring, `@Validated` thường được dùng để kích hoạt validation groups/method validation theo framework. Nó **không phải** một JPA lifecycle annotation; JPA không cần controller/service `@Validated` mới chạy Bean Validation pre-persist/update khi integration đã bật.

### 26.4. Không dựa vào request validation để giữ cross-row invariant

DTO `quantity > 0` là hợp lệ nhưng Inventory chỉ còn 1 trong DB. Service phải kiểm tra current state dưới transaction/concurrency strategy.

---

## 27. Mapping field access và getter constraints

JPA có field access/property access. Bean Validation cũng cho phép đặt constraints trên fields hoặc properties/getters.

### 27.1. Field-based JPA mapping

```java
@Entity
public class Product {

    @Id
    private Long id;

    @NotBlank
    private String name;

    protected Product() {
    }
}
```

Ở đây JPA identity/access được xác định từ mapping annotations trên fields, Bean Validation constraint cũng đặt trên field.

### 27.2. Property-based JPA mapping

```java
@Entity
@Access(AccessType.PROPERTY)
public class PropertyProduct {

    private Long id;
    private String name;

    protected PropertyProduct() {
    }

    @Id
    public Long getId() {
        return id;
    }

    protected void setId(Long id) {
        this.id = id;
    }

    @NotBlank
    @Column(name = "product_name")
    public String getName() {
        return name;
    }

    protected void setName(String name) {
        this.name = name;
    }
}
```

### 27.3. Tránh duplicate constraints trên cùng field và getter

```java
@NotBlank
private String name;

@NotBlank
public String getName() {
    return name;
}
```

Bean Validation có thể coi đây là hai constraint declarations và báo duplicate violations/cost không cần thiết, tùy mapping. Chọn một convention nhất quán trừ khi có lý do cụ thể.

### 27.4. JPA transient không đồng nghĩa Bean Validation bỏ qua

`@Transient` trong JPA nói property không được persist. Bean Validation vẫn có thể kiểm tra property được annotate constraint khi bạn validate bean, tùy placement/constraints/traversability.

Nếu chỉ muốn validate một derived property cho request chứ không muốn nó tham gia entity lifecycle, cân nhắc DTO/group tách biệt.

### 27.5. Có cần setter được gọi để validation xảy ra?

Không. Bean Validation provider có thể đọc constraints trên fields/getters trực tiếp. Nó không cần tất cả mutations đi qua một setter có validation logic.

---

## 28. Lifecycle callbacks @PrePersist/@PreUpdate khác Bean Validation

JPA định nghĩa:

```java
@PrePersist
@PreUpdate
@PreRemove
@PostPersist
@PostUpdate
@PostRemove
@PostLoad
```

Đây là **entity lifecycle callbacks**, khác Bean Validation constraint callbacks.

### 28.1. @PrePersist có thể chuẩn bị giá trị

```java
@PrePersist
void initializeTimestamps() {
    Instant now = Instant.now();

    if (createdAt == null) {
        createdAt = now;
    }

    updatedAt = now;
}
```

### 28.2. @PreUpdate có thể cập nhật audit metadata

```java
@PreUpdate
void updateTimestamp() {
    updatedAt = Instant.now();
}
```

### 28.3. ConstraintValidator chỉ nên kiểm tra, không mutate

```java
@Override
public boolean isValid(String value, Context context) {
    // Không nên tự gán lại entity hoặc gọi em.persist().
    return value == null || validFormat(value);
}
```

### 28.4. Cẩn thận callback order

Trong pipeline entity-level write của JPA, entity lifecycle callbacks tương ứng có thể chuẩn bị state trước automatic Bean Validation được áp ở điểm ghi. Vì vậy một giá trị `createdAt` do `@PrePersist` gán có thể vượt `@NotNull`.

Nhưng **thời điểm cụ thể của API persist/flush/INSERT, và thứ tự với provider-specific listeners/interceptors** cần được hiểu theo spec/provider. Đừng thiết kế logic dựa vào một SQL/event order quá chi tiết không được bảo đảm.

### 28.5. Không truy cập EntityManager phức tạp trong lifecycle callback

JPA lifecycle callbacks có những giới hạn và khuyến nghị portability; không nên mở query/modify relationships hoặc gọi external services từ `@PrePersist`/`@PreUpdate`. Một callback query dữ liệu trong lúc flush có thể gây reentrant actions, hiệu năng kém và behavior phụ thuộc provider.

### 28.6. Bean Validation không gọi @PrePersist cho một Java object chỉ vì Validator.validate

`validator.validate(product)` không phải một JPA lifecycle operation; nó kiểm tra constraints mà không tự gọi `@PrePersist` để chuẩn bị audit fields. Nếu test manual validation một transient entity có createdAt null, `@NotNull createdAt` có thể fail dù JPA persist flow sẽ điền createdAt trong callback.

Điều này cần được thiết kế rõ để tránh nhầm lẫn giữa manual validation timing và pre-persist validation.

---

## 29. Database-generated values và validation timing

Giả sử database có:

```sql
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
```

nhưng entity:

```java
@NotNull
@Column(name = "created_at", insertable = false)
private Instant createdAt;
```

Nếu giá trị `createdAt` chỉ được database tạo khi INSERT, Bean Validation chạy **trước INSERT** có thể thấy Java field null và từ chối entity trước khi DB default có cơ hội chạy.

### 29.1. Đây là timing conflict, không phải database lỗi

Automatic validation đang kiểm tra object state trước DML; database-generated field chưa có.

### 29.2. Các hướng thiết kế

- Cho application/JPA callback gán field trước insert.
- Nếu trường thực sự server-generated, không đặt `@NotNull` trong lifecycle group chạy trước INSERT mà kỳ vọng nó đã tồn tại.
- Dùng group khác hoặc loại constraint khỏi pre-persist khi có lý do phù hợp.
- Dùng provider-supported generated value mapping rồi refresh/đọc lại sau INSERT.
- Đảm bảo schema NOT NULL/DEFAULT vẫn bảo vệ dữ liệu trong DB.

### 29.3. Với generated ID

`@GeneratedValue` có thời điểm gán ID tùy strategy/provider. `@NotNull` trên ID generated có thể gây validation timing/mapping surprises nếu gán quá sớm trong lifecycle. Đừng buộc pre-persist bean validation của ID generated phải nonnull nếu không có yêu cầu rõ và test đúng chiến lược.

### 29.4. Với @Version

Provider quản lý version; giá trị version ban đầu có thể được chuẩn bị ở thời điểm persistence. Đừng tự gán version để qua validation. Nếu có constraints trên `version`, phải kiểm tra chúng có tương thích lifecycle initialization strategy hay không.

---

## 30. Validation không bảo đảm uniqueness hoặc quan hệ hợp lệ ở cấp database

Một entity `OrderLine` có:

```java
@NotNull
@ManyToOne(optional = false)
private CatalogProduct product;
```

Nếu `product` là object không null nhưng trỏ tới ID không tồn tại trong DB, `@NotNull` vẫn pass. Foreign key constraint có thể chặn INSERT/UPDATE tại database.

### 30.1. @Valid trên product có giúp xác minh FK tồn tại không?

Không. `@Valid` kiểm tra constraints của object được cascade tới, không thay thế kiểm tra tồn tại của referenced row hoặc FK constraint.

### 30.2. @NotNull khác @JoinColumn(nullable=false)

`@JoinColumn(nullable=false)` là mapping/schema metadata. Nó không tự chạy Bean Validation constraint logic nếu không có `@NotNull` hoặc tương ứng.

### 30.3. Relationship ownership vẫn phải đúng

Nếu bidirectional `@OneToMany(mappedBy="order")` và `@ManyToOne` không được đồng bộ hai phía, Bean Validation không tự sửa owning side. Có thể pass validation nhưng persist ra FK không đúng mong đợi.

### 30.4. Orphan removal và cascade remove

JPA `orphanRemoval=true` hoặc `CascadeType.REMOVE` điều khiển persistence operations. Việc child bị delete không mặc nhiên chạy Default validation group trên pre-remove; default pre-remove groups vẫn trống.

---

## 31. Lazy associations: không biến validation thành N+1 vô tình

Ví dụ Product có nhiều reviews:

```java
@OneToMany(mappedBy = "product", fetch = FetchType.LAZY)
private List<@Valid ProductReview> reviews;
```

Nếu validation luôn fetch toàn bộ reviews mỗi lần sửa Product name, performance sẽ rất tệ. JPA integration với Bean Validation dùng traversability/lazy awareness để tránh tự ý tải những state chưa được load trong một số trường hợp.

### 31.1. Nhưng điều này tạo một giới hạn quan trọng

Một constraint ở child không có nghĩa **mọi child trên database** đều đã được validate khi parent UPDATE nếu association chưa loaded.

### 31.2. Khi business thực sự cần kiểm tra toàn bộ graph

Ví dụ “không publish Product nếu có Review chưa được kiểm duyệt”. Đây là database-wide business invariant. Một service query COUNT/EXISTS hoặc guarded aggregate rule có thể rõ hơn việc hy vọng `@Valid` fetch cả collection.

### 31.3. Không lạm dụng eager fetch để ép validation

Đổi mọi `@OneToMany` thành EAGER có thể gây N+1, cartesian multiplication, memory blow-up và slow transactions. Fetch strategy cần được thiết kế theo use case đọc, không chỉ để khiến Bean Validation đi sâu.

### 31.4. DTO và domain query tách khỏi entity validation

API muốn xác nhận order có ít nhất một line đang hợp lệ có thể chủ động fetch và validate đúng set lines trong transaction. JPA lifecycle validation vẫn có ích cho constraints trên từng entity, nhưng không phải công cụ thay query logic chuyên biệt.

---

## 32. Bean Validation và optimistic locking

`@Version`:

```java
@Version
@Column(name = "row_version", nullable = false)
private Long version;
```

cho phép JPA phát hiện stale updates theo entity-level optimistic locking. Nó giải quyết vấn đề khác Bean Validation.

### 32.1. Một trạng thái có thể hợp lệ nhưng stale

A và B cùng load Item version 7, available=10, cả hai muốn trừ 4. Mỗi entity state sau trừ thành available=6 — **không âm**, có thể pass `@PositiveOrZero`.

A commit thành version 8. B flush theo version 7 có thể nhận `OptimisticLockException`. Nếu không có version/locking thích hợp, hai updates hợp lệ riêng lẻ vẫn có thể làm mất thay đổi của nhau.

### 32.2. Một trạng thái có thể current nhưng invalid

A là transaction duy nhất, đặt price=-5. `@Version` không có contention nên không có optimistic conflict. Bean Validation có thể chặn price âm trước INSERT/UPDATE.

### 32.3. Hai lớp bảo vệ bổ sung

| Vấn đề | Bean Validation | `@Version` |
|---|---|---|
| price âm | Có thể chặn bằng `@DecimalMin` | Không tự chặn |
| name blank | Có thể chặn bằng `@NotBlank` | Không tự chặn |
| stale write/lost update | Không tự chặn | Có thể phát hiện |
| cross-row quota | Không tự bảo vệ | Không tự bảo vệ mọi rows |
| unique SKU | Không tự bảo vệ race | Không tự bảo vệ concurrent inserts |
| duplicate payment | Không | Không |
| invalid state transition | Custom/domain validation | Cần domain rule, version giúp xử lý cạnh tranh |

### 32.4. Retry phải làm lại cả business validation

Sau optimistic conflict, rollback và reload current state. Không replay computed values cũ rồi chỉ validate shape của chúng.

---

## 33. Bean Validation và pessimistic locking

Một transaction muốn giữ chỗ hàng:

```java
@Transactional
public void reserve(long itemId, int requestedQuantity) {
    InventoryItem item = em.find(
        InventoryItem.class,
        itemId,
        LockModeType.PESSIMISTIC_WRITE
    );

    if (item == null) {
        throw new ItemNotFoundException(itemId);
    }

    item.reserve(requestedQuantity);
}
```

`reserve` là domain method kiểm tra số lượng hiện tại. Bean Validation có thể kiểm tra những constraints như `@PositiveOrZero availableQuantity` khi JPA UPDATE; nhưng **nó không thay kiểm tra “request này có được phép reserve bao nhiêu”**.

### 33.1. Lock trước rồi kiểm tra

Với pessimistic lock, business state mutable cần được đọc/kiểm tra sau khi lấy lock, để không dựa vào snapshot cũ.

### 33.2. Lock không thay Bean Validation

Dù transaction nắm `PESSIMISTIC_WRITE`, nó vẫn có thể set `name=""`. Lock chỉ điều phối concurrency; validation bảo vệ entity constraints.

### 33.3. Bean Validation không thay lock

Một constraint `@PositiveOrZero` trên availableQuantity không ngăn hai transactions cùng đọc 10 và cùng ghi 6. Cần concurrency control.

### 33.4. Multi-row invariants

Nếu quota = tổng reservations nhiều rows, lock một InventoryItem chỉ bảo vệ quota nếu mọi writers dùng InventoryItem làm guard row. Bean Validation trên collection không tự tạo predicate lock.

---

## 34. Bulk JPQL UPDATE/DELETE bỏ qua lifecycle validation

Một ví dụ:

```java
int changed = em.createQuery(
    """
    update CatalogProduct p
    set p.name = :newName
    where p.status = :draft
    """
)
.setParameter("newName", "")
.setParameter("draft", ProductStatus.DRAFT)
.executeUpdate();
```

Đây là **bulk JPQL UPDATE**, tác động database trực tiếp. Nó không tự thực hiện vòng lặp:

```text
load mỗi Product
-> setName
-> @PreUpdate
-> Bean Validation
-> dirty checking
-> SQL UPDATE
```

Kết quả là `@NotBlank name` **không được tự áp như entity-level validation** cho từng Product qua bulk query.

### 34.1. Vì sao nguy hiểm?

Nếu DB chỉ có `NOT NULL`, một chuỗi rỗng có thể vẫn hợp lệ về database schema, dù Bean Validation xem blank là invalid. Bulk UPDATE có thể lưu state mà entity-level writes bình thường bị chặn.

### 34.2. Cần kiểm soát gì với bulk DML?

- Validate parameters trước.
- Đưa điều kiện có thể biểu diễn vào SQL WHERE/SET.
- Có DB CHECK/NOT NULL/UNIQUE/FK phù hợp.
- Xử lý `@Version` theo manual strategy nếu entity có version.
- Xử lý audit callbacks không chạy.
- Xử lý stale managed entities trong persistence context.
- Đánh giá L2/query cache invalidation.
- Test điều kiện và transaction rollback thật.

### 34.3. CriteriaUpdate/CriteriaDelete tương tự

Criteria bulk update/delete vẫn là set-based DML, không phải entity-level lifecycle validation.

### 34.4. Native SQL càng không tự biết Bean Validation annotations

```sql
UPDATE catalog_product
SET product_name = ''
WHERE id = 42;
```

Nếu database không có ràng buộc chống blank, câu lệnh có thể thành công dù Java entity gắn `@NotBlank`.

### 34.5. Phải dùng managed entities khi cần callbacks và validation

Nếu business quy định mỗi Product UPDATE phải qua domain method và Bean Validation, hãy xử lý managed entities trong transaction, có batching hợp lý. Bulk DML chỉ là lựa chọn đúng nếu bạn **chủ động chấp nhận/đền bù** khác biệt lifecycle semantics.

---

## 35. Validation cho JPQL SELECT có tự chạy không?

Không. JPQL SELECT thường truy xuất dữ liệu, không phải một pre-persist/pre-update/pre-remove event.

```java
List<CatalogProduct> products = em.createQuery(
    "select p from CatalogProduct p",
    CatalogProduct.class
).getResultList();
```

Nếu database chứa Product legacy có name blank:

- Entity có thể được load vào persistence context.
- `@NotBlank` không tự từ chối mọi SELECT.
- Gọi getter không tự gây `ConstraintViolationException`.
- Nếu entity được sửa và provider chuẩn bị UPDATE, pre-update validation có thể phát hiện lỗi legacy đó ngay cả khi chỉ thay field khác.

### 35.1. Bảo trì dữ liệu legacy

Nếu thêm `@NotBlank` vào entity của bảng có dữ liệu cũ invalid, lần UPDATE một field không liên quan vẫn có thể thất bại. Cần migration/backfill, staged rollout hoặc group strategy phù hợp.

### 35.2. Validation thủ công sau load

```java
Set<ConstraintViolation<CatalogProduct>> violations =
    validator.validate(product);
```

có thể kiểm tra đối tượng đã load, nhưng không tự sửa database.

### 35.3. @PostLoad không tự validate

JPA `@PostLoad` callback có thể chạy khi entity được load, nhưng Bean Validation auto integration **không mặc định chạy Default group mỗi khi @PostLoad**. Nếu muốn bảo vệ read models hoặc phân loại dữ liệu legacy, thiết kế read-path validation rõ riêng.

---

## 36. Quan hệ Bean Validation với database schema generation

Một số provider có thể dùng Bean Validation metadata để hỗ trợ DDL/schema generation:

- `@NotNull` có thể ảnh hưởng generated nullable metadata.
- `@Size(max=...)` có thể ảnh hưởng varchar length.
- `@Digits` có thể liên quan column precision/scale.

Nhưng:

1. Đây là chi tiết phụ thuộc provider/config/version.
2. Không phải thay database migration.
3. Không tự thay đổi một schema production đang chạy.
4. Không biến regex/custom class-level constraints thành một database CHECK tương đương portable.
5. Không đảm bảo trigger/stored procedure/raw SQL tuân thủ Bean Validation.

### 36.1. Ưu tiên migration tường minh

Với Flyway/Liquibase/manual migration, hãy quản lý schema constraints riêng và review khả năng tương thích:

```sql
ALTER TABLE catalog_product
ADD CONSTRAINT ck_catalog_price_nonnegative
CHECK (unit_price >= 0);
```

DDL này phụ thuộc DB support/cú pháp và dữ liệu hiện hữu. Nếu bảng có price âm, migration phải backfill hoặc xử lý trước khi bật CHECK.

### 36.2. Hai lớp không cần giống hệt từng ký tự

Bean Validation `@NotBlank` có thể dùng trim/whitespace semantics theo Java; database CHECK như `LENGTH(TRIM(name)) > 0` có thể khác Unicode whitespace và collation. Cần xác định domain rule chính xác và test.

### 36.3. Không đặt toàn bộ logic vào DB nếu code cần thông báo tốt

Database constraint là lớp bảo vệ cuối. Bean Validation giúp API/transaction nhận violations có cấu trúc để giải thích sớm, miễn là không phơi bày dữ liệu nhạy cảm.

---

## 37. Validation nhóm pre-remove: khi nào dùng, khi nào tránh?

Giả sử muốn chặn xóa Product có field `lockedForDeletion=true`. Một ý tưởng:

```java
public interface BeforeDeleteChecks {
}
```

Constraint riêng:

```java
@AssertFalse(groups = BeforeDeleteChecks.class)
public boolean isLockedForDeletion() {
    return lockedForDeletion;
}
```

Cấu hình:

```xml
<property
    name="jakarta.persistence.validation.group.pre-remove"
    value="com.example.catalog.validation.BeforeDeleteChecks"/>
```

### 37.1. Lợi ích

Có thể biểu đạt một rule thuần trên current entity state, không cần truy vấn DB.

### 37.2. Hạn chế

- Field `lockedForDeletion` có thể stale nếu entity đã load quá lâu.
- Quy tắc có thể phụ thuộc child rows/foreign keys không nằm trong object state.
- Bulk DELETE/native SQL bỏ qua.
- Automatic validation có thể làm xóa dữ liệu legacy khó khăn.
- Race condition vẫn có thể xảy ra nếu writer khác thay đổi state song song.

### 37.3. Khi nào dùng service guard tốt hơn?

Một quyết định “có được xóa Order đã SHIPPED không?” là state transition nghiệp vụ. Service/domain method dưới transaction và concurrency strategy phù hợp thường rõ hơn, có thể trả lỗi chính xác và kiểm soát authorization.

### 37.4. FK constraint vẫn cần

Dù validator cho phép, database có thể từ chối DELETE khi còn các rows tham chiếu nếu FK không cho cascade. Không coi Bean Validation là thay thế FK.

---

## 38. Validation groups cho create/update: những sai lầm thiết kế hay gặp

Một ý tưởng:

```java
public interface OnCreate {
}

public interface OnUpdate {
}
```

```java
@NotBlank(groups = OnCreate.class)
private String sku;

@NotNull(groups = OnUpdate.class)
private Long id;
```

### 38.1. Vấn đề với ID generated

`id` được provider sinh; pre-persist timing khác nhau. Đặt constraint `@NotNull(groups=OnUpdate)` trên ID có thể hợp lý khi update, nhưng không tạo ra bảo đảm đó là entity tồn tại hoặc caller có quyền sửa. DB identity và authorization riêng.

### 38.2. Vấn đề với fields dùng cả create/update

Nếu `name` chỉ thuộc `OnCreate`, sửa name thành blank trong một update có thể pass `OnUpdate`. Các invariants “name luôn nonblank” nên ở Default hoặc một group bao gồm trong cả pre-persist và pre-update.

### 38.3. Group marker là operation semantics, không phải API route semantics

JPA pre-persist/update liên quan **INSERT/UPDATE thực tế**. Một HTTP POST có thể cập nhật entity có sẵn, một HTTP PATCH có thể tạo child entity mới; không đồng nhất HTTP method với entity lifecycle event.

### 38.4. Một thiết kế groups thực dụng

- Default: các invariant luôn đúng trên entity state persisted.
- PublishChecks: chỉ dành cho transition publish hoặc class-level predicate kiểm tra trạng thái.
- ImportChecks: chính sách nhập dữ liệu tạm/lax khi có workflow migration rõ.
- BeforeDeleteChecks: rất ít, chỉ khi phù hợp với semantics remove.

Đừng tạo hàng chục groups trước khi có use case.

---

## 39. Vòng đời đối với collection và associated entity

Ví dụ:

```java
SalesOrder order = em.find(SalesOrder.class, orderId);
order.addLine(new OrderLine(...));
em.flush();
```

Các sự kiện xảy ra tùy mapping/cascade/ownership:

- Một child mới có thể được persist thông qua cascade.
- Child mới có thể chạy pre-persist validation của **chính OrderLine**.
- Parent Order có thể hoặc không có SQL UPDATE cho row chính.
- Collection/join table có thể được update.
- Parent `@PreUpdate`/pre-update Bean Validation **không được bảo đảm chỉ vì collection thay đổi** trong mọi mapping/provider.

### 39.1. Không lệ thuộc vào parent callback để kiểm tra mọi child operations

Nếu parent không được UPDATE, parent pre-update validation có thể không chạy. Nên dùng domain methods/child constraints và validation tại service khi invariant phụ thuộc collection.

### 39.2. @Valid trên parent collection có ý nghĩa nhưng không thay lifecycle của child

Cascaded Bean Validation có thể kiểm tra những child objects reachable theo traversal. Còn việc child được INSERT/UPDATE/DELETE là chuyện JPA cascade và association ownership.

### 39.3. Delete child từ collection

`orphanRemoval=true` có thể làm JPA DELETE child. Default pre-remove validation groups là trống; điều này khác với việc child được updated và pre-update Default validation chạy.

### 39.4. Phân biệt collection in-memory với dữ liệu DB

Một managed collection có thể chưa initialized. Nếu rule “Order phải có ít nhất một line” phụ thuộc database, không nên giả định kiểm tra một collection state chưa load/bị filters/soft delete là đủ cho toàn nghiệp vụ.

---

## 40. Tương tác với Spring Data JPA save/flush

Spring Data JPA có các API như:

```java
repository.save(entity);
repository.saveAndFlush(entity);
repository.flush();
```

### 40.1. save không đảm bảo validation ngay

`save` có thể gọi `persist` hoặc `merge` theo cơ chế nhận diện entity mới/cũ, nhưng SQL write và validation có thể chờ tới flush/commit.

### 40.2. saveAndFlush có thể làm lỗi xuất hiện sớm hơn

`saveAndFlush` yêu cầu đồng bộ changes, nên có thể giúp kiểm tra thời điểm persistence errors. Nhưng:

- Nó không commit transaction.
- Nó có thể flush **các pending managed changes khác** trong cùng persistence context, không chỉ entity truyền vào.
- Một số lỗi vẫn xuất hiện lúc commit.
- Không dùng nó để phát external event trước khi commit.

### 40.3. @Transactional boundaries quan trọng hơn tên method

Nếu controller gọi service `@Transactional` và service return trước khi interceptor commit, caller cần xử lý exceptions ở ranh giới transaction thực tế.

### 40.4. Entity validation và method validation khác nhau

`@Validated` trên service có thể bật method parameter/return validation theo Spring. Nó không tự thay đổi nhóm JPA pre-update hoặc khiến bulk UPDATE chạy Bean Validation.

### 40.5. Khi cần báo lỗi API thân thiện

Có thể chủ động validate request DTO, dùng domain exception, đồng thời catch/translate `jakarta.validation.ConstraintViolationException` tại boundary đủ rộng để bao gồm flush/commit failures. Không chỉ dựa vào validation trong repository method body.

---

## 41. Những vấn đề với @PrePersist/@PreUpdate callbacks và custom validators

### 41.1. Callback mutate field mà validator phụ thuộc

Ví dụ `@PrePersist` set `createdAt`, `@NotNull` kiểm tra field đó. Đây là một use case phù hợp nếu lifecycle order trên target stack đúng như JPA integration.

### 41.2. Callback sửa price thành giá trị âm

```java
@PreUpdate
void applyDiscount() {
    price = price.subtract(discount);
}
```

Nếu discount lớn khiến price âm, validation tiếp theo có thể phát hiện `@DecimalMin("0.00")`. Nhưng **không nên để logic pricing phức tạp trong callback**; service/domain method dễ kiểm soát và test hơn.

### 41.3. Validator gọi repository

Một custom validator `isValid` gọi JPA repository query:

```java
return !repository.existsBySku(value);
```

có thể gây reentrant flush/query và vẫn không bảo đảm uniqueness. Đặt checks phụ thuộc DB ở application service/transaction phù hợp, database UNIQUE constraint là lớp cuối.

### 41.4. Validator sửa dữ liệu cho “hợp lệ”

```java
product.setSku(product.getSku().trim());
return true;
```

trong `isValid` là anti-pattern. Normalization nên chạy tường minh trước validation, chẳng hạn DTO mapper/domain constructor hoặc `@PrePersist` callback có giới hạn hợp lý.

### 41.5. Validator gửi event

Không. Validation có thể chạy nhiều lần/rollback. External side effects cần được quản lý sau commit/outbox.

### 41.6. Message có thể chứa thông tin nhạy cảm

Không đưa raw `getInvalidValue()` vào message default hoặc log ở nơi không được phép.

---

## 42. Tránh validate toàn graph quá lớn

Một entity aggregate có:

```text
Customer
  ├── 5000 Orders
  ├── Addresses
  ├── Payments
  └── Reviews
```

Nếu gắn `@Valid` cascade trên mọi association và eager load tất cả, một lần update Customer.phoneNumber có thể khiến validation rất nặng.

### 42.1. Chọn graph validation theo use case

- Constraint trên Customer fields.
- @Valid trên embedded Address nếu cần.
- @Valid trên children thật sự thuộc domain aggregate nhỏ.
- Service-level checks cho cross-row relationships.
- Database constraints cho FK/uniqueness.

### 42.2. Cân nhắc group conversion

Jakarta Validation có `@ConvertGroup` để thay đổi group được áp vào nested object khi cascading validation. Đây là kỹ thuật nâng cao khi parent operation group và child group khác nhau, không phải lời giải mặc định cho graph quá lớn.

### 42.3. Không lạm dụng group sequence với expensive validators

Nếu expensive validator truy vấn DB, group sequence chỉ giảm vài lần gọi, không giải quyết consistency/race. Tách logic ra application service/SQL transaction.

### 42.4. Kiểm tra performance trên workload thật

Đo:

- Số entities bị validate mỗi flush.
- Số nested objects được traverse.
- Số DB queries phát sinh do validators/callbacks.
- Flush/commit latency.
- Memory allocation và GC.
- Lock wait/transaction duration.
- Validation failure rate.

Không tắt validation chỉ vì một benchmark một lần; trước tiên tìm graph/validator có vấn đề.

---

## 43. Bulk import: làm thế nào giữ dữ liệu hợp lệ?

Một job import 100.000 Products có thể dùng JDBC batch hoặc JPA `persist` theo lô. Hai cách có trade-off:

### 43.1. Entity-based import

```text
CSV -> parse -> DTO validate
    -> entity/domain mapping
    -> em.persist(...)
    -> periodic flush/clear
    -> commit per batch
```

Ưu điểm:

- Có thể dùng JPA lifecycle validation.
- Có callbacks, mapping và cascade.
- Dễ dùng domain methods.

Đổi lại:

- Overhead tạo/managed entities.
- Validator graph traversal.
- Batch size và flush/clear cần có chủ đích.
- Một invalid record có thể làm transaction batch rollback.

### 43.2. JDBC/native bulk import

```text
CSV -> parse -> explicit Validator/domain checks
    -> prepared/batch SQL
    -> DB constraints
```

Ưu điểm: có thể nhanh và đơn giản với set-based operations.

Đổi lại:

- Không có automatic JPA lifecycle validation.
- Phải tự làm normalization/validation/audit/version.
- Lỗi DB có thể xuất hiện theo batch và cần mapping về source row.

### 43.3. Không gọi Validator.validate chỉ trên một “sample row”

Nếu batch code bỏ qua JPA validation, phải có chiến lược kiểm tra **tất cả records cần kiểm tra**, không dựa vào sample.

### 43.4. Database constraints vẫn luôn cần

Dù nhập bằng JPA, CSV, ETL hay admin SQL, database NOT NULL/UNIQUE/CHECK/FK là những hàng rào cuối bảo vệ dữ liệu chung.

### 43.5. Import dữ liệu legacy không hợp lệ

Có thể đưa vào staging table, validate/normalize, rồi chỉ INSERT dữ liệu đã đạt điều kiện vào production tables. Đừng tắt validation global trên persistence unit production chỉ để import dữ liệu bẩn mà không có policy.

---

## 44. Transaction và lỗi validation trong API

Một workflow create Product:

```text
HTTP POST /products
        |
        v
DTO @Valid
        |
        v
Service transaction:
    authorization
    domain mapping
    em.persist(product)
    flush / automatic Bean Validation
    database INSERT + UNIQUE constraints
    commit
        |
        v
201 Created nếu commit thành công
```

Các lỗi có thể xuất hiện ở các tầng:

| Tầng | Ví dụ | Outcome đề xuất |
|---|---|---|
| DTO validation | name thiếu | 400/422 tùy API contract |
| Domain validation | trạng thái publish không hợp lệ | 409/422 tùy contract |
| Entity lifecycle validation | price âm do service/mapper gán | 400/422 hoặc server bug tùy nguồn dữ liệu |
| DB UNIQUE | SKU đồng thời trùng | 409 hoặc code business conflict |
| DB FK | Product reference không tồn tại | 400/409 hoặc lỗi dữ liệu nội bộ |
| Optimistic locking | version stale | 409/412 tùy expectedVersion/HTTP conditional request |
| Lock timeout/deadlock | transaction contention | Retryable outcome hoặc lỗi tạm thời |
| Commit/connection failure | database unavailable | Không trả thành công; xử lý idempotency/reconciliation |

Các HTTP codes là lựa chọn thiết kế API, **không có mapping cố định do Jakarta Persistence quy định**.

### 44.1. Violation message không phải lỗi HTTP mặc định

Nếu Bean Validation provider ném exception ở commit, web framework có thể coi là server error nếu chưa có exception handler phù hợp. Cần xử lý riêng cho input-caused violations và internal invariant violations, tránh lộ entity internals.

### 44.2. Không leak class/property của dữ liệu không được phép

Đối với multi-tenant, lỗi trên entity của tenant khác không nên được serialize ra client chỉ vì có property path rõ.

### 44.3. Một service có thể tự tạo invalid entity do bug

Nếu DTO đã hợp lệ nhưng service tính price âm, đó có thể là **bug backend**, không phải lỗi người dùng. Đừng luôn trả “sửa request” cho mọi ConstraintViolationException.

### 44.4. Exception commit có thể được wrap

Spring/JPA transaction interceptors có thể bọc cause. Exception translation nên nhận diện nguyên nhân có kiểm soát, không catch mọi `Exception` và biến thành 400.

---

## 45. Test Bean Validation trực tiếp

Trước khi test JPA integration, kiểm tra annotation constraints thuần với `Validator`.

### 45.1. Test @NotBlank và price âm

```java
@Test
void rejectsBlankNameAndNegativePrice() {
    CatalogProduct product = new CatalogProduct(
        "BOOK-JPA",
        "  ",
        new BigDecimal("-1.00")
    );

    Set<ConstraintViolation<CatalogProduct>> violations =
        validator.validate(product);

    Set<String> paths = violations.stream()
        .map(v -> v.getPropertyPath().toString())
        .collect(Collectors.toSet());

    assertTrue(paths.contains("name"));
    assertTrue(paths.contains("price"));
}
```

Ở ví dụ entity có `@NotNull createdAt/updatedAt` do `@PrePersist` điền khi persist, **manual validation transient product** cũng có thể báo violations ở các fields audit. Vì vậy test không nên assert chỉ có hai violations; chỉ assert những field liên quan. Nếu muốn unit test chỉ business constraints, tách nhóm/cấu hình hoặc tạo fixture có audit fields theo strategy được chọn.

### 45.2. Test group PublishChecks

```java
Set<ConstraintViolation<Article>> violations =
    validator.validate(article, PublishChecks.class);
```

Assert những publish constraints tương ứng, không tự kỳ vọng mọi Default constraints chạy nếu không khai báo group inheritance/sequence.

### 45.3. Test @Valid nested

Tạo một SalesOrder có OrderLine quantity=0, bảo đảm nested violation xuất hiện khi association/element thật sự được cascade. Không chỉ assert parent `@NotEmpty`.

### 45.4. Test custom constraint

Một SKU `"abc_lowercase"` phải fail `@SkuCode`; `"BOOK-JPA"` pass, theo regex đã định nghĩa.

### 45.5. Test class-level date range

Campaign `endAt` trước `startAt` phải fail `@ValidCampaignDateRange`, kể cả từng Instant đều không null.

---

## 46. Test JPA pre-persist validation thật

Mục tiêu: chứng minh lifecycle integration thực sự hoạt động, không chỉ Validator có trong classpath.

### 46.1. Test setup resource-local

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

tx.begin();

try {
    CatalogProduct invalid = new CatalogProduct(
        "BOOK-INVALID",
        "",
        new BigDecimal("-2.00")
    );

    assertThrows(
        ConstraintViolationException.class,
        () -> {
            em.persist(invalid);
            em.flush();
        }
    );

    tx.rollback();
} finally {
    if (tx.isActive()) {
        tx.rollback();
    }
    em.close();
}
```

Đây là skeleton để test với JPA provider chạy automatic validation. Exception thực tế có thể xuất hiện ở flush hoặc persist; nếu chỉ xuất hiện khi commit hoặc bị wrap trong persistence exception, điều chỉnh assertions theo target provider/transaction manager, **không đánh giá integration chỉ từ một class exception ở một dòng API cố định**.

### 46.2. Cần đúng validation mode

Nếu `ValidationMode.NONE`, test tự động sẽ không chạy dù Bean Validation annotations tồn tại. Với `AUTO` cần provider khả dụng; với `CALLBACK` thiếu provider thường setup lỗi.

### 46.3. Phải rollback sau test failure

Sau automatic validation violation, transaction có thể rollback-only. Không tiếp tục persist thêm records rồi cố commit cùng transaction.

### 46.4. Kiểm tra không có row invalid trong DB

Mở EntityManager/transaction mới để xác nhận Product `BOOK-INVALID` không được commit. Không chỉ assert exception mà bỏ qua database outcome.

### 46.5. Không giả định Hibernate Validator là JPA provider

Test cần cả JPA provider và Bean Validation provider được kết nối đúng, không chỉ `validator.validate` hoạt động độc lập.

---

## 47. Test JPA pre-update validation

Kịch bản:

1. Persist Product hợp lệ, commit.
2. Mở transaction mới.
3. Load Product managed.
4. Gán name blank hoặc price âm.
5. Flush/commit.
6. Mong validation failure.
7. Rollback.
8. Load lại ở context mới, xác nhận state DB vẫn hợp lệ.

Sơ đồ:

```text
Tx 1:
  INSERT valid Product
  COMMIT

Tx 2:
  FIND Product
  changePrice(-10)
  FLUSH -> violation
  ROLLBACK

Tx 3:
  FIND Product
  price vẫn là giá hợp lệ đã commit ở Tx 1
```

### 47.1. Test đúng target field

Một Product có constraints trên audit fields do `@PreUpdate` cập nhật. Nếu service chỉ đổi price, audit callback có thể chạy trước validation. Đảm bảo test không bị nhiễu bởi dữ liệu fixture thiếu createdAt.

### 47.2. Test no-op update

Nếu load entity rồi không sửa gì, provider có thể không gửi UPDATE và pre-update validation không xảy ra. Vì vậy không assert “chỉ cần find rồi commit sẽ validate toàn bộ entity”.

### 47.3. Test collection-only updates

Thêm OrderLine vào collection có thể chỉ INSERT child và không UPDATE parent row. Test behavior của child pre-persist và parent pre-update tách biệt theo mapping thực tế.

### 47.4. Test legacy invalid row

Nếu table đã có Product name blank từ trước, thử update description (field khác) qua JPA. Default pre-update có thể phát hiện name invalid. Đây là case quan trọng khi rollout constraints cho dữ liệu legacy.

---

## 48. Test pre-remove mặc định và groups

### 48.1. Pre-remove không chạy Default group mặc định

Chuẩn bị một row Product invalid bằng SQL setup được kiểm soát (nếu schema cho phép), rồi thử `em.remove`. Nếu default pre-remove groups trống, Bean Validation không tự chặn remove vì `@NotBlank`, dù FK/DB constraints vẫn có thể chặn.

### 48.2. Khi cấu hình BeforeDeleteChecks

Cấu hình `jakarta.persistence.validation.group.pre-remove` và tạo entity có deletion guard vi phạm. Thử remove/flush, kiểm tra violation theo target provider.

### 48.3. Test cascade delete

Nếu remove parent cascade tới children, các child remove operations có lifecycle riêng. Không suy ra mọi child Default constraints được validate khi xóa; default remove groups vẫn trống.

### 48.4. Test bulk DELETE

Một JPQL bulk DELETE không tự chạy entity-level pre-remove Bean Validation cho từng row. Nếu có business deletion guard, bulk SQL cần điều kiện/authorization và constraints riêng.

---

## 49. Test bulk/native SQL bypass

Một test quan trọng để tránh giả định sai:

```java
em.createQuery(
    """
    update CatalogProduct p
    set p.name = :name
    where p.id = :id
    """
)
.setParameter("name", "")
.setParameter("id", productId)
.executeUpdate();
```

Nếu DB schema không cấm chuỗi blank, bulk UPDATE có thể thành công dù entity có `@NotBlank`. Test nên xác nhận cơ chế và sau đó xem có cần database CHECK/SQL predicate hoặc bỏ bulk approach hay không.

### 49.1. Không dùng test này để đưa dữ liệu bẩn vào production

Chỉ chạy trong disposable test DB/transaction và rollback/cleanup phù hợp.

### 49.2. Test L1 stale sau bulk

Nếu managed Product đã được load, bulk UPDATE không tự sync field của Java object. Nên dùng context mới hoặc refresh/clear sau bulk theo policy, đồng thời hiểu version/cache implications.

### 49.3. Test native writer

SQL script bên ngoài JPA cũng có thể bypass validation. Database constraints là lớp cuối; nếu không có, data có thể invalid.

### 49.4. Test schema-level CHECK

Cố chạy native UPDATE price âm; nếu DB CHECK được migrate đúng, database phải từ chối dù không có Bean Validation callback. Lỗi sẽ là DB constraint error, không nhất thiết `jakarta.validation.ConstraintViolationException`.

---

## 50. Multi-tenant, security và validation

Một entity có:

```java
@NotNull
private String tenantId;
```

chỉ bảo đảm tenantId không null. Nó **không bảo đảm tenantId thuộc user hiện tại**.

### 50.1. Không tin tenantId do client gửi

Service phải xác định authorized tenant từ security context đáng tin, lọc queries theo tenant và set tenantId server-side theo policy.

### 50.2. Validator không phải access-control engine

Một custom constraint `@BelongsToCurrentTenant` được triển khai bằng thread-local security context có thể khó test, khó dùng trong batch jobs và dễ sai nếu context thay đổi. Authorization thường nên thuộc application/service boundary.

### 50.3. Error messages không được leak dữ liệu khác tenant

Nếu validation trên association của một entity khác tenant phát hiện field invalid, không trả raw object/property path/invalid value ra API nếu user không được xem dữ liệu đó.

### 50.4. Bulk DML phải lọc tenant riêng

Bulk JPQL/native SQL có thể bypass entity lifecycle validation, và cũng không tự thêm tenant predicate nếu không được cấu hình/mapping rõ. Security boundary cần kiểm soát mọi writer.

### 50.5. Chỉ @NotNull tenantId không thay database isolation

Hai requests từ một tenant vẫn có concurrency issues riêng về quota/stock/version. Validation không tạo row locks.

---

## 51. Kiểm tra dữ liệu trong hệ thống đa nguồn ghi

Một bảng có thể được sửa bởi:

```text
REST API -> JPA entity updates
Admin UI -> JPA entity updates
Nightly job -> JDBC batch UPDATE
Data migration -> SQL scripts
Other service -> database client
Trigger/procedure -> database-side change
```

Bean Validation integration **chỉ bao phủ những thao tác đi qua entity lifecycle trong môi trường JPA phù hợp**. Nó không thể tự ép mọi writer ngoài JPA gọi Validator.

### 51.1. Hợp đồng dữ liệu nên ở DB cho điều kiện thiết yếu

- NOT NULL.
- UNIQUE business keys.
- CHECK đơn giản như price >= 0.
- FOREIGN KEY.
- Transaction isolation/locking thích hợp.
- Indexes/constraints phù hợp.

### 51.2. Bean Validation bổ sung thông báo sớm và code readability

Annotating entity giúp các developer hiểu field constraints, validate thủ công ở API/service và chặn JPA writes sai.

### 51.3. Eventual consistency vẫn cần kiểm soát

Một service có thể tạo entity hợp lệ nhưng phát event không phù hợp với state sau commit. Bean Validation không bảo đảm message exactly once hay atomic publish; cần outbox/idempotency/reconciliation.

### 51.4. Data migrations phải được test riêng

Nếu bổ sung constraint mới vào entity nhưng dữ liệu legacy chưa đạt chuẩn, JPA updates sau deploy có thể thất bại. Có lộ trình backfill/feature rollout, test compatibility của phiên bản ứng dụng cũ và mới.

---

## 52. Các anti-pattern thường gặp

### 52.1. Nghĩ @Column(nullable=false) là @NotNull

`@Column` là JPA mapping/schema metadata; nó không tự chạy Bean Validation `@NotNull`.

### 52.2. Nghĩ @NotNull tạo database NOT NULL ngay trong production

Không tự đảm bảo migration/schema đã được thay đổi.

### 52.3. Dùng @NotNull cho String nhưng muốn cấm dấu cách

`@NotNull` cho phép `""` và `"   "`. Cần `@NotBlank`.

### 52.4. Chỉ dùng @Size và quên nullability

`@Size` thường coi null là hợp lệ; thêm `@NotNull`/`@NotBlank` khi cần.

### 52.5. Không có validation provider nhưng nghĩ AUTO luôn chạy

`AUTO` có thể bỏ qua automatic integration nếu không có provider khả dụng.

### 52.6. Dùng NONE rồi kỳ vọng JPA lifecycle vẫn validate

`NONE` tắt automatic integration, dù `Validator.validate` chủ động vẫn dùng được.

### 52.7. Dùng CALLBACK nhưng thiếu provider

Persistence unit setup có thể fail; cần có provider và dependency tương thích.

### 52.8. Nhầm Default group ở pre-remove

Pre-remove mặc định không validate Default group.

### 52.9. Nghĩ pre-update chạy sau mọi setter

Pre-update gắn với lifecycle update, không phải property setter interceptor.

### 52.10. Nghĩ em.persist luôn ném lỗi ngay

Validation/SQL write có thể xảy ra tại flush/commit hoặc sớm hơn theo provider.

### 52.11. Catch ở setter rồi không xử lý exception commit

Commit-time validation có thể xảy ra sau method body.

### 52.12. Catch ConstraintViolationException rồi tiếp tục transaction

Transaction có thể rollback-only; cần rollback/new attempt.

### 52.13. Dùng Bean Validation để thay UNIQUE constraint

Precheck uniqueness có race; DB UNIQUE vẫn cần.

### 52.14. Nhầm jakarta.validation.ConstraintViolationException với Hibernate SQL exception

Khác package và ngữ nghĩa.

### 52.15. Viết ConstraintValidator gọi SQL để tìm unique

Tốn query, có race, nguy cơ reentrant flush; không phải giải pháp concurrency.

### 52.16. Viết ConstraintValidator mutate entity cho “đúng”

Validation nên kiểm tra, normalization nên làm tường minh trước.

### 52.17. Gửi email/payment trong validator

Validation có thể fail/retry/rollback; external side effects không tự rollback.

### 52.18. Gán @NotNull cho DB-generated field chưa có tại pre-persist

Có thể chặn INSERT trước khi DB default/generation chạy.

### 52.19. Dùng @Valid nhưng quên @NotEmpty trên collection bắt buộc

`@Valid` cascade validation, không yêu cầu có phần tử.

### 52.20. Tưởng CascadeType.ALL tự validate children

Persistence cascade và Bean Validation cascade khác nhau.

### 52.21. Nghĩ @Valid bắt buộc load mọi lazy association

JPA-aware traversal có thể bỏ qua uninitialized lazy associations; test thực tế.

### 52.22. Nghĩ parent pre-update chạy khi collection-only changes

Không được bảo đảm; child/entity relationship lifecycle có ngữ nghĩa riêng.

### 52.23. Quên groups khi gọi validator.validate

Nếu chỉ validate Default, constraints thuộc PublishChecks riêng có thể không được chạy.

### 52.24. Bật PublishChecks cho mọi pre-update trong persistence unit

Có thể từ chối mọi DRAFT updates không mong muốn.

### 52.25. Đặt duplicate constraints lên field và getter

Có thể gây kiểm tra trùng hoặc khó bảo trì.

### 52.26. Nghĩ @Valid trên REST DTO bật JPA lifecycle validation

Chúng là hai tích hợp khác, với timing và cơ chế khác.

### 52.27. Dùng @Validated của Spring để thay @Version

Method validation không phát hiện lost updates.

### 52.28. Bulk JPQL UPDATE nghĩ vẫn chạy @PreUpdate và Bean Validation

Không theo entity-level lifecycle; cần checks riêng.

### 52.29. Native SQL mong jakarta.validation constraints tự áp

Không. Database constraints mới bảo vệ writers này.

### 52.30. Chỉ test Validator.validate mà không test JPA integration

Không chứng minh persistence unit đã bật AUTO/CALLBACK và lifecycle events đúng.

### 52.31. Chỉ test em.persist mà không flush/commit

Có thể chưa quan sát validation/SQL failure.

### 52.32. Test invalid entity nhưng không rollback/kiểm tra DB

Có thể để transaction lỗi hoặc data side effect còn sót trong test.

### 52.33. Nghĩ entity valid nên không có optimistic conflict

Object constraints có thể pass nhưng snapshot stale.

### 52.34. Nghĩ lock row nên entity chắc chắn hợp lệ

Lock chỉ điều phối concurrency, không kiểm tra field values.

### 52.35. Xem @Email là xác minh email tồn tại

Nó chỉ hỗ trợ kiểm tra hình thức, không thay verification flow.

### 52.36. Trả toàn bộ invalidValue trong API error

Có thể leak token, PII hoặc object nhạy cảm.

### 52.37. Tắt validation global để batch chạy nhanh

Có thể làm mọi entity writes mất lớp bảo vệ; cần quyết định scoped/configuration rõ và DB constraints.

### 52.38. Nhầm validation state hiện tại với business invariant nhiều rows

Một Product hợp lệ không chứng minh quota, inventory hoặc payment consistency.

### 52.39. Bỏ qua schema migration khi thêm constraints

Dữ liệu legacy invalid sẽ khiến UPDATE thất bại ở nơi không dự kiến.

### 52.40. Cho rằng automatic Bean Validation chạy khi SELECT

Không. SELECT không phải pre-persist/update/remove lifecycle event.

---

## 53. Bảng lựa chọn chiến lược theo use case

| Nhu cầu | Cơ chế nên cân nhắc | Lý do |
|---|---|---|
| Form tạo sản phẩm phải có tên | DTO `@NotBlank` và entity `@NotBlank` | Phản hồi sớm + bảo vệ entity writes |
| Giá không được âm | `@DecimalMin` + DB CHECK | Java validation và DB integrity |
| SKU duy nhất khi tạo đồng thời | DB UNIQUE constraint | Bảo vệ race ở DB |
| Entity mới có createdAt | `@PrePersist` hoặc generator strategy phù hợp | Khởi tạo trước persistence; chú ý validation timing |
| Chỉnh entity và cần phát hiện stale write | `@Version` | Optimistic concurrency |
| Giữ chỗ tồn kho | Domain check + atomic UPDATE/lock | Business invariant cạnh tranh |
| Publish bài viết chỉ khi đủ dữ liệu | PublishChecks/class-level rule + domain transition | Validation theo operation/state |
| Xóa Product có OrderLines | Domain deletion guard + FK constraint | Không dựa vào pre-remove Default |
| Import nhiều Products bằng JPA | Manual DTO checks + lifecycle validation + batch transaction | Tận dụng constraints ở entity lifecycle |
| Bulk update 100.000 rows | DML predicates/DB constraints + manual version/audit | Bulk bypass entity validation |
| Nested @Embedded Address | `@Valid` + field constraints | Validate value-object state |
| Child OrderLines | `List<@Valid OrderLine>` + child constraints, test lazy traversal | Bean Validation cascade có chủ đích |
| Custom SKU format | `@Constraint`/`ConstraintValidator` | Quy tắc thuần Java |
| Ngày bắt đầu < ngày kết thúc | Class-level constraint | Cross-field rule |
| Tồn tại email thật | Verification workflow | `@Email` chỉ kiểm tra định dạng |
| API lỗi friendly | DTO validation + error mapping | Không phơi provider internals |
| Nhiều app cùng ghi DB | DB constraints + shared write contract | Bean Validation JPA không bao phủ raw SQL |
| Notification sau ghi | Outbox/after-commit | Validation pass chưa đồng nghĩa commit |

---

## 54. Bài tập thực hành có gợi ý

### Bài 1 — NotNull và NotBlank

Một Product.name nhận `"   "`. Nếu chỉ có `@NotNull` thì pass hay fail?

**Đáp án:** Pass với `@NotNull`. Muốn cấm trắng, dùng `@NotBlank`.

### Bài 2 — Size và null

`@Size(max=20)` trên String null có tự fail không?

**Gợi ý:** Không, null thường hợp lệ cho `@Size`; thêm `@NotNull`/`@NotBlank` nếu bắt buộc.

### Bài 3 — Kiểm tra giá

Viết annotation cho price không null, không âm, tối đa 12 chữ số phần nguyên và 2 số phần lẻ.

```java
@NotNull
@DecimalMin("0.00")
@Digits(integer = 12, fraction = 2)
private BigDecimal price;
```

### Bài 4 — Pre-persist

Một Product mới có name blank, gọi `em.persist(product)` nhưng chưa có exception.

**Gợi ý:** Validation có thể xuất hiện ở flush/commit; test đúng lifecycle boundary.

### Bài 5 — Pre-update

Load Product managed, đổi price thành -1 và flush.

**Gợi ý:** Với Bean Validation integration bật và Default group chứa DecimalMin, pre-update validation phải phát hiện vi phạm trong entity-level update.

### Bài 6 — Pre-remove mặc định

Xóa Product legacy có name blank. Default group có tự chặn remove không?

**Đáp án:** Pre-remove mặc định không có groups được validate.

### Bài 7 — AUTO

Một persistence unit có AUTO nhưng không có Bean Validation provider.

**Gợi ý:** Automatic validation có thể không được bật; cần dependencies đầy đủ nếu application yêu cầu.

### Bài 8 — CALLBACK

Muốn application fail khi thiếu Bean Validation provider.

**Gợi ý:** `<validation-mode>CALLBACK</validation-mode>`.

### Bài 9 — NONE

Muốn tắt auto JPA validation nhưng vẫn tự gọi Validator trong import service.

**Đáp án:** `NONE` tắt JPA auto integration, `validator.validate` vẫn dùng được khi provider có sẵn.

### Bài 10 — Cấu hình group update

Thêm `Default` vào pre-update groups trong persistence unit.

**Gợi ý:** Property `jakarta.persistence.validation.group.pre-update` với giá trị `jakarta.validation.groups.Default`.

### Bài 11 — Group PublishChecks

Field publishedAt bắt buộc khi publish nhưng draft được null.

**Gợi ý:** Đặt `@NotNull(groups=PublishChecks.class)` và gọi validation group trong publish service; hoặc class-level rule phụ thuộc status.

### Bài 12 — Group bất cẩn

Cấu hình `PublishChecks` cho mọi pre-update, khiến DRAFT không lưu được.

**Gợi ý:** Không tự coi pre-update nghĩa là publish. Sửa group strategy theo operation/state.

### Bài 13 — Domain transition

Article từ ARCHIVED không được chuyển sang PUBLISHED.

**Gợi ý:** Domain method/service kiểm tra status; Bean Validation field constraints không tự có state machine.

### Bài 14 — ConstraintViolationException

In property path và message của tất cả violations.

```java
for (ConstraintViolation<?> v
        : ex.getConstraintViolations()) {
    System.out.println(
        v.getPropertyPath() + ": " + v.getMessage()
    );
}
```

### Bài 15 — Hai exception cùng tên

Bean Validation và Hibernate DB constraint có thể cùng tên `ConstraintViolationException` không?

**Đáp án:** Có, nhưng package khác: `jakarta.validation` và `org.hibernate.exception`, ý nghĩa khác.

### Bài 16 — @Column nullable=false

Có tự phát `jakarta.validation.ConstraintViolationException` không?

**Gợi ý:** Không mặc định. Nó là JPA schema/mapping hint; DB có thể từ chối null sau SQL.

### Bài 17 — Unique SKU

Hai transactions cùng query “SKU chưa có” rồi INSERT.

**Gợi ý:** DB UNIQUE constraint phải chặn concurrent duplicates; precheck/custom validator không đủ.

### Bài 18 — @Valid nested

Order có Line quantity=0 và field `List<@Valid OrderLine> lines`.

**Gợi ý:** Khi cascading traversal tới Line, `@Positive` phải phát violation. Cần test loaded/lazy state thực tế.

### Bài 19 — CascadeType.ALL

Chỉ có `@OneToMany(cascade=ALL)` mà không có `@Valid`.

**Gợi ý:** JPA cascade không tự đồng nghĩa Bean Validation cascade theo object graph.

### Bài 20 — @NotEmpty lines

Order.lines là empty list và chỉ có `@Valid`.

**Đáp án:** `@Valid` không yêu cầu có line; thêm `@NotEmpty` nếu bắt buộc.

### Bài 21 — Embedded Address

ShippingAddress là `@Embedded` có street blank.

**Gợi ý:** Thêm `@Valid` trên embedded property để cascade Bean Validation vào Address fields.

### Bài 22 — Container element

List tags không được chứa blank string.

```java
private List<@NotBlank String> tags;
```

**Gợi ý:** Nếu collection cũng bắt buộc có phần tử, thêm `@NotEmpty`.

### Bài 23 — Lazy association

Parent có `@Valid` lên LAZY collection chưa initialized.

**Gợi ý:** Không mặc định mọi child DB row đã được fetch/validated; JPA traversability có thể bỏ qua chưa loaded graph.

### Bài 24 — Custom SKU

Viết constraint cho mẫu `[A-Z0-9-]{3,32}`.

**Gợi ý:** `@Constraint` + `ConstraintValidator<SkuCode,String>`, không gọi database trong `isValid`.

### Bài 25 — Cross-field

Campaign.endAt phải sau startAt.

**Gợi ý:** Class-level constraint hoặc domain method kiểm tra cả hai fields.

### Bài 26 — Class-level property path

Violation hiện gắn class, muốn gắn vào endAt.

**Gợi ý:** `ConstraintValidatorContext` có API tạo property node và custom violation.

### Bài 27 — Generated timestamp

createdAt chỉ được DB default set sau INSERT nhưng có `@NotNull` trong pre-persist.

**Gợi ý:** Có thể fail trước SQL; đổi initialization/validation group hoặc generated-field strategy.

### Bài 28 — @PrePersist callback

Muốn createdAt được gán trước INSERT.

**Gợi ý:** JPA `@PrePersist` có thể khởi tạo audit field; test timing theo provider.

### Bài 29 — Manual validation transient entity

Một Product chưa persist có createdAt null nhưng sẽ được @PrePersist điền.

**Gợi ý:** `validator.validate` trực tiếp không tự gọi JPA @PrePersist; manual result có thể khác lifecycle validation.

### Bài 30 — @PreUpdate và no-op

Load Product rồi commit mà không sửa gì.

**Gợi ý:** Không mặc định pre-update validation đã chạy nếu provider không UPDATE entity.

### Bài 31 — Update chỉ collection

Thêm Line mới nhưng không đổi parent fields.

**Gợi ý:** Child pre-persist có thể xảy ra, parent pre-update không được bảo đảm trong mọi mapping.

### Bài 32 — Bulk JPQL

Bulk UPDATE Product.name="" dù @NotBlank.

**Gợi ý:** Không có entity-level Bean Validation tự động; cần SQL/DB constraints/manual checks.

### Bài 33 — Native SQL

JDBC job INSERT price=-10.

**Gợi ý:** Bean Validation annotations không tự bảo vệ; DB CHECK là lớp cuối.

### Bài 34 — Flush và commit

em.flush() pass validation nhưng commit fail UNIQUE constraint.

**Đáp án:** Flush không phải commit; business operation chưa được xác nhận hoàn tất.

### Bài 35 — Exception timing trong Spring

Service method thay price âm rồi return, caller nhận commit failure.

**Gợi ý:** Transaction interceptor flush/commit sau method body; catch ở setter không đủ.

### Bài 36 — Rollback

Validation fail trong flush; service sửa lại name và thử flush tiếp cùng transaction.

**Gợi ý:** Không nên tiếp tục transaction rollback-only; rollback và attempt mới.

### Bài 37 — Test integration

Đã có Validator unit test pass; có chắc JPA tự validate không?

**Đáp án:** Không. Cần integration test với persistence unit/validation mode và em.persist/flush/commit.

### Bài 38 — Test pre-remove group

Muốn chặn xóa entity lockedForDeletion.

**Gợi ý:** Định nghĩa BeforeDeleteChecks, cấu hình pre-remove group hoặc xử lý service/domain guard tùy use case.

### Bài 39 — DTO vs Entity

Controller dùng `@Valid CreateProductRequest`. Service gán price=-2 do bug sau mapping.

**Gợi ý:** DTO pass không bảo vệ state biến đổi sau đó; JPA lifecycle validation có thể phát hiện, đồng thời cần sửa business bug.

### Bài 40 — Multi-tenant

TenantId có `@NotBlank` nhưng client có thể gửi bất kỳ tenant.

**Gợi ý:** Validation không thay authorization; tenant phải lấy/kiểm tra từ server-side security context.

### Bài 41 — @Version

Hai transactions đều có entity hợp lệ, một bên commit trước.

**Gợi ý:** Bean Validation có thể pass cả hai; `@Version` giúp phát hiện stale write cho bên còn lại.

### Bài 42 — DB constraint vs validation

Tại sao cần CHECK price>=0 dù entity có `@DecimalMin("0.00")`?

**Gợi ý:** Raw SQL, native DML và external writers không chạy JPA lifecycle validation.

### Bài 43 — Import batch

Job nhập 100.000 Products bằng native batch.

**Gợi ý:** Explicit DTO/domain validation + DB constraints; đừng giả định JPA callbacks chạy.

### Bài 44 — PII

`getInvalidValue()` chứa email/secret và API trả raw violation JSON.

**Gợi ý:** Rò rỉ dữ liệu; chỉ trả field/code/message phù hợp, mask invalid value.

### Bài 45 — Idempotency

Request tạo Product commit thành công nhưng response mất; client retry.

**Gợi ý:** Validation không ngăn duplicate business operation; dùng idempotency key/UNIQUE/business reconciliation.

---

## 55. Checklist tích hợp trong dự án

Khi tích hợp Bean Validation với JPA, xác nhận:

- [ ] Project dùng đồng nhất namespace Jakarta hoặc legacy javax.
- [ ] Có Jakarta Validation API và một provider thực thi.
- [ ] JPA validation mode được xác định: AUTO, CALLBACK hoặc NONE.
- [ ] Nếu phụ thuộc automatic validation, có test phát hiện thiếu provider.
- [ ] Pre-persist/pre-update groups được cấu hình đúng, thường gồm Default.
- [ ] Pre-remove groups không bị bật vô tình và chặn việc dọn dữ liệu cũ.
- [ ] Constraints được đặt đúng field/getter theo coding convention.
- [ ] `@NotNull`, `@NotBlank`, `@NotEmpty`, `@Size` được dùng đúng ngữ nghĩa.
- [ ] Monetary constraints dùng `BigDecimal`/`@DecimalMin`/`@Digits` phù hợp.
- [ ] Generated fields/audit timestamps không bị fail vì validation trước INSERT.
- [ ] `@PrePersist`/`@PreUpdate` chỉ làm công việc lifecycle an toàn, không gọi external I/O.
- [ ] Custom validators chủ yếu thuần, không tự mutate entity hoặc query DB tùy tiện.
- [ ] Các invariants cục bộ được thể hiện bằng domain methods/custom constraints.
- [ ] Rules riêng cho publish/approve dùng groups/conditional constraints có chủ đích.
- [ ] `@Valid` được dùng khi thực sự cần cascading validation.
- [ ] Không nhầm `@Valid` với `CascadeType.ALL`.
- [ ] Graph/lazy associations và collection-only updates đã được test.
- [ ] Entity-level validation không được coi là bảo vệ bulk JPQL/Criteria/native SQL.
- [ ] DB có NOT NULL/UNIQUE/CHECK/FK constraints thiết yếu.
- [ ] Có concurrency strategy cho stale writes, quota, stock và cross-row invariants.
- [ ] Transaction rollback đúng khi validation failure.
- [ ] Không phát email/payment/event trước khi commit theo cách không thể bù trừ.
- [ ] API không lộ invalid values/PII hoặc thông tin tenant khác.
- [ ] Có unit tests Validator trực tiếp cho constraints.
- [ ] Có integration tests pre-persist/pre-update/pre-remove đúng persistence unit.
- [ ] Test exception timing với flush/commit theo provider/transaction manager.
- [ ] Test bulk/native bypass và database constraints.
- [ ] Dữ liệu legacy đã được migration/backfill khi bổ sung constraints.
- [ ] Có monitoring validation failure rate, flush/commit latency và lỗi database.

## 56. Bảng tra cứu nhanh

| Câu hỏi | Câu trả lời |
|---|---|
| Annotation Bean Validation namespace hiện đại? | `jakarta.validation.constraints.*` |
| JPA namespace hiện đại? | `jakarta.persistence.*` |
| Provider Bean Validation phổ biến? | Hibernate Validator |
| JPA provider là gì? | Hibernate ORM/EclipseLink hoặc provider khác |
| Kiểm tra không null? | `@NotNull` |
| Kiểm tra String không blank? | `@NotBlank` |
| Kiểm tra collection không rỗng? | `@NotEmpty` |
| Giới hạn độ dài? | `@Size` |
| Giá không âm? | `@DecimalMin("0.00")` |
| Giới hạn chữ số? | `@Digits` |
| Nested object validation? | `@Valid` |
| Validation trực tiếp? | `Validator.validate(entity, groups...)` |
| Custom constraint? | `@Constraint` + `ConstraintValidator` |
| Multi-field rule? | Class-level constraint |
| Default JPA validation nhóm INSERT? | `Default` ở pre-persist |
| Default JPA validation nhóm UPDATE? | `Default` ở pre-update |
| Default JPA validation nhóm DELETE? | Không có groups ở pre-remove |
| Bật auto validation khi có provider? | `ValidationMode.AUTO` |
| Bắt buộc phải có validation provider? | `ValidationMode.CALLBACK` |
| Tắt auto lifecycle validation? | `ValidationMode.NONE` |
| Cấu hình group pre-update? | `jakarta.persistence.validation.group.pre-update` |
| Exception Bean Validation? | `jakarta.validation.ConstraintViolationException` |
| Exception SQL constraint Hibernate? | `org.hibernate.exception.ConstraintViolationException` |
| Có chắc exception tại persist? | Không; có thể flush/commit |
| @PrePersist có phải @NotNull? | Không, là entity lifecycle callback |
| saveAndFlush đã commit? | Không |
| JPA SELECT tự validate entity? | Không theo automatic lifecycle mặc định |
| Bulk JPQL UPDATE tự validate? | Không |
| Native SQL tự validate? | Không |
| @Column(unique=true) là Bean Validation? | Không, schema metadata |
| @Valid có persist child? | Không, JPA cascade là cơ chế khác |
| @Version có validate price? | Không, bảo vệ optimistic concurrency |
| @NotNull ngăn lost update? | Không |
| Violation property path? | `ConstraintViolation.getPropertyPath()` |
| Kiểm tra invalid value trong log? | Không log raw nếu có dữ liệu nhạy cảm |
| Unit test validation thuần? | `validator.validate(...)` |
| Integration test JPA validation? | EntityManager persist/modify/remove + flush/commit |
| Kiểm thử database constraints? | Native/bulk SQL trên test DB |
| Khi violation ở flush? | Rollback transaction attempt, không tiếp tục ghi |

## 57. Tổng kết

Những nguyên tắc quan trọng nhất:

1. **Bean Validation giúp khai báo và đánh giá constraints trên Java objects**, còn JPA cung cấp lifecycle integration để kiểm tra entities trước những thao tác ghi tương ứng.
2. **Pre-persist và pre-update mặc định validate Default group** khi JPA–Bean Validation integration hoạt động; **pre-remove mặc định không validate group nào**.
3. **`AUTO`, `CALLBACK` và `NONE` quyết định cách automatic validation được kích hoạt**; API annotations không đủ nếu thiếu provider hoặc configuration phù hợp.
4. **`persist`/`merge` không đồng nghĩa “validation chắc chắn chạy ngay lập tức”**. Lỗi có thể xuất hiện ở flush/commit hoặc sớm hơn theo provider.
5. **`flush` không phải commit**. Validation pass hoặc SQL đã được gửi không bảo đảm transaction cuối cùng thành công.
6. **`@NotBlank`/`@Size`/`@DecimalMin` là constraints của Bean Validation**, khác với JPA `@Column` metadata và database schema constraints.
7. **`@Valid` chỉ là Bean Validation cascading**, còn `CascadeType` điều khiển persistence lifecycle; hai cơ chế cần được cấu hình độc lập.
8. **Groups cho phép chọn bộ constraints theo event/operation**, nhưng một UPDATE trong JPA không tự đồng nghĩa domain operation như publish/approve.
9. **Custom `ConstraintValidator` nên chủ yếu là phép kiểm tra thuần**, không ghi DB, gọi external service hoặc thay state trong lúc flush.
10. **Bean Validation không bảo đảm uniqueness/lost update/cross-row invariants**; những vấn đề đó cần database UNIQUE/FK/CHECK constraints, transaction isolation, `@Version`, locks hoặc atomic DML.
11. **Bulk JPQL/Criteria DML và native SQL bỏ qua entity-level lifecycle validation**; phải có chiến lược kiểm tra/dữ liệu riêng.
12. **Khi validation failure xuất hiện, rollback transaction**, không tiếp tục flush và commit như chưa có lỗi.
13. **Kiểm thử phải gồm cả Validator unit tests và JPA integration tests**, với pre-persist/pre-update/pre-remove, exception timing và database outcome thực tế.
14. **Thiết kế nhiều lớp: DTO validation → domain rules → entity lifecycle validation → DB constraints**, đồng thời chú ý bảo mật, idempotency, concurrency và các writers ngoài JPA.

**Kết luận:** Tích hợp Bean Validation với vòng đời JPA là cách hiệu quả để biến các quy tắc về giá trị hợp lệ thành một lớp kiểm tra nhất quán ngay trước entity-level persistence operations. Nhưng những annotation như `@NotNull` và `@Valid` chỉ là **một phần của kiến trúc dữ liệu đáng tin cậy**. Khi hiểu chính xác thời điểm pre-persist/pre-update/pre-remove, cấu hình groups, xử lý flush/commit/rollback và giữ database constraints làm lớp bảo vệ cuối, ứng dụng vừa có thể phát hiện lỗi sớm, trả thông báo rõ ràng, vừa duy trì tính toàn vẹn dữ liệu ngay cả khi hệ thống có nhiều transaction, nhiều writers và các thao tác bulk.

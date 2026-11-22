# Thiết kế nhóm kiểm tra trước persist, update và remove trong JPA

Trong một ứng dụng sử dụng **Jakarta Persistence (JPA)**, cùng một entity có thể cần những quy tắc kiểm tra khác nhau tùy **giai đoạn của vòng đời dữ liệu**. Khi tạo mới, ta muốn bảo đảm những thông tin bắt buộc đã có. Khi cập nhật, ta muốn giữ các invariant của bản ghi hiện tại và áp dụng những quy tắc chỉ có ý nghĩa đối với chỉnh sửa. Trước khi xóa, ta có thể cần xác nhận bản ghi đang ở trạng thái cho phép loại bỏ.

Ví dụ hệ thống bán hàng có entity `CatalogItem`:

- **Trước persist:** mã sản phẩm, tên và giá phải hợp lệ; bản ghi được tạo trong trạng thái DRAFT.
- **Trước update:** các invariant chung vẫn đúng; việc thay đổi thông tin của sản phẩm đã phát hành phải tuân thủ quy tắc tương ứng.
- **Trước remove:** chỉ một item ở trạng thái DRAFT hoặc ARCHIVED mới có thể bị xóa theo chính sách đơn giản của ví dụ.

Nếu đặt mọi constraint vào một nhóm duy nhất, các quy tắc chỉ dành cho một giai đoạn dễ bị áp vào giai đoạn khác. Jakarta Bean Validation hỗ trợ **validation groups** — các nhóm đánh dấu bằng interface — và JPA tích hợp chúng vào các sự kiện **pre-persist**, **pre-update** và **pre-remove**.

~~~text
Application service
      |
      v
EntityManager.persist(entity)
           hoặc
managed entity thay đổi và flush
           hoặc
EntityManager.remove(entity)
      |
      v
JPA lifecycle validation integration
      |
      +-- pre-persist -> nhóm kiểm tra khi tạo
      |
      +-- pre-update  -> nhóm kiểm tra khi cập nhật
      |
      +-- pre-remove  -> nhóm kiểm tra trước xóa
      |
      v
Bean Validation provider kiểm tra constraints
      |
      +-- Không có vi phạm -> tiếp tục lifecycle/SQL
      |
      +-- Có vi phạm -> ConstraintViolationException,
                         operation/transaction thất bại
~~~

**Điểm quan trọng:** nhóm validation là cơ chế **chọn bộ quy tắc kiểm tra**, không phải cách mở transaction, không tự phát hiện dữ liệu đã bị người khác thay đổi và không thay thế ràng buộc tại database. Đặc biệt, JPA **mặc định kiểm tra nhóm `Default` trước persist và update, nhưng thường không tự kích hoạt kiểm tra nhóm nào trước remove** nếu chưa cấu hình.

Bài học trình bày đầy đủ cách khai báo groups, gắn constraints, cấu hình thuộc tính validation lifecycle trong `persistence.xml`, thiết kế nhóm và group sequence, phân biệt validation tự động với kiểm tra tại service/API, xử lý cascade, các giới hạn khi xóa và kiểm thử bằng EntityManager thật.

## 1. Vì sao cần phân biệt persist, update và remove?

Một entity có thể đi qua ba thao tác khác nhau:

~~~text
NEW/TRANSIENT
      |
      | EntityManager.persist
      v
MANAGED
      |
      | sửa persistent fields
      v
DIRTY MANAGED
      |
      | flush/commit
      v
DATABASE UPDATE

MANAGED
      |
      | EntityManager.remove
      v
REMOVED
      |
      | flush/commit
      v
DATABASE DELETE
~~~

Các giai đoạn có điều kiện khác nhau. Chẳng hạn:

| Quy tắc | Khi tạo mới | Khi cập nhật | Khi xóa |
| --- | --- | --- | --- |
| Mã SKU không rỗng | Cần | Vẫn là invariant nếu SKU được lưu | Không phải mục tiêu kiểm tra chính |
| Giá không âm | Cần | Cần | Thường không liên quan |
| Mã SKU không trùng | Phải bảo vệ bằng DB UNIQUE | Có thể liên quan nếu cho phép sửa SKU | Không |
| Item chưa phát hành mới được xóa | Không | Không | Cần |
| Không xóa khi có đơn hàng tham chiếu | Không | Không | Cần giao dịch, FK/domain query |

Không nên dùng một annotation tùy tiện để mô tả tất cả những yêu cầu này. Cần phân loại đâu là:

1. Constraint trên **state hiện tại của entity**.
2. Constraint chỉ áp dụng tại một lifecycle phase.
3. Quy tắc cần đọc **những entity khác hoặc database**.
4. Ràng buộc phải được database enforce trong lúc concurrent transactions.

Validation groups chủ yếu giải quyết loại (1) và (2). Service/transaction và DB constraints đảm nhiệm phần còn lại.

## 2. Bean Validation và JPA là hai đặc tả liên quan nhưng không giống nhau

**Jakarta Bean Validation** cung cấp:

- Constraints như `@NotNull`, `@NotBlank`, `@Size`, `@Min`, `@DecimalMin`.
- Interface đánh dấu nhóm kiểm tra.
- `Validator.validate(object, groups...)`.
- Cascade validation bằng `@Valid`.
- Group sequences và group conversion.

**Jakarta Persistence** cung cấp:

- Entity lifecycle và `EntityManager`.
- Persistence context, dirty checking, flush và transaction integration.
- Các property để chỉ định **nhóm Bean Validation nào phải được kiểm tra ở từng lifecycle event**.

Một entity:

~~~java
@Entity
public class CatalogItem {

    @NotBlank
    private String sku;

    // ...
}
~~~

chưa tự cho biết nó sẽ được kiểm tra ở thời điểm nào. Hành vi phụ thuộc JPA validation mode, Bean Validation provider và cấu hình các nhóm cho pre-persist/pre-update/pre-remove.

### Namespace trong bài

Bài dùng:

~~~java
jakarta.persistence.*
jakarta.validation.*
jakarta.validation.constraints.*
~~~

phù hợp Jakarta Persistence/Bean Validation hiện đại. Dự án JPA 2.x cũ có thể sử dụng `javax.persistence.*` và `javax.validation.*`; không trộn namespace giữa hai thế hệ nếu chưa xác minh dependencies/provider.

## 3. Validation group là gì?

Một **group** thường chỉ là marker interface:

~~~java
package com.example.shop.validation;

public interface OnCreate {
}
~~~

Tương tự:

~~~java
package com.example.shop.validation;

public interface OnUpdate {
}
~~~

Và:

~~~java
package com.example.shop.validation;

public interface OnRemove {
}
~~~

Các interface này **không chứa logic thực thi**. Chúng là nhãn để gắn constraints và chọn khi gọi validator.

Ví dụ:

~~~java
@NotBlank(groups = OnCreate.class)
private String sku;
~~~

Constraint chỉ được chọn khi validate một nhóm bao gồm `OnCreate` theo quy tắc Bean Validation. Nếu chỉ validate `OnUpdate.class`, constraint này không tự động được chọn.

### Tên group không có phép màu

Tên `OnCreate`, `OnUpdate` và `OnRemove` là quy ước của dự án, không phải enum JPA built-in. Có thể đặt tên `CreateChecks`, `UpdateChecks`, `DeleteChecks`, nhưng phải sử dụng thống nhất giữa annotations và cấu hình JPA.

## 4. Nhóm Default

Bean Validation định nghĩa:

~~~java
import jakarta.validation.groups.Default;
~~~

Nếu một constraint **không ghi thuộc tính groups**, nó thuộc nhóm `Default`:

~~~java
@NotNull
private BigDecimal price;
~~~

tương đương về nhóm với:

~~~java
@NotNull(groups = Default.class)
private BigDecimal price;
~~~

### Default không tự nằm trong mọi nhóm khác

Giả sử:

~~~java
@NotNull
private BigDecimal price;

@NotBlank(groups = OnCreate.class)
private String sku;
~~~

Thao tác:

~~~java
validator.validate(item, OnCreate.class);
~~~

**không mặc nhiên** kiểm tra `@NotNull` của `price`, vì nó thuộc nhóm `Default` chứ không phải `OnCreate`.

Để kiểm tra cả hai:

~~~java
validator.validate(
    item,
    Default.class,
    OnCreate.class
);
~~~

Hoặc sử dụng group sequence/quan hệ kế thừa groups được thiết kế rõ.

Đây là sai lầm phổ biến khi thay cấu hình `pre-persist` từ `Default` sang chỉ `OnCreate`: những constraints không khai báo groups có thể **bị bỏ qua ngoài ý muốn**.

## 5. Không viết mọi constraint hai lần nếu không cần

Có hai chiến lược thông dụng.

### Chiến lược A — Constraints chung thuộc Default

~~~java
@NotBlank
private String name;

@NotNull
@DecimalMin("0.00")
private BigDecimal price;

@AssertTrue(groups = OnRemove.class)
public boolean isDeletionAllowed() {
    return status == ItemStatus.DRAFT
        || status == ItemStatus.ARCHIVED;
}
~~~

Sau đó cấu hình pre-persist và pre-update **đều bao gồm Default**, còn pre-remove dùng OnRemove.

Ưu điểm: một invariant cơ bản có thể được diễn đạt đúng một nơi.

### Chiến lược B — Khai báo rõ constraint cho nhiều nhóm

~~~java
@NotBlank(groups = {
    OnCreate.class,
    OnUpdate.class
})
private String name;
~~~

Ưu điểm: nhìn annotation biết giai đoạn nào áp dụng. Nhược điểm: dễ lặp lại tên nhiều nhóm, khó bảo trì khi thêm nhóm mới.

### Nên chọn gì?

Với entity nghiệp vụ có nhiều invariant chung, **Default cho quy tắc luôn đúng**, nhóm riêng cho quy tắc khác theo sự kiện thường dễ duy trì hơn. Nếu dự án muốn groups hoàn toàn tách nhau, cần chính sách rõ để không bỏ quên các constraints chung.

## 6. Cấu hình ba lifecycle validation properties của JPA

JPA sử dụng các property keys:

~~~text
jakarta.persistence.validation.group.pre-persist
jakarta.persistence.validation.group.pre-update
jakarta.persistence.validation.group.pre-remove
~~~

Chúng chỉ định **những nhóm constraint được Bean Validation kiểm tra khi JPA thực hiện lifecycle validation tương ứng**.

| Property | Sự kiện | Mục đích |
| --- | --- | --- |
| `jakarta.persistence.validation.group.pre-persist` | Trước persist/INSERT theo lifecycle | Chọn nhóm kiểm tra trước tạo mới |
| `jakarta.persistence.validation.group.pre-update` | Trước update entity theo lifecycle | Chọn nhóm kiểm tra trước UPDATE |
| `jakarta.persistence.validation.group.pre-remove` | Trước remove/DELETE theo lifecycle | Chọn nhóm kiểm tra trước xóa |

### Giá trị mặc định quan trọng

Trong cấu hình Bean Validation/JPA thông thường:

- **pre-persist** kiểm tra nhóm `jakarta.validation.groups.Default`.
- **pre-update** kiểm tra nhóm `jakarta.validation.groups.Default`.
- **pre-remove** **mặc định không kiểm tra nhóm nào**.

Do đó, chỉ thêm:

~~~java
@AssertTrue(groups = OnRemove.class)
public boolean isDeletionAllowed() {
    return status == ItemStatus.DRAFT;
}
~~~

**không đủ để tin rằng EntityManager.remove() sẽ kiểm tra OnRemove**. Phải cấu hình nhóm pre-remove hoặc xác thực tường minh tại service.

## 7. Cấu hình persistence.xml cho ba nhóm

Giả sử groups đặt trong package:

~~~text
com.example.shop.validation.OnCreate
com.example.shop.validation.OnUpdate
com.example.shop.validation.OnRemove
~~~

Ví dụ fragment `persistence.xml`:

~~~xml
<persistence
    xmlns="https://jakarta.ee/xml/ns/persistence"
    version="3.1">
  <persistence-unit name="shopPU"
                    transaction-type="RESOURCE_LOCAL">

    <validation-mode>AUTO</validation-mode>

    <properties>
      <property
          name="jakarta.persistence.validation.group.pre-persist"
          value="jakarta.validation.groups.Default,com.example.shop.validation.OnCreate"/>

      <property
          name="jakarta.persistence.validation.group.pre-update"
          value="jakarta.validation.groups.Default,com.example.shop.validation.OnUpdate"/>

      <property
          name="jakarta.persistence.validation.group.pre-remove"
          value="com.example.shop.validation.OnRemove"/>
    </properties>
  </persistence-unit>
</persistence>
~~~

Ví dụ này chọn:

~~~text
CREATE:  Default + OnCreate
UPDATE:  Default + OnUpdate
REMOVE:  OnRemove
~~~

### Chú ý

Tên class trong property là **fully qualified class names**, phân cách bằng dấu phẩy; phải đúng package đã compile vào classpath. Fragment này không bao gồm JDBC properties, provider hoặc entity scanning, nên cần bổ sung cấu hình persistence unit thực tế.

### Tại sao pre-remove không có Default ở ví dụ?

Default thường chứa các quy tắc về dữ liệu cần tồn tại cho một entity hợp lệ, không nhất thiết là điều kiện xóa. Nếu xóa một row legacy có field sai nhưng business cho phép dọn dẹp, việc vô tình chạy Default trên remove có thể chặn operation không cần thiết.

Nếu business yêu cầu Default khi remove, có thể cấu hình rõ. **Lựa chọn nhóm nào cho remove là quyết định nghiệp vụ**, không phải nghĩa vụ sao chép pre-update.

## 8. Đặt properties ở đâu ngoài persistence.xml?

Tùy JPA bootstrap và môi trường quản lý EntityManagerFactory, các persistence unit properties có thể được cung cấp qua cấu hình chương trình/framework, ví dụ khi tạo EntityManagerFactory:

~~~java
Map<String, Object> properties = new HashMap<>();

properties.put(
    "jakarta.persistence.validation.group.pre-persist",
    "jakarta.validation.groups.Default,"
        + "com.example.shop.validation.OnCreate");

properties.put(
    "jakarta.persistence.validation.group.pre-update",
    "jakarta.validation.groups.Default,"
        + "com.example.shop.validation.OnUpdate");

properties.put(
    "jakarta.persistence.validation.group.pre-remove",
    "com.example.shop.validation.OnRemove");

EntityManagerFactory emf =
    Persistence.createEntityManagerFactory(
        "shopPU", properties);
~~~

Các phương thức bootstrap và property overrides phải tuân theo provider/container thực tế. Đối với Spring Boot, cần cấu hình những properties được chuyển đến **JPA provider**, không nhầm với các Spring MVC validation options.

### Không dùng Query.setHint để cấu hình pre-remove group toàn hệ thống

Validation group cho lifecycle events là một cấu hình persistence unit/EMF integration; không phải mọi `Query.setHint()` đều có ý nghĩa thay thế nó.

Nếu muốn kiểm tra một operation cụ thể với nhóm khác, gọi `Validator.validate(entity, Group.class)` tường minh tại service thường dễ hiểu hơn việc dùng một property không được provider hỗ trợ ở query scope.

## 9. ValidationMode: AUTO, CALLBACK, NONE

JPA có:

~~~java
import jakarta.persistence.ValidationMode;
~~~

Các chế độ:

| Mode | Ý nghĩa khái quát |
| --- | --- |
| `AUTO` | Tích hợp validation khi có Bean Validation provider phù hợp, theo quy tắc môi trường |
| `CALLBACK` | Yêu cầu callback-style validation; thiếu provider phù hợp có thể khiến bootstrap thất bại |
| `NONE` | Vô hiệu hóa tự động Bean Validation integration của JPA |

Trong XML:

~~~xml
<validation-mode>AUTO</validation-mode>
~~~

### NONE có vô hiệu hóa mọi validation trong ứng dụng không?

Không. Nếu service gọi:

~~~java
validator.validate(item, OnCreate.class);
~~~

thì đây là **kiểm tra Bean Validation tường minh**; `ValidationMode.NONE` của persistence unit không phải công tắc xóa mọi Validator trong ứng dụng.

### AUTO có nghĩa luôn có provider không?

Không. Phải có Bean Validation API/provider và integration tương thích. Một ứng dụng có JPA nhưng không có implementation Bean Validation phù hợp có thể không thực thi các constraints tự động trong AUTO.

Vì vậy, nếu production dựa vào lifecycle validation để bảo vệ dữ liệu, cần **integration test thực**; đừng chỉ nhìn annotations rồi tin rằng chúng đã chạy.

## 10. Chuẩn bị Maven dependencies

Ví dụ với Jakarta Persistence và Bean Validation:

~~~xml
<dependencies>
  <dependency>
    <groupId>jakarta.persistence</groupId>
    <artifactId>jakarta.persistence-api</artifactId>
    <version><!-- phiên bản phù hợp runtime --></version>
  </dependency>

  <dependency>
    <groupId>jakarta.validation</groupId>
    <artifactId>jakarta.validation-api</artifactId>
    <version><!-- phiên bản phù hợp runtime --></version>
  </dependency>

  <!-- Thêm JPA provider như Hibernate ORM/EclipseLink
       và Bean Validation implementation như Hibernate Validator
       tương thích với Jakarta stack của dự án. -->
</dependencies>
~~~

Đây là **mẫu định hướng**, không phải POM copy-paste chạy ngay. Không dùng ký hiệu placeholder trong bản build thực; chọn versions theo BOM/framework và xác nhận provider integrations.

### Bean Validation implementation khác JPA provider

Hibernate ORM và Hibernate Validator là hai dự án/thành phần có vai trò khác nhau:

- Hibernate ORM cung cấp JPA persistence.
- Hibernate Validator cung cấp Bean Validation implementation.

Có một tên “Hibernate” chung không nghĩa JPA provider mặc định đã có mọi Bean Validation implementation dependency.

## 11. Thiết kế ví dụ xuyên suốt: CatalogItem

Ta xây mô hình sản phẩm có trạng thái:

~~~java
package com.example.shop.domain;

public enum ItemStatus {
    DRAFT,
    PUBLISHED,
    ARCHIVED
}
~~~

DDL PostgreSQL minh họa:

~~~sql
CREATE TABLE catalog_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    sku VARCHAR(80) NOT NULL,
    name VARCHAR(160) NOT NULL,
    price NUMERIC(14, 2) NOT NULL,
    status VARCHAR(20) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT uq_item_tenant_sku
      UNIQUE (tenant_id, sku),

    CONSTRAINT ck_item_price
      CHECK (price >= 0),

    CONSTRAINT ck_item_status
      CHECK (status IN (
        'DRAFT', 'PUBLISHED', 'ARCHIVED'
      ))
);
~~~

Các ràng buộc `NOT NULL`, `UNIQUE`, `CHECK` tồn tại ở database và bảo vệ tất cả writers phù hợp, kể cả JDBC, native SQL hoặc một service khác không chạy Bean Validation.

### Lý do có @Version

Nếu hai users cập nhật cùng CatalogItem ở các transactions khác nhau, Bean Validation không phát hiện lost update. `@Version` có thể giúp kiểm tra optimistic concurrency trên đường ghi JPA managed entity.

Validation và version giải quyết hai loại vấn đề khác nhau.

## 12. Marker interfaces cho các sự kiện

~~~java
package com.example.shop.validation;

public interface OnCreate {
}
~~~

~~~java
package com.example.shop.validation;

public interface OnUpdate {
}
~~~

~~~java
package com.example.shop.validation;

public interface OnRemove {
}
~~~

Những groups này được tham chiếu bởi constraints và persistence configuration, không phải JPA lifecycle annotations.

### Vì sao không tạo một enum?

Bean Validation groups được xác định bằng **Class/interface tokens**, không phải một enum:

~~~java
validator.validate(item, OnCreate.class);
~~~

Không thay được bằng:

~~~java
validator.validate(item, Operation.CREATE); // Sai API.
~~~

Muốn giao tiếp với code domain bằng một enum operation, application có thể map enum sang nhóm, nhưng bản thân Bean Validation API nhận `Class<?>... groups`.

## 13. Entity với constraints chung và nhóm riêng

~~~java
package com.example.shop.domain;

import com.example.shop.validation.OnCreate;
import com.example.shop.validation.OnUpdate;
import com.example.shop.validation.OnRemove;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;

@Entity
@Table(name = "catalog_items")
public class CatalogItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotNull
    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @NotBlank
    @Size(max = 80)
    @Column(nullable = false, length = 80)
    private String sku;

    @NotBlank
    @Size(max = 160)
    @Column(nullable = false, length = 160)
    private String name;

    @NotNull
    @DecimalMin("0.00")
    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    @NotNull
    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private ItemStatus status;

    @Version
    @Column(nullable = false)
    private Long version;

    protected CatalogItem() {
    }

    public CatalogItem(
            Long tenantId,
            String sku,
            String name,
            BigDecimal price) {
        this.tenantId = tenantId;
        this.sku = sku;
        this.name = name;
        this.price = price;
        this.status = ItemStatus.DRAFT;
    }

    @AssertTrue(
        groups = OnCreate.class,
        message = "Item mới phải ở trạng thái DRAFT")
    public boolean isNewItemInDraft() {
        return status == ItemStatus.DRAFT;
    }

    @AssertTrue(
        groups = OnRemove.class,
        message = "Chỉ DRAFT hoặc ARCHIVED được xóa")
    public boolean isDeletionAllowed() {
        return status == ItemStatus.DRAFT
            || status == ItemStatus.ARCHIVED;
    }

    public Long getId() { return id; }
    public Long getTenantId() { return tenantId; }
    public String getSku() { return sku; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
    public ItemStatus getStatus() { return status; }
    public Long getVersion() { return version; }

    public void changeName(String nextName) {
        this.name = nextName;
    }

    public void changePrice(BigDecimal nextPrice) {
        this.price = nextPrice;
    }

    public void publish() {
        if (status != ItemStatus.DRAFT) {
            throw new IllegalStateException(
                "Chỉ DRAFT được publish");
        }
        status = ItemStatus.PUBLISHED;
    }

    public void archive() {
        if (status != ItemStatus.PUBLISHED) {
            throw new IllegalStateException(
                "Chỉ PUBLISHED được archive");
        }
        status = ItemStatus.ARCHIVED;
    }
}
~~~

### Ý nghĩa nhóm trong entity này

- Các `@NotBlank`, `@NotNull`, `@DecimalMin`, `@Size` thuộc **Default**. Chúng là invariants chung cho bản ghi khi được persist hoặc update.
- `isNewItemInDraft()` thuộc **OnCreate**. Đây là yêu cầu chỉ riêng khi tạo mới.
- `isDeletionAllowed()` thuộc **OnRemove**. Đây là yêu cầu khi xóa.
- `OnUpdate` hiện chưa có constraint riêng trong bản ví dụ tối thiểu; nhóm vẫn được định nghĩa để mở rộng chính sách nếu cần.

### Cẩn trọng với property access của validation

`@AssertTrue` đặt trên JavaBean getter `isDeletionAllowed()` là một constraint về giá trị Boolean được tính. Với JPA mapping field access (do `@Id` trên field), nó không cần trở thành column. Không cần truy vấn database trong getter.

### Vì sao không đặt @Null(groups=OnCreate) lên id?

Với ID sinh bởi database/provider, thời điểm generated ID được gán so với lifecycle validation có thể khác giữa generation strategies. Quy tắc “client không được tự cấp id” nên kiểm tra trên **create request DTO**, không dựa duy nhất vào entity `@Null(id)` ở pre-persist.

## 14. Định nghĩa constraint chỉ dành cho update

Ví dụ nghiệp vụ muốn một catalog item khi cập nhật phải có `name` tối thiểu 5 ký tự, trong khi lúc tạo DRAFT cho phép tên ngắn để lưu nháp:

~~~java
@NotBlank
@Size(max = 160)
@Size(
    min = 5,
    groups = OnUpdate.class,
    message = "Tên khi cập nhật phải từ 5 ký tự")
private String name;
~~~

Khi pre-persist cấu hình `Default + OnCreate`:

~~~text
Tên "Ab" không rỗng, <=160 -> có thể hợp lệ theo nhóm này.
~~~

Khi pre-update cấu hình `Default + OnUpdate`:

~~~text
Tên "Ab" -> vi phạm @Size(min=5).
~~~

### Lưu ý về chính sách thực tế

Đây là một ví dụ để minh họa **khác biệt theo phase**. Quy tắc “tên mới tạo ngắn hơn tên cập nhật” có thể không hợp lý với mọi domain. Phải có lý do nghiệp vụ trước khi tách nhóm, không chia groups chỉ để có nhiều interfaces.

### Chú ý constraints của cùng loại

Nhiều constraints cùng loại trên một field được Bean Validation hỗ trợ thông qua annotations repeatable/composition ở các phiên bản tương ứng. Nếu môi trường cũ không hỗ trợ syntax lặp trực tiếp, có thể dùng container annotation hoặc chuyển quy tắc vào class-level constraint.

## 15. Bean Validation kiểm tra state entity, không kiểm tra “chỉ field dirty”

Với JPA `pre-update`:

~~~java
item.changePrice(new BigDecimal("125000.00"));
~~~

Khi validation chạy, nó áp nhóm `Default + OnUpdate` lên **state entity**, không tự giới hạn constraints ở riêng `price` chỉ vì Java code sửa price.

Điều này có ý nghĩa:

- Nếu `name` sai constraint OnUpdate dù không được sửa trong transaction hiện tại, update price vẫn có thể fail.
- Nếu một entity legacy chứa dữ liệu sai từ trước, việc chỉnh bất kỳ property có thể bị chặn.
- Validation group không phải một hệ thống biết “trường nào client đã gửi” hay “delta nào changed”.

### Nếu chỉ muốn validate một field mới từ request

Làm ở DTO/command trước khi đưa vào entity:

~~~java
public record ChangePriceRequest(
    @NotNull
    @DecimalMin("0.00")
    BigDecimal price
) {
}
~~~

Sau đó vẫn cần giữ các **invariants cuối cùng của entity** và DB constraints. Không nên tắt validation trên state entity chỉ để né một bản ghi legacy lỗi mà chưa có chiến lược migration.

## 16. Từ API request đến lifecycle validation

Một request tạo item:

~~~json
{
  "sku": "BOOK-JPA",
  "name": "Java Persistence",
  "price": 150000.00
}
~~~

Controller có thể kiểm tra DTO đầu vào trước:

~~~java
public record CreateCatalogItemRequest(
    @NotBlank String sku,
    @NotBlank String name,
    @NotNull @DecimalMin("0.00") BigDecimal price
) {
}
~~~

Service tạo entity rồi gọi:

~~~java
CatalogItem item = new CatalogItem(
    tenantId,
    request.sku(),
    request.name(),
    request.price()
);

em.persist(item);
~~~

Khi flush/commit, JPA lifecycle validation kiểm tra các nhóm pre-persist đã cấu hình.

### Tại sao cần hai lớp kiểm tra?

**DTO validation** cung cấp lỗi sớm/gắn với request contract. **Entity validation** kiểm tra persistent state trước khi được ghi, kể cả khi entity được tạo từ một batch job không đi qua HTTP controller. **DB constraints** bảo vệ dữ liệu trước mọi writer đi qua database.

Không có lớp nào thay thế hoàn toàn các lớp còn lại.

## 17. @Valid và @Validated trong Spring không đồng nghĩa lifecycle groups

Trong Spring MVC:

~~~java
@PostMapping("/catalog-items")
public ResponseEntity<?> create(
        @Valid @RequestBody CreateCatalogItemRequest request) {
    // ...
}
~~~

`@Valid` kích hoạt Bean Validation phù hợp trên DTO request qua Spring MVC integration. Nó **không phải property JPA pre-persist**.

Nếu dùng Spring `@Validated`:

~~~java
@Validated(OnCreate.class)
@RequestBody CreateCatalogItemRequest request
~~~

thì đó là cách Spring chọn nhóm validation của **request argument**, không có nghĩa JPA EntityManager sẽ tự lấy OnCreate trong mọi persistence operation. Các cấu hình độc lập.

### @Validated là Spring-specific

`org.springframework.validation.annotation.Validated` thuộc Spring, còn `jakarta.validation.Valid` thuộc Bean Validation. Với Java/Jakarta EE thuần, sử dụng Validator và các integration của framework tương ứng.

### Không đặt entity làm request DTO mặc định

Một entity có `id`, `tenantId`, `version`, associations và server-controlled fields. Nhận thẳng JSON thành entity có thể mở cửa cho over-posting và sai authorization. DTO tách rõ dữ liệu client được phép cung cấp.

## 18. Kiểm tra thủ công bằng Validator

JPA validation lifecycle có thể xảy ra ở flush/commit. Đôi lúc service muốn kiểm tra sớm để trả lỗi cho caller trước khi thực hiện một số công việc khác.

~~~java
import jakarta.validation.Validator;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.groups.Default;

Set<ConstraintViolation<CatalogItem>> violations =
    validator.validate(
        item,
        Default.class,
        OnCreate.class
    );

if (!violations.isEmpty()) {
    throw new IllegalArgumentException(
        "Item không đạt điều kiện tạo mới");
}
~~~

Ở đây `validator` thường được inject bởi CDI/Spring/Bean Validation integration, hoặc lấy qua `ValidatorFactory`.

### Validator.validate() có ghi database không?

Không. Nó kiểm tra constraints trên object theo group được yêu cầu; bản thân API không phải EntityManager.flush. Một custom ConstraintValidator có thể được viết để gọi DB nhưng đó là lựa chọn nhiều rủi ro và không phải chức năng mặc định của Validator.

### Có thể kiểm tra sớm nhưng JPA vẫn kiểm tra khi ghi

~~~text
Service validate() -> OK
Service thay đổi thêm một property
flush() -> Entity validation phát hiện state không hợp lệ
~~~

Đây là lý do manual validation không nhất thiết thay thế lifecycle validation. Nếu business cần bảo vệ persistent state, hãy để JPA/DB checks ở boundary ghi.

## 19. Nhóm được chọn thế nào khi gọi Validator?

Các cách:

~~~java
validator.validate(item);
~~~

Đồng nghĩa validate nhóm Default.

~~~java
validator.validate(item, OnCreate.class);
~~~

Chỉ chọn OnCreate và groups liên quan theo inheritance/sequence.

~~~java
validator.validate(
    item,
    Default.class,
    OnCreate.class
);
~~~

Chọn Default và OnCreate.

### Đừng dùng String thay Class với Validator API

Sai:

~~~java
validator.validate(item, "OnCreate");
~~~

Đúng:

~~~java
validator.validate(item, OnCreate.class);
~~~

JPA XML property dùng **string class names**, còn Validator Java API dùng **Class<?> group tokens**.

## 20. Kiểm tra từng property và validateValue

Bean Validation có:

~~~java
validator.validateProperty(
    item,
    "name",
    OnUpdate.class
);
~~~

để kiểm tra một property được chỉ định theo nhóm.

Cũng có:

~~~java
validator.validateValue(
    CatalogItem.class,
    "price",
    new BigDecimal("-10.00"),
    Default.class
);
~~~

để kiểm tra giá trị giả định theo constraints của property, không cần áp state đó lên entity managed.

### Khi nào hữu ích?

Một form muốn kiểm tra “giá mới có hợp lệ theo constraint không?” trước khi gọi mutation.

### Giới hạn

- Cross-field/class-level invariants không được bao phủ như validate toàn object.
- Không biết transaction state hoặc DB uniqueness.
- Validation của một property không bảo đảm entity cuối cùng hợp lệ.

Vì vậy, các API này hỗ trợ feedback nhưng **không thay thế validate toàn state và database constraints tại commit**.

## 21. Group inheritance

Groups cũng có thể kế thừa:

~~~java
package com.example.shop.validation;

public interface BasicChecks {
}
~~~

~~~java
package com.example.shop.validation;

public interface OnUpdate extends BasicChecks {
}
~~~

Khi một group được yêu cầu, quy tắc Bean Validation về group inheritance có thể khiến constraints gắn trên super-interface group được xét cùng với nhóm kế thừa.

Ví dụ:

~~~java
@NotNull(groups = BasicChecks.class)
private BigDecimal price;
~~~

Khi validate:

~~~java
validator.validate(item, OnUpdate.class);
~~~

constraint BasicChecks cũng có thể được chọn theo group inheritance.

### Tại sao không dùng inheritance vô tội vạ?

Nếu OnRemove kế thừa một group chứa tất cả CreateChecks, thao tác xóa có thể bị chặn vì thiếu các fields vốn không cần cho xóa. Hãy thiết kế cây nhóm từ **ý nghĩa nghiệp vụ**, không phải chỉ để giảm ký tự annotations.

## 22. Group sequence để kiểm tra theo giai đoạn

Trong một operation, có thể muốn kiểm tra **constraints cơ bản trước**, rồi mới kiểm tra constraints phức tạp.

~~~java
package com.example.shop.validation;

import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

@GroupSequence({
    Default.class,
    OnCreate.class
})
public interface CreateChecksInOrder {
}
~~~

Gọi:

~~~java
validator.validate(
    item,
    CreateChecksInOrder.class
);
~~~

Ý nghĩa: kiểm tra nhóm Default trước. Nếu nhóm đó có vi phạm, Bean Validation **không tiếp tục** nhóm OnCreate trong sequence.

### Tại sao hữu ích?

Ví dụ:

1. Kiểm tra name không rỗng, price không null.
2. Chỉ nếu hợp lệ mới kiểm tra một constraint create-specific phức tạp.

### Không bảo đảm thứ tự từng constraint trong cùng group

Group sequence xác định thứ tự **giữa các nhóm**, không phải “@NotNull trước @Size trước @DecimalMin” trên từng property trong cùng group.

Nếu có nhiều violations trong một group, API không hứa thứ tự phát hiện/duyệt là thứ tự annotation xuất hiện.

## 23. Group sequence cho update

Tương tự:

~~~java
@GroupSequence({
    Default.class,
    OnUpdate.class
})
public interface UpdateChecksInOrder {
}
~~~

Service:

~~~java
Set<ConstraintViolation<CatalogItem>> violations =
    validator.validate(
        item,
        UpdateChecksInOrder.class
    );
~~~

### Có thể cấu hình group sequence làm lifecycle group không?

Có thể tham chiếu một group sequence interface khi chọn groups cho operation ở những môi trường/provider hỗ trợ theo Bean Validation rules, nhưng cần xác định semantics và kiểm thử JPA integration thật.

Ví dụ, cấu hình:

~~~xml
<property
    name="jakarta.persistence.validation.group.pre-update"
    value="com.example.shop.validation.UpdateChecksInOrder"/>
~~~

để dùng nhóm sequence làm gốc kiểm tra trong pre-update.

### Khi nào không cần sequence?

Nếu chỉ có vài constraints nhanh, cấu hình `Default,OnUpdate` đã đủ. Một sequence là hợp lý khi thứ tự các phases có ý nghĩa, ví dụ muốn ngăn một constraint validator tốn kém chạy khi dữ liệu cơ bản sai.

## 24. Không đặt Default và group sequence chồng chéo một cách tùy tiện

Giả sử:

~~~java
@GroupSequence({Default.class, OnCreate.class})
public interface CreateChecksInOrder {
}
~~~

và gọi:

~~~java
validator.validate(
    item,
    Default.class,
    CreateChecksInOrder.class
);
~~~

Có thể làm thiết kế trở nên khó suy luận: Default được yêu cầu trực tiếp lại cũng nằm trong sequence. Bean Validation loại bỏ một số duplicate validation theo rules, nhưng **không nên dựa vào việc danh sách nhóm chồng lắp tạo ra thứ tự tùy ý**.

### Chọn một contract nhất quán

- Nếu cần thứ tự: validate **sequence interface**.
- Nếu không cần thứ tự: validate các group độc lập.

### Default group sequence ở entity class là trường hợp riêng

Bean Validation còn cho phép **định nghĩa lại Default group sequence trên class**, với yêu cầu group sequence có chính class đó theo quy tắc đặc tả. Đây không phải cùng việc tạo một interface sequence như ví dụ.

Không sao chép:

~~~java
@GroupSequence({Default.class, OnCreate.class})
@Entity
public class CatalogItem { ... }
~~~

để định nghĩa lại Default sequence tại class: cấu hình đó không đúng quy tắc thay thế Default của class. Khi cần class-level default redefinition, nghiên cứu đúng `@GroupSequence({CatalogItem.class, ...})` và các hệ quả cascade; không coi đó là bước bắt buộc cho lifecycle groups.

## 25. Khi nào OnCreate và OnUpdate chỉ nên nằm ở DTO?

Một entity có thể có cùng invariant không đổi suốt vòng đời, nhưng **request contract** khác nhau:

~~~text
CreateItemRequest:
  sku, name, price đều bắt buộc

PatchItemRequest:
  name và price là optional
  field vắng mặt nghĩa "không thay đổi"
~~~

Nếu đặt `@NotNull(groups=OnUpdate.class)` lên entity.price, pre-update kiểm tra **state cuối cùng của entity**, không biết field `price` có được gửi trong PATCH hay không.

### Thiết kế tốt hơn

DTO create:

~~~java
public record CreateItemRequest(
    @NotBlank String sku,
    @NotBlank String name,
    @NotNull @DecimalMin("0.00") BigDecimal price
) {
}
~~~

DTO patch:

~~~java
public record ChangeItemNameRequest(
    @NotBlank
    @Size(max = 160)
    String name,

    @NotNull
    Long expectedVersion
) {
}
~~~

Entity vẫn có các constraints Default cho invariant chung. Dùng service áp thay đổi vào entity managed sau khi xác minh quyền/version, rồi JPA kiểm tra state khi flush.

### Vì sao quan trọng?

**Validation groups theo lifecycle không phải validation groups theo HTTP method một-một.** Một operation PATCH có thể dẫn tới INSERT, UPDATE hoặc không ghi gì tùy use case; ngược lại, một batch writer không có HTTP vẫn cần entity lifecycle validation.

## 26. Ràng buộc bất biến không nhất thiết chỉ dùng Bean Validation

Một Product đã PUBLISHED không được đổi SKU. Có nên thêm:

~~~java
@AssertTrue(groups = OnUpdate.class)
public boolean isSkuUnchanged() { ... }
~~~

Không đơn giản, vì entity hiện tại thường chỉ có **giá trị SKU mới**, không lưu một snapshot “giá trị SKU cũ” portable để so sánh. Validator trên state không biết mọi lịch sử thay đổi.

### Hướng xử lý

- Không cung cấp domain method đổi SKU cho entity đã PUBLISHED.
- Service xác minh trạng thái và version trước khi gọi mutation.
- Nếu cần bảo vệ ở DB, dùng trigger/constraints hoặc mô hình dữ liệu tương ứng.
- Với concurrent writes, dùng optimistic locking/pessimistic lock theo use case.

**Nhóm OnUpdate không tự biết một field có bị thay đổi hay không**. Đó là đặc tính quan trọng khi thiết kế constraints.

## 27. PrePersist được kiểm tra lúc nào?

Trong JPA, việc gọi:

~~~java
em.persist(item);
~~~

đưa entity mới vào trạng thái managed và lên lịch/triển khai persistence theo generation strategy/provider. **SQL INSERT và lifecycle validation có thể xảy ra tại flush hoặc thời điểm khác theo JPA/provider**, không thể suy ra chỉ từ việc `persist()` không ném exception rằng bản ghi đã hợp lệ và commit.

Ví dụ:

~~~java
tx.begin();
em.persist(item);

// Với nhiều provider, validation/INSERT có thể
// chưa hoàn tất tại đây.

em.flush();
tx.commit();
~~~

### Khi nào nhận ConstraintViolationException?

Có thể trong:

- `persist()`/flush path nếu provider thực hiện validation sớm.
- `em.flush()`.
- `tx.commit()` khi flush được kích hoạt tự động.

**Code xử lý lỗi phải bao quanh transaction boundary**, không chỉ bao quanh lời gọi setter hoặc persist.

## 28. PreUpdate chỉ áp dụng khi có lifecycle UPDATE tương ứng

Một transaction:

~~~java
CatalogItem item = em.find(
    CatalogItem.class, itemId);

// Không thay đổi gì.

tx.commit();
~~~

không có lý do bắt buộc mọi provider phải thực hiện một SQL UPDATE chỉ để kiểm tra nhóm OnUpdate.

### Nếu entity dirty

~~~java
item.changePrice(new BigDecimal("125000.00"));
em.flush();
~~~

provider thường thực hiện update path và áp lifecycle validation pre-update nếu tích hợp Bean Validation được bật.

### Đừng dùng pre-update làm validation cho mọi GET

Nếu muốn kiểm tra entity vừa load, dùng `Validator.validate()` tường minh ở service hoặc cơ chế kiểm tra dữ liệu riêng. Lifecycle pre-update không phải generic “validate mỗi khi truy cập entity”.

## 29. PreRemove mặc định thường không kiểm tra nhóm nào

Đây là phần dễ bị bỏ qua.

Khai báo:

~~~java
@AssertTrue(groups = OnRemove.class)
public boolean isDeletionAllowed() {
    return status == ItemStatus.DRAFT
        || status == ItemStatus.ARCHIVED;
}
~~~

không đủ. Nếu không cấu hình:

~~~text
jakarta.persistence.validation.group.pre-remove
~~~

thì JPA lifecycle validation thường **không kiểm tra nhóm nào khi remove theo mặc định**.

### Cấu hình rõ

~~~xml
<property
    name="jakarta.persistence.validation.group.pre-remove"
    value="com.example.shop.validation.OnRemove"/>
~~~

### Vì sao mặc định lại khác?

Khi xóa, nhiều ràng buộc về tính hợp lệ của object trước khi lưu không còn thiết yếu. Ví dụ, một bản ghi legacy thiếu name có thể cần bị xóa để làm sạch dữ liệu. Tự động kiểm tra mọi Default constraints trước remove có thể ngăn cleanup.

Tùy domain, muốn kiểm tra remove phải **chủ động thiết kế**.

## 30. Remove trong service: transaction, trạng thái và quyền

Một service JPA resource-local:

~~~java
public void deleteItem(
        EntityManager em,
        long tenantId,
        long itemId) {

    CatalogItem item =
        em.find(CatalogItem.class, itemId);

    if (item == null
            || !Objects.equals(
                item.getTenantId(), tenantId)) {
        throw new ItemNotFoundException(itemId);
    }

    // Có thể kiểm tra rõ nghiệp vụ tại đây,
    // không chỉ dựa vào cấu hình callback.
    if (!item.isDeletionAllowed()) {
        throw new IllegalStateException(
            "Trạng thái hiện tại không cho phép xóa");
    }

    em.remove(item);
}
~~~

Method trên **giả định EntityManager đã tham gia transaction phù hợp**, và `ItemNotFoundException` là custom unchecked exception của ứng dụng.

### Tại sao kiểm tra cả service lẫn pre-remove?

Service có thể trả lỗi nghiệp vụ rõ ràng và kiểm tra tenant/ACL, trong khi Bean Validation pre-remove cung cấp **lớp kiểm tra state bổ sung** cho các đường xóa qua JPA managed entity khác.

Nhưng nếu business rule cần query xem còn Booking/OrderLine tham chiếu hay không, phải thực hiện trong transaction thích hợp và vẫn dựa vào FK/constraints cho tính toàn vẹn dưới concurrency.

## 31. Xóa cần kiểm tra các entity liên quan: giới hạn của group validation

Ví dụ:

> Không được xóa CatalogItem nếu đã có OrderLine tham chiếu.

Một `@AssertTrue(groups=OnRemove.class)` chỉ nhìn các field của CatalogItem **không thể tự biết chắc** dữ liệu trong bảng order_lines, trừ khi callback/validator query DB.

Nhưng query DB trong entity validator có rủi ro:

- N+1 queries khi xóa nhiều items.
- Race giữa thời điểm SELECT và DELETE.
- Transaction isolation khác nhau.
- Repository injection/provider lifecycle khó kiểm soát.
- Vòng lặp đọc entity/validation query re-entrant.

### Cách làm phù hợp

1. Service kiểm tra điều kiện nghiệp vụ nếu cần thông báo sớm.
2. Database có foreign key `order_lines.item_id -> catalog_items.id` với chính sách DELETE thích hợp.
3. Nếu cần coordinated state transition, dùng row locks/optimistic version hoặc atomic SQL.
4. Xử lý database constraint violation tại transaction boundary.

**Một validation group không biến việc kiểm tra “không tồn tại row liên quan” thành một phép kiểm tra atomic khi có giao dịch đồng thời.**

## 32. Đừng dùng constraint class-level để gọi repository tùy tiện

Một constraint validator có thể dùng service injection trong một số môi trường, nhưng:

~~~java
public boolean isValid(
        CatalogItem item,
        ConstraintValidatorContext context) {
    return !orderRepository.existsByItemId(item.getId());
}
~~~

không nên là giải pháp mặc định cho pre-remove.

### Race example

~~~text
TX_A: Validator query -> không có OrderLine.
TX_B: INSERT OrderLine tham chiếu Item và COMMIT.
TX_A: DELETE CatalogItem.
~~~

Nếu không có FK hoặc khóa/isolation đúng, dữ liệu vẫn có thể sai. Validator chỉ cho kết quả **tại thời điểm query**, không bảo đảm nó vẫn đúng khi DELETE.

### Khi nào class-level constraint hữu ích?

Khi điều kiện có thể quyết định từ **state local của entity**, ví dụ hai timestamps phải có thứ tự đúng hoặc status phải phù hợp với một flag.

Các quy tắc liên quan toàn bộ database thường thuộc transaction/service và DB constraints.

## 33. Tạo custom constraint cho OnRemove khi logic phức tạp

Nếu điều kiện xóa cần kiểm tra nhiều **fields local**, có thể viết class-level constraint.

Annotation:

~~~java
package com.example.shop.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy =
    RemovalAllowedValidator.class)
public @interface RemovalAllowed {

    String message()
        default "Không đáp ứng điều kiện xóa";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

Validator:

~~~java
package com.example.shop.validation;

import com.example.shop.domain.CatalogItem;
import com.example.shop.domain.ItemStatus;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class RemovalAllowedValidator
        implements ConstraintValidator<
            RemovalAllowed, CatalogItem> {

    @Override
    public boolean isValid(
            CatalogItem item,
            ConstraintValidatorContext context) {

        if (item == null) {
            return true;
        }

        return item.getStatus() == ItemStatus.DRAFT
            || item.getStatus() == ItemStatus.ARCHIVED;
    }
}
~~~

Áp vào entity:

~~~java
@Entity
@RemovalAllowed(groups = OnRemove.class)
public class CatalogItem {
    // ...
}
~~~

### Null semantics

Ở ví dụ, validator trả true nếu object null, vì tính không-null của tham số thường nên được kiểm tra bởi `@NotNull` ở nơi sở hữu reference. Đây là quy ước phổ biến cho custom constraints, không phải bắt buộc mọi validator phải có cùng behavior.

### Không đăng ký hai constraints trùng mục đích vô điều kiện

Nếu entity đã có `@AssertTrue(groups=OnRemove.class)` trên `isDeletionAllowed()`, thêm `@RemovalAllowed(groups=OnRemove.class)` cùng logic sẽ báo duplicate violations. Chọn một cách thể hiện hoặc dùng cả hai khi chúng có thông điệp/semantics khác nhau thực sự.

## 34. @Valid để cascade validation

Một entity:

~~~java
@Embeddable
public class Address {

    @NotBlank
    private String line1;

    @NotBlank
    private String city;
}
~~~

Entity:

~~~java
@Entity
public class Supplier {

    @Id
    private Long id;

    @Embedded
    @Valid
    private Address address;
}
~~~

`@Valid` yêu cầu **cascaded validation** vào object liên quan khi validation engine đi qua đường đó theo nhóm được chọn và quy tắc traversability.

### @Valid khác cascade persist/remove của JPA

| Annotation | Thuộc cơ chế | Vai trò |
| --- | --- | --- |
| `jakarta.validation.Valid` | Bean Validation | Cascade kiểm tra constraints |
| `jakarta.persistence.CascadeType.PERSIST` | JPA | Cascade persistence operation |
| `jakarta.persistence.CascadeType.MERGE` | JPA | Cascade merge |
| `jakarta.persistence.CascadeType.REMOVE` | JPA | Cascade remove |

Đánh dấu `@Valid` **không có nghĩa tự persist Address entity khác hoặc xóa association**.

### Address là embeddable

Trong ví dụ, `Address` là value object gắn với Supplier; không phải một entity có identity riêng. Kết hợp `@Embedded` + `@Valid` là cách phổ biến để kiểm tra nested state.

## 35. Cascade validation và nhóm đang được kiểm tra

Giả sử:

~~~java
@Embeddable
public class Address {

    @NotBlank
    private String city;

    @NotBlank(groups = OnCreate.class)
    private String line1;
}
~~~

Khi gọi:

~~~java
validator.validate(
    supplier,
    OnCreate.class
);
~~~

và Supplier có `@Valid Address address`, nhóm OnCreate được truyền theo cascading rules. Khi đó constraints gắn OnCreate của Address được xét, nhưng constraint `city` thuộc Default không được chọn chỉ vì group OnCreate.

### Nếu cần Default + OnCreate

~~~java
validator.validate(
    supplier,
    Default.class,
    OnCreate.class
);
~~~

hoặc một sequence/group conversion được thiết kế phù hợp.

### Không suy luận từ “parent hợp lệ” sang “mọi association hợp lệ”

`@Valid` phải được khai báo đúng nơi, group phải tương thích, và lazy traversability có thể hạn chế các thuộc tính chưa được load. Xem phần tiếp theo.

## 36. @ConvertGroup khi parent/child có nhóm khác nhau

Ví dụ Supplier có OnCreate, còn Address dùng một nhóm `AddressChecks`:

~~~java
public interface AddressChecks {
}
~~~

Address:

~~~java
@NotBlank(groups = AddressChecks.class)
private String city;
~~~

Supplier:

~~~java
@Embedded
@Valid
@ConvertGroup(
    from = OnCreate.class,
    to = AddressChecks.class)
private Address address;
~~~

Khi validate Supplier bằng OnCreate, group được **chuyển đổi** khi cascade sang address, để những constraints thuộc AddressChecks được chọn.

### Import

~~~java
import jakarta.validation.Valid;
import jakarta.validation.groups.ConvertGroup;
~~~

### Những điểm cần nhớ

- Group conversion có ý nghĩa trên một **cascaded validation association/property**.
- Không tạo ra một transaction mới.
- Không có tác dụng “tự convert” tất cả constraints của Supplier.
- Không dùng group conversion như cách ép Hibernate load mọi LAZY association không cần thiết.

### Khi nào cần?

Khi nested value object được tái sử dụng và nhóm nội bộ của nó không muốn phụ thuộc vào những tên operation group bên ngoài.

## 37. Entity associations, LAZY loading và validation

Ví dụ:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@Valid
private Category category;
~~~

Một pre-update validation của Product không nên ngầm trở thành hàng loạt SQL chỉ để validate Categories không cần thiết. JPA/Bean Validation integration sử dụng **traversability rules** để quyết định những attributes/associations nào có thể được duyệt, bao gồm tình trạng loaded của lazy attributes.

### Điểm dễ nhầm

`@Valid` không phải `JOIN FETCH`.

Nếu Category chưa được load, không nên dựa vào assumption rằng JPA sẽ luôn fetch và validate toàn bộ Category graph trước mỗi update. Quy tắc loaded/unloaded, traversability và provider integration cần được hiểu và kiểm thử theo mapping.

### Hướng thiết kế

- Validate các scalar invariants quan trọng của Product trên chính Product.
- Với nested embeddable đã loaded, dùng @Valid và groups.
- Với entity association có vòng đời riêng, validate nó trong service của chính operation thay đổi association nếu cần.
- Không dùng cascaded validation thay cho FK, referential integrity hoặc transaction locks.

## 38. Không nhầm cascade remove của JPA với pre-remove validation

Giả sử:

~~~java
@OneToMany(
    mappedBy = "order",
    cascade = CascadeType.REMOVE)
private List<OrderLine> lines;
~~~

Nếu remove Order, JPA có thể cascade remove tới OrderLines theo mapping. Các lifecycle events có thể liên quan từng entity được xóa qua JPA.

Nhưng:

- `CascadeType.REMOVE` không tự quyết định nhóm Bean Validation pre-remove.
- Database `ON DELETE CASCADE` có thể xóa child rows **trong database** mà JPA không instantiate/validate từng child entity.
- JPQL bulk DELETE cũng không trải qua cùng per-entity lifecycle processing như `em.remove(managedEntity)`.

### Kết luận

Nếu invariant phải được bảo vệ **cho mọi cách xóa**, chỉ dựa vào constraint pre-remove ở JPA là chưa đủ. Database constraints, triggers hoặc việc giới hạn writers có thể cần thiết.

## 39. Khác biệt giữa @PreRemove callback và nhóm pre-remove validation

Hai khái niệm:

**JPA lifecycle callback:**

~~~java
@PreRemove
private void beforeRemove() {
    // Lifecycle method, không phải Bean Validation group.
}
~~~

**Bean Validation group:**

~~~java
@AssertTrue(groups = OnRemove.class)
public boolean isDeletionAllowed() { ... }
~~~

cấu hình:

~~~text
jakarta.persistence.validation.group.pre-remove
    = com.example.shop.validation.OnRemove
~~~

### Khác nhau thế nào?

| Chủ đề | `@PreRemove` | Bean Validation pre-remove |
| --- | --- | --- |
| Cơ chế | JPA entity lifecycle callback | JPA tích hợp Bean Validation |
| Code chạy | Method do entity/listener định nghĩa | ConstraintValidator cho nhóm được cấu hình |
| Thông báo vi phạm | Do code ném exception | ConstraintViolation(s) |
| Kích hoạt | Lifecycle remove callback | Theo validation mode + nhóm pre-remove |
| Tùy biến | Một method có thể làm nhiều thứ | Quy tắc constraint declarative |

Không suy đoán thứ tự tuyệt đối của mọi callback và validation đối với mọi provider nếu logic phụ thuộc vào tương tác giữa chúng. Hãy thiết kế để constraints không cần một callback trước đó “bí mật sửa state” mới pass.

## 40. @PrePersist/@PreUpdate callbacks có thể thay đổi state?

Một use case phổ biến:

~~~java
@PrePersist
void beforePersist() {
    if (createdAt == null) {
        createdAt = Instant.now();
    }
}
~~~

và constraint:

~~~java
@NotNull
private Instant createdAt;
~~~

Vấn đề thiết kế là **thời điểm** callback, Bean Validation và ID generation có quy tắc riêng. Nếu một constraint chỉ pass khi callback đã tự tạo giá trị, việc phụ thuộc vào thứ tự chính xác cần được xác minh theo spec/provider và test.

### Cách ổn định hơn

Nếu `createdAt` là yêu cầu của domain:

- Gán tại factory/domain constructor/service trước khi persist.
- Hoặc dùng một mechanism timestamp generation/DB default có contract rõ và kiểm thử với validation.

Không đặt cùng một yêu cầu ở nhiều lifecycle hooks với giả định “thế nào cũng có một cái chạy trước”.

### Không tự sửa associations trong callback

Lifecycle callback có giới hạn portable; không nên gọi EntityManager/query operations hay sửa quan hệ tùy tiện trong cùng context. Sử dụng domain/service methods trước lifecycle operation giúp hành vi minh bạch hơn.

## 41. Bean Validation exception khác database constraint exception

Khi Bean Validation phát hiện vi phạm:

~~~java
jakarta.validation.ConstraintViolationException
~~~

Exception có thể mang tập:

~~~java
Set<ConstraintViolation<?>> violations =
    ex.getConstraintViolations();
~~~

Khi database từ chối SQL vì UNIQUE/FK/CHECK/NOT NULL, JPA provider có thể ném `PersistenceException` hoặc wrapper, ví dụ một Hibernate SQL constraint exception.

### Hai loại lỗi không giống nhau

| Loại | Khi phát hiện | Nguồn quy tắc |
| --- | --- | --- |
| Bean Validation violation | Khi Validator chạy trong lifecycle/service | Java annotations/custom constraints |
| Database constraint violation | Khi DB thực thi INSERT/UPDATE/DELETE | SQL schema/constraints/triggers |

### Vì sao phải phân biệt?

Một exception có tên gần giống nhau ở các thư viện không phải luôn cùng class:

- `jakarta.validation.ConstraintViolationException` là Bean Validation.
- `org.hibernate.exception.ConstraintViolationException` là exception hạ tầng SQL của Hibernate ORM.

Không dùng một catch theo tên ngắn rồi kết luận lỗi nào cũng là HTTP 400 validation thông thường.

### Transaction boundary

Cả hai loại lỗi có thể chỉ xuất hiện khi `flush()` hoặc `commit()`. Service phải rollback theo đúng ownership; không bắt rồi tiếp tục transaction đã rollback-only.

## 42. Xử lý ConstraintViolationException có cấu trúc

Một đoạn service/helper:

~~~java
try {
    em.flush();
} catch (jakarta.validation.ConstraintViolationException ex) {
    for (ConstraintViolation<?> violation :
            ex.getConstraintViolations()) {

        String property =
            violation.getPropertyPath().toString();

        String message =
            violation.getMessage();

        // Ghi log nội bộ có kiểm soát; không lộ dữ liệu nhạy cảm.
        logValidationIssue(property, message);
    }

    throw ex;
}
~~~

`logValidationIssue` là helper minh họa, không phải API built-in.

### Không luôn trả nguyên message cho client

Một custom ConstraintValidator có thể ghi message chứa ID nội bộ hoặc logic nghiệp vụ. API cần map violations thành field errors phù hợp request contract, bỏ thông tin nhạy cảm và không expose entity graph/path vượt quyền.

### Không commit sau exception

Trong JPA transaction, một lifecycle validation exception có thể đánh dấu transaction rollback-only. Để framework/transaction owner rollback và xử lý lỗi ở tầng phù hợp.

## 43. Ví dụ RESOURCE_LOCAL: tạo item

~~~java
package com.example.shop;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;

public class CatalogItemWriter {

    private final EntityManagerFactory emf;

    public CatalogItemWriter(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public Long create(CatalogItem item) {
        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();

            em.persist(item);
            em.flush();

            tx.commit();
            return item.getId();

        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                try {
                    tx.rollback();
                } catch (RuntimeException rollbackError) {
                    ex.addSuppressed(rollbackError);
                }
            }
            throw ex;
        } finally {
            em.close();
        }
    }
}
~~~

Trong ví dụ, EntityManagerFactory đã được tạo từ persistence unit có:

~~~text
pre-persist = Default + OnCreate
pre-update  = Default + OnUpdate
pre-remove  = OnRemove
~~~

### Khi nào validation chạy?

Nó có thể chạy trong một bước của persistence lifecycle/flush; không nên phụ thuộc vào việc exception nhất thiết ném ngay tại `em.persist(item)`. Việc gọi `em.flush()` trong ví dụ cho phép phát hiện nhiều lỗi trước `tx.commit()` nhưng **không biến flush thành commit**.

### Nếu flush thành công nhưng commit thất bại?

Operation vẫn chưa được xác nhận. Phải xử lý lỗi commit, rollback nếu transaction vẫn active và không trả thành công cho client.

## 44. Ví dụ RESOURCE_LOCAL: update item

~~~java
public void changePrice(
        long itemId,
        long tenantId,
        BigDecimal newPrice) {

    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        CatalogItem item =
            em.find(CatalogItem.class, itemId);

        if (item == null
                || !Objects.equals(
                    item.getTenantId(), tenantId)) {
            throw new ItemNotFoundException(itemId);
        }

        item.changePrice(newPrice);

        // Dirty checking / JPA validation pre-update
        // khi provider thực hiện update.
        em.flush();
        tx.commit();

    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    } finally {
        em.close();
    }
}
~~~

### Khi entity đã managed có cần merge không?

Không. `em.find()` trả managed entity, thay đổi `price` qua domain method rồi flush/commit cho phép JPA dirty checking hoạt động.

### Nhóm nào chạy?

Với cấu hình đã nêu, validation pre-update chọn **Default + OnUpdate**. Nếu OnUpdate không có constraint riêng, Default vẫn bảo vệ name/sku/price/status.

### Concurrent update

Nếu entity có `@Version`, JPA có thể phát hiện optimistic conflict khi transaction khác đã ghi version mới. Bean Validation hợp lệ **không có nghĩa phiên bản còn hợp lệ**; hai cơ chế phải phối hợp.

## 45. Ví dụ RESOURCE_LOCAL: remove item

~~~java
public void deleteItem(long tenantId, long itemId) {
    EntityManager em = emf.createEntityManager();
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        CatalogItem item =
            em.find(CatalogItem.class, itemId);

        if (item == null
                || !Objects.equals(
                    item.getTenantId(), tenantId)) {
            throw new ItemNotFoundException(itemId);
        }

        em.remove(item);
        em.flush();
        tx.commit();

    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    } finally {
        em.close();
    }
}
~~~

Khi JPA validation integration bật và `pre-remove` được cấu hình `OnRemove`, constraint `isDeletionAllowed()` sẽ được chọn trong lifecycle remove.

### Đừng nghĩ “không có vi phạm validation = DELETE chắc chắn thành công”

Database có thể chặn vì:

- Có foreign key tham chiếu CatalogItem.
- Một transaction khác thay đổi dữ liệu theo isolation/locking rules.
- Một trigger/check constraint từ chối delete.
- Connection hoặc transaction fail.

Do đó mọi exception liên quan cần xử lý đúng transaction boundary.

## 46. Spring @Transactional: service bao toàn bộ unit of work

Ví dụ Spring:

~~~java
package com.example.shop;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.math.BigDecimal;
import java.util.Objects;

@Service
public class CatalogService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public Long create(CatalogItem item) {
        em.persist(item);
        em.flush();
        return item.getId();
    }

    @Transactional
    public void updatePrice(
            long tenantId,
            long itemId,
            BigDecimal nextPrice) {

        CatalogItem item =
            em.find(CatalogItem.class, itemId);

        if (item == null
                || !Objects.equals(
                    item.getTenantId(), tenantId)) {
            throw new ItemNotFoundException(itemId);
        }

        item.changePrice(nextPrice);
    }

    @Transactional
    public void delete(
            long tenantId,
            long itemId) {

        CatalogItem item =
            em.find(CatalogItem.class, itemId);

        if (item == null
                || !Objects.equals(
                    item.getTenantId(), tenantId)) {
            throw new ItemNotFoundException(itemId);
        }

        em.remove(item);
    }
}
~~~

Đối với Spring transaction-managed EntityManager, **không tự gọi `em.getTransaction().begin()`/`commit()`**; Spring transaction manager sở hữu lifecycle.

### Khi nào caller biết đã commit?

Nếu method chạy trong transaction do Spring proxy vừa tạo, interceptor thường commit sau khi method body kết thúc và trước khi caller nhận return thành công. Nếu method tham gia outer transaction, commit thuộc outer boundary; method con return không bảo đảm dữ liệu đã commit.

### Lưu ý transaction readOnly

Một service thực hiện persist/update/remove cần transaction writable phù hợp. `@Transactional(readOnly=true)` không phải cách tối ưu dành cho những operations sẽ ghi database.

## 47. Sự khác nhau giữa @Valid, @Validated và JPA group properties trong Spring

Trong một hệ thống Spring MVC + Spring Data JPA:

~~~text
Controller:
   @Valid / @Validated
         |
         v
   Validate request DTO
         |
         v
Service:
   @Transactional
         |
         v
   Load managed entity / apply domain methods
         |
         v
JPA provider:
   pre-persist / pre-update / pre-remove validation groups
         |
         v
Database:
   NOT NULL / CHECK / UNIQUE / FK / locking
~~~

### Không cấu hình nhầm tầng

Nếu đặt:

~~~java
@Validated(OnUpdate.class)
public class CatalogController { ... }
~~~

điều đó không có nghĩa mọi entity UPDATE trong persistence unit tự kiểm tra OnUpdate.

Ngược lại, cấu hình:

~~~text
jakarta.persistence.validation.group.pre-update=...
~~~

không có nghĩa Spring MVC sẽ chỉ kiểm tra OnUpdate trên mọi request DTO.

**Mỗi tầng phải có contract nhóm kiểm tra của nó.**

## 48. Validation ở transaction không phải authorization

Giả sử CatalogItem có:

~~~text
id=10
tenantId=300
status=DRAFT
~~~

Tất cả constraints Default/OnRemove đều pass, nhưng user ở tenant 400 **không được xóa item ấy**.

### Quy tắc

- Tenant/ACL phải được kiểm tra khi tìm resource và trước mutation.
- Validation groups không mang user identity hoặc quyền theo request.
- Không đặt permission check trong `@AssertTrue` dựa trên thread-local current user.
- Với nhiều tenants, DB row-level security có thể bổ sung lớp bảo vệ nếu áp dụng.

### Vì sao không biến security thành Bean Validation group?

Constraints nên ổn định, có thể kiểm tra trên state. Quyền truy cập thường phụ thuộc actor, role, organization, resource policy và transaction context. Application service/security layer phù hợp hơn.

## 49. Validation và optimistic locking

Ví dụ:

~~~text
CatalogItem#10 version=7, price=100000

TX_A: đọc version=7, sửa price=110000.
TX_B: đọc version=7, sửa price=120000.
~~~

Cả hai state đều thỏa:

~~~java
@DecimalMin("0.00")
private BigDecimal price;
~~~

Nhưng không thể để cả hai ghi đè mà không phát hiện xung đột nếu nghiệp vụ không cho phép.

`@Version` giải quyết race **stale state version** trên đường ghi managed entity:

~~~sql
UPDATE catalog_items
SET price = ?, version = ?
WHERE id = ? AND version = ?;
~~~

**Validation group không thay thế optimistic locking.**

### Pre-remove và concurrent updates

Một item có status DRAFT ở lúc service đọc nhưng bị transaction khác publish trước khi DELETE. `OnRemove` trên state local có thể pass dựa trên snapshot cũ. Để bảo vệ quy tắc xóa dưới cạnh tranh, cần version checking/lock/conditional DELETE/transaction isolation phù hợp.

### Hướng thiết kế

- Validate local state.
- Kiểm tra expectedVersion nếu người dùng xóa từ UI dựa trên bản cũ.
- Dùng optimistic version hoặc pessimistic lock tùy use case.
- Database kiểm tra FK/constraints.
- Xử lý conflict tại commit boundary.

## 50. Validation và pessimistic locking

Khi xóa có ràng buộc “chỉ xóa item không còn được dùng”:

~~~java
CatalogItem item = em.find(
    CatalogItem.class,
    itemId,
    LockModeType.PESSIMISTIC_WRITE);
~~~

Lock có thể giúp điều phối concurrent writers trên **row CatalogItem**. Nhưng một transaction khác INSERT OrderLine tham chiếu item có thể cần khóa/constraints trên những tài nguyên khác.

### Đừng suy luận lock một row bảo vệ cả thế giới

Nếu invariant liên quan nhiều rows hoặc một query predicate, khóa một CatalogItem không tự bảo vệ mọi OrderLine hoặc Invoice trong DBMS.

### Phân tách trách nhiệm

| Cơ chế | Bảo vệ gì? |
| --- | --- |
| Bean Validation OnRemove | State cục bộ được kiểm tra theo nhóm |
| PESSIMISTIC_WRITE | Điều phối giao dịch cạnh tranh đối với rows/locks được DB quản lý |
| @Version | Phát hiện stale version trên đường ghi tuân thủ protocol |
| FK/UNIQUE/CHECK | Ràng buộc dữ liệu cuối cùng tại DB |

Không dùng ba validation groups làm lời giải duy nhất cho một bài toán concurrency.

## 51. Bulk JPQL UPDATE không chạy validation trên từng entity

Ví dụ:

~~~java
int count = em.createQuery(
        "UPDATE CatalogItem i " +
        "SET i.price = :p " +
        "WHERE i.tenantId = :tenant")
    .setParameter("p", new BigDecimal("-10.00"))
    .setParameter("tenant", tenantId)
    .executeUpdate();
~~~

JPQL bulk update có thể trực tiếp sinh SQL mà **không load từng CatalogItem managed**, nên JPA không áp cùng per-entity pre-update lifecycle validation cho mọi affected row.

Nếu database không có:

~~~sql
CHECK (price >= 0)
~~~

dữ liệu âm có thể được ghi qua bulk UPDATE dù entity có `@DecimalMin("0.00")`.

### Cách bảo vệ

- Validate inputs của bulk operation ở service.
- Enforce DB constraints.
- Tăng/check version thủ công nếu nghiệp vụ yêu cầu optimistic concurrency.
- Đối với bulk operations, đồng bộ/evict persistence context/cache phù hợp.

**Một annotation trên entity không tự bảo vệ các SQL writers bỏ qua lifecycle entity.**

## 52. Bulk JPQL DELETE cũng bypass per-entity pre-remove validation

Ví dụ:

~~~java
int deleted = em.createQuery(
        "DELETE FROM CatalogItem i " +
        "WHERE i.status = :status")
    .setParameter(
        "status", ItemStatus.ARCHIVED)
    .executeUpdate();
~~~

Không được kỳ vọng:

~~~text
JPA load mọi CatalogItem ARCHIVED.
JPA validate OnRemove trên mỗi item.
JPA gọi @PreRemove từng item.
JPA mới DELETE từng row.
~~~

Đây là bulk operation, không phải vòng lặp `em.remove(managedItem)`.

### Nếu chính sách remove phải áp mọi đường xóa

Phải thiết kế predicate SQL, FK/constraints, triggers hoặc quy trình xóa riêng; không để một bulk DELETE vô tình đi vòng toàn bộ quy tắc lifecycle.

### Native SQL và stored procedure

Tương tự, native DELETE hoặc stored procedure bên ngoài managed entity lifecycle cũng không tự kích hoạt JPA Bean Validation per entity.

## 53. Dữ liệu legacy và nhóm update

Giả sử dữ liệu cũ:

~~~text
CatalogItem#15:
  sku = ""
  name = "Legacy Item"
  price = 100000
~~~

Hệ thống mới thêm:

~~~java
@NotBlank
private String sku;
~~~

Với pre-update gồm `Default`, một transaction chỉ sửa price của Item#15 có thể fail vì `sku` không hợp lệ.

### Đây có phải bug?

Không hẳn. Validation đang bảo vệ invariant cuối cùng của entity. Nhưng migration plan phải tính đến dữ liệu tồn tại trước khi thêm constraint.

### Các lựa chọn

1. **Data migration:** sửa SKU legacy trước khi bật constraint.
2. **Staged rollout:** chạy job phân loại/điền dữ liệu, áp constraint theo từng đợt.
3. **Domain-specific exceptions:** chỉ tạm nới rule có lý do và có thời hạn, không biến Default thành vô nghĩa.
4. **DB constraint strategy:** khi dữ liệu đã sạch, thêm NOT NULL/UNIQUE/CHECK phù hợp.

### Không tắt toàn bộ pre-update validation để chữa một row lỗi

Việc đó có thể mở đường cho các writes khác lưu dữ liệu sai. Cần giải quyết dữ liệu và rollout thay vì che lỗi bằng cách bỏ nhóm Default.

## 54. Các lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân khả dĩ |
| --- | --- |
| OnCreate không chạy | Property key sai hoặc class name group không đúng |
| Default constraints bị bỏ qua khi create | pre-persist chỉ cấu hình OnCreate, quên Default |
| OnRemove không chạy | Chưa cấu hình pre-remove group |
| Test @Valid DTO pass nhưng em.persist vẫn sai | DTO và entity lifecycle validation là hai tầng |
| ValidationMode.NONE nhưng gọi Validator vẫn có lỗi | NONE chỉ tắt tự động JPA integration |
| AUTO mà không có validation provider | Thiếu implementation/integration |
| Không thấy lỗi ngay tại persist | Validation/SQL có thể hoãn đến flush/commit |
| Không thấy OnUpdate khi chỉ find entity | Không có update lifecycle event |
| OnUpdate áp lỗi field không sửa | Validator kiểm tra whole state, không chỉ dirty field |
| Remove một legacy row bị Default lỗi | pre-remove bị cấu hình Default không cần thiết |
| JPQL bulk UPDATE vẫn ghi dữ liệu xấu | Bypass per-entity lifecycle validation |
| SQL FK chặn DELETE dù OnRemove pass | Ràng buộc DB khác với local constraint |
| Violation bị bọc trong RollbackException | Exception phát tại commit boundary |
| Spring catch không bắt được lỗi trong service | Commit xảy ra ở transaction interceptor bên ngoài body |
| @Validated group trên controller không ảnh hưởng JPA | Request validation khác lifecycle validation |
| Group sequence sai cấu hình | Định nghĩa sequence/circular dependency không hợp lệ |
| Cascade @Valid không áp vào child | Thiếu @Valid, group conversion hoặc lazy traversability |
| Validation query ra DB làm chậm | Custom ConstraintValidator có IO |
| Xóa item sai tenant vẫn pass | Validation không phải authorization |
| Entity @Version vẫn gặp optimistic conflict | Constraint hợp lệ không bảo đảm concurrency success |

## 55. Chiến lược triển khai trong dự án thực

Đối với một module JPA có create/update/remove, quy trình:

1. Liệt kê business invariants của entity.
2. Tách invariants **mọi lúc đúng** vào Default.
3. Liệt kê các rules thật sự khác giữa create/update/remove.
4. Định nghĩa marker interfaces ít nhưng rõ.
5. Gắn groups vào constraints và chọn validation messages.
6. Cấu hình persistence unit pre-persist/pre-update/pre-remove.
7. Xác nhận ValidationMode và Bean Validation provider.
8. Validate DTO ở API boundary theo request contract.
9. Validate entity managed ở lifecycle boundary.
10. Enforce DB constraints cho dữ liệu quan trọng.
11. Xử lý tenant/ACL ở service/query.
12. Với remove, bảo vệ FK/association/concurrency riêng.
13. Xử lý ConstraintViolationException và DB errors tại transaction boundary.
14. Kiểm thử create/update/remove bằng EntityManager thật.
15. Kiểm thử bulk/native operations không vô tình bỏ qua invariant.
16. Theo dõi lỗi validation trong production theo loại constraint/operation.

### Quy tắc “ít groups nhưng đúng”

Nếu create và update chỉ khác vài trường DTO, không cần tạo hàng chục entity groups. Default + một hoặc hai nhóm đặc biệt có thể đủ.

Groups nên phản ánh **quy tắc state theo lifecycle**; authorization, request workflow và database concurrency cần những công cụ riêng.

## 56. Kiểm thử JPA lifecycle validation thật

Một unit test:

~~~java
validator.validate(item, OnRemove.class);
~~~

chứng minh constraint hoạt động khi gọi Validator, nhưng **không chứng minh JPA đã cấu hình pre-remove đúng**.

Integration test cần:

~~~text
EntityManagerFactory có validation provider và properties thật
                 |
                 v
Transaction riêng
                 |
                 v
persist/update/remove managed entity
                 |
                 v
flush/commit hoặc bắt validation exception
                 |
                 v
rollback và đọc lại DB bằng context mới
~~~

### Tránh test chỉ mock EntityManager

Mock `em.persist()` không chạy provider lifecycle validation, nên có thể pass dù XML properties sai.

### Xác minh exception ở boundary

Nếu dùng Spring, commit có thể xảy ra ngoài method service; test gọi qua proxy hoặc transaction template phù hợp để quan sát đúng lỗi.

## 57. Test pre-persist nhóm Default + OnCreate

Fixture hợp lệ:

~~~java
CatalogItem valid = new CatalogItem(
    tenantId,
    "BOOK-JPA",
    "Java Persistence",
    new BigDecimal("150000.00")
);
~~~

Kỳ vọng:

~~~text
Default:
  SKU, name, price, status đều hợp lệ.
OnCreate:
  status == DRAFT.
=> Persist/flush/commit thành công.
~~~

Fixture không hợp lệ:

~~~java
CatalogItem invalid = new CatalogItem(
    tenantId,
    "",
    "Java Persistence",
    new BigDecimal("150000.00")
);
~~~

Kỳ vọng:

~~~text
Default:
  @NotBlank sku vi phạm.
=> pre-persist validation thất bại khi lifecycle check chạy.
~~~

### Test OnCreate riêng

Tạo một entity trong status PUBLISHED trước persist bằng fixture/test-only setter hoặc factory có kiểm soát:

~~~text
Default constraints đều hợp lệ.
OnCreate: isNewItemInDraft() == false.
=> expect validation failure.
~~~

Không dùng reflection bừa bãi trong production; test fixture có thể cung cấp helper package-private nhằm tạo state cần kiểm tra.

## 58. Test pre-update nhóm Default + OnUpdate

Quy trình:

1. Persist CatalogItem hợp lệ, commit.
2. Đóng EntityManager tạo fixture.
3. Mở EntityManager/transaction mới.
4. Find item managed.
5. Đổi name thành chuỗi không hợp lệ với OnUpdate, hoặc price âm để vi phạm Default.
6. Flush/commit và kiểm tra violation phù hợp.
7. Rollback, mở context mới kiểm tra DB vẫn giữ state cũ.

### Vì sao phải tạo một update thực?

Chỉ tìm entity rồi commit mà không sửa gì có thể không phát SQL UPDATE hoặc pre-update validation. Test phải đảm bảo **dirty state thực sự** và query/flush path tương ứng.

### Không dùng entity detached trong test mà quên merge semantics

Nếu test tạo object mới có ID rồi gọi merge, provider có thể có hành vi load/copy khác; với mục tiêu test pre-update đơn giản, **find managed + domain mutation** rõ ràng hơn.

## 59. Test pre-remove có và không có cấu hình nhóm

Hai cấu hình cần phân biệt:

### A. Có pre-remove = OnRemove

Fixture: Item status PUBLISHED, có thể hợp lệ cho Default.

~~~text
em.remove(item)
flush/commit
=> validation OnRemove bị vi phạm,
   transaction không được xác nhận thành công.
~~~

### B. Không cấu hình pre-remove groups

Với default lifecycle integration, OnRemove không được tự động chọn chỉ vì constraint tồn tại. Nếu database FK/trigger khác không ngăn, thao tác remove có thể đi tới DELETE.

**Đừng dùng tình huống B để xóa dữ liệu production.** Kiểm thử bằng persistence unit/database fixture độc lập, rollback hoặc transaction test cô lập.

### Tại sao cần cả hai?

Để chứng minh rule thực sự đến từ **cấu hình lifecycle group**, không chỉ do custom exception ở domain method hoặc FK constraint ở database.

## 60. Test nhóm Default không bị đánh mất

Một lỗi nguy hiểm:

~~~xml
<property
    name="jakarta.persistence.validation.group.pre-update"
    value="com.example.shop.validation.OnUpdate"/>
~~~

Nếu entity có:

~~~java
@NotNull
private BigDecimal price;
~~~

thì Default không nhất thiết được xét trong pre-update ở cấu hình trên.

### Test đơn giản

1. Persist một Item hợp lệ.
2. Load item managed.
3. Đặt price=null, đồng thời tạo dirty update.
4. Flush.
5. Nếu pre-update chỉ OnUpdate và không có constraint OnUpdate trên price, Bean Validation có thể **không** báo lỗi `@NotNull`, dù DB NOT NULL có thể báo lỗi sau đó.

### Hướng sửa

~~~xml
<property
    name="jakarta.persistence.validation.group.pre-update"
    value="jakarta.validation.groups.Default,com.example.shop.validation.OnUpdate"/>
~~~

Sau đó kiểm thử cả Bean Validation và database behavior để chắc chắn policy được thực thi.

## 61. Test group sequence

Giả sử:

~~~java
@GroupSequence({
    Default.class,
    OnCreate.class
})
public interface CreateChecksInOrder {
}
~~~

Test:

- Item vi phạm Default và OnCreate: những constraints của nhóm sau sequence không cần được đánh giá khi nhóm trước đã có violation.
- Item pass Default nhưng vi phạm OnCreate: nhận violation OnCreate.
- Item pass cả hai: không có violation.

### Không bắt buộc assert thứ tự Set iteration

`Validator.validate()` trả tập `ConstraintViolation`; không nên dựa vào thứ tự iteration để kết luận group sequence có hiệu lực. Kiểm tra **loại violation được sinh ra** hoặc dùng test-only validators có instrumentation phù hợp.

### Không dùng validator thực hiện IO chỉ để kiểm tra thứ tự

Đặt một custom validator có side effects ngoài DB/test sẽ khiến bài test khó an toàn; nếu cần chứng minh sequence skip, dùng một constraint validator test-only thuần túy và recorder được cô lập.

## 62. Test cascade @Valid và @ConvertGroup

Ví dụ Supplier chứa Address:

~~~java
@Embedded
@Valid
@ConvertGroup(
    from = OnCreate.class,
    to = AddressChecks.class)
private Address address;
~~~

Test:

1. Supplier pass các constraints gốc thuộc OnCreate.
2. Address.city trống, constraint thuộc AddressChecks.
3. Validate Supplier với OnCreate.
4. Xác nhận có violation ở property path liên quan `address.city` khi converter và cascade được áp dụng.

### Tại sao không cần DB ở test đầu?

Group conversion là Bean Validation feature; unit test với Validator thật có thể chứng minh mapping này. Sau đó integration test JPA có thể xác nhận lifecycle groups sử dụng nó trong persistence operation.

## 63. Test bulk operations không kích hoạt per-entity validation

Với một persistence unit có pre-update groups:

~~~java
em.createQuery(
    "UPDATE CatalogItem i SET i.price = :bad " +
    "WHERE i.id = :id")
  .setParameter("bad", new BigDecimal("-10.00"))
  .setParameter("id", itemId)
  .executeUpdate();
~~~

Nếu database có `CHECK(price >= 0)`, SQL sẽ bị DB từ chối. Đó là **DB constraint**, không phải Bean Validation per-entity lifecycle.

### Test cần phân loại nguyên nhân

- Có đúng loại SQL/JDBC exception từ DB không?
- Có Bean Validation `ConstraintViolationException` không?
- Entity đã managed trong context có stale state sau bulk không?

Không catch mọi `RuntimeException` rồi tuyên bố rằng “pre-update validation bảo vệ bulk update”.

## 64. Kiểm thử concurrency trước khi remove

Một use case:

> Xóa CatalogItem nếu còn DRAFT và không có OrderLine.

Hai transaction:

~~~text
TX_A                             TX_B
-------------------------------  ---------------------------------
Find Item DRAFT.
Validator OnRemove pass.
                                 INSERT OrderLine liên quan.
                                 COMMIT.
DELETE Item.
COMMIT?
~~~

Nếu FK bảo vệ tham chiếu, database sẽ từ chối DELETE hoặc điều phối lock phù hợp. Nếu không có FK/lock/isolation và mọi kiểm tra chỉ ở Java, ứng dụng có thể lưu trạng thái sai.

### Thông điệp

Group validation xác nhận **state của object tại một thời điểm**, không bảo vệ một invariant liên quan những rows có thể được ghi đồng thời. DB constraints và transaction semantics phải là phần của thiết kế.

## 65. Những anti-pattern phổ biến

| Anti-pattern | Vì sao sai | Hướng thay thế |
| --- | --- | --- |
| Chỉ tạo interface OnRemove rồi tin remove sẽ validate | Pre-remove default không chọn nhóm | Cấu hình pre-remove rõ |
| pre-persist chỉ OnCreate, bỏ Default | Mất constraints chung | Include Default hoặc group inheritance/sequence có chủ đích |
| Dùng OnUpdate để validate field vừa đổi | Group validate state, không phải dirty delta | DTO/command validation và domain methods |
| Dùng @Null trên generated ID để xác định create | Thời điểm ID generation/provider khác nhau | Validate request DTO |
| Xóa khi OnRemove pass mà không kiểm tra FK | Có thể còn OrderLine | Service + DB FK/constraints |
| ConstraintValidator query repository theo mỗi row | N+1 và race | Service query/transaction, DB invariant |
| Dùng @Valid thay CascadeType.PERSIST | Hai cơ chế khác nhau | Mapping persistence cascade riêng |
| Dùng CascadeType.REMOVE rồi nghĩ validator child chắc chạy | DB cascades/bulk bypass entity lifecycle | Kiểm thử và DB constraints |
| Dùng ValidationMode.NONE để tắt mọi validation | Chỉ tắt JPA integration | Xác định Validator calls riêng |
| Bỏ Bean Validation provider | AUTO có thể không chạy | Dependencies/boot tests |
| Chỉ bắt lỗi ở persist() | Có thể lỗi tại flush/commit | Transaction boundary handling |
| Catch violation rồi commit tiếp | Transaction rollback-only | Rollback đúng ownership |
| Bulk JPQL update bỏ qua entity constraint | Không có per-entity lifecycle | Validate input + DB constraint |
| Nhận thẳng Entity từ HTTP | Over-posting/tenant/id fields | DTO + authorization + managed mutation |
| Validation group dùng để kiểm tra quyền | Không có actor context rõ | Security layer |
| OnRemove tự sửa association/SQL | Lifecycle/re-entrant/race | Service trước remove |
| GroupSequence sai chứa Default khi redefine class | Vi phạm quy tắc sequence | Định nghĩa đúng sequence semantics |
| Tạo rất nhiều groups cho từng endpoint | Khó hiểu và coupling | Ít groups theo state lifecycle |
| Chỉ test Validator.validate() | Không test cấu hình JPA pre-* | Integration test EM/transactions |
| Chỉ dùng H2/mocks khi DB có FK/locking khác | Khác production semantics | Test DBMS tương đương |

## 66. Quy trình ra quyết định chọn nhóm

~~~text
Quy tắc cần kiểm tra là gì?
           |
           v
Quy tắc luôn đúng với entity persistent?
          /  \
         Có   Không
         |       |
         v       v
      Default   Chỉ đúng ở giai đoạn nào?
                /      |       \
              Tạo     Sửa      Xóa
               |       |        |
               v       v        v
           OnCreate OnUpdate  OnRemove
               \       |        /
                \      |       /
                 v     v      v
          Cấu hình JPA pre-* group tương ứng
                         |
                         v
                 Rule chỉ cần local state?
                      /       \
                    Có         Không
                     |          |
                     v          v
              Bean Validation   Service/transaction/
              constraint        DB constraint/locking
                     \           /
                      v         v
               Integration test trên provider/DB
~~~

### Những câu hỏi nên hỏi trước khi chọn OnRemove

- Xóa là hard delete hay soft delete?
- Item DRAFT, PUBLISHED, ARCHIVED có các quyền xóa khác nhau?
- Có FK/OrderLine/Payment/History tham chiếu?
- Người dùng có cần expectedVersion để tránh xóa trạng thái đã thay đổi?
- Những đường xóa nào có thể bypass JPA lifecycle, như bulk SQL?
- Có cần audit/outbox/retention policy khi xóa?

Nếu câu trả lời kéo dài qua nhiều entities hoặc external systems, **validation group chỉ là một phần nhỏ của workflow**.

## 67. Bài tập thực hành

### Bài 1 — Nhóm mặc định

Một field có `@NotBlank` và không ghi `groups`. Nó thuộc nhóm nào?

**Gợi ý:** `jakarta.validation.groups.Default`.

### Bài 2 — Marker interface

OnCreate được khai báo như thế nào?

**Gợi ý:** `public interface OnCreate {}`.

### Bài 3 — Nhóm OnCreate

Nếu chỉ gọi `validator.validate(item, OnCreate.class)`, có chắc @NotNull thuộc Default chạy không?

**Gợi ý:** không; cần Default hoặc group inheritance/sequence phù hợp.

### Bài 4 — pre-persist property

Viết đúng property key để cấu hình nhóm trước persist.

**Gợi ý:** `jakarta.persistence.validation.group.pre-persist`.

### Bài 5 — pre-update property

Viết đúng property key để cấu hình nhóm trước update.

**Gợi ý:** `jakarta.persistence.validation.group.pre-update`.

### Bài 6 — pre-remove property

Viết đúng property key để cấu hình nhóm trước remove.

**Gợi ý:** `jakarta.persistence.validation.group.pre-remove`.

### Bài 7 — Mặc định pre-remove

Không cấu hình pre-remove group. JPA có tự validate OnRemove không?

**Gợi ý:** không; thông thường mặc định pre-remove không chọn nhóm nào.

### Bài 8 — Default + OnCreate

Bạn muốn kiểm tra cả constraints chung và tạo mới. XML value nên chứa gì?

**Gợi ý:** `jakarta.validation.groups.Default,com.example.shop.validation.OnCreate`.

### Bài 9 — Validator Java API

Chọn nhiều nhóm:

~~~java
validator.validate(item, ???);
~~~

**Gợi ý:** `Default.class, OnCreate.class`.

### Bài 10 — Bean Validation vs database

`@NotBlank` trên SKU có thay được `UNIQUE (tenant_id, sku)` không?

**Gợi ý:** không; NotBlank chỉ kiểm tra không trắng, UNIQUE bảo vệ trùng khóa tại DB.

### Bài 11 — @AssertTrue on remove

Một method `isDeletionAllowed()` trả false khi Item PUBLISHED. Constraint nhóm nào phù hợp?

**Gợi ý:** `@AssertTrue(groups=OnRemove.class)`, cộng cấu hình pre-remove.

### Bài 12 — Update kiểm tra toàn state

Service chỉ sửa price, nhưng name sai `@NotBlank` của Default. Pre-update có thể fail không?

**Gợi ý:** có; validate state entity, không chỉ price dirty.

### Bài 13 — Chỉ check field request

Bạn muốn validate field price do PATCH gửi trước khi load entity. API Bean Validation nào có thể hữu ích?

**Gợi ý:** DTO validation, `validateValue` hoặc `validateProperty` tùy design.

### Bài 14 — ValidationMode.NONE

Nếu đặt `ValidationMode.NONE`, `validator.validate(item)` được gọi tường minh có tự tắt không?

**Gợi ý:** không.

### Bài 15 — ValidationMode.CALLBACK

Nếu CALLBACK được yêu cầu nhưng thiếu Bean Validation implementation phù hợp, có thể xảy ra điều gì?

**Gợi ý:** bootstrap/integration có thể báo lỗi thay vì silently skip.

### Bài 16 — GroupSequence

Muốn kiểm tra Default trước OnCreate, dùng annotation nào?

**Gợi ý:** `@GroupSequence({Default.class, OnCreate.class})` trên một **interface sequence**.

### Bài 17 — Group sequence stop

Nếu nhóm đầu trong sequence đã vi phạm, nhóm sau có còn buộc chạy không?

**Gợi ý:** không; nhóm sau được bỏ qua theo sequence behavior.

### Bài 18 — Class-level Default sequence

Có thể đặt `@GroupSequence({Default.class, OnCreate.class})` lên chính entity class để redefine Default không?

**Gợi ý:** không đúng quy tắc redefinition; cần class type trong sequence của class.

### Bài 19 — @Valid

`@Valid` trên Address có tương đương `CascadeType.PERSIST` không?

**Gợi ý:** không; một cái cascade validation, một cái cascade JPA persistence.

### Bài 20 — @ConvertGroup

Khi Supplier được validate OnCreate nhưng Address dùng AddressChecks, annotation nào có thể chuyển nhóm khi cascade?

**Gợi ý:** `@ConvertGroup(from=OnCreate.class,to=AddressChecks.class)` trên property @Valid.

### Bài 21 — LAZY association

Có nên mặc định mọi @Valid association LAZY đều được load để kiểm tra hết entity graph không?

**Gợi ý:** không; traversability/provider behavior cần được hiểu, không dùng @Valid thay fetch plan.

### Bài 22 — @PreRemove vs OnRemove

`@PreRemove` và `@AssertTrue(groups=OnRemove.class)` có phải cùng cơ chế không?

**Gợi ý:** không; JPA callback khác Bean Validation group selection.

### Bài 23 — Remove và FK

OnRemove pass nhưng OrderLine còn tham chiếu Item. Database vẫn có thể từ chối DELETE không?

**Gợi ý:** có; FK độc lập với local validation.

### Bài 24 — Query DB trong validator

Vì sao gọi `existsByItemId()` từ ConstraintValidator OnRemove không tự bảo đảm invariant under concurrency?

**Gợi ý:** race giữa check và DELETE/INSERT; cần DB constraint/transaction locking.

### Bài 25 — Transaction phase

`em.persist(item)` không ném exception. Có chắc JPA đã validate và commit thành công chưa?

**Gợi ý:** chưa; validation/SQL có thể xảy ra khi flush/commit.

### Bài 26 — pre-update không chạy

Find entity rồi commit mà không sửa persistent state. Có chắc pre-update validation chạy không?

**Gợi ý:** không; không có update lifecycle event.

### Bài 27 — Bulk update

JPQL bulk UPDATE đặt price=-10. Bean Validation @DecimalMin của entity có chắc chặn từng row không?

**Gợi ý:** không; bulk operation bypass per-entity validation; cần DB CHECK.

### Bài 28 — Bulk delete

JPQL bulk DELETE ARCHIVED items có tự gọi OnRemove trên từng row không?

**Gợi ý:** không như em.remove(managedEntity).

### Bài 29 — Spring @Validated

`@Validated(OnCreate.class)` ở controller có tự cấu hình JPA pre-persist groups không?

**Gợi ý:** không; request validation khác lifecycle validation.

### Bài 30 — Validation exception

Khác biệt giữa `jakarta.validation.ConstraintViolationException` và một SQL FK/UNIQUE constraint error là gì?

**Gợi ý:** một bên Bean Validation; bên kia do database thực thi constraints.

### Bài 31 — Rollback

Một pre-update validation exception xảy ra ở commit. Có nên catch bên trong entity setter rồi coi là đã cập nhật không?

**Gợi ý:** không; commit boundary cần rollback/error propagation.

### Bài 32 — Legacy data

Một row cũ có SKU rỗng, chỉ sửa price nhưng pre-update Default fail. Nên tắt mọi entity validation không?

**Gợi ý:** không; cần migration/rollout/invariant strategy.

### Bài 33 — Generated ID

Vì sao `@Null(groups=OnCreate.class)` trên entity ID generated không nên là hàng rào duy nhất chống client tự đặt ID?

**Gợi ý:** ID generation timing khác nhau; dùng DTO/contract để ngăn over-posting.

### Bài 34 — Concurrency

Hai transactions cập nhật price hợp lệ nhưng cùng dựa trên version cũ. Bean Validation có phát hiện lost update không?

**Gợi ý:** không; dùng `@Version`/locking.

### Bài 35 — Xóa sai tenant

Một item thuộc tenant B, constraints OnRemove đều pass. User tenant A có quyền xóa không?

**Gợi ý:** không; authorization/tenant check độc lập.

### Bài 36 — Custom constraint

Muốn kiểm tra state local phức tạp trước remove, có thể tạo annotation sử dụng API nào?

**Gợi ý:** `@Constraint(validatedBy=...)` và `ConstraintValidator<Annotation,Entity>`.

### Bài 37 — Test pre-remove

Một unit test `validator.validate(item,OnRemove.class)` pass. Đã chứng minh EntityManager.remove sẽ chạy OnRemove chưa?

**Gợi ý:** chưa; phải integration test với validation group property thực.

### Bài 38 — Test update

Vì sao test chỉ find entity rồi commit không đủ chứng minh nhóm OnUpdate được kích hoạt?

**Gợi ý:** có thể không có SQL UPDATE/lifecycle update.

### Bài 39 — Test affected rows

Một native SQL DELETE vi phạm FK. Vì sao không gọi đó là “OnRemove constraint được kiểm tra”?

**Gợi ý:** native SQL và FK là database layer, không phải JPA per-entity callback.

### Bài 40 — Thiết kế tối giản

Một entity chỉ có các invariant chung và không có rule đặc biệt cho create/update. Có nhất thiết phải tạo OnCreate/OnUpdate không?

**Gợi ý:** không; nhóm Default có thể đủ cho cả hai theo cấu hình mặc định.

## 68. Bảng ghi nhớ nhanh

| Cần nhớ | Quy tắc |
| --- | --- |
| Validation groups dùng làm gì? | Chọn bộ Bean Validation constraints theo use case/phase |
| Nhóm mặc định | `jakarta.validation.groups.Default` |
| Constraint không ghi groups | Thuộc Default |
| Validator Java API | `validator.validate(entity, Group.class)` |
| pre-persist property | `jakarta.persistence.validation.group.pre-persist` |
| pre-update property | `jakarta.persistence.validation.group.pre-update` |
| pre-remove property | `jakarta.persistence.validation.group.pre-remove` |
| pre-persist mặc định | Default |
| pre-update mặc định | Default |
| pre-remove mặc định | Không chọn nhóm |
| Tạo item kiểm tra cả invariant chung | Default + OnCreate |
| Cập nhật item kiểm tra cả invariant chung | Default + OnUpdate |
| Xóa item có điều kiện | OnRemove + service/DB protection |
| Nhóm mới chỉ được đặt tên? | Marker interface không có magic |
| Nhiều groups trong JPA property | Fully qualified names, cách nhau bởi dấu phẩy |
| Bean Validation mode | AUTO, CALLBACK, NONE |
| NONE có tắt Validator thủ công? | Không |
| Validator kiểm tra riêng field? | validateProperty / validateValue |
| Group sequence | Thứ tự giữa groups, nhóm sau có thể bị bỏ qua |
| @Valid | Cascade Bean Validation |
| @ConvertGroup | Chuyển group ở cascaded association |
| JPA cascade PERSIST/REMOVE | Khác @Valid |
| PreUpdate kiểm tra dirty fields only? | Không, kiểm tra entity state theo group |
| pre-remove constraint tự chạy? | Không nếu chưa cấu hình |
| @PreRemove có giống group OnRemove? | Không |
| Validation có thay FK/UNIQUE/CHECK? | Không |
| Validation có thay @Version? | Không |
| Bulk JPQL UPDATE/DELETE chạy per-entity validation? | Không |
| Lỗi Bean Validation | `jakarta.validation.ConstraintViolationException` |
| Lỗi DB constraint | SQL/provider exception khác |
| Khi nào lỗi xuất hiện? | Có thể tại flush/commit |
| Kiểm thử đúng | EntityManagerFactory + transactions + persistence config thật |
| Nhóm cho request DTO | Tách với nhóm lifecycle của entity |
| Quy tắc cấp quyền | Service/security, không phải group |

## Kết luận

**Thiết kế nhóm kiểm tra trước persist, update và remove** giúp một entity JPA tuân thủ những ràng buộc phù hợp với từng giai đoạn thay vì áp mọi constraint một cách thiếu chọn lọc. Với Jakarta Bean Validation, các nhóm như `OnCreate`, `OnUpdate` và `OnRemove` chỉ là marker interfaces; constraints được chọn bằng thuộc tính `groups` và JPA tích hợp chúng thông qua ba property chuẩn `jakarta.persistence.validation.group.pre-persist`, `pre-update` và `pre-remove`.

Nguyên tắc cấu hình cần nhớ là **pre-persist và pre-update mặc định kiểm tra Default, còn pre-remove mặc định không tự chọn nhóm nào**. Khi thêm nhóm chuyên biệt, hãy giữ các invariants chung bằng cách bao gồm `Default` hoặc thiết kế group hierarchy/sequence phù hợp; đừng thay Default bằng OnCreate/OnUpdate rồi vô tình bỏ qua `@NotNull`, `@NotBlank` hay `@DecimalMin`. Với remove, cần chủ động bật OnRemove nếu muốn kiểm tra tại lifecycle event.

Tuy nhiên, **Bean Validation kiểm tra state của object, không phải toàn bộ thế giới dữ liệu đang thay đổi đồng thời**. Nó không thay DB `UNIQUE`/`CHECK`/`FK`, transaction isolation, optimistic/pessimistic locking, tenant authorization hoặc các kiểm tra domain liên quan nhiều entities. Những đường ghi như bulk JPQL, native SQL và stored procedures có thể đi vòng per-entity lifecycle validation, nên database constraints vẫn là lớp bảo vệ không thể bỏ qua.

Một cách triển khai bền vững là **đặt invariants chung trong Default, dùng ít groups có ý nghĩa thật, kiểm tra DTO tại API boundary, kiểm tra entity trong JPA lifecycle, bảo vệ consistency bằng database/transaction và xác nhận hoạt động bằng integration tests thực**. Cách phân lớp này làm lỗi dữ liệu dễ hiểu hơn, tránh chặn nhầm thao tác xóa và giữ các quy tắc nghiệp vụ nhất quán qua nhiều đường cập nhật.

# Quy tắc kiểm tra Jakarta Validation khi thực thể được lưu hoặc cập nhật

Trong một ứng dụng Hibernate, entity không chỉ cần ánh xạ đúng sang bảng và cột. Trước khi được lưu hoặc cập nhật, dữ liệu còn phải thỏa **các quy tắc hợp lệ của mô hình nghiệp vụ**: tên không được rỗng, số lượng phải dương, email phải đúng định dạng, ngày kết thúc không được trước ngày bắt đầu, hoặc một đơn hàng ở trạng thái xác nhận phải có địa chỉ giao hàng.

Jakarta Bean Validation cung cấp một cơ chế khai báo những quy tắc đó ngay trên Java object bằng các constraint annotations như `@NotNull`, `@NotBlank`, `@Size`, `@Positive`, `@Email` và `@Valid`. Hibernate Validator là một implementation phổ biến của chuẩn này. Khi tích hợp với Jakarta Persistence, Hibernate ORM có thể tự động kiểm tra các entity theo các **lifecycle events** phù hợp — đặc biệt là trước insert và trước update — rồi từ chối thao tác nếu có constraint violations.

Điểm quan trọng là phải phân biệt ba lớp:

1. **Bean Validation** kiểm tra trạng thái của Java object theo constraints và validation groups.
2. **Hibernate ORM** quản lý lifecycle entity, phát hiện thay đổi, flush và chuyển đổi trạng thái sang SQL.
3. **Database constraints** như `NOT NULL`, `UNIQUE`, `FOREIGN KEY` và `CHECK` là chốt bảo vệ dữ liệu ở database.

Ba lớp có thể hỗ trợ nhau, nhưng không thay thế hoàn toàn cho nhau. Một `@NotNull` trong Java **không chứng minh** rằng cột database đã có `NOT NULL`; một entity hợp lệ theo Bean Validation **không bảo đảm** transaction sẽ commit thành công; và một phép `UPDATE` viết bằng native SQL **không tự chạy entity Bean Validation**.

Bài học thuộc chương **Sự kiện và mở rộng** của *Data Persistence Relational Access ORM Hibernate*, tập trung vào Hibernate ORM 6.x, Hibernate Validator và Jakarta Persistence trên Spring Boot 3.x. Các ví dụ dùng namespace `jakarta.*`; nếu ứng dụng còn ở `javax.*` của Java EE/JPA đời cũ, phải chọn phiên bản và dependencies tương ứng chứ không trộn hai hệ API.

## 1. Jakarta Validation là gì?

Jakarta Bean Validation định nghĩa một API chuẩn cho việc mô tả và kiểm tra constraints trên object.

Ví dụ:

~~~java
import jakarta.validation.constraints.*;

public class RegistrationRequest {

    @NotBlank
    @Size(max = 120)
    private String fullName;

    @NotBlank
    @Email
    private String email;

    @Min(18)
    private int age;

    // Constructors/getters/setters được lược bớt.
}
~~~

Với một `Validator`, có thể kiểm tra object này **không cần database**:

~~~java
import jakarta.validation.*;
import java.util.Set;

try (ValidatorFactory factory =
        Validation.buildDefaultValidatorFactory()) {

    Validator validator = factory.getValidator();

    RegistrationRequest request = new RegistrationRequest();
    Set<ConstraintViolation<RegistrationRequest>> violations =
            validator.validate(request);

    for (ConstraintViolation<RegistrationRequest> violation : violations) {
        System.out.println(
                violation.getPropertyPath() + ": " +
                violation.getMessage()
        );
    }
}
~~~

Khi dùng Spring Boot, thông thường `Validator` được container quản lý và có thể inject; không cần tự xây `ValidatorFactory` cho mỗi request.

### 1.1. Constraint annotation khác code kiểm tra thủ công ở đâu?

Khai báo:

~~~java
@NotBlank
private String customerName;
~~~

là **metadata kiểm tra**. Một implementation Bean Validation sẽ diễn giải annotation đó khi một lệnh validate được kích hoạt. Tự gán:

~~~java
order.setCustomerName("");
~~~

không khiến Java ngay lập tức ném exception chỉ vì field có `@NotBlank`. Kiểm tra xảy ra khi code gọi `validator.validate(...)`, khi Spring MVC kiểm tra request, hoặc khi Hibernate/JPA lifecycle validation được kích hoạt.

Do đó **khai báo annotation và kích hoạt validation là hai việc khác nhau**.

### 1.2. Các thành phần chính

| Thành phần | Chức năng |
| --- | --- |
| `@NotNull`, `@Size`, `@Positive`, ... | Khai báo constraint |
| `Validator` | Kiểm tra một object theo nhóm constraints |
| `ConstraintViolation<T>` | Mô tả một vi phạm cụ thể |
| `@Valid` | Kích hoạt cascaded validation tới object lồng nhau |
| Validation group | Chọn tập constraints cho một tình huống |
| `ConstraintValidator<A,T>` | Code thực thi custom constraint |
| `ValidatorFactory` | Tạo/cấu hình Validator instances |
| JPA lifecycle integration | Tự validate entities tại các thời điểm persistence thích hợp |

## 2. Entity ví dụ: PurchaseOrder và OrderLine

Giả sử ứng dụng quản lý đơn hàng. Một đơn hàng có thông tin khách, tổng tiền, trạng thái và nhiều dòng sản phẩm.

### 2.1. PurchaseOrder

~~~java
package com.example.sales;

import jakarta.persistence.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotBlank
    @Size(max = 120)
    @Column(name = "customer_name", nullable = false, length = 120)
    private String customerName;

    @NotBlank
    @Email
    @Size(max = 254)
    @Column(name = "customer_email", nullable = false, length = 254)
    private String customerEmail;

    @NotNull
    @PositiveOrZero
    @Digits(integer = 12, fraction = 2)
    @Column(
        name = "total_amount",
        nullable = false,
        precision = 14,
        scale = 2
    )
    private BigDecimal totalAmount;

    @NotNull
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @NotNull
    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false)
    private OrderStatus status;

    @Valid
    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<OrderLine> lines = new ArrayList<>();

    @Version
    private long version;

    protected PurchaseOrder() {}

    // Constructors, getters và domain methods được lược bỏ.
}
~~~

### 2.2. OrderLine

~~~java
package com.example.sales;

import jakarta.persistence.*;
import jakarta.validation.constraints.*;

import java.math.BigDecimal;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @NotBlank
    @Size(max = 60)
    @Column(name = "sku", nullable = false, length = 60)
    private String sku;

    @Positive
    @Column(name = "quantity", nullable = false)
    private int quantity;

    @NotNull
    @PositiveOrZero
    @Column(name = "unit_price", nullable = false)
    private BigDecimal unitPrice;

    protected OrderLine() {}

    // Constructors/getters/domain methods được lược bỏ.
}
~~~

### 2.3. Enum

~~~java
package com.example.sales;

public enum OrderStatus {
    DRAFT, CONFIRMED, CANCELLED
}
~~~

Các `public` types được đặt trong những file Java riêng. Mapping là ví dụ để giải thích Validation, chưa trình bày đầy đủ factory, các methods bảo vệ invariants và các schema migrations cần thiết để chạy một ứng dụng.

**Lưu ý:** `@NotBlank` trên `customerName` kiểm tra Java value không null và có ít nhất một ký tự không phải whitespace. `@Column(nullable = false)` mô tả mapping/database DDL; cả hai thường được dùng cùng nhau nhưng phục vụ hai tầng riêng.

## 3. Luồng kiểm tra tự động khi lưu entity

Giả sử service tạo một PurchaseOrder không có email:

~~~java
@Transactional
public Long createOrder(CreateOrderCommand command) {
    PurchaseOrder order = new PurchaseOrder(
            command.customerName(),
            "",                           // Không hợp lệ theo @NotBlank.
            command.lines()
    );

    entityManager.persist(order);

    return order.getId();
}
~~~

Ở bước persist hoặc flush phù hợp, Hibernate có thể kích hoạt **pre-insert Bean Validation** đối với entity. Nếu constraint `@NotBlank` trên `customerEmail` không đạt, provider tạo một `jakarta.validation.ConstraintViolationException` và thao tác lưu không thể hoàn thành theo transaction bình thường.

~~~mermaid
flowchart TD
    A["Service bắt đầu transaction"] --> B["EntityManager.persist(order)"]
    B --> C["Order chuyển sang managed/pending insert"]
    C --> D["Hibernate cần thực hiện INSERT"]
    D --> E["JPA Bean Validation pre-persist"]
    E --> F{"Constraint groups hợp lệ?"}
    F -- Không --> G["ConstraintViolationException"]
    G --> H["Rollback unit of work"]
    F -- Có --> I["Tiếp tục SQL INSERT"]
    I --> J["DB constraints / FK / UNIQUE checks"]
    J --> K["Flush + commit thành công nếu không có lỗi"]
~~~

Sơ đồ mô tả một chuỗi khái niệm. **Thời điểm xảy ra validation không cố định tại chính dòng `persist()`**:

- Với nhiều identifier generation strategies, insert được trì hoãn cho đến `flush()` hoặc commit.
- Với chiến lược như `IDENTITY`, Hibernate có thể cần INSERT sớm hơn để lấy ID, do đó lỗi có thể xuất hiện ngay trong `persist()` hoặc tại một điểm trước commit.
- Một query có thể kích hoạt auto-flush trước khi transaction kết thúc.
- Lifecycle event của Hibernate xảy ra khi ORM thực sự xử lý insert/update/delete theo mapping, không phải vì Java setter được gọi.

Vì thế caller không nên cho rằng `persist()` return nghĩa là dữ liệu đã được chấp nhận và commit.

## 4. Khi nào Hibernate/JPA tự chạy validation?

Trong Jakarta Persistence có tích hợp Jakarta Bean Validation, việc kiểm tra entity thường xảy ra với các lifecycle events sau:

| Lifecycle event | Thao tác ORM tương ứng | Validation group mặc định |
| --- | --- | --- |
| **Pre-persist** | Entity sắp được insert | `jakarta.validation.groups.Default` |
| **Pre-update** | Managed entity có update chuẩn bị ghi DB | `jakarta.validation.groups.Default` |
| **Pre-remove** | Entity sắp bị remove | **Không có group được validate theo mặc định** |

Những nhóm mặc định có thể được cấu hình lại bằng các persistence properties được trình bày sau.

### 4.1. Pre-persist không có nghĩa gọi mọi constraint tại mọi thời điểm

Một entity mới được tạo trong Java:

~~~java
PurchaseOrder order = PurchaseOrder.draft(...);
~~~

không tự validate ngay khi constructor kết thúc. Khi `entityManager.persist(order)` được gọi trong persistence context phù hợp, Hibernate chuyển entity sang trạng thái managed/pending insert. Validation thường gắn với pre-insert event khi Hibernate chuẩn bị ghi row.

Điều này giải thích vì sao hai lỗi khác nhau có thể xuất hiện ở hai thời điểm:

~~~java
entityManager.persist(order);
entityManager.flush(); // Ép ORM thực hiện những DML pending.
~~~

Nếu flush kích hoạt insert, đó là nơi Bean Validation có thể ném exception. Tuy nhiên không dựa vào `flush()` như ranh giới duy nhất vì IDENTITY insert hoặc cơ chế khác có thể làm sự kiện xảy ra sớm hơn.

### 4.2. Pre-update gắn với cập nhật entity thực sự

~~~java
@Transactional
public void renameCustomer(Long orderId, String newName) {
    PurchaseOrder order = entityManager.find(
            PurchaseOrder.class,
            orderId
    );

    order.changeCustomerName(newName);
    // Hibernate phát hiện dirty state khi flush.
}
~~~

Khi Hibernate xác định entity cần UPDATE, pre-update validation có thể kiểm tra các constraints trong nhóm tương ứng.

**Không thể suy ra rằng cứ gọi setter là pre-update validation chạy ngay.** Nếu setter gán lại cùng giá trị, hoặc entity không dirty theo cơ chế của Hibernate, có thể không có SQL UPDATE, và lifecycle pre-update không được kích hoạt.

Đối với một thay đổi chỉ tác động đến collection association, có thể có SQL INSERT/DELETE ở bảng nối/bảng child mà **không có UPDATE row của owner**. Không thiết kế quy tắc nghiệp vụ quan trọng dựa trên giả định owner luôn nhận pre-update callback khi collection membership đổi.

### 4.3. Pre-remove mặc định thường không validate

Ví dụ xóa một entity không còn hợp lệ theo `@NotBlank`:

~~~java
entityManager.remove(order);
~~~

Theo cấu hình mặc định, `Default` group không được tự áp cho pre-remove. Lý do thực tế: không nên chặn việc dọn dẹp dữ liệu cũ hỏng chỉ vì entity không còn thỏa quy tắc tạo/cập nhật hiện tại. Nhưng nếu có yêu cầu nghiệp vụ như “chỉ xóa order khi có mã xác nhận”, có thể cấu hình một group riêng cho pre-remove hoặc kiểm tra rõ trong service.

**Không nhầm `remove()` với hard delete trong mọi mapping**: soft delete qua custom SQL/@SQLDelete hoặc những cơ chế provider-specific có semantics khác. Cần kiểm tra event path thực sự và loại persistence operation được dùng.

## 5. Cài đặt Hibernate Validator và tích hợp Hibernate ORM

Hibernate ORM không đồng nghĩa với Hibernate Validator. Đây là hai dự án/module có vai trò khác nhau:

- **Hibernate ORM:** mapping entity, persistence context, HQL, SQL, transaction, flush, lifecycle events.
- **Hibernate Validator:** implementation của Jakarta Bean Validation, cung cấp constraint validators, message interpolation, validation factory.

### 5.1. Maven trong Spring Boot

Với Spring Boot 3.x:

~~~xml
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
~~~

Ngoài ra cần JDBC driver/database dependency phù hợp. Spring Boot dependency management sẽ chọn Hibernate ORM và Hibernate Validator versions tương thích với bản Boot đang dùng; không cần hardcode một phiên bản khác nếu chưa có lý do.

`spring-boot-starter-data-jpa` cung cấp JPA infrastructure, nhưng không nên giả định mọi stack/version tự động bổ sung một Bean Validation provider. `spring-boot-starter-validation` là cách thường dùng để có Hibernate Validator và tích hợp liên quan.

### 5.2. Maven khi cấu hình JPA thủ công

Ví dụ phụ thuộc độc lập:

~~~xml
<dependency>
    <groupId>org.hibernate.orm</groupId>
    <artifactId>hibernate-core</artifactId>
    <version>6.6.0.Final</version>
</dependency>

<dependency>
    <groupId>org.hibernate.validator</groupId>
    <artifactId>hibernate-validator</artifactId>
    <version>8.0.1.Final</version>
</dependency>
~~~

Phiên bản chỉ minh họa một kết hợp thuộc hệ Jakarta Persistence/Validation; dự án thật cần chọn một BOM/nhóm versions tương thích. Một runtime Jakarta EL implementation có thể cần thiết cho message interpolation nâng cao ngoài các cấu hình đơn giản; cần đọc yêu cầu của Hibernate Validator version đang dùng.

Khi chuyển từ Spring Boot 2/Hibernate 5 sang Boot 3/Hibernate 6, phải thay `javax.validation.*` bằng `jakarta.validation.*` và dùng các artifacts tương thích. Trộn hai namespace thường dẫn đến annotations không được provider mới nhận biết đúng.

### 5.3. Điều kiện để auto-validation hoạt động

Tùy JPA validation mode, Hibernate cần tìm được Bean Validation provider phù hợp qua bootstrap/runtime. Nếu implementation không có trong classpath và mode là `AUTO`, ORM có thể bỏ qua automatic validation theo cơ chế provider; nếu mode yêu cầu callback validation, việc thiếu provider có thể làm bootstrap thất bại.

Đừng kiểm tra bằng cách chỉ nhìn thấy annotation trong source. Cách đáng tin cậy là có integration test tạo một entity không hợp lệ và xác nhận persistence layer thực sự ném `jakarta.validation.ConstraintViolationException` ở thao tác thích hợp.

## 6. Validation mode: AUTO, CALLBACK, NONE

Jakarta Persistence định nghĩa validation-mode cho persistence unit. Có thể cấu hình qua `persistence.xml`:

~~~xml
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit name="salesPU">
        <validation-mode>AUTO</validation-mode>
    </persistence-unit>
</persistence>
~~~

Hoặc persistence property:

~~~properties
jakarta.persistence.validation.mode=AUTO
~~~

| Mode | Ý nghĩa | Khi nên cân nhắc |
| --- | --- | --- |
| `AUTO` | Tự tích hợp Bean Validation callbacks khi provider phù hợp hiện diện | Mặc định thông thường |
| `CALLBACK` | Yêu cầu validation callbacks; thiếu provider phù hợp có thể làm bootstrap lỗi | Khi validation là một điều kiện cấu hình bắt buộc |
| `NONE` | Tắt automatic lifecycle Bean Validation từ JPA | Khi ứng dụng có chiến lược khác rõ ràng hoặc cần test riêng |

**NONE không xóa constraint annotations.** Các calls `validator.validate(...)` thủ công và validation ở web/controller vẫn có thể hoạt động. Nó chỉ điều chỉnh việc JPA tự gọi validation tại entity lifecycle.

### 6.1. Spring Boot property forwarding

Khi dùng Spring Boot, có thể truyền JPA provider property:

~~~properties
spring.jpa.properties.jakarta.persistence.validation.mode=CALLBACK
~~~

Cơ chế đi qua `spring.jpa.properties.*` chuyển các properties tương ứng cho JPA provider. Hãy dùng đúng cú pháp configuration source của dự án và xác nhận property được áp dụng qua integration test.

Tránh đặt cùng tính năng ở nhiều nguồn với giá trị mâu thuẫn, ví dụ `persistence.xml` đặt NONE nhưng Spring Boot property yêu cầu CALLBACK, rồi dựa vào precedence ngầm.

### 6.2. Khi nào cần tắt automatic validation?

Có những ứng dụng legacy muốn validate entity qua một workflow riêng; hoặc batch import phải chấp nhận dữ liệu không hoàn chỉnh để staging trong một vùng riêng. Tuy vậy, tắt lifecycle validation có hậu quả:

- Invalid entity có thể vượt qua ORM layer.
- DB constraints vẫn có thể bắt một phần lỗi nhưng không bắt được mọi business rule.
- Những entry points khác như batch jobs có thể quên gọi manual validation.
- Dữ liệu cũ hỏng có thể lan sang use cases đọc/ghi khác.

Nếu bật `NONE`, phải mô tả chính xác lớp nào chịu trách nhiệm kiểm tra và có tests cho mọi write path quan trọng. Không tắt validation chỉ để làm một test lỗi “xanh” lên.

## 7. Constraint groups: không phải mọi quy tắc đều dùng cho mọi operation

Một entity thường có các mức kiểm tra khác nhau:

- Khi tạo draft, chỉ cần customerName hợp lệ.
- Khi xác nhận order, phải có email và ít nhất một dòng sản phẩm.
- Khi sửa order, có thể phải kiểm tra một quy tắc update riêng.
- Khi xóa, có thể cần chính sách xóa riêng, không phải toàn bộ create constraints.

Jakarta Validation cho phép dùng **groups** để lựa chọn tập constraints.

### 7.1. Khai báo nhóm bằng marker interface

~~~java
package com.example.sales.validation;

public interface OnCreate {}
~~~

~~~java
package com.example.sales.validation;

public interface OnUpdate {}
~~~

~~~java
package com.example.sales.validation;

public interface OnConfirm {}
~~~

Các interfaces này thường không có methods. Chúng là identifiers của constraint groups, không phải các hàm validate.

### 7.2. Gắn groups lên constraints

~~~java
@Entity
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotBlank
    private String customerName;  // Default group.

    @NotBlank(groups = OnCreate.class)
    @Email(groups = OnCreate.class)
    private String customerEmail;

    @NotNull(groups = OnConfirm.class)
    private Instant confirmedAt;

    @NotNull(groups = OnUpdate.class)
    private String changeReason;

    protected PurchaseOrder() {}
}
~~~

Đây là snippet tập trung vào constraints; dự án thật cần mapping đầy đủ theo mô hình nghiệp vụ. Không nên bắt buộc `changeReason` luôn có khi chỉnh mọi đơn hàng nếu yêu cầu nghiệp vụ chỉ áp dụng cho một số chuyển trạng thái; ví dụ nhằm minh họa group selection.

### 7.3. Default group là gì?

Constraint không khai báo `groups`, ví dụ:

~~~java
@NotBlank
private String customerName;
~~~

thuộc nhóm `jakarta.validation.groups.Default`. Khi gọi:

~~~java
validator.validate(order);
~~~

tương đương kiểm tra Default group (trừ khi có default group sequence được định nghĩa lại). Nó **không tự kiểm tra mọi custom group**.

Tương tự, JPA lifecycle validation mặc định kiểm tra `Default` ở pre-persist và pre-update. Một constraint chỉ khai báo `groups=OnConfirm.class` không tự được kiểm tra tại mỗi lần `persist()`/`update` trừ khi cấu hình group selection hoặc group sequence khiến nó được chọn.

### 7.4. Một constraint thuộc nhiều groups

~~~java
@NotBlank(groups = {
    Default.class,
    OnCreate.class,
    OnUpdate.class
})
private String customerName;
~~~

Ở đây nhập `jakarta.validation.groups.Default`. Cùng constraint có thể được chọn bởi một trong các nhóm. Khi khai báo nhiều groups trong một lần validation, provider có các quy tắc tránh thực hiện trùng constraint tương ứng trong một validation pass; không nên dựa vào số lượng exception messages bằng số group occurrences.

## 8. Cấu hình group cho các lifecycle events

Jakarta Persistence có các properties:

~~~properties
jakarta.persistence.validation.group.pre-persist
jakarta.persistence.validation.group.pre-update
jakarta.persistence.validation.group.pre-remove
~~~

Có thể đặt trong `persistence.xml` dưới dạng tên nhóm Java đầy đủ, ngăn cách bởi dấu phẩy:

~~~xml
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
  <persistence-unit name="salesPU">
    <properties>
      <property
          name="jakarta.persistence.validation.group.pre-persist"
          value="jakarta.validation.groups.Default,com.example.sales.validation.OnCreate"/>

      <property
          name="jakarta.persistence.validation.group.pre-update"
          value="jakarta.validation.groups.Default,com.example.sales.validation.OnUpdate"/>

      <property
          name="jakarta.persistence.validation.group.pre-remove"
          value="com.example.sales.validation.OnDelete"/>
    </properties>
  </persistence-unit>
</persistence>
~~~

Giả định `com.example.sales.validation.OnDelete` là một group marker interface có thật trong ứng dụng.

### 8.1. Tác dụng của cấu hình trên

- Pre-persist kiểm tra Default và OnCreate.
- Pre-update kiểm tra Default và OnUpdate.
- Pre-remove kiểm tra OnDelete thay vì không có group như mặc định.

Nếu chỉ khai báo:

~~~properties
jakarta.persistence.validation.group.pre-persist=com.example.sales.validation.OnCreate
~~~

thì **không nên mặc định Default cũng được kiểm tra**: property này thay đổi nhóm được chọn cho event tương ứng. Nếu muốn cả Default và custom group, khai báo cả hai.

### 8.2. Lưu ý khi gắn nhóm cho mọi update

Giả sử `OnConfirm` yêu cầu `confirmedAt != null`. Nếu thêm OnConfirm vào **mọi pre-update**, một draft order hợp lệ khi tạo có thể không còn chỉnh sửa được, bởi lần đổi tên khách cũng kích hoạt validation OnConfirm.

Đó là một lỗi **thiết kế group**, không phải lỗi Hibernate:

- Pre-update group áp dụng theo lifecycle event, không tự suy ra transition DRAFT → CONFIRMED.
- Nếu chỉ xác nhận đơn hàng mới cần kiểm tra OnConfirm, service nên validate group OnConfirm **tại transition**, hoặc sử dụng cơ chế nhóm/phân luồng nghiệp vụ phù hợp.
- Không để một update đơn giản bất ngờ đòi đầy đủ dữ liệu của một trạng thái nghiệp vụ khác.

### 8.3. Property configuration không phải tự kiểm tra trên SELECT

Các properties pre-persist/pre-update/pre-remove không làm mọi entity được tải từ DB tự validate. Khi chạy:

~~~java
PurchaseOrder order =
        entityManager.find(PurchaseOrder.class, id);
~~~

JPA không mặc nhiên ném `ConstraintViolationException` chỉ vì row trong DB vi phạm một constraint Java. Nếu cần kiểm tra dữ liệu legacy sau khi tải, gọi `validator.validate(order)` rõ ràng trong workflow phù hợp hoặc dùng cơ chế kiểm định data migration.

## 9. Group sequences và thứ tự kiểm tra

Nếu một số constraints rẻ và cần kiểm tra trước khi thực hiện những checks phức tạp, Jakarta Validation cho phép định nghĩa `@GroupSequence`.

~~~java
import jakarta.validation.GroupSequence;
import jakarta.validation.groups.Default;

public interface BasicChecks {}
public interface ExpensiveChecks {}

@GroupSequence({
    Default.class,
    BasicChecks.class,
    ExpensiveChecks.class
})
public interface OrderValidationSequence {}
~~~

Chạy:

~~~java
Set<ConstraintViolation<PurchaseOrder>> violations =
        validator.validate(order, OrderValidationSequence.class);
~~~

Ý nghĩa: thực hiện các groups theo thứ tự định nghĩa. Nếu một group trong sequence có violations, các groups sau có thể **không được chạy**. Điều này hữu ích khi một check chỉ có ý nghĩa nếu những dữ liệu cơ bản đã hợp lệ.

### 9.1. Không nhầm sequence với union groups

~~~java
validator.validate(order, BasicChecks.class, ExpensiveChecks.class);
~~~

không có cùng cam kết short-circuit theo thứ tự như một `@GroupSequence`. Nếu muốn dependency validation theo tầng, dùng sequence.

### 9.2. Redefine Default group trên entity

Một class có thể định nghĩa lại Default group sequence theo đặc tả. Khi làm vậy phải tuân thủ quy tắc sequence của Bean Validation, ví dụ nhóm đại diện cho chính class trong sequence và tránh vòng lặp. Đây là kỹ thuật nâng cao; không lạm dụng nếu service validation theo transition đã đủ rõ.

Hibernate Validator còn có một số extension cho dynamic default group sequences. Khi dùng extension, ghi rõ provider dependency và kiểm thử các trạng thái entity liên quan; không coi đó là portable Jakarta Validation API.

## 10. @Valid: kiểm tra lan truyền sang object liên quan

Annotation `@Valid` trên một association hoặc embedded value yêu cầu Bean Validation kiểm tra cả object được tham chiếu.

### 10.1. Validation cascade cho OrderLine

~~~java
@Entity
public class PurchaseOrder {

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL
    )
    @Valid
    private List<OrderLine> lines = new ArrayList<>();

    // ...
}
~~~

Khi PurchaseOrder được validate và provider đi qua `lines`, mỗi `OrderLine` có thể được kiểm tra theo group tương ứng.

Ví dụ một dòng có:

~~~java
@Positive
private int quantity;
~~~

với `quantity = 0`, validation của graph có thể có violation path đến `lines[0].quantity` (hình thức index/key trong path tùy collection).

### 10.2. @Valid không đồng nghĩa CascadeType.PERSIST

Hai annotations hoàn toàn khác:

| Annotation | Tác dụng |
| --- | --- |
| `jakarta.validation.Valid` | Cascade **kiểm tra constraints** sang object được tham chiếu |
| `jakarta.persistence.CascadeType.PERSIST` | Cascade **persist operation** theo JPA |
| `CascadeType.MERGE` | Cascade **merge operation** |
| `CascadeType.REMOVE` | Cascade **remove operation** |
| `CascadeType.ALL` | Tổng hợp các cascade operations của JPA |

Có thể có `@Valid` mà không có JPA cascade: validator kiểm tra object con nhưng việc persist/merge con vẫn tuân theo mapping/cascade JPA riêng. Ngược lại, có JPA cascade persist mà **không có `@Valid`**, thì không thể mặc định việc validate parent sẽ traverse toàn bộ child graph; tuy nhiên child entity nếu được persist cũng có lifecycle validation của chính nó.

### 10.3. Khi validate association có lazy loading

Một quan hệ `@ManyToOne(fetch = LAZY)` hoặc `@OneToMany(fetch = LAZY)` có thể chưa được tải. Khi tích hợp Bean Validation với JPA, provider có cơ chế traversable resolution dựa trên trạng thái association đã được tải để tránh việc validation vô tình ép tải toàn bộ graph trong những trường hợp không cần.

Không nên tuyên bố “đặt `@Valid` luôn tải mọi lazy association” hoặc “không bao giờ tải gì”: behavior có thể phụ thuộc object đã initialized, cách truy cập field/property, provider và validation context. Hãy kiểm tra SQL và fetch plan nếu một validation cascade có nguy cơ mở rộng graph quá lớn.

### 10.4. Không validate hai chiều không kiểm soát

Entity graph thường có liên kết hai chiều:

~~~text
Order
  -> lines
     -> order
        -> lines
        ...
~~~

Bean Validation có cơ chế tránh vòng lặp vô hạn khi cascade validation theo object identity/group trong một validation call, nhưng thiết kế `@Valid` ở cả hai phía không phải lúc nào cần thiết. Chọn hướng cascade theo aggregate boundary và use case để giảm công việc không cần thiết.

## 11. @ConvertGroup: chuyển nhóm khi đi qua association

Một tình huống: khi validate một PurchaseOrder theo `Default`, các OrderLine cần được kiểm tra theo nhóm `LineChecks`.

~~~java
public interface LineChecks {}
~~~

~~~java
@Entity
public class PurchaseOrder {

    @Valid
    @ConvertGroup(
        from = Default.class,
        to = LineChecks.class
    )
    @OneToMany(mappedBy = "order", cascade = CascadeType.ALL)
    private List<OrderLine> lines = new ArrayList<>();

    // ...
}
~~~

Ở OrderLine:

~~~java
@Positive(groups = LineChecks.class)
private int quantity;
~~~

Cần imports:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.groups.ConvertGroup;
import jakarta.validation.groups.Default;
~~~

Khi validation cascade đi từ parent sang child với Default group, group có thể được chuyển sang LineChecks cho phía child. Điều này giúp các aggregate components áp dụng tập quy tắc phù hợp mà không ép mọi constraint vào Default.

### 11.1. Không dùng ConvertGroup để che model khó hiểu

Nếu một trường bắt buộc chỉ khi Order chuyển sang CONFIRMED, một nhóm `OnConfirm` rõ ràng và service transition có thể dễ hiểu hơn một mạng lưới group conversions khó theo dõi. `@ConvertGroup` hữu ích nhưng nên dùng khi mô hình thật sự yêu cầu thay group ở association boundary.

Ngoài ra, group conversion chỉ có ý nghĩa trong cascaded validation; không dùng `@ConvertGroup` trên một field không có `@Valid` rồi kỳ vọng nó tự kích hoạt validation.

## 12. Persist, merge và dirty checking: object nào được validate?

### 12.1. Persist một entity mới

~~~java
PurchaseOrder order = PurchaseOrder.createDraft(command);
entityManager.persist(order);
~~~

Entity mới trở thành managed theo JPA lifecycle; khi Hibernate chuẩn bị INSERT, pre-persist validation được áp dụng theo groups cấu hình.

### 12.2. Merge detached entity

~~~java
PurchaseOrder detached = loadFromAnotherContext();
detached.changeCustomerName("New name");

PurchaseOrder managed = entityManager.merge(detached);
~~~

`merge()` sao chép state từ detached object vào **managed instance** do JPA quản lý. Tham chiếu `detached` không tự trở thành managed chỉ vì gọi merge. Pre-update validation thường xảy ra đối với state của entity managed được ghi, không phải cam kết rằng mọi field của detached object được validate ngay tại dòng `merge()`.

Nếu merge dẫn tới INSERT cho một entity mới, hành vi lifecycle tương ứng có thể là pre-persist thay vì pre-update. Phải hiểu entity state và identifier strategy.

**Khuyến nghị:** với use case sửa dữ liệu, thường load managed entity trong transaction rồi gọi domain methods/patch fields được cho phép, thay vì lấy một object từ request và merge toàn bộ field không kiểm soát.

### 12.3. Dirty checking có thể không phát UPDATE

~~~java
PurchaseOrder managed = entityManager.find(
        PurchaseOrder.class,
        orderId
);

managed.changeCustomerName(managed.getCustomerName());
~~~

Nếu trạng thái thực tế không đổi, Hibernate có thể không phát SQL UPDATE. Khi không có pre-update event, JPA lifecycle validation tương ứng có thể không chạy. Vì vậy **không dùng pre-update validation như một cơ chế bắt buộc kiểm tra mọi command bất kể có thay đổi row hay không**.

Nếu một command cần được kiểm tra ngay cả khi không dirty, hãy validate request/aggregate rõ ràng ở service boundary.

### 12.4. Bulk HQL/JPQL và native SQL thường bỏ qua entity validation

Ví dụ:

~~~java
entityManager.createQuery(
        "update PurchaseOrder o " +
        "set o.customerEmail = :email " +
        "where o.status = :status"
    )
    .setParameter("email", "invalid-email")
    .setParameter("status", OrderStatus.DRAFT)
    .executeUpdate();
~~~

Đây là **bulk update** qua HQL/JPQL. Nó không tải và dirty-check từng PurchaseOrder như các managed entities thông thường, do đó **không kích hoạt pre-update Bean Validation cho từng row**.

Tương tự:

~~~java
entityManager.createNativeQuery(
        "update purchase_orders set customer_email = :email"
    )
    .setParameter("email", "not-an-email")
    .executeUpdate();
~~~

SQL native trực tiếp đi tới database. Nếu DB chỉ có NOT NULL và không có CHECK cho email format, một chuỗi sai format có thể được lưu thành công.

### 12.5. Các đường ghi khác cũng cần kiểm tra

- JDBC template hoặc JDBC batch.
- Direct database scripts.
- ETL/import jobs.
- Migration DML.
- Một ứng dụng khác dùng cùng database.
- Stored procedures hoặc triggers.
- Bulk deletes/updates theo provider.

Các đường này không mặc định đi qua Jakarta Bean Validation trên entity. Nếu quy tắc phải đúng ở mọi write path, hãy có **DB constraint** thích hợp, API/domain checks hoặc một lớp validation chung có chủ đích.

## 13. Lifecycle callbacks và Bean Validation

Jakarta Persistence cũng có callbacks như `@PrePersist`, `@PreUpdate`, `@PreRemove`:

~~~java
@Entity
public class PurchaseOrder {

    @PrePersist
    void setCreationTime() {
        if (createdAt == null) {
            createdAt = Instant.now();
        }
    }

    // ...
}
~~~

Callbacks có thể gán những giá trị chuẩn hóa hoặc timestamps trước khi SQL được ghi. Theo quy trình lifecycle integration của Jakarta Persistence, automatic validation được áp dụng tại thời điểm liên quan tới các lifecycle callback events trước hoạt động DB; những thay đổi do callbacks thực hiện có thể ảnh hưởng state được validate.

Tuy nhiên không nên thiết kế callbacks như một “dịch vụ nghiệp vụ ẩn”:

- Callback không nên gọi remote API hoặc gây side effects khó rollback.
- Không nên tự mở transaction/repository calls từ callbacks.
- Không giả định callbacks chạy khi bulk HQL/native update.
- Không tự gọi `persist()/remove()` trên một tập entity tùy ý trong callback nếu không nắm rõ giới hạn của spec/provider.
- Nên giữ callbacks nhỏ, deterministic, gắn với state của entity.

### 13.1. Cách tách nhiệm vụ

| Thành phần | Trách nhiệm phù hợp |
| --- | --- |
| Constructor/domain method | Bảo vệ những invariants có thể kiểm tra ngay |
| `@PrePersist` / `@PreUpdate` | Bổ sung metadata kỹ thuật/normalization nhỏ khi phù hợp |
| Jakarta Bean Validation | Kiểm tra constraints khai báo trên object graph |
| Spring service | Điều phối use case, transitions, authorization, transaction |
| Database constraints | Bảo vệ tính đúng của dữ liệu ở nguồn lưu trữ |

**Không dựa duy nhất vào pre-update callback để xử lý mọi business transition**, vì lifecycle event được quyết định bởi ORM dirty checking/flush, không phải mọi hành động của người dùng.

## 14. Custom constraint: quy tắc liên quan nhiều field

Các annotation đơn giản như `@NotNull` và `@Positive` kiểm tra từng property. Nhưng một quy tắc như “ngày giao không được trước ngày gửi” cần nhìn ít nhất hai fields.

Có thể tạo class-level constraint.

### 14.1. Khai báo annotation

~~~java
package com.example.sales.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

import java.lang.annotation.*;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = DeliveryDatesValidator.class)
@Documented
public @interface ValidDeliveryDates {

    String message() default
        "deliveredAt must not be before shippedAt";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

### 14.2. Viết validator

~~~java
package com.example.sales.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public class DeliveryDatesValidator
        implements ConstraintValidator<ValidDeliveryDates, Shipment> {

    @Override
    public boolean isValid(
            Shipment shipment,
            ConstraintValidatorContext context
    ) {
        if (shipment == null) {
            return true;
        }

        if (shipment.getDeliveredAt() == null) {
            return true; // Chưa giao là trạng thái hợp lệ ở đây.
        }

        if (shipment.getShippedAt() == null) {
            return false;
        }

        return !shipment.getDeliveredAt()
                .isBefore(shipment.getShippedAt());
    }
}
~~~

### 14.3. Gắn constraint lên entity

~~~java
@Entity
@ValidDeliveryDates
public class Shipment {

    @Id
    private Long id;

    private Instant shippedAt;
    private Instant deliveredAt;

    // Getters...
}
~~~

Các class là ví dụ, cần import `java.time.Instant`, Jakarta Persistence và những constructors phù hợp. Custom validator trên class được chạy khi validation group của constraint đó được chọn.

### 14.4. Đưa violation vào property cụ thể

Mặc định class-level violation path có thể trỏ tới root object. Nếu muốn API báo lỗi trên field `deliveredAt`, có thể tùy chỉnh context:

~~~java
context.disableDefaultConstraintViolation();

context.buildConstraintViolationWithTemplate(
        "Delivery date must follow shipping date"
    )
    .addPropertyNode("deliveredAt")
    .addConstraintViolation();

return false;
~~~

Đoạn này chỉ là phần thêm vào nhánh lỗi trong `isValid()`; cần đặt đúng vị trí khi biết ngày giao không hợp lệ. Không ném exception tùy tiện trong validator cho một input bất hợp lệ thường gặp; trả `false` để Bean Validation tổng hợp violations.

### 14.5. Custom validators nên không có side effects

Không cho `ConstraintValidator` tự gọi repository để sửa entity hoặc gửi email. Validators có thể được gọi nhiều lần và ở nhiều boundary, bao gồm web validation, programmatic validation và JPA lifecycle. Chúng nên:

- Có semantics rõ ràng.
- Không thay đổi object đang kiểm tra.
- Không tạo writes ngoài ý muốn.
- Tránh I/O chậm gây timeout khi flush.
- Không giả định transaction luôn tồn tại nếu validator có dùng một dependency.

Đối với quy tắc đòi transaction/database isolation như uniqueness trong hệ thống đồng thời, thường nên dùng database constraint thay vì chỉ custom validator truy vấn DB.

## 15. Unique constraint: Bean Validation không thay thế database concurrency control

Một câu hỏi rất phổ biến: “Tôi có thể viết validator kiểm tra email chưa tồn tại, vậy có cần UNIQUE ở database nữa không?”

Giả sử hai request A và B cùng làm:

~~~text
A: SELECT count(customer where email = x) -> 0
B: SELECT count(customer where email = x) -> 0

A: INSERT email = x
B: INSERT email = x
~~~

Nếu chỉ kiểm tra bằng query từ validator, hai request đều thấy email chưa tồn tại và cả hai có thể cố INSERT. Đây là **race condition**.

Cơ chế vững hơn:

~~~java
@Table(
    name = "customers",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customer_email",
        columnNames = "email"
    )
)
~~~

Đồng thời migration tạo một UNIQUE constraint thật trong DB:

~~~sql
alter table customers
    add constraint uk_customer_email unique (email);
~~~

Cú pháp DDL ví dụ, cần điều chỉnh theo DBMS và dữ liệu đã tồn tại. Annotation `@UniqueConstraint` giúp schema generation hiểu ý định, nhưng nếu production quản lý schema bằng Flyway/Liquibase, **chỉ migration đã áp mới quyết định constraint có thật**.

### 15.1. Kiểm tra trước để cải thiện UX, DB constraint để bảo đảm đúng

Có thể query trước xem email đã dùng chưa nhằm hiển thị thông báo sớm. Nhưng **không được coi query đó là bảo đảm atomic**. Vẫn phải chuẩn bị xử lý database unique violation tại flush/commit.

Một custom Bean Validation uniqueness check còn có những vấn đề:

- Phải loại trừ chính entity hiện tại khi update.
- Dễ N+1 queries nếu validate nhiều entities.
- Có race condition ở mức transaction.
- Có thể chạy nhiều lần khi ORM flush.
- Không bảo vệ dữ liệu từ JDBC/import/external systems.

Với invariant uniqueness, database là nơi bảo vệ cuối cùng.

## 16. ConstraintViolationException từ Bean Validation

Khi entity lifecycle validation thất bại, exception thường là:

~~~java
jakarta.validation.ConstraintViolationException
~~~

Có thể lấy tập violations:

~~~java
try {
    entityManager.persist(order);
    entityManager.flush();
} catch (jakarta.validation.ConstraintViolationException ex) {

    for (ConstraintViolation<?> violation :
            ex.getConstraintViolations()) {

        System.out.println(
            violation.getPropertyPath() +
            " -> " +
            violation.getMessage()
        );
    }

    throw ex; // Để transaction boundary rollback.
}
~~~

Đây là ví dụ minh họa cách đọc lỗi; trong ứng dụng Spring, nên để exception đi qua transactional boundary rồi xử lý thành API response ở lớp ngoài (ví dụ `@ControllerAdvice`), thay vì nuốt exception và cố tiếp tục dùng cùng Hibernate Session.

### 16.1. Thông tin trong ConstraintViolation

| API | Nội dung |
| --- | --- |
| `getPropertyPath()` | Đường dẫn thuộc tính vi phạm, có thể chứa node của collection |
| `getMessage()` | Message đã nội suy theo locale/provider |
| `getMessageTemplate()` | Template được khai báo trên constraint |
| `getInvalidValue()` | Giá trị không hợp lệ |
| `getConstraintDescriptor()` | Metadata của constraint |
| `getRootBean()` | Root object được validate |
| `getLeafBean()` | Object chứa constraint tại điểm vi phạm |

**Cảnh báo bảo mật:** không ghi thẳng `getInvalidValue()` hoặc `getRootBean()` vào production logs/API response vì chúng có thể chứa dữ liệu cá nhân, secrets, token hoặc toàn bộ entity graph. Chỉ trả field path và message phù hợp với hợp đồng API.

### 16.2. Hai ConstraintViolationException khác nhau

Đây là nguồn nhầm lẫn thường gặp:

~~~java
// Bean Validation:
jakarta.validation.ConstraintViolationException

// Hibernate ORM/JDBC constraint:
org.hibernate.exception.ConstraintViolationException
~~~

Hai classes có tên giống nhau nhưng thuộc package khác nhau và nghĩa khác nhau.

- `jakarta.validation.ConstraintViolationException`: Java object vi phạm Bean Validation constraints.
- `org.hibernate.exception.ConstraintViolationException`: database từ chối một SQL operation do constraint ở database (ví dụ UNIQUE, FK, CHECK), được Hibernate chuyển thành ORM exception.
- Trong Spring, lỗi DB có thể được translate thành `DataIntegrityViolationException` tùy đường đi qua repository/exception translation.

Không bắt một class rồi tin rằng nó đại diện cho cả hai. Khi thiết kế error handling, phân biệt **validation error của object** và **database integrity error**.

### 16.3. Exception xuất hiện lúc commit

Nếu `persist()` không flush ngay:

~~~java
@Transactional
public void create(PurchaseOrder order) {
    entityManager.persist(order);
    // Không gọi flush().
}
~~~

Hibernate có thể chỉ phát hiện lỗi khi transaction interceptor thực hiện flush/commit **sau khi method body return**. Do đó try/catch chỉ quanh dòng persist trong cùng method có thể không bắt được lỗi.

Nếu cần chủ động phát hiện tại một điểm kiểm soát được, có thể dùng `flush()`:

~~~java
entityManager.persist(order);
entityManager.flush();
~~~

Nhưng một lỗi Bean Validation/JDBC đã xảy ra tại flush không phải tín hiệu để sửa entity và tiếp tục transaction tùy tiện. Rollback và tạo unit of work mới khi cần retry.

## 17. Transaction rollback và trạng thái Session sau lỗi

`jakarta.validation.ConstraintViolationException` là runtime exception. Với default `@Transactional` của Spring, nếu exception thoát ra khỏi transactional interceptor, Spring thường đánh dấu transaction để rollback.

~~~java
@Service
public class OrderService {

    @Transactional
    public Long create(CreateOrderCommand command) {
        PurchaseOrder order = PurchaseOrder.from(command);
        entityManager.persist(order);
        entityManager.flush();
        return order.getId();
    }
}
~~~

Nếu validation thất bại, caller nên nhận một kết quả lỗi phù hợp. Transaction không được commit.

### 17.1. Không tiếp tục Session đã có ORM failure

Không làm:

~~~java
@Transactional
public void unsafe(PurchaseOrder order) {
    try {
        entityManager.persist(order);
        entityManager.flush();
    } catch (RuntimeException exception) {
        // Cố sửa một field và tiếp tục cùng EntityManager/transaction:
        order.setCustomerEmail("fixed@example.com");
        entityManager.flush();
    }
}
~~~

Khi ORM operation tại flush bị lỗi, session/persistence context có thể đang giữ pending actions hoặc snapshot state không còn đáng tin, và transaction có thể rollback-only. Không nên “chữa” một failed flush bằng cách thử tiếp trong cùng context.

Cách xử lý thông thường:

1. Rollback current transaction.
2. Kết thúc/discard failed persistence context.
3. Trả lỗi validation có cấu trúc cho caller.
4. Nếu người dùng sửa dữ liệu, thực hiện lại operation trong **transaction và context mới**.

### 17.2. Manual validate trước khi persist giúp tránh failed flush

Có thể kiểm tra trước khi entity được quản lý:

~~~java
Set<ConstraintViolation<PurchaseOrder>> violations =
        validator.validate(order);

if (!violations.isEmpty()) {
    throw new jakarta.validation.ConstraintViolationException(
            "Invalid order",
            violations
    );
}

entityManager.persist(order);
~~~

Manual validation mang lại thời điểm báo lỗi chủ động, nhưng **không được thay thế hoàn toàn lifecycle validation**: state có thể thay đổi sau đó, entities khác có thể được persist trong cùng unit of work, hoặc một entry point khác có thể bỏ qua manual check.

Khi yêu cầu kiểm tra group `OnConfirm` trước một business transition, manual validation tại service boundary thường là lựa chọn rõ ràng, rồi JPA Default validation vẫn là lớp bảo vệ cuối trong ORM path.

## 18. Spring MVC validation và JPA validation là hai thời điểm khác nhau

Request DTO:

~~~java
public record CreateOrderRequest(
        @NotBlank String customerName,
        @NotBlank @Email String customerEmail,
        @NotEmpty List<@Valid CreateOrderLineRequest> lines
) {}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService service;

    @PostMapping
    public ResponseEntity<?> create(
            @Valid @RequestBody CreateOrderRequest request
    ) {
        Long id = service.create(request.toCommand());
        return ResponseEntity.ok(id);
    }
}
~~~

`@Valid @RequestBody` ở Spring MVC yêu cầu validate **request DTO** trước khi controller method chạy. Khi DTO vi phạm constraints, Spring thường báo lỗi binding/validation ở web layer, như `MethodArgumentNotValidException` tùy signature/framework version.

JPA lifecycle validation lại kiểm tra **entity state** khi Hibernate chuẩn bị persist/update.

| Tiêu chí | Request validation | JPA entity lifecycle validation |
| --- | --- | --- |
| Đối tượng | HTTP request DTO | Managed entity/state ORM |
| Thời điểm | Trước/khi thực thi controller handler | Pre-persist/pre-update/... |
| Kích hoạt | `@Valid`/`@Validated` trong MVC hoặc method validation | JPA Bean Validation integration |
| Thường trả lỗi | Binding/validation exception của Spring | `jakarta.validation.ConstraintViolationException` |
| Có áp dụng cho batch job không? | Không nếu job không đi qua HTTP | Có thể có nếu job dùng ORM entity lifecycle |
| Có thay DB constraints không? | Không | Không |

Một số quy tắc có thể được tái sử dụng giữa DTO và entity, nhưng không buộc mọi entity dùng cùng annotations với HTTP schema. DTO và entity có lifecycle khác nhau; request có thể cho phép field optional để PATCH, còn entity phải luôn hợp lệ theo state nghiệp vụ.

### 18.1. @Validated cho nhóm theo use case

Spring cung cấp `@Validated` để chọn validation groups trong những contexts được Spring hỗ trợ, ví dụ:

~~~java
@PostMapping("/confirm")
public ResponseEntity<?> confirm(
        @Validated(OnConfirm.class)
        @RequestBody ConfirmOrderRequest request
) {
    // ...
}
~~~

`@Validated` thuộc `org.springframework.validation.annotation.Validated`. Đây là cơ chế chọn group ở web/method layer, **không tự đổi các nhóm JPA pre-update**. Nếu entity cần OnConfirm validation tại domain transition, phải gọi group đó phù hợp hoặc cấu hình lifecycle group theo model đã thiết kế.

### 18.2. PATCH và validation groups

Với PATCH, DTO thường cho phép một số field null vì chúng có nghĩa “không cập nhật”. Nếu copy `@NotNull` của entity vào mọi field của PATCH DTO, request hợp lệ có thể bị từ chối.

Giải pháp có thể là:

- Dùng request DTO riêng cho create/patch.
- Phân biệt absent với explicit null theo API schema.
- Áp patch lên managed entity trong transaction.
- Validate entity/default group sau khi thay đổi khi cần.
- Validate transition-specific group riêng cho business action.

**Không dùng entity trực tiếp làm request body rồi merge tất cả field từ client**, nhất là các field ID, status, tenantId, version hoặc quyền sở hữu.

## 19. Kiểm tra ràng buộc liên quan đến dữ liệu động và groups

### 19.1. Quy tắc phụ thuộc trạng thái Order

Một order ở DRAFT có thể không có địa chỉ giao hàng. Nhưng khi CONFIRMED, địa chỉ là bắt buộc. Có ít nhất hai cách:

**Cách A — explicit validation tại transition**

~~~java
@Service
public class ConfirmationService {

    private final Validator validator;

    @Transactional
    public void confirm(Long orderId) {
        PurchaseOrder order =
                entityManager.find(PurchaseOrder.class, orderId);

        Set<ConstraintViolation<PurchaseOrder>> violations =
                validator.validate(order, OnConfirm.class);

        if (!violations.isEmpty()) {
            throw new jakarta.validation.ConstraintViolationException(
                    violations
            );
        }

        order.confirm();
    }
}
~~~

Nếu `order.confirm()` tạo thêm dữ liệu có thể ảnh hưởng constraints, cân nhắc validate **state đích** sau khi áp transition nhưng trước flush/commit. Quyết định thứ tự phụ thuộc domain method có được phép chuyển sang trạng thái tạm không hợp lệ trong memory hay không.

**Cách B — class-level invariant theo state**

~~~java
@ValidOrderState
@Entity
public class PurchaseOrder {
    private OrderStatus status;
    private String shippingAddress;
}
~~~

Một custom class-level validator kiểm tra `shippingAddress` khi status CONFIRMED. Constraint thuộc Default group nên tự chạy khi pre-persist/pre-update, nhưng phải thiết kế để các trạng thái DRAFT được phép thiếu address.

Cách B có ưu điểm bảo vệ cùng invariant ở mọi entity write path có lifecycle validation; cách A giúp thể hiện rõ use case. Có thể kết hợp: domain transition validate sớm, class-level invariant bảo vệ ở ORM boundary.

### 19.2. Không dùng groups để lách ràng buộc DB bắt buộc

Nếu database cột `shipping_address` là NOT NULL, một Draft order không có address vẫn không thể insert, dù Bean Validation bỏ qua constraint đó ở Default group. Khi thiết kế state-dependent constraints, database nullability cũng phải tương thích với model cho phép draft. Có thể giữ column nullable rồi dùng class-level business validation hoặc DB CHECK conditional phù hợp.

Nhóm validation chỉ điều khiển **Java constraints được chọn**, không thay cấu trúc database.

## 20. Thứ tự callback, validation và SQL: nên kỳ vọng điều gì?

Với ORM-managed entity, một chuỗi đơn giản có thể được nhìn như:

~~~text
New Java object
    ↓
service/domain method tạo hoặc thay state
    ↓
EntityManager.persist(...) hoặc managed dirty state
    ↓
Hibernate flush quyết định action INSERT/UPDATE
    ↓
JPA/Hibernate lifecycle callbacks theo event
    ↓
Automatic Bean Validation cho groups cấu hình
    ↓
SQL INSERT/UPDATE + DB constraints
    ↓
Commit transaction hoặc rollback khi có lỗi
~~~

Đây là sơ đồ thứ tự khái niệm. Implementation có thể gọi callbacks, validate và generate ID ở các điểm cụ thể theo mapping/version; không lấy sơ đồ này để đoán chính xác một event sẽ xuất hiện ở dòng source code nào.

### 20.1. Nếu callback tự thay đổi field

~~~java
@PrePersist
void beforeInsert() {
    if (createdAt == null) {
        createdAt = Instant.now();
    }
}
~~~

Constraint:

~~~java
@NotNull
private Instant createdAt;
~~~

Một callback trước insert có thể bổ sung timestamp để state hợp lệ. Nhưng đừng lạm dụng callback để sửa những field mà người dùng nhập sai; validation failure nên được thể hiện rõ, không tự thay email trống bằng placeholder.

### 20.2. Tại sao listener không phải nơi gọi repository tùy ý?

Entity listeners hoạt động trong lifecycle ORM, thường gần thời điểm flush. Nếu listener gọi query, persist entity khác, gửi message hoặc truy cập lazy graph lớn, có thể gặp reentrancy, flush ordering, deadlocks, N+1 hoặc side effect sau rollback. Nên tách logic nghiệp vụ phức tạp ra application service/domain event handler với transaction semantics rõ.

## 21. Bean Validation không bảo đảm dữ liệu luôn hợp lệ sau khi đã lưu

Ngay cả khi Hibernate tự validate ở pre-persist/pre-update, dữ liệu có thể thay đổi ngoài đường ORM:

~~~sql
update purchase_orders
set customer_email = 'not-an-email'
where id = 42;
~~~

Nếu database không có constraint tương ứng, câu SQL có thể thành công. Sau đó ứng dụng:

~~~java
PurchaseOrder order =
        entityManager.find(PurchaseOrder.class, 42L);
~~~

vẫn có thể tải state không hợp lệ. **Automatic entity validation không đồng nghĩa validate-on-load.**

Hệ quả:

- Dữ liệu legacy có thể đang vi phạm annotations mới.
- Các ứng dụng khác có thể bypass validation.
- Batch/native updates có thể bypass callbacks.
- DB migration cần data checks/backfills khi đổi constraints.
- Không nên giả định mọi managed entity được tải đều hợp lệ cho một business operation mới.

Nếu use case cần kiểm tra dữ liệu nhập từ ngoài, hãy validate tại điểm đưa dữ liệu vào hệ thống và dùng DB constraints cho invariants có thể enforce ở database.

## 22. Hiệu năng: validation không miễn phí

Khi một transaction flush nhiều entities, JPA validation có thể chạy nhiều lần theo event path. Chi phí có thể đến từ:

- Reflection/metadata lookups (thường được provider cache).
- Traversal của object graph với `@Valid`.
- Class-level/custom validators.
- Message interpolation.
- Custom validation logic gọi DB/network.
- Constraint groups/sequence phức tạp.
- Kiểm tra hàng nghìn child records trong batch import.

### 22.1. Batch processing

Ví dụ import 20.000 OrderLine entities:

~~~java
@Transactional
public void importLines(List<LineInput> inputs) {
    int count = 0;

    for (LineInput input : inputs) {
        entityManager.persist(toOrderLine(input));

        if (++count % 50 == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
~~~

Đây là pattern giới hạn kích thước persistence context, nhưng **không giải quyết hoàn toàn lỗi batch transaction**: một entity vi phạm constraint ở giữa batch có thể khiến transaction rollback; Hibernate/JDBC error cần được xử lý như lỗi của unit of work. Nếu ứng dụng muốn bỏ qua rows sai mà vẫn commit rows tốt, nên validate/partition dữ liệu trước rồi sử dụng các transactions/chunks riêng, không tiếp tục dùng Session đã flush lỗi.

### 22.2. Tránh validators gọi DB cho từng row

Một custom validator thực hiện:

~~~java
repository.existsBySku(value.getSku());
~~~

trên mỗi row có thể gây N+1 database round trips và race conditions. Thường có thể tối ưu bằng cách validate cấu trúc input trước, dùng batch lookups ở service, còn uniqueness được DB bảo vệ.

### 22.3. Đừng tắt validation để tối ưu trước khi đo

Nếu flush chậm, có thể nguyên nhân nằm ở JDBC batch, indexes, locks, association fetching hoặc SQL execution chứ không phải validation. Cần profiling/metrics để biết tỷ lệ chi phí. Tắt toàn bộ JPA lifecycle validation có thể cải thiện một trường hợp benchmark nhưng đánh đổi correctness ở nhiều write paths.

## 23. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `@NotBlank` không chặn insert | Không có provider, validation mode NONE, group không được chọn hoặc write bypass ORM | Kiểm tra provider/mode/groups và integration test |
| Gọi `persist()` xong không thấy lỗi | Validation có thể xảy ra khi flush/commit | Ép flush trong test hoặc quan sát transaction boundary |
| Entity không dirty nhưng @PreUpdate không chạy | Hibernate không cần UPDATE row | Validate ở service nếu command luôn phải được kiểm tra |
| Sửa collection nhưng owner không được validate | Collection DML không nhất thiết kích hoạt owner PRE_UPDATE | Validate aggregate explicitly khi sửa association |
| OnConfirm constraint không chạy lúc update | Pre-update mặc định chỉ Default | Gọi validator.validate(entity, OnConfirm.class) ở transition |
| Draft không thể sửa vì thiếu confirmedAt | Đưa OnConfirm vào mọi pre-update | Thiết kế lại groups theo state/use case |
| Child invalid nhưng parent validate không phát hiện | Chưa cascade `@Valid` hoặc child chưa thuộc validation graph | Thêm `@Valid` có chủ đích, kiểm tra cascade |
| Child persist được nhưng parent @Valid không thấy | JPA cascade và Bean Validation cascade khác nhau | Thiết kế riêng cả hai loại cascade |
| Error xuất hiện ở commit, không trong method | Hibernate flush tại transaction boundary | Catch ngoài proxy / validate sớm nếu cần |
| Database unique violation dù @Email hợp lệ | @Email kiểm tra format, không kiểm tra uniqueness | DB UNIQUE constraint |
| Bean Validation exception bị bắt sai loại | Nhầm `jakarta.validation` với `org.hibernate.exception` | Phân biệt class packages |
| `noRollbackFor` nhưng transaction vẫn rollback | DB/Hibernate đã đánh dấu rollback-only sau SQL failure | Không tiếp tục failed Session |
| Bulk HQL/native UPDATE lưu dữ liệu sai format | Bypass per-entity callbacks | Validate trước, DB constraint hoặc dùng managed update |
| Update entity bị chậm vì @Valid graph lớn | Cascaded validation/custom validator tốn chi phí | Kiểm tra graph, groups, profile và thiết kế aggregate |
| Import batch lỗi một item khiến rollback toàn bộ | Một transaction chung và flush thất bại | Validate/chia chunk trước, tạo transaction riêng hợp đồng |
| Validate-on-load không xảy ra | JPA không mặc định validate mọi SELECT/find | Kiểm tra dữ liệu ở use case hoặc migration |
| @NotNull trên generated ID khiến create fail | Kiểm tra generated field quá sớm/không phù hợp group | Không đặt invariant ID theo thời điểm không đúng |
| Constraint annotation không xuất hiện ở generated schema | DDL integration/provider không tạo được ràng buộc mong muốn | Tạo migration DB rõ ràng |
| @Validated Spring controller hoạt động nhưng JPA không | Hai integration points khác nhau | Kiểm tra riêng JPA validation mode/provider |

Không chữa những lỗi này bằng cách tắt validation ngay. Trước tiên xác định object nào đang được validate, group nào được chọn, event nào đã phát và exception xảy ra ở lớp nào.

## 24. Kiểm thử lifecycle validation trên database thật

Unit test `validator.validate(order)` chứng minh Bean Validation annotations hoạt động, nhưng **không chứng minh JPA tự kích hoạt validation khi flush**. Muốn kiểm tra integration, cần test chạy Hibernate/JPA thật.

### 24.1. Test pre-persist

~~~java
@DataJpaTest
class OrderValidationIntegrationTest {

    @PersistenceContext
    EntityManager em;

    @Test
    void invalid_email_is_rejected_before_insert() {
        PurchaseOrder order = PurchaseOrder.testDraft(
                "Alice",
                "not-an-email"
        );

        assertThrows(
            jakarta.validation.ConstraintViolationException.class,
            () -> {
                em.persist(order);
                em.flush();
            }
        );
    }
}
~~~

Mô hình `PurchaseOrder.testDraft` là factory giả định trong test, cần bảo đảm các fields khác hợp lệ để test chỉ thất bại vì email. Với IDENTITY, lỗi có thể xuất hiện tại `persist`, nên đặt cả persist và flush trong lambda để test không phụ thuộc vào thời điểm sinh ID.

`@DataJpaTest` thuộc Spring Boot Test, `@PersistenceContext` thuộc Jakarta Persistence và `@Test` thuộc JUnit Jupiter.

### 24.2. Test pre-update

~~~java
@Test
void blank_customer_name_is_rejected_on_update() {
    PurchaseOrder order =
            em.find(PurchaseOrder.class, existingOrderId);

    order.changeCustomerName("   ");

    assertThrows(
        jakarta.validation.ConstraintViolationException.class,
        em::flush
    );
}
~~~

Test setup phải đảm bảo `existingOrderId` có dữ liệu và entity đang managed. Có thể cần transaction mới giữa fixture persist và update để cô lập các events. Nếu test trước đã làm persistence context rollback-only sau exception, không sử dụng lại cùng context cho assertion khác.

### 24.3. Test không tự validate với bulk update

~~~java
@Test
void bulk_update_bypasses_entity_validation() {
    int changed = em.createQuery(
            "update PurchaseOrder o " +
            "set o.customerEmail = :email " +
            "where o.id = :id"
        )
        .setParameter("email", "invalid")
        .setParameter("id", existingOrderId)
        .executeUpdate();

    assertEquals(1, changed);
}
~~~

Ví dụ giả định DB không có CHECK constraint cho định dạng email. Kết quả này không chứng minh DB cho phép mọi dữ liệu; một DB constraint khác vẫn có thể từ chối SQL. Mục tiêu test là cho thấy **bulk HQL không duyệt mỗi entity để chạy Jakarta Bean Validation callbacks**.

### 24.4. Test group custom

~~~java
@Test
void confirm_group_rejects_missing_confirmation_data() {
    PurchaseOrder order = validDraft();

    Set<ConstraintViolation<PurchaseOrder>> violations =
            validator.validate(order, OnConfirm.class);

    assertFalse(violations.isEmpty());
}
~~~

Test cần thêm trường bị ràng buộc bởi OnConfirm; không nên giả định Default có cùng kết quả.

### 24.5. Test Spring transaction rollback

Với một service annotated `@Transactional`, gọi từ test không mang transaction hoặc dùng transaction độc lập, gây failure rồi kiểm tra DB qua một EntityManager/transaction mới. Nếu test method cũng mặc định `@Transactional` và rollback cuối test, có thể che một bug service đã commit nhầm. Để xác minh commit/rollback, phải kiểm soát test transaction boundary rõ.

### 24.6. Các trường hợp cần thử

1. New entity invalid tại pre-persist.
2. Managed entity dirty invalid tại pre-update.
3. Không có UPDATE khi entity không dirty.
4. Cascaded child invalid qua `@Valid`.
5. Validation group OnCreate/OnUpdate đúng cấu hình.
6. Pre-remove không validate Default theo mặc định.
7. OnConfirm chỉ chạy tại transition có chủ đích.
8. Exception có tập `ConstraintViolation` và property paths đúng.
9. Transaction rollback, DB không còn row invalid.
10. Bulk/native write bypass entity validation.
11. Dữ liệu cũ sai format vẫn có thể load theo JPA.
12. DB constraints vẫn chặn uniqueness/FK invalid khi Bean Validation không đủ.
13. Lazy association không gây N+1 bất ngờ khi validation cascade.
14. Khi dùng @PrePersist để điền timestamp, state được validate đúng.
15. Namespace Jakarta Validation/provider tương thích trong CI/runtime.

## 25. Quy trình thiết kế validation cho một entity

Một cách tiếp cận thực dụng khi xây model Hibernate:

1. **Viết rõ invariant của entity.** Ví dụ customerName không rỗng, quantity dương, amount không âm.
2. **Đặt constraint ở đúng model layer.** Request DTO rules khác entity persistent invariants và transition-specific rules.
3. **Chọn các annotation sẵn có trước.** `@NotBlank`, `@NotNull`, `@Size`, `@Positive`, `@Digits`, `@Email`.
4. **Dùng custom constraint cho quan hệ nhiều fields**, tránh side effects và DB queries trong validators.
5. **Phân nhóm theo lifecycle thật.** Default cho invariants luôn đúng, custom groups cho create/update/confirm khi cần.
6. **Cấu hình pre-persist/pre-update/pre-remove rõ ràng**, không quên Default nếu custom groups được thêm.
7. **Dùng @Valid có chủ đích** để kiểm tra graph liên quan; phân biệt với JPA cascade.
8. **Kích hoạt provider/validation mode phù hợp**, có integration test để xác nhận auto-validation.
9. **Không dựa vào validation-on-update cho commands không dirty**, collection-only changes hoặc bulk SQL.
10. **Validate transition ở service boundary** nếu nghiệp vụ cần kiểm tra ngay, kể cả khi chưa flush.
11. **Giữ DB constraints cho các bất biến cần atomicity**, đặc biệt NOT NULL, UNIQUE, FK và CHECK khả thi.
12. **Để exception thoát khỏi transaction boundary** để rollback; không tiếp tục Session đã có ORM failure.
13. **Phân biệt Bean Validation và DB constraint exceptions** khi mapping sang HTTP/domain errors.
14. **Kiểm soát performance** của cascading validation và custom validators trong batch workloads.
15. **Kiểm tra với DBMS thực tế** và các lối ghi ngoài ORM, không chỉ test `validator.validate`.

## 26. Bài tập tự kiểm tra

### Bài 1 — Thời điểm validation

Một service gọi `em.persist(order)` rồi return, không gọi flush. Email invalid. Có thể kết luận exception phải được ném ngay tại `persist` không? Vì sao IDENTITY generator có thể làm thời điểm khác?

### Bài 2 — Pre-update

Một managed entity được gọi setter với giá trị bằng state hiện tại. Hibernate không phát UPDATE. Có thể dựa vào pre-update validation để kiểm tra command đó không?

### Bài 3 — Group mặc định

Constraint:

~~~java
@NotNull(groups = OnConfirm.class)
private Instant confirmedAt;
~~~

Vì sao pre-update validation mặc định có thể không kiểm tra constraint này? Làm thế nào validate khi transition DRAFT → CONFIRMED?

### Bài 4 — Nhóm lifecycle

Một persistence unit cần pre-persist kiểm tra Default và OnCreate; pre-update kiểm tra Default và OnUpdate; pre-remove không validate. Hãy viết các properties tương ứng và chỉ ra giá trị nào là mặc định.

### Bài 5 — @Valid khác cascade persist

Order chứa `List<OrderLine>`. Vì sao `cascade = CascadeType.PERSIST` không đồng nghĩa parent validation sẽ traverse tất cả child lines? Vì sao `@Valid` không tự làm child được INSERT?

### Bài 6 — Group conversion

Khi validate Order theo Default, cần validate Lines theo LineChecks. Annotation nào hỗ trợ chuyển nhóm tại association boundary, và cần annotation cascade nào đi kèm?

### Bài 7 — Checked vs runtime exception

`jakarta.validation.ConstraintViolationException` là checked hay runtime? Nếu nó thoát ra khỏi service `@Transactional` theo Spring default, transaction thường được xử lý thế nào?

### Bài 8 — Hai exception cùng tên

Giải thích khác nhau giữa:

~~~text
jakarta.validation.ConstraintViolationException
org.hibernate.exception.ConstraintViolationException
~~~

Trong Spring repository, lỗi DB có thể được translate thành exception nào?

### Bài 9 — Unique email

Hai requests đồng thời kiểm tra email chưa tồn tại bằng custom validator rồi cùng insert. Vì sao vẫn có thể xảy ra duplicate? Constraint nào phải có trong DB?

### Bài 10 — Bulk update

Vì sao lệnh `update PurchaseOrder o set o.customerEmail = :email` có thể lưu một email invalid dù entity field có `@Email`?

### Bài 11 — Cập nhật collection

Thêm một OrderLine invalid vào collection nhưng không đổi field của PurchaseOrder. Có chắc pre-update validation của parent chạy không? Hãy nêu một cách kiểm tra aggregate rõ hơn.

### Bài 12 — Spring MVC và JPA

Controller dùng `@Valid @RequestBody` nên request DTO invalid bị từ chối. Một batch job ghi entity qua EntityManager có tự đi qua Controller validation không? Cơ chế nào có thể bảo vệ ORM write?

### Bài 13 — Callback

Một `@PrePersist` callback gán `createdAt = Instant.now()` nếu null. Constraint `@NotNull` trên createdAt nhằm bảo đảm điều gì? Vì sao không nên thực hiện network I/O trong callback?

### Bài 14 — Transaction sau lỗi

Một flush ném `ConstraintViolationException`. Có nên bắt exception, sửa field rồi flush lại trong cùng Hibernate Session không? Hãy mô tả transaction boundary phù hợp.

### Bài 15 — Test coverage

Vì sao unit test chỉ gọi `validator.validate(order)` không chứng minh ORM thực sự bật lifecycle validation? Viết ý tưởng integration test chứng minh invalid order không được insert.

**Gợi ý:** (1) có thể xảy ra ở flush/commit hoặc sớm do IDENTITY; (2) không; (3) OnConfirm không thuộc Default; validate group tại transition; (4) cấu hình group pre-persist và pre-update, pre-remove mặc định rỗng; (5) JPA cascade và Bean Validation cascade riêng; (6) `@ConvertGroup` đi với `@Valid`; (7) runtime, rollback mặc định; (8) Java object validation so với DB integrity violation; (9) race condition, DB UNIQUE; (10) bulk update bypass per-entity validation; (11) không, validate aggregate tại service; (12) không, JPA lifecycle validation; (13) timestamp và side effects/flush phase; (14) rollback, context mới; (15) thử persist + flush với provider thật.

## 27. Tài liệu tham khảo

- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/): constraints, groups, cascaded validation, `Validator` và `ConstraintViolation`.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/): entity lifecycle events, automatic Bean Validation integration, validation modes và group properties.
- [Hibernate Validator Reference Guide](https://docs.jboss.org/hibernate/validator/8.0/reference/en-US/html_single/): built-in constraints, custom validators, group sequence, group conversion, JPA integration và metadata.
- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html): persistence context, lifecycle events, flushing, bulk update và constraint handling.
- [Spring Framework Reference — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): Bean Validation integration trong Spring.
- [Spring Framework Reference — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, rollback rules và transaction boundaries.
- [Spring Boot Reference — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html): auto-configuration của Bean Validation provider và method validation.

**Kết luận:** Jakarta Bean Validation giúp khai báo và kiểm tra các quy tắc trên Java entities; Hibernate ORM có thể tự kích hoạt các constraints theo **pre-persist** và **pre-update** events (mặc định nhóm `Default`), còn **pre-remove** mặc định không kiểm tra nhóm nào. Validation thường gắn với **flush/persistence action**, không phải setter hay lời gọi `persist()` theo một thời điểm cố định. Khi quy tắc thay đổi theo trạng thái nghiệp vụ, hãy chọn groups và service-level validation có chủ đích, dùng `@Valid` để cascade việc kiểm tra object graph và nhớ nó khác `CascadeType.PERSIST`. Dữ liệu vẫn cần DB constraints và transaction handling an toàn vì bulk/native SQL, external writers hoặc cập nhật đồng thời có thể bỏ qua entity validation. Khi Bean Validation thất bại ở flush, rollback transaction và không tiếp tục sử dụng Hibernate Session đã lỗi; hãy báo rõ các vi phạm cho caller và thực hiện lại trong unit of work mới sau khi dữ liệu được sửa.

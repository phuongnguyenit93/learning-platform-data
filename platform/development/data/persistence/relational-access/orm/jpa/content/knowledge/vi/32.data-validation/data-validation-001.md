# Phân biệt kiểm tra đối tượng, quy tắc nghiệp vụ và ràng buộc cơ sở dữ liệu

Trong một ứng dụng Java dùng JPA, yêu cầu “dữ liệu phải hợp lệ” thường được hiện thực bằng nhiều cơ chế khác nhau. Một trường `sku` không được bỏ trống, một sản phẩm chỉ được công bố khi đã được phê duyệt, và database không được tồn tại hai sản phẩm có cùng mã trong một cửa hàng là **ba yêu cầu khác bản chất**, dù đều có thể bị gọi chung là *validation*.

Hãy xem ba câu hỏi:

1. **Kiểm tra đối tượng (object validation):** giá trị đang nằm trong Java object hoặc request DTO có đúng định dạng, kiểu và điều kiện cục bộ hay không?
2. **Quy tắc nghiệp vụ (business rule / domain invariant):** thao tác đang được yêu cầu có hợp lệ trong trạng thái và bối cảnh nghiệp vụ hiện tại hay không?
3. **Ràng buộc cơ sở dữ liệu (database constraint):** những trạng thái nào tuyệt đối không được phép tồn tại trong các hàng hoặc quan hệ được database lưu bền vững?

Ví dụ:

```java
public record CreateProductRequest(
    @NotBlank String sku,
    @NotBlank String name,
    @NotNull @DecimalMin("0.00") BigDecimal price
) {}
```

Đoạn mã trên kiểm tra dữ liệu đầu vào về hình dạng và giá trị đơn giản. Nhưng nó **không chứng minh** rằng mã `sku` chưa bị người khác sử dụng trong một request khác, và **không chứng minh** tài khoản gọi API có quyền tạo sản phẩm ở cửa hàng này.

Một service nghiệp vụ có thể kiểm tra quyền, xác định trạng thái hợp lệ và tạo entity. Tuy nhiên, kể cả service đã truy vấn `existsBySku(...)` để bảo đảm mã chưa tồn tại, **hai transaction chạy đồng thời vẫn có thể cùng thấy “chưa tồn tại”**. Database vẫn cần một ràng buộc `UNIQUE` thật sự để chặn trùng mã khi cả hai cùng INSERT.

Đây là ý nghĩa cốt lõi của bài **“Phân biệt kiểm tra đối tượng, quy tắc nghiệp vụ và ràng buộc cơ sở dữ liệu”**, thuộc chương **Kiểm tra dữ liệu** trong chủ đề **Data Persistence Relational Access ORM JPA**: mỗi lớp có trách nhiệm, thời điểm chạy, khả năng quan sát và giới hạn riêng. Hệ thống đúng không chọn một trong ba, mà **phối hợp chúng để lỗi được phát hiện sớm, nghiệp vụ rõ ràng và database không thể lưu trạng thái cấm**.

Các ví dụ dùng Java 17+, Jakarta Persistence (`jakarta.persistence`) và Jakarta Bean Validation (`jakarta.validation`). Một số ví dụ dùng Spring Data JPA hoặc Spring MVC sẽ được ghi rõ. Cú pháp DDL mang tính minh họa; SQL dialect, cơ chế phát exception và thời điểm flush/commit phải được kiểm chứng theo database/JPA provider thực tế.

---

## 1. Bức tranh tổng thể: ba lớp, ba loại câu hỏi

Giả sử API tạo sản phẩm:

```text
HTTP POST /shops/7/products
       │
       ▼
Request DTO
  - sku phải có ký tự
  - name không được trống
  - price không âm
       │
       ▼
Application / domain service
  - người gọi có quyền tạo sản phẩm cho shop #7?
  - shop đã hoạt động và được phép bán hàng?
  - sản phẩm mới bắt đầu ở trạng thái DRAFT?
  - có đang vi phạm chính sách danh mục?
       │
       ▼
JPA EntityManager / transaction
  - persist(Product)
  - flush / commit
       │
       ▼
Database constraints
  - PRIMARY KEY(id)
  - NOT NULL(sku, name, price, shop_id)
  - CHECK(price >= 0)
  - UNIQUE(shop_id, normalized_sku)
  - FOREIGN KEY(shop_id) REFERENCES shops(id)
       │
       ▼
Dữ liệu được commit hoặc transaction thất bại
```

Một request có thể bị từ chối ở bất cứ lớp nào. Việc từ chối sớm rất hữu ích cho trải nghiệm người dùng và giảm tải, nhưng **không được nhầm với bảo đảm bất biến cuối cùng ở database**.

### Bảng phân biệt nhanh

| Khía cạnh | Kiểm tra đối tượng | Quy tắc nghiệp vụ | Ràng buộc database |
| --- | --- | --- | --- |
| Câu hỏi chính | “Giá trị này hợp lệ không?” | “Thao tác này được phép trong bối cảnh hiện tại không?” | “Trạng thái dữ liệu này có được lưu bền vững không?” |
| Dữ liệu thường cần | Field của một DTO/entity, đôi khi nhiều field cùng object | Entity/aggregate, trạng thái, quyền, thời điểm, các dữ liệu liên quan | Rows, columns, keys, relationships, transactions |
| Công cụ điển hình | Jakarta Bean Validation, type checks, parsing | Domain methods, services, policies, authorization, locking | NOT NULL, CHECK, UNIQUE, FK, PK, triggers, constraints |
| Khi chạy | API boundary, gọi Validator, lifecycle validation | Khi thực hiện use case/command trong transaction | Khi DB thực thi SQL, hoặc khi commit với constraint được trì hoãn |
| Có thể kiểm tra format? | Rất phù hợp | Có thể nhưng không nên lặp vô ích | Chỉ phần diễn đạt được bằng SQL constraints |
| Có thể kiểm tra quyền người dùng? | Không đủ ngữ cảnh | Có, tại authorization/application layer | Không thay thế authorization |
| Chống race condition khi hai transaction cùng INSERT? | Không | Không chỉ bằng `exists(...)` | UNIQUE thật có thể bảo vệ |
| Áp dụng cho JDBC/native writers? | Không tự động | Không nếu writer bypass service | Có, nếu constraints ở DB vẫn bật |
| Trải nghiệm lỗi | Có thể trả lỗi theo field | Có thể trả lỗi nghiệp vụ theo action | Cần dịch lỗi DB thành thông báo an toàn |
| Bảo vệ dữ liệu khi ứng dụng khác ghi DB | Không | Không nếu ứng dụng kia bypass policy | Có với bất biến được DB enforce |

Một nguyên tắc hữu ích: **kiểm tra đối tượng và nghiệp vụ càng sớm càng tốt, nhưng các bất biến có thể diễn đạt bằng database constraints phải được bảo vệ ở chính database**.

## 2. Không có một lớp nào thay thế hoàn toàn hai lớp còn lại

Chỉ dùng Bean Validation:

```java
@NotBlank
private String sku;
```

không chặn được hai transaction cùng tạo mã giống nhau nếu mã đều không trống.

Chỉ dùng nghiệp vụ:

```java
if (!repository.existsByShopIdAndSku(shopId, sku)) {
    repository.save(product);
}
```

không chặn được race giữa lúc kiểm tra và lúc INSERT nếu thiếu unique constraint.

Chỉ dùng database:

```sql
CONSTRAINT ck_price_nonnegative CHECK (price >= 0)
```

có thể chặn giá âm, nhưng người dùng chỉ biết “constraint violated” sau khi gửi request, thiếu thông báo lỗi thân thiện và không có logic “chỉ quản trị viên mới được đổi giá”.

Vì vậy kết hợp đúng là:

```text
Validation giúp phát hiện lỗi đơn giản sớm
          +
Domain/service giữ nghiệp vụ và quyền
          +
Database constraints giữ trạng thái lưu trữ an toàn
          +
Transaction / locking bảo vệ tính đúng dưới concurrency
```

Không nên suy rằng đặt annotation trên entity sẽ tự biến những tầng này thành một.

---

## 3. Ví dụ xuyên suốt: Product theo từng cửa hàng

Giả sử hệ thống quản lý nhiều cửa hàng. Một sản phẩm có:

- `id`: định danh.
- `shopId`: cửa hàng sở hữu.
- `sku`: mã sản phẩm do shop quản lý.
- `name`: tên hiển thị.
- `price`: giá bán không âm.
- `status`: `DRAFT`, `APPROVED` hoặc `PUBLISHED`.
- `version`: bảo vệ optimistic locking.
- `approvedAt`: thời điểm phê duyệt nếu có.

Yêu cầu nghiệp vụ:

1. Mã SKU không trống và được chuẩn hóa.
2. Giá không âm.
3. Một shop không có hai Product cùng normalized SKU.
4. Chỉ Product đã phê duyệt mới có thể published.
5. User phải được phép chỉnh Product của shop tương ứng.
6. Update từ bản cũ không được âm thầm ghi đè update mới nếu có version conflict.

Một phần có thể kiểm tra trên object, một phần cần domain policy, và một phần phải có DB constraint/transaction support.

### Mô hình bảng

```sql
CREATE TABLE shops (
    id BIGINT PRIMARY KEY,
    active BOOLEAN NOT NULL
);

CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    shop_id BIGINT NOT NULL,
    sku VARCHAR(80) NOT NULL,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(14, 2) NOT NULL,
    status VARCHAR(30) NOT NULL,
    approved_at TIMESTAMP NULL,
    version BIGINT NOT NULL,

    CONSTRAINT fk_product_shop
        FOREIGN KEY (shop_id) REFERENCES shops(id),

    CONSTRAINT uq_product_shop_sku
        UNIQUE (shop_id, sku),

    CONSTRAINT ck_product_price
        CHECK (price >= 0),

    CONSTRAINT ck_product_status
        CHECK (status IN ('DRAFT', 'APPROVED', 'PUBLISHED')),

    CONSTRAINT ck_product_published_approved
        CHECK (
            status <> 'PUBLISHED'
            OR approved_at IS NOT NULL
        )
);
```

SQL trên mô tả **ý tưởng ràng buộc**, không phải migration hoàn chỉnh chạy nguyên văn trên mọi database. Cú pháp boolean, identity generation, check constraints và Unicode/collation tùy dialect.

Một số bất biến có thể được mã hóa ở database (`price >= 0`, unique SKU), nhưng việc **ai có quyền publish**, liệu phê duyệt còn hiệu lực hay không hoặc có cần tuân thủ quy trình nội bộ không vẫn là luật ứng dụng.

## 4. Lớp một: kiểm tra object và request DTO

**Object validation** hỏi một instance có thỏa điều kiện trên fields/structure hay không.

Ví dụ DTO:

```java
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;

public record CreateProductRequest(
    @NotBlank
    @Size(max = 80)
    String sku,

    @NotBlank
    @Size(max = 200)
    String name,

    @NotNull
    @DecimalMin("0.00")
    BigDecimal price
) {}
```

Những annotation này cung cấp các câu trả lời cục bộ:

- SKU có blank không?
- SKU vượt giới hạn chiều dài không?
- Name có chữ không?
- Price có null hoặc âm không?

Điều chúng **chưa nói**:

- SKU có duy nhất trong shop?
- User có quyền tạo cho shop?
- Shop có đang hoạt động?
- Loại sản phẩm có cần phê duyệt đặc biệt?
- Bản ghi khác có bị cập nhật đồng thời không?

Đó là ranh giới giữa validation hình dạng và business/database correctness.

## 5. Bean Validation và JPA là hai specification riêng

JPA định nghĩa ánh xạ entity và persistence lifecycle. Jakarta Bean Validation định nghĩa constraints và việc validate Java objects.

Ví dụ:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.validation.constraints.NotBlank;

@Entity
public class Category {

    @Id
    private Long id;

    @NotBlank
    private String name;
}
```

`@Entity` đến từ Jakarta Persistence; `@NotBlank` đến từ Jakarta Validation.

Nếu runtime có Bean Validation provider và JPA validation integration được cấu hình phù hợp, validation có thể chạy tự động tại lifecycle persistence operations. Nhưng **không nên coi mọi `@NotBlank` đều chắc chắn được kiểm tra khi bất cứ Java code nào sửa entity field**.

Object validation có thể được gọi tường minh:

```java
Validator validator =
    Validation.buildDefaultValidatorFactory()
        .getValidator();

Set<ConstraintViolation<CreateProductRequest>> violations =
    validator.validate(request);
```

Trong ứng dụng production, nên quản lý `ValidatorFactory` như tài nguyên dùng chung được container/framework cấu hình và đóng khi lifecycle kết thúc, không build factory mới cho từng HTTP request.

### Cần Bean Validation provider thực sự

Có dependency `jakarta.validation-api` cho annotation/API **chưa đủ** nếu không có implementation phù hợp ở runtime. Ví dụ một ứng dụng có thể dùng Hibernate Validator, nhưng nó là **Bean Validation provider**, không đồng nhất với Hibernate ORM JPA provider.

## 6. Những annotation kiểm tra object thường gặp

| Constraint | Ý nghĩa cơ bản | Giới hạn cần nhớ |
| --- | --- | --- |
| `@NotNull` | Reference không được null | Không cấm empty string |
| `@NotBlank` | CharSequence không null và có ký tự không phải whitespace | Không kiểm tra tính duy nhất |
| `@NotEmpty` | Chuỗi/collection/map/array không rỗng | Không đồng nghĩa “không có toàn dấu cách” |
| `@Size(min,max)` | Kiểm tra kích thước chuỗi/collection/mảng | Không tự thay DB column length |
| `@Min`/`@Max` | Giới hạn số | Cần đúng kiểu áp dụng |
| `@DecimalMin`/`@DecimalMax` | So sánh decimal theo giới hạn | Không thay DB CHECK |
| `@Positive`/`@PositiveOrZero` | Dương/không âm | Null thường cần `@NotNull` riêng |
| `@Digits(integer,fraction)` | Giới hạn số chữ số | DB precision/scale vẫn phải khớp |
| `@Pattern` | Khớp regex | Không tự canonicalize dữ liệu |
| `@Email` | Kiểm tra cấu trúc email theo constraint provider | Không xác minh email tồn tại/duy nhất |
| `@Past`/`@Future` | Quan hệ với thời điểm hiện tại | Cần clock/timezone policy phù hợp |
| `@Valid` | Cascaded object validation | Không tương đương JPA cascade persist/remove |
| `@AssertTrue` | Một điều kiện boolean được yêu cầu true | Phù hợp invariant đơn giản, không tự quản lý transaction |

Không phải annotation nào cũng hợp lệ trên mọi kiểu. Ví dụ `@NotBlank` không được đặt trên `BigDecimal`; `@Size` không phải cách đo kích thước một kiểu số.

### Null semantics

Nhiều constraints như `@Size`, `@PositiveOrZero` coi null là hợp lệ và để `@NotNull` xử lý sự hiện diện. Vì vậy:

```java
@PositiveOrZero
private BigDecimal price;
```

không được xem là tương đương:

```java
@NotNull
@PositiveOrZero
private BigDecimal price;
```

Khi dữ liệu không được phép thiếu, cần kết hợp constraints phù hợp.

## 7. Request validation cần được kích hoạt tại boundary

Trong Spring MVC, ví dụ:

```java
@PostMapping("/shops/{shopId}/products")
public ResponseEntity<ProductView> create(
        @PathVariable Long shopId,
        @Valid @RequestBody CreateProductRequest request) {

    ProductView created =
        productService.create(shopId, request);

    return ResponseEntity.status(HttpStatus.CREATED)
        .body(created);
}
```

`@Valid` giúp Spring kích hoạt Bean Validation trên request body khi framework được cấu hình đúng. Trong JAX-RS/Jakarta REST hoặc một CLI worker, cơ chế kích hoạt có thể khác.

Quan trọng:

- Validation ở controller giúp báo lỗi sớm.
- Service vẫn phải kiểm tra quyền và nghiệp vụ.
- Database vẫn phải có constraints.
- Không nên tin rằng mọi người ghi data đều đi qua endpoint này.
- Một event consumer, scheduled job hoặc admin tool có thể gọi service trực tiếp.

Nếu nghiệp vụ cần chắc rằng service bảo vệ invariant dù không qua HTTP, hãy thiết kế service/domain validation rõ, không chỉ trông chờ `@Valid` ở controller.

## 8. Bean Validation có thể kiểm tra nhiều field trong một object

Ví dụ yêu cầu khoảng giảm giá:

```java
public record DiscountRequest(
    @NotNull BigDecimal originalPrice,
    @NotNull BigDecimal discountedPrice
) {}
```

Một rule là `discountedPrice <= originalPrice`. Rule này cần nhìn **hai fields cùng một object**. Có thể dùng:

- Class-level custom Bean Validation constraint.
- `@AssertTrue` trên method boolean phù hợp.
- Domain value object có constructor kiểm tra.
- Application service validation nếu ngữ nghĩa phụ thuộc bối cảnh.

Ví dụ đơn giản:

```java
public record DiscountRequest(
    @NotNull BigDecimal originalPrice,
    @NotNull BigDecimal discountedPrice
) {

    @AssertTrue(message = "Discounted price exceeds original")
    public boolean isDiscountValid() {
        return originalPrice == null
            || discountedPrice == null
            || discountedPrice.compareTo(originalPrice) <= 0;
    }
}
```

Ở đây việc chấp nhận null tạm thời trong predicate cho phép `@NotNull` báo lỗi riêng, thay vì ném NullPointerException khi validator chạy các constraints theo thứ tự không xác định.

**Cross-field object validation vẫn không tự giải quyết race/cross-row invariants trong database.**

## 9. Custom constraint dùng khi nào?

Nếu nhiều DTO cần một mã SKU theo format:

```text
SKU = chữ in hoa, chữ số, dấu gạch ngang
Độ dài từ 4 đến 40 ký tự
```

Có thể dùng `@Pattern`:

```java
@Pattern(regexp = "[A-Z0-9-]{4,40}")
String sku
```

Nếu rule phức tạp và được tái sử dụng, định nghĩa custom annotation + `ConstraintValidator`. Nhưng:

- Custom validator không phải nơi mặc định gọi repository để kiểm tra unique SKU.
- Một query uniqueness trong validator vẫn có race.
- Validator phải ổn định, không phụ thuộc mutable global state.
- Nếu rule là domain state transition, domain method thường biểu đạt tốt hơn.
- Nếu rule thay đổi theo tenant/config, service/policy object có thể phù hợp hơn annotation tĩnh.

**Custom constraint hữu ích cho object-shape rules tái sử dụng, không phải cái cớ chuyển mọi nghiệp vụ vào reflection/validation annotations.**

## 10. Validation groups: cùng object có nhiều ngữ cảnh

Trong Jakarta Bean Validation, có thể nhóm constraints:

```java
public interface OnCreate {}
public interface OnUpdate {}
```

Ví dụ:

```java
public class ProductForm {

    @NotBlank(groups = OnCreate.class)
    private String sku;

    @NotNull(groups = {OnCreate.class, OnUpdate.class})
    @PositiveOrZero(groups = {OnCreate.class, OnUpdate.class})
    private BigDecimal price;
}
```

Gọi:

```java
validator.validate(form, OnCreate.class);

validator.validate(form, OnUpdate.class);
```

Cần chú ý:

- Constraints không khai báo groups thuộc group `Default`.
- Khi gọi một group tường minh, không mặc nhiên validate tất cả constraints của `Default`, trừ khi group sequence/inheritance được cấu hình tương ứng.
- Validation groups giúp chia validation scenarios, nhưng không tự định nghĩa quyền cập nhật field.
- Đừng dùng một entity/DTO khổng lồ với quá nhiều groups thay cho command DTO chuyên biệt khi API có nhiều operations khác nhau.

Ví dụ `CreateProductCommand` và `ChangePriceCommand` riêng thường dễ hiểu và an toàn hơn một `ProductDto` vừa dùng create/update/publish.

## 11. Cascaded `@Valid` khác cascade JPA

Một request lồng:

```java
public record AddressRequest(
    @NotBlank String street,
    @NotBlank String city
) {}

public record CustomerRequest(
    @NotBlank String name,
    @Valid @NotNull AddressRequest address
) {}
```

`@Valid` yêu cầu validate object `address` khi validate `CustomerRequest`.

Trong JPA:

```java
@OneToMany(cascade = CascadeType.PERSIST)
private List<OrderLine> lines;
```

`CascadeType.PERSIST` là **quy tắc propagate persistence operation**, không phải annotation Bean Validation.

Không nhầm:

- `@Valid`: cascade validation sang nested object khi được yêu cầu.
- `CascadeType.PERSIST`: cascade JPA persist sang related entities.
- `orphanRemoval`: xử lý orphan entity lifecycle.
- `@EntityListeners`: callbacks quanh JPA lifecycle.

Các cơ chế có thể phối hợp nhưng không hoán đổi. `@Valid` trên request không tự lưu Address, còn `CascadeType.PERSIST` không tự bảo đảm child thỏa mọi Bean Validation constraints nếu validation không được kích hoạt/cấu hình phù hợp.

## 12. Validation tại JPA lifecycle: pre-persist, pre-update

Khi có Bean Validation integration, JPA có thể kích hoạt validation đối với entity trước một số lifecycle operations, chẳng hạn persist/update.

Ví dụ:

```java
@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue
    private Long id;

    @NotBlank
    @Column(nullable = false)
    private String name;

    @NotNull
    @PositiveOrZero
    @Column(nullable = false)
    private BigDecimal price;
}
```

Ứng dụng:

```java
em.getTransaction().begin();

Product product = new Product(...);

em.persist(product);

em.flush(); // Có thể phát hiện Bean Validation failure tại đây.

em.getTransaction().commit();
```

Không nên mặc định constraint sẽ ném exception ngay khi gọi:

```java
product.setPrice(new BigDecimal("-1"));
```

Setter thông thường không tự gọi Validator. Validation có thể chạy tại framework boundary, trong code gọi validator tường minh hoặc trong JPA lifecycle validation khi enabled.

**Thời điểm ném lỗi có thể ở persist, flush hoặc commit tùy action/provider**, nên transaction error handling phải bao trùm ranh giới commit, không chỉ setter.

## 13. `validation-mode` trong persistence unit

Jakarta Persistence cho phép cấu hình Bean Validation integration, ví dụ:

```xml
<persistence-unit name="shopPU">
    <validation-mode>AUTO</validation-mode>
</persistence-unit>
```

Các mode:

| ValidationMode | Ý định |
| --- | --- |
| `AUTO` | Dùng tích hợp validation khi provider hiện diện theo specification |
| `CALLBACK` | Yêu cầu lifecycle validation callback integration |
| `NONE` | Không thực hiện automatic lifecycle Bean Validation theo chế độ này |

Điểm cần hiểu:

- `NONE` **không có nghĩa** `Validator.validate(...)` tường minh bị cấm.
- `CALLBACK` yêu cầu Bean Validation provider phù hợp; nếu không có implementation/runtime requirements, việc bootstrap có thể thất bại.
- `AUTO` phụ thuộc khả năng tìm thấy provider và ngữ cảnh integration.
- Application server/Spring có thể bổ sung cấu hình riêng.
- JPA validation mode **không làm database bỏ NOT NULL/UNIQUE/CHECK/FK**.

Nếu một test validation ở controller xanh nhưng persist entity trực tiếp qua batch vẫn lưu được giá trị không hợp lệ, cần xem có Bean Validation integration ở JPA hay không và DB schema có constraints thực sự không.

## 14. Các group lifecycle JPA

JPA có các cấu hình chuẩn cho validation groups tại lifecycle operations, ví dụ:

```properties
jakarta.persistence.validation.group.pre-persist
jakarta.persistence.validation.group.pre-update
jakarta.persistence.validation.group.pre-remove
```

Có thể cấu hình groups tương ứng để điều khiển những constraints nào được validate tự động trong JPA lifecycle, theo version/provider/runtime.

Ý nghĩa khái quát:

- Pre-persist: xác minh entity trước khi INSERT lifecycle.
- Pre-update: xác minh entity khi JPA chuẩn bị UPDATE.
- Pre-remove: có thể cấu hình group phù hợp khi remove; mặc định không nên mặc nhiên suy mọi constraints tạo/ghi đều được validate trước DELETE.
- Không phải callback Java `@PrePersist` tự tương đương toàn bộ Bean Validation integration.

**Đừng nhầm tên JPA validation lifecycle hooks với validation groups trên HTTP DTO.** Chúng có cùng Bean Validation API nền tảng nhưng thời điểm, đối tượng và config khác nhau.

## 15. Tại sao không đặt mọi constraint vào entity?

Một entity được dùng ở nhiều use cases:

- Tạo Product.
- Sửa tên Product.
- Đổi giá.
- Phê duyệt.
- Publish.
- Xóa hoặc ngừng bán.

Một trường có thể bắt buộc trong command này nhưng không có ý nghĩa trong command khác. Nếu ép tất cả rules vào annotation entity, rất dễ:

- Bắt buộc field không liên quan đến operation.
- Phải dùng phức tạp validation groups.
- Không biểu đạt được transition giữa states.
- Cố nhét repository/transaction vào custom validator.
- Gây validation muộn chỉ khi flush.
- Nhầm HTTP input shape với database persistence shape.

Hướng thực dụng:

1. Request DTO constraints kiểm tra input của từng operation.
2. Domain methods kiểm tra invariants của Product/aggregate.
3. Service kiểm tra quyền và state liên quan từ DB.
4. Entity-level constraints bảo vệ những properties cục bộ có ý nghĩa cho managed lifecycle.
5. Database constraints giữ trạng thái lưu trữ an toàn.

Không nhất thiết lặp y hệt mọi annotation ở cả DTO và entity; các checks được đặt theo trách nhiệm, nhưng bất biến DB quan trọng vẫn phải có lớp cuối.

---

## 16. Lớp hai: quy tắc nghiệp vụ là gì?

Một **business rule** nói về ý nghĩa nghiệp vụ, không chỉ hình dạng của dữ liệu.

Ví dụ:

- Chỉ tài khoản có vai trò quản trị của shop mới tạo Product cho shop đó.
- Shop đang bị khóa không được publish Product.
- Product phải được phê duyệt trước khi publish.
- Chỉ được hoàn tiền khi Payment đã settled.
- Không cho hủy Order khi hàng đã giao.
- Giá giảm không được vượt ngưỡng do policy theo từng loại khách hàng.
- Một người không được đặt vé chồng thời gian.
- Tổng hạn mức tín dụng của một khách hàng không được vượt quá chính sách được áp dụng.

Một số business rules vẫn có thể diễn đạt thành predicate trên một entity, nhưng **vị trí phù hợp để áp dụng chúng thường là domain model hoặc application service**, nơi biết operation và context.

### Ví dụ state transition

```text
DRAFT ──approve──► APPROVED ──publish──► PUBLISHED
   ▲                    │                    │
   └──request changes───┘                    └──unpublish──► DRAFT
```

Không phải mọi chuyển trạng thái đều được phép. Chỉ kiểm tra `status IN (...)` ở DB sẽ không bảo đảm transition hợp lệ: nó chỉ bảo đảm giá trị thuộc tập đã định.

## 17. Đặt invariant vào domain method

Một entity Product minh họa:

```java
import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false)
    private Long shopId;

    @Column(nullable = false, length = 80)
    private String sku;

    @Column(nullable = false, length = 200)
    private String name;

    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal price;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 30)
    private ProductStatus status;

    private Instant approvedAt;

    protected Product() {}

    public Product(
            Long shopId,
            String sku,
            String name,
            BigDecimal price) {

        this.shopId = Objects.requireNonNull(shopId);
        this.sku = ProductSku.normalize(sku);
        this.name = requireName(name);
        setPrice(price);
        this.status = ProductStatus.DRAFT;
    }

    public void setPrice(BigDecimal value) {
        Objects.requireNonNull(value);
        if (value.signum() < 0) {
            throw new IllegalArgumentException(
                "Price must be nonnegative"
            );
        }
        this.price = value;
    }

    public void approve(Instant approvedAt) {
        if (status != ProductStatus.DRAFT) {
            throw new IllegalStateException(
                "Only draft products can be approved"
            );
        }
        this.approvedAt =
            Objects.requireNonNull(approvedAt);
        status = ProductStatus.APPROVED;
    }

    public void publish() {
        if (status != ProductStatus.APPROVED
                || approvedAt == null) {
            throw new IllegalStateException(
                "Product must be approved first"
            );
        }
        status = ProductStatus.PUBLISHED;
    }

    public Long getId() { return id; }
    public Long getShopId() { return shopId; }
    public String getSku() { return sku; }
    public ProductStatus getStatus() { return status; }

    private static String requireName(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Name is required");
        }
        return value.trim();
    }
}
```

Enum:

```java
public enum ProductStatus {
    DRAFT,
    APPROVED,
    PUBLISHED
}
```

`ProductSku.normalize(...)` là value-object/helper sẽ minh họa ở phần sau.

### Những gì domain method kiểm soát

- Không thể gọi `publish()` khi status còn DRAFT.
- Không thể set giá âm qua method.
- Một Product mới bắt đầu DRAFT theo factory/constructor.
- Việc phê duyệt có ý nghĩa riêng và cần thời điểm.

Nhưng JPA có thể hydrate entity từ database bằng constructor không tham số và field access; **đừng giả định mọi dữ liệu đi vào entity đều bắt buộc đi qua public business constructor hoặc setters**. Đó là một lý do cần database constraints và entity-level validation thích hợp.

## 18. Quy tắc nghiệp vụ có thể phụ thuộc nhiều entities

Xét quy tắc:

> “Chỉ publish Product nếu Shop đang active và người gọi có quyền quản trị Shop.”

Product object đơn lẻ không tự có đủ thông tin. Một application service có thể:

```java
@Transactional
public ProductView publish(
        Long shopId,
        Long productId,
        UserPrincipal actor) {

    permissionService.requireShopAdmin(actor, shopId);

    Shop shop = shopRepository.findById(shopId)
        .orElseThrow(ShopNotFoundException::new);

    if (!shop.isActive()) {
        throw new BusinessRuleViolation(
            "Shop is not active"
        );
    }

    Product product = productRepository
        .findByIdAndShopId(productId, shopId)
        .orElseThrow(ProductNotFoundException::new);

    product.publish();

    return toView(product);
}
```

Đây là Spring-style pseudocode: repository types, `UserPrincipal`, exceptions, `ProductView` và `permissionService` là các abstraction của ứng dụng. `@Transactional` đến từ Spring nếu dùng Spring transaction manager.

Điểm chính:

- Quyền được kiểm tra theo actor và shop.
- Shop hiện đang hoạt động hay không là một điều kiện từ entity khác.
- Product transition được kiểm tra trong domain method.
- Những thay đổi được ghi trong transaction.
- Nếu shop status có thể thay đổi đồng thời, cần cân nhắc concurrency policy để bảo đảm điều kiện đang được bảo vệ.

Không nên đưa `shopRepository.findById(...)` vào một `@AssertTrue` trong Product chỉ vì muốn gộp mọi rule vào Bean Validation.

## 19. Domain invariant và database CHECK có thể bổ sung nhau

Quy tắc:

> “Product ở trạng thái PUBLISHED phải có approvedAt.”

Ở domain:

```java
public void publish() {
    if (status != ProductStatus.APPROVED
            || approvedAt == null) {
        throw new IllegalStateException("Not approved");
    }

    status = ProductStatus.PUBLISHED;
}
```

Ở DB:

```sql
CONSTRAINT ck_product_published_approved
CHECK (
    status <> 'PUBLISHED'
    OR approved_at IS NOT NULL
)
```

Hai lớp có giá trị khác nhau:

- Domain method bảo đảm transition theo ngữ nghĩa, báo lỗi dễ hiểu.
- DB CHECK ngăn writer bỏ qua domain method lưu một Product PUBLISHED mà approvedAt null.

Nhưng DB CHECK ở trên **không thể bảo đảm** lịch sử transition “phải đi từ DRAFT sang APPROVED rồi PUBLISHED” nếu writer trực tiếp set status=PUBLISHED và approvedAt khác null. Để bảo vệ điều kiện có lịch sử hoặc nhiều giao dịch, cần thiết kế thêm service workflow, append-only audit, trigger/transition table hoặc concurrency policy tùy yêu cầu.

**Ràng buộc dữ liệu trạng thái** và **quy tắc chuyển trạng thái** không phải cùng một loại điều kiện.

## 20. Quyền truy cập không phải object validation

Ví dụ request:

```json
{
  "sku": "ABC-123",
  "name": "Bàn phím",
  "price": 150000
}
```

Object có thể hợp lệ hoàn toàn. Nhưng người gọi không phải admin của shop. Kết quả phải là **authorization failure**, không phải “SKU không hợp lệ”.

Không nên dùng:

```java
@AssertTrue
boolean isAuthorized() {
    return CurrentUserContext...;
}
```

trên entity để quyết định phân quyền, vì:

- Entity không nên phụ thuộc HTTP thread/security principal.
- Có nhiều entrypoints khác HTTP: CLI, batch, event consumer.
- JPA callbacks có thể chạy khi flush, không phải nơi authorization decision được gọi.
- Quyền có thể thay đổi khi request chạy.
- Một DB trigger không tự thay thế user-level authorization nếu không có đầy đủ trusted context.

Đặt authorization trong application service/security boundary và dùng **tenant-scoped query** khi tải entity để tránh thao tác nhầm đối tượng thuộc shop khác.

## 21. Domain logic có thể cần dữ liệu đồng thời nhất quán

Ví dụ tồn kho:

```java
if (inventory.getAvailableQuantity() >= requested) {
    inventory.reserve(requested);
}
```

Rule “không được bán quá số lượng có sẵn” không chỉ kiểm tra field nonnegative của request. Nó phụ thuộc **trạng thái hiện tại** của InventoryItem và các transactions cạnh tranh.

Một cách dùng optimistic locking:

```java
@Entity
public class InventoryItem {

    @Id
    private Long id;

    @Version
    private Long version;

    private int availableQuantity;

    public void reserve(int requested) {
        if (requested <= 0) {
            throw new IllegalArgumentException();
        }
        if (availableQuantity < requested) {
            throw new InsufficientStockException();
        }
        availableQuantity -= requested;
    }
}
```

Nếu hai transactions tải version giống nhau rồi cùng update, JPA có thể phát hiện conflict khi flush/commit bằng `@Version`.

Một cách dùng pessimistic lock:

```java
InventoryItem item = em.find(
    InventoryItem.class,
    id,
    LockModeType.PESSIMISTIC_WRITE
);

item.reserve(requested);
```

Một cách dùng atomic SQL:

```sql
UPDATE inventory_items
SET available_quantity = available_quantity - :requested
WHERE id = :id
  AND available_quantity >= :requested;
```

Sau SQL có điều kiện phải kiểm tra row count đúng kỳ vọng. **Chỉ đọc số tồn rồi kiểm tra trong service không đủ chặn race**.

## 22. Vì sao `existsBy...` không phải UNIQUE constraint?

Giả sử Shop #7 chưa có SKU `ABC-123`.

```text
Transaction A                            Transaction B
      │                                         │
SELECT EXISTS(sku='ABC-123') → false           │
      │                                SELECT EXISTS(...) → false
      │                                         │
INSERT SKU='ABC-123'                           │
      │                                 INSERT SKU='ABC-123'
      │                                         │
COMMIT                                      COMMIT
```

Nếu database không có unique constraint, cả hai INSERT có thể được chấp nhận, tùy transaction/isolation và cách thực thi.

**`existsByShopIdAndSku` chỉ là một kiểm tra tiện lợi về trạng thái đã thấy**, không bảo vệ khoảng thời gian sau SELECT.

Nếu có:

```sql
UNIQUE (shop_id, sku)
```

database phải từ chối một trong hai kết quả trùng khi uniqueness được enforce, kể cả khi hai request đều đã pass object validation và business pre-check.

### Có nên vẫn pre-check unique?

Có thể, để trả lỗi dễ hiểu sớm trong phần lớn requests:

```java
if (repository.existsByShopIdAndSku(shopId, normalizedSku)) {
    throw new SkuAlreadyExistsException();
}
```

Nhưng luôn giữ DB UNIQUE và xử lý **violation lúc ghi/commit** làm phương án bảo vệ cuối. Đừng coi pre-check là điều kiện đủ.

---

## 23. Lớp ba: ràng buộc database là gì?

Database constraints định nghĩa những trạng thái của bảng/quan hệ mà database sẽ không cho phép lưu.

Một số ràng buộc phổ biến:

- `PRIMARY KEY`: định danh row duy nhất và không null.
- `NOT NULL`: cột bắt buộc có giá trị khác null.
- `UNIQUE`: uniqueness theo cột/tổ hợp cột, với null/collation semantics của DB.
- `FOREIGN KEY`: tham chiếu tới row hợp lệ ở bảng liên quan.
- `CHECK`: boolean condition trên dữ liệu row theo khả năng DB.
- `DEFAULT`: giá trị mặc định khi SQL INSERT không cung cấp cột, không phải validator tổng quát.
- Generated columns/constraints, exclusion constraints, filtered indexes hoặc triggers: khả năng nâng cao tùy database.

Bảng ví dụ:

```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    shop_id BIGINT NOT NULL,
    sku VARCHAR(80) NOT NULL,
    price DECIMAL(14,2) NOT NULL,

    CONSTRAINT fk_product_shop
        FOREIGN KEY (shop_id) REFERENCES shops(id),

    CONSTRAINT uq_product_shop_sku
        UNIQUE (shop_id, sku),

    CONSTRAINT ck_product_price_nonnegative
        CHECK (price >= 0)
);
```

Database áp dụng các constraints khi thực thi SQL/tại thời điểm quy định bởi engine. Các constraints vẫn bảo vệ dữ liệu **khi một batch JDBC hoặc ứng dụng khác bỏ qua Java service**.

## 24. `NOT NULL` và `@NotNull` khác nhau

JPA mapping:

```java
@NotNull
@Column(nullable = false)
private BigDecimal price;
```

Hai annotation khác tầng:

| Khai báo | Thuộc hệ thống | Ý nghĩa |
| --- | --- | --- |
| `@NotNull` | Bean Validation | Kiểm tra Java property không null khi validation chạy |
| `@Column(nullable = false)` | JPA mapping metadata | Mô tả nullability cột, thường dùng trong DDL generation và provider mapping |
| `price DECIMAL(...) NOT NULL` | Database schema | DB thực sự không chấp nhận giá trị SQL NULL |

Đừng suy rằng `@Column(nullable=false)` tự thay Bean Validation ở mọi request hoặc **tự bảo đảm schema production đã có NOT NULL**. Nếu production schema được quản lý bằng migrations, phải kiểm tra migration thật đã áp dụng ràng buộc.

Tương tự, `@NotNull` chỉ chạy khi validation được kích hoạt. Một native SQL viết trực tiếp vẫn có thể INSERT NULL nếu DB thiếu NOT NULL.

### Giá trị mặc định của primitive

`int quantity` không thể null trong Java, nhưng mặc định bằng `0`. Nếu nghiệp vụ yêu cầu quantity > 0, `@NotNull` không có ý nghĩa với primitive; cần `@Positive`/domain method và DB CHECK tùy yêu cầu.

## 25. `@Size` và độ dài cột

Ví dụ:

```java
@NotBlank
@Size(max = 200)
@Column(length = 200, nullable = false)
private String name;
```

Trong đó:

- `@Size(max=200)` kiểm tra độ dài Java CharSequence theo Bean Validation.
- `@Column(length=200)` là mapping/schema metadata để định nghĩa độ dài cột.
- `VARCHAR(200)` ở DB là giới hạn độ dài theo database semantics (ký tự/bytes/collation/dialect).

Không mặc định `String.length()`, “số ký tự nhìn thấy” và độ dài byte trong database luôn giống nhau với Unicode/emoji. Nếu API có giới hạn đặc thù theo grapheme clusters hoặc bytes, cần logic rõ và kiểm thử đúng RDBMS/encoding.

Bảo đảm cuối cùng cần schema constraint thực tế và error handling nếu DB từ chối chuỗi dài.

## 26. Precision, scale và quy tắc giá

Ví dụ:

```java
@NotNull
@DecimalMin("0.00")
@Digits(integer = 12, fraction = 2)
@Column(
    nullable = false,
    precision = 14,
    scale = 2
)
private BigDecimal price;
```

Ở đây:

- `@DecimalMin("0.00")` kiểm tra giá không âm.
- `@Digits(integer=12, fraction=2)` kiểm tra cấu trúc chữ số.
- `@Column(precision=14, scale=2)` biểu đạt metadata cột.
- `DECIMAL(14,2) CHECK(price >= 0)` bảo vệ database state.

Cần có policy về rounding/monetary units. Ví dụ nếu input là `12.345` và tiền tệ cho phép hai chữ số thập phân, ứng dụng phải quyết định **reject, round HALF_UP, hay một rule khác**; không phó mặc database tự làm tròn trong im lặng.

`BigDecimal` hỗ trợ decimal precision, nhưng một giá trị đúng kiểu `BigDecimal` vẫn có thể trái luật nghiệp vụ nếu quá lớn/âm/khác currency.

## 27. `UNIQUE` và chuẩn hóa SKU

Giả sử:

```text
abc-123
ABC-123
 ABC-123
```

có được coi là một SKU hay ba SKU khác nhau? Đây là **quy tắc canonicalization** của ứng dụng.

Value object:

```java
public final class ProductSku {

    private ProductSku() {}

    public static String normalize(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new IllegalArgumentException("SKU is required");
        }

        String value = raw.trim().toUpperCase(Locale.ROOT);

        if (!value.matches("[A-Z0-9-]{4,40}")) {
            throw new IllegalArgumentException("Invalid SKU");
        }

        return value;
    }
}
```

Nếu application luôn lưu normalized SKU:

```sql
UNIQUE (shop_id, sku)
```

thì uniqueness database bảo vệ các giá trị đã chuẩn hóa.

Nhưng nếu có writers bypass normalization, chúng có thể lưu lowercase hoặc whitespace khác mà DB collation vẫn xem là khác nhau. Có thể cần:

- Functional unique index trên `LOWER(TRIM(sku))`.
- Generated normalized column kèm unique constraint.
- Database check về allowed format.
- Case-insensitive collation khi semantics đúng.
- Một quy ước write path nhất quán, có tests.

**Unique constraint giữ uniqueness theo giá trị/collation DB nhìn thấy, không tự hiểu khái niệm “cùng SKU” nếu chuẩn hóa chưa thống nhất.**

## 28. UNIQUE theo tenant hoặc phạm vi

Một sai lầm phổ biến:

```sql
UNIQUE (sku)
```

trong hệ thống nhiều shops. Nó cấm hai shops khác nhau dùng cùng mã, có thể không đúng yêu cầu.

Nếu uniqueness chỉ trong mỗi shop:

```sql
CONSTRAINT uq_product_shop_sku
UNIQUE (shop_id, sku)
```

Thao tác service phải truyền/check `shopId` đáng tin cậy:

```java
Product product = new Product(
    authorizedShopId,
    normalizedSku,
    name,
    price
);
```

Không chỉ dựa vào request body `shopId` do client tự khai rồi tạo Product. Authorization và tenant scope thuộc service; unique constraint bảo vệ một **phạm vi định danh** ở DB.

### Soft delete và partial uniqueness

Nếu sản phẩm đã soft-delete được phép tái dùng SKU, rule có thể là “mỗi shop chỉ có một active product cho mỗi SKU”.

Các DB hỗ trợ **partial/filtered unique index** có thể diễn đạt:

```sql
-- SQL minh họa cho dialect hỗ trợ partial unique index.
CREATE UNIQUE INDEX uq_active_sku
ON products(shop_id, sku)
WHERE deleted_at IS NULL;
```

Đây là **DB-specific**, không phải DDL portable của mọi JPA provider. Nếu không hỗ trợ partial index, cần cách thiết kế khác và migration rõ.

## 29. NULL với UNIQUE và CHECK có thể gây bất ngờ

Database khác nhau có thể áp dụng semantics khác đối với nhiều giá trị NULL trong unique keys. Đừng suy rằng:

```sql
UNIQUE(email)
```

tự cấm nhiều rows có email NULL trên mọi RDBMS.

Nếu email là bắt buộc, thêm:

```sql
email VARCHAR(320) NOT NULL
```

và uniqueness phù hợp. Nếu optional, định nghĩa rõ có cho phép nhiều NULL không và kiểm tra theo DB mục tiêu.

Với CHECK:

```sql
CHECK (price >= 0)
```

SQL three-valued logic có thể cho phép NULL vì điều kiện đánh giá UNKNOWN chứ không FALSE, tùy constraint semantics. Vì vậy nếu price không được null, vẫn cần:

```sql
price DECIMAL(14,2) NOT NULL,
CHECK (price >= 0)
```

**CHECK và NOT NULL là hai ràng buộc bổ sung nhau**, không nên bỏ một trong hai mà không xét SQL NULL semantics.

## 30. FOREIGN KEY không thay phép kiểm tra nghiệp vụ

Ví dụ Product thuộc một Shop:

```sql
FOREIGN KEY (shop_id) REFERENCES shops(id)
```

Ràng buộc này bảo đảm giá trị shop_id tham chiếu đến một Shop tồn tại (theo constraint settings/transaction semantics).

Nó **không bảo đảm**:

- Shop đang active.
- User được phép tạo Product ở Shop.
- Shop chưa vượt quota sản phẩm.
- Shop thuộc tổ chức đang có hợp đồng hợp lệ.
- Product status được phép thay đổi.

Các điều kiện đó thường thuộc application/domain service, hoặc nếu thực sự phải được DB bảo đảm thì cần schema/locking/triggers/constraints riêng.

Đặt `@ManyToOne(optional=false)` và `@JoinColumn(nullable=false)` là metadata hữu ích cho ORM, nhưng foreign key thực sự phải tồn tại ở DB schema nếu yêu cầu bảo vệ mọi external writer.

## 31. CHECK có thể bảo vệ invariant một hàng

Một rule dễ bảo vệ:

```sql
CHECK (quantity >= 0)
```

Một rule kết hợp fields trong cùng row:

```sql
CHECK (
    status <> 'PUBLISHED'
    OR approved_at IS NOT NULL
)
```

Các CHECK này giúp chặn dữ liệu bất hợp lệ do:

- SQL do service không gọi domain method.
- Bulk JPQL/native DML.
- Batch import.
- ETL job.
- Một ứng dụng khác truy cập cùng database.

Nhưng CHECK thông thường không phù hợp để tự tham chiếu một loạt rows/tables tùy ý, và DBs có giới hạn riêng về subqueries, user-defined functions hoặc constraint volatility.

Ví dụ “tổng OrderLine amount phải đúng bằng Order.total” là một **cross-row/cross-table invariant**. Nó thường cần transaction-level service logic, triggers/materialized totals/constraints nâng cao hoặc một thiết kế dữ liệu khác, không chỉ một CHECK đơn giản trên Order row.

## 32. Business rule theo thời gian không phải constraint tĩnh

Quy tắc:

> “Chỉ cho phép hủy Order trước thời hạn giao 24 giờ.”

Nó phụ thuộc thời điểm hiện tại và lịch giao. Một check trên object có thể tính:

```java
boolean cancellable =
    clock.instant().isBefore(
        deliveryAt.minus(24, ChronoUnit.HOURS)
    );
```

Nhưng:

- Đồng hồ khác nhau giữa application nodes có thể gây lệch.
- DeliveryAt có thể bị thay đổi đồng thời.
- User permission có thể khác theo trạng thái Order.
- Không nên mã hóa một điều kiện theo “current time” không ổn định như một CHECK tĩnh rồi giả định DB tự tái kiểm tra khi thời gian trôi qua.
- Cần transaction/lock/version khi transition state.

Business rule phụ thuộc thời gian thường ở domain/service với injected `Clock`, kèm DB constraints cho những trạng thái có thể biểu diễn bền vững (ví dụ không có `cancelled_at` khi status khác CANCELLED nếu đó là invariant).

---

## 33. Ma trận trách nhiệm cho Product

| Yêu cầu | Object validation | Business/domain | Database |
| --- | --- | --- | --- |
| SKU không blank | `@NotBlank` | Normalize và từ chối bất hợp lệ | `NOT NULL`, có thể CHECK format |
| SKU tối đa 80 | `@Size(max=80)` | Value object chuẩn hóa | `VARCHAR(80)` |
| Price không null | `@NotNull` | Constructor/method yêu cầu có giá | `NOT NULL` |
| Price không âm | `@DecimalMin("0")` | `setPrice` từ chối âm | `CHECK(price >= 0)` |
| SKU duy nhất trong shop | Không đủ qua `@Pattern` | Có thể pre-check thân thiện | `UNIQUE(shop_id, sku)` |
| User có quyền tạo | Không phải field-shape rule | Authorization trong service | Không thay thế bằng UNIQUE/FK |
| Shop phải active | Không phải một property của request | Query Shop/policy trong transaction | Có thể cần cơ chế riêng nếu phải bảo vệ dưới concurrency |
| DRAFT → APPROVED → PUBLISHED | Không chỉ một enum value | Domain transition methods | CHECK trạng thái và cặp fields; không tự bảo đảm lịch sử |
| Product thuộc shop tồn tại | `@NotNull shopId` không đủ | Service tìm shop có quyền | FOREIGN KEY |
| Chặn stale update | DTO có expectedVersion token | Service kiểm tra intent | `@Version`/SQL conditional update |
| Không tồn kho âm | Request số lượng dương | Reserve logic | CHECK, atomic update/locking |
| Không trùng booking slot | DTO ngày/time hợp lệ | Chọn slot/can-book policy | UNIQUE/exclusion/guard lock phù hợp |

Bảng này không yêu cầu copy-paste mọi điều kiện vào ba nơi. Nó giúp xác định **lớp nào cho trải nghiệm tốt, lớp nào giữ nghiệp vụ, lớp nào bảo đảm tính toàn vẹn khi có nhiều đường ghi**.

## 34. Bất biến có nhiều mức bảo đảm

Nên phân loại theo mức:

1. **Presentation invariant:** field trên form có định dạng đúng để hiển thị/gửi request.
2. **Command invariant:** một hành động có inputs đầy đủ, hợp lệ.
3. **Entity invariant:** một entity không ở trạng thái tự mâu thuẫn trong domain model.
4. **Aggregate invariant:** những entities thuộc aggregate cùng tuân quy tắc, ví dụ order total.
5. **Cross-aggregate invariant:** quota, uniqueness, balance limit, inventory.
6. **Persistence invariant:** database rows/relations không vi phạm constraint.
7. **Security invariant:** người gọi không được thao tác tài nguyên ngoài quyền/tenant.
8. **Concurrency invariant:** kết quả vẫn đúng khi nhiều transactions đồng thời.

Không phải toàn bộ những mức này đều giải quyết được bằng `@NotNull` hay `@AssertTrue`. Thiết kế tốt giúp người đọc thấy **invariant thuộc phạm vi nào và được bảo vệ bằng công cụ nào**.

## 35. Độ tin cậy của pre-check và database constraint

So sánh:

```java
if (productRepository.existsByShopIdAndSku(shopId, sku)) {
    throw new DuplicateSkuException();
}
```

và:

```sql
UNIQUE (shop_id, sku)
```

Pre-check có thể:

- Giảm số requests vấp DB exception.
- Trả message rõ ràng ngay trước persist.
- Cho biết mã SKU nào đã được dùng.
- Nhưng không atomic với INSERT nếu chỉ SELECT rồi INSERT.

DB UNIQUE có thể:

- Bảo vệ trước concurrent inserts.
- Áp dụng cho external writers.
- Nhưng lỗi có thể đến muộn tại flush/commit.
- Cần dịch error code/constraint name sang thông báo hợp lý.
- Không biết đầy đủ authorization context của người dùng.

Kết luận: **Pre-check là hỗ trợ trải nghiệm, UNIQUE mới là hàng rào cuối cho uniqueness.**

## 36. Khi nào lỗi xuất hiện: setter, validator, flush hay commit?

Một transaction có thể:

```java
em.getTransaction().begin();

Product product = new Product(
    shopId,
    sku,
    name,
    price
);

em.persist(product);

em.getTransaction().commit();
```

Các lỗi khác nhau xuất hiện tại các mốc khác nhau:

| Mốc | Loại lỗi có thể xuất hiện |
| --- | --- |
| JSON parsing | Sai kiểu dữ liệu, sai cú pháp |
| `@Valid` ở controller | Không blank, sai size, giá âm |
| Domain constructor/method | Trạng thái hoặc thao tác sai |
| Service query/pre-check | Không có shop, không có quyền, SKU có vẻ trùng |
| `em.persist(...)` | Có thể gặp lỗi mapping/lifecycle/INSERT sớm |
| `em.flush()` | Bean Validation lifecycle, NOT NULL, CHECK, UNIQUE, FK, version conflicts |
| `commit()` | Flush còn lại, deferred constraints, transaction errors |
| Sau commit | Đây mới là lúc có thể thông báo durable success |

**Không được coi `save()` hoặc `persist()` trả về không exception là bằng chứng tất cả ràng buộc DB đã được kiểm tra.** Một số constraints chỉ được DB kiểm tra khi INSERT/UPDATE thực thi, hoặc khi commit nếu là deferrable constraint trong dialect hỗ trợ.

## 37. Flush không có nghĩa transaction đã commit

Ví dụ:

```java
em.getTransaction().begin();

em.persist(product);
em.flush(); // INSERT và constraints có thể đã được kiểm tra.

em.getTransaction().rollback();
```

Database có thể đã chạy INSERT nhưng rollback làm thay đổi không được commit bền vững.

Hệ quả:

- Object Java Product có thể giữ ID/timestamps/version đã được gán.
- PrePersist callbacks có thể đã chạy.
- External side effect ở listener không tự rollback.
- Dữ liệu DB có thể không có Product sau rollback.
- Một constraint chưa được kiểm tra do deferrable semantics có thể vẫn làm commit fail dù flush trước đó thành công.

Khi cần chắc chắn một request tạo Product thành công, chỉ coi là thành công **sau transaction completion**. Đối với external events, cân nhắc transactional outbox thay vì gửi email/message trước commit.

## 38. Phân biệt hai `ConstraintViolationException` hay gặp

Một điểm rất dễ nhầm khi dùng Hibernate ORM + Jakarta Bean Validation:

### Bean Validation exception

```java
jakarta.validation.ConstraintViolationException
```

Thường mang danh sách violations của properties/paths, ví dụ `price must be greater than or equal to 0`, khi Bean Validation chạy.

### Hibernate ORM/database exception

```java
org.hibernate.exception.ConstraintViolationException
```

Thường thể hiện database constraint violation, ví dụ unique/foreign-key/check, được ORM ném/bọc từ JDBC error.

Hai exception **khác package và nguồn gốc**. Không nên chỉ bắt class tên `ConstraintViolationException` rồi coi mọi lỗi đều là “người dùng nhập sai field”.

Ngoài ra, transaction manager có thể bọc lỗi trong `PersistenceException`, `RollbackException` hoặc Spring `DataIntegrityViolationException`.

Khi phân loại:

- Dựa vào full exception type/package.
- Đọc cause chain có kiểm soát.
- Nếu là DB constraint, xác định **constraint name/code** từ driver/provider nếu được hỗ trợ.
- Không parse raw English error message làm hợp đồng bền vững.
- Không log/present giá trị nhạy cảm ra response.

## 39. Bean Validation violations có thể chuyển thành field errors

Một validator:

```java
Set<ConstraintViolation<CreateProductRequest>> violations =
    validator.validate(request);
```

Mỗi `ConstraintViolation` có thể cung cấp:

- Property path.
- Message template/message.
- Invalid value (cần cẩn trọng bảo mật).
- Root bean/leaf bean.
- Constraint descriptor.

Một API có thể chuyển thành:

```json
{
  "code": "VALIDATION_FAILED",
  "fields": [
    {
      "field": "sku",
      "message": "must not be blank"
    },
    {
      "field": "price",
      "message": "must be greater than or equal to 0"
    }
  ]
}
```

Đây là ví dụ về hợp đồng JSON, không phải format Jakarta Validation bắt buộc. Trong sản phẩm thật, messages thường được localize và tránh lộ raw invalid values nếu chứa dữ liệu nhạy cảm.

### Có nên công khai mọi Bean Validation message?

Không nhất thiết. Một số violations ở persistence layer có thể nhắc tới internal entity fields không thuộc public API; controller nên chuyển thành thông điệp/field names theo contract của endpoint.

## 40. Business errors cần mã lỗi rõ

Service:

```java
if (!shop.isActive()) {
    throw new BusinessRuleViolation(
        "SHOP_INACTIVE",
        "Shop is not active"
    );
}
```

Một domain error có thể có:

- Stable machine-readable code.
- Human-readable message.
- Context an toàn để client biết hướng xử lý.
- Correlation ID cho log.

Ví dụ:

```json
{
  "code": "SHOP_INACTIVE",
  "message": "Cửa hàng chưa hoạt động nên không thể đăng sản phẩm."
}
```

Điều này khác input format error và khác database integrity failure. API có thể chọn HTTP 400, 409 hoặc 422 tùy hợp đồng, nhưng phải nhất quán.

**Không phải mọi business-rule failure đều là lỗi kỹ thuật 500**, và cũng không nên chuyển mọi lỗi SQL thành 400 để che mất bug.

## 41. Database constraint errors cần ánh xạ có chọn lọc

Giả sử unique constraint có tên:

```sql
uq_product_shop_sku
```

Khi DB từ chối một Product trùng SKU, application có thể chuyển error thành:

```json
{
  "code": "SKU_ALREADY_EXISTS",
  "message": "Mã sản phẩm đã tồn tại trong cửa hàng."
}
```

Cách làm đúng là **nhận diện constraint cụ thể** qua provider/driver translation và map nó sang domain error tương ứng.

Không nên:

```java
catch (RuntimeException ex) {
    throw new DuplicateSkuException();
}
```

vì một RuntimeException có thể là:

- Connection timeout.
- Foreign key violation.
- Deadlock.
- Null pointer bug.
- Optimistic locking conflict.
- Serialization failure.
- Một lỗi validation khác.

Khi database trả lỗi không được nhận diện, nên để exception đi qua error boundary thích hợp, ghi log có kiểm soát và không giả làm “SKU trùng”.

## 42. Lỗi SQL tại commit có thể xảy ra ngoài try/catch của service body

Trong Spring proxy-based transaction:

```java
@Service
public class ProductService {

    @Transactional
    public ProductView create(
            Long shopId,
            CreateProductRequest request) {

        Product product = new Product(
            shopId,
            request.sku(),
            request.name(),
            request.price()
        );

        repository.save(product);

        return toView(product);
    }
}
```

Transaction interceptor có thể flush/commit **sau khi method body return**. Do đó catch nằm bên trong method chỉ bao lấy `repository.save` có thể không bắt được UNIQUE violation xuất hiện tại commit.

Hướng tiếp cận:

- Đặt exception translation ở tầng ngoài transaction (controller advice/application boundary).
- Hoặc chủ động `flush()` khi cần phát hiện lỗi sớm trong scope có thể xử lý, nhưng vẫn phải dự trù commit failure.
- Không nuốt exception khi transaction đã rollback-only.
- Không coi return DTO trước commit là durable success.

Với resource-local `EntityTransaction`, code dùng `try/catch` bao cả `commit()`.

## 43. Không tiếp tục dùng transaction sau lỗi integrity nghiêm trọng

Ví dụ sai:

```java
try {
    em.persist(product);
    em.flush();
} catch (PersistenceException ex) {
    product.setSku("ANOTHER-SKU");
    em.flush(); // Cố tiếp tục trong transaction đã lỗi.
}
```

Nếu DB constraint violation khiến transaction/provider ở trạng thái thất bại hoặc rollback-only, cố thay field và flush tiếp **không phải pattern an toàn**.

Nên:

1. Phân loại lỗi ở boundary.
2. Rollback transaction hiện tại.
3. Kết thúc persistence context của đơn vị công việc thất bại.
4. Nếu nghiệp vụ cho phép retry, tạo transaction/context mới.
5. Đọc lại state liên quan và áp dụng command hợp lệ.
6. Không chỉ lặp thao tác trên managed entity đã lỗi.

Một số database đánh dấu transaction aborted sau SQL error và không cho các SQL tiếp theo trước rollback. Không nên xây logic dựa trên giả định mọi DB cho phép “sửa và tiếp tục” sau constraint failure.

## 44. Domain method và `@PrePersist` khác nhau

Một cách validation muộn:

```java
@PrePersist
@PreUpdate
void checkState() {
    if (price.signum() < 0) {
        throw new IllegalStateException("Negative price");
    }
}
```

Ưu điểm: có một lớp phòng vệ khi entity đi qua managed lifecycle.

Nhược điểm:

- Chạy muộn khi persist/flush.
- Không kích hoạt cho bulk/native SQL.
- Nếu `price` null, có thể NullPointerException nếu code không check.
- Không kiểm tra business transition/history.
- Không thích hợp query repository hoặc đổi association graph.
- Không thay thế DB CHECK.

Domain method:

```java
public void changePrice(BigDecimal newPrice) {
    if (newPrice == null || newPrice.signum() < 0) {
        throw new IllegalArgumentException("Invalid price");
    }
    this.price = newPrice;
}
```

báo lỗi **ngay tại business operation** và làm code dễ suy luận hơn. Có thể kết hợp callback local check và database constraint khi cần, nhưng không mặc định chỉ cần callback.

## 45. JPA entity có thể bị load mà không qua constructor nghiệp vụ

Ví dụ Product có constructor:

```java
public Product(String name, BigDecimal price) {
    // validation...
}
```

và constructor không tham số:

```java
protected Product() {}
```

JPA provider có thể tạo entity qua no-arg constructor và hydrate persistent fields từ DB bằng field/property access tùy mapping. Vì vậy constructor nghiệp vụ không tự là lớp kiểm tra mọi row đọc từ DB.

Nếu DB chứa dữ liệu legacy không hợp lệ, query vẫn có thể trả một entity state vi phạm invariant kỳ vọng. Thay vì coi constructor là DB enforcement:

- Đảm bảo database constraints ở migration.
- Backfill/clean dữ liệu legacy.
- Thiết kế domain methods cho state transitions.
- Kiểm tra data quality và schema compatibility trong integration tests.
- Dùng DTO/value objects cho những giá trị có construction invariants khi phù hợp.

Object validation và database integrity là hai trách nhiệm khác nhau.

## 46. Entity annotations không tự làm schema production đúng

Ví dụ:

```java
@Column(nullable = false, unique = true)
private String sku;
```

Nếu schema production được tạo bằng Flyway/Liquibase/migrations, việc đổi annotation **không có nghĩa DB đã tự thêm NOT NULL/UNIQUE**.

Thậm chí `unique=true` trên riêng SKU có thể sai phạm vi nếu business rule là unique trong từng shop.

Vì vậy:

- Entity mapping mô tả model ORM.
- Migration định nghĩa schema thực triển khai.
- DDL generation có thể hữu ích cho test/development, nhưng không thay thế migration review cho production.
- Schema drift giữa entity và DB phải được phát hiện.
- Không tùy tiện dùng auto schema update để sửa ràng buộc trên production database mà không kiểm soát dữ liệu cũ.

Nếu cần unique compound key, chọn `@Table(uniqueConstraints=...)` để biểu đạt mapping metadata và tạo migration tương ứng; đừng trông chờ `@Column(unique=true)` cho một ràng buộc nhiều cột.

## 47. Mô tả composite unique trong JPA

Entity:

```java
@Entity
@Table(
    name = "products",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_product_shop_sku",
        columnNames = {"shop_id", "sku"}
    )
)
public class Product {

    @Id
    private Long id;

    @Column(name = "shop_id", nullable = false)
    private Long shopId;

    @Column(name = "sku", nullable = false)
    private String sku;
}
```

Annotation này giúp metadata/DDL generator biết uniqueness mong muốn, nhưng **chỉ một constraint tồn tại và được database áp dụng mới thực sự chặn concurrent duplicates**.

Nếu database migration hiện tại không tạo `uq_product_shop_sku`, annotation không làm production tự an toàn.

### Thiết kế tên constraint ổn định

Đặt tên constraint rõ có ích khi:

- Đọc lỗi SQL và phân loại.
- Viết migrations.
- Tra cứu schema.
- Mapping lỗi API thành domain code.
- So sánh schema nhiều môi trường.

Nhưng không nên hardcode parsing raw error message kiểu “Duplicate entry” để nhận diện constraint, vì tên và message vary theo dialect/driver.

## 48. DDL migration khi thêm constraint vào dữ liệu cũ

Giả sử bảng products đã có duplicates và giá âm:

```sql
SELECT shop_id, sku, COUNT(*)
FROM products
GROUP BY shop_id, sku
HAVING COUNT(*) > 1;

SELECT id, price
FROM products
WHERE price < 0 OR price IS NULL;
```

Không thể chỉ thêm:

```sql
ALTER TABLE products
ADD CONSTRAINT uq_product_shop_sku UNIQUE (shop_id, sku);
```

mà mặc định thành công khi dữ liệu đang vi phạm.

Một quy trình migration:

1. Xác định invariant mới và phạm vi áp dụng.
2. Thống kê dữ liệu cũ không hợp lệ.
3. Quyết định cleanup/backfill được nghiệp vụ phê duyệt.
4. Cập nhật code writers để không tạo dữ liệu sai mới.
5. Áp dụng migration constraint/index phù hợp.
6. Kiểm tra kết quả schema thực tế.
7. Giám sát constraint violations sau rollout.
8. Xóa workaround code sau khi toàn hệ thống chuyển chính sách.

Với hệ thống có lưu lượng ghi cao, cần kế hoạch online migration, khóa bảng/index creation và compatibility giữa các phiên bản ứng dụng.

**Database constraint là một hợp đồng dữ liệu dài hạn; thêm nó cần quản lý dữ liệu lịch sử và quy trình triển khai.**

## 49. Chọn ràng buộc mạnh nhưng không khóa nhầm nghiệp vụ

Một constraint:

```sql
UNIQUE (email)
```

có thể đúng ở hệ thống “mỗi email chỉ một tài khoản toàn cầu”, nhưng sai ở hệ thống multi-tenant có một email tham gia nhiều tổ chức.

Một CHECK:

```sql
CHECK (discount_percentage <= 50)
```

có thể đúng hôm nay nhưng sai khi policy cho phép 70% cho một chương trình đặc biệt.

Vì vậy, trước khi đưa business policy vào DB:

- Rule có phải **bất biến bền vững mọi lúc** không?
- Rule phụ thuộc shop, actor, thời gian hay cấu hình bên ngoài không?
- Có dữ liệu legacy khác yêu cầu không?
- Có cần thay đổi policy thường xuyên mà không migration schema không?
- Có thể mã hóa rule bằng CHECK/UNIQUE/FK đơn giản không?
- Nếu cần trigger, ai quản lý/test/monitor nó?
- Có nguy cơ database-only rule không được service thông báo tốt không?

Không phải mọi business rule nên trở thành CHECK, nhưng các trạng thái tuyệt đối sai của dữ liệu nên được chặn tại DB khi có thể.

---

## 50. Quy tắc kiểm tra duy nhất trên một request không đủ cho concurrency

Giả sử người dùng muốn tạo Reservation cho phòng và ngày:

```java
if (!reservationRepository.existsByRoomIdAndDate(roomId, date)) {
    reservationRepository.save(
        new Reservation(roomId, date)
    );
}
```

Tại thời điểm kiểm tra, chỗ có thể còn trống. Trước INSERT, một transaction khác có thể đặt cùng phòng.

Nếu business rule là một reservation duy nhất mỗi room/day:

```sql
UNIQUE (room_id, reserved_date)
```

bảo vệ tốt ở DB.

Nếu booking có các khoảng thời gian chồng lấn, một UNIQUE trên start_time đơn lẻ không đủ. Các lựa chọn có thể gồm:

- DB exclusion constraints trên range types ở DB hỗ trợ.
- Lock một guard row của room trong transaction rồi kiểm tra overlap.
- Serializable isolation với transaction retry phù hợp.
- Mô hình slot granularity có unique keys.
- Một allocator/service tuần tự hóa per-room.
- Kết hợp constraints và application logic.

**Chọn constraint phải dựa trên bất biến thật**, không chỉ chọn UNIQUE vì nó dễ viết.

## 51. Quy tắc tổng tiền Order và các dòng OrderLine

Một aggregate:

```text
Order
 ├─ Line A: quantity 2 × unitPrice 100
 └─ Line B: quantity 1 × unitPrice 50

Total = 250
```

Object validation có thể xác minh:

- quantity > 0.
- unitPrice >= 0.
- Không thiếu productId.

Domain invariant cần đảm bảo:

```java
public BigDecimal calculateTotal() {
    return lines.stream()
        .map(line -> line.getUnitPrice()
            .multiply(BigDecimal.valueOf(line.getQuantity())))
        .reduce(BigDecimal.ZERO, BigDecimal::add);
}
```

Database có thể bảo vệ:

- `CHECK(quantity > 0)` cho line.
- `CHECK(unit_price >= 0)` cho line.
- FK `order_id`.
- NOT NULL.
- Một số unique constraints theo domain model.

Nhưng “Order.total luôn đúng bằng tổng mọi lines” là một **cross-row aggregate invariant**. Nếu Order.total được lưu riêng để tăng tốc, cần quyết định:

- Tính lại theo service trong cùng transaction.
- Lock Order root/OrderLines phù hợp.
- Dùng versioning để phát hiện cập nhật đồng thời.
- Database trigger/materialized calculation khi thật sự cần.
- Hoặc **không lưu total** nếu có thể tính theo query/DTO projection mà vẫn đủ hiệu năng.

Không giả định `@AssertTrue` trên Order tự bảo vệ khi một native SQL thêm line vào DB.

## 52. Transaction là nơi ghép các lớp lại

Một workflow tạo Product có thể được biểu diễn:

```text
Request DTO
    │
    ▼
Bean Validation
    │
    ├─ lỗi field → trả 400/422 theo API
    │
    ▼
Application service bắt đầu transaction
    │
    ├─ xác định actor/tenant/permission
    ├─ load Shop và kiểm tra trạng thái
    ├─ chuẩn hóa SKU, tạo Product DRAFT
    ├─ optional duplicate pre-check
    ├─ em.persist(product)
    └─ flush / commit
              │
              ├─ UNIQUE / CHECK / FK / NOT NULL được DB kiểm tra
              ├─ optimistic/DB concurrency checks
              └─ commit hoặc rollback
    │
    ▼
API boundary ánh xạ lỗi có chọn lọc
```

Trong thực tế có thể có nhiều operations/transactions hơn, nhưng hợp đồng nên rõ:

- Domain service chỉ return success khi transaction đã hoàn tất thành công ở boundary áp dụng.
- Đừng publish external event trước commit nếu cần bảo đảm không báo sai.
- Database exception được dịch mà không làm mất nguyên nhân kỹ thuật trong logs.
- Nếu retry, tạo đơn vị công việc mới với current state.
- Không tiếp tục dùng persistence context sau transaction lỗi.

## 53. Xử lý lỗi transaction resource-local

Một skeleton:

```java
public Long create(
        EntityManagerFactory emf,
        CreateProductRequest request,
        Long authorizedShopId) {

    EntityManager em = emf.createEntityManager();

    try {
        em.getTransaction().begin();

        Product product = new Product(
            authorizedShopId,
            request.sku(),
            request.name(),
            request.price()
        );

        em.persist(product);

        // Tùy ID strategy, flush giúp hoàn tất insert và
        // phát hiện nhiều lỗi DB sớm hơn.
        em.flush();

        Long id = product.getId();

        em.getTransaction().commit();

        return id;
    } catch (RuntimeException failure) {
        if (em.getTransaction().isActive()) {
            try {
                em.getTransaction().rollback();
            } catch (RuntimeException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
        }
        throw failure;
    } finally {
        em.close();
    }
}
```

Ở ví dụ này, caller phải **kiểm tra object request, quyền và shop policy** ở vị trí phù hợp; method tập trung minh họa transaction/JPA write. Không nên diễn giải nó là endpoint production đầy đủ.

Nếu môi trường dùng JTA/Spring, transaction manager quản lý commit/rollback. Không gọi `em.getTransaction()` trên container-managed EntityManager một cách tùy tiện.

## 54. Validation lỗi sau rollback không tự khôi phục object Java

Một transaction:

```java
Product product = em.find(Product.class, id);

product.setPrice(new BigDecimal("-1"));

try {
    em.flush();
} catch (RuntimeException failure) {
    em.getTransaction().rollback();
}
```

Dù DB từ chối UPDATE và rollback, object `product` trong heap có thể vẫn giữ giá -1. Rollback database không tự hoàn tác mọi setter trên Java instance.

Nếu muốn trả trạng thái DB đã commit sau lỗi:

- Đóng context thất bại.
- Đọc lại Product trong context/transaction mới.
- Không dùng entity từ rollback làm DTO “current saved state”.
- Nếu cần giữ input người dùng, lưu nó ở command/form DTO riêng.

Đây là khác biệt giữa **trạng thái đối tượng Java** và **trạng thái dữ liệu đã commit**.

## 55. DTO và entity validation có thể khác nhau một cách hợp lý

Ví dụ partial update chỉ đổi giá:

```java
public record ChangePriceRequest(
    @NotNull
    @PositiveOrZero
    BigDecimal newPrice,

    @NotNull Long expectedVersion
) {}
```

Không bắt client gửi name/sku/status vì chúng không liên quan operation.

Service:

```java
public void changePrice(
        Long productId,
        ChangePriceRequest request) {

    Product product = repository.findById(productId)
        .orElseThrow();

    checkVersion(
        product.getVersion(),
        request.expectedVersion()
    );

    product.setPrice(request.newPrice());
}
```

`checkVersion` là helper/service policy của ứng dụng. Sau khi method trả, managed update được flush/commit theo transaction boundary, và `@Version` là hàng rào chống race giữa lần check và DB write.

Không cần một DTO “đại diện toàn bộ entity” với tất cả trường optional để phục vụ mọi API PATCH. Command DTO chuyên biệt giúp cho phép cập nhật **đúng trường người dùng được quyền sửa**.

## 56. Validation không thay thế authorization và mass-assignment protection

Một lỗi thiết kế:

```java
public record ProductUpdateRequest(
    String name,
    BigDecimal price,
    Long shopId,
    boolean approved
) {}
```

Nếu endpoint cho mọi user cập nhật object này rồi copy thẳng vào entity:

```java
mapper.copyAllFields(request, product);
```

người dùng có thể thay `shopId` hoặc `approved` dù các giá trị đều vượt qua `@NotNull`, `@Size`.

Validation bảo đảm **giá trị hợp dạng**, không tự bảo đảm **người gọi được quyền sửa field đó**.

Một service an toàn hơn nhận các commands có allowlist:

```java
public record RenameProductCommand(
    @NotBlank String newName
) {}

public record ChangeProductPriceCommand(
    @NotNull @PositiveOrZero BigDecimal price
) {}
```

và áp dụng qua methods kiểm tra quyền, tenant và state.

## 57. Chuyển đổi lỗi sang HTTP status

Không có một ánh xạ HTTP duy nhất bắt buộc cho mọi API, nhưng có thể chọn policy nhất quán:

| Ngữ cảnh | Trạng thái thường dùng | Ví dụ mã nghiệp vụ |
| --- | --- | --- |
| JSON sai cú pháp/kiểu | 400 Bad Request | `INVALID_REQUEST` |
| Field object không hợp lệ | 400 hoặc 422 | `VALIDATION_FAILED` |
| Không có quyền | 403 Forbidden (hoặc 404 nếu không lộ tồn tại) | `FORBIDDEN` |
| ID không tồn tại | 404 Not Found | `PRODUCT_NOT_FOUND` |
| State transition không cho phép | 409 hoặc 422 | `INVALID_STATE_TRANSITION` |
| SKU bị unique conflict | 409 Conflict | `SKU_ALREADY_EXISTS` |
| Version/If-Match lỗi thời | 409 hoặc 412 | `STALE_VERSION` |
| Insufficient stock | 409 hoặc 422 tùy contract | `INSUFFICIENT_STOCK` |
| DB connection error | 500/503 theo hạ tầng | `SERVICE_UNAVAILABLE` |
| Lỗi SQL không nhận diện | 500, log nguyên nhân nội bộ | `INTERNAL_ERROR` |

Không map mọi `DataIntegrityViolationException` thành một lỗi “input không hợp lệ”: có thể là bug migration hoặc vi phạm FK do logic nội bộ. Chỉ chuyển những constraints đã nhận diện và có ý nghĩa domain sang public error code.

## 58. Testing: kiểm thử từng lớp riêng

Cần nhiều loại tests, vì một loại test không chứng minh tất cả.

| Kiểu test | Mục tiêu |
| --- | --- |
| Bean Validation unit test | Field, cross-field, groups, messages/paths |
| Domain unit test | State transitions và local invariants |
| Service test | Authorization, tenant scope, business policies |
| JPA integration test | Persistence validation, callbacks, flush/commit behavior |
| Database integration test | NOT NULL, UNIQUE, CHECK, FK thật |
| Concurrency integration test | Race conditions, version/locking/atomic SQL |
| API integration test | HTTP error mapping và response fields |
| Migration/schema test | Constraints tồn tại trên DB triển khai |
| External writer test | Native/bulk/JDBC không bypass database invariants |

**Test một DTO `@NotBlank` xanh không chứng minh DB unique constraint tồn tại**; ngược lại, test DB chặn giá âm không chứng minh API trả field error dễ hiểu.

## 59. Unit test cho Bean Validation

Một ví dụ JUnit 5:

```java
@Test
void rejectsBlankSkuAndNegativePrice() {
    CreateProductRequest request =
        new CreateProductRequest(
            " ",
            "Keyboard",
            new BigDecimal("-100")
        );

    Set<ConstraintViolation<CreateProductRequest>> violations =
        validator.validate(request);

    Set<String> invalidFields = violations.stream()
        .map(v -> v.getPropertyPath().toString())
        .collect(Collectors.toSet());

    assertTrue(invalidFields.contains("sku"));
    assertTrue(invalidFields.contains("price"));
}
```

`validator` được tạo từ ValidatorFactory phù hợp trong test fixture. Test kiểm tra violations theo property path; không assert toàn bộ message tiếng Anh nếu provider/localization có thể khác.

Một test khác cần kiểm tra giới hạn `@Size` và `@Digits` với giá trị biên.

## 60. Unit test cho domain state transition

```java
@Test
void cannotPublishDraftProduct() {
    Product product = new Product(
        7L,
        "ABC-123",
        "Keyboard",
        new BigDecimal("150000")
    );

    assertEquals(
        ProductStatus.DRAFT,
        product.getStatus()
    );

    assertThrows(
        IllegalStateException.class,
        product::publish
    );
}
```

Test này không cần database vì invariant “chưa approve thì không publish” nằm trên trạng thái Product hiện có.

Thêm test cho luồng hợp lệ:

```java
@Test
void approvedProductCanBePublished() {
    Product product = sampleDraftProduct();

    product.approve(Instant.parse(
        "2026-01-01T00:00:00Z"
    ));

    product.publish();

    assertEquals(
        ProductStatus.PUBLISHED,
        product.getStatus()
    );
}
```

Nếu rule cần Shop state và user permission, dùng service tests với policy collaborators hoặc integration test phù hợp. Không ép mọi domain test phải khởi tạo EntityManager nếu logic không phụ thuộc persistence.

## 61. Integration test: database CHECK thật

Một test kiểm tra CHECK nên cố tình **bypass object validation/domain method** để chứng minh database constraint tự bảo vệ.

Ví dụ JDBC khái niệm:

```java
@Test
void databaseRejectsNegativePrice() {
    assertThrows(SQLException.class, () -> {
        try (Connection c = dataSource.getConnection();
             PreparedStatement ps = c.prepareStatement(
                 "INSERT INTO products " +
                 "(id, shop_id, sku, name, price, " +
                 "status, version) " +
                 "VALUES (?, ?, ?, ?, ?, ?, ?)"
             )) {

            ps.setLong(1, newTestId());
            ps.setLong(2, existingShopId);
            ps.setString(3, "NEG-PRICE");
            ps.setString(4, "Invalid item");
            ps.setBigDecimal(5, new BigDecimal("-1"));
            ps.setString(6, "DRAFT");
            ps.setLong(7, 0L);

            ps.executeUpdate();
        }
    });
}
```

Ví dụ cần fixture/transaction setup thực tế, ID strategy phù hợp và database thật có CHECK constraint. Đừng assert chỉ một class `SQLException` nếu framework/provider sẽ bọc lỗi hoặc SQL engine trả loại cụ thể; test nên nhận diện SQLState/constraint có chủ đích.

Quan trọng: nếu test đi qua `Product.setPrice`, nó có thể bị domain method chặn trước khi DB được thử. Muốn chứng minh database CHECK, dùng một đường SQL trực tiếp trong test được cô lập.

## 62. Integration test: UNIQUE dưới concurrency

Mục tiêu: hai writers không thể commit cùng `(shop_id, sku)`.

Một test có thể:

1. Seed Shop và commit.
2. Chuẩn bị hai transactions độc lập.
3. Cho cả A/B cùng thử INSERT Product với SKU giống nhau.
4. Điều khiển timing bằng latch/barrier thay vì sleep tùy tiện.
5. Chờ kết quả commit/rollback của cả hai.
6. Xác nhận DB cuối cùng có đúng một row `(shop,sku)`.
7. Xác nhận một writer thành công và writer kia bị unique conflict hoặc transaction failure tương ứng.

Pseudo-flow:

```text
Thread A / Transaction A     Thread B / Transaction B
            │                            │
INSERT (7, ABC-123)             INSERT (7, ABC-123)
            │                            │
         COMMIT                      COMMIT
            │                            │
          success                conflict / rolled back
            └────────────┬───────────────┘
                         ▼
             COUNT(*) WHERE shop=7
                         AND sku=ABC-123
                         = 1
```

Số lần chờ/SQL exception timing phụ thuộc database isolation và lock scheduling. Nhưng invariant phải là **không có hai committed duplicate rows** nếu unique constraint đúng.

### Không dùng cùng EntityManager cho hai transactions

`EntityManager` không thread-safe. Mỗi thread cần context và DB transaction riêng. Không chạy concurrency test trên H2/in-memory setup nếu nó không phản ánh lock/isolation của production mà lại suy ra guarantee của DB khác.

## 63. Integration test: quy tắc không bị bypass bởi native SQL

Nếu schema có:

```sql
CHECK (price >= 0)
```

test native UPDATE:

```java
em.createNativeQuery(
    "UPDATE products SET price = ? WHERE id = ?"
).setParameter(1, new BigDecimal("-1"))
 .setParameter(2, productId)
 .executeUpdate();
```

nên bị database từ chối khi SQL được thực thi nếu CHECK đang được enforce.

Trong khi đó Java `@PreUpdate` callback/Bean Validation per-entity không cần chạy cho câu native update, nên đừng coi nó là nguồn bảo vệ của test này.

Sau lỗi:

- Rollback transaction.
- Đọc lại bằng context mới.
- Xác minh giá cũ vẫn được commit.
- Kiểm tra constraint name/SQLState nếu API cần translation.

## 64. Integration test: application error mapping

Một API test:

```text
POST /shops/7/products
Body: {"sku":"ABC-123","name":"A","price":100}

→ 201 Created

POST /shops/7/products
Body: {"sku":"ABC-123","name":"B","price":120}

→ 409 Conflict
   {"code":"SKU_ALREADY_EXISTS", ...}
```

Test này nên xác minh:

- Response không chứa raw SQL/stack trace.
- Không có duplicate row sau hai requests.
- Mã lỗi domain ổn định.
- Nếu SKU khác nhau chỉ khác case/whitespace, canonicalization policy được kiểm tra.
- Người dùng ở shop khác có được dùng cùng SKU theo rule không.
- Quyền user và tenant context đúng.
- Concurrency test riêng vẫn cần thiết; hai requests tuần tự không chứng minh race safety.

## 65. Test rollback và timing lỗi

Một transaction:

```java
em.getTransaction().begin();

em.persist(productA);
em.persist(productBWithDuplicateSku);

try {
    em.flush();
    em.getTransaction().commit();
} catch (RuntimeException failure) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
}
```

Với database transaction đúng, nếu một INSERT gây unique violation dẫn đến rollback, các INSERT trong cùng transaction phải được xử lý theo rollback semantics; không nên có “một nửa batch committed” nếu transaction thật sự đã rollback.

Cần nhớ:

- ID có thể được cấp trước rollback và để lại gap trong sequence.
- Java objects có thể giữ ID dù DB row không tồn tại.
- Callback `@PostPersist` có thể đã chạy cho một số entities trước rollback.
- Logging “saved” trước commit dễ sai.
- Nếu có external side effects, chúng cần coordination riêng.

Test nên kiểm tra database committed state bằng connection/context mới sau rollback, không dựa vào managed graph thất bại.

## 66. Dữ liệu legacy và dữ liệu nhập từ hệ thống khác

Một file CSV import có thể chứa:

```text
SKU = "  abc-123  "
NAME = ""
PRICE = -20.00
SHOP = 999 (không tồn tại)
```

Một ingestion pipeline tốt:

1. Parse input và báo lỗi định dạng theo dòng.
2. Chuẩn hóa SKU theo policy.
3. Validate fields trước khi tạo domain object.
4. Kiểm tra business context/shop quyền.
5. Xử lý batch size, transaction boundaries.
6. Để DB NOT NULL/CHECK/UNIQUE/FK làm last-line protection.
7. Ghi nhận duplicate/constraint failures với mã lỗi có thể xử lý.
8. Quyết định atomic import toàn batch hay partial success theo yêu cầu.
9. Không chỉ dựa vào HTTP controller `@Valid` vì CSV path bypass controller.
10. Dùng idempotency key để tránh tạo trùng khi retry.

Nếu import dùng JDBC batch, entity callbacks không tự chạy; nhưng database constraints vẫn nên bảo vệ.

## 67. Mô hình trạng thái lỗi và trách nhiệm xử lý

Một cách thiết kế:

```text
Validation error:
    Field/syntax → client có thể sửa input

Business rule error:
    Operation/state/permission → client cần đổi hành động
    hoặc chờ trạng thái hợp lệ

Database constraint error:
    Last-line invariant violated → application map
    đến domain error đã biết hoặc log internal failure

Concurrency conflict:
    State thay đổi giữa read và write → client reload/retry
    theo policy, không ghi đè mù

Infrastructure error:
    DB unavailable/timeout → retry/degrade theo vận hành,
    không nói sai rằng user nhập SKU trùng
```

Các loại lỗi có thể có cùng HTTP status theo API nhưng nguyên nhân vẫn phải được phân loại trong mã nguồn/observability.

Ví dụ `UNIQUE(shop_id, sku)` conflict là dữ liệu đang trùng, còn `OptimisticLockException` là xung đột phiên bản. Cả hai có thể map 409, nhưng frontend có hành động giải quyết khác: sửa SKU hoặc tải lại entity mới.

## 68. Tối ưu hiệu năng mà không giảm tính đúng

Có những validation tốn nhiều query:

```java
for (ProductDraft draft : drafts) {
    if (repository.existsByShopIdAndSku(
            shopId, draft.sku())) {
        ...
    }
}
```

Với 10.000 drafts, code có thể tạo N truy vấn tồn tại. Có thể cải thiện bằng:

- Chuẩn hóa và loại duplicate **trong batch đầu vào**.
- Query một lần lấy các SKUs đang tồn tại theo tập IDs có kiểm soát.
- Dùng batch INSERT và xử lý DB uniqueness.
- Chia transaction/batch có chủ đích.
- Sử dụng import staging table khi data lớn.
- Đo số SQL và constraint errors.
- Xác định chính sách all-or-nothing hoặc partial success.

Nhưng ngay cả khi batch pre-check nhận diện duplicates trước, **UNIQUE constraint vẫn phải tồn tại** để chống writers khác chạy đồng thời.

Đừng xóa DB constraint chỉ vì nó làm chậm import mà không thiết kế phương án integrity tương đương.

## 69. Bảng quyết định đặt một rule ở đâu

| Rule | Nên bắt đầu ở đâu? | Có nên có DB protection? |
| --- | --- | --- |
| Email có cấu trúc hợp lệ | Request/Bean Validation | Nếu DB cần format nhất quán, cân nhắc CHECK/normalized column |
| Email đã xác thực | Domain/account workflow | Có thể lưu flag/status, không thể suy chỉ từ regex |
| Email duy nhất theo tenant | Domain pre-check + canonicalization | **UNIQUE theo normalized email/tenant** |
| Giá không âm | Request + domain method | **CHECK(price >= 0), NOT NULL** |
| Không được public khi chưa approve | Domain transition | CHECK cho invariant row hiện tại nếu phù hợp |
| Chỉ admin được approve | Authorization/service | Không thay bằng CHECK đơn giản |
| Một Order có ít nhất một line khi submit | Aggregate method | Thiết kế trạng thái/locking; DB cross-row protection nếu cần |
| Không tồn kho âm | Domain reserve | CHECK + locking/atomic SQL |
| Hai booking không được overlap | Service/concurrency policy | Exclusion/guard lock/serializable/slot uniqueness tùy DB |
| Cột shop_id phải tham chiếu shop tồn tại | Service may check | **FOREIGN KEY** |
| Client update không được ghi đè bản mới | Expected-version/service | `@Version`/conditional SQL |
| Actor phải thuộc tổ chức | Security/service | Tenant scoping, DB row-level security nếu áp dụng |
| Total = sum(lines) | Aggregate/service | Trigger/generated strategy/locking nếu phải đảm bảo cross-row |
| Dữ liệu audit của mọi SQL writer | Application/event pipeline | DB trigger/CDC nếu yêu cầu bao phủ toàn bộ DB |
| Sửa lỗi thời gian hệ thống | Injected clock/domain policy | Không thể chỉ dựa vào NOT NULL |

Nên quyết định dựa trên **ngữ nghĩa và phạm vi**, không đơn thuần dựa vào công cụ team quen sử dụng.

## 70. Những lỗi thiết kế thường gặp

### Lỗi 1: Coi `@Column(nullable=false)` là request validation

Nó là mapping metadata, không tự trả field errors khi người dùng nhập null trước khi persist.

### Lỗi 2: Coi `@NotNull` là NOT NULL thật của database

Không. Bean Validation có thể không chạy ở một đường JDBC/native write.

### Lỗi 3: Coi `@Column(unique=true)` là anti-race đủ trong production

Chỉ khi DB thực sự có unique constraint đúng phạm vi; metadata không tự bảo đảm migration.

### Lỗi 4: Dùng `existsBy...` rồi bỏ UNIQUE

Hai transactions có thể cùng pass pre-check. Cần database uniqueness.

### Lỗi 5: Đưa phân quyền vào entity validator

Entity không nên phụ thuộc HTTP principal/repository context. Kiểm tra tại service/security boundary.

### Lỗi 6: Để client gửi toàn entity rồi mass-assign

Field có giá trị hợp lệ vẫn có thể không được phép chỉnh. Dùng command DTO theo operation.

### Lỗi 7: Tưởng `@Valid` tương đương JPA cascade persist

Validation cascade và persistence cascade khác nhau.

### Lỗi 8: Dùng `@PreUpdate` bảo vệ mọi native SQL

Native/bulk DML bypass per-entity callbacks. DB constraint mới bao phủ các writer trực tiếp.

### Lỗi 9: Chỉ đặt CHECK mà không đặt NOT NULL

SQL NULL có thể không bị CHECK từ chối như mong muốn.

### Lỗi 10: Unique key không bao gồm tenant

Có thể chặn sản phẩm khác shop sai phạm vi.

### Lỗi 11: Dùng default collation rồi giả định SKU case-insensitive

Cần canonicalization/index/collation đúng rule.

### Lỗi 12: Coi mọi status enum hợp lệ đồng nghĩa transition hợp lệ

CHECK status set không bảo đảm DRAFT → APPROVED → PUBLISHED.

### Lỗi 13: Coi flush thành công là commit chắc chắn

Transaction có thể rollback hoặc deferred constraint fail tại commit.

### Lỗi 14: Catch mọi PersistenceException rồi nói “trùng mã”

Làm mất phân loại lỗi, che bug/schema issues. Nhận diện constraint cụ thể.

### Lỗi 15: Sau constraint failure tiếp tục dùng cùng EntityManager/transaction

Transaction có thể rollback-only hoặc database aborted. Rollback/context mới.

### Lỗi 16: Không test external writer

JDBC batch có thể bypass HTTP/domain/Bean Validation nhưng DB constraints vẫn phải chặn sai.

### Lỗi 17: Chỉ test business logic bằng mock repository

Mock không chứng minh UNIQUE/CHECK/FK tồn tại và hoạt động.

### Lỗi 18: Chỉ test DB constraint mà không test API errors

User nhận thông báo SQL không hữu ích hoặc lộ thông tin.

### Lỗi 19: Không kiểm tra dữ liệu cũ trước migration

Thêm NOT NULL/UNIQUE có thể fail nếu legacy rows đã vi phạm.

### Lỗi 20: Quên concurrency khi kiểm tra số dư/tồn kho

Một check trên object chưa chắc giữ đúng khi transactions cạnh tranh.

### Lỗi 21: Coi database constraint thay cả authorization

DB bảo vệ row relationships, không tự biết user có quyền publish.

### Lỗi 22: Sử dụng type Java sai cho tiền

`double` có sai số biểu diễn nhị phân; dùng BigDecimal với scale/currency policy rõ khi thích hợp.

### Lỗi 23: Đặt Bean Validation null-safe không đúng

`@PositiveOrZero` có thể chấp nhận null; cần `@NotNull` nếu field bắt buộc.

### Lỗi 24: Không phân biệt Bean Validation và SQL ConstraintViolationException

Cùng tên, khác package và nguyên nhân.

### Lỗi 25: Gọi entity setter rồi khẳng định DB đã bị sửa

Managed state có thể mới dirty; SQL được phát ở flush/commit, có thể bị constraint từ chối.

## 71. Bài tập thực hành

### Bài 1: Phân loại ba quy tắc

1. SKU không được blank.
2. Chỉ admin được publish.
3. SKU duy nhất trong mỗi shop.

**Đáp án:** (1) object validation/domain value object, nên có NOT NULL/format policy ở DB; (2) authorization/domain service; (3) DB composite UNIQUE, có thể thêm pre-check thân thiện.

### Bài 2: Giá âm

```java
@PositiveOrZero
private BigDecimal price;
```

**Câu hỏi:** Field có thể null không?

**Đáp án:** Có thể, vì constraint trên thường cho phép null; thêm `@NotNull` nếu bắt buộc. DB cần NOT NULL và CHECK(price >=0) khi dữ liệu lưu bền vững không được thiếu/âm.

### Bài 3: Độ dài tên

DTO `@Size(max=200)` nhưng database là `VARCHAR(100)`.

**Câu hỏi:** Lỗi nào?

**Đáp án:** Quy tắc tầng object và DB không đồng bộ. Chuỗi dài 150 có thể pass Bean Validation nhưng DB từ chối. Cần đồng bộ contract, mapping và schema migration.

### Bài 4: Duplicate SKU

Hai requests đồng thời cùng pre-check `exists=false`.

**Câu hỏi:** Cách bảo đảm không có hai rows trùng?

**Đáp án:** UNIQUE(shop_id, sku) ở DB, xử lý exception tại flush/commit; có thể giữ pre-check để báo lỗi sớm.

### Bài 5: Publish Product

Product.status là `DRAFT`, user gửi `PUBLISHED` trực tiếp.

**Câu hỏi:** `@NotNull` trên status đủ không?

**Đáp án:** Không. Cần domain transition/authorization; DB có thể CHECK các trạng thái và quan hệ approvedAt nhưng không tự biết lịch sử transition.

### Bài 6: Sai foreign key

Request có shopId hợp dạng Long, nhưng Shop không tồn tại.

**Câu hỏi:** Validator `@NotNull` có phát hiện không?

**Đáp án:** Không. Service có thể tìm Shop để trả lỗi sớm; DB FK là bảo vệ cuối.

### Bài 7: Partial update

Endpoint chỉ cho phép đổi giá, nhưng DTO chứa `approved` và `shopId`.

**Câu hỏi:** Rủi ro?

**Đáp án:** Mass assignment; validation không quyết định quyền sửa field. Dùng ChangePriceCommand.

### Bài 8: Transaction flush

`em.persist(product)` trả về bình thường, nhưng `commit()` ném unique violation.

**Câu hỏi:** Có mâu thuẫn không?

**Đáp án:** Không. SQL/constraint check có thể xảy ra ở flush/commit, không nhất thiết khi persist.

### Bài 9: Spring exception

`org.hibernate.exception.ConstraintViolationException` xuất hiện.

**Câu hỏi:** Có phải Bean Validation `jakarta.validation.ConstraintViolationException` không?

**Đáp án:** Không. Đây thường là ORM wrapper cho DB constraint violation; phân biệt package/cause.

### Bài 10: Native SQL

Batch import dùng JDBC lưu price = -10.

**Câu hỏi:** `@PrePersist` hoặc `@Valid` ở controller có chặn không?

**Đáp án:** Không. DB CHECK là lớp bảo vệ nếu thực sự tồn tại và được enforce.

### Bài 11: Legacy data

Bảng products có nhiều SKU trùng, muốn thêm UNIQUE.

**Câu hỏi:** Nên làm gì trước migration?

**Đáp án:** Kiểm kê duplicate rows, quyết định canonicalization/cleanup, cập nhật writers và áp constraints sau khi dữ liệu hợp lệ.

### Bài 12: NULL với CHECK

DB có `CHECK(price >= 0)` nhưng không `NOT NULL`.

**Câu hỏi:** Có chắc price không thể null?

**Đáp án:** Không. SQL CHECK thường không từ chối UNKNOWN do null; cần NOT NULL.

### Bài 13: Unique không đúng phạm vi

Hai shops cần cùng SKU nhưng DB đặt UNIQUE(sku).

**Câu hỏi:** Sửa như thế nào?

**Đáp án:** Unique theo (shop_id, normalized_sku) phù hợp nghiệp vụ; xử lý dữ liệu cũ và migration.

### Bài 14: Tồn kho đồng thời

Hai transactions đọc quantity=1, đều muốn reserve(1).

**Câu hỏi:** Bean Validation requested>0 có giúp chống oversell không?

**Đáp án:** Không. Cần locking/optimistic version/atomic conditional SQL và DB CHECK.

### Bài 15: Email format

`@Email` pass.

**Câu hỏi:** Email có được xác thực hoặc unique chưa?

**Đáp án:** Chưa. Cần verification workflow và uniqueness theo normalized email/tenant nếu là requirement.

### Bài 16: DTO group

`@NotBlank(groups=OnCreate.class)` được khai báo, nhưng code chỉ validate `Default`.

**Câu hỏi:** Constraint có chắc chạy không?

**Đáp án:** Không. Cần validate đúng group hoặc group sequence đã cấu hình.

### Bài 17: Cascade validation

CustomerRequest chứa AddressRequest, nhưng không có `@Valid` trên field address.

**Câu hỏi:** Nested constraints có luôn được validate không?

**Đáp án:** Không. Cần cascaded validation được khai báo và kích hoạt phù hợp.

### Bài 18: Deferred uniqueness

Database hỗ trợ deferrable unique constraint.

**Câu hỏi:** `flush()` thành công có đủ chắc commit được không?

**Đáp án:** Không. Constraint có thể được kiểm tra tại commit.

### Bài 19: HTTP error mapping

DB trả FK violation do code tham chiếu sai shop.

**Câu hỏi:** Có nên luôn map thành 400 “SKU sai” không?

**Đáp án:** Không. Nhận diện constraint/nguồn lỗi và map đúng domain error; nếu là bug, giữ internal error và log.

### Bài 20: Data source of truth

Sau SQL constraint failure và rollback, Product Java vẫn có giá -1.

**Câu hỏi:** Có thể trả entity đó làm “Product hiện tại” không?

**Đáp án:** Không. Đọc lại từ transaction/context mới nếu cần committed state; giữ request DTO riêng cho input chưa lưu.

### Bài 21: Soft delete

Business cho phép tái sử dụng SKU sau khi Product bị soft-delete.

**Câu hỏi:** UNIQUE(shop_id, sku) còn đúng không?

**Đáp án:** Không nếu muốn reuse cùng code. Cần thiết kế partial unique/index hoặc mô hình dữ liệu khác theo DB, kèm migration.

### Bài 22: Aggregate total

Order.total phải bằng tổng OrderLines.

**Câu hỏi:** Một `@AssertTrue` trên Order đã bảo vệ mọi JDBC writer chưa?

**Đáp án:** Chưa. Đây là cross-row invariant cần transaction/model/DB strategy phù hợp; Object validation chỉ chạy khi được kích hoạt.

### Bài 23: Security

User có thể tạo Product hợp lệ nhưng gửi shopId của người khác.

**Câu hỏi:** Lớp nào giải quyết?

**Đáp án:** Authorization và tenant-scoped load trong service, không phải `@NotNull shopId` hoặc FK.

### Bài 24: Chọn test

Muốn chứng minh CHECK(price >=0) đã tồn tại trong production-like DB.

**Câu hỏi:** Nên dùng unit test cho setter hay integration test chạy SQL trực tiếp?

**Đáp án:** Integration test với schema thật và SQL bypass domain/Bean Validation.

### Bài 25: Ba lớp trong một use case

**Yêu cầu:** Thiết kế endpoint tạo Product có giá không âm, SKU unique theo shop và chỉ shop admin được tạo.

**Gợi ý:** DTO `@NotBlank`, `@PositiveOrZero`, service authorize shop admin + normalize SKU + optional duplicate pre-check, persist trong transaction; database NOT NULL/CHECK/UNIQUE/FK; catch/translate known unique violation sau flush/commit, rollback và trả error code rõ.

## 72. Checklist thiết kế kiểm tra dữ liệu trong JPA

Trước khi kết luận một invariant đã được bảo vệ:

1. Rule là field shape, state transition, authorization hay database integrity?
2. Request DTO có constraints phù hợp operation không?
3. Validator có thực sự được kích hoạt ở mọi entrypoint cần thiết không?
4. Validation groups có chạy đúng `Default`/create/update group không?
5. Nested DTO có `@Valid` phù hợp không?
6. Object validation có null-safe và đúng kiểu dữ liệu không?
7. SKU/email có được chuẩn hóa thống nhất trước uniqueness check không?
8. Domain method có từ chối state transition không hợp lệ không?
9. Application service có xác minh quyền/tenant ở trusted context không?
10. Có điều kiện cross-entity nào cần transaction/locking không?
11. Rule có chịu concurrency giữa read và write không?
12. `existsBy...` có được hỗ trợ bằng DB UNIQUE thật không?
13. Entity mapping và migration schema thực tế có khớp không?
14. DB có NOT NULL cho required columns không?
15. Có CHECK cho những giá trị không thể chấp nhận không?
16. Có composite UNIQUE theo đúng scope business không?
17. Có FOREIGN KEY cho reference integrity không?
18. Có xét NULL/collation/normalization semantics của DB không?
19. Có writer nào dùng JDBC/native/bulk SQL và bypass JPA validation không?
20. Có `@Version`/lock/atomic SQL cho update cạnh tranh không?
21. SQL errors có thể xuất hiện ở flush hay commit không?
22. Có xử lý cả exceptions được transaction manager bọc không?
23. Có phân biệt Bean Validation ConstraintViolation và DB constraint violation không?
24. Có map lỗi DB theo constraint name/type thay vì raw message không?
25. Transaction lỗi có rollback, context mới nếu retry không?
26. API có phân biệt validation/business/concurrency/infrastructure errors không?
27. Có tránh mass assignment và overposting không?
28. Có test domain object mà không cần DB khi thích hợp không?
29. Có integration test constraints trên DB thật không?
30. Có concurrency test chứng minh duplicate/oversell không xảy ra không?
31. Có migration data cleanup trước khi thêm constraints không?
32. Có test legacy/import/batch writers không?
33. Có audit/tracing đủ để phát hiện constraint violations lặp lại không?
34. Có không gửi event bên ngoài trước commit nếu cần tính nhất quán không?
35. Có phân biệt trạng thái Java object và dữ liệu đã commit sau rollback không?

Checklist này không nhằm đưa mọi validation vào nhiều nơi một cách máy móc. Mục tiêu là **định rõ ai chịu trách nhiệm về giá trị, nghiệp vụ, tính bền vững và concurrent correctness**.

## Kết luận

**Kiểm tra đối tượng, quy tắc nghiệp vụ và ràng buộc cơ sở dữ liệu là ba lớp bảo vệ khác nhau trong ứng dụng JPA.**

- **Object validation** (điển hình Jakarta Bean Validation) kiểm tra hình dạng và điều kiện cục bộ của DTO/entity: nullability, độ dài, định dạng, số âm, cross-field constraints. Nó giúp phát hiện lỗi sớm và trả field errors rõ ràng, nhưng chỉ hoạt động khi được kích hoạt.
- **Business/domain validation** xác định hành động có được phép trong bối cảnh hiện tại không: authorization, tenant scope, state transitions, quota, tồn kho hoặc các điều kiện phụ thuộc nhiều entities. Nó thuộc domain methods và application services, đi cùng transaction và concurrency policy.
- **Database constraints** (NOT NULL, CHECK, UNIQUE, FK, PK và các cơ chế nâng cao) bảo vệ trạng thái lưu bền vững kể cả khi một SQL writer bỏ qua JPA hoặc Bean Validation. Chúng giữ hàng rào cuối, nhưng không tự thay thế thông báo nghiệp vụ thân thiện hay quy trình phân quyền.

Điểm khó nhất thường không phải viết annotation mà là **xử lý concurrency và thời điểm báo lỗi**. Một pre-check `existsBy...` có thể pass ở hai requests đồng thời; chỉ một UNIQUE constraint thực tế mới có thể chặn hai committed duplicates. Bean Validation có thể báo lỗi tại API boundary hoặc JPA flush, còn database constraint có thể thất bại tại SQL execution hoặc commit. Cần rollback, nhận diện exception theo type/cause, map lỗi có chọn lọc và không tiếp tục dùng persistence context đã thất bại.

Khi thiết kế một rule, hãy tự hỏi: **“Rule này nói về một giá trị, một hành động, hay trạng thái lưu trữ? Nó có phải đúng khi JDBC/native SQL ghi dữ liệu không? Nó có thể bị vi phạm giữa hai transaction chạy đồng thời không? Và nếu DB từ chối ở commit, API sẽ trả lỗi nào?”**. Trả lời rõ bốn câu hỏi đó giúp các tầng JPA, domain và database phối hợp đúng trách nhiệm: **ngăn lỗi sớm, diễn đạt nghiệp vụ rõ và không để dữ liệu không hợp lệ được commit**.

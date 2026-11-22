# `@Column`, tên cột và các tùy chọn ánh xạ cơ bản

## 1. `@Column` giải quyết vấn đề gì?

Trong ứng dụng Java sử dụng cơ sở dữ liệu quan hệ, một **entity** thường biểu diễn một hàng của bảng và các thuộc tính của entity biểu diễn dữ liệu cần lưu vào cột. Jakarta Persistence (thường vẫn gọi là JPA) cho phép khai báo ánh xạ đó bằng annotation. **`@Column`** là annotation chuẩn trong gói `jakarta.persistence`, dùng để tùy chỉnh ánh xạ của một thuộc tính cơ bản (*basic attribute*) đến một cột cơ sở dữ liệu.

Ví dụ, entity có thuộc tính Java `unitPrice` nhưng database đặt tên cột là `unit_price`:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "unit_price")
    private BigDecimal unitPrice;

    protected Product() {}
}
```

Trong ví dụ:

- `Product` là tên entity mặc định dùng trong JPQL.
- `products` là tên bảng được khai báo với `@Table`.
- `unitPrice` là tên thuộc tính Java.
- `unit_price` là tên cột trong bảng `products`.
- Hibernate ORM có thể đóng vai trò **persistence provider**: đọc các annotation của Jakarta Persistence, tạo ánh xạ và phát sinh SQL để lưu, đọc dữ liệu.

Khi viết JPQL, lập trình viên sử dụng **tên thuộc tính Java**:

```java
List<Product> products = entityManager.createQuery(
        "select p from Product p where p.unitPrice >= :minimum",
        Product.class)
    .setParameter("minimum", new BigDecimal("100.00"))
    .getResultList();
```

Hibernate sau đó có thể phát sinh SQL có ý nghĩa tương đương:

```sql
SELECT p.id, p.unit_price
FROM products p
WHERE p.unit_price >= ?;
```

SQL trên chỉ minh họa; tên alias, danh sách cột và cú pháp cụ thể phụ thuộc phiên bản Hibernate, dialect và truy vấn.

**Lưu ý quan trọng:** không phải thuộc tính nào của entity cũng bắt buộc có `@Column`. Với các trường cơ bản, JPA đã có quy tắc ánh xạ mặc định. Chỉ thêm `@Column` khi muốn cấu hình rõ tên cột hoặc các đặc tính như `nullable`, `length`, `precision`, `scale`, `insertable`, `updatable`.

## 2. Phân biệt `@Entity`, `@Table`, `@Id` và `@Column`

Bốn annotation thường xuất hiện cạnh nhau nhưng có phạm vi khác nhau:

| Annotation | Đặt trên | Chức năng chính |
|---|---|---|
| `@Entity` | Lớp | Đánh dấu lớp được quản lý như một thực thể JPA |
| `@Table(name = "...")` | Lớp | Chỉ định bảng chính và một số ràng buộc cấp bảng |
| `@Id` | Field hoặc getter | Chỉ định khóa định danh của entity |
| `@Column(name = "...")` | Field hoặc getter được ánh xạ | Cấu hình cột dành cho một thuộc tính cơ bản |

Hãy hình dung ánh xạ như sau:

```text
Java                                 Database
--------------------------------    ----------------------
@Entity Product                      Bảng products
  id: Long             ----------->    id (khóa chính)
  sku: String          ----------->    product_sku
  unitPrice: BigDecimal ----------->    unit_price
  quantity: int        ----------->    quantity

@Table(name = "products")
@Column(name = "product_sku")    dùng với thuộc tính sku
@Column(name = "unit_price")     dùng với thuộc tính unitPrice
```

`@Column` không biến một lớp thông thường thành entity và không tự tạo định danh. Ngược lại, `@Entity` cũng không buộc phải khai báo `@Column` cho từng field. Những thuộc tính không lưu xuống database cần được xử lý theo quy tắc của JPA, chẳng hạn đánh dấu `@Transient`.

## 3. Ví dụ đầy đủ: entity `InventoryItem`

Xét hệ thống quản lý hàng tồn kho. Database có bảng `inventory_items` với SKU, tên sản phẩm, giá tiền, số lượng, trạng thái và ghi chú.

```java
package example.inventory;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "inventory_items")
public class InventoryItem {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "sku", nullable = false, unique = true, length = 40)
    private String sku;

    @Column(name = "display_name", nullable = false, length = 160)
    private String displayName;

    @Column(name = "unit_price", nullable = false, precision = 12, scale = 2)
    private BigDecimal unitPrice;

    @Column(name = "quantity_on_hand", nullable = false)
    private Integer quantityOnHand;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 20)
    private ItemStatus status;

    @Column(name = "internal_note", length = 1000)
    private String internalNote;

    protected InventoryItem() { // Constructor bắt buộc cho JPA
    }

    public InventoryItem(String sku, String displayName,
                         BigDecimal unitPrice, Integer quantityOnHand) {
        this.sku = sku;
        this.displayName = displayName;
        this.unitPrice = unitPrice;
        this.quantityOnHand = quantityOnHand;
        this.status = ItemStatus.ACTIVE;
    }

    public enum ItemStatus { ACTIVE, INACTIVE }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public String getDisplayName() { return displayName; }
    public BigDecimal getUnitPrice() { return unitPrice; }
    public Integer getQuantityOnHand() { return quantityOnHand; }
    public ItemStatus getStatus() { return status; }
    public String getInternalNote() { return internalNote; }

    public void setUnitPrice(BigDecimal unitPrice) {
        this.unitPrice = unitPrice;
    }

    public void setInternalNote(String internalNote) {
        this.internalNote = internalNote;
    }
}
```

Lược đồ SQL **tham khảo** có thể tương tự:

```sql
CREATE TABLE inventory_items (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    display_name VARCHAR(160) NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    quantity_on_hand INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    internal_note VARCHAR(1000)
);
```

Đoạn DDL trên mô tả ý định ánh xạ, **không cam kết** Hibernate ở mọi database sẽ tạo đúng từng từ khóa SQL. Chẳng hạn, kiểu identity, tên constraint, kiểu `VARCHAR` và cách biểu diễn enum có thể khác tùy dialect và phiên bản. Trong dự án production, thường tạo hoặc thay đổi bảng bằng migration có kiểm soát, rồi cấu hình ORM khớp với schema đó.

Ví dụ này thể hiện nhiều công dụng của `@Column`:

- `name`: tên cột thực tế.
- `nullable = false`: mong muốn cột không nhận `NULL` trong DDL.
- `unique = true`: khai báo tính duy nhất của một cột khi sinh schema.
- `length`: độ dài gợi ý cho kiểu chuỗi.
- `precision`, `scale`: độ chính xác và số chữ số thập phân của kiểu số thập phân.

`@Enumerated(EnumType.STRING)` chịu trách nhiệm cách chuyển enum sang dữ liệu cột; `@Column` chỉ quy định các thuộc tính của cột tương ứng. Hai annotation có thể kết hợp vì chúng giải quyết hai khía cạnh khác nhau của ánh xạ.

## 4. Những thuộc tính thường dùng của `@Column`

`@Column` là annotation chuẩn. Các thuộc tính cơ bản sau xuất hiện trong nhiều phiên bản Jakarta Persistence/JPA:

| Thuộc tính | Giá trị mặc định | Tác dụng |
|---|---|---|
| `name` | `""` | Tên cột; để trống sẽ áp dụng quy tắc đặt tên ngầm định của provider và naming strategy |
| `nullable` | `true` | Cột được phép chứa `NULL` ở mức metadata sinh DDL |
| `unique` | `false` | Yêu cầu ràng buộc duy nhất của cột khi sinh DDL |
| `length` | `255` | Độ dài dự kiến đối với cột chuỗi; ảnh hưởng schema theo provider/dialect |
| `precision` | `0` | Tổng số chữ số thập phân; `0` nghĩa là không chỉ định cụ thể |
| `scale` | `0` | Số chữ số sau dấu thập phân; cần xem cùng `precision` và kiểu dữ liệu |
| `insertable` | `true` | Có đưa cột này vào SQL `INSERT` do ORM tạo cho thuộc tính đó hay không |
| `updatable` | `true` | Có đưa cột này vào SQL `UPDATE` do ORM tạo cho thuộc tính đó hay không |
| `columnDefinition` | `""` | Định nghĩa cột theo SQL riêng dùng trong DDL, khi thực sự cần |
| `table` | `""` | Bảng chứa cột; để trống là bảng chính của entity |

Các phiên bản Jakarta Persistence mới có thể bổ sung phần tử cấu hình khác. Khi sử dụng một phần tử ít phổ biến, hãy kiểm tra đúng Javadoc của **phiên bản Jakarta Persistence mà dự án đang phụ thuộc**, bởi khả năng Hibernate hiểu một phần tử còn liên quan đến phiên bản Hibernate.

Điều đặc biệt dễ nhầm là bảng này diễn tả **metadata ánh xạ**. Nó không có nghĩa mọi thuộc tính đều là bộ kiểm tra dữ liệu Java lúc runtime. Hibernate diễn giải metadata để sinh SQL và, khi được bật, sinh hoặc kiểm tra schema. Database là nơi cuối cùng thực thi các ràng buộc đã được tạo thực tế.

## 5. Đặt tên cột: mặc định, tường minh và naming strategy

### 5.1. Tên cột mặc định

Nếu bỏ `@Column`, một thuộc tính cơ bản vẫn có thể được ánh xạ:

```java
@Entity
public class Customer {
    @Id
    private Long id;

    private String email;
    private String displayName;

    protected Customer() {}
}
```

Ở mức quy tắc ngầm định, tên cột thường bắt nguồn từ tên thuộc tính (`email`, `displayName`). Tuy nhiên, **tên vật lý cuối cùng** có thể chịu tác động của cấu hình naming strategy. Ví dụ, một ứng dụng cấu hình Hibernate để đổi `displayName` thành `display_name`, nhưng không thể mặc định mọi ứng dụng JPA hoặc mọi cấu hình Spring/Hibernate đều làm như vậy.

Hibernate phân biệt hai bước khái niệm:

1. **Implicit naming:** đề xuất tên khi không có tên tường minh trong annotation.
2. **Physical naming:** chuyển tên logic sang tên đối tượng SQL thực tế theo chính sách đặt tên của ứng dụng.

Ngay cả khi ghi `@Column(name = "display_name")`, một `PhysicalNamingStrategy` tùy chỉnh vẫn có thể xử lý định danh đó. Vì vậy, muốn biết câu SQL thật sự, cần xem cấu hình provider, schema và SQL được phát sinh. Một khi nhóm đã có quy ước đặt tên thống nhất, nên dùng quy ước ổn định thay vì kết hợp ngẫu nhiên tên tự suy luận và tên tường minh.

### 5.2. Khai báo tên tường minh

```java
@Column(name = "customer_email")
private String email;

@Column(name = "created_at")
private java.time.Instant createdAt;
```

Thuộc tính Java vẫn là `email` và `createdAt`. Nếu đổi tên cột trong DB mà không cập nhật mapping hoặc migration tương ứng, ứng dụng có thể gặp lỗi kiểu “column not found”. Ngược lại, chỉ thay `name` trong annotation **không tự đổi tên cột hiện có** khi ứng dụng chạy với schema đã được quản lý bằng migration.

### 5.3. Tên cột trùng từ khóa SQL

Ví dụ cột tên `order` hoặc `user` có thể xung đột với từ khóa hay quy tắc riêng của hệ quản trị cơ sở dữ liệu. Nên ưu tiên một tên rõ ràng như `sort_order`, `user_name` thay vì phụ thuộc vào việc escape/quote tên cột.

Nếu buộc phải dùng identifier cần quote, JPA/Hibernate có khả năng làm việc với định danh được quote, nhưng cú pháp và quy tắc chữ hoa/chữ thường có thể khác theo dialect. Hibernate có hỗ trợ các cơ chế đặt quote cho tên định danh; **không** nên tự nối dấu quote trực tiếp vào mọi tên cột rồi hy vọng tương thích mọi database. Ví dụ, identifier được quote của PostgreSQL có thể phân biệt chữ hoa/chữ thường, trong khi identifier không quote thường được chuẩn hóa.

### 5.4. `name` không xác định bảng

`@Column(name = "street")` chỉ xác định cột. Bảng chính thường do `@Table(name = "customers")` chỉ định. Nếu thuộc tính nằm trong bảng phụ được khai báo bằng `@SecondaryTable`, dùng `@Column(table = "...")`; không thể tự đổi tên bảng chỉ bằng `name`.

## 6. `nullable` và `unique`: metadata ràng buộc dữ liệu

### 6.1. `nullable = false`

```java
@Column(name = "full_name", nullable = false, length = 100)
private String fullName;
```

Khi Hibernate được dùng để sinh DDL, cấu hình này thường dẫn đến một cột `NOT NULL`. Nhưng cần phân biệt:

- **Ở Java:** biến `fullName` vẫn có thể nhận `null` nếu code gán như vậy.
- **Ở ORM:** Hibernate có thể phát hiện một số vi phạm nullability trong quá trình đồng bộ, tùy mapping và cấu hình, nhưng không nên xem đây là bộ xác thực dữ liệu đầu vào đầy đủ.
- **Ở database:** `NOT NULL` chỉ được bảo đảm nếu ràng buộc đó thực sự tồn tại trong schema đang chạy.

Nếu muốn kiểm tra dữ liệu ở ranh giới ứng dụng, có thể kết hợp Bean Validation:

```java
import jakarta.validation.constraints.NotBlank;

@NotBlank
@Column(name = "full_name", nullable = false, length = 100)
private String fullName;
```

`@NotBlank` phục vụ **validation** chuỗi, còn `nullable = false` diễn tả quy tắc cho cột. Bean Validation yêu cầu dependency/provider phù hợp và được gọi hoặc tích hợp vào luồng xử lý. Với những bất biến nghiệp vụ quan trọng, vẫn cần kiểm tra ở tầng domain/service và giữ constraint ở DB.

Đối với kiểu nguyên thủy như `int` hoặc `boolean`, biến Java không nhận `null`, nhưng điều đó không tự tạo constraint cho mọi schema đã tồn tại. Với kiểu wrapper như `Integer`, `Boolean`, dữ liệu `null` vẫn có thể được biểu diễn và cần quyết định rõ có cho phép hay không.

### 6.2. `unique = true`

```java
@Column(name = "sku", nullable = false, unique = true, length = 40)
private String sku;
```

Tùy cấu hình schema generation và dialect, Hibernate có thể tạo unique constraint/index tương ứng. Nhưng `unique = true` **không thay thế** thao tác tạo constraint trong migration của schema đang được quản lý độc lập.

Ngay cả khi service đã kiểm tra “SKU này chưa tồn tại”, hai transaction đồng thời vẫn có thể vượt qua bước kiểm tra đó. Ràng buộc duy nhất tại DB mới là lớp bảo vệ cuối cùng; ứng dụng phải xử lý lỗi vi phạm constraint và phản hồi phù hợp.

Hành vi của `UNIQUE` đối với giá trị `NULL`, collation, chữ hoa/chữ thường và index có thể khác theo database. Nếu muốn SKU không được null, hãy khai báo riêng `nullable = false` và tạo constraint tương ứng.

### 6.3. Ràng buộc unique trên **nhiều cột**

`@Column(unique = true)` chỉ diễn đạt tính duy nhất của **một cột**. Nếu SKU chỉ cần duy nhất trong từng kho hàng, phải dùng constraint kết hợp:

```java
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

@Entity
@Table(
    name = "inventory_items",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_inventory_warehouse_sku",
        columnNames = { "warehouse_id", "sku" }
    )
)
public class InventoryItem {
    @Id
    private Long id;

    @Column(name = "warehouse_id", nullable = false)
    private Long warehouseId;

    @Column(name = "sku", nullable = false, length = 40)
    private String sku;

    protected InventoryItem() {}
}
```

Trong ví dụ này **không** thêm `unique = true` cho riêng `sku`, vì làm vậy sẽ cấm trùng SKU giữa các kho, khác yêu cầu nghiệp vụ. Tên trong `columnNames` là tên các cột theo mapping, không phải tên getter/field Java. Tên constraint tường minh cũng giúp migration và việc tìm lỗi DB dễ quản lý hơn.

## 7. `length`, `precision`, `scale`: kích thước và độ chính xác

### 7.1. `length` cho chuỗi

```java
@Column(name = "title", nullable = false, length = 150)
private String title;

@Column(name = "description", length = 2000)
private String description;
```

`length` thường ảnh hưởng đến độ dài của cột dạng ký tự trong DDL, ví dụ `VARCHAR(150)`. Giá trị mặc định của `length` là `255`, nhưng kiểu SQL thực tế do provider và dialect lựa chọn. Nó không có nghĩa Hibernate tự động cắt chuỗi quá dài hoặc tự kiểm tra mọi phép gán Java.

Nếu đầu vào phải có tối đa 150 ký tự, có thể dùng `@Size(max = 150)` từ Jakarta Validation trong luồng validation, đồng thời đặt độ dài cột thực tế phù hợp. Với chuỗi rất dài, cân nhắc kiểu lưu trữ thích hợp (`@Lob`, kiểu `TEXT` của DB hoặc chiến lược khác), chứ không tùy tiện đặt `length` cực lớn rồi mặc định mọi database sẽ xử lý giống nhau.

### 7.2. `precision` và `scale` cho số thập phân

```java
@Column(name = "unit_price", precision = 12, scale = 2, nullable = false)
private BigDecimal unitPrice;
```

`precision` là **tổng số chữ số có nghĩa** được phép lưu theo kiểu SQL thập phân. `scale` là **số chữ số ở phần thập phân**. Với `DECIMAL(12,2)`, tối đa 12 chữ số, trong đó 2 chữ số sau dấu thập phân; về mặt định dạng có thể chứa 10 chữ số ở phần nguyên và 2 chữ số phần lẻ, còn giới hạn chính xác phụ thuộc DB và giá trị dấu.

Một số ví dụ:

| Giá trị | Với `DECIMAL(6,2)` | Giải thích |
|---|---|---|
| `1234.56` | Trong phạm vi | 4 chữ số trước dấu, 2 chữ số sau dấu |
| `9999.99` | Trong phạm vi | Giá trị dương lớn nhất với 4 chữ số phần nguyên |
| `10000.00` | Vượt phạm vi | Có 5 chữ số phần nguyên |
| `12.345` | Cần làm tròn/từ chối theo DB và cấu hình | Có 3 chữ số phần lẻ trong khi scale là 2 |

Trong Java, nên dùng `BigDecimal` cho tiền hoặc đại lượng cần tính toán thập phân chính xác:

```java
BigDecimal price = new BigDecimal("1234.56");
```

Tránh dùng `new BigDecimal(0.1)` vì số thực nhị phân `double` không biểu diễn chính xác hầu hết phân số thập phân. `precision` và `scale` trên `@Column` **không tự thay thế** quy tắc làm tròn tiền trong domain model; hãy chọn `RoundingMode` và chính sách tiền tệ rõ ràng ở tầng nghiệp vụ.

### 7.3. Kiểu Java ảnh hưởng đến kiểu SQL

`@Column(length = 20)` không tự biến mọi kiểu Java thành `VARCHAR(20)`. Hibernate còn dựa vào kiểu Java, converter, mapping JDBC và dialect để xác định kiểu SQL. Chẳng hạn:

- `String` thường dẫn đến kiểu chuỗi; `length` có ý nghĩa trực tiếp.
- `BigDecimal` thường gắn với kiểu `DECIMAL`/`NUMERIC`; `precision`, `scale` là các tham số quan trọng.
- `Integer`, `Long`, `Boolean`, `LocalDate` và `Instant` có các mapping kiểu riêng; một số cần cân nhắc tính tương thích thời gian/time zone và dialect.
- `enum` cần định rõ phương thức biểu diễn khi nghiệp vụ yêu cầu; `@Enumerated(EnumType.STRING)` thường dễ bảo trì hơn cách lưu thứ tự ordinal nếu danh sách enum có thể thay đổi.

Không nên dùng `columnDefinition` chỉ để ép kiểu khi Hibernate đã có mapping chuẩn phù hợp. Việc lựa chọn kiểu cột phải thống nhất với schema và nhu cầu truy vấn thực tế.

## 8. `insertable` và `updatable`: cột có tham gia SQL ghi hay không?

Hai thuộc tính này thường gây nhầm lẫn vì nghe giống như “quyền sửa dữ liệu”. Thực chất, chúng điều khiển **việc provider có đưa cột tương ứng vào các câu `INSERT`/`UPDATE` do ORM sinh ra cho mapping đó**.

### 8.1. `insertable = false`

```java
@Column(name = "created_at", insertable = false, updatable = false)
private java.time.Instant createdAt;
```

Ở mapping này, Hibernate không dùng giá trị `createdAt` của entity để ghi cột khi insert/update. Đây có thể là lựa chọn phù hợp khi database có default hoặc trigger quản lý giá trị:

```sql
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
```

Tuy nhiên, khai báo `insertable = false` **không tự tạo** `DEFAULT CURRENT_TIMESTAMP`. Nếu cột không có default và đang `NOT NULL`, `INSERT` có thể thất bại. Ngược lại, nếu DB sinh giá trị, object Java có thể chưa được cập nhật ngay; có thể cần `refresh()` hoặc cơ chế đọc lại giá trị sinh từ DB được provider hỗ trợ.

### 8.2. `updatable = false`

```java
@Column(name = "external_reference", updatable = false, length = 64)
private String externalReference;
```

Trường `externalReference` có thể được điền khi `INSERT`, nhưng Hibernate sẽ không đưa cột đó vào SQL `UPDATE` của entity khi giá trị thay đổi về sau. Điều này **không** làm field Java trở thành `final` hay tự ngăn code gọi setter. Cũng không bảo đảm một actor khác không thể sửa trực tiếp giá trị trong database.

### 8.3. Bảng hành vi

| Mapping | Khi ORM `INSERT` | Khi ORM `UPDATE` |
|---|---|---|
| Mặc định `true/true` | Cột có thể tham gia `INSERT` | Cột có thể tham gia `UPDATE` |
| `false/true` | Không tham gia `INSERT` qua mapping này | Có thể tham gia `UPDATE` |
| `true/false` | Có thể tham gia `INSERT` | Không tham gia `UPDATE` qua mapping này |
| `false/false` | Không tham gia `INSERT` qua mapping này | Không tham gia `UPDATE` qua mapping này |

Ví dụ `false/false` thường dùng cho dữ liệu DB tự sinh hoặc một thuộc tính chỉ đọc từ cùng cột đã được ánh xạ có quyền ghi bằng một thuộc tính khác. Trong trường hợp cùng cột được ánh xạ nhiều lần, Hibernate cần xác định rõ mapping nào chịu trách nhiệm ghi, tránh lỗi “repeated column mapping”.

**Không dùng `updatable = false` làm cơ chế phân quyền.** Giới hạn nào là quy tắc nghiệp vụ cần được kiểm tra ở service/domain; giới hạn nào cần chống sửa từ mọi phía phải được bảo vệ thêm bằng quyền truy cập hoặc chính sách tại database.

## 9. `columnDefinition`: chủ động định nghĩa SQL, chấp nhận phụ thuộc database

Thông thường nên để Hibernate chọn kiểu cột phù hợp từ kiểu Java, các thuộc tính `length`/`precision`/`scale` và dialect. Khi DDL cần một khai báo SQL cụ thể, `columnDefinition` cung cấp lối thoát:

```java
@Column(
    name = "order_state",
    nullable = false,
    columnDefinition = "varchar(20) default 'NEW'"
)
private String orderState;
```

Định nghĩa trên là một đoạn SQL định nghĩa cột do ứng dụng cung cấp. Hỗ trợ và ý nghĩa của nó tùy database; ví dụ `varchar(20)` và `default` phổ biến nhưng nhiều cú pháp đặc biệt khác sẽ không portable.

Các lưu ý quan trọng:

1. `columnDefinition` chủ yếu liên quan đến **DDL khi sinh schema**, không phải một bộ chuyển đổi giá trị Java.
2. Default của DB chỉ phát huy khi cột được bỏ qua trong `INSERT` hoặc có logic SQL/DB phù hợp. Nếu ORM gửi `NULL` tường minh vào cột, default có thể không được áp dụng.
3. Với schema do Flyway/Liquibase hay đội DBA quản lý, thay annotation không đồng nghĩa đã cập nhật bảng trong DB; phải tạo migration tương ứng.
4. Khác biệt cú pháp giữa PostgreSQL, MySQL, Oracle, SQL Server, H2... có thể làm ứng dụng không khởi tạo schema được hoặc tạo schema khác mong đợi.
5. Nếu mục tiêu là giá trị mặc định nghiệp vụ, thường dễ kiểm soát hơn khi khởi tạo trong constructor/service và có constraint DB nhất quán, thay vì chỉ phụ thuộc DDL default.

Hibernate còn có annotation riêng như `@ColumnDefault` để thể hiện default trong DDL ở một số trường hợp. Nó thuộc `org.hibernate.annotations`, **không thuộc Jakarta Persistence**. Dùng extension này khi đội phát triển chấp nhận phụ thuộc Hibernate và hiểu rõ khác biệt giữa default của database với giá trị của object trong bộ nhớ.

## 10. `table`: cột thuộc bảng chính hay bảng phụ?

Phần lớn entity chỉ ánh xạ một bảng, nên `@Column(table = "")` mặc định trỏ về bảng chính. Một entity đôi khi trải qua nhiều bảng, ví dụ bảng `customers` chứa dữ liệu cốt lõi, còn `customer_profiles` chứa thông tin mở rộng.

Khi đó, `@SecondaryTable` khai báo bảng phụ và `@Column(table = "customer_profiles")` xác định cột nằm ở đó:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PrimaryKeyJoinColumn;
import jakarta.persistence.SecondaryTable;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
@SecondaryTable(
    name = "customer_profiles",
    pkJoinColumns = @PrimaryKeyJoinColumn(
        name = "customer_id", referencedColumnName = "id"
    )
)
public class Customer {
    @Id
    private Long id;

    @Column(name = "email", nullable = false)
    private String email;

    @Column(table = "customer_profiles", name = "biography", length = 500)
    private String biography;

    protected Customer() {}
}
```

`Customer` vẫn là một entity, nhưng hai nhóm cột nằm trong hai bảng được liên kết bằng khóa chính theo quy tắc `@SecondaryTable`. `table` trong `@Column` phải tham chiếu đến một bảng đã được khai báo phù hợp, **không** tự tạo một quan hệ `@OneToOne` mới.

Nếu muốn lưu các đối tượng có vòng đời và khóa định danh riêng, việc khai báo quan hệ giữa hai entity bằng `@OneToOne`/`@ManyToOne` có thể là mô hình đúng hơn việc trải một entity lên nhiều bảng. Chọn mapping dựa trên mô hình dữ liệu và nhu cầu truy vấn.

## 11. Khi nào dùng `@Column`, `@JoinColumn`, `@AttributeOverride`?

Điểm chung là các annotation này đều nói về cột, nhưng chúng phục vụ những loại ánh xạ khác nhau.

| Trường hợp | Annotation thường dùng | Giải thích |
|---|---|---|
| Thuộc tính cơ bản `String`, `BigDecimal`, `Integer`, `LocalDate` | `@Column` | Cấu hình cột chứa giá trị của thuộc tính |
| Khóa ngoại của quan hệ `@ManyToOne`, `@OneToOne` | `@JoinColumn` | Cấu hình cột liên kết và cột được tham chiếu |
| Thuộc tính nằm trong `@Embedded` và cần đổi tên cột | `@AttributeOverride` kết hợp `@Column` | Ghi đè mapping của thuộc tính bên trong embeddable |
| Thuộc tính không cần lưu | `@Transient` | Loại khỏi mapping persistence |
| Trường tính toán trong Java, không lưu | Getter tính toán hoặc `@Transient` | Không cần một cột riêng |

### 11.1. Khóa ngoại dùng `@JoinColumn`

Ví dụ đơn hàng tham chiếu khách hàng:

```java
@Entity
@Table(name = "orders")
public class Order {
    @Id
    private Long id;

    @jakarta.persistence.ManyToOne
    @jakarta.persistence.JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected Order() {}
}
```

Ở đây `customer` là **quan hệ đến entity khác**, vì thế dùng `@JoinColumn` để chỉ cột khóa ngoại. `@Column(name = "customer_id")` trên cùng thuộc tính quan hệ không có cùng ý nghĩa và thường là sai cách khai báo.

### 11.2. Embedded object dùng `@AttributeOverride`

Giả sử địa chỉ được tái sử dụng ở nhiều nơi:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;

@Embeddable
public class Address {
    @Column(name = "street", length = 150)
    private String street;

    @Column(name = "postal_code", length = 12)
    private String postalCode;

    protected Address() {}
}
```

Nếu entity cần đổi tên cột theo vai trò của địa chỉ:

```java
@jakarta.persistence.Embedded
@jakarta.persistence.AttributeOverrides({
    @jakarta.persistence.AttributeOverride(
        name = "street",
        column = @Column(name = "shipping_street", length = 150)
    ),
    @jakarta.persistence.AttributeOverride(
        name = "postalCode",
        column = @Column(name = "shipping_postal_code", length = 12)
    )
})
private Address shippingAddress;
```

`name` của `@AttributeOverride` là **tên thuộc tính trong `Address`** (`street`, `postalCode`), còn `name` của `@Column` là **tên cột SQL**. Phân biệt hai tầng tên này giúp tránh lỗi mapping rất phổ biến khi đổi tên hoặc tái sử dụng embeddable.

### 11.3. Thuộc tính không lưu và thuộc tính dẫn xuất

```java
@Column(name = "unit_price", precision = 12, scale = 2)
private BigDecimal unitPrice;

@Column(name = "quantity")
private int quantity;

@jakarta.persistence.Transient
public BigDecimal getTotalValue() {
    return unitPrice.multiply(BigDecimal.valueOf(quantity));
}
```

Với ví dụ này, entity dùng **field access** vì `@Id` đặt trên field trong class đầy đủ. Getter tính toán không được xem là persistent field. Đánh dấu `@Transient` trên getter vẫn giúp truyền đạt ý định rõ ràng. Nếu muốn giá trị tính toán thật sự là cột database hoặc expression do SQL tính, cần chọn mapping khác, không đơn giản đặt `@Column` lên mọi getter.

## 12. Vị trí đặt annotation và chiến lược truy cập thuộc tính

JPA hỗ trợ hai chiến lược phổ biến:

- **Field access:** annotation định danh (`@Id`) đặt trên field; provider đọc và ghi trạng thái qua field.
- **Property access:** annotation định danh đặt trên getter JavaBeans; provider thao tác qua getter/setter.

Ví dụ field access:

```java
@Entity
public class Category {
    @Id
    private Long id;

    @Column(name = "category_name", length = 100)
    private String name;

    protected Category() {}
}
```

Ví dụ property access:

```java
@Entity
public class Supplier {
    private Long id;
    private String name;

    protected Supplier() {}

    @Id
    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }

    @Column(name = "supplier_name", length = 100)
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
}
```

Vị trí đặt `@Column` phải nhất quán với access strategy áp dụng. Đặt `@Id` trên field nhưng đặt `@Column` ở getter rồi mong Hibernate luôn đọc annotation getter có thể dẫn đến cấu hình không được áp dụng như kỳ vọng. Nếu thật sự cần phối hợp hai chiến lược, Jakarta Persistence có `@Access` để chỉ rõ phạm vi áp dụng; không trộn ngẫu nhiên.

Ngoài ra:

- `static` field không đại diện trạng thái của từng entity.
- Java `transient` và JPA `@Transient` có tác dụng khác nhau trong các hệ thống Java nói chung; cần hiểu mục đích trước khi sử dụng.
- Getter/setter không thay thế yêu cầu về constructor và mapping hợp lệ của entity.
- Một entity dùng Lombok hoặc record cần được thiết kế cẩn thận theo các yêu cầu của JPA; không xem việc có annotation `@Column` là đủ để provider quản lý mọi kiểu class.

## 13. `@Column` trong vòng đời ghi và đọc của Hibernate

Xét entity `InventoryItem` có `sku`, `unitPrice` và `internalNote`:

```java
entityManager.getTransaction().begin();

InventoryItem item = new InventoryItem(
    "JAVA-BOOK-01", "Java Persistence Guide",
    new BigDecimal("249.00"), 25
);
entityManager.persist(item);

entityManager.getTransaction().commit();
```

Hibernate đọc metadata `@Column` để biết cách đưa các giá trị vào `INSERT` phù hợp. Với entity còn đang được quản lý, những thay đổi tiếp theo có thể được phát hiện bởi cơ chế dirty checking:

```java
entityManager.getTransaction().begin();

InventoryItem managed = entityManager.find(InventoryItem.class, itemId);
managed.setUnitPrice(new BigDecimal("259.00"));

entityManager.getTransaction().commit();
```

Tùy thời điểm flush, Hibernate có thể thực hiện `UPDATE` lúc commit hoặc sớm hơn khi cần đồng bộ. Nếu cột `unit_price` được đánh dấu `updatable = false`, thao tác sửa giá Java này sẽ không được sử dụng để cập nhật cột qua mapping đó. Nếu property được ánh xạ bình thường, dữ liệu mới có thể được đồng bộ khi flush, trong phạm vi transaction thành công.

Một điểm quan trọng khác: `@Column(name = "unit_price")` **không làm thay đổi tên thuộc tính trong JPQL**. Câu sau đúng:

```java
entityManager.createQuery(
    "select i from InventoryItem i where i.unitPrice < :limit",
    InventoryItem.class
);
```

Còn viết `i.unit_price` thường không đúng trong JPQL nếu entity không có thuộc tính Java mang tên `unit_price`. Native SQL thì dùng tên cột `unit_price` thật của database.

## 14. Schema generation, schema validation và migration

Khi thấy `@Column(nullable = false, length = 100)`, người mới học dễ nghĩ Hibernate sẽ tự sửa bảng đã có. Thực tế phải phân biệt ba việc:

1. **Khai báo metadata mapping:** annotation mô tả entity sẽ đọc/ghi cột như thế nào và nêu các đặc điểm schema dự kiến.
2. **Tạo/kiểm tra schema bằng ORM:** tùy cấu hình, Hibernate có thể dùng metadata để tạo, cập nhật hoặc kiểm tra schema; khả năng và mức độ an toàn của mỗi chế độ khác nhau.
3. **Migration schema được kiểm soát:** thay đổi bảng thực tế qua script và công cụ như Flyway/Liquibase hoặc quy trình DBA.

Ví dụ, thay:

```java
@Column(name = "product_name", length = 100)
private String name;
```

thành:

```java
@Column(name = "product_name", length = 200)
private String name;
```

là thay metadata trong ứng dụng. Nếu database production vẫn đang có `VARCHAR(100)`, application có thể gặp lỗi khi ghi giá trị dài hơn 100, cho dù annotation hiện ghi `length = 200`. Cần có migration tăng độ dài cột, xem xét dữ liệu hiện có và triển khai theo thứ tự phù hợp.

Tương tự, đổi `nullable = true` thành `nullable = false` đòi hỏi xử lý các hàng đang chứa `NULL` trước khi thêm `NOT NULL`. Đổi `unique = false` thành `true` có thể thất bại nếu bảng đã có dữ liệu trùng. Những vấn đề này là một phần của thay đổi schema, không phải chỉ là cú pháp Java.

Trong môi trường phát triển, chế độ sinh schema giúp thử nghiệm nhanh. Trong production, thường nên dùng migration rõ ràng, có khả năng đánh giá và triển khai từng bước, đồng thời để Hibernate xác nhận mapping phù hợp với schema.

## 15. Các lỗi thường gặp và cách nhận biết

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| SQL báo không tìm thấy cột | `name` sai, naming strategy khác dự kiến, schema chưa migration | Kiểm tra tên cột thực tế và SQL được phát sinh |
| `NOT NULL` violation khi insert | Giá trị null; DB thiếu default; `insertable=false` nhưng cột bắt buộc | Kiểm tra dữ liệu đầu vào, default, và mapping ghi |
| Unique constraint violation | Hai bản ghi trùng, có race condition, unique index thực sự tồn tại | Xác minh quy tắc nghiệp vụ và xử lý conflict |
| Dữ liệu lưu bị cắt/lỗi quá dài | `length` không khớp schema, thiếu validation | Đồng bộ schema và kiểm soát độ dài dữ liệu |
| Giá trị tiền bị làm tròn sai | Scale/precision không phù hợp hoặc dùng `double` | Dùng `BigDecimal`, quy tắc làm tròn và kiểu DB phù hợp |
| Thay field Java nhưng DB không cập nhật | `updatable=false`, entity detached, chưa flush/commit | Kiểm tra lifecycle, transaction và mapping |
| DB default không được áp dụng | ORM ghi `NULL` tường minh thay vì bỏ cột khỏi `INSERT` | Quy định rõ bên nào sinh giá trị |
| Lỗi “repeated column” trong mapping | Hai thuộc tính cùng ghi một cột | Chỉ định một đường ghi hoặc đổi mô hình mapping |
| HQL/JPQL báo thuộc tính không tồn tại | Dùng tên cột SQL thay vì tên field/property | Viết JPQL theo tên thuộc tính entity |
| Annotation ở getter không có tác dụng | Entity đang dùng field access | Đặt annotation đúng vị trí hoặc cấu hình `@Access` |
| DDL chạy ở H2 nhưng không chạy ở PostgreSQL/MySQL | `columnDefinition`, quoting hoặc kiểu SQL phụ thuộc dialect | Dùng migration và kiểm tra trên DB mục tiêu |

Điều cần nhớ khi xử lý lỗi là phải kiểm tra đồng thời **metadata Java**, **SQL Hibernate thực sự phát sinh**, **schema database thực tế** và **trạng thái transaction/entity**. Cùng một biểu hiện có thể có nhiều nguyên nhân; chỉ nhìn một annotation thường chưa đủ để kết luận.

## 16. Ví dụ lựa chọn mapping theo yêu cầu nghiệp vụ

Giả sử dịch vụ đặt hàng cần các cột sau:

- Mã đơn hàng dạng chuỗi, không null và duy nhất.
- Tiền phải lưu chính xác đến hai chữ số thập phân.
- Ghi chú có thể null, tối đa 500 ký tự.
- Thời điểm tạo đơn do database tự điền.
- Mã tích hợp bên ngoài không được cập nhật sau khi tạo.

Một cách biểu diễn bằng JPA:

```java
@Entity
@Table(name = "customer_orders")
public class CustomerOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "order_code", nullable = false, unique = true, length = 32)
    private String orderCode;

    @Column(name = "total_amount", nullable = false, precision = 14, scale = 2)
    private BigDecimal totalAmount;

    @Column(name = "note", length = 500)
    private String note;

    @Column(name = "created_at", insertable = false, updatable = false)
    private java.time.Instant createdAt;

    @Column(name = "external_ref", updatable = false, length = 64)
    private String externalReference;

    protected CustomerOrder() {}
}
```

Để thiết kế này hoạt động đúng, schema cần có `NOT NULL`/`UNIQUE` tương ứng; cột `created_at` phải có default/trigger ở DB hoặc một cơ chế sinh giá trị tương thích; dịch vụ phải kiểm tra `orderCode`, `totalAmount`, `note` theo quy tắc nghiệp vụ. `external_ref` không được ORM cập nhật sau insert qua mapping này, nhưng nếu quy tắc là “không ai được sửa”, vẫn cần chính sách bảo vệ tương ứng ở DB hoặc tầng ứng dụng.

Đặc biệt, `nullable = false` trên `totalAmount` không tự ngăn số âm. Nếu tổng tiền không được âm, phải bổ sung validation/domain invariant và có thể thêm check constraint trong schema. `@Column` không cố gắng biểu diễn toàn bộ mọi ràng buộc nghiệp vụ.

## 17. Câu hỏi tự luyện

**Tình huống 1:** Có field `private String fullName` nhưng DB dùng cột `full_name`. Có nên dùng `@Column(name = "full_name")`?

Có. Đây là cách tường minh và dễ hiểu. Nếu dự án đã cấu hình naming strategy tự chuyển camelCase sang snake_case thì cũng có thể đạt kết quả như vậy mà không cần khai báo, nhưng phải xác nhận naming strategy thực tế.

**Tình huống 2:** Có `@Column(length = 20) private String code;`. Người dùng gửi chuỗi dài 30 ký tự. Annotation có chắc chắn gây lỗi validation Java trước khi gửi SQL không?

Không. `length` chủ yếu mô tả mapping/DDL, không tương đương `@Size(max = 20)`. Hệ thống nên kiểm soát dữ liệu nhập và có ràng buộc schema tương ứng.

**Tình huống 3:** Cần mỗi người dùng chỉ có một tên hiển thị duy nhất trong từng tổ chức, nhưng các tổ chức khác nhau được phép trùng tên. Dùng `@Column(unique = true)` ở `displayName` có đúng không?

Không, vì nó có thể áp đặt duy nhất trên toàn bộ cột. Cần unique constraint kết hợp `organization_id` và `display_name` ở mức bảng.

**Tình huống 4:** Một cột có DB default là `CURRENT_TIMESTAMP`, nhưng khi persist, Hibernate vẫn gửi `NULL`. Nên xem xét gì?

Xác định ORM có đang đưa cột vào `INSERT` không, default của DB đã tồn tại chưa, và có cần dùng `insertable = false` hoặc cơ chế Hibernate hỗ trợ nhận giá trị sinh từ DB không. Cũng cần xem lúc nào object Java được cập nhật giá trị trả về.

**Tình huống 5:** Entity `Order` có `private Customer customer` và bảng `orders` có cột `customer_id`. Dùng annotation nào để ánh xạ khóa ngoại?

Dùng `@ManyToOne` kết hợp `@JoinColumn(name = "customer_id")`, vì đây là quan hệ đến entity khác. `@Column` chủ yếu phục vụ thuộc tính cơ bản.

## 18. Ghi nhớ

`@Column` là công cụ **tùy chỉnh ánh xạ thuộc tính cơ bản thành cột** trong Jakarta Persistence; Hibernate đọc và thực thi metadata đó với tư cách persistence provider. Những lựa chọn quan trọng nhất thường là:

- **Tên:** `name` xác định cột; JPQL vẫn dùng tên thuộc tính Java, còn SQL dùng tên cột database.
- **Ràng buộc DDL:** `nullable`, `unique` mô tả schema dự kiến, không thay thế validation/domain logic và constraint thực tế trong database.
- **Kích thước/độ chính xác:** `length` phù hợp với chuỗi; `precision`, `scale` cần được thiết kế cùng kiểu `BigDecimal` và quy tắc làm tròn.
- **Ghi dữ liệu:** `insertable`, `updatable` quyết định cột có tham gia SQL ghi do ORM sinh ra, không phải cơ chế phân quyền.
- **Cấu trúc nâng cao:** `columnDefinition` mang SQL tùy biến; `table` chỉ bảng phụ đã khai báo; quan hệ dùng `@JoinColumn` và embedded mapping có thể dùng `@AttributeOverride`.

Thực hành bền vững là dùng annotation rõ ràng, hiểu naming strategy của Hibernate, quản lý schema bằng migration, và đối chiếu hành vi với database thực tế. Khi nắm vững sự khác biệt giữa **Java property**, **mapping metadata**, **SQL generated** và **database constraint**, việc thiết kế entity sẽ nhất quán và dễ bảo trì hơn.

### Tài liệu chính thức

- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — định nghĩa chuẩn về entity, `@Column` và metadata ánh xạ.
- [Hibernate ORM User Guide](https://docs.hibernate.org/orm/) — xem hướng dẫn đúng phiên bản cho naming strategy, mapping cơ bản và schema generation.
- [Jakarta Persistence API Javadocs](https://jakarta.ee/specifications/persistence/) — tra chữ ký các thuộc tính của `@Column`, `@Table`, `@JoinColumn` và `@AttributeOverride` theo phiên bản.

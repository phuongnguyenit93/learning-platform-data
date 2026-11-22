# Tái sử dụng ánh xạ bằng `@MappedSuperclass`

## 1. Vì sao cần tái sử dụng mapping trong JPA?

Trong ứng dụng sử dụng Jakarta Persistence (JPA), nhiều entity không cùng một loại thực thể nghiệp vụ nhưng có những thuộc tính và quy tắc persistence giống nhau. Ví dụ, `Product`, `Customer` và `Invoice` đều có thể cần:

- Một thuộc tính khóa chính `id`.
- Thông tin thời điểm tạo `createdAt` và thời điểm cập nhật `updatedAt`.
- Một cột `version` để kiểm soát cập nhật đồng thời.
- Một số phương thức lifecycle callback như `@PrePersist` và `@PreUpdate`.
- Các quy ước khai báo cột như `nullable = false` hoặc `updatable = false`.

Nếu sao chép toàn bộ annotation và method này vào từng entity, việc duy trì dễ sai lệch: entity này dùng `created_at`, entity khác lại đặt `create_time`; một entity có `@Version`, một entity quên mất; hoặc hai method cập nhật thời gian có cách làm khác nhau.

Java cho phép dùng **kế thừa lớp**, còn JPA cung cấp **`@MappedSuperclass`** để các mapping thuộc tính của lớp cha được **áp dụng vào các entity con**.

Ví dụ:

```text
                  @MappedSuperclass
                     AuditedRecord
                 /       |        \
                /        |         \
               v         v          v
         @Entity     @Entity      @Entity
          Product     Customer     Invoice
             |           |           |
             v           v           v
         products     customers     invoices
            table       table        table

Không có bảng AuditedRecord.
Không có entity riêng tên AuditedRecord.
```

**Ý nghĩa cốt lõi:** `@MappedSuperclass` là cơ chế **tái sử dụng metadata ánh xạ và mã Java** giữa các entity khác nhau. Nó **không tạo ra một entity cha có định danh độc lập**, không tự sinh bảng riêng cho lớp cha và **không tạo quan hệ kế thừa đa hình ở mức JPA entity**.

Bài học này làm rõ cách khai báo, cách các thuộc tính được ánh xạ sang bảng con, cách override metadata và khi nào không nên dùng `@MappedSuperclass`.

## 2. `@MappedSuperclass` hoạt động như thế nào?

### 2.1. Annotation và ý nghĩa

```java
import jakarta.persistence.MappedSuperclass;

@MappedSuperclass
public abstract class AuditedRecord {
    // Các thuộc tính và mapping sẽ được entity con kế thừa.
}
```

JPA coi lớp này là một **nguồn metadata persistence**, không phải một entity có thể lưu độc lập.

Nếu một entity kế thừa:

```java
@Entity
@Table(name = "products")
public class Product extends AuditedRecord {
    // Các trường riêng của Product.
}
```

thì các thuộc tính persistent trong `AuditedRecord` được xem như một phần của mapping `Product`. Theo hướng thông thường, cột của chúng nằm trong **bảng `products`**, không nằm trong một bảng cho lớp cha.

Nếu `Customer extends AuditedRecord`, các thuộc tính tương tự lại được ánh xạ vào **bảng `customers`**. Cùng một khai báo Java được tái sử dụng để mô tả nhiều bảng vật lý.

### 2.2. Những điều `@MappedSuperclass` có thể mang xuống entity con

Lớp mapped superclass có thể khai báo:

| Thành phần | Ví dụ | Khi entity con kế thừa |
|---|---|---|
| Thuộc tính cơ bản | `@Column String createdBy` | Trở thành cột của bảng entity con |
| Khóa chính | `@Id Long id` | Entity con sử dụng định danh được thừa kế |
| Sinh khóa | `@GeneratedValue` | Provider dùng chiến lược sinh khóa tương ứng theo entity/schema |
| Optimistic locking | `@Version long version` | Version column nằm ở bảng entity con |
| Quan hệ | `@ManyToOne UserAccount owner` | Association được kế thừa; FK nằm theo mapping của từng entity con |
| Thuộc tính nhúng | `@Embedded Address address` | Các thành phần embeddable được ánh xạ trong bảng con |
| Lifecycle callback | `@PrePersist`, `@PreUpdate` | Callback có thể áp dụng khi entity con được quản lý |
| Java method dùng chung | Getter, validation helper | Được kế thừa theo Java như bình thường |

`@MappedSuperclass` không buộc mọi entity con có cấu trúc nghiệp vụ giống nhau; nó chỉ chia sẻ những phần thực sự chung. Entity con vẫn có field riêng, quan hệ riêng, constraint riêng và bảng riêng.

### 2.3. Những điều nó **không** tạo ra

- Không có persistence identity cho chính lớp mapped superclass.
- Không có bảng cho lớp mapped superclass theo mặc định.
- Không tạo cơ chế `SINGLE_TABLE` hoặc `JOINED` polymorphic inheritance như một `@Entity` root.
- Không khiến `EntityManager.find(AuditedRecord.class, id)` trở thành thao tác hợp lệ.
- Không cho phép JPQL chuẩn truy vấn `from AuditedRecord` như một entity.
- Không khiến một association `@ManyToOne` có thể trỏ đến lớp mapped superclass như đích entity đa hình.

Java vẫn có thể gán một `Product` vào biến kiểu `AuditedRecord` hoặc gọi method thừa kế. Nhưng **đa hình Java** và **đa hình truy vấn entity của JPA** là hai khái niệm khác nhau.

## 3. Ví dụ hoàn chỉnh: chia sẻ ID, version và audit timestamp

Ta dùng hai bảng riêng: `products` và `customers`. Mỗi bảng có cột khóa chính, version, thời điểm tạo và cập nhật.

### 3.1. Lớp mapped superclass

**`src/main/java/com/example/shop/domain/AuditedRecord.java`**

```java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.MappedSuperclass;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Version;

import java.time.Instant;

@MappedSuperclass
public abstract class AuditedRecord {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id", nullable = false, updatable = false)
    private Long id;

    @Version
    @Column(name = "row_version", nullable = false)
    private long version;

    @Column(
        name = "created_at",
        nullable = false,
        updatable = false
    )
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected AuditedRecord() {
        // Constructor cho entity subclass và JPA.
    }

    public Long getId() {
        return id;
    }

    public long getVersion() {
        return version;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    @PrePersist
    protected void beforeInsert() {
        Instant now = Instant.now();

        if (createdAt == null) {
            createdAt = now;
        }
        updatedAt = now;
    }

    @PreUpdate
    protected void beforeUpdate() {
        updatedAt = Instant.now();
    }
}
```

Ý nghĩa:

1. **`@MappedSuperclass`** thông báo đây là nguồn mapping để các entity con thừa kế.
2. **`@Id` + `@GeneratedValue(IDENTITY)`** áp dụng một chiến lược khóa chính dùng chung. Mỗi bảng con phải có cột `id` và cơ chế identity tương thích.
3. **`@Version`** cho phép JPA kiểm tra và cập nhật phiên bản khi entity được ghi theo cơ chế optimistic locking.
4. **`@Column`** mô tả các thuộc tính audit nằm trong bảng của entity con.
5. **`@PrePersist` / `@PreUpdate`** chia sẻ logic gán timestamp vào thời điểm JPA thực hiện các lifecycle event tương ứng.
6. Method getter được kế thừa; mã nghiệp vụ không cần lặp lại chúng ở từng entity.

Ví dụ sử dụng `Instant.now()` trực tiếp cho ngắn gọn. Trong hệ thống cần kiểm thử thời gian, đồng bộ chính sách clock, hoặc thời điểm do database quyết định, có thể chuyển cơ chế cấp timestamp sang service/listener/database theo thiết kế rõ ràng.

**Quan trọng:** `createdAt`, `updatedAt` và `version` là trạng thái **của từng entity con**, không phải trạng thái của một “bản ghi AuditedRecord” riêng.

### 3.2. Entity con `Product`

**`Product.java`**

```java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "products")
public class Product extends AuditedRecord {

    @Column(name = "sku", nullable = false,
            unique = true, length = 64)
    private String sku;

    @Column(name = "name", nullable = false, length = 160)
    private String name;

    @Column(name = "unit_price", nullable = false,
            precision = 14, scale = 2)
    private BigDecimal unitPrice;

    protected Product() {
    }

    public Product(
            String sku,
            String name,
            BigDecimal unitPrice) {

        this.sku = Objects.requireNonNull(sku);
        this.name = Objects.requireNonNull(name);
        this.unitPrice = Objects.requireNonNull(unitPrice);
    }

    public String getSku() {
        return sku;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public void changePrice(BigDecimal nextPrice) {
        if (nextPrice == null || nextPrice.signum() < 0) {
            throw new IllegalArgumentException(
                "Đơn giá phải không âm");
        }
        this.unitPrice = nextPrice;
    }
}
```

`Product` không có field `id`, `version`, `createdAt` hay `updatedAt` riêng, nhưng JPA vẫn biết cách ánh xạ chúng vì lớp này kế thừa `AuditedRecord`.

Java code có thể gọi:

```java
Product product = entityManager.find(Product.class, 7L);

Long id = product.getId();
long version = product.getVersion();
Instant createdAt = product.getCreatedAt();
```

Provider xác định rằng `Product.class` tương ứng bảng `products`, rồi đọc các cột vừa riêng của Product vừa thừa kế từ superclass.

### 3.3. Entity con `Customer`

**`Customer.java`**

```java
package com.example.shop.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

import java.util.Objects;

@Entity
@Table(name = "customers")
public class Customer extends AuditedRecord {

    @Column(name = "email", nullable = false,
            unique = true, length = 255)
    private String email;

    @Column(name = "display_name",
            nullable = false, length = 120)
    private String displayName;

    protected Customer() {
    }

    public Customer(String email, String displayName) {
        this.email = Objects.requireNonNull(email);
        this.displayName = Objects.requireNonNull(displayName);
    }

    public String getEmail() {
        return email;
    }

    public void changeDisplayName(String nextName) {
        this.displayName = Objects.requireNonNull(nextName);
    }
}
```

`Product` và `Customer` dùng chung mapping audit, nhưng có bảng và vòng đời riêng.

### 3.4. Database schema tương ứng

Ví dụ với PostgreSQL:

```sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    row_version BIGINT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,

    sku VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(160) NOT NULL,
    unit_price NUMERIC(14, 2) NOT NULL
);

CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    row_version BIGINT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,

    email VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(120) NOT NULL
);
```

Không có lệnh:

```sql
-- Không cần bảng riêng chỉ vì khai báo @MappedSuperclass:
CREATE TABLE audited_records (...);
```

Các cột `id`, `row_version`, `created_at` và `updated_at` **lặp lại về mặt vật lý** trong hai bảng. Điều được tái sử dụng là **định nghĩa mapping trong mã Java**, chứ không phải một bảng quan hệ dùng chung.

Đây cũng là khác biệt lớn nhất so với `@Entity` inheritance theo chiến lược `JOINED`, vốn có thể sử dụng bảng gốc chứa các cột chung.

### 3.5. Thao tác persist và kiểm soát phiên bản

Giả sử `em` là `EntityManager` có transaction `RESOURCE_LOCAL`:

```java
EntityTransaction tx = em.getTransaction();
tx.begin();

try {
    Product product = new Product(
        "KEYBOARD-01",
        "Mechanical Keyboard",
        new BigDecimal("890000.00")
    );

    em.persist(product);
    tx.commit();

    System.out.println(product.getId());
    System.out.println(product.getCreatedAt());
    System.out.println(product.getVersion());
} catch (RuntimeException ex) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw ex;
}
```

Đoạn mã sử dụng `java.math.BigDecimal` và `jakarta.persistence.EntityTransaction`. Với JTA hoặc Spring-managed transactions, cách quản lý transaction sẽ khác.

Khi persist entity, provider sẽ sử dụng mapping inherited và thực hiện callback `@PrePersist` để set các timestamp. Khóa `id` được sinh bằng cơ chế identity; thời điểm chính xác ID được biết phụ thuộc thao tác INSERT/provider. Field `@Version` được provider quản lý, không nên cập nhật thủ công trong mã nghiệp vụ.

Khi sửa `unitPrice` của một Product managed, một câu SQL có thể tương đương:

```sql
UPDATE products
SET unit_price = ?,
    updated_at = ?,
    row_version = ?
WHERE id = ?
  AND row_version = ?;
```

Nếu version đã thay đổi bởi transaction khác, ORM có thể ném một ngoại lệ optimistic locking khi đồng bộ. SQL chính xác và cách cấp giá trị version thuộc provider; ví dụ minh họa nguyên tắc so sánh version.

## 4. `@MappedSuperclass` khác `@Entity` inheritance ra sao?

Hai cách đều dùng Java `extends`, nhưng **ý nghĩa persistence khác nhau**.

### 4.1. Mapped superclass: tái sử dụng cấu hình

```java
@MappedSuperclass
public abstract class AuditedRecord {
    @Id
    private Long id;
}

@Entity
public class Product extends AuditedRecord {}

@Entity
public class Customer extends AuditedRecord {}
```

Hệ quả:

- `Product` và `Customer` là **hai entity type riêng**.
- Không thể truy vấn `AuditedRecord` như một entity.
- Không tự có một bảng gốc chứa hàng chung của Product và Customer.
- Không có mặc định polymorphic query trả về cả Product lẫn Customer theo kiểu mapped superclass.
- Các subtype có thể có cùng giá trị ID, ví dụ Product #1 và Customer #1, mà vẫn là hai entity hoàn toàn khác.

### 4.2. Entity inheritance: mô hình đa hình thực sự

```java
@Entity
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class Payment {

    @Id
    private Long id;

    private BigDecimal amount;
}

@Entity
public class CardPayment extends Payment {
    private String cardLastFour;
}

@Entity
public class BankPayment extends Payment {
    private String bankReference;
}
```

Với `@Entity` root là `Payment`, JPA có thể quản lý quan hệ kế thừa entity và truy vấn đa hình:

```jpql
select p
from Payment p
where p.amount > :minimum
```

Tùy `InheritanceType`, schema có thể gồm bảng gốc và bảng subtype (`JOINED`), một bảng duy nhất (`SINGLE_TABLE`), hoặc bảng theo concrete class (`TABLE_PER_CLASS`). Provider xử lý tính đa hình qua metadata của entity hierarchy.

### 4.3. Bảng so sánh

| Khía cạnh | `@MappedSuperclass` | `@Entity` root + `@Inheritance` |
|---|---|---|
| Lớp cha là JPA entity? | **Không** | **Có** |
| Lớp cha có bảng riêng? | **Không có bảng chỉ vì là mapped superclass** | Phụ thuộc chiến lược inheritance |
| Kế thừa field, mapping và method? | Có | Có |
| `EntityManager.find(Base.class, id)` | Không hợp lệ với mapped superclass | Hợp lệ nếu Base là entity, có dữ liệu tương ứng |
| JPQL `from Base` | Không hợp lệ | Hợp lệ, có thể là truy vấn đa hình |
| Association trỏ tới Base | Không dùng Base như entity target | Có thể dùng entity root khi phù hợp |
| Discriminator/hierarchy query | Không tự tạo | Có thể được sử dụng theo chiến lược |
| Phù hợp | Audit, ID conventions, timestamp và trường dùng chung giữa entity độc lập | Các subtype là những loại của **cùng một khái niệm thực thể** |
| Chỗ lưu dữ liệu inherited | Trong bảng entity con | Theo chiến lược `SINGLE_TABLE/JOINED/TABLE_PER_CLASS` |

**Một dấu hiệu để chọn:** nếu nghiệp vụ muốn hỏi “trả về mọi `Payment` bất kể loại thanh toán” hoặc có quan hệ `Transaction → Payment` mà target có nhiều subtype, `@Entity` inheritance thích hợp hơn. Nếu chỉ muốn `Product` và `Customer` cùng có `createdAt`, `@MappedSuperclass` thường nhẹ nhàng hơn.

### 4.4. `@Inheritance` không biến mapped superclass thành entity

Ví dụ không phải cách thiết kế đúng:

```java
@MappedSuperclass
@Inheritance(strategy = InheritanceType.JOINED)
public abstract class SharedRecord {
    // Tưởng rằng có bảng gốc cùng JOINED hierarchy.
}
```

Chiến lược `@Inheritance` được định nghĩa cho **entity inheritance hierarchy**, không làm cho lớp `@MappedSuperclass` trở thành một entity root. Nếu cần thực thể cha có persistence identity và polymorphic querying, phải mô hình hóa nó là `@Entity`.

## 5. Override cột được thừa kế bằng `@AttributeOverride`

Một lợi ích của mapped superclass là chia sẻ cấu trúc Java nhưng cho phép từng entity con **điều chỉnh metadata ánh xạ**.

Giả sử bảng `customers` trong hệ thống đã tồn tại có cột `registered_at`, còn `products` dùng `created_at`. Ta vẫn muốn dùng thuộc tính Java `createdAt` trong superclass.

### 5.1. Đổi tên cột ở entity con

```java
import jakarta.persistence.AttributeOverride;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
@AttributeOverride(
    name = "createdAt",
    column = @Column(
        name = "registered_at",
        nullable = false,
        updatable = false
    )
)
public class Customer extends AuditedRecord {
    // Các trường của Customer...
}
```

Giải thích:

- `name = "createdAt"` là **tên thuộc tính Java inherited**, không phải tên cột SQL.
- `column = @Column(name = "registered_at", ...)` thay metadata cột cho mapping **Customer.createdAt**.
- `Product.createdAt` tiếp tục dùng `created_at` từ superclass.
- Getter `getCreatedAt()` vẫn tồn tại trên cả hai entity; nghiệp vụ không cần biết tên cột vật lý khác nhau.

Schema tương ứng cho Customer cần:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    row_version BIGINT NOT NULL,
    registered_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(120) NOT NULL
);
```

Đây là **phương án thay thế** schema Customer của ví dụ trước, không phải thêm cả `registered_at` và `created_at` cho cùng một thuộc tính mà không có lý do.

### 5.2. Override nhiều thuộc tính

Nếu một entity con cần đổi cả `createdAt` và `updatedAt`:

```java
@Entity
@AttributeOverrides({
    @AttributeOverride(
        name = "createdAt",
        column = @Column(name = "inserted_on",
                         nullable = false, updatable = false)
    ),
    @AttributeOverride(
        name = "updatedAt",
        column = @Column(name = "changed_on",
                         nullable = false)
    )
})
public class LegacyDocument extends AuditedRecord {
    // ...
}
```

Import `jakarta.persistence.AttributeOverrides` và `AttributeOverride` khi dùng đoạn này.

**`@AttributeOverride` đổi cấu hình cột, không đổi quy tắc callback hoặc Java field**. `beforeInsert()` trong mapped superclass vẫn gán `createdAt`/`updatedAt` như trước.

### 5.3. Override những gì, không override những gì?

`@AttributeOverride` chủ yếu dùng cho metadata ánh xạ cột của basic/embedded attributes. Nó không phải một cơ chế “thay mọi annotation inherited”:

- Không dùng để đổi `@Id` thành một thuộc tính khác.
- Không dùng để chọn lại một `@GeneratedValue`/generator tùy ý cho mỗi entity.
- Không biến một mapped superclass thành entity.
- Không thay đổi business semantics của field.
- Không thay thế `@AssociationOverride` đối với quan hệ cần đổi join column/join table.

Khi schema các entity con khác nhau quá nhiều, việc ép tất cả vào một mapped superclass có thể tạo vô số override. Khi đó cân nhắc **thu hẹp phần metadata chia sẻ** và để mỗi entity tự khai báo những mapping riêng.

## 6. Tái sử dụng quan hệ và đổi join column bằng `@AssociationOverride`

Mapped superclass không chỉ chứa scalar fields. Nó có thể khai báo một association mà nhiều entity con cần dùng chung.

Ví dụ một số entity quản trị đều lưu người tạo bản ghi, tham chiếu đến `UserAccount`.

### 6.1. Lớp cha giữ quan hệ

```java
package com.example.shop.domain;

import jakarta.persistence.FetchType;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.MappedSuperclass;

@MappedSuperclass
public abstract class CreatedByUser {

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "created_by_user_id", nullable = false)
    private UserAccount createdBy;

    protected CreatedByUser() {
    }

    protected CreatedByUser(UserAccount createdBy) {
        this.createdBy = createdBy;
    }

    public UserAccount getCreatedBy() {
        return createdBy;
    }
}
```

Entity đích của association là **`UserAccount`**, một lớp được gắn `@Entity` và có `@Id`. Bản thân `CreatedByUser` chỉ cung cấp cấu hình tham chiếu, không phải một entity target.

Ví dụ lớp UserAccount:

```java
@Entity
@Table(name = "user_accounts")
public class UserAccount {

    @Id
    private Long id;

    @Column(name = "username", nullable = false)
    private String username;

    protected UserAccount() {}
}
```

### 6.2. Entity con giữ tên FK mặc định

```java
@Entity
@Table(name = "articles")
public class Article extends CreatedByUser {

    @Id
    private Long id;

    private String title;

    protected Article() {}
}
```

Bảng `articles` có thể có cột:

```sql
created_by_user_id BIGINT NOT NULL
    REFERENCES user_accounts(id)
```

### 6.3. Entity con đổi join column

Bảng `approval_requests` có quy ước dùng cột `initiator_id`. Entity này override association:

```java
import jakarta.persistence.AssociationOverride;
import jakarta.persistence.Entity;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Table;

@Entity
@Table(name = "approval_requests")
@AssociationOverride(
    name = "createdBy",
    joinColumns = @JoinColumn(
        name = "initiator_id",
        nullable = false
    )
)
public class ApprovalRequest extends CreatedByUser {

    @Id
    private Long id;

    private String reason;

    protected ApprovalRequest() {}
}
```

Ở đây:

- `name = "createdBy"` là **tên property inherited**, không phải tên SQL.
- `joinColumns` chỉ định cột FK của chính bảng `approval_requests`.
- Quan hệ vẫn trỏ tới `UserAccount`; chỉ cột vật lý thay đổi.
- Nếu có nhiều quan hệ cần override, dùng `@AssociationOverrides` tương ứng.

Có thể dùng `@AssociationOverride` cho các mapping association hỗ trợ, bao gồm cấu hình join table thích hợp. Nó là công cụ điều chỉnh **join metadata**, khác `@AttributeOverride` dành cho basic/embedded column metadata.

### 6.4. Một lưu ý quan trọng: superclass không nhất thiết chứa ID

`CreatedByUser` không có `@Id`. Hai entity con tự khai báo ID riêng:

```java
@Entity
public class Article extends CreatedByUser {
    @Id
    private Long id;
}

@Entity
public class ApprovalRequest extends CreatedByUser {
    @Id
    private UUID id;
}
```

Đây là thiết kế hoàn toàn hợp lý: **tái sử dụng quan hệ** nhưng **không ép mọi entity dùng cùng ID type và generator**.

## 7. Có nên đặt `@Id` trong mapped superclass?

### 7.1. Khi kế thừa ID là hợp lý

Nếu mọi entity con cùng tuân thủ chính sách ID, ta có thể khai báo ID một lần trong superclass:

```java
@MappedSuperclass
public abstract class NumericIdentified {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id", updatable = false)
    private Long id;

    protected NumericIdentified() {}

    public Long getId() {
        return id;
    }
}
```

Các entity con kế thừa ID và **không cần khai báo lại `@Id`**. Với `IDENTITY`, mỗi bảng con phải có cột identity phù hợp. Việc có `Product(id=1)` và `Customer(id=1)` hoàn toàn bình thường: hai entity khác nhau, hai bảng khác nhau.

### 7.2. Khi nên để ID ở từng entity con

Không nên cố định `@Id` trong mapped superclass nếu:

- Một entity cần `Long` identity, entity khác cần `UUID`.
- Một bảng dùng key nghiệp vụ `String code`, bảng khác dùng sequence.
- Có entity dùng khóa ghép `@EmbeddedId` hoặc `@IdClass`.
- Một số entity legacy có tên và chiến lược khóa khác biệt đáng kể.
- Tầng dữ liệu phân biệt identity theo tenant hoặc cần một cách sinh khóa riêng.

Trong tình huống này, mapped superclass chỉ chứa phần chung thực sự như `createdAt`, `updatedAt` hoặc người tạo, còn mỗi entity tự đặt `@Id`.

Ví dụ:

```java
@MappedSuperclass
public abstract class AuditFields {

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    // Getter và callback...
}

@Entity
public class Shipment extends AuditFields {
    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;
}

@Entity
public class ExternalPartner extends AuditFields {
    @Id
    @Column(name = "partner_code")
    private String partnerCode;
}
```

`GenerationType.UUID` được chuẩn hóa từ Jakarta Persistence 3.1; các dự án dùng phiên bản cũ phải chọn chiến lược phù hợp hoặc tự cấp UUID.

### 7.3. Không thể tạo generator chung mà bỏ qua thực tế database

`@GeneratedValue(strategy = SEQUENCE)` và `@SequenceGenerator` trong một mapped superclass có thể làm nhiều entity sử dụng cùng cấu hình sinh khóa, nhưng không phải lúc nào schema cũng cho phép hoặc có ý nghĩa như nhau. Chẳng hạn một database yêu cầu sequence khác nhau cho từng bảng, hoặc phần mềm cần tối ưu allocation riêng.

`@AttributeOverride` **không phải cách tiêu chuẩn để override toàn bộ chiến lược `@GeneratedValue`**. Nếu generator thay đổi theo entity, có thể cần để phần ID ở từng entity, dùng provider-specific extension được tài liệu hóa hoặc thiết kế lại base class.

Nguyên tắc: **tái sử dụng cấu hình ID khi chính sách ID thực sự chung**, không đặt ID trong superclass chỉ để giảm vài dòng annotation.

## 8. Field access, property access và annotation placement

### 8.1. Chọn cùng mô hình truy cập

Trong ví dụ `AuditedRecord`, annotation `@Id` được đặt trên **field**. JPA sử dụng field access cho mapping phù hợp, và các thuộc tính được quản lý thông qua field chứ không dựa hoàn toàn vào getter/setter nghiệp vụ.

```java
@MappedSuperclass
public abstract class AuditedRecord {

    @Id
    private Long id; // Field access.

    @Column(name = "created_at")
    private Instant createdAt;

    public Long getId() {
        return id;
    }
}
```

Nếu entity con cũng đặt annotation trên field, mapping dễ theo dõi:

```java
@Entity
public class Product extends AuditedRecord {

    @Column(name = "sku")
    private String sku;
}
```

### 8.2. Không trộn annotation field/getter tùy tiện

Ví dụ dễ gây nhầm:

```java
@MappedSuperclass
public abstract class Base {

    @Id
    private Long id;
}

@Entity
public class Product extends Base {

    private String name;

    @Column(name = "product_name")
    public String getName() {
        return name;
    }
}
```

Nếu access type mặc định là field, `@Column` đặt trên getter có thể không được áp dụng theo cách mong muốn. Cách rõ hơn là dùng field mapping nhất quán, hoặc **`@Access`** để chỉ định cách truy cập ở phạm vi phù hợp khi có lý do thật sự.

Ví dụ thiết lập rõ:

```java
@MappedSuperclass
@Access(AccessType.FIELD)
public abstract class Base {
    @Id
    private Long id;
}

@Entity
@Access(AccessType.FIELD)
public class Product extends Base {
    @Column(name = "product_name")
    private String name;
}
```

Có thể dùng property access, nhưng phải tổ chức getter/setter và metadata tương ứng. **Tên property để `@AttributeOverride` hoặc `@AssociationOverride` tham chiếu phải theo metadata Java**, không theo tên cột vật lý.

### 8.3. Các field nào của superclass được lưu?

Trong một `@MappedSuperclass` theo field access, các field persistent hợp lệ được kế thừa **không nhất thiết phải gắn `@Column`** mới được JPA nhận diện. Nếu provider sử dụng default basic mapping, một field không có annotation vẫn có thể được ánh xạ theo quy tắc tên mặc định.

Khi muốn một field dùng cho tính toán, không lưu database, sử dụng `@Transient` hoặc modifier Java `transient` phù hợp:

```java
@MappedSuperclass
public abstract class Base {

    @Transient
    private String cachedDisplayName;

    private transient boolean localDirtyFlag;
}
```

Không nên để các field helper trong mapped superclass bị JPA ánh xạ ngoài ý muốn chỉ vì quên `@Transient`.

## 9. Lifecycle callback được kế thừa nhưng không thay transaction

### 9.1. Callback trong superclass

`@PrePersist` và `@PreUpdate` có thể đặt trên mapped superclass để tái sử dụng logic audit:

```java
@MappedSuperclass
public abstract class Timestamped {

    @Column(name = "created_at", updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at")
    private Instant updatedAt;

    @PrePersist
    protected void onCreate() {
        Instant now = Instant.now();
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    protected void onUpdate() {
        updatedAt = Instant.now();
    }
}
```

Entity con kế thừa mapping và logic callback. Khi persist một entity con, provider xử lý lifecycle của **entity con**, không tạo một entity `Timestamped` riêng.

### 9.2. Giới hạn của callback

- `@PrePersist` xảy ra trong quá trình persist trước thao tác INSERT tương ứng; ID do database sinh có thể chưa có tại thời điểm callback chạy.
- `@PreUpdate` được gọi khi provider thực sự thực hiện một lifecycle update tương ứng, không phải mỗi lần Java setter được gọi.
- Nếu không có thay đổi persistent cần UPDATE, không nên giả định callback update chắc chắn chạy.
- JPQL bulk `UPDATE`/`DELETE` bỏ qua phần lớn cơ chế lifecycle thông thường của từng managed entity, vì vậy không tự chạy callback như khi cập nhật entity từng instance.
- Callback không thay thế **transaction** hoặc **ràng buộc database**. Cột `NOT NULL` và rule doanh nghiệp vẫn cần được bảo vệ phù hợp.

Nếu hệ thống nhận update từ cả SQL ngoài ứng dụng, background jobs và nhiều dịch vụ, `updatedAt` do JPA callback gán **không tự phản ánh những cập nhật ngoài JPA**. Có thể cần trigger hoặc quy ước đồng bộ giữa các kênh ghi.

### 9.3. Có cần dùng `@EntityListeners` không?

`@EntityListeners` là một công cụ JPA khác để tách lifecycle callback sang listener class. Nếu nhiều entity chỉ muốn tái sử dụng **hành vi audit** mà không cùng thuộc tính hoặc mapping, listener có thể dễ hiểu hơn việc ép tất cả dùng chung một superclass.

Mapped superclass có lợi nhất khi cần tái sử dụng **cả field mapping và logic**. Listener có thể kết hợp với cấu trúc entity phù hợp; đừng tạo một lớp cha chứa hàng chục field không dùng tới chỉ để chia sẻ một method.

## 10. `@Version` được thừa kế và kiểm soát cập nhật đồng thời

Khi một mapped superclass chứa:

```java
@Version
@Column(name = "row_version")
private long version;
```

mỗi entity con có một version column của riêng nó. Một update lên Product kiểm tra **version của hàng Product**; một update lên Customer kiểm tra **version của hàng Customer**, không có “version toàn hệ thống” chung ở superclass.

Ví dụ hai transaction:

```text
T1: đọc Product #7, version = 3
T2: đọc Product #7, version = 3

T1: đổi giá và commit
    -> UPDATE với WHERE id=7 AND version=3
    -> version mới = 4

T2: đổi tên và commit
    -> UPDATE với WHERE id=7 AND version=3
    -> không còn hàng nào khớp version cũ
    -> optimistic locking exception
```

Đặt `@Version` ở mapped superclass là lựa chọn tốt nếu **mọi entity con đều cần cùng cơ chế optimistic locking**. Nhưng nếu có entity đặc thù đã dùng cách kiểm soát khác, việc đưa `@Version` vào superclass chung có thể gây thêm cột/version semantics không mong muốn. Một số quan hệ collection và bulk operation có hành vi version khác; không coi annotation là giải pháp cho mọi xung đột đồng thời.

Không nên có hai thuộc tính `@Version` trong cùng một entity chỉ vì superclass và subclass đều khai báo. Nếu mỗi lớp cần version riêng, nên phân tách mô hình hoặc chọn chính sách nhất quán.

## 11. `@MappedSuperclass` so với `@Embeddable` và Java superclass thường

Cùng một bộ field `createdAt`/`updatedAt` có thể được tái sử dụng theo nhiều cách. Lựa chọn nên dựa trên **ngữ nghĩa mô hình**.

### 11.1. `@MappedSuperclass`: tái sử dụng theo kế thừa kiểu

```java
@MappedSuperclass
public abstract class AuditFields {
    @Column(name = "created_at")
    private Instant createdAt;
}

@Entity
public class Product extends AuditFields {
    @Id
    private Long id;
}
```

Các field và method trở thành một phần thừa kế của entity. Java chỉ cho kế thừa **một lớp cha trực tiếp**, nên việc chọn mapped superclass tiêu tốn vị trí extends trong thiết kế object-oriented.

### 11.2. `@Embeddable`: tái sử dụng theo thành phần

```java
@Embeddable
public class AuditInfo {

    @Column(name = "created_at")
    private Instant createdAt;

    @Column(name = "updated_at")
    private Instant updatedAt;
}

@Entity
public class Product {

    @Id
    private Long id;

    @Embedded
    private AuditInfo audit;
}
```

`AuditInfo` là một value object được **nhúng như thành phần** của Product, không phải superclass. Có thể dùng nhiều embeddable trong một entity, điều chỉnh cột bằng `@AttributeOverrides` và truy cập qua `product.getAudit()` nếu định nghĩa getter.

`@Embeddable` phù hợp khi domain muốn nói “Product **có một** AuditInfo”, thay vì “Product **là một** loại AuditFields”. Nó cũng tránh phụ thuộc vào cây kế thừa Java.

Nếu audit logic cần callback/automatic timestamps, phải tổ chức callback/listener và cách cập nhật embeddable phù hợp; không mặc định mọi cơ chế callback trong mapped superclass hoạt động giống hệt một embeddable.

### 11.3. Java superclass không có `@MappedSuperclass`

```java
public abstract class PlainBase {
    private Instant createdAt;

    public Instant getCreatedAt() {
        return createdAt;
    }
}

@Entity
public class Product extends PlainBase {

    @Id
    private Long id;
}
```

Java vẫn kế thừa field/method, nhưng một superclass **không được đánh dấu là mapped superclass hay entity** không phải nguồn mapping JPA kế thừa theo cách `@MappedSuperclass` cung cấp. Không nên trông chờ mọi field ở lớp Java thường tự được lưu ở các bảng con.

Nếu muốn lưu `createdAt`, cách rõ ràng là khai báo mapping đúng trong entity, dùng `@Embeddable` hoặc đặt `@MappedSuperclass` cho lớp base nếu mô hình kế thừa phù hợp.

### 11.4. So sánh

| Tiêu chí | `@MappedSuperclass` | `@Embeddable` | Superclass Java thường |
|---|---|---|---|
| Quan hệ Java | `extends Base` | `has-a` thành phần | `extends Base` |
| Metadata persistent được tái sử dụng? | Có | Có, khi `@Embedded` | Không theo cơ chế mapped superclass |
| Có entity/table riêng? | Không | Không | Không |
| Có thể chứa `@Id` kế thừa? | Có | Không dùng như entity root `@Id` theo kiểu tương tự |
| Truy vấn trực tiếp như entity? | Không | Không | Không |
| Thích hợp khi | Nhiều entity chia sẻ field/ID/audit/callback | Nhiều entity có cùng value object | Chỉ cần tái sử dụng Java method/logic |
| Có chiếm vị trí Java `extends`? | Có | Không | Có |

Cả mapped superclass và embeddable đều có thể cần `@AttributeOverride` khi tên cột khác nhau; vị trí đường dẫn thuộc tính trong override phụ thuộc cấu trúc nesting.

## 12. Mapped superclass trong một hierarchy nhiều tầng

Một entity có thể thừa kế qua nhiều lớp, trong đó các lớp mapped superclass ở nhiều tầng cung cấp metadata:

```text
@MappedSuperclass Identified
    @Id Long id
           |
           v
@MappedSuperclass Audited
    Instant createdAt
    Instant updatedAt
           |
           v
@Entity Product
    String sku
    BigDecimal price
```

Ví dụ:

```java
@MappedSuperclass
public abstract class Identified {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    public Long getId() {
        return id;
    }
}

@MappedSuperclass
public abstract class Audited extends Identified {

    @Column(name = "created_at")
    private Instant createdAt;
}

@Entity
public class Product extends Audited {

    @Column(name = "sku")
    private String sku;
}
```

`Product` thừa kế ID từ `Identified` và `createdAt` từ `Audited`. JPA không cần bảng `identified` hoặc `audited`. Các mapping inherited được kết hợp trong entity concrete.

Tuy nhiên, tầng kế thừa càng sâu thì việc tìm nguồn gốc `@Id`, `@Column`, callback và access type càng khó. Nếu superclass bắt đầu chứa nhiều trường không dùng ở một số subclass, đó là dấu hiệu nên chia thành các khối mapping hẹp hơn hoặc dùng composition.

### Không khai báo trùng ID ở entity con

Ví dụ không mong muốn:

```java
@MappedSuperclass
abstract class Identified {
    @Id
    private Long id;
}

@Entity
class Product extends Identified {

    @Id
    private Long productId; // Tạo thêm identifier khác.
}
```

Điều này làm model không còn là entity khóa đơn như dự định, có thể dẫn tới lỗi metadata hoặc yêu cầu khóa ghép theo cách không chủ đích. Nếu các entity có chính sách ID khác nhau, **đừng đặt `@Id` ở superclass dùng chung**.

## 13. Kế thừa method `equals`/`hashCode`: điểm cần thận trọng

`@MappedSuperclass` có thể chia sẻ method Java, nhưng việc đặt `equals` và `hashCode` dùng ID vào lớp cha **không tự động phù hợp với mọi entity con**.

### 13.1. Hai entity khác loại có thể có cùng ID

Vì `Product` và `Customer` có bảng riêng:

```text
products.id = 1
customers.id = 1
```

Nếu base class triển khai:

```java
@Override
public boolean equals(Object other) {
    if (!(other instanceof AuditedRecord that)) {
        return false;
    }
    return Objects.equals(getId(), that.getId());
}
```

thì `Product(id=1)` và `Customer(id=1)` có thể bị xem là bằng nhau dù chúng là **hai loại entity độc lập**. Hơn nữa, hai entity mới cùng `id == null` cũng có thể bị coi là bằng nhau nếu code không kiểm tra ID khác null.

Cách suy nghĩ khi cần equality theo identity:

- Hai tham chiếu Java giống nhau luôn bằng nhau.
- Hai entity khác tham chiếu chỉ so sánh theo **ID đã được cấp** và **loại entity có cùng ý nghĩa identity**.
- Khi có Hibernate proxy hoặc entity inheritance, phải xác định thế nào là “cùng loại” một cách tương thích với provider.
- `hashCode` phải ổn định nếu entity được đưa vào `HashSet` trước khi ID sinh; việc dùng `Objects.hashCode(id)` có thể làm thay đổi bucket sau persist.

Không nên đặt một `equals`/`hashCode` “one size fits all” vào mapped superclass nếu nó không xét tới entity type, proxy, transient ID và phạm vi tenant. Khi không có nhu cầu so sánh entity từ nhiều persistence context, reference equality mặc định cũng có thể là lựa chọn đơn giản.

### 13.2. Audit fields không phải định danh

Hai Product có cùng `createdAt` và `updatedAt` vẫn là hai Product khác nhau. Timestamp, version hoặc người tạo không phải khóa identity.

Không triển khai equality dựa trên mọi field audit và business mutable. Các thuộc tính này có thể thay đổi và làm hash của entity biến động, dẫn đến lỗi collection hoặc gây lazy loading khi so sánh.

## 14. Quan hệ inherited không có nghĩa polymorphic target

Một câu hỏi thực tế: “Nếu Product và Customer đều kế thừa AuditedRecord, có thể tạo entity `ActivityLog` với `@ManyToOne AuditedRecord target` không?”

Ví dụ không phù hợp với mapping chuẩn:

```java
@Entity
public class ActivityLog {

    @Id
    private Long id;

    @ManyToOne
    private AuditedRecord target; // AuditedRecord không phải entity.
}
```

Lý do: JPA association như `@ManyToOne` phải trỏ tới **entity type** hợp lệ. `AuditedRecord` chỉ là mapped superclass, không có entity identity/table root để provider dùng như một target đa hình chung.

Các phương án thiết kế:

1. **Nếu Product và Customer thực sự là subtype của cùng một entity concept**, chuyển mô hình sang một entity root với `@Inheritance` thích hợp.
2. **Nếu chúng là entity độc lập**, ActivityLog có thể lưu `targetType` + `targetId` như hai thuộc tính scalar, nhưng đây là polymorphic reference do ứng dụng tự diễn giải, không có một FK SQL bình thường bảo vệ tới nhiều bảng khác nhau. Phải thiết kế integrity và lookup rõ ràng.
3. Dùng **hai association riêng** nếu chỉ có vài loại target và ràng buộc database cần mạnh.
4. Dùng event table/snapshot hoặc một aggregate root khác nếu audit không cần truy cập entity target qua ORM association trực tiếp.

Không nên mong `targetEntity=AuditedRecord.class` biến một mapped superclass thành entity. Thuộc tính `targetEntity` không thay đổi bản chất metadata của class đích.

## 15. Thiết kế schema và migration khi thêm một field ở superclass

Một thay đổi nhỏ ở lớp mapped superclass có thể tác động **nhiều bảng vật lý**.

Giả sử lúc đầu `AuditedRecord` chỉ có:

```java
@Column(name = "created_at")
private Instant createdAt;
```

Sau đó thêm:

```java
@Column(name = "updated_by", length = 120)
private String updatedBy;
```

Vì `Product` và `Customer` đều kế thừa, mapping mới đòi hỏi cột `updated_by` ở **cả hai bảng**, trừ khi có override/thiết kế khác.

Migration có thể gồm:

```sql
ALTER TABLE products
ADD COLUMN updated_by VARCHAR(120);

ALTER TABLE customers
ADD COLUMN updated_by VARCHAR(120);
```

Nếu quên một bảng, thao tác đọc/ghi entity con tương ứng có thể thất bại với lỗi thiếu cột.

### 15.1. Các trường hợp dễ gây lệch schema

- Đổi `@Column(name="created_at")` thành `created_on` ở superclass nhưng chỉ migrate một bảng.
- Chuyển `nullable=true` sang `false` mà chưa backfill dữ liệu cũ ở tất cả bảng.
- Thêm `@Version` ở superclass nhưng quên tạo/version backfill cho một entity con.
- Đổi chiến lược ID từ `IDENTITY` sang `SEQUENCE` mà không đồng bộ database generator của các bảng.
- Thay enum hoặc kiểu cột chung, trong khi vài entity legacy đang dùng representation khác.
- Đổi tên field Java khiến tên mặc định của cột thay đổi ở nhiều bảng vì thiếu `@Column` tường minh.

**Metadata chia sẻ làm giảm việc lặp code, nhưng có thể tăng số bảng cần migration mỗi khi quy ước thay đổi.** Đây là đánh đổi quan trọng của `@MappedSuperclass`.

### 15.2. Có phải dùng hbm2ddl tự động để tạo tất cả cột?

JPA provider như Hibernate có thể hỗ trợ tạo/kiểm tra schema trong môi trường phát triển, nhưng không nên dựa vào chế độ tự động chỉnh DDL để migrate production mà không kiểm soát. Dùng migration như Flyway hoặc Liquibase theo quy trình triển khai phù hợp và kiểm tra schema của **mọi entity con**.

Khi nâng cấp provider, kiểm tra quy tắc naming, type binding, sequence allocation và generated DDL vì các mapping được thừa kế vẫn phụ thuộc dialect.

## 16. Hiệu năng và thiết kế truy vấn

### 16.1. `@MappedSuperclass` tự nó không sinh JOIN

Vì không có bảng base riêng, khi đọc Product, ORM thường truy cập bảng `products` và các association cần thiết. `@MappedSuperclass` **không bắt buộc một JOIN tới bảng superclass**.

Ví dụ `Product extends AuditedRecord`:

```jpql
select p
from Product p
where p.createdAt >= :from
```

`p.createdAt` là một inherited property hợp lệ trên entity `Product`. Provider ánh xạ tới cột `products.created_at` hoặc tên đã được override.

Nhưng không thể dùng:

```jpql
-- Không hợp lệ nếu AuditedRecord chỉ là @MappedSuperclass:
select a from AuditedRecord a
```

Muốn lấy Product và Customer cùng thời gian tạo, có thể chạy hai truy vấn tương ứng hoặc tổ chức một read model chuyên dụng. Nếu yêu cầu query đa hình thường xuyên, đó là dấu hiệu cần xem lại mô hình entity inheritance.

### 16.2. Kế thừa quan hệ có thể mang theo chi phí fetch

Nếu mapped superclass khai báo:

```java
@ManyToOne(fetch = FetchType.EAGER)
private UserAccount owner;
```

thì **mọi entity con kế thừa association này** có thể chịu chi phí fetch mà không hề sử dụng owner trong use case đang chạy. Thông thường nên chủ động chọn fetch plan theo nhu cầu; `LAZY` ở `@ManyToOne` có thể hữu ích nhưng cần hiểu proxy và session/transaction boundaries.

Không đặt một `@OneToMany` collection lớn vào superclass chỉ vì vài entity có quan hệ cùng tên nếu nghiệp vụ và database của chúng không thực sự giống nhau. Mapped superclass tái sử dụng metadata, và vì vậy cũng có thể vô tình **nhân rộng chi phí fetch/dirty checking** sang nhiều entity.

### 16.3. Gói thiết kế chung nên nhỏ và ổn định

Một mapped superclass tốt thường chỉ chia sẻ những thành phần **thực sự nhất quán**:

- ID strategy chung khi có bằng chứng nhiều entity dùng giống nhau.
- Timestamps hoặc audit fields có cùng semantics.
- Version field khi mọi entity con cùng dùng optimistic locking.
- Association thật sự giống nhau về target, lifecycle và join semantics.

Nếu số lượng `@AttributeOverride`, `@AssociationOverride` và ngoại lệ nghiệp vụ lớn dần, thành phần chung đang trở nên quá rộng. Có thể chia nhỏ bằng mapped superclass theo nhóm entity hoặc chuyển vài trường sang `@Embeddable` thay vì xây cây kế thừa sâu.

## 17. Lỗi thường gặp

| Tình huống | Vì sao không đúng / dễ lỗi | Hướng xử lý |
|---|---|---|
| Đặt `@Entity` cho base chỉ để chia sẻ cột | Vô tình tạo một entity hierarchy với semantics polymorphism/schema khác | Dùng `@MappedSuperclass` nếu base không phải entity |
| Mong JPQL `from Base` hoạt động với mapped superclass | Base không phải entity name/type | Truy vấn các entity con, hoặc dùng entity root khi cần đa hình |
| Dùng `@ManyToOne Base` làm association target | Mapped superclass không có entity identity | Trỏ tới entity type thực hoặc thiết kế lại hierarchy |
| Quên `@MappedSuperclass` trên lớp chứa `@Column` muốn kế thừa | Superclass Java thường không cung cấp mapped inheritance metadata theo cách này | Annotate `@MappedSuperclass` hoặc dùng embeddable/field riêng |
| Khai báo `@Id` ở base rồi thêm `@Id` khác ở con | Có thể tạo cấu hình khóa ghép/sai metadata không chủ đích | Chỉ đặt ID ở nơi phản ánh chính sách thật |
| Các entity con cần generator khác nhau | `@GeneratedValue` chung gây xung đột schema/strategy | Để ID ở từng entity hoặc tách base |
| Dùng `@AttributeOverride` để đổi quan hệ | AttributeOverride dành cho column của basic/embedded attribute | Dùng `@AssociationOverride` khi đổi join metadata |
| Trong override dùng tên cột SQL thay tên Java | JPA đối chiếu theo tên property inherited | Dùng `createdAt`, không dùng `created_at` |
| Đổi cột ở base nhưng chỉ migrate một bảng | Mapping inherited áp dụng cho nhiều bảng | Migrate mọi bảng con cần cột mới |
| Kết hợp field/getter mapping thiếu nhất quán | Annotation có thể bị bỏ qua hoặc gây lỗi metadata | Thống nhất access type, dùng `@Access` khi cần |
| Dùng `equals` base chỉ theo non-null ID mà bỏ qua concrete type | Product #1 và Customer #1 có thể bị coi là cùng object | Xác định identity theo loại entity và ID phù hợp |
| Dùng `hashCode` thay đổi theo generated ID | HashSet/HashMap có thể không tìm lại phần tử | Chọn chính sách hash ổn định hoặc key bất biến |
| Cho rằng `@PreUpdate` luôn chạy khi đổi Java field | Không phải setter nào cũng dẫn tới SQL UPDATE | Hiểu dirty checking, flush và lifecycle |
| Mong bulk JPQL update chạy mọi callback | Bulk query bỏ qua lifecycle callback từng entity | Xử lý audit/trạng thái ở service hoặc DB theo thiết kế |
| Dùng `@MappedSuperclass` khi cần bảng cha chung | Mapped superclass không tạo bảng cha | Chọn `@Entity` inheritance như `JOINED` hoặc `SINGLE_TABLE` |
| Dùng một base khổng lồ cho mọi entity | Mọi entity phải mang field/mapping không phù hợp | Phân chia mapping theo semantics, cân nhắc embeddable |

### 17.1. Ví dụ lỗi: mong provider tạo bảng base

```java
@MappedSuperclass
@Table(name = "base_records")
public abstract class BaseRecord {

    @Id
    private Long id;
}
```

`@MappedSuperclass` không phải entity và không tạo bảng chỉ vì có annotation `@Table`. Không nên đặt `@Table` như một lời yêu cầu tạo parent table; nếu muốn một thực thể cha có bảng thì phải chọn entity inheritance đúng.

### 17.2. Ví dụ lỗi: override sai tên thuộc tính

```java
@MappedSuperclass
public abstract class Audited {

    @Column(name = "created_at")
    private Instant createdAt;
}

@Entity
@AttributeOverride(
    name = "created_at", // Sai: đây là tên cột SQL.
    column = @Column(name = "inserted_at")
)
public class Product extends Audited {
}
```

Cách đúng:

```java
@AttributeOverride(
    name = "createdAt",  // Đúng: tên thuộc tính Java.
    column = @Column(name = "inserted_at")
)
```

Tên trường trong `@AttributeOverride` phải khớp mapping attribute của JPA, không chỉ khớp DDL.

## 18. Lựa chọn giải pháp theo tình huống

| Yêu cầu | Thiết kế khởi đầu | Lý do |
|---|---|---|
| Nhiều entity khác nhau đều có createdAt/updatedAt | Mapped superclass audit nhỏ gọn | Tránh lặp metadata và callback |
| Mọi entity con dùng cùng `Long id`, cùng generator | Mapped superclass khai báo `@Id` | Chia sẻ ID mapping nhất quán |
| Entity con có ID types/generator khác nhau | Mapped superclass audit **không có `@Id`** | Giữ linh hoạt ở từng entity |
| Cùng value object nhiều field như `Money` hoặc `Address` | `@Embeddable` | Quan hệ has-a, không tiêu tốn extends |
| Nhiều subtype thuộc cùng một loại thực thể và cần query chung | `@Entity` root + `@Inheritance` | Cần polymorphic entity identity |
| Chỉ cần chia sẻ method validation, không cần persistence mapping | Superclass Java hoặc service/helper | Không cần JPA annotation |
| Entity con cần tên cột khác nhau cho inherited field | `@AttributeOverride` | Giữ Java property chung, đổi mapping cột |
| Entity con cần tên FK khác nhau cho inherited association | `@AssociationOverride` | Điều chỉnh join metadata cụ thể |
| Các bảng có cấu trúc quá khác nhau | Không ép cùng base mapping | Giảm override, giảm coupling schema |
| Nhiều hệ thống cùng cập nhật audit timestamp ngoài JPA | Cân nhắc DB trigger hoặc audit infrastructure | Callback JPA không quan sát mọi đường ghi |

Một nguyên tắc thiết kế hữu ích: **“Dùng mapped superclass để chia sẻ những thứ nhiều entity *có* giống nhau ở tầng lưu trữ, không phải để tuyên bố chúng *là cùng một loại entity*.”**

## 19. Thực hành

### Bài 1 — Tái sử dụng audit và version

Tạo `AuditedRecord` chứa `id`, `version`, `createdAt` và `updatedAt` như phần 3. Tạo `Product` và `Customer` kế thừa, mỗi entity có các field nghiệp vụ khác nhau.

Viết schema cho hai bảng và tạo vài bản ghi. Xác định:

1. Có bảng `audited_records` không?
2. Các cột inherited nằm ở bảng nào?
3. Hai entity con có thể cùng mang `id = 1` không?
4. JPQL `select p from Product p where p.createdAt > :time` có hợp lệ không?
5. Vì sao `select a from AuditedRecord a` lại khác?

### Bài 2 — Override tên cột inherited

Giả sử bảng legacy `customers` dùng `registered_at`. Thêm:

```java
@AttributeOverride(
    name = "createdAt",
    column = @Column(
        name = "registered_at",
        nullable = false,
        updatable = false
    )
)
```

vào `Customer`. Đối chiếu SQL schema trước và sau, giải thích vì sao Product không bị đổi cột và method `getCreatedAt()` vẫn dùng được.

### Bài 3 — Override association

Viết `CreatedByUser` mapped superclass có `@ManyToOne UserAccount createdBy` và join column mặc định `created_by_user_id`. Tạo `Article` và `ApprovalRequest`, trong đó ApprovalRequest dùng `@AssociationOverride` chuyển FK sang `initiator_id`.

Kiểm tra hai bảng khác nhau về tên FK như thế nào. Tự trả lời: `CreatedByUser` có phải entity target của relation không?

### Bài 4 — Hai kiểu ID khác nhau

Tạo `Shipment` dùng `UUID` và `LegacyPartner` dùng `String partnerCode`. Cả hai cần audit timestamps.

Thử thiết kế một superclass chung có `Long id` rồi nhận xét vì sao không phù hợp. Sau đó tạo `AuditFields` **không khai báo ID**, để từng entity tự ánh xạ khóa theo nhu cầu.

### Bài 5 — Optimistic locking

Tạo một Product version 1. Mở hai `EntityManager`/transaction riêng, cùng tải Product đó. Transaction đầu đổi giá và commit, transaction sau đổi tên rồi commit.

Quan sát optimistic locking exception và giải thích cột `row_version` nằm ở bảng `products` hay một bảng superclass tưởng tượng.

### Bài 6 — Mapped superclass hay entity hierarchy?

Xét ba lớp `CreditCardPayment`, `BankTransferPayment` và `CashPayment`. Nghiệp vụ cần query mọi Payment cùng một API, lưu reference tới Payment từ Refund và làm báo cáo tổng hợp.

Giải thích vì sao `@Entity Payment` với `@Inheritance` có thể thích hợp hơn `@MappedSuperclass Payment`. Sau đó so sánh với hai lớp `Customer` và `Product` chỉ cùng timestamp audit nhưng không chung entity identity.

### Bài 7 — Migration khi thêm field ở base

Thêm `updatedBy` vào `AuditedRecord`. Giả sử hệ thống có bốn entity kế thừa với bốn bảng riêng. Liệt kê các migration cần thực hiện và rủi ro nếu chỉ thêm cột vào một bảng.

### Bài 8 — Chẩn đoán access type và transient field

Một base có `@Id` trên field, entity con đặt `@Column` trên getter. Hãy chọn một access strategy nhất quán rồi chỉnh annotation cho phù hợp.

Thêm một cache field `String displayCache` vào superclass. Hãy bảo đảm nó không bị lưu database bằng `@Transient` hoặc Java `transient`, và giải thích vì sao.

## 20. Ghi nhớ cốt lõi

**`@MappedSuperclass` dùng để tái sử dụng ánh xạ và hành vi persistence qua kế thừa Java, nhưng bản thân lớp cha không phải JPA entity.** Các field inherited như `@Column`, `@Id`, `@Version` và association được ánh xạ vào **bảng của từng entity con**, chứ không nằm trong một bảng superclass riêng.

Khi có khác biệt schema, dùng **`@AttributeOverride`** để điều chỉnh basic/embedded column mapping và **`@AssociationOverride`** để điều chỉnh join metadata của association inherited. Chọn nhất quán field/property access, chiến lược sinh ID và chính sách migration, vì một thay đổi ở superclass có thể tác động nhiều bảng.

Cuối cùng, không dùng `@MappedSuperclass` thay cho **`@Entity` inheritance** khi cần truy vấn hoặc liên kết đa hình tới entity cha. Cũng không cố dùng lớp cha chứa ID chung khi các entity con có cách định danh khác nhau. Thiết kế tốt chia sẻ đúng những thuộc tính thật sự ổn định, để từng entity giữ **identity và vòng đời nghiệp vụ riêng**.

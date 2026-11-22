# Thực hành tổng hợp: Ánh xạ khóa sinh, kiểu giá trị và quan hệ có ràng buộc trong JPA

Trong ứng dụng thực tế, các kỹ thuật JPA hiếm khi xuất hiện riêng lẻ. Một đơn hàng có **khóa được cơ sở dữ liệu hoặc provider sinh**, liên kết tới một khách hàng và nhiều sản phẩm, chứa **đối tượng giá trị** như số tiền/địa chỉ, đồng thời phải tuân thủ **khóa ngoại, ràng buộc duy nhất, kiểm tra số lượng và giao dịch**. Nếu chỉ biết viết `@Entity` và gọi `persist`, bạn có thể tạo được bản ghi nhưng chưa chứng minh rằng cấu trúc dữ liệu đúng, chống được cập nhật sai và tồn tại nhất quán khi lỗi giữa chừng.

Bài thực hành xây dựng một mô-đun quản lý đơn hàng với các entity:

- `Customer` — khách hàng, khóa `Long` sinh bằng sequence; email là value object được chuyển thành một cột.
- `Product` — sản phẩm, khóa `Long` sinh bằng sequence, có giá `Money`.
- `PurchaseOrder` — đơn hàng, khóa sequence, có tổng tiền `Money`, trạng thái và `@Version`.
- `OrderLine` — dòng đơn hàng, khóa `IDENTITY`, quan hệ tới Order và Product; số lượng và giá chụp tại thời điểm đặt.
- `CustomerProfile` — hồ sơ giao hàng, quan hệ một-một **dùng chung khóa chính** với Customer qua `@MapsId`.
- `PaymentAttempt` — lần thử thanh toán, khóa UUID được provider sinh và liên kết tới Order.

Các ràng buộc vật lý gồm composite UNIQUE cho dữ liệu nhiều tenant, FK từ Order sang Customer, FK từ Line sang Order/Product, CHECK cho các giá trị không âm và `UNIQUE(order_id,line_no)` để không trùng số thứ tự dòng. Mọi ví dụ Java dùng namespace `jakarta.persistence` (Jakarta Persistence 3.1 trở lên khi sử dụng `GenerationType.UUID`); ví dụ SQL dùng PostgreSQL. Với Hibernate/Spring Data hay database khác, cần xác nhận version, dialect và migrations tương ứng.

> **Mục tiêu thực hành:** Hoàn thành luồng **tạo Customer/Product → tạo Order với nhiều Lines → thêm Profile dùng chung PK → ghi PaymentAttempt UUID → flush/commit → đọc lại qua persistence context mới → xác nhận constraints và concurrency**. Không chỉ nhìn Java object trong memory rồi kết luận đã lưu thành công.

---

## 1. Kết quả đầu ra mong muốn

Sau bài này, bạn có thể:

1. Giải thích khi nào dùng `SEQUENCE`, `IDENTITY` và `UUID` để sinh khóa.
2. Khai báo `@SequenceGenerator` tương ứng sequence thật của database.
3. Dự đoán thời điểm định danh có thể được cấp và ảnh hưởng tới batching/flush.
4. Xây dựng `Money`, `PostalAddress` và `EmailAddress` có giá trị, kiểm tra và equality rõ ràng.
5. Ánh xạ `Money` bằng `@Embeddable`/`@AttributeOverrides` và `EmailAddress` bằng `AttributeConverter`.
6. Ánh xạ `@ManyToOne`/`@OneToMany`, xác định phía sở hữu và viết helper đồng bộ hai phía.
7. Phân biệt `cascade = ALL` với `orphanRemoval = true` và chọn phạm vi cascade hợp lý.
8. Ánh xạ `@OneToOne` shared primary key bằng `@MapsId`.
9. Khai `@Table(uniqueConstraints=...)` và database migrations cho PK/FK/UNIQUE/CHECK.
10. Tạo transaction lưu toàn bộ order aggregate và rollback nếu có lỗi.
11. Dùng `@Version` phát hiện stale update, hiểu giới hạn khi chỉ sửa quan hệ con.
12. Xác minh dữ liệu thật qua `flush → clear → find` và commit → EntityManager mới.
13. Tạo tests cho uniqueness, FK, positivity, tenant scope, orphan removal và optimistic concurrency.
14. Nhận diện N+1, IDENTITY batching, fetch plans và vấn đề trả entity trực tiếp qua API.
15. Phân biệt ràng buộc database và invariant nghiệp vụ nằm ở application/domain.

---

# Phần I — Đề bài và mô hình dữ liệu

## 2. Bài toán cửa hàng đa tenant

Một công ty vận hành hệ thống cho nhiều cửa hàng (tenants). Mỗi cửa hàng quản lý Customer, Product và Order của riêng mình.

Quy tắc nghiệp vụ:

1. Trong cùng một tenant, hai Customers không được có email chuẩn hóa trùng nhau.
2. Trong cùng một tenant, hai Products không được có SKU trùng nhau.
3. Một Order chỉ thuộc một tenant và một Customer của tenant đó.
4. Mỗi Order có một hoặc nhiều Lines trước khi gửi xác nhận.
5. Một Line tham chiếu một Product, `quantity > 0`, lưu **giá snapshot** để giá Product thay đổi sau này không thay đổi đơn đã tạo.
6. `totalAmount` của Order phải bằng tổng `quantity × unitPrice` các Lines; mọi Line/Order dùng cùng currency trong bài tập.
7. `externalCode` của Order phải duy nhất trong tenant, phục vụ tra cứu và giảm nguy cơ tạo trùng do request lặp.
8. Một Customer có tối đa một `CustomerProfile` (theo shared primary key).
9. Một Order có thể có nhiều `PaymentAttempt`, mỗi attempt mang UUID và `attemptNo` duy nhất trong Order.
10. Hai transactions cùng sửa một Order không được âm thầm ghi đè trạng thái cũ.
11. Nếu lưu Order thất bại, không được committed chỉ một nửa số Lines.
12. Không cho phép truy vấn hoặc liên kết chéo tenant ngoài policy đã được phê duyệt.

Những quy tắc thuộc nhiều tầng khác nhau. Ví dụ `quantity > 0` nên được kiểm tra bằng Java **và** DB CHECK. Quy tắc “total bằng tổng dòng” khó biểu diễn bằng một CHECK đơn giản trên một row; cần domain logic và transaction, hoặc cơ chế database phức tạp hơn nếu có nhiều writers.

## 3. Sơ đồ quan hệ dự kiến

```text
customer                              customer_profile
+----------------------+              +-------------------------+
| customer_id PK       |<-------------| customer_id PK, FK      |
| tenant_id            |      1:0..1  | default_shipping_*      |
| email                |              +-------------------------+
| billing_*            |
| row_version          |
+----------+-----------+
           ^ 1
           |
           | many
+----------+--------------------+
| purchase_order                |
| order_id PK (SEQUENCE)        |
| tenant_id                     |
| customer_id FK                |
| external_code                 |
| status                        |
| total_amount, total_currency  |
| next_line_no                  |
| created_at                    |
| row_version                   |
+-------------+-----------------+
              ^ 1
              |
              | many
+-------------+-----------------+        +----------------------+
| order_line                    |        | product              |
| line_id PK (IDENTITY)         |        | product_id PK (SEQ)  |
| order_id FK                   |        | tenant_id            |
| product_id FK ------------------------>| sku                  |
| line_no                       |        | price_amount/currency|
| quantity                      |        | active               |
| unit_price_amount/currency    |        +----------------------+
+-------------------------------+
              ^
              |
              | payment attempt belongs to order
+-------------+-----------------+
| payment_attempt               |
| attempt_id PK (UUID)          |
| order_id FK                   |
| attempt_no                    |
| status, provider_ref          |
+-------------------------------+
```

Các mũi tên biểu diễn quan hệ tham chiếu, không phải dấu hiệu rằng mọi association đều cần cascade. `Customer` và `Product` có vòng đời độc lập, còn `OrderLine` là thành phần thuộc Order aggregate.

## 4. Phạm vi công nghệ và conventions

Ví dụ giả định:

- Java 21 hoặc Java tương thích với Jakarta Persistence được chọn.
- Jakarta Persistence 3.1+ nếu dùng `GenerationType.UUID`.
- Provider: Hibernate ORM theo stack Spring Boot tương ứng (hoặc JPA provider khác đã kiểm tra).
- Database mục tiêu: PostgreSQL.
- Schema được quản lý bằng Flyway/Liquibase migrations.
- JUnit 5 và Testcontainers cho integration tests.
- Service transaction dùng `@Transactional` của Spring; khi không dùng Spring, thay bằng JTA hoặc resource-local transaction tương ứng.

**Đây không phải yêu cầu phải chạy Gradle trong bài viết.** Các snippets minh họa cách lập trình/kiểm thử, cần ghép thành source files, imports và migrations của một dự án thực tế.

### 4.1. Đặt tên

Dùng tên entity Java `PurchaseOrder` thay vì `Order` để tránh nhầm với từ khóa SQL `ORDER`. Tên bảng `purchase_order`, `order_line` và tên columns được khai tường minh.

### 4.2. Access type

Trong các entities, `@Id` nằm trên **field**, nên dùng field access nhất quán; không rải annotations tùy tiện lên getters của subclass.

### 4.3. Không để Hibernate tự tạo production schema

`hibernate.hbm2ddl.auto=validate` hoặc cấu hình validate tương ứng có thể hữu ích, nhưng migration mới là nguồn chính cho PK/FK/UNIQUE/CHECK và indexes. `validate` không chứng minh mọi constraint nâng cao đã có.

---

# Phần II — Chiến lược sinh khóa

## 5. Generated ID không có nghĩa tất cả chiến lược giống nhau

JPA hỗ trợ các chiến lược `AUTO`, `IDENTITY`, `SEQUENCE`, `TABLE` và ở Jakarta Persistence 3.1 là `UUID`. Mỗi chiến lược có đặc tính:

| Chiến lược | Nguồn định danh | Điểm cần chú ý |
|---|---|---|
| `SEQUENCE` | Database sequence | Có thể lấy ID trước INSERT, hỗ trợ allocation/batching |
| `IDENTITY` | Identity/autoincrement column | Thường cần INSERT để lấy generated key; có thể hạn chế batch insert |
| `UUID` | Provider/database tạo UUID tùy strategy/implementation | Phù hợp ID không phụ thuộc thứ tự DB; index/locality trade-off |
| `TABLE` | Bảng sinh ID riêng | Dễ tạo contention và overhead, tùy provider |
| `AUTO` | Provider chọn theo dialect/type | Khó kiểm soát khi cần portability/schema cụ thể |

Không đổi generator chỉ vì một test `getId()` trả null sớm hơn mong muốn. Cần quyết định theo throughput, schema, migration, shard/distributed use case và khả năng tương thích.

## 6. Sinh khóa Customer bằng SEQUENCE

```java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "customer_id_gen"
)
@SequenceGenerator(
    name = "customer_id_gen",
    sequenceName = "customer_id_seq",
    allocationSize = 1
)
@Column(name = "customer_id")
private Long id;
```

Migration PostgreSQL:

```sql
CREATE SEQUENCE customer_id_seq
    START WITH 1
    INCREMENT BY 1;
```

### 6.1. Những tên khác nhau

`generator` là tên generator trong JPA metadata; `sequenceName` là tên sequence vật lý trong DB. Tên chúng không cần giống nhau, nhưng sequenceName phải có thật.

### 6.2. Tại sao chọn allocationSize=1 ở ví dụ?

Dễ theo dõi hành vi trong bài học và khớp sequence `INCREMENT BY 1`. Production có thể chọn allocation/pooling lớn hơn để giảm round-trips lấy IDs, nhưng phải cấu hình DB sequence/optimizer tương ứng provider; không tự đổi hai phía độc lập.

### 6.3. Khi nào ID có giá trị?

Với sequence strategy, provider thường cấp ID trước INSERT vật lý (có thể ngay lúc `persist`), song thời điểm phát SQL vẫn tùy flush/transaction/provider. Không xem `id != null` là bằng chứng row đã committed.

### 6.4. Sequence có thể có khoảng trống

Transaction rollback hoặc sequence caching vẫn có thể “đốt” giá trị. **Không dùng generated primary key làm số hóa đơn liên tục không có khoảng trống** nếu nghiệp vụ/pháp lý đòi thứ tự riêng.

### 6.5. Không dựa vào ID mang ngữ nghĩa bí mật

ID được sinh không thay authentication/authorization. Customer#42 phải được lookup trong authorized tenant/owner scope.

## 7. Sinh khóa Product và Order bằng sequence riêng

`Product`:

```java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "product_id_gen"
)
@SequenceGenerator(
    name = "product_id_gen",
    sequenceName = "product_id_seq",
    allocationSize = 1
)
@Column(name = "product_id")
private Long id;
```

`PurchaseOrder`:

```java
@Id
@GeneratedValue(
    strategy = GenerationType.SEQUENCE,
    generator = "order_id_gen"
)
@SequenceGenerator(
    name = "order_id_gen",
    sequenceName = "order_id_seq",
    allocationSize = 1
)
@Column(name = "order_id")
private Long id;
```

### 7.1. Có cần sequence riêng cho mỗi entity?

Không bắt buộc, nhưng ví dụ dùng riêng để migration dễ hiểu. Một shared sequence có thể được nhiều entity sử dụng khi thiết kế và cấu hình đúng.

### 7.2. Đừng nhầm sequence với transaction durability

Lấy ID thành công nhưng INSERT/commit thất bại thì ID đã cấp không đồng nghĩa có row tồn tại.

### 7.3. Test trên DB mục tiêu

H2 sequence behavior và PostgreSQL sequence behavior có thể khác về SQL, allocation, permissions và DDL. Integration test cần xác minh actual migration.

## 8. Sinh khóa OrderLine bằng IDENTITY

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
@Column(name = "line_id")
private Long id;
```

PostgreSQL:

```sql
line_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY
```

### 8.1. Ưu điểm

Database cấp key trong quá trình INSERT, schema dễ hiểu nếu database hỗ trợ identity columns.

### 8.2. Hạn chế

Provider thường cần thực hiện INSERT để biết generated key; điều này có thể hạn chế JDBC insert batching. Với hàng nghìn Lines/Order, thử nghiệm hiệu năng riêng trước khi chọn IDENTITY cho hot write path.

### 8.3. Test không chốt thời điểm ID có giá trị

Một số provider có thể insert ngay khi `persist`, số khác defer trong một số trường hợp. Test nên `flush` rồi assert `line.getId() != null`, không ép mọi implementation gán ID ngay từ constructor hoặc trước flush.

### 8.4. IDENTITY vẫn có gaps

Rollback hoặc failed INSERT có thể tiêu thụ IDs. Không dùng `line_id` để xác định số thứ tự hiển thị của dòng đơn.

## 9. Sinh khóa PaymentAttempt bằng UUID

Jakarta Persistence 3.1:

```java
@Id
@GeneratedValue(strategy = GenerationType.UUID)
@Column(name = "attempt_id")
private UUID id;
```

PostgreSQL:

```sql
attempt_id UUID PRIMARY KEY
```

### 9.1. Ưu điểm

UUID có thể hữu ích với identifiers phân tán, tích hợp external systems hoặc tạo reference khó dự đoán hơn ID tuần tự. Nhưng UUID **không phải secret hay access token**.

### 9.2. Vấn đề cân nhắc

UUID dài hơn BIGINT; cách sinh UUID/randomness ảnh hưởng index locality và storage. Đo theo database, workload và provider thay vì khẳng định UUID luôn chậm hay nhanh.

### 9.3. Không mặc định mọi JPA version hỗ trợ GenerationType.UUID

Với Jakarta Persistence cũ hơn hoặc `javax.persistence`, có thể cần generator/provider extension khác. Code ví dụ này yêu cầu API phù hợp.

### 9.4. UUID generation khác mã thanh toán bên ngoài

Attempt ID chỉ nhận diện bản ghi trong hệ thống. Gateway payment token/transaction reference có lifecycle và security contract riêng.

---

# Phần III — Kiểu giá trị

## 10. Thiết kế Money như value object

Tiền có ít nhất **số lượng** và **đơn vị tiền**. Không lưu “120000” rồi mặc định tất cả đều là VND, đặc biệt nếu hệ thống đa tiền tệ.

```java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;
import java.util.Objects;

@Embeddable
public class Money {

    @Column(name = "amount", precision = 18, scale = 2)
    private BigDecimal amount;

    @Column(name = "currency", length = 3)
    private String currency;

    protected Money() {
        // JPA
    }

    public Money(BigDecimal amount, String currency) {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");

        String normalizedCurrency =
            currency.strip().toUpperCase(Locale.ROOT);

        if (!normalizedCurrency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                "Invalid currency code"
            );
        }

        // Bài tập dùng 2 chữ số thập phân để dễ minh họa.
        BigDecimal scaled =
            amount.setScale(2, RoundingMode.UNNECESSARY);

        if (scaled.signum() < 0) {
            throw new IllegalArgumentException(
                "Negative monetary amount"
            );
        }

        this.amount = scaled;
        this.currency = normalizedCurrency;
    }

    public static Money zero(String currency) {
        return new Money(new BigDecimal("0.00"), currency);
    }

    public BigDecimal getAmount() { return amount; }
    public String getCurrency() { return currency; }

    public Money add(Money other) {
        requireSameCurrency(other);
        return new Money(amount.add(other.amount), currency);
    }

    public Money subtract(Money other) {
        requireSameCurrency(other);
        return new Money(amount.subtract(other.amount), currency);
    }

    public Money multiply(int factor) {
        if (factor <= 0) {
            throw new IllegalArgumentException(
                "Factor must be positive"
            );
        }
        return new Money(
            amount.multiply(BigDecimal.valueOf(factor)),
            currency
        );
    }

    private void requireSameCurrency(Money other) {
        Objects.requireNonNull(other, "other");
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                "Currency mismatch"
            );
        }
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof Money other)) return false;
        return Objects.equals(amount, other.amount)
            && Objects.equals(currency, other.currency);
    }

    @Override
    public int hashCode() {
        return Objects.hash(amount, currency);
    }
}
```

### 10.1. Đây là ví dụ fixed 2-decimal

Một số tiền tệ có số chữ số thập phân quy định khác nhau; dùng `BigDecimal(...).setScale(2)` ở đây là **quy tắc thực hành**, không phải quy luật toàn cầu. Production cần currency-specific scale, rounding/FX policy và quy tắc kế toán riêng.

### 10.2. Vì sao không dùng double?

`double` không biểu diễn chính xác nhiều số thập phân cơ sở 10. Với số tiền và phép cộng nhân, `BigDecimal` giảm lỗi precision; vẫn cần định nghĩa rounding.

### 10.3. Equality và BigDecimal scale

`new BigDecimal("10.0").equals(new BigDecimal("10.00"))` là `false`. Constructor chuẩn hóa về scale 2 nên hai Money hợp lệ cùng giá trị/currency có equality nhất quán.

### 10.4. Value object không có identity độc lập

`Money` không phải entity và không được `em.find(Money.class,id)`. Nó được lưu trong các cột của owner.

### 10.5. Dữ liệu DB có thể bỏ qua constructor

Provider có thể hydrate fields theo field access. Vì vậy vẫn cần DB CHECK, NOT NULL và tests; constructor không phải phòng tuyến duy nhất nếu có writers khác.

## 11. Ánh xạ Money vào nhiều entity bằng AttributeOverride

Trong Product:

```java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "amount",
        column = @Column(
            name = "price_amount",
            nullable = false,
            precision = 18,
            scale = 2
        )
    ),
    @AttributeOverride(
        name = "currency",
        column = @Column(
            name = "price_currency",
            nullable = false,
            length = 3
        )
    )
})
private Money price;
```

Trong PurchaseOrder:

```java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "amount",
        column = @Column(
            name = "total_amount",
            nullable = false,
            precision = 18,
            scale = 2
        )
    ),
    @AttributeOverride(
        name = "currency",
        column = @Column(
            name = "total_currency",
            nullable = false,
            length = 3
        )
    )
})
private Money total;
```

Trong OrderLine:

```java
@Embedded
@AttributeOverrides({
    @AttributeOverride(
        name = "amount",
        column = @Column(
            name = "unit_price_amount",
            nullable = false,
            precision = 18,
            scale = 2
        )
    ),
    @AttributeOverride(
        name = "currency",
        column = @Column(
            name = "unit_price_currency",
            nullable = false,
            length = 3
        )
    )
})
private Money unitPrice;
```

### 11.1. Vì sao override tên cột?

Cùng class Money dùng trong nhiều bối cảnh. Nếu không override, tên `amount`/`currency` trong OrderLine hoặc Order có thể không đúng schema dự kiến.

### 11.2. AttributeOverride dùng Java property name

`name="amount"` là attribute trong `Money`, không phải SQL column `price_amount`.

### 11.3. Đừng đặt logic FX conversion trong getter

Nếu Product có currency USD còn Order muốn VND, không âm thầm `new Money(amount, "VND")`. Tỷ giá/rounding cần use case riêng với nguồn rate, thời điểm và audit.

### 11.4. Snapshot quan trọng hơn quan hệ giá hiện tại

`OrderLine.unitPrice` giữ giá tại lúc đặt; không dùng `line.getProduct().getPrice()` để tính lại hóa đơn lịch sử.

## 12. PostalAddress bằng @Embeddable

```java
@Embeddable
public class PostalAddress {

    @Column(name = "street", length = 200)
    private String street;

    @Column(name = "city", length = 100)
    private String city;

    @Column(name = "postal_code", length = 30)
    private String postalCode;

    protected PostalAddress() {}

    public PostalAddress(
            String street,
            String city,
            String postalCode
    ) {
        this.street = requireText(street);
        this.city = requireText(city);
        this.postalCode = requireText(postalCode);
    }

    private static String requireText(String s) {
        if (s == null || s.isBlank()) {
            throw new IllegalArgumentException(
                "Missing address component"
            );
        }
        return s.strip();
    }

    public String getStreet() { return street; }
    public String getCity() { return city; }
    public String getPostalCode() { return postalCode; }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof PostalAddress other)) return false;
        return Objects.equals(street, other.street)
            && Objects.equals(city, other.city)
            && Objects.equals(postalCode, other.postalCode);
    }

    @Override
    public int hashCode() {
        return Objects.hash(street, city, postalCode);
    }
}
```

### 12.1. Địa chỉ không có primary key riêng

Nó là value object thuộc Customer hoặc CustomerProfile, không phải một bản ghi Address entity tự đứng độc lập.

### 12.2. Có thể thay cả value object

Để đổi địa chỉ, gán `new PostalAddress(...)` cho owner. Việc thay cả đối tượng thường dễ kiểm chứng hơn sửa fields nội bộ qua setters.

### 12.3. Null semantics phải rõ

Nếu Customer chưa có billing address, có thể cho `billingAddress = null` và các cột nullable. Nếu nghiệp vụ bắt buộc, dùng validation và schema constraints phù hợp.

### 12.4. Hai embedded fields cùng kiểu cần override

Khi Customer.billingAddress và CustomerProfile.defaultShippingAddress đều là PostalAddress, dùng tên cột riêng giúp mapping rõ; nếu hai địa chỉ cùng nằm trên **một entity**, override là đặc biệt quan trọng để tránh đụng cột.

## 13. EmailAddress: value object lưu trong một cột

Email không cần ba cột như PostalAddress. Có thể dùng converter để ánh xạ `EmailAddress ↔ VARCHAR`.

```java
import java.util.Locale;
import java.util.Objects;

public final class EmailAddress {

    private final String value;

    public EmailAddress(String raw) {
        Objects.requireNonNull(raw, "email");

        String normalized =
            raw.strip().toLowerCase(Locale.ROOT);

        if (normalized.isBlank() || normalized.length() > 320
                || !normalized.contains("@")) {
            throw new IllegalArgumentException(
                "Invalid email"
            );
        }
        this.value = normalized;
    }

    public String value() { return value; }

    @Override
    public boolean equals(Object obj) {
        return obj instanceof EmailAddress other
            && value.equals(other.value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }
}
```

Đây là **validation đơn giản phục vụ bài tập**, không phải bộ kiểm tra email theo tất cả RFC và chính sách internationalized email. Production cần định nghĩa normalization phù hợp với business, Unicode/locale và DB uniqueness strategy.

Converter:

```java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = false)
public class EmailAddressConverter
        implements AttributeConverter<EmailAddress, String> {

    @Override
    public String convertToDatabaseColumn(
            EmailAddress attribute
    ) {
        return attribute == null
            ? null
            : attribute.value();
    }

    @Override
    public EmailAddress convertToEntityAttribute(
            String dbValue
    ) {
        return dbValue == null
            ? null
            : new EmailAddress(dbValue);
    }
}
```

Mapping trong Customer:

```java
@Convert(converter = EmailAddressConverter.class)
@Column(name = "email", nullable = false, length = 320)
private EmailAddress email;
```

### 13.1. Converter hoạt động hai chiều

Persist chuyển value object thành String; hydrate xây lại value object. Test **DB raw column** để chắc không chỉ đang so sánh một managed Java instance.

### 13.2. Converter không tự tạo UNIQUE

Nếu email chuẩn hóa phải duy nhất trong tenant, DB cần constraint `UNIQUE(tenant_id,email)`, không chỉ một `existsByEmail` ở service.

### 13.3. Không mặc định converter chạy trên mọi loại thuộc tính

Identifier/version/relationships và những mappings đặc biệt có giới hạn theo JPA/provider. Ví dụ dùng converter cho basic attribute `Customer.email`, không dùng cho `@Id`.

### 13.4. Giá trị bí mật/PII vẫn có thể bị log

Một EmailAddress object có thể chứa dữ liệu cá nhân; `AttributeConverter` không che Hibernate bind logger hay entity `toString()`. Không log raw email để “debug” mapping.

## 14. Enum mapping và migration

Trạng thái:

```java
public enum OrderStatus {
    DRAFT, SUBMITTED, PAID, SHIPPED, CANCELLED
}

public enum PaymentAttemptStatus {
    CREATED, AUTHORIZED, DECLINED, FAILED
}
```

Mapping:

```java
@Enumerated(EnumType.STRING)
@Column(name = "status", nullable = false, length = 24)
private OrderStatus status;
```

### 14.1. STRING thay vì ORDINAL

`ORDINAL` lưu vị trí 0,1,2...; chèn enum constant ở giữa có thể làm sai ý nghĩa dữ liệu cũ. `STRING` đọc được, dễ migration hơn.

### 14.2. Đổi tên enum cũng là schema/data migration

Nếu đổi `SUBMITTED` thành `CONFIRMED`, cần xử lý rows cũ trước khi provider hydrate, đặc biệt nếu có CHECK constraint giới hạn status.

### 14.3. DB CHECK và Java enum nên cùng hợp đồng

Một CHECK `status IN ('DRAFT','SUBMITTED',...)` là hàng rào với external writers. Khi thêm trạng thái, cập nhật migration/test cùng code.

---

# Phần IV — Ánh xạ các entity

## 15. Customer: khóa sinh và email duy nhất theo tenant

```java
import jakarta.persistence.*;
import java.util.Objects;

@Entity
@Table(
    name = "customer",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customer_tenant_email",
        columnNames = {"tenant_id", "email"}
    )
)
public class Customer {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "customer_id_gen"
    )
    @SequenceGenerator(
        name = "customer_id_gen",
        sequenceName = "customer_id_seq",
        allocationSize = 1
    )
    @Column(name = "customer_id")
    private Long id;

    @Column(name = "tenant_id", nullable = false, length = 64)
    private String tenantId;

    @Convert(converter = EmailAddressConverter.class)
    @Column(name = "email", nullable = false, length = 320)
    private EmailAddress email;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(name = "billing_street")
        ),
        @AttributeOverride(
            name = "city",
            column = @Column(name = "billing_city")
        ),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(name = "billing_postal_code")
        )
    })
    private PostalAddress billingAddress;

    @Version
    @Column(name = "row_version")
    private Long version;

    protected Customer() {}

    public Customer(
            String tenantId,
            EmailAddress email,
            PostalAddress billingAddress
    ) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException(
                "Tenant required"
            );
        }
        this.tenantId = tenantId;
        this.email = Objects.requireNonNull(email);
        this.billingAddress = billingAddress;
    }

    public Long getId() { return id; }
    public String getTenantId() { return tenantId; }
    public EmailAddress getEmail() { return email; }
    public PostalAddress getBillingAddress() {
        return billingAddress;
    }

    public void changeBillingAddress(PostalAddress next) {
        billingAddress = next;
    }
}
```

### 15.1. Vì sao không có Customer.orders?

Order có `@ManyToOne Customer` là đủ để lưu FK. Không bắt buộc dựng collection nghịch trên Customer nếu không có use case điều hướng đó. Giảm một collection cũng giảm nguy cơ lazy loading và cascade vô tình.

### 15.2. Khóa sinh khác khóa nghiệp vụ

`customer_id` là primary key, còn `(tenant_id,email)` là business uniqueness. Có thể thay email mà không thay identity. Business uniqueness cần xử lý conflict/trạng thái transaction.

### 15.3. Không dùng @Column(unique=true) cho email toàn hệ thống

`unique=true` trên email một cột sẽ cấm hai tenants cùng email, có thể sai yêu cầu. Dùng composite constraint đúng scope.

### 15.4. Không mặc định DB UNIQUE là case-insensitive

Để bảo đảm `Alice@Example` và `alice@example` không trùng theo business, normalization và DB collation/index phải nhất quán. Converter chỉ một đường ghi; DB writers khác vẫn có thể bypass normalization.

---

## 16. Product: khóa sinh và Money

```java
@Entity
@Table(
    name = "product",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_product_tenant_sku",
        columnNames = {"tenant_id", "sku"}
    )
)
public class Product {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "product_id_gen"
    )
    @SequenceGenerator(
        name = "product_id_gen",
        sequenceName = "product_id_seq",
        allocationSize = 1
    )
    @Column(name = "product_id")
    private Long id;

    @Column(name = "tenant_id", nullable = false, length = 64)
    private String tenantId;

    @Column(name = "sku", nullable = false, length = 80)
    private String sku;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "amount",
            column = @Column(
                name = "price_amount",
                nullable = false,
                precision = 18,
                scale = 2
            )
        ),
        @AttributeOverride(
            name = "currency",
            column = @Column(
                name = "price_currency",
                nullable = false,
                length = 3
            )
        )
    })
    private Money price;

    @Column(name = "active", nullable = false)
    private boolean active;

    protected Product() {}

    public Product(
            String tenantId,
            String sku,
            Money price
    ) {
        this.tenantId = Objects.requireNonNull(tenantId);
        this.sku = Objects.requireNonNull(sku);
        this.price = Objects.requireNonNull(price);
        this.active = true;
    }

    public Long getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getSku() { return sku; }
    public Money getPrice() { return price; }
    public boolean isActive() { return active; }

    public void changePrice(Money next) {
        this.price = Objects.requireNonNull(next);
    }

    public void deactivate() { active = false; }
}
```

### 16.1. Giá Product có thể đổi

OrderLine giữ snapshot unitPrice, nên sửa Product.price không làm thay đổi giá những Orders đã tạo.

### 16.2. Không cascade persist tới Product từ Line

Product là shared reference. Persist Order không nên tự tạo Product hoặc xóa Product khi một Order bị xóa.

### 16.3. Unique SKU theo tenant

Nếu `shop-a` và `shop-b` cùng dùng SKU `BOOK-JPA`, đó là hợp lệ trong schema này. Trong cùng tenant, trùng SKU bị từ chối.

---

## 17. PurchaseOrder: aggregate root

Order kiểm soát vòng đời các Lines và tổng tiền.

```java
@Entity
@Table(
    name = "purchase_order",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_order_tenant_external",
        columnNames = {"tenant_id", "external_code"}
    )
)
public class PurchaseOrder {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "order_id_gen"
    )
    @SequenceGenerator(
        name = "order_id_gen",
        sequenceName = "order_id_seq",
        allocationSize = 1
    )
    @Column(name = "order_id")
    private Long id;

    @Column(name = "tenant_id", nullable = false, length = 64)
    private String tenantId;

    @Column(name = "external_code", nullable = false, length = 96)
    private String externalCode;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 24)
    private OrderStatus status;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "amount",
            column = @Column(
                name = "total_amount",
                nullable = false,
                precision = 18,
                scale = 2
            )
        ),
        @AttributeOverride(
            name = "currency",
            column = @Column(
                name = "total_currency",
                nullable = false,
                length = 3
            )
        )
    })
    private Money total;

    @Column(name = "next_line_no", nullable = false)
    private int nextLineNumber;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Version
    @Column(name = "row_version")
    private Long version;

    @OneToMany(
        mappedBy = "order",
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    @OrderBy("lineNumber ASC")
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public PurchaseOrder(
            String tenantId,
            Customer customer,
            String externalCode,
            String currency,
            Instant createdAt
    ) {
        this.tenantId = Objects.requireNonNull(tenantId);
        this.customer = Objects.requireNonNull(customer);

        if (!tenantId.equals(customer.getTenantId())) {
            throw new IllegalArgumentException(
                "Customer belongs to a different tenant"
            );
        }
        if (externalCode == null
                || externalCode.isBlank()) {
            throw new IllegalArgumentException(
                "External code required"
            );
        }

        this.externalCode = externalCode;
        this.createdAt = Objects.requireNonNull(createdAt);
        this.status = OrderStatus.DRAFT;
        this.total = Money.zero(currency);
        this.nextLineNumber = 1;
    }

    public Long getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getExternalCode() { return externalCode; }
    public Customer getCustomer() { return customer; }
    public OrderStatus getStatus() { return status; }
    public Money getTotal() { return total; }
    public Long getVersion() { return version; }

    public List<OrderLine> getLines() {
        return Collections.unmodifiableList(lines);
    }

    public void addLine(Product product, int quantity) {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Cannot edit non-draft order"
            );
        }
        Objects.requireNonNull(product, "product");

        if (!tenantId.equals(product.getTenantId())) {
            throw new IllegalArgumentException(
                "Product belongs to a different tenant"
            );
        }
        if (!product.isActive()) {
            throw new IllegalStateException(
                "Inactive product"
            );
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive"
            );
        }

        Money unitPrice = product.getPrice();
        Money lineTotal = unitPrice.multiply(quantity);

        // Currency mismatch also rejected by Money.add().
        Money newTotal = total.add(lineTotal);

        OrderLine line = new OrderLine(
            this,
            product,
            nextLineNumber++,
            quantity,
            unitPrice
        );
        lines.add(line);
        total = newTotal;
    }

    public void submit() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Order already left draft state"
            );
        }
        if (lines.isEmpty()) {
            throw new IllegalStateException(
                "Cannot submit empty order"
            );
        }
        status = OrderStatus.SUBMITTED;
    }

    public void markPaid() {
        if (status != OrderStatus.SUBMITTED) {
            throw new IllegalStateException(
                "Only submitted order can be paid"
            );
        }
        status = OrderStatus.PAID;
    }
}
```

Imports cần có `java.util.*`, `java.time.Instant`, Jakarta Persistence. Để ngắn gọn, các snippets trong bài chỉ đưa imports trọng tâm ở một số nơi.

### 17.1. PurchaseOrder là phía nghịch của quan hệ Lines

`mappedBy="order"` nghĩa là `OrderLine.order` sở hữu foreign key `order_id`. Thêm line vào `lines` **chưa đủ** nếu không gán `line.order = this` trong constructor.

### 17.2. Cascade và orphanRemoval

`cascade = ALL` cho phép persist/remove/merge Lines theo lifecycle Order. `orphanRemoval=true` cho phép loại Line ra khỏi collection và để provider xóa row child theo semantics phù hợp. **Không áp cùng cascade cho Customer/Product shared entities**.

### 17.3. Giá và tổng tiền được lưu nhất quán trong method

Tính `newTotal` trước khi thêm Line giúp tránh việc thêm child rồi mới phát hiện currency mismatch khiến object graph trong bộ nhớ rơi vào trạng thái dở dang.

### 17.4. Tại sao có nextLineNumber?

Nếu đánh số bằng `lines.size()+1`, xóa dòng rồi thêm dòng mới có thể tái sử dụng `line_no` và va chạm với các rows chưa flush/orphan-deleted. Một counter tăng đơn điệu đơn giản hơn. Vì là field persisted, nó cũng giúp giữ thứ tự khi entity được load lại.

### 17.5. Không dùng tổng tiền trong Order để tin cậy tuyệt đối mọi writer

Nếu một script SQL thay `order_line` trực tiếp mà không cập nhật `purchase_order.total_amount`, CHECK trên một row không thể tự đảm bảo SUM các Lines đúng. Cần quy định writers đi qua aggregate/service hoặc xây DB-level invariant riêng.

### 17.6. Optimistic locking

`@Version` phát hiện stale updates của Order row. Khi nghiệp vụ chỉ sửa child mà không sửa state parent, **không giả định** mọi provider sẽ tăng Order.version; nếu cần aggregate-wide version, thiết kế force increment/explicit parent update có test concurrency.

### 17.7. Không trả managed List ra public mutation API

`Collections.unmodifiableList` giúp bên ngoài không thay collection mà không qua `addLine`. JPA truy cập field trực tiếp nên vẫn quản lý persistent collection được; cần test provider/lifecycle cụ thể.

---

## 18. OrderLine: owner của hai quan hệ ManyToOne

```java
@Entity
@Table(
    name = "order_line",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_order_line_number",
        columnNames = {"order_id", "line_no"}
    )
)
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "line_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id", nullable = false)
    private Product product;

    @Column(name = "line_no", nullable = false)
    private int lineNumber;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "amount",
            column = @Column(
                name = "unit_price_amount",
                nullable = false,
                precision = 18,
                scale = 2
            )
        ),
        @AttributeOverride(
            name = "currency",
            column = @Column(
                name = "unit_price_currency",
                nullable = false,
                length = 3
            )
        )
    })
    private Money unitPrice;

    protected OrderLine() {}

    OrderLine(
            PurchaseOrder order,
            Product product,
            int lineNumber,
            int quantity,
            Money unitPrice
    ) {
        this.order = Objects.requireNonNull(order);
        this.product = Objects.requireNonNull(product);
        this.lineNumber = lineNumber;
        this.quantity = quantity;
        this.unitPrice = Objects.requireNonNull(unitPrice);
    }

    public Long getId() { return id; }
    public int getLineNumber() { return lineNumber; }
    public int getQuantity() { return quantity; }
    public Product getProduct() { return product; }
    public Money getUnitPrice() { return unitPrice; }

    public Money subtotal() {
        return unitPrice.multiply(quantity);
    }
}
```

### 18.1. Sở hữu FK

Trong `order_line` có `order_id` và `product_id`, nên hai `@ManyToOne` ở OrderLine là owning sides. `mappedBy` chỉ dùng ở phía nghịch của `PurchaseOrder.lines`.

### 18.2. Không cascade tới Product

OrderLine tham chiếu Product đã tồn tại. Việc xóa một Order không được xóa Product khỏi catalog.

### 18.3. Snapshot price

`unitPrice` được copy theo giá trị Money tại lúc tạo Line. Nó **không** tự liên kết đồng bộ với `Product.price`, đó là hành vi mong muốn của đơn hàng lịch sử.

### 18.4. Giá trị và cột NOT NULL

Constructor bảo vệ quantity/price qua aggregate, nhưng database CHECK `quantity > 0` và NOT NULL vẫn cần để ngăn writers bypass application.

### 18.5. Không tự cập nhật quantity từ bên ngoài

Nếu có `setQuantity` public, total trong PurchaseOrder có thể stale. Thiết kế mutation method trên aggregate để tính lại total một cách nhất quán.

---

## 19. Quan hệ một-một dùng chung khóa bằng @MapsId

Mỗi Customer có tối đa một CustomerProfile. Thay vì sinh thêm `profile_id` độc lập, profile dùng luôn `customer_id` làm primary key:

```java
@Entity
@Table(name = "customer_profile")
public class CustomerProfile {

    @Id
    @Column(name = "customer_id")
    private Long id;

    @MapsId
    @OneToOne(
        fetch = FetchType.LAZY,
        optional = false
    )
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Embedded
    @AttributeOverrides({
        @AttributeOverride(
            name = "street",
            column = @Column(
                name = "default_shipping_street"
            )
        ),
        @AttributeOverride(
            name = "city",
            column = @Column(
                name = "default_shipping_city"
            )
        ),
        @AttributeOverride(
            name = "postalCode",
            column = @Column(
                name = "default_shipping_postal_code"
            )
        )
    })
    private PostalAddress defaultShippingAddress;

    protected CustomerProfile() {}

    public CustomerProfile(
            Customer customer,
            PostalAddress shippingAddress
    ) {
        this.customer = Objects.requireNonNull(customer);
        this.defaultShippingAddress = shippingAddress;
    }

    public Long getId() { return id; }
    public Customer getCustomer() { return customer; }
    public PostalAddress getDefaultShippingAddress() {
        return defaultShippingAddress;
    }
}
```

### 19.1. @MapsId nghĩa là gì?

`CustomerProfile.id` được dẫn xuất từ `Customer.id`. Một row profile có `customer_id` vừa là PK vừa là FK. Không có independent generated identifier cho Profile.

### 19.2. Vì sao chỉ ánh xạ một chiều?

Chúng ta không khai `Customer.profile` inverse để giảm độ phức tạp lazy to-one trong bài tập. Khi cần inverse relation, thêm `@OneToOne(mappedBy="customer")` có mục đích và test fetch behavior trên provider.

### 19.3. Lưu profile đúng thứ tự

```java
Customer customer = new Customer(
    tenant, new EmailAddress("demo@example.invalid"), null
);
em.persist(customer);

CustomerProfile profile = new CustomerProfile(
    customer,
    new PostalAddress(
        "12 Main Street", "Da Nang", "550000"
    )
);
em.persist(profile);
em.flush();

assertEquals(customer.getId(), profile.getId());
```

ID của Customer dùng SEQUENCE; `@MapsId` cung cấp cùng ID cho Profile. Thời điểm sync ID cụ thể tùy provider; assert sau flush.

### 19.4. Shared PK enforce tối đa một profile

PK trên `customer_profile.customer_id` ngăn tạo profile thứ hai cho cùng customer, ngay cả khi code application bị gọi đồng thời.

### 19.5. Profile không được cascade remove Customer

Profile là dependent record. Nếu xóa Profile, không xóa Customer shared parent. Không đặt `CascadeType.REMOVE` từ Profile tới Customer.

---

## 20. PaymentAttempt với UUID và ManyToOne

```java
@Entity
@Table(
    name = "payment_attempt",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_attempt_order_no",
        columnNames = {"order_id", "attempt_no"}
    )
)
public class PaymentAttempt {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    @Column(name = "attempt_id")
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @Column(name = "attempt_no", nullable = false)
    private int attemptNo;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false, length = 24)
    private PaymentAttemptStatus status;

    @Column(name = "provider_ref", length = 120)
    private String providerReference;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected PaymentAttempt() {}

    public PaymentAttempt(
            PurchaseOrder order,
            int attemptNo,
            Instant createdAt
    ) {
        this.order = Objects.requireNonNull(order);
        if (attemptNo <= 0) {
            throw new IllegalArgumentException(
                "Invalid attempt number"
            );
        }
        this.attemptNo = attemptNo;
        this.createdAt = Objects.requireNonNull(createdAt);
        this.status = PaymentAttemptStatus.CREATED;
    }

    public UUID getId() { return id; }
    public int getAttemptNo() { return attemptNo; }
    public PaymentAttemptStatus getStatus() {
        return status;
    }

    public void authorized(String safeProviderReference) {
        if (status != PaymentAttemptStatus.CREATED) {
            throw new IllegalStateException(
                "Invalid payment transition"
            );
        }
        status = PaymentAttemptStatus.AUTHORIZED;
        providerReference = safeProviderReference;
    }
}
```

### 20.1. Một Order có nhiều attempts

`@ManyToOne` từ PaymentAttempt → PurchaseOrder đủ để biểu diễn quan hệ. Không cần collection ngược nếu không có use case.

### 20.2. UNIQUE(order_id,attempt_no)

Nếu hai workers cố tạo attempt #1 cho cùng Order, DB chặn duplicate. `attemptNo` không tự sinh an toàn bằng `MAX+1` trong concurrency; cần allocator/lock/idempotency hợp lý.

### 20.3. Không cascade Order từ PaymentAttempt

Một PaymentAttempt mới chỉ tham chiếu Order đã có. Không được vô tình persist lại hoặc xóa Order khi thao tác Attempt.

### 20.4. External payment side effects

Ví dụ này chỉ lưu state. Gọi payment gateway cần luồng idempotency/outbox/reconciliation riêng; **không giữ DB transaction mở trong khi chờ remote call** mà không có thiết kế đầy đủ.

### 20.5. UUID không phải bearer credential

Biết attempt UUID không đồng nghĩa được quyền xem hay sửa PaymentAttempt; mọi query cần authorization/tenant scope.

---

# Phần V — Ràng buộc vật lý bằng migration

## 21. Migration PostgreSQL tổng thể

Một migration ban đầu có thể được chia versioned files thực tế; dưới đây ghép thành một script để thấy PK/FK/UNIQUE/CHECK.

```sql
-- Ví dụ PostgreSQL. Chạy trên database thử nghiệm riêng.
CREATE SEQUENCE customer_id_seq
    START WITH 1 INCREMENT BY 1;

CREATE SEQUENCE product_id_seq
    START WITH 1 INCREMENT BY 1;

CREATE SEQUENCE order_id_seq
    START WITH 1 INCREMENT BY 1;

CREATE TABLE customer (
    customer_id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    email VARCHAR(320) NOT NULL,
    billing_street VARCHAR(200),
    billing_city VARCHAR(100),
    billing_postal_code VARCHAR(30),
    row_version BIGINT,
    CONSTRAINT uk_customer_tenant_email
        UNIQUE (tenant_id, email)
);

CREATE TABLE product (
    product_id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    sku VARCHAR(80) NOT NULL,
    price_amount NUMERIC(18,2) NOT NULL,
    price_currency VARCHAR(3) NOT NULL,
    active BOOLEAN NOT NULL,
    CONSTRAINT uk_product_tenant_sku
        UNIQUE (tenant_id, sku),
    CONSTRAINT ck_product_price_nonnegative
        CHECK (price_amount >= 0)
);

CREATE TABLE purchase_order (
    order_id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    customer_id BIGINT NOT NULL,
    external_code VARCHAR(96) NOT NULL,
    status VARCHAR(24) NOT NULL,
    total_amount NUMERIC(18,2) NOT NULL,
    total_currency VARCHAR(3) NOT NULL,
    next_line_no INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    row_version BIGINT,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer(customer_id),
    CONSTRAINT uk_order_tenant_external
        UNIQUE (tenant_id, external_code),
    CONSTRAINT ck_order_total_nonnegative
        CHECK (total_amount >= 0),
    CONSTRAINT ck_order_next_line_positive
        CHECK (next_line_no >= 1),
    CONSTRAINT ck_order_status
        CHECK (
            status IN (
                'DRAFT','SUBMITTED','PAID',
                'SHIPPED','CANCELLED'
            )
        )
);

CREATE TABLE order_line (
    line_id BIGINT GENERATED BY DEFAULT AS IDENTITY
        PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price_amount NUMERIC(18,2) NOT NULL,
    unit_price_currency VARCHAR(3) NOT NULL,
    CONSTRAINT fk_line_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_order(order_id),
    CONSTRAINT fk_line_product
        FOREIGN KEY (product_id)
        REFERENCES product(product_id),
    CONSTRAINT uk_order_line_number
        UNIQUE (order_id, line_no),
    CONSTRAINT ck_line_quantity_positive
        CHECK (quantity > 0),
    CONSTRAINT ck_line_no_positive
        CHECK (line_no > 0),
    CONSTRAINT ck_line_price_nonnegative
        CHECK (unit_price_amount >= 0)
);

CREATE TABLE customer_profile (
    customer_id BIGINT PRIMARY KEY,
    default_shipping_street VARCHAR(200),
    default_shipping_city VARCHAR(100),
    default_shipping_postal_code VARCHAR(30),
    CONSTRAINT fk_profile_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer(customer_id)
);

CREATE TABLE payment_attempt (
    attempt_id UUID PRIMARY KEY,
    order_id BIGINT NOT NULL,
    attempt_no INTEGER NOT NULL,
    status VARCHAR(24) NOT NULL,
    provider_ref VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT fk_attempt_order
        FOREIGN KEY (order_id)
        REFERENCES purchase_order(order_id),
    CONSTRAINT uk_attempt_order_no
        UNIQUE (order_id, attempt_no),
    CONSTRAINT ck_attempt_no_positive
        CHECK (attempt_no > 0),
    CONSTRAINT ck_attempt_status
        CHECK (
            status IN (
                'CREATED','AUTHORIZED',
                'DECLINED','FAILED'
            )
        )
);

CREATE INDEX idx_order_tenant_created_id
    ON purchase_order(
        tenant_id,
        created_at DESC,
        order_id DESC
    );

CREATE INDEX idx_line_order
    ON order_line(order_id);

CREATE INDEX idx_attempt_order
    ON payment_attempt(order_id);
```

### 21.1. Đây là schema khởi đầu, không phải bản production hoàn chỉnh

Có thể cần thêm indexes, partitioning, timestamps audit, currency domain constraints, TLS/roles, RLS, data retention và foreign key tenant consistency. Thêm constraints theo business requirements thực, không sao chép DDL vô điều kiện.

### 21.2. Vì sao có FK từ Line đến Product?

Line không thể tham chiếu Product chưa tồn tại nếu FK được thực thi. Nhưng FK chỉ khẳng định **Product tồn tại**, chưa khẳng định Product cùng tenant hoặc active.

### 21.3. Vì sao cần UNIQUE ngoài PK?

PK của Order là `order_id`, còn externalCode là một business identifier có scope tenant. Các ràng buộc giải quyết vấn đề khác nhau.

### 21.4. Database CHECK không thay domain validation

Java kiểm tra quantity trước khi gọi DB để phản hồi rõ; CHECK bảo vệ database nếu một code path hoặc external writer bỏ qua Java.

### 21.5. Database constraints còn cần test trên migrations thật

Annotations trong entity không bảo đảm migration đã tạo constraints. Integration tests nên xác minh cả hành vi vi phạm constraint và schema catalog khi cần.

### 21.6. Lưu ý row_version

Trong ví dụ JPA, `@Version Long` được provider khởi tạo và cập nhật; schema column có thể nullable lúc đầu cho phù hợp quản lý migration/legacy rows, nhưng deployment hoàn chỉnh nên xác định default/backfill/NOT NULL policy theo provider và dữ liệu thực. Không tự sửa version từ application.

---

## 22. Khoảng trống của FK một cột trong multi-tenancy

Schema ở phần 21 có:

```sql
FOREIGN KEY (customer_id)
REFERENCES customer(customer_id)
```

Điều này **chỉ đảm bảo Customer tồn tại**. Nó **không đảm bảo** `purchase_order.tenant_id = customer.tenant_id`.

Ví dụ sai nhưng FK một cột vẫn chấp nhận:

```text
customer:
  customer_id=7, tenant_id='shop-b'

purchase_order:
  order_id=99, tenant_id='shop-a', customer_id=7
```

### 22.1. Phòng tuyến application

Constructor Order kiểm tra `tenantId.equals(customer.getTenantId())`, và service truy vấn Customer theo cả ID và authorized tenant. Đây là lớp bảo vệ cần thiết cho use case.

### 22.2. Nếu cần DB enforce cùng tenant

Có thể tạo composite unique key trên Customer:

```sql
ALTER TABLE customer
ADD CONSTRAINT uk_customer_tenant_id
UNIQUE (tenant_id, customer_id);
```

Rồi thay FK đơn bằng composite FK:

```sql
ALTER TABLE purchase_order
DROP CONSTRAINT fk_order_customer;

ALTER TABLE purchase_order
ADD CONSTRAINT fk_order_customer_tenant
FOREIGN KEY (tenant_id, customer_id)
REFERENCES customer(tenant_id, customer_id);
```

Để JPA mapping phù hợp với schema **biến thể này**, thay `PurchaseOrder.customer` bằng `@JoinColumns`, trong đó cột tenant_id đã được mapping writable bởi `PurchaseOrder.tenantId`:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumns({
    @JoinColumn(
        name = "tenant_id",
        referencedColumnName = "tenant_id",
        insertable = false,
        updatable = false,
        nullable = false
    ),
    @JoinColumn(
        name = "customer_id",
        referencedColumnName = "customer_id",
        nullable = false
    )
})
private Customer customer;
```

**Đây là biến thể nâng cao của mapping**, không dùng đồng thời với `@JoinColumn(name="customer_id")` trong bản cơ bản. Composite uniqueness/FK của Product trong OrderLine cũng cần nghiên cứu nếu DB phải enforce tenant relationship ở tầng line; đơn thuần bổ sung tenant filter ở query không tự bảo vệ mọi writers.

### 22.3. Why DB constraints matter

Nếu có batch import/native SQL hoặc service khác ghi trực tiếp, application constructor không chạy; composite FK có thể ngăn dữ liệu cross-tenant sai được committed.

### 22.4. RLS và authorization

PostgreSQL Row Level Security có thể hỗ trợ bảo vệ truy vấn/ghi theo tenant với cấu hình phù hợp, nhưng không thay thế mọi PK/FK/domain invariant và cần test cẩn thận theo connection/session context.

---

## 23. Vòng đời quan hệ và cascade matrix

| Quan hệ | Phía sở hữu | Cascade trong bài | Vì sao? |
|---|---|---|---|
| PurchaseOrder → Customer (ManyToOne) | PurchaseOrder.customer | Không | Customer tồn tại độc lập |
| PurchaseOrder → Lines (OneToMany) | OrderLine.order sở hữu FK | ALL + orphanRemoval | Lines thuộc Order aggregate |
| OrderLine → Product (ManyToOne) | OrderLine.product | Không | Product catalog shared |
| CustomerProfile → Customer (OneToOne) | CustomerProfile.customer | Không | Shared PK nhưng Customer độc lập |
| PaymentAttempt → PurchaseOrder (ManyToOne) | PaymentAttempt.order | Không | Attempt có lifecycle riêng |

### 23.1. CascadeType.PERSIST

Khi `em.persist(order)`, provider có thể persist các Lines trong `order.lines` vì `cascade=ALL` bao gồm PERSIST.

### 23.2. CascadeType.REMOVE

Khi xóa Order bằng `em.remove(order)`, Lines có thể bị xóa theo cascade. Tuy nhiên PaymentAttempts có FK tới Order: nếu đã có Attempts mà không có deletion policy, DB có thể chặn remove Order. Đây thường là mong muốn để tránh xóa lịch sử tài chính. Nhiều hệ thống chọn soft-delete/retention thay hard delete.

### 23.3. orphanRemoval không phải xóa “mọi quan hệ”

Nếu remove Line khỏi collection được quản lý, orphanRemoval có thể xóa row Line. Nó không cho phép xóa Product mà Line tham chiếu.

### 23.4. Bidirectional helper

Trong mapping này `addLine` thiết lập cả hai phía khi tạo child. Nếu thêm `removeLine`, hãy đồng bộ collection và owning side theo provider/lifecycle:

```java
public void removeLine(OrderLine line) {
    if (status != OrderStatus.DRAFT) {
        throw new IllegalStateException(
            "Cannot edit non-draft order"
        );
    }
    if (lines.remove(line)) {
        total = total.subtract(line.subtotal());
        line.detachFromOrder();
    }
}
```

`detachFromOrder()` là method package-private bổ sung trên `OrderLine` đặt `order = null`. Với `orphanRemoval`, provider sẽ xóa orphan khi flush; không nên cho bên ngoài tự gọi setter làm mất FK rồi giữ Line sống. Cần integration test SQL ordering/constraint theo provider. Với line chưa từng persist, remove chỉ điều chỉnh object graph trong memory.

### 23.5. Không dùng cascade “cho tiện” trên mọi @ManyToOne

Một thao tác xóa Order nếu cascade REMOVE tới Customer/Product có thể gây mất dữ liệu nghiêm trọng hoặc FK conflicts. Cascade phải theo **quyền sở hữu vòng đời**, không theo khả năng điều hướng Java.

---

# Phần VI — Luồng nghiệp vụ có transaction

## 24. Tạo Order và Lines trong một transaction

Các input types:

```java
public record DraftLineInput(
    Long productId,
    int quantity
) {}

public record CreateDraftCommand(
    Long customerId,
    String externalCode,
    String currency,
    List<DraftLineInput> lines
) {}
```

Service dùng authorized tenant từ authenticated context, không tin tenant do client tự gửi:

```java
@Service
public class CheckoutService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public Long createDraft(
            String authorizedTenant,
            CreateDraftCommand cmd
    ) {
        Objects.requireNonNull(cmd);
        if (cmd.lines() == null
                || cmd.lines().isEmpty()) {
            throw new IllegalArgumentException(
                "Order must have lines"
            );
        }
        if (cmd.lines().size() > 100) {
            throw new IllegalArgumentException(
                "Too many lines"
            );
        }

        Customer customer = em.createQuery(
            """
            select c
            from Customer c
            where c.id = :id
              and c.tenantId = :tenant
            """,
            Customer.class
        )
        .setParameter("id", cmd.customerId())
        .setParameter("tenant", authorizedTenant)
        .getResultStream()
        .findFirst()
        .orElseThrow(() ->
            new IllegalArgumentException(
                "Customer unavailable"
            )
        );

        Set<Long> productIds = cmd.lines().stream()
            .map(DraftLineInput::productId)
            .collect(Collectors.toSet());

        List<Product> products = em.createQuery(
            """
            select p
            from Product p
            where p.id in :ids
              and p.tenantId = :tenant
              and p.active = true
            """,
            Product.class
        )
        .setParameter("ids", productIds)
        .setParameter("tenant", authorizedTenant)
        .getResultList();

        Map<Long, Product> byId = products.stream()
            .collect(Collectors.toMap(
                Product::getId,
                Function.identity()
            ));

        PurchaseOrder order = new PurchaseOrder(
            authorizedTenant,
            customer,
            cmd.externalCode(),
            cmd.currency(),
            Instant.now()
        );

        for (DraftLineInput input : cmd.lines()) {
            Product product = byId.get(input.productId());
            if (product == null) {
                throw new IllegalArgumentException(
                    "Product unavailable"
                );
            }
            order.addLine(product, input.quantity());
        }

        em.persist(order); // Cascades to OrderLine.
        em.flush();        // Force SQL/constraints early.
        return order.getId();
    }
}
```

Required imports: `java.util.*`, `java.util.function.Function`, `java.util.stream.Collectors`, `java.time.Instant` và Spring/JPA annotations phù hợp. Project thực nên inject `Clock` thay `Instant.now()` để tests xác định được thời gian; cũng cần validation cho `null` productId, duplicate externalCode, request size, consistency và idempotency.

### 24.1. Vì sao preload Products theo IDs?

Nếu mỗi Line gọi `em.find(Product.class,id)` riêng, có thể tạo N database lookups. Bounded set query giúp giảm round-trips. Với quá nhiều IDs, cần chunking/DB limits.

### 24.2. Đảm bảo tenant từ nguồn đáng tin

Service nhận `authorizedTenant` đã được xác minh từ security context. Query Customer/Product đều lọc tenant, constructor Order kiểm tra ownership một lần nữa.

### 24.3. Cascade persist

`em.persist(order)` đưa Order và các Line đã add vào persistence context. Provider phát INSERT root/children khi phù hợp; `em.flush()` giúp quan sát sớm constraints, nhưng **không commit**.

### 24.4. Lỗi bất kỳ phải rollback

Nếu dòng thứ ba vi phạm constraint hoặc duplicate externalCode, transaction nên rollback toàn bộ INSERTs. Không catch exception rồi trả success/ID nếu commit thất bại.

### 24.5. Không tự tin rằng externalCode là idempotency đầy đủ

Unique externalCode ngăn duplicate row, nhưng một request retry sau timeout có thể không biết transaction đầu đã commit hay chưa. API idempotency cần policy đọc kết quả cũ, xác minh payload, xử lý conflict và side effects.

### 24.6. Việc trả ID không có nghĩa client đã thấy committed data

Nếu transaction proxy commit xảy ra sau khi method return, lỗi commit có thể ngăn response thành công; test ở boundary bao trùm method/transaction.

---

## 25. Cập nhật trạng thái qua managed entity

```java
@Transactional
public void submitOrder(
        String authorizedTenant,
        Long orderId
) {
    PurchaseOrder order = em.createQuery(
        """
        select o
        from PurchaseOrder o
        where o.id = :id
          and o.tenantId = :tenant
        """,
        PurchaseOrder.class
    )
    .setParameter("id", orderId)
    .setParameter("tenant", authorizedTenant)
    .getResultStream()
    .findFirst()
    .orElseThrow(() ->
        new IllegalArgumentException(
            "Order unavailable"
        )
    );

    order.submit();
    // JPA dirty checking flushes state and @Version.
}
```

### 25.1. Không gọi em.merge() chỉ vì sửa field

`order` là managed instance trả về từ query trong transaction. Dirty checking đồng bộ changes; gọi merge lại thường thừa.

### 25.2. @Version kiểm tra stale row

Provider thường phát conditional update dựa trên ID/version; nếu một transaction khác đã thay Order, transaction này có thể nhận optimistic conflict ở flush/commit.

### 25.3. Submit cần có Lines

`order.submit()` kiểm tra collection không rỗng. Với entity load từ DB, access `lines` có thể kích hoạt SELECT; đây là use case cần fetch plan hoặc một predicate COUNT/EXISTS nếu số Lines rất lớn.

### 25.4. Không gửi email khi transaction chưa commit

Nếu gọi hệ thống ngoài trước commit rồi DB rollback, bên ngoài có thể thấy order không tồn tại. Dùng outbox/event-after-commit/idempotent workflow theo architecture.

---

## 26. Tạo PaymentAttempt sau khi có Order

```java
@Transactional
public UUID startPaymentAttempt(
        String authorizedTenant,
        Long orderId,
        int attemptNo
) {
    PurchaseOrder order = em.createQuery(
        """
        select o
        from PurchaseOrder o
        where o.id = :id
          and o.tenantId = :tenant
        """,
        PurchaseOrder.class
    )
    .setParameter("id", orderId)
    .setParameter("tenant", authorizedTenant)
    .getResultStream()
    .findFirst()
    .orElseThrow(() ->
        new IllegalArgumentException(
            "Order unavailable"
        )
    );

    PaymentAttempt attempt = new PaymentAttempt(
        order, attemptNo, Instant.now()
    );

    em.persist(attempt);
    em.flush();
    return attempt.getId();
}
```

### 26.1. UUID assigned trước hay sau INSERT?

Phụ thuộc JPA provider/version/strategy. Bài test nên kiểm tra ID sau flush và dữ liệu committed sau transaction.

### 26.2. Attempt number phải được cấp an toàn

Trong service minh họa, caller cung cấp `attemptNo`. Production không nên tin raw client attemptNo hoặc dùng `MAX+1` vô lock; cần server-side allocator/idempotent attempt creation.

### 26.3. Không lặp payment gateway call

Tạo DB Attempt trước, commit, rồi dùng workflow đáng tin/queue để gọi gateway; cập nhật Attempt result bằng transaction khác. Bảo vệ khỏi duplicate callbacks và repeated messages.

---

# Phần VII — Đọc, truy vấn và fetch plan

## 27. Truy vấn list Order bằng DTO projection

UI danh sách chỉ cần Order ID, Customer name, status, total, createdAt. Không cần tải Lines/Products.

DTO:

```java
public record OrderListRow(
    Long orderId,
    String customerEmail,
    OrderStatus status,
    BigDecimal totalAmount,
    String currency,
    Instant createdAt
) {}
```

JPQL:

```java
List<OrderListRow> rows = em.createQuery(
    """
    select new com.example.shop.api.OrderListRow(
        o.id,
        c.email,
        o.status,
        o.total.amount,
        o.total.currency,
        o.createdAt
    )
    from PurchaseOrder o
    join o.customer c
    where o.tenantId = :tenant
    order by o.createdAt desc, o.id desc
    """,
    OrderListRow.class
)
.setParameter("tenant", authorizedTenant)
.setMaxResults(50)
.getResultList();
```

**Lưu ý về converter:** `c.email` có Java type `EmailAddress`, không phải `String`. Nếu DTO constructor nhận `String` như ví dụ trên, `c.email` có thể gây constructor type mismatch. Hai cách đúng hơn:

- Đổi `OrderListRow.customerEmail` thành `EmailAddress`, rồi map ra String theo policy ở API boundary.
- Hoặc dùng custom query/projection chọn representation được provider hỗ trợ và mapper chuyển sang String.

Ví dụ type-safe cho JPQL constructor:

```java
public record OrderListRow(
    Long orderId,
    EmailAddress customerEmail,
    OrderStatus status,
    BigDecimal totalAmount,
    String currency,
    Instant createdAt
) {}
```

Ở thực tế, email là PII: nếu màn hình không cần hiển thị email, hãy bỏ hẳn field này và chọn một display name được phép. **Projection và authorization là hai yêu cầu riêng**.

### 27.1. JPQL dùng property path của embeddable

`o.total.amount` và `o.total.currency` là paths theo Java embeddable, không dùng tên cột `total_amount` trong JPQL.

### 27.2. JOIN khác JOIN FETCH

`join o.customer c` cho projection scalar/DTO; không cần `join fetch` để xây DTO. `JOIN FETCH` dùng khi cần entity result cùng association initialized.

### 27.3. Sort ổn định

`order by o.createdAt desc, o.id desc` giúp các rows trùng timestamp có tie-breaker, cần thiết cho paging.

### 27.4. Có thể không nên trả email

API response phải có DTO allowlist theo quyền. Không serialize toàn Customer entity hoặc log EmailAddress values.

---

## 28. Đọc detail Order cùng Lines

Một query:

```jpql
select distinct o
from PurchaseOrder o
join fetch o.customer
left join fetch o.lines l
left join fetch l.product
where o.id = :orderId
  and o.tenantId = :tenant
```

### 28.1. Hợp lý với một Order có số Lines giới hạn

Đọc một Order detail kèm Line/Product có thể dùng fetch join. Tuy nhiên SQL rows lặp Order fields cho mỗi Line; với Orders rất lớn, nên query Lines phân trang riêng.

### 28.2. Không dùng collection fetch join với page root Orders tùy tiện

Nếu `setMaxResults(50)` đặt trên query fetch join Lines của nhiều Orders, LIMIT theo SQL rows có thể làm thiếu roots/children hoặc provider paginate in-memory.

### 28.3. Nhiều collection có thể nhân rows

Nếu Order đồng thời fetch Lines và PaymentAttempts, SQL có thể sinh gần `lineCount × attemptCount` rows per Order. Tách bounded queries thường tốt hơn giant join.

### 28.4. Test số SQL

Khi DTO mapper lặp Lines và truy cập Product.name, nếu Product chưa được fetch có thể tạo N+1. Đo toàn use case trên data có nhiều distinct Products.

---

## 29. Không để API trả nguyên JPA entity

Sai:

```java
@GetMapping("/orders/{id}")
public PurchaseOrder detail(...) {
    return repository.findById(id).orElseThrow();
}
```

Có thể gây:

- Lazy initialization exception ngoài transaction.
- N+1 qua JSON serialization.
- Circular relation nếu thêm inverse association.
- Lộ các fields nội bộ: tenant, version, external references, customer data.
- Payload vô tình thay đổi khi thêm field vào entity.

Tốt hơn: controller trả `OrderDetailResponse` được map từ query results đã xác thực tenant và chọn trường cần thiết.

### 29.1. toString/equals/hashCode của entity

Không dùng Lombok `@Data` máy móc cho entity có relationships; generated methods có thể duyệt lazy graphs hoặc dùng mutable/generated IDs sai cách. Domain entity equality cần thiết kế theo lifecycle.

### 29.2. @JsonIgnore không thay quyền

Jackson annotations chỉ kiểm soát một serialization path; repository queries vẫn phải áp tenant/owner authorization.

---

# Phần VIII — Kiểm thử tích hợp

## 30. Vì sao cần database thật tương đương production?

Những assertions quan trọng phụ thuộc database:

- PostgreSQL sequences/IDENTITY.
- UUID column mapping.
- Composite UNIQUE và FK.
- Numeric scale/precision.
- CHECK constraints.
- Transaction rollback và isolation.
- Hibernate-generated SQL và parameter binding.
- Lazy associations/orphan removal.
- Optimistic concurrency.

Một in-memory database như H2 rất tiện cho smoke tests nhưng không đủ chứng minh PostgreSQL collation, FK/locking/dialect và identity behavior.

## 31. PostgreSQL Testcontainers + Spring Data JPA

Ví dụ JUnit 5/Spring Boot:

```java
@DataJpaTest
@Testcontainers
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class OrderPersistenceTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void dbProps(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.datasource.url",
            postgres::getJdbcUrl
        );
        registry.add(
            "spring.datasource.username",
            postgres::getUsername
        );
        registry.add(
            "spring.datasource.password",
            postgres::getPassword
        );
    }

    @PersistenceContext
    EntityManager em;

    @Test
    void persistsOrderAndLines() {
        // Fixture setup + assertions.
    }
}
```

Required imports gồm JUnit Jupiter, Testcontainers JUnit/PostgreSQL, Spring Boot Test, Jakarta Persistence. Package của một số Spring Boot Test annotations có thể thay đổi giữa major versions; thích ứng theo version đang dùng.

### 31.1. Testcontainers chọn đúng major version DB đích

`postgres:16` chỉ là ví dụ. Dự án đang deploy PostgreSQL major version khác phải dùng image tương ứng khi test dialect-specific behavior.

### 31.2. Dùng migrations

Chạy Flyway/Liquibase scripts trong test datasource. Tránh `ddl-auto=create-drop` tạo schema khác production nếu đang chứng minh PK/FK/UNIQUE/CHECK correctness.

### 31.3. Test-managed transaction thường rollback

`@DataJpaTest` thường rollback test transaction cuối test; phù hợp isolated mapping tests, nhưng không chứng minh dữ liệu đã committed. Dùng separate transaction tests khi kiểm commit/concurrency.

### 31.4. Không hard-code production credentials

Testcontainer tạo credentials cho DB test. Không lưu URL/password production trong test configuration.

---

## 32. Fixture builder để test tạo Order

Pseudo helper:

```java
Customer customer = new Customer(
    "shop-a",
    new EmailAddress("alice@example.invalid"),
    new PostalAddress(
        "12 Main Road", "Da Nang", "550000"
    )
);

Product product = new Product(
    "shop-a",
    "BOOK-JPA",
    new Money(new BigDecimal("125.50"), "USD")
);

em.persist(customer);
em.persist(product);

PurchaseOrder order = new PurchaseOrder(
    "shop-a",
    customer,
    "WEB-ORDER-001",
    "USD",
    Instant.parse("2026-11-15T03:00:00Z")
);

order.addLine(product, 2);
em.persist(order);
em.flush();
```

Expected:

```text
Customer.id != null (sequence)
Product.id != null (sequence)
Order.id != null (sequence)
OrderLine.id != null (identity, after flush)
Order.total = 251.00 USD
Order.status = DRAFT
Line.quantity = 2
Line.unitPrice = 125.50 USD
```

### 32.1. Test phải tái lập

Dùng timestamps cố định/Clock, generated synthetic emails, unique external codes. Không dùng dữ liệu khách hàng thật.

### 32.2. Test scope

Nếu test nhiều cases trong cùng DB mà không rollback/cleanup đúng, composite unique constraints có thể làm fail theo thứ tự. Dùng independent transactions/fixtures.

---

## 33. Test flush → clear → reload

```java
@Test
void orderAndLineRoundTrip() {
    Customer c = fixtureCustomer();
    Product p = fixtureProduct("USD", "125.50");
    em.persist(c);
    em.persist(p);

    PurchaseOrder order = new PurchaseOrder(
        "shop-a", c, "ORDER-ROUNDTRIP-1", "USD",
        Instant.parse("2026-11-15T03:00:00Z")
    );
    order.addLine(p, 2);

    em.persist(order);
    em.flush();

    Long orderId = order.getId();
    Long lineId = order.getLines().get(0).getId();

    assertNotNull(orderId);
    assertNotNull(lineId);

    em.clear();

    PurchaseOrder loaded =
        em.find(PurchaseOrder.class, orderId);

    assertNotNull(loaded);
    assertEquals(OrderStatus.DRAFT, loaded.getStatus());
    assertEquals(
        new Money(new BigDecimal("251.00"), "USD"),
        loaded.getTotal()
    );
    assertEquals(1, loaded.getLines().size());
    assertEquals(
        p.getId(),
        loaded.getLines().get(0).getProduct().getId()
    );
}
```

`fixtureCustomer` và `fixtureProduct` là test helpers minh họa. `getLines()` trả unmodifiable view; truy cập trong transaction đang mở để provider có thể load LAZY collection.

### 33.1. Không chỉ assert ngay sau persist

Nếu không `clear`, JPA có thể trả lại managed object đang nằm trong L1 mà chưa chứng minh query hydration đúng.

### 33.2. Flush không phải commit

`em.flush()` đồng bộ SQL nhưng transaction vẫn có thể rollback. Test round-trip cùng transaction kiểm mapping, không kiểm durability.

### 33.3. Kiểm tra Line owning side

Nếu helper addLine không gán `line.order`, INSERT có thể vi phạm NOT NULL FK; đó là lỗi mapping mà test này phải phát hiện.

---

## 34. Test EmailAddress converter đọc qua cột thật

```java
@Test
void normalizesEmailToDatabaseColumn() {
    Customer c = new Customer(
        "shop-a",
        new EmailAddress("  ALICE@EXAMPLE.INVALID "),
        null
    );

    em.persist(c);
    em.flush();
    Long id = c.getId();
    em.clear();

    String stored = (String) em.createNativeQuery(
        "select email from customer where customer_id = ?1"
    )
    .setParameter(1, id)
    .getSingleResult();

    assertEquals("alice@example.invalid", stored);

    Customer reloaded = em.find(Customer.class, id);
    assertEquals(
        new EmailAddress("alice@example.invalid"),
        reloaded.getEmail()
    );
}
```

### 34.1. Hai hướng

Native SQL đọc database representation; JPA `find` kiểm conversion về value object.

### 34.2. Test duplicates sau normalization

`Alice@Example.Invalid` và `alice@example.invalid` trong cùng tenant phải conflict theo business rule. Nếu converter normalize, DB unique constraint trên normalized value có thể bảo vệ ứng dụng này; external writers vẫn cần conventions/DB-level normalization phù hợp.

### 34.3. Không log email canary

Test dùng `example.invalid`, nhưng production logging không nên dump raw email/bind values.

---

## 35. Test CHECK quantity và giá không âm

Domain method:

```java
assertThrows(
    IllegalArgumentException.class,
    () -> order.addLine(product, 0)
);
```

DB-level test phải dùng SQL/fixture bypass domain validation có kiểm soát:

```sql
-- Chạy trong transaction test rồi rollback.
INSERT INTO order_line (
    order_id, product_id, line_no,
    quantity, unit_price_amount, unit_price_currency
)
VALUES (
    :existing_order, :existing_product, 100,
    0, 10.00, 'USD'
);
```

Expected: DB từ chối vì `ck_line_quantity_positive`. Tên bind syntax `:existing_order` chỉ mang tính minh họa; khi chạy bằng JDBC/JPA native, bind theo API/driver thích hợp.

### 35.1. Domain validation + DB CHECK có mục đích khác

Domain báo lỗi sớm, dễ giải thích. DB CHECK đảm bảo không ghi state invalid kể cả qua import/native SQL.

### 35.2. Constraint exception timing

Có thể xảy ra khi statement chạy/flush/commit tùy DB/constraint deferral/provider. Test transaction boundary đủ, không hard-code mọi provider ném cùng exception class.

### 35.3. Sau lỗi SQL

Rollback transaction test; không tiếp tục dùng cùng EntityManager nếu transaction đã aborted/rollback-only.

### 35.4. CHECK không bảo vệ mọi domain invariant

Tổng tiền order bằng SUM Lines, Product cùng tenant, mã externalCode idempotency, payment gateway state đều cần cơ chế khác ngoài CHECK đơn giản.

---

## 36. Test UNIQUE customer email và Product SKU

Kịch bản:

```text
Customer("shop-a", "alice@example.invalid") -> success
Customer("shop-a", "ALICE@example.invalid") -> conflict
Customer("shop-b", "alice@example.invalid") -> allowed

Product("shop-a", "SKU-7") -> success
Product("shop-a", "SKU-7") -> conflict
Product("shop-b", "SKU-7") -> allowed
```

### 36.1. Test trong transaction khác khi cần DB unique

Nếu hai entities có generated IDs khác nhau, `persist` trong một context rồi `flush` có thể kiểm được UNIQUE constraint. Với concurrency/commit durability, tạo hai transactions độc lập.

### 36.2. Đừng chỉ kiểm tra `repository.existsBy...`

Hai requests có thể cùng quan sát absent trước khi INSERT. Database UNIQUE là bảo vệ cuối cùng.

### 36.3. Exception thuộc nhiều tầng

JDBC `SQLException` có thể được wrap bởi Hibernate PersistenceException, hoặc Spring `DataIntegrityViolationException`. Test theo behavior/stack thực tế và xác nhận DB state, tránh assert một exception class cho mọi provider.

---

## 37. Test FK và cascade đúng vòng đời

Tạo Order với Customer/Product đã tồn tại, rồi xóa Order:

- Lines thuộc Order có thể bị xóa theo cascade/remove.
- Customer và Product **phải còn**.
- PaymentAttempts đang tham chiếu Order có thể chặn hard delete vì FK, trừ khi có deletion policy riêng.

### 37.1. Delete khi chưa có PaymentAttempt

```java
PurchaseOrder order =
    em.find(PurchaseOrder.class, orderId);

em.remove(order);
em.flush();
em.clear();

assertNull(em.find(PurchaseOrder.class, orderId));
assertNotNull(em.find(Customer.class, customerId));
assertNotNull(em.find(Product.class, productId));
```

Nếu cần xác minh Lines đã xóa, query `count(l) where l.order.id=:id` hoặc raw DB row count.

### 37.2. Đừng xóa Product khi vẫn được tham chiếu

FK `order_line.product_id → product.product_id` có thể từ chối Product hard delete, và thường nên giữ Product historical reference. Deactivate Product thay vì xóa theo business policy.

### 37.3. Test orphanRemoval riêng

Thêm hai Lines, flush, remove một Line bằng domain method, flush/clear/reload. Expected còn một Line và total cập nhật đúng. Đừng gọi `em.remove(line)` và kết luận orphanRemoval hoạt động; cần loại khỏi collection để test semantics của nó.

---

## 38. Test CustomerProfile shared PK

```java
@Test
void profileSharesCustomerPrimaryKey() {
    Customer customer = fixtureCustomer();
    em.persist(customer);

    CustomerProfile profile = new CustomerProfile(
        customer,
        new PostalAddress(
            "77 New Road", "Hue", "530000"
        )
    );
    em.persist(profile);
    em.flush();

    Long customerId = customer.getId();
    assertEquals(customerId, profile.getId());

    em.clear();

    CustomerProfile loaded = em.find(
        CustomerProfile.class,
        customerId
    );

    assertNotNull(loaded);
    assertEquals(
        customerId,
        loaded.getCustomer().getId()
    );
}
```

### 38.1. Đọc bằng Customer ID

Không có generated Profile ID riêng. `CustomerProfile.id` và FK `customer_id` trùng nhau.

### 38.2. Tạo profile thứ hai phải conflict

DB PK `customer_profile.customer_id` ngăn duplicate; xác minh ở transaction mới nếu muốn kiểm đúng physical constraint.

### 38.3. Test khi Customer bị xóa

FK profile → customer có thể chặn xóa Customer nếu Profile còn tồn tại. Nếu business cần cascade delete, thiết kế lifecycle rõ; không tự thêm CASCADE REMOVE từ Profile sang Customer.

---

## 39. Test PaymentAttempt UUID và unique attempt number

```java
@Test
void uuidAttemptRoundTrips() {
    PurchaseOrder order = persistedOrderFixture();

    PaymentAttempt attempt = new PaymentAttempt(
        order, 1,
        Instant.parse("2026-11-15T04:00:00Z")
    );

    em.persist(attempt);
    em.flush();
    UUID id = attempt.getId();

    assertNotNull(id);
    em.clear();

    PaymentAttempt loaded =
        em.find(PaymentAttempt.class, id);

    assertNotNull(loaded);
    assertEquals(1, loaded.getAttemptNo());
    assertEquals(
        PaymentAttemptStatus.CREATED,
        loaded.getStatus()
    );
}
```

### 39.1. ID UUID không là thứ tự thanh toán

`attemptNo` biểu diễn lần thử theo business, còn UUID là persistent identity.

### 39.2. Test duplicate attemptNo

Hai Attempts của cùng Order với cùng attemptNo phải vi phạm UNIQUE. Hai Orders khác nhau đều có attempt #1 là hợp lệ.

### 39.3. Không in payment provider reference ra debug logs

Reference có thể là dữ liệu nhạy cảm tùy provider/use case. Dùng event code và request ID.

---

## 40. Test transaction rollback: không có Order nửa chừng

Scenario:

1. Tạo Customer/Product hợp lệ, commit.
2. Transaction mới: persist Order + Lines.
3. Cố gây một FK/CHECK/UNIQUE violation trong cùng transaction.
4. Flush/commit fail và rollback.
5. EntityManager mới kiểm tra không có Order/Lines được committed.

### 40.1. Không chỉ kiểm tra exception

Một test có thể thấy exception nhưng không biết các INSERT trước đó đã committed chưa nếu transaction boundary sai. Dùng transaction mới để kiểm rollback state.

### 40.2. Thận trọng với generated IDs

Sequences/identity có thể đã tiêu thụ ID dù transaction rollback. Gap trong ID không chứng minh rollback thất bại.

### 40.3. External side effects không rollback tự động

Nếu test transaction đã gửi email/thanh toán qua remote API, rollback database không hoàn tác bên ngoài. Điều này nhấn mạnh outbox/idempotency patterns.

---

## 41. Test optimistic locking cho Order

Timeline:

```text
Tx A: SELECT Order#42, version=3, status=DRAFT
Tx B: SELECT Order#42, version=3, status=DRAFT

Tx A: submit -> UPDATE ... WHERE id=42 AND version=3
Tx A: COMMIT -> version=4

Tx B: submit -> tries update with expected version=3
Tx B: flush/commit -> OptimisticLockException
```

JUnit-style resource-local pseudocode:

```java
EntityManager a = emf.createEntityManager();
EntityManager b = emf.createEntityManager();

try {
    a.getTransaction().begin();
    b.getTransaction().begin();

    PurchaseOrder oa = a.find(
        PurchaseOrder.class, orderId
    );
    PurchaseOrder ob = b.find(
        PurchaseOrder.class, orderId
    );

    oa.submit();
    a.getTransaction().commit();

    ob.submit();

    assertThrows(
        RuntimeException.class,
        () -> {
            b.flush();  // Conflict may surface here,
            b.getTransaction().commit(); // or at commit.
        }
    );
} finally {
    if (a.getTransaction().isActive()) {
        a.getTransaction().rollback();
    }
    if (b.getTransaction().isActive()) {
        b.getTransaction().rollback();
    }
    a.close();
    b.close();
}
```

Đây là **pseudocode test strategy**, không phải assertion hoàn chỉnh để dùng nguyên văn: `assertThrows(RuntimeException.class)` quá rộng cho test thực; cần bắt đúng `OptimisticLockException` hoặc wrapper được stack mục tiêu sử dụng, và đảm bảo transaction setup/flush/order row/line fixture hợp lệ. Với JTA-managed EntityManager phải dùng transaction manager thay vì resource-local `getTransaction()`. Ngoài ra nếu test có ambient Spring `@Transactional`, phải tách transactions thật.

### 41.1. Hai EntityManagers độc lập

Nếu dùng cùng EM, cả hai “transactions” không có independent snapshots như yêu cầu và test không chứng minh concurrency.

### 41.2. Bản ghi có Lines trước khi submit

`submit()` từ DRAFT yêu cầu không rỗng. Fixture phải persist Order với ít nhất một Line.

### 41.3. Rollback sau conflict

Không tái sử dụng stale Order trong failed persistence context; mở transaction/context mới và đọc lại committed state.

### 41.4. @Version không bảo vệ cross-row invariant tự động

Nếu một writer update OrderLine bằng bulk SQL hoặc chỉ thay child row mà không chạm Order, parent version có thể không đổi. Thiết kế aggregate-wide conflict detection nếu cần.

---

# Phần IX — Những lựa chọn thiết kế phải biết cân nhắc

## 42. SEQUENCE, IDENTITY hay UUID cho từng entity?

| Entity | Chọn trong bài | Lý do | Khi cần xem xét lại |
|---|---|---|---|
| Customer | SEQUENCE/BIGINT | Khóa nhỏ, hiệu quả khi relational joins | Distributed ID policy |
| Product | SEQUENCE/BIGINT | Catalog nhiều quan hệ, joins thường xuyên | Cross-region data merge |
| PurchaseOrder | SEQUENCE/BIGINT | Aggregate root, dễ index/FK | Global immutable public IDs |
| OrderLine | IDENTITY/BIGINT | Minh họa DB-generated row ID | Bulk insert throughput lớn |
| CustomerProfile | @MapsId/Long | Cùng lifecycle identity với Customer | Profile có identity riêng |
| PaymentAttempt | UUID | Reference phân tán, không theo thứ tự | Index locality/DB compatibility |

Không có nghĩa mỗi entity nhất định phải sử dụng đúng chiến lược trong bảng. Với write-heavy workload, có thể chuyển OrderLine sang sequence để hỗ trợ batching sau khi đo.

## 43. Generated ID và business number là hai thứ khác

Order có `order_id` là PK do sequence sinh, còn `external_code` duy nhất theo tenant.

### 43.1. Không lấy order_id thay hóa đơn pháp lý

Một số nghiệp vụ yêu cầu số chứng từ có quy tắc thời gian/chuỗi riêng; database sequence PK không mặc định đáp ứng.

### 43.2. ExternalCode cần canonicalization

Nếu `abc-01` và `ABC-01` được coi trùng, phải normalize và enforce ở DB tương ứng. `UNIQUE` theo collation có thể khác.

### 43.3. Idempotency không chỉ là UNIQUE

Client retry cùng externalCode nhưng payload khác là conflict, không phải “trả kết quả cũ” không kiểm chứng. Cần lưu fingerprint/business operation policy phù hợp.

## 44. Composite unique và generated PK tồn tại song song

Đừng ngộ nhận:

```text
PRIMARY KEY (customer_id)
```

thay thế được:

```text
UNIQUE (tenant_id, email)
```

Một Customer có ID mới vẫn có thể vi phạm email uniqueness. Ngược lại, đổi email không đổi Customer persistent identity.

## 45. Null trong UNIQUE và constraint behavior

Một số DB cho phép nhiều NULL trong UNIQUE columns; PostgreSQL mặc định coi NULL khác nhau trong UNIQUE theo nhiều version/setting, có tùy chọn `NULLS NOT DISTINCT` ở PostgreSQL mới. Nếu business muốn duy nhất trên field optional, cần chọn migration constraint phù hợp, không giả định `@UniqueConstraint` tự giải quyết semantics NULL.

Trong bài, `Customer.email` và `Order.externalCode` khai NOT NULL, tránh ambiguity cho hai business keys đó.

## 46. FK bảo vệ sự tồn tại, không bảo vệ toàn bộ nghiệp vụ

Một OrderLine có FK tới Product. Nếu Product inactive hoặc thuộc tenant khác, FK vẫn có thể hợp lệ. Domain/service phải kiểm tra `product.active` và tenant, hoặc nâng cấp DB constraints/tenant keys để bảo vệ theo thiết kế đa writer.

## 47. Không dùng cascade để chữa lỗi FK

Nếu `order_line.product_id` bị lỗi vì Product chưa persist, cách khắc phục đúng thường là persist Product trong catalog transaction trước hoặc tham chiếu Product đã tồn tại, **không phải** thêm `cascade=PERSIST` bừa vào `@ManyToOne Product`.

## 48. Bulk DML và persistence context stale

JPQL bulk update:

```java
int changed = em.createQuery(
    """
    update Product p
    set p.active = false
    where p.tenantId = :tenant
    """
)
.setParameter("tenant", authorizedTenant)
.executeUpdate();
```

Có thể cập nhật nhiều rows nhanh, nhưng:

- Không chạy từng entity domain method.
- Bypass dirty checking/normal lifecycle callbacks.
- Không tự xử lý `@Version` theo semantics managed update.
- Các Product đã managed trong EM có thể giữ `active=true` tới khi refresh/clear.
- DB CHECK/FK vẫn áp dụng.

Không gọi bulk DML nếu nghiệp vụ đòi callbacks/version per entity mà chưa thiết kế bổ sung.

## 49. Tránh fetch graph không có giới hạn

Một `PurchaseOrder` có 30 Lines và 5 PaymentAttempts; fetch join cả hai collections có thể tạo gần 150 joined rows trước khi deduplicate. Không dùng `EAGER` cho mọi quan hệ để “đơn giản hóa” JSON mapping.

Với list endpoint, DTO projection và paging. Với detail, một hoặc vài bounded queries. Với export, chunked read model.

## 50. Precision/rounding là business constraint

Trong bài, Money dùng scale 2 và `RoundingMode.UNNECESSARY`. Vì vậy:

```java
new Money(new BigDecimal("10.125"), "USD");
```

sẽ ném `ArithmeticException` thay vì âm thầm làm tròn. Production có thể chọn rounding mode khác cho tax/discount/FX, nhưng phải quy định ở domain và test trên DB decimal precision, không chuyển đại sang `double`.

## 51. Các quan hệ một-một không phải luôn LAZY thực sự

Với shared-PK `CustomerProfile.customer` owning side, LAZY to-one thường có thể dùng proxy theo provider. Nhưng nếu thêm inverse `Customer.profile` optional, provider có thể cần kiểm tra xem row profile có tồn tại, dẫn tới secondary SQL nếu không có enhancement/metadata phù hợp. Test SQL count trên provider thực.

## 52. Migrations và schema drift

Nếu developer đổi entity `priceAmount` sang `NUMERIC(20,4)` nhưng migration không đổi, các tests dùng Hibernate create-drop có thể pass trong khi production fail. Cần migration version, schema validation, native CHECK/FK tests và DB catalog inspection theo use case.

## 53. Data privacy khi debug JPA

Không log `Customer.email`, payment provider reference, SQL bind values hay entity graph trong error logs. Nếu vi phạm UNIQUE email, database exception message có thể chứa rejected value. API trả safe error code như `CUSTOMER_CONFLICT`, không trả `ex.getMessage()` hoặc raw stack trace.

## 54. Đo hiệu năng trên dữ liệu đại diện

Một Order có 1 Line không cho thấy behavior khi 1.000 Lines. Test:

- 1, 10, 100 và các tail sizes của Lines/Order.
- N Orders với distinct Customers/Products để lộ N+1.
- IDENTITY vs SEQUENCE insertion throughput.
- @Version conflicts dưới concurrency.
- List Page p50/p95/p99, count query, connection wait.
- DB planner/explain với indexes và tenant skew.

Không khẳng định tối ưu sau một benchmark H2 có 10 rows.

---

# Phần X — Bài tập thực hành

## 55. Bài tập cấp độ cơ bản

### Bài 1 — Nhận diện khóa

Chỉ ra PK của Customer, Product, PurchaseOrder, OrderLine, CustomerProfile và PaymentAttempt.

**Gợi ý:** Customer/Product/Order có Long sequence; Line IDENTITY; Profile dùng Customer ID; Attempt UUID.

### Bài 2 — Phân biệt business key

Vì sao `externalCode` không nên tự động được chọn làm `@Id` cho Order?

**Gợi ý:** Business key có scope/format/lifecycle khác persistent ID, có thể thay theo nghiệp vụ.

### Bài 3 — Sequence name

`@SequenceGenerator(name="x",sequenceName="order_id_seq")`: cái nào là physical database object?

**Đáp án:** `order_id_seq`.

### Bài 4 — ID gap

Tại sao Order IDs có thể không liên tục sau rollback?

**Gợi ý:** Sequence/identity allocation không rollback giống row INSERT.

### Bài 5 — IDENTITY

Vì sao Identity có thể hạn chế JDBC batching?

**Gợi ý:** Provider cần nhận generated key từ INSERT.

### Bài 6 — UUID

UUID có thay authentication/authorization không?

**Đáp án:** Không.

### Bài 7 — Money

`new Money(10.50,"usd")` có value representation nào sau normalization?

**Gợi ý:** 10.50, "USD"; truyền BigDecimal thay double.

### Bài 8 — BigDecimal

`BigDecimal("10.0").equals(BigDecimal("10.00"))` trả gì?

**Đáp án:** false; scale khác, constructor Money chuẩn hóa.

### Bài 9 — Currency mismatch

Cộng 100 USD và 100 VND có hợp lệ theo `Money.add` không?

**Đáp án:** Không; phải có FX business rule.

### Bài 10 — @Embedded

`Money` có cần `@Id` không?

**Đáp án:** Không, là value object trong entity owner.

### Bài 11 — AttributeOverride

Trong Product, `Money.amount` được lưu cột nào?

**Đáp án:** `price_amount`.

### Bài 12 — Converter

`EmailAddressConverter` xử lý hai hướng nào?

**Gợi ý:** EmailAddress → String column; String column → EmailAddress.

### Bài 13 — Unique email

Hai tenants có thể dùng cùng email không?

**Đáp án:** Có theo constraint `UNIQUE(tenant_id,email)`.

### Bài 14 — @Enumerated

Vì sao `EnumType.STRING` an toàn hơn ORDINAL khi chèn enum values?

**Gợi ý:** Không phụ thuộc thứ tự khai báo enum.

### Bài 15 — @Version

Ai nên cập nhật `row_version`?

**Đáp án:** JPA provider trong managed updates; application không tự tăng.

## 56. Bài tập cấp độ quan hệ và constraint

### Bài 16 — Owning side

Quan hệ PurchaseOrder–OrderLine: field nào giữ FK?

**Đáp án:** `OrderLine.order` giữ `order_id`.

### Bài 17 — mappedBy

`@OneToMany(mappedBy="order")` cần property nào ở Line?

**Đáp án:** `order`.

### Bài 18 — Cascade

Có nên cascade REMOVE từ OrderLine tới Product?

**Đáp án:** Không; Product shared entity.

### Bài 19 — Orphan removal

Làm sao test `orphanRemoval` thật sự xóa dòng?

**Gợi ý:** Remove child qua aggregate helper, flush/clear, truy vấn DB rows.

### Bài 20 — Snapshot price

Giá Product tăng sau khi Order đã tạo. Có nên thay UnitPrice cũ trong OrderLine không?

**Gợi ý:** Không; đó là lịch sử giao dịch.

### Bài 21 — CHECK

DB constraint nào chặn `quantity = 0`?

**Đáp án:** `ck_line_quantity_positive`.

### Bài 22 — UNIQUE Line number

Hai Lines cùng order và line_no có hợp lệ không?

**Đáp án:** Không; `UNIQUE(order_id,line_no)`.

### Bài 23 — FK

Nếu Product không tồn tại, việc INSERT Line product_id trỏ tới đó phải thế nào?

**Gợi ý:** Database từ chối bằng FK.

### Bài 24 — Cross-tenant FK

FK theo customer_id đơn lẻ có ngăn Order tenant A trỏ Customer tenant B không?

**Đáp án:** Không; cần scope validation/composite FK.

### Bài 25 — Composite FK

Muốn database enforce cùng tenant cho Order→Customer, cần những cột nào?

**Gợi ý:** `(tenant_id,customer_id)` ở cả referencing/referenced keys; UNIQUE tương ứng bên Customer.

### Bài 26 — Shared PK

Vì sao `CustomerProfile.id` không có `@GeneratedValue`?

**Đáp án:** Dùng `@MapsId` lấy ID từ Customer.

### Bài 27 — Duplicate Profile

Có thể tạo hai Profiles cùng customer_id không?

**Đáp án:** Không; PK trên customer_profile.customer_id.

### Bài 28 — Attempt

Hai PaymentAttempts khác UUID nhưng cùng order_id + attempt_no có hợp lệ không?

**Đáp án:** Không; unique business key.

### Bài 29 — Hard delete

Xóa Order khi còn PaymentAttempts liên kết có thể gặp gì?

**Gợi ý:** FK chặn nếu không có cascade/deletion policy.

### Bài 30 — Total integrity

CHECK `total_amount >= 0` có chứng minh total bằng SUM các Lines không?

**Đáp án:** Không; cần domain/transaction/DB aggregate invariant riêng.

## 57. Bài tập transaction và test

### Bài 31 — L1 cache

`em.find` trả lại Order vừa persist trong cùng EM. Đã chứng minh round-trip chưa?

**Đáp án:** Chưa; flush/clear/find lại.

### Bài 32 — Flush

`em.flush` không lỗi có nghĩa Order đã committed chưa?

**Đáp án:** Chưa.

### Bài 33 — Rollback

Lỗi CHECK ở dòng thứ ba nên để lại bao nhiêu committed Lines từ transaction tạo Order đó?

**Đáp án:** Không; transaction rollback tất cả nếu đúng boundary.

### Bài 34 — UNIQUE race

Hai requests cùng kiểm tra externalCode chưa tồn tại. Điều gì ngăn cả hai committed?

**Gợi ý:** DB UNIQUE, cộng idempotency/conflict policy.

### Bài 35 — ID after flush

Line dùng IDENTITY: thời điểm nào test nên assert id khác null?

**Gợi ý:** Sau flush là mốc kiểm thử an toàn.

### Bài 36 — Converter DB test

Làm sao biết email được lưu normalized chứ không chỉ là Java object cached?

**Gợi ý:** Native SQL đọc raw column sau flush/clear.

### Bài 37 — Tenant test

Fixture chỉ có một tenant. Query thiếu tenant filter có bị phát hiện không?

**Đáp án:** Không chắc; thêm tenant B với records tương tự.

### Bài 38 — Concurrency

Vì sao test hai concurrent updates cần hai EntityManagers?

**Gợi ý:** EM không thread-safe, cần independent persistence contexts.

### Bài 39 — Optimistic lock

Hai transactions cùng đọc Order version=3 rồi cùng submit, expected outcome?

**Gợi ý:** Một commit thành công, stale update gặp conflict/rollback theo concurrency semantics.

### Bài 40 — Bulk DML

JPQL bulk UPDATE Product có tự gọi method deactivate() cho từng entity không?

**Đáp án:** Không.

### Bài 41 — JDBC batching

Nếu có 10.000 OrderLines, nên benchmark điều gì khi dùng IDENTITY vs SEQUENCE?

**Gợi ý:** INSERT count/batches, DB round-trips, commit latency, memory.

### Bài 42 — DTO

List endpoint chỉ cần Order ID và total; có nên fetch tất cả Lines không?

**Đáp án:** Không, dùng DTO projection.

### Bài 43 — Pagination

Vì sao fetch join collection cùng LIMIT page root có rủi ro?

**Gợi ý:** Một Order nhân thành nhiều SQL rows.

### Bài 44 — Currency column

Nếu Order total là USD nhưng UnitPrice Line là VND, ràng buộc nào trong demo chặn?

**Gợi ý:** `Money.add` trong aggregate, không phải FK.

### Bài 45 — Remote payment

Có nên gọi gateway và giữ transaction/row lock tới khi gateway trả lời?

**Gợi ý:** Tránh giữ DB transaction qua external latency; dùng outbox/idempotency.

### Bài 46 — UUID exposure

Public URL chứa PaymentAttempt UUID có tự trở thành truy cập được phép không?

**Đáp án:** Không.

### Bài 47 — Schema drift

Hibernate annotation có CHECK logic ở Java nhưng migration thiếu CHECK: test nào phát hiện?

**Gợi ý:** Native SQL violation test trên DB từ migrations thật.

### Bài 48 — Provider portability

Code `GenerationType.UUID` có chạy với javax.persistence cũ không?

**Đáp án:** Không như Jakarta Persistence 3.1; cần API/provider/version phù hợp.

### Bài 49 — Email normalization

Tại sao SQL writer bypass converter có thể làm vi phạm uniqueness semantics?

**Gợi ý:** DB collation/normalization và converter không tự áp cho raw SQL.

### Bài 50 — Thử thách tổng hợp

Xây test scenario:

1. Persist Customer/Product thuộc tenant A.
2. Tạo Order 2 Lines.
3. Persist CustomerProfile.
4. Submit Order và thêm PaymentAttempt.
5. Commit.
6. Đọc lại bằng EntityManager mới.
7. Assert generated IDs, FK, total, status, profile shared ID và Attempt UUID.
8. Cố tạo duplicate externalCode; assert rollback.
9. Cố tạo Line quantity=0 qua SQL; assert CHECK failure.
10. Tạo concurrent updates; assert optimistic conflict.

**Tiêu chí:** Chỉ dùng dữ liệu synthetic, giữ transaction boundaries rõ, không dựa vào L1 cache để chứng minh persistence.

---

# Phần XI — Checklist hoàn thành

## 58. Checklist về khóa

- [ ] Customer, Product, Order dùng sequence generators khớp migrations.
- [ ] OrderLine IDENTITY column thực sự tồn tại đúng ở DB.
- [ ] PaymentAttempt UUID generator được hỗ trợ bởi JPA/provider version.
- [ ] CustomerProfile dùng `@MapsId`, không tự sinh ID.
- [ ] Không dùng generated PK như number sequence nghiệp vụ không được phép có gaps.
- [ ] Không đổi ID của managed entity.
- [ ] Có test ID assigned/round-trip sau flush và commit.
- [ ] Có xem xét batching/index cost của ID strategy.

## 59. Checklist về value objects

- [ ] Money dùng BigDecimal và currency, có policy scale/rounding.
- [ ] Money equality/hashCode ổn định sau normalization.
- [ ] Product.price, Order.total, Line.unitPrice có AttributeOverrides đúng.
- [ ] PostalAddress là embeddable không có independent ID.
- [ ] EmailAddressConverter kiểm tra hai hướng.
- [ ] UNIQUE email tính đến normalization/tenant scope.
- [ ] Enum dùng STRING và có migration khi đổi values.
- [ ] Có tests về null/precision/currency mismatch.
- [ ] Không log PII, tiền/token/provider ref ngoài policy.

## 60. Checklist về quan hệ và ràng buộc

- [ ] `OrderLine.order` là owning FK side; `mappedBy` đúng.
- [ ] Order.addLine đồng bộ hai phía.
- [ ] Cascade ALL chỉ trong aggregate Lines; không cascade REMOVE Customer/Product.
- [ ] OrphanRemoval được kiểm thử bằng xóa khỏi collection.
- [ ] OrderLine có FK Order/Product.
- [ ] CustomerProfile shared PK/FK đúng.
- [ ] PaymentAttempt có FK và UNIQUE(order_id,attempt_no).
- [ ] Customer/Product/Order có composite business UNIQUE theo tenant.
- [ ] DB CHECK bảo vệ quantity, amount, attemptNo và nextLineNumber.
- [ ] Domain vẫn kiểm tenant/currency/active Product.
- [ ] Nếu cần DB enforce tenant FK, dùng composite keys/join mapping nhất quán.
- [ ] Migrations là ground truth; annotation chỉ mô tả intent mapping.

## 61. Checklist về giao dịch và kiểm thử

- [ ] Persist Order+Lines diễn ra trong cùng transaction.
- [ ] Lỗi flush/commit rollback toàn aggregate.
- [ ] Readback test dùng flush/clear/find hoặc transaction mới.
- [ ] Optimistic concurrency test dùng EM/tx độc lập.
- [ ] Không tiếp tục dùng context bị rollback-only sau failure.
- [ ] Không coi generated ID có giá trị là bằng chứng commit.
- [ ] Query API có tenant scope và DTO allowlist.
- [ ] Không dùng collection fetch join cho paged root query vô điều kiện.
- [ ] Có tests DB PK/FK/UNIQUE/CHECK trên engine mục tiêu.
- [ ] Không để Hibernate auto-DDL che schema drift.
- [ ] Có test N+1/SQL count khi read graph.
- [ ] Có giới hạn Lines/Order, batch size và query size.
- [ ] External payment calls dùng workflow idempotent/outbox khi cần.
- [ ] Logs/traces không lộ email, SQL bind values hoặc payment references.
- [ ] Tests dùng synthetic data và isolation đúng.
- [ ] Có kết luận trade-off IDENTITY vs SEQUENCE/UUID dựa trên workload.

---

## 62. Bảng tra cứu nhanh

| Bài toán | Giải pháp trong bài |
|---|---|
| PK Customer | `@Id + @GeneratedValue(SEQUENCE)` |
| PK Product | Sequence riêng |
| PK Order | Sequence riêng |
| PK OrderLine | `GenerationType.IDENTITY` |
| PK PaymentAttempt | `GenerationType.UUID` (Jakarta Persistence 3.1+) |
| PK CustomerProfile | `@MapsId` dùng Customer ID |
| Value object Money | `@Embeddable` + BigDecimal + currency |
| Value object Address | `@Embeddable` |
| Email lưu một cột | `AttributeConverter<EmailAddress,String>` |
| Enum trạng thái | `EnumType.STRING` |
| Customer.email unique theo tenant | `UNIQUE(tenant_id,email)` |
| Product.SKU unique theo tenant | `UNIQUE(tenant_id,sku)` |
| Order.externalCode unique | `UNIQUE(tenant_id,external_code)` |
| Line number unique | `UNIQUE(order_id,line_no)` |
| Line positive quantity | `CHECK(quantity > 0)` |
| Line thuộc Order | `@ManyToOne` owning FK |
| Order có Lines | `@OneToMany(mappedBy="order", cascade=ALL, orphanRemoval=true)` |
| Line tham chiếu Product | `@ManyToOne` không cascade |
| Profile một-một | Shared PK + `@MapsId` |
| Attempt nhiều lần/Order | `@ManyToOne` + unique attemptNo per Order |
| Total bằng Lines | Domain invariant + transaction/tests |
| Cross-tenant FK | Authorized queries + optional composite FK |
| Readback đúng DB | `flush → clear → find` |
| Durability | Commit + new EntityManager read |
| Rollback nguyên tử | Một transaction cho Order+Lines |
| Concurrent stale update | `@Version` + two-EM test |
| Danh sách nhanh | DTO projection + bounded query |
| N+1 | Fetch plan/projection + SQL count metrics |
| Test gần production | Testcontainers + migrations target DB |

## 63. Tổng kết

Từ bài thực hành này, cần ghi nhớ:

1. **Khóa sinh là quyết định về storage và transaction**, không chỉ annotation: sequence, identity và UUID có timing, hiệu năng và portability khác nhau.
2. **Khóa chính và business uniqueness không thay thế nhau**. Customer ID là PK; email trong tenant là UNIQUE; Product ID là PK; SKU trong tenant là UNIQUE.
3. **Value objects giúp giữ semantics trong Java**: Money có amount/currency và phép toán đúng đơn vị; PostalAddress có các field gắn kết; EmailAddress có normalization.
4. **`@Embeddable` và `AttributeConverter` giải quyết hai kiểu mapping khác nhau**: nhiều columns trong owner so với chuyển thành một basic column.
5. **Quan hệ hai chiều có owning side**. OrderLine giữ FK và helper addLine phải gán cả OrderLine.order lẫn Order.lines.
6. **Cascade chỉ theo quyền sở hữu vòng đời**: Lines thuộc Order; Customer/Product/PaymentAttempt không nên bị xóa do cascade tùy tiện.
7. **`@MapsId` giúp mô hình shared primary key one-to-one**, tránh generated ID trùng lặp không cần thiết cho CustomerProfile.
8. **PK/FK/UNIQUE/CHECK được thực thi ở database**, bảo vệ cả đường ghi không đi qua JPA. Domain validation vẫn cần để đảm bảo thông điệp lỗi và invariants giàu ngữ nghĩa.
9. **FK đơn lẻ không tự enforce tenant consistency**. Phải kiểm tra authorized scope và thêm composite FK/RLS/DB strategy khi threat model yêu cầu.
10. **Snapshot giá trong OrderLine** bảo vệ dữ liệu giao dịch lịch sử trước thay đổi giá Product.
11. **Một transaction tạo Order+Lines phải atomic**; lỗi ở một child không được khiến parent committed nửa chừng.
12. **`@Version` phát hiện concurrent stale updates của entity row**, nhưng không mặc nhiên bao phủ mọi chỉnh sửa child hoặc bulk SQL.
13. **Flush, clear và EntityManager mới là cách kiểm chứng thực tế persistence**; chỉ assert object trong memory là thiếu.
14. **Repository read contracts cần projection/fetch plan theo use case**, tránh N+1 và không trả entity graph trực tiếp qua REST.
15. **Test bằng migrations và DB mục tiêu** để chắc generated keys, numeric precision, constraints và locking đúng môi trường triển khai.

**Kết luận:** Một thiết kế JPA đáng tin cậy phải đồng thời làm đúng **identity**, **value semantics**, **relational ownership** và **database integrity**. Khi mô hình Order được tạo bằng khóa sinh phù hợp, Money/Address/Email được ánh xạ rõ ràng, các quan hệ có PK/FK/UNIQUE/CHECK, transaction được đóng đúng ranh giới và integration tests kiểm tra commit/rollback/concurrency, hệ thống mới có cơ sở để phát triển các nghiệp vụ phức tạp mà không âm thầm đánh đổi tính đúng đắn dữ liệu.

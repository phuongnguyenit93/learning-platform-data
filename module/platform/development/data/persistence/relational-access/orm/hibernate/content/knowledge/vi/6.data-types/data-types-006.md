# AttributeConverter cho đối tượng giá trị và giới hạn áp dụng

Trong Java, nhiều khái niệm nghiệp vụ đáng được mô hình hóa thành **đối tượng giá trị (value object)** thay vì dùng trực tiếp `String`, `Long` hay `BigDecimal`. Ví dụ, `Sku` đại diện cho mã sản phẩm hợp lệ, `EmailAddress` đại diện cho địa chỉ email đã được kiểm tra, `CurrencyCode` đại diện cho một mã tiền tệ. Những kiểu dữ liệu này giúp đặt quy tắc nghiệp vụ ngay tại nơi tạo giá trị và tránh truyền nhầm các chuỗi có ý nghĩa khác nhau.

Cơ sở dữ liệu quan hệ lại thường lưu những giá trị đó dưới dạng cột đơn giản như `VARCHAR`, `BIGINT`, `DECIMAL`. Trong JPA/Hibernate, **`AttributeConverter<X, Y>`** giải quyết trường hợp một thuộc tính Java kiểu `X` cần được biểu diễn bằng một giá trị lưu trữ kiểu `Y`. Hibernate gọi converter khi đọc/ghi thuộc tính đã ánh xạ, cho phép mã nghiệp vụ sử dụng `X` mà cơ sở dữ liệu vẫn chứa một giá trị đơn giản.

Bài học sử dụng **Jakarta Persistence** (`jakarta.persistence.*`) và Hibernate ORM. Các dự án JPA cũ dùng `javax.persistence.*` có những khái niệm tương tự nhưng namespace và phiên bản thư viện cần đồng nhất.

## 1. Vì sao không dùng `String` cho mọi dữ liệu?

Xét một entity sản phẩm:

~~~java
@Entity
public class Product {
    @Id
    private Long id;

    private String sku;
    private String name;

    protected Product() {}
}
~~~

Ở đây `sku` và `name` đều là `String`. Trình biên dịch không thể ngăn lập trình viên gán một tên sản phẩm vào ô mã SKU. Mọi chỗ nhận `String sku` còn phải tự nhớ cách kiểm tra: độ dài bao nhiêu, có được chứa khoảng trắng không, chữ hoa/chữ thường xử lý thế nào.

Ta có thể đóng gói những điều kiện đó thành một kiểu Java:

~~~java
Sku sku = Sku.of(" sp-001 ");
System.out.println(sku.value()); // SP-001
~~~

Một giá trị kiểu `Sku` có thể biểu diễn quy tắc: sau khi chuẩn hóa, mã chỉ chứa chữ cái Latin viết hoa, chữ số và dấu gạch ngang, độ dài từ 3 đến 32 ký tự. Từ đó, phương thức nghiệp vụ nhận `Sku` thay vì nhận một chuỗi bất kỳ:

~~~java
public void changeSku(Sku newSku) {
    this.sku = Objects.requireNonNull(newSku);
}
~~~

Nhưng để lưu `Sku` vào cột `VARCHAR(32)`, ORM cần biết cách **chuyển đổi giữa hai kiểu**. Đó là nhiệm vụ của `AttributeConverter`.

### Đối tượng giá trị khác entity thế nào?

| Tiêu chí | Value object như `Sku` | Entity như `Product` |
| --- | --- | --- |
| Định danh | Thường xác định bởi chính giá trị | Có entity ID, thường là khóa chính |
| Ý nghĩa của bằng nhau | Hai `Sku` có cùng mã được xem là cùng giá trị | Hai entity có thể đại diện cùng bản ghi dù là object Java khác nhau |
| Vòng đời | Thường được tạo/thay thế như một giá trị | Được JPA quản lý theo các trạng thái new, managed, detached, removed |
| Nơi lưu | Có thể nằm trong một hoặc nhiều cột của entity khác | Có mapping entity và thường có bản ghi riêng |
| Annotation bắt buộc | Không cần `@Entity` nếu dùng converter thích hợp | Cần entity mapping hợp lệ, bao gồm định danh |

**Value object không đòi hỏi mọi trường hợp phải dùng converter.** Nếu nó có nhiều thành phần cần truy vấn riêng, `@Embeddable` có thể thích hợp hơn. Converter đặc biệt phù hợp khi một giá trị Java muốn được lưu thành **một giá trị cột cơ bản**.

## 2. Hợp đồng của `AttributeConverter<X, Y>`

JPA định nghĩa giao diện:

~~~java
package jakarta.persistence;

public interface AttributeConverter<X, Y> {
    Y convertToDatabaseColumn(X attribute);
    X convertToEntityAttribute(Y dbData);
}
~~~

Hai tham số kiểu có ý nghĩa:

- **`X`:** kiểu của thuộc tính ở phía Java, ví dụ `Sku`.
- **`Y`:** kiểu trung gian dùng để lưu trữ qua JDBC, ví dụ `String`.

Hai phương thức chịu trách nhiệm chuyển đổi theo hai hướng:

~~~text
Ứng dụng Java                        JPA/Hibernate                        Cơ sở dữ liệu
Product.sku: Sku("SP-001")  --convertToDatabaseColumn-->  VARCHAR: "SP-001"
Product.sku: Sku("SP-001")  <--convertToEntityAttribute---  VARCHAR: "SP-001"
~~~

Khi **ghi**, provider đọc thuộc tính Java và gọi `convertToDatabaseColumn` để nhận giá trị phía database. Khi **đọc**, provider nhận giá trị từ cột rồi gọi `convertToEntityAttribute` để tạo lại đối tượng cho entity.

Kiểu `Y` nên là kiểu dữ liệu cơ bản mà provider có thể ánh xạ tới JDBC phù hợp, chẳng hạn `String`, `Integer`, `Long`, `BigDecimal` hay một kiểu Java thời gian được hỗ trợ. `AttributeConverter` **không tự tạo một cơ chế JDBC tùy ý** cho mọi kiểu `Y` phức tạp.

### Converter không phải trình quản lý vòng đời entity

`AttributeConverter` chỉ chuyển **giá trị thuộc tính**; nó không cung cấp:

- Một entity ID mới.
- Một `EntityManager` hoặc transaction riêng.
- Quan hệ khóa ngoại giữa entity.
- Khả năng đọc/ghi nhiều bảng.
- Cơ chế theo dõi thay đổi trên object theo cách riêng.

Những việc đó thuộc trách nhiệm của entity mapping, persistence context, transaction và các cơ chế ORM khác.

## 3. Xây dựng value object `Sku` bất biến

Đầu tiên tạo lớp giá trị thuần Java. Lớp này không cần `@Entity`, không cần `@Id` và không cần constructor không tham số kiểu JPA.

**`Sku.java`:**

~~~java
package com.example.catalog.domain;

import java.util.Locale;
import java.util.Objects;

public final class Sku {
    private final String value;

    private Sku(String value) {
        this.value = value;
    }

    public static Sku of(String raw) {
        String normalized = Objects.requireNonNull(raw, "sku")
            .trim()
            .toUpperCase(Locale.ROOT);

        if (!normalized.matches("[A-Z0-9-]{3,32}")) {
            throw new IllegalArgumentException(
                "SKU phải gồm 3-32 ký tự A-Z, 0-9 hoặc dấu -"
            );
        }

        return new Sku(normalized);
    }

    public String value() {
        return value;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        return other instanceof Sku sku
            && value.equals(sku.value);
    }

    @Override
    public int hashCode() {
        return value.hashCode();
    }

    @Override
    public String toString() {
        return value;
    }
}
~~~

Thiết kế này có các đặc điểm đáng chú ý:

1. **`final` và field `final`:** sau khi tạo, một `Sku` không thể bị sửa tại chỗ.
2. **Factory `of(...)`:** mọi giá trị đều đi qua cùng quy tắc kiểm tra và chuẩn hóa.
3. **`Locale.ROOT`:** tránh thay đổi cách chuyển chữ hoa theo locale của máy chạy.
4. **`equals`/`hashCode` dựa trên giá trị:** hai instance `Sku.of("sp-001")` và `Sku.of("SP-001")` bằng nhau về mặt nghiệp vụ.
5. **Không phụ thuộc Hibernate:** lớp có thể dùng trong domain, kiểm thử thuần Java và các tầng nghiệp vụ khác.

Quy tắc chuẩn hóa chữ hoa ở đây là **quy tắc SKU minh họa**. Với dữ liệu khác, ví dụ địa chỉ email hoặc mã có phân biệt hoa/thường, không nên tự động áp dụng cùng quy tắc mà không xét yêu cầu nghiệp vụ.

## 4. Viết `SkuConverter`

Tạo một lớp triển khai `AttributeConverter<Sku, String>` và đánh dấu `@Converter`.

**`SkuConverter.java`:**

~~~java
package com.example.catalog.persistence;

import com.example.catalog.domain.Sku;
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = false)
public class SkuConverter implements AttributeConverter<Sku, String> {

    @Override
    public String convertToDatabaseColumn(Sku attribute) {
        return attribute == null ? null : attribute.value();
    }

    @Override
    public Sku convertToEntityAttribute(String dbData) {
        return dbData == null ? null : Sku.of(dbData);
    }
}
~~~

Ở chiều ghi, `Sku("SP-001")` trở thành `"SP-001"`. Ở chiều đọc, chuỗi database `"SP-001"` được đưa qua `Sku.of(...)` để trở lại đối tượng giá trị có quy tắc rõ ràng.

`@Converter(autoApply = false)` nghĩa là converter được khai báo nhưng **không tự động áp dụng cho mọi thuộc tính `Sku`**. Các thuộc tính cần dùng converter phải lựa chọn bằng `@Convert` hoặc có mapping tương đương.

### Xử lý `null`

Trong ví dụ, cả hai chiều đều chuyển `null` thành `null`. Đây là lựa chọn phù hợp khi một thuộc tính có thể thiếu giá trị. Tuy nhiên:

- Converter không quyết định cột có được `NULL` hay không; chuyện đó thuộc schema và metadata cột.
- Với thuộc tính bắt buộc như mã SKU của sản phẩm, nên kết hợp kiểm tra trong domain và `@Column(nullable = false)` cùng ràng buộc `NOT NULL` thực tế trong database.
- Có thể thiết kế converter ánh xạ `null` thành giá trị thay thế, nhưng cần đặc biệt cẩn thận để tránh làm mờ sự khác biệt giữa “thiếu giá trị” và “giá trị mặc định”.

Converter cũng có thể nhận dữ liệu cũ không hợp lệ trong lúc đọc: nếu `dbData = "invalid sku!"`, `Sku.of(dbData)` ném lỗi. Đây có thể là hành vi mong muốn để phát hiện dữ liệu hỏng, nhưng việc triển khai vào hệ thống đang có dữ liệu phải tính đến bước làm sạch dữ liệu hoặc chuyển đổi schema trước.

## 5. Sử dụng converter trên thuộc tính entity

Đánh dấu thuộc tính bằng `@Convert(converter = SkuConverter.class)`:

**`Product.java`:**

~~~java
package com.example.catalog.domain;

import com.example.catalog.persistence.SkuConverter;
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Convert(converter = SkuConverter.class)
    @Column(name = "sku", nullable = false, unique = true, length = 32)
    private Sku sku;

    @Column(name = "name", nullable = false, length = 160)
    private String name;

    @Column(name = "price", nullable = false, precision = 15, scale = 2)
    private BigDecimal price;

    protected Product() {
        // JPA sử dụng constructor không tham số.
    }

    public Product(Sku sku, String name, BigDecimal price) {
        this.sku = Objects.requireNonNull(sku);
        this.name = Objects.requireNonNull(name);
        this.price = Objects.requireNonNull(price);
        if (name.isBlank() || name.length() > 160 || price.signum() < 0) {
            throw new IllegalArgumentException("Thông tin sản phẩm không hợp lệ");
        }
    }

    public Long getId() {
        return id;
    }

    public Sku getSku() {
        return sku;
    }

    public void changeSku(Sku sku) {
        this.sku = Objects.requireNonNull(sku);
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

Giả sử database PostgreSQL đã có schema:

~~~sql
CREATE TABLE products (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(32) NOT NULL UNIQUE,
    name VARCHAR(160) NOT NULL,
    price NUMERIC(15, 2) NOT NULL CHECK (price >= 0)
);
~~~

| Thành phần Java | Ánh xạ SQL |
| --- | --- |
| `Product` | Bảng `products` |
| `Product.id: Long` | `id BIGINT PRIMARY KEY` |
| `Product.sku: Sku` | `sku VARCHAR(32)`, thông qua `SkuConverter` |
| `Product.name: String` | `name VARCHAR(160)` |
| `Product.price: BigDecimal` | `price NUMERIC(15,2)` |

**Trong bảng không có cột kiểu `Sku`.** Cơ sở dữ liệu lưu chuỗi `SP-001`. Object `Sku` chỉ tồn tại ở phía Java; Hibernate sử dụng converter để nối hai biểu diễn.

Khi viết quy tắc nghiệp vụ như kiểm tra SKU hợp lệ, ta làm việc với `Sku`; khi tối ưu chỉ mục, kiểm tra unique hoặc chạy SQL, ta xét `VARCHAR(32)` và ràng buộc thực sự ở database.

## 6. Luồng ghi và đọc qua Hibernate

Giả sử ứng dụng đã tạo `EntityManagerFactory emf` và cấu hình kết nối, bảng tương ứng.

### Ghi một sản phẩm

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityTransaction;
import java.math.BigDecimal;

EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Product product = new Product(
        Sku.of("sp-001"),
        "Sổ tay",
        new BigDecimal("75000.00")
    );

    em.persist(product);
    tx.commit();
} catch (RuntimeException e) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw e;
} finally {
    em.close();
}
~~~

Khi Hibernate thực hiện thao tác chèn, về mặt khái niệm nó cần lấy `product.getSku()`, gọi `convertToDatabaseColumn` và truyền giá trị `"SP-001"` xuống JDBC. SQL minh họa:

~~~sql
INSERT INTO products (sku, name, price)
VALUES ('SP-001', 'Sổ tay', 75000.00);
~~~

SQL thực tế có thể dùng tham số `?` hoặc named binding, có thêm thao tác lấy ID và xảy ra tại thời điểm khác nhau tùy chiến lược sinh khóa/flush. Converter không thay thế transaction; chỉ khi giao dịch commit thành công thì thao tác ghi mới được xác nhận.

### Đọc lại từ database

~~~java
EntityManager em = emf.createEntityManager();

try {
    Product product = em.find(Product.class, productId);

    if (product != null) {
        Sku sku = product.getSku();
        System.out.println(sku.value()); // Ví dụ SP-001
    }
} finally {
    em.close();
}
~~~

Giả sử hàng SQL mang chuỗi `SP-001`, khi materialize entity Hibernate chuyển `String` thành `Sku` bằng `convertToEntityAttribute`. Nếu lần đọc được phục vụ từ persistence context hoặc cơ chế cache, đường thực thi không nhất thiết gọi converter ngay ở mỗi lần truy cập getter; ý nghĩa ánh xạ vẫn là thuộc tính Java có kiểu `Sku`.

### Thay đổi thuộc tính

~~~java
Product product = em.find(Product.class, productId);
product.changeSku(Sku.of("sp-002"));
~~~

Trong một transaction phù hợp, Hibernate có thể nhận biết thuộc tính đã đổi qua cơ chế *dirty checking*, gọi converter cho giá trị mới và gửi `UPDATE` vào database khi flush. Thời điểm phát SQL phụ thuộc persistence context và flush mode.

Với value object **bất biến** như `Sku`, thay thế toàn bộ instance bằng một giá trị khác thường dễ theo dõi hơn sửa một object mutable nằm bên trong entity.

## 7. Khai báo tường minh hay áp dụng tự động?

Hai cách phổ biến để dùng converter là **`@Convert` trên thuộc tính** và **`@Converter(autoApply = true)` trên lớp converter**.

### Cách A — Tường minh tại thuộc tính

~~~java
@Converter(autoApply = false)
public class SkuConverter implements AttributeConverter<Sku, String> {
    // Hai phương thức chuyển đổi.
}
~~~

~~~java
@Convert(converter = SkuConverter.class)
private Sku sku;
~~~

**Ưu điểm:** nhìn entity là biết thuộc tính dùng quy tắc chuyển đổi nào; thích hợp khi chỉ vài field cần đổi hoặc cùng kiểu Java có nhiều cách biểu diễn database.

**Hạn chế:** phải thêm `@Convert` ở từng thuộc tính cần ánh xạ; nếu quên có thể gặp lỗi xác định kiểu JDBC khi bootstrap.

### Cách B — Tự động cho những thuộc tính tương thích

~~~java
@Converter(autoApply = true)
public class SkuConverter implements AttributeConverter<Sku, String> {
    // Hai phương thức chuyển đổi.
}
~~~

Khi converter đã được provider khám phá/đăng ký, nó có thể tự áp dụng cho các **basic attribute** có kiểu `Sku` phù hợp trong cùng persistence unit:

~~~java
@Column(name = "sku", length = 32)
private Sku sku;
~~~

Không nhất thiết phải thêm `@Convert` nếu auto-apply hoạt động đúng.

**Ưu điểm:** tiện với những kiểu giá trị có đúng một cách lưu trữ nhất quán, được dùng ở nhiều entity.

**Hạn chế:** phạm vi áp dụng rộng. Nếu vô tình bật auto-apply cho kiểu phổ biến như `String` hoặc `Long`, nhiều thuộc tính không mong muốn có thể bị chuyển đổi. Nếu có nhiều converter tự động cho cùng kiểu, cần giải quyết xung đột thay vì giả định provider chọn ngẫu nhiên đúng converter.

Một converter đánh dấu `@Converter` cũng cần được đưa vào tập metadata bằng cơ chế khám phá hoặc khai báo phù hợp với cách bootstrap JPA/Hibernate. Không nên mặc định class converter đặt ở một package bất kỳ trên classpath luôn được mọi cấu hình provider quét thấy.

### Tắt chuyển đổi tự động ở một field

`@Convert(disableConversion = true)` có thể yêu cầu bỏ áp dụng converter tại thuộc tính tương ứng:

~~~java
@Convert(disableConversion = true)
@Column(name = "raw_note")
private String rawNote;
~~~

Ví dụ trên hữu ích khi có một converter tự động cho `String` và muốn `rawNote` dùng cách ánh xạ mặc định. **Nếu áp dụng cách này cho `Sku`, trong khi provider không có cách ánh xạ `Sku` nào khác, việc tắt converter có thể làm thuộc tính không thể ánh xạ**. Tắt chuyển đổi không có nghĩa Hibernate tự biết lưu một value object tùy ý.

### Converter trên một thuộc tính của `@Embeddable`

Khi một đối tượng nhúng chứa basic attribute cần chuyển đổi, có thể đặt `@Convert` trực tiếp trên thuộc tính đó:

~~~java
@Embeddable
public class ProductLabel {
    @Convert(converter = SkuConverter.class)
    @Column(name = "label_sku", length = 32)
    private Sku labelSku;

    protected ProductLabel() {}
}
~~~

Entity chứa `@Embedded ProductLabel label` sẽ lưu `labelSku` theo converter và mapping tương ứng. JPA cũng hỗ trợ `@Convert(attributeName = "...")` cho một số trường hợp ghi đè chuyển đổi trên thuộc tính lồng trong embeddable; tên đường dẫn phải phù hợp cấu trúc attribute cụ thể. Cách tường minh ngay trên field là lựa chọn dễ nhìn trong ví dụ đơn giản.

## 8. Một converter ánh xạ một basic attribute: giới hạn quan trọng nhất

`AttributeConverter<X, Y>` tạo ra **một giá trị database tương ứng với một mapped basic attribute**. Nó không tự động tách object ra nhiều cột SQL.

Ví dụ một giá trị `Money` gồm:

~~~java
public final class Money {
    private final BigDecimal amount;
    private final Currency currency;

    // Constructor, getter và quy tắc nghiệp vụ...
}
~~~

Muốn lưu độc lập **số tiền** và **mã tiền tệ** thành hai cột:

~~~text
amount          NUMERIC(15, 2)
currency_code   VARCHAR(3)
~~~

thì một converter `AttributeConverter<Money, String>` không tự sinh được hai cột này. Nếu converter biến `Money` thành chuỗi như `"75000|VND"`, về mặt database đó chỉ là **một cột**, khiến truy vấn số học, sắp xếp và chỉ mục theo lượng tiền khó xử lý hơn.

Với hai cột độc lập, dùng `@Embeddable` thường phù hợp hơn:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Embeddable;
import java.math.BigDecimal;
import java.util.Objects;

@Embeddable
public class MonetaryAmount {
    @Column(name = "amount", nullable = false, precision = 15, scale = 2)
    private BigDecimal amount;

    @Column(name = "currency_code", nullable = false, length = 3)
    private String currencyCode;

    protected MonetaryAmount() {
    }

    public MonetaryAmount(BigDecimal amount, String currencyCode) {
        this.amount = Objects.requireNonNull(amount);
        this.currencyCode = Objects.requireNonNull(currencyCode);
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public String getCurrencyCode() {
        return currencyCode;
    }
}
~~~

Trong entity:

~~~java
@Entity
public class Invoice {
    @Id
    private Long id;

    @Embedded
    private MonetaryAmount total;

    protected Invoice() {
    }
}
~~~

Điểm cần phân biệt:

| Mục tiêu | `AttributeConverter` | `@Embeddable` |
| --- | --- | --- |
| Bọc một mã `String` thành kiểu `Sku` | Rất phù hợp | Thường không cần thiết |
| Lưu một value object thành một giá trị cột | Phù hợp | Cũng có thể dùng tùy mô hình |
| Lưu một value object thành nhiều cột riêng | Không tự hỗ trợ | Phù hợp |
| Truy vấn theo từng thành phần của value object | Bị giới hạn khi đã mã hóa trong một cột | Tự nhiên hơn nhờ các cột riêng |
| Tận dụng ràng buộc và chỉ mục trên từng thành phần | Khó nếu chỉ lưu chuỗi gộp | Dễ hơn |
| Định nghĩa quan hệ entity qua khóa ngoại | Không | Cũng không trực tiếp thay `@ManyToOne` |
| Tạo bản ghi có định danh riêng | Không | Không; cần `@Entity` |

## 9. Khi muốn lưu enum bằng mã nghiệp vụ

Một trường hợp phổ biến là cần lưu enum bằng mã ổn định như `N`, `P`, `C`, thay vì tên enum hoặc thứ tự số.

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED
}
~~~

Nếu chỉ cần lưu tên enum, `@Enumerated(EnumType.STRING)` thường đủ:

~~~java
@Enumerated(EnumType.STRING)
private OrderStatus status;
~~~

Nhưng khi database phải lưu mã riêng, có thể dùng converter:

~~~java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter(autoApply = false)
public class OrderStatusConverter
        implements AttributeConverter<OrderStatus, String> {

    @Override
    public String convertToDatabaseColumn(OrderStatus value) {
        if (value == null) {
            return null;
        }

        return switch (value) {
            case NEW -> "N";
            case PAID -> "P";
            case CANCELLED -> "C";
        };
    }

    @Override
    public OrderStatus convertToEntityAttribute(String code) {
        if (code == null) {
            return null;
        }

        return switch (code) {
            case "N" -> OrderStatus.NEW;
            case "P" -> OrderStatus.PAID;
            case "C" -> OrderStatus.CANCELLED;
            default -> throw new IllegalArgumentException(
                "Mã trạng thái không xác định: " + code
            );
        };
    }
}
~~~

Entity sử dụng:

~~~java
@Convert(converter = OrderStatusConverter.class)
@Column(name = "status_code", nullable = false, length = 1)
private OrderStatus status;
~~~

**Không đặt thêm `@Enumerated` lên chính field `status` đang dùng converter.** Theo quy tắc JPA, các thuộc tính đã được đánh dấu `@Enumerated` không phải đối tượng áp dụng chuyển đổi thông thường của `AttributeConverter`; kết hợp hai cơ chế cho cùng thuộc tính dễ gây xung đột hoặc hành vi không di động.

Ngoài ra, không nên sử dụng `EnumType.ORDINAL` cho một enum mà thứ tự hằng có thể thay đổi: thêm/chèn hằng có thể làm những số nguyên cũ bị hiểu thành trạng thái khác. Converter dùng mã riêng hỗ trợ giữ giá trị database ổn định hơn khi tên enum trong mã Java thay đổi, miễn là bảng ánh xạ mã được bảo trì có chủ đích.

## 10. Những chỗ `AttributeConverter` không được JPA bảo đảm áp dụng

Không phải mọi thuộc tính trong entity đều có thể gắn converter và nhận hành vi chuẩn, di động. Những trường hợp quan trọng:

| Vị trí hoặc kiểu mapping | Khả năng áp dụng converter theo JPA | Cách tiếp cận thường phù hợp |
| --- | --- | --- |
| Thuộc tính basic không có mapping đặc biệt | Trường hợp chính được hỗ trợ | `@Convert` hoặc `autoApply` |
| Basic attribute trong embeddable | Có hỗ trợ theo quy tắc mapping phù hợp | `@Convert` tại field hoặc override thích hợp |
| Thuộc tính `@Id` / `@EmbeddedId` | Không được JPA bảo đảm cho conversion thông thường | Chọn kiểu ID được hỗ trợ hoặc dùng giải pháp provider-specific có chủ đích |
| Thuộc tính `@Version` | Không được JPA bảo đảm | Dùng kiểu version được provider hỗ trợ |
| Quan hệ `@ManyToOne`, `@OneToOne` và các relationship | Không | Dùng relationship mapping và khóa ngoại |
| Thuộc tính có `@Enumerated` | Không áp dụng chuyển đổi theo cơ chế thông thường | Chọn `@Enumerated` **hoặc** converter |
| Thuộc tính có `@Temporal` | Không áp dụng chuyển đổi theo cơ chế thông thường | Dùng temporal mapping hoặc thiết kế lại kiểu thuộc tính |
| Một object cần nhiều cột | Không tự tách đa cột | `@Embeddable` hoặc mapping riêng |
| Một object cần nhiều bảng/bản ghi | Không | Entity, association, collection mapping |
| SQL không đi qua ánh xạ thuộc tính của JPA | Không mặc định | Chuyển đổi thủ công hoặc sử dụng mapping/result thích hợp |

Đối với ID, version, relationship, enum có `@Enumerated` và temporal có `@Temporal`, nếu provider nào đó vẫn chấp nhận converter thì cần coi đó là **hành vi riêng hoặc không di động**, phải kiểm tra tài liệu cho đúng phiên bản; không nên thiết kế dựa trên giả định mọi JPA provider sẽ xử lý giống nhau.

### Converter không trực tiếp thay thế `@ManyToOne`

Không nên coi quan hệ tới entity khác là một giá trị có thể được converter tự động biến thành FK:

~~~java
@ManyToOne
@JoinColumn(name = "customer_id")
private Customer customer;
~~~

Đây là **association**, thuộc mô hình quan hệ do JPA quản lý. Nếu muốn cất mỗi mã khách hàng như một giá trị đơn trong bảng mà không có relationship, đó là một mô hình khác và cần tự xử lý tính nhất quán tham chiếu.

### Converter không tự định nghĩa khóa hay version

Ví dụ muốn dùng `ProductId` thay cho `Long` ở `@Id` có thể rất hấp dẫn. Tuy nhiên, `@Convert(converter = ProductIdConverter.class)` trên ID không phải một khả năng portable được JPA bảo đảm. Những yêu cầu typed ID có thể cần kiểu cơ bản tương thích, cơ chế định danh được provider hỗ trợ hoặc mapping đặc thù Hibernate; nên phân tích trước khi sử dụng.

Tương tự, `@Version` dùng cơ chế optimistic locking của ORM và cần kiểu dữ liệu phù hợp. Không dùng converter để tùy ý thay đổi hình dạng version mà không có hỗ trợ rõ ràng.

## 11. Truy vấn JPQL, Criteria và SQL native

Với thuộc tính `Product.sku` đã được ánh xạ bằng converter, **JPQL làm việc theo kiểu Java của entity**, không phải trực tiếp với chuỗi cột SQL.

Ví dụ truy vấn typed JPQL:

~~~java
Sku requestedSku = Sku.of("sp-001");

Product product = em.createQuery(
        "select p from Product p where p.sku = :sku",
        Product.class
    )
    .setParameter("sku", requestedSku)
    .getSingleResult();
~~~

Ở đây tham số `:sku` có kiểu logic `Sku`; vì biểu thức so sánh tham chiếu tới thuộc tính mapped `p.sku`, Hibernate có thông tin converter để bind xuống kiểu JDBC tương ứng. Nếu không có hàng khớp, `getSingleResult()` ném `NoResultException` (trừ khi API truy vấn/phiên bản hỗ trợ phương thức kết quả thay thế); xử lý trường hợp không tìm thấy theo nhu cầu nghiệp vụ.

Có thể viết bằng Criteria API:

~~~java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Product> query = cb.createQuery(Product.class);
Root<Product> root = query.from(Product.class);

query.select(root).where(
    cb.equal(root.get("sku"), Sku.of("SP-001"))
);

List<Product> matches = em.createQuery(query).getResultList();
~~~

Trong code thực tế, import `jakarta.persistence.criteria.CriteriaBuilder`, `CriteriaQuery` và `Root` tương ứng. Khi truy vấn dựa trên đường dẫn thuộc tính đã ánh xạ, provider có cơ sở để áp dụng conversion.

### Phân biệt truy vấn SQL native

Với native query:

~~~java
List<?> rows = em.createNativeQuery(
        "select id from products where sku = :sku"
    )
    .setParameter("sku", "SP-001")
    .getResultList();
~~~

SQL native tham chiếu **cột và kiểu database**. Không nên mặc định provider sẽ tìm `SkuConverter` để tự động chuyển mọi tham số native SQL; ở ví dụ trên, sử dụng giá trị `String` phù hợp với cột `VARCHAR`. Nếu thao tác thông qua một API/query không có thông tin đường dẫn mapped attribute, ứng dụng có thể cần chuyển đổi tường minh hoặc cấu hình kiểu riêng cho provider.

**Converter cũng không biến SQL thành truy vấn theo thuộc tính của đối tượng.** Nếu SKU được gộp, mã hóa hoặc băm, điều kiện SQL như `LIKE`, `ORDER BY` và chỉ mục trên cột hoạt động theo **giá trị đã chuyển đổi**, có thể khác hoàn toàn ý nghĩa so sánh của object trong Java.

## 12. Quy tắc chuyển đổi phải phù hợp đặc tính dữ liệu

Một converter tốt nên có tính **dự đoán được, ổn định và nhất quán**. Chuyển đổi theo chiều ghi và đọc cần phục hồi được thông tin nghiệp vụ cần thiết.

Với `Sku`:

~~~text
Sku.of(" sp-001 ") → Sku("SP-001")
convertToDatabaseColumn → "SP-001"
convertToEntityAttribute → Sku("SP-001")
~~~

Sự chuẩn hóa xảy ra trước hoặc trong lúc tạo `Sku`, nên đối tượng không chứa hai biểu diễn khác nhau cho cùng một mã.

Với value object phức tạp hơn, cần trả lời:

1. Dữ liệu có phải **một giá trị logic** phù hợp cất trong một cột không?
2. Sau khi ghi rồi đọc, có giữ được những thông tin cần bảo toàn không?
3. Tên, kiểu, độ dài, độ chính xác và `NULL` của cột có đủ không?
4. Định dạng database có ổn định khi nâng cấp phiên bản ứng dụng không?
5. Database có cần lọc, sắp xếp, nối hoặc index theo từng phần của giá trị không?
6. Dữ liệu hiện có có thể đọc bằng converter mới không?

### Đặc biệt cẩn thận với số tiền

Không nên lưu `BigDecimal` bằng:

~~~java
return amount.toString() + " VND";
~~~

rồi kỳ vọng database thực hiện được phép tính số học chính xác, so sánh trị số, index số hoặc chuyển đổi tiền tệ. Nếu cần thao tác số, nên dùng cột `DECIMAL/NUMERIC` cho lượng tiền và cột riêng cho mã tiền tệ khi phù hợp. Với một kiểu wrapper đơn giản quanh `BigDecimal`, converter sang `BigDecimal` có thể phù hợp hơn converter sang `String`.

### Đặc biệt cẩn thận với ngày giờ

Thời điểm `Instant`, thời gian địa phương `LocalDateTime`, múi giờ `ZoneId` và ngày `LocalDate` là những khái niệm khác nhau. Trước khi viết converter chuyển chúng thành chuỗi, cần xem Hibernate/JDBC đã hỗ trợ mapping trực tiếp chưa, và database có cần truy vấn theo khoảng thời gian hay không.

Không nên tự thêm `@Temporal` cho các kiểu `java.time` hiện đại theo thói quen cũ. `@Temporal` vốn dành cho những kiểu thời gian legacy như `java.util.Date`/`Calendar` trong JPA. Với thuộc tính đã đánh dấu `@Temporal`, converter không phải cơ chế phối hợp chuẩn.

## 13. Đối tượng bất biến và phát hiện thay đổi

Hibernate theo dõi thay đổi của managed entity bằng các cơ chế snapshot/dirty checking hoặc bytecode enhancement, tùy cấu hình.

Nếu converter làm việc với một value object **bất biến**, chẳng hạn `Sku`, ứng dụng thay toàn bộ đối tượng:

~~~java
product.changeSku(Sku.of("SP-002"));
~~~

Cách này rõ ràng: giá trị thuộc tính trước và sau khác nhau theo quy tắc `equals`; Hibernate có thể phát hiện thay đổi để ghi giá trị cột mới khi đồng bộ persistence context.

Nếu dùng value object **mutable**:

~~~java
product.getSomeValue().setPart("new value");
~~~

thì việc Hibernate có phát hiện thay đổi đúng hay không còn phụ thuộc kiểu dữ liệu, chiến lược so sánh snapshot, cách converter ánh xạ, cấu hình mutability và các cơ chế nội bộ. Với những trường hợp giá trị được converter tạo ra là mutable collection, mảng hoặc object phức tạp, cần đặc biệt chú ý tới việc sao chép snapshot và equality.

Vì vậy, với đối tượng giá trị dùng `AttributeConverter`, **ưu tiên bất biến**, định nghĩa `equals`/`hashCode` dựa trên giá trị và cập nhật bằng cách thay instance. Những kiểu mutable không tự động bị cấm, nhưng có thể cần mapping/kiểm soát mutability theo Hibernate để dirty checking và caching hoạt động như mong đợi.

## 14. Hiệu năng và thiết kế converter

Hibernate có thể gọi converter khi đọc/ghi nhiều hàng. Một converter chạy cho 100.000 bản ghi mà thực hiện thao tác đắt đỏ sẽ ảnh hưởng rõ đến thời gian xử lý.

Nên ưu tiên converter:

- **Không lưu trạng thái thay đổi theo mỗi lần gọi:** tránh chia sẻ biến đếm hoặc dữ liệu của entity trước giữa các conversion.
- **Thread-safe:** provider có thể quản lý và tái sử dụng converter giữa nhiều thao tác/phiên.
- **Không thực hiện truy vấn database từ converter:** converter không nên phụ thuộc việc mở `EntityManager` mới.
- **Không gọi HTTP hoặc I/O mạng cho từng giá trị:** một lần đọc danh sách lớn có thể phát sinh nhiều lời gọi ngoài mong muốn.
- **Không làm rơi thông tin âm thầm:** dữ liệu sai định dạng nên có cách xử lý rõ ràng.
- **Có quy tắc lỗi ổn định:** ngoại lệ đọc một hàng không hợp lệ cần được xử lý ở ranh giới thích hợp thay vì làm biến đổi dữ liệu bất ngờ.

Một lỗi phổ biến là đặt mã hóa phức tạp, phân tích JSON nặng hoặc tra cứu dịch vụ ngoài vào converter rồi cho rằng vì phương thức có vẻ nhỏ nên chi phí không đáng kể. Trên hệ thống truy vấn nhiều bản ghi, thao tác đó có thể lặp lại rất nhiều lần.

Nếu converter cần dependency từ DI container, khả năng injection và vòng đời converter phụ thuộc cơ chế tích hợp JPA với môi trường đang sử dụng. Không mặc định converter luôn được Spring tạo như mọi `@Component`, hoặc có thể truy cập service tùy ý trong cấu hình Java SE thuần.

## 15. Converter không thay thế schema và ràng buộc dữ liệu

`AttributeConverter` có thể giúp định dạng dữ liệu khi Hibernate thao tác, nhưng **database không biết logic của lớp `Sku`**. Nếu một client SQL trực tiếp chèn `"bad sku"` và database chỉ có `VARCHAR(32)`, ràng buộc kiểu dữ liệu đơn thuần có thể vẫn cho phép giá trị đó.

Ví dụ nên kết hợp:

~~~sql
ALTER TABLE products
ADD CONSTRAINT products_sku_format
CHECK (sku ~ '^[A-Z0-9-]{3,32}$');
~~~

Câu lệnh `~` là toán tử biểu thức chính quy của PostgreSQL. Hệ quản trị khác có cú pháp tương đương khác hoặc cần cách kiểm tra riêng.

Cột `sku` còn có thể cần:

~~~sql
ALTER TABLE products
ADD CONSTRAINT products_sku_unique UNIQUE (sku);
~~~

Nếu bảng đã có ràng buộc `UNIQUE` trong `CREATE TABLE`, không cần thêm lần nữa; các câu trên chỉ minh họa cách đặt ràng buộc tại database.

Cần phân biệt ba tầng:

| Tầng | Ví dụ kiểm tra | Bảo vệ điều gì? |
| --- | --- | --- |
| Value object Java | `Sku.of(...)` | Tạo giá trị nghiệp vụ hợp lệ trong mã Java |
| Mapping JPA | `@Column(nullable = false, length = 32)` | Khai báo ràng buộc/mô tả cột cho provider và DDL khi được áp dụng |
| Database schema | `NOT NULL`, `UNIQUE`, `CHECK` | Bảo vệ dữ liệu cho mọi đường ghi vào database |

Đặc biệt, `@Column(length=32)` không phải validator Java tự động cho mọi thao tác. Nếu hệ thống dùng migration như Flyway/Liquibase, phải bảo đảm schema triển khai thực tế có ràng buộc mong muốn.

## 16. JSON, mã hóa và định dạng dữ liệu riêng

Converter đôi khi được dùng để biểu diễn dữ liệu JSON hoặc chuỗi mã hóa:

~~~text
Java value object
    → JSON String
    → VARCHAR/TEXT/JSON column
~~~

Về nguyên tắc, một converter có thể serialize object thành `String` và deserialize khi đọc; tuy nhiên:

- Nếu kiểu `Y` là `String`, đối với provider đây vẫn là giá trị String. Kiểu SQL vật lý `JSON`/`JSONB` có thể cần mapping JDBC riêng.
- Khi serialize nhiều field thành một cột, SQL tiêu chuẩn không còn coi mỗi field đó là cột độc lập; filter/index phụ thuộc khả năng JSON của database.
- Muốn quản lý định dạng JSON bền vững, cần chính sách versioning cho dữ liệu cũ và xử lý lỗi deserialize.
- Hibernate có hỗ trợ kiểu JSON và các API type riêng trong những phiên bản nhất định; việc sử dụng các API đó là **một quyết định mapping cụ thể của Hibernate**, không phải điều tự động có từ `AttributeConverter`.

Tương tự, converter được dùng để **mã hóa** dữ liệu phải xử lý thêm các vấn đề về quản lý khóa, rotation, IV/nonce, tính toàn vẹn, truy vấn và logging. Việc đặt thuật toán mã hóa vào hai phương thức converter **không đủ** để bảo đảm một thiết kế bảo mật hoàn chỉnh. Mã hóa không xác định (randomized encryption) cũng có thể làm tìm kiếm bằng `WHERE column = ?` không còn hoạt động theo cách so sánh plaintext thông thường.

Với dữ liệu nhạy cảm hoặc định dạng phức tạp, hãy đánh giá mapping, truy vấn, di chuyển dữ liệu và vận hành trước khi đưa converter vào.

## 17. Khi thay đổi converter hoặc đổi định dạng lưu

Giả sử phiên bản đầu lưu SKU:

~~~text
SP-001
~~~

Sau đó một bản phát hành mới muốn đổi biểu diễn thành:

~~~text
SKU:SP-001
~~~

Nếu chỉ sửa:

~~~java
@Override
public String convertToDatabaseColumn(Sku attribute) {
    return "SKU:" + attribute.value();
}
~~~

mà không thay `convertToEntityAttribute` và không xử lý các hàng có định dạng cũ, ứng dụng có thể không đọc được dữ liệu đã lưu hoặc tạo dữ liệu hỗn hợp.

Một thay đổi định dạng lưu cần xem xét:

1. **Khả năng đọc dữ liệu cũ:** converter mới cần hỗ trợ hai định dạng trong giai đoạn chuyển tiếp, hoặc migration phải sửa dữ liệu trước.
2. **Khả năng ghi trong thời gian triển khai nhiều phiên bản:** nếu hai version ứng dụng chạy đồng thời, version cũ có đọc được dữ liệu mới không?
3. **Ràng buộc cột:** chiều dài, loại cột, unique index và CHECK constraint có thay đổi không?
4. **Truy vấn SQL/JPQL:** các điều kiện trên cột đã chuyển đổi có cần cập nhật không?
5. **Cache:** dữ liệu/cache của phiên bản trước có thể mang dạng khác với metadata mới.
6. **Rollback triển khai:** có đường quay lại tương thích không?

Thay đổi converter là một thay đổi **hợp đồng dữ liệu** khi biểu diễn trong database thay đổi. Đừng chỉ xem nó như refactor nội bộ Java.

## 18. Một số trường hợp sử dụng nên chọn converter

| Kiểu value object Java | Giá trị lưu phù hợp | Nhận xét |
| --- | --- | --- |
| `Sku` đã chuẩn hóa | `VARCHAR(32)` | Bọc mã với quy tắc định dạng |
| `CurrencyCode` | `CHAR(3)` hoặc `VARCHAR(3)` | Mã ISO có thể biểu diễn đơn cột |
| `CountryCode` | `CHAR(2)` | Bọc mã quốc gia đã xác thực |
| `PhoneNumber` theo định dạng xác định | `VARCHAR` phù hợp | Cần quy tắc chuẩn hóa rõ ràng |
| `Percentage` bọc `BigDecimal` | `DECIMAL` | Bảo toàn khả năng tính toán số |
| Enum có mã ổn định riêng | `CHAR(1)`/`VARCHAR` | Dùng converter thay `@Enumerated` |
| Một value object gồm `amount` và `currency` cần query riêng | Hai cột `DECIMAL` và `CHAR(3)` | Thường ưu tiên `@Embeddable` |
| Object cần nhiều hàng/bảng | FK hoặc bảng phụ | Cần entity/association/collection mapping |

Converter phát huy giá trị khi mang lại **type safety trong Java** mà vẫn giữ **schema quan hệ rõ ràng**.

## 19. Ví dụ kiểm tra hai chiều chuyển đổi

Bản thân `SkuConverter` là một lớp Java thông thường triển khai interface, nên có thể kiểm tra logic chuyển đổi mà không cần khởi động database.

Ví dụ sử dụng JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class SkuConverterTest {
    private final SkuConverter converter = new SkuConverter();

    @Test
    void shouldWriteNormalizedSku() {
        Sku sku = Sku.of(" sp-001 ");

        assertEquals(
            "SP-001",
            converter.convertToDatabaseColumn(sku)
        );
    }

    @Test
    void shouldReadValueObject() {
        Sku result = converter.convertToEntityAttribute("SP-001");

        assertEquals(Sku.of("sp-001"), result);
    }

    @Test
    void shouldHandleNull() {
        assertNull(converter.convertToDatabaseColumn(null));
        assertNull(converter.convertToEntityAttribute(null));
    }

    @Test
    void shouldRejectInvalidDatabaseValue() {
        assertThrows(
            IllegalArgumentException.class,
            () -> converter.convertToEntityAttribute("bad sku!")
        );
    }
}
~~~

Trong lớp kiểm tra, cần import `Sku` và `SkuConverter` theo đúng package của dự án nếu chúng nằm ở package khác. Kiểm tra converter thuần giúp khẳng định logic `X → Y` và `Y → X` của chính lớp converter.

Để kiểm tra **mapping thực tế**, nên có một bài kiểm tra tích hợp JPA/Hibernate riêng với database hoặc môi trường test phù hợp:

1. Khởi tạo `EntityManagerFactory` có entity `Product` và converter tương ứng.
2. Persist sản phẩm với `Sku.of("sp-001")`, commit và đóng persistence context.
3. Đọc giá trị `sku` trực tiếp bằng SQL; kỳ vọng là chuỗi `SP-001`.
4. Mở persistence context mới, nạp sản phẩm bằng JPA; kỳ vọng `product.getSku()` là `Sku` có giá trị `SP-001`.
5. Thay `Sku` trong một transaction, commit rồi đọc lại; kỳ vọng DB chứa giá trị mới.

Phần kiểm tra tích hợp giúp quan sát provider có thực sự đăng ký converter, ánh xạ tới đúng cột, binding query và xử lý transaction đúng như thiết kế hay không. Logic thuần của converter và cấu hình ORM là hai vấn đề khác nhau.

## 20. Những nhầm lẫn hay gặp

| Nhầm lẫn | Cách hiểu chính xác |
| --- | --- |
| Gắn `@Converter` là Hibernate tự áp dụng ở mọi field | Còn phụ thuộc `autoApply`, `@Convert`, tập metadata và phạm vi thuộc tính được hỗ trợ |
| Converter tạo được hai cột từ một object | Converter biến một basic attribute thành một giá trị lưu; muốn nhiều cột thường dùng `@Embeddable` |
| Converter thay thế `@ManyToOne` | Relationship dùng mapping và FK, không phải basic attribute conversion |
| Có thể gắn converter cho `@Id`/`@Version` như field bình thường | Không được Jakarta Persistence bảo đảm theo cơ chế conversion thông thường |
| Có thể đồng thời dùng `@Enumerated` và converter trên cùng thuộc tính | Hai cơ chế có thể xung đột; chọn một cách ánh xạ |
| `@Column(length=32)` tự đảm bảo chuỗi luôn hợp lệ | Value object, validator và database constraint đảm nhiệm các phần kiểm soát khác nhau |
| Query native SQL luôn tự convert `Sku` sang `String` | Native query không nhất thiết có metadata của mapped attribute để áp dụng converter |
| Converter là nơi phù hợp để gọi HTTP/DB mỗi lần đọc field | Converter nên nhẹ, nhất quán, stateless và thread-safe |
| Chỉ cần cập nhật converter khi thay đổi định dạng trong DB | Dữ liệu cũ, migration, constraint, query và nhiều phiên bản ứng dụng đều bị ảnh hưởng |
| Cần `@Entity` cho lớp `Sku` | `Sku` là value object, không có entity identity; chỉ `Product` là entity trong ví dụ |

### Gợi ý xử lý lỗi

- **Hibernate không xác định được JDBC type cho `Sku`:** kiểm tra converter đã được đăng ký, đúng `AttributeConverter<Sku, String>` và được áp dụng cho thuộc tính chưa.
- **Vừa thêm converter nhưng dữ liệu đọc lỗi:** kiểm tra định dạng cũ, `null`, giá trị không hợp lệ và chiều đọc `convertToEntityAttribute`.
- **Tìm theo SKU bằng JPQL không có kết quả:** kiểm tra `Sku.of(...)` chuẩn hóa như thế nào, thuộc tính mapped nào được tham chiếu, giá trị thực trong DB và kiểu tham số.
- **Native query dùng tham số `Sku` lỗi binding:** thử chuyển tường minh thành `String` theo giá trị DB của converter hoặc cấu hình kiểu bind riêng thích hợp.
- **Lưu object mutable rồi sửa thuộc tính bên trong không ra `UPDATE`:** xem lại equality/mutability và dirty checking; cân nhắc immutable value object và thay toàn bộ field.
- **Thay đổi converter gây lỗi schema:** kiểm tra kiểu cột, độ dài, precision/scale và migration thay vì chỉ nhìn annotation.

## 21. Câu hỏi tự luyện

**Câu 1.** Với `AttributeConverter<Sku, String>`, `X` và `Y` lần lượt có ý nghĩa gì?

**Trả lời:** `X = Sku` là kiểu thuộc tính Java; `Y = String` là kiểu giá trị dùng để lưu/truy xuất qua ánh xạ JDBC. Hai phương thức converter chuyển đổi hai chiều giữa chúng.

**Câu 2.** Có thể dùng `AttributeConverter<Money, String>` để tự động sinh hai cột `amount` và `currency_code` không?

**Trả lời:** Không. Nó tạo một giá trị lưu từ một basic attribute. Nếu muốn hai cột độc lập, cần mapping đa thuộc tính như `@Embeddable`.

**Câu 3.** Khi `@Converter(autoApply = false)`, làm gì để entity `Product` sử dụng converter?

**Trả lời:** Đặt `@Convert(converter = SkuConverter.class)` lên thuộc tính `Sku sku` hoặc khai báo mapping tương ứng bằng metadata hỗ trợ.

**Câu 4.** Có nên đặt `@Enumerated(EnumType.STRING)` đồng thời với `@Convert(converter = OrderStatusConverter.class)`?

**Trả lời:** Không. Hãy chọn mapping enum chuẩn hoặc converter mã nghiệp vụ, tránh phối hợp hai cơ chế trên cùng thuộc tính.

**Câu 5.** Tại sao dùng converter để mã hóa một cột có thể làm truy vấn bằng giá trị ban đầu khó khăn?

**Trả lời:** Database nhìn thấy giá trị đã mã hóa, không biết plaintext. Nếu mỗi lần mã hóa cho kết quả khác nhau, phép so sánh bằng trên ciphertext không tương ứng trực tiếp với so sánh bằng plaintext.

**Câu 6.** Vì sao đổi converter từ lưu `SP-001` thành `SKU:SP-001` có thể cần migration?

**Trả lời:** Vì dữ liệu cũ vẫn có biểu diễn trước đó. Converter mới, phiên bản ứng dụng cũ và query/ràng buộc DB phải được tính toán để đọc/ghi tương thích trong giai đoạn chuyển đổi.

**Câu 7.** `@Convert(disableConversion=true)` có làm một kiểu Java tùy ý như `Sku` tự động trở thành kiểu JDBC được Hibernate hỗ trợ không?

**Trả lời:** Không. Nếu không còn converter và cũng không có mapping cơ bản khác được hỗ trợ, provider có thể không ánh xạ được thuộc tính đó.

## 22. Sơ đồ quyết định khi chọn cách ánh xạ

~~~mermaid
flowchart TD
    A["Có một kiểu giá trị Java cần lưu?"] --> B{"Cần entity identity và vòng đời riêng?"}
    B -- "Có" --> E["Dùng @Entity và các quan hệ phù hợp"]
    B -- "Không" --> C{"Giá trị cần bao nhiêu cột độc lập?"}
    C -- "Nhiều cột" --> D["Xem xét @Embeddable"]
    C -- "Một cột" --> F{"Provider đã hỗ trợ basic mapping trực tiếp?"}
    F -- "Có" --> G["Có thể dùng mapping trực tiếp"]
    F -- "Chưa hoặc cần quy tắc riêng" --> H["Xem xét AttributeConverter<X,Y>"]
    H --> I{"Thuộc tính là ID, version, relationship hoặc mapping đặc biệt?"}
    I -- "Có" --> J["Không giả định converter portable; chọn mapping phù hợp"]
    I -- "Không" --> K["Dùng @Convert hoặc autoApply"]
    K --> L["Đồng bộ schema, query và quy tắc dữ liệu"]
~~~

**Nguyên tắc cốt lõi:** `AttributeConverter` là cầu nối giữa **một thuộc tính Java có ý nghĩa nghiệp vụ** và **một biểu diễn cột cơ bản được Hibernate/JDBC hỗ trợ**. Dùng nó để tăng tính rõ ràng của mô hình domain, nhưng giữ nguyên sự phân biệt với entity, quan hệ, định danh, ánh xạ nhiều cột và transaction. Hiểu các giới hạn ấy giúp chọn đúng giữa converter, `@Embeddable` và mapping riêng của Hibernate khi thiết kế kiểu dữ liệu.

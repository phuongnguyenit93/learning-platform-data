# Chuyển đổi giá trị bằng `AttributeConverter` trong JPA

## 1. Vấn đề: giá trị nghiệp vụ không phải lúc nào cũng trùng kiểu cột SQL

Trong ứng dụng Java dùng **Jakarta Persistence (JPA)**, nhiều thuộc tính có kiểu đơn giản như `String`, `Integer`, `BigDecimal` hoặc `LocalDate`. JPA provider có thể ánh xạ các kiểu này đến cột cơ sở dữ liệu mà không cần mã chuyển đổi thủ công.

Nhưng một mô hình nghiệp vụ tốt thường sử dụng **kiểu giá trị** (*value object*) thay vì rải rác các kiểu nguyên thủy:

- `EmailAddress` đại diện cho email hợp lệ, thay vì chuỗi `String` bất kỳ.
- `CountryCode` mang quy tắc về mã quốc gia, thay vì một `String` khó kiểm soát.
- `OrderStatus` sử dụng enum có mã lưu trữ ổn định, thay vì phụ thuộc vào vị trí enum.
- `Percentage` hoặc `Amount` áp dụng quy tắc miền giá trị, đơn vị và làm tròn riêng.

Ví dụ lớp `Customer` khai báo:

```java
private EmailAddress email;
```

Trong database, ta chỉ cần lưu:

```sql
email VARCHAR(254)
```

Câu hỏi kiến trúc là: **làm sao để JPA lưu `EmailAddress` vào một cột `VARCHAR` và khôi phục lại `EmailAddress` khi đọc?**

JPA cung cấp giao diện **`AttributeConverter<X, Y>`** cùng annotation **`@Converter`** và **`@Convert`** để mô tả phép chuyển đổi này.

Đây là giải pháp **ánh xạ một giá trị của thuộc tính entity sang một biểu diễn đơn cột**. Nó giúp entity giữ ngôn ngữ và bất biến của miền nghiệp vụ trong khi database tiếp tục dùng kiểu dữ liệu SQL thông thường.

## 2. `AttributeConverter<X, Y>` là gì?

Giao diện nằm trong gói `jakarta.persistence`:

```java
package jakarta.persistence;

public interface AttributeConverter<X, Y> {
    Y convertToDatabaseColumn(X attribute);

    X convertToEntityAttribute(Y dbData);
}
```

Hai tham số kiểu có ý nghĩa:

| Tham số | Ý nghĩa | Ví dụ |
|---|---|---|
| `X` | Kiểu của **thuộc tính trong entity** hoặc kiểu giá trị của miền nghiệp vụ. | `EmailAddress` |
| `Y` | Kiểu Java của **giá trị được đưa tới/đọc từ JDBC** để lưu trong cột database. | `String` |

Hai phương thức vận hành theo hướng đối xứng:

- `convertToDatabaseColumn(X attribute)`: chuyển **giá trị Java của entity → giá trị cơ sở dữ liệu**.
- `convertToEntityAttribute(Y dbData)`: chuyển **giá trị cơ sở dữ liệu → giá trị Java của entity**.

Sơ đồ:

```text
        Lớp nghiệp vụ và Entity
        Customer.email: EmailAddress
                    |
                    | convertToDatabaseColumn(...)
                    v
        Giá trị JDBC: String
                    |
              JPA provider
                    |
                    v
         Cột SQL: VARCHAR(254)

         Cột SQL: VARCHAR(254)
                    |
              JPA provider
                    |
                    v
         Giá trị JDBC: String
                    |
                    | convertToEntityAttribute(...)
                    v
        Customer.email: EmailAddress
```

**Phân biệt:** `Y` là **kiểu Java dùng để truyền dữ liệu với provider/JDBC**, không phải tên kiểu SQL. Khi `Y = String`, cột có thể là `VARCHAR`, `CHAR` hoặc kiểu văn bản phù hợp tùy metadata, provider và SQL dialect. Muốn điều khiển kích thước hoặc tên cột, vẫn có thể dùng `@Column`.

Một `AttributeConverter` thông thường **không phải entity**, **không cần `@Id`**, và không quản lý transaction. Nó chỉ cung cấp quy tắc chuyển đổi giá trị.

## 3. Ví dụ đầy đủ: lưu `EmailAddress` dưới dạng chuỗi

### 3.1. Định nghĩa kiểu giá trị bất biến

Đầu tiên tạo một lớp `EmailAddress` bao bọc chuỗi và bảo vệ quy tắc nghiệp vụ cơ bản:

```java
package com.example.customer;

import java.util.Objects;

public final class EmailAddress {
    private final String value;

    private EmailAddress(String value) {
        this.value = value;
    }

    public static EmailAddress of(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Email không được null");
        }

        String normalized = raw.trim();

        // Kiểm tra tối thiểu để minh họa value object.
        // Hệ thống thật có thể áp dụng validator chuyên biệt.
        int at = normalized.indexOf('@');
        if (at <= 0 || at == normalized.length() - 1) {
            throw new IllegalArgumentException("Email không hợp lệ");
        }
        if (normalized.length() > 254) {
            throw new IllegalArgumentException("Email quá dài");
        }

        return new EmailAddress(normalized);
    }

    public String value() {
        return value;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof EmailAddress email)) {
            return false;
        }
        return Objects.equals(value, email.value);
    }

    @Override
    public int hashCode() {
        return Objects.hash(value);
    }

    @Override
    public String toString() {
        return value;
    }
}
```

`EmailAddress` là **value object**, không phải entity. Nó không cần constructor không tham số, không cần `@Entity` và cũng không có khóa chính. `final` có thể phù hợp với value object, dù `final` không được dùng cho lớp **entity** theo yêu cầu portable JPA.

Phương thức `of` dùng để tạo giá trị hợp lệ và thực hiện phép chuẩn hóa được cho phép. Việc `trim()` ở đây chỉ là ví dụ; quy tắc thay đổi chữ hoa/thường của địa chỉ email cần được quyết định theo yêu cầu nghiệp vụ, không nên tự động giả định mọi email đều có thể chuyển toàn bộ sang chữ thường mà không đổi ý nghĩa.

### 3.2. Viết converter

```java
package com.example.customer;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class EmailAddressConverter
        implements AttributeConverter<EmailAddress, String> {

    @Override
    public String convertToDatabaseColumn(EmailAddress attribute) {
        return attribute == null ? null : attribute.value();
    }

    @Override
    public EmailAddress convertToEntityAttribute(String dbData) {
        return dbData == null ? null : EmailAddress.of(dbData);
    }
}
```

Ở đây:

- `@Converter` thông báo đây là lớp converter của JPA.
- `EmailAddress` là kiểu trong entity (`X`).
- `String` là kiểu JDBC/provider sẽ lưu (`Y`).
- Cả hai phương thức xử lý `null` tường minh.
- Khi đọc chuỗi từ database, `EmailAddress.of(dbData)` tái áp dụng quy tắc tạo value object; dữ liệu cũ không hợp lệ có thể làm quá trình đọc thất bại.

**Converter không tự chọn schema.** Nó mô tả phép biến đổi dữ liệu; `@Column` và các thiết lập provider/schema định nghĩa cột theo yêu cầu.

### 3.3. Áp dụng converter cho thuộc tính entity

```java
package com.example.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Convert(converter = EmailAddressConverter.class)
    @Column(name = "email", nullable = false, length = 254)
    private EmailAddress email;

    @Column(name = "display_name", nullable = false, length = 120)
    private String displayName;

    protected Customer() {
        // Constructor dành cho JPA.
    }

    public Customer(String displayName, EmailAddress email) {
        if (displayName == null || displayName.isBlank()) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        if (email == null) {
            throw new IllegalArgumentException("Email không được null");
        }

        this.displayName = displayName;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public EmailAddress getEmail() {
        return email;
    }

    public void changeEmail(EmailAddress newEmail) {
        if (newEmail == null) {
            throw new IllegalArgumentException("Email không được null");
        }
        this.email = newEmail;
    }

    public String getDisplayName() {
        return displayName;
    }
}
```

Entity dùng **field access** vì `@Id` được khai báo trên field. Vì vậy, `@Convert` và `@Column` cũng đặt trên field `email`.

Trong bảng `customers`, một cấu trúc SQL thường thấy là:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(254) NOT NULL,
    display_name VARCHAR(120) NOT NULL
);
```

DDL trên là **minh họa**. Tên kiểu ID, cú pháp tự tăng và kiểu chuỗi thực tế có thể khác giữa các hệ quản trị; giá trị `length = 254` cũng phụ thuộc quy tắc sinh schema của provider.

### 3.4. Khi lưu và đọc dữ liệu, điều gì xảy ra?

Giả sử project dùng persistence unit `RESOURCE_LOCAL`. Đoạn mã sau lưu entity:

```java
EntityManager em = emf.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();

    try {
        tx.begin();

        Customer customer = new Customer(
                "Lan",
                EmailAddress.of("lan@example.com")
        );

        em.persist(customer);
        tx.commit();
    } catch (RuntimeException ex) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw ex;
    }
} finally {
    em.close();
}
```

Khi JPA provider đồng bộ thay đổi, nó sử dụng converter để lấy chuỗi `"lan@example.com"` và bind chuỗi đó vào cột `email`.

Khi đọc một bản ghi qua `EntityManager` mới:

```java
EntityManager readEm = emf.createEntityManager();

try {
    Customer customer = readEm.find(Customer.class, customerId);

    if (customer != null) {
        EmailAddress email = customer.getEmail();
        System.out.println(email.value());
    }
} finally {
    readEm.close();
}
```

Provider đọc giá trị chuỗi từ database và gọi phép chuyển đổi tương ứng để tái tạo `EmailAddress`. Không cần thêm hàm đổi kiểu trong repository sau khi gọi `find()`.

**Không nên dựa vào số lần converter được gọi.** Provider có thể thực hiện chuyển đổi khi đọc/ghi, flush, lấy snapshot phục vụ dirty checking hoặc vì cơ chế nội bộ khác. Một lần gọi `find()` cũng có thể trả về entity đã nằm trong persistence context mà không cần truy vấn database; lúc đó không nhất thiết có phép chuyển đổi mới.

## 4. Cấu hình converter trong persistence unit

Để ví dụ tự chạy trong một project Java SE, cần có JPA API, một provider triển khai Jakarta Persistence và JDBC driver của database.

File `src/main/resources/META-INF/persistence.xml` có thể được khai báo:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit name="customerPU"
                      transaction-type="RESOURCE_LOCAL">
        <class>com.example.customer.Customer</class>
        <class>com.example.customer.EmailAddressConverter</class>

        <properties>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.h2.Driver"/>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:h2:mem:customers;DB_CLOSE_DELAY=-1"/>
            <property name="jakarta.persistence.jdbc.user"
                      value="sa"/>
            <property name="jakarta.persistence.jdbc.password"
                      value=""/>
            <property
                name="jakarta.persistence.schema-generation.database.action"
                value="drop-and-create"/>
        </properties>
    </persistence-unit>
</persistence>
```

Lớp converter có thể được tìm thấy bằng cơ chế khám phá metadata của provider/container, hoặc đăng ký tường minh như trên. Cách quét package và classpath còn phụ thuộc môi trường Jakarta EE, Spring hay Java SE. Việc có file `@Converter` trong source code không bảo đảm mọi provider tự tìm được nó nếu cấu hình persistence unit không bao gồm lớp.

`drop-and-create` **chỉ phù hợp cho thực hành**, bởi nó có thể xóa dữ liệu cũ. Với dữ liệu thật cần migration schema có kiểm soát.

Một ứng dụng khởi tạo JPA thuần Java SE có thể dùng:

```java
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.Persistence;

EntityManagerFactory emf =
        Persistence.createEntityManagerFactory("customerPU");

try {
    // Tạo EntityManager và thực hiện các đơn vị công việc.
} finally {
    emf.close();
}
```

Trong Jakarta EE hoặc Spring, container/framework thường đảm nhiệm bootstrap và vòng đời persistence unit. Converter vẫn dùng cùng giao diện `AttributeConverter`.

## 5. `@Convert` và `@Converter` khác nhau ở đâu?

Hai annotation dễ nhầm tên nhưng đảm nhiệm **hai vai trò khác nhau**.

| Annotation | Đặt ở đâu? | Vai trò |
|---|---|---|
| `@Converter` | Trên lớp hiện thực `AttributeConverter<X,Y>`. | Khai báo lớp là converter; có thể bật `autoApply`. |
| `@Convert` | Trên thuộc tính entity/embeddable, hoặc vị trí mapping được hỗ trợ. | Yêu cầu dùng converter cụ thể, hoặc điều chỉnh việc áp dụng converter tự động. |

Ví dụ:

```java
@Converter
public class EmailAddressConverter
        implements AttributeConverter<EmailAddress, String> {
    // ...
}
```

Và tại entity:

```java
@Convert(converter = EmailAddressConverter.class)
private EmailAddress email;
```

Cách trên là **áp dụng tường minh**. Mặc định `@Converter` không đặt `autoApply = true`, nên converter không tự áp dụng cho mọi thuộc tính có cùng kiểu `X`.

### 5.1. Áp dụng tường minh bằng `@Convert`

Nếu converter chỉ dùng cho một số cột, cách khai báo tường minh phù hợp:

```java
@Entity
public class Customer {
    @Id
    private Long id;

    @Convert(converter = EmailAddressConverter.class)
    private EmailAddress contactEmail;

    protected Customer() {}
}
```

Ưu điểm là có thể nhìn vào entity để biết thuộc tính đang sử dụng converter nào. Nếu một kiểu giá trị cần nhiều cách biểu diễn khác nhau ở các cột, mỗi trường hợp có thể dùng converter tương ứng, miễn không xung đột với loại mapping.

### 5.2. Áp dụng tự động bằng `autoApply = true`

Nếu **mọi thuộc tính thích hợp có kiểu `EmailAddress`** đều cần lưu dạng `String`, có thể sửa khai báo:

```java
@Converter(autoApply = true)
public class EmailAddressConverter
        implements AttributeConverter<EmailAddress, String> {
    // ...
}
```

Khi converter đã được phát hiện trong persistence unit, provider sẽ tự áp dụng nó cho các thuộc tính basic đủ điều kiện có kiểu `EmailAddress`, kể cả khi không ghi `@Convert` ở từng field:

```java
@Entity
public class Customer {
    @Id
    private Long id;

    @Column(name = "email", length = 254)
    private EmailAddress email; // Converter tự áp dụng.

    protected Customer() {}
}
```

Cần phân biệt:

- **`autoApply = false` hoặc không khai báo:** phải áp dụng converter tường minh khi cần.
- **`autoApply = true`:** converter được áp dụng tự động cho các mapping phù hợp của kiểu `X` trong phạm vi persistence unit.
- **`@Convert(converter = ...)` tường minh:** lựa chọn converter cho thuộc tính cụ thể theo quy tắc metadata của JPA.
- **`@Convert(disableConversion = true)`:** cho phép tắt conversion tự động tại vị trí mapping được hỗ trợ.

Với một kiểu miền nghiệp vụ **chỉ tồn tại nhờ converter** như `EmailAddress`, nếu tắt chuyển đổi mà không cung cấp một mapping khác, provider có thể không biết cách lưu thuộc tính đó. Vì vậy `disableConversion` thường chỉ hữu ích khi loại thuộc tính đó có cách ánh xạ cơ bản khác.

Ví dụ một converter tự động xử lý chuỗi (đưa tất cả chuỗi thành chữ hoa) nhưng cần loại trừ một cột:

```java
@Converter(autoApply = true)
public class UppercaseConverter
        implements AttributeConverter<String, String> {

    @Override
    public String convertToDatabaseColumn(String value) {
        return value == null ? null : value.toUpperCase(java.util.Locale.ROOT);
    }

    @Override
    public String convertToEntityAttribute(String value) {
        return value;
    }
}
```

```java
@Entity
public class Category {
    @Id
    private Long id;

    private String label; // UppercaseConverter được áp dụng.

    @Convert(disableConversion = true)
    private String externalCode; // Giữ nguyên mapping String thông thường.

    protected Category() {}
}
```

Đây là ví dụ kỹ thuật cho `disableConversion`; thực tế **không nên bật autoApply cho kiểu phổ biến như `String` mà thiếu chủ đích rõ ràng**, vì rất nhiều thuộc tính của toàn persistence unit sẽ chịu tác động.

### 5.3. Converter đặt ở field hay getter?

Quy tắc giống các annotation JPA khác:

- Với **field access**, đặt `@Convert` trên field.
- Với **property access**, đặt `@Convert` trên getter JavaBeans phù hợp.
- Khi dùng `@Access` để điều chỉnh truy cập, phải đặt annotation mapping tại vị trí phù hợp với access type đó.

Ví dụ property access:

```java
@Entity
@Access(AccessType.PROPERTY)
public class Customer {
    private Long id;
    private EmailAddress email;

    protected Customer() {}

    @Id
    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    @Convert(converter = EmailAddressConverter.class)
    @Column(name = "email")
    public EmailAddress getEmail() {
        return email;
    }

    public void setEmail(EmailAddress email) {
        this.email = email;
    }
}
```

Trộn lẫn field access/property access thiếu `@Access` có thể khiến provider không áp dụng converter tại nơi bạn nghĩ.

## 6. Ví dụ khác: enum có mã lưu trữ ổn định

Một nhu cầu thực tế là lưu enum bằng **mã nghiệp vụ ổn định**. Xét các trạng thái:

```java
public enum OrderStatus {
    NEW("N"),
    PAID("P"),
    CANCELLED("C");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        for (OrderStatus status : values()) {
            if (status.code.equals(code)) {
                return status;
            }
        }
        throw new IllegalArgumentException(
                "Mã trạng thái không được hỗ trợ: " + code
        );
    }
}
```

Viết converter:

```java
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

@Converter
public class OrderStatusConverter
        implements AttributeConverter<OrderStatus, String> {

    @Override
    public String convertToDatabaseColumn(OrderStatus attribute) {
        return attribute == null ? null : attribute.code();
    }

    @Override
    public OrderStatus convertToEntityAttribute(String dbData) {
        return dbData == null ? null : OrderStatus.fromCode(dbData);
    }
}
```

Dùng trong entity:

```java
@Entity
public class CustomerOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Convert(converter = OrderStatusConverter.class)
    @Column(name = "status_code", length = 1, nullable = false)
    private OrderStatus status;

    protected CustomerOrder() {}

    public CustomerOrder(OrderStatus status) {
        this.status = status;
    }
}
```

Khi lưu `OrderStatus.PAID`, cột `status_code` chứa `"P"`. Khi đọc `"C"`, JPA tạo lại `OrderStatus.CANCELLED`. Nếu database chứa mã lạ như `"X"`, phép chuyển đổi hiện tại ném exception để cho biết dữ liệu không phù hợp.

**Không thêm `@Enumerated` vào chính thuộc tính đang dùng `AttributeConverter`.** `@Enumerated(EnumType.STRING)` và `@Enumerated(EnumType.ORDINAL)` là cơ chế ánh xạ enum có sẵn, khác với cơ chế converter tùy chỉnh; theo quy tắc JPA, conversion không áp dụng cho thuộc tính được gắn `@Enumerated`.

### 6.1. Vì sao không luôn dùng `@Enumerated`?

| Cách lưu | Ví dụ giá trị SQL | Ưu điểm | Rủi ro/giới hạn |
|---|---|---|---|
| `@Enumerated(EnumType.ORDINAL)` | `0`, `1`, `2` | Đơn giản, gọn. | Đổi thứ tự enum có thể đổi ý nghĩa dữ liệu cũ. |
| `@Enumerated(EnumType.STRING)` | `"NEW"`, `"PAID"` | Dễ đọc, ít phụ thuộc thứ tự. | Đổi tên enum constant có thể ảnh hưởng dữ liệu. |
| `AttributeConverter` sang mã cố định | `"N"`, `"P"`, `"C"` | Kiểm soát chặt mã lưu trữ, độc lập thứ tự/tên enum. | Phải viết và bảo trì bảng ánh xạ hai chiều. |

Nếu yêu cầu database tương thích dài hạn với ứng dụng hoặc hệ thống ngoài, converter theo mã nghiệp vụ thường là lựa chọn hợp lý. Tuy nhiên, không cần converter khi `@Enumerated` đã đáp ứng yêu cầu.

## 7. Converter tham gia vòng đời persistence như thế nào?

Sơ đồ một đơn vị công việc với `Customer`:

```text
Ứng dụng                       JPA provider / database
    |                                      |
    | new Customer(..., EmailAddress)      |
    |                                      |
    | em.persist(customer)                 |
    |------------------------------------->|
    |                                      |
    |                        Khi cần ghi SQL:
    |                        convertToDatabaseColumn(email)
    |                                      |
    |                        JDBC bind String -> VARCHAR
    |                                      |
    | tx.commit() / flush                  |
    |------------------------------------->|
    |                                      |
    | em.find(Customer.class, id)          |
    |------------------------------------->|
    |                                      |
    |                        JDBC đọc String
    |                        convertToEntityAttribute(dbData)
    |                                      |
    |<--------- Customer(email: EmailAddress)
```

Trong giao dịch, converter **không có trách nhiệm** gọi `commit()` hoặc `rollback()`. Nó không tự phát SQL và cũng không quyết định flush lúc nào. Các công việc này thuộc `EntityManager`, provider và transaction manager.

Với **managed entity**, khi ứng dụng thay thuộc tính:

```java
Customer customer = em.find(Customer.class, id);
customer.changeEmail(EmailAddress.of("new@example.com"));
```

Provider có thể phát hiện thay đổi qua cơ chế dirty checking, rồi chuyển thuộc tính sang dạng cột khi cần ghi `UPDATE`. Không cần gọi converter bằng tay.

Sau khi entity trở thành **detached** (ví dụ entity manager đã đóng), sửa `Customer.email` không tự động cập nhật database. Converter chỉ giúp chuyển dữ liệu **khi một thao tác persistence phù hợp được thực hiện**, không thay thế vòng đời managed/detached hoặc transaction.

## 8. Query và tham số khi thuộc tính có converter

### 8.1. JPQL sử dụng kiểu Java của thuộc tính

Với entity `Customer`, thuộc tính `email` có kiểu `EmailAddress`. Một truy vấn JPQL có thể sử dụng tham số cùng kiểu:

```java
EmailAddress wanted =
        EmailAddress.of("lan@example.com");

Customer result = em.createQuery(
        "SELECT c FROM Customer c WHERE c.email = :email",
        Customer.class
    )
    .setParameter("email", wanted)
    .getResultStream()
    .findFirst()
    .orElse(null);
```

Trong trường hợp phép so sánh này được hỗ trợ trên mapping tương ứng, provider chuyển tham số `EmailAddress` sang biểu diễn database nhờ converter và so sánh cột `email` với giá trị chuỗi thích hợp.

Điểm cần nhớ: **JPQL thao tác trên thuộc tính entity và kiểu Java**, trong khi native SQL thao tác trên cột/giá trị database. Không viết `c.email.value` trong JPQL chỉ vì `EmailAddress` có phương thức `value()`; `value` không phải persistent attribute độc lập theo mapping converter đơn cột này.

### 8.2. Criteria API

Tiêu chí tìm `Customer` theo email cũng có thể được tạo với Criteria API:

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<Customer> query =
        cb.createQuery(Customer.class);

Root<Customer> root = query.from(Customer.class);
ParameterExpression<EmailAddress> emailParam =
        cb.parameter(EmailAddress.class, "email");

query.select(root).where(
        cb.equal(root.get("email"), emailParam)
);

List<Customer> matches = em.createQuery(query)
        .setParameter("email", EmailAddress.of("lan@example.com"))
        .getResultList();
```

Nếu muốn an toàn kiểu hơn, project có thể dùng JPA static metamodel thay cho `root.get("email")` dạng chuỗi.

### 8.3. Native SQL

Với native SQL, cột `email` lưu **chuỗi**, nên truy vấn SQL làm việc với biểu diễn đó:

```java
List<?> rows = em.createNativeQuery(
        "SELECT email FROM customers WHERE email = :email"
    )
    .setParameter("email", "lan@example.com")
    .getResultList();
```

Không giả định một scalar result của native SQL luôn được tự chuyển thành `EmailAddress`. Khi native query ánh xạ kết quả thành **entity** được quản lý và metadata mapping được áp dụng, provider sẽ xử lý thuộc tính theo entity mapping; còn khi chỉ yêu cầu một cột scalar, kết quả thường là kiểu JDBC/provider tương ứng.

### 8.4. Phép lọc và sắp xếp

Converter **không biến SQL thành hệ truy vấn hiểu toàn bộ API của value object**. Nếu cột chứa mã `"P"`, database sắp xếp và lọc theo giá trị cột đó, không tự theo thứ tự nghiệp vụ của `OrderStatus`.

Tương tự, nếu converter mã hóa hoặc đóng gói giá trị vào một chuỗi, các phép `ORDER BY`, `LIKE`, range comparison và index trên cột có thể mang ý nghĩa khác so với giá trị gốc. Chỉ chọn biểu diễn được sắp xếp/lọc tự nhiên khi nghiệp vụ thực sự cần những truy vấn đó.

## 9. Những thuộc tính nào không dùng converter tùy tiện?

`AttributeConverter` chủ yếu hướng tới **basic attribute** có thể biểu diễn bằng một giá trị cột. Theo các quy tắc Jakarta Persistence, conversion thông thường **không áp dụng** lên những mapping đặc biệt sau:

| Loại thuộc tính/mapping | Hướng xử lý phù hợp |
|---|---|
| `@Id` / `@EmbeddedId` (thuộc tính định danh) | Dùng kiểu khóa và mapping khóa chính mà JPA/provider hỗ trợ. Không dựa vào converter portable cho ID. |
| `@Version` | Dùng kiểu được JPA hỗ trợ cho optimistic locking; không dựa vào converter để quản lý version. |
| Quan hệ `@ManyToOne`, `@OneToOne`, `@OneToMany`, `@ManyToMany` | Ánh xạ quan hệ bằng annotation association và khóa ngoại/join table. |
| Thuộc tính có `@Enumerated` | Dùng cơ chế enum mapping đó, hoặc bỏ `@Enumerated` và dùng converter. |
| Thuộc tính có `@Temporal` | Dùng temporal mapping phù hợp; không kết hợp converter như một yêu cầu portable. |

Đặc tả có các quy tắc chi tiết cho converter ở **embeddable** và **element collection**. Khi cần áp dụng converter cho một thuộc tính nằm trong embeddable hoặc thành phần collection, `@Convert` hỗ trợ xác định thuộc tính đích qua `attributeName` tại các vị trí mapping được cho phép. Cần xác định chính xác field/property theo access type và mapping collection tương ứng.

Ví dụ một embeddable chứa địa chỉ email:

```java
@Embeddable
public class ContactInfo {
    private EmailAddress alternateEmail;

    protected ContactInfo() {}

    public ContactInfo(EmailAddress alternateEmail) {
        this.alternateEmail = alternateEmail;
    }
}
```

Entity có thể chỉ định converter cho thuộc tính bên trong embeddable:

```java
@Entity
public class Customer {
    @Id
    private Long id;

    @Embedded
    @Convert(
        attributeName = "alternateEmail",
        converter = EmailAddressConverter.class
    )
    private ContactInfo contactInfo;

    protected Customer() {}
}
```

Đây là tình huống mà `attributeName` định vị thuộc tính cần conversion bên trong giá trị nhúng. Nếu `EmailAddressConverter` dùng `autoApply = true` và đã được đăng ký, conversion có thể được áp dụng tự động cho các basic attribute phù hợp bên trong embeddable; không nhất thiết phải khai báo lại tại mỗi nơi.

## 10. Những việc `AttributeConverter` làm được và không làm được

### 10.1. Làm được

Một converter thích hợp cho **chuyển đổi có quy tắc rõ ràng giữa một kiểu miền nghiệp vụ và một giá trị cột**, chẳng hạn:

- `EmailAddress ↔ String`.
- `CountryCode ↔ String`.
- `OrderStatus ↔ String` dùng mã ổn định.
- `Percentage ↔ BigDecimal` khi đơn vị và scale đã được thống nhất.
- Một kiểu mã định danh nghiệp vụ không phải khóa chính của entity, ánh xạ sang `String` hoặc `Long`.
- Một đối tượng giá trị nhỏ sang chuỗi biểu diễn chuẩn, khi application thực sự chỉ cần một cột và có chiến lược migration rõ.

Ví dụ kiểu `Percentage` muốn cột `DECIMAL(7,6)` lưu tỷ lệ từ `0` đến `1`:

```java
public final class Percentage {
    private final BigDecimal ratio;

    private Percentage(BigDecimal ratio) {
        this.ratio = ratio;
    }

    public static Percentage ofRatio(BigDecimal ratio) {
        if (ratio == null
                || ratio.compareTo(BigDecimal.ZERO) < 0
                || ratio.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException(
                    "Tỷ lệ phải nằm trong khoảng [0, 1]"
            );
        }
        return new Percentage(ratio);
    }

    public BigDecimal ratio() {
        return ratio;
    }
}
```

Converter:

```java
@Converter
public class PercentageConverter
        implements AttributeConverter<Percentage, BigDecimal> {

    @Override
    public BigDecimal convertToDatabaseColumn(Percentage value) {
        return value == null ? null : value.ratio();
    }

    @Override
    public Percentage convertToEntityAttribute(BigDecimal data) {
        return data == null ? null : Percentage.ofRatio(data);
    }
}
```

Entity:

```java
@Convert(converter = PercentageConverter.class)
@Column(name = "discount_rate", precision = 7, scale = 6)
private Percentage discountRate;
```

Ở đây converter chỉ thay đổi **kiểu Java bề mặt**; việc kiểm soát phạm vi và scale của cột thuộc metadata `@Column` và các ràng buộc/validation khác. Nếu giá trị `Percentage` có scale dài hơn yêu cầu, cần quyết định chuẩn hóa hoặc từ chối input trước khi lưu.

### 10.2. Không thay thế quan hệ entity

Giả sử `Customer` có nhiều `Order`. Đây là quan hệ một-nhiều có khóa ngoại và vòng đời riêng. Không dùng converter để “nhét” cả tập `Order` vào một chuỗi chỉ nhằm bỏ qua `@OneToMany`:

```java
@OneToMany(mappedBy = "customer")
private List<Order> orders;
```

Mapping quan hệ JPA hỗ trợ quản lý định danh, join, lazy/eager fetching, cascade và truy vấn quan hệ. Converter đơn cột không mang các khả năng đó.

### 10.3. Không thay thế `@Embeddable` khi cần nhiều cột

Địa chỉ có `street`, `city` và `postalCode` thường nên được ánh xạ thành **nhiều cột**:

```java
@Embeddable
public class PostalAddress {
    private String street;
    private String city;
    private String postalCode;

    protected PostalAddress() {}
}
```

```java
@Embedded
private PostalAddress address;
```

Với cách này, `street`, `city` và `postalCode` có thể được lọc hoặc đánh index độc lập. Nếu dùng converter biến cả địa chỉ thành một chuỗi đơn cột, database sẽ khó truy vấn và kiểm soát từng thành phần hơn.

### 10.4. Không tự trở thành bộ mã hóa an toàn

Converter có thể gọi một thư viện mã hóa, nhưng **chỉ có `AttributeConverter` không đủ để thiết kế hệ thống bảo mật dữ liệu**. Mã hóa còn liên quan đến quản lý khóa, lưu trữ IV/nonce, xác thực dữ liệu, rotation, truy vấn và rò rỉ thông tin qua mẫu mã hóa.

Với mã hóa ngẫu nhiên, cùng một plaintext có thể cho nhiều ciphertext khác nhau, khiến phép so sánh equality ở SQL không hoạt động như dữ liệu gốc. Với mã hóa tất định, có thể xuất hiện rủi ro lộ mẫu lặp. Nếu cần mã hóa dữ liệu nhạy cảm, dùng thiết kế bảo mật chuyên biệt thay vì coi converter là giải pháp trọn gói.

### 10.5. Không thay thế migration schema hoặc dữ liệu

Giả sử trước đây cột `status` lưu `"PAID"`, còn converter mới đọc mã một ký tự `"P"`. Chỉ thay `@Convert` **không tự chuyển** các bản ghi cũ từ `"PAID"` sang `"P"`.

Cần migration dữ liệu hoặc một converter hỗ trợ tạm thời cả định dạng cũ và mới theo kế hoạch phát hành. Nếu không, `convertToEntityAttribute("PAID")` có thể ném exception ngay khi đọc bản ghi cũ.

## 11. Thiết kế converter đáng tin cậy

### 11.1. Xử lý `null` tường minh

Cả hai phương thức nên định nghĩa cách ứng xử với `null`:

```java
@Override
public String convertToDatabaseColumn(EmailAddress value) {
    return value == null ? null : value.value();
}

@Override
public EmailAddress convertToEntityAttribute(String dbData) {
    return dbData == null ? null : EmailAddress.of(dbData);
}
```

Provider có thể xử lý null theo các tình huống riêng, nên không nên viết converter dựa trên giả định rằng một phương thức **không bao giờ** nhận null. Quy tắc null còn phụ thuộc ý nghĩa thuộc tính và `@Column(nullable = ...)`.

Không nên biến null thành chuỗi `"null"` hoặc chuỗi rỗng trừ khi đó là **quy tắc dữ liệu đã được thiết kế rõ**; việc này khiến dữ liệu thực và giá trị vắng mặt khó phân biệt.

### 11.2. Bảo toàn giá trị và khả năng đọc lại

Với phép chuyển đổi dự định không mất dữ liệu, nên đảm bảo rằng:

```text
convertToEntityAttribute(
    convertToDatabaseColumn(x)
)
    ≈ x
```

Ký hiệu `≈` nghĩa là **tương đương theo ngữ nghĩa nghiệp vụ**, không nhất thiết luôn là cùng một reference trong bộ nhớ hoặc bằng nhau từng byte.

Ví dụ:

- `EmailAddress(" lan@example.com ")` được chuẩn hóa về `"lan@example.com"` trước khi tạo value object, nên kết quả đọc lại vẫn đại diện cho cùng địa chỉ đã chuẩn hóa.
- Mã `OrderStatus.PAID` phải chuyển thành `"P"` và đọc `"P"` trở lại đúng `OrderStatus.PAID`.
- Nếu converter dùng phép chia hoặc làm tròn, mất độ chính xác có thể xảy ra; phải ghi rõ quy tắc và quyết định liệu điều đó có chấp nhận được hay không.

### 11.3. Không đặt logic thay đổi toàn hệ thống vào converter

Converter nên xử lý **chuyển đổi cục bộ của giá trị**. Nó không nên:

- Mở/đóng transaction hoặc gọi `EntityManager.persist()` từ trong converter.
- Gọi HTTP API hay truy vấn database cho mỗi thuộc tính khi đọc hàng nghìn hàng.
- Phụ thuộc vào trạng thái request, người dùng đang đăng nhập hoặc biến mutable dùng chung.
- Lén thay đổi các entity khác hoặc phát sự kiện nghiệp vụ.

Provider có quyền gọi converter nhiều lần; một converter có tác dụng phụ hoặc phụ thuộc trạng thái bên ngoài rất dễ tạo lỗi khó tái hiện. Cách viết **stateless, deterministic, không tác dụng phụ** thường ổn định và dễ hiểu nhất.

### 11.4. Cân nhắc thread safety

Đối tượng converter có thể được provider tạo, quản lý và sử dụng theo vòng đời do provider/container quyết định. Không nên giả định một instance converter chỉ được một thread sử dụng tại một thời điểm.

Converter thuần, chỉ sử dụng biến cục bộ và value object bất biến, sẽ dễ an toàn khi nhiều thread cùng truy cập. Tránh giữ `SimpleDateFormat` mutable hoặc bộ đệm trạng thái sửa chung bên trong converter; với chuyển đổi ngày giờ, ưu tiên API `java.time` khi phù hợp.

### 11.5. Giữ lỗi dữ liệu có ý nghĩa

Khi database chứa mã lạ `"X"`, converter enum có thể ném `IllegalArgumentException`:

```java
@Override
public OrderStatus convertToEntityAttribute(String dbData) {
    if (dbData == null) {
        return null;
    }
    return OrderStatus.fromCode(dbData);
}
```

Provider có thể bọc exception này trong một exception persistence khác. Điều quan trọng là không **âm thầm đổi mã lạ thành một trạng thái hợp lệ** nếu không có quy định nghiệp vụ; làm vậy có thể che giấu dữ liệu sai.

Khi có nhiều phiên bản ứng dụng cùng đọc dữ liệu, cần thiết kế chiến lược tương thích định dạng một cách chủ động, thay vì sửa converter để tùy tiện bỏ qua mã không nhận biết.

## 12. Phân biệt converter với các cơ chế khác

| Cơ chế | Mục đích chính | Khi nào nên dùng |
|---|---|---|
| `AttributeConverter<X,Y>` | Chuyển một kiểu giá trị ứng dụng sang kiểu Java tương ứng để lưu trong một cột. | Value object nhỏ, enum có mã riêng, chuẩn hóa biểu diễn dữ liệu. |
| `@Enumerated` | Ánh xạ enum bằng tên hoặc thứ tự theo chiến lược JPA. | Enum không cần mã tùy chỉnh. |
| `@Embeddable` + `@Embedded` | Ánh xạ một nhóm thuộc tính thành nhiều cột thuộc entity sở hữu. | Địa chỉ, khoảng tiền gồm nhiều thành phần, nhóm giá trị truy vấn độc lập. |
| `@ManyToOne` / `@OneToMany` | Ánh xạ quan hệ giữa các entity có danh tính riêng. | Mô hình quan hệ nghiệp vụ và khóa ngoại. |
| `@Column` | Cấu hình tên, độ dài, nullable, precision/scale và metadata cột. | Điều chỉnh schema của cột, kể cả cột do converter cung cấp dữ liệu. |
| Jakarta Bean Validation | Kiểm tra invariant như `@NotNull`, `@Size`, `@Pattern` hoặc constraint riêng. | Phát hiện dữ liệu đầu vào/trạng thái không hợp lệ. |
| Entity lifecycle callback (`@PrePersist`, `@PostLoad`, ...) | Chạy logic vòng đời entity tại các sự kiện JPA. | Xử lý gắn với vòng đời entity; không thay thế mapping kiểu giá trị. |
| Provider-specific custom type | Tùy biến mapping hoặc JDBC type ở mức riêng của provider. | Trường hợp cần kiểu SQL đặc thù mà `AttributeConverter` chuẩn không biểu diễn đủ. |

Ví dụ một giá trị gồm **số tiền và mã tiền tệ** thường nên được ánh xạ thành hai cột bằng `@Embeddable` khi cần truy vấn độc lập cả hai. Nếu mã hóa cả hai vào một `VARCHAR` bằng converter, đây là quyết định lưu trữ cụ thể với trade-off về truy vấn, constraint và migration.

## 13. Lỗi thường gặp khi dùng `AttributeConverter`

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Provider báo không biết ánh xạ `EmailAddress` | Converter chưa được phát hiện, chưa áp dụng tường minh hoặc `autoApply` chưa bật. | Đăng ký converter trong persistence unit, kiểm tra scanning và `@Convert`. |
| Dữ liệu được ghi nhưng không đọc lại được | `convertToEntityAttribute` không nhận mọi định dạng đang có trong cột. | Kiểm tra dữ liệu cũ, quy tắc parse và kế hoạch migration. |
| Converter không được gọi với enum | Thuộc tính đã dùng `@Enumerated` hoặc mapping khác loại trừ converter. | Chọn một cơ chế mapping; bỏ `@Enumerated` nếu dùng converter tùy chỉnh. |
| Query so sánh không cho kết quả mong đợi | Tham số khác kiểu ứng dụng hoặc converter lưu một biểu diễn không phù hợp với phép so sánh. | Bind tham số đúng kiểu `X` trong JPQL/Criteria, kiểm tra biểu diễn SQL. |
| Converter áp dụng lên quá nhiều cột | Bật `autoApply = true` cho `String` hoặc kiểu dùng rộng. | Chuyển sang `@Convert` tường minh hoặc tắt conversion ở trường hợp phù hợp. |
| SQL báo cột quá ngắn | Converter trả về chuỗi dài hơn độ dài cột được khai báo. | Điều chỉnh `@Column(length=...)` và schema migration; validate kích thước. |
| Gọi một lần `find` nhưng converter không chạy | Entity có thể đã nằm trong first-level cache của persistence context. | Không giả định số lần converter chạy bằng số lần gọi API. |
| Đổi converter rồi dữ liệu cũ bị lỗi | Định dạng lưu trữ thay đổi nhưng không migration. | Đảm bảo hỗ trợ dữ liệu cũ và thực hiện chuyển đổi dữ liệu có kế hoạch. |
| `@Convert` trên getter không có tác dụng | Entity đang dùng field access. | Đặt annotation theo access type hoặc dùng `@Access` đúng cách. |
| Dùng converter cho quan hệ hoặc khóa định danh | Vượt phạm vi áp dụng portable của converter. | Sử dụng association/ID mapping chuẩn tương ứng. |
| Cùng giá trị vào converter nhưng kết quả thay đổi theo thời điểm | Converter phụ thuộc trạng thái ngoài hoặc có tác dụng phụ. | Thiết kế conversion thuần, xác định quy tắc và dữ liệu phụ thuộc. |
| Native SQL lấy chuỗi thay vì value object | Scalar native query trả kiểu database/JDBC. | Ánh xạ kết quả thành entity hoặc chuyển đổi chủ động tại biên dữ liệu. |

## 14. Tình huống áp dụng: thay đổi trạng thái đơn hàng theo mã nghiệp vụ

Giả sử database đang lưu `order_status` kiểu `VARCHAR(1)`. Quy ước:

| Mã lưu trong database | Trạng thái Java | Ý nghĩa |
|---|---|---|
| `N` | `OrderStatus.NEW` | Đơn mới được tạo. |
| `P` | `OrderStatus.PAID` | Đã thanh toán. |
| `C` | `OrderStatus.CANCELLED` | Đã hủy. |

Một entity sử dụng converter:

```java
@Entity
@Table(name = "customer_orders")
public class CustomerOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Convert(converter = OrderStatusConverter.class)
    @Column(name = "order_status", nullable = false, length = 1)
    private OrderStatus status;

    public CustomerOrder() {
        this.status = OrderStatus.NEW;
    }

    public void markPaid() {
        if (status != OrderStatus.NEW) {
            throw new IllegalStateException(
                    "Chỉ đơn mới mới được chuyển sang đã thanh toán");
        }
        this.status = OrderStatus.PAID;
    }

    public OrderStatus getStatus() {
        return status;
    }
}
```

Khi thao tác bên trong transaction:

```java
CustomerOrder order = em.find(CustomerOrder.class, orderId);
order.markPaid();
// Provider chuyển OrderStatus.PAID thành "P" lúc đồng bộ thay đổi.
```

Logic `markPaid()` giữ **quy tắc chuyển trạng thái** ở entity/domain; converter chỉ biết chuyển enum sang mã SQL. Nếu muốn cấm trạng thái khác ngoài ba mã trong database, có thể bổ sung `CHECK (order_status IN ('N', 'P', 'C'))` trong migration schema phù hợp. Converter không thay thế constraint đó.

Nếu hệ thống thêm `OrderStatus.REFUNDED("R")`, thay đổi cần được cân nhắc ở cả Java, converter, quy tắc nghiệp vụ, database constraint và các phiên bản ứng dụng đang hoạt động. Đó là lý do nên coi biểu diễn converter là một phần của **hợp đồng dữ liệu lưu trữ lâu dài**.

## 15. Câu hỏi tự luyện

**1. `AttributeConverter<EmailAddress, String>` có nghĩa gì?**  
`EmailAddress` là kiểu thuộc tính trong Java entity, `String` là biểu diễn Java dùng để ghi/đọc giá trị cột qua provider/JDBC.

**2. Khi nào phải dùng `@Convert`, khi nào có thể chỉ dùng `@Converter(autoApply = true)`?**  
Dùng `@Convert` để chỉ định converter cho thuộc tính cụ thể. Khi converter auto-apply được đăng ký, provider có thể tự áp dụng nó cho những basic attribute có kiểu phù hợp trong persistence unit.

**3. Đặt `@Convert` trên một thuộc tính `@ManyToOne` có phải cách đổi khóa ngoại sang chuỗi không?**  
Không. Quan hệ entity được ánh xạ bằng association mapping. Converter không thay thế ánh xạ khóa ngoại hoặc vòng đời entity đích.

**4. Vì sao converter enum theo mã `"N"`, `"P"`, `"C"` có thể tốt hơn `EnumType.ORDINAL`?**  
Mã có thể giữ ổn định khi thay đổi thứ tự khai báo enum. Converter yêu cầu duy trì ánh xạ hai chiều đúng và quản lý migration khi đổi mã.

**5. Một thuộc tính `EmailAddress` có converter sang `String` thì JPQL nên bind loại tham số nào?**  
Thông thường là `EmailAddress`, tức kiểu thuộc tính entity. Provider chuyển tham số sang biểu diễn database phù hợp khi thực thi truy vấn.

**6. Có thể dùng converter để lưu một đối tượng `PostalAddress` có ba phần vào ba cột không?**  
Một `AttributeConverter<X,Y>` thông thường mô tả chuyển sang **một giá trị cột**. Nếu muốn ba cột riêng cho `street`, `city` và `postalCode`, nên dùng `@Embeddable`.

**7. `convertToDatabaseColumn` có cần gọi `em.flush()` không?**  
Không. Converter không quản lý persistence context hay transaction. Provider gọi converter trong quá trình xử lý mapping và chịu trách nhiệm thực thi SQL.

**8. Sau khi đổi cách mã hóa `"PAID"` thành `"P"`, thêm converter là đủ chưa?**  
Chưa. Cần kiểm tra/migrate dữ liệu cũ và bảo đảm các phiên bản ứng dụng còn hoạt động có thể đọc biểu diễn hiện có.

## 16. Ghi nhớ cách sử dụng

`AttributeConverter` là **cầu nối giữa kiểu giá trị Java và cách lưu một cột SQL**. Một converter hoàn chỉnh thường có:

1. **Kiểu giá trị của domain**: thể hiện ý nghĩa và invariant, ví dụ `EmailAddress`.
2. **Lớp converter `@Converter`**: hiện thực hai hướng `convertToDatabaseColumn` và `convertToEntityAttribute`.
3. **Mapping sử dụng converter**: `@Convert(converter = ...)` hoặc `@Converter(autoApply = true)` khi phạm vi tự động thực sự phù hợp.
4. **Metadata cột**: `@Column` để cấu hình tên, chiều dài, nullable hoặc precision/scale của giá trị được lưu.
5. **Kế hoạch duy trì dữ liệu**: null, dữ liệu cũ, mã không hợp lệ, query semantics và migration khi thay đổi cách biểu diễn.

Một converter tốt là converter **nhỏ, nhất quán, gần như thuần hàm và dễ đọc hai chiều**. Nhờ đó entity sử dụng được các value object có ý nghĩa nghiệp vụ, trong khi JPA provider vẫn lưu trữ chúng bằng các kiểu dữ liệu quan hệ thông dụng.

### Tài liệu tham khảo

- [Jakarta Persistence — trang đặc tả](https://jakarta.ee/specifications/persistence/)
- [Jakarta Persistence API — `AttributeConverter`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/attributeconverter)
- [Jakarta Persistence API — `@Converter`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/converter)
- [Jakarta Persistence API — `@Convert`](https://jakarta.ee/specifications/persistence/3.1/apidocs/jakarta.persistence/jakarta/persistence/convert)

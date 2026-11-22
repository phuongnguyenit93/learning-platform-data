# Áp dụng autoApply và giới hạn của AttributeConverter

JPA AttributeConverter cho phép chuyển một kiểu dữ liệu trong mô hình Java thành một kiểu cơ bản mà database lưu được, rồi chuyển ngược lại khi đọc dữ liệu. Khi khai báo **@Converter(autoApply = true)**, provider tự áp dụng converter cho các thuộc tính phù hợp trong persistence unit. Cơ chế này giảm việc lặp lại **@Convert** trên nhiều entity, nhưng chỉ nên dùng khi cùng một kiểu Java luôn có cùng quy tắc lưu trữ.

Bài này tập trung vào cách autoApply hoạt động, cách ghi đè hoặc tắt conversion ở từng thuộc tính, những loại thuộc tính không được converter hỗ trợ và các giới hạn cần nhớ khi thiết kế converter.

## 1. AttributeConverter giải quyết vấn đề gì?

Giả sử mô hình Java sử dụng một value object EmailAddress thay vì lưu email dưới dạng String ở mọi nơi. Database vẫn có thể lưu giá trị đó trong một cột VARCHAR. AttributeConverter làm cầu nối giữa kiểu miền nghiệp vụ và kiểu database:

```text
Entity attribute: EmailAddress
          |
          | convertToDatabaseColumn(...)
          v
Database value: String / VARCHAR
          |
          | convertToEntityAttribute(...)
          v
Entity attribute: EmailAddress
```

JPA định nghĩa interface tổng quát:

```java
public interface AttributeConverter<X, Y> {
    Y convertToDatabaseColumn(X attribute);

    X convertToEntityAttribute(Y dbData);
}
```

Trong đó:

- **X** là kiểu Java của thuộc tính entity.
- **Y** là kiểu Java biểu diễn dữ liệu database mà provider có thể ánh xạ tới một kiểu JDBC/database cơ bản.
- convertToDatabaseColumn chuyển giá trị từ entity sang giá trị lưu.
- convertToEntityAttribute chuyển giá trị đọc từ database thành giá trị trong entity.

Converter không phải serializer JSON tổng quát và cũng không thay thế quan hệ entity. Nó phù hợp với một giá trị cơ bản hoặc value object có thể biểu diễn bằng một kiểu database cơ bản, ví dụ EmailAddress thành VARCHAR, Money thành DECIMAL trong trường hợp chỉ có một loại tiền tệ, hoặc một mã nghiệp vụ thành CHAR/VARCHAR.

## 2. Tạo converter và áp dụng thủ công

Ví dụ tạo value object EmailAddress:

```java
public record EmailAddress(String value) {

    public EmailAddress {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Email address must not be blank"
            );
        }

        value = value.trim();
    }
}
```

Value object kiểm soát tính hợp lệ của dữ liệu ở tầng Java. Converter chịu trách nhiệm biểu diễn nó trong database:

```java
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
        return dbData == null ? null : new EmailAddress(dbData);
    }
}
```

Entity có thể áp dụng converter tường minh:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Convert(converter = EmailAddressConverter.class)
    @Column(name = "email", nullable = false, length = 254)
    private EmailAddress email;

    protected Customer() {
    }
}
```

Khi ghi entity, provider gọi convertToDatabaseColumn và lưu String vào cột email. Khi đọc entity, provider lấy String từ database rồi gọi convertToEntityAttribute để tạo EmailAddress.

Converter xử lý cả hai chiều. Nếu chỉ chuyển đúng khi ghi mà không thể khôi phục đúng giá trị khi đọc, mapping sẽ không đáp ứng yêu cầu của entity.

### 2.1. Xử lý null

Ví dụ trên trả về null khi đầu vào null. Đây là cách triển khai thường dùng để giữ ngữ nghĩa NULL của database.

Cần phân biệt:

- Giá trị Java null thường được chuyển thành SQL NULL.
- Chuỗi rỗng "" không giống NULL.
- Chuỗi chỉ có khoảng trắng có thể bị value object từ chối.
- Nếu cột database chứa dữ liệu cũ không hợp lệ, convertToEntityAttribute có thể phát sinh exception khi đọc.

Không nên âm thầm đổi dữ liệu sai thành một giá trị mặc định vì điều đó có thể che giấu lỗi dữ liệu. Nếu có dữ liệu legacy, hãy xác định quy tắc migration hoặc xử lý tương thích rõ ràng.

## 3. autoApply = true hoạt động thế nào?

Annotation Converter có thuộc tính autoApply. Mặc định là false:

```java
@Converter
public class EmailAddressConverter
        implements AttributeConverter<EmailAddress, String> {
    // ...
}
```

Với mặc định này, converter chỉ được áp dụng khi mapping chỉ định qua @Convert hoặc cơ chế cấu hình tương ứng. Nếu muốn provider tự áp dụng cho các thuộc tính có kiểu EmailAddress, khai báo:

```java
@Converter(autoApply = true)
public class EmailAddressConverter
        implements AttributeConverter<EmailAddress, String> {
    // ...
}
```

Khi autoApply = true, converter được áp dụng cho các thuộc tính persistent phù hợp với kiểu X trong persistence unit, trừ những trường hợp bị loại trừ theo quy tắc JPA hoặc được ghi đè/tắt conversion tại thuộc tính.

Ví dụ:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    @Column(name = "primary_email", length = 254)
    private EmailAddress primaryEmail;

    @Column(name = "backup_email", length = 254)
    private EmailAddress backupEmail;
}
```

Cả primaryEmail và backupEmail đều có kiểu EmailAddress nên converter autoApply được áp dụng mà không cần viết @Convert ở từng field.

Điều này đặc biệt hữu ích khi cùng một value object xuất hiện ở nhiều entity:

```java
@Entity
@Table(name = "suppliers")
public class Supplier {

    @Id
    private Long id;

    @Column(name = "contact_email", length = 254)
    private EmailAddress contactEmail;
}
```

Supplier.contactEmail cũng được chuyển đổi tự động vì thuộc tính có kiểu EmailAddress và converter được auto apply trong persistence unit.

**Phạm vi là persistence unit**, không phải toàn bộ ứng dụng Java bất kể cấu hình. Nếu ứng dụng có nhiều EntityManagerFactory/persistence unit, hãy kiểm tra converter được phát hiện và áp dụng trong từng persistence unit theo cấu hình provider. Không nên giả định một converter tự động được chia sẻ cho mọi EMF trong ứng dụng.

## 4. autoApply áp dụng cho kiểu nào?

Converter khai báo kiểu nguồn X trong AttributeConverter<X, Y>. autoApply nhắm đến các thuộc tính có kiểu Java tương ứng với X. Ví dụ:

```java
AttributeConverter<EmailAddress, String>
```

thì converter này dành cho thuộc tính EmailAddress, không phải mọi String trong entity.

Điều này giúp tránh việc vô tình biến đổi tất cả cột String. Nếu converter được khai báo cho một kiểu quá rộng, ví dụ String, autoApply có thể ảnh hưởng đến nhiều thuộc tính không cùng ý nghĩa nghiệp vụ. Hãy tạo value object riêng cho dữ liệu cần chuyển đổi thay vì áp dụng converter toàn cục lên kiểu nền tảng rộng.

Converter có thể áp dụng cho thuộc tính cơ bản được khai báo trong entity, mapped superclass, embeddable và các phần tử cơ bản trong collection theo quy tắc mapping của JPA. Converter xử lý từng giá trị phù hợp; nó không biến một object graph hoặc collection tùy ý thành một quan hệ database.

## 5. Ghi đè autoApply bằng @Convert

Có trường hợp phần lớn thuộc tính EmailAddress dùng converter mặc định, nhưng một field phải dùng cách biểu diễn khác để tương thích với schema legacy. Khi đó, có thể chỉ định converter cụ thể ở thuộc tính:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    private EmailAddress primaryEmail;

    @Convert(converter = LegacyEmailAddressConverter.class)
    @Column(name = "legacy_email")
    private EmailAddress legacyEmail;
}
```

Trong ví dụ:

- primaryEmail dùng EmailAddressConverter do autoApply.
- legacyEmail dùng LegacyEmailAddressConverter được chỉ định rõ.
- Converter chỉ định tại thuộc tính có độ ưu tiên để xác định cách chuyển đổi cho chính thuộc tính đó.

Converter thay thế cần được khai báo như converter JPA hợp lệ:

```java
@Converter
public class LegacyEmailAddressConverter
        implements AttributeConverter<EmailAddress, String> {

    @Override
    public String convertToDatabaseColumn(EmailAddress attribute) {
        if (attribute == null) {
            return null;
        }
        return "legacy:" + attribute.value();
    }

    @Override
    public EmailAddress convertToEntityAttribute(String dbData) {
        if (dbData == null) {
            return null;
        }

        String prefix = "legacy:";
        if (!dbData.startsWith(prefix)) {
            throw new IllegalArgumentException(
                "Unexpected legacy email representation"
            );
        }

        return new EmailAddress(dbData.substring(prefix.length()));
    }
}
```

Đây là ví dụ minh họa một định dạng lưu trữ cũ. Trong dự án thực tế, chỉ dùng quy tắc prefix nếu schema và dữ liệu legacy thực sự yêu cầu. Khi đổi định dạng lưu trữ, cần migration hoặc chiến lược đọc tương thích để không làm hỏng dữ liệu hiện hữu.

Không nên tạo nhiều converter autoApply = true cho cùng một kiểu X trong cùng persistence unit. Nếu một kiểu có nhiều cách biểu diễn, hãy chọn một converter mặc định và dùng @Convert để chỉ rõ ngoại lệ. Điều này giúp mapping dễ hiểu và tránh cấu hình converter mơ hồ.

## 6. Tắt auto conversion tại một thuộc tính

JPA có thể tắt converter tự động cho một thuộc tính bằng:

```java
@Convert(disableConversion = true)
private SomeBasicType value;
```

Thuộc tính disableConversion có ý nghĩa là không áp dụng converter tự động cho field đó. Cần chú ý: sau khi tắt converter, kiểu thuộc tính vẫn phải được JPA/provider hỗ trợ mapping theo một cách hợp lệ.

Ví dụ, nếu thuộc tính có kiểu String thì provider đã biết cách ánh xạ String sang VARCHAR nên có thể không cần converter. Nhưng nếu thuộc tính có kiểu EmailAddress tùy chỉnh và không còn converter nào áp dụng, provider thường không biết cách lưu kiểu đó. Khi ấy việc tắt conversion có thể làm EntityManagerFactory khởi tạo thất bại hoặc mapping không hợp lệ.

Không dùng disableConversion như một cách "bỏ qua lỗi converter". Hãy xác định kiểu Java còn lại có phải basic type được provider hỗ trợ hay không.

Nếu thuộc tính cần một quy tắc lưu trữ khác, ưu tiên dùng @Convert(converter = ...) để chọn converter phù hợp thay vì tắt converter rồi mong provider tự hiểu custom value object.

## 7. Các loại thuộc tính không được converter áp dụng

AttributeConverter không phải công cụ chuyển đổi mọi loại mapping. Theo quy tắc JPA, converter không được áp dụng cho các thuộc tính:

- Có @Id hoặc @EmbeddedId.
- Có @Version.
- Là quan hệ entity: @OneToOne, @OneToMany, @ManyToOne hoặc @ManyToMany.
- Có @Enumerated.
- Có @Temporal.

Những loại trên có quy tắc mapping riêng của JPA. Không cố gắng dùng AttributeConverter để thay thế mapping quan hệ, khóa định danh, optimistic locking, enum mapping hoặc temporal mapping được chỉ định bằng annotation tương ứng.

### 7.1. Không dùng converter cho ID

Không thiết kế converter để biến khóa chính custom type thành một kiểu database khác khi thuộc tính được đánh dấu @Id. Với khóa phức hợp, dùng @EmbeddedId hoặc @IdClass và mapping phù hợp.

Nếu muốn một value object đại diện cho ID trong domain, hãy xem xét cách mapping khóa theo khả năng của JPA/provider và giữ rõ ràng identity của entity. Không dựa vào autoApply để chuyển đổi ID.

### 7.2. Không dùng converter cho version

@Version được provider sử dụng để kiểm soát optimistic locking. Không dùng AttributeConverter để biến đổi version field. Hãy để provider quản lý kiểu version được hỗ trợ như numeric hoặc timestamp theo quy định JPA.

### 7.3. Không dùng converter cho quan hệ entity

Một quan hệ ManyToOne không thể được chuyển thành một chuỗi mã tùy ý bằng AttributeConverter. Quan hệ phải được ánh xạ bằng association và foreign key:

```java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;
```

Nếu database chỉ lưu customer_code và không cần quản lý association, có thể mô hình nó thành một basic attribute như String hoặc CustomerCode value object. Nhưng khi đã mô hình thành quan hệ entity, hãy dùng mapping quan hệ JPA thay vì converter.

### 7.4. Không kết hợp converter với @Enumerated hoặc @Temporal

Một enum có thể được lưu bằng tên hoặc ordinal thông qua @Enumerated. Nếu cần cách lưu tùy chỉnh như mã "P", "C", "X", hãy dùng AttributeConverter cho enum và không đánh dấu thuộc tính bằng @Enumerated.

Ví dụ:

```java
public enum OrderStatus {
    PENDING, CONFIRMED, CANCELLED
}

@Converter(autoApply = true)
public class OrderStatusConverter
        implements AttributeConverter<OrderStatus, String> {

    @Override
    public String convertToDatabaseColumn(OrderStatus status) {
        if (status == null) {
            return null;
        }

        return switch (status) {
            case PENDING -> "P";
            case CONFIRMED -> "C";
            case CANCELLED -> "X";
        };
    }

    @Override
    public OrderStatus convertToEntityAttribute(String code) {
        if (code == null) {
            return null;
        }

        return switch (code) {
            case "P" -> OrderStatus.PENDING;
            case "C" -> OrderStatus.CONFIRMED;
            case "X" -> OrderStatus.CANCELLED;
            default -> throw new IllegalArgumentException(
                "Unknown order status code: " + code
            );
        };
    }
}
```

Không đặt @Enumerated(EnumType.STRING) lên cùng field OrderStatus nếu muốn converter điều khiển representation. Với kiểu ngày giờ, JPA đã hỗ trợ nhiều kiểu java.time; hãy dùng mapping tiêu chuẩn trừ khi có yêu cầu lưu trữ đặc biệt. @Temporal chủ yếu dành cho các kiểu Date/Calendar cũ và không được kết hợp converter theo quy tắc JPA.

## 8. Converter phải ánh xạ về kiểu database cơ bản

Kiểu Y trong AttributeConverter<X, Y> cần là kiểu mà provider có thể ánh xạ thành kiểu database cơ bản. Các kiểu thường gặp gồm String, Integer, Long, BigDecimal, Boolean, LocalDate hoặc các kiểu cơ bản khác được provider hỗ trợ.

Ví dụ hợp lý:

- EmailAddress → String.
- CountryCode → String.
- Money → BigDecimal nếu đơn vị tiền tệ được cố định hoặc lưu ở nơi khác.
- ExternalReference → UUID hoặc String tùy schema.

Không nên dùng converter để biến một object có nhiều quan hệ thành một chuỗi JSON chỉ nhằm tránh thiết kế bảng. Cách đó làm mất khả năng truy vấn quan hệ, constraint, join và cập nhật từng thành phần. Nếu thật sự cần lưu JSON, hãy cân nhắc kiểu JSON native/provider-specific, embeddable, collection mapping hoặc thiết kế schema phù hợp với database.

Một converter thường nên stateless và thread-safe. Không lưu trạng thái của entity trong field mutable, không giữ request context, không thực hiện truy vấn database hoặc gọi HTTP từ converter. Conversion diễn ra trong quá trình ORM đọc/ghi; side effect có thể gây vòng lặp, hiệu năng kém và khó kiểm thử.

## 9. Converter và truy vấn Spring Data JPA

Với derived query hoặc JPQL dựa trên thuộc tính đã được converter ánh xạ, ứng dụng truyền giá trị theo kiểu Java X. Provider chịu trách nhiệm chuyển tham số sang kiểu Y khi tạo SQL.

Ví dụ:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByPrimaryEmail(EmailAddress email);
}
```

Method nhận EmailAddress vì đó là kiểu thuộc tính trong entity. Không đổi method parameter thành String chỉ vì database lưu VARCHAR.

Với JPQL:

```java
@Query("""
    select c
    from Customer c
    where c.primaryEmail = :email
    """)
Optional<Customer> findByEmail(
    @Param("email") EmailAddress email
);
```

JPQL tham chiếu entity và property Java. Provider sử dụng mapping converter để xử lý giá trị tương ứng.

Với native SQL, câu query làm việc trực tiếp với bảng/cột và kiểu database. Việc áp dụng converter cho parameter/result của native query có thể phụ thuộc cách provider nhận diện mapping. Không giả định mọi native query tự động chuyển mọi kiểu custom. Nếu cần native query, hãy kiểm thử với đúng provider/database; có thể truyền kiểu Y hoặc dùng projection/mapping phù hợp theo API đang dùng.

Converter cũng không tự chuyển đổi JSON HTTP. Jackson serialization/deserialization của request/response là một cơ chế khác. Nếu API nhận email dưới dạng chuỗi, cần mapping DTO sang EmailAddress ở application boundary; AttributeConverter chỉ phục vụ persistence.

## 10. Schema, column definition và validation

Converter không thay thế việc thiết kế column. Nếu X chuyển thành Y là String, cột database cần độ dài và kiểu dữ liệu phù hợp:

```java
@Convert(converter = EmailAddressConverter.class)
@Column(name = "email", nullable = false, length = 254)
private EmailAddress email;
```

Nếu Y là BigDecimal, cần cân nhắc precision và scale:

```java
@Column(name = "amount", precision = 19, scale = 2)
private Money amount;
```

Trong ví dụ Money, converter phải trả về BigDecimal và cách biểu diễn phải bảo toàn giá trị nghiệp vụ. Nếu Money có currency code, chỉ chuyển amount thành BigDecimal sẽ làm mất currency. Khi có nhiều currency, cần lưu currency riêng hoặc thiết kế một mapping phù hợp hơn, chẳng hạn embeddable gồm amount và currency.

Với migration-managed schema, migration phải tạo column đúng kiểu, length, precision, nullability, index và constraint. @Column mô tả mapping; @Convert mô tả chuyển đổi giá trị; hai annotation giải quyết hai phần khác nhau.

## 11. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Converter không được tự áp dụng | Quên autoApply = true hoặc converter không được nhận diện trong persistence unit | Kiểm tra @Converter và cấu hình EMF |
| Converter áp dụng ngoài ý muốn | autoApply đặt trên kiểu Java quá rộng | Dùng value object chuyên biệt hoặc chọn @Convert tường minh |
| Dữ liệu đọc lên lỗi | Giá trị DB cũ không đúng định dạng mà converter mong đợi | Kiểm tra dữ liệu legacy, migration và xử lý lỗi rõ ràng |
| EntityManagerFactory không khởi tạo | Custom type không có mapping hợp lệ sau khi tắt conversion | Chọn converter hoặc kiểu basic được provider hỗ trợ |
| Enum không dùng mã tùy chỉnh | Kết hợp @Enumerated với AttributeConverter | Bỏ @Enumerated khi dùng converter cho enum |
| Converter không chạy trên ID/version | JPA loại trừ các thuộc tính này | Thiết kế mapping ID/version theo cơ chế JPA |
| JPQL báo không tìm thấy entity | Dùng table name thay entity name | Dùng entity name và property Java trong JPQL |
| Native query sai tên cột | Dùng property Java thay database column | Dùng table/column name vật lý trong SQL |
| Cột lưu bị cắt dữ liệu | Y dài hơn column length hoặc schema cũ | Đặt length phù hợp và migration schema |
| So sánh giá trị sai | Conversion làm thay đổi chuẩn hóa hoặc representation | Kiểm thử round-trip và quy tắc equals/hashCode của value object |

## 12. Bài tập thực hành

1. Tạo EmailAddress value object và converter sang String.
2. Đánh dấu converter bằng @Converter(autoApply = true), sau đó dùng EmailAddress ở hai entity khác nhau.
3. Kiểm tra dữ liệu lưu trong database là VARCHAR và khi đọc lại nhận được EmailAddress.
4. Tạo một converter thay thế cho field legacy và áp dụng bằng @Convert(converter = ...).
5. Thử disableConversion trên thuộc tính có kiểu basic được provider hỗ trợ; quan sát khác biệt.
6. Thử kết hợp @Enumerated với converter trong một mapping riêng và đọc thông báo lỗi/kiểm tra quy tắc provider.
7. Viết derived query nhận EmailAddress và xác nhận parameter được chuyển đổi.
8. Viết JPQL theo property EmailAddress; so sánh với native query theo column email.
9. Thử đọc một giá trị legacy không hợp lệ và quyết định cách migration dữ liệu.
10. Viết round-trip test: Java value → database value → Java value; xác nhận equality và null behavior.

**Nguyên tắc xuyên suốt:** autoApply giúp dùng một converter nhất quán cho các thuộc tính có kiểu Java phù hợp trong persistence unit. Dùng @Convert để chọn converter cụ thể hoặc tắt conversion khi kiểu còn lại vẫn có mapping hợp lệ. AttributeConverter chỉ dành cho basic values theo quy tắc JPA; không dùng nó thay thế mapping ID, version, relationship, enum/temporal mapping hoặc toàn bộ object graph.

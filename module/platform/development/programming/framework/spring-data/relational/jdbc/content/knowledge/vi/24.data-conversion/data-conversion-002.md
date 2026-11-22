# Viết @ReadingConverter và @WritingConverter

Spring Data Relational JDBC cho phép đăng ký converter để chuyển đổi giá trị giữa mô hình Java và kiểu dữ liệu mà JDBC/database sử dụng. Hai annotation `@ReadingConverter` và `@WritingConverter` giúp Spring Data biết converter được áp dụng theo chiều nào:

- `@WritingConverter` chuyển giá trị từ domain model sang giá trị dùng để ghi xuống database.
- `@ReadingConverter` chuyển giá trị do JDBC driver đọc được thành kiểu mà domain model cần.

Ví dụ, ứng dụng muốn biểu diễn email bằng kiểu `EmailAddress` riêng để kiểm tra và chuẩn hóa dữ liệu, trong khi database chỉ lưu email dưới dạng `VARCHAR`. Writing converter chuyển `EmailAddress` thành `String` khi ghi; reading converter chuyển `String` thành `EmailAddress` khi đọc.

Bài học trình bày cách viết hai loại converter, đăng ký chúng với Spring Data JDBC, xử lý kiểu dữ liệu JDBC và kiểm thử việc chuyển đổi trong một lần lưu/đọc aggregate.

## 1. Converter trong Spring Data JDBC là gì?

Spring Data JDBC dùng hệ thống mapping để chuyển đổi object trong Java thành giá trị của một hàng quan hệ và khôi phục object khi đọc hàng đó. Trong nhiều trường hợp, kiểu Java đã được hỗ trợ trực tiếp hoặc được JDBC driver xử lý nên không cần converter tự viết.

Khi một property có kiểu miền nghiệp vụ riêng hoặc cần cách biểu diễn khác trong database, ta có thể đăng ký một implementation của Spring `Converter<S, T>`.

Ví dụ:

- Java dùng `EmailAddress`, database lưu `VARCHAR`.
- Java dùng enum `OrderStatus`, database lưu mã ngắn như `N`, `P`, `C`.
- Java dùng kiểu value object cho mã quốc gia, database lưu chuỗi hai ký tự.
- Database trả về kiểu riêng của driver, ứng dụng muốn chuyển nó thành kiểu Java dễ sử dụng.

Một converter là phép chuyển đổi giữa một kiểu nguồn và một kiểu đích. Với Spring Data JDBC, converter tùy chỉnh được áp dụng ở **cấp property**: một giá trị domain được chuyển thành một giá trị database và ngược lại. Converter không tự biến một object phức tạp thành nhiều cột khác nhau.

## 2. Phân biệt chiều đọc và chiều ghi

~~~text
Java object                                  Database row

EmailAddress("user@example.com")  ------->  "user@example.com"
             WritingConverter

EmailAddress("user@example.com")  <-------  "user@example.com"
             ReadingConverter
~~~

Hai chiều có source và target đảo ngược nhau:

| Loại converter | Generic type | Hướng chuyển đổi | Mục đích |
| --- | --- | --- | --- |
| Writing | `Converter<EmailAddress, String>` | Domain → JDBC value | Chuẩn bị giá trị để ghi |
| Reading | `Converter<String, EmailAddress>` | JDBC value → Domain | Khôi phục kiểu miền nghiệp vụ |

### 2.1. @WritingConverter

`@WritingConverter` đánh dấu converter được dùng khi Spring Data ghi property vào database.

~~~java
@WritingConverter
public class EmailAddressWritingConverter
        implements Converter<EmailAddress, String> {

    @Override
    public String convert(EmailAddress source) {
        return source.value();
    }
}
~~~

`Converter<EmailAddress, String>` có kiểu nguồn là `EmailAddress` và kiểu đích là `String`. Spring Data nhận value object từ entity, gọi converter và đưa chuỗi trả về vào thao tác JDBC.

### 2.2. @ReadingConverter

`@ReadingConverter` đánh dấu converter được dùng khi Spring Data đọc giá trị từ database và gán vào property của entity.

~~~java
@ReadingConverter
public class EmailAddressReadingConverter
        implements Converter<String, EmailAddress> {

    @Override
    public EmailAddress convert(String source) {
        return new EmailAddress(source);
    }
}
~~~

JDBC driver trả về `String` từ cột `VARCHAR`. Spring Data gọi reading converter để tạo object `EmailAddress` trước khi hoàn thành entity.

### 2.3. Vì sao cần chỉ rõ hướng?

Spring Data cần xác định converter áp dụng cho chiều đọc hay chiều ghi. Điều này đặc biệt quan trọng khi cả source và target đều là kiểu đơn giản mà JDBC có thể xử lý.

Ví dụ `Converter<Boolean, String>` có thể bị hiểu nhầm nếu không có chỉ dẫn: nó trông giống một phép chuyển đổi tổng quát giữa hai kiểu đơn giản. `@WritingConverter` nói rõ rằng chỉ dùng nó cho chiều ghi. Converter ngược `Converter<String, Boolean>` cần `@ReadingConverter`.

Với kiểu domain tùy chỉnh và một kiểu JDBC đơn giản, framework thường có thể suy ra hướng từ source/target. Tuy vậy, gắn annotation đúng chiều giúp ý định rõ ràng và tránh đăng ký converter không mong muốn.

## 3. Ví dụ: EmailAddress được lưu bằng VARCHAR

Ứng dụng muốn tránh truyền chuỗi email tùy ý khắp domain model. Ta tạo value object `EmailAddress` để gom quy tắc kiểm tra dữ liệu.

~~~java
import java.util.Objects;

public record EmailAddress(String value) {

    public EmailAddress {
        Objects.requireNonNull(value, "email must not be null");

        value = value.trim();

        if (value.isEmpty() || !value.contains("@")) {
            throw new IllegalArgumentException("Invalid email address");
        }
    }
}
~~~

Đây là kiểm tra minh họa, không phải bộ xác thực đầy đủ theo mọi quy tắc email. Ứng dụng thực tế nên dùng validation phù hợp với yêu cầu nghiệp vụ.

Entity có property kiểu `EmailAddress`:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Column("email_address")
    private EmailAddress emailAddress;

    protected Customer() {
    }

    public Customer(EmailAddress emailAddress) {
        this.emailAddress = emailAddress;
    }

    public Long getId() {
        return id;
    }

    public EmailAddress getEmailAddress() {
        return emailAddress;
    }
}
~~~

Database chỉ cần một cột chuỗi:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email_address VARCHAR(320) NOT NULL
);
~~~

Nếu không đăng ký converter, Spring Data JDBC có thể không biết cách ánh xạ kiểu `EmailAddress` tùy chỉnh thành kiểu mà JDBC hỗ trợ. Hai converter sẽ giải quyết việc đó.

## 4. Viết WritingConverter

Writing converter chuyển `EmailAddress` thành `String`:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class EmailAddressWritingConverter
        implements Converter<EmailAddress, String> {

    @Override
    public String convert(EmailAddress source) {
        return source.value();
    }
}
~~~

Đọc từng phần:

- `Converter<EmailAddress, String>`: kiểu nguồn là `EmailAddress`, kiểu đích là `String`.
- `@WritingConverter`: chỉ định converter cho chiều ghi.
- `source.value()`: lấy biểu diễn chuỗi đã được value object chuẩn hóa.

Khi lưu một customer:

~~~java
Customer customer = new Customer(
    new EmailAddress("  user@example.com  ")
);

Customer saved = customerRepository.save(customer);
~~~

Giá trị trong object đã được chuẩn hóa thành `user@example.com` khi tạo `EmailAddress`. Writing converter lấy giá trị đó và đưa chuỗi vào cột `email_address`.

Converter chỉ chuyển đổi dữ liệu. Nó không tự kiểm tra uniqueness, không tạo index và không thay thế validation ở domain/database.

## 5. Viết ReadingConverter

Reading converter thực hiện chiều ngược lại:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class EmailAddressReadingConverter
        implements Converter<String, EmailAddress> {

    @Override
    public EmailAddress convert(String source) {
        return new EmailAddress(source);
    }
}
~~~

Khi Spring Data JDBC đọc hàng từ database, driver trả về chuỗi trong cột `email_address`. Converter tạo lại value object `EmailAddress`.

~~~java
Customer loaded = customerRepository.findById(saved.getId())
    .orElseThrow();

EmailAddress email = loaded.getEmailAddress();
~~~

Sau khi đọc, code nghiệp vụ tiếp tục làm việc với `EmailAddress` thay vì chuỗi thô.

### Dữ liệu database không hợp lệ

Reading converter cũng là ranh giới để phát hiện dữ liệu không tuân thủ quy tắc domain. Nếu cột chứa chuỗi không thể tạo thành `EmailAddress`, constructor có thể ném `IllegalArgumentException`.

Điều này có thể xảy ra khi dữ liệu được ghi bởi ứng dụng khác, migration cũ tạo ra giá trị sai, người vận hành sửa dữ liệu trực tiếp hoặc quy tắc validation đã thay đổi.

Hãy quyết định cách xử lý dữ liệu cũ trước khi triển khai converter có validation nghiêm ngặt. Nếu cần chuyển đổi dữ liệu, dùng migration hoặc quy trình làm sạch có kiểm soát thay vì âm thầm thay dữ liệu sai bằng giá trị mặc định.

## 6. Đăng ký converter với Spring Data JDBC

Viết class converter là chưa đủ. Spring Data JDBC cần nhận được các converter thông qua `CustomConversions` để `JdbcConverter` sử dụng chúng khi mapping.

Với cấu hình Spring Data JDBC dựa trên `AbstractJdbcConfiguration`, extension point hiện hành là override `userConverters()`:

~~~java
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;

@Configuration
public class DataJdbcConfiguration extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
            new EmailAddressWritingConverter(),
            new EmailAddressReadingConverter()
        );
    }
}
~~~

`userConverters()` trả về các converter instance do ứng dụng cung cấp. Spring Data kết hợp chúng với converter mặc định và converter của JDBC dialect để xây dựng `JdbcCustomConversions`, sau đó dùng chúng trong `JdbcConverter`.

### Vì sao đăng ký theo instance?

Spring Data JDBC không tự động lấy mọi class có annotation converter từ classpath hoặc component scan để đăng ký. Converter cần được thêm tường minh vào danh sách custom conversions. Việc này tránh đưa converter vào toàn bộ conversion service của ứng dụng khi nó chỉ nên áp dụng cho mapping database.

Vì vậy, chỉ thêm `@Component` vào converter không thay thế bước đăng ký trong `userConverters()`.

### Nếu ứng dụng dùng Spring Boot auto-configuration

Nhiều ứng dụng Spring Boot để Boot quản lý hạ tầng Spring Data JDBC. Trong trường hợp đó, hãy dùng extension point cấu hình custom conversions mà phiên bản Spring Boot/Spring Data của dự án hỗ trợ; Spring Data JDBC hiện cho phép cung cấp bean `JdbcCustomConversions` để Boot sử dụng.

Không nên đồng thời tạo nhiều cấu hình JDBC cạnh tranh nhau. Trong các phiên bản hiện hành, nếu kế thừa `AbstractJdbcConfiguration` thì nên bổ sung converter qua `userConverters()` thay vì tự override `jdbcCustomConversions()`. Phương thức `jdbcCustomConversions()` lắp ghép converter mặc định, converter của dialect và converter người dùng; ghi đè trực tiếp có thể làm mất converter do dialect đăng ký.

## 7. Ví dụ đầy đủ: repository và luồng lưu/đọc

Repository tiêu chuẩn:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

Service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {

    private final CustomerRepository customers;

    public CustomerService(CustomerRepository customers) {
        this.customers = customers;
    }

    @Transactional
    public Long register(String rawEmail) {
        EmailAddress email = new EmailAddress(rawEmail);

        Customer saved = customers.save(new Customer(email));

        return saved.getId();
    }

    @Transactional(readOnly = true)
    public EmailAddress getEmail(Long customerId) {
        Customer customer = customers.findById(customerId)
            .orElseThrow();

        return customer.getEmailAddress();
    }
}
~~~

Luồng dữ liệu khi ghi:

~~~mermaid
flowchart TD
    A["Customer.emailAddress"] --> B["EmailAddressWritingConverter"]
    B --> C["String"]
    C --> D["JDBC bind parameter"]
    D --> E["customers.email_address VARCHAR"]
~~~

Luồng dữ liệu khi đọc:

~~~mermaid
flowchart TD
    A["customers.email_address VARCHAR"] --> B["JDBC driver trả String"]
    B --> C["EmailAddressReadingConverter"]
    C --> D["EmailAddress"]
    D --> E["Customer.emailAddress"]
~~~

Hai converter tạo thành một cặp biểu diễn nhất quán. Giá trị sau khi ghi rồi đọc lại cần khôi phục cùng ý nghĩa domain, dù dạng lưu trữ là chuỗi.

## 8. Ví dụ enum được lưu bằng mã riêng

Hãy xét trường hợp database lưu trạng thái đơn hàng bằng mã một ký tự, còn Java dùng enum:

~~~java
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
            "Unknown order status code: " + code
        );
    }
}
~~~

Writing converter:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class OrderStatusWritingConverter
        implements Converter<OrderStatus, String> {

    @Override
    public String convert(OrderStatus source) {
        return source.code();
    }
}
~~~

Reading converter:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class OrderStatusReadingConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.fromCode(source);
    }
}
~~~

Đăng ký cả hai converter:

~~~java
@Override
protected List<?> userConverters() {
    return List.of(
        new EmailAddressWritingConverter(),
        new EmailAddressReadingConverter(),
        new OrderStatusWritingConverter(),
        new OrderStatusReadingConverter()
    );
}
~~~

Trong trường hợp này, cả enum và String đều là kiểu đơn giản có thể biểu diễn ở database. Annotation rất quan trọng để phân biệt:

- `OrderStatus → String` chỉ dùng khi ghi.
- `String → OrderStatus` chỉ dùng khi đọc.

Nếu không phân biệt hướng, converter có thể bị áp dụng ở chiều không mong muốn hoặc gây xung đột với conversion mặc định.

### So sánh lưu enum theo tên và theo mã

Spring Data JDBC có thể ánh xạ enum theo tên mặc định. Nếu lưu enum `PAID` theo tên, database giữ chuỗi `PAID`. Khi dùng converter trên, database giữ mã `P`.

| Cách lưu | Giá trị database | Ảnh hưởng khi đổi tên enum |
| --- | --- | --- |
| Mặc định theo enum name | `PAID` | Đổi tên constant có thể làm dữ liệu cũ không đọc được |
| Converter theo mã ổn định | `P` | Có thể đổi tên constant mà giữ mã lưu trữ |

Mã lưu trữ cần được xem như hợp đồng dữ liệu. Không tái sử dụng mã cũ cho trạng thái có ý nghĩa khác; khi thêm trạng thái mới, hãy cập nhật converter và migration tương ứng.

## 9. Simple type và converter bị mơ hồ

Spring Data JDBC có thể nhận biết hướng chuyển đổi khi một phía là kiểu domain tùy chỉnh và phía kia là kiểu JDBC đơn giản. Tuy nhiên, khi cả hai phía đều là kiểu đơn giản, hướng không thể được suy ra an toàn.

Ví dụ:

~~~java
Converter<Boolean, String>
Converter<String, Boolean>
~~~

Cả Boolean và String đều là kiểu đơn giản. Converter đầu phải có `@WritingConverter`, converter sau phải có `@ReadingConverter`.

Ví dụ ghi boolean thành `T` hoặc `F`:

~~~java
@WritingConverter
public class BooleanToFlagConverter
        implements Converter<Boolean, String> {

    @Override
    public String convert(Boolean source) {
        return Boolean.TRUE.equals(source) ? "T" : "F";
    }
}
~~~

Converter đọc:

~~~java
@ReadingConverter
public class FlagToBooleanConverter
        implements Converter<String, Boolean> {

    @Override
    public Boolean convert(String source) {
        return switch (source) {
            case "T" -> true;
            case "F" -> false;
            default -> throw new IllegalArgumentException(
                "Unsupported flag value: " + source
            );
        };
    }
}
~~~

Cách viết trên giả định property không null hoặc null được xử lý ở lớp mapping/database phù hợp. Không dùng giá trị mặc định `F` để che giấu dữ liệu null hoặc mã không hợp lệ nếu nghiệp vụ cần phân biệt các trạng thái đó.

## 10. Converter chỉ chuyển một property, không chuyển nhiều cột

Đây là giới hạn quan trọng của custom converter trong Spring Data JDBC.

Converter tùy chỉnh được áp dụng ở cấp property: một giá trị trong domain được chuyển thành một giá trị lưu trữ, và ngược lại. Nó không tự ánh xạ một object thành nhiều cột.

Ví dụ, `Money` gồm `amount` và `currency`:

~~~java
public record Money(
    BigDecimal amount,
    String currency
) {
}
~~~

Nếu muốn lưu thành hai cột `amount` và `currency`, hãy dùng `@Embedded` để mô hình hóa các thuộc tính trong cùng hàng:

~~~java
@Table("invoices")
public class Invoice {

    @Id
    private Long id;

    @Embedded(prefix = "total_")
    private Money total;
}
~~~

Không viết một converter `Money → String` rồi kỳ vọng nó tự tạo hai cột. Nếu thật sự muốn lưu cả Money trong một cột JSON hoặc chuỗi, converter có thể chuyển toàn object thành một giá trị duy nhất; đó là thiết kế lưu trữ khác và cần tự quyết định serialization/versioning.

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Một domain value object lưu trong một cột VARCHAR | Reading + Writing converter |
| Enum lưu bằng mã riêng | Reading + Writing converter |
| Value object gồm nhiều cột trong cùng hàng | `@Embedded` |
| Một object được lưu thành JSON trong một cột | Converter/JSON mapping một giá trị, tùy database |
| Entity có vòng đời và bảng riêng | Entity relationship/aggregate mapping |

## 11. Kiểu JDBC cụ thể và JdbcValue

Thông thường, converter trả về kiểu đơn giản mà JDBC driver xử lý được, ví dụ `String`, `Integer` hoặc `BigDecimal`. Spring Data và dialect sẽ xác định JDBC type phù hợp.

Có trường hợp cần chỉ định rõ SQL type khi bind parameter. Spring Data JDBC cung cấp `JdbcValue` để ghép giá trị với `SQLType`.

Ví dụ converter ghi một chuỗi vào kiểu JDBC VARCHAR:

~~~java
import java.sql.JDBCType;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;
import org.springframework.data.jdbc.core.mapping.JdbcValue;

@WritingConverter
public class EmailAddressJdbcValueConverter
        implements Converter<EmailAddress, JdbcValue> {

    @Override
    public JdbcValue convert(EmailAddress source) {
        return JdbcValue.of(source.value(), JDBCType.VARCHAR);
    }
}
~~~

`JdbcValue.of(value, jdbcType)` tạo wrapper chứa giá trị và kiểu JDBC sẽ dùng cho bind parameter. Chỉ cần cách này khi cần kiểm soát kiểu bind cụ thể; converter trả về `String` thông thường thường đã đủ.

Với kiểu database đặc thù như JSON, UUID hoặc binary, cần kiểm tra yêu cầu của driver và dialect. `JDBCType` truyền vào phải phù hợp với kiểu cột và cách driver xử lý giá trị. Không phải database nào cũng nhận cùng một kiểu bind cho một loại dữ liệu mở rộng.

## 12. Null, dữ liệu không hợp lệ và quy tắc chuyển đổi

Converter nên có hợp đồng rõ ràng cho dữ liệu đầu vào.

### Giá trị null

Nếu property có thể null, hãy giữ đúng semantics null của database và domain. Không nên biến null thành chuỗi như `"NULL"` hoặc một mã sentinel trừ khi đó là quy ước lưu trữ được thiết kế rõ ràng.

Một cột `NULL` khác với cột chứa bốn ký tự `NULL`. Tương tự, chuỗi rỗng `""` khác null.

### Dữ liệu không hợp lệ khi đọc

Reading converter có thể phát hiện giá trị database không hợp lệ và từ chối tạo domain object. Ví dụ, `OrderStatus.fromCode("X")` ném exception vì mã X không được hỗ trợ.

Hãy có migration khi thay đổi mã lưu trữ:

1. Xác định các giá trị cũ trong database.
2. Viết migration chuyển giá trị sang mã mới nếu cần.
3. Cập nhật reading/writing converter.
4. Triển khai theo thứ tự tương thích nếu nhiều phiên bản ứng dụng cùng chạy.
5. Kiểm thử đọc cả dữ liệu cũ và mới trong giai đoạn chuyển đổi.

### Chuẩn hóa khi ghi và đọc

Một cặp converter nên tuân theo quy tắc round-trip:

~~~text
read(write(value)) = value
~~~

Đẳng thức này hiểu theo ý nghĩa domain, không nhất thiết theo identity object. Ví dụ, email có thể được trim khi tạo value object; sau khi ghi rồi đọc, giá trị chuẩn hóa vẫn phải tương đương.

Nếu writing converter đổi định dạng nhưng reading converter không hiểu định dạng đó, dữ liệu sẽ không thể khôi phục. Hãy xem hai chiều như một hợp đồng chung.

## 13. Kiểm thử converter độc lập

Converter là class Java thông thường, có thể kiểm thử trực tiếp mà không cần database.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class EmailAddressConverterTest {

    private final EmailAddressWritingConverter writing =
        new EmailAddressWritingConverter();

    private final EmailAddressReadingConverter reading =
        new EmailAddressReadingConverter();

    @Test
    void writesDomainValueAsString() {
        EmailAddress email = new EmailAddress("user@example.com");

        String stored = writing.convert(email);

        assertThat(stored).isEqualTo("user@example.com");
    }

    @Test
    void readsStringAsDomainValue() {
        EmailAddress email = reading.convert("user@example.com");

        assertThat(email).isEqualTo(
            new EmailAddress("user@example.com")
        );
    }

    @Test
    void supportsRoundTrip() {
        EmailAddress original =
            new EmailAddress("user@example.com");

        EmailAddress restored =
            reading.convert(writing.convert(original));

        assertThat(restored).isEqualTo(original);
    }
}
~~~

Unit test xác nhận logic chuyển đổi, validation và quy tắc chuẩn hóa. Nó không xác nhận Spring Data đã đăng ký converter hoặc JDBC driver bind kiểu dữ liệu đúng.

## 14. Integration test với Spring Data JDBC

Cần có ít nhất một integration test để xác nhận converter thực sự được dùng khi repository ghi và đọc dữ liệu.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;

@DataJdbcTest
class CustomerRepositoryConversionTest {

    @Autowired
    CustomerRepository customers;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void persistsEmailAddressAsStringAndReadsItBack() {
        EmailAddress email =
            new EmailAddress("user@example.com");

        Customer saved =
            customers.save(new Customer(email));

        String rawValue = jdbcTemplate.queryForObject(
            "SELECT email_address FROM customers WHERE id = ?",
            String.class,
            saved.getId()
        );

        assertThat(rawValue).isEqualTo("user@example.com");

        Customer loaded = customers.findById(saved.getId())
            .orElseThrow();

        assertThat(loaded.getEmailAddress()).isEqualTo(email);
    }
}
~~~

Ví dụ giả định test có migration tạo bảng `customers` và cấu hình custom conversions được nạp vào Spring context. Nếu cấu hình JDBC của ứng dụng nằm ngoài test slice, hãy import cấu hình đó vào test hoặc dùng cấu hình integration test tương ứng.

Một test đầy đủ nên xác nhận ba điều:

- Repository ghi property domain thành đúng giá trị SQL.
- Repository đọc giá trị SQL thành đúng kiểu domain.
- Giá trị đọc lại tương đương giá trị ban đầu.

Với enum code, bổ sung test cho từng mã hợp lệ và mã không được hỗ trợ. Với dữ liệu null, kiểm thử riêng nếu property/cột cho phép null.

## 15. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Property custom type không lưu được | Chưa đăng ký writing converter | Kiểm tra converter và `userConverters()` |
| Đọc hàng thất bại khi materialize entity | Thiếu reading converter hoặc source type sai | Kiểm tra kiểu JDBC driver trả về và converter đọc |
| Converter bị gọi sai chiều | Thiếu annotation hoặc generic type bị đảo | Dùng annotation đúng chiều và kiểm tra `Converter<S, T>` |
| Converter không được Spring Data sử dụng | Chỉ thêm `@Component` hoặc để class trên classpath | Đăng ký converter instance với custom conversions |
| Converter bị mơ hồ giữa hai kiểu đơn giản | Không chỉ rõ hướng | Gắn annotation đúng chiều |
| Giá trị enum trong DB không đọc được | Mã trong database không có trong enum | Kiểm tra dữ liệu và `fromCode` |
| Dữ liệu null biến thành chuỗi sentinel | Converter tự thay null bằng giá trị mặc định | Giữ semantics null hoặc định nghĩa sentinel rõ ràng |
| Object nhiều thuộc tính chỉ được lưu một cột | Mong converter tự tạo nhiều cột | Dùng `@Embedded` hoặc mô hình quan hệ phù hợp |
| JDBC báo lỗi kiểu bind | Driver cần SQL type cụ thể | Cân nhắc `JdbcValue` và `JDBCType` |
| Converter hoạt động ở unit test nhưng không ở repository | Test chưa tải cấu hình JDBC có custom conversions | Import cấu hình và chạy integration test |
| Dữ liệu cũ không thể đọc sau khi đổi format | Reading converter chỉ hỗ trợ format mới | Migration hoặc hỗ trợ tương thích format cũ |

## 16. Quy trình triển khai converter

Khi cần thêm một kiểu domain mới vào mapping Spring Data JDBC, hãy thực hiện theo trình tự:

1. Xác định kiểu Java và kiểu cột database tương ứng.
2. Xác định dữ liệu cần chuyển đổi theo chiều ghi và chiều đọc.
3. Viết `Converter<DomainType, JdbcType>` với `@WritingConverter`.
4. Viết `Converter<JdbcType, DomainType>` với `@ReadingConverter`.
5. Đăng ký cả hai converter bằng `userConverters()` hoặc cơ chế custom conversions mà cấu hình Spring Boot hiện tại hỗ trợ.
6. Kiểm tra schema, nullability và dữ liệu cũ.
7. Viết unit test cho từng chiều và round-trip.
8. Viết integration test lưu/đọc qua repository.
9. Nếu kiểu JDBC cần chỉ định tường minh, dùng `JdbcValue`.
10. Triển khai migration tương thích nếu format lưu trữ đã thay đổi.

Không nên tạo converter nếu Spring Data JDBC hoặc JDBC driver đã hỗ trợ kiểu đó theo cách phù hợp. Converter tùy chỉnh làm tăng hợp đồng mapping mà nhóm phát triển phải duy trì; chỉ dùng khi cần một biểu diễn domain/database khác nhau hoặc quy tắc chuyển đổi cụ thể.

## 17. Bài tập tự thực hành

### Bài 1 — EmailAddress

Tạo value object `EmailAddress`, writing converter `EmailAddress → String` và reading converter `String → EmailAddress`. Đăng ký cả hai và lưu một Customer qua repository.

### Bài 2 — Kiểm tra round-trip

Viết unit test xác nhận `reading.convert(writing.convert(value))` trả về value tương đương ban đầu. Thử input có khoảng trắng đầu/cuối và xác định nơi chuẩn hóa nên diễn ra.

### Bài 3 — Enum code

Tạo enum `OrderStatus` có mã `N`, `P` và `C`. Viết cặp converter và xác nhận database lưu mã ngắn thay vì tên enum.

### Bài 4 — Mã không hợp lệ

Thử đọc một hàng có status code không tồn tại. Quyết định ứng dụng nên từ chối dữ liệu, dùng trạng thái UNKNOWN hay chạy migration; triển khai quy tắc đã chọn trong reading converter.

### Bài 5 — Simple type ambiguity

Viết `Converter<Boolean, String>` và `Converter<String, Boolean>`. Thử bỏ annotation ở từng converter trong một nhánh thử nghiệm, quan sát cách Spring Data xác định hướng và giải thích vì sao cần chỉ rõ chiều.

### Bài 6 — Null semantics

Tạo property tùy chọn và cột nullable. Lưu object có giá trị null, đọc lại và xác nhận null không bị biến thành chuỗi rỗng hoặc sentinel.

### Bài 7 — JdbcValue

Tạo writing converter trả về `JdbcValue` với một `JDBCType` phù hợp. Kiểm tra giá trị được bind trên database mục tiêu và so sánh với converter trả về kiểu String thông thường.

### Bài 8 — Embedded hay converter?

Mô hình hóa `Money` gồm amount và currency. Phân biệt trường hợp muốn lưu cả Money thành một cột với trường hợp muốn lưu thành hai cột bằng `@Embedded`. Giải thích giới hạn property-level của converter.

## 18. Tài liệu tham khảo chính thức

- [Spring Data Relational — Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): custom converter, giới hạn chuyển đổi ở cấp property, cách đăng ký qua `userConverters()` và `JdbcValue`.
- [Spring Data Relational — AbstractJdbcConfiguration API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/config/AbstractJdbcConfiguration.html): cấu hình JDBC và extension point `userConverters()`.
- [Spring Data Commons — Custom Conversions](https://docs.spring.io/spring-data/commons/reference/custom-conversions.html): cơ chế đăng ký converter và phân biệt chiều đọc/ghi.
- [Spring Data Relational — JdbcValue API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/mapping/JdbcValue.html): wrapper giá trị và JDBC type dùng cho bind parameter.

`@WritingConverter` và `@ReadingConverter` giúp Spring Data JDBC áp dụng converter đúng chiều giữa domain model và database. Hãy định nghĩa rõ source/target type, đăng ký converter instance trong custom conversions, và kiểm thử cả hai chiều qua repository. Khi converter chỉ xử lý một property và một giá trị lưu trữ, mô hình sẽ dễ hiểu; nếu value object cần nhiều cột, hãy dùng mapping embedded phù hợp thay vì cố ép converter làm nhiệm vụ đó.

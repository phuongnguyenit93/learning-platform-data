# Đăng ký converter qua `userConverters` hoặc `JdbcCustomConversions`

Trong **Spring Data Relational JDBC**, entity domain không bắt buộc phải dùng đúng các kiểu dữ liệu đơn giản mà JDBC driver trả về. Ứng dụng có thể mô hình hóa một giá trị bằng kiểu riêng, chẳng hạn `EmailAddress`, `Money` hoặc `OrderStatus`, rồi chuyển kiểu đó sang kiểu lưu trữ trong database khi ghi và chuyển ngược lại khi đọc.

Spring Data JDBC thực hiện việc chuyển đổi thông qua **converter**. Converter cần được đăng ký với cơ chế mapping của Spring Data để `JdbcConverter` có thể sử dụng. Có hai cách cấu hình thường gặp:

- Override `userConverters()` trong một class kế thừa `AbstractJdbcConfiguration`.
- Cung cấp bean `JdbcCustomConversions` chứa các converter tùy chỉnh.

Hai cách này đưa converter vào cùng hệ thống conversion của Spring Data JDBC. Hãy chọn một cách phù hợp với cấu hình ứng dụng và tránh đăng ký trùng cùng một converter. Bài học giải thích chiều đọc/ghi, cách viết converter hai chiều, cách đăng ký, ví dụ value object và cách kiểm tra việc chuyển đổi bằng repository.

## 1. Vì sao cần converter?

JDBC làm việc với kiểu dữ liệu mà driver và database hỗ trợ, chẳng hạn `VARCHAR`, `INTEGER`, `DECIMAL`, `TIMESTAMP` hoặc `BOOLEAN`. Trong domain, ứng dụng có thể muốn biểu diễn dữ liệu bằng kiểu có ý nghĩa hơn.

Ví dụ, nếu email được khai báo là `String`:

~~~java
private String email;
~~~

thì bất kỳ chuỗi nào cũng có thể được gán vào property. Một kiểu `EmailAddress` riêng có thể gom quy tắc tạo và xác thực địa chỉ email vào một nơi:

~~~java
public record EmailAddress(String value) {

    public EmailAddress {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Email address không được để trống"
            );
        }

        value = value.trim();
    }
}
~~~

Database vẫn có thể lưu email trong cột `VARCHAR`, trong khi domain dùng `EmailAddress`:

~~~java
@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Column("email_address")
    private EmailAddress email;

    // Constructor và getter.
}
~~~

Converter đảm nhiệm hai chiều:

~~~text
Khi ghi:
EmailAddress  --->  String  --->  VARCHAR

Khi đọc:
VARCHAR  --->  String  --->  EmailAddress
~~~

Converter giúp giữ kiểu domain có ý nghĩa mà không buộc schema phải lưu một kiểu dữ liệu phức tạp tương ứng.

## 2. Hai chiều chuyển đổi: reading và writing

Spring Data JDBC cần biết converter được dùng ở chiều nào:

| Chiều | Dữ liệu nguồn | Dữ liệu đích | Annotation |
|---|---|---|---|
| Reading | Kiểu JDBC/store | Kiểu domain | `@ReadingConverter` |
| Writing | Kiểu domain | Kiểu JDBC/store | `@WritingConverter` |

Hai annotation nằm trong package:

~~~java
org.springframework.data.convert
~~~

Converter sử dụng interface `Converter<S, T>` của Spring:

~~~java
org.springframework.core.convert.converter.Converter
~~~

Trong đó `S` là kiểu nguồn, `T` là kiểu đích. Nên đánh dấu rõ chiều chuyển đổi, đặc biệt khi cả hai kiểu đều là kiểu đơn giản như `String`, `Long` hoặc `Integer`.

### 2.1. Writing converter: từ domain sang kiểu lưu trữ

Khi ghi một `Customer`, Spring Data JDBC cần chuyển `EmailAddress` thành giá trị mà JDBC có thể bind:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class EmailAddressToStringConverter
        implements Converter<EmailAddress, String> {

    @Override
    public String convert(EmailAddress source) {
        return source.value();
    }
}
~~~

Converter nhận `EmailAddress` và trả về `String`. Spring Data JDBC sử dụng kết quả này khi ghi vào cột `VARCHAR`.

### 2.2. Reading converter: từ kiểu lưu trữ sang domain

Khi đọc cột `VARCHAR`, JDBC driver trả về `String`. Spring Data JDBC cần chuyển chuỗi đó thành `EmailAddress`:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class StringToEmailAddressConverter
        implements Converter<String, EmailAddress> {

    @Override
    public EmailAddress convert(String source) {
        return new EmailAddress(source);
    }
}
~~~

Constructor của `EmailAddress` tiếp tục áp dụng quy tắc xác thực. Nếu dữ liệu cũ trong database không hợp lệ, quá trình đọc có thể thất bại với lỗi chuyển đổi hoặc lỗi validation. Đây thường là dấu hiệu cần xử lý dữ liệu không hợp lệ rõ ràng, thay vì âm thầm tạo một object domain sai.

### 2.3. Vì sao nên đăng ký cả hai converter?

Nếu chỉ đăng ký `EmailAddressToStringConverter`, ứng dụng có thể ghi value object nhưng không đọc lại được nó theo cách mong muốn. Nếu chỉ đăng ký `StringToEmailAddressConverter`, ứng dụng có thể đọc được nhưng thiếu quy tắc ghi.

Với value object được lưu bằng một cột scalar, thường cần cả cặp:

- `EmailAddress -> String` cho writing.
- `String -> EmailAddress` cho reading.

Một converter đơn hướng vẫn hợp lệ khi use case chỉ cần một chiều, nhưng phải xác định rõ đường đọc/ghi còn lại được xử lý như thế nào.

## 3. Đăng ký qua `userConverters()`

Khi cấu hình Spring Data JDBC bằng `AbstractJdbcConfiguration`, cách gọn là override method `userConverters()` và trả về danh sách converter tùy chỉnh.

~~~java
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;

@Configuration
public class JdbcConfiguration extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
            new EmailAddressToStringConverter(),
            new StringToEmailAddressConverter()
        );
    }
}
~~~

`AbstractJdbcConfiguration` cung cấp cấu hình nền cho Spring Data JDBC, trong đó có bean `JdbcCustomConversions`. Các converter do `userConverters()` trả về được đưa vào cấu hình conversion mà framework sử dụng.

Trong cách này:

1. Tạo các class converter.
2. Đánh dấu đúng chiều bằng `@ReadingConverter` hoặc `@WritingConverter`.
3. Override `userConverters()`.
4. Trả về danh sách converter cần đăng ký.
5. Để Spring Data JDBC sử dụng cấu hình đó khi khởi tạo mapping infrastructure.

Đây là lựa chọn phù hợp khi ứng dụng đã có một class cấu hình kế thừa `AbstractJdbcConfiguration`.

### 3.1. Không cần khai báo converter thành bean riêng chỉ để đăng ký

Các converter trong ví dụ là object không có dependency khác, vì vậy có thể khởi tạo trực tiếp trong `List.of(...)`. Việc thêm `@Component` vào converter tự nó không đảm bảo converter được đưa vào `JdbcCustomConversions`.

Điều quan trọng là converter phải có mặt trong danh sách được đăng ký với Spring Data JDBC. Nếu converter cần dependency, có thể tổ chức việc tạo converter bằng cấu hình Spring phù hợp, nhưng vẫn phải đưa các instance đó vào `JdbcCustomConversions`.

### 3.2. Giữ lại cấu hình conversion mặc định

Khi dùng `AbstractJdbcConfiguration`, nên tận dụng cơ chế `userConverters()` thay vì tự tạo một conversion service hoàn toàn mới. Cấu hình nền của Spring Data JDBC còn cung cấp các chuyển đổi mặc định cho những kiểu JDBC được hỗ trợ.

Không tự thay thế toàn bộ conversion infrastructure chỉ để thêm một value object. Mục tiêu là bổ sung converter ứng dụng vào hệ thống mapping hiện có.

## 4. Đăng ký trực tiếp bằng `JdbcCustomConversions`

Nếu ứng dụng không override `userConverters()`, có thể khai báo bean `JdbcCustomConversions` và truyền danh sách converter tùy chỉnh vào constructor:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.core.convert.JdbcCustomConversions;

@Configuration
public class JdbcConversionConfiguration {

    @Bean
    JdbcCustomConversions jdbcCustomConversions() {
        return new JdbcCustomConversions(List.of(
            new EmailAddressToStringConverter(),
            new StringToEmailAddressConverter()
        ));
    }
}
~~~

`JdbcCustomConversions` là cấu hình conversion dành cho Spring Data JDBC. Bean này được dùng khi framework xây dựng `JdbcConverter` và mapping infrastructure.

### 4.1. Chọn một đường đăng ký phù hợp

Hai cách cấu hình có thể được hiểu như sau:

| Cách | Cách thực hiện | Khi phù hợp |
|---|---|---|
| `userConverters()` | Override method trong `AbstractJdbcConfiguration` | Ứng dụng dùng class cấu hình nền của Spring Data JDBC |
| Bean `JdbcCustomConversions` | Tự khai báo bean với danh sách converter | Ứng dụng quản lý bean conversion trực tiếp |

Nếu đã override `userConverters()` trong `AbstractJdbcConfiguration`, không cần khai báo thêm một bean `JdbcCustomConversions` thứ hai chỉ để đăng ký cùng converter. Nếu vừa khai báo cả hai, cần xem cấu hình nào thực sự được Spring sử dụng; nhiều bean cùng loại có thể gây xung đột hoặc khiến cấu hình không rõ ràng.

Với Spring Boot, hãy kiểm tra cấu hình auto-configuration của phiên bản đang dùng trước khi tự khai báo bean. Nếu ứng dụng đã có một bean `JdbcCustomConversions`, hãy mở rộng đúng điểm cấu hình mà ứng dụng đang sử dụng thay vì tạo một conversion infrastructure cạnh tranh.

### 4.2. Import quan trọng

Một số class thường xuất hiện trong cấu hình:

| Class | Package |
|---|---|
| `JdbcCustomConversions` | `org.springframework.data.jdbc.core.convert` |
| `AbstractJdbcConfiguration` | `org.springframework.data.jdbc.repository.config` |
| `ReadingConverter` | `org.springframework.data.convert` |
| `WritingConverter` | `org.springframework.data.convert` |
| `Converter` | `org.springframework.core.convert.converter` |

Tên package là một phần của API; hãy dùng import từ đúng Spring Data JDBC version của dự án.

## 5. Ví dụ hoàn chỉnh: lưu `EmailAddress` trong cột VARCHAR

Ví dụ này ghép domain type, hai converter và cấu hình đăng ký.

### 5.1. Schema

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email_address VARCHAR(255) NOT NULL
);
~~~

Schema chỉ lưu email dưới dạng chuỗi. Không cần tạo một bảng riêng cho `EmailAddress`, vì đây là value object scalar thuộc `Customer`.

### 5.2. Value object

~~~java
public record EmailAddress(String value) {

    public EmailAddress {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Email address không được để trống"
            );
        }
        value = value.trim();
    }
}
~~~

Ví dụ validation trên chỉ kiểm tra giá trị không rỗng và chuẩn hóa khoảng trắng. Hệ thống thực tế có thể cần quy tắc email phù hợp với nghiệp vụ.

### 5.3. Aggregate root

~~~java
@Table("customers")
public class Customer {

    @Id
    private Long id;

    @Column("email_address")
    private EmailAddress email;

    public Customer(EmailAddress email) {
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public EmailAddress getEmail() {
        return email;
    }
}
~~~

### 5.4. Hai converter

~~~java
@WritingConverter
public class EmailAddressToStringConverter
        implements Converter<EmailAddress, String> {

    @Override
    public String convert(EmailAddress source) {
        return source.value();
    }
}
~~~

~~~java
@ReadingConverter
public class StringToEmailAddressConverter
        implements Converter<String, EmailAddress> {

    @Override
    public EmailAddress convert(String source) {
        return new EmailAddress(source);
    }
}
~~~

### 5.5. Cấu hình

~~~java
@Configuration
public class JdbcConfiguration extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
            new EmailAddressToStringConverter(),
            new StringToEmailAddressConverter()
        );
    }
}
~~~

### 5.6. Repository

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

### 5.7. Lưu và đọc

~~~java
Customer customer = new Customer(
    new EmailAddress("dev@example.com")
);

Customer saved = customerRepository.save(customer);

Customer loaded = customerRepository.findById(saved.getId())
    .orElseThrow();

EmailAddress email = loaded.getEmail();
System.out.println(email.value());
~~~

Khi lưu, converter writing chuyển `EmailAddress` thành `String` để ghi cột `email_address`. Khi đọc, converter reading tạo lại `EmailAddress` từ chuỗi trong database.

## 6. Đăng ký converter cho kiểu enum hoặc mã lưu trữ riêng

Converter không chỉ dùng cho value object dạng String. Ví dụ domain có enum:

~~~java
public enum OrderStatus {
    DRAFT(10),
    SUBMITTED(20),
    CANCELLED(90);

    private final int code;

    OrderStatus(int code) {
        this.code = code;
    }

    public int code() {
        return code;
    }

    public static OrderStatus fromCode(int code) {
        for (OrderStatus status : values()) {
            if (status.code == code) {
                return status;
            }
        }
        throw new IllegalArgumentException(
            "Order status code không hợp lệ: " + code
        );
    }
}
~~~

Nếu schema lưu `status_code` dưới dạng `INTEGER`, có thể viết converter:

~~~java
@WritingConverter
public class OrderStatusToIntegerConverter
        implements Converter<OrderStatus, Integer> {

    @Override
    public Integer convert(OrderStatus source) {
        return source.code();
    }
}
~~~

~~~java
@ReadingConverter
public class IntegerToOrderStatusConverter
        implements Converter<Integer, OrderStatus> {

    @Override
    public OrderStatus convert(Integer source) {
        return OrderStatus.fromCode(source);
    }
}
~~~

Đăng ký hai converter này cùng cách như cặp `EmailAddress` ở trên.

Đây là lựa chọn hữu ích khi database cần lưu mã ổn định, độc lập với tên enum Java. Nếu dùng ordinal của enum, việc đổi thứ tự khai báo có thể làm dữ liệu cũ mang ý nghĩa khác; mã tường minh giúp tránh phụ thuộc vào vị trí phần tử.

## 7. Chọn đúng chiều converter và tránh mơ hồ

Spring Data cần phân biệt một converter dùng khi đọc hay khi ghi. Điều này đặc biệt quan trọng khi cả kiểu nguồn và đích đều là kiểu đơn giản.

Ví dụ:

~~~java
Converter<String, EmailAddress>
Converter<EmailAddress, String>
~~~

Nếu không đánh dấu chiều, framework có thể không suy ra ý định một cách rõ ràng trong một số trường hợp. Hãy dùng:

- `@ReadingConverter` cho `String -> EmailAddress`.
- `@WritingConverter` cho `EmailAddress -> String`.

Không đánh dấu ngược chiều. Nếu một converter đọc bị gắn `@WritingConverter`, framework có thể tìm nó ở đường ghi và không tìm được converter cần thiết khi đọc.

### 7.1. Không đăng ký hai converter cạnh tranh cho cùng cặp kiểu

Tránh tạo nhiều converter có cùng source/target và cùng chiều nhưng cho kết quả khác nhau. Khi có nhiều lựa chọn, việc chọn converter có thể trở nên khó hiểu hoặc gây lỗi khởi tạo/chuyển đổi.

Nếu có hai quy tắc biểu diễn khác nhau, hãy dùng kiểu domain riêng hoặc tách rõ cấu hình theo context thay vì đăng ký các converter cạnh tranh toàn cục.

### 7.2. Converter nên tập trung vào chuyển đổi

Converter nên thực hiện chuyển đổi xác định giữa hai kiểu. Tránh đưa vào converter:

- Truy vấn repository hoặc gọi database.
- Gọi HTTP/service bên ngoài.
- Quy tắc nghiệp vụ phụ thuộc trạng thái aggregate.
- Logic cần transaction hoặc quyền người dùng.

Converter được gọi trong quá trình mapping persistence. Nếu nó thực hiện I/O hoặc phụ thuộc context bên ngoài, việc đọc/ghi entity sẽ khó dự đoán và khó kiểm thử.

## 8. Converter khác gì với `@Column` và `@MappedCollection`?

Ba cơ chế giải quyết ba vấn đề khác nhau:

| Cơ chế | Vai trò |
|---|---|
| `@Column("email_address")` | Ánh xạ property Java sang tên cột database |
| `@MappedCollection(idColumn = "order_id")` | Mô tả quan hệ collection con trong aggregate |
| Converter | Chuyển đổi giá trị giữa kiểu domain và kiểu JDBC |

Ví dụ:

~~~java
@Column("email_address")
private EmailAddress email;
~~~

`@Column` cho biết property `email` nằm ở cột `email_address`. Nó không tự chuyển `EmailAddress` thành `String`. Converter mới thực hiện phần chuyển kiểu.

Tương tự, converter không khai báo quan hệ giữa `PurchaseOrder` và `OrderLine`. Quan hệ đó vẫn cần mapping aggregate như `@MappedCollection`.

## 9. Converter không thay thế schema hoặc migration

Converter thay đổi cách Java biểu diễn giá trị khi đọc/ghi, nhưng không tự sửa schema database.

Ví dụ:

- Nếu converter ghi `String`, cột đích phải có kiểu tương thích như `VARCHAR`.
- Nếu converter ghi `Integer`, cột cần kiểu số phù hợp.
- Nếu đổi từ lưu enum dạng tên sang lưu mã số, cần migration dữ liệu và schema nếu cần.
- Nếu thay đổi format JSON hoặc chuỗi ngày, dữ liệu cũ cần được xử lý tương thích.

Không chỉ thêm converter rồi giả định dữ liệu hiện tại tự chuyển sang format mới. Converter reading phải hiểu format đang có; converter writing phải ghi đúng format mà schema và ứng dụng mong đợi.

### 9.1. Thay đổi format có thể cần chuyển đổi dữ liệu

Giả sử trước đây database lưu:

~~~text
SUBMITTED
~~~

và phiên bản mới muốn lưu:

~~~text
20
~~~

Chỉ đổi converter writing có thể làm các hàng mới dùng số, trong khi hàng cũ vẫn là chuỗi. Converter reading lúc đó phải hỗ trợ cả hai định dạng hoặc dữ liệu cần được migration trước.

Hãy xác định kế hoạch triển khai:

1. Converter reading có hỗ trợ format cũ và mới trong giai đoạn chuyển tiếp không?
2. Phiên bản ứng dụng nào bắt đầu ghi format mới?
3. Khi nào migration dữ liệu hoàn tất?
4. Có cần rollback về phiên bản cũ không?

Converter là một phần của chiến lược tương thích dữ liệu, không phải công cụ migration tự động.

## 10. Kiểm tra converter bằng integration test

Một unit test có thể kiểm tra logic chuyển đổi riêng, nhưng cần integration test để xác nhận Spring Data JDBC thực sự sử dụng converter đã đăng ký.

Ví dụ kiểm tra round-trip:

~~~java
@DataJdbcTest
@Import(JdbcConfiguration.class)
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository customers;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void writesAndReadsEmailAddress() {
        Customer saved = customers.save(
            new Customer(new EmailAddress("dev@example.com"))
        );

        String storedValue = jdbcTemplate.queryForObject(
            "SELECT email_address FROM customers WHERE id = ?",
            String.class,
            saved.getId()
        );

        assertEquals("dev@example.com", storedValue);

        Customer loaded = customers.findById(saved.getId())
            .orElseThrow();

        assertEquals(
            new EmailAddress("dev@example.com"),
            loaded.getEmail()
        );
    }
}
~~~

Ví dụ giả định `JdbcConfiguration` là cấu hình được import trong test slice và database test đã có schema. Điều chỉnh package, constructor, ID generation và cấu hình test theo dự án.

Test này xác nhận cả hai hướng:

- Giá trị Java `EmailAddress` được ghi thành chuỗi đúng trong database.
- Chuỗi trong database được đọc thành `EmailAddress`.

### 10.1. Kiểm tra dữ liệu cũ không hợp lệ

Nếu converter reading tạo value object có validation, hãy kiểm tra dữ liệu lỗi:

~~~java
jdbcTemplate.update(
    "INSERT INTO customers(email_address) VALUES (?)",
    ""
);

assertThrows(
    RuntimeException.class,
    () -> customers.findAll()
);
~~~

Loại exception cụ thể có thể được Spring Data JDBC bọc lại tùy đường gọi và phiên bản. Trong test thực tế, hãy kiểm tra exception phù hợp với hợp đồng ứng dụng thay vì phụ thuộc một lớp exception nội bộ không ổn định.

### 10.2. Kiểm tra schema và kiểu JDBC

Khi converter trả về kiểu số hoặc thời gian, cần kiểm tra driver bind đúng JDBC type:

- `Integer` hoặc `Long` có khớp kiểu cột không?
- `BigDecimal` có precision/scale phù hợp không?
- `LocalDateTime` có khớp kiểu timestamp và timezone semantics không?
- Enum code có nằm trong tập giá trị được hỗ trợ không?

Nếu kiểu JDBC cần chỉ định rõ ràng, hãy dùng cơ chế hỗ trợ kiểu JDBC của phiên bản Spring Data JDBC đang dùng và xác nhận bằng integration test. Không ép kiểu bằng cách nối chuỗi SQL hoặc cast tùy tiện trong converter.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Lưu value object thất bại | Chưa có writing converter | Đăng ký converter domain sang kiểu store |
| Đọc entity thất bại | Thiếu reading converter | Đăng ký converter kiểu store sang domain |
| Converter không được gọi | Chỉ tạo class hoặc gắn `@Component`, chưa đăng ký với `JdbcCustomConversions` | Thêm vào `userConverters()` hoặc bean `JdbcCustomConversions` |
| Framework dùng sai chiều | Đánh dấu nhầm annotation | Dùng `@ReadingConverter` và `@WritingConverter` đúng hướng |
| Không biết converter nào được chọn | Có nhiều converter cạnh tranh cùng cặp kiểu | Loại bỏ đăng ký trùng và làm rõ source/target |
| Cột database không tương thích | Kiểu đích converter không khớp schema | Chọn kiểu lưu trữ phù hợp và kiểm tra JDBC type |
| Dữ liệu cũ không đọc được | Format lưu trữ đã thay đổi | Viết converter tương thích tạm thời hoặc migration dữ liệu |
| Converter ném lỗi khi đọc | Dữ liệu store không hợp lệ với domain | Xác định quy tắc validation và xử lý dữ liệu lỗi |
| Chỉ kiểm tra unit test converter | Chưa xác nhận Spring Data JDBC đăng ký và gọi converter | Viết integration test qua repository |
| Hai bean conversions xung đột | Vừa override `userConverters()` vừa khai báo bean riêng | Chọn một đường đăng ký nhất quán |

## 12. Quy trình thêm converter mới

Khi cần hỗ trợ một kiểu domain mới, có thể làm theo trình tự:

1. **Xác định kiểu lưu trữ:** giá trị sẽ nằm trong `VARCHAR`, `INTEGER`, `DECIMAL`, `TIMESTAMP` hay kiểu khác?
2. **Xác định hai chiều:** ứng dụng có cần cả đọc và ghi không?
3. **Viết converter:** triển khai `Converter<S, T>` cho từng chiều cần thiết.
4. **Đánh dấu hướng:** thêm `@ReadingConverter` hoặc `@WritingConverter`.
5. **Đăng ký:** override `userConverters()` hoặc khai báo `JdbcCustomConversions`.
6. **Kiểm tra mapping:** bảo đảm property và cột có kiểu tương thích.
7. **Kiểm tra round-trip:** lưu aggregate, đọc lại và kiểm tra giá trị domain.
8. **Kiểm tra dữ liệu cũ:** xác định cách xử lý nếu format database đã tồn tại khác format mới.

## 13. Bài tập thực hành

### Bài 1 — Value object dạng String

1. Tạo `EmailAddress` dưới dạng record.
2. Viết `EmailAddressToStringConverter`.
3. Viết `StringToEmailAddressConverter`.
4. Đăng ký qua `userConverters()`.
5. Lưu và đọc một `Customer` qua repository.

### Bài 2 — So sánh hai cách đăng ký

1. Tạo một cấu hình dùng `AbstractJdbcConfiguration`.
2. Đăng ký converter qua `userConverters()`.
3. Tạo một cấu hình thử nghiệm khác dùng bean `JdbcCustomConversions`.
4. Xác nhận mỗi application context chỉ có cấu hình conversion phù hợp.
5. Giải thích vì sao không nên đăng ký trùng cùng converter.

### Bài 3 — Enum lưu bằng mã số

1. Tạo enum `OrderStatus` với mã số ổn định.
2. Viết converter đọc `Integer` thành enum.
3. Viết converter ghi enum thành `Integer`.
4. Đăng ký cả hai chiều.
5. Kiểm tra trường hợp database chứa mã không hợp lệ.

### Bài 4 — Tương thích dữ liệu

1. Lưu trạng thái dưới dạng chuỗi ở phiên bản đầu.
2. Thiết kế converter reading có thể đọc format cũ và format mới.
3. Xác định thời điểm phiên bản mới bắt đầu ghi format mới.
4. Viết kế hoạch migration các hàng cũ.
5. Kiểm tra khả năng đọc sau migration.

## 14. Kết luận

Spring Data JDBC sử dụng converter để chuyển giá trị giữa kiểu domain và kiểu dữ liệu mà JDBC lưu trữ. `@WritingConverter` đánh dấu chiều domain sang store; `@ReadingConverter` đánh dấu chiều store sang domain. Với một value object scalar, thường cần cả hai converter để hỗ trợ lưu và đọc.

Đăng ký converter bằng cách override `userConverters()` trong `AbstractJdbcConfiguration`, hoặc cung cấp bean `JdbcCustomConversions` trong cấu hình do ứng dụng quản lý. Hai cách cùng phục vụ conversion infrastructure của Spring Data JDBC; hãy chọn một điểm đăng ký rõ ràng và tránh tạo các bean hoặc converter cạnh tranh.

Converter chỉ xử lý chuyển đổi giá trị. `@Column` vẫn xác định tên cột, `@MappedCollection` vẫn mô tả collection con, còn schema và migration vẫn phải được quản lý riêng. Hãy xác nhận converter bằng integration test round-trip qua repository để bảo đảm cả chiều ghi và chiều đọc hoạt động với database thực tế.

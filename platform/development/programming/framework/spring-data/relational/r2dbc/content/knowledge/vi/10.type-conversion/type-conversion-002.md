# Chuyển đổi chiều đọc và chiều ghi

## 1. Vì sao cần phân biệt chuyển đổi chiều đọc và chiều ghi?

Ứng dụng Java thường biểu diễn dữ liệu bằng những kiểu gần với ngôn ngữ nghiệp vụ: `EmailAddress`, `Money`, `OrderStatus`, `CustomerId` hoặc một value object riêng. Cơ sở dữ liệu lại lưu dữ liệu theo những kiểu mà hệ quản trị và driver hỗ trợ, chẳng hạn `VARCHAR`, `NUMERIC`, `UUID`, `DATE` hoặc kiểu đặc thù của database.

Khi đọc dữ liệu, ứng dụng cần chuyển giá trị do driver trả về thành kiểu Java mà domain model mong đợi. Khi ghi dữ liệu, ứng dụng cần chuyển thuộc tính Java thành kiểu mà R2DBC driver có thể bind vào câu SQL.

Hai hướng chuyển đổi này có thể dùng hai converter khác nhau:

- **Chiều đọc (reading):** dữ liệu đi từ database vào ứng dụng, tức kiểu do driver trả về được chuyển thành kiểu domain.
- **Chiều ghi (writing):** dữ liệu đi từ ứng dụng xuống database, tức kiểu domain được chuyển thành kiểu mà driver và database chấp nhận.

Trong Spring Data R2DBC, quá trình ánh xạ entity được thực hiện bởi mapping infrastructure của Spring Data Relational. Các custom converter được đăng ký qua `R2dbcCustomConversions`. Annotation `@ReadingConverter` và `@WritingConverter` giúp xác định rõ converter được dùng theo hướng nào.

Phân biệt đúng hai hướng giúp tránh trường hợp một converter bị suy luận sai chiều, kiểu Java không khớp kiểu cột, hoặc ứng dụng đọc được dữ liệu nhưng lại không ghi được (và ngược lại).

## 2. Hai chiều chuyển đổi trong luồng dữ liệu

Có thể hình dung đường đi dữ liệu như sau:

~~~text
                 CHIỀU ĐỌC
Database column
      |
      v
R2DBC Driver
      |
      v
Giá trị kiểu store (String, UUID, ...)
      |
      v
Reading Converter
      |
      v
Kiểu domain Java
      |
      v
Entity / Aggregate

                 CHIỀU GHI
Entity / Aggregate
      |
      v
Kiểu domain Java
      |
      v
Writing Converter
      |
      v
Giá trị kiểu store
      |
      v
R2DBC Driver bind parameter
      |
      v
Database column
~~~

Ví dụ, cột `email_address` có kiểu `VARCHAR`:

- Khi đọc, PostgreSQL R2DBC driver trả về một `String`; ứng dụng muốn nhận `EmailAddress`.
- Khi ghi, entity chứa `EmailAddress`; driver cần nhận một `String` để bind vào cột `VARCHAR`.

Do đó, hai converter cần có hướng khác nhau:

| Hướng | Source type | Target type | Vai trò |
|---|---|---|---|
| Reading | `String` | `EmailAddress` | Tạo value object từ dữ liệu database |
| Writing | `EmailAddress` | `String` | Lấy giá trị lưu trữ từ value object |

Tên reading và writing được xác định theo góc nhìn của ứng dụng: reading là đọc từ store, writing là ghi xuống store.

## 3. Spring Data R2DBC thực hiện mapping ở đâu?

Khi dùng Spring Data R2DBC, repository và `R2dbcEntityTemplate` sử dụng mapping infrastructure để chuyển đổi entity với dữ liệu quan hệ. Thành phần trung tâm là `MappingR2dbcConverter`, phối hợp với mapping context và custom conversions.

### 3.1. Khi ghi entity

Ví dụ ứng dụng gọi:

~~~java
customerRepository.save(customer);
~~~

Quá trình khái quát:

1. Spring Data đọc metadata của entity và các property.
2. Với mỗi property, mapping converter xác định kiểu Java và kiểu dữ liệu cần gửi đến driver.
3. Nếu property cần custom conversion, writing converter chuyển kiểu domain sang kiểu store.
4. Spring Data tạo dữ liệu đầu ra (outbound values) và bind chúng vào câu SQL.
5. R2DBC driver thực hiện thao tác ghi với database.

Converter không tự thực hiện câu SQL. Nó chỉ chuyển đổi giá trị property; phần tạo SQL, bind và thực thi thuộc mapping infrastructure cùng R2DBC driver.

### 3.2. Khi đọc entity

Ví dụ ứng dụng gọi:

~~~java
customerRepository.findById(10L);
~~~

Quá trình khái quát:

1. Spring Data thực hiện truy vấn và nhận hàng dữ liệu từ R2DBC driver.
2. Mapping converter đọc giá trị từng cột.
3. Nếu kiểu Java của property khác kiểu store mà driver trả về, reading converter phù hợp được dùng.
4. Các giá trị đã chuyển đổi được đưa vào constructor hoặc property của entity.
5. Repository phát ra entity qua `Mono` hoặc `Flux`.

Việc đọc dữ liệu là reactive. Publisher mô tả thao tác và được thực thi khi có subscription; converter thường được gọi trong quá trình mapping khi kết quả hàng dữ liệu được xử lý.

### 3.3. Chuyển đổi mặc định và custom conversion

Spring Data và R2DBC driver đã hỗ trợ nhiều kiểu phổ biến như số, chuỗi, ngày giờ, UUID và các kiểu dữ liệu mà dialect/driver tương ứng cung cấp. Không cần tạo converter riêng nếu mapping mặc định đã đáp ứng yêu cầu.

Custom converter phù hợp khi:

- Domain model dùng value object riêng.
- Cột database dùng kiểu đơn giản nhưng ứng dụng muốn kiểu Java giàu ngữ nghĩa hơn.
- Dữ liệu cần được chuẩn hóa khi đọc hoặc ghi.
- Kiểu database đặc thù cần được chuyển sang kiểu Java mà ứng dụng sử dụng.
- Quy tắc chuyển đổi không thể biểu diễn bằng naming hoặc annotation mapping thông thường.

Trước khi viết converter, hãy xác định driver thực sự trả về kiểu Java nào cho cột đó. Cùng một kiểu SQL có thể có cách biểu diễn khác nhau tùy database và R2DBC driver.

## 4. Ví dụ: ánh xạ EmailAddress với cột VARCHAR

Để minh họa hai chiều, ta dùng một value object `EmailAddress`. Trong domain model, email được biểu diễn bằng kiểu riêng để có thể kiểm tra định dạng và tránh truyền chuỗi tùy ý khắp ứng dụng. Trong database, email được lưu dưới dạng `VARCHAR`.

### 4.1. Khai báo value object

~~~java
public record EmailAddress(String value) {

    public EmailAddress {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Email address is required");
        }

        if (!value.contains("@")) {
            throw new IllegalArgumentException("Invalid email address");
        }
    }
}
~~~

Đây là ví dụ kiểm tra tối thiểu để minh họa. Validation email trong ứng dụng thực tế cần theo quy tắc nghiệp vụ và chuẩn định dạng mà hệ thống chấp nhận; việc kiểm tra chuỗi có chứa ký tự `@` không phải một validator đầy đủ.

### 4.2. Entity sử dụng value object

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record Customer(
        @Id Long id,
        String name,
        @Column("email_address") EmailAddress email
) {}
~~~

Property `email` có kiểu `EmailAddress`, còn cột database có tên `email_address` và kiểu `VARCHAR`.

Schema PostgreSQL minh họa:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    email_address VARCHAR(320) NOT NULL UNIQUE
);
~~~

Khi Spring Data lưu hoặc đọc entity Customer, nó cần chuyển đổi giữa `EmailAddress` và kiểu chuỗi mà driver sử dụng cho cột `VARCHAR`.

## 5. Viết converter cho chiều đọc

Chiều đọc đi từ kiểu store sang kiểu domain. Với ví dụ trên, source là `String`, target là `EmailAddress`.

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class EmailAddressReadConverter
        implements Converter<String, EmailAddress> {

    @Override
    public EmailAddress convert(String source) {
        return new EmailAddress(source);
    }
}
~~~

Annotation `@ReadingConverter` đánh dấu converter này được sử dụng khi đọc dữ liệu từ database. Spring Data nhận giá trị kiểu `String` do driver cung cấp và chuyển thành `EmailAddress`.

Converter chỉ nên tập trung vào chuyển đổi. Quy tắc xác thực có thể nằm trong constructor hoặc factory method của value object. Nếu dữ liệu cũ trong database không hợp lệ, việc tạo EmailAddress có thể thất bại; ứng dụng cần quyết định cách xử lý dữ liệu legacy thay vì âm thầm tạo một object không hợp lệ.

Một converter đọc khác có thể chuẩn hóa dữ liệu hoặc xử lý kiểu database đặc thù. Tuy nhiên, việc chuẩn hóa như chuyển chữ thường cần cân nhắc tính bảo toàn dữ liệu và quy tắc so sánh email của hệ thống.

## 6. Viết converter cho chiều ghi

Chiều ghi đi từ kiểu domain sang kiểu store. Với ví dụ trên, source là `EmailAddress`, target là `String`.

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class EmailAddressWriteConverter
        implements Converter<EmailAddress, String> {

    @Override
    public String convert(EmailAddress source) {
        return source.value();
    }
}
~~~

Annotation `@WritingConverter` đánh dấu converter này được sử dụng khi ghi dữ liệu xuống database. Spring Data chuyển value object thành chuỗi trước khi bind vào cột `VARCHAR`.

Converter không nên tự mở connection hoặc thực hiện truy vấn. Nó chỉ nên chuyển đổi giá trị; phần tạo SQL, bind và thực thi thuộc mapping infrastructure cùng R2DBC driver. Nếu một phép chuyển đổi cần gọi database, gọi HTTP hoặc thực hiện I/O, đó thường là dấu hiệu logic đang đặt sai tầng.

### 6.1. Vì sao cần đánh dấu hướng rõ ràng?

Một converter có hai kiểu đơn giản ở hai đầu có thể khiến hệ thống khó suy luận chiều sử dụng nếu không có thông tin bổ sung. Ví dụ `String` và `EmailAddress` là cặp kiểu mà ứng dụng cần chuyển đổi theo hai hướng khác nhau.

Dùng annotation rõ ràng:

- `@ReadingConverter`: chuyển từ kiểu dữ liệu store sang kiểu domain.
- `@WritingConverter`: chuyển từ kiểu domain sang kiểu dữ liệu store.

Không nên đánh dấu converter đọc thành converter ghi hoặc ngược lại chỉ để làm cho lỗi mapping biến mất. Source type và target type phải phản ánh đúng dữ liệu đầu vào và đầu ra của hướng đó.

## 7. Đăng ký custom converters với R2dbcCustomConversions

Định nghĩa converter chưa đủ. Spring Data cần biết các converter đó để sử dụng trong mapping. Với Spring Boot, có thể cung cấp bean `R2dbcCustomConversions` chứa converter và dialect của database.

Ví dụ PostgreSQL:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.r2dbc.convert.R2dbcCustomConversions;
import org.springframework.data.r2dbc.dialect.PostgresDialect;

@Configuration
public class R2dbcConversionConfiguration {

    @Bean
    R2dbcCustomConversions r2dbcCustomConversions() {
        return R2dbcCustomConversions.of(
                PostgresDialect.INSTANCE,
                List.of(
                        new EmailAddressReadConverter(),
                        new EmailAddressWriteConverter()
                )
        );
    }
}
~~~

Dialect phải tương ứng với hệ quản trị cơ sở dữ liệu đang sử dụng. Nếu dùng MySQL, SQL Server hoặc database khác, hãy dùng dialect tương ứng và driver R2DBC phù hợp. Dialect cung cấp thông tin để Spring Data tạo SQL và xử lý những khác biệt giữa các hệ quản trị.

Trong ứng dụng dùng cấu hình R2DBC thủ công qua `AbstractR2dbcConfiguration`, có thể đăng ký converter bằng cách override `getCustomConverters()` trong cấu hình hiện có:

~~~java
@Override
protected List<Object> getCustomConverters() {
    return List.of(
            new EmailAddressReadConverter(),
            new EmailAddressWriteConverter()
    );
}
~~~

Chọn một cách đăng ký phù hợp với cấu hình ứng dụng. Không khai báo nhiều nguồn custom conversion trùng nhau một cách tùy tiện. Nếu Spring Boot đã auto-configure connection và mapping, bean `R2dbcCustomConversions` thường là cách tích hợp phù hợp; nếu tự quản lý cấu hình R2DBC, dùng extension point của `AbstractR2dbcConfiguration`.

## 8. Sử dụng converter qua ReactiveCrudRepository

Sau khi converter được đăng ký, repository có thể sử dụng entity như bình thường:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
~~~

Khi ghi:

~~~java
Customer customer = new Customer(
        null,
        "An Nguyen",
        new EmailAddress("an@example.test")
);

Mono<Customer> saved = customerRepository.save(customer);
~~~

Spring Data đọc property `email`, áp dụng writing converter để chuyển `EmailAddress` thành `String`, sau đó bind giá trị chuỗi vào cột `email_address`.

Khi đọc:

~~~java
Mono<Customer> customer = customerRepository.findById(10L);
~~~

Spring Data nhận chuỗi từ cột `email_address`, áp dụng reading converter để tạo `EmailAddress`, rồi đưa object đó vào Customer.

Tầng service không cần gọi converter trực tiếp. Việc chuyển đổi được thực hiện trong quá trình mapping entity của repository.

## 9. Đăng ký converter theo đúng chiều và đúng kiểu

Khi tạo custom converter, hãy ghi rõ ba yếu tố:

1. **Source type:** kiểu dữ liệu thực tế converter nhận.
2. **Target type:** kiểu dữ liệu converter trả về.
3. **Direction:** dữ liệu đang đi từ database vào ứng dụng hay từ ứng dụng xuống database.

Bảng ví dụ:

| Nhu cầu | Reading converter | Writing converter |
|---|---|---|
| Email value object ↔ VARCHAR | `String → EmailAddress` | `EmailAddress → String` |
| Mã đơn hàng riêng ↔ VARCHAR | `String → OrderCode` | `OrderCode → String` |
| Mã trạng thái riêng ↔ VARCHAR | `String → OrderStatus` | `OrderStatus → String` |
| Kiểu Java biểu diễn UUID riêng ↔ UUID | Kiểu driver trả về → domain ID | Domain ID → kiểu driver nhận |

Ví dụ, nếu `OrderCode` là record bao quanh chuỗi, reading converter nhận String và tạo OrderCode; writing converter lấy chuỗi từ OrderCode. Không nên tạo converter ngược chiều rồi mong Spring tự đoán ý nghĩa nghiệp vụ.

### 9.1. Đừng nhầm kiểu Java của property với kiểu database

Property Java có thể là `EmailAddress`, nhưng database column vẫn là `VARCHAR`. Khi chọn converter, source của reading converter phải là kiểu Java mà R2DBC driver trả về cho cột đó, không phải tên kiểu SQL viết trong DDL.

Ví dụ PostgreSQL có kiểu `UUID` và driver có thể trả về `java.util.UUID`. Nếu domain model dùng `CustomerId`, converter có thể có hướng:

- Reading: `UUID → CustomerId`.
- Writing: `CustomerId → UUID`.

Cần kiểm tra kiểu trả về thực tế của driver và dialect. Không nên giả định mọi driver đều biểu diễn một SQL type theo cùng một Java type.

### 9.2. Converter không thay thế schema migration

Converter xác định cách chuyển giá trị ở tầng ứng dụng. Nó không tự thay đổi kiểu cột, thêm constraint hoặc chuyển dữ liệu cũ trong database.

Nếu đổi cột từ `VARCHAR` sang `UUID`, cần migration tương ứng và cần xác định dữ liệu hiện có có thể chuyển đổi hay không. Converter mới chỉ hoạt động đúng khi schema, driver và dữ liệu đã phù hợp.

## 10. Những trường hợp cần chuyển đổi phức tạp hơn một cột

Converter dạng `Converter<S, T>` phù hợp khi một giá trị đầu vào được chuyển thành một giá trị đầu ra, ví dụ String thành EmailAddress. Nhưng một số domain object được cấu thành từ nhiều cột.

Ví dụ địa chỉ có thể được lưu trong ba cột:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    street VARCHAR(200),
    city VARCHAR(100),
    postal_code VARCHAR(20)
);
~~~

Một converter scalar từ String sang Address không thể tự đọc cả ba cột chỉ từ một giá trị String. Trong trường hợp này, có thể dùng mapping value object phù hợp như `@Embedded`, một custom row mapping, projection hoặc truy vấn chuyên biệt.

Với `DatabaseClient`, có thể đọc nhiều cột trong callback:

~~~java
databaseClient.sql("""
        SELECT street, city, postal_code
        FROM customers
        WHERE id = :id
        """)
    .bind("id", customerId)
    .map((row, metadata) -> new Address(
            row.get("street", String.class),
            row.get("city", String.class),
            row.get("postal_code", String.class)
    ))
    .one();
~~~

Callback trên chủ động tạo Address từ nhiều cột. Đây là row mapping của truy vấn, khác với converter scalar được áp dụng cho một property trong entity mapping.

Nếu cần chuyển đổi cả một hàng thành kiểu domain phức tạp trong repository mapping, hãy xem xét khả năng row-level converter và API mapping của phiên bản Spring Data R2DBC đang dùng. Không nên cố ép một chuyển đổi nhiều cột vào converter một giá trị.

## 11. Phân biệt entity mapping với DatabaseClient mapping thủ công

Custom conversions được sử dụng trong mapping infrastructure của Spring Data, chẳng hạn repository và `R2dbcEntityTemplate`. Nhưng `DatabaseClient` là API cấp thấp cho phép lập trình viên tự định nghĩa cách đọc kết quả.

Ví dụ:

~~~java
databaseClient.sql("""
        SELECT email_address
        FROM customers
        WHERE id = :id
        """)
    .bind("id", customerId)
    .map((row, metadata) -> row.get("email_address", String.class))
    .one();
~~~

Callback này yêu cầu driver trả về `String` và publisher có kiểu `Mono<String>`. Nó không tự động biến String thành EmailAddress chỉ vì ứng dụng đã đăng ký converter cho entity mapping.

Nếu muốn kết quả là EmailAddress, có thể chuyển đổi tường minh:

~~~java
databaseClient.sql("""
        SELECT email_address
        FROM customers
        WHERE id = :id
        """)
    .bind("id", customerId)
    .map((row, metadata) -> new EmailAddress(
            row.get("email_address", String.class)
    ))
    .one();
~~~

Hoặc dùng API mapping entity phù hợp nếu mục tiêu là đọc một entity đã có metadata. Khi dùng `DatabaseClient`, hãy chủ động xác định kiểu đọc, nullability và cách ánh xạ kết quả.

## 12. Xử lý null và dữ liệu không hợp lệ

Database có thể chứa `NULL`, trong khi domain object có thể yêu cầu giá trị bắt buộc. Cần phân biệt:

- Cột có thể null theo schema.
- Property Java có cho phép null hay không.
- Constructor hoặc value object có chấp nhận null hay không.
- Converter có được gọi với null hay mapping infrastructure xử lý null trước đó.

Không nên giả định `convert(null)` luôn được gọi. Spring ConversionService và mapping infrastructure thường xử lý null riêng; converter thông thường nên tập trung chuyển đổi một giá trị không null. Hãy kiểm tra nullability của property, kiểu Java và constraint database.

Với giá trị bắt buộc, nên đặt `NOT NULL` ở database và kiểm tra ở domain model. Với giá trị tùy chọn, dùng kiểu tham chiếu có thể null hoặc mô hình optional phù hợp với quy ước của ứng dụng. Không dùng kiểu primitive như `long` nếu cột có thể trả về NULL.

Dữ liệu legacy có thể không còn hợp lệ theo quy tắc mới. Ví dụ một cột email chứa chuỗi rỗng hoặc sai định dạng sẽ làm constructor EmailAddress ném exception khi đọc. Cần có kế hoạch migration hoặc xử lý dữ liệu không hợp lệ rõ ràng; không nên âm thầm thay bằng giá trị giả khiến domain model sai.

## 13. Chuyển đổi có mất thông tin và yêu cầu round-trip

Không phải mọi cặp reading/writing converter đều là phép nghịch đảo hoàn hảo. Một converter có thể chuẩn hóa dữ liệu, làm tròn số hoặc loại bỏ thông tin không được lưu trong database.

Ví dụ:

- Reading converter chuyển chuỗi email thành value object có chuẩn hóa.
- Writing converter chuyển value object thành chuỗi canonical.
- Một kiểu domain có nhiều trường nhưng chỉ lưu một phần trong cột sẽ không thể khôi phục đầy đủ khi đọc.

Với dữ liệu cần bảo toàn, hãy xác định yêu cầu round-trip:

~~~text
Domain value
    |
    | Writing converter
    v
Store value
    |
    | Reading converter
    v
Domain value sau khi đọc
~~~

Câu hỏi cần trả lời là: giá trị sau khi đọc có bằng giá trị ban đầu theo quy tắc domain hay không? Nếu không, khác biệt đó có chủ đích hay là lỗi mất dữ liệu?

Ví dụ EmailAddress có thể giữ nguyên chuỗi gốc hoặc chuẩn hóa chữ thường. Nếu hệ thống xem email là không phân biệt chữ hoa/chữ thường, việc chuẩn hóa có thể phù hợp. Nhưng nếu cần giữ nguyên chính tả ban đầu để hiển thị hoặc audit, converter không nên tự thay đổi dữ liệu.

## 14. Lỗi thường gặp khi chuyển đổi chiều đọc và chiều ghi

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Đọc entity thất bại với lỗi không chuyển đổi được kiểu | Thiếu reading converter hoặc source type không khớp kiểu driver trả về | Kiểm tra kiểu Java từ Row và đăng ký converter đọc |
| Lưu entity thất bại khi bind property | Thiếu writing converter hoặc target type không được driver hỗ trợ | Tạo converter từ domain type sang store type được hỗ trợ |
| Converter chạy sai chiều | Thiếu hoặc gắn nhầm annotation direction | Dùng `@ReadingConverter` và `@WritingConverter` đúng ý nghĩa |
| Không tìm thấy custom converter | Chưa đăng ký trong R2dbcCustomConversions hoặc bean cấu hình không được nạp | Kiểm tra cấu hình R2DBC và custom conversions bean |
| Có nhiều converter cùng source/target gây mơ hồ | Định nghĩa trùng hoặc thiếu thông tin direction | Thu hẹp converter và đánh dấu chiều rõ ràng |
| Đọc được nhưng ghi không được | Chỉ có reading converter | Bổ sung writing converter tương ứng nếu cần lưu |
| Ghi được nhưng đọc không được | Chỉ có writing converter | Bổ sung reading converter tương ứng nếu cần đọc |
| Lỗi chỉ xảy ra với NULL | Giả định converter nhận null hoặc property không phù hợp nullability | Kiểm tra schema, kiểu Java và xử lý null ở mapping/domain |
| Repository hoạt động nhưng DatabaseClient không chuyển domain type | Callback DatabaseClient đang map thủ công sang kiểu khác | Tạo object trong callback hoặc dùng entity mapping API |
| Lỗi khi đọc dữ liệu cũ | Giá trị trong database không đáp ứng validation mới | Làm sạch/migrate dữ liệu hoặc định nghĩa cách xử lý legacy |

### 14.1. Source type không khớp kiểu driver

Ví dụ converter được khai báo `Converter<Long, CustomerId>`, nhưng driver thực tế trả về `Integer` cho một cột số nguyên. Converter không được chọn vì source type không khớp. Cần kiểm tra kiểu thực tế từ driver và schema, sau đó chọn kiểu phù hợp hoặc hỗ trợ các kiểu đầu vào cần thiết một cách tường minh.

Không nên tạo hàng loạt converter cho nhiều kiểu phỏng đoán. Hãy xác nhận database column type, driver và dialect trước.

### 14.2. Thiếu converter ở một chiều

Định nghĩa `String → EmailAddress` không tự động tạo converter `EmailAddress → String`. Hai chiều là hai thao tác riêng. Nếu ứng dụng vừa đọc vừa ghi entity, thường cần cả hai converter.

### 14.3. Converter không được đăng ký

Converter có thể compile nhưng không được Spring Data sử dụng nếu không nằm trong custom conversions mà mapping infrastructure đang dùng. Kiểm tra bean `R2dbcCustomConversions`, dialect, cấu hình auto-configuration và component context. Đừng chỉ dựa vào việc class converter có annotation để kết luận nó đã được đăng ký.

### 14.4. Dùng converter để thực hiện nghiệp vụ hoặc I/O

Converter được gọi trong quá trình mapping và nên thực hiện chuyển đổi nhanh, xác định, không có side effect. Tránh gọi repository, HTTP client, ghi log dữ liệu nhạy cảm hoặc thực hiện thao tác blocking trong converter. Nếu chuyển đổi phụ thuộc vào database khác hoặc trạng thái nghiệp vụ, hãy đưa logic đó lên service.

## 15. Kiểm thử converter theo cả hai hướng

Một converter nên được kiểm tra độc lập và qua database thực tế.

### 15.1. Unit test converter đọc

~~~java
class EmailAddressReadConverterTest {

    private final EmailAddressReadConverter converter =
            new EmailAddressReadConverter();

    @Test
    void shouldCreateEmailAddressFromString() {
        EmailAddress result = converter.convert("an@example.test");

        assertThat(result.value()).isEqualTo("an@example.test");
    }
}
~~~

### 15.2. Unit test converter ghi

~~~java
class EmailAddressWriteConverterTest {

    private final EmailAddressWriteConverter converter =
            new EmailAddressWriteConverter();

    @Test
    void shouldWriteEmailAddressAsString() {
        String result = converter.convert(
                new EmailAddress("an@example.test"));

        assertThat(result).isEqualTo("an@example.test");
    }
}
~~~

Unit test xác nhận logic chuyển đổi thuần, nhưng chưa chứng minh Spring Data đã đăng ký converter hoặc driver hỗ trợ kiểu store tương ứng.

### 15.3. Integration test qua repository

Có thể kiểm tra round-trip bằng database test thực tế:

~~~java
@Test
void shouldSaveAndReadCustomerWithEmailAddress() {
    Customer input = new Customer(
            null,
            "An Nguyen",
            new EmailAddress("an@example.test")
    );

    StepVerifier.create(
            customerRepository.save(input)
                    .flatMap(saved ->
                            customerRepository.findById(saved.id()))
    )
    .assertNext(actual -> {
        assertThat(actual.name()).isEqualTo("An Nguyen");
        assertThat(actual.email())
                .isEqualTo(new EmailAddress("an@example.test"));
    })
    .verifyComplete();
}
~~~

Test này đi qua cả chiều ghi và chiều đọc. Cần chạy với PostgreSQL tương thích, chẳng hạn bằng Testcontainers hoặc database test được quản lý riêng. Một mock repository không kiểm tra được mapping converter hay kiểu bind thực tế của driver.

Ngoài round-trip, có thể kiểm tra riêng từng hướng:

- Insert dữ liệu chuỗi trực tiếp bằng SQL rồi đọc qua repository để kiểm tra reading converter.
- Lưu entity qua repository rồi truy vấn cột bằng DatabaseClient để xác nhận writing converter đã ghi giá trị mong đợi.
- Kiểm tra dữ liệu null, dữ liệu legacy và giá trị không hợp lệ theo quy tắc domain.

## 16. Nguyên tắc thiết kế custom conversion

Khi bổ sung chuyển đổi cho một kiểu domain, có thể áp dụng các nguyên tắc sau:

1. Xác định kiểu Java mà R2DBC driver trả về khi đọc cột.
2. Xác định kiểu mà driver có thể bind khi ghi cột.
3. Viết reading converter từ store type sang domain type.
4. Viết writing converter từ domain type sang store type.
5. Đánh dấu chiều bằng `@ReadingConverter` và `@WritingConverter`.
6. Đăng ký converter trong `R2dbcCustomConversions` với dialect đúng.
7. Dùng repository hoặc `R2dbcEntityTemplate` để kiểm tra entity mapping.
8. Nếu dùng `DatabaseClient` map thủ công, tự chịu trách nhiệm chuyển đổi kết quả.
9. Xác định chính sách null, dữ liệu không hợp lệ và dữ liệu legacy.
10. Kiểm thử cả hai hướng với database và driver thực tế.

Converter nên nhỏ, tập trung vào một kiểu dữ liệu và không phụ thuộc trạng thái bên ngoài. Nếu một chuyển đổi cần nhiều cột, nhiều truy vấn hoặc quyết định nghiệp vụ, hãy chọn cơ chế mapping hoặc service phù hợp hơn.

## 17. Kết luận

Chuyển đổi chiều đọc và chiều ghi là hai phần riêng trong quá trình ánh xạ dữ liệu của Spring Data R2DBC. Reading converter chuyển giá trị do database driver trả về thành kiểu domain Java; writing converter chuyển property domain thành kiểu dữ liệu mà driver có thể bind xuống database.

Spring Data cung cấp `@ReadingConverter`, `@WritingConverter` và `R2dbcCustomConversions` để khai báo, phân biệt và đăng ký những phép chuyển đổi này. Repository và `R2dbcEntityTemplate` sử dụng mapping infrastructure để áp dụng converter trong quá trình đọc và ghi entity. Với `DatabaseClient` ở mức thấp, callback mapping có thể cần chuyển đổi tường minh.

Khi thiết kế custom conversion, hãy xác định chính xác source type, target type, driver, dialect và yêu cầu round-trip. Converter chỉ nên xử lý chuyển đổi dữ liệu thuần; nullability, dữ liệu legacy, schema migration và quy tắc nghiệp vụ cần được quản lý ở đúng tầng. Làm rõ hai chiều ngay từ đầu giúp entity mapping dễ hiểu, nhất quán và ít lỗi hơn.


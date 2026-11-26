# Đăng ký converter qua cơ chế cấu hình của store

## 1. Mục tiêu và phạm vi

Trong chương **Chuyển đổi dữ liệu** của module **Spring Data Commons**, bài này giải quyết một việc cụ thể: đưa converter do ứng dụng viết vào đúng hạ tầng ánh xạ dữ liệu của kho lưu trữ.

Sau bài học, bạn cần có khả năng:

- Phân biệt converter tồn tại trong Spring container với converter đã được mapper của store sử dụng.
- Đăng ký chiều đọc và chiều ghi tại điểm mở rộng của MongoDB, JDBC hoặc R2DBC.
- Giải thích vì sao cấu hình chuyển đổi còn liên quan đến metadata kiểu dữ liệu.
- Kiểm tra biểu diễn đã lưu, dữ liệu đọc lại và tham số truy vấn đi qua đúng đường ánh xạ.
- Chọn cơ chế riêng của store khi cùng một domain model được sử dụng với nhiều công nghệ.

Repository, CRUD và derived query cung cấp giao diện thao tác quen thuộc. Tuy nhiên, việc biến một thuộc tính Java thành BSON, giá trị cột hay kiểu mà driver nhận được thuộc về module store. Một converter dùng được với một mapper không tự động được mọi repository trong ứng dụng sử dụng.

Các ví dụ dùng Java 17 trở lên để biểu diễn value object bằng record. Ba cấu hình store là **những phương án thay thế cho các ứng dụng tương ứng**; mỗi ví dụ giả định đã có dependency, kết nối và phần khởi tạo repository cần thiết của store đó. Khi áp dụng, đối chiếu chữ ký API với phiên bản Spring Data do dự án quản lý.

## 2. Đăng ký converter gồm những mắt xích nào?

Xét một thuộc tính `CustomerCode` trong domain model, nhưng kho dữ liệu lưu nó thành chuỗi:

```text
Chiều ghi:
CustomerCode("CUS-0042")
    -> converter ghi
    -> "CUS-0042"
    -> mapper và driver
    -> giá trị trong kho

Chiều đọc:
giá trị trong kho
    -> driver trả về String
    -> converter đọc
    -> CustomerCode("CUS-0042")
```

Một cấu hình hoàn chỉnh cần nối được ba phần:

1. **Logic chuyển đổi:** triển khai `Converter<S, T>` với cặp kiểu rõ ràng.
2. **Tập chuyển đổi của store:** converter được đưa vào cấu hình mà store sử dụng.
3. **Mapper thực tế:** repository hoặc template phải dùng mapper được tạo từ cấu hình đó.

Chỉ tạo `new CustomerCodeWriteConverter()` trong một service mới hoàn thành phần thứ nhất. Đăng ký nó vào một `DefaultConversionService` riêng cũng chỉ tác động đến nơi sử dụng instance conversion service đó.

Trong Spring Data Commons, `CustomConversions` lưu thông tin chuyển đổi, hỗ trợ truy vấn cặp kiểu và cung cấp `SimpleTypeHolder`. Các store dùng những biến thể như `MongoCustomConversions`, `JdbcCustomConversions` và `R2dbcCustomConversions`. Tập kiểu đơn giản giúp mapper biết kiểu nào có thể xử lý như một giá trị thay vì tiếp tục phân tích các thuộc tính bên trong. Xem [API CustomConversions](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/convert/CustomConversions.html).

Đó là lý do đăng ký ở cấu hình store thường có ý nghĩa rộng hơn việc thêm một hàm vào conversion service bất kỳ.

## 3. Thiết kế một cặp converter có phạm vi hẹp

### 3.1. Value object và hợp đồng lưu trữ

Giả sử mã khách hàng có định dạng ba chữ cái in hoa, dấu gạch ngang và bốn chữ số. Ứng dụng muốn lưu đúng chuỗi này, giữ cả các số 0 ở đầu.

```java
package com.example.data;

import java.util.Objects;

public record CustomerCode(String value) {

    public CustomerCode {
        Objects.requireNonNull(value, "CustomerCode must not be null");

        if (!value.matches("[A-Z]{3}-[0-9]{4}")) {
            throw new IllegalArgumentException(
                    "CustomerCode must have format AAA-0000");
        }
    }
}
```

Biểu diễn lưu trữ được chọn là `String`. Với MongoDB, đó là giá trị chuỗi trong document; với cơ sở dữ liệu quan hệ, đó có thể là cột `VARCHAR(8)`. Thiết kế này khác với chuyển mã thành số vì số sẽ làm mất các số 0 đầu chuỗi.

Trước khi viết converter, cần xác định:

| Quyết định | Hợp đồng của ví dụ |
| --- | --- |
| Kiểu domain | `CustomerCode` |
| Kiểu lưu trữ trung gian | `String` |
| Định dạng | `AAA-0000` |
| Chuẩn hóa khi ghi | Không tự đổi hoa/thường hoặc cắt khoảng trắng |
| Dữ liệu sai định dạng khi đọc | Báo lỗi thay vì âm thầm thay thế |
| Giá trị thiếu hoặc null | Do hợp đồng thuộc tính và mapping xử lý riêng |

Các quyết định này thuộc thiết kế dữ liệu của ứng dụng. Việc đăng ký converter chỉ khiến mapper áp dụng chúng.

### 3.2. Converter ghi

```java
package com.example.data;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public final class CustomerCodeWriteConverter
        implements Converter<CustomerCode, String> {

    @Override
    public String convert(CustomerCode source) {
        return source.value();
    }
}
```

### 3.3. Converter đọc

```java
package com.example.data;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public final class CustomerCodeReadConverter
        implements Converter<String, CustomerCode> {

    @Override
    public CustomerCode convert(String source) {
        return new CustomerCode(source);
    }
}
```

`@WritingConverter` đánh dấu hướng domain sang kiểu lưu trữ; `@ReadingConverter` đánh dấu hướng ngược lại. Các annotation này giúp phân biệt hướng, đặc biệt khi cả kiểu nguồn và đích đều là kiểu store hỗ trợ. **Chúng không tự thực hiện việc đăng ký converter.** Tài liệu MongoDB mô tả rõ yêu cầu đăng ký tường minh và cách phân biệt hướng tại [Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html).

Converter ở đây áp dụng theo **cặp kiểu**, không theo tên thuộc tính. Nó không có nghĩa “chỉ đổi trường tên code”. Nếu một mapper sử dụng cặp chuyển đổi này, những thuộc tính `CustomerCode` phù hợp khác cũng có thể được xử lý tương tự.

Dùng một value object giúp tránh tạo converter `String -> String` rồi vô tình thay đổi nhiều chuỗi không liên quan. Khi hai thuộc tính cùng kiểu Java cần hai định dạng lưu khác nhau, hãy xem xét tách kiểu domain hoặc dùng khả năng chuyển đổi theo thuộc tính mà store và phiên bản đó thực sự hỗ trợ.

Theo hợp đồng của Spring `Converter`, khi được gọi qua hạ tầng chuyển đổi, nguồn truyền vào `convert` không null và implementation cần an toàn khi dùng đồng thời. Hai converter trên không giữ trạng thái thay đổi. Xem [Spring Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html).

Không dựa vào converter này để bắt mọi trường hợp thuộc tính bị thiếu: mapper có thể xử lý null hoặc giá trị vắng mặt trước khi có lời gọi chuyển đổi.

## 4. MongoDB: đăng ký qua configureConverters

### 4.1. Cấu hình Java của store

Với cấu hình kế thừa `AbstractMongoClientConfiguration`, điểm mở rộng là `configureConverters`. Ví dụ dưới đây giả định các lớp nằm trong package `com.example.data`.

```java
package com.example.data;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.config.AbstractMongoClientConfiguration;
import org.springframework.data.mongodb.core.convert.MongoCustomConversions
        .MongoConverterConfigurationAdapter;
import org.springframework.data.mongodb.repository.config.EnableMongoRepositories;

@Configuration
@EnableMongoRepositories(basePackageClasses = CustomerRepository.class)
public class MongoDataConfig extends AbstractMongoClientConfiguration {

    @Override
    protected String getDatabaseName() {
        return "customer_demo";
    }

    @Override
    protected void configureConverters(
            MongoConverterConfigurationAdapter adapter) {

        adapter.registerConverter(new CustomerCodeWriteConverter());
        adapter.registerConverter(new CustomerCodeReadConverter());
    }
}
```

Điểm mở rộng này tham gia quá trình tạo `MongoCustomConversions` của cấu hình cơ sở. Nó phù hợp khi ứng dụng đã chọn cách quản lý hạ tầng MongoDB bằng lớp cấu hình nói trên. Xem [MongoConfigurationSupport.configureConverters](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/config/MongoConfigurationSupport.html).

Phương thức `registerConverter` nhận một implementation của Spring `Converter`; có thể đăng ký từng instance như ví dụ. Xem [MongoConverterConfigurationAdapter](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/convert/MongoCustomConversions.MongoConverterConfigurationAdapter.html).

Ví dụ chỉ tập trung vào đăng ký converter; cấu hình kết nối MongoDB cần được cung cấp theo môi trường triển khai. Không sao chép lớp cấu hình này vào một ứng dụng đang có mapper tùy biến mà chưa xác định mapper nào repository thực sự sử dụng.

### 4.2. Entity và repository minh họa

```java
package com.example.data;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document("customers")
public record Customer(
        @Id String id,
        CustomerCode code,
        String displayName) {
}
```

```java
package com.example.data;

import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface CustomerRepository extends MongoRepository<Customer, String> {

    Optional<Customer> findByCode(CustomerCode code);
}
```

Lưu bằng repository:

```java
Customer saved = repository.save(
        new Customer(
                null,
                new CustomerCode("CUS-0042"),
                "Khách hàng minh họa"));
```

Kết quả mong muốn ở phần dữ liệu nghiệp vụ của document:

```json
{
  "code": "CUS-0042",
  "displayName": "Khách hàng minh họa"
}
```

Đây là phần trích minh họa; document thực tế còn có `_id` và có thể có metadata khác theo cấu hình. Điều cần quan sát là `code` có kiểu chuỗi, thay vì trở thành một document lồng có trường `value`.

Khi đọc lại bằng `findById(saved.id())`, thuộc tính `code` cần được dựng thành `CustomerCode`. Với `findByCode`, kiểm tra riêng việc ánh xạ giá trị tham số sang biểu diễn lưu trữ; khả năng truy vấn phụ thuộc đường thực thi mà module store cung cấp.

### 4.3. Converter cần dependency thì sao?

Nếu converter cần một đối tượng chính sách định dạng bất biến, hãy để Spring tạo đối tượng đó rồi truyền vào converter khi đăng ký. Không dùng `new` nếu cách đó bỏ qua dependency bắt buộc.

Dù được tạo bằng constructor hay bean, converter vẫn cần xuất hiện trong tập converter mà cấu hình store sử dụng. Đồng thời, nên giữ chuyển đổi là một thao tác xác định được từ dữ liệu đầu vào. Các việc như gọi HTTP để tra cứu khách hàng hoặc truy vấn repository khác cần được thiết kế ở tầng nghiệp vụ, thay vì biến mỗi lần đọc thuộc tính thành một luồng I/O khó dự đoán.

## 5. JDBC: thêm converter qua userConverters

Trong ứng dụng dùng `AbstractJdbcConfiguration`, có thể cung cấp converter của ứng dụng bằng `userConverters()`:

```java
package com.example.data;

import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;

@Configuration
public class JdbcDataConfig extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
                new CustomerCodeWriteConverter(),
                new CustomerCodeReadConverter());
    }
}
```

Đây là phần mở rộng chuyển đổi; ứng dụng vẫn cần hạ tầng JDBC như `DataSource` và các bean truy cập dữ liệu theo cách khởi tạo đã chọn.

Trong cách cấu hình này, ưu tiên hook `userConverters()`. Tài liệu JDBC giải thích rằng ghi đè toàn bộ `jdbcCustomConversions()` có thể làm mất phần chuyển đổi được dialect đóng góp nếu ứng dụng tự dựng lại tập conversions không đầy đủ. Xem [JDBC Custom Conversions](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html#jdbc.custom-converters).

Với ví dụ `CustomerCode`, hãy thiết kế cột lưu mã dưới dạng chuỗi phù hợp. Đăng ký converter không tự tạo hoặc thay đổi schema:

```sql
-- Minh họa riêng cột lưu mã, không phải DDL đầy đủ của bảng.
code VARCHAR(8) NOT NULL
```

Nếu cần ràng buộc duy nhất hoặc chỉ mục cho mã khách hàng, các yêu cầu đó vẫn phải được thể hiện trong thiết kế database và migration.

Một lỗi thiết kế thường gặp là converter ghi trả về kiểu driver không nhận được, rồi cho rằng việc đăng ký đã đủ để khắc phục. Cần kiểm tra toàn bộ đường đi: kiểu Java đầu ra, kiểu SQL của cột và khả năng binding của driver. Một kiểu driver riêng của JDBC không tự trở thành kiểu hợp lệ của R2DBC.

## 6. R2DBC: thêm converter qua getCustomConverters

Với `AbstractR2dbcConfiguration`, hook tương ứng là `getCustomConverters()`. Ví dụ giả định đã có driver R2DBC phù hợp và biến môi trường `DEMO_R2DBC_URL` chứa URL kết nối.

```java
package com.example.data;

import io.r2dbc.spi.ConnectionFactories;
import io.r2dbc.spi.ConnectionFactory;
import java.util.List;
import java.util.Objects;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.r2dbc.config.AbstractR2dbcConfiguration;

@Configuration
public class R2dbcDataConfig extends AbstractR2dbcConfiguration {

    @Bean
    @Override
    public ConnectionFactory connectionFactory() {
        String url = Objects.requireNonNull(
                System.getenv("DEMO_R2DBC_URL"),
                "DEMO_R2DBC_URL is required");

        return ConnectionFactories.get(url);
    }

    @Override
    protected List<Object> getCustomConverters() {
        return List.of(
                new CustomerCodeWriteConverter(),
                new CustomerCodeReadConverter());
    }
}
```

Đây là hook được tài liệu [R2DBC Mapping Configuration](https://docs.spring.io/spring-data/relational/reference/r2dbc/mapping.html#r2dbc.mapping.configuration) mô tả. Phần cấu hình cơ sở tạo `R2dbcCustomConversions` để dùng với mapper và mapping context; xem thêm [AbstractR2dbcConfiguration](https://docs.spring.io/spring-data/r2dbc/docs/current/api/org/springframework/data/r2dbc/config/AbstractR2dbcConfiguration.html).

Trong ví dụ này, đầu ra `String` được chọn vì phù hợp với cột chuỗi và giúp dùng lại logic chuyển đổi. Với kiểu riêng như JSON hoặc kiểu hình học do driver cung cấp, cần thiết kế lại cặp kiểu dựa trên driver và dialect thực tế.

Converter vẫn là thao tác đồng bộ được mapper gọi trong pipeline reactive. Không trả `Mono<String>` từ một converter được kỳ vọng tạo giá trị cột `String`, và không gọi `block()` để hoàn thành I/O bên trong converter. Việc cần xử lý bất đồng bộ nên diễn ra trong pipeline nghiệp vụ trước thao tác lưu hoặc sau thao tác đọc.

JDBC và R2DBC có thể cùng lưu vào một schema nhưng sử dụng các mapper và driver khác nhau. Cấu hình converter cho JDBC không đăng ký thay cho R2DBC.

## 7. Chọn đúng cơ chế và phạm vi cấu hình

### 7.1. Các điểm mở rộng không thay thế lẫn nhau

| Nơi cần chuyển đổi | Cơ chế cần xem xét | Điều cần xác minh |
| --- | --- | --- |
| Request parameter hoặc dữ liệu web | ConversionService của tầng web | Controller đang dùng cấu hình nào |
| JSON request/response | Cấu hình Jackson | Serializer/deserializer được ObjectMapper nào dùng |
| MongoDB document | MongoCustomConversions và mapper MongoDB | Template/repository trỏ đến mapper đã cấu hình |
| Dữ liệu Spring Data JDBC | JdbcCustomConversions | Giữ phần chuyển đổi của dialect và driver |
| Dữ liệu Spring Data R2DBC | R2dbcCustomConversions | Đúng dialect, ConnectionFactory và mapper |
| Thuộc tính entity JPA | Jakarta Persistence AttributeConverter | Quy tắc áp dụng của persistence provider |

Hàng JPA cần được hiểu riêng: `jakarta.persistence.AttributeConverter<X, Y>` chuyển đổi thuộc tính entity và giá trị cơ bản biểu diễn cột. Cách áp dụng liên quan đến `@Converter`, `@Convert` hoặc mapping descriptor của Jakarta Persistence. Nó khác với Spring `Converter<S, T>` và không sử dụng các hook MongoDB/JDBC/R2DBC ở trên. Xem [Jakarta Persistence AttributeConverter](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/AttributeConverter.html).

Một ứng dụng có thể cần chuyển đổi cùng một value object ở cả HTTP, JSON và persistence. Khi đó có thể dùng chung quy tắc parse/format trong một thành phần domain thích hợp, còn việc tích hợp phải thực hiện tại từng hạ tầng.

### 7.2. Phối hợp với Spring Boot

Trước khi thêm cấu hình, xác định ứng dụng đang:

1. Kế thừa lớp cấu hình cơ sở của store.
2. Dựa vào Spring Boot auto-configuration.
3. Tự tạo template, mapping context hoặc mapper.
4. Kết hợp nhiều kết nối hoặc nhiều store.

Các ví dụ trong bài ưu tiên trường hợp thứ nhất. Với Spring Boot, việc công bố bean conversions có thể là điểm tùy biến được hỗ trợ tùy store và phiên bản; cần đối chiếu tài liệu auto-configuration của phiên bản đang dùng.

Tránh thêm đồng thời lớp cấu hình cơ sở, một bean conversions riêng và một mapper tự tạo chỉ để thử xem cách nào có hiệu lực. Hãy chọn một luồng khởi tạo rõ ràng rồi xác minh instance sử dụng ở cuối luồng đó.

Nếu tự tạo mapper, cần cấu hình conversions và metadata kiểu dữ liệu theo đúng lifecycle của store trước khi sử dụng. Đưa converter vào một conversion service mà mapper không tham chiếu đến sẽ không thay đổi thao tác repository.

### 7.3. Nhiều store và nhiều mapper

Giả sử `CustomerCode` được lưu thành chuỗi ở cả MongoDB và PostgreSQL:

- Có thể dùng lại hai lớp converter vì hợp đồng đầu vào/đầu ra giống nhau.
- Cần đăng ký độc lập vào từng cấu hình store.
- Cần kiểm tra độc lập từng mapper, kết nối và định dạng lưu trữ.

Nếu MongoDB dùng chuỗi nhưng một store khác cần cấu trúc nhiều trường, chỉ dùng lại phần quy tắc domain thực sự chung. Việc chia sẻ interface repository hoặc kiểu entity không tạo ra cùng một chiến lược ánh xạ.

Một converter theo kiểu thường có phạm vi áp dụng rộng trong mapper được cấu hình. Nếu hai template phải lưu cùng kiểu domain theo hai định dạng khác nhau, cần tách rõ cấu hình và kiểm tra template nào sử dụng tập conversions nào.

## 8. Xác minh converter đã có hiệu lực

Mục tiêu xác minh là chứng minh đường đi từ cấu hình đến dữ liệu, thay vì chỉ chứng minh phương thức `convert` trả đúng kết quả.

### 8.1. Ba mức bằng chứng

| Mức | Cách kiểm tra | Điều chứng minh được |
| --- | --- | --- |
| Logic | Gọi trực tiếp converter với dữ liệu đại diện | Hợp đồng parse/format |
| Hạ tầng | Kiểm tra conversions gắn với mapper thực tế | Cặp kiểu đã được cấu hình ở đúng nơi |
| Tích hợp | Lưu, quan sát dữ liệu thô, đọc lại và truy vấn | Đường persistence cụ thể sử dụng cấu hình mong đợi |

Ví dụ kiểm tra logic, giả định sử dụng JUnit Jupiter:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class CustomerCodeConvertersTest {

    @Test
    void preservesCodeAcrossWriteAndRead() {
        var write = new CustomerCodeWriteConverter();
        var read = new CustomerCodeReadConverter();
        var original = new CustomerCode("CUS-0042");

        assertEquals("CUS-0042", write.convert(original));
        assertEquals(original, read.convert(write.convert(original)));
    }

    @Test
    void rejectsMalformedStoredValue() {
        var read = new CustomerCodeReadConverter();

        assertThrows(IllegalArgumentException.class,
                () -> read.convert("cus-42"));
    }
}
```

Đây là ví dụ để người học thực hành; nó chưa chứng minh cấu hình store đã được nối đúng.

Ở mức hạ tầng, các API như `hasCustomWriteTarget(CustomerCode.class, String.class)` và `hasCustomReadTarget(String.class, CustomerCode.class)` có thể hỗ trợ kiểm tra tập conversions. Cần lấy **instance gắn với mapper đang sử dụng**, vì tạo một tập conversions mới trong bài kiểm tra chỉ chứng minh đối tượng mới đó có converter.

### 8.2. Kịch bản tích hợp tối thiểu

Với cấu hình MongoDB đã chọn, có thể tổ chức kiểm tra như sau:

1. Lưu một khách hàng mới có mã `CUS-0042` qua repository.
2. Dùng collection thô của driver để đọc document theo định danh vừa lưu.
3. Kiểm tra trường `code` có kiểu BSON chuỗi và giá trị chính xác.
4. Đọc lại bằng `findById`, kiểm tra `CustomerCode` được khôi phục.
5. Gọi `findByCode(new CustomerCode("CUS-0042"))` và kiểm tra kết quả.
6. Nạp một bản ghi thô có mã sai định dạng, quan sát lỗi khi đọc qua mapper.

Dùng driver thô ở bước 2 giúp tránh việc đọc dữ liệu đã được mapper chuyển đổi ngược, vốn có thể che mất định dạng thực sự trong kho.

Đối với JDBC hoặc R2DBC, thay bước quan sát document bằng đọc giá trị cột trực tiếp. Mỗi kịch bản cần chạy trên hạ tầng tương ứng; kết quả MongoDB không xác nhận hành vi của JDBC hoặc R2DBC.

Đừng suy rộng từ `save` và `findById` sang mọi loại query. Derived query, truy vấn khai báo, thao tác template, SQL tự bind và driver API có thể đi qua những đường xử lý khác nhau. Đặc biệt, khi tự bind tham số bằng driver hoặc tự viết row mapper, hãy xác định phần chuyển đổi nào bạn đang tự chịu trách nhiệm.

## 9. Chẩn đoán các lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Gọi trực tiếp converter đúng, repository vẫn lỗi | Converter chưa nằm trong cấu hình store được dùng | Kiểm tra luồng tạo conversions và mapper |
| Value object thành cấu trúc lồng | Mapper chưa nhận custom write target hoặc đang dùng mapper khác | Xác minh cặp kiểu và mapper thực tế |
| Ghi được nhưng đọc lỗi | Thiếu converter đọc, sai kiểu nguồn hoặc dữ liệu cũ khác định dạng | Kiểm tra kiểu driver trả về và hợp đồng đọc |
| Đọc bằng định danh được nhưng tìm theo mã không ra | Tham số query chưa có biểu diễn phù hợp | Kiểm tra riêng đường ánh xạ query |
| Nhiều thuộc tính bị đổi ngoài dự kiến | Converter có cặp kiểu quá rộng | Dùng value object hoặc cơ chế theo thuộc tính phù hợp |
| Chuyển đổi kiểu đặc thù bị hỏng sau tùy biến | Tập conversions mới bỏ mất phần của store/dialect | Dùng hook bổ sung hoặc bảo toàn cấu hình nền |
| Chỉ một template hoạt động | Các template dùng mapper khác nhau | Đăng ký ở đúng mapper của từng template |
| Dữ liệu mới đọc được, dữ liệu cũ đọc lỗi | Hợp đồng lưu trữ đã thay đổi | Thiết kế tương thích đọc hoặc migration dữ liệu |

Thứ tự điều tra thực tế nên đi từ store/repository đang sử dụng, đến mapper của nó, tập conversions, cặp kiểu và cuối cùng là giá trị thật do driver trả về. Cách này giúp tránh sửa converter trong khi nguyên nhân nằm ở wiring cấu hình.

## 10. Thay đổi converter là thay đổi hợp đồng dữ liệu

Đăng ký converter mới không tự chuyển đổi các bản ghi đã tồn tại.

Ví dụ, trước đây mã khách hàng được lưu thành `{ "value": "CUS-0042" }` trong một document lồng; nay converter ghi tạo chuỗi `"CUS-0042"`. Hai biểu diễn có kiểu dữ liệu khác nhau. Converter đọc `String -> CustomerCode` không tự đọc được document lồng.

Trước khi đổi biểu diễn, hãy quyết định:

- Có cần đọc cả định dạng cũ và mới trong giai đoạn chuyển tiếp không?
- Có migration để đưa dữ liệu cũ về cùng biểu diễn không?
- Query và index hiện tại có còn khớp kiểu dữ liệu mới không?
- Những ứng dụng khác đọc cùng dữ liệu đã hỗ trợ định dạng mới chưa?
- Tiêu chí nào xác nhận chuyển đổi dữ liệu đã hoàn tất?

Với ví dụ trong bài, hợp đồng mong muốn là:

```text
read(write(CustomerCode("CUS-0042")))
    == CustomerCode("CUS-0042")

stored type
    == chuỗi theo khả năng của store
```

Điều kiện đầu kiểm tra sự nhất quán của hai chiều. Điều kiện thứ hai kiểm tra quyết định ánh xạ thực sự được áp dụng. Nếu converter có chủ đích chuẩn hóa dữ liệu, cần diễn đạt lại điều kiện bằng giá trị chuẩn hóa và kiểm tra cả tác động đến query.

## 11. Bài thực hành

Chọn **một** store bạn đang học và thực hiện tuần tự:

1. Tạo `CustomerCode` cùng cặp converter đọc/ghi ở trên.
2. Đăng ký bằng đúng hook của store đã chọn.
3. Tạo entity và repository phù hợp với store; thêm truy vấn tìm theo mã.
4. Lưu dữ liệu, quan sát trực tiếp biểu diễn trong kho rồi đọc lại qua repository.
5. Kiểm tra mã có số 0 đầu, dữ liệu sai định dạng và thuộc tính bị thiếu theo hợp đồng ứng dụng.
6. Bỏ đăng ký một chiều trong môi trường thực hành, ghi nhận lỗi rồi khôi phục cấu hình.
7. Giải thích converter thuộc mapper nào và tại sao một converter của tầng web không thay thế cấu hình đó.

Bài thực hành đạt yêu cầu khi bạn chỉ ra được **nơi đăng ký**, **mapper sử dụng**, **biểu diễn lưu trữ** và **bằng chứng đọc/ghi qua repository**. Đây là nền tảng để mở rộng hành vi repository mà vẫn tôn trọng khả năng và cơ chế ánh xạ riêng của từng kho dữ liệu.

# Đăng ký converter tùy chỉnh bằng R2dbcCustomConversions

Trong Spring Data R2DBC, dữ liệu của một thuộc tính entity có thể cần được chuyển đổi giữa kiểu Java của miền nghiệp vụ và kiểu mà database/driver hỗ trợ. Ví dụ, ứng dụng có thể muốn biểu diễn mã đơn hàng bằng một value object `OrderCode`, trong khi cột tương ứng trong database chỉ lưu `VARCHAR`. Converter tùy chỉnh giúp Spring Data thực hiện chuyển đổi này khi đọc và ghi entity.

`R2dbcCustomConversions` là nơi đăng ký các converter bổ sung cho cơ chế mapping của Spring Data R2DBC. Khi cấu hình đúng, repository và `R2dbcEntityTemplate` có thể ánh xạ thuộc tính domain sang giá trị lưu trữ và chuyển giá trị đọc được trở lại kiểu domain. Để tránh lỗi chuyển đổi khó phát hiện, cần khai báo rõ chiều đọc/ghi, chọn đúng dialect của database và kiểm thử cả hai chiều.

## 1. Converter giải quyết vấn đề gì?

Giả sử ứng dụng có kiểu `OrderCode` để biểu diễn mã đơn hàng. Mã này có quy tắc định dạng riêng và không nên được truyền quanh ứng dụng như một chuỗi tùy ý.

```java
public record OrderCode(String value) {
    public OrderCode {
        if (value == null || !value.matches("ORD-[0-9]{6}")) {
            throw new IllegalArgumentException("Invalid order code");
        }
    }
}
```

Trong database, cột `order_code` có thể là `VARCHAR(10)`. Khi đó cần hai chiều chuyển đổi:

- **Ghi (writing):** `OrderCode` trong Java thành `String` để bind vào cột database.
- **Đọc (reading):** `String` từ database thành `OrderCode` để entity nhận được kiểu domain.

```text
Ghi entity xuống database

OrderEntity.orderCode: OrderCode
             |
             v
  OrderCodeToStringConverter
             |
             v
       String "ORD-123456"
             |
             v
      R2DBC driver / SQL
             |
             v
       VARCHAR column

Đọc entity từ database

       VARCHAR column
             |
             v
      R2DBC driver / SQL
             |
             v
       String "ORD-123456"
             |
             v
  StringToOrderCodeConverter
             |
             v
OrderEntity.orderCode: OrderCode
```

Converter tập trung quy tắc chuyển kiểu tại một vị trí, thay vì lặp lại `new OrderCode(...)` hoặc `.value()` ở mọi Repository và Service. Nó cũng giúp entity thể hiện kiểu miền nghiệp vụ có ý nghĩa hơn.

## 2. Các thành phần chính

### 2.1. `Converter<S, T>`

Spring sử dụng interface `org.springframework.core.convert.converter.Converter<S, T>` để mô tả phép chuyển đổi từ kiểu nguồn `S` sang kiểu đích `T`.

```java
public interface Converter<S, T> {
    T convert(S source);
}
```

Một converter chỉ thực hiện một chiều. Nếu cần đọc và ghi cho cùng một value object, thường cần hai converter riêng:

| Chiều | Kiểu nguồn | Kiểu đích | Annotation |
|---|---|---|---|
| Ghi | `OrderCode` | `String` | `@WritingConverter` |
| Đọc | `String` | `OrderCode` | `@ReadingConverter` |

Không nên cho rằng đăng ký converter ghi tự động tạo ra converter đọc ngược lại. Hai chiều cần được thiết kế và kiểm thử độc lập.

### 2.2. `@WritingConverter` và `@ReadingConverter`

Hai annotation này chỉ rõ hướng sử dụng converter trong quá trình mapping:

- `@WritingConverter`: chuyển từ kiểu Java/domain sang kiểu được lưu trong database.
- `@ReadingConverter`: chuyển từ kiểu lưu trữ đọc được sang kiểu Java/domain.

Việc khai báo hướng đặc biệt quan trọng khi một trong hai kiểu là kiểu đơn giản như `String`, `Long`, `UUID` hoặc `BigDecimal`. Nếu chỉ dựa vào suy luận kiểu, Spring có thể không xác định được converter được dùng khi đọc hay ghi. Annotation giúp tránh sự mơ hồ.

### 2.3. `R2dbcCustomConversions`

`R2dbcCustomConversions` thuộc package `org.springframework.data.r2dbc.convert`. Nó tập hợp các converter tùy chỉnh cùng những conversion được cung cấp bởi dialect R2DBC đang sử dụng. Spring Data dùng cấu hình này trong mapping context và converter để chuyển thuộc tính entity khi đọc/ghi.

Không nên nhầm `R2dbcCustomConversions` với:

- Jackson `ObjectMapper`, vốn chuyển đổi Java object và JSON.
- Converter của Spring MVC/WebFlux, vốn xử lý dữ liệu HTTP.
- Converter của JDBC, vốn dành cho đường truy cập JDBC.
- Cơ chế bind tham số trực tiếp của R2DBC driver, vốn yêu cầu kiểu dữ liệu driver hỗ trợ.

Một converter được đăng ký trong `R2dbcCustomConversions` chủ yếu phục vụ đường mapping của Spring Data R2DBC. Nó không tự động thay đổi cách Jackson serialize response JSON hoặc cách mọi lời gọi `DatabaseClient` bind tham số thủ công.

## 3. Viết converter cho value object

Ví dụ dùng `OrderCode` để minh họa một kiểu miền nghiệp vụ được lưu bằng `VARCHAR`.

### 3.1. Value object

```java
package com.example.store.order.domain;

public record OrderCode(String value) {

    public OrderCode {
        if (value == null || !value.matches("ORD-[0-9]{6}")) {
            throw new IllegalArgumentException("Invalid order code: " + value);
        }
    }

    @Override
    public String toString() {
        return value;
    }
}
```

Constructor kiểm tra định dạng để mọi `OrderCode` hợp lệ ngay khi được tạo. Quy tắc này cũng được áp dụng khi đọc dữ liệu từ database. Nếu database có dữ liệu cũ không tuân thủ định dạng, converter đọc có thể phát sinh lỗi; cần làm sạch hoặc migration dữ liệu trước khi bật quy tắc mới.

### 3.2. Converter ghi

```java
package com.example.store.order.persistence;

import com.example.store.order.domain.OrderCode;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class OrderCodeWritingConverter
        implements Converter<OrderCode, String> {

    @Override
    public String convert(OrderCode source) {
        return source.value();
    }
}
```

Converter nhận `OrderCode` và trả về chuỗi có thể lưu vào cột `VARCHAR`. Phương thức không truy cập database, không thực hiện I/O và không gọi `.block()`.

### 3.3. Converter đọc

```java
package com.example.store.order.persistence;

import com.example.store.order.domain.OrderCode;
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class OrderCodeReadingConverter
        implements Converter<String, OrderCode> {

    @Override
    public OrderCode convert(String source) {
        return new OrderCode(source);
    }
}
```

Converter đọc nhận giá trị `String` từ driver và tạo value object. Nếu dữ liệu trong database không hợp lệ, constructor `OrderCode` sẽ báo lỗi. Có thể bổ sung xử lý chuyển đổi hoặc exception phù hợp với chính sách dữ liệu của ứng dụng, nhưng không nên âm thầm thay dữ liệu sai thành một mã mặc định.

### 3.4. Entity sử dụng kiểu tùy chỉnh

```java
package com.example.store.order.persistence;

import com.example.store.order.domain.OrderCode;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("orders")
public record OrderEntity(
        @Id Long id,
        @Column("order_code") OrderCode orderCode,
        String status
) {
}
```

Trong entity, thuộc tính `orderCode` có kiểu `OrderCode`. Cột `order_code` vẫn có kiểu lưu trữ `VARCHAR`. Spring Data sử dụng converter đã đăng ký để chuyển đổi ở ranh giới persistence.

## 4. Đăng ký converter bằng `R2dbcCustomConversions`

Khi dùng Spring Boot với cấu hình R2DBC tự động, có thể cung cấp bean `R2dbcCustomConversions` chứa converter của ứng dụng. Ví dụ:

```java
package com.example.store.config;

import com.example.store.order.persistence.OrderCodeReadingConverter;
import com.example.store.order.persistence.OrderCodeWritingConverter;
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.r2dbc.convert.R2dbcCustomConversions;
import org.springframework.data.r2dbc.dialect.DialectResolver;
import org.springframework.data.r2dbc.dialect.R2dbcDialect;

import java.util.List;

@Configuration
public class R2dbcConversionConfiguration {

    @Bean
    R2dbcCustomConversions r2dbcCustomConversions(
            ConnectionFactory connectionFactory) {

        R2dbcDialect dialect = DialectResolver.getDialect(connectionFactory);

        return R2dbcCustomConversions.of(dialect, List.of(
                new OrderCodeWritingConverter(),
                new OrderCodeReadingConverter()
        ));
    }
}
```

Các bước trong cấu hình:

1. Spring cung cấp `ConnectionFactory` đã được cấu hình cho database.
2. `DialectResolver.getDialect(connectionFactory)` xác định dialect phù hợp với driver/database.
3. `R2dbcCustomConversions.of(...)` kết hợp conversion mặc định theo dialect với danh sách converter của ứng dụng.
4. Bean `R2dbcCustomConversions` được Spring Data sử dụng trong mapping entity.

`R2dbcDialect` cung cấp những khác biệt theo hệ quản trị cơ sở dữ liệu, chẳng hạn kiểu dữ liệu và cách bind/đọc một số giá trị. Dùng dialect được phân giải từ `ConnectionFactory` giúp giữ các conversion mặc định phù hợp với driver đang chạy. Không tự chọn dialect PostgreSQL khi ứng dụng thực tế kết nối SQL Server hoặc database khác.

Spring Boot có thể tự cấu hình các thành phần R2DBC dựa trên dependency và thuộc tính `spring.r2dbc.*`. Khi cung cấp bean `R2dbcCustomConversions` riêng, cần để phiên bản Spring Boot/Spring Data quản lý các bean mapping còn lại và tránh khai báo thêm một mapping context hoặc converter trùng lặp nếu không có yêu cầu đặc biệt.

### 4.1. Khai báo danh sách converter ở cấu hình tập trung

Khi có nhiều kiểu miền nghiệp vụ, gom converter vào cùng một cấu hình hoặc một lớp cấu hình chuyên biệt theo module. Ví dụ:

```java
return R2dbcCustomConversions.of(dialect, List.of(
        new OrderCodeWritingConverter(),
        new OrderCodeReadingConverter(),
        new CustomerCodeWritingConverter(),
        new CustomerCodeReadingConverter(),
        new ExternalReferenceWritingConverter(),
        new ExternalReferenceReadingConverter()
));
```

Giữ danh sách converter rõ ràng giúp người bảo trì biết những kiểu domain nào có cách biểu diễn đặc biệt trong database. Không đăng ký hai converter cùng chiều và cùng cặp kiểu nguồn/đích nếu chúng có hành vi khác nhau mà không có quy tắc lựa chọn rõ ràng.

### 4.2. Cấu hình qua `AbstractR2dbcConfiguration`

Một ứng dụng chủ động quản lý cấu hình hạ tầng có thể kế thừa `AbstractR2dbcConfiguration` và override `getCustomConverters()` để cung cấp converter. Ví dụ khái quát:

```java
@Configuration
public class DatabaseConfiguration extends AbstractR2dbcConfiguration {

    @Override
    public ConnectionFactory connectionFactory() {
        // Trả về ConnectionFactory đã cấu hình cho database.
        return createConnectionFactory();
    }

    @Override
    protected List<Object> getCustomConverters() {
        return List.of(
                new OrderCodeWritingConverter(),
                new OrderCodeReadingConverter()
        );
    }
}
```

Đây là hướng cấu hình khi ứng dụng chủ động dùng lớp cấu hình nền của Spring Data R2DBC để quản lý `ConnectionFactory` và hạ tầng liên quan. Trong ứng dụng Spring Boot đã dùng auto-configuration, thường chỉ cần cung cấp bean `R2dbcCustomConversions` như ví dụ trước. Không trộn hai cách một cách máy móc vì có thể tạo cấu hình hạ tầng hoặc bean trùng nhau.

API cụ thể có thể thay đổi giữa các phiên bản Spring Data. Hãy dùng dependency management của Spring Boot và kiểm tra chữ ký phương thức tương ứng với phiên bản dự án khi nâng cấp.

## 5. Converter đọc và ghi phải có hướng rõ ràng

Một cặp converter thường có cùng kiểu lưu trữ ở giữa nhưng ngược chiều:

```java
@WritingConverter
Converter<OrderCode, String>

@ReadingConverter
Converter<String, OrderCode>
```

Không đổi nhầm hai annotation. Nếu đánh dấu converter `String -> OrderCode` là writing, Spring Data có thể diễn giải sai hướng chuyển đổi hoặc không sử dụng converter ở giai đoạn đọc như mong muốn.

### 5.1. Vì sao không chỉ dùng `Converter<OrderCode, String>`?

Converter ghi chỉ giải quyết việc bind entity xuống database. Khi đọc, driver trả về `String`, còn entity yêu cầu `OrderCode`. Nếu không có converter đọc, Spring Data có thể báo lỗi không thể chuyển kiểu hoặc không materialize được entity.

### 5.2. Khi nào một converter là đủ?

Nếu chỉ có thao tác ghi hoặc chỉ có thao tác đọc theo một đường dữ liệu đặc biệt, một converter có thể đủ cho use case đó. Tuy nhiên, entity được dùng cho cả CRUD thường cần cả hai chiều. Cần xác định rõ mọi đường đọc/ghi thực tế thay vì chỉ kiểm tra insert thành công.

### 5.3. Converter có thể nhận diện kiểu đơn giản

Khi converter chuyển giữa một kiểu domain tùy chỉnh và một kiểu đơn giản như `String`, annotation hướng đọc/ghi giúp Spring Data phân loại chính xác. Đừng bỏ annotation chỉ vì generic type có vẻ đã thể hiện hướng chuyển đổi; converter được đăng ký trong hệ thống conversion chung có thể gặp trường hợp suy luận không đủ rõ.

## 6. Những trường hợp sử dụng phổ biến

### 6.1. Value object cho mã định danh nghiệp vụ

Các mã như `OrderCode`, `CustomerNumber`, `InvoiceNumber` hoặc `ProductSku` có thể được biểu diễn bằng class/record riêng để đóng gói định dạng và quy tắc kiểm tra. Converter giúp lưu chúng dưới dạng chuỗi hoặc kiểu scalar mà database hỗ trợ.

Ưu điểm là code nghiệp vụ không phải phân biệt nhiều chuỗi có cùng kiểu Java nhưng ý nghĩa khác nhau. Ví dụ, `OrderCode` không thể bị truyền nhầm vào phương thức cần `CustomerNumber` nếu hai kiểu được định nghĩa riêng.

### 6.2. Kiểu enum có quy tắc lưu trữ riêng

Nếu enum được lưu bằng tên hoặc mã riêng, converter có thể ánh xạ giữa enum và giá trị database. Cần xác định rõ hành vi khi database chứa giá trị chưa có trong phiên bản code hiện tại. Có thể phát lỗi để phát hiện dữ liệu không tương thích hoặc dùng một giá trị `UNKNOWN` nếu nghiệp vụ cho phép; không nên phụ thuộc vào ordinal vì thay đổi thứ tự enum có thể làm sai dữ liệu cũ.

### 6.3. Kiểu dữ liệu đặc thù của database

Một số database có kiểu riêng như JSON/JSONB, array, enum native hoặc kiểu thời gian đặc biệt. Driver R2DBC có thể cung cấp kiểu Java riêng để bind và đọc các giá trị này. Converter có thể chuyển giữa kiểu domain và kiểu driver tương ứng.

Trước khi viết converter, hãy kiểm tra driver đã hỗ trợ kiểu đó hay chưa và dialect có conversion mặc định hay không. Nếu driver đã cung cấp mapping phù hợp, không cần thêm converter trùng chức năng. Với JSON, cần phân biệt chuyển đổi giữa domain object và kiểu JSON của driver với serialize/deserialize HTTP JSON của Jackson.

### 6.4. Giá trị tiền tệ hoặc kiểu ghép

Một value object `Money` thường gồm số tiền và đơn vị tiền tệ. Nếu database lưu cả hai thuộc tính trong hai cột riêng, một converter scalar `Money -> BigDecimal` không thể tự ghi thêm cột currency. Cần thiết kế entity với hai thuộc tính, một kiểu embedded/aggregate phù hợp, hoặc xử lý mapping bằng cách khác.

Converter đơn giản phù hợp nhất khi một thuộc tính Java được biểu diễn bằng một giá trị lưu trữ. Nếu cần biến đổi nhiều cột thành một object, phải thiết kế rõ ranh giới mapping thay vì ép mọi thứ vào một `Converter<S, T>`.

## 7. Converter và các API truy cập dữ liệu

### 7.1. Repository và R2dbcEntityTemplate

Repository Spring Data và `R2dbcEntityTemplate` sử dụng mapping infrastructure của Spring Data. `R2dbcCustomConversions` được dùng để chuyển các thuộc tính entity khi lưu hoặc materialize kết quả.

Ví dụ repository:

```java
public interface OrderRepository
        extends ReactiveCrudRepository<OrderEntity, Long> {

    Mono<OrderEntity> findByOrderCode(OrderCode orderCode);
}
```

Khi truy vấn theo thuộc tính `OrderCode`, Spring Data cần biết cách chuyển giá trị tham số sang kiểu lưu trữ phù hợp. Converter ghi đã đăng ký cung cấp phép chuyển đổi cho giá trị này trong đường mapping repository.

### 7.2. `DatabaseClient` ở mức SQL thấp

`DatabaseClient` cho phép viết và bind SQL trực tiếp. Khi tự bind một tham số vào `Statement`, cần truyền kiểu mà driver hỗ trợ. Không nên mặc định rằng mọi thao tác bind thủ công sẽ tự gọi converter entity của `R2dbcCustomConversions`.

Ví dụ chuyển rõ ràng trước khi bind:

```java
OrderCode orderCode = new OrderCode("ORD-123456");

return databaseClient.sql(
        "SELECT * FROM orders WHERE order_code = :code")
    .bind("code", orderCode.value())
    .map((row, metadata) -> /* ánh xạ kết quả */)
    .one();
```

Ở đường truy vấn mức thấp, code chịu trách nhiệm chuyển giá trị bind và ánh xạ `Row` theo cách phù hợp. Nếu muốn tái sử dụng logic chuyển đổi, có thể gọi một mapper/converter riêng hoặc dùng API mapping entity thích hợp. Tránh cho rằng cấu hình custom conversions sẽ tự động bao phủ tất cả API của R2DBC SPI.

### 7.3. JSON API là một ranh giới riêng

Converter persistence không tự quyết định cách `OrderCode` xuất hiện trong JSON. Nếu API muốn trả `"ORD-123456"`, có thể dùng Jackson serializer/deserializer, `@JsonValue`/`@JsonCreator` hoặc DTO chứa chuỗi theo hợp đồng API. Nếu API muốn cấu trúc object, DTO có thể biểu diễn cấu trúc đó riêng.

Giữ mapping database và mapping JSON tách biệt giúp thay đổi kiểu lưu trữ mà không làm client phải thay đổi hợp đồng, và ngược lại.

## 8. Kiểm thử converter và cấu hình

Không chỉ xác nhận bean khởi tạo thành công. Cần kiểm thử từng converter và đường mapping thực tế.

### 8.1. Unit test converter

```java
class OrderCodeConverterTests {

    private final OrderCodeWritingConverter writing =
            new OrderCodeWritingConverter();

    private final OrderCodeReadingConverter reading =
            new OrderCodeReadingConverter();

    @Test
    void writesOrderCodeAsString() {
        String value = writing.convert(new OrderCode("ORD-123456"));

        assertThat(value).isEqualTo("ORD-123456");
    }

    @Test
    void readsStringAsOrderCode() {
        OrderCode value = reading.convert("ORD-123456");

        assertThat(value).isEqualTo(new OrderCode("ORD-123456"));
    }

    @Test
    void rejectsInvalidStoredValue() {
        assertThatThrownBy(() -> reading.convert("invalid"))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
```

Unit test xác nhận phép chuyển đổi đơn lẻ, nhưng chưa chứng minh Spring Data đã đăng ký và sử dụng converter đúng hướng.

### 8.2. Kiểm thử cấu hình Spring

Khởi tạo application context trong test và xác nhận bean `R2dbcCustomConversions` được tạo với dialect phù hợp. Nếu ứng dụng có nhiều cấu hình hoặc nhiều `ConnectionFactory`, cần kiểm tra converter được gắn với đúng mapping context và database tương ứng.

Không khai báo thêm bean trùng chỉ để test. Nên khởi chạy cấu hình thực tế của ứng dụng trong phạm vi integration test.

### 8.3. Integration test đọc và ghi entity

Ví dụ kiểm thử theo luồng repository:

```java
OrderEntity order = new OrderEntity(
        null,
        new OrderCode("ORD-123456"),
        "NEW"
);

StepVerifier.create(orderRepository.save(order))
        .assertNext(saved -> {
            assertThat(saved.id()).isNotNull();
            assertThat(saved.orderCode())
                    .isEqualTo(new OrderCode("ORD-123456"));
        })
        .verifyComplete();

StepVerifier.create(orderRepository.findByOrderCode(
                new OrderCode("ORD-123456")))
        .expectNextMatches(found ->
                found.orderCode().equals(new OrderCode("ORD-123456")))
        .verifyComplete();
```

Test này minh họa cả chiều ghi và đọc thông qua repository. Trong test thực tế, chuẩn bị schema `orders`, cấu hình database/driver tương thích và dọn dữ liệu theo quy trình test của dự án.

### 8.4. Kiểm thử dữ liệu lỗi và tương thích

Nên có trường hợp kiểm thử:

- Database trả về giá trị không đúng định dạng của value object.
- Cột có giá trị `NULL` trong khi kiểu domain không chấp nhận null.
- Dữ liệu cũ có format trước khi quy tắc mới được triển khai.
- Giá trị biên, độ dài tối đa và ký tự đặc biệt.
- Chạy trên đúng database và driver production dự kiến.

Nếu converter có thể phát lỗi khi đọc, hãy quyết định lỗi đó được xử lý ở tầng repository/service ra sao. Dữ liệu sai định dạng có thể là vấn đề chất lượng dữ liệu cần được quan sát và xử lý, không nên âm thầm biến thành giá trị hợp lệ giả.

## 9. Lỗi thường gặp khi đăng ký custom conversions

### Chỉ viết converter một chiều

Insert có thể thành công nhưng đọc entity lại thất bại vì thiếu converter ngược. Kiểm tra cả reading và writing path; đăng ký cả hai nếu use case cần CRUD.

### Đảo nhầm kiểu nguồn và kiểu đích

`Converter<OrderCode, String>` là hướng ghi trong ví dụ; `Converter<String, OrderCode>` là hướng đọc. Kiểm tra generic type và annotation của từng class.

### Bỏ qua `@ReadingConverter` hoặc `@WritingConverter`

Khi chuyển giữa custom type và simple type, hướng chuyển đổi có thể mơ hồ. Gắn annotation tương ứng để Spring Data biết converter được dùng ở giai đoạn nào.

### Chọn dialect không khớp database

Dialect ảnh hưởng tới conversion và cách xử lý kiểu dữ liệu theo hệ quản trị. Lấy dialect từ `ConnectionFactory` đang sử dụng hoặc cấu hình phù hợp với driver; không sao chép cấu hình dialect của database khác.

### Nghĩ converter persistence tự áp dụng cho JSON

`R2dbcCustomConversions` phục vụ mapping của Spring Data R2DBC. JSON request/response cần cấu hình serialization riêng nếu API không dùng cách biểu diễn mặc định.

### Nghĩ converter tự áp dụng cho mọi lệnh bind thủ công

Khi dùng `DatabaseClient` hoặc R2DBC SPI trực tiếp, cần kiểm tra API mapping đang sử dụng. Lời gọi bind tham số thủ công phải cung cấp giá trị mà driver hỗ trợ; có thể cần chuyển đổi rõ ràng.

### Dùng converter cho một giá trị cần nhiều cột

`Converter<S, T>` chuyển một giá trị nguồn thành một giá trị đích. Nếu một value object gồm nhiều phần cần lưu ở nhiều cột, hãy chọn mô hình entity/embedded hoặc cách mapping phù hợp thay vì kỳ vọng converter tự ghi nhiều cột.

### Đặt logic nghiệp vụ hoặc truy vấn database bên trong converter

Converter nên là phép chuyển đổi nhỏ, xác định và dễ kiểm thử. Không gọi Repository, không truy cập mạng và không dùng `.block()` trong converter. Nếu cần tra cứu dữ liệu để diễn giải một giá trị, đó là logic của Service hoặc một bước nghiệp vụ riêng.

## 10. Quy trình đăng ký converter cho một kiểu mới

Khi cần lưu một kiểu domain tùy chỉnh, có thể làm theo thứ tự:

1. Xác định kiểu database/driver hỗ trợ để biểu diễn giá trị.
2. Thiết kế value object và quy tắc hợp lệ của nó.
3. Viết converter ghi từ domain type sang store type.
4. Viết converter đọc từ store type sang domain type.
5. Gắn `@WritingConverter` và `@ReadingConverter` theo đúng chiều.
6. Đăng ký converter trong `R2dbcCustomConversions`, giữ dialect phù hợp với `ConnectionFactory`.
7. Dùng kiểu domain trong persistence entity và khai báo mapping cột.
8. Kiểm thử từng converter độc lập.
9. Kiểm thử repository/template đọc và ghi entity trên database mục tiêu.
10. Kiểm thử dữ liệu cũ, null, giá trị biên và lỗi chuyển đổi.

## 11. Checklist ghi nhớ

- [ ] Đã xác định kiểu Java/domain và kiểu lưu trữ mà driver hỗ trợ.
- [ ] Converter ghi có kiểu `Converter<DomainType, StoreType>` và `@WritingConverter`.
- [ ] Converter đọc có kiểu `Converter<StoreType, DomainType>` và `@ReadingConverter`.
- [ ] Hai chiều được đăng ký riêng khi use case cần cả đọc và ghi.
- [ ] `R2dbcCustomConversions` được tạo với dialect phù hợp database/driver.
- [ ] Không tạo mapping context hoặc converter trùng với auto-configuration.
- [ ] Entity dùng kiểu domain và mapping cột phù hợp schema.
- [ ] Converter không thực hiện I/O, không gọi Repository và không blocking.
- [ ] Phân biệt mapping của Spring Data với bind thủ công qua `DatabaseClient`/R2DBC SPI.
- [ ] JSON serialization được cấu hình độc lập khi API cần cách biểu diễn khác.
- [ ] Có unit test cho converter và integration test cho cả chiều đọc/ghi.
- [ ] Có chiến lược xử lý dữ liệu cũ, null và giá trị không hợp lệ.

`R2dbcCustomConversions` giúp Spring Data R2DBC hiểu cách chuyển đổi giữa kiểu miền nghiệp vụ và kiểu dữ liệu lưu trữ. Khi converter được khai báo đúng chiều, đăng ký cùng dialect phù hợp và kiểm thử qua Repository thực tế, entity có thể sử dụng value object rõ nghĩa mà vẫn lưu trữ bằng các kiểu dữ liệu quan hệ tiêu chuẩn.

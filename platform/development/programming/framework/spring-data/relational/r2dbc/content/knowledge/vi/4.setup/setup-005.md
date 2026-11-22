# Cấu hình thủ công và vai trò của AbstractR2dbcConfiguration

Spring Data R2DBC cần một `ConnectionFactory` để tạo kết nối reactive đến cơ sở dữ liệu. Trên nền tảng đó, Spring Data xây dựng các thành phần ánh xạ hàng dữ liệu thành object, thực thi câu lệnh SQL, cung cấp API thao tác entity và hỗ trợ repository. Trong một ứng dụng Spring không dùng Spring Boot auto-configuration, hoặc khi cần kiểm soát cách tạo kết nối và các thành phần persistence, ta có thể khai báo cấu hình Java thủ công.

`AbstractR2dbcConfiguration` là lớp cấu hình cơ sở của Spring Data R2DBC. Ứng dụng kế thừa lớp này và cung cấp `ConnectionFactory`; lớp cơ sở đăng ký các bean hạ tầng mặc định cần thiết cho Spring Data R2DBC. Nhờ vậy, ta không phải tự lắp ráp toàn bộ mapping context, converter, dialect, `DatabaseClient` và `R2dbcEntityTemplate` trong cấu hình thông thường.

## 1. Các thành phần cần có khi cấu hình thủ công

Một cấu hình Spring Data R2DBC thường có các thành phần sau:

| Thành phần | Vai trò |
|---|---|
| `ConnectionFactory` | Tạo kết nối reactive đến database thông qua R2DBC driver. Đây là đầu vào nền tảng của các thành phần còn lại. |
| `R2dbcDialect` | Cung cấp khác biệt SQL và kiểu dữ liệu theo hệ quản trị cơ sở dữ liệu, chẳng hạn cách tạo câu lệnh và xử lý một số kiểu đặc thù. |
| `R2dbcMappingContext` | Lưu metadata ánh xạ giữa kiểu Java, entity, bảng và cột. |
| `R2dbcConverter` và custom conversions | Chuyển đổi giá trị giữa kiểu dữ liệu trong database và kiểu Java của ứng dụng. |
| `DatabaseClient` | Thực thi SQL và xử lý kết quả theo API reactive ở mức thấp hơn. |
| `R2dbcEntityTemplate` | Cung cấp API mức entity cho các thao tác đọc, ghi và truy vấn dữ liệu. |
| Repository infrastructure | Tạo implementation cho các interface repository được khai báo bằng Spring Data. |

Các thành phần này phối hợp với nhau. `ConnectionFactory` cung cấp kết nối; dialect và mapping metadata giúp Spring Data tạo và diễn giải thao tác dữ liệu; converter chuyển đổi giá trị; `DatabaseClient` thực thi SQL; template và repository cung cấp API thuận tiện hơn cho tầng ứng dụng.

## 2. Khai báo cấu hình bằng AbstractR2dbcConfiguration

Ví dụ dưới đây cấu hình một ứng dụng sử dụng PostgreSQL R2DBC driver. Tên host, database và thông tin đăng nhập chỉ mang tính minh họa; trong ứng dụng thực tế, thông tin nhạy cảm nên được cấp từ biến môi trường hoặc hệ thống quản lý cấu hình bí mật.

```java
import io.r2dbc.spi.ConnectionFactories;
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.ConnectionFactoryOptions;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.r2dbc.config.AbstractR2dbcConfiguration;
import org.springframework.data.r2dbc.repository.config.EnableR2dbcRepositories;

import static io.r2dbc.spi.ConnectionFactoryOptions.DATABASE;
import static io.r2dbc.spi.ConnectionFactoryOptions.DRIVER;
import static io.r2dbc.spi.ConnectionFactoryOptions.HOST;
import static io.r2dbc.spi.ConnectionFactoryOptions.PASSWORD;
import static io.r2dbc.spi.ConnectionFactoryOptions.PORT;
import static io.r2dbc.spi.ConnectionFactoryOptions.USER;

@Configuration
@EnableR2dbcRepositories(basePackages = "com.example.orders.repository")
public class R2dbcConfig extends AbstractR2dbcConfiguration {

    @Override
    @Bean
    public ConnectionFactory connectionFactory() {
        ConnectionFactoryOptions options = ConnectionFactoryOptions.builder()
            .option(DRIVER, "postgresql")
            .option(HOST, "localhost")
            .option(PORT, 5432)
            .option(USER, System.getenv("DB_USER"))
            .option(PASSWORD, System.getenv("DB_PASSWORD"))
            .option(DATABASE, "orders")
            .build();

        return ConnectionFactories.get(options);
    }
}
```

Điểm quan trọng trong cấu hình là phương thức `connectionFactory()`:

- `ConnectionFactory` thuộc R2DBC SPI, không phải JDBC `DataSource`.
- `ConnectionFactories.get(options)` tìm driver phù hợp với tùy chọn `DRIVER` và tạo `ConnectionFactory` do driver cung cấp.
- Các tùy chọn như host, port, database và credentials mô tả cách kết nối. Driver cụ thể có thể hỗ trợ thêm các tùy chọn riêng.
- `@Bean` đưa `ConnectionFactory` vào Spring application context để các bean persistence sử dụng.

Ứng dụng cần có R2DBC driver tương ứng trên classpath, ví dụ PostgreSQL R2DBC driver khi dùng `DRIVER = "postgresql"`. Thông tin đăng nhập trong ví dụ được đọc từ biến môi trường; cần bảo đảm các biến đó đã được thiết lập trước khi khởi chạy ứng dụng.

`@EnableR2dbcRepositories` yêu cầu Spring Data quét package repository và tạo các bean triển khai cho những interface phù hợp. Có thể thay `basePackages` bằng package thực tế của dự án. Nếu không bật repository scanning, ứng dụng vẫn có thể thao tác dữ liệu thông qua `DatabaseClient` hoặc `R2dbcEntityTemplate`, miễn là các bean tương ứng đã được cấu hình.

## 3. AbstractR2dbcConfiguration làm gì?

Lớp `AbstractR2dbcConfiguration` cung cấp cấu hình mặc định cho hạ tầng Spring Data R2DBC. Sau khi ứng dụng cung cấp `ConnectionFactory`, lớp cơ sở sử dụng nó để thiết lập các thành phần persistence thường dùng.

### 3.1 Tạo các bean truy cập dữ liệu

`DatabaseClient` là abstraction để gửi SQL đến database và xử lý kết quả theo kiểu reactive. Nó phù hợp khi cần viết SQL trực tiếp hoặc kiểm soát rõ cách bind tham số và đọc từng dòng kết quả.

`R2dbcEntityTemplate` xây dựng trên hạ tầng truy cập dữ liệu để cung cấp thao tác theo entity. Thay vì tự viết toàn bộ phần ánh xạ cho những thao tác phổ biến, ứng dụng có thể dùng template để insert, update, select và delete object theo metadata đã khai báo.

Repository infrastructure sử dụng các thành phần này để hỗ trợ repository như `ReactiveCrudRepository`. Nhờ đó, tầng nghiệp vụ có thể phụ thuộc vào interface repository thay vì tự quản lý việc tạo kết nối và ánh xạ từng hàng dữ liệu.

### 3.2 Thiết lập mapping context và converter

`R2dbcMappingContext` lưu thông tin mô tả entity. Spring Data dùng metadata này để biết tên bảng, tên cột, trường định danh và cấu trúc các object thuộc aggregate.

`R2dbcConverter` chịu trách nhiệm chuyển đổi dữ liệu giữa database và object Java. Ví dụ, một cột kiểu số có thể được chuyển thành `Long`, `BigDecimal` hoặc kiểu miền nghiệp vụ phù hợp, tùy mapping và converter đã đăng ký.

Khi ứng dụng có kiểu dữ liệu riêng, có thể đăng ký custom converter để định nghĩa cách đọc và ghi kiểu đó. Với các phiên bản Spring Data R2DBC có hook `getCustomConverters()`, có thể bổ sung converter trong lớp cấu hình kế thừa:

```java
@Override
protected List<Object> getCustomConverters() {
    return List.of(
        new MoneyReadConverter(),
        new MoneyWriteConverter()
    );
}
```

`MoneyReadConverter` và `MoneyWriteConverter` là các converter do ứng dụng định nghĩa; chúng cần triển khai đúng hướng chuyển đổi mà Spring Data yêu cầu. Ví dụ, converter đọc có thể chuyển một giá trị `BigDecimal` từ database thành `Money`, còn converter ghi chuyển `Money` thành `BigDecimal`. Khi dùng hook này, cần khai báo các converter và import tương ứng trong dự án.

### 3.3 Chọn dialect theo database

SQL có những khác biệt giữa các hệ quản trị cơ sở dữ liệu. `R2dbcDialect` biểu diễn các khác biệt mà Spring Data cần biết khi tạo một số thao tác SQL và xử lý kiểu dữ liệu. Cấu hình cơ sở sử dụng khả năng nhận diện dialect tương ứng với `ConnectionFactory` khi driver được hỗ trợ.

Vì vậy, `ConnectionFactory` phải được tạo từ đúng R2DBC driver. Nếu dùng driver hoặc hệ quản trị không được Spring Data hỗ trợ nhận diện, ứng dụng cần kiểm tra khả năng hỗ trợ dialect và bổ sung tích hợp phù hợp; không nên giả định rằng mọi driver R2DBC đều tự động có dialect của Spring Data.

## 4. Cấu hình transaction reactive

`ConnectionFactory` cũng là cơ sở để quản lý transaction reactive. Trong cấu hình thủ công, khi ứng dụng cần transaction được quản lý bởi Spring, có thể đăng ký `R2dbcTransactionManager`:

```java
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;

@Bean
ReactiveTransactionManager transactionManager(
        ConnectionFactory connectionFactory) {
    return new R2dbcTransactionManager(connectionFactory);
}
```

Transaction manager này phối hợp transaction với `ConnectionFactory`. Khi dùng transaction khai báo, cấu hình transaction management của Spring cũng phải được bật trong ứng dụng (hoặc được Spring Boot tự cấu hình). Các thao tác database cần nằm trong reactive flow phù hợp để Spring truyền transaction context qua chuỗi reactive.

Không nên trộn thao tác blocking hoặc gọi `block()` tùy tiện bên trong reactive transaction. Việc chặn luồng có thể làm mất tính chất non-blocking và khiến transaction context không được sử dụng theo cách mong muốn. Với nhiều thao tác cần cùng thành công hoặc thất bại, hãy tổ chức chúng trong cùng phạm vi reactive transaction.

Nếu Spring Boot đã tự cấu hình transaction manager cho `ConnectionFactory`, không đăng ký thêm một bean trùng vai trò nếu không có lý do rõ ràng. Hãy kiểm tra các bean hiện có trước khi bổ sung cấu hình thủ công.

## 5. Spring Boot auto-configuration và cấu hình thủ công

Trong ứng dụng Spring Boot, trường hợp thông thường không cần kế thừa `AbstractR2dbcConfiguration`. Khi có starter phù hợp và cấu hình kết nối trong `application.yml`, Spring Boot có thể tự tạo `ConnectionFactory` và cấu hình hạ tầng Spring Data R2DBC.

Ví dụ cấu hình kết nối trong `application.yml`:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/orders
    username: ${DB_USER}
    password: ${DB_PASSWORD}
```

Spring Boot đọc các thuộc tính này để tạo cấu hình kết nối. Driver PostgreSQL R2DBC vẫn phải có trong dependencies. Repository scanning cũng có thể được auto-configure theo cấu trúc ứng dụng; nếu cần giới hạn package hoặc thay đổi cách quét, có thể khai báo `@EnableR2dbcRepositories`.

| Tình huống | Cách tiếp cận phù hợp |
|---|---|
| Ứng dụng Spring Boot thông thường, một database, cấu hình kết nối tiêu chuẩn | Dùng `spring.r2dbc.*` và auto-configuration. |
| Ứng dụng Spring Framework không dùng Spring Boot | Kế thừa `AbstractR2dbcConfiguration`, cung cấp `ConnectionFactory` và bật repository scanning nếu cần. |
| Cần custom converter hoặc tinh chỉnh mapping của Spring Data | Dùng điểm mở rộng của Spring Data R2DBC; có thể kế thừa `AbstractR2dbcConfiguration`. |
| Cần tạo `ConnectionFactory` theo cách riêng, dùng pool hoặc cấu hình driver đặc thù | Khai báo bean thủ công và bảo đảm các thành phần Spring Data sử dụng đúng factory đó. |
| Có nhiều database hoặc nhiều `ConnectionFactory` | Cấu hình rõ từng nhóm repository và bean truy cập dữ liệu tương ứng; tránh để một repository trỏ nhầm factory. |

Không nên vừa khai báo đầy đủ các bean thủ công vừa giữ nguyên một cấu hình auto-configuration khác mà không kiểm tra điều kiện tạo bean. Điều đó có thể dẫn đến bean trùng tên, nhiều `ConnectionFactory`, hoặc repository sử dụng nhầm `R2dbcEntityOperations`. Hãy chọn một điểm chịu trách nhiệm chính cho từng thành phần và cấu hình rõ ràng khi cần nhiều database.

## 6. Những việc AbstractR2dbcConfiguration không tự thực hiện

Kế thừa `AbstractR2dbcConfiguration` giúp khởi tạo hạ tầng Spring Data R2DBC, nhưng không có nghĩa toàn bộ vòng đời database được tự động quản lý.

- **Không thay thế R2DBC driver.** Ứng dụng vẫn phải thêm dependency driver tương ứng với database.
- **Không tự tạo hoặc migrate schema.** Tạo bảng, index và thay đổi cấu trúc database cần migration tool hoặc quy trình quản lý schema riêng.
- **Không tự tạo domain model.** Ứng dụng vẫn phải định nghĩa entity, mapping và ranh giới aggregate.
- **Không biến R2DBC thành ORM đầy đủ.** Lớp cấu hình không bổ sung persistence context kiểu JPA, dirty checking hay lazy loading qua proxy.
- **Không thay thế thiết kế transaction.** Ứng dụng vẫn phải xác định phạm vi transaction và tổ chức các thao tác trong reactive flow.
- **Không bảo đảm mọi database đều có dialect tương thích.** Cần dùng driver và dialect được Spring Data hỗ trợ hoặc cung cấp tích hợp phù hợp.

## 7. Quy trình cấu hình và kiểm tra khi khởi tạo

Khi thiết lập R2DBC thủ công, có thể thực hiện theo trình tự sau:

1. Thêm R2DBC SPI và driver cho hệ quản trị cơ sở dữ liệu cần dùng.
2. Tạo `ConnectionFactory` với driver, host, port, database và credentials phù hợp.
3. Kế thừa `AbstractR2dbcConfiguration` và override `connectionFactory()` để Spring Data có đầu vào tạo hạ tầng.
4. Bật `@EnableR2dbcRepositories` nếu ứng dụng dùng repository, đồng thời chỉ rõ package cần quét.
5. Bổ sung custom converter hoặc cấu hình transaction khi nghiệp vụ cần.
6. Khởi động ứng dụng và kiểm tra việc tạo bean, kết nối database, truy vấn đơn giản và repository thực tế.

Nếu ứng dụng khởi động nhưng truy vấn thất bại, cần xác định lỗi thuộc nhóm nào: driver không có trên classpath, tùy chọn kết nối sai, database không truy cập được, dialect không được nhận diện, mapping không khớp schema hay repository chưa được quét. Phân loại lỗi theo từng tầng giúp xử lý đúng thành phần chịu trách nhiệm.

`AbstractR2dbcConfiguration` vì thế đóng vai trò cầu nối giữa `ConnectionFactory` của R2DBC và hạ tầng Spring Data R2DBC. Ứng dụng chỉ cần cung cấp factory cùng các tùy chỉnh cần thiết; lớp cơ sở chuẩn bị những thành phần mapping và truy cập dữ liệu mặc định để template và repository có thể hoạt động. Trong Spring Boot, hãy ưu tiên auto-configuration cho nhu cầu thông thường và chỉ chuyển sang cấu hình thủ công khi ứng dụng cần quyền kiểm soát hoặc điểm mở rộng cụ thể.

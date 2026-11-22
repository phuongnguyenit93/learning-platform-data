# Dùng `@ConfigurationProperties` trên `@Bean` của thư viện bên ngoài trong Spring Boot

## 1. Vấn đề cần giải quyết

`@ConfigurationProperties` là cơ chế của Spring Boot để ánh xạ cấu hình ngoài vào các đối tượng Java. Trong những ví dụ cơ bản, ta tự viết một lớp `AppProperties`, đặt `@ConfigurationProperties(prefix = "app")` lên lớp đó và đăng ký nó với Spring.

Nhưng dự án thực tế thường dùng **đối tượng do một thư viện khác cung cấp**, chẳng hạn:

- `HikariDataSource` hoặc `HikariConfig` của HikariCP để quản lý kết nối cơ sở dữ liệu.
- Một bean cấu hình pool, cache hoặc HTTP client có setter do nhà cung cấp thư viện định nghĩa.
- Một thành phần hạ tầng mà mã nguồn dự án **không sở hữu**, không thể tùy ý thêm annotation vào class.

Vấn đề là: làm thế nào để lấy các giá trị trong `application.yml`, biến môi trường hoặc các nguồn cấu hình của Spring Boot và **bind trực tiếp vào bean của thư viện**, mà không sửa mã nguồn của thư viện và không viết thủ công hàng loạt lời gọi setter?

Spring Boot hỗ trợ đặt `@ConfigurationProperties` **trên phương thức `@Bean`**:

~~~java
@Configuration(proxyBeanMethods = false)
public class ThirdPartyConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "app.datasource.reporting")
    public HikariDataSource reportingDataSource() {
        return new HikariDataSource();
    }
}
~~~

Spring tạo instance bằng factory method, sau đó infrastructure của `@ConfigurationProperties` gán các thuộc tính có tiền tố tương ứng vào các JavaBean properties của instance đó.

> **Ý chính:** với bean của thư viện ngoài, annotation được đặt ở **điểm đăng ký bean**, không cần đặt trên class của thư viện. Cách này phù hợp với **JavaBean/setter binding trên đối tượng đã được tạo**, không phải constructor binding để Spring Boot tự xây dựng một object bất biến.

## 2. Hai vị trí đặt `@ConfigurationProperties`

Có hai mẫu cần phân biệt rõ.

### 2.1. Trên lớp thuộc quyền sở hữu của ứng dụng

Ví dụ ứng dụng có class tự viết:

~~~java
package com.example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.remote")
public class RemoteProperties {
    private String baseUrl;
    private Duration timeout = Duration.ofSeconds(3);

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(RemoteProperties.class)` rồi inject `RemoteProperties` vào bean nghiệp vụ. Cách này hợp lý khi bạn kiểm soát cấu trúc và muốn khai báo kiểu, mặc định, validation ngay trên class.

### 2.2. Trên phương thức `@Bean` khi class thuộc thư viện khác

Nếu class được cung cấp bởi một JAR ngoài, không thể viết:

~~~java
// Không thể chỉnh sửa mã nguồn HikariCP để thêm annotation tùy ý.
@ConfigurationProperties(prefix = "app.datasource.reporting")
public class HikariDataSource { /* ... */ }
~~~

Thay vào đó:

~~~java
import com.zaxxer.hikari.HikariDataSource;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ReportingDataSourceConfiguration {

    @Bean("reportingDataSource")
    @ConfigurationProperties(prefix = "app.datasource.reporting")
    public HikariDataSource reportingDataSource() {
        return new HikariDataSource();
    }
}
~~~

Phương thức `@Bean` là nơi ứng dụng đăng ký object vào Spring container. Annotation `@ConfigurationProperties` trên chính phương thức đó yêu cầu Spring Boot bind các thuộc tính cấu hình vào bean trả về.

Một class `@Configuration` nằm trong vùng component scan của ứng dụng (hoặc được import/đăng ký rõ ràng) là đủ để Spring nhận phương thức `@Bean`. **Không cần thêm `@ConfigurationPropertiesScan` chỉ để nhận biết annotation trên phương thức `@Bean`.** Annotation scan chủ yếu để tìm các *type* `@ConfigurationProperties` do ứng dụng khai báo.

## 3. Cơ chế binding ở thời điểm tạo bean

Mô hình khái quát:

~~~text
application.yml / application.properties
OS environment / JVM -D / command-line args
                 |
                 v
             Environment
       (giá trị theo precedence)
                 |
                 v
        @Configuration + @Bean
                 |
                 v
        reportingDataSource()
           new HikariDataSource()
                 |
                 v
    @ConfigurationProperties binding
  app.datasource.reporting.jdbc-url
  app.datasource.reporting.username
  app.datasource.reporting.maximum-pool-size
                 |
                 v
   các setter trên HikariDataSource
                 |
                 v
   bean đã cấu hình được inject / dùng
~~~

Điểm cần hiểu:

1. Phương thức `@Bean` **tạo object trước**. Trong ví dụ, đó là `new HikariDataSource()`.
2. Spring Boot bind những property khớp prefix vào object sau khi factory method trả về, trong quy trình cấu hình bean.
3. Bean sau binding được đưa vào dependency injection và có thể được sử dụng bởi các bean phụ thuộc.
4. Spring Boot dựa trên **JavaBean properties** (thường là getter/setter) và conversion service để ánh xạ dữ liệu sang kiểu Java.
5. Binding chỉ có thể tác động đến những thuộc tính mà object bên ngoài **thực sự hỗ trợ cấu hình**. Annotation không tự tạo setter hay thay đổi API của thư viện.

Vì giai đoạn binding diễn ra sau khi factory method đã tạo object, **đừng thực hiện thao tác cần cấu hình hoàn chỉnh ngay trong factory method**. Ví dụ, gọi `getConnection()` trên datasource trước khi return có thể sử dụng giá trị chưa được bind.

## 4. Ví dụ thực tế: cấu hình HikariCP từ `application.yml`

HikariCP là connection pool phổ biến trong hệ sinh thái Spring Boot. Nó có `HikariDataSource` và các JavaBean properties như `jdbcUrl`, `username`, `password`, `maximumPoolSize`, `minimumIdle`, `connectionTimeout`.

### 4.1. Dependency

Với ứng dụng Spring Boot 3.x dùng Maven, dependency JDBC starter thường đã mang theo HikariCP theo mặc định:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>

<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Đoạn thứ hai là JDBC driver ví dụ cho PostgreSQL. Chọn driver thực tế theo cơ sở dữ liệu sử dụng. Khi dự án đã có starter hoặc dependency HikariCP, không cần thêm trùng lặp.

### 4.2. Cấu hình ngoài

File `src/main/resources/application.yml`:

~~~yaml
app:
  datasource:
    reporting:
      jdbc-url: jdbc:postgresql://localhost:5432/reporting
      username: report_user
      password: "${REPORTING_DB_PASSWORD}"
      maximum-pool-size: 8
      minimum-idle: 2
      connection-timeout: 30000
      pool-name: reporting-pool
~~~

Các property dưới `app.datasource.reporting` được đưa vào `HikariDataSource` theo tên property tương ứng. `connection-timeout` ở ví dụ dùng giá trị số nguyên tính bằng **mili giây** như API `HikariConfig#setConnectionTimeout(long)`.

Biến môi trường `REPORTING_DB_PASSWORD` cần được cấp bởi cơ chế quản lý secret phù hợp. Đừng commit mật khẩu thật vào repository hoặc in mật khẩu ra log.

### 4.3. Đăng ký bean của thư viện ngoài

~~~java
package com.example.config;

import com.zaxxer.hikari.HikariDataSource;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ReportingDataSourceConfiguration {

    @Bean(name = "reportingDataSource", destroyMethod = "close")
    @ConfigurationProperties(prefix = "app.datasource.reporting")
    public HikariDataSource reportingDataSource() {
        return new HikariDataSource();
    }
}
~~~

Giải thích:

- `@Configuration`: lớp khai báo các bean Spring.
- `proxyBeanMethods = false`: lựa chọn thích hợp khi các factory method không dựa vào việc gọi trực tiếp các method `@Bean` khác; không liên quan đến bản chất binding.
- `@Bean(name = "reportingDataSource")`: đăng ký một bean có tên rõ ràng, hữu ích nếu ứng dụng có nhiều datasource.
- `destroyMethod = "close"`: yêu cầu đóng datasource/pool khi bean bị hủy. Spring cũng có thể tự suy luận destroy method phù hợp; viết tường minh giúp nêu rõ vòng đời.
- `@ConfigurationProperties(prefix = "app.datasource.reporting")`: bind các property có cùng prefix vào instance được trả về.
- `new HikariDataSource()`: dùng constructor không tham số; các setter được binder gọi sau đó.

Nếu bean do thư viện không có constructor không tham số, bạn vẫn có thể gọi constructor phù hợp **ở trong factory method**, nhưng các tham số constructor đó **không được tự động binder cung cấp** chỉ nhờ `@ConfigurationProperties` trên phương thức. Khi cần constructor arguments đến từ cấu hình, dùng mẫu đối tượng properties trung gian ở phần sau.

### 4.4. Sử dụng bean từ service khác

~~~java
package com.example.service;

import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class ReportingService {
    private final DataSource reportingDataSource;

    public ReportingService(
            @Qualifier("reportingDataSource") DataSource reportingDataSource) {
        this.reportingDataSource = reportingDataSource;
    }

    // Sử dụng reportingDataSource để truy cập dữ liệu reporting.
}
~~~

Có thể inject qua interface `javax.sql.DataSource` vì `HikariDataSource` triển khai interface này. `@Qualifier` giúp Spring chọn đúng bean khi hệ thống có nhiều datasource.

**Lưu ý tích hợp:** đăng ký `DataSource` thủ công có thể làm auto-configuration của Spring Boot thay đổi hoặc back off. Nếu ứng dụng có nhiều datasource, phải thiết kế rõ datasource chính, các `@Qualifier`, transaction manager và tích hợp JPA/JDBC tương ứng. Ví dụ này tập trung vào cách bind bean của thư viện, không phải cấu hình hoàn chỉnh cho hệ thống nhiều datasource.

## 5. Bảng ánh xạ YAML → JavaBean setters

Trong ví dụ HikariCP:

| Key trong YAML | Thuộc tính JavaBean | Setter điển hình |
| --- | --- | --- |
| `app.datasource.reporting.jdbc-url` | `jdbcUrl` | `setJdbcUrl(String)` |
| `app.datasource.reporting.username` | `username` | `setUsername(String)` |
| `app.datasource.reporting.password` | `password` | `setPassword(String)` |
| `app.datasource.reporting.maximum-pool-size` | `maximumPoolSize` | `setMaximumPoolSize(int)` |
| `app.datasource.reporting.minimum-idle` | `minimumIdle` | `setMinimumIdle(int)` |
| `app.datasource.reporting.connection-timeout` | `connectionTimeout` | `setConnectionTimeout(long)` |
| `app.datasource.reporting.pool-name` | `poolName` | `setPoolName(String)` |

Spring Boot có **relaxed binding**, nên `maximum-pool-size` trong cấu hình có thể khớp với Java property `maximumPoolSize`. Các key nên dùng dạng **lowercase kebab-case** trong YAML/Properties để dễ đọc và nhất quán.

Tên prefix trong annotation phải phù hợp cú pháp canonical:

~~~java
@ConfigurationProperties(prefix = "app.datasource.reporting")
~~~

Không nên viết prefix bằng chữ hoa hoặc một dạng tên không chuẩn chỉ vì Java property của thư viện dùng camelCase.

### 5.1. Chú ý tên thật của thuộc tính thư viện

Một lỗi phổ biến khi cấu hình HikariCP:

~~~yaml
app:
  datasource:
    reporting:
      url: jdbc:postgresql://localhost:5432/reporting
~~~

`HikariDataSource` có property `jdbcUrl`, không phải property JavaBean `url` tương ứng để binder trực tiếp điền URL theo mẫu trên. Dùng:

~~~yaml
app:
  datasource:
    reporting:
      jdbc-url: jdbc:postgresql://localhost:5432/reporting
~~~

Đây là khác biệt giữa **binding trực tiếp vào class của nhà cung cấp** và **binding vào một lớp properties riêng của Spring Boot** có thể thực hiện bước chuyển đổi hay ánh xạ tên.

Ví dụ, `spring.datasource.url` được hỗ trợ thông qua những lớp auto-configuration/properties của Spring Boot. Không có nghĩa bất kỳ bean `HikariDataSource` custom nào cũng tự hiểu `url` khi bạn gắn một prefix tùy chọn.

## 6. Thứ tự ưu tiên nguồn cấu hình vẫn giữ nguyên

`@ConfigurationProperties` không tự định nghĩa một thứ tự nguồn mới. Nó bind **giá trị đã được giải quyết** từ `Environment`.

Ví dụ YAML:

~~~yaml
app:
  datasource:
    reporting:
      maximum-pool-size: 8
      minimum-idle: 2
~~~

Biến môi trường:

~~~bash
APP_DATASOURCE_REPORTING_MAXIMUMPOOLSIZE=12 java -jar app.jar
~~~

Ở dạng env var chuẩn, dấu chấm trong key trở thành dấu gạch dưới, dấu gạch ngang trong tên field được bỏ đi, rồi tên được chuyển thành chữ hoa.

Nếu không có property source khác ưu tiên cao hơn, `maximumPoolSize` sẽ nhận `12` từ biến môi trường, còn `minimumIdle` vẫn nhận `2` từ YAML. Các field được quyết định theo từng property, không phải lấy toàn bộ cấu hình từ một “file chiến thắng”.

Tương tự, với chế độ mặc định Spring Boot:

~~~bash
java -jar app.jar --app.datasource.reporting.maximum-pool-size=16
~~~

đối số dòng lệnh có thể ghi đè giá trị tương ứng trong file. Nếu ứng dụng đã tắt command-line property source bằng `setAddCommandLineProperties(false)`, giá trị từ kênh đó không còn tự tham gia vào `Environment`.

Dù cấu hình đến từ file, JVM system properties hay biến môi trường, `@ConfigurationProperties` trên `@Bean` vẫn bind vào **cùng một object**.

## 7. Khác với viết thủ công từng `setXxx(...)`

Có thể cấu hình một đối tượng thư viện bằng cách đọc `Environment` thủ công:

~~~java
@Bean
public HikariDataSource reportingDataSource(Environment environment) {
    HikariDataSource ds = new HikariDataSource();
    ds.setJdbcUrl(environment.getRequiredProperty(
            "app.datasource.reporting.jdbc-url"));
    ds.setUsername(environment.getRequiredProperty(
            "app.datasource.reporting.username"));
    ds.setMaximumPoolSize(environment.getProperty(
            "app.datasource.reporting.maximum-pool-size",
            Integer.class, 8));
    return ds;
}
~~~

Cách này có thể phù hợp khi cần logic tùy biến. Tuy nhiên, khi nhiều field cần bind, nó dễ dẫn đến:

- Lặp lại nhiều tên property dạng chuỗi trong mã Java.
- Tự xử lý default và conversion lặp lại.
- Dễ quên bind field mới khi thư viện bổ sung property.
- Khó nhìn thấy toàn bộ nhóm cấu hình từ một prefix.

Với JavaBean có setter phù hợp, cấu hình thông qua annotation ngắn hơn:

~~~java
@Bean
@ConfigurationProperties(prefix = "app.datasource.reporting")
HikariDataSource reportingDataSource() {
    return new HikariDataSource();
}
~~~

Nhưng việc ít mã hơn **không tự đảm bảo giá trị được kiểm tra đúng**. Binding không thay thế các ràng buộc bắt buộc của ứng dụng, và các thuộc tính không có setter cũng không tự được hỗ trợ.

## 8. Không cần `@ConfigurationPropertiesScan` cho phương thức `@Bean`

Sự khác biệt giữa các hình thức đăng ký:

| Trường hợp | Cách đăng ký | Vai trò |
| --- | --- | --- |
| Tự viết class `AppProperties` có `@ConfigurationProperties` | `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(AppProperties.class)` | Đưa type properties vào Spring context |
| Class thư viện ngoài được tạo bởi `@Bean` | `@Configuration` + `@Bean` + `@ConfigurationProperties` trên method | Bind properties trực tiếp vào bean được tạo |
| Type properties đã được đánh dấu `@Component` | Quét component + JavaBean binding nếu phù hợp | Cơ chế tạo bean thông thường; không phải constructor binding chuyên dụng |

Ví dụ đủ để Spring Boot xử lý bean thư viện:

~~~java
@Configuration(proxyBeanMethods = false)
public class VendorConfiguration {
    @Bean
    @ConfigurationProperties("third-party.client")
    VendorClientConfig vendorClientConfig() {
        return new VendorClientConfig();
    }
}
~~~

`VendorClientConfig` là tên minh họa cho một class thư viện có getter/setter. Không cần thêm `@ConfigurationPropertiesScan` chỉ vì annotation đặt trên `@Bean`.

Tất nhiên, lớp `VendorConfiguration` phải nằm trong vùng mà Spring đăng ký được. Nếu đặt nó ở package nằm ngoài component scan, hãy import qua `@Import(VendorConfiguration.class)` hoặc đăng ký một cách tường minh.

## 9. JavaBean binding cần gì ở đối tượng bên ngoài?

Không phải mọi class từ thư viện đều dùng được cách này.

### 9.1. Trường hợp phù hợp: mutable JavaBean

Giả sử thư viện có class:

~~~java
// Ví dụ mô phỏng API của một thư viện ngoài.
public class VendorClientConfig {
    private String endpoint;
    private int maxConnections = 5;
    private boolean enabled;

    public String getEndpoint() {
        return endpoint;
    }
    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public int getMaxConnections() {
        return maxConnections;
    }
    public void setMaxConnections(int maxConnections) {
        this.maxConnections = maxConnections;
    }

    public boolean isEnabled() {
        return enabled;
    }
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

Nếu thư viện thực sự cung cấp cấu trúc như trên:

~~~java
@Configuration(proxyBeanMethods = false)
public class VendorConfiguration {
    @Bean
    @ConfigurationProperties(prefix = "vendor.client")
    public VendorClientConfig vendorClientConfig() {
        return new VendorClientConfig();
    }
}
~~~

Và YAML:

~~~yaml
vendor:
  client:
    endpoint: https://api.example.test
    max-connections: 20
    enabled: true
~~~

Binder có thể gọi các setter để thiết lập các thuộc tính `endpoint`, `maxConnections`, `enabled`.

### 9.2. Trường hợp không phù hợp: object bất biến

Một số thư viện dùng class bất biến:

~~~java
// Mã minh họa một kiểu API bên ngoài.
public final class ImmutableVendorClient {
    private final String endpoint;
    private final int maxConnections;

    public ImmutableVendorClient(String endpoint, int maxConnections) {
        this.endpoint = endpoint;
        this.maxConnections = maxConnections;
    }

    // Chỉ có getter, không có setter.
}
~~~

Không thể kỳ vọng:

~~~java
@Bean
@ConfigurationProperties(prefix = "vendor.client")
public ImmutableVendorClient client() {
    return new ImmutableVendorClient("default", 5);
}
~~~

sẽ thay được hai field `final` chỉ bằng annotation. **Constructor binding không áp dụng cho các bean được tạo qua các phương thức `@Bean` thông thường.**

Giải pháp thích hợp là bind một **đối tượng properties do ứng dụng sở hữu**, rồi dùng nó để gọi constructor hoặc builder của thư viện:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "vendor.client")
public record VendorClientProperties(
        String endpoint,
        int maxConnections) {
}
~~~

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(VendorClientProperties.class)
public class VendorClientConfiguration {

    @Bean
    public ImmutableVendorClient vendorClient(VendorClientProperties properties) {
        return new ImmutableVendorClient(
                properties.endpoint(),
                properties.maxConnections());
    }
}
~~~

Đây là ví dụ mô hình để biểu diễn cách xử lý class bất biến; trong dự án thật thay `ImmutableVendorClient` bằng constructor/builder thực tế của thư viện.

**Nguyên tắc:** nếu thư viện có JavaBean setters, có thể bind trực tiếp lên `@Bean`. Nếu thư viện chỉ có constructor/builder, bind vào class properties trung gian rồi tạo vendor object tường minh.

## 10. Mẫu hai bước: bind `HikariConfig` rồi tạo `HikariDataSource`

Trong một số trường hợp cần cấu hình đầy đủ trước khi khởi tạo thành phần, thay vì bind trực tiếp vào datasource, có thể bind vào **config bean của HikariCP** rồi tạo datasource.

~~~java
package com.example.config;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AnalyticsDataSourceConfiguration {

    @Bean("analyticsHikariConfig")
    @ConfigurationProperties(prefix = "app.datasource.analytics")
    public HikariConfig analyticsHikariConfig() {
        return new HikariConfig();
    }

    @Bean(name = "analyticsDataSource", destroyMethod = "close")
    public HikariDataSource analyticsDataSource(
            @Qualifier("analyticsHikariConfig") HikariConfig config) {
        return new HikariDataSource(config);
    }
}
~~~

YAML:

~~~yaml
app:
  datasource:
    analytics:
      jdbc-url: jdbc:postgresql://localhost:5432/analytics
      username: analytics_user
      password: "${ANALYTICS_DB_PASSWORD}"
      maximum-pool-size: 6
      pool-name: analytics-pool
~~~

Luồng chạy:

~~~text
Spring tạo HikariConfig bằng @Bean
                |
                v
@ConfigurationProperties bind app.datasource.analytics.*
                |
                v
HikariConfig đã có jdbcUrl, username, pool size...
                |
                v
Spring tạo analyticsDataSource(HikariConfig config)
                |
                v
new HikariDataSource(config)
                |
                v
inject datasource đã được cấu hình
~~~

Ưu điểm của mẫu hai bước là có **config bean đã bind** để truyền cho constructor của thành phần thư viện. Nó đặc biệt phù hợp nếu constructor làm công việc phải nhận các thuộc tính chính xác ngay lúc tạo.

HikariCP có những ràng buộc và thời điểm khởi tạo pool riêng; cần quản lý lifecycle và kết nối thật theo mục tiêu của ứng dụng. Không phải mọi thư viện đều có một class `Config` tách biệt, nên mẫu hai bước là một chiến lược khi API hỗ trợ, không phải quy tắc bắt buộc.

## 11. Giá trị mặc định và mức ưu tiên của cấu hình

Khi dùng `@ConfigurationProperties` trên `@Bean`, binder thường chỉ thiết lập các property có trong dữ liệu cấu hình phù hợp. Những field không được bind có thể giữ giá trị mặc định do constructor hoặc thư viện cung cấp.

Ví dụ:

~~~java
@Bean
@ConfigurationProperties("vendor.client")
VendorClientConfig vendorClientConfig() {
    VendorClientConfig config = new VendorClientConfig();
    config.setMaxConnections(5);
    return config;
}
~~~

Nếu YAML chỉ có:

~~~yaml
vendor:
  client:
    endpoint: https://api.example.test
~~~

thì `maxConnections` có thể tiếp tục là `5` do factory method đã thiết lập, trong khi `endpoint` được binder điền từ YAML.

Nhưng nếu YAML có:

~~~yaml
vendor:
  client:
    max-connections: 20
~~~

thì binder có thể ghi đè giá trị mặc định `5` bằng `20`.

Cần nhớ **mặc định ở object** khác với một property mặc định trong `Environment`. Một field được set sẵn trong `new VendorClientConfig()` không tự tạo property `vendor.client.max-connections` trong `Environment`. Điều này có thể quan trọng nếu code ở nơi khác gọi `Environment.getProperty(...)` để xác định cấu hình đã được cấp hay chưa.

Với những field mang ý nghĩa bắt buộc, đừng chỉ dựa vào default mơ hồ của thư viện. Hãy kiểm tra rõ ràng yêu cầu nghiệp vụ và cấu hình deployment.

## 12. Cấu hình từ biến môi trường

Với prefix:

~~~java
@ConfigurationProperties(prefix = "app.datasource.reporting")
~~~

và field Java `maximumPoolSize`, biến môi trường theo dạng canonical là:

~~~bash
APP_DATASOURCE_REPORTING_MAXIMUMPOOLSIZE=12
~~~

Lệnh chạy Unix minh họa:

~~~bash
APP_DATASOURCE_REPORTING_MAXIMUMPOOLSIZE=12 \
REPORTING_DB_PASSWORD=example-secret \
java -jar app.jar
~~~

Trong PowerShell:

~~~powershell
$env:APP_DATASOURCE_REPORTING_MAXIMUMPOOLSIZE = "12"
$env:REPORTING_DB_PASSWORD = "example-secret"
java -jar app.jar
~~~

Các giá trị secret ở đây chỉ là ví dụ. Trong production, cung cấp qua secret manager, file mount hoặc cơ chế bảo vệ tương ứng, không dán khóa thật vào lịch sử shell hay log.

Bảng tương ứng:

| Property trong YAML | Biến môi trường dạng chuẩn |
| --- | --- |
| `app.datasource.reporting.jdbc-url` | `APP_DATASOURCE_REPORTING_JDBCURL` |
| `app.datasource.reporting.maximum-pool-size` | `APP_DATASOURCE_REPORTING_MAXIMUMPOOLSIZE` |
| `app.datasource.reporting.minimum-idle` | `APP_DATASOURCE_REPORTING_MINIMUMIDLE` |
| `app.datasource.reporting.pool-name` | `APP_DATASOURCE_REPORTING_POOLNAME` |

Spring Boot hỗ trợ **relaxed binding**: dấu gạch nối trong field kebab-case được bỏ khi chuyển sang tên biến môi trường, còn dấu chấm giữa các thành phần prefix được thay bằng dấu gạch dưới. Đây là quy tắc chính thống cho binding; không nên tự ý thêm dấu gạch dưới giữa mọi từ của camelCase rồi mặc định chúng tương đương.

## 13. Hạn chế và tình huống không bind được

### 13.1. Không có setter hoặc property không ghi được

Nếu class chỉ có getter mà không hỗ trợ setter, binder không thể tùy ý thay giá trị như một JavaBean mutable thông thường. Một số collection lồng nhau có thể được cập nhật khi đối tượng đã được khởi tạo và getter trả về collection mutable, nhưng không có nghĩa mọi field read-only đều có thể bind.

Với thành phần bên ngoài không hỗ trợ JavaBean binding, dùng properties trung gian hoặc adapter/factory thay vì cố buộc annotation trực tiếp làm việc.

### 13.2. Property name không khớp

Ví dụ `jdbc-url` khớp `jdbcUrl`, còn `url` không tự trở thành `jdbcUrl` chỉ vì cùng ý nghĩa. Nếu thư viện dùng tên field đặc thù, phải đọc tài liệu API của nó.

### 13.3. Đối tượng đã hoạt động trước khi binder gán giá trị

Không nên tạo kết nối, mở socket, chạy thread hoặc dùng pool ngay trong `@Bean` method nếu chúng cần các property mà binder **chưa kịp điền**:

~~~java
@Bean
@ConfigurationProperties("app.datasource.reporting")
HikariDataSource reportingDataSource() throws Exception {
    HikariDataSource ds = new HikariDataSource();

    // Không nên: có thể dùng pool trước khi @ConfigurationProperties bind.
    // ds.getConnection();

    return ds;
}
~~~

Nếu cần khởi tạo đối tượng bằng constructor với giá trị đã bind, sử dụng mẫu `HikariConfig` hoặc properties trung gian rồi tạo bean phụ thuộc.

### 13.4. Cấu hình sai kiểu

Nếu `maximum-pool-size: abc` nhưng setter yêu cầu `int`, conversion có thể thất bại và làm startup lỗi. Nếu `maximum-pool-size: -5` chuyển được thành `int`, class thư viện vẫn có thể từ chối ở validation riêng. Cần phân biệt **chuyển đổi kiểu** với **ràng buộc hợp lệ của thư viện**.

### 13.5. Unknown properties bị bỏ qua

Một số chế độ binding của `@ConfigurationProperties` cho phép bỏ qua property không được ánh xạ, theo thuộc tính `ignoreUnknownFields` của annotation. Vì vậy lỗi gõ nhầm tên như `maximun-pool-size` có thể không tạo ra kết quả mong muốn mà không báo lỗi rõ ràng.

Nên dùng tên property được vendor hỗ trợ, kiểm tra cấu hình hiệu lực trong môi trường thử nghiệm và bổ sung validation cho những field bắt buộc.

### 13.6. Nhiều bean cùng loại

Đăng ký một bean `HikariDataSource` riêng có thể ảnh hưởng tới lựa chọn bean của Spring DataSource/JPA auto-configuration. Nếu có nhiều bean `DataSource`, cần quản lý tên, `@Primary` khi có datasource mặc định, `@Qualifier` cho dependency rõ ràng và transaction manager phù hợp. Không đặt tên bean giống nhau hoặc để nhiều bean không thể phân biệt nếu ứng dụng cần tự động inject đúng một instance.

## 14. Validation cho object của thư viện ngoài

Đặt `@ConfigurationProperties` lên method không cho bạn quyền bổ sung `@NotBlank`, `@Min` hay các annotation khác lên field trong JAR của thư viện. Vì vậy không nên mặc định rằng bean của vendor đã có **Bean Validation theo nghiệp vụ của ứng dụng**.

Một cách an toàn là tạo **properties class do ứng dụng quản lý**, có ràng buộc rõ ràng, rồi dùng dữ liệu đã validate để tạo vendor bean.

Ví dụ:

~~~java
package com.example.config;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "vendor.client")
public record VendorClientProperties(
        @NotBlank String endpoint,
        @Min(1) int maxConnections) {
}
~~~

Đăng ký type này bằng `@EnableConfigurationProperties(VendorClientProperties.class)` hoặc `@ConfigurationPropertiesScan`. Ở Spring Boot 3.x, cần một Bean Validation implementation phù hợp, thường lấy qua `spring-boot-starter-validation`.

Tạo vendor bean:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(VendorClientProperties.class)
public class VendorClientConfiguration {

    @Bean
    public ImmutableVendorClient vendorClient(VendorClientProperties props) {
        return new ImmutableVendorClient(
                props.endpoint(),
                props.maxConnections());
    }
}
~~~

Mẫu này đặc biệt có ích khi cần fail-fast với giá trị thiếu, rỗng, sai khoảng hoặc điều kiện bảo mật. Nó cũng có thể dùng với vendor object mutable nếu dự án muốn thẩm định trước khi gọi các setter.

Đối với HikariCP, class thư viện có validation riêng cho một số thiết lập của pool, nhưng điều đó không tự thay thế toàn bộ yêu cầu nghiệp vụ như “chỉ kết nối HTTPS” của một HTTP client hoặc “chỉ dùng database được phép”.

## 15. So sánh `@ConfigurationProperties` trên `@Bean` với `@Value`

Một cách khác là gán thủ công bằng `@Value`:

~~~java
@Bean
VendorClientConfig vendorClientConfig(
        @Value("${vendor.client.endpoint}") String endpoint,
        @Value("${vendor.client.max-connections:5}") int maxConnections) {

    VendorClientConfig config = new VendorClientConfig();
    config.setEndpoint(endpoint);
    config.setMaxConnections(maxConnections);
    return config;
}
~~~

Với một hoặc hai giá trị và logic tạo object đơn giản, `@Value` có thể chấp nhận được. Nhưng khi số property tăng, cách này kém thuận tiện.

| Tiêu chí | `@ConfigurationProperties` trên `@Bean` | `@Value` trong factory method |
| --- | --- | --- |
| Nhóm property theo prefix | Có | Phải ghi từng placeholder |
| Relaxed binding | Có | Hỗ trợ hạn chế hơn theo cách dùng placeholder |
| Chuyển đổi kiểu | Binder/ConversionService | Placeholder và type conversion |
| Số dòng khi nhiều setter | Thường ngắn | Tăng theo số trường |
| Đòi hỏi vendor class mutable JavaBean | Thường có | Không bắt buộc nếu tự gọi constructor/builder |
| Validation nghiệp vụ | Cần cấu hình/kiểm tra bổ sung | Cần kiểm tra bổ sung |
| Dùng cho class bất biến chỉ có constructor | Không trực tiếp | Có thể tạo object bằng tham số đã inject |

Không có quy tắc phải dùng một cách cho mọi thư viện. Chọn dựa trên API vendor, khả năng thay đổi cấu hình, mức độ rõ ràng và nhu cầu kiểm soát lỗi.

## 16. Trường hợp có nhiều cấu hình cho cùng một loại thư viện

Ví dụ hệ thống có hai HikariCP datasource:

~~~yaml
app:
  datasource:
    reporting:
      jdbc-url: jdbc:postgresql://localhost:5432/reporting
      maximum-pool-size: 8

    analytics:
      jdbc-url: jdbc:postgresql://localhost:5432/analytics
      maximum-pool-size: 4
~~~

Có thể tạo hai bean dùng hai prefix khác nhau:

~~~java
@Configuration(proxyBeanMethods = false)
public class MultipleDataSourceConfiguration {

    @Bean(name = "reportingDataSource", destroyMethod = "close")
    @ConfigurationProperties(prefix = "app.datasource.reporting")
    public HikariDataSource reportingDataSource() {
        return new HikariDataSource();
    }

    @Bean(name = "analyticsDataSource", destroyMethod = "close")
    @ConfigurationProperties(prefix = "app.datasource.analytics")
    public HikariDataSource analyticsDataSource() {
        return new HikariDataSource();
    }
}
~~~

Bean sử dụng:

~~~java
@Service
public class AnalyticsJob {
    private final DataSource analyticsDataSource;

    public AnalyticsJob(
            @Qualifier("analyticsDataSource") DataSource analyticsDataSource) {
        this.analyticsDataSource = analyticsDataSource;
    }
}
~~~

Hai bean cùng class nhưng lấy giá trị từ **hai namespace riêng**, nên không ghi đè qua lại chỉ vì cả hai dùng `HikariDataSource`. Tuy nhiên, như đã lưu ý, ứng dụng nhiều datasource còn cần thiết kế transaction managers, repository/JPA mappings, lựa chọn primary và cơ chế startup phù hợp.

Nếu không muốn duy trì nhiều datasource riêng, không cần tạo nhiều bean chỉ để minh họa annotation; đây là tình huống cho thấy việc chọn **prefix + tên bean** có tác động đến kiến trúc.

## 17. Kiểm tra giá trị đã được bind như thế nào?

Trong môi trường phát triển, có thể inject bean vendor rồi đọc một số property không nhạy cảm:

~~~java
import com.zaxxer.hikari.HikariDataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ReportingDiagnostics {

    @Bean
    ApplicationRunner printPoolSettings(
            @Qualifier("reportingDataSource") HikariDataSource ds) {

        return args -> {
            System.out.println("Pool name = " + ds.getPoolName());
            System.out.println("Max size = " + ds.getMaximumPoolSize());
            System.out.println("JDBC URL = " + ds.getJdbcUrl());
        };
    }
}
~~~

Ví dụ chỉ nhằm quan sát việc binding trong môi trường kiểm thử. URL database có thể chứa thông tin hạ tầng, nên production cần hạn chế log và phân quyền. Tuyệt đối không log `ds.getPassword()`.

Spring Boot Actuator, khi được bật và bảo vệ đúng cách, có thể giúp theo dõi cấu hình đã bind qua `/actuator/configprops` và kiểm tra property sources qua `/actuator/env`. Các endpoint có thể tiết lộ thông tin nhạy cảm; không nên mở công khai chỉ để debug.

Một checklist chẩn đoán:

1. `@Configuration` có được component scan/import vào context không?
2. `@Bean` có được tạo thực sự hay bị điều kiện khác loại bỏ?
3. Prefix có khớp chính xác với cấu trúc YAML/Properties?
4. Class vendor có getter/setter tương ứng và setter nhận kiểu có thể convert?
5. Có nguồn cấu hình khác ghi đè key bằng giá trị không mong muốn?
6. Bean có đang được sử dụng trước khi binding hoàn thành không?
7. Có nhiều bean cùng loại khiến injection không chọn đúng instance?
8. Vendor có validation hoặc lifecycle hạn chế giá trị/ thời điểm đặt setter?

Khi có lỗi, hãy kiểm tra **nguồn property hiệu lực**, **tên JavaBean property** và **thời điểm khởi tạo** trước khi cho rằng `@ConfigurationProperties` bị bỏ qua.

## 18. Bài tập áp dụng

Giả sử một thư viện cung cấp class:

~~~java
public class VendorSchedulerConfig {
    private int workerCount = 2;
    private boolean enabled = false;
    private String queueName;

    public int getWorkerCount() { return workerCount; }
    public void setWorkerCount(int workerCount) {
        this.workerCount = workerCount;
    }

    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getQueueName() { return queueName; }
    public void setQueueName(String queueName) {
        this.queueName = queueName;
    }
}
~~~

Dự án đăng ký bean:

~~~java
@Configuration(proxyBeanMethods = false)
class SchedulerConfiguration {

    @Bean
    @ConfigurationProperties(prefix = "vendor.scheduler")
    VendorSchedulerConfig vendorSchedulerConfig() {
        return new VendorSchedulerConfig();
    }
}
~~~

File `application.yml`:

~~~yaml
vendor:
  scheduler:
    worker-count: 6
    enabled: true
    queue-name: priority
~~~

**Câu hỏi 1:** khi bean được bind, ba field có giá trị nào?

**Đáp án:** `workerCount=6`, `enabled=true`, `queueName=priority`. Binder dùng prefix `vendor.scheduler` và relaxed binding để ánh xạ `worker-count` sang `workerCount`.

**Câu hỏi 2:** xóa `worker-count` khỏi YAML thì giá trị nào được giữ?

Nếu không có nguồn khác cung cấp property, `workerCount` có thể giữ mặc định `2` do constructor/field initializer của thư viện thiết lập. Binder không tự biến giá trị mặc định đó thành một key trong `Environment`.

**Câu hỏi 3:** đổi YAML thành `workers-count: 6` thì sao?

Tên `workers-count` không tương ứng với JavaBean property `workerCount`. Nếu unknown fields được bỏ qua, `workerCount` có thể vẫn là `2` mà không có lỗi rõ ràng. Cần dùng đúng tên được thư viện hỗ trợ hoặc thiết lập cấu hình strict/validation phù hợp.

**Câu hỏi 4:** nếu `VendorSchedulerConfig` không có setter, chỉ nhận constructor `VendorSchedulerConfig(int, boolean, String)` thì áp dụng annotation trên `@Bean` có tự truyền ba đối số constructor không?

**Không.** Factory method phải tự tạo object. Hãy bind một class properties của ứng dụng (có thể là record với constructor binding), rồi truyền giá trị đã bind cho constructor vendor trong một phương thức `@Bean`.

## 19. Tổng kết

- **Dùng `@ConfigurationProperties` trên `@Bean`** khi cần bind cấu hình vào đối tượng JavaBean do thư viện bên ngoài cung cấp mà không sửa class đó.
- **Annotation nằm tại bean registration point:** Spring gọi factory method, tạo instance, rồi binder thiết lập các properties trên object theo prefix.
- **Chọn đúng tên setter và property của vendor:** ví dụ HikariCP dùng `jdbc-url` để bind `jdbcUrl`; không tùy ý thay bằng `url`.
- **Cấu hình vẫn lấy từ `Environment` theo thứ tự ưu tiên nguồn** và hỗ trợ relaxed binding.
- **Không dùng constructor binding trực tiếp cho bean tạo bằng `@Bean`**. Với class bất biến hoặc builder-only, dùng properties trung gian rồi tạo vendor object tường minh.
- **Không mặc định có validation nghiệp vụ:** phải kiểm tra field bắt buộc, giá trị sai kiểu, phạm vi và các ràng buộc bảo mật.
- **Quản lý vòng đời và xung đột bean:** nhất là với datasource, connection pools và nhiều instance cùng class.

### Tài liệu tham khảo

- Spring Boot Reference — Externalized Configuration, Third-party Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.third-party-configuration
- Spring Boot Reference — Type-safe Configuration Properties: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties
- Spring Boot Reference — Relaxed Binding: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.relaxed-binding
- HikariCP: https://github.com/brettwooldridge/HikariCP

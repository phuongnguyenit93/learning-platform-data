# Xác định thuộc tính đầu vào, bean đầu ra và điểm tùy chỉnh công khai khi đọc mã Auto-configuration

## 1. Mục tiêu: biến một lớp auto-configuration thành bản đồ có thể kiểm chứng

Một lớp Spring Boot auto-configuration thường chỉ là điểm bắt đầu. Những property nó nhận có thể được bind vào một lớp `@ConfigurationProperties`; các bean mà ứng dụng nhìn thấy có thể được tạo ở những lớp `@Configuration` lồng nhau hoặc được `@Import`; hành vi có thể được điều chỉnh qua property, một bean người dùng cung cấp, hoặc một callback interface công khai.

Khi đọc mã nguồn, cần trả lời được bốn câu hỏi:

1. **Input:** cấu hình nào đi vào auto-configuration? Property prefix là gì, từng key có ý nghĩa gì, điều kiện nào đọc trực tiếp từ `Environment`?
2. **Điều kiện:** lớp và từng nhánh/bean method chỉ được áp dụng khi nào? Classpath, property, bean có sẵn, resource hoặc môi trường nào được kiểm tra?
3. **Output:** bean nào được đăng ký? Tên, kiểu trả về, scope, dependency và nguồn định nghĩa của chúng là gì?
4. **Extension points:** ứng dụng có thể thay đổi hành vi qua property, custom bean, `Customizer`, `Configurer`, `ConnectionDetails` hay một interface công khai nào?

Bản đồ này giúp trả lời những câu hỏi thực tế: đổi property nào để chọn pool khác, vì sao bean mặc định không xuất hiện, làm thế nào để thay một dependency mà vẫn giữ phần còn lại của auto-configuration, và API nào được thiết kế để ứng dụng mở rộng.

Bài viết dùng **Spring Boot 3.5.x, Spring Framework 6.2 và Java 17+** làm mốc. Khi đọc một dự án khác, hãy dùng source/Javadoc đúng phiên bản của dependency trong dự án; không suy luận package, property hoặc callback từ nhánh `main` mới nhất.

## 2. Mô hình tổng quát: từ candidate đến bean trong context

Có thể hình dung quá trình như sau:

~~~text
META-INF/spring/...AutoConfiguration.imports
                   |
                   v
       Danh sách auto-configuration ứng viên
                   |
                   v
   Annotation ở cấp class (@Conditional...)
                   |
                   v
  @EnableConfigurationProperties / @Import
                   |
                   v
  Các nhánh cấu hình lồng nhau / bean methods
                   |
                   v
   Điều kiện của từng nhánh và từng bean
                   |
                   v
  Bean definitions được đăng ký vào context
                   |
                   v
      Instance được tạo khi Spring cần
~~~

Mỗi lớp cần được đọc ở đúng vai trò:

- **Imports file:** cho biết lớp nào được công bố là auto-configuration candidate.
- **Class annotations:** điều kiện bao trùm toàn bộ cấu hình, thứ tự trước/sau, property types được bật và cấu hình được import.
- **Nested configuration:** chia các nhánh theo loại implementation hoặc môi trường.
- **Bean methods:** xác định bean đầu ra, kiểu, tên, tham số phụ thuộc và điều kiện riêng.
- **Configuration properties:** mô tả các input có cấu trúc, kiểu dữ liệu và default.
- **Customizer/configurer/connection details:** điểm mở rộng để ứng dụng can thiệp vào quá trình tạo bean.

Cần phân biệt **bean definition** và **bean instance**. Auto-configuration trước hết quyết định bean definition nào được đăng ký. Instance singleton thường được tạo khi context khởi tạo, nhưng lazy bean hoặc prototype có thời điểm tạo khác. Vì vậy, đọc được một phương thức `@Bean` không có nghĩa mọi lần khởi động đều có instance tương ứng; phải xét toàn bộ điều kiện và vòng đời.

## 3. Chuẩn bị đúng source trước khi đọc

### 3.1. Xác định phiên bản thật đang chạy

Đầu tiên, xác định Spring Boot version được quản lý bởi Maven/Gradle:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
</parent>
~~~

Hoặc kiểm tra dependency tree:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.boot
~~~

Với Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-boot-autoconfigure --configuration runtimeClasspath
~~~

Không chỉ nhìn version ghi trong một starter: dependency management, BOM hoặc version override có thể khiến các module Boot không đồng nhất như mong đợi. Hãy xác định version thực tế của `spring-boot`, `spring-boot-autoconfigure` và các module liên quan.

### 3.2. Mở source JAR hoặc source trong IDE

Cách đọc tốt nhất là dùng **source JAR đúng version**. Với Maven:

~~~bash
mvn dependency:sources
~~~

Sau đó IDE có thể mở declaration/source của class từ dependency. Nếu cần kiểm tra JAR:

~~~bash
jar tf ~/.m2/repository/org/springframework/boot/spring-boot-autoconfigure/3.5.16/spring-boot-autoconfigure-3.5.16.jar
~~~

Trên Windows PowerShell, đường dẫn Maven local repository thường nằm dưới thư mục user profile; thay đường dẫn tương ứng với máy đang chạy.

Trong IDE:
1. Ctrl/Cmd-click tên auto-configuration.
2. Mở class và các class được `@Import`.
3. Mở `@ConfigurationProperties` type.
4. Theo tiếp factory method và customizer interface.
5. Dùng chức năng Find Usages để xác định nơi framework thực sự gọi extension point.

Nếu source JAR chưa có, có thể dùng Javadoc hoặc source trên GitHub với **tag tương ứng**. Không dùng một class ở Spring Boot 4.x để kết luận về package hay hành vi của Spring Boot 3.5.x.

### 3.3. Tìm file khai báo auto-configuration

Spring Boot 3.x dùng imports file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

File chứa danh sách fully qualified class names, mỗi dòng là một candidate. Khi phát triển starter riêng, đây là nơi khai báo auto-configuration của thư viện.

Không nhầm file này với:
- `META-INF/spring.factories`: vẫn còn được sử dụng cho nhiều loại factory/extension khác, nhưng không còn là cách đăng ký auto-configuration candidate tiêu chuẩn trong Boot 3.x.
- `META-INF/spring-configuration-metadata.json`: metadata mô tả property và hỗ trợ IDE.
- `spring-autoconfigure-metadata.properties`: metadata tối ưu việc lọc candidate; không phải danh sách property public để người dùng cấu hình.

## 4. Quy trình đọc source theo thứ tự

### Bước 1 — Đọc annotation trên lớp chính

Tìm các annotation sau:

| Annotation | Cần ghi nhận |
| --- | --- |
| `@AutoConfiguration` | Đây có phải auto-configuration không? Có `before`, `after` hoặc tên class ordering nào? |
| `@ConditionalOnClass` | Thư viện/class nào phải có trên classpath? |
| `@ConditionalOnMissingBean` | Bean nào do người dùng cung cấp sẽ khiến cấu hình back off? |
| `@ConditionalOnBean` | Cần có bean nào từ cấu hình khác? |
| `@ConditionalOnProperty` | Property nào bật/tắt class hoặc nhánh? `havingValue` và `matchIfMissing` ra sao? |
| `@ConditionalOnWebApplication` / `@ConditionalOnNotWebApplication` | Phạm vi web/non-web nào được hỗ trợ? |
| `@EnableConfigurationProperties` | Những class properties nào được đăng ký và bind? |
| `@Import` | Cần đọc tiếp những cấu hình nào? |
| `@ImportAutoConfiguration` | Có auto-configuration khác được nhập tường minh không? |

**Không dừng lại ở class-level condition.** Một lớp có thể match nhưng bean method bên trong lại không match. Mỗi nhánh nested configuration cũng có thể có điều kiện riêng.

### Bước 2 — Theo các class được import

Ví dụ:

~~~java
@AutoConfiguration
@EnableConfigurationProperties(ClientProperties.class)
@Import(ClientTransportConfiguration.class)
class ClientAutoConfiguration {
}
~~~

Ba class trên chưa đủ để xác định bean đầu ra. Cần mở tiếp `ClientTransportConfiguration`, các nested configuration và method được import.

Có thể một lớp cấu hình chỉ gom điều kiện và import; bean thật được khai báo ở class khác. Vì thế, đừng chỉ tìm `@Bean` trong file có tên `*AutoConfiguration.java`.

### Bước 3 — Tìm tất cả property prefix và nơi đọc property

Tìm:

- `@ConfigurationProperties("...")`;
- `@EnableConfigurationProperties(...)`;
- `@ConfigurationPropertiesScan`;
- `@ConfigurationProperties` trên phương thức `@Bean`;
- `@ConditionalOnProperty`;
- `Environment.getProperty(...)`;
- `Binder.get(environment)`;
- `@Value` placeholder.

**Một property có thể được đọc theo nhiều cơ chế.** Ví dụ, `spring.datasource.type` vừa là property được bind vào `DataSourceProperties`, vừa có thể được đọc trong một condition để quyết định có chọn nhánh pooled DataSource hay không.

Tách ba nhóm:

1. **Property được bind:** trở thành field trong một object cấu hình.
2. **Property điều kiện:** được dùng để quyết định cấu hình/bean có match không.
3. **Property được đọc trực tiếp:** được dùng qua `Environment`, `Binder` hoặc placeholder ở một vị trí cụ thể.

Một key có thể thuộc nhiều nhóm. Đừng cho rằng mọi field trong `@ConfigurationProperties` đều được dùng trong condition.

### Bước 4 — Lập danh sách bean đầu ra

Tìm tất cả:
- `@Bean`;
- `@Import` dẫn đến class có `@Bean`;
- `ImportSelector` hoặc registrar nếu auto-configuration dùng cơ chế đăng ký động;
- các factory/registrar tạo bean definitions.

Với từng bean, ghi:

| Thuộc tính cần đọc | Cách tìm |
| --- | --- |
| Bean name | Tên method `@Bean`, hoặc giá trị tường minh `@Bean("...")` |
| Return type | Kiểu trả về của method |
| Implementation thật | Lớp được khởi tạo hoặc builder được gọi |
| Condition | Annotation ở class, nested class và method |
| Dependency | Tham số method, constructor và `@DependsOn` |
| Scope/lazy | `@Scope`, `@Lazy`, `@Primary`, các metadata liên quan |
| Back-off | `@ConditionalOnMissingBean` hoặc condition thay thế |
| Nguồn | Class và method thực sự định nghĩa bean |

**Return type quan trọng.** Spring Boot condition thường dựa vào thông tin kiểu sẵn có khi đăng ký bean definition. Một method trả về `Object` dù thực tế tạo `DataSource` có thể khiến type matching kém chính xác hơn method khai báo đúng kiểu.

### Bước 5 — Xác định extension point công khai

Tìm các interface/class có tên hoặc vai trò như:
- `Customizer`;
- `Configurer`;
- `Builder`;
- `ConnectionDetails`;
- `Provider`;
- `Strategy`;
- `Factory`.

Sau đó kiểm tra:
1. Interface có `public` không?
2. Javadoc có mô tả nó là callback hoặc extension point cho ứng dụng không?
3. Framework thu thập nó qua `ObjectProvider`, `orderedStream()`, `List<...>` hay cơ chế khác nào?
4. Callback được áp dụng ở đâu và vào lúc nào?
5. Nó chỉ sửa một bean hay ảnh hưởng đến tất cả builder/bean được tạo qua một factory?
6. Có ordering contract như `@Order`/`Ordered` không?

**Tên gọi chưa đủ để kết luận là API công khai.** Một class package-private có tên `Customizer` hoặc một nested condition nội bộ không phải extension point được hỗ trợ cho ứng dụng. Chỉ ghi nhận điểm mở rộng khi có hợp đồng public và có đường gọi thực tế trong source.

## 5. Ví dụ thật: đọc DataSourceAutoConfiguration trong Spring Boot 3.5

Một ví dụ tốt để luyện đọc source là:

~~~java
org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Javadoc Boot 3.5 mô tả class này là auto-configuration cho `javax.sql.DataSource`. Annotation ở lớp chính có ý nghĩa:

~~~java
@AutoConfiguration(before = SqlInitializationAutoConfiguration.class)
@ConditionalOnClass({
    DataSource.class,
    EmbeddedDatabaseType.class
})
@ConditionalOnMissingBean(type = "io.r2dbc.spi.ConnectionFactory")
@EnableConfigurationProperties(DataSourceProperties.class)
@Import({
    DataSourcePoolMetadataProvidersConfiguration.class,
    DataSourceCheckpointRestoreConfiguration.class
})
public class DataSourceAutoConfiguration {
    // Các nested configuration được khai báo bên dưới.
}
~~~

Đây là trích đoạn minh họa phần class-level annotation trong Boot 3.5; có thể lược bỏ import và một số nội dung phụ để tập trung vào cách đọc.

### 5.1. Input từ class-level annotation

| Thành phần | Ý nghĩa |
| --- | --- |
| `before = SqlInitializationAutoConfiguration.class` | Định nghĩa bean của DataSource auto-configuration trước cấu hình SQL initialization theo ordering contract |
| `@ConditionalOnClass(DataSource.class, EmbeddedDatabaseType.class)` | Cần JDBC DataSource API và embedded database type có trên classpath |
| `@ConditionalOnMissingBean(type = "io.r2dbc.spi.ConnectionFactory")` | Nếu đã có R2DBC ConnectionFactory thì JDBC DataSource auto-configuration này không được áp dụng |
| `@EnableConfigurationProperties(DataSourceProperties.class)` | Đăng ký và bind cấu hình chuẩn có prefix `spring.datasource` |
| `@Import(...)` | Thêm cấu hình metadata provider và checkpoint/restore support |

Một chi tiết dễ bỏ sót: class-level condition kiểm tra **R2DBC ConnectionFactory**. Nếu dự án có dependency R2DBC và đã đăng ký ConnectionFactory, việc không thấy JDBC DataSource tự cấu hình có thể là kết quả của điều kiện này; không nhất thiết là lỗi property URL.

Ordering của auto-configuration điều khiển thứ tự đăng ký bean definitions, không có nghĩa instance của DataSource chắc chắn được tạo trước mọi bean khác. Việc tạo instance còn phụ thuộc dependency graph.

### 5.2. Input properties: DataSourceProperties

Mở class:

~~~java
org.springframework.boot.autoconfigure.jdbc.DataSourceProperties
~~~

Class này được gắn với prefix:

~~~java
@ConfigurationProperties("spring.datasource")
public class DataSourceProperties {
    // Các trường cấu hình DataSource.
}
~~~

Các key chuẩn thường gặp:

| Property | Mục đích |
| --- | --- |
| `spring.datasource.url` | JDBC URL |
| `spring.datasource.username` | Username |
| `spring.datasource.password` | Password |
| `spring.datasource.driver-class-name` | Driver class; thường có thể suy ra từ URL |
| `spring.datasource.type` | Chỉ định implementation DataSource/pool |
| `spring.datasource.name` | Tên database/DataSource theo hợp đồng properties |
| `spring.datasource.generate-unique-name` | Có tạo tên database embedded duy nhất hay không |
| `spring.datasource.embedded-database-connection` | Loại embedded database muốn dùng |
| `spring.datasource.jndi-name` | Tên JNDI của DataSource; nhánh JNDI được xử lý bởi auto-configuration liên quan |

Các field chuẩn nằm trong `DataSourceProperties`; **pool-specific properties** nằm ở prefix riêng của implementation, ví dụ:

~~~properties
spring.datasource.hikari.maximum-pool-size=20
spring.datasource.hikari.connection-timeout=30000
~~~

Nếu dùng Tomcat JDBC pool hoặc DBCP2, prefix và key khác. Đọc lớp cấu hình implementation cụ thể, ví dụ `DataSourceConfiguration.Hikari`, để biết property prefix nào được bind cho pool.

Lưu ý: `spring.datasource.jndi-name` có liên quan đến `DataSourceProperties`, nhưng việc tạo DataSource từ JNDI được thực hiện bởi `JndiDataSourceAutoConfiguration` riêng. Khi thấy property có trong một properties class, vẫn phải truy vết class nào thực sự sử dụng nó.

### 5.3. Condition của nhánh Embedded Database

Trong source của `DataSourceAutoConfiguration`, có nested class:

~~~java
@Configuration(proxyBeanMethods = false)
@Conditional(EmbeddedDatabaseCondition.class)
@ConditionalOnMissingBean({
    DataSource.class,
    XADataSource.class
})
@Import(EmbeddedDataSourceConfiguration.class)
protected static class EmbeddedDatabaseConfiguration {
}
~~~

Điều kiện embedded database xét các yếu tố như:
- `spring.datasource.url` đã được đặt hay chưa;
- có pooled DataSource được hỗ trợ hay không;
- class embedded database có trên classpath không;
- có embedded database driver phù hợp không.

Nếu URL được chỉ định cho một database ngoài, nhánh embedded không còn phù hợp. Nếu pool có sẵn, Boot ưu tiên pooled DataSource thay vì embedded database. Nếu người dùng đã cung cấp `DataSource` hoặc `XADataSource`, nhánh cấu hình mặc định sẽ back off.

### 5.4. Condition của nhánh Pooled DataSource

Nested class khác:

~~~java
@Configuration(proxyBeanMethods = false)
@Conditional(PooledDataSourceCondition.class)
@ConditionalOnMissingBean({
    DataSource.class,
    XADataSource.class
})
@Import({
    DataSourceConfiguration.Hikari.class,
    DataSourceConfiguration.Tomcat.class,
    DataSourceConfiguration.Dbcp2.class,
    DataSourceConfiguration.OracleUcp.class,
    DataSourceConfiguration.Generic.class,
    DataSourceJmxConfiguration.class
})
protected static class PooledDataSourceConfiguration {
}
~~~

Nhánh pooled có thể được chọn khi:
- `spring.datasource.type` được chỉ định; hoặc
- một connection pool được hỗ trợ có trên classpath.

Sau đó các nested implementation configuration tiếp tục quyết định pool nào được dùng. Theo tài liệu Boot 3.5, thứ tự lựa chọn thông dụng ưu tiên **HikariCP**, tiếp theo Tomcat pool, Commons DBCP2 và Oracle UCP khi các lựa chọn trước không có.

Không nên chỉ đọc `PooledDataSourceConfiguration` rồi kết luận pool luôn là Hikari. Hãy mở `DataSourceConfiguration.Hikari`, xem `@ConditionalOnClass`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty` và method `@Bean` cụ thể.

### 5.5. Output beans

Khi các điều kiện phù hợp, kết quả thường bao gồm:

| Bean/nhóm bean | Nguồn | Ý nghĩa |
| --- | --- | --- |
| `dataSource` | Nested configuration cho embedded hoặc pool implementation | DataSource mà ứng dụng inject để làm việc với database |
| `DataSourceProperties` | `@EnableConfigurationProperties` | Bean chứa cấu hình được bind từ `spring.datasource` |
| `JdbcConnectionDetails` mặc định trong nhánh pooled | Bean method tạo property-backed details nếu chưa có bean cùng kiểu | Đóng gói URL, username, password và thông tin kết nối cho DataSource |
| Pool metadata providers | Các class được import | Hỗ trợ đọc metadata của pool, ví dụ thông tin trạng thái/connection |
| Embedded database support | Embedded configuration được import khi nhánh phù hợp | Tạo database nhúng khi classpath và điều kiện cho phép |

Danh sách chính xác tùy classpath và nhánh. Một dự án có Hikari có thể nhận `HikariDataSource`; dự án chỉ có embedded database có thể nhận implementation embedded. Các support bean không nhất thiết xuất hiện ở mọi trường hợp.

Điểm đáng học: **class đầu mối không nhất thiết trực tiếp khai báo bean DataSource**. Nó bật properties, áp dụng conditions và import nested configurations. Muốn biết implementation thật phải theo đến lớp `@Bean` được import.

## 6. Extension points công khai trong ví dụ DataSource

### 6.1. Cấu hình qua property chuẩn

Đây là extension point đơn giản nhất. Người vận hành thay đổi `application.properties`, YAML, environment variables hoặc command line mà không cần sửa source Java.

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: app_user
    password: change-me
    hikari:
      maximum-pool-size: 20
      connection-timeout: 30000
~~~

Boot bind phần chuẩn vào `DataSourceProperties` và phần Hikari vào cấu hình pool tương ứng. Khi đọc source, cần xác định property prefix của từng lớp, không gộp mọi key vào một object.

### 6.2. Cung cấp DataSource của riêng ứng dụng

`@ConditionalOnMissingBean(DataSource.class)` là một extension point quan trọng. Nếu người dùng đăng ký bean DataSource phù hợp trước khi auto-configuration xử lý nhánh đó, Boot sẽ không tạo DataSource mặc định trong nhánh tương ứng.

Ví dụ minh họa:

~~~java
@Configuration(proxyBeanMethods = false)
class MyDatabaseConfiguration {

    @Bean
    DataSource applicationDataSource() {
        return DataSourceBuilder.create()
                .url("jdbc:postgresql://localhost:5432/orders")
                .username("app_user")
                .password("change-me")
                .build();
    }
}
~~~

Đoạn code cần có dependency PostgreSQL driver và một pool/implementation phù hợp trên classpath. Trong ứng dụng thực tế, không hard-code credential; lấy từ secret store hoặc external configuration.

**Back-off không có nghĩa toàn bộ DataSource-related auto-configuration biến mất.** Các cấu hình khác như JDBC template, transaction manager hoặc SQL initialization vẫn có thể được áp dụng nếu điều kiện và dependency phù hợp. Vì vậy phải theo tiếp các auto-configuration downstream.

### 6.3. Cung cấp JdbcConnectionDetails

Trong Spring Boot 3.5, `JdbcConnectionDetails` là interface công khai mô tả thông tin cần để kết nối JDBC. Auto-configuration có thể cung cấp một implementation lấy dữ liệu từ `DataSourceProperties` nếu chưa có bean phù hợp.

Khi cần cấp connection details từ một nguồn riêng, có thể đăng ký bean:

~~~java
@Configuration(proxyBeanMethods = false)
class CustomJdbcConnectionConfiguration {

    @Bean
    JdbcConnectionDetails customJdbcConnectionDetails() {
        return new JdbcConnectionDetails() {

            @Override
            public String getJdbcUrl() {
                return "jdbc:postgresql://localhost:5432/orders";
            }

            @Override
            public String getUsername() {
                return "app_user";
            }

            @Override
            public String getPassword() {
                return "change-me";
            }
        };
    }
}
~~~

Đây là ví dụ minh họa cho extension interface; trong môi trường thật, lấy giá trị từ nguồn cấu hình an toàn. Khi auto-configuration tìm thấy bean `JdbcConnectionDetails` do ứng dụng cung cấp, bean property-backed mặc định có thể back off. Cách này phù hợp với service connection hoặc nguồn cung cấp kết nối riêng.

Không nhầm `JdbcConnectionDetails` với `DataSource`: một bên mô tả thông tin kết nối; bên kia là abstraction dùng để lấy JDBC Connection.

### 6.4. JNDI là một nhánh cấu hình liên quan

Nếu DataSource do application server quản lý, có thể dùng:

~~~properties
spring.datasource.jndi-name=java:comp/env/jdbc/OrdersDS
~~~

Khi đọc source, hãy tìm tiếp `JndiDataSourceAutoConfiguration` và các điều kiện của nó. Đừng giả định mọi nhánh trong `DataSourceAutoConfiguration` đều xử lý JNDI.

### 6.5. Không phải class nội bộ nào cũng là extension point

Các nested condition như `EmbeddedDatabaseCondition` hoặc `PooledDataSourceCondition` chủ yếu là chi tiết triển khai. Không nên để ứng dụng của mình phụ thuộc trực tiếp vào class package-private hoặc protected nội bộ nếu tài liệu không cam kết hỗ trợ.

Extension point nên ưu tiên:
- property có tài liệu;
- bean type được kiểm tra bằng `@ConditionalOnMissingBean`;
- public interface như `JdbcConnectionDetails`;
- builder/customizer/configurer được Javadoc công bố là callback;
- API được ghi trong Reference Guide.

## 7. Theo tiếp bean đầu ra: JdbcTemplateAutoConfiguration

Để thấy vì sao cần truy vết nhiều lớp, tiếp tục mở:

~~~java
org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration
~~~

Trong Boot 3.5, lớp này có các annotation quan trọng:

~~~java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
@ConditionalOnClass({
    DataSource.class,
    JdbcTemplate.class
})
@ConditionalOnSingleCandidate(DataSource.class)
@EnableConfigurationProperties(JdbcProperties.class)
@Import({
    DatabaseInitializationDependencyConfigurer.class,
    JdbcTemplateConfiguration.class,
    NamedParameterJdbcTemplateConfiguration.class
})
public class JdbcTemplateAutoConfiguration {
}
~~~

Những điều cần rút ra:
- Đây là auto-configuration **sau** DataSource auto-configuration.
- Cần cả JDBC DataSource và JdbcTemplate API trên classpath.
- Cần một DataSource candidate duy nhất để inject theo kiểu; nhiều DataSource không rõ primary có thể khiến condition không match.
- Input của template thuộc `JdbcProperties`, prefix `spring.jdbc`, không phải toàn bộ `spring.datasource`.
- Bean `JdbcTemplate` và `NamedParameterJdbcTemplate` được khai báo trong các imported configuration.

Ví dụ property cho template:

~~~properties
spring.jdbc.template.fetch-size=100
spring.jdbc.template.query-timeout=5s
spring.jdbc.template.max-rows=500
~~~

Điều này cho thấy một chuỗi liên kết:
1. `DataSourceAutoConfiguration` tạo DataSource.
2. `JdbcTemplateAutoConfiguration` cần một DataSource có thể chọn duy nhất.
3. `JdbcTemplateConfiguration` và `NamedParameterJdbcTemplateConfiguration` đăng ký template bean.
4. Các bean nghiệp vụ inject `JdbcTemplate` để chạy query.

Nếu muốn biết một property điều chỉnh bean nào, hãy truy ngược từ bean method về properties type. Đừng gán mọi key `spring.jdbc.*` cho `DataSourceProperties` chỉ vì chúng cùng liên quan JDBC.

## 8. Tìm nhanh bằng IDE hoặc ripgrep

Trong source repository hoặc source JAR đã giải nén, có thể dùng:

~~~bash
rg -n "@ConfigurationProperties|@EnableConfigurationProperties" spring-boot-project/spring-boot-autoconfigure/src/main/java
~~~

Tìm điều kiện và bean:

~~~bash
rg -n "@ConditionalOnProperty|@ConditionalOnMissingBean|@ConditionalOnBean|@ConditionalOnClass|@Bean|@Import" path/to/autoconfigure/package
~~~

Tìm callback:

~~~bash
rg -n "Customizer|Configurer|Builder|ConnectionDetails|Provider|Strategy" path/to/autoconfigure/package
~~~

Tìm metadata:

~~~bash
rg --files | rg "AutoConfiguration.imports|spring-configuration-metadata.json|additional-spring-configuration-metadata.json"
~~~

Khi đọc code trong IDE, có thể dùng Find Usages để xác nhận:
- class properties được bật ở đâu;
- customizer được collect và apply ở đâu;
- builder nào được cấp cho ứng dụng;
- bean nào back off khi user bean xuất hiện.

Không chỉ tìm theo tên class. Một customizer public nhưng không có chỗ nào gọi có thể là extension point cho một subsystem khác; phải xác định chính xác ai tiêu thụ nó.

## 9. Metadata của configuration properties

Spring Boot có thể tạo:

~~~text
META-INF/spring-configuration-metadata.json
~~~

File này hỗ trợ IDE autocomplete, mô tả property, kiểu dữ liệu, default value và deprecation khi được khai báo. Có thể kiểm tra metadata trong module auto-configuration hoặc JAR đã build.

Metadata hữu ích để xác định:
- property name canonical;
- type (String, boolean, Duration, Class, enum, list...);
- description;
- default value nếu có;
- property deprecated/replacement;
- nguồn metadata.

Tuy nhiên, metadata không thay thế source:
- Nó không cho biết đầy đủ condition nào sử dụng property.
- Nó không chứng minh một bean sẽ được tạo trong mọi môi trường.
- Property có thể được đọc trực tiếp bằng `Environment` hoặc custom condition mà không có metadata generated.
- Default trong object properties không nhất thiết là một property có mặt trong Environment.

Theo khuyến nghị Spring Boot, property key nên dùng **lowercase kebab-case**, ví dụ `spring.datasource.driver-class-name`. Relaxed binding giúp map key từ file, YAML, system properties và environment variables sang field Java phù hợp.

## 10. Kiểm thử: xác nhận input, output và back-off

Một cách kiểm thử tốt là `ApplicationContextRunner`: tạo context nhỏ, đưa vào property cụ thể, nạp auto-configuration cần kiểm tra và assert bean đầu ra.

Ví dụ dưới đây dùng:
- Spring Boot **3.5.16**;
- Java 17+;
- `spring-boot-starter-jdbc`;
- H2 database trong test;
- `spring-boot-starter-test`.

### 10.1. Dependency Maven

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Nếu dự án đã có parent/BOM quản lý version, không thêm một parent thứ hai; chỉ thêm các dependency còn thiếu.

### 10.2. Test source

Tạo file **`src/test/java/example/DataSourceAutoConfigurationReadingTests.java`**:

~~~java
package example;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import static org.assertj.core.api.Assertions.assertThat;

class DataSourceAutoConfigurationReadingTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    DataSourceAutoConfiguration.class));

    @Test
    void propertiesCreateADataSource() {
        runner.withPropertyValues(
                "spring.datasource.url=jdbc:h2:mem:source_read",
                "spring.datasource.username=sa",
                "spring.datasource.password="
        ).run(context -> {
            assertThat(context).hasSingleBean(DataSource.class);
            assertThat(context).hasSingleBean(DataSourceProperties.class);
            assertThat(context).hasBean("dataSource");
        });
    }

    @Test
    void userDataSourceMakesDefaultDataSourceBackOff() {
        runner.withUserConfiguration(UserDataSourceConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(DataSource.class);
                    assertThat(context).hasBean("applicationDataSource");
                    assertThat(context).doesNotHaveBean("dataSource");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserDataSourceConfiguration {

        @Bean
        DataSource applicationDataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:user_defined", "sa", "");
        }
    }
}
~~~

Dự án test cần `spring-boot-starter-jdbc`, H2 và `spring-boot-starter-test`. Test đầu kiểm tra properties bean và DataSource đầu ra; test thứ hai xác nhận bean do ứng dụng cung cấp làm nhánh DataSource mặc định back off.

**Giới hạn của test:** nó kiểm tra bean registration, không chứng minh mọi truy vấn SQL đều thành công. Nếu cần xác nhận kết nối thật, hãy mở connection hoặc chạy query trong integration test.

### 10.3. Chạy test

~~~bash
mvn test -Dtest=DataSourceAutoConfigurationReadingTests
~~~

Hoặc Maven Wrapper:

~~~bash
./mvnw test -Dtest=DataSourceAutoConfigurationReadingTests
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd test '-Dtest=DataSourceAutoConfigurationReadingTests'
~~~

**Kết quả kỳ vọng:** hai test PASS:
- Khi property JDBC URL có mặt và H2/Hikari có trên classpath, auto-configuration có thể đăng ký một DataSource.
- Khi người dùng cung cấp DataSource bean, nhánh DataSource mặc định back off và bean do ứng dụng cung cấp được giữ lại.

Nếu muốn xác nhận implementation cụ thể, có thể thêm assertion:

~~~java
assertThat(context.getBean(DataSource.class))
        .isInstanceOf(com.zaxxer.hikari.HikariDataSource.class);
~~~

Chỉ assert Hikari khi Hikari thực sự có trong classpath và không có pool khác được chỉ định. Với embedded DB hoặc implementation khác, assertion cần tương ứng.

## 11. Cách lập bảng phân tích cho bất kỳ auto-configuration nào

Sau khi đọc source, hãy ghi lại kết quả trong một bảng thống nhất:

| Nhóm | Câu hỏi cần trả lời | Bằng chứng trong source |
| --- | --- | --- |
| Candidate | Lớp được nạp từ imports file nào? | `AutoConfiguration.imports` |
| Version | Source và Javadoc đúng version nào? | Maven/Gradle dependency tree |
| Class conditions | Cần class/property/bean nào ở cấp lớp? | Annotation trên class |
| Properties | Prefix và các key input là gì? | `@ConfigurationProperties`, metadata, Environment reads |
| Nested conditions | Các nhánh nào được bật? | Nested `@Configuration`, `@Conditional...` |
| Output beans | Bean name, type và implementation nào được tạo? | `@Bean`, imported configuration |
| Dependencies | Bean phụ thuộc những bean nào? | Method parameters, constructors, `@DependsOn` |
| Back-off | User bean nào làm Boot dừng tạo mặc định? | `@ConditionalOnMissingBean` |
| Public extension | Có callback/interface/strategy nào? | Public API + điểm framework gọi |
| Ordering | Phụ thuộc auto-configuration nào trước/sau? | `before`, `after`, `@AutoConfigureOrder` |
| Verification | Test nào chứng minh từng nhánh? | `ApplicationContextRunner`, integration tests |

Khi hoàn thành, bạn có thể mô tả auto-configuration bằng một câu có đủ input, điều kiện và output, ví dụ:

> Khi JDBC API và một pool/embedded database phù hợp có mặt, không có R2DBC ConnectionFactory và chưa có DataSource do ứng dụng cung cấp, Spring Boot bind `spring.datasource.*`, chọn nhánh embedded hoặc pooled phù hợp, rồi đăng ký DataSource cùng các support bean cần thiết.

Câu mô tả này là bản tóm tắt có thể kiểm chứng từ source; nó không thay thế bảng condition chi tiết.

## 12. Những lỗi thường gặp khi đọc source

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Chỉ đọc class `*AutoConfiguration` đầu tiên | Bean có thể nằm trong nested/imported configuration | Theo `@Import` và mở các class được import |
| Tưởng `@ConfigurationProperties` đồng nghĩa bean chắc chắn được dùng | Bean properties có thể được bind nhưng nhánh tiêu thụ nó không match | Theo các method nhận properties và điều kiện tương ứng |
| Xem property condition như toàn bộ input | Property còn có thể được bind hoặc đọc qua Environment | Tìm cả `@ConfigurationProperties`, `@Value`, `Binder`, `Environment` |
| Chỉ ghi tên class, bỏ qua version | Package và property có thể đổi giữa Boot versions | Kiểm tra dependency tree và source JAR đúng version |
| Coi `@ConditionalOnMissingBean` là xóa bean hiện hữu | Nó quyết định đăng ký bean mặc định có tiếp tục hay không | Kiểm tra bean definition do user cung cấp và nhánh condition |
| Cho rằng bean method luôn tạo singleton | Scope có thể khác; instance có thể lazy | Đọc `@Scope`, `@Lazy` và lifecycle |
| Cho rằng mọi class có chữ Customizer là API công khai | Có thể là helper nội bộ hoặc không được framework thu thập | Kiểm tra visibility, Javadoc và nơi callback được gọi |
| Dùng metadata JSON như source hoàn chỉnh | Metadata không mô tả toàn bộ conditions hoặc logic runtime | Đối chiếu source, Javadoc và metadata |
| Đọc một output bean nhưng không theo dependency chain | Bean downstream có thể có condition riêng | Theo các auto-configuration phụ thuộc |
| Chỉ test context startup | Bean có thể tồn tại nhưng cấu hình sai hoặc không dùng được | Assert property binding, type, implementation và hành vi |

## 13. Phân biệt API public với chi tiết nội bộ

Khi phát triển ứng dụng hoặc starter, cần phân biệt:

**Public contract**
- Property prefix/key được tài liệu hóa;
- interface/class public có Javadoc;
- bean type được thiết kế để người dùng override;
- callback mà framework thu thập và gọi;
- annotation và extension API trong Reference Guide.

**Implementation detail**
- nested class package-private/protected không được tài liệu cam kết;
- method private và tên biến nội bộ;
- class condition riêng chỉ dùng để quyết định một nhánh;
- metadata tối ưu import/filter;
- thứ tự nội bộ của collection không được công bố.

Nếu code ứng dụng import trực tiếp implementation detail, nâng cấp Boot có thể làm vỡ build dù hành vi công khai vẫn giữ nguyên. Hãy mở rộng qua API public và test contract thay vì phụ thuộc vào lớp nội bộ.

## 14. Quy trình làm việc thực tế trong một repository

1. Chọn đúng auto-configuration từ Condition Evaluation Report hoặc từ bean mà ứng dụng đang dùng.
2. Xác định version Boot trong dependency tree.
3. Mở source class chính và imports file.
4. Ghi annotation cấp class: classpath, bean, property, ordering.
5. Mở tất cả `@Import` và nested configuration liên quan.
6. Tìm `@ConfigurationProperties`, ghi prefix và các key; đối chiếu configuration metadata.
7. Tìm `@Bean`, lập bảng tên/type/condition/dependencies.
8. Tìm `@ConditionalOnMissingBean` và xác định user bean nào có thể khiến Boot back off.
9. Tìm public customizer/configurer/connection details và điểm gọi thực tế.
10. Theo tiếp auto-configuration downstream để hiểu chuỗi bean hoàn chỉnh.
11. Viết `ApplicationContextRunner` test cho các case match, no-match, user override và property variant.
12. Ghi lại kết quả theo version, không sao chép kết luận từ source branch khác.

Một báo cáo source analysis tốt nên có:
- Tên lớp và version đã đọc;
- input properties;
- class/method conditions;
- bean output và implementation;
- extension point public;
- test chứng minh các trường hợp chính;
- các điều kiện hoặc hành vi phụ thuộc classpath/profile.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Nếu class auto-configuration có `@EnableConfigurationProperties(MyProperties.class)`, đã đủ kết luận bean nghiệp vụ sẽ được tạo chưa?

**Đáp án:** Chưa. Annotation này đăng ký/bind properties bean. Bean nghiệp vụ còn phụ thuộc các nested configuration, `@Bean` method và condition tương ứng.

**Câu 2.** Muốn tìm property prefix, nên tìm ở đâu?

**Đáp án:** Mở class có `@ConfigurationProperties` hoặc bean method gắn annotation này; kiểm tra metadata generated và các nơi đọc `Environment`/`Binder` để tìm property condition bổ sung.

**Câu 3.** Vì sao cần mở nested configuration/imported configuration?

**Đáp án:** Lớp đầu mối có thể chỉ định điều kiện và import các nhánh; bean đầu ra thật sự được khai báo trong các class được import.

**Câu 4.** `@ConditionalOnMissingBean(DataSource.class)` thể hiện extension point gì?

**Đáp án:** Nếu ứng dụng cung cấp DataSource phù hợp trước khi nhánh auto-configuration được đánh giá, Boot có thể bỏ qua DataSource mặc định để giữ bean của ứng dụng.

**Câu 5.** Làm thế nào xác định một Customizer là public extension point thật?

**Đáp án:** Kiểm tra interface public, Javadoc và nơi framework thu thập/gọi nó. Tên class có chữ Customizer không đủ để chứng minh hợp đồng mở rộng.

**Câu 6.** Vì sao cần test bằng `ApplicationContextRunner`?

**Đáp án:** Nó tạo context nhỏ với classpath/property/user beans kiểm soát được, giúp xác minh điều kiện và bean registration theo từng trường hợp mà không cần khởi động toàn ứng dụng.

## 16. Tài liệu tham khảo chính thức

- Spring Boot 3.5 Reference — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 Reference — Externalized Configuration: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Spring Boot 3.5 API — `DataSourceAutoConfiguration`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.html
- Spring Boot 3.5 API — `DataSourceProperties`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceProperties.html
- Spring Boot 3.5 API — `JdbcConnectionDetails`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jdbc/JdbcConnectionDetails.html
- Spring Boot 3.5 API — `JdbcTemplateAutoConfiguration`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jdbc/JdbcTemplateAutoConfiguration.html
- Spring Boot 3.5 Reference — SQL Databases: https://docs.spring.io/spring-boot/3.5/reference/data/sql.html
- Spring Boot 3.5 Appendix — Common Application Properties: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/

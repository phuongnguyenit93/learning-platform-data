# Đọc báo cáo khi thiếu driver, thiếu thông tin kết nối hoặc bean DataSource bị thay thế

> **Spring Boot Auto Configuration → Ví dụ JDBC.** Bài học hướng dẫn đọc lỗi khởi động datasource theo ba nhóm nguyên nhân: JDBC driver không có trên runtime classpath, thông tin kết nối chưa đủ, và auto-configuration đã nhường cho bean DataSource do ứng dụng cung cấp. Nội dung dùng Spring Boot 3.3.x, Java 17+, JDBC và H2 để minh họa; các lỗi với PostgreSQL/MySQL được phân tích riêng.

## 1. Bắt đầu từ câu hỏi: ứng dụng đang thất bại ở giai đoạn nào?

Khi Spring Boot khởi động một ứng dụng JDBC, có nhiều việc diễn ra trước khi câu lệnh SQL đầu tiên chạy:

1. Spring tìm các auto-configuration ứng viên dựa trên classpath và cơ chế đăng ký.
2. Spring đánh giá các điều kiện như **@ConditionalOnClass**, **@ConditionalOnMissingBean** và property.
3. Nếu đủ điều kiện, auto-configuration đăng ký bean **DataSource** cùng các thành phần liên quan.
4. Khi bean được tạo hoặc kết nối được yêu cầu, driver và thông tin kết nối được sử dụng.
5. Ứng dụng mở kết nối đến database; sau đó lỗi mạng, xác thực hoặc SQL mới có thể xuất hiện.

Vì vậy, cùng một thông báo chung như *Failed to configure a DataSource* có thể dẫn đến các nguyên nhân khác nhau. Cần phân biệt:

- **Không tìm thấy driver:** thư viện JDBC tương ứng không được đóng gói hoặc không nạp được ở runtime.
- **Thiếu URL/thông tin kết nối:** Spring không biết cần kết nối đến database nào hoặc chưa có cấu hình đủ để tạo datasource.
- **Không thể kết nối/xác thực:** driver và URL có thể đúng, nhưng database không truy cập được hoặc từ chối đăng nhập.
- **Bean bị thay thế:** ứng dụng đã tự đăng ký DataSource; Spring Boot chủ động bỏ qua cấu hình datasource mặc định.
- **Bean tùy chỉnh bị lỗi:** auto-configuration đã nhường, nhưng factory method của ứng dụng tạo datasource không thành công.

Đừng bắt đầu bằng cách thêm dependency, đổi URL hoặc loại DataSourceAutoConfiguration một cách ngẫu nhiên. Trước tiên hãy tìm **exception gốc**, điều kiện auto-configuration và bean nào thực sự được đăng ký.

## 2. Ba khái niệm phải phân biệt

### 2.1. JDBC driver là gì?

JDBC driver là thư viện thực hiện giao thức kết nối với một hệ quản trị cơ sở dữ liệu. Ví dụ:

| Database | JDBC driver artifact | Driver class thường dùng |
| --- | --- | --- |
| PostgreSQL | org.postgresql:postgresql | org.postgresql.Driver |
| MySQL | com.mysql:mysql-connector-j | com.mysql.cj.jdbc.Driver |
| H2 | com.h2database:h2 | org.h2.Driver |
| Microsoft SQL Server | com.microsoft.sqlserver:mssql-jdbc | com.microsoft.sqlserver.jdbc.SQLServerDriver |

Spring Boot starter JDBC cung cấp hạ tầng JDBC của Spring và connection pool mặc định (HikariCP trong cấu hình phổ biến), nhưng **không tự mang theo driver của mọi database**. Ứng dụng cần khai báo driver đúng với database đang dùng.

Driver thường được khai báo ở runtime vì source code không nhất thiết tham chiếu trực tiếp class driver:

~~~xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Khi dùng Spring Boot parent hoặc BOM, phiên bản driver có thể được quản lý bởi dependency management tương ứng. Với Gradle:

~~~groovy
runtimeOnly 'org.postgresql:postgresql'
~~~

JDBC 4 hỗ trợ phát hiện driver qua cơ chế service provider khi driver JAR có metadata phù hợp. Vì vậy, nếu URL được nhận diện và driver có trên runtime classpath, thường không cần tự gọi Class.forName hoặc khai báo driver-class-name bằng tay. Thuộc tính spring.datasource.driver-class-name chỉ nên đặt khi cần chỉ định tường minh hoặc driver không được suy ra đúng từ URL.

### 2.2. JDBC URL cho biết database ở đâu và dùng giao thức nào

URL có dạng tổng quát:

~~~text
jdbc:<database-type>:<database-specific-address>
~~~

Ví dụ:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/orders
spring.datasource.username=app_user
spring.datasource.password=secret
~~~

URL vừa cung cấp địa chỉ database, vừa cho Spring Boot biết loại driver cần dùng. Username/password phụ thuộc chính sách xác thực của database; một số môi trường có thể dùng trust authentication, socket identity hoặc secret provider khác. Vì vậy, thiếu username/password không phải lúc nào cũng là lỗi, nhưng URL thường là thông tin thiết yếu khi không có embedded database để Spring tự cấu hình.

### 2.3. DataSource là bean kết nối, không phải JDBC driver

DataSource là abstraction chuẩn của JDBC để lấy Connection. Nó có thể được triển khai bởi:
- HikariDataSource — connection pool.
- org.apache.tomcat.jdbc.pool.DataSource — Tomcat JDBC pool.
- BasicDataSource — Apache DBCP.
- DriverManagerDataSource — implementation đơn giản, thường dùng trong ví dụ/test, không phải connection pool.
- Một datasource do ứng dụng hoặc thư viện khác tự cung cấp.

Driver là thành phần giao tiếp với database; URL mô tả endpoint; DataSource là object ứng dụng dùng để lấy kết nối. **Có driver không đồng nghĩa có URL; có URL không đồng nghĩa driver đã được đóng gói; có bean DataSource không bảo đảm kết nối thành công.**

## 3. Cách Spring Boot tự cấu hình DataSource

Với Spring Boot 3.3, DataSourceAutoConfiguration thuộc package:

~~~text
org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Auto-configuration này có điều kiện classpath và các điều kiện khác. Bên trong, Boot lựa chọn cấu hình phù hợp:
- Nếu có embedded database như H2, HSQLDB hoặc Derby và không có datasource do người dùng cung cấp, Boot có thể tự cấu hình embedded datasource.
- Nếu có connection pool phù hợp (thường là HikariCP), Boot có thể cấu hình datasource dạng pool dựa trên các thuộc tính spring.datasource.*.
- Nếu ứng dụng đã đăng ký DataSource phù hợp, các nhánh tạo datasource mặc định thường **back off** nhờ @ConditionalOnMissingBean.
- Nếu môi trường dùng R2DBC ConnectionFactory, điều kiện của JDBC auto-configuration cũng có thể khiến cấu hình JDBC mặc định không được áp dụng.

Mô hình khái quát:

~~~text
Spring Boot khởi động
        |
        v
DataSourceAutoConfiguration có đủ class trên classpath?
        |
        +-- Không --> JDBC auto-configuration không áp dụng
        |
        +-- Có
             |
             v
Có bean DataSource do ứng dụng/thư viện khác cung cấp?
             |
             +-- Có --> auto-configuration datasource mặc định back off
             |
             +-- Không
                    |
                    v
       Có embedded DB phù hợp?
                    |
                    +-- Có --> có thể cấu hình embedded DataSource
                    |
                    +-- Không
                           |
                           v
                Có URL và driver phù hợp?
                           |
                           +-- Có --> tạo DataSource theo pool/loại cấu hình
                           |
                           +-- Không --> startup failure
~~~

Đây là sơ đồ định hướng. Chi tiết nhánh được quyết định bởi phiên bản Boot, pool implementation, classpath và điều kiện cấu hình thực tế. Không dùng sơ đồ này thay cho Condition Evaluation Report của ứng dụng.

### 3.1. Vì sao có H2 thì thiếu URL vẫn có thể chạy?

Nếu H2 có trên runtime classpath, Boot có thể chọn embedded database và tạo URL in-memory mặc định khi người dùng không khai báo URL. Do đó, việc không thấy spring.datasource.url **không tự động chứng minh cấu hình sai**.

Ngược lại, nếu không có embedded database và không khai báo URL, Boot không thể tự đoán endpoint của database bên ngoài. Trường hợp thường gặp là:

~~~text
Failed to configure a DataSource:
'url' attribute is not specified and no embedded datasource could be configured.
Reason: Failed to determine a suitable driver class
~~~

Thông điệp này cho biết Boot không thể tạo datasource mặc định với thông tin hiện có. Nó không có nghĩa chỉ cần thêm một driver bất kỳ là đủ; ứng dụng vẫn cần URL/endpoint hoặc embedded database phù hợp.

### 3.2. Vì sao DataSourceAutoConfiguration có thể back off?

Một cấu hình người dùng khai báo:

~~~java
@Bean
DataSource dataSource() {
    // tạo DataSource tùy chỉnh
}
~~~

Khi Spring đã nhận diện bean DataSource này, auto-configuration mặc định không cần tạo thêm một datasource cạnh tranh. Condition report có thể hiển thị điều kiện @ConditionalOnMissingBean không match vì đã tìm thấy bean thuộc type javax.sql.DataSource.

Đây thường là **hành vi đúng**, không phải lỗi. Nếu bean tùy chỉnh hoạt động, việc Boot không tạo datasource mặc định là điều mong muốn. Nếu bean tùy chỉnh bị lỗi, cần điều tra factory method, driver, URL và credentials của chính bean đó.

## 4. Đọc dấu hiệu lỗi theo nguyên nhân

### 4.1. Thiếu URL hoặc không có embedded database

Dấu hiệu thường gặp:

~~~text
Failed to configure a DataSource:
'url' attribute is not specified and no embedded datasource could be configured.
Reason: Failed to determine a suitable driver class
~~~

Cách hiểu:
- Boot đang thử tạo datasource tự động.
- Không có URL phù hợp.
- Không tìm thấy embedded database có thể sử dụng.
- Boot không thể suy ra driver phù hợp để hoàn thiện datasource.

Kiểm tra:
1. spring.datasource.url có được khai báo trong profile đang chạy không?
2. Tên khóa có đúng không (spring.datasource.url, không phải spring.datasource.jdbc-url trong cấu hình chuẩn DataSourceProperties)?
3. Embedded DB như H2 có thực sự nằm trên runtime classpath không?
4. Profile, biến môi trường hoặc tham số chạy có làm mất/ghi đè URL không?
5. Ứng dụng có chủ đích dùng datasource tự tạo hay không?

Không sửa bằng cách chỉ thêm driver-class-name mà vẫn không có URL. Driver biết cách nói chuyện với PostgreSQL không thể tự biết hostname, port và database name cần kết nối.

### 4.2. URL đã chỉ ra database nhưng thiếu driver JAR

Ví dụ ứng dụng cấu hình:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/orders
~~~

nhưng runtime classpath không có org.postgresql:postgresql. Với HikariCP, lỗi gốc thường có dạng:

~~~text
Failed to load driver class org.postgresql.Driver
~~~

hoặc lỗi liên quan driver không được nạp/không chấp nhận JDBC URL. Thông điệp chính xác phụ thuộc pool, driver và cách cấu hình.

Cách kiểm tra:
- URL có scheme đúng jdbc:postgresql: không?
- Artifact org.postgresql:postgresql có được resolve vào runtime không?
- Dependency có bị đặt nhầm scope test, provided, compileOnly hoặc bị exclude khỏi dependency graph không?
- Executable JAR/container có đóng gói driver JAR không?
- Driver class được chỉ định có đúng với database và version driver không?

Sửa bằng cách thêm đúng driver artifact vào runtime dependency và đóng gói lại. Đừng thêm driver MySQL để sửa URL PostgreSQL; mỗi driver chỉ hỗ trợ giao thức tương ứng.

### 4.3. Driver class có mặt nhưng URL không hợp lệ hoặc không tương thích

Ví dụ:

~~~properties
spring.datasource.url=jdbc:postgres://localhost:5432/orders
spring.datasource.driver-class-name=org.postgresql.Driver
~~~

URL trên dùng scheme sai; PostgreSQL JDBC URL chuẩn là jdbc:postgresql://... Có thể xuất hiện lỗi kiểu:

~~~text
Driver ... claims to not accept jdbcUrl
~~~

Cần so sánh:
- Scheme của URL.
- Driver class.
- Database type và driver version.
- Các tham số URL.
- Pool đang được dùng và cách pool truyền URL cho driver.

Không kết luận thiếu driver chỉ vì pool báo URL không được chấp nhận. JAR có thể đã nạp thành công nhưng URL sai.

### 4.4. Driver và URL đúng nhưng database không truy cập được

Các lỗi sau xảy ra ở giai đoạn kết nối:

~~~text
Connection refused
Connection timed out
UnknownHostException
password authentication failed
Access denied for user
database does not exist
~~~

Chúng không giống lỗi thiếu driver:
- Connection refused: endpoint có thể đúng nhưng server chưa lắng nghe, port sai hoặc firewall từ chối.
- Connection timed out: không nhận được phản hồi trong thời gian chờ; kiểm tra mạng, security group, route và server.
- UnknownHostException: hostname không phân giải được.
- Authentication failure: database từ chối credentials hoặc phương thức xác thực.
- Database không tồn tại: server đã phản hồi nhưng tên database sai hoặc chưa được tạo.

Đọc Caused by và thông tin JDBC URL/driver đã chọn. Không đăng mật khẩu, token hoặc URL chứa secret vào log, issue hay báo cáo chẩn đoán công khai.

### 4.5. DataSourceAutoConfiguration không match vì đã có bean

Trong Condition Evaluation Report, có thể gặp nội dung tương tự:

~~~text
DataSourceConfiguration.Hikari:
   Did not match:
      @ConditionalOnMissingBean
      found beans of type 'javax.sql.DataSource'
~~~

Ý nghĩa: Boot tìm thấy datasource đã tồn tại và **chủ động không tạo Hikari datasource mặc định**. Đây là dấu hiệu của bean thay thế, không phải bằng chứng driver mặc định bị thiếu.

Tiếp theo:
1. Tìm bean name và class thực tế của DataSource.
2. Tìm configuration/factory method đã tạo bean.
3. Xem bean đó có nhận đúng property hay không.
4. Mở connection thử và xem exception gốc.
5. Kiểm tra @Primary / @Qualifier nếu có nhiều datasource.

Nếu user bean tự tạo bị lỗi, Spring không tự quay lại tạo một datasource mặc định khác như phương án dự phòng. Điều kiện back-off đã được đáp ứng bởi sự hiện diện của bean definition; bean tùy chỉnh phải được sửa đúng nguyên nhân.

## 5. Condition Evaluation Report: đọc gì và ở đâu?

### 5.1. Bật báo cáo bằng --debug

Chạy ứng dụng với:

~~~bash
java -jar target/jdbc-diagnostics-1.0.0.jar --debug
~~~

Hoặc thêm cấu hình debug phù hợp khi chạy trong IDE. Spring Boot sẽ in **Condition Evaluation Report**, gồm các nhóm:
- Positive matches: các condition đã match.
- Negative matches: các condition không match và lý do.
- Exclusions: các auto-configuration bị loại trừ.
- Unconditional classes: các cấu hình được xử lý không cần điều kiện thông thường.

Khi điều tra datasource, tìm các tên:
- DataSourceAutoConfiguration
- DataSourceConfiguration.Hikari
- EmbeddedDatabaseConfiguration
- PooledDataSourceConfiguration
- Các auto-configuration liên quan transaction manager hoặc JDBC template nếu cần.

Tên nested configuration và cách trình bày có thể thay đổi theo phiên bản. Hãy đọc report của chính ứng dụng.

### 5.2. Bốn mẫu kết quả và cách kết luận

| Điều quan sát được | Cách hiểu | Bước tiếp theo |
| --- | --- | --- |
| DataSourceAutoConfiguration không match do thiếu class | Hạ tầng JDBC cần thiết không có trên classpath | Kiểm tra spring-jdbc, starter và runtime dependency |
| DataSourceAutoConfiguration match nhưng khởi tạo lỗi vì URL/driver | Điều kiện auto-config đủ; lỗi nằm ở thông tin kết nối hoặc tạo datasource | Đọc failure analysis và Caused by, kiểm tra URL/driver |
| DataSourceConfiguration.Hikari không match vì đã có DataSource | Bean do ứng dụng/thư viện khác cung cấp, Boot back off | Xác định bean thực tế và factory method |
| Embedded database configuration match | Boot có thể dùng H2/HSQLDB/Derby mặc định | Xác nhận ứng dụng có chủ đích dùng embedded DB hay không |

**Positive match không có nghĩa kết nối đã thành công.** Condition report nói cấu hình nào được chọn; nó không chứng minh driver có thể mở kết nối, database tồn tại hoặc credentials hợp lệ.

### 5.3. Dùng Actuator khi ứng dụng có thể khởi động

Nếu ứng dụng có spring-boot-starter-actuator, endpoint conditions có thể giúp xem các condition sau khi context được tạo:

~~~properties
management.endpoints.web.exposure.include=health,info,conditions
~~~

Endpoint thường là:

~~~text
/actuator/conditions
~~~

Chỉ expose endpoint chẩn đoán trong môi trường có kiểm soát và bảo vệ bằng cơ chế bảo mật thích hợp. Nếu ứng dụng fail trước khi server/Actuator sẵn sàng, dùng --debug và stack trace thay vì kỳ vọng endpoint vẫn truy cập được.

### 5.4. Đọc exception gốc, không chỉ dòng đầu

Ví dụ stack trace có thể đi qua:
- BeanCreationException
- UnsatisfiedDependencyException
- DataSourceBeanCreationException
- HikariPool / HikariConfig
- DriverManager
- JDBC driver cụ thể

Các exception Spring phía ngoài mô tả bean nào không tạo được. Caused by sâu hơn thường cho biết lý do thực: driver class không load, URL không hợp lệ, socket timeout, authentication failure hoặc lỗi SQL. Ghi lại cả exception ngoài và nguyên nhân gốc.

## 6. Kiểm tra dependency và artifact runtime

### 6.1. Maven

Xem dependency tree tổng thể:

~~~bash
mvn dependency:tree
~~~

Chỉ xem driver PostgreSQL:

~~~bash
mvn dependency:tree -Dincludes=org.postgresql:postgresql
~~~

Xem dependency được resolve trong runtime scope:

~~~bash
mvn dependency:tree -Dscope=runtime
~~~

Nếu không thấy driver, kiểm tra:
- Dependency đã khai báo đúng module chưa?
- Có nằm trong dependencyManagement mà thiếu dependencies thực tế không?
- Scope có phải test hoặc provided không?
- Có exclusion từ dependency cha không?
- Module tạo executable JAR có kế thừa dependency không?

### 6.2. Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency postgresql --configuration runtimeClasspath
~~~

runtimeClasspath quan trọng vì ứng dụng có thể compile thành công nhưng thiếu driver khi chạy. dependencyInsight giải thích vì sao một module/version được chọn và đường phụ thuộc nào đưa nó vào.

### 6.3. Kiểm tra Spring Boot executable JAR

Với Spring Boot executable JAR, dependency thường nằm trong:

~~~text
BOOT-INF/lib/
~~~

Kiểm tra trên Bash:

~~~bash
jar tf target/app.jar | grep BOOT-INF/lib
~~~

Trên Windows PowerShell/CMD:

~~~powershell
jar tf target/app.jar | findstr BOOT-INF/lib
~~~

Tìm đúng artifact, ví dụ postgresql-*.jar hoặc mysql-connector-j-*.jar. Kiểm tra container image tương tự: một dependency có trên máy IDE chưa chắc đã nằm trong image đang chạy.

### 6.4. Đừng nhầm compile classpath với runtime classpath

| Khai báo | Ý nghĩa điển hình | Rủi ro với JDBC driver |
| --- | --- | --- |
| Maven compile / runtime | Có thể hiện diện lúc chạy | Phù hợp cho driver nếu được đóng gói |
| Maven test | Chỉ dành cho test | Ứng dụng production thiếu driver |
| Maven provided | Môi trường runtime được kỳ vọng cung cấp | Có thể thiếu trong executable JAR/container |
| Gradle runtimeOnly | Chỉ cần lúc chạy | Thường phù hợp driver |
| Gradle testRuntimeOnly | Chỉ runtime test | Production có thể thiếu driver |
| Gradle compileOnly | Chỉ compile | Không đủ cho kết nối JDBC lúc chạy |

Driver cần có trong runtime environment thực tế, không chỉ trong môi trường biên dịch.

## 7. Phân biệt cấu hình DataSource chuẩn với bean do user tạo

### 7.1. Cấu hình chuẩn qua spring.datasource.*

Ví dụ PostgreSQL:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://db.example.internal:5432/orders
    username: orders_app
    password: secret-from-environment
    driver-class-name: org.postgresql.Driver
    hikari:
      maximum-pool-size: 10
      connection-timeout: 30000
~~~

Trong trường hợp auto-configuration mặc định:
- DataSourceProperties đọc các thuộc tính spring.datasource.*.
- Spring Boot suy ra driver từ URL nếu có thể.
- Boot chọn implementation datasource/pool phù hợp.
- Các thuộc tính pool dưới spring.datasource.hikari.* được áp dụng cho Hikari khi Hikari được chọn.

Thông thường có thể bỏ driver-class-name nếu URL và driver JAR đủ để suy ra driver. Khai báo tường minh hữu ích khi cần kiểm soát, nhưng không thay thế driver JAR.

### 7.2. User tự khai báo DataSource: Boot sẽ nhường

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
class CustomDatabaseConfiguration {

    @Bean
    DataSource dataSource() {
        DriverManagerDataSource dataSource =
                new DriverManagerDataSource();

        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:customdb;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        return dataSource;
    }
}
~~~

Đây là cấu hình thủ công dùng DriverManagerDataSource, phù hợp cho ví dụ hoặc một số test đơn giản. Nó không phải connection pool production. Khi bean này được đăng ký, DataSourceAutoConfiguration không tạo datasource mặc định cạnh tranh vì điều kiện missing-bean không còn thỏa.

Điểm cần nhớ: **spring.datasource.* không tự động bind vào mọi bean DataSource mà user viết.** Khi tự tạo bean, user phải tự cấu hình nó hoặc sử dụng DataSourceProperties / @ConfigurationProperties theo thiết kế riêng.

### 7.3. Nếu muốn tự tạo HikariDataSource và vẫn bind properties

Một cách phổ biến là sử dụng DataSourceProperties để chuyển url chuẩn thành thuộc tính URL phù hợp với pool:

~~~java
@Configuration(proxyBeanMethods = false)
class CustomPoolConfiguration {

    @Bean
    @ConfigurationProperties("app.datasource")
    DataSourceProperties dataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @ConfigurationProperties("app.datasource.configuration")
    HikariDataSource dataSource(DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }
}
~~~

Ví dụ cấu hình:

~~~yaml
app:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: orders_app
    password: secret-from-environment
    configuration:
      maximum-pool-size: 10
      connection-timeout: 30000
~~~

Đây là cấu hình datasource tùy chỉnh dùng prefix riêng app.datasource; nó không tự áp dụng chính sách mặc định của spring.datasource. Cần bảo đảm dependency PostgreSQL và điều kiện đăng ký cấu hình được khai báo đúng.

Nếu bind trực tiếp vào HikariDataSource, property của Hikari là jdbc-url, trong khi DataSourceProperties chuẩn dùng url. Đây là một nguồn gây nhầm lẫn phổ biến; dùng DataSourceProperties.initializeDataSourceBuilder() giúp giữ tên url ở cấu hình ứng dụng.

### 7.4. Nhiều DataSource và @Primary / @Qualifier

Nếu ứng dụng có nhiều datasource, Boot có thể back off cấu hình datasource mặc định khi bean DataSource do user cung cấp đã tồn tại. Khi inject không chỉ rõ bean, Spring có thể báo NoUniqueBeanDefinitionException.

Giải pháp:
- Dùng @Qualifier("ordersDataSource") khi một service cần datasource cụ thể.
- Dùng @Primary cho datasource mặc định khi injection không chỉ định qualifier.
- Cấu hình transaction manager và repository phù hợp với từng datasource.
- Kiểm tra bean name, type và package scan/import.

@Primary chỉ giúp Spring chọn bean ưu tiên khi injection theo type có nhiều candidate. Nó **không phải** điều kiện khiến DataSourceAutoConfiguration tự tạo hoặc không tạo bean; sự hiện diện của bean DataSource mới là yếu tố quan trọng đối với điều kiện back-off.

## 8. Lab Java 17 + Spring Boot 3.3: xem datasource mặc định và datasource thay thế

Lab sử dụng H2 để chạy cục bộ không cần database server. Có hai trạng thái:
1. Không bật datasource tùy chỉnh: Boot tạo Hikari datasource từ spring.datasource.*.
2. Bật datasource tùy chỉnh: ứng dụng tự đăng ký DataSource; Boot back off.

### 8.1. Cấu trúc dự án

~~~text
jdbc-diagnostics/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── jdbc/
        │           └── JdbcDiagnosticsApplication.java
        └── resources/
            └── application.properties
~~~

### 8.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>jdbc-diagnostics</artifactId>
    <version>1.0.0</version>
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
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

spring-boot-starter-jdbc mang theo Spring JDBC và HikariCP theo cấu hình starter phổ biến. H2 là database driver riêng được khai báo ở runtime.

### 8.3. application.properties

~~~properties
spring.datasource.url=jdbc:h2:mem:autoconfigdb;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=

spring.main.banner-mode=off
logging.level.root=OFF
~~~

URL chỉ ra H2 in-memory database tên autoconfigdb. DB_CLOSE_DELAY=-1 giữ database tồn tại trong vòng đời JVM dù một connection được đóng; khi JVM kết thúc, database in-memory biến mất.

### 8.4. JdbcDiagnosticsApplication.java

~~~java
package demo.jdbc;

import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Statement;
import javax.sql.DataSource;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

@SpringBootApplication
public class JdbcDiagnosticsApplication {

    public static void main(String[] args) {
        SpringApplication.run(JdbcDiagnosticsApplication.class, args);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.datasource",
            name = "custom",
            havingValue = "true"
    )
    DataSource customDataSource() {
        DriverManagerDataSource dataSource =
                new DriverManagerDataSource();

        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl(
                "jdbc:h2:mem:customdb;DB_CLOSE_DELAY=-1"
        );
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        return dataSource;
    }

    @Bean
    ApplicationRunner report(
            ApplicationContext context,
            ObjectProvider<DataSource> dataSources) {

        return args -> {
            String[] names =
                    context.getBeanNamesForType(DataSource.class);

            System.out.println("DataSource bean count: " + names.length);

            DataSource dataSource = dataSources.getIfAvailable();
            if (dataSource == null) {
                System.out.println("DataSource present: false");
                return;
            }

            System.out.println(
                    "DataSource implementation: " +
                    dataSource.getClass().getName()
            );

            try (Connection connection = dataSource.getConnection()) {
                System.out.println(
                        "Database URL: " +
                        connection.getMetaData().getURL()
                );

                try (Statement statement = connection.createStatement();
                     ResultSet result = statement.executeQuery("SELECT 1")) {

                    result.next();
                    System.out.println("SELECT 1: " + result.getInt(1));
                }
            }
        };
    }
}
~~~

@ConditionalOnProperty trên customDataSource() chỉ tạo bean thay thế khi demo.datasource.custom=true. Vì đây là bean trong application configuration, nó được đăng ký trước khi auto-configuration datasource mặc định đánh giá điều kiện missing-bean.

ObjectProvider<DataSource> cho phép runner xử lý trường hợp không có datasource mà không buộc constructor injection thất bại ngay. Trong lab hai trường hợp thành công đều có đúng một datasource.

### 8.5. Trường hợp A — Boot tạo datasource mặc định

Đóng gói:

~~~bash
mvn -q -DskipTests package
~~~

Chạy:

~~~bash
java -jar target/jdbc-diagnostics-1.0.0.jar
~~~

Stdout do chương trình in:

~~~text
DataSource bean count: 1
DataSource implementation: com.zaxxer.hikari.HikariDataSource
Database URL: jdbc:h2:mem:autoconfigdb
SELECT 1: 1
~~~

Kết luận:
- H2 driver có trên runtime classpath.
- URL và credentials dùng được.
- Auto-configuration chọn Hikari datasource.
- Kết nối mở thành công và câu SQL kiểm tra trả về 1.

### 8.6. Trường hợp B — ứng dụng tự cung cấp DataSource

Chạy cùng artifact với property bật bean tùy chỉnh:

~~~bash
java -jar target/jdbc-diagnostics-1.0.0.jar --demo.datasource.custom=true
~~~

Stdout:

~~~text
DataSource bean count: 1
DataSource implementation: org.springframework.jdbc.datasource.DriverManagerDataSource
Database URL: jdbc:h2:mem:customdb
SELECT 1: 1
~~~

Kết luận:
- Bean customDataSource của ứng dụng đã tồn tại.
- DataSourceAutoConfiguration không tạo Hikari datasource mặc định.
- DriverManagerDataSource mở kết nối thành công vì H2 driver có mặt.
- spring.datasource.url trong application.properties không tự động chuyển thành URL của bean tùy chỉnh; bean tùy chỉnh dùng URL được khai báo trong factory method.

Đây là **back-off có chủ đích**, không phải lỗi driver. Nếu muốn custom bean dùng cấu hình ngoài, phải bind properties cho nó như phần 7.3.

### 8.7. Trường hợp C — bỏ H2 để tái hiện thiếu URL và embedded database

Để thử lỗi thiếu URL:
1. Tạm bỏ dependency H2 khỏi pom.xml.
2. Xóa hoặc comment spring.datasource.url, username và password trong application.properties.
3. Chạy lại mvn -q clean package.
4. Khởi động ứng dụng.

Vì không có embedded database và cũng không có URL, startup sẽ thất bại. Failure analysis thường có nội dung:

~~~text
Failed to configure a DataSource:
'url' attribute is not specified and no embedded datasource could be configured.
Reason: Failed to determine a suitable driver class
~~~

Đây là tình huống **thiếu thông tin kết nối/không có embedded DB**, không phải bằng chứng driver PostgreSQL hay MySQL cần được thêm tùy tiện. Hãy xác định database thật mà ứng dụng muốn dùng rồi khai báo URL và đúng driver.

Khôi phục dependency H2 và application.properties sau khi thử.

### 8.8. Trường hợp D — URL PostgreSQL nhưng thiếu PostgreSQL driver

Để mô phỏng driver thiếu:
1. Giữ dependency spring-boot-starter-jdbc.
2. Không thêm org.postgresql:postgresql.
3. Đổi URL thành:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/orders
spring.datasource.username=orders_app
spring.datasource.password=secret
~~~

4. Có thể bỏ H2 để tránh embedded fallback; URL PostgreSQL đã chỉ rõ driver cần dùng.
5. Đóng gói và chạy lại.

Lỗi gốc thường chỉ ra org.postgresql.Driver không thể được nạp. Không cần database server đang chạy để phát hiện một số lỗi driver-loading: nếu driver JAR vắng mặt, lỗi có thể xảy ra trước khi thử kết nối.

Sửa bằng cách thêm:

~~~xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Sau đó build lại. Khi driver đã nạp được, nếu PostgreSQL không chạy hoặc credentials sai, lỗi tiếp theo sẽ thuộc nhóm network/authentication; đó là giai đoạn chẩn đoán khác.

## 9. Kiểm thử việc auto-configuration tạo hoặc nhường DataSource

Có thể dùng ApplicationContextRunner để kiểm tra điều kiện mà không cần chạy cả ứng dụng. Thêm dependency test vào pom.xml:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Tạo cấu hình datasource tùy chỉnh dùng trong test:

~~~java
package demo.jdbc;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

@Configuration(proxyBeanMethods = false)
class TestDataSourceConfiguration {

    @Bean
    DataSource userDataSource() {
        DriverManagerDataSource dataSource =
                new DriverManagerDataSource();

        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:userdb");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        return dataSource;
    }
}
~~~

Tạo test:

~~~java
package demo.jdbc;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import static org.assertj.core.api.Assertions.assertThat;

class DataSourceAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            DataSourceAutoConfiguration.class
                    ));

    @Test
    void embeddedH2CanCreateDefaultDataSourceWithoutUrl() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(DataSource.class);
            assertThat(context.getBean(DataSource.class))
                    .isNotNull();
        });
    }

    @Test
    void userDataSourceMakesAutoConfigurationBackOff() {
        runner.withUserConfiguration(TestDataSourceConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(DataSource.class);
                    assertThat(context.getBean(DataSource.class))
                            .isInstanceOf(DriverManagerDataSource.class);
                });
    }
}
~~~

Với H2 runtime dependency vẫn có mặt, chạy:

~~~bash
mvn test
~~~

Kỳ vọng **2 test PASS**:
- H2 có trên classpath nên Boot có thể tạo embedded datasource dù không có URL tường minh.
- Khi user configuration cung cấp datasource, bean tùy chỉnh hiện diện và auto-configuration không tạo thêm datasource mặc định.

Hai test này kiểm tra việc chọn bean. Các tình huống driver thiếu hoặc URL không có embedded database là lỗi khởi động; nên kiểm tra bằng integration test riêng hoặc quy trình chạy thử với classpath tương ứng, không giả vờ rằng context thành công trong các ca đó.

## 10. Cách đọc báo cáo cho từng tình huống thực tế

### Tình huống 1 — không có driver phù hợp

**Bằng chứng:**
- URL có scheme PostgreSQL/MySQL.
- Dependency tree hoặc executable JAR không có driver tương ứng.
- Stack trace báo không load được driver class.

**Kết luận:** lỗi runtime dependency/driver. Thêm đúng artifact và kiểm tra scope/packaging.

### Tình huống 2 — không có URL và không có embedded DB

**Bằng chứng:**
- spring.datasource.url không tồn tại trong Environment.
- H2/HSQLDB/Derby không có trên runtime classpath.
- Failure analysis nói URL không được chỉ định và không thể cấu hình embedded datasource.

**Kết luận:** thiếu endpoint kết nối. Cung cấp URL database thật và driver phù hợp, hoặc thêm embedded database nếu đó là chủ đích.

### Tình huống 3 — URL đúng nhưng kết nối bị từ chối

**Bằng chứng:**
- Driver đã load.
- URL được driver chấp nhận.
- getConnection() thất bại với lỗi mạng, timeout hoặc xác thực.

**Kết luận:** kiểm tra host/port, server status, DNS, firewall, database name, username/password và quyền truy cập. Không tiếp tục thêm driver nếu driver đã load đúng.

### Tình huống 4 — DataSourceAutoConfiguration back off

**Bằng chứng:**
- Negative match ở @ConditionalOnMissingBean.
- Report nói đã tìm thấy bean DataSource.
- Context có bean name/class của datasource do user hoặc thư viện khác đăng ký.

**Kết luận:** Boot đang nhường cho bean có sẵn. Xác định factory method, config properties và connection logic của bean đó.

### Tình huống 5 — bean tùy chỉnh tồn tại nhưng không mở được connection

**Bằng chứng:**
- Condition report xác nhận Boot back off.
- Context có datasource tùy chỉnh.
- Lỗi xảy ra khi lấy connection, thường bắt đầu từ class/driver/URL của custom bean.

**Kết luận:** sửa factory method hoặc property binding của datasource tùy chỉnh. Đừng chờ Boot tạo datasource thứ hai; điều kiện back-off đã hoạt động đúng.

### Tình huống 6 — có nhiều DataSource

**Bằng chứng:**
- Bean count lớn hơn một.
- Injection theo type báo NoUniqueBeanDefinitionException.

**Kết luận:** xác định datasource nào thuộc repository/service nào; dùng @Qualifier, @Primary, transaction manager và repository configuration đúng phạm vi.

## 11. Quy trình chẩn đoán từng bước

1. **Đọc exception đầu tiên và toàn bộ Caused by.** Xác định lỗi xảy ra lúc resolve condition, tạo bean, load driver hay mở connection.
2. **Xác định DataSource bean có được đăng ký không.** Dùng condition report và bean type/name; không giả định Boot luôn tạo datasource mặc định.
3. **Nếu không có bean:** kiểm tra DataSourceAutoConfiguration có match không, nested config nào bị loại, và vì sao.
4. **Nếu bean do user cung cấp:** tìm chính xác factory method/class và property source của bean đó.
5. **Kiểm tra JDBC URL.** Scheme có đúng với database không? Host, port, database name và query parameter có hợp lệ không?
6. **Kiểm tra driver trên runtime classpath.** Dùng Maven/Gradle dependency tree và nội dung executable JAR/container.
7. **Kiểm tra thông tin xác thực.** Xác nhận username/password hoặc phương thức authentication thực tế; không ghi secret vào log.
8. **Thử kết nối bằng cùng endpoint và credentials trong môi trường triển khai.** Điều này giúp tách lỗi ứng dụng khỏi lỗi mạng/database.
9. **Dùng --debug để đọc Condition Evaluation Report.** Phân biệt positive match, negative match và back-off do bean có sẵn.
10. **Sửa đúng một nguyên nhân đã xác nhận, sau đó chạy lại test/startup và một truy vấn đơn giản.** Đừng chỉ kiểm tra ứng dụng đã in Started; hãy xác minh lấy connection và thực thi SQL thành công.

## 12. Những nhầm lẫn phổ biến

1. **Thêm spring-boot-starter-jdbc là đã có mọi driver.** Không đúng; driver database cụ thể thường là dependency riêng.
2. **Có driver là không cần URL.** Không đúng với database bên ngoài; driver không tự biết endpoint.
3. **Không có URL luôn là lỗi.** Không đúng nếu embedded database có trên classpath và Boot có thể tự cấu hình.
4. **Lỗi Failed to determine a suitable driver class luôn chỉ có một nguyên nhân.** Cần đọc phần URL, embedded DB, driver và runtime classpath để xác định.
5. **DataSourceAutoConfiguration back off nghĩa là auto-configuration hỏng.** Có thể là hành vi đúng vì ứng dụng đã cung cấp datasource.
6. **@Primary khiến Boot không tạo datasource.** Điều kiện back-off dựa trên bean DataSource tồn tại; @Primary chủ yếu giải quyết lựa chọn injection khi có nhiều bean.
7. **spring.datasource.* tự bind vào mọi datasource tùy chỉnh.** Không đúng; bean do user tạo cần cấu hình/binding riêng.
8. **Có DataSource bean nghĩa là database kết nối được.** Không đúng; object có thể được tạo nhưng mở connection vẫn lỗi.
9. **Connection refused là thiếu driver.** Thường đây là lỗi mạng/server; driver đã đi xa hơn giai đoạn load.
10. **NoUniqueBeanDefinitionException là thiếu datasource.** Có thể là nhiều datasource; kiểm tra bean count và qualifier.
11. **Exclude DataSourceAutoConfiguration là cách sửa mọi lỗi JDBC.** Có thể làm mất bean mặc định mà ứng dụng thực sự cần, trong khi không sửa driver hay connection.
12. **IDE chạy được nghĩa là executable JAR/container có driver.** Runtime artifact có thể khác classpath IDE.
13. **Chỉ nhìn dòng log đầu tiên là đủ.** Exception gốc thường nằm sâu hơn trong Caused by.
14. **Password luôn bắt buộc hoặc luôn được để trống.** Điều đó phụ thuộc database và chính sách authentication; không áp đặt một quy tắc cho mọi hệ thống.
15. **Report positive match nghĩa là SQL sẽ chạy.** Report chỉ mô tả điều kiện cấu hình; cần thử mở connection và truy vấn để xác minh.

## 13. Checklist vận hành và phát hành

- [ ] Đã xác định bean DataSource nào thực sự được sử dụng.
- [ ] Driver artifact đúng database và có mặt trên runtime classpath.
- [ ] JDBC URL đúng scheme, host, port, database name và tham số.
- [ ] URL hoặc embedded database đủ để Boot cấu hình datasource.
- [ ] Credentials/authentication được cấp qua nguồn cấu hình phù hợp.
- [ ] Nếu có custom DataSource, factory method tự bind/cấu hình đầy đủ.
- [ ] Hiểu rõ vì sao DataSourceAutoConfiguration match hoặc back off.
- [ ] Nếu có nhiều datasource, đã dùng qualifier/primary và transaction manager đúng.
- [ ] Đã kiểm tra executable JAR/container chứ không chỉ classpath IDE.
- [ ] Đã chạy --debug hoặc đọc Condition Evaluation Report khi có khác biệt.
- [ ] Đã thử getConnection() và một câu SQL đơn giản.
- [ ] Không đưa mật khẩu, token hoặc secret vào log và báo cáo lỗi.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** spring-boot-starter-jdbc đã có nhưng ứng dụng dùng PostgreSQL. Vì sao vẫn cần driver PostgreSQL?  
**Đáp án:** Starter cung cấp hạ tầng JDBC/pool; driver PostgreSQL là thư viện riêng thực hiện giao thức PostgreSQL và cần có trong runtime classpath.

**Câu 2.** Không khai báo spring.datasource.url nhưng H2 có trong runtime classpath. Có chắc startup fail không?  
**Đáp án:** Không. Boot có thể tự cấu hình embedded H2.

**Câu 3.** URL là jdbc:postgresql://... nhưng org.postgresql.Driver không load được. Nhóm lỗi nào?  
**Đáp án:** Thiếu hoặc không nạp được driver trên runtime classpath.

**Câu 4.** Condition report nói @ConditionalOnMissingBean không match vì đã tìm thấy DataSource. Có nghĩa Boot hỏng không?  
**Đáp án:** Không. Boot đang nhường cho bean datasource đã được đăng ký.

**Câu 5.** Ứng dụng có custom DataSource nhưng spring.datasource.url không tác dụng. Vì sao?  
**Đáp án:** Custom bean không tự động nhận binding của datasource auto-configuration; cần cấu hình bean hoặc bind DataSourceProperties riêng.

**Câu 6.** Driver và URL đúng, nhưng lỗi Connection refused. Cần kiểm tra gì?  
**Đáp án:** Server đang chạy, host/port, DNS, firewall, route và endpoint; không tiếp tục thêm driver một cách mù quáng.

**Câu 7.** Có hai bean DataSource, injection theo type thất bại. Giải pháp nào?  
**Đáp án:** Xác định vai trò từng bean, dùng @Qualifier hoặc @Primary phù hợp và cấu hình repository/transaction manager.

## 15. Tài liệu tham khảo chính thức

- [Spring Boot 3.3 Javadoc — DataSourceAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.html).
- [Spring Boot 3.3 Javadoc — DataSourceProperties](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceProperties.html).
- [Spring Boot Reference — SQL Databases and Configure a DataSource](https://docs.spring.io/spring-boot/3.3/reference/data/sql.html).
- [Spring Boot Reference — Auto-configuration and Condition Evaluation Report](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html).
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
- [JDBC API — DataSource](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/javax/sql/DataSource.html)
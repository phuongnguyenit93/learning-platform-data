# Kiểm tra giá trị cấu hình đã được gắn vào bean mặc định

## 1. Mục tiêu: kiểm tra kết quả cuối cùng trong bean

Trong Spring Boot, thấy property trong file cấu hình hoặc thấy object `@ConfigurationProperties` đã nhận giá trị vẫn chưa đủ để kết luận bean mặc định hoạt động đúng. Cần xác minh toàn bộ đường đi:

1. Giá trị có mặt trong `Environment` từ đúng nguồn cấu hình.
2. Spring Binder chuyển giá trị sang đúng kiểu và gắn vào properties object.
3. Auto-configuration nhận properties object hoặc bind trực tiếp vào bean.
4. Bean mặc định được tạo với đúng giá trị hiệu lực.
5. Nếu ứng dụng cung cấp bean thay thế, auto-configuration có back off theo thiết kế.

Ví dụ, `spring.datasource.url` có thể được bind đúng vào `DataSourceProperties`, nhưng bean `DataSource` cuối cùng vẫn có thể sai nếu một cấu hình khác thay thế nó hoặc pool-specific property không được bind như mong đợi. Vì vậy, test nên kiểm tra **bean thực tế mà ứng dụng sẽ inject**, không chỉ kiểm tra object cấu hình trung gian.

Bài viết sử dụng **Spring Boot 3.5.x, Java 17+ và JUnit 5**. Ví dụ chính kiểm tra `DataSourceAutoConfiguration` cùng `HikariDataSource`, chạy bằng H2 in-memory để không phụ thuộc database bên ngoài.

## 2. Ba lớp cần kiểm chứng

| Lớp | Câu hỏi | Cách kiểm tra |
| --- | --- | --- |
| `Environment` | Property nào đang có giá trị hiệu lực? | `Environment.getProperty(...)` |
| Properties bean | Binder đã chuyển giá trị sang field/kiểu Java đúng chưa? | Lấy bean `@ConfigurationProperties` và assert từng giá trị |
| Bean mặc định | Factory method đã dùng các giá trị đó để tạo bean đúng chưa? | Lấy bean theo type thực tế, assert getter hoặc hành vi công khai |

Ví dụ:

- `spring.datasource.url` và `spring.datasource.username` thuộc nhóm cấu hình DataSource chung.
- `spring.datasource.hikari.maximum-pool-size` thuộc cấu hình riêng của Hikari.
- `DataSourceProperties` kiểm tra phần cấu hình JDBC chung.
- `HikariDataSource` kiểm tra giá trị thực sự đã đến pool mặc định.

**Không dừng ở properties bean.** Nếu test chỉ xác nhận `DataSourceProperties.getUrl()` đúng, nó chưa chứng minh Hikari đã nhận URL đó.

### 2.1. Default value trong class không nhất thiết có trong Environment

Nếu một class `@ConfigurationProperties` khai báo:

~~~java
private int maxConnections = 8;
~~~

thì object sau khi bind có thể trả về `8` dù người dùng không khai báo property. Nhưng điều đó **không có nghĩa** `Environment.getProperty("acme.client.max-connections")` trả về `"8"`.

Default khai báo trong object và giá trị có mặt trong `Environment` là hai khái niệm khác nhau. Khi kiểm tra default, assert trực tiếp trên properties bean hoặc bean đã được cấu hình; đừng chỉ truy vấn `Environment`.

## 3. Dùng ApplicationContextRunner để kiểm tra auto-configuration độc lập

`ApplicationContextRunner` tạo một Spring ApplicationContext nhỏ, cho phép kiểm soát:
- Auto-configuration nào được nạp;
- Property nào được thêm vào Environment;
- User configuration hoặc bean thay thế nào có mặt;
- Classpath có hoặc thiếu dependency nào.

Mỗi lần gọi `.run(...)` tạo một context riêng và đóng context sau callback. Nhờ đó, test không phải khởi động toàn bộ ứng dụng hoặc mở HTTP port.

Cấu trúc cơ bản:

~~~java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(
                                DataSourceAutoConfiguration.class));

@Test
void configuredValuesReachTheDefaultBean() {
    contextRunner.withPropertyValues(
            "spring.datasource.url=jdbc:h2:mem:config_test",
            "spring.datasource.username=sa"
    ).run(context -> {
        // Assert properties bean và bean thực tế tại đây.
    });
}
~~~

`withPropertyValues(...)` thêm property trực tiếp cho test context. Đây là cách tốt để cô lập binding và condition. Tuy nhiên, nó **không tự chứng minh** ứng dụng production đang nạp đúng `application.yml`, profile hay biến môi trường; phần kiểm tra Config Data thật được trình bày ở mục 10.

## 4. Ví dụ hoàn chỉnh: kiểm tra DataSource mặc định của Spring Boot

Ta kiểm tra hai nhóm giá trị:

- `spring.datasource.*`: URL, username và password được bind vào `DataSourceProperties`.
- `spring.datasource.hikari.*`: cấu hình pool được gắn vào `HikariDataSource`.

Nếu các giá trị đã đi đến bean cuối cùng, ứng dụng có thể inject `DataSource` và dùng pool với cấu hình mong muốn.

### 4.1. Cấu trúc dự án

~~~text
datasource-binding-test/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── DataSourceAutoConfigurationTests.java
~~~

Đây là test độc lập; không cần class `@SpringBootApplication` hoặc `main()`.

### 4.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>datasource-binding-test</artifactId>
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
            <scope>test</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

`spring-boot-starter-jdbc` cung cấp Spring JDBC và HikariCP theo cấu hình mặc định của starter. H2 chỉ có trong test scope; nó tạo database trong bộ nhớ, không cần cài hoặc khởi động database server.

Nếu dự án đã có parent/BOM quản lý Spring Boot version, không thêm parent thứ hai; chỉ bổ sung các dependency còn thiếu.

### 4.3. Test toàn bộ giá trị từ properties đến HikariDataSource

Tạo file `src/test/java/example/DataSourceAutoConfigurationTests.java`:

~~~java
package example;

import com.zaxxer.hikari.HikariDataSource;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class DataSourceAutoConfigurationTests {

    private static final String JDBC_URL =
            "jdbc:h2:mem:config_binding_test";

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    DataSourceAutoConfiguration.class));

    @Test
    void configuredPropertiesReachTheDefaultHikariDataSource() {
        contextRunner.withPropertyValues(
                "spring.datasource.url=" + JDBC_URL,
                "spring.datasource.username=sa",
                "spring.datasource.password=",
                "spring.datasource.hikari.maximum-pool-size=7",
                "spring.datasource.hikari.connection-timeout=3000"
        ).run(context -> {
            assertThat(context).hasNotFailed();

            // Kiểm tra properties bean.
            assertThat(context)
                    .hasSingleBean(DataSourceProperties.class);

            DataSourceProperties properties =
                    context.getBean(DataSourceProperties.class);

            assertThat(properties.getUrl()).isEqualTo(JDBC_URL);
            assertThat(properties.getUsername()).isEqualTo("sa");

            // Kiểm tra bean pool mặc định thực tế.
            assertThat(context).hasSingleBean(HikariDataSource.class);

            HikariDataSource dataSource =
                    context.getBean(HikariDataSource.class);

            assertThat(dataSource.getJdbcUrl()).isEqualTo(JDBC_URL);
            assertThat(dataSource.getUsername()).isEqualTo("sa");
            assertThat(dataSource.getMaximumPoolSize()).isEqualTo(7);
            assertThat(dataSource.getConnectionTimeout()).isEqualTo(3000L);
        });
    }
}
~~~

Các assertion chứng minh từng tầng:

1. `context.hasNotFailed()` xác nhận context đã khởi tạo thành công.
2. `DataSourceProperties` nhận URL và username từ nhóm `spring.datasource.*`.
3. `HikariDataSource` là implementation pool thực tế được đăng ký.
4. `getJdbcUrl()`, `getUsername()`, `getMaximumPoolSize()` và `getConnectionTimeout()` xác nhận giá trị đã đến bean cuối cùng.

Đặc biệt, `maximum-pool-size` không thuộc `DataSourceProperties`; nó là property riêng của Hikari. Nếu chỉ kiểm tra `DataSourceProperties`, test sẽ bỏ sót cấu hình pool.

### 4.4. Chạy test

Với Maven:

~~~bash
mvn test -Dtest=DataSourceAutoConfigurationTests
~~~

Với Maven Wrapper trên macOS/Linux:

~~~bash
./mvnw test -Dtest=DataSourceAutoConfigurationTests
~~~

Với Windows PowerShell:

~~~powershell
.\mvnw.cmd test '-Dtest=DataSourceAutoConfigurationTests'
~~~

Kết quả mong đợi: **1 test PASS**. Maven/Surefire có thể hiển thị thêm log hoặc định dạng báo cáo khác nhau theo phiên bản; điều cần xác nhận là test method thành công và không có assertion failure.

Test trên kiểm tra cấu hình được gắn vào Hikari bean. Nó chưa thực hiện kết nối tới database. Nếu mục tiêu còn bao gồm khả năng mở kết nối, hãy thêm một assertion integration với H2 như mục 9.

## 5. Kiểm tra giá trị mặc định khi không khai báo property

Đôi khi yêu cầu là bảo đảm bean mặc định sử dụng đúng default khi người dùng không cấu hình gì.

Với một properties class do ứng dụng sở hữu:

~~~java
@ConfigurationProperties("acme.client")
public class AcmeClientProperties {

    private String endpoint = "https://api.example.test";

    private Duration connectTimeout = Duration.ofSeconds(2);

    private int maxConnections = 8;

    // Getter và setter cho các field.
}
~~~

Nếu auto-configuration tạo bean từ object này:

~~~java
@AutoConfiguration
@EnableConfigurationProperties(AcmeClientProperties.class)
public class AcmeClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    AcmeClient acmeClient(AcmeClientProperties properties) {
        return new AcmeClient(
                properties.getEndpoint(),
                properties.getConnectTimeout(),
                properties.getMaxConnections());
    }
}
~~~

thì test default phải kiểm tra cả properties object và bean được tạo:

~~~java
@Test
void defaultsReachTheDefaultClient() {
    clientContextRunner.run(context -> {
        assertThat(context).hasNotFailed();

        AcmeClientProperties properties =
                context.getBean(AcmeClientProperties.class);

        AcmeClient client = context.getBean(AcmeClient.class);

        assertThat(properties.getEndpoint())
                .isEqualTo("https://api.example.test");
        assertThat(properties.getConnectTimeout())
                .isEqualTo(Duration.ofSeconds(2));
        assertThat(properties.getMaxConnections()).isEqualTo(8);

        assertThat(client.endpoint())
                .isEqualTo(properties.getEndpoint());
        assertThat(client.connectTimeout())
                .isEqualTo(properties.getConnectTimeout());
        assertThat(client.maxConnections())
                .isEqualTo(properties.getMaxConnections());
    });
}
~~~

Đây là đoạn test minh họa; `clientContextRunner` phải được khai báo với `AutoConfigurations.of(AcmeClientAutoConfiguration.class)`, và `AcmeClient` cần có các accessor tương ứng.

**Tại sao cần assert hai phía?** Nếu properties bean có default đúng nhưng factory method vô tình truyền sai field vào constructor, assertion trên properties vẫn PASS. Assertion trên `AcmeClient` mới phát hiện lỗi nối dữ liệu.

## 6. Kiểm tra trường hợp ứng dụng thay bean mặc định

Nhiều auto-configuration sử dụng `@ConditionalOnMissingBean` để cho phép ứng dụng tự cung cấp bean. Khi user bean đã có, bean mặc định sẽ back off.

Ví dụ cấu hình người dùng:

~~~java
@Configuration(proxyBeanMethods = false)
class CustomDataSourceConfiguration {

    @Bean
    DataSource customDataSource() {
        return new DriverManagerDataSource(
                "jdbc:h2:mem:custom_data_source",
                "sa",
                "");
    }
}
~~~

Thêm test:

~~~java
@Test
void userDataSourceMakesTheDefaultPoolBackOff() {
    contextRunner
            .withUserConfiguration(CustomDataSourceConfiguration.class)
            .withPropertyValues(
                    "spring.datasource.url=jdbc:h2:mem:default_source",
                    "spring.datasource.username=sa")
            .run(context -> {
                assertThat(context).hasNotFailed();

                assertThat(context).hasSingleBean(DataSource.class);
                assertThat(context).hasBean("customDataSource");
                assertThat(context).doesNotHaveBean(HikariDataSource.class);
            });
}
~~~

Test này xác nhận:
- DataSource do ứng dụng cung cấp vẫn tồn tại;
- Hikari DataSource mặc định không được đăng ký;
- Auto-configuration tôn trọng extension point `@ConditionalOnMissingBean`.

**Lưu ý:** Khi user bean thay thế DataSource mặc định, không nên tiếp tục kỳ vọng `spring.datasource.url` tự cấu hình bean `DriverManagerDataSource` do người dùng tạo. Bean đó được tạo bởi method của ứng dụng; nếu muốn bind property vào nó, hãy cấu hình binding riêng, ví dụ dùng `@ConfigurationProperties` trên `@Bean` method.

Không dùng `@Primary` để che một default bean không mong muốn trong test back-off. `@Primary` chỉ quyết định bean ưu tiên khi inject theo kiểu; nó không chứng minh auto-configuration đã dừng tạo bean mặc định.

## 7. Bind trực tiếp property vào bean bên thứ ba

Một số thư viện có JavaBean mutable nhưng không cung cấp `@ConfigurationProperties` class riêng. Spring Boot cho phép đặt annotation trực tiếp trên method `@Bean`:

~~~java
@Bean
@ConditionalOnMissingBean
@ConfigurationProperties("acme.http")
ThirdPartyHttpClient thirdPartyHttpClient() {
    return new ThirdPartyHttpClient();
}
~~~

Giả sử `ThirdPartyHttpClient` có:
- `setBaseUrl(String)`;
- `setReadTimeout(Duration)`;
- getter tương ứng.

Khi bean được tạo, configuration properties binder sẽ gắn các key `acme.http.*` lên object. Test cần lấy **ThirdPartyHttpClient** và assert getter của chính object đó:

~~~java
contextRunner.withPropertyValues(
        "acme.http.base-url=https://partner.example.test",
        "acme.http.read-timeout=4s"
).run(context -> {
    ThirdPartyHttpClient client =
            context.getBean(ThirdPartyHttpClient.class);

    assertThat(client.getBaseUrl())
            .isEqualTo("https://partner.example.test");
    assertThat(client.getReadTimeout())
            .isEqualTo(Duration.ofSeconds(4));
});
~~~

Cách này hữu ích khi tích hợp thư viện bên thứ ba. Nếu bean là immutable hoặc không có setter, cách bind trực tiếp JavaBean có thể không phù hợp; hãy dùng properties object riêng rồi truyền giá trị qua constructor/builder hoặc customizer.

## 8. Kiểm tra property source, relaxed binding và thứ tự ưu tiên

Nếu test cho kết quả khác với môi trường thật, hãy kiểm tra nguồn giá trị trước khi kết luận binder bị lỗi.

### 8.1. Đọc giá trị hiệu lực trong Environment

Trong test hoặc khi chẩn đoán:

~~~java
String url = context.getEnvironment()
        .getProperty("spring.datasource.url");
~~~

Giá trị này cho biết property mà Environment trả về. Sau đó so sánh với `DataSourceProperties.getUrl()` và `HikariDataSource.getJdbcUrl()`.

Ba giá trị cần khớp trong ví dụ đơn giản:

~~~text
Environment property
        |
        v
DataSourceProperties.url
        |
        v
HikariDataSource.jdbcUrl
~~~

Nếu ba tầng khác nhau, xác định nơi giá trị thay đổi:
- Environment đã chọn nguồn property nào?
- Binder đã bind đúng field chưa?
- Bean factory method có dùng properties object đó không?
- Một customizer hoặc cấu hình khác có sửa bean sau khi tạo không?

### 8.2. Relaxed binding

Spring Boot hỗ trợ relaxed binding. Ví dụ property:

~~~properties
acme.client.connect-timeout=3s
~~~

có thể được bind vào field Java `connectTimeout`.

Với biến môi trường, tên chuẩn được chuyển theo quy tắc:
- dấu chấm thành `_`;
- bỏ dấu gạch ngang;
- chuyển thành chữ hoa.

Ví dụ:

~~~text
acme.client.connect-timeout
        |
        v
ACME_CLIENT_CONNECTTIMEOUT
~~~

Khi kiểm thử property source dạng environment variable, dùng đúng quy tắc này. Đừng nhầm với cách đặt tên biến có thêm dấu gạch dưới giữa `CONNECT` và `TIMEOUT`.

### 8.3. Property source ưu tiên cao hơn

Spring Boot hỗ trợ nhiều nguồn cấu hình: file application, profile-specific file, environment variables, JVM system properties và command-line arguments. Nguồn ưu tiên cao hơn có thể ghi đè nguồn thấp hơn.

Vì thế, nếu `application.yml` ghi `maximum-pool-size: 10` nhưng môi trường chạy có biến môi trường tương ứng đặt `7`, bean cuối cùng có thể nhận `7`.

Khi debug:
1. Xem giá trị trong `Environment`.
2. Xác định nguồn cấu hình thắng.
3. Kiểm tra giá trị sau binding.
4. Kiểm tra bean cuối cùng.

Không chỉ đọc file YAML rồi giả định đó là giá trị đang chạy.

## 9. Kiểm tra hành vi thật khi getter chưa đủ

Có những bean không công khai getter cho mọi cấu hình. Trong trường hợp đó, không nên dùng reflection để kiểm tra private field như giải pháp mặc định. Hãy xác minh hành vi công khai mà cấu hình đó được kỳ vọng tạo ra.

Ví dụ với DataSource, có thể mở connection đến H2 in-memory và chạy một câu query:

~~~java
@Test
void configuredDataSourceCanOpenAConnection() throws Exception {
    contextRunner.withPropertyValues(
            "spring.datasource.url=jdbc:h2:mem:connection_test",
            "spring.datasource.username=sa",
            "spring.datasource.hikari.maximum-pool-size=3"
    ).run(context -> {
        DataSource dataSource = context.getBean(DataSource.class);

        try (Connection connection = dataSource.getConnection();
             Statement statement = connection.createStatement();
             ResultSet resultSet = statement.executeQuery("SELECT 1")) {

            assertThat(resultSet.next()).isTrue();
            assertThat(resultSet.getInt(1)).isEqualTo(1);
        }
        catch (SQLException exception) {
            throw new AssertionError(
                    "The configured DataSource could not execute SELECT 1",
                    exception);
        }
    });
}
~~~

Thêm import:

~~~java
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

import javax.sql.DataSource;
~~~

Đoạn test này xác minh H2 connection thực sự hoạt động trong context test. Nó không kiểm tra kết nối production database; integration test cho PostgreSQL/MySQL/Oracle vẫn cần môi trường tương ứng, thường là Testcontainers hoặc một database test chuyên dụng.

## 10. Khi nào dùng ApplicationContextRunner, khi nào dùng SpringBootTest?

| Công cụ | Phù hợp khi | Điều cần lưu ý |
| --- | --- | --- |
| `ApplicationContextRunner` | Test một auto-configuration, property, condition hoặc bean back-off | Nhẹ, dễ kiểm soát; thường truyền property bằng `withPropertyValues` |
| `WebApplicationContextRunner` | Auto-configuration chỉ chạy trong servlet web context | Dùng khi condition phụ thuộc servlet context |
| `ReactiveWebApplicationContextRunner` | Auto-configuration phụ thuộc reactive web context | Không thay thế servlet runner |
| `@SpringBootTest` | Kiểm tra nhiều auto-configuration cùng ứng dụng, component scan và cấu hình gần production | Nặng hơn, context lớn hơn |
| Integration test với Testcontainers | Cần xác minh bean thực sự kết nối tới service/database tương thích production | Cần container runtime và thời gian chạy cao hơn |

Nếu mục tiêu là **giá trị đã bind vào bean mặc định**, `ApplicationContextRunner` thường là lựa chọn đầu tiên. Nếu cần xác nhận `application.yml`, profile, import config tree hoặc command line được nạp đúng như ứng dụng thật, bổ sung một test khởi động qua `SpringApplication` hoặc `@SpringBootTest` với cấu hình thực tế.

### Ví dụ @SpringBootTest

~~~java
@SpringBootTest(properties = {
        "spring.datasource.url=jdbc:h2:mem:spring_boot_test",
        "spring.datasource.username=sa",
        "spring.datasource.hikari.maximum-pool-size=5"
})
class DataSourceIntegrationTests {

    @Autowired
    DataSource dataSource;

    @Test
    void injectedDataSourceUsesConfiguredPool() {
        assertThat(dataSource)
                .isInstanceOf(HikariDataSource.class);

        HikariDataSource hikari =
                (HikariDataSource) dataSource;

        assertThat(hikari.getJdbcUrl())
                .isEqualTo("jdbc:h2:mem:spring_boot_test");
        assertThat(hikari.getMaximumPoolSize()).isEqualTo(5);
    }
}
~~~

Ví dụ trên cần `@SpringBootApplication` trong test application hoặc main source để `@SpringBootTest` tìm thấy cấu hình khởi động. Nó kiểm tra bean được inject trong application context đầy đủ hơn, nhưng không nên thay thế các test nhỏ để cô lập từng nhánh auto-configuration.

## 11. Kiểm tra validation và trường hợp cấu hình không hợp lệ

Nếu properties class dùng `@Validated`, property sai có thể khiến context không khởi động.

Ví dụ:

~~~java
@ConfigurationProperties("acme.client")
@Validated
public class AcmeClientProperties {

    @NotBlank
    private String endpoint;

    @Min(1)
    private int maxConnections = 8;

    // Getter/setter.
}
~~~

Cần có dependency validation phù hợp, chẳng hạn `spring-boot-starter-validation`.

Test nên kiểm tra cả hai trường hợp:
- Giá trị hợp lệ tạo context và bean;
- Giá trị không hợp lệ làm context startup fail với nguyên nhân validation rõ ràng.

Với `ApplicationContextRunner`, có thể đọc `context.getStartupFailure()` khi context không khởi động. Đừng chỉ assert bean vắng mặt, vì bean vắng mặt có thể do condition không match hoặc do context đã fail trước khi đăng ký bean.

## 12. Lỗi thường gặp và cách khắc phục

| Lỗi | Vì sao chưa đủ | Cách sửa |
| --- | --- | --- |
| Chỉ assert properties bean | Factory method có thể không dùng đúng field | Assert thêm getter hoặc hành vi của bean cuối cùng |
| Chỉ assert bean tồn tại | Bean có thể nhận giá trị mặc định hoặc sai property | Assert các giá trị cụ thể trên bean |
| Kiểm tra `Environment` rồi kết luận bean đúng | Bean có thể được tạo với cấu hình khác hoặc bị customizer sửa | Kiểm tra cả Environment, properties object và bean |
| Kiểm tra default bằng `Environment.getProperty` | Default trong class không nhất thiết được thêm vào Environment | Assert trên properties bean |
| Chỉ kiểm tra `spring.datasource.*` | Bỏ sót `spring.datasource.hikari.*` | Assert pool-specific property trên `HikariDataSource` |
| User bean đã thay default nhưng test vẫn mong bean mặc định | `@ConditionalOnMissingBean` khiến auto-configuration back off | Viết test riêng cho custom bean và test back-off |
| Dùng `@Primary` để che bean dư | Không xác nhận default bean có back off | Assert số lượng bean và absence của default type/name |
| Test ApplicationContextRunner nhưng mong tự load application.yml | Runner thường được cấp property trực tiếp, không phải full Config Data bootstrap | Dùng SpringApplication/@SpringBootTest cho Config Data |
| Dùng reflection đọc private field | Phụ thuộc implementation, dễ vỡ khi nâng cấp | Dùng getter hoặc test hành vi công khai |
| Chỉ test context startup | Bean có thể tạo được nhưng cấu hình sai | Assert property values và khi cần, thực hiện thao tác thật |
| Test với database ngoài | Test phụ thuộc trạng thái môi trường | Dùng H2 hoặc Testcontainers tùy mục tiêu |

## 13. Quy trình kiểm tra theo từng bước

Khi một bean mặc định có giá trị không như mong đợi:

1. **Xác định bean mặc định:** tên, type, auto-configuration class và factory method tạo nó.
2. **Tìm property prefix:** xem `@ConfigurationProperties`, `@ConfigurationProperties` trên `@Bean`, hoặc nơi đọc `Environment`.
3. **Tách property chung và property riêng implementation:** ví dụ `spring.datasource.*` so với `spring.datasource.hikari.*`.
4. **Tạo test context nhỏ:** dùng `ApplicationContextRunner` và nạp đúng auto-configuration.
5. **Cấp giá trị test rõ ràng:** dùng giá trị khác default để phát hiện binder/factory method bỏ sót.
6. **Assert properties bean:** xác nhận Binder chuyển giá trị đúng kiểu.
7. **Assert bean cuối cùng:** kiểm tra getter hoặc hành vi thực tế.
8. **Test default values:** không cấp property và kiểm tra giá trị mặc định trên object/bean.
9. **Test user override:** thêm bean thay thế và xác nhận default bean back off.
10. **Kiểm tra nguồn cấu hình thật:** nếu khác test, xem profile, environment variable, command line và Config Data.
11. **Chạy integration test khi cần:** xác minh kết nối hoặc giao tiếp với hệ thống thật.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao assert `DataSourceProperties.getUrl()` đúng vẫn chưa đủ?

**Đáp án:** Vì bean `DataSource` có thể không dùng properties đó, hoặc một cấu hình khác thay thế bean. Cần assert URL trên implementation DataSource cuối cùng.

**Câu 2.** Property nào điều chỉnh số connection tối đa của Hikari?

**Đáp án:** `spring.datasource.hikari.maximum-pool-size`. Đây là cấu hình riêng của Hikari, không phải field chung trong `DataSourceProperties`.

**Câu 3.** Default khai báo trong field của `@ConfigurationProperties` có nhất thiết xuất hiện trong `Environment` không?

**Đáp án:** Không. Default có thể chỉ tồn tại trên object sau binding; hãy assert trực tiếp trên object.

**Câu 4.** Khi ứng dụng tự cung cấp DataSource, auto-configuration mặc định có thể làm gì?

**Đáp án:** Với `@ConditionalOnMissingBean(DataSource.class)`, Boot có thể back off và giữ bean do ứng dụng cung cấp. Test cần xác nhận default bean không còn được đăng ký.

**Câu 5.** Khi nào nên dùng `ApplicationContextRunner` thay `@SpringBootTest`?

**Đáp án:** Khi cần kiểm tra một auto-configuration với property, classpath và user bean được kiểm soát độc lập. Dùng `@SpringBootTest` khi cần toàn bộ application context hoặc Config Data bootstrap thực tế.

**Câu 6.** Nếu bean không có getter cho cấu hình, nên kiểm tra bằng cách nào?

**Đáp án:** Kiểm tra hành vi công khai mà cấu hình đó tạo ra, ví dụ mở connection và chạy query với DataSource test. Tránh phụ thuộc private field bằng reflection.

## 15. Tài liệu tham khảo chính thức

- Spring Boot 3.5 Reference — Externalized Configuration, `@ConfigurationProperties`, relaxed binding, default values và property sources: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Spring Boot 3.5 Reference — Creating Your Own Auto-configuration, phần Testing your Auto-configuration và `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 API — `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Boot 3.5 API — `DataSourceAutoConfiguration`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.html
- Spring Boot 3.5 API — `DataSourceProperties`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceProperties.html
- HikariCP API — `HikariDataSource`: https://javadoc.io/doc/com.zaxxer/HikariCP/latest/com/zaxxer/hikari/HikariDataSource.html

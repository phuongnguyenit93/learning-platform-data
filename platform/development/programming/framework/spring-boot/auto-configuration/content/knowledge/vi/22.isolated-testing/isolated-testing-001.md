# ApplicationContextRunner và lợi ích của context nhỏ cho kiểm thử tự cấu hình

## 1. Vì sao cần kiểm thử auto-configuration độc lập?

Một auto-configuration của Spring Boot thường đăng ký bean khi một số điều kiện được thỏa mãn: class có trên classpath, property được bật, ứng dụng chưa cung cấp bean thay thế hoặc ứng dụng đang chạy một loại web stack phù hợp.

Nếu chỉ kiểm thử bằng cách khởi động toàn bộ ứng dụng với `@SpringBootTest`, mỗi thay đổi nhỏ có thể kéo theo nhiều thành phần không liên quan: component scan, database, web server, messaging, cache, security và các auto-configuration khác. Test chậm hơn, khó xác định nguyên nhân lỗi và có thể phụ thuộc vào môi trường bên ngoài.

`ApplicationContextRunner` giải quyết bài toán này bằng cách tạo **một ApplicationContext nhỏ, mới cho từng lần chạy**, nạp đúng cấu hình cần kiểm tra, cho phép đặt properties hoặc user beans, rồi đóng context sau khi callback hoàn tất.

Công cụ này đặc biệt phù hợp để kiểm tra:

- Auto-configuration có tạo bean mặc định khi điều kiện đúng không.
- Bean mặc định có back off khi người dùng cung cấp bean riêng không.
- `@ConditionalOnProperty` phản ứng đúng với giá trị có mặt, vắng mặt và `false` không.
- `@ConditionalOnClass` có bỏ qua integration khi dependency không nằm trên classpath không.
- `@ConfigurationProperties` có bind đúng giá trị và default không.
- Các bean phụ thuộc có được inject đúng và context có khởi động thành công không.
- Auto-configuration có hoạt động độc lập với những module khác không.

**Mục tiêu không phải kiểm thử mọi chức năng của ứng dụng.** Ta kiểm thử hợp đồng của một nhóm cấu hình và những bean mà nhóm đó chịu trách nhiệm đăng ký.

## 2. ApplicationContextRunner hoạt động như thế nào?

`ApplicationContextRunner` thuộc module `spring-boot-test`, package:

```java
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
```

Một runner mô tả cách tạo context. Mỗi lời gọi `run(...)` tạo context theo cấu hình đã ghép, thực thi callback test, rồi đóng context. Vì vậy, các lần chạy độc lập không dùng chung singleton bean hoặc trạng thái ApplicationContext.

Luồng cơ bản:

```text
Tạo ApplicationContextRunner
          |
          v
Thêm auto-configurations cần kiểm thử
          |
          v
Thêm user configuration / properties / classloader
          |
          v
runner.run(context -> { assertions })
          |
          v
Tạo ApplicationContext mới
          |
          v
Đăng ký bean definitions và đánh giá conditions
          |
          v
Khởi tạo các bean cần thiết
          |
          v
Assertions trong callback
          |
          v
Đóng context
```

Runner mặc định dùng một `AnnotationConfigApplicationContext` phù hợp cho kiểm thử cấu hình không phải web. Nó không tự khởi động Tomcat/Jetty và không tự quét mọi auto-configuration của ứng dụng. Bạn chỉ nạp những cấu hình cần kiểm thử.

### 2.1. Đưa auto-configuration vào runner

Cách phổ biến:

```java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(MyAutoConfiguration.class)
                );
```

`AutoConfigurations.of(...)` tạo tập hợp auto-configuration được Spring Boot xử lý theo thứ tự auto-configuration. Chỉ những class được truyền vào mới thuộc tập hợp này; runner không tự tìm toàn bộ auto-configuration imports như khi chạy ứng dụng hoàn chỉnh.

Điểm này giúp test tập trung. Nếu đang kiểm tra `CacheAutoConfiguration`, không cần vô tình nạp `DataSourceAutoConfiguration`, `WebMvcAutoConfiguration` hoặc các cấu hình không liên quan.

Nếu auto-configuration của thư viện có nhiều lớp phụ thuộc nhau, truyền đầy đủ các auto-configuration liên quan hoặc tạo một nhóm cấu hình test có chủ đích. Tránh thêm mọi auto-configuration chỉ để làm context giống production hơn; việc đó làm giảm lợi ích của test nhỏ.

### 2.2. Đăng ký user configuration

Dùng `withUserConfiguration(...)` để đưa cấu hình do ứng dụng cung cấp vào context:

```java
contextRunner
        .withUserConfiguration(UserClientConfiguration.class)
        .run(context -> {
            // Kiểm tra bean người dùng và bean mặc định.
        });
```

Điều này hữu ích để kiểm tra `@ConditionalOnMissingBean`, `@Primary`, `@Qualifier` hoặc customizer do người dùng đăng ký. User configuration được xử lý theo cơ chế của runner cùng auto-configuration đã khai báo.

### 2.3. Đưa property vào context

Dùng `withPropertyValues(...)`:

```java
contextRunner
        .withPropertyValues(
                "demo.client.enabled=true",
                "demo.client.endpoint=https://api.example.test"
        )
        .run(context -> {
            // Đọc bean đã được cấu hình từ property.
        });
```

Các giá trị này được thêm vào Environment của context test. Có thể gọi `withPropertyValues(...)` nhiều lần để ghép các nhóm property. Khi muốn kiểm tra property vắng mặt, hãy tạo một lần chạy không cung cấp key đó; đừng giả định rằng giá trị default của một object `@ConfigurationProperties` cũng xuất hiện trong Environment.

### 2.4. Thay classpath bằng ClassLoader riêng

Một số auto-configuration phụ thuộc `@ConditionalOnClass`. Muốn kiểm tra nhánh class có hoặc không có, dùng `withClassLoader(...)` cùng `FilteredClassLoader`:

```java
contextRunner
        .withClassLoader(new FilteredClassLoader(OptionalClient.class))
        .run(context -> {
            // OptionalClient không có trên classpath của context này.
        });
```

`FilteredClassLoader` thuộc `spring-boot-test`. Nó giúp giả lập một thư viện bị thiếu mà không cần tạo project thứ hai hoặc chỉnh dependency file trong lúc chạy test.

### 2.5. Các tùy chọn hữu ích khác

| Phương thức | Mục đích |
| --- | --- |
| `withBean(...)` | Đăng ký bean test bằng kiểu, tên hoặc supplier |
| `withUserConfiguration(...)` | Thêm cấu hình do ứng dụng cung cấp |
| `withPropertyValues(...)` | Thêm property vào Environment |
| `withSystemProperties(...)` | Cung cấp system properties cho lần chạy |
| `withClassLoader(...)` | Chọn classloader cho context |
| `withInitializer(...)` | Chạy `ApplicationContextInitializer` |
| `withParent(...)` | Gắn parent context nếu cần kiểm tra hierarchy |
| `withAllowBeanDefinitionOverriding(...)` | Điều khiển chính sách bean definition overriding |
| `withConfiguration(...)` | Thêm nhóm auto-configuration |
| `run(...)` | Tạo context, chạy assertion callback rồi đóng context |

Không cần dùng tất cả phương thức trong mọi test. Hãy chỉ thêm đầu vào làm thay đổi nhánh điều kiện đang kiểm tra.

## 3. Ví dụ đầy đủ: kiểm thử một auto-configuration

Ta xây một integration nhỏ cho `AuditClient`. Auto-configuration tạo client mặc định khi:

1. Class `AuditClient` hiện diện.
2. Property `demo.audit.enabled` là `true`, hoặc key chưa được khai báo.
3. Ứng dụng chưa đăng ký một bean `AuditClient` phù hợp.

`AuditProperties` giữ `service-name`, còn `DefaultAuditClient` nhận giá trị qua constructor. Ví dụ không gọi mạng, vì mục tiêu là kiểm tra đăng ký bean và cấu hình.

### 3.1. Cấu trúc project

```text
application-context-runner-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── AuditAutoConfigurationTests.java
```

### 3.2. Tệp pom.xml

Dùng Spring Boot `3.5.0` và Java `17`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>application-context-runner-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

`spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ, Spring Test và `spring-boot-test` cho `ApplicationContextRunner`/`FilteredClassLoader`. Không cần web starter vì context mẫu không phải web.

### 3.3. Tệp AuditAutoConfigurationTests.java

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AuditAutoConfigurationTests {

    @ConfigurationProperties(prefix = "demo.audit")
    public static class AuditProperties {

        private String serviceName = "catalog-service";

        public String getServiceName() {
            return serviceName;
        }

        public void setServiceName(String serviceName) {
            this.serviceName = serviceName;
        }
    }

    @AutoConfiguration
    @EnableConfigurationProperties(AuditProperties.class)
    static class AuditAutoConfiguration {

        @Configuration(proxyBeanMethods = false)
        @ConditionalOnClass(name = "example.AuditClient")
        static class AuditClientConfiguration {

            @Bean
            @ConditionalOnMissingBean(AuditClient.class)
            @ConditionalOnProperty(
                    prefix = "demo.audit",
                    name = "enabled",
                    havingValue = "true",
                    matchIfMissing = true
            )
            AuditClient auditClient(AuditProperties properties) {
                return new DefaultAuditClient(properties.getServiceName());
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserAuditConfiguration {

        @Bean
        AuditClient customAuditClient() {
            return () -> "user-defined-audit";
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(AuditAutoConfiguration.class)
                    );

    @Test
    void createsDefaultClientWhenConditionsMatch() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(AuditProperties.class);
            assertThat(context).hasSingleBean(AuditClient.class);
            assertThat(context).hasBean("auditClient");

            AuditClient client = context.getBean(AuditClient.class);
            assertThat(client.serviceName()).isEqualTo("catalog-service");
        });
    }

    @Test
    void bindsPropertiesIntoTheDefaultClient() {
        runner.withPropertyValues("demo.audit.service-name=orders")
                .run(context -> {
                    AuditClient client = context.getBean(AuditClient.class);

                    assertThat(client.serviceName()).isEqualTo("orders");
                });
    }

    @Test
    void userBeanMakesTheDefaultClientBackOff() {
        runner.withUserConfiguration(UserAuditConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(AuditClient.class);
                    assertThat(context).hasBean("customAuditClient");
                    assertThat(context).doesNotHaveBean("auditClient");

                    AuditClient client = context.getBean(AuditClient.class);
                    assertThat(client.serviceName())
                            .isEqualTo("user-defined-audit");
                });
    }

    @Test
    void disabledPropertyPreventsDefaultClientCreation() {
        runner.withPropertyValues("demo.audit.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(AuditClient.class);
                    assertThat(context).hasSingleBean(AuditProperties.class);
                });
    }

    @Test
    void optionalIntegrationIsSkippedWhenItsClassIsMissing() {
        runner.withClassLoader(new FilteredClassLoader(AuditClient.class))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(AuditClient.class);
                    assertThat(context).hasSingleBean(AuditProperties.class);
                });
    }

    @Test
    void userBeanStillExistsWhenDefaultFeatureIsDisabled() {
        runner.withUserConfiguration(UserAuditConfiguration.class)
                .withPropertyValues("demo.audit.enabled=false")
                .run(context -> {
                    assertThat(context).hasSingleBean(AuditClient.class);
                    assertThat(context).hasBean("customAuditClient");
                    assertThat(context).doesNotHaveBean("auditClient");
                });
    }
}

interface AuditClient {
    String serviceName();
}

record DefaultAuditClient(String serviceName) implements AuditClient {
}
```

### 3.4. Chạy test

Tại thư mục có `pom.xml`, dùng JDK 17+ và Maven:

```bash
java -version
mvn -version
mvn test
```

**Kết quả mong đợi:** sáu test JUnit pass và Maven kết thúc bằng `BUILD SUCCESS` nếu dependency tải thành công. Test không in stdout nghiệp vụ cố định; kết quả chi tiết nằm trong `target/surefire-reports`.

Ví dụ là một test class đầy đủ, nhưng auto-configuration nằm trong test source để tập trung vào cách kiểm thử. Trong starter thực tế, class `AuditAutoConfiguration` thuộc `src/main/java`, được đăng ký trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; test chỉ import nó bằng `AutoConfigurations.of(...)`.

### 3.5. Đọc từng test như một hợp đồng

| Test | Điều kiện được thay đổi | Kết quả cần chứng minh |
| --- | --- | --- |
| `createsDefaultClientWhenConditionsMatch` | Không thêm property hoặc user bean | Client mặc định được tạo với default |
| `bindsPropertiesIntoTheDefaultClient` | `demo.audit.service-name=orders` | Binder truyền giá trị mới vào client |
| `userBeanMakesTheDefaultClientBackOff` | Đăng ký `AuditClient` do user tạo | Bean mặc định không xuất hiện |
| `disabledPropertyPreventsDefaultClientCreation` | `enabled=false` | Không tạo client mặc định |
| `optionalIntegrationIsSkippedWhenItsClassIsMissing` | Lọc `AuditClient` khỏi classpath | Nhánh optional không được kích hoạt |
| `userBeanStillExistsWhenDefaultFeatureIsDisabled` | User bean và `enabled=false` | Property chỉ tắt bean mặc định, không xóa bean user |

Điểm đáng chú ý là test cuối. `@ConditionalOnProperty` nằm trên factory tạo bean mặc định; nó không phải chính sách cấm mọi bean `AuditClient` trong context. Vì thế bean user vẫn tồn tại.

## 4. Vì sao context nhỏ làm test tốt hơn?

### 4.1. Tốc độ và phạm vi lỗi rõ ràng

`ApplicationContextRunner` không quét toàn ứng dụng và không khởi động web server. Khi một assertion thất bại, phạm vi điều tra thường chỉ gồm:

- Auto-configuration được đưa vào runner.
- User configuration được thêm vào lần chạy đó.
- Property values của lần chạy.
- Classpath/classloader của lần chạy.
- Dependency mà bean đang khởi tạo yêu cầu.

Một test có thể chạy nhiều biến thể bằng cách gọi `run(...)` nhiều lần, mỗi lần với builder khác nhau. Runner được thiết kế bất biến theo kiểu fluent: `withPropertyValues(...)` trả về runner đã cấu hình để sử dụng cho lần chạy tiếp theo, không sửa trạng thái context cũ.

### 4.2. Không cần database, broker hoặc HTTP server thật

Nếu câu hỏi chỉ là "auto-configuration có tạo `AuditClient` khi property bật không?", test không cần kết nối database hay gửi HTTP. Có thể thay dependency bằng bean giả, supplier hoặc mock trong context.

Tuy nhiên, context nhỏ không chứng minh giao tiếp thật hoạt động. Khi client có logic HTTP/JDBC, vẫn cần unit test và integration test cho timeout, serialization, lỗi mạng, transaction, schema hoặc driver phù hợp.

### 4.3. Test điều kiện theo ma trận

Auto-configuration thường có nhiều condition. Thay vì một test lớn, hãy tách thành các trường hợp độc lập:

| Class trên classpath | Property | User bean | Kết quả mặc định |
| --- | --- | --- | --- |
| Có | Thiếu, `matchIfMissing=true` | Không | Tạo |
| Có | `true` | Không | Tạo |
| Có | `false` | Không | Không tạo |
| Có | `true` | Có | Back off |
| Không | Bất kỳ | Không | Không tạo integration |
| Không | Bất kỳ | Có | Phụ thuộc API user bean và các type còn lại; integration optional vẫn phải được bỏ qua |

Không cần test mọi tổ hợp nếu condition độc lập và đã được bao phủ. Nhưng các điều kiện lồng nhau hoặc có interaction nên có test riêng để chứng minh kết quả thực tế.

## 5. Những assertion và kỹ thuật hữu ích

### 5.1. Kiểm tra bean tồn tại và không tồn tại

Các assertion thường dùng:

```java
assertThat(context).hasSingleBean(AuditClient.class);
assertThat(context).hasBean("auditClient");
assertThat(context).doesNotHaveBean(AuditClient.class);
assertThat(context).doesNotHaveBean("auditClient");
```

Dùng kiểm tra theo type khi contract là một bean của kiểu đó; dùng tên khi tên bean là điều cần kiểm tra cụ thể. Tránh assert tên bean nội bộ không được công bố trong contract của thư viện.

### 5.2. Kiểm tra bean và giá trị thực tế

```java
AuditClient client = context.getBean(AuditClient.class);
assertThat(client.serviceName()).isEqualTo("orders");
```

Kiểm tra hành vi qua interface giúp test ít phụ thuộc implementation. Nếu bean là proxy, assertion vào concrete class hoặc tên class sinh tự động có thể làm test mong manh.

### 5.3. Kiểm tra context khởi động thất bại

Nếu một tổ hợp configuration phải thất bại, có thể kiểm tra startup failure:

```java
runner.withPropertyValues("demo.audit.timeout=invalid")
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure()).isNotNull();
        });
```

Đây là snippet minh họa; để test chính xác validation, hãy cấu hình constraint/dependency validation trong project và assert root cause/message phù hợp. Không nên chỉ assert `hasFailed()` nếu nhiều lỗi khác nhau đều có thể khiến context thất bại.

### 5.4. Kiểm tra classpath optional

```java
runner.withClassLoader(new FilteredClassLoader(OptionalCodec.class))
        .run(context -> {
            assertThat(context).doesNotHaveBean(CodecService.class);
        });
```

Cần đặt `@ConditionalOnClass` ở configuration class hoặc nested configuration phù hợp để Spring có thể bỏ qua toàn bộ nhánh có reference tới optional type. Nếu optional type xuất hiện trực tiếp trong method signature của cấu hình gốc, class có thể bị load/introspect trước khi condition dự kiến bảo vệ nó.

Với thư viện optional, nested configuration có condition thường an toàn hơn:

```java
@AutoConfiguration
public class CodecAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.example.codec.OptionalCodec")
    static class OptionalCodecConfiguration {

        @Bean
        CodecService codecService(OptionalCodec codec) {
            return new DefaultCodecService(codec);
        }
    }
}
```

Đây là snippet kiến trúc, giả định `OptionalCodec`, `CodecService` và `DefaultCodecService` thuộc thư viện tương ứng. Dùng `name` cho condition giúp cấu hình gốc không cần resolve class optional chỉ để đọc annotation; nested class cô lập method signature phụ thuộc vào class đó.

### 5.5. Kiểm tra thứ tự auto-configuration

Nếu một bean phụ thuộc vào bean do auto-configuration khác tạo, đưa các auto-configuration liên quan vào `AutoConfigurations.of(...)`. Runner xử lý thứ tự auto-configuration theo cơ chế của Spring Boot.

Nếu test chỉ thêm một class nhưng thiếu auto-configuration cung cấp dependency, lỗi `NoSuchBeanDefinitionException` có thể phản ánh test setup thiếu cấu hình, không phải lỗi production. Trước khi sửa code, xác định bean còn thiếu thuộc trách nhiệm auto-configuration nào.

## 6. Khi nào dùng WebApplicationContextRunner hoặc ReactiveWebApplicationContextRunner?

`ApplicationContextRunner` kiểm thử context không phải web. Khi auto-configuration cần Servlet hoặc Reactive web infrastructure, dùng runner đúng loại:

| Runner | Context | Phù hợp |
| --- | --- | --- |
| `ApplicationContextRunner` | Generic annotation context | JDBC, client, properties, cache, bean conditions |
| `WebApplicationContextRunner` | Servlet web application context | MVC, Servlet filters, web server factory auto-configuration |
| `ReactiveWebApplicationContextRunner` | Reactive web application context | WebFlux, reactive handlers, codecs |

Ví dụ Servlet:

```java
new WebApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(MyWebAutoConfiguration.class)
        )
        .run(context -> {
            // Kiểm tra bean MVC hoặc Servlet.
        });
```

Ví dụ Reactive:

```java
new ReactiveWebApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(MyReactiveAutoConfiguration.class)
        )
        .run(context -> {
            // Kiểm tra bean WebFlux.
        });
```

Các runner này cũng thuộc nhóm công cụ test của Spring Boot. Chúng tạo loại context phù hợp; chúng không thay thế test request/response qua MockMvc hoặc WebTestClient nếu cần xác nhận hành vi HTTP.

## 7. ApplicationContextRunner khác @SpringBootTest và @WebMvcTest thế nào?

| Công cụ | Phạm vi | Nên dùng khi |
| --- | --- | --- |
| `ApplicationContextRunner` | Một nhóm auto-configuration/bean nhỏ, do test chỉ định | Test conditions, properties, back-off, classpath |
| `WebApplicationContextRunner` | Nhóm cấu hình Servlet web | Test auto-configuration web ở mức context |
| `ReactiveWebApplicationContextRunner` | Nhóm cấu hình reactive web | Test auto-configuration WebFlux |
| `@WebMvcTest` | MVC test slice, tập trung controller/MVC components | Test mapping, validation, serialization, MVC advice |
| `@SpringBootTest` | Toàn bộ ứng dụng hoặc context gần production | Integration test nhiều module và cấu hình thực tế |

Một cách tổ chức test hiệu quả:

1. Dùng `ApplicationContextRunner` cho logic điều kiện và bean wiring.
2. Dùng `@WebMvcTest` hoặc WebApplicationContextRunner cho MVC-specific behavior.
3. Dùng `@SpringBootTest` cho những luồng cần nhiều module phối hợp.
4. Dùng Testcontainers hoặc môi trường tích hợp khi cần chứng minh tương tác với database/broker thật.

Không cần thay mọi `@SpringBootTest` bằng runner. Chọn công cụ theo câu hỏi mà test phải trả lời.

## 8. Những giới hạn cần hiểu

- Runner không tự mô phỏng mọi phần của `SpringApplication`. Các listener, initializer hoặc environment processing đặc thù của ứng dụng có thể cần được thêm rõ ràng.
- Runner mặc định không tạo Servlet/Reactive web context.
- Classpath filter giả lập việc thiếu class, nhưng không chứng minh mọi dependency conflict hoặc binary incompatibility.
- Bean giả/mock giúp cô lập wiring, nhưng không kiểm chứng giao tiếp thật.
- Nếu không thêm một auto-configuration vào `AutoConfigurations.of(...)`, runner không tự kiểm tra nó.
- `ApplicationContextRunner` tạo context nhỏ; test pass không chứng minh toàn bộ ứng dụng production khởi động thành công.
- Test không nên phụ thuộc vào thứ tự đăng ký bean không được bảo đảm hoặc tên class proxy.
- Khi condition có tương tác giữa nhiều auto-configuration, phải thêm đủ nhóm liên quan để phản ánh dependency contract.

## 9. Lỗi thường gặp và cách khắc phục

1. **Quên thêm auto-configuration vào runner.** Test không thấy bean vì class cấu hình chưa được nạp. Dùng `withConfiguration(AutoConfigurations.of(...))`.
2. **Nhầm runner tự quét toàn ứng dụng.** Runner chỉ tạo context từ cấu hình được chỉ định; thêm `withUserConfiguration` hoặc `withConfiguration` có chủ đích.
3. **Chỉ test trường hợp property=true.** Bổ sung trường hợp thiếu key, false và giá trị không hợp lệ nếu contract quy định.
4. **Không test user bean back-off.** Một starter tốt phải cho ứng dụng thay bean mặc định theo điều kiện đã công bố.
5. **Không kiểm tra classpath thiếu optional dependency.** Dùng `FilteredClassLoader` để kiểm tra nhánh `@ConditionalOnClass`.
6. **Đặt optional type ở cấu hình gốc.** Cô lập reference trong nested configuration có `@ConditionalOnClass`.
7. **Dùng ApplicationContextRunner cho MVC mà không có web context.** Chuyển sang `WebApplicationContextRunner` hoặc test slice MVC.
8. **Chỉ assert context không lỗi.** Kiểm tra bean thực sự tồn tại, giá trị properties và hành vi quan trọng.
9. **Assert vào tên class proxy.** Kiểm tra interface và hành vi thay vì implementation class do framework sinh.
10. **Test quá nhiều auto-configuration không liên quan.** Chỉ thêm nhóm cần thiết; test càng rộng càng khó tìm nguyên nhân.
11. **Dùng chung context hoặc mutable state giữa test.** Mỗi lần `run` tạo context riêng; tránh static mutable state ngoài context.
12. **Dùng mock cho mọi dependency rồi kết luận integration chạy thật.** Bổ sung integration test với database/broker/client thật ở nơi cần.
13. **Không kiểm tra startup failure đúng nguyên nhân.** Assert root cause hoặc message cụ thể khi kiểm thử validation/condition failure.
14. **Quên dependency test.** Đảm bảo module có `spring-boot-starter-test` hoặc dependency tương ứng trong test scope.
15. **Nhầm classpath của test module với classpath consumer.** Test trong module autoconfigure có thể luôn thấy optional dependency do test dependency; thêm consumer sample không có thư viện đó.

## 10. Checklist viết test auto-configuration

- [ ] Đã chọn đúng runner: generic, Servlet hoặc Reactive.
- [ ] Đã thêm đúng auto-configuration bằng `AutoConfigurations.of(...)`.
- [ ] Có test default khi không có property.
- [ ] Có test property override và disable.
- [ ] Có test bean người dùng làm auto-configuration back off.
- [ ] Có test optional class vắng mặt bằng `FilteredClassLoader` khi có class condition.
- [ ] Có assertion bean theo type/name phù hợp và giá trị thực tế.
- [ ] Có test startup failure cho cấu hình không hợp lệ nếu thư viện hỗ trợ validation.
- [ ] Context test không cần database/network thật nếu câu hỏi chỉ là bean wiring.
- [ ] Có integration test riêng cho giao tiếp thật khi cần.
- [ ] Đã xác nhận runner không bỏ sót auto-configuration cung cấp dependency.
- [ ] Test không dựa vào class proxy, thứ tự ngẫu nhiên hoặc implementation detail.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** `ApplicationContextRunner` phù hợp nhất để kiểm tra điều gì?  
**Đáp án:** Các nhánh auto-configuration độc lập như class conditions, property conditions, bean back-off, properties binding và dependency injection trong context nhỏ.

**Câu 2.** Runner có tự nạp mọi auto-configuration trong ứng dụng không?  
**Đáp án:** Không. Test cần chỉ định nhóm cấu hình, thường qua `AutoConfigurations.of(...)`.

**Câu 3.** Muốn kiểm tra auto-configuration back off khi user cung cấp bean, dùng phương thức nào?  
**Đáp án:** `withUserConfiguration(...)` hoặc `withBean(...)`, rồi assert bean mặc định không xuất hiện và bean user tồn tại.

**Câu 4.** Muốn kiểm tra nhánh `@ConditionalOnClass` khi thư viện không có trên classpath, dùng gì?  
**Đáp án:** `withClassLoader(new FilteredClassLoader(OptionalType.class))`.

**Câu 5.** Mỗi lần gọi `run(...)` có dùng lại ApplicationContext cũ không?  
**Đáp án:** Không. Runner tạo context mới cho lần chạy và đóng context sau callback, giúp các scenario độc lập.

**Câu 6.** Có nên dùng `ApplicationContextRunner` để test controller mapping và HTTP serialization?  
**Đáp án:** Dùng web runner hoặc `@WebMvcTest`/MockMvc cho MVC behavior; ApplicationContextRunner mặc định không phải web context.

**Câu 7.** Test runner pass có chứng minh database thật kết nối thành công không?  
**Đáp án:** Không nếu test chỉ dùng bean giả hoặc không mở kết nối. Cần integration test với database phù hợp.

**Câu 8.** Vì sao cần kiểm tra cả property thiếu và property false?  
**Đáp án:** `matchIfMissing`, default value và điều kiện `havingValue` quyết định hành vi khác nhau; chỉ test true không chứng minh hai nhánh còn lại.

## Tài liệu tham khảo chính thức

- Spring Boot 3.5 Reference — Creating Your Own Auto-configuration, phần kiểm thử bằng `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 API — `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Boot 3.5 API — `WebApplicationContextRunner`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/WebApplicationContextRunner.html
- Spring Boot 3.5 API — `ReactiveWebApplicationContextRunner`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/ReactiveWebApplicationContextRunner.html
- Spring Boot 3.5 API — `FilteredClassLoader`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/FilteredClassLoader.html
- Spring Boot 3.5 Reference — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html

**Ghi nhớ:** `ApplicationContextRunner` cho phép kiểm thử một auto-configuration trong context nhỏ, cô lập và có thể tái tạo. Chỉ nạp đúng cấu hình cần thiết, thay đổi properties/user beans/classpath theo từng scenario, rồi kiểm tra bean và hành vi thực tế. Dùng web runner hoặc test integration khi câu hỏi vượt khỏi phạm vi bean wiring.

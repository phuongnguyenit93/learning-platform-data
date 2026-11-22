# Quan hệ giữa test slice, bộ tự cấu hình được nhập và kiểm thử toàn ứng dụng

## 1. Vì sao cùng một bean có thể xuất hiện trong test này nhưng biến mất ở test khác?

Spring Boot có nhiều cách dựng ApplicationContext cho kiểm thử. Hai cách thường gặp là:

- **Test slice** như **@WebMvcTest**, **@DataJpaTest**, **@JsonTest**, **@RestClientTest**: chỉ nạp một phần ứng dụng phù hợp với lớp cần kiểm tra.
- **Full application test** với **@SpringBootTest**: dựng context từ cấu hình chính của ứng dụng và áp dụng hệ thống auto-configuration tương ứng.

Điểm dễ nhầm là test slice **không phải full context bị tắt một vài bean**. Slice có cơ chế chọn component và một danh sách auto-configuration được nhập riêng. Vì vậy một auto-configuration có thể hoạt động trong ứng dụng thật nhưng không được nạp trong @WebMvcTest, hoặc một bean @Component tồn tại ở full context nhưng không được component scan của slice nhận vào.

Khi kiểm tra lỗi kiểu “bean có trong ứng dụng nhưng test không tìm thấy”, cần trả lời:

1. Test đang dùng loại context nào?
2. Slice đó quét những component nào?
3. Auto-configuration nào được nhập mặc định?
4. Auto-configuration của ứng dụng/thư viện có nằm trong danh sách đó không?
5. Nếu cần thêm cấu hình, nên dùng @Import, @ImportAutoConfiguration, @EnableConfigurationProperties hay chuyển sang @SpringBootTest?

Bài viết dùng **Spring Boot 3.5.16, Java 17+ và JUnit 5**. Danh sách auto-configuration cụ thể có thể thay đổi giữa các phiên bản Boot; khi điều tra dự án thật, luôn tra appendix đúng version đang chạy.

## 2. Mô hình ba lớp: test slice, imported auto-configuration và full context

Có thể hình dung quan hệ như sau:

~~~text
                         Spring Boot app
                               |
                    @SpringBootApplication
                               |
                    @EnableAutoConfiguration
                               |
                 AutoConfiguration.imports
                               |
                 Candidate auto-configurations
                               |
                 Conditions + classpath + beans
                               |
                     Full ApplicationContext
                               |
             @SpringBootTest (toàn ứng dụng)
                               |
          -------------------------------------------
          |                                         |
     Test slice                               Test full app
          |                                         |
   @WebMvcTest / @DataJpaTest                 @SpringBootTest
          |                                         |
   Component scan giới hạn                    Scan/config chính
          |                                         |
   Danh sách auto-config riêng                Auto-config đủ điều kiện
          |                                         |
   Imported auto-config subset                Nhiều tầng bean thực tế
          |
   Có thể bổ sung bằng
   @ImportAutoConfiguration
~~~

Ba khái niệm cần phân biệt:

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Test slice** | Cách tạo context giới hạn theo một phần ứng dụng, ví dụ web MVC hoặc JPA |
| **Imported auto-configuration** | Các lớp auto-configuration mà slice chủ động đưa vào context |
| **Full application test** | Context được dựng từ cấu hình chính, cho phép các component và auto-configuration của ứng dụng tham gia theo điều kiện |

Spring Boot có một nhóm annotation test trong module spring-boot-test-autoconfigure. Mỗi slice kết hợp annotation @...Test với một hoặc nhiều annotation @AutoConfigure... để nạp cấu hình cần thiết. Mỗi slice giới hạn component scan và chỉ tải một tập auto-configuration rất hẹp. Xem [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html).

## 3. Test slice làm gì và không làm gì?

### 3.1. Test slice tập trung vào một tầng

Một số ví dụ:

| Annotation | Phần được tập trung kiểm tra | Hạ tầng thường được auto-configure |
| --- | --- | --- |
| @WebMvcTest | Controller, MVC mapping, validation/converter/filter liên quan web | Spring MVC, message converters, MockMvc, một số cấu hình Security nếu có |
| @WebFluxTest | WebFlux controller và reactive web layer | WebFlux, codecs, WebTestClient |
| @DataJpaTest | Entity, repository, JPA mapping và truy vấn | DataSource, Hibernate/JPA, transaction, repository support |
| @JdbcTest | JDBC component/repository | DataSource, JdbcTemplate, transaction và test database support |
| @JsonTest | Serialize/deserialize JSON | Jackson/Gson/Jsonb và JSON tester |
| @RestClientTest | Code gọi REST service bên ngoài | RestClient/RestTemplate builder, message converter và mock server |

Các danh sách auto-configuration chính thức được liệt kê trong appendix [Spring Boot 3.5 — Test Slices](https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html). Ví dụ, @WebMvcTest có WebMvcAutoConfiguration, HttpMessageConvertersAutoConfiguration, MockMvcAutoConfiguration và một số cấu hình liên quan; @DataJpaTest có DataSourceAutoConfiguration, HibernateJpaAutoConfiguration, repository, transaction và test database support.

Đừng coi bảng trên là danh sách đầy đủ. Dependency có mặt trên classpath, thuộc tính test và điều kiện bean có thể làm tập cấu hình thực tế khác đi.

### 3.2. Component scan bị giới hạn

Ví dụ @WebMvcTest chỉ scan các loại component phù hợp với MVC như:
- @Controller và @ControllerAdvice;
- @JsonComponent;
- Converter và GenericConverter;
- Filter, HandlerInterceptor;
- WebMvcConfigurer, WebMvcRegistrations;
- HandlerMethodArgumentResolver.

Các @Component thông thường và bean @ConfigurationProperties không tự được scan trong slice này. Nếu cần properties bean, dùng @EnableConfigurationProperties; nếu cần component phụ trợ, import rõ cấu hình hoặc cung cấp mock. Xem [Spring Boot 3.5 — Auto-configured Spring MVC Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html).

@DataJpaTest cũng không scan regular @Component và @ConfigurationProperties; nó tập trung vào entity và Spring Data JPA repository. Nó thường dùng embedded database nếu dependency phù hợp có trên classpath và mặc định chạy test trong transaction rồi rollback sau mỗi test.

### 3.3. Vì sao không nên thêm nhiều slice annotation vào một test?

Không hỗ trợ ghép nhiều annotation @...Test slice trong cùng một test class, ví dụ:

~~~java
// Không dùng cách này để cố ghép hai slice.
@WebMvcTest
@DataJpaTest
class InvalidCombinedSliceTests {
}
~~~

Nếu cần thêm một số khả năng của slice khác, hãy chọn một slice chính rồi thêm annotation @AutoConfigure... thích hợp. Nếu mục tiêu là kiểm tra toàn bộ đường đi controller → service → repository, dùng @SpringBootTest thường rõ ràng hơn.

## 4. Bộ auto-configuration được nhập trong slice đến từ đâu?

Một slice không đơn giản quét tất cả file AutoConfiguration.imports rồi bật mọi auto-configuration. Annotation slice có metadata riêng để chỉ định nhóm auto-configuration mà nó cần.

Ví dụ về tư duy chọn cấu hình:

- @WebMvcTest cần MVC, message conversion, MockMvc và các integration web phù hợp.
- @DataJpaTest cần DataSource, JPA provider, repository, transaction và test database.
- @JsonTest cần JSON mapper và các JSON test helper.
- @RestClientTest cần client builder, message converter và MockRestServiceServer.

Các auto-configuration vẫn phải vượt qua điều kiện của chính chúng: classpath, property, bean đã tồn tại, loại ApplicationContext và các condition khác. Việc một class nằm trong danh sách imported **không bảo đảm bean của nó được tạo**.

Có thể diễn đạt:

~~~text
Slice imports auto-configuration class
                |
                v
Class-level conditions match?
                |
                v
Nested configuration / @Bean conditions match?
                |
                v
No user bean makes it back off?
                |
                v
Bean definition is registered
                |
                v
Bean instance is created when required
~~~

Đây là lý do cần phân biệt:
- **Được nhập (imported):** cấu hình được đưa vào quá trình xử lý.
- **Condition match:** điều kiện của cấu hình hoặc bean method đạt.
- **Bean definition được đăng ký:** Spring có metadata để tạo bean.
- **Instance được tạo:** object thực tế được khởi tạo khi lifecycle yêu cầu.

Chỉ nhìn annotation trên test class chưa đủ để kết luận bean cuối cùng chắc chắn tồn tại.

## 5. @ImportAutoConfiguration: bổ sung auto-configuration vào một slice

Khi slice thiếu một auto-configuration mà test cần, có thể thêm nó cho riêng test bằng @ImportAutoConfiguration.

Ví dụ:

~~~java
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.boot.autoconfigure.integration.IntegrationAutoConfiguration;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;

@JdbcTest
@ImportAutoConfiguration(IntegrationAutoConfiguration.class)
class JdbcIntegrationTests {
}
~~~

@ImportAutoConfiguration đưa auto-configuration được chỉ định vào context của test và để Spring Boot xử lý nó theo cơ chế auto-configuration.

**Không dùng @Import thông thường để nhập một lớp auto-configuration.** Spring Boot xử lý auto-configuration theo thứ tự và quy tắc riêng; @ImportAutoConfiguration là annotation đúng mục đích. Tài liệu chính thức minh họa cách này trong phần [Additional Auto-configuration and Slicing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html).

### 5.1. Khi nào dùng @ImportAutoConfiguration?

Dùng khi:
- Một slice cần thêm đúng một auto-configuration mà mặc định không nhập;
- Muốn kiểm tra tương tác giữa slice và auto-configuration của thư viện;
- Muốn kiểm tra một test với một tập auto-configuration rõ ràng;
- Cần giữ phạm vi test nhỏ, không muốn chuyển cả test sang full context.

### 5.2. Khi nào dùng @Import?

@Import phù hợp với cấu hình thông thường do ứng dụng sở hữu, ví dụ:
- Một lớp @Configuration cung cấp test fixture;
- Một bean converter, mapper hoặc helper cụ thể;
- Một cấu hình security cần dùng trong controller slice;
- Một @TestConfiguration bổ sung cho test.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
class GreetingTestSupportConfiguration {

    @Bean
    GreetingFormatter greetingFormatter() {
        return new GreetingFormatter();
    }
}

@WebMvcTest(GreetingController.class)
@Import(GreetingTestSupportConfiguration.class)
class GreetingControllerTests {
}
~~~

Nếu một lớp @Configuration có nhiều bean thuộc các domain khác nhau, nên tách nó thành các cấu hình nhỏ. Slice chỉ import đúng phần cần thiết, tránh kéo cả DataSource hoặc external client vào một test chỉ cần MVC.

### 5.3. Phân biệt các cơ chế nhập cấu hình

| Cơ chế | Dùng cho | Ví dụ |
| --- | --- | --- |
| @Import | Cấu hình/selector/bean configuration thông thường | @Import(MyTestConfiguration.class) |
| @ImportAutoConfiguration | Auto-configuration của Spring Boot | @ImportAutoConfiguration(MyLibraryAutoConfiguration.class) |
| @EnableConfigurationProperties | Đăng ký một hoặc nhiều properties type | @EnableConfigurationProperties(MyProperties.class) |
| @ComponentScan | Quét component theo package/filter | Dùng có chủ đích, tránh làm slice mất giới hạn |
| @SpringBootTest | Khởi tạo ứng dụng bằng cấu hình chính | @SpringBootTest |

## 6. Bổ sung auto-configuration cho mọi test dùng một slice

Nếu nhiều test @JdbcTest đều cần cùng một auto-configuration, không cần lặp @ImportAutoConfiguration ở từng class.

Có thể tạo file trong test resources:

~~~text
src/test/resources/META-INF/spring/
└── org.springframework.boot.test.autoconfigure.jdbc.JdbcTest.imports
~~~

Nội dung:

~~~text
com.example.IntegrationAutoConfiguration
~~~

Auto-configuration được liệt kê sẽ được thêm vào mọi test sử dụng @JdbcTest trên classpath đó.

Một số lưu ý:
- File phải nằm đúng META-INF/spring.
- Tên file phải tương ứng chính xác với annotation slice.
- Có thể dùng dòng bắt đầu bằng # để ghi chú.
- Cơ chế này áp dụng cho slice hoặc @AutoConfigure... annotation được meta-annotate bằng @ImportAutoConfiguration.
- Nếu chỉ một test cần cấu hình, @ImportAutoConfiguration trên test class thường dễ hiểu hơn.

Đây là cách mở rộng có phạm vi cho test suite, nên chỉ dùng khi tất cả test của slice đó thật sự cần cùng cấu hình.

## 7. @SpringBootTest: kiểm thử toàn ứng dụng

@SpringBootTest tạo ApplicationContext thông qua SpringApplication. Nếu không chỉ định cấu hình chính, Spring Boot tìm từ package của test đi lên cho đến khi gặp @SpringBootApplication hoặc @SpringBootConfiguration.

Khi chạy full context:
- Component scan của ứng dụng được áp dụng;
- Các auto-configuration được đăng ký bởi @EnableAutoConfiguration có thể tham gia;
- Các property sources của Spring Boot được cài vào context;
- Conditions tiếp tục quyết định bean nào được tạo;
- User-defined beans có thể khiến auto-configuration back off.

@SpringBootTest mặc định không khởi động server thật. Thuộc tính webEnvironment điều khiển môi trường:

| Giá trị | Hành vi |
| --- | --- |
| MOCK (mặc định) | Web ApplicationContext với mock web environment; không bật embedded server |
| RANDOM_PORT | Khởi động web server thật trên cổng ngẫu nhiên |
| DEFINED_PORT | Khởi động web server thật trên cổng cấu hình hoặc cổng mặc định |
| NONE | ApplicationContext không có web environment |

Nếu muốn dùng MockMvc trong full context, kết hợp @SpringBootTest với @AutoConfigureMockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class FullApplicationMvcTests {

    @Autowired
    MockMvc mockMvc;

    // Kiểm tra controller trong context của toàn ứng dụng.
}
~~~

Đây là **full application test có MockMvc**, không phải @WebMvcTest slice. Nó hữu ích khi cần xác minh controller cùng service, repository, security, serializer và cấu hình ứng dụng thật hoạt động với nhau.

Khi cần kiểm tra HTTP server thật, dùng webEnvironment = RANDOM_PORT hoặc DEFINED_PORT và gửi request qua HTTP client phù hợp. Chú ý server và test client chạy ở các thread khác nhau; transaction của test không tự rollback các thao tác đã thực hiện ở server thread.

Tham khảo [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html).

## 8. Ví dụ hoàn chỉnh: một custom auto-configuration được dùng trong slice và full test

Ví dụ tạo dịch vụ greeting. Auto-configuration cung cấp GreetingService mặc định nếu property bật và ứng dụng chưa tự cung cấp bean. Controller sử dụng service này.

### 8.1. Cấu trúc dự án

~~~text
greeting-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/demo/
    │   │   ├── DemoApplication.java
    │   │   ├── GreetingController.java
    │   │   ├── GreetingResponse.java
    │   │   ├── GreetingService.java
    │   │   ├── DefaultGreetingService.java
    │   │   └── autoconfigure/GreetingAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/demo/
            ├── GreetingAutoConfigurationTests.java
            ├── GreetingControllerSliceTests.java
            └── GreetingApplicationIntegrationTests.java
~~~

### 8.2. Maven dependencies

File pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>greeting-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

### 8.3. Service API và implementation mặc định

File GreetingService.java:

~~~java
package com.example.demo;

public interface GreetingService {

    String greet(String name);
}
~~~

File DefaultGreetingService.java:

~~~java
package com.example.demo;

public class DefaultGreetingService implements GreetingService {

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Implementation không cần @Component. Auto-configuration sẽ đăng ký bean mặc định bằng @Bean.

### 8.4. Auto-configuration

File autoconfigure/GreetingAutoConfiguration.java:

~~~java
package com.example.demo.autoconfigure;

import com.example.demo.DefaultGreetingService;
import com.example.demo.GreetingService;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService() {
        return new DefaultGreetingService();
    }
}
~~~

Ý nghĩa:
- @AutoConfiguration đánh dấu class là auto-configuration.
- @ConditionalOnProperty chỉ bật cấu hình khi demo.greeting.enabled=true; nếu property không được khai báo thì vẫn bật do matchIfMissing=true.
- @ConditionalOnMissingBean(GreetingService.class) cho phép ứng dụng tự cung cấp service khác.
- Bean mặc định chỉ được tạo khi điều kiện phù hợp.

### 8.5. Đăng ký auto-configuration cho ứng dụng Boot

Tạo file:

src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports

Nội dung:

~~~text
com.example.demo.autoconfigure.GreetingAutoConfiguration
~~~

Đây là cơ chế để auto-configuration được nhận diện khi ứng dụng dùng @EnableAutoConfiguration hoặc @SpringBootApplication. Full application test sẽ nạp class này qua cơ chế auto-configuration nếu resource đã được đóng gói trên classpath.

### 8.6. Controller và response

File GreetingResponse.java:

~~~java
package com.example.demo;

public record GreetingResponse(String message) {
}
~~~

File GreetingController.java:

~~~java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/greeting")
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/{name}")
    public GreetingResponse greet(@PathVariable String name) {
        return new GreetingResponse(this.greetingService.greet(name));
    }
}
~~~

File DemoApplication.java:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 8.7. Test riêng auto-configuration với ApplicationContextRunner

Trước khi kiểm tra slice hoặc full app, nên test logic auto-configuration độc lập. Điều này giúp xác minh property, condition và user override mà không cần MVC hoặc database.

File GreetingAutoConfigurationTests.java:

~~~java
package com.example.demo;

import com.example.demo.autoconfigure.GreetingAutoConfiguration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    GreetingAutoConfiguration.class));

    @Test
    void createsDefaultServiceWhenEnabledOrPropertyMissing() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(GreetingService.class);
            assertThat(context.getBean(GreetingService.class).greet("Ada"))
                    .isEqualTo("Hello, Ada");
        });
    }

    @Test
    void doesNotCreateServiceWhenDisabled() {
        runner.withPropertyValues("demo.greeting.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(GreetingService.class);
                });
    }

    @Test
    void userServiceMakesDefaultBeanBackOff() {
        runner.withUserConfiguration(CustomGreetingConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(GreetingService.class);
                    assertThat(context.getBean(GreetingService.class).greet("Ada"))
                            .isEqualTo("Custom, Ada");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomGreetingConfiguration {

        @Bean
        GreetingService greetingService() {
            return name -> "Custom, " + name;
        }
    }
}
~~~

Điểm cần kiểm tra:
- Không khai báo property: default service vẫn được tạo.
- Property false: service không được tạo.
- User configuration có service riêng: default bean back off và bean người dùng được dùng.

ApplicationContextRunner phù hợp để test một auto-configuration riêng lẻ, không phải full application test. Nếu cần kiểm tra missing optional dependency, có thể dùng FilteredClassLoader để mô phỏng classpath thiếu thư viện.

### 8.8. Test slice: @WebMvcTest và @ImportAutoConfiguration

File GreetingControllerSliceTests.java:

~~~java
package com.example.demo;

import com.example.demo.autoconfigure.GreetingAutoConfiguration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(GreetingController.class)
@ImportAutoConfiguration(GreetingAutoConfiguration.class)
class GreetingControllerSliceTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void controllerUsesDefaultServiceImportedForThisSlice() throws Exception {
        mockMvc.perform(get("/greeting/{name}", "Ada"))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.message").value("Hello, Ada"));
    }
}
~~~

@WebMvcTest(GreetingController.class) giới hạn component scan vào controller và các MVC component phù hợp. GreetingService không phải MVC component nên không được tìm qua component scan. @ImportAutoConfiguration đưa GreetingAutoConfiguration vào slice để cung cấp service mặc định.

Nếu bỏ @ImportAutoConfiguration, test có thể thất bại khi tạo controller vì không tìm thấy GreetingService. Đây là ví dụ điển hình cho tình huống auto-configuration của ứng dụng có trong full context nhưng không nằm trong tập imported của slice.

Test này không bật embedded HTTP server. MockMvc thực thi request qua Spring MVC infrastructure trong mock web context.

### 8.9. Full application test: @SpringBootTest

File GreetingApplicationIntegrationTests.java:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class GreetingApplicationIntegrationTests {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ApplicationContext applicationContext;

    @Test
    void applicationDiscoversAutoConfigurationAndServesRequest()
            throws Exception {

        assertThat(applicationContext)
                .hasSingleBean(GreetingService.class);

        mockMvc.perform(get("/greeting/{name}", "Ada"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Hello, Ada"));
    }
}
~~~

Ở test này:
- @SpringBootTest tìm DemoApplication và dựng full application context.
- @SpringBootApplication bật auto-configuration.
- AutoConfiguration.imports giúp Spring Boot phát hiện GreetingAutoConfiguration.
- Condition demo.greeting.enabled và @ConditionalOnMissingBean vẫn quyết định service cuối cùng.
- @AutoConfigureMockMvc thêm MockMvc để gọi endpoint mà không cần mở server thật.

Khác biệt quan trọng: slice test cần import auto-configuration riêng nếu slice không có nó; full application test tự nạp auto-configuration đã đăng ký trong AutoConfiguration.imports.

### 8.10. Chạy các test

Chạy tất cả:

~~~bash
mvn test
~~~

Chạy riêng từng nhóm:

~~~bash
mvn test -Dtest=GreetingAutoConfigurationTests
mvn test -Dtest=GreetingControllerSliceTests
mvn test -Dtest=GreetingApplicationIntegrationTests
~~~

Kết quả mong đợi:
- Auto-configuration tests: 3 test PASS.
- Controller slice: 1 test PASS.
- Full application test: 1 test PASS.

Đây là số test method được viết trong ví dụ; output log cụ thể của Maven/Surefire thay đổi theo phiên bản. Các test dùng context riêng phù hợp với mục đích và không gọi dịch vụ ngoài.

## 9. So sánh ba cách test trên cùng một auto-configuration

| Khía cạnh | ApplicationContextRunner | Test slice | @SpringBootTest |
| --- | --- | --- | --- |
| Mục tiêu | Kiểm tra logic auto-configuration | Kiểm tra một tầng ứng dụng cùng hạ tầng cần thiết | Kiểm tra tích hợp toàn ứng dụng |
| Phạm vi component scan | Không tự quét ứng dụng; test khai báo cấu hình cụ thể | Giới hạn theo slice | Theo cấu hình ứng dụng chính |
| Auto-configuration | Chỉ các class test đưa vào runner | Tập imported riêng của slice + phần bổ sung | Các candidate được ứng dụng bật và thỏa condition |
| Property | Dễ thêm bằng withPropertyValues | Dùng property của test annotation hoặc test property source | Dùng @SpringBootTest(properties=...), profile, file cấu hình |
| User bean override | Dễ tạo bằng withUserConfiguration | Dùng @Import, @MockitoBean hoặc test configuration | Có thể dùng bean thật hoặc mock có chủ đích |
| HTTP server | Không phải mục tiêu | Mock web infrastructure nếu là web slice | MOCK mặc định; RANDOM_PORT/DEFINED_PORT cho server thật |
| Tốc độ | Thường nhanh nhất | Trung bình | Thường nặng nhất |

Một chiến lược cân bằng thường là:
1. Unit test cho logic Java thuần.
2. ApplicationContextRunner cho auto-configuration contract.
3. Test slice cho từng tầng web/data/client.
4. Một số @SpringBootTest cho các luồng tích hợp quan trọng.

Không cần chuyển tất cả test sang full context. Full context thường chậm và có thể làm lỗi test khó định vị hơn.

## 10. Khi nào cần thêm auto-configuration, khi nào nên mock bean?

Giả sử controller cần GreetingService. Có hai mục tiêu test khác nhau:

**Test controller độc lập với service:**

~~~java
@WebMvcTest(GreetingController.class)
class GreetingControllerWithMockTests {

    @MockitoBean
    GreetingService greetingService;
}
~~~

Mock service giúp kiểm tra mapping, status, JSON và xử lý request mà không kiểm tra auto-configuration.

**Test controller cùng default service:**

~~~java
@WebMvcTest(GreetingController.class)
@ImportAutoConfiguration(GreetingAutoConfiguration.class)
class GreetingControllerWithDefaultServiceTests {
}
~~~

Cách này kiểm tra tương tác giữa controller và service được auto-configure.

**Test toàn bộ ứng dụng:**

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class GreetingFullApplicationTests {
}
~~~

Cách này kiểm tra controller cùng service, component scan và các auto-configuration khác của ứng dụng.

Chọn dựa vào câu hỏi mà test cần trả lời. Nếu test controller chỉ cần giả lập kết quả service, mock giúp test tập trung. Nếu mục tiêu là chứng minh auto-configuration cung cấp đúng bean để controller sử dụng, hãy nhập auto-configuration thật.

## 11. Tổ chức configuration để slice không kéo thừa bean

Một lớp @Configuration lớn có thể khai báo cả SecurityFilterChain, DataSource, client và MVC configurer. Nếu import cả lớp vào @WebMvcTest, mọi bean trong đó có thể được tạo, kể cả DataSource không cần cho web test.

Nên tách theo domain:

~~~text
config/
├── WebSecurityConfiguration.java
├── PersistenceConfiguration.java
├── ExternalClientConfiguration.java
└── JsonConfiguration.java
~~~

Sau đó mỗi slice import phần phù hợp:

~~~java
@WebMvcTest(GreetingController.class)
@Import(WebSecurityConfiguration.class)
class GreetingSecuritySliceTests {
}
~~~

Hoặc:

~~~java
@DataJpaTest
@Import(PersistenceTestConfiguration.class)
class RepositorySliceTests {
}
~~~

Đối với auto-configuration, dùng @ImportAutoConfiguration. Đối với cấu hình thông thường, dùng @Import. Nếu cấu hình chỉ dành cho test, có thể dùng nested @TestConfiguration; annotation này bổ sung cấu hình vào cấu hình chính của test.

Tài liệu Spring Boot khuyến nghị không đặt cấu hình chỉ dành cho một domain vào class @SpringBootApplication, vì class đó thường được dùng làm nguồn cấu hình cho các test. Chuyển domain-specific configuration sang lớp riêng giúp slice chỉ bật phần cần thiết.

## 12. Exclude auto-configuration khỏi một slice

Đôi khi slice mặc định nhập một auto-configuration không phù hợp. Có thể loại nó ra.

Ví dụ:

~~~java
@WebMvcTest(
        controllers = GreetingController.class,
        excludeAutoConfiguration = SomeUnwantedAutoConfiguration.class)
class GreetingControllerWithoutExtraConfigurationTests {
}
~~~

Hoặc dùng thuộc tính exclude của @ImportAutoConfiguration khi phù hợp:

~~~java
@ImportAutoConfiguration(
        exclude = SomeUnwantedAutoConfiguration.class)
~~~

Dùng exclude khi:
- Slice không cần một integration cụ thể;
- Một dependency test có mặt khiến auto-configuration match nhưng test không muốn bật;
- Muốn cô lập một tầng khỏi external infrastructure.

Trước khi exclude, kiểm tra condition report hoặc danh sách imported auto-configuration của đúng version. Đừng loại một cấu hình chỉ vì tên của nó có vẻ không liên quan; có thể một bean hạ tầng mà slice cần được tạo ở đó.

## 13. Chẩn đoán khi bean có trong full app nhưng không có trong slice

Làm theo trình tự:

1. **Xác định annotation test:** @WebMvcTest, @DataJpaTest, @RestClientTest hay @SpringBootTest.
2. **Xem slice import những auto-configuration nào:** tra appendix đúng Boot version.
3. **Xem component scan filter:** bean đang thiếu là @Component, @ConfigurationProperties, @Bean hay auto-configured bean?
4. **Nếu là component:** kiểm tra component type có thuộc slice scan không; cân nhắc @Import, @MockitoBean hoặc @EnableConfigurationProperties.
5. **Nếu là regular configuration:** import lớp cấu hình cần thiết bằng @Import; ưu tiên tách nhỏ config để không kéo bean thừa.
6. **Nếu là auto-configuration:** thêm bằng @ImportAutoConfiguration, hoặc đăng ký ở file slice imports nếu tất cả test của slice cần nó.
7. **Kiểm tra condition:** classpath, property, bean hiện có, context type, @ConditionalOnMissingBean và thứ tự auto-configuration.
8. **Nếu cần nhiều tầng cùng lúc:** chuyển sang @SpringBootTest thay vì cố ghép nhiều slice.
9. **Tạo test riêng cho auto-configuration:** dùng ApplicationContextRunner để xác nhận condition và bean registration độc lập.
10. **Chạy lại test:** xác nhận lỗi context đã được giải quyết và không kéo thêm dependency không cần thiết.

### 13.1. Condition Evaluation Report

Có thể chạy test/application với debug phù hợp hoặc kiểm tra ConditionEvaluationReport để hiểu auto-configuration nào match hoặc back off. Điều này hữu ích khi class đã được import nhưng bean vẫn không xuất hiện.

Cần phân biệt:
- Không được import vào slice;
- Đã import nhưng class-level condition không match;
- Class-level match nhưng method-level condition không match;
- Bean mặc định back off do user bean;
- Bean definition có nhưng instance tạo thất bại.

Mỗi trường hợp có nguyên nhân và cách sửa khác nhau.

## 14. Các lỗi thường gặp

| Lỗi | Vì sao xảy ra | Cách sửa |
| --- | --- | --- |
| Bean @Component có trong app nhưng không có trong @WebMvcTest | Slice không scan regular component | Dùng @MockitoBean hoặc @Import nếu cần bean thật |
| @ConfigurationProperties không được inject trong slice | Slice không scan properties bean thông thường | Dùng @EnableConfigurationProperties |
| Auto-configuration có trong full app nhưng không có trong slice | Slice chỉ nhập một tập auto-configuration hạn chế | Thêm bằng @ImportAutoConfiguration |
| Dùng @Import để nhập auto-configuration | Bỏ qua cách xử lý chuyên biệt của Boot | Dùng @ImportAutoConfiguration |
| Thêm cả @WebMvcTest và @DataJpaTest vào một class | Nhiều slice annotation không được hỗ trợ kết hợp | Chọn một slice hoặc dùng @SpringBootTest |
| Import một config lớn làm slice khởi động DB ngoài ý muốn | Config chứa nhiều bean không thuộc slice | Tách config theo domain và import phần cần |
| Full test không tìm thấy auto-configuration riêng | Chưa đăng ký trong AutoConfiguration.imports hoặc chưa được import | Kiểm tra imports resource và package/class name |
| Auto-configuration được nhập nhưng bean vẫn thiếu | Condition không match hoặc back off | Đọc condition message và user beans |
| @SpringBootTest chạy lâu hơn slice | Full context nạp nhiều component/auto-configuration | Dùng slice cho test tầng, giữ ít full integration test |
| server.port=0 được cho là mock web test | Port 0 vẫn khởi động server thật | Dùng WebEnvironment.MOCK nếu cần MockMvc không server |
| @ImportAutoConfiguration trên một test làm thay đổi nhiều test | Cấu hình bị đăng ký toàn cục qua slice imports file | Dùng import tại test class nếu chỉ một test cần |
| @TestConfiguration không được nạp | Chưa import hoặc khai báo sai phạm vi | Dùng nested test config hoặc @Import tường minh |

## 15. Ma trận lựa chọn test

| Mục tiêu | Cách test nên dùng | Lý do |
| --- | --- | --- |
| Kiểm tra @ConditionalOnProperty của auto-configuration | ApplicationContextRunner | Kiểm soát property và assert bean dễ dàng |
| Kiểm tra @ConditionalOnMissingBean | ApplicationContextRunner + user config | Xác nhận default back off khi có user bean |
| Kiểm tra controller mapping và JSON | @WebMvcTest | Chỉ nạp MVC layer và MockMvc |
| Controller cần default bean từ custom auto-config | @WebMvcTest + @ImportAutoConfiguration | Giữ slice nhưng thêm đúng auto-config cần |
| Kiểm tra repository và mapping JPA | @DataJpaTest | Có entity/repository, transaction và DB test |
| Kiểm tra REST client gọi service bên ngoài | @RestClientTest | Có builder và mock server |
| Kiểm tra serializer/deserializer | @JsonTest | Tập trung JSON mapper/tester |
| Kiểm tra controller → service → repository | @SpringBootTest | Cần nhiều tầng cùng tồn tại |
| Kiểm tra server thật, port, HTTP stack | @SpringBootTest(RANDOM_PORT) | Khởi động embedded server |
| Kiểm tra một auto-config trong full app | @SpringBootTest | Xác nhận nó được phát hiện trong application bootstrap |
| Kiểm tra nhiều auto-config phối hợp nhưng không cần toàn app | ApplicationContextRunner với nhiều class | Kiểm soát rõ danh sách cấu hình và điều kiện |

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao một auto-configuration có thể hoạt động trong @SpringBootTest nhưng không có trong @WebMvcTest?

**Đáp án:** @SpringBootTest dựng context từ cấu hình chính và áp dụng auto-configuration của ứng dụng. @WebMvcTest chỉ nhập một tập auto-configuration giới hạn phục vụ MVC. Nếu auto-configuration riêng không nằm trong tập đó, cần thêm nó bằng @ImportAutoConfiguration.

**Câu 2.** Dùng annotation nào để bổ sung auto-configuration vào một slice?

**Đáp án:** @ImportAutoConfiguration.

**Câu 3.** Khi nào dùng @Import?

**Đáp án:** Khi cần nhập một cấu hình thông thường, test support configuration hoặc component cụ thể; không dùng @Import thay cho @ImportAutoConfiguration đối với auto-configuration.

**Câu 4.** @WebMvcTest có scan tất cả @Component và @ConfigurationProperties không?

**Đáp án:** Không. Nó giới hạn scan theo các loại MVC component. Có thể dùng @EnableConfigurationProperties, @Import hoặc mock collaborator phù hợp.

**Câu 5.** Có thể kết hợp @WebMvcTest và @DataJpaTest trên cùng test class không?

**Đáp án:** Không. Spring Boot không hỗ trợ ghép nhiều slice annotation như vậy. Chọn một slice chính, bổ sung annotation @AutoConfigure... nếu cần, hoặc dùng @SpringBootTest.

**Câu 6.** @SpringBootTest mặc định có bật embedded server thật không?

**Đáp án:** Không. Mặc định là WebEnvironment.MOCK. Dùng RANDOM_PORT hoặc DEFINED_PORT để khởi động server thật.

**Câu 7.** Nên test custom auto-configuration bằng gì trước khi đưa vào full app?

**Đáp án:** ApplicationContextRunner để kiểm tra property, condition, default bean và user bean override độc lập.

## 17. Tài liệu tham khảo chính thức

- Spring Boot 3.5 — Testing Spring Boot Applications, test slices, full context, additional auto-configuration và @ImportAutoConfiguration: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — Test Slices appendix, danh sách auto-configuration được nhập theo từng slice: https://docs.spring.io/spring-boot/3.5/appendix/test-auto-configuration/slices.html
- Spring Boot 3.5 — Testing how-to, cấu trúc configuration cho slice tests: https://docs.spring.io/spring-boot/3.5/how-to/testing.html
- Spring Boot 3.5 API — ImportAutoConfiguration: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/ImportAutoConfiguration.html
- Spring Boot 3.5 API — SpringBootTest: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/SpringBootTest.html
- Spring Boot 3.5 API — WebMvcTest: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/WebMvcTest.html
- Spring Boot 3.5 Reference — Creating Your Own Auto-configuration, testing với ApplicationContextRunner: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html

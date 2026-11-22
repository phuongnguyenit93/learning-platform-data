# @ImportAutoConfiguration và phạm vi sử dụng có chủ đích

Spring Boot có thể tự động cấu hình nhiều thành phần dựa trên dependency, classpath và properties của ứng dụng. Cơ chế này rất tiện khi khởi động một ứng dụng hoàn chỉnh, nhưng trong một số tình huống ta chỉ muốn áp dụng **một tập auto-configuration cụ thể**. Ví dụ, một bài kiểm thử chỉ cần cấu hình Jackson để kiểm tra JSON; một test slice chỉ cần các thành phần MVC; hoặc một module muốn tạo annotation riêng để chia sẻ cấu hình kiểm thử giữa nhiều test.

Spring Boot cung cấp annotation **`@ImportAutoConfiguration`** cho mục đích đó. Annotation cho phép import có chủ đích các class auto-configuration, có thể chỉ định danh sách class và loại trừ những class không muốn áp dụng. Nó thường xuất hiện trong các test slice và các annotation kiểm thử tổng hợp.

Bài học giải thích `@ImportAutoConfiguration` làm gì, khác `@Import` và `@EnableAutoConfiguration` ra sao, cách khai báo danh sách class và exclusion, cách dùng trong test và custom annotation, cùng những giới hạn cần lưu ý khi thiết kế phạm vi cấu hình.

## 1. Vì sao cần import auto-configuration có chọn lọc?

Trong một ứng dụng Spring Boot hoàn chỉnh, `@SpringBootApplication` bao gồm `@EnableAutoConfiguration`. Boot xem xét các auto-configuration được công bố bởi dependency trên classpath, sau đó áp dụng những cấu hình phù hợp với điều kiện hiện tại.

Ví dụ, nếu ứng dụng có dependency web, Boot có thể cấu hình các thành phần liên quan đến web server và Spring MVC. Nếu có thư viện Jackson, Boot có thể cấu hình JSON serialization. Nếu có JDBC driver và datasource properties, Boot có thể cấu hình kết nối database.

Nhưng trong một bài kiểm thử nhỏ, ta có thể chỉ cần một phần của các cấu hình này:

- Test serializer chỉ cần Jackson.
- Test controller cần các thành phần MVC và HTTP message converter.
- Test repository cần cấu hình JPA và datasource phù hợp.
- Test một thư viện muốn kiểm tra riêng auto-configuration do thư viện cung cấp.

Nếu khởi động toàn bộ ứng dụng cho mọi bài test, context có thể nạp nhiều bean và dependency không liên quan. Điều đó làm test chậm hơn, tăng yêu cầu môi trường và khiến lỗi khó khoanh vùng.

`@ImportAutoConfiguration` giúp khai báo rõ những auto-configuration cần được áp dụng trong một context hoặc một cấu hình cụ thể.

## 2. @ImportAutoConfiguration là gì?

Annotation nằm trong package:

~~~java
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
~~~

Nó cho phép import và áp dụng các class auto-configuration được chỉ định.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportAutoConfiguration({
        JacksonAutoConfiguration.class,
        ValidationAutoConfiguration.class
})
public class ApiSupportConfiguration {
}
~~~

Trong ví dụ:

- `JacksonAutoConfiguration` cung cấp cấu hình liên quan đến Jackson khi các điều kiện cần thiết thỏa mãn.
- `ValidationAutoConfiguration` cung cấp cấu hình liên quan đến Bean Validation khi dependency tương ứng có mặt.
- Hai class vẫn phải thỏa các condition nội bộ của chúng; việc import không ép mọi bean bên trong được tạo bất kể điều kiện.

Một số điểm quan trọng:

- Có thể chỉ định class auto-configuration bằng thuộc tính `value` hoặc `classes`.
- Có thể dùng thuộc tính `exclude` để loại một số auto-configuration khỏi tập import.
- Annotation có thể đặt trên class cấu hình hoặc được dùng như meta-annotation trong annotation khác.
- Khi không chỉ định class tường minh, cơ chế import sử dụng danh sách candidate auto-configuration được Boot công bố qua metadata imports.
- Các điều kiện trên auto-configuration vẫn được đánh giá trong quá trình đăng ký bean.

`@ImportAutoConfiguration` không phải lệnh gọi method Java và cũng không trực tiếp tạo object. Nó đưa các cấu hình vào quá trình xử lý của Spring; các bean bên trong được đăng ký và khởi tạo theo cơ chế container.

## 3. Chỉ định auto-configuration bằng value hoặc classes

Có thể khai báo một class:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportAutoConfiguration(JacksonAutoConfiguration.class)
public class JsonSupportConfiguration {
}
~~~

Hoặc nhiều class:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportAutoConfiguration(classes = {
        JacksonAutoConfiguration.class,
        ValidationAutoConfiguration.class
})
public class ApiSupportConfiguration {
}
~~~

Hai thuộc tính `value` và `classes` là hai cách biểu đạt danh sách class import. Thường chỉ cần dùng một trong hai để code dễ đọc.

Ví dụ rút gọn với `value`:

~~~java
@ImportAutoConfiguration({
        JacksonAutoConfiguration.class,
        ValidationAutoConfiguration.class
})
~~~

Ví dụ tường minh với `classes`:

~~~java
@ImportAutoConfiguration(classes = {
        JacksonAutoConfiguration.class,
        ValidationAutoConfiguration.class
})
~~~

Khi có nhiều cấu hình, hãy chỉ import những auto-configuration liên quan đến mục tiêu của context. Việc import một class không có nghĩa tất cả dependency của nó tự xuất hiện; điều kiện classpath, bean và property vẫn có thể khiến một phần cấu hình được bỏ qua.

### 3.1. Import class auto-configuration đúng loại

`@ImportAutoConfiguration` được thiết kế cho auto-configuration của Spring Boot, ví dụ các class được đánh dấu `@AutoConfiguration` hoặc các auto-configuration được Boot cung cấp.

Ví dụ:

~~~java
import org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration;
~~~

Không nên dùng annotation này như một cách thay thế chung cho `@Import` để đưa mọi class bất kỳ vào context. Nếu bạn có một class cấu hình ứng dụng thông thường, dùng `@Import` thường diễn đạt đúng ý định hơn.

## 4. Loại trừ auto-configuration bằng exclude

Đôi khi muốn import một nhóm cấu hình nhưng bỏ qua một cấu hình cụ thể.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportAutoConfiguration(
        classes = {
                JacksonAutoConfiguration.class,
                ValidationAutoConfiguration.class
        },
        exclude = {
                ValidationAutoConfiguration.class
        }
)
public class JsonOnlyConfiguration {
}
~~~

Trong trường hợp này, `ValidationAutoConfiguration` bị loại khỏi tập import; cấu hình Jackson vẫn được xem xét.

Thuộc tính `exclude` nhận các class. Nó hữu ích khi một nhóm cấu hình được chia sẻ nhưng một test hoặc module cụ thể cần loại một phần.

Không nên dùng exclusion chỉ để làm context khởi động bằng mọi giá. Nếu auto-configuration bị loại là dependency thực sự của bean đang kiểm thử, context có thể thiếu bean hoặc không còn mô phỏng đúng môi trường mà bạn muốn xác nhận.

### 4.1. Phân biệt exclusion ở annotation với exclusion toàn ứng dụng

`@ImportAutoConfiguration(exclude = ...)` điều khiển tập auto-configuration được import qua annotation đó.

Trong ứng dụng Spring Boot đầy đủ, `@EnableAutoConfiguration` còn có cơ chế loại trừ ở phạm vi ứng dụng, chẳng hạn thuộc tính `exclude`/`excludeName` hoặc property `spring.autoconfigure.exclude`. Đây là các cơ chế có phạm vi và mục đích khác nhau.

Đừng nhầm một exclusion cục bộ trong test configuration với việc tắt auto-configuration đó trên toàn bộ ứng dụng production.

## 5. Khác nhau giữa @ImportAutoConfiguration, @Import và @EnableAutoConfiguration

Ba annotation có liên quan đến việc đưa cấu hình vào context nhưng biểu đạt ý định khác nhau.

### 5.1. @Import: đưa class cấu hình hoặc component cụ thể vào context

`@Import` là annotation của Spring Framework:

~~~java
import org.springframework.context.annotation.Import;
~~~

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
@Import({
        LocalCacheConfiguration.class,
        AuditConfiguration.class
})
public class ApplicationModuleConfiguration {
}
~~~

Nó import những class cụ thể được chỉ định, thường là class cấu hình hoặc component do ứng dụng kiểm soát.

Dùng `@Import` khi bạn muốn kết nối các cấu hình ứng dụng với nhau một cách tường minh.

### 5.2. @EnableAutoConfiguration: bật cơ chế auto-configuration của Boot

`@EnableAutoConfiguration` cho phép Spring Boot tìm và xem xét tập auto-configuration được công bố trên classpath.

~~~java
@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

`@SpringBootApplication` đã bao gồm `@EnableAutoConfiguration` cùng component scan và `@SpringBootConfiguration`.

Cơ chế này phù hợp khi khởi động ứng dụng Spring Boot và muốn Boot tự quyết định các cấu hình phù hợp dựa trên classpath, properties và bean hiện có.

### 5.3. @ImportAutoConfiguration: import auto-configuration có chọn lọc

~~~java
@Configuration(proxyBeanMethods = false)
@ImportAutoConfiguration(JacksonAutoConfiguration.class)
public class JsonTestConfiguration {
}
~~~

Annotation này phù hợp khi một context chỉ cần một tập auto-configuration được chọn. Nó thường được dùng trong test slice, test configuration hoặc annotation tổng hợp.

### 5.4. Bảng so sánh

| Annotation | Nguồn | Mục đích chính |
| --- | --- | --- |
| `@Import` | Spring Framework | Import class cấu hình/component cụ thể |
| `@EnableAutoConfiguration` | Spring Boot | Bật cơ chế tìm và áp dụng auto-configuration của Boot |
| `@ImportAutoConfiguration` | Spring Boot | Import một tập auto-configuration có chủ đích |

Một cách ghi nhớ:

- Cần import một class cấu hình của ứng dụng: dùng `@Import`.
- Cần bật hệ thống auto-configuration tổng thể của Boot: dùng `@EnableAutoConfiguration` hoặc `@SpringBootApplication`.
- Cần một tập auto-configuration cụ thể cho context hoặc test: dùng `@ImportAutoConfiguration`.

## 6. Auto-configuration vẫn chịu các condition

Import một auto-configuration không có nghĩa mọi bean của nó chắc chắn xuất hiện.

Ví dụ, auto-configuration có thể chứa:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
public class ExampleJsonAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    ExampleJsonService exampleJsonService() {
        return new ExampleJsonService();
    }
}
~~~

Nếu class cần thiết không có trên classpath, cấu hình có thể không khớp. Nếu ứng dụng đã cung cấp bean phù hợp, bean mặc định có thể nhường chỗ.

Các condition thường gặp gồm:

- `@ConditionalOnClass` và `@ConditionalOnMissingClass`.
- `@ConditionalOnProperty`.
- `@ConditionalOnBean` và `@ConditionalOnMissingBean`.
- `@ConditionalOnResource`.
- Condition tùy chỉnh triển khai từ `Condition`.

`@ImportAutoConfiguration` chọn cấu hình nào được đưa vào quá trình xử lý. Các condition bên trong tiếp tục quyết định bean nào thực sự được đăng ký.

Đây là lý do test cần cung cấp classpath, properties và bean dependency phù hợp với tình huống muốn kiểm tra.
## 7. Khi không chỉ định class: metadata auto-configuration imports

Spring Boot có cơ chế công bố danh sách auto-configuration trong metadata. Với Spring Boot 2.7 trở lên, định dạng imports tiêu chuẩn là:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Một thư viện auto-configuration có thể khai báo:

~~~text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
com.example.audit.autoconfigure.AuditAutoConfiguration
~~~

Boot dùng metadata này để tìm các candidate auto-configuration.

`@ImportAutoConfiguration` có thể sử dụng cơ chế candidate discovery này khi không cung cấp danh sách class tường minh. Điều đó hữu ích khi xây dựng một annotation tổng hợp hoặc test context muốn dùng danh sách auto-configuration được công bố bởi module.

Tuy nhiên, khi mục tiêu là import một tập nhỏ và ổn định, khai báo class rõ ràng thường dễ đọc và dễ kiểm soát hơn.

### 7.1. File imports không phải file cấu hình properties

`AutoConfiguration.imports` là danh sách tên class, mỗi dòng là một class auto-configuration. Nó không chứa key/value như `application.properties`.

Ví dụ:

~~~text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
~~~

Không viết:

~~~properties
greeting.enabled=true
~~~

Property bật tính năng thuộc file cấu hình ứng dụng; metadata imports chỉ công bố class auto-configuration.

### 7.2. Metadata imports và khả năng tương thích phiên bản

Spring Boot trước 2.7 thường sử dụng key `EnableAutoConfiguration` trong `META-INF/spring.factories` để công bố auto-configuration. Từ Boot 2.7, định dạng `AutoConfiguration.imports` được hỗ trợ và là cách tiêu chuẩn cho các dòng Boot hiện đại.

Khi phát triển starter hỗ trợ nhiều dòng Boot, hãy xem tài liệu migration và quy tắc đóng gói tương ứng. Không nên sao chép metadata của một phiên bản mới vào một starter cũ mà chưa xác định cơ chế discovery của phiên bản đó.

## 8. Dùng @ImportAutoConfiguration trong kiểm thử

Một trong những mục đích phổ biến nhất của annotation là đưa đúng auto-configuration vào test context.

Ví dụ test cần Jackson để kiểm tra JSON serialization, nhưng không cần khởi động web server hay database.

Cấu hình test:

~~~java
import org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration;
import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ImportAutoConfiguration(JacksonAutoConfiguration.class)
class JsonTestConfiguration {
}
~~~

Test:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;

@SpringJUnitConfig(JsonTestConfiguration.class)
class JsonSerializationTest {

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void serializesAnObjectAsJson() throws Exception {
        String json = objectMapper.writeValueAsString(
                new Message("hello")
        );

        assertThat(json).contains("hello");
    }

    record Message(String value) {
    }
}
~~~

Test context được khởi tạo từ `JsonTestConfiguration`. Cấu hình đó import `JacksonAutoConfiguration`; các condition và dependency liên quan vẫn được xử lý.

Đoạn test cần các dependency test của Spring và JUnit, cùng Jackson. Với dự án Spring Boot, `spring-boot-starter-test` thường cung cấp phần lớn test infrastructure; dependency web hoặc JSON tương ứng cần có để auto-configuration Jackson được hỗ trợ.

### 8.1. Vì sao không dùng @SpringBootTest cho mọi test?

`@SpringBootTest` thường khởi tạo context dựa trên cấu hình ứng dụng chính và có thể áp dụng một phạm vi cấu hình rộng hơn.

Nếu mục tiêu chỉ là kiểm tra Jackson auto-configuration, một context nhỏ với `@ImportAutoConfiguration` giúp test tập trung hơn và ít phụ thuộc vào database, server hoặc các integration khác.

Dù vậy, test slice không thay thế integration test toàn ứng dụng. Hãy chọn loại test theo hành vi cần xác nhận.

## 9. Dùng trong custom test annotation

Có thể tạo annotation tổng hợp để nhiều test dùng chung một tập auto-configuration.

Ví dụ, thư viện muốn mọi test JSON có Jackson support:

~~~java
package com.example.testing;

import org.springframework.boot.autoconfigure.ImportAutoConfiguration;
import org.springframework.boot.autoconfigure.jackson.JacksonAutoConfiguration;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Inherited
@ImportAutoConfiguration(JacksonAutoConfiguration.class)
public @interface JsonSupportTest {
}
~~~

Test có thể sử dụng:

~~~java
@JsonSupportTest
@SpringJUnitConfig
class InvoiceJsonTest {
    // Test có thể inject ObjectMapper từ auto-configuration đã import.
}
~~~

Đây là ví dụ về meta-annotation. Trong dự án thực tế, annotation tổng hợp thường cần kết hợp với annotation bootstrap/context phù hợp của Spring Test để xác định cấu hình test. `@ImportAutoConfiguration` cung cấp phần import; nó không tự thay thế toàn bộ test context bootstrap.

### 9.1. Lợi ích của annotation tổng hợp

- Giảm lặp lại danh sách auto-configuration trong nhiều test.
- Thể hiện rõ loại hạ tầng mà test cần.
- Có thể thay đổi tập cấu hình dùng chung tại một nơi.
- Giúp nhóm test dùng cùng một convention.

Không nên tạo một annotation tổng hợp chứa quá nhiều auto-configuration không liên quan. Khi phạm vi quá rộng, test lại trở nên khó hiểu và khó cô lập.

## 10. Vai trò của @ImportAutoConfiguration trong test slices

Spring Boot cung cấp nhiều test slice, ví dụ:

- `@WebMvcTest` tập trung vào Spring MVC và các thành phần web liên quan.
- `@DataJpaTest` tập trung vào JPA và persistence.
- `@JsonTest` tập trung vào JSON mapping.
- `@RestClientTest` tập trung vào kiểm thử client HTTP.
- `@JdbcTest` tập trung vào JDBC.

Các test slice này thường dùng một tập annotation và cơ chế import để đưa vào context những auto-configuration phù hợp với loại test. `@ImportAutoConfiguration` là một trong các cơ chế Boot sử dụng cho mục tiêu đó.

Ví dụ, test MVC:

~~~java
@WebMvcTest(InvoiceController.class)
class InvoiceControllerTest {
    // Chỉ tập trung vào MVC slice.
}
~~~

Nếu controller cần một service nghiệp vụ, test có thể cung cấp mock bean:

~~~java
@WebMvcTest(InvoiceController.class)
class InvoiceControllerTest {

    @MockitoBean
    InvoiceService invoiceService;
}
~~~

Tên annotation mock bean có thể khác tùy phiên bản Spring Framework/Boot và bộ test đang dùng; ở các dự án Boot cũ thường gặp `@MockBean`, trong các dòng mới có `@MockitoBean` từ Spring Framework Test.

Nếu cần thêm auto-configuration cụ thể vào slice:

~~~java
@WebMvcTest(InvoiceController.class)
@ImportAutoConfiguration(CustomJsonAutoConfiguration.class)
class InvoiceControllerJsonTest {
}
~~~

Chỉ thêm cấu hình cần thiết. Import thêm một auto-configuration có thể đưa vào dependency và bean không thuộc phạm vi test slice ban đầu.

## 11. Phân biệt với @EnableAutoConfiguration và các exclusion toàn cục trong test

Một test dùng `@ImportAutoConfiguration` thường muốn chỉ định rõ tập cấu hình bổ sung cho context. Điều này khác với việc bật toàn bộ auto-configuration của ứng dụng.

Ví dụ:

~~~java
@SpringBootTest
class FullApplicationIntegrationTest {
}
~~~

Test này thường khởi động application context theo cấu hình ứng dụng đầy đủ.

Trong khi:

~~~java
@SpringJUnitConfig(JsonTestConfiguration.class)
class JsonSerializationTest {
}
~~~

với `JsonTestConfiguration` chỉ import Jackson auto-configuration, context được xây dựng tập trung cho mục tiêu JSON.

Không nên thêm `@EnableAutoConfiguration` vào một test nhỏ chỉ để có một bean tiện dụng, nếu có thể import đúng auto-configuration cần thiết hoặc tạo cấu hình test đơn giản.

Ngược lại, nếu đang kiểm tra tương tác giữa nhiều auto-configuration của ứng dụng trong điều kiện thật, một integration test đầy đủ vẫn cần thiết.

## 12. Ordering và các condition khi import nhiều auto-configuration

Auto-configuration có thể khai báo quan hệ thứ tự:

~~~java
@AutoConfiguration(before = CacheAutoConfiguration.class)
public class CustomCacheSupportAutoConfiguration {
    // ...
}
~~~

Hoặc:

~~~java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
public class JdbcAuditAutoConfiguration {
    // ...
}
~~~

Khi import nhiều auto-configuration, thứ tự khai báo trong một mảng không nên được dùng như cơ chế điều phối phụ thuộc. Auto-configuration có thể khai báo ordering metadata và Boot xử lý theo cơ chế sắp xếp auto-configuration.

Nếu cấu hình cần bean từ một auto-configuration khác:

- Xác định bean dependency thực sự.
- Dùng parameter injection hoặc constructor injection.
- Khai báo ordering metadata khi condition cần được đánh giá sau cấu hình cung cấp bean.
- Kiểm thử context với đúng tập cấu hình.

Đừng dựa vào thứ tự khởi tạo singleton để giải quyết vấn đề ordering. Ordering của auto-configuration và dependency graph là hai khái niệm liên quan nhưng khác nhau.

## 13. Import auto-configuration của thư viện do ứng dụng phát triển

Giả sử bạn có một starter nội bộ cung cấp:

~~~java
@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService() {
        return new DefaultGreetingService();
    }
}
~~~

Một test của module starter có thể import trực tiếp:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportAutoConfiguration(GreetingAutoConfiguration.class)
class GreetingStarterTestConfiguration {
}
~~~

Sau đó test xác nhận bean mặc định được đăng ký nếu không có custom bean.

Một test khác có thể cung cấp bean riêng:

~~~java
@Configuration(proxyBeanMethods = false)
class CustomGreetingTestConfiguration {

    @Bean
    GreetingService customGreetingService() {
        return new TestGreetingService();
    }
}
~~~

Test context kết hợp hai cấu hình:

~~~java
@SpringJUnitConfig({
        GreetingStarterTestConfiguration.class,
        CustomGreetingTestConfiguration.class
})
class GreetingBackOffTest {
    // Kiểm tra auto-configuration nhường chỗ cho bean test.
}
~~~

Trong một auto-configuration thực tế, cần bảo đảm thứ tự và cách đăng ký user configuration phù hợp để condition nhìn thấy bean test. Với auto-configuration Boot, có thể dùng `ApplicationContextRunner` để kiểm tra rõ ràng hai nhánh.

## 14. Kiểm thử auto-configuration bằng ApplicationContextRunner

`ApplicationContextRunner` thường là công cụ phù hợp để test auto-configuration của thư viện. Nó cho phép dựng một context nhỏ, thêm auto-configuration, user configuration và properties rồi kiểm tra kết quả.

Ví dụ:

~~~java
class GreetingAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    GreetingAutoConfiguration.class
                            )
                    );

    @Test
    void registersDefaultWhenNoUserBeanExists() {
        contextRunner.run(context -> {
            assertThat(context).hasSingleBean(GreetingService.class);
            assertThat(context.getBean(GreetingService.class))
                    .isInstanceOf(DefaultGreetingService.class);
        });
    }

    @Test
    void usesUserBeanWhenProvided() {
        contextRunner
                .withUserConfiguration(CustomGreetingTestConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(GreetingService.class);
                    assertThat(context.getBean(GreetingService.class))
                            .isInstanceOf(TestGreetingService.class);
                });
    }
}
~~~

Ví dụ cần các import:

~~~java
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
~~~

Các implementation `GreetingService`, `DefaultGreetingService`, `TestGreetingService` và cấu hình custom là những class trong test project.

### 14.1. Vì sao test cả hai nhánh?

Một auto-configuration có thể hoạt động đúng khi không có custom bean nhưng lại không nhường chỗ khi ứng dụng cung cấp implementation riêng.

Test hai nhánh xác nhận:

- Default được đăng ký khi thiếu bean.
- Default back off khi có bean người dùng.
- Consumer có thể inject contract đúng.
- Số lượng bean không bị tăng ngoài ý muốn.

### 14.2. Dùng context runner để kiểm tra property và classpath

`ApplicationContextRunner` còn cho phép thêm property:

~~~java
contextRunner
        .withPropertyValues("greeting.enabled=true")
        .run(context -> {
            // Kiểm tra cấu hình theo property.
        });
~~~

Có thể kết hợp với `FilteredClassLoader` hoặc các helper phù hợp để kiểm tra condition classpath. Điều này đặc biệt hữu ích khi auto-configuration có nhiều condition.
## 15. Những lỗi thường gặp

### 15.1. Import nhầm class cấu hình thông thường

**Triệu chứng:** Dùng `@ImportAutoConfiguration` cho một class cấu hình ứng dụng không phải auto-configuration và kết quả không như mong đợi.

**Nguyên nhân:** Annotation này được thiết kế cho cơ chế import auto-configuration của Boot. `@Import` là lựa chọn tự nhiên hơn cho class cấu hình thông thường.

**Cách xử lý:** Xác định class cần import thuộc loại nào. Nếu đó là cấu hình module do ứng dụng kiểm soát, dùng `@Import`; nếu là auto-configuration của Boot/starter, dùng `@ImportAutoConfiguration`.

### 15.2. Import class nhưng bean không xuất hiện

**Triệu chứng:** Auto-configuration được chỉ định nhưng bean cần thiết không có trong context.

**Nguyên nhân có thể:**

- `@ConditionalOnClass` không khớp vì thiếu dependency.
- `@ConditionalOnProperty` không khớp.
- `@ConditionalOnMissingBean` nhường chỗ cho bean khác.
- Một condition khác không thỏa mãn.
- Bean được đăng ký dưới kiểu khác hoặc bị loại bởi exclusion.

**Cách xử lý:** Kiểm tra condition evaluation report, classpath và properties của context. Import class không bỏ qua condition.

### 15.3. Import quá nhiều auto-configuration

**Triệu chứng:** Test context kéo theo database, web server hoặc nhiều bean không liên quan.

**Nguyên nhân:** Tập auto-configuration được import quá rộng hoặc annotation tổng hợp chứa nhiều cấu hình.

**Cách xử lý:** Chỉ import các class phục vụ mục tiêu test. Nếu mục tiêu là kiểm thử ứng dụng đầy đủ, dùng integration test rõ ràng thay vì cố biến một test nhỏ thành context toàn ứng dụng.

### 15.4. Exclude nhầm phạm vi

**Triệu chứng:** Một auto-configuration vẫn hoạt động ở ứng dụng thật dù đã loại khỏi một test.

**Nguyên nhân:** Exclusion đặt trên `@ImportAutoConfiguration` chỉ liên quan đến tập import của annotation đó; ứng dụng có thể còn một cơ chế import auto-configuration khác.

**Cách xử lý:** Xác định test context đang được tạo từ đâu và auto-configuration nào được import qua `@EnableAutoConfiguration` hoặc test slice. Nếu muốn loại ở phạm vi ứng dụng, dùng exclusion phù hợp của `@EnableAutoConfiguration` hoặc property tương ứng.

### 15.5. Nghĩ rằng annotation tự tạo test context

`@ImportAutoConfiguration` chỉ tham gia import cấu hình. Nó không tự cung cấp JUnit extension, test bootstrap hoặc toàn bộ context infrastructure.

Kết hợp với `@SpringJUnitConfig`, `@ContextConfiguration`, test slice hoặc một test bootstrap phù hợp.

### 15.6. Quên dependency của auto-configuration

Import `JacksonAutoConfiguration` không tự thêm thư viện Jackson vào build. Nếu class cần thiết không có trên classpath, condition có thể không khớp hoặc cấu hình không cung cấp bean như dự kiến.

Thêm dependency phù hợp và kiểm tra điều kiện trước khi kết luận annotation không hoạt động.

### 15.7. Dựa vào thứ tự mảng class để giải quyết dependency

Danh sách class trong annotation không nên được xem như một chuỗi lệnh tạo bean tuần tự. Auto-configuration có ordering metadata và dependency graph riêng.

Dùng dependency injection, ordering metadata và test context để mô tả quan hệ đúng.

## 16. Quy trình chọn phạm vi import

Khi cần đưa auto-configuration vào một context, hãy đi theo các bước:

1. **Xác định mục tiêu:** đang kiểm thử JSON, MVC, persistence hay một starter cụ thể?
2. **Xác định class auto-configuration:** tìm đúng class Boot/starter cung cấp bean cần dùng.
3. **Chọn cơ chế import:** dùng `@ImportAutoConfiguration` cho auto-configuration; dùng `@Import` cho cấu hình ứng dụng thông thường.
4. **Giữ danh sách hẹp:** chỉ import các cấu hình có liên quan.
5. **Kiểm tra condition:** bảo đảm dependency, properties và bean prerequisites phù hợp.
6. **Dùng exclude có chủ đích:** loại đúng cấu hình không cần thiết và hiểu phạm vi exclusion.
7. **Kiểm thử context:** xác nhận bean được đăng ký, bean bị bỏ qua và dependency được giải quyết đúng.
8. **Kiểm tra phạm vi test:** bảo đảm test slice vẫn tập trung vào hành vi cần kiểm tra.

Nếu test đang cần toàn bộ application context, hãy dùng một integration test tương ứng. Đừng import thủ công một danh sách dài auto-configuration để mô phỏng một ứng dụng đầy đủ nếu `@SpringBootTest` đã thể hiện ý định đó rõ hơn.

## 17. Bài thực hành

### Bài A: Import riêng Jackson

Tạo một class cấu hình test:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportAutoConfiguration(JacksonAutoConfiguration.class)
class JsonOnlyConfiguration {
}
~~~

Tạo test context, inject `ObjectMapper` và serialize một record đơn giản.

Xác nhận test không cần khởi động web server.

### Bài B: Import hai auto-configuration và loại một class

Import Jackson và Validation, sau đó dùng `exclude` để loại Validation.

Quan sát bean liên quan đến Jackson vẫn có thể xuất hiện khi điều kiện phù hợp, trong khi cấu hình Validation không được import từ annotation đó.

### Bài C: So sánh @Import và @ImportAutoConfiguration

Tạo một class cấu hình ứng dụng đơn giản có `@Bean`. Import nó bằng `@Import`.

Sau đó import một auto-configuration của Boot bằng `@ImportAutoConfiguration`. Ghi lại sự khác biệt về ý nghĩa, điều kiện và mục đích sử dụng.

### Bài D: Tạo custom test annotation

Tạo annotation `@JsonSupportTest` có meta-annotation `@ImportAutoConfiguration(JacksonAutoConfiguration.class)`.

Dùng annotation này trên hai test class và xác nhận cả hai có thể inject `ObjectMapper`.

### Bài E: Kiểm tra condition

Import một auto-configuration có `@ConditionalOnProperty`. Chạy test với property thiếu, false và true.

Xác nhận import class không làm condition tự động khớp.

### Bài F: Kiểm thử starter của riêng bạn

Tạo auto-configuration đăng ký `GreetingService` mặc định bằng `@ConditionalOnMissingBean`.

Dùng `ApplicationContextRunner` để kiểm tra trường hợp có và không có bean tùy biến. Sau đó dùng `@ImportAutoConfiguration` trong một test context nhỏ để import riêng auto-configuration đó.

## 18. Câu hỏi tự kiểm tra

**1. `@ImportAutoConfiguration` thuộc package nào?**

`org.springframework.boot.autoconfigure`.

**2. Annotation này dùng để làm gì?**

Import và áp dụng một tập auto-configuration có chủ đích cho một cấu hình hoặc context.

**3. `@ImportAutoConfiguration` khác `@Import` thế nào?**

`@Import` thường đưa class cấu hình/component cụ thể vào context; `@ImportAutoConfiguration` dành cho auto-configuration của Spring Boot và cơ chế import tương ứng.

**4. `@ImportAutoConfiguration` khác `@EnableAutoConfiguration` thế nào?**

`@EnableAutoConfiguration` bật cơ chế tìm và áp dụng auto-configuration cho ứng dụng; `@ImportAutoConfiguration` cho phép import một tập auto-configuration được chọn.

**5. Import một auto-configuration có bảo đảm mọi bean bên trong được tạo không?**

Không. Các condition, dependency và quy tắc đăng ký bean vẫn được áp dụng.

**6. Có thể loại một auto-configuration khỏi tập import không?**

Có. Dùng thuộc tính `exclude` của `@ImportAutoConfiguration`.

**7. Annotation có tự khởi động JUnit test context không?**

Không. Nó tham gia import cấu hình; cần kết hợp với test bootstrap hoặc annotation của Spring Test.

**8. Khi nào nên dùng annotation tổng hợp?**

Khi nhiều test hoặc module cần cùng một tập auto-configuration và muốn chia sẻ convention rõ ràng.

**9. Có nên import mọi auto-configuration vào một unit test không?**

Không. Unit test nên kiểm tra logic class độc lập; integration hoặc slice test mới cần context và các auto-configuration liên quan.

## 19. Kết luận

`@ImportAutoConfiguration` giúp kiểm soát **phạm vi auto-configuration được đưa vào một context**. Nó đặc biệt hữu ích trong test slice, test cấu hình starter và các annotation tổng hợp cần chia sẻ một tập auto-configuration cụ thể.

Hãy dùng `value` hoặc `classes` để chỉ định class cần import, `exclude` để loại cấu hình không cần thiết và nhớ rằng các condition bên trong auto-configuration vẫn được đánh giá. Phân biệt rõ `@Import`, `@EnableAutoConfiguration` và `@ImportAutoConfiguration` để chọn đúng cơ chế theo mục tiêu.

Một test tốt chỉ đưa vào những cấu hình cần thiết cho hành vi đang kiểm tra. Khi phạm vi import được chọn có chủ đích, context gọn hơn, test dễ đọc hơn và lỗi cấu hình cũng dễ khoanh vùng hơn.




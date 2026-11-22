# Phân biệt cấu hình Spring Framework và tự cấu hình của Spring Boot

## 1. Hai khái niệm giải quyết hai bài toán khác nhau

**Cấu hình Spring Framework** mô tả các bean, phụ thuộc, component scan và thành phần hạ tầng mà ứng dụng muốn dùng. Spring IoC container tạo, kết nối, quản lý vòng đời của những bean đó. Spring Framework cung cấp các API như `@Configuration`, `@Bean`, `@Component`, `@Import`, `@Profile`, `Environment`, `ApplicationContext` và các cơ chế mở rộng.

**Tự cấu hình Spring Boot (auto-configuration)** sử dụng các điều kiện và thông tin trên classpath, môi trường, thuộc tính cấu hình và bean đã tồn tại để tự đăng ký những bean hạ tầng thường cần trong ứng dụng. Boot được xây dựng trên cùng Spring container: auto-configuration cuối cùng vẫn tạo ra bean definitions và bean thông thường. Nó không thay thế `ApplicationContext`, IoC, dependency injection hoặc cấu hình Spring.

Ví dụ: trong Spring Framework thuần, người phát triển có thể phải đăng ký rõ web infrastructure, cấu hình servlet, data binding, validator, converter và các bean cụ thể. Với ứng dụng Spring Boot MVC, dependency phù hợp và mặc định của Boot thường cung cấp sẵn hạ tầng MVC để có thể tập trung vào controller, service và cấu hình ứng dụng.

| Khía cạnh | Spring Framework | Spring Boot auto-configuration |
| --- | --- | --- |
| Bản chất | Hạ tầng IoC và các API để tác giả ứng dụng cấu hình bean | Bộ cấu hình có điều kiện chạy trên hạ tầng Spring |
| Nơi xác định bean | `@Bean`, `@ComponentScan`, XML, API đăng ký bean | Các lớp auto-configuration và cấu hình do Boot nhập vào |
| Điều kiện hoạt động | Theo định nghĩa và cấu hình được ứng dụng cung cấp | Classpath, bean đã có/chưa có, property, web application type và điều kiện khác |
| Tùy chỉnh | Tự định nghĩa bean và các extension point | Thuộc tính Boot, bean tùy chỉnh, các extension point hoặc loại trừ auto-config cụ thể |
| Khi thiếu dependency | Cấu hình có thể không biên dịch hoặc không khởi động | Auto-config có thể không được áp dụng do điều kiện không thỏa |
| Đối tượng sử dụng | Mọi ứng dụng Spring, kể cả không dùng Boot | Ứng dụng có cơ chế auto-configuration của Spring Boot |

Chỉ thêm một thư viện Spring vào classpath không có nghĩa Spring Framework sẽ tự đăng ký mọi bean mà ứng dụng cần. Ngược lại, Boot cũng không tự cấu hình mọi thư viện bất kỳ: phải có auto-configuration tương ứng và các điều kiện của nó phải phù hợp.

## 2. Cấu hình Spring Framework hoạt động thế nào?

### 2.1. Khai báo bean bằng Java configuration

```java
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class ManualSpringConfigDemo {
    interface ClockLabel { String text(); }

    static class FixedClockLabel implements ClockLabel {
        @Override public String text() { return "10:30"; }
    }

    static class GreetingService {
        private final ClockLabel clock;
        GreetingService(ClockLabel clock) { this.clock = clock; }
        String greet() { return "Hello at " + clock.text(); }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {
        @Bean ClockLabel clockLabel() { return new FixedClockLabel(); }
        @Bean GreetingService greetingService(ClockLabel clockLabel) {
            return new GreetingService(clockLabel);
        }
    }

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {
            System.out.println(context.getBean(GreetingService.class).greet());
        }
    }
}
```

Kết quả với Spring Context và các dependency của nó có trên classpath:

```text
Hello at 10:30
```

`AppConfig` là cấu hình do ứng dụng viết; container xử lý `@Bean` và tiêm `ClockLabel` vào `GreetingService`. Không có Spring Boot và cũng không cần HTTP server. Đây là chương trình Java 17+ có `main`, nhưng lệnh `javac ManualSpringConfigDemo.java` thuần túy cần classpath chứa Spring. Trong dự án Gradle/Maven, nên dùng cơ chế build và runtime classpath của dự án.

### 2.2. Component scan và cấu hình theo môi trường

`@Component`, `@Service`, `@Repository` và `@Controller` đánh dấu các lớp có thể được khám phá qua component scan. Việc đánh dấu **không bảo đảm bean tồn tại**: phạm vi scan, cấu hình context, các điều kiện và lỗi khởi tạo quyết định kết quả. `@Profile("dev")` có thể giới hạn bean theo profile đang hoạt động; `@Conditional` hoặc các cơ chế cấu hình khác có thể kiểm soát đăng ký bean.

`Environment` và property sources có trong Spring Framework; Boot mở rộng việc nạp, binding và tổ chức cấu hình tiện lợi qua `application.properties`/`application.yml`, profiles và `@ConfigurationProperties`. Không nên nhầm cơ chế đọc property của Spring với quy tắc property-specific của từng auto-configuration trong Boot.

## 3. Spring Boot bật auto-configuration ra sao?

Trong ứng dụng Boot thông thường:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`@SpringBootApplication` kết hợp các vai trò chính của `@SpringBootConfiguration`, `@EnableAutoConfiguration` và `@ComponentScan`. `SpringApplication.run` chuẩn bị môi trường và tạo/refresh application context. Boot nhập các auto-configuration có sẵn trong dependency của phiên bản Boot đang sử dụng.

Ở Spring Boot 3.x, auto-configuration thường được công bố qua file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` trong JAR liên quan. Đây là danh sách lớp để Boot xem xét; mỗi lớp vẫn có thể bị bỏ qua nếu điều kiện không thỏa. Tránh coi cơ chế đăng ký này là một quy tắc cố định cho mọi thế hệ Boot.

Những annotation điều kiện thường thấy:

- `@ConditionalOnClass`: cấu hình chỉ phù hợp khi có class được yêu cầu trên classpath.
- `@ConditionalOnMissingBean`: đăng ký một bean mặc định khi chưa có bean phù hợp, theo điều kiện định nghĩa.
- `@ConditionalOnBean`: chỉ áp dụng khi đã có bean cần thiết.
- `@ConditionalOnProperty`: dựa trên property và giá trị được cấu hình.
- `@ConditionalOnWebApplication`: giới hạn theo web application type.

Không có bảo đảm rằng **mọi** auto-configuration đều dùng `@ConditionalOnMissingBean`, hoặc một bean tự viết luôn thay thế được mọi bean mặc định. Phải kiểm tra chính xác điều kiện, kiểu bean, tên bean, phạm vi xét và thứ tự cấu hình của thành phần liên quan.

### 3.1. Một ví dụ quen thuộc: web MVC

Trong Gradle (Groovy DSL) của một dự án Spring Boot đã được quản lý phiên bản:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Starter web thường mang vào Spring MVC, các dependency cần thiết và web server nhúng phù hợp. Khi ứng dụng được nhận diện là servlet web application, các auto-configuration có điều kiện có thể chuẩn bị `DispatcherServlet`, registration, message converters và những thành phần MVC mặc định.

Controller:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class GreetingController {
    @GetMapping("/greeting")
    String greeting() {
        return "Hello";
    }
}
```

Nếu controller nằm trong phạm vi component scan của ứng dụng MVC đã chạy, `GET /greeting` thường trả response body `Hello`. Đây là ví dụ class thuộc một ứng dụng Boot đầy đủ; một mình file `GreetingController.java` không khởi chạy server.

Điểm phân biệt: `@RestController` và `@GetMapping` là mô hình Spring Web; việc Boot chuẩn bị một số bean và cấu hình mặc định cho ứng dụng web là đóng góp của auto-configuration.

## 4. Starter, auto-configuration và property không phải cùng một thứ

Ba khái niệm thường đi kèm nhưng có vai trò khác nhau:

1. **Starter**: tập dependency được đóng gói hợp lý để dễ chọn khả năng, ví dụ web, validation hoặc data access; starter bản thân không phải container.
2. **Auto-configuration**: lớp cấu hình Spring chạy có điều kiện khi Boot nhận thấy ứng dụng có các thành phần cần thiết.
3. **Configuration properties**: dữ liệu đầu vào cho cấu hình, ví dụ `server.port=8081`; chỉ có hiệu lực nếu thành phần liên quan đọc hoặc bind giá trị đó.

Ví dụ:

```properties
server.port=8081
spring.main.banner-mode=off
```

Trong ứng dụng Boot servlet với embedded server được cấu hình đúng, `server.port` thay đổi cổng lắng nghe. Trong một ứng dụng `AnnotationConfigApplicationContext` thuần không sử dụng Boot/web server, đặt property này tự nó không làm một HTTP server xuất hiện.

Không nên hiểu rằng `application.yml` là tính năng hoàn toàn vắng mặt trong mọi Spring Framework app: ứng dụng Framework có thể tự nạp nguồn YAML/property bằng các cơ chế hoặc thư viện phù hợp. Boot cung cấp đường cấu hình quy ước và integration mặc định, giúp giảm code thiết lập.

## 5. Các cách tùy chỉnh Boot mà vẫn dùng hạ tầng Spring

### 5.1. Định nghĩa bean của ứng dụng

Giả sử có auto-configuration cung cấp một bean mặc định khi chưa có `ClockLabel`. Ứng dụng có thể khai báo:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class CustomConfig {
    @Bean
    ClockLabel clockLabel() {
        return () -> "11:45";
    }
}
```

Đây là **minh họa extension point**, với `ClockLabel` là interface của ứng dụng trong ví dụ mục 2; snippet không phải auto-configuration có sẵn trong Boot. Nếu auto-configuration thực sự dùng điều kiện `@ConditionalOnMissingBean(ClockLabel.class)` đúng ngữ cảnh, bean tùy chỉnh có thể khiến cấu hình mặc định “back off”. Nếu không có điều kiện ấy, việc thêm bean có thể gây trùng hoặc ambiguity thay vì thay thế.

### 5.2. Dùng property chính thức của thành phần

Ưu tiên property được tài liệu hóa để thay đổi default, chẳng hạn cấu hình server hoặc định dạng JSON theo tính năng và version đang chạy. Không tự tạo property rồi kỳ vọng auto-config đọc nó; phải có lớp cấu hình bind property hoặc code ứng dụng chủ động xử lý.

### 5.3. Mở rộng qua interface cấu hình

Với Spring MVC, triển khai `WebMvcConfigurer` có thể thêm formatters, interceptors, resource handlers hoặc các tùy chỉnh khác mà vẫn dùng cơ sở MVC đang hoạt động:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
class MvcConfig implements WebMvcConfigurer {
    @Override
    public void addFormatters(FormatterRegistry registry) {
        // Đăng ký converter hoặc formatter thuộc ứng dụng tại đây.
    }
}
```

Chú ý `@EnableWebMvc` thường chuyển sang chế độ ứng dụng kiểm soát cấu hình MVC theo Spring Framework và có thể khiến nhiều tùy chỉnh MVC mặc định của Boot không còn được áp dụng. Chỉ sử dụng khi thực sự muốn tiếp quản cấu hình MVC.

### 5.4. Loại trừ auto-configuration cụ thể

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
class NoDataSourceApplication {
}
```

Đây là ví dụ cách loại trừ một auto-configuration khi ứng dụng **có chủ đích** không muốn Boot tạo `DataSource`. Không nên sử dụng nó như mẹo che lỗi thiếu JDBC driver, URL hoặc credentials nếu ứng dụng thực sự cần database. Có thể loại trừ bằng property `spring.autoconfigure.exclude` khi phù hợp.

## 6. Tự viết auto-configuration khi phát triển thư viện

Ứng dụng thông thường chỉ cần `@Configuration` và `@Bean`. Auto-configuration có giá trị khi cung cấp một thư viện/starter dùng chung và muốn Boot tự kích hoạt tính năng trên cơ sở điều kiện xác định.

Ví dụ đơn giản (đặt trong JAR chứa auto-configuration):

```java
package example.autoconfig;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(GreetingFormatter.class)
public class GreetingAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean
    GreetingFormatter greetingFormatter() {
        return new GreetingFormatter();
    }
}
```

Và một kiểu thư viện minh họa:

```java
package example.autoconfig;

public class GreetingFormatter {
    public String format(String name) {
        return "Hello, " + name;
    }
}
```

Đăng ký đường dẫn resource:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung file:

```text
example.autoconfig.GreetingAutoConfiguration
```

Ở Spring Boot 3.x, Boot tìm lớp auto-configuration từ file imports, kiểm tra điều kiện có class và bean rồi đăng ký bean khi đủ điều kiện. `@ConditionalOnMissingBean` thường phù hợp cho mặc định có thể bị override bởi ứng dụng. Hãy kiểm tra auto-configuration trong `ApplicationContextRunner` của `spring-boot-test` với các tổ hợp có/không có dependency và bean tùy chỉnh; việc class nằm trong imports chưa chứng minh mọi điều kiện đều thành công.

Không đặt cấu hình auto-configuration của thư viện vào component scan thường ngày như một cách kích hoạt mặc định; cơ chế imports giúp Boot kiểm soát thứ tự/điều kiện của auto-configuration rõ ràng hơn.

## 7. Chẩn đoán vì sao auto-configuration được hoặc không được áp dụng

Khi một bean không xuất hiện, hãy kiểm tra theo trình tự:

1. **Ứng dụng có dùng Boot auto-configuration không?** Xác minh entry point, `@EnableAutoConfiguration`/`@SpringBootApplication`, và không loại trừ ngoài ý muốn.
2. **Classpath có dependency cần thiết không?** Kiểm tra dependency tree và module có mặt tại runtime.
3. **Điều kiện có được đáp ứng không?** Bean khác đã tồn tại, profile/property, web application type, class hoặc resource có thể thay đổi kết quả.
4. **Phạm vi component scan?** Các `@Component` và `@Configuration` ứng dụng có nằm trong packages được scan/import không?
5. **Bean có tạo thất bại?** Lỗi construct/inject, dependency cycle hoặc invalid configuration khác với một auto-configuration không được chọn.
6. **Có nhiều bean cùng loại không?** `@Primary`, qualifier, tên bean hoặc điều kiện mặc định có thể ảnh hưởng injection.

Với Spring Boot, bật báo cáo điều kiện bằng `--debug` hoặc thiết lập mức logging phù hợp; `ConditionEvaluationReport` cho biết những auto-configuration được xét và lý do match/non-match. Nếu dùng Spring Boot Actuator và đã bật/quản lý truy cập endpoint tương ứng, endpoint `conditions` cũng có thể giúp phân tích. Cần bảo vệ endpoint quản trị; không mặc định endpoint này luôn công khai.

Ví dụ chạy ứng dụng Boot đã được đóng gói đúng:

```bash
java -jar build/libs/your-application.jar --debug
```

Tên JAR chỉ là minh họa; sử dụng đúng file build sinh ra. Không trộn lẫn `--debug` của Boot với các công cụ debug JVM.

## 8. Lỗi suy luận phổ biến

- **“Có `spring-context` nên Boot tự cấu hình mọi thứ.”** Không đúng: Spring Context cung cấp cơ chế container; Boot cần auto-config được kích hoạt cùng các điều kiện phù hợp.
- **“Có starter là đủ để feature hoạt động trong mọi tình huống.”** Không đúng: có thể còn cần driver, endpoint, credentials, cấu hình external service hoặc bean cụ thể.
- **“`@Bean` luôn ưu tiên tuyệt đối so với auto-config.”** Cần đọc điều kiện của auto-configuration và thời điểm khai báo bean; đôi khi còn xung đột nhiều bean.
- **“Tắt auto-configuration để sửa bất cứ lỗi startup nào.”** Loại trừ tùy tiện có thể che nguyên nhân và khiến tính năng không tồn tại.
- **“Boot ấn định cách cấu hình, không thể thay.”** Nhiều default có thể đổi qua properties, bean tùy chỉnh và extension point; mức độ phụ thuộc từng thành phần.
- **“Cấu hình XML/Java của Framework đã lỗi thời nên không còn dùng trong Boot.”** Boot vẫn chạy trên Spring IoC container và có thể dùng cùng annotation configuration, XML/import và API container khi cần.
- **“Spring Framework và Spring Boot là hai container độc lập.”** Boot tổ chức khởi động và auto-configuration của ứng dụng dựa trên Spring Framework container.

## 9. Checklist lựa chọn cách cấu hình

1. Nếu chỉ cần tạo bean hoặc khai báo dependency của nghiệp vụ, bắt đầu với `@Component`/`@Configuration`/`@Bean` và constructor injection.
2. Nếu dùng Spring Boot, chọn starter tương ứng trước, xem property chính thức và bean mặc định mà Boot cung cấp.
3. Khi muốn thay hành vi mặc định, xác định extension point chính xác: property, bean tùy chỉnh, interface cấu hình hay loại trừ auto-config.
4. Khi không thấy bean, đọc condition report và dependency tree trước khi viết thêm cấu hình đối phó.
5. Khi phát triển thư viện dành cho nhiều ứng dụng Boot, cân nhắc auto-configuration có điều kiện và test trường hợp back-off; không áp dụng mô hình đó cho mọi bean nghiệp vụ.

**Kết luận:** Spring Framework cung cấp công cụ định nghĩa và vận hành cấu hình của ứng dụng. Spring Boot sử dụng chính công cụ đó để áp dụng những mặc định có điều kiện, giúp giảm việc cấu hình lặp lại. Hiểu ranh giới này cho phép tùy chỉnh đúng chỗ và xử lý lỗi có căn cứ.
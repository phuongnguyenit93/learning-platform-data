# @AutoConfiguration và cấu hình ứng viên

Spring Boot auto-configuration giúp thư viện tự đăng ký các bean phù hợp với classpath, cấu hình môi trường và những bean mà ứng dụng đã cung cấp. Thay vì yêu cầu mỗi ứng dụng import thủ công từng lớp cấu hình, thư viện công bố các lớp auto-configuration như những **ứng viên**. Spring Boot phát hiện các ứng viên đó, sắp xếp và đánh giá điều kiện để quyết định cấu hình nào được áp dụng.

Trong Spring Boot 3, annotation `@AutoConfiguration` đánh dấu một lớp cấu hình dành cho cơ chế này. Danh sách ứng viên được công bố trong file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.

## 1. Auto-configuration giải quyết vấn đề gì?

Giả sử một thư viện cung cấp client để kết nối tới một dịch vụ bên ngoài. Ứng dụng sử dụng thư viện thường cần một bean client và một service bọc quanh client. Nếu phải tự khai báo tất cả bean trong từng ứng dụng, người dùng phải lặp lại cấu hình giống nhau.

Auto-configuration cho phép thư viện cung cấp cấu hình mặc định. Spring Boot chỉ áp dụng cấu hình khi các điều kiện phù hợp, ví dụ:

- Thư viện client có mặt trên classpath.
- Một thuộc tính bật chức năng được cấu hình.
- Ứng dụng chưa tự cung cấp bean thay thế.
- Loại ứng dụng hoặc môi trường đáp ứng yêu cầu của tích hợp.

Ứng dụng vẫn có thể ghi đè bean mặc định hoặc loại trừ một auto-configuration cụ thể. Nhờ vậy, thư viện cung cấp trải nghiệm khởi tạo thuận tiện mà vẫn giữ quyền kiểm soát cho ứng dụng.

## 2. @AutoConfiguration là gì?

`@AutoConfiguration` thuộc package `org.springframework.boot.autoconfigure`. Đây là annotation chuyên dùng để đánh dấu một lớp cấu hình auto-configuration của Spring Boot.

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;

@AutoConfiguration
public class AcmeClientAutoConfiguration {
}
~~~

Về bản chất, `@AutoConfiguration` là một dạng `@Configuration` với `proxyBeanMethods = false`. Điều này phù hợp với cách tổ chức auto-configuration: các phương thức `@Bean` nên nhận dependency thông qua tham số thay vì gọi trực tiếp lẫn nhau để dựa vào CGLIB proxy.

Ví dụ:

~~~java
@AutoConfiguration
public class AcmeClientAutoConfiguration {

    @Bean
    AcmeClientService acmeClientService(AcmeClient client) {
        return new AcmeClientService(client);
    }
}
~~~

Spring phân giải tham số `AcmeClient` như dependency của bean. Không nên gọi trực tiếp `acmeClient()` từ một phương thức `@Bean` khác trong cùng lớp để mong container can thiệp như khi dùng full configuration proxy.

Có thể dùng các annotation điều kiện trên lớp auto-configuration hoặc từng phương thức `@Bean`. Những annotation thường gặp gồm:

- `@ConditionalOnClass`: áp dụng khi một class có mặt trên classpath.
- `@ConditionalOnMissingBean`: áp dụng khi chưa có bean phù hợp.
- `@ConditionalOnBean`: áp dụng khi đã có bean phù hợp.
- `@ConditionalOnProperty`: áp dụng khi thuộc tính cấu hình khớp.
- `@ConditionalOnWebApplication` và `@ConditionalOnNotWebApplication`: áp dụng theo loại ứng dụng web.

## 3. Công bố cấu hình ứng viên trong Spring Boot 3

Trong Spring Boot 3, thư viện công bố các lớp auto-configuration trong resource:

~~~text
src/main/resources/
└── META-INF/
    └── spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

File `AutoConfiguration.imports` chứa tên đầy đủ của từng lớp auto-configuration, mỗi lớp trên một dòng. Ví dụ:

~~~text
com.example.acme.autoconfigure.AcmeClientAutoConfiguration
com.example.acme.autoconfigure.AcmeMetricsAutoConfiguration
~~~

Khi thư viện được đóng gói thành JAR, file resource này nằm trong JAR và có thể được Spring Boot đọc khi ứng dụng sử dụng thư viện.

Một vài điểm cần nhớ:

- Đường dẫn và tên file phải chính xác.
- Mỗi dòng phải là tên lớp đầy đủ, bao gồm package.
- Lớp được liệt kê phải có trên classpath khi ứng viên được xử lý.
- Không liệt kê một lớp cấu hình thông thường chỉ vì muốn component scan tự tìm thấy nó; đây là danh sách dành cho auto-configuration.
- Các lớp được công bố phải có thể được tải và phân tích theo điều kiện classpath tương ứng.

### Ứng viên được phát hiện như thế nào?

`@SpringBootApplication` bao gồm `@EnableAutoConfiguration`. Annotation này đưa `AutoConfigurationImportSelector` vào quá trình phân tích cấu hình. Selector sử dụng danh sách ứng viên được công bố để thu thập các auto-configuration, sau đó áp dụng các bộ lọc, danh sách loại trừ và thứ tự cấu hình.

Có thể hình dung luồng tổng quát:

~~~text
@SpringBootApplication
        |
        v
@EnableAutoConfiguration
        |
        v
AutoConfigurationImportSelector
        |
        v
Đọc AutoConfiguration.imports
        |
        v
Tập auto-configuration ứng viên
        |
        +--> Áp dụng exclusions và filters
        |
        +--> Sắp xếp theo quan hệ before / after
        |
        v
Phân tích cấu hình và đánh giá conditions
        |
        v
Đăng ký các bean definition phù hợp
~~~

Việc có tên lớp trong file imports chỉ có nghĩa lớp đó là ứng viên. Nó không đảm bảo mọi bean trong lớp sẽ được tạo. Các điều kiện trên lớp và phương thức bean vẫn quyết định cấu hình nào thực sự được áp dụng.

## 4. Ví dụ xây dựng một auto-configuration

Giả sử thư viện Acme cung cấp `AcmeClient` và ứng dụng muốn nhận một bean `AcmeClientService` mặc định. Các kiểu `AcmeClient`, `AcmeClientProperties` và `AcmeClientService` dưới đây đại diện cho API của thư viện.

~~~java
package com.example.acme.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(AcmeClient.class)
@ConditionalOnProperty(
        prefix = "acme.client",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
@EnableConfigurationProperties(AcmeClientProperties.class)
public class AcmeClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    AcmeClient acmeClient(AcmeClientProperties properties) {
        return AcmeClient.connect(properties.getEndpoint());
    }

    @Bean
    @ConditionalOnMissingBean
    AcmeClientService acmeClientService(AcmeClient client) {
        return new AcmeClientService(client);
    }
}
~~~

Cấu hình có ba nhóm điều kiện và hành vi:

1. `@ConditionalOnClass(AcmeClient.class)` yêu cầu thư viện Acme client có trên classpath.
2. `@ConditionalOnProperty` cho phép người dùng tắt tích hợp bằng thuộc tính `acme.client.enabled=false`. Nếu thuộc tính bị thiếu, `matchIfMissing = true` cho phép cấu hình mặc định được áp dụng.
3. `@ConditionalOnMissingBean` chỉ đăng ký bean mặc định khi ứng dụng chưa cung cấp bean thay thế phù hợp.

Thuộc tính có thể đặt trong `application.yml`:

~~~yaml
acme:
  client:
    enabled: true
    endpoint: https://api.example.test
~~~

Ứng dụng chỉ cần khai báo dependency của thư viện Acme. Khi auto-configuration được phát hiện và điều kiện khớp, Spring Boot đăng ký các bean mặc định.

Trong thư viện thực tế, cần bảo đảm `AcmeClientProperties` được định nghĩa bằng `@ConfigurationProperties("acme.client")` và có các getter hoặc record accessor phù hợp với cách truy cập. Việc khởi tạo client cũng cần xử lý timeout, xác thực và giải phóng tài nguyên theo API của thư viện.

### Cho phép ứng dụng ghi đè bean mặc định

Nếu ứng dụng cần cấu hình client theo cách riêng, nó có thể tự khai báo bean:

~~~java
@Configuration
public class CustomAcmeConfiguration {

    @Bean
    AcmeClient acmeClient() {
        return AcmeClient.connect("https://internal.example.test");
    }
}
~~~

Do auto-configuration sử dụng `@ConditionalOnMissingBean`, bean do ứng dụng cung cấp sẽ khiến bean mặc định tương ứng không được đăng ký. Đây là một trong những quy ước quan trọng của Spring Boot: auto-configuration cung cấp mặc định có thể thay thế.

Điều kiện `@ConditionalOnMissingBean` thường nên đặt ở phương thức cung cấp bean mặc định để ứng dụng có thể thay thế từng thành phần. Nếu đặt điều kiện ở cấp lớp, việc có một bean phù hợp có thể làm cả lớp cấu hình bị bỏ qua, kể cả những bean khác mà ứng dụng vẫn cần.

## 5. Thứ tự của các auto-configuration ứng viên

Một số auto-configuration phụ thuộc vào bean hoặc cấu hình do auto-configuration khác cung cấp. `@AutoConfiguration` hỗ trợ khai báo quan hệ thứ tự bằng các thuộc tính:

- `before` và `beforeName`: cấu hình này được xử lý trước các cấu hình được chỉ định.
- `after` và `afterName`: cấu hình này được xử lý sau các cấu hình được chỉ định.

Ví dụ, một cấu hình tích hợp cần được xử lý sau cấu hình DataSource:

~~~java
@AutoConfiguration(
        afterName = "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
public class AcmeJdbcAutoConfiguration {
}
~~~

Có thể dùng thuộc tính `after` với class literal nếu có dependency trực tiếp tới lớp auto-configuration đó:

~~~java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
public class AcmeJdbcAutoConfiguration {
}
~~~

Tên lớp dạng chuỗi hữu ích khi không muốn tạo liên kết compile-time với một auto-configuration tùy chọn. Cần bảo đảm tên đầy đủ chính xác nếu sử dụng `afterName` hoặc `beforeName`.

Thứ tự này điều khiển thứ tự xử lý các lớp auto-configuration trong quá trình đăng ký cấu hình. Nó không phải cơ chế bảo đảm thứ tự khởi tạo instance của mọi bean. Nếu một bean cần dependency khác, hãy khai báo dependency qua tham số phương thức `@Bean` hoặc constructor để Spring quản lý đúng quan hệ.

Không nên dùng `@DependsOn` hoặc thứ tự auto-configuration chỉ để che một dependency chưa được khai báo rõ. Hãy thể hiện quan hệ bean bằng dependency injection trước; chỉ dùng before/after khi thứ tự giữa các lớp auto-configuration thực sự ảnh hưởng đến việc đánh giá điều kiện hay đăng ký bean definition.

## 6. Loại trừ một auto-configuration

Ứng dụng có thể loại trừ auto-configuration không mong muốn. Với `@SpringBootApplication` hoặc `@EnableAutoConfiguration`, có thể dùng `exclude`:

~~~java
@SpringBootApplication(
        exclude = AcmeClientAutoConfiguration.class
)
public class Application {
}
~~~

Nếu không muốn tham chiếu trực tiếp class, có thể dùng `excludeName` với tên đầy đủ:

~~~java
@SpringBootApplication(
        excludeName = "com.example.acme.autoconfigure.AcmeClientAutoConfiguration"
)
public class Application {
}
~~~

Cũng có thể cấu hình qua thuộc tính:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - com.example.acme.autoconfigure.AcmeClientAutoConfiguration
~~~

Việc loại trừ ứng viên có nghĩa Spring Boot không áp dụng auto-configuration đó trong lần xây dựng context. Nếu ứng dụng vẫn cần bean do cấu hình đó cung cấp, ứng dụng phải tự khai báo cấu hình thay thế hoặc chọn một thư viện khác cung cấp chức năng tương đương.

Loại trừ auto-configuration không đồng nghĩa gỡ dependency khỏi classpath. JAR vẫn có thể tồn tại trong ứng dụng; chỉ cấu hình được chọn qua cơ chế auto-configuration bị loại khỏi quá trình áp dụng.

## 7. Auto-configuration khác component scanning như thế nào?

Component scanning tìm các stereotype như `@Component`, `@Service`, `@Repository`, `@Controller` và các lớp cấu hình trong phạm vi package được quét.

Auto-configuration được phát hiện theo danh sách ứng viên mà thư viện công bố trong `AutoConfiguration.imports`, sau đó được đưa vào qua cơ chế import của Spring Boot.

Sự khác biệt này quan trọng khi đóng gói starter:

- Component scanning phụ thuộc vào package gốc của ứng dụng và phạm vi quét.
- Auto-configuration có thể nằm trong package riêng của thư viện, ngoài package quét của ứng dụng.
- Điều kiện của auto-configuration giúp bean chỉ xuất hiện khi classpath, property hoặc bean hiện có đáp ứng yêu cầu.

Vì `@AutoConfiguration` là một dạng `@Configuration`, không nên đặt lớp auto-configuration trong package con mà ứng dụng quét như một component thông thường. Hãy để nó được phát hiện qua danh sách imports. Việc này giữ ranh giới rõ ràng giữa cấu hình tự động của thư viện và cấu hình do ứng dụng chủ động khai báo.

## 8. Tổ chức starter và resource

Một starter thường có hai phần:

- Starter artifact tập hợp dependency để ứng dụng dễ thêm tính năng.
- Auto-configuration module chứa các lớp cấu hình tự động và file công bố ứng viên.

Ví dụ cấu trúc module auto-configuration:

~~~text
acme-spring-boot-autoconfigure/
├── src/main/java/
│   └── com/example/acme/autoconfigure/
│       ├── AcmeClientAutoConfiguration.java
│       └── AcmeClientProperties.java
└── src/main/resources/
    └── META-INF/spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung file imports:

~~~text
com.example.acme.autoconfigure.AcmeClientAutoConfiguration
~~~

Khi build JAR, hãy kiểm tra resource được đóng gói đúng đường dẫn. Có thể mở JAR hoặc liệt kê nội dung để xác nhận file tồn tại:

~~~bash
jar tf acme-spring-boot-autoconfigure.jar
~~~

Kết quả cần có đường dẫn `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` cùng các lớp auto-configuration đã biên dịch.

Nếu file không có trong JAR, ứng dụng tiêu thụ thư viện sẽ không tìm thấy ứng viên dù lớp cấu hình đã tồn tại trong bytecode. Nếu tên lớp trong file sai package hoặc sai chính tả, quá trình import có thể thất bại khi ứng viên được xử lý.

## 9. Kiểm thử auto-configuration

Auto-configuration nên được kiểm thử độc lập với toàn bộ ứng dụng. Spring Boot cung cấp `ApplicationContextRunner` để tạo context nhỏ, nạp một tập auto-configuration và kiểm tra bean được đăng ký.

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeClientAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    AcmeClientAutoConfiguration.class
                            )
                    );

    @Test
    void createsDefaultBeansWhenEnabled() {
        contextRunner
                .withPropertyValues("acme.client.enabled=true")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(AcmeClient.class);
                    assertThat(context)
                            .hasSingleBean(AcmeClientService.class);
                });
    }

    @Test
    void backsOffWhenDisabled() {
        contextRunner
                .withPropertyValues("acme.client.enabled=false")
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(AcmeClient.class);
                    assertThat(context)
                            .doesNotHaveBean(AcmeClientService.class);
                });
    }
}
~~~

Ngoài trường hợp bật và tắt, nên kiểm tra:

- Khi ứng dụng tự cung cấp `AcmeClient`, bean mặc định có được bỏ qua không.
- Khi class client không có trên classpath, auto-configuration có được bỏ qua không.
- Khi thuộc tính bị thiếu, `matchIfMissing` có tạo đúng hành vi dự kiến không.
- Khi có nhiều auto-configuration liên quan, thứ tự và điều kiện có tạo ra kết quả đúng không.
- Khi loại trừ auto-configuration, các bean do nó cung cấp có biến mất đúng như mong đợi không.

Để kiểm tra điều kiện classpath, có thể dùng `FilteredClassLoader` trong Spring Boot Test để mô phỏng việc thiếu một thư viện tùy chọn. Với auto-configuration cần web stack hoặc reactive stack, sử dụng context runner phù hợp để xác minh điều kiện theo loại context.

Spring Boot Actuator cũng có thể cung cấp endpoint `conditions` để chẩn đoán vì sao một auto-configuration match hoặc không match. Đây là công cụ hữu ích khi phân tích ứng dụng đang chạy; việc bật và bảo vệ endpoint cần tuân theo chính sách vận hành của ứng dụng.

## 10. Những lỗi thường gặp khi khai báo ứng viên

### Chỉ tạo lớp @AutoConfiguration nhưng quên file imports

Annotation đánh dấu vai trò của lớp nhưng không tự làm cho lớp trở thành ứng viên. Nếu không có entry trong `AutoConfiguration.imports`, cơ chế auto-configuration không có tên lớp để phát hiện.

### Đưa lớp vào file imports nhưng package hoặc tên lớp sai

Spring Boot đọc tên lớp từ resource. Một tên sai có thể làm lỗi quá trình import. Dùng tên lớp đầy đủ và kiểm tra nội dung JAR sau khi build.

### Đặt lớp auto-configuration trong package được component scan

Lớp có thể bị quét như một cấu hình thông thường, làm mất ý nghĩa của việc phát hiện qua danh sách ứng viên và có thể khiến điều kiện hoặc thứ tự xử lý khác với dự kiến. Đặt auto-configuration ở package riêng ngoài phạm vi quét của ứng dụng.

### Không dùng @ConditionalOnMissingBean cho bean mặc định

Nếu auto-configuration luôn đăng ký bean mặc định, ứng dụng có thể không thay thế được bean hoặc gặp nhiều candidate cùng kiểu. Dùng điều kiện phù hợp để auto-configuration lùi lại khi người dùng đã cung cấp bean tùy chỉnh.

### Nhầm thứ tự auto-configuration với thứ tự khởi tạo bean

`before` và `after` sắp xếp quá trình xử lý các lớp cấu hình. Chúng không thay thế constructor injection, tham số phương thức `@Bean` hoặc các quan hệ dependency thực tế.

### Dùng cơ chế đăng ký cũ cho danh sách auto-configuration trong Boot 3

Với Spring Boot 3, danh sách auto-configuration được công bố bằng `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Không tiếp tục thêm các lớp auto-configuration vào khóa `EnableAutoConfiguration` trong `spring.factories` theo hướng dẫn cũ. `spring.factories` vẫn có thể được dùng cho một số extension point khác; điều cần thay đổi là cơ chế công bố auto-configuration candidates.

## 11. Quy trình xây dựng auto-configuration

Khi tạo một auto-configuration cho thư viện, có thể làm theo trình tự:

1. Xác định chức năng mặc định mà thư viện muốn cung cấp.
2. Tạo lớp cấu hình với `@AutoConfiguration`.
3. Thêm điều kiện classpath, property, web application hoặc bean phù hợp.
4. Dùng `@ConditionalOnMissingBean` cho những bean mặc định mà ứng dụng cần có khả năng thay thế.
5. Khai báo các lớp ứng viên trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
6. Chỉ định `before` hoặc `after` khi thứ tự xử lý auto-configuration thực sự cần thiết.
7. Kiểm thử các trường hợp match, không match, bean tùy chỉnh và dependency tùy chọn.
8. Kiểm tra JAR đã đóng gói resource đúng đường dẫn và ứng dụng tiêu thụ thư viện có thể phát hiện cấu hình.

`@AutoConfiguration` đánh dấu lớp cấu hình tự động; file `AutoConfiguration.imports` công bố các lớp đó như ứng viên. Spring Boot phát hiện, sắp xếp và đánh giá điều kiện trước khi đăng ký bean definition. Khi nắm rõ hai phần này, có thể xây dựng starter cung cấp cấu hình mặc định thuận tiện, vẫn cho phép ứng dụng ghi đè và kiểm soát những tích hợp mà nó thực sự cần.


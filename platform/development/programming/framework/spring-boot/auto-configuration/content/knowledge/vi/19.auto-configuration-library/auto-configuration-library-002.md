# Tạo lớp @AutoConfiguration và đăng ký trong tệp imports

> **Mục tiêu:** Đóng gói cấu hình tự động trong một thư viện để ứng dụng Spring Boot phát hiện và áp dụng chỉ bằng cách thêm dependency. Hai phần cốt lõi là **lớp cấu hình được đánh dấu `@AutoConfiguration`** và **tên lớp đầy đủ được ghi trong resource `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`** nằm trong JAR phát hành.

Bài học thuộc nhóm **Thư viện tự cấu hình**, dùng Spring Boot 3.3.x và Java 17+. Nội dung đi từ cơ chế discovery, cấu trúc package/module, điều kiện tạo bean, thứ tự auto-configuration, đến kiểm thử imports resource và xác minh JAR.

## 1. Auto-configuration giải quyết vấn đề gì?

Một thư viện Java/Spring có thể cung cấp service, client, serializer hoặc thành phần hạ tầng. Nếu mỗi ứng dụng phải tự viết lại các bean kết nối thư viện, phần tích hợp sẽ lặp lại và dễ cấu hình thiếu.

Spring Boot Auto Configuration cho phép thư viện đề xuất một cấu hình mặc định. Khi thư viện có trên classpath và các điều kiện phù hợp thỏa mãn, Boot tự áp dụng cấu hình đó. Ứng dụng vẫn có thể cung cấp bean riêng để thay thế mặc định.

Ví dụ, thư viện `acme-greeting` muốn cung cấp `GreetingService`:

1. Ứng dụng thêm dependency thư viện.
2. Boot phát hiện `GreetingAutoConfiguration` từ resource imports.
3. Auto-configuration đăng ký `GreetingService` mặc định khi điều kiện cho phép.
4. Nếu ứng dụng khai báo `GreetingService` riêng, bean mặc định nhường chỗ.
5. Nếu property tắt tính năng, cấu hình không được áp dụng.

Người dùng ứng dụng tiêu thụ thư viện không cần biết tên class cấu hình hoặc tự `@Import` nó. Việc phát hiện là trách nhiệm của cơ chế auto-configuration.

**Phân biệt:** `@Configuration` là annotation cấu hình Spring thông thường. `@AutoConfiguration` là annotation chuyên dụng của Spring Boot, được thiết kế cho các class cấu hình tự động tìm thấy qua `ImportCandidates`. Đánh dấu class bằng `@AutoConfiguration` nhưng không đăng ký trong imports file thì chưa đủ để Boot tự phát hiện qua `@EnableAutoConfiguration`.

## 2. Hai thành phần bắt buộc

### 2.1. Lớp cấu hình với @AutoConfiguration

Ví dụ:

~~~java
package com.acme.greeting.autoconfigure;

import com.acme.greeting.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService greetingService() {
        return new GreetingService("Hello");
    }
}
~~~

`@AutoConfiguration` thuộc package `org.springframework.boot.autoconfigure`. Annotation này tự mang meta-annotation `@Configuration(proxyBeanMethods = false)`; không cần đặt thêm `@Configuration` trên cùng class.

Các điều kiện trong ví dụ có ý nghĩa riêng:

- `@ConditionalOnProperty` ở cấp lớp cho phép toàn bộ auto-configuration áp dụng khi `acme.greeting.enabled=true`. Với `matchIfMissing=true`, tính năng mặc định được bật nếu ứng dụng chưa khai báo property.
- `@ConditionalOnMissingBean(GreetingService.class)` ở method chỉ tạo bean mặc định nếu context chưa có bean phù hợp kiểu `GreetingService`.
- Kiểu trả về của method là `GreetingService` cụ thể để bean condition có đủ thông tin type khi đánh giá.

Auto-configuration nên cung cấp **default có thể thay thế**. Nếu thư viện có integration tùy chọn, dùng thêm condition phù hợp như `@ConditionalOnClass` để chỉ áp dụng khi dependency có mặt. Không tạo bean vô điều kiện rồi buộc ứng dụng phải xóa hoặc ghi đè nó.

### 2.2. Resource đăng ký auto-configuration

Tạo đúng đường dẫn trong module chứa class cấu hình:

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

Nội dung:

~~~text
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
~~~

Mỗi dòng là **tên class đầy đủ (fully qualified class name)** của một auto-configuration. Không ghi tên ngắn, tên bean, tên package đơn lẻ hoặc đường dẫn file Java.

Nếu thư viện có nhiều cấu hình độc lập, liệt kê mỗi class trên một dòng:

~~~text
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
com.acme.greeting.autoconfigure.GreetingMetricsAutoConfiguration
com.acme.greeting.autoconfigure.GreetingWebAutoConfiguration
~~~

Có thể thêm dòng comment bắt đầu bằng `#` trong tệp imports:

~~~text
# Core integration
com.acme.greeting.autoconfigure.GreetingAutoConfiguration

# Optional web integration
com.acme.greeting.autoconfigure.GreetingWebAutoConfiguration
~~~

Đường dẫn và tên file phân biệt chính xác theo chữ hoa/thường. `AutoConfiguration.imports` phải nằm dưới `META-INF/spring/`; nếu đặt trong package Java hoặc dưới `META-INF/` trực tiếp thì Boot không tìm thấy theo quy ước này.

**Không nhầm với `spring.factories`:** Từ Spring Boot 2.7, auto-configuration candidates được đăng ký qua resource imports chuyên dụng. Với Spring Boot 3.3, hãy dùng `AutoConfiguration.imports` cho auto-configuration. `spring.factories` vẫn có thể phục vụ các extension point khác, nhưng không dùng khóa `EnableAutoConfiguration` cũ làm cách đăng ký auto-configuration mới.

## 3. Cấu trúc module và package đề xuất

Một module auto-configure tối giản:

~~~text
acme-greeting-autoconfigure/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/acme/greeting/
    │   │       ├── GreetingService.java
    │   │       └── autoconfigure/
    │   │           └── GreetingAutoConfiguration.java
    │   └── resources/
    │       └── META-INF/
    │           └── spring/
    │               └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/
            └── com/acme/greeting/autoconfigure/
                └── GreetingAutoConfigurationTests.java
~~~

Đặt API thư viện và auto-configuration trong package có chủ đích. Ứng dụng tiêu thụ có thể có package gốc `com.example.app`; thư viện có package `com.acme.greeting` riêng nên không vô tình trở thành đối tượng của component scan thông thường của ứng dụng.

**Auto-configuration phải được tải qua imports file.** Spring Boot khuyến nghị các class này nằm trong package riêng và **không** là mục tiêu của component scanning. Không thêm `@ComponentScan` vào auto-configuration để quét toàn bộ package thư viện. Nếu cần cấu hình helper hoặc import một số component cụ thể, dùng `@Import` tường minh.

Quy tắc thực tế:

- Dùng tên class kết thúc bằng `AutoConfiguration`, ví dụ `GreetingAutoConfiguration`.
- Ưu tiên class top-level thay vì class lồng nhau.
- Giữ auto-configuration tách khỏi package gốc mà ứng dụng người dùng thường dùng cho component scan.
- Không đặt `@Component` hoặc `@Configuration` thông thường để trông chờ component scan phát hiện auto-configuration.
- Tên class trong imports file phải khớp chính xác package và tên class sau khi biên dịch.

### Nếu class là nested class

Trường hợp hiếm khi auto-configuration không phải top-level class, tên trong imports file dùng dấu `$` để phân cách class chứa và class lồng nhau, ví dụ:

~~~text
com.acme.Outer$NestedAutoConfiguration
~~~

Dù cú pháp này được hỗ trợ, class top-level thường dễ tìm, dễ sắp thứ tự và dễ bảo trì hơn.

## 4. Boot tìm imports file như thế nào?

Trong ứng dụng tiêu thụ, `@SpringBootApplication` bao gồm `@EnableAutoConfiguration`. `@EnableAutoConfiguration` sử dụng cơ chế import selector của Boot để tìm các auto-configuration candidates từ resource `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` trên classpath.

Khi ứng dụng có nhiều JAR thư viện, Boot tìm các resource phù hợp trên classpath và tổng hợp các candidate. Vì vậy mỗi JAR auto-configure có thể cung cấp resource cùng tên, chứa danh sách class của chính thư viện đó.

Luồng khái quát:

~~~text
Ứng dụng khởi động
       |
       v
@SpringBootApplication
       |
       v
@EnableAutoConfiguration
       |
       v
AutoConfigurationImportSelector
       |
       v
Đọc các AutoConfiguration.imports trên classpath
       |
       v
Lọc candidate theo exclusions và conditions
       |
       v
Áp dụng auto-configuration phù hợp
       |
       v
Đăng ký các bean mặc định còn đủ điều kiện
~~~

Đây là luồng khái quát; Boot còn có các bước xử lý metadata, thứ tự và điều kiện trước khi bean được tạo.

### Không cần import class bằng tay trong ứng dụng

Ứng dụng tiêu thụ chỉ cần dependency thư viện và cấu hình property nếu cần:

~~~yaml
acme:
  greeting:
    enabled: true
~~~

Nếu dùng mặc định `matchIfMissing=true` như ví dụ, có thể bỏ hẳn property và để tính năng bật theo mặc định. Khi muốn tắt:

~~~properties
acme.greeting.enabled=false
~~~

Khi `@SpringBootApplication` kích hoạt auto-configuration, Boot tìm class trong imports file. Người dùng không cần thêm:

~~~java
@Import(GreetingAutoConfiguration.class)
~~~

`@Import` trực tiếp có thể dùng để nạp một cấu hình trong trường hợp đặc biệt, nhưng nếu mục tiêu là phát hành thư viện tự cấu hình dùng được khi thêm dependency thì phải đăng ký đúng imports file.

## 5. Điều kiện trong auto-configuration

`@AutoConfiguration` chỉ đánh dấu class là auto-configuration; nó không tự quyết định bean nào nên được tạo. Các condition xác định phạm vi áp dụng.

### 5.1. Điều kiện classpath

`@ConditionalOnClass` chỉ áp dụng cấu hình khi một class có trên runtime classpath. Ví dụ một thư viện cung cấp integration cho client tùy chọn:

~~~java
@AutoConfiguration
public class GreetingAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.client.VendorClient")
    static class VendorClientConfiguration {

        @Bean
        @ConditionalOnMissingBean
        VendorGreetingClient vendorGreetingClient() {
            return new VendorGreetingClient();
        }
    }
}
~~~

Đoạn này là ví dụ cấu trúc; các kiểu `VendorGreetingClient` và thư viện vendor phải được cung cấp trong module phù hợp. Điểm quan trọng là class cấu hình nested được bảo vệ bởi condition classpath. Khi dependency là tùy chọn, đừng để một method `@Bean` ở class luôn được nạp có kiểu trả về trực tiếp là class không tồn tại; JVM có thể phải load kiểu đó trước khi condition trên method được áp dụng. Tách phần phụ thuộc tùy chọn vào nested configuration có condition ở cấp class.

Trong composed meta-annotation có `@ConditionalOnClass` hoặc `@ConditionalOnMissingClass`, tài liệu Boot yêu cầu dùng thuộc tính `name` thay vì tham chiếu class bằng `value` trong trường hợp đó.

### 5.2. Điều kiện bean

`@ConditionalOnMissingBean` là mẫu phổ biến để cho phép ứng dụng thay default:

~~~java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService greetingService() {
    return new GreetingService("Hello");
}
~~~

Nếu ứng dụng đã có bean `GreetingService`, method default không đăng ký bean đó. Các bean mặc định khác trong cùng auto-configuration vẫn có thể được tạo nếu điều kiện riêng của chúng đạt.

`@ConditionalOnBean` chỉ áp dụng bean phụ trợ khi một bean dependency đã có. Bean conditions chỉ nhìn những bean definition đã được xử lý tại thời điểm condition chạy; do đó hãy sắp thứ tự auto-configuration khi phụ thuộc một provider khác.

### 5.3. Điều kiện property

`@ConditionalOnProperty` cho phép bật/tắt theo cấu hình triển khai:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class GreetingAutoConfiguration {
    // @Bean methods
}
~~~

Nên chỉ rõ `havingValue` cho cờ boolean. Mặc định nếu không chỉ định, property có mặt và không bằng chuỗi `false` có thể khớp; điều đó không tương đương với yêu cầu chính xác `true`. `matchIfMissing` quyết định việc thiếu khóa có được coi là khớp không.

### 5.4. Các condition khác

Tùy mục tiêu, Boot còn cung cấp `@ConditionalOnResource`, `@ConditionalOnWebApplication`, `@ConditionalOnNotWebApplication` và `@ConditionalOnExpression`. Chọn condition theo điều cần kiểm tra: classpath, bean, property, resource hoặc kiểu ứng dụng. Tránh dùng SpEL tham chiếu trực tiếp bean nếu có thể, vì bean có thể bị khởi tạo quá sớm trong lúc context refresh.

## 6. Thứ tự áp dụng các auto-configuration

Nếu một auto-configuration cần chạy sau cấu hình provider khác, khai báo quan hệ thứ tự:

~~~java
@AutoConfiguration(after = JacksonAutoConfiguration.class)
public class GreetingJsonAutoConfiguration {
    // Bean phụ thuộc cấu hình Jackson
}
~~~

Các thuộc tính thứ tự của `@AutoConfiguration`:

- `before`: chạy trước các auto-configuration class được chỉ định.
- `beforeName`: chạy trước class được chỉ định bằng tên đầy đủ dạng chuỗi.
- `after`: chạy sau các auto-configuration class được chỉ định.
- `afterName`: chạy sau class được chỉ định bằng tên đầy đủ dạng chuỗi.

Dùng `afterName` khi muốn tham chiếu tên một cấu hình mà module không cần phụ thuộc compile-time vào class đó. Nếu các auto-configuration không cần biết trực tiếp về nhau nhưng vẫn cần thứ tự tương đối, có thể dùng `@AutoConfigureOrder`.

**Thứ tự auto-configuration chỉ ảnh hưởng thứ tự đăng ký bean definition.** Nó không quyết định thứ tự object bean được tạo sau đó; việc tạo bean phụ thuộc dependency injection và các quan hệ `@DependsOn` nếu có. Đừng dùng `@AutoConfigureOrder` như cách thay thế dependency injection hoặc để điều khiển thứ tự gọi constructor.

Không dựa vào thứ tự các dòng trong `AutoConfiguration.imports` để thiết lập quan hệ provider/consumer. Hãy khai báo `before`/`after` rõ ràng.

## 7. Ví dụ hoàn chỉnh: thư viện Greeting

Phần này ghép class, imports resource và test thành một ví dụ nhất quán.

### 7.1. Service API

**Tệp:** `src/main/java/com/acme/greeting/GreetingService.java`

~~~java
package com.acme.greeting;

public record GreetingService(String prefix) {

    public String greet(String name) {
        return prefix + ", " + name + "!";
    }
}
~~~

Đây là class API của thư viện. Nó không phụ thuộc Spring; auto-configuration chỉ có nhiệm vụ đăng ký một instance mặc định.

### 7.2. Auto-configuration class

**Tệp:** `src/main/java/com/acme/greeting/autoconfigure/GreetingAutoConfiguration.java`

~~~java
package com.acme.greeting.autoconfigure;

import com.acme.greeting.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService greetingService() {
        return new GreetingService("Hello");
    }
}
~~~

`@ConditionalOnProperty` là điều kiện chung của cấu hình. `@ConditionalOnMissingBean` ở method cho phép ứng dụng cung cấp implementation khác. Kiểu trả về được khai báo cụ thể là `GreetingService` để condition nhìn thấy type rõ ràng.

### 7.3. Imports resource

**Tệp:** `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

~~~text
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
~~~

Đây là bước làm cho Boot tự phát hiện class khi JAR nằm trên classpath. Resource thuộc module auto-configure, không phải file cấu hình YAML của ứng dụng.

### 7.4. Cấu hình ở ứng dụng tiêu thụ

Nếu dùng default:

~~~yaml
acme:
  greeting:
    enabled: true
~~~

Ứng dụng có thể inject service:

~~~java
package com.example.app;

import com.acme.greeting.GreetingService;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner showGreeting(GreetingService greetingService) {
        return args -> System.out.println(
                greetingService.greet("Lan"));
    }
}
~~~

Khi cấu hình hợp lệ và service default được đăng ký, stdout:

~~~text
Hello, Lan!
~~~

Nếu ứng dụng khai báo `GreetingService` riêng, `@ConditionalOnMissingBean` khiến default lùi lại. Nếu `acme.greeting.enabled=false`, cấu hình không tạo bean service; ứng dụng khi đó không thể inject `GreetingService` trừ khi có một bean khác cung cấp nó.

**Package ứng dụng và package thư viện:** `com.example.app` không phải package cha của `com.acme.greeting`, vì thế component scan mặc định của `@SpringBootApplication` không quét class auto-configuration thư viện. Boot vẫn phát hiện nó thông qua imports file.

## 8. Kiểm thử cả điều kiện lẫn việc phát hiện từ imports file

Một lỗi phổ biến là test trực tiếp auto-configuration bằng `AutoConfigurations.of(...)` rồi kết luận imports file đã đúng. Cách đó **không kiểm tra resource**: test đã chỉ định class trực tiếp. Cần có ít nhất một test chạy qua `@EnableAutoConfiguration` để chứng minh Boot đọc được imports file.

Ví dụ test sau dùng Java 17+, Spring Boot 3.3.x, JUnit Jupiter và AssertJ. Đặt tệp trong cùng module với resource `src/main/resources` ở trên.

**Tệp:** `src/test/java/com/acme/greeting/autoconfigure/GreetingAutoConfigurationTests.java`

~~~java
package com.acme.greeting.autoconfigure;

import com.acme.greeting.GreetingService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingAutoConfigurationTests {

    private final ApplicationContextRunner directRunner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(GreetingAutoConfiguration.class));

    @Test
    void enableAutoConfigurationDiscoversImportsFile() {
        new ApplicationContextRunner()
                .withUserConfiguration(ImportDiscoveryApplication.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(GreetingService.class);
                    assertThat(context.getBean(GreetingService.class)
                            .greet("Lan")).isEqualTo("Hello, Lan!");
                });
    }

    @Test
    void missingEnabledPropertyUsesDefaultAndRegistersService() {
        directRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(GreetingService.class);
        });
    }

    @Test
    void falsePropertyDisablesAutoConfiguration() {
        directRunner.withPropertyValues("acme.greeting.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(GreetingService.class);
                });
    }

    @Test
    void userBeanMakesDefaultBackOff() {
        directRunner.withUserConfiguration(UserGreetingConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(GreetingService.class);
                    assertThat(context).hasBean("customGreetingService");
                    assertThat(context).doesNotHaveBean("greetingService");
                    assertThat(context.getBean(GreetingService.class)
                            .greet("Lan")).isEqualTo("Welcome, Lan!");
                });
    }

    @SpringBootConfiguration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class ImportDiscoveryApplication {
    }

    @Configuration(proxyBeanMethods = false)
    static class UserGreetingConfiguration {

        @Bean
        GreetingService customGreetingService() {
            return new GreetingService("Welcome");
        }
    }
}
~~~

Giải thích hai đường test:

- `enableAutoConfigurationDiscoversImportsFile` dùng cấu hình có `@EnableAutoConfiguration`. Boot phải tự đọc `AutoConfiguration.imports` từ classpath để tìm `GreetingAutoConfiguration`. Đây là test quan trọng cho việc đăng ký.
- Ba test còn lại dùng `AutoConfigurations.of(GreetingAutoConfiguration.class)` để nạp trực tiếp class, tập trung kiểm tra default property và back-off. Chúng không thay thế test discovery ở trên.

Chạy trong module Maven có Spring Boot 3.3.x:

~~~bash
mvn -Dtest=GreetingAutoConfigurationTests test
~~~

Hoặc với Gradle wrapper:

~~~bash
./gradlew test --tests com.acme.greeting.autoconfigure.GreetingAutoConfigurationTests
~~~

**Kết quả mong đợi:** 4 test PASS, không có stdout cố định vì test dùng assertion. Test discovery xác nhận service được tìm thấy qua imports file; test còn lại xác nhận default hoạt động, property false tắt cấu hình, và bean người dùng thay thế default.

## 9. Đóng gói và kiểm tra JAR

Resource trong `src/main/resources` sẽ được Maven/Gradle copy vào output resources và đóng gói trong JAR. Một lỗi phổ biến là file tồn tại trên IDE nhưng bị đặt nhầm module hoặc sai tên nên không xuất hiện trong artifact đã publish.

Với Maven:

~~~bash
mvn clean package
~~~

Kiểm tra JAR:

~~~bash
jar tf target/acme-greeting-autoconfigure-1.0.0.jar
~~~

Trong danh sách phải có chính xác:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Trên Windows PowerShell có thể lọc:

~~~powershell
jar tf target/acme-greeting-autoconfigure-1.0.0.jar |
    Select-String "META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports"
~~~

Nếu không thấy resource:

1. Kiểm tra tên file và chữ hoa/thường.
2. Kiểm tra file nằm trong `src/main/resources/META-INF/spring/`, không nằm trong `src/test/resources`.
3. Kiểm tra module chứa auto-configuration thực sự được build và publish.
4. Kiểm tra cấu hình build có loại trừ resource đó không.
5. Kiểm tra nội dung resource có tên class đúng với package/class đã biên dịch không.

Chỉ xác nhận file có trong JAR vẫn chưa chứng minh class được áp dụng; hãy chạy test discovery bằng `@EnableAutoConfiguration` hoặc một ứng dụng tiêu thụ thật.

## 10. Cấu trúc custom starter

Với thư viện đơn giản, có thể gộp code API, auto-configuration và resource imports trong một module. Khi thư viện có nhiều dependency hoặc nhiều integration tùy chọn, nên tách thành hai module:

~~~text
acme/
├── acme-spring-boot-autoconfigure/
│   ├── API và AutoConfiguration classes
│   ├── META-INF/spring/AutoConfiguration.imports
│   └── configuration metadata
└── acme-spring-boot-starter/
    └── dependency declarations
~~~

Vai trò:

- **Autoconfigure module:** chứa class cấu hình, API hỗ trợ, `@ConfigurationProperties`, resource imports và các điều kiện.
- **Starter module:** thường là JAR rất nhỏ, tập hợp dependency auto-configure cùng những dependency cần thiết để người dùng thêm một starter là đủ.

Không bắt buộc phải tách hai module. Nếu thư viện chỉ có ít thành phần, không có nhiều dependency tùy chọn và cấu hình đơn giản, gộp chung có thể hợp lý.

Nếu module auto-configure tham chiếu một thư viện vendor tùy chọn, cân nhắc khai báo dependency đó là optional trong metadata build để người dùng có thể dùng module auto-configure mà không buộc kéo tất cả integration. Starter dành cho một trường hợp sử dụng cụ thể có thể bổ sung dependency vendor tương ứng.

Tên module nên dùng namespace của thư viện, ví dụ `acme-spring-boot-autoconfigure` và `acme-spring-boot-starter`. Tránh bắt đầu tên module của riêng thư viện bằng `spring-boot`.

## 11. Metadata cho cấu hình và thay thế class

### 11.1. Metadata điều kiện

Spring Boot có thể dùng annotation processor `spring-boot-autoconfigure-processor` để thu thập metadata condition của auto-configuration, giúp lọc candidate sớm và cải thiện startup trong một số trường hợp. Với Maven, khai báo annotation processor trong cấu hình compiler plugin; với Gradle, dùng configuration `annotationProcessor`.

Nếu thư viện cung cấp `@ConfigurationProperties`, `spring-boot-configuration-processor` có thể tạo `META-INF/spring-configuration-metadata.json` để IDE gợi ý tên property, kiểu và mô tả. Đây là metadata cấu hình cho người dùng, **khác** với `AutoConfiguration.imports` dùng để phát hiện class.

| Resource | Mục đích |
| --- | --- |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Liệt kê auto-configuration class để Boot phát hiện |
| `META-INF/spring-autoconfigure-metadata.properties` | Metadata điều kiện phục vụ tối ưu quá trình lọc auto-configuration |
| `META-INF/spring-configuration-metadata.json` | Mô tả property để IDE/documentation hỗ trợ người dùng |

Processor không thay thế imports file. Một auto-configuration class vẫn phải được đăng ký trong resource imports.

### 11.2. Đổi tên hoặc thay thế auto-configuration class

Auto-configuration class có thể được class khác tham chiếu qua `before`/`after` hoặc danh sách exclusions. Khi đổi package hoặc thay class, có thể cần resource:

**`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements`**

Ví dụ nội dung:

~~~text
com.acme.greeting.autoconfigure.LegacyGreetingAutoConfiguration=com.acme.greeting.autoconfigure.GreetingAutoConfiguration
~~~

File này ánh xạ class cũ sang class thay thế. Đồng thời cập nhật `AutoConfiguration.imports` để chỉ liệt kê class mới; không tiếp tục đăng ký cả class cũ và class thay thế nếu chúng đại diện cho cùng một cấu hình.

Đây là tình huống bảo trì thư viện đã phát hành, không phải resource bắt buộc cho starter mới.

## 12. Những lỗi thường gặp

1. **Chỉ tạo class `@AutoConfiguration` mà quên imports file:** Boot không tự phát hiện class chỉ vì nó nằm trong JAR.
2. **Sai đường dẫn resource:** file phải nằm dưới `META-INF/spring/` với đúng tên `org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
3. **Ghi tên class không đầy đủ:** phải dùng FQCN, bao gồm package và tên class.
4. **Đặt imports file trong test resources:** resource không có trong artifact chính mà ứng dụng tiêu thụ sử dụng.
5. **Component-scan auto-configuration:** có thể làm cấu hình được nạp như cấu hình thông thường, ngoài cơ chế auto-configuration và thứ tự condition dự kiến. Hãy giữ package riêng và chỉ đăng ký qua imports file.
6. **Dùng `spring.factories` theo hướng dẫn cũ:** với Boot 3.3, đăng ký auto-configuration bằng imports file.
7. **Đặt condition thiếu bean trên method trả về `Object`:** metadata type có thể không đủ để Boot đánh giá đúng; trả về kiểu cụ thể.
8. **Không dùng `@ConditionalOnMissingBean` cho default có thể thay:** ứng dụng có thể nhận nhiều bean cùng chức năng và gặp lỗi chọn candidate.
9. **Nhầm thứ tự file imports với thứ tự xử lý:** dùng `before`/`after` hoặc `@AutoConfigureOrder` khi cần.
10. **Dùng thứ tự auto-configuration để điều khiển thứ tự khởi tạo bean:** dependency injection và `@DependsOn` mới chi phối việc tạo object.
11. **Dùng component scan trong auto-configuration:** nếu cần helper, ưu tiên `@Import` cụ thể thay vì quét toàn package.
12. **Test chỉ dùng `AutoConfigurations.of`:** cách này nạp class trực tiếp, không chứng minh imports file được đóng gói hoặc đọc.
13. **Chỉ kiểm tra JAR có file:** vẫn cần test discovery để phát hiện sai FQCN, class không load được hoặc condition không khớp.
14. **Đăng ký cùng class ở nhiều cơ chế:** tránh vừa liệt kê trong imports vừa tự scan/import như cấu hình thông thường nếu không có lý do rõ ràng.

## 13. Checklist phát hành thư viện

- [ ] Auto-configuration class dùng `@AutoConfiguration` và có package riêng.
- [ ] Default bean có condition phù hợp, thường là `@ConditionalOnMissingBean`.
- [ ] Property condition có `havingValue` và `matchIfMissing` rõ ràng khi dùng cờ boolean.
- [ ] Resource imports nằm đúng đường dẫn trong `src/main/resources`.
- [ ] Mỗi entry là FQCN chính xác; comment dùng `#` nếu cần.
- [ ] Không component-scan auto-configuration class.
- [ ] Optional dependency được cô lập bằng condition phù hợp.
- [ ] Có test `ApplicationContextRunner` cho default, property và user override.
- [ ] Có test discovery thông qua `@EnableAutoConfiguration`.
- [ ] JAR build ra chứa imports resource.
- [ ] Tên property và module dùng namespace riêng của thư viện.
- [ ] Starter module kéo theo các dependency cần thiết cho use case dự kiến.

## 14. Tự kiểm tra kiến thức

1. Class đã có `@AutoConfiguration` nhưng không có trong `AutoConfiguration.imports`. `@SpringBootApplication` có tự phát hiện class không?  
   **Đáp án:** Không theo cơ chế auto-configuration discovery; phải đăng ký class trong resource imports.

2. Tên class trong imports file là `GreetingAutoConfiguration` hay FQCN?  
   **Đáp án:** FQCN, ví dụ `com.acme.greeting.autoconfigure.GreetingAutoConfiguration`.

3. Resource imports đặt trong `src/test/resources` có đủ cho ứng dụng tiêu thụ thư viện không?  
   **Đáp án:** Không; nó phải nằm trong main resources và được đóng gói trong JAR phát hành.

4. Vì sao không nên component-scan auto-configuration?  
   **Đáp án:** Boot yêu cầu auto-configuration được tải qua imports file để giữ đúng cơ chế lọc, thứ tự và condition. Component scanning có thể làm nó được xử lý như cấu hình thông thường.

5. `@ConditionalOnMissingBean` trên method default giúp gì?  
   **Đáp án:** Cho phép bean do ứng dụng khai báo thay thế default; các bean mặc định khác trong cùng class vẫn có thể được áp dụng.

6. Test dùng `AutoConfigurations.of(GreetingAutoConfiguration.class)` có kiểm tra imports file không?  
   **Đáp án:** Không; nó nạp class trực tiếp. Dùng test `@EnableAutoConfiguration` để xác nhận discovery.

7. `@AutoConfiguration(after = OtherAutoConfiguration.class)` điều khiển điều gì?  
   **Đáp án:** Thứ tự áp dụng/đăng ký bean definition của auto-configuration, không điều khiển thứ tự khởi tạo object.

8. Nếu đổi tên một auto-configuration đã phát hành, resource nào có thể cần cập nhật để ánh xạ class cũ sang class mới?  
   **Đáp án:** `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements`, đồng thời cập nhật imports file chỉ còn class thay thế.

## Tài liệu chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): `@AutoConfiguration`, imports file, component-scan rule, ordering, condition và testing.
- [Spring Boot 3.3 API — AutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): meta-annotation, attributes `before`/`after` và ý nghĩa auto-configuration.
- [Spring Boot 3.3 API — EnableAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html): cơ chế bật auto-configuration trong ứng dụng.
- [Spring Boot 3.3 API — ImportAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/ImportAutoConfiguration.html): nạp có chọn lọc auto-configuration; hữu ích trong một số tình huống, đặc biệt khi viết test.
- [Spring Boot 3.3 — Configuration Metadata](https://docs.spring.io/spring-boot/3.3/reference/configuration-metadata.html): metadata property hỗ trợ IDE và tài liệu.

**Ghi nhớ:** Một thư viện tự cấu hình cần cả **class `@AutoConfiguration`** và **resource `AutoConfiguration.imports` được đóng gói trong JAR**. Class cung cấp bean cùng conditions; imports file giúp Boot tìm class; `@EnableAutoConfiguration` kích hoạt quá trình discovery; test phải kiểm tra cả đường discovery thực tế lẫn hành vi default/back-off.

# Đảm bảo ứng dụng không cần quét package của thư viện: thiết kế Spring Boot Auto-configuration

## 1. Mục tiêu của thư viện tự cấu hình

Giả sử thư viện `Acme Widget` cung cấp một service dùng chung. Ứng dụng tiêu thụ chỉ cần thêm starter vào dependency và cấu hình:

~~~yaml
acme:
  widget:
    endpoint: https://api.example.test
~~~

Ứng dụng không nên phải biết package nội bộ của thư viện để mở rộng component scan:

~~~java
@ComponentScan({
    "com.example.application",
    "com.acme.widget"
})
~~~

Cách làm này khiến ứng dụng phụ thuộc vào cấu trúc source của thư viện. Nếu thư viện đổi package, tách module hoặc thêm package implementation, người dùng có thể phải sửa cấu hình ứng dụng.

Spring Boot có cơ chế **auto-configuration** để thư viện tự khai báo các bean cần thiết. Boot phát hiện class cấu hình từ metadata trong JAR, sau đó áp dụng condition và đăng ký bean. Nhờ vậy:
- Ứng dụng chỉ cần bật auto-configuration, thường qua `@SpringBootApplication`.
- Thư viện tự công bố class cấu hình trong JAR.
- Bean được đăng ký bằng `@Bean`, `@Import` và `@EnableConfigurationProperties`.
- `@ConditionalOnClass`, `@ConditionalOnProperty` và `@ConditionalOnMissingBean` giúp cấu hình chỉ bật khi phù hợp và cho phép người dùng thay default.
- Component scan của ứng dụng chỉ cần bao phủ package do ứng dụng sở hữu.

**Nguyên tắc:** thư viện phải tự mô tả cách tích hợp Spring; ứng dụng không cần quét package của thư viện để tìm implementation nội bộ.

## 2. Component scan và auto-configuration là hai cơ chế riêng

`@SpringBootApplication` kết hợp ba vai trò chính: cấu hình ứng dụng, kích hoạt auto-configuration và component scan. Component scan mặc định bắt đầu từ package chứa class ứng dụng và đi xuống các package con.

Ví dụ:

~~~text
com.example.shop
├── ShopApplication.java
├── controller
├── service
└── config

com.acme.widget
├── api
├── internal
└── autoconfigure
~~~

Nếu `ShopApplication` nằm trong `com.example.shop`, component scan mặc định không tự mở rộng sang package sibling `com.acme.widget`. Đây là phạm vi có chủ đích: ứng dụng sở hữu package của nó; thư viện chịu trách nhiệm đăng ký bean công khai của thư viện.

| Cơ chế | Mục tiêu | Nguồn thông tin |
| --- | --- | --- |
| `@ComponentScan` | Tìm class có stereotype như `@Component`, `@Service`, `@Repository` trong package được quét | Package khai báo hoặc package của class cấu hình |
| `@EnableAutoConfiguration` | Tìm và áp dụng cấu hình tự động từ dependency | `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` |

Ứng dụng thường dùng cả hai: component scan cho code ứng dụng và auto-configuration cho tích hợp thư viện. Package của thư viện không cần là package con của ứng dụng.

## 3. Khai báo auto-configuration trong AutoConfiguration.imports

Trong Spring Boot 3.x, JAR chứa auto-configuration cần file:

`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Ví dụ nội dung:

~~~text
com.acme.widget.autoconfigure.WidgetAutoConfiguration
~~~

Mỗi dòng là tên đầy đủ của một auto-configuration class. Có thể liệt kê nhiều class; comment bắt đầu bằng `#` được phép. Nếu dùng nested class, tên class trong file dùng `$` để phân cách class ngoài và class lồng.

Spring Boot đọc descriptor này từ các JAR trên classpath. Vì thế thư viện có thể đóng gói cấu hình trong JAR riêng mà không cần đặt class đó dưới package ứng dụng.

### Vì sao không dùng spring.factories cho việc này?

`META-INF/spring.factories` vẫn được Spring dùng cho một số extension khác. Tuy nhiên, từ Spring Boot 3.0, đăng ký auto-configuration qua key `EnableAutoConfiguration` trong file này đã bị loại bỏ. Spring Boot 2.7 giới thiệu `AutoConfiguration.imports` và hỗ trợ giai đoạn chuyển tiếp; thư viện nhắm tới Boot 3.x nên dùng descriptor mới.

Chỉ thêm annotation `@AutoConfiguration` vào source chưa đủ để starter tự được phát hiện. File imports phải được đóng gói trong JAR nằm trên runtime classpath.

## 4. Tổ chức module để consumer chỉ cần thêm starter

Một cấu trúc phổ biến:

~~~text
acme-widget/
├── acme-widget-autoconfigure/
│   ├── src/main/java/com/acme/widget/
│   │   ├── WidgetService.java
│   │   ├── DefaultWidgetService.java
│   │   ├── WidgetProperties.java
│   │   └── autoconfigure/
│   │       ├── WidgetAutoConfiguration.java
│   │       └── WidgetClientConfiguration.java
│   └── src/main/resources/META-INF/spring/
│       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── acme-widget-spring-boot-starter/
    └── build.gradle hoặc pom.xml
~~~

Module `autoconfigure` chứa auto-configuration class, conditions, properties, bean factory methods và descriptor imports. Module `starter` thường là dependency aggregator: khai báo module autoconfigure cùng những dependency runtime phù hợp để consumer thêm một dependency duy nhất.

Gradle consumer:

~~~kotlin
dependencies {
    implementation("com.acme:acme-widget-spring-boot-starter:1.0.0")
}
~~~

Maven consumer:

~~~xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>acme-widget-spring-boot-starter</artifactId>
    <version>1.0.0</version>
</dependency>
~~~

File imports nằm trong JAR `acme-widget-autoconfigure` vẫn được Boot phát hiện nếu starter khai báo module đó là dependency transitive. Không cần sao chép descriptor sang project ứng dụng.

## 5. Ví dụ thư viện: auto-configuration và bean registration tường minh

Ví dụ dùng Java 17+ và Spring Boot 3.3. Các class nhỏ để tập trung vào cơ chế đăng ký.

**`WidgetService.java`:**

~~~java
package com.acme.widget;

public interface WidgetService {
    String endpoint();
}
~~~

**`DefaultWidgetService.java`:**

~~~java
package com.acme.widget;

public final class DefaultWidgetService implements WidgetService {

    private final String endpoint;

    public DefaultWidgetService(String endpoint) {
        this.endpoint = endpoint;
    }

    @Override
    public String endpoint() {
        return endpoint;
    }
}
~~~

**`WidgetProperties.java`:**

~~~java
package com.acme.widget;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.widget")
public class WidgetProperties {

    private String endpoint = "https://default.example";

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }
}
~~~

**`WidgetAutoConfiguration.java`:**

~~~java
package com.acme.widget.autoconfigure;

import com.acme.widget.WidgetProperties;
import com.acme.widget.WidgetService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Import;

@AutoConfiguration
@ConditionalOnClass(WidgetService.class)
@EnableConfigurationProperties(WidgetProperties.class)
@Import(WidgetClientConfiguration.class)
public class WidgetAutoConfiguration {
}
~~~

**`WidgetClientConfiguration.java`:**

~~~java
package com.acme.widget.autoconfigure;

import com.acme.widget.DefaultWidgetService;
import com.acme.widget.WidgetProperties;
import com.acme.widget.WidgetService;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class WidgetClientConfiguration {

    @Bean
    @ConditionalOnMissingBean(WidgetService.class)
    DefaultWidgetService widgetService(WidgetProperties properties) {
        return new DefaultWidgetService(properties.getEndpoint());
    }
}
~~~

File `AutoConfiguration.imports` có đúng một dòng:

~~~text
com.acme.widget.autoconfigure.WidgetAutoConfiguration
~~~

Luồng đăng ký:
1. `@EnableAutoConfiguration` của ứng dụng yêu cầu Boot tìm auto-configuration candidates.
2. Boot đọc descriptor và tìm `WidgetAutoConfiguration`.
3. `@ConditionalOnClass` xác nhận API của thư viện có trên classpath.
4. `@EnableConfigurationProperties` đăng ký `WidgetProperties` và bật binding từ `Environment`.
5. `@Import` đưa `WidgetClientConfiguration` vào context mà không quét package.
6. Method `@Bean` tạo default `WidgetService` nếu ứng dụng chưa có implementation phù hợp.

Không class nào phải được tìm thấy bằng component scan của ứng dụng.

## 6. Dùng @Import thay vì component scan bên trong auto-configuration

Spring Boot khuyến nghị auto-configuration **không tự bật component scan để tìm thêm component**. Hãy import cụ thể những cấu hình cần thiết:

~~~java
@AutoConfiguration
@Import({
        WidgetClientConfiguration.class,
        WidgetMetricsConfiguration.class,
        WidgetHealthConfiguration.class
})
public class WidgetAutoConfiguration {
}
~~~

Mỗi class được import có thể chứa các method `@Bean` và condition riêng. Các class hỗ trợ có thể nằm trong package nội bộ của thư viện; `@Import` đăng ký chúng trực tiếp theo class reference.

| Nhu cầu | Cơ chế |
| --- | --- |
| Đăng ký auto-configuration class | `AutoConfiguration.imports` |
| Nạp nhóm cấu hình hỗ trợ | `@Import(SomeConfiguration.class)` |
| Đăng ký service/default bean | Method `@Bean` |
| Đăng ký properties class | `@EnableConfigurationProperties` |
| Chỉ bật khi dependency có mặt | `@ConditionalOnClass` |
| Chỉ tạo default khi chưa có bean | `@ConditionalOnMissingBean` |
| Đăng ký động theo metadata phức tạp | `ImportSelector` hoặc `ImportBeanDefinitionRegistrar` khi thật sự cần |

Không nên dùng `@ComponentScan("com.acme.widget")` trong auto-configuration. Scan rộng có thể đăng ký nhầm class nội bộ, test helper hoặc component không dành cho public API; nó cũng khiến ứng dụng phụ thuộc vào package layout của thư viện. Danh sách import tường minh giúp reviewer biết chính xác nhóm bean nào được nạp.

## 7. Cho phép ứng dụng thay bean mặc định

Thư viện nên cung cấp default hữu ích nhưng cho phép ứng dụng override. Method `widgetService` dùng:

~~~java
@Bean
@ConditionalOnMissingBean(WidgetService.class)
DefaultWidgetService widgetService(WidgetProperties properties) {
    return new DefaultWidgetService(properties.getEndpoint());
}
~~~

Khi ứng dụng khai báo bean triển khai `WidgetService`, condition không khớp và default back off.

Cấu hình phía ứng dụng:

~~~java
package com.example.application;

import com.acme.widget.WidgetService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class CustomWidgetConfiguration {

    @Bean
    CustomWidgetService customWidgetService() {
        return new CustomWidgetService();
    }

    static final class CustomWidgetService implements WidgetService {
        @Override
        public String endpoint() {
            return "custom://application";
        }
    }
}
~~~

Bean tùy chỉnh được đăng ký từ cấu hình do ứng dụng sở hữu; auto-configuration của thư viện thấy bean definition đó và bỏ qua default. Không cần scan package thư viện.

Nên dùng return type cụ thể trên method `@Bean`. Default method trả `DefaultWidgetService` dù condition kiểm tra interface `WidgetService`, giúp Spring có type metadata đầy đủ.

Tránh vừa đăng ký default qua auto-configuration vừa đánh dấu `DefaultWidgetService` bằng `@Component`. Component scan có thể tạo default vô điều kiện và làm mất ý nghĩa back-off.

## 8. Đăng ký properties mà không cần ConfigurationPropertiesScan

Một class `@ConfigurationProperties` không tự trở thành bean chỉ vì có annotation. Auto-configuration nên đăng ký tường minh các properties class:

~~~java
@AutoConfiguration
@EnableConfigurationProperties({
        WidgetProperties.class,
        WidgetRetryProperties.class
})
public class WidgetAutoConfiguration {
}
~~~

Ứng dụng cấu hình qua `application.yml` hoặc `application.properties`; binder đọc từ `Environment`. Consumer không phải viết `@ConfigurationPropertiesScan("com.acme.widget")`.

Phân biệt:
- `@ConfigurationProperties` định nghĩa prefix và cấu trúc dữ liệu.
- `@EnableConfigurationProperties` đăng ký các class cụ thể làm bean và bật binding.
- `@ConfigurationPropertiesScan` là cơ chế scan riêng cho ứng dụng muốn tự tìm nhiều properties class; thư viện auto-configure không cần buộc consumer bật cơ chế đó.

Nếu thư viện có nhiều properties class, liệt kê chúng trên auto-configuration phù hợp. Với properties của tích hợp tùy chọn, có thể đăng ký trong cấu hình con có condition riêng.

## 9. Phân biệt @AutoConfigurationPackage với component scan

Tên hai cơ chế dễ gây nhầm:

- `@AutoConfiguration` đánh dấu class cấu hình tự động.
- `@AutoConfigurationPackage` đăng ký package gốc mà một số auto-configured feature của Boot dùng làm cơ sở tìm entity hoặc repository.
- `@ComponentScan` tìm các Spring component và configuration class trong package được chỉ định.

`@AutoConfigurationPackage` **không** thay component scan để đăng ký mọi `@Component` của thư viện. Nó cũng không có nghĩa mọi bean trong package sẽ được tạo.

Nếu thư viện cần helper bean, dùng `@Bean`, `@Import` hoặc registrar. Đừng dựa vào việc package được thêm vào danh sách auto-configuration packages để mọi class trong đó tự trở thành bean.

## 10. Kiểm thử: consumer không scan package thư viện vẫn nhận được bean

`ApplicationContextRunner` có thể chạy một context dùng `@EnableAutoConfiguration` nhưng **không có `@ComponentScan`**. Auto-configuration của thư viện được phát hiện từ descriptor imports trên test runtime classpath.

Test dưới đây dùng Java 17+, Spring Boot 3.3, JUnit 5 và AssertJ.

File `src/test/java/com/example/application/LibraryAutoConfigurationDiscoveryTest.java`:

~~~java
package com.example.application;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import com.acme.widget.DefaultWidgetService;
import com.acme.widget.WidgetProperties;
import com.acme.widget.WidgetService;
import com.acme.widget.autoconfigure.WidgetAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class LibraryAutoConfigurationDiscoveryTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(ApplicationConfiguration.class);

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class ApplicationConfiguration {
        // Cố ý không khai báo @ComponentScan.
    }

    @Test
    void libraryBeansAreDiscoveredWithoutComponentScanning() {
        runner.withPropertyValues(
                "acme.widget.endpoint=https://api.example.test")
                .run(context -> {
                    assertThat(context).hasSingleBean(WidgetProperties.class);
                    assertThat(context).hasSingleBean(WidgetService.class);
                    assertThat(context).hasSingleBean(DefaultWidgetService.class);
                    assertThat(context.getBean(WidgetService.class).endpoint())
                            .isEqualTo("https://api.example.test");
                });
    }

    @Test
    void applicationBeanReplacesLibraryDefault() {
        runner.withUserConfiguration(CustomWidgetConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(WidgetService.class);
                    assertThat(context).hasSingleBean(CustomWidgetService.class);
                    assertThat(context).doesNotHaveBean(DefaultWidgetService.class);
                    assertThat(context.getBean(WidgetService.class).endpoint())
                            .isEqualTo("custom://application");
                });
    }

    @Test
    void publishedImportsDescriptorNamesAutoConfiguration()
            throws IOException {

        String path =
                "META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports";

        try (InputStream input =
                     getClass().getClassLoader().getResourceAsStream(path)) {

            assertThat(input).isNotNull();

            String imports = new String(
                    input.readAllBytes(), StandardCharsets.UTF_8);

            assertThat(imports.lines())
                    .contains(WidgetAutoConfiguration.class.getName());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomWidgetConfiguration {

        @Bean
        CustomWidgetService customWidgetService() {
            return new CustomWidgetService();
        }
    }

    static final class CustomWidgetService implements WidgetService {
        @Override
        public String endpoint() {
            return "custom://application";
        }
    }
}
~~~

Test thứ nhất là bằng chứng chính: cấu hình ứng dụng chỉ bật `@EnableAutoConfiguration`, không bật component scan. Nếu `WidgetService` và `WidgetProperties` vẫn xuất hiện, thư viện được nạp qua auto-configuration mechanism.

Test thứ hai chứng minh bean người dùng được giữ và default back off. Test thứ ba kiểm tra descriptor thực sự nằm trên test runtime classpath và liệt kê đúng auto-configuration class.

Chạy bằng Gradle:

~~~bash
./gradlew test --tests "com.example.application.LibraryAutoConfigurationDiscoveryTest"
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.application.LibraryAutoConfigurationDiscoveryTest"
~~~

**Kết quả kỳ vọng:** 3 test PASS. Các assertion kiểm tra bean registration, binding và descriptor, không phụ thuộc stdout cố định. Đây là ví dụ test đã được rà soát, chưa được thực thi trong project cụ thể ở lượt soạn bài này.

## 11. Xác minh file imports trong JAR phát hành

Test context có thể chạy tốt trong IDE nhưng JAR phát hành lại thiếu descriptor nếu resource không được đóng gói. Kiểm tra artifact sau khi build.

Với Gradle:

~~~bash
./gradlew :acme-widget-autoconfigure:jar
jar tf acme-widget-autoconfigure/build/libs/acme-widget-autoconfigure-1.0.0.jar
~~~

Output phải có đường dẫn:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Lọc nhanh trên Windows:

~~~powershell
jar tf acme-widget-autoconfigure/build/libs/acme-widget-autoconfigure-1.0.0.jar |
    Select-String "AutoConfiguration.imports"
~~~

Sau đó xác nhận:
- Nội dung descriptor có đúng tên class đầy đủ và đúng package.
- Starter có dependency tới module autoconfigure.
- Module autoconfigure nằm trên runtime classpath của ứng dụng.
- Không có exclude hoặc `spring.autoconfigure.exclude` loại class cấu hình.

## 12. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Ứng dụng phải thêm `@ComponentScan("com.acme.widget")` mới có bean | Thư viện dựa vào stereotype scan thay vì auto-configuration | Tạo auto-configuration và file imports; dùng `@Bean`/`@Import` |
| Class có `@AutoConfiguration` nhưng không chạy | Thiếu hoặc sai file `AutoConfiguration.imports` | Kiểm tra resource trong JAR và class name |
| IDE test pass nhưng ứng dụng sau publish không tìm thấy cấu hình | Resource không được đóng gói hoặc starter thiếu dependency autoconfigure | Kiểm tra JAR và dependency runtime |
| Properties có nhưng service không có | Condition trên bean method không khớp hoặc dependency không có | Xem Condition Evaluation Report và test từng condition |
| Có hai bean default sau khi thêm scan | Default vừa được scan như component vừa được tạo bằng `@Bean` | Chỉ giữ một đường đăng ký default |
| Descriptor có class nhưng không có bean | Auto-configuration bị exclude hoặc condition cấp class không khớp | Kiểm tra `--debug` và điều kiện classpath/property/bean |
| Thư viện đổi package làm app lỗi | Consumer hardcode package thư viện trong `@ComponentScan` hoặc `@Import` | Giữ scan của app độc lập; cập nhật descriptor trong artifact |
| Helper class không được đăng ký | Chưa `@Import` hoặc khai báo bean helper | Import configuration hỗ trợ hoặc khai báo `@Bean` |
| Properties vẫn ở giá trị mặc định | Properties class chưa được enable/scan | Dùng `@EnableConfigurationProperties` |
| Bean trùng hoặc cấu hình chạy hai lần | Nạp cùng cấu hình qua nhiều đường không cần thiết | Dùng descriptor làm đường auto-configuration chuẩn |

Bật `--debug` hoặc `debug=true` để xem Condition Evaluation Report. Nếu auto-configuration không xuất hiện, kiểm tra imports file và runtime classpath. Nếu xuất hiện nhưng là negative match, đọc condition cụ thể. Nếu class match nhưng bean method không tạo bean, kiểm tra condition ở method hoặc cấu hình con.

Với Actuator, `/actuator/conditions` có thể hiển thị condition evaluation khi endpoint được expose phù hợp. Không mở endpoint nhạy cảm ra môi trường công khai chỉ để debug.

## 13. Nguyên tắc thiết kế thư viện có auto-configuration

- **Đặt auto-configuration trong package riêng**, ví dụ `com.acme.widget.autoconfigure`, để phân biệt API, implementation và cấu hình tích hợp.
- **Đăng ký qua `AutoConfiguration.imports`** trong JAR; không yêu cầu consumer scan package thư viện.
- **Không đặt `@ComponentScan` trong auto-configuration** để quét package nội bộ. Dùng `@Import` cho nhóm cấu hình cần thiết.
- **Dùng `@Bean` cho default bean** và `@ConditionalOnMissingBean` để người dùng override.
- **Dùng `@EnableConfigurationProperties`** để đăng ký properties class mà không buộc ứng dụng chạy configuration property scan.
- **Dùng conditions** để tích hợp tùy chọn chỉ bật khi dependency có mặt hoặc property thỏa mãn.
- **Giữ starter gọn:** starter gom dependency; module autoconfigure sở hữu metadata và cấu hình.
- **Test như consumer độc lập:** dùng package ứng dụng khác với package thư viện và không component-scan thư viện.
- **Kiểm tra JAR phát hành:** xác minh imports resource, class name và dependency runtime.
- **Giữ API ổn định:** consumer phụ thuộc starter, public SPI và properties đã công bố; không dựa vào package implementation.

Mô hình tổng quát:

~~~mermaid
flowchart TD
    A["Ứng dụng thêm starter"] --> B["Autoconfigure JAR trên runtime classpath"]
    B --> C["@EnableAutoConfiguration"]
    C --> D["Đọc AutoConfiguration.imports"]
    D --> E["Nạp WidgetAutoConfiguration"]
    E --> F["@Import cấu hình hỗ trợ"]
    F --> G["@EnableConfigurationProperties"]
    F --> H["@Bean + conditions"]
    G --> I["WidgetProperties bean"]
    H --> J["WidgetService bean"]
    I --> J
    J --> K["Ứng dụng inject WidgetService"]
~~~

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): auto-configuration trong external JAR, `AutoConfiguration.imports`, không dùng component scan trong auto-configuration và cách dùng `@Import`.
- [Spring Boot 3.3 — `@AutoConfiguration` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): annotation và metadata auto-configuration.
- [Spring Boot 3.3 — `@EnableAutoConfiguration` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html): kích hoạt cơ chế auto-configuration của ứng dụng.
- [Spring Boot 3.3 — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): kiểm thử context kết hợp user configuration và auto-configuration bằng `ApplicationContextRunner`.
- [Spring Framework — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): phạm vi và cơ chế component scan.

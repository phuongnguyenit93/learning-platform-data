# `@EnableWebMvc` và tác động đến cơ chế cấu hình mặc định của Spring Boot

Trong một ứng dụng Spring Boot dùng Spring MVC, annotation `@EnableWebMvc` có tác động lớn hơn việc “bật MVC”. Nó yêu cầu Spring Framework nhập cấu hình MVC Java mặc định của chính Spring. Vì cấu hình này tạo ra một bean thuộc kiểu `WebMvcConfigurationSupport`, điều kiện của `WebMvcAutoConfiguration` trong Spring Boot không còn khớp. Kết quả là **Spring Boot nhường quyền cấu hình MVC cho ứng dụng**.

Đây là điểm cốt lõi cần nhớ:

- Muốn **giữ cấu hình MVC mặc định của Boot** và chỉ thêm interceptor, formatter, CORS, resource handler hoặc view controller: đăng ký bean `WebMvcConfigurer`, **không thêm `@EnableWebMvc`**.
- Muốn **tự chịu trách nhiệm cấu hình Spring MVC** và không cần các tùy chỉnh MVC riêng của Boot: dùng `@EnableWebMvc` có chủ đích.
- Muốn thay một số thành phần cốt lõi như `RequestMappingHandlerMapping`, `RequestMappingHandlerAdapter` hoặc `ExceptionHandlerExceptionResolver` nhưng vẫn giữ Boot MVC auto-configuration: xem `WebMvcRegistrations`.

## 1. `@EnableWebMvc` thực sự nhập cấu hình nào?

Annotation nằm trong package:

```java
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
```

Khi một lớp cấu hình có `@EnableWebMvc`, Spring Framework nhập `DelegatingWebMvcConfiguration`:

```java
@Configuration(proxyBeanMethods = false)
@EnableWebMvc
public class MyWebConfiguration {
}
```

Đây là một cấu hình Spring MVC Java đầy đủ. `DelegatingWebMvcConfiguration` kế thừa `WebMvcConfigurationSupport` và phát hiện các bean kiểu `WebMvcConfigurer` để ủy quyền các tùy chỉnh vào cấu hình MVC.

Quan hệ kế thừa có thể hình dung:

```text
@EnableWebMvc
     |
     | @Import
     v
DelegatingWebMvcConfiguration
     |
     | extends
     v
WebMvcConfigurationSupport
     |
     v
Đăng ký hạ tầng Spring MVC:
HandlerMapping, HandlerAdapter,
exception resolvers, conversion service,
validator, message converters...
```

Vì vậy, sau khi `@EnableWebMvc` được xử lý, BeanFactory đã có bean cấu hình mang kiểu `WebMvcConfigurationSupport` (thực tế là lớp con `DelegatingWebMvcConfiguration`). Chính kiểu này là tín hiệu khiến Spring Boot biết rằng ứng dụng đã tự cung cấp cấu hình MVC.

Lưu ý: `@EnableWebMvc` không chỉ tạo một bean `WebMvcConfigurer`. Nó nhập **một lớp cấu hình nền tảng** của Spring MVC. Đây là khác biệt quan trọng giữa `@EnableWebMvc` và việc chỉ khai báo một bean `WebMvcConfigurer`.

## 2. Vì sao Spring Boot MVC auto-configuration back off?

Trong Spring Boot 3.3, `WebMvcAutoConfiguration` có các điều kiện cấp lớp quan trọng:

```java
@AutoConfiguration(after = {
        DispatcherServletAutoConfiguration.class,
        TaskExecutionAutoConfiguration.class,
        ValidationAutoConfiguration.class
})
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
@ConditionalOnClass({
        Servlet.class,
        DispatcherServlet.class,
        WebMvcConfigurer.class
})
@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)
@AutoConfigureOrder(Ordered.HIGHEST_PRECEDENCE + 10)
public class WebMvcAutoConfiguration {
    // ...
}
```

Đây là trích đoạn rút gọn theo API Spring Boot 3.3. Ba điều kiện chính nói rằng:

1. Ứng dụng phải là **Servlet web application**.
2. Các lớp cần thiết của Servlet và Spring MVC phải có trên classpath.
3. Chưa có bean kiểu `WebMvcConfigurationSupport` trong phạm vi tìm kiếm của condition.

Điều kiện thứ ba giải thích tác động của `@EnableWebMvc`:

- Không có `@EnableWebMvc`: nếu hai điều kiện web và classpath cũng khớp, chưa có `WebMvcConfigurationSupport` nên `WebMvcAutoConfiguration` được áp dụng.
- Có `@EnableWebMvc`: `DelegatingWebMvcConfiguration` đã được nhập; lớp này là subclass của `WebMvcConfigurationSupport`. Vì thế `@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)` không khớp và `WebMvcAutoConfiguration` **rút lui**.

Đây là cơ chế conditional backoff của Spring Boot. Boot không cần xóa cấu hình MVC do Spring Framework đã đăng ký và cũng không ghi đè cấu hình đó. Nó đơn giản **không áp dụng auto-configuration MVC mặc định của mình** khi phát hiện ứng dụng đã cung cấp nền tảng MVC.

### Sơ đồ hai trường hợp

```text
TRƯỜNG HỢP A — Không có @EnableWebMvc
  User configuration
       |
       v
  Chưa có WebMvcConfigurationSupport
       |
       v
  WebMvcAutoConfiguration condition khớp
       |
       v
  Boot đăng ký MVC adapter + tùy chỉnh Boot
       |
       v
  Spring MVC chạy với cấu hình mặc định của Boot

TRƯỜNG HỢP B — Có @EnableWebMvc
  User configuration
       |
       v
  @EnableWebMvc imports DelegatingWebMvcConfiguration
       |
       v
  Đã có WebMvcConfigurationSupport
       |
       v
  WebMvcAutoConfiguration condition không khớp
       |
       v
  Boot MVC auto-configuration back off
       |
       v
  Ứng dụng tự chịu trách nhiệm cấu hình MVC
```

Điều kiện class-level này cũng có nghĩa là **một cấu hình tự viết kế thừa trực tiếp `WebMvcConfigurationSupport`** có thể làm Boot MVC auto-configuration back off ngay cả khi không dùng annotation `@EnableWebMvc`.

## 3. Những thay đổi thực tế khi thêm `@EnableWebMvc`

`@EnableWebMvc` không làm Spring MVC biến mất. Nó chuyển quyền thiết lập MVC từ adapter của Boot sang cấu hình Spring Framework do ứng dụng kích hoạt.

### 3.1. Những tính năng MVC bổ sung của Boot không còn được tự động áp dụng

Theo tài liệu Spring Boot, `WebMvcAutoConfiguration` bổ sung nhiều tính năng bên cạnh mặc định của Spring MVC:

| Tính năng do Boot MVC auto-configuration cung cấp | Khi `@EnableWebMvc` khiến auto-config back off |
| --- | --- |
| `ContentNegotiatingViewResolver` và `BeanNameViewResolver` | Không còn được thêm bởi MVC adapter mặc định của Boot; nếu cần, ứng dụng tự đăng ký và sắp thứ tự view resolver. |
| Static resource handling, WebJars và static `index.html` welcome page | Không nên giả định các mapping và welcome-page behavior mặc định của Boot còn tồn tại; tự cấu hình resource handler khi cần. |
| Tự động đăng ký các bean `Converter`, `GenericConverter` và `Formatter` | Cần cấu hình các formatter/converter phù hợp trong MVC. |
| Tích hợp `HttpMessageConverters` với MVC | Cần xác định cách xây dựng và đăng ký converter mà ứng dụng mong muốn. |
| Tự động đăng ký `MessageCodesResolver` theo cấu hình Boot | Nếu cần định dạng message code riêng, ứng dụng tự cấu hình. |
| Dùng `ConfigurableWebBindingInitializer` tùy chỉnh nếu có bean phù hợp | Cần tự kiểm soát data binding initializer trong cấu hình MVC. |
| Các thiết lập MVC mà adapter Boot đọc từ `WebMvcProperties`/`WebProperties` | Không nên giả định các property này vẫn được áp dụng vào MVC theo cách của auto-configuration. |

Điểm cần phân biệt: một số auto-configuration khác của Boot có thể vẫn đăng ký bean liên quan tới HTTP, validation, lỗi hoặc Jackson. Bảng trên nói về các **tùy chỉnh được `WebMvcAutoConfiguration` cung cấp cho Spring MVC**. Không nên suy rộng thành “tất cả auto-configuration của Boot đều bị tắt”.

Ví dụ, `@EnableWebMvc` không tự tắt:

- `@EnableAutoConfiguration` bên trong `@SpringBootApplication`.
- Cấu hình embedded Servlet container như Tomcat/Jetty/Undertow.
- Cơ chế đăng ký `DispatcherServlet` của `DispatcherServletAutoConfiguration`.
- Các auto-configuration độc lập khác, miễn điều kiện riêng của chúng vẫn khớp.

Các controller `@Controller`/`@RestController` vẫn có thể được Spring MVC xử lý. Ứng dụng vẫn là Servlet web application; phần thay đổi là cách cấu hình MVC.

### 3.2. Những lỗi thường thấy sau khi thêm annotation

- URL tĩnh như `/css/app.css` hoặc tài nguyên WebJars trả 404.
- `index.html` không còn được nhận diện như welcome page theo quy tắc Boot.
- `spring.mvc.format.*` hoặc `spring.mvc.contentnegotiation.*` không tạo ra hành vi như trước.
- Converter/formatter tự khai báo không được đăng ký theo đúng đường cấu hình kỳ vọng.
- View resolver mặc định của Boot không xuất hiện hoặc thứ tự resolver thay đổi.
- Một `HttpMessageConverter` tùy chỉnh thay đổi danh sách converter ngoài dự kiến.

Khi gặp các triệu chứng này, hãy kiểm tra xem có lớp cấu hình nào dùng `@EnableWebMvc` hoặc kế thừa `WebMvcConfigurationSupport` không. Nếu có, điều tra đường cấu hình MVC thủ công trước khi thêm property hoặc bean để “sửa” từng lỗi riêng lẻ.

## 4. Cách tùy chỉnh MVC mà vẫn giữ cấu hình mặc định của Boot

Đây là lựa chọn phù hợp với đa số ứng dụng Spring Boot. Chỉ cần khai báo bean `WebMvcConfigurer`:

```java
package demo.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcCustomization {

    @Bean
    WebMvcConfigurer mvcConfigurer() {
        return new WebMvcConfigurer() {

            @Override
            public void addInterceptors(InterceptorRegistry registry) {
                registry.addInterceptor(new RequestAuditInterceptor())
                        .addPathPatterns("/api/**");
            }

            @Override
            public void addCorsMappings(CorsRegistry registry) {
                registry.addMapping("/api/**")
                        .allowedMethods("GET", "POST", "PUT", "DELETE");
            }
        };
    }
}
```

`RequestAuditInterceptor` là class do ứng dụng tự định nghĩa, triển khai `HandlerInterceptor`. Đoạn code minh họa hai điểm mở rộng; trong dự án thực tế, hãy cấu hình origin CORS cụ thể theo chính sách của ứng dụng.

Không có `@EnableWebMvc` ở đây. Bean `WebMvcConfigurer` được Boot MVC configuration phát hiện và ủy quyền. Do đó:

- `WebMvcConfigurationSupport` vẫn được tạo bởi cấu hình MVC của Boot.
- `@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)` vẫn khớp.
- `WebMvcAutoConfiguration` tiếp tục đăng ký các tính năng mặc định của Boot.
- Các phương thức tùy chỉnh như `addInterceptors`, `addCorsMappings`, `addFormatters`, `addResourceHandlers` và `addViewControllers` được áp dụng cùng cấu hình mặc định.

Có thể khai báo nhiều bean `WebMvcConfigurer` để chia cấu hình theo module. Spring MVC sẽ phát hiện và gọi các configurer. Nếu thứ tự giữa chúng có ý nghĩa, có thể áp dụng `@Order` hoặc `Ordered` cho từng configurer và kiểm thử kết quả.

### Ví dụ ngắn: thêm formatter mà không bật lại MVC thủ công

```java
@Configuration(proxyBeanMethods = false)
public class DateMvcConfiguration {

    @Bean
    WebMvcConfigurer dateFormatterConfigurer() {
        return new WebMvcConfigurer() {
            @Override
            public void addFormatters(FormatterRegistry registry) {
                registry.addFormatter(new LocalDateFormatter());
            }
        };
    }
}
```

`LocalDateFormatter` là formatter của ứng dụng cần được định nghĩa riêng. Với cách này, Boot vẫn giữ cấu hình MVC mặc định và gọi thêm formatter tùy chỉnh.

## 5. Khi cần thay component cốt lõi: dùng `WebMvcRegistrations`

Đôi khi ứng dụng muốn cung cấp implementation riêng của một số thành phần Spring MVC, nhưng vẫn muốn giữ các tùy chỉnh khác của Boot. Không nhất thiết phải chuyển sang `@EnableWebMvc`.

Spring Boot có extension point `WebMvcRegistrations` cho các thành phần:

- `RequestMappingHandlerMapping`
- `RequestMappingHandlerAdapter`
- `ExceptionHandlerExceptionResolver`

Ví dụ minh họa:

```java
import org.springframework.boot.autoconfigure.web.servlet.WebMvcRegistrations;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

@Configuration(proxyBeanMethods = false)
public class CustomMvcComponents {

    @Bean
    WebMvcRegistrations webMvcRegistrations() {
        return new WebMvcRegistrations() {
            @Override
            public RequestMappingHandlerMapping
                    getRequestMappingHandlerMapping() {
                return new CustomRequestMappingHandlerMapping();
            }
        };
    }
}
```

`CustomRequestMappingHandlerMapping` là class do ứng dụng tự viết và cần kế thừa/triển khai phù hợp với API Spring Framework đang dùng. Đoạn trên chỉ minh họa extension point; không cần thay mapping class nếu chỉ muốn thêm interceptor hoặc formatter.

Boot vẫn tạo MVC auto-configuration và đưa component tùy chỉnh vào quá trình khởi tạo. Đây là lựa chọn tốt khi cần thay một thành phần lõi nhưng vẫn muốn các cấu hình resource, converter, view resolver và property của Boot tiếp tục được áp dụng.

## 6. Khi nào nên dùng `@EnableWebMvc`?

Chỉ nên dùng khi ứng dụng thật sự muốn **kiểm soát đầy đủ cấu hình Spring MVC**.

Ví dụ:

- Framework nội bộ đã có một bộ MVC configuration hoàn chỉnh.
- Ứng dụng cần thay đổi sâu cách đăng ký handler mapping, adapter, exception resolver và các bean hạ tầng.
- Ứng dụng không muốn phụ thuộc vào các MVC default và property mapping riêng của Boot.
- Đội ngũ vận hành muốn sở hữu toàn bộ chính sách resource handler, converter, formatter, view resolver, content negotiation và data binding.

Cấu hình thủ công có thể bắt đầu:

```java
@Configuration(proxyBeanMethods = false)
@EnableWebMvc
public class FullControlMvcConfiguration implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/assets/**")
                .addResourceLocations("classpath:/assets/");
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addFormatter(new LocalDateFormatter());
    }
}
```

Trong ví dụ này, ứng dụng tự khai báo mapping tài nguyên `/assets/**` và formatter. Nếu còn cần WebJars, welcome page, resolver, converter, CORS hoặc các cấu hình khác, hãy đăng ký rõ ràng theo yêu cầu thực tế.

Spring Framework lưu ý chỉ nên có **một lớp cấu hình** dùng `@EnableWebMvc` để nhập cấu hình MVC. Có thể có nhiều lớp khác triển khai `WebMvcConfigurer` để chia nhỏ tùy chỉnh. `DelegatingWebMvcConfiguration` sẽ phát hiện các configurer này.

### Phân biệt với WebFlux

`@EnableWebMvc` dành cho **Spring MVC/Servlet**. Với ứng dụng Spring WebFlux, annotation tương ứng là `@EnableWebFlux` và extension point là `WebFluxConfigurer`. Hai stack có cơ chế cấu hình riêng; không dùng `@EnableWebMvc` để tùy chỉnh Reactive web application.

## 7. Thí nghiệm tối thiểu: kiểm chứng condition của Boot bằng `WebApplicationContextRunner`

Ta có thể chứng minh tác động của annotation mà không cần chạy embedded server. `WebApplicationContextRunner` tạo một Servlet `WebApplicationContext` có `MockServletContext`. Ta nạp trực tiếp `WebMvcAutoConfiguration` rồi so sánh ba trường hợp:

1. Không có cấu hình MVC của người dùng: Boot auto-configuration khớp.
2. Người dùng bật `@EnableWebMvc`: Boot auto-configuration không khớp.
3. Người dùng chỉ đăng ký `WebMvcConfigurer`: Boot auto-configuration vẫn khớp.

Thí nghiệm đọc `ConditionEvaluationReport` để kiểm tra đúng condition ở class-level, đồng thời kiểm tra bean `WebMvcConfigurationSupport` và `WebMvcProperties`.

### 7.1. Cấu trúc dự án

```text
enable-webmvc-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── EnableWebMvcAutoConfigurationTest.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>enable-webmvc-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

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
</project>
```

### 7.2. File test hoàn chỉnh

Tạo `src/test/java/demo/EnableWebMvcAutoConfigurationTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.web.servlet.WebMvcAutoConfiguration;
import org.springframework.boot.autoconfigure.web.servlet.WebMvcProperties;
import org.springframework.boot.test.context.assertj.AssertableWebApplicationContext;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurationSupport;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import static org.assertj.core.api.Assertions.assertThat;

class EnableWebMvcAutoConfigurationTest {

    private final WebApplicationContextRunner runner =
            new WebApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            WebMvcAutoConfiguration.class
                    ));

    private static ConditionEvaluationReport.ConditionAndOutcomes
    bootMvcOutcomes(AssertableWebApplicationContext context) {
        return ConditionEvaluationReport.get(context.getBeanFactory())
                .getConditionAndOutcomesBySource()
                .get(WebMvcAutoConfiguration.class.getName());
    }

    @Test
    void bootMvcAutoConfigurationMatchesWithoutEnableWebMvc() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(WebMvcConfigurationSupport.class);
            assertThat(context).hasSingleBean(WebMvcProperties.class);

            assertThat(bootMvcOutcomes(context)).isNotNull();
            assertThat(bootMvcOutcomes(context).isFullMatch()).isTrue();
        });
    }

    @Test
    void enableWebMvcMakesBootMvcAutoConfigurationBackOff() {
        runner.withUserConfiguration(ManualMvcConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasSingleBean(WebMvcConfigurationSupport.class);

                    assertThat(context).doesNotHaveBean(WebMvcProperties.class);

                    assertThat(bootMvcOutcomes(context)).isNotNull();
                    assertThat(bootMvcOutcomes(context).isFullMatch()).isFalse();
                });
    }

    @Test
    void webMvcConfigurerAloneKeepsBootMvcAutoConfiguration() {
        runner.withUserConfiguration(MvcCustomizerConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(WebMvcConfigurationSupport.class);
                    assertThat(context).hasSingleBean(WebMvcProperties.class);
                    assertThat(context).hasBean("customMvcConfigurer");

                    assertThat(bootMvcOutcomes(context)).isNotNull();
                    assertThat(bootMvcOutcomes(context).isFullMatch()).isTrue();
                });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableWebMvc
    static class ManualMvcConfiguration {
    }

    @Configuration(proxyBeanMethods = false)
    static class MvcCustomizerConfiguration {

        @Bean
        WebMvcConfigurer customMvcConfigurer() {
            return new WebMvcConfigurer() {
            };
        }
    }
}
```

Chạy từ thư mục `enable-webmvc-demo` bằng JDK 17+ và Maven:

```bash
mvn test
```

**Kết quả kỳ vọng:** ba test thành công.

| Test | Bean/configuration quan sát được | Kết quả condition của `WebMvcAutoConfiguration` |
| --- | --- | --- |
| `bootMvcAutoConfigurationMatchesWithoutEnableWebMvc` | Boot cung cấp `WebMvcConfigurationSupport` và `WebMvcProperties` | Full match: `true` |
| `enableWebMvcMakesBootMvcAutoConfigurationBackOff` | Spring Framework cung cấp `WebMvcConfigurationSupport`; Boot MVC properties adapter không được đăng ký bởi auto-config này | Full match: `false` |
| `webMvcConfigurerAloneKeepsBootMvcAutoConfiguration` | Có bean `customMvcConfigurer` và Boot vẫn cung cấp MVC configuration/properties | Full match: `true` |

`ConditionEvaluationReport` nhóm condition theo source. Source ở đây là tên đầy đủ của class `WebMvcAutoConfiguration`. `isFullMatch()` trả `true` khi tất cả condition ghi cho source đó khớp. Trong test thứ hai, condition missing bean không khớp vì `@EnableWebMvc` đã nhập lớp con của `WebMvcConfigurationSupport`.

Test dùng `WebApplicationContextRunner` vì condition của Boot yêu cầu Servlet web application. Nếu dùng `ApplicationContextRunner` thông thường, điều kiện `@ConditionalOnWebApplication(type = SERVLET)` sẽ không khớp và ta không kiểm tra được đúng nguyên nhân đang nghiên cứu.

Các test được thiết kế để cô lập **quyết định auto-configuration**. Chúng không khởi chạy server HTTP thật và không chứng minh mọi route/static resource trong ứng dụng production hoạt động; muốn kiểm tra request thực tế, hãy bổ sung integration test với `@SpringBootTest(webEnvironment = RANDOM_PORT)`.

## 8. Chẩn đoán khi ứng dụng không còn nhận cấu hình MVC của Boot

### 8.1. Tìm nguồn khai báo `@EnableWebMvc`

Tìm trong source code:

- `@EnableWebMvc` trên các lớp `@Configuration`.
- Lớp cấu hình kế thừa `WebMvcConfigurationSupport` hoặc `DelegatingWebMvcConfiguration`.
- Cấu hình được import từ module dùng chung hoặc starter nội bộ.
- Cấu hình được component scan tự động phát hiện.

Đừng chỉ tìm trong lớp main application. Annotation có thể nằm trong module cấu hình được import gián tiếp.

### 8.2. Xem Condition Evaluation Report

Khởi động ứng dụng với:

```bash
java -jar app.jar --debug
```

Tìm source `WebMvcAutoConfiguration`. Nếu condition `@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)` không khớp, message sẽ cho biết bean kiểu nào đã được tìm thấy. Đây là bằng chứng trực tiếp rằng cấu hình MVC thủ công đang làm Boot back off.

Có thể kiểm tra bằng endpoint `/actuator/conditions` nếu Actuator được thêm và endpoint được expose an toàn. Không nên expose report cấu hình nội bộ ra mạng công khai.

### 8.3. Phân biệt lỗi của MVC với lỗi của Servlet container

Nếu `@EnableWebMvc` được thêm, nhưng:

- Ứng dụng vẫn khởi động và có embedded server: điều đó phù hợp, vì auto-configuration của Servlet container độc lập với `WebMvcAutoConfiguration`.
- Controller không được map: kiểm tra component scan, request mapping, context và cấu hình handler mapping.
- Static file 404: kiểm tra `addResourceHandlers`, resource location và path pattern.
- JSON converter khác trước: kiểm tra `HttpMessageConverter` thực tế trong `RequestMappingHandlerAdapter`.
- Format ngày giờ khác: kiểm tra `addFormatters` và cấu hình `ConversionService`.
- View resolver không tìm được template: kiểm tra các bean `ViewResolver`, thứ tự resolver và template engine.

Không nên quy mọi lỗi web sau khi thêm annotation cho DispatcherServlet hoặc embedded server. Trước tiên hãy xác định phần MVC auto-configuration nào đã back off.

## 9. Những nhầm lẫn phổ biến

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “`@EnableWebMvc` bật thêm vài feature mà Boot chưa có.” | Nó nhập cấu hình MVC của Spring Framework và khiến Boot MVC auto-configuration back off. |
| “Có `@EnableWebMvc` thì toàn bộ Spring Boot auto-configuration bị tắt.” | Chỉ `WebMvcAutoConfiguration` bị điều kiện missing bean chặn; các auto-configuration khác xét điều kiện riêng. |
| “Không có `@EnableWebMvc` thì không thể thêm interceptor hoặc formatter.” | Đăng ký `WebMvcConfigurer` bean là cách chuẩn để mở rộng MVC của Boot. |
| “`WebMvcConfigurer` cũng làm Boot back off.” | Không. Bean này không phải `WebMvcConfigurationSupport`. |
| “`@EnableWebMvc` tắt DispatcherServlet và embedded Tomcat.” | Không. Nó thay đổi cấu hình MVC; servlet container và DispatcherServlet có auto-configuration riêng. |
| “`spring.mvc.*` luôn bị bỏ qua hoàn toàn.” | Các property không được áp dụng qua MVC adapter đã back off; cần xác định property nào được component nào đọc. |
| “Muốn thay HandlerMapping phải bật `@EnableWebMvc`.” | Có thể dùng `WebMvcRegistrations` để thay một số component mà vẫn giữ Boot MVC auto-configuration. |
| “`@EnableWebMvc` là annotation của WebFlux.” | Không. WebFlux dùng `@EnableWebFlux` và `WebFluxConfigurer`. |
| “Có thể đặt `@EnableWebMvc` ở nhiều cấu hình để chia module.” | Chỉ nên có một lớp cấu hình nhập MVC qua annotation này; có thể có nhiều `WebMvcConfigurer`. |

## 10. Checklist chọn đúng cơ chế

Trước khi thêm annotation, tự hỏi:

1. Tôi chỉ muốn thêm interceptor, formatter, CORS, view controller hoặc resource handler? → Dùng `WebMvcConfigurer` bean.
2. Tôi cần thay một `RequestMappingHandlerMapping`, `RequestMappingHandlerAdapter` hoặc exception resolver nhưng muốn giữ cấu hình Boot? → Xem `WebMvcRegistrations`.
3. Tôi muốn tự quản lý đầy đủ MVC infrastructure, converter, resource handler, view resolver, binding và content negotiation? → `@EnableWebMvc` có thể phù hợp.
4. Tôi có đang vô tình kế thừa `WebMvcConfigurationSupport` hoặc import một cấu hình dùng `@EnableWebMvc` từ module khác không?
5. Sau khi thay đổi, tôi đã kiểm tra condition report, bean definitions và HTTP behavior chưa?

**Ghi nhớ:** `@EnableWebMvc` nhập `DelegatingWebMvcConfiguration`, một lớp con của `WebMvcConfigurationSupport`. Spring Boot 3.3 chỉ áp dụng `WebMvcAutoConfiguration` khi **chưa có** bean kiểu `WebMvcConfigurationSupport`. Vì thế, thêm `@EnableWebMvc` sẽ làm Boot MVC auto-configuration nhường chỗ và ứng dụng tự quản lý nhiều tùy chỉnh MVC. Nếu chỉ muốn mở rộng hành vi, hãy thêm `WebMvcConfigurer` mà không dùng `@EnableWebMvc`; nếu muốn thay một số component cốt lõi, xem `WebMvcRegistrations`.

### Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Servlet Web Applications / Spring MVC Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 API — `WebMvcAutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/servlet/WebMvcAutoConfiguration.html
- Spring Framework 6.1 — `@EnableWebMvc` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/servlet/config/annotation/EnableWebMvc.html
- Spring Framework 6.1 — `DelegatingWebMvcConfiguration` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/servlet/config/annotation/DelegatingWebMvcConfiguration.html
- Spring Framework 6.1 — `WebMvcConfigurationSupport` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurationSupport.html
- Spring Boot 3.3 API — `WebApplicationContextRunner`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/WebApplicationContextRunner.html
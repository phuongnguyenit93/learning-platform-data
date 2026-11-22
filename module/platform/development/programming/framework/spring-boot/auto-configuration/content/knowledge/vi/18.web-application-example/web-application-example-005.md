# WebMvcConfigurer để mở rộng cấu hình MVC đang có

## 1. Bài toán và nguyên tắc chính

Spring Boot tự cấu hình Spring MVC cho phần lớn ứng dụng Servlet: đăng ký DispatcherServlet, các HandlerMapping/HandlerAdapter, message converters, xử lý static resources, formatters và một số tiện ích khác. Khi ứng dụng cần thêm interceptor, CORS policy, formatter, resource handler hoặc view controller, ta thường chỉ cần **bổ sung một WebMvcConfigurer**.

Trong Spring Boot, cách làm phổ biến là:

```java
@Configuration(proxyBeanMethods = false)
public class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        // Đăng ký interceptor bổ sung.
    }
}
```

Điểm cần nhớ: **không thêm @EnableWebMvc** vào cấu hình trên nếu mục tiêu là giữ các tùy chỉnh MVC do Spring Boot cung cấp. WebMvcConfigurer là API callback để đóng góp cấu hình vào MVC infrastructure hiện có; nó không phải tín hiệu yêu cầu thay thế toàn bộ cấu hình mặc định.

@EnableWebMvc có mục đích khác: bật cấu hình MVC Java ở cấp Spring Framework để ứng dụng tự kiểm soát toàn bộ cấu hình. Trong Boot, annotation này đưa WebMvcConfigurationSupport vào context; WebMvcAutoConfiguration có điều kiện chỉ chạy khi chưa có bean kiểu đó, nên cấu hình MVC tự khai báo sẽ khiến auto-configuration của Boot back off.

## 2. WebMvcConfigurer nằm ở đâu trong Spring MVC?

WebMvcConfigurer thuộc package:

```java
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
```

Đây là interface có các phương thức mặc định (default methods). Ứng dụng chỉ override callback cần dùng. Không cần implement toàn bộ interface và không cần tự tạo DispatcherServlet, RequestMappingHandlerMapping hay RequestMappingHandlerAdapter cho các tùy chỉnh thông thường.

Có thể hình dung luồng xử lý như sau:

```text
HTTP request
     |
     v
Servlet filters (ví dụ Spring Security filter chain)
     |
     v
DispatcherServlet
     |
     v
HandlerMapping tìm controller/handler
     |
     +--> HandlerInterceptor.preHandle(...)
     |
     v
HandlerAdapter gọi controller
     |
     +--> argument resolvers / data binding / validation
     |
     v
Controller trả về kết quả
     |
     +--> HttpMessageConverter ghi response
     |
     v
HandlerInterceptor.afterCompletion(...)
     |
     v
HTTP response
```

Các callback WebMvcConfigurer đóng góp cấu hình cho những thành phần trong pipeline này. Ví dụ addInterceptors đăng ký interceptor với handler mappings; addFormatters thêm conversion/formatting; addCorsMappings khai báo CORS; extendMessageConverters sửa danh sách converter sau khi MVC đã thiết lập danh sách mặc định.

Không phải mọi extension point đều nằm cùng một tầng. Servlet Filter chạy trước DispatcherServlet; HandlerInterceptor chạy sau khi Spring MVC đã chọn handler. Cần chọn đúng tầng theo mục đích.

## 3. Vì sao Spring Boot khuyên dùng WebMvcConfigurer mà không dùng @EnableWebMvc?

### 3.1. Những gì Boot bổ sung

Spring Boot MVC auto-configuration xây trên Java MVC configuration của Spring Framework và bổ sung nhiều tiện ích, thường gồm:

- ContentNegotiatingViewResolver và BeanNameViewResolver khi phù hợp.
- Phục vụ static resources và WebJars.
- Tự đăng ký Converter, GenericConverter và Formatter beans.
- Tích hợp HttpMessageConverters.
- MessageCodesResolver và ConfigurableWebBindingInitializer theo cấu hình.
- Hỗ trợ static index.html.
- Các thuộc tính spring.mvc.* và spring.web.*.

Các tính năng cụ thể phụ thuộc classpath và cấu hình ứng dụng.

### 3.2. Cách giữ nguyên Boot defaults

Tạo một hoặc nhiều class @Configuration triển khai WebMvcConfigurer, không gắn @EnableWebMvc:

```java
@Configuration(proxyBeanMethods = false)
public class ApiMvcConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://ui.example.test")
                .allowedMethods("GET", "POST");
    }
}

@Configuration(proxyBeanMethods = false)
public class WebInterceptorConfiguration implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new RequestMarkerInterceptor())
                .addPathPatterns("/api/**");
    }
}
```

Các configurer cùng đóng góp vào MVC Java configuration. Tách chúng theo trách nhiệm giúp dễ đọc và dễ kiểm thử. Nếu có nhiều callback cùng sửa một cấu hình, hãy xem quy tắc thứ tự và tránh để nhiều nơi tranh nhau sửa cùng một giá trị.

### 3.3. Khi nào dùng @EnableWebMvc?

Dùng @EnableWebMvc khi ứng dụng Spring MVC thuần cần bật MVC Java configuration, hoặc khi ứng dụng Spring Boot **cố ý muốn tự chịu trách nhiệm toàn bộ cấu hình MVC** và không muốn dùng WebMvcAutoConfiguration.

Trong ứng dụng Boot, trước khi thêm annotation này, hãy xác định bạn có sẵn sàng tự cấu hình lại những phần Boot từng cung cấp hay không: static resources, message converters, formatters, view resolvers, binding initializer, content negotiation và các thuộc tính MVC.

Nếu chỉ muốn thay một thành phần đặc biệt như RequestMappingHandlerMapping, RequestMappingHandlerAdapter hoặc ExceptionHandlerExceptionResolver mà vẫn muốn giữ phần còn lại của Boot, hãy xem WebMvcRegistrations. Boot cho phép cung cấp các implementation tùy chỉnh qua hook này và tiếp tục áp dụng các bước cấu hình MVC thích hợp. Sau đó vẫn có thể dùng WebMvcConfigurer cho các callback còn lại.

## 4. Các callback thường dùng

Những nhóm dưới đây là các callback thường gặp trong Spring Framework 6.2 / Spring Boot 3.5.

| Nhu cầu | Callback | Ví dụ |
| --- | --- | --- |
| Thêm interceptor | addInterceptors | Request marker, locale hoặc đo thời gian xử lý |
| Cấu hình CORS toàn cục | addCorsMappings | Allowed origins/methods/headers |
| Thêm kiểu chuyển đổi/định dạng | addFormatters | Chuỗi sang value object, ngày giờ |
| Thêm static resource mapping | addResourceHandlers | /assets/** tới vị trí resource |
| Đăng ký view controller | addViewControllers | Forward trang đơn giản |
| Điều chỉnh path matching | configurePathMatch | Quy tắc matching URL |
| Content negotiation | configureContentNegotiation | Media type mặc định |
| Async MVC | configureAsyncSupport | Timeout và executor cho request async |
| View resolver | configureViewResolvers | Render template |
| Thêm converter vào danh sách hiện có | extendMessageConverters | JSON/XML converter |
| Mở rộng exception resolvers | extendHandlerExceptionResolvers | Resolver bổ sung |
| Thêm argument resolver riêng | addArgumentResolvers | Kiểu tham số controller tùy biến |
| Thêm return value handler riêng | addReturnValueHandlers | Kiểu kết quả controller tùy biến |

Một số callback quan trọng:

### 4.1. Interceptor

```java
@Override
public void addInterceptors(InterceptorRegistry registry) {
    registry.addInterceptor(new RequestMarkerInterceptor())
            .addPathPatterns("/api/**")
            .excludePathPatterns("/api/health");
}
```

- addPathPatterns giới hạn đường dẫn interceptor áp dụng.
- excludePathPatterns loại trừ đường dẫn.
- Có thể đăng ký nhiều interceptor và cấu hình thứ tự áp dụng.
- Interceptor thường là bean dùng chung; không lưu dữ liệu riêng của từng request vào field mutable của interceptor.

HandlerInterceptor có các callback preHandle, postHandle và afterCompletion. preHandle trả về false sẽ chặn việc gọi handler tiếp theo; ứng dụng phải tự hoàn tất response thích hợp. postHandle chạy sau controller nhưng trước khi view được render; với response body REST, nội dung thường được xử lý qua message converter trong giai đoạn trả response. afterCompletion phù hợp cho cleanup sau khi request hoàn tất.

**Không dùng HandlerInterceptor làm lớp bảo vệ authorization chính.** Spring Security filter chain chạy ở tầng Servlet filter trước MVC và có cơ chế bảo mật chuyên biệt. Interceptor chỉ xử lý request đã đi tới Spring MVC handler mapping; nó không bao phủ mọi loại request như một filter/security chain.

### 4.2. CORS

```java
@Override
public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/api/**")
            .allowedOrigins("https://ui.example.test")
            .allowedMethods("GET", "POST", "PUT")
            .allowedHeaders("Content-Type", "Authorization")
            .exposedHeaders("X-Request-Id")
            .allowCredentials(true)
            .maxAge(3600);
}
```

Cấu hình trên cho phép origin cụ thể truy cập các endpoint /api/**. Một số khái niệm:

- allowedOrigins: origin được phép; gồm scheme, host và port nếu có.
- allowedMethods: method được phép trong CORS.
- allowedHeaders: header client được phép gửi.
- exposedHeaders: header response mà JavaScript phía browser được phép đọc.
- allowCredentials: cho phép gửi credentials như cookie theo chính sách CORS.
- maxAge: thời gian browser có thể cache kết quả preflight.

Khi bật credentials, không dùng allowedOrigins("*"); hãy khai báo origin cụ thể hoặc cân nhắc allowedOriginPatterns với chính sách được kiểm soát. CORS là cơ chế browser kiểm soát việc JavaScript đọc response; nó không thay thế authentication/authorization và không chặn mọi client ngoài browser.

Nếu ứng dụng dùng Spring Security, cần tích hợp cấu hình CORS vào security chain phù hợp (ví dụ http.cors(...) cùng CorsConfigurationSource khi cần). Chỉ khai báo MVC CORS mà không xem thứ tự filter có thể chưa giải quyết được preflight bị chặn ở security layer.

### 4.3. Formatter và Converter

Dùng addFormatters khi controller cần chuyển một kiểu chuỗi sang kiểu domain hoặc định dạng dữ liệu:

```java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addConverter(String.class, RegionCode.class,
            source -> new RegionCode(source.trim().toUpperCase(Locale.ROOT)));
}
```

Đây là ví dụ minh họa; RegionCode là kiểu do ứng dụng định nghĩa. Converter<S,T> thường phù hợp cho chuyển đổi một chiều đơn giản. Formatter<T> phù hợp hơn khi cần cả parse và print theo locale.

Không đặt quy tắc nghiệp vụ phức tạp vào converter. Converter nên chuyển đổi representation; validation/domain service vẫn chịu trách nhiệm xác định dữ liệu có hợp lệ theo nghiệp vụ hay không.

### 4.4. Message converters

Message converter đọc request body và ghi response body, ví dụ JSON qua Jackson. Khi chỉ cần **bổ sung hoặc chỉnh danh sách converter hiện có**, ưu tiên extendMessageConverters:

```java
@Override
public void extendMessageConverters(
        List<HttpMessageConverter<?>> converters) {

    // Có thể tìm converter phù hợp trong danh sách và cấu hình nó,
    // hoặc thêm converter chuyên biệt vào vị trí phù hợp.
}
```

configureMessageConverters là callback cấu hình danh sách converter. Trong Spring MVC thuần, khi tự thêm converter qua method này, việc đăng ký default converters có thể bị tắt. Trong ứng dụng Boot, WebMvcAutoConfiguration còn đóng góp các converter beans và default converters; tuy vậy, nếu mục tiêu là chỉnh danh sách đã được dựng, extendMessageConverters thể hiện ý định rõ và giúp giữ các converter mặc định.

Thứ tự converter quan trọng: converter phù hợp sớm hơn có thể xử lý response trước, nhất là khi client gửi Accept: */*. Đừng thêm một converter quá rộng lên đầu danh sách nếu nó có thể chiếm các media type mà Jackson hoặc converter mặc định xử lý tốt.

Spring Boot cũng hỗ trợ đóng góp HttpMessageConverter dưới dạng bean và cơ chế HttpMessageConverters để tùy chỉnh converter ở cấp Boot. Nếu chỉ cần cấu hình ObjectMapper, hãy xem cơ chế Jackson/Boot tương ứng trước khi thay toàn bộ converter list.

### 4.5. Argument resolver và return value handler

addArgumentResolvers thêm resolver cho kiểu tham số tùy biến của controller. addReturnValueHandlers thêm handler cho kiểu kết quả tùy biến. Hai callback này **bổ sung** hỗ trợ; chúng không thay thế cơ chế built-in cho các tham số/kết quả đã được Spring MVC hỗ trợ.

Nếu cần thay đổi cách Spring xử lý các kiểu built-in, phải xem cấu hình chuyên sâu hơn của RequestMappingHandlerAdapter và cân nhắc tác động đến các resolver mặc định. Đừng override toàn bộ danh sách chỉ để xử lý một kiểu nhỏ.

## 5. Ví dụ runnable: thêm interceptor và CORS nhưng giữ JSON mặc định

Ví dụ dùng **Java 17 và Spring Boot 3.5.0**. Ứng dụng có endpoint trả JSON; WebMvcConfigurer thêm một interceptor đặt response header và một CORS policy cho frontend. Test dùng MockMvc xác nhận:

1. Endpoint vẫn serialize JSON bằng converter mặc định.
2. Interceptor được áp dụng cho /api/**.
3. Response có CORS header khi request gửi Origin được cho phép.

### Cấu trúc thư mục

```text
webmvc-configurer-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── WebMvcConfigurerDemoTest.java
```

### Tệp pom.xml

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
    <artifactId>webmvc-configurer-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>

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

### Tệp src/test/java/example/WebMvcConfigurerDemoTest.java

```java
package example;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = WebMvcConfigurerDemoTest.TestApplication.class)
@AutoConfigureMockMvc
class WebMvcConfigurerDemoTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void addsInterceptorAndKeepsDefaultJsonConversion() throws Exception {
        mockMvc.perform(get("/api/greeting")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(content()
                        .contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.message").value("Hello from MVC"))
                .andExpect(header().string("X-MVC-Extension", "active"));
    }

    @Test
    void appliesCorsPolicyForAllowedOrigin() throws Exception {
        mockMvc.perform(get("/api/greeting")
                        .header("Origin", "https://ui.example.test"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "Access-Control-Allow-Origin",
                        "https://ui.example.test"
                ));
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import({GreetingController.class, MvcExtensionConfiguration.class})
    public static class TestApplication {
    }

    public record Greeting(String message) {
    }

    @RestController
    public static class GreetingController {

        @GetMapping("/api/greeting")
        public Greeting greeting() {
            return new Greeting("Hello from MVC");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class MvcExtensionConfiguration
            implements WebMvcConfigurer {

        @Override
        public void addInterceptors(InterceptorRegistry registry) {
            registry.addInterceptor(new HandlerInterceptor() {
                @Override
                public boolean preHandle(
                        HttpServletRequest request,
                        HttpServletResponse response,
                        Object handler) {

                    response.setHeader("X-MVC-Extension", "active");
                    return true;
                }
            }).addPathPatterns("/api/**");
        }

        @Override
        public void addCorsMappings(CorsRegistry registry) {
            registry.addMapping("/api/**")
                    .allowedOrigins("https://ui.example.test")
                    .allowedMethods("GET");
        }
    }
}
```

### Chạy test

Tại thư mục chứa pom.xml, dùng JDK 17+ và Maven:

```bash
java -version
mvn -version
mvn test
```

**Kết quả mong đợi:** hai test JUnit pass và Maven kết thúc BUILD SUCCESS nếu dependency tải thành công. Code không gọi System.out.println, nên không có stdout nghiệp vụ cố định; báo cáo chi tiết nằm trong target/surefire-reports.

### Giải thích test

- addsInterceptorAndKeepsDefaultJsonConversion: xác nhận endpoint vẫn trả JSON và header do interceptor đặt. Đây là bằng chứng ứng dụng có thêm callback mà vẫn dùng MVC message conversion.
- appliesCorsPolicyForAllowedOrigin: gửi header Origin của frontend đã được allow và kiểm tra response có Access-Control-Allow-Origin.
- TestApplication dùng @EnableAutoConfiguration nhưng **không** dùng @EnableWebMvc. Do đó WebMvcAutoConfiguration vẫn tham gia context.
- MvcExtensionConfiguration chỉ override hai callback cần thiết; các callback còn lại giữ hành vi mặc định.

Ví dụ không mở server thật; MockMvc chạy request qua Spring MVC trong test context. Khi triển khai CORS cùng Spring Security, cần test thêm preflight OPTIONS và thứ tự security filters trong cấu hình thật.

## 6. Những điểm mở rộng khác nên biết

### 6.1. Static resources

Dùng addResourceHandlers khi cần ánh xạ một URL pattern tới vị trí tài nguyên:

```java
@Override
public void addResourceHandlers(ResourceHandlerRegistry registry) {
    registry.addResourceHandler("/manual/**")
            .addResourceLocations("classpath:/manual/");
}
```

Ví dụ này phục vụ tài nguyên nằm dưới src/main/resources/manual/ tại URL /manual/**. Hãy chú ý cache control, versioning, content type và phạm vi public của tài nguyên. Spring Boot vốn đã có static resource handling mặc định cho các location được hỗ trợ; chỉ thêm mapping khi có nhu cầu riêng.

### 6.2. View controllers

addViewControllers phù hợp với route đơn giản chỉ forward tới view mà không cần logic trong controller:

```java
@Override
public void addViewControllers(ViewControllerRegistry registry) {
    registry.addViewController("/help").setViewName("help");
}
```

Đoạn trên giả định ứng dụng có view tên help và một ViewResolver phù hợp. Nó không tự tạo template.

### 6.3. Path matching và content negotiation

configurePathMatch điều chỉnh cách Spring MVC khớp path. Trước khi đổi các quy tắc như trailing slash hoặc parsed PathPattern, hãy kiểm tra route hiện có, proxy/reverse proxy và các test tích hợp.

configureContentNegotiation kiểm soát cách MVC quyết định media type dựa trên request. Với REST API, ưu tiên Accept header và content type rõ ràng; tránh bật path extension negotiation nếu không có lý do tương thích cụ thể.

### 6.4. Async request handling

configureAsyncSupport cấu hình timeout và executor cho các controller trả về kiểu async như Callable hoặc DeferredResult. Không nhầm executor MVC async với executor của @Async hay scheduler; chúng có lifecycle và cấu hình riêng. Nếu cung cấp executor riêng, cần giới hạn tài nguyên, xử lý shutdown và theo dõi queue/latency.

### 6.5. Exception resolvers

extendHandlerExceptionResolvers phù hợp khi muốn bổ sung resolver sau danh sách mặc định. configureHandlerExceptionResolvers là callback cấu hình danh sách; khi tự thêm resolver, hãy hiểu cách default resolver registration bị ảnh hưởng. Với REST API, @RestControllerAdvice thường là lựa chọn dễ đọc cho xử lý exception theo controller/application hơn việc thay toàn bộ resolver chain.

## 7. Khi cần thay một MVC infrastructure component

Nếu nhu cầu vượt quá callback của WebMvcConfigurer, hãy cân nhắc theo thứ tự:

1. Có property hoặc bean extension point mà Boot cung cấp cho mục tiêu này không?
2. Có thể dùng WebMvcConfigurer callback tương ứng không?
3. Nếu cần thay một số component cốt lõi nhưng giữ phần Boot khác, xem WebMvcRegistrations.
4. Chỉ dùng @EnableWebMvc khi muốn tự kiểm soát toàn bộ MVC configuration.
5. Tránh tự khai báo WebMvcConfigurationSupport hoặc subclass infrastructure class khi chưa thực sự cần; nó có thể làm Boot auto-configuration back off.

WebMvcRegistrations là hook của Spring Boot để thay implementation RequestMappingHandlerMapping, RequestMappingHandlerAdapter hoặc ExceptionHandlerExceptionResolver. Các instance tùy chỉnh vẫn được MVC tiếp tục khởi tạo/cấu hình theo pipeline phù hợp. Đây là lựa chọn hẹp hơn việc tắt toàn bộ Boot MVC auto-configuration.

## 8. Phân biệt WebMvcConfigurer với Filter và WebFluxConfigurer

| Công cụ | Tầng | Khi phù hợp |
| --- | --- | --- |
| WebMvcConfigurer | Spring MVC / Servlet DispatcherServlet | Interceptor, CORS MVC, formatter, converter, view, path matching |
| Servlet Filter | Servlet container trước DispatcherServlet | Request/response wrapping, correlation id, cross-cutting HTTP processing |
| Spring Security SecurityFilterChain | Security filter chain | Authentication, authorization, security headers, CSRF |
| WebFluxConfigurer | Reactive Spring WebFlux | Router/handler reactive, codec, WebFlux CORS và các cấu hình reactive |

Không dùng WebMvcConfigurer trong ứng dụng WebFlux thuần; hai stack có API cấu hình khác nhau. Nếu ứng dụng có cả Servlet và Reactive dependency, hãy kiểm tra loại web application mà Boot đang chọn và test đúng stack.

## 9. Những lỗi thường gặp

1. **Thêm @EnableWebMvc chỉ để đăng ký interceptor.** Điều này có thể làm Boot MVC auto-configuration back off. Chỉ cần @Configuration implements WebMvcConfigurer.
2. **Subclass WebMvcConfigurationSupport mà không hiểu tác động.** Trong Boot, bean kiểu này khiến WebMvcAutoConfiguration không khớp điều kiện missing bean.
3. **Ghi đè configureMessageConverters để thêm một converter.** Có thể làm thay đổi việc đăng ký converter mặc định trong Spring MVC thuần. Ưu tiên extendMessageConverters hoặc converter bean/HttpMessageConverters trong Boot.
4. **Thêm converter quá rộng hoặc sai thứ tự.** Converter đứng trước có thể chiếm media type và thay đổi JSON/XML response. Kiểm tra Accept header và thứ tự converter.
5. **Dùng interceptor làm security layer.** Interceptor không bao phủ mọi request như filter chain; dùng Spring Security cho authorization.
6. **Cho phép CORS * cùng credentials.** CORS credentials cần origin policy cụ thể; không dùng wildcard origin với credentials.
7. **Quên CORS ở Spring Security layer.** Preflight có thể bị filter từ chối trước khi tới MVC.
8. **Lưu request state trong field interceptor singleton.** Nhiều request có thể chạy đồng thời; dùng request attributes hoặc biến cục bộ.
9. **Tạo interceptor nhưng không giới hạn path.** Nếu không chỉ định pattern, nó có thể áp dụng rộng hơn dự kiến, bao gồm route không liên quan.
10. **Thêm argument resolver để thay resolver built-in.** addArgumentResolvers là cơ chế bổ sung; để thay built-in support cần cấu hình adapter chuyên sâu hơn.
11. **Thêm resource handler trùng mapping mặc định.** Có thể làm thay đổi static resource resolution hoặc cache behavior. Kiểm tra URL pattern và location.
12. **Dùng API Servlet trong WebFlux.** WebMvcConfigurer chỉ dành cho Spring MVC Servlet stack; dùng WebFluxConfigurer cho reactive stack.
13. **Không kiểm thử Boot defaults còn hoạt động.** Chỉ test interceptor là chưa đủ; nên test JSON conversion, static resource hoặc feature Boot mà ứng dụng cần giữ.
14. **Dựa vào thứ tự configurer không được kiểm chứng.** Nếu nhiều configurer cùng chỉnh một danh sách/setting, đặt trách nhiệm rõ và test kết quả cuối.

## 10. Cách chẩn đoán khi cấu hình không có tác dụng

1. Xác nhận ứng dụng đang chạy Servlet MVC hay WebFlux.
2. Kiểm tra có @EnableWebMvc hoặc bean WebMvcConfigurationSupport nào khiến Boot auto-configuration back off không.
3. Kiểm tra class @Configuration triển khai WebMvcConfigurer có được component scan hoặc import vào context không.
4. Kiểm tra addPathPatterns/excludePathPatterns của interceptor và route thực tế.
5. Kiểm tra CORS bằng request có Origin; với preflight dùng OPTIONS, Access-Control-Request-Method và Access-Control-Request-Headers.
6. Nếu JSON không serialize như mong đợi, xem danh sách HttpMessageConverter, thứ tự và Accept header.
7. Dùng --debug để xem condition evaluation report của Spring Boot; nếu Actuator conditions endpoint đã được bật, kiểm tra /actuator/conditions.
8. Kiểm tra security filter chain trước MVC nếu request bị chặn trước khi tới controller.
9. Kiểm tra log của DispatcherServlet, handler mappings và exception resolvers khi route không được tìm thấy.

## 11. Checklist trước khi thêm WebMvcConfigurer

- [ ] Đã xác nhận đây là ứng dụng Spring MVC trên Servlet stack.
- [ ] Đã dùng @Configuration triển khai WebMvcConfigurer.
- [ ] Không thêm @EnableWebMvc nếu muốn giữ Boot MVC auto-configuration.
- [ ] Chỉ override callback cần thiết.
- [ ] Interceptor có path include/exclude phù hợp và không thay thế Spring Security.
- [ ] CORS dùng origins/methods/headers có chủ đích; credentials không đi cùng wildcard origin.
- [ ] Nếu thêm converter, đã xem extendMessageConverters hoặc cơ chế HttpMessageConverters.
- [ ] Nếu thay HandlerMapping/Adapter/ExceptionResolver, đã xem WebMvcRegistrations.
- [ ] Test JSON conversion và các tiện ích Boot mà ứng dụng cần giữ.
- [ ] Nếu dùng Spring Security, test cả request thường và preflight CORS qua filter chain.
- [ ] Có test cho route, interceptor, CORS, converter và static resources theo nhu cầu thực tế.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Muốn thêm một interceptor trong Spring Boot mà vẫn giữ cấu hình MVC mặc định, cần annotation nào?  
**Đáp án:** Tạo @Configuration implement WebMvcConfigurer; không thêm @EnableWebMvc.

**Câu 2.** Vì sao @EnableWebMvc có thể khiến WebMvcAutoConfiguration back off?  
**Đáp án:** Nó import MVC configuration dựa trên WebMvcConfigurationSupport; auto-configuration của Boot có điều kiện thiếu bean kiểu này.

**Câu 3.** Muốn thêm một converter nhưng giữ converter mặc định, nên xem callback nào?  
**Đáp án:** extendMessageConverters, hoặc đóng góp HttpMessageConverter bean/HttpMessageConverters theo cơ chế Boot.

**Câu 4.** HandlerInterceptor và Servlet Filter khác nhau ở đâu?  
**Đáp án:** Filter chạy ở Servlet layer trước DispatcherServlet; interceptor chạy trong Spring MVC sau khi handler được chọn.

**Câu 5.** Có nên dùng interceptor để quyết định user có quyền truy cập endpoint?  
**Đáp án:** Không nên dùng nó làm security layer chính; dùng Spring Security filter chain.

**Câu 6.** addArgumentResolvers có thay thế resolver built-in của Spring MVC không?  
**Đáp án:** Không. Nó thêm resolver hỗ trợ kiểu tham số tùy biến; thay built-in support cần cấu hình RequestMappingHandlerAdapter chuyên sâu.

**Câu 7.** Khi cần custom RequestMappingHandlerAdapter nhưng vẫn muốn giữ Boot MVC customization, nên xem gì?  
**Đáp án:** WebMvcRegistrations.

**Câu 8.** Có thể dùng WebMvcConfigurer trong ứng dụng WebFlux thuần không?  
**Đáp án:** Không. WebFlux có WebFluxConfigurer và pipeline reactive riêng.

## Tài liệu tham khảo chính thức

- Spring Boot 3.5 Reference — Servlet Web Applications, phần Spring MVC Auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Boot 3.5 API — WebMvcAutoConfiguration và điều kiện @ConditionalOnMissingBean(WebMvcConfigurationSupport.class): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/servlet/WebMvcAutoConfiguration.html
- Spring Boot 3.5 Reference — Spring MVC how-to, converters và switch off default MVC configuration: https://docs.spring.io/spring-boot/3.5/how-to/spring-mvc.html
- Spring Boot 3.5 Reference — Testing Spring Boot Applications, @WebMvcTest: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework 6.2 Reference — MVC Config: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config.html
- Spring Framework 6.2 Javadoc — WebMvcConfigurer: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html
- Spring Framework 6.2 Reference — Message Converters: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/message-converters.html
- Spring Framework 6.2 Reference — Interceptors: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/interceptors.html

**Ghi nhớ:** Trong Spring Boot, WebMvcConfigurer là cách mở rộng cấu hình MVC hiện có. Dùng @Configuration và chỉ override callback cần thiết; giữ @EnableWebMvc cho trường hợp muốn tự quản lý toàn bộ MVC. Khi cần thêm converter, ưu tiên extendMessageConverters; khi cần bảo mật request, dùng Spring Security thay cho interceptor.

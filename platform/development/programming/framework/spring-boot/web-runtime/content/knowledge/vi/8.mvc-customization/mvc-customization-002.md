# WebMvcConfigurer: bổ sung cấu hình Spring MVC mà vẫn giữ mặc định của Spring Boot

## 1. Vấn đề cần giải quyết

Spring Boot tự cấu hình Spring MVC để một ứng dụng có thể xử lý HTTP request bằng controller mà không phải tự tạo toàn bộ hạ tầng MVC. Tuy nhiên, dự án vẫn có thể cần một interceptor, một bộ chuyển đổi tham số, quy tắc CORS, một đường dẫn tĩnh bổ sung hoặc một view controller.

**WebMvcConfigurer** là giao diện mở rộng cấu hình Spring MVC cho các nhu cầu như vậy. Cách sử dụng phù hợp với Spring Boot là viết một lớp **@Configuration implements WebMvcConfigurer** và chỉ override những phương thức cần thiết, **không thêm @EnableWebMvc**.

~~~java
@Configuration(proxyBeanMethods = false)
public class MvcExtensionConfiguration implements WebMvcConfigurer {
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        // Đăng ký thêm interceptor của ứng dụng.
    }
}
~~~

Đoạn mã này chỉ mô tả cấu trúc, chưa phải một chương trình độc lập. Các import, controller và ví dụ chạy đầy đủ xuất hiện ở phần sau.

Điểm cốt lõi: **bổ sung một cấu hình** khác với **giành quyền quản lý toàn bộ cấu hình Spring MVC**. Chỉ cần một interceptor không có nghĩa nên thay thế DispatcherServlet, handler mapping, message converters hay các mặc định mà Boot đã chuẩn bị.

Bài sử dụng API thuộc Spring Boot **3.5.x / Spring Framework 6.2.x**, Java 17+. Tên phương thức liên quan message converters và cách auto-configuration được tổ chức có thể thay đổi khi chuyển sang Spring Boot 4.x / Spring Framework 7.x; phải đối chiếu tài liệu đúng phiên bản đang chạy.

## 2. Spring Boot đang cấu hình những gì?

Với dependency spring-boot-starter-web, Spring Boot chuẩn bị một ứng dụng web theo mô hình Servlet: embedded Tomcat mặc định, DispatcherServlet, các bean hỗ trợ MVC và tích hợp với những tùy chọn của Boot.

Các tiện ích tự cấu hình liên quan MVC thường gồm:

- Handler mappings và adapters để đưa HTTP request tới controller.
- ContentNegotiatingViewResolver và BeanNameViewResolver.
- HttpMessageConverters để đọc request body và ghi response body, ví dụ JSON.
- Converter, GenericConverter và Formatter do application context cung cấp.
- Phục vụ static resources từ các vị trí classpath mặc định như /static và /public.
- Hỗ trợ index.html làm welcome page.
- Một số tích hợp binding, error handling và property cấu hình liên quan.

Boot còn có cấu hình riêng cho Jackson, multipart, path matching, static resource chain, format ngày giờ, compression và các thành phần khác, tùy phiên bản, dependency và property.

Ví dụ một controller:

~~~java
@RestController
@RequestMapping("/api")
public class ExampleController {

    @GetMapping("/hello")
    public Map<String, String> hello() {
        return Map.of("message", "hello");
    }
}
~~~

Không cần tự đăng ký MappingJackson2HttpMessageConverter để response được chuyển sang JSON khi starter-web có các dependency cần thiết. Cấu hình bổ sung nên giữ được những khả năng này.

## 3. Ba cách cấu hình MVC dễ bị nhầm lẫn

| Cách làm | Hành vi dự kiến | Trường hợp sử dụng |
|---|---|---|
| @Configuration + WebMvcConfigurer | Thêm hoặc điều chỉnh phần cấu hình MVC thông qua extension points, giữ cơ chế MVC auto-configuration của Boot | Lựa chọn mặc định cho hầu hết ứng dụng |
| @Configuration + @EnableWebMvc | Tự giành trách nhiệm cấu hình MVC, khiến MVC auto-configuration của Boot không áp dụng như trước | Khi chủ ý quản lý hạ tầng MVC ở mức framework |
| Tự khai báo WebMvcConfigurationSupport hoặc cấu hình hạ tầng thay thế tương đương | Có thể làm Boot back off và thay đổi mặc định | Trường hợp chuyên sâu, cần kiểm soát đầy đủ |

### 3.1. Cách nên dùng

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class AppMvcConfiguration implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        // Chỉ đăng ký phần cần bổ sung.
    }
}
~~~

Spring Boot có thể tiếp tục đăng ký resource handlers, message converters và các phần MVC mặc định của nó.

### 3.2. Cách không nên dùng nếu chỉ muốn thêm một tính năng

~~~java
@Configuration
@EnableWebMvc
public class FullMvcConfiguration implements WebMvcConfigurer {
}
~~~

Khai báo trên là ví dụ **đối chứng không nên áp dụng** khi mục tiêu là giữ mặc định Boot. @EnableWebMvc kích hoạt hướng cấu hình MVC riêng của Spring Framework; MVC auto-configuration của Boot không còn được áp dụng theo cơ chế thông thường. MVC không ngừng hoạt động, nhưng nhiều tiện ích mà ứng dụng từng nhận từ Boot có thể cần được cấu hình lại.

Lỗi phổ biến là thêm @EnableWebMvc theo một ví dụ Spring Framework thuần rồi phát hiện CSS/JS hoặc index.html không còn được phục vụ như trước. Nguyên nhân không phải WebMvcConfigurer, mà là việc chuyển sang tự quản lý MVC.

### 3.3. Không nhầm với WebFlux

WebMvcConfigurer dành cho **Spring MVC / Servlet stack**. Nó không phải cơ chế tùy chỉnh Spring WebFlux. WebFlux có các extension points riêng như WebFluxConfigurer.

Nếu dùng cả spring-boot-starter-web và spring-boot-starter-webflux để lấy WebClient, Boot thường ưu tiên mô hình MVC cho server. Sự có mặt của WebClient không khiến một WebMvcConfigurer tự chuyển thành WebFlux configuration.

## 4. Các phương thức chính của WebMvcConfigurer

| Phương thức | Dùng để | Lưu ý |
|---|---|---|
| addInterceptors | Thêm HandlerInterceptor theo path | Không thay thế Spring Security |
| addFormatters | Đăng ký Converter và Formatter | Có ích cho @RequestParam, @PathVariable, binding |
| addCorsMappings | Thêm CORS mapping | CORS không phải cơ chế xác thực |
| addViewControllers | Ánh xạ URL đơn giản tới view hoặc redirect | Không cần viết controller logic |
| addResourceHandlers | Thêm tài nguyên tĩnh theo path | Kiểm tra resource location và cache |
| configurePathMatch | Điều chỉnh cách match path | Dễ ảnh hưởng toàn bộ endpoint |
| configureContentNegotiation | Điều chỉnh chiến lược content negotiation | Có thể thay đổi cách chọn representation |
| addArgumentResolvers | Thêm resolver cho tham số tùy chỉnh | Resolver mới không tự thay thế tất cả built-in resolvers |
| addReturnValueHandlers | Thêm handler cho kiểu kết quả tùy chỉnh | Chỉ dùng khi cần extension đặc thù |
| configureMessageConverters | Điều khiển danh sách converter | Cần đặc biệt thận trọng với các converter mặc định |
| extendMessageConverters | Điều chỉnh danh sách sau khi đã cấu hình | Thường an toàn hơn nếu chỉ thêm/chỉnh một phần |
| configureAsyncSupport | Cấu hình async request processing | Không thay thế timeout của HTTP client/upstream |
| configureDefaultServletHandling | Điều chỉnh việc giao tài nguyên cho default servlet | Chỉ dùng khi kiến trúc container cần |

Không nhất thiết override tất cả các phương thức. WebMvcConfigurer có các phương thức default, nên một lớp chỉ cần triển khai đúng những hook cần dùng.

## 5. Một dự án chạy được: vừa mở rộng MVC vừa giữ mặc định

Bài toán:

1. Mọi request tới /api/** nhận response header X-MVC-Extension: enabled qua interceptor.
2. Tham số priority=high hoặc priority=normal được chuyển sang enum Priority.
3. /welcome redirect sang /api/status mà không cần controller riêng.
4. /guides/** phục vụ nội dung bổ sung từ classpath:/public-guides/.
5. Origin https://app.example.com được phép gọi API theo CORS policy đã chỉ định.
6. /index.html trong thư mục static mặc định và JSON response vẫn hoạt động: đây là kiểm tra quan trọng rằng ứng dụng không vô tình bỏ toàn bộ Boot MVC defaults.

Cấu trúc:

~~~text
mvc-extension-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/mvcdemo/
    │   │   ├── MvcDemoApplication.java
    │   │   ├── Priority.java
    │   │   ├── DemoHeaderInterceptor.java
    │   │   ├── MvcEnhancements.java
    │   │   └── DemoController.java
    │   └── resources/
    │       ├── static/index.html
    │       └── public-guides/start.txt
    └── test/java/com/example/mvcdemo/
        └── MvcDemoTest.java
~~~

### 5.1. pom.xml

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
    <artifactId>mvc-extension-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>mvc-extension-demo</name>

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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugins>
    </build>
</project>
~~~

Phiên bản 3.5.16 được dùng để cố định API ví dụ. Đây là bản cuối của nhánh 3.5.x được hỗ trợ OSS; với dự án sản xuất mới cần chọn nhánh còn được hỗ trợ và chuyển đổi ví dụ theo API tương ứng.

### 5.2. MvcDemoApplication.java

~~~java
package com.example.mvcdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcDemoApplication.class, args);
    }
}
~~~

@SpringBootApplication bật auto-configuration và component scanning. Đặt file trong package com.example.mvcdemo để quét những lớp còn lại.

### 5.3. Priority.java

~~~java
package com.example.mvcdemo;

public enum Priority {
    LOW, NORMAL, HIGH
}
~~~

### 5.4. DemoHeaderInterceptor.java

~~~java
package com.example.mvcdemo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
public class DemoHeaderInterceptor implements HandlerInterceptor {

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler) {

        response.setHeader("X-MVC-Extension", "enabled");
        return true;
    }
}
~~~

Interceptor này minh họa một hành động không làm thay đổi business logic. Nó thêm response header trước khi controller xử lý rồi cho request đi tiếp bằng cách trả true.

Trong dự án thật, không dùng header minh họa này làm bằng chứng xác thực, phân quyền hay tín hiệu tin cậy giữa các hệ thống.

### 5.5. MvcEnhancements.java: phần mở rộng chính

~~~java
package com.example.mvcdemo;

import java.util.Locale;

import org.springframework.context.annotation.Configuration;
import org.springframework.format.FormatterRegistry;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.ViewControllerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcEnhancements implements WebMvcConfigurer {

    private final DemoHeaderInterceptor interceptor;

    public MvcEnhancements(DemoHeaderInterceptor interceptor) {
        this.interceptor = interceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(interceptor)
                .addPathPatterns("/api/**");
    }

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
                String.class,
                Priority.class,
                source -> Priority.valueOf(
                        source.trim().toUpperCase(Locale.ROOT)));
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://app.example.com")
                .allowedMethods("GET")
                .allowedHeaders("Content-Type")
                .maxAge(3600);
    }

    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        registry.addRedirectViewController(
                "/welcome", "/api/status");
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/guides/**")
                .addResourceLocations("classpath:/public-guides/");
    }
}
~~~

Tại đây không có @EnableWebMvc. Những gì ứng dụng làm là đăng ký **thêm** các thành phần với registry mà Spring MVC đang dùng.

Các lựa chọn có chủ đích:

- Scope interceptor là /api/**, không áp dụng mọi static resource.
- Converter String → Priority cho phép client nhập high, normal, low mà vẫn nhận enum.
- CORS chỉ cho một origin cụ thể và method GET.
- Resource mapping /guides/** là một đường dẫn mới, không tự khai báo lại mapping mặc định /**.
- View controller đơn giản chỉ redirect, không trộn business logic.

### 5.6. DemoController.java

~~~java
package com.example.mvcdemo;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {

    @GetMapping("/status")
    public Map<String, String> status() {
        return Map.of("status", "ready");
    }

    @GetMapping("/tasks")
    public Map<String, String> tasks(
            @RequestParam(defaultValue = "normal") Priority priority) {

        return Map.of(
                "status", "ready",
                "priority", priority.name());
    }
}
~~~

Nếu chưa có converter tùy chỉnh, biểu diễn enum mặc định thường đòi hỏi cách ghi tương ứng tên enum; sau khi đăng ký converter, request priority=high được chuyển thành Priority.HIGH. Đoạn xử lý còn lại không cần biết chữ hoa/chữ thường trong query string.

### 5.7. Tài nguyên tĩnh mặc định và tài nguyên bổ sung

Tạo **src/main/resources/static/index.html**:

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>MVC defaults</title>
</head>
<body>
  <h1>Welcome from Boot static resources</h1>
</body>
</html>
~~~

Tạo **src/main/resources/public-guides/start.txt**:

~~~text
Guide served by custom resource handler.
~~~

/index.html thuộc cơ chế static resources có sẵn của Boot. /guides/start.txt thuộc mapping do ứng dụng bổ sung. Hai cơ chế có thể cùng tồn tại.

## 6. Chạy thử và kết quả mong đợi

Yêu cầu Java 17+ và Maven 3.6.3+:

~~~bash
mvn test
mvn spring-boot:run
~~~

Khi ứng dụng chạy trên cổng mặc định 8080, kiểm tra:

~~~bash
curl -i "http://localhost:8080/api/tasks?priority=high"
curl -i "http://localhost:8080/api/status"
curl -i "http://localhost:8080/welcome"
curl -i "http://localhost:8080/index.html"
curl -i "http://localhost:8080/guides/start.txt"
~~~

Các kết quả quan trọng:

- GET /api/tasks?priority=high trả 200, có header X-MVC-Extension: enabled và JSON chứa priority bằng HIGH, status bằng ready. Thứ tự trường JSON không phải hợp đồng bắt buộc.
- GET /api/status trả JSON với status bằng ready.
- GET /welcome trả redirect (thường 302) tới /api/status.
- GET /index.html trả HTML có dòng Welcome from Boot static resources: **mặc định Boot vẫn hoạt động**.
- GET /guides/start.txt trả nội dung Guide served by custom resource handler. từ resource handler mới.

Ví dụ body của /api/tasks:

~~~json
{"priority":"HIGH","status":"ready"}
~~~

Không khẳng định thứ tự key trong JSON hoặc thứ tự HTTP headers luôn giống nhau. Kiểm tra bằng status, header riêng và các giá trị JSON là đủ.

## 7. Kiểm thử integration bằng MockMvc

Bổ sung file **src/test/java/com/example/mvcdemo/MvcDemoTest.java**:

~~~java
package com.example.mvcdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.redirectedUrl;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MvcDemoTest {

    @Autowired
    MockMvc mvc;

    @Test
    void convertsQueryParameterAndRunsInterceptor() throws Exception {
        mvc.perform(get("/api/tasks").param("priority", "high"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-MVC-Extension", "enabled"))
                .andExpect(jsonPath("$.priority").value("HIGH"))
                .andExpect(jsonPath("$.status").value("ready"));
    }

    @Test
    void preservesDefaultStaticResourceHandling() throws Exception {
        mvc.perform(get("/index.html"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        containsString("Welcome from Boot static resources")));
    }

    @Test
    void servesAdditionalResourceMapping() throws Exception {
        mvc.perform(get("/guides/start.txt"))
                .andExpect(status().isOk())
                .andExpect(content().string(
                        containsString("Guide served by custom resource handler.")));
    }

    @Test
    void mapsViewControllerRedirect() throws Exception {
        mvc.perform(get("/welcome"))
                .andExpect(status().is3xxRedirection())
                .andExpect(redirectedUrl("/api/status"));
    }
}
~~~

Bộ test này kiểm tra đồng thời chức năng mới và một chức năng mặc định. Đây là hướng kiểm thử tốt hơn cách chỉ xác nhận rằng bean MvcEnhancements có mặt trong ApplicationContext.

Chạy:

~~~bash
mvn test
~~~

Nếu các test đều thành công, Maven trả exit code 0. Số lượng test, thời gian chạy và text log phụ thuộc môi trường; không nên hard-code output log làm tiêu chí đúng/sai.

## 8. Interceptor: hiểu đúng phạm vi tác động

HandlerInterceptor chạy trong quy trình xử lý của Spring MVC quanh một handler. Những phương thức chính:

- preHandle chạy trước khi handler thực thi, có thể ngăn xử lý bằng cách trả false.
- postHandle có thể chạy sau handler khi mô hình xử lý cho phép; với @ResponseBody và xử lý async, không nên giả định có thể thay nội dung response ở đây.
- afterCompletion chạy sau khi request hoàn thành để cleanup hoặc quan sát. Với xử lý async, có các lưu ý riêng về dispatch và callback.

Khi đăng ký interceptor:

~~~java
registry.addInterceptor(interceptor)
        .addPathPatterns("/api/**")
        .excludePathPatterns("/api/public/**");
~~~

Đường dẫn include/exclude cần được kiểm tra trong bối cảnh servlet mapping và matching strategy. Không nên dùng interceptor để thay bộ lọc bảo mật ở tầng Servlet hoặc Spring Security filter chain.

**Vì sao không dùng interceptor làm lớp authorization duy nhất?**

- Một số request có thể không đi qua handler MVC đã đăng ký interceptor.
- Quy tắc include/exclude phụ thuộc mapping.
- Bảo mật cần xử lý đồng nhất credential, authentication, exception, CSRF và các entry points khác.

Spring Security thường phù hợp hơn để xác thực/phân quyền. Interceptor hữu ích cho instrumentation, logging metadata, thiết lập request context hoặc cross-cutting concern gắn với controller.

Nếu cần xử lý trước DispatcherServlet hoặc trên toàn bộ Servlet request chain, cân nhắc Filter/OncePerRequestFilter hoặc FilterRegistrationBean thay vì HandlerInterceptor.

## 9. Converter và Formatter: chọn đúng công cụ

Phương thức addFormatters nhận FormatterRegistry. Tại đây có thể đăng ký:

- Converter<S,T>: một phép chuyển từ kiểu S sang T.
- ConverterFactory<S,R>: tạo converter cho một họ kiểu đích.
- Formatter<T>: chuyển đổi String ↔ object có xét locale thông qua print/parse.

Ví dụ chuyển một tham số dạng yyyy-MM-dd sang kiểu domain. Nếu ứng dụng chỉ cần format date/time thông dụng, hãy ưu tiên thuộc tính Boot như spring.mvc.format.date trước khi viết converter mới.

Một Formatter phù hợp khi cần định dạng theo locale. Ví dụ định dạng giá tiền có thể dùng NumberFormat hoặc Formatter riêng, nhưng phải xử lý nhập liệu sai và tránh diễn giải mơ hồ dấu phân cách.

**Lưu ý quan trọng:** ConversionService của Spring MVC dùng cho binding request khác với conversion service mà Boot dùng để bind application.properties/application.yml. Một converter đăng ký qua WebMvcConfigurer.addFormatters không có nghĩa nó sẽ tự chuyển đổi mọi giá trị của @ConfigurationProperties.

Với trường hợp chỉ cần đổi format một field:

~~~java
@GetMapping("/search")
public String search(
        @RequestParam
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate date) {
    return date.toString();
}
~~~

Đây là đoạn minh họa; các import của LocalDate và DateTimeFormat cần có nếu đặt trong class controller. Nó cho thấy không phải nhu cầu binding nào cũng đòi cấu hình WebMvcConfigurer.

## 10. CORS: thêm mapping không phải mở toàn bộ bảo mật

addCorsMappings thiết lập chính sách Cross-Origin Resource Sharing cho request xử lý qua Spring MVC. Với frontend tại https://app.example.com và backend tại https://api.example.com, trình duyệt áp dụng chính sách origin và có thể gửi preflight request.

~~~java
@Override
public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST")
            .allowedHeaders("Content-Type", "Authorization")
            .exposedHeaders("X-Request-Id")
            .maxAge(1800);
}
~~~

Đoạn này minh họa khi ứng dụng cần thêm POST và Authorization; không thuộc ví dụ chạy ở mục 5.

Cần phân biệt:

- CORS điều khiển quyền của JavaScript trên một origin khác được đọc response trong trình duyệt.
- CORS **không** thay authentication và authorization ở server.
- CORS **không** phải biện pháp CSRF đầy đủ.
- allowCredentials chỉ bật khi thật sự cần gửi cookie/credential từ trình duyệt và phải giới hạn origin tương ứng.
- Dùng wildcard origins một cách tùy tiện có thể tạo lỗ hổng truy cập dữ liệu nếu hệ thống cấu hình credential sai.

Nếu ứng dụng có Spring Security, phải tích hợp xử lý CORS với security filter chain. Preflight request thường không có session credential và có thể bị security filter chặn trước khi tới MVC nếu cấu hình không phù hợp.

Đối với CORS policy đơn giản toàn cục, WebMvcConfigurer là điểm cấu hình phổ biến; đối với chính sách endpoint đặc thù, có thể dùng @CrossOrigin trên controller hoặc method khi thật sự hợp lý.

## 11. View controllers và static resources

### 11.1. View controller

addViewControllers hữu ích cho endpoint không có business logic:

~~~java
@Override
public void addViewControllers(ViewControllerRegistry registry) {
    registry.addViewController("/about").setViewName("about");
    registry.addRedirectViewController("/legacy", "/about");
}
~~~

Nếu trả view "about", dự án phải có view resolver và template tương ứng hoặc kiến trúc phục vụ view phù hợp. Với ứng dụng API-only, không nên tạo view controller chỉ để trả dữ liệu JSON; dùng @RestController.

Trong dự án chạy ở mục 5, redirect /welcome → /api/status tránh phụ thuộc vào template engine.

### 11.2. Resource handler

Boot mặc định phục vụ static content từ những nơi như classpath:/static/, classpath:/public/, classpath:/resources/ và classpath:/META-INF/resources/. AddResourceHandlers phù hợp khi cần thêm location riêng:

~~~java
registry.addResourceHandler("/docs/**")
        .addResourceLocations("classpath:/extra-docs/");
~~~

Một mapping quá rộng như /** có thể chồng lên static resource mapping của Boot và làm thay đổi cách xử lý không mong muốn. Khi chỉ muốn đổi path hoặc location static mặc định, trước tiên xem xét property spring.mvc.static-path-pattern hoặc spring.web.resources.static-locations của phiên bản đang dùng.

Không phục vụ tài liệu nội bộ bí mật chỉ bằng cách đặt nó dưới static resources. Việc file có thể tải qua HTTP cần được kiểm soát tương ứng với chính sách truy cập.

### 11.3. Quy tắc cache và versioning

Static resource trong production có thể cần cache-control và content-based versioning. Boot cung cấp các property cho static resources và resource chain tùy phiên bản. Nếu cần hành vi riêng cho /docs/**, có thể cấu hình cache cho đúng resource handler.

Tuy nhiên, hãy kiểm tra việc cache dữ liệu nhạy cảm, file thay đổi thường xuyên, proxy/CDN và header thực tế. Không nên set max-age dài cho tất cả response chỉ để tăng tốc tải trang.

## 12. Message converters: điểm dễ làm mất mặc định

Spring MVC dùng HttpMessageConverter để đọc @RequestBody và ghi @ResponseBody. Khi có spring-boot-starter-web và Jackson, object Java thường được serialize thành JSON mà không phải cấu hình thủ công.

Trong **Spring Framework 6.2**, WebMvcConfigurer có hai hook dễ nhầm:

- configureMessageConverters(List<HttpMessageConverter<?>>): trực tiếp cấu hình danh sách converters; với cấu hình MVC chuẩn, việc dùng hook này có thể ảnh hưởng việc thêm converters mặc định. Spring Boot có cơ chế bổ sung các HttpMessageConverter beans, nên không được đơn giản hóa rằng mọi ứng dụng Boot sẽ luôn mất toàn bộ default converters.
- extendMessageConverters(List<HttpMessageConverter<?>>): được gọi để tiếp tục điều chỉnh danh sách converter đã hình thành. Khi cần thay đổi nhỏ, nên cân nhắc hook này.

Ví dụ chỉ kiểm tra converter trong quá trình mở rộng:

~~~java
@Override
public void extendMessageConverters(
        List<HttpMessageConverter<?>> converters) {
    // Chỉ thêm hoặc điều chỉnh phần thực sự cần thiết.
    // Không clear() hoặc thay cả danh sách một cách tùy tiện.
}
~~~

Đoạn trên mang tính minh họa cấu trúc và cần import List, HttpMessageConverter.

Với customization JSON, hãy xem các lựa chọn cấp cao hơn:

1. Thuộc tính spring.jackson.* trong các phiên bản Boot có hỗ trợ.
2. Bean hoặc customizer Jackson phù hợp với phiên bản dự án.
3. HttpMessageConverter bean khi thật sự cần một định dạng hay cách xử lý mới.
4. extendMessageConverters khi có yêu cầu tinh chỉnh rõ ràng và đã kiểm tra thứ tự converter.

Không nên tự tạo RequestMappingHandlerAdapter hoặc xóa converters mặc định chỉ để đổi cách format một property JSON.

**Lưu ý phiên bản:** Spring Framework 7 đã thay đổi một số hợp đồng cấu hình message converters. Ví dụ hook nhận List ở đây dành cho Spring Framework 6.2 / Spring Boot 3.5; khi nâng sang Boot 4 cần xem lại signature và API migration.

## 13. Khi nào cần WebMvcRegistrations?

Có những nhu cầu chuyên sâu phải thay cách tạo một thành phần hạ tầng MVC, ví dụ RequestMappingHandlerMapping, RequestMappingHandlerAdapter hoặc ExceptionHandlerExceptionResolver, nhưng vẫn muốn giữ các MVC customizations của Boot.

Spring Boot cung cấp điểm mở rộng **WebMvcRegistrations** cho những trường hợp đó. Nó cho phép ứng dụng cung cấp custom instance của một số infrastructure bean trước khi Spring MVC hoàn thiện khâu khởi tạo/cấu hình.

Đây **không phải** lựa chọn mặc định cho một interceptor hoặc converter. WebMvcConfigurer giải quyết nhiều tình huống hơn với ít rủi ro và ít mã phụ thuộc vào internals.

Thứ tự lựa chọn gợi ý:

1. Property Boot nếu đủ.
2. Bean hoặc component extension ở mức nghiệp vụ.
3. WebMvcConfigurer cho hook chính thức.
4. WebMvcRegistrations nếu cần thành phần MVC đặc biệt.
5. Chỉ sử dụng @EnableWebMvc và cấu hình toàn bộ nếu chủ đích tiếp quản MVC configuration.

Cần test tác động đến content negotiation, static resources, exception handling và security khi thay component lõi.

## 14. Khi nào nên dùng application.properties thay vì WebMvcConfigurer?

Không phải mọi nhu cầu cấu hình đều cần Java code. Ví dụ:

~~~properties
server.port=8080
server.servlet.context-path=/shop
spring.mvc.static-path-pattern=/assets/**
spring.web.resources.static-locations=classpath:/static/
spring.mvc.format.date=iso
~~~

Đây là ví dụ các property có thể dùng theo hợp đồng Boot 3.5.x; không nhất thiết cấu hình tất cả cùng lúc. Một số property có phạm vi và tương tác khác nhau:

- server.port đặt cổng của embedded server.
- server.servlet.context-path đặt context path của Servlet app.
- spring.mvc.static-path-pattern đổi pattern cho static resources, không đổi mọi controller mapping.
- spring.web.resources.static-locations đổi danh sách location phục vụ tài nguyên tĩnh; nếu ghi đè danh sách, cần bảo đảm vẫn giữ location mong muốn.
- spring.mvc.format.date định dạng mặc định cho MVC date binding phù hợp.

Khi requirement đã được property giải quyết, property thường dễ theo dõi theo environment, ít mã và ít phụ thuộc API hơn. Nhưng một đoạn logic lựa chọn mapping dựa trên bean/domain behavior thì WebMvcConfigurer có thể rõ ràng hơn.

## 15. Nhiều WebMvcConfigurer có thể cùng tồn tại

Ứng dụng có thể khai báo nhiều cấu hình triển khai WebMvcConfigurer trong các module khác nhau. Spring MVC tổng hợp những đóng góp của chúng qua cơ chế configuration của framework.

Tuy vậy, cần chú ý:

- Nhiều interceptor áp dụng cùng path có thể chạy liên tiếp; nên ghi rõ thứ tự và phạm vi.
- Hai cấu hình cùng thay format/converter cho một kiểu có thể gây xung đột.
- Hai resource mappings chồng pattern có thể khiến hành vi khó dự đoán.
- CORS policy từ nhiều nơi cần được xét theo quy tắc kết hợp và ưu tiên.
- Tùy chỉnh path matching hoặc message converter có ảnh hưởng toàn cục, cần kiểm thử hồi quy.

Có thể dùng @Order cho các bean hoặc registration khi framework hỗ trợ thứ tự tại điểm mở rộng liên quan. Đừng giả định thứ tự không xác định là một hợp đồng bảo đảm giữa các module.

Một tổ chức dễ duy trì thường đặt tên rõ trách nhiệm, ví dụ ApiCorsConfiguration, MvcFormattingConfiguration và InterceptorConfiguration; mỗi class chỉ sở hữu một nhóm cấu hình.

## 16. Lỗi thường gặp và cách xử lý

| Dấu hiệu | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| Sau khi thêm custom MVC config, CSS/JS hoặc index.html trả 404 | Đã thêm @EnableWebMvc hoặc thay WebMvcConfigurationSupport | Bỏ cấu hình takeover nếu không cần; giữ WebMvcConfigurer thuần và kiểm thử static files |
| JSON response không còn được convert như trước | Danh sách message converters bị thay, thiếu Jackson hoặc media type không phù hợp | Kiểm tra dependencies và converters; dùng extendMessageConverters hoặc cơ chế Boot nếu chỉ thêm |
| Interceptor không chạy với endpoint mong muốn | Path pattern không match, endpoint không thuộc MVC handler hoặc bị exclude | Kiểm tra addPathPatterns, servlet mapping và request thực tế |
| Interceptor được coi là bảo mật nhưng endpoint khác lọt qua | HandlerInterceptor không phải filter chain bảo mật toàn diện | Dùng Spring Security, kiểm thử mọi entry point |
| @RequestParam enum lỗi với chuỗi chữ thường | Converter không được đăng ký hoặc thứ tự converter gây xung đột | Đăng ký đúng với addFormatters, kiểm thử lower/upper case |
| CORS vẫn bị chặn sau khi addCorsMappings | Origin/method/header chưa khớp hoặc Spring Security xử lý trước | Kiểm tra preflight và security configuration |
| Resource handler mới vô tình chặn static resources cũ | Pattern quá rộng như /** hoặc resource location sai | Dùng namespace hẹp và kiểm thử đồng thời đường dẫn cũ/mới |
| Đổi spring.mvc.static-path-pattern làm /index.html 404 | Pattern mặc định đã được thay bằng prefix mới | Truy cập theo URL mới hoặc điều chỉnh property |
| @ConfigurationProperties không dùng converter đã đăng ký cho MVC | MVC conversion service khác binder của Boot | Tùy chỉnh conversion cho properties qua cơ chế Boot tương ứng |
| Đăng ký view controller nhưng view không render | Thiếu template/view resolver hoặc nhầm view với REST response | Cấu hình view engine đúng hoặc dùng @RestController |
| Đổi server stack nhưng WebMvcConfigurer không có tác dụng | Ứng dụng chạy WebFlux/reactive thay vì MVC/Servlet | Xác minh starter, application type và dùng WebFluxConfigurer nếu cần |
| Một tùy chỉnh nhỏ làm nhiều test cũ hỏng | Vô tình thay hạ tầng mặc định hoặc chỉnh path matching toàn cục | Bắt đầu từ hook tối thiểu, test hồi quy từng endpoint |

## 17. Checklist trước khi merge thay đổi

- [ ] Ứng dụng thực sự dùng Spring MVC/Servlet, không phải Spring WebFlux server.
- [ ] Lớp cấu hình dùng @Configuration implements WebMvcConfigurer.
- [ ] Không thêm @EnableWebMvc hoặc tự khai báo WebMvcConfigurationSupport nếu vẫn muốn giữ Boot auto-configuration.
- [ ] Chỉ override phương thức cần thiết; path cho interceptor/CORS/resources được giới hạn rõ.
- [ ] Không dùng interceptor thay cho authentication/authorization.
- [ ] Không vô tình thay toàn bộ message converters.
- [ ] Đã xem property Boot trước khi viết custom Java code.
- [ ] Các static resources và JSON mapping mặc định vẫn hoạt động.
- [ ] Có test lỗi, cả endpoint mới lẫn endpoint cũ.
- [ ] Mọi thay đổi global path matching, content negotiation, format hoặc async đều có test hồi quy.
- [ ] Tên API và method được đối chiếu đúng nhánh Spring Boot/Spring Framework đang dùng.

## 18. Ghi nhớ

**WebMvcConfigurer là điểm mở rộng, không phải lời yêu cầu thay thế toàn bộ Spring MVC.** Khi muốn bổ sung interceptor, formatter, CORS mapping, redirect hoặc static resource handler trong Spring Boot, hãy tạo @Configuration implements WebMvcConfigurer **và không thêm @EnableWebMvc**.

Chỉ dùng @EnableWebMvc khi chủ ý tự tiếp quản MVC infrastructure và chấp nhận trách nhiệm tái tạo những hành vi cần thiết mà Boot đã cung cấp. Luôn kiểm thử cả hai phía: chức năng được bổ sung **và** những mặc định vẫn phải hoạt động.

## Tài liệu chính thức

- [Spring Boot 3.5 — Servlet Web Applications và MVC Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Spring Framework 6.2 — Web MVC Config](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config.html)
- [Spring Framework 6.2 — Message Converters](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/message-converters.html)
- [Spring Framework 6.2 — Interceptors](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/interceptors.html)

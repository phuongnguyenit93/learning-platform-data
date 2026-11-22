# @EnableWebMvc, WebMvcConfigurer và cấu hình XML tương đương trong Spring MVC

Khi đọc dự án Spring Web, có thể gặp ba cách khai báo cấu hình: **Java config với @EnableWebMvc**, **các callback của WebMvcConfigurer**, hoặc **XML có phần tử mvc:annotation-driven và các phần tử mvc khác**. Chúng cùng giải quyết cấu hình Spring MVC nhưng **không có cùng vai trò**. Đặc biệt, trong ứng dụng **Spring Boot**, gắn @EnableWebMvc không phải bước bắt buộc và thường làm mất một phần tiện ích MVC mà Boot đang tự cấu hình.

Bài học này phân biệt từng thành phần, chỉ ra vị trí cấu hình trong quá trình khởi động Servlet, đưa ra ví dụ Java chạy được, đối chiếu Java–XML theo từng chức năng và cách chọn cấu hình phù hợp khi dùng hoặc không dùng Spring Boot.

## 1. Bức tranh tổng thể

Spring MVC là web framework trên **Servlet stack**. Để ứng dụng nhận request HTTP và gọi controller, phải có cả **Servlet tiếp nhận request**, **ApplicationContext chứa MVC infrastructure** và **controller/handler**.

~~~text
HTTP client
    |
Servlet container: Tomcat / Jetty ...
    |
Servlet mapping và filter chain
    |
DispatcherServlet  <-- được đăng ký qua Boot, initializer hoặc web.xml
    |
Spring WebApplicationContext của servlet
    |
    +-- HandlerMapping: tìm @GetMapping, @PostMapping...
    +-- HandlerAdapter: gọi controller, binding tham số
    +-- HandlerExceptionResolver: xử lý exception
    +-- HttpMessageConverter: đọc/ghi JSON, text, ...
    +-- ViewResolver / resource handler / interceptor / CORS...
    |
Controller -> Service -> response
~~~

Ba vai trò cần nhớ:

1. **@EnableWebMvc:** bật bộ **cấu hình hạ tầng Spring MVC dựa trên Java** trong ApplicationContext; đứng phía cấu hình web stack, không trực tiếp khởi tạo HTTP server hoặc tự đăng ký DispatcherServlet.
2. **WebMvcConfigurer:** giao diện callback để **tùy chỉnh cấu hình MVC**, như interceptor, formatter, static resource, CORS, view controller, path matching. Có thể dùng cùng @EnableWebMvc khi tự quản lý MVC, hoặc dùng riêng trong Spring Boot để giữ auto-configuration.
3. **XML namespace mvc:** biểu diễn nhiều cấu hình tương đương về chức năng bằng XML. Phần tử **mvc:annotation-driven** đóng vai trò bật phần lớn cơ sở hạ tầng tương tự @EnableWebMvc; **mvc:interceptors**, **mvc:resources**, **mvc:cors**... tương ứng với các callback ở Java config.

**Tách hai câu hỏi:** Ai đăng ký và phục vụ **DispatcherServlet**? Ai tạo/tùy chỉnh các **MVC beans** mà servlet sử dụng? Tập trung vào vế thứ hai sẽ hiểu đúng @EnableWebMvc và WebMvcConfigurer.

## 2. Bảng nhận diện nhanh

| Thành phần | Tác dụng chính | Khi dùng phù hợp | Điều dễ nhầm |
|---|---|---|---|
| **@EnableWebMvc** | Import cấu hình MVC nền tảng vào Spring context | Spring MVC thuần, muốn chủ động bật framework infrastructure; Boot khi cố ý tự kiểm soát MVC | Không phải annotation bắt buộc cho mọi ứng dụng Boot |
| **WebMvcConfigurer** | Cho phép thêm/sửa cấu hình MVC qua các phương thức callback | Boot muốn bổ sung MVC mà vẫn dùng các mặc định của Boot; hoặc cùng @EnableWebMvc trong MVC thuần | Tự implement interface không tự bật DispatcherServlet hay khởi động server |
| **mvc:annotation-driven** | Bật MVC annotation support và các thành phần liên quan qua XML | Ứng dụng Spring MVC dùng cấu hình XML | Không tự đăng ký servlet trong web.xml |
| **mvc:interceptors** | Khai báo MVC interceptors | Spring MVC XML | Không thay cho Servlet Filter hay Spring Security |
| **mvc:resources** | Ánh xạ URL tới nguồn static resource | Spring MVC XML | Không mặc định chỉ tới mọi thư mục và mọi resource của Boot |
| **mvc:cors** | Cấu hình CORS theo URL pattern | Spring MVC XML | CORS không phải xác thực/phân quyền |
| **mvc:view-controller** | Route tới view hoặc redirect/forward không cần controller method | Spring MVC XML | Không dùng để xử lý nghiệp vụ API phức tạp |
| **Spring Boot MVC auto-configuration** | Thiết lập sẵn phần lớn MVC + các tích hợp riêng của Boot | Ứng dụng Boot dùng Spring Web | Bị ảnh hưởng khi bật @EnableWebMvc hoặc khai báo cơ sở hạ tầng MVC tùy biến cấp thấp |

## 3. @EnableWebMvc thực sự làm gì?

Một cấu hình Java cơ bản của **Spring Framework MVC không dùng Boot**:

~~~java
package example.mvc;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
public class WebConfig {
}
~~~

**Ý nghĩa từng annotation:**

- **@Configuration:** đăng ký lớp làm nguồn định nghĩa Spring beans.
- **@EnableWebMvc:** kích hoạt Java-based MVC configuration, thông qua cơ chế import **DelegatingWebMvcConfiguration**. Cấu hình này đăng ký nhiều thành phần cần thiết để các controller dựa trên @RequestMapping hoạt động.
- Đây là **mã cấu hình minh họa, chưa phải ứng dụng HTTP chạy độc lập**. Muốn nhận request phải có servlet container, DispatcherServlet được đăng ký và controller nằm trong context phù hợp.

DelegatingWebMvcConfiguration là lớp cấu hình dựa trên **WebMvcConfigurationSupport**, đồng thời thu thập các bean **WebMvcConfigurer** đã đăng ký rồi gọi các callback thích hợp. Những thành phần MVC mặc định được thiết lập theo khả năng thư viện trên classpath và cấu hình thực tế; ví dụ cần có thư viện JSON thích hợp để chuyển đổi object thành JSON.

### Không phải các việc @EnableWebMvc làm

- Không khởi động Tomcat hay bất kỳ cổng HTTP nào.
- Không thay cho **DispatcherServlet registration**.
- Không tự động quét mọi controller ở mọi package.
- Không tự tải thêm Jackson, JSP, Thymeleaf hoặc dependency khác từ Maven.
- Không có nghĩa “ứng dụng hiện đã chạy Spring Boot”.
- Không áp dụng cho **Spring WebFlux**; WebFlux có mô hình cấu hình khác.

### Tại sao Spring Boot thường không cần @EnableWebMvc?

Spring Boot đưa vào **WebMvcAutoConfiguration** khi điều kiện về web stack/classpath thích hợp. Nó tự cung cấp cấu hình MVC cùng những tiện ích như resource handling, view resolvers, converter/formatter integration và hỗ trợ các properties tương ứng.

Nếu thêm **@EnableWebMvc** vào một dự án Boot MVC, bạn chuyển hướng sang **toàn quyền cấu hình MVC theo Spring Framework**; phần lớn MVC auto-configuration đặc thù của Boot **không còn được áp dụng như trước**. Controller có thể vẫn chạy, khiến lỗi khó nhận ra; nhưng các mặc định như phục vụ tài nguyên tĩnh, nội dung JSON, các customizations theo properties có thể thay đổi và cần chủ động cấu hình lại.

**Quy tắc thực dụng:** Trong Spring Boot, nếu chỉ cần thêm CORS, interceptor, formatter, resource mapping hoặc view controller, hãy dùng **@Configuration implements WebMvcConfigurer**, **không thêm @EnableWebMvc**.

## 4. WebMvcConfigurer: cơ chế tùy chỉnh có chọn lọc

**WebMvcConfigurer** là interface chứa các phương thức mặc định (default methods), nên lớp triển khai chỉ override phần cần dùng.

~~~java
package example.mvc;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConfig implements WebMvcConfigurer {
    // Override đúng các callback MVC cần dùng.
}
~~~

Trong đoạn trên, lớp vẫn phải được **đăng ký trong Spring ApplicationContext**. @Configuration kết hợp component scan/explicit import là cách thường dùng. Nếu lớp không được Spring phát hiện, các callback sẽ không chạy. Một class chỉ “implements WebMvcConfigurer” nhưng không phải bean sẽ không tự được áp dụng.

### Những callback quan trọng

| Callback Java | Chức năng | XML tương ứng ở mức chức năng |
|---|---|---|
| **addInterceptors** | Chèn HandlerInterceptor cho URL patterns | mvc:interceptors |
| **addResourceHandlers** | Ánh xạ URL tới static resource locations và cache | mvc:resources |
| **addCorsMappings** | CORS policy theo path | mvc:cors |
| **addViewControllers** | URL trực tiếp tới view/redirect | mvc:view-controller |
| **addFormatters** | Đăng ký Converter/Formatter dùng cho MVC binding | mvc:annotation-driven với conversion-service và converter beans |
| **configureContentNegotiation** | Điều chỉnh cách xác định requested media types | Thuộc tính/phần tử content-negotiation tương ứng tùy schema/phiên bản |
| **configureViewResolvers** | Cấu hình ViewResolver | Bean ViewResolver hoặc phần tử mvc:view-resolvers tùy phiên bản |
| **configureMessageConverters / extendMessageConverters** | Kiểm soát cách đọc/ghi HTTP body | mvc:annotation-driven với message-converters |
| **configurePathMatch** | Tùy chỉnh cách MVC khớp path | Một số tùy chọn XML/schema có thể khác; không luôn ánh xạ 1:1 |
| **addArgumentResolvers** | Bổ sung resolver cho tham số controller | mvc:annotation-driven/argument-resolvers theo schema tương ứng |
| **addReturnValueHandlers** | Bổ sung handler cho kiểu return value | Cấu hình nâng cao, không luôn có một phần tử XML trực tiếp |

**Đây là bảng tương đương mục tiêu sử dụng**, không hứa rằng Java callback và XML element có tập thuộc tính hoặc thời điểm xử lý giống hệt nhau trên mọi phiên bản Spring.

### Callback chỉ hiệu lực trong MVC infrastructure

Khi có @EnableWebMvc, **DelegatingWebMvcConfiguration** tìm các WebMvcConfigurer beans. Trong Spring Boot MVC, auto-configuration cũng tích hợp các WebMvcConfigurer để thu thập phần bổ sung. Nếu chỉ tạo interface nhưng không có MVC infrastructure thực sự, sẽ không có handler/service web để sử dụng cấu hình.

**Có thể có nhiều WebMvcConfigurer beans.** Các đóng góp thường được Spring phối hợp, nhưng nếu hai bean cùng thay đổi một cấu hình có thứ tự/ưu tiên, cần kiểm tra thứ tự và xung đột. Đừng chia cấu hình tùy tiện rồi mặc định kết quả luôn giống nhau.

## 5. Ví dụ Spring Boot MVC hoàn chỉnh: tùy chỉnh mà giữ mặc định Boot

Đây là ví dụ **chạy được** với Java 17+, Maven và ứng dụng Spring Boot có dependency **Spring Web**. Tạo một dự án **MVC** từ Spring Initializr, chọn Java, Maven, Spring Web. Với Boot 3.x, starter thông dụng là **spring-boot-starter-web**; với Boot 4.x, starter MVC là **spring-boot-starter-webmvc**. Cứ để Initializr sinh pom.xml tương ứng với phiên bản đã chọn.

Sử dụng package **example.demo** cho tất cả file Java (hoặc đổi nhất quán package trong ví dụ cho trùng dự án), đảm bảo lớp @SpringBootApplication nằm ở package gốc bao trùm controller/config. Ví dụ không cần database, template engine hay Spring Security.

Cấu trúc:

~~~text
src/main/
  java/example/demo/
    DemoApplication.java
    DemoController.java
    MarkerInterceptor.java
    WebConfig.java
  resources/
    manual/
      hello.txt
~~~

### 5.1. Application entry point

**src/main/java/example/demo/DemoApplication.java**

~~~java
package example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**Giải thích:** SpringApplication tạo ApplicationContext, Boot kích hoạt các auto-configuration phù hợp với dependency MVC và đăng ký embedded HTTP server. Không cần đặt @EnableWebMvc vào đây.

### 5.2. Controller để quan sát kết quả

**src/main/java/example/demo/DemoController.java**

~~~java
package example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {

    @GetMapping("/greet")
    public Message greet(
            @RequestParam(defaultValue = "Lan") String name) {
        return new Message("Xin chào " + name);
    }

    public record Message(String message) {
    }
}
~~~

**Giải thích:** @RestController kết hợp @Controller và @ResponseBody, record Message được Spring/Jackson ghi thành JSON. Đây là **HTTP controller**, không phải phương thức cấu hình MVC.

### 5.3. Interceptor có hành vi quan sát được

**src/main/java/example/demo/MarkerInterceptor.java**

~~~java
package example.demo;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.servlet.HandlerInterceptor;

public class MarkerInterceptor implements HandlerInterceptor {

    @Override
    public boolean preHandle(HttpServletRequest request,
                             HttpServletResponse response,
                             Object handler) {
        response.setHeader("X-Mvc-Config", "applied");
        return true;
    }
}
~~~

**Giải thích:** preHandle trả **true** để request đi tiếp tới handler. Header X-Mvc-Config chỉ giúp kiểm chứng interceptor đã chạy; trong ứng dụng thực tế có thể thay bằng đo thời gian, correlation/tracing hay logic cross-cutting phù hợp. **Đừng dùng MVC interceptor làm lớp bảo vệ phân quyền chính**; cân nhắc Spring Security/Servlet filter chain.

### 5.4. WebMvcConfigurer thêm bốn loại cấu hình

**src/main/java/example/demo/WebConfig.java**

~~~java
package example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.ViewControllerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConfig implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new MarkerInterceptor())
                .addPathPatterns("/api/**");
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/docs/**")
                .addResourceLocations("classpath:/manual/");
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("http://localhost:5173")
                .allowedMethods("GET")
                .allowedHeaders("Accept", "Content-Type");
    }

    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        registry.addRedirectViewController(
                "/welcome", "/api/greet");
    }
}
~~~

**Giải thích theo callback:**

- **addInterceptors:** chỉ các URL /api/** đi qua MarkerInterceptor; /docs/hello.txt không nhận header X-Mvc-Config do pattern không khớp.
- **addResourceHandlers:** URI /docs/hello.txt đọc resource **classpath:/manual/hello.txt**; URL mapping và resource location là hai khái niệm khác nhau.
- **addCorsMappings:** chỉ cho browser origin **http://localhost:5173** truy cập /api/** bằng các method phù hợp. Ví dụ không bật credentials.
- **addViewControllers:** /welcome trả về redirect tới /api/greet mà không cần một controller method riêng.
- **Không có @EnableWebMvc.** Boot vẫn là bên sở hữu MVC auto-configuration của ứng dụng mẫu.

### 5.5. Resource để thử phục vụ file

**src/main/resources/manual/hello.txt** chứa chính xác:

~~~text
Tai nguyen tinh tu WebMvcConfigurer
~~~

### 5.6. Khởi động và kiểm chứng

Tại thư mục gốc của dự án Spring Initializr (có pom.xml và Maven wrapper), chạy:

~~~bash
# macOS / Linux
./mvnw spring-boot:run
~~~

Trên Windows, dùng lệnh tương ứng:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Ở terminal khác, gọi:

~~~bash
curl -i "http://localhost:8080/api/greet?name=An"
~~~

Response dự kiến có status 200, header **X-Mvc-Config: applied** và JSON body:

~~~json
{"message":"Xin chào An"}
~~~

Một số HTTP response headers khác và thứ tự có thể khác nhau theo server/Boot.

Kiểm tra static resource:

~~~bash
curl -i "http://localhost:8080/docs/hello.txt"
~~~

Body dự kiến:

~~~text
Tai nguyen tinh tu WebMvcConfigurer
~~~

Kiểm tra redirect:

~~~bash
curl -i "http://localhost:8080/welcome"
~~~

Status dự kiến thuộc nhóm **3xx**, cụ thể trong cấu hình redirect mặc định thường là **302**, và Location chỉ tới /api/greet (có thể được server biểu diễn thành URL tuyệt đối). Thêm **-L** để curl theo redirect nếu muốn thấy JSON cuối.

Kiểm tra CORS từ origin được phép:

~~~bash
curl -i \
  -H "Origin: http://localhost:5173" \
  "http://localhost:8080/api/greet"
~~~

Kỳ vọng response có **Access-Control-Allow-Origin: http://localhost:5173**. Với origin không được cho phép, browser không được trao quyền đọc cross-origin response theo policy này. **curl không thực thi chính sách CORS của browser**, nên curl vẫn có thể hiển thị response khi gọi trực tiếp; không dùng khả năng curl gửi request để kết luận CORS đã cho phép browser.

Mẫu chạy này chứng minh rằng một WebMvcConfigurer có thể bổ sung interceptor, static mapping, CORS và redirect trong ứng dụng Boot MVC **mà không phải chiếm toàn quyền thiết lập MVC**.

## 6. Spring MVC thuần với Java Config: cần @EnableWebMvc và bootstrap Servlet

Đối với **Spring Framework MVC không dùng Spring Boot**, thông thường cần bật MVC infrastructure và đăng ký DispatcherServlet với servlet container.

Java config ví dụ:

~~~java
package example.plainmvc;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
@EnableWebMvc
@ComponentScan("example.plainmvc")
public class WebConfig implements WebMvcConfigurer {
    // Có thể override addInterceptors(), addResourceHandlers()...
}
~~~

**Đây là đoạn cấu hình cho một ứng dụng Servlet khác, không phải thay thế file WebConfig của ứng dụng Boot ở phần trước.** Lớp @ComponentScan tìm controller/services trong package nêu ra. @EnableWebMvc bật MVC infrastructure và tập hợp các WebMvcConfigurer beans.

Có thể đăng ký DispatcherServlet bằng Java initializer:

~~~java
package example.plainmvc;

import org.springframework.web.servlet.support
        .AbstractAnnotationConfigDispatcherServletInitializer;

public class WebAppInitializer
        extends AbstractAnnotationConfigDispatcherServletInitializer {

    @Override
    protected Class<?>[] getRootConfigClasses() {
        return null;
    }

    @Override
    protected Class<?>[] getServletConfigClasses() {
        return new Class<?>[] { WebConfig.class };
    }

    @Override
    protected String[] getServletMappings() {
        return new String[] { "/" };
    }
}
~~~

**Phụ thuộc môi trường:** cần đóng gói ứng dụng theo mô hình servlet web app, cung cấp **spring-webmvc**, các dependency cần dùng và container hỗ trợ Jakarta Servlet tương thích với thế hệ Spring đang chạy. Với Spring Framework 6, dùng **jakarta.servlet.***, không dùng **javax.servlet.*** của thế hệ cũ. Đây là bộ khung bootstrap thực tế nhưng **chưa phải project WAR độc lập đầy đủ**: còn cần cấu hình build, controller và triển khai đến container. Không chạy trực tiếp bằng javac/java vì chưa có dependency/classpath và servlet runtime.

### Vai trò của initializer

- **getRootConfigClasses():** cấu hình context gốc (nếu cần). Ví dụ trả null để tập trung vào một web context.
- **getServletConfigClasses():** cấu hình của **DispatcherServlet WebApplicationContext**, chứa MVC beans/controller.
- **getServletMappings():** ánh xạ servlet tới "/", phục vụ controller theo URL.
- Container phát hiện WebApplicationInitializer qua cơ chế Servlet startup tương ứng và đăng ký DispatcherServlet.

**Vị trí context rất quan trọng:** MVC infrastructure và controller thường thuộc context của DispatcherServlet. Root ApplicationContext có thể chứa service/repository dùng chung; bean ở child context thấy bean của parent, còn parent không tự nhìn thấy bean của child. Đặt @EnableWebMvc vào context không đúng có thể khiến DispatcherServlet không thấy hạ tầng mong đợi hoặc tạo hai bản cấu hình khó debug.

## 7. Cấu hình XML tương đương: mvc:annotation-driven và web.xml

Trong ứng dụng Spring MVC dùng XML, vai trò bật annotation MVC tương ứng với @EnableWebMvc là:

~~~xml
<mvc:annotation-driven/>
~~~

Để XML có nghĩa và chạy được khi được nạp, cần namespace beans, mvc, context và cấu hình **DispatcherServlet**. Ví dụ **WEB-INF/spring-mvc.xml** dưới đây thể hiện cấu hình MVC hoàn chỉnh về mặt XML; controller và lớp interceptor được giả định có sẵn trong classpath của một dự án Servlet.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xmlns:mvc="http://www.springframework.org/schema/mvc"
       xmlns:context="http://www.springframework.org/schema/context"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd
           http://www.springframework.org/schema/mvc
           https://www.springframework.org/schema/mvc/spring-mvc.xsd
           http://www.springframework.org/schema/context
           https://www.springframework.org/schema/context/spring-context.xsd">

    <!-- Phát hiện @Controller, @Service và @Component. -->
    <context:component-scan base-package="example.plainmvc"/>

    <!-- Bật MVC annotation infrastructure. -->
    <mvc:annotation-driven/>

    <!-- Tương ứng addInterceptors(...). -->
    <mvc:interceptors>
        <mvc:interceptor>
            <mvc:mapping path="/api/**"/>
            <bean class="example.plainmvc.MarkerInterceptor"/>
        </mvc:interceptor>
    </mvc:interceptors>

    <!-- Tương ứng addResourceHandlers(...). -->
    <mvc:resources mapping="/docs/**"
                   location="classpath:/manual/"/>

    <!-- Tương ứng addViewControllers(...). -->
    <mvc:view-controller path="/welcome"
                         view-name="redirect:/api/greet"/>

    <!-- Tương ứng addCorsMappings(...). -->
    <mvc:cors>
        <mvc:mapping path="/api/**"
                     allowed-origins="http://localhost:5173"
                     allowed-methods="GET"
                     allowed-headers="Accept, Content-Type"/>
    </mvc:cors>
</beans>
~~~

Các class **example.plainmvc.MarkerInterceptor** và các controller cần được tạo tương ứng trong project XML; không nên lấy nguyên class package **example.demo** từ dự án Boot ở phần 5 mà bỏ qua khác biệt package. Chẳng hạn có thể viết MarkerInterceptor cùng mã ở ví dụ Boot rồi đổi package thành **example.plainmvc**. XML này là **bản đối chiếu cấu hình**, không phải ứng dụng runnable độc lập nếu thiếu các lớp Java và container.

Nếu chưa có Java initializer, một ứng dụng Servlet có thể khai báo servlet bằng **WEB-INF/web.xml**. Mẫu web.xml cho Servlet 6.0/Jakarta API:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
             https://jakarta.ee/xml/ns/jakartaee
             https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">

    <servlet>
        <servlet-name>dispatcher</servlet-name>
        <servlet-class>
            org.springframework.web.servlet.DispatcherServlet
        </servlet-class>
        <init-param>
            <param-name>contextConfigLocation</param-name>
            <param-value>/WEB-INF/spring-mvc.xml</param-value>
        </init-param>
        <load-on-startup>1</load-on-startup>
    </servlet>

    <servlet-mapping>
        <servlet-name>dispatcher</servlet-name>
        <url-pattern>/</url-pattern>
    </servlet-mapping>
</web-app>
~~~

**Giải thích:**

- Servlet container tạo **DispatcherServlet** cho mapping "/".
- DispatcherServlet đọc contextConfigLocation và khởi tạo **WebApplicationContext** từ spring-mvc.xml.
- Phần tử **mvc:annotation-driven** bật các bean cần cho @RequestMapping, @RequestBody, @ResponseBody, converter/validation phù hợp.
- **context:component-scan** tìm controller và các bean Java.
- XML cấu hình interceptors/resources/CORS/view-controller được áp dụng trong MVC context ấy.

Nếu dùng **AbstractAnnotationConfigDispatcherServletInitializer** (Java) thì không cần đồng thời cấu hình **cùng một DispatcherServlet** lại qua web.xml; cấu hình cả hai không có chủ ý có thể dẫn đến servlet/context lặp, mapping đụng nhau hoặc ứng dụng khởi động sai.

## 8. Đối chiếu trực tiếp Java Config và XML theo hành vi

### 8.1. Bật annotation-based MVC

Java:

~~~java
@Configuration
@EnableWebMvc
public class WebConfig {
}
~~~

XML:

~~~xml
<mvc:annotation-driven/>
~~~

Cả hai bật các thành phần MVC cơ bản trong bối cảnh Spring MVC thuần. **Nhưng** @Configuration/@EnableWebMvc tự chúng không khai báo component scanning; XML mvc:annotation-driven cũng không. Muốn controller được tìm thấy phải dùng @ComponentScan, context:component-scan hoặc đăng ký bean bằng cách khác.

### 8.2. Đăng ký interceptor

Java, trong lớp WebMvcConfigurer:

~~~java
@Override
public void addInterceptors(InterceptorRegistry registry) {
    registry.addInterceptor(new MarkerInterceptor())
            .addPathPatterns("/api/**");
}
~~~

XML:

~~~xml
<mvc:interceptors>
    <mvc:interceptor>
        <mvc:mapping path="/api/**"/>
        <bean class="example.plainmvc.MarkerInterceptor"/>
    </mvc:interceptor>
</mvc:interceptors>
~~~

Hai đoạn **tương đương về mục tiêu** khi class interceptor có cùng logic. Tuy nhiên có khác biệt kỹ thuật: XML mvc:interceptors khai báo **MappedInterceptor** beans có thể được phát hiện bởi các HandlerMapping khác trong context, còn callback Java đăng ký qua các HandlerMapping do MVC Java config quản lý. Khi tích hợp framework bổ sung, cần kiểm tra phạm vi áp dụng thay vì cho rằng luôn giống hệt.

**Không nhầm HandlerInterceptor với Servlet Filter**: Filter chạy trong servlet container filter chain, có thể bao phủ URL trước DispatcherServlet; HandlerInterceptor gắn với các handler MVC sau HandlerMapping. An ninh phân quyền nên giao cho lớp xử lý phù hợp, thường Spring Security/filter chain.

### 8.3. Phục vụ tài nguyên tĩnh

Java:

~~~java
@Override
public void addResourceHandlers(ResourceHandlerRegistry registry) {
    registry.addResourceHandler("/docs/**")
            .addResourceLocations("classpath:/manual/");
}
~~~

XML:

~~~xml
<mvc:resources mapping="/docs/**"
               location="classpath:/manual/"/>
~~~

Nếu file ở **src/main/resources/manual/hello.txt** thì request **/docs/hello.txt** trả file ấy khi resource được đóng gói lên classpath. Không lẫn **đường dẫn URL** /docs với **địa chỉ resource** classpath:/manual/.

Spring Boot MVC có các resource locations và welcome page mặc định riêng. Thêm @EnableWebMvc có thể thay đổi hành vi serving static content; trong Boot hãy ưu tiên dùng **WebMvcConfigurer** hoặc Boot properties tương ứng khi chỉ cần điều chỉnh.

### 8.4. CORS toàn cục cho MVC

Java:

~~~java
@Override
public void addCorsMappings(CorsRegistry registry) {
    registry.addMapping("/api/**")
            .allowedOrigins("http://localhost:5173")
            .allowedMethods("GET")
            .allowedHeaders("Accept", "Content-Type");
}
~~~

XML:

~~~xml
<mvc:cors>
    <mvc:mapping path="/api/**"
                 allowed-origins="http://localhost:5173"
                 allowed-methods="GET"
                 allowed-headers="Accept, Content-Type"/>
</mvc:cors>
~~~

Nếu browser gọi từ một origin khác, CORS policy có thể khiến trình duyệt chặn truy cập response hoặc preflight bị từ chối. Không được dùng CORS để xác thực người dùng. Nếu dùng cookies hoặc credentials, phải cấu hình cụ thể origin được tin cậy, credentials và bảo vệ CSRF/authorization theo đúng trường hợp; không kết hợp credentials với wildcard origin "*" tùy tiện.

### 8.5. View controller/redirect

Java:

~~~java
@Override
public void addViewControllers(ViewControllerRegistry registry) {
    registry.addRedirectViewController(
            "/welcome", "/api/greet");
}
~~~

XML theo mục tiêu tương tự:

~~~xml
<mvc:view-controller path="/welcome"
                     view-name="redirect:/api/greet"/>
~~~

Cả hai cho phép đường dẫn /welcome trả redirect mà không viết business controller. Không nên định nghĩa một annotated controller và view-controller cùng tranh quyền sở hữu một route, vì mapping ưu tiên và status lỗi có thể không như người viết mong đợi.

### 8.6. Formatter/Converter và validation

Java:

~~~java
@Override
public void addFormatters(FormatterRegistry registry) {
    registry.addConverter(String.class, Code.class,
            value -> new Code(value.trim()));
}
~~~

Đây là **method minh họa** trong WebMvcConfigurer, yêu cầu có kiểu **Code** được định nghĩa và import FormatterRegistry phù hợp, không phải đoạn Java độc lập. Nếu muốn tự chạy, có thể khai báo:

~~~java
public record Code(String value) {
}
~~~

Khi phương thức controller nhận @RequestParam Code, formatter/converter có thể chuyển text tham số thành đối tượng Code. Đây là **conversion khi binding HTTP tham số**, khác với JSON deserialization của @RequestBody.

XML dùng conversion service tùy biến gắn vào annotation-driven:

~~~xml
<mvc:annotation-driven conversion-service="conversionService"/>

<bean id="conversionService"
      class="org.springframework.format.support.FormattingConversionServiceFactoryBean">
    <property name="converters">
        <set>
            <bean class="example.plainmvc.StringToCodeConverter"/>
        </set>
    </property>
</bean>
~~~

**Yêu cầu bổ sung:** lớp StringToCodeConverter phải được cài đặt là Spring Converter<String, Code> và có constructor thích hợp; XML trên là ví dụ tích hợp, chưa đủ để chạy độc lập. Cấu hình validator có thể khai báo với thuộc tính validator của mvc:annotation-driven tùy schema; hỗ trợ Bean Validation còn phụ thuộc provider/dependency và configuration.

### 8.7. HTTP message converters và content negotiation

Trong Java config **Spring Framework 6.x**, phương thức:

~~~java
@Override
public void extendMessageConverters(
        List<HttpMessageConverter<?>> converters) {
    // Bổ sung hoặc tinh chỉnh danh sách converter đã thiết lập.
}
~~~

là một hook điều chỉnh. **configureMessageConverters(List...)** có semantics khác: việc tự cung cấp converter có thể làm mất đăng ký mặc định trong Spring Framework thuần nếu bạn không chủ động bổ sung lại.

Trong XML có thể cấu hình message converters trong **mvc:annotation-driven**:

~~~xml
<mvc:annotation-driven>
    <mvc:message-converters register-defaults="true">
        <!-- Bean converter tùy chỉnh có thể thêm ở đây. -->
    </mvc:message-converters>
</mvc:annotation-driven>
~~~

Đây là **đoạn cấu hình minh họa**; không phải yêu cầu bắt buộc. Hãy chỉ tạo converter bean khi thực sự cần. Trong Boot, cơ chế **HttpMessageConverters** và việc đăng ký converter bean của Boot thường phù hợp hơn việc tự thay thế toàn bộ danh sách.

**Lưu ý phiên bản:** API cấu hình message converters đang thay đổi giữa Spring Framework 6.x và 7.x; ở Spring 7, các hook nhận **List<HttpMessageConverter<?>>** đã bị deprecated để ưu tiên builder-based API. Khi nâng cấp cần đọc Javadoc cùng phiên bản thay vì áp dụng nguyên xi ví dụ 6.x.

XML namespace MVC tiếp tục là cách đọc/duy trì nhiều codebase cũ, nhưng **từ Spring Framework 7.0, hỗ trợ XML MVC namespace đã được đánh dấu deprecated**; tài liệu Spring cũng lưu ý XML config không tiếp tục được cập nhật để bắt kịp mọi tùy chọn Java config mới. Với dự án mới, ưu tiên Java config; khi bảo trì XML, cân nhắc lộ trình di chuyển từng phần có kiểm chứng.

## 9. Vì sao @EnableWebMvc có thể gây lỗi trong Spring Boot?

Giả sử bạn bắt đầu với ứng dụng Boot MVC có resource:

~~~text
src/main/resources/static/css/site.css
~~~

Khi dùng auto-configuration của Boot, URL **/css/site.css** thường được phục vụ theo resource mapping mặc định. Sau đó một nhà phát triển thêm:

~~~java
@Configuration
@EnableWebMvc
public class CustomWebConfig implements WebMvcConfigurer {
    // Chỉ muốn đăng ký một interceptor.
}
~~~

Ứng dụng có thể **vẫn khởi động** và controller JSON vẫn chạy, nhưng một phần cấu hình MVC do Boot cung cấp (bao gồm static resource mapping hoặc các customizations liên quan) có thể **không còn hoạt động như trước**. Vì vậy không nên coi việc bật @EnableWebMvc như “bật thêm một tiện ích” nhỏ.

### Cách sửa khi chỉ muốn thêm interceptor

~~~java
@Configuration
public class CustomWebConfig implements WebMvcConfigurer {
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new MarkerInterceptor());
    }
}
~~~

Đây là **mã minh họa** cần import và định nghĩa MarkerInterceptor như ví dụ ở phần 5. Điểm thay đổi cốt lõi là **bỏ @EnableWebMvc**, giữ cấu hình MVC auto của Boot rồi áp dụng callback.

**@EnableWebMvc có phải luôn là lỗi?** Không. Khi ứng dụng Boot có yêu cầu đặc biệt và đội phát triển **cố ý tự quản lý toàn bộ Spring MVC**, có thể dùng @EnableWebMvc, nhưng phải hiểu các phần do Boot không còn cung cấp tự động và khai báo/kiểm thử lại những gì cần thiết.

### extends WebMvcConfigurationSupport cũng là lựa chọn toàn quyền

~~~java
@Configuration
public class FullControlMvcConfig
        extends WebMvcConfigurationSupport {
    // Có quyền override các hooks và beans hạ tầng cấp thấp.
}
~~~

Đây là **đoạn minh họa không hoàn chỉnh**. Việc có bean WebMvcConfigurationSupport có thể khiến điều kiện auto-configuration MVC của Boot không còn đáp ứng. Không dùng cách này chỉ để thêm CORS hoặc formatter.

Nếu cần tùy biến sâu **RequestMappingHandlerMapping**, **RequestMappingHandlerAdapter** hoặc **ExceptionHandlerExceptionResolver** nhưng vẫn giữ MVC customizations của Boot, xem cơ chế **WebMvcRegistrations** của Spring Boot. Đây là nhánh nâng cao, cần kiểm chứng toàn bộ kết hợp framework/Boot cùng phiên bản.

## 10. So sánh đường đi cấu hình ở Boot và Spring MVC thuần

~~~text
A. Spring Boot + Spring MVC
@SpringBootApplication
      |
SpringApplication + AutoConfiguration
      |
WebMvcAutoConfiguration, DispatcherServletAutoConfiguration
      |
WebMvcConfigurer beans bổ sung callback (KHÔNG @EnableWebMvc)
      |
DispatcherServlet -> HandlerMapping / Adapter / Converter...
      |
Controller

B. Spring Framework MVC thuần — Java
Servlet container
      |
WebApplicationInitializer đăng ký DispatcherServlet
      |
@Configuration + @EnableWebMvc
      |
DelegatingWebMvcConfiguration nhận WebMvcConfigurer beans
      |
MVC infrastructure -> Controller

C. Spring Framework MVC thuần — XML
Servlet container
      |
web.xml đăng ký DispatcherServlet và XML config location
      |
spring-mvc.xml:
  context:component-scan
  mvc:annotation-driven
  mvc:interceptors / resources / cors / view-controller...
      |
MVC infrastructure -> Controller
~~~

**A** là đường hiện đại, ít cấu hình thủ công. **B/C** cho thấy những bộ phận Boot đã tự cung cấp hoặc thay bằng auto-configuration. Khi debug, hãy xác định dự án thuộc nhánh nào trước khi chỉnh annotation/XML.

## 11. Kiểm thử cấu hình thay vì đoán hiệu lực

### Bài thử HTTP cho ví dụ Boot

Sau khi chạy ứng dụng mẫu ở phần 5:

1. GET **/api/greet?name=An** phải trả JSON thông điệp chào và header **X-Mvc-Config: applied**.
2. GET **/docs/hello.txt** phải trả nội dung file từ classpath.
3. GET **/welcome** phải redirect đến **/api/greet**.
4. Request có **Origin: http://localhost:5173** tới /api/greet phải nhận CORS header tương ứng.
5. Origin khác không được mặc nhiên cho phép truy cập cross-origin trong browser.
6. Kiểm tra behavior khi đổi/sửa cấu hình; không thử nghiệm bằng cách giữ đồng thời nhiều lớp cấu hình trùng trách nhiệm.

### Khi muốn viết test tự động

Với Spring Boot 3.x dùng **spring-boot-starter-test**, có thể kiểm tra endpoint bằng **@SpringBootTest + @AutoConfigureMockMvc** hoặc dùng các test slices phù hợp. Test MVC có hai lớp ý nghĩa:

- **Slice test @WebMvcTest:** tập trung controller và một phần MVC infrastructure; không bảo đảm tải mọi bean cấu hình tùy chỉnh của toàn ứng dụng. Nếu test cần một WebMvcConfigurer/interceptor cụ thể, phải chủ động import/thiết lập trong slice.
- **Full-context test @SpringBootTest:** phù hợp để xác nhận integration của auto-configuration, converter, handler mapping, MVC config. Khi kết hợp MockMvc, cần annotation/config tương ứng.

Một test tự động minh họa cho ứng dụng Boot ở phần 5:

~~~java
package example.demo;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet
        .AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class MvcConfigTest {

    @Autowired
    MockMvc mvc;

    @Test
    void interceptorAndControllerAreConfigured() throws Exception {
        mvc.perform(get("/api/greet").param("name", "An"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "X-Mvc-Config", "applied"))
                .andExpect(jsonPath("$.message")
                        .value("Xin chào An"));
    }
}
~~~

Đây là **lớp test độc lập bên trong project Boot 3.x của ví dụ**, đặt ở **src/test/java/example/demo/MvcConfigTest.java**, yêu cầu dependency Spring Boot Test và JUnit/Jackson/JsonPath qua starter test. Nếu dùng Boot 4.x, package test auto-configuration có thể khác; tạo test từ dependency và import đúng version tương ứng. Để chạy:

~~~bash
# macOS / Linux
./mvnw test
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd test
~~~

**Kỳ vọng:** test pass nếu project khai báo đúng dependencies, package scan và các file của ví dụ. Không nên ghi log chạy thử cụ thể khi chưa thực sự chạy trong môi trường đó.

### Debug khi cấu hình không có hiệu lực

- Kiểm tra **WebConfig có thực sự là bean không**: package, component scan, @Import hoặc XML registration.
- Kiểm tra ứng dụng **Servlet MVC hay WebFlux**: WebMvcConfigurer không dùng để cấu hình WebFlux; reactive stack có **WebFluxConfigurer**.
- Kiểm tra có vô tình thêm **@EnableWebMvc** hoặc extends **WebMvcConfigurationSupport** trong Boot không.
- Đọc **auto-configuration condition report** (Boot có thể hiển thị qua startup debug/Actuator conditions tùy setup) để xác định WebMvcAutoConfiguration có chạy.
- Kiểm tra servlet **context path, servlet mapping và handler patterns** trước khi kết luận addInterceptors/addResourceHandlers không hoạt động.
- Nếu dùng XML, kiểm tra XML được **DispatcherServlet context** thực sự nạp, namespace và schema đúng, các class tham chiếu có trong classpath.
- Khi có nhiều DispatcherServlet hoặc nhiều ApplicationContexts, xác định context sở hữu controller và config.
- Kiểm tra xung đột **@CrossOrigin với global CORS**, nhiều converters, view resolvers hoặc static URL patterns.
- Kiểm tra lỗi app khởi động và exception chi tiết trước khi đổi framework version.
- Đừng dùng interceptor để bảo vệ quyền truy cập; khi security filter xử lý request trước MVC, phản hồi có thể được tạo trước khi interceptor chạy.

## 12. Lưu ý khi di chuyển XML sang Java config

Di chuyển cấu hình cần **đối chiếu hành vi**, không chỉ thay cú pháp:

1. Xác định servlet mapping, WebApplicationContext, root context và nơi đang load XML.
2. Lập danh sách những chức năng trong XML: annotation-driven, scan, interceptors, formatter, validation, converter, view resolver, resources, CORS, redirect và cấu hình nâng cao.
3. Với ứng dụng **Spring MVC thuần**, chuyển mvc:annotation-driven sang **@EnableWebMvc**, các phần tử bổ sung sang WebMvcConfigurer hoặc beans tương ứng; vẫn phải bootstrap DispatcherServlet.
4. Với ứng dụng **Spring Boot**, tận dụng MVC auto-configuration trước; chuyển các tùy biến hữu ích sang **WebMvcConfigurer không gắn @EnableWebMvc**, không bê nguyên annotation từ cấu hình thuần vào một cách máy móc.
5. Nếu XML có custom message converters, mapping rules hoặc handler adapter, so sánh các default và thử các request JSON/XML, validation/error cases sau di chuyển.
6. So sánh security/filter order, CORS preflight, static resources, cache headers, redirect URLs và view rendering.
7. Có thể tồn tại cấu hình XML và Java **cùng lúc**, nhưng tránh đăng ký trùng servlet, component scan, handler mappings, converter/interceptor vì kết quả phụ thuộc ownership và precedence.
8. Giữ phiên bản nhất quán: Spring 5/javax.servlet và Spring 6+/jakarta.servlet là hai thế hệ API khác nhau; nâng cấp cùng thư viện/container thích hợp.

Một ví dụ bảng kiểm cấu hình:

| Trước (XML) | Sau (Java/Boot) | Test cần giữ |
|---|---|---|
| mvc:annotation-driven | @EnableWebMvc (thuần); Boot MVC auto-config | Annotation controller, binding, JSON |
| context:component-scan | @ComponentScan hoặc @SpringBootApplication scan | Controller/service được đăng ký |
| mvc:interceptors | addInterceptors | Header/logging và include/exclude URL |
| mvc:resources | addResourceHandlers hoặc Boot static mapping | File có thể GET, content type/cache đúng |
| mvc:view-controller | addViewControllers | Redirect/forward và status |
| mvc:cors | addCorsMappings / @CrossOrigin | Allowed Origin, preflight và credentials |
| conversion-service | addFormatters / Converter beans | Query/form binding và validation |
| ViewResolver beans | configureViewResolvers / Boot view integration | HTML view được render |
| Custom HttpMessageConverters | Custom converter/Boot HttpMessageConverters | JSON/XML, Accept, error bodies |

## 13. Những hiểu lầm và lỗi phổ biến

**“@EnableWebMvc để bật mọi tính năng web trong Spring Boot.”** Không đúng. Boot MVC thường đã bật chức năng đó; @EnableWebMvc có thể làm mất các customizations tự động của Boot.

**“WebMvcConfigurer thay thế DispatcherServlet.”** Không đúng. Configurer chỉ mô tả callbacks cho MVC infrastructure. Servlet vẫn cần được Boot, initializer hoặc web.xml đăng ký.

**“Có @EnableWebMvc là controller sẽ tự được scan.”** Không đúng. Phải có component scan hoặc bean registration thích hợp.

**“@EnableWebMvc và mvc:annotation-driven là hai hệ hoàn toàn không liên quan.”** Không đúng. Cả hai bật hỗ trợ annotation-based MVC theo hai kiểu cấu hình; khác biệt ở cách khai báo và phạm vi tính năng/schema cụ thể.

**“XML mvc:annotation-driven đăng ký DispatcherServlet.”** Không đúng. Servlet registration là một bước riêng.

**“Thêm một converter bằng configureMessageConverters không ảnh hưởng defaults.”** Có thể sai trong Java MVC configuration thế hệ 6.x; phải phân biệt thay thế với mở rộng. Đọc Javadoc đúng version. Trong Boot nên ưu tiên cơ chế message converter integration của Boot nếu muốn giữ mặc định.

**“WebMvcConfigurer áp dụng cho WebFlux vì cả hai đều dùng Spring Web.”** Sai. WebFlux dùng WebFluxConfigurer và reactive codecs; MVC dùng Servlet stack.

**“Interceptors là nơi lý tưởng để thực hiện authorization.”** Sai trong nhiều kiến trúc; MVC interceptors có thể không khớp toàn bộ đường đi request hoặc security requirements. Dùng Spring Security/filter chain phù hợp.

**“CORS giúp bảo vệ API khỏi client ngoài.”** Không đúng. CORS là chính sách browser đọc cross-origin response; client không phải browser có thể gửi HTTP request bình thường. Authentication/authorization vẫn cần thiết.

**“Có thể chuyển XML sang Java theo tìm-thay chuỗi.”** Không đáng tin. Phải xét scope của context, thứ tự bean/configurer, converters, servlet mapping, Boot defaults và testing.

**“Spring MVC XML namespace luôn được phát triển ngang bằng Java config ở mọi bản tương lai.”** Không đúng. Kể từ Spring Framework 7.0, MVC XML namespace deprecated, và các tính năng mới không nhất thiết được phản ánh đầy đủ ở XML.

## 14. Tự kiểm tra

1. **Trong Spring Boot, chỉ muốn thêm interceptor, dùng gì?** @Configuration implements WebMvcConfigurer; thông thường không dùng @EnableWebMvc.
2. **Trong Spring MVC thuần, @EnableWebMvc có tự mở cổng HTTP không?** Không; cần DispatcherServlet registration và container.
3. **XML nào gần với @EnableWebMvc nhất?** mvc:annotation-driven, đặt trong XML thuộc context MVC phù hợp.
4. **XML nào tương ứng addResourceHandlers?** mvc:resources.
5. **Vì sao dự án Boot bị 404 cho file static sau khi thêm @EnableWebMvc?** Có thể Boot MVC auto-configuration bị thay bằng cấu hình do ứng dụng tự quản lý, dẫn đến thiếu resource mapping cần thiết.
6. **WebMvcConfigurer có cần @Component/@Configuration không?** Bản triển khai phải trở thành bean Spring; annotation hoặc explicit registration là cách thông dụng.
7. **Đang dùng Spring WebFlux có được dùng WebMvcConfigurer không?** Không để cấu hình reactive stack; xem WebFluxConfigurer.
8. **Hai DispatcherServlet có mặc định chung một WebApplicationContext không?** Không; mỗi servlet có thể có child context riêng, cần hiểu bean visibility.
9. **XML + Java config có thể cùng tồn tại không?** Có, nhưng phải quản lý rõ ownership và tránh khai báo trùng.
10. **Khác biệt giữa configureMessageConverters và extendMessageConverters trong Spring 6.x?** Một bên cấu hình danh sách có thể làm mất defaults; một bên cho phép mở rộng/điều chỉnh danh sách đã cấu hình.
11. **Khi nào cân nhắc WebMvcConfigurationSupport/WebMvcRegistrations?** Khi có nhu cầu cấu hình hạ tầng cấp thấp rõ ràng; kiểm tra ảnh hưởng đến Boot auto-configuration.
12. **Khi di chuyển XML sang Boot, có nên chuyển nguyên mvc:annotation-driven thành @EnableWebMvc?** Thường không; dùng Boot MVC auto-config và chuyển các customizations cần giữ sang WebMvcConfigurer.

## 15. Tài liệu chính thức

- [Spring Framework — Enable MVC Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/enable.html): @EnableWebMvc, mvc:annotation-driven, lưu ý với Boot và deprecation XML ở Spring 7.
- [Spring Framework — MVC Config API](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/customize.html): WebMvcConfigurer.
- [Spring Framework — Interceptors](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/interceptors.html): mapping interceptor và khác biệt Java/XML.
- [Spring Framework — Static Resources](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html): resource handlers.
- [Spring Framework — View Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/view-controller.html): view controller và redirect.
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): cors mappings và browser policy.
- [Spring Framework — Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/message-converters.html): converter customization, lưu ý version API.
- [Spring Framework — Advanced Java Config](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/advanced-java.html): DelegatingWebMvcConfiguration và WebMvcConfigurationSupport.
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): MVC auto-configuration, WebMvcConfigurer không @EnableWebMvc và tùy biến sâu.
- [Spring Framework — Web MVC Reference](https://docs.spring.io/spring-framework/reference/web/webmvc.html): toàn bộ vòng đời và kiến trúc Spring MVC.

**Ghi nhớ:** **@EnableWebMvc bật MVC Java infrastructure**, **WebMvcConfigurer thêm các callback tùy chỉnh**, **mvc:annotation-driven và các mvc:* khác là tuyến XML**, còn **Spring Boot thường tự cấu hình MVC và chỉ cần WebMvcConfigurer để mở rộng**.

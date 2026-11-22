# Ảnh hưởng của @EnableWebMvc và WebMvcConfigurationSupport trong Spring Boot

## Mục tiêu học tập

Khi xây dựng ứng dụng Spring Boot dùng Spring MVC, bạn thường không cần kích hoạt MVC bằng tay. Spring Boot đã cấu hình MVC mặc định và cho phép mở rộng qua **WebMvcConfigurer**. Việc thêm **@EnableWebMvc** hoặc một bean kế thừa **WebMvcConfigurationSupport** có thể làm thay đổi hoàn toàn nguồn cấu hình MVC. Đây là nguyên nhân thường gặp khi một ứng dụng trước đó phục vụ được file tĩnh hoặc trang index nhưng sau khi thêm một class cấu hình lại trả HTTP 404.

Sau bài này, bạn có thể:

- Giải thích Spring Boot MVC auto-configuration khác với Spring Framework MVC Java configuration ở đâu.
- Trình bày quan hệ giữa **@EnableWebMvc**, **DelegatingWebMvcConfiguration** và **WebMvcConfigurationSupport**.
- Hiểu vì sao bean kiểu WebMvcConfigurationSupport khiến **WebMvcAutoConfiguration** của Spring Boot rút lui.
- Phân biệt tính năng thực sự bị ảnh hưởng với tính năng MVC cơ bản vẫn tiếp tục hoạt động.
- Chọn **WebMvcConfigurer** để mở rộng MVC mà vẫn dùng các mặc định của Spring Boot.
- Nhận biết tình huống có thể chủ động dùng @EnableWebMvc hoặc kế thừa cấu hình MVC nền tảng.
- Kiểm tra, khôi phục và phòng tránh lỗi cấu hình liên quan tới static resources, JSON, formatter, interceptor, CORS và view resolver.

## 1. Bức tranh cấu hình Spring MVC trong Spring Boot

Spring MVC là web framework của Spring Framework, triển khai theo Servlet API và sử dụng **DispatcherServlet** để tiếp nhận request, phân giải handler, gọi controller và tạo response. Spring Framework có sẵn hạ tầng cấu hình MVC. Spring Boot đặt thêm một lớp auto-configuration để người phát triển không phải tự đăng ký và tinh chỉnh mọi thành phần MVC.

Trong ứng dụng Spring Boot Servlet có starter MVC thích hợp, khi điều kiện được đáp ứng, **WebMvcAutoConfiguration** thiết lập một số tiện ích bên trên cấu hình MVC của Spring Framework:

- Đăng ký và tích hợp các view resolver phù hợp.
- Thiết lập cách phục vụ tài nguyên tĩnh, thường từ classpath:/static/, classpath:/public/ và các vị trí mặc định khác.
- Hỗ trợ trang chào mừng index.html khi cấu hình và tài nguyên phù hợp.
- Kết hợp các Converter, Formatter và HTTP message converter với cấu hình/bean của ứng dụng.
- Tích hợp thêm các tùy chỉnh Web MVC của Spring Boot, chẳng hạn một số cơ chế data binding, resource handling và property liên quan.

Mức chi tiết có thể thay đổi theo phiên bản Spring Boot; vì vậy không nên xem mọi tiện ích nêu trên như một danh sách API ổn định tuyệt đối qua tất cả các major version.

Mô hình thông thường:

~~~text
SpringApplication
   |
   +-- Servlet web application
   |
   +-- Spring Framework MVC infrastructure
   |       |
   |       +-- DispatcherServlet
   |       +-- HandlerMapping / HandlerAdapter
   |       +-- HandlerExceptionResolver
   |       +-- message conversion / validation / view resolution
   |
   +-- Spring Boot WebMvcAutoConfiguration
           |
           +-- MVC defaults and integrations
           +-- static resources and welcome page support
           +-- available converters, formatters, view resolvers
           +-- callbacks supplied by WebMvcConfigurer beans
~~~

Cần ghi nhớ: **Spring Boot MVC auto-configuration là phần mở rộng**, còn **Spring MVC infrastructure** là nền tảng. Mất phần auto-configuration không đồng nghĩa toàn bộ controller MVC dừng hoạt động.

## 2. @EnableWebMvc thực hiện điều gì?

**@EnableWebMvc** là annotation của Spring Framework, nằm trong package:

~~~java
org.springframework.web.servlet.config.annotation.EnableWebMvc
~~~

Nó được dùng để kích hoạt cấu hình Spring MVC theo Java Config. Về cơ chế, annotation này import **DelegatingWebMvcConfiguration**, một class mở rộng **WebMvcConfigurationSupport**:

~~~text
@EnableWebMvc
     |
     v
@Import(DelegatingWebMvcConfiguration.class)
     |
     v
DelegatingWebMvcConfiguration
     |
     +-- extends WebMvcConfigurationSupport
     |
     +-- collects WebMvcConfigurer beans
     |
     +-- registers core Spring MVC infrastructure
~~~

Nhờ đó, Spring Framework vẫn đăng ký hạ tầng cần thiết cho controller annotation như @Controller, @RestController, @RequestMapping, các handler adapter và resolver. Nếu các thư viện hỗ trợ có trên classpath, các converter mặc định của Spring Framework có thể vẫn được cấu hình.

Trong dự án Spring Framework thuần không dùng Spring Boot, @EnableWebMvc là một lựa chọn hợp lý để bật MVC Java configuration. Nhưng ở dự án Spring Boot, nó thường là một tín hiệu rằng ứng dụng **muốn tự kiểm soát cấu hình MVC** thay vì sử dụng các mặc định MVC của Boot.

Ví dụ cấu hình đưa ứng dụng Boot sang chế độ tự quản MVC:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
public class FullMvcConfiguration {
}
~~~

Class trên chỉ là minh họa quyết định cấu hình, **không phải** lựa chọn khuyến nghị cho một ứng dụng Spring Boot thông thường.

## 3. Vì sao WebMvcAutoConfiguration của Spring Boot bị vô hiệu hóa?

Spring Boot áp dụng conditional auto-configuration. Một điều kiện chủ chốt của cấu hình MVC là **@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)**. Có thể hiểu logic ở mức khái niệm như sau:

~~~java
// Mã minh họa điều kiện, không phải toàn bộ source WebMvcAutoConfiguration:
@ConditionalOnMissingBean(WebMvcConfigurationSupport.class)
class WebMvcAutoConfiguration {
    // Spring Boot MVC integrations
}
~~~

Trường hợp bình thường, khi chưa có bean WebMvcConfigurationSupport do ứng dụng tự cung cấp, điều kiện này cho phép Boot tham gia cấu hình MVC.

Khi đặt @EnableWebMvc:

1. Annotation import DelegatingWebMvcConfiguration.
2. DelegatingWebMvcConfiguration kế thừa WebMvcConfigurationSupport.
3. Spring thấy bean cấu hình thuộc loại WebMvcConfigurationSupport.
4. Điều kiện missing-bean không còn thỏa mãn.
5. WebMvcAutoConfiguration của Spring Boot rút lui, nhường cấu hình MVC cho Spring Framework và class của ứng dụng.

Khi tự khai báo một class **@Configuration extends WebMvcConfigurationSupport**, điều kiện cũng không còn thỏa mãn, ngay cả khi class đó **không có @EnableWebMvc**.

Đây là quan hệ nguyên nhân và kết quả chính của bài học:

~~~text
WebMvcConfigurer alone
        |
        +--> does NOT provide WebMvcConfigurationSupport
        |
        +--> Spring Boot MVC auto-configuration can remain active

@EnableWebMvc
        |
        +--> imports DelegatingWebMvcConfiguration
        |      (a WebMvcConfigurationSupport subtype)
        |
        +--> Spring Boot WebMvcAutoConfiguration backs off

@Configuration extends WebMvcConfigurationSupport
        |
        +--> provides WebMvcConfigurationSupport directly
        |
        +--> Spring Boot WebMvcAutoConfiguration backs off
~~~

**Phân biệt phạm vi:** Điều kiện trên liên quan đến **WebMvcAutoConfiguration**. Nó không tự vô hiệu hóa mọi Spring Boot auto-configuration khác như datasource, embedded server, logging hay toàn bộ Actuator. Mỗi thành phần Boot có điều kiện riêng.

## 4. Điều gì thay đổi sau khi thêm @EnableWebMvc?

Không nên kết luận đơn giản rằng "có @EnableWebMvc thì Spring MVC hỏng". Ứng dụng có thể khởi động, DispatcherServlet vẫn nhận request và @RestController vẫn trả kết quả. Phần thay đổi là **những tiện ích tự động và tích hợp riêng của Boot dành cho MVC** không còn được tạo theo cách mặc định.

| Khía cạnh | Boot MVC mặc định | Sau @EnableWebMvc hoặc WebMvcConfigurationSupport tùy chỉnh |
|---|---|---|
| DispatcherServlet và controller | Được Boot và Spring MVC cấu hình tự động | Hạ tầng MVC cơ bản vẫn có thể hoạt động nhờ cấu hình Spring Framework |
| Resource handler cho static file | Boot đăng ký các mapping/vị trí tài nguyên mặc định | Không nên kỳ vọng mapping tài nguyên của Boot còn hoạt động; thường cần tự đăng ký |
| Trang index.html chào mừng | Boot có cơ chế welcome page riêng | Cơ chế welcome page của Boot có thể không còn |
| View resolver | Boot tích hợp các resolver theo classpath và cấu hình | Chỉ còn những resolver do cấu hình MVC nền tảng/ứng dụng thực sự cung cấp |
| Converter / Formatter | Boot đóng góp bean và mặc định riêng | Phụ thuộc MVC Java Config, classpath và cấu hình tự thêm |
| JSON qua Jackson | Có tích hợp Boot khi thư viện phù hợp hiện diện | Có thể vẫn hoạt động qua converter Spring Framework; không mặc định khẳng định JSON bị tắt |
| MVC properties trong application.properties | Nhiều thuộc tính được Boot áp dụng qua MVC auto-config | Một số thuộc tính phụ thuộc phần MVC auto-config có thể không còn tác dụng như kỳ vọng |
| WebMvcConfigurer bean | Bổ sung vào cấu hình MVC của Boot | Có thể vẫn được DelegatingWebMvcConfiguration sử dụng; không khôi phục tự động các default riêng của Boot |

Ví dụ điển hình: file **src/main/resources/static/logo.png** được truy cập bằng **/logo.png** ở ứng dụng MVC mặc định. Sau khi thêm @EnableWebMvc, resource handler mặc định do Spring Boot cung cấp có thể biến mất và request trả 404 cho đến khi ứng dụng bổ sung mapping tương đương.

Những nhận định cần tránh:

- "Thêm @EnableWebMvc sẽ luôn làm REST API trả 404": sai; controller mapping có thể vẫn hoạt động.
- "Thêm @EnableWebMvc sẽ luôn làm JSON mất hoàn toàn": sai; JSON phụ thuộc các converter hiện có.
- "Thêm @EnableWebMvc là tắt Spring Boot": sai; chỉ nói đến các cấu hình thỏa điều kiện cụ thể.
- "Chỉ cần implements WebMvcConfigurer là Boot cũng rút lui": sai; đây là cơ chế mở rộng được Boot khuyến nghị.
- "Xóa @EnableWebMvc luôn đủ để sửa mọi thứ": chưa chắc; một bean WebMvcConfigurationSupport khác cũng có thể khiến Boot rút lui.

## 5. Cách khuyến nghị: dùng WebMvcConfigurer mà không có @EnableWebMvc

Với phần lớn ứng dụng Spring Boot, nên tạo **@Configuration implements WebMvcConfigurer** và chỉ override những callback cần dùng.

Các callback tiêu biểu:

| Callback | Mục đích |
|---|---|
| addInterceptors | Đăng ký HandlerInterceptor cho request của Spring MVC |
| addCorsMappings | Bổ sung chính sách CORS cho route |
| addFormatters | Đăng ký Converter hoặc Formatter |
| addResourceHandlers | Thêm cách phục vụ tài nguyên tĩnh cho đường dẫn riêng |
| addViewControllers | Tạo view controller đơn giản hoặc redirect |
| configurePathMatch | Tùy biến một số quy tắc path matching |
| configureAsyncSupport | Cấu hình hỗ trợ xử lý Servlet async |
| extendMessageConverters | Tinh chỉnh danh sách converter sau khi đã được cấu hình (xem khác biệt API theo phiên bản) |

### Ví dụ minh họa chạy được

Giả sử dùng dự án được tạo bằng Spring Initializr, Java 17+, Spring Boot 3.x cùng dependency Spring Web (spring-boot-starter-web). Các file Java dưới đây nằm trong cùng package com.example.mvc, nên có thể được component scanning phát hiện.

**DemoApplication.java**:

~~~java
package com.example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**GreetingController.java**:

~~~java
package com.example.mvc;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/api/hello")
    public Map<String, String> hello() {
        return Map.of("message", "Xin chào MVC");
    }
}
~~~

**MvcCustomization.java**:

~~~java
package com.example.mvc;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.ViewControllerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcCustomization implements WebMvcConfigurer {

    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        registry.addRedirectViewController("/start", "/api/hello");
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://client.example")
                .allowedMethods("GET");
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/docs/**")
                .addResourceLocations("classpath:/docs/");
    }
}
~~~

Không đặt @EnableWebMvc ở class này hoặc class cấu hình khác. Mục tiêu là mở rộng MVC mà vẫn để Spring Boot xử lý auto-configuration.

Tạo hai file tài nguyên tùy chọn:

~~~text
src/main/resources/static/readme.txt
src/main/resources/docs/guide.txt
~~~

Ví dụ nội dung file **readme.txt** là **Boot static**, còn **guide.txt** là **Tài liệu nội bộ**.

Chạy ứng dụng từ thư mục project:

~~~bash
./mvnw spring-boot:run
~~~

Trên Windows với Maven Wrapper:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Thử endpoint:

~~~bash
curl -i http://localhost:8080/api/hello
curl -i http://localhost:8080/start
curl -i http://localhost:8080/readme.txt
curl -i http://localhost:8080/docs/guide.txt
~~~

Với starter và cấu hình nêu trên, kết quả dự kiến:

- GET /api/hello trả HTTP 200 cùng JSON có thuộc tính message bằng **Xin chào MVC**.
- GET /start trả HTTP redirect đến /api/hello; có thể xem header Location bằng **curl -i**.
- GET /readme.txt có thể được Boot phục vụ từ thư mục static mặc định.
- GET /docs/guide.txt được phục vụ từ resource handler vừa khai báo.

Chính sách CORS của ví dụ chỉ cho phép origin https://client.example đối với route /api/**; nó không có nghĩa cấm mọi lệnh curl không chứa Origin, cũng không thay thế cấu hình CORS khi Spring Security tham gia chuỗi xử lý request.

Nếu dự án thuộc Spring Boot 4.x, hãy dùng starter MVC và các API tương ứng với major version đang chạy. Cơ chế WebMvcConfigurer không thêm @EnableWebMvc vẫn là nguyên tắc chính, nhưng tên starter và một số API converter có thể thay đổi theo phiên bản.

## 6. So sánh trước và sau bằng một tình huống thực tế

Giả sử ứng dụng đã hoạt động với:

~~~text
src/main/resources/static/index.html
src/main/resources/static/assets/app.js
~~~

Trong cấu hình Spring Boot MVC mặc định, hệ thống thường có:

~~~text
GET /               -> welcome page index.html
GET /assets/app.js  -> static JavaScript
GET /api/hello      -> GreetingController
~~~

Một lập trình viên muốn thêm interceptor, nhưng lại viết:

~~~java
@Configuration
@EnableWebMvc
public class ApiWebConfiguration implements WebMvcConfigurer {
    // addInterceptors(...) và các callback tùy chỉnh
}
~~~

Khi đó, cấu hình MVC của Spring Boot rút lui. Endpoint controller có thể vẫn hoạt động, nhưng cơ chế welcome page và mapping resource mặc định của Boot có nguy cơ không còn. Tùy cấu hình, người dùng sẽ quan sát 404 tại / hoặc /assets/app.js.

Cách sửa phù hợp nếu chỉ cần thêm interceptor là **xóa @EnableWebMvc** và giữ:

~~~java
@Configuration
public class ApiWebConfiguration implements WebMvcConfigurer {
    // addInterceptors(...) và các callback tùy chỉnh
}
~~~

Sau khi chạy lại, Boot tiếp tục quyết định các mặc định MVC mà không bị chặn bởi bean WebMvcConfigurationSupport. Cần kiểm tra thực tế các URL trước đó, nhất là nếu đã có thêm cấu hình resource handler, reverse proxy hoặc Spring Security.

Cách sửa này đơn giản hơn việc copy tất cả resource handler, welcome page handler và converter của Boot sang mã của chính ứng dụng.

## 7. Tự kế thừa WebMvcConfigurationSupport có gì khác?

**WebMvcConfigurationSupport** là class cấu hình MVC nền tảng, nằm trong package:

~~~java
org.springframework.web.servlet.config.annotation.WebMvcConfigurationSupport
~~~

Ví dụ một class chủ động kế thừa:

~~~java
package com.example.mvc;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurationSupport;

@Configuration
public class ManualMvcConfiguration extends WebMvcConfigurationSupport {

    @Override
    protected void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/files/**")
                .addResourceLocations("classpath:/files/");
    }
}
~~~

Đây là phương án **thay quyền kiểm soát cấu hình MVC**. Chỉ cần bean kế thừa WebMvcConfigurationSupport xuất hiện trong context, điều kiện Spring Boot WebMvcAutoConfiguration đã có thể không còn thỏa, bất kể class có @EnableWebMvc hay không.

Khi dùng class tự kế thừa, bạn nhận trách nhiệm thiết lập những phần MVC mà ứng dụng cần, trong đó có resource handling, converter, path matching, validator và nhiều thiết lập khác. Nếu chỉ muốn thêm /files/**, cách phù hợp hơn trong ứng dụng Boot thường là implements WebMvcConfigurer như phần 5.

### Sự khác nhau giữa WebMvcConfigurationSupport và DelegatingWebMvcConfiguration

- WebMvcConfigurationSupport tạo ra cấu hình hạ tầng MVC và cung cấp các phương thức protected để tùy chỉnh sâu.
- DelegatingWebMvcConfiguration kế thừa WebMvcConfigurationSupport và phát hiện/ủy quyền các callback cho các WebMvcConfigurer trong context.
- @EnableWebMvc import DelegatingWebMvcConfiguration.
- Một subclass tự tạo của WebMvcConfigurationSupport không nên được giả định sẽ tự xử lý toàn bộ WebMvcConfigurer của các module khác theo cách DelegatingWebMvcConfiguration thực hiện.
- Spring Framework có cách cấu hình nâng cao dựa trên DelegatingWebMvcConfiguration; trong Boot, phương án này cũng dẫn tới việc phải chịu trách nhiệm với các MVC defaults mà Boot trước đó cung cấp.

Đừng đồng thời khai báo @EnableWebMvc và nhiều class cấu hình nền tảng MVC khác chỉ để thử xem cái nào thắng. Việc đó có thể gây trùng bean, xung đột mapping hoặc lỗi khởi tạo context.

## 8. Khi nào thực sự cần @EnableWebMvc hoặc WebMvcConfigurationSupport?

Có một số tình huống hợp lý:

1. Một ứng dụng Spring Framework thuần, không dùng các tiện ích MVC auto-configuration của Spring Boot.
2. Hệ thống cần kiểm soát hoàn toàn hạ tầng MVC, chủ động đăng ký và quản trị tất cả bean liên quan.
3. Một framework tích hợp đặc biệt yêu cầu thay thế cấu hình MVC nền tảng theo cách không thể đáp ứng bằng callbacks hay extension points cấp cao.

Tuy nhiên, trong ứng dụng Spring Boot có yêu cầu phổ biến như thêm interceptor, converter, formatter, CORS hoặc một resource handler, trước tiên hãy dùng **WebMvcConfigurer**. Nếu cần thay thế một số bean chuyên sâu mà vẫn giữ các tích hợp của Boot, xem xét **WebMvcRegistrations** theo tài liệu của phiên bản đang chạy.

Có thể dùng các extension points khác tùy bài toán, chẳng hạn bean **Converter**, **Formatter** hoặc tùy chỉnh HTTP message converter theo cơ chế Spring Boot đang hỗ trợ. Không nên thay toàn bộ hạ tầng chỉ để sửa một chi tiết.

## 9. Converter và JSON: một bẫy hay gặp

Spring MVC dùng các **HttpMessageConverter** để chuyển dữ liệu giữa HTTP request/response và đối tượng Java. Ví dụ @RequestBody cần converter để đọc JSON thành object, còn @ResponseBody thường dùng converter để ghi object thành JSON.

Khi có @EnableWebMvc:

- Phần tích hợp HttpMessageConverters của Spring Boot MVC có thể không được áp dụng.
- Spring Framework MVC Java Config vẫn có cơ chế đăng ký converter mặc định dựa trên thư viện hiện diện.
- Vì vậy JSON **có thể vẫn hoạt động** nếu có Jackson và converter thích hợp. Không thể kết luận chỉ từ sự xuất hiện của @EnableWebMvc rằng mọi JSON endpoint đều lỗi.
- Các tùy chỉnh cấu hình ObjectMapper hoặc converter do ứng dụng/Boot cung cấp cần được kiểm tra xem còn tham gia đúng pipeline MVC hay không.

Trong Spring Framework 6.x, có hai callback thường gặp:

- **configureMessageConverters(List)**: có thể thay đổi cách đăng ký danh sách mặc định. Nếu tự thêm converter không đúng cách, có thể khiến các converter mặc định không được dùng.
- **extendMessageConverters(List)**: cho phép điều chỉnh danh sách sau khi converter đã được cấu hình.

Spring Framework 7.x có API mới cho cấu hình converter; nên đọc tài liệu tương ứng thay vì copy nguyên đoạn code tùy chỉnh converter của phiên bản cũ.

Khi một endpoint trước đây trả JSON nhưng sau khi thay cấu hình lại trả lỗi **406 Not Acceptable** hoặc **415 Unsupported Media Type**, cần kiểm tra Accept, Content-Type, bộ converter, dependency Jackson và cơ chế xử lý request/response. Các lỗi này có thể có nhiều nguyên nhân; không nên sửa bằng cách bật thêm @EnableWebMvc.

## 10. Phân biệt với một số cấu hình không liên quan trực tiếp

### @SpringBootApplication

Annotation này kích hoạt cơ chế auto-configuration tổng quát và component scanning của Spring Boot. Không cần thêm @EnableWebMvc để mọi @RestController chạy được. Thêm @EnableWebMvc vào class ứng dụng có thể làm WebMvcAutoConfiguration rút lui như đã phân tích.

### @EnableWebFlux

@EnableWebFlux dành cho **Spring WebFlux**, không phải Spring MVC. Không dùng nó như cách thay thế @EnableWebMvc trong một ứng dụng Servlet MVC. Boot có cơ chế cấu hình WebFlux riêng và hành vi khác.

### Spring Security

Spring Security có filter chain riêng. Việc thay đổi HandlerMapping hoặc MVC matching có thể ảnh hưởng đến matcher và các URL được bảo vệ, nhưng @EnableWebMvc không có nghĩa tự động tắt Security. Nếu endpoint thay đổi behavior sau khi cấu hình MVC, hãy kiểm tra cả filter chain và MVC mapping.

### Embedded server

server.port, server.address và cấu hình Tomcat nhúng không tự động bị mất chỉ vì MVC WebMvcAutoConfiguration rút lui. Embedded server có auto-configuration riêng. Vì thế một ứng dụng vẫn có thể lắng nghe cổng HTTP bình thường trong khi static resource hoặc một số MVC defaults bị thay đổi.

### Spring Boot Actuator

Actuator cũng có cấu hình và đường dẫn riêng. Không thể kết luận toàn bộ Actuator biến mất khi thêm @EnableWebMvc. Nếu endpoint management gặp lỗi, kiểm tra dependency, management port/base path, security và auto-configuration đang hoạt động.

## 11. Cách xác nhận WebMvcAutoConfiguration còn hoạt động

Khi nghi ngờ cấu hình MVC của Boot đã rút lui, hãy làm theo quy trình sau:

1. Tìm **@EnableWebMvc** trong các @Configuration của ứng dụng hoặc thư viện tích hợp.
2. Tìm các bean có kiểu **WebMvcConfigurationSupport**, bao gồm class kế thừa trực tiếp hoặc gián tiếp.
3. Kiểm tra sự xuất hiện của **DelegatingWebMvcConfiguration** và các class cấu hình MVC nền tảng trong context.
4. Xem điều kiện **WebMvcAutoConfiguration** trong condition evaluation report.
5. Kiểm tra các URL có thể quan sát: API controller, static resource, welcome page, CORS và message conversion.
6. Nếu chỉ cần thêm callback, chuyển cấu hình sang **WebMvcConfigurer** rồi khởi động lại và chạy các kiểm thử HTTP thích hợp.

### Bật condition evaluation report

Có thể dùng chế độ debug khi khởi động ứng dụng để thấy auto-configuration nào match và không match:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Đầu ra cụ thể thay đổi theo version và môi trường. Trong report, tìm **WebMvcAutoConfiguration** và lý do điều kiện liên quan đến WebMvcConfigurationSupport không thỏa. Không cần dựa vào vị trí dòng log cụ thể vì cấu trúc report có thể thay đổi.

Trong môi trường được quản trị phù hợp, Spring Boot Actuator cũng có endpoint **conditions** để quan sát kết quả điều kiện auto-configuration, nếu endpoint được thêm và mở quyền đúng cách. Tránh expose endpoint chẩn đoán ra internet công khai.

### Kiểm thử hồi quy hữu ích

Sau khi sửa cấu hình MVC, nên thử tối thiểu:

- Controller GET /api/hello trả nội dung dự kiến và HTTP 200.
- File static ở vị trí mặc định có URL hoạt động nếu hệ thống sử dụng.
- Welcome page hoạt động nếu ứng dụng cần trang chủ.
- Request JSON với Content-Type/Accept phù hợp có thể đọc và ghi.
- Route có custom interceptor, formatter, CORS hoặc resource handler vẫn hoạt động.
- Quy tắc Spring Security không trở nên rộng hoặc hẹp hơn dự kiến.

Kiểm tra cả trạng thái trước và sau ở cùng một profile để tránh nhầm lỗi cấu hình MVC với khác biệt environment.

## 12. Bảng quyết định nhanh

| Yêu cầu | Cách nên ưu tiên | Có giữ Boot MVC auto-configuration? |
|---|---|---|
| Thêm HandlerInterceptor | implements WebMvcConfigurer, addInterceptors | Thường có |
| Thêm CORS policy cho MVC route | implements WebMvcConfigurer, addCorsMappings | Thường có |
| Thêm Formatter hoặc Converter | WebMvcConfigurer / bean theo Boot | Thường có |
| Thêm URL static riêng | implements WebMvcConfigurer, addResourceHandlers | Thường có |
| Thêm redirect hoặc view controller | implements WebMvcConfigurer, addViewControllers | Thường có |
| Tùy chỉnh converter | Extension API/bean tương thích phiên bản | Có thể giữ |
| Thay một phần MVC infrastructure nâng cao | Xem WebMvcRegistrations và extension points | Có thể giữ, tùy implementation |
| Kiểm soát hoàn toàn Spring MVC Java Config | @EnableWebMvc hoặc configuration nền tảng tùy biến | Boot WebMvcAutoConfiguration rút lui |
| Kế thừa WebMvcConfigurationSupport | Chỉ dùng khi có lý do kiến trúc rõ ràng | Boot WebMvcAutoConfiguration rút lui |

"Thường có" trong bảng giả định không có bean WebMvcConfigurationSupport khác khiến Boot rút lui. Cần kiểm tra toàn bộ context khi có nhiều module và starter tích hợp.

## 13. Câu hỏi tự kiểm tra và đáp án

**Câu 1:** Một class chỉ implements WebMvcConfigurer có tự làm Boot mất MVC auto-configuration không?

Trả lời: Không. Đây là cách mở rộng được Spring Boot khuyến nghị, miễn là không có @EnableWebMvc hoặc WebMvcConfigurationSupport khác làm điều kiện missing-bean thất bại.

**Câu 2:** Vì sao @EnableWebMvc làm WebMvcAutoConfiguration rút lui?

Trả lời: @EnableWebMvc import DelegatingWebMvcConfiguration, một subclass của WebMvcConfigurationSupport. Bean thuộc loại này khiến @ConditionalOnMissingBean(WebMvcConfigurationSupport.class) không thỏa mãn.

**Câu 3:** Vì sao kế thừa WebMvcConfigurationSupport trực tiếp có thể gây hệ quả tương tự?

Trả lời: Bản thân class cấu hình đó đã cung cấp bean WebMvcConfigurationSupport, nên Spring Boot không tiếp tục tự động cung cấp cấu hình MVC riêng.

**Câu 4:** Có thể còn dùng được @RestController và JSON sau @EnableWebMvc không?

Trả lời: Có thể. Spring Framework MVC Java Config vẫn cung cấp hạ tầng controller và các converter thích hợp nếu dependency tương ứng hiện diện. Cần kiểm tra cụ thể thay vì giả định mọi thứ đều bị tắt.

**Câu 5:** Một ứng dụng Boot mất index.html và static files ngay sau khi thêm cấu hình MVC mới. Bước đầu nên kiểm tra gì?

Trả lời: Tìm @EnableWebMvc hoặc subclass WebMvcConfigurationSupport, xem condition report của WebMvcAutoConfiguration. Nếu chỉ cần interceptor hoặc CORS, chuyển sang WebMvcConfigurer mà không bật @EnableWebMvc.

**Câu 6:** @EnableWebMvc có làm embedded Tomcat ngừng chạy không?

Trả lời: Không phải là hệ quả trực tiếp. Embedded Tomcat được cấu hình qua các phần khác của Spring Boot; ứng dụng có thể tiếp tục nghe HTTP nhưng mất một số tiện ích MVC mặc định.

## 14. Tài liệu tham khảo chính thức

- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html): phần Spring MVC Auto-configuration, static resources và tùy chỉnh MVC.
- [Spring Boot — Customize Spring MVC](https://docs.spring.io/spring-boot/how-to/spring-mvc.html): cơ chế tùy chỉnh MVC, HttpMessageConverters và bật chế độ kiểm soát MVC hoàn toàn.
- [Spring Framework — Enable MVC Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/enable.html): cách @EnableWebMvc kích hoạt MVC Java Config.
- [Spring Framework — Advanced Java Config](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/advanced-java.html): DelegatingWebMvcConfiguration và cấu hình nâng cao.
- [Spring Framework — Static Resources](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/static-resources.html): ResourceHandlerRegistry và cách tự đăng ký đường dẫn tài nguyên.
- [Spring Framework — Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/message-converters.html): lựa chọn API để thêm và tùy chỉnh converter.

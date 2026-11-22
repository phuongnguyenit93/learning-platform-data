# Đăng ký DispatcherServlet và ánh xạ yêu cầu trong Spring Boot

## 1. DispatcherServlet nằm ở đâu trong luồng Spring MVC?

Trong Spring MVC, **DispatcherServlet** là front controller: một Servlet trung tâm nhận các HTTP request đã được Servlet container chuyển đến nó, tìm handler phù hợp, thực thi chuỗi xử lý MVC và tạo HTTP response. Trong ứng dụng Spring Boot chạy theo mô hình Servlet với embedded Tomcat mặc định, người phát triển thường chỉ cần khai báo các @Controller hoặc @RestController; Spring Boot tự tạo và đăng ký DispatcherServlet.

Cần phân biệt ba quyết định liên tiếp:

1. **Web server / Servlet container** nhận kết nối trên IP, port và quyết định request thuộc web application (context path) nào.
2. **Servlet mapping** trong container quyết định Servlet nào nhận đường dẫn HTTP còn lại. DispatcherServlet mặc định của Spring Boot thường được map với URL pattern "/" trong context của ứng dụng.
3. **Handler mapping** bên trong DispatcherServlet chọn một controller method, handler chức năng, handler tài nguyên tĩnh hoặc handler khác theo HTTP method, đường dẫn và các điều kiện mapping.

Một @GetMapping("/books") không tạo thêm Servlet mới trong Tomcat. Nó đăng ký một handler method với Spring MVC, để DispatcherServlet gọi khi gặp request phù hợp. Ngược lại, ServletRegistrationBean hoặc ServletContext.addServlet(...) tạo đăng ký ở **tầng Servlet container**, trước khi logic @RequestMapping được xem xét.

Luồng điển hình:

~~~text
Client  GET /app/books/42
   |
   v
TCP/TLS -> embedded Tomcat HTTP Connector
   |
   v
Web application context path: /app
   |
   v
Servlet Filter chain (ví dụ Spring Security, logging)
   |
   v
Tomcat Servlet URL mapping: "/" -> DispatcherServlet
   |
   v
DispatcherServlet
   +-- HandlerMapping (ví dụ RequestMappingHandlerMapping)
   |       -> BookController.find(42)
   +-- HandlerAdapter (ví dụ RequestMappingHandlerAdapter)
   |       -> argument resolution + controller invocation
   +-- Return value handling / HttpMessageConverter
   |       -> JSON response
   +-- HandlerExceptionResolver khi xử lý có exception
   |
   v
Filter chain hoàn tất -> Tomcat -> HTTP response -> Client
~~~

Từ góc nhìn vận hành, việc “Tomcat đã mở cổng” chưa bảo đảm có DispatcherServlet hợp lệ, có controller mapping mong muốn hoặc ứng dụng đã sẵn sàng phục vụ. Chẩn đoán phải kiểm tra đúng lớp đang có vấn đề: network, Servlet registration, Spring MVC handler mapping hay nghiệp vụ phía sau.

## 2. Spring Boot tự động tạo và đăng ký DispatcherServlet

Trong ứng dụng sử dụng spring-boot-starter-web, Spring Boot 3.3 thường đưa các thành phần quan trọng lên classpath:

- Spring Web và Spring MVC, trong đó có org.springframework.web.servlet.DispatcherServlet.
- Jakarta Servlet API và embedded Servlet container (Tomcat mặc định nếu không thay đổi dependency).
- Các auto-configuration cho Servlet web application, MVC, message conversion, error handling và tài nguyên tĩnh.

Khi các điều kiện về classpath, loại ứng dụng và bean phù hợp, DispatcherServletAutoConfiguration tạo một bean DispatcherServlet theo tên thông dụng **dispatcherServlet**. Một bean DispatcherServletRegistrationBean (tên mặc định thường là **dispatcherServletRegistration**) đăng ký Servlet đó vào ServletContext với đường dẫn do Spring MVC properties quyết định, mặc định "/".

Về bản chất có hai đối tượng/việc khác nhau:

| Khái niệm | Trách nhiệm |
|---|---|
| DispatcherServlet bean | Chứa logic front controller của Spring MVC; được Spring quản lý như một bean |
| DispatcherServletRegistrationBean | Thực hiện đăng ký bean Servlet với ServletContext của Tomcat/Jetty/Undertow; xác định URL pattern, tên Servlet, load-on-startup |
| ServletWebServerFactory | Tạo và cấu hình embedded Servlet server, bao gồm cổng và container |
| RequestMappingHandlerMapping | Tìm các controller method được đăng ký qua @RequestMapping, @GetMapping, @PostMapping... |
| RequestMappingHandlerAdapter | Gọi controller method, bind argument, xử lý return value |
| HandlerExceptionResolver | Chuyển exception trong MVC thành kết quả/response phù hợp |
| HttpMessageConverter | Đọc/ghi HTTP body theo media type, chẳng hạn JSON |
| ViewResolver | Giải quyết tên view cho controller trả về trang giao diện theo mô hình MVC |

Trong Spring Boot tiêu chuẩn, không cần tự viết web.xml, không cần tạo WebApplicationInitializer, không cần gọi ServletContext.addServlet và không cần đăng ký thủ công mỗi controller. Khi @SpringBootApplication được đặt trong package cha phù hợp, component scan tìm thấy các controller, và MVC infrastructure tự phát hiện các handler method.

### 2.1. Điều kiện để auto-configuration có hiệu lực

Đừng suy luận chỉ từ dependency tên spring-web: ứng dụng cần chạy ở loại **Servlet web application** và có Spring MVC. Một ứng dụng WebFlux theo mô hình reactive thường sử dụng DispatcherHandler thay cho DispatcherServlet. Một ứng dụng được cấu hình spring.main.web-application-type=none sẽ không khởi động embedded web server.

Nếu có nhiều thư viện web, cần xác nhận stack thực tế của Spring Boot. Khi cả Spring MVC và WebFlux cùng có trên classpath trong thiết lập thông thường, Spring Boot ưu tiên Servlet/MVC; việc dùng WebClient không tự đổi server sang reactive.

Khai báo một DispatcherServlet hoặc registration bean riêng có thể khiến auto-configuration mặc định lùi lại theo điều kiện bean. Vì thế trước khi “sửa” bằng cách thêm bean thứ hai, nên kiểm tra thực sự auto-configuration đang tạo những gì và tác động đến servlet mapping.

### 2.2. Khi nào DispatcherServlet được khởi tạo?

Có thể cấu hình:

~~~yaml
spring:
  mvc:
    servlet:
      load-on-startup: 1
~~~

Trong Spring Boot 3.3, thuộc tính spring.mvc.servlet.load-on-startup có giá trị mặc định -1. Giá trị dương yêu cầu container ưu tiên khởi tạo Servlet lúc khởi động theo thứ tự load-on-startup của Servlet spec. Nó liên quan thời điểm init Servlet, **không phải** cách thay đổi route/controller mapping và cũng không chứng minh mọi dependency nghiệp vụ đã ready. Tránh tùy tiện đổi giá trị này để che lỗi 404 hoặc readiness.

## 3. Hai tầng ánh xạ: URL pattern của Servlet và @RequestMapping

Tầng Servlet container làm việc với URL patterns theo Servlet specification, chẳng hạn:

- Một đường dẫn chính xác: /special.
- Một tiền tố: /legacy/*.
- Một hậu tố theo extension: *.do.
- Mapping mặc định: /.
- Một pattern /* thường là path mapping phủ rộng, **khác** default mapping "/".

Tomcat sử dụng các quy tắc ưu tiên của Servlet spec khi chọn Servlet: exact match, prefix match dài nhất, extension match và default match. Không thể kết luận một request luôn đi qua DispatcherServlet chỉ vì ứng dụng có controller; nếu một Servlet khác có mapping cụ thể hơn, nó có thể nhận request trước.

Sau khi DispatcherServlet được chọn, Spring MVC mới xét các handler mappings: điều kiện path, HTTP method, params, headers, consumes và produces. RequestMappingHandlerMapping dùng annotation của controller để tạo các mapping ở **tầng Spring MVC**, không tạo thêm URL pattern trong Tomcat.

Ví dụ:

~~~java
@RestController
@RequestMapping("/books")
class BookController {

    @GetMapping("/{id}")
    String find(@PathVariable long id) {
        return "book " + id;
    }
}
~~~

Trong ứng dụng có DispatcherServlet map "/" và context path rỗng, GET /books/42 được Tomcat chuyển đến DispatcherServlet; Spring MVC chọn BookController.find(...), rồi trả body "book 42". Tomcat không cần biết cụ thể controller hay route "/books/{id}" trong danh sách Servlet registration.

### 3.1. Default mapping "/" không phải "/*"

Đây là điểm quan trọng khi chỉnh thủ công Servlet registration:

- "/" là default Servlet mapping theo quy tắc của container. Một Servlet khác đăng ký exact hoặc prefix mapping cụ thể hơn vẫn có cơ hội nhận request thích hợp.
- "/*" là path-prefix pattern có độ ưu tiên khác và có thể chiếm các URL mà bạn dự kiến để Servlet khác hoặc cơ chế view/resource xử lý.
- Không đổi mặc định "/" thành "/*" chỉ vì nghĩ đây là cách diễn đạt tương đương. Việc thay đổi có thể ảnh hưởng các Servlet bổ sung, request forwarding, trang lỗi và việc xử lý view/asset.

Với ứng dụng Spring Boot MVC thông thường, giữ mapping mặc định "/" là đơn giản và tương thích nhất.

### 3.2. Annotation route còn có điều kiện khác đường dẫn

Ví dụ:

~~~java
@PostMapping(
        path = "/books",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
)
ResponseEntity<BookView> create(@RequestBody NewBook body) {
    BookView saved = new BookView(101L, body.title());
    return ResponseEntity.status(HttpStatus.CREATED).body(saved);
}
~~~

Đây là đoạn phương thức controller minh họa, cần đặt trong class Spring MVC và bổ sung các kiểu BookView, NewBook, import tương ứng. Nó không tự đăng ký một Servlet riêng. Spring MVC chọn handler dựa trên POST /books và điều kiện Content-Type/Accept phù hợp.

Các HTTP status thường giúp xác định tầng lỗi: 404 có thể do không có servlet/handler/resource tương ứng; 405 thường là route tồn tại nhưng HTTP method không được hỗ trợ; 415 thường liên quan Content-Type không tương thích với consumes; 406 thường liên quan Accept không phù hợp với produces. Không nên quy mọi trường hợp 4xx cho lỗi DispatcherServlet registration.

## 4. Ghép đường dẫn: context path, servlet path, controller path

Ba kiểu path dễ bị lẫn:

1. **server.servlet.context-path**: tiền tố web application theo Servlet container.
2. **spring.mvc.servlet.path**: đường đăng ký DispatcherServlet trong web application.
3. **@RequestMapping/@GetMapping**: đường dẫn handler tương đối với không gian MVC được DispatcherServlet quản lý.

Ví dụ controller:

~~~java
@RestController
@RequestMapping("/books")
class BookController {
    @GetMapping("/{id}")
    String book(@PathVariable long id) {
        return "book-" + id;
    }
}
~~~

Một số cấu hình và URL dự kiến:

| Context path | DispatcherServlet path | Controller path | URL GET hoàn chỉnh |
|---|---|---|---|
| Rỗng (mặc định) | "/" (mặc định) | /books/7 | http://localhost:8080/books/7 |
| /catalog | "/" | /books/7 | http://localhost:8080/catalog/books/7 |
| Rỗng | /api | /books/7 | http://localhost:8080/api/books/7 |
| /catalog | /api | /books/7 | http://localhost:8080/catalog/api/books/7 |

URL trên giả định server.port=8080, ứng dụng chưa bị reverse proxy thay URL, các servlet mappings không xung đột và prefix servlet path được cấu hình với path matching tương thích.

### 4.1. Context path cho toàn ứng dụng Servlet

Cấu hình:

~~~yaml
server:
  port: 8080
  servlet:
    context-path: /catalog
~~~

Controller GET /books/7 được truy cập qua GET /catalog/books/7. Context path thuộc web application. Nó có thể áp dụng cho các Servlet khác đăng ký trong cùng context, kể cả Servlet không chạy qua Spring MVC.

Dùng context path khi toàn bộ web application cần một tiền tố thống nhất, ví dụ đặt phiên bản sản phẩm hoặc đường chung trên server. Khi dùng ingress, gateway hoặc reverse proxy có path rewrite, cần tách URL bên ngoài khỏi path thực sự Tomcat nhận được; không giả định proxy luôn giữ nguyên prefix.

### 4.2. DispatcherServlet path cho riêng Spring MVC

Cấu hình có prefix:

~~~yaml
spring:
  mvc:
    servlet:
      path: /api
    pathmatch:
      matching-strategy: ant-path-matcher
~~~

**Lưu ý phiên bản:** Trong Spring Boot 3.3, PathPatternParser là chiến lược path matching mặc định; tài liệu Spring Boot chỉ rõ việc đặt prefix tùy chỉnh bằng spring.mvc.servlet.path **không tương thích** với PathPatternParser. Vì vậy, nếu chủ đích dùng spring.mvc.servlet.path=/api trong Spring Boot 3.3, cần cấu hình matching-strategy=ant-path-matcher như trên và kiểm tra thực tế các route đang dùng.

Nếu không có yêu cầu về một Servlet prefix riêng, thường dễ hơn khi để spring.mvc.servlet.path mặc định và chọn server.servlet.context-path hoặc @RequestMapping cấp controller theo đúng phạm vi cần đổi. Tránh chuyển chiến lược matching không cần thiết, vì AntPathMatcher và PathPatternParser có khác biệt về cách chấp nhận một số pattern.

### 4.3. @RequestMapping không phải servlet path

Nếu class có @RequestMapping("/api/books"), URL handler có tiền tố /api trong MVC dù DispatcherServlet vẫn map "/". Cách này khác với spring.mvc.servlet.path=/api:

- Đổi @RequestMapping chỉ thay handler mapping; các controller khác và Servlet registration không bị chuyển sang prefix mới.
- Đổi spring.mvc.servlet.path là thay phạm vi URL của DispatcherServlet; hầu hết handler MVC cần truy cập qua prefix này.
- Đổi server.servlet.context-path thay tiền tố chung cho web application.
- Nếu cùng lúc đặt servlet.path=/api và @RequestMapping("/api/books"), URL có thể thành /api/api/books; đây là lỗi cấu hình thường gặp.

Không cộng trùng các prefix khi thiết kế route hoặc test.

## 5. Ví dụ Java 17+ chạy được: đăng ký mặc định và controller mapping

Giả sử tạo một project Spring Boot 3.3.x Java 17 với starter web. Trong project Gradle đã áp dụng Spring Boot plugin, dependency tối thiểu:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Tạo file src/main/java/dev/example/mvc/MvcDemoApplication.java:

~~~java
package dev.example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcDemoApplication.class, args);
    }
}
~~~

Tạo file src/main/java/dev/example/mvc/BookController.java:

~~~java
package dev.example.mvc;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping(path = "/books", produces = MediaType.APPLICATION_JSON_VALUE)
public class BookController {

    public record BookView(long id, String title) {}

    public record CreateBook(String title) {}

    @GetMapping("/{id}")
    public BookView find(@PathVariable long id) {
        return new BookView(id, "Spring MVC");
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<BookView> create(@RequestBody CreateBook body) {
        BookView saved = new BookView(100L, body.title());
        return ResponseEntity.status(HttpStatus.CREATED).body(saved);
    }
}
~~~

Hai record lồng trong class dùng Java 17. Đây là controller minh họa, không kết nối database và không lưu dữ liệu thật. Khi ứng dụng khởi động, component scan tìm thấy BookController vì nó cùng package với main class. Spring MVC ghi nhận hai handler mappings:

- GET /books/{id} -> BookController.find(...).
- POST /books (Content-Type: application/json) -> BookController.create(...).

Không cần thêm web.xml hoặc ServletRegistrationBean nào trong ví dụ này. Spring Boot tạo DispatcherServlet và map vào "/" tự động.

Có thể đặt src/main/resources/application.yml:

~~~yaml
server:
  port: 8080
~~~

Từ thư mục project có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell, có thể chạy .\gradlew.bat bootRun. Kiểm tra GET:

~~~bash
curl -i http://localhost:8080/books/7
~~~

Kết quả chính cần kiểm tra là HTTP 200 và JSON body:

~~~json
{"id":7,"title":"Spring MVC"}
~~~

Ví dụ POST:

~~~bash
curl -i -X POST http://localhost:8080/books \
  -H "Content-Type: application/json" \
  -d '{"title":"DispatcherServlet"}'
~~~

Lệnh dùng cách nối dòng của shell Unix; trên PowerShell có thể viết gộp thành một dòng với curl.exe. Kết quả chính là HTTP 201 và body:

~~~json
{"id":100,"title":"DispatcherServlet"}
~~~

Các header như Date, Content-Length, connection hoặc content type parameter có thể khác tùy server/config. Đừng xem toàn bộ chuỗi header là output bất biến. Nếu thêm server.servlet.context-path=/catalog, hãy gọi /catalog/books/7. Nếu thêm spring.mvc.servlet.path=/api với matching-strategy phù hợp, hãy gọi /api/books/7.

### 5.1. Vì sao @RestController tự hoạt động?

@RestController là sự kết hợp ngữ nghĩa của @Controller và @ResponseBody. Spring MVC sử dụng RequestMappingHandlerMapping để tìm phương thức có mapping annotation, RequestMappingHandlerAdapter để gọi phương thức và các argument resolver để truyền @PathVariable/@RequestBody.

Khi handler trả một record, các return value handlers và HttpMessageConverter (thường có Jackson nhờ starter web) chuyển đối tượng thành JSON. DispatcherServlet điều phối quá trình này; mỗi controller method không phải một Servlet và không cần một port riêng.

### 5.2. Component scan cũng quyết định có tìm thấy controller hay không

@SpringBootApplication bao gồm component scan từ package chứa main class trở xuống. Nếu BookController nằm ngoài vùng scan, sẽ không có handler mapping cho nó dù DispatcherServlet vẫn đăng ký đúng và /actuator/health có thể hoạt động.

Khi gặp 404, kiểm tra vị trí package, annotation @Controller/@RestController và điều kiện bean. Chỉ mở rộng component scan khi cần; không di chuyển main class hoặc scan toàn bộ classpath tùy tiện.

## 6. Đăng ký DispatcherServlet bằng tay khi thực sự cần

Spring Boot đã có DispatcherServletAutoConfiguration, nên các trường hợp phổ biến nên dùng properties thay vì tạo thêm Servlet registration. Tuy nhiên, khi cần kiểm soát registration nâng cao (Servlet name, load-on-startup hoặc mapping khác thường), có thể dùng DispatcherServletRegistrationBean.

Lớp của Spring Boot 3.3:

- org.springframework.boot.autoconfigure.web.servlet.DispatcherServletRegistrationBean.
- Nó kế thừa ServletRegistrationBean<DispatcherServlet>.
- Nó đồng thời triển khai DispatcherServletPath để các phần cấu hình MVC biết đường đăng ký Servlet.
- Constructor nhận một DispatcherServlet và path.
- Có các phương thức setName, setLoadOnStartup, setUrlMappings hoặc addUrlMappings.

Ví dụ **thay thế registration mặc định**, không tạo DispatcherServlet thứ hai. File src/main/java/dev/example/mvc/DispatcherRegistrationConfig.java:

~~~java
package dev.example.mvc;

import org.springframework.boot.autoconfigure.web.servlet.DispatcherServletAutoConfiguration;
import org.springframework.boot.autoconfigure.web.servlet.DispatcherServletRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.DispatcherServlet;

@Configuration(proxyBeanMethods = false)
public class DispatcherRegistrationConfig {

    @Bean(name =
            DispatcherServletAutoConfiguration
                    .DEFAULT_DISPATCHER_SERVLET_REGISTRATION_BEAN_NAME)
    public DispatcherServletRegistrationBean customRegistration(
            DispatcherServlet dispatcherServlet) {

        DispatcherServletRegistrationBean registration =
                new DispatcherServletRegistrationBean(dispatcherServlet, "/api");

        registration.setName(
                DispatcherServletAutoConfiguration
                        .DEFAULT_DISPATCHER_SERVLET_BEAN_NAME);
        registration.setLoadOnStartup(1);
        return registration;
    }
}
~~~

Đây là ví dụ nâng cao có chủ đích: tạo registration bean được Spring quản lý để sử dụng DispatcherServlet do Spring Boot tạo, đăng ký tại /api thay cho mapping mặc định. Cần bảo đảm trong context không có một bean registration khác cùng tên hoặc mapping trùng. Với Spring Boot 3.3, cần chọn path matching tương thích nếu đặt prefix:

~~~yaml
spring:
  mvc:
    pathmatch:
      matching-strategy: ant-path-matcher
~~~

Không đồng thời đặt spring.mvc.servlet.path mâu thuẫn với custom registration trong hai nơi. Ưu tiên chọn **một nguồn điều khiển servlet path**; nếu mục tiêu đơn thuần là /api, thuộc tính spring.mvc.servlet.path là đủ và ít rủi ro hơn.

Một bean DispatcherServlet tùy biến không tự bảo đảm container sẽ register nó với mapping mong muốn: cần registration phù hợp. Tương tự, một registration bean thiếu điều kiện khiến MVC infrastructure không biết servlet path có thể gây sai static resource path, link generation hoặc handler mapping. Đây là lý do nên dùng DispatcherServletRegistrationBean thay cho ServletRegistrationBean thông thường khi cần thay registration của DispatcherServlet chính.

### 6.1. Có nên tạo DispatcherServlet thứ hai?

Nhiều DispatcherServlet có thể dùng cho những web contexts, cơ chế route hoặc module tách biệt, nhưng đây không phải lựa chọn mặc định cho một ứng dụng CRUD/REST. Mỗi servlet cần tên riêng, registration rõ ràng, mapping không xung đột và cấu hình liên quan đến ApplicationContext, component scan, HandlerMapping, error handling, filter và security.

Chỉ tạo nhiều DispatcherServlet khi thực sự có yêu cầu phân vùng MVC cụ thể và hiểu cách các servlet dùng chung/tách riêng WebApplicationContext. Việc thêm một servlet thứ hai mà vẫn reuse toàn bộ cùng controller beans thường gây trùng route hoặc khó xác định servlet nào nhận request.

Nếu chỉ muốn group endpoint /v1 và /v2, dùng @RequestMapping("/v1") hoặc API versioning được thiết kế rõ ràng thường dễ bảo trì hơn nhiều so với tạo hai DispatcherServlet.

### 6.2. Trường hợp dùng ServletContext.addServlet trực tiếp

Servlet spec hỗ trợ đăng ký qua ServletContext.addServlet(name, servlet), sau đó cấu hình ServletRegistration.Dynamic.addMapping(...) và load-on-startup. Trong Spring Boot embedded server, ServletContextInitializer và các RegistrationBean là cách tích hợp gần với lifecycle Boot hơn. Không gọi addServlet tùy tiện từ code chạy sau khi container đã khởi động; Servlet registration có giai đoạn được phép thay đổi.

Đăng ký qua web.xml hoặc WebApplicationInitializer là kỹ thuật Servlet/Spring MVC thuần; không cần thiết trong ứng dụng Spring Boot embedded Tomcat thông thường. Khi deploy WAR vào một container bên ngoài, quy tắc ownership của ServletContext và container cũng khác.

## 7. Đăng ký Servlet khác cạnh DispatcherServlet

Một ứng dụng có thể có một Servlet thuần Java xử lý đường /legacy/* ngoài Spring MVC. Spring Boot hỗ trợ ServletRegistrationBean để làm điều này.

Ví dụ file src/main/java/dev/example/mvc/LegacyServletConfiguration.java:

~~~java
package dev.example.mvc;

import java.io.IOException;

import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LegacyServletConfiguration {

    @Bean
    ServletRegistrationBean<HttpServlet> legacyServlet() {
        HttpServlet servlet = new HttpServlet() {
            @Override
            protected void doGet(
                    HttpServletRequest request,
                    HttpServletResponse response) throws IOException {

                response.setContentType("text/plain;charset=UTF-8");
                response.getWriter().write("legacy servlet");
            }
        };

        ServletRegistrationBean<HttpServlet> bean =
                new ServletRegistrationBean<>(servlet, "/legacy/*");
        bean.setName("legacyServlet");
        return bean;
    }
}
~~~

Trong Spring Boot 3.x sử dụng namespace **jakarta.servlet**, không còn javax.servlet như nhiều ví dụ Spring Boot 2.x. Với context path rỗng và DispatcherServlet map "/", GET /legacy/check có thể được Tomcat đưa thẳng đến legacyServlet vì prefix mapping /legacy/* cụ thể hơn default "/" của DispatcherServlet.

Ví dụ:

~~~bash
curl -i http://localhost:8080/legacy/check
~~~

Body dự kiến:

~~~text
legacy servlet
~~~

Trong trường hợp này **BookController, HandlerInterceptor và @ControllerAdvice của Spring MVC không trực tiếp xử lý legacyServlet**. Nhưng các Servlet Filter được map phù hợp (bao gồm filter chain bảo mật nếu bao phủ URL đó) vẫn có thể chạy trước khi legacyServlet nhận request. Phải kiểm tra security policy cho cả Servlet không thuộc MVC.

@ServletComponentScan có thể bật discovery các @WebServlet, @WebFilter, @WebListener trong embedded container. Nó không phải yêu cầu để Spring Boot đăng ký DispatcherServlet mặc định, cũng không phải cách để @RestController được phát hiện. Đừng dùng @ServletComponentScan như một giải pháp chung cho lỗi controller 404.

### 7.1. Tránh xung đột servlet mappings

Nếu đăng ký một Servlet mới tại /books/*, các request /books/7 có thể bị Servlet đó nhận trước DispatcherServlet map "/". Dù BookController vẫn có @GetMapping("/{id}"), Spring MVC sẽ không nhìn thấy request đó.

Khi một endpoint đột nhiên trả 404 hoặc sai response sau khi thêm Servlet thứ ba, hãy kiểm tra Servlet URL mappings trước, không chỉ kiểm tra @RequestMapping. Xung đột Servlet mapping khác xung đột HandlerMapping.

Một Servlet khác được map "/*" có thể chiếm nhiều request hơn dự định. Chỉ sử dụng pattern rộng nếu đã xét tất cả servlet, static content, forward, error dispatch và security filters liên quan.

## 8. Spring MVC xử lý request ra sao sau DispatcherServlet?

Sau khi container chọn DispatcherServlet, nó sử dụng các chiến lược MVC được cấu hình trong ApplicationContext.

1. **HandlerMapping** tìm handler phù hợp. RequestMappingHandlerMapping là thành phần thường giải quyết @RequestMapping; resource handlers, functional routes hoặc view controllers có thể được xử lý bởi các HandlerMapping khác.
2. **HandlerExecutionChain** có thể chứa HandlerInterceptor. preHandle có thể cho phép/chặn việc xử lý; postHandle và afterCompletion có vai trò riêng trong lifecycle.
3. **HandlerAdapter** phù hợp gọi handler. Với annotation controller, RequestMappingHandlerAdapter thực thi method, xử lý binding, conversion và validation theo cấu hình.
4. **Argument resolvers** giải quyết @PathVariable, @RequestParam, @RequestHeader, @RequestBody, HttpServletRequest và các tham số được hỗ trợ khác.
5. **Return value handlers** chuyển kết quả sang response. @ResponseBody/@RestController thường dùng HttpMessageConverter (chẳng hạn JSON), còn controller trả view name có thể cần ViewResolver.
6. **HandlerExceptionResolver** xử lý exception do MVC pipeline phát sinh; @ExceptionHandler và @ControllerAdvice có thể tham gia.
7. DispatcherServlet hoàn tất việc xử lý và Servlet container gửi response qua các filter đã đăng ký.

Tùy async handling, exception, forwarding và tính chất handler, thứ tự callback interceptor/filter có thể phức tạp hơn sơ đồ tuyến tính. Đây là mô hình khái quát cho request thông thường.

### 8.1. Filter khác HandlerInterceptor

| Thành phần | Chạy ở đâu? | Tác động |
|---|---|---|
| Servlet Filter | Chuỗi của Servlet container | Có thể áp dụng trước DispatcherServlet, cũng có thể áp dụng cho Servlet khác |
| Spring Security Filter Chain | Servlet Filter chain nếu đăng ký thích hợp | Authentication, authorization, CSRF và policy bảo mật |
| HandlerInterceptor | Spring MVC sau khi DispatcherServlet chọn HandlerExecutionChain | Logic liên quan đến handler MVC, logging hoặc kiểm tra nhẹ |
| ControllerAdvice / ExceptionHandler | Trong cơ chế xử lý exception của MVC | Chuyển exception MVC thành phản hồi |
| HandlerMethod | Phương thức controller đã được ánh xạ | Thực thi logic HTTP/nghiệp vụ |

Một Filter map "/*" có thể chạy cho cả /books/7 và /legacy/check. HandlerInterceptor được đăng ký qua MVC chỉ chạy khi request đi qua Spring MVC phù hợp. Không đặt các kiểm soát bảo mật bắt buộc vào HandlerInterceptor rồi cho rằng mọi Servlet trong application đều được bảo vệ như nhau.

### 8.2. Phương thức HTTP và media type cũng thuộc handler mapping

Ví dụ GET /books/7 khớp path nhưng gọi POST /books/7 có thể trả 405 thay vì 404 vì Spring MVC thấy path phù hợp nhưng method không hợp lệ. POST /books với Content-Type text/plain có thể trả 415 do consumes=application/json. Header Accept không phù hợp với produces có thể dẫn đến 406. Khi debug, luôn kiểm tra **HTTP method + đầy đủ URL + headers + content type**.

## 9. Mở rộng Spring MVC mà vẫn giữ cấu hình tự động của Boot

Để thêm formatters, interceptors, CORS mappings, view controllers hoặc tài nguyên tĩnh, thường nên khai báo bean WebMvcConfigurer thay vì tự tạo lại DispatcherServlet hoặc sử dụng @EnableWebMvc.

Ví dụ thêm một redirect MVC:

~~~java
package dev.example.mvc;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ViewControllerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcPathConfiguration implements WebMvcConfigurer {

    @Override
    public void addViewControllers(ViewControllerRegistry registry) {
        registry.addRedirectViewController("/old-books", "/books/7");
    }
}
~~~

Đây là class hoàn chỉnh có thể thêm vào demo. Khi gọi GET /old-books, MVC có thể trả response redirect tới /books/7. Nếu có servlet path/context path, cần kiểm tra URL redirect cuối cùng (Location header) theo môi trường thực tế.

**@EnableWebMvc** cho phép tự kiểm soát MVC configuration và thường khiến một phần WebMvcAutoConfiguration của Boot không còn áp dụng theo mặc định. Không thêm @EnableWebMvc chỉ để @GetMapping hoạt động, vì starter-web đã kích hoạt MVC thông thường. Dùng WebMvcConfigurer nếu chỉ cần mở rộng một vài điểm.

Khi cần thay đổi cách phát hiện annotation mapping, xây dựng custom RequestMappingHandlerMapping hoặc HandlerAdapter là công việc nâng cao có rủi ro ảnh hưởng toàn bộ route; hãy xác nhận rằng WebMvcConfigurer hoặc cấu hình handler thông thường không đủ trước khi đi theo hướng này.

## 10. Static resources, error handling và MVC mapping

Spring Boot MVC thường cấu hình handler tài nguyên tĩnh phục vụ static content từ các vị trí như classpath:/static, classpath:/public, classpath:/resources hoặc META-INF/resources. Điều này cũng đi qua MVC resource handling ở những URL phù hợp với DispatcherServlet.

Không có @GetMapping("/favicon.ico") không có nghĩa request đó sẽ trả 404 ngay từ Servlet container; MVC resource handler có thể thử tìm tài nguyên tĩnh. Trong Spring Boot 3.3, khi không tìm thấy resource có thể xuất hiện NoResourceFoundException thay vì NoHandlerFoundException trong một số cấu hình mặc định.

Có thể đặt:

~~~yaml
spring:
  web:
    resources:
      add-mappings: false
~~~

để vô hiệu hóa mapping tài nguyên tĩnh, nếu ứng dụng API thực sự không cần. Tuy nhiên việc này cũng làm mất khả năng phục vụ static resources mặc định, nên chỉ áp dụng sau khi hiểu hệ quả. Một lựa chọn khác là thu hẹp spring.mvc.static-path-pattern thành /assets/**.

Spring Boot có cơ chế error handling cho Servlet stack; DispatcherServlet có thể ủy quyền sang HandlerExceptionResolver và Boot có thể cung cấp BasicErrorController cho những đường lỗi do container forward đến error path. Không tự tạo handler "/*" hoặc một Servlet khác bắt toàn bộ URL nếu chưa kiểm tra tác động đến /error và static resource handling.

### 10.1. Reverse proxy và ingress có thể thay URL trước khi đến DispatcherServlet

Một URL bên ngoài như https://example.com/service/books/7 có thể được proxy chuyển vào Tomcat thành /books/7, hoặc giữ /service/books/7 tùy cấu hình rewrite. Khi request không khớp controller, hãy xác định chính xác path mà server nhận, thay vì chỉ đọc URL người dùng thấy trên browser.

Nếu cần xử lý X-Forwarded-* hoặc Forwarded headers, dùng cấu hình proxy trust phù hợp và Spring Boot server.forward-headers-strategy theo môi trường. Không tin header do client không đáng tin tự gửi để tạo redirect URL. Servlet mapping vẫn xét đường request bên trong container sau khi các bộ phận mạng/proxy đã xử lý.

## 11. Kiểm tra những gì đã được đăng ký

Thay vì đoán, có thể quan sát các tầng khác nhau.

### 11.1. Startup và log

Kiểm tra log loại web application, embedded server (Tomcat), port, context path và thông tin DispatcherServlet initialization. Không lấy một dòng “Tomcat started” làm bằng chứng tất cả controller mappings đã được tạo.

Có thể tạm tăng log trong môi trường phát triển:

~~~yaml
logging:
  level:
    org.springframework.web.servlet.DispatcherServlet: DEBUG
    org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping: TRACE
~~~

Mức TRACE có thể tạo nhiều output và không nên bật rộng trên production. Log cho phép quan sát quá trình chọn handler hoặc đăng ký mappings nhưng phải kết hợp với HTTP request thực tế.

### 11.2. Actuator mappings endpoint

Nếu thêm dependency:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
~~~

có thể bật endpoint mappings trong môi trường kiểm tra:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,mappings
~~~

Sau khi khởi động, dùng:

~~~bash
curl -i http://localhost:8080/actuator/mappings
~~~

Endpoint này có thể hiển thị thông tin servlet mappings, filter mappings và Spring MVC handler mappings. Cấu trúc JSON cụ thể phụ thuộc phiên bản/config, vì vậy không nên hardcode đường JSON nội bộ khi kiểm tra. Nếu Actuator chạy trên management.server.port riêng hoặc có management context path khác, URL của endpoint cũng thay đổi.

**Bảo mật:** mappings cho biết cấu trúc endpoint nội bộ; chỉ expose trong môi trường được kiểm soát hoặc bảo vệ bằng authentication/network policy thích hợp. Không mở public chỉ để debug 404.

### 11.3. Kiểm tra ServletContext registration theo cách có kiểm soát

ServletContext có thể cung cấp các ServletRegistration và mapping liên quan. Ví dụ để in thông tin khi ứng dụng đã khởi động, có thể dùng một runner:

~~~java
package dev.example.mvc;

import jakarta.servlet.ServletContext;
import jakarta.servlet.ServletRegistration;
import java.util.Map;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ServletMappingsDiagnostic {

    @Bean
    ApplicationRunner logServletMappings(ServletContext servletContext) {
        return args -> {
            for (Map.Entry<String, ? extends ServletRegistration> entry
                    : servletContext.getServletRegistrations().entrySet()) {
                System.out.println(
                        entry.getKey() + " -> " + entry.getValue().getMappings());
            }
        };
    }
}
~~~

Đây là class hỗ trợ chẩn đoán cho Servlet environment. Output phụ thuộc các Servlet đang có và container thực tế; không giả định chỉ có một registration. Nó giúp biết DispatcherServlet có được container map vào "/" hay "/api/*" hay không, nhưng không chứng minh một controller method cụ thể tồn tại.

Trên production, không nên log toàn bộ mappings ở mỗi request; runner ở đây chỉ chạy một lần khi startup để khảo sát và có thể loại bỏ sau chẩn đoán.

## 12. Kiểm thử đúng tầng

### 12.1. MockMvc kiểm tra các MVC handler

Trong project có spring-boot-starter-test, có thể viết test:

~~~java
package dev.example.mvc;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getBookIsMappedToController() throws Exception {
        mvc.perform(get("/books/7"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(7))
                .andExpect(jsonPath("$.title").value("Spring MVC"));
    }
}
~~~

Tệp có thể là src/test/java/dev/example/mvc/BookControllerTest.java. MockMvc kiểm tra luồng Spring MVC và controller mappings không cần mở cổng mạng thật. Nó rất phù hợp cho binding/validation/response, nhưng **không đủ để chứng minh Tomcat thực sự đăng ký đúng URL pattern hoặc cổng** khi đã cấu hình nhiều Servlet hay custom registration.

Nếu đang dùng servlet path hoặc context path tùy chỉnh, hãy xem kỹ cách MockMvc mô phỏng servletPath/contextPath trong request builder. Đừng đưa toàn bộ external URL vào request mapping rồi cho rằng một test MockMvc mặc định luôn tương đương hành vi container thật.

### 12.2. Integration test với cổng thực

Dùng @SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT), hoặc chạy ứng dụng rồi curl đến địa chỉ localhost:port. Kiểm tra:

- GET /books/7 trên đường mặc định.
- GET /catalog/books/7 khi có context-path=/catalog.
- GET /api/books/7 khi có servlet path=/api và matching-strategy phù hợp.
- GET /legacy/check khi có ServletRegistrationBean("/legacy/*").
- POST /books theo Content-Type application/json và body hợp lệ.
- Trường hợp HTTP method, path hoặc media type sai.
- Endpoint Actuator/health nếu có, và mapping thực tế khi management port tách riêng.

RANDOM_PORT khiến embedded server khởi động thật và chọn port khả dụng. Đây là nơi phát hiện xung đột Servlet mapping, sai cổng, request prefix, security filter hoặc proxy settings mà unit test controller đơn lẻ không thấy.

### 12.3. Kiểm tra trùng mapping lúc startup

Nếu hai controller khai báo handler mapping giống nhau theo tập điều kiện MVC và không thể phân biệt, Spring MVC có thể báo ambiguous mapping khi khởi động. Ví dụ hai phương thức @GetMapping("/books") cùng context và điều kiện sẽ xung đột.

Trùng mapping của controller khác với xung đột Servlet registration: một trường hợp xảy ra trong RequestMappingHandlerMapping, trường hợp kia liên quan URL pattern/Servlet name được đăng ký với Tomcat.

## 13. Những lỗi phổ biến và cách sửa

| Triệu chứng | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| Tomcat mở cổng nhưng mọi controller trả 404 | Controller ngoài component scan, Servlet path sai, request bị Servlet khác chặn | Kiểm tra package, Actuator mappings, servlet registrations |
| /books/7 trả 404 nhưng /catalog/books/7 trả 200 | Đã đặt server.servlet.context-path=/catalog | Kiểm tra context path |
| /api/books/7 trả 404 dù @GetMapping("/books/{id}") đúng | Prefix được cấu hình sai tầng hoặc router path không tương thích | Kiểm tra spring.mvc.servlet.path, matcher, servlet registration |
| 404 chỉ khi sau reverse proxy | Proxy rewrite, forwarded path, ingress rule sai | So sánh external URL với request path tại ứng dụng |
| GET hoạt động nhưng POST cùng path trả 405 | Handler chỉ khai báo @GetMapping | Kiểm tra HTTP method mapping |
| POST trả 415 | Content-Type không đúng consumes | Kiểm tra Content-Type và body converter |
| Request trả 406 | Accept không phù hợp produces | Kiểm tra Accept và handler produces |
| Startup báo ambiguous mapping | Hai MVC handler mappings trùng điều kiện | Kiểm tra các @RequestMapping/GetMapping |
| Request /books đi tới legacy Servlet | Servlet khác đăng ký /books/* cụ thể hơn "/" | Kiểm tra ServletRegistrationBean và mappings |
| Sau @EnableWebMvc tài nguyên tĩnh/CORS thay đổi | MVC auto-configuration mặc định không còn áp dụng đầy đủ | Xem WebMvcConfigurer và @EnableWebMvc |
| Filter bảo mật hoạt động nhưng HandlerInterceptor không chạy | Request không đi qua DispatcherServlet hoặc không khớp MVC handler | Kiểm tra servlet mapping và MVC interceptor registration |
| /actuator/mappings trả 404/403 | Actuator chưa có/exposed, management port khác, security policy | Kiểm tra starter, exposure, port, filter chain |
| Servlet registration thêm thủ công gây lỗi startup | Trùng tên Servlet, URL mapping, bean hoặc cấu hình servlet path | Xác định chính xác bean và registration ownership |

### 13.1. Không dùng @EnableWebMvc để giải quyết mọi lỗi route

Trong ứng dụng starter-web chuẩn, auto-configuration đã đăng ký DispatcherServlet và MVC infrastructure. @EnableWebMvc không tạo ra controller bị thiếu trong component scan. Nó còn có thể thay đổi default Boot MVC configuration, làm lỗi tài nguyên tĩnh, converters hoặc CORS nếu tự cấu hình không đầy đủ.

### 13.2. Không dùng @ServletComponentScan để tìm @RestController

@ServletComponentScan dành cho annotation thuộc Servlet API như @WebServlet/@WebFilter/@WebListener. @RestController là Spring bean được component scan phát hiện. Nếu đặt @RestController ngoài package được scan, sửa phạm vi component scan hoặc cấu trúc package phù hợp.

### 13.3. Không tự đăng ký DispatcherServlet thứ hai khi chỉ cần prefix

Nếu muốn endpoint có URL /api/books, có ba cách thường bị trộn lẫn: context path /api, servlet path /api hoặc @RequestMapping("/api/books"). Mỗi cách có phạm vi khác nhau. Đừng thêm DispatcherServlet mới chỉ để có prefix; điều đó làm tăng nguy cơ xung đột Servlet mapping và MVC infrastructure.

### 13.4. Không nhầm mapping của servlet với mapping của controller

Một controller có thể được Spring MVC đăng ký chính xác nhưng không nhận được request vì container đã giao URL cho Servlet khác. Ngược lại, Servlet mapping có thể đúng nhưng không có MVC handler vì controller không được scan. Dùng hai lớp kiểm tra riêng: ServletContext registrations và RequestMappingHandlerMapping/Actuator mappings.

### 13.5. Đừng mặc định mọi 404 là NoHandlerFoundException

Spring Boot có thể cấu hình resource handler /**; request không khớp controller vẫn có thể được resource handler chọn rồi trả lỗi vì không tìm thấy tệp. Với Spring Framework 6.x, có thể thấy NoResourceFoundException. Xem stack trace và handler thực tế trước khi cài một global exception handler rồi quy kết sai nguồn lỗi.

### 13.6. Nếu có Spring Security thì request còn đi qua filter trước MVC

Khi truy cập route được bảo vệ, response 401, 403 hoặc redirect login có thể xuất hiện trước khi controller được gọi. Việc không thấy breakpoint ở controller không tự chứng minh DispatcherServlet map sai. Kiểm tra security filter chain, matcher và quy tắc truy cập trước khi thay đổi Servlet registration.

## 14. Quy trình quyết định khi muốn thay đổi ánh xạ

1. Ghi lại URL external mà client phải gọi và URL Tomcat thực sự nhận sau proxy/ingress.
2. Xác định đường chung cho **toàn ứng dụng** hay chỉ cho một nhóm controller.
3. Nếu thay toàn ứng dụng Servlet, xét server.servlet.context-path.
4. Nếu chỉ thêm route prefix cho nhóm API, xét @RequestMapping ở class/controller hoặc cấu hình API routing.
5. Nếu thật sự cần đổi vùng quản lý của DispatcherServlet, xét spring.mvc.servlet.path và chiến lược path matching của phiên bản Spring Boot.
6. Nếu cần một Servlet khác cùng server, dùng ServletRegistrationBean hoặc @WebServlet đúng phạm vi, với URL pattern không xung đột.
7. Nếu cần thay registration của DispatcherServlet chính, dùng DispatcherServletRegistrationBean có kiểm soát; kiểm tra bean name, Servlet name, mapping và DispatcherServletPath.
8. Khởi động project bằng đúng profile, kiểm tra ServletContext registrations và MVC handler mappings.
9. Chạy MockMvc để xác nhận handler/binding, rồi kiểm tra HTTP trên cổng thật để xác nhận container routing.
10. Kiểm tra security, Actuator exposure, static resources, forwarding và reverse proxy sau thay đổi.

Đừng bỏ qua regression test khi đổi context path hoặc servlet path: một thay đổi tưởng chỉ tác động một route có thể ảnh hưởng tất cả endpoint MVC, static resource URLs, error page và đường link sinh ra trong ứng dụng.

## 15. Tự kiểm tra kiến thức

**Câu 1: Có cần tự tạo DispatcherServlet khi dùng spring-boot-starter-web không?**  
Thông thường không. DispatcherServletAutoConfiguration tạo bean và registration phù hợp trong ứng dụng Servlet MVC.

**Câu 2: @GetMapping("/books") có đăng ký một Servlet riêng không?**  
Không. Nó khai báo MVC handler method để DispatcherServlet chọn sau khi Servlet container đã chuyển request tới DispatcherServlet.

**Câu 3: server.servlet.context-path=/shop khác gì spring.mvc.servlet.path=/api?**  
/shop là tiền tố của web application Servlet; /api là tiền tố mapping cho DispatcherServlet. Nếu dùng cả hai, URL MVC có thể là /shop/api/... và cần cấu hình strategy tương thích cho servlet prefix trên Spring Boot 3.3.

**Câu 4: Vì sao /legacy/check không chạy qua @ControllerAdvice?**  
Nếu có Servlet riêng map /legacy/*, Tomcat có thể chuyển request trực tiếp đến Servlet đó. Nó không qua DispatcherServlet, nên MVC ControllerAdvice không xử lý lỗi của Servlet ấy theo cách thông thường.

**Câu 5: Có thể thay servlet path bằng cách thêm @RequestMapping("/api") không?**  
Đó là một cách thêm tiền tố cho route của controller, không thay đổi đăng ký Servlet ở Tomcat. Phạm vi thay đổi khác nhau.

**Câu 6: Vì sao Spring Boot 3.3 cần chú ý khi dùng spring.mvc.servlet.path?**  
Vì property này không tương thích với PathPatternParser mặc định theo tài liệu Boot 3.3; nếu đặt prefix, cần chọn matching-strategy phù hợp, thường là ant-path-matcher, hoặc thiết kế prefix ở tầng khác.

**Câu 7: MockMvc PASS có chứng minh servlet được map đúng ở Tomcat không?**  
Chưa đủ. MockMvc chủ yếu kiểm tra Spring MVC pipeline. Khi sửa ServletRegistrationBean hoặc mapping prefix, cần kiểm tra HTTP qua embedded container thực.

## 16. Những nguyên tắc cần nhớ

- DispatcherServlet là front controller của Spring MVC; Spring Boot Servlet stack thường tự tạo bean và registration của nó.
- Servlet container chọn Servlet theo URL pattern **trước**, DispatcherServlet chọn controller/handler theo @RequestMapping **sau**.
- server.servlet.context-path, spring.mvc.servlet.path và @RequestMapping có phạm vi khác nhau; cần ghép đúng URL và tránh cộng prefix hai lần.
- Spring Boot 3.3 dùng PathPatternParser mặc định; custom servlet path prefix cần kiểm tra tính tương thích, thường dùng ant-path-matcher.
- DispatcherServletRegistrationBean dùng khi cần kiểm soát registration của DispatcherServlet; ServletRegistrationBean phù hợp để đăng ký Servlet bổ sung. Không tạo nhiều DispatcherServlet nếu chưa có yêu cầu rõ ràng.
- Filter/Spring Security có thể chạy trước Servlet; HandlerInterceptor và @ControllerAdvice nằm trong MVC pipeline.
- Khi debug 404/405/406/415, hãy kiểm tra route, method, Content-Type/Accept, component scan, Servlet URL mapping, path prefix và proxy trước khi sửa code nghiệp vụ.
- Kiểm tra cả Actuator mappings/Servlet registrations và thực nghiệm HTTP thật; test MockMvc không thay thế hoàn toàn kiểm thử web server.

Khi hiểu ranh giới giữa **Servlet registration** và **Spring MVC handler mapping**, bạn có thể lần theo chính xác đường đi của request, giải thích vì sao một endpoint được hoặc không được gọi, và thay đổi cấu hình Spring Boot mà không vô tình tạo thêm Servlet hoặc làm mất route đang hoạt động.

## 17. Tài liệu tham khảo

- Spring Boot 3.3 — Servlet Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Spring Boot 3.3 — Common Application Properties (spring.mvc.servlet.path, spring.mvc.pathmatch.matching-strategy): https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3 API — DispatcherServletRegistrationBean: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/servlet/DispatcherServletRegistrationBean.html
- Spring Boot 3.3 API — DispatcherServletAutoConfiguration: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/servlet/DispatcherServletAutoConfiguration.html
- Spring Boot 3.3 API — ServletRegistrationBean: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/servlet/ServletRegistrationBean.html
- Spring Framework 6.x — DispatcherServlet, Front Controller: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html

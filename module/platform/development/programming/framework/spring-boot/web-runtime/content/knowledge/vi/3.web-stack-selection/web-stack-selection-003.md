# spring-boot-starter-web và mô hình Servlet với Spring MVC

Khi muốn xây dựng một ứng dụng HTTP truyền thống bằng Spring Boot, lựa chọn phổ biến là **spring-boot-starter-web**. Starter này đưa Spring Web MVC và máy chủ Servlet nhúng vào classpath, để ứng dụng có thể nhận request, ánh xạ URL tới controller, gọi nghiệp vụ và trả HTTP response. Người phát triển chủ yếu viết controller, service và cấu hình; Spring Framework và Spring Boot đảm nhiệm phần lớn hạ tầng.

Bài học này tập trung vào **Servlet web stack** của Spring Boot: dependency nào được đưa vào, Spring Boot khởi động web server ra sao, request đi qua Servlet container và DispatcherServlet như thế nào, cũng như cách viết, chạy, kiểm thử và chẩn đoán một ứng dụng MVC.

## 1. Starter web giải quyết vấn đề gì?

Một ứng dụng HTTP cần nhiều thành phần phối hợp:

- Web server mở cổng mạng và nhận kết nối HTTP.
- Servlet container quản lý Servlet, Filter, Listener và request/response.
- Web framework tìm controller phù hợp, bind tham số và chuyển đổi dữ liệu.
- Dependency injection container tạo controller, service và các dependency.
- JSON serialization biến Java object thành dữ liệu trả về cho API.
- Cấu hình môi trường quyết định port, context path và các giới hạn runtime.

Nếu ghép các thư viện thủ công, lập trình viên phải phối hợp nhiều dependency, phiên bản và bước khởi tạo. Spring Boot cung cấp starter cùng auto-configuration để các thành phần phổ biến hoạt động với ít cấu hình hơn.

**spring-boot-starter-web** là một dependency tập hợp các thành phần hỗ trợ phát triển ứng dụng Servlet web, đặc biệt là **Spring MVC**. Starter không phải web server và cũng không phải toàn bộ Spring Framework. Nó giúp đưa những thư viện cần thiết vào ứng dụng; Spring Boot dựa vào classpath và điều kiện cấu hình để tạo các bean và server thích hợp.

Các tình huống phù hợp: REST API, ứng dụng MVC trả HTML, backend có JDBC/JPA và nhiều lời gọi blocking, ứng dụng nghiệp vụ cần request/response đồng bộ, cũng như hệ thống đang dùng Servlet Filter, Spring Security Servlet và thư viện Java truyền thống.

## 2. Các lớp trách nhiệm

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Ứng dụng của bạn | Định nghĩa endpoint và nghiệp vụ | GreetingController, OrderService |
| Spring Framework | Quản lý bean và xử lý web với Spring MVC | ApplicationContext, DispatcherServlet, HandlerMapping |
| Spring Boot | Khởi tạo ứng dụng, tự cấu hình MVC và server | SpringApplication, WebMvcAutoConfiguration |
| Servlet container | Thực thi Servlet API, Filter chain và xử lý request/response | Embedded Tomcat |
| Web server connector | Nhận kết nối mạng và trao đổi dữ liệu HTTP | HTTP connector của Tomcat |

Mối quan hệ ở mức khái niệm:

~~~text
Ứng dụng Spring Boot
    |
    +-- Controller / Service / Repository
    |
    +-- Spring Framework
    |     +-- IoC container / ApplicationContext
    |     +-- Spring MVC / DispatcherServlet
    |
    +-- Spring Boot
    |     +-- Bootstrap
    |     +-- Auto-configuration
    |     +-- Embedded server integration
    |
    +-- Tomcat (mặc định khi dùng starter-web)
          +-- HTTP Connector
          +-- Servlet container
          +-- Filters -> DispatcherServlet
~~~

Sơ đồ mô tả cách các lớp phối hợp, không có nghĩa Spring Framework chỉ chạy được bên trong Spring Boot. Có thể dùng Spring Framework mà không dùng Boot; Boot là lớp hỗ trợ cấu hình và vận hành xây dựng trên Framework.

**DispatcherServlet là Servlet của Spring MVC, không phải web server.** Tomcat nhận kết nối HTTP và gọi Servlet. Controller lại là bean của ứng dụng được Spring MVC gọi thông qua các handler adapter.

## 3. Những dependency quan trọng của spring-boot-starter-web

Với Spring Boot 3.3.x, starter web thông thường đưa vào các thành phần chính:

| Nhóm | Vai trò |
|---|---|
| spring-boot-starter | Các khả năng nền tảng của Spring Boot, cấu hình và logging |
| spring-web | HTTP abstraction, REST support và các thành phần nền của Spring Web |
| spring-webmvc | DispatcherServlet, controller mapping, argument resolver, MVC infrastructure |
| spring-boot-starter-tomcat | Máy chủ Tomcat nhúng và Servlet runtime mặc định |
| spring-boot-starter-json | Tích hợp Jackson và các thư viện JSON đi kèm |

Spring Boot quản lý phiên bản các dependency thông qua dependency management/BOM tương ứng. Ứng dụng thường không cần tự đặt version riêng cho từng thư viện do starter cung cấp.

Một số hiểu nhầm cần tránh:

- **Starter web không tự thêm Spring Security.** Nếu cần xác thực và phân quyền, phải thêm và cấu hình capability bảo mật phù hợp.
- **Starter web không mặc nhiên cung cấp toàn bộ Bean Validation API/provider.** Với Spring Boot 3.x, ứng dụng thường thêm spring-boot-starter-validation khi muốn dùng @Valid, @NotBlank và các constraint để validate request.
- **Jackson nằm trong dependency JSON mặc định**, nhưng việc chuyển đổi phụ thuộc content type, message converter và cấu hình của ứng dụng.
- **Tomcat là lựa chọn server nhúng mặc định**, nhưng có thể thay bằng server Servlet khác được Spring Boot hỗ trợ.
- **Starter chỉ quyết định một phần classpath.** Thực tế bean nào được tạo còn phụ thuộc vào auto-configuration conditions và cấu hình hiện hành.

Dùng Gradle kiểm tra dependency graph của chính ứng dụng:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Khi chẩn đoán xung đột thư viện, hãy nhìn dependency graph thực tế thay vì suy luận chỉ từ tên starter.

## 4. Vì sao starter-web dẫn tới ứng dụng Servlet?

Spring Boot xác định loại web application dựa trên classpath và cấu hình. Khi Spring MVC/Servlet stack hiện diện và không có override trái ngược, Boot thường chọn **WebApplicationType.SERVLET**. Nó tạo web application context phù hợp và cấu hình web server.

Các bước khởi động khái quát:

~~~text
JVM chạy main()
    |
SpringApplication.run(...)
    |
Đọc Environment và nguồn cấu hình
    |
Tạo ServletWebServerApplicationContext
    |
Component scan + Bean definitions
    |
Auto-configuration của Spring Boot
    |
Refresh ApplicationContext
    |
Tạo/khởi động embedded Servlet web server
    |
Đăng ký DispatcherServlet, Filter, Listener
    |
Ứng dụng sẵn sàng nhận HTTP requests
~~~

Đây là sơ đồ khái niệm của vòng đời startup; thứ tự chi tiết các callback và nội bộ refresh context phụ thuộc phiên bản Spring Boot.

Các auto-configuration đáng biết:

- **ServletWebServerFactoryAutoConfiguration** chuẩn bị tích hợp Servlet web server và factory tương ứng khi điều kiện phù hợp.
- **DispatcherServletAutoConfiguration** tạo và đăng ký DispatcherServlet nếu ứng dụng chưa cung cấp cấu hình thay thế.
- **WebMvcAutoConfiguration** cung cấp cấu hình MVC mặc định, chẳng hạn handler mapping, message conversion, static resources và nhiều MVC setting.

Auto-configuration thường có điều kiện, chẳng hạn có class cần thiết, là Servlet web application, chưa có bean do ứng dụng tự định nghĩa, hoặc property đã được bật. Vì vậy, không nên hiểu auto-configuration là “luôn luôn tạo mọi bean”.

Annotation @SpringBootApplication cũng có ba vai trò chính: đánh dấu cấu hình Boot, kích hoạt auto-configuration và component scan. Vị trí package của lớp main ảnh hưởng phạm vi tìm controller và service. Thông thường hãy đặt lớp main ở package cha của những package ứng dụng cần scan.

## 5. Request đi qua Servlet container và Spring MVC như thế nào?

Luồng xử lý HTTP đồng bộ thường gặp:

~~~text
HTTP client
    |
    v
Tomcat Connector: nhận kết nối, đọc HTTP request
    |
    v
Servlet container: HttpServletRequest / HttpServletResponse
    |
    v
Servlet Filter chain (logging, encoding, security... nếu có)
    |
    v
DispatcherServlet (Spring MVC front controller)
    |
    +--> HandlerMapping: tìm handler theo URL, HTTP method...
    |
    +--> HandlerAdapter: gọi handler/controller method
    |      +--> argument resolvers / data binding
    |      +--> conversion và validation khi được cấu hình
    |
    +--> Controller -> Service -> Repository
    |
    +--> Return value handling / HttpMessageConverter
    |
    v
Servlet container -> HTTP response -> Client
~~~

Một số thuật ngữ cụ thể:

- **HttpServletRequest/HttpServletResponse:** abstraction của Jakarta Servlet cho dữ liệu request/response.
- **Servlet Filter:** xử lý request/response ở biên Servlet; ví dụ logging, correlation ID, security. Filter có thể từ chối request trước khi vào controller.
- **DispatcherServlet:** front controller trung tâm của Spring MVC.
- **RequestMappingHandlerMapping:** tìm method controller phù hợp dựa trên request mapping.
- **RequestMappingHandlerAdapter:** thực thi method đó, hỗ trợ binding và xử lý giá trị trả về.
- **HandlerMethodArgumentResolver:** ánh xạ path variable, query param, header, principal, request body... thành tham số Java.
- **HttpMessageConverter:** đọc request body hoặc ghi response body theo loại dữ liệu, ví dụ JSON.
- **HandlerExceptionResolver / @ExceptionHandler:** cho phép chuyển lỗi của MVC thành phản hồi HTTP theo chính sách.

Bởi vì filter và MVC có trách nhiệm khác nhau, việc request không vào controller chưa chứng minh controller sai. Request có thể bị filter chặn, đường dẫn không khớp DispatcherServlet, request mapping không khớp, hoặc dữ liệu không thể binding.

### 5.1. Đường đi của GET

Giả sử client gọi GET /api/greetings/Linh. Tomcat tiếp nhận request; filter chain xử lý nếu có; DispatcherServlet chọn method được gắn @GetMapping với pattern tương ứng; Spring MVC bind chuỗi Linh vào tham số; controller trả object Java; Jackson serialize object thành JSON; Tomcat gửi response.

### 5.2. Đường đi của POST JSON

Với POST /api/echo và Content-Type: application/json, Spring MVC dùng message converter để đọc JSON thành kiểu Java được khai báo bởi @RequestBody. Controller xử lý rồi trả object hoặc ResponseEntity. Nếu body không phải JSON hợp lệ, kiểu không đọc được, hoặc content type không được hỗ trợ, request có thể bị từ chối trước khi gọi method controller.

### 5.3. Thread xử lý request

Với mô hình Spring MVC đồng bộ phổ biến, Tomcat dùng thread pool để xử lý nhiều request. Nếu service gọi database bằng JDBC hoặc chờ HTTP client blocking, thread đang xử lý thường bị chiếm trong thời gian chờ. Khi số request đồng thời tăng, có thể hết thread hoặc gặp hàng đợi, timeout và suy giảm throughput.

Servlet cũng hỗ trợ xử lý bất đồng bộ; Spring MVC có Callable, DeferredResult, streaming và các cơ chế khác. Vì vậy, không nên kết luận mọi request MVC luôn dùng một thread từ đầu đến cuối. Khi dự đoán khả năng chịu tải, phải xem mô hình handler và các I/O dependency thực tế.

## 6. Ví dụ chạy được: Spring Boot 3.3 + Java 21 + Gradle

Ví dụ dưới đây tạo một ứng dụng HTTP Servlet tối giản, có GET và POST JSON. Không cần tự cài Tomcat riêng; embedded Tomcat được khởi động nhờ starter-web và Spring Boot.

Cấu trúc thư mục:

~~~text
mvc-servlet-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/webdemo/
    │   ├── WebDemoApplication.java
    │   └── GreetingController.java
    └── test/java/com/example/webdemo/
        └── GreetingControllerTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'mvc-servlet-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Plugin Spring Boot cung cấp task bootRun và bootJar. Dependency-management plugin giúp dùng các version do Spring Boot quản lý; ví dụ không phải tự ghi version cho spring-boot-starter-web.

**src/main/java/com/example/webdemo/WebDemoApplication.java**

~~~java
package com.example.webdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebDemoApplication.class, args);
    }
}
~~~

**src/main/java/com/example/webdemo/GreetingController.java**

~~~java
package com.example.webdemo;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api")
public class GreetingController {

    @GetMapping("/greetings/{name}")
    public Map<String, String> greet(@PathVariable String name) {
        return Map.of("message", "Hello, " + name);
    }

    @PostMapping("/echo")
    public ResponseEntity<Map<String, String>> echo(
            @RequestBody EchoRequest request) {
        if (request.text() == null || request.text().isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "text must not be blank");
        }
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(Map.of("echo", request.text()));
    }

    public record EchoRequest(String text) {
    }
}
~~~

Trong ví dụ:

- @RestController đánh dấu bean controller với response body serialization.
- @RequestMapping("/api") đặt prefix cho các endpoint.
- @GetMapping và @PostMapping ràng buộc HTTP method + đường dẫn.
- @PathVariable lấy một thành phần đường dẫn.
- @RequestBody yêu cầu Spring MVC đọc JSON body thành record EchoRequest.
- ResponseEntity đặt HTTP status là 201 Created cho request POST thành công.
- ResponseStatusException trả 400 Bad Request khi text bị bỏ trống; lỗi body JSON không hợp lệ cũng thường bị Spring MVC từ chối ở bước đọc body.
- Map chỉ chứa một khóa trong mỗi response, nên JSON mẫu dưới đây có nội dung dự đoán được.

Ví dụ dùng thao tác POST mô phỏng echo, không lưu dữ liệu vào database. Trong ứng dụng thật, 201 Created nên tương ứng với việc tạo một tài nguyên mới; nếu chỉ xử lý và trả kết quả mà không tạo tài nguyên, status 200 OK có thể phù hợp hơn.

### 6.1. Chạy ứng dụng

Nếu project đã có Gradle wrapper, chạy trong thư mục mvc-servlet-demo:

~~~bash
./gradlew bootRun
~~~

Trong PowerShell trên Windows, lệnh tương ứng là .\gradlew.bat bootRun. Nếu tự tạo project chưa có wrapper, cần tạo Gradle wrapper hoặc dùng Gradle đã cài; ví dụ phù hợp với Gradle 8.5 và JDK 21.

Spring Boot thường in log về Tomcat khởi động trên port 8080, sau đó ứng dụng sẵn sàng. Port mặc định có thể thay đổi nếu cấu hình environment hoặc properties ghi đè.

Trong terminal khác (cú pháp Bash), kiểm thử GET:

~~~bash
curl -i http://localhost:8080/api/greetings/Linh
~~~

Kết quả kỳ vọng: status **200 OK**, response body JSON:

~~~json
{"message":"Hello, Linh"}
~~~

Kiểm thử POST JSON:

~~~bash
curl -i -X POST http://localhost:8080/api/echo \
    -H "Content-Type: application/json" \
    -d '{"text":"Hello MVC"}'
~~~

Kết quả kỳ vọng: status **201 Created**, response body:

~~~json
{"echo":"Hello MVC"}
~~~

Thử chuỗi trống:

~~~bash
curl -i -X POST http://localhost:8080/api/echo \
    -H "Content-Type: application/json" \
    -d '{"text":""}'
~~~

Kết quả kỳ vọng: status **400 Bad Request** do controller ném ResponseStatusException. Body lỗi phụ thuộc cấu hình xử lý exception, nên không giả định nó luôn có một JSON schema nhất định.

Response headers và thứ tự header không cố định; kiểm chứng các status và JSON body nêu trên. Đây là kết quả dự kiến từ code, không phải bản ghi một lần chạy thực tế.

### 6.2. Đóng gói executable JAR

~~~bash
./gradlew clean bootJar
java -jar build/libs/mvc-servlet-demo-1.0.0.jar
~~~

Trong cấu hình ví dụ, Boot đóng gói ứng dụng cùng dependency runtime và launcher phù hợp. Khi chạy JAR, JVM khởi tạo Spring Boot rồi embedded Tomcat; không cần triển khai WAR vào Tomcat bên ngoài.

## 7. Kiểm thử Spring MVC bằng MockMvc

Cần phân biệt kiểm thử MVC handler với kiểm thử một kết nối HTTP thật. **MockMvc** chạy request qua hạ tầng Spring MVC trong test context mà không mở socket mạng. Nó rất hữu ích để kiểm tra route, JSON conversion, validation và status.

**src/test/java/com/example/webdemo/GreetingControllerTest.java**

~~~java
package com.example.webdemo;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(GreetingController.class)
class GreetingControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void getReturnsJson() throws Exception {
        mvc.perform(get("/api/greetings/Linh"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("Hello, Linh"));
    }

    @Test
    void postEchoReturnsCreated() throws Exception {
        mvc.perform(post("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"Hello MVC\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.echo").value("Hello MVC"));
    }

    @Test
    void blankTextIsRejected() throws Exception {
        mvc.perform(post("/api/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"\"}"))
            .andExpect(status().isBadRequest());
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

@WebMvcTest tập trung vào MVC slice, hữu ích khi controller không phụ thuộc nhiều bean nghiệp vụ. Với controller gọi service cần mock hoặc import những dependency cần thiết cho test. Để kiểm thử Tomcat thật, có thể dùng @SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT) và HTTP client test phù hợp; đó là tầng integration test khác với MockMvc slice.

Lưu ý: ví dụ chưa thêm spring-boot-starter-security nên test không có các yêu cầu đăng nhập hoặc CSRF do Spring Security. Nếu dự án thêm Security, cần cấu hình test credentials, quyền và CSRF token theo chính sách thực tế.

## 8. Những annotation MVC nên biết

| Annotation/API | Vai trò |
|---|---|
| @RestController | @Controller kết hợp cơ chế trả response body |
| @Controller | Controller trả view hoặc response theo cách được cấu hình |
| @RequestMapping | Khai báo đường dẫn, method, consumes, produces và điều kiện mapping |
| @GetMapping, @PostMapping, @PutMapping, @DeleteMapping | Shortcut theo HTTP method |
| @PathVariable | Lấy tham số từ URL path |
| @RequestParam | Lấy tham số từ query string hoặc form phù hợp |
| @RequestHeader | Lấy giá trị header |
| @RequestBody | Chuyển request body thành Java object qua message converter |
| @ResponseBody | Ghi giá trị trả về vào response body |
| ResponseEntity | Điều khiển status, headers và body |
| @ExceptionHandler, @RestControllerAdvice | Định nghĩa cách xử lý exception ở MVC layer |

Controller nên mỏng: nhận input, gọi service, chuyển kết quả thành response. Không nên chứa toàn bộ business logic, không tự tạo JDBC connection trong controller và không giữ request-specific state trong mutable field của singleton bean.

### 8.1. JSON và Content negotiation

Khi có Jackson và Spring MVC, object Java thường được serialize thành JSON nếu media type phù hợp. Spring MVC dùng **Content-Type** để hiểu kiểu nội dung request, còn **Accept** để thương lượng kiểu phản hồi mà client có thể nhận.

- **400 Bad Request:** body không thể đọc/bind hoặc dữ liệu sai theo quy tắc xử lý.
- **404 Not Found:** không tìm được mapping/tài nguyên tương ứng.
- **405 Method Not Allowed:** URL có thể khớp nhưng HTTP method không được handler hỗ trợ.
- **406 Not Acceptable:** server không tạo được phản hồi phù hợp với Accept.
- **415 Unsupported Media Type:** request dùng kiểu body mà handler/converter không hỗ trợ.
- **500 Internal Server Error:** lỗi nội bộ chưa được xử lý phù hợp.

Không nên đánh đồng mọi 4xx với “server không chạy”. Đọc method, URL, Content-Type, Accept và log mapping để tìm đúng nguyên nhân.

### 8.2. Validation cần dependency riêng

Khi muốn kiểm tra DTO qua @Valid và các annotation như @NotBlank, ứng dụng Spring Boot 3.x thường thêm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

Rồi khai báo constraint trên DTO và dùng @Valid tại tham số @RequestBody. Đó là một bước mở rộng của ứng dụng; **không** nên giả định chỉ thêm starter-web thì mọi validation annotation sẽ tự hoạt động.

## 9. Cấu hình server và đường dẫn

Ví dụ cấu hình tùy chọn trong src/main/resources/application.yml:

~~~yaml
server:
  port: 8081
  servlet:
    context-path: /training
~~~

Với cấu hình này, GET mapping /api/greetings/{name} được gọi qua:

~~~text
http://localhost:8081/training/api/greetings/Linh
~~~

Cần phân biệt:

- **server.port:** cổng mà embedded server dùng để nhận kết nối.
- **server.servlet.context-path:** prefix của toàn bộ Servlet web application.
- **spring.mvc.servlet.path:** có thể cấu hình đường dẫn gắn với DispatcherServlet trong trường hợp cụ thể.
- **@RequestMapping:** đường dẫn do controller định nghĩa trong Spring MVC.
- **Reverse proxy prefix:** có thể tồn tại ở tầng gateway và không nhất thiết giống context path nội bộ.

Khi gặp 404 sau khi thay đổi context path, kiểm tra URL bên ngoài và URL thực tế ứng dụng nhận thay vì sửa controller một cách tùy tiện.

Ứng dụng cũng có thể chỉnh giới hạn và pool của Tomcat bằng các thuộc tính server.tomcat.*. Chỉ thay các thông số khi có quan sát về tải, thời gian chờ, tài nguyên và mục tiêu vận hành; tăng số thread không tự khắc phục database chậm hoặc lệnh blocking không được giới hạn.

## 10. Thay Tomcat bằng Servlet server khác

Mặc định spring-boot-starter-web dùng embedded Tomcat. Khi có yêu cầu về Jetty, có thể loại starter Tomcat mặc định rồi thêm starter Jetty phù hợp với phiên bản Boot:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }
    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
~~~

Đây là **phương án thay thế đoạn khai báo starter-web** trong build.gradle, không phải đoạn cần chép thêm bên dưới dependency Tomcat hiện có. Kiểm tra runtimeClasspath sau khi đổi để tránh nhiều server implementation ngoài chủ đích.

Cách viết controller Spring MVC thường vẫn giữ nguyên, vì Spring MVC lập trình trên Servlet abstraction. Tuy nhiên, cấu hình connector, thread pool, servlet version và hành vi vận hành có thể khác giữa Tomcat và Jetty.

Ngoài executable JAR, ứng dụng có thể đóng gói WAR và triển khai vào external Servlet container khi môi trường yêu cầu. Khi đó cần cấu hình WAR packaging, Servlet initializer và dependency scope phù hợp; external container chịu trách nhiệm khởi động server. Không đơn giản đổi đuôi JAR thành WAR.

## 11. MVC/Servlet so với WebFlux

spring-boot-starter-web đại diện cho đường phát triển **Spring MVC trên Servlet stack**. Spring WebFlux là mô hình web khác, thường chọn qua spring-boot-starter-webflux.

| Khía cạnh | Spring MVC / Servlet | Spring WebFlux |
|---|---|---|
| Runtime nền | Jakarta Servlet và Servlet container | Reactive Streams / WebFlux HTTP runtime |
| Mô hình mặc định | Request/response, thường đồng bộ | Reactive, non-blocking khi toàn bộ chuỗi hỗ trợ |
| Return type phổ biến | DTO, ResponseEntity, ModelAndView | Mono, Flux và các kiểu reactive |
| I/O blocking | Phù hợp với nhiều thư viện JDBC/JPA truyền thống | Cần tránh chặn event-loop; dùng client/driver non-blocking khi muốn khai thác lợi ích reactive |
| Tích hợp hạ tầng | Servlet Filter, Spring MVC interceptor, Security Servlet | WebFilter và Spring Security Reactive |
| Tình huống chọn | REST/MVC nghiệp vụ truyền thống, blocking dependencies | Workload có nhiều I/O không chặn với thư viện và thiết kế reactive |

Không có chuyện WebFlux luôn nhanh hơn Spring MVC. Khả năng chịu tải phụ thuộc workload, database/client, tài nguyên, backpressure và thiết kế code. Nếu ứng dụng chủ yếu dùng JDBC blocking và mô hình imperative, MVC thường đơn giản và dễ bảo trì hơn.

Nếu vô tình có cả Spring MVC và WebFlux trên classpath, Spring Boot thường ưu tiên kiểu ứng dụng Servlet/MVC theo mặc định. Vì vậy phải kiểm tra starter và WebApplicationType thực tế, không chọn stack dựa trên việc controller dùng một annotation trông giống nhau.

## 12. Lỗi thường gặp và cách điều tra

### 12.1. Ứng dụng không mở port

Kiểm tra startup log, dependency server, loại WebApplicationType, cấu hình server.port, port conflict và biến môi trường. Nếu ứng dụng được cấu hình spring.main.web-application-type=none, Boot sẽ không khởi chạy web server theo cách mặc định.

Nếu không dùng spring-boot-starter-web hoặc đã loại toàn bộ Servlet server mà không cung cấp server khác, auto-configuration có thể không tạo được runtime web như mong muốn.

### 12.2. 404 dù ứng dụng chạy

Xác minh context path, HTTP URL, package scan, @RequestMapping và DispatcherServlet mapping. Nếu lớp @SpringBootApplication nằm ở package không phải cha của controller, controller có thể không được phát hiện bởi component scan mặc định.

### 12.3. 405, 415 hoặc 406

Kiểm tra HTTP method, Content-Type, Accept và điều kiện consumes/produces. Ví dụ POST JSON gửi thiếu application/json có thể không được converter xử lý như mong đợi, dù GET cùng URL hoạt động.

### 12.4. Trả JSON sai hoặc 500

Kiểm tra DTO/record có được Jackson đọc hay không, nullability, constructor, exception và phần service thực thi. Không giả định mọi exception là lỗi Tomcat. Controller/service có thể phát sinh lỗi nghiệp vụ; exception handler có thể chuyển thành status cụ thể.

### 12.5. Thêm @EnableWebMvc mà mất cấu hình mặc định

Khi sử dụng Spring Boot MVC, thường nên tận dụng các auto-configured MVC settings và chỉ tùy biến phần cần thiết. Bật @EnableWebMvc thủ công có thể làm một phần auto-configuration MVC của Boot không còn được áp dụng; chỉ dùng khi chủ đích tự quản lý MVC configuration.

### 12.6. Nhầm Jakarta Servlet và javax.servlet

Spring Boot 3 và Spring Framework 6 sử dụng namespace Jakarta, ví dụ jakarta.servlet.http.HttpServletRequest. Không sao chép nguyên mã javax.servlet từ ứng dụng Spring Boot 2 vào môi trường Boot 3 nếu chưa chuyển đổi API và dependency.

### 12.7. Lầm tưởng starter-web tự bảo mật ứng dụng

Starter-web không bật authentication/authorization cho tất cả endpoint. Khi thêm spring-boot-starter-security, filter chain, đăng nhập và CSRF có thể làm HTTP response thay đổi. Không tắt bảo mật chỉ để nhận 200 trong test; cần cấu hình access rule và test đúng intent.

### 12.8. Performance kém khi tăng concurrent requests

Tomcat thread pool, connection timeout, database pool, external HTTP client và blocking service đều có thể là nút thắt. Hãy đo số request đang chạy, queue, latency, thread dump và thời gian truy vấn; không sửa bằng cách tăng thread vô hạn.

## 13. Checklist chọn và triển khai starter-web

1. Xác định ứng dụng cần **Spring MVC/Servlet** hay reactive runtime dựa trên kiểu xử lý và dependency.
2. Thêm spring-boot-starter-web và giữ version theo Spring Boot dependency management.
3. Đặt lớp @SpringBootApplication ở package phù hợp để component scan tìm được controller và service.
4. Khai báo @RestController, request mappings, DTO và service rõ ràng.
5. Kiểm tra embedded server, port, context path và URL thực tế trong môi trường chạy.
6. Xác định Content-Type, Accept, status code và cách xử lý exception.
7. Thêm validation và security qua dependency/cấu hình riêng khi cần.
8. Kiểm thử cả MVC mapping bằng MockMvc và tích hợp server HTTP thật cho chức năng quan trọng.
9. Đánh giá thread, blocking I/O, timeout và connection pool dưới tải thực.
10. Kiểm tra runtime dependency graph khi thay server hoặc thêm WebFlux/Security.

**Kết luận:** spring-boot-starter-web giúp Spring Boot cấu hình một ứng dụng web Servlet sử dụng Spring MVC và server nhúng mặc định. Server nhận HTTP, Servlet container chạy Filter và DispatcherServlet, Spring MVC định tuyến đến controller, còn ứng dụng sở hữu quy tắc nghiệp vụ. Nắm rõ ranh giới giữa starter, Spring Boot, Spring Framework, Servlet container và controller giúp chọn đúng web stack, kiểm thử đúng lớp và xử lý sự cố hiệu quả.

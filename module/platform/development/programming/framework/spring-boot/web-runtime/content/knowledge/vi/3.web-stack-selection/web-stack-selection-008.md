# ServletWebServerApplicationContext và ReactiveWebServerApplicationContext trong Spring Boot

## 1. Vấn đề cần hiểu

Khi gọi SpringApplication.run(...), Spring Boot phải quyết định ứng dụng có chạy như một web application không và, nếu có, thuộc Servlet stack hay Reactive stack. Quyết định đó ảnh hưởng đến loại ApplicationContext được tạo, loại embedded web server factory cần có, cách đăng ký HTTP handler, chuỗi xử lý request, các auto-configuration được kích hoạt và mô hình đồng thời của ứng dụng.

Hai lớp trung tâm là:

- org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext
- org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext

Cả hai đều là ApplicationContext có khả năng quản lý vòng đời embedded web server. Chúng là những lớp nền của context, không phải tên của web server và không phải annotation đặt trên controller. Chọn đúng context là một phần thiết yếu của bài toán lựa chọn web stack.

Bài học tập trung vào Spring Boot 3.x, đặc biệt nhánh 3.3.x, và Java 17+. Các phiên bản Spring Boot mới hơn có thể thay đổi chi tiết API và package.

### Kết quả cần đạt

Sau bài học, bạn cần:

1. Giải thích được vai trò của ApplicationContext và WebServerApplicationContext.
2. Biết điều kiện để Spring Boot chọn SERVLET, REACTIVE hoặc NONE.
3. Phân biệt hai context theo superclass, factory, tầng web, pipeline request và lifecycle.
4. Hiểu lúc nào embedded web server được tạo, khởi động, phát event và đóng.
5. Tạo được hai ứng dụng nhỏ để tự kiểm chứng context và HTTP response.
6. Biết tìm nguyên nhân khi Spring Boot khởi động sai web stack hoặc không tìm được web server factory.

## 2. Các tầng khái niệm: Spring container, web context, web server

Không nên gộp bốn khái niệm sau thành một:

| Khái niệm | Vai trò |
| --- | --- |
| ApplicationContext | Container quản lý Bean, dependency, configuration, event và lifecycle của Spring |
| Web application context | ApplicationContext bổ sung môi trường, Bean và khả năng xử lý dành cho ứng dụng web |
| WebServerApplicationContext | Hợp đồng của context tự tạo và quản lý embedded WebServer |
| WebServer | Đối tượng đại diện cho máy chủ HTTP nhúng, có khả năng start, stop, lấy port |

Giao diện org.springframework.boot.web.context.WebServerApplicationContext mở rộng ApplicationContext và cung cấp getWebServer() cùng thông tin namespace của web server. getWebServer() có thể trả null trước khi server được tạo; không giả định có server sẵn trong constructor của một Bean.

Cả ServletWebServerApplicationContext và ReactiveWebServerApplicationContext đều triển khai ConfigurableWebServerApplicationContext, qua đó triển khai WebServerApplicationContext. Điểm khác nhau là cách chúng chuẩn bị môi trường web, yêu cầu loại WebServerFactory nào và kết nối web server với các handler HTTP.

Hai context này thường được Spring Boot chọn tự động. Lập trình viên phần lớn làm việc với @SpringBootApplication, starter, controller và configuration; không cần trực tiếp new một trong hai context.

## 3. ServletWebServerApplicationContext

### 3.1. Bản chất và vai trò

ServletWebServerApplicationContext là lớp thuộc package org.springframework.boot.web.servlet.context. Nó kế thừa GenericWebApplicationContext của Spring Framework và bổ sung việc tìm ServletWebServerFactory, tạo embedded WebServer, thiết lập ServletContext và đăng ký các thành phần của Servlet API.

Một ứng dụng khởi động qua annotation configuration thường dùng lớp con AnnotationConfigServletWebServerApplicationContext. Vì vậy, khi in tên class thực tế bạn thường thấy lớp con này thay vì chính ServletWebServerApplicationContext.

Đây là context phù hợp cho ứng dụng Servlet-based, thường là Spring MVC. Nó cũng có thể phục vụ các Servlet khác; sự tồn tại của ServletWebServerApplicationContext không đồng nghĩa ứng dụng bắt buộc phải có controller MVC.

### 3.2. Quan hệ với ServletWebServerFactory

Context tìm Bean kiểu ServletWebServerFactory để tạo web server. Một số implementation phổ biến:

- TomcatServletWebServerFactory: embedded Tomcat.
- JettyServletWebServerFactory: embedded Jetty.
- UndertowServletWebServerFactory: embedded Undertow.

Với spring-boot-starter-web, lựa chọn mặc định thông thường là Tomcat. Có thể đổi server bằng cách điều chỉnh dependency và cấu hình tương thích.

Context cần một factory phù hợp trong chính container. Nếu không có factory hoặc có nhiều factory mơ hồ, việc tạo server có thể thất bại. Không thể sửa một lỗi thiếu factory chỉ bằng cách thêm @RestController.

### 3.3. ServletContext và cơ chế đăng ký

Servlet stack sử dụng jakarta.servlet.ServletContext, Servlet, Filter và các cơ chế đăng ký tương ứng. ServletWebServerApplicationContext chuẩn bị ServletContext để các thành phần có thể hoạt động với embedded server.

Các thành phần có thể tham gia đăng ký:

- Servlet: thành phần tiếp nhận request ở tầng Servlet; DispatcherServlet là Servlet chính của Spring MVC.
- Filter: xử lý trước và sau Servlet; ví dụ filter cho security, logging hoặc CORS.
- ServletContextInitializer: tùy chỉnh quá trình khởi tạo và đăng ký.
- ServletRegistrationBean và FilterRegistrationBean: đăng ký Servlet/Filter một cách tường minh.

Spring Boot hỗ trợ tự động đăng ký Servlet và Filter Bean phù hợp. Khi cần mapping, thứ tự filter hoặc cấu hình cụ thể, dùng các registration bean và hiểu quy tắc đăng ký để tránh trùng lặp.

Spring MVC thường có DispatcherServlet được mapping để nhận các request tương ứng, sau đó dùng HandlerMapping và HandlerAdapter để gọi controller. Servlet Filter chạy ở tầng container, nằm ngoài vòng xử lý của HandlerInterceptor thuộc Spring MVC.

### 3.4. Luồng HTTP điển hình

~~~text
HTTP client
    |
    v
Embedded Servlet server (ví dụ Tomcat)
    |
    v
jakarta.servlet.Filter chain
    |
    v
DispatcherServlet
    |
    +--> HandlerMapping
    +--> HandlerAdapter
    +--> @Controller / @RestController
    |         |
    |         v
    |       Service -> Repository / downstream service
    |
    v
HttpMessageConverter / response
    |
    v
Servlet server -> HTTP client
~~~

Đây là luồng minh họa khi có Spring MVC. Một Servlet không phải DispatcherServlet có thể nhận request theo mapping riêng; ServletWebServerApplicationContext vẫn là context phù hợp.

### 3.5. Mô hình thực thi

Với xử lý Servlet đồng bộ phổ biến, server dùng thread để thực thi request; lệnh gọi database hoặc HTTP blocking có thể giữ thread cho đến khi hoàn tất. Servlet stack cũng có hỗ trợ async, nên không nên phát biểu rằng mọi request Servlet luôn blocking từ đầu đến cuối.

Khi vận hành MVC, cần hiểu kích thước thread pool, connection pool, timeout, queue và việc Bean singleton không được chứa mutable state riêng từng request nếu không có đồng bộ thích hợp.

## 4. ReactiveWebServerApplicationContext

### 4.1. Bản chất và vai trò

ReactiveWebServerApplicationContext là lớp thuộc package org.springframework.boot.web.reactive.context. Nó kế thừa GenericReactiveWebApplicationContext và dùng ReactiveWebServerFactory để tạo embedded WebServer phục vụ mô hình xử lý HTTP reactive.

Trong một ứng dụng cấu hình bằng annotation, implementation thường thấy là AnnotationConfigReactiveWebServerApplicationContext.

Lớp này không dùng ServletContext làm mô hình lập trình web cốt lõi. Các abstraction chính của Spring WebFlux là HttpHandler, WebHandler, WebFilter, ServerWebExchange, HandlerMapping và các thành phần xử lý kết quả reactive. Ứng dụng có thể viết annotated controller hoặc functional routing.

### 4.2. Quan hệ với ReactiveWebServerFactory

Context tìm Bean kiểu ReactiveWebServerFactory. Các implementation bao gồm:

- NettyReactiveWebServerFactory: Reactor Netty; mặc định thông thường của spring-boot-starter-webflux.
- TomcatReactiveWebServerFactory, JettyReactiveWebServerFactory, UndertowReactiveWebServerFactory: các lựa chọn reactive server tương ứng khi dependency và adapter hỗ trợ.

Điều này rất quan trọng: ReactiveWebServerApplicationContext không có nghĩa bắt buộc chạy Netty; và thấy Tomcat trong log chưa đủ để kết luận ứng dụng đang dùng Spring MVC. Context type và HTTP server implementation là hai trục lựa chọn khác nhau.

### 4.3. HttpHandler và pipeline reactive

WebFlux xây dựng HttpHandler từ hạ tầng WebHandler, WebFilter, exception handler và các adapter để kết nối ứng dụng với HTTP server. Với annotated controller, DispatcherHandler là thành phần front controller của WebFlux, khác với DispatcherServlet của MVC.

~~~text
HTTP client
    |
    v
Reactive HTTP server (ví dụ Reactor Netty)
    |
    v
HttpHandler / server adapter
    |
    v
WebFilter chain
    |
    v
DispatcherHandler (Spring WebFlux)
    |
    +--> HandlerMapping
    +--> HandlerAdapter
    +--> @RestController / RouterFunction
    |         |
    |         v
    |      Mono<T> / Flux<T> hoặc kiểu trả về phù hợp
    |
    v
HandlerResultHandler + encoder
    |
    v
Reactive HTTP response
~~~

Mono thể hiện luồng có tối đa một phần tử; Flux thể hiện luồng có thể có nhiều phần tử. WebFlux có thể xử lý kết quả bất đồng bộ và backpressure ở những đoạn pipeline có hỗ trợ. Không nên diễn giải rằng chỉ cần phương thức trả Mono là mọi I/O bên dưới tự động trở thành non-blocking.

### 4.4. Mô hình thực thi và hạn chế thực tế

Reactor Netty thường dùng các event-loop thread để xử lý kết nối và tín hiệu I/O. Lợi ích của mô hình reactive xuất hiện khi phần lớn pipeline, bao gồm truy cập dịch vụ và dữ liệu, không chặn thread.

Ví dụ, gọi Thread.sleep(), JDBC blocking hoặc một SDK HTTP đồng bộ trực tiếp trên event-loop có thể làm nhiều request khác bị ảnh hưởng. Khi phải tích hợp thư viện blocking, cần đánh giá cách cô lập công việc trên scheduler phù hợp, giới hạn concurrency và khả năng chịu tải; việc chuyển scheduler không biến API blocking thành API non-blocking.

Với Servlet MVC, HttpSession và request scope của Servlet là các khái niệm quen thuộc. WebFlux có ServerWebExchange, WebSession và các abstraction riêng. Không mang nguyên xi Servlet Filter hoặc HttpServletRequest sang reactive controller rồi kỳ vọng cùng semantics.

## 5. Spring Boot lựa chọn context như thế nào?

### 5.1. WebApplicationType

Spring Boot dùng WebApplicationType với ba giá trị:

- SERVLET: chạy dạng ứng dụng web dựa trên Servlet.
- REACTIVE: chạy dạng ứng dụng web reactive.
- NONE: ứng dụng không chạy embedded web server.

Khi khởi động, SpringApplication xác định web application type, thường bằng cách suy ra từ các class có trên classpath; sau đó dùng cơ chế tạo context phù hợp. Khả năng suy đoán này không đơn thuần dựa trên tên module hoặc việc bạn viết một controller trả Mono.

Trong Spring Boot 3.x, một số tình huống thông thường:

| Dependency / cấu hình | WebApplicationType thường chọn | Loại context thường nhận |
| --- | --- | --- |
| spring-boot-starter-web, không có WebFlux | SERVLET | AnnotationConfigServletWebServerApplicationContext |
| spring-boot-starter-webflux, không có MVC | REACTIVE | AnnotationConfigReactiveWebServerApplicationContext |
| Có cả Spring MVC và WebFlux | SERVLET theo mặc định | Servlet context |
| Không có web infrastructure tương ứng | NONE | AnnotationConfigApplicationContext |
| Cấu hình spring.main.web-application-type=reactive và đủ hạ tầng reactive | REACTIVE | Reactive context |
| Cấu hình spring.main.web-application-type=none | NONE | Không tạo embedded web server |

Nếu vừa có Spring MVC vừa có WebFlux, Spring MVC được ưu tiên theo quy tắc mặc định của Boot 3.x. Đây là lý do một ứng dụng MVC vẫn có thể sử dụng WebClient mà context của nó vẫn là Servlet context.

### 5.2. Cấu hình lựa chọn tường minh

Ví dụ application.properties:

~~~properties
spring.main.web-application-type=reactive
server.port=8081
~~~

Cấu hình này yêu cầu ứng dụng chọn REACTIVE. Tuy nhiên vẫn cần dependency, controller/filter và web server factory tương thích. Ép loại web application không tự chuyển một dự án Servlet MVC thành kiến trúc WebFlux hoàn chỉnh.

Tắt embedded web server:

~~~properties
spring.main.web-application-type=none
~~~

Trường hợp NONE phù hợp cho CLI, batch job, một số worker hoặc ứng dụng không nhận HTTP. Một ứng dụng có starter web nhưng cố ý đặt NONE sẽ không tạo server HTTP nhúng ở main context.

Có thể chọn kiểu programmatically bằng WebApplicationType khi cấu hình SpringApplication. Chỉ dùng khi thực sự có yêu cầu; với ứng dụng thông thường, quản lý dependency và cấu hình rõ ràng sẽ dễ duy trì hơn.

### 5.3. Auto-configuration phản ứng với lựa chọn này

Auto-configuration thường xét loại web application, classpath, sự tồn tại của Bean và property.

Ở Servlet stack, thường gặp:

- ServletWebServerFactoryAutoConfiguration
- DispatcherServletAutoConfiguration
- WebMvcAutoConfiguration

Ở Reactive stack, thường gặp:

- ReactiveWebServerFactoryAutoConfiguration
- HttpHandlerAutoConfiguration
- WebFluxAutoConfiguration

Các cấu hình này không được kích hoạt chỉ vì có tên class trong repository; phải thỏa các điều kiện thực tế. Dùng condition evaluation report khi cần xác định chính xác vì sao auto-configuration có hiệu lực hoặc bị loại.

## 6. So sánh trực tiếp hai context

| Tiêu chí | ServletWebServerApplicationContext | ReactiveWebServerApplicationContext |
| --- | --- | --- |
| WebApplicationType | SERVLET | REACTIVE |
| Lớp cha | GenericWebApplicationContext | GenericReactiveWebApplicationContext |
| Hợp đồng chung | ConfigurableWebServerApplicationContext | ConfigurableWebServerApplicationContext |
| Web server factory | ServletWebServerFactory | ReactiveWebServerFactory |
| Starter tiêu biểu | spring-boot-starter-web | spring-boot-starter-webflux |
| Server mặc định phổ biến | Tomcat | Reactor Netty |
| Server có thể thay | Jetty, Undertow | Tomcat, Jetty, Undertow tùy dependency |
| HTTP entry point | Servlet / DispatcherServlet (nếu MVC) | HttpHandler / DispatcherHandler (nếu WebFlux) |
| Filter chính | jakarta.servlet.Filter | org.springframework.web.server.WebFilter |
| Đối tượng request thường gặp | HttpServletRequest, HttpServletResponse | ServerWebExchange, ServerHttpRequest, ServerHttpResponse |
| Kiểu trả về thường gặp | Object, ResponseEntity, CompletableFuture, MVC async types | Mono, Flux, Object, ResponseEntity, reactive wrapper |
| Security chain thường gặp | SecurityFilterChain | SecurityWebFilterChain |
| Mô hình request điển hình | Servlet thread model và async nếu dùng | Reactive I/O với event loop khi dùng Netty |
| Session abstraction | HttpSession | WebSession |

Một số API có tên giống nhau ở hai stack nhưng hoạt động khác nhau. Ví dụ @RestController và @GetMapping dùng được ở cả MVC lẫn WebFlux; annotation không cho bạn biết chắc app đang chạy theo stack nào.

Khác biệt quan trọng nhất không chỉ là hiệu năng. Nó nằm ở hợp đồng lập trình: request abstraction, filter/security, error handling, dữ liệu đồng thời, kiểu I/O và cách tích hợp thư viện.

## 7. Lifecycle của embedded web server

### 7.1. Khởi động

Quy trình ở mức khái niệm:

1. JVM gọi main và SpringApplication.run(...).
2. SpringApplication chuẩn bị Environment, property và active profile.
3. SpringApplication tạo ApplicationContext phù hợp với WebApplicationType.
4. Context nhận Bean definitions và refresh.
5. Auto-configuration cung cấp ServletWebServerFactory hoặc ReactiveWebServerFactory khi thỏa điều kiện.
6. Context tạo embedded WebServer; phần Servlet đăng ký Servlet/Filter, phần Reactive thiết lập HttpHandler.
7. Spring thực thi các bước lifecycle để server khởi động và nhận kết nối.
8. Spring Boot phát WebServerInitializedEvent chuyên biệt cho stack khi server đã được khởi tạo.
9. Các runner hoàn tất và ứng dụng đi đến ApplicationReadyEvent.

Đây là sơ đồ nghiệp vụ, không phải cam kết rằng tất cả bước nội bộ đều xảy ra tại một callback duy nhất. Trong Boot 3.x, việc tạo server gắn với refresh context, còn việc start/stop server có sự tham gia của lifecycle infrastructure.

Không đánh đồng web server initialized với toàn bộ ứng dụng đã ready. Event server initialized giúp lấy cổng thực tế của web server; ApplicationReadyEvent báo quá trình startup của SpringApplication đã đi đến mốc sẵn sàng.

### 7.2. Event cần biết

- ServletWebServerInitializedEvent: sự kiện cho Servlet web server, thuộc package org.springframework.boot.web.servlet.context.
- ReactiveWebServerInitializedEvent: sự kiện cho Reactive web server, thuộc package org.springframework.boot.web.reactive.context.
- WebServerInitializedEvent: lớp sự kiện chung, chứa WebServer vừa được khởi tạo.
- ApplicationReadyEvent: ứng dụng hoàn thành startup theo lifecycle của SpringApplication.

Khi chạy với server.port=0, hệ điều hành cấp một port khả dụng. Lấy port từ event hoặc WebServer thực tế sau khi server khởi tạo, không mặc định rằng giá trị cấu hình 0 chính là port đang listen.

### 7.3. Đóng ứng dụng

Đóng ApplicationContext kéo theo lifecycle stop của web server và các Bean/resource liên quan. Graceful shutdown có thể giúp các request đang chạy hoàn tất trong khoảng thời gian cấu hình trước khi dừng hẳn.

Khác biệt của Servlet/Reactive còn ảnh hưởng cách dừng request đang chờ, subscription, connection và executor. Việc tạo thread hoặc event loop riêng mà không có shutdown hook phù hợp có thể giữ tiến trình không thoát dù context đã đóng.

## 8. Thực hành A: tạo Servlet application và xác minh context

Tạo một project Spring Boot 3.x (Java 17+) bằng Spring Initializr, chỉ chọn dependency Spring Web (spring-boot-starter-web). Đặt main class dưới package com.example.servletdemo. Nếu dùng Gradle, dependency cốt lõi thường là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Phần trên là đoạn dependencies của build.gradle, không phải build file đầy đủ; plugin và phiên bản Spring Boot do project tạo từ Initializr quản lý.

Tạo file src/main/java/com/example/servletdemo/ServletDemoApplication.java:

~~~java
package com.example.servletdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ServletDemoApplication {

    public static void main(String[] args) {
        var context = SpringApplication.run(ServletDemoApplication.class, args);
        System.out.println(
                "SERVLET_CONTEXT=" +
                (context instanceof ServletWebServerApplicationContext));
    }
}

@RestController
class PingServletController {

    @GetMapping(value = "/ping", produces = "text/plain")
    public String ping() {
        return "pong";
    }
}
~~~

Chạy từ thư mục project Gradle:

~~~shell
./gradlew bootRun
~~~

Trên Windows dùng gradlew.bat bootRun. Sau các dòng log khởi động, console phải có dòng:

~~~text
SERVLET_CONTEXT=true
~~~

Tên lớp concrete thường là AnnotationConfigServletWebServerApplicationContext. Log startup có thể hiển thị Tomcat và cổng 8080 theo cấu hình mặc định, nhưng log cụ thể phụ thuộc phiên bản và môi trường.

Trong terminal khác:

~~~shell
curl -i http://localhost:8080/ping
~~~

Kỳ vọng: HTTP 200, Content-Type dạng text/plain và body chính xác là pong. Curl có thể hiển thị thêm các header khác tùy server; chỉ nên khẳng định phần status/body và loại content type cốt lõi.

Vì sao kết quả là Servlet context? Starter Web đưa Spring MVC và Servlet web infrastructure lên classpath; Spring Boot nhận diện WebApplicationType.SERVLET, tạo context Servlet và dùng ServletWebServerFactory phù hợp.

## 9. Thực hành B: tạo Reactive application và xác minh context

Tạo project Spring Boot riêng, Java 17+, chỉ chọn Spring Reactive Web (spring-boot-starter-webflux). Không đặt Spring Web (MVC) vào classpath của bài thực hành này.

Đoạn Gradle dependency tiêu biểu:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Tạo file src/main/java/com/example/reactivedemo/ReactiveDemoApplication.java:

~~~java
package com.example.reactivedemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class ReactiveDemoApplication {

    public static void main(String[] args) {
        var context = SpringApplication.run(ReactiveDemoApplication.class, args);
        System.out.println(
                "REACTIVE_CONTEXT=" +
                (context instanceof ReactiveWebServerApplicationContext));
    }
}

@RestController
class PingReactiveController {

    @GetMapping(value = "/ping", produces = "text/plain")
    public Mono<String> ping() {
        return Mono.just("pong");
    }
}
~~~

Chạy:

~~~shell
./gradlew bootRun
~~~

Sau log startup, console phải có dòng:

~~~text
REACTIVE_CONTEXT=true
~~~

Với starter-webflux mặc định, log thường cho thấy Reactor Netty. Gửi request:

~~~shell
curl -i http://localhost:8080/ping
~~~

Kết quả mong đợi: HTTP 200, Content-Type text/plain và body pong. Điểm khác nằm ở context, HTTP server adapter và xử lý Mono trong pipeline WebFlux.

Không chạy đồng thời cả hai bài thực hành trên cùng cổng 8080; dừng một ứng dụng trước khi chạy ứng dụng kia, hoặc đặt server.port khác nhau. Nếu muốn dùng port riêng cho reactive demo, có thể thêm trong application.properties:

~~~properties
server.port=8081
~~~

Khi đó gọi http://localhost:8081/ping.

### Đối chiếu kết quả

Hai controller có thể trả cùng response, nhưng cùng output không chứng minh cùng runtime. Việc kiểm tra instanceof ngay sau SpringApplication.run và xem dependency là bằng chứng trực tiếp hơn.

Nếu dòng REACTIVE_CONTEXT=false, cần kiểm tra classpath có kéo theo Spring MVC hay không, hoặc cấu hình web application type có bị thay đổi không. Không sửa bằng cách ép cast context sang ReactiveWebServerApplicationContext; cast sai chỉ làm phát sinh ClassCastException.

## 10. Quan sát server và port bằng API chung

Để đọc thông tin server, dùng hợp đồng WebServerApplicationContext khi ứng dụng chạy dạng web:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.context.WebServerApplicationContext;

@SpringBootApplication
public class ContextInspectorApplication {

    public static void main(String[] args) {
        var context = SpringApplication.run(ContextInspectorApplication.class, args);

        System.out.println("CONTEXT_TYPE=" + context.getClass().getSimpleName());
        if (context instanceof WebServerApplicationContext webContext) {
            var server = webContext.getWebServer();
            if (server != null) {
                System.out.println("ACTUAL_PORT=" + server.getPort());
            }
        }
    }
}
~~~

Đây là một ví dụ thay thế main class trong một project đã có Spring Web hoặc Spring Reactive Web và web server phù hợp; không tạo thêm main class để khởi chạy cùng lúc. Đoạn ví dụ dùng cú pháp pattern matching for instanceof của Java 17.

CONTEXT_TYPE phụ thuộc stack và implementation cụ thể; ACTUAL_PORT phụ thuộc cấu hình, có thể được cấp động nếu server.port=0. Vì vậy không đưa ra một stdout số port cố định.

Lưu ý: getWebServer() được thiết kế để trả null nếu server chưa được tạo. Nếu cần quan sát chính thời điểm khởi tạo, nên lắng nghe WebServerInitializedEvent thay vì truy cập server quá sớm.

Ví dụ listener chung dùng được trong cả hai loại ứng dụng:

~~~java
package com.example.demo;

import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class WebServerPortListener {

    @EventListener
    public void onWebServerInitialized(WebServerInitializedEvent event) {
        System.out.println("WEB_SERVER_PORT=" + event.getWebServer().getPort());
    }
}
~~~

Đặt file ở package được component scan quét. Nếu ứng dụng có thêm management web context trên cổng riêng, có thể có nhiều web-server event; cần xem context/namespace của event trước khi gán một cổng cho main application.

## 11. Chẩn đoán lỗi chọn sai web stack

### Tình huống A: mong đợi Reactive nhưng lại thấy Servlet context

Dấu hiệu: in ra AnnotationConfigServletWebServerApplicationContext hoặc REACTIVE_CONTEXT=false.

Các bước:

1. Kiểm tra dependency runtime xem có spring-boot-starter-web / spring-webmvc không.
2. Nếu cả MVC và WebFlux cùng tồn tại, nhớ rằng Boot 3.x mặc định ưu tiên MVC.
3. Nếu mục tiêu là WebFlux thuần, bỏ dependency MVC không cần thiết và dùng spring-boot-starter-webflux.
4. Nếu cố ý giữ cả hai stack, cấu hình spring.main.web-application-type=reactive và kiểm tra lại điều kiện auto-configuration.
5. Xác minh Bean, controller, filter và thư viện I/O đều tương thích với WebFlux.

Không coi sự xuất hiện của WebClient hay Mono trong source code là bằng chứng ứng dụng đã dùng ReactiveWebServerApplicationContext.

### Tình huống B: No ServletWebServerFactory bean

Dấu hiệu: startup thất bại khi Servlet context không tìm thấy ServletWebServerFactory phù hợp.

Hướng kiểm tra: dependency servlet container có bị loại khỏi starter không, app có bị ép SERVLET khi chỉ có reactive infrastructure không, auto-configuration có bị exclude không, có Bean factory tùy chỉnh gây xung đột không.

Không tạo thủ công một factory mới chỉ để che nguyên nhân mà chưa hiểu dependency và deployment mode của ứng dụng.

### Tình huống C: No ReactiveWebServerFactory bean

Dấu hiệu: Reactive context không tìm được ReactiveWebServerFactory.

Hướng kiểm tra: reactive server dependency (thường spring-boot-starter-reactor-netty), dependency exclusions, active configuration và điều kiện auto-configuration. Nếu đã thay server bằng Tomcat hoặc Jetty reactive, xác minh dependency thực sự cung cấp factory reactive tương ứng.

Chỉ có spring-webflux hoặc Mono trên classpath không đảm bảo web server factory cần thiết đã sẵn sàng.

### Tình huống D: controller trả 404

Hướng kiểm tra:

- Component scan có bao trùm package controller không?
- Request path và method có khớp @GetMapping/@PostMapping không?
- Có cấu hình context path hoặc base path làm thay đổi URL không?
- Ứng dụng đang chạy MVC hay WebFlux và controller có thuộc đúng pipeline được khởi tạo không?
- Có Filter, WebFilter hoặc security cấu hình chặn request không?

404 không đủ để kết luận sai ApplicationContext; luôn xem class runtime và log mapping.

### Tình huống E: 401/403 sau khi đổi stack

Spring Security cho MVC sử dụng servlet SecurityFilterChain và các Filter; reactive security sử dụng SecurityWebFilterChain và WebFilter. Khi đổi từ Servlet sang Reactive, không tự động mang nguyên cấu hình bảo mật Servlet sang và kỳ vọng chạy.

Cần viết cấu hình security theo stack đã chọn, kiểm tra authentication/authorization và test trực tiếp các endpoint được bảo vệ.

### Tình huống F: startup thành công nhưng xử lý chậm

Servlet MVC: kiểm tra thread pool, connection pool, timeout, truy vấn chậm và request blocking.

Reactive WebFlux: kiểm tra có thao tác blocking trên event-loop không, scheduler, downstream client, database driver và giới hạn concurrency. Đổi starter sang WebFlux không tự động cải thiện hiệu năng nếu các dependency vẫn blocking.

### Tình huống G: lỗi ClassCastException khi ép kiểu context

Sai lầm:

~~~java
// Chỉ minh họa lỗi khi ứng dụng thật sự dùng Reactive context:
ServletWebServerApplicationContext servletContext =
        (ServletWebServerApplicationContext) context;
~~~

Cast này sẽ thất bại nếu context runtime thuộc ReactiveWebServerApplicationContext. Giải pháp đúng là xác định WebApplicationType từ dependency/cấu hình; dùng interface chung khi chỉ cần đọc server, hoặc kiểm tra instanceof trước các thao tác phụ thuộc stack.

## 12. Test phân biệt context

Trong mỗi project, có thể tạo integration test với @SpringBootTest(webEnvironment = RANDOM_PORT) để bảo đảm ApplicationContext và web server được tạo đầy đủ. Với JUnit 5:

Servlet project:

~~~java
package com.example.servletdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ServletContextTest {

    @Autowired
    ApplicationContext context;

    @Test
    void shouldUseServletContext() {
        assertInstanceOf(ServletWebServerApplicationContext.class, context);
    }
}
~~~

Reactive project:

~~~java
package com.example.reactivedemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveContextTest {

    @Autowired
    ApplicationContext context;

    @Test
    void shouldUseReactiveContext() {
        assertInstanceOf(ReactiveWebServerApplicationContext.class, context);
    }
}
~~~

Mỗi đoạn test là file riêng trong project tương ứng; không ghép cả hai lớp kiểm tra vào cùng một project. Chạy ./gradlew test với test runtime được cấu hình từ Spring Boot starter test.

Test kiểu context xác minh quyết định bootstrap. Nó không thay thế test HTTP endpoint, Filter/WebFilter, validation, bảo mật hay tích hợp downstream.

## 13. Những quyết định thiết kế cần cân nhắc

### Khi nào ưu tiên Servlet stack?

Thường phù hợp khi:

- Ứng dụng dùng nhiều thư viện blocking như JDBC, một số HTTP SDK hoặc các API đồng bộ.
- Nhóm đã có hệ thống Spring MVC và Servlet Filter/Security.
- Nhu cầu chính là REST API đồng bộ với mô hình lập trình imperative dễ theo dõi.
- Hệ sinh thái middleware hiện có yêu cầu Servlet API.

Servlet stack có hỗ trợ xử lý bất đồng bộ; lựa chọn này không mặc nhiên là thiếu khả năng mở rộng.

### Khi nào ưu tiên Reactive stack?

Thường phù hợp khi:

- Luồng I/O sử dụng API reactive thực sự, ví dụ reactive client và R2DBC khi cần.
- Có nhiều request I/O-bound, kết nối dài hoặc luồng dữ liệu cần quản lý backpressure.
- Nhóm kiểm soát được thao tác blocking và hiểu semantics Reactor, WebFlux, scheduler.
- Hạ tầng observability, security, test và thư viện tích hợp tương thích reactive.

Reactive không tự động nhanh hơn trong mọi bài toán; với xử lý CPU-bound hoặc tích hợp blocking, độ phức tạp có thể tăng mà lợi ích không tương xứng.

### Không quyết định dựa trên tên server

Một web server như Tomcat có thể là engine của Servlet stack hoặc tham gia làm reactive server khi được cấu hình tương ứng. Chọn web stack bằng hợp đồng ứng dụng, loại context, I/O model và hệ sinh thái dependency; sau đó mới chọn server implementation phù hợp.

## 14. Checklist thực hành

Trước khi khẳng định ứng dụng dùng Servlet hay Reactive, kiểm tra:

- [ ] Dependency runtime có Spring MVC hay WebFlux?
- [ ] Có cả hai stack không? Nếu có, Boot chọn loại nào và có override tường minh không?
- [ ] Giá trị spring.main.web-application-type có được cấu hình không?
- [ ] ApplicationContext thực tế có phải ServletWebServerApplicationContext hoặc ReactiveWebServerApplicationContext?
- [ ] Factory tương ứng được đăng ký đúng một cách nhất quán?
- [ ] Pipeline request dùng DispatcherServlet hay DispatcherHandler?
- [ ] Filter và security chain thuộc đúng stack?
- [ ] Thư viện truy cập dữ liệu và HTTP client có đúng mô hình blocking/non-blocking mong muốn?
- [ ] Embedded server đã bind đúng port? Có thể lấy port từ WebServerInitializedEvent?
- [ ] Đã có test cho context type, HTTP response, lỗi và shutdown/health khi cần?

## 15. Câu hỏi tự kiểm tra

1. WebServerApplicationContext cung cấp những khả năng nào thêm so với ApplicationContext?
2. ServletWebServerApplicationContext kế thừa lớp nào? ReactiveWebServerApplicationContext kế thừa lớp nào?
3. Mỗi context cần loại WebServerFactory nào?
4. Vì sao project có cả spring-boot-starter-web và spring-boot-starter-webflux thường khởi động ở Servlet stack?
5. DispatcherServlet và DispatcherHandler khác nhau ở đâu?
6. Filter của Servlet và WebFilter của WebFlux dùng trong pipeline nào?
7. ReactiveWebServerApplicationContext có bắt buộc dùng Reactor Netty không?
8. Trong lifecycle, khi nào nên dùng WebServerInitializedEvent và khi nào dùng ApplicationReadyEvent?
9. Vì sao controller trả Mono không đủ để chứng minh ứng dụng dùng reactive context?
10. Khi startup báo thiếu ReactiveWebServerFactory, cần kiểm tra những cấu hình và dependency nào?
11. Vì sao chuyển sang WebFlux nhưng vẫn dùng blocking JDBC có thể gây vấn đề?
12. Làm sao viết integration test xác nhận context type mà không dựa vào câu chữ của log?

## 16. Tài liệu đối chiếu

- [Spring Boot 3.3 API — ServletWebServerApplicationContext](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/servlet/context/ServletWebServerApplicationContext.html)
- [Spring Boot 3.3 API — ReactiveWebServerApplicationContext](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/reactive/context/ReactiveWebServerApplicationContext.html)
- [Spring Boot 3.3 API — WebServerApplicationContext](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/context/WebServerApplicationContext.html)
- [Spring Boot 3.3 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html)

Mấu chốt cần nắm: hai context đều quản lý embedded web server trong Spring Boot, nhưng ServletWebServerApplicationContext gắn với Servlet API và ServletWebServerFactory, còn ReactiveWebServerApplicationContext gắn với reactive HTTP pipeline và ReactiveWebServerFactory. Lựa chọn được quyết định khi bootstrap theo WebApplicationType và điều kiện auto-configuration; hãy kiểm tra chính context thực tế để biết ứng dụng đang vận hành theo stack nào.

# Quan hệ giữa Web ApplicationContext, WebServerFactory và máy chủ nhúng trong Spring Boot

## 1. Ba thành phần đóng vai trò khác nhau

Khi chạy một ứng dụng Spring Boot web dưới dạng JAR, framework không chỉ tạo các controller và trả về một Spring ApplicationContext thông thường. Nó còn cần một thành phần quản lý **máy chủ HTTP nhúng** (embedded web server) để ứng dụng tự phục vụ request mà không phải triển khai WAR vào một ứng dụng máy chủ riêng.

Ba khái niệm cốt lõi:

1. **Web ApplicationContext (web context)** là **Spring IoC container có khả năng quản lý vòng đời web server**. Nó đăng ký, tạo và quản lý bean (controller, service, filter, configuration...), khởi tạo tích hợp web và phối hợp lúc server được tạo, start, stop.
2. **WebServerFactory** là **factory tạo server**. Nó lưu/cấu hình các tùy chọn như port, SSL, compression, connector, context path tùy stack; khi web context yêu cầu, nó tạo một đối tượng **WebServer**. Factory thường là **một Spring bean** được Spring Boot auto-configuration cung cấp.
3. **WebServer** là **đối tượng đại diện cho server đã được tạo** (ví dụ **TomcatWebServer** hoặc **NettyWebServer**), có các phương thức **start()**, **stop()**, **getPort()**. Phía sau abstraction này là Tomcat, Jetty, Undertow hoặc Reactor Netty nhận và xử lý kết nối HTTP.

**Quan hệ trách nhiệm:** web context là bên quản lý vòng đời, factory là bên biết cách tạo/cấu hình server, còn server là thành phần thực sự nhận kết nối mạng. **Factory không phải chính server**; Spring ApplicationContext cũng không phải HTTP server.

~~~text
SpringApplication
    |
    | Xác định WebApplicationType và tạo context
    v
Web ApplicationContext (Spring IoC container)
    |                         |
    | quản lý bean            | tìm một WebServerFactory bean
    |                         v
    |                  WebServerFactory
    |                  (được cấu hình bằng server.*,
    |                   customizers, dependencies)
    |                         |
    |                         | getWebServer(...)
    |                         v
    |                      WebServer
    |                  (Tomcat / Jetty /
    |                   Undertow / Netty)
    |                         |
    | start, stop              | lắng nghe HTTP
    +-------------------------+----------------> client
~~~

Đây là mô hình **ứng dụng có embedded server**. Khi triển khai WAR vào servlet container bên ngoài, container có thể do môi trường triển khai quản lý; không áp nguyên sơ đồ “web context tự tạo embedded server” cho mọi kiểu triển khai WAR.

## 2. Hai nhánh web context tương ứng với hai web stack

Trong Spring Boot 3.3, loại ứng dụng web dẫn đến **hai họ context và factory khác nhau**.

| Tiêu chí | Servlet stack (Spring MVC) | Reactive stack (Spring WebFlux) |
| --- | --- | --- |
| Loại ứng dụng | **WebApplicationType.SERVLET** | **WebApplicationType.REACTIVE** |
| Web context thường gặp | **AnnotationConfigServletWebServerApplicationContext**, kế thừa **ServletWebServerApplicationContext** | **AnnotationConfigReactiveWebServerApplicationContext**, kế thừa **ReactiveWebServerApplicationContext** |
| Factory interface | **ServletWebServerFactory** | **ReactiveWebServerFactory** |
| Đầu vào hàm tạo server | **getWebServer(ServletContextInitializer... initializers)** | **getWebServer(HttpHandler httpHandler)** |
| Thành phần xử lý HTTP | Servlet container, **Filter**, **DispatcherServlet**, Spring MVC handler | **HttpHandler** và WebFlux handler chain |
| Server nhúng mặc định với starter phổ biến | **Tomcat**, qua **spring-boot-starter-web** | **Reactor Netty**, qua **spring-boot-starter-webflux** |
| Server khác có thể chọn (Boot 3.3) | Jetty, Undertow | Tomcat, Jetty, Undertow |

**Các tên lớp thực tế phụ thuộc phiên bản**, còn mô hình hai nhánh là khái niệm chính. Cả hai loại context đều triển khai giao diện **WebServerApplicationContext**, nhờ đó có thể lấy đối tượng server bằng **getWebServer()**.

### 2.1. Servlet web context

Lớp **ServletWebServerApplicationContext** tìm **một bean ServletWebServerFactory duy nhất** trong context, thường do auto-configuration cung cấp. Factory chọn cách tạo container nhúng; context chuẩn bị các **ServletContextInitializer** phục vụ đăng ký Servlet, Filter và listener.

Với Spring MVC, luồng request có thể hình dung:

~~~text
Client HTTP
   |
   v
Embedded Tomcat / Jetty / Undertow
   |
   v
Servlet Filter chain
   |
   v
DispatcherServlet
   |
   v
HandlerMapping -> Controller -> Service
   |
   v
HTTP response
~~~

**DispatcherServlet** là front controller của Spring MVC, **không phải web server**. Nếu thiếu Tomcat/Jetty/Undertow hoặc không có một servlet container tương ứng, DispatcherServlet không tự mở socket hay lắng nghe port. Ngược lại, một Tomcat nhúng có thể chạy nhưng nếu không đăng ký endpoint/servlet phù hợp thì không tự xuất hiện các route MVC mong muốn.

Ví dụ factory cụ thể:

- **TomcatServletWebServerFactory** tạo **TomcatWebServer**.
- **JettyServletWebServerFactory** tạo server dựa trên Jetty.
- **UndertowServletWebServerFactory** tạo server dựa trên Undertow.

Các **ServletContextInitializer** giúp cấu hình servlet context trước khi ứng dụng phục vụ request; Spring Boot cũng tự thích nghi các bean Servlet, Filter và một số EventListener để đăng ký vào server.

### 2.2. Reactive web context

**ReactiveWebServerApplicationContext** làm vai trò tương đương nhưng tìm **ReactiveWebServerFactory**. Thay vì nhận ServletContextInitializer như nhánh MVC, factory reactive nhận một **org.springframework.http.server.reactive.HttpHandler** làm điểm vào xử lý HTTP.

~~~text
Client HTTP
   |
   v
Reactor Netty / Tomcat / Jetty / Undertow
   |
   v
Server adapter
   |
   v
HttpHandler
   |
   v
WebFlux chain (WebFilter, WebHandler)
   |
   v
Annotated controller / functional router
   |
   v
Reactive response
~~~

**HttpHandler** là hợp đồng kết nối server HTTP với cơ chế xử lý request của Spring WebFlux. Ở các container servlet chạy WebFlux, adapter thích hợp chuyển servlet request vào pipeline reactive. **WebFlux không đồng nghĩa bắt buộc phải dùng Netty**; Netty chỉ là lựa chọn mặc định của starter WebFlux trong Spring Boot 3.3.

Ví dụ factory:

- **NettyReactiveWebServerFactory** tạo **NettyWebServer**.
- **TomcatReactiveWebServerFactory**, **JettyReactiveWebServerFactory** và **UndertowReactiveWebServerFactory** cho phép reactive stack sử dụng các server khác nếu cấu hình dependency phù hợp.

Tuy hai nhánh sử dụng các factory khác nhau, chúng đều cung cấp **WebServer** và được web context quản lý vòng đời.

## 3. Ai tạo web context và ai đăng ký WebServerFactory?

Trong trường hợp thông thường, lập trình viên chỉ khai báo một ứng dụng và chọn starter:

~~~java
@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

**SpringApplication** xác định **WebApplicationType** bằng cách xét classpath, trừ khi có thiết lập rõ ràng bằng **spring.main.web-application-type** hoặc API tương ứng. Theo đó, nó chọn một ApplicationContext phù hợp.

**Auto-configuration** tiếp tục cung cấp factory bean khi các điều kiện tương ứng đúng:

- Với Servlet: **ServletWebServerFactoryAutoConfiguration** và các cấu hình cho Tomcat/Jetty/Undertow có thể tạo **ServletWebServerFactory**.
- Với Reactive: **ReactiveWebServerFactoryAutoConfiguration** có thể tạo **ReactiveWebServerFactory** phù hợp.
- Các cấu hình server thông dụng từ **server.port**, **server.address**, **server.ssl.***, **server.compression.*** và cấu hình riêng của Tomcat/Jetty/Netty được áp dụng vào factory thông qua cơ chế cấu hình, customizer.

Thông thường, Boot **không cần bạn tự viết @Bean WebServerFactory**. Việc thay đổi dependency sẽ ảnh hưởng loại factory được đăng ký. Ví dụ **spring-boot-starter-web** mang Tomcat theo mặc định; muốn dùng Jetty phải thay starter Tomcat bằng starter Jetty và kiểm tra lại dependency graph.

Khi có cả Spring MVC và WebFlux trên classpath, **Spring MVC thường được ưu tiên** trong bước tự suy đoán loại ứng dụng. Việc chỉ thêm **spring-boot-starter-webflux** để dùng **WebClient** không có nghĩa ứng dụng đang vận hành trên reactive web context hoặc server Netty.

**Điểm phân biệt:** chọn Servlet/Reactive xác định cách xử lý request và context; chọn Tomcat/Jetty/Undertow/Netty xác định server được factory dựng. Hai quyết định liên quan nhau nhưng là các tầng trách nhiệm khác nhau.

## 4. Khi nào factory tạo server, khi nào server thực sự chạy?

Dưới đây là trình tự khái quát cho ứng dụng nhúng khởi động thành công (Spring Boot 3.3, listener mặc định xử lý đồng bộ):

1. **SpringApplication chuẩn bị Environment** từ các nguồn cấu hình và xác định Servlet, Reactive hoặc None.
2. **SpringApplication tạo ApplicationContext** thích hợp và đăng ký các nguồn cấu hình/bean definition.
3. **Auto-configuration đăng ký WebServerFactory bean**. Các **WebServerFactoryCustomizer** cấu hình factory trước khi server được tạo.
4. Trong giai đoạn **ApplicationContext.refresh()**, web context tìm factory và gọi **getWebServer(...)**. Factory tạo WebServer với các thông số đã cấu hình.
5. Khi context hoàn tất refresh, cơ chế lifecycle của Boot gọi **WebServer.start()**. Server bắt đầu phục vụ HTTP; sự kiện **WebServerInitializedEvent** (hoặc biến thể Servlet/Reactive) được phát khi server sẵn sàng.
6. Sau refresh, Boot phát **ApplicationStartedEvent**, chạy **ApplicationRunner/CommandLineRunner**, rồi **ApplicationReadyEvent** và trạng thái readiness khi phù hợp.
7. **SpringApplication.run(...) trả về ConfigurableApplicationContext**. Tiến trình web thường tiếp tục hoạt động và phục vụ request sau khi hàm run đã trả về.
8. Khi **ApplicationContext đóng**, cơ chế vòng đời đóng server và các tài nguyên liên quan.

~~~text
Environment + WebApplicationType
            |
            v
Tạo Web ApplicationContext
            |
            v
Đăng ký factory bean và tùy chỉnh factory
            |
            v
ApplicationContext.refresh()
       |
       +--> context gọi factory.getWebServer(...)
       |            |
       |            +--> tạo WebServer (chưa phục vụ HTTP)
       |
       +--> hoàn tất refresh
                    |
                    v
               WebServer.start()
                    |
                    v
          WebServerInitializedEvent
                    |
                    v
          ApplicationStartedEvent
                    |
                    v
          ApplicationRunner / CommandLineRunner
                    |
                    v
          ApplicationReadyEvent
                    |
                    v
          SpringApplication.run(...) trả về
~~~

**Lưu ý kỹ thuật:** chi tiết thứ tự *khởi tạo nội bộ* của từng container có thể khác nhau, nhưng hợp đồng **ServletWebServerFactory.getWebServer(...)** và **ReactiveWebServerFactory.getWebServer(...)** trong Boot 3.3 mô tả một **WebServer đã được cấu hình và tạm dừng**; client chưa nên kết nối được cho đến khi **start()**. Có thể phân biệt việc khởi tạo đối tượng/cấu hình network với việc thật sự phục vụ HTTP.

**WebServerInitializedEvent không đồng nghĩa ApplicationReadyEvent.** Server có thể đã mở port trong khi một **ApplicationRunner** đồng bộ vẫn đang chạy. Trong môi trường vận hành, cần kết hợp readiness probe/thông tin health phù hợp; riêng tín hiệu “đã bind port” chưa chứng minh toàn bộ ứng dụng đã sẵn sàng nhận traffic nghiệp vụ.

## 5. Ví dụ Java 17+ chạy được: quan sát context, factory và server thật

Ví dụ dùng một dự án **Spring Boot 3.3.x** với **spring-boot-starter-web** (mặc định embedded Tomcat). Đặt tệp **src/main/java/com/example/runtime/ServerRelationshipApplication.java**:

~~~java
package com.example.runtime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.boot.web.server.WebServer;
import org.springframework.boot.web.servlet.server.ServletWebServerFactory;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ServerRelationshipApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(ServerRelationshipApplication.class, args);

        if (context instanceof WebServerApplicationContext webContext) {
            WebServer server = webContext.getWebServer();
            ServletWebServerFactory factory =
                    context.getBean(ServletWebServerFactory.class);

            System.out.println(
                    "MAIN | context=" + context.getClass().getSimpleName());
            System.out.println(
                    "MAIN | factory=" + factory.getClass().getSimpleName());
            System.out.println(
                    "MAIN | server=" + server.getClass().getSimpleName());
            System.out.println(
                    "MAIN | port=" + server.getPort());
        }
    }

    @Bean
    ApplicationListener<WebServerInitializedEvent> serverListener() {
        return event -> {
            // Bỏ qua management context nếu ứng dụng có server riêng.
            if (event.getApplicationContext().getServerNamespace() == null) {
                System.out.println(
                        "EVENT | server port=" + event.getWebServer().getPort());
            }
        };
    }

    @RestController
    static class GreetingController {
        @GetMapping("/hello")
        public String hello() {
            return "Hello from embedded server";
        }
    }
}
~~~

**Cấu hình** tại **src/main/resources/application.properties**:

~~~properties
server.port=0
spring.main.banner-mode=off
~~~

Lệnh chạy từ thư mục dự án có Gradle Wrapper và plugin Spring Boot:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

**Ý nghĩa kết quả kỳ vọng** (các số port chỉ là ví dụ vì **server.port=0** chọn port còn trống):

~~~text
EVENT | server port=51742
MAIN | context=AnnotationConfigServletWebServerApplicationContext
MAIN | factory=TomcatServletWebServerFactory
MAIN | server=TomcatWebServer
MAIN | port=51742
~~~

Log thông thường của Spring Boot/Tomcat có thể xen giữa các dòng này, và **port thực tế khác nhau ở mỗi lần chạy**. Điều đáng kiểm tra là:

- **EVENT** xuất hiện trước các dòng **MAIN** vì sự kiện được phát trong quá trình hoàn tất refresh, còn main chỉ tiếp tục sau **SpringApplication.run(...)**.
- Factory có kiểu triển khai **TomcatServletWebServerFactory**; đối tượng được factory tạo ra là **TomcatWebServer**; đó là **hai đối tượng với trách nhiệm khác nhau**.
- Số port từ event và số port đọc qua **webContext.getWebServer().getPort()** khớp nhau ở cùng một lần khởi động.
- ApplicationContext vẫn active sau khi phương thức run trả về, cho nên web server tiếp tục nhận request.

Để gọi endpoint, thay **51742** bằng port thật trong log:

~~~bash
curl http://localhost:51742/hello
~~~

Phần thân HTTP response chính xác là:

~~~text
Hello from embedded server
~~~

Trong ví dụ, **@RestController** cung cấp handler, nhưng Tomcat mới nhận kết nối HTTP. **DispatcherServlet** làm nhiệm vụ định tuyến đến controller, còn **web context** quản lý các bean, factory và server.

**Tại sao không gọi context.close() trong main?** Vì đây là web server chạy lâu dài. Đóng context ngay sau **run(...)** sẽ bắt đầu dừng embedded server và endpoint mất khả năng phục vụ.

## 6. Cùng ví dụ, nếu đổi sang WebFlux thì quan hệ thay đổi thế nào?

Giả sử chuyển sang một dự án **spring-boot-starter-webflux**, không giữ **spring-boot-starter-web** (để Boot tự chọn REACTIVE theo classpath). Khi đó:

- Context thường là **AnnotationConfigReactiveWebServerApplicationContext**.
- Factory thường là **NettyReactiveWebServerFactory**.
- WebServer thường là **NettyWebServer**.
- HTTP đi vào **HttpHandler** và pipeline WebFlux; không đi qua Spring MVC **DispatcherServlet**.

Để quan sát chung cả hai stack ở runtime mà không gắn cứng vào Servlet, có thể dùng đoạn minh họa sau **SpringApplication.run(...)**:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(MyApplication.class, args);

if (context instanceof WebServerApplicationContext webContext) {
    WebServer server = webContext.getWebServer();
    System.out.println("Context = " + context.getClass().getSimpleName());
    System.out.println("Server = " + server.getClass().getSimpleName());
    System.out.println("Port = " + server.getPort());
}
~~~

Đoạn này **giả định** bạn đã khai báo **MyApplication** và import **ConfigurableApplicationContext**, **SpringApplication**, **WebServerApplicationContext**, **WebServer**; nó minh họa API chung, không phải tệp Java độc lập. Trong ứng dụng REACTIVE, **không** gọi **getBean(ServletWebServerFactory.class)** như ví dụ Servlet: cần dùng **ReactiveWebServerFactory** nếu muốn đọc factory cụ thể.

Không nên thay mỗi import **ServletWebServerFactory** thành **ReactiveWebServerFactory** rồi cho rằng mọi controller servlet tự hoạt động trong WebFlux. **@RestController** có mặt ở cả hai stack, nhưng pipeline xử lý HTTP, filter, security và các chi tiết API khác nhau.

## 7. Cấu hình nào đi đến factory, và cấu hình nào chọn context?

Phân biệt hai nhóm thuộc tính thường được dùng cùng nhau:

| Cấu hình | Quyết định cái gì? | Hệ quả |
| --- | --- | --- |
| **spring.main.web-application-type=servlet** | Yêu cầu chọn Servlet web context | Cần các thành phần Servlet và factory thích hợp |
| **spring.main.web-application-type=reactive** | Yêu cầu chọn Reactive web context | Cần reactive HTTP stack và factory thích hợp |
| **spring.main.web-application-type=none** | Chọn non-web context | Không khởi chạy embedded HTTP server cho ứng dụng chính |
| **server.port=8081** | Chỉnh port của factory/server | Không tự biến non-web app thành web app |
| **server.port=0** | Yêu cầu server dùng port trống do hệ điều hành chọn | Phải lấy port thật sau khi server initialized |
| **server.port=-1** | Tắt HTTP endpoints trong khi vẫn giữ web application context | Khác với việc chọn WebApplicationType.NONE |
| **server.address**, **server.ssl.*** | Chỉnh địa chỉ bind và TLS | Được áp dụng khi cấu hình và tạo server |
| **server.servlet.context-path=/api** | Context path cho servlet web server | URL endpoint /hello thường thành /api/hello ở Servlet stack |
| **server.compression.enabled=true** | Bật nén HTTP response nếu được hỗ trợ | Có thể ảnh hưởng response theo content type và ngưỡng nén |

**spring.main.web-application-type** quyết định loại **container/context**. **server.*** điều chỉnh **web server** trong context đã chọn. Một lỗi thường gặp là đặt **server.port=8080** rồi mong ứng dụng **NONE** tự tạo Tomcat; điều đó không xảy ra.

### 7.1. Ưu tiên cấu hình bên ngoài

Ví dụ cấu hình file:

~~~properties
server.port=8080
~~~

Và chạy:

~~~bash
./gradlew bootRun --args='--server.port=9090'
~~~

Với cấu hình thông thường, **--server.port=9090** từ command line thắng giá trị **8080** trong file, vì các thuộc tính được bind vào factory từ Environment theo thứ tự ưu tiên PropertySource. Tuy nhiên, một **WebServerFactoryCustomizer** chạy sau có thể tiếp tục thay đổi factory: cần kiểm tra cấu hình và customizer thực tế khi debug port.

### 7.2. Tùy biến factory bằng WebServerFactoryCustomizer

Ưu tiên cấu hình **server.*** có sẵn trước. Khi cần tùy biến mà Spring Boot chưa cung cấp property tương ứng, có thể đăng ký một **WebServerFactoryCustomizer**.

Ví dụ độc lập cho **Servlet stack**, nếu bạn thực sự muốn ấn định port bằng mã Java:

~~~java
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.boot.web.servlet.server.ConfigurableServletWebServerFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class CustomServletServerConfiguration {

    @Bean
    WebServerFactoryCustomizer<ConfigurableServletWebServerFactory>
            localPortCustomizer() {
        return factory -> factory.setPort(9090);
    }
}
~~~

Đoạn này là một lớp cấu hình dùng trong **dự án Servlet Boot**. Khi thêm nó, không còn kỳ vọng kết quả **server.port=0** của ví dụ trước vì customizer đang ấn định **9090**. Trong các dự án thực tế, nếu mục tiêu chỉ là đổi port, **server.port=9090** trong cấu hình sẽ rõ ràng và dễ vận hành hơn.

Nếu chỉ muốn chỉnh một server cụ thể, có thể dùng factory type cụ thể như **TomcatServletWebServerFactory**. Với Reactive stack, dùng **ConfigurableReactiveWebServerFactory** hoặc factory triển khai tương ứng như **NettyReactiveWebServerFactory**.

**Không tự tạo WebServer bean rồi gọi start() song song** khi đã dùng web context do Spring Boot quản lý. Điều đó có thể gây hai server, tranh chấp port, shutdown không đồng nhất hoặc bỏ qua lifecycle của context.

### 7.3. Tự khai báo factory bean khi nào?

Có thể tự khai báo một **ServletWebServerFactory** hoặc **ReactiveWebServerFactory** bean để thay thế factory auto-configured nếu có yêu cầu đặc biệt. Nhưng đây là cấp tùy biến mạnh:

- Bạn phải bảo đảm factory phù hợp với Servlet/Reactive context.
- Spring Boot có thể vẫn áp dụng các customizer auto-configured lên factory của bạn.
- Hai factory bean cùng loại trong một context có thể khiến web context không xác định được factory nào phải dùng.
- Nên ưu tiên đổi starter, cấu hình **server.*** hoặc thêm **WebServerFactoryCustomizer** trước khi thay hẳn factory.

## 8. Đọc port và theo dõi lifecycle đúng thời điểm

### 8.1. WebServerInitializedEvent

Đây là sự kiện dành cho lúc server đã được khởi tạo/sẵn sàng, có **getWebServer()** để đọc đối tượng server và port.

~~~java
@Bean
ApplicationListener<WebServerInitializedEvent> portListener() {
    return event -> {
        int port = event.getWebServer().getPort();
        System.out.println("Actual HTTP port = " + port);
    };
}
~~~

Đoạn này là method **@Bean** đặt trong một lớp **@Configuration** hoặc **@SpringBootApplication**, với các import tương ứng. Phù hợp để đọc port động và quan sát lúc server khởi động. **WebServerInitializedEvent** có các biến thể **ServletWebServerInitializedEvent** và **ReactiveWebServerInitializedEvent**.

Đừng nhầm thời điểm event này với thời điểm ứng dụng ready. Sự kiện server initialized đến sớm hơn **ApplicationReadyEvent**. Nếu actuator management được chạy trên cổng riêng, một ứng dụng có thể có **nhiều web context/server** và phát nhiều sự kiện; kiểm tra **event.getApplicationContext()** hoặc **getServerNamespace()** trước khi coi event nào là HTTP server chính.

### 8.2. Lấy WebServer từ web context sau khi run trả về

Khi bootstrapping đã hoàn tất:

~~~java
ConfigurableApplicationContext context = SpringApplication.run(App.class, args);

if (context instanceof WebServerApplicationContext webContext) {
    WebServer server = webContext.getWebServer();
    if (server != null) {
        System.out.println("Listening on port " + server.getPort());
    }
}
~~~

Đây là snippet (giả định có lớp **App** và import phù hợp). API **WebServerApplicationContext.getWebServer()** trả về server do context tạo hoặc **null nếu server chưa được tạo**. Sau một lần **run(...)** thành công và có embedded HTTP server hoạt động, thông thường đã có server để truy vấn.

### 8.3. Vì sao không lấy local.server.port quá sớm?

Khi dùng **server.port=0**, cổng thật chỉ được biết khi server được khởi tạo. Vì thế không nên inject **local.server.port** vào một bean được tạo quá sớm trong bootstrap rồi kỳ vọng đó là số cổng thực tế.

Trong integration test với **@SpringBootTest(webEnvironment = RANDOM_PORT)** có thể dùng **@LocalServerPort**; Spring Boot bố trí cách tiêm giá trị sau khi server đã được khởi tạo. Với mã ứng dụng thông thường, **WebServerInitializedEvent** là điểm quan sát đáng tin cậy hơn cho việc truy cập port thực tế.

## 9. Khác nhau giữa server chạy thật và mock web context trong test

**@SpringBootTest(webEnvironment = RANDOM_PORT)** khởi động embedded server trên port ngẫu nhiên, phù hợp kiểm tra luồng HTTP thật từ network stack đến controller.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HelloHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate rest;

    @Test
    void endpointIsServedOverHttp() {
        String body = rest.getForObject(
                "http://localhost:" + port + "/hello", String.class);

        assertThat(body).isEqualTo("Hello from embedded server");
    }
}
~~~

Đoạn test giả định ứng dụng ví dụ ở mục 5 và dependency **spring-boot-starter-test**. **TestRestTemplate** dùng cho integration test Servlet phù hợp; trong dự án reactive có thể dùng **WebTestClient**.

Ngược lại, **@SpringBootTest(webEnvironment = MOCK)** hoặc các slice test như **@WebMvcTest** có thể dựng context phục vụ kiểm thử MVC mà **không mở embedded HTTP listener thật**. Vì vậy phép thử mock thành công không chứng minh rằng factory thực tế có thể bind cổng, nạp TLS certificate hoặc chấp nhận request HTTP qua socket.

## 10. Những lỗi thường gặp khi phối hợp context, factory và server

### 10.1. Thiếu WebServerFactory bean

Triệu chứng thường có thông báo liên quan **missing ServletWebServerFactory bean** hoặc **missing ReactiveWebServerFactory bean**. Các hướng kiểm tra:

1. Xác nhận **spring.main.web-application-type** có đúng với stack bạn muốn.
2. Kiểm tra dependency của **spring-boot-starter-web** hoặc **spring-boot-starter-webflux** và starter server tương ứng.
3. Kiểm tra có loại trừ auto-configuration hoặc loại trừ dependency của embedded server hay không.
4. Nếu đã khai báo factory thủ công, kiểm tra nó có đúng interface và thuộc context hiện tại không.

**Context có thể được tạo nhưng thất bại khi refresh** nếu không tìm được factory phù hợp. Đây là lỗi về cấu hình bootstrap, khác lỗi controller không tìm thấy route.

### 10.2. Có nhiều factory cùng loại

Web context thường mong tìm **một factory đúng loại**. Nếu có nhiều bean cùng loại mà không thể xác định duy nhất, ứng dụng có thể dừng khởi động với thông báo lựa chọn factory không rõ ràng. Đừng cố sửa bằng cách inject ngẫu nhiên một factory; cần cấu hình rõ bean nào được sử dụng hoặc để auto-configuration quản lý.

### 10.3. Cổng 8080 đang bị tiến trình khác chiếm

Dù controller và context hoàn toàn hợp lệ, server vẫn có thể thất bại khi bind **server.port**. Cách kiểm tra: xem lỗi **Port ... was already in use**, chọn cổng khác, dừng tiến trình chiếm cổng hoặc dùng **server.port=0** khi chạy thử.

### 10.4. Đã thấy log "Tomcat started" nhưng request vẫn thất bại

Cần phân biệt ba lớp chẩn đoán:

- **Server/network:** địa chỉ bind, cổng, reverse proxy, firewall, TLS, lỗi port, tình trạng server có đang chạy.
- **HTTP framework:** URL, context path, servlet mapping, DispatcherServlet, WebFlux routing, method HTTP.
- **Business/readiness:** dependency ngoài, runner, datasource, authentication và tình trạng ứng dụng đã ready.

Log server start không khẳng định một endpoint cụ thể tồn tại, handler không lỗi, hay mọi dependency nghiệp vụ đã sẵn sàng.

### 10.5. Có cả spring-boot-starter-web và spring-boot-starter-webflux

Mặc định Spring MVC thường được Boot ưu tiên khi cả hai thư viện hiện diện. Vì vậy **reactive dependency** hoặc **WebClient** có mặt không tự biến toàn bộ ứng dụng thành reactive web server. Nếu chủ đích sử dụng REACTIVE, cần chọn stack, loại context và factory đúng cách thay vì phỏng đoán từ tên một dependency.

### 10.6. Cấu hình server.port=-1 bị nhầm với NONE

**server.port=-1** giữ web application context trong khi vô hiệu hóa HTTP endpoints; **spring.main.web-application-type=none** chọn non-web context. Hai lựa chọn phục vụ mục đích khác nhau và có hệ quả bootstrap khác nhau.

### 10.7. Gọi factory.getWebServer(...) trực tiếp trong service

Nếu một bean nghiệp vụ tự gọi factory để tạo server mới, nó có thể tạo thêm instance server ngoài vòng đời context, gây lỗi trùng port hoặc tài nguyên không được shutdown đúng cách. Hãy để **web context** là bên tạo/quản lý server. Cần truy vấn server đang chạy thì dùng **WebServerApplicationContext.getWebServer()**.

### 10.8. Không đóng context khi tắt ứng dụng

Embedded server thuộc vòng đời application context. Hãy để cơ chế shutdown của Spring Boot đóng context một cách có kiểm soát; nếu ứng dụng tự vận hành context thủ công, đảm bảo **close()** được gọi khi thực sự kết thúc. Trong app web phục vụ lâu dài, không đóng context ngay sau run.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Ứng dụng Spring MVC có bean **TomcatServletWebServerFactory**. Bean này có phải **TomcatWebServer** không?

**Đáp án:** Không. **TomcatServletWebServerFactory** là factory có khả năng tạo **WebServer**, còn **TomcatWebServer** là đối tượng server thực tế; web context điều phối tạo, start và stop.

**Câu 2.** Muốn chuyển từ Spring MVC trên Tomcat sang Spring MVC trên Jetty thì có cần đổi web context thành ReactiveWebServerApplicationContext không?

**Đáp án:** Không. Spring MVC vẫn là Servlet stack; thay server dependency/factory sang Jetty nhưng vẫn dùng họ **ServletWebServerApplicationContext**.

**Câu 3.** Một ứng dụng dùng **spring-boot-starter-webflux** và Reactor Netty. Factory nhận gì để gắn xử lý HTTP?

**Đáp án:** **ReactiveWebServerFactory.getWebServer(HttpHandler)** nhận **HttpHandler**, cầu nối từ server reactive vào pipeline WebFlux.

**Câu 4.** Trong **WebServerInitializedEvent**, bạn đọc được port thật. Ứng dụng chắc chắn đã phát **ApplicationReadyEvent** chưa?

**Đáp án:** Chưa. Event server initialized đến trước khi toàn bộ chuỗi runner/ready hoàn tất.

**Câu 5.** Đặt **server.port=0**, muốn kiểm tra socket HTTP thật trong test thì dùng **@WebMvcTest** hay **@SpringBootTest(webEnvironment = RANDOM_PORT)**?

**Đáp án:** Chọn **RANDOM_PORT** để có embedded HTTP server thật. **@WebMvcTest** chủ yếu kiểm thử MVC slice trên mock request infrastructure.

**Câu 6.** Khi **spring.main.web-application-type=none** nhưng vẫn có **spring-boot-starter-web** trên classpath, container có tự tạo Tomcat không?

**Đáp án:** Không theo cơ chế khởi động embedded web server thông thường. Boot đã được yêu cầu chọn non-web context; có dependency là chưa đủ để ứng dụng chính lắng nghe HTTP.

**Câu 7.** Vì sao nên chỉnh **server.port** thay vì tự gọi **new Tomcat()**?

**Đáp án:** Vì Boot đang cung cấp factory, áp dụng ServerProperties/customizers và quản lý lifecycle. Dựng Tomcat độc lập sẽ đi ngoài hệ thống này và dễ gây lỗi phối hợp hoặc shutdown.

## 12. Ghi nhớ và tài liệu chính thức

Một ứng dụng web Spring Boot nhúng có ba lớp quan trọng:

**Web ApplicationContext (người quản lý vòng đời) → WebServerFactory (người tạo server) → WebServer (thành phần lắng nghe HTTP).**

Với Servlet, web context dùng **ServletWebServerFactory** và **ServletContextInitializer** để kết nối Spring MVC với Tomcat/Jetty/Undertow. Với Reactive, web context dùng **ReactiveWebServerFactory** và **HttpHandler** để kết nối WebFlux với Reactor Netty hoặc server tương thích. **Sự kiện server đã khởi động** khác với **ứng dụng đã ready**, và việc **run(...) trả về** cũng không có nghĩa web server dừng.

Tham khảo theo Spring Boot 3.3:

- Embedded Web Servers: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Servlet Web Applications, mục ServletWebServerApplicationContext: https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html
- Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- ServletWebServerApplicationContext API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/servlet/context/ServletWebServerApplicationContext.html
- ServletWebServerFactory API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/servlet/server/ServletWebServerFactory.html
- WebServerApplicationContext API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/context/WebServerApplicationContext.html
- WebServerInitializedEvent API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/context/WebServerInitializedEvent.html
# Mối quan hệ giữa ứng dụng, Spring Framework và máy chủ web

Một ứng dụng Spring Boot chạy trên Servlet stack gồm nhiều thành phần có trách nhiệm khác nhau. **Ứng dụng** chứa cấu hình và nghiệp vụ của sản phẩm; **Spring Framework** quản lý object, dependency và xử lý web theo mô hình Spring MVC; **Spring Boot** khởi tạo và tự động cấu hình các thành phần phù hợp; **máy chủ web/Servlet container** tiếp nhận kết nối HTTP và gọi các Servlet Filter, Servlet trong ứng dụng.

Hiểu đúng ranh giới này giúp trả lời các câu hỏi thực tế: ai mở cổng 8080, ai tạo controller, request đi qua đâu, tại sao thêm starter lại có Tomcat, DispatcherServlet có phải web server không, và điều gì thay đổi khi đóng gói ứng dụng thành JAR hoặc WAR.

## 1. Bốn thành phần và trách nhiệm

| Thành phần | Trách nhiệm chính | Ví dụ |
|---|---|---|
| Ứng dụng (application) | Khai báo cấu hình, endpoint, service, repository và quy tắc nghiệp vụ | DemoApplication, HelloController, OrderService |
| Spring Framework | Cung cấp IoC/DI, ApplicationContext, AOP, event, Spring MVC và các abstraction | ApplicationContext, @Component, DispatcherServlet, @Transactional |
| Spring Boot | Bootstrap ứng dụng, quản lý dependency, auto-configuration, externalized configuration, đóng gói và chạy server nhúng | SpringApplication.run, @SpringBootApplication, spring-boot-starter-web |
| Web server / Servlet container | Mở socket, nhận HTTP, quản lý Servlet lifecycle, filter chain, thread xử lý và gửi response | Tomcat, Jetty, Undertow |

Có thể xem luồng phụ thuộc theo hướng:

~~~text
Ứng dụng của chúng ta
    |
    | khai báo bean, controller, cấu hình
    v
Spring Framework
    |
    | cung cấp container, Spring MVC và abstraction
    v
Spring Boot
    |
    | bootstrap + auto-configure + tích hợp server
    v
Web server / Servlet container
    |
    | nhận kết nối và gọi Servlet Filter / Servlet
    v
HTTP request và response
~~~

Sơ đồ trên thể hiện trách nhiệm, không có nghĩa Spring Framework phụ thuộc Spring Boot ở mọi ứng dụng. Spring Framework có thể chạy độc lập; Spring Boot xây dựng trên Spring Framework để giảm cấu hình và chuẩn hóa cách khởi động, triển khai.

## 2. Ứng dụng là nơi chứa cấu hình và nghiệp vụ

Ứng dụng Spring Boot là phần code do đội phát triển sở hữu. Nó thường định nghĩa:

- **Entry point:** lớp có main() gọi SpringApplication.run(...).
- **Configuration:** bean, cấu hình bảo mật, datasource, serialization, cache và các tích hợp.
- **Web layer:** controller, request mapping, validation và chuyển đổi dữ liệu HTTP.
- **Application/service layer:** use case và điều phối nghiệp vụ.
- **Persistence/integration layer:** repository, database client, message broker và dịch vụ bên ngoài.
- **Domain model:** trạng thái và quy tắc cốt lõi của nghiệp vụ.

Ví dụ một controller chỉ mô tả endpoint và giao việc cho service:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/{id}")
    public OrderResponse findById(@PathVariable long id) {
        return orderService.findById(id);
    }
}
~~~

Controller không tự mở socket, không tự phân tích HTTP protocol và cũng không tự tạo Spring bean. Những trách nhiệm đó thuộc hạ tầng web và Spring container. Controller chỉ được gọi khi request đã đi qua các lớp phía trước và được Spring MVC định tuyến đến handler tương ứng.

## 3. Spring Framework quản lý object và xử lý request

### 3.1. IoC container và Dependency Injection

Spring Framework cung cấp IoC container. Container tạo, cấu hình, kết nối và quản lý vòng đời các object được đăng ký làm bean.

ApplicationContext là interface trung tâm thường dùng để tương tác với container. Bean có thể được khai báo qua:

- @Component, @Service, @Repository, @Controller và các stereotype tương ứng.
- @Bean trong lớp @Configuration.
- Các cơ chế đăng ký bean khác do framework hoặc thư viện tích hợp cung cấp.

Dependency Injection giúp object nhận dependency từ container thay vì tự tạo chúng bằng new ở mọi nơi. Constructor injection làm dependency rõ ràng và thuận tiện cho kiểm thử:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    public OrderResponse findById(long id) {
        Order order = orderRepository.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));
        return OrderResponse.from(order);
    }
}
~~~

Trong ví dụ, Spring container tạo OrderRepository, tạo OrderService với repository đó, rồi tạo controller với service. Ứng dụng không cần tự nối từng object bằng tay.

Mặc định, nhiều bean Spring có scope singleton: một instance được dùng chung trong ApplicationContext. Vì vậy, không nên lưu dữ liệu riêng của request vào field mutable trong singleton service/controller. Nhiều request có thể chạy đồng thời trên các thread khác nhau; bean dùng chung cần an toàn luồng và nên giữ trạng thái request trong biến cục bộ hoặc abstraction có scope phù hợp.

### 3.2. Spring MVC và DispatcherServlet

Với ứng dụng Servlet dùng Spring MVC, DispatcherServlet là Front Controller. Servlet container gọi nó khi request khớp mapping đã đăng ký.

Các bước khái quát bên trong Spring MVC:

1. DispatcherServlet nhận request.
2. HandlerMapping tìm handler phù hợp, thường là method trong controller.
3. HandlerAdapter gọi handler.
4. Argument resolver đọc path variable, query parameter, header, body và chuyển thành tham số Java.
5. Controller gọi service và nhận kết quả.
6. Return value handler, HttpMessageConverter hoặc ViewResolver chuyển kết quả thành response body/view.
7. Servlet container gửi HTTP response về client.

@RestController thường trả dữ liệu được chuyển đổi qua HttpMessageConverter, ví dụ object Java thành JSON bằng Jackson khi dependency phù hợp có trên classpath.

DispatcherServlet **không phải máy chủ web**. Nó là một Servlet chạy bên trong Servlet container. Tomcat hoặc container tương đương mới tiếp nhận kết nối HTTP ở tầng server và quản lý Servlet lifecycle.

### 3.3. Spring Framework không chỉ có web

Spring Framework còn cung cấp nhiều capability mà ứng dụng có thể dùng ngoài xử lý HTTP:

- AOP và transaction abstraction.
- Validation và event.
- Resource abstraction.
- Scheduling và task execution.
- Integration với persistence, messaging và các hệ thống khác thông qua module phù hợp.

Một ứng dụng Spring Boot không bắt buộc phải là web application. Nếu chỉ chạy batch, command line hoặc worker, nó vẫn có thể dùng Spring container mà không mở HTTP server.

## 4. Spring Boot kết nối các thành phần khi khởi động

### 4.1. Vai trò của Spring Boot

Spring Boot không thay thế Spring Framework. Nó bổ sung cách khởi tạo và cấu hình ứng dụng dựa trên classpath, bean hiện có và properties:

- **Starter dependencies** gom các dependency thường đi cùng nhau.
- **Auto-configuration** tạo cấu hình mặc định khi điều kiện phù hợp được đáp ứng.
- **Externalized configuration** đọc cấu hình từ properties, YAML, environment variables và nguồn được hỗ trợ.
- **Embedded server integration** tạo và khởi động web server ngay trong tiến trình ứng dụng.
- **Executable archive** đóng gói ứng dụng cùng dependency để chạy bằng Java.

Ví dụ, spring-boot-starter-web đưa Spring MVC và server nhúng mặc định của cấu hình Boot vào classpath. Nếu ứng dụng dùng Tomcat mặc định, Boot tạo cấu hình server và tích hợp Tomcat với Spring ApplicationContext.

Starter không phải máy chủ; nó là dependency descriptor. Tomcat cũng không được tạo ra bởi annotation @RestController; nó xuất hiện vì runtime web và cấu hình Boot tương ứng.

### 4.2. @SpringBootApplication

Annotation này kết hợp ba ý chính:

- @SpringBootConfiguration: đánh dấu lớp cấu hình nguồn của ứng dụng.
- @EnableAutoConfiguration: cho phép Boot áp dụng auto-configuration dựa trên điều kiện.
- @ComponentScan: quét component theo package của lớp ứng dụng và các package con theo quy tắc mặc định.

Ví dụ entry point:

~~~java
@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

SpringApplication.run(...) là điểm bắt đầu bootstrap. Nó chuẩn bị Environment, tạo ApplicationContext phù hợp, nạp bean definitions, áp dụng auto-configuration và refresh context. Với web application Servlet, context chuyên biệt tạo và quản lý web server. Khi quá trình khởi động hoàn tất, ứng dụng sẵn sàng nhận request.

Không nên hiểu rằng @SpringBootApplication tự chứa toàn bộ server hoặc controller. Annotation bật các cơ chế cấu hình và quét bean; các thành phần cụ thể được tạo bởi container và auto-configuration khi điều kiện tương ứng đúng.

### 4.3. Auto-configuration có điều kiện

Auto-configuration không đơn giản là “có dependency thì luôn tạo bean”. Các cấu hình thường dựa trên điều kiện như:

- Có hoặc không có class trên classpath.
- Ứng dụng có phải web application hay không.
- Bean tương ứng đã được người dùng tự khai báo hay chưa.
- Properties có bật/tắt capability hay đặt giá trị cụ thể không.

Ví dụ, nếu ứng dụng tự khai báo bean SecurityFilterChain, cấu hình bảo mật mặc định của Boot có thể lùi lại ở phần tương ứng. Tương tự, việc thay server implementation hoặc cấu hình bean tùy chỉnh có thể làm auto-configuration mặc định không còn áp dụng.

Khi một bean không xuất hiện như mong đợi, cần kiểm tra condition evaluation report, classpath, properties và các bean tùy chỉnh trước khi kết luận framework không hỗ trợ.

## 5. Máy chủ web và Servlet container làm gì?

### 5.1. Web server so với Servlet container

Web server chịu trách nhiệm tiếp nhận kết nối mạng và trao đổi HTTP. Servlet container là runtime thực thi Jakarta Servlet: quản lý Servlet, Filter, listener, mapping, request/response và lifecycle.

Tomcat kết hợp vai trò web server với Servlet container. Jetty cũng có thể đảm nhiệm vai trò tương tự. Trong ứng dụng Spring MVC, server nhúng thường cung cấp Servlet container cho DispatcherServlet và các filter của ứng dụng.

Các trách nhiệm điển hình của server/container:

- Bind vào địa chỉ và port cấu hình.
- Nhận kết nối TCP và đọc HTTP request.
- Quản lý connector, thread pool và giới hạn kết nối.
- Tạo HttpServletRequest/HttpServletResponse.
- Chạy Servlet Filter theo thứ tự đăng ký.
- Gọi Servlet được mapping, ví dụ DispatcherServlet.
- Gửi response và quản lý tài nguyên mạng.
- Quản lý lifecycle khi ứng dụng khởi động hoặc shutdown.

Server không tự hiểu “đơn hàng 42 thuộc khách hàng nào”. Đó là trách nhiệm của application/service/repository và chính sách bảo mật nghiệp vụ.

### 5.2. Embedded server

Với mô hình executable JAR, web server chạy nhúng trong cùng JVM với ứng dụng:

~~~text
Một tiến trình JVM
    |
    +-- Spring Boot
    |     |
    |     +-- ApplicationContext
    |     +-- Spring MVC
    |     +-- Controllers / Services / Repositories
    |
    +-- Embedded Tomcat
          |
          +-- Connector / HTTP handling
          +-- Servlet container
          +-- DispatcherServlet
          +-- Servlet Filters
~~~

Lệnh chạy phổ biến:

~~~bash
java -jar application.jar
~~~

Ứng dụng và server được khởi động, giám sát và dừng như một tiến trình. Điều này đơn giản hóa triển khai vì không cần cài một Tomcat riêng rồi copy WAR vào server đó. Server nhúng vẫn là một server thật, có port, connector, thread pool, TLS và cấu hình vận hành.

### 5.3. External server

Một mô hình khác là đóng gói WAR rồi triển khai vào Servlet container do môi trường vận hành quản lý:

~~~text
Tomcat bên ngoài
    |
    +-- Context của ứng dụng
          |
          +-- SpringBootServletInitializer
          +-- Spring ApplicationContext
          +-- Spring MVC / DispatcherServlet
          +-- Controllers / Services
~~~

Khi chạy theo cách này, server container được khởi động độc lập và nạp ứng dụng WAR. Với Spring Boot, ứng dụng WAR thường kế thừa SpringBootServletInitializer để cung cấp nguồn cấu hình cho servlet container.

Hai mô hình có chung code ứng dụng Spring MVC nhưng khác nơi sở hữu lifecycle của web server:

- Embedded: ứng dụng Spring Boot khởi tạo và quản lý server nhúng.
- External: môi trường/container khởi động server, sau đó nạp ứng dụng WAR.

Không nên giả định một ứng dụng JAR chạy nhúng có thể được thả trực tiếp vào thư mục webapps của Tomcat. Cần đúng packaging và bootstrap cho WAR.

## 6. Từ lúc khởi động đến khi nhận request

### 6.1. Startup flow

Luồng khởi động khái quát của ứng dụng Servlet Spring Boot:

~~~text
JVM chạy main()
    |
SpringApplication.run(...)
    |
Chuẩn bị Environment và cấu hình
    |
Tạo ServletWebServerApplicationContext
    |
Đăng ký và tạo bean definitions
    |
Áp dụng auto-configuration
    |
Refresh ApplicationContext
    |
Tạo EmbeddedWebServer từ WebServerFactory
    |
Đăng ký Servlet, Filter, Listener
    |
Khởi động server và mở port
    |
ApplicationReadyEvent / ứng dụng sẵn sàng
~~~

Tên và thứ tự chi tiết của các event/hook có thể khác theo phiên bản và custom lifecycle. Điểm quan trọng: web server được tích hợp vào quá trình khởi tạo web ApplicationContext; nó không phải một tiến trình Tomcat riêng được Spring MVC tự tìm thấy ở runtime.

Các thành phần như ServletWebServerApplicationContext, ServletWebServerFactory và implementation Tomcat cụ thể là phần tích hợp giữa Boot và server. Thông thường ứng dụng chỉ cần dùng starter và cấu hình properties; chỉ tùy biến factory khi có yêu cầu rõ ràng.

### 6.2. Request flow

Sau khi server sẵn sàng, một request MVC thường đi theo luồng:

~~~text
Browser / API client
    |
TCP connection -> Tomcat Connector
    |
HTTP parsing -> Servlet container
    |
Servlet Filter chain
    |
DispatcherServlet
    |
HandlerMapping -> HandlerAdapter
    |
Controller
    |
Service -> Repository / external system
    |
Return value / HttpMessageConverter
    |
Servlet response -> Tomcat -> HTTP response
~~~

Ví dụ GET /api/orders/42:

1. Tomcat nhận request và tạo request/response object theo Servlet API.
2. Các filter được chạy: encoding, logging, security, tracing hoặc filter của ứng dụng theo cấu hình.
3. DispatcherServlet tìm controller method khớp /api/orders/{id}.
4. Spring MVC chuyển path variable 42 thành kiểu long nếu hợp lệ.
5. Controller gọi OrderService.
6. Service thực hiện kiểm tra nghiệp vụ và gọi repository.
7. Controller trả DTO; message converter chuyển DTO thành JSON.
8. Container ghi status, headers và response body về client.

Nếu filter từ chối request, request có thể không tới DispatcherServlet. Nếu controller gọi service và service phát sinh lỗi, exception resolver/exception handler có thể chuyển lỗi thành response. Không phải mọi lỗi đều do Tomcat tạo ra.

### 6.3. Request thread và bean scope

Trong cấu hình Spring MVC đồng bộ thông thường, request được xử lý trên thread do server quản lý. Tomcat dùng thread pool để phục vụ nhiều request; không phải mỗi request khởi tạo một JVM hoặc một Spring ApplicationContext mới.

Vì bean singleton được chia sẻ giữa các request, cần:

- Không lưu dữ liệu request vào field mutable của singleton controller/service.
- Dùng biến local cho dữ liệu của một lần gọi.
- Dùng request scope hoặc cơ chế context phù hợp khi thực sự cần state theo request.
- Không tự tạo thread tùy tiện rồi truy cập request object sau khi request đã kết thúc.
- Cấu hình giới hạn thread, queue, connection timeout theo tải và tài nguyên thực tế.

Async processing, virtual threads hoặc reactive stack có mô hình thực thi khác; không áp dụng máy móc giả định “mỗi request luôn một thread” cho mọi kiến trúc.

## 7. Cấu hình runtime web

Một số cấu hình thường gặp trong application.yml:

~~~yaml
server:
  port: 8081
  address: 0.0.0.0
  servlet:
    context-path: /shop
~~~

Ý nghĩa:

- server.port: port mà server nhúng lắng nghe. Mặc định thường là 8080 khi không thay đổi.
- server.address: địa chỉ network interface để bind; 0.0.0.0 cho phép bind mọi interface IPv4 trong môi trường phù hợp.
- server.servlet.context-path: prefix của toàn bộ web application. Với cấu hình trên, controller mapping /api/orders được truy cập qua /shop/api/orders.

Cần phân biệt:

| Giá trị | Vai trò | Ví dụ |
|---|---|---|
| Server port | Port server mở trên máy | 8081 |
| Context path | Prefix của web application | /shop |
| Servlet mapping/path | Đường dẫn mà một Servlet cụ thể nhận | /mvc/* nếu cấu hình riêng |
| Controller mapping | Đường dẫn do Spring MVC handler khai báo | /api/orders/{id} |

Đừng cộng/trừ các prefix theo cảm tính. Khi request trả 404, hãy xác định port, context path, servlet mapping và controller mapping riêng biệt.

Các thuộc tính riêng của server như server.tomcat.* chỉ áp dụng khi dùng Tomcat. Nếu chuyển sang Jetty hoặc Undertow, nhóm cấu hình tương ứng có thể khác. Tránh phụ thuộc sâu vào implementation nếu ứng dụng không có yêu cầu đặc thù.

## 8. Vì sao thêm starter lại có server?

Với Servlet/MVC stack, dependency thường dùng là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Starter web kéo các thành phần cần cho Spring MVC và server nhúng mặc định (Tomcat trong cấu hình tiêu chuẩn). Khi ứng dụng được nhận diện là Servlet web application, Boot áp dụng auto-configuration tương ứng và tạo web server.

Có thể thay Tomcat bằng Jetty hoặc server được hỗ trợ khác bằng cách loại dependency server mặc định và thêm starter/server thay thế phù hợp. Cần kiểm tra dependency tree để tránh đưa đồng thời nhiều server implementation ngoài chủ đích.

Không đồng nhất các khái niệm:

- spring-boot-starter-web: nhóm dependency cho web MVC/Servlet.
- spring-webmvc: framework xử lý web MVC.
- spring-boot-starter-tomcat: dependency tích hợp Tomcat trong mô hình Boot.
- Tomcat: server/Servlet container thực thi ứng dụng.
- DispatcherServlet: Servlet của Spring MVC chạy bên trong container.

## 9. Servlet stack và Reactive stack

Spring MVC trên Servlet và Spring WebFlux là hai mô hình web khác nhau:

| Nội dung | Spring MVC / Servlet | Spring WebFlux |
|---|---|---|
| Programming model | Servlet request/response, thường đồng bộ | Reactive streams, non-blocking |
| Server thường gặp | Tomcat, Jetty, Undertow | Reactor Netty; cũng có thể chạy trên server hỗ trợ |
| API chính | HttpServletRequest, HttpServletResponse, MVC controllers | Mono, Flux, reactive handler |
| Phù hợp khi | Ứng dụng MVC truyền thống, thư viện blocking, mô hình request/response phổ biến | Cần xử lý non-blocking xuyên suốt và có workload phù hợp |
| Threading | Thường dùng request thread từ server pool | Event-loop và scheduler; tránh blocking event-loop |

Không nên chọn WebFlux chỉ vì nghe “nhanh hơn”. Nếu controller gọi JDBC/blocking HTTP client, lợi ích non-blocking có thể mất đi và cấu hình sai có thể gây nghẽn event-loop.

Khi cả starter MVC và WebFlux cùng có mặt trên classpath, Spring Boot thông thường ưu tiên ứng dụng MVC nếu không cấu hình loại web application khác. Vì vậy cần quản lý dependency rõ ràng, tránh vô tình đưa cả hai stack vào chỉ vì một thư viện phụ thuộc.

## 10. Ví dụ chạy được: Spring Boot Servlet tối giản

Ví dụ dưới đây dùng Java 21 và Spring Boot 3.3.x. Nó minh họa ứng dụng khai báo controller, Boot khởi tạo context và embedded Tomcat nhận HTTP request.

Cấu trúc:

~~~text
web-runtime-demo/
├── pom.xml
└── src/main/java/com/example/demo/
    ├── DemoApplication.java
    └── HelloController.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>web-runtime-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**DemoApplication.java**

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**HelloController.java**

~~~java
package com.example.demo;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    @GetMapping("/hello")
    public Map<String, String> hello() {
        return Map.of("message", "Hello from Spring MVC");
    }
}
~~~

Chạy ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Trong cấu hình mặc định, Boot khởi động embedded Tomcat trên port 8080. Mở terminal khác và gọi:

~~~bash
curl -i http://localhost:8080/hello
~~~

Response body:

~~~json
{"message":"Hello from Spring MVC"}
~~~

Status là 200 OK; headers có thể thay đổi theo phiên bản và cấu hình. Điều quan sát được là request đã được server tiếp nhận, Servlet container chuyển tới Spring MVC, controller được gọi và kết quả Java được serialize thành JSON.

Có thể đóng gói rồi chạy cùng ứng dụng:

~~~bash
mvn package
java -jar target/web-runtime-demo-1.0.0.jar
~~~

Cả hai cách đều chạy ứng dụng cùng server nhúng. Khác biệt là một cách chạy qua Maven plugin, cách còn lại chạy executable JAR đã đóng gói.

## 11. Khi nào chọn JAR nhúng và khi nào chọn WAR?

| Tiêu chí | Executable JAR + embedded server | WAR + external Servlet container |
|---|---|---|
| Khởi động server | Spring Boot khởi động server nhúng | Môi trường vận hành khởi động server |
| Đơn vị triển khai | Một artifact có app và dependency | WAR được triển khai vào container |
| Vận hành | Mỗi instance thường là một tiến trình app riêng | Có thể nhiều web application trên một container |
| Cấu hình server | Thường nằm cùng cấu hình ứng dụng/biến môi trường | Một phần cấu hình thuộc container bên ngoài |
| Phù hợp | Container/Kubernetes, triển khai độc lập, pipeline đơn giản | Hệ thống đã chuẩn hóa external container hoặc có yêu cầu vận hành tương ứng |

JAR nhúng là lựa chọn phổ biến của Spring Boot vì đóng gói và chạy độc lập. WAR vẫn hữu ích khi hạ tầng yêu cầu triển khai vào Servlet container dùng chung. Chọn theo môi trường vận hành, quy trình nâng cấp, quan sát, bảo mật và trách nhiệm quản trị server.

## 12. Kiểm thử các lớp runtime

Mỗi kiểu kiểm thử chứng minh một phần khác nhau:

- **Unit test:** kiểm tra service/domain mà không khởi động web server. Phù hợp cho nghiệp vụ thuần.
- **MockMvc:** gửi request qua Spring MVC và các filter đã tích hợp trong test context mà không cần mở socket thật. Hữu ích để kiểm tra mapping, validation, security filter và response.
- **@SpringBootTest với WebEnvironment.RANDOM_PORT:** khởi động application context cùng server thật trên port ngẫu nhiên; kiểm tra tích hợp HTTP, connector và cấu hình runtime gần thực tế hơn.
- **End-to-end test:** chạy ứng dụng trong môi trường triển khai tương tự production để kiểm tra reverse proxy, TLS termination, context path, health check và network policy.

Ví dụ kiểm thử HTTP với server thật cần khai báo test dependency phù hợp và dùng port được inject từ @LocalServerPort. Không hard-code port 8080 trong test vì có thể trùng port hoặc môi trường CI không cho phép.

Nếu ứng dụng khởi động nhưng request trả 404, hãy phân biệt lỗi route/controller mapping với lỗi context path hoặc reverse proxy. Nếu port không mở, kiểm tra startup log, port conflict, bind address và trạng thái web server trước khi điều tra controller.

## 13. Chẩn đoán sự cố theo đúng lớp

| Triệu chứng | Lớp nên kiểm tra trước | Ví dụ nguyên nhân |
|---|---|---|
| Ứng dụng không mở được port | Boot startup / server | Server không tạo được, port đang được dùng, bind address sai |
| Server nhận request nhưng 404 | Context path / Servlet mapping / Spring MVC | Sai URL, controller chưa được scan, mapping khác dự kiến |
| 401 hoặc 403 | Filter/security chain | Request bị chặn bởi xác thực, phân quyền hoặc CSRF |
| Controller chạy nhưng dependency null/không tìm thấy bean | Spring container | Bean chưa được scan, thiếu cấu hình, nhiều bean không rõ lựa chọn |
| JSON không đúng format | Spring MVC message conversion | Thiếu converter, content negotiation hoặc DTO mapping |
| Request chậm khi tải tăng | Server pool / blocking work / database | Thread pool cạn, truy vấn chậm, gọi dịch vụ blocking |
| Chạy IDE được nhưng JAR lỗi | Packaging/runtime config | Thiếu resource, profile/environment khác, dependency scope sai |
| WAR chạy khác JAR | External container integration | Servlet version, context path, classloader hoặc cấu hình server khác |

Cách điều tra hiệu quả là xác định request dừng ở đâu: chưa tới server, ở filter, ở DispatcherServlet, ở controller/service hay trong dependency bên ngoài. Dùng log có cấu trúc, request correlation ID, health/readiness endpoint và metrics để phân biệt các lớp.

## 14. Tổng kết kiến thức

- **Ứng dụng** định nghĩa endpoint, bean, cấu hình và nghiệp vụ.
- **Spring Framework** quản lý object/dependency và cung cấp Spring MVC để ánh xạ HTTP request vào controller.
- **Spring Boot** bootstrap ApplicationContext, áp dụng auto-configuration, đọc cấu hình và tích hợp server nhúng.
- **Web server/Servlet container** mở port, nhận HTTP, quản lý filter/servlet/thread và gửi response.
- DispatcherServlet là Servlet của Spring MVC, không phải web server.
- Với JAR nhúng, app và server chạy trong cùng JVM; với WAR, container bên ngoài sở hữu lifecycle của server.
- Request MVC đi từ connector/container qua filter chain, tới DispatcherServlet, controller, service rồi trở về qua message converter.
- Chọn đúng Servlet hay Reactive stack dựa trên mô hình xử lý và dependency thực tế.

Khi debug hoặc thiết kế runtime, luôn xác định rõ thành phần nào đang chịu trách nhiệm cho hành vi quan sát được. Điều đó giúp thay đổi đúng lớp, tránh thêm cấu hình ở controller để sửa lỗi server, hoặc thay server chỉ để xử lý một lỗi mapping của Spring MVC.

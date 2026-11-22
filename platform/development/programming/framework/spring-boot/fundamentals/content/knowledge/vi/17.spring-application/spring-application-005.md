# WebApplicationType NONE, SERVLET, REACTIVE

`SpringApplication` là điểm khởi động phổ biến của ứng dụng Spring Boot. Khi tạo application context, Spring Boot cần xác định ứng dụng sẽ chạy theo mô hình nào: không phải web application, web dựa trên Servlet hay web reactive. Lựa chọn này được biểu diễn bằng enum `WebApplicationType` với ba giá trị:

- **`NONE`**: ứng dụng không chạy như web application và không khởi động embedded web server.
- **`SERVLET`**: ứng dụng web dựa trên Servlet API, thường dùng Spring MVC.
- **`REACTIVE`**: ứng dụng web theo mô hình reactive, thường dùng Spring WebFlux.

Ba giá trị này quyết định loại `ApplicationContext`, cách Spring Boot cấu hình web infrastructure và cách server được khởi động. Chúng không đơn thuần là ba lựa chọn cú pháp cho controller. Chọn sai có thể khiến ứng dụng không tạo HTTP endpoint, khởi động nhầm loại server context hoặc không có request handling stack mà code đang cần.

## 1. WebApplicationType trong quá trình khởi động

Trong ứng dụng Spring Boot, `SpringApplication.run(...)` khởi tạo và làm mới application context. Trước khi context sẵn sàng, Boot cần biết loại ứng dụng để chọn hạ tầng tương ứng.

```java
@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Nếu không chỉ định rõ, Spring Boot cố gắng **suy luận WebApplicationType từ classpath**. Sau khi chọn loại, Boot tạo loại context phù hợp và áp dụng các auto-configuration tương ứng.

```text
SpringApplication.run(...)
          │
          ▼
Xác định WebApplicationType
          │
     ┌────┼─────────┐
     ▼    ▼         ▼
    NONE SERVLET  REACTIVE
     │    │         │
     ▼    ▼         ▼
Non-web Servlet   Reactive
context  web      web context
         context
     │    │         │
     ▼    ▼         ▼
Runner  Servlet   Reactive
        server    server
        startup   startup
```

Loại ứng dụng ảnh hưởng đến cách tạo context ngay từ đầu. Đây là lý do nên xác định mô hình web của ứng dụng trước khi cấu hình controller, server hoặc dependency liên quan.

## 2. NONE: ứng dụng không chạy như web application

`WebApplicationType.NONE` phù hợp với chương trình dùng Spring container nhưng không cần nhận HTTP request qua embedded web server.

Các trường hợp phổ biến:

- Batch job đọc dữ liệu, xử lý và kết thúc.
- Command-line application.
- Worker tiêu thụ message từ queue hoặc broker.
- Scheduler chạy tác vụ định kỳ.
- Tool migration hoặc import/export dữ liệu.
- Ứng dụng khởi tạo Spring context để dùng dependency injection, configuration properties và lifecycle callback nhưng không cung cấp HTTP endpoint.

Ví dụ:

```java
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.SpringApplication;

@SpringBootApplication
public class BatchApplication {
    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BatchApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }
}
```

Khi chạy theo kiểu NONE, Spring Boot tạo non-web application context. Ứng dụng vẫn có bean, dependency injection, configuration properties, event và lifecycle của Spring. Nó chỉ không tạo web server context để phục vụ HTTP.

### 2.1. NONE vẫn dùng Spring container

Một hiểu nhầm thường gặp là NONE đồng nghĩa với chương trình Java thuần không có Spring. Thực tế, Spring container vẫn hoạt động đầy đủ trong phạm vi cần thiết.

Ví dụ một tác vụ batch:

```java
@Service
public class ImportService {
    public void importData() {
        System.out.println("Importing records...");
        // Đọc file, validate và ghi dữ liệu.
    }
}
```

```java
@Component
public class ImportRunner implements CommandLineRunner {
    private final ImportService importService;

    public ImportRunner(ImportService importService) {
        this.importService = importService;
    }

    @Override
    public void run(String... args) {
        importService.importData();
    }
}
```

Khi application context khởi động, Spring tạo `ImportService` và `ImportRunner`, inject dependency rồi gọi `CommandLineRunner.run(...)`. Tác vụ có thể chạy mà không cần controller hoặc HTTP server.

`ApplicationRunner` cũng có vai trò tương tự nhưng nhận `ApplicationArguments` đã được phân tích:

```java
@Component
public class StartupTask implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Application started without a web server");
    }
}
```

Có thể dùng `CommandLineRunner` hoặc `ApplicationRunner` cho công việc sau khi context được khởi tạo. Nếu tác vụ cần chạy dài, cần quản lý shutdown, retry và trạng thái hoàn tất phù hợp; NONE không tự quyết định khi nào một batch job nên thoát.

### 2.2. NONE không khởi động embedded web server

Với NONE, Spring Boot không tạo Servlet web server context hoặc Reactive web server context. Vì vậy:

- Không có embedded Tomcat/Jetty/Undertow được khởi động chỉ để phục vụ ứng dụng.
- Không có `DispatcherServlet` làm front controller cho Spring MVC.
- Không có `DispatcherHandler` làm request handler của WebFlux server.
- Các endpoint controller không được phục vụ qua HTTP trong application context đó.

Nếu ứng dụng có web dependency trên classpath nhưng đặt rõ NONE, dependency vẫn có thể nằm trong runtime classpath. Tuy nhiên, có class web trên classpath không đồng nghĩa web server sẽ được khởi động.

### 2.3. NONE phù hợp với worker và batch

Worker nhận message có thể dùng Spring Boot để cấu hình broker client và service:

```java
@SpringBootApplication
public class MessageWorkerApplication {
    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(MessageWorkerApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.run(args);
    }
}
```

Worker vẫn có thể duy trì kết nối tới message broker, chạy listener container hoặc scheduler. NONE chỉ nói rằng ứng dụng không phải web application theo mô hình Boot; nó không có nghĩa ứng dụng không dùng network hoặc không có kết nối bên ngoài.

## 3. SERVLET: web application dựa trên Servlet API

`WebApplicationType.SERVLET` dùng cho ứng dụng web dựa trên Servlet API. Đây là mô hình quen thuộc của Spring MVC.

Các thành phần thường gặp:

- Servlet API và Servlet web application context.
- `DispatcherServlet` của Spring MVC.
- Controller dùng `@Controller` hoặc `@RestController`.
- Embedded server như Tomcat, Jetty hoặc Undertow khi dependency và cấu hình phù hợp.
- Servlet filters, listeners và các thành phần web Servlet khác.

Ví dụ controller:

```java
@RestController
@RequestMapping("/api/orders")
public class OrderController {
    @GetMapping("/{id}")
    public String getOrder(@PathVariable long id) {
        return "Order " + id;
    }
}
```

Trong ứng dụng Servlet web, request HTTP được tiếp nhận bởi Servlet container. Với Spring MVC, `DispatcherServlet` điều phối request tới controller phù hợp.

```text
HTTP request
     │
     ▼
Servlet container
(Tomcat / Jetty / Undertow)
     │
     ▼
DispatcherServlet
     │
     ▼
HandlerMapping
     │
     ▼
Controller method
     │
     ▼
HTTP response
```

### 3.1. Spring MVC và Servlet context

Với kiểu SERVLET, Boot thường tạo `ServletWebServerApplicationContext`. Context này tích hợp Spring container với embedded Servlet web server.

Khi context được refresh, web server được tạo và khởi động theo lifecycle của context. Vì vậy, nếu cấu hình server lỗi hoặc port đã được sử dụng, ứng dụng có thể thất bại trong quá trình startup.

Các property thường dùng:

```properties
server.port=8080
server.servlet.context-path=/shop
```

Ví dụ YAML:

```yaml
server:
  port: 8080
  servlet:
    context-path: /shop
```

Với cấu hình này, endpoint `/api/orders/1` có thể được truy cập qua base path `/shop` và port `8080`, nếu controller và server được cấu hình đúng.

### 3.2. Embedded server và external Servlet container

Spring Boot thường đóng gói embedded server trong executable JAR để có thể chạy bằng:

```bash
java -jar app.jar
```

Ứng dụng Servlet cũng có thể được đóng gói theo kiểu WAR và triển khai vào external Servlet container, tùy cách build và cấu hình. `WebApplicationType.SERVLET` mô tả mô hình Servlet web; nó không bắt buộc chỉ được chạy bằng embedded Tomcat.

### 3.3. Khi nào chọn SERVLET?

Chọn SERVLET khi:

- Ứng dụng dùng Spring MVC.
- API hoặc website dựa trên Servlet request/response.
- Dùng thư viện cần Servlet API, Servlet filter hoặc Servlet container integration.
- Ứng dụng đang có kiến trúc MVC truyền thống và không có lý do chuyển sang reactive server stack.

Spring MVC vẫn có thể xử lý một số kiểu trả về reactive như `Mono` hoặc `Flux`, tùy chức năng và cấu hình. Điều đó không tự biến ứng dụng MVC thành WebFlux application. Kiểu application context và request processing stack vẫn là Servlet nếu Boot chọn SERVLET.

## 4. REACTIVE: web application theo mô hình reactive

`WebApplicationType.REACTIVE` dùng cho ứng dụng web reactive, thường được xây dựng bằng Spring WebFlux.

WebFlux được thiết kế cho mô hình non-blocking và reactive streams. Các thành phần tiêu biểu:

- `DispatcherHandler` làm trung tâm điều phối request của WebFlux.
- `Mono` và `Flux` biểu diễn publisher trong Reactor.
- Reactive server runtime, thường là Reactor Netty theo cấu hình mặc định phổ biến.
- Reactive web application context.
- Các adapter hỗ trợ những server/runtime reactive tương thích.

Ví dụ controller:

```java
@RestController
@RequestMapping("/api/products")
public class ProductController {
    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping("/{id}")
    public Mono<Product> getProduct(@PathVariable String id) {
        return productService.findById(id);
    }
}
```

Ví dụ này giả định `ProductService` cung cấp phương thức trả về `Mono<Product>` và được inject qua constructor.

Luồng xử lý khái quát:

```text
HTTP request
     │
     ▼
Reactive web server
(Reactor Netty hoặc server phù hợp)
     │
     ▼
DispatcherHandler
     │
     ▼
HandlerMapping / HandlerAdapter
     │
     ▼
Reactive controller
     │
     ▼
Mono / Flux publisher
     │
     ▼
Reactive response
```

### 4.1. Reactive application context

Với REACTIVE, Spring Boot tạo `ReactiveWebServerApplicationContext`. Context này tích hợp Spring container với reactive web server.

Không có `DispatcherServlet` làm front controller chính như Spring MVC. WebFlux dùng `DispatcherHandler` cùng các adapter reactive để điều phối request.

Các endpoint vẫn có thể dùng annotation như `@RestController`, `@GetMapping` và `@PostMapping`. Sự khác nhau nằm ở web runtime, request processing model và kiểu dữ liệu trả về/nhận vào.

### 4.2. Reactive không có nghĩa chỉ dùng Reactor Netty

Reactor Netty là lựa chọn phổ biến và mặc định khi phù hợp, nhưng WebFlux có thể chạy trên các server khác được hỗ trợ, tùy dependency và cấu hình.

Vì vậy, đừng đồng nhất:

- REACTIVE với duy nhất Reactor Netty.
- SERVLET với duy nhất Tomcat.
- NONE với việc không có bất kỳ dependency network nào.

`WebApplicationType` mô tả loại web application context; server cụ thể được quyết định bởi dependency và cấu hình runtime.

### 4.3. Reactive không tự làm mọi code non-blocking

Chọn REACTIVE không tự biến JDBC blocking call, file I/O blocking hoặc method đồng bộ thành non-blocking.

Ví dụ không phù hợp nếu chạy blocking call trực tiếp trên event-loop thread:

```java
@GetMapping("/report")
public Mono<Report> getReport() {
    Report report = blockingRepository.loadReport();
    return Mono.just(report);
}
```

Nếu `blockingRepository.loadReport()` thực hiện I/O blocking, nó có thể chặn thread đang xử lý reactive pipeline. Cần dùng reactive data access phù hợp hoặc cô lập blocking work trên scheduler/executor thích hợp, đồng thời đánh giá giới hạn tài nguyên.

Reactive là một mô hình lập trình xuyên suốt. Chỉ đổi enum sang REACTIVE mà giữ toàn bộ code blocking không tự mang lại lợi ích non-blocking.

## 5. So sánh NONE, SERVLET và REACTIVE

| Tiêu chí | NONE | SERVLET | REACTIVE |
|---|---|---|---|
| Loại ứng dụng | Non-web | Servlet web | Reactive web |
| Application context thường dùng | Non-web context, ví dụ `AnnotationConfigApplicationContext` | `ServletWebServerApplicationContext` | `ReactiveWebServerApplicationContext` |
| Embedded web server | Không khởi động | Có khi cấu hình server phù hợp | Có khi cấu hình reactive server phù hợp |
| Request handling | Không có HTTP server của Boot | Servlet API, thường Spring MVC | Reactive web stack, thường Spring WebFlux |
| Front controller/dispatcher | Không có dispatcher web | `DispatcherServlet` | `DispatcherHandler` |
| Kiểu controller thường gặp | Không phục vụ HTTP endpoint | MVC controller, có thể trả object hoặc kiểu hỗ trợ | WebFlux controller, thường trả `Mono`/`Flux` |
| Use case | Batch, CLI, worker, scheduler | Website, REST API MVC, Servlet integration | API reactive, streaming, non-blocking I/O |
| Điều kiện chính | Không cần web runtime | Cần Servlet web runtime | Cần reactive web runtime |

Không có lựa chọn nào luôn tốt hơn. Hãy chọn dựa trên mô hình request handling và dependency thực tế của ứng dụng.

## 6. Spring Boot tự suy luận WebApplicationType từ classpath

Nếu không chỉ định loại ứng dụng, Spring Boot kiểm tra các class quan trọng trên classpath để suy luận.

Ở mức khái quát:

- Nếu có WebFlux nhưng không có Spring MVC hoặc Jersey Servlet stack tương ứng, Boot thường chọn REACTIVE.
- Nếu có Servlet web stack phù hợp, Boot chọn SERVLET.
- Nếu không tìm thấy dấu hiệu của Servlet hoặc reactive web application, Boot chọn NONE.

Một điểm đáng chú ý: **nếu Spring MVC và Spring WebFlux cùng có trên classpath, Spring MVC thường được ưu tiên và Boot chọn SERVLET**. Một số ứng dụng MVC thêm dependency WebFlux chỉ để dùng `WebClient`, không có ý định chuyển toàn bộ server sang reactive.

Bảng tình huống minh họa:

| Classpath/đặc điểm | Loại thường được suy luận |
|---|---|
| Không có Servlet web stack và không có WebFlux | NONE |
| Có Spring MVC/Servlet stack | SERVLET |
| Có WebFlux và không có MVC/Jersey Servlet stack | REACTIVE |
| Có cả Spring MVC và WebFlux | SERVLET theo ưu tiên mặc định |

Đây là quy tắc suy luận theo classpath, không phải kiểm tra nội dung controller. Một lớp có `@RestController` không đủ để quyết định ứng dụng là SERVLET hay REACTIVE.

### 6.1. Vì sao ứng dụng có WebClient vẫn có thể là SERVLET?

`WebClient` là HTTP client reactive. Ứng dụng Spring MVC có thể dùng `WebClient` để gọi API bên ngoài nhưng vẫn nhận request bằng Servlet stack.

Ví dụ:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

Nếu cả hai starter có mặt, Boot thường chọn SERVLET vì MVC có ưu tiên theo quy tắc suy luận. Bạn vẫn có thể sử dụng `WebClient` ở phía client mà không cần biến server thành WebFlux.

Nếu thực sự muốn server reactive, hãy xác định dependency, loại ứng dụng và cấu hình tường minh. Không nên thêm WebFlux starter rồi mặc định cho rằng Boot sẽ tự chuyển sang REACTIVE.

## 7. Chọn loại ứng dụng tường minh bằng Java

Có thể đặt loại trực tiếp trên `SpringApplication`:

```java
@SpringBootApplication
public class WorkerApplication {
    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(WorkerApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }
}
```

Các giá trị khác:

```java
application.setWebApplicationType(WebApplicationType.SERVLET);
```

```java
application.setWebApplicationType(WebApplicationType.REACTIVE);
```

Cách này hữu ích khi muốn quyết định rõ từ code bootstrap, ví dụ cùng một module có các entry point khác nhau cho worker và web server.

### 7.1. Dùng SpringApplicationBuilder

`SpringApplicationBuilder` cũng hỗ trợ lựa chọn web application type:

```java
new SpringApplicationBuilder(DemoApplication.class)
        .web(WebApplicationType.NONE)
        .run(args);
```

Tương tự, có thể truyền SERVLET hoặc REACTIVE.

Không nên cấu hình nhiều entry point cùng chạy cho một ứng dụng nếu không có mục đích rõ ràng. Hãy bảo đảm class nguồn, property và builder được sử dụng nhất quán.

## 8. Chọn loại ứng dụng bằng property

Spring Boot cung cấp property:

```properties
spring.main.web-application-type=none
```

Các giá trị có thể dùng là `none`, `servlet` và `reactive`.

YAML:

```yaml
spring:
  main:
    web-application-type: none
```

Có thể thay đổi theo profile:

```yaml
# application-worker.yml
spring:
  main:
    web-application-type: none
```

```yaml
# application-web.yml
spring:
  main:
    web-application-type: servlet
```

Sau đó kích hoạt profile phù hợp:

```bash
java -jar app.jar --spring.profiles.active=worker
```

Hoặc:

```bash
java -jar app.jar --spring.profiles.active=web
```

Property này phù hợp khi cùng một artifact có thể được chạy trong các vai trò khác nhau và quyết định được đưa ra từ môi trường triển khai.

Nếu vừa đặt property vừa gọi `setWebApplicationType(...)` trong code, hãy kiểm tra kết quả theo phiên bản Boot và cách bootstrap đang dùng. Để tránh cấu hình khó hiểu, nên có một nguồn quyết định rõ ràng và kiểm tra startup log/context type thực tế.

## 9. Dependency starter ảnh hưởng đến việc suy luận

Các starter phổ biến:

| Starter | Stack chính | WebApplicationType thường gặp khi dùng riêng |
|---|---|---|
| `spring-boot-starter` | Spring core/Boot nền tảng | NONE |
| `spring-boot-starter-web` | Spring MVC, Servlet | SERVLET |
| `spring-boot-starter-webflux` | Spring WebFlux | REACTIVE |
| `spring-boot-starter-web` và `spring-boot-starter-webflux` | Có cả MVC và WebFlux | SERVLET theo ưu tiên mặc định |

Tên artifact và cách quản lý dependency có thể thay đổi theo dòng Spring Boot; hãy dùng starter được quản lý bởi BOM/plugin của phiên bản dự án.

Một dependency transitive cũng có thể đưa Servlet hoặc WebFlux indicator class vào classpath. Khi loại ứng dụng được suy luận ngoài dự kiến, kiểm tra runtime dependency graph thay vì chỉ nhìn phần dependencies trực tiếp.

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Với Maven:

```bash
./mvnw dependency:tree
```

Tìm các starter và thư viện web liên quan. Mục tiêu là xác định class nào khiến Boot suy luận SERVLET hoặc REACTIVE.

## 10. Chọn SERVLET khi có cả MVC và WebFlux

Đây là tình huống thường gặp:

- Ứng dụng dùng `spring-boot-starter-web` để phục vụ REST API bằng Spring MVC.
- Ứng dụng thêm `spring-boot-starter-webflux` để dùng `WebClient`.
- Boot thấy cả hai stack trên classpath.

Theo mặc định, Boot ưu tiên MVC và chọn SERVLET. Đây thường là behavior mong muốn vì thêm WebFlux để có client không đồng nghĩa muốn thay server stack.

Nếu cần WebFlux server thực sự, có thể chọn rõ:

```java
@SpringBootApplication
public class ReactiveApplication {
    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ReactiveApplication.class);

        app.setWebApplicationType(WebApplicationType.REACTIVE);
        app.run(args);
    }
}
```

Tuy nhiên, chọn REACTIVE không đảm bảo mọi bean Servlet/MVC trong ứng dụng trở nên tương thích. Cần xem lại dependency, auto-configuration và các thư viện chỉ hoạt động với Servlet API. Với ứng dụng reactive server, nên giữ classpath và integration theo đúng mô hình WebFlux.

## 11. NONE với dependency web vẫn có thể có bean không mong đợi

Giả sử project có `spring-boot-starter-web` nhưng muốn chạy batch. Bạn có thể đặt:

```properties
spring.main.web-application-type=none
```

Điều này chọn non-web context và không khởi động embedded Servlet server. Tuy nhiên, dependency web vẫn nằm trên classpath và các class Java của nó vẫn có thể được load nếu code tham chiếu.

Ngoài ra, các bean do component scan hoặc cấu hình ứng dụng tự khai báo vẫn có thể được đăng ký. Nếu ứng dụng có component yêu cầu một bean chỉ có trong Servlet web context, startup có thể thất bại.

Khi chuyển app từ SERVLET sang NONE:

1. Kiểm tra các bean có dependency vào `ServletContext`, `HttpServletRequest` hoặc web-specific scope.
2. Kiểm tra configuration có `@ConditionalOnWebApplication` hoặc điều kiện tương tự.
3. Đảm bảo runner/worker không phụ thuộc controller hoặc server lifecycle.
4. Nếu batch module không cần web dependencies, cân nhắc tách dependency/module để classpath rõ hơn.

**NONE không phải bộ lọc loại bỏ tất cả web classes khỏi classpath.** Nó chọn non-web application context.

## 12. Conditional configuration theo loại web application

Spring Boot cung cấp condition để chỉ áp dụng cấu hình cho loại web application nhất định.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(
    type = ConditionalOnWebApplication.Type.SERVLET
)
public class ServletOnlyConfiguration {
    @Bean
    public ServletFeature servletFeature() {
        return new ServletFeature();
    }
}
```

Tương tự, có thể kiểm tra reactive:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(
    type = ConditionalOnWebApplication.Type.REACTIVE
)
public class ReactiveOnlyConfiguration {
    @Bean
    public ReactiveFeature reactiveFeature() {
        return new ReactiveFeature();
    }
}
```

Với cấu hình chỉ dùng cho non-web:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnNotWebApplication
public class WorkerOnlyConfiguration {
    @Bean
    public WorkerFeature workerFeature() {
        return new WorkerFeature();
    }
}
```

Các condition này hữu ích khi viết thư viện dùng chung cho nhiều kiểu ứng dụng. Ví dụ, một starter có thể cung cấp Servlet filter trong SERVLET mode và reactive web filter trong REACTIVE mode.

Không nên chỉ kiểm tra classpath bằng `@ConditionalOnClass` nếu ý định thực sự là phân biệt loại application context. Một class có thể có mặt trên classpath nhưng web application type đang được đặt tường minh thành NONE.

## 13. Lifecycle của server theo từng loại

Với NONE, Spring tạo non-web context, khởi tạo bean và chạy các runner. Không có embedded web server để nhận HTTP request. Ứng dụng kết thúc khi lifecycle của chương trình kết thúc, ví dụ sau khi runner hoàn thành và không còn thread/tài nguyên giữ tiến trình sống.

Với SERVLET, context tích hợp Servlet web server. Khi context refresh, server được tạo và khởi động; khi context đóng bình thường, server được dừng theo lifecycle.

Với REACTIVE, context tích hợp reactive web server. Server được khởi động trong quá trình refresh và dừng khi context đóng.

```text
                         ApplicationContext
                                  │
                ┌─────────────────┼─────────────────┐
                ▼                 ▼                 ▼
               NONE            SERVLET           REACTIVE
                │                 │                 │
         Tạo non-web       Tạo Servlet web    Tạo Reactive web
            context             context            context
                │                 │                 │
         Khởi tạo bean      Khởi động server   Khởi động server
                │                 │                 │
         Run Application   Nhận HTTP request  Nhận HTTP request
         Runner/Command    qua Servlet stack  qua reactive stack
                │                 │                 │
         Không có web      Đóng context:      Đóng context:
         server lifecycle  dừng server        dừng server
```

Không nên dùng `CommandLineRunner` như một cơ chế chờ server chạy mãi trong NONE. Nếu worker cần chạy liên tục, hãy dùng listener/scheduler hoặc lifecycle component phù hợp, đồng thời thiết kế shutdown graceful.

## 14. Ảnh hưởng tới controller và endpoint

Annotation controller có thể được compile bình thường trong cả ba loại ứng dụng, nhưng chỉ SERVLET hoặc REACTIVE context có web infrastructure tương ứng mới phục vụ HTTP endpoint.

| Code/controller | NONE | SERVLET | REACTIVE |
|---|---|---|---|
| `@RestController` | Không có HTTP server để nhận request | Spring MVC xử lý nếu cấu hình phù hợp | WebFlux xử lý nếu cấu hình phù hợp |
| `@GetMapping` | Không tạo endpoint HTTP phục vụ request | Mapping trong MVC | Mapping trong WebFlux |
| `HttpServletRequest` | Không có request Servlet đang active | Có trong Servlet request lifecycle | Không phải API request chính của WebFlux |
| `Mono`/`Flux` return type | Không tự tạo reactive HTTP endpoint | MVC có thể hỗ trợ một số reactive return types | WebFlux dùng reactive pipeline làm mô hình chính |

Nếu một bean trong NONE gọi code yêu cầu `HttpServletRequest`, không có request context để cung cấp đối tượng đó. Tương tự, không nên inject Servlet-specific component vào reactive application nếu không có Servlet web context phù hợp.

## 15. WebApplicationType trong kiểm thử

Spring Boot Test cung cấp các chế độ web environment khác nhau. Cần phân biệt **loại application** với **cách test tạo server**.

Ví dụ test không cần web environment:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class BatchServiceTests {
    // Test service và Spring beans mà không cần web server.
}
```

`WebEnvironment.NONE` phù hợp với test không cần web server. Nếu cần test Servlet hoặc reactive endpoint, có thể chọn môi trường test phù hợp như `MOCK`, `RANDOM_PORT` hoặc `DEFINED_PORT`, tùy mục tiêu.

Ví dụ test chạy embedded server trên port ngẫu nhiên:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ApiIntegrationTests {
    // Gửi HTTP request tới server do test khởi động.
}
```

`MOCK` tạo web application context giả lập phù hợp với stack được phát hiện/configured nhưng không khởi động embedded server thực. `RANDOM_PORT` và `DEFINED_PORT` khởi động server thật trong test context.

Khi viết test, hãy chọn chế độ theo thứ cần kiểm tra:

- Unit test service thuần Java: thường không cần Spring context.
- Test dependency injection/configuration không cần HTTP: NONE hoặc context runner phù hợp.
- Test controller MVC: dùng MockMvc hoặc Servlet mock web environment.
- Test WebFlux: dùng WebTestClient và reactive web test setup.
- Test end-to-end server thật: dùng RANDOM_PORT/DEFINED_PORT.

### 15.1. Kiểm tra loại ApplicationContext

Có thể quan sát context type trong integration test hoặc debug session:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(DemoApplication.class, args);

System.out.println(context.getClass().getName());
```

Đoạn trên là ví dụ quan sát; context được trả về bởi `SpringApplication.run(...)` chính là context ứng dụng đã khởi tạo.

Các class thường gặp:

- Non-web context: `AnnotationConfigApplicationContext` hoặc một non-web context implementation phù hợp.
- Servlet: `ServletWebServerApplicationContext`.
- Reactive: `ReactiveWebServerApplicationContext`.

Tên implementation cụ thể có thể thay đổi theo phiên bản hoặc cách custom application context. Dùng context type như một dấu hiệu debug, không coi class name là API contract cho business logic.

## 16. Lỗi thường gặp khi chọn WebApplicationType

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Ứng dụng có controller nhưng không truy cập HTTP được | WebApplicationType là NONE hoặc không có web server runtime phù hợp. | Kiểm tra `spring.main.web-application-type` và context type. |
| Ứng dụng dự định WebFlux nhưng lại khởi động MVC/Tomcat | MVC/Servlet stack có trên classpath và được ưu tiên khi suy luận. | Kiểm tra runtime dependency tree; chọn REACTIVE tường minh nếu đúng mục tiêu và kiểm tra compatibility. |
| Batch app vẫn cố khởi động web server | Classpath khiến Boot suy luận SERVLET/REACTIVE. | Đặt NONE bằng property hoặc `setWebApplicationType`. |
| Bean yêu cầu `ServletContext` không được tạo trong NONE | Non-web context không cung cấp Servlet web infrastructure. | Tách cấu hình Servlet bằng `@ConditionalOnWebApplication`. |
| WebFlux code bị lỗi do blocking call | REACTIVE không tự biến API blocking thành non-blocking. | Dùng reactive client/repository hoặc cô lập blocking work. |
| Port đã được sử dụng | SERVLET/REACTIVE server không bind được port. | Kiểm tra `server.port`, tiến trình đang listen và log startup. |
| Test không có endpoint dù controller compile được | Test context dùng NONE hoặc không tạo web environment. | Chọn `@SpringBootTest` web environment phù hợp. |
| App có cả MVC và WebFlux nhưng behavior không như mong muốn | Boot chọn SERVLET theo mặc định hoặc dependency stack không đồng nhất. | Kiểm tra classpath và loại application được chọn. |

### 16.1. Không nên sửa lỗi bằng cách loại starter một cách mù quáng

Nếu ứng dụng khởi động sai loại, hãy kiểm tra:

1. Dependency runtime nào có mặt.
2. Boot suy luận loại nào.
3. Property hoặc code có override loại đó không.
4. Các auto-configuration nào được áp dụng.
5. Context type và server thực tế được tạo.

Sau đó mới quyết định gỡ starter, đặt explicit WebApplicationType hoặc tách module. Một starter có thể cung cấp API cần thiết ngay cả khi server stack không được dùng; gỡ nó có thể làm mất các class khác.

## 17. Ví dụ: một artifact có hai vai trò chạy

Một project có thể chứa service nghiệp vụ dùng chung, nhưng có hai entry point: web application và batch worker.

Cấu trúc minh họa:

```text
com.example.platform/
├── shared/
│   └── OrderService.java
├── web/
│   ├── WebApplication.java
│   └── OrderController.java
└── worker/
    ├── WorkerApplication.java
    └── OrderImportRunner.java
```

Web entry point:

```java
package com.example.platform.web;

@SpringBootApplication(scanBasePackages = "com.example.platform")
public class WebApplication {
    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(WebApplication.class);

        app.setWebApplicationType(WebApplicationType.SERVLET);
        app.run(args);
    }
}
```

Worker entry point:

```java
package com.example.platform.worker;

@SpringBootApplication(scanBasePackages = "com.example.platform")
public class WorkerApplication {
    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(WorkerApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.run(args);
    }
}
```

Cả hai có thể dùng `OrderService` chung. Tuy nhiên, không phải mọi bean đều nên được scan và khởi tạo trong cả hai context. Controller, Servlet filter và request-scoped component nên được điều kiện hóa hoặc tổ chức package/configuration để chỉ nạp trong web application. Runner của worker cũng nên được điều kiện hóa để không chạy trong web process.

Ví dụ điều kiện cho cấu hình web:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnWebApplication(
    type = ConditionalOnWebApplication.Type.SERVLET
)
public class WebOnlyConfiguration {
    // Các bean chỉ cần trong Servlet application.
}
```

Với kiến trúc production, tách module hoặc tách artifact có thể giúp dependency graph rõ hơn. Ví dụ này minh họa khả năng chia sẻ code; không có nghĩa hai main class luôn nên được đóng gói và scan toàn bộ cùng nhau.

## 18. Nguyên tắc lựa chọn

Chọn `NONE` khi ứng dụng chỉ cần Spring container để chạy tác vụ, worker hoặc command-line flow và không cần HTTP server.

Chọn `SERVLET` khi ứng dụng phục vụ HTTP qua Servlet stack, đặc biệt với Spring MVC và các thư viện Servlet.

Chọn `REACTIVE` khi ứng dụng được thiết kế cho reactive web stack, thường là Spring WebFlux, và các dependency/request handling phù hợp với mô hình non-blocking.

Trước khi quyết định, hãy trả lời:

- Ứng dụng có nhận HTTP request không?
- Nếu có, request đi qua Servlet API hay reactive web stack?
- Runtime dependency graph có cả MVC và WebFlux không?
- Ứng dụng có bean phụ thuộc ServletContext, HttpServletRequest hoặc reactive context không?
- Có cần một artifact chạy ở nhiều vai trò khác nhau không?
- Loại ứng dụng được suy luận tự động hay nên đặt tường minh?

## 19. Bài tập thực hành

### Bài tập A — Chạy ứng dụng NONE

1. Tạo Spring Boot app có một service và một `CommandLineRunner`.
2. Đặt `spring.main.web-application-type=none`.
3. Chạy ứng dụng và quan sát runner.
4. Kiểm tra không có embedded web server được khởi động.
5. Thêm một controller và giải thích vì sao endpoint không được phục vụ HTTP.

### Bài tập B — Chạy Servlet application

1. Thêm dependency Spring MVC phù hợp.
2. Tạo `@RestController` với một GET endpoint.
3. Chạy ứng dụng theo SERVLET.
4. Quan sát log embedded server và truy cập endpoint.
5. Thay đổi `server.port` rồi xác nhận port mới.

### Bài tập C — Chạy Reactive application

1. Tạo project dùng WebFlux.
2. Tạo controller trả `Mono<String>` hoặc `Flux<String>`.
3. Chọn REACTIVE và chạy server.
4. Quan sát context/server runtime.
5. Thử thêm một blocking call và tìm cách xử lý phù hợp với reactive model.

### Bài tập D — Thử classpath detection

1. Chạy project chỉ có starter nền tảng.
2. Thêm Spring MVC starter.
3. Thêm WebFlux starter cùng MVC.
4. Quan sát loại Boot suy luận trong từng trường hợp.
5. Dùng `setWebApplicationType(REACTIVE)` và so sánh kết quả, đồng thời kiểm tra compatibility của các bean.

### Bài tập E — Hai vai trò trong cùng project

Tạo một web entry point và một worker entry point cùng dùng service nghiệp vụ. Chọn SERVLET cho web, NONE cho worker. Điều kiện hóa các bean chỉ dành cho web/worker và kiểm tra mỗi context chỉ khởi tạo những thành phần cần thiết.

### Bài tập F — Kiểm thử web environment

Viết một test dùng `WebEnvironment.NONE` để kiểm tra service, một test MVC dùng MockMvc và một test reactive dùng WebTestClient. So sánh context và request handling giữa các test.

## 20. Ghi nhớ

1. `WebApplicationType.NONE` tạo non-web application context và không khởi động embedded web server.
2. `WebApplicationType.SERVLET` tạo Servlet web application context, thường dùng với Spring MVC và `DispatcherServlet`.
3. `WebApplicationType.REACTIVE` tạo reactive web application context, thường dùng với Spring WebFlux và `DispatcherHandler`.
4. Spring Boot thường suy luận loại từ classpath; nếu MVC và WebFlux cùng có mặt, SERVLET thường được ưu tiên.
5. Có thể chọn tường minh bằng `SpringApplication.setWebApplicationType(...)`, `SpringApplicationBuilder.web(...)` hoặc property `spring.main.web-application-type`.
6. NONE vẫn có Spring beans, dependency injection, runners và lifecycle; nó chỉ không chạy web server.
7. REACTIVE không tự chuyển blocking code thành non-blocking.
8. Loại application context ảnh hưởng tới web-specific beans, scope và điều kiện auto-configuration.
9. Dependency vẫn có thể nằm trên classpath sau khi chọn NONE; hãy kiểm tra các bean cần Servlet/reactive infrastructure.
10. Test phải chọn web environment phù hợp với loại behavior cần kiểm tra.

Khi đọc log startup hoặc thiết kế entry point, hãy xác định **Spring Boot đang chạy NONE, SERVLET hay REACTIVE**, sau đó đối chiếu context type, dependency graph và web infrastructure được tạo. Chọn đúng loại ngay từ bootstrap giúp controller, server, lifecycle và cấu hình auto-configuration hoạt động theo đúng mô hình của ứng dụng.

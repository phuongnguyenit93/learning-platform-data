# Phân biệt Spring Framework, Spring MVC, Spring WebFlux và Spring Boot

Khi xây dựng ứng dụng Java, bốn tên gọi này thường xuất hiện cùng nhau nhưng chúng **không nằm ở bốn lựa chọn ngang hàng**. Spring Framework là nền tảng; Spring MVC và Spring WebFlux là hai mô hình xây dựng ứng dụng web thuộc Spring Framework; Spring Boot giúp cấu hình, khởi động, đóng gói và vận hành ứng dụng dùng các thành phần ấy.

Hiểu đúng mối quan hệ này giúp chọn công nghệ, đọc dependency, tìm lỗi cấu hình và tránh nhầm giữa cách xử lý HTTP với cách khởi động ứng dụng.

## 1. Bản đồ khái niệm: cái nào chứa cái nào?

~~~text
                          Ứng dụng Java
                                |
                         Spring Framework
                    (IoC/DI, bean, AOP, dữ liệu,
                     transaction, validation, ...)
                                |
                     +----------+-----------+
                     |                      |
               Spring MVC              Spring WebFlux
             (Servlet stack)          (Reactive stack)
                     |                      |
                HTTP API / UI          HTTP API / stream
                     \                      /
                      \                    /
                       Spring Boot (tùy chọn)
              auto-configuration, starter, chạy server,
                  cấu hình ngoài, đóng gói, Actuator
~~~

Sơ đồ trên thể hiện **quan hệ chức năng**, không phải quan hệ kế thừa: Spring Boot không phải lớp nằm bên dưới Spring MVC/WebFlux về mặt mã nguồn. Boot đứng ở lớp **thiết lập và vận hành**, có thể sử dụng MVC, WebFlux, các thư viện Spring khác hoặc không dùng HTTP.

Có thể hình dung:

- **Spring Framework:** bộ nền tảng để ứng dụng quản lý đối tượng và triển khai các mối quan tâm dùng chung.
- **Spring MVC:** cách Spring nhận và xử lý HTTP dựa trên Servlet API.
- **Spring WebFlux:** cách Spring nhận và xử lý HTTP theo mô hình reactive, hỗ trợ I/O không chặn và Reactive Streams.
- **Spring Boot:** cách khởi tạo một ứng dụng Spring ít cấu hình thủ công hơn, chọn cấu hình theo classpath và điều kiện.

Một ứng dụng phổ biến là **Spring Boot + Spring MVC + Spring Framework**. Một ứng dụng khác là **Spring Boot + Spring WebFlux + Spring Framework**. Spring Framework hoặc Spring MVC vẫn có thể dùng **không cần Spring Boot**.

## 2. Bảng so sánh theo trách nhiệm

| Khía cạnh | Spring Framework | Spring MVC | Spring WebFlux | Spring Boot |
|---|---|---|---|---|
| Bản chất | Nền tảng/libraries cho ứng dụng Java | Framework web theo Servlet | Framework web reactive | Công cụ cấu hình và chạy ứng dụng Spring |
| Câu hỏi giải quyết | Bean được tạo, nối và quản lý thế nào? | HTTP request được ánh xạ và xử lý theo Servlet thế nào? | HTTP và luồng dữ liệu bất đồng bộ được xử lý không chặn thế nào? | Làm sao dựng, cấu hình và chạy ứng dụng thuận tiện? |
| Thành phần tiêu biểu | IoC container, DI, AOP, transaction, events | DispatcherServlet, HandlerMapping, HandlerAdapter, HttpMessageConverter | DispatcherHandler, WebHandler, WebFilter, codecs, Reactor | SpringApplication, auto-configuration, starters, embedded server, Actuator |
| Module/thư viện thường thấy | spring-context, spring-beans, spring-core | spring-webmvc (cùng spring-web) | spring-webflux, Reactor | spring-boot, spring-boot-autoconfigure, starters |
| Mô hình xử lý request | Không quy định một mô hình web | Servlet; thường mỗi request sử dụng thread xử lý theo mô hình đồng bộ | Reactive; tác vụ I/O có thể không chặn, event-loop phù hợp | Phụ thuộc web stack được chọn |
| Kiểu controller điển hình | Không bắt buộc có controller HTTP | @Controller, @RestController, @RequestMapping | Cùng annotation controller hoặc RouterFunction/HandlerFunction | Dùng controller của MVC hoặc WebFlux, không định nghĩa thêm một mô hình controller độc lập |
| Chạy trực tiếp web server? | Bản thân container không mặc định mở HTTP server | Cần servlet container và cấu hình triển khai | Cần runtime HTTP/server và cấu hình triển khai | Có thể cấu hình và chạy embedded server tự động |
| Phù hợp | Hầu hết ứng dụng Spring, kể cả ứng dụng không web | REST CRUD, MVC view, JPA/JDBC, thư viện blocking | Streaming, nhiều kết nối I/O chờ đợi, chuỗi non-blocking end-to-end | Hầu hết ứng dụng Spring muốn khởi tạo/triển khai thuận tiện |

**Hai trục quyết định độc lập:**

1. **Có dùng Spring Boot không?** Đây là lựa chọn cách cấu hình, khởi động và vận hành.
2. **Nếu làm web, dùng Spring MVC hay WebFlux?** Đây là lựa chọn mô hình xử lý HTTP.

Không nên đặt câu hỏi “Spring MVC hay Spring Boot?” như hai lựa chọn thay thế trực tiếp.

## 3. Spring Framework: nền tảng chung

Spring Framework cung cấp **IoC container** quản lý các bean. Với **Dependency Injection (DI)**, mã nghiệp vụ khai báo dependency cần dùng, container tạo/tiêm các bean theo cấu hình thay vì từng nơi tự khởi tạo và nối đối tượng. Điều này giúp giảm phụ thuộc trực tiếp, tổ chức cấu hình tập trung và thuận tiện cho kiểm thử.

Ví dụ thành phần ứng dụng dùng chung cho MVC, WebFlux và thậm chí ứng dụng console:

~~~java
package example.core;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Xin chào, " + name;
    }
}
~~~

**Ý nghĩa:** @Service đánh dấu lớp để được đăng ký dưới dạng bean nếu nằm trong phạm vi component scan thích hợp. Spring không tự biến GreetingService thành HTTP endpoint; muốn nhận HTTP phải có thêm cấu hình và web stack, chẳng hạn một controller MVC hoặc WebFlux.

Một số khả năng khác của Spring Framework:

- **@Configuration, @Bean, @Component, @Autowired:** đăng ký/cấu hình và kết nối bean (thực tế thường ưu tiên constructor injection).
- **AOP, transaction:** tách logic xuyên suốt như transaction khỏi mã nghiệp vụ.
- **ApplicationContext, event, resource, conversion, validation:** hỗ trợ vòng đời và hạ tầng ứng dụng.
- **Tích hợp dữ liệu và kiểm thử:** lớp trừu tượng, công cụ kết nối nhiều công nghệ; từng tính năng cần dependency/cấu hình tương ứng.

Spring Framework **không đồng nghĩa** với Spring MVC: ứng dụng chạy batch job, ứng dụng command-line hoặc một thư viện dùng Spring context vẫn là ứng dụng Spring dù không có controller HTTP.

### Spring Framework có cần Spring Boot?

Không. Có thể tự tạo ApplicationContext, đăng ký bean, cấu hình Spring MVC trên servlet container hoặc cấu hình WebFlux server. Tuy nhiên cần chủ động quản lý thư viện, cấu hình cơ sở, tích hợp server và triển khai. Spring Boot phổ biến vì tự động hóa phần lớn công việc lặp lại này.

## 4. Spring MVC: web stack dựa trên Servlet

Spring MVC (Spring Web MVC, module **spring-webmvc**) xây dựng trên **Servlet API**. Điểm vào trung tâm là **DispatcherServlet**, một front controller nhận request rồi phối hợp các thành phần để chọn handler, gắn tham số, chạy controller và tạo HTTP response.

Luồng request đơn giản hóa:

~~~text
Client gửi HTTP
    -> Servlet container (thường Tomcat hoặc Jetty)
    -> Servlet Filter chain
    -> DispatcherServlet
    -> HandlerMapping: tìm controller method
    -> HandlerAdapter: gọi method, binding/validation
    -> Controller -> Service -> Repository
    -> Return value / exception resolution
    -> HttpMessageConverter (JSON, text...) hoặc ViewResolver (HTML view)
    -> HTTP response
~~~

Các chức năng quen thuộc:

- **@GetMapping, @PostMapping, @PathVariable, @RequestParam, @RequestBody:** ánh xạ HTTP và dữ liệu vào tham số.
- **@RestController:** kết hợp @Controller và @ResponseBody; kết quả thường chuyển thành JSON qua message converter khi là object.
- **@Controller:** có thể trả về tên view cùng model để render HTML ở server.
- **@ExceptionHandler, @ControllerAdvice:** xử lý lỗi tập trung.
- **@Valid, conversion, data binding:** xác thực và chuyển đổi dữ liệu khi được cấu hình đúng.
- **Servlet Filter, HandlerInterceptor:** xử lý yêu cầu xuyên suốt theo tầng tương ứng.

MVC hay dùng mô hình **thread-per-request** đối với xử lý đồng bộ: khi code chờ JDBC hoặc HTTP client blocking, thread đang xử lý bị giữ trong lúc chờ. Mô hình này rõ ràng và kết hợp tự nhiên với hệ sinh thái Java blocking, đặc biệt **JPA/Hibernate, JDBC**.

**Không được hiểu MVC là “chỉ có đồng bộ”.** Spring MVC hỗ trợ xử lý bất đồng bộ qua Callable, DeferredResult, CompletableFuture và một số reactive return types. Servlet async có thể giải phóng request thread trong lúc chờ và dispatch tiếp khi có kết quả. Tuy nhiên, hỗ trợ async đó **không tự chuyển toàn bộ tầng Servlet/MVC sang WebFlux non-blocking I/O**.

## 5. Spring WebFlux: web stack reactive

Spring WebFlux (module **spring-webflux**) xuất hiện từ Spring Framework 5 và xây dựng API web theo hợp đồng reactive, hỗ trợ **I/O không chặn** và **Reactive Streams backpressure**. Bộ điều phối tương ứng là **DispatcherHandler**. Ứng dụng WebFlux có thể chạy trên Reactor Netty hoặc server khác được hỗ trợ, trong đó có servlet container qua lớp adapter thích hợp; WebFlux **không bắt buộc chạy trên Netty**.

Hai kiểu khai báo endpoint:

1. **Annotated controller:** dùng @RestController/@GetMapping tương tự cú pháp MVC, nhưng method có thể trả Mono<T>, Flux<T>.
2. **Functional endpoints:** RouterFunction điều hướng request tới HandlerFunction, ví dụ ServerRequest và ServerResponse.

### Mono và Flux nói lên điều gì?

- **Mono<T>:** publisher phát tối đa một phần tử, hoặc hoàn thành rỗng, hoặc báo lỗi.
- **Flux<T>:** publisher có thể phát 0 đến nhiều phần tử, hoàn thành hoặc báo lỗi.
- Publisher mô tả một pipeline; với publisher **cold** thường chỉ thực thi khi có subscriber. Trong WebFlux, framework subscribe vào kết quả controller để tạo response.
- **Backpressure:** bên tiêu thụ có thể báo nhu cầu (demand) lên phía phát dữ liệu trong các đường truyền Reactive Streams hỗ trợ cơ chế đó. Backpressure không có nghĩa mọi nguồn ngoài (ví dụ một API bên thứ ba) tự động chịu điều tiết.

Luồng request đơn giản hóa:

~~~text
Client HTTP
    -> Reactive HTTP server (thường Reactor Netty)
    -> WebFilter / WebHandler
    -> DispatcherHandler
    -> Chọn annotated controller hoặc functional handler
    -> Mono / Flux pipeline
    -> Reactive codec ghi response, theo tín hiệu dữ liệu
    -> Client nhận HTTP response / stream
~~~

WebFlux thường dùng số lượng nhỏ **event-loop threads** để phục vụ nhiều kết nối đang chờ I/O. Điều đó hiệu quả khi phần lớn chuỗi xử lý cũng không chặn, ví dụ WebClient và driver database reactive. Một request vẫn có thể đi qua các scheduler/thread khác tùy thao tác và cấu hình; không nên quy toàn bộ WebFlux thành “mọi request chạy trên đúng một thread”.

### Blocking là rủi ro cần hiểu

Gọi **Thread.sleep**, JDBC/JPA blocking, client HTTP đồng bộ hoặc **Mono.block()** ngay trên event-loop có thể chặn các request khác chia sẻ event-loop đó. Ví dụ sau chỉ minh họa cách **cô lập công việc blocking** khi buộc phải dùng một thư viện cũ:

~~~java
Mono<Result> source = Mono.fromCallable(() -> blockingRepository.load())
    .subscribeOn(Schedulers.boundedElastic());
~~~

Ví dụ dùng giả định có lớp Result, biến blockingRepository và các import Reactor tương ứng; đây là **đoạn minh họa, không phải một chương trình biên dịch độc lập**. boundedElastic đưa việc blocking sang nhóm thread được thiết kế để chứa các công việc kiểu này; thao tác I/O phía repository **vẫn blocking**, không trở thành non-blocking thực sự và vẫn có giới hạn tài nguyên.

WebFlux thích hợp khi hệ thống có số lượng lớn kết nối đang chờ và một pipeline I/O non-blocking từ đầu đến cuối, ví dụ nhiều lời gọi dịch vụ bằng WebClient, streaming/SSE, kết nối dài, hoặc truy cập dữ liệu qua driver reactive như R2DBC. Nhưng **reactive không mặc nhiên nhanh hơn** cho nghiệp vụ đơn giản hay tác vụ CPU-bound: độ phức tạp, bối cảnh và benchmark thực tế mới quyết định.

### Giống nhau ở cú pháp không có nghĩa giống nhau ở runtime

Cả MVC lẫn WebFlux có thể dùng @RestController, @GetMapping, @RequestBody và cùng một service Spring. Tên annotation giống nhau **không cho biết ứng dụng chạy servlet stack hay reactive stack**. Để xác định phải xét dependency, loại ApplicationContext, auto-configuration và server thực tế.

## 6. Spring Boot: xây và chạy ứng dụng Spring

Spring Boot bổ sung cơ chế **opinionated defaults** và **auto-configuration có điều kiện** lên Spring Framework. Boot phân tích thư viện trên classpath, bean hiện có, properties và các điều kiện khác để đăng ký hạ tầng phù hợp.

Tính năng cốt lõi:

- **SpringApplication.run(...):** khởi động ApplicationContext và quy trình bootstrapping.
- **@SpringBootApplication:** gộp @SpringBootConfiguration, @EnableAutoConfiguration và @ComponentScan. Component scan mặc định bắt đầu từ package của lớp application trở xuống.
- **Starters:** nhóm dependency được lựa chọn sẵn (web stack, logging, testing...) để giảm cấu hình thủ công.
- **Embedded HTTP server:** ứng dụng web thường chạy như một process JAR có server nhúng; không bắt buộc tự triển khai WAR lên server ngoài.
- **Externalized configuration:** application.properties/application.yml, environment variables, command-line arguments... cấu hình theo môi trường.
- **Actuator (dependency tùy chọn):** health, metrics và các endpoint quản trị/quan sát; phải bật và bảo vệ endpoint theo môi trường.
- **Dependency management, packaging, test hỗ trợ:** quản lý phiên bản tương thích theo dòng Boot được chọn.

**Spring Boot không tự động thay thế kiến trúc ứng dụng:** bạn vẫn dùng bean của Spring Framework, controller MVC/WebFlux, service, repository, transaction. Boot cũng không mặc định biến API thành reactive.

### Cẩn thận khác biệt tên starter giữa các dòng Boot

Đối với ứng dụng web Servlet dùng MVC:

- **Spring Boot 3.x:** starter thông dụng là **spring-boot-starter-web**.
- **Spring Boot 4.x:** tài liệu chính thức dùng starter tách rõ **spring-boot-starter-webmvc**.

Đối với WebFlux, starter thông dụng là **spring-boot-starter-webflux**. Khi sao chép hướng dẫn cũ, hãy kiểm tra **dòng phiên bản Spring Boot đang dùng**; tránh suy luận một tên starter áp dụng y hệt cho mọi phiên bản. Nếu tạo dự án bằng Spring Initializr, chọn dependency **Spring Web** (MVC) hoặc **Spring Reactive Web** (WebFlux) phù hợp với phiên bản đã chọn.

Sự khác nhau giữa **starter** và **framework module**: spring-webmvc là module thực thi chức năng MVC thuộc Spring Framework; spring-boot-starter-webmvc là bộ dependency thuận tiện do Spring Boot cung cấp để kéo các thành phần cần thiết và cấu hình tương ứng.

## 7. Hai ứng dụng đối chiếu có thể chạy

Ví dụ minh họa hai endpoint HTTP cùng mục đích, nhưng một bên xử lý MVC, bên kia trả về Mono của WebFlux. **Tạo hai dự án riêng biệt** từ Spring Initializr, dùng **Java 17+**, một phiên bản Spring Boot ổn định tương thích với JDK bạn cài và Maven. Khi chọn dependency trên Initializr:

- Dự án **mvc-demo**: chọn **Spring Web** (được ánh xạ đến starter MVC phù hợp với phiên bản Boot).
- Dự án **webflux-demo**: chọn **Spring Reactive Web**.
- Mỗi dự án có Maven wrapper do Initializr sinh ra; dưới đây cung cấp **toàn bộ mã Java** cần thêm hoặc thay trong dự án tương ứng.

### 7.1. Dự án A — Spring Boot + Spring MVC

Tập tin **src/main/java/example/mvc/MvcApplication.java**:

~~~java
package example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcApplication.class, args);
    }
}
~~~

Tập tin **src/main/java/example/mvc/GreetingController.java**:

~~~java
package example.mvc;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    @GetMapping("/greeting")
    public Greeting greet(@RequestParam(defaultValue = "bạn") String name) {
        return new Greeting("Xin chào, " + name);
    }

    public record Greeting(String message) {
    }
}
~~~

Cấu trúc package **example.mvc** phải nằm trong component scan bắt đầu từ MvcApplication. Nếu Initializr tạo package khác, đổi **package** của cả hai file cho nhất quán và đặt chúng vào đúng thư mục.

Tại thư mục gốc **mvc-demo**:

~~~bash
# macOS/Linux
./mvnw spring-boot:run

# Windows PowerShell hoặc Command Prompt: dùng thay lệnh trên
mvnw.cmd spring-boot:run
~~~

Mở một terminal khác:

~~~bash
curl -s "http://localhost:8080/greeting?name=Lan"
~~~

HTTP body (dạng JSON, trình bày một dòng):

~~~json
{"message":"Xin chào, Lan"}
~~~

**Giải thích:** request tới DispatcherServlet, được map vào greet(), tạo record Greeting rồi được JSON message converter serialize. Với starter MVC mặc định, Boot thường cấu hình embedded Tomcat. Controller trả object trực tiếp; bạn không cần viết Servlet hay cấu hình DispatcherServlet bằng tay.

### 7.2. Dự án B — Spring Boot + Spring WebFlux

Tập tin **src/main/java/example/reactive/ReactiveApplication.java**:

~~~java
package example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveApplication.class, args);
    }
}
~~~

Tập tin **src/main/java/example/reactive/GreetingController.java**:

~~~java
package example.reactive;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class GreetingController {
    @GetMapping("/greeting")
    public Mono<Greeting> greet(
            @RequestParam(defaultValue = "bạn") String name) {
        return Mono.fromSupplier(
                () -> new Greeting("Xin chào, " + name));
    }

    public record Greeting(String message) {
    }
}
~~~

Trong thư mục gốc **webflux-demo**, chạy:

~~~bash
# macOS/Linux
./mvnw spring-boot:run

# Windows: dùng thay lệnh trên
mvnw.cmd spring-boot:run
~~~

Từ terminal khác:

~~~bash
curl -s "http://localhost:8080/greeting?name=Lan"
~~~

HTTP body:

~~~json
{"message":"Xin chào, Lan"}
~~~

**Giải thích:** WebFlux framework subscribe vào Mono trả về từ controller và phát JSON khi publisher cung cấp Greeting. Mono.fromSupplier hoãn công việc tạo đối tượng đến lúc subscription; bản thân ví dụ quá nhỏ nên **không chứng minh lợi ích hiệu năng** của reactive. Với cấu hình mặc định thường dùng Reactor Netty.

**Quan trọng:** hai dự án đều có đường dẫn /greeting và cho cùng kết quả. Điểm khác nhau nằm ở **web stack, contract thực thi và chuỗi I/O**, không phải ở JSON body hay tên annotation. Chạy lần lượt từng dự án trên cổng 8080 hoặc cấu hình server.port khác nhau khi muốn chạy song song.

### 7.3. Kiểm tra dependency Maven

Với Spring Boot 4.x, một dependency MVC đặc trưng trong pom.xml là:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webmvc</artifactId>
</dependency>
~~~

Với Spring Boot 3.x, dùng **spring-boot-starter-web** thay cho artifactId của ví dụ MVC trên. Với WebFlux trên các dòng tương ứng:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Đây là **các đoạn dependency** để đặt vào thẻ dependencies của pom.xml đã có Spring Boot parent/BOM tương thích, **không phải toàn bộ pom.xml độc lập**. Version của starter thường do dependency management của Boot quyết định; không tự trộn Spring Framework 6/7, Boot 3/4 hoặc Reactor versions tùy ý.

## 8. Minh họa execution model qua cùng một request

Giả sử endpoint vừa lấy khách hàng từ database vừa gọi API khác:

~~~text
MVC:     HTTP → Servlet thread → JDBC (chờ) → RestClient (chờ) → JSON
WebFlux: HTTP → reactive pipeline → R2DBC / WebClient → signals → JSON
~~~

Với MVC đồng bộ, thread thường chờ ở JDBC hoặc HTTP client. Với WebFlux dùng **driver và connector non-blocking thật**, event-loop có thể phục vụ công việc khác trong lúc chờ I/O. Đây chỉ là mô hình rút gọn: Servlet async có thể giải phóng request thread, còn WebFlux có thể đổi thread theo scheduler và vẫn bị nghẽn nếu gọi thư viện blocking.

**Điều kiện quan trọng:** `Mono` không làm JDBC thành non-blocking; Reactive Streams backpressure không tự điều tiết mọi API bên ngoài; CPU-bound work vẫn tiêu tốn CPU. Vì vậy, chọn stack theo **toàn bộ chuỗi I/O** chứ không nhìn annotation hay tên server. Cách lập bảng từng chặng I/O, benchmark và lựa chọn kiến trúc cụ thể được đào sâu ở bài riêng về Servlet/MVC so với WebFlux.

## 9. Cách chọn stack cho dự án

Cách nhớ để bắt đầu: **MVC** thường thích hợp cho ứng dụng Servlet/HTML/REST với JPA, JDBC và SDK blocking; **WebFlux** đáng cân nhắc nếu có streaming hoặc nhiều kết nối chờ I/O và chuỗi client/driver reactive xuyên suốt. Với tác vụ batch hay console không có HTTP, có thể dùng Spring Framework/Boot mà không cần web stack. Nếu hệ thống đang chạy MVC ổn định, hãy đo bottleneck trước khi di chuyển.

Các nhận diện quan trọng giúp tránh chọn sai runtime:

### Có thể dùng WebClient trong Spring MVC không?

**Có.** WebClient là HTTP client non-blocking thuộc hệ sinh thái WebFlux và có thể được dùng trong ứng dụng MVC. Thêm thư viện để dùng WebClient **không có nghĩa mọi controller MVC tự thành WebFlux**. Cần hiểu cách tích hợp kết quả async vào MVC để tránh vô tình gọi block() khiến thread chờ không cần thiết.

### Có nên đưa cả MVC và WebFlux starter vào cùng dự án?

Thông thường **không cần** để xử lý cùng một server API. Khi cả module MVC và WebFlux nằm trên classpath, Spring Boot mặc định **ưu tiên loại ứng dụng Servlet/MVC**; hiện tượng này hữu ích với dự án MVC dùng WebClient nhưng dễ gây nhầm khi người viết tưởng controller đã chạy WebFlux. Nếu thật sự muốn reactive web application, cần kiểm tra lại dependencies và xác định rõ WebApplicationType.REACTIVE theo yêu cầu thực tế.

### Spring Security, Spring Data, Spring Cloud có phải Spring Boot không?

Không. Chúng là **các dự án riêng trong hệ sinh thái Spring**, có thể tích hợp với Framework và thường được Boot hỗ trợ qua starter/auto-configuration. Phân biệt *Spring Framework* (nền tảng), *Spring Boot* (khởi động/cấu hình), *MVC/WebFlux* (web stack) và *các dự án bổ trợ* theo trách nhiệm thay vì nhầm chúng thành cùng một framework.

## 10. Những nhầm lẫn và lỗi phổ biến

1. **“Spring Boot thay thế Spring Framework.”** Sai. Boot dựa trên Spring Framework và tự động cấu hình nhiều thành phần của nó.
2. **“Spring Boot luôn là Spring MVC.”** Sai. Boot có thể chạy MVC, WebFlux hoặc không có web server.
3. **“Spring MVC là tên cũ của Spring Boot.”** Sai. MVC giải quyết xử lý web bằng Servlet; Boot giải quyết khởi động và cấu hình.
4. **“Dùng @RestController thì chắc chắn là MVC.”** Sai. WebFlux cũng hỗ trợ cùng annotation, cần nhìn web stack được kích hoạt.
5. **“WebFlux lúc nào cũng nhanh hơn MVC.”** Sai. Workload, client/database, độ trễ I/O, giới hạn CPU và cách triển khai mới quyết định.
6. **“Có Mono là mọi lời gọi non-blocking.”** Sai. Một Mono có thể bọc lệnh blocking; kiểu trả về không sửa bản chất I/O.
7. **“WebFlux chỉ chạy với Netty.”** Sai. Reactor Netty phổ biến với Boot, nhưng WebFlux hỗ trợ các runtime khác thích hợp.
8. **“MVC không hỗ trợ bất đồng bộ.”** Sai. MVC có Servlet async và các kiểu return async, dù hạ tầng khác WebFlux.
9. **“Thêm cả hai starter tự động chuyển hết sang reactive.”** Sai. Kiểm tra sự ưu tiên Servlet/MVC của Boot và auto-configuration.
10. **“@EnableWebMvc luôn cần khi dùng Spring Boot MVC.”** Không đúng trong cấu hình Boot thông thường: Boot đã tự cấu hình MVC; @EnableWebMvc trao quyền kiểm soát cấu hình MVC cho ứng dụng và có thể làm mất các tiện ích auto-configuration mặc định. Để tùy chỉnh nhỏ, ưu tiên WebMvcConfigurer.
11. **“Spring Boot tự tìm được mọi @Service ở mọi package.”** Sai. Component scan có phạm vi; đặt application class ở package gốc phù hợp hoặc cấu hình scan rõ ràng.
12. **“Để minh họa Spring Framework phải dùng HTTP.”** Sai. IoC/DI, transaction hoặc event vẫn có ích trong tác vụ không web.

## 11. Chẩn đoán khi ứng dụng chạy sai stack

Khi controller không được map hoặc ứng dụng sử dụng mô hình web không như mong đợi, kiểm tra theo thứ tự:

1. **Dependency tree:** ứng dụng đang có spring-webmvc, spring-webflux, starter nào và theo phiên bản Boot nào? Maven có thể dùng **mvn dependency:tree**.
2. **Component scan:** lớp @SpringBootApplication có nằm tại package bao trùm controller và service không?
3. **Auto-configuration:** chạy với tùy chọn **--debug** hoặc kiểm tra condition evaluation report/Actuator conditions khi đã cấu hình thích hợp; xác định config MVC hoặc WebFlux nào thực sự kích hoạt.
4. **HTTP server và context:** Tomcat/Jetty/Reactor Netty đang khởi động? server.port, servlet context path hoặc base path có bị đổi?
5. **Kiểu I/O trong service:** thread đang chờ JDBC/HTTP blocking, hay pipeline dùng driver và client non-blocking? Đừng chỉ nhìn chữ Mono/Flux.
6. **Lỗi thường gặp:** nếu port 8080 đã được dùng bởi dự án ví dụ kia, hãy dừng server trước hoặc đổi port, chẳng hạn **--server.port=8081** khi chạy ứng dụng Boot.

## 12. Ghi nhớ và tự kiểm tra

**Công thức nhận diện:** *Spring Framework = nền tảng; Spring MVC = Servlet web; Spring WebFlux = reactive web; Spring Boot = bootstrap và auto-configuration.*

Hãy thử trả lời:

1. Dự án dùng **@SpringBootApplication + spring-boot-starter-webmvc** thì đang dùng Framework, MVC hay Boot? **Cả ba**: Boot khởi động, MVC xử lý HTTP, Spring Framework cung cấp các thành phần nền.
2. Dự án chỉ có **spring-boot-starter-webflux**, controller trả **Mono<Greeting>**, chạy bằng Reactor Netty: dùng stack nào? **Boot + Spring WebFlux** (cùng hạ tầng Spring Framework).
3. Một REST API dùng **JPA/JDBC** với throughput tốt, chưa cần streaming: có bắt buộc chuyển WebFlux không? **Không**; MVC thường là lựa chọn tự nhiên, cần số liệu trước khi đổi.
4. Một app MVC thêm dependency WebFlux để gọi **WebClient**: endpoint của app có tự chuyển sang WebFlux không? **Không**; phải xác định web application type và cấu hình thực tế.
5. Một ứng dụng chỉ cần DI để chạy command-line: có phải thêm Spring MVC không? **Không**.

## Tài liệu chính thức để đào sâu

- [Spring Framework — Spring Web MVC](https://docs.spring.io/spring-framework/reference/web/webmvc.html): DispatcherServlet, annotated controllers, Servlet async, message conversion.
- [Spring Framework — Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): reactive contract, annotated/functional endpoints, runtime và so sánh với MVC.
- [Spring Framework — Core Technologies](https://docs.spring.io/spring-framework/reference/core.html): IoC container, bean, dependency injection.
- [Spring Boot — Web](https://docs.spring.io/spring-boot/reference/web/index.html): lựa chọn MVC/WebFlux và starter theo dòng phiên bản.
- [Spring Boot — Using @SpringBootApplication](https://docs.spring.io/spring-boot/reference/using/using-the-springbootapplication-annotation.html): auto-configuration, component scan và cấu hình ứng dụng.
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): WebFlux auto-configuration và lưu ý khi MVC/WebFlux cùng có mặt.

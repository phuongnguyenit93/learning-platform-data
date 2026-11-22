# Lựa chọn WebApplicationType: NONE, SERVLET và REACTIVE

## 1. WebApplicationType là gì?

Trong Spring Boot, `WebApplicationType` xác định loại môi trường ứng dụng mà `SpringApplication` sẽ khởi tạo. Nó ảnh hưởng đến loại `ApplicationContext`, việc cấu hình web server và các auto-configuration liên quan đến web.

Enum nằm trong package `org.springframework.boot` và có ba giá trị:

- **`NONE`**: ứng dụng không chạy như một web server. Spring vẫn tạo ApplicationContext, khởi tạo bean và chạy các callback như `ApplicationRunner` hoặc `CommandLineRunner`.
- **`SERVLET`**: ứng dụng web dựa trên Servlet API, thường sử dụng Spring MVC và embedded servlet container như Tomcat.
- **`REACTIVE`**: ứng dụng web theo mô hình reactive của Spring WebFlux, thường dùng Reactor Netty hoặc một server adapter tương thích.

Có thể hiểu đây là lựa chọn kiến trúc ở cấp ứng dụng. Nó quyết định cách Spring Boot khởi tạo môi trường web; không phải một thuộc tính để bật/tắt riêng từng endpoint.

## 2. Spring Boot tự xác định loại ứng dụng như thế nào?

Nếu không cấu hình rõ ràng, Spring Boot suy luận `WebApplicationType` từ những lớp có mặt trên classpath. Quy tắc khái quát:

1. Nếu có các lớp nền tảng của Spring WebFlux và không có các lớp đặc trưng của Spring MVC, Boot chọn `REACTIVE`.
2. Nếu các lớp cần thiết của Servlet/Spring MVC có mặt, Boot chọn `SERVLET`.
3. Nếu không thỏa điều kiện của ứng dụng Servlet hoặc Reactive, Boot chọn `NONE`.

Một tình huống dễ nhầm là project có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`. Khi cả Spring MVC và WebFlux cùng có mặt, Spring Boot mặc định ưu tiên Spring MVC và chọn loại `SERVLET`. Nếu chủ đích xây dựng ứng dụng WebFlux, cần chọn `REACTIVE` một cách tường minh và kiểm tra các dependency, auto-configuration đi kèm.

Việc suy luận dựa trên classpath giúp ứng dụng có cấu hình mặc định thuận tiện, nhưng cũng có thể khiến loại ứng dụng thay đổi khi thêm một starter. Vì vậy, hãy xem lại dependency tree khi ứng dụng bất ngờ khởi động web server hoặc chọn sai web stack.

## 3. NONE — ứng dụng Spring không có web server

### 3.1. Cách hoạt động

Với `WebApplicationType.NONE`, Spring Boot khởi tạo ApplicationContext không dành cho web server. Ứng dụng vẫn sử dụng được dependency injection, configuration properties, component scanning, auto-configuration phù hợp, lifecycle của bean và các tính năng cốt lõi của Spring.

Điểm khác biệt là Boot không khởi động embedded web server để nhận HTTP request. Ứng dụng không có luồng xử lý request/response như một web application.

Các trường hợp sử dụng thường gặp:

- Chương trình command-line cần nhận tham số và thực hiện tác vụ.
- Batch job đọc dữ liệu, xử lý và ghi kết quả.
- Worker chạy tác vụ nền hoặc xử lý message.
- Công cụ migration, import/export hoặc đồng bộ dữ liệu.
- Một tiến trình theo lịch, nếu ứng dụng được cấu hình scheduler phù hợp.

Ứng dụng NONE vẫn có thể gọi dịch vụ bên ngoài qua HTTP client như `RestClient` hoặc `WebClient`. Dùng một HTTP client không biến ứng dụng thành web server; loại ứng dụng nói về vai trò nhận request của chính tiến trình.

### 3.2. Cấu hình bằng application.properties

```properties
spring.main.web-application-type=none
```

Hoặc trong `application.yml`:

```yaml
spring:
  main:
    web-application-type: none
```

Cấu hình này hữu ích khi project có dependency web trên classpath nhưng mục đích chạy hiện tại là batch hoặc command-line. Tuy nhiên, nếu ứng dụng không cần web stack, nên cân nhắc bỏ starter web không sử dụng để giảm dependency và tránh auto-configuration không cần thiết.

### 3.3. Ví dụ Spring Boot NONE

Ví dụ dưới đây là một ứng dụng Spring Boot tối giản. Nó tạo ApplicationContext, sau đó chạy một `ApplicationRunner` mà không mở cổng HTTP.

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BatchApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BatchApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }

    @Bean
    ApplicationRunner batchRunner() {
        return args -> System.out.println("Batch job started");
    }
}
```

Với project đã cấu hình Spring Boot và dependency phù hợp, có thể chạy ứng dụng bằng Maven:

```bash
./mvnw spring-boot:run
```

Phần output do đoạn code của ứng dụng in ra là:

```text
Batch job started
```

Spring Boot còn có thể in banner và log khởi động. Dòng trên là output của `ApplicationRunner`, không phải toàn bộ log của tiến trình.

Có thể viết ngắn hơn bằng cách đặt property `spring.main.web-application-type=none` trong cấu hình và dùng `SpringApplication.run(BatchApplication.class, args)`. Cách gọi `setWebApplicationType` trong ví dụ giúp thể hiện trực tiếp API được sử dụng.

### 3.4. Khi nào không nên chọn NONE?

Không chọn NONE nếu tiến trình cần tiếp nhận HTTP request, cung cấp REST API, phục vụ giao diện web hoặc chạy WebSocket endpoint. Khi đó cần một web application type phù hợp. Nếu chỉ cần gọi API của hệ thống khác, NONE vẫn có thể phù hợp vì outbound HTTP client không yêu cầu embedded web server.

## 4. SERVLET — ứng dụng web dựa trên Servlet và Spring MVC

### 4.1. Cách hoạt động

`WebApplicationType.SERVLET` dùng mô hình web dựa trên Java Servlet API. Với cấu hình phổ biến, Spring Boot sử dụng Spring MVC và embedded Tomcat làm web server mặc định khi dependency tương ứng có mặt.

Khi khởi động, Boot tạo Servlet web application context và cấu hình web server. Request HTTP đi vào server, được chuyển qua Servlet filter chain và đến `DispatcherServlet`. `DispatcherServlet` phối hợp với các thành phần Spring MVC như handler mapping, controller, argument resolver và message converter để xử lý request, rồi tạo response.

Luồng khái quát:

```text
HTTP Client
    |
Embedded Servlet Container
    |
Servlet Filters
    |
DispatcherServlet
    |
Controller / Service
    |
HTTP Response
```

Mô hình Spring MVC thường được sử dụng theo kiểu xử lý đồng bộ: request được xử lý trên thread của container và controller trả về kết quả. Tuy nhiên, Servlet API và Spring MVC cũng hỗ trợ xử lý bất đồng bộ; vì thế không nên hiểu rằng mọi request trong mọi cấu hình đều bắt buộc chiếm một thread cho đến khi hoàn tất.

### 4.2. Dependency thường dùng

Với ứng dụng Spring MVC thông thường, dependency thường là:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

Starter này đưa Spring MVC và embedded servlet container mặc định vào classpath. Có thể thay container mặc định bằng server khác được Spring Boot hỗ trợ nếu có nhu cầu và cấu hình phù hợp.

### 4.3. Cấu hình loại ứng dụng

Nếu muốn chỉ rõ loại ứng dụng:

```properties
spring.main.web-application-type=servlet
server.port=8080
```

Trong nhiều project chỉ có `spring-boot-starter-web`, Boot sẽ tự suy luận SERVLET. Khai báo tường minh hữu ích khi classpath có nhiều web starter hoặc khi muốn cấu hình dễ đọc và ổn định hơn.

### 4.4. Ví dụ controller Spring MVC

Đây là một controller theo kiểu annotated controller:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello from Servlet";
    }
}
```

Khi ứng dụng SERVLET chạy trên cổng 8080, request:

```http
GET /hello HTTP/1.1
Host: localhost:8080
```

sẽ nhận body:

```text
Hello from Servlet
```

Trong ứng dụng thực tế, controller thường gọi service để xử lý nghiệp vụ thay vì đặt logic nghiệp vụ trực tiếp trong method controller.

### 4.5. Khi nào nên chọn SERVLET?

SERVLET phù hợp khi:

- Dự án dùng Spring MVC, REST API hoặc server-rendered web.
- Ứng dụng có nhiều thư viện, filter hoặc integration dựa trên Servlet API.
- Phần lớn thao tác xử lý là đồng bộ và có thể sử dụng mô hình request/thread quen thuộc.
- Đội ngũ muốn dùng hệ sinh thái Spring MVC và các embedded servlet container.

Spring MVC vẫn có thể xử lý tải lớn nếu được thiết kế và triển khai đúng. Không nên chọn REACTIVE chỉ vì nghe nói reactive luôn nhanh hơn; cần xét kiểu tải, thời gian chờ I/O, dependency và năng lực vận hành.

## 5. REACTIVE — ứng dụng web với Spring WebFlux

### 5.1. Cách hoạt động

`WebApplicationType.REACTIVE` khởi tạo môi trường web reactive. Spring Boot sử dụng Spring WebFlux thay cho Spring MVC làm web stack chính. Với cấu hình mặc định phổ biến, embedded server là Reactor Netty.

WebFlux được xây dựng trên Reactive Streams và Project Reactor. Hai kiểu dữ liệu thường gặp:

- `Mono<T>`: biểu diễn một kết quả bất đồng bộ có thể có tối đa một phần tử.
- `Flux<T>`: biểu diễn một chuỗi bất đồng bộ gồm không, một hoặc nhiều phần tử.

WebFlux thường sử dụng event loop và xử lý I/O non-blocking. Thay vì giữ một request thread trong lúc chờ I/O, runtime có thể dùng thread đó để xử lý công việc khác khi thao tác I/O chưa hoàn tất.

Luồng khái quát:

```text
HTTP Client
    |
Reactive Web Server (thường Reactor Netty)
    |
WebFlux Handler / DispatcherHandler
    |
Controller hoặc Functional Endpoint
    |
Mono / Flux pipeline
    |
HTTP Response
```

Đây là mô hình phù hợp với ứng dụng có nhiều thao tác I/O đồng thời và các dependency có API non-blocking.

### 5.2. Dependency thường dùng

Với Spring WebFlux:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

Starter này đưa Spring WebFlux và reactive server runtime mặc định phù hợp vào classpath. WebFlux cũng có thể chạy trên một số server adapter khác, bao gồm các Servlet container tương thích; dùng WebFlux không đồng nghĩa bắt buộc phải dùng Netty trong mọi triển khai.

### 5.3. Cấu hình loại ứng dụng

```properties
spring.main.web-application-type=reactive
server.port=8080
```

Nếu project có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, hãy chọn REACTIVE tường minh khi thực sự muốn dùng WebFlux. Tốt hơn nữa, loại bỏ starter không cần thiết để tránh việc auto-configuration chọn nhầm stack và làm dependency tree phức tạp.

### 5.4. Ví dụ reactive controller

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveHelloController {

    @GetMapping("/hello")
    public Mono<String> hello() {
        return Mono.just("Hello from Reactive");
    }
}
```

Controller trả về `Mono<String>`. WebFlux đăng ký và ghi kết quả khi publisher phát ra dữ liệu, thay vì yêu cầu method phải trả ngay một String theo cách đồng bộ truyền thống.

Body response là:

```text
Hello from Reactive
```

Ví dụ này minh họa kiểu trả về reactive. Trong ứng dụng thực tế, lợi ích non-blocking thể hiện rõ hơn khi các bước xử lý tiếp theo cũng dùng API non-blocking, chẳng hạn WebClient hoặc reactive database driver.

### 5.5. Tránh blocking trong reactive pipeline

Một lỗi phổ biến là chọn REACTIVE nhưng vẫn gọi API blocking trên event-loop thread. Ví dụ, gọi JDBC đồng bộ, `Thread.sleep()` hoặc một HTTP client blocking trực tiếp trong reactive pipeline có thể giữ thread event loop trong lúc chờ. Điều này làm giảm khả năng phục vụ nhiều request đồng thời và có thể gây nghẽn.

Nguyên tắc thực hành:

- Ưu tiên driver và client reactive khi toàn bộ luồng nghiệp vụ cần non-blocking.
- Không gọi `block()` tùy tiện trong controller hoặc event-loop pipeline.
- Không dùng `Thread.sleep()` để chờ trong reactive chain.
- Nếu buộc phải tích hợp một thao tác blocking, cô lập nó trên scheduler phù hợp, thường là `Schedulers.boundedElastic()`, và giới hạn tải theo nhu cầu hệ thống.
- Đo latency, throughput, thread usage và lỗi dưới tải thực tế.

Ví dụ minh họa cách cô lập một tác vụ blocking:

```java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<String> result = Mono.fromCallable(() -> legacyBlockingCall())
        .subscribeOn(Schedulers.boundedElastic());
```

Đây là đoạn minh họa cho một lời gọi blocking đã tồn tại; `legacyBlockingCall()` cần được định nghĩa trong ứng dụng. Không nên xem việc chuyển sang boundedElastic là lý do để biến toàn bộ ứng dụng thành blocking mà không đánh giá giới hạn concurrency và tài nguyên.

### 5.6. Khi nào nên chọn REACTIVE?

REACTIVE phù hợp khi:

- Ứng dụng xử lý nhiều kết nối đồng thời và có nhiều thời gian chờ I/O.
- Các client, database driver và dịch vụ tích hợp hỗ trợ reactive/non-blocking.
- Cần streaming dữ liệu hoặc xử lý luồng bất đồng bộ.
- Nhóm phát triển hiểu Reactor, backpressure, scheduler và cách debug reactive pipeline.

Reactive không tự động làm mọi tác vụ nhanh hơn. Công việc CPU-bound vẫn tiêu tốn CPU; dependency blocking vẫn có thể gây nghẽn; pipeline phức tạp có thể khó debug hơn. Hãy chọn theo workload và khả năng của hệ sinh thái dependency.

## 6. So sánh ba loại WebApplicationType

| Tiêu chí | NONE | SERVLET | REACTIVE |
|---|---|---|---|
| Mục đích | Ứng dụng không nhận HTTP request như web server | Web application dựa trên Servlet API | Web application dựa trên reactive stack |
| Web server | Không khởi động embedded web server | Có, thường Tomcat mặc định | Có, thường Reactor Netty mặc định |
| ApplicationContext | Context không dành cho web | Servlet web application context | Reactive web application context |
| Web framework thường gặp | Không bắt buộc MVC/WebFlux | Spring MVC | Spring WebFlux |
| Mô hình xử lý phổ biến | Runner, batch, command-line, worker | Request/response đồng bộ, có hỗ trợ async | Reactive, non-blocking I/O |
| Kiểu trả về thường gặp | Không có controller web | Object, String, ResponseEntity và các kiểu MVC hỗ trợ | Mono, Flux và publisher tương thích |
| Starter thường gặp | Không cần starter web | spring-boot-starter-web | spring-boot-starter-webflux |
| Trường hợp phù hợp | Job, CLI, tiến trình nền | REST API, MVC, ứng dụng Servlet | Nhiều I/O đồng thời, streaming, reactive integration |

Tên enum và web framework có quan hệ gần nhau nhưng không phải là một. `SERVLET` mô tả loại web application context; Spring MVC là framework thường được Boot cấu hình trong mô hình này. Tương tự, `REACTIVE` là loại ứng dụng reactive; Spring WebFlux là web framework thường được dùng.

## 7. Cách chọn WebApplicationType trong code

### 7.1. Dùng SpringApplication.setWebApplicationType

Có thể cấu hình trực tiếp trước khi gọi `run`:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;

SpringApplication application = new SpringApplication(MyApplication.class);
application.setWebApplicationType(WebApplicationType.REACTIVE);
application.run(args);
```

Thay `REACTIVE` bằng `SERVLET` hoặc `NONE` tùy mục đích. Cách này hữu ích khi loại ứng dụng được quyết định bằng code hoặc khi tạo nhiều cấu hình khởi động khác nhau.

### 7.2. Dùng SpringApplicationBuilder

```java
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;

new SpringApplicationBuilder(MyApplication.class)
        .web(WebApplicationType.NONE)
        .run(args);
```

Builder thuận tiện khi cần cấu hình thêm parent/child context hoặc nhiều application source. Với ứng dụng đơn giản, `SpringApplication` là đủ.

### 7.3. Dùng cấu hình ngoài

```properties
spring.main.web-application-type=servlet
```

Có thể thay giá trị bằng `none` hoặc `reactive`. Property thường được quản lý theo profile hoặc biến môi trường khi triển khai các môi trường khác nhau. Hãy đảm bảo profile đang active đúng với môi trường mong muốn.

## 8. Những nhầm lẫn thường gặp

| Nhầm lẫn | Giải thích chính xác |
|---|---|
| NONE nghĩa là không dùng Spring | NONE chỉ không khởi động web server; Spring ApplicationContext và bean vẫn hoạt động |
| NONE không thể gọi API bên ngoài | NONE vẫn có thể dùng RestClient, WebClient hoặc client khác để gửi request đi |
| Có WebFlux trên classpath thì chắc chắn là REACTIVE | Nếu Spring MVC cũng có mặt, Boot mặc định ưu tiên SERVLET; cần cấu hình rõ nếu muốn REACTIVE |
| REACTIVE luôn nhanh hơn SERVLET | Hiệu năng phụ thuộc workload, dependency, blocking I/O, CPU và cách triển khai |
| REACTIVE đồng nghĩa với Netty | Netty là server mặc định phổ biến; WebFlux có thể dùng server adapter tương thích khác |
| SERVLET luôn blocking | Servlet/Spring MVC có hỗ trợ asynchronous processing; mô hình phổ biến không đồng nghĩa mọi request đều đồng bộ |
| Đổi property là chuyển đổi hoàn toàn kiến trúc | Cần kiểm tra controller, dependency, server, data access và các API đang sử dụng |
| Dùng Mono hoặc Flux trong bất kỳ ứng dụng nào cũng biến nó thành reactive server | Kiểu publisher có thể được dùng ở nhiều nơi; loại web application được quyết định bởi cấu hình và runtime |

## 9. Quy trình lựa chọn và kiểm tra trong project

Khi tạo hoặc sửa một project Spring Boot, có thể thực hiện theo trình tự:

1. **Xác định vai trò tiến trình:** ứng dụng cần nhận HTTP request hay chỉ chạy tác vụ nền?
2. **Chọn web stack:** không cần web server thì chọn NONE; dùng Servlet/MVC thì chọn SERVLET; dùng WebFlux thì chọn REACTIVE.
3. **Kiểm tra dependency:** xem `spring-boot-starter-web`, `spring-boot-starter-webflux` và embedded server có đúng mục tiêu không.
4. **Kiểm tra cấu hình:** đọc `spring.main.web-application-type`, profile và các cấu hình liên quan.
5. **Khởi động và quan sát log:** kiểm tra server có khởi động hay không, loại context và cổng lắng nghe.
6. **Kiểm tra hành vi:** gọi endpoint nếu là web application; với NONE, xác nhận runner/job thực thi và tiến trình kết thúc hoặc tiếp tục theo thiết kế.
7. **Đánh giá dưới tải:** nếu chọn reactive, kiểm tra blocking call, scheduler, backpressure và giới hạn tài nguyên.

Một số lệnh hữu ích để xem dependency:

```bash
./mvnw dependency:tree
```

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Nếu project có cả hai web starter, kiểm tra dependency tree để biết dependency nào kéo Spring MVC hoặc WebFlux vào classpath. Không nên chỉ nhìn file khai báo trực tiếp vì dependency bắc cầu cũng có thể ảnh hưởng việc suy luận.

## 10. Kết luận thực hành

- Chọn **NONE** cho CLI, batch, worker hoặc tiến trình không cần nhận HTTP request.
- Chọn **SERVLET** cho ứng dụng Spring MVC và hệ sinh thái Servlet quen thuộc.
- Chọn **REACTIVE** khi cần WebFlux và có kế hoạch sử dụng non-blocking I/O xuyên suốt các dependency quan trọng.
- Kiểm tra classpath vì Spring Boot tự suy luận loại ứng dụng khi không cấu hình tường minh.
- Nếu có cả MVC và WebFlux, mặc định MVC được ưu tiên; cấu hình rõ `spring.main.web-application-type=reactive` khi chủ đích dùng reactive stack.
- Đừng lựa chọn chỉ theo cảm giác về hiệu năng. Đo workload thực tế và cân nhắc độ phức tạp vận hành.

## 11. Tài liệu tham khảo

- Spring Boot Reference Documentation — Web: https://docs.spring.io/spring-boot/reference/web/index.html
- Spring Boot API — WebApplicationType: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/WebApplicationType.html
- Spring Boot Reference Documentation — Developing with Spring Boot: https://docs.spring.io/spring-boot/reference/using/index.html
- Spring Framework Reference — Spring Web MVC: https://docs.spring.io/spring-framework/reference/web/webmvc.html
- Spring Framework Reference — Spring WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Project Reactor Reference Guide: https://projectreactor.io/docs/core/release/reference/

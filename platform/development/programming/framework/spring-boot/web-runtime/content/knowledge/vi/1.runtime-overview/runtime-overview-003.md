# Phân biệt Spring MVC, Spring WebFlux và máy chủ nhúng

## 1. Mục tiêu và bức tranh tổng thể

Khi viết ứng dụng web với Spring Boot, cần phân biệt **framework xử lý HTTP** và **phần mềm nhận kết nối HTTP**:

- **Spring MVC** là web framework theo mô hình Servlet, thường dùng lối lập trình imperative (gọi hàm tuần tự), phù hợp với các thư viện đồng bộ như JDBC/JPA.
- **Spring WebFlux** là web framework reactive, thiết kế cho I/O bất đồng bộ, không chặn luồng (non-blocking), thường dùng kiểu `Mono<T>` và `Flux<T>` của Project Reactor.
- **Máy chủ nhúng (embedded web server)** là thành phần nhận kết nối mạng, đọc/ghi HTTP và chuyển request vào web framework. Ví dụ: Tomcat, Jetty, Reactor Netty. Nó **không phải** là framework controller.

Spring Boot phụ trách **tự cấu hình và khởi động** framework cùng máy chủ tương ứng dựa trên dependencies, cấu hình và kiểu ứng dụng. Một chương trình thường chạy bằng `java -jar` mà không phải cài Tomcat bên ngoài.

```text
Client (browser, curl, mobile app)
           |
       HTTP/TCP
           |
  Embedded HTTP server
  (Tomcat / Jetty / Reactor Netty)
           |
   +-------+-----------------------------+
   |                                     |
Servlet adapter                       Reactive HTTP adapter
   |                                     |
Spring MVC                            Spring WebFlux
DispatcherServlet                     HttpHandler / DispatcherHandler
   |                                     |
Controller -> Service                 Handler -> Mono/Flux -> Service
   |                                     |
HTTP response                         HTTP response
```

Đây là **hai nhánh ứng dụng thay thế nhau**, không phải một request tự động đi qua cả MVC lẫn WebFlux. Sơ đồ giản lược để chỉ vị trí trách nhiệm; các filter, security, handler mapping, message converter/codec còn nằm trên đường xử lý thực tế.

## 2. Spring MVC: web stack dựa trên Servlet

**Spring MVC (spring-webmvc)** dùng Servlet API và thường chạy trên servlet container như Tomcat hoặc Jetty.

Dòng xử lý tiêu biểu:

1. Tomcat/Jetty nhận kết nối và chuyển HTTP request tới `DispatcherServlet`.
2. `DispatcherServlet` nhờ `HandlerMapping` tìm controller phù hợp với URL và HTTP method.
3. `HandlerAdapter` gọi phương thức controller; controller gọi service/repository.
4. Kết quả được chuyển thành body (ví dụ JSON qua `HttpMessageConverter`) hoặc view; servlet container gửi response.

Ở mô hình xử lý đồng bộ phổ biến, request chiếm một luồng xử lý của container trong lúc controller chạy, kể cả khi lệnh gọi JDBC hoặc HTTP đồng bộ đang đợi I/O. Pool luồng giúp xử lý nhiều request, nhưng số luồng và thời gian bị chặn là tài nguyên phải quản lý. **Không nên tuyệt đối hóa thành “MVC luôn chặn một luồng từ đầu đến cuối”:** Spring MVC cũng hỗ trợ Servlet async, `Callable`, `DeferredResult`, streaming và một số reactive return type; tuy nhiên nền tảng Servlet và phần lớn thư viện sử dụng vẫn theo mô hình đồng bộ.

Ví dụ hành vi quen thuộc:

```java
@GetMapping("/users/{id}")
public UserDto getUser(@PathVariable long id) {
    // Ví dụ rút gọn: service có thể dùng JDBC/JPA đồng bộ.
    return userService.findById(id);
}
```

Đoạn trên là **minh họa controller**, chưa chạy độc lập vì `UserDto` và `userService` chưa được định nghĩa. Nó thể hiện lời gọi tuần tự, dễ đọc, debug và tích hợp hệ sinh thái blocking.

Chọn MVC thường hợp lý khi ứng dụng là CRUD/business API, có JPA/JDBC, giao dịch đồng bộ, thư viện Servlet, hoặc đội ngũ muốn mô hình imperative đơn giản.

## 3. Spring WebFlux: web stack reactive, non-blocking

**Spring WebFlux (spring-webflux)** không phụ thuộc vào Servlet API để định nghĩa mô hình xử lý; nó có thể chạy trực tiếp trên Reactor Netty hoặc qua adapter non-blocking trên Tomcat/Jetty. WebFlux dùng `DispatcherHandler` (thay cho `DispatcherServlet`), cho phép cả annotated controllers và functional endpoints (`RouterFunction`/`HandlerFunction`).

Hai kiểu dữ liệu Reactor cơ bản:

- `Mono<T>`: publisher phát **0 hoặc 1** phần tử (hoặc lỗi rồi kết thúc).
- `Flux<T>`: publisher phát **0 đến nhiều** phần tử theo thời gian (hoặc lỗi rồi kết thúc).

Controller thường **trả về publisher mô tả công việc**; runtime subscribe trong quá trình xử lý request. Các bước I/O non-blocking có thể tiếp tục qua callback/signal khi dữ liệu sẵn sàng, thay vì giữ một thread chờ mạng. **Backpressure** là cơ chế bên tiêu thụ báo nhu cầu nhận dữ liệu cho publisher theo Reactive Streams; không nên hiểu là mọi database/HTTP upstream tự động hỗ trợ backpressure chỉ vì code trả về `Flux`.

Dòng xử lý điển hình:

1. Reactor Netty (mặc định thường dùng) nhận request trên các event-loop worker.
2. HTTP adapter chuyển vào WebFlux `HttpHandler`/`WebHandler` và `DispatcherHandler`.
3. Handler trả về `Mono`/`Flux`; các phép toán reactive mô tả xử lý và phối hợp I/O.
4. Khi tín hiệu dữ liệu/hoàn tất/lỗi xuất hiện, runtime encode kết quả và ghi HTTP response theo cơ chế bất đồng bộ.

Event loop cần được giữ thông thoáng. **Không gọi `Thread.sleep(...)`, JDBC/JPA blocking, HTTP client đồng bộ hoặc `.block()` trực tiếp trong luồng xử lý non-blocking**: chúng có thể làm nghẽn ít event-loop thread và ảnh hưởng nhiều request. Khi bắt buộc gọi API blocking, cô lập công việc trên scheduler phù hợp, chẳng hạn:

```java
// Minh họa phương thức trong một controller đã được cấu hình dependency:
// blockingService là bean cung cấp API đồng bộ, không có trong ví dụ độc lập.
@GetMapping("/legacy")
public Mono<String> legacy() {
    return Mono.fromCallable(() -> blockingService.fetch())
            .subscribeOn(Schedulers.boundedElastic());
}
```

Cần import `reactor.core.publisher.Mono` và `reactor.core.scheduler.Schedulers`. `boundedElastic()` là giải pháp chuyển tiếp để cô lập blocking I/O, **không biến JDBC thành non-blocking**; nếu đường dữ liệu chủ yếu là blocking, dùng MVC thường đơn giản và phù hợp hơn.

WebFlux phát huy lợi ích với dịch vụ có nhiều tác vụ I/O đồng thời, thời gian chờ mạng biến động, streaming, hoặc chuỗi thành phần reactive thực sự (ví dụ WebClient + driver reactive như R2DBC). Nó không mặc nhiên làm mọi request nhanh hơn: thêm publisher/operator có chi phí, tác vụ CPU vẫn cần tài nguyên CPU, và hiệu quả phải đo bằng throughput, latency, memory, số luồng, tải thực tế.

## 4. Máy chủ nhúng: nằm dưới framework

**Embedded server** là server được đóng gói/chạy cùng ứng dụng Spring Boot. Khi ứng dụng khởi động, Boot tạo server, mở cổng TCP (mặc định HTTP `8080` nếu không đổi), đăng ký các adapter/handler và quản lý vòng đời server. Server nhận HTTP; framework quyết định định tuyến, gọi controller và xây response.

| Thành phần | Bản chất | Phối hợp thường gặp |
| --- | --- | --- |
| **Tomcat** | Servlet container và HTTP server | Spring MVC + embedded Tomcat; cũng có thể phục vụ WebFlux qua adapter |
| **Jetty** | Servlet container và HTTP server | Spring MVC + embedded Jetty; cũng có thể phục vụ WebFlux qua adapter |
| **Reactor Netty** | HTTP server non-blocking dựa trên Netty, không phải Servlet container | Spring WebFlux + embedded Reactor Netty |
| **Spring MVC** | Framework xử lý request theo Servlet | Chạy trên servlet container, thường Tomcat |
| **Spring WebFlux** | Framework xử lý reactive HTTP | Chạy trên Reactor Netty, Tomcat hoặc Jetty |
| **Spring Boot** | Bootstrap, auto-configuration, dependency conventions, vận hành | Chọn và khởi động stack/server phù hợp |

Vì vậy **“Spring MVC = Tomcat” và “Spring WebFlux = Netty” đều là cách nói thiếu chính xác**: đó chỉ là những tổ hợp phổ biến. Tomcat và Jetty có thể chạy WebFlux; Netty không biến thành Servlet container để chạy DispatcherServlet của MVC.

```text
Spring MVC  -> Servlet container -> Tomcat / Jetty
Spring WebFlux -> reactive HTTP runtime -> Reactor Netty / Tomcat / Jetty
```

“Nhúng” là **cách đóng gói/vận hành**, không phải cơ chế blocking hay non-blocking. Một ứng dụng MVC có thể chạy bằng executable JAR với embedded Tomcat; Spring MVC cũng có thể triển khai WAR lên servlet container bên ngoài. Việc đổi cách triển khai không tự chuyển MVC thành WebFlux.

## 5. Bảng so sánh để quyết định đúng

| Tiêu chí | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Nền tảng | Servlet API | Reactive Streams, WebFlux HTTP abstraction; có adapter cho server Servlet |
| Front controller | `DispatcherServlet` | `DispatcherHandler` |
| Lối viết phổ biến | Imperative: trả `T`, `ResponseEntity<T>` | Reactive: trả `Mono<T>`, `Flux<T>`; cũng có annotated controller |
| I/O mặc định trong ứng dụng | Thường blocking; hỗ trợ Servlet async | Thiết kế non-blocking xuyên tầng nếu dependencies cùng hỗ trợ |
| Mô hình luồng thường gặp | Pool luồng request trong Servlet container | Ít event-loop worker; không được block event loop |
| Thư viện dữ liệu điển hình | Spring Data JPA, JDBC (blocking) | R2DBC, reactive drivers, WebClient (non-blocking) |
| Server mặc định trong starter Boot | Tomcat | Reactor Netty |
| Streaming | Có thể làm với async/SSE/streaming | `Flux` và reactive streaming là mô hình tự nhiên |
| Lợi thế chính | Dễ hiểu, dễ debug, tương thích thư viện blocking | Khả năng mở rộng I/O nhiều kết nối với lượng thread nhỏ khi end-to-end non-blocking |
| Điểm cần cân nhắc | Thread pool chịu áp lực nếu I/O chờ quá lâu | Debug/operator phức tạp hơn; chặn event loop rất nguy hiểm |

Không có kết luận “WebFlux luôn tốt hơn MVC”. Lợi ích của WebFlux thường rõ khi tải có **nhiều thời gian chờ I/O** và toàn bộ chuỗi phụ thuộc phù hợp reactive. MVC thường là lựa chọn mặc định tốt cho API dùng JPA và business logic truyền thống.

### Ba tình huống chọn stack

1. **Ứng dụng quản lý đơn hàng có Spring Data JPA/PostgreSQL và giao dịch đồng bộ:** ưu tiên MVC vì call stack rõ và repository blocking là thành phần chính.
2. **API gateway hợp nhất nhiều HTTP API bất đồng bộ, kết nối lâu/streaming, dùng WebClient và reactive persistence:** WebFlux đáng cân nhắc, sau đó benchmark với dữ liệu thực.
3. **Dịch vụ CPU-bound tính toán nặng:** không chọn WebFlux chỉ để mong chạy nhanh hơn; phải thiết kế giới hạn concurrency, phân bố CPU và queue/executor phù hợp ở cả hai stack.

## 6. Hai ví dụ chạy được với Java 17+

Hai ví dụ là **hai project Maven Spring Boot riêng**, mỗi project chỉ chọn **một** web starter. Tạo project từ https://start.spring.io/ với Maven, Java 17 trở lên, cùng package `com.example.demo`. Với **Spring Boot 4.x**, dependency của project MVC là:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webmvc</artifactId>
</dependency>
```

Với **Spring Boot 3.x**, starter MVC phổ biến tương ứng là `spring-boot-starter-web`. Project WebFlux trên Boot 3.x/4.x dùng:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

Các đoạn dependency trên được đặt trong `<dependencies>` của `pom.xml` do Initializr sinh ra; chúng **không phải toàn bộ POM**. Giữ Spring Boot parent, Maven plugin và wrapper mà Initializr tạo để quản lý phiên bản phù hợp.

### 6.1. Project A — MVC với embedded Tomcat

Tạo tệp `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello() {
        return "Hello MVC";
    }
}
```

Chạy tại thư mục gốc project Maven:

```bash
./mvnw spring-boot:run
```

Trên Windows PowerShell dùng `.\mvnw.cmd spring-boot:run`. Ở terminal khác, gọi:

```bash
curl -s http://localhost:8080/hello
```

HTTP response body nhận được là `Hello MVC`. Với starter MVC mặc định, Boot khởi động Tomcat và đặt `DispatcherServlet` vào luồng xử lý request.

### 6.2. Project B — WebFlux với embedded Reactor Netty

Tạo **project thứ hai** (không thay starter trong lúc project A đang chạy cùng cổng), dùng starter `spring-boot-starter-webflux` và cùng đường dẫn Java ở project B:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@RestController
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @GetMapping("/hello")
    public Mono<String> hello() {
        return Mono.just("Hello WebFlux");
    }
}
```

Chạy `./mvnw spring-boot:run` (PowerShell: `.\mvnw.cmd spring-boot:run`), rồi:

```bash
curl -s http://localhost:8080/hello
```

HTTP response body là `Hello WebFlux`. Netty lắng nghe HTTP; WebFlux xử lý handler trả về `Mono<String>`. Với response tức thời như `Mono.just(...)`, không thể suy ra WebFlux sẽ nhanh hơn MVC; ví dụ này nhằm phân biệt **kiểu lập trình và runtime**.

Nếu muốn chạy **cả hai project cùng lúc**, đặt `src/main/resources/application.properties` của một project là:

```properties
server.port=8081
```

Sau đó gọi project ấy bằng `curl -s http://localhost:8081/hello`. Cả MVC và WebFlux đều hỗ trợ cấu hình `server.port` khi chạy trên máy chủ nhúng do Boot quản lý.

### 6.3. Hiểu đúng về `Flux` và streaming

Trong project WebFlux, có thể thêm vào class controller ở mục 6.2 một endpoint (đoạn sau **chỉ là phương thức bổ sung**, không phải Java class độc lập):

```java
@GetMapping(value = "/ticks", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<Long> ticks() {
    return Flux.interval(Duration.ofSeconds(1)).take(3);
}
```

Thêm imports `java.time.Duration`, `org.springframework.http.MediaType` và `reactor.core.publisher.Flux`. Lệnh `curl -N http://localhost:8080/ticks` sẽ nhận các sự kiện SSE mang giá trị `0`, `1`, `2` theo thời gian (thời điểm chính xác phụ thuộc lịch chạy). `Flux.interval` tạo tín hiệu bất đồng bộ; đây là ví dụ nhỏ về stream, không phải bằng chứng benchmark.

## 7. Spring Boot chọn stack và server như thế nào?

Đối với các ứng dụng web điển hình:

- Chỉ có MVC starter: Boot cấu hình **SERVLET** web application, tạo servlet web server và `DispatcherServlet`; Tomcat là lựa chọn mặc định của starter.
- Chỉ có WebFlux starter: Boot cấu hình **REACTIVE** web application, tạo reactive web server và WebFlux HTTP pipeline; Reactor Netty là lựa chọn mặc định của starter.
- Có **cả MVC và WebFlux** trên classpath: Boot thường ưu tiên cấu hình **Spring MVC/Servlet**, vì ứng dụng MVC có thể thêm hỗ trợ WebClient. **Chỉ có `Mono`, `Flux` hoặc WebClient trong code không chứng minh server đang chạy WebFlux**. Nếu thực sự cần reactive web application, phải kiểm tra dependency và web application type rõ ràng, ví dụ `spring.main.web-application-type=reactive` trong cấu hình phù hợp.

Tùy chọn cấu hình máy chủ:

```properties
# Mặc định thường là 8080; thay đổi khi có yêu cầu:
server.port=8081
```

Đổi server bằng cách **loại dependency server mặc định và thêm dependency server muốn dùng** (ví dụ loại Tomcat rồi thêm Jetty cho MVC, hoặc loại Reactor Netty và thêm Tomcat/Jetty cho WebFlux). Đây là thay đổi **server transport**, không nhất thiết là thay đổi web framework. Dùng dependency tree để xác nhận server nào đang nằm trên classpath; dùng startup log để nhận diện server thực sự được mở.

Khi đóng gói với Maven wrapper:

```bash
./mvnw clean package
java -jar target/<ten-artifact-da-build>.jar
```

Lệnh `java -jar` ở trên là **mẫu lệnh**, cần thay `<ten-artifact-da-build>` bằng đúng tên JAR mà Maven đã tạo (không gõ dấu ngoặc nhọn dạng placeholder). Trên Windows, thay `./mvnw` bằng `.\mvnw.cmd`. Một executable JAR thường chứa ứng dụng cùng các dependency/server cần thiết; không cần cài Tomcat hệ thống chỉ để chạy project MVC có embedded Tomcat.

## 8. Các nhầm lẫn và lỗi thường gặp

| Nhầm lẫn / sự cố | Điều đúng và cách kiểm tra |
| --- | --- |
| “MVC là Tomcat, WebFlux là Netty.” | MVC/WebFlux là framework; Tomcat/Jetty/Netty là server. WebFlux cũng có thể chạy trên Tomcat/Jetty. |
| “Thêm `Mono` vào MVC là chuyển cả ứng dụng sang WebFlux.” | MVC hỗ trợ một số reactive return type; runtime vẫn có thể là `DispatcherServlet`. Kiểm tra starter và loại ứng dụng. |
| “Reactive tức là mọi câu lệnh tự non-blocking.” | Nếu dùng JDBC/JPA đồng bộ hoặc `.block()` ngay trên event loop, request vẫn chặn thread. |
| “WebFlux lúc nào cũng throughput cao hơn.” | Cần benchmark thực tế và xét chi phí framework, mức độ chờ I/O, database, CPU, số kết nối và memory. |
| “Máy chủ nhúng là thứ làm API reactive.” | Embedded chỉ nói tới cách server được chạy/đóng gói; reactive phụ thuộc WebFlux và toàn bộ chuỗi I/O. |
| “Cài Tomcat riêng mới chạy được Spring MVC.” | Embedded Tomcat trong executable Boot JAR có thể tự chạy; external container là lựa chọn khác. |
| “Cả hai project không lên được trên `8080`.” | Hai process không thể cùng bind một địa chỉ/cổng; đổi `server.port` của một project, hoặc dừng project kia. |
| “WebFlux nên gọi blocking API ở event loop cho tiện.” | Hãy dùng driver non-blocking; nếu bất khả kháng, cô lập blocking call lên scheduler phù hợp, đo hiệu quả và theo dõi pool. |

**Cách tự kiểm chứng runtime:** xem `pom.xml`/`build.gradle` và dependency tree; xem startup log báo Tomcat/Jetty/Netty; xem có `DispatcherServlet` (MVC) hay `DispatcherHandler` (WebFlux); thử endpoint bằng `curl`. **Không kết luận chỉ từ annotation `@RestController`**, vì cả hai stack đều dùng annotation-based controller.

## 9. Tự kiểm tra hiểu bài

1. Một API dùng Spring Data JPA, có controller trả về `UserDto`: nên bắt đầu với MVC hay WebFlux? **MVC**, vì persistence đang blocking và cách viết imperative phù hợp.
2. Spring WebFlux có bắt buộc dùng Netty? **Không**. WebFlux chạy được trên Reactor Netty và qua adapter tương ứng của Tomcat/Jetty.
3. Embedded Tomcat có đồng nghĩa ứng dụng luôn là Spring MVC? **Không**. Tomcat là server/Servlet container và cũng có thể phục vụ WebFlux.
4. Tại sao `Thread.sleep(3000)` trong WebFlux handler có thể nghiêm trọng? **Vì chặn event-loop worker**, làm trì hoãn các request khác dùng chung luồng.
5. Khi thêm WebClient vào một ứng dụng MVC, stack HTTP server có tự trở thành WebFlux? **Không**. Có thể dùng reactive client trong ứng dụng MVC; cần xem kiểu ứng dụng mà Boot thực sự cấu hình.
6. Dấu hiệu để chọn WebFlux là gì? **Nhiều tác vụ I/O bất đồng bộ/streaming, dependencies reactive xuyên tầng, nhu cầu mở rộng có đo đạc**, chứ không chỉ vì tên gọi “reactive”.

## 10. Tài liệu tham khảo chính thức

- Spring Framework — [Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc.html)
- Spring Framework — [Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html)
- Spring Framework — [WebFlux overview, servers, performance và concurrency](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- Spring Boot — [Web applications và starter](https://docs.spring.io/spring-boot/reference/web/index.html)
- Spring Boot — [Reactive web applications](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- Spring Boot — [Embedded web servers](https://docs.spring.io/spring-boot/how-to/webserver.html)

**Ghi nhớ:** chọn **MVC hay WebFlux** dựa trên mô hình xử lý I/O và hệ sinh thái thư viện; chọn **Tomcat, Jetty hay Reactor Netty** dựa trên runtime/server phù hợp. Spring Boot là lớp tự động lắp ghép và vận hành các thành phần ấy.
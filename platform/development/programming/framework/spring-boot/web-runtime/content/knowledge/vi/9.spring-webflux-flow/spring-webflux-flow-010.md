# Ranh giới hỗ trợ WebFlux trên máy chủ Servlet và trên Reactor Netty

## 1. Vì sao phải hiểu ranh giới hỗ trợ?

Spring WebFlux là web framework reactive của Spring. Nó hỗ trợ lập trình bất đồng bộ, non-blocking I/O và Reactive Streams, nhưng **WebFlux không đồng nghĩa với Reactor Netty**. WebFlux có thể xử lý HTTP trên Reactor Netty hoặc trên một số máy chủ Servlet có khả năng non-blocking I/O. Điểm chung nằm ở lập trình WebFlux phía ứng dụng; điểm khác nằm ở cách adapter nối framework với socket, Servlet container và vòng đời server.

Nhầm lẫn phổ biến gồm: cho rằng cứ dùng Tomcat là Spring MVC; cho rằng WebFlux bắt buộc chạy Netty; cho rằng chạy WebFlux trên Tomcat cho phép sử dụng trực tiếp mọi Servlet Filter; và cho rằng đổi starter là đủ để biến một ứng dụng MVC đồng bộ thành một hệ thống reactive hoàn toàn.

Bài học này giải thích ranh giới đó theo bốn góc nhìn: **mô hình lập trình**, **adapter HTTP**, **mô hình concurrency/I/O** và **hỗ trợ triển khai theo phiên bản Spring Boot**. Ví dụ thực hành sử dụng Java 17+ và Spring Boot 3.3.x để giữ dependency và API nhất quán. Đối với Spring Boot 4.x, hãy đối chiếu tài liệu của nhánh đang chạy vì danh sách server được hỗ trợ, baseline Servlet và starter có thay đổi.

Kết quả kỳ vọng:

- Mô tả được WebFlux trên Reactor Netty và WebFlux trên Tomcat/Jetty khác nhau ở đâu.
- Giải thích được HttpHandler, WebHandler, ServerWebExchange, DispatcherHandler và adapter HTTP.
- Phân biệt WebFlux-on-Servlet với Spring MVC-on-Servlet.
- Hiểu giới hạn của Servlet API, Servlet Filter, WAR deployment, WebFilter và SecurityWebFilterChain trong ứng dụng WebFlux.
- Chọn, đổi và xác nhận embedded server bằng dependency, ApplicationContext và HTTP test thật.
- Tránh chặn event loop và không khẳng định backpressure toàn chuỗi khi downstream vẫn blocking.
- Biết những kiểm thử bắt buộc trước khi chuyển server trong production.

## 2. Ba khái niệm phải tách biệt

**Web framework** quyết định controller/router và pipeline xử lý request. **HTTP runtime** nhận kết nối và truyền byte qua mạng. **Deployment model** quyết định ai tạo và quản lý tiến trình, server và artifact.

| Khía cạnh | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Mô hình lập trình | Servlet web stack | Reactive web stack |
| Front controller | DispatcherServlet | DispatcherHandler |
| Request API thường dùng | HttpServletRequest, ServletRequest, ModelAndView | ServerHttpRequest, ServerWebExchange, Mono, Flux |
| Bộ lọc framework | Servlet Filter, HandlerInterceptor | WebFilter, WebFilterChain |
| Security cấu hình web | SecurityFilterChain | SecurityWebFilterChain |
| Kiểu kết quả | DTO, ResponseEntity, có thể hỗ trợ async | Mono, Flux, Publisher, DTO được hỗ trợ |
| Server điển hình | Tomcat/Jetty | Reactor Netty; cũng có thể Tomcat/Jetty qua adapter |
| Assumption về blocking | Có thể dùng API đồng bộ với thread container | Cần bảo vệ event-loop khỏi blocking |

Cả hai framework đều có thể dùng @RestController, @GetMapping và JSON, nên **nhìn annotation không đủ để xác định stack**. Phải kiểm tra starter, web application type, context thực sự khởi tạo và handler runtime.

Cùng một Tomcat có thể đóng vai trò:

1. Servlet container cho Spring MVC, trực tiếp quản lý Servlet/Filter/DispatcherServlet.
2. HTTP server cho Spring WebFlux, dùng non-blocking I/O của Servlet qua bridge nội bộ. Lúc đó request đi vào pipeline WebFlux chứ không thành Spring MVC.

Ngược lại, Reactor Netty không phải Servlet container để thay Tomcat trong một ứng dụng MVC bất kỳ chỉ bằng một dependency.

## 3. Nền tảng chung của WebFlux: HttpHandler và WebHandler

Spring WebFlux xây dựng một lớp HTTP độc lập với API của server. Ở tầng thấp, org.springframework.http.server.reactive.HttpHandler có nhiệm vụ xử lý ServerHttpRequest và ServerHttpResponse bằng phản hồi reactive. Hợp đồng khái quát:

~~~java
Mono<Void> handle(
        ServerHttpRequest request,
        ServerHttpResponse response);
~~~

Đoạn trên là chữ ký minh họa API, không phải một chương trình Java độc lập. Mono<Void> mô tả quá trình xử lý response bất đồng bộ. Việc hoàn tất Publisher không có nghĩa framework phải tạo một thread mới cho mỗi request.

Ở tầng cao hơn, WebHandler xử lý ServerWebExchange, một đối tượng bao bọc request, response, attributes, session và những thông tin web liên quan. WebHttpHandlerBuilder và HttpWebHandlerAdapter kết nối các phần WebFlux như WebFilter, exception handler và WebHandler vào HttpHandler phù hợp.

Trong ứng dụng @RestController, DispatcherHandler thực hiện vai trò chọn handler, binding tham số và gọi controller của WebFlux. Với functional endpoints, RouterFunction và HandlerFunction cho phép khai báo tuyến theo một cách khác nhưng vẫn chạy trên cùng hạ tầng reactive.

Nhờ hợp đồng HttpHandler, WebFlux có thể nối với nhiều server mà không phải viết lại controller khi thay runtime, miễn rằng các đặc tính máy chủ cần dùng được hỗ trợ và đã được kiểm thử.

## 4. WebFlux trên Reactor Netty

Reactor Netty xây dựng trên Netty và tích hợp Project Reactor. Trong cấu hình Spring Boot WebFlux thông dụng, spring-boot-starter-webflux kéo spring-boot-starter-reactor-netty; Boot chọn embedded Reactor Netty làm HTTP server.

Luồng tổng quát:

~~~text
Client TCP/HTTP
    |
    v
Netty channel pipeline / event loop
    |
    v
Reactor Netty HttpServer
    |
    v
ReactorHttpHandlerAdapter
    |
    v
Spring HttpHandler
    |
    v
WebFilter / WebHandler / DispatcherHandler
    |
    v
Controller -> Mono/Flux -> HTTP response
~~~

ReactorHttpHandlerAdapter đóng vai trò cầu nối giữa callback/API của Reactor Netty và HttpHandler của Spring. Nó không cần jakarta.servlet.http.HttpServletRequest hoặc một Servlet container để tiếp nhận request.

Ưu điểm chính:

- Mô hình event-driven, non-blocking network I/O là thiết kế gốc của server.
- Hợp với chuỗi reactive gồm WebClient, R2DBC và các thư viện non-blocking khác.
- Reactor Netty có HTTP client và server, có thể chia sẻ tài nguyên event loop trong cấu hình mặc định phù hợp.
- Streaming và xử lý bất đồng bộ có thể sử dụng số thread tương đối nhỏ trong những workload có nhiều thời gian chờ I/O.

Ranh giới thực tế:

- Spring WebFlux vẫn cần application context, codec, security, timeout và quản lý tài nguyên.
- Event loop không nên bị chiếm bởi JDBC đồng bộ, Thread.sleep, File API chặn lâu hoặc WebClient.block().
- Reactive không tự bảo đảm latency thấp hơn MVC. Lợi ích thường thể hiện rõ ở khả năng mở rộng và hiệu quả tài nguyên khi tải có nhiều I/O chờ.
- Các thao tác CPU nặng vẫn chiếm thời gian xử lý; cần giới hạn concurrency và xem xét scheduler/worker phù hợp.

## 5. WebFlux trên Tomcat hoặc Jetty: Servlet bridge

Tomcat và Jetty đều là Servlet container, nhưng Servlet API từ phiên bản 3.1 cung cấp các khả năng **asynchronous processing** và **non-blocking I/O**. WebFlux sử dụng những khả năng đó thông qua lớp adapter thay vì đưa Servlet API vào code nghiệp vụ.

Luồng khái quát:

~~~text
Client TCP/HTTP
    |
    v
Tomcat / Jetty connector
    |
    v
Servlet container + Servlet non-blocking I/O
    |
    v
ServletHttpHandlerAdapter
    |
    v
Spring HttpHandler
    |
    v
WebFilter / WebHandler / DispatcherHandler
    |
    v
Controller -> Mono/Flux -> HTTP response
~~~

ServletHttpHandlerAdapter nằm tại điểm giao giữa Servlet API và hợp đồng HttpHandler của Spring. Adapter chuyển tín hiệu request/response theo cơ chế Servlet non-blocking I/O tới reactive streams mà WebFlux xử lý.

**Điểm cực kỳ quan trọng:** Có Servlet API ở hạ tầng không làm Servlet API trở thành API lập trình chính của WebFlux. Trong một handler WebFlux, ứng dụng nên làm việc với ServerWebExchange, ServerHttpRequest, ServerHttpResponse, Mono/Flux, WebFilter và các component reactive.

Tài liệu Spring Framework khuyến nghị không map Servlet Filter hoặc thao tác trực tiếp Servlet API như một phần của ứng dụng WebFlux. Việc trộn các nhánh I/O blocking và non-blocking mà không hiểu bridge có thể tạo vấn đề runtime, mất lợi ích concurrency hoặc gây hành vi khác mong đợi.

### 5.1. Tại sao Tomcat/Jetty chạy được cả MVC và WebFlux?

Tomcat/Jetty có cơ chế networking và khả năng non-blocking, trong khi Servlet API hỗ trợ cả những phương thức đồng bộ truyền thống và các API non-blocking. Spring MVC sử dụng Servlet frontend; Spring WebFlux sử dụng một adapter của Servlet non-blocking I/O rồi chuyển request sang reactive pipeline.

Chính **bộ xử lý phía Spring** xác định semantics của framework. Tomcat làm HTTP server không chứng minh DispatcherServlet đang xử lý request. Bạn có thể có ứng dụng WebFlux trên Tomcat mà không tạo một DispatcherServlet nào cho routes reactive.

### 5.2. Servlet Filter có chạy được không?

Về mặt kỹ thuật, container có Servlet chain và một số thành phần hạ tầng có thể tồn tại ở tầng này. Nhưng khi viết ứng dụng WebFlux, **không nên thiết kế middleware nghiệp vụ dựa trên Servlet Filter, HttpServletRequest hoặc ThreadLocal request state**. Điểm mở rộng chuẩn ở tầng WebFlux là WebFilter, WebExceptionHandler và những API reactive tương ứng.

Các chức năng như correlation ID, request logging, authentication, authorization, rate limiting hoặc request mutation phải được đánh giá theo reactive lifecycle. Ví dụ một Servlet Filter tùy biến cũ dựa trên ThreadLocal có thể thất bại khi xử lý chuyển thread hoặc khi request/response hoàn tất bất đồng bộ.

### 5.3. Tại sao khác với deploy WAR truyền thống?

Đây là hai khái niệm dễ lẫn:

- Framework WebFlux có **adapter** để chạy trên Servlet container phù hợp.
- Mô hình **Spring Boot WebFlux application đóng gói và triển khai WAR** vào container bên ngoài không được Boot hỗ trợ như cách Spring MVC truyền thống.

Spring Boot WebFlux thường đóng gói executable JAR và Boot khởi chạy embedded server. Tài liệu Spring Boot nêu rõ việc triển khai WebFlux theo WAR truyền thống không được hỗ trợ. Đừng suy luận rằng chỉ vì WebFlux chạy trên embedded Tomcat, ta có thể triển khai Spring Boot WebFlux WAR như một ứng dụng MVC bất kỳ.

Nếu tổ chức yêu cầu một external Servlet container, phải đánh giá thật kỹ mô hình triển khai và hỗ trợ của framework/version; phương án đơn giản với Boot WebFlux thường là embedded server do Boot quản lý.

## 6. Bảng hỗ trợ theo phiên bản và server

Các tùy chọn phải được gắn với nhánh Spring Boot cụ thể:

| Máy chủ | Spring MVC trên Servlet | WebFlux trong Boot 3.x | WebFlux trong Boot 4.0 | Cơ chế WebFlux |
| --- | --- | --- | --- | --- |
| Tomcat | Có | Có | Có | Servlet non-blocking I/O + adapter |
| Jetty | Có | Có | Có | Servlet non-blocking I/O + adapter |
| Reactor Netty | Không phải Servlet container cho MVC | Có; mặc định WebFlux | Có; mặc định WebFlux | Reactor Netty API + adapter |
| Undertow | Có trong Boot 3.x | Có trong Boot 3.x | **Không còn tích hợp embedded Undertow** | Spring Framework 6.x dùng Undertow API trực tiếp |

**Lưu ý Undertow:** Tài liệu Spring Boot 3.3 liệt kê Undertow cho reactive server và Servlet server. Với WebFlux, Spring Framework 6.x dùng API Undertow trực tiếp, không đi qua cùng đường ServletHttpHandlerAdapter của Tomcat/Jetty. Spring Boot 4.0 yêu cầu baseline Servlet 6.1 và đã bỏ starter/support cho embedded Undertow. Không đưa dependency Undertow từ Boot 3.x sang Boot 4.x rồi kỳ vọng auto-configuration tiếp tục làm việc.

Bảng này mô tả hỗ trợ trong các nhánh được nêu, không bảo đảm mọi tổ hợp version/JDK/HTTP feature hoạt động giống nhau. Trước khi nâng cấp, kiểm tra release notes và managed dependencies của Spring Boot mục tiêu.

## 7. Phân biệt WebFlux và Spring MVC khi cùng có annotation

Hai đoạn code có thể trông rất giống nhau:

~~~java
@RestController
class SampleController {
    @GetMapping("/api/hello")
    public Mono<String> hello() {
        return Mono.just("Hello");
    }
}
~~~

Đoạn này chỉ minh họa controller method. Dùng Mono không tự chứng minh framework hiện tại là WebFlux, bởi Spring MVC cũng hỗ trợ một số kiểu trả kết quả bất đồng bộ/reactive. Xác định web stack bằng cách kiểm tra dependency, application type và context.

Trong Spring Boot thông thường:

- spring-boot-starter-web thiên về Servlet MVC và mặc định nhúng Tomcat.
- spring-boot-starter-webflux thiên về reactive WebFlux và mặc định nhúng Reactor Netty.
- Nếu **cả hai** starter có trong classpath, Spring Boot thường ưu tiên MVC. Tình huống này có thể hợp lý khi MVC controller dùng WebClient.
- Có thể chỉ định spring.main.web-application-type=reactive trong trường hợp có chủ đích, nhưng cần đánh giá xung đột auto-configuration và dependency. Tốt hơn là có classpath rõ ràng cho web stack muốn triển khai.

Cách xác minh đáng tin hơn việc nhìn annotation: quan sát loại ApplicationContext, log startup, dependency tree, server factory và test routing. Đừng dùng tên thread hoặc sự tồn tại của reactor-netty-client một mình để kết luận server.

## 8. WebFilter, DispatcherHandler và các thành phần reactive

Một WebFlux request thường đi qua pipeline:

1. Server nhận byte và phân tích HTTP.
2. Adapter tạo ServerHttpRequest và ServerHttpResponse phản ánh request/response ở tầng reactive.
3. HttpHandler chuyển vào WebHandler chain.
4. WebFilterChain áp dụng các WebFilter được đăng ký.
5. DispatcherHandler tìm handler qua HandlerMapping.
6. HandlerAdapter gọi controller hoặc functional handler thích hợp.
7. Codec đọc/ghi request/response body thông qua publisher.
8. Kết quả được subscribe/xử lý theo vòng đời request và phát ra network adapter.

Spring MVC dùng DispatcherServlet, Servlet Filter và Servlet API. WebFlux dùng DispatcherHandler, WebFilter và ServerWebExchange. Tên hai framework tương tự nhưng object và callback không hoán đổi trực tiếp.

Một WebFilter minh họa thêm response header:

~~~java
@Component
class ApiHeaderFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {
        exchange.getResponse()
                .getHeaders()
                .add("X-API-Stack", "WebFlux");
        return chain.filter(exchange);
    }
}
~~~

Đây là đoạn minh họa bên trong ứng dụng WebFlux; cần import Component, WebFilter, ServerWebExchange, WebFilterChain và Mono. Filter áp dụng được cho WebFlux chạy trên Reactor Netty **và** trên Tomcat/Jetty Servlet bridge. Không cần truy cập HttpServletRequest.

Không nên tạo logic authentication chỉ từ một header tùy ý trong filter minh họa. Với bảo mật, dùng Spring Security reactive và cấu hình quyền truy cập rõ ràng.

## 9. Thread model: ranh giới lớn nhất khi lập trình

### 9.1. Reactor Netty

Reactor Netty tổ chức các event loop để nhận và chuyển tiếp sự kiện I/O. Handler có thể được thực thi trên những thread event loop đó. Một lời gọi blocking dài sẽ giữ thread, làm chậm các request khác đang chia sẻ cùng loop.

Ví dụ **sai**:

~~~java
@GetMapping("/slow")
Mono<String> slow() {
    Thread.sleep(3000); // không biên dịch nếu không xử lý InterruptedException
    return Mono.just("done");
}
~~~

Đoạn trên được dùng để minh họa phản mẫu, không phải code runnable. Ngay cả khi xử lý checked exception, ngủ 3 giây trong request handler vẫn chiếm thread xử lý. Không đưa đoạn này vào ứng dụng WebFlux thật.

Một phản mẫu khác thường gặp:

~~~java
String body = webClient.get()
        .uri("/remote")
        .retrieve()
        .bodyToMono(String.class)
        .block();
~~~

.block() đưa thao tác reactive về kiểu chờ đồng bộ. Ở luồng request WebFlux, đặc biệt trên non-blocking thread, cách này có thể gây IllegalStateException hoặc làm nghẽn tài nguyên, tùy thread và tình huống.

### 9.2. Tomcat/Jetty Servlet bridge

Tomcat/Jetty có pool/thread và cơ chế scheduling riêng để đáp ứng Servlet request và non-blocking I/O. Chạy WebFlux trên Servlet container **không đảm bảo mọi đoạn code có thể blocking thoải mái**. Phần xử lý WebFlux vẫn hướng tới non-blocking. Một blocker trong handler có thể làm cạn thread, tăng latency hoặc gây phản ứng khác tùy adapter.

Không áp dụng một công thức số thread từ Tomcat MVC cho Reactor Netty hoặc ngược lại. Tối ưu concurrency phải dựa vào workload và metric của server đang chạy.

### 9.3. Lối thoát với thư viện bắt buộc blocking

Khi bắt buộc gọi một API đồng bộ, có thể cô lập công việc trên boundedElastic:

~~~java
Mono<String> result = Mono.fromCallable(
        () -> blockingRepository.loadValue())
        .subscribeOn(Schedulers.boundedElastic());
~~~

Đây là đoạn minh họa; blockingRepository phải là một dependency thật, và cần import Mono cùng Schedulers. boundedElastic là một scheduler **có giới hạn**, không phải tài nguyên vô hạn. Nó giúp tránh giữ event-loop bởi API đồng bộ, nhưng không tự biến dependency thành non-blocking và không bảo đảm khả năng hủy lời gọi blocking đang chạy.

Nếu phần lớn ứng dụng là JDBC và API đồng bộ, Spring MVC có thể là lựa chọn đơn giản hơn. Còn nếu cần reactive end-to-end, hãy cân nhắc driver/database client non-blocking và giới hạn concurrency đúng cách.

## 10. Backpressure: hỗ trợ ở đâu và kết thúc ở đâu?

Reactive Streams định nghĩa cơ chế yêu cầu số lượng phần tử giữa Publisher và Subscriber; trong Reactor, Mono/Flux mang semantics này. WebFlux có khả năng xử lý stream theo nhu cầu tiêu thụ và nối với non-blocking I/O.

Tuy nhiên, **backpressure không tự lan xuyên mọi tầng**:

- Với Reactor Netty, adapter chuyển dữ liệu sang mô hình Reactive Streams; phản ứng thực tế còn phụ thuộc network buffering, TCP flow control và cấu hình Netty.
- Với Tomcat/Jetty, Servlet adapter phải cầu nối non-blocking ReadListener/WriteListener và Publisher; việc bridge có chi phí và giới hạn buffering cụ thể.
- Nếu service load toàn bộ kết quả database vào List trước khi trả Flux, upstream đã tiêu thụ bộ nhớ và không có backpressure theo từng bản ghi.
- Nếu publisher tạo dữ liệu nhanh hơn client/network có thể nhận, cần xác minh giới hạn buffer và cancellation.
- Reverse proxy hoặc ingress có thể buffer response trước khi client nhìn thấy dữ liệu; streaming ở server không chứng minh streaming end-to-end qua mọi proxy.

Hãy đo memory, dữ liệu đang queue, response latency, kết nối và cancellation khi làm SSE, streaming upload/download hoặc long-lived responses. Không dùng Flux như một nhãn chứng nhận “không tốn bộ nhớ”.

## 11. Tạo project WebFlux dùng Reactor Netty mặc định

Ví dụ đầy đủ dành cho **Spring Boot 3.3.x, Java 17+**. Điều kiện chạy là JDK 17+, Gradle Wrapper tương thích và truy cập Maven Central. Ví dụ này không dùng spring-boot-starter-web để tránh chọn nhầm MVC.

Cấu trúc project:

~~~text
webflux-server-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        example/
          reactive/
            WebFluxServerApplication.java
            GreetingController.java
      resources/
        application.yml
    test/
      java/
        example/
          reactive/
            GreetingControllerTest.java
~~~

Tệp settings.gradle:

~~~groovy
rootProject.name = 'webflux-server-demo'
~~~

Tệp build.gradle:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Tệp src/main/resources/application.yml:

~~~yaml
spring:
  application:
    name: webflux-server-demo

server:
  port: 8080
~~~

Tệp src/main/java/example/reactive/WebFluxServerApplication.java:

~~~java
package example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebFluxServerApplication.class, args);
    }
}
~~~

Tệp src/main/java/example/reactive/GreetingController.java:

~~~java
package example.reactive;

import java.time.Duration;
import java.util.Map;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/api/hello")
    public Mono<Map<String, String>> hello(
            @RequestParam(defaultValue = "World") String name) {
        return Mono.just(Map.of("message", "Hello, " + name));
    }

    @GetMapping(
            value = "/api/ticks",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> ticks() {
        return Flux.interval(Duration.ofSeconds(1))
                .take(3)
                .map(index -> ServerSentEvent.<String>builder()
                        .data("tick-" + index)
                        .build());
    }
}
~~~

Đây là một ứng dụng Java hoàn chỉnh ở mức ví dụ, tách public main class và controller thành hai tệp. Hàm hello trả Mono chứa JSON DTO dạng Map. Hàm ticks trả tối đa ba Server-Sent Events có nội dung tick-0, tick-1 và tick-2. Flux.interval phát sự kiện theo lịch Reactor, không ngủ chặn event loop để chờ giữa các sự kiện.

### 11.1. Chạy thử

Trên Linux/macOS:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Khi server bind thành công port 8080, gọi:

~~~bash
curl -i "http://localhost:8080/api/hello?name=Lan"
~~~

Status mong đợi là HTTP 200 và body JSON có field:

~~~json
{"message":"Hello, Lan"}
~~~

Thử SSE:

~~~bash
curl -N "http://localhost:8080/api/ticks"
~~~

Sau khoảng một giây giữa các sự kiện, client sẽ nhận các event có data tương ứng tick-0, tick-1 và tick-2 rồi stream kết thúc. Cách hiển thị dòng, header và buffering phụ thuộc client/proxy. Nếu muốn kiểm thử streaming từ xa, cần kiểm tra proxy có giữ buffer hay không.

### 11.2. Kiểm tra server mặc định

Khi chỉ có starter webflux với dependency chuẩn, Spring Boot 3.3 thường chọn Reactor Netty. Kiểm tra bằng:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

và:

~~~bash
./gradlew dependencyInsight --dependency spring-boot-starter-reactor-netty --configuration runtimeClasspath
~~~

Sau đó xem startup log để xác nhận loại server và port. Cùng với HTTP test, đây là bằng chứng mạnh hơn suy đoán từ Mono trong controller.

## 12. Chạy cùng WebFlux application trên Tomcat

Để dùng Tomcat làm HTTP server cho **chính WebFlux application** trên Spring Boot 3.3.x, thay dependencies trong build.gradle:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-webflux') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-reactor-netty'
    }

    implementation 'org.springframework.boot:spring-boot-starter-tomcat'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Giữ nguyên các file Java đã tạo ở phần 11. Starter webflux vẫn cung cấp WebFlux controller, WebFilter và codec. Starter Tomcat cung cấp HTTP server/Servlet adapter; không thêm spring-boot-starter-web chỉ để lấy Tomcat, vì starter web có thể khiến Boot chọn MVC.

Những điều cần kiểm tra:

1. Runtime classpath thực sự có starter Tomcat và những dependency reactive cần thiết.
2. Reactor Netty server dependency đã được thay đúng mục tiêu; nếu có WebClient dùng Reactor Netty client thì cần xem xét connector client riêng.
3. ApplicationContext vẫn là reactive web context, không phải MVC web context.
4. Log cho thấy Tomcat khởi động; GET /api/hello trả cùng JSON.
5. Streaming /api/ticks, cancellation, security và error mapping hoạt động đúng sau khi đổi server.

**Không phải chuyển đổi sang Spring MVC.** Chính controller returning Mono và WebFlux pipeline tiếp tục hoạt động; Tomcat đang cung cấp khả năng non-blocking Servlet I/O cho adapter.

## 13. Chạy cùng WebFlux application trên Jetty

Với Spring Boot 3.3.x, cấu hình theo cùng nguyên tắc:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-webflux') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-reactor-netty'
    }

    implementation 'org.springframework.boot:spring-boot-starter-jetty'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Giữ nguyên GreetingController. Sau khi chạy, kiểm tra server thực sự là Jetty, gửi cùng bộ request và đánh giá thread, timeout, SSE, connection/cancellation.

Không copy property server.tomcat.* sang server.jetty.* bằng cách đổi tên tùy tiện. Cấu hình chung server.port có ý nghĩa cho cả hai, nhưng thread pool/connector/idle timeout có namespace và semantics riêng. Đọc property list của đúng phiên bản Boot trước khi điều chỉnh.

## 14. Undertow: ví dụ chỉ áp dụng nhánh hỗ trợ

Spring Boot 3.3 vẫn liệt kê Undertow là embedded reactive server. Khác với Tomcat/Jetty, Spring Framework 6.x dùng API Undertow trực tiếp cho WebFlux; nó không dùng ServletHttpHandlerAdapter trong cùng cách mô tả.

Với project Boot 3.x, ví dụ phụ thuộc minh họa:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-webflux') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-reactor-netty'
    }

    implementation 'org.springframework.boot:spring-boot-starter-undertow'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Một số tài liệu Boot 3.x trình bày module replacement khi chuyển Reactor Netty sang Undertow để xử lý transitive dependencies; với build cụ thể cần kiểm tra dependency resolution và tránh đồng thời có hai web server factory không mong muốn.

**Spring Boot 4.0:** Undertow không còn được hỗ trợ như embedded server. Khi nâng cấp từ Boot 3.x, cần chọn Tomcat, Jetty hoặc Reactor Netty đúng ứng dụng, cập nhật dependencies và cấu hình, sau đó chạy lại integration tests. Không xem một ví dụ Boot 3.x là hợp đồng tương thích của Boot 4.x.

## 15. Nếu dùng WebClient thì server có tự trở thành Netty không?

Không. WebClient là HTTP **client**, độc lập với vai trò HTTP server nhận inbound requests. Một ứng dụng Spring MVC trên Tomcat có thể dùng WebClient Reactor Netty để gọi API khác; điều đó không khiến inbound server trở thành Reactor Netty.

Tương tự, một WebFlux application dùng Tomcat/Jetty có thể cần Reactor Netty hoặc một client connector khác cho outbound WebClient, tùy dependency và cấu hình. Vì vậy, việc tìm thấy jar reactor-netty trên classpath chưa đủ để xác định inbound server. Xem server factory, context và startup log.

Khi có nhiều implementation cùng tồn tại, cần tránh trông chờ cơ chế chọn tự động không được xác minh. Điều chỉnh transitive exclusions/dependency cho rõ mục tiêu và kiểm tra HTTP server factory được Boot tạo.

## 16. Testing: kiểm tra hành vi WebFlux độc lập với server

### 16.1. WebTestClient ở tầng web

WebTestClient cho phép gửi HTTP request kiểm thử WebFlux; nó có thể bind trực tiếp với application context mà không mở socket thật hoặc kết nối đến server chạy trên port ngẫu nhiên.

Kiểm thử ở tầng web giúp xác minh:

- Route /api/hello và /api/ticks tồn tại.
- JSON body, HTTP status, content type và mapping đúng.
- Controller trả Mono/Flux theo hợp đồng.
- Validation, codec và exception handler được gọi theo pipeline WebFlux.

Nhưng mock/bind-to-context test không chứng minh Tomcat/Jetty/Netty listener thực sự nhận kết nối.

### 16.2. Integration test qua HTTP thật

Để kiểm tra server đang chạy và HTTP adapter thực tế, dùng @SpringBootTest(webEnvironment = RANDOM_PORT) với WebTestClient. Tệp src/test/java/example/reactive/GreetingControllerTest.java:

~~~java
package example.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class GreetingControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void helloIsExposedOverHttp() {
        client.get()
                .uri("/api/hello?name=Lan")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message")
                .isEqualTo("Hello, Lan");
    }

    @Test
    void missingNameUsesDefault() {
        client.get()
                .uri("/api/hello")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message")
                .isEqualTo("Hello, World");
    }
}
~~~

Trong Spring Boot 3.3.x, annotation và API nêu trên phù hợp cho ví dụ. Test khởi tạo embedded web server thật trên một port ngẫu nhiên, client gửi request tới server. Chạy lại cùng bộ test sau khi thay starter Netty sang Tomcat/Jetty để xác minh hợp đồng HTTP không đổi.

~~~bash
./gradlew test
~~~

Đừng kết luận toàn bộ công nghệ đã tương thích chỉ từ hai test GET đơn giản. Với ứng dụng có streaming, multipart, WebSocket, TLS hoặc proxy, phải bổ sung test tương ứng.

### 16.3. Kiểm thử SSE và streaming

Với SSE, hãy kiểm tra bằng WebTestClient hoặc HTTP client có khả năng xử lý stream từng phần:

- Header Content-Type là text/event-stream.
- Nhận đúng ba event và thứ tự.
- Client có thể hủy subscribe/ngắt kết nối và server giải phóng nguồn phát.
- Proxy không buffer toàn bộ response nếu hợp đồng yêu cầu streaming.
- Không để một request slow consumer tích tụ buffer không giới hạn.

SSE có thể hoạt động trên Reactor Netty và Servlet container phù hợp, nhưng chi tiết flush, kết nối và buffering có thể khác; cần test qua mạng/ingress thật khi triển khai.

## 17. Sự khác nhau khi xử lý request body và codec

WebFlux dùng các HttpMessageReader và HttpMessageWriter bên dưới các codec để đọc/ghi request/response theo kiểu reactive. Đối tượng như Mono<MyDto> hoặc Flux<MyDto> được binding theo publisher, khác cách controller MVC thường đọc body thông qua HttpMessageConverter truyền thống.

Đọc toàn bộ body rồi gom vào List có thể làm mất ưu điểm streaming. Với request body lớn, cần hiểu giới hạn memory buffering và cách xử lý multipart, streaming và codec. Spring Boot cung cấp thuộc tính cấu hình codec như spring.codec.max-in-memory-size trong các phiên bản hỗ trợ, nhưng phải đối chiếu application properties theo phiên bản đang chạy.

Không nhầm Content-Type của request với Accept của response; hai header này tham gia chọn codec ở hai chiều khác nhau. Khi có lỗi 400, 406 hoặc 415, xem media type, mapping, codec và exception chain trước khi nghi ngờ server adapter.

### 17.1. Chuyển server có đổi JSON output không?

Thông thường không nếu application WebFlux, object, codec và cấu hình Jackson giữ nguyên. Nhưng không nên suy ra mọi header, transfer encoding, compression, connection handling hoặc streaming flush đều đồng nhất. Chúng có thể phụ thuộc server/connector và môi trường proxy.

## 18. Spring Security trên WebFlux-on-Servlet

Nếu ứng dụng là WebFlux, hãy sử dụng Spring Security cho reactive stack:

- SecurityWebFilterChain và ServerHttpSecurity cho web authorization.
- ReactiveSecurityContextHolder để truy cập thông tin security theo reactive context khi thích hợp.
- WebFilter và ServerWebExchange cho request/response và middleware.
- Reactive authentication/authorization phù hợp với Publisher nếu xử lý bất đồng bộ.

Servlet SecurityFilterChain/HttpSecurity thuộc MVC/Servlet configuration; không tự động coi nó là cấu hình chính cho WebFlux chỉ vì inbound server là Tomcat.

Một custom Servlet Filter cũ có thể được container thực thi ở tầng thấp, nhưng việc kết hợp nó với WebFlux không phải con đường mặc định được khuyên dùng. Cần rà soát security chain và adapter, vì sai phân tầng có thể gây bỏ sót authentication hoặc xử lý lỗi ở thời điểm không đúng.

Không dùng raw client header để tự xác thực tenant hoặc user. Dù WebFlux chạy server nào, thông tin identity/permission phải đến từ cơ chế authentication đã kiểm chứng.

## 19. Session, request context và ThreadLocal

Ứng dụng MVC Servlet thường phụ thuộc request attributes và ThreadLocal trong nhiều thư viện cũ. Trên WebFlux, xử lý có thể tiếp tục qua thread khác theo signals/scheduler, nên một ThreadLocal không mặc nhiên đi theo request.

Dùng:

- ServerWebExchange.getAttributes() cho các thuộc tính gắn với exchange.
- WebSession API của WebFlux nếu cần session.
- Reactor Context cho dữ liệu cần lan theo chuỗi reactive.
- API context propagation được framework/libraries hỗ trợ nếu tích hợp tracing/security.

Không lưu thông tin request trong static mutable field hoặc một singleton Bean. Không dựa vào việc quan sát thấy cùng thread ở một phép thử nhỏ rồi thiết kế logic phải chạy trên đúng thread đó.

Khi chuyển ứng dụng từ MVC sang WebFlux, rà soát MDC logging, security context, transaction context và các thư viện dựa ThreadLocal. Dùng framework integration thay vì tự chép context bằng tay thiếu cleanup.

## 20. Thread, connection pool và resource tuning

### Trên Reactor Netty

Reactor Netty thường dùng event-loop resources cho server. Một số client WebClient cũng có thể dùng tài nguyên Reactor Netty và chia sẻ tài nguyên trong những cấu hình mặc định. Cần quan sát:

- Số connection đang mở, accept rate và network errors.
- Event-loop pressure và request latency.
- Byte buffer và memory ngoài heap.
- CPU, GC, blocking call và scheduler saturation.
- Cancellation/timeout và downstream client pool.

### Trên Tomcat/Jetty

Server có connector, thread pool và non-blocking I/O adapter. Cần quan sát:

- Acceptor/worker threads, request queue và connection backlog.
- Async request lifecycle, timeout và completion/cancellation.
- Connection pool cho downstream.
- Thread bị giữ lâu do blocking API.
- Network buffering và client ngắt kết nối.

### Ranh giới chung

Không có cấu hình số thread “chuẩn” cho mọi server. Property server.tomcat.* không áp dụng cho Netty, và server.netty.* không tự đổi cấu hình Tomcat. Trước khi tuning, dùng baseline workload/metric giống nhau và kiểm tra bottleneck thực sự ở server hay dependency khác.

## 21. Giới hạn giao thức và deployment cần xác minh

Khi thay runtime, xác minh những tính năng mà ứng dụng dùng:

| Chức năng | Điều cần kiểm tra |
| --- | --- |
| HTTP/1.1 keep-alive | Timeout, connection reuse, maximum connections |
| HTTP/2 | Server dependency, TLS/ALPN, proxy/ingress |
| TLS | Termination tại server hay proxy, certificate, rotation |
| Compression | Config và Content-Type/size được hỗ trợ |
| SSE/streaming | Chunk flush, buffering, client cancellation |
| WebSocket | Handshake/upgrade và session lifecycle |
| Multipart/upload | Size limits, temp storage và streaming |
| Large response | Backpressure, memory/buffer limits |
| Forwarded headers | Trusted proxy, scheme, host và client IP |
| Access logs | Format, request ID, tránh rò secret |
| Graceful shutdown | Ngừng nhận request mới, drain và timeout |
| Health/readiness | Chỉ nhận traffic khi instance thực sự sẵn sàng |

Với Spring Boot WebFlux, thuộc tính server.port và một số cấu hình chung có thể dùng trên nhiều server. Các tùy chọn server-specific cần kiểm tra đúng Boot version. Tránh xem sự tồn tại của cùng một property name là bằng chứng hai server sẽ có behavior hoàn toàn giống nhau.

### 21.1. WebFlux và reverse proxy

Ingress có thể kết thúc TLS, nén response, giữ buffer hoặc thay đổi HTTP version. Một route WebFlux streaming có thể tạo event từng giây nhưng client chỉ nhìn thấy sau nhiều giây vì proxy buffering. Khi điều tra, kiểm tra cả ứng dụng, server adapter, network và proxy, không quy mọi trễ về Reactor Netty hoặc Tomcat.

## 22. Những sai lầm phổ biến

| Nhầm lẫn | Thực tế | Hướng sửa |
| --- | --- | --- |
| WebFlux chỉ chạy Netty | WebFlux có adapter Servlet cho Tomcat/Jetty | Tách web framework và HTTP server |
| Chạy trên Tomcat tức là MVC | WebFlux-on-Tomcat vẫn dùng DispatcherHandler | Kiểm tra ApplicationContext và framework |
| Chỉ cần trả Mono là đã reactive | MVC cũng có thể hỗ trợ kiểu phản hồi reactive | Kiểm tra starter và request pipeline |
| Có WebClient là server dùng Netty | WebClient là HTTP client | Kiểm tra inbound server factory |
| Servlet Filter là middleware chuẩn của WebFlux-on-Tomcat | WebFlux nên dùng WebFilter | Thay/rà soát middleware theo reactive API |
| Dùng ThreadLocal giống MVC | Reactive chain có thể đổi thread | Dùng Reactor Context/ServerWebExchange |
| Netty bảo đảm mọi dependency non-blocking | JDBC, file I/O, SDK vẫn có thể blocking | Dùng non-blocking driver hoặc cô lập blocking |
| Mono/Flux tự bảo đảm end-to-end backpressure | Codec, proxy, DB và network buffering có giới hạn | Test streaming, cancellation, memory |
| WebFlux trên Tomcat deploy WAR như MVC | Boot WebFlux WAR truyền thống không được hỗ trợ | Dùng executable JAR/embedded server |
| Undertow luôn có trong mọi Boot version | Boot 4.0 bỏ tích hợp Undertow | Chọn server được version hỗ trợ |
| Đổi starter không cần test | Server adapter ảnh hưởng network behavior | Test routing, body, streaming, TLS, security |
| Reactor Netty luôn nhanh hơn Tomcat | Hiệu quả phụ thuộc workload và blocking | Benchmark có kiểm soát |
| Cứ tăng thread là xử lý được nghẽn | DB pool, CPU hoặc downstream có thể là nút thắt | Đo thread/connection/latency thực tế |

## 23. Quy trình chọn và chuyển server an toàn

Một quy trình kỹ thuật rõ ràng:

1. **Xác định ứng dụng là MVC hay WebFlux.** Kiểm tra runtime classpath và Spring context, không chỉ tên annotation.
2. **Xác định phiên bản Boot.** Với Boot 4.x, loại Undertow khỏi danh sách chọn embedded server chính thức.
3. **Xác định dependency I/O:** JDBC, Redis, Kafka, filesystem, SDK và HTTP client là blocking hay non-blocking.
4. **Bắt đầu từ mặc định hợp lý:** Reactor Netty cho WebFlux; Tomcat/Jetty chỉ khi có lý do tích hợp, vận hành hoặc kết quả test phù hợp.
5. **Đổi starter đúng cách:** loại server mặc định khi cần, thêm server mong muốn; không vô tình thêm starter MVC.
6. **Kiểm tra web stack sau đổi:** Spring reactive application context, WebFlux route mapping, WebFilter và Spring Security reactive.
7. **Kiểm tra server:** startup log, dependency tree, bean factory và port đã bind.
8. **Chạy regression tests:** request/response JSON, status, error, security, SSE/WebSocket nếu dùng.
9. **Load test và quan sát:** p50/p95/p99, connection count, memory, CPU, thread, event loop, queue, cancellation và timeout.
10. **Deploy theo từng bước:** health/readiness, graceful shutdown, rollback và khả năng so sánh metric trước/sau.

Chuyển **HTTP server** trong một WebFlux app thường ít ảnh hưởng controller hơn việc chuyển **web framework** từ MVC sang WebFlux. Nhưng cả hai đều cần kiểm chứng runtime, đặc biệt trong những ứng dụng phụ thuộc server-specific settings.

## 24. Bài thực hành tổng hợp

**Bối cảnh:** Một nhóm đang chạy API reactive với Spring WebFlux và muốn biết việc chuyển từ Reactor Netty sang Tomcat có làm thay đổi semantics của API không.

Thực hiện lần lượt:

1. Tạo project ở phần 11 với starter webflux và Reactor Netty mặc định.
2. Ghi lại runtime dependency, loại application context, log startup, HTTP status/body của /api/hello và kết quả /api/ticks.
3. Thêm WebFilter gắn response header X-API-Stack=WebFlux; xác minh header xuất hiện.
4. Chạy integration tests bằng WebTestClient trên cổng ngẫu nhiên.
5. Đổi dependency như phần 12 để WebFlux chạy Tomcat; giữ nguyên controller và WebFilter.
6. Kiểm tra application context vẫn là reactive, nhưng startup log cho thấy HTTP server là Tomcat.
7. Chạy lại tests GET, JSON, SSE, WebFilter, lỗi request và cancellation.
8. Thử Jetty tương tự, nếu có thời gian; ghi rõ version starter và JDK.
9. Nếu hệ thống có blocking API, thêm một phép thử có thể thấy được saturation khi concurrency tăng; sau đó tách blocking ra scheduler giới hạn hoặc thay dependency reactive.
10. Ghi bảng so sánh theo cùng cấu hình CPU/memory và cùng request load.

Bảng kết quả cần có:

| Tiêu chí | Reactor Netty | Tomcat + Servlet bridge | Jetty + Servlet bridge |
| --- | --- | --- | --- |
| Web stack | WebFlux | WebFlux | WebFlux |
| HTTP server | Reactor Netty | Tomcat | Jetty |
| Adapter | Reactor Netty -> HttpHandler | Servlet -> HttpHandler | Servlet -> HttpHandler |
| Controller code | Giữ nguyên | Giữ nguyên | Giữ nguyên |
| WebFilter | Hoạt động | Phải test | Phải test |
| API JSON | Test | Test | Test |
| SSE/cancellation | Test | Test | Test |
| Server-specific tuning | Netty | Tomcat | Jetty |

Không điền số latency hoặc throughput tưởng tượng. Chỉ kết luận sau khi có số đo trên cùng workload, tương thích JDK, cùng tài nguyên và có nhiều lần chạy.

## 25. Câu hỏi tự đánh giá

1. Tại sao WebFlux có thể chạy trên Tomcat nhưng không trở thành Spring MVC?
2. HttpHandler đóng vai trò gì trong khả năng hỗ trợ nhiều HTTP server?
3. ReactorHttpHandlerAdapter và ServletHttpHandlerAdapter nối hai loại API khác nhau như thế nào?
4. WebHandler/DispatcherHandler khác DispatcherServlet về web stack ra sao?
5. Vì sao API Servlet không được khuyến khích sử dụng trực tiếp trong business handler WebFlux?
6. WebFilter và Servlet Filter phục vụ những lớp pipeline nào?
7. Khi nào có thể giữ nguyên WebFlux controller dù thay Netty bằng Jetty?
8. Nếu có cả starter web và webflux, tại sao không thể suy luận stack chỉ từ Mono trong controller?
9. WebFlux trên Tomcat có nghĩa là Spring Boot WebFlux hỗ trợ WAR deployment truyền thống không?
10. Vì sao Undertow xuất hiện trong tài liệu Spring Boot 3.x nhưng không còn trong Boot 4.0?
11. Vì sao JDBC blocking hoặc WebClient.block() có thể làm nghẽn reactive request processing?
12. Đâu là khác biệt giữa Reactive Streams backpressure và buffering của TCP/proxy?
13. Khi nào mock WebTestClient đủ, khi nào phải chạy HTTP server thật?
14. Nếu chuyển server làm lỗi SSE nhưng GET JSON vẫn pass, cần kiểm tra những gì?
15. Làm sao biết một performance improvement đến từ server, chứ không phải JDK hoặc data/cache?
16. Tại sao WebClient dùng Netty không đồng nghĩa inbound server là Reactor Netty?
17. Cần làm gì khi Spring Security MVC cũ đang dựa vào Servlet Filter và ThreadLocal?
18. Những phần nào của application.properties có thể dùng chung, phần nào là server-specific?

## 26. Tài liệu chính thức

- [Spring Framework – WebFlux Overview](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html): server hỗ trợ, performance, concurrency và ranh giới Servlet.
- [Spring Framework – Reactive Core](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): HttpHandler, WebHandler và các server adapter.
- [Spring Boot 3.3 – Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): đổi server, dependency, factory và HTTP options.
- [Spring Boot 3.3 – Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): cấu hình ứng dụng WebFlux.
- [Spring Boot 4.0 – Embedded Web Servers](https://docs.spring.io/spring-boot/4.0/how-to/webserver.html): lựa chọn embedded server ở Boot 4.0.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): Undertow removal và những thay đổi phiên bản.
- [Spring Boot – Traditional Deployment](https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html): giới hạn WAR deployment với WebFlux.
- [Reactor Netty](https://spring.io/projects/reactor-netty/): mô hình network non-blocking và Reactor integration.

Khi áp dụng vào dự án, hãy kiểm tra đúng phiên bản Spring Boot/Spring Framework/JDK và chạy test qua mạng thật. Giới hạn của một HTTP server không chỉ do API framework mà còn do dependency, các adapter, proxy và cách ứng dụng thực sự sử dụng I/O.

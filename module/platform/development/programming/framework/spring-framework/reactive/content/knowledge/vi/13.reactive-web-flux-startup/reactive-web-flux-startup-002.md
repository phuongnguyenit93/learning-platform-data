# Vai trò của spring-web, spring-webflux và Reactor Netty

## 1. Bức tranh tổng thể: ba thành phần ở ba tầng khác nhau

Khi khởi động một ứng dụng Spring WebFlux, các dependency thường xuất hiện cạnh nhau:

- **spring-web**: nền tảng web chung của Spring, cung cấp HTTP abstractions, codec contracts và nhiều thành phần hạ tầng web; đây cũng là nền reactive mà WebFlux xây dựng trên đó.
- **spring-webflux**: framework web reactive của Spring, định nghĩa cách nhận request, định tuyến tới handler/controller, đọc/ghi body và trả dữ liệu bằng các kiểu reactive như Mono/Flux.
- **Reactor Netty**: thư viện networking tích hợp Project Reactor với Netty, cung cấp HTTP client/server non-blocking. Spring Boot thường chọn nó làm embedded server mặc định khi dùng WebFlux.

~~~text
                 ỨNG DỤNG SPRING BOOT
                           |
                           v
               spring-boot-starter-webflux
                           |
              +------------+-------------+
              |                          |
              v                          v
          spring-web                spring-webflux
       HTTP abstraction           Reactive web framework
       codecs / WebHandler        DispatcherHandler / handlers
              |                          |
              +------------+-------------+
                           |
                 HTTP server adapter
                           |
                           v
                    Reactor Netty
                           |
                           v
                     Netty / TCP
                           |
                           v
                       Mạng
~~~

Đây là **sơ đồ khái niệm**, không phải dependency tree Maven đầy đủ. Starter còn kéo theo các thư viện nền và cấu hình tự động. Cần nhớ: **spring-web cung cấp nền web và reactive contracts; spring-webflux cung cấp mô hình xử lý web reactive; Reactor Netty thực hiện networking khi được chọn làm runtime**.

Ba thành phần không phải ba tên gọi thay thế cho nhau. Nhầm tầng dễ dẫn đến thêm dependency không cần thiết, cấu hình sai server hoặc nghĩ rằng phải dùng Netty mới viết được controller WebFlux.

## 2. spring-web: nền tảng web chung của Spring

### 2.1. Artifact và trách nhiệm

Maven artifact:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-web</artifactId>
</dependency>
~~~

Trong ứng dụng Spring Boot, thông thường **không cần khai báo riêng** nếu đã dùng starter phù hợp. Dependency management của Boot sẽ đưa phiên bản tương thích vào classpath.

spring-web là module nền tảng, chứa các abstraction và tiện ích web được những framework web khác sử dụng:

- **HTTP abstraction**: request, response, header, status, media type, cookie, URI và các kiểu liên quan.
- **HTTP message conversion và codec contracts**: hợp đồng đọc/ghi nội dung request/response và các kiểu dữ liệu được hỗ trợ.
- **WebHandler infrastructure**: abstraction cốt lõi cho đường xử lý web non-blocking mà WebFlux dùng.
- **Web utilities**: URI, CORS, HTTP caching, multipart và các tiện ích web chung.
- **Annotation và contract dùng chung**: các annotation như @RequestMapping, @GetMapping, @RequestBody, @ResponseBody và kiểu hỗ trợ controller.
- **Client-side abstraction**: các hợp đồng HTTP client như ClientHttpRequest, ClientHttpResponse và ClientHttpConnector.

spring-web **không phải HTTP server độc lập**. Nó cung cấp abstraction và hạ tầng; để nhận kết nối mạng thật, ứng dụng cần một runtime/server phù hợp hoặc được triển khai trong container có sẵn.

### 2.2. spring-web không đồng nghĩa với Spring MVC

Dễ nhầm ba artifact:

| Artifact | Vai trò |
| --- | --- |
| **spring-web** | Nền tảng web chung và các abstraction dùng chung |
| **spring-webmvc** | Framework Spring MVC dựa trên Servlet API |
| **spring-webflux** | Framework web reactive của Spring |

spring-web có thể được dùng bởi cả Spring MVC và WebFlux. Còn spring-webmvc và spring-webflux là hai web stack khác nhau, có thể tồn tại cạnh nhau trong hệ sinh thái Spring.

Vì vậy, nhìn thấy @RestController hoặc @GetMapping chưa đủ kết luận ứng dụng đang chạy MVC hay WebFlux. Cần xem dependency, application type và runtime.

## 3. spring-webflux: framework xử lý HTTP theo mô hình reactive

### 3.1. Artifact và chức năng

Artifact chính:

~~~xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-webflux</artifactId>
</dependency>
~~~

Với Spring Boot, cách thông thường là dùng starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

spring-boot-starter-webflux kéo các thành phần WebFlux cần thiết và kích hoạt auto-configuration. Không cần tự ghép từng artifact nếu mục tiêu là tạo ứng dụng Boot thông thường.

Spring WebFlux cung cấp:

1. **Reactive request handling**: xử lý request/response với hợp đồng non-blocking.
2. **DispatcherHandler**: điều phối request tới handler phù hợp.
3. **Annotated controllers**: dùng @RestController, @GetMapping, @PostMapping và các annotation quen thuộc.
4. **Functional endpoints**: mô hình RouterFunction/HandlerFunction, khai báo route và hàm xử lý theo phong cách functional.
5. **Reactive codecs**: đọc/ghi JSON, text, byte stream và các kiểu nội dung theo luồng.
6. **WebClient**: HTTP client reactive với API fluent, trả Mono/Flux và hỗ trợ streaming.
7. **WebFilter và exception handling**: lọc request, xử lý lỗi, CORS và các hạ tầng web khác.
8. **Reactive Streams integration**: phối hợp demand/backpressure tại những ranh giới Publisher/Subscriber hỗ trợ.

### 3.2. Hai phong cách lập trình

**Annotated controller** gần với Spring MVC:

~~~java
@RestController
class GreetingController {
    @GetMapping("/hello")
    Mono<String> hello() {
        return Mono.just("Hello WebFlux");
    }
}
~~~

**Functional endpoint** khai báo route và handler tường minh:

~~~java
@Bean
RouterFunction<ServerResponse> routes(GreetingHandler handler) {
    return RouterFunctions.route()
            .GET("/hello", handler::hello)
            .build();
}
~~~

Đây là các đoạn mã minh họa cần đặt trong ứng dụng WebFlux đã cấu hình bean và import. Cả hai phong cách đều thuộc spring-webflux; lựa chọn tùy cách tổ chức code và nhu cầu dự án.

### 3.3. Mono và Flux trong controller

Controller WebFlux thường trả:

- **Mono<T>** khi có tối đa một kết quả hoặc một phản hồi.
- **Flux<T>** khi có 0 đến nhiều phần tử, có thể phát dần theo thời gian.

~~~java
@GetMapping("/profile")
Mono<Profile> profile() {
    return profileService.findProfile();
}

@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<Event> events() {
    return eventService.streamEvents();
}
~~~

Đây là đoạn minh họa với Profile, Event và service do ứng dụng cung cấp. WebFlux không yêu cầu controller tự gọi subscribe() hoặc block() để lấy kết quả. Framework điều phối subscription và ghi response theo vòng đời HTTP. Gọi block() trên event loop có thể làm nghẽn nhiều request khác.

## 4. Reactor Netty: tầng networking non-blocking

### 4.1. Netty, Reactor Core và Reactor Netty

**Netty** là framework networking bất đồng bộ, hướng sự kiện, dùng để xây dựng client/server mạng.

**Project Reactor Core** cung cấp mô hình reactive với Mono, Flux, Scheduler và operator.

**Reactor Netty** kết hợp hai nền tảng này: cung cấp networking non-blocking có thể tích hợp trực tiếp với Reactor types. Nó hỗ trợ HTTP và các giao thức mạng khác, phù hợp với event-loop và xử lý dữ liệu theo luồng.

Artifact thường gặp:

~~~xml
<dependency>
    <groupId>io.projectreactor.netty</groupId>
    <artifactId>reactor-netty-http</artifactId>
</dependency>
~~~

Trong Spring Boot, starter tương ứng thường là spring-boot-starter-reactor-netty. Khi dùng starter WebFlux mặc định, Boot thường đưa Reactor Netty vào để cung cấp embedded HTTP server.

### 4.2. Reactor Netty làm gì?

Khi được chọn làm server runtime, Reactor Netty đảm nhận phần network:

- Mở cổng và nhận kết nối TCP.
- Quản lý socket, event loop và I/O non-blocking.
- Xử lý HTTP protocol ở tầng transport/server.
- Chuyển request/response mạng thành abstraction mà Spring WebFlux làm việc.
- Ghi dữ liệu response trở lại socket; hỗ trợ streaming và phối hợp với reactive demand tại các tầng tương ứng.

Reactor Netty **không quyết định controller nào được gọi hoặc business logic nào chạy**. Định tuyến và xử lý request thuộc Spring WebFlux. Netty cũng không thay thế Reactor Core: Mono/Flux là kiểu của Reactor Core, còn Reactor Netty là tích hợp networking với Reactor.

### 4.3. Reactor Netty cũng có thể làm HTTP client

Không chỉ server, Reactor Netty còn có thể là connector cho WebClient:

~~~text
Ứng dụng Service
      |
      v
   WebClient
      |
      v
ClientHttpConnector
      |
      v
Reactor Netty HttpClient
      |
      v
Netty / Socket / TLS
      |
      v
Remote HTTP service
~~~

WebClient là API client ở tầng Spring. Reactor Netty có thể là implementation thực hiện I/O mạng bên dưới. WebClient cũng hỗ trợ các HTTP client implementation khác, tùy phiên bản và dependency được cấu hình.

## 5. Một request HTTP đi qua những thành phần nào?

Giả sử client gửi:

~~~http
GET /hello HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

Luồng xử lý ở mức khái niệm:

1. **Reactor Netty** nhận kết nối và dữ liệu HTTP từ socket.
2. Adapter đưa request vào abstraction của Spring WebFlux.
3. **spring-web / WebFlux infrastructure** cung cấp HTTP request/response, filter và codec contracts.
4. **DispatcherHandler** tìm handler qua HandlerMapping.
5. Controller hoặc functional handler thực hiện nghiệp vụ và trả **Mono/Flux**.
6. Codec của Spring chuyển đối tượng thành JSON, text hoặc stream phù hợp.
7. Runtime server ghi response ra socket; nếu là Flux stream, dữ liệu có thể phát từng phần theo vòng đời Publisher.

~~~text
TCP socket
    |
    v
Reactor Netty
    |
    v
Spring HTTP adapter / HttpHandler
    |
    v
WebFilter chain
    |
    v
DispatcherHandler
    |
    +--> HandlerMapping
    |
    +--> HandlerAdapter / Controller
    |           |
    |           v
    |        Mono / Flux
    |
    v
HttpMessageWriter / Codec
    |
    v
Reactor Netty response
    |
    v
TCP socket
~~~

Sơ đồ lược bỏ nhiều thành phần như security, observation, error handling, multipart và resource management. Mục tiêu là phân biệt **tầng mạng**, **hạ tầng HTTP** và **mô hình xử lý request**.

## 6. Vì sao WebFlux thường đi cùng Reactor Netty?

Spring WebFlux cần một server runtime để tiếp nhận và gửi HTTP. Reactor Netty là lựa chọn mặc định phổ biến trong Spring Boot vì:

- Cung cấp I/O non-blocking và event loop phù hợp với reactive model.
- Tích hợp với Reactor Core và WebClient.
- Có cả client và server implementation.
- Có thể chia sẻ một số network resources giữa client và server khi cùng dùng Reactor Netty và cấu hình Boot mặc định.
- Hỗ trợ streaming và các giao thức HTTP hiện đại.

Tuy nhiên, **WebFlux không bị khóa vào Reactor Netty**. Framework hỗ trợ nhiều runtime, gồm server dựa trên Servlet như Tomcat/Jetty và các lựa chọn khác tùy phiên bản Spring Boot. Khi chạy WebFlux trên Servlet container, WebFlux vẫn giữ contract reactive/non-blocking của mình; adapter kết nối framework với API của container.

Có hai quyết định độc lập:

- **Chọn programming model:** Spring MVC hay Spring WebFlux?
- **Chọn server runtime:** Tomcat, Jetty, Reactor Netty hoặc runtime được hỗ trợ khác?

Không nên suy ra “dùng Netty thì bắt buộc WebFlux” hoặc “dùng Tomcat thì chỉ có MVC”.

## 7. Spring MVC, WebFlux và trường hợp chỉ cần WebClient

### 7.1. So sánh hai web stack

| Tiêu chí | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Artifact chính | spring-webmvc | spring-webflux |
| Nền web | Servlet API | Reactive HTTP handling; chạy trên Netty hoặc Servlet runtime |
| Kiểu return | Thường object/ResponseEntity; cũng hỗ trợ async/reactive types | Mono/Flux là kiểu tự nhiên |
| I/O | Mô hình MVC thường blocking theo request thread | Non-blocking end-to-end khi các tầng đều hỗ trợ |
| Streaming | Có hỗ trợ streaming/async | Streaming là phần cốt lõi của reactive model |
| Use case | CRUD truyền thống, thư viện blocking | Nhiều I/O đồng thời, streaming, reactive pipeline |

**MVC không phải framework lỗi thời.** Nếu ứng dụng dùng JDBC blocking, thư viện đồng bộ và tải vừa phải, Spring MVC có thể đơn giản và dễ vận hành hơn. WebFlux hữu ích khi cần nhiều I/O concurrent, streaming hoặc hệ sinh thái non-blocking xuyên suốt.

### 7.2. Chỉ cần WebClient không đồng nghĩa phải chuyển server sang WebFlux

Ứng dụng Spring MVC vẫn có thể dùng **WebClient** để gọi dịch vụ khác theo kiểu reactive. Đây là một lý do phổ biến khiến dependency WebFlux xuất hiện trong ứng dụng MVC.

Với Spring Boot 3.x, nếu classpath có cả **spring-boot-starter-web** và **spring-boot-starter-webflux**, Boot thường tự cấu hình **Spring MVC** làm application type mặc định. Bạn vẫn có thể dùng WebClient trong ứng dụng đó.

Nếu muốn server chạy WebFlux trong trường hợp có cả hai starter, có thể chỉ định application type:

~~~java
SpringApplication app = new SpringApplication(DemoApplication.class);
app.setWebApplicationType(WebApplicationType.REACTIVE);
app.run(args);
~~~

Đây là đoạn cấu hình minh họa. Với dự án thông thường, tốt nhất chỉ thêm starter của web stack đã chọn để dependency tree dễ hiểu.

## 8. Cấu hình dependency trong Spring Boot

### 8.1. WebFlux starter

Ví dụ Maven với Spring Boot **3.5.5** và Java 17+:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-stack-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

Với starter trên, Boot quản lý phiên bản tương thích và tự động cấu hình WebFlux cùng server runtime mặc định là Reactor Netty. **Không cần khai báo spring-web, spring-webflux, reactor-core và reactor-netty-http từng món** trong ứng dụng Boot thông thường.

Ví dụ khóa version **3.5.5** để tái lập. Dự án mới nên dùng Spring Boot release được tổ chức phê duyệt và cập nhật theo dependency policy; không trộn tùy ý version Spring Framework, Reactor và Netty.

### 8.2. Xem dependency thực tế

Chạy:

~~~bash
mvn dependency:tree
~~~

Hoặc lọc artifact quan tâm:

~~~bash
mvn dependency:tree -Dincludes=org.springframework:spring-web,org.springframework:spring-webflux,org.springframework:spring-webmvc,io.projectreactor.netty:reactor-netty-http
~~~

Khi đọc kết quả:

- **spring-web** là nền tảng web.
- **spring-webflux** là reactive web stack.
- **spring-webmvc** xuất hiện nếu ứng dụng kéo thêm MVC starter hoặc dependency khác.
- **reactor-netty-http** là implementation HTTP của Reactor Netty.
- Dependency xuất hiện không tự chứng minh nó đang là server runtime; cần xem auto-configuration và application type.

### 8.3. Đổi server runtime

Nếu muốn chạy WebFlux trên Jetty/Tomcat thay vì Reactor Netty, thay dependency server theo hướng dẫn Spring Boot của đúng phiên bản, loại bỏ starter mặc định tương ứng và thêm server starter được hỗ trợ.

**Không loại bỏ mọi dependency có chữ Netty một cách máy móc.** WebClient cũng có thể cần HTTP connector; nếu bỏ Reactor Netty khỏi classpath, phải bảo đảm client có implementation khác được cấu hình. Spring Boot có server starter riêng và chọn connector theo dependency hiện diện.

## 9. Chương trình Spring Boot WebFlux chạy được trên Java 17+

Ví dụ tạo hai endpoint:

- **GET /hello**: trả JSON qua Mono.
- **GET /ticks**: phát ba sự kiện Server-Sent Events qua Flux.

Cấu trúc:

~~~text
webflux-stack-demo/
├── pom.xml
└── src/main/java/example/demo/
    ├── DemoApplication.java
    └── GreetingController.java
~~~

Dùng pom.xml ở phần 8.1.

Tệp **src/main/java/example/demo/DemoApplication.java**:

~~~java
package example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Tệp **src/main/java/example/demo/GreetingController.java**:

~~~java
package example.demo;

import java.time.Duration;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class GreetingController {
    @GetMapping("/hello")
    public Mono<Map<String, String>> hello() {
        return Mono.just(Map.of("message", "Hello from WebFlux"));
    }

    @GetMapping(value = "/ticks", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<Long> ticks() {
        return Flux.interval(Duration.ofSeconds(1)).take(3);
    }
}
~~~

Chạy tại thư mục chứa pom.xml:

~~~bash
mvn spring-boot:run
~~~

Gọi endpoint JSON:

~~~bash
curl -s http://localhost:8080/hello
~~~

Body JSON:

~~~json
{"message":"Hello from WebFlux"}
~~~

Gọi endpoint streaming:

~~~bash
curl -N http://localhost:8080/ticks
~~~

Dữ liệu SSE được phát lần lượt:

~~~text
data:0

data:1

data:2

~~~

Khoảng cách phát xấp xỉ một giây; response kết thúc sau ba phần tử.

### 9.1. Thành phần nào làm việc gì?

- **DemoApplication** khởi động Spring Boot và kích hoạt auto-configuration.
- **spring-web** cung cấp HTTP/controller abstractions và hạ tầng dùng chung.
- **spring-webflux** phát hiện @RestController, định tuyến request và quản lý Mono/Flux response.
- **Reactor Core** cung cấp Mono.just và Flux.interval/take.
- **Reactor Netty** mặc định nhận kết nối HTTP trên cổng 8080 và gửi response ra mạng trong cấu hình Boot này.
- **Codec của Spring** chuyển Map thành JSON; với /ticks, WebFlux ghi các phần tử theo định dạng SSE.

Controller không tự subscribe() và không block(). Framework quản lý subscription theo vòng đời request.

## 10. WebClient: phân biệt API client với implementation networking

Một service có thể dùng WebClient:

~~~java
@Service
public class CatalogClient {
    private final WebClient client;

    public CatalogClient(WebClient.Builder builder) {
        this.client = builder
                .baseUrl("https://catalog.example")
                .build();
    }

    public Mono<Item> findItem(String id) {
        return client.get()
                .uri("/items/{id}", id)
                .retrieve()
                .bodyToMono(Item.class);
    }
}
~~~

Đây là đoạn service minh họa, cần có Item và dependency injection của Spring. **WebClient** là API Spring: nó mô tả request, headers, body, decode và kết quả reactive. Nó cần một **ClientHttpConnector** để thực hiện network I/O. Reactor Netty là một connector phổ biến, nhưng có thể chọn implementation khác.

| Thành phần | Vai trò |
| --- | --- |
| WebClient | API fluent cho ứng dụng gọi HTTP |
| ExchangeFilterFunction | Filter request/response phía client |
| ClientHttpConnector | Cầu nối tới HTTP client implementation |
| Reactor Netty HttpClient | Thực hiện I/O HTTP bằng Reactor Netty |
| Mono/Flux | Biểu diễn kết quả bất đồng bộ và stream |

Nếu dùng WebClient.Builder auto-configured và Reactor Netty cho cả server/client, một số network resources/event-loop có thể được chia sẻ mặc định. Nếu thay connector hoặc tự tạo client, cần quản lý resource lifecycle và shutdown phù hợp.

## 11. Event loop và lý do không được block

Reactor Netty thường sử dụng mô hình **event loop** với số thread tương đối nhỏ so với số kết nối có thể điều phối. Một event-loop thread có thể phục vụ nhiều kết nối. Điều này hiệu quả khi callback xử lý nhanh và I/O thật sự non-blocking.

Nếu đặt JDBC blocking, Thread.sleep(), Future.get(), CompletableFuture.join() hoặc Mono.block() trên event loop:

1. Thread bị giữ lại trong thời gian chờ.
2. Các kết nối khác được event loop đó phục vụ có thể bị chậm.
3. Queue và latency tăng.
4. Throughput giảm, timeout và lỗi dây chuyền có thể xuất hiện.

Với thư viện blocking bắt buộc phải dùng, cô lập hợp lý:

~~~java
Mono<Result> result = Mono.fromCallable(() -> blockingRepository.find(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Đây là đoạn minh họa với blockingRepository và Result. boundedElastic đưa nguồn blocking sang Scheduler phù hợp hơn; nó không biến JDBC thành non-blocking. Ưu tiên reactive driver/API nếu muốn giữ pipeline non-blocking xuyên suốt.

## 12. Backpressure và streaming ở tầng nào?

**Reactive Streams backpressure** là cơ chế demand giữa Publisher và Subscriber. WebFlux và Reactor có thể phối hợp demand để downstream không bị buộc nhận dữ liệu nhanh hơn khả năng tiêu thụ tại các ranh giới hỗ trợ.

Phân biệt:

- **Mono/Flux** định nghĩa tín hiệu reactive ở tầng ứng dụng.
- **WebFlux** chuyển Publisher thành HTTP response/body stream và phối hợp codec.
- **Reactor Netty/Netty** vận chuyển dữ liệu qua socket, buffer và transport flow-control.
- **TCP flow control** không tương đương hoàn toàn với request(n) của Reactive Streams.
- Một nguồn ngoài không hỗ trợ pause/replay vẫn có thể phát nhanh; cần buffer/overflow policy ở adapter phù hợp.

Không suy ra chỉ vì ứng dụng trả Flux nên mọi nguồn ngoài đều tự giảm tốc hoặc bộ nhớ luôn hữu hạn.

## 13. Những lỗi cấu hình và hiểu nhầm phổ biến

| Hiểu nhầm / lỗi | Hệ quả | Cách hiểu đúng |
| --- | --- | --- |
| Nghĩ spring-web là Spring MVC | Chọn sai dependency | spring-web là nền tảng chung; MVC là spring-webmvc |
| Nghĩ spring-webflux chính là Netty | Cho rằng WebFlux chỉ chạy trên Netty | WebFlux là framework, hỗ trợ nhiều runtime |
| Nghĩ Reactor Netty là nơi viết controller | Trộn network code với business routing | Controller/handler thuộc Spring WebFlux |
| Nghĩ Mono/Flux đến từ Reactor Netty | Nhầm thư viện | Mono/Flux thuộc Reactor Core |
| Thêm spring-webflux và nghĩ Boot tự cấu hình mọi thứ | Có thể thiếu embedded server/auto-configuration tiện ích | Dùng spring-boot-starter-webflux cho ứng dụng Boot |
| Thêm cả MVC và WebFlux starter mà không biết auto-config | Boot có thể chọn MVC theo mặc định | Kiểm tra dependency tree và application type |
| Nghĩ WebClient bắt buộc dùng Reactor Netty | Khóa client vào implementation không cần thiết | WebClient dùng ClientHttpConnector và có nhiều connector |
| Gọi block() trên event loop | Làm nghẽn nhiều request | Trả Mono/Flux và tránh blocking |
| Dùng JDBC blocking trong map() | Chặn thread reactive | Dùng driver reactive hoặc cô lập blocking |
| Tạo một Netty client/pool cho mỗi request | Tạo nhiều pool/thread, khó quản lý | Reuse client/resource theo vòng đời ứng dụng |
| Cho rằng WebFlux luôn nhanh hơn MVC | Chọn stack theo tên gọi | Benchmark theo concurrency, I/O, CPU và dependency |
| Nghĩ TCP flow control bảo đảm lossless business events | Có thể mất sự kiện tại nguồn/adapter | Phân biệt transport, Reactive Streams và delivery semantics |

## 14. Cách chọn stack cho dự án

| Nhu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| CRUD truyền thống, JDBC và nhiều thư viện blocking | Spring MVC + Servlet server |
| Nhiều kết nối đồng thời, API non-blocking xuyên suốt | Spring WebFlux + runtime reactive như Reactor Netty |
| Streaming/SSE/WebSocket và dữ liệu phát liên tục | WebFlux, chọn server/client runtime theo yêu cầu |
| Chỉ cần gọi HTTP bất đồng bộ trong ứng dụng MVC | Có thể dùng WebClient mà không chuyển toàn bộ server |
| Muốn dùng Netty cho server nhưng giữ handler Spring | WebFlux + Reactor Netty |
| Muốn WebFlux trên hạ tầng Servlet hiện có | WebFlux + Servlet container được hỗ trợ |
| Phụ thuộc driver blocking chưa thể thay | MVC có thể đơn giản hơn; nếu dùng WebFlux cần cô lập blocking và đo tải |

Quyết định nên dựa trên **tính chất I/O, số kết nối đồng thời, driver database, HTTP client, mô hình streaming, năng lực vận hành và số đo hiệu năng**. Không chuyển sang WebFlux chỉ để sử dụng Mono/Flux nếu toàn bộ hệ thống vẫn blocking mà không có nhu cầu rõ.

## 15. Checklist debug dependency và runtime

1. **Starter nào được khai báo?** spring-boot-starter-web, spring-boot-starter-webflux hay cả hai?
2. **Dependency tree thực tế là gì?** Có spring-webmvc ngoài dự kiến không? Có server starter nào kéo theo?
3. **Application type nào được Boot chọn?** SERVLET hay REACTIVE?
4. **Server factory nào được auto-config?** NettyReactiveWebServerFactory, TomcatReactiveWebServerFactory hay JettyReactiveWebServerFactory?
5. **WebClient connector nào được chọn?** Reactor Netty, JDK, Jetty hay connector tùy chỉnh?
6. **Có nhiều ConnectionProvider/EventLoopGroup không cần thiết?** Kiểm tra lifecycle và resource sharing.
7. **Có blocking trên event loop không?** Kiểm tra thread name, stack trace và block detection.
8. **Controller có trả Publisher không?** Có tự subscribe()/block() hoặc tách tác vụ khỏi HTTP request không?
9. **Codec có hỗ trợ media type/body không?** Kiểm tra JSON, SSE, multipart và kiểu dữ liệu.
10. **Phiên bản Spring/Reactor/Netty có được quản lý đồng bộ không?** Dùng dependency management của Spring Boot thay vì override tùy ý.

## 16. Ghi nhớ

- **spring-web** là nền tảng web chung, cung cấp HTTP abstraction và hạ tầng mà MVC/WebFlux sử dụng.
- **spring-webflux** là reactive web framework: định tuyến request, controller/functional endpoint, codec, WebClient và tích hợp Mono/Flux.
- **Reactor Netty** là networking runtime/client-server non-blocking tích hợp Netty với Reactor; Spring Boot thường chọn làm server mặc định cho WebFlux.
- **Reactor Core** cung cấp Mono/Flux và operator.
- WebFlux có thể chạy trên nhiều server runtime; Reactor Netty phổ biến nhưng không bắt buộc.
- MVC có thể sử dụng WebClient; có WebFlux dependency không tự chứng minh server đang chạy WebFlux.
- Muốn hưởng lợi non-blocking, cần giữ I/O non-blocking xuyên suốt và tránh chặn event loop.

**Tài liệu chính thức:**
- [Spring Framework — WebFlux Overview and server support](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- [Spring Framework — Spring WebFlux reference](https://docs.spring.io/spring-framework/reference/web/webflux.html)
- [Spring Boot — Reactive Web Applications and auto-configuration](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Boot — Embedded Web Servers and replacing Reactor Netty](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Framework — WebClient and supported HTTP clients](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Reactor Netty — Project overview](https://spring.io/projects/reactor-netty)

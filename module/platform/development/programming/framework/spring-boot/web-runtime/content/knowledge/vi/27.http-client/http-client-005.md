# WebClient trong MVC và ảnh hưởng tới lựa chọn web application type

## 1. Phân biệt HTTP client và HTTP server

Trong **Spring Boot**, WebClient là **HTTP client reactive** đến từ module Spring WebFlux. Nó dùng để **gửi request tới dịch vụ khác**. Ngược lại, Spring MVC và Spring WebFlux là hai mô hình xử lý **request đi vào server**. Vì vậy **một ứng dụng Spring MVC có thể dùng WebClient mà vẫn là ứng dụng Servlet**.

Tình huống quen thuộc: dự án có dependency **spring-boot-starter-web** để chạy MVC, sau đó thêm **spring-boot-starter-webflux** chỉ để lấy WebClient. Spring Boot 3.3 **ưu tiên Spring MVC** nếu cả Spring MVC và WebFlux có mặt trên classpath. Server mặc định vẫn là **Tomcat/DispatcherServlet**, còn WebClient có thể dùng **Reactor Netty HTTP client** để thực hiện outbound HTTP requests.

Đừng đồng nhất ba trục độc lập:
1. **WebApplicationType**: Boot chọn SERVLET, REACTIVE hay NONE cho server runtime?
2. **Outbound client**: ứng dụng gọi REST bằng WebClient, RestClient, RestTemplate hay thư viện khác?
3. **Kiểu trả về Controller**: DTO đồng bộ, Mono/Flux hoặc Servlet async abstractions?

**Một Controller trả Mono không tự biến MVC thành WebFlux**. Spring MVC có hỗ trợ reactive return types bằng cơ chế Servlet asynchronous processing. Bài học giải thích quyết định framework, hai cách dùng WebClient trong MVC, thời điểm block/subscribe, cách xử lý timeout, và cách tự kiểm chứng bằng ứng dụng Java 17.

Phạm vi ví dụ: **Spring Boot 3.3.13, Spring Framework 6.1.x, Spring MVC/Servlet, Spring WebFlux WebClient, Project Reactor và Java 17+**.

## 2. So sánh chính xác các thành phần

| Thành phần | Trách nhiệm | Có quyết định server type? |
| --- | --- | --- |
| Spring MVC | Xử lý inbound HTTP bằng Servlet, DispatcherServlet | Có, theo stack MVC |
| Spring WebFlux | Xử lý inbound HTTP bằng reactive web stack | Có, theo stack WebFlux |
| WebClient | Gửi outbound HTTP request bằng reactive API | **Không** |
| RestClient | Gửi outbound HTTP request bằng imperative API | **Không** |
| Mono<T> | Publisher có tối đa một giá trị hoặc lỗi/completion | **Không** |
| Flux<T> | Publisher có nhiều giá trị hoặc lỗi/completion | **Không** |
| Reactor Netty | Có thể chạy HTTP client hoặc HTTP server | Phụ thuộc vai trò thực tế |
| Embedded Tomcat | Servlet HTTP server mặc định của starter-web | Thường báo hiệu MVC server |

**Spring MVC** dùng Servlet request threads, đồng thời hỗ trợ DeferredResult, Callable, CompletionStage, Mono/Flux qua async adapter. **Spring WebFlux** xây trên Reactive Streams, có DispatcherHandler và non-blocking I/O theo reactive server. Cả hai có thể sử dụng WebClient để gọi dịch vụ khác.

### 2.1. Luồng request trong MVC + WebClient

~~~text
Client bên ngoài
      |
      v
Tomcat Servlet HTTP server
      |
      v
Spring MVC DispatcherServlet
      |
      v
MVC Controller
      |
      +---- WebClient -> Reactor Netty HTTP client -> Service B
      |                              |
      |                              v
      |                        Mono<Response>
      |
      +---- Nếu dùng block(): Servlet worker đợi HTTP response
      |
      +---- Nếu return Mono: MVC sử dụng Servlet async handling
      |
      v
HTTP response gửi lại cho client
~~~

Sơ đồ này **không có WebFlux HTTP server**. Reactor Netty có thể xuất hiện chỉ vì WebClient HTTP client connector. Việc có thư viện reactive trong classpath không đổi cách DispatcherServlet xử lý request.

## 3. Spring Boot chọn web application type khi có cả hai starter

Quy tắc auto-detection của Spring Boot 3.3:

| Dependency có ở runtime | Lựa chọn mặc định | Runtime thường gặp |
| --- | --- | --- |
| Chỉ starter-web | **SERVLET** | MVC + Tomcat |
| Chỉ starter-webflux | **REACTIVE** | WebFlux + Reactor Netty |
| **starter-web và starter-webflux** | **SERVLET** | MVC + Tomcat; WebClient sử dụng được |
| Không có web stack phù hợp | Thường NONE | Không tự chạy HTTP server |
| Cả hai, nhưng ép kiểu reactive | REACTIVE theo cấu hình | Cần kiểm tra migration WebFlux |

Điểm dễ bị hiểu ngược: nhóm phát triển thêm starter-webflux vào MVC để dùng WebClient là tình huống **được Spring Boot dự liệu**, không phải lỗi thiết kế cần khắc phục bằng việc loại bỏ starter-web.

### 3.1. Khai báo rõ web application type

Muốn khóa lựa chọn MVC:

~~~yaml
spring:
  main:
    web-application-type: servlet
~~~

Muốn chuyển sang WebFlux server có chủ đích:

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

Hoặc tại bootstrap:

~~~java
// Fragment khi chủ động chọn loại runtime; cần các lớp đã import.
SpringApplication app = new SpringApplication(MyApplication.class);
app.setWebApplicationType(WebApplicationType.REACTIVE);
app.run(args);
~~~

**MyApplication** là tên minh họa; fragment không biên dịch độc lập. Không đặt reactive chỉ vì muốn dùng WebClient. Ép reactive sẽ thay đổi server request processing và các điểm tích hợp Servlet có thể không còn áp dụng.

### 3.2. Cách xác minh chính xác

Trong Boot ứng dụng MVC, application context thường là implementation của **ServletWebServerApplicationContext**; trong WebFlux là **ReactiveWebServerApplicationContext**. Ngoài ra có thể xem:
- Có **DispatcherServlet** hay **DispatcherHandler** xử lý inbound requests?
- HTTP server đang lắng nghe là Tomcat hay Reactor Netty?
- Bean security có dùng HttpSecurity/SecurityFilterChain hay ServerHttpSecurity/SecurityWebFilterChain?
- Tập test của production có ép spring.main.web-application-type khác môi trường chạy không?

Đừng chỉ nhìn thông báo Reactor Netty được khởi tạo; nó có thể thuộc outbound client.

## 4. Thêm WebClient vào ứng dụng MVC bằng Maven

Trong một dự án Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

**starter-web** mang MVC/Servlet container. **starter-webflux** có WebClient, Reactor, codec và Reactor Netty connector mặc định. Nếu cả hai có mặt, MVC vẫn được Boot chọn. Có thể chọn riêng dependency spring-webflux và HTTP connector thích hợp để kiểm soát classpath, nhưng phải bảo đảm client runtime/codec tương thích.

### 4.1. WebClient.Builder được Boot cấu hình

Spring Boot tạo **WebClient.Builder** đã áp dụng cấu hình phù hợp của framework. Builder ở prototype scope, nhưng nó là một **mutable builder**: nếu dùng lại cùng một object builder cho nhiều clients, mutation có thể ảnh hưởng các clients build sau.

~~~java
// Fragment trong một service có field WebClient client.
public PartnerClient(WebClient.Builder builder) {
    this.client = builder.baseUrl("https://partner.example.test")
            .build();
}
~~~

Ưu tiên inject **WebClient.Builder** thay vì gọi WebClient.create() ở mọi request vì muốn tận dụng Boot customizers, codecs, resource management và giữ client tái sử dụng. Với nhiều base URLs/headers riêng biệt, dùng builders riêng hoặc builder.clone().

### 4.2. Khi nào RestClient hợp lý hơn?

Trong Spring Framework 6.1 có **RestClient**, API fluent **imperative**. Nếu MVC Controller chỉ cần một HTTP call đồng bộ đơn giản, không có reactive composition hoặc streaming, RestClient có thể rõ nghĩa hơn WebClient + block().

~~~java
// Fragment: builder có kiểu RestClient.Builder, không phải WebClient.Builder.
RestClient client = builder.baseUrl("https://partner.example.test")
        .build();

Customer result = client.get()
        .uri("/customers/{id}", id)
        .retrieve()
        .body(Customer.class);
~~~

**Customer** là DTO ứng dụng tự định nghĩa. Fragment cần imports, class và biến id; không phải chương trình độc lập. RestClient giúp tránh đưa reactive API vào luồng nghiệp vụ hoàn toàn đồng bộ nếu không cần.

## 5. Hai cách dùng WebClient từ Spring MVC Controller

### 5.1. Cách A: chờ kết quả bằng block()

~~~java
// Fragment trong Controller MVC; client, Greeting và imports đã tồn tại.
@GetMapping("/sync")
Greeting sync() {
    return client.get()
            .uri("/hello")
            .retrieve()
            .bodyToMono(Greeting.class)
            .block(Duration.ofSeconds(4));
}
~~~

Nếu code thực thi trên **Tomcat Servlet request worker**, block() có thể sử dụng tại boundary imperative khi chủ đích của Controller là đợi một kết quả đồng bộ. Đây **không phải một lệnh cấm tuyệt đối** đối với mọi ứng dụng MVC.

Đánh đổi:
- Servlet thread bị chiếm trong khi upstream chậm.
- Tải cao có thể làm pool threads cạn và tăng tail latency.
- Nhiều calls block tuần tự có thể cộng dồn thời gian chờ.
- Bắt buộc có timeout, error handling và giới hạn concurrency/pool.
- Gọi block nhiều lần lên cold Publisher có thể phát sinh nhiều HTTP requests.

**Lưu ý:** gọi block() trong **Reactor Netty event-loop** của một reactive pipeline khác là vấn đề nghiêm trọng; Reactor có thể ném IllegalStateException vì blocking trên NonBlocking thread.

### 5.2. Cách B: trả Mono cho Spring MVC

~~~java
// Fragment trong Controller MVC; Spring MVC tự quản lý async result.
@GetMapping("/async")
Mono<Greeting> async() {
    return client.get()
            .uri("/hello")
            .retrieve()
            .bodyToMono(Greeting.class)
            .timeout(Duration.ofSeconds(3));
}
~~~

Spring MVC dùng **ReactiveAdapterRegistry** để xử lý single-value Publisher tương tự **DeferredResult**:
1. Controller trả Mono.
2. MVC đăng ký Servlet asynchronous request processing.
3. Request thread có thể được trả lại cho container trong lúc chờ upstream.
4. Khi Mono hoàn thành hoặc lỗi, MVC thực hiện async dispatch và viết response.
5. **Application type vẫn là SERVLET**.

Mô hình này có ích nếu nhiều request chờ HTTP I/O. Nhưng một ứng dụng MVC trả Mono **không trở thành non-blocking end-to-end**: JDBC/JPA, Servlet filters, data binding và ghi response có thể vẫn blocking.

### 5.3. Không subscribe thủ công rồi trả response

~~~java
// ANTI-PATTERN cho endpoint phải trả kết quả upstream.
@GetMapping("/wrong")
String wrong() {
    client.get().uri("/hello").retrieve()
            .bodyToMono(String.class)
            .subscribe(System.out::println);
    return "done";
}
~~~

Endpoint trả **done** trước khi upstream chắc chắn hoàn tất. Lỗi, cancellation và response lifecycle bị tách khỏi HTTP request. Với endpoint cần kết quả, **return Mono** và để framework subscribe, hoặc **block có kiểm soát** tại một boundary synchronous. Background job thực sự nên có queue/workflow trạng thái riêng, không dùng subscribe() tùy tiện trong Controller.

### 5.4. Flux trong MVC không mặc định stream giống WebFlux

- Mono<T> trong MVC: đơn giá trị, tương tự DeferredResult.
- Flux<T> với media type streaming, ví dụ **text/event-stream** hoặc NDJSON: MVC có thể dùng cơ chế emitter.
- Flux<T> với **application/json** thông thường: có thể thu thập phần tử thành một danh sách rồi trả.
- Servlet output writes có thể blocking và được thực hiện trên thread executor riêng khi streaming.

Vì vậy **return Flux** không chứng minh toàn bộ response writes đều non-blocking. Production streaming MVC cần cấu hình async executor và timeout phù hợp.

## 6. Demo Maven chạy được: hai starter nhưng server vẫn là MVC

Bài thực hành có một endpoint upstream nội bộ và hai proxy endpoint để so sánh. Upstream nằm **trong cùng ứng dụng** chỉ để không cần service khác. Đây **không phải kiến trúc production**: self-call dưới tải có thể gây nghẽn Servlet worker pool, đặc biệt khi dùng block().

### 6.1. Cấu trúc dự án

~~~text
mvc-webclient-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/mvcclient/
    │   └── MvcWebClientApplication.java
    └── resources/application.yml
~~~

### 6.2. pom.xml đầy đủ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>mvc-webclient-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
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

Hai starters mang cả MVC và WebFlux libraries, nhưng Boot **không** tự khởi chạy cả Tomcat và một Reactor Netty server cùng lúc theo cấu hình mặc định.

### 6.3. application.yml

**src/main/resources/application.yml:**

~~~yaml
server:
  port: 8080

spring:
  mvc:
    async:
      request-timeout: 5s

demo:
  upstream-url: http://localhost:8080
~~~

Property **demo.upstream-url** là cấu hình tự định nghĩa cho client. **spring.mvc.async.request-timeout** dành cho Servlet async request lifecycle, không thay connect/response timeout của WebClient.

Không khai báo spring.main.web-application-type trong lab để quan sát cách Boot tự chọn mặc định.

### 6.4. Java code hoàn chỉnh một file

**src/main/java/com/example/mvcclient/MvcWebClientApplication.java:**

~~~java
package com.example.mvcclient;

import java.time.Duration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class MvcWebClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcWebClientApplication.class, args);
    }

    public record Greeting(String message) {}
}

@Configuration
class ClientConfig {
    @Bean
    WebClient upstreamClient(WebClient.Builder builder, Environment env) {
        String url = env.getRequiredProperty("demo.upstream-url");
        return builder.baseUrl(url).build();
    }
}

@RestController
class DemoController {
    private final WebClient client;
    private final ApplicationContext context;

    DemoController(WebClient client, ApplicationContext context) {
        this.client = client;
        this.context = context;
    }

    @GetMapping(path = "/api/runtime",
                produces = MediaType.TEXT_PLAIN_VALUE)
    String runtime() {
        return context instanceof ServletWebServerApplicationContext
                ? "SERVLET/MVC\n" : "OTHER\n";
    }

    // Chỉ là endpoint mock upstream, cùng server MVC.
    @GetMapping(path = "/upstream/hello/{name}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    MvcWebClientApplication.Greeting upstream(
            @PathVariable String name
    ) {
        return new MvcWebClientApplication.Greeting("hello " + name);
    }

    private Mono<MvcWebClientApplication.Greeting> fetch(String name) {
        return client.get()
                .uri("/upstream/hello/{name}", name)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .bodyToMono(MvcWebClientApplication.Greeting.class)
                .switchIfEmpty(Mono.error(
                        new IllegalStateException("Empty upstream body")
                ))
                .timeout(Duration.ofSeconds(3));
    }

    @GetMapping(path = "/api/blocking/{name}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    MvcWebClientApplication.Greeting blocking(
            @PathVariable String name
    ) {
        return fetch(name).block(Duration.ofSeconds(4));
    }

    @GetMapping(path = "/api/async/{name}",
                produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<MvcWebClientApplication.Greeting> async(
            @PathVariable String name
    ) {
        return fetch(name);
    }
}
~~~

**Phân tích:**
- Boot tự chọn Servlet/MVC. Code không bật WebFlux server một cách tường minh.
- **WebClient.Builder** đến từ Boot, client được tạo một lần trong Bean thay vì mỗi request.
- **Environment** lấy upstream base URL được quản lý qua config.
- **/api/runtime** trực tiếp xác minh context thực tế.
- **/upstream/hello** trả Java 17 record, Jackson của starter-web serialize thành JSON.
- **fetch()** trả Mono lazy; switchIfEmpty biến response không có body thành lỗi rõ, timeout(3s) đặt deadline ở Publisher.
- **/api/blocking** gọi block(Duration) trong Servlet worker. Nếu upstream lâu, worker đợi.
- **/api/async** trả Mono; Spring MVC chịu trách nhiệm subscription và async result.
- Không dùng subscribe() thủ công; error signal đi cùng pipeline và có thể được MVC exception handler xử lý.
- Trong production hãy thay URL upstream bằng service khác, không dùng self-call.

Lưu ý: **fetch timeout 3 giây** và **block timeout 4 giây** không thay thế connect timeout, TCP read timeout, pool acquisition timeout hay proxy timeout. Khi lỗi xảy ra, demo có thể trả error response mặc định; phần 9 giải thích cách ánh xạ status.

### 6.5. Chạy Maven và curl

Tại thư mục **mvc-webclient-demo**, yêu cầu JDK 17+, Maven và cổng 8080 rảnh:

~~~bash
mvn package
java -jar target/mvc-webclient-demo-1.0.0.jar
~~~

Mở terminal khác gọi:

~~~bash
curl -s http://localhost:8080/api/runtime
~~~

Body mong đợi:

~~~text
SERVLET/MVC
~~~

~~~bash
curl -s http://localhost:8080/upstream/hello/Ada
~~~

JSON body:

~~~json
{"message":"hello Ada"}
~~~

~~~bash
curl -s http://localhost:8080/api/blocking/Ada
~~~

JSON body:

~~~json
{"message":"hello Ada"}
~~~

~~~bash
curl -s http://localhost:8080/api/async/Ada
~~~

JSON body:

~~~json
{"message":"hello Ada"}
~~~

Kết quả JSON giống nhau không chứng minh execution model giống nhau. **Blocking endpoint** chờ trong Servlet thread; **async endpoint** trả Mono để MVC xử lý Servlet async lifecycle. Trên Windows PowerShell, có thể dùng **curl.exe** để tránh alias curl khác cú pháp. Khi dùng curl -i, stdout có thêm HTTP headers; đoạn trên mô tả response body.

### 6.6. Cách kiểm tra runtime bằng Spring Boot Test

Thêm dependency test nếu muốn kiểm tra tự động:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Đây là **fragment** thêm vào phần dependencies của pom.xml đã có. Tạo file **src/test/java/com/example/mvcclient/WebTypeTest.java**:

~~~java
package com.example.mvcclient;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ApplicationContext;
import org.springframework.web.reactive.function.client.WebClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebTypeTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    WebClient.Builder webClientBuilder;

    @Test
    void mvcWinsAndWebClientIsStillAvailable() {
        assertInstanceOf(ServletWebServerApplicationContext.class, context);
        assertNotNull(webClientBuilder);
    }
}
~~~

Chạy **mvn test**. Nếu context dựng thành công, test chứng minh **ServletWebServerApplicationContext** hiện hữu và **WebClient.Builder vẫn inject được**. Test này không gọi outbound URL localhost:8080 nên không phụ thuộc cổng mock upstream, và RANDOM_PORT không gây xung đột với cổng server đã khai báo.

**Không** gán một stdout Maven cố định; Maven log/phần tải dependency phụ thuộc môi trường.

## 7. WebClient reactive có nghĩa gì khi dùng với MVC?

WebClient trả về **Mono/Flux** theo mô hình Publisher. Tạo Publisher không đồng nghĩa ngay lập tức gửi HTTP request trong mọi trường hợp; với WebClient thông thường, request bắt đầu khi có **subscription**.

~~~java
// Fragment minh họa một Publisher chưa được consume.
Mono<Customer> customer = client.get()
        .uri("/customers/{id}", id)
        .retrieve()
        .bodyToMono(Customer.class);
~~~

- **block()** subscribe và chờ kết quả.
- **return Mono** trong MVC để framework sở hữu subscription/lifecycle.
- **subscribe()** thủ công trong Controller thường làm mất liên kết với HTTP response.
- Hai subscriptions lên cold Publisher có thể tạo hai HTTP calls.
- **map/flatMap/zip** tạo pipeline composition, không bắt buộc chặn Servlet thread.

### 7.1. Ghép hai API calls bằng Mono.zip

~~~java
// Fragment, các DTO Customer/Balance/CustomerView do app định nghĩa.
Mono<Customer> customer = customerClient.get()
        .uri("/customers/{id}", id)
        .retrieve()
        .bodyToMono(Customer.class);

Mono<Balance> balance = balanceClient.get()
        .uri("/balances/{id}", id)
        .retrieve()
        .bodyToMono(Balance.class);

Mono<CustomerView> view = Mono.zip(customer, balance)
        .map(tuple -> new CustomerView(
                tuple.getT1(),
                tuple.getT2()
        ));
~~~

Hai Publisher có thể được subscribe cùng lúc và thực hiện HTTP requests đồng thời, giúp giảm thời gian chờ tuần tự. Nhưng **Mono.zip cần đủ giá trị**; nếu một Publisher hoàn thành rỗng, combined Mono có thể cũng không phát giá trị. Vẫn cần concurrency limit, lỗi rõ và timeout. Không dùng zip như một bảo đảm mọi side effect đều thành công cùng nhau.

## 8. Blocking, event-loop và MVC async

### 8.1. Điều gì xảy ra khi block sai thread?

Trong WebFlux/Reactive Netty code chạy trên NonBlocking event-loop, gọi block có thể gây:

~~~text
java.lang.IllegalStateException:
block()/blockFirst()/blockLast() are blocking,
which is not supported in thread reactor-http-nio-...
~~~

Đây là **mẫu lỗi**, tên thread và stack trace có thể khác. Không nên sửa bằng cách tắt kiểm tra hoặc bọc blocking call trực tiếp trong map(). Hãy giữ pipeline bằng flatMap/return Mono.

Nếu bắt buộc dùng API legacy blocking trong reactive path, có thể đưa công việc sang scheduler giới hạn:

~~~java
// Fragment cho legacy blocking API, không phải chương trình độc lập.
Mono<LegacyData> data = Mono.fromCallable(
        () -> legacyService.load(id)
).subscribeOn(Schedulers.boundedElastic());
~~~

Điều này **cô lập blocking**, không làm API tự non-blocking. Với JPA/JDBC và transaction gắn ThreadLocal phải xét riêng transaction/context, latency và pool capacity.

### 8.2. MVC async không loại bỏ mọi blocking

Khi MVC trả Mono, Servlet thread có thể được trả về pool trong thời gian chờ. Nhưng:
- Ghi response qua Servlet API có thể blocking.
- Async dispatch vẫn cần container phục vụ phần hoàn tất request.
- JSP, file IO, JDBC, Servlet filters và một số middleware vẫn blocking.
- Flux streaming trong MVC cần AsyncTaskExecutor đủ năng lực; default executor có thể không phù hợp production concurrency lớn.
- Context propagation qua thread hops không mặc định giống một method call đồng bộ.

Vì vậy phải đo **Tomcat threads, event-loop/client connection pool, GC, async requests, latency và throughput**. Không suy luận “hiệu năng sẽ tốt hơn” chỉ từ chữ ký Mono.

### 8.3. Self-call trong lab có thể nghẽn nặng

Nếu Tomcat có rất ít worker threads, nhiều request tới **/api/blocking** giữ tất cả threads để đợi **/upstream/hello** nằm trong cùng process, upstream không có thread để xử lý. Chỉ một self-call topology có thể gây starvation dù WebClient connector vẫn hoạt động. Production nên tách service, dùng deadline và không yêu cầu một request đợi chính máy chủ đang cạn threads để phản hồi.

## 9. Xử lý status, lỗi và timeout

### 9.1. retrieve() không tự copy status từ upstream

WebClient **retrieve()** mặc định coi HTTP 4xx/5xx là lỗi và thường phát **WebClientResponseException**. Nếu một MVC Controller không map lỗi đó, response cho client bên ngoài có thể là lỗi server mặc định. Không được giả định upstream 404 tự động biến thành HTTP 404 ở Controller của bạn.

Có thể tùy chỉnh:

~~~java
// Fragment: HttpStatusCode và Mono cần được import.
Mono<Customer> data = client.get()
        .uri("/customers/{id}", id)
        .retrieve()
        .onStatus(
                HttpStatusCode::is5xxServerError,
                response -> Mono.error(
                        new IllegalStateException("Upstream unavailable")
                )
        )
        .bodyToMono(Customer.class);
~~~

Đây là fragment minh họa policy, chưa có Customer class. Ứng dụng thật cần @RestControllerAdvice/exception mapping hợp API contract: upstream 5xx có thể thành 502/503; timeout có thể thành 504; upstream 404 có thể thành 404 hoặc business error tùy ngữ nghĩa.

### 9.2. exchangeToMono cho nhánh response riêng

~~~java
// Fragment điều khiển giải mã theo HTTP status.
Mono<Customer> result = client.get()
        .uri("/customers/{id}", id)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Customer.class);
            }
            return response.createException()
                    .flatMap(error -> Mono.error(error));
        });
~~~

**exchangeToMono** phù hợp khi cần quyết định khác nhau theo status/header. Cần đọc hoặc release response body đúng hợp đồng để không leak resource/connection. Không tùy tiện chuyển sang API exchange() cũ mà bỏ quên việc xử lý body.

### 9.3. Timeout có nhiều lớp

| Loại | Ở đâu | Phạm vi |
| --- | --- | --- |
| TCP connect timeout | HTTP client connector | Thiết lập TCP connection |
| Response/read timeout | Reactor Netty/client connector | Chờ dữ liệu HTTP response |
| Mono.timeout | Reactor pipeline | Thời gian hoàn thành Publisher |
| block(Duration) | Thread imperative | Thời gian caller đợi |
| spring.mvc.async.request-timeout | Spring MVC/Servlet | Thời gian giữ async request |
| Ingress/gateway timeout | Tầng proxy | Thời gian proxy đợi upstream |

Ví dụ cấu hình Reactor Netty connector:

~~~java
// Fragment cần HttpClient, ChannelOption, ReactorClientHttpConnector.
HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 2000)
        .responseTimeout(Duration.ofSeconds(3));

WebClient client = builder
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .baseUrl("https://api.example.test")
        .build();
~~~

**Không coi responseTimeout là tổng deadline của mọi giai đoạn**, và không coi Mono.timeout thay được connect timeout. Tùy biến connector có thể thay cách Boot quản lý resources và metrics, nên cần test pool/connection lifecycle. Nếu gateway trả 504 trước khi WebClient timeout, điều chỉnh deadline toàn tuyến chứ không chỉ tăng một property.

### 9.4. Dung lượng body và streaming

WebClient dùng codecs và có giới hạn bộ nhớ để decode nội dung. Response quá lớn có thể gây **DataBufferLimitException**. Không tăng buffer vô hạn vì có thể làm heap tăng mạnh khi nhiều requests đồng thời. Với file lớn hoặc data stream, dùng streaming API, giới hạn body và chọn chiến lược backpressure/memory phù hợp.

### 9.5. Cancellation và retry

Khi client ngắt kết nối hoặc Mono timeout/cancel, subscription có thể bị hủy, nhưng upstream **có thể đã thực hiện side effect**. Với POST tạo đơn/thanh toán, retry có thể lặp thao tác. Chỉ retry khi API idempotent hoặc có idempotency key/chính sách phù hợp. Không coi cancellation là rollback giao dịch đã chạy ở upstream.

## 10. Bảo mật của outbound WebClient

WebClient mở kết nối từ backend tới một đích mạng. Nó có thể tạo rủi ro dù inbound Controller đã xác thực người dùng.

### 10.1. SSRF do URL người dùng kiểm soát

~~~java
// Anti-pattern: không cho người dùng tùy ý điều khiển full URL.
@GetMapping("/fetch")
Mono<String> unsafe(@RequestParam String url) {
    return WebClient.create()
            .get().uri(url)
            .retrieve().bodyToMono(String.class);
}
~~~

Nguy cơ **Server-Side Request Forgery (SSRF)**: attacker yêu cầu backend gọi mạng nội bộ, metadata service hoặc endpoint bí mật. Nên dùng upstream base URL cố định/allowlist, validate path/query, kiểm soát redirect và egress theo policy. Không dùng URL user cung cấp làm đích tùy ý.

### 10.2. Không copy toàn bộ Authorization/Cookie sang upstream

Một client có thể gửi **Authorization**, **Cookie**, **Host**, **X-Forwarded-*** trong inbound request. Không forward hết sang mọi upstream:
- Credential dành cho service A chưa chắc được dùng ở service B.
- Session cookie của browser không phải token service-to-service.
- Forward header sai có thể làm downstream hiểu nhầm origin/identity.
- Log raw headers có thể lộ credentials.

Nếu cần truyền danh tính, dùng policy delegation/token exchange rõ ràng và tracing context chuẩn. Bảo vệ HTTPS, xác thực certificate/hostname và không tạo trust-all TLS client chỉ vì gặp lỗi handshake.

### 10.3. Context propagation

Spring MVC thường có **SecurityContextHolder, RequestContextHolder, MDC** liên quan ThreadLocal. Reactor callback chạy trên luồng khác có thể không tự có các ThreadLocal đó. **Reactor Context khác ThreadLocal**. Dùng cơ chế context propagation/Observation phù hợp và kiểm thử qua async boundary; không giả định JPA transaction hoặc SecurityContext tự động lan sang mọi callback.

## 11. Nếu chuyển hẳn sang WebFlux, phải thay đổi gì?

Chuyển web application type là **migration của server stack**, không phải thay HTTP client.

| Vùng | Spring MVC/Servlet | Spring WebFlux |
| --- | --- | --- |
| Front controller | DispatcherServlet | DispatcherHandler |
| Request context | HttpServletRequest / HttpServletResponse | ServerWebExchange / ServerHttpRequest |
| Web configuration | WebMvcConfigurer | WebFluxConfigurer |
| Servlet Filter | Filter/OncePerRequestFilter | WebFilter |
| Security | HttpSecurity / SecurityFilterChain | ServerHttpSecurity / SecurityWebFilterChain |
| Multipart upload | MultipartFile / jakarta.servlet.http.Part | FilePart / reactive Part |
| Async response | DeferredResult, Mono adapter, Servlet async | Reactive server pipeline |
| Database integrations | JDBC/JPA thường blocking | Cần reactive adapter hoặc cô lập blocking |
| Outbound calls | RestClient/WebClient | WebClient |

Nếu code vẫn giữ Servlet Filters, HttpSession, MultipartFile, JSP hoặc JPA calls trên request path, ép reactive có thể làm những giả định cũ không còn đúng. Cần rà soát từng feature, security, transaction, tracing, error handling và regression test. Thường nên **loại starter-web** khi đã chủ động chọn WebFlux để tránh classpath ambiguity.

Một test muốn **ép WebFlux** có thể dùng:

~~~java
// Fragment test cho dự án thực sự muốn reactive runtime.
@SpringBootTest(
        properties = "spring.main.web-application-type=reactive"
)
class ReactiveAppTest {
}
~~~

Cấu hình này làm **test context là reactive** theo yêu cầu; nó không phải cách test một ứng dụng MVC + WebClient đúng như production. Với MVC, test ServletWebServerApplicationContext như phần 6.

## 12. Khi nào chọn MVC + WebClient, MVC + RestClient hoặc WebFlux?

**MVC + RestClient** thường hợp khi code nghiệp vụ imperative, JPA/JDBC nhiều, một vài HTTP calls đồng bộ và không cần stream/composition phức tạp. Lợi ích là call stack và error model dễ theo dõi.

**MVC + WebClient + block** hợp khi đã có WebClient, phải giao tiếp với code imperative và quy mô/tải không khiến chờ network chiếm quá nhiều threads. Giới hạn block Duration rõ và đo concurrency thực tế.

**MVC + WebClient + return Mono** hợp khi ứng dụng phải chờ nhiều outbound HTTP I/O và muốn trả lại Servlet worker trong lúc chờ mà vẫn giữ hệ sinh thái MVC. Cần hiểu Servlet async, context propagation, blocking response writes và AsyncTaskExecutor.

**WebFlux + WebClient** có thể phù hợp khi thật sự cần reactive processing end-to-end, tải I/O cao và tầng data/security/integration tương thích. Không nên chọn chỉ vì muốn một HTTP client hiện đại.

Không có lựa chọn tốt nhất cho mọi workload. Hãy so sánh latency p95/p99, concurrency, resource usage, error rate, complexity và khả năng vận hành bằng load test trên ứng dụng thật.

## 13. Bảng lỗi và hướng kiểm tra nhanh

| Hiện tượng | Nguyên nhân khả dĩ | Cách làm |
| --- | --- | --- |
| Thêm starter-webflux mà server vẫn Tomcat | Boot ưu tiên MVC với cả hai starter | Xác nhận context; thường là đúng |
| WebClient.Builder không inject được | Dependency hoặc Boot conditions thiếu | Kiểm tra Maven tree và bean auto-config |
| Reactor Netty xuất hiện nhưng không có WebFlux server | Netty là outbound client connector | Xem server port và Servlet context |
| Controller trả Mono nhưng vẫn MVC | MVC hỗ trợ reactive return | Đúng thiết kế; không cần ép reactive |
| block() trên reactor-http-nio báo lỗi | Blocking trên event-loop | Compose Mono/Flux, không block |
| MVC blocking controller chậm khi upstream lỗi | Servlet threads bị giữ | Timeout, concurrency limit, return Mono hoặc RestClient |
| Upstream trả 404, proxy API trả 500 | WebClientResponseException chưa map | Domain error mapping rõ |
| HTTP 504 mặc dù app chưa hết deadline | Proxy timeout sớm hơn app | Đồng bộ timeouts |
| Upstream nhận hai HTTP calls | Cold Publisher subscribe nhiều lần | Kiểm tra block/subscribe/retry |
| Response được trả trước khi upstream xong | subscribe() thủ công | Return Mono hoặc quản lý job riêng |
| MVC Flux streaming vẫn chiếm threads | Servlet output write blocking | Cấu hình AsyncTaskExecutor và load test |
| Codec DataBufferLimitException | Buffer response lớn | Stream, giới hạn body, cấu hình buffer hợp lý |
| Mất request/security context trong callback | ThreadLocal không tự propagate | Context propagation đúng framework |
| App ép reactive nhưng Servlet security không chạy | Sai stack SecurityFilterChain | Migration sang WebFlux security |
| Self-call localhost bị timeout khi tải lớn | Cạn Tomcat worker pool | Bỏ self-call, tách upstream |

## 14. Câu hỏi củng cố

**1. Khi có cả starter-web và starter-webflux, Boot 3.3 mặc định dùng framework nào để nhận HTTP request?**  
Spring MVC/SERVLET, thường embedded Tomcat.

**2. Có Reactor Netty trong dependency tree chứng minh server là Netty không?**  
Không. Nó có thể chỉ là HTTP client connector của WebClient.

**3. WebClient có buộc Controller phải return Mono không?**  
Không. Trong MVC có thể dùng block() tại boundary đồng bộ, nhưng cần timeout và lưu ý chi phí threads.

**4. MVC Controller return Mono tự trở thành WebFlux Controller chưa?**  
Chưa. MVC dùng Servlet async adapter.

**5. Vì sao không nên block trên reactor-http-nio?**  
Đó là event-loop non-blocking thread; Reactor có thể cấm thao tác blocking hoặc event-loop bị nghẽn.

**6. subscribe() thủ công rồi trả response có an toàn không?**  
Không nếu response phụ thuộc kết quả upstream; lỗi và lifecycle bị tách.

**7. Với MVC imperative chỉ cần gọi REST một lần, ngoài WebClient nên cân nhắc gì?**  
RestClient từ Spring 6.1.

**8. Mono.zip có đảm bảo kết quả nếu một publisher hoàn thành rỗng không?**  
Không. Cần chính sách xử lý Mono.empty/error rõ.

**9. WebClient retrieve() gặp upstream 500 có tự trả đúng 500 từ app MVC không?**  
Không nhất thiết. Nó phát WebClientResponseException, phải map theo API contract.

**10. Đổi spring.main.web-application-type sang reactive đã migration xong ứng dụng MVC có Servlet filters và JPA chưa?**  
Chưa. Cần sửa/kiểm thử request APIs, security, data access và execution model.

**11. Trong MVC return Mono có giảm chờ Servlet request thread không?**  
Có thể, nhờ Servlet async; nhưng response writes và phần khác vẫn có thể blocking.

**12. Vì sao không cho client truyền URL bất kỳ để WebClient gọi?**  
Nguy cơ SSRF và truy cập mạng nội bộ trái phép.

## 15. Checklist áp dụng

- [ ] Mục đích là **outbound HTTP client** hay **migrate inbound HTTP server**?
- [ ] Dự án có cả starter-web và starter-webflux? Hiểu Boot ưu tiên **SERVLET**.
- [ ] Kiểm tra **ServletWebServerApplicationContext** hoặc integration test trước khi kết luận.
- [ ] Inject **WebClient.Builder** từ Boot; build/reuse client.
- [ ] Dùng **RestClient** khi mục tiêu chỉ là imperative HTTP đơn giản.
- [ ] Nếu dùng WebClient trong MVC, chọn **block với timeout** hoặc **return Mono** có chủ đích.
- [ ] Không subscribe thủ công trong request handler cần kết quả.
- [ ] Không block event-loop, không nhầm Servlet async với reactive server end-to-end.
- [ ] Đặt connect/response/pipeline/Servlet async/proxy timeouts phù hợp.
- [ ] Có error mapping, retry/idempotency policy, connection pool/concurrency monitoring.
- [ ] Giữ TLS verification, kiểm soát SSRF và credential forwarding.
- [ ] Nếu chuyển sang WebFlux, rà soát Servlet filters, security, multipart, JDBC/JPA và tests.

## 16. Kết luận

**WebClient là HTTP client reactive, không phải công tắc chuyển web application type.** Trong Spring Boot 3.3, khi cùng có Spring MVC và WebFlux, **MVC/SERVLET được chọn mặc định**. WebClient vẫn gửi outbound HTTP requests; Reactor Netty có thể được sử dụng bên phía client trong khi Tomcat tiếp tục phục vụ inbound requests.

Một MVC Controller có thể **block() có giới hạn thời gian** ở boundary đồng bộ, hoặc **return Mono để Spring MVC tận dụng Servlet async**. Không được đánh đồng hai kiểu thực thi, và không xem return Mono là bằng chứng WebFlux server. Chỉ chuyển sang WebFlux khi toàn bộ stack và mục tiêu hiệu năng đã được đánh giá.

## Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Reactive Web Applications, quy tắc MVC ưu tiên khi có cả hai starters: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Boot 3.3 — Calling REST Services, WebClient.Builder và client runtime: https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html
- Spring Boot 3.3 — Testing Spring Boot Applications, Detecting Web Application Type: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Framework — MVC Asynchronous Requests và Reactive Types: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework — WebClient.retrieve: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
- Spring Framework — WebClient overview: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- Project Reactor — Reactor Reference Guide: https://projectreactor.io/docs/core/release/reference/

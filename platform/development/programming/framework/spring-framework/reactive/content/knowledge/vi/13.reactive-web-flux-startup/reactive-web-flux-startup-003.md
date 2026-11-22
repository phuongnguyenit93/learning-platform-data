# Khởi tạo cấu hình WebFlux và endpoint tối thiểu

## 1. Mục tiêu và bối cảnh

**Spring WebFlux** là web framework reactive của Spring, được xây dựng quanh mô hình bất đồng bộ và non-blocking. Ứng dụng WebFlux thường sử dụng **Project Reactor** với hai kiểu dữ liệu quen thuộc:

- **Mono<T>** biểu diễn một kết quả có thể có tối đa một phần tử.
- **Flux<T>** biểu diễn một chuỗi có thể có từ không đến nhiều phần tử.

Một ứng dụng WebFlux tối thiểu cần có dependency đúng, điểm khởi động Spring Boot, cấu hình HTTP phù hợp và ít nhất một endpoint trả về Mono hoặc Flux. Khi ứng dụng khởi động, Spring tạo ApplicationContext, phát hiện controller/handler, cấu hình codec để chuyển đổi request/response và khởi tạo web server reactive.

Bài này hướng dẫn tạo ứng dụng WebFlux từ đầu bằng Maven và Java 17+, cấu hình một số thuộc tính cần thiết, viết endpoint annotation và functional endpoint, chạy ứng dụng, kiểm thử bằng WebTestClient và nhận biết những lỗi cấu hình thường gặp.

Sau bài học, bạn có thể:

- Phân biệt WebFlux với Spring MVC và biết khi nào nên chọn từng stack.
- Thêm đúng starter để khởi động ứng dụng WebFlux.
- Tạo class main với @SpringBootApplication.
- Viết REST endpoint trả Mono và Flux.
- Hiểu vai trò của HTTP message codecs và WebFluxConfigurer.
- Viết functional endpoint bằng RouterFunction và HandlerFunction.
- Chạy, kiểm tra và test endpoint bằng curl và WebTestClient.
- Tránh blocking, subscribe thủ công và cấu hình trùng lặp làm mất lợi ích reactive.

## 2. WebFlux khác Spring MVC ở điểm nào?

| Đặc điểm | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Mô hình chính | Servlet, thường xử lý theo request thread | Reactive, hỗ trợ non-blocking I/O |
| Kiểu trả về phổ biến | Object, ResponseEntity, Callable, DeferredResult | Mono<T>, Flux<T>, Publisher |
| Runtime thường gặp | Servlet container như Tomcat | Reactor Netty mặc định trong cấu hình Boot phổ biến |
| I/O | Có thể dùng blocking API theo mô hình servlet | Phù hợp với reactive/non-blocking client và server |
| Luồng dữ liệu | Thường trả response sau khi xử lý | Có thể stream nhiều phần tử qua Flux/SSE |
| Hệ sinh thái | Spring MVC, Servlet filters, MVC interceptors | WebFilter, WebClient, Reactor Context, reactive security |

WebFlux phù hợp khi hệ thống có I/O bất đồng bộ, cần streaming hoặc muốn kết nối các dịch vụ reactive mà không giữ thread chờ blocking. Nó không tự làm một thuật toán CPU-bound nhanh hơn, cũng không biến JDBC hay một thư viện blocking thành non-blocking chỉ bằng cách đổi kiểu trả về.

**Không phải ứng dụng nào cũng cần WebFlux.** Nếu toàn bộ hệ thống đang dùng JDBC/blocking và tải không đòi hỏi mô hình reactive, Spring MVC có thể đơn giản hơn. Giá trị của WebFlux rõ hơn khi phần lớn chuỗi xử lý có thể non-blocking từ đầu đến cuối.

### 2.1. Tránh đưa hai web starter vào cùng một ứng dụng nếu không có chủ đích

Để tạo ứng dụng WebFlux thuần, sử dụng **spring-boot-starter-webflux**. Không thêm **spring-boot-starter-web** một cách tùy tiện.

Nếu cả starter MVC và WebFlux cùng xuất hiện trên classpath, Spring Boot thường ưu tiên cấu hình Spring MVC. Đây là nguyên nhân phổ biến khiến ứng dụng tưởng đã dùng WebFlux nhưng lại khởi động bằng servlet stack. Nếu mục tiêu thật sự là WebFlux, hãy kiểm tra dependency tree và loại starter MVC không cần thiết thay vì cố sửa bằng nhiều cấu hình.

WebFlux có thể chạy trên Reactor Netty mặc định, và cũng hỗ trợ một số runtime khác theo cấu hình. Trong bài thực hành này ta giữ cấu hình mặc định để giảm số thành phần phải thiết lập.

## 3. Tạo project Maven và thêm dependency

Cấu trúc thư mục mẫu:

~~~text
reactive-webflux-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/webflux/
    │   │       ├── ReactiveWebFluxApplication.java
    │   │       ├── GreetingController.java
    │   │       ├── FunctionalRoutes.java
    │   │       └── WebFluxConfiguration.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/
            └── com/example/webflux/
                └── GreetingControllerTest.java
~~~

Tệp **pom.xml** dùng Spring Boot 3.3.5 và Java 17:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>reactive-webflux-demo</artifactId>
    <version>1.0.0</version>
    <name>reactive-webflux-demo</name>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

Ý nghĩa dependency:

- **spring-boot-starter-webflux** đưa vào Spring WebFlux, Reactor và server reactive mặc định phù hợp với cấu hình Boot.
- **spring-boot-starter-test** cung cấp JUnit Jupiter, Spring Test và các thư viện kiểm thử thường dùng, bao gồm WebTestClient trong môi trường WebFlux.
- Spring Boot parent quản lý phiên bản dependency/plugin tương thích; không cần tự đặt version cho từng thư viện do Boot quản lý.

Không cần thêm **spring-boot-starter-web** cho ví dụ này. Nếu dự án đã có starter đó, hãy kiểm tra xem có thực sự cần MVC hay không trước khi triển khai.

## 4. Điểm khởi động Spring Boot

Tạo tệp **ReactiveWebFluxApplication.java**:

~~~java
package com.example.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveWebFluxApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            ReactiveWebFluxApplication.class,
            args
        );
    }
}
~~~

**@SpringBootApplication** kết hợp ba khả năng chính:

1. **@SpringBootConfiguration**: đánh dấu class cấu hình chính của ứng dụng.
2. **@EnableAutoConfiguration**: cho phép Spring Boot cấu hình bean dựa trên dependency và cấu hình hiện có.
3. **@ComponentScan**: quét component từ package của class main trở xuống.

Vì class main nằm trong **com.example.webflux**, các controller, service và configuration đặt trong package này hoặc package con sẽ được phát hiện tự động. Nếu đặt component ngoài phạm vi quét, cần tổ chức package hợp lý hoặc cấu hình scan rõ ràng.

Với WebFlux, Spring Boot nhận diện starter reactive và cấu hình web application theo reactive stack. Trong trường hợp mặc định, server sẽ khởi động bằng Reactor Netty nếu dependency/runtime tương ứng có mặt.

**Không cần thêm @EnableWebFlux trong ứng dụng Spring Boot thông thường.** Boot đã cung cấp auto-configuration. Chỉ dùng @EnableWebFlux khi muốn kiểm soát cấu hình WebFlux ở mức thấp và chấp nhận tự chịu trách nhiệm cho những phần auto-configuration mà ứng dụng thay thế.

## 5. Viết endpoint annotation tối thiểu bằng Mono

Tạo tệp **GreetingController.java**:

~~~java
package com.example.webflux;

import java.time.Duration;
import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class GreetingController {

    @GetMapping("/hello")
    public Mono<Map<String, String>> hello(
        @RequestParam(defaultValue = "World") String name
    ) {
        return Mono.just(
            Map.of("message", "Hello, " + name)
        );
    }

    @GetMapping(
        value = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<String>> events() {
        return Flux.interval(Duration.ofSeconds(1))
            .map(sequence ->
                ServerSentEvent.builder("tick-" + sequence)
                    .id(Long.toString(sequence))
                    .event("tick")
                    .build()
            );
    }
}
~~~

### 5.1. Phân tích endpoint /api/hello

- **@RestController** đánh dấu component xử lý HTTP và serialize giá trị trả về thành response body.
- **@RequestMapping("/api")** đặt prefix cho các endpoint trong class.
- **@GetMapping("/hello")** ánh xạ HTTP GET tới method hello.
- **@RequestParam(defaultValue = "World")** đọc query parameter name; nếu client không truyền, giá trị là World.
- **Mono<Map<String,String>>** cho biết kết quả được phát theo mô hình reactive và chỉ có một map.
- **Map.of(...)** tạo dữ liệu bất biến phù hợp làm response đơn giản; Spring codec sẽ serialize thành JSON.

Request:

~~~http
GET /api/hello?name=Lan HTTP/1.1
Host: localhost:8080
Accept: application/json
~~~

Response body:

~~~json
{
  "message": "Hello, Lan"
}
~~~

Khi không có query parameter:

~~~http
GET /api/hello
~~~

Response:

~~~json
{
  "message": "Hello, World"
}
~~~

### 5.2. Phân tích endpoint /api/events

Endpoint thứ hai trả về **Flux<ServerSentEvent<String>>**. Đây là ví dụ stream dữ liệu theo thời gian:

- **Flux.interval(Duration.ofSeconds(1))** phát một số tăng dần sau mỗi giây.
- **map(...)** biến số thứ tự thành ServerSentEvent.
- **id(...)** đặt event id để client có thể nhận diện sự kiện.
- **event("tick")** đặt tên event.
- **data(...)** đặt payload.
- **produces = TEXT_EVENT_STREAM_VALUE** yêu cầu response dùng media type text/event-stream.

Khi client kết nối, response không cần đợi toàn bộ Flux hoàn tất. Mỗi phần tử được ghi ra khi có tín hiệu. Khi client ngắt kết nối, subscription có thể bị cancel; nguồn interval tương ứng được yêu cầu dừng.

Đây là ví dụ SSE tối thiểu, không phải message broker bền vững. Nếu client ngắt kết nối rồi kết nối lại, server không tự khôi phục mọi event đã bỏ lỡ trừ khi ứng dụng xây dựng cơ chế replay/id riêng.

## 6. Cấu hình WebFlux có chủ đích bằng WebFluxConfigurer

Spring Boot tự cấu hình nhiều phần. Khi cần tùy chỉnh một điểm cụ thể, có thể triển khai **WebFluxConfigurer** mà không bật lại toàn bộ cấu hình bằng @EnableWebFlux.

Tạo tệp **WebFluxConfiguration.java**:

~~~java
package com.example.webflux;

import org.springframework.context.annotation.Configuration;
import org.springframework.http.codec.ServerCodecConfigurer;
import org.springframework.web.reactive.config.WebFluxConfigurer;

@Configuration
public class WebFluxConfiguration implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
        ServerCodecConfigurer configurer
    ) {
        configurer.defaultCodecs()
            .maxInMemorySize(1024 * 1024);
    }
}
~~~

Ở đây cấu hình giới hạn bộ nhớ cho việc đọc/ghi các nội dung mà codec cần buffer ở mức 1 MiB. Đây là giá trị minh họa để thể hiện cách tùy chỉnh; phải chọn theo kích thước payload, giới hạn tài nguyên và yêu cầu của ứng dụng.

**HTTP message codecs** đảm nhiệm chuyển đổi giữa byte stream và kiểu Java, ví dụ:

- JSON thành object Java và ngược lại qua Jackson khi dependency phù hợp có mặt.
- String thành text.
- ByteBuffer/DataBuffer cho dữ liệu nhị phân.
- Server-Sent Events cho stream event.
- Các kiểu dữ liệu reactive như Mono và Flux ở tầng web adapter.

Nếu client gửi payload vượt giới hạn buffer của codec, request có thể thất bại với lỗi giới hạn dữ liệu. Không tăng giới hạn vô hạn chỉ để làm biến mất lỗi; cần kiểm tra kích thước request, streaming và nguy cơ tiêu thụ bộ nhớ.

### 6.1. application.properties

Tạo tệp **src/main/resources/application.properties**:

~~~properties
spring.application.name=reactive-webflux-demo
server.port=8080
logging.level.com.example.webflux=INFO
~~~

- **spring.application.name** đặt tên ứng dụng để quan sát/log.
- **server.port** chọn cổng HTTP.
- **logging.level...** cấu hình mức log cho package ứng dụng.

Có thể thay đổi cổng qua biến môi trường hoặc cấu hình profile. Không hard-code secret, token hoặc thông tin môi trường production trong file properties được commit.

### 6.2. Khi nào cần @EnableWebFlux?

Trong ứng dụng Boot thông thường, hãy để auto-configuration quản lý WebFlux. Nếu thêm **@EnableWebFlux**, ứng dụng chủ động bật cấu hình WebFlux đầy đủ và có thể khiến một số tùy chỉnh mặc định của Boot không còn được áp dụng như trước.

Chỉ sử dụng khi cần kiểm soát sâu và đã hiểu những bean/codec/handler mapping cần tự cấu hình. Với bài toán thông thường như thêm CORS, codec, formatter hoặc converter, bắt đầu từ **WebFluxConfigurer** thường là lựa chọn ít xáo trộn hơn.

## 7. Functional endpoint: RouterFunction và HandlerFunction

Ngoài annotation controller, WebFlux hỗ trợ mô hình functional routing. Hai khái niệm:

- **RouterFunction<ServerResponse>** mô tả điều kiện route và handler tương ứng.
- **HandlerFunction<ServerResponse>** xử lý request đã được route và trả Mono<ServerResponse>.

Tạo tệp **FunctionalRoutes.java**:

~~~java
package com.example.webflux;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class FunctionalRoutes {

    @Bean
    RouterFunction<ServerResponse> helloRoute() {
        return RouterFunctions.route()
            .GET(
                "/functional/hello",
                request -> ServerResponse.ok()
                    .contentType(MediaType.TEXT_PLAIN)
                    .bodyValue("Hello from functional WebFlux")
            )
            .build();
    }
}
~~~

Functional endpoint trên không cần @RestController. Spring nhận bean RouterFunction và đăng ký route tương ứng.

Request:

~~~http
GET /functional/hello HTTP/1.1
Host: localhost:8080
~~~

Response:

~~~text
Hello from functional WebFlux
~~~

### 7.1. Annotation hay functional endpoint?

| Tiêu chí | Annotation controller | Functional endpoint |
| --- | --- | --- |
| Khai báo route | @GetMapping, @PostMapping | RouterFunctions.route |
| Handler | Method trong @RestController | HandlerFunction |
| Phù hợp | REST API phổ biến, controller theo tài nguyên | Route rõ ràng, handler composition, endpoint theo module |
| Validation/binding | Tích hợp annotation và argument resolver | Tự tổ chức đọc request, validate và tạo response |
| Đọc code | Quen thuộc với đa số Spring developer | Tường minh ở tầng routing/handler |

Không cần dùng cả hai phong cách cho cùng một route. Có thể kết hợp trong một ứng dụng nhưng nên phân chia rõ trách nhiệm để tránh route trùng hoặc logic bị chia đôi khó theo dõi.

## 8. Chạy ứng dụng

Điều kiện:

- JDK 17 trở lên.
- Maven 3.6+ hoặc Maven Wrapper.
- Cổng 8080 chưa bị ứng dụng khác chiếm.

Tại thư mục chứa pom.xml:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Hoặc đóng gói rồi chạy JAR:

~~~bash
mvn clean package
java -jar target/reactive-webflux-demo-1.0.0.jar
~~~

Khi khởi động thành công, log thường cho thấy Spring Boot đã khởi tạo ApplicationContext và web server reactive trên cổng 8080. Dòng log cụ thể có thể khác theo phiên bản patch, môi trường và cấu hình logging; không nên phụ thuộc vào toàn bộ câu chữ log để xác định endpoint hoạt động.

### 8.1. Kiểm tra endpoint JSON

Mở terminal khác:

~~~bash
curl "http://localhost:8080/api/hello?name=Lan"
~~~

Kết quả:

~~~json
{"message":"Hello, Lan"}
~~~

Thử default parameter:

~~~bash
curl "http://localhost:8080/api/hello"
~~~

Kết quả:

~~~json
{"message":"Hello, World"}
~~~

Kiểm tra functional route:

~~~bash
curl "http://localhost:8080/functional/hello"
~~~

Kết quả:

~~~text
Hello from functional WebFlux
~~~

### 8.2. Kiểm tra Server-Sent Events

Dùng:

~~~bash
curl -N "http://localhost:8080/api/events"
~~~

Option **-N** tắt buffering phía curl để quan sát từng event khi được gửi. Output minh họa:

~~~text
id:0
event:tick
data:tick-0

id:1
event:tick
data:tick-1

id:2
event:tick
data:tick-2
~~~

Các event tiếp tục phát mỗi giây cho tới khi client ngắt kết nối. Số thứ tự bắt đầu từ 0 trong một subscription mới của Flux.interval.

## 9. Kiểm thử bằng WebTestClient

WebTestClient cho phép gửi request và kiểm tra response mà không cần viết test thủ công bằng curl. Với Spring Boot WebFlux, có thể kiểm thử ứng dụng trên một server ngẫu nhiên.

Tệp **src/test/java/com/example/webflux/GreetingControllerTest.java**:

~~~java
package com.example.webflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class GreetingControllerTest {

    @Autowired
    private WebTestClient client;

    @Test
    void helloReturnsJson() {
        client.get()
            .uri("/api/hello?name=Lan")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
                .jsonPath("$.message")
                .isEqualTo("Hello, Lan");
    }

    @Test
    void functionalRouteReturnsText() {
        client.get()
            .uri("/functional/hello")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("Hello from functional WebFlux");
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Hai test xác nhận:

1. Controller được phát hiện và route GET /api/hello hoạt động.
2. JSON được serialize đúng và query parameter được bind.
3. Functional RouterFunction được đăng ký và trả nội dung text đúng.

Test không cần phụ thuộc cổng 8080 vì Spring Boot dùng cổng ngẫu nhiên. Nếu muốn kiểm tra SSE, nên viết test riêng có giới hạn số event và thời gian chờ phù hợp để test không treo vô hạn.

## 10. Luồng xử lý request tổng quan

~~~text
HTTP Client
    |
    | GET /api/hello?name=Lan
    v
Reactive Web Server
    |
    v
WebFilter chain
    |
    v
Handler Mapping
    |
    +------------------------------+
    |                              |
    v                              v
Annotated Controller          RouterFunction
    |                              |
    v                              v
Mono / Flux                    HandlerFunction
    |                              |
    +---------------+--------------+
                    |
                    v
          Reactive HTTP Adapter
                    |
                    v
             Message Codecs
                    |
                    v
             HTTP Response
~~~

Ở luồng annotation, handler mapping tìm controller method theo mapping. Ở luồng functional, RouterFunction chọn HandlerFunction phù hợp. Cả hai đều trả Publisher reactive để framework điều phối subscription, tín hiệu và response.

Các thành phần chính:

- **Web server** nhận kết nối và tạo request/response abstraction.
- **WebFilter** có thể xử lý cross-cutting concern như correlation ID, CORS, xác thực hoặc logging.
- **HandlerMapping** tìm handler tương ứng.
- **Controller/HandlerFunction** tạo pipeline reactive.
- **HTTP message codecs** chuyển đổi dữ liệu.
- **Reactive adapter** kết nối Publisher với vòng đời HTTP.

Không phải mọi bước đều tạo một thread riêng. Reactor Netty và các thành phần reactive thường dùng event loop; blocking trên event-loop có thể làm nhiều request bị chậm cùng lúc.

## 11. Quy tắc quan trọng về non-blocking

### 11.1. Không gọi block trong controller

Không nên:

~~~java
@GetMapping("/bad")
public String bad() {
    return remoteService.fetch()
        .block();
}
~~~

Lời gọi block đợi kết quả đồng bộ và có thể chặn thread đang xử lý request. Trong WebFlux, hãy trả về Publisher:

~~~java
@GetMapping("/good")
public Mono<Data> good() {
    return remoteService.fetch();
}
~~~

Spring WebFlux sẽ subscribe và ghi response khi tín hiệu đến.

### 11.2. Không subscribe thủ công trong controller

Không nên:

~~~java
@GetMapping("/bad-subscribe")
public Mono<Void> badSubscribe() {
    service.doWork().subscribe();
    return Mono.empty();
}
~~~

Subscription thủ công tách công việc khỏi vòng đời HTTP response. Framework có thể hoàn tất response trước khi công việc xong; lỗi và cancellation của request cũng không còn gắn đúng với tác vụ.

Nên ghép pipeline:

~~~java
@GetMapping("/good-work")
public Mono<Void> goodWork() {
    return service.doWork();
}
~~~

### 11.3. Nếu bắt buộc gọi API blocking

Nếu phải tích hợp một thư viện blocking, cô lập phần đó trên scheduler dành cho blocking:

~~~java
Mono<Result> result = Mono.fromCallable(
        () -> legacyClient.fetchBlocking()
    )
    .subscribeOn(Schedulers.boundedElastic());
~~~

Đây là snippet cần import **reactor.core.publisher.Mono** và **reactor.core.scheduler.Schedulers**. Cách này tránh thực hiện lời gọi blocking trực tiếp trên event-loop, nhưng **không biến thư viện blocking thành non-blocking**. Vẫn phải giới hạn concurrency, timeout, tài nguyên thread và cân nhắc thay thế bằng client reactive khi có thể.

### 11.4. CPU-bound work

Tác vụ tính toán CPU nặng cũng cần được thiết kế có chủ đích. Có thể dùng scheduler phù hợp hoặc tách sang worker pool riêng; không mặc định đưa mọi tác vụ vào boundedElastic. Chọn scheduler theo bản chất công việc và đo dưới tải thực tế.

## 12. Cấu hình thường gặp và cách kiểm tra

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Ứng dụng khởi động MVC thay vì WebFlux | Có spring-boot-starter-web trên classpath | Kiểm tra dependency tree và loại starter không cần thiết |
| Controller không được phát hiện | Package controller nằm ngoài component scan | Đặt dưới package class main hoặc cấu hình scan rõ |
| Endpoint trả 404 | Sai path, HTTP method hoặc route chưa được đăng ký | Kiểm tra mapping và request |
| JSON không serialize như mong đợi | Codec/dependency hoặc kiểu dữ liệu không phù hợp | Kiểm tra Jackson và response type |
| Request body lớn bị từ chối | Giới hạn buffer codec | Đánh giá kích thước và cấu hình maxInMemorySize có kiểm soát |
| CPU/thread bị nghẽn | Có block hoặc thư viện blocking trên event-loop | Dùng API reactive hoặc cô lập blocking work |
| Flux SSE không kết thúc | Flux.interval là stream vô hạn | Client phải cancel; nếu cần hữu hạn, giới hạn bằng take(n) |
| Test WebTestClient không có bean | Thiếu cấu hình test hoặc ứng dụng không chạy WebFlux | Kiểm tra starter, @AutoConfigureWebTestClient và test context |
| Port đã được sử dụng | 8080 đang có tiến trình khác | Đổi server.port hoặc dừng tiến trình cũ |
| Thêm @EnableWebFlux làm mất cấu hình Boot | Đã chuyển sang kiểm soát cấu hình WebFlux thủ công | Bỏ annotation nếu không thực sự cần |

### 12.1. Kiểm tra dependency tree

Có thể chạy:

~~~bash
mvn dependency:tree
~~~

Tìm các dependency liên quan:

- spring-boot-starter-webflux
- reactor-core
- reactor-netty-http
- spring-boot-starter-web

Nếu ứng dụng dự định dùng WebFlux thuần nhưng dependency tree có cả starter MVC, hãy tìm dependency bắc cầu đưa MVC vào và quyết định có cần nó không.

### 12.2. Kiểm tra cấu hình endpoint

Nếu endpoint không hoạt động, đi theo trình tự:

1. Ứng dụng đã khởi động thành công chưa?
2. Server đang lắng nghe cổng nào?
3. Controller/route có nằm trong ApplicationContext không?
4. HTTP method và path có khớp request không?
5. Có filter/security rule chặn request không?
6. Handler trả về kiểu dữ liệu nào?
7. Codec có hỗ trợ kiểu dữ liệu và media type không?
8. Có exception trong pipeline trước khi response được ghi không?

Không nên thêm nhiều annotation/configuration để chữa 404 trước khi xác định mapping có thực sự được đăng ký.

## 13. Khi nào nên thêm cấu hình WebFlux riêng?

Bài thực hành có WebFluxConfigurer chỉ để minh họa một tùy chỉnh codec. Trong dự án thật, chỉ thêm cấu hình khi có yêu cầu rõ:

- **Codec:** giới hạn kích thước payload, đăng ký encoder/decoder hoặc tùy chỉnh format.
- **CORS:** chỉ cho phép origin, method và header cần thiết; không mở wildcard tùy tiện khi có credentials.
- **WebFilter:** correlation ID, logging, security hoặc xử lý request xuyên suốt.
- **WebClient:** base URL, timeout, connector, TLS và filter theo từng dịch vụ.
- **Error handling:** chuyển exception sang response theo hợp đồng API.
- **Resource management:** giới hạn kết nối, timeout và scheduler phù hợp.

Ưu tiên cấu hình nhỏ theo đúng trách nhiệm. Không tạo một class cấu hình lớn gom mọi thứ chỉ vì tất cả đều thuộc WebFlux. Cũng không thêm @EnableWebFlux khi một WebFluxConfigurer đã đáp ứng nhu cầu.

## 14. Bài tập thực hành

**Bài 1 — Endpoint cơ bản:** thêm GET /api/greet nhận query parameter name và trả Mono<Map<String,String>>. Kiểm tra trường hợp có name và không có name.

**Bài 2 — Flux:** thêm GET /api/numbers trả Flux<Integer> từ Flux.range(1,5). Xác định response JSON array khác gì so với text/event-stream.

**Bài 3 — SSE:** thay Flux.interval bằng Flux.interval(...).take(5). Kiểm tra stream kết thúc sau năm event và client nhận event cuối cùng.

**Bài 4 — Functional route:** tạo POST /functional/echo nhận body JSON thành Mono<Map<String,Object>> rồi trả lại body. Kiểm tra Content-Type và body không hợp lệ.

**Bài 5 — Codec:** gửi payload lớn hơn giới hạn maxInMemorySize. Quan sát exception và quyết định giới hạn hợp lý theo use case thay vì tăng vô hạn.

**Bài 6 — Test:** thêm WebTestClient test cho default parameter, status code, JSON path và functional route. Chạy test trên cổng ngẫu nhiên.

**Bài 7 — Blocking:** tạo một hàm giả lập blocking có thời gian chờ; so sánh khi gọi trực tiếp với khi bọc Mono.fromCallable và subscribeOn(boundedElastic). Không dùng kết quả một lần chạy làm benchmark; quan sát thread và throughput dưới tải.

**Bài 8 — Dependency:** thử thêm spring-boot-starter-web vào project rồi kiểm tra loại web application mà Boot chọn. Sau đó bỏ dependency và xác nhận WebFlux thuần.

## 15. Checklist trước khi đưa WebFlux vào dự án

- Dependency có đúng stack WebFlux và không vô tình kéo MVC vào?
- Package scan có bao phủ controller, configuration và service?
- Endpoint trả Mono/Flux hoặc Publisher phù hợp, không block?
- Không subscribe thủ công ở controller/service nếu tác vụ thuộc request?
- HTTP codecs hỗ trợ đúng payload và có giới hạn bộ nhớ hợp lý?
- Timeout, cancellation và error handling đã được thiết kế?
- SSE/streaming có quy tắc reconnect/replay nếu nghiệp vụ cần?
- WebClient và database client có thực sự reactive hay vẫn blocking?
- Cấu hình server, port, logging và profile không chứa secret?
- Có test endpoint bằng WebTestClient?
- Có metrics/tracing để quan sát latency, lỗi và tài nguyên?

## 16. Ghi nhớ

Một ứng dụng Spring WebFlux tối thiểu cần **starter-webflux**, class main Spring Boot, handler trả Publisher và cấu hình HTTP phù hợp. Có thể khai báo endpoint bằng **@RestController** hoặc **RouterFunction**; cả hai đều được tích hợp vào pipeline reactive của framework.

Giá trị của WebFlux đến từ việc giữ chuỗi xử lý non-blocking, quản lý demand/cancellation và stream dữ liệu đúng vòng đời. Chỉ đổi kiểu trả về sang Mono/Flux nhưng vẫn gọi blocking hoặc subscribe tách rời sẽ không tạo ra một ứng dụng reactive đúng nghĩa.

## 17. Tài liệu tham khảo

- Spring Boot Reference — Developing Reactive Applications: https://docs.spring.io/spring-boot/reference/web/reactive.html
- Spring Framework Reference — WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework Reference — Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
- Spring Framework Reference — Functional Endpoints: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
- Spring Framework Reference — HTTP Message Codecs: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Framework Reference — WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Project Reactor Reference Guide: https://projectreactor.io/docs/core/release/reference/

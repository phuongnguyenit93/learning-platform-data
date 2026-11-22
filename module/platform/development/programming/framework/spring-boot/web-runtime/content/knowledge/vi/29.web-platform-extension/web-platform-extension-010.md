# Tránh thêm giao thức hoặc starter không phục vụ nhu cầu ứng dụng

> **Ngữ cảnh:** Spring Boot **web-runtime** → **Mở rộng nền tảng web**. Bài học dùng **Java 17+, Spring Boot 3.3.x và Spring Framework 6.1.x**, tập trung vào việc không đưa WebFlux, WebSocket, STOMP, GraphQL, RSocket, gRPC, SOAP, template engine hay thư viện HTTP mới vào ứng dụng khi nhu cầu thực tế chưa yêu cầu. Mục tiêu không phải “làm JAR nhỏ nhất bằng mọi giá” mà là **hệ thống đủ năng lực, dễ hiểu, được kiểm thử, an toàn và vận hành được**.

## 1. Sau bài học, bạn cần làm được gì?

1. Tách bốn khái niệm: **giao thức truyền thông**, **web stack**, **HTTP client** và **Spring Boot starter**.
2. Xuất phát từ yêu cầu nghiệp vụ để chọn đúng starter cho REST JSON, server-side rendering, reactive I/O, WebSocket hai chiều, SSE một chiều, GraphQL schema, RSocket hoặc SOAP/gRPC theo hợp đồng.
3. Giải thích quy tắc Spring Boot 3.3: nếu cả Spring MVC và Spring WebFlux có mặt, **MVC thường được ưu tiên làm web application type mặc định**; có `WebClient` không đồng nghĩa đã đổi server sang Reactor Netty.
4. Nhận ra starter kéo theo **transitive dependencies** và tác động lên classpath, auto-configuration, codecs, beans, endpoint mappings, client connectors, CVE surface và chi phí vận hành.
5. So sánh các lựa chọn tối thiểu, ví dụ: `RestClient` cho HTTP blocking trong app MVC thay vì thêm WebFlux chỉ để gọi một API đơn giản.
6. Tạo một project Spring Boot MVC Java 17+ có Maven POM, Java controller và HTTP integration test chạy được mà **không cần giao thức thừa**.
7. Dùng `mvn dependency:tree`, `mvn dependency:analyze`, Gradle `dependencyInsight`, Boot conditions report và các test có kiểm soát để giải thích vì sao một dependency có hoặc không có.
8. Đưa ra đề xuất **thêm, giữ hoặc gỡ** starter có lý do rõ, kèm regression tests, security review, benchmark và rollback.

## 2. Giao thức, framework, client API và starter: phân biệt ngay từ đầu

Một giao thức (*protocol*) định nghĩa các thông điệp và quy tắc giao tiếp giữa các thành phần. Ví dụ: HTTP/1.1 hoặc HTTP/2 cho request/response, WebSocket cho liên lạc hai chiều, RSocket cho reactive messaging, gRPC cho RPC theo protobuf/service contract.

Một **web stack** là cách xử lý incoming requests trong ứng dụng:

- **Spring MVC**: mô hình Servlet, `DispatcherServlet`, `@RestController`, embedded Tomcat theo cấu hình mặc định của `spring-boot-starter-web`.
- **Spring WebFlux**: reactive web stack, `Mono`/`Flux`, có thể chạy với Reactor Netty; phù hợp khi request processing và các dependencies quan trọng hỗ trợ non-blocking end-to-end.

Một **HTTP client** là phần ứng dụng đi **gọi ra ngoài**: `RestClient` (blocking), `WebClient` (reactive), `RestTemplate` (legacy), hoặc Java `HttpClient`. Client nào được chọn **không tự quyết định** server xử lý HTTP bằng MVC hay WebFlux.

Một **starter** là dependency bundle được Spring Boot cung cấp để gom các thư viện phù hợp và tận dụng auto-configuration. Starter có tên dễ hiểu nhưng **không phải protocol** và **không có nghĩa** mọi endpoint của công nghệ tương ứng được tự động public.

~~~text
Nghiệp vụ: "khách xem danh mục sản phẩm"
        |
        v
Giao tiếp: HTTP GET /api/products
        |
        v
Server stack: Spring MVC (đủ dùng?)
        |
        v
Dependency: spring-boot-starter-web
        |
        v
Auto-configuration theo classpath + properties
        |
        v
Tomcat / DispatcherServlet / JSON conversion
        |
        v
Test thực tế: HTTP 200, auth, startup, resources
~~~

### Bảng so sánh khái niệm

| Thuật ngữ | Ví dụ | Không phải |
|---|---|---|
| HTTP/2 | `server.http2.enabled=true` với embedded server hỗ trợ | Không phải RSocket hoặc GraphQL |
| Spring MVC | `@RestController`, Servlet | Không phải chỉ HTTP/1.1; có thể dùng HTTPS/HTTP2 |
| Spring WebFlux | `Flux`, reactive routing | Không tự làm JDBC blocking thành non-blocking |
| RestClient | Gọi HTTP blocking tới partner API | Không phải inbound HTTP server |
| WebClient | Gọi HTTP reactive tới partner API | Không buộc app chuyển sang WebFlux server |
| WebSocket | Kết nối hai chiều lâu dài | Không cần chỉ để gửi 1 thông báo mỗi phút |
| GraphQL | Query language, schema, resolver | Không tự thay thế transport HTTP |
| RSocket | Reactive messaging protocol | Không phải alias của HTTP/2 |
| Starter | `spring-boot-starter-graphql` | Không phải một endpoint đã cấu hình xong |

**Thông điệp cốt lõi:** “Thêm thư viện” và “bổ sung năng lực đã được dùng đúng” là hai việc khác nhau. Hãy thiết kế contract trước, đưa dependency vào sau.

## 3. Bắt đầu từ danh sách yêu cầu, không từ tất cả tùy chọn trên Initializr

Ví dụ một sản phẩm mới:

> Ứng dụng quản lý đơn hàng có 8 endpoint JSON, dùng Spring Data JPA để truy vấn cơ sở dữ liệu, xác thực người dùng, gọi một partner REST API và trả response theo HTTP request/response. Không có live chat, không có client GraphQL, không có client RSocket.

Yêu cầu cho thấy cần HTTP REST server, persistence/security và outbound client, nhưng **không có bằng chứng** cần mở WebSocket endpoint, thiết kế GraphQL schema, RSocket TCP listener, gRPC service hoặc thêm cả Thymeleaf, Mustache và FreeMarker.

Một quyết định hợp lý có thể là:

- **Spring MVC** cho các HTTP JSON controllers.
- **RestClient** cho outbound HTTP đồng bộ nếu đáp ứng latency/concurrency budget.
- **Spring Security**, JPA, validation, migration tool, metrics nếu thực tế có yêu cầu tương ứng, chứ không loại bỏ các dependencies bảo mật chỉ để giảm artifact size.
- **Một** embedded servlet server do starter-web quản lý, không cài đồng thời nhiều server runtimes nếu không cần.

Đặt câu hỏi trước mỗi dependency:

1. Client nào cần công nghệ đó? Browser, mobile, third-party, background job hay service khác?
2. Có protocol contract cụ thể và đã có consumer chưa?
3. Cơ chế hiện có (HTTP JSON, polling, SSE, RestClient) có đáp ứng được không?
4. SLO nào không đạt nếu không thêm nó? Độ trễ, concurrency, binary throughput, schema evolution hay bidirectional communication?
5. Thêm nó có làm thay đổi request handling, security, port, resource budget, deployment/proxy không?
6. Ai sẽ bảo trì, theo dõi phiên bản/CVE và xử lý lỗi của giao thức đó?
7. Ta có thể chứng minh lợi ích bằng integration test/benchmark hay chỉ đang dự phòng một nhu cầu chưa có?

**Không cần đạt cực tiểu tuyệt đối.** Một starter cho authentication, metrics, validation hay contract testing là đúng khi nó phục vụ rủi ro/năng lực thật. “Chưa thấy import trong Java” không chứng minh thư viện thừa: có thể runtime dùng qua reflection, SPI hoặc auto-configuration.

## 4. Bảng chọn starter theo nhu cầu thật

| Nhu cầu | Spring Boot 3.3 starter/API thích hợp | Không tự thêm | Kiểm tra trước quyết định |
|---|---|---|---|
| REST JSON với MVC | `spring-boot-starter-web` | webflux, websocket, graphql, rsocket | API clients, Servlet workload |
| Reactive HTTP server non-blocking | `spring-boot-starter-webflux` | web chỉ để “phòng khi cần” | Reactive pipeline thực, drivers, event-loop blocking |
| MVC gọi API đồng bộ | `RestClient` đã có qua Spring Web | Không cần webflux riêng chỉ để gọi HTTP | Timeouts, retries, pool, response bounds |
| MVC cần reactive WebClient | Thêm WebFlux dependencies với mục đích rõ | Không mặc định đổi server từ Tomcat sang Netty | WebClient bean/connector, MVC remains selected |
| HTML render trên server | Chọn một: `spring-boot-starter-thymeleaf`, FreeMarker, Mustache | Không thêm cả ba nếu không dùng | View resolver, template security |
| Server push một chiều | SSE trên HTTP (`SseEmitter` / reactive SSE) | WebSocket/STOMP không tự bắt buộc | Reconnect, proxy buffering, concurrent connections |
| Chat, collaboration full-duplex | `spring-boot-starter-websocket` cho MVC hoặc WebFlux WebSocket support | GraphQL/RSocket không đương nhiên cần | Authentication, origin, scaling |
| GraphQL schema/query API | `spring-boot-starter-graphql` + web transport | Không thêm WebSocket/RSocket nếu không dùng | Schema, resolver, authorization, query limits |
| RSocket transport thật | `spring-boot-starter-rsocket` | Không phải để bật HTTP/2 | RSocket client, routing/transport, network |
| SOAP/WSDL integration | `spring-boot-starter-web-services` | Không thay bằng GraphQL chỉ vì hiện đại | SOAP contract, XML schema, security |
| gRPC/protobuf interface | gRPC/protobuf SDK/toolchain thích hợp | Không tự giả định Boot 3.3 có một official gRPC starter bắt buộc | Proto contract, generated code, TLS, deadlines |
| Hypermedia REST contract | `spring-boot-starter-hateoas` | Không bắt buộc cho mọi REST API | Link relations, client behavior |
| Jakarta Bean Validation cần thiết | `spring-boot-starter-validation` | Không thêm khi không có validation use case | Constraints, error contract |
| Production management | `spring-boot-starter-actuator` | Không public diagnostics tùy tiện | Endpoint exposure, security/monitoring |
| Unit/integration testing | `spring-boot-starter-test` ở scope test | Không đưa vào runtime chỉ để có JUnit | Maven scopes, CI |

Một starter chỉ là **điểm khởi đầu**. Để có GraphQL endpoint thật cần schema và handler phù hợp; với WebSocket cần endpoint/handler hoặc STOMP broker config; với gRPC cần proto service, generated code, listener và client; với RSocket cần transport/routing configuration. Không được coi “đã khai báo dependency” là “feature chạy đúng và an toàn”.

## 5. Classpath thay đổi thì auto-configuration có thể thay đổi

Spring Boot kiểm tra các điều kiện như `@ConditionalOnClass`, `@ConditionalOnMissingBean`, `@ConditionalOnProperty` và `@ConditionalOnWebApplication` để quyết định tạo những beans/auto-configurations nào. Một starter kéo transitive dependencies vào **runtime classpath**; do đó nó có thể thay đổi điều kiện match.

~~~text
Maven pom.xml / Gradle dependencies
         |
         v
Resolved compile/runtime classpath
         |
         v
Spring Boot auto-configuration conditions
         |
         +--> match: đăng ký beans/config/handlers phù hợp
         |
         +--> no match: bỏ qua auto-configuration
         |
         +--> conflict/missing config: có thể khởi động lỗi
         |
         v
Thực tế runtime: context, port, endpoint, resource
~~~

Có **thể** xảy ra các tác động: thêm HTTP client connector candidate, thêm message converters, thêm serializer, thêm beans, thay điều kiện auto-config, tăng startup work hoặc tạo endpoint khi đã có config phù hợp. Nhưng không phải mỗi starter đều tạo listener/endpoint mới; điều kiện và code ứng dụng quyết định.

### Vì sao thêm WebFlux vào MVC không tự đổi server?

Trong Spring Boot 3.3, khi chỉ có `spring-boot-starter-web`, app thường là Servlet MVC với Tomcat. Khi chỉ có `spring-boot-starter-webflux`, app thường là reactive web application với Reactor Netty. Khi **cả hai** có mặt, Spring MVC được **ưu tiên** làm web application type mặc định. Đây là hành vi có chủ đích vì nhiều MVC apps thêm WebFlux chỉ để dùng outbound `WebClient`.

~~~text
starter-web                  -> Servlet MVC / default Tomcat
starter-webflux              -> Reactive WebFlux / default Reactor Netty
starter-web + starter-webflux -> Servlet MVC thường được chọn,
                                 WebClient vẫn dùng được ở outbound
~~~

Đổi sang reactive bằng `spring.main.web-application-type=reactive` có thể làm được trong bối cảnh phù hợp, **nhưng không phải biện pháp sửa dependency graph tùy tiện**. Những Servlet filters, controller assumptions và các blocking dependencies phải được kiểm tra/chuyển đổi theo lộ trình rõ ràng.

### Tại sao không ép nhiều embedded servers cùng tồn tại?

Servlet starter-web dùng Tomcat mặc định, WebFlux starter dùng Reactor Netty mặc định. Nếu ứng dụng đổi sang Jetty/Undertow theo một mục tiêu vận hành, hãy thay dependency server theo hướng dẫn của Boot và kiểm thử. Đừng giữ Tomcat, Jetty, Undertow và Netty ở runtime chỉ vì “server nào phù hợp Boot sẽ chọn”: tăng confusion và compatibility work mà không có nhu cầu.

## 6. Cách quyết định MVC, WebFlux và outbound HTTP client

### Spring MVC có thể là lựa chọn đủ tốt

Spring MVC/Servlet thích hợp khi phần lớn code là REST JSON, có JPA/JDBC hoặc các SDK blocking, và throughput/latency đo được đạt SLO. MVC còn hỗ trợ async request processing, HTTP streaming và `SseEmitter` cho các trường hợp phù hợp. “Blocking” không đồng nghĩa “không mở rộng được”; cần đo thread/concurrency, connection pools, DB latency, HTTP proxy behavior.

### Khi nào WebFlux là lựa chọn hợp lý?

WebFlux có thể phù hợp nếu I/O concurrency và streaming là yêu cầu rõ, các downstream drivers thật sự non-blocking, team hiểu `Mono`/`Flux`, backpressure, cancellation, pooled `DataBuffer` và vận hành reactive. Thêm WebFlux trong khi code vẫn gọi JDBC blocking trên Netty event loop **không** làm I/O trở nên non-blocking.

### Chỉ gọi REST bên ngoài: RestClient trước khi WebClient nếu phù hợp

Spring Framework 6.1 cung cấp `RestClient` fluent blocking API. Trong ứng dụng MVC đã dùng starter-web, không nhất thiết thêm starter-webflux chỉ để gọi `GET /partner/health` đồng bộ.

Ví dụ **snippet bên trong service**:

~~~java
// Cần imports RestClient và một class PartnerDto của ứng dụng.
private final RestClient client;

public PartnerService(RestClient.Builder builder) {
    this.client = builder
            .baseUrl("https://partner.example.test")
            .build();
}

public PartnerDto load(long id) {
    return client.get()
            .uri("/items/{id}", id)
            .retrieve()
            .body(PartnerDto.class);
}
~~~

Đoạn trên **không phải Java class hoàn chỉnh**, chỉ minh họa cách Boot có thể inject `RestClient.Builder`. Production vẫn phải đặt connect/read timeouts, validate TLS, giới hạn response, tránh SSRF, map 4xx/5xx và đo concurrency. Khi thật sự cần reactive composition hoặc xử lý stream response lớn, `WebClient` có thể có lợi và việc thêm WebFlux dependencies có lý do cụ thể.

## 7. Realtime không tự động có nghĩa WebSocket

Nếu dashboard chỉ nhận thông báo tiến độ 3 giây/lần, hãy so sánh:

| Cơ chế | Đặc tính | Có cần WebSocket starter không? |
|---|---|---|
| HTTP polling | Client GET theo interval | Không |
| Long polling | Server giữ GET cho tới khi có event/timeout | Không |
| SSE | `text/event-stream` cho server→browser push | Không |
| WebSocket | Client↔server full-duplex liên tục | Trong MVC thường cần `spring-boot-starter-websocket` |
| STOMP over WebSocket | Destinations, subscription, broker concepts | Cần messaging/STOMP configuration ngoài WebSocket transport |
| RSocket | Binary/reactive messaging với transport riêng | Không phải cùng giao thức WebSocket/HTTP SSE |

**SSE trên MVC** có `SseEmitter`. Một method minh họa:

~~~java
// Snippet trong @RestController MVC, không phải cả ứng dụng.
@GetMapping(value = "/api/progress",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public SseEmitter progress() {
    SseEmitter emitter = new SseEmitter(10_000L);
    try {
        emitter.send(SseEmitter.event()
                .name("progress")
                .data("done"));
        emitter.complete();
    } catch (Exception ex) {
        emitter.completeWithError(ex);
    }
    return emitter;
}
~~~

Các imports cần `org.springframework.http.MediaType`, `org.springframework.web.bind.annotation.GetMapping` và `org.springframework.web.servlet.mvc.method.annotation.SseEmitter`. Đây là mảnh code để cho thấy **đã có SSE trong MVC**; production cần quản lý thread/async, disconnect, heartbeat, proxy buffering và số connections.

Nếu application cần chat thật, client gửi message liên tục, co-edit hoặc game state full-duplex, WebSocket có thể có lợi. Lúc ấy phải thiết kế authentication, origin policies, heartbeat, idle timeout, rate limits và scaling, không chỉ thêm dependency. `spring-boot-starter-websocket` trong MVC **không tự mở `/ws` endpoint** nếu không có handler hoặc broker mapping được cấu hình.

## 8. GraphQL khi nào thực sự phục vụ sản phẩm?

GraphQL giải quyết bài toán query/mutation/subscription theo **schema**. Nó có ích khi nhiều clients cần projection linh hoạt, schema evolution hoặc một domain graph mà REST hiện tại phục vụ kém. Nó cũng thêm công việc:

- Schema `.graphqls` và resolvers/data fetchers.
- Authorization có thể theo field/object; không dựa duy nhất HTTP route.
- Query complexity/depth/cost limits, N+1/DataLoader và timeout.
- Error mapping, caching strategy, schema migration và tooling.
- Monitoring per operation, public schema/docs policy.

Spring Boot 3.3 `spring-boot-starter-graphql` **cần web transport** để expose GraphQL qua HTTP; nếu dùng MVC thì `spring-boot-starter-web`, nếu dùng reactive server thì `spring-boot-starter-webflux`. GraphQL là transport-agnostic. GraphQL WebSocket endpoint **không bật theo mặc định**, và với Servlet phải có WebSocket transport support cộng `spring.graphql.websocket.path`. Không thêm GraphQL starter chỉ vì “frontend hiện gọi 3 endpoints”; có thể tối ưu một REST endpoint hoặc dùng caching trước.

Một schema minh họa nhỏ:

~~~graphql
type Query {
    product(id: ID!): Product
}

type Product {
    id: ID!
    name: String!
}
~~~

Schema chưa có DataFetcher/`@QueryMapping`, transport và security — **không phải GraphQL API runnable độc lập**. Chính khoảng cách từ “starter added” đến “API vận hành an toàn” là thứ cần được đưa vào dependency decision.

## 9. RSocket, gRPC, SOAP và những lựa chọn khác

### RSocket

RSocket là giao thức khác HTTP, với các interaction models như request-response, request-stream, fire-and-forget và request-channel. Khi những consumers của bạn có RSocket client và việc reactive streaming/routing là yêu cầu chính, `spring-boot-starter-rsocket` phù hợp. Nhưng một REST JSON app thông thường không cần RSocket chỉ vì bạn thấy “backpressure” là tính năng hay. Thiết kế còn phải bao gồm TCP/WebSocket transport, routes, authentication, port/proxy support và codec versioning.

### gRPC

gRPC thường dùng Protocol Buffers, generated stubs và HTTP/2. Nó **không phải** một setting mới của Spring MVC, cũng không tự có chỉ vì `server.http2.enabled=true`. Spring Boot 3.3 không quy định một official gRPC starter duy nhất bắt buộc cho mọi dự án; thư viện/framework tích hợp được chọn theo contract và compatibility. Khi client không có protobuf/gRPC requirements, không tự đưa protoc compiler, code generation và extra listener vào service.

### SOAP/Web Services

Nếu tích hợp WSDL/XSD, SOAP security/headers và hiện có SOAP clients, `spring-boot-starter-web-services` có mục đích thực. Nếu API chỉ dùng JSON, SOAP runtime không giúp GET/POST JSON tốt hơn.

### HATEOAS

HATEOAS hữu ích khi representation chứa links/affordances mà clients thật sự theo để điều hướng. Nếu API đơn giản chỉ trao DTO JSON, `spring-boot-starter-hateoas` không bắt buộc để “đạt chuẩn REST”.

### Template engines

Nếu ứng dụng render HTML tại server, chọn Thymeleaf, FreeMarker, Mustache hoặc engine phù hợp **theo nhu cầu UI**. Nếu chỉ có `@RestController` trả JSON, không cần cài tất cả templates; thêm engine không tự cải thiện REST performance và có thể làm view resolver/config phức tạp.

## 10. HTTP/2, HTTPS và compression không phải một protocol starter mới

Spring MVC/Tomcat và WebFlux server phù hợp có khả năng nói HTTP/2 theo điều kiện runtime. Tùy deployment, có thể dùng:

~~~properties
server.http2.enabled=true
~~~

Đây là **server capability/configuration**; với HTTPS cần TLS certificate đúng, client/ALPN support và kiểm negotiated protocol. Nó không đòi thêm RSocket, gRPC hoặc GraphQL starter. Một client dùng HTTP/2 tới ingress không chứng minh hop ingress→backend cũng dùng HTTP/2.

Compression:

~~~properties
server.compression.enabled=true
~~~

là cấu hình HTTP server để tiết kiệm bandwidth cho những responses đủ điều kiện; không cần thêm “compression protocol” mới chỉ vì JSON có thể nén. Phải đo CPU và network, đúng MIME/Accept-Encoding/Vary nếu cache có representation variants. Một số image/video/archives đã nén không có lợi khi nén lại.

Tương tự, HTTPS với Spring Boot 3.3 có thể dùng `server.ssl.bundle` và PEM/JKS bundle cho embedded server; không nên đưa một messaging starter vào project chỉ để bật TLS.

## 11. Lab runnable: Spring Boot MVC phục vụ JSON với starter tối thiểu

Một ứng dụng độc lập có **một REST endpoint** và test. Không sử dụng các protocol không cần thiết.

### 11.1. Cây thư mục

~~~text
minimal-web/
  pom.xml
  src/
    main/
      java/
        example/
          minimalweb/
            MinimalWebApplication.java
      resources/
        application.properties
    test/
      java/
        example/
          minimalweb/
            MinimalWebApplicationTests.java
~~~

### 11.2. Maven pom.xml đầy đủ (Boot 3.3.13, Java 17)

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

    <groupId>example</groupId>
    <artifactId>minimal-web</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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

`spring-boot-starter-test` ở **test scope**, không phải runtime capability. BOM từ Boot parent quản lý versions liên quan; không cần tự thêm `spring-webmvc`, Jackson hoặc Tomcat với custom versions để controller hoạt động.

### 11.3. Java application hoàn chỉnh

Tạo `src/main/java/example/minimalweb/MinimalWebApplication.java`:

~~~java
package example.minimalweb;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MinimalWebApplication {
    public static void main(String[] args) {
        SpringApplication.run(MinimalWebApplication.class, args);
    }

    public record Greeting(String message) { }

    @RestController
    static class GreetingController {
        @GetMapping("/api/greeting")
        public Greeting greeting() {
            return new Greeting("xin chào");
        }
    }
}
~~~

`@SpringBootApplication` đặt trên application class, scan nested `@RestController` cùng package. Spring MVC handler mapping đưa HTTP GET tới method. Jackson từ web starter serialize record thành JSON. Không cần WebFlux `Mono`, WebSocket broker, GraphQL schema hay template engine.

### 11.4. application.properties

~~~properties
server.port=8080
~~~

Chạy trong thư mục project:

~~~bash
mvn spring-boot:run
~~~

Kiểm API từ terminal khác:

~~~bash
curl -i http://localhost:8080/api/greeting
~~~

Kỳ vọng status **200 OK**, body JSON tương đương:

~~~json
{"message":"xin chào"}
~~~

Headers như Content-Type/Date/Content-Length có thể có thêm thông tin và thứ tự thay đổi. Không cần ép một stdout bất biến cho Maven hoặc HTTP response. Một cổng HTTP server là đủ cho use case này.

### 11.5. Integration test có embedded web server thật

Tạo `src/test/java/example/minimalweb/MinimalWebApplicationTests.java`:

~~~java
package example.minimalweb;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class MinimalWebApplicationTests {
    @Autowired
    private TestRestTemplate http;

    @Autowired
    private ApplicationContext context;

    @Test
    void usesServletWebStack() {
        assertTrue(context instanceof
                ServletWebServerApplicationContext);
    }

    @Test
    void returnsGreetingJson() {
        ResponseEntity<MinimalWebApplication.Greeting> response =
                http.getForEntity("/api/greeting",
                        MinimalWebApplication.Greeting.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertNotNull(response.getBody());
        assertEquals("xin chào", response.getBody().message());
    }
}
~~~

Đây là **file Java test hoàn chỉnh**, tương thích JUnit Jupiter/Spring Boot Test từ starter-test. `RANDOM_PORT` cho test chạy embedded server trên port ngẫu nhiên (không phải cố chấp sử dụng 8080 trong application.properties). Assertion `ServletWebServerApplicationContext` xác nhận application test đang dùng MVC/Servlet context; test thứ hai kiểm tra HTTP endpoint/JSON.

Chạy:

~~~bash
mvn test
mvn clean package
~~~

Trong điều kiện JDK 17/Maven và Maven Central hoạt động, hai tests phải pass. Không coi test này chứng minh production authorization/TLS đúng; lab cố tình chưa thêm security và DB. Nếu sản phẩm yêu cầu authentication/authorization, phải thêm starter/config và integration tests tương ứng — **không được gỡ các kiểm soát cần thiết** chỉ vì bài nói tránh dependency thừa.

## 12. Thử nghiệm trước–sau khi thêm một starter không cần

Trên một nhánh thử nghiệm của lab, thêm:

~~~xml
<!-- Thêm tạm để nghiên cứu: chưa có use case WebSocket -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-websocket</artifactId>
</dependency>
~~~

Sau đó chạy lại:

~~~bash
mvn test
mvn dependency:tree
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Quan sát:

- Dependency tree có thêm những libraries nào?
- Conditions Evaluation Report có matches mới không?
- Application context/server có thay đổi không?
- Có WebSocket endpoint nào thực sự được mapping không?
- Các tests HTTP REST cũ có còn pass không?
- JAR size/startup/heap có tăng theo measurement không?

Không tuyên bố **starter-websocket tự mở port** hoặc endpoint `/ws`; bạn chưa khai báo WebSocket handler. Sau khi thu thập evidence, hãy gỡ dependency không có requirement, không giữ nó chỉ vì không thấy lỗi startup.

Thí nghiệm tương tự với `spring-boot-starter-webflux`: Boot 3.3 thường vẫn chọn MVC khi có cả hai starters. Nếu bạn muốn `WebClient` cho outbound I/O thực, hãy ghi lý do và có tests/metrics tương ứng; nếu không, bỏ sự phức tạp đó.

## 13. Maven dependency tree: direct vs transitive dependencies

`pom.xml` chỉ liệt kê dependency trực tiếp. `spring-boot-starter-web` kéo Spring MVC, Jackson, embedded servlet container và các modules hỗ trợ **qua transitive dependencies**. Không xóa `spring-webmvc`/Tomcat/Jackson chỉ vì source code không import từng library.

~~~text
Ứng dụng minimal-web
  |
  +-- spring-boot-starter-web      [direct]
  |       |
  |       +-- Spring MVC            [transitive]
  |       +-- embedded Tomcat       [transitive]
  |       +-- JSON libraries        [transitive]
  |
  +-- spring-boot-starter-test     [test scope]
~~~

Đây là sơ đồ khái niệm, **không phải output chính xác** của `mvn dependency:tree`. Kiểm thực tế bằng:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dscope=runtime
mvn dependency:tree -Dincludes=org.springframework:spring-webflux
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-websocket
~~~

`-Dincludes` giúp tìm một library và đường phụ thuộc. Khi audit, cần phân biệt runtime/compile/test scopes. Các `test` dependencies không trở thành runtime libraries trong executable archive thông thường.

### Gradle tương đương

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webflux --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-netty --configuration runtimeClasspath
~~~

Windows dùng `gradlew.bat`. `dependencyInsight` giúp thấy vì sao dependency xuất hiện và cơ chế chọn version trong runtimeClasspath.

### “Unused dependency” không đồng nghĩa an toàn để gỡ

~~~bash
mvn dependency:analyze
~~~

Static analysis có thể báo declared-unused nếu framework sử dụng dependency qua Spring auto-configuration, reflection, ServiceLoader, Jackson modules, annotations hoặc runtime wiring. Xem báo cáo như **đầu mối cần kiểm tra**, không làm theo kiểu xóa tất cả không hỏi. Quyết định gỡ cần integration/runtime tests, không chỉ pass compile.

## 14. Conditions Evaluation Report: auto-configuration nào thực sự bật?

Dùng Boot `--debug` trong local environment:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

hoặc với JAR đã build:

~~~bash
java -jar target/minimal-web-0.0.1-SNAPSHOT.jar --debug
~~~

Spring Boot có thể in **Conditions Evaluation Report** gồm positive matches/negative matches và lý do. Dùng nó để trả lời:

- Servlet MVC auto-config đã match chưa?
- WebFlux server auto-config có bị loại vì web application type không?
- Có WebSocket/GraphQL/RSocket config nào match thật không?
- Vì sao một bean hoặc converter được tạo/hay bị bỏ qua?
- Dependencies mới có ảnh hưởng tới HTTP client connector selection không?

Không cố tìm một dòng report không tồn tại chỉ dựa trên tên starter. Kết quả là các auto-configuration classes/conditions theo actual Boot version.

Nếu có `spring-boot-starter-actuator`, endpoint `/actuator/conditions` cung cấp report tương tự **khi được cấu hình expose và bảo vệ**. Spring Boot 3.3 mặc định không expose tất cả Actuator endpoints qua HTTP. **Không bật `management.endpoints.web.exposure.include=*` công khai** chỉ để tìm lỗi dependency; report/beans/configprops có thể lộ cấu trúc nội bộ và chi tiết triển khai.

## 15. Đo tác động: dependency cost không chỉ tính số JAR

Các tác động có thể có:

| Chi phí | Nguồn | Cần đo bằng gì? |
|---|---|---|
| Executable JAR/image size | Thêm transitive dependencies | Compare JAR/image bytes |
| Startup | Classpath/auto-config/bean initialization | Startup time và conditions report |
| Memory | Objects, codecs, caches, native buffers, pools | Heap/native memory, GC, threads |
| Network surface | New listeners/routes nếu config thực bật | Test ports, mappings, ingress |
| Security | Nhiều component versions/CVEs, parsing features | SBOM/SCA, CVE applicability |
| Upgrades | Version skew/conflicts, BOM maintenance | Dependency tree, compatibility tests |
| Operational burden | Logs, health, session state, proxies, timeouts | Runbook/alerts/SLIs |
| Developer burden | Một stack và programming model mới | Training, code review, testing |

Có thể xem artifact:

~~~bash
mvn clean package
jar tf target/minimal-web-0.0.1-SNAPSHOT.jar
~~~

Trên Linux/macOS:

~~~bash
ls -lh target/*.jar
~~~

Trên Windows PowerShell:

~~~powershell
Get-ChildItem target -Filter "*.jar" |
    Select-Object Name, Length
~~~

Spring Boot executable JAR thường đóng dependencies dưới `BOOT-INF/lib`. Không phải mọi library trên classpath đều được khởi tạo hoặc làm app chậm theo cùng cách; chỉ đo cùng workload mới kết luận được performance. Một dependency nhỏ vẫn có thể mở parser/endpoint nhạy cảm nếu được cấu hình sai, và một dependency lớn vẫn có thể cần thiết cho tính đúng/bảo mật.

**SBOM** và software composition analysis (SCA) giúp theo dõi versions, licenses, advisories. Không lấy tổng số CVEs công cụ báo làm bằng chứng ứng dụng có thể khai thác được ngay; xem version, affected code path và exposure. Nhưng dependency không phục vụ năng lực nào thường không đáng gánh upgrade/security obligations lâu dài.

## 16. Quản lý version: để Boot BOM làm đúng phần việc của nó

Maven parent `spring-boot-starter-parent` hoặc `spring-boot-dependencies` BOM quản lý một tập các phiên bản thư viện tương thích đã được thử nghiệm với Spring Boot. Với các dependencies được quản lý, thông thường **không phải** tự gắn version riêng cho Spring MVC, Jackson, Tomcat, Reactor/Netty.

Tránh anti-pattern:

~~~xml
<!-- Minh họa ý tưởng sai: đè version ngẫu nhiên,
     không phải một dependency được khuyên dùng. -->
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-webmvc</artifactId>
    <version>6.x.y-tuy-chon</version>
</dependency>
~~~

Đây **không phải snippet hợp lệ để chạy Maven** vì `6.x.y-tuy-chon` là chuỗi minh họa; mục đích là nhấn mạnh: không override phiên bản nếu chưa có compatibility/security plan. Một lần override có thể cần khi xử lý advisory khẩn cấp nhưng phải có test coverage, pin rationale và lịch bỏ override khi nâng Boot.

**Version lab 3.3.13** được dùng để tái lập các APIs trong bài. Production nên chọn **nhánh Spring Boot còn được bảo trì và nhận security updates** theo chính sách tổ chức, không giữ một version cũ chỉ vì example.

## 17. Vì sao không gỡ bừa transitive dependencies?

Giả sử source không import `ObjectMapper` nhưng controller trả một Java record qua JSON. Jackson vẫn có thể được Spring MVC dùng để serialize body. Loại nó có thể phá endpoint. Tương tự, app không import `Tomcat` trực tiếp nhưng cần embedded HTTP server. Spring Security, validation provider hoặc Jackson modules cũng có thể được sử dụng bằng reflection/config và ít import trong business code.

Muốn đổi server, hãy dùng phương án Boot hỗ trợ: ví dụ thay embedded Tomcat bằng Jetty/Undertow trong Servlet stack, **loại đúng starter cũ và thêm starter tương ứng**, kiểm build/runtime/HTTP2/TLS/cookies/sessions/WebSockets nếu có. Không giữ nhiều servers chỉ để “chờ chọn”.

Mục tiêu là **tối thiểu có chủ đích**, không phải số dependency thấp nhất bất chấp behavior. Khi một feature thực tế cần, dependency của feature đó là hợp lý dù làm JAR to hơn.

## 18. Quy trình thêm dependency/starter mới có kiểm chứng

1. **Ghi use case bằng lời nghiệp vụ.** Client nào, dữ liệu nào, cần one-way hay two-way, request/stream, schema/version?
2. **Xét giải pháp đã có.** REST JSON/SSE/RestClient/async MVC có đạt SLO không?
3. **Chọn một ứng viên.** Không thêm đồng thời 4 protocols “để so sánh sau” trong production graph.
4. **Vẽ data path.** Client→proxy→server, server→downstream, port/protocol/TLS/authentication/authorization.
5. **Kiểm direct và transitive dependencies.** So Maven/Gradle tree, BOM versions, licenses/CVEs.
6. **Kiểm Boot conditions và runtime.** Web application type, beans, endpoint mappings, network listener.
7. **Viết acceptance tests.** Correctness, authenticated/unauthorized requests, payload limits, cancellation, backpressure nếu áp dụng.
8. **Đo baseline và candidate.** Startup, heap/direct memory, threads, latency/throughput, CPU, artifact/image size.
9. **Quản lý triển khai.** Config/ports/ingress, alerts/metrics, owner, rollback, deployment rollout.
10. **Ghi quyết định.** Vì sao chọn starter, phiên bản Boot, ai bảo trì, khi nào review lại.

Ví dụ với “cập nhật tiến độ 5 giây/lần”: thử polling HTTP trước, rồi SSE nếu muốn push một chiều; chỉ xem xét WebSocket khi có messages hai chiều hoặc một contract cụ thể mà polling/SSE không đạt. Không sử dụng benchmark chưa đo để tự tuyên bố WebSocket nhanh hơn ở mọi trường hợp.

### Mẫu Dependency Decision Record

~~~markdown
# Quyết định thêm dependency

## Use case
- Client sử dụng:
- Contract/protocol bắt buộc:
- Latency/throughput/availability SLO:

## Lựa chọn đã xem xét
- Dùng HTTP/API hiện tại:
- Dùng library nhỏ hơn hoặc client hiện tại:
- Giao thức/starter mới:

## Tác động
- Direct + transitive dependencies:
- Auto-configuration, beans, routes, ports:
- Security/TLS/authn/authz:
- Memory/threads/startup/packaging:
- Observability và owner:

## Kiểm thử/triển khai
- Unit/integration/contract tests:
- Load/cancel/error tests:
- No unexpected public endpoints:
- Rollback plan:

## Quyết định
- Thêm/giữ/không thêm:
- Lý do và thời điểm review:
~~~

Mẫu này là **tài liệu quyết định**, không được nhúng nguyên như một runtime config file. Nó giúp team biết lý do có một starter, thay vì chỉ thấy nó được thêm vì “đã chọn trong wizard”.

## 19. Quy trình gỡ starter không phục vụ nhu cầu

Nếu một starter được nghi là thừa, đừng xóa vội:

1. Phân biệt nó là **direct** hay **transitive** dependency; tìm path trong tree.
2. Tìm Java/Kotlin imports, XML/config properties, generated code, SPI, runtime reflection và integration clients.
3. Hỏi owner của public protocol/legacy clients: một WebSocket endpoint ít dùng vẫn có thể là hợp đồng quan trọng.
4. Ghi baseline: API/contract tests, dependency tree, actual port mappings, bean conditions, security controls, metrics.
5. Gỡ **đúng direct dependency** trên nhánh thử nghiệm; không sửa các files/hàng/tab khác trong một thay đổi audit không liên quan.
6. Chạy `mvn test`, packaging, e2e/security/contract tests và kiểm runtime.
7. Kiểm framework/client connector selection sau khi classpath đổi; ví dụ WebClient có thể chọn underlying HTTP connector khác.
8. Đo lợi ích thực tế (artifact, startup, memory/CVE scope) và regression risk.
9. Deploy canary/staging nếu cần, theo dõi metrics, giữ rollback.
10. Cập nhật decision record và xóa properties/config mồ côi **sau khi** đã xác minh chúng thực sự không dùng.

**Không xóa security/validation/observability bắt buộc** để giảm vài MB. “Không thấy code import” và “compile pass” chưa bảo đảm runtime/reflection/external clients vẫn hoạt động.

### Khi nào giữ một starter?

- Có consumer thực hoặc contract đã cam kết.
- Chức năng được sử dụng qua auto-config, runtime SPI hay generated code.
- Removal rủi ro cao và benefit chưa được chứng minh bằng số liệu.
- Starter cung cấp security/validation/operability được yêu cầu.
- Có planned migration với deprecation date thay vì gỡ đột ngột.

## 20. CI và review để dependency graph không tăng vô hạn

Một pipeline/PR review có thể kiểm:

~~~text
1. Compilation and unit tests
2. Integration + contract tests
3. Dependency graph delta and SBOM
4. Vulnerability and license review
5. Auto-configuration/startup smoke
6. Actual endpoint/port inventory
7. Authorization/TLS/CORS checks where relevant
8. Performance smoke on representative load
9. Dependency decision rationale and rollback
~~~

Không fail CI chỉ vì tổng số JAR tăng trên một ngưỡng tùy ý. Nên có chính sách rõ cho: dependency nguồn gốc không đáng tin, known exploitable advisories, version overrides, giao thức mới chưa review, unexpected management endpoints hoặc open listeners. Một tính năng quan trọng vẫn có thể cần dependency lớn hơn; chất lượng được đo bằng **rủi ro/lợi ích**, không phải chỉ size.

Bảng inventory giả định:

| Dependency | Lý do có mặt | Bằng chứng | Hành động |
|---|---|---|---|
| starter-web | REST JSON MVC | HTTP integration tests | Giữ |
| starter-test (test scope) | Regression suite | `mvn test` | Giữ test scope |
| starter-webflux | Không có WebClient/reactive server | Chưa có test/use case | Điều tra |
| starter-websocket | Không có handler/duplex clients | Chưa có contract | Điều tra |
| starter-graphql | Không có schema/consumers | Chưa có contract | Điều tra |
| starter-actuator | SLO/production management | Monitoring + auth tests | Giữ nếu yêu cầu |

Đây chỉ là ví dụ; **không phải kết quả rà soát một repository thực**. Cột “điều tra” có nghĩa chưa đủ bằng chứng để kết luận, không phải lệnh xóa lập tức.

## 21. Những hiểu lầm cần tránh

| Hiểu lầm | Điều đúng hơn |
|---|---|
| “Microservices bắt buộc dùng gRPC.” | HTTP/JSON có thể đủ; gRPC cần contract/client/protobuf tooling thực |
| “Có realtime thì phải thêm WebSocket.” | Polling/SSE có thể đủ cho server push một chiều |
| “Thêm WebFlux làm MVC non-blocking.” | MVC vẫn được ưu tiên mặc định khi cả hai có mặt |
| “Có WebClient thì server phải dùng Netty.” | WebClient outbound độc lập với inbound MVC/Tomcat |
| “RSocket chính là HTTP/2.” | Hai protocols khác nhau |
| “GraphQL sẽ sửa mọi vấn đề REST.” | GraphQL thêm schema/resolvers/query auth & complexity |
| “WebSocket starter tự bật endpoint.” | Handler/broker mapping cần thiết |
| “Mỗi starter mở thêm một cổng.” | Không; auto-config có điều kiện |
| “Không import trực tiếp thì dependency không được dùng.” | SPI/reflection/auto-config có thể dùng |
| “Starter càng nhiều thì performance càng tốt.” | Phải đo; complexity có thể tăng |
| “Starter càng ít thì bảo mật càng tốt.” | Không được bỏ security/validation cần thiết |
| “Có BOM thì không phải theo dõi CVE.” | BOM hỗ trợ compatibility; vẫn cần patch policy |
| “Chỉ compile pass là gỡ dependency an toàn.” | Cần integration/runtime/external client tests |
| “Actuator mặc định expose tất cả endpoints.” | HTTP exposure của Actuator bị giới hạn; mở thêm phải bảo vệ |
| “Muốn HTTP/2 phải thêm GraphQL/gRPC.” | HTTP/2 là capability của HTTP server/client |
| “Chỉ cần thêm GraphQL starter là có API hoàn chỉnh.” | Còn schema, resolvers, transport và bảo mật |
| “Mỗi transitive dependency là thừa.” | Nhiều JAR có vai trò quan trọng trong starter đã chọn |

## 22. Bài tập với lời giải gợi ý

**Bài tập A — REST-only:** service có ba GET và hai POST JSON, gọi partner qua HTTP blocking, không có client GraphQL/WebSocket. Chọn starters tối thiểu.

*Hướng giải:* starter-web + starter-test, mở rộng có chủ đích cho Security/Validation/DB/observability khi product cần. Dùng RestClient, không thêm WebFlux server hay RSocket.

**Bài tập B — kiểm tra web application type:** chạy lab, xác minh `ServletWebServerApplicationContext`. Thêm starter-webflux trên nhánh thử nghiệm, chạy test và conditions report; app vẫn thường chạy MVC. Giải thích tại sao.

**Bài tập C — realtime dashboard:** server phát tiến độ job 5 giây/lần, browser không gửi messages qua persistent connection. So polling và SSE, tìm điều kiện nào đòi WebSocket.

**Bài tập D — GraphQL:** xác định frontend có thật sự cần projection từ nhiều domains. Nếu có, viết schema, giới hạn query complexity, design field-level auth và contract tests; nếu không, tối ưu REST trước.

**Bài tập E — dependency graph:** dùng `mvn dependency:tree` tìm tuyến đưa Tomcat/Jackson vào runtime. Dùng `mvn dependency:analyze` rồi giải thích vì sao static analysis không chứng minh các libraries này không dùng.

**Bài tập F — security review:** khi thêm một protocol endpoint, liệt kê các checks: authn/authz, TLS, payload limits, CORS/origin nếu browser, rate limiting, connection lifecycle, timeout/cancel, logging và proxy routes.

**Bài tập G — remove safely:** một service chứa WebSocket starter từ prototype cũ. Lập test/metric baseline và kế hoạch gỡ; đừng tuyên bố “không ai dùng” chỉ vì repo không có handler trong một package.

## 23. Câu hỏi ôn tập

**1. Starter là giao thức mới?**  
Không. Starter là dependency bundle; protocol là hợp đồng giao tiếp.

**2. Vì sao Boot 3.3 thường chọn MVC khi có cả web và webflux?**  
Quy tắc application type ưu tiên Spring MVC khi cả hai frameworks có mặt, phù hợp use case MVC dùng WebClient outbound.

**3. RestClient có cần starter-webflux trong MVC?**  
Không. RestClient thuộc Spring Web 6.1, có thể dùng trong app với starter-web.

**4. WebClient có buộc server MVC đổi sang Netty?**  
Không. HTTP client và HTTP server là hai lựa chọn khác nhau.

**5. SSE cần WebSocket starter?**  
Không. SSE dùng HTTP text/event-stream; MVC hỗ trợ SseEmitter.

**6. GraphQL starter có tự cung cấp schema/resolvers đầy đủ?**  
Không. Cần schema, data fetchers và transport/application configuration.

**7. RSocket có giống HTTP/2?**  
Không. RSocket có protocol/interaction semantics riêng.

**8. Thêm một starter có chắc mở thêm public port?**  
Không. Phụ thuộc conditions và explicit configuration.

**9. Maven dependency:tree cho biết gì?**  
Direct/transitive dependencies, scopes và đường kéo library; không tự chứng minh runtime feature đang hoạt động.

**10. Conditions Evaluation Report cho biết gì?**  
Vì sao Boot auto-config conditions match hoặc không match trong context thực.

**11. Không có source import có thể gỡ dependency ngay?**  
Không. Có thể dùng qua reflection, auto-config, SPI hoặc runtime external integration.

**12. Vì sao không override Spring versions ngẫu nhiên?**  
Có nguy cơ phá BOM-tested compatibility và runtime behavior.

**13. Vì sao không bỏ Spring Security/Validation vì artifact size?**  
Bởi các controls có thể là yêu cầu bảo mật/tính đúng; phải cân bằng rủi ro.

**14. Khi nào thêm WebSocket hợp lý?**  
Khi có clients/full-duplex contract, performance/latency requirement và vận hành connection lifecycle hợp lệ.

**15. Khi nào thêm một starter không sai dù artifact lớn hơn?**  
Khi có nhu cầu cụ thể, tests, security/operations owner và lợi ích đã được đánh giá.

**16. Chỉ test HTTP 200 có chứng minh removal an toàn?**  
Không. Còn security, errors, runtime auto config, external consumers và performance.

## 24. Tài liệu chính thức

- [Spring Boot 3.3 – First Application](https://docs.spring.io/spring-boot/3.3/tutorial/first-application/): starter, classpath và auto-configuration.
- [Spring Boot 3.3 – Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): MVC, Servlet stack và embedded server.
- [Spring Boot 3.3 – Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): WebFlux, web application type và trường hợp cùng hai starters.
- [Spring Boot 3.3 – Calling REST Services](https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html): RestClient, WebClient, RestTemplate và auto-config builders.
- [Spring Boot 3.3 – Spring for GraphQL](https://docs.spring.io/spring-boot/3.3/reference/web/spring-graphql.html): GraphQL transport, WebSocket mặc định tắt.
- [Spring Boot 3.3 – RSocket](https://docs.spring.io/spring-boot/3.3/reference/messaging/rsocket.html): các transports và server config.
- [Spring Boot 3.3 – Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): Tomcat/Reactor Netty và thay server.
- [Spring Boot 3.3 – Build Systems](https://docs.spring.io/spring-boot/3.3/reference/using/build-systems.html): starters và dependency management.
- [Spring Boot 3.3 – Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html): conditional configuration, conditions report.
- [Spring Boot 3.3 – Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): exposure và management security.
- [Apache Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/): dependency:tree, dependency:analyze.
- [Gradle – Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): dependencyInsight.
- [Spring Boot Dependency Management](https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html): BOM version alignment.

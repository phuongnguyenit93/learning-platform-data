# Giới hạn đóng gói hoặc triển khai WebFlux theo máy chủ và phiên bản trong Spring Boot

## 1. Mục tiêu: phân biệt “WebFlux chạy trên máy chủ nào” và “đóng gói/triển khai bằng cách nào”

Một nhóm phát triển có ứng dụng Spring WebFlux chạy tốt trên **Reactor Netty** bằng `java -jar`, nhưng môi trường vận hành yêu cầu nộp file `.war` để thả vào một **Tomcat bên ngoài**. Có người lý luận: “WebFlux hỗ trợ Tomcat, vậy chuyển sang WAR rồi deploy lên Tomcat chắc chắn được”. Kết luận này **không đúng với mô hình triển khai Spring Boot 3.3 được hỗ trợ**.

Cần phân biệt bốn câu hỏi độc lập:

1. **Web programming model:** ứng dụng đang dùng Spring MVC/Servlet hay Spring WebFlux/reactive?
2. **HTTP server runtime:** ứng dụng WebFlux chạy trên Reactor Netty, Tomcat, Jetty hay Undertow?
3. **Application packaging:** executable JAR, Docker/OCI image, native executable, hay traditional WAR?
4. **Version contract:** Java/Jakarta Servlet API, Spring Boot/Spring Framework và phiên bản container/Netty có tương thích nhau không?

Kết luận nền tảng của Spring Boot 3.3:

- `spring-boot-starter-webflux` mặc định dùng **embedded Reactor Netty**.
- Có thể **thay embedded server** bằng Tomcat, Jetty hoặc Undertow qua dependencies phù hợp, vẫn dùng WebFlux programming model.
- Spring Boot **không hỗ trợ traditional WAR deployment cho WebFlux applications**, kể cả vì WebFlux framework có servlet adapter và embedded WebFlux có thể chạy trên Tomcat. Muốn một `.war` triển khai theo mô hình `SpringBootServletInitializer` vào external servlet container, đó là hướng đi được tài liệu Boot mô tả cho **Servlet/MVC applications**, không phải một công thức WebFlux WAR.
- **Executable JAR và container image** là đường triển khai thông dụng, được Spring Boot hỗ trợ cho ứng dụng WebFlux.
- Các phiên bản Boot khác nhau có yêu cầu Java/Jakarta và server khác nhau; **không copy cấu hình server của Boot 2.7, 3.3 và 4.x cho nhau mà không kiểm tra**.

Ví dụ và hướng dẫn build ở đây dùng **Spring Boot 3.3.13, Spring Framework 6.1.x, Java 21, Gradle**; Java 17 là mức tối thiểu của nhánh Spring Boot 3.3. Khi đề cập Boot 2.7 hoặc 4.x, chỉ để giúp nhận ra ranh giới tương thích, không coi đó là cấu hình thay thế trực tiếp.

## 2. Bốn tầng cần giữ tách biệt

```text
[Web programming model]
  Spring MVC                        Spring WebFlux
  DispatcherServlet                 HttpHandler / WebHandler
  Servlet handlers                  Reactive Streams / Publisher
           |                                     |
           v                                     v
[HTTP server runtime / embedded adapter]
  Tomcat / Jetty / Undertow          Reactor Netty (default)
                                     Tomcat / Jetty / Undertow
           |                                     |
           v                                     v
[Packaging and lifecycle]
  Executable JAR or traditional WAR  Executable JAR / OCI image / native
  Boot Servlet initializer          Boot starts embedded reactive server
           |                                     |
           v                                     v
[Platform / version]
  JDK, Servlet/Jakarta, HTTP/TLS     JDK, adapter, server, Netty
  server and deployment platform     native transports and dependencies
```

Không được đánh đồng:

- “**Tomcat có hỗ trợ WebFlux**” với “**Boot WebFlux có thể deploy WAR lên Tomcat ngoài**”.
- “Thêm `spring-webflux` để dùng `WebClient`” với “Ứng dụng đã chuyển hẳn sang WebFlux”.
- “Build ra `.war` bằng Gradle” với “Artifact ấy có một **deployment lifecycle được Spring Boot hỗ trợ**”.
- “Một library có tên reactive” với “HTTP runtime thực sự chạy non-blocking từ đầu tới cuối”.
- “Compile được trên Java 21” với “Mọi servlet container cũ sẽ chấp nhận Jakarta API/classpath của Boot 3.3”.

Hãy quyết định **web stack → embedded server → artifact → target runtime/version** theo thứ tự, rồi viết smoke test để chứng minh cả bốn đều đúng.

## 3. Ma trận lựa chọn cho Spring Boot 3.3

| Nhu cầu | Stack/server | Artifact triển khai | Trạng thái/giới hạn |
| --- | --- | --- | --- |
| WebFlux thông thường | WebFlux + embedded Reactor Netty | `bootJar`, OCI image | **Đường mặc định nên dùng** |
| WebFlux cần embedded Tomcat | WebFlux + Tomcat reactive adapter | `bootJar`, OCI image | **Được hỗ trợ**, phải đổi dependencies |
| WebFlux cần embedded Jetty | WebFlux + Jetty reactive adapter | `bootJar`, OCI image | **Được hỗ trợ**, phải kiểm thử server-specific features |
| WebFlux cần embedded Undertow | WebFlux + Undertow adapter | `bootJar`, OCI image | **Được hỗ trợ trên Boot 3.3**, không áp dụng mặc định cho Boot 4.x |
| Boot WebFlux và external Tomcat `.war` | WebFlux + traditional servlet WAR | WAR deploy vào container khác | **Không được Spring Boot hỗ trợ** |
| Spring MVC trên external Tomcat | Servlet/MVC + `SpringBootServletInitializer` | WAR | **Mô hình Boot hỗ trợ** khi đáp ứng version/API |
| WebFlux cần startup nhanh/nhỏ | WebFlux + compatible native image | Native executable/OCI | Có thể dùng AOT; nhiều giới hạn reflection/dynamic config |
| Chỉ cần reactive HTTP client | MVC + `WebClient` | MVC JAR/WAR tùy stack | Không cần chuyển toàn bộ app sang WebFlux |

**Khác biệt giữa “support” và “possible”:** ở mức Spring Framework, có thể tự lắp `HttpHandler` vào một Servlet adapter và tự quản lý lifecycle. Điều đó không khiến Spring Boot tự hỗ trợ đường `.war` truyền thống cho một Boot WebFlux application. Tránh quảng cáo một workaround thủ công thành cam kết sản phẩm.

## 4. Điều Spring Framework hỗ trợ ở tầng HTTP adapter

Spring WebFlux có một abstraction nền tảng:

```java
public interface HttpHandler {
    Mono<Void> handle(ServerHttpRequest request,
                      ServerHttpResponse response);
}
```

Đây là **chữ ký khái niệm** của Spring WebFlux `HttpHandler`, không phải file Java độc lập; các imports nằm trong `org.springframework.http.server.reactive` và Reactor. Các handler/adapter biến HTTP requests của server thành `ServerHttpRequest` và `ServerHttpResponse`.

Một mô hình đơn giản:

```text
HTTP socket
    |
    +--> Reactor Netty server API
    |      -> ReactorHttpHandlerAdapter
    |
    +--> Tomcat Servlet non-blocking I/O
    |      -> Servlet HttpHandler adapter
    |
    +--> Jetty Servlet non-blocking I/O
    |      -> Servlet HttpHandler adapter
    |
    +--> Undertow server API
           -> UndertowHttpHandlerAdapter
                   |
                   v
              HttpHandler
                   |
                   v
            Spring WebFlux WebHandler
                   |
                   v
        HandlerMapping / HandlerAdapter
        WebFilter / codecs / controller
```

Một code `@RestController` WebFlux thường không cần biết server là Reactor Netty hay Jetty. Tuy nhiên behavior của HTTP/2, TLS, connection flow control, WebSocket, compression, thread model, shutdown và request limits **không nhất thiết đồng nhất** vì adapters và server implementation khác nhau.

Spring Framework cung cấp abstraction, còn **Spring Boot auto-configuration** chọn và quản lý **embedded reactive server**. Đó là hai tầng hỗ trợ khác nhau.

## 5. Reactor Netty: server mặc định của `spring-boot-starter-webflux`

Gradle cho một app thuần WebFlux:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

Starter WebFlux mặc định kéo theo `spring-boot-starter-reactor-netty` trong Spring Boot 3.3. Server thường là một instance `NettyWebServer`, do Boot `NettyReactiveWebServerFactory` khởi tạo.

Ưu điểm thực dụng:

- Đường mặc định của Spring Boot nên ít cấu hình hơn khi dùng `WebFlux`.
- Non-blocking I/O dựa trên Reactor Netty và event-loop model.
- Hệ sinh thái Reactor Netty có connection pooling, timeouts, native transport options và metrics khi cấu hình đúng.
- Phù hợp cho nhiều connections đồng thời khi handlers không block event loop và backpressure/limits được thiết kế phù hợp.
- Boot có integration cho graceful shutdown, SSL, HTTP/2, compression và Actuator theo tính năng/version được hỗ trợ.

Nhưng **Netty không phải Servlet container**. Không thể thả một executable Netty JAR vào `webapps/` của external Tomcat như một WAR Servlet app. Netty cũng không tự đảm bảo application non-blocking nếu resolver/service gọi JDBC, `Thread.sleep` hoặc synchronous HTTP client ngay trên event loop.

**Không nhầm runtime của WebClient và runtime của HTTP server:** chúng có thể dùng Reactor Netty nhưng là hai vai trò riêng, có thể được cấu hình dùng chung hoặc tài nguyên khác nhau.

## 6. Tomcat: WebFlux embedded được, nhưng không biến thành Spring MVC

Khi dùng `spring-boot-starter-tomcat` thay Netty cho WebFlux, Spring Boot có một **reactive web application** chạy trên embedded Tomcat với Servlet non-blocking I/O adapter. Đây **không** phải việc chuyển `@GetMapping` WebFlux sang Spring MVC `DispatcherServlet`.

| Khía cạnh | WebFlux + embedded Tomcat | Spring MVC + embedded Tomcat |
| --- | --- | --- |
| HTTP stack | WebFlux | MVC |
| Handler abstraction | `HttpHandler`, WebFlux WebHandler | `DispatcherServlet`, HandlerAdapter |
| Controller return type | `Mono`, `Flux`, POJO | POJO, `ResponseEntity`, có thể hỗ trợ reactive types |
| Servlet API xuất hiện trong business handler? | Không nên dùng trực tiếp | Có thể dùng theo thiết kế MVC |
| Server transport | Tomcat non-blocking Servlet adapter | Tomcat Servlet request handling |
| Artifact | Boot executable JAR/OCI | Executable JAR hoặc MVC WAR |
| Traditional WAR từ Boot | Không hỗ trợ với WebFlux | Hỗ trợ với cấu hình phù hợp |

Vì WebFlux có adapter chạy phía dưới Servlet API, **không nên gắn Servlet `Filter` hoặc xử lý `HttpServletRequest` trực tiếp vào WebFlux handler** như cách viết Spring MVC. Dùng `WebFilter`, `ServerWebExchange`, reactive security và codecs của WebFlux.

Tương tự, `TomcatServletWebServerFactory` dành cho Servlet application; khi chọn WebFlux embedded Tomcat, factory đúng thuộc nhóm **reactive** (`TomcatReactiveWebServerFactory`).

## 7. Jetty: embedded reactive server có thể thay Reactor Netty

Spring Boot 3.3 hỗ trợ `spring-boot-starter-jetty` cho WebFlux khi thay starter Netty. Spring Framework dùng **Servlet non-blocking API** của Jetty qua adapter để phục vụ reactive pipelines.

Vì vậy:

- `Mono`/`Flux` controller không cần viết lại chỉ để đổi Jetty.
- Phải xác nhận phiên bản Jetty tương thích **Spring Boot BOM**, JDK và Jakarta Servlet.
- TLS/ALPN, HTTP/2, WebSocket, timeouts, threading, headers và compression cần test theo Jetty runtime thật.
- Không áp dụng mọi ví dụ Netty như `LoopResources`, `HttpServer.create`, `reactor.netty.*` server metrics hoặc event-loop thread names vào Jetty.
- Không sử dụng `JettyServletWebServerFactory` trong một reactive-specific customizer mà mong callback tác động đúng server.

Một deployment “Jetty chạy được” cần có real HTTP smoke test và kiểm tra artifact dependency graph. Có thể có Netty libraries vẫn ở classpath vì **HTTP client**, nhưng đó không phải bằng chứng embedded **HTTP server** đang là Netty.

## 8. Undertow: nhánh 3.3 hỗ trợ, nhưng đặc điểm adapter khác

Spring Boot 3.3 nêu Undertow như một lựa chọn embedded server cho reactive stack. Khi dùng Spring WebFlux + Undertow, Spring Framework có adapter dùng **Undertow APIs** thay vì dựa vào Servlet adapter giống Tomcat/Jetty.

Điều này dẫn tới:

- Không viết Servlet filter chain chỉ vì Undertow có thể chạy Servlet stack ở bối cảnh khác.
- Undertow-specific config và server metrics không giống Reactor Netty.
- Các HTTP protocol features cần kiểm tra đúng phiên bản và dependency tree.
- Có thể tồn tại các class `undertow-servlet` ở dependencies của một số ứng dụng khác, nhưng WebFlux Undertow adapter không nên bị hiểu thành một `DispatcherServlet`.

**Ranh giới phiên bản:** tài liệu Spring Boot 4.1 không còn liệt kê Undertow trong danh sách embedded server được hỗ trợ theo cách giống Boot 3.3. Khi nâng version, cần kiểm tra tài liệu của **đúng release** thay vì mặc định starter/adapter vẫn được hỗ trợ. Không ép một phiên bản Undertow cũ vào BOM mới để làm app compile rồi gọi đó là supported deployment.

## 9. Sự khác nhau giữa Servlet adapter và WAR truyền thống

Trường hợp gây nhầm lẫn nhiều nhất:

```text
Trường hợp A — ĐƯỢC HỖ TRỢ:
  java -jar webflux-app.jar
        |
        v
  Spring Boot starts embedded Tomcat
        |
        v
  WebFlux HttpHandler via Servlet non-blocking adapter

Trường hợp B — KHÔNG ĐƯỢC BOOT HỖ TRỢ:
  external-tomcat/webapps/webflux-app.war
        |
        v
  external Tomcat owns servlet lifecycle
        |
        v
  Expect SpringBootServletInitializer to bootstrap WebFlux
  as if it were a traditional MVC WAR
```

Tài liệu **Spring Boot 3.3 Traditional Deployment** nói rõ WAR deployment **không được hỗ trợ cho WebFlux applications**. Điều này vẫn đúng ngay cả khi Tomcat là một lựa chọn **embedded** cho WebFlux.

`SpringBootServletInitializer` là bridge cho mô hình traditional Servlet WAR của Spring Boot, không phải mẹo chuyển một `NettyReactiveWebServerFactory` thành một external WAR. Việc thêm plugin Gradle `war` hoặc tạo file `.war` trên disk **không chứng minh** artifact có Boot WebFlux runtime thích hợp trong external container.

Nếu hạ tầng bắt buộc chỉ nhận `.war` và không cho service tự mở HTTP listener, cân nhắc **Spring MVC WAR**, hoặc thay đổi deployment contract để chạy WebFlux executable JAR/container. Không chọn cách manual Servlet bridge trừ khi tổ chức chấp nhận tự xây, duy trì và kiểm thử toàn bộ lifecycle ngoài phạm vi Boot-supported WebFlux WAR.

## 10. Version matrix: Java, Jakarta Servlet và server không bất biến

Tài liệu các bản release khác nhau có ranh giới tương thích:

| Nhánh | Java tối thiểu | Framework | Embedded servlet server nổi bật | Namespace Servlet |
| --- | --- | --- | --- | --- |
| Spring Boot 2.7.18 | Java 8 | Spring Framework 5.3.x | Tomcat 9, Jetty 9.4/10, Undertow 2.x | `javax.servlet.*` |
| Spring Boot 3.3.13 | Java 17 | Spring Framework 6.1.x | Tomcat 10.1, Jetty 12, Undertow 2.3 | `jakarta.servlet.*` |
| Spring Boot 4.1.x | Java 17+ theo system requirements | Spring Framework 7.x | Tomcat 11, Jetty 12.1 trong tài liệu hiện hành | Jakarta Servlet 6.1 |

Đây là **khả năng của Boot/system requirements tương ứng**, không có nghĩa Spring WebFlux external WAR được hỗ trợ ở các phiên bản đó. Với Spring Boot 3.3.13, system requirements nêu **Servlet 6.0** cho các embedded Tomcat 10.1/Jetty 12/Undertow 2.3, cùng khả năng deploy **Servlet applications** trên container Servlet 5.0+ tương thích. Dòng “Servlet 5.0+” **không hủy bỏ cảnh báo “WebFlux WAR not supported”** ở tài liệu traditional deployment.

Với Boot 4.x, danh sách server và starter conventions có thay đổi; ví dụ Undertow không còn là lựa chọn embedded được docs hiện hành liệt kê. Vì thế mỗi nâng cấp major/minor cần kiểm tra: **Boot BOM → Framework → servlet API → container → native/HTTP client library**. Không chỉ sửa mỗi số version `org.springframework.boot`.

## 11. Vì sao `javax.servlet` và `jakarta.servlet` thường làm triển khai thất bại?

Từ Spring Framework 6 / Spring Boot 3, hệ sinh thái Servlet chuyển sang **Jakarta EE**:

```java
// Servlet app cũ, họ Spring Boot 2.x:
import javax.servlet.http.HttpServletRequest;

// Servlet app mới, họ Spring Boot 3.x:
import jakarta.servlet.http.HttpServletRequest;
```

Đây là các package/class **khác nhau**, không tự tương thích nhị phân. WAR theo Boot 3 không thể đơn giản thả vào Tomcat 9 có `javax.servlet` rồi kỳ vọng Servlet API tự chuyển sang Jakarta. Ngược lại, dependency cũ còn tham chiếu `javax.servlet.*` có thể ném `ClassNotFoundException`/`NoClassDefFoundError` khi app dùng Jakarta stack.

Với **WebFlux Reactor Netty**, business handlers không nên phụ thuộc Servlet API; tuy nhiên một số thư viện authentication/filter/observability được kéo vào vẫn có thể mang API cũ, tạo classpath conflicts.

Hãy xác nhận `gradlew dependencies`/`dependencyInsight` trước khi đổi server. Không tự thêm cả `javax.servlet-api` và `jakarta.servlet-api` để “chữa” lỗi nếu chưa rõ library nào thuộc phiên bản nào.

## 12. Dùng Spring Boot BOM thay vì pin lẻ từng library

Một bộ classpath reactive nhất quán có thể gồm:

```text
spring-boot-autoconfigure 3.3.x
spring-webflux 6.1.x
reactor-core 3.6.x
reactor-netty 1.1.x
netty 4.1.x
```

Đây là **các nhánh minh họa**, patch cụ thể do Spring Boot 3.3 BOM chọn. Jetty/Tomcat/Undertow starter cũng phải đi cùng phiên bản do BOM quản lý.

Không nên tùy tiện nâng `reactor-netty-http` hoặc Netty riêng khi starter vẫn là Boot 3.3 chỉ vì advisory mà chưa đánh giá tương thích; cần theo supported patch, dependency management hoặc một override **đã kiểm thử đầy đủ**. Trong trường hợp security fix khẩn cấp, override cần có review và regression tests cho HTTP/2, TLS, WebSocket, SSE, connection pools.

Chốt version kiểm soát bằng lockfile/SBOM và artifact digest ở pipeline. Một app compile thành công không chứng minh runtime không có binary incompatibility.

## 13. Dự án WebFlux có thể chạy: cấu trúc và mục tiêu

Ví dụ đầy đủ này cho phép chọn embedded server bằng Gradle property `-PwebServer=netty|tomcat|jetty|undertow` trong **Spring Boot 3.3.13**. Toàn bộ app dùng cùng một WebFlux controller; thay đổi chỉ ở **server starter dependency**.

```text
build.gradle
src/main/java/com/example/reactivedeploy/
    ReactiveDeployApplication.java
    RuntimeController.java
src/main/resources/application.properties
src/test/java/com/example/reactivedeploy/
    ReactiveServerHttpTest.java
```

Yêu cầu:

- JDK 21 và Gradle Wrapper tương thích Java 21.
- Build dependencies có thể truy cập Maven Central.
- `java -jar` chỉ dùng executable `bootJar` output.
- Không thêm `spring-boot-starter-web` vào runtime classpath của ví dụ này.
- Tests gọi HTTP thật qua `@SpringBootTest(RANDOM_PORT)`.

**Mục tiêu test:** kiểm chứng 2 điều riêng biệt: (a) `ReactiveWebServerApplicationContext` thật sự được tạo và (b) HTTP server thực hiện endpoint qua mạng, không dựa vào tên dependency trong source.

## 14. `build.gradle`: chọn một embedded reactive server

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

def serverStarters = [
        netty: 'spring-boot-starter-reactor-netty',
        tomcat: 'spring-boot-starter-tomcat',
        jetty: 'spring-boot-starter-jetty',
        undertow: 'spring-boot-starter-undertow'
]

def chosenServer = providers.gradleProperty('webServer')
        .getOrElse('netty')

if (!serverStarters.containsKey(chosenServer)) {
    throw new GradleException(
            "webServer must be netty, tomcat, jetty or undertow")
}

dependencies {
    // Bỏ server Netty mặc định để không chọn hai server factories.
    implementation('org.springframework.boot:spring-boot-starter-webflux') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-reactor-netty'
    }

    // Thêm đúng một server starter được chọn.
    implementation "org.springframework.boot:${serverStarters[chosenServer]}"

    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
    systemProperty 'expectedWebServer', chosenServer
}
```

**Cách đọc:**

- Khi không truyền `-PwebServer`, project dùng `netty`.
- Để chọn Tomcat/Jetty/Undertow, ví dụ `./gradlew -PwebServer=jetty test`.
- `exclude` gỡ transitive Netty **server starter** của WebFlux trước khi chọn một server.
- Không dựa vào `server.type=tomcat` hoặc `spring.main.web-application-type` để tự tải Tomcat khi dependencies không có.
- `systemProperty expectedWebServer` chỉ phục vụ assert trong test; đây không phải Spring Boot production property.

**Lưu ý quan trọng về WebClient:** tài liệu Boot 3.3 chỉ ra `spring-boot-starter-reactor-netty` cần cho WebClient khi dùng **Netty connector** mặc định. Sau khi bỏ server Netty starter, phải kiểm tra HTTP client connector mà dự án sử dụng. WebClient là API đa connector, nhưng nếu business code yêu cầu Reactor Netty `HttpClient` hoặc Reactor Netty-specific options, hãy cấu hình client dependency/connector riêng và xác minh không vô tình tạo **hai reactive server factories**. Không “sửa lỗi WebClient” bằng cách thêm lại nguyên server starter rồi bỏ qua server selection.

## 15. `ReactiveDeployApplication.java`

```java
package com.example.reactivedeploy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveDeployApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveDeployApplication.class, args);
    }
}
```

Đây là entrypoint Boot cho mọi lựa chọn embedded server. **Không extends `SpringBootServletInitializer`**, vì mục tiêu của ví dụ là **WebFlux executable deployment**, không phải traditional WAR. Boot auto-configure `ReactiveWebServerApplicationContext` dựa trên classpath/runtime stack.

Không tự đăng ký `DispatcherServlet` hoặc tạo `ServletRegistrationBean` trong project WebFlux chỉ để app được phát hiện. Với WebFlux hãy dùng annotation controllers/functional routes và WebFlux infrastructure.

## 16. `RuntimeController.java`: cùng contract HTTP ở bốn server

```java
package com.example.reactivedeploy;

import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class RuntimeController {

    @GetMapping(path = "/api/ping",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> ping() {
        return Mono.just("reactive-ok");
    }

    @GetMapping(path = "/api/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<String>> events() {
        return Flux.range(1, 3)
                .delayElements(Duration.ofMillis(30))
                .map(n -> ServerSentEvent.<String>builder()
                        .event("tick")
                        .id(Integer.toString(n))
                        .data("tick-" + n)
                        .build());
    }
}
```

`GET /api/ping` trả text `reactive-ok` và hoàn tất. `GET /api/events` gửi ba SSE events, rồi hoàn tất để integration test không giữ stream vô hạn.

- `Mono`/`Flux` là reactive values, **không tự chứng minh** HTTP request đang đi qua non-blocking server nào; cần test context/server thực.
- `ServerSentEvent` là Spring WebFlux encoder contract; server khác nhau vẫn phải trả đúng `text/event-stream`.
- `delayElements(30 ms)` giúp thấy streams theo thời gian; đây không phải timing guarantee cho HTTP test ở môi trường CI.
- Trong production SSE có thể tồn tại lâu; phải thêm cancellation cleanup, heartbeat/backpressure và proxy idle timeout policy.

Cùng controller có thể được dùng cho Netty/Tomcat/Jetty/Undertow trên Boot 3.3 với phù hợp dependencies. Những tính năng khác như WebSocket, TLS và HTTP/2 cần integration tests riêng theo server.

## 17. `application.properties`: cổng và health probes

```properties
# Runtime config: có thể override bằng biến môi trường PORT.
server.port=${PORT:8080}

# Chỉ expose health; management endpoints khác cần policy riêng.
management.endpoints.web.exposure.include=health
management.endpoint.health.probes.enabled=true

# Graceful shutdown cho executable runtime.
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Ở test, chỉ bind local loopback bằng annotation properties. Khi chạy trong Docker/Kubernetes, app cần bind địa chỉ interface container phù hợp (không `127.0.0.1` nếu muốn host/pod bên ngoài truy cập qua published port).

Lưu ý:

- `EXPOSE 8080` trong Dockerfile **không tự thay `server.port`**; phải thống nhất cấu hình và published/container port.
- Readiness/liveness của Actuator chỉ giúp orchestration nếu probes được cấu hình đúng và endpoint thực có trả kết quả phù hợp.
- `server.shutdown=graceful` điều phối ngừng tiếp nhận request/đóng server theo Spring Boot; đối với SSE/WebSocket vô hạn, cần **application-owned session cleanup**, không kỳ vọng stop chờ mãi.
- Nếu quản lý TLS qua ingress, phân biệt server SSL trực tiếp với TLS termination ở proxy.

## 18. `ReactiveServerHttpTest.java`: kiểm tra server thật và endpoint

```java
package com.example.reactivedeploy;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "server.address=127.0.0.1")
class ReactiveServerHttpTest {

    private static final Map<String, String> SERVER_CLASSES = Map.of(
            "netty", "NettyWebServer",
            "tomcat", "TomcatWebServer",
            "jetty", "JettyWebServer",
            "undertow", "UndertowWebServer");

    @LocalServerPort
    int port;

    @Autowired
    ReactiveWebServerApplicationContext context;

    @Test
    void expectedEmbeddedServerWasSelected() {
        String expected = System.getProperty("expectedWebServer");
        assertThat(SERVER_CLASSES).containsKey(expected);
        assertThat(context.getWebServer().getPort()).isEqualTo(port);
        assertThat(context.getWebServer()
                .getClass().getSimpleName())
                .isEqualTo(SERVER_CLASSES.get(expected));
    }

    @Test
    void respondsOverARealHttpSocket() throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + "/api/ping"))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.body()).isEqualTo("reactive-ok");
        assertThat(response.headers().firstValue("content-type")
                .orElse(""))
                .contains("text/plain");
    }

    @Test
    void emitsFiniteServerSentEvents() throws Exception {
        HttpClient client = HttpClient.newHttpClient();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + "/api/events"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(response.headers().firstValue("content-type")
                .orElse(""))
                .contains("text/event-stream");
        assertThat(response.body()).contains(
                "data:tick-1", "data:tick-2", "data:tick-3");
    }
}
```

**Kiểm tra hai tầng:**

- Inject `ReactiveWebServerApplicationContext` thất bại nếu ứng dụng thực tế bị biến thành **Servlet MVC context**. Vì thế test không bị đánh lừa chỉ bởi việc controller có `Mono`.
- `context.getWebServer().getClass().getSimpleName()` xác nhận factory/server được chọn cho mỗi Gradle variant. Map tên lớp là **assert phụ thuộc Spring Boot 3.3 implementation**, phù hợp regression test có chủ đích, không phải public SPI ổn định mãi qua các major versions.
- `HttpClient` JDK 21 gửi HTTP thật tới random port, không dùng mock environment.
- SSE test kiểm tra HTTP content type/serialization, không chỉ unit-test `Flux` logic.
- Test **không** chứng minh TLS/HTTP2/WebSocket hoặc proxy routing; bổ sung tests khi các tính năng đó được dùng.

Code test có import `java.net.http.*` từ JDK 11+, nên không cần thêm WebClient connector vào test classpath để gọi endpoint. Nó tránh nhầm giữa **Netty-backed WebClient** và việc kiểm tra **HTTP server lựa chọn**.

## 19. Chạy ma trận server bằng Gradle và đọc kết quả đúng

Chạy các lựa chọn **từng lần**, vì mỗi Gradle invocation resolve một dependency graph:

```bash
./gradlew clean test -PwebServer=netty
./gradlew clean test -PwebServer=tomcat
./gradlew clean test -PwebServer=jetty
./gradlew clean test -PwebServer=undertow
```

Dấu `-P` là Gradle project property, không phải JVM option. Nếu CI chạy các variants song song, dùng build workspaces độc lập hoặc điều phối task outputs, không để nhiều builds cùng `clean`/`build` vào một directory.

Kết quả mong đợi **khi dependencies/runtime tương thích và environment có network loopback** là các tests PASS. Không in một stdout cố định vì Gradle logs, ports và server startup messages thay đổi.

Để build JAR:

```bash
./gradlew clean bootJar -PwebServer=netty
```

Gradle tạo executable artifact trong `build/libs/`; tên mặc định theo project/Gradle settings. **Không copy một tên JAR giả định** khi project có `archiveFileName`, classifier hoặc nhiều artifacts; dùng đường dẫn thực của `bootJar`.

Để chạy Jetty embedded:

```bash
./gradlew clean bootRun -PwebServer=jetty
```

Sau đó:

```bash
curl -i http://127.0.0.1:8080/api/ping
curl -N http://127.0.0.1:8080/api/events
```

Kết quả `/api/ping` body là:

```text
reactive-ok
```

SSE có các dòng `id:`, `event:`, `data:`; thứ tự payload theo `Flux.range` là `tick-1`, `tick-2`, `tick-3`, nhưng format xuống dòng/header timing tùy HTTP client/server. Không assert Netty/Jetty phải có cùng startup log line hoặc cùng thread names.

## 20. Cẩn thận với dependency graph: code compile không xác định server

Kiểm tra dependencies khi đổi server:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-boot-starter-reactor-netty \
  --configuration runtimeClasspath
```

Chạy thêm với `-PwebServer=tomcat` hoặc `jetty` để xem dependency graph thực; không chỉ mở `build.gradle` rồi kết luận. Khi có nhiều starters ở classpath, kết quả auto-config và precedence có thể không khớp ý định.

Các câu hỏi review:

1. Có đang kéo cả `spring-boot-starter-web` và `spring-boot-starter-webflux` vào runtime?
2. Có `spring-boot-starter-reactor-netty` từ một dependency khác ngoài WebFlux không?
3. Có nhiều `ReactiveWebServerFactory` beans không?
4. `spring.main.web-application-type` có bị override bởi profile/environment không?
5. Có auto-configuration exclusion hoặc custom server factory không?
6. Có custom `WebClient` connector phụ thuộc Reactor Netty sau khi đổi server không?
7. Version của Netty/Tomcat/Jetty/Undertow có được BOM quản lý đồng nhất không?

**Không kết luận từ một starter name.** Smoke test cần xác nhận actual `ReactiveWebServerApplicationContext` và server class.

## 21. Bẫy `spring-boot-starter-web` + `spring-boot-starter-webflux`

Ví dụ dependency dễ gây nhầm:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

Khi cả MVC và WebFlux starters ở runtime classpath, Spring Boot **thường ưu tiên Servlet web application type**. Một controller có `Mono<String>` không đủ để chứng minh ứng dụng đang chạy WebFlux; Spring MVC cũng có thể hỗ trợ reactive return types.

Nếu dự án chỉ muốn dùng `WebClient` trong một MVC service, việc WebFlux libraries ở classpath **không nhất thiết là lỗi**, vì `WebClient` có giá trị trong MVC apps. Nhưng nếu bạn cần HTTP server thực sự là WebFlux, nên loại `spring-boot-starter-web` khi không cần.

Có thể ép:

```properties
spring.main.web-application-type=reactive
```

khi có lý do chủ đích để dùng reactive web stack dù các thư viện Servlet vẫn tồn tại. Tuy nhiên property này **không xóa blocking Servlet filters, MVC-only auto-configurations hay các dependency conflicts**, cũng không làm WebFlux WAR thành một mô hình Boot-supported. Ưu tiên sửa dependency graph sạch thay vì dựa lâu dài vào override này.

## 22. Maven: cùng nguyên tắc exclude và thay server starter

Một `pom.xml` dùng Boot parent/BOM phù hợp và WebFlux + embedded Jetty có thể khai:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
        <exclusions>
            <exclusion>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-starter-reactor-netty</artifactId>
            </exclusion>
        </exclusions>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jetty</artifactId>
    </dependency>
</dependencies>
```

Đây là **một đoạn dependencies tích hợp**, không phải POM độc lập. Cần Maven coordinates, `spring-boot-starter-parent` hoặc import BOM, Java/toolchain và Maven plugin đúng project.

Tương tự:

- Tomcat: `spring-boot-starter-tomcat`.
- Undertow trên Boot 3.3: `spring-boot-starter-undertow`.
- Reactor Netty mặc định: bỏ phần exclusions/Jetty starter và dùng WebFlux starter bình thường.

Đừng tạo một POM với **4 server starters cùng lúc** và giả định Spring Boot tự chọn theo `application.properties`. Chọn một server hoặc có explicit conditional build profile/module và smoke test đi kèm.

## 23. Packaging executable JAR: cách Boot WebFlux được triển khai thông dụng

Với Spring Boot Gradle plugin:

```bash
./gradlew clean bootJar
```

Executable JAR có cấu trúc khái niệm:

```text
META-INF/
BOOT-INF/
  classes/
    com/example/reactivedeploy/...
    application.properties
  lib/
    spring-webflux-...
    reactor-core-...
    <selected server dependencies>
org/springframework/boot/loader/...
```

Tên classes/JAR dependencies là minh họa; artifact thực có Boot loader, nested JARs và metadata theo Gradle plugin. Có thể kiểm tra:

```bash
jar tf build/libs/<actual-jar-name>.jar
```

Dòng `<actual-jar-name>` là ký hiệu cần thay bằng tên file đã sinh, không phải shell command chạy nguyên văn.

Để chạy:

```bash
java -jar build/libs/<actual-jar-name>.jar
```

`java -jar` kích hoạt Spring Boot launcher load nested dependencies; không giống `java -cp ordinary.jar com.example.Main` cho một JAR thông thường. Nếu bật Gradle plain `jar` task, một **plain jar không gồm runtime dependencies** có thể không chạy độc lập; phân biệt `jar`, `bootJar` và `bootRun`.

Để kiểm tra selected server, xem dependency graph **và** HTTP runtime. Đừng giả định một `jar tf` có `reactor-netty` nghĩa HTTP server chắc chắn Netty; có thể library chỉ phục vụ outbound client.

## 24. Vì sao `jar` và `war` không chỉ khác đuôi tệp?

| Thuộc tính | Executable Boot JAR | Traditional external WAR |
| --- | --- | --- |
| Server lifecycle | Application tự khởi động embedded server | External servlet container sở hữu lifecycle |
| Launcher | Boot nested-jar launcher | Container deploy mechanism |
| Deployment | `java -jar`, Docker, orchestrator | Copy WAR đến container/webapps hoặc deploy API |
| App context startup | Boot `main`/auto-configuration | Servlet initialization bootstrap |
| Port/config | Embedded server config của app | External server connector config |
| Reactive WebFlux Boot 3.3 | **Được hỗ trợ** | **Không được hỗ trợ** |
| MVC Boot 3.3 | Được hỗ trợ | Được hỗ trợ khi cấu hình đúng |

Với Servlet/MVC WAR, `SpringBootServletInitializer`, `war` plugin và `providedRuntime`/`provided` scope có ý nghĩa. Đem nguyên hướng dẫn này áp dụng cho WebFlux có thể tạo artifact nhưng không phải **supported path**.

Nếu tổ chức yêu cầu “WAR vì server runtime chung”, có thể thảo luận đổi deployment nền tảng sang **container image chạy executable JAR** nhưng vẫn chuẩn hóa quản lý ports, TLS, logs, deployment metadata, metrics, graceful shutdown và autoscaling ở orchestration layer.

## 25. Framework-level `ServletHttpHandlerAdapter` không tự trở thành Boot WAR

Spring WebFlux `HttpHandler` có adapter cho Servlet non-blocking I/O. Tầng framework cho phép một ứng dụng tự đăng ký adapter vào một Servlet container trong cách tích hợp tùy biến.

```text
Custom external Servlet container integration
    |
    v
Servlet registration + async/non-blocking support
    |
    v
ServletHttpHandlerAdapter(HttpHandler)
    |
    v
WebFlux HttpHandler / WebHandler
```

Nhưng khi tự lắp như vậy, chính ứng dụng phải giải quyết:

- Tạo và đóng application context.
- Servlet initialization và async/non-blocking settings.
- Classloader boundaries, Jakarta Servlet version.
- Dependency scope, resource duplication, logging lifecycle.
- HTTP session/security/filter integration.
- Graceful shutdown, monitoring, startup failures.
- WebSocket/SSE support trên từng container.
- Kiểm thử qua target server/version thực.

Đây là công việc **framework integration tùy biến**, khác hẳn `SpringBootServletInitializer` auto startup của Boot MVC. Spring Boot 3.3 vẫn ghi rõ **WebFlux WAR không được hỗ trợ**; không dùng framework adapter để sửa câu đó thành “Boot WebFlux WAR được hỗ trợ nếu Tomcat đủ mới”.

## 26. Trường hợp nào nên chọn MVC WAR thay vì WebFlux?

Nếu môi trường deployment thực sự chỉ cung cấp:

```text
Shared external Tomcat 10.1
  -> deploy .war only
  -> application must not own listener
  -> standard Servlet filters and container session
```

và tổ chức không chấp nhận custom integration framework-level, lựa chọn phù hợp thường là **Spring MVC WAR**. Cần đánh giá blocking dependency, security filters, servlet requirements và test trên container version. Không tự chọn WebFlux vì nghĩ “reactive luôn nhanh hơn”.

Có thể vẫn dùng **`WebClient`** trong MVC app để gọi dịch vụ HTTP khác theo mô hình reactive client; nhưng toàn bộ web server không tự thành WebFlux. Nếu nghiệp vụ thực sự cần WebFlux non-blocking server, hãy đề xuất **executable JAR/OCI runtime riêng** thay vì ép vào WAR.

Chọn giữa WebFlux và MVC theo concurrency model, workloads, team, libraries và đo lường; chọn artifact theo deployment platform. Hai quyết định này liên quan nhưng không phải cùng một quyết định.

## 27. OCI container cho WebFlux: executable JAR bên trong image

WebFlux không cần WAR khi chạy trong Docker/Kubernetes. Bạn có thể đóng gói executable JAR và chạy một Java process:

```dockerfile
FROM eclipse-temurin:21-jre

WORKDIR /app
COPY build/libs/reactivedeploy-0.0.1-SNAPSHOT.jar /app/app.jar

USER 10001:10001
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Đây là **Dockerfile mẫu tích hợp**, tên JAR phải khớp `bootJar` output thực. Trong production nên pin base image theo digest, dùng image được cập nhật bảo mật và tránh filesystem cần quyền ghi đối với process non-root. Chọn `linux/amd64`/`linux/arm64` theo runtime, kiểm tra JDK/native dependencies tương ứng.

Trước khi build image, tạo JAR cho **một** server variant:

```bash
./gradlew clean bootJar -PwebServer=netty
docker build -t webflux-demo:local .
docker run --rm -p 8080:8080 webflux-demo:local
```

Sau đó:

```bash
curl -i http://127.0.0.1:8080/api/ping
```

`EXPOSE` chỉ ghi metadata, còn `-p` publish port khi chạy container. Cấu hình `server.port=${PORT:8080}` phải nhất quán với containerPort, service/ingress. Không bind server chỉ ở `127.0.0.1` **bên trong container** nếu cần traffic từ host/pod network; loopback của container không phải host loopback.

## 28. Spring Boot buildpacks: `bootBuildImage` cũng tạo runtime độc lập

Spring Boot Gradle plugin hỗ trợ tạo OCI images bằng buildpacks khi môi trường/container engine phù hợp:

```bash
./gradlew bootBuildImage --imageName=webflux-demo:local
```

Lệnh ở đây là workflow minh họa; cần Docker daemon/buildpack environment, registry access và buildpack support tương ứng. Buildpacks tạo image chạy ứng dụng Boot, **không** biến WebFlux thành WAR để copy vào Tomcat ngoài.

Nếu dùng runtime images được sinh từ buildpacks, vẫn phải kiểm tra:

- JDK/JRE version thực.
- Arch/OS/libc và Netty native transports tương ứng.
- HTTP server starter selected trong artifact.
- Container user/permissions, layers, SBOM và vulnerabilities.
- Startup probes, memory limits và graceful termination.

Đừng chạy `bootBuildImage` và coi build success là đủ: phải smoke test HTTP request, health, SSE/WebSocket nếu có và shutdown lifecycle của image thực.

## 29. GraalVM native image: một hướng triển khai, không phải WAR

Spring Boot 3.3 hỗ trợ Spring AOT và GraalVM native images. Native executable thường có startup nhanh và memory footprint nhỏ hơn JVM equivalent ở nhiều workloads, nhưng có các giới hạn **closed-world analysis**:

- Bean graph và một số dynamic configuration phải được xác định ở build-time.
- Reflection, resources, dynamic proxies và serialization có thể cần hints.
- Không có đầy đủ mọi khả năng runtime classpath/lazy class loading như JVM.
- Không phải library thứ ba nào cũng tương thích native image.
- Native binary là artifact phụ thuộc OS/arch, cần build tương ứng target platform.
- Container TLS, DNS và Netty native transport dependencies cần kiểm tra trong bản native thực tế.

Khi dùng Gradle plugin native:

```groovy
plugins {
    id 'org.graalvm.buildtools.native' version '0.10.6'
}
```

Đây là **phần bổ sung** cho build.gradle project có Spring Boot plugin, không phải file build.gradle độc lập. Cần GraalVM native-image toolchain đã được hỗ trợ và cấu hình. Build:

```bash
./gradlew nativeCompile
```

Native image output nằm trong `build/native/nativeCompile/` theo build plugin và settings thực. Hãy thực hiện smoke/integration tests trên **binary được deploy**, không chỉ trên JVM `bootRun`. AOT may change behavior of conditional beans/configuration; không dùng kết quả JVM test làm bằng chứng hoàn chỉnh cho native build.

Native image hỗ trợ WebFlux theo những dependency/configuration tương thích, **không làm thay đổi giới hạn traditional WebFlux WAR**.

## 30. Platform deployment: cổng, readiness, liveness và shutdown

Trong Kubernetes hoặc nền tảng tương tự, executable WebFlux service thường có:

```text
OCI image
  -> one Java/native process
  -> embedded HTTP server listening :8080
  -> Service / ingress routes requests
  -> readiness determines new traffic eligibility
  -> graceful shutdown/draining on termination
```

Ví dụ **một phần** manifest container/probes:

```yaml
containers:
  - name: webflux-app
    image: registry.example.test/webflux-demo:release
    ports:
      - name: http
        containerPort: 8080
    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: http
      initialDelaySeconds: 2
      periodSeconds: 5
    livenessProbe:
      httpGet:
        path: /actuator/health/liveness
        port: http
      initialDelaySeconds: 5
      periodSeconds: 10
    terminationMessagePolicy: File
```

Đây là **đoạn manifest tích hợp**, không phải Deployment YAML đầy đủ. Cần cấu hình Actuator health probes thực sự được expose, TLS/port mapping và `readiness` policy theo ứng dụng. `registry.example.test` là tên giả; phải dùng image/version thật khi triển khai.

**Không đưa** một endpoint business public không cần auth vào production chỉ để làm readiness. Có thể dùng Actuator health groups được giới hạn theo network, và quyền truy cập riêng cho monitoring.

Graceful shutdown được hỗ trợ ở embedded servers theo Boot, nhưng semantics với SSE, WebSocket hoặc long-lived connections tùy server/proxy. Không kỳ vọng tất cả streams vô hạn tự hoàn tất trước `terminationGracePeriodSeconds`; ứng dụng có thể cần chủ động đóng subscriptions và giảm tài nguyên.

## 31. HTTP/2, TLS/ALPN và compression không giống nhau ở mọi server

Khi thay Netty bằng Jetty/Tomcat/Undertow, controller vẫn có thể trả `Mono<String>`, nhưng các khả năng HTTP server phụ thuộc implementation:

| Tính năng | Điều cần kiểm tra |
| --- | --- |
| HTTP/1.1 | Routing, body/headers, keep-alive, timeouts |
| HTTP/2 TLS (`h2`) | TLS/ALPN, phiên bản server, JDK/provider/native libs |
| HTTP/2 cleartext (`h2c`) | Tính năng thực sự được enable và proxy hỗ trợ |
| HTTPS | Keystore/certificates, trust chain, SNI, cipher policy |
| Compression | `server.compression.*`, proxy buffering và SSE |
| SSE | Flush timing, async lifecycle, proxy idle timeout |
| WebSocket | Upgrade handshake, auth, ping/pong, close handling |
| Large uploads | Max body/multipart limits, backpressure, buffer size |
| Graceful shutdown | In-flight streams, server shutdown policy |
| Metrics | Tên metric và adapter-specific labels |

Ví dụ:

```properties
server.http2.enabled=true
server.compression.enabled=true
```

Các properties có thể bật chức năng **khi HTTP server hỗ trợ và prerequisites thỏa**, chứ không chứng minh mọi server/proxy negotiation HTTP2 giống nhau. Cần `curl --http2`/tool HTTP2 thích hợp để kiểm tra negotiated protocol, không chỉ xem startup log.

Tương tự, không suy rằng một Reactor Netty-specific `HttpServer` customizer sẽ ảnh hưởng Tomcat/Jetty. Dùng `WebServerFactoryCustomizer` cho đúng **reactive factory type** hoặc server-specific API.

## 32. Native Netty transport và phụ thuộc hệ điều hành

Reactor Netty có các lựa chọn I/O transport (NIO, epoll trên Linux, kqueue trên macOS/BSD khi phù hợp). Các native transports hoặc TLS provider như Netty tcnative có thể tăng hiệu quả trong một số môi trường, nhưng phụ thuộc platform/architecture và phiên bản.

Đừng viết deployment checklist kiểu “mọi Linux Netty đều bắt buộc epoll” hoặc “không có native library là startup chắc chắn fail”. Reactor Netty có thể dùng Java NIO khi native transport không được chọn/không khả dụng, tùy config/dependency/runtime.

Khi chuyển image từ x86_64 sang ARM64 hoặc từ glibc sang musl, hãy kiểm thử:

- Native library classifier/availability.
- TLS/ALPN negotiation và supported ciphers.
- DNS resolver behavior.
- JVM architecture and JDK vendor.
- Container/seccomp permissions.
- HTTP/2/WebSocket/SSE behavior dưới load thực.

Một binary native image cũng phải tương thích đúng OS/arch/libc. **JAR đa nền tảng hơn native binary**, nhưng các native dependencies bên trong vẫn có thể ràng buộc nền tảng.

## 33. HTTP client không phải HTTP server: tránh test nhầm `WebClient`

Trong WebFlux:

```text
Spring WebFlux HTTP server:
  Reactor Netty / Tomcat / Jetty / Undertow

Outbound WebClient:
  ClientHttpConnector
  Reactor Netty HttpClient / Jetty client / JDK client / another supported adapter
```

Hai vai trò có thể dùng khác backend. Bỏ `spring-boot-starter-reactor-netty` để thay server có thể ảnh hưởng **default WebClient connector** của ứng dụng. Nhưng giữ Netty **client libraries** không tự chứng minh server vẫn Netty.

Nếu một module có `WebClient`, cần tách tests:

1. **Server test:** `ReactiveWebServerApplicationContext` và HTTP socket thật cho biết embedded server nào đang chạy.
2. **Client test:** gọi mock upstream/server đã quản lý, xác nhận TLS, timeouts, pool, backpressure và resource shutdown của connector.
3. **End-to-end test:** kiểm tra cả hai khi `WebClient` gọi downstream service trong real request.

Không tự đóng global HTTP client connection provider hoặc Reactor schedulers mỗi khi một HTTP request hoàn tất. Điều này có thể gây lỗi khó phát hiện, nhất là khi client và server chia sẻ resources theo default Netty setup.

## 34. Thread model và blocking code vẫn là giới hạn dù đổi server

WebFlux là programming model dựa trên Reactive Streams; lợi ích scalability phụ thuộc việc các bước I/O/CPU được xử lý phù hợp. Đổi Reactor Netty sang Tomcat không biến synchronous JDBC hoặc `Thread.sleep` thành non-blocking.

Anti-pattern:

```java
@GetMapping("/api/slow")
public Mono<String> slow() {
    return Mono.fromSupplier(() -> legacyBlockingSdk.fetch());
}
```

Đây là **đoạn minh họa tích hợp**, `legacyBlockingSdk` là SDK giả định; không phải source độc lập. `Mono.fromSupplier` lazy nhưng không tự di chuyển blocking work sang scheduler.

Khi buộc dùng SDK đồng bộ:

```java
return Mono.fromCallable(() -> legacyBlockingSdk.fetch())
        .subscribeOn(Schedulers.boundedElastic());
```

Đây cũng là snippet tích hợp, cần Reactor `Schedulers`, bean SDK, timeout/concurrency limits. `boundedElastic()` có giới hạn threads/queue, không chữa backend chậm hay Hikari connection pool bị cạn.

Trên Tomcat/Jetty non-blocking adapter, blocking callbacks vẫn có thể giữ worker hoặc ảnh hưởng I/O progression. Trên Reactor Netty, blocking event loop có thể làm nhiều connections chậm. **Không coi đổi HTTP server là giải pháp cho lỗi blocking trong business pipeline.**

## 35. Các dạng lỗi startup khi đổi WebFlux server

| Hiện tượng | Nguyên nhân có thể | Bước kiểm chứng |
| --- | --- | --- |
| `No qualifying bean of type ReactiveWebServerFactory` | Không có embedded reactive server starter thích hợp | Runtime dependency tree, Boot autoconfiguration |
| MVC `ServletWebServerApplicationContext` thay vì reactive | `spring-boot-starter-web` xuất hiện hoặc web type override | Check classpath, `spring.main.web-application-type` |
| `ClassNotFoundException jakarta.servlet...` | Servlet API/server/library versions lệch | Boot BOM, Tomcat/Jetty versions, excludes |
| `NoClassDefFoundError javax.servlet...` | Library Boot 2.x/Java EE cũ còn trong Boot 3.x | Upgrade dependency sang Jakarta |
| Startup hai server factory beans/conflict | Cả Netty và Tomcat/Jetty server starters bị kéo vào | dependencyInsight và factory beans |
| Netty-specific customizer không có tác dụng | App đã đổi sang Jetty/Tomcat | Dùng đúng reactive server factory |
| Endpoint 404 sau chuyển server | Path/context/base-path/filter behavior khác | Real HTTP test, WebFlux route mapping |
| HTTP client outbound lỗi sau exclude Netty | WebClient connector/dependency bị ảnh hưởng | Config ClientHttpConnector, test outbound riêng |
| WAR artifact build được nhưng deploy lỗi | Boot WebFlux WAR unsupported | Chọn JAR/OCI hoặc MVC WAR |
| `UnsupportedClassVersionError` | JDK runtime thấp hơn compile target | Java/toolchain version |
| `NoSuchMethodError` của Netty/Reactor | Binary dependency version mismatch | BOM, dependency tree, locks |
| TLS/HTTP2 fail khi đổi server | ALPN/native/dependency/config khác | Server-specific HTTP2/TLS integration tests |
| SSE bị buffer/timeout | Server/proxy flush/idle behavior khác | Streaming test qua ingress |
| WebSocket handshake error | Upgrade/proxy/server feature mismatch | WebSocket test và headers |
| Native image fail reflection/config | Missing reachability hints/AOT limits | Native tests/hints, supported dependencies |

**Không chữa bằng cách thêm cả 4 HTTP server starters**. Chọn một factory đúng cho build/deployment và xác minh nó bằng test.

## 36. Khi nâng từ Boot 2.7 sang 3.3 cần xét những gì?

Một dự án Boot 2.7 có thể từng chạy:

```text
Java 8 / Spring Framework 5.3
Tomcat 9 / Jetty 9/10 / Undertow 2.x
javax.servlet.* for Servlet components
Reactor/Netty versions managed by Boot 2.7
```

Khi lên Boot 3.3:

```text
Java 17+ / Spring Framework 6.1
Tomcat 10.1 / Jetty 12 / Undertow 2.3 in embedded stack
jakarta.servlet.* for Servlet-related dependencies
Reactor Core 3.6.x / Reactor Netty 1.1.x via BOM
```

Đó là **migrating framework + runtime**, không chỉ đổi một version property:

- Rà soát Jakarta migration cho security/filter/session libraries.
- Đổi Spring Security configurations/API tương thích.
- Kiểm tra Reactor operators/backpressure behavior và Netty connection settings.
- So lại codec defaults, Jackson versions, problem details, error handling.
- Chạy real HTTP/SSE/WebSocket tests theo server.
- Nếu có custom `HttpHandler` hoặc low-level server adapters, kiểm tra API/SPI thay đổi.
- Đảm bảo JDK/toolchain cùng version ở build, test và production.
- **Không suy** Servlet container requirement của Boot 3 có nghĩa WebFlux WAR được hỗ trợ.

Đặc biệt, nếu phải giữ external Tomcat 9 cũ, không thể dùng một Boot 3.x Servlet WAR thông thường dựa trên Jakarta Servlet API và mong chạy trên Tomcat 9. Đối với WebFlux, đường hợp lý vẫn là executable server chạy riêng.

## 37. Khi nâng Boot 3.3 sang nhánh 4.x

Spring Boot 4.x có thay đổi phiên bản Spring Framework, các starter modules, yêu cầu server và mức Java/Servlet API theo release. Theo system requirements của **Boot 4.1**, embedded Servlet server được nêu là **Tomcat 11 và Jetty 12.1**, khác Boot 3.3 (**Tomcat 10.1, Jetty 12, Undertow 2.3**).

Quy trình nâng cấp:

1. Pin chính xác Boot release target, xem **System Requirements** của release đó.
2. Xác định server starter có còn tồn tại/được hỗ trợ không; không giả định Undertow tiếp tục được liệt kê.
3. Xác nhận Jakarta Servlet version, Java version, Gradle/Maven compatibility.
4. Đọc release notes/migration guide cho Boot/Framework/Netty/Reactor.
5. Tạo dependency graph và SBOM sau upgrade.
6. Build executable JAR/native image theo release mới.
7. Chạy server selection test và HTTP protocol regression suite.
8. Đo latency, RSS, CPU, GC, connection pools, shutdown trước/sau.

Đừng copy `Gradle plugin version '3.3.13'` hay `spring-boot-starter-undertow` trong ví dụ sang 4.1 rồi giả định mọi build variant vẫn thành công. **Mọi khẳng định hỗ trợ phải gắn với phiên bản đang vận hành**.

## 38. CI compatibility matrix: kiểm tra điều gì trước khi phát hành?

Một pipeline chất lượng nên xác minh những ô sau:

| Trục | Biến thể kiểm tra | Test bắt buộc |
| --- | --- | --- |
| Boot version | Release đang dùng, bản target upgrade | Build + dependency tree + smoke test |
| Java runtime | JDK được hỗ trợ theo Boot | Compile target, startup, runtime tests |
| Server | Netty/Tomcat/Jetty/Undertow (theo release) | Reactive context + server class + HTTP request |
| Packaging | Boot JAR, OCI, native nếu được chọn | Artifact chạy được và phản hồi |
| HTTP protocol | HTTP1, HTTP2 khi dùng | Negotiated protocol/TLS |
| Streaming | SSE, WebSocket nếu dùng | Events, cancellation, proxy, idle timeout |
| Security | Auth/CSRF/CORS/headers | Integration tests theo stack |
| Shutdown | SIGTERM/drain | In-flight cleanup, readiness |
| Resources | Memory/CPU limits | Load tests, error rates, p99, GC |
| Upgrade | Old vs new | Contract regression, rollbacks |

Không cần chạy full cross-product vô hạn. Chọn những server/artifacts thực sự được production dùng; thêm một smoke matrix tối thiểu để bảo vệ khả năng đổi server mà docs cho phép.

Để test một external servlet container, nếu doanh nghiệp vẫn có MVC WAR, cần CI riêng deploy WAR lên **đúng container version**. Không dùng “Netty bootJar test PASS” để suy rằng “external Tomcat WAR test PASS”.

## 39. Tình huống ra quyết định: chọn cách triển khai nào?

**Tình huống A — Cloud/Kubernetes, không bị ràng buộc container bên ngoài**

Chọn WebFlux + Reactor Netty mặc định, Boot executable JAR/OCI. Cấu hình health, metrics, TLS gateway, backpressure, rate limits và shutdown. Chỉ đổi server nếu có nguyên nhân cụ thể (policy/security/feature/compatibility).

**Tình huống B — Doanh nghiệp chuẩn hóa embedded Tomcat**

Có thể dùng WebFlux + embedded Tomcat trên Boot 3.3, đổi starter, vẫn deploy JAR/OCI. Chạy tests để đảm bảo context reactive và HTTP behavior chính xác. Đừng đổi thành external WAR chỉ vì tên server là Tomcat.

**Tình huống C — Shared external Tomcat buộc nhận `.war`**

Spring Boot WebFlux WAR **không được hỗ trợ**. Lựa chọn có căn cứ là Spring MVC WAR theo supported path, hoặc xin runtime độc lập để deploy WebFlux executable JAR. Không quảng bá một custom Servlet HttpHandler adapter là feature Boot sẵn có.

**Tình huống D — Bắt buộc Jetty trong production**

Dùng Jetty starter đúng Boot release, bỏ Netty server starter, giữ WebFlux controllers. Kiểm tra Jetty TLS/HTTP2/WebSocket/proxy behavior và client connector, không chỉ đổi Gradle dependency.

**Tình huống E — Runtime nâng sang Boot 4.1**

Kiểm tra danh sách HTTP servers được hỗ trợ từ docs 4.1. Nếu đang dùng Undertow trên Boot3.3, phải có kế hoạch chuyển server hoặc phương án được hỗ trợ, không tự override library versions rồi chỉ nhìn compile result.

**Tình huống F — Serverless/scale-to-zero**

Cân nhắc native image/short startup nếu workload phù hợp, nhưng phải kiểm tra AOT/third-party support, cold-start, probes và timeout behavior. WebFlux không tự xóa platform request timeout hoặc connection lifetime caps.

## 40. Một chương trình Java 17 nhỏ để phân biệt tên artifact và runtime

Chương trình dưới đây **không phải Spring Boot** và không kiểm tra server thực; nó minh họa lý do không thể suy ra deployment contract từ một tên artifact. Chỉ dùng để củng cố mô hình tư duy.

**`PackagingDecisionDemo.java`:**

```java
public class PackagingDecisionDemo {

    static String supportedPath(String stack, String artifact) {
        if ("webflux".equals(stack) && "war".equals(artifact)) {
            return "unsupported Boot WebFlux WAR";
        }
        if ("webflux".equals(stack) && "jar".equals(artifact)) {
            return "supported executable WebFlux";
        }
        if ("mvc".equals(stack) && "war".equals(artifact)) {
            return "supported MVC WAR with servlet setup";
        }
        return "check runtime and Boot version";
    }

    public static void main(String[] args) {
        System.out.println(supportedPath("webflux", "jar"));
        System.out.println(supportedPath("webflux", "war"));
        System.out.println(supportedPath("mvc", "war"));
    }
}
```

Chạy:

```bash
javac PackagingDecisionDemo.java
java PackagingDecisionDemo
```

**Stdout chính xác:**

```text
supported executable WebFlux
unsupported Boot WebFlux WAR
supported MVC WAR with servlet setup
```

Đây là bảng quyết định mã hóa ba trường hợp **của Spring Boot 3.3** để dễ nhớ, không phải runtime compatibility checker. Với Boot version, server setup, native image và deployment platform khác, cần đánh giá theo docs và actual integration tests.

## 41. Anti-pattern thường gặp cần tránh

1. **Thấy WebFlux chạy được trên Tomcat, suy ra external WAR được Boot hỗ trợ.** Sai: embedded adapter khác traditional WAR deployment.
2. **Chỉ đổi phần mở rộng `.jar` thành `.war`.** Không thay đổi launcher/lifecycle/dependencies đúng chuẩn.
3. **Thêm `SpringBootServletInitializer` vào WebFlux rồi chờ tự deploy.** Không biến đường WAR unsupported thành supported.
4. **Thêm `spring-boot-starter-web` để “dùng Tomcat WebFlux”.** Có thể chuyển auto-detected stack sang MVC.
5. **Đổi bằng `spring.main.web-application-type=reactive` rồi bỏ qua dependency conflicts.** Override type không xóa incompatibility.
6. **Giữ hai server starters, nghĩ property sẽ chọn một.** Cần kiểm tra actual reactive factory.
7. **Copy Netty `HttpServer`/`LoopResources` customizer vào Jetty build.** Sai API tầng HTTP server.
8. **Cho rằng WebClient không dùng được nếu server không là Netty.** Client và server connectors riêng; phải cấu hình/test client đúng.
9. **Cho rằng server non-blocking làm JDBC non-blocking.** Blocking business I/O vẫn phải quản lý.
10. **Dùng Tomcat 9 với Boot 3.x Jakarta Servlet application.** Không tương thích servlet namespace/API.
11. **Dùng Undertow starter của Boot3.3 trên Boot4.x mà không kiểm tra support.** Nhiều khả năng không đúng release contract.
12. **Dùng `jar` task thay cho `bootJar` rồi kỳ vọng `java -jar` có nested dependencies.** Cần Boot executable artifact.
13. **Coi `EXPOSE 8080` tự publish port.** Docker cần run/network mapping, server phải bind interface đúng.
14. **Bật HTTP/2 config rồi mặc định TLS/ALPN thành công trên mọi server.** Phải test negotiated behavior.
15. **Coi một JVM test PASS là native-image test PASS.** AOT/reflective resource restrictions khác.
16. **Bỏ qua proxy buffering cho SSE và idle timeout WebSocket.** Server thay đổi có thể tạo lỗi runtime.
17. **Chỉ test ping, không test error/cancellation/large bodies.** Một endpoint 200 chưa bảo đảm workload thật.
18. **Pin Netty/Tomcat jar version ngoài BOM không có kiểm thử.** Dễ bị binary incompatible.
19. **Dùng common Tomcat access log rồi vô tình ghi secrets/path/query.** Cần observability security policy.
20. **Dùng một startup log line để chứng minh server type.** Test `ReactiveWebServerApplicationContext` và actual HTTP request.

## 42. Checklist trước khi ship một WebFlux artifact

- [ ] Đã ghi rõ **Boot release**, Java runtime, Spring Framework và dependency BOM.
- [ ] HTTP stack được xác nhận là **WebFlux reactive** (không vô tình thành MVC).
- [ ] Selected **embedded server** được chứng minh bằng dependency tree và runtime test.
- [ ] Artifact là executable `bootJar`/OCI/native theo đường được hỗ trợ.
- [ ] Không gọi `.war` là supported WebFlux deployment trên Boot 3.3.
- [ ] Tomcat/Jetty/Undertow đã được đối chiếu với **đúng Boot version**.
- [ ] Phân biệt external servlet container với embedded server.
- [ ] `server.port`, containerPort, ingress, TLS và readiness probes được kiểm tra.
- [ ] HTTP/1.1 JSON, SSE/WebSocket, HTTP/2/TLS (nếu sử dụng) có regression tests trên target server.
- [ ] Outbound `WebClient` connector và connection pool vẫn hoạt động sau đổi server.
- [ ] Blocking operations được xử lý theo concurrency/timeout policy, không block I/O loops.
- [ ] Graceful shutdown và per-connection cancellation cleanup được kiểm thử.
- [ ] Logs/metrics/tracing không lộ token/cookie/PII.
- [ ] OCI/native image có đúng platform architecture, security updates và build reproducibility.
- [ ] Upgrade/downgrade và rollback plan có đo p99, throughput, error rate.

## 43. Câu hỏi kiểm tra và bài tập thực hành

1. Vì sao “WebFlux có Tomcat adapter” **không** chứng minh WebFlux WAR được Boot hỗ trợ?
2. Spring Boot 3.3 dùng embedded HTTP server gì khi chỉ thêm `spring-boot-starter-webflux`?
3. Các starter nào thay thế Reactor Netty để dùng embedded Tomcat, Jetty và Undertow?
4. `HttpHandler` trong WebFlux nằm ở tầng nào so với TCP socket và controller?
5. Tomcat + WebFlux khác Tomcat + Spring MVC ở điểm nào dù cả hai cùng sử dụng Servlet-related infrastructure bên dưới?
6. Undertow adapter của WebFlux có dựa vào Servlet API giống Tomcat không?
7. Nếu runtime classpath có cả `starter-web` và `starter-webflux`, Boot thường chọn stack nào?
8. `spring.main.web-application-type=reactive` sửa được classpath có thư viện `javax.servlet.*` không?
9. Khi bỏ `spring-boot-starter-reactor-netty`, phải kiểm tra thêm phần nào của outbound `WebClient`?
10. Boot 2.7/Tomcat 9/`javax.servlet` khác Boot 3.3/Tomcat 10.1/`jakarta.servlet` như thế nào?
11. Vì sao khả năng deploy một Boot **Servlet** application lên Servlet 5.0+ không phủ nhận WebFlux WAR unsupported?
12. `bootJar`, `jar`, traditional WAR và native image có cùng launcher/lifecycle không?
13. Nếu chạy Docker image với `EXPOSE 8080` nhưng bind `127.0.0.1` trong container, client ngoài container có thể gặp gì?
14. Tại sao SSE/WebSocket cần test qua ingress/proxy thay vì chỉ ping HTTP 200?
15. Từ test `ReactiveWebServerApplicationContext`, bạn sẽ xác nhận actual server type thế nào?
16. Vì sao phải dùng BOM để thống nhất Reactor Core/Netty/Servlet server versions?
17. Boot 4.1 còn liệt kê Undertow trong supported embedded servlet servers không?
18. Native image AOT có giới hạn gì với reflection/dynamic beans?
19. Blocking JDBC trong WebFlux trên embedded Jetty có tự trở thành non-blocking không?
20. Nếu hạ tầng bắt buộc nộp WAR nhưng sản phẩm thật cần WebFlux, có hai lựa chọn triển khai nào cần thảo luận?

**Bài tập A:** Chạy project mục 13–19 với 4 variants `-PwebServer`. Ghi lại dependency tree, server class, HTTP response và SSE body. Nếu variant thất bại, phân loại dependency/version hay protocol/runtime error thay vì ép pass.

**Bài tập B:** Cố ý thêm `spring-boot-starter-web` vào runtime của project trong local test, quan sát sự khác biệt giữa Servlet/Reactive application contexts. Khôi phục dependency sau thí nghiệm.

**Bài tập C:** Tạo `bootJar`, inspect `BOOT-INF/classes`/`BOOT-INF/lib`, chạy `java -jar`, rồi build Docker image để truy cập endpoint qua `-p 8080:8080`. Phân biệt JAR packaging với container runtime.

**Bài tập D:** Với một service đang chạy Boot 3.3 Undertow, viết upgrade checklist lên Boot 4.1 dựa trên system requirements và server support list của target release. Không thử override Undertow version mà bỏ qua docs.

**Bài tập E:** Với yêu cầu deploy external WAR, so sánh Spring MVC WAR và WebFlux executable image về lifecycle, traffic routing, auth/security, readiness và rollback.

## 44. Kết luận

Trong Spring Boot 3.3, **WebFlux có thể chạy trên nhiều embedded HTTP servers**, nhưng điều đó **không** có nghĩa mọi packaging/deployment mechanism đều được hỗ trợ. Phải giữ ranh giới:

```text
Spring WebFlux programming model
       |
       v
Spring Boot reactive server auto-configuration
       |
       +-- Reactor Netty (default)
       +-- Tomcat / Jetty / Undertow (embedded, Boot 3.3)
       |
       v
Executable JAR / OCI image / compatible native executable
       |
       v
Test real server, protocols, startup and shutdown

Traditional external WAR deployment of Boot WebFlux:
  NOT SUPPORTED in Boot 3.3
```

Chọn stack và server theo **đúng release**, dùng BOM để quản lý versions, xác nhận bằng real HTTP tests và đóng gói theo lifecycle mà Spring Boot hỗ trợ. Nếu một tổ chức bắt buộc WAR, hãy trao đổi rõ lựa chọn **MVC WAR** hoặc **WebFlux chạy độc lập** thay vì dựa vào hiểu lầm rằng tên “Tomcat” giống nhau làm mọi mô hình triển khai tương đương.

### Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Embedded Web Servers; thay Reactor Netty bằng Tomcat/Jetty/Undertow: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3 — Traditional Deployment; lưu ý WebFlux WAR not supported: https://docs.spring.io/spring-boot/3.3/how-to/deployment/traditional-deployment.html
- Spring Boot 3.3 — System Requirements (Java, Servlet containers, GraalVM): https://docs.spring.io/spring-boot/3.3/system-requirements.html
- Spring Boot 3.3 — Reactive Web Applications: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Framework — WebFlux Overview, Servers and Thread Model: https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html
- Spring Framework — Reactive Core/HttpHandler/Server Adapters: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Boot 3.3 — Packaging Executable Archives/Gradle: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 — Native Images/AOT Limitations: https://docs.spring.io/spring-boot/3.3/reference/packaging/native-image/introducing-graalvm-native-images.html
- Spring Boot 2.7.18 — System Requirements: https://docs.spring.io/spring-boot/docs/2.7.18/reference/html/getting-started.html
- Spring Boot 4.1 — System Requirements: https://docs.spring.io/spring-boot/4.1/system-requirements.html
- Project Reactor — Schedulers and Threading: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
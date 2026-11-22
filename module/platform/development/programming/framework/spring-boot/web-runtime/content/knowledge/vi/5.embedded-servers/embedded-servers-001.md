# Tomcat, Jetty, Undertow và Reactor Netty trong Spring Boot

## 1. Mục tiêu và phạm vi

Spring Boot có thể khởi chạy máy chủ HTTP ngay trong tiến trình JVM của ứng dụng. Máy chủ này được gọi là embedded web server, hay máy chủ nhúng. Bốn tên thường gặp là Apache Tomcat, Eclipse Jetty, Undertow và Reactor Netty. Chúng không hoàn toàn thay thế nhau trong mọi ứng dụng: việc chọn server phải phù hợp với mô hình Spring MVC (Servlet) hoặc Spring WebFlux (reactive), phiên bản Spring Boot, cách ứng dụng xử lý I/O và yêu cầu triển khai.

Sau bài học, bạn có thể giải thích vai trò máy chủ nhúng; phân biệt Servlet container với reactive HTTP server; hiểu mặc định Tomcat và Reactor Netty; chọn Jetty hoặc Undertow đúng phiên bản; thay dependency an toàn; cấu hình port, thread, timeout và shutdown; kiểm tra server thực sự chạy; và tránh các ngộ nhận về hiệu năng.

**Lưu ý theo phiên bản:** Spring Boot 3.x hỗ trợ Tomcat, Jetty, Undertow và Reactor Netty theo các tổ hợp web stack thích hợp. Spring Boot 4.0 đã loại bỏ tích hợp Undertow và starter tương ứng vì baseline Servlet 6.1. Các đoạn dependency dùng tên starter trong bài được viết cho Spring Boot 3.x; trước khi áp dụng cho Boot 4.x, kiểm tra tài liệu của chính nhánh phiên bản đang sử dụng. Không nên dùng một hướng dẫn của Boot 3.x để suy ra rằng Undertow vẫn được hỗ trợ trong Boot 4.x.

## 2. Máy chủ nhúng là gì?

Trước đây, nhiều ứng dụng Java web được đóng gói thành WAR rồi triển khai vào một Tomcat hoặc application server được cài riêng. Với Spring Boot, mô hình thông dụng là đóng gói ứng dụng thành executable JAR chứa các thư viện và cơ chế bootstrap cần thiết để chạy một HTTP server ngay trong tiến trình ứng dụng.

Luồng khởi động cơ bản:

1. JVM gọi phương thức main của ứng dụng.
2. SpringApplication tạo và refresh ApplicationContext.
3. Spring Boot phát hiện loại web application từ classpath và cấu hình.
4. Auto-configuration đăng ký WebServerFactory thích hợp.
5. WebServerFactory tạo embedded server; server bind vào địa chỉ/port.
6. Spring kết nối web framework với server và bắt đầu nhận request.
7. Khi application context đóng, Spring dừng server và giải phóng tài nguyên.

Máy chủ nhúng phụ trách kết nối mạng, giao thức HTTP, socket, request/response, quản lý tài nguyên I/O và cơ chế giao tiếp với web framework. Nó không thay thế Spring MVC/WebFlux, các Bean nghiệp vụ, service, repository hay Spring Security.

Ưu điểm của mô hình embedded server:

- Dễ chạy cùng một artifact trên laptop, máy ảo hoặc container.
- Có thể đóng gói và kiểm thử ứng dụng gần với môi trường chạy thật.
- Phiên bản server thường được quản lý cùng dependency của ứng dụng.
- Không cần quy trình deploy WAR lên một server cài độc lập trong tình huống phổ biến.
- Dễ chạy nhiều instance độc lập với port và cấu hình môi trường riêng.

Nhưng “nhúng” không đồng nghĩa không cần vận hành. Vẫn phải cấu hình TLS/proxy, resource limit, timeout, log, health, readiness, security, graceful shutdown và cập nhật phiên bản server khi có lỗ hổng bảo mật.

## 3. Phân biệt web stack và HTTP server

Có hai câu hỏi khác nhau:

1. **Ứng dụng dùng web programming model nào?** Spring MVC/Servlet hay Spring WebFlux/reactive.
2. **Thành phần nào nhận kết nối HTTP?** Tomcat, Jetty, Undertow hoặc Reactor Netty.

Spring MVC sử dụng Servlet API. Tomcat, Jetty và Undertow là các Servlet container trong những phiên bản Spring Boot có hỗ trợ tương ứng. Spring MVC có thể xử lý bất đồng bộ một số trường hợp, nhưng không biến thành WebFlux chỉ vì đổi container.

Spring WebFlux dùng cơ chế reactive và các HTTP adapter phù hợp. Reactor Netty là server mặc định thông dụng cho WebFlux. WebFlux cũng có thể chạy trên Tomcat/Jetty qua adapter thay vì bắt buộc dùng Reactor Netty. Trong Spring Boot 3.x, Undertow cũng là một lựa chọn được tài liệu nhánh đó liệt kê cho reactive server.

Hai luồng khái quát:

~~~text
Spring MVC / Servlet
Client -> embedded Servlet container
       -> Servlet Filter chain
       -> DispatcherServlet
       -> Handler / Controller
       -> Response

Spring WebFlux / reactive
Client -> embedded HTTP server (thường là Reactor Netty)
       -> reactive HttpHandler / WebFilter chain
       -> DispatcherHandler hoặc functional router
       -> Mono / Flux / response publisher
       -> Response
~~~

Sự khác biệt không dừng ở tên server: Servlet filter là jakarta.servlet.Filter; reactive filter là org.springframework.web.server.WebFilter. Spring Security MVC thường dùng SecurityFilterChain, còn WebFlux dùng SecurityWebFilterChain. Cách quản lý thread và yêu cầu tránh blocking trên event loop cũng khác nhau.

Đặc biệt, thêm spring-boot-starter-webflux vào project MVC để sử dụng WebClient không tự động biến HTTP server thành Reactor Netty. Khi có cả Spring MVC và WebFlux trên classpath, Spring Boot thường chọn cấu hình MVC theo mặc định. Nếu chủ đích là ứng dụng reactive, cần thiết kế dependency và application type đúng ngay từ đầu.

## 4. So sánh bốn công nghệ

| Công nghệ | Vai trò điển hình | Mô hình xử lý | Spring Boot 3.x | Điểm cần nhớ |
| --- | --- | --- | --- | --- |
| Apache Tomcat | Servlet container mặc định của Spring MVC | Connector/NIO, Servlet request và thread xử lý | Có starter Tomcat; dùng với MVC và adapter WebFlux | Lựa chọn mặc định, hệ sinh thái rộng |
| Eclipse Jetty | Servlet container thay thế Tomcat | Connector, thread pool, cơ chế async của Jetty | Có starter Jetty; dùng với MVC và adapter WebFlux | Phù hợp khi đã có kinh nghiệm/tích hợp Jetty |
| Undertow | Servlet container/HTTP server | Kiến trúc XNIO, I/O threads và worker threads | Có starter Undertow; dùng trong những cấu hình được Boot 3.x hỗ trợ | **Boot 4.0 bỏ hỗ trợ embedded Undertow** |
| Reactor Netty | Reactive HTTP server, mặc định của WebFlux | Netty event loop kết hợp Reactor | Có starter Reactor Netty, thường dùng với WebFlux | Không phải Servlet container để chạy Spring MVC |

Bảng trên mô tả các mô hình thông dụng, không khẳng định một server luôn nhanh hơn server khác. Hiệu năng còn phụ thuộc xử lý nghiệp vụ, database, connection pool, logging, TLS, loại workload, số core, giới hạn tài nguyên và cấu hình.

### 4.1. Tomcat

Apache Tomcat cung cấp môi trường Servlet cho Spring MVC. Khi dùng spring-boot-starter-web trong Spring Boot 3.x, starter Tomcat thường có mặt theo dependency bắc cầu. Spring Boot tự tạo TomcatServletWebServerFactory và đăng ký DispatcherServlet cùng các Servlet/Filter phù hợp.

Tomcat dùng connector để lắng nghe kết nối HTTP; trong cấu hình Servlet phổ biến, request đồng bộ sử dụng thread xử lý. Các API bất đồng bộ của Servlet cũng được Tomcat hỗ trợ, nên không nên mô tả Tomcat là chỉ biết I/O blocking.

Khi lựa chọn Tomcat:

- Hợp lý cho API MVC thông thường và các hệ thống đã dùng Servlet/Spring Security MVC.
- Thường giảm công sức cấu hình vì là mặc định được tài liệu Spring Boot hướng dẫn rộng rãi.
- Dễ tìm tài liệu về connector, thread, access log, session, proxy và TLS.
- Nên đo tải thực tế trước khi chỉnh thread pool; tăng số thread vô điều kiện có thể làm tăng memory, context switch và áp lực lên database.

Một số property Spring Boot 3.x dành riêng cho Tomcat là server.tomcat.threads.max và server.tomcat.max-connections. Ý nghĩa của chúng khác nhau: số kết nối mở không đồng nghĩa số request được xử lý đồng thời bởi worker threads.

### 4.2. Jetty

Eclipse Jetty cũng là một Servlet container và có thể được nhúng trực tiếp vào Spring Boot. Jetty có kiến trúc connector/handler và thread pool riêng, hỗ trợ Servlet và các tình huống HTTP bất đồng bộ.

Có thể chọn Jetty khi nhóm đã quen vận hành Jetty, khi phải tích hợp đặc tính cụ thể của Jetty hoặc khi benchmark trên workload thật cho thấy phù hợp. Đổi sang Jetty không có nghĩa phải đổi toàn bộ controller MVC; Spring MVC API vẫn giữ vai trò xử lý request.

Cần quan sát thread pool, connector, backlog, timeout, TLS và cấu hình đặc thù Jetty. Property như server.jetty.threads.max áp dụng cho Jetty; property server.tomcat.* không tự động có hiệu lực khi server đã chuyển sang Jetty.

### 4.3. Undertow

Undertow là HTTP server và Servlet container dựa trên XNIO, thường phân biệt I/O threads với worker threads. Trên các cấu hình Servlet đồng bộ, việc xử lý công việc blocking cần được chuyển đến worker thích hợp; không được chiếm I/O thread bằng thao tác chờ kéo dài.

Trong Spring Boot 3.x, Undertow có thể thay Tomcat bằng spring-boot-starter-undertow. Những property thường thấy gồm server.undertow.threads.io và server.undertow.threads.worker. Chúng là thông số cần cân nhắc theo CPU và tải, không phải giá trị “càng lớn càng tốt”.

**Giới hạn tương thích bắt buộc:** Spring Boot 4.0 yêu cầu Servlet 6.1 và đã bỏ hỗ trợ embedded Undertow. Không thêm starter Undertow của Boot 3.x vào project Boot 4.x rồi mong auto-configuration hoạt động. Khi nâng từ Boot 3.x có Undertow sang Boot 4.x, phải lên kế hoạch chuyển sang server còn được hỗ trợ như Tomcat hoặc Jetty, kiểm tra lại dependency, property, API và kết quả test.

### 4.4. Reactor Netty

Netty là bộ công cụ mạng dựa trên sự kiện; Reactor Netty tích hợp Netty với Project Reactor và cung cấp HTTP server/client cho mô hình reactive. Với spring-boot-starter-webflux, Reactor Netty thường là HTTP server mặc định.

Request được xử lý qua event-loop threads và pipeline không đồng bộ. Nếu handler chỉ tạo Mono/Flux nhưng lại gọi JDBC blocking, Thread.sleep hoặc API chặn kéo dài trên event loop thì hệ thống vẫn có thể bị nghẽn. Muốn khai thác reactive tốt cần xem xét cả chuỗi dependency và cách xử lý I/O.

Reactor Netty không triển khai Servlet API theo vai trò một Servlet container. Do đó nó không phải lựa chọn chỉ cần đổi dependency để chạy nguyên một ứng dụng Spring MVC. Muốn chuyển từ MVC/Tomcat sang WebFlux/Reactor Netty, cần rà soát controller, filter, security, session, validation, data access và mọi lời gọi blocking.

Lưu ý: Một ứng dụng MVC có thể dùng Reactor Netty làm HTTP client thông qua WebClient trong một số cấu hình dependency. Điều đó không chứng minh server nhận request của ứng dụng đang chạy trên Reactor Netty.

## 5. Spring Boot quyết định server như thế nào?

Spring Boot kết hợp nhiều yếu tố:

1. Loại web application: SERVLET, REACTIVE hoặc NONE.
2. Starter và thư viện thật sự có trên runtime classpath.
3. Các điều kiện auto-configuration và Bean đã tồn tại.
4. Cấu hình override cụ thể do ứng dụng cung cấp.

Ở nhánh Boot 3.x thông thường:

| Dependency chính | Web stack mặc định | HTTP server mặc định |
| --- | --- | --- |
| spring-boot-starter-web | Spring MVC / Servlet | Tomcat |
| spring-boot-starter-webflux | Spring WebFlux | Reactor Netty |
| Cả web và webflux | Thường là Spring MVC | Tomcat nếu starter Tomcat vẫn hiện diện |
| Starter web và thay Tomcat bằng Jetty | Spring MVC / Servlet | Jetty |
| Starter web và thay Tomcat bằng Undertow | Spring MVC / Servlet | Undertow (chỉ phiên bản hỗ trợ) |

Đây là mô hình mặc định; dependency exclusions, application type và custom WebServerFactory có thể làm thay đổi kết quả. Không xác định server bằng suy luận từ tên project. Hãy kiểm tra runtimeClasspath và log sau khởi động.

Các factory quan trọng:

- ServletWebServerFactory là contract để tạo embedded Servlet server.
- TomcatServletWebServerFactory, JettyServletWebServerFactory và UndertowServletWebServerFactory là các implementation tương ứng trong nhánh hỗ trợ.
- ReactiveWebServerFactory là contract của reactive server.
- NettyReactiveWebServerFactory là factory dành cho Reactor Netty; cũng có factory cho reactive adapter của Tomcat/Jetty trong các phiên bản phù hợp.

Spring Boot chọn và cấu hình factory thông qua auto-configuration. WebServerFactoryCustomizer cho phép tùy chỉnh factory trước khi server khởi chạy; dùng property được hỗ trợ trước, chỉ dùng code customizer nếu property chưa đáp ứng.

## 6. Ví dụ Spring MVC chạy Tomcat mặc định

Ví dụ dưới đây dành cho **Spring Boot 3.3.x, Java 17+**, sử dụng Gradle Groovy DSL và project đã có Gradle Wrapper. Một cấu hình build tối thiểu tham khảo:

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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là ví dụ chạy độc lập trong một project Gradle có wrapper tương thích. Trong dự án thật, nên dùng bộ phiên bản plugin/dependency do dự án quản lý, thay vì sao chép phiên bản mẫu vào một build đã có cấu hình riêng.

Tệp src/main/java/example/web/EmbeddedServerApplication.java:

~~~java
package example.web;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EmbeddedServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(EmbeddedServerApplication.class, args);
    }
}
~~~

Tệp src/main/java/example/web/StatusController.java:

~~~java
package example.web;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {
    @GetMapping("/api/status")
    public Map<String, String> status() {
        return Map.of("status", "ok");
    }
}
~~~

Chạy trên Linux/macOS:

~~~bash
./gradlew bootRun
~~~

Trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Sau khi startup thành công, gọi:

~~~bash
curl -i http://localhost:8080/api/status
~~~

Kết quả body JSON:

~~~json
{"status":"ok"}
~~~

Status HTTP mong đợi là 200. Dòng log startup thường cho biết Tomcat đã bắt đầu lắng nghe port cụ thể; câu chữ chính xác thay đổi theo phiên bản. Nếu ứng dụng không bind được port, hãy tìm nguyên nhân gốc trong exception log.

Để đóng gói:

~~~bash
./gradlew test
./gradlew bootJar
~~~

Sau đó chạy đúng tên JAR thật trong build/libs bằng java -jar. Tên file được xác định từ version và cấu hình artifact của project, không phải một tên cố định cho mọi project.

## 7. Đổi từ Tomcat sang Jetty trong Spring MVC

Cần **loại bỏ starter Tomcat** từ dependency bắc cầu của starter web và **thêm starter Jetty**. Trong build.gradle dành cho Boot 3.x, thay phần dependencies tương ứng bằng:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }
    implementation 'org.springframework.boot:spring-boot-starter-jetty'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Giữ nguyên hai file Java ở phần 6. Build và chạy lại ứng dụng, kiểm tra log để xác nhận Jetty thực sự được khởi động và GET /api/status vẫn trả JSON như cũ.

Đây là thao tác thay implementation của embedded Servlet server, không phải chuyển framework Spring MVC sang Spring WebFlux. Các loại Servlet filter, MVC controller và cấu hình security kiểu Servlet vẫn là mối quan tâm chính.

Đối với Maven, ý tưởng giống nhau: đặt exclusion cho spring-boot-starter-tomcat trong dependency spring-boot-starter-web, rồi khai báo dependency spring-boot-starter-jetty. Không chỉ thêm Jetty trong khi giữ nguyên toàn bộ Tomcat rồi đoán framework sẽ chọn server nào.

## 8. Đổi từ Tomcat sang Undertow trong Spring Boot 3.x

Trong project **Boot 3.x còn hỗ trợ Undertow**, dùng:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }
    implementation 'org.springframework.boot:spring-boot-starter-undertow'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Các controller MVC ở phần 6 có thể giữ nguyên. Kiểm tra dependency, startup log, response HTTP và test tích hợp trước khi kết luận việc chuyển server thành công.

**Không áp dụng đoạn này cho Spring Boot 4.0 trở lên** vì starter embedded Undertow đã bị bỏ khỏi hỗ trợ chính thức tại 4.0. Nếu môi trường đang nâng phiên bản, chọn server được Spring Boot mục tiêu hỗ trợ rồi xử lý các thay đổi cấu hình liên quan.

## 9. Spring WebFlux và Reactor Netty

Muốn một ứng dụng reactive, tạo project có spring-boot-starter-webflux và không có starter web MVC. Trên Boot 3.x, phần dependencies của một project reactive tối thiểu:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Spring Boot sẽ dùng Reactor Netty theo mặc định khi các starter và auto-configuration còn nguyên.

Tệp src/main/java/example/web/ReactiveStatusController.java trong project WebFlux riêng:

~~~java
package example.web;

import java.util.Map;
import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReactiveStatusController {
    @GetMapping("/api/reactive-status")
    public Mono<Map<String, String>> status() {
        return Mono.just(Map.of("status", "ok"));
    }
}
~~~

Ứng dụng reactive vẫn cần class main được đánh dấu @SpringBootApplication như ví dụ phần 6. Khi chạy project chỉ có WebFlux starter:

~~~bash
./gradlew bootRun
curl -i http://localhost:8080/api/reactive-status
~~~

Body JSON mong đợi:

~~~json
{"status":"ok"}
~~~

Mono.just trong ví dụ chỉ minh họa kiểu phản hồi; nó không tự biến một thao tác blocking thành non-blocking. Trong ứng dụng thực, tránh chặn event-loop bằng Thread.sleep, JDBC đồng bộ, gọi HTTP đồng bộ hoặc ghi file đồng bộ kéo dài. Với các phần bắt buộc blocking, cần tách khỏi event loop bằng cơ chế điều phối phù hợp và đánh giá lại lợi ích reactive.

### 9.1. Có thể dùng Jetty/Tomcat với WebFlux không?

Có. Spring WebFlux có adapter để hoạt động trên một số Servlet container, nên cần phân biệt “server công nghệ nào” với “framework là MVC hay WebFlux”. Trong các phiên bản được hỗ trợ, có thể thay Reactor Netty bằng Jetty hoặc Tomcat thông qua dependency exclusion và starter tương ứng.

Ví dụ cấu hình Gradle Boot 3.x thay Reactor Netty bằng Jetty:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-webflux') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-reactor-netty'
    }
    implementation 'org.springframework.boot:spring-boot-starter-jetty'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Vẫn phải xác nhận nhánh Spring Boot đích hỗ trợ tổ hợp đó, kiểm tra runtime classpath và kiểm thử HTTP thực tế. WebFlux chạy trên Servlet container vẫn sử dụng web programming model của WebFlux; không đồng nghĩa controller chuyển thành Spring MVC.

### 9.2. Nếu thêm cả hai starter thì sao?

Khi một project có cả spring-boot-starter-web và spring-boot-starter-webflux, Boot thường ưu tiên MVC. Nhiều project dùng WebClient trong ứng dụng MVC, và trường hợp đó hoàn toàn hợp lệ. Để xây dựng ứng dụng reactive server, nên cấu hình dependency rõ ràng và kiểm tra loại ApplicationContext; không lấy sự tồn tại của reactor-netty trong cây dependency làm bằng chứng server đã chuyển sang Netty.

## 10. Cấu hình chung của embedded server

Một số property áp dụng cho cả Servlet và reactive server, tùy hỗ trợ của phiên bản/framework:

~~~yaml
server:
  port: 8080
  compression:
    enabled: true
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Ví dụ này phù hợp để minh họa cấu hình Boot 3.x. Trong Spring Boot 4.x, graceful shutdown đã được bật mặc định theo tài liệu nhánh hiện hành; cần đọc chính xác hành vi theo phiên bản.

Các khái niệm cần hiểu:

- server.port: port HTTP mà embedded server cố gắng bind; mặc định thông dụng là 8080.
- server.port=0: yêu cầu chọn port còn trống, hữu ích cho test.
- server.address: địa chỉ network interface để bind, nếu cần giới hạn.
- server.compression.enabled: bật HTTP compression trong các trường hợp phù hợp.
- server.ssl.*: các thuộc tính TLS/SSL; giữ secret/certificate password ngoài source.
- server.shutdown và spring.lifecycle.timeout-per-shutdown-phase: chính sách dừng và thời gian chờ lifecycle.

Với Spring MVC/Servlet, server.servlet.context-path đặt context path của Servlet web application. Với WebFlux, dùng cấu hình base path của WebFlux tương ứng, không giả định server.servlet.context-path sẽ thay đổi reactive routes.

Nếu chạy sau reverse proxy hoặc ingress, cần xác định đúng việc xử lý Forwarded/X-Forwarded-* headers, TLS termination và trust boundary. Không tin tuyệt đối mọi forwarded header do client trực tiếp gửi; cấu hình proxy đáng tin cậy theo môi trường.

Trong container, không nên hard-code port hoặc địa chỉ bind theo máy phát triển. Cần phối hợp cấu hình server với port mapping, service discovery, health probes và network policy.

## 11. Cấu hình đặc thù cho từng server

Spring Boot có nhiều property chung nhưng không thể trừu tượng hóa hoàn toàn mọi đặc tính của các server.

### Tomcat

Ví dụ minh họa giới hạn worker thread, không phải khuyến nghị mặc định cho production:

~~~yaml
server:
  tomcat:
    threads:
      max: 120
~~~

Số thread nên được quyết định qua đo tải, latency, CPU và mức blocking của nghiệp vụ. Việc tăng thread có thể tạo thêm áp lực lên database pool, memory và CPU.

### Jetty

Ví dụ minh họa:

~~~yaml
server:
  jetty:
    threads:
      max: 160
~~~

Đừng dùng property server.tomcat.* để điều chỉnh Jetty. Tham khảo danh mục application properties đúng nhánh phiên bản và quan sát metric thực tế.

### Undertow, chỉ Boot 3.x còn hỗ trợ

Ví dụ minh họa hai loại thread:

~~~yaml
server:
  undertow:
    threads:
      io: 4
      worker: 32
~~~

I/O thread và worker thread phục vụ mục đích khác nhau. Nếu handler chạy blocking trực tiếp trên I/O thread, một nhóm nhỏ thread bị nghẽn có thể ảnh hưởng rất nhiều kết nối. Chỉ điều chỉnh sau khi có benchmark và hiểu workload.

### Reactor Netty

Reactor Netty dùng event loop và tài nguyên networking riêng. Có những property đặc thù trong namespace server.netty.* và các API/customizer của Reactor Netty; tập property cụ thể phụ thuộc nhánh Spring Boot. Khi tinh chỉnh event loop, connection pool hoặc TLS, phải kiểm tra cả HTTP server và những WebClient/Reactor Netty client có thể chia sẻ tài nguyên.

Không chuyển giá trị thread của Tomcat sang Reactor Netty theo tỷ lệ một-một: thread-per-request và event-loop có mô hình tài nguyên khác nhau. Các property không được server đang chạy hỗ trợ có thể không mang lại hiệu quả bạn kỳ vọng.

## 12. Auto-configuration và WebServerFactory

Trong Boot, các web server factory chịu trách nhiệm tạo server instance. Spring Boot cung cấp auto-configuration cho Servlet hoặc reactive context khi dependency và điều kiện phù hợp.

Chu trình ý tưởng:

~~~text
Dependencies + WebApplicationType + Properties
                 |
                 v
        Spring auto-configuration
                 |
                 v
       WebServerFactory bean
                 |
                 v
         Embedded HTTP server
                 |
                 v
         HTTP handlers/adapters
~~~

Khi cần tùy biến đặc thù mà property không biểu diễn được, có thể khai báo WebServerFactoryCustomizer với đúng factory type. Với Tomcat có TomcatServletWebServerFactory; với Reactor Netty có NettyReactiveWebServerFactory. Một customizer dành cho Tomcat không có tác dụng lên Jetty hoặc Netty.

Đừng tạo custom WebServerFactory chỉ để đổi port hoặc thread count vốn đã có property. Khi khai báo factory riêng, bạn chịu trách nhiệm về tác động lên auto-configuration và tương thích phiên bản. Kiểm thử startup thật sau mỗi thay đổi.

Khi nghi ngờ auto-configuration:

1. Kiểm tra dependency runtime và starter có bị exclude nhầm không.
2. Kiểm tra application type, active profile và các property có hiệu lực.
3. Xem nguyên nhân Bean condition trong condition evaluation report nếu cần.
4. Xác nhận server factory và log startup.
5. Gửi request thật đến port mà server đang bind.

## 13. Luồng nhận request và thread model

### 13.1. Spring MVC trên Tomcat/Jetty/Undertow

Một HTTP request đến connector rồi vào Servlet container. Sau Servlet Filter chain, DispatcherServlet tìm handler Spring MVC, binding tham số, gọi controller và trả response qua message converter.

Ở endpoint đồng bộ điển hình, thread container xử lý request có thể phải chờ truy vấn database hoặc HTTP client đồng bộ. Với nhiều request chậm, queue và số thread đang bận có thể tăng. Servlet có hỗ trợ xử lý bất đồng bộ, vì vậy không nên đánh đồng mọi request MVC với một mô hình blocking đơn giản trong tất cả tình huống.

Rủi ro thường gặp: thread pool cạn, database pool cạn, timeout, chậm do lock, request body lớn hoặc quá nhiều kết nối giữ lâu.

### 13.2. WebFlux trên Reactor Netty

Netty quản lý socket và event loop; Spring WebFlux xử lý luồng sự kiện qua reactive chain. Đường xử lý muốn non-blocking từ đầu đến cuối cần các dependency tương thích; nếu trộn blocking call vào event loop, thời gian phản hồi của các request khác cũng có thể bị ảnh hưởng.

Rủi ro thường gặp: blocking trên event-loop, backpressure chưa được hiểu đúng, subscribe thủ công không kiểm soát lifecycle, không quản lý cancellation, sử dụng connection pool không phù hợp hoặc giữ tài nguyên qua chuỗi reactive quá lâu.

Không nên tuyên bố Reactor Netty luôn nhanh hơn Tomcat. Đối với nghiệp vụ có thư viện đồng bộ, chuyển sang WebFlux mà không thay đổi data access có thể tăng độ phức tạp và không cải thiện thông lượng.

## 14. Kiểm tra server nào thực sự đang chạy

Sau khi sửa dependency, làm các kiểm tra theo thứ tự.

**Kiểm tra dependency ở runtime classpath:**

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Tìm starter và thư viện server tương ứng. Nếu cần điều tra một dependency cụ thể:

~~~bash
./gradlew dependencyInsight --dependency spring-boot-starter-tomcat --configuration runtimeClasspath
~~~

Nếu cây dependency còn Tomcat ngoài ý muốn, kiểm tra nhánh transitive nào đưa nó vào. Khi thấy reactor-netty là dependency của client trong ứng dụng MVC, không kết luận rằng HTTP server là Netty.

**Chạy application thật:**

~~~bash
./gradlew bootRun
~~~

Đọc log tên server và port. Tomcat, Jetty, Undertow và Netty thường có các dấu hiệu khác nhau trong startup logs, nhưng chuỗi log cụ thể thay đổi theo phiên bản và log level. Không parse tên server bằng cách phụ thuộc vào một dòng log hard-code.

**Gọi endpoint:**

~~~bash
curl -i http://localhost:8080/api/status
~~~

Xác nhận HTTP status, content type và response body. Nếu dùng profile hoặc port khác thì cập nhật URL. Lúc test thay server, cần lặp lại bộ kiểm thử đầu-cuối và các request có body, header, timeout, error mapping và security.

**Kiểm tra cổng:**

Nếu bind thất bại, xem tiến trình nào đã giữ port. server.port=0 giúp kiểm thử tránh xung đột port nhưng không thay thế việc kiểm tra port được cấu hình ở production. Với @SpringBootTest(webEnvironment = RANDOM_PORT), Spring Boot tự chọn port ngẫu nhiên phục vụ test HTTP.

## 15. Kiểm thử khi đổi máy chủ

Đổi web server là thay đổi ở tầng hạ tầng. API controller có thể không đổi nhưng hành vi runtime vẫn cần xác minh.

Một ma trận smoke test hợp lý:

| Khu vực | Điều phải xác minh |
| --- | --- |
| Startup | Context tạo thành công; một server đúng loại bind port |
| Routing | GET/POST, path variable, query parameter và request body |
| JSON | Content-Type, charset, converter và error response |
| Validation | 400 khi input sai; exception mapping đúng |
| Security | 401/403, filter chain và CORS hoạt động như thiết kế |
| Session/cookie | Cookie, session, SameSite/Secure nếu ứng dụng sử dụng |
| Long request | Timeout, upload/download, streaming hoặc SSE nếu có |
| Observability | Access log, application log, health, metric, trace |
| Shutdown | Dừng server theo đúng grace period và chính sách của load balancer |
| Deployment | TLS/proxy headers, port, container readiness và resource limits |

Với code của phần 6, có thể thêm test HTTP thật, sử dụng TestRestTemplate trong Spring Boot 3.x:

Tệp src/test/java/example/web/EmbeddedServerApplicationTests.java:

~~~java
package example.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class EmbeddedServerApplicationTests {

    @Autowired
    TestRestTemplate rest;

    @Test
    void statusEndpointReturnsOk() {
        ResponseEntity<String> response =
            rest.getForEntity("/api/status", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("{\"status\":\"ok\"}", response.getBody());
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Test này khởi động HTTP server thật trên port ngẫu nhiên, khác với unit test chỉ gọi trực tiếp phương thức controller. Với các server thay thế, chạy lại cùng bộ test để kiểm tra contract của ứng dụng; riêng WebFlux cần test reactive phù hợp và cấu hình ứng dụng WebFlux.

## 16. Vận hành trong production

### 16.1. Timeout và giới hạn kết nối

Cần hiểu rõ timeout đang đo điều gì: chờ thiết lập kết nối, chờ nhận request, chờ gửi response hay timeout của downstream HTTP/database. Mỗi server dùng tên property và API khác nhau cho các giới hạn chuyên biệt.

Không mở số kết nối/thread quá lớn chỉ vì số request tăng. Nút thắt thực tế có thể ở SQL, cache, HTTP client hoặc thread pool phụ trợ. Dùng load test xác định saturation và thiết lập giới hạn bảo vệ hệ thống.

### 16.2. HTTPS, proxy và giao thức

Thông thường client đi qua load balancer/reverse proxy trước khi đến embedded server. Phải thống nhất nơi kết thúc TLS, cách truyền scheme/host/remote IP và các forwarded headers được tin cậy. Nếu có yêu cầu HTTP/2, WebSocket hoặc SSE, hãy kiểm tra hỗ trợ và cấu hình của đúng server/Boot version.

Không bật TLS hoặc forwarded-header trust bằng cách sao chép ngẫu nhiên cấu hình từ môi trường khác; điều này có thể gây sai redirect URL, cookie Secure, client IP, hoặc lỗi bảo mật.

### 16.3. Health và readiness

Spring Boot Actuator có thể cung cấp health và readiness/liveness probes khi được cấu hình đúng. Cần phân biệt một tiến trình đang sống với một instance đủ điều kiện nhận traffic. Không expose các endpoint vận hành nhạy cảm ra Internet không kiểm soát.

### 16.4. Graceful shutdown

Spring Boot 3.x cho phép bật:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Mục tiêu là ngừng nhận request mới theo cách được server hỗ trợ, cho phép request đang xử lý hoàn tất trong giới hạn thời gian và đóng tài nguyên. Chi tiết từ chối request mới khác nhau giữa Tomcat, Jetty, Undertow và Reactor Netty; ví dụ tài liệu Boot 3.3 mô tả Undertow có thể trả 503 đối với request mới trong giai đoạn dừng.

Tại Boot 4.x, graceful shutdown bật mặc định theo tài liệu hiện hành. Dù phiên bản nào, cần kiểm tra hành vi thực tế trong container hoặc orchestrator vì tín hiệu dừng và thời gian chờ của nền tảng có thể cắt ngắn quá trình shutdown.

### 16.5. Logging và metric

Nên quan sát cùng một bộ chỉ số khi so sánh các server: throughput, p50/p95/p99 latency, error rate, CPU, heap, GC, open connections, active threads hoặc event-loop pressure, pool saturation và thời gian shutdown. Phân biệt log ứng dụng với access log của HTTP server.

Nếu benchmark, cố định phần cứng, JVM, garbage collector, JDK, workload, dữ liệu, concurrency và dependency. Warm up trước, chạy nhiều lần, so sánh dưới cùng điều kiện và ghi rõ khoảng biến động. Không suy luận thứ hạng hiệu năng tuyệt đối từ một mẫu test đơn lẻ.

## 17. Các lỗi cấu hình thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Application không start sau khi đổi server | Starter cũ còn trên runtimeClasspath, auto-configuration/factory xung đột hoặc phiên bản không tương thích | Kiểm tra dependency tree, loại starter không dùng, đối chiếu hỗ trợ của Boot version |
| Thêm WebFlux nhưng vẫn thấy Tomcat | Starter MVC vẫn tồn tại, MVC được chọn theo mặc định | Xác định ứng dụng cần MVC hay reactive; tổ chức lại dependency/application type |
| Không tìm thấy starter Undertow trên Boot 4 | Undertow đã bị loại khỏi hỗ trợ chính thức ở Boot 4.0 | Chuyển sang Tomcat/Jetty phù hợp và kiểm thử lại |
| Port 8080 bị chiếm | Tiến trình khác đang bind cổng | Tắt tiến trình xung đột hoặc cấu hình port khác |
| 404 dù server chạy | Sai path, context path/base path hoặc mapping | Kiểm tra mapping và URL thực tế |
| Thread cao/latency tăng ở MVC | Blocking dependency, pool nhỏ hoặc request chờ quá lâu | Đo thread dump, connection pool, timeout, latency từng dependency |
| Event loop bị nghẽn trong WebFlux | Gọi API blocking ngay trên event-loop | Dùng dependency non-blocking hoặc điều phối blocking ra executor phù hợp |
| Tăng thread không cải thiện throughput | Nút thắt downstream, lock, CPU hoặc GC | Đo tải và tìm saturation thực tế |
| Request sai scheme/client IP sau proxy | Forwarded headers hoặc trust boundary sai | Cấu hình proxy và forwarded-header strategy đúng môi trường |
| Dừng container làm hỏng request đang xử lý | Grace period không đủ hoặc SIGTERM không được truyền đúng | Kiểm tra shutdown policy và timeout của cả app lẫn orchestrator |

## 18. Cách chọn server cho một dự án

Không có lựa chọn tốt nhất cho mọi hoàn cảnh. Quy trình chọn thực tế:

1. **Xác định framework:** Servlet MVC hay WebFlux; thư viện database và HTTP client chủ yếu blocking hay non-blocking.
2. **Xác định phiên bản Spring Boot:** đặc biệt khi đề xuất Undertow, vì Boot 4 đã loại bỏ.
3. **Bắt đầu từ mặc định hợp lý:** Tomcat cho MVC, Reactor Netty cho WebFlux.
4. **Đổi server khi có lý do đo được:** yêu cầu tích hợp, chính sách tổ chức, đặc tính cụ thể hoặc kết quả benchmark trên workload thật.
5. **Kiểm tra dependency và runtime:** loại starter mặc định không dùng, xác nhận server đã được chọn.
6. **Kiểm thử đầy đủ:** routing, security, session, streaming, TLS, errors, health và graceful shutdown.
7. **Theo dõi vận hành:** đo trước/sau, có khả năng rollback nếu gặp regression.

Ba tình huống minh họa:

- API CRUD dùng Spring MVC + JPA/JDBC đồng bộ: bắt đầu với Tomcat. Có thể thử Jetty nếu có nhu cầu cụ thể; đổi sang Reactor Netty không tự làm JDBC trở thành non-blocking.
- Gateway/event-streaming dùng Spring WebFlux và client reactive: Reactor Netty là lựa chọn mặc định hợp lý; kiểm tra backpressure, event loop và timeout.
- Ứng dụng MVC hiện dùng Undertow trên Boot 3.x nhưng chuẩn bị lên Boot 4.x: đưa việc chuyển server sang Tomcat hoặc Jetty vào kế hoạch nâng cấp, chạy regression test trước khi rollout.

## 19. Bài thực hành có kiểm chứng

Thực hiện trên các project thử nghiệm riêng hoặc các nhánh có thể hoàn nguyên:

1. Tạo ứng dụng MVC ở phần 6; chạy với Tomcat mặc định.
2. Ghi nhận tên server/port trong log, response của GET /api/status, kết quả test và những dependency liên quan.
3. Thay Tomcat bằng Jetty theo phần 7, chạy cùng bộ test và kiểm tra server mới.
4. Nếu đang dùng Boot 3.x hỗ trợ Undertow, thử cấu hình phần 8 rồi so sánh cách startup và shutdown.
5. Tạo project WebFlux riêng với Reactor Netty, chạy endpoint reactive và phân biệt code WebFlux với controller Servlet.
6. Mô phỏng port conflict để quan sát lỗi bind; thử server.port=0 trong test.
7. Bật graceful shutdown và kiểm tra thời gian dừng với request có thời lượng thực tế trong môi trường test.
8. Ghi lại kết quả trong bảng gồm Boot version, server, web stack, dependency, startup, HTTP test, shutdown, lỗi và cách xử lý.

Bài thực hành đạt khi bạn chứng minh được server nào đang chạy bằng bằng chứng từ runtime, giải thích vì sao nó được chọn, đổi server đúng dependency và không đánh đồng Servlet MVC với reactive WebFlux.

## 20. Câu hỏi tự kiểm tra

1. Embedded server làm gì và khác Spring MVC ở đâu?
2. Vì sao spring-boot-starter-web thường kéo Tomcat còn spring-boot-starter-webflux thường kéo Reactor Netty?
3. Tomcat, Jetty và Undertow có điểm chung nào về Servlet API?
4. Vì sao Reactor Netty không thể chỉ thay Tomcat trong một ứng dụng MVC bất kỳ?
5. WebFlux chạy trên Jetty có trở thành Spring MVC không? Vì sao?
6. Cần thay đổi dependency như thế nào khi chuyển từ Tomcat sang Jetty ở Boot 3.x?
7. Vì sao Undertow cần chú ý đặc biệt khi nâng lên Spring Boot 4.0?
8. Property server.port khác các property server.tomcat.*, server.jetty.*, server.undertow.* thế nào?
9. Khi có cả starter web và webflux, framework nào thường được chọn?
10. Làm thế nào để xác minh server đang chạy mà không dựa vào suy đoán?
11. Tại sao tăng số thread có thể không cải thiện hiệu năng?
12. Những điều gì phải kiểm tra khi đổi server trong production?

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 – Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html)
- [Spring Boot 3.3 – Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Spring Boot 3.3 – Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Spring Boot 3.3 – Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)
- [Spring Boot 4.0 – Embedded Web Servers](https://docs.spring.io/spring-boot/4.0/how-to/webserver.html)
- [Spring Boot 4.0 Migration Guide – Undertow removal](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)

Các đường dẫn tới tài liệu theo phiên bản giúp tránh áp dụng nhầm starter, API và property giữa Spring Boot 3.x và 4.x.

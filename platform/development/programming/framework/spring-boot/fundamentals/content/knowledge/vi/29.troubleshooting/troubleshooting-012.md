# Ứng dụng chọn sai web type, thiếu server hoặc cổng bị chiếm

Khi chạy một ứng dụng Spring Boot, có ba tình huống thường bị nhầm thành cùng một lỗi: ứng dụng khởi động nhưng không mở cổng HTTP; ứng dụng cần cung cấp REST API nhưng startup thất bại vì không tạo được web server; hoặc embedded server dừng với thông báo port đã được tiến trình khác sử dụng. Để chẩn đoán đúng, cần tách ba lớp nguyên nhân:

1. **Web application type**: Spring Boot đang tạo ứng dụng Servlet, Reactive hay Non-web?
2. **Server dependency và auto-configuration**: runtime classpath có embedded server phù hợp không?
3. **Network binding**: server có bind được địa chỉ và port đã cấu hình không?

Chọn đúng `WebApplicationType.SERVLET` không tự cài Tomcat. Có Tomcat trên classpath cũng không giúp bind nếu port đang bị chiếm. Đổi port chỉ giải quyết xung đột địa chỉ; nó không sửa việc ứng dụng vô tình được khởi tạo dưới dạng non-web.

Bài học này dùng Spring Boot 3.x và Java 17/21 để trình bày cách nhận diện `NONE`, `SERVLET`, `REACTIVE`, kiểm tra starter và embedded server, xử lý port conflict trên Windows/Linux, phân biệt port trong container với host port và viết test không phụ thuộc cổng cố định.

## 1. Ba lớp cần kiểm tra

~~~mermaid
flowchart TD
    A["SpringApplication.run(...)"] --> B["Xác định WebApplicationType"]
    B --> C{"Web type"}
    C -->|NONE| D["Non-web context; không mở HTTP listener"]
    C -->|SERVLET| E["Tìm ServletWebServerFactory"]
    C -->|REACTIVE| F["Tìm ReactiveWebServerFactory"]
    E --> G{"Có Servlet server?"}
    F --> H{"Có Reactive server?"}
    G -->|Không| I["Thiếu server hoặc cấu hình WAR sai"]
    H -->|Không| I
    G -->|Có| J["Tạo web server"]
    H -->|Có| J
    J --> K["Đọc server.address và server.port"]
    K --> L{"Bind thành công?"}
    L -->|Không| M["Port/address conflict hoặc lỗi quyền"]
    L -->|Có| N["HTTP listener hoạt động"]
~~~

Một quy trình chẩn đoán hợp lý là xác định ứng dụng có chủ đích là web hay non-web, kiểm tra web type, xác nhận server dependency, đọc port/address hiệu lực, xác định process đang giữ port và cuối cùng kiểm tra network topology của máy/container.

Không nên đổi nhiều cấu hình cùng lúc. Nếu ứng dụng không mở port vì đang ở web type `NONE`, đổi port từ 8080 sang 9090 không giải quyết được nguyên nhân.

## 2. WebApplicationType là gì?

Spring Boot dùng `WebApplicationType` để quyết định loại application context và hạ tầng web cần khởi tạo.

| Giá trị | Mô hình | Hành vi |
| --- | --- | --- |
| `SERVLET` | Servlet-based web application | Dùng Servlet API và web server tương ứng, thường là embedded Tomcat |
| `REACTIVE` | Reactive web application | Dùng reactive web stack, thường là WebFlux và Reactor Netty |
| `NONE` | Non-web application | Không tạo web application context và không mở HTTP listener |

### 2.1. SERVLET

Ứng dụng Spring MVC thông thường dùng Servlet stack:

~~~java
@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Khi runtime classpath có Spring MVC và embedded Servlet server phù hợp, Spring Boot có thể khởi tạo Servlet web application context, tạo server và bind port.

Ví dụ controller:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @GetMapping("/{id}")
    public Map<String, String> find(@PathVariable String id) {
        return Map.of("id", id, "status", "ACCEPTED");
    }
}
~~~

Có `@RestController` không đồng nghĩa server chắc chắn đã mở port. Controller chỉ được phục vụ qua HTTP khi web context và server thực sự được khởi tạo.

### 2.2. REACTIVE

Ứng dụng dùng Spring WebFlux có thể khởi tạo Reactive web application:

~~~java
@RestController
@RequestMapping("/reactive/orders")
public class ReactiveOrderController {

    @GetMapping("/{id}")
    public Mono<Map<String, String>> find(@PathVariable String id) {
        return Mono.just(Map.of("id", id, "status", "ACCEPTED"));
    }
}
~~~

Với cấu hình phổ biến, `spring-boot-starter-webflux` kéo Reactor Netty làm embedded server. WebFlux cũng có thể chạy trên một số Servlet container tương thích; lựa chọn server phụ thuộc dependency và cấu hình runtime.

Không nên kết luận WebFlux bắt buộc chỉ dùng Netty. Điều cần xác nhận là có server implementation phù hợp với reactive application context.

### 2.3. NONE

Ứng dụng batch, command line, scheduler hoặc tác vụ nền có thể không cần HTTP listener:

~~~java
@SpringBootApplication
public class ImportJobApplication {
    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ImportJobApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.run(args);
    }
}
~~~

Ứng dụng `NONE` vẫn có thể sử dụng dependency injection, configuration properties, scheduling, database hoặc Spring events. Nó chỉ không tạo web application context để mở HTTP server.

Một process không mở port chưa chắc bị lỗi. Có thể đó là hành vi đúng theo thiết kế.

## 3. Spring Boot tự chọn web type như thế nào?

Khi gọi:

~~~java
SpringApplication.run(ShopApplication.class, args);
~~~

Spring Boot có thể suy luận web application type từ class có mặt trên runtime classpath. Ở mức khái quát:

- Có Spring MVC/Servlet stack phù hợp: thường chọn `SERVLET`.
- Có reactive web stack phù hợp mà không có MVC stack được ưu tiên: có thể chọn `REACTIVE`.
- Không có dấu hiệu web stack: có thể chọn `NONE`.

Việc suy luận dựa trên classpath và quy tắc của phiên bản Spring Boot, không chỉ dựa vào annotation trên controller.

### 3.1. Khi có cả Spring MVC và WebFlux

Một project có thể chứa cả hai starter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Trong cấu hình Spring Boot thông thường, khi cả Spring MVC và WebFlux cùng có mặt, Boot chọn **Servlet/MVC application type theo mặc định**. Có thể project chỉ thêm WebFlux để dùng `WebClient` cho outbound HTTP calls; điều đó không có nghĩa inbound server phải chuyển sang reactive.

Nếu thật sự muốn reactive application, có thể cấu hình:

~~~properties
spring.main.web-application-type=reactive
~~~

Nhưng cần bảo đảm runtime classpath có reactive server implementation. Chỉ ép web type mà không có server phù hợp có thể khiến startup thất bại.

### 3.2. Dùng WebClient không đồng nghĩa ứng dụng là Reactive server

`WebClient` là HTTP client API có thể dùng trong ứng dụng Servlet/MVC. Một kiến trúc hợp lệ có thể là Spring MVC xử lý inbound HTTP requests, `WebClient` gửi outbound HTTP requests và embedded Servlet server như Tomcat tiếp nhận request.

Không cần ép toàn bộ application thành `REACTIVE` chỉ vì có `WebClient` trong dependency.

### 3.3. Controller annotation không quyết định server

`@RestController` và `@RequestMapping` cung cấp metadata cho web framework. Nếu application type là `NONE` hoặc thiếu web server factory, các controller đó không được phục vụ như HTTP endpoints thông thường.

## 4. Cấu hình web application type tường minh

Có thể đặt type bằng property:

~~~properties
spring.main.web-application-type=servlet
~~~

Các giá trị thường dùng:

~~~properties
spring.main.web-application-type=servlet
spring.main.web-application-type=reactive
spring.main.web-application-type=none
~~~

Trong YAML:

~~~yaml
spring:
  main:
    web-application-type: servlet
~~~

Hoặc cấu hình bằng Java:

~~~java
SpringApplication application =
        new SpringApplication(ShopApplication.class);

application.setWebApplicationType(WebApplicationType.SERVLET);
application.run(args);
~~~

Với builder:

~~~java
new SpringApplicationBuilder(ShopApplication.class)
        .web(WebApplicationType.SERVLET)
        .run(args);
~~~

### 4.1. Khi nào nên đặt tường minh?

- Application module có dependency tree phức tạp và cần cố định Servlet/Reactive semantics.
- Ứng dụng batch dùng một số dependency web nhưng không được mở server.
- Một test context cần non-web behavior.
- Ứng dụng có cả MVC và WebFlux nhưng chủ đích runtime đã được xác định.

Nếu auto-detection hoạt động đúng, không cần thêm cấu hình chỉ để lặp lại default.

### 4.2. NONE không phải cách chữa thiếu server

Nếu ứng dụng cần REST API nhưng runtime thiếu Tomcat, đặt `spring.main.web-application-type=none` có thể giúp context khởi động mà không tạo server. Nhưng endpoint HTTP cũng sẽ không hoạt động.

Đây là thay đổi loại ứng dụng, không phải cài đặt server. Nếu mục tiêu là chạy API, hãy sửa dependency/runtime configuration để có web server phù hợp.

## 5. Embedded server đến từ đâu?

Spring Boot starter thường kéo theo embedded server phù hợp.

Servlet web application:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Trong cấu hình mặc định, starter web đưa embedded Tomcat vào runtime dependency graph.

Reactive web application phổ biến:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Starter WebFlux thường kéo Reactor Netty làm reactive embedded server.

### 5.1. Starter và server implementation khác nhau

Starter tập hợp dependencies cho một khả năng. Server implementation là thành phần thực sự mở network listener.

Với MVC, `spring-boot-starter-web` cung cấp Spring MVC và các dependency web phổ biến; `spring-boot-starter-tomcat` cung cấp embedded Tomcat trong cấu hình mặc định. Có thể thay Tomcat bằng Servlet container khác được Spring Boot hỗ trợ.

Nếu loại embedded server khỏi runtime classpath mà không thay bằng server khác, ứng dụng có thể không tạo được Servlet web server.

### 5.2. Kiểm tra Gradle runtime dependencies

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Để biết vì sao Tomcat được kéo vào:

~~~bash
./gradlew dependencyInsight --dependency tomcat --configuration runtimeClasspath
~~~

Với reactive server:

~~~bash
./gradlew dependencyInsight --dependency reactor-netty --configuration runtimeClasspath
~~~

Đọc output để biết dependency nào được include/exclude, version nào được resolve và server có mặt trong `runtimeClasspath` hay chỉ xuất hiện ở configuration khác.

### 5.3. Kiểm tra Maven dependency tree

~~~bash
mvn dependency:tree
~~~

Lọc theo starter Tomcat:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-tomcat
~~~

Hoặc embedded Tomcat artifacts:

~~~bash
mvn dependency:tree -Dincludes=org.apache.tomcat.embed:*
~~~

Nếu server bị exclude, hãy tìm dependency khai báo exclusion và xác định có server thay thế hay không.

### 5.4. Compile thành công nhưng runtime thiếu server

Compiler có thể biên dịch controller vì các API Spring MVC nằm trong compile classpath. Nhưng khi chạy, nếu embedded server không có trong runtime classpath, Spring Boot có thể không tìm được `ServletWebServerFactory` phù hợp.

Đây là khác biệt giữa compile classpath và runtime classpath.

## 6. Thay Tomcat bằng Jetty hoặc Undertow

Một ứng dụng có thể muốn dùng Servlet server khác Tomcat. Ví dụ Gradle loại Tomcat khỏi starter và thêm Jetty:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }

    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
~~~

Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-tomcat</artifactId>
        </exclusion>
    </exclusions>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jetty</artifactId>
</dependency>
~~~

Hãy dùng version được Spring Boot dependency management quản lý và xác nhận server tương thích với Boot version đang dùng.

Nếu runtime classpath có nhiều Servlet server implementations do dependency graph phức tạp, hãy kiểm tra auto-configuration và server factory thực tế. Không nên thêm Jetty mà quên loại Tomcat nếu mục tiêu là thay thế.

Tomcat/Jetty/Undertow là các lựa chọn Servlet server trong phạm vi tích hợp tương ứng. Reactor Netty là lựa chọn reactive server phổ biến. Thêm một Servlet server không tự giải quyết lỗi thiếu reactive server khi application type đang là `REACTIVE`.

## 7. WAR triển khai trên external Servlet container

Ứng dụng Spring Boot cũng có thể được đóng gói dạng WAR và triển khai vào Servlet container do môi trường cung cấp. Khi đó embedded server không nhất thiết được đóng gói như trong executable JAR.

Ví dụ class khởi tạo:

~~~java
@SpringBootApplication
public class ShopApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder builder) {
        return builder.sources(ShopApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Project WAR cần plugin, packaging và dependency scope phù hợp. External container chịu trách nhiệm cung cấp Servlet implementation.

Nếu cố chạy WAR như executable archive, cần bảo đảm Spring Boot plugin đã cấu hình executable WAR theo mục tiêu triển khai. Đừng kết luận thiếu embedded server khi ứng dụng được thiết kế cho external container.

## 8. Xác định application context thực tế

Có thể quan sát context được tạo:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(ShopApplication.class, args);

System.out.println(context.getClass().getName());
~~~

Các context class thường gặp:

| Application type | Context class điển hình |
| --- | --- |
| Servlet | `ServletWebServerApplicationContext` |
| Reactive | `ReactiveWebServerApplicationContext` |
| Non-web | Context non-web, ví dụ `AnnotationConfigApplicationContext` |

Tên class cụ thể là chi tiết implementation có thể thay đổi theo version/bootstrap mode. Dùng để chẩn đoán, không nên viết business logic phụ thuộc vào tên class.

### 8.1. Đọc startup log

Một web application thường có log xác nhận server đã khởi động và port thực tế, ví dụ Tomcat hoặc Netty đã bắt đầu lắng nghe. Nếu context hoàn tất mà không có thông báo server, hãy kiểm tra web type và server factory.

Đừng chỉ nhìn dòng `Started ...`. Một ứng dụng non-web vẫn có thể in thông báo đó thành công.

### 8.2. Condition evaluation report

Trong môi trường phát triển, có thể chạy:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot có thể in condition evaluation report để hỗ trợ xác định auto-configuration nào được áp dụng hoặc bị loại.

Đây là công cụ chẩn đoán. Một auto-configuration có thể back off vì thiếu class trên classpath, có bean tự định nghĩa hoặc property điều khiển. Không bật debug report rộng rãi trong production nếu output có thể tiết lộ cấu trúc nội bộ.

## 9. Embedded server không được tạo: nguyên nhân thường gặp

| Nguyên nhân | Dấu hiệu | Cách xử lý |
| --- | --- | --- |
| Web type là `NONE` | Context non-web, không có server startup log | Kiểm tra `spring.main.web-application-type` |
| MVC/WebFlux dependency bị thiếu | Không nhận diện web stack phù hợp | Kiểm tra starter/runtime classpath |
| Embedded server bị exclude | Thiếu server factory | Khôi phục dependency hoặc thêm server thay thế |
| Dependency chỉ có ở compileOnly/provided sai mục đích | Compile được nhưng runtime thiếu server | Điều chỉnh dependency scope |
| Chạy library module thay vì app module | Không có bootstrap/application phù hợp | Chạy đúng application module |
| WAR dành cho external container nhưng chạy sai cách | Deployment mode không đúng | Triển khai external container hoặc tạo executable archive |
| Custom configuration làm thay đổi auto-configuration | Factory không được tạo như dự kiến | Kiểm tra bean definitions và condition report |
| Profile/CLI override web type | Local và deployment khác nhau | Kiểm tra property source hiệu lực |

### 9.1. Lỗi thiếu ServletWebServerFactory

Một exception có thể có nội dung tương tự:

~~~text
ApplicationContextException: Unable to start web server
...
No qualifying bean of type
'org.springframework.boot.web.servlet.server.ServletWebServerFactory'
available
~~~

Điều này thường chỉ ra Spring đang tạo Servlet web application context nhưng không tìm thấy factory để tạo embedded server.

Các bước điều tra:

1. Kiểm tra application type có phải SERVLET không.
2. Kiểm tra starter/server dependency có trong runtime classpath không.
3. Kiểm tra exclusion và scope `provided`/`compileOnly`.
4. Kiểm tra đang chạy đúng module/artifact không.
5. Xem custom configuration có làm thay đổi auto-configuration không.

### 9.2. Lỗi thiếu ReactiveWebServerFactory

Nếu application type là REACTIVE nhưng không có server implementation phù hợp, context có thể báo không tìm thấy `ReactiveWebServerFactory` hoặc lỗi tạo reactive web server.

Kiểm tra WebFlux starter và reactive server dependency, không chỉ kiểm tra Servlet Tomcat.

## 10. Cấu hình server.port

Cổng HTTP mặc định của ứng dụng web Spring Boot thường là `8080`.

Trong properties:

~~~properties
server.port=9090
~~~

Trong YAML:

~~~yaml
server:
  port: 9090
~~~

Command-line:

~~~bash
java -jar app.jar --server.port=9090
~~~

JVM system property:

~~~bash
java -Dserver.port=9090 -jar app.jar
~~~

Environment variable:

~~~text
SERVER_PORT=9090
~~~

### 10.1. Port có thể bị override

Giả sử `application.yml` đặt 8080, nhưng deployment truyền:

~~~bash
java -jar app.jar --server.port=9090
~~~

Trong cấu hình Spring Boot thông thường, command-line property có độ ưu tiên cao hơn config file, nên port hiệu lực có thể là 9090.

Profile-specific configuration cũng có thể đổi port:

~~~yaml
# application-dev.yml
server:
  port: 8081
~~~

Khi profile `dev` active, ứng dụng có thể dùng 8081, trừ khi một property source có độ ưu tiên cao hơn override.

Khi chẩn đoán, không chỉ đọc YAML. Hãy kiểm tra profile, environment variables, JVM properties, command-line arguments và các external config sources.

### 10.2. Xác nhận port thực tế

Hãy xác nhận startup log hoặc quan sát listener của process. Khi dùng port ngẫu nhiên, server có thể bind một port khác giá trị cấu hình ban đầu `0`.

## 11. Port 0 và port -1

### 11.1. Port 0: hệ điều hành chọn port khả dụng

Trong test hoặc môi trường chạy nhiều instance, có thể dùng:

~~~properties
server.port=0
~~~

Port `0` yêu cầu hệ điều hành chọn một cổng khả dụng khi bind.

Integration test:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {

    @LocalServerPort
    int port;

    @Test
    void serverStartsOnRandomPort() {
        assertThat(port).isBetween(1, 65535);
    }
}
~~~

`RANDOM_PORT` khởi chạy server trên port ngẫu nhiên và `@LocalServerPort` cung cấp port thực tế cho test.

Client không gọi `http://localhost:0`. Hãy dùng port được server bind thực sự.

### 11.2. RANDOM_PORT khác MOCK

`@SpringBootTest(webEnvironment = MOCK)` không tương đương việc khởi chạy embedded server trên TCP port thật. Nếu muốn phát hiện port conflict, hãy dùng `RANDOM_PORT` hoặc smoke test runtime.

### 11.3. Port -1: không mở HTTP listener

Spring Boot hỗ trợ `server.port=-1` trong một số ứng dụng web để không mở HTTP listener nhưng vẫn giữ web application context.

| Giá trị | Ý nghĩa |
| --- | --- |
| `server.port=8080` | Bind port 8080 |
| `server.port=0` | Hệ điều hành chọn port khả dụng |
| `server.port=-1` | Không mở HTTP listener |

Nếu bạn mong API HTTP hoạt động mà cấu hình là `-1`, đây là nguyên nhân trực tiếp khiến không có listener.

## 12. Port bị chiếm: nhận diện BindException

Lỗi startup thường gặp:

~~~text
Web server failed to start. Port 8080 was already in use.
~~~

Hoặc:

~~~text
java.net.BindException: Address already in use
~~~

Server không bind được port do một process khác đang sử dụng địa chỉ/port đó hoặc hệ điều hành từ chối việc bind.

Nguyên nhân phổ biến:

- Một instance Spring Boot cũ vẫn chạy.
- Bấm Run hai lần trong IDE.
- Một ứng dụng khác đang dùng 8080.
- Test chạy server ở port cố định và nhiều process chạy đồng thời.
- Docker container khác đã publish cùng host port.
- Management server đang dùng port bạn chọn.
- Một process không thuộc project chiếm port.

### 12.1. Phân biệt với lỗi network khác

| Thông báo | Khả năng nguyên nhân |
| --- | --- |
| `Address already in use` | Port đã được sử dụng |
| `Permission denied` | Quyền bind hoặc policy hệ điều hành |
| `Cannot assign requested address` | Địa chỉ bind không tồn tại/không phù hợp interface |
| `Connection refused` | Không có listener ở đích hoặc network path bị từ chối |
| HTTP 404 | Server đã nhận request nhưng route không tồn tại |
| Timeout | Firewall, routing, server quá tải hoặc service không phản hồi |

Đọc exception gốc trước khi đổi port. Không phải mọi lỗi kết nối đều là port conflict.

## 13. Tìm process giữ port trên Windows

Mở PowerShell:

~~~powershell
netstat -ano | findstr :8080
~~~

Ví dụ output:

~~~text
TCP    0.0.0.0:8080    0.0.0.0:0    LISTENING    14520
~~~

Cột cuối là PID. Kiểm tra process:

~~~powershell
Get-Process -Id 14520
~~~

Hoặc:

~~~powershell
tasklist /FI "PID eq 14520"
~~~

Có thể dùng cmdlet chuyên biệt:

~~~powershell
Get-NetTCPConnection -LocalPort 8080 -State Listen |
    Select-Object LocalAddress, LocalPort, State, OwningProcess
~~~

Sau đó kiểm tra process theo PID trả về.

### 13.1. Dừng process có kiểm soát

Ưu tiên dừng ứng dụng bằng cơ chế quản lý của nó:

- Stop trong IDE.
- Dừng terminal session đang chạy `bootRun`.
- Dừng service qua service manager.
- Dừng container bằng Docker.
- Dùng shutdown signal phù hợp.

Chỉ sau khi xác nhận đúng process và cần thiết mới dừng bằng:

~~~powershell
Stop-Process -Id 14520
~~~

Không mặc định dùng force kill ngay. Dừng cưỡng bức có thể bỏ qua shutdown hooks, làm gián đoạn ghi dữ liệu hoặc khiến hệ thống ngoài còn trạng thái dở dang. PID có thể được tái sử dụng, vì vậy xác minh process ngay trước thao tác.

## 14. Tìm process giữ port trên Linux/macOS

Trên Linux, dùng `ss`:

~~~bash
sudo ss -ltnp 'sport = :8080'
~~~

Dùng `lsof`:

~~~bash
sudo lsof -nP -iTCP:8080 -sTCP:LISTEN
~~~

Hoặc `fuser`:

~~~bash
sudo fuser -v 8080/tcp
~~~

Các lệnh giúp xác định process và PID. Cần quyền phù hợp để xem đầy đủ thông tin owner.

Nếu process do systemd quản lý, ưu tiên dừng service bằng systemctl. Nếu process thuộc container, dừng container. Với process chạy trong terminal, dùng cơ chế stop tương ứng.

Nếu cần gửi signal tới PID, bắt đầu bằng signal mềm:

~~~bash
kill <PID>
~~~

Chỉ dùng force signal khi đã hiểu tác động và process không thể dừng bình thường:

~~~bash
kill -9 <PID>
~~~

Không dùng PID chưa xác minh.

## 15. Dừng process cũ hay đổi port?

Dừng process đang giữ port phù hợp khi đó là instance cũ của chính ứng dụng, test process bị bỏ sót hoặc service local không còn cần chạy. Hãy xác nhận process owner và ưu tiên shutdown có tổ chức.

Đổi port phù hợp khi nhiều ứng dụng cần chạy đồng thời hoặc port hiện tại thuộc về service khác:

~~~bash
./gradlew bootRun --args='--server.port=8081'
~~~

Hoặc:

~~~bash
java -jar app.jar --server.port=8081
~~~

Không nên chọn port mới chỉ bằng cách đoán rằng nó rảnh. Trong test, port 0 thường phù hợp hơn; trong production, port allocation nên được quản lý bởi platform.

## 16. Địa chỉ bind: localhost, 127.0.0.1 và 0.0.0.0

Port đúng vẫn có thể không truy cập được từ máy khác nếu server chỉ bind loopback.

~~~yaml
server:
  address: 127.0.0.1
  port: 8080
~~~

Cấu hình này thường chỉ nhận kết nối trên loopback interface của host/container.

Để lắng nghe trên mọi network interface IPv4:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

`0.0.0.0` là wildcard bind address, không phải địa chỉ client nên gọi. Client phải dùng địa chỉ thật của host, DNS name, container/service hoặc địa chỉ được platform cấp.

Không bind mọi interface một cách vô điều kiện. Điều đó có thể làm service tiếp cận được từ nhiều mạng hơn dự kiến. Kết hợp firewall, security group, network policy, reverse proxy và Spring Security phù hợp.

Nếu cấu hình một IP không có trên host, server có thể báo `Cannot assign requested address`. Kiểm tra interfaces bằng:

Windows:

~~~powershell
Get-NetIPAddress
~~~

Linux:

~~~bash
ip address
~~~

Chỉ bind tới địa chỉ có trong network namespace mà process đang chạy.

## 17. Port trong Docker: host và container là hai lớp

Ứng dụng trong container thường bind vào port bên trong, ví dụ 8080:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
~~~

Docker publish host port 18080 tới container port 8080:

~~~bash
docker run -p 18080:8080 my-shop-app:latest
~~~

Client từ host gọi `http://localhost:18080`. Docker chuyển traffic tới container port 8080; Spring Boot bên trong container vẫn nghe port 8080.

### 17.1. EXPOSE không tự mở hoặc publish port

Dockerfile:

~~~dockerfile
EXPOSE 8080
~~~

`EXPOSE` là metadata mô tả port dự kiến sử dụng. Nó không tự mở listener, không đổi `server.port` và không publish host port. Ứng dụng vẫn phải bind port bên trong container; khi chạy container cần publish hoặc kết nối qua network phù hợp.

### 17.2. Container port conflict và host port conflict

Hai container có thể cùng nghe port 8080 trong network namespace riêng. Điều đó bình thường.

Nhưng nếu cả hai cùng publish host port 18080 trên cùng host/interface, Docker có thể báo port mapping conflict:

~~~bash
docker run -p 18080:8080 app-a
docker run -p 18080:8080 app-b
~~~

Lệnh thứ hai có thể thất bại vì host port 18080 đã được container đầu tiên sử dụng.

Cách xử lý là chọn host port khác hoặc dùng service routing phù hợp. Không nhất thiết thay `server.port` bên trong mỗi container.

### 17.3. Docker Compose

~~~yaml
services:
  shop-api:
    image: my-shop-app:latest
    ports:
      - "18080:8080"
    environment:
      SERVER_PORT: "8080"
~~~

`SERVER_PORT` cấu hình port bên trong container; mapping `18080:8080` điều khiển host-to-container forwarding.

Nếu ứng dụng đổi thành port 9090 nhưng Compose vẫn map 18080:8080, traffic sẽ được gửi tới 8080 và không tới server đang nghe 9090.

## 18. Kubernetes: container port, Service port và targetPort

Một đường đi điển hình:

~~~text
Client
  |
  v
Ingress / Gateway
  |
  v
Service port (ví dụ 80)
  |
  v
Pod targetPort (ví dụ 8080)
  |
  v
Spring Boot server.port=8080
~~~

Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: shop-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: shop-api
  template:
    metadata:
      labels:
        app: shop-api
    spec:
      containers:
        - name: app
          image: my-shop-app:latest
          ports:
            - name: http
              containerPort: 8080
          env:
            - name: SERVER_PORT
              value: "8080"
~~~

Service:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: shop-api
spec:
  selector:
    app: shop-api
  ports:
    - name: http
      port: 80
      targetPort: 8080
~~~

`containerPort` chủ yếu khai báo/documentation port của container. Service `targetPort` phải trỏ tới port mà process thực sự đang nghe.

### 18.1. Probe phải gọi đúng port/path

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 10

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 15
~~~

Endpoint probe cần được bật/cấu hình theo ứng dụng. Nếu Actuator chạy trên management port riêng, probe phải trỏ đúng port đó.

Nếu Spring Boot bind `127.0.0.1` trong Pod, kubelet hoặc client từ Pod network có thể không truy cập được qua Pod IP. Hãy cấu hình bind address phù hợp topology và kiểm soát truy cập bằng network/security policy.

## 19. Management port cũng có thể bị chiếm

Actuator có thể chạy management endpoints trên port riêng:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9001
~~~

Application server và management server cần bind các port tương ứng. Nếu port 9001 đã bị chiếm, ứng dụng có thể thất bại khi khởi tạo management web server dù port 8080 còn trống.

Kiểm tra cả `server.port`, `management.server.port`, management address, container mappings và các process khác.

## 20. Test không phụ thuộc port cố định

### 20.1. Random-port integration test

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class HealthHttpTest {

    @LocalServerPort
    int port;

    @Test
    void serverBindsToAvailablePort() {
        assertThat(port).isBetween(1, 65535);
    }
}
~~~

Có thể inject `TestRestTemplate` hoặc `WebTestClient` phù hợp để gửi HTTP request tới server đang chạy.

### 20.2. MOCK không kiểm tra TCP binding

`@SpringBootTest(webEnvironment = MOCK)` không tương đương việc khởi chạy embedded server trên TCP port thật. Nếu muốn phát hiện port conflict, hãy dùng `RANDOM_PORT` hoặc smoke test runtime.

### 20.3. Non-web test

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "spring.main.web-application-type=none"
)
class ImportJobContextTest {
}
~~~

Test này không yêu cầu server bind port. Đừng dùng nó để kết luận REST API có listener.

### 20.4. Kiểm tra context type

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class WebApplicationStartupTest {

    @Autowired
    ApplicationContext context;

    @Test
    void startsAsServletWebApplication() {
        assertThat(context)
                .isInstanceOf(ServletWebServerApplicationContext.class);
    }
}
~~~

Assertion này chỉ phù hợp nếu ứng dụng được thiết kế là Servlet application. Với WebFlux, kiểm tra context reactive tương ứng. Tránh cố định implementation detail nếu ứng dụng có nhiều mode được hỗ trợ có chủ đích.

## 21. Chẩn đoán theo log và exception

### 21.1. App báo Started nhưng không có port

Kiểm tra:

1. Có cấu hình `spring.main.web-application-type=none` không?
2. Auto-detection có chọn Non-web do runtime classpath không?
3. Có đang chạy batch/worker module thay vì API module không?
4. Có cấu hình `server.port=-1` không?
5. Có log xác nhận embedded server đã khởi động không?

Một ứng dụng non-web vẫn có thể in `Started ...` thành công.

### 21.2. Unable to start web server

Đọc root cause trong stack trace:

- Thiếu `ServletWebServerFactory` hoặc `ReactiveWebServerFactory`.
- Embedded server dependency không có trong runtime classpath.
- Cấu hình server/connector/SSL không hợp lệ.
- Port/address bind thất bại.
- Custom factory hoặc server customizer lỗi.

Đừng dừng ở exception wrapper `ApplicationContextException`. Tìm exception gốc và cấu hình liên quan.

### 21.3. Port already in use

Xác nhận process đang listen và PID/owner. Sau đó quyết định dừng instance cũ, chọn port khác, dùng port ngẫu nhiên trong test, thay host-port mapping hoặc kiểm tra management port riêng.

### 21.4. App chạy nhưng client không kết nối

Kiểm tra process, listener, host/port client, bind address, firewall/security group, Docker publish mapping, Kubernetes Service `targetPort`, TLS scheme/certificate và context path/reverse proxy prefix.

## 22. Bảng triệu chứng và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| App start nhưng không mở HTTP | Web type NONE | Kiểm tra `spring.main.web-application-type` |
| Có MVC và WebFlux nhưng chạy Servlet | Boot ưu tiên MVC khi cả hai có mặt | Xác nhận dependency và chọn reactive tường minh nếu có chủ đích |
| `No ServletWebServerFactory` | Thiếu embedded Servlet server ở runtime | Kiểm tra starter/exclusion/scope |
| `No ReactiveWebServerFactory` | Thiếu reactive server implementation | Kiểm tra WebFlux/server dependency |
| Compile được nhưng startup thiếu server | Dependency chỉ ở compile hoặc bị exclude runtime | Sửa runtime dependency configuration |
| `Port 8080 already in use` | Process khác đang listen | Xác định PID, dừng có kiểm soát hoặc đổi port |
| Port 0 nhưng client gọi localhost:0 | Nhầm port yêu cầu với port thực tế | Đọc port đã bind |
| App bind 127.0.0.1 trong container | Listener chỉ loopback | Bind interface phù hợp, kiểm tra network policy |
| Docker publish conflict | Host port đã được process/container khác dùng | Đổi host mapping hoặc dừng owner |
| Docker mapping sai | Host port map tới container port không đúng | Sửa `-p`/Compose `ports` |
| Kubernetes probe fail | Sai port/path hoặc bind address | Kiểm tra listener, management port và probe config |
| Management endpoint không lên | `management.server.port` bị chiếm | Kiểm tra port management riêng |
| `Cannot assign requested address` | Bind address không có trên host/container | Chọn địa chỉ interface hợp lệ |
| `Permission denied` | Quyền bind hoặc network policy | Kiểm tra privilege/capability |
| Local chạy, production không mở port | Profile/env/CLI/network khác | So sánh runtime config và deployment topology |

## 23. Các lệnh chẩn đoán nhanh

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency tomcat --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-netty --configuration runtimeClasspath
~~~

Maven:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-tomcat
~~~

Windows PowerShell:

~~~powershell
netstat -ano | findstr :8080
Get-NetTCPConnection -LocalPort 8080 -State Listen
Get-Process -Id <PID>
~~~

Linux:

~~~bash
ss -ltnp 'sport = :8080'
lsof -nP -iTCP:8080 -sTCP:LISTEN
~~~

Kiểm tra HTTP:

~~~bash
curl -v http://localhost:8080/actuator/health
~~~

Nếu chưa có Actuator hoặc health không exposed, gọi endpoint thực tế. `Connection refused` khác HTTP 404: 404 cho thấy một HTTP server đã nhận request nhưng không tìm thấy route phù hợp.

## 24. Bài tập thực hành

### Bài tập 1 — Nhận diện ba web types

Tạo ba ứng dụng nhỏ: Servlet MVC, WebFlux và non-web command-line. Ghi lại context type, startup log và việc có/không có HTTP listener.

### Bài tập 2 — Cố ý chọn NONE

Đặt `spring.main.web-application-type=none` trong ứng dụng có controller. Chạy ứng dụng và xác nhận process có thể startup nhưng URL HTTP không được phục vụ. Sau đó chuyển về servlet.

### Bài tập 3 — Dependency thiếu server

Tạo một project Servlet và loại embedded Tomcat khỏi runtime dependency mà chưa thêm server thay thế. Quan sát startup error. Dùng Gradle dependencyInsight hoặc Maven dependency tree để tìm nguyên nhân.

### Bài tập 4 — MVC và WebFlux cùng classpath

Thêm cả `spring-boot-starter-web` và `spring-boot-starter-webflux`. Quan sát application type mặc định. Sau đó thử `spring.main.web-application-type=reactive` và xác nhận reactive server dependency có sẵn.

### Bài tập 5 — Port conflict

Chạy ứng dụng thứ nhất trên 8080. Khởi chạy instance thứ hai cũng trên 8080. Quan sát BindException. Xác định PID của process đầu tiên và dừng nó có kiểm soát.

### Bài tập 6 — Random port test

Viết `@SpringBootTest(webEnvironment = RANDOM_PORT)` và inject `@LocalServerPort`. Chạy nhiều test hoặc nhiều project song song, xác nhận không cần cố định 8080.

### Bài tập 7 — Bind address

Chạy ứng dụng với `server.address=127.0.0.1` rồi thử truy cập từ một máy/namespace khác. Chuyển sang địa chỉ phù hợp và giải thích ảnh hưởng bảo mật của wildcard bind.

### Bài tập 8 — Docker port mapping

Chạy container với `server.port=8080` và mapping `18080:8080`. Gọi host port 18080. Sau đó cố tình map sai `18080:9090` để quan sát lỗi kết nối.

### Bài tập 9 — Management port conflict

Đặt app port 8080 và management port 9001. Chiếm 9001 bằng một listener khác rồi startup ứng dụng. Phân tích vì sao app port còn trống nhưng management server vẫn thất bại.

### Bài tập 10 — Property precedence

Đặt `server.port=8080` trong YAML, `SERVER_PORT=9090` trong environment và `--server.port=10080` trong command line. Xác định port hiệu lực, sau đó bỏ dần từng override.

### Bài tập 11 — Kubernetes probe

Tạo Deployment với `containerPort`, Service `targetPort` và readiness/liveness probes. Thay đổi port Spring Boot mà không sửa probe, quan sát trạng thái không ready rồi sửa mapping.

### Bài tập 12 — Phân loại lỗi network

So sánh Address already in use, Cannot assign requested address, Permission denied, Connection refused và HTTP 404. Ghi rõ lỗi nào thuộc bind, lỗi nào thuộc routing/client và lỗi nào chứng minh server đã nhận HTTP request.

## 25. Ghi nhớ

Khi ứng dụng Spring Boot không mở port, hãy phân biệt **web application type**, **embedded server runtime dependency** và **network binding**. `WebApplicationType.SERVLET` dùng cho Servlet stack, `REACTIVE` dùng cho reactive stack, còn `NONE` tạo ứng dụng non-web không có HTTP listener. Khi MVC và WebFlux cùng có mặt, Boot thông thường ưu tiên MVC/Servlet; dùng `WebClient` không có nghĩa server phải là reactive.

Ứng dụng cần server phải có đúng server implementation trong runtime classpath. `spring-boot-starter-web` thường cung cấp embedded Tomcat; `spring-boot-starter-webflux` thường cung cấp Reactor Netty. Nếu server bị exclude hoặc chỉ có trong compile classpath, code có thể compile nhưng không tạo được web server.

Cổng mặc định thường là 8080 và có thể thay bằng `server.port`, environment variable `SERVER_PORT` hoặc command-line `--server.port`. Khi port đã bị chiếm, xác định PID/process trước khi dừng; dùng port 0 cho test để tránh tranh chấp. Nếu server đã chạy nhưng máy khác không truy cập được, kiểm tra `server.address`, firewall và port mapping.

Trong Docker/Kubernetes, phân biệt **host port**, **container port**, **Service port** và `targetPort`. `EXPOSE` không tự mở listener; ứng dụng phải bind port bên trong container và network mapping phải trỏ tới đúng port đó. Sau mọi thay đổi, kiểm tra startup log, listener thực tế và HTTP request trên đúng artifact/môi trường.

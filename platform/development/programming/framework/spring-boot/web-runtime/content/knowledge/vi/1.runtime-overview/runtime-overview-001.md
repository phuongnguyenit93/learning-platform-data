# Web runtime là gì và vai trò của Spring Boot khi phục vụ yêu cầu HTTP

## Mục tiêu và phạm vi

Bài viết giải thích môi trường chạy của một ứng dụng web Java, cách Spring Boot khởi tạo môi trường đó và đường đi của một yêu cầu HTTP trong ứng dụng Spring Boot dùng Spring MVC (Servlet stack). Ví dụ sử dụng Java 17 trở lên và Spring Boot 3.x.

Sau khi học, bạn có thể phân biệt JVM, web server, Servlet container, Spring MVC và Spring Boot; mô tả vòng đời một request; tạo một endpoint HTTP tối giản; và nhận biết các cấu hình, lỗi vận hành thường gặp.

## 1. Web runtime là gì?

**Web runtime** là môi trường và các thành phần đang hoạt động để một ứng dụng web nhận, xử lý và trả lời yêu cầu qua mạng. Với ứng dụng Java theo Servlet stack, runtime thường bao gồm:

- **JVM:** tiến trình thực thi bytecode Java, quản lý bộ nhớ, garbage collection và các luồng.
- **Web server / Servlet container:** mở cổng mạng, tiếp nhận kết nối HTTP, phân tích request, quản lý vòng đời Servlet và Filter, rồi phân phối request đến ứng dụng. Tomcat là một Servlet container phổ biến.
- **Spring Framework / Spring MVC:** cung cấp dependency injection, ánh xạ URL đến controller, binding dữ liệu, validation, xử lý ngoại lệ và chuyển đổi request/response.
- **Mã ứng dụng:** controller, service, repository, cấu hình và các thành phần nghiệp vụ.
- **Tài nguyên vận hành:** cấu hình, logging, kết nối cơ sở dữ liệu, HTTP client, thread pool, giới hạn kết nối và công cụ quan sát hệ thống.

Các thành phần này phối hợp trong một tiến trình để phục vụ request. Với cấu hình mặc định của Spring Boot Web, Tomcat được nhúng và chạy bên trong cùng JVM với ứng dụng; thông thường không cần cài một Tomcat server riêng rồi triển khai WAR lên đó.

Cần phân biệt các khái niệm:

| Thành phần | Vai trò |
|---|---|
| JDK | Bộ công cụ phát triển Java, gồm compiler và runtime |
| JVM | Chạy bytecode và quản lý tiến trình Java |
| Tomcat | Web server kiêm Servlet container, tiếp nhận HTTP và thực thi Servlet |
| Spring MVC | Framework xử lý request theo mô hình controller và Servlet |
| Spring Boot | Tự động cấu hình, đóng gói và khởi chạy ứng dụng Spring thuận tiện hơn |
| Ứng dụng | Logic nghiệp vụ do nhóm phát triển viết |

Spring Boot không tự thay thế HTTP server hay tự xử lý toàn bộ giao thức HTTP. Nó kết nối và cấu hình các thành phần phù hợp để ứng dụng có thể chạy với ít cấu hình thủ công hơn.

### Kiến trúc tổng quát

Với ứng dụng Spring MVC dùng Tomcat nhúng, luồng xử lý điển hình như sau:

~~~mermaid
flowchart TD
    A[HTTP Client] --> B[Reverse Proxy / Load Balancer - nếu có]
    B --> C[Embedded Tomcat]
    C --> D[Servlet Filter Chain]
    D --> E[DispatcherServlet]
    E --> F[HandlerMapping]
    F --> G[HandlerAdapter]
    G --> H[Controller]
    H --> I[Service]
    I --> J[Repository / External Services]
    J --> I
    I --> H
    H --> K[HttpMessageConverter]
    K --> L[HTTP Response]
~~~

Sơ đồ mô tả đường đi phổ biến. Một request cụ thể có thể không đi qua repository hoặc dịch vụ bên ngoài; request phục vụ file tĩnh cũng có handler riêng.

## 2. Spring Boot đóng vai trò gì trong web runtime?

Khi dùng Spring Boot với **spring-boot-starter-web**, Boot cung cấp cơ chế khởi động và tự cấu hình cho ứng dụng Spring MVC.

### 2.1. Cung cấp dependency theo starter

Dependency **spring-boot-starter-web** tập hợp các thư viện cần thiết cho ứng dụng web Servlet, thường gồm Spring MVC, embedded Tomcat và các thư viện hỗ trợ chuyển đổi dữ liệu JSON như Jackson.

Nhờ starter, dự án không cần khai báo riêng từng thư viện nền tảng. Phiên bản các dependency được quản lý đồng bộ theo phiên bản Spring Boot.

### 2.2. Tự động cấu hình theo classpath

Spring Boot xem xét dependency và cấu hình hiện có để tạo các bean cần thiết. Trong ứng dụng Servlet MVC thông thường, Boot cấu hình web application context, embedded server, **DispatcherServlet**, các thành phần Spring MVC và các HTTP message converter.

Cấu hình tự động có điều kiện: khi ứng dụng bổ sung thư viện hoặc tự khai báo bean tương ứng, một số cấu hình mặc định có thể thay đổi hoặc không còn được áp dụng. Vì vậy, cần hiểu dependency nào đang có trên classpath và cấu hình nào do ứng dụng ghi đè.

### 2.3. Khởi chạy server cùng ứng dụng

Khi chạy **SpringApplication.run(...)**, Spring Boot tạo ApplicationContext, đăng ký bean, áp dụng auto-configuration và khởi tạo web server. Khi context được refresh, embedded server được khởi động và bắt đầu nhận request.

Vì server được nhúng, ứng dụng có thể chạy bằng **java -jar** trong môi trường phát triển, máy chủ hoặc container. Quy trình build và triển khai cũng đơn giản hơn vì server và ứng dụng được đóng gói cùng nhau.

### 2.4. Quản lý cấu hình và vòng đời

Boot hỗ trợ cấu hình qua **application.properties**, **application.yml**, biến môi trường và tham số dòng lệnh. Nhờ đó có thể thay đổi cổng, context path, TLS hoặc giới hạn thread theo môi trường mà không phải sửa mã nguồn.

Boot cũng tích hợp vòng đời ứng dụng, logging, xử lý lỗi mặc định và khả năng graceful shutdown của web server. Các tính năng quan sát sâu hơn như health check và metrics có thể được bổ sung bằng Spring Boot Actuator.

## 3. Ứng dụng khởi động như thế nào?

Một ứng dụng Spring Boot MVC thường đi qua các bước sau:

1. JVM khởi chạy class có hàm **main**.
2. **SpringApplication.run(...)** tạo Environment và ApplicationContext phù hợp với ứng dụng web Servlet.
3. Component scan tìm các class được đánh dấu như **@Component**, **@Service**, **@Repository** và **@Controller**.
4. Auto-configuration tạo các bean nền tảng dựa trên classpath và cấu hình.
5. Web server factory tạo embedded server (mặc định thường là Tomcat khi dùng **spring-boot-starter-web**).
6. ApplicationContext refresh; server được khởi động và bắt đầu lắng nghe trên cổng đã cấu hình.
7. Ứng dụng phát sự kiện sẵn sàng (**ApplicationReadyEvent**) sau khi quá trình khởi động hoàn tất.

**@SpringBootApplication** là annotation tổng hợp, bao gồm ba ý chính:

- **@SpringBootConfiguration:** đánh dấu class cấu hình chính.
- **@EnableAutoConfiguration:** bật cơ chế cấu hình tự động.
- **@ComponentScan:** quét component trong package hiện tại và các package con.

Đặt class main ở package gốc của ứng dụng giúp component scan tìm thấy controller và service dễ dàng. Nếu class main nằm sai package, controller có thể không được phát hiện dù mã nguồn đã tồn tại.

## 4. Một yêu cầu HTTP đi qua runtime như thế nào?

Với một request **GET /api/greetings?name=Lan**, quy trình điển hình gồm các giai đoạn sau.

### Bước 1: Kết nối mạng và tiếp nhận HTTP

Client phân giải tên miền, tạo kết nối TCP và có thể thực hiện TLS handshake. Trong môi trường triển khai thực tế, reverse proxy hoặc load balancer có thể đứng trước ứng dụng và kết thúc TLS tại đó.

Connector của Tomcat tiếp nhận kết nối, phân tích dữ liệu HTTP và tạo các đối tượng request/response của Servlet API. Cấu hình cổng, TLS, giới hạn header và kết nối ảnh hưởng đến giai đoạn này.

### Bước 2: Servlet Filter Chain

Container gọi chuỗi Servlet Filter trước khi request đến Servlet đích. Filter có thể đọc hoặc thay đổi request/response, kiểm tra quyền truy cập, ghi log, xử lý CORS hoặc thiết lập encoding.

Nếu dự án dùng Spring Security, chuỗi filter bảo mật thường được tích hợp vào giai đoạn này. Chỉ thêm **spring-boot-starter-web** không tự động bật toàn bộ cơ chế xác thực và phân quyền của Spring Security; ứng dụng phải bổ sung và cấu hình dependency bảo mật phù hợp.

### Bước 3: DispatcherServlet tiếp nhận request

**DispatcherServlet** là Front Controller của Spring MVC. Nó nhận request đã đi qua filter chain và điều phối đến handler phù hợp.

Spring MVC sử dụng các thành phần chính:

- **HandlerMapping:** tìm controller method hoặc handler phù hợp với HTTP method, URL và các điều kiện mapping.
- **HandlerAdapter:** gọi handler đã được chọn.
- **Argument resolvers:** lấy dữ liệu từ path, query parameter, header, body hoặc các nguồn khác để tạo tham số cho method.
- **HttpMessageConverter:** đọc body, ví dụ JSON thành object Java, và chuyển object trả về thành dữ liệu response.

### Bước 4: Interceptor và Controller

Spring MVC có **HandlerInterceptor**, cho phép chạy logic trước controller (**preHandle**), sau khi controller xử lý (**postHandle**) và khi request hoàn tất (**afterCompletion**). Interceptor hoạt động bên trong luồng Spring MVC, sau bước tìm handler.

Filter và interceptor có phạm vi khác nhau: Filter thuộc Servlet container và có thể bao quanh nhiều loại Servlet; interceptor gắn với handler của Spring MVC. Các yêu cầu bảo mật ở tầng HTTP thường được đặt trong Spring Security filter chain.

Controller nhận dữ liệu đã binding, kiểm tra điều kiện đầu vào và gọi service để thực hiện nghiệp vụ. Controller nên tập trung vào giao tiếp HTTP; quy tắc nghiệp vụ nên được đặt trong service để dễ kiểm thử và tái sử dụng.

### Bước 5: Xử lý nghiệp vụ

Service có thể gọi repository để truy cập cơ sở dữ liệu, gọi HTTP client đến hệ thống khác hoặc phối hợp nhiều thành phần. Những thao tác này thường ảnh hưởng trực tiếp đến thời gian xử lý request.

Trong Servlet MVC truyền thống, lời gọi đồng bộ thường giữ một worker thread trong suốt thời gian xử lý. Nếu truy vấn cơ sở dữ liệu hoặc gọi dịch vụ bên ngoài chậm, thread phục vụ request có thể bị giữ lâu.

### Bước 6: Tạo HTTP response

Giá trị trả về từ controller được Spring MVC xử lý. Với **@RestController**, object thường được chuyển thành JSON bằng **HttpMessageConverter** phù hợp, chẳng hạn Jackson.

Response được ghi về Servlet response, đi ngược qua filter chain để các filter có thể bổ sung header hoặc thực hiện xử lý sau cùng, rồi được gửi về client. HTTP status, response header và body là ba phần quan trọng cần quan sát khi debug.

### Bước 7: Xử lý ngoại lệ

Nếu controller hoặc service ném exception, Spring MVC tìm cơ chế xử lý phù hợp, ví dụ **@ExceptionHandler** hoặc **@ControllerAdvice**. Nếu không có handler phù hợp, exception có thể trở thành lỗi HTTP 500 và được xử lý bởi cơ chế lỗi mặc định của Spring Boot.

Không nên trả stack trace hoặc thông tin nội bộ cho client trong môi trường production. Hãy ghi log có ngữ cảnh ở phía server và trả về thông báo lỗi ổn định, không làm lộ dữ liệu nhạy cảm.

## 5. Tạo ứng dụng Spring Boot HTTP tối giản

Ví dụ sau tạo endpoint trả về lời chào dưới dạng JSON.

### Cấu trúc dự án

~~~text
web-runtime-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/webruntime/
        │       ├── WebRuntimeApplication.java
        │       └── GreetingController.java
        └── resources/
            └── application.yml
~~~

### 5.1. Khai báo Maven

Tạo file **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>web-runtime-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>web-runtime-demo</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

### 5.2. Class khởi động

Tạo **src/main/java/com/example/webruntime/WebRuntimeApplication.java**:

~~~java
package com.example.webruntime;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebRuntimeApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebRuntimeApplication.class, args);
    }
}
~~~

### 5.3. REST Controller

Tạo **src/main/java/com/example/webruntime/GreetingController.java**:

~~~java
package com.example.webruntime;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/greetings")
public class GreetingController {

    @GetMapping
    public GreetingResponse greet(
            @RequestParam(defaultValue = "bạn") String name) {
        return new GreetingResponse("Xin chào, " + name);
    }

    public record GreetingResponse(String message) {
    }
}
~~~

Giải thích:

- **@RestController** đánh dấu controller trả dữ liệu trực tiếp trong response body.
- **@RequestMapping("/api/greetings")** đặt URL gốc cho controller.
- **@GetMapping** ánh xạ HTTP GET đến method **greet**.
- **@RequestParam** lấy query parameter **name**; nếu client không gửi, giá trị mặc định là **bạn**.
- **GreetingResponse** là Java record. Jackson có thể serialize record thành JSON.

### 5.4. Chạy ứng dụng và gửi request

Cần có JDK 17+ và Maven. Tại thư mục chứa **pom.xml**, chạy:

~~~bash
mvn spring-boot:run
~~~

Khi server khởi động thành công, gửi request từ terminal khác:

~~~bash
curl "http://localhost:8080/api/greetings?name=Lan"
~~~

Trên Windows PowerShell, có thể gọi rõ **curl.exe**:

~~~powershell
curl.exe "http://localhost:8080/api/greetings?name=Lan"
~~~

Response body mong đợi:

~~~json
{"message":"Xin chào, Lan"}
~~~

Request này minh họa toàn bộ chuỗi: Tomcat nhận HTTP, filter chain được gọi, DispatcherServlet tìm **GreetingController**, Spring binding query parameter **name**, controller trả record và Jackson chuyển record thành JSON.

Có thể đóng gói và chạy JAR:

~~~bash
mvn clean package
java -jar target/web-runtime-demo-0.0.1-SNAPSHOT.jar
~~~

Lệnh build tạo file JAR thực thi. Khi chạy JAR, embedded server vẫn được khởi động trong JVM; không cần triển khai ứng dụng lên một Tomcat cài riêng.

## 6. Cấu hình web runtime

Spring Boot cho phép cấu hình server trong **src/main/resources/application.yml**.

Ví dụ đổi cổng, context path và một số giới hạn thread của Tomcat:

~~~yaml
server:
  port: 8081
  servlet:
    context-path: /app
  tomcat:
    threads:
      max: 200
      min-spare: 10
    accept-count: 100
~~~

Sau cấu hình này, endpoint trong ví dụ được truy cập tại:

~~~text
http://localhost:8081/app/api/greetings?name=Lan
~~~

Ý nghĩa các thuộc tính:

- **server.port:** cổng HTTP mà embedded server lắng nghe.
- **server.servlet.context-path:** tiền tố chung của URL ứng dụng.
- **server.tomcat.threads.max:** giới hạn số worker thread tối đa trong thread pool xử lý request.
- **server.tomcat.threads.min-spare:** số worker thread nhàn rỗi tối thiểu mà Tomcat cố gắng duy trì.
- **server.tomcat.accept-count:** độ dài hàng đợi kết nối chờ khi các worker thread bận, trong giới hạn và cách xử lý của connector.

Không nên tăng thread pool tùy tiện. Nếu ứng dụng bị giới hạn bởi database connection pool hoặc dịch vụ bên ngoài, tăng số thread có thể làm tăng số request chờ ở tầng phụ thuộc và khiến hệ thống quá tải nhanh hơn.

### Cấu hình theo môi trường

Các giá trị thay đổi giữa local, staging và production nên được đưa ra ngoài mã nguồn. Có thể đặt giá trị mặc định trong YAML và ghi đè bằng biến môi trường hoặc tham số khi chạy.

Ví dụ, có thể đặt **SERVER_PORT** trong môi trường triển khai để thay đổi cổng mà không sửa file cấu hình. Với mật khẩu TLS, database hoặc API key, hãy dùng secret manager hoặc biến môi trường phù hợp; không commit bí mật vào Git.

Nếu bật HTTPS trực tiếp trên embedded server, cần cấu hình chứng thư và private key hợp lệ. Trong nhiều hệ thống, TLS được kết thúc tại reverse proxy/load balancer; khi đó cần cấu hình proxy headers đúng để ứng dụng nhận biết scheme và địa chỉ gốc của request.

### Graceful shutdown

Khi triển khai, ứng dụng nên có thời gian hoàn tất các request đang chạy trước khi tiến trình dừng hẳn. Spring Boot hỗ trợ graceful shutdown cho embedded web server. Có thể cấu hình thời gian chờ theo nhu cầu:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Thời gian chờ cần phù hợp với timeout của nền tảng triển khai và thời gian xử lý request thực tế.

## 7. Servlet MVC và Reactive WebFlux

Spring Boot hỗ trợ hai mô hình web phổ biến. Chọn mô hình dựa trên cách ứng dụng xử lý I/O và kiến trúc mong muốn.

| Tiêu chí | Spring MVC (Servlet) | Spring WebFlux |
|---|---|---|
| Starter | spring-boot-starter-web | spring-boot-starter-webflux |
| Runtime mặc định phổ biến | Tomcat | Reactor Netty |
| Mô hình xử lý | Thường đồng bộ, blocking | Reactive, hỗ trợ non-blocking |
| API | Servlet API, Spring MVC | Reactive Streams, Mono, Flux |
| Phù hợp | Ứng dụng CRUD, nghiệp vụ đồng bộ, hệ sinh thái Servlet | Luồng I/O bất đồng bộ, streaming hoặc tải đồng thời lớn khi các dependency cũng non-blocking |

WebFlux không tự động làm mọi tác vụ nhanh hơn. Nếu code reactive gọi thư viện blocking, lợi ích non-blocking có thể mất đi và còn gây nghẽn event loop. Tương tự, MVC vẫn là lựa chọn phù hợp cho nhiều ứng dụng nghiệp vụ thông thường.

Hai stack có thể dùng một số annotation controller giống nhau, nhưng runtime và cách thực thi khác nhau. Nếu thêm cả **spring-boot-starter-web** và **spring-boot-starter-webflux**, Spring Boot thường ưu tiên cấu hình MVC khi cả hai cùng có mặt. Chỉ thêm cả hai khi đã hiểu rõ mục đích và hành vi auto-configuration.

## 8. Thread, kết nối và hiệu năng

Trong Servlet MVC, Tomcat thường dùng thread pool để xử lý request. Thread được tái sử dụng cho nhiều request theo thời gian; không nhất thiết tạo một thread mới cho mỗi request.

Khi một request thực hiện thao tác blocking như truy vấn JDBC hoặc gọi HTTP đồng bộ, worker thread thường phải chờ thao tác đó hoàn tất. Nếu nhiều request cùng chờ một dịch vụ chậm, thread pool có thể cạn worker thread và request mới phải đợi trong hàng đợi hoặc bị từ chối.

Khi phân tích hiệu năng, cần xem đồng thời:

- Thời gian xử lý ở controller/service và thời gian chờ database hoặc dịch vụ ngoài.
- Số worker thread đang bận, hàng đợi request và số kết nối đang mở.
- Kích thước database connection pool và giới hạn kết nối của dịch vụ phụ thuộc.
- Timeout cho HTTP client, JDBC và request tổng thể.
- Bộ nhớ, CPU, garbage collection và kích thước payload.

Đặt timeout rõ ràng cho các lời gọi bên ngoài, tránh giữ transaction hoặc lock lâu, và giới hạn tải ở các điểm phụ thuộc. Thread pool chỉ là một phần của năng lực xử lý; hiệu năng tổng thể phụ thuộc vào mắt xích chậm nhất trong request path.

## 9. Các lỗi thường gặp khi chạy ứng dụng

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Ứng dụng không khởi động, báo port đang dùng | Cổng cấu hình đã có tiến trình khác lắng nghe | Kiểm tra tiến trình chiếm cổng hoặc đổi server.port |
| HTTP 404 | Sai URL, sai context path hoặc controller chưa được scan | Kiểm tra mapping, package của class main và context path |
| HTTP 405 | URL tồn tại nhưng HTTP method không được hỗ trợ | Kiểm tra GetMapping, PostMapping và method client gửi |
| HTTP 400 | Query/path parameter không binding được hoặc dữ liệu không hợp lệ | Kiểm tra kiểu dữ liệu, định dạng body và validation |
| HTTP 415 | Content-Type không phù hợp với dữ liệu gửi lên | Kiểm tra header Content-Type và message converter |
| HTTP 500 | Exception chưa được xử lý trong ứng dụng | Xem stack trace trong log server và kiểm tra service/repository |
| Request phản hồi chậm hoặc timeout | Truy vấn DB, HTTP call, lock hoặc xử lý blocking kéo dài | Đo thời gian từng dependency, xem thread pool và đặt timeout |

Một số lệnh hữu ích khi debug:

~~~bash
# Xem status, header và body của response
curl -i "http://localhost:8080/api/greetings?name=Lan"

# Xem chi tiết quá trình kết nối và trao đổi HTTP
curl -v "http://localhost:8080/api/greetings?name=Lan"
~~~

Có thể tăng mức log tạm thời trong môi trường phát triển:

~~~yaml
logging:
  level:
    org.springframework.web: DEBUG
~~~

Không nên bật log quá chi tiết kéo dài trong production nếu chưa đánh giá tác động về hiệu năng và dữ liệu nhạy cảm. Khi cần health check hoặc metrics, có thể thêm **spring-boot-starter-actuator** và chỉ công khai các endpoint phù hợp với chính sách bảo mật.

## 10. Checklist khi triển khai

- Dùng phiên bản JDK tương thích với phiên bản Spring Boot đã chọn.
- Xác nhận starter web và web stack đang dùng đúng với kiến trúc.
- Đặt cổng, context path, TLS và proxy headers phù hợp với môi trường.
- Đặt timeout cho database và các dịch vụ bên ngoài.
- Cấu hình pool, giới hạn kết nối và tài nguyên theo năng lực thực tế.
- Ghi log có request context nhưng không làm lộ token, mật khẩu hoặc dữ liệu nhạy cảm.
- Có health check, metrics và cảnh báo cho lỗi, độ trễ, CPU, memory và thread pool.
- Kiểm tra graceful shutdown và khả năng khởi động lại trong nền tảng triển khai.
- Trả status code và lỗi nhất quán; không gửi stack trace nội bộ cho client.

## 11. Tổng kết

Web runtime là tập hợp môi trường thực thi và các thành phần nhận, xử lý, trả lời HTTP. Trong ứng dụng Spring Boot Servlet MVC, JVM chạy ứng dụng; embedded Tomcat tiếp nhận kết nối và thực thi Servlet; filter chain xử lý các bước ở tầng Servlet; **DispatcherServlet** điều phối đến controller; service thực hiện nghiệp vụ; và **HttpMessageConverter** chuyển đổi dữ liệu response.

Spring Boot giúp kết nối các thành phần này bằng starter, auto-configuration, embedded server, cấu hình bên ngoài và cơ chế quản lý vòng đời. Hiểu rõ từng lớp giúp xác định đúng nơi cần xử lý khi gặp lỗi về kết nối, mapping, bảo mật, binding dữ liệu, hiệu năng hoặc triển khai.

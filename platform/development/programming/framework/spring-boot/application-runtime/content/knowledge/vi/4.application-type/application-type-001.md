# Ba kiểu `WebApplicationType` trong Spring Boot: `NONE`, `SERVLET` và `REACTIVE`

## 1. `WebApplicationType` giải quyết vấn đề gì?

Một ứng dụng Spring Boot có thể là chương trình xử lý dữ liệu chạy xong rồi kết thúc, một dịch vụ HTTP dùng Spring MVC, hoặc một dịch vụ HTTP dùng Spring WebFlux. Cả ba đều có thể dùng dependency injection, `@SpringBootApplication`, cấu hình qua `application.yml`, bean, lifecycle event và `ApplicationRunner`. Khác biệt lớn nằm ở **loại môi trường web mà `SpringApplication` tạo ra khi khởi động**.

`org.springframework.boot.WebApplicationType` là enum có đúng ba giá trị:

- `NONE` — không tạo môi trường web và không khởi động máy chủ HTTP nhúng.
- `SERVLET` — tạo môi trường web theo **Jakarta Servlet**, thường kết hợp Spring MVC và embedded Tomcat.
- `REACTIVE` — tạo môi trường web theo **Spring WebFlux**, thường kết hợp Reactor Netty.

Đây là lựa chọn ở cấp **ứng dụng khi khởi động**. Nó ảnh hưởng đến loại `ApplicationContext`, các nhánh auto-configuration dành cho web, hạ tầng nhận HTTP request và bộ xử lý request tương ứng. Nó **không** trực tiếp cho biết ứng dụng có bao nhiêu thread, có dùng Reactor trong mọi phương thức hay không, hay một method có thực sự non-blocking hay không.

Ví dụ dễ nhớ:

- Công cụ xuất báo cáo từ cơ sở dữ liệu lúc 2 giờ sáng: cần Spring để cấu hình và tổ chức bean, không cần nhận HTTP request → thường `NONE`.
- REST API trả dữ liệu từ JPA/JDBC với mô hình Spring MVC → thường `SERVLET`.
- Gateway/streaming service có luồng I/O bất đồng bộ xuyên suốt, dùng WebFlux/Reactor → thường `REACTIVE`.

Chọn đúng kiểu để Boot tạo đúng “bộ khung chạy” cho ứng dụng, tránh khởi động web server không cần thiết và tránh hiểu nhầm giữa hai mô hình xử lý HTTP.

## 2. Bản đồ ba kiểu và các thành phần đi cùng

| Khía cạnh | `NONE` | `SERVLET` | `REACTIVE` |
| --- | --- | --- | --- |
| Có web server HTTP nhúng theo mặc định? | Không | Có, khi có server factory phù hợp | Có, khi có reactive server factory phù hợp |
| Kiểu context thường được Boot tạo | `AnnotationConfigApplicationContext` | `AnnotationConfigServletWebServerApplicationContext` | `AnnotationConfigReactiveWebServerApplicationContext` |
| Bộ khung HTTP thường gặp | Không có | Spring MVC, `DispatcherServlet` | Spring WebFlux, `DispatcherHandler` |
| Starter thường dùng | `spring-boot-starter` | `spring-boot-starter-web` | `spring-boot-starter-webflux` |
| HTTP server mặc định theo starter ở Spring Boot 3.3 | Không có | Tomcat | Reactor Netty |
| Mô hình lập trình thường gặp | `CommandLineRunner`, `ApplicationRunner`, job, consumer | `@RestController`, Spring MVC, Servlet filter | `@RestController` + `Mono`/`Flux`, router functions, `WebFilter` |
| Tình huống điển hình | CLI, batch, scheduled worker | CRUD REST, MVC, backend truyền thống | Streaming, non-blocking I/O, reactive pipeline |

Tên class context ở bảng là **mặc định thông thường** của Spring Boot, không phải lời hứa rằng mọi ứng dụng dùng một context factory tùy chỉnh đều có đúng class đó. Có thể thay `ApplicationContextFactory` khi có yêu cầu chuyên biệt.

**Quan hệ cần phân biệt:** `WebApplicationType` chọn **mô hình ứng dụng**; Tomcat, Jetty, Undertow, Reactor Netty là các **hiện thực HTTP server**. Không nên đồng nhất “`REACTIVE` = Netty bắt buộc” hoặc “`SERVLET` = chỉ có Tomcat”. WebFlux cũng có thể chạy trên các Servlet container phù hợp.

```text
                        SpringApplication
                               |
                     xác định WebApplicationType
                               |
           +-------------------+-------------------+
           |                   |                   |
         NONE                SERVLET             REACTIVE
           |                   |                   |
 ApplicationContext    ServletWebServer       ReactiveWebServer
 không có web server   ApplicationContext     ApplicationContext
           |                   |                   |
   runner / batch /      Servlet container       Reactive server
   job / consumer         + Spring MVC            + Spring WebFlux
                               |                   |
                       DispatcherServlet      DispatcherHandler
                               |                   |
                           HTTP endpoint       HTTP endpoint
```

## 3. `NONE`: Spring Boot không có môi trường web

### 3.1. Chương trình vẫn là ứng dụng Spring Boot

Với `NONE`, Boot vẫn nạp cấu hình, áp dụng auto-configuration phù hợp, tạo bean, tiêm dependency, gọi callback vòng đời và các `ApplicationRunner`/`CommandLineRunner`. Điểm khác là Boot **không dựng web application context hoặc embedded HTTP server để nhận request**.

Điều này phù hợp với:

- CLI thực hiện một nghiệp vụ rồi trả mã thoát cho hệ điều hành.
- Batch/ETL đọc dữ liệu, xử lý và ghi đích.
- Công cụ migration hoặc tác vụ quản trị nội bộ.
- Worker nhận sự kiện từ queue mà không cần endpoint HTTP.
- Scheduled application chạy theo lịch và không yêu cầu cổng web.

Một ứng dụng `NONE` **không nhất thiết tự thoát ngay**: nếu có scheduler, listener, luồng non-daemon hoặc hạ tầng background đang hoạt động, JVM có thể tiếp tục chạy. Ngược lại, nếu chỉ có runner chạy xong và không còn luồng giữ tiến trình, JVM có thể kết thúc. Cần tự xác định chính sách kết thúc, mã thoát và dọn dẹp tài nguyên của công việc.

### 3.2. Cách chọn `NONE`

Khi muốn buộc chương trình không khởi động web server dù thư viện web có trên classpath:

```properties
# src/main/resources/application.properties
spring.main.web-application-type=none
```

Hoặc trong YAML:

```yaml
spring:
  main:
    web-application-type: none
```

Hoặc cấu hình qua Java trước khi chạy:

```java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setWebApplicationType(WebApplicationType.NONE);
app.run(args);
```

Đoạn Java trên là **minh họa nằm trong method `main`** của một Spring Boot application, cần import `SpringApplication` và `WebApplicationType`. Nó không phải một file độc lập nếu đứng ngoài class.

Khi sử dụng `NONE`, đừng mong `@RestController`, `@GetMapping` hoặc endpoint HTTP Actuator hoạt động chỉ vì có các bean hay dependency tương ứng. Muốn expose HTTP health endpoint, cần thiết kế lại nhu cầu web hoặc chọn loại web phù hợp.

### 3.3. `NONE` khác `server.port=-1`

Hai cấu hình nhìn giống nhau ở chỗ không phục vụ HTTP từ cổng ứng dụng, nhưng mục đích khác nhau:

- `spring.main.web-application-type=none`: **không tạo môi trường web**; không start embedded HTTP server.
- `server.port=-1` trong ứng dụng web: Boot vẫn tạo **web application context**, nhưng không mở HTTP endpoint thông thường. Một số thử nghiệm/cấu hình cần giữ môi trường web mà không cho nhận traffic có thể dùng cách này.

Dùng `NONE` khi bản chất chương trình không phải web application. Đừng thay thế máy móc hai tùy chọn vì loại context và nhánh auto-configuration khác nhau.

## 4. `SERVLET`: web application theo Spring MVC

### 4.1. Đường đi một HTTP request

`SERVLET` dựng môi trường dựa trên Jakarta Servlet API. Với `spring-boot-starter-web`, cấu hình phổ biến nhất là Spring MVC chạy trên Tomcat nhúng.

```text
HTTP client
    |
Embedded Servlet container (ví dụ Tomcat)
    |
Servlet Filter chain
    |
DispatcherServlet (Spring MVC)
    |
HandlerMapping -> Controller / HandlerAdapter
    |
Service -> Repository / các hệ thống khác
    |
HTTP response
```

Một `@RestController` có method `@GetMapping` thường được Spring MVC đăng ký và phục vụ qua `DispatcherServlet`; trong kiểu `NONE`, không có cùng đường đi request này.

Mô hình phổ biến của Spring MVC là xử lý request bằng các thread của Servlet container. Các API đồng bộ như JDBC/JPA hay client HTTP blocking thường dễ tích hợp với mô hình này. Spring MVC cũng hỗ trợ xử lý bất đồng bộ qua `Callable`, `DeferredResult` và một số reactive return type; vì vậy **`SERVLET` không có nghĩa mọi tác vụ bắt buộc đồng bộ**.

### 4.2. Cấu hình tối thiểu và server mặc định

Trong dự án Boot 3.3 đã có plugin và dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Starter này đưa vào Spring MVC và Tomcat theo mặc định. Có thể thay Tomcat bằng Jetty hoặc Undertow bằng cách loại trừ dependency tương ứng và thêm starter server phù hợp. Việc đổi Tomcat sang Jetty **không biến** `WebApplicationType.SERVLET` thành `REACTIVE`.

Theo cách nhận biết classpath mặc định, khi Spring MVC có mặt, Boot chọn môi trường servlet. Có thể chỉ định tường minh:

```properties
spring.main.web-application-type=servlet
server.port=8080
```

Thông thường không cần đặt dòng đầu tiên nếu dự án chỉ dùng `spring-boot-starter-web`. Nếu thiếu embedded servlet server factory thích hợp nhưng vẫn ép `SERVLET`, quá trình khởi động có thể thất bại; việc chọn enum không tự tải thư viện server bị thiếu.

### 4.3. Khi nào chọn Servlet?

Phù hợp với REST CRUD, server-rendered MVC, API dựa nhiều vào thư viện blocking, đa số ứng dụng sử dụng JPA/JDBC, Spring Security filter chain theo Servlet và các tích hợp đã xây dựng quanh request/thread model. Không có quy tắc “Servlet không mở rộng được”: công suất hệ thống còn phụ thuộc database, pooling, caching, kiến trúc và cách vận hành.

## 5. `REACTIVE`: web application theo Spring WebFlux

### 5.1. Đường xử lý request

`REACTIVE` dựng môi trường web theo Spring WebFlux. Với `spring-boot-starter-webflux`, Boot 3.3 thường dùng Reactor Netty làm server nhúng. Bộ điều phối trung tâm của WebFlux là `DispatcherHandler`.

```text
HTTP client
    |
Reactive HTTP server (thường Reactor Netty)
    |
WebFilter chain
    |
DispatcherHandler (Spring WebFlux)
    |
Annotated controller / RouterFunction
    |
Publisher: Mono<T> / Flux<T>
    |
Reactive response
```

WebFlux xây dựng trên reactive streams, phù hợp với mô hình non-blocking và backpressure khi các thành phần tham gia đều phối hợp đúng. `Mono<T>` diễn tả chuỗi phát tối đa một kết quả (hoặc completion/error); `Flux<T>` diễn tả chuỗi không hoặc nhiều kết quả. Đây là **mô hình lập trình**, không phải bảo đảm mã tùy ý bên trong pipeline sẽ tự biến thành bất đồng bộ.

**Ví dụ dễ phạm lỗi:** gọi `Thread.sleep(...)`, JDBC blocking hoặc `block()` ngay trên Netty event-loop có thể làm nghẽn thread xử lý nhiều request. Phải chọn thư viện/reactive driver thích hợp, hoặc tách việc blocking sang scheduler được quản lý với giới hạn tài nguyên rõ ràng; việc chuyển scheduler không tự động biến I/O blocking thành non-blocking end-to-end.

### 5.2. Cấu hình tối thiểu

Trong một dự án Boot 3.3 đã cấu hình build:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

Khi có WebFlux mà không có Spring MVC, Boot thường chọn `REACTIVE`. Có thể cấu hình rõ ràng:

```properties
spring.main.web-application-type=reactive
server.port=8080
```

Không phải mọi ứng dụng thêm `spring-boot-starter-webflux` đều tự trở thành reactive web server. Nếu đồng thời có Spring MVC, Boot mặc định **ưu tiên `SERVLET`**; phần sau giải thích.

WebFlux không bị khóa vào Reactor Netty: Spring WebFlux có thể chạy trên các server được hỗ trợ như Tomcat/Jetty/Undertow qua adapter phù hợp. Vì thế, nhận diện kiểu ứng dụng bằng chữ “Tomcat” hoặc “Netty” xuất hiện trong log là một phép đoán dễ sai.

### 5.3. Khi nào chọn Reactive?

Có giá trị khi ứng dụng phải duy trì nhiều kết nối I/O đồng thời, streaming, SSE, proxy/gateway, kết nối lâu, hoặc khi luồng xử lý phía sau thực sự có các API reactive/non-blocking phù hợp. Cân nhắc độ phức tạp của pipeline, quan sát lỗi, backpressure và tích hợp thư viện. Một ứng dụng WebFlux sử dụng nhiều thao tác blocking vẫn có thể vận hành kém hơn dự kiến.

## 6. Spring Boot quyết định kiểu nào khi bạn không chỉ định?

`SpringApplication` tự suy luận `WebApplicationType` từ **các lớp có trên runtime classpath**. Đó không phải là phép đếm `@RestController`, không dựa vào tên package và không dựa vào ứng dụng có từng mở cổng ở lần chạy trước hay không.

Trong các trường hợp thường gặp ở Boot 3.3:

1. Có Spring MVC (`spring-webmvc`, thường qua `spring-boot-starter-web`) → chọn `SERVLET`.
2. Không có Spring MVC, có Spring WebFlux (`spring-webflux`, thường qua starter WebFlux) → chọn `REACTIVE`.
3. Không có hạ tầng web mà thuật toán cần để nhận diện → chọn `NONE`.

Ở mức triển khai, Boot kiểm tra các class chỉ dấu, bao gồm dispatcher của WebFlux/MVC và các class Servlet. Trường hợp có Servlet API nhưng không có đủ MVC/WebFlux cần xét classpath cụ thể; ba gạch đầu dòng là quy tắc thực hành cho cấu hình dự án thông thường, không phải bản chép nguyên mã nguồn của thuật toán.

### 6.1. Khi cả hai starter cùng hiện diện

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

**Kết quả mặc định: `SERVLET`.** Spring Boot ưu tiên MVC. Lý do sử dụng cả hai dependency khá phổ biến: server vẫn phục vụ bằng Spring MVC nhưng client nội bộ dùng `WebClient` của WebFlux để gọi dịch vụ khác.

Hệ quả thực tế:

- Dùng `WebClient` **không** chứng minh inbound HTTP request đang được xử lý bằng WebFlux.
- Controller trả `Mono` **không** tự động chứng minh server đang chạy với `REACTIVE`.
- Thấy `spring-webflux` trong dependency tree **không** có nghĩa `DispatcherHandler` là dispatcher inbound đang hoạt động.
- Để **buộc** ứng dụng với cả hai trên classpath chạy theo nhánh WebFlux, có thể đặt `spring.main.web-application-type=reactive`, nhưng phải kiểm tra dependency/auto-configuration, server, security và thư viện MVC đang dùng có còn phù hợp không.

Giải pháp đơn giản nhất nếu ứng dụng chỉ cần WebFlux cho inbound HTTP là **chỉ giữ starter WebFlux** và bổ sung các thư viện cần thiết riêng lẻ. Nếu ứng dụng chỉ cần Spring MVC inbound và `WebClient` outbound, giữ `SERVLET` như mong muốn và dùng WebClient làm HTTP client.

### 6.2. Sơ đồ chọn nhanh

```text
                 SpringApplication.run(...)
                            |
             Đã cấu hình type tường minh?
                   /                 \
                 Có                  Không
                  |                     |
          Dùng type được đặt    Dựa vào runtime classpath
                                        |
                             Spring MVC có mặt?
                                /          \
                              Có           Không
                               |              |
                            SERVLET       WebFlux có mặt?
                                           /       \
                                         Có        Không
                                          |           |
                                       REACTIVE      NONE
```

Sơ đồ thể hiện các trường hợp có starter thông thường. Tùy cấu hình classpath đặc biệt, Boot có những kiểm tra chỉ dấu bổ sung. Nếu type được ép nhưng dependency không đáp ứng hạ tầng tương ứng, việc khởi động vẫn có thể thất bại.

## 7. Ba cách thiết lập kiểu chạy

### 7.1. Để Boot suy luận theo dependency

Phương án thông thường, ít cấu hình nhất: chỉ chọn starter phù hợp:

```groovy
// App thuần, không HTTP:
implementation 'org.springframework.boot:spring-boot-starter'

// App Spring MVC:
implementation 'org.springframework.boot:spring-boot-starter-web'

// App Spring WebFlux:
implementation 'org.springframework.boot:spring-boot-starter-webflux'
```

Ba dòng trên là **ba phương án thay thế**, không phải lời khuyên đưa cả ba vào cùng một project.

### 7.2. Cấu hình qua `application.properties`

```properties
# Chọn đúng một kiểu theo mục đích:
spring.main.web-application-type=none
# spring.main.web-application-type=servlet
# spring.main.web-application-type=reactive
```

Thuộc tính này được Boot ánh xạ vào `SpringApplication` ở giai đoạn khởi động. Tên enum trong Java là `NONE`/`SERVLET`/`REACTIVE`; trong cấu hình thường viết chữ thường.

Có thể chuyển mode khi khởi chạy JAR thông qua tham số cấu hình, với điều kiện thư viện cần thiết đã có trong JAR:

```bash
java -jar build/libs/my-app.jar --spring.main.web-application-type=none
```

Lệnh trên giả định `my-app.jar` là **tên tệp đã được build thực sự**; thay bằng đường dẫn JAR của dự án.

### 7.3. Đặt bằng Java

```java
package com.example.webtype;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ForcedNoneApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(ForcedNoneApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.run(args);
    }
}
```

Đây là **file hoàn chỉnh** tại `src/main/java/com/example/webtype/ForcedNoneApplication.java`, chạy trong project có `spring-boot-starter`. Nếu sau này muốn chọn Servlet/Reactive bằng API, đổi đối số enum và bổ sung dependency web/server tương ứng.

Một lựa chọn cùng ý nghĩa là `new SpringApplicationBuilder(...).web(WebApplicationType.NONE).run(args)`. Đặt giá trị trong Java khi cần quyết định từ code; nếu muốn vận hành thay đổi theo môi trường, cấu hình externalized thường dễ quản lý hơn. Không nên đồng thời đặt các giá trị mâu thuẫn ở nhiều nơi rồi đoán nơi nào có ưu tiên cao nhất; hãy kiểm tra kết quả runtime.

## 8. Thực hành một ứng dụng quan sát mode thực tế

Ví dụ sau dùng **một class Java** hoạt động với cả ba cấu hình. Nó in ra tên `ApplicationContext` và cho phép đối chiếu mode suy ra ở runtime. Nội dung không tạo HTTP controller; vì vậy dùng web server ở mode `SERVLET`/`REACTIVE` sẽ mở máy chủ, nhưng chưa có endpoint nghiệp vụ để gọi.

**File:** `src/main/java/com/example/webtype/WebTypeDemoApplication.java`

```java
package com.example.webtype;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class WebTypeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebTypeDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner reportContext(ApplicationContext context) {
        return args -> {
            System.out.println("CONTEXT_CLASS="
                    + context.getClass().getSimpleName());
            System.out.println("RUNNER_EXECUTED=true");
        };
    }
}
```

Giải thích:

- `SpringApplication.run` dựng và refresh context phù hợp.
- `@Bean` tạo một `ApplicationRunner` chung cho cả ba kiểu, thực thi sau mốc `ApplicationStartedEvent` và trước `ApplicationReadyEvent`.
- `getClass().getSimpleName()` quan sát **context thực tế** đã dựng. Không suy đoán mode từ annotation `@SpringBootApplication`.
- Chương trình in hai dòng nêu trên; các log khởi động của Spring Boot có thể xuất hiện trước, sau hoặc xen kẽ.

Giả sử đã có dự án **Spring Boot 3.3.x với Java 17+**, plugin Gradle Boot và dependency management đúng phiên bản. Lần lượt chạy ba thí nghiệm **trong ba cấu hình dependency riêng**, sử dụng cùng class ở trên:

**Thí nghiệm A: `NONE`**

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Chạy:

```bash
./gradlew bootRun
```

Các dòng cần thấy:

```text
CONTEXT_CLASS=AnnotationConfigApplicationContext
RUNNER_EXECUTED=true
```

Không có embedded HTTP server để nhận kết nối ở cổng 8080. Nếu không có tác vụ nền giữ JVM, chương trình có thể kết thúc khi startup/runner hoàn tất.

**Thí nghiệm B: `SERVLET`**

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Chạy lại `./gradlew bootRun`. Các dòng cần thấy:

```text
CONTEXT_CLASS=AnnotationConfigServletWebServerApplicationContext
RUNNER_EXECUTED=true
```

Boot thường khởi động Tomcat trên port 8080 (nếu cổng rảnh và không thay cấu hình). Do **chưa viết controller**, một request đến đường dẫn không tồn tại thường nhận HTTP 404; mã 404 không chứng minh web server không chạy. Hãy tắt instance giữa hai thí nghiệm để tránh trùng cổng.

**Thí nghiệm C: `REACTIVE`**

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

Chạy lại `./gradlew bootRun`. Các dòng cần thấy:

```text
CONTEXT_CLASS=AnnotationConfigReactiveWebServerApplicationContext
RUNNER_EXECUTED=true
```

Boot thường dùng Reactor Netty để mở HTTP port 8080. Nếu bạn vẫn để `spring-boot-starter-web` cùng tồn tại trong dependencies, kết quả có thể quay về context servlet vì MVC được ưu tiên. Trước khi so sánh ba thí nghiệm, kiểm tra rằng dependency đã được thay như hướng dẫn và đã dừng tiến trình cũ.

Trên Windows, thay `./gradlew bootRun` bằng `gradlew.bat bootRun` hoặc `.\gradlew.bat bootRun` trong PowerShell. Với dự án Maven, chạy bằng `./mvnw spring-boot:run` nếu đã có Maven Wrapper.

### 8.1. Thêm endpoint HTTP cho thí nghiệm B/C

Chỉ khi sử dụng starter MVC hoặc WebFlux, tạo file thứ hai `src/main/java/com/example/webtype/PingController.java`:

```java
package com.example.webtype;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
```

Chạy mode `SERVLET` hoặc `REACTIVE` rồi gọi:

```bash
curl -i http://localhost:8080/ping
```

Khi server hoạt động và không có cấu hình ngăn request, HTTP status dự kiến là `200 OK`, body:

```text
pong
```

Controller annotation ở trên được cả Spring MVC và WebFlux hỗ trợ, nhưng đường dispatch phía dưới khác nhau. **Không thêm file `PingController.java` vào thí nghiệm `NONE` chỉ dùng starter cơ bản**: dependency đó không có các annotation web nên Java sẽ không biên dịch nếu bạn giữ import `org.springframework.web.bind.annotation`.

## 9. Cách quan sát và chẩn đoán khi mode không như mong đợi

### 9.1. Quan sát context và dependency

Kiểm tra class được in bởi `WebTypeDemoApplication`. Với cấu hình mặc định, nó thể hiện context tương ứng với mode trong bảng đầu bài. Khi có context factory tùy chỉnh, kiểm tra thêm code tạo context thay vì suy luận duy nhất từ tên class.

Liệt kê runtime dependencies:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Tìm `spring-webmvc`, `spring-webflux`, Servlet API và các HTTP server starter; đừng nhìn duy nhất dòng dependency mà bạn tự khai báo vì thư viện transitively được kéo vào cũng có thể ảnh hưởng phát hiện mode.

Lệnh Gradle này giả định project có Gradle Wrapper và cấu hình Java/Boot tương ứng.

### 9.2. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có khả năng | Hướng xử lý |
| --- | --- | --- |
| Thêm WebFlux nhưng Boot vẫn tạo servlet context | `spring-webmvc`/starter web cùng có mặt | Kiểm tra dependency tree; bỏ MVC nếu không cần hoặc cấu hình reactive tường minh. |
| `WebClient` dùng được nhưng endpoint vẫn qua `DispatcherServlet` | `WebClient` là HTTP **client**, không quyết định inbound server | Phân biệt client reactive với mode của server. |
| Đặt `spring.main.web-application-type=none` rồi request HTTP không vào | Đã tắt hạ tầng web theo thiết kế | Chọn `SERVLET`/`REACTIVE` nếu thật sự cần endpoint. |
| Ép `SERVLET`/`REACTIVE` nhưng startup lỗi thiếu web server factory | Classpath không có server factory phù hợp hoặc cấu hình loại trừ sai | Bổ sung starter/server phù hợp và kiểm tra nguyên nhân gốc trong startup logs. |
| WebFlux chậm khi tải cao dù có `Mono`/`Flux` | Gọi JDBC, `Thread.sleep` hay `block()` trên event loop | Kiểm tra blocking call, scheduler, driver và thời gian chờ. |
| `server.port=-1` mà vẫn thấy web context | Thuộc tính này chỉ tắt HTTP endpoints, không đổi mode | Dùng `spring.main.web-application-type=none` nếu cần non-web context. |
| Chương trình `NONE` thoát ngay sau runner | Không còn công việc hoặc thread giữ JVM | Nếu là CLI: hành vi có thể đúng; nếu là worker: khởi tạo vòng xử lý/listener đúng lifecycle. |
| REST endpoint trả 404 trong ví dụ chưa có controller | Server đã mở nhưng không có route phù hợp | Thêm `PingController` cho mode web và gọi đúng `/ping`. |
| Test dùng `@SpringBootTest` khác mode production | Test có thể tự chọn `webEnvironment` hoặc property riêng | Xác minh cấu hình test và mode production độc lập. |

### 9.3. Phân biệt `WebApplicationType` và `SpringBootTest.WebEnvironment`

`WebApplicationType` là loại ứng dụng được `SpringApplication` sử dụng. Trong kiểm thử, `@SpringBootTest(webEnvironment = ...)` lại dùng enum **khác** (`SpringBootTest.WebEnvironment`) với các giá trị như `MOCK`, `RANDOM_PORT`, `DEFINED_PORT`, `NONE`. Không gán hai enum cho nhau hoặc cho rằng `RANDOM_PORT` là một `WebApplicationType` mới.

Khi cả MVC và WebFlux có mặt, tài liệu Spring Boot hướng dẫn dùng:

```java
@SpringBootTest(properties = "spring.main.web-application-type=reactive")
class WebFluxApplicationTests {
    // Kiểm thử với reactive web application context
}
```

Đây là **đoạn minh họa annotation trong lớp test**, không phải file test hoàn chỉnh; dự án cần dependency test và các import JUnit/SpringBootTest thích hợp. Mục tiêu là buộc kiểu ứng dụng trong test, vì Boot vốn ưu tiên MVC khi cả hai cùng hiện diện.

## 10. Quy tắc lựa chọn trong thiết kế

Đặt câu hỏi theo thứ tự:

1. **Ứng dụng có cần nhận HTTP request không?** Nếu không, `NONE` là điểm xuất phát hợp lý. Nếu có, chọn một trong hai web mode.
2. **Các thành phần xử lý phía sau có mang tính blocking và được thiết kế cho Servlet không?** Nếu chủ yếu dùng JDBC/JPA và API đồng bộ thông thường, `SERVLET` thường đơn giản, dễ tích hợp.
3. **Có lợi ích rõ ràng từ non-blocking I/O/reactive streams không?** Nếu dịch vụ streaming, số lượng kết nối đồng thời cao và hệ thống phía sau hỗ trợ reactive API, xem xét `REACTIVE`.
4. **Có thật sự cần hai web starter cùng lúc không?** Thường chỉ cần một. Nếu là MVC server dùng `WebClient` outbound, để MVC làm mode inbound là hợp lý.
5. **Cần override bằng cấu hình không?** Cấu hình tường minh khi mong muốn khác suy luận classpath; nếu không, để Boot tự nhận biết và kiểm tra bằng runtime context.

Đừng chọn `REACTIVE` chỉ vì từ “reactive” nghe hiện đại hơn, và cũng đừng cho rằng `SERVLET` không thể xử lý tải lớn. Đánh giá bằng đặc tính I/O, khả năng vận hành, tính phù hợp của thư viện và phép đo thực tế.

## 11. Câu hỏi tự kiểm tra

**1. Một ứng dụng có `spring-boot-starter-web` và `spring-boot-starter-webflux`. Không đặt cấu hình mode. Boot chọn gì?** — `SERVLET` trong cấu hình thông thường, vì Spring MVC có ưu tiên cao hơn WebFlux.

**2. Một CLI có `@SpringBootApplication` và `ApplicationRunner` có nhất thiết phải mở HTTP server?** — Không. Với `NONE`, lifecycle bean và runner vẫn hoạt động mà không dựng web server.

**3. Nếu thấy `Mono<String>` trong method của controller, có đủ kết luận app dùng `REACTIVE` không?** — Không. Cần kiểm tra context và hệ thống dispatch; Spring MVC cũng có thể tương tác với reactive types.

**4. Muốn tắt HTTP server hoàn toàn mà vẫn dùng Boot, thuộc tính nào diễn tả ý định rõ nhất?** — `spring.main.web-application-type=none`. `server.port=-1` giữ web application context nên mang ý nghĩa khác.

**5. WebFlux có bắt buộc dùng Reactor Netty không?** — Không. Netty là lựa chọn mặc định của starter WebFlux trong Boot 3.3, còn reactive stack có các server adapter khác.

**6. Chuyển enum từ `SERVLET` sang `REACTIVE` liệu tự sửa mọi thư viện blocking?** — Không. Kiểu context, auto-configuration và dispatcher thay đổi, nhưng code blocking vẫn blocking; phải kiểm tra driver, client và cách dùng scheduler.

**7. Điểm quan sát đáng tin hơn tên starter là gì?** — Runtime context thực tế, bean/web server được tạo, auto-configuration và dependency tree.

## 12. Tài liệu chính thức để đối chiếu

- [Spring Boot 3.3 — SpringApplication và lựa chọn Web Environment](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html).
- [Spring Boot 3.3 — Embedded Web Servers, server mặc định và tắt web server](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html).
- [Spring Boot 3.3 — Detecting Web Application Type trong test](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html).
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html).
- [Spring Framework — Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html).

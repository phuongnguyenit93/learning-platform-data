# Trường hợp đồng thời có Spring MVC và Spring WebFlux trong Spring Boot

## 1. Vấn đề cần hiểu

Spring Boot có thể sử dụng **Spring Web MVC** hoặc **Spring WebFlux** để xử lý HTTP request. Hai framework này cùng thuộc Spring Framework nhưng hoạt động theo những mô hình khác nhau:

- **Spring MVC** dựa trên **Servlet API**, sử dụng **DispatcherServlet**, servlet filters và servlet container như Tomcat. Phong cách phổ biến là controller đồng bộ, với khả năng hỗ trợ xử lý bất đồng bộ khi cần.
- **Spring WebFlux** là reactive web framework, sử dụng **DispatcherHandler**, Reactive Streams và các kiểu **Mono**/**Flux** của Reactor. Nó được thiết kế để hỗ trợ xử lý không chặn cùng các cơ chế backpressure trong reactive pipeline.
- **WebClient** là HTTP client có API reactive nằm trong module Spring WebFlux. Một ứng dụng MVC vẫn có thể dùng WebClient để gọi API khác.

**Kết luận cốt lõi:** khi Spring MVC và Spring WebFlux **cùng có mặt trên classpath**, Spring Boot **ưu tiên khởi chạy ứng dụng dạng SERVLET/Spring MVC theo mặc định**. Sự có mặt của thư viện WebFlux không đồng nghĩa Boot sẽ tự chuyển HTTP server sang reactive hoặc đồng thời mở hai framework để xử lý cùng một request.

Đây là hành vi có chủ đích của Spring Boot: nhiều hệ thống MVC cần sử dụng WebClient nhưng vẫn muốn giữ nguyên cách nhận và xử lý HTTP request của MVC.

## 2. WebApplicationType được suy ra như thế nào?

**SpringApplication** phát hiện các thư viện web trên classpath để xác định kiểu ứng dụng khi không có chỉ định rõ ràng.

| Các thành phần có mặt | Kiểu Boot chọn mặc định | Server-side framework |
| --- | --- | --- |
| Spring MVC, không có WebFlux | **SERVLET** | Spring MVC |
| WebFlux, không có Spring MVC | **REACTIVE** | Spring WebFlux |
| **Spring MVC và WebFlux cùng có** | **SERVLET** | **Spring MVC thắng** |
| Không có cả hai | **NONE** | Non-web |
| Có cả hai và chủ động ép REACTIVE | **REACTIVE** | WebFlux nếu có server runtime tương thích |

Sơ đồ nhận diện mặc định:

~~~text
                   SpringApplication
                           |
                  Phát hiện classpath
                           |
              +------------+------------+
              | Có Spring MVC?          |
              +------------+------------+
                 | Có             | Không
                 v                v
             SERVLET       Có Spring WebFlux?
          Spring MVC          | Có       | Không
                              v          v
                           REACTIVE     NONE
                           WebFlux     Non-web
~~~

Ở mode SERVLET, Boot thường tạo **AnnotationConfigServletWebServerApplicationContext** và cấu hình Spring MVC. Ở mode REACTIVE, Boot thường tạo **AnnotationConfigReactiveWebServerApplicationContext** và cấu hình WebFlux. Các ApplicationContext này thể hiện hai kiểu runtime khác nhau.

Lưu ý: bảng mô tả hành vi **mặc định**. Có thể chủ động ghi đè bằng **SpringApplication.setWebApplicationType(WebApplicationType.REACTIVE)**, **SpringApplicationBuilder.web(WebApplicationType.REACTIVE)** hoặc property **spring.main.web-application-type=reactive**. Phải có đủ dependency và cấu hình tương ứng mới khởi chạy thành công.

## 3. Khi có cả hai, server và HTTP client đảm nhiệm hai việc khác nhau

Một ứng dụng phổ biến có cấu trúc:

~~~text
HTTP client gọi endpoint của ứng dụng
                  |
                  v
    Embedded servlet server (Tomcat)
                  |
                  v
      Spring MVC DispatcherServlet
                  |
                  v
             Controller
                  |
                  v
               Service
                  |
               WebClient
                  |
                  v
        HTTP API bên ngoài
~~~

Ở mô hình này:

1. Request **đi vào server** được Spring MVC nhận và dispatch.
2. Khi nghiệp vụ cần gọi hệ thống khác, service có thể dùng **WebClient** như một outbound HTTP client.
3. Boot vẫn chọn **SERVLET**; việc dùng WebClient không biến server thành WebFlux.
4. WebClient có thể dùng API không chặn, nhưng chuyện application thread có bị chặn hay không phụ thuộc cách gọi, ví dụ có sử dụng **block()** hay không.
5. Cấu hình servlet filters, MVC interceptors, xử lý exception và security của MVC vẫn được áp dụng cho server MVC.

Đừng nhầm **có dependency WebFlux** với **đang phục vụ request bằng WebFlux**. Đây là hai thuộc tính khác nhau của ứng dụng.

## 4. Ví dụ đầy đủ: hai starter cùng tồn tại, MVC được ưu tiên

### 4.1. Chuẩn bị dự án

Dùng Spring Initializr tạo một dự án Maven, Java 17 trở lên, Spring Boot **3.3.x**, package **com.example.demo**. Chọn hai dependency:

~~~xml
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
~~~

Đây là **phần dependencies** trong POM hoàn chỉnh do Initializr tạo; không phải một file pom.xml độc lập. Boot parent/BOM sẽ quản lý phiên bản thư viện tương thích. Starter Web thông thường cung cấp Spring MVC và Tomcat; Starter WebFlux cung cấp reactive web classes, WebClient và hạ tầng Reactor tương ứng.

### 4.2. Chương trình Java chạy được

Tạo file **src/main/java/com/example/demo/MixedWebApplication.java**:

~~~java
package com.example.demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ApplicationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

@SpringBootApplication
@RestController
public class MixedWebApplication {

    private final ApplicationContext context;
    private final WebClient.Builder webClientBuilder;

    public MixedWebApplication(
            ApplicationContext context,
            WebClient.Builder webClientBuilder) {
        this.context = context;
        this.webClientBuilder = webClientBuilder;
    }

    public static void main(String[] args) {
        SpringApplication.run(MixedWebApplication.class, args);
    }

    @GetMapping("/stack")
    public Map<String, Boolean> stack() {
        return Map.of(
                "servletContext",
                context instanceof ServletWebServerApplicationContext,
                "webClientAvailable",
                webClientBuilder != null);
    }
}
~~~

**Phân tích:**

- **@SpringBootApplication** khai báo nguồn cấu hình của ứng dụng.
- **@RestController** và **@GetMapping** khai báo endpoint. Hai annotation này được dùng trong cả MVC và WebFlux; chỉ nhìn annotation không đủ biết web stack.
- **ApplicationContext** là context đang chạy, được inject để xác nhận loại ứng dụng.
- **ServletWebServerApplicationContext** là kiểu servlet context trong Spring Boot 3.x. Vì cả hai starter đều có, Boot ưu tiên SERVLET, nên kiểm tra **instanceof** cho kết quả **true**.
- **WebClient.Builder** được Boot cung cấp qua auto-configuration khi các điều kiện tương ứng thỏa mãn. Injection thành công cho thấy server MVC vẫn sử dụng được WebClient.
- Endpoint không gọi network bên ngoài; chỉ kiểm tra hai đặc điểm runtime để bài tập dễ tái hiện.

### 4.3. Chạy và quan sát

Ở thư mục gốc dự án:

~~~bash
# Linux/macOS
./mvnw spring-boot:run

# Windows:
# .\mvnw.cmd spring-boot:run
~~~

Mở terminal khác:

~~~bash
curl http://localhost:8080/stack
~~~

Response body dự kiến:

~~~json
{
  "servletContext": true,
  "webClientAvailable": true
}
~~~

Thứ tự khóa, khoảng trắng và logging thực tế có thể khác. Hai giá trị boolean trong response mới là điều cần quan sát. Startup log thường có thông tin Tomcat được khởi chạy theo cấu hình mặc định của starter-web.

**Giải thích kết quả:** true ở **servletContext** chứng minh đây là servlet web application; true ở **webClientAvailable** cho thấy component reactive client vẫn có sẵn. Hai kết quả hoàn toàn không mâu thuẫn.

Nếu cổng mặc định đang bị chiếm, cấu hình **server.port** sang cổng khác và thay URL khi gọi curl. Đóng ứng dụng bằng **Ctrl+C** trong terminal.

## 5. Khi muốn WebFlux làm server dù classpath vẫn có MVC

### 5.1. Chọn REACTIVE bằng mã Java

Trong ứng dụng ví dụ ở mục 4, có thể **thay phương thức main** bằng đoạn sau:

~~~java
public static void main(String[] args) {
    new org.springframework.boot.builder.SpringApplicationBuilder(
            MixedWebApplication.class)
            .web(org.springframework.boot.WebApplicationType.REACTIVE)
            .run(args);
}
~~~

Đoạn này minh họa thay thế **một phương thức**, không phải một chương trình độc lập. **SpringApplicationBuilder.web(...)** yêu cầu Boot chọn reactive web application context. Khi các dependency hiện có phù hợp, Boot sẽ cấu hình WebFlux server runtime; với starter-webflux mặc định, server reactive phổ biến là Reactor Netty.

Nếu dùng chính class của ví dụ trên, **@GetMapping** vẫn là một annotation HTTP handler hợp lệ trong WebFlux. Sau khi ứng dụng khởi động theo REACTIVE, giá trị **servletContext** dự kiến đổi thành **false**, vì ApplicationContext giờ không phải ServletWebServerApplicationContext.

Chọn REACTIVE không tự chuyển servlet filters, MVC interceptors, MVC-specific argument resolvers hay cấu hình security servlet sang reactive equivalents. Mọi thành phần gắn chặt với Servlet phải được kiểm tra khi chuyển đổi.

### 5.2. Chọn từ cấu hình runtime

Thay vì sửa main, đặt:

~~~properties
spring.main.web-application-type=reactive
~~~

trong file **src/main/resources/application.properties** hoặc truyền tham số khi chạy executable JAR:

~~~bash
# Sau khi chạy ./mvnw package
java -jar target/ten-file-thuc-te.jar --spring.main.web-application-type=reactive
~~~

Thay **ten-file-thuc-te.jar** bằng tên JAR được build thực tế. Có thể chỉ định **servlet**, **reactive**, hoặc **none** theo nhu cầu và theo các dependency có sẵn.

Nếu mục tiêu của dự án là làm server WebFlux thuần túy, cách dễ duy trì hơn thường là chỉ khai báo **spring-boot-starter-webflux** và không thêm **spring-boot-starter-web** nếu không cần. Khi đó Boot sẽ tự nhận diện REACTIVE.

## 6. WebFlux và Spring MVC khác nhau ở server pipeline

| Tiêu chí | MVC / SERVLET | WebFlux / REACTIVE |
| --- | --- | --- |
| HTTP dispatcher | **DispatcherServlet** | **DispatcherHandler** |
| Cơ sở lập trình | Servlet API | Reactive Streams, non-blocking API |
| Controller | @Controller / @RestController | @Controller / @RestController |
| Functional routes | **org.springframework.web.servlet.function** | **org.springframework.web.reactive.function.server** |
| Web configuration | **WebMvcConfigurer** | **WebFluxConfigurer** |
| Interception/filter | Servlet Filter, HandlerInterceptor | WebFilter và reactive filter chain |
| Server security | SecurityFilterChain (servlet) | SecurityWebFilterChain (reactive) |
| Server phổ biến | Tomcat, Jetty | Reactor Netty và adapter tương thích khác |
| HTTP client WebClient | Có thể sử dụng | Có thể sử dụng |
| Mục tiêu | Dịch vụ servlet thông thường, blocking code được quản lý bằng threads | Pipeline thiết kế theo reactive, tránh chặn event-loop |

**WebFlux không đồng nghĩa duy nhất với Netty**. WebFlux có thể chạy trên một số runtime khác, kể cả adapter tương thích Servlet. Không thể xác định framework chỉ từ tên server hoặc port; cần xem loại ApplicationContext/auto-configuration và đường dispatch thực tế.

### Controller MVC trả Mono có làm server thành WebFlux không?

**Không.** Spring MVC có khả năng điều hợp một số reactive return types vào cơ chế async Servlet. Ví dụ một method đặt trong MVC **@RestController** có thể có dạng:

~~~java
@GetMapping("/hello")
public reactor.core.publisher.Mono<String> hello() {
    return reactor.core.publisher.Mono.just("Hello");
}
~~~

Đây là **method minh họa**, cần đặt trong controller phù hợp. Kết quả trả về Mono không làm biến mất DispatcherServlet. Điều này chỉ thể hiện rằng MVC đang chấp nhận một reactive type trong signature.

Tương tự, khi một controller WebFlux dùng **@GetMapping**, annotation đó không có nghĩa server đang là MVC. Tên annotation giống nhau nhưng dispatcher/context phụ thuộc runtime type đã chọn.

### WebClient có bảo đảm non-blocking từ đầu đến cuối không?

**Không.** WebClient xây dựng pipeline reactive, nhưng code có thể biến thao tác thành blocking nếu gọi **block()**:

~~~java
String body = webClient.get()
        .uri("https://example.com/data")
        .retrieve()
        .bodyToMono(String.class)
        .block();
~~~

Đoạn trên minh họa cú pháp client (biến **webClient** và endpoint là giả định), không phải một chương trình chạy độc lập. **block()** chặn thread gọi đến khi có dữ liệu hoặc lỗi. Trong MVC, nó có thể chiếm servlet request thread. Trong WebFlux, nếu gọi trực tiếp trên event-loop thread thì việc blocking có thể gây lỗi hoặc giảm khả năng xử lý đồng thời.

Một server WebFlux dùng JDBC blocking, gọi file I/O blocking hoặc xử lý tác vụ CPU nặng trên event-loop vẫn cần xem xét scheduler và giới hạn tài nguyên. **Chọn REACTIVE không tự động làm mọi dependency trở thành non-blocking**.

## 7. Những cấu hình dễ bị nhầm khi có cả hai thư viện

### 7.1. Đừng dùng @EnableWebFlux làm công tắc thay thế web type

**@EnableWebFlux** là annotation cấu hình framework. Nó không phải cách chính xác nhất để chọn loại ApplicationContext khi bootstrap Spring Boot. Nó cũng có thể làm thay đổi cách Boot tự cấu hình WebFlux vì các thành phần framework được ứng dụng tự cung cấp.

Tương tự, **@EnableWebMvc** tác động cấu hình MVC và có thể làm thay đổi auto-configuration mặc định. Nên ưu tiên web type do Boot suy ra, hoặc đặt tường minh bằng **spring.main.web-application-type** / **SpringApplicationBuilder.web(...)** khi chủ động cần loại khác.

### 7.2. Đừng nhầm hai loại RouterFunction

Spring MVC functional endpoint dùng package **org.springframework.web.servlet.function**. WebFlux functional endpoint dùng package **org.springframework.web.reactive.function.server**. Cả hai đều có các tên như **RouterFunction** và **ServerResponse**, nhưng type thuộc hai package và hai HTTP pipelines khác nhau.

Vì vậy trước khi copy ví dụ **RouterFunction** từ tài liệu, cần xem import và server stack mà ứng dụng thực sự chạy.

### 7.3. Không tự sao chép security, filters và config giữa hai stack

Trong MVC, **jakarta.servlet.Filter**, **HandlerInterceptor** và **SecurityFilterChain** phục vụ mô hình servlet. Trong WebFlux, **WebFilter** và **SecurityWebFilterChain** nằm trong reactive stack. Hai mô hình bảo mật có các đối tượng runtime khác nhau.

Việc ứng dụng có sẵn cả hai dependency không khiến một servlet filter tự trở thành reactive WebFilter hoặc ngược lại. Nếu thay web type, hãy kiểm thử authentication, authorization, error handling, CORS, validation và tracing theo đúng pipeline đang dùng.

## 8. Cách chẩn đoán khi runtime không giống kỳ vọng

**Bước 1: xem dependency tree.**

~~~bash
./mvnw dependency:tree
~~~

Kiểm tra **spring-webmvc**, **spring-webflux** và starter nào đưa chúng vào (kể cả transitive dependency). Đừng chỉ nhìn những dependency trực tiếp trong POM.

**Bước 2: kiểm tra ApplicationContext.** Ở Boot 3.x, **ServletWebServerApplicationContext** là dấu hiệu SERVLET. Context reactive thường thuộc nhóm **ReactiveWebServerApplicationContext**. Đây là bằng chứng đáng tin hơn việc thấy một class WebClient hay Flux trong code.

**Bước 3: kiểm tra startup logs** để biết web server, cổng, và lỗi auto-configuration. Với starter-web thông thường, Tomcat log là dấu hiệu phù hợp với MVC mặc định; tuy nhiên một số server có thể hoạt động với nhiều adapter, nên cần kết hợp bước 2.

**Bước 4: xem Condition Evaluation Report** bằng chế độ **--debug** hoặc qua Spring Boot Actuator endpoint **conditions** nếu project đã cài dependency và cấu hình bảo vệ phù hợp. Tập trung vào auto-configurations về MVC, WebFlux và loại ứng dụng web.

**Bước 5: kiểm tra test context.** Nếu ứng dụng có cả hai starter, **@SpringBootTest** cũng có thể chọn MVC theo classpath. Khi bài test chủ đích kiểm tra reactive runtime, có thể chỉ định:

~~~java
@SpringBootTest(
        properties = "spring.main.web-application-type=reactive")
class ReactiveApplicationTests {
    // Thêm test method và import/dependency tương ứng.
}
~~~

Đây là khung minh họa, chưa phải test chạy độc lập. Nó cần import **org.springframework.boot.test.context.SpringBootTest**, dependency **spring-boot-starter-test**, test methods và các điều kiện môi trường phù hợp. Không nên đặt REACTIVE trong test nếu application production vẫn dự kiến là MVC, trừ khi đang chủ động kiểm tra cấu hình đó.

## 9. Khi nào giữ MVC + WebClient, khi nào chọn WebFlux?

### Giữ MVC và dùng WebClient khi

- Ứng dụng đã dựa trên MVC, servlet filters, JDBC/JPA hoặc thư viện blocking.
- Nhu cầu chính là **gọi HTTP outbound** bằng client API reactive.
- Nhóm phát triển không có yêu cầu chuyển toàn bộ request pipeline sang reactive.
- Có kế hoạch quản lý timeout, kết nối, số request đồng thời và cách gọi **block()** phù hợp.

Khi gọi HTTP đồng bộ thuần túy, cũng có thể đánh giá **RestClient** của Spring Framework hiện đại nếu phù hợp với stack hiện hữu.

### Chọn WebFlux làm server khi

- Ứng dụng được thiết kế theo reactive pipeline có chủ đích.
- Các dependency quan trọng có API non-blocking hoặc có giải pháp xử lý blocking riêng.
- Nhóm cần tận dụng cơ chế async/reactive để xử lý nhiều I/O-bound request theo cách hợp lý.
- Đã kiểm thử backpressure, cancellation, event-loop blocking, security và observability phù hợp.

Không nên coi WebFlux là cách mặc định để đạt hiệu năng cao hơn trong mọi trường hợp. Workload và các dependency quyết định hiệu quả thật.

### Nếu MVC xuất hiện ngoài dự kiến

Đầu tiên xác định dependency nào đưa **spring-webmvc** vào classpath. Nếu không cần MVC, có thể loại dependency đó; nếu cần cả hai, đặt **REACTIVE** tường minh và kiểm thử toàn bộ cấu hình. Cả hai phương án đều phải dựa trên yêu cầu thật và tình trạng hệ thống.

## 10. Sai lầm thường gặp

1. **“Thêm spring-boot-starter-webflux là Boot sẽ ưu tiên WebFlux.”** Sai khi MVC cùng hiện diện: MVC thắng mặc định.
2. **“Hai starter làm xuất hiện hai HTTP servers.”** Không phải hành vi auto-configuration thông thường; Boot chọn một web application type.
3. **“WebClient chỉ hoạt động trong server WebFlux.”** Sai: MVC sử dụng WebClient hợp lệ.
4. **“Controller trả Mono thì server là reactive.”** Chưa đủ kết luận; MVC cũng có thể xử lý reactive return type.
5. **“WebFlux lúc nào cũng phải chạy Netty.”** Sai: WebFlux có nhiều server adapters.
6. **“Đổi sang REACTIVE tự động xử lý mọi servlet-specific component.”** Sai: filters, interceptors, security và code blocking cần đánh giá lại.
7. **“@EnableWebFlux chính là thay thế cho setWebApplicationType.”** Sai về trách nhiệm của hai cơ chế.
8. **“Có đồng thời MVC và WebFlux luôn là cấu hình xấu.”** Không đúng: MVC server dùng WebClient là trường hợp được Spring Boot hỗ trợ có chủ đích.

## 11. Bài tập và đáp án gợi ý

**Bài 1.** Một ứng dụng có starter-web và starter-webflux, main chỉ gọi **SpringApplication.run**. Boot chọn loại nào? Vì sao?

**Bài 2.** Một Spring MVC controller inject **WebClient.Builder**. Request đầu vào đi qua DispatcherServlet hay DispatcherHandler theo mặc định?

**Bài 3.** Một đội muốn web server thực sự chạy WebFlux nhưng dependency tree có cả Spring MVC. Nêu hai phương án và điểm cần kiểm chứng.

**Bài 4.** Trả về **Mono<String>** từ controller có phải bằng chứng toàn bộ stack non-blocking không?

**Bài 5.** Sau khi đổi SERVLET thành REACTIVE, vì sao cấu hình filter/security của ứng dụng phải được kiểm tra lại?

**Đáp án:** (1) SERVLET/Spring MVC vì Boot ưu tiên MVC khi cả hai hiện diện; (2) DispatcherServlet theo default; (3) bỏ dependency MVC không cần thiết hoặc ép REACTIVE khi đủ server runtime, đồng thời test các component; (4) không, MVC có hỗ trợ một số reactive return types và code có thể blocking; (5) hai framework có HTTP filters/security pipeline khác nhau.

## 12. Ghi nhớ và tài liệu chính thức

**Mặc định MVC được ưu tiên nếu MVC và WebFlux cùng xuất hiện. WebClient có thể được dùng trong ứng dụng MVC. Chọn WebFlux server đòi hỏi cấu hình REACTIVE hoặc classpath không có MVC, cùng sự tương thích của các thành phần runtime.**

Tài liệu nên đối chiếu với phiên bản Spring Boot của dự án:

- Spring Boot Reference — Reactive Web Applications (giải thích ưu tiên MVC khi có hai starter): https://docs.spring.io/spring-boot/reference/web/reactive.html
- Spring Boot Reference — SpringApplication, Web Environment và WebApplicationType: https://docs.spring.io/spring-boot/reference/features/spring-application.html
- Spring Framework Reference — Spring Web MVC: https://docs.spring.io/spring-framework/reference/web/webmvc.html
- Spring Framework Reference — Spring WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html

Trong Spring Boot major versions khác nhau, một số package, starter, auto-configuration và default dependency có thể thay đổi. Ví dụ Java ở trên được viết theo Spring Boot 3.3.x và Java 17+; hãy đối chiếu JavaDoc đúng phiên bản khi chuyển sang dự án khác.
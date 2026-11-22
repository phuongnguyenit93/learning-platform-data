# Thiết lập spring.main.web-application-type để chọn web stack tường minh

Trong Spring Boot, thuộc tính **spring.main.web-application-type** cho biết ứng dụng phải khởi tạo theo kiểu web nào: **servlet**, **reactive** hoặc **none**. Thông thường Spring Boot tự xác định kiểu ứng dụng từ các thư viện có trên classpath. Tuy nhiên, khi một dự án có nhiều starter, vừa dùng MVC vừa dùng WebClient, chạy tác vụ nền bằng cùng mã nguồn hoặc cần điều khiển môi trường triển khai, việc chỉ định tường minh giúp tránh hiểu nhầm về kiểu ApplicationContext và web server sẽ được tạo.

Cần phân biệt hai quyết định: **chọn loại ứng dụng** và **cung cấp các dependency phù hợp cho loại đó**. Đặt thuộc tính này không cài thêm Spring MVC, WebFlux, Tomcat hay Reactor Netty; cũng không tự chuyển đoạn mã chặn luồng thành mã non-blocking.

## 1. Ba giá trị và tác động khi khởi động

| Giá trị | Mô hình khởi động | Thích hợp khi |
|---|---|---|
| **servlet** | Khởi tạo ApplicationContext cho Servlet, thông thường dùng Spring MVC và embedded Servlet web server như Tomcat | REST API dùng Spring MVC, ứng dụng web theo mô hình request/response truyền thống |
| **reactive** | Khởi tạo ApplicationContext cho Reactive Web, thường dùng Spring WebFlux và reactive web server như Reactor Netty | API hoặc gateway thiết kế xử lý I/O theo mô hình reactive/non-blocking |
| **none** | Khởi tạo ApplicationContext không phải web, không mở HTTP web server | Công cụ dòng lệnh, import dữ liệu, tác vụ batch, chương trình worker không nhận HTTP request |

Các tên enum tương ứng trong Java là **WebApplicationType.SERVLET**, **WebApplicationType.REACTIVE** và **WebApplicationType.NONE**. Trong application.properties hoặc application.yml có thể dùng các giá trị chữ thường như servlet, reactive, none.

### Servlet

Với Servlet stack, Spring Boot có thể tự cấu hình DispatcherServlet, bộ lọc Servlet và embedded Tomcat khi các dependency Spring MVC/Servlet tương ứng có mặt. Một HTTP request thường được xử lý bởi worker thread của Servlet server. Các API Servlet như HttpServletRequest, Filter hoặc HandlerInterceptor thuộc ngữ cảnh này.

### Reactive

Với Reactive stack, Spring Boot có thể tự cấu hình WebFlux DispatcherHandler, WebFilter và reactive web server khi có đầy đủ dependency cần thiết. I/O không chặn cho phép phục vụ nhiều kết nối với số event-loop thread tương đối nhỏ. Mô hình này không mặc định biến việc gọi JDBC, thư viện blocking hoặc Thread.sleep thành non-blocking.

Chế độ reactive không đồng nghĩa chắc chắn phải dùng Reactor Netty: server được chọn còn phụ thuộc thư viện và cấu hình. Reactor Netty là lựa chọn phổ biến của spring-boot-starter-webflux.

### None

Với none, Spring Boot vẫn tạo ApplicationContext, nạp bean, chạy dependency injection, ApplicationRunner và CommandLineRunner; nhưng không tạo HTTP web server. Những bean được định nghĩa bằng @RestController vẫn có thể tồn tại nếu được quét, song ứng dụng sẽ không phục vụ endpoint HTTP chỉ nhờ có các bean ấy. Các tác vụ nền, scheduler hoặc kết nối tới hệ thống khác vẫn có thể hoạt động nếu được cấu hình.

**none không phải server.port=0**: cổng 0 yêu cầu hệ điều hành chọn một cổng TCP tự do cho web server, trong khi none không khởi động web server.

## 2. Spring Boot chọn mặc định như thế nào?

Khi không được cấu hình tường minh, SpringApplication suy luận WebApplicationType dựa trên những class web có sẵn khi khởi động:

1. Nếu **chỉ có WebFlux** phù hợp với web stack, ứng dụng thường được suy luận là **reactive**.
2. Nếu **Spring MVC và WebFlux cùng có mặt**, Spring MVC được ưu tiên và mặc định là **servlet**.
3. Nếu có hệ Servlet phù hợp và không bị điều kiện reactive-only chi phối, kiểu được suy luận là **servlet**.
4. Nếu không có hạ tầng web phù hợp, ứng dụng được suy luận là **none**.

Đây là hành vi suy luận từ classpath, không phải lựa chọn dựa trên tên package của controller hay kiểu dữ liệu được trả về từ một phương thức.

Ví dụ thường gặp:

| Dependency chính | Kiểu mặc định thường gặp | Điểm cần nhớ |
|---|---|---|
| spring-boot-starter-web | servlet | Starter mang theo Spring MVC và embedded Tomcat theo mặc định |
| spring-boot-starter-webflux | reactive | Starter mang theo WebFlux và Reactor Netty theo mặc định |
| Có cả starter-web và starter-webflux | servlet | Có WebClient không làm toàn bộ server chuyển sang reactive |
| Chỉ có spring-boot-starter thông thường, không có web stack | none | Ứng dụng có thể chạy tác vụ không cần HTTP server |

Nếu một ứng dụng Spring MVC cần gọi API bên ngoài bằng WebClient, việc có thêm WebFlux trên classpath **không có nghĩa bắt buộc chuyển sang reactive**. Spring MVC vẫn có thể là web stack của server, còn WebClient chỉ là HTTP client được sử dụng bên trong ứng dụng.

## 3. Đặt trong application.yml hoặc application.properties

### Chỉ định Servlet

~~~yaml
spring:
  main:
    web-application-type: servlet
~~~

Tương đương trong application.properties:

~~~properties
spring.main.web-application-type=servlet
~~~

Một dự án dùng servlet nên có dependency phù hợp, ví dụ Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Thiết lập này phù hợp với REST controller dùng Spring MVC, Servlet filter, HandlerInterceptor hoặc Spring Security dạng servlet. Nó không tự thêm dependency nếu dự án thiếu starter-web.

### Chỉ định Reactive

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

Dependency thường dùng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Khi thật sự xây dựng WebFlux server, nên loại bỏ dependency Spring MVC không cần thiết để giảm mơ hồ về auto-configuration và tránh đem các thành phần Servlet vào cấu trúc Reactive. Đặt reactive tường minh có thể hữu ích khi cần tránh suy luận mặc định do classpath có thêm thành phần MVC, nhưng chỉ định này **không** chuyển một MVC HandlerInterceptor thành WebFilter hoặc biến một controller đồng bộ thành pipeline reactive đúng nghĩa.

### Chỉ định không khởi động web server

~~~yaml
spring:
  main:
    web-application-type: none
~~~

Đây là lựa chọn rõ ràng khi cùng mã nguồn có cả dependency web nhưng một lần chạy chỉ làm import dữ liệu hoặc chạy worker. Những bean không cần HTTP vẫn được khởi tạo theo cấu hình ứng dụng. Nếu một cấu hình đòi hỏi ServletWebServerApplicationContext hoặc bean chỉ có trong chế độ web, ứng dụng có thể gặp lỗi khi đặt none; cần kiểm tra sự phụ thuộc này.

Chỉ nên khai báo một giá trị hiệu lực cho từng lần chạy. Không thể đồng thời chạy hai loại ApplicationContext servlet và reactive trong cùng một SpringApplication chỉ bằng cách ghi nhiều giá trị cho thuộc tính.

## 4. Ghi đè theo môi trường và lệnh khởi động

Cấu hình có thể đặt trong application.yml, file profile hoặc truyền từ bên ngoài. Ví dụ application.yml mặc định:

~~~yaml
spring:
  main:
    web-application-type: servlet
~~~

Khi cần chạy không có web server, có thể truyền tham số chương trình:

~~~bash
java -jar build/libs/my-app.jar --spring.main.web-application-type=none
~~~

Tên file JAR phải thay bằng artifact thực tế. Với Gradle Spring Boot plugin:

~~~bash
./gradlew bootRun --args="--spring.main.web-application-type=none"
~~~

Trên Windows có thể dùng gradlew.bat thay cho ./gradlew. Hai lệnh trên là những cách khởi chạy thay thế cho nhau, không phải thực hiện tuần tự trong cùng một lần chạy.

Có thể dùng biến môi trường theo quy tắc relaxed binding của Spring Boot:

~~~bash
SPRING_MAIN_WEB_APPLICATION_TYPE=reactive
~~~

Dòng trên biểu diễn tên và giá trị biến môi trường; cách gán cụ thể phụ thuộc shell, Docker, Kubernetes hoặc hệ thống triển khai. Ví dụ cấu hình qua application-reactive.yml:

~~~yaml
spring:
  config:
    activate:
      on-profile: reactive

  main:
    web-application-type: reactive
~~~

Khi kích hoạt profile reactive, thuộc tính tương ứng có thể có hiệu lực. Một tham số command-line thường có độ ưu tiên cao hơn giá trị trong application.yml theo thứ tự nguồn cấu hình mặc định; cần kiểm tra cấu hình thực tế nếu có nhiều nguồn ghi đè.

Vì kiểu ứng dụng quyết định ApplicationContext và web server ngay trong giai đoạn khởi động, **thay đổi cấu hình này sau khi ứng dụng đã chạy không chuyển stack tại chỗ**. Cần khởi động lại ứng dụng với giá trị mong muốn.

## 5. Chọn kiểu ứng dụng bằng Java API

Nếu muốn lựa chọn ngay trong mã khởi động, SpringApplication có phương thức setWebApplicationType.

Ví dụ chương trình Spring Boot **không khởi động HTTP server**, file src/main/java/demo/BatchModeApplication.java:

~~~java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class BatchModeApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BatchModeApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }

    @Bean
    CommandLineRunner runBatch() {
        return args -> System.out.println("BATCH_DONE");
    }
}
~~~

Ví dụ yêu cầu dự án Spring Boot có dependency spring-boot-starter và entry point được cấu hình để chạy BatchModeApplication. Khi Spring Boot khởi động thành công, bên cạnh log của framework, lệnh println in ra một dòng:

~~~text
BATCH_DONE
~~~

Để chạy trong dự án Gradle đã cấu hình Spring Boot và main class tương ứng:

~~~bash
./gradlew bootRun
~~~

Giá trị được chỉ định trong ví dụ qua Java API là **NONE**. Nếu cần servlet hoặc reactive bằng API này, dùng WebApplicationType.SERVLET hoặc WebApplicationType.REACTIVE và đảm bảo các dependency server phù hợp. Tránh đặt giá trị mâu thuẫn giữa chương trình khởi động và file/biến môi trường. Các nguồn cấu hình được SpringApplication bind trong quá trình startup có thể ảnh hưởng đến giá trị hiệu lực; nên giữ một nguồn quyết định rõ ràng cho mỗi cách triển khai.

SpringApplicationBuilder cũng hỗ trợ khai báo kiểu ứng dụng ở bước dựng ứng dụng. Chọn giữa cấu hình ngoài và cấu hình trong mã theo yêu cầu vận hành; cấu hình ngoài thường thuận tiện khi chạy cùng artifact dưới nhiều chế độ.

## 6. Chọn chế độ theo trường hợp sử dụng

### Trường hợp A: API REST Spring MVC bình thường

Ứng dụng khai báo spring-boot-starter-web và dùng @RestController trả DTO, dùng Servlet Filter hoặc Spring MVC HandlerInterceptor. Giữ mặc định servlet thường là đủ; có thể khai báo servlet nếu muốn hợp đồng triển khai hiển thị rõ và phát hiện thay đổi classpath.

### Trường hợp B: API server thật sự dùng WebFlux

Ứng dụng sử dụng WebFlux, Publisher/Mono/Flux hoặc reactive functional endpoints, WebFilter và non-blocking I/O. Dùng spring-boot-starter-webflux, tránh kéo thêm starter-web nếu không cần và có thể đặt reactive tường minh. Đồng thời kiểm tra tài nguyên downstream: dùng JDBC blocking trên event loop có thể phá vỡ lợi ích reactive dù ApplicationContext đã là reactive.

### Trường hợp C: Spring MVC gọi dịch vụ ngoài bằng WebClient

Ứng dụng dùng starter-web và WebClient từ thư viện WebFlux để gọi API khác. Mặc định vẫn là servlet vì MVC hiện diện. Đặt reactive chỉ để “dùng được WebClient” là không cần thiết; WebClient không yêu cầu server phải là WebFlux.

### Trường hợp D: Chạy batch hoặc lệnh quản trị từ cùng artifact

Ứng dụng có dependency web nhưng một tác vụ chỉ cần ApplicationRunner/CommandLineRunner để chuyển dữ liệu. Dùng none để tránh tạo HTTP listener. Nếu chương trình phải thoát sau khi chạy, còn cần kiểm tra non-daemon thread, scheduler, client và vòng đời bean. none chỉ loại bỏ web server, không bảo đảm mọi tác vụ nền tự dừng.

### Trường hợp E: Chạy nhiều biến thể deployment

Một source code có thể được build thành artifact dùng cho API servlet và cho batch worker. Có thể cấu hình servlet ở deployment web và none ở deployment worker. Tuy nhiên, cần kiểm tra bean nào chỉ hợp lệ khi ứng dụng có Servlet context, bean nào tạo background job và bean nào cần tắt trong từng môi trường. Web application type không tự quyết định bean nghiệp vụ nào phải hoạt động.

## 7. Mối quan hệ với auto-configuration và điều kiện bean

Spring Boot kích hoạt nhiều auto-configuration dựa trên **cả** kiểu ứng dụng lẫn classpath và các bean hiện có. Thuộc tính spring.main.web-application-type tác động đến việc dựng ApplicationContext và các cấu hình phụ thuộc loại ứng dụng.

Ví dụ, một auto-configuration hoặc bean mang điều kiện Servlet sẽ chỉ được xét khi ngữ cảnh thực sự là Servlet; điều kiện Reactive tương ứng dành cho Reactive Web. Điều kiện không phải web sẽ có ý nghĩa trong ngữ cảnh none. Vì vậy, đổi giá trị này có thể làm một số bean được tạo hoặc không được tạo, kể cả khi các file Java của dự án không đổi.

Về hệ xử lý request, hai stack không dùng cùng mọi lớp tích hợp:

| Thành phần | Servlet MVC | Reactive WebFlux |
|---|---|---|
| HTTP server integration | Servlet web server | Reactive web server |
| Request dispatcher | DispatcherServlet | DispatcherHandler |
| Request API điển hình | HttpServletRequest | ServerWebExchange |
| Filter web | Servlet Filter | WebFilter |
| Security filter chain | SecurityFilterChain | SecurityWebFilterChain |
| Xử lý async/non-blocking | Cần dùng API/phương án phù hợp với Servlet MVC | Reactor và reactive stream là mô hình cốt lõi |

Nếu một dự án có security, filter, exception handler, request binding hoặc tài liệu API được viết theo MVC, hãy kiểm tra tương thích trước khi đổi sang reactive. Việc đổi ApplicationContext không tự viết lại các cấu hình đó.

Tương tự, **@EnableWebMvc** và **@EnableWebFlux** là các annotation tùy biến cấu hình web tương ứng, không nên dùng thay cho việc lựa chọn WebApplicationType hoặc để bù dependency server bị thiếu.

## 8. Kiểm chứng chế độ thực tế khi chạy

Đừng chỉ nhìn một dòng cấu hình rồi kết luận; cần kiểm tra hành vi khởi động và loại ApplicationContext hiệu lực.

1. **Xem startup log:** với embedded Tomcat thường thấy log Tomcat đã khởi động; với Reactor Netty thường thấy log Netty; với none sẽ không có web server được khởi tạo do SpringApplication.
2. **Kiểm tra endpoint:** servlet và reactive có thể phục vụ HTTP nếu server và mapping được cấu hình. none không mở HTTP server.
3. **Kiểm tra loại ApplicationContext:** các context Servlet thường triển khai ServletWebServerApplicationContext; reactive thường triển khai ReactiveWebServerApplicationContext; none thường dùng AnnotationConfigApplicationContext nếu không tùy biến factory.
4. **Quan sát auto-configuration report khi cần:** chạy với debug để tìm điều kiện cấu hình nào đã match hoặc không match.

Ví dụ để bật debug trong lần chạy:

~~~bash
java -jar build/libs/my-app.jar --debug
~~~

Không suy luận chắc chắn “reactive” chỉ vì ứng dụng có dependency reactor-core, một phương thức trả Mono hoặc đang dùng WebClient. Điều quyết định là kiểu web application hiệu lực và hệ cấu hình web/server thực sự được kích hoạt.

Lưu ý: kiểu context cụ thể có thể được tùy biến; kiểm tra interface loại web context và log thực tế chính xác hơn so sánh cứng một class name.

## 9. Lỗi thường gặp và cách khắc phục

### 9.1. Đã thêm WebFlux nhưng ứng dụng vẫn chạy MVC

**Biểu hiện:** có starter-web và starter-webflux, request vẫn qua DispatcherServlet hoặc log cho thấy Tomcat Servlet server.

**Nguyên nhân:** khi MVC và WebFlux cùng có mặt, Spring Boot mặc định chọn servlet.

**Cách xử lý:** nếu chỉ cần WebClient, giữ servlet. Nếu muốn reactive server, kiểm tra lý do starter-web xuất hiện, bỏ dependency MVC không cần thiết, dùng starter-webflux và chỉ định reactive khi phù hợp. Kiểm tra lại Security, Filter và các controller trước khi chạy.

### 9.2. Đặt reactive nhưng ứng dụng không khởi động được

**Biểu hiện:** lỗi auto-configuration liên quan ReactiveWebServerFactory hoặc không có reactive web server phù hợp, hoặc bean được cấu hình cho servlet không tồn tại.

**Nguyên nhân khả dĩ:** thiếu dependency reactive server, bean cấu hình lệ thuộc Servlet context, hoặc sự phối hợp starter không tương thích với thiết kế.

**Cách xử lý:** kiểm tra dependency tree; xác nhận có starter-webflux và reactive web server tương thích; xem root cause đầy đủ trong startup log; tách cấu hình Servlet-only khỏi cấu hình reactive. Không chỉ che lỗi bằng cách tắt auto-configuration ngẫu nhiên.

### 9.3. Đặt none nhưng controller không nhận request

**Biểu hiện:** request HTTP không có nơi nhận hoặc kết nối bị từ chối.

**Nguyên nhân:** none không khởi tạo web server. @RestController không đủ để tạo HTTP listener.

**Cách xử lý:** dùng servlet hoặc reactive nếu ứng dụng thực sự cần HTTP; giữ none nếu chủ đích là batch/worker. Kiểm tra probes, load balancer và kỳ vọng cổng của môi trường triển khai.

### 9.4. Cấu hình servlet nhưng không có Servlet web server

**Biểu hiện:** Spring Boot báo không tạo được ServletWebServerFactory hoặc không khởi động được web server.

**Nguyên nhân khả dĩ:** chỉ đặt servlet trong config nhưng thiếu starter và embedded server cần thiết, hoặc server đã bị exclude.

**Cách xử lý:** khai báo đúng starter-web hoặc server dependency được hỗ trợ; xem dependency tree và cấu hình exclude. Property này không thể thay thế jar thiếu trên classpath.

### 9.5. Bật reactive để cải thiện hiệu năng nhưng độ trễ vẫn cao

**Biểu hiện:** request chậm khi gọi cơ sở dữ liệu hoặc API ngoài.

**Nguyên nhân:** JDBC blocking, gọi HTTP đồng bộ, thao tác CPU nặng hoặc chờ tài nguyên khác vẫn có thể chiếm thread hay làm nghẽn event loop.

**Cách xử lý:** đo metrics latency/thread/pool, dùng các driver và client non-blocking khi cần, giới hạn concurrency và chuyển blocking work khỏi event loop. Chỉ định kiểu reactive đơn thuần không bảo đảm cải thiện throughput.

### 9.6. Cấu hình profile và tham số chạy cho kết quả khác nhau

**Biểu hiện:** application.yml ghi servlet nhưng ứng dụng khởi động none hoặc reactive.

**Nguyên nhân khả dĩ:** profile-specific file, biến môi trường hoặc tham số command-line đang ghi đè giá trị.

**Cách xử lý:** kiểm tra active profiles, các nguồn cấu hình và lệnh chạy thực tế. Chọn một nguồn cấu hình rõ ràng cho từng deployment và ghi nhận giá trị hiệu lực khi startup.

## 10. Phân biệt với những cấu hình gần giống

- **server.port** chọn cổng cho web server đang chạy; không quyết định Servlet, Reactive hay None.
- **spring.main.lazy-initialization** thay đổi chiến lược khởi tạo bean; không thay web stack.
- **spring.threads.virtual.enabled** ảnh hưởng cách Spring Boot sử dụng virtual threads ở những thành phần được hỗ trợ; không thay lựa chọn Servlet hay Reactive.
- **spring.profiles.active** chọn nhóm cấu hình đang có hiệu lực; có thể gián tiếp tác động đến web application type nếu file profile khai báo thuộc tính đó.
- **server.shutdown** và các thuộc tính graceful shutdown ảnh hưởng quá trình dừng web server; không phải công tắc chọn web application type.
- **management.endpoints.web.exposure.include** cấu hình Actuator endpoint được expose qua HTTP khi có hạ tầng web phù hợp; không tự tạo web server cho none.

Không dùng các thuộc tính trên để giải quyết nhầm lẫn về chế độ web.

## 11. Quy trình quyết định trước khi chỉ định tường minh

1. Xác định ứng dụng là HTTP API MVC, HTTP API WebFlux hay chỉ là tiến trình không phục vụ HTTP.
2. Kiểm tra dependency thực tế; nếu đồng thời có starter-web và starter-webflux, xác định starter nào cần cho **server** và thư viện nào chỉ để làm **client**.
3. Chọn servlet, reactive hoặc none phù hợp với code và luồng xử lý; ưu tiên loại bỏ dependency dư thừa trước khi ép kiểu để che mâu thuẫn.
4. Đặt spring.main.web-application-type trong một nguồn cấu hình rõ ràng, hoặc chọn bằng SpringApplication API nếu ứng dụng thực sự cần điều khiển ở code.
5. Khởi động và kiểm tra log, ApplicationContext, HTTP endpoint, auto-configuration cùng dependency được tải.
6. Chạy thử luồng nghiệp vụ và các thành phần phụ thuộc web stack như security, filter, exception handler, scheduler và actuator.
7. Kiểm tra behavior sau deployment: cổng, readiness probe, batch lifecycle và thông số tài nguyên.

**Nguyên tắc:** để Spring Boot tự suy luận khi classpath thể hiện rõ thiết kế; chọn tường minh khi cần làm rõ một chế độ triển khai hoặc điều khiển một trường hợp đặc biệt. Giá trị web-application-type phải nhất quán với dependency và mã nguồn; nó quyết định loại ứng dụng được khởi động, không tự xây dựng lại web stack cho bạn.
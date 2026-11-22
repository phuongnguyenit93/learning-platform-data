# Đối chiếu các loại ApplicationContext tương ứng với kiểu ứng dụng Spring Boot

## 1. Từ kiểu ứng dụng đến ApplicationContext: hiểu đúng mối quan hệ

Khi chương trình gọi `SpringApplication.run(...)`, Spring Boot không chỉ quét bean và tạo đối tượng theo `@Configuration`, `@Component` hay `@Bean`. Nó còn phải quyết định **ứng dụng có vận hành như một máy chủ web hay không và nếu có thì dùng mô hình web nào**. Quyết định này ảnh hưởng trực tiếp đến **loại `ApplicationContext` cụ thể** được tạo ra.

Trong Spring Framework, `ApplicationContext` là giao diện chứa các thành phần quản lý bean, cấu hình, sự kiện và tài nguyên. `ConfigurableApplicationContext` bổ sung thao tác liên quan đến vòng đời và cấu hình context. Spring Boot sử dụng các triển khai khác nhau của `ApplicationContext` để hỗ trợ ứng dụng thông thường, web theo Servlet và web phản ứng (reactive).

Cần tách ba lớp khái niệm:

1. **`WebApplicationType`**: enum mô tả kiểu ứng dụng Spring Boot, gồm `NONE`, `SERVLET` và `REACTIVE`.
2. **`ApplicationContext`**: đối tượng Spring quản lý bean, dependency injection, cấu hình, sự kiện và vòng đời của ứng dụng. Đây là phần lõi có ở cả ba kiểu.
3. **Web server**: thành phần có thể lắng nghe HTTP, chẳng hạn Tomcat, Jetty hoặc Reactor Netty tùy mô hình và các dependency đã cấu hình. Web server **không đồng nghĩa** với `ApplicationContext`; một số context chịu trách nhiệm tạo và quản lý server đó.

Điều quan trọng nhất: **`WebApplicationType` là lựa chọn mô hình chạy; tên lớp `ApplicationContext` là một biểu hiện cụ thể của lựa chọn ấy**. Không nên suy ngược kiểu ứng dụng chỉ từ việc dự án có một thư viện xử lý HTTP hoặc có kiểu trả về `Mono`.

## 2. Bảng ánh xạ mặc định của Spring Boot 3.3

Trong luồng khởi chạy mặc định, với `SpringApplication` chưa bị thay đổi `ApplicationContextFactory`, ta có:

| `WebApplicationType` | `ApplicationContext` thường được tạo | Mục đích |
| --- | --- | --- |
| `NONE` | `AnnotationConfigApplicationContext` | Ứng dụng không có web server nhúng; vẫn có Spring container và bean |
| `SERVLET` | `AnnotationConfigServletWebServerApplicationContext` | Ứng dụng HTTP theo Servlet API, thường cùng Spring MVC |
| `REACTIVE` | `AnnotationConfigReactiveWebServerApplicationContext` | Ứng dụng web theo Spring WebFlux/reactive, có web server phù hợp |

Tên đầy đủ của các lớp trong Spring Boot 3.3:

```text
NONE:
  org.springframework.context.annotation
      .AnnotationConfigApplicationContext

SERVLET:
  org.springframework.boot.web.servlet.context
      .AnnotationConfigServletWebServerApplicationContext

REACTIVE:
  org.springframework.boot.web.reactive.context
      .AnnotationConfigReactiveWebServerApplicationContext
```

Hai lớp web của Spring Boot triển khai `WebServerApplicationContext`. Chúng có trách nhiệm phối hợp với `WebServerFactory` thích hợp để tạo, khởi động và quản lý vòng đời máy chủ HTTP nhúng.

Đây là **ánh xạ mặc định**, không phải khẳng định rằng mọi ứng dụng Spring trên thế giới chỉ có đúng ba loại context. Spring Framework còn nhiều triển khai khác; Spring Boot cho phép tùy chỉnh cách tạo context, và các kiểm thử có thể dùng bối cảnh khác với ứng dụng sản xuất.

Sơ đồ quan hệ khái niệm:

```text
                        SpringApplication
                              |
                      chọn WebApplicationType
                              |
         +--------------------+--------------------+
         |                    |                    |
        NONE                SERVLET              REACTIVE
         |                    |                    |
 AnnotationConfig-   AnnotationConfig-    AnnotationConfig-
 ApplicationContext  ServletWebServer-    ReactiveWebServer-
                     ApplicationContext   ApplicationContext
         |                    |                    |
    Quản lý bean         Quản lý bean         Quản lý bean
    và vòng đời          + Servlet web       + Reactive web
                             server               server
```

Tất cả vẫn dùng cùng các nền tảng như `ApplicationContext`, `BeanFactory`, injection qua constructor, `Environment` và các sự kiện vòng đời. Điểm khác biệt là **những khả năng web đi kèm**.

## 3. NONE: AnnotationConfigApplicationContext

### Bản chất

`WebApplicationType.NONE` tương ứng với ứng dụng Spring không khởi động web server nhúng theo cơ chế tự động của Spring Boot. Lớp context mặc định là `AnnotationConfigApplicationContext`, thuộc Spring Framework.

Nó vẫn có thể:

- Nạp bean từ `@Configuration`, `@ComponentScan`, `@Service` và `@Bean`.
- Thực hiện dependency injection, đọc `Environment` và cấu hình ngoài.
- Chạy `CommandLineRunner` / `ApplicationRunner` sau khi context được khởi tạo.
- Quản lý vòng đời bean và phát sự kiện `ApplicationStartedEvent` / `ApplicationReadyEvent` theo cơ chế `SpringApplication`.
- Kết nối database, gọi API từ client, xử lý file hoặc chạy job khi những dependency tương ứng được cấu hình.

Nó **không tự tạo cổng HTTP chỉ vì có Spring container**. Nếu dùng `spring-boot-starter` mà không có các thành phần web làm thay đổi suy luận kiểu ứng dụng, kết quả mặc định là `NONE`. Các ví dụ thường gặp: batch CLI, tool chuyển đổi dữ liệu, tác vụ khởi tạo, ứng dụng nền chỉ cần bean Spring.

### Ví dụ chủ động chọn NONE

```java
package demo.context;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContextDemoApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(ContextDemoApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.run(args);
    }
}
```

Cấu hình tương đương khi muốn đặt kiểu qua nguồn property:

```properties
spring.main.web-application-type=none
```

**Không phải tắt toàn bộ Spring.** Đây là cách giữ cơ chế container nhưng không vận hành ứng dụng bằng web context. Ví dụ một chương trình dùng `spring-boot-starter-web` để có thư viện HTTP vẫn có thể được cấu hình chạy `NONE`, mặc dù các điều kiện tự cấu hình web server sẽ không còn phù hợp.

**Ứng dụng non-web có tự thoát ngay không?** Không nên khẳng định tuyệt đối. Nếu chỉ có các runner hoàn tất và không còn thread non-daemon giữ JVM, tiến trình có thể kết thúc; nếu có scheduler, thread nền, listener hoặc công việc dài hạn, tiến trình có thể tiếp tục sống. Sự tồn tại của context và vòng đời JVM là hai vấn đề khác nhau. Khi muốn đóng ứng dụng một cách có kiểm soát, dùng các API dừng context và trả mã thoát phù hợp.

## 4. SERVLET: AnnotationConfigServletWebServerApplicationContext

### Bản chất

`WebApplicationType.SERVLET` đại diện ứng dụng theo Servlet API, là mô hình thường gặp khi dùng `spring-boot-starter-web` cùng Spring MVC.

`AnnotationConfigServletWebServerApplicationContext` kế thừa `ServletWebServerApplicationContext`. Ngoài khả năng quản lý bean chung, context web này tích hợp với:

- Một `ServletWebServerFactory`, thường do Spring Boot tự cấu hình khi có server implementation phù hợp.
- Servlet container nhúng, chẳng hạn Tomcat hoặc Jetty tùy bộ dependency.
- Hệ thống `ServletContext`, servlet/filter/listener và các tích hợp web Servlet.
- Spring MVC, trong trường hợp dự án có và sử dụng `DispatcherServlet` để điều phối request HTTP đến controller.
- Cấu hình web server như `server.port`, `server.address` và các tính năng liên quan.

Với `spring-boot-starter-web` theo cấu hình mặc định của Spring Boot 3.3, embedded Tomcat là lựa chọn thông thường. Tuy nhiên **Servlet không có nghĩa bắt buộc Tomcat**: có thể dùng Jetty hoặc server tương thích khác được hỗ trợ và cấu hình đúng.

Một chuỗi request Spring MVC thường có ý nghĩa:

```text
HTTP request
     |
Embedded Servlet container
     |
DispatcherServlet (Spring MVC)
     |
HandlerMapping / HandlerAdapter
     |
@Controller / @RestController
     |
HTTP response
```

`ApplicationContext` quản lý các bean liên quan đến sơ đồ này và vòng đời web server; nó không tự xử lý mỗi request thay cho `DispatcherServlet`.

### Ví dụ cấu hình tối thiểu

Với dependency Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Có thể khai báo:

```properties
spring.application.name=context-servlet-demo
server.port=8080
```

Một controller thử nghiệm:

```java
package demo.context;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "hello-servlet";
    }
}
```

Khi chạy lớp ứng dụng `@SpringBootApplication` trong package `demo.context` hoặc package cha chứa controller, Spring sẽ quét được bean này; với starter web và không có override kiểu ứng dụng, context mặc định thuộc nhánh `SERVLET`. Nếu server khởi động thành công và cổng không bị thay đổi, gọi `GET http://localhost:8080/hello` sẽ trả nội dung:

```text
hello-servlet
```

Ví dụ giả định project đã có Spring Boot Gradle plugin và cấu hình build Java phù hợp. Nếu cổng đang bị chiếm, có thể đặt `server.port=0` để được cấp cổng ngẫu nhiên và đọc cổng thực tế từ context khi xác minh.

## 5. REACTIVE: AnnotationConfigReactiveWebServerApplicationContext

### Bản chất

`WebApplicationType.REACTIVE` mô tả ứng dụng web theo hạ tầng reactive, thường dùng `spring-boot-starter-webflux`.

`AnnotationConfigReactiveWebServerApplicationContext` kế thừa `ReactiveWebServerApplicationContext`, cung cấp môi trường cho các cấu trúc WebFlux. Khi đủ dependency, Spring Boot có thể tự cấu hình `ReactiveWebServerFactory` tương ứng.

Mô hình WebFlux thường dùng `DispatcherHandler` hoặc cơ chế functional routing `RouterFunction` / `HandlerFunction`. Dữ liệu bất đồng bộ có thể đi qua Reactor `Mono` và `Flux`:

```text
HTTP request
     |
Reactive web server / HTTP adapter
     |
WebFlux DispatcherHandler hoặc functional RouterFunction
     |
Handler / @RestController
     |
Mono<T> / Flux<T> hoặc kiểu kết quả phù hợp
     |
HTTP response
```

Ví dụ controller:

```java
package demo.context;

import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReactiveHelloController {

    @GetMapping("/hello")
    public Mono<String> hello() {
        return Mono.just("hello-reactive");
    }
}
```

Dependency Gradle cho ví dụ WebFlux **khi không đồng thời thêm starter MVC**:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

Với Spring Boot 3.3, starter WebFlux thường đưa Reactor Netty vào làm web server mặc định. Cần phân biệt:

- `REACTIVE` không đồng nghĩa “bắt buộc Reactor Netty trong mọi cấu hình”. WebFlux có các lựa chọn runtime HTTP adapter và server được hỗ trợ khác.
- Dùng `Mono` hoặc `Flux` trong một phương thức bất kỳ **không tự động đổi loại ApplicationContext**.
- Thêm `WebClient` để gọi dịch vụ khác cũng **không tự động biến ứng dụng Spring MVC thành reactive web server**.
- Code blocking chạy trên event-loop mà không được xử lý phù hợp có thể làm giảm khả năng phục vụ; chỉ chọn `REACTIVE` không đủ đảm bảo mọi thao tác đều không chặn.

Điểm khác biệt thiết kế là **mô hình xử lý HTTP và hạ tầng web**, không chỉ tên dependency hay kiểu trả về của một controller.

## 6. SpringApplication suy luận WebApplicationType ra sao?

Khi tạo `SpringApplication`, Spring Boot có cơ chế **suy luận kiểu web từ classpath**. Cách hiểu thực dụng cho Spring Boot 3.3:

1. Khi có hạ tầng Spring MVC/Servlet thích hợp, Boot thông thường lựa chọn `SERVLET`.
2. Khi không có lựa chọn MVC chiếm ưu tiên nhưng có hạ tầng WebFlux thích hợp, Boot lựa chọn `REACTIVE`.
3. Khi không có bộ hạ tầng web phù hợp, Boot lựa chọn `NONE`.

Sau đó context factory mặc định tạo triển khai `ApplicationContext` tương ứng. Mô hình này được mô tả trong tài liệu `SpringApplication`.

| Dependency chính của dự án | Kiểu mặc định thường gặp | Context tương ứng |
| --- | --- | --- |
| `spring-boot-starter`, không bổ sung hạ tầng web | `NONE` | `AnnotationConfigApplicationContext` |
| `spring-boot-starter-web` | `SERVLET` | `AnnotationConfigServletWebServerApplicationContext` |
| `spring-boot-starter-webflux`, không thêm MVC | `REACTIVE` | `AnnotationConfigReactiveWebServerApplicationContext` |
| Cùng có `spring-boot-starter-web` và `spring-boot-starter-webflux` | `SERVLET` | `AnnotationConfigServletWebServerApplicationContext` |
| Chỉ dùng một HTTP client mà thiếu hạ tầng web server cần thiết | Có thể `NONE` | Phụ thuộc classpath thực tế |

Dòng “chỉ dùng HTTP client” cần đánh giá theo **những lớp thật sự xuất hiện trong classpath**, không chỉ theo tên dependency khai báo trực tiếp. Thư viện phụ thuộc bắc cầu vẫn có thể tác động đến suy luận kiểu web.

Một trong những bẫy quan trọng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

**Kết quả mặc định là Servlet/MVC**. Đây là cấu hình hợp lý khi ứng dụng MVC muốn dùng `WebClient` để gọi dịch vụ ngoài. Việc có cả Spring WebFlux trên classpath **không phải bằng chứng** chương trình đang chạy với `AnnotationConfigReactiveWebServerApplicationContext`.

Nếu thật sự muốn chạy `REACTIVE` trong trường hợp có cả hai hạ tầng, có thể chỉ định rõ kiểu ứng dụng, nhưng cũng phải đảm bảo các dependency web server reactive và tự cấu hình tương ứng hoạt động. Không giả định rằng đổi enum đủ để tự động thay mọi thành phần của ứng dụng.

## 7. Ép kiểu ứng dụng bằng cấu hình hoặc Java

### Cách A: application.properties

```properties
# Chọn một trong none, servlet, reactive
spring.main.web-application-type=reactive
```

Đây là một property của Spring Boot; đặt trong nguồn cấu hình hợp lệ khi khởi động, hoặc truyền khi chạy:

```bash
java -jar build/libs/app.jar --spring.main.web-application-type=none
```

`app.jar` là tên ví dụ, hãy dùng tệp JAR thật đã build.

### Cách B: Java API

```java
package demo.context;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContextDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ContextDemoApplication.class);

        application.setWebApplicationType(WebApplicationType.REACTIVE);
        application.run(args);
    }
}
```

Thay `REACTIVE` bằng `NONE` hoặc `SERVLET` khi đó là chủ đích. Thí dụ chỉ dùng setter **không thay đổi dependency** đã có: khi chọn `SERVLET` nhưng không có Servlet web server factory, hoặc `REACTIVE` nhưng thiếu reactive server factory, quá trình khởi chạy có thể thất bại.

Lưu ý rằng nguồn cấu hình `spring.main.web-application-type` được Spring Boot bind vào `SpringApplication`. Khi vừa đặt bằng Java vừa có property tương ứng trong `Environment`, thứ tự áp dụng cấu hình có thể ảnh hưởng kết quả. Nên có một nguồn điều khiển rõ ràng và kiểm tra thực tế thay vì ngầm coi setter luôn thắng mọi cấu hình.

### Cách C: SpringApplicationBuilder

```java
new SpringApplicationBuilder(ContextDemoApplication.class)
        .web(WebApplicationType.NONE)
        .run(args);
```

Mã trên cần import `org.springframework.boot.builder.SpringApplicationBuilder` và `org.springframework.boot.WebApplicationType`. Đây là lựa chọn khởi động thay thế; không dùng cả ba cách trong cùng một `main()` chỉ để thử.

**Khi nào nên ép `NONE`?** Ví dụ chạy một lệnh batch hoặc kiểm thử khởi động các bean mà không cần mở port, mặc dù classpath ứng dụng có starter web. **Khi nào nên ép `REACTIVE`?** Khi muốn bảo đảm chế độ reactive trong môi trường có cả MVC và WebFlux, đồng thời đã chuẩn bị đúng web runtime và cấu hình tương ứng.

## 8. Kiểm chứng loại ApplicationContext đang chạy bằng Java

Không nên đoán loại context chỉ từ tên dependency. Ta có thể đọc trực tiếp **đối tượng context mà `SpringApplication.run` trả về**.

File `src/main/java/demo/context/ContextProbeApplication.java`:

```java
package demo.context;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class ContextProbeApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(ContextProbeApplication.class, args);

        System.out.println("context=" + context.getClass().getSimpleName());

        if (context instanceof WebServerApplicationContext webContext) {
            System.out.println("webServer=true");
            System.out.println("port=" + webContext.getWebServer().getPort());
        } else {
            System.out.println("webServer=false");
        }
    }
}
```

Vì việc kiểm tra diễn ra **sau khi `SpringApplication.run(...)` trả về**, đây là thời điểm thích hợp để quan sát kết quả khởi chạy thành công. Mã sử dụng cú pháp pattern matching cho `instanceof`, tương thích Java 17 trở lên.

Thử với ba bộ dependency **thay thế nhau** trong một dự án có Spring Boot Gradle plugin đã cấu hình:

**Phương án NONE:**

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Các dòng kiểm tra có dạng:

```text
context=AnnotationConfigApplicationContext
webServer=false
```

**Phương án SERVLET:**

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

Nếu dùng cổng mặc định và không có lỗi bind port:

```text
context=AnnotationConfigServletWebServerApplicationContext
webServer=true
port=8080
```

**Phương án REACTIVE:**

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

Nếu dùng cổng mặc định:

```text
context=AnnotationConfigReactiveWebServerApplicationContext
webServer=true
port=8080
```

Đây là **những dòng chính do mã kiểm tra in ra**, không phải toàn bộ stdout. Spring Boot còn in banner và log; tên lớp cụ thể có thể khác nếu nhà phát triển thay `ApplicationContextFactory` hoặc áp dụng cơ chế khởi chạy riêng. Port thực tế có thể khác do cấu hình hoặc do hệ điều hành cấp cổng ngẫu nhiên.

Một vài lưu ý khi làm bài thực hành:

- Chỉ sử dụng **một** bộ dependency web trong mỗi lượt thử mặc định. Sau khi đổi dependency, tải lại Gradle và chạy lại để classpath thật sự được cập nhật.
- Nếu package chứa `@SpringBootApplication` không bao phủ những lớp khác, cần điều chỉnh cấu trúc package. Ví dụ trên không phụ thuộc controller nên có thể dùng riêng để kiểm tra context.
- Không cần tự khởi tạo `AnnotationConfigServletWebServerApplicationContext` hay gọi `refresh()` thủ công; `SpringApplication` sẽ thực hiện luồng bootstrap.
- Có thể bổ sung `--server.port=0` khi chạy web app, rồi quan sát `getWebServer().getPort()` để tránh đụng cổng cố định. Khi đó không dự đoán số port trước lúc chạy.
- Để thử ép mode NONE với starter web, truyền `--spring.main.web-application-type=none`. Kết quả nên là context non-web và `webServer=false`, miễn các bean khác không gây lỗi khởi động.

Đoạn kiểm tra dùng interface `WebServerApplicationContext` (thuộc package `org.springframework.boot.web.context`) để hỏi khả năng server; nó có ích hơn việc kiểm tra tên lớp bằng chuỗi `equals(...)`.

## 9. So sánh các khả năng thực sự khác nhau

| Tiêu chí | `NONE` | `SERVLET` | `REACTIVE` |
| --- | --- | --- | --- |
| Có Spring IoC container | Có | Có | Có |
| Tự tạo embedded HTTP server theo mặc định | Không | Có, nếu có factory/runtime phù hợp | Có, nếu có factory/runtime phù hợp |
| Context mặc định | `AnnotationConfigApplicationContext` | `AnnotationConfigServletWebServerApplicationContext` | `AnnotationConfigReactiveWebServerApplicationContext` |
| API xử lý HTTP chủ đạo | Không có web runtime mặc định | Servlet / Spring MVC | WebFlux reactive |
| Dispatcher điển hình | Không có dispatcher HTTP | `DispatcherServlet` | `DispatcherHandler` hoặc functional routing |
| Phụ thuộc Servlet API cho mô hình điều phối web | Không | Có | Không bắt buộc theo mô hình WebFlux |
| Cổng HTTP `server.port` có ý nghĩa | Không theo cơ chế web server nhúng mặc định | Có | Có |
| Có thể dùng DB, scheduler, gọi HTTP client | Có nếu khai báo dependency | Có | Có |
| Có thể dùng `ApplicationRunner` | Có | Có | Có |
| Có thể chạy job nền | Có | Có | Có |

Hai ý cần tránh:

1. `NONE` **không đồng nghĩa** với “không có bean” hoặc “không có mạng”. Nó chỉ không dùng chế độ tự tạo web server nhúng của Spring Boot. Một HTTP client vẫn gọi API ngoài được.
2. `REACTIVE` **không đồng nghĩa** với “mọi đoạn code đều bất đồng bộ” hoặc “ứng dụng không thể chạy trên Servlet container”. WebFlux định nghĩa mô hình lập trình web; lựa chọn HTTP runtime và khả năng tránh blocking còn phụ thuộc cách triển khai cụ thể.

## 10. Vì sao context type ảnh hưởng auto-configuration?

Spring Boot quyết định nhiều bean dựa trên điều kiện có thể bao gồm:

- `@ConditionalOnClass`: một lớp hoặc bộ thư viện có mặt trên classpath.
- `@ConditionalOnMissingBean`: chưa có bean cùng loại/tên tương ứng.
- `@ConditionalOnWebApplication`: đang chạy trong một ngữ cảnh web phù hợp.
- `@ConditionalOnNotWebApplication`: đang chạy ngoài ngữ cảnh web.

Chẳng hạn:

```java
package demo.context;

import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class WebOnlyConfiguration {

    @Bean
    @ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
    String servletOnlyMarker() {
        return "servlet";
    }
}
```

Mã trên là ví dụ minh họa điều kiện: bean tên `servletOnlyMarker` chỉ được đăng ký khi điều kiện web Servlet được thỏa mãn. Đây không phải một endpoint. Tương tự, một cấu hình có thể dùng:

```java
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.REACTIVE)
```

để chỉ áp dụng ở môi trường reactive. Các điều kiện này được xét trong quá trình dựng context. Kết quả có thể khác nếu đổi `WebApplicationType` dù tập các lớp nguồn và nhiều dependency khác không đổi.

Vì thế thao tác “chỉ đổi `spring.main.web-application-type`” có thể thay đổi **những bean auto-configured được tạo**. Không nên xem nó chỉ là cờ bật/tắt cổng web.

**Sự khác nhau giữa classpath và context:** classpath cung cấp bằng chứng rằng một công nghệ **có thể được sử dụng**; loại web context và các điều kiện cấu hình quyết định công nghệ đó **có được khởi tạo cho ứng dụng đang chạy hay không**.

## 11. WebServerApplicationContext khác WebApplicationType ở điểm nào?

`WebApplicationType` là enum của Spring Boot, được dùng ở giai đoạn quyết định cách bootstrap. Sau khi tạo, context là một đối tượng Java có loại và giao diện cụ thể.

Ví dụ:

```java
if (context instanceof WebServerApplicationContext webContext) {
    int actualPort = webContext.getWebServer().getPort();
    System.out.println(actualPort);
}
```

Câu lệnh trên hỏi về khả năng của context **tại runtime**, không hỏi enum đã được truyền vào `SpringApplication` trước đó. Với ngữ cảnh mặc định, cả Servlet và reactive web context đều triển khai `WebServerApplicationContext`. Vì thế chỉ kiểm tra `instanceof WebServerApplicationContext` **không phân biệt được** hai mô hình web.

Để phân biệt chính xác, có thể kiểm tra các interface chuyên biệt hoặc type context, ví dụ:

```java
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;

if (context instanceof ServletWebServerApplicationContext) {
    System.out.println("kind=SERVLET");
} else if (context instanceof ReactiveWebServerApplicationContext) {
    System.out.println("kind=REACTIVE");
} else {
    System.out.println("kind=NON_WEB_OR_CUSTOM");
}
```

Đây là **đoạn Java chèn vào một phương thức đã có biến `context` kiểu `ApplicationContext`/`ConfigurableApplicationContext`**. Nó không phải chương trình biên dịch độc lập. Hai lớp kiểm tra thuộc Spring Boot 3.3; sau khi khởi động bằng factory tùy chỉnh hoặc chạy các tình huống test đặc biệt, phân loại mặc định trên không phải một hợp đồng tuyệt đối.

Khi chỉ cần dùng bean, nên phụ thuộc vào interface chung `ApplicationContext` hoặc injection trực tiếp qua constructor, thay vì viết nhiều nhánh so sánh tên lớp. Chỉ dùng lớp web cụ thể nếu thực sự cần khả năng web chuyên biệt.

## 12. Có thể tự chọn ApplicationContextFactory không?

Có. `SpringApplication` có điểm mở rộng `setApplicationContextFactory(...)` để tùy chỉnh chiến lược tạo context. Trong Spring Boot 3.3, factory mặc định chọn context phù hợp dựa trên `WebApplicationType`.

Mục đích của factory này là tạo **context chưa được refresh**, sau đó `SpringApplication` tiếp tục cấu hình, nạp bean và hoàn thành bootstrap. Nó khác với việc tự tạo một `ApplicationContext` rồi bỏ qua quy trình khởi chạy của Boot.

Ví dụ chỉ minh họa API, khi **chắc chắn** ứng dụng non-web:

```java
import org.springframework.boot.ApplicationContextFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

// Đặt trước application.run(args):
application.setApplicationContextFactory(
        ApplicationContextFactory.ofContextClass(
                AnnotationConfigApplicationContext.class));
```

Đây là đoạn mã cần biến `application` kiểu `SpringApplication` đã được tạo. Không dùng factory cố định trả về non-web context trong ứng dụng đang yêu cầu `SERVLET` hay `REACTIVE`: các auto-configuration và web server factory có thể không còn tương thích. Khi nhu cầu chỉ là bật/tắt web server, `setWebApplicationType(...)` hoặc `spring.main.web-application-type` là điểm cấu hình phù hợp hơn.

Một điểm dễ nhầm: **một loại `ApplicationContext` không nhất thiết có một phiên bản duy nhất trong mọi tình huống**. Có thể có parent-child context do nhà phát triển dựng, context cho test slice hoặc context được tùy chỉnh. Bảng mặc định ở mục 2 mô tả startup bình thường của Spring Boot, không mô tả mọi cấu trúc container tùy biến.

## 13. Khác biệt khi kiểm thử

Trong test, context có thể khác với khi chạy executable JAR vì `@SpringBootTest`, `@WebMvcTest`, `@WebFluxTest`, test slice, mock web environment và test framework có thể thay đổi cách tạo/nạp context.

Ví dụ nếu bài test chỉ cần kiểm tra bean hoặc runner, không cần chạy server thật:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class SimpleContextTest {
    // Các bài test bean không cần cổng HTTP thực.
}
```

Đây là đoạn minh họa annotation của `org.springframework.boot.test.context.SpringBootTest`; cần dependency `spring-boot-starter-test` và framework kiểm thử tương ứng. Nếu không cần tích hợp cả Spring Boot, `ApplicationContextRunner` hoặc unit test thuần cũng có thể phù hợp hơn.

Với `@SpringBootTest(webEnvironment = RANDOM_PORT)`, Spring Boot có thể tạo server chạy trên cổng được hệ điều hành chọn; điều đó không giống context mô phỏng trong `MOCK`. Vì vậy:

- Đừng dựa vào tên class context ở một test để kết luận chắc chắn sản phẩm đang chạy cùng loại.
- Đừng dùng `@WebMvcTest` rồi kết luận toàn bộ ứng dụng chỉ có Spring MVC; đó là một test slice.
- Khi cả MVC và WebFlux hiện diện trong test mà mục đích là WebFlux, có thể cần property `spring.main.web-application-type=reactive` và dependency phù hợp.
- Nếu test cần bảo đảm có web server thật, xác nhận `webEnvironment` và cổng thực tế. Chỉ thấy `@SpringBootTest` không đủ kết luận có server lắng nghe.

Các khác biệt này là lý do nên kiểm chứng ở cả **lượt chạy thực tế** và **lớp kiểm thử đúng mục đích**.

## 14. Lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Nguyên nhân đáng kiểm tra | Hành động |
| --- | --- | --- |
| Thêm `spring-boot-starter-webflux` nhưng vẫn thấy Servlet context | Spring MVC cũng có trên classpath và được ưu tiên mặc định | Xem dependency tree; xác định mục đích là MVC + WebClient hay WebFlux server |
| Chỉ có `spring-boot-starter` nhưng muốn mở HTTP endpoint | App đang là `NONE` và thiếu web stack | Thêm starter web thích hợp và đảm bảo web server factory hoạt động |
| Chọn `SERVLET` nhưng startup lỗi thiếu web server factory | Thiếu/loại trừ embedded Servlet server runtime hoặc cấu hình sai | Kiểm tra starter, dependency exclusions và bean `ServletWebServerFactory` |
| Chọn `REACTIVE` nhưng startup lỗi thiếu reactive server factory | Thiếu runtime HTTP reactive thích hợp hoặc cấu hình không tương thích | Kiểm tra `spring-boot-starter-webflux`, HTTP runtime và các exclusions |
| Ép `NONE` rồi nhận 404 ở cổng cũ | Không còn web server được Boot tự tạo theo cơ chế mặc định | Dùng `SERVLET` hoặc `REACTIVE` khi cần phục vụ HTTP |
| `server.port=8080` nhưng vẫn không mở cổng | Context `NONE`, lỗi startup hoặc server không tạo | In loại context và kiểm tra log khởi động |
| `Mono<String>` trong controller nhưng context vẫn là Servlet | Có MVC và WebFlux đồng thời; kiểu trả về không quyết định context | Kiểm tra startup mode, dispatcher và dependency |
| Kiểm tra trong unit test cho tên context khác production | Test dùng context riêng, slice hoặc mock environment | So sánh theo cùng cách khởi chạy và cùng webEnvironment |
| Đã gọi `setWebApplicationType(NONE)` nhưng vẫn tạo web context | Property khởi động khác có thể bind lại hoặc có custom factory | Kiểm tra `spring.main.web-application-type`, nguồn config và factory |
| Startup in log web server rồi vẫn fail | Web server bắt đầu trong giai đoạn refresh nhưng các bước tiếp có thể lỗi | Kiểm tra exception đầy đủ và sự kiện readiness, không chỉ loại context |

Các bước kiểm tra lần lượt:

1. Xác nhận **classpath thực tế** qua dependency tree, vì dependency bắc cầu có thể kéo theo MVC/Servlet hoặc WebFlux.
2. Tìm mọi nguồn đặt `spring.main.web-application-type`: Java, `application.properties` / YAML, environment variable và tham số dòng lệnh.
3. In loại context và kiểm tra `instanceof WebServerApplicationContext` bằng mã mục 8.
4. Khi có web context, kiểm tra web server factory, cổng bind thực tế, địa chỉ lắng nghe và log lỗi.
5. Kiểm tra những bean tự cấu hình có điều kiện theo Servlet/Reactive; nếu cần, bật report điều kiện bằng `--debug` và đọc những điều kiện được/không được thỏa mãn.
6. Với vấn đề riêng của test, đối chiếu annotation test và web environment đã chọn.

## 15. Thực hành so sánh ba kiểu bằng cùng một bộ mã

Giữ nguyên lớp `ContextProbeApplication` ở mục 8 và thực hiện các bước:

1. **NONE:** chỉ giữ `spring-boot-starter`, chạy và ghi lại tên lớp context, `webServer=false` và trạng thái kết thúc tiến trình sau khi runner hoàn tất.
2. **SERVLET:** thay dependency bằng `spring-boot-starter-web`, chạy và ghi tên context, số port thực tế. Thêm controller `/hello` nếu muốn thử request.
3. **REACTIVE:** thay dependency bằng `spring-boot-starter-webflux` và không để MVC trong classpath, chạy và ghi tên context, số port thực tế. Có thể thử controller trả `Mono<String>`.
4. **Có cả hai starter:** bật lại cả web và webflux, dự đoán context nào sẽ được tạo **trước khi chạy**, rồi chứng minh bằng log và tên lớp context.
5. **Ép kiểu:** trong cấu hình có starter web, chạy với `--spring.main.web-application-type=none`. Kiểm tra tại sao không còn mở port HTTP dù vẫn có các thư viện web.
6. **Thí nghiệm phản ví dụ:** ép `REACTIVE` mà chưa chuẩn bị đúng web runtime để thấy sự khác biệt giữa “chọn enum” và “có đủ điều kiện khởi tạo server”. Chỉ thực hiện trong môi trường thử nghiệm.

Để kiểm chứng output của HTTP endpoint, sử dụng `curl` khi server đang chạy:

```bash
curl http://localhost:8080/hello
```

Chỉ lệnh này phù hợp khi server đang nghe cổng 8080 và đã khai báo controller `/hello` ở bài thực hành. Nếu chọn cổng `0`, lấy số port thực tế từ log hoặc context trước khi gọi.

Hãy giải thích kết quả theo câu hỏi: **Loại ứng dụng được suy luận từ đâu? Spring Boot chọn context nào? Có web server không? Framework nào điều phối request?** Nếu trả lời được cả bốn, bạn đã hiểu mối liên hệ giữa `WebApplicationType` và `ApplicationContext`.

## 16. Ghi nhớ để áp dụng trong dự án

- `ApplicationContext` là nền tảng IoC chung; web app cũng là Spring app, chỉ có thêm hạ tầng web.
- Ánh xạ mặc định của Spring Boot 3.3 là `NONE → AnnotationConfigApplicationContext`, `SERVLET → AnnotationConfigServletWebServerApplicationContext`, `REACTIVE → AnnotationConfigReactiveWebServerApplicationContext`.
- Cách chọn mặc định chịu ảnh hưởng của classpath. Khi cùng có Spring MVC và WebFlux, **Servlet/MVC được ưu tiên mặc định**.
- Dùng `spring.main.web-application-type` hoặc `setWebApplicationType(...)` khi cần chủ động chọn mode, nhưng phải bảo đảm dependency và web server factory tương thích.
- Dùng `SpringApplication.run(...)` và các interface context để quan sát runtime; đừng suy luận chỉ bằng tên starter hoặc kiểu trả về của controller.
- `NONE` vẫn có bean Spring và có thể thực hiện công việc nền; `SERVLET` và `REACTIVE` khác nhau ở hạ tầng HTTP và điều kiện cấu hình web.
- Custom `ApplicationContextFactory` và bối cảnh test có thể thay đổi tên lớp context; nên xem bảng ánh xạ là **hành vi chuẩn của luồng mặc định**, không phải luật bất biến cho mọi ứng dụng Spring.

### Tài liệu tham khảo

- [Spring Boot 3.3 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html): `getWebApplicationType`, `setWebApplicationType`, `setApplicationContextFactory` và quy tắc tạo context.
- [Spring Boot — SpringApplication / Web Environment](https://docs.spring.io/spring-boot/reference/features/spring-application.html): cách suy luận web environment khi có MVC/WebFlux.
- [Spring Boot 3.3 — Servlet context](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/servlet/context/AnnotationConfigServletWebServerApplicationContext.html).
- [Spring Boot 3.3 — Reactive context](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/reactive/context/AnnotationConfigReactiveWebServerApplicationContext.html).

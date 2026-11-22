# Classpath ảnh hưởng tới việc chọn loại ứng dụng như thế nào

Khi gọi `SpringApplication.run(...)`, Spring Boot cần xác định ứng dụng sẽ chạy theo mô hình web nào. Ứng dụng có thể dùng Servlet stack (thường là Spring MVC), Reactive stack (Spring WebFlux), hoặc chạy như một ứng dụng không có web server. Nếu không chỉ định rõ, Spring Boot **dựa vào các class có thể nhìn thấy trên runtime classpath** để suy ra loại ứng dụng.

Vì vậy, thêm hoặc loại một starter có thể làm thay đổi cách Spring Boot khởi động dù code của class ứng dụng không đổi. Ví dụ, `spring-boot-starter-web` thường đưa Spring MVC và Servlet container vào classpath nên ứng dụng được nhận diện là Servlet application. `spring-boot-starter-webflux` đưa Spring WebFlux vào classpath nên có thể dẫn đến Reactive application. Nếu cả MVC và WebFlux cùng hiện diện, Spring Boot mặc định ưu tiên Servlet/MVC.

Bài học theo dõi cách Spring Boot chọn `WebApplicationType`, các class marker được dùng để nhận diện, tác động của dependency bắc cầu, cách ghi đè lựa chọn bằng cấu hình hoặc Java API, loại `ApplicationContext` được tạo và ảnh hưởng tới auto-configuration.

## 1. Ba loại WebApplicationType

Spring Boot định nghĩa enum `WebApplicationType` với ba giá trị:

| Giá trị | Ý nghĩa | Loại ứng dụng thường gặp |
| --- | --- | --- |
| `SERVLET` | Ứng dụng web dựa trên Servlet API | Spring MVC, ứng dụng Servlet/Jersey |
| `REACTIVE` | Ứng dụng web dựa trên reactive web stack | Spring WebFlux |
| `NONE` | Không phải ứng dụng web | Batch job, command-line tool, worker hoặc ứng dụng nền |

Có thể hình dung:

~~~mermaid
flowchart TD
    A["SpringApplication khởi động"] --> B["Xác định WebApplicationType"]
    B --> C{"Loại ứng dụng"}
    C -->|SERVLET| D["Servlet web context"]
    C -->|REACTIVE| E["Reactive web context"]
    C -->|NONE| F["Non-web ApplicationContext"]
    D --> G["Servlet web server / DispatcherServlet"]
    E --> H["Reactive web server / DispatcherHandler"]
    F --> I["Không khởi tạo embedded web server"]
~~~

Loại ứng dụng ảnh hưởng đến cách Spring Boot tạo context, chọn auto-configuration web, khởi tạo web server và xử lý request. Nó không chỉ là nhãn để hiển thị trong log.

### 1.1. SERVLET

`SERVLET` thường được chọn khi ứng dụng có hạ tầng Spring MVC và Servlet API phù hợp. Một ứng dụng Spring MVC điển hình có:

- `DispatcherServlet` làm front controller.
- Servlet container như Tomcat, Jetty hoặc Undertow.
- `ServletWebServerApplicationContext` làm context web trong cấu hình Boot thông thường.
- Các controller dùng `@Controller` hoặc `@RestController`.

Ví dụ dependency thường dùng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Starter này đưa các thành phần Spring MVC và embedded Servlet server mặc định vào runtime classpath theo dependency management của phiên bản Spring Boot đang sử dụng.

### 1.2. REACTIVE

`REACTIVE` dành cho ứng dụng web reactive, thường dùng Spring WebFlux. Stack này được thiết kế để xử lý bất đồng bộ và backpressure với Reactor.

Các thành phần thường gặp:

- `DispatcherHandler` làm điểm điều phối request của WebFlux.
- Reactor types như `Mono<T>` và `Flux<T>`.
- Reactive server như Reactor Netty trong cấu hình starter mặc định.
- `ReactiveWebServerApplicationContext` trong cấu hình Boot thông thường.

Dependency thường dùng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

WebFlux không bắt buộc phải chạy trên Reactor Netty trong mọi cấu hình. Có thể dùng server reactive khác nếu dependency và cấu hình tương ứng được cung cấp.

### 1.3. NONE

`NONE` có nghĩa Spring Boot không khởi tạo ứng dụng như một Servlet hoặc Reactive web application. Loại này phù hợp với:

- Command-line application.
- Batch processing.
- Scheduled worker.
- Công cụ migration.
- Consumer xử lý message không phục vụ HTTP.
- Ứng dụng cần Spring IoC, configuration và auto-configuration nhưng không cần embedded web server.

Ví dụ, ứng dụng có thể vẫn dùng `@Service`, `@Repository`, `ApplicationRunner` và `@ConfigurationProperties` trong non-web context. `NONE` không tắt Spring container; nó chỉ chọn mô hình application context không phải web.

## 2. Classpath là gì trong quyết định này?

Classpath là tập hợp class và resource mà class loader có thể tìm thấy khi ứng dụng chạy. Với ứng dụng Spring Boot, runtime classpath thường gồm:

- Class do chính ứng dụng biên dịch.
- Các JAR dependency trực tiếp.
- Các dependency bắc cầu do starter kéo vào.
- Resource nằm trong thư mục output hoặc trong JAR.
- Các thư viện do runtime/container cung cấp theo cách triển khai.

Khi suy ra loại ứng dụng, Spring Boot kiểm tra khả năng tìm thấy một số class marker. Nó không chỉ đọc tên dependency trong file Gradle/Maven, cũng không phân tích controller để quyết định.

Ví dụ:

~~~text
Ứng dụng
├── spring-boot-starter-web
│   ├── spring-webmvc
│   ├── spring-web
│   └── embedded Servlet server
└── spring-boot-starter-webflux
    ├── spring-webflux
    └── Reactor libraries
~~~

Các starter là dependency tiện dụng. Dependency bắc cầu của chúng mới đưa những class cần thiết vào classpath. Khi thêm hoặc loại starter, tập class mà Spring Boot nhìn thấy có thể thay đổi.

### 2.1. Không phải cứ khai báo dependency là class luôn có mặt lúc chạy

Cần phân biệt các classpath theo giai đoạn:

| Classpath | Mục đích |
| --- | --- |
| Compile classpath | Cung cấp kiểu cần thiết để biên dịch source |
| Runtime classpath | Cung cấp class và resource khi chạy ứng dụng |
| Test compile/runtime classpath | Phục vụ biên dịch và chạy test, có thể chứa dependency riêng |
| Annotation processor path | Chứa processor chạy trong quá trình biên dịch, không mặc nhiên là runtime dependency |

Việc SpringApplication suy ra loại ứng dụng dựa trên class có thể nạp được trong môi trường chạy. Một dependency chỉ có ở compile classpath nhưng không có ở runtime sẽ không đủ để marker class được phát hiện khi ứng dụng khởi động.

Ví dụ, một dependency Gradle khai báo là `compileOnly` thường không được đưa vào runtime classpath. Nếu nó chứa class marker mà Spring Boot cần để nhận diện web stack, việc biên dịch thành công không bảo đảm ứng dụng được chọn loại web tương ứng.

### 2.2. Dependency bắc cầu cũng ảnh hưởng

Bạn có thể không khai báo trực tiếp `spring-webmvc` nhưng một starter khác kéo nó vào. Spring Boot vẫn nhìn thấy class của MVC trên runtime classpath.

Ngược lại, loại `spring-boot-starter-web` khỏi build chưa chắc đã loại MVC nếu một dependency khác vẫn kéo `spring-webmvc` vào.

Do đó, khi loại ứng dụng được suy ra không như mong đợi, hãy xem **runtime dependency graph thực tế**, bao gồm cả dependency bắc cầu.

## 3. Spring Boot nhận diện web stack bằng class marker

Trong Spring Boot 3.x, logic suy ra loại ứng dụng sử dụng một số class marker tiêu biểu:

| Mục đích nhận diện | Class marker |
| --- | --- |
| WebFlux reactive dispatcher | `org.springframework.web.reactive.DispatcherHandler` |
| Spring MVC dispatcher | `org.springframework.web.servlet.DispatcherServlet` |
| Jersey Servlet container | `org.glassfish.jersey.servlet.ServletContainer` |
| Servlet API | `jakarta.servlet.Servlet` |
| Spring Servlet web context | `org.springframework.web.context.ConfigurableWebApplicationContext` |

Đây là chi tiết triển khai để hiểu cơ chế phát hiện, không phải danh sách dependency mà ứng dụng cần khai báo thủ công. Các tên class và namespace có thể khác giữa những thế hệ Spring Boot; ví dụ Spring Boot 2 dùng Servlet namespace `javax.servlet`, còn Spring Boot 3 dùng `jakarta.servlet`.

Spring Boot kiểm tra class có thể được nạp qua class loader hay không. Nếu marker không có, một nhánh nhận diện có thể không được chọn.

### 3.1. Logic suy ra loại ứng dụng ở mức khái niệm

Có thể mô tả quy tắc của Spring Boot 3.x như sau:

1. Nếu `DispatcherHandler` có mặt, nhưng `DispatcherServlet` và `ServletContainer` của Jersey không có, chọn `REACTIVE`.
2. Nếu không thỏa điều kiện Reactive ở trên, Spring kiểm tra các marker Servlet cần thiết.
3. Nếu một trong các marker Servlet cần thiết không có, chọn `NONE`.
4. Nếu các marker Servlet cần thiết đều có, chọn `SERVLET`.

Sơ đồ:

~~~mermaid
flowchart TD
    A["Kiểm tra DispatcherHandler"] --> B{"Có WebFlux marker?"}
    B -->|Không| E["Kiểm tra Servlet markers"]
    B -->|Có| C{"Có MVC DispatcherServlet hoặc Jersey ServletContainer?"}
    C -->|Không| D["REACTIVE"]
    C -->|Có| E
    E --> F{"Có đủ Servlet markers?"}
    F -->|Có| G["SERVLET"]
    F -->|Không| H["NONE"]
~~~

Điểm đáng chú ý là nhánh Reactive được kiểm tra trước nhánh Servlet. Vì vậy, nếu WebFlux có mặt và không có MVC/Jersey marker, Spring Boot có thể chọn `REACTIVE` ngay cả khi một số Servlet API class cũng xuất hiện trên classpath.

Đây là heuristic nhận diện loại ứng dụng dựa trên classpath. Nó không phải phân tích sâu xem code của bạn có thực sự viết controller MVC hay WebFlux hay không.

### 3.2. Vì sao MVC được ưu tiên khi cả hai stack cùng có?

Nếu `DispatcherHandler` và `DispatcherServlet` đều có mặt, điều kiện chọn Reactive không thỏa mãn. Nếu Servlet markers cần thiết có mặt, Spring Boot chọn `SERVLET`.

Đây là hành vi có chủ đích để ứng dụng thêm WebFlux chỉ nhằm dùng một số API reactive, chẳng hạn `WebClient`, mà không vô tình chuyển toàn bộ server từ Spring MVC sang WebFlux.

Khi cần chạy WebFlux server dù MVC cũng có trên classpath, hãy đặt loại ứng dụng tường minh là `REACTIVE`.

## 4. Ví dụ 1: chỉ có spring-boot-starter-web

Build:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Runtime classpath thường có Spring MVC, Servlet API và embedded Servlet container.

Các marker liên quan:

| Marker | Trạng thái dự kiến |
| --- | --- |
| `DispatcherHandler` | Không có nếu không có WebFlux |
| `DispatcherServlet` | Có |
| `ServletContainer` của Jersey | Không có nếu không thêm Jersey |
| Servlet markers | Có |

Kết quả suy ra: `SERVLET`.

Spring Boot tạo Servlet web application context, đăng ký hạ tầng web MVC phù hợp và khởi tạo embedded Servlet server nếu ứng dụng dùng cấu hình server thông thường.

Ví dụ:

~~~java
@SpringBootApplication
public class MvcApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcApplication.class, args);
    }
}
~~~

Controller MVC:

~~~java
@RestController
@RequestMapping("/api")
public class GreetingController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello from Spring MVC";
    }
}
~~~

Khi ứng dụng chạy, request HTTP được Servlet container nhận và chuyển tới hạ tầng Spring MVC.

## 5. Ví dụ 2: chỉ có spring-boot-starter-webflux

Build:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Nếu không có MVC dispatcher hoặc Jersey Servlet marker, WebFlux marker sẽ khiến Spring Boot chọn `REACTIVE`.

| Marker | Trạng thái dự kiến |
| --- | --- |
| `DispatcherHandler` | Có |
| `DispatcherServlet` | Không có |
| `ServletContainer` của Jersey | Không có |
| Servlet markers | Có thể có hoặc không; không làm thay đổi nhánh Reactive khi điều kiện Reactive đã khớp |

Kết quả suy ra: `REACTIVE`.

Controller WebFlux:

~~~java
@RestController
@RequestMapping("/api")
public class ReactiveGreetingController {

    @GetMapping("/hello")
    public Mono<String> hello() {
        return Mono.just("Hello from WebFlux");
    }
}
~~~

`Mono` thuộc Reactor Core, là một publisher phát tối đa một giá trị. Để đoạn ví dụ biên dịch, project cần dependency WebFlux có Reactor tương ứng và import `reactor.core.publisher.Mono`.

Trong WebFlux, request được xử lý theo reactive web stack. Với cấu hình mặc định của starter, Reactor Netty thường là server được sử dụng nếu không có server reactive khác được cấu hình.

## 6. Ví dụ 3: cả Spring MVC và WebFlux cùng có

Build:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Classpath lúc này có cả:

- `DispatcherServlet` của Spring MVC.
- `DispatcherHandler` của Spring WebFlux.
- Servlet API và các dependency web liên quan.
- Các thư viện Reactor cần thiết.

Dù WebFlux marker có mặt, điều kiện chọn Reactive không thỏa mãn vì MVC marker cũng có mặt. Spring Boot mặc định chọn `SERVLET`.

Điều này hữu ích trong trường hợp ứng dụng là MVC server nhưng muốn sử dụng `WebClient` để gọi dịch vụ khác:

~~~java
@Service
public class PartnerLookupService {
    private final WebClient webClient;

    public PartnerLookupService(WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("https://partner.example.test")
                .build();
    }

    public Mono<String> lookup(String id) {
        return webClient.get()
                .uri("/partners/{id}", id)
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

Ứng dụng vẫn có thể là Servlet/MVC application trong khi một service sử dụng `Mono` và `WebClient` để gọi HTTP bất đồng bộ.

### 6.1. Dùng WebClient không có nghĩa server đã chuyển sang WebFlux

Cần phân biệt:

- **WebClient:** HTTP client API, có thể được dùng từ ứng dụng MVC hoặc WebFlux.
- **WebFlux server:** web stack reactive xử lý inbound request.
- **Mono/Flux:** reactive publisher types, không tự quyết định loại application context.
- **WebApplicationType:** lựa chọn mô hình ứng dụng của Spring Boot khi tạo context.

Nếu mục tiêu chỉ là gọi API khác bằng `WebClient`, không cần chuyển server sang Reactive. Nếu muốn inbound server thực sự dùng WebFlux, cần chọn `REACTIVE` và bảo đảm dependency/configuration phù hợp.

### 6.2. Muốn WebFlux server khi cả hai starter cùng có

Có thể ghi đè lựa chọn mặc định:

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

Hoặc dùng Java API:

~~~java
SpringApplication application =
        new SpringApplication(DemoApplication.class);

application.setWebApplicationType(WebApplicationType.REACTIVE);
application.run(args);
~~~

Khi đã chọn `REACTIVE`, Spring Boot tạo reactive web context. Tuy nhiên, việc ghi đè loại ứng dụng không loại bỏ xung đột dependency hay bảo đảm mọi thư viện MVC tương thích với WebFlux. Cần giữ cấu hình và các auto-configuration phù hợp với stack mong muốn.

## 7. Ví dụ 4: ứng dụng không có web dependency

Build:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

Nếu runtime classpath không có các marker cần thiết cho WebFlux hoặc Servlet, Spring Boot chọn `NONE`.

Ứng dụng vẫn có thể sử dụng Spring IoC:

~~~java
@SpringBootApplication
public class BatchApplication {
    public static void main(String[] args) {
        SpringApplication.run(BatchApplication.class, args);
    }
}
~~~

Service:

~~~java
@Service
public class ImportService {
    public void importData() {
        // Đọc và xử lý dữ liệu.
    }
}
~~~

Chạy tác vụ khi ứng dụng khởi động:

~~~java
@Component
public class ImportRunner implements ApplicationRunner {
    private final ImportService importService;

    public ImportRunner(ImportService importService) {
        this.importService = importService;
    }

    @Override
    public void run(ApplicationArguments args) {
        importService.importData();
    }
}
~~~

Ứng dụng này không cần HTTP server. Spring vẫn tạo context, inject service và gọi runner theo lifecycle startup của Boot.

Nếu muốn ứng dụng dừng sau khi hoàn thành batch, cần thiết kế cách kết thúc process phù hợp. Chọn `NONE` tự nó không có nghĩa JVM tự thoát ngay khi runner kết thúc nếu còn non-daemon thread hoặc resource đang hoạt động.

## 8. Loại ứng dụng quyết định ApplicationContext nào được tạo

Sau khi xác định `WebApplicationType`, Spring Boot chọn loại application context tương ứng.

Trong cấu hình mặc định thường gặp:

| WebApplicationType | Context thường được tạo |
| --- | --- |
| `SERVLET` | `AnnotationConfigServletWebServerApplicationContext` |
| `REACTIVE` | `AnnotationConfigReactiveWebServerApplicationContext` |
| `NONE` | `AnnotationConfigApplicationContext` |

Context này ảnh hưởng đến các capability sẵn có:

- Servlet context có tích hợp với Servlet API và embedded Servlet web server.
- Reactive context có tích hợp với reactive web server và WebFlux infrastructure.
- Non-web context không có web server infrastructure mặc định.

Có thể quan sát context class sau khi chạy ứng dụng:

~~~java
ConfigurableApplicationContext context =
        SpringApplication.run(DemoApplication.class, args);

System.out.println(context.getClass().getName());
~~~

Ví dụ, ứng dụng Servlet và Reactive thường in ra tên context class khác nhau. Nếu ứng dụng tự cấu hình `ApplicationContextFactory`, loại context cụ thể có thể được tùy biến; các tên trên mô tả lựa chọn mặc định phổ biến của Spring Boot.

Đừng chỉ nhìn log “Started ...” để suy ra loại context. Kiểm tra context class hoặc cấu hình web type thực tế khi cần xác nhận.

## 9. Loại ứng dụng ảnh hưởng tới auto-configuration

Nhiều auto-configuration được điều kiện hóa theo loại web application.

Ví dụ annotation:

~~~java
@Configuration
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
public class ServletOnlyConfiguration {
    // Bean chỉ phù hợp với Servlet web application.
}
~~~

Reactive configuration:

~~~java
@Configuration
@ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.REACTIVE)
public class ReactiveOnlyConfiguration {
    // Bean chỉ phù hợp với Reactive web application.
}
~~~

Non-web configuration:

~~~java
@Configuration
@ConditionalOnNotWebApplication
public class BatchOnlyConfiguration {
    // Bean chỉ phù hợp khi không chạy web application.
}
~~~

Spring Boot dùng condition để quyết định auto-configuration nào phù hợp với context. Vì vậy, cùng một dependency graph có thể tạo ra các bean khác nhau tùy theo `WebApplicationType` đã chọn và các điều kiện khác.

### 9.1. ConditionalOnClass khác ConditionalOnWebApplication

Hai condition kiểm tra hai điều khác nhau:

| Condition | Kiểm tra |
| --- | --- |
| `@ConditionalOnClass` | Một class cụ thể có trên classpath không? |
| `@ConditionalOnWebApplication` | Context đang được cấu hình như web application loại nào? |
| `@ConditionalOnProperty` | Property có thỏa điều kiện không? |
| `@ConditionalOnMissingBean` | Đã có bean phù hợp trong context chưa? |

Một class marker có thể tồn tại trên classpath nhưng ứng dụng vẫn không chọn loại web tương ứng do marker khác hoặc cấu hình ghi đè. Ngược lại, chọn `REACTIVE` tường minh không thể tự tạo dependency class bị thiếu.

### 9.2. Không phải mọi bean web đều tự xuất hiện chỉ vì chọn SERVLET/REACTIVE

`WebApplicationType` xác định mô hình context và ảnh hưởng condition. Các bean cụ thể vẫn cần auto-configuration hoặc configuration đăng ký chúng. Một context Servlet không tự bảo đảm mọi controller ngoài vùng component scan đều được phát hiện; một context Reactive cũng không tự tạo endpoint nếu ứng dụng chưa khai báo handler phù hợp.

## 10. Ghi đè lựa chọn bằng spring.main.web-application-type

Spring Boot cho phép cấu hình loại ứng dụng tường minh qua property `spring.main.web-application-type`.

Các giá trị hợp lệ tương ứng enum:

~~~yaml
spring:
  main:
    web-application-type: none
~~~

Các lựa chọn:

| Property value | Loại được chọn |
| --- | --- |
| `servlet` | `WebApplicationType.SERVLET` |
| `reactive` | `WebApplicationType.REACTIVE` |
| `none` | `WebApplicationType.NONE` |

Ví dụ chạy ứng dụng như non-web dù dependency web vẫn có trên classpath:

~~~yaml
spring:
  main:
    web-application-type: none
~~~

Điều này có thể hữu ích cho một command-line mode dùng chung module với web application. Nhưng nếu classpath còn các bean web hoặc auto-configuration web khác, cần xem chúng có phù hợp với non-web context hay không.

### 10.1. Truyền property từ command line

Spring Boot hỗ trợ command-line property:

~~~bash
java -jar app.jar --spring.main.web-application-type=none
~~~

Có thể dùng cùng cách cho `servlet` hoặc `reactive`. Command-line property thường có độ ưu tiên cao trong Environment theo quy tắc property source của Boot.

Khi chạy qua IDE, container hoặc script deploy, hãy kiểm tra tham số thực sự được truyền vào process. Một property nằm trong file cấu hình có thể bị override bởi environment variable, system property hoặc command-line argument.

### 10.2. Đặt bằng Java API

Có thể cấu hình trực tiếp trước khi gọi `run`:

~~~java
SpringApplication application =
        new SpringApplication(DemoApplication.class);

application.setWebApplicationType(WebApplicationType.NONE);

ConfigurableApplicationContext context =
        application.run(args);
~~~

Cách này hữu ích khi loại ứng dụng là quyết định của launcher hoặc một chế độ chạy cụ thể. Hãy đặt loại ứng dụng trước khi khởi động context.

### 10.3. Dùng SpringApplicationBuilder

Một lựa chọn khác:

~~~java
new SpringApplicationBuilder(DemoApplication.class)
        .web(WebApplicationType.REACTIVE)
        .run(args);
~~~

`SpringApplicationBuilder` hữu ích khi cần cấu hình nhiều context hoặc parent/child context. Với một ứng dụng đơn giản, `SpringApplication.setWebApplicationType` thường đủ rõ.

## 11. Thứ tự ưu tiên giữa suy luận classpath và cấu hình tường minh

Có thể xem quá trình lựa chọn theo hai giai đoạn:

1. Spring Boot có một giá trị mặc định suy ra từ classpath.
2. Cấu hình ứng dụng hoặc Java API có thể đặt loại ứng dụng cụ thể trước khi context được tạo.

Do đó, khi đọc dependency graph, bạn biết **giá trị mặc định có khả năng được suy ra**. Nhưng để biết ứng dụng đang chạy loại nào, cần kiểm tra thêm cấu hình tường minh và launcher code.

Ví dụ:

- Classpath có cả MVC và WebFlux → mặc định `SERVLET`.
- File cấu hình đặt `spring.main.web-application-type=reactive` → chọn `REACTIVE`.
- Launcher gọi `setWebApplicationType(NONE)` → chọn `NONE`.
- Nếu không có override, kết quả theo heuristic classpath được dùng.

Đừng kết luận loại ứng dụng chỉ dựa vào danh sách dependency nếu chưa kiểm tra property và Java configuration của `SpringApplication`.

## 12. Classpath thay đổi do dependency bắc cầu: cách điều tra

Giả sử team chỉ thêm một thư viện client nhưng sau đó ứng dụng bất ngờ khởi động như MVC application. Có thể thư viện đó kéo một starter web vào dependency graph.

Với Gradle, xem runtime dependency tree:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Tìm riêng một dependency:

~~~bash
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
~~~

Hoặc:

~~~bash
./gradlew dependencyInsight --dependency spring-webflux --configuration runtimeClasspath
~~~

Với Maven:

~~~bash
mvn dependency:tree -Dscope=runtime
~~~

Các lệnh này giúp trả lời:

- Dependency nào kéo `spring-webmvc` vào?
- Phiên bản nào được chọn sau conflict resolution?
- `spring-webflux` có mặt trực tiếp hay bắc cầu?
- Starter nào kéo Servlet container?
- Có dependency bị exclude hoặc chỉ có trong test không?

Khi đã tìm ra dependency gây ra stack không mong muốn, cân nhắc loại đúng starter hoặc dependency bắc cầu ở nơi khai báo. Không nên exclude tùy tiện một class marker mà thư viện khác thực sự cần.

### 12.1. Exclude dependency bắc cầu

Gradle cho phép exclude một module từ một dependency:

~~~groovy
dependencies {
    implementation('com.acme:legacy-client:2.0.0') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-web'
    }
}
~~~

Chỉ dùng khi hiểu thư viện có cần dependency đó ở runtime hay không. Exclude starter có thể loại cả các dependency mà client thực sự dùng. Nếu chỉ muốn thay embedded server hoặc thay web stack, hãy điều chỉnh dependency theo hướng dẫn của Spring Boot và thư viện liên quan.

### 12.2. Dependency test có thể làm thay đổi kết quả test

Classpath khi chạy test có thể khác runtime production. Ví dụ, một test source set thêm starter web để dùng MVC test support, trong khi ứng dụng production không có starter đó.

Khi một test khởi tạo `SpringApplication` riêng, nó có thể suy ra web type theo test runtime classpath. Vì vậy, test context không phải lúc nào cũng phản ánh chính xác runtime dependency graph của artifact deploy.

Nếu cần kiểm tra hành vi production, hãy chạy với classpath/profile gần với cách deploy thật hoặc thiết lập web application type tường minh trong test.

## 13. Kiểm tra loại ứng dụng bằng code

Có thể in ra context class sau khi khởi động:

~~~java
@SpringBootApplication
public class ApplicationTypeDemo {
    public static void main(String[] args) {
        ConfigurableApplicationContext context =
                SpringApplication.run(ApplicationTypeDemo.class, args);

        System.out.println(
                "ApplicationContext: " + context.getClass().getName()
        );
    }
}
~~~

Đây là cách quan sát trực tiếp context mà Spring Boot tạo. Nếu ứng dụng cần đóng context thủ công trong launcher hoặc test, hãy quản lý lifecycle phù hợp; ứng dụng server thường giữ context mở trong suốt thời gian process hoạt động.

Cũng có thể in web type từ chính đối tượng `SpringApplication` trước khi chạy nếu launcher đang kiểm soát instance đó, nhưng không nên dựa vào API nội bộ không được public hoặc suy luận từ log không ổn định giữa các phiên bản.

## 14. Kiểm thử các loại ứng dụng

Một cách kiểm thử rõ ràng là tạo ứng dụng với loại web type được đặt tường minh, rồi xác nhận context class. Ví dụ với non-web:

~~~java
@SpringBootTest(
        properties = "spring.main.web-application-type=none"
)
class NonWebApplicationTest {
    // Kiểm tra các service và configuration không phụ thuộc web server.
}
~~~

Với ứng dụng Servlet hoặc Reactive, có thể dùng test tương ứng trong Spring Boot và cấu hình web environment phù hợp. Khi dùng `@SpringBootTest(webEnvironment = MOCK)`, Boot vẫn chọn loại web application dựa trên web type; mock environment ảnh hưởng cách tạo server/environment cho test chứ không biến MVC thành WebFlux.

Các điều cần kiểm tra:

- Context class có đúng loại mong đợi không?
- Auto-configuration theo web type có match không?
- Bean chỉ dành cho Servlet/Reactive có được đăng ký đúng không?
- Ứng dụng có cố inject Servlet API vào Reactive context hoặc ngược lại không?
- Test runtime classpath có dependency khác production không?

Không cần khởi động embedded server thật cho mọi test. Nếu chỉ muốn kiểm tra service thuần, dùng non-web context hoặc unit test không cần Spring.

## 15. Sự khác nhau giữa chọn loại ứng dụng và chọn embedded server

`WebApplicationType` quyết định Servlet, Reactive hay non-web context. Nó không nhất thiết quyết định duy nhất server implementation cuối cùng.

Ví dụ:

| Loại ứng dụng | Server có thể dùng |
| --- | --- |
| SERVLET | Tomcat, Jetty, Undertow hoặc Servlet container phù hợp |
| REACTIVE | Reactor Netty, Tomcat reactive adapter, Jetty reactive adapter hoặc server reactive phù hợp |
| NONE | Không có embedded web server mặc định |

Nếu dùng `spring-boot-starter-web`, Tomcat thường là embedded Servlet server mặc định. Nếu dùng `spring-boot-starter-webflux`, Reactor Netty thường là lựa chọn mặc định. Dependency khác hoặc cấu hình có thể thay đổi server implementation mà không nhất thiết thay đổi loại application context.

Ví dụ, đổi Tomcat sang Jetty trong một ứng dụng MVC vẫn là `SERVLET`. Chọn server không đồng nghĩa với chọn Servlet hay Reactive stack.

## 16. Chọn sai loại ứng dụng có thể gây ra vấn đề gì?

### 16.1. Ứng dụng muốn MVC nhưng lại chạy NONE

Có thể Servlet marker thiếu ở runtime, starter web bị exclude hoặc property đặt `none`. Khi đó ứng dụng không có Servlet web context như mong đợi và auto-configuration MVC không hoạt động theo cách dự kiến.

Hãy kiểm tra:

- `spring-boot-starter-web` có trong runtime classpath không?
- Servlet API và MVC dispatcher có hiện diện không?
- Có property hoặc Java API override sang `NONE` không?
- Có cấu hình build khiến dependency chỉ tồn tại ở compile/test không?

### 16.2. Ứng dụng muốn WebFlux nhưng chạy SERVLET

Nguyên nhân thường gặp là `spring-webmvc` cũng có mặt, có thể do `spring-boot-starter-web` được kéo vào trực tiếp hoặc bắc cầu.

Nếu thực sự muốn WebFlux server:

- Kiểm tra dependency graph.
- Loại starter MVC nếu không cần.
- Nếu cần giữ MVC dependency cho một mục đích cụ thể, đặt `spring.main.web-application-type=reactive` một cách có chủ đích.
- Xác nhận các auto-configuration và thư viện còn lại tương thích với Reactive context.

### 16.3. Ứng dụng muốn MVC nhưng chạy REACTIVE

Có thể `spring-webflux` có mặt, MVC dispatcher không có, và reactive marker được phát hiện. Hãy thêm Servlet/MVC dependency nếu ứng dụng thực sự cần MVC, hoặc ghi đè loại ứng dụng phù hợp.

### 16.4. Ép loại ứng dụng không tạo dependency còn thiếu

Đặt `spring.main.web-application-type=servlet` không tự thêm `DispatcherServlet`, Servlet API hoặc embedded server vào classpath. Tương tự, ép `reactive` không tự thêm WebFlux hoặc Reactor server.

Cấu hình tường minh chỉ chọn mô hình context. Dependency và implementation cần thiết vẫn phải có trong runtime classpath.

## 17. Phân biệt WebApplicationType với các khái niệm gần giống

| Khái niệm | Câu hỏi trả lời |
| --- | --- |
| `WebApplicationType` | Ứng dụng chạy Servlet, Reactive hay non-web? |
| `ApplicationContext` | Container nào quản lý bean và lifecycle? |
| `spring.main.web-application-type` | Cấu hình tường minh loại ứng dụng nào? |
| `spring.main.lazy-initialization` | Có trì hoãn khởi tạo bean không? |
| `server.port` | Web server lắng nghe ở port nào? |
| `spring.main.banner-mode` | Hiển thị banner startup ra sao? |
| `@ConditionalOnWebApplication` | Configuration có phù hợp với web type hiện tại không? |
| `@ConditionalOnClass` | Class cần thiết có trên classpath không? |

Ví dụ, `server.port=0` không làm ứng dụng thành `NONE`; nó yêu cầu web server chọn port ngẫu nhiên trong phạm vi cấu hình. `spring.main.lazy-initialization` cũng không thay đổi Servlet/Reactive/None, nó thay đổi thời điểm khởi tạo bean.

## 18. Một quy trình thực tế để xác định ứng dụng sẽ chạy loại nào

Khi tiếp nhận một project Spring Boot, có thể làm theo các bước:

1. Tìm dependency trực tiếp của ứng dụng trong Gradle hoặc Maven.
2. Xem runtime dependency graph để biết starter bắc cầu nào được kéo vào.
3. Kiểm tra sự hiện diện của Spring MVC, WebFlux, Jersey và Servlet API marker.
4. Tìm property `spring.main.web-application-type` trong file cấu hình, environment variable và command line.
5. Tìm launcher code có gọi `setWebApplicationType` hoặc `SpringApplicationBuilder.web(...)` không.
6. Dự đoán giá trị mặc định theo classpath và áp dụng override nếu có.
7. Quan sát context class khi ứng dụng khởi động.
8. Kiểm tra auto-configuration condition report nếu bean web mong đợi không xuất hiện.

Có thể dùng lệnh Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webflux --configuration runtimeClasspath
~~~

Và chạy ứng dụng với debug condition report:

~~~bash
java -jar app.jar --debug
~~~

Kết hợp dependency insight và condition report sẽ giúp phân biệt hai nguyên nhân khác nhau: classpath khiến Boot chọn loại ứng dụng nào, và condition nào khiến một auto-configuration cụ thể được bật hoặc bỏ qua.

## 19. Bài tập thực hành

### Bài tập 1 — Chỉ dùng Spring MVC

Tạo project chỉ có `spring-boot-starter-web`. Chạy ứng dụng, ghi lại context class và xác nhận controller có thể nhận HTTP request.

### Bài tập 2 — Chỉ dùng WebFlux

Tạo project chỉ có `spring-boot-starter-webflux`. Tạo endpoint trả `Mono<String>`. So sánh context class và server với bài tập MVC.

### Bài tập 3 — Thêm cả hai starter

Thêm cả `spring-boot-starter-web` và `spring-boot-starter-webflux`. Dự đoán loại ứng dụng trước khi chạy, sau đó kiểm tra context class. Giải thích vì sao MVC được ưu tiên mặc định.

### Bài tập 4 — Ép Reactive bằng property

Giữ cả hai starter và đặt:

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

Chạy lại ứng dụng và quan sát context. Xác định các dependency/configuration nào cần thiết để ứng dụng thực sự phục vụ request bằng WebFlux.

### Bài tập 5 — Chạy non-web

Thêm web starter nhưng chạy với:

~~~bash
java -jar app.jar --spring.main.web-application-type=none
~~~

Quan sát context class và xác định bean nào còn có thể được tạo. Giải thích vì sao chọn NONE không xóa các class web khỏi classpath.

### Bài tập 6 — Tìm dependency bắc cầu

Thêm một thư viện bên thứ ba, dùng `dependencyInsight` để tìm xem nó có kéo `spring-webmvc` hoặc `spring-webflux` vào không. Xác định dependency trực tiếp nào gây ra thay đổi.

### Bài tập 7 — Phân biệt compile và runtime classpath

Đưa một web dependency vào compile-only configuration rồi kiểm tra runtime classpath. Giải thích vì sao source có thể biên dịch nhưng Spring Boot không phát hiện marker tương ứng khi chạy.

## 20. Ghi nhớ

Spring Boot sử dụng runtime classpath để suy ra `WebApplicationType` mặc định. WebFlux marker có thể dẫn tới `REACTIVE` nếu MVC dispatcher và Jersey Servlet marker không có. Nếu nhánh Reactive không được chọn, Spring Boot kiểm tra Servlet marker để chọn `SERVLET`; nếu không đủ marker, ứng dụng được chọn là `NONE`.

Khi cả Spring MVC và WebFlux cùng có trên classpath, Spring Boot mặc định ưu tiên `SERVLET`. Đây là lý do một ứng dụng MVC vẫn có thể thêm WebFlux để sử dụng `WebClient` mà không tự động đổi thành reactive server. Nếu cần lựa chọn khác, đặt `spring.main.web-application-type` hoặc gọi `SpringApplication.setWebApplicationType` trước khi chạy.

Loại ứng dụng được chọn quyết định context web tương ứng và ảnh hưởng tới các auto-configuration có condition theo Servlet, Reactive hoặc non-web. Tuy nhiên, chọn loại ứng dụng không tự thêm dependency còn thiếu và cũng không thay thế việc kiểm tra runtime dependency graph.

Khi ứng dụng khởi động sai stack, hãy lần theo runtime classpath, dependency bắc cầu, property override, launcher code và context class. Phân biệt rõ classpath detection với cấu hình tường minh sẽ giúp bạn hiểu vì sao cùng một codebase có thể chạy MVC, WebFlux hoặc non-web trong những môi trường khác nhau.

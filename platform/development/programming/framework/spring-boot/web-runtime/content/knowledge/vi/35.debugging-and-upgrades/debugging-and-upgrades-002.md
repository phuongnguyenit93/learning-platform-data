# Không tạo được web server hoặc không có bean WebServerFactory

**Module:** Spring Boot → web-runtime → **Gỡ lỗi và nâng cấp**.

Một trong những thông báo khiến người mới học Spring Boot bối rối là:

~~~text
org.springframework.context.ApplicationContextException:
Unable to start ServletWebServerApplicationContext due to missing
ServletWebServerFactory bean.
~~~

Biến thể reactive có thể nhắc đến `ReactiveWebServerApplicationContext` và `ReactiveWebServerFactory`. Chúng thường xuất hiện khi Spring Boot đã chọn **một loại web application context cần chạy embedded server**, nhưng **không tìm được factory tương ứng** trong `ApplicationContext`. Đây **không phải** một lỗi chung cho mọi HTTP 404/500, cũng **không đồng nghĩa** cổng 8080 đang bị sử dụng.

Bài này giải thích:
- `ServletWebServerFactory` và `ReactiveWebServerFactory` là gì, khác Servlet/DispatcherServlet/WebServer/`WebServerFactoryCustomizer` thế nào;
- vì sao `@SpringBootApplication`, auto-configuration, starters, dependency scopes, `WebApplicationType`, parent/child contexts, explicit `@Configuration` và test annotations quyết định factory có được tạo hay không;
- cách phân biệt **missing factory**, **multiple factories**, **server port occupied**, **NoClassDefFoundError**, **BeanCreationException**, **startup without web server** và **request trả 404**;
- cách dùng `--debug`/conditions report, `mvn dependency:tree`, `jar tf`, `@SpringBootTest(RANDOM_PORT)` và các integration tests để khoanh vùng nguyên nhân;
- phương án sửa đúng trong Spring MVC, WebFlux, đổi Tomcat → Jetty/Undertow, executable JAR/WAR, migration Boot 2 → 3 (Jakarta) và Boot 3 → 4;
- ví dụ **Java 17 + Maven + Spring Boot 3.5.16** có full project, positive HTTP test, test tạo lỗi missing factory có chủ đích, test chế độ NONE, hướng dẫn tái hiện bằng command-line exclusion, và checklist triển khai.

**Môi trường tham chiếu:** Java 17+, Spring Boot **3.5.16**, Spring Framework 6.2.x, Maven. Dòng Boot 3.5 kết thúc hỗ trợ OSS sau bản phát hành cuối tháng 6/2026, nên **không chọn 3.5.16 cho ứng dụng production mới nếu không có kênh vá bảo mật phù hợp**; version được cố định ở đây chỉ để học theo API Boot 3.5. Không sao chép package/annotation mới của Boot 4.x vào project 3.5 mà chưa kiểm tra migration notes.

## 1. Hiểu đúng câu lỗi trước khi sửa

Một ứng dụng Servlet Spring Boot thông thường đi theo chuỗi:

~~~text
SpringApplication.run(...)
          │
          ▼
WebApplicationType.SERVLET
          │
          ▼
AnnotationConfigServletWebServerApplicationContext
          │
          ├── refresh() tạo/đăng ký bean definitions
          │       │
          │       └─ @EnableAutoConfiguration
          │             └─ ServletWebServerFactoryAutoConfiguration
          │                    ├─ EmbeddedTomcat
          │                    ├─ EmbeddedJetty
          │                    └─ EmbeddedUndertow
          │
          ├── tìm đúng 1 ServletWebServerFactory bean
          │       │
          │       ├─ 0 bean → lỗi "missing ServletWebServerFactory"
          │       ├─ >1 beans → lỗi "multiple ServletWebServerFactory"
          │       └─ 1 bean: Tomcat/Jetty/Undertow factory
          │
          └── factory.getWebServer(initializers...)
                   │
                   └─ WebServer.start() → socket/connector → HTTP
~~~

Trong Spring Boot 3.5, `ServletWebServerApplicationContext` là loại context dành cho embedded servlet container. Khi khởi tạo, nó **tra cứu một bean duy nhất có kiểu `ServletWebServerFactory`** trong context; thường bean do Boot auto-configure là `TomcatServletWebServerFactory`, `JettyServletWebServerFactory` hoặc `UndertowServletWebServerFactory`.

**Cần phân biệt rất rõ:**

| Thành phần | Nó thực sự làm gì? | Có tạo HTTP server không? |
| --- | --- | --- |
| `SpringApplication` | Điều phối bootstrap, chọn web type/context, load configuration | Thông qua context phù hợp |
| `ServletWebServerApplicationContext` | Embedded Servlet context; tìm factory, tạo/start server | **Có**, khi có factory |
| `ServletWebServerFactory` | Factory tạo container `WebServer`: Tomcat/Jetty/Undertow | **Có**, khi được context gọi |
| `TomcatServletWebServerFactory` | Servlet factory cụ thể cho embedded Tomcat | **Có** |
| `DispatcherServlet` | Servlet của Spring MVC, xử lý controller/handler mappings | **Không** tự cung cấp HTTP listener |
| `@RestController` | Đăng ký handler ở tầng MVC | **Không** tạo factory/server |
| `WebServerFactoryCustomizer` | Chỉnh port, connector, SSL hoặc options của factory hiện có | **Không** tạo factory một mình |
| `WebServer` | Embedded runtime đã được factory tạo | Start/stop và lắng nghe network |
| `ReactiveWebServerFactory` | Factory cho HTTP runtime reactive | **Có** khi dùng Reactive context |
| `server.port` | Cấu hình cổng cho một server đã có | **Không** chữa lỗi thiếu factory |

**Định nghĩa theo hợp đồng:** thiếu factory nghĩa là **0 bean có type phù hợp tại nơi context tìm**. Nó không có nghĩa “Java không biết Tomcat là gì”, cũng không khẳng định “Maven thiếu starter-web” — đó chỉ là **một** khả năng. Nếu bean khác tồn tại nhưng không ở context đúng hoặc type khác (reactive thay vì servlet), servlet context vẫn xem là thiếu.

### 1.1. Tại sao `@RestController` vẫn compile nhưng ứng dụng không chạy?

Một Java controller có thể compile vì `spring-web`/`spring-webmvc` có trên compile classpath, trong khi **embedded Tomcat runtime classes** đã bị Maven exclusion hoặc sai scope. Ngược lại, HTTP server starter có thể tồn tại nhưng auto-configuration bị loại bỏ do dùng `@Configuration` thay vì `@SpringBootApplication` khi bootstrap.

Framework phải qua **hai điều kiện khác nhau**:
1. Có runtime/framework classes và configuration đủ để tạo đúng loại **factory bean**.
2. Tạo/bind/start server thành công, rồi request mới được dispatch đến controller.

Một handler `@GetMapping("/ping")` không thể tự lấp chỗ trống của `ServletWebServerFactory`.

### 1.2. Thông báo thường chỉ ra tầng lỗi, không chỉ ra toàn bộ root cause

Ví dụ:

~~~text
ApplicationContextException: Unable to start ServletWebServerApplicationContext
due to missing ServletWebServerFactory bean.
~~~

Phần “missing” cho biết Spring tìm factory **trong context và không có**, nhưng chưa giải thích:
- Maven/Gradle thiếu Tomcat/Jetty/Undertow?
- Auto-config `ServletWebServerFactoryAutoConfiguration` bị exclude?
- `@EnableAutoConfiguration` không có?
- SpringApplication bị ép `WebApplicationType.SERVLET` khi runtime classpath không phù hợp?
- Test/custom context chỉ import một cấu hình tối giản?
- Parent context có factory, child Servlet context không có?
- Custom bean/multiple contexts hoặc auto-config conditions đã bị thay đổi?

**Chẩn đoán chuẩn:** lấy **root cause + Condition Evaluation Report + runtime dependency tree + effective properties + loại ApplicationContext thực tế**, không bắt đầu bằng thêm một `@Bean TomcatServletWebServerFactory` vô điều kiện.

## 2. Hai họ factory và ứng dụng nào cần họ nào?

| Web stack | Loại context | Factory interface bắt buộc | Factory mặc định thường gặp |
| --- | --- | --- | --- |
| **Spring MVC / Servlet** | `ServletWebServerApplicationContext` | `ServletWebServerFactory` | `TomcatServletWebServerFactory` |
| **WebFlux / Reactive** | `ReactiveWebServerApplicationContext` | `ReactiveWebServerFactory` | `NettyReactiveWebServerFactory` |
| **Non-web process** | Non-web `ApplicationContext` | **Không cần** | Không có HTTP listener |
| **WAR trong external container** | Container-managed Servlet lifecycle theo deployment | Không có cùng yêu cầu tạo embedded server trong lúc external container bootstrap | Container ngoài chịu trách nhiệm HTTP server |

Spring Boot 3.5 có các lựa chọn:
- Servlet: **Tomcat, Jetty, Undertow**.
- Reactive: **Reactor Netty, Tomcat, Jetty, Undertow** qua factory thích hợp.
- Reactor Netty **không** phải một Servlet factory; `NettyReactiveWebServerFactory` không thể được đưa vào `ServletWebServerFactory` rồi dùng `DispatcherServlet` như trên Tomcat.

**Sai lầm phổ biến:** thấy dependency `reactor-netty-http` rồi cho rằng Servlet web app đã có embedded server. Nếu Boot đang chọn `SERVLET` mà không có `TomcatServletWebServerFactory`/Jetty/Undertow factory, Reactor Netty reactive factory không thỏa điều kiện Servlet context.

### 2.1. Servlet factory được tạo bởi auto-configuration nào?

Tên lớp Boot 3.5:

~~~java
org.springframework.boot.autoconfigure.web.servlet
    .ServletWebServerFactoryAutoConfiguration
~~~

Các điều kiện chính của auto-configuration servlet gồm:
- Có Servlet API class thích hợp trên classpath (ví dụ `jakarta.servlet.ServletRequest`).
- `@ConditionalOnWebApplication(type=SERVLET)` match.
- Các nested configurations cho Tomcat/Jetty/Undertow chỉ tạo factory khi runtime container classes tương ứng hiện diện và các bean conditions phù hợp.
- `@ConditionalOnMissingBean`/`@ConditionalOnClass` ảnh hưởng việc Boot có tạo default bean hay không.

Đừng chỉ xem dòng “`ServletWebServerFactoryAutoConfiguration matched`”: phần nested `EmbeddedTomcat`/`EmbeddedJetty`/`EmbeddedUndertow` vẫn có thể **không match**. Cần đọc **negative matches** để biết class nào thiếu hoặc factory khác đã khiến default backing off.

### 2.2. Reactive factory và reactive auto-configuration

Tên lớp Boot 3.5:

~~~java
org.springframework.boot.autoconfigure.web.reactive
    .ReactiveWebServerFactoryAutoConfiguration
~~~

Nó cấu hình factory thích hợp cho `ReactiveWebServerApplicationContext` nếu web application reactive và HTTP runtime implementation tương thích trên classpath. Với starter `spring-boot-starter-webflux`, Boot 3.5 thường kéo theo **`spring-boot-starter-reactor-netty`**.

Nếu exclude Reactor Netty mà không thay bằng reactive runtime tương thích (Tomcat/Jetty/Undertow), reactive context có thể thiếu `ReactiveWebServerFactory` hoặc lỗi thiếu class trước đó. **Không sửa bằng `TomcatServletWebServerFactory` khi app đã chọn `REACTIVE`.** Hai interface không thay thế lẫn nhau.

### 2.3. Boot khác Servlet container ngoài WAR thế nào?

Khi dùng executable JAR/embedded server, `SpringApplication` tạo một `ServletWebServerApplicationContext` và cần embedded server factory.

Khi deploy một WAR theo mô hình truyền thống, **Tomcat/Jetty ngoài process** quản lý socket và `ServletContext`; Boot có integration khác qua `SpringBootServletInitializer`. Không mặc nhiên lấy stack trace `missing ServletWebServerFactory` của executable JAR rồi áp dụng tương đương cho external-WAR runtime. Một WAR có dependency embedded container `provided` **có thể đúng**; trong executable Boot WAR, `lib-provided` giúp nó còn có thể chạy qua `java -jar` nếu build plugin/config đúng.

## 3. `WebApplicationType`: SERVLET, REACTIVE và NONE

Boot định nghĩa enum `org.springframework.boot.WebApplicationType`:

| Giá trị | Ý nghĩa | Factory cần? |
| --- | --- | --- |
| `SERVLET` | Servlet-based web application, embedded server | `ServletWebServerFactory` |
| `REACTIVE` | Reactive web application, embedded reactive server | `ReactiveWebServerFactory` |
| `NONE` | Không tạo web server | **Không** |

Boot suy luận type từ classpath. **Nếu cả `spring-boot-starter-web` (MVC) và `spring-boot-starter-webflux` có mặt, MVC thường được ưu tiên và Boot chọn SERVLET**. Không giả định thêm WebFlux starter tự chuyển cả ứng dụng sang Reactor Netty.

Đặt rõ ràng bằng property:

~~~properties
spring.main.web-application-type=servlet
~~~

hoặc:

~~~properties
spring.main.web-application-type=reactive
~~~

hoặc CLI/headless job:

~~~properties
spring.main.web-application-type=none
~~~

Cách programmatic:

~~~java
SpringApplication app = new SpringApplication(DemoApplication.class);
app.setWebApplicationType(WebApplicationType.NONE);
app.run(args);
~~~

Đây là **mảnh minh họa**, không copy vào main của web server demo. `NONE` cố ý chạy không HTTP, không phải một “cách fix” nếu mục tiêu business bắt buộc nhận web requests.

### 3.1. Cấu hình `NONE` có làm mất WebServerFactory bean không?

Trong non-web mode, `@ConditionalOnWebApplication` không match, nên **không có embedded WebServerFactory là đúng thiết kế**. Ứng dụng có thể startup thành công mà không có `/ping` và port listening.

Nếu người dùng báo “app không có HTTP port” nhưng logs cho thấy `Started DemoApplication`, trước khi đi tìm missing factory error hãy kiểm tra:

~~~properties
spring.main.web-application-type=none
~~~

và các nơi override: command-line arguments, environment variables, active profiles, `SpringApplication#setWebApplicationType`, `SpringApplicationBuilder.web(...)`. Một app chạy thành công ở `NONE` **không phải** lỗi missing factory, bởi context không yêu cầu factory.

### 3.2. `server.port=-1` khác `NONE`

Spring Boot docs phân biệt:

~~~properties
server.port=-1
~~~

**Tắt HTTP endpoints nhưng vẫn tạo web application context.** Đây là thiết kế khác với:

~~~properties
spring.main.web-application-type=none
~~~

`server.port=-1` không đổi `ServletWebServerApplicationContext` thành non-web, nên context vẫn có thể cần factory. Nó cũng không chứng minh mọi loại web server startup có kết quả giống nhau ở từng version.

~~~properties
server.port=0
~~~

yêu cầu OS chọn cổng rảnh **sau khi factory đã tồn tại**, hữu ích cho `@SpringBootTest(RANDOM_PORT)`. Nó không tạo một factory bị thiếu. Đổi từ port 8080 sang 8081 hay 0 để “sửa missing factory” là nhầm tầng.

### 3.3. Khi ép web type trái với runtime classpath

Một CLI project chỉ có `spring-boot-starter` (không Servlet API/server implementation), rồi ép `WebApplicationType.SERVLET`, có thể fail vì thiếu servlet classes, vì missing factory hoặc classloading trước khi factory lookup — **stack trace phụ thuộc classpath thực**. Không tuyên bố luôn nhận chính xác một message.

Nếu buộc dùng Servlet, cung cấp stack servlet nhất quán (ví dụ `spring-boot-starter-web` + một servlet container starter). Nếu muốn CLI không web, dùng `NONE`. Nếu dùng WebFlux, cần reactive web framework + reactive runtime; không ép `SERVLET` chỉ để chữa HTTP port.

## 4. Root cause 1: dependency container bị loại hoặc đóng gói sai

### 4.1. MVC Maven dependency tối thiểu phù hợp

Với Spring Boot 3.5, `spring-boot-starter-web` thường bao gồm:
- `spring-web`/`spring-webmvc`;
- Jackson JSON integration;
- `spring-boot-starter-tomcat` và các embedded Tomcat artifacts;
- Spring Boot auto-configuration phù hợp.

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Thêm starter này thường là lựa chọn đúng để có MVC + embedded Tomcat. **Không** thêm thủ công các JAR `tomcat-embed-core` với version tùy ý chỉ để bù một transitively excluded starter; nó có thể thiếu các artifacts tương thích hoặc tạo javax/jakarta API mismatch.

### 4.2. Ví dụ Maven exclusion gây mất Tomcat

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
~~~

**Chỉ bỏ Tomcat khi cố ý thay bằng một Servlet container starter khác**, ví dụ:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jetty</artifactId>
</dependency>
~~~

hoặc:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-undertow</artifactId>
</dependency>
~~~

Các khối XML trên là **mảnh cấu hình**, không thêm cả Jetty và Undertow cùng lúc trong project mẫu. Khi thay server, dùng BOM của Spring Boot 3.5 để quản lý versions. Nếu project đang thiếu Servlet API class toàn bộ sau exclusion, Boot có thể phát hiện `NONE` hoặc throw class-loading failure trước khi báo missing factory. Cần đọc root cause thực thay vì giả định một thông báo duy nhất.

### 4.3. Runtime dependencies khác compile dependencies

Maven scopes:
- `compile`: có mặt khi compile và runtime.
- `runtime`: có mặt tại runtime, không nhất thiết lúc compile.
- `provided`: thường dùng cho servlet container do **external environment** cung cấp khi deploy WAR; không tự xem nó là bình thường cho mọi executable JAR.
- `test`: chỉ cho tests, **không** có trong packaged app runtime.
- `optional`/exclusions/dependencyManagement`: có thể đổi effective runtime graph.

Gradle tương ứng có `implementation`, `runtimeOnly`, `compileOnly` và `providedRuntime` trong WAR. Spring Boot docs ưu tiên `providedRuntime` thay `compileOnly` cho traditional WAR để dependency vẫn có trên test classpath và executable-WAR layout đúng.

**Đừng chữa bằng compile success.** Artifact runtime phải thật sự chứa hoặc có khả năng load factory implementation trong đúng environment.

### 4.4. Lệnh kiểm tra dependency runtime

Tại root Maven project:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-tomcat
mvn dependency:tree -Dincludes=org.apache.tomcat.embed:tomcat-embed-core
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-jetty
mvn help:effective-pom
~~~

Kiểm tra:
- `spring-boot-starter-web` có còn trên runtime dependency graph không?
- `spring-boot-starter-tomcat`/Jetty/Undertow có bị loại do một parent BOM, profile hoặc exclusion không?
- Effective scope có phải `test`/`provided` không?
- Có cùng lúc nhiều embedded servers dẫn đến điều kiện chọn bean không mong đợi?
- Spring Boot dependencies có cùng line/version family không, hoặc từng module bị override lệch?

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot-starter-tomcat --configuration runtimeClasspath
~~~

Các lệnh này phân tích **runtime classpath**, không đụng production host và không cần xem source của container tự cấu hình. Trong Windows PowerShell có thể dùng `.\gradlew.bat`; Maven `-Dincludes=...` đôi khi cần đặt trong dấu nháy tùy shell.

### 4.5. Kiểm tra executable JAR/WAR

~~~bash
mvn clean package
jar tf target/server-factory-lab-0.0.1-SNAPSHOT.jar
~~~

Trong executable Boot JAR, dependencies được đóng dưới `BOOT-INF/lib/`, classes/resources dưới `BOOT-INF/classes/`; hãy tìm các embedded Tomcat/Jetty/Undertow JARs phù hợp. Nếu `jar tf` không tìm thấy embedded runtime dù dependency tree có, kiểm tra Spring Boot Maven/Gradle repackaging, shade/minimize rules, assembly plugin, exclusions và Docker copy image layering.

**Không** coi `java -cp app.jar com.example.App` là giống `java -jar executable.jar`: Boot executable JAR chứa nested libraries cần Boot launcher hoặc giải pháp classpath chuẩn. Dùng `java -jar` như build được tạo; nếu chạy traditional WAR trong external Tomcat, dùng deployment path của WAR và container logs.

## 5. Root cause 2: chưa bật hoặc đã exclude auto-configuration

### 5.1. `@SpringBootApplication` thực sự làm gì?

~~~java
@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` kết hợp **`@SpringBootConfiguration` + `@EnableAutoConfiguration` + `@ComponentScan`**. Khi classpath chứa embedded Tomcat và web type SERVLET, auto-configuration có thể tạo `TomcatServletWebServerFactory`. Nếu main class thay bằng:

~~~java
@Configuration
public class BareApp {
    public static void main(String[] args) {
        SpringApplication.run(BareApp.class, args);
    }
}
~~~

thì `@Configuration` một mình **không tự bật Boot auto-configuration**. Khi Boot vẫn khởi tạo một Servlet WebServer context, việc không có factory có thể tạo chính lỗi **missing ServletWebServerFactory**. Phần 11 có test tái hiện lỗi này có chủ đích.

**Lưu ý tinh tế:** thiếu `@ComponentScan`/đặt main class sai package có thể làm **không tìm thấy controller/service**, nhưng **không tự chứng minh missing factory** nếu auto-configuration vẫn tạo server. Phải phân biệt bean của application với bean factory infrastructure.

### 5.2. Exclude sai một auto-configuration cụ thể

Bất kỳ cấu hình nào dưới đây có thể cố ý vô hiệu auto-configuration factory:

~~~java
@SpringBootApplication(
    exclude = ServletWebServerFactoryAutoConfiguration.class
)
class BadServletApplication {
}
~~~

Hoặc:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.web.servlet.ServletWebServerFactoryAutoConfiguration
~~~

**Đây là cấu hình phá hỏng ví dụ**, chỉ nên dùng để **tái hiện lỗi có chủ đích** ở lab. Với một Servlet web app bình thường, **bỏ exclude** mới là hướng sửa đúng. Nếu một library/team đã thêm exclude để tránh một lỗi khác, tìm lý do và giải quyết nguyên nhân thay vì đổi qua custom factory mù quáng.

### 5.3. `@EnableWebMvc` không phải một factory switch

`@EnableWebMvc` ảnh hưởng cách Spring MVC được cấu hình và có thể khiến Boot MVC auto-configuration không còn cung cấp default static resource mappings, message converters hoặc handlers theo cách quen thuộc. Tuy nhiên nó **không đồng nghĩa** `ServletWebServerFactoryAutoConfiguration` bị tắt. Một app có `@EnableWebMvc` vẫn có thể start Tomcat nếu factory được tạo.

**Đừng đổ mọi missing factory cho `@EnableWebMvc`** chỉ vì lỗi xảy ra sau khi thêm annotation; xem conditions report và bean definitions thực. Ngược lại, nếu app startup nhưng static resource 404 sau `@EnableWebMvc`, đó là **lỗi mapping MVC**, không phải missing factory.

### 5.4. Manual bean: khi nào thật sự cần?

Spring Boot docs cho phép tùy biến server qua `WebServerFactoryCustomizer`:

~~~java
@Component
public class ServerTuner implements
        WebServerFactoryCustomizer<TomcatServletWebServerFactory> {
    @Override
    public void customize(TomcatServletWebServerFactory factory) {
        factory.setPort(9090);
    }
}
~~~

Đây là **mảnh minh họa**, cần imports từ `org.springframework.boot.web.server.WebServerFactoryCustomizer`, `org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory` và `org.springframework.stereotype.Component`. Dùng properties `server.port=9090` thường đơn giản hơn.

`WebServerFactoryCustomizer` **không tạo factory bean**: nó chỉ customizes bean đã tồn tại. Nếu factory là null/không có, thêm customizer không chữa được. Trong trường hợp rất đặc biệt có thể khai báo:

~~~java
@Configuration(proxyBeanMethods = false)
public class ExplicitFactoryConfig {
    @Bean
    ServletWebServerFactory servletWebServerFactory() {
        return new TomcatServletWebServerFactory();
    }
}
~~~

Đây cũng là **mảnh minh họa** (cần imports và embedded Tomcat dependency), **không phải bước sửa mặc định**. Custom bean có thể làm Boot auto-config back off; phải bảo đảm chỉ **một** factory phù hợp, các customizers/SSL/ports/session settings vẫn chạy và security policies không bị bỏ qua. Khi nguyên nhân là missing starter/auto-configuration, **sửa root cause** trước.

## 6. Root cause 3: test, custom ApplicationContext hoặc component scan quá hẹp

### 6.1. Test slice không mở server thật

`@WebMvcTest` + `MockMvc` nạp **MVC test slice**, thường không tạo một HTTP server listening trên socket. Điều đó là **thiết kế đúng**, không phải thiếu factory. Nếu test controller đang pass nhưng `java -jar` fail thiếu factory, test đó chưa bao phủ runtime bootstrap.

Một `@SpringBootTest` mặc định dùng `webEnvironment=MOCK`, cũng không nhất thiết mở embedded server. Để xác minh startup có factory/socket:

~~~java
@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
class WebRuntimeTest {
    @LocalServerPort
    int port;
}
~~~

Project mục 11 có test gọi `/ping` qua real HTTP client và assert có đúng một Servlet factory.

### 6.2. `@ContextConfiguration(classes=...)` có thể đổi nguồn cấu hình

Một test:

~~~java
@SpringBootTest(
    classes = BareConfiguration.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class AccidentalTest {
}
~~~

có thể dùng `BareConfiguration` thuần `@Configuration` thay vì main `@SpringBootApplication`. Khi không bật auto-configuration phù hợp, Servlet web context không tìm được factory. Mảnh này **minh họa anti-pattern**, không phải một test độc lập có class đầy đủ.

Cách sửa thường là chỉ ra Boot main configuration:

~~~java
@SpringBootTest(
    classes = DemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class CorrectIntegrationTest {
}
~~~

hoặc nếu đang test riêng một `@Configuration`, **không ép webEnvironment=RANDOM_PORT** nếu mục tiêu chỉ test bean. Dùng `ApplicationContextRunner`/`@SpringBootTest(webEnvironment=NONE)` khi phù hợp. Không buộc mọi test config phải nạp Tomcat chỉ để thỏa một stack trace.

### 6.3. Nested `@Configuration` trong test có thể thay primary config

Spring Boot test docs phân biệt:
- Nested plain `@Configuration` trong test có thể **thay thế** primary Boot config cho context đó.
- Nested `@TestConfiguration` thường được **thêm vào** primary Boot config, không thay thế.

Khi một test viết:

~~~java
@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
class MyTest {
    @Configuration
    static class OverrideOnly {
        @Bean MyService service() { ... }
    }
}
~~~

Spring TestContext có thể lấy nested config làm source chính, làm mất Boot auto-configuration nếu source đó không có `@EnableAutoConfiguration`. Đó là cách tạo ra missing WebServerFactory dù dependencies đầy đủ.

Với bean test-only:

~~~java
@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
class MyTest {
    @TestConfiguration
    static class AddOnly {
        @Bean MyService service() { ... }
    }
}
~~~

Đây là **mảnh minh họa** cần class `MyService`/imports; trong ứng dụng thật phải tránh duplicate service beans và bảo đảm Boot main config vẫn được sử dụng. Dùng `@TestConfiguration` hoặc explicit `classes=DemoApplication.class` + `@Import(...)` theo nhu cầu.

### 6.4. `new AnnotationConfigServletWebServerApplicationContext(...)` không tự đủ

Tạo Servlet context thủ công:

~~~java
new AnnotationConfigServletWebServerApplicationContext(
    BareConfiguration.class);
~~~

có thể thiếu server factory nếu không import auto-configuration hoặc bean tương ứng. Không giống `SpringApplication.run(@SpringBootApplication)` vì Boot run thiết lập Environment/listeners/autoconfig/web type logic. Nếu project tích hợp Spring vào một framework khác hoặc custom bootstrap, hãy kiểm tra code đang tạo **context class nào**, **register config nào** và **factory bean nằm ở context nào**.

### 6.5. Parent/child ApplicationContexts

Với `SpringApplicationBuilder.parent(...).child(...)`, parent context thường không chứa bean của child và ngược lại. `ServletWebServerApplicationContext` tìm factory tại context của nó (Boot API nói bean được tìm **trong ApplicationContext itself**). Một factory chỉ nằm ở parent không phải lời hứa sẽ được dùng làm factory embedded server của child. Tương tự, tạo thêm một Servlet child context nhưng chỉ import controller config có thể gây missing factory dù parent app chạy tốt.

Hạn chế đa tầng context khi không thực sự cần; đưa server ownership/auto-configuration vào đúng context và test hierarchy. Đừng kéo `TomcatServletWebServerFactory` từ parent bằng một shortcut thiếu hiểu biết vì có thể tạo **hai embedded servers** hoặc duplicate lifecycle.

### 6.6. Custom component scan và quá trình nâng cấp

`@SpringBootApplication(scanBasePackages=...)` giúp chọn application package scan. Nhưng Boot auto-configuration imports dùng `@EnableAutoConfiguration`, không đơn thuần component scan các classes trong packages của app. Một custom `@ComponentScan` có thể làm test slicing mất `TypeExcludeFilter` và kéo các beans ngoài ý muốn vào tests, nhưng đừng nói “scanBasePackages sai là nguyên nhân chắc chắn thiếu factory”. Hãy kiểm tra effective auto-config và `@SpringBootApplication` trước.

## 7. Root cause 4: Servlet ↔ Reactive mismatch khi nâng cấp

### 7.1. Khi project dùng cả Web MVC và WebFlux

Trong Spring Boot 3.5, có `spring-boot-starter-web` và `spring-boot-starter-webflux` cùng lúc thì Boot **ưu tiên MVC/SERVLET**. Việc thêm WebFlux chỉ để dùng `WebClient` không tự làm ứng dụng chạy Reactor Netty.

~~~text
Classpath:
  spring-boot-starter-web
  spring-boot-starter-webflux

Default WebApplicationType:
  SERVLET → cần ServletWebServerFactory
~~~

Nếu thật sự muốn một server WebFlux/reactive:

~~~properties
spring.main.web-application-type=reactive
~~~

**Nhưng property không tạo runtime implementation từ không khí.** Cần một reactive web-server factory khả dụng cho classpath (thường Netty qua `spring-boot-starter-webflux`, hoặc Tomcat/Jetty/Undertow theo Boot 3.5). Khi reactive context thiếu factory, chẩn đoán `ReactiveWebServerFactoryAutoConfiguration` và reactive starter/runtime, **không** chỉ xem Servlet factory.

### 7.2. Reactive minimal Maven (mảnh cấu hình)

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

Spring Boot 3.5 starter WebFlux thường kéo Reactor Netty. Nếu project exclude:

~~~xml
<exclusion>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-reactor-netty</artifactId>
</exclusion>
~~~

mà không thay reactive server implementation khác, startup có thể thiếu factory hoặc class. Đây là **mảnh minh họa**, exclusion phải nằm bên trong dependency phù hợp; không copy như dependency độc lập.

### 7.3. Jakarta migration từ Boot 2.x lên 3.x

Spring Boot 3.x chuyển sang Jakarta EE namespaces. Đối với Servlet:
- Boot 2 / Spring 5 thường dùng `javax.servlet.*`.
- Boot 3 / Spring 6 dùng `jakarta.servlet.*`.
- Các container tương ứng cũng phải hỗ trợ Servlet/Jakarta API tương thích.

Nếu project mang libraries cũ chỉ có `javax.servlet.Filter` hoặc ép Tomcat/Jetty phiên bản không tương thích, có thể gặp `NoClassDefFoundError`, `ClassCastException`, `NoSuchMethodError` hoặc startup failure khi factory/server được tạo. **Không gộp mọi lỗi nâng cấp vào “missing factory”**; xem nested cause thực.

Sửa đúng là đồng bộ **Spring Boot BOM + server implementation + Servlet API + third-party filters/security libraries**. Không chỉ đổi chuỗi `javax` thành `jakarta` trong vài imports rồi giữ mọi dependency cũ.

### 7.4. Nâng Boot 3 → Boot 4

Các starter/module/packages và baseline thay đổi theo major version. Khi nâng cấp:
1. Đọc upgrade guide và dependency BOM đúng nhánh.
2. Không copy chính xác FQN của `ServletWebServerFactoryAutoConfiguration`/type imports từ Boot 3.5 vào Boot 4.x mà chưa kiểm tra.
3. Không trộn một số `spring-boot-*.jar` 3.x với 4.x để “giữ” embedded server.
4. Kiểm tra Servlet/Reactive web type và supported embedded servers của **đúng release**, không dựa vào bảng Boot 3.5.
5. Chạy cả `@SpringBootTest(RANDOM_PORT)` và packaged `java -jar` smoke tests.
6. Test WAR/deploy container nếu sử dụng external Servlet engine.

## 8. Phân biệt các lỗi dễ bị gom chung

| Hiện tượng / log | Lớp lỗi | Hướng kiểm tra đầu tiên |
| --- | --- | --- |
| `missing ServletWebServerFactory bean` | **Không có** factory cho Servlet context | Auto-config, starter container, context class/type |
| `missing ReactiveWebServerFactory bean` | **Không có** reactive factory | WebFlux/runtime dependencies, REACTIVE type, reactive auto-config |
| `multiple ServletWebServerFactory beans` | **Nhiều** factory cùng kiểu | Custom `@Bean` trùng với auto-config hoặc hơn một server implementation |
| `Port 8080 was already in use` | Factory tồn tại nhưng **bind socket thất bại** | PID/listening process/server.port/network |
| `Unable to start web server` | Wrapper, có thể bao nhiều nguyên nhân | Đọc **Caused by** cuối hoặc failure analysis |
| `NoClassDefFoundError: jakarta/servlet/...` | Classpath/runtime incompatibility | Servlet API/starter version/scope |
| `BeanCreationException` ở customizer | Factory hoặc option bean khởi tạo lỗi | SSL/keystore/port/custom code |
| `NoSuchMethodError` liên quan Tomcat/Jetty | Binary version mismatch | BOM, dependency overrides, duplicate JARs |
| `Started Application` nhưng không có HTTP port | Có thể `WebApplicationType.NONE`, `server.port=-1` hoặc wrong port | Effective properties, context type, listening sockets |
| HTTP `404 Not Found` | Server đã nhận request, router không tìm handler/resource | Controller scan, path mapping, context path, security/proxy |
| HTTP `503` khi shutdown | Runtime đang drain hoặc downstream unavailable | Graceful shutdown/health/proxy |
| `ApplicationContextException` khi runner lỗi | Startup sau refresh bị failure | Runner/error chain, không tự quy là missing factory |
| `@WebMvcTest` pass nhưng packaged jar fail | Slice không khởi động embedded server | Real HTTP integration + artifact runtime classpath |
| Reactive `Mono` controller compile nhưng Boot chọn SERVLET | Framework mix | Check both web starters and web application type |
| Bean factory nằm trong parent context | Context hierarchy ownership | Kiểm tra factory đúng child context cần server |
| Lỗi chỉ Docker/container | Build image khác runtime hoặc host-port mapping | Inspect packaged JAR/image/dependencies/entrypoint |

**Đừng “fix” bằng những hành động ở tầng không liên quan.** Thay `server.port=0` chỉ giúp port conflict; thêm `@RestController` chỉ giúp endpoint mapping; thay `server.shutdown=immediate` chỉ đổi shutdown behavior; không hành động nào tự làm xuất hiện một bean `ServletWebServerFactory` đã bị loại.

## 9. Quy trình gỡ lỗi 12 bước, có thứ tự và kết luận cụ thể

### Bước 1: Lấy full stack trace, đặc biệt dòng nguyên nhân

Phải xác định exact:
- `ServletWebServerApplicationContext` hay `ReactiveWebServerApplicationContext`?
- missing factory hay multiple factories?
- root `Caused by` là `BindException`, classpath error, `IllegalStateException` hay `BeanCreationException`?
- `ApplicationFailedEvent`, exit code và build artifact nào?
- lỗi xảy ra local IDE, `mvn spring-boot:run`, `java -jar`, Docker hay external WAR?

Không debug qua ảnh screenshot cắt mất 20 dòng `Caused by` quan trọng.

### Bước 2: Xác minh yêu cầu thực: cần HTTP server hay chạy CLI/job?

Nếu là batch:
~~~properties
spring.main.web-application-type=none
~~~

đúng thiết kế. Nếu cần API, `NONE` không phải fix. Ghi nhận effective profile/property, deployment flags, `SpringApplication.setWebApplicationType`.

### Bước 3: Xem classpath runtime, không chỉ pom.xml hiển thị

~~~bash
mvn dependency:tree
mvn help:effective-pom
~~~

Tìm `spring-boot-starter-web` hoặc `spring-boot-starter-webflux`, embedded container starter, exclusions, scopes, version overrides. Nếu chạy Gradle, dùng `runtimeClasspath` và `dependencyInsight`.

### Bước 4: Chọn đúng web type

- MVC app → `SERVLET`.
- WebFlux server → `REACTIVE`.
- Non-web tool → `NONE`.
- Có cả MVC/WebFlux → mặc định MVC/SERVLET trừ cấu hình khác.

Không thay type chỉ vì exception có chữ “reactive” hoặc “servlet” trong một method name, xem context type thực.

### Bước 5: Kiểm tra main/source configuration

Có `@SpringBootApplication` hoặc `@EnableAutoConfiguration` không? `SpringApplication.run(...)` được gọi với **class nào**? Có custom `SpringApplicationBuilder`/parent-child contexts không? Có test-specific bare `@Configuration` replace primary config không?

### Bước 6: Tìm exclude của auto-config

Tìm trong source/config/profiles/CLI:
~~~text
ServletWebServerFactoryAutoConfiguration
ReactiveWebServerFactoryAutoConfiguration
spring.autoconfigure.exclude
@SpringBootApplication(exclude = ...)
@EnableAutoConfiguration(exclude = ...)
~~~

Nếu thấy exclude, hỏi **tại sao** và bỏ khi không có lý do chính đáng. Không tự thêm factory để “đi vòng” exclude ngầm.

### Bước 7: In Condition Evaluation Report

Chạy từ executable JAR:

~~~bash
java -jar target/server-factory-lab-0.0.1-SNAPSHOT.jar \
  --debug \
  --server.port=0
~~~

`--debug` của Boot bật conditions report cho auto-configuration, có **positive matches** và **negative matches**. Tra:
- `ServletWebServerFactoryAutoConfiguration`;
- `ServletWebServerFactoryConfiguration.EmbeddedTomcat`/`EmbeddedJetty`/`EmbeddedUndertow`;
- `ReactiveWebServerFactoryAutoConfiguration` và reactive server nested conditions;
- `@ConditionalOnClass`, `@ConditionalOnWebApplication`, `@ConditionalOnMissingBean`.

Khi lỗi không chạy được tới Actuator, **startup conditions report + dependency tree** là công cụ chính. Nếu app đã startup và Actuator conditions endpoint được expose an toàn, `/actuator/conditions` hỗ trợ xem condition outcomes. **Không expose endpoint này public** vì nó tiết lộ classpath/bean config. Bật local/dev với security policy nếu cần.

### Bước 8: Xác minh factory được tạo trong *đúng context*

Khi app đã chạy, có thể kiểm tra `getBeanNamesForType(ServletWebServerFactory.class)` hoặc reactive equivalent. Với missing factory error, code `ApplicationRunner` sẽ **không chạy tới** nếu startup fail trước refresh; phải dùng condition report/early listener hoặc isolated context test, không chờ runner log.

### Bước 9: Kiểm tra runtime packaged artifact

~~~bash
mvn clean package
jar tf target/server-factory-lab-0.0.1-SNAPSHOT.jar
~~~

Tìm container JAR trong `BOOT-INF/lib/`. So với artifacts thực trong Docker image/CI; không suy ra runtime giống local IDE.

### Bước 10: So positive real HTTP test với negative injection

Positive test `@SpringBootTest(RANDOM_PORT)` chứng minh factory + connector + route. Negative test không auto-config cho biết missing factory path hoạt động. Nếu positive pass nhưng production fail, so classpath/profiles/startup source/environment/packaging.

### Bước 11: Nếu chuyển server, đổi dependency thành một lựa chọn nhất quán

Tomcat mặc định cho MVC; nếu chuyển Jetty/Undertow, exclude Tomcat và thêm đúng starter tương ứng cho **Boot 3.5**. Nếu dùng Reactive, dùng reactive runtime phù hợp. Không mix nhiều factory beans hoặc ép versions server thủ công.

### Bước 12: Chốt regression tests và quan sát phiên bản triển khai

Đưa `RANDOM_PORT` smoke test vào CI, kiểm tra packaged JAR, liveness/readiness và start logs. Với deployment có reverse proxy, test public path và load balancer tách biệt. Chỉ xem task “sửa xong” khi app **startup và nhận HTTP request thật** nếu nhu cầu là HTTP server.

## 10. Project mẫu Java 17/Maven: factory đúng và tests tái hiện lỗi

**Mục tiêu:** Một project **runnable**, không yêu cầu DB/external services:
- Boot main bình thường tạo embedded Tomcat `ServletWebServerFactory`.
- Endpoint `GET /ping` trả `pong`.
- `RuntimeInspector` in tên/số lượng factory beans và actual port sau startup.
- `HealthyWebServerTest` chứng minh server thật và một factory.
- `MissingFactoryTest` cố ý bootstrap Servlet context bằng **plain `@Configuration` không auto-config**, tạo lỗi thiếu factory có kiểm soát.
- `NonWebModeTest` cho thấy `NONE` khởi động **không yêu cầu** web server.
- Có lệnh `--spring.autoconfigure.exclude=...` để tái hiện lỗi từ chính executable JAR mà không sửa code chính.

**Cây thư mục:**

~~~text
server-factory-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/serverfactory/
    │   │   ├── DemoApplication.java
    │   │   ├── PingController.java
    │   │   └── RuntimeInspector.java
    │   └── resources/application.properties
    └── test/java/com/example/serverfactory/
        ├── HealthyWebServerTest.java
        ├── MissingFactoryTest.java
        └── NonWebModeTest.java
~~~

### 10.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>server-factory-lab</artifactId>
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
            <artifactId>spring-boot-starter-actuator</artifactId>
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

Đây là **POM đầy đủ** cho embedded servlet + test. Không thêm `spring-boot-starter-webflux` hoặc Jetty chỉ vì muốn debug một servlet app. Starter web có embedded Tomcat mặc định và Spring MVC auto-config.

### 10.2. `src/main/java/com/example/serverfactory/DemoApplication.java`

~~~java
package com.example.serverfactory;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` được đặt ở root package `com.example.serverfactory` để scan `PingController`/`RuntimeInspector` bên dưới. Không đổi thành `@Configuration` thuần ở ứng dụng chính, vì như vậy không có Boot auto-configuration tạo server factory.

### 10.3. `src/main/java/com/example/serverfactory/PingController.java`

~~~java
package com.example.serverfactory;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {
    @GetMapping(value = "/ping",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String ping() {
        return "pong\n";
    }
}
~~~

`PingController` là Spring MVC handler **sau khi Tomcat và DispatcherServlet đã được tạo**. Nếu context thiếu factory, endpoint không bao giờ được serve. Nếu server start nhưng `/ping` 404, đó là bài toán mapping/package scan, khác với missing factory.

### 10.4. `src/main/java/com/example/serverfactory/RuntimeInspector.java`

~~~java
package com.example.serverfactory;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.boot.web.servlet.server.ServletWebServerFactory;
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class RuntimeInspector implements ApplicationRunner {
    private static final Logger log =
            LoggerFactory.getLogger(RuntimeInspector.class);

    private final ApplicationContext context;

    public RuntimeInspector(ApplicationContext context) {
        this.context = context;
    }

    @Override
    public void run(ApplicationArguments args) {
        String[] names =
                context.getBeanNamesForType(ServletWebServerFactory.class);
        log.info("SERVLET_FACTORY_COUNT={}", names.length);
        for (String name : names) {
            log.info("SERVLET_FACTORY_BEAN={} TYPE={}",
                     name, context.getType(name).getName());
        }

        if (context instanceof ServletWebServerApplicationContext web) {
            log.info("WEB_CONTEXT_TYPE={}",
                     web.getClass().getSimpleName());
            log.info("HTTP_PORT={}", web.getWebServer().getPort());
        } else {
            log.info("NON_SERVLET_WEB_CONTEXT={}",
                     context.getClass().getSimpleName());
        }
    }
}
~~~

**Lưu ý compile:** `ServletWebServerFactory` package Boot 3.5 là `org.springframework.boot.web.servlet.server.ServletWebServerFactory`; `ServletWebServerApplicationContext` package là `org.springframework.boot.web.servlet.context`. Không copy nguyên package FQN theo Boot 4 docs vào Boot 3.5.

**Vì sao inspector không tự “sửa” lỗi?** `ApplicationRunner` chỉ chạy **sau context refresh thành công**. Nếu context fail lúc tìm ServletWebServerFactory, inspector chưa được gọi. Khi startup success, inspector hữu ích để kiểm tra:
- một factory bean trên Servlet context;
- implementation bean name/type (thường Tomcat);
- web context class;
- actual listening port do factory/web server tạo.

Ví dụ các dòng log **dạng kỳ vọng**, không phải capture:

~~~text
SERVLET_FACTORY_COUNT=1
SERVLET_FACTORY_BEAN=tomcatServletWebServerFactory TYPE=org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory
WEB_CONTEXT_TYPE=AnnotationConfigServletWebServerApplicationContext
HTTP_PORT=8080
~~~

Tên bean, ordering và logger prefix có thể khác khi tùy biến. **Đừng assert exact toàn bộ log lines**; test trực tiếp bean type/HTTP response để ổn định hơn.

### 10.5. `src/main/resources/application.properties`

~~~properties
spring.application.name=server-factory-lab
server.address=127.0.0.1
server.port=8080

management.endpoints.web.exposure.include=health
logging.level.com.example.serverfactory=INFO
~~~

Chỉ bind loopback cho lab vì `/ping` chưa có authentication. Khi chạy container/Kubernetes, `127.0.0.1` là loopback **của container**; phải override bằng bind address/network policy phù hợp trước khi dùng Pod IP. Cổng được override thành 0 trong JUnit `RANDOM_PORT`.

### 10.6. `HealthyWebServerTest.java` — positive real HTTP integration

File `src/test/java/com/example/serverfactory/HealthyWebServerTest.java`:

~~~java
package com.example.serverfactory;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.boot.web.servlet.server.ServletWebServerFactory;
import org.springframework.context.ApplicationContext;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class HealthyWebServerTest {

    @LocalServerPort
    int port;

    @Autowired
    ApplicationContext context;

    @Autowired
    ServletWebServerFactory factory;

    @Test
    void servletFactoryAndRealHttpServerAreAvailable() {
        assertInstanceOf(TomcatServletWebServerFactory.class, factory);
        assertInstanceOf(ServletWebServerApplicationContext.class,
                         context);

        assertEquals(1,
                context.getBeanNamesForType(
                        ServletWebServerFactory.class).length);
        assertTrue(port > 0);

        String body = RestClient.create().get()
                .uri("http://127.0.0.1:" + port + "/ping")
                .retrieve()
                .body(String.class);
        assertEquals("pong\n", body);
    }
}
~~~

**Điểm test này thực sự chứng minh:**
- `@SpringBootTest(RANDOM_PORT)` khởi động embedded Tomcat thật, tránh hard-code cổng.
- Context thuộc họ ServletWebServerApplicationContext.
- Có **một** bean `ServletWebServerFactory` và default implementation là Tomcat theo POM.
- HTTP GET thực qua socket trả JSON? **Không**: endpoint ở đây trả plain text `pong\n`; assertion đúng body này.
- `RestClient.create()` dùng trong test như HTTP client bình thường, không cần tracing auto-config ở demo.

Không kiểm tra chỉ bằng một `MockMvc.perform(get("/ping"))` vì nó có thể chạy khi không có HTTP port thật. Với một project đã chọn Jetty/Undertow, thay assertion Tomcat bằng factory phù hợp thay vì bỏ hết integration tests.

### 10.7. `MissingFactoryTest.java` — tạo chính lỗi thiếu factory

File `src/test/java/com/example/serverfactory/MissingFactoryTest.java`:

~~~java
package com.example.serverfactory;

import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MissingFactoryTest {

    // Cố ý không gắn @EnableAutoConfiguration/@SpringBootApplication.
    // Lớp này độc lập và không thay main DemoApplication.
    @Configuration(proxyBeanMethods = false)
    static class BareServletConfiguration {
    }

    @Test
    void bareServletContextFailsWithMissingFactory() {
        SpringApplication app =
                new SpringApplication(BareServletConfiguration.class);
        app.setWebApplicationType(WebApplicationType.SERVLET);
        app.setBannerMode(Banner.Mode.OFF);

        AtomicReference<Throwable> failure =
                new AtomicReference<>();
        app.addListeners(
            (ApplicationListener<ApplicationFailedEvent>) event ->
                failure.set(event.getException()));

        RuntimeException thrown = assertThrows(
                RuntimeException.class,
                () -> app.run(
                    "--server.port=0",
                    "--spring.main.log-startup-info=false"));

        assertNotNull(thrown);
        assertNotNull(failure.get(),
                "Expected ApplicationFailedEvent");
        assertTrue(hasMessage(failure.get(),
                "ServletWebServerFactory"),
                "Missing factory reason should appear in cause chain");
    }

    private static boolean hasMessage(
            Throwable error, String needle) {
        for (Throwable e = error;
             e != null; e = e.getCause()) {
            if (String.valueOf(e.getMessage()).contains(needle)) {
                return true;
            }
        }
        return false;
    }
}
~~~

**Vì sao test âm tính đáng tin?**
1. Project test classpath **có** `spring-boot-starter-web`/Tomcat, nên Servlet APIs khả dụng.
2. `setWebApplicationType(SERVLET)` khiến Boot tạo Servlet web-server context thay vì tình cờ chọn NONE.
3. `BareServletConfiguration` chỉ có `@Configuration`, không bật `@EnableAutoConfiguration`.
4. Không có auto-config tạo `ServletWebServerFactory`, nên startup fail **trước khi bind port**.
5. Test bắt `ApplicationFailedEvent` qua listener đăng ký **trước `run`**, bởi bean listener trong context có thể chưa tồn tại khi lỗi xảy ra.
6. Test xem cause chain có tên factory, không so exact message do version changes.

**Không cố ý gọi lại `app.run()` trong test này để “chữa” lỗi**, và không thêm một `@Bean` factory vào BareServletConfiguration: khi đó mất đúng tình huống cần tái hiện. Positive path đã có HealthyWebServerTest riêng.

### 10.8. `NonWebModeTest.java` — NONE không cần factory

File `src/test/java/com/example/serverfactory/NonWebModeTest.java`:

~~~java
package com.example.serverfactory;

import org.junit.jupiter.api.Test;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.boot.web.servlet.server.ServletWebServerFactory;
import org.springframework.context.ConfigurableApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class NonWebModeTest {

    @Test
    void noneModeRunsWithoutServletFactory() {
        SpringApplication app =
                new SpringApplication(DemoApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);

        try (ConfigurableApplicationContext context =
                app.run("--server.port=0")) {
            assertFalse(
                context instanceof ServletWebServerApplicationContext);

            assertEquals(0,
                context.getBeanFactory().getBeanNamesForType(
                    ServletWebServerFactory.class).length);
        }
    }
}
~~~

**Ý nghĩa:** `NONE` không phải “missing factory startup failure”. Đây là **non-web context** được tạo thành công; vì vậy không có factory/HTTP port là **expected behavior**. Nếu app server production bất ngờ không listen, kiểm tra `spring.main.web-application-type=none` hoặc programmatic WebApplicationType override trước khi thay dependencies.

**Không dùng `NONE` như test thay thế** `@SpringBootTest(RANDOM_PORT)` cho một API cần nhận request: test non-web có thể pass khi app HTTP thực đã hỏng.

### 10.9. Chạy tests/ứng dụng

~~~bash
java -version
mvn clean test
mvn clean package
java -jar target/server-factory-lab-0.0.1-SNAPSHOT.jar
~~~

Ở terminal thứ hai:

~~~bash
curl -i http://127.0.0.1:8080/ping
~~~

**Kỳ vọng dạng response:**

~~~http
HTTP/1.1 200
Content-Type: text/plain;charset=UTF-8

pong
~~~

Body thật có newline cuối từ Java `"pong\n"`, header formatting và case có thể khác giữa embedded server versions. Không lấy `HTTP/1.1 200` làm output capture đã đo — đây là **expected semantics** của code.

### 10.10. Tái hiện missing factory bằng CLI trên cùng JAR

**Chỉ dùng trên máy lab, không trong production config:**

~~~bash
java -jar target/server-factory-lab-0.0.1-SNAPSHOT.jar \
  --spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.web.servlet.ServletWebServerFactoryAutoConfiguration \
  --server.port=0 \
  --debug
~~~

Khi auto-configuration tạo factory bị exclude, Servlet web context vẫn yêu cầu factory nên **startup dự kiến fail** với lỗi nhắc `ServletWebServerFactory`. Dòng lỗi chi tiết/phân tích phụ thuộc Boot version; bạn sẽ thấy lý do trực tiếp từ conditions/logs.

Để sửa, **bỏ option `--spring.autoconfigure.exclude=...`**, chạy lại JAR bình thường. Đây là minh chứng tại chỗ rằng thêm `@RestController`, đổi port hoặc thêm `WebServerFactoryCustomizer` không thay cho auto-configuration đúng.

## 11. Nếu thật sự cần WebFlux: project đối chiếu reactive tối thiểu

Đây là **một project khác**, không trộn các dependencies với servlet project chính. Một WebFlux server trong Boot 3.5:

**Maven dependency mảnh:**

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

**Main class:**

~~~java
package com.example.reactivedemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveApplication.class, args);
    }
}
~~~

**Reactive controller:**

~~~java
package com.example.reactivedemo;

import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReactiveController {
    @GetMapping("/ping")
    public Mono<String> ping() {
        return Mono.just("reactive-pong\n");
    }
}
~~~

Với đúng dependency/reactive web application type, Boot chọn `ReactiveWebServerApplicationContext` và thường có `NettyReactiveWebServerFactory` từ Reactor Netty. **Đây là mảnh ví dụ đối chiếu**, không phải project standalone đầy đủ vì chưa có riêng parent POM/directory/properties/test. Nếu cần chạy project này, dùng Maven parent/POM tương tự mục 10 nhưng thay `spring-boot-starter-web` bằng `spring-boot-starter-webflux`, đổi `groupId/artifactId` và đặt hai classes vào cùng package root. Không giữ servlet starter nếu mục đích là test pure WebFlux selection.

**Test ý tưởng:**

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "spring.main.web-application-type=reactive"
)
class ReactiveHttpTest {
    @LocalServerPort int port;
    // Dùng HTTP client gọi localhost:port/ping và
    // kiểm tra ReactiveWebServerFactory bean trong context.
}
~~~

Đây là **mảnh test minh họa**, không copy như một class compile được vì chưa có đầy đủ imports/body. Với WebFlux, `@WebFluxTest` là slice test tương đương ở web reactive layer, **không** prove port runtime. Nếu gặp lỗi missing `ReactiveWebServerFactory`, kiểm tra reactive runtime/transitives và `ReactiveWebServerFactoryAutoConfiguration`, không thêm Servlet-specific bean.

### 11.1. Một ứng dụng có cả MVC và WebFlux có phải lỗi?

Không nhất thiết. Một MVC app có thể dùng `WebClient` (và dependency WebFlux) để thực hiện HTTP outbound mà vẫn chạy Tomcat + DispatcherServlet. Tuy nhiên bạn phải biết server đang chạy stack nào; một method trả `Mono` trong controller không tự nghĩa server Netty.

**Phân biệt:**
- **MVC server + WebClient:** servlet factory thuộc Tomcat, reactive client là client library.
- **WebFlux server + Reactor Netty:** reactive factory thuộc Netty.
- **Reactive server chạy Tomcat/Jetty:** cần **reactive factory** tương ứng, không phải servlet factory vì cùng tên container.
- **Non-web scheduled job dùng WebClient:** có thể đặt `WebApplicationType.NONE`, không cần HTTP listener.

## 12. Spring Boot Actuator, --debug và Conditions report

### 12.1. Bật điều tra tự động an toàn

Chạy local:

~~~bash
java -jar target/server-factory-lab-0.0.1-SNAPSHOT.jar \
  --debug \
  --server.port=0
~~~

Khi `--debug` bật, Spring Boot có thể in **CONDITIONS EVALUATION REPORT**, gồm:
- Positive matches: auto-configuration conditions đã được thỏa.
- Negative matches: loại vì thiếu class, bean đã tồn tại, sai web type, property không match.
- Unconditional classes.

Nếu `ServletWebServerFactoryAutoConfiguration` xuất hiện positive nhưng nested `EmbeddedTomcat` negative, điều tra embedded server classes/dependencies. Nếu cả servlet factory auto-config negative do **Not a servlet web application**, kiểm tra application type. Nếu Boot nói custom factory bean đã có, điều tra bean đó có đúng type và nằm trong context đang được tạo server không.

**Không phân tích report theo một keyword duy nhất.** Conditions report chỉ nói vì sao các điều kiện match/not match tại thời điểm evaluation; cần kết hợp runtime bean count và actual exception.

### 12.2. Actuator `conditions` không phải công cụ duy nhất

Nếu app còn startup thành công, có thể cấu hình nội bộ:

~~~properties
management.endpoints.web.exposure.include=health,conditions
~~~

Sau đó, với authorization thích hợp, xem `GET /actuator/conditions` để xem condition outcomes. **Không** mở endpoint này không auth trên internet; nó tiết lộ runtime classpath/configuration topology. Khi app fail trước khi tạo HTTP server, endpoint không có để query; sử dụng `--debug`/early listener/CI logs.

### 12.3. ConditionEvaluationReport trong Java (mảnh nâng cao)

Khi context đã refresh:

~~~java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(
                configurableContext.getBeanFactory());
~~~

Import `org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport`, `ConfigurableApplicationContext`; đoạn này là **mảnh minh họa**, phải có `configurableContext` đúng type. Trong test auto-configuration có thể dùng `ApplicationContextRunner` + `ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)` để log outcomes.

**Đừng đặt code trên trong `ApplicationRunner` rồi mong nó debug context không thể start**: runner chưa được thực thi khi context fail sớm. Với startup-failure diagnostics, listener được register trước `SpringApplication.run` và Boot `--debug` hữu ích hơn.

### 12.4. Tại sao test slice không cần factory?

Theo Boot testing docs, `@WebMvcTest` tạo MVC slice được auto-configured với `MockMvc`, không cần real embedded server. `@SpringBootTest(MOCK)` tạo mock servlet environment. **Missing ServletWebServerFactory chỉ có ý nghĩa khi bạn đang khởi tạo một ServletWebServerApplicationContext thật**; việc không thấy bean factory trong slice không phải một “failure” phải sửa.

## 13. WAR, scope provided và external container

Ví dụ traditional WAR với embedded Tomcat dependency `provided`:

~~~xml
<packaging>war</packaging>

<!-- ... project dependencies ... -->

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
~~~

Cần class kế thừa `SpringBootServletInitializer`, packaging WAR đúng, external Servlet container phiên bản tương thích với Boot 3.5/Jakarta Servlet API. Đây là **mảnh** POM, không thay thế full WAR guide.

**Bẫy:**
- Chạy `java -jar app.jar` đã được build như executable JAR nhưng không đóng gói embedded container rồi mong ngoại cảnh Tomcat tự xuất hiện.
- Thấy `provided` trong traditional WAR rồi xóa ngay: có thể sai với deployment target.
- Trộn WAR deploy vào external Tomcat cũ không hỗ trợ Jakarta EE 10/Servlet 6: có thể classloading fail khác missing factory.
- Đóng gói executable WAR với Spring Boot plugin có `WEB-INF/lib-provided` cho provided embedded server; nó vẫn có thể chạy bằng `java -jar app.war` theo docs. Vì vậy câu “provided luôn mất runtime container” là **sai**.

**Chọn deployment model trước khi chọn scope:** embedded runnable JAR khác external WAR. Kiểm chứng artifact và entrypoint thực trong CI/staging, không chỉ build local.

## 14. Nâng cấp và sự phụ thuộc phiên bản

### 14.1. Thay server implementation

Khi thay Tomcat sang Jetty/Undertow trong **Boot 3.5**, sử dụng Boot starters đúng version BOM. Test:
- Có đúng một `ServletWebServerFactory` bean.
- Factory type đúng với server đã chọn.
- `GET /ping` thực sự trả 200 qua random port.
- Session/SSL/HTTP2/static/Actuator vẫn hoạt động như contract.
- Lifecycle graceful shutdown được test theo server behavior mới.

**Đừng copy** factory bean class name trong docs Boot khác major version. Hãy xem API và dependency graph tương ứng.

### 14.2. Dependency override và binary mismatch

Một parent POM/Gradle constraints có thể ép `tomcat-embed-core` hoặc `jetty-server` sang version khác Boot BOM. Kết quả có thể là `NoSuchMethodError`/`LinkageError` ngay khi khởi tạo factory, hoặc condition mismatch, **không** nhất thiết là missing bean. Lựa chọn ổn định: để Spring Boot dependency management pin versions đồng bộ, override chỉ khi có matrix tương thích đã kiểm thử.

### 14.3. Native image / AOT

Với GraalVM native image, runtime classpath/reflective hints và **build-time application type** cần nhất quán. Nếu image được build với `WebApplicationType.NONE` rồi lúc chạy cố đổi sang `SERVLET`, các classes/bean definitions cho web server có thể không được đưa vào image. Đây không giống một JVM JAR có full classpath. Spring Boot issue tracker từng cảnh báo cần đặt web application type đúng **lúc build native image**, không chỉ trên command-line runtime.

**Quy trình:** xác định intended web type trước AOT/native build, giữ cùng configuration tại runtime, chạy native image smoke test `GET /ping`. Không thêm runtime `--spring.main.web-application-type=servlet` vào một binary đã được optimize cho NONE rồi mong factory xuất hiện.

## 15. Các anti-pattern cần tránh

1. **Thêm thủ công `@Bean TomcatServletWebServerFactory` ngay khi thấy missing factory.** Nó có thể che auto-config/exclusion/scope sai và tạo double factories về sau.
2. **Đổi `server.port=0` để sửa missing bean.** Random port chỉ xử lý bind collision sau khi factory tồn tại.
3. **Gắn `@RestController` rồi mong có Tomcat.** Controllers xử lý requests, không tạo HTTP listener.
4. **Dùng `WebServerFactoryCustomizer` để chữa missing factory.** Customizer không phải factory bean.
5. **Bỏ `@SpringBootApplication` thành `@Configuration` chỉ vì muốn tối giản bootstrap.** Cần hiểu auto-configuration imports.
6. **Gắn `@EnableWebMvc`/`@EnableWebFlux` bừa.** Chúng điều chỉnh web framework configuration, không thay thế embedded server runtime.
7. **Ep `WebApplicationType.SERVLET` khi chỉ có reactive runtime.** Hai factory interfaces khác nhau, không có chuyển đổi tự động Netty → Servlet.
8. **Thêm cả Tomcat, Jetty và Undertow để thử xem cái nào chạy.** Có thể tạo điều kiện không mong muốn hoặc nhiều candidates, khó audit.
9. **Chỉ chạy `@WebMvcTest` rồi phát hành Docker image.** Test slice không phát hiện runtime packaging và port bind failures.
10. **Thêm `@ComponentScan` trùm mọi thứ để “lộ bean”.** Có thể gây bean conflicts/circular dependencies, không phải giải pháp nguyên nhân auto-config.
11. **Đọc mỗi dòng top-level `Unable to start web server`.** Phải xem deepest cause và condition report.
12. **Đồng nhất external WAR với executable JAR.** Scope/container ownership khác nhau.
13. **Nhét javax.servlet JAR cũ vào Spring Boot 3.5.** Jakarta namespace khác, dễ lỗi binary.
14. **Dùng `server.port=-1` để tránh lỗi factory.** Nó giữ web context nhưng không expose HTTP endpoints.
15. **Bỏ Actuator security để xem `/conditions`.** Chỉ expose trong mạng nội bộ với auth.
16. **Cho máy production tự sửa dependencies khi runtime fail.** Dependency resolution và container image phải tái lập được từ CI.
17. **Lấy thiếu factory trong @WebMvcTest làm lỗi.** Slice không yêu cầu embedded server; đúng tầng test mới quan trọng.
18. **Phụ thuộc chính xác failure log string cho mọi Boot versions/OS.** Test cause/type/missing-bean behavior thay vì toàn bộ stack trace literal.

## 16. Bảng chẩn đoán theo tình huống thực tế

| Bối cảnh | Cơ chế thường gặp | Cách sửa/kiểm chứng |
| --- | --- | --- |
| Mới tạo một controller và chạy bằng `@Configuration` main | `@EnableAutoConfiguration` thiếu | Dùng `@SpringBootApplication`/auto config thích hợp |
| Boot MVC build nhưng `missing ServletWebServerFactory` | Container dependency bị exclude hoặc factory auto-config không match | Maven runtime tree + conditions report |
| `spring-boot-starter-web` bị exclude Tomcat | Không còn Servlet container default | Thêm Jetty/Undertow starter hoặc khôi phục Tomcat |
| `spring.autoconfigure.exclude` chứa Servlet factory auto-config | Factory deliberately disabled | Bỏ exclude nếu yêu cầu embedded HTTP |
| Chạy worker CLI, log không có HTTP port | `WebApplicationType.NONE` | Bình thường nếu không cần web |
| Chạy API nhưng `NONE` từ profile env | Non-web context, không có endpoint | Bỏ/đổi override thành web type đúng |
| Chạy Servlet với only Reactor Netty | Reactive runtime không phải Servlet factory | Đổi stack hoặc thêm đúng Servlet container |
| Chạy WebFlux exclude Reactor Netty | Không có reactive HTTP factory | Khôi phục Netty hoặc dùng server reactive thay thế |
| Cả starters MVC + WebFlux | Boot mặc định chọn MVC | Xác định chủ đích, cấu hình reactive nếu muốn |
| JUnit custom @Configuration + RANDOM_PORT | Mất Boot primary auto-config | Chỉ rõ main @SpringBootApplication hoặc dùng @TestConfiguration |
| Tự tạo child Servlet web context | Factory không nằm trong context đó | Đưa auto-config/factory đúng child |
| Custom ServletWebServerFactory @Bean | Default backoff, có thể 2 beans | Kiểm tra factory count/type và ownership |
| Nâng Boot 2→3, filter còn javax.servlet | Binary incompatibility Jakarta | Nâng third-party library/server API đúng |
| Nâng Boot 3→4, giữ package auto-config cũ | Class/package moved, auto-config không phù hợp | Follow migration docs và BOM mới |
| Native image build NONE, runtime ép SERVLET | AOT không chứa web classes/beans cần thiết | Rebuild native image với web type đúng |
| Tomcat đã tồn tại nhưng `Port 8080 in use` | Bind socket conflict, factory **đã tồn tại** | Check PID/port, `server.port`, `RANDOM_PORT` |
| App startup nhưng GET 404 | Controller scan/route/static/security | Debug mapping, không đổi server factory |
| Không vào được từ container host | Bind localhost hoặc Docker port publish | `server.address`/ports/network |
| Boot JVM jar chạy, Docker image fail | Artifact/classpath/layer khác | Inspect BOOT-INF/lib và image contents |
| Executable WAR có Tomcat provided | lib-provided theo Boot plugin | Đọc WAR deploy model, không coi provided luôn sai |

## 17. Checklist kiểm tra cuối cùng

**Chủ đích:** HTTP service cần nhánh MVC/Servlet, WebFlux/Reactive hay CLI không web?

- [ ] Có exact stack trace và deepest `Caused by`.
- [ ] Xác định `SERVLET`, `REACTIVE` hay `NONE` effective (classpath + properties + API override).
- [ ] Xác định context type tại runtime, không suy đoán từ controllers.
- [ ] MVC có `spring-boot-starter-web`, embedded Tomcat hoặc Jetty/Undertow tương thích.
- [ ] Reactive có WebFlux + một reactive HTTP server implementation.
- [ ] `@SpringBootApplication`/`@EnableAutoConfiguration` còn hoạt động cho Boot context cần server.
- [ ] Không exclude nhầm factory auto-configuration.
- [ ] Condition report giải thích embedded server nested conditions.
- [ ] Factory đúng **một** bean trong đúng context khi embedded server cần.
- [ ] Không có dependency scope/exclusion/BOM override làm runtime thiếu classes.
- [ ] Không nhầm servlet factory với reactive factory.
- [ ] Không dùng custom `WebServerFactoryCustomizer` như biện pháp tạo missing bean.
- [ ] Servlet/Jakarta versions tương thích Spring Boot 3.x.
- [ ] Test `@SpringBootTest(RANDOM_PORT)` gọi HTTP thật qua `/ping`.
- [ ] Test negative missing factory/failure event ở isolated context đúng mục tiêu.
- [ ] Kiểm tra `server.port=-1` khác `NONE` và `server.port=0`.
- [ ] Packaged executable JAR/WAR có dependency runtime đúng và entrypoint phù hợp.
- [ ] Khi chạy container, bind address/expose port/ingress đúng và security đầy đủ.
- [ ] Native/AOT build-time web type nhất quán với runtime.
- [ ] Có CI smoke test cho version nâng cấp, factory type, HTTP port và startup failure.

## 18. Câu hỏi tự kiểm tra

1. `ServletWebServerFactory` khác `DispatcherServlet` ở trách nhiệm nào?
2. `ServletWebServerApplicationContext` cần bao nhiêu factory beans?
3. Một app có `@RestController` có đồng nghĩa sẽ tự có Tomcat không?
4. Factory reactive và servlet có dùng thay nhau được không?
5. `spring-boot-starter-web` thường đưa embedded server nào vào runtime?
6. Exclude Tomcat mà không thêm server thay thế có thể dẫn đến những dạng lỗi nào?
7. `@SpringBootApplication` gồm ba annotation cơ bản nào?
8. Tại sao `@Configuration` thuần làm Servlet context có thể thiếu factory?
9. `@EnableWebMvc` có mặc nhiên làm factory biến mất không?
10. `WebServerFactoryCustomizer` có tạo server factory không?
11. `spring.main.web-application-type=none` và `server.port=-1` khác nhau thế nào?
12. `server.port=0` có sửa missing factory không?
13. App có cả MVC và WebFlux thì Boot 3.5 mặc định chọn stack nào?
14. Trong `@WebMvcTest` không có ServletWebServerFactory có phải bug không?
15. `@SpringBootTest(webEnvironment=RANDOM_PORT)` chứng minh điều gì mà MockMvc không có?
16. Vì sao trong JUnit nested `@TestConfiguration` khác nested plain `@Configuration`?
17. Vì sao `ApplicationFailedEvent` listener nên được register trước run ở test failure?
18. Vì sao test missing factory dùng `WebApplicationType.SERVLET` explicit?
19. Lệnh nào giúp xem Maven runtime dependency graph và exclusions?
20. `--debug` cung cấp thông tin gì về auto-configuration?
21. Khi ServletWebServerFactoryAutoConfiguration positive nhưng EmbeddedTomcat negative, điều tra gì?
22. Vì sao không nên khai báo manual `@Bean TomcatServletWebServerFactory` để chữa mọi lỗi?
23. `Port 8080 was already in use` xảy ra ở bước nào so với tìm factory?
24. Nếu Boot log `Started Application` nhưng HTTP 404, có chắc thiếu factory không?
25. Mô hình external WAR có bắt buộc factory embedded lúc external Tomcat bootstrap không?
26. `provided` container starter trong executable WAR có thể được đóng gói thế nào?
27. Migration Boot 2→3 tác động namespace Servlet ra sao?
28. Một native image build non-web có thể bật web server chỉ bằng runtime property không?
29. `NoSuchMethodError` trong Tomcat factory thường gợi ý vấn đề gì?
30. Khi Spring Boot 3→4, có nên giữ nguyên tất cả imports/dependency names từ Boot 3.5 không?

**Đáp án tóm tắt:** (1) Factory tạo HTTP server, DispatcherServlet xử lý MVC requests. (2) Đúng một. (3) Không. (4) Không. (5) Tomcat. (6) Type detection khác, classpath/missing factory failures. (7) SpringBootConfiguration/EnableAutoConfiguration/ComponentScan. (8) Không bật Boot auto-config. (9) Không. (10) Không. (11) Non-web context vs web context không expose HTTP. (12) Không. (13) MVC/SERVLET. (14) Không, slice không startup embedded container. (15) Real web server/socket/bean context. (16) TestConfiguration thêm vào primary config, plain config có thể thay thế. (17) Context có thể chưa tạo khi startup fail. (18) Ép servlet context dù config tối giản. (19) mvn dependency:tree/help:effective-pom. (20) Positive/negative condition matches. (21) Embedded server classes và @ConditionalOnMissingBean. (22) Che root cause/double beans. (23) Sau factory, lúc bind socket. (24) Không, server chạy rồi nên là routing/port/proxy. (25) Không giống embedded JAR. (26) WEB-INF/lib-provided. (27) javax.servlet → jakarta.servlet. (28) Phải rebuild với đúng web type/closed-world config. (29) Version binary mismatch. (30) Không; đọc migration guide.

## 19. Tài liệu chính thức

- **Spring Boot 3.5 — Servlet Web Applications / ServletWebServerApplicationContext**, cơ chế tìm đúng một factory bean: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- **Spring Boot 3.5 — Embedded Web Servers**, đổi server, tắt HTTP, server.port=-1, random port, custom factory: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- **Spring Boot 3.5 — Testing Spring Boot Applications**, MOCK/RANDOM_PORT, web application type và nested @TestConfiguration: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- **Spring Boot 3.5.16 API — WebApplicationType**, SERVLET/REACTIVE/NONE: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/WebApplicationType.html
- **Spring Boot 3.5.16 API — ServletWebServerApplicationContext**, tìm factory bean: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/context/ServletWebServerApplicationContext.html
- **Spring Boot 3.5.16 API — ServletWebServerFactoryAutoConfiguration**, điều kiện auto-config: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/web/servlet/ServletWebServerFactoryAutoConfiguration.html
- **Spring Boot 3.5.16 API — @SpringBootApplication**, @EnableAutoConfiguration và component scan: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/SpringBootApplication.html
- **Spring Boot 3.5.16 API — @EnableAutoConfiguration**, container factory và custom bean backing off: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html
- **Spring Boot 3.5.16 API — ReactiveWebServerApplicationContext/ReactiveWebServerFactoryAutoConfiguration**: https://docs.spring.io/spring-boot/3.5/api/java/allclasses-index.html
- **Spring Boot — Creating Your Own Auto-configuration**, condition report và ApplicationContextRunner: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- **Spring Boot 3.5 — Traditional Deployment**, WAR/external container and provided runtime: https://docs.spring.io/spring-boot/3.5/how-to/deployment/traditional-deployment.html
- **Spring Boot 3.5.16 release/OSS support**: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/

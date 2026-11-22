# Thời điểm tạo máy chủ, đăng ký handler và mở cổng lắng nghe trong Spring Boot

## 1. Câu trả lời trọng tâm

Khi gọi `SpringApplication.run(...)` để khởi động một ứng dụng Spring Boot có embedded web server, **ba việc sau liên quan với nhau nhưng không phải cùng một thao tác**:

1. **Tạo máy chủ (create):** Spring Boot chọn `WebServerFactory`, tạo và thiết lập đối tượng server như Tomcat, Jetty hoặc Reactor Netty trong quá trình `ApplicationContext.refresh()`.
2. **Đăng ký cơ chế xử lý HTTP (register/wire):** Boot nối servlet/filter hoặc reactive `HttpHandler` với server; Spring MVC/WebFlux đồng thời xây thông tin định tuyến từ `@GetMapping`, `@PostMapping`, các handler và cấu hình liên quan. Có **hai lớp đăng ký khác nhau**: đăng ký đầu vào HTTP với server và ánh xạ URL vào handler của framework.
3. **Khởi động server và mở lắng nghe (start/listen):** server được khởi động trong vòng đời refresh của context; socket được bind vào địa chỉ/cổng thích hợp theo triển khai server. Khi Boot phát `WebServerInitializedEvent`, server được coi là đã sẵn sàng ở **mức máy chủ web**, và có thể truy vấn cổng thực tế.

Sau đó `ApplicationStartedEvent` được phát, các `ApplicationRunner`/`CommandLineRunner` chạy, rồi mới đến `ApplicationReadyEvent` và trạng thái readiness `ACCEPTING_TRAFFIC`. **Mở cổng không đồng nghĩa đã hoàn thành mọi tác vụ khởi động và sẵn sàng nhận traffic từ hệ thống triển khai.**

> Điểm cần nhớ: **không được suy luận “có `@RestController`” là cổng đã mở**, “server object đã được tạo” là ứng dụng đã ready, hay “đã nhìn thấy log khởi tạo Tomcat” là HTTP đã nhận request ổn định.

## 2. Bốn khái niệm rất dễ bị trộn lẫn

| Khái niệm | Ý nghĩa thực tế | Dấu hiệu / cách kiểm chứng |
| --- | --- | --- |
| **Bean definition / dependency injection** | Spring đã biết cần tạo controller, service, server factory và các hạ tầng web | Context đang dựng, bean được phát hiện hoặc khởi tạo; chưa đủ để kết luận có HTTP listener |
| **WebServer object** | Có đối tượng quản lý vòng đời server; factory đã cấu hình connector, địa chỉ và tài nguyên liên quan | `ServletWebServerFactory` / `ReactiveWebServerFactory` tạo `WebServer` |
| **Handler registration** | URL/method được ánh xạ đến hàm xử lý; tầng transport được nối với `DispatcherServlet` hoặc reactive `HttpHandler` | `RequestMappingHandlerMapping`, `ServletRegistrationBean`, `RouterFunction`, `HttpHandler` |
| **Listening / ready** | Listening: hệ điều hành/server có thể nhận kết nối trên cổng. Ready: ứng dụng phát tín hiệu đủ điều kiện phục vụ traffic | `WebServerInitializedEvent` để biết server đã khởi động; `ApplicationReadyEvent` và readiness để biết startup đã hoàn tất |

**“Handler” có hai cách dùng:** (a) bộ phận HTTP đầu vào mà server gọi (Servlet hay `HttpHandler`), và (b) phương thức controller hoặc functional handler mà Spring chọn cho một route. Những thứ này được gắn kết trong các giai đoạn khác nhau; không thể chỉ định một mốc duy nhất cho mọi loại handler.

## 3. Dòng thời gian Spring Boot từ `main()` tới `ready`

Sơ đồ dưới đây mô tả luồng **embedded server thông thường** của Spring Boot 3.x/4.x. Nó là trình tự logic; chi tiết bên trong server, lazy initialization và các callback có thể làm thứ tự những tác vụ con thay đổi.

```text
main()
  |
  +-- SpringApplication.run(args)
      |
      +-- chuẩn bị Environment, cấu hình, web application type
      +-- tạo ApplicationContext phù hợp (Servlet / Reactive / None)
      +-- load bean definitions và auto-configuration
      |
      +-- ApplicationPreparedEvent
      |
      +-- context.refresh()
          |
          +-- chuẩn bị BeanFactory, xử lý configuration/bean definitions
          +-- onRefresh(): tạo embedded WebServer qua factory
          |   \-- thiết lập tầng HTTP / ServletContext / reactive adapter
          +-- khởi tạo các singleton và hạ tầng handler mapping
          |   \-- ánh xạ GET /hello -> phương thức controller
          +-- finishRefresh(): khởi động SmartLifecycle, gồm web server
          |   +-- server.start(), lắng nghe theo triển khai server
          |   +-- WebServerInitializedEvent (có actual port)
          |   \-- ContextRefreshedEvent
          |
      +-- ApplicationStartedEvent
      +-- Availability: LivenessState.CORRECT
      +-- ApplicationRunner / CommandLineRunner
      +-- ApplicationReadyEvent
      +-- Availability: ReadinessState.ACCEPTING_TRAFFIC
  |
  +-- SpringApplication.run(...) trả về ApplicationContext
```

### Giai đoạn A — trước `refresh()`

`SpringApplication` đọc môi trường và cấu hình, nhận diện loại web application dựa trên classpath/cấu hình, tạo đối tượng `ApplicationContext` thích hợp và đăng ký các định nghĩa bean. Ví dụ, `@RestController` được component scanning nhận diện; tại bước này **chưa có lý do gì để khẳng định socket HTTP đã bind**.

Một số sự kiện có trước refresh:

- `ApplicationStartingEvent`: rất sớm, trước khi có `Environment`.
- `ApplicationEnvironmentPreparedEvent`: môi trường đã được chuẩn bị.
- `ApplicationContextInitializedEvent`: context đã tạo và chạy initializers, chưa load bean definitions.
- `ApplicationPreparedEvent`: ngay trước refresh, sau khi chuẩn bị các bean definitions.

Các tên sự kiện phản ánh **mức tiến triển của bootstrap**, không tương đương việc mở cổng.

### Giai đoạn B — `refresh()` tạo máy chủ

Trong ứng dụng Servlet với embedded server, `ServletWebServerApplicationContext.onRefresh()` thực hiện việc tạo `WebServer`, bằng cách lấy `ServletWebServerFactory` phù hợp rồi gọi factory để xây máy chủ. Đối với WebFlux, `ReactiveWebServerApplicationContext.onRefresh()` thiết lập `ReactiveWebServerFactory` và HTTP handling tương ứng.

Khái quát hóa, **đây là mốc tạo server trong vòng đời context**. Tuy nhiên hành động tạo có thể khởi tạo cấu trúc server/connector ở mức nội bộ, kể cả thực hiện một số thao tác mạng riêng của Tomcat/Jetty. Bởi thế không nên đưa ra kết luận tuyệt đối rằng “mọi lệnh `bind()` luôn chỉ diễn ra sau khi tất cả bean hoàn tất”.

Hãy phân biệt:

- `factory.getWebServer(...)`: lấy/khởi tạo server theo contract Spring Boot.
- `webServer.start()`: yêu cầu server đi vào trạng thái chạy.
- `WebServerInitializedEvent`: sự kiện Boot phát khi server đã sẵn sàng, phù hợp để lấy cổng thực tế.

Tại mốc tạo server, các phần liên quan đến **ServletContext initialization** có thể cần đăng ký rất sớm, trước cả khi mọi singleton thông thường được tạo.

### Giai đoạn C — nối request tới handler và hoàn tất bean initialization

Ở **Spring MVC** có ít nhất hai tầng:

1. Boot chuẩn bị/đăng ký `DispatcherServlet` và các servlet/filter/listener với Servlet container thông qua cơ chế như `ServletRegistrationBean`, `FilterRegistrationBean`, `ServletContextInitializer`. `DispatcherServlet` thường được map vào `/`.
2. Spring MVC khởi tạo các `HandlerMapping`, tìm các phương thức gắn `@RequestMapping`/`@GetMapping`, xây bảng ánh xạ route, chẳng hạn `GET /hello -> HelloController.hello()`. Tầng này không phải thao tác mở cổng.

Ở **Spring WebFlux**:

1. Reactive server được nối với một `HttpHandler` (thông qua adapter/`HttpHandler` pipeline).
2. WebFlux dựng `WebHandler`, filter chain, `DispatcherHandler` và các handler mappings. Annotated controllers hoặc `RouterFunction` quyết định endpoint xử lý request.

**Chú ý thứ tự:** Spring Boot có thể tạo embedded server trong `onRefresh()` **trước bước khởi tạo xong toàn bộ singleton**; route mapping thường hoàn tất khi các bean hạ tầng MVC/WebFlux khởi tạo trong refresh. Do đó câu “phải đăng ký tất cả controller xong thì mới tạo Tomcat” là mô tả không chính xác về vòng đời nội bộ. Điều quan trọng là những thành phần cần thiết được nối đầy đủ trước khi ứng dụng hoạt động bình thường.

### Giai đoạn D — server chạy, phát sự kiện, nhưng chưa chắc app đã ready

Trong tiến trình `finishRefresh()`, lifecycle processor khởi động các bean `SmartLifecycle` liên quan, bao gồm cơ chế start/stop của embedded web server. Boot phát `WebServerInitializedEvent` sau khi server được khởi động. Đây là điểm quan sát đúng để lấy `event.getWebServer().getPort()`.

Sau khi context refresh hoàn tất, `SpringApplication` phát `ApplicationStartedEvent`, sau đó thực thi các `ApplicationRunner`/`CommandLineRunner`. Cuối cùng Boot phát `ApplicationReadyEvent` và cập nhật readiness sang `ACCEPTING_TRAFFIC`.

Điều này dẫn tới một khác biệt thực tế:

- **Server listening:** một tiến trình có thể đã sở hữu cổng TCP và có hạ tầng web đang chạy.
- **Application ready:** mọi runner khởi động đã hoàn tất; hạ tầng health/readiness có thể báo hệ thống điều phối chuyển traffic đến ứng dụng.

Ở môi trường container/Kubernetes, readiness probe được dùng để **ngăn hệ thống chuyển traffic quá sớm**. Đừng dùng “port mở” làm tiêu chí duy nhất cho khả năng phục vụ nghiệp vụ. Mức độ server xử lý/hoãn request trong thời gian chuyển trạng thái có thể tùy server và cấu hình triển khai.

## 4. Mốc nào thuộc Spring MVC, mốc nào thuộc WebFlux?

| Vấn đề | Spring MVC / Servlet | Spring WebFlux / Reactive |
| --- | --- | --- |
| Web context | `ServletWebServerApplicationContext` | `ReactiveWebServerApplicationContext` |
| Web server factory | `ServletWebServerFactory` | `ReactiveWebServerFactory` |
| Server mặc định điển hình | Embedded Tomcat | Embedded Reactor Netty |
| Đầu vào HTTP | Servlet container gọi `DispatcherServlet` | HTTP server/adapter gọi `HttpHandler` |
| Handler trung tâm | `DispatcherServlet` + `HandlerMapping` | `DispatcherHandler` + reactive `HandlerMapping` |
| Đăng ký endpoint | `@GetMapping`, `@RequestMapping`, MVC functional routes | `@GetMapping` hoặc `RouterFunction` |
| Dấu mốc server đã sẵn sàng | `ServletWebServerInitializedEvent` | `ReactiveWebServerInitializedEvent` |
| Dấu mốc toàn ứng dụng ready | `ApplicationReadyEvent`, readiness | Giống MVC |

Tên lớp và package cụ thể có thể đổi giữa **Spring Boot 3.x và 4.x**. Cơ chế lifecycle và ranh giới giữa server, handler, readiness vẫn tương tự. WebFlux **không buộc phải dùng Netty** và MVC **không đồng nghĩa với Tomcat**: framework quyết định cách xử lý HTTP; server quyết định cách nhận kết nối.

## 5. Ví dụ Java 17+: quan sát từng mốc trên ứng dụng MVC chạy được

Ví dụ sau dùng **Spring Boot 3.5.x** để minh họa bằng một ứng dụng Maven độc lập. Spring Boot 4.x có thay đổi một số package và tên starter, được ghi chú cuối mục.

### 5.1. Tạo project

Tạo thư mục `startup-timeline` với hai tệp:

```text
startup-timeline/
├── pom.xml
└── src/main/java/com/example/startup/StartupTimelineApplication.java
```

Nội dung `pom.xml`:

```xml
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
    <artifactId>startup-timeline</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
```

Đây là POM **hoàn chỉnh**, phù hợp Java 17 và Maven. Nếu tạo bằng Spring Initializr, có thể dùng Maven wrapper (`mvnw`) thay cho Maven cài sẵn.

### 5.2. Tạo lớp ứng dụng và các listener

```java
package com.example.startup;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.boot.web.context.WebServerInitializedEvent;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

@SpringBootApplication
@RestController
public class StartupTimelineApplication {

    public static void main(String[] args) {
        System.out.println("01 BEFORE_RUN");
        SpringApplication.run(StartupTimelineApplication.class, args);
        System.out.println("06 AFTER_RUN");
    }

    @GetMapping("/hello")
    public String hello() {
        return "Hello from MVC";
    }

    @EventListener
    public void whenWebServerInitialized(WebServerInitializedEvent event) {
        System.out.println("02 WEB_SERVER_INITIALIZED port="
                + event.getWebServer().getPort());
    }

    @EventListener
    public void whenApplicationStarted(ApplicationStartedEvent event) {
        System.out.println("03 APPLICATION_STARTED");
    }

    @Bean
    public ApplicationRunner inspectRoute(RequestMappingHandlerMapping mappings) {
        return args -> {
            boolean hasHello = mappings.getHandlerMethods().keySet().stream()
                    .anyMatch(info -> info.getPatternValues().contains("/hello"));
            System.out.println("04 RUNNER route /hello registered=" + hasHello);
        };
    }

    @EventListener
    public void whenApplicationReady(ApplicationReadyEvent event) {
        System.out.println("05 APPLICATION_READY");
    }
}
```

Giải thích:

- `WebServerInitializedEvent`: đọc **cổng đang được server sử dụng**, thay vì đoán từ property.
- `ApplicationStartedEvent`: context đã refresh thành công, nhưng runner chưa chạy.
- `ApplicationRunner`: kiểm tra Spring MVC đã có ánh xạ `/hello`.
- `ApplicationReadyEvent`: các runners đã hoàn tất; đây là mốc sẵn sàng của ứng dụng.
- `SpringApplication.run(...)` chỉ trả về sau khi chuỗi startup hoàn tất hoặc ném lỗi.

Chạy tại thư mục `startup-timeline`:

```bash
mvn spring-boot:run
```

Nếu port `8080` đang trống, các dòng **do ứng dụng tự in** có thứ tự:

```text
01 BEFORE_RUN
02 WEB_SERVER_INITIALIZED port=8080
03 APPLICATION_STARTED
04 RUNNER route /hello registered=true
05 APPLICATION_READY
06 AFTER_RUN
```

Các dòng log của Spring/Tomcat có thể xen giữa, còn giá trị cổng đổi nếu cấu hình khác. Ví dụ không in một dòng “handler đã đăng ký” ngay tại đúng thời điểm đăng ký; nó **chứng minh ở thời điểm ApplicationRunner chạy thì route đã có**.

Trong một terminal khác, thử:

```bash
curl -s http://localhost:8080/hello
```

Response body:

```text
Hello from MVC
```

Dừng bằng Ctrl+C. Nếu cổng bị chiếm, dùng `mvn spring-boot:run -Dspring-boot.run.arguments=--server.port=8081` rồi gọi cổng `8081`. Không nên giả định lỗi “port already in use” là do controller không được đăng ký.

**Ghi chú phiên bản:** Ví dụ import `org.springframework.boot.web.context.WebServerInitializedEvent` là cho Boot **3.x**. Ở Boot **4.x**, lớp tương ứng nằm trong `org.springframework.boot.web.server.context.WebServerInitializedEvent`; starter MVC chính là `spring-boot-starter-webmvc`. Nếu chuyển phiên bản, dùng BOM/starter và imports phù hợp đồng bộ, tránh trộn các dependency 3.x và 4.x.

## 6. Ví dụ WebFlux: thay tầng HTTP, vẫn giữ thứ tự startup tổng thể

Với một **project khác** sử dụng `spring-boot-starter-webflux`, các route có thể được khai báo bằng `RouterFunction`. Đoạn dưới là **bean bổ sung trong một lớp `@Configuration`** của project WebFlux, không phải chương trình Java độc lập:

```java
@Bean
RouterFunction<ServerResponse> routes() {
    return RouterFunctions.route(
            RequestPredicates.GET("/hello"),
            request -> ServerResponse.ok().bodyValue("Hello from WebFlux")
    );
}
```

Imports tương ứng: `org.springframework.context.annotation.Bean`, `org.springframework.web.reactive.function.server.RouterFunction`, `RouterFunctions`, `RequestPredicates` và `ServerResponse`.

Trong WebFlux, server (thường Reactor Netty) nhận request và gọi pipeline của `HttpHandler`/`WebHandler`. `DispatcherHandler` hoặc functional router quyết định handler. Handler do framework quản lý **không tự mở TCP socket**. Embedded server vẫn được tạo và khởi động trong quá trình refresh, rồi Boot phát `ReactiveWebServerInitializedEvent`; `ApplicationReadyEvent` vẫn đến sau runners.

Không đưa cả MVC starter và WebFlux starter vào project chỉ để so sánh startup: Boot thông thường sẽ ưu tiên **Servlet/MVC** khi cả hai cùng hiện diện trên classpath. Hai project tách biệt giúp quan sát chính xác từng stack.

## 7. Đọc log, event và cổng: nên tin bằng chứng nào?

| Quan sát | Có thể kết luận | Chưa được kết luận |
| --- | --- | --- |
| `main()` vừa bắt đầu | JVM đã chạy chương trình | Context đã refresh, HTTP lắng nghe |
| Thấy bean factory hoặc controller bean được tạo | Spring đang thiết lập ứng dụng | Đã mở socket |
| Log “Tomcat initialized…” hoặc thông báo tương tự | Container được khởi tạo ở một mức nào đó | Runners đã hoàn tất hoặc readiness đã ACCEPTING |
| `WebServerInitializedEvent` và `getWebServer().getPort()` | Server của context ấy đã sẵn sàng và cung cấp actual port | Business dependencies, startup tasks hay readiness đã hoàn tất |
| `ApplicationStartedEvent` | Refresh context thành công | `ApplicationRunner`/`CommandLineRunner` đã chạy xong |
| `ApplicationReadyEvent` | Boot đã chạy xong runners và phát tín hiệu ready | Mọi dependency bên ngoài luôn khỏe trong tương lai |
| TCP connect hoặc `curl` thành công | Endpoint có thể được truy cập ở thời điểm kiểm tra | Readiness/health nghiệp vụ luôn ổn |

**Log không phải API ổn định**: từ ngữ và vị trí dòng log của Tomcat, Jetty, Netty thay đổi theo version. Để viết logic đáng tin, dùng lifecycle event và health/readiness; để điều tra tầng TCP, dùng `curl`, `ss`, `netstat` hoặc công cụ network phù hợp.

Nếu đặt `server.port=0`, hệ điều hành sẽ chọn **cổng còn trống**. Khi đó cổng ghi trong cấu hình là `0`, còn cổng thực tế phải lấy từ `WebServerInitializedEvent`/`WebServer.getPort()` sau khi server đã khởi động. Không thử truy cập `localhost:0`.

Khi dùng `management.server.port` khác cổng ứng dụng chính, Spring Boot có thể có **nhiều web context/server**; một listener có thể thấy nhiều `WebServerInitializedEvent`. Cần đối chiếu `event.getApplicationContext()`, context hoặc namespace để xác định đúng server.

## 8. Readiness, liveness và xử lý request khi đang startup

Spring Boot hỗ trợ các trạng thái availability:

- **Liveness = CORRECT:** context đã refresh, tiến trình được coi đang sống.
- **Readiness = REFUSING_TRAFFIC:** startup chưa xong, hoặc ứng dụng không nên nhận traffic.
- **Readiness = ACCEPTING_TRAFFIC:** Boot đã hoàn tất runners, cho phép môi trường triển khai điều hướng traffic.

Ví dụ: `ApplicationRunner` thực hiện tác vụ khởi tạo cache mất 10 giây. Có thể server đã ở giai đoạn listening trước khi tác vụ ấy kết thúc, nhưng readiness vẫn có thể báo **chưa chấp nhận traffic**. Kubernetes readiness probe cần dựa vào tín hiệu readiness để tránh chuyển request vào quá sớm. Không nên coi việc cổng TCP đang mở là phép kiểm thử đủ cho tính sẵn sàng nghiệp vụ.

Với Spring Boot Actuator và cấu hình health probes phù hợp, các endpoint dạng `/actuator/health/liveness`, `/actuator/health/readiness` có thể phục vụ hệ thống điều phối. Có thể dùng `/actuator/mappings` (khi endpoint được cho phép và exposed) để xem danh sách route mà Spring đã nhận diện.

Các probe trên chỉ đại diện mức trạng thái **được cấu hình**. Chúng không tự bảo đảm tất cả đối tác hay cơ sở dữ liệu bên ngoài luôn hoạt động. Đánh giá readiness và các dependency cần sát nhu cầu hệ thống; tránh dùng dependency liveness gây restart dây chuyền.

## 9. Can thiệp đúng chỗ khi cần tùy chỉnh startup

| Nhu cầu | Điểm mở rộng phù hợp | Vì sao |
| --- | --- | --- |
| Đổi port, địa chỉ bind | `server.port`, `server.address` | Cấu hình server trước lúc khởi động |
| Đổi connector/threads/TLS theo server | `WebServerFactoryCustomizer` hoặc cấu hình server tương ứng | Tùy chỉnh trước hoặc khi factory tạo server |
| Đăng ký một Servlet/Filter chuyên dụng ở MVC | `ServletRegistrationBean`, `FilterRegistrationBean`, `ServletContextInitializer` | Khai báo đúng cơ chế Servlet container |
| Đăng ký endpoint MVC/WebFlux | `@RestController` + `@GetMapping`, hoặc functional routes | Để framework xây handler mapping; không tự quản lý socket |
| Cần cổng thực tế sau khi server start | `WebServerInitializedEvent` | Sự kiện được thiết kế để đọc `WebServer.getPort()` |
| Công việc khởi tạo có deadline trước readiness | `ApplicationRunner` / `CommandLineRunner`, tổ chức thời gian chạy hợp lý | Chạy trước `ApplicationReadyEvent` |
| Hệ thống cân bằng tải chỉ chuyển request khi đã sẵn sàng | Readiness probe / availability state | Phân biệt cổng mở với nghiệp vụ đã phục vụ được |
| Đo thời gian từng bước startup | `ApplicationStartup`, `BufferingApplicationStartup`, Actuator `/actuator/startup` | Có dữ liệu đo thay vì suy luận từ số dòng log |

**Cẩn trọng với việc làm nặng trong lifecycle callback**: listener của `ApplicationStartedEvent`, `WebServerInitializedEvent` hoặc bean initialization quá lâu có thể kéo dài startup; nếu listener ném exception, toàn bộ ứng dụng có thể khởi động thất bại. Đừng cố mở cổng thủ công trong `@PostConstruct` của controller để “bắt đầu server sớm hơn”; điều đó phá vỡ việc Boot quản lý vòng đời.

## 10. Những tình huống lỗi thường gặp và cách chẩn đoán

### 10.1. Server “initialized” nhưng `curl` bị từ chối

Có thể log chỉ mô tả giai đoạn tạo container, listener chưa phục vụ, startup sau đó thất bại, port khác kỳ vọng hoặc server chỉ bind vào địa chỉ không truy cập được. Kiểm tra **log cuối cùng**, `WebServerInitializedEvent`, `server.port`/`server.address` và tiến trình thực sự sở hữu cổng. Nếu startup ném exception, không coi các log sớm là dấu hiệu thành công.

### 10.2. Có `@GetMapping` nhưng HTTP trả 404

Route có thể chưa được component scan, nằm ngoài package gốc, có context path/prefix khác, bị giới hạn method, hoặc project dùng WebFlux/MVC khác kỳ vọng. Kiểm tra mappings thực tế (`RequestMappingHandlerMapping` hoặc Actuator `/actuator/mappings`) và URL đầy đủ; đừng sửa port khi nguyên nhân nằm ở định tuyến.

### 10.3. Port mở nhưng yêu cầu nghiệp vụ thất bại

Một `ApplicationRunner` có thể vẫn đang chuẩn bị dữ liệu, service phụ thuộc chưa sẵn sàng, hoặc readiness chưa cho phép route traffic. Kiểm tra `ApplicationReadyEvent` và readiness state, thiết lập timeout/failure policy và health checks rõ ràng. Không chạy tác vụ vô hạn trong runner: điều đó có thể khiến ứng dụng mãi chưa ready.

### 10.4. `@PostConstruct` chạy trước/sau log Tomcat khác dự kiến

`@PostConstruct` là callback khởi tạo **một bean**, không phải đồng hồ chuẩn cho toàn bộ web server. Nó phụ thuộc khi nào bean được tạo; một số bean có thể được tạo sớm, số khác muộn hoặc lazy. Đừng cố suy ra thời điểm socket listen chỉ từ callback của một service.

### 10.5. `server.port=0` nhưng cấu hình in ra là 0

`0` là yêu cầu để hệ điều hành tự cấp cổng, không phải cổng phục vụ HTTP. Đọc giá trị thật từ `WebServerInitializedEvent` hoặc từ trạng thái runtime được Boot cập nhật. Nếu hệ thống có context quản trị riêng, chọn đúng event/server.

### 10.6. Đổi starter nhưng không còn server

Với `spring.main.web-application-type=none`, Boot chạy như ứng dụng không có web server; không có cổng HTTP hay `WebServerInitializedEvent`. Nếu cần HTTP, phải có đúng web starter và web application type. Nếu lỗi “missing web server factory bean”, kiểm tra dependency và các auto-configuration bị loại bỏ.

### 10.7. Server đang lắng nghe nhưng firewall không cho truy cập

Bind socket thành công chỉ xác nhận tiến trình đã mở địa chỉ/cổng **trong môi trường nó chạy**; firewall, Docker port mapping, Kubernetes Service/Ingress hoặc reverse proxy vẫn có thể ngăn truy cập từ bên ngoài. Kiểm tra tầng mạng, không nhầm với handler registration.

## 11. Checklist tự kiểm tra kiến thức

1. **Tạo server diễn ra lúc nào?** Trong quá trình `ApplicationContext.refresh()`, thường thông qua `onRefresh()` của web application context và `WebServerFactory`.
2. **Endpoint `@GetMapping("/hello")` có tự bind cổng 8080 không?** Không. Nó góp phần xây route mapping; server factory và vòng đời web server mới quản lý cổng.
3. **Đăng ký `DispatcherServlet` có giống ánh xạ `/hello` không?** Không. Đó là hai tầng: servlet đầu vào và route mapping của MVC.
4. **Event nào phù hợp để lấy actual port?** `WebServerInitializedEvent`, rồi `getWebServer().getPort()`.
5. **`ApplicationStartedEvent` có nghĩa runner đã chạy xong không?** Chưa. Các runners chạy **sau** event đó.
6. **`ApplicationReadyEvent` nói gì hơn server initialized?** Boot đã chạy xong runners, chuẩn bị phát trạng thái readiness chấp nhận traffic.
7. **Máy chủ nhúng WebFlux có buộc phải là Reactor Netty không?** Không; đó là mặc định phổ biến, còn adapter/server khác có thể được cấu hình.
8. **Server có log “started” mà ứng dụng vẫn chưa nhận traffic từ load balancer vì sao?** Readiness probe có thể còn ở trạng thái refusing; còn cần xét định tuyến, firewall, health và các startup task.

## 12. Tài liệu tham khảo chính thức

- Spring Boot — [SpringApplication và thứ tự application events](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- Spring Boot — [Embedded Web Servers](https://docs.spring.io/spring-boot/how-to/webserver.html)
- Spring Boot — [Actuator Endpoints, lifecycle/probe states](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- Spring Boot — [Startup endpoint](https://docs.spring.io/spring-boot/api/rest/actuator/startup.html)
- Spring Framework — [Spring MVC DispatcherServlet](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html)
- Spring Framework — [WebFlux Reactive Core / HttpHandler](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- Spring Framework — [Bean lifecycle và SmartLifecycle](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- Spring Boot API — [ServletWebServerApplicationContext (3.5)](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/context/ServletWebServerApplicationContext.html)

**Kết luận kỹ thuật cần nhớ:** Spring Boot **tạo web server trong refresh**, **thiết lập hạ tầng HTTP và route mapping trong quá trình khởi tạo context**, rồi **khởi động server trong vòng đời refresh**. `WebServerInitializedEvent` báo server đã sẵn sàng và có actual port; `ApplicationReadyEvent`/readiness báo toàn ứng dụng đã hoàn tất startup. Đây là các mốc khác nhau và cần quan sát bằng công cụ tương ứng.
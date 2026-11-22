# So sánh cùng một chương trình ở kiểu NONE, SERVLET và REACTIVE trong Spring Boot

Spring Boot có thể khởi động cùng một tập mã Java theo ba kiểu `WebApplicationType`: **`NONE`**, **`SERVLET`** hoặc **`REACTIVE`**. Ba kiểu này quyết định **loại `ApplicationContext` và hạ tầng web được tạo**, chứ không đơn thuần là bật/tắt một endpoint hay đổi tên thread.

Trong bài thực hành tổng hợp này, ta **xây dựng một project Spring Boot duy nhất**, không sửa `build.gradle` hoặc source code giữa các lần chạy; chỉ thay đối số cấu hình `spring.main.web-application-type`:

- **`NONE`:** Spring tạo một application context không có embedded HTTP server; startup logic, dependency injection, runners và bean lifecycle vẫn hoạt động.
- **`SERVLET`:** Spring tạo servlet web application context, cấu hình Spring MVC và embedded servlet server, thường là **Tomcat** với dependency của demo.
- **`REACTIVE`:** Spring tạo reactive web application context, cấu hình Spring WebFlux và embedded reactive web server, thường là **Reactor Netty** với dependency của demo.

Ta sẽ quan sát **loại context thật, bean được tạo có điều kiện, khả năng phục vụ HTTP, sự kiện Ready và hành vi đóng context**, sau đó dùng JUnit để tự kiểm tra cả ba kiểu. Bài dùng **Java 17+, Spring Boot 3.3.x, Spring Framework 6.1**. Những khẳng định về Tomcat/Netty bên dưới là cho **classpath của project demo**, không phải định nghĩa tuyệt đối của SERVLET/REACTIVE.

## 1. Mục tiêu và bảng kết quả cần đạt

Sau khi hoàn thành, người học có thể:

1. Giải thích sự khác nhau giữa `WebApplicationType.NONE`, `SERVLET` và `REACTIVE`.
2. Biết Spring Boot **suy luận chế độ mặc định theo classpath** và cách ép chế độ rõ ràng.
3. Xác định loại Spring `ApplicationContext` trong JVM thay vì đoán từ log.
4. Phân biệt “không có HTTP server” với “server có tồn tại nhưng không mở cổng”.
5. Dùng **cùng một `@RestController`** và quan sát endpoint ở SERVLET lẫn REACTIVE.
6. Biết `ApplicationRunner` và lifecycle callbacks có thể chạy ở **cả ba chế độ**.
7. Sử dụng `@ConditionalOnWebApplication` để cấu hình bean chỉ phù hợp với một web stack.
8. Hiểu hệ quả với servlet filters, WebFlux filters, blocking I/O, testing và production dependencies.

Bảng định hướng:

| Tiêu chí | NONE | SERVLET | REACTIVE |
|---|---|---|---|
| WebApplicationType | `NONE` | `SERVLET` | `REACTIVE` |
| ApplicationContext thường dùng | `AnnotationConfigApplicationContext` | `AnnotationConfigServletWebServerApplicationContext` | `AnnotationConfigReactiveWebServerApplicationContext` |
| Embedded HTTP server | **Không tạo** | Có | Có |
| Cấu hình HTTP xử lý request | Không có HTTP dispatch | Spring MVC/`DispatcherServlet` | Spring WebFlux/`DispatcherHandler` |
| Server mặc định trong demo | Không có | Tomcat | Reactor Netty |
| `@RestController` được tự phục vụ qua HTTP? | Không | Có | Có |
| `ApplicationRunner` | Có thể chạy | Có thể chạy | Có thể chạy |
| `ApplicationReadyEvent` | Có thể được phát | Có thể được phát | Có thể được phát |
| Spring quản lý bean và `@PreDestroy` | Có | Có | Có |
| Thread model web thường gặp | Không có request worker | Servlet request threads | Event-loop/reactive callbacks |
| Trường hợp phù hợp | Batch, CLI, worker nền | REST MVC, servlet stack | Reactive/non-blocking HTTP app |

Tên class trong bảng là kiểu thông thường khi Spring Boot dùng context factory mặc định. Ứng dụng có cấu hình custom context factory có thể tạo subclass hoặc context khác; **đừng kiểm tra tên class bằng chuỗi cứng** khi kiểm thử.

## 2. Spring Boot chọn kiểu web bằng cách nào?

`SpringApplication` xác định `WebApplicationType` từ **classpath** nếu ứng dụng không chỉ định rõ:

~~~text
Có Spring MVC?
   |
   +-- Có --------------------> SERVLET
   |
   +-- Không
         |
         +-- Có Spring WebFlux -> REACTIVE
         |
         +-- Không -----------> NONE
~~~

Đây là mô hình đơn giản hóa chính sách mặc định của Boot cho các starter thông dụng:

- Có `spring-boot-starter-web` → có Spring MVC → **SERVLET**.
- Không có MVC nhưng có `spring-boot-starter-webflux` → **REACTIVE**.
- Không có cả hai web frameworks → thường **NONE**.
- Có **cả hai starters** → **SERVLET được ưu tiên**, bởi nhiều ứng dụng MVC thêm WebFlux để dùng `WebClient` mà không muốn chuyển server sang WebFlux.

**Quan trọng:** *có Reactor trên classpath* không đủ để kết luận ứng dụng đang chạy REACTIVE. Tương tự, chỉ thấy Netty dependency không có nghĩa request server đang dùng Netty.

### Cách ép mode

Trong `application.properties`:

~~~properties
spring.main.web-application-type=none
~~~

Hoặc đối số lúc khởi chạy:

~~~bash
java -jar build/libs/three-modes-lab.jar \
  --spring.main.web-application-type=reactive
~~~

Hoặc dùng Java API trước `run(...)`:

~~~java
SpringApplication application =
        new SpringApplication(ModeLabApplication.class);
application.setWebApplicationType(WebApplicationType.REACTIVE);
application.run(args);
~~~

Đoạn Java là **ví dụ API riêng**, cần các imports và class `ModeLabApplication` được khai báo ở mục 4; chương trình chính sẽ **không hard-code** mode để cho phép đổi bằng CLI.

**Lưu ý:** không ép REACTIVE nếu classpath không có hạ tầng WebFlux/server phù hợp, hoặc ép SERVLET khi thiếu servlet web server factory. Chọn một `WebApplicationType` không tự tải thêm dependency; cấu hình bị thiếu có thể làm context startup thất bại.

## 3. Ba mode khác nhau ở những tầng nào?

### NONE: vẫn có Spring, nhưng không có HTTP listener

Với `NONE`, Boot thường tạo `AnnotationConfigApplicationContext`. Những phần vẫn có thể hoạt động:

- `@Configuration`, `@Bean`, `@Component`, `@Service`, injection.
- `Environment`, configuration properties, profiles.
- `ApplicationRunner` và `CommandLineRunner`.
- `ApplicationStartedEvent`, `ApplicationReadyEvent` và bean lifecycle.
- Datasource, HTTP **client**, message consumer, scheduled task hoặc executor **nếu được khai báo/cấu hình**, dù không có HTTP server.

Những phần **không** được Boot khởi tạo như một web app:

- Không embedded HTTP server của application.
- Không servlet request routing hoặc WebFlux HTTP request routing.
- Không thể `curl http://localhost:8080/api/ping` vào **ứng dụng này**, trừ khi chính bạn tự khởi chạy một server khác không thuộc auto-config.

**Không nhầm NONE với “ứng dụng không chạy được gì”.** Một batch job `ApplicationRunner` có thể hoàn thành toàn bộ nghiệp vụ trong NONE. Với service tiêu thụ Kafka/Rabbit hoặc chạy lịch, NONE vẫn có thể tồn tại lâu vì component nền giữ process sống.

### SERVLET: Spring MVC và servlet container

Ở SERVLET, Spring Boot sử dụng servlet web application context:

- Tạo hạ tầng `ServletContext` và embedded servlet web server.
- Spring MVC thường dispatch request qua `DispatcherServlet`.
- Các thành phần như `Filter`, `ServletRegistrationBean`, `HandlerInterceptor`, `HttpServletRequest` phù hợp với servlet stack.
- Starter web trong demo kéo **Tomcat**.
- Controller MVC được gọi theo request handling model của servlet container; đối với mã xử lý đồng bộ blocking, một worker thread có thể bị giữ trong thời gian xử lý.

Điều này **không có nghĩa mọi việc trong servlet app đều phải blocking**: Spring MVC hỗ trợ async request processing và nhiều reactive return adapters. Nhưng core request stack vẫn là servlet/MVC.

### REACTIVE: Spring WebFlux và reactive server

Ở REACTIVE, Boot sử dụng reactive web application context:

- Tạo reactive HTTP handler chain của Spring WebFlux.
- Annotated controllers vẫn có thể dùng `@RestController`, `@GetMapping`; WebFlux có `DispatcherHandler` thay vì MVC `DispatcherServlet`.
- Có thể khai báo routing function kiểu `RouterFunction<ServerResponse>`.
- Starter WebFlux trong demo kéo Reactor Netty làm embedded server.
- Request/event processing thường dùng **event loops** và reactive composition, hướng tới non-blocking I/O.

**Đừng block event-loop thread** bằng `Thread.sleep(...)`, JDBC blocking dài hoặc gọi `Mono.block()` trong reactive request handler. Một đường I/O blocking không tự trở thành non-blocking chỉ vì bật REACTIVE; nếu chưa thể thay client, cần offload có kiểm soát tới scheduler phù hợp và quản lý backpressure.

**REACTIVE không đồng nghĩa lúc nào cũng phải dùng Netty.** Spring WebFlux cũng có thể chạy trên một số servlet containers tương thích khi cấu hình adapter/server phù hợp. “REACTIVE” là lựa chọn **web application stack**, còn server implementation là một yếu tố riêng.

## 4. Một project duy nhất cho cả ba mode

Để phép so sánh thực sự công bằng, giữ **đúng cùng source code và classpath**. Ta cố ý khai báo **cả hai** starter:

~~~text
three-modes-lab/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/modes/ModeLabApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/modes/ModeComparisonTest.java
~~~

### 4.1 build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

springBoot {
    mainClass = 'com.example.modes.ModeLabApplication'
}

tasks.named('bootJar') {
    archiveFileName = 'three-modes-lab.jar'
}
~~~

Trong project này:

- `spring-boot-starter-web` mang Spring MVC và Tomcat theo dependency mặc định.
- `spring-boot-starter-webflux` mang WebFlux và Reactor Netty theo dependency mặc định.
- Cả hai được cố định trong **cùng một JAR**.
- `spring-boot-starter-test` cung cấp JUnit Jupiter và AssertJ để kiểm thử.
- Java toolchain dùng Java 17, tương thích Spring Boot 3.3.

**Đây là cấu hình dành cho bài thực hành so sánh.** Trong production, thường nên **chọn một web starter chính** để tránh dependency không dùng và giảm phức tạp bảo trì. Một servlet app dùng `WebClient` vẫn có thể giữ starter WebFlux, nhưng nên hiểu chính sách chọn MVC của Boot.

### 4.2 application.properties

Tạo `src/main/resources/application.properties`:

~~~properties
spring.application.name=three-modes-lab
server.port=8080
spring.main.banner-mode=off
logging.level.root=WARN

# Không đặt spring.main.web-application-type ở đây.
# Mỗi lần chạy sẽ chọn none / servlet / reactive bằng CLI.
~~~

Chưa đặt mode nào, vì bài thực hành cần đổi bằng argument **mà không chỉnh sửa file**. Property `server.port=8080` chỉ có tác dụng với **web server** được tạo ở SERVLET/REACTIVE; ở NONE, nó **không tự khởi chạy server**.

### 4.3 ModeLabApplication.java — file đầy đủ

Tạo `src/main/java/com/example/modes/ModeLabApplication.java`:

~~~java
package com.example.modes;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ModeLabApplication {

    public static void main(String[] args) {
        // Không hard-code WebApplicationType.
        // Tham số --spring.main.web-application-type quyết định mode.
        ConfigurableApplicationContext context =
                SpringApplication.run(ModeLabApplication.class, args);

        System.out.println("MAIN_RETURNED=true");

        // Không cần HTTP server trong NONE; chủ động cleanup context.
        // Với SERVLET/REACTIVE, giữ context/server sống để gọi curl;
        // JVM shutdown hook của Spring Boot sẽ đóng khi dừng mềm.
        if ("NONE".equals(modeOf(context))) {
            context.close();
        }
    }

    static String modeOf(ApplicationContext context) {
        if (context instanceof ServletWebServerApplicationContext) {
            return "SERVLET";
        }
        if (context instanceof ReactiveWebServerApplicationContext) {
            return "REACTIVE";
        }
        return "NONE";
    }

    public record ModeMarker(String name) {
    }

    @Bean
    @ConditionalOnWebApplication(
            type = ConditionalOnWebApplication.Type.SERVLET)
    ModeMarker servletModeMarker() {
        return new ModeMarker("SERVLET");
    }

    @Bean
    @ConditionalOnWebApplication(
            type = ConditionalOnWebApplication.Type.REACTIVE)
    ModeMarker reactiveModeMarker() {
        return new ModeMarker("REACTIVE");
    }

    @Bean
    ApplicationRunner reportMode(
            ApplicationContext context,
            ObjectProvider<ModeMarker> markers) {

        return args -> {
            String mode = modeOf(context);
            ModeMarker marker = markers.getIfAvailable();

            System.out.println("MODE=" + mode);
            System.out.println("CONDITIONAL_MARKER="
                    + (marker == null ? "NONE" : marker.name()));
            System.out.println("HTTP_ENABLED="
                    + !"NONE".equals(mode));
        };
    }

    @Bean
    DisposableBean closeNotice() {
        return () -> System.out.println("CONTEXT_CLOSED=true");
    }

    @Component
    public static class ReadyNotice {

        @EventListener(ApplicationReadyEvent.class)
        public void ready() {
            System.out.println("READY_EVENT=true");
        }
    }

    @RestController
    public static class DemoController {

        private final ApplicationContext context;

        public DemoController(ApplicationContext context) {
            this.context = context;
        }

        @GetMapping(value = "/api/ping",
                produces = MediaType.TEXT_PLAIN_VALUE)
        public String ping() {
            return "pong";
        }

        @GetMapping(value = "/api/mode",
                produces = MediaType.TEXT_PLAIN_VALUE)
        public String currentMode() {
            return modeOf(context);
        }
    }
}
~~~

**Một số chi tiết kỹ thuật cố ý trong ví dụ:**

1. `modeOf(...)` phân loại bằng **loại context thực tế**, không dựa vào việc dependency có mặt trên classpath. Vì cả hai starters đều có mặt ở mọi mode, kiểm tra classpath sẽ không phân biệt được ba lần chạy.
2. Hai bean kiểu `ModeMarker` được gắn `@ConditionalOnWebApplication` khác loại. Với một web mode hợp lệ, chỉ marker tương ứng được tạo. Với NONE, không có marker nào.
3. `ApplicationRunner` chạy ở cả ba mode và in `MODE`, `CONDITIONAL_MARKER`, `HTTP_ENABLED`.
4. `@RestController` dùng **cùng method và URL** cho MVC và WebFlux. Ở NONE, bean có thể vẫn được tạo do component scan, nhưng **không có HTTP mapping/server** để nhận request.
5. `@EventListener(ApplicationReadyEvent.class)` cho thấy Ready event là một phần của SpringApplication startup, **không phụ thuộc bắt buộc phải có HTTP server**.
6. `DisposableBean` in `CONTEXT_CLOSED=true` khi Spring context hủy bean trong đường đóng bình thường. Nó không thể được đảm bảo khi JVM bị SIGKILL.
7. Trong NONE, `main` đóng context sau khi `SpringApplication.run(...)` trả về. Trong hai mode web, `main` kết thúc nhưng embedded server tiếp tục giữ process phục vụ request.

**Không có `Thread.sleep(...)`, database hay API ngoài** trong controller. Điều này giữ phép so sánh tập trung vào startup context/HTTP stack thay vì nhiễu từ I/O. Endpoint `/api/mode` trả một chuỗi ngắn có thể được MVC và WebFlux serialize nhất quán dưới dạng `text/plain`.

## 5. Build đúng một lần

Với JDK 17+ và Gradle wrapper phù hợp trong project:

~~~bash
./gradlew clean bootJar
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat clean bootJar
~~~

Artifact cần chạy:

~~~text
build/libs/three-modes-lab.jar
~~~

Nếu project chưa có wrapper, chuẩn bị Gradle hoặc tạo wrapper tương thích trước. Không thể biên dịch ứng dụng Spring Boot này bằng một lệnh `javac ModeLabApplication.java` đơn lẻ nếu không đưa Spring libraries vào classpath.

**Điều kiện so sánh:** sau khi build, **không build lại hoặc thay code** giữa ba lần thử. Chỉ đổi `--spring.main.web-application-type` khi khởi chạy JAR đó.

## 6. Lần 1 — chạy kiểu NONE

Chạy trong terminal:

~~~bash
java -jar build/libs/three-modes-lab.jar \
    --spring.main.web-application-type=none
~~~

Những dòng do **mã ứng dụng chủ động in**, không kể log riêng của Boot/JVM:

~~~text
MODE=NONE
CONDITIONAL_MARKER=NONE
HTTP_ENABLED=false
READY_EVENT=true
MAIN_RETURNED=true
CONTEXT_CLOSED=true
~~~

Tại sao có những dòng này?

1. `SpringApplication` chọn non-web application context.
2. Không có `@ConditionalOnWebApplication` marker phù hợp.
3. `ApplicationRunner` vẫn được gọi và in ba thuộc tính.
4. `ApplicationReadyEvent` vẫn được phát khi startup hoàn tất bình thường.
5. `main` nhận context, in `MAIN_RETURNED` và **chủ động gọi `context.close()`**.
6. Spring destroy `DisposableBean` và in `CONTEXT_CLOSED=true`.
7. Không còn web server để giữ process sống; chương trình kết thúc bình thường.

Đừng suy luận “có Ready event nên phải có HTTP endpoint”. `ApplicationReadyEvent` không phải HTTP response hay lệnh khởi tạo cổng mạng. Ở NONE, các service/bean không cần web vẫn có thể hoạt động bình thường.

**Kiểm tra HTTP:** nếu thử:

~~~bash
curl -i http://127.0.0.1:8080/api/ping
~~~

sau khi chạy NONE, kết nối sẽ **không được phục vụ bởi chương trình này**. Nếu vẫn nhận HTTP 200, có thể một process khác đang nghe cổng 8080; hãy kiểm tra process/port thay vì kết luận NONE đã tạo server.

**Một lưu ý về CLI:** `server.port=8080` trong file cấu hình **không thể bật server** khi `WebApplicationType.NONE`. Đổi `--server.port=9090` cũng không biến NONE thành servlet/reactive application.

## 7. Lần 2 — chạy kiểu SERVLET

Chạy trong terminal riêng:

~~~bash
java -jar build/libs/three-modes-lab.jar \
    --spring.main.web-application-type=servlet
~~~

Những dòng do code chương trình in khi startup hoàn tất bình thường:

~~~text
MODE=SERVLET
CONDITIONAL_MARKER=SERVLET
HTTP_ENABLED=true
READY_EVENT=true
MAIN_RETURNED=true
~~~

**Chưa có `CONTEXT_CLOSED=true`** ở giai đoạn này, vì context/server đang chạy và chờ requests. Trong các log khác có thể có thông điệp Tomcat khởi động; ví dụ đặt log root WARN để giảm nhiễu, nên **đừng dùng sự có mặt của một dòng log server cụ thể làm phép đo duy nhất**.

Từ terminal khác:

~~~bash
curl -i http://127.0.0.1:8080/api/ping
curl -i http://127.0.0.1:8080/api/mode
~~~

Hai HTTP responses có body lần lượt là:

~~~text
pong
~~~

và:

~~~text
SERVLET
~~~

Headers HTTP như `Content-Length`, `Date`, `Connection` có thể thay đổi tùy server/version; body `pong` và `SERVLET` do controller tạo là phần cần assert.

**Luồng xử lý:**

~~~text
TCP/HTTP client
       |
       v
Embedded Tomcat
       |
       v
Servlet filters / DispatcherServlet
       |
       v
Spring MVC handler mapping
       |
       v
DemoController.currentMode()
       |
       v
text/plain body: SERVLET
~~~

Khi nhấn `Ctrl+C` trong terminal chạy trực tiếp JVM trên hệ Unix thông thường (hoặc gửi SIGTERM đúng PID), Spring shutdown hook có cơ hội đóng context. Khi đó đoạn code demo in:

~~~text
CONTEXT_CLOSED=true
~~~

Đây là kết quả của **đường shutdown mềm hoàn tất**. Với force kill/SIGKILL, destroy callback không được bảo đảm.

## 8. Lần 3 — chạy kiểu REACTIVE

**Dừng SERVLET trước khi dùng cùng port 8080**, hoặc chọn một port khác để tránh xung đột.

Chạy:

~~~bash
java -jar build/libs/three-modes-lab.jar \
    --spring.main.web-application-type=reactive
~~~

Những dòng do code in lúc startup:

~~~text
MODE=REACTIVE
CONDITIONAL_MARKER=REACTIVE
HTTP_ENABLED=true
READY_EVENT=true
MAIN_RETURNED=true
~~~

Ở đây, mặc dù JAR vẫn chứa Spring MVC và Tomcat classes, bạn đã ép Boot dùng **reactive application context**. Với dependency mặc định của demo, HTTP server dùng Reactor Netty.

Gọi cùng endpoints:

~~~bash
curl -i http://127.0.0.1:8080/api/ping
curl -i http://127.0.0.1:8080/api/mode
~~~

Bodies lần lượt là:

~~~text
pong
~~~

và:

~~~text
REACTIVE
~~~

**Luồng xử lý:**

~~~text
TCP/HTTP client
       |
       v
Reactor Netty (server)
       |
       v
Spring WebFlux HttpHandler / WebFilter chain
       |
       v
DispatcherHandler
       |
       v
DemoController.currentMode()
       |
       v
text/plain body: REACTIVE
~~~

**Cùng `@RestController` nhưng khác dispatcher.** `@GetMapping` là kiểu annotation được hỗ trợ trong cả MVC và WebFlux, nên source của controller không cần thay. Tuy nhiên các phần mở rộng của hai stack **không** có cùng hợp đồng: Servlet `Filter`, `HttpServletRequest`, MVC `HandlerInterceptor` không tự trở thành `WebFilter` hoặc `ServerWebExchange` trong REACTIVE.

Khi dừng mềm, context được đóng và demo in `CONTEXT_CLOSED=true` tương tự SERVLET. Context lifecycle là khái niệm chung, dù web server và request processing model khác.

## 9. Vì sao hai mode web trả cùng body?

Điểm dạy học quan trọng: **API contract ở controller không nhất thiết đổi**, nhưng đường thực thi ở tầng framework lại khác:

~~~java
@GetMapping(value = "/api/ping",
        produces = MediaType.TEXT_PLAIN_VALUE)
public String ping() {
    return "pong";
}
~~~

Đoạn trên chính là method từ project. Cả MVC và WebFlux đều có annotation-based controllers. Với một method đồng bộ, nhẹ, chỉ trả `String`, kết quả HTTP có thể giống nhau.

**Nhưng không vì thế kết luận MVC và WebFlux tương đương về mọi thứ**:

- MVC dựa trên servlet stack; WebFlux tổ chức HTTP request handling qua reactive types/handler chain.
- `@ExceptionHandler` và validation có những điểm tương đồng, nhưng cấu hình error handling/filters/security stack khác nhau.
- Servlet request/session/thread-local context không nên được dùng y nguyên trong WebFlux event loops.
- Các operator `Mono`/`Flux` mô tả luồng xử lý reactive; trả `Mono<String>` trong Spring MVC vẫn có thể được adapter hỗ trợ, nên **chỉ nhìn return type chưa đủ khẳng định application type**.
- REACTIVE không đảm bảo mọi downstream API của ứng dụng đều non-blocking; JDBC blocking/legacy SDK vẫn cần thiết kế riêng.

Trong demo, `modeOf(context)` là phép quan sát đáng tin hơn việc “endpoint có phản hồi” vì cả hai web stacks đều phục vụ được URL đó.

## 10. So sánh các bean được tạo có điều kiện

Hai factory methods trong demo:

~~~java
@Bean
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.SERVLET)
ModeMarker servletModeMarker() {
    return new ModeMarker("SERVLET");
}

@Bean
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.REACTIVE)
ModeMarker reactiveModeMarker() {
    return new ModeMarker("REACTIVE");
}
~~~

Các điều kiện trên được đánh giá trong quá trình xây dựng context, không phải khi request tới. Bởi vậy:

| Mode | `servletModeMarker` | `reactiveModeMarker` |
|---|---|---|
| NONE | Không có | Không có |
| SERVLET | Có | Không có |
| REACTIVE | Không có | Có |

Nếu dự án cần một bean chỉ cho batch, có thể sử dụng một điều kiện phù hợp trên property/profile hoặc custom condition thay vì cố dùng `@ConditionalOnWebApplication` để biểu diễn “not web”. Điều kiện phụ thuộc web là một công cụ cho auto-configuration, không tự thay thế mọi kiểu điều kiện nghiệp vụ.

**Không nhầm condition với classpath:**

- `@ConditionalOnClass` hỏi: class có tồn tại trên classpath không?
- `@ConditionalOnWebApplication(type=SERVLET)` hỏi: đây có phải servlet web application theo điều kiện Boot không?
- Với JAR chứa cả MVC và WebFlux, một condition kiểm tra MVC class sẽ **đúng ở cả ba mode**, dù NONE không tạo servlet web context.

Nhờ marker, ví dụ chứng minh sự khác nhau đến từ **context type**, không phải “chỉ mode SERVLET mới có Spring MVC dependency”.

## 11. JUnit integration test chạy cả ba mode mà không sửa source

Bài thực hành có thể tự động kiểm chứng bằng **một test class** khởi chạy từng SpringApplication trong một context riêng. Không gọi method `main()` để tránh logic dành cho one-shot NONE đóng context ngay trong process test; thay vào đó kiểm thử trực tiếp `SpringApplication.run(...)` và chủ động close từng context.

Tạo file `src/test/java/com/example/modes/ModeComparisonTest.java`:

~~~java
package com.example.modes;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

class ModeComparisonTest {

    @Test
    void noneStartsWithoutHttpServer() {
        try (ConfigurableApplicationContext context = start("none")) {
            assertThat(context)
                    .isNotInstanceOfAny(
                            ServletWebServerApplicationContext.class,
                            ReactiveWebServerApplicationContext.class);

            assertThat(context.getBeanProvider(
                    ModeLabApplication.ModeMarker.class)
                    .getIfAvailable()).isNull();

            assertThat(ModeLabApplication.modeOf(context))
                    .isEqualTo("NONE");
        }
    }

    @Test
    void servletStartsMvcHttpEndpoint() throws Exception {
        try (ConfigurableApplicationContext context = start("servlet")) {
            assertThat(context)
                    .isInstanceOf(ServletWebServerApplicationContext.class);

            assertThat(context.getBean(
                    ModeLabApplication.ModeMarker.class).name())
                    .isEqualTo("SERVLET");

            assertThat(get(context, "/api/ping"))
                    .isEqualTo("pong");
            assertThat(get(context, "/api/mode"))
                    .isEqualTo("SERVLET");
        }
    }

    @Test
    void reactiveStartsWebFluxHttpEndpoint() throws Exception {
        try (ConfigurableApplicationContext context = start("reactive")) {
            assertThat(context)
                    .isInstanceOf(ReactiveWebServerApplicationContext.class);

            assertThat(context.getBean(
                    ModeLabApplication.ModeMarker.class).name())
                    .isEqualTo("REACTIVE");

            assertThat(get(context, "/api/ping"))
                    .isEqualTo("pong");
            assertThat(get(context, "/api/mode"))
                    .isEqualTo("REACTIVE");
        }
    }

    private ConfigurableApplicationContext start(String mode) {
        SpringApplication application =
                new SpringApplication(ModeLabApplication.class);

        // Thay mode bằng CLI, giống như khi chạy JAR.
        // Cổng 0: OS cấp cổng còn trống, tránh trùng port 8080.
        return application.run(
                "--spring.main.web-application-type=" + mode,
                "--server.port=0",
                "--logging.level.root=ERROR");
    }

    private String get(
            ConfigurableApplicationContext context, String path)
            throws Exception {

        int port = ((WebServerApplicationContext) context)
                .getWebServer().getPort();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("http://127.0.0.1:" + port + path))
                .GET()
                .build();

        HttpResponse<String> response =
                HttpClient.newHttpClient().send(
                        request,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8));

        assertThat(response.statusCode()).isEqualTo(200);
        return response.body();
    }
}
~~~

### Vì sao test này kiểm chứng đúng ba mode?

1. Mỗi test tạo **SpringApplication** mới, truyền mode riêng bằng arguments.
2. Mỗi test sử dụng **cùng class `ModeLabApplication`**, không đổi classpath.
3. `NONE` kiểm tra không có servlet/reactive web server context và không có conditional marker.
4. `SERVLET` kiểm tra servlet context, marker và HTTP endpoint trên cổng được OS cấp.
5. `REACTIVE` kiểm tra reactive context, marker và **cùng** HTTP endpoints.
6. `server.port=0` giúp tránh port collision. Test lấy cổng thật từ `WebServerApplicationContext.getWebServer().getPort()`, không đoán 8080.
7. `try-with-resources` đóng context cả khi assertion thất bại, để test không rò rỉ web server giữa các lần chạy.
8. Test quan sát **hành vi thực**, không chỉ đọc property `spring.main.web-application-type` rồi suy ra mọi thứ đã được cấu hình đúng.

Chạy:

~~~bash
./gradlew test
~~~

Kết quả kỳ vọng: **3 tests pass**, ứng với `noneStartsWithoutHttpServer`, `servletStartsMvcHttpEndpoint` và `reactiveStartsWebFluxHttpEndpoint`. Gradle có thể chỉ in `BUILD SUCCESSFUL` và lưu báo cáo chi tiết dưới `build/reports/tests/test/`; không nên khẳng định một chuỗi stdout cố định nếu chưa cấu hình test logger.

**Lưu ý:** đây là integration tests dùng SpringApplication thật; chúng chậm hơn unit tests thuần Java vì tạo/đóng contexts. Chỉ cần một vài smoke tests để chứng minh web mode; logic parse/business nên test riêng không dựng cả server.

### Test với @SpringBootTest có gì khác?

Nếu dùng `@SpringBootTest`, khi cả MVC và WebFlux có mặt thì Boot thường chọn servlet, kể cả khi bạn muốn kiểm tra WebFlux. Để thử reactive mode phải chỉ rõ property:

~~~java
@SpringBootTest(
        properties = "spring.main.web-application-type=reactive",
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveModeSpringBootTest {
    // Kiểm tra ReactiveWebServerApplicationContext và HTTP endpoint.
}
~~~

Đây là **khung minh họa**, chưa phải test class độc lập; cần imports và method assertions. Với NONE có thể dùng `webEnvironment=NONE` nhưng phải nhớ nó chủ động chọn non-web test environment, không giống tình huống web defaults.

**Đừng trộn `MockMvc` và `WebTestClient` như thể chúng luôn chạy cùng một web stack**. `MockMvc` chủ yếu kiểm thử Spring MVC; `WebTestClient` hỗ trợ WebFlux và cũng có cách dùng với server thật. Chọn công cụ đúng mục đích và hiểu test đang dựng servlet hay reactive context.

## 12. Không nhầm mode với port hoặc HTTP server được chọn

Ba cấu hình dưới đây **khác ý nghĩa**:

~~~properties
spring.main.web-application-type=none
~~~

~~~properties
spring.main.web-application-type=servlet
server.port=0
~~~

~~~properties
spring.main.web-application-type=servlet
server.port=-1
~~~

- `NONE`: không tạo web ApplicationContext/server theo auto-config thông thường.
- `SERVLET + server.port=0`: **có** web server, OS chọn một cổng còn trống. Đây là lựa chọn tốt cho integration test.
- `SERVLET + server.port=-1`: cấu hình vô hiệu hóa HTTP endpoints theo tính năng web server của Boot nhưng vẫn giữ **web ApplicationContext và hạ tầng liên quan**; không tương đương NONE.

Ngoài ra, `server.port=0` không có nghĩa “không lắng nghe”, mà là “chọn cổng bất kỳ còn trống”. Khi test, không thể cố định port 8080.

Chuyển sang REACTIVE không nhất thiết thay đổi port; cả servlet và reactive server có thể cùng phục vụ port 8080 **nếu chạy tuần tự**, hoặc dùng các port khác nhau khi chạy song song.

## 13. Điều gì không nên chuyển nguyên xi giữa SERVLET và REACTIVE?

Một controller đơn giản có thể dùng chung, nhưng middleware/server APIs khác rõ:

| Nhu cầu | Servlet/MVC | Reactive/WebFlux |
|---|---|---|
| Entry point HTTP | `DispatcherServlet` | `DispatcherHandler` |
| Per-request abstraction | `HttpServletRequest/Response` | `ServerWebExchange` |
| Filter | `jakarta.servlet.Filter`, `FilterRegistrationBean` | `org.springframework.web.server.WebFilter` |
| Interceptor | `HandlerInterceptor` | `WebFilter` hoặc reactive handler infrastructure |
| Handler mapping | MVC `RequestMappingHandlerMapping` | WebFlux handler mappings |
| Security | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Error handling | Servlet/MVC exception resolver & error handling | Reactive error handler chain |
| HTTP client thường dùng | `RestClient`, `RestTemplate` hoặc `WebClient` | `WebClient` non-blocking phù hợp |
| Blocking data access | Thường có thể dùng JDBC theo thread-per-request | Tránh block event-loop, cân nhắc R2DBC/offloading |
| Request context | Servlet request attrs/thread-bound conventions | Reactive context propagation có semantics khác |

Một bean `Filter` được định nghĩa trong cùng JAR không tự trở thành `WebFilter` khi ép REACTIVE. Nếu muốn chạy cả ba mode trong một app codebase, nên khai báo **configuration riêng có condition phù hợp**.

### Không nghĩ REACTIVE = “nhanh hơn mọi thứ”

Event loop phù hợp với nhiều tác vụ I/O non-blocking, nhưng:

- Code CPU-bound nặng vẫn tranh CPU.
- JDBC/HTTP blocking có thể chặn event-loop nếu viết sai.
- Reactive publishers có backpressure và lifecycle riêng, cần kiến thức đúng.
- Độ trễ phụ thuộc workload, serialization, DB, network và contention.
- Một endpoint trả `String` đơn giản không phải performance benchmark.

Muốn so sánh throughput/latency, cần workload tương đương, tài nguyên CPU/heap như nhau, warm-up, số mẫu và metrics về event-loop, queue, GC, downstream. Chỉ nhìn tên stack không đủ.

## 14. Vòng đời và mã thoát: NONE có thể kết thúc ngay, web mode tồn tại lâu

Trong ví dụ:

~~~text
NONE:
  SpringApplication.run(...)
      -> Runner
      -> Ready event
      -> return to main
      -> context.close()
      -> @Bean DisposableBean.destroy()
      -> JVM exits normally

SERVLET / REACTIVE:
  SpringApplication.run(...)
      -> Runner
      -> Ready event
      -> return to main
      -> HTTP server keeps process available
      -> Ctrl+C / SIGTERM
      -> Spring Boot shutdown hook closes context
      -> @Bean DisposableBean.destroy()
      -> JVM exits after shutdown
~~~

`ApplicationRunner` và `ApplicationReadyEvent` thuộc SpringApplication lifecycle, nên xuất hiện ở cả NONE và hai web modes. Sự khác nhau lớn ở đây là **HTTP server có được tạo và còn giữ ứng dụng phục vụ hay không**.

**Không suy luận mọi NONE app tự tắt:** nếu có scheduler, thread pool với non-daemon threads, consumer hoặc vòng lặp vô hạn, JVM vẫn có thể tiếp tục sống. Demo **chủ động đóng context**, tránh để vòng đời của một bean khác quyết định lúc chương trình kết thúc.

**Không suy luận mọi web app có thể đóng context vô thời hạn:** graceful shutdown có timeouts; task đang chạy hoặc hạ tầng bên ngoài có thể làm cleanup bị giới hạn. Mã demo không bảo đảm callback chạy khi force kill.

## 15. Cấu hình kiểu web từ Java, properties và command line: điểm khác

Có ba nguồn lựa chọn phổ biến:

1. **Classpath inference** khi không chỉ định gì.
2. **Spring configuration** qua `spring.main.web-application-type` trong properties/YAML hoặc CLI.
3. **Java API** `SpringApplication.setWebApplicationType(...)` trước run.

Với bài thực hành, chỉ thay CLI:

~~~bash
java -jar build/libs/three-modes-lab.jar \
    --spring.main.web-application-type=none

java -jar build/libs/three-modes-lab.jar \
    --spring.main.web-application-type=servlet

java -jar build/libs/three-modes-lab.jar \
    --spring.main.web-application-type=reactive
~~~

Chạy **từng lệnh riêng**, bởi ứng dụng servlet/reactive tiếp tục phục vụ HTTP và không tự trả shell prompt cho tới khi dừng. Nếu cấu hình Java của bạn **cố định** mode bằng `setWebApplicationType(...)` hoặc custom application context factory, cần hiểu thứ tự các nguồn cấu hình trong chính ứng dụng, không giả định CLI luôn có thể thay mọi programmatic choice.

Đừng thêm code `application.setWebApplicationType(REACTIVE)` vào demo chính rồi thử `--spring.main.web-application-type=servlet` và kỳ vọng kết quả chắc chắn theo CLI; bài tập cố tình **không hard-code**.

## 16. Khi nào chọn mode nào trong ứng dụng thực tế?

### Chọn NONE

- CLI tools, migration runners, one-shot batch.
- Background workers không nhận HTTP requests.
- Tác vụ scheduler chạy trong context riêng.
- Integration tests chỉ cần DI/service layer, không cần HTTP.
- Spring config làm thư viện cho một process lớn hơn.

**Đảm bảo:** biết ai sở hữu context, khi nào gọi close, và có thread/consumer nào giữ JVM sống hay không.

### Chọn SERVLET

- REST APIs hoặc MVC apps theo servlet ecosystem.
- Ứng dụng hiện có nhiều `Filter`, servlet integrations hoặc synchronous blocking service.
- Kết nối với SDK/JDBC blocking nhưng có pool, timeout và giới hạn concurrency rõ.
- Tổ chức đã vận hành ổn định Tomcat/Jetty/Undertow.

**Đảm bảo:** thread pool, connection pool và server shutdown được cấu hình theo tải. Thêm WebFlux để dùng `WebClient` không nhất thiết là một lý do chuyển toàn bộ server sang REACTIVE.

### Chọn REACTIVE

- Tải nhiều kết nối I/O chủ yếu non-blocking.
- Kiến trúc đã dùng Reactor, `Mono/Flux` và reactive clients/drivers.
- Streaming, server-sent events, request composition bất đồng bộ.
- Cần quản lý backpressure và reactive context đúng cách.

**Đảm bảo:** không chạy blocking I/O dài trên event loops, quan sát thread starvation và sử dụng client/database thực sự tương thích. Một controller trả `Mono` không tự sửa được toàn bộ blocking dependencies.

**Cả ba đều có thể dùng Spring DI, configuration, event listeners, application runners và lifecycle**. Không có mode “tốt nhất” cho mọi ứng dụng; lựa chọn dựa vào **yêu cầu xử lý, thư viện đang dùng và đặc tính tải**.

## 17. Các lỗi thường gặp khi chạy bài thực hành

**Lỗi 1 — “Thêm spring-boot-starter-webflux thì app tự chạy REACTIVE”.**

Sai nếu `spring-boot-starter-web` cũng có mặt: Boot thường ưu tiên MVC/SERVLET theo mặc định. Ép mode bằng property nếu thật sự muốn WebFlux server.

**Lỗi 2 — “NONE vẫn phục vụ controller vì @RestController nằm trong source”.**

Sai. Bean controller có thể được scan nhưng không có web server/dispatcher để nhận HTTP.

**Lỗi 3 — “server.port=0 đồng nghĩa NONE”.**

Sai. Port 0 yêu cầu OS chọn cổng ngẫu nhiên cho server được tạo.

**Lỗi 4 — “server.port=-1 đồng nghĩa không tạo WebApplicationContext”.**

Sai. Trong servlet mode, vẫn có thể có web context nhưng không mở HTTP endpoints.

**Lỗi 5 — “Có Reactor Netty dependency thì request đang chạy trên Netty”.**

Không chắc. Project có cả hai starters mặc định dùng MVC/Tomcat nếu không ép reactive.

**Lỗi 6 — “SERVLET không hỗ trợ response async”.**

Sai. MVC có async request APIs và adapters; khác với reactive server model.

**Lỗi 7 — “REACTIVE luôn non-blocking dù controller gọi JDBC trực tiếp”.**

Sai. Blocking call vẫn block thread đang chạy; có thể phá lợi ích event-loop.

**Lỗi 8 — “@ConditionalOnClass(WebFlux) đủ để nhận biết REACTIVE mode”.**

Sai trong project chứa cả hai starters. Dùng web application condition hoặc kiểm tra context thật.

**Lỗi 9 — “Nếu main() return thì embedded server luôn biến mất”.**

Không đúng. Web server tiếp tục chạy theo lifecycle; không phải phương thức `main` phải nằm trong một vòng lặp.

**Lỗi 10 — “ApplicationReadyEvent chỉ có trong web apps”.**

Sai. NONE vẫn chạy SpringApplication lifecycle và có thể có Ready event.

**Lỗi 11 — “Mỗi lần dùng curl đều thử đúng ứng dụng mới”.**

Không chắc. Nếu một process cũ đang nghe port 8080, lệnh curl có thể đang gọi vào process đó. Dừng mode cũ hoặc dùng `server.port=0` và lấy cổng thật khi test.

**Lỗi 12 — “Cùng controller có nghĩa MVC filter và WebFlux filter giống nhau”.**

Không. Servlet Filter/HttpServletRequest không phải WebFilter/ServerWebExchange.

**Lỗi 13 — “Chỉ cần thêm server.port là chọn được SERVLET hay REACTIVE”.**

Sai. Port là property server; mode được quyết định bởi `spring.main.web-application-type` và classpath.

**Lỗi 14 — “Một test @SpringBootTest mặc định đang kiểm tra WebFlux vì có WebClient”.**

Không chắc. Khi có cả MVC và WebFlux, nó thường chọn servlet. Chỉ định reactive mode trong test hoặc khởi động SpringApplication với property rõ ràng.

**Lỗi 15 — “Cứ ép một mode là mọi app chạy thành công dù thiếu starter”.**

Không. Web mode cần framework và server factory phù hợp; thiếu dependency có thể làm bootstrapping fail.

## 18. Bài tập mở rộng

1. **Không truyền mode**, chạy JAR với cả hai starters: kiểm tra xem có mặc định ra SERVLET hay không. Giải thích vì sao.
2. **Chạy NONE** và quan sát `ApplicationRunner`, `ApplicationReadyEvent`, `CONTEXT_CLOSED=true`. Giải thích vì sao không có port.
3. **Chạy SERVLET**, gọi `/api/mode`, chứng minh body là `SERVLET` và marker bean tương ứng có mặt.
4. **Chạy REACTIVE**, gọi cùng route, chứng minh body là `REACTIVE`.
5. **Chỉ dùng `--server.port=9090`**, giữ mode servlet: endpoint có đổi port nhưng context type có đổi không?
6. **Thử `--server.port=0`** rồi xem log web server/actual port; phân biệt port 0 với không có server.
7. **Thử `--server.port=-1`** với mode servlet, so sánh việc tạo web context và khả năng truy cập HTTP.
8. **Bỏ starter-web** khỏi một bản build **riêng**, không ép mode; xác minh WebFlux được tự suy luận khi còn starter-webflux.
9. **Bỏ cả hai web starters** khỏi một bản build **riêng**; xác minh Boot mặc định NONE nếu không có web stack nào khác.
10. **Tạo bean conditional Servlet** cho `Filter`, bean conditional Reactive cho `WebFilter` và kiểm tra mỗi mode chỉ tạo bean phù hợp.
11. **Thêm endpoint trả Mono<String>**, thử SERVLET và REACTIVE; giải thích vì sao reactive return type không đủ để nhận biết context type.
12. **Thêm một service CPU-bound** rồi đo latency dưới tải nhỏ trên cả hai web modes, không dùng kết quả của một request làm benchmark.
13. **Thêm blocking I/O** trong REACTIVE và dùng thread dump/metrics quan sát event-loop; sửa bằng API non-blocking hoặc offloading có giới hạn.
14. **Thử Spring Security**: so sánh `SecurityFilterChain` và `SecurityWebFilterChain`, đừng dùng cùng một filter chain bean cho cả hai.
15. **Chạy Gradle tests** ba mode, xác minh mỗi test đóng context và không gây port conflict.
16. **Gắn `@PreDestroy` vào một bean managed**, so sánh cleanup khi NONE tự đóng và web modes nhận SIGTERM.
17. **Thử nhiều ApplicationContexts trong cùng JVM**; đảm bảo đóng riêng context đã tạo, không suy luận đóng một context là đóng tất cả.
18. **Viết bảng tự đo** về thời gian startup, số threads và heap usage; ghi rõ JVM/host/config, không bịa kết quả benchmark.

## 19. Checklist tự đánh giá

- Có **một** Gradle project và **một** JAR được dùng cho cả ba phép thử.
- Thay mode bằng `spring.main.web-application-type`, không vô tình đổi code/classpath giữa các lần.
- Biết rằng **cả MVC + WebFlux trên classpath → mặc định SERVLET**.
- NONE tạo non-web ApplicationContext, không tạo embedded web server.
- SERVLET tạo servlet web context, xử lý qua Spring MVC.
- REACTIVE tạo reactive web context, xử lý qua Spring WebFlux.
- Với dependencies của demo, SERVLET dùng Tomcat, REACTIVE dùng Reactor Netty.
- `ApplicationRunner` và `ApplicationReadyEvent` được quan sát ở cả ba mode.
- `@ConditionalOnWebApplication` kiểm soát bean theo web stack, không chỉ theo classpath.
- Controller đơn giản trả cùng API contract ở cả hai web modes.
- NONE không phục vụ HTTP dù controller class tồn tại trong mã nguồn.
- `server.port=0/-1` không đồng nghĩa chọn NONE.
- Tests lấy port thật từ `WebServerApplicationContext`, không dựa vào cổng 8080.
- Không chạy blocking I/O không kiểm soát trên WebFlux event loop.
- Cleanup và graceful shutdown có chủ sở hữu rõ ràng ở cả ba mode.
- Không nhầm `@SpringBootTest` mặc định với reactive test khi có cả hai starters.

### Tài liệu chính thức

- Spring Boot 3.3 — SpringApplication và Web Environment: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — Reactive Web Applications, MVC precedence khi có cả hai starters: https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html
- Spring Boot 3.3 — Embedded Web Servers và `server.port`: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot 3.3 — Testing Spring Boot Applications, detecting web application type: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — `WebApplicationType` enum: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/WebApplicationType.html
- Spring Boot 3.3 — `WebServerApplicationContext` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/context/WebServerApplicationContext.html
- Spring Boot 3.3 — `ConditionalOnWebApplication`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnWebApplication.html
- Spring Framework — WebFlux reference: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework — Spring MVC reference: https://docs.spring.io/spring-framework/reference/web/webmvc.html

**Kết luận:** `WebApplicationType.NONE`, `SERVLET` và `REACTIVE` là **ba mô hình khởi tạo application context và hạ tầng web khác nhau**. Với cùng một Spring Boot project có đủ dependencies, đổi `spring.main.web-application-type` làm thay đổi context, server và request dispatcher, trong khi DI, runner và lifecycle vẫn tồn tại. NONE phù hợp chạy không có HTTP server; SERVLET thường dùng Spring MVC/servlet container; REACTIVE dùng WebFlux/reactive handler stack. Chỉ khẳng định ứng dụng đang ở mode nào sau khi kiểm tra **context thực tế và behavior** — không dựa vào một dependency, một tên thread hoặc một HTTP response đơn lẻ.

# Đặt loại ứng dụng tường minh khi cần

Khi khởi động một ứng dụng Spring Boot, framework cần xác định ứng dụng thuộc loại nào để chọn đúng `ApplicationContext` và hạ tầng web. Một ứng dụng có thể chạy theo mô hình Servlet/MVC, Reactive/WebFlux hoặc không phải ứng dụng web. Spring Boot thường suy luận lựa chọn này từ các thư viện có trên classpath, nhưng trong một số tình huống bạn cần **đặt loại ứng dụng tường minh**.

Spring Boot cung cấp enum `WebApplicationType` với ba giá trị:

- `SERVLET`: ứng dụng web dựa trên Servlet API, thường dùng Spring MVC.
- `REACTIVE`: ứng dụng web reactive, thường dùng Spring WebFlux.
- `NONE`: ứng dụng không chạy dưới dạng web application và không khởi tạo embedded web server.

Bạn có thể đặt loại ứng dụng bằng API của `SpringApplication`, qua `SpringApplicationBuilder` hoặc bằng property `spring.main.web-application-type`.

Bài học thuộc chương **SpringApplication** của **Spring Boot Fundamentals**. Chúng ta sẽ tìm hiểu cách Boot tự suy luận loại ứng dụng, khi nào cần ghi đè lựa chọn đó, ảnh hưởng tới ApplicationContext và web server, cùng cách áp dụng trong ứng dụng batch, command-line, MVC, WebFlux và integration test.

## 1. WebApplicationType là gì?

`WebApplicationType` là enum của Spring Boot:

```java
import org.springframework.boot.WebApplicationType;
```

Enum có ba giá trị:

```java
public enum WebApplicationType {
    NONE,
    SERVLET,
    REACTIVE
}
```

Ý nghĩa từng giá trị:

| Giá trị | Mô hình ứng dụng | Context và hạ tầng thường dùng |
|---|---|---|
| `SERVLET` | Ứng dụng web theo Servlet API, thường là Spring MVC | Servlet web application context và `ServletWebServerFactory` |
| `REACTIVE` | Ứng dụng web reactive, thường là Spring WebFlux | Reactive web application context và `ReactiveWebServerFactory` |
| `NONE` | Ứng dụng không chạy như web application | Context không phải web, không khởi tạo embedded web server |

Loại ứng dụng ảnh hưởng tới cách `SpringApplication` tạo context, chọn các auto-configuration phù hợp và quyết định có khởi tạo web server hay không.

### 1.1. Loại ứng dụng không phải là loại bean

`WebApplicationType` không phải annotation gắn lên controller hay service. Nó là lựa chọn ở cấp **SpringApplication/bootstrap**.

Ví dụ, một class `@Service` vẫn là Spring bean trong cả ứng dụng Servlet, Reactive hoặc non-web nếu component scan và các điều kiện đăng ký cho phép.

Tương tự, việc một class có `@RestController` không tự quyết định `WebApplicationType`. Loại ứng dụng được chọn khi Spring Boot chuẩn bị tạo ApplicationContext; các annotation web sau đó được xử lý trong môi trường phù hợp.

### 1.2. Không đồng nhất WebApplicationType với dependency

Có dependency `spring-boot-starter-web` thường khiến Boot suy luận `SERVLET`; có `spring-boot-starter-webflux` thường khiến Boot suy luận `REACTIVE` nếu không có Spring MVC trên classpath.

Tuy nhiên, dependency chỉ cung cấp class và hạ tầng cần thiết. Việc chọn `WebApplicationType` là quyết định riêng của SpringApplication. Bạn có thể đặt tường minh loại ứng dụng, nhưng cần bảo đảm dependency và server implementation phù hợp với lựa chọn đó.

## 2. Spring Boot tự suy luận loại ứng dụng như thế nào?

Nếu không đặt loại ứng dụng, Spring Boot thường suy luận từ các class có trên runtime classpath.

Ở mức khái niệm:

```text
              Kiểm tra runtime classpath
                         │
                         ▼
       Có Spring WebFlux DispatcherHandler?
                         │
                         ▼
        Có Spring MVC DispatcherServlet?
                         │
          ┌──────────────┴──────────────┐
          │                             │
          ▼                             ▼
 WebFlux có, MVC không             MVC có mặt
          │                             │
          ▼                             ▼
      REACTIVE                      SERVLET
          │
          │ Nếu không có web stack
          ▼
         NONE
```

Quy tắc chính thường gặp:

- Nếu có class nhận diện WebFlux và không có class nhận diện Spring MVC, Boot chọn `REACTIVE`.
- Nếu có Servlet API và các class cần thiết cho ứng dụng Servlet, Boot chọn `SERVLET`.
- Nếu không đáp ứng các điều kiện nhận diện web tương ứng, Boot chọn `NONE`.

Đây là mô tả khái niệm. Chi tiết kiểm tra classpath được triển khai trong `WebApplicationType` và có thể thay đổi theo phiên bản Boot.

### 2.1. Chỉ có Spring MVC

Nếu ứng dụng có dependency:

```groovy
implementation("org.springframework.boot:spring-boot-starter-web")
```

thì runtime classpath thường có Spring MVC và Servlet API. Boot thường chọn `SERVLET`.

Ứng dụng sử dụng các thành phần như:

- `DispatcherServlet`.
- `ServletWebServerApplicationContext`.
- `ServletWebServerFactory`.
- Embedded Tomcat, Jetty hoặc Undertow tùy dependency.

### 2.2. Chỉ có Spring WebFlux

Nếu ứng dụng có:

```groovy
implementation("org.springframework.boot:spring-boot-starter-webflux")
```

và không có Spring MVC trên classpath, Boot thường chọn `REACTIVE`.

Ứng dụng sử dụng các thành phần như:

- `DispatcherHandler`.
- Reactive web application context.
- `ReactiveWebServerFactory`.
- Reactor Netty theo cấu hình mặc định phổ biến, hoặc một server reactive tương thích khác.

### 2.3. Có cả Spring MVC và Spring WebFlux

Đây là tình huống dễ gây nhầm lẫn.

Nếu cả Spring MVC và Spring WebFlux đều có trên classpath, Spring Boot **mặc định ưu tiên Spring MVC** và thường chọn `SERVLET`.

Ví dụ:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-webflux")
}
```

Có thể ứng dụng chỉ thêm WebFlux để dùng `WebClient` trong một ứng dụng MVC. Việc có WebFlux dependency không đồng nghĩa toàn bộ ứng dụng tự chuyển sang reactive server.

Nếu muốn ứng dụng chạy theo WebFlux, bạn có thể đặt `REACTIVE` tường minh. Nhưng cần kiểm tra cấu hình và dependency server tương thích; chỉ thay enum không tự biến code MVC blocking thành reactive.

### 2.4. Không có web dependency

Một ứng dụng chỉ dùng Spring context, scheduler, batch job hoặc command-line runner mà không có web stack phù hợp thường được suy luận là `NONE`.

Ví dụ dependency:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
}
```

Trong trường hợp này, ứng dụng có thể dùng `CommandLineRunner` hoặc `ApplicationRunner` để chạy công việc mà không cần mở cổng HTTP.

### 2.5. Kiểm tra loại được suy luận

Bạn có thể quan sát loại ứng dụng bằng cách cấu hình `SpringApplication` trước khi chạy:

```java
SpringApplication application =
        new SpringApplication(BatchApplication.class);

System.out.println(application.getWebApplicationType());
```

Giá trị được trả về cho biết loại mà instance `SpringApplication` đang giữ. Đây là cách chẩn đoán đơn giản khi muốn hiểu classpath hiện tại đang dẫn tới lựa chọn nào.

Không nên dựa vào một dependency đơn lẻ để đoán chắc chắn loại ứng dụng; hãy kiểm tra runtime classpath và giá trị thực tế.

## 3. Vì sao cần đặt loại ứng dụng tường minh?

Suy luận tự động phù hợp với phần lớn ứng dụng, nhưng có những trường hợp lựa chọn mặc định không trùng với mục đích của chương trình.

Một số tình huống phổ biến:

1. Ứng dụng có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, nhưng bạn muốn chạy WebFlux.
2. Ứng dụng có web dependency dùng cho một thư viện phụ, nhưng tiến trình hiện tại chỉ cần chạy batch hoặc command-line.
3. Cùng một codebase có nhiều entry point: một tiến trình chạy web server, một tiến trình chạy batch job.
4. Test hoặc tool cần tạo non-web ApplicationContext để tránh khởi động server.
5. Bạn muốn loại bỏ sự mơ hồ khi classpath thay đổi do dependency transitively được thêm vào.
6. Một thư viện hoặc plugin làm classpath chứa web API ngoài dự kiến và khiến Boot suy luận loại ứng dụng khác.

Đặt tường minh giúp ý định bootstrap được thể hiện trong code hoặc cấu hình, dễ đọc và dễ vận hành hơn.

### 3.1. Ví dụ: ứng dụng batch có web dependency ngoài dự kiến

Giả sử project dùng một thư viện có dependency transitively kéo theo Servlet API hoặc Spring MVC. Ứng dụng thực tế chỉ cần chạy một job:

```java
@SpringBootApplication
public class ImportJobApplication {

    public static void main(String[] args) {
        SpringApplication.run(ImportJobApplication.class, args);
    }
}
```

Nếu Boot nhận diện classpath như một ứng dụng Servlet, nó có thể tạo web context và cố khởi tạo embedded server. Trong khi đó, chương trình chỉ cần chạy tác vụ import dữ liệu rồi kết thúc.

Bạn có thể đặt `NONE` để xác định rõ đây là tiến trình non-web.

### 3.2. Ví dụ: muốn dùng WebFlux khi cả hai stack có mặt

Nếu ứng dụng thật sự được thiết kế theo reactive stack nhưng một dependency kéo Spring MVC vào classpath, lựa chọn mặc định có thể là Servlet.

Đặt `REACTIVE` tường minh giúp Boot tạo reactive web context. Tuy nhiên, hãy kiểm tra controller, server dependency và auto-configuration tương ứng để bảo đảm ứng dụng nhất quán.

### 3.3. Không dùng WebApplicationType để sửa lỗi kiến trúc

Đặt `NONE` không làm một ứng dụng blocking trở thành batch architecture đúng nghĩa; đặt `REACTIVE` không tự chuyển mọi `RestController` thành non-blocking. Enum chỉ chọn mô hình ApplicationContext/web bootstrap.

Nếu ứng dụng có dependency không cần thiết, hãy xem lại dependency graph. Đặt loại ứng dụng rõ ràng có thể giải quyết lựa chọn bootstrap, nhưng không thay thế việc quản lý dependency và thiết kế kiến trúc.

## 4. Cách 1: đặt loại ứng dụng bằng SpringApplication

Cách trực tiếp là tạo instance `SpringApplication`, gọi `setWebApplicationType(...)`, rồi chạy ứng dụng.

Ví dụ non-web:

```java
package com.example.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ImportJobApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ImportJobApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);

        application.run(args);
    }
}
```

Các bước:

1. Tạo `SpringApplication` với source configuration.
2. Gọi `setWebApplicationType(WebApplicationType.NONE)`.
3. Gọi `run(args)` để bootstrap ứng dụng.

Đối với Servlet hoặc Reactive, thay giá trị enum tương ứng:

```java
application.setWebApplicationType(WebApplicationType.SERVLET);
```

hoặc:

```java
application.setWebApplicationType(WebApplicationType.REACTIVE);
```

### 4.1. Vì sao không dùng SpringApplication.run(...) dạng static?

Cách ngắn:

```java
SpringApplication.run(ImportJobApplication.class, args);
```

tiện lợi khi chấp nhận lựa chọn mặc định. Nhưng phương thức static không cung cấp instance để bạn gọi `setWebApplicationType(...)` trước khi `run`.

Nếu cần đặt loại ứng dụng bằng API, hãy tạo instance như ví dụ trên.

### 4.2. Một helper để tái sử dụng

Nếu có nhiều entry point, có thể tạo phương thức dựng SpringApplication:

```java
public final class ApplicationLauncher {

    private ApplicationLauncher() {
    }

    public static ConfigurableApplicationContext runNonWeb(
            Class<?> source,
            String... args
    ) {
        SpringApplication application = new SpringApplication(source);
        application.setWebApplicationType(WebApplicationType.NONE);
        return application.run(args);
    }
}
```

Sau đó:

```java
public static void main(String[] args) {
    ApplicationLauncher.runNonWeb(ImportJobApplication.class, args);
}
```

Đây là cách tổ chức tùy chọn. Với ứng dụng nhỏ, cấu hình trực tiếp trong `main` thường dễ hiểu hơn. Không cần tạo abstraction riêng nếu chỉ có một entry point.

## 5. Cách 2: dùng SpringApplicationBuilder

`SpringApplicationBuilder` cung cấp API fluent để cấu hình và chạy ứng dụng.

Ví dụ:

```java
package com.example.batch;

import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ImportJobApplication {

    public static void main(String[] args) {
        new SpringApplicationBuilder(ImportJobApplication.class)
                .web(WebApplicationType.NONE)
                .run(args);
    }
}
```

Phương thức `.web(...)` nhận một `WebApplicationType`.

Các lựa chọn:

```java
new SpringApplicationBuilder(Application.class)
        .web(WebApplicationType.NONE)
        .run(args);
```

```java
new SpringApplicationBuilder(Application.class)
        .web(WebApplicationType.SERVLET)
        .run(args);
```

```java
new SpringApplicationBuilder(Application.class)
        .web(WebApplicationType.REACTIVE)
        .run(args);
```

Cách này phù hợp khi cần nối thêm cấu hình builder, ví dụ default properties, initializers, listeners hoặc parent/child contexts.

### 5.1. Kết hợp với default properties

Ví dụ:

```java
new SpringApplicationBuilder(ImportJobApplication.class)
        .web(WebApplicationType.NONE)
        .properties(
                "app.import.batch-size=500",
                "app.import.dry-run=false"
        )
        .run(args);
```

`properties(...)` đặt default properties cho ứng dụng. Các property từ nguồn có độ ưu tiên cao hơn vẫn có thể ghi đè theo quy tắc Environment của Spring Boot.

Loại ứng dụng được đặt riêng bằng `.web(...)`; hai phần cấu hình có mục đích khác nhau.

## 6. Cách 3: cấu hình qua spring.main.web-application-type

Nếu muốn thay đổi loại ứng dụng theo môi trường mà không sửa Java code, dùng property:

```properties
spring.main.web-application-type=none
```

Hoặc YAML:

```yaml
spring:
  main:
    web-application-type: none
```

Các giá trị thường dùng:

| Property value | Enum tương ứng |
|---|---|
| `none` | `WebApplicationType.NONE` |
| `servlet` | `WebApplicationType.SERVLET` |
| `reactive` | `WebApplicationType.REACTIVE` |

Ví dụ chạy JAR:

```bash
java -jar application.jar --spring.main.web-application-type=none
```

Bạn cũng có thể đặt qua biến môi trường theo quy tắc relaxed binding:

```bash
SPRING_MAIN_WEB_APPLICATION_TYPE=none
```

### 6.1. Dùng profile để chọn loại ứng dụng

Một codebase có thể có cấu hình khác nhau theo profile:

```yaml
# application-batch.yml
spring:
  main:
    web-application-type: none
```

```yaml
# application-web.yml
spring:
  main:
    web-application-type: servlet
```

Chạy batch:

```bash
java -jar application.jar --spring.profiles.active=batch
```

Chạy web:

```bash
java -jar application.jar --spring.profiles.active=web
```

Cách này hữu ích khi các profile tương ứng với hai chế độ triển khai được thiết kế rõ ràng. Tuy nhiên, nếu hai chế độ có dependency hoặc lifecycle rất khác nhau, tách thành hai application entry point hoặc hai artifact có thể dễ vận hành hơn.

### 6.2. Property không tự thêm dependency

Đặt:

```properties
spring.main.web-application-type=reactive
```

không tự thêm WebFlux, Reactor Netty hoặc reactive server implementation vào classpath.

Nếu không có các dependency/hạ tầng phù hợp, context có thể không khởi động hoặc không có server factory cần thiết.

Tương tự, đặt `servlet` nhưng không có Servlet web stack/embedded server tương ứng có thể dẫn tới lỗi khi Boot cần tạo web server.

### 6.3. Tránh nhiều nơi cùng đặt một giá trị

Trong một project, loại ứng dụng có thể được đặt qua:

- `SpringApplication#setWebApplicationType(...)`.
- `SpringApplicationBuilder.web(...)`.
- `spring.main.web-application-type`.
- Các cấu hình khởi động do framework hoặc test cung cấp.

Hãy chọn một nơi cấu hình chính để người vận hành dễ hiểu. Nếu vừa đặt qua API vừa đặt property với giá trị khác, hãy kiểm tra hành vi thực tế của phiên bản Boot đang dùng thay vì dựa vào giả định về thứ tự ưu tiên.

## 7. Ảnh hưởng tới ApplicationContext

`WebApplicationType` ảnh hưởng loại context mà Spring Boot tạo.

### 7.1. SERVLET

Với `SERVLET`, Boot tạo context phù hợp với ứng dụng Servlet, thường là `ServletWebServerApplicationContext`.

Context này tích hợp với Servlet API và embedded web server. Spring MVC có thể đăng ký các thành phần như `DispatcherServlet`, handler mappings, message converters và các bean web liên quan khi điều kiện auto-configuration phù hợp.

Luồng khái quát:

```text
SpringApplication
      │
      ▼
WebApplicationType.SERVLET
      │
      ▼
ServletWebServerApplicationContext
      │
      ▼
ServletWebServerFactory
      │
      ▼
Embedded web server
      │
      ▼
DispatcherServlet / Spring MVC
      │
      ▼
HTTP requests
```

### 7.2. REACTIVE

Với `REACTIVE`, Boot tạo context dành cho reactive web application, thường là `ReactiveWebServerApplicationContext`.

Reactive stack sử dụng các abstraction như `DispatcherHandler`, `WebHandler` và `ReactiveWebServerFactory`. Với starter WebFlux thông dụng, Reactor Netty thường là server mặc định nếu không có lựa chọn khác.

Luồng khái quát:

```text
SpringApplication
      │
      ▼
WebApplicationType.REACTIVE
      │
      ▼
ReactiveWebServerApplicationContext
      │
      ▼
ReactiveWebServerFactory
      │
      ▼
Reactive web server
      │
      ▼
DispatcherHandler / WebFlux
      │
      ▼
Reactive HTTP requests
```

### 7.3. NONE

Với `NONE`, Boot tạo ApplicationContext không phải web context và không khởi tạo embedded web server.

Luồng khái quát:

```text
SpringApplication
      │
      ▼
WebApplicationType.NONE
      │
      ▼
Non-web ApplicationContext
      │
      ▼
Bean definitions / dependency injection
      │
      ▼
ApplicationRunner / CommandLineRunner
      │
      ▼
Batch, CLI hoặc background task
```

Ứng dụng vẫn có dependency injection, `@Configuration`, `@Bean`, `@Service`, `Environment`, events và các tính năng Spring context phù hợp. `NONE` chỉ thay đổi mô hình web bootstrap.

### 7.4. Bảng so sánh context

| Khía cạnh | SERVLET | REACTIVE | NONE |
|---|---|---|---|
| Web application context | Có | Có | Không |
| Embedded web server | Có nếu server factory phù hợp | Có nếu reactive server factory phù hợp | Không |
| Stack chính | Servlet/MVC | Reactive/WebFlux | Core Spring context |
| `DispatcherServlet` | Thường có với Spring MVC | Không phải dispatcher chính | Không được thiết lập như MVC web app |
| `DispatcherHandler` | Không phải dispatcher chính | Thường có với WebFlux | Không được thiết lập như reactive web app |
| Dùng `CommandLineRunner` | Có | Có | Có |
| Dependency injection | Có | Có | Có |
| Phù hợp batch/CLI | Có thể, nhưng có web infrastructure không cần thiết | Có thể, nhưng có web infrastructure không cần thiết | Phù hợp khi không cần web |

Các thành phần cụ thể còn phụ thuộc dependency, condition và cấu hình ứng dụng. Bảng mô tả mô hình bootstrap, không khẳng định mọi bean web luôn được tạo trong mọi project.

## 8. Ví dụ hoàn chỉnh: ứng dụng batch chạy với NONE

Giả sử có một job nhập dữ liệu từ file và không cần mở HTTP port.

### 8.1. Cấu trúc project

```text
src/main/java/com/example/importer/
├── ImportJobApplication.java
├── service/
│   └── ImportService.java
└── config/
    └── ImportConfiguration.java
```

### 8.2. Lớp main

```java
package com.example.importer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ImportJobApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ImportJobApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);

        application.run(args);
    }
}
```

### 8.3. Service xử lý dữ liệu

```java
package com.example.importer.service;

import org.springframework.stereotype.Service;

@Service
public class ImportService {

    public void importData() {
        System.out.println("Đang nhập dữ liệu...");
        // Thực hiện logic import thực tế.
        System.out.println("Nhập dữ liệu hoàn tất.");
    }
}
```

### 8.4. Chạy job sau khi context khởi tạo

```java
package com.example.importer;

import com.example.importer.service.ImportService;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class ImportRunner implements CommandLineRunner {

    private final ImportService importService;

    public ImportRunner(ImportService importService) {
        this.importService = importService;
    }

    @Override
    public void run(String... args) {
        importService.importData();
    }
}
```

Khi chạy:

```bash
java -jar import-job.jar
```

Ứng dụng tạo non-web context, inject `ImportService` vào `ImportRunner`, rồi chạy công việc sau khi context refresh. Không có embedded server được mở chỉ để thực hiện job.

### 8.5. Phân biệt NONE với việc tự đóng context ngay lập tức

`NONE` không có nghĩa SpringApplication bỏ qua lifecycle. Context vẫn được refresh, bean singleton vẫn được tạo theo cấu hình, runner vẫn chạy và context được đóng khi ứng dụng kết thúc theo quy trình phù hợp.

Nếu job cần giữ process sống để tiếp tục xử lý nền, bạn phải thiết kế cơ chế chờ/lifecycle riêng. Không nên giả định `NONE` tự động giữ process chạy vô thời hạn.

## 9. Ví dụ: ép ứng dụng chạy WebFlux khi cả hai stack có mặt

Giả sử classpath có cả MVC và WebFlux:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-webflux")
}
```

Theo suy luận mặc định, Boot thường chọn Servlet vì Spring MVC có mặt.

Nếu mục tiêu là reactive application, có thể đặt:

```java
@SpringBootApplication
public class ReactiveApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ReactiveApplication.class);

        application.setWebApplicationType(WebApplicationType.REACTIVE);

        application.run(args);
    }
}
```

Hoặc property:

```yaml
spring:
  main:
    web-application-type: reactive
```

### 9.1. Kiểm tra server implementation

Reactive web application cần một `ReactiveWebServerFactory` phù hợp. Ví dụ với Reactor Netty, dependency `spring-boot-starter-webflux` thông thường sẽ cung cấp server runtime mặc định.

Nếu bạn loại bỏ Reactor Netty hoặc thay server implementation, hãy bảo đảm dependency khác cung cấp reactive server factory tương thích.

Nếu chỉ có MVC embedded server mà không có reactive server factory phù hợp, việc ép `REACTIVE` có thể khiến context không khởi động.

### 9.2. Không nhầm WebClient với WebFlux server

Một ứng dụng Spring MVC có thể sử dụng `WebClient` để gọi dịch vụ HTTP bất đồng bộ mà vẫn chạy trên Servlet stack.

Việc có class `WebClient` hoặc dependency `spring-webflux` không bắt buộc ứng dụng phải là `REACTIVE`. Điều quan trọng là loại web application mà Spring Boot chọn và hạ tầng server mà ứng dụng muốn sử dụng.

Đây là lý do Spring Boot ưu tiên MVC khi cả MVC và WebFlux cùng có mặt: nhiều ứng dụng chỉ cần WebClient chứ không muốn chuyển server stack sang reactive.

## 10. Những điều NONE không làm

Khi đặt `WebApplicationType.NONE`, hãy hiểu chính xác phạm vi tác động.

`NONE`:

- Không tạo web application context theo mô hình Servlet/Reactive.
- Không khởi tạo embedded web server như một phần của web context.
- Không biến Spring container thành một chương trình Java không dùng Spring.
- Không tắt dependency injection.
- Không tự loại bỏ mọi class `@Controller` khỏi component scan.
- Không xóa web dependency khỏi runtime classpath.
- Không biến property/configuration thành feature flag runtime.
- Không thay đổi logic nghiệp vụ trong service.

Một class `@RestController` vẫn có thể được phát hiện như component nếu package nằm trong vùng scan. Nhưng vì ứng dụng đang dùng non-web context, nó không được thiết lập như một endpoint hoạt động trên embedded server theo mô hình web thông thường.

Nếu ứng dụng non-web không cần các controller hoặc web infrastructure, có thể tổ chức package, cấu hình scan hoặc conditions để không đăng ký những thành phần đó.

### 10.1. NONE không phải cách loại dependency

Nếu mục tiêu là giảm kích thước artifact hoặc loại bỏ web libraries khỏi ứng dụng batch, hãy loại dependency không cần thiết khỏi module/build. Đặt `NONE` chỉ chọn non-web context; các JAR vẫn có thể nằm trong runtime classpath.

Ví dụ, nếu batch module không cần MVC, nên tách dependency:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    // Không thêm spring-boot-starter-web nếu module không cần HTTP.
}
```

Tách module giúp dependency graph và ý định triển khai rõ ràng hơn.

## 11. SpringApplicationBuilder và nhiều entry point

Một codebase có thể cung cấp nhiều chương trình khởi động khác nhau.

Ví dụ:

```text
com.example.application
├── ApplicationConfiguration.java
├── WebApplication.java
└── BatchApplication.java
```

Cả hai entry point có thể chia sẻ service/configuration, nhưng lựa chọn web type khác nhau.

### 11.1. Web entry point

```java
public class WebApplication {

    public static void main(String[] args) {
        new SpringApplicationBuilder(ApplicationConfiguration.class)
                .web(WebApplicationType.SERVLET)
                .run(args);
    }
}
```

### 11.2. Batch entry point

```java
public class BatchApplication {

    public static void main(String[] args) {
        new SpringApplicationBuilder(ApplicationConfiguration.class)
                .web(WebApplicationType.NONE)
                .run(args);
    }
}
```

Đây là cách biểu đạt hai chế độ bootstrap. Cần kiểm tra các configuration được chia sẻ không phụ thuộc vào web-only beans. Nếu một service dùng `ServletRequest` hoặc reactive server infrastructure, nó không thể hoạt động trong non-web context nếu dependency đó không được cung cấp.

### 11.3. Khi nào nên tách thành module riêng?

Nếu web và batch có dependency, cấu hình, security và lifecycle rất khác nhau, tách thành module/artifact riêng thường dễ quản lý hơn:

```text
application-core
    ├── domain services
    ├── repositories
    └── shared configuration

application-web
    ├── spring-boot-starter-web
    └── WebApplication

application-batch
    ├── spring-boot-starter
    └── BatchApplication
```

Khi đó mỗi artifact có classpath phù hợp, Boot ít phải suy luận trong tình huống phức tạp và người triển khai dễ biết tiến trình nào cần server.

## 12. Đặt loại ứng dụng trong integration test

Khi viết test, bạn thường không muốn mở một server thật nếu chỉ cần kiểm tra bean wiring hoặc service logic.

Với `@SpringBootTest`, có thể chỉ định web environment:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class ImportServiceIntegrationTest {
}
```

`WebEnvironment.NONE` yêu cầu test context không khởi tạo web environment. Đây là lựa chọn phù hợp cho integration test cần Spring context nhưng không cần server.

Các lựa chọn khác của `SpringBootTest.WebEnvironment` gồm:

- `MOCK`: tạo web application context phù hợp nhưng không khởi động server thật.
- `RANDOM_PORT`: khởi động server và chọn cổng ngẫu nhiên.
- `DEFINED_PORT`: khởi động server trên cổng cấu hình.
- `NONE`: không tạo web environment.

Đây là cấu hình của test bootstrap. Nó có mục đích gần với việc chọn non-web context cho test, nhưng không phải cách thay thế trực tiếp mọi cấu hình `SpringApplication` trong main application.

### 12.1. Khi cần test Servlet hoặc Reactive thật

Nếu cần kiểm tra HTTP integration, hãy dùng `RANDOM_PORT` hoặc `DEFINED_PORT` tùy mục đích. Với `MOCK`, bạn có thể test MVC/WebFlux infrastructure mà không mở network server thật.

Ví dụ Servlet:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class HttpIntegrationTest {
}
```

Ví dụ non-web:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class ServiceIntegrationTest {
}
```

Chọn test environment theo mục tiêu: test service wiring không cần server; test endpoint thực tế cần web environment phù hợp.

## 13. Cấu hình loại ứng dụng bằng property và các nguồn cấu hình

Property `spring.main.web-application-type` là một property thuộc nhóm `spring.main`. Nó có thể được đặt trong các nguồn cấu hình Spring Boot:

- `application.properties`.
- `application.yml`.
- File cấu hình theo profile.
- Biến môi trường.
- System properties.
- Command-line arguments.

Ví dụ `application.properties`:

```properties
spring.main.web-application-type=none
```

System property:

```bash
java -Dspring.main.web-application-type=none -jar application.jar
```

Command-line argument:

```bash
java -jar application.jar --spring.main.web-application-type=none
```

Biến môi trường:

```bash
SPRING_MAIN_WEB_APPLICATION_TYPE=none
```

Trong ứng dụng chạy bằng container, có thể truyền environment variable qua cấu hình deployment thay vì đóng cứng loại ứng dụng vào code.

### 13.1. Property và API programmatic

Có thể đặt loại qua API:

```java
application.setWebApplicationType(WebApplicationType.NONE);
```

hoặc qua property:

```properties
spring.main.web-application-type=none
```

Nếu cả hai cùng được cấu hình, hãy tránh đặt giá trị mâu thuẫn ở nhiều nơi. Cách rõ ràng nhất là có một nguồn cấu hình chủ đạo cho mỗi deployment mode và kiểm tra loại context thực tế khi startup.

Đặc biệt, nếu một `SpringApplication` được tạo và cấu hình bằng code trong một launcher dùng chung, hãy ghi rõ property nào được phép override theo chính sách của ứng dụng. Đừng để người vận hành phải đoán giữa nhiều nguồn cấu hình.

## 14. Quan sát loại context và web server thực tế

Có thể in loại context sau khi ứng dụng khởi động:

```java
ConfigurableApplicationContext context =
        application.run(args);

System.out.println(context.getClass().getName());
```

Ví dụ các context class có thể gặp:

- `ServletWebServerApplicationContext`.
- `ReactiveWebServerApplicationContext`.
- `AnnotationConfigApplicationContext` hoặc context non-web tương ứng.

Tên class cụ thể phụ thuộc phiên bản Boot và cách cấu hình. Dùng phép kiểm tra kiểu nếu muốn kiểm tra chương trình:

```java
if (context instanceof WebServerApplicationContext webContext) {
    System.out.println("Web server: " + webContext.getWebServer().getPort());
} else {
    System.out.println("Ứng dụng không dùng WebServerApplicationContext");
}
```

Cần import:

```java
import org.springframework.boot.web.context.WebServerApplicationContext;
import org.springframework.context.ConfigurableApplicationContext;
```

Trong code nghiệp vụ, thường không cần kiểm tra context class. Ví dụ này hữu ích cho việc học và chẩn đoán bootstrap.

### 14.1. Quan sát bằng log startup

Khi chạy ứng dụng web, Spring Boot thường in log cho biết embedded server đã khởi động và port đang lắng nghe.

Nếu đặt `NONE`, bạn sẽ không thấy log khởi động Tomcat/Jetty/Netty như một web server của ứng dụng. Context vẫn có thể in log startup bình thường và các runner vẫn được gọi.

Đừng dùng việc “không thấy log Tomcat” làm bằng chứng duy nhất; hãy xác nhận context type và cấu hình web application.

## 15. Các lỗi thường gặp khi đặt WebApplicationType

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Ứng dụng batch vẫn mở cổng HTTP | Boot suy luận `SERVLET` từ classpath | Đặt `NONE` hoặc tách web dependency khỏi batch module |
| Muốn WebFlux nhưng ứng dụng chạy MVC | Cả MVC và WebFlux có mặt; Boot mặc định ưu tiên MVC | Đặt `REACTIVE` nếu thật sự cần reactive server và kiểm tra dependency |
| `No qualifying bean of type ServletWebServerFactory` | Chọn `SERVLET` nhưng không có server factory phù hợp | Thêm embedded servlet server dependency tương thích hoặc chọn loại khác |
| `No qualifying bean of type ReactiveWebServerFactory` | Chọn `REACTIVE` nhưng thiếu reactive server implementation | Thêm reactive server dependency phù hợp |
| Đặt `NONE` nhưng vẫn thấy controller bean | Component scan vẫn có thể phát hiện controller như component | Điều chỉnh package scan/conditions nếu không cần bean đó |
| Ứng dụng không có HTTP endpoint sau khi đặt `NONE` | Đây là kết quả đúng của non-web context | Dùng `SERVLET` hoặc `REACTIVE` nếu cần web server |
| IDE chạy web nhưng JAR chạy non-web (hoặc ngược lại) | Classpath hoặc property giữa hai môi trường khác nhau | So sánh runtime dependencies, profiles và `spring.main.web-application-type` |
| Đặt property nhưng loại không như dự kiến | Có nguồn cấu hình khác hoặc launcher programmatic | In/kiểm tra loại SpringApplication và Environment, thống nhất nguồn cấu hình |
| Chọn `REACTIVE` nhưng code block request thread | Ứng dụng có thể đang dùng blocking API | Xem lại thiết kế reactive; enum không biến code blocking thành non-blocking |
| Test vô tình khởi động server | Test dùng `RANDOM_PORT`/`DEFINED_PORT` hoặc web environment mặc định | Chọn `@SpringBootTest(webEnvironment = NONE)` nếu không cần server |

### 15.1. Lỗi thiếu ServletWebServerFactory

Ví dụ thông báo:

```text
ApplicationContextException:
Unable to start web server

Caused by:
NoSuchBeanDefinitionException:
No qualifying bean of type
'org.springframework.boot.web.servlet.server.ServletWebServerFactory'
available
```

Điều này thường cho biết Boot đang tạo Servlet web context nhưng không có factory để tạo server. Kiểm tra:

- Có embedded servlet container dependency không?
- Có loại bỏ Tomcat nhưng chưa thêm Jetty/Undertow không?
- Có đang ép `SERVLET` trong một module vốn chỉ có core starter không?
- Dependency scope có khiến server chỉ tồn tại ở compile time mà không có runtime không?

### 15.2. Lỗi thiếu ReactiveWebServerFactory

Nếu ép `REACTIVE` nhưng thiếu server implementation, có thể thấy lỗi tương tự với `ReactiveWebServerFactory`.

Hãy kiểm tra `spring-boot-starter-webflux` và dependency server tương ứng. Chỉ có `spring-webflux` API chưa chắc đủ để khởi chạy embedded reactive server.

### 15.3. Lỗi không phải lúc nào cũng do WebApplicationType

Nếu ứng dụng không khởi động, có thể nguyên nhân là bean dependency, property, port đã bị chiếm, database connection hoặc init callback. Đừng đổi `WebApplicationType` chỉ vì startup thất bại; hãy đọc exception gốc và xác định context đang được tạo theo loại nào.

## 16. Phân biệt WebApplicationType với các cấu hình liên quan

Một số property/annotation có tên gần nhau nhưng điều khiển những khía cạnh khác nhau.

| Cấu hình | Vai trò |
|---|---|
| `spring.main.web-application-type` | Chọn loại ứng dụng ở bootstrap: none, servlet, reactive |
| `server.port` | Chọn cổng server khi có web server |
| `spring.main.banner-mode` | Điều khiển banner lúc startup |
| `spring.main.lazy-initialization` | Điều khiển lazy initialization ở cấp ứng dụng |
| `@ConditionalOnWebApplication` | Điều kiện cấu hình dựa trên môi trường web |
| `@EnableWebMvc` | Tùy chỉnh/kích hoạt cấu hình Spring MVC theo cách cụ thể |
| `@EnableWebFlux` | Tùy chỉnh/kích hoạt cấu hình Spring WebFlux theo cách cụ thể |
| `spring.webflux.base-path` | Cấu hình base path cho WebFlux trong trường hợp phù hợp |

`server.port=0` không làm ứng dụng thành `NONE`; nó vẫn là web application nhưng server chọn cổng ngẫu nhiên.

`@ConditionalOnWebApplication` cũng không chọn loại ứng dụng. Nó kiểm tra môi trường web mà Spring Boot đã thiết lập để quyết định một cấu hình có được áp dụng hay không.

## 17. Chọn loại ứng dụng cho từng kiến trúc

### 17.1. REST API dùng Spring MVC

Chọn `SERVLET` khi ứng dụng được thiết kế quanh Spring MVC, Servlet filters, servlet container và các API blocking thông thường.

```java
SpringApplication application =
        new SpringApplication(ApiApplication.class);

application.setWebApplicationType(WebApplicationType.SERVLET);
application.run(args);
```

Nếu chỉ có `spring-boot-starter-web`, Boot thường đã tự suy luận đúng. Đặt tường minh hữu ích khi classpath có cả web stacks hoặc khi muốn cố định ý định của deployment.

### 17.2. Reactive API dùng Spring WebFlux

Chọn `REACTIVE` khi ứng dụng được thiết kế để xử lý request theo reactive stack và có reactive server runtime phù hợp.

```java
SpringApplication application =
        new SpringApplication(ReactiveApiApplication.class);

application.setWebApplicationType(WebApplicationType.REACTIVE);
application.run(args);
```

Không chọn `REACTIVE` chỉ vì muốn dùng `Mono` hoặc `Flux` ở một service. Một ứng dụng MVC vẫn có thể dùng Reactor types ở những nơi phù hợp; web application type là lựa chọn ở cấp server/context.

### 17.3. Batch job hoặc command-line tool

Chọn `NONE` khi không cần HTTP server:

```java
SpringApplication application =
        new SpringApplication(BatchApplication.class);

application.setWebApplicationType(WebApplicationType.NONE);
application.run(args);
```

`CommandLineRunner` hoặc `ApplicationRunner` có thể thực thi công việc sau khi context khởi tạo.

### 17.4. Scheduler/background worker

Một tiến trình chỉ chạy scheduler hoặc consumer có thể dùng `NONE` nếu không cần HTTP endpoint. Tuy nhiên, nếu cần actuator endpoint hoặc health endpoint để nền tảng orchestration kiểm tra, bạn cần quyết định rõ cách expose health/management server và loại context phù hợp.

Không nên đặt `NONE` mà vẫn kỳ vọng ứng dụng có endpoint HTTP `/actuator/health` được phục vụ bởi embedded server. Nếu cần HTTP health endpoint, hãy thiết kế web/management context phù hợp với mục tiêu triển khai.

## 18. Những điểm cần lưu ý với Actuator và management server

Spring Boot Actuator có thể cung cấp health, metrics và management endpoints. Khi ứng dụng không phải web application, các endpoint HTTP không tự nhiên có một server để phục vụ.

Nếu yêu cầu vận hành là:

- Batch process chạy xong rồi thoát: `NONE` có thể phù hợp.
- Worker chạy lâu dài và cần health qua HTTP: cân nhắc một web context/management server phù hợp.
- Worker chạy lâu dài và nền tảng kiểm tra qua process signal hoặc file/socket: có thể giữ `NONE` và dùng cơ chế health riêng.

Loại ứng dụng chính và cấu hình management endpoint cần được thiết kế cùng nhau. Đừng giả định thêm `spring-boot-starter-actuator` tự biến một non-web application thành HTTP server.

## 19. Cấu hình tường minh có ảnh hưởng tới auto-configuration ra sao?

Auto-configuration có thể dựa trên điều kiện web application:

```java
@ConditionalOnWebApplication(type = Type.SERVLET)
```

hoặc:

```java
@ConditionalOnWebApplication(type = Type.REACTIVE)
```

Khi đặt `WebApplicationType`, bạn ảnh hưởng môi trường mà các condition này quan sát. Vì vậy, một số auto-configuration có thể được bật hoặc bỏ qua tùy loại ứng dụng.

Ví dụ khái niệm:

```text
WebApplicationType.SERVLET
      │
      ├── Servlet web auto-configuration có thể khớp
      └── Reactive-only auto-configuration không khớp

WebApplicationType.REACTIVE
      │
      ├── Reactive web auto-configuration có thể khớp
      └── Servlet-only auto-configuration không khớp

WebApplicationType.NONE
      │
      ├── Non-web auto-configuration có thể khớp
      └── Web-only auto-configuration thường không khớp
```

Điều này giải thích vì sao đổi loại ứng dụng có thể làm thay đổi danh sách bean. Đó là kết quả của conditional auto-configuration, không phải enum trực tiếp xóa bean của người dùng.

### 19.1. Component scan vẫn là cơ chế riêng

Một class `@Service` hoặc `@Component` vẫn có thể được scan trong cả ba loại ứng dụng. Các cấu hình web chuyên biệt mới thường phụ thuộc `WebApplicationType` hoặc điều kiện web tương ứng.

Vì vậy, nếu muốn một component chỉ tồn tại trong chế độ web, hãy cân nhắc condition hoặc profile trên configuration/component phù hợp. Đừng giả định `NONE` tự động loại mọi class có annotation web.

## 20. Một quy trình quyết định loại ứng dụng

Khi xây dựng một ứng dụng mới hoặc xử lý khác biệt giữa IDE và JAR, có thể đi theo các bước:

### Bước 1 — Xác định tiến trình có cần HTTP server không

- Cần endpoint HTTP: xem `SERVLET` hoặc `REACTIVE`.
- Không cần endpoint HTTP: xem `NONE`.

### Bước 2 — Xác định web programming model

- Spring MVC, Servlet filters, servlet container: `SERVLET`.
- Spring WebFlux và reactive server: `REACTIVE`.
- Không có web stack: `NONE`.

### Bước 3 — Kiểm tra runtime classpath

Xem dependency tree để xác định MVC, WebFlux và server implementation nào có mặt. Đặc biệt kiểm tra dependency transitively.

### Bước 4 — So sánh lựa chọn mặc định với mục tiêu

Nếu classpath đã dẫn đến đúng loại, có thể để Boot tự suy luận. Nếu không, đặt tường minh bằng API hoặc property.

### Bước 5 — Bảo đảm dependency tương thích

`SERVLET` cần Servlet web server factory phù hợp; `REACTIVE` cần reactive web server factory phù hợp; `NONE` không cần embedded web server.

### Bước 6 — Kiểm tra context thực tế

Quan sát context type, log startup và server port. Xác nhận ứng dụng chạy theo đúng mô hình dự kiến.

### Bước 7 — Kiểm tra auto-configuration và bean graph

Nếu đổi loại ứng dụng làm mất một bean, xem condition report, component scan và điều kiện web. Không kết luận rằng bean bị mất chỉ vì enum.

### Bước 8 — Kiểm tra các môi trường chạy

So sánh IDE, Gradle/Maven, executable JAR, container deployment và integration test. Đảm bảo property, profile và runtime classpath nhất quán.

## 21. Ví dụ so sánh ba loại ứng dụng trong cùng một codebase

Một project demo có thể chia thành ba entry point để quan sát:

```text
src/main/java/com/example/demo/
├── shared/
│   └── GreetingService.java
├── servlet/
│   └── ServletApplication.java
├── reactive/
│   └── ReactiveApplication.java
└── batch/
    └── BatchApplication.java
```

Shared service:

```java
package com.example.demo.shared;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greet() {
        return "Hello from shared service";
    }
}
```

Servlet entry point:

```java
package com.example.demo.servlet;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(scanBasePackages = "com.example.demo")
public class ServletApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ServletApplication.class);

        application.setWebApplicationType(WebApplicationType.SERVLET);
        application.run(args);
    }
}
```

Reactive entry point:

```java
package com.example.demo.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(scanBasePackages = "com.example.demo")
public class ReactiveApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ReactiveApplication.class);

        application.setWebApplicationType(WebApplicationType.REACTIVE);
        application.run(args);
    }
}
```

Batch entry point:

```java
package com.example.demo.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(scanBasePackages = "com.example.demo")
public class BatchApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BatchApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }
}
```

Ví dụ này minh họa API bootstrap. Trong một ứng dụng thực tế, không nên đóng gói cả ba entry point với component scanning rộng nếu chúng có các controller/configuration không phù hợp với từng mode. Hãy tách package, configuration hoặc module để mỗi entry point chỉ nạp các thành phần cần thiết.

## 22. Các hiểu lầm thường gặp

### 22.1. “Có spring-webflux là Boot luôn chọn REACTIVE”

Không hẳn. Nếu Spring MVC cũng có trên classpath, Boot thường chọn `SERVLET`. Muốn reactive server trong tình huống đó, hãy đặt `REACTIVE` tường minh và kiểm tra server dependencies.

### 22.2. “Đặt NONE sẽ loại tất cả bean web”

Không. `NONE` chọn non-web context và không khởi tạo embedded web server. Component scan vẫn có thể tìm thấy class có stereotype annotation; điều kiện web và cấu hình ứng dụng quyết định những bean nào được đăng ký.

### 22.3. “Đặt REACTIVE tự chuyển controller MVC thành reactive”

Không. `WebApplicationType` không biến code blocking thành non-blocking. Cần thiết kế handler, return type, I/O và dependency theo reactive programming model.

### 22.4. “Đặt SERVLET tự thêm Tomcat”

Không. Loại ứng dụng chỉ chọn mô hình context. Runtime classpath vẫn cần embedded servlet server implementation phù hợp.

### 22.5. “server.port=0 tương đương NONE”

Không. `server.port=0` vẫn khởi động web server và yêu cầu hệ điều hành chọn một cổng khả dụng. `NONE` không khởi tạo web server.

### 22.6. “WebApplicationType là một property của từng controller”

Không. Nó là lựa chọn bootstrap của SpringApplication, áp dụng cho ApplicationContext được tạo bởi lần chạy đó.

### 22.7. “Dùng NONE là cách tối ưu mọi ứng dụng batch”

Không phải lúc nào cũng vậy. Nếu batch worker cần HTTP health endpoint, management server hoặc giao tiếp web khác, cần thiết kế mô hình phù hợp. `NONE` phù hợp khi tiến trình thực sự không cần web server.

## 23. Bài thực hành

### Bài 1 — Quan sát suy luận mặc định

Tạo project chỉ có `spring-boot-starter`, chạy ứng dụng và in `SpringApplication.getWebApplicationType()`. Sau đó thêm `spring-boot-starter-web` và quan sát thay đổi.

### Bài 2 — So sánh MVC và WebFlux trên classpath

Thêm cả `spring-boot-starter-web` và `spring-boot-starter-webflux`. Quan sát lựa chọn mặc định. Sau đó đặt `REACTIVE` tường minh và xác nhận context/server được chọn.

### Bài 3 — Chạy batch với NONE

Tạo một `CommandLineRunner` thực hiện tác vụ ngắn. Đặt `WebApplicationType.NONE`, chạy JAR và xác nhận không có embedded web server được khởi động.

### Bài 4 — Thử ba cách cấu hình

Chạy cùng ứng dụng với:
- `SpringApplication#setWebApplicationType`.
- `SpringApplicationBuilder.web(...)`.
- `spring.main.web-application-type`.

Ghi nhận cách cấu hình nào đang được dùng trong từng môi trường và giữ một nguồn cấu hình chủ đạo.

### Bài 5 — Quan sát context type

In `context.getClass().getName()` sau startup. So sánh `SERVLET`, `REACTIVE` và `NONE`. Ghi nhận các server-specific bean chỉ xuất hiện trong loại context phù hợp.

### Bài 6 — Kiểm tra property theo profile

Tạo `application-batch.yml` và `application-web.yml` với web application type khác nhau. Chạy từng profile và xác nhận context tương ứng.

### Bài 7 — Thử test không cần server

Viết `@SpringBootTest(webEnvironment = NONE)` cho service integration test. Sau đó dùng `RANDOM_PORT` cho HTTP integration test và so sánh startup behavior.

### Bài 8 — Phân biệt NONE với loại bỏ dependency

Đặt `NONE` nhưng giữ `spring-boot-starter-web` trên classpath. Quan sát server không khởi động nhưng web classes vẫn có trong dependency tree. Sau đó loại starter khỏi module và so sánh artifact/runtime classpath.

## 24. Tài liệu tham khảo chính thức

- [Spring Boot API — WebApplicationType](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/WebApplicationType.html): ba giá trị `NONE`, `SERVLET`, `REACTIVE` và cách suy luận loại ứng dụng.
- [Spring Boot API — SpringApplication](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/SpringApplication.html): `setWebApplicationType(...)`, `getWebApplicationType()` và bootstrap application.
- [Spring Boot API — SpringApplicationBuilder](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/builder/SpringApplicationBuilder.html): cấu hình fluent qua `.web(...)`.
- [Spring Boot Reference — Developing Web Applications](https://docs.spring.io/spring-boot/reference/web/index.html): cách Spring Boot cấu hình ứng dụng Servlet và Reactive.
- [Spring Boot Reference — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest` và các web environment.

`WebApplicationType` cho phép bạn xác định rõ mô hình bootstrap mà Spring Boot cần sử dụng. Hãy để Boot tự suy luận khi classpath phản ánh đúng kiến trúc; đặt `SERVLET`, `REACTIVE` hoặc `NONE` tường minh khi dependency, entry point hoặc môi trường triển khai khiến lựa chọn mặc định không còn diễn tả đúng mục đích ứng dụng. Điều quan trọng là chọn enum phù hợp, bảo đảm có hạ tầng tương ứng và kiểm tra ApplicationContext thực tế sau khi startup.

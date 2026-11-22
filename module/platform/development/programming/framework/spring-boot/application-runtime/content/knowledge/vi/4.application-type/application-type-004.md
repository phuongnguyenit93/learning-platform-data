# Chọn kiểu ứng dụng tường minh bằng setWebApplicationType hoặc spring.main.web-application-type

## 1. Vì sao cần chọn kiểu ứng dụng?

Khi gọi `SpringApplication.run(...)`, Spring Boot phải quyết định sẽ tạo loại `ApplicationContext` nào và có cần khởi động máy chủ Web nhúng hay không. Một ứng dụng HTTP theo Spring MVC khác với ứng dụng WebFlux và khác với chương trình chỉ chạy tác vụ nền hoặc xử lý theo lô (batch).

Thông thường, Spring Boot **suy luận kiểu ứng dụng từ thư viện có trên classpath**. Điều này tiện lợi, nhưng có những trường hợp lập trình viên phải chọn tường minh:

- Một dự án có `spring-boot-starter-web` nhưng ở chế độ chạy theo lô cần khởi tạo bean và thực hiện tác vụ, **không** mở cổng HTTP.
- Dự án chứa cả thư viện Spring MVC và WebFlux, nhưng một cấu hình chạy cụ thể phải dùng mô hình WebFlux.
- Muốn giữ nguyên mã Java, còn cách chạy ở mỗi môi trường được quyết định từ `application.properties`, `application.yml`, biến môi trường hoặc đối số dòng lệnh.
- Khi kiểm thử, muốn khởi tạo phần xử lý nghiệp vụ mà không khởi động máy chủ Web thực tế.

Đề bài này tập trung vào **hai cách quyết định kiểu khởi động**: gọi Java API `SpringApplication.setWebApplicationType(...)` và khai báo thuộc tính `spring.main.web-application-type`. Chúng tác động vào **kiểu ngữ cảnh ứng dụng**, không trực tiếp đổi port, endpoint hay tự thêm thư viện còn thiếu.

## 2. Ba giá trị của WebApplicationType

Enum nằm tại `org.springframework.boot.WebApplicationType` và có ba giá trị:

| Giá trị | Ý nghĩa | Context mặc định trong Spring Boot 3.3 | Máy chủ Web nhúng |
|---|---|---|---|
| `NONE` | Chạy như ứng dụng Spring thông thường, không phải ứng dụng Web | `AnnotationConfigApplicationContext` | Không khởi động |
| `SERVLET` | Chạy ứng dụng Web theo mô hình Servlet, thường là Spring MVC | `AnnotationConfigServletWebServerApplicationContext` | Khởi động khi có hạ tầng Servlet server phù hợp |
| `REACTIVE` | Chạy ứng dụng Web phản ứng, thường là Spring WebFlux | `AnnotationConfigReactiveWebServerApplicationContext` | Khởi động khi có hạ tầng Reactive Web server phù hợp |

Các tên context trong bảng là **mặc định**, khi không tùy chỉnh `ApplicationContextFactory`/lớp context. Chọn `SERVLET` hay `REACTIVE` là yêu cầu một kiểu khởi động; không bảo đảm ứng dụng sẽ chạy thành công nếu classpath thiếu các thành phần cần thiết.

### Spring Boot tự suy luận khi chưa chọn tường minh

Hình dung thuật toán mặc định:

```text
Classpath có các dấu hiệu của Spring MVC / Servlet?
           |
        Có +--------------------> SERVLET
           |
         Không
           v
Classpath có các dấu hiệu của WebFlux?
           |
        Có +--------------------> REACTIVE
           |
         Không
           v
          NONE
```

Đây là cách diễn giải khái quát, không phải mã nguồn chính xác của bộ phát hiện classpath. Khi cả **Spring MVC và WebFlux** cùng có mặt, Spring Boot thường ưu tiên `SERVLET`. Ví dụ: ứng dụng MVC thêm `spring-webflux` để dùng `WebClient` **không tự động biến thành ứng dụng WebFlux**. Có thể ghi đè kiểu mặc định, nhưng phải kiểm tra đầy đủ thư viện, auto-configuration và mô hình controller tương ứng.

Điểm cốt lõi: `WebApplicationType` là **quyết định ở thời điểm bootstrap**. Nó khác `spring.profiles.active` (chọn profile cấu hình), `server.port` (chọn cổng) và `@Primary` (ưu tiên bean khi tiêm phụ thuộc).

## 3. Cách 1: chọn kiểu bằng setWebApplicationType(...)

Chữ ký trong Spring Boot 3.3:

```java
public void setWebApplicationType(WebApplicationType webApplicationType);
```

Cách dùng đúng là tạo `SpringApplication`, thiết lập kiểu, rồi gọi `run(args)`:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;

public class ExampleBootstrap {
    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ExampleBootstrap.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }
}
```

Đoạn trên minh họa cách gọi API. Khi thực hành, lớp bootstrap cần nằm trong dự án Spring Boot với dependency phù hợp và thường được gắn `@SpringBootApplication` như ví dụ hoàn chỉnh ở phần 5.

Các lựa chọn thường gặp:

```java
application.setWebApplicationType(WebApplicationType.NONE);     // Không chạy Web
application.setWebApplicationType(WebApplicationType.SERVLET);  // Servlet Web
application.setWebApplicationType(WebApplicationType.REACTIVE); // Reactive Web
```

Trong code thật, chỉ gọi giá trị mà lần chạy đó cần. Đây **không phải** ba lệnh cần chạy liên tiếp: nếu gọi nhiều lần trước `run` mà không có cấu hình khác, giá trị được thiết lập sau cùng là giá trị của đối tượng `SpringApplication` tại thời điểm đó.

Vì sao phải dùng `new SpringApplication(...)`? Cú pháp rút gọn `SpringApplication.run(App.class, args)` tạo và chạy ứng dụng trong cùng một lời gọi nên không cho ta biến `application` để gọi setter trước `run`. Khi cần tùy biến cấu hình khởi động bằng mã, hãy tạo đối tượng rõ ràng.

Lấy giá trị trên đối tượng ứng dụng:

```java
WebApplicationType chosen = application.getWebApplicationType();
System.out.println(chosen);
```

Lời gọi này cho biết **trạng thái cấu hình tại thời điểm đọc**. Nếu đọc **trước** `run(args)`, hãy lưu ý thuộc tính `spring.main.web-application-type` từ môi trường có thể được liên kết vào `SpringApplication` trong quá trình chuẩn bị khởi động và thay đổi lựa chọn cuối cùng.

## 4. Cách 2: chọn kiểu bằng spring.main.web-application-type

Thuộc tính chính xác:

```properties
spring.main.web-application-type=none
```

Các giá trị thông dụng là `none`, `servlet` và `reactive` (Spring Boot chuyển chúng thành enum tương ứng). Nên dùng chữ thường trong tệp cấu hình, phù hợp cách đặt tên thuộc tính của Spring Boot.

### Trong application.properties

Tệp `src/main/resources/application.properties`:

```properties
spring.application.name=web-mode-demo
spring.main.web-application-type=none
```

Khi chạy, ứng dụng sẽ khởi tạo Spring context không phải Web, kể cả khi dự án có `spring-boot-starter-web`.

### Trong application.yml

Dùng **một** định dạng tệp phù hợp với project, không cần khai báo trùng ở cả hai:

```yaml
spring:
  application:
    name: web-mode-demo
  main:
    web-application-type: none
```

### Qua đối số dòng lệnh

Khi đã đóng gói Spring Boot executable JAR:

```bash
java -jar build/libs/web-mode-demo-0.0.1-SNAPSHOT.jar --spring.main.web-application-type=none
```

Khi chạy bằng Gradle Wrapper (Linux/macOS):

```bash
./gradlew bootRun --args='--spring.main.web-application-type=none'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.main.web-application-type=none"
```

Đối số `--spring.main.web-application-type=none` là **đối số Spring Boot** được truyền tới `main(String[] args)`. `--args` là tùy chọn của tác vụ Gradle `bootRun` để chuyển tiếp đối số vào ứng dụng. Hai cơ chế này không được nhầm với nhau.

### Qua biến môi trường

Spring Boot hỗ trợ liên kết tên biến môi trường theo quy tắc relaxed binding. Ví dụ:

```bash
SPRING_MAIN_WEB_APPLICATION_TYPE=none java -jar build/libs/web-mode-demo-0.0.1-SNAPSHOT.jar
```

Cú pháp Bash trên chỉ áp dụng cho một lần chạy. Trong PowerShell:

```powershell
$env:SPRING_MAIN_WEB_APPLICATION_TYPE = "none"
java -jar .\build\libs\web-mode-demo-0.0.1-SNAPSHOT.jar
Remove-Item Env:SPRING_MAIN_WEB_APPLICATION_TYPE
```

Biến môi trường thuận tiện khi chạy trong container hoặc hệ thống triển khai mà không muốn sửa source code hoặc đóng gói lại JAR. Các biến cấu hình bên ngoài vẫn phụ thuộc quy tắc thứ tự ưu tiên của `PropertySource` trong Spring Boot.

## 5. Ví dụ hoàn chỉnh: cùng một dự án, chạy SERVLET hoặc NONE

Ví dụ dùng **Java 17+**, **Spring Boot 3.3.x**, **Gradle Groovy DSL** và `spring-boot-starter-web`. Ta cố tình có dependency Web, rồi xem việc chọn kiểu tường minh làm thay đổi kết quả như thế nào.

Cấu trúc:

```text
web-mode-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/webmode/
    │   ├── WebModeDemoApplication.java
    │   └── HelloController.java
    └── resources/
        └── application.properties
```

**Tệp `settings.gradle`:**

```groovy
rootProject.name = 'web-mode-demo'
```

**Tệp `build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
}
```

**Tệp `src/main/java/com/example/webmode/WebModeDemoApplication.java`:**

```java
package com.example.webmode;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class WebModeDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(WebModeDemoApplication.class);

        // Chọn kiểu bằng Java API.
        application.setWebApplicationType(WebApplicationType.SERVLET);
        application.run(args);
    }

    @Bean
    CommandLineRunner showContext(ApplicationContext context) {
        return args -> System.out.println(
                "Context type: " + context.getClass().getSimpleName());
    }
}
```

**Tệp `src/main/java/com/example/webmode/HelloController.java`:**

```java
package com.example.webmode;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "xin-chao";
    }
}
```

**Tệp `src/main/resources/application.properties`** (ban đầu chưa đặt kiểu):

```properties
spring.application.name=web-mode-demo
server.port=8080
```

Ví dụ được thiết kế để chạy với Gradle Wrapper đã được tạo từ công cụ khởi tạo dự án hoặc bởi Gradle cài đặt sẵn. Nếu repository chưa có `gradlew`/`gradlew.bat`, cần tạo Wrapper bằng cơ chế chuẩn của dự án trước khi dùng các lệnh dưới đây; không thể gọi Wrapper khi tệp chưa tồn tại.

### Lượt A — chạy SERVLET bằng Java API

Linux/macOS:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Vì `main` gọi `setWebApplicationType(WebApplicationType.SERVLET)` và chưa có thuộc tính bên ngoài ghi đè, context mặc định là Servlet Web context. Trong log có dòng do chương trình in, thường như sau:

```text
Context type: AnnotationConfigServletWebServerApplicationContext
```

Chạy lệnh ở terminal thứ hai:

```bash
curl -s http://localhost:8080/hello
```

Phần thân phản hồi:

```text
xin-chao
```

Windows PowerShell có thể dùng `Invoke-RestMethod http://localhost:8080/hello`. Sự kiện HTTP thành công chứng minh ứng dụng đang phục vụ theo mô hình Servlet. Cần dừng lượt này bằng Ctrl+C trước khi chạy lượt khác cùng cổng.

### Lượt B — cùng mã Java nhưng đặt kiểu NONE ở dòng lệnh

Giữ nguyên cả hai file Java, chạy:

```bash
./gradlew bootRun --args='--spring.main.web-application-type=none'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.main.web-application-type=none"
```

Lần này thuộc tính từ đối số ứng dụng được Spring Boot liên kết trong bước khởi động, có thể **ghi đè** giá trị `SERVLET` đã đặt bằng Java API. Dòng do ứng dụng in sẽ tương tự:

```text
Context type: AnnotationConfigApplicationContext
```

Ứng dụng vẫn tạo các bean Spring thích hợp và chạy `CommandLineRunner`, nhưng **không** tạo Servlet Web server. Nếu không còn luồng nào giữ JVM tiếp tục hoạt động, tiến trình sẽ kết thúc sau khi xong tác vụ; đó là hành vi bình thường của ứng dụng không phải Web. Không có endpoint `http://localhost:8080/hello` từ **lần chạy này**; nếu URL vẫn phản hồi, có thể một tiến trình khác đang chạy tại cổng 8080.

Điều đáng nhớ: bean `HelloController` có thể vẫn được đăng ký do component scan, nhưng khi `WebApplicationType.NONE`, không có hạ tầng Web thực tế để tiếp nhận và ánh xạ yêu cầu HTTP vào controller đó.

### Lượt C — chọn NONE trong tệp cấu hình

Xóa đối số `--spring.main.web-application-type=none` ở lệnh, rồi thêm vào `application.properties`:

```properties
spring.application.name=web-mode-demo
server.port=8080
spring.main.web-application-type=none
```

Chạy lại `./gradlew bootRun`. Kết quả cũng là **ứng dụng không phải Web** mặc dù `main` vẫn gọi `setWebApplicationType(SERVLET)`. Cách này chứng minh **thuộc tính cấu hình ngoài không chỉ dùng để đặt giá trị mặc định**; nó có thể thay thế giá trị setter trong quá trình chuẩn bị chạy.

Để quay lại Servlet mà **không sửa tệp**, có thể dùng đối số dòng lệnh ưu tiên cao hơn tệp cấu hình:

```bash
./gradlew bootRun --args='--spring.main.web-application-type=servlet'
```

Kết quả phụ thuộc vào việc ứng dụng có giữ mặc định đọc đối số dòng lệnh hay không; ví dụ trên giữ cấu hình Spring Boot chuẩn. Nếu port đang bị chiếm bởi ứng dụng khác, cần dừng tiến trình đó hoặc đổi `server.port`.

## 6. Nếu không muốn hard-code lựa chọn trong main

Khi muốn dự án cấu hình kiểu hoàn toàn qua `spring.main.web-application-type`, hãy dùng điểm khởi động đơn giản:

```java
package com.example.webmode;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebModeDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebModeDemoApplication.class, args);
    }
}
```

Đây là **phiên bản thay thế của cùng tệp Java**, không đặt song song với phiên bản ở phần 5. Nếu dùng biến thể này cho dự án thực hành, thêm lại `@Bean CommandLineRunner` ở phần 5 nếu muốn giữ dòng log quan sát kiểu context.

Khi không có cấu hình kiểu, Boot suy luận theo classpath. Với `spring-boot-starter-web`, kết quả thông thường là `SERVLET`. Khi có `spring.main.web-application-type=none`, môi trường chọn `NONE`. Việc dùng static `SpringApplication.run(...)` **không ngăn** Spring Boot đọc và áp dụng thuộc tính `spring.main.*`.

Nên chọn hình thức theo mục đích: setter khi phương thức `main` phải chủ động quyết định, còn property khi vận hành cần đổi kiểu mà không viết lại mã nguồn.

## 7. Chọn REACTIVE: cần cả kiểu phù hợp lẫn dependency tương ứng

Để chạy WebFlux thực thụ, ứng dụng cần hạ tầng reactive HTTP server. Ví dụ một dự án riêng có:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

Khi có **chỉ starter WebFlux** làm Web stack và không có Spring MVC, Spring Boot thường tự chọn `REACTIVE`. Muốn xác định tường minh, dùng một trong hai cách:

```java
application.setWebApplicationType(WebApplicationType.REACTIVE);
```

hoặc:

```properties
spring.main.web-application-type=reactive
```

Chỉ đưa `reactive` vào property **không tự tải** Reactor Netty, WebFlux hoặc các lớp hỗ trợ tương ứng. Trong dự án hiện có `spring-boot-starter-web` nhưng thiếu server reactive, ép `REACTIVE` có thể khiến khởi động thất bại. Đừng coi thay đổi property là cách chuyển tự động toàn bộ kiến trúc từ Servlet sang reactive.

Trường hợp có đồng thời `spring-boot-starter-web` và `spring-boot-starter-webflux`, mặc định thông thường là Servlet. Muốn ép Reactive phải xác minh Spring Boot auto-configuration, servlet/reactive components, thư viện máy chủ Web, endpoint và các tính năng bảo mật tương thích. Chỉ nên làm khi có yêu cầu kiến trúc rõ ràng, không phải để sửa một lỗi cổng hoặc một lỗi controller đơn lẻ.

## 8. Quan hệ giữa setter, properties và độ ưu tiên cấu hình

Khi thấy kết quả chạy không giống lệnh setter, cần xét cả hai tầng:

1. **Trạng thái ban đầu:** constructor `new SpringApplication(...)` suy luận từ classpath; gọi `setWebApplicationType(...)` cập nhật kiểu trên đối tượng Java.
2. **Cấu hình trong quá trình chạy:** Spring Boot chuẩn bị `Environment` và liên kết các thuộc tính `spring.main.*` vào đối tượng `SpringApplication`. Thuộc tính ngoài được nạp có thể **thay thế lựa chọn từ Java API**, trước khi tạo context phù hợp.

Ví dụ trong phần 5:

```text
Classpath: spring-boot-starter-web
              |
       Suy luận: SERVLET
              |
      Java setter: SERVLET
              |
--spring.main.web-application-type=none
              |
      Cuối cùng: NONE
              |
  AnnotationConfigApplicationContext
              |
       Không chạy HTTP
```

Nếu cùng lúc có `application.properties` đặt `none` và đối số dòng lệnh đặt `servlet`, trong cơ chế mặc định của Spring Boot, **đối số dòng lệnh có ưu tiên cao hơn giá trị trong tệp**. Các nguồn cấu hình khác (biến môi trường, JVM system properties, profile và tệp cấu hình ngoài) cũng tham gia thứ tự ưu tiên; khi gặp xung đột, hãy kiểm tra nguồn thực sự được nạp.

**Hai nguyên tắc dễ nhớ:**

- Đừng kết luận `setWebApplicationType(SERVLET)` luôn là lựa chọn cuối nếu vẫn tồn tại `spring.main.web-application-type` từ cấu hình ngoài.
- Đừng giả định `getWebApplicationType()` được in **trước `run`** là bằng chứng cuối cùng. Hãy quan sát context thực tế hoặc kiểm tra hành vi HTTP **sau khi khởi động thành công**.

Nếu ứng dụng sử dụng một `ApplicationContextFactory` tùy biến, loại context thực tế còn chịu ảnh hưởng bởi cách factory được viết; bảng ở phần 2 phản ánh cơ chế mặc định.

## 9. Phân biệt với server.port và các cấu hình khác

| Ý định | Cấu hình | Hệ quả |
|---|---|---|
| Không chạy Web server | `spring.main.web-application-type=none` hoặc `setWebApplicationType(NONE)` | Chọn non-web `ApplicationContext`. |
| Chạy Servlet Web | `spring.main.web-application-type=servlet` hoặc setter `SERVLET` | Dùng hạ tầng Servlet, nếu dependency hỗ trợ. |
| Chạy Reactive Web | `spring.main.web-application-type=reactive` hoặc setter `REACTIVE` | Dùng hạ tầng Reactive, nếu dependency hỗ trợ. |
| Đổi cổng HTTP | `server.port=9090` | Vẫn là ứng dụng Web, chỉ đổi cổng. |
| Cho hệ điều hành tự chọn cổng Web | `server.port=0` | Web server vẫn khởi động trên cổng ngẫu nhiên còn trống. |
| Tắt HTTP endpoint nhưng vẫn giữ Web context | `server.port=-1` | Không tương đương với `WebApplicationType.NONE`. |
| Đổi profile cấu hình | `spring.profiles.active=dev` | Chọn cấu hình/bean theo profile; không trực tiếp là lựa chọn Web type. |

Spring Boot còn có thuộc tính liên quan đến SSL, context path, session, graceful shutdown và nhiều thiết lập Web khác. Chúng điều chỉnh hệ thống Web đã chọn, **không thay cho quyết định kiểu `WebApplicationType`**.

Ví dụ: nếu đã chọn `NONE`, sửa `server.port=9090` không tự tạo HTTP server. Nếu muốn giữ Servlet Web context nhưng không mở HTTP endpoint, `server.port=-1` có ý nghĩa khác và cần kiểm tra các hạ tầng vẫn được khởi tạo.

## 10. Ứng dụng không phải Web vẫn có thể làm những việc gì?

`WebApplicationType.NONE` không có nghĩa là bỏ Spring hoặc bỏ tất cả bean. Ứng dụng vẫn có thể:

- Nạp các `@Configuration`, `@Component` và `@Bean` không phụ thuộc hạ tầng Web.
- Dùng Spring Dependency Injection, cấu hình externalized, logging, validation và bean lifecycle.
- Chạy `CommandLineRunner` hoặc `ApplicationRunner` để xử lý dữ liệu, thực hiện tác vụ theo lô hoặc kiểm tra cấu hình lúc startup.
- Gọi HTTP **ra bên ngoài** qua HTTP client nếu đã cấu hình dependency phù hợp; `NONE` chỉ nói về **vai trò máy chủ Web của ứng dụng**, không chặn mọi kết nối mạng.
- Kết thúc tiến trình khi công việc hoàn thành, nếu không còn non-daemon thread giữ JVM chạy.

Ngược lại, các thành phần cần Servlet request/context hay Reactive Web infrastructure có thể không được cấu hình hoặc không khởi tạo được. Ví dụ một `Filter` Servlet cần runtime Servlet Web đầy đủ; một `@GetMapping` trong controller không tự mở HTTP endpoint ở `NONE`.

Một chương trình xử lý theo lô sử dụng Spring có thể chọn `NONE` và khai báo `CommandLineRunner`:

```java
@Bean
CommandLineRunner runJob() {
    return args -> System.out.println("Xu ly cong viec da xong");
}
```

Đây là đoạn bean minh họa đặt **bên trong** lớp `@SpringBootApplication` hoặc `@Configuration`; không phải một tệp Java tự biên dịch độc lập. Để xử lý exit code, lỗi và tài nguyên của tác vụ nền trong hệ thống thật, cần thiết kế thêm quy tắc kết thúc tiến trình và giám sát công việc.

## 11. Lỗi thường gặp và cách kiểm tra

| Triệu chứng | Nguyên nhân hay gặp | Cách kiểm tra |
|---|---|---|
| Đã gọi setter `SERVLET` nhưng ứng dụng không mở cổng | Property `spring.main.web-application-type=none` từ tệp, biến môi trường hoặc CLI ghi đè | Kiểm tra cấu hình ngoài và loại context chạy thực tế. |
| Đặt `none` nhưng vẫn truy cập được `localhost:8080` | Một tiến trình Web **khác** vẫn còn sống | Dừng phiên cũ; xem PID và log startup của đúng tiến trình. |
| Chọn `SERVLET` nhưng startup báo thiếu Servlet Web server factory | Thiếu dependency tạo server nhúng hoặc cấu hình loại trừ không phù hợp | Xem `runtimeClasspath`, starter-web/server dependency và nguyên nhân gốc của exception. |
| Chọn `REACTIVE` nhưng không khởi động | Thiếu WebFlux/reactive server hoặc có cấu hình xung đột | Kiểm tra Gradle dependencies và điều kiện auto-configuration. |
| Mất endpoint `@GetMapping` khi chọn `NONE` | Ứng dụng không tạo Web server nên không nhận HTTP request | Chuyển về `SERVLET`/`REACTIVE` phù hợp, hoặc dùng non-web runner nếu nhiệm vụ không cần HTTP. |
| Đặt `server.port=9090` mà không có port | Ứng dụng vẫn ở `NONE`; port chỉ áp dụng khi có server | Kiểm tra `spring.main.web-application-type` trước. |
| Gọi `getWebApplicationType()` trước `run` thấy khác kết quả chạy | `spring.main.*` được liên kết trong bước bootstrap sau thời điểm in | Quan sát context sau startup và nguồn property thực tế. |
| Nhập `web` hoặc chuỗi không hợp lệ cho property | Chỉ có `none`, `servlet`, `reactive` | Sửa thành giá trị enum hỗ trợ, đọc lỗi liên kết cấu hình. |
| Dùng đồng thời MVC và WebFlux nhưng mong tự động REACTIVE | Mặc định Servlet được ưu tiên khi có MVC | Chọn kiểu tường minh và xác nhận toàn bộ hạ tầng reactive phù hợp. |

Quy trình xử lý vấn đề thực tế:

1. Xác định đúng tiến trình và lệnh chạy: IDE, `bootRun` hay `java -jar`.
2. Kiểm tra `runtimeClasspath` có starter Servlet/WebFlux nào; đừng đoán dựa trên tên module.
3. Tìm tất cả nơi đang khai báo `spring.main.web-application-type`: cấu hình đóng gói, cấu hình ngoài, profile, env và command line.
4. Quan sát lớp context mà ứng dụng tạo sau bootstrap. Với Web mode, xác nhận máy chủ và endpoint bằng log/HTTP thực tế.
5. Đọc nguyên nhân lỗi gốc (`Caused by`) nếu ứng dụng không chạy. Chỉ đổi Web type khi lỗi liên quan trực tiếp đến kiểu runtime hoặc thiết kế ứng dụng.

Khi cần phân tích sâu lý do một auto-configuration được áp dụng hay bỏ qua, có thể bật báo cáo điều kiện bằng `--debug`. Cần phân biệt cờ debug điều kiện của Spring Boot với chế độ gỡ lỗi từng dòng của IDE.

## 12. Thực hành có kiểm chứng

Với dự án ở phần 5, tiến hành tuần tự, mỗi lần dừng tiến trình cũ trước khi chạy lại:

1. Giữ setter `SERVLET` và không khai báo property. Kiểm tra log context Servlet và phản hồi `GET /hello` là `xin-chao`.
2. Giữ nguyên Java, chạy `bootRun --args='--spring.main.web-application-type=none'`. Kiểm tra context non-web và xác nhận **chính phiên chạy đó** không mở HTTP server.
3. Thêm `spring.main.web-application-type=none` vào `application.properties`. Chạy không truyền `--args` để kiểm tra cấu hình tệp vẫn ghi đè setter Java.
4. Giữ property `none` trong tệp nhưng chạy với `--spring.main.web-application-type=servlet`. Xác nhận trong ví dụ chuẩn, đối số ứng dụng ưu tiên hơn tệp.
5. Thay `main` bằng biến thể `SpringApplication.run(...)` ở phần 6; lặp lại hai giá trị property `none`/`servlet` để thấy có thể chọn kiểu hoàn toàn từ cấu hình.
6. Trong một **dự án thử nghiệm riêng**, thay dependency Web MVC bằng WebFlux và thử `spring.main.web-application-type=reactive`. Xác nhận context Reactive và tránh đánh đồng lựa chọn enum với việc thêm thư viện.

Câu hỏi tự đánh giá: **Vì sao `WebApplicationType.NONE` vẫn chạy được `CommandLineRunner`?** **Vì sao `server.port=0` không tương đương với `NONE`?** **Khi setter và property khác nhau, phải quan sát điều gì để biết cấu hình thực tế đã áp dụng?** Trả lời được ba câu này nghĩa là bạn đã hiểu cả cơ chế lẫn cách kiểm chứng.

## Tài liệu chính thức để đối chiếu

- Spring Boot 3.3, `SpringApplication` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3, enum `WebApplicationType`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/WebApplicationType.html
- Spring Boot 3.3, cơ chế `SpringApplication` và Web Environment: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3, cấu hình vô hiệu hóa máy chủ Web: https://docs.spring.io/spring-boot/3.3/how-to/webserver.html
- Spring Boot, Externalized Configuration và liên kết `spring.main.*`: https://docs.spring.io/spring-boot/reference/features/external-config.html

Kết luận kỹ thuật: **`setWebApplicationType(...)` và `spring.main.web-application-type` đều dùng để xác định loại ứng dụng Spring Boot trước khi context được tạo.** Với cấu hình mặc định, Spring Boot suy luận từ classpath; với lựa chọn tường minh, nó cố gắng tạo context theo kiểu chỉ định. Thành công cuối cùng vẫn phụ thuộc vào dependency, cấu hình và các bean của ứng dụng.
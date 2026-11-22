# Thiết lập phụ thuộc và cấu trúc ứng dụng Spring Web tối thiểu

## Mục tiêu

Sau bài này, bạn có thể tự dựng một ứng dụng HTTP nhỏ bằng Spring Web MVC, biết vì sao từng dependency xuất hiện, đặt đúng các lớp vào cấu trúc package và chạy thử endpoint. Bạn cũng phân biệt hai cách khởi tạo thường gặp:

1. **Spring Framework Web MVC thuần**: tự khai báo `spring-webmvc`, cấu hình `DispatcherServlet` và triển khai trên Servlet container.
2. **Spring Boot + Spring Web MVC**: dùng starter và auto-configuration để có ứng dụng chạy độc lập với embedded server. Đây là cách triển khai ví dụ chạy được ở phần chính.

Hai cách cùng dựa trên Spring MVC/Servlet stack. Spring Boot là lớp hỗ trợ cấu hình và khởi động ứng dụng, **không phải tên thay thế của Spring MVC**.

## 1. Bức tranh tối thiểu: một HTTP request đi qua đâu?

```text
HTTP client
    |
    | GET /api/hello?name=Ada
    v
Servlet container (embedded Tomcat hoặc container bên ngoài)
    |
    v
Spring MVC DispatcherServlet
    |
    +--> HandlerMapping tìm handler khớp GET /api/hello
    +--> HandlerAdapter gọi phương thức controller
    +--> HttpMessageConverter ghi body JSON/text
    |
    v
HTTP response
```

Các vai trò:

| Thành phần | Trách nhiệm trong ứng dụng tối thiểu |
|---|---|
| Java/JDK | Biên dịch và chạy code ứng dụng. |
| Gradle/Maven | Tải dependencies, biên dịch, test, đóng gói. |
| `spring-web` | Hỗ trợ HTTP, request/response, một số abstraction và tiện ích web. |
| `spring-webmvc` | Bổ sung Spring MVC, `DispatcherServlet`, ánh xạ handler và xử lý request theo Servlet stack; có dependency chuyển tiếp đến `spring-web`. |
| Servlet container | Tiếp nhận kết nối/request HTTP và chạy Servlet; ví dụ Tomcat. |
| `@Controller` / `@RestController` | Lớp xử lý endpoint do Spring quản lý. |
| JSON library / converter | Đổi dữ liệu Java sang JSON và ngược lại, khi endpoint cần JSON. |
| Spring Boot starter/auto-configuration | Gom dependency tương thích, cấu hình phần thông dụng, khởi động embedded server. |

**Điểm phân biệt:** chỉ thêm `spring-webmvc` vào project Java không tự sinh một HTTP server đang lắng nghe cổng 8080. Với Spring MVC thuần, bạn còn phải cấu hình và triển khai Servlet; với Spring Boot web starter, Boot tạo và cấu hình embedded Servlet container theo convention.

## 2. Điều kiện cần và lựa chọn phiên bản nhất quán

Ví dụ chính dùng **Java 17**, **Gradle 8.5**, **Spring Boot 3.5.16** và Spring MVC thuộc Spring Framework 6.2.x do Boot quản lý. Đây là một tổ hợp được tài liệu yêu cầu hệ thống của nhánh Boot 3.5 hỗ trợ: Java từ 17, Gradle 8.4+ trong nhánh 8.x. Không dùng đồng thời Spring Boot 4.x với bộ dependency/Gradle cũ nếu chưa đối chiếu yêu cầu phiên bản mới.

Kiểm tra công cụ:

```bash
java -version
javac -version
gradle -version
```

Nếu project đã có **Gradle Wrapper** (`gradlew` / `gradlew.bat`), dùng wrapper thay cho Gradle cài global. Wrapper khóa phiên bản Gradle để các máy cùng xây dựng một project nhất quán. Cần có JDK, không chỉ JRE, để biên dịch.

Để tạo project mới, có thể tạo các tệp được trình bày dưới đây bằng tay hoặc dùng https://start.spring.io/ với:
- Project: Gradle - Groovy hoặc Maven
- Language: Java
- Spring Boot: một bản thuộc nhánh **3.5.x** tương thích Java và build tool
- Packaging: Jar
- Java: 17
- Dependency: **Spring Web**

Ví dụ này nêu rõ `3.5.16` nhằm tái hiện cấu hình; ở project thực tế, cập nhật lên bản vá đang được hỗ trợ trong nhánh bạn chọn và đồng bộ plugin/BOM theo tài liệu chính thức.

## 3. Cấu trúc thư mục của ứng dụng Gradle tối thiểu

```text
spring-web-minimal/
├── settings.gradle
├── build.gradle
├── gradlew                     # Gradle Wrapper trên Unix/macOS
├── gradlew.bat                 # Gradle Wrapper trên Windows
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/webapp/
    │   │       ├── WebApplication.java
    │   │       └── controller/
    │   │           └── HelloController.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/
            └── com/example/webapp/
                └── HelloControllerTest.java
```

Các tệp `gradlew`, `gradlew.bat` và `gradle/wrapper/*` được tạo bởi Gradle Wrapper hoặc Spring Initializr; không cần tự viết nội dung nhị phân của `gradle-wrapper.jar`. Trong lần thử tối thiểu, test file có thể được thêm sau. Nếu tạo bằng tay và máy đã có Gradle thích hợp, lệnh `gradle wrapper --gradle-version 8.5` sẽ tạo wrapper; sau đó ưu tiên gọi wrapper.

Giải thích:

- `settings.gradle` đặt tên project.
- `build.gradle` mô tả plugin, repositories, dependency, Java toolchain và tác vụ build.
- `src/main/java` chứa nguồn chương trình; tên package Java khớp cấu trúc thư mục.
- `src/main/resources` chứa cấu hình được đưa vào classpath lúc chạy.
- `src/test/java` tách bài test khỏi code production.
- `WebApplication` đặt ở package gốc `com.example.webapp`; controller bên dưới `com.example.webapp.controller` để **component scan mặc định** của Boot tìm thấy.
- Với project thực tế, thêm package `service`, `repository`, `config` **khi có nhiệm vụ tương ứng**; không cần tạo các lớp giả chỉ để đủ sơ đồ.

## 4. Khai báo dependency bằng Gradle (Groovy DSL)

Tệp `settings.gradle`:

```groovy
rootProject.name = 'spring-web-minimal'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Vì sao khai báo như vậy?**

- `java` bật compile Java và cấu trúc source set tiêu chuẩn.
- `org.springframework.boot` mang các task Boot như `bootRun` và `bootJar`, hỗ trợ đóng gói executable JAR.
- `io.spring.dependency-management` cho phép quản lý phiên bản thư viện theo dependency management của Spring Boot; trong cấu hình này, không ghi phiên bản riêng cho starter.
- `mavenCentral()` là kho tải thư viện đã công bố.
- `spring-boot-starter-web` kéo vào Spring MVC, các thành phần cần để làm web servlet, Jackson cho JSON và Tomcat nhúng mặc định trong nhánh 3.5.
- `spring-boot-starter-test` đưa các thư viện kiểm thử thường dùng (JUnit Jupiter, Spring Test, assertion/mocking tùy starter).
- `useJUnitPlatform()` cho task `test` chạy bộ kiểm thử JUnit Platform.
- Java toolchain giúp thống nhất JDK biên dịch; máy cần cài toolchain tương ứng hoặc cấu hình cơ chế tự tải toolchain.

Đừng thêm đồng thời một phiên bản `spring-webmvc` tùy ý khi đã dùng starter: Spring Boot dependency management đã lựa chọn bộ Spring Framework tương thích. Nếu buộc override một dependency, cần kiểm tra khả năng tương thích, vì cập nhật riêng một module Spring có thể tạo xung đột binary.

### Nếu dùng Maven thay Gradle

Hai build tool là **hai lựa chọn thay thế**, không cần đặt cả `pom.xml` và `build.gradle` cho cùng ví dụ. Tệp `pom.xml` tương đương cơ bản:

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
    <artifactId>spring-web-minimal</artifactId>
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
```

Maven lấy phiên bản dependency từ parent `spring-boot-starter-parent`; với project Maven thông thường chạy `./mvnw spring-boot:run` hoặc `mvn spring-boot:run` nếu đã cài Maven. Chọn Gradle hay Maven theo hệ thống build của project; logic Spring Web phía Java vẫn như nhau.

## 5. Lớp khởi động ứng dụng

Tệp `src/main/java/com/example/webapp/WebApplication.java`:

```java
package com.example.webapp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebApplication.class, args);
    }
}
```

Đây là lớp Java độc lập về cú pháp nhưng **phải build cùng dependencies Spring Boot** mới biên dịch được. `SpringApplication.run` tạo Spring `ApplicationContext`, áp dụng auto-configuration, tìm beans và khởi động embedded server theo dependency trên classpath.

`@SpringBootApplication` kết hợp các vai trò cấu hình ứng dụng, auto-configuration và component scanning. Vì lớp này ở `com.example.webapp`, Spring mặc định phát hiện các bean bên dưới package đó, gồm `com.example.webapp.controller.HelloController`.

Nếu di chuyển lớp khởi động xuống `com.example.webapp.bootstrap` còn controller ở package anh em, scan mặc định có thể bỏ sót controller. Cách đơn giản là giữ lớp khởi động ở package cha chung.

## 6. Controller HTTP tối thiểu

Tệp `src/main/java/com/example/webapp/controller/HelloController.java`:

```java
package com.example.webapp.controller;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/api/hello")
    public Map<String, String> hello(
            @RequestParam(defaultValue = "bạn") String name) {
        return Map.of("message", "Xin chào, " + name + "!");
    }
}
```

Giải thích dòng chạy:

1. `@RestController` đánh dấu bean web controller; return value thường được viết vào HTTP response body thông qua `HttpMessageConverter` thay vì hiểu là view name.
2. `@GetMapping("/api/hello")` ánh xạ HTTP GET với path `/api/hello`. Không có controller bean thì mapping này không tồn tại.
3. `@RequestParam` lấy tham số query `name`; khi không cung cấp, `defaultValue = "bạn"` được dùng. Nếu không có tên tham số được compiler giữ lại, cần khai báo tường minh `@RequestParam(name = "name", defaultValue = "bạn")` để tránh phụ thuộc metadata tên tham số. Để ví dụ vững chắc giữa cấu hình build, nên dùng dạng khai báo tường minh như bên dưới.
4. `Map<String, String>` là object Java; Jackson và HTTP message converter của starter chuyển nó sang JSON khi response được xử lý.
5. Một key JSON duy nhất giúp kết quả minh họa ổn định; với nhiều key, đừng dựa vào thứ tự thuộc tính JSON trừ khi cấu hình rõ.

Để tránh phụ thuộc cách biên dịch giữ tên tham số, có thể thay đúng khai báo tham số ở trên thành:

```java
@RequestParam(name = "name", defaultValue = "bạn") String name
```

Trong cả hai trường hợp, client có thể gọi `/api/hello?name=Ada` để nhận dữ liệu cá nhân hóa.

Tệp `src/main/resources/application.properties`:

```properties
spring.application.name=spring-web-minimal
server.port=8080
```

`server.port` là cấu hình **Spring Boot** cho embedded web server; nó không tự có tác dụng nếu bạn chỉ chạy Spring Framework MVC thuần bên trong Tomcat ngoài. Nếu không khai báo port, Boot web app mặc định thường dùng 8080. Không cần tạo `web.xml`, `DispatcherServlet` bean thủ công, hay cấu hình Tomcat bằng Java cho ví dụ Boot này.

### Phiên bản controller hoàn toàn tường minh để copy dùng ngay

Để bài thực hành không lệ thuộc metadata tên tham số, đây là toàn văn controller đã chọn cho ví dụ chạy:

```java
package com.example.webapp.controller;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/api/hello")
    public Map<String, String> hello(
            @RequestParam(name = "name", defaultValue = "bạn") String name) {
        return Map.of("message", "Xin chào, " + name + "!");
    }
}
```

Hai khối controller ở mục này minh họa cùng một endpoint; trong project **chỉ tạo một file `HelloController.java`**, với bản tường minh cuối cùng.

## 7. Chạy và xác minh request/response

Ở thư mục gốc project Gradle (nơi có `build.gradle`):

**Windows PowerShell:**

```powershell
.\gradlew.bat clean test
.\gradlew.bat bootRun
```

**Linux/macOS:**

```bash
./gradlew clean test
./gradlew bootRun
```

`bootRun` giữ ứng dụng hoạt động trong terminal; mở terminal thứ hai để gửi request. Ở lần đầu chạy, Gradle có thể cần Internet để tải plugin/dependencies. Đợi ứng dụng thực sự khởi động thành công và server lắng nghe cổng 8080 trước khi thử HTTP.

Dùng `curl.exe` trên Windows, hoặc `curl` trên macOS/Linux:

```powershell
curl.exe -i "http://localhost:8080/api/hello?name=Ada"
```

Ví dụ response body JSON:

```json
{"message":"Xin chào, Ada!"}
```

Header thông thường bao gồm `HTTP/1.1 200` và `Content-Type: application/json` (chi tiết header/status line có thể khác theo server). Khi bỏ query:

```powershell
curl.exe "http://localhost:8080/api/hello"
```

Body mong đợi:

```json
{"message":"Xin chào, bạn!"}
```

Khi gọi `http://localhost:8080/api/missing` và không có handler cho path này, ứng dụng mặc định trả lỗi HTTP 404, dù cấu trúc/JSON lỗi chi tiết phụ thuộc phiên bản và cấu hình.

Đóng gói và chạy bằng executable JAR:

```powershell
.\gradlew.bat bootJar
java -jar build/libs/spring-web-minimal-0.0.1-SNAPSHOT.jar
```

Nếu đổi `rootProject.name` hoặc `version`, tên JAR có thể thay đổi theo cấu hình build. `bootJar` chứa các dependency runtime và cơ chế khởi động cần thiết cho Spring Boot, khác với JAR Java thư viện thông thường.

## 8. Test endpoint bằng Spring Boot + MockMvc

Có thể kiểm tra route và JSON mà không cần mở HTTP server thật trên cổng cố định. Tệp `src/test/java/com/example/webapp/HelloControllerTest.java`:

```java
package com.example.webapp;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class HelloControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void helloUsesQueryParameter() throws Exception {
        mockMvc.perform(get("/api/hello").param("name", "Ada"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Xin chào, Ada!"));
    }

    @Test
    void helloUsesDefaultName() throws Exception {
        mockMvc.perform(get("/api/hello"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message").value("Xin chào, bạn!"));
    }
}
```

`@SpringBootTest` nạp application context; `@AutoConfigureMockMvc` tạo mock Servlet request layer để kiểm tra mapping và response. `mockMvc.perform(...)` không cần chiếm port 8080. Hai assertion kiểm tra ngữ nghĩa của endpoint, không phụ thuộc log và thứ tự JSON.

Chạy:

```powershell
.\gradlew.bat test
```

Khi thành công, Gradle task `test` kết thúc thành công; nếu chạy lại ngay và không có thay đổi, Gradle có thể báo `UP-TO-DATE`. Không gán một stdout cố định cho toàn bộ Gradle run vì log phụ thuộc phiên bản plugin, JDK và môi trường.

## 9. Spring Framework thuần khác gì? Cấu hình Servlet thủ công

Đây là một **phương án triển khai riêng**, để bạn thấy việc Spring Boot đã tự động làm hộ. Nếu chỉ dùng Spring Framework MVC, cần tối thiểu:

- `org.springframework:spring-webmvc` và dependency chuyển tiếp Spring.
- Servlet API tương ứng ở compile classpath.
- Lớp `@Configuration` có `@EnableWebMvc` + `@ComponentScan`.
- Đăng ký `DispatcherServlet` vào Servlet container bằng `WebApplicationInitializer` hoặc `web.xml`.
- Build WAR, triển khai WAR lên container tương thích (ví dụ Tomcat 10.1 cho Jakarta Servlet 6.0). Container ngoài phải chạy để nhận HTTP.

Ví dụ một **project khác**, dùng Gradle + Spring Framework 6.2.19 và Tomcat 10.1:

```text
spring-mvc-war/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/plainweb/
    ├── WebConfig.java
    ├── WebInitializer.java
    └── HelloController.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-mvc-war'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'war'
}

group = 'com.example'
version = '0.0.1'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-webmvc:6.2.19'
    compileOnly 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}
```

Trong ví dụ WAR không dùng Spring Boot: Gradle plugin `war` tạo file WAR; `compileOnly` nghĩa là mã compile cần Servlet API nhưng server bên ngoài sẽ cung cấp runtime Servlet API. Không trộn trực tiếp các class `javax.servlet.*` cũ với Spring Framework 6.x vốn dùng `jakarta.servlet.*`.

`WebConfig.java`:

```java
package com.example.plainweb;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@Configuration
@EnableWebMvc
@ComponentScan(basePackageClasses = WebConfig.class)
public class WebConfig {
}
```

`WebInitializer.java`:

```java
package com.example.plainweb;

import org.springframework.web.servlet.support.AbstractAnnotationConfigDispatcherServletInitializer;

public class WebInitializer
        extends AbstractAnnotationConfigDispatcherServletInitializer {

    @Override
    protected Class<?>[] getRootConfigClasses() {
        return null;
    }

    @Override
    protected Class<?>[] getServletConfigClasses() {
        return new Class<?>[] {WebConfig.class};
    }

    @Override
    protected String[] getServletMappings() {
        return new String[] {"/"};
    }
}
```

`HelloController.java` trong project WAR:

```java
package com.example.plainweb;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/api/hello")
    public String hello() {
        return "Hello from Spring MVC";
    }
}
```

Khi Tomcat phát hiện `WebApplicationInitializer` theo cơ chế Servlet startup, initializer tạo `DispatcherServlet`, sử dụng `WebConfig` để bật các cấu hình MVC và quét bean controller. `@RestController` + trả chuỗi trong ví dụ này tạo **text response**; không yêu cầu Jackson.

Build bằng Gradle:

```bash
./gradlew war
```

Sau đó triển khai `build/libs/spring-mvc-war-0.0.1.war` vào Tomcat 10.1 chạy độc lập. Khi triển khai dưới context path mặc định theo tên WAR, request thường là:

```text
GET http://localhost:8080/spring-mvc-war-0.0.1/api/hello
```

Path thực tế phụ thuộc tên deployment/context path cấu hình trên server; có thể đổi context thành `/` để endpoint thành `/api/hello`. Không dùng `java -jar` để chạy WAR này như Boot JAR, vì không có embedded server/Boot launcher.

### So sánh các cách khởi tạo

| Tiêu chí | Spring Framework MVC thuần | Spring Boot + Spring MVC |
|---|---|---|
| Dependency chính | `spring-webmvc` | `spring-boot-starter-web` trong Boot 3.5 |
| HTTP server | Thường cần Servlet container bên ngoài | Embedded Tomcat mặc định |
| Cấu hình DispatcherServlet | Khai báo initializer hoặc `web.xml` | Boot auto-configuration |
| Khởi động | Deploy WAR lên container | `main()` + `SpringApplication.run` |
| MVC config | `@EnableWebMvc` trong cấu hình Java thuần | Convention + auto-configuration; thường không cần `@EnableWebMvc` |
| Triển khai | WAR truyền thống | Executable JAR thường dùng, có thể cấu hình WAR riêng |
| Khi hữu ích | Hiểu nền tảng, tích hợp hệ thống Servlet cũ | Khởi tạo dịch vụ web nhanh, giảm mã cấu hình |

**Chú ý về `@EnableWebMvc`:** annotation này hợp lý khi bạn tự cấu hình Spring MVC thuần. Với Spring Boot, thêm `@EnableWebMvc` vào cấu hình có thể chuyển quyền quản lý phần lớn MVC config sang bạn và làm mất những tùy chỉnh mặc định của Boot. Khi chỉ cần thêm interceptor, formatter, CORS hoặc resource handler trong Boot, trước hết cân nhắc `WebMvcConfigurer` mà không bật `@EnableWebMvc`.

## 10. Quy tắc tổ chức ứng dụng khi mở rộng

Cấu trúc hai lớp là đủ cho endpoint tối thiểu. Khi yêu cầu nghiệp vụ tăng, giữ trách nhiệm rõ:

```text
com.example.webapp/
├── WebApplication.java
├── controller/
│   └── ProductController.java   # HTTP, request/response, status
├── service/
│   └── ProductService.java      # Quy tắc nghiệp vụ
├── repository/
│   └── ProductRepository.java   # Truy cập dữ liệu nếu có
├── dto/
│   └── ProductResponse.java     # Hợp đồng dữ liệu HTTP
└── config/
    └── WebConfig.java           # Chỉ thêm khi cần custom MVC
```

Đây là sơ đồ gợi ý, **không phải các lớp bắt buộc** để ứng dụng Spring Web chạy. Spring container quản lý object đánh dấu `@Component`, `@Service`, `@Repository` và `@Controller`/`@RestController` khi scan được. Dependency nên được truyền qua constructor; controller chỉ xử lý giao tiếp HTTP, còn business logic phức tạp chuyển vào service để dễ kiểm thử.

### Khi nào dùng các dependency web khác?

- `spring-web` đơn thuần cung cấp nhiều API web/HTTP nhưng **không tương đương** đầy đủ với framework Spring MVC servlet.
- `spring-webmvc` là nền tảng `DispatcherServlet`, handler mappings và annotation controller của Servlet MVC.
- `spring-boot-starter-web` (nhánh Boot 3.5) gom MVC và server cho ứng dụng Servlet chạy độc lập.
- `spring-boot-starter-webflux` phục vụ stack reactive, có mô hình xử lý khác; không thêm chỉ vì muốn tạo REST endpoint đơn giản.
- Jackson chủ yếu cần khi làm JSON; Spring MVC có thể trả văn bản mà không cần Jackson.
- Spring Boot 4.x đã tái tổ chức tên web starter (ví dụ `spring-boot-starter-webmvc`). Không copy file build Boot 3.5 sang Boot 4 rồi kỳ vọng tất cả version/dependency giữ nguyên.

**Dependency tối thiểu** phụ thuộc kiểu triển khai: servlet MVC thuần và Boot MVC không cần cùng một danh sách thư viện khai báo trực tiếp.

## 11. Sự cố thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân thường gặp | Bước xử lý |
|---|---|---|
| Build không tải được `spring-boot-starter-web` | Thiếu `mavenCentral()`, sai tọa độ, mạng/proxy, repository credentials. | Kiểm tra `repositories`, internet, `./gradlew dependencies` và lỗi resolve thực tế. |
| `Unsupported class file major version` hoặc toolchain failure | JDK/Gradle/plugin không tương thích, Gradle chạy bằng JDK khác. | Xem `java -version` và `./gradlew --version`; chọn bộ version được hỗ trợ. |
| `Port 8080 was already in use` | Ứng dụng khác giữ cổng 8080. | Dừng process chiếm cổng hoặc đặt `server.port=8081` rồi thử cổng mới. |
| HTTP 404 cho `/api/hello` | Sai path, sai HTTP method, controller nằm ngoài phạm vi scan, ứng dụng chưa chạy hoặc context path khác. | Kiểm tra package của `WebApplication`, annotation, mapping và URL thực tế. |
| HTTP 405 | Có route nhưng không hỗ trợ HTTP method đã gửi. | So khớp GET/POST với annotation. |
| Body trả lỗi chuyển đổi JSON | Thiếu JSON converter hoặc type/serialization lỗi. | Kiểm tra starter, Jackson và loại dữ liệu response. |
| Spring bean không tìm thấy | Package scan không bao phủ bean hoặc chưa đánh dấu stereotype/config. | Đặt app ở root package, kiểm tra bean declarations. |
| `ClassNotFoundException: jakarta.servlet...` | API Servlet vắng mặt lúc chạy WAR trên container hoặc phối phiên bản không tương thích. | Chạy WAR trên container Servlet/Jakarta phù hợp; tránh `javax.servlet` ở Spring 6.x. |
| Tạo WAR thuần nhưng chạy `java -jar` | WAR không có Boot launcher/embedded container. | Triển khai vào Tomcat hoặc đổi thiết kế sang Spring Boot executable JAR. |
| Tự thêm `@EnableWebMvc` trong Boot rồi static resource/MVC behavior thay đổi | Override phần auto-configuration MVC mặc định. | Gỡ annotation nếu không cần nắm toàn quyền MVC; dùng `WebMvcConfigurer` để mở rộng. |

Một số lệnh hữu ích trong project Gradle:

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew clean test
./gradlew bootRun
```

Lệnh cuối chỉ tồn tại nếu project áp dụng Spring Boot Gradle plugin. Không suy ra nguyên nhân từ mỗi mã lỗi HTTP mà chưa kiểm tra log, mapping, port, context path và môi trường runtime.

## 12. Bài thực hành củng cố

1. Chạy ứng dụng Boot với endpoint `GET /api/hello?name=Ada` và xác nhận JSON.
2. Thêm endpoint `GET /api/ping` trả về một `Map` với key `status` và value `up`. Giữ controller hiện tại hoặc thêm controller mới dưới `com.example.webapp.controller`.
3. Đặt `server.port=8081`, chạy lại và thử đúng cổng; giải thích vì sao đổi port không đổi `@GetMapping`.
4. Di chuyển controller sang package **không nằm dưới** `com.example.webapp` (chỉ thử trong project mẫu), nhận diện nguyên nhân 404, rồi sửa lại cấu trúc package.
5. Nếu muốn khảo sát cơ chế gốc, build ví dụ WAR thuần và deploy lên Tomcat tương thích, đối chiếu context path và cách đăng ký `DispatcherServlet`.

### Tự kiểm tra

**Hỏi:** Thêm `spring-webmvc` vào một project Java đã đủ có HTTP server chưa?  
**Đáp:** Chưa. Spring MVC cần Servlet container và registration của `DispatcherServlet`; Spring Boot web starter hỗ trợ tự động khởi tạo embedded container.

**Hỏi:** Vì sao controller để trong `com.example.webapp.controller` dễ được tìm thấy?  
**Đáp:** `@SpringBootApplication` trên `com.example.webapp.WebApplication` kích hoạt component scan từ package của lớp khởi động xuống subpackages.

**Hỏi:** Có nên thêm `@EnableWebMvc` để endpoint Boot có thể chạy?  
**Đáp:** Không cần trong ví dụ Boot MVC thông thường. Boot đã auto-configure MVC; thêm annotation đó có thể thay đổi cấu hình mặc định.

**Hỏi:** Làm sao bảo đảm mọi máy dùng cùng phiên bản Gradle?  
**Đáp:** Commit Gradle Wrapper và chạy `./gradlew` hoặc `.\gradlew.bat`; đồng thời kiểm soát Java toolchain và phiên bản plugin/dependency.

## Tài liệu chính thức

- Spring Framework — DispatcherServlet: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html
- Spring Framework 6.2 — Servlet initialization: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet/container-config.html
- Spring Framework 6.2 — Enable Web MVC configuration: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/enable.html
- Spring Boot 3.5 — System Requirements: https://docs.spring.io/spring-boot/3.5/system-requirements.html
- Spring Boot 3.5 — Embedded Web Servers: https://docs.spring.io/spring-boot/3.5/how-to/webserver.html
- Spring Initializr: https://start.spring.io/

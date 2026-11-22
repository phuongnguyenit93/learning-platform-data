# Thay máy chủ nhúng mặc định của Spring Boot bằng Jetty hoặc Undertow

> **Phạm vi:** Spring Boot **3.5.0**, **Java 17+**, ứng dụng Spring MVC chạy bằng executable JAR. Bài hướng dẫn chuyển từ **embedded Tomcat** (mặc định của `spring-boot-starter-web`) sang **embedded Jetty** hoặc **embedded Undertow** bằng cách loại dependency mặc định và bổ sung starter của máy chủ muốn dùng. Các ví dụ Maven và Gradle sử dụng dependency management của Spring Boot để chọn phiên bản tương thích.

## 1. Spring Boot chọn máy chủ nhúng như thế nào?

Khi thêm dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

một ứng dụng Spring MVC thường kéo theo starter **`spring-boot-starter-tomcat`** thông qua dependency dạng transitive. Khi ứng dụng bắt đầu, Spring Boot autoconfiguration phát hiện thư viện web server trên classpath và tạo servlet container nhúng phù hợp. Vì vậy, chạy chương trình có `@SpringBootApplication` và `SpringApplication.run(...)` có thể mở cổng HTTP mà không phải tự cấu hình hoặc triển khai một Tomcat bên ngoài.

Cần phân biệt:

- **`spring-boot-starter-web`:** tập hợp dependency cho Spring MVC, HTTP, JSON và mặc định một servlet container.
- **`spring-boot-starter-tomcat`:** starter của embedded Tomcat; được Spring Web starter kéo theo ở chế độ mặc định.
- **`spring-boot-starter-jetty`:** starter cho embedded Jetty.
- **`spring-boot-starter-undertow`:** starter cho embedded Undertow.
- **Servlet API và Spring MVC:** lớp xử lý request của ứng dụng, nhìn chung không đổi khi đổi embedded servlet container.

Quá trình chọn máy chủ chủ yếu dựa vào **classpath sau khi Maven hoặc Gradle giải quyết toàn bộ dependency**, không dựa vào một thuộc tính kiểu `server.type=jetty`. Thay tên một giá trị trong `application.properties` không đủ để thay container.

### Mô hình trước và sau

~~~text
Trước:
spring-boot-starter-web
    |
    +-- spring-webmvc, Spring MVC ...
    |
    +-- spring-boot-starter-tomcat
            |
            +-- embedded Tomcat

Sau (Jetty):
spring-boot-starter-web
    |
    +-- spring-webmvc, Spring MVC ...
    |
    +-- (loại spring-boot-starter-tomcat)
    |
    +-- thêm spring-boot-starter-jetty
            |
            +-- embedded Jetty
~~~

Để chuyển máy chủ đúng cách, **vừa loại Tomcat khỏi dependency path của web starter, vừa thêm starter của server mới**. Sau đó kiểm tra dependency tree và startup để chắc chắn classpath chỉ còn container dự kiến.

## 2. Ví dụ Maven hoàn chỉnh: thay Tomcat bằng Jetty

Tạo project có cấu trúc:

~~~text
embedded-server-demo/
  pom.xml
  src/
    main/
      java/
        com/
          example/
            serverdemo/
              ServerDemoApplication.java
              HelloController.java
      resources/
        application.properties
    test/
      java/
        com/
          example/
            serverdemo/
              HelloControllerIntegrationTest.java
~~~

### 2.1. `pom.xml`

File dưới đây là một Maven project độc lập dùng **Spring Boot 3.5.0**. Parent quản lý phiên bản và plugin; **không cần tự gắn phiên bản riêng** cho starter Jetty.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>embedded-server-demo</artifactId>
    <version>1.0.0</version>
    <name>embedded-server-demo</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
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

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jetty</artifactId>
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

**Ý nghĩa cấu hình:**

1. Dependency `spring-boot-starter-web` vẫn giữ Spring MVC và phần web application cần thiết.
2. Khối `<exclusions>` loại `spring-boot-starter-tomcat` khỏi nhánh transitive của `spring-boot-starter-web`.
3. Thêm `spring-boot-starter-jetty` khiến các thành phần Jetty cần thiết xuất hiện trên classpath.
4. Dùng chung dependency management của parent Spring Boot để giữ phiên bản Spring Framework, servlet server và thư viện liên quan tương thích.
5. `spring-boot-maven-plugin` tạo executable JAR; khi chạy bằng `java -jar`, embedded Jetty nằm trong ứng dụng, không yêu cầu cài Jetty rời.

**Lưu ý:** exclusion áp dụng cho **một đường dependency cụ thể**. Nếu một dependency khác cũng đưa Tomcat vào classpath, Tomcat có thể vẫn còn. Vì thế, bước kiểm tra dependency tree là bắt buộc, đặc biệt trong dự án nhiều module hoặc có nhiều web starter.

### 2.2. Java source có thể chạy

`src/main/java/com/example/serverdemo/ServerDemoApplication.java`:

~~~java
package com.example.serverdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ServerDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServerDemoApplication.class, args);
    }
}
~~~

`src/main/java/com/example/serverdemo/HelloController.java`:

~~~java
package com.example.serverdemo;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public Map<String, String> hello() {
        return Map.of("message", "Hello from Spring MVC");
    }
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=9090
server.servlet.context-path=/api
~~~

Đây đều là cấu hình cấp ứng dụng và servlet context, tiếp tục có hiệu lực sau khi đổi Tomcat sang Jetty. Controller xử lý cùng một đường dẫn `/hello`, nhưng từ bên ngoài sẽ truy cập qua `/api/hello` do `server.servlet.context-path=/api`.

### 2.3. Chạy và xác nhận kết quả

Từ thư mục có `pom.xml`:

~~~bash
mvn clean package
java -jar target/embedded-server-demo-1.0.0.jar
~~~

Hoặc trong môi trường phát triển:

~~~bash
mvn spring-boot:run
~~~

Trong log khởi động, tìm thông tin cho thấy **Jetty** được khởi tạo và server lắng nghe cổng **9090**. Thông điệp log cụ thể phụ thuộc phiên bản và cấu hình logging; không nên kiểm tra bằng cách đòi đúng từng chữ của một dòng log.

Gọi HTTP:

~~~bash
curl -i http://localhost:9090/api/hello
~~~

Khi server khởi động thành công và không có thành phần khác can thiệp, body JSON có nội dung:

~~~json
{"message":"Hello from Spring MVC"}
~~~

Với Spring Boot 3.x, `@RestController` và `Map` trả về JSON thông qua message converter trên classpath. Thứ tự các response header và cách hiển thị status line có thể khác nhau giữa phiên bản curl và máy chủ.

Nếu cổng `9090` đã bị một ứng dụng khác sử dụng, Spring Boot có thể thất bại ở bước bind. Việc đổi servlet container **không tự động giải quyết xung đột cổng**; hãy đổi `server.port` hoặc tắt process đang chiếm cổng.

## 3. Thay Jetty bằng Undertow trong Maven

Để chuyển từ bản Jetty ở mục 2 sang Undertow, giữ nguyên Java source, `application.properties` và các dependency web/test. Trong `pom.xml`, **bỏ dependency `spring-boot-starter-jetty`, thay bằng**:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-undertow</artifactId>
</dependency>
~~~

Đồng thời vẫn giữ exclusion của Tomcat bên trong `spring-boot-starter-web`:

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

Hai đoạn XML này là **dependency fragments** cần đặt trong cùng thẻ `<dependencies>` của `pom.xml`; các thành phần còn lại giữ theo ví dụ Maven hoàn chỉnh ở trên.

Chạy lại:

~~~bash
mvn clean package
java -jar target/embedded-server-demo-1.0.0.jar
~~~

Cấu hình `server.port`, `server.servlet.context-path` và controller MVC vẫn hoạt động theo cùng hợp đồng. Kiểm tra log startup và dependency tree để bảo đảm bản build mới thực sự đang dùng Undertow.

Không giữ cả Jetty và Undertow trong cùng project trừ khi có cấu hình đặc biệt và hiểu rõ cách tạo web server factory. Nếu chỉ muốn **một** embedded server, hãy để **một** starter container tương ứng trên classpath.

## 4. Cấu hình Gradle Groovy DSL

Nếu project dùng Gradle, cách chuyển giống Maven: loại Tomcat khỏi web starter rồi thêm Jetty hoặc Undertow.

Ví dụ `build.gradle` hoàn chỉnh cho Jetty với Spring Boot 3.5.0 và Java 17:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation('org.springframework.boot:spring-boot-starter-web') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-tomcat'
    }

    implementation 'org.springframework.boot:spring-boot-starter-jetty'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Dùng cùng Java source và file `application.properties` của phần Maven. Nếu đã có Gradle Wrapper:

~~~bash
./gradlew clean bootJar
java -jar build/libs/embedded-server-demo-1.0.0.jar
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat clean bootJar
java -jar build/libs/embedded-server-demo-1.0.0.jar
~~~

Nếu đổi sang Undertow, thay đúng dòng:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-jetty'
~~~

thành:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-undertow'
~~~

**Không xóa dòng exclusion của Tomcat**.

### Gradle Kotlin DSL

Trong project đã có plugin và repositories thích hợp, đoạn `dependencies` trong `build.gradle.kts`:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web") {
        exclude(
            group = "org.springframework.boot",
            module = "spring-boot-starter-tomcat"
        )
    }

    implementation("org.springframework.boot:spring-boot-starter-jetty")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Đây là **fragment Kotlin DSL**, không phải toàn bộ file build. Để đổi sang Undertow, thay `spring-boot-starter-jetty` bằng `spring-boot-starter-undertow` và giữ exclusion tương tự.

## 5. Xác nhận dependency tree: tránh tưởng đã đổi nhưng Tomcat vẫn còn

Chạy lệnh Maven:

~~~bash
mvn dependency:tree
~~~

Tìm các dependency liên quan:

- Với bản **Jetty**: mong đợi `spring-boot-starter-jetty` và các thư viện Jetty; **không mong đợi `spring-boot-starter-tomcat`** hoặc embedded Tomcat do một nhánh khác kéo vào.
- Với bản **Undertow**: mong đợi `spring-boot-starter-undertow` và các thư viện Undertow; **không mong đợi `spring-boot-starter-tomcat`**.
- Nếu vẫn xuất hiện `spring-boot-starter-tomcat` hoặc `tomcat-embed-*`, kiểm tra nhánh phía trên trong dependency tree để tìm chính xác dependency đã kéo nó vào.

Với Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Muốn tìm lý do một dependency có mặt:

~~~bash
./gradlew dependencyInsight --dependency spring-boot-starter-tomcat --configuration runtimeClasspath
~~~

Khi một dependency khác kéo Tomcat vào, hãy loại nó tại nhánh tương ứng, chọn dependency thay thế phù hợp hoặc cấu hình dependency graph có chủ đích. Không đoán rằng exclusion đặt vào `spring-boot-starter-web` luôn loại Tomcat khỏi **mọi** nhánh của hệ thống.

### Đối chiếu runtime

Tại runtime, ba phép kiểm tra bổ sung nhau:

1. **Dependency tree:** xác nhận cấu phần build.
2. **Startup log:** quan sát web server factory nào thực sự khởi tạo và server nào được mở.
3. **HTTP integration test:** xác nhận endpoint có thể truy cập và xử lý đúng request.

Chỉ thấy response `200 OK` chưa chứng minh server đã đổi: Tomcat, Jetty và Undertow đều có thể phục vụ cùng một endpoint. Vì vậy phải kiểm tra cả build và runtime.

## 6. Kiểm thử tự động khi thay embedded server

Việc thay máy chủ thường không cần đổi controller, nhưng có thể làm lộ khác biệt về HTTP parsing, header size, timeout, compression, WebSocket hoặc file upload. Nên chạy test tích hợp với server thật và cổng động.

Tạo `src/test/java/com/example/serverdemo/HelloControllerIntegrationTest.java`:

~~~java
package com.example.serverdemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HelloControllerIntegrationTest {

    @LocalServerPort
    private int port;

    @Test
    void helloEndpointWorksWithEmbeddedServer() throws Exception {
        assertTrue(port > 0);

        URI uri = URI.create("http://localhost:" + port + "/api/hello");
        HttpRequest request = HttpRequest.newBuilder(uri)
                .GET()
                .build();

        HttpResponse<String> response = HttpClient.newHttpClient()
                .send(request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertEquals(
                "{\"message\":\"Hello from Spring MVC\"}",
                response.body()
        );
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Hoặc với Gradle:

~~~bash
./gradlew test
~~~

Giải thích:

- `@SpringBootTest(webEnvironment = RANDOM_PORT)` khởi động web server **thật** và chọn cổng khả dụng, giảm xung đột port trong CI.
- `@LocalServerPort` nhận cổng HTTP của server đã khởi tạo. Đây là annotation dành cho test, giúp tránh hard-code cổng 9090.
- Spring Boot vẫn đọc `server.servlet.context-path=/api`; URL test phải chứa `/api/hello`.
- Java `HttpClient` gửi HTTP thực; kiểm tra cả status code và nội dung body.
- `@WebMvcTest` và MockMvc hữu ích cho controller nhưng **không thay thế** bài test xác minh embedded container thực sự khởi động.

Trong ví dụ này, body JSON có đúng **một thuộc tính**, nên chuỗi kỳ vọng ổn định với cấu hình JSON mặc định. Nếu response có nhiều thuộc tính, nên so sánh nội dung JSON theo cấu trúc để tránh phụ thuộc thứ tự khóa.

Sau khi đổi server, nên chạy lại regression tests cho các tính năng thực tế ứng dụng dùng: session/cookie, redirect, xử lý lỗi, upload, streaming/SSE, WebSocket và TLS nếu có.

## 7. Các thành phần thường không thay đổi

Việc đổi embedded server **không đồng nghĩa với chuyển framework web**. Trong cùng một ứng dụng Spring MVC, các thành phần dưới đây thông thường giữ nguyên:

| Thành phần | Sau khi Tomcat → Jetty/Undertow |
|---|---|
| `@RestController`, `@GetMapping`, `@PostMapping` | Giữ controller/mapping |
| `@RequestParam`, `@RequestBody`, `@ModelAttribute` | Vẫn do Spring MVC xử lý |
| Bean validation và Jackson | Giữ cách dùng nếu dependency vẫn đầy đủ |
| `server.port` | Vẫn cấu hình cổng lắng nghe |
| `server.servlet.context-path` | Vẫn định nghĩa context path |
| `@SpringBootTest(RANDOM_PORT)` | Vẫn dùng được với embedded server tương thích |
| `WebServerInitializedEvent` | Vẫn dùng để biết server đã được khởi tạo |
| Spring Boot executable JAR | Vẫn có thể chạy với `java -jar` |

Điểm thay đổi là **implementation của servlet container** và một số hành vi phía dưới Spring MVC: connector/threading, cách quản lý connection, giới hạn HTTP, xử lý request bất thường, TLS/HTTP2, WebSocket, session serialization và hiệu năng.

Vì thế, không cần viết lại controller chỉ vì đổi container. Nhưng cũng không nên tuyên bố rằng mọi request đều hành xử giống nhau ở mức wire protocol hoặc khi gặp cấu hình không mặc định.

## 8. Những cấu hình cần rà soát sau khi đổi container

### 8.1. Cấu hình chung và cấu hình riêng

Một số thuộc tính Spring Boot áp dụng chung cho server, ví dụ:

~~~properties
server.port=9090
server.servlet.context-path=/api
server.compression.enabled=true
~~~

Tuy nhiên, nhiều property cấu hình chi tiết **gắn với từng server**. Ví dụ một số setting tiền tố `server.tomcat.*` chỉ dành cho Tomcat, không mặc nhiên điều khiển Jetty hay Undertow. Khi đổi server, rà lại những giá trị liên quan:

- số luồng xử lý và cấu hình thread pool;
- thời gian chờ kết nối, keep-alive và idle timeout;
- giới hạn header/request line và kích thước request;
- TLS certificates, HTTPS và HTTP/2;
- compression, connection limits;
- access log, error page và request encoding;
- session, servlet filters và multipart upload;
- graceful shutdown, health checks và readiness.

Cần tra danh sách property tương ứng **đúng phiên bản Spring Boot đang sử dụng**. Không tự sao chép `server.tomcat.threads.max` sang một tên `server.jetty.threads.max` theo suy đoán: tên property, kiểu giá trị và cơ chế liên quan có thể khác.

### 8.2. Điều kiện môi trường triển khai

Nếu ứng dụng chạy sau proxy/load balancer, cổng container nội bộ và cổng public có thể khác nhau. Đổi embedded server không tự đổi Docker `EXPOSE`, Kubernetes Service/Ingress, firewall hoặc reverse proxy. Hãy xác nhận:

1. process mở đúng cổng và bind address;
2. container image/Deployment công bố đúng cổng;
3. Service và ingress route đến đúng target;
4. các endpoint readiness/health hoạt động;
5. telemetry, access log và tracing vẫn phản ánh request cần theo dõi.

Trong môi trường production, khởi động thành công là điều kiện cần; phải kiểm thử traffic thật và khả năng rollback khi cập nhật dependency.

## 9. Spring MVC khác Spring WebFlux

**Không áp dụng nguyên xi dependency của Spring MVC cho ứng dụng reactive.**

- `spring-boot-starter-web` hướng tới **Spring MVC**, mặc định dùng embedded **Tomcat**.
- `spring-boot-starter-webflux` hướng tới **Spring WebFlux**, mặc định dùng **Reactor Netty** qua `spring-boot-starter-reactor-netty`.

Với WebFlux, quy trình thay server cũng là loại server starter mặc định trên nhánh WebFlux và chọn một **web server tương thích với reactive stack**, nhưng dependency và cách custom server có thể khác. Đừng chỉ exclude `spring-boot-starter-tomcat` trong project WebFlux thuần: Tomcat không phải default server của `spring-boot-starter-webflux`.

Ví dụ xác định starter mặc định trong WebFlux:

~~~text
spring-boot-starter-webflux
    |
    +-- spring-boot-starter-reactor-netty
~~~

Nếu đồng thời thêm cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thường chọn chế độ **Servlet MVC** theo quy tắc auto-detection mặc định. Đừng thêm cả hai chỉ nhằm thay máy chủ. Quyết định dùng MVC hay WebFlux phải dựa vào mô hình xử lý request, không phải sở thích về tên server.

## 10. Exclusion transitive, dependency management và tương thích phiên bản

### 10.1. Vì sao không tự thêm mọi JAR của server?

Starter của Spring Boot đã gom các artifact server và integration cần thiết. Khi viết:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jetty</artifactId>
</dependency>
~~~

và dùng Spring Boot BOM/parent, Maven tự giải quyết các artifact Jetty phù hợp. Nếu tự thêm nhiều module Jetty với version tùy ý, project dễ gặp mismatch API, classpath conflict hoặc lỗi khởi động.

Tương tự, Gradle project nên dùng Spring Boot dependency management/BOM để thống nhất version. Tránh gắn một phiên bản Jetty/Undertow tự chọn trừ khi có lý do tương thích được kiểm thử rõ ràng.

### 10.2. Khi project có nhiều module

Giả sử module API phụ thuộc module khác có kéo Tomcat vào, việc exclude Tomcat từ nhánh `spring-boot-starter-web` **chưa chắc** loại được toàn bộ container cũ. Hãy kiểm tra `runtimeClasspath` thực tế của **module đóng gói executable JAR**.

Lỗi phổ biến là chỉ xem file `pom.xml` hoặc `build.gradle` của module API mà quên dependency mang vào từ module infrastructure. Lệnh `dependency:tree` hoặc `dependencyInsight` giúp tìm đường đi thực tế.

### 10.3. Đóng gói và vận hành

- **Executable JAR:** chứa các dependency embedded server, chạy trực tiếp bằng `java -jar`. Đây là trường hợp chính của bài.
- **WAR triển khai vào external container:** vòng đời server do container bên ngoài quản lý. Thay starter embedded không có cùng ý nghĩa như đổi server vận hành. Không tự chuyển `packaging` từ JAR sang WAR chỉ để đổi Tomcat → Jetty.
- **Spring Boot version:** ví dụ được kiểm tra theo cấu trúc dependency của Boot 3.5.0. Với Boot 4.x hoặc phiên bản khác, đối chiếu starter artifact và Servlet API được hỗ trợ trước khi chép cấu hình; không trộn tùy tiện các dòng phiên bản.

## 11. Các lỗi thường gặp và cách xử lý

### 11.1. Đã thêm Jetty nhưng log vẫn nhắc Tomcat

**Nguyên nhân có thể:** chưa exclude `spring-boot-starter-tomcat` hoặc còn một nhánh transitive khác kéo Tomcat vào. 

**Cách kiểm tra:** `mvn dependency:tree` hoặc `./gradlew dependencies --configuration runtimeClasspath`. Tìm chính xác nhánh dependency; sửa exclusion tương ứng, build lại từ đầu và xem log startup mới.

### 11.2. Không tìm thấy `ServletWebServerFactory` / web server không khởi động

Nếu đã loại default Tomcat nhưng **quên thêm starter thay thế**, Spring Boot có thể thiếu embedded server factory. Thêm **một** starter Jetty/Undertow tương thích và xác nhận lại classpath.

Nếu project có custom `ServletWebServerFactory` bean, nó có thể ảnh hưởng autoconfiguration. Kiểm tra các cấu hình tự tạo này trước khi kết luận rằng chỉ cần đổi dependency là đủ.

### 11.3. `NoSuchMethodError`, `NoClassDefFoundError`, xung đột Servlet API

Thường liên quan dependency phiên bản không nhất quán hoặc jar cũ được thêm thủ công. Dùng dependency management đồng nhất, loại module server và servlet API không tương thích, xem stack trace ở điểm lỗi và cây phụ thuộc thực tế. Không cố chữa bằng cách thêm ngẫu nhiên một JAR khác.

### 11.4. App khởi động nhưng endpoint trả 404

Kiểm tra `server.servlet.context-path=/api`: endpoint `@GetMapping("/hello")` thực tế ở `/api/hello`, không còn trực tiếp ở `/hello`. Cũng kiểm tra `@RequestMapping` ở class và reverse proxy đang thêm hoặc bỏ prefix.

### 11.5. HTTP 400/413 khác trước hoặc upload thất bại

Có thể server mới áp dụng giới hạn request khác hoặc property Tomcat cũ không còn tác dụng. Đối chiếu các giới hạn của Jetty/Undertow, cấu hình multipart chung, proxy và kích thước upload; kiểm thử request thực, thay vì chỉ kiểm tra controller.

### 11.6. Test MVC pass nhưng triển khai mới lỗi

`@WebMvcTest`/MockMvc kiểm tra tầng MVC mà không mở embedded HTTP socket. Cần thêm ít nhất một bài `@SpringBootTest(RANDOM_PORT)` truy cập HTTP thật, rồi kiểm tra các tính năng cụ thể như TLS, WebSocket, cookies và graceful shutdown nếu ứng dụng dùng.

### 11.7. Ứng dụng có nhiều web server factory

Khi có nhiều embedded server starter hoặc bean factory thủ công, Spring Boot có thể chọn implementation không mong muốn hoặc phát sinh lỗi khởi tạo. Hãy để chỉ một starter mong muốn hoặc tự cấu hình factory rõ ràng; không phụ thuộc vào thứ tự classpath ngẫu nhiên.

## 12. Checklist chuyển đổi an toàn

1. Xác định **stack**: Spring MVC hay WebFlux; với MVC, ghi nhận Tomcat là embedded server mặc định.
2. Chọn **một** embedded servlet container đích: Jetty hoặc Undertow; kiểm tra tương thích với phiên bản Spring Boot/Java đang dùng.
3. Exclude `spring-boot-starter-tomcat` khỏi `spring-boot-starter-web`; thêm `spring-boot-starter-jetty` hoặc `spring-boot-starter-undertow`.
4. Giữ dependency management và tránh tự ghim version server không phù hợp.
5. Chạy `mvn dependency:tree` hoặc kiểm tra Gradle `runtimeClasspath` để loại mọi đường kéo server cũ.
6. Build và khởi động executable JAR; đọc startup log để xác nhận container thực.
7. Gọi endpoint HTTP bằng curl và chạy integration test trên `RANDOM_PORT`.
8. Rà lại cấu hình `server.tomcat.*` cũ, các giới hạn HTTP, TLS, session, upload và thread handling theo server mới.
9. Kiểm tra image/container/service/proxy, health endpoint và logging.
10. Đưa vào môi trường kiểm thử, đo hiệu năng theo traffic thực tế rồi mới triển khai rộng.

## Tài liệu tham khảo

- Spring Boot Reference, [How to Change the HTTP Port and Configure the Embedded Web Server](https://docs.spring.io/spring-boot/how-to/webserver.html).
- Spring Boot Reference, [Build Systems and Starters](https://docs.spring.io/spring-boot/reference/using/build-systems.html).
- Maven Dependency Plugin, [dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html).
- Gradle User Manual, [DependencyInsight](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html).

**Ghi nhớ:** Với ứng dụng Spring MVC trên Spring Boot 3.x, thay embedded server là một thay đổi **dependency graph**: bỏ Tomcat mặc định, thêm Jetty hoặc Undertow, xác nhận bằng dependency tree và chạy thử server thật. Lớp Spring MVC không cần viết lại, nhưng cấu hình và hành vi của container cần được kiểm thử.

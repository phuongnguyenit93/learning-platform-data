# Xác định ranh giới của WAR đối với ứng dụng reactive dùng WebFlux

## 1. Kết luận trước khi thiết kế hệ thống

**Với Spring Boot, không triển khai ứng dụng WebFlux theo mô hình WAR truyền thống vào Servlet container bên ngoài.** Đây là giới hạn được Spring Boot nêu rõ trong tài liệu Traditional Deployment và Reactive Web Applications, bao gồm nhánh Spring Boot 3.3 dùng ở ví dụ dưới đây.

Điều này **không có nghĩa WebFlux chỉ chạy được trên Netty hoặc không thể chạy trên Tomcat**. Cần phân biệt ba tình huống:

1. **Spring Boot WebFlux + executable JAR + embedded Reactor Netty**: mô hình mặc định, được hỗ trợ.
2. **Spring Boot WebFlux + executable JAR + embedded Tomcat/Jetty**: có thể được hỗ trợ khi thay embedded server theo cấu hình chính thức. WebFlux dùng adapter cho Servlet non-blocking I/O; đây vẫn là ứng dụng **tự khởi động server**.
3. **Spring Boot WebFlux + WAR triển khai vào Tomcat/Jetty bên ngoài**: **không được Spring Boot hỗ trợ** như luồng traditional deployment của Spring MVC. Chỉ thêm plugin war, đặt packaging=war hay kế thừa SpringBootServletInitializer không biến nó thành một lựa chọn triển khai WebFlux được hỗ trợ.

Ngoài ra, **Spring Framework WebFlux thuần** có cơ chế cấp thấp để đóng gói vào WAR cho một Servlet container tương thích thông qua **AbstractReactiveWebInitializer** và **ServletHttpHandlerAdapter**. Đây là khả năng ở tầng Spring Framework, **không phải** bảo đảm rằng **Spring Boot WebFlux auto-configuration + traditional WAR** sẽ hoạt động. Không lấy ví dụ Spring Framework thủ công để phủ định giới hạn triển khai của Spring Boot.

**Quy tắc quyết định:** Nếu yêu cầu bắt buộc là **deploy WAR vào application server doanh nghiệp**, chọn một ứng dụng **Servlet/Spring MVC phù hợp** hoặc đánh giá một kiến trúc không dùng Boot WebFlux WAR. Nếu yêu cầu quan trọng là **WebFlux reactive server stack**, ưu tiên **executable JAR** hoặc container image chạy JAR đó.

Bài thực hành sử dụng **Spring Boot 3.3.5**, **Java 17**, Maven và **Gradle 8.5**. Đây là bộ phiên bản minh họa, không phải khẳng định mới nhất. Cần kiểm tra release notes nếu nâng Spring Boot, Spring Framework hoặc servlet container.

## 2. WAR là gì và dựa vào cơ chế khởi động nào?

### 2.1. WAR truyền thống

**WAR (Web Application Archive)** là archive web được đưa tới một **Servlet container đã chạy sẵn**, chẳng hạn Tomcat ở môi trường doanh nghiệp. Container giải nén hoặc đọc WAR, tạo web application context và gọi cơ chế khởi tạo ứng dụng theo Servlet API. Với ứng dụng **Spring Boot MVC**, có thể dùng **SpringBootServletInitializer** để khởi tạo Spring application context trong môi trường này.

Bố cục điển hình của WAR:

~~~text
mvc-war-demo.war
├── META-INF/
└── WEB-INF/
    ├── classes/                 # application classes và resources
    ├── lib/                     # thư viện web app cần
    └── lib-provided/            # với executable Boot WAR, server embedded được đánh dấu provided
~~~

**WEB-INF/lib-provided** là bố cục riêng được Spring Boot build plugins sử dụng trong một số executable WAR để những thư viện container provided không can thiệp khi triển khai ngoài, nhưng vẫn có sẵn khi chạy **java -jar**. WAR truyền thống không bắt buộc có lib-provided; đừng dựa vào duy nhất tên thư mục để đánh giá web stack.

### 2.2. Executable JAR Spring Boot WebFlux

Spring Boot executable JAR được JVM chạy trực tiếp. Nó mang code ứng dụng và dependency runtime, đồng thời khởi động embedded HTTP server:

~~~text
reactive-war-boundary-1.0.0.jar
├── META-INF/
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   └── com/example/reactive/ReactiveJarApplication.class
    └── lib/
        ├── spring-boot-*.jar
        ├── reactor-netty-*.jar
        └── ...
~~~

Ở mô hình này, **java -jar** khởi động Spring Boot, Boot tạo reactive application context và embedded Reactor Netty (mặc định). Không cần một Tomcat bên ngoài để triển khai file lên thư mục webapps.

### 2.3. Cùng là .war nhưng không phải cùng hợp đồng

Một build tool **có thể tạo ra một file có đuôi .war**, nhưng điều đó chỉ chứng minh có archive. Nó **không chứng minh** rằng container bên ngoài sẽ đăng ký handler đúng, khởi động application context hay xử lý WebFlux endpoint thành công. Tên file, layout archive và khả năng triển khai được hỗ trợ là ba điều riêng biệt.

Ngược lại, một **Spring Boot MVC executable WAR** với build configuration chính xác có thể **vừa triển khai ra servlet container vừa chạy bằng java -jar**. Tính năng hai chế độ này thuộc luồng Servlet/Spring MVC, **không** tự áp dụng cho WebFlux.

## 3. WebFlux là reactive HTTP programming model, không phải định dạng WAR

Spring WebFlux dựa trên mô hình **non-blocking**, các kiểu như **Mono** và **Flux**, và một tầng xử lý HTTP không phụ thuộc tuyệt đối vào Servlet API.

Các thành phần liên quan:

- **DispatcherHandler**: cơ chế request dispatch của Spring WebFlux.
- **HttpHandler**: abstraction cấp thấp đại diện cho HTTP request/response bất đồng bộ.
- **Reactor Netty**: một server runtime thường được dùng mặc định cùng spring-boot-starter-webflux.
- **ServletHttpHandlerAdapter**: adapter khi chạy WebFlux qua Servlet non-blocking I/O.
- **DispatcherServlet**: cơ chế request dispatch của Spring MVC, khác DispatcherHandler.

Không nên đánh đồng **WebFlux** với **WebClient**. WebClient là **reactive HTTP client**; một ứng dụng Spring MVC vẫn có thể dùng WebClient để gọi dịch vụ khác và vẫn là Servlet/MVC application.

Tương tự, Spring MVC có thể hỗ trợ một số reactive return types như Mono/Flux. Việc controller trả về **Mono<String>** **không phải bằng chứng đủ** rằng toàn ứng dụng được vận hành bởi WebFlux DispatcherHandler. Phải xét các starters, auto-configuration và web application type.

### 3.1. Bảng lựa chọn

| Ứng dụng | Server/stack | Artifact/triển khai | Trạng thái |
| --- | --- | --- | --- |
| Spring Boot WebFlux, spring-boot-starter-webflux | Embedded Reactor Netty | **Executable JAR** | **Được hỗ trợ; mặc định phù hợp** |
| Spring Boot WebFlux, thay Netty bằng embedded Tomcat/Jetty | WebFlux trên adapter Servlet non-blocking I/O | **Executable JAR** | **Có thể hỗ trợ** theo cấu hình embedded server |
| Spring Boot WebFlux | External Tomcat/Jetty đã chạy sẵn | **Traditional WAR** | **Không được Spring Boot hỗ trợ** |
| Spring Boot MVC, spring-boot-starter-web | Servlet / DispatcherServlet | **WAR triển khai ngoài** | **Được hỗ trợ** khi cấu hình initializer và dependency scope đúng |
| Spring Boot MVC sử dụng WebClient | Servlet/MVC + reactive client | **WAR triển khai ngoài** | **Được hỗ trợ** theo quy tắc MVC WAR |
| Spring Framework WebFlux không dùng Boot theo mô hình traditional Boot | WebFlux + ServletHttpHandlerAdapter tự cấu hình | **WAR thủ công** | **Khả năng của Spring Framework**; cần tự thiết kế/kiểm thử, không phải Boot WebFlux WAR |

Đừng dùng cấu hình WebFlux chạy trên embedded Tomcat làm bằng chứng rằng WebFlux của Spring Boot sẽ được external Tomcat bootstrap từ WAR. **Embedded server integration** và **Servlet container deployment lifecycle** là hai cơ chế khác nhau.

## 4. Vì sao Spring Boot không hỗ trợ WebFlux traditional WAR?

### 4.1. Hai mô hình khởi động khác nhau

Với ứng dụng WebFlux mặc định:

~~~text
java -jar app.jar
    |
    v
SpringApplication.run(...)
    |
    v
ReactiveWebServerApplicationContext
    |
    v
ReactiveWebServerFactory
    |
    v
Reactor Netty (hoặc embedded reactive server adapter)
    |
    v
DispatcherHandler / WebFlux routes
~~~

Trong WAR Servlet/Spring MVC:

~~~text
External Tomcat/Jetty đang chạy
    |
    v
Servlet container tìm Servlet initializer
    |
    v
SpringBootServletInitializer / Spring WebApplicationInitializer
    |
    v
Servlet web application context
    |
    v
DispatcherServlet và các MVC mappings
~~~

**SpringBootServletInitializer** nằm trong cơ chế bootstrap của **Servlet web application**. WebFlux application context và server factory có vòng đời khác. Việc thêm một class kế thừa SpringBootServletInitializer không khiến Boot WebFlux tự lắp ghép đúng reactive HttpHandler adapter vào external container theo luồng traditional deployment được Boot hỗ trợ.

### 4.2. Reactor Netty không phải một Servlet container

Mặc định **spring-boot-starter-webflux** kéo theo **spring-boot-starter-reactor-netty**. Reactor Netty là HTTP server theo Netty API, không phải Servlet container. Nó không nhận file WAR và xử lý **WEB-INF/web.xml** hay Servlet initialization như external Tomcat.

**Không thể sửa bằng cách đổi extension từ .jar sang .war.** Bản chất runtime và bootstrapping không thay đổi bởi tên file.

### 4.3. Servlet adapter không xóa giới hạn của Boot

Spring Framework có adapter cho WebFlux chạy với Servlet non-blocking I/O. Trong Spring Framework có **AbstractReactiveWebInitializer** cho deployment thủ công vào container phù hợp. Điều đó **không tạo ra một hướng dẫn Spring Boot truyền thống được hỗ trợ**; muốn đi đường này phải cân nhắc tự tạo bootstrap, cấu hình handler/filter/security, dependency scopes và sự tương thích của container, thay vì dùng Spring Boot WebFlux WAR theo giả định mặc định.

**Phạm vi bài:** Chúng ta giải thích ranh giới và cách chọn kiến trúc an toàn. Không cung cấp công thức “đổi vài dòng build.gradle thành Boot WebFlux WAR” vì đó là hướng chưa được Spring Boot hỗ trợ.

## 5. Cách chọn từ yêu cầu triển khai

Bắt đầu từ **ràng buộc bắt buộc của môi trường**, không bắt đầu từ đuôi archive:

**Tình huống A — Hệ thống cần WebFlux non-blocking HTTP server:**

- Chọn **spring-boot-starter-webflux**.
- Đóng gói **executable JAR** bằng Spring Boot Maven/Gradle Plugin.
- Chạy qua **java -jar**, systemd, container image, Kubernetes hoặc nền tảng phù hợp.
- Dùng embedded Reactor Netty mặc định, hoặc đánh giá embedded Tomcat/Jetty khi có yêu cầu riêng.
- Kiểm thử cổng HTTP, backpressure/chỗ blocking, throughput và resource usage theo nhu cầu thực tế.

**Tình huống B — Tổ chức chỉ nhận WAR vào Tomcat/Jetty có sẵn:**

- Chọn **Spring MVC / Servlet stack**, trừ khi có một kiến trúc thay thế được phê duyệt.
- Cấu hình **packaging war** (Maven) hoặc plugin **war** (Gradle).
- Kế thừa **SpringBootServletInitializer** và khai báo **provided** cho embedded servlet container.
- Kiểm tra phiên bản Servlet/Jakarta tương thích với Spring Boot và server bên ngoài.
- Có thể dùng **WebClient** để gọi API theo kiểu reactive mà không cần chuyển toàn server sang WebFlux.

**Tình huống C — Muốn giữ WebFlux nhưng bên hạ tầng chỉ cho tải WAR:**

- Nêu rõ đây là **xung đột kiến trúc**, không chỉ là cấu hình build thiếu một plugin.
- Đề xuất cho phép executable JAR/container image, hoặc thay đổi stack server sang MVC.
- Nếu cân nhắc tự dùng **Spring Framework WebFlux + AbstractReactiveWebInitializer**, phải coi đó là dự án tích hợp nâng cao, có owner, test/maintenance và phạm vi hỗ trợ riêng. Không gọi đó là đường triển khai WAR tiêu chuẩn của Spring Boot.

**Điểm mấu chốt:** WAR là **một hình thức phân phối và bootstrap**, không phải một “tính năng của endpoint reactive”. Quyết định WAR/JAR cần được kiểm tra từ kiến trúc runtime ngay từ đầu.

## 6. Bài thực hành: một Spring Boot WebFlux executable JAR chạy thực tế

Bài thực hành cho thấy lựa chọn đúng cho WebFlux: **JAR tự chạy**. Cùng một mã nguồn Java 17 có thể build bằng Maven **hoặc** Gradle.

### 6.1. Cây thư mục

~~~text
reactive-war-boundary/
├── pom.xml                     # chỉ dùng nếu chọn Maven
├── settings.gradle             # chỉ dùng nếu chọn Gradle
├── build.gradle                # chỉ dùng nếu chọn Gradle
└── src/
    ├── main/
    │   ├── java/com/example/reactive/
    │   │   ├── ReactiveJarApplication.java
    │   │   └── GreetingController.java
    │   └── resources/static/index.html
    └── test/java/com/example/reactive/
        └── ReactiveJarApplicationTest.java
~~~

Đây là cấu trúc mô tả **hai phương án build thay thế**. Một repository thực tế chọn POM hoặc Gradle files, không yêu cầu đồng thời cả hai.

Đối với WebFlux, đặt static content ở **src/main/resources/static** (hoặc các resource locations do Boot hỗ trợ), **không dùng src/main/webapp** như cách tổ chức web application cũ dành cho WAR. Điều này cũng tránh hiểu lầm rằng WebFlux cần một servlet webapp root.

### 6.2. Main class hoàn chỉnh

File **src/main/java/com/example/reactive/ReactiveJarApplication.java**:

~~~java
package com.example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveJarApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveJarApplication.class, args);
    }
}
~~~

Class này được Boot dùng làm application entry point. Chúng ta **không** kế thừa SpringBootServletInitializer, vì mục tiêu là Spring Boot WebFlux executable JAR chứ không phải external Servlet WAR.

### 6.3. WebFlux controller trả Mono<String>

File **src/main/java/com/example/reactive/GreetingController.java**:

~~~java
package com.example.reactive;

import reactor.core.publisher.Mono;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping(value = "/hello", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> hello() {
        return Mono.just("WEBFLUX_JAR_OK");
    }
}
~~~

Đây là file Java hoàn chỉnh. **Mono<String>** là reactive publisher chứa tối đa một giá trị. Trong một ứng dụng được cấu hình **WebFlux**, request này được WebFlux xử lý theo reactive HTTP stack.

**Đừng suy ra chỉ vì Mono có mặt mà Spring MVC biến mất.** Chúng ta cố ý khai báo **spring-boot-starter-webflux** và **không khai báo spring-boot-starter-web** để application type được chọn là reactive. Đây là điều quan trọng khi giải thích ranh giới WAR.

Khi server chạy ở cổng mặc định 8080 và không có proxy/override, gọi:

~~~bash
curl --silent http://localhost:8080/hello
~~~

**HTTP response body chính xác:**

~~~text
WEBFLUX_JAR_OK
~~~

Chuỗi trả về không có JSON object, vì controller tạo **text/plain**. Curl có thể không tự thêm newline, nên shell prompt có thể xuất hiện ngay sau body; không xem đó là lỗi. Log Spring Boot/Gradle/Maven không phải một phần response body.

### 6.4. Một static resource WebFlux

File **src/main/resources/static/index.html**:

~~~html
<!doctype html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <title>WebFlux JAR</title>
</head>
<body>
    <h1>Reactive application in executable JAR</h1>
</body>
</html>
~~~

Với cấu hình resource mặc định của Spring Boot WebFlux, ứng dụng có thể phục vụ file welcome page này từ **GET /**. Đây là resource nằm trên classpath bên trong executable JAR, không phải **src/main/webapp** của một WAR triển khai ngoài.

### 6.5. JUnit integration test trên cổng ngẫu nhiên

File **src/test/java/com/example/reactive/ReactiveJarApplicationTest.java**:

~~~java
package com.example.reactive;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ReactiveJarApplicationTest {

    @Autowired
    private WebTestClient client;

    @Test
    void respondsOverHttp() {
        client.get().uri("/hello")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("WEBFLUX_JAR_OK");
    }
}
~~~

Test dùng **RANDOM_PORT**, tránh tranh chấp cổng 8080 trong CI. Nó kiểm tra endpoint qua HTTP khi Spring Boot khởi động embedded server trong test context.

**WebTestClient** là công cụ kiểm thử, không biến một ứng dụng thành WebFlux nếu production dependencies/auto-configuration đang là MVC. Bài sử dụng WebFlux starter, nên môi trường này kiểm tra đúng WebFlux app. Nếu test không khởi động được, kiểm tra classpath, dependency test và report trước khi kết luận lỗi ở WAR/JAR.

## 7. Maven: POM đầy đủ cho WebFlux executable JAR

Tạo file **pom.xml** (chọn Maven thì dùng file này với mã Java ở mục 6):

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactive-war-boundary</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

**Phần cần quan sát:**

- **packaging=jar**: bản phân phối là executable Spring Boot JAR, không phải WAR.
- **spring-boot-starter-webflux**: đưa WebFlux và Reactor Netty embedded server mặc định vào runtime.
- **spring-boot-starter-test**, scope test: JUnit/Boot test support không được coi là runtime dependency của ứng dụng.
- **spring-boot-maven-plugin** với Spring Boot parent: được dùng để **repackage** JAR thành executable artifact.
- Không có **spring-boot-starter-web**; tránh để Spring MVC được ưu tiên nếu vô tình có cả hai frameworks trên classpath.

### 7.1. Build và chạy Maven

Khi repository có Maven Wrapper:

~~~bash
./mvnw clean verify
java -jar target/reactive-war-boundary-1.0.0.jar
~~~

Nếu chưa có wrapper, dùng **mvn clean verify** với Maven tương thích đã cài sẵn. Trên Windows sử dụng **mvnw.cmd**.

Lệnh **verify** biên dịch, chạy kiểm thử và đi qua package/repackage trong lifecycle chuẩn. Với POM này, artifact dự kiến:

~~~text
target/reactive-war-boundary-1.0.0.jar
~~~

Sau khi ứng dụng start thành công, mở một terminal khác:

~~~bash
curl --silent http://localhost:8080/hello
~~~

Response body dự kiến:

~~~text
WEBFLUX_JAR_OK
~~~

**Điều kiện:** Java runtime phù hợp, port 8080 rảnh, dependency được tải thành công, test pass. Không giả định môi trường CI đã cho phép lắng nghe cổng 8080 ở mọi job; khi chỉ chạy test, ví dụ đã dùng RANDOM_PORT.

### 7.2. Kiểm tra artifact theo cấu trúc, không theo tên file

~~~bash
jar tf target/reactive-war-boundary-1.0.0.jar
~~~

Trong danh sách entry, dự kiến có:

~~~text
BOOT-INF/classes/com/example/reactive/ReactiveJarApplication.class
BOOT-INF/classes/com/example/reactive/GreetingController.class
BOOT-INF/classes/static/index.html
BOOT-INF/lib/...
~~~

Có thể thấy Boot launcher trong package của Spring Boot loader. **Sự tồn tại BOOT-INF và chạy được java -jar** xác nhận đây là Boot executable JAR; không phải WAR cho Tomcat bên ngoài. Danh sách BOOT-INF/lib có nhiều tệp hơn, tùy version đã resolve.

## 8. Gradle: build.gradle đầy đủ cho WebFlux executable JAR

Nếu chọn Gradle, file **settings.gradle**:

~~~groovy
rootProject.name = 'reactive-war-boundary'
~~~

File **build.gradle** (Groovy DSL):

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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là cấu hình hoàn chỉnh cho **WebFlux executable JAR** cùng source code mục 6. Không áp dụng **id 'war'**, vì chúng ta không chọn traditional WAR deployment. Spring Boot Gradle Plugin tạo **bootJar** khi Java plugin có mặt; task bootJar dùng main source set và runtime dependencies để đóng executable archive.

### 8.1. Gradle commands

Dự án cần Gradle Wrapper tương thích (ví dụ 8.5) được tạo/cung cấp sẵn. Chạy tại root:

~~~bash
./gradlew clean test bootJar
java -jar build/libs/reactive-war-boundary-1.0.0.jar
~~~

Trên Windows sử dụng **gradlew.bat**. Khi server đã chạy, ở terminal thứ hai:

~~~bash
curl --silent http://localhost:8080/hello
~~~

Response body:

~~~text
WEBFLUX_JAR_OK
~~~

Từ Java source và starter dependencies giống nhau, cách chạy Maven/Gradle cho cùng một kết quả nghiệp vụ. Sự khác biệt là thư mục artifact **target/** và **build/libs/**.

### 8.2. Xem dependency graph Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Dự kiến nhìn thấy **spring-boot-starter-webflux** và **spring-boot-starter-reactor-netty**, không phải một Spring MVC server starter được khai báo trong project mẫu. Nếu thấy spring-boot-starter-web thông qua một dependency khác, hãy tìm đường dẫn đưa dependency đó vào và xác nhận web application type.

Không dùng output dependency graph một mình để chứng minh “WAR supported”: graph giải thích thư viện, còn khả năng external deployment là **hợp đồng lifecycle** của framework và container.

## 9. Điều gì xảy ra khi cố chuyển WebFlux build sang WAR?

Một đề xuất hay gặp:

~~~xml
<packaging>war</packaging>
~~~

hoặc Gradle:

~~~groovy
plugins {
    id 'war'
}
~~~

Đây là các **fragment minh họa**; chúng không tự đủ để tạo một hệ thống. Chúng chỉ đổi loại artifact hoặc thêm nhiệm vụ WAR của build tool, **không** tạo Servlet initializer phù hợp cho Boot WebFlux, không tự thay Reactor Netty thành external Tomcat và không thay reactive application context thành Servlet/MVC context.

**Phân biệt kết quả:**

1. **Build thành công**: chỉ có nghĩa compiler, task đóng gói và những kiểm tra chạy lúc build đã hoàn tất.
2. **WAR có cấu trúc hợp lệ**: chỉ có nghĩa ZIP/JAR layout đáp ứng tiêu chí archive cơ bản.
3. **Deploy lên external container thành công**: còn cần bootstrap/lifecycle đúng, Servlet container phù hợp, dependencies phù hợp, application context hoạt động và endpoint thực sự phục vụ request.
4. **Được Spring Boot hỗ trợ**: còn là câu chuyện hợp đồng của framework, được nêu trong tài liệu. Với **Boot WebFlux traditional WAR**, tài liệu xác nhận **không hỗ trợ** ngay cả khi có thể tự tạo file WAR.

**Không viết hướng dẫn “cứ thêm SpringBootServletInitializer là chạy WebFlux WAR”**. SpringBootServletInitializer phục vụ đường khởi động **Servlet web applications**. Đối với WebFlux, nếu phải theo WAR thủ công thì đang bước sang một phương án **Spring Framework adapter tùy biến**, không phải Boot WebFlux WAR chuẩn.

### 9.1. Đừng chuyển providedRuntime theo công thức MVC sang WebFlux

Trong một hướng dẫn Spring MVC WAR, người học thường thấy:

~~~text
Maven: spring-boot-starter-tomcat scope provided
Gradle: providedRuntime spring-boot-starter-tomcat
~~~

Những dòng này có ý nghĩa với **Servlet container external WAR** của MVC. Đưa chúng vào WebFlux POM/build.gradle mà không thiết kế lại web runtime **không khắc phục** giới hạn Boot WebFlux WAR. Netty và Tomcat là những HTTP server có API khác nhau; một dependency scope không tự đổi mô hình dispatch, Servlet bootstrap hay lifecycle.

## 10. Nếu bắt buộc WAR: đối chiếu với Spring Boot MVC đúng cách

Để thấy đâu là ranh giới, đây là một phương án **khác WebFlux**: ứng dụng Spring MVC deploy được thành WAR theo Spring Boot traditional deployment. Nó dùng **spring-boot-starter-web**, Servlet API và **SpringBootServletInitializer**.

### 10.1. Java main class cho MVC WAR

File **src/main/java/com/example/mvc/MvcWarApplication.java**:

~~~java
package com.example.mvc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MvcWarApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(MvcWarApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(MvcWarApplication.class, args);
    }

    @RestController
    static class HelloController {
        @GetMapping("/hello")
        String hello() {
            return "MVC_WAR_OK";
        }
    }
}
~~~

Đây là file Java hoàn chỉnh cho **một ứng dụng MVC WAR tách biệt**. Controller dùng **DispatcherServlet**, không phải WebFlux DispatcherHandler. **configure()** cho phép Servlet container khởi tạo Boot app từ external WAR; **main()** còn hỗ trợ đường chạy executable WAR khi cấu hình Boot packaging đúng.

**Cấu trúc project này độc lập với reactive-war-boundary** ở trên; không đặt cả hai main classes vào cùng project rồi nghĩ compiler tự chọn đúng architecture.

### 10.2. Maven POM hoàn chỉnh cho MVC WAR

File **pom.xml** của project **mvc-war-demo**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mvc-war-demo</artifactId>
    <version>1.0.0</version>
    <packaging>war</packaging>

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
            <artifactId>spring-boot-starter-tomcat</artifactId>
            <scope>provided</scope>
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

Với **Spring Boot starter parent**, Maven hỗ trợ cấu hình Maven WAR Plugin phù hợp và goal repackage của Spring Boot Plugin. Bản WAR này là **Servlet/MVC WAR**, không phải WebFlux WAR.

- **packaging=war**: đặt loại artifact.
- **spring-boot-starter-web**: dùng Spring MVC và embedded Tomcat theo mặc định.
- **spring-boot-starter-tomcat** với **scope provided**: cho phép external servlet container cung cấp server tương ứng thay vì nhét một server embedded vào classpath deployment ngoài.
- **SpringBootServletInitializer**: khởi tạo app từ servlet lifecycle của external container.
- **spring-boot-maven-plugin**: có thể tạo executable WAR phù hợp để chạy thêm bằng **java -jar** khi dùng đúng cấu hình.

### 10.3. Gradle build.gradle tương đương cho MVC WAR

File **settings.gradle**:

~~~groovy
rootProject.name = 'mvc-war-demo'
~~~

File **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'war'
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
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
~~~

Gradle plugin **war** cung cấp configuration **providedRuntime** và task WAR; Spring Boot plugin hỗ trợ **bootWar** cho executable WAR khi kết hợp War plugin. **providedRuntime** phù hợp hơn **compileOnly** cho embedded servlet server trong mô hình Servlet WAR, vì compileOnly không tự có mặt trong test runtime classpath.

Đây là một mô hình **khác hoàn toàn** với WebFlux JAR ở mục 6–8, nên không thể lấy toàn bộ build.gradle của MVC WAR rồi chỉ thay starter-web thành starter-webflux và mặc định cho là hợp lệ.

### 10.4. Build và kiểm tra WAR MVC

Maven:

~~~bash
./mvnw clean package
~~~

Artifact dự kiến:

~~~text
target/mvc-war-demo-1.0.0.war
~~~

Gradle:

~~~bash
./gradlew clean bootWar
~~~

Artifact dự kiến:

~~~text
build/libs/mvc-war-demo-1.0.0.war
~~~

Có thể dùng JDK **jar tf** để xem cấu trúc:

~~~bash
jar tf target/mvc-war-demo-1.0.0.war
~~~

hoặc đường dẫn Gradle tương ứng. Trong WAR của Servlet app, các classes/resources thường ở **WEB-INF/classes/**, các libraries phù hợp ở **WEB-INF/lib/**; bản executable Boot WAR có thể có **WEB-INF/lib-provided/**.

**Khi chạy bằng external Tomcat:** phiên bản Tomcat/Servlet API phải tương thích Spring Boot 3.3, và URL có thể có **context path từ tên WAR hoặc cấu hình container**. Không mặc định GET /hello sẽ nằm ngay tại root: nếu WAR deploy theo tên **mvc-war-demo**, URL có thể là **/mvc-war-demo/hello** tùy container config.

**Khi chạy bằng java -jar:** nếu WAR được Boot repackaged đúng và môi trường Java phù hợp, có thể chạy bằng **java -jar target/mvc-war-demo-1.0.0.war**, hoặc đường dẫn Gradle tương ứng. Điều này **không** làm WebFlux traditional WAR trở thành hỗ trợ.

## 11. Spring MVC + WebClient: giải pháp trung gian đáng cân nhắc

Một nhu cầu phổ biến: doanh nghiệp bắt buộc deploy lên Tomcat ngoài, nhưng muốn gọi REST API khác một cách non-blocking hoặc dùng Reactor. Trong trường hợp đó, có thể giữ **web server MVC/Servlet** và dùng **WebClient** làm HTTP client.

Ví dụ fragment dependency Maven trong một dự án MVC WAR:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

**Đây không phải POM đầy đủ**. Spring Boot chọn **Spring MVC** khi cả Spring MVC và WebFlux cùng có trên classpath trong trường hợp thông thường, vì nhiều người dùng WebFlux starter chỉ để dùng WebClient. Không suy ra ứng dụng đang chạy WebFlux chỉ vì có WebFlux starter.

Với Gradle, một fragment tương ứng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

Cần thêm cấu hình WAR Servlet thích hợp như mục 10 nếu thực sự deploy vào external container. **Không được nhầm** việc thêm reactive client với việc chuyển toàn bộ server stack sang WebFlux. Spring MVC có mô hình request processing khác, ngay cả khi return types hoặc HTTP client dùng Reactor.

**Lưu ý về hiệu năng:** Dùng WebClient không tự làm mọi xử lý end-to-end trở thành non-blocking. Nếu controller gọi **.block()** hoặc servlet thread phải chờ kết quả, cần đo thực tế concurrency và resource usage. Không chọn WebFlux/MVC chỉ vì một thư viện có từ khóa reactive.

## 12. Embedded Tomcat cho WebFlux không đồng nghĩa WAR Tomcat

Spring Boot WebFlux có thể sử dụng embedded servlet-based web server thay cho Reactor Netty khi cấu hình theo tài liệu Spring Boot. Ví dụ **Gradle fragment minh họa**:

~~~groovy
dependencies {
    implementation('org.springframework.boot:spring-boot-starter-webflux') {
        exclude group: 'org.springframework.boot',
                module: 'spring-boot-starter-reactor-netty'
    }
    implementation 'org.springframework.boot:spring-boot-starter-tomcat'
}
~~~

Đây là **fragment thay cho dòng WebFlux starter** trong build.gradle ở mục 8, **không phải** một build.gradle độc lập. Mục tiêu là chạy **Spring Boot WebFlux trên embedded Tomcat** với servlet non-blocking adapter. Trong cấu hình này vẫn **giữ plugin java và task bootJar**; không thêm war plugin, không tạo traditional deployable WAR và không đặt Tomcat vào providedRuntime.

Đối với Maven, ý tưởng tương đương là loại trừ **spring-boot-starter-reactor-netty** khỏi **spring-boot-starter-webflux**, rồi đưa **spring-boot-starter-tomcat** vào dependencies. Khi dùng hướng này, cần kiểm tra dependency graph, web application type và chạy integration test HTTP vì các phiên bản/tương tác server có thể khác.

**Nên chọn embedded Tomcat lúc nào?** Khi vận hành hoặc thư viện tích hợp có yêu cầu hợp lý liên quan Tomcat nhưng vẫn muốn ứng dụng Boot tự khởi động, dùng JAR. **Không chọn** với mục đích “lách” giới hạn WebFlux traditional WAR.

## 13. Gradle/Maven có thể tạo WAR nhưng cần hiểu điều gì?

Build tool làm đúng những task nó được yêu cầu. Nếu dùng Maven packaging war hoặc Gradle war plugin trong một dự án có WebFlux, nó có thể tạo ra **archive WAR hợp lệ về định dạng**. Điều đó không tự tạo:

- Servlet initializer phù hợp với Spring Boot WebFlux.
- Mapping HttpHandler sang Servlet do Boot hỗ trợ ở chế độ traditional deployment.
- Cơ chế khởi tạo Netty từ external WAR.
- Scope và lifecycle startup/shutdown của reactive server bên ngoài.
- Một môi trường deploy đã được nhà cung cấp framework kiểm thử/hỗ trợ.

**Build success khác deploy support.** CI có thể build thành công nhưng external Tomcat fail khi start hoặc không nhận route. Đây là rủi ro kiến trúc; không nên chờ đến staging mới phát hiện.

Đặc biệt, đặt:

~~~properties
spring.main.web-application-type=reactive
~~~

có thể buộc Boot chọn reactive application type trong bối cảnh classpath có cả MVC/WebFlux. Nhưng property này **không** tự biến WebFlux thành Spring Boot WAR được hỗ trợ. Cách kiểm tra phù hợp là đọc tài liệu support matrix và thử đúng **phương thức deployment** dự kiến.

## 14. Bảng kiểm chứng sau khi chọn kiến trúc

| Điều cần xác nhận | WebFlux JAR | MVC WAR |
| --- | --- | --- |
| Dependency HTTP server | WebFlux starter; embedded Netty hoặc adapter server phù hợp | Spring MVC starter; Servlet container |
| Packaging chính | JAR | WAR |
| Entry point | SpringApplication.main; Boot JAR launcher | SpringBootServletInitializer khi external WAR |
| External Servlet WAR được Spring Boot hỗ trợ? | **Không** | **Có** khi tương thích |
| Static resources | src/main/resources/static | src/main/resources/static và quy tắc Servlet webapp tùy cấu hình |
| Artifact check | BOOT-INF/classes, BOOT-INF/lib | WEB-INF/classes, WEB-INF/lib |
| Test HTTP | RANDOM_PORT WebTestClient | MockMvc/HTTP integration test/container deployment test |
| Run command | java -jar ...jar | Deploy .war ngoài hoặc chạy executable .war khi đã cấu hình |
| Hướng production | Service/container image chạy JAR | Enterprise Servlet server khi hợp đồng yêu cầu |

### Checklist cho WebFlux JAR

1. Chọn đúng **spring-boot-starter-webflux**, không vô tình kéo **spring-boot-starter-web** vào server classpath nếu mục tiêu là reactive application type.
2. Giữ Maven **packaging jar** hoặc Gradle **bootJar**; không thêm WAR chỉ vì cần môi trường triển khai.
3. Đặt static resources trong **src/main/resources/static**, không dùng src/main/webapp.
4. Chạy unit/integration tests với RANDOM_PORT.
5. Xây executable JAR và kiểm tra **BOOT-INF/classes** và **BOOT-INF/lib**.
6. Chạy **java -jar** và gọi endpoint thực tế.
7. Với Docker/Kubernetes, dùng image chứa đúng Boot JAR và cấu hình cổng, health check, graceful shutdown, resource limits phù hợp.
8. Trong kiến trúc cần WAR ngoài, ghi rõ đây là hạn chế support và có quyết định kiến trúc riêng.

### Checklist cho MVC WAR

1. Chọn **spring-boot-starter-web** và đảm bảo ứng dụng thực sự là Servlet/MVC web application.
2. Kế thừa **SpringBootServletInitializer**, cấu hình **configure()** đúng source class.
3. Chọn **packaging war** hoặc Gradle **war** + **bootWar**.
4. Đánh dấu embedded servlet container là **provided** theo tài liệu plugin.
5. Xác minh version Java/Jakarta Servlet/Tomcat phù hợp với Spring Boot được chọn.
6. Build WAR, kiểm tra WEB-INF và runtime dependencies.
7. Deploy thử vào external container đúng phiên bản và kiểm tra context path, endpoint.
8. Không dùng việc MVC có WebClient làm bằng chứng đã chuyển server sang WebFlux.

## 15. Các lỗi phổ biến và cách xử lý

**Lỗi 1 — Chỉ đổi packaging từ jar sang war trong WebFlux POM.** Cách này đổi loại archive chứ không đổi mô hình bootstrap. **Giải pháp:** quay về executable JAR cho Boot WebFlux, hoặc chuyển kiến trúc sang Servlet/MVC WAR có hỗ trợ.

**Lỗi 2 — Thêm SpringBootServletInitializer vào main class WebFlux.** Initializer là cơ chế truyền thống cho Servlet apps của Boot, không tự đăng ký đúng WebFlux adapter ngoài container. **Giải pháp:** không coi initializer là đường hỗ trợ Boot WebFlux WAR.

**Lỗi 3 — Thấy WebFlux chạy được trên embedded Tomcat và suy ra triển khai WAR ngoài được.** Embedded Tomcat do Boot điều khiển lifecycle khác external Tomcat bootstrap WAR. **Giải pháp:** tách hai phương thức triển khai trong tài liệu kiến trúc.

**Lỗi 4 — Nghĩ Reactor Netty có thể nhận WAR.** Netty không phải Servlet WAR container. **Giải pháp:** dùng Boot JAR làm artifact và khởi động Netty từ ứng dụng.

**Lỗi 5 — Nghĩ mọi REST controller trả Mono đều là WebFlux.** Spring MVC cũng có thể xử lý một số reactive return types. **Giải pháp:** xác định stack từ starters, context type và auto-configuration, không chỉ chữ ký phương thức.

**Lỗi 6 — Có cả spring-boot-starter-web và spring-boot-starter-webflux, nhưng test WebFlux không khởi động như kỳ vọng.** Với classpath gồm cả hai, Spring Boot thường ưu tiên Spring MVC. **Giải pháp:** bỏ starter dư hoặc chỉ định reactive type khi thực sự muốn thử WebFlux; lưu ý property này vẫn không làm WAR được hỗ trợ.

**Lỗi 7 — Thêm providedRuntime/provided Tomcat trong WebFlux rồi cho rằng external WAR chạy.** Dependency scope chỉ là một phần của packaging Servlet WAR, không tự giải quyết Boot reactive bootstrap. **Giải pháp:** chọn lại hướng runtime.

**Lỗi 8 — Đặt static resources ở src/main/webapp của WebFlux.** Boot WebFlux không dùng thư mục đó theo cách WAR servlet app truyền thống. **Giải pháp:** dùng src/main/resources/static hoặc resource locations được Boot WebFlux hỗ trợ.

**Lỗi 9 — Dùng Gradle war plugin và thấy task war thành công, rồi ghi “WebFlux WAR supported”.** Archive hợp lệ không bảo đảm runtime/deployment được framework hỗ trợ. **Giải pháp:** dựa vào Spring Boot documentation và thử startup đúng kiểu.

**Lỗi 10 — Chọn nhầm plain.jar thay bootJar khi deploy reactive app.** Plain JAR không nhất thiết mang Boot loader và nested dependencies. **Giải pháp:** chọn đúng executable Boot JAR và thử java -jar.

**Lỗi 11 — MVC WAR triển khai lỗi do dùng javax.servlet với Boot 3.x.** Spring Boot 3 sử dụng Jakarta namespace; container Servlet cũ có thể không tương thích. **Giải pháp:** chọn container Jakarta Servlet tương thích phiên bản Boot, không chỉ nhìn số Java.

**Lỗi 12 — MVC WAR báo 404 tại /hello dù ứng dụng đã start.** External container thường có context path từ tên WAR. **Giải pháp:** kiểm tra server deployment path, ví dụ /mvc-war-demo/hello thay vì /hello.

**Lỗi 13 — Dùng WebClient nhưng chờ mọi request tự non-blocking.** Reactive client không tự biến Spring MVC DispatcherServlet thành WebFlux DispatcherHandler. **Giải pháp:** đo hiệu năng thực tế, tránh block không chủ đích, phân biệt client/server stack.

**Lỗi 14 — Test integration chỉ chạy với bootRun nhưng không test WAR ngoài.** Với MVC WAR, deploy lên external Tomcat có thêm biến số: classloader, Servlet version, context path, provided libs. **Giải pháp:** có smoke test trên container mục tiêu thực tế.

**Lỗi 15 — Giấu giới hạn WAR bằng cách tự cấu hình AbstractReactiveWebInitializer rồi ghi đó là Spring Boot WebFlux chuẩn.** Đây là API của Spring Framework dành cho setup tùy biến, không phải traditional WAR deployment được Boot hỗ trợ. **Giải pháp:** ghi rõ kiến trúc/framework, owner và compatibility test.

**Lỗi 16 — Đổi từ MVC sang WebFlux chỉ để tránh thread blocking nhưng chưa xem các thư viện JDBC.** Nếu code vẫn dùng JDBC hoặc các API blocking trên event loop, khả năng mở rộng có thể không như kỳ vọng. **Giải pháp:** đánh giá reactive end-to-end, tác vụ blocking và lựa chọn framework theo workload.

**Lỗi 17 — Dùng WAR ngoài với dependency Netty không được quản lý lifecycle.** Servlet container không tự quản lý Reactor Netty bên trong một WebFlux JAR/ZIP tùy tiện. **Giải pháp:** sử dụng mô hình Boot JAR embedded server hoặc kiến trúc Servlet phù hợp.

**Lỗi 18 — Đặt test property spring.main.web-application-type=reactive rồi coi điều đó chứng minh môi trường production.** Một test context chạy được không kiểm chứng archive/traditional deployment lifecycle. **Giải pháp:** kiểm tra artifact cuối cùng và cách khởi động thực tế trong CI/staging.

## 16. Một ví dụ lựa chọn theo yêu cầu nghiệp vụ

**Bối cảnh:** Dịch vụ tra cứu dữ liệu cần xử lý nhiều lời gọi HTTP bất đồng bộ, còn bộ phận vận hành có truyền thống triển khai WAR trên một Tomcat dùng chung.

**Phương án 1 — Giữ WebFlux:** tổ chức cho phép chạy ứng dụng dưới dạng **executable JAR hoặc container image**. Dịch vụ có embedded Netty (hoặc embedded server khác), tự quản lý lifecycle. Cần bổ sung quy trình release/monitoring phù hợp. Đây là phương án phù hợp nếu reactive server stack là yêu cầu kỹ thuật quan trọng.

**Phương án 2 — Giữ external WAR:** ứng dụng chuyển về **Spring MVC** với Servlet container bên ngoài. Có thể vẫn dùng WebClient để gọi API bất đồng bộ ở client-side, nhưng request processing không phải WebFlux server. Đây là phương án phù hợp nếu external WAR là ràng buộc không thể thay đổi.

**Phương án 3 — Tự dùng Spring Framework WebFlux trên Servlet:** là công việc tùy biến sâu, kiểm soát HttpHandler adapter và bootstrap, không dựa vào contract Boot WebFlux WAR. Chỉ lựa chọn nếu có lý do đặc biệt, kiểm thử toàn diện và chấp nhận chi phí bảo trì.

**Câu hỏi quyết định:** Hệ thống thực sự cần **reactive server stack**, hay chỉ muốn **reactive HTTP client**? Câu trả lời ảnh hưởng đến kiến trúc hơn rất nhiều so với việc đổi tên file artifact từ .jar sang .war.

## 17. Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html) — nêu rõ giới hạn WAR của Spring Boot WebFlux và static resources.
- [Spring Boot — Traditional Deployment](https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html) — hướng dẫn WAR cho Servlet-based applications và cảnh báo không hỗ trợ WAR cho WebFlux.
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html) — kiến trúc Spring MVC, Servlet và cấu hình.
- [Spring Boot 3.3 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html) — Netty/Tomcat/Jetty/Undertow làm embedded runtime.
- [Spring Framework — WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html) — HttpHandler, ServletHttpHandlerAdapter và trường hợp WAR ở tầng Framework.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html) — phát hiện WebFlux/MVC và kiểm thử Boot web applications.
- [Spring Boot 3.3 — Maven Plugin Packaging](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html) — đóng gói executable archive.
- [Spring Boot 3.3 — Gradle Plugin Packaging](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html) — task bootJar và bootWar.

**Ghi nhớ cuối bài:** **Spring Boot WebFlux không hỗ trợ traditional WAR deployment vào external Servlet container.** Hãy dùng **executable JAR/container image** cho WebFlux server, kể cả khi muốn lựa chọn embedded Tomcat thay Netty. Nếu triển khai WAR ngoài là điều kiện bắt buộc, dùng **Spring MVC/Servlet stack** và cấu hình **SpringBootServletInitializer + provided servlet container** đúng quy trình. Khả năng **Spring Framework WebFlux WAR tùy biến** là một chủ đề khác, không phải lời hứa hỗ trợ cho Boot WebFlux WAR.
# Khi nào chọn WAR và khi nào chọn JAR với máy chủ nhúng trong Spring Boot?

## 1. Vấn đề cần quyết định

Spring Boot cho phép đóng gói một ứng dụng web để chạy **độc lập** với máy chủ HTTP nhúng (embedded server), hoặc triển khai theo mô hình **WAR vào servlet container bên ngoài**. Việc lựa chọn không chỉ là đổi đuôi file từ `.jar` sang `.war`. Nó tác động đến nơi chứa máy chủ servlet, người chịu trách nhiệm nâng cấp máy chủ, lệnh khởi động, thư viện được đóng gói và cách vận hành.

Có **ba trường hợp** nên phân biệt:

1. **Executable JAR + embedded server**: file JAR chứa mã ứng dụng, dependency và các thư viện embedded server như Tomcat. Đội vận hành chạy `java -jar app.jar`; JVM của ứng dụng tự khởi tạo HTTP server.
2. **Executable WAR + embedded server**: file WAR được Spring Boot đóng gói đúng cách, có cả dependency `provided`/`providedRuntime` trong `WEB-INF/lib-provided`. Có thể chạy `java -jar app.war` như một tiến trình độc lập.
3. **Deploy WAR vào external servlet container**: server Tomcat/Jetty/ứng dụng Servlet tương thích được cài và quản lý **bên ngoài** file WAR. Container nhận WAR và khởi tạo ứng dụng; thông thường bạn **không** chạy `java -jar` cho đường triển khai này.

**Nguyên tắc xuất phát:** Nếu không có yêu cầu phải dùng container ngoài, **executable JAR với embedded server thường là lựa chọn đơn giản nhất cho dịch vụ Spring Boot mới**. WAR thích hợp khi có yêu cầu triển khai tương thích với hạ tầng servlet container hiện hữu hoặc một số ràng buộc tổ chức.

Bài này dùng ví dụ **Spring Boot 3.5.x và Java 17**; hệ sinh thái Spring Boot 4.x có thay đổi phiên bản Servlet/container, vì vậy hãy đối chiếu tài liệu đúng **major/minor version** của project thật. Ví dụ cấu hình dưới đây minh họa bằng Spring Boot `3.5.16`.

## 2. Các thành phần: archive, Boot Loader và máy chủ nhúng

**JAR/WAR là kiểu archive và layout**, còn Tomcat/Jetty/Undertow là **máy chủ servlet**. Hai cặp khái niệm không đồng nhất.

Trong ứng dụng Servlet Spring MVC có starter `spring-boot-starter-web`:

- Spring Boot mặc định đưa `spring-boot-starter-tomcat` vào dependency graph, trừ khi đã thay đổi starter.
- **Embedded Tomcat** là thư viện được ứng dụng khởi tạo trong cùng tiến trình JVM, không phải một Tomcat service phải cài riêng.
- Với **external Tomcat**, container được cài/chạy độc lập; WAR cung cấp web application và container cung cấp servlet runtime.
- Các cấu hình như `server.port`, `server.ssl.*` hoặc `server.tomcat.*` chủ yếu điều khiển embedded server; khi deploy vào container bên ngoài, cơ chế vận hành/port/connector và một phần context path do container quyết định.

**Spring Boot Loader** hỗ trợ khởi chạy archive executable chứa các JAR phụ thuộc lồng bên trong:

```text
Executable JAR                  Executable WAR
+------------------+            +---------------------------+
| META-INF/        |            | META-INF/                 |
| Boot Loader      |            | Boot Loader               |
| BOOT-INF/classes |            | WEB-INF/classes           |
| BOOT-INF/lib     |            | WEB-INF/lib               |
+------------------+            | WEB-INF/lib-provided      |
   java -jar app.jar             +---------------------------+
      |                            java -jar app.war
      v                                  |
  JarLauncher                            v
      |                              WarLauncher
      +----------- Spring application --+
                        |
                        v
               Embedded servlet server

External container:
    Tomcat service -> deploy app.war -> Servlet initializer
                -> application context
                (không chạy WarLauncher bằng java -jar)
```

Đây là mô hình logic, không phải sơ đồ byte-for-byte của ZIP. `WEB-INF/lib-provided` được Boot Loader sử dụng khi chạy **executable WAR**; nó được bố trí để **không trở thành WEB-INF/lib thông thường** khi external container triển khai WAR.

## 3. Bảng so sánh lựa chọn

| Tiêu chí | JAR + embedded server | WAR chạy bằng `java -jar` | WAR vào external container |
|---|---|---|---|
| File phát hành | Executable `.jar` | Executable `.war` | Deployable `.war` (có thể cũng executable) |
| Ai khởi động HTTP server? | Spring Boot trong JVM ứng dụng | Spring Boot trong JVM ứng dụng | Container ngoài, ví dụ Tomcat đã chạy |
| Lệnh chạy điển hình | `java -jar app.jar` | `java -jar app.war` | Deploy/undeploy WAR theo cơ chế container |
| Layout lớp/thư viện | `BOOT-INF/classes`, `BOOT-INF/lib` | `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided` | Container nạp `WEB-INF/classes` và `WEB-INF/lib`; servlet runtime do container cung cấp |
| Launcher khi `java -jar` | `JarLauncher` | `WarLauncher` | Không gọi Boot launcher theo đường traditional deploy |
| Cập nhật servlet server | Thường nâng dependency Boot/Tomcat và rebuild image/artifact | Tương tự khi chạy độc lập | Đội vận hành nâng/nắn cấu hình container ngoài |
| Cấu hình cổng và TLS | Tiến trình ứng dụng hoặc proxy/ingress | Tiến trình ứng dụng hoặc proxy/ingress | Container ngoài, proxy/ingress |
| Cô lập tiến trình | Một JVM ứng dụng có thể deploy/scale độc lập | Tương tự JAR khi chạy standalone | Có thể chia sẻ JVM/container với WAR khác |
| Kiểu CI/CD thường gặp | Container image chứa app + JVM; roll out từng instance | Image/tiến trình chạy `java -jar` WAR | Copy/deploy WAR vào managed servlet container |
| Độ đơn giản cho dịch vụ mới | Thường cao | Chỉ hữu ích khi cần cùng WAR cho hai cách chạy | Phụ thuộc hạ tầng, cấu hình container và compatibility |
| Hệ reactive mặc định | Phù hợp với WebFlux + Reactor Netty | Không nên chọn chỉ để “có đuôi WAR” | Spring Boot 3.5 **không hỗ trợ WAR deployment cho WebFlux** theo tài liệu traditional deployment |

**Không suy luận hiệu năng từ đuôi file:** JAR không mặc nhiên nhanh hơn WAR, WAR không mặc nhiên tiết kiệm RAM. Tốc độ và tài nguyên phụ thuộc workload, server, thread/connection pools, JVM flags, cách scale và công nghệ deploy. Khác biệt quan trọng là **ranh giới trách nhiệm vận hành**.

## 4. Khi nào nên chọn executable JAR + embedded server?

JAR phù hợp nhất nếu:

- Bắt đầu **microservice**, REST API, ứng dụng Spring MVC mới, dịch vụ xử lý job/webhook, hoặc ứng dụng WebFlux mặc định chạy Reactor Netty.
- Muốn mỗi service có **vòng đời triển khai riêng**: build một artifact/image, chạy một JVM, kiểm tra health, scale nhiều instance.
- Dùng Docker/Kubernetes, systemd, VM hoặc một nền tảng hỗ trợ chạy process/container trực tiếp.
- Muốn kiểm soát bản Tomcat/Jetty/Undertow của ứng dụng bằng dependency management và quy trình build, thay vì phụ thuộc container chung do bên khác quản trị.
- Muốn có command nhất quán giữa local, CI và runtime production: `java -jar`.
- Không có chính sách bắt buộc nộp WAR cho application server.

**Điểm mạnh:** cấu hình, dependency và server version thường đi cùng application artifact; dễ làm immutable deployment và rollback theo phiên bản image. Triển khai ít bị ảnh hưởng bởi các WAR khác nếu mỗi app có JVM riêng.

**Đánh đổi:** bạn phải **tự cập nhật** embedded server khi có lỗ hổng; nhiều JVM/instance đồng nghĩa mỗi app có heap, thread pools và các chi phí runtime riêng. Không nên khẳng định kiến trúc một container/JVM cho mỗi service luôn rẻ hơn môi trường chia sẻ.

**Lưu ý:** JAR executable **không phải** điều kiện bắt buộc để dùng Spring Boot; bạn có thể chạy `bootRun`/`spring-boot:run` trực tiếp khi phát triển. Khi phát hành, build `bootJar` hoặc `spring-boot:repackage` tạo artifact dùng cho đường `java -jar`.

## 5. Khi nào nên chọn WAR triển khai vào servlet container bên ngoài?

WAR thích hợp khi tổ chức đã có ràng buộc rõ, chẳng hạn:

- Hệ thống production chỉ hỗ trợ deploy **WAR qua Tomcat/Jetty/ứng dụng Servlet** quản lý tập trung, với quy trình release/rollback tuân thủ hạ tầng đó.
- Bạn đang **hiện đại hóa ứng dụng Spring MVC truyền thống** và muốn chuyển dần sang Spring Boot mà chưa được phép thay đổi cách deploy.
- Platform team chịu trách nhiệm phiên bản container, connector, TLS, thread pool, policy vận hành và muốn quản lý chúng ở cấp máy chủ dùng chung.
- Nhiều ứng dụng servlet hiện chia sẻ một application server; migration cần giữ cơ chế deployment để giảm thay đổi hạ tầng trong một giai đoạn.
- Hợp đồng/hệ thống tích hợp cần artifact `.war` có cấu trúc chuẩn.

**Đánh đổi:**

1. Phiên bản servlet container/JDK bên ngoài phải **tương thích** với Spring Boot đang dùng; mã biên dịch qua `jakarta.servlet` của Boot 3.x sẽ không phù hợp với môi trường chỉ hỗ trợ `javax.servlet` cũ.
2. Khi nhiều WAR dùng chung một JVM/container, có thể có xung đột classloader, logging, resource/thread pools, cấu hình và ảnh hưởng lẫn nhau khi container restart.
3. Rollback một WAR có thể bị ràng buộc bởi cơ chế undeploy/redeploy và trạng thái container; không đồng nhất với restart một container image độc lập.
4. Một số tùy chọn `server.*` ở application properties không chi phối external container như khi chạy embedded.
5. Các lỗi chỉ xuất hiện ở external container (context path, servlet initialization, JNDI, container-provided API) cần test deploy thật, không đủ chỉ chạy `java -jar app.war`.

**Cảnh báo:** Chọn WAR vì “server ngoài chắc chắn an toàn hơn” hoặc “WAR luôn nhanh hơn” là suy luận không có cơ sở. Server ngoài cần chính sách vá lỗi, phân tách ứng dụng, logging và giám sát riêng.

## 6. WAR executable không đồng nghĩa WAR phải dùng container ngoài

Một **WAR được Spring Boot repackage đúng cách** có thể phục vụ cả hai đường:

```text
cùng file app.war
    |
    +--> java -jar app.war
    |    -> WarLauncher
    |    -> đọc WEB-INF/lib-provided
    |    -> khởi động embedded Tomcat
    |
    +--> Deploy vào Tomcat ngoài
         -> Tomcat đọc cấu trúc WAR chuẩn
         -> dùng Servlet initializer
         -> không nạp thư viện provided như WEB-INF/lib
```

Điều này hữu ích trong giai đoạn migration: đội vận hành chạy WAR trong container hiện tại, developer vẫn có thể kiểm tra nhanh bằng `java -jar`. Tuy nhiên cần **kiểm thử cả hai đường** vì classpath, context path, cấu hình server và phiên bản servlet runtime khác nhau.

**Cách đóng gói mới quan trọng hơn đuôi `.war`:** một WAR thông thường chưa qua Spring Boot repackaging có thể deploy được trên Tomcat nhưng `java -jar` báo không có entry point. Ngược lại, một executable WAR sai initializer hoặc sai servlet dependency scope có thể chạy bằng `java -jar` nhưng deploy vào Tomcat ngoài thất bại.

## 7. Phạm vi hỗ trợ: Servlet, WebFlux và các phiên bản

### 7.1. Servlet MVC và embedded servers

Trong Spring Boot 3.5, lựa chọn embedded servlet container gồm Tomcat 10.1, Jetty 12 và Undertow 2.3 tương thích dòng Servlet 6.0. Mặc định `spring-boot-starter-web` sử dụng Tomcat; bạn có thể thay bằng starter Jetty/Undertow nếu phù hợp.

Với **external container**, tài liệu hệ thống Spring Boot 3.5 công bố có thể deploy tới servlet container tương thích Servlet **5.0+**. Trong thực tế phải kiểm tra thêm JDK, namespace Jakarta, API/security và khả năng hỗ trợ bởi vendor; dùng **Tomcat 10.1 tương thích** là phương án minh họa an toàn cho Boot 3.5. Tránh deploy Boot 3.x lên Tomcat 9.x dựa trên `javax.servlet` rồi kỳ vọng hoạt động.

Đừng áp dụng version Tomcat/Servlet của Spring Boot 3.5 cho Spring Boot 4.x mà không tra tài liệu 4.x; chiến lược đóng gói tương tự nhưng baseline thư viện có thể khác.

### 7.2. WebFlux không chọn traditional WAR

Spring Boot 3.5 document cảnh báo **WAR deployment không hỗ trợ cho Spring WebFlux applications**. Với ứng dụng reactive WebFlux thường dùng `spring-boot-starter-webflux` và Reactor Netty, lựa chọn đơn giản là executable JAR chạy server nhúng. Dù một số thư viện reactive có thể tích hợp nền tảng servlet trong tình huống khác, **không** suy luận rằng chỉ cần đổi `<packaging>war</packaging>` là Spring Boot WebFlux deploy được theo traditional WAR.

### 7.3. Không nhầm server nhúng với proxy

Cả JAR và WAR chạy standalone vẫn có thể đặt sau **Nginx, Apache HTTP Server, ingress controller hoặc cloud load balancer**. Reverse proxy xử lý HTTP routing/TLS/traffic, nhưng **không nhất thiết là servlet container**. Việc có Nginx phía trước **không đòi hỏi** phải build WAR.

## 8. Ví dụ Java 17 dùng chung khi chuyển giữa JAR và WAR

Giả sử ứng dụng tên `deployment-demo` với Spring Boot 3.5.x, Java 17, dependency `spring-boot-starter-web`. Ta sẽ dùng một lớp entry point có thể chạy bằng `main` và hỗ trợ traditional WAR deployment, để việc so sánh không bị nhiễu bởi thay đổi business code.

### 8.1. Cấu trúc nguồn

```text
deployment-demo/
├── pom.xml                       # nếu chọn Maven
│   hoặc
├── settings.gradle               # nếu chọn Gradle Groovy
├── build.gradle
├── src/main/java/com/example/deploy/
│   ├── DeployApplication.java
│   └── HelloController.java
├── src/main/resources/application.properties
└── src/test/java/com/example/deploy/
    └── HelloControllerTest.java
```

Chỉ tạo bộ file build của **một** công cụ trong mỗi project. Trong triển khai thực tế, Maven Wrapper hoặc Gradle Wrapper được commit cùng source (ví dụ `mvnw` hoặc `gradlew`).

### 8.2. Main class cho cả hai đường khởi động

File `src/main/java/com/example/deploy/DeployApplication.java`:

```java
package com.example.deploy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class DeployApplication extends SpringBootServletInitializer {

    public static void main(String[] args) {
        SpringApplication.run(DeployApplication.class, args);
    }

    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder application) {
        return application.sources(DeployApplication.class);
    }
}
```

Hai entry points có vai trò khác nhau:

- `main(...)` cho đường **java -jar**. Spring Boot Loader gọi main class được chỉ định bởi `Start-Class`, sau đó `SpringApplication.run` khởi động ứng dụng và embedded server.
- `configure(...)` của `SpringBootServletInitializer` cho đường **external servlet container**. Tomcat ngoài khởi tạo application context qua Servlet startup mà **không cần gọi `main`**.

Việc kế thừa `SpringBootServletInitializer` trong ví dụ JAR **không bắt buộc**; nó chỉ làm mã nguồn chung dễ chuyển đổi. Nếu dự án JAR mới không có kế hoạch WAR, main class đơn giản với `@SpringBootApplication` và `main` là đủ.

### 8.3. Controller

File `src/main/java/com/example/deploy/HelloController.java`:

```java
package com.example.deploy;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello from Spring Boot";
    }
}
```

File `src/main/resources/application.properties`:

```properties
spring.application.name=deployment-demo
server.port=8080
```

Khi chạy bằng **executable JAR/WAR standalone** và không có cấu hình khác, HTTP GET `http://localhost:8080/hello` trả body:

```text
Hello from Spring Boot
```

Đây là **HTTP response body**, không phải toàn bộ stdout; log khởi động và dòng xuống hàng của `curl` phụ thuộc terminal/môi trường. Nếu cổng 8080 đã bị chiếm, dùng `--server.port=8081` sau tên JAR/WAR và truy cập 8081.

Trong **Tomcat bên ngoài**, URL thường là `http://localhost:8080/<context-path>/hello`, với context path do tên WAR/ứng dụng và cấu hình container quyết định. Giá trị `server.port` trong `application.properties` **không quyết định** cổng HTTP listener của Tomcat ngoài.

### 8.4. Smoke test không phụ thuộc cổng hoặc WAR context path

File `src/test/java/com/example/deploy/HelloControllerTest.java`:

```java
package com.example.deploy;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
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
    private MockMvc mockMvc;

    @Test
    void helloEndpointWorks() throws Exception {
        mockMvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello from Spring Boot"));
    }
}
```

Test này dùng JUnit Jupiter và `spring-boot-starter-test` (thêm trong các build files ở dưới). Nó kiểm tra hành vi Spring MVC trong **test application context**, không cần deploy WAR vào Tomcat ngoài. **Nó không thay thế integration test deployment** trên container đích, bởi khác classpath và servlet lifecycle.

### 8.5. Điều kiện chạy mã

Các file Java ở mục 8 có cú pháp Java 17, nhưng không thể biên dịch bằng một lệnh `javac` trần thiếu dependency Spring/JUnit. Maven/Gradle sẽ tải classpath tương ứng. Chỉ gọi `javac DeployApplication.java` sẽ thất bại vì không tìm thấy Spring API; đó không phải lỗi trong ví dụ.

## 9. Maven: executable JAR mặc định

### 9.1. POM đầy đủ cho JAR

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>deployment-demo</artifactId>
    <version>0.1.0-SNAPSHOT</version>
    <packaging>jar</packaging>

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

Giải thích:

1. `<packaging>jar</packaging>` là kiểu archive đầu ra. Nếu bỏ thuộc tính trong Maven project thông thường, mặc định cũng là `jar`.
2. `spring-boot-starter-web` đưa Spring MVC và embedded Tomcat vào dependency graph mặc định.
3. `spring-boot-maven-plugin` thực hiện `repackage` để tạo **executable JAR** (đối với POM kế thừa Boot starter parent, execution đã được cấu hình). Nó tạo layout `BOOT-INF` và manifest phù hợp.
4. `spring-boot-starter-test` ở scope test không đưa JUnit vào runtime application như dependency production.
5. Boot parent quản lý version starter; không gán version từng starter tùy tiện.

### 9.2. Build và chạy

```bash
# Unix/macOS, từ thư mục dự án Maven có Maven Wrapper
./mvnw clean verify

# Kiểm tra artifact thực tế trong target/
java -jar target/deployment-demo-0.1.0-SNAPSHOT.jar

# Terminal khác sau khi app start
curl -s http://localhost:8080/hello
```

Response body mong đợi: `Hello from Spring Boot`. Trên Windows dùng `mvnw.cmd clean verify`; file JAR ở `target` khi build giữ các tên mặc định.

**Không bắt buộc `clean` mỗi lần:** `./mvnw package` đủ để đóng gói trong thông thường, còn `verify` chạy đến phase kiểm tra. `clean` hữu ích khi nghi output cũ gây nhầm lẫn.

Manifest executable JAR Spring Boot 3.5 thường có:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.deploy.DeployApplication
```

Ngoài ra archive có `BOOT-INF/classes/com/example/deploy/DeployApplication.class` và các nested JAR trong `BOOT-INF/lib`.

## 10. Maven: chuyển sang executable/deployable WAR

### 10.1. Thay đổi tối thiểu có ý nghĩa

Giữ nguyên source Java ở mục 8 và phần lớn POM mục 9, nhưng:

1. Đổi `<packaging>jar</packaging>` thành `<packaging>war</packaging>`.
2. Đánh dấu embedded Tomcat là `provided`.
3. Giữ `spring-boot-maven-plugin` để Spring Boot repackage thành executable WAR.
4. Giữ `SpringBootServletInitializer` để container ngoài khởi tạo ứng dụng.

Fragment cần có trong POM WAR:

```xml
<packaging>war</packaging>

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
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

**Đây là đoạn thay thế** cho `<packaging>` và `<dependencies>` trong POM mục 9, **không được dán thêm một `<dependencies>` thứ hai** vào POM hiện có. `<parent>`, tọa độ project, properties và `<build><plugins>` giữ như ví dụ JAR.

Mặc dù `spring-boot-starter-web` kéo Tomcat transitively, khai báo `spring-boot-starter-tomcat` trực tiếp ở scope `provided` giúp Maven áp dụng phạm vi mong muốn; đó chính là cấu hình traditional WAR của Spring Boot.

### 10.2. provided nghĩa là gì?

Trong Maven, `provided` nói rằng dependency cần cho compile/test nhưng được **container/runtime bên ngoài cung cấp** theo mô hình triển khai truyền thống. Đối với Spring Boot **executable WAR**, Boot repackager vẫn sắp xếp dependency `provided` vào `WEB-INF/lib-provided`:

- **External Tomcat** không tải chúng như thư viện `WEB-INF/lib` thông thường, tránh va chạm với Tomcat container đang có.
- **WarLauncher** khi `java -jar app.war` có thể đưa chúng vào classpath để tự khởi động embedded Tomcat.

Đừng nghĩ `provided` nghĩa là **xóa hẳn Tomcat khỏi file WAR**; mô hình executable WAR của Spring Boot cần giữ chúng ở vị trí đặc biệt. Đừng hiểu `provided` trong WAR giống nguyên xi ý nghĩa mọi dependency provided ở tất cả kiểu đóng gói.

### 10.3. Build và chạy hai đường

```bash
./mvnw clean verify
java -jar target/deployment-demo-0.1.0-SNAPSHOT.war
```

Đường executable chạy `http://localhost:8080/hello` (trừ khi có override).

Đường external deployment: copy/deploy file `target/deployment-demo-0.1.0-SNAPSHOT.war` vào Tomcat tương thích theo công cụ và chính sách hạ tầng. Ví dụ nếu Tomcat đặt context theo tên file WAR, URL có thể là:

```text
http://localhost:8080/deployment-demo-0.1.0-SNAPSHOT/hello
```

**Chỉ là ví dụ context path**, không bảo đảm chính xác khi người vận hành đặt tên context khác, dùng ROOT.war, reverse proxy, cấu hình host hoặc deploy bằng API.

Tài liệu Spring Boot 3.5 mô tả `Main-Class` của executable WAR dùng `org.springframework.boot.loader.launch.WarLauncher`. **External Tomcat không gọi launcher này**, mà khởi tạo ứng dụng qua Servlet container lifecycle và initializer.

## 11. Gradle: executable JAR bằng bootJar

Một project Gradle Groovy DSL cần `settings.gradle`:

```groovy
rootProject.name = 'deployment-demo'
```

Và `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0-SNAPSHOT'

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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là build script **JAR**; không áp dụng `war` plugin. Spring Boot Gradle plugin tạo task `bootJar` khi dùng Java plugin để sinh executable JAR; `jar` thường tạo JAR Java thông thường.

```bash
./gradlew clean test bootJar
java -jar build/libs/deployment-demo-0.1.0-SNAPSHOT.jar
```

Với Windows: `gradlew.bat clean test bootJar`. Tên archive giả định `rootProject.name` và `version` như trên; nếu người dùng cấu hình classifier/name khác, xem `build/libs` để chọn đúng.

Task `bootRun` **không phải** đường chạy executable JAR: nó chạy trực tiếp runtime classpath của source set trong giai đoạn phát triển. Muốn xác minh Boot Loader và package contents, phải chạy `java -jar` trên artifact thật.

## 12. Gradle: executable/deployable WAR bằng bootWar

### 12.1. Khác biệt trong build.gradle

Đổi build `JAR` ở mục 11 thành cấu hình `WAR`. Đoạn sau là **file `build.gradle` đầy đủ**:

```groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.1.0-SNAPSHOT'

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

    // Cần khi chạy executable WAR, nhưng container ngoài sẽ cung cấp Tomcat
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Khi `war` plugin được áp dụng cùng Spring Boot plugin, task `bootWar` đóng gói executable WAR. Configuration `providedRuntime` được `war` plugin hỗ trợ; Boot `bootWar` đặt những dependency này vào `WEB-INF/lib-provided`.

**Dùng `providedRuntime` thay vì `compileOnly`** cho embedded container: tài liệu Spring Boot giải thích `compileOnly` không xuất hiện trên test classpath, khiến web-based integration tests có thể thất bại; `providedRuntime` phù hợp hơn trong mô hình deployable WAR.

Gradle có thể tạo nhiều task archive như `war`, `bootWar` hoặc `bootJar` tùy plugin/config; **đừng đoán** file nào đã được tạo chỉ từ extension hoặc từ `build`. Chọn trực tiếp task `bootWar` khi cần executable/deployable WAR.

### 12.2. Build, chạy standalone và deploy external

```bash
./gradlew clean test bootWar
java -jar build/libs/deployment-demo-0.1.0-SNAPSHOT.war
```

Dù `providedRuntime` được dùng, `java -jar` vẫn có embedded Tomcat qua `lib-provided`. Nếu muốn deploy external, đưa file `.war` này cho servlet container tương thích; đừng copy file `.jar` và kỳ vọng Tomcat đọc như web application WAR.

Khi muốn chỉ kiểm tra cấu trúc:

```bash
jar tf build/libs/deployment-demo-0.1.0-SNAPSHOT.war
```

Tìm `WEB-INF/classes/com/example/deploy/DeployApplication.class`, `WEB-INF/lib`, `WEB-INF/lib-provided` và loader classes. File cụ thể của starter/Tomcat phụ thuộc build version.

### 12.3. Kotlin DSL tương ứng

Nếu project dùng `build.gradle.kts`, những thay đổi chính:

```kotlin
plugins {
    java
    war
    id("org.springframework.boot") version "3.5.16"
    id("io.spring.dependency-management") version "1.1.7"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    providedRuntime("org.springframework.boot:spring-boot-starter-tomcat")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
```

Đây là **fragment** để đặt trong `build.gradle.kts` cùng `group`, `version`, `java { toolchain { ... } }` và `repositories { mavenCentral() }` từ mẫu Groovy đã được chuyển cú pháp. Không trộn dấu nháy Groovy `id 'war'` với Kotlin DSL.

## 13. Vị trí dependency trong archive: đọc đúng bố cục

### 13.1. Executable JAR

```text
deployment-demo-0.1.0-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/com/example/deploy/DeployApplication.class
    ├── classes/com/example/deploy/HelloController.class
    ├── classes/application.properties
    └── lib/
        ├── spring-boot-*.jar
        ├── tomcat-embed-*.jar
        └── ... các dependency runtime khác
```

Khi JVM đọc manifest, `Main-Class` thường là `org.springframework.boot.loader.launch.JarLauncher` và `Start-Class` là `com.example.deploy.DeployApplication`. Embedded server được nạp như library runtime của app.

### 13.2. Executable WAR

```text
deployment-demo-0.1.0-SNAPSHOT.war
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── WEB-INF/
    ├── classes/com/example/deploy/DeployApplication.class
    ├── classes/com/example/deploy/HelloController.class
    ├── classes/application.properties
    ├── lib/
    │   ├── spring-webmvc-*.jar
    │   └── ... dependency ứng dụng
    └── lib-provided/
        ├── tomcat-embed-*.jar
        └── ... provided dependencies
```

Các tên JAR có dấu `*` chỉ là minh họa; nội dung thực tế phụ thuộc artifact và version. Với executable WAR, `Main-Class` là `org.springframework.boot.loader.launch.WarLauncher` và `Start-Class` là main ứng dụng.

**Đừng nhầm** `WEB-INF/lib-provided` với việc Tomcat ngoài chủ động đọc nó: đây là phần đóng gói giúp **WarLauncher** có dependency khi chạy standalone mà external container tránh nạp trùng như một WEB-INF/lib thông thường.

## 14. Phạm vi cấu hình khác nhau giữa hai kiểu server

### 14.1. Cổng, context path, TLS

Trong executable JAR/WAR, cấu hình:

```properties
server.port=8081
server.servlet.context-path=/api
```

thường làm Spring Boot điều khiển embedded servlet server lắng nghe port 8081 và ứng dụng nằm dưới path `/api` (giả sử không có override). Endpoint demo khi đó là `http://localhost:8081/api/hello`.

Khi **deploy WAR vào external Tomcat**, cổng 8081, TLS/HTTP connectors và context path có thể do Tomcat/server admin quy định. Không mặc định `server.port` hoặc `server.servlet.context-path` sẽ thay thế cấu hình deploy của external Tomcat. Hãy đối chiếu container admin console, `server.xml`/context descriptors, reverse proxy và version Tomcat thực tế.

### 14.2. JVM và tài nguyên chia sẻ

Standalone JAR/WAR chạy trong một JVM ứng dụng riêng. Vì vậy `-Xmx`/GC/system properties thuộc process này và thường được quản lý bởi deployment spec/script của app.

External Tomcat dùng JVM của **container**. Các WAR được deploy vào cùng JVM có thể chịu chung cấu hình heap/GC, process uptime, một phần shared libraries và startup/shutdown lifecycle. Điều này có thể đem lại tập trung quản lý, nhưng cũng có rủi ro ảnh hưởng lẫn nhau và khó phân bổ resource/monitoring per WAR.

### 14.3. Logging, thread pool và database

- Với embedded server, Spring Boot cấu hình server và logger trong phạm vi app theo các property, starter và custom bean.
- Với external servlet container, container có logging/access log, thread pool, connector và classloader policy riêng. Ứng dụng cũng có logger Spring; cần tránh xung đột binding hoặc trùng log.
- Nếu dùng JNDI DataSource do container cấp, phải cấu hình Spring Boot tham chiếu tới tài nguyên đúng tên/vị trí; một số dự án WAR truyền thống có yêu cầu này.
- Những yêu cầu vận hành khác biệt không thể giải quyết chỉ bằng đổi extension artifact.

## 15. CI/CD, Docker/Kubernetes và quản lý bản vá

**JAR với embedded server:** pipeline build JAR, chạy tests, tạo image chứa JDK/JRE phù hợp và artifact, triển khai nhiều instance sau load balancer. Cập nhật Tomcat bằng cách nâng Spring Boot-managed dependency, rebuild artifact/image, kiểm thử rồi rollout.

**WAR executable trong container:** vẫn có thể đóng gói vào image và chạy `java -jar app.war`. Nếu mục tiêu chỉ là chạy standalone, lựa chọn WAR này không tự tạo lợi thế so với JAR; nó thường được chọn khi muốn **cùng artifact** hỗ trợ thêm external deployment.

**WAR deploy ngoài:** pipeline build WAR, publish artifact vào repository, triển khai tới Tomcat/Servlet container đã có; team hạ tầng quản lý máy chủ, runtime, patch và restart theo chính sách. Cần quản lý **tương thích phiên bản container** trong quy trình release.

### 15.1. Dockerfile minh họa cho JAR

```dockerfile
# Dùng base image Java runtime 17 phù hợp chính sách tổ chức.
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/deployment-demo-0.1.0-SNAPSHOT.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

Ví dụ này giả định Maven đã build **JAR**, base image có thể tải được và chính sách image scanning được áp dụng. `EXPOSE 8080` chỉ là metadata Docker; thực tế port có thể đổi qua cấu hình và phải được publish/map/route ở runtime. Tránh chạy container với quyền rộng không cần thiết hoặc đưa secret vào image; một hệ thống sản xuất thường cấu hình user không root, memory limits, health checks và logging.

Với Gradle, đổi `COPY` từ `target` sang đường dẫn `build/libs` của output tương ứng. Dockerfile **không chuyển một WAR external deployment thành JAR**; chỉ minh họa đường chạy standalone.

### 15.2. Health check và thao tác rollback

Dù đóng gói JAR hay WAR, pipeline nên kiểm tra:

- Artifact đúng **version/commit** và cùng tập dependency đã test.
- Health readiness/liveness qua Spring Boot Actuator nếu có cấu hình thích hợp; đừng dùng health endpoint chưa tồn tại.
- Startup logs không có `ClassNotFoundException`, `NoSuchMethodError`, binding/port error.
- HTTP smoke test đi qua URL/context path thực tế của môi trường.
- Có rollback recipe cho **JVM/instance** (JAR) hoặc **container/WAR** (external deployment).

Một external container cần được vá độc lập với WAR; một embedded server cần được vá bằng artifact/image mới. Không có chiến lược nào tự động miễn nhiễm lỗ hổng.

## 16. Thực hành đối chiếu ba cách chạy trên cùng source

**Điều kiện:** JDK 17+, Maven Wrapper hoặc Gradle Wrapper đúng phiên bản, Spring Boot 3.5.x, các file Java và test ở mục 8, cổng 8080 chưa bị dùng và một Tomcat ngoài tương thích nếu thử deploy WAR.

### 16.1. Lượt A: JAR standalone

Maven: dùng POM JAR mục 9.

```bash
./mvnw clean verify
java -jar target/deployment-demo-0.1.0-SNAPSHOT.jar
```

Hoặc Gradle: dùng build JAR mục 11.

```bash
./gradlew clean test bootJar
java -jar build/libs/deployment-demo-0.1.0-SNAPSHOT.jar
```

Trong terminal khác gọi `curl -s http://localhost:8080/hello`. Body là `Hello from Spring Boot`. Quan sát log server được Spring Boot khởi động trong cùng JVM.

### 16.2. Lượt B: WAR standalone

Dừng lượt A. Dùng cấu hình WAR Maven mục 10 hoặc Gradle mục 12:

```bash
# Maven
./mvnw clean verify
java -jar target/deployment-demo-0.1.0-SNAPSHOT.war
```

```bash
# Gradle (nếu dự án của bạn dùng Gradle)
./gradlew clean test bootWar
java -jar build/libs/deployment-demo-0.1.0-SNAPSHOT.war
```

Với executable WAR, endpoint vẫn có thể nằm tại `http://localhost:8080/hello` vì **embedded Tomcat** đang xử lý request. Phân biệt với external Tomcat chỉ từ lệnh khởi động và nguồn process.

### 16.3. Lượt C: WAR vào Tomcat bên ngoài

Dừng các process standalone trước để tránh tranh cổng. Khởi động một Tomcat ngoài tương thích và deploy **WAR vừa build** bằng cơ chế của container.

- Không gọi `java -jar app.war` ở lượt này.
- Xem log Tomcat để biết ứng dụng được khởi tạo qua `SpringBootServletInitializer`.
- Xác định context path của WAR theo cấu hình deploy; thử `/deployment-demo-0.1.0-SNAPSHOT/hello` nếu container dùng tên WAR làm context và không có override.
- Trả body `Hello from Spring Boot` nếu deploy và routing đúng.
- Thay đổi `server.port` trong WAR không mặc nhiên đổi cổng listener của Tomcat ngoài.

**Tiêu chí so sánh công bằng:** cùng source, JDK/Servlet API tương thích, same business properties, database và environment; chỉ thay packaging/launcher hoặc container deployment path. Nếu có khác biệt, kiểm tra classpath, provided dependencies, context path, profile và container logs.

## 17. Chẩn đoán lỗi theo triệu chứng

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
|---|---|---|
| `no main manifest attribute` khi `java -jar` | Đang chạy plain JAR/WAR hoặc thiếu Boot `repackage` | Build đúng `package`/`bootJar`/`bootWar`, xem manifest và file artifact |
| `JarLauncher`/`WarLauncher` không tìm thấy | Archive/manifest do custom packaging tạo sai | Dùng Spring Boot build plugin đúng version, kiểm tra loader classes |
| JAR chạy nhưng WAR Tomcat ngoài không khởi động | Chưa kế thừa `SpringBootServletInitializer` hoặc Servlet runtime không tương thích | Thêm initializer, kiểm tra JDK/Jakarta/Servlet version và container logs |
| `ClassNotFoundException: jakarta.servlet.*` | Dependency/container Servlet API không tương thích | Kiểm tra container ngoài và scope của embedded server |
| `ClassCastException`/`LinkageError` khi deploy WAR | Trùng/khác version server library hoặc shared library | Kiểm tra `WEB-INF/lib`, `lib-provided`, classloader policies và server version |
| `server.port` không tác động khi deploy Tomcat ngoài | Cổng được Tomcat quản lý | Sửa connector/container config, không chỉ application.properties |
| `/hello` trả 404 ở external Tomcat | Sai context path hoặc routing/scan | Thử `/<context>/hello` đúng deployment name; xem logs |
| `java -jar app.war` fail vì thiếu embedded Tomcat | `provided`/`providedRuntime` hoặc packaging sai, bị exclude | Kiểm tra lib-provided và Spring Boot repackaging |
| `providedRuntime` không tồn tại ở Gradle | Chưa áp dụng `war` plugin hoặc dùng sai DSL | Thêm `id 'war'`/`war` và dùng `providedRuntime` |
| WAR chỉ có WEB-INF/lib, không có lib-provided | Có thể là plain WAR, không dùng Boot repackager/không có provided deps | Kiểm tra task/goal build và khai báo Tomcat provided |
| WebFlux không deploy được kiểu WAR | WAR traditional deployment không hỗ trợ WebFlux theo Spring Boot 3.5 | Sử dụng executable JAR + embedded reactive runtime |
| Standalone JAR chạy được nhưng webapp trên container lỗi JNDI | Context/resource naming của Tomcat ngoài khác | Cấu hình JNDI và Spring property khớp môi trường |
| Tên JAR/WAR khác lệnh mẫu | Project version, artifact ID, classifier hoặc archive name thay đổi | Liệt kê `target`/`build/libs` thay vì đoán |
| CI gọi `bootJar` nhưng thiếu WAR | Task `bootJar` không tạo `bootWar` | Gọi `bootWar`/`package` với đúng packaging |
| Dùng WAR external, lỡ commit Tomcat `provided` thành runtime normal | Duplicate embedded servlet library trong `WEB-INF/lib` | Đặt scope `provided`/`providedRuntime`, kiểm tra archive |

### 17.1. Lệnh kiểm tra nhanh

```bash
# Kiểm tra archive có class ứng dụng và dependency đúng layout
jar tf target/deployment-demo-0.1.0-SNAPSHOT.war

# Gradle WAR tương đương
jar tf build/libs/deployment-demo-0.1.0-SNAPSHOT.war

# Maven dependency graph (trong project Maven)
./mvnw dependency:tree

# Gradle runtime dependency graph (trong project Gradle)
./gradlew dependencies --configuration runtimeClasspath
```

Chỉ chạy lệnh phù hợp với build tool/kiểu artifact của bạn. Nếu terminal không có `jar`, dùng JDK đầy đủ hoặc công cụ đọc ZIP đáng tin. `jar tf` kiểm tra entry có mặt nhưng **không chứng minh archive khởi chạy thành công**; luôn thử `java -jar` hoặc deploy thật.

## 18. Decision tree chọn JAR hoặc WAR

```text
Ứng dụng Spring Boot cần triển khai
              |
              v
Có yêu cầu BẮT BUỘC deploy vào
external Servlet container không?
        /                  \
      Không                Có
       |                    |
       v                    v
Dùng reactive WebFlux?   Ứng dụng Servlet MVC?
   /        \               /          \
 Có          Không         Có          Không
 |             |            |            |
 v             v            v            v
JAR +         JAR +       WAR +        Kiểm tra lại
embedded      embedded    Servlet      kiến trúc/khả năng
reactive      servlet     initializer  WAR trước
runtime       server          |
                             v
                     Tomcat ngoài tương thích
                             |
                             v
                   Cần chạy cùng WAR standalone?
                            /  \
                           Có  Không
                            |   |
                            v   v
                      Boot executable WAR
                      với providedRuntime/
                      provided dependency
                      (vẫn có thể deploy ngoài)
```

Trong nhánh **không cần external container**, bạn vẫn có thể dùng executable WAR nếu tổ chức cần artifact loại WAR, nhưng cần hiểu đây là yêu cầu phát hành riêng, không phải nhu cầu kỹ thuật tự nhiên của microservice mới. Nếu cả JAR và WAR đều đáp ứng, lựa chọn **ít khác biệt hạ tầng và ít thao tác đặc thù** thường dễ vận hành hơn.

## 19. Checklist ra quyết định và nghiệm thu

1. **Mô hình runtime:** JVM riêng hay servlet container chia sẻ? Ai cấp máy chủ HTTP?
2. **Hạn chế hạ tầng:** Có chính sách chỉ nhận WAR không? Có CI/CD cho JAR/container không?
3. **Kiểu ứng dụng:** Spring MVC/Servlet hay WebFlux/reactive? Với Boot 3.5, WebFlux không dùng traditional WAR deployment.
4. **Version:** Java, Spring Boot, embedded/external servlet container và Jakarta Servlet API tương thích?
5. **Packaging:** Maven `jar/war` và `repackage`; Gradle `bootJar/bootWar` đã đúng?
6. **Initializer:** Nếu external WAR, có `SpringBootServletInitializer` và source Boot application đúng không?
7. **Dependency scope:** WAR external đã có `provided`/`providedRuntime` cho servlet container dependency và `WEB-INF/lib-provided` chưa?
8. **Artifacts:** Manifest và layout thực tế đúng `JarLauncher`/`WarLauncher`, `BOOT-INF`/`WEB-INF`?
9. **Cổng/context:** Endpoint được kiểm thử theo route standalone hoặc context path external container?
10. **Quy trình vá lỗi:** Ai chịu trách nhiệm cập nhật Tomcat/JDK? Có khả năng rollback độc lập không?
11. **Resource và log:** Có xung đột shared logging, JDBC, JNDI, connector hay class loader không?
12. **CI/CD:** Build/test và smoke test trên **đúng đường triển khai sản xuất**?
13. **Độ quan sát:** Health/metrics/logging và alerting phù hợp với JVM/app/container?
14. **Rủi ro migration:** Nếu đang từ hệ thống WAR cũ sang Boot, có thể chia lộ trình traditional WAR → executable WAR → JAR nếu yêu cầu vận hành cho phép.

### Tài liệu chính thức

- [Spring Boot 3.5 — Traditional Deployment](https://docs.spring.io/spring-boot/3.5/how-to/deployment/traditional-deployment.html)
- [Spring Boot 3.5 — System Requirements (Java và Servlet containers)](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html)
- [Spring Boot 3.5 — Maven Packaging Executable Archives](https://docs.spring.io/spring-boot/3.5/maven-plugin/packaging.html)
- [Spring Boot 3.5 — Gradle BootWar API](https://docs.spring.io/spring-boot/3.5/gradle-plugin/api/java/org/springframework/boot/gradle/tasks/bundling/BootWar.html)
- [Spring Boot 3.5 — SpringBootServletInitializer API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/support/SpringBootServletInitializer.html)

**Ghi nhớ:** **JAR + embedded server** là lựa chọn mặc định thuận tiện cho phần lớn ứng dụng Spring Boot mới. **WAR** nên có lý do rõ ràng — đặc biệt khi phải deploy lên **external servlet container**. Một **executable WAR** còn có thể chạy độc lập qua `java -jar` nhờ `WarLauncher` và `WEB-INF/lib-provided`, nhưng không làm mất yêu cầu kiểm thử thật trên container ngoài.

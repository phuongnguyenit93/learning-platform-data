# Triển khai trên Servlet container và phân biệt WAR với máy chủ nhúng

## 1. Bài toán: ứng dụng Spring MVC thực sự chạy ở đâu?

Spring MVC xử lý request HTTP thông qua **Servlet API**, nhưng mã ứng dụng không tự mở socket và thực thi giao thức HTTP. Một **Servlet container** (ví dụ Apache Tomcat hoặc Jetty) nhận kết nối, tạo request/response, quản lý vòng đời Servlet/Filter và gọi `DispatcherServlet` của Spring MVC để điều phối đến controller.

Có hai kiểu triển khai phổ biến:

1. **Máy chủ nhúng (embedded server)**: ứng dụng Spring Boot đóng gói thành executable JAR và tự khởi động Tomcat/Jetty khi chạy `java -jar`. Tiến trình Java của ứng dụng sở hữu máy chủ HTTP và vòng đời của nó.
2. **Servlet container bên ngoài (external/traditional container)**: người vận hành khởi động Tomcat/Jetty trước; ứng dụng được đóng gói thành **WAR** và triển khai vào container đó. Container quản lý web application, context path và vòng đời Servlet theo hợp đồng triển khai.

Chúng có thể phục vụ cùng một REST endpoint và cùng sử dụng Spring MVC. Điểm khác nhau nằm ở **cách khởi động, đóng gói phụ thuộc, quyền quản lý cổng HTTP, context path và vận hành**.

```text
Cách A — Spring Boot executable JAR + Tomcat nhúng

shell / systemd / container runtime
             |
             v
     java -jar app.jar
             |
             v
  SpringApplication.run(...)
             |
             v
 ApplicationContext + Tomcat nhúng
             |
             v
    DispatcherServlet -> Controller

Cách B — WAR trên Tomcat bên ngoài

shell / systemd / container runtime
             |
             v
        Start Tomcat
             |
             v
   Tomcat deploy app.war
             |
             v
   SpringBootServletInitializer
             |
             v
 ApplicationContext + DispatcherServlet
             |
             v
          Controller
```

**Quan trọng:** Spring MVC là web framework; **Servlet container** là môi trường phục vụ request; **WAR/JAR** là dạng artifact. “WAR” không đồng nghĩa “Spring MVC cũ”; một WAR cấu hình đúng vẫn có thể chạy bằng Spring Boot hiện đại.

## 2. Servlet container chịu trách nhiệm gì?

Servlet container triển khai Jakarta Servlet specification và cung cấp môi trường chạy cho một hoặc nhiều web application. Những trách nhiệm chính:

- Mở listener HTTP/HTTPS, nhận request và chuyển thành `HttpServletRequest`/`HttpServletResponse`.
- Tạo và quản lý `ServletContext`, các Servlet, Filter, Listener theo vòng đời triển khai.
- Xử lý request mapping cấp Servlet, dispatcher type, session, timeout, async servlet và các yêu cầu khác trong phạm vi đặc tả Servlet.
- Phân vùng ứng dụng theo **context path** (chẳng hạn `/shop` và `/admin`), thường sử dụng classloader ứng dụng riêng.
- Khi undeploy/redeploy, dừng web application, giải phóng resource trong phạm vi có thể và nạp phiên bản mới. Các kết nối, thread hoặc static state do ứng dụng quản lý sai vẫn có thể gây rò rỉ tài nguyên.

Spring MVC bổ sung tầng điều phối:

```text
HTTP request
    |
    v
Servlet container
    |
    v
Filter chain
    |
    v
DispatcherServlet (một Servlet của Spring MVC)
    |
    +--> HandlerMapping
    +--> HandlerAdapter -> @Controller / @RestController
    +--> MessageConverter / ViewResolver
    +--> ExceptionResolver
    |
    v
HTTP response
```

Bản thân `DispatcherServlet` không thay thế container: nó là thành phần **được đăng ký trong container**, dù container được nhúng hay do một máy chủ khác khởi động.

## 3. Embedded server là gì?

Máy chủ nhúng là **thư viện Servlet container nằm trong dependency/runtime của ứng dụng** và được tạo khi tiến trình ứng dụng chạy.

Với Spring Boot 3.5:

- `spring-boot-starter-web` thường kéo theo `spring-boot-starter-tomcat` theo mặc định.
- Spring Boot auto-configuration tạo `ServletWebServerApplicationContext` và dùng `ServletWebServerFactory` phù hợp để khởi động Tomcat/Jetty/Undertow nhúng.
- `SpringApplication.run(...)` tạo application context, đăng ký DispatcherServlet cùng Servlet/Filter/Listener, rồi máy chủ phục vụ request.
- `server.port`, `server.address`, `server.servlet.context-path` và những cấu hình server khác điều khiển **server nhúng** theo khả năng được hỗ trợ.

Ví dụ cấu hình:

```yaml
# src/main/resources/application.yml
server:
  port: 8085
  servlet:
    context-path: /catalog
```

Với executable JAR có controller `@GetMapping("/books")`, endpoint bên ngoài là `http://localhost:8085/catalog/books`. Context path `/catalog` thuộc Servlet context, còn `/books` là đường dẫn controller.

Ưu điểm thực tế: artifact dễ chạy, mỗi ứng dụng tự chủ version container và dependency, có thể đóng gói thành container image hoặc chạy bằng service manager; mở rộng quy mô bằng cách chạy thêm instance sau load balancer. Điều này **không buộc** mọi hệ thống phải dùng microservice.

Hạn chế cần quản trị: mỗi tiến trình có resource/cổng/server lifecycle riêng; vận hành phải chuẩn hóa cấu hình, logs, shutdown, health checks và cập nhật bản vá bảo mật của container nhúng qua phiên bản dependency/build.

## 4. WAR và external Servlet container là gì?

**WAR (Web Application Archive)** là gói web application theo cấu trúc Java/Jakarta EE được Servlet container hiểu. Với triển khai truyền thống:

1. Build file `app.war`.
2. Đưa artifact tới khu vực deployment của Tomcat/Jetty hoặc dùng công cụ deploy của server.
3. Container phát hiện gói, thiết lập web application context, load class/resources và khởi tạo Spring MVC.
4. Request tới context path của WAR được chuyển qua filter chain tới `DispatcherServlet`.

Tomcat có thể chạy nhiều WAR cùng tiến trình, ví dụ:

```text
Tomcat process (HTTP :8080)
  |
  +-- /shop    -> shop.war    -> Spring MVC app A
  |
  +-- /admin   -> admin.war   -> Spring MVC app B
  |
  +-- /reports -> reports.war -> Spring MVC app C
```

Mỗi WAR thường có web application classloader riêng và ServletContext riêng. Tuy nhiên chúng vẫn **chia sẻ cùng JVM/container process**: CPU, memory, thread capacity, các chính sách container, cổng và rủi ro ảnh hưởng lẫn nhau. Vì vậy “nhiều WAR trong một Tomcat” không tự có mức cô lập bằng nhiều tiến trình/container độc lập.

Ưu điểm: phù hợp tổ chức có nền tảng Java application server do đội vận hành quản lý, triển khai/redeploy ứng dụng vào server hiện hữu, dùng các chính sách container chung. Đánh đổi: phải quản lý compatibility giữa WAR và container, cấu hình deployment, classloader, shared libraries và vòng đời server; nâng cấp container ảnh hưởng nhiều ứng dụng trên cùng instance.

**WAR không có nghĩa là tất cả thư viện đều được container cung cấp.** Container thường cung cấp Servlet API và implementation container; các dependency nghiệp vụ, Spring Framework và phần lớn dependency của ứng dụng vẫn được đóng gói trong WAR. Chính xác cái nào dùng `provided` cần quyết định theo hợp đồng môi trường đích.

## 5. So sánh executable JAR, deployable WAR và executable WAR

| Tiêu chí | Executable JAR + server nhúng | WAR trên container ngoài | Executable WAR của Spring Boot |
| --- | --- | --- | --- |
| Ai bắt đầu server HTTP? | `main`/Spring Boot của ứng dụng | Tomcat/Jetty bên ngoài | Khi `java -jar`: Spring Boot; khi deploy: container ngoài |
| Artifact | `.jar` có Boot loader và dependencies | `.war` có cấu trúc web application | `.war` được Spring Boot repackaging |
| Lệnh/mô hình | `java -jar app.jar` | Deploy WAR theo server, khởi động server | `java -jar app.war` **hoặc** deploy WAR |
| Servlet container runtime | Được đóng gói cho execution | Do server bên ngoài cung cấp | `WEB-INF/lib-provided` cho execution; bên ngoài dùng container của server |
| HTTP port | Thường từ `server.port` | Do container ngoài cấu hình | Phụ thuộc mode chạy |
| Context path | `server.servlet.context-path` của server nhúng | Thường do deployment/context của server quyết định | Phụ thuộc mode chạy |
| Độc lập tiến trình | Một app thường một JVM/process | Nhiều WAR có thể chung JVM | Tùy mode |
| Nâng cấp container | Cập nhật dependency và rebuild artifact | Đội vận hành nâng cấp server | Mode nào dùng container đó |
| Rủi ro vận hành cần kiểm | JVM/process, port, build image và lifecycle | Shared server, classloading, context path, server patch | Phải kiểm thử **cả hai mode** nếu hỗ trợ cả hai |

**Phân biệt quan trọng:** WAR là **format**; embedded/external là **mode chạy**. Spring Boot có thể xây **executable WAR** triển khai vào Tomcat ngoài và cũng chạy được bằng `java -jar app.war` khi dependency container được đóng gói đúng.

## 6. Cấu trúc đóng gói và classpath

Một Spring Boot executable JAR thường có dạng:

```text
catalog.jar
├── META-INF/MANIFEST.MF
├── BOOT-INF/
│   ├── classes/             # class và resource của ứng dụng
│   └── lib/                 # dependencies
└── ...                      # Spring Boot loader
```

WAR triển khai lên Servlet container có cấu trúc cơ bản:

```text
catalog.war
├── META-INF/
└── WEB-INF/
    ├── classes/             # class và resource của ứng dụng
    ├── lib/                 # thư viện chạy trong external container
    └── lib-provided/        # phần Boot executable WAR, nếu có
```

`WEB-INF/lib-provided` là chi tiết hữu ích của **executable WAR do Spring Boot plugin đóng gói**, không phải yêu cầu chung của mọi WAR: nó cho phép `java -jar catalog.war` tìm được embedded Tomcat, trong khi external Servlet container không đưa thư viện ở thư mục này vào ứng dụng theo cách thông thường.

Nếu nhét Tomcat embedded implementation vào `WEB-INF/lib` khi deploy WAR lên Tomcat ngoài, có thể xảy ra trùng implementation, sai classloader hoặc xung đột dependency. Trong Maven, đặt starter Tomcat ở scope `provided`; Spring Boot plugin vẫn có thể đóng gói vào `lib-provided` cho executable WAR. Ở Gradle, dùng cấu hình `providedRuntime` phù hợp với plugin WAR/Boot.

**Không nhầm** `provided` với “không cần Servlet API lúc biên dịch”: application vẫn cần compile classpath có API thích hợp. Ý nghĩa là dependency đó do môi trường chạy **bên ngoài** cung cấp khi deploy WAR.

## 7. Ví dụ hoàn chỉnh: một codebase chạy WAR trên Tomcat ngoài hoặc trực tiếp bằng java -jar

Ví dụ sử dụng **Java 17+, Spring Boot 3.5.16, Maven 3.6.3+ và Tomcat 10.1**. Đây là một tổ hợp tương thích trong dòng Boot 3.5: Spring Framework 6.x dùng `jakarta.servlet.*`, Tomcat 10.1 triển khai Jakarta Servlet 6.0. Người đọc không phải tự cài Servlet API bằng một JAR rời.

**Cấu trúc dự án:**

```text
deploy-demo/
├── pom.xml
└── src/main/java/example/deploy/
    ├── DeployDemoApplication.java
    └── HelloController.java
```

### 7.1. Maven pom.xml: packaging WAR và Tomcat provided

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

    <groupId>example</groupId>
    <artifactId>deploy-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
```

`spring-boot-starter-web` mang Spring MVC và mặc định tham chiếu starter Tomcat. Khai báo trực tiếp `spring-boot-starter-tomcat` với `provided` khiến container implementation không nằm trong dependency runtime tiêu chuẩn khi deploy vào container ngoài. Parent và Boot Maven Plugin xử lý đóng gói executable WAR phù hợp.

### 7.2. Application class và điểm khởi động thứ hai

**`src/main/java/example/deploy/DeployDemoApplication.java`:**

```java
package example.deploy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class DeployDemoApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder builder) {
        return builder.sources(DeployDemoApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(DeployDemoApplication.class, args);
    }
}
```

Hai entry point có vai trò khác nhau:

- **Chạy trực tiếp `java -jar`:** `main(String[])` được Spring Boot launcher gọi và khởi động SpringApplication cùng embedded Tomcat.
- **Deploy lên Tomcat ngoài:** container tích hợp với Servlet `WebApplicationInitializer`; `SpringBootServletInitializer` đóng vai trò bridge để tạo Spring ApplicationContext từ lifecycle của Servlet container. `configure(SpringApplicationBuilder)` xác định source configuration.

`SpringBootServletInitializer` là kiểu hỗ trợ **traditional WAR deployment**. Với executable JAR thông thường, không cần kế thừa class này; để nguyên trong một codebase dùng cả hai mode cũng được.

### 7.3. Controller không cần biết loại packaging

**`src/main/java/example/deploy/HelloController.java`:**

```java
package example.deploy;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello from Spring MVC";
    }

    @GetMapping("/servlet")
    public String servlet(HttpServletRequest request) {
        int major = request.getServletContext().getMajorVersion();
        int minor = request.getServletContext().getMinorVersion();
        return "Servlet " + major + "." + minor;
    }
}
```

Controller tương tự trong cả hai deployment mode. `HttpServletRequest` là kiểu **Jakarta** nên tương thích Spring 6/Tomcat 10.1. Endpoint `/servlet` lấy phiên bản đặc tả Servlet do container runtime công bố.

### 7.4. Build và chạy WAR ở chế độ nhúng

Đứng tại thư mục có `pom.xml`:

```bash
java -version
mvn -version
mvn clean package
java -jar target/deploy-demo-0.0.1-SNAPSHOT.war
```

Chạy thử bằng terminal khác:

```bash
curl -s http://localhost:8080/hello
curl -s http://localhost:8080/servlet
```

Output body với Tomcat 10.1 nhúng mặc định của Boot 3.5:

```text
Hello from Spring MVC
Servlet 6.0
```

Hai dòng là kết quả **của hai lệnh `curl` liên tiếp**, không phải một response chung. Dùng `curl.exe` trong PowerShell nếu alias `curl` không hoạt động như mong muốn.

Vì artifact là executable WAR được Boot repackaging, `java -jar ...war` được hỗ trợ; đây là tính năng của Spring Boot build plugin, không áp dụng mặc định cho mọi WAR thuần Java.

### 7.5. Deploy cùng WAR lên Tomcat 10.1 bên ngoài

Giả sử bạn đã cài **Tomcat 10.1** và chạy nó trên Java 17+. Tắt instance nhúng ở `:8080` trước để tránh tranh cổng. Các bước trên một Tomcat local tiêu chuẩn:

1. Build `mvn clean package` và lấy `target/deploy-demo-0.0.1-SNAPSHOT.war`.
2. Đặt vào `$CATALINA_BASE/webapps/catalog.war`, hoặc sử dụng giao diện/cơ chế deploy chính thức của container. `CATALINA_BASE` là đường dẫn cấu hình instance Tomcat (không nhất thiết trùng `CATALINA_HOME`).
3. Khởi động Tomcat bằng script được cung cấp (ví dụ `bin/catalina.sh run` trên Linux/macOS hoặc `bin\catalina.bat run` trên Windows), tùy cấu hình instance.
4. Kiểm tra log triển khai; nếu context path mặc định xuất phát từ tên WAR là `catalog` và Tomcat lắng nghe tại `:8080`, gọi:

```bash
curl -s http://localhost:8080/catalog/hello
curl -s http://localhost:8080/catalog/servlet
```

Output body dự kiến:

```text
Hello from Spring MVC
Servlet 6.0
```

Tại sao URL ở chế độ này có `/catalog`? Với cơ chế auto-deploy tiêu chuẩn của Tomcat, WAR `catalog.war` thường được triển khai dưới context path `/catalog`. Nếu deploy thành `ROOT.war` hoặc định nghĩa context descriptor/virtual host khác, đường dẫn thay đổi theo cấu hình container. Không hardcode `/catalog` vào `@GetMapping` chỉ để “đi theo WAR”.

Cổng `8080` trong ví dụ WAR bên ngoài thuộc **Tomcat config**. Nếu đặt `server.port=8085` trong Spring Boot application properties của WAR, bạn không nên kỳ vọng nó thay cổng lắng nghe của Tomcat ngoài; cổng thuộc container đích.

### 7.6. Cùng controller nhưng chuyển về executable JAR

Khi chỉ muốn chạy embedded Tomcat qua executable JAR, thay phần packaging trong `pom.xml` thành:

```xml
<packaging>jar</packaging>
```

Đồng thời xóa dependency `spring-boot-starter-tomcat` có `scope` là `provided`, giữ `spring-boot-starter-web` với Tomcat ở runtime bình thường. Class `DeployDemoApplication` vẫn biên dịch và chạy được (dù `SpringBootServletInitializer` khi đó không cần thiết). Sau đó:

```bash
mvn clean package
java -jar target/deploy-demo-0.0.1-SNAPSHOT.jar
```

Với server mặc định `:8080`, `/hello` vẫn trả:

```text
Hello from Spring MVC
```

Sự khác biệt nằm ở cách đóng gói/container lifecycle. Endpoint Spring MVC và business logic không cần chỉnh theo loại artifact nếu chúng không phụ thuộc cấu hình deployment.

## 8. Nếu dùng Gradle thay vì Maven

Ví dụ ý tưởng cho Spring Boot **3.5** với Gradle Groovy DSL, giữ phần `repositories`, plugin versions và cấu hình Java theo dự án đang dùng:

```groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
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
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
```

Với WAR plugin và Boot plugin, task `bootWar` tạo executable WAR:

```bash
./gradlew bootWar
java -jar build/libs/deploy-demo-0.0.1-SNAPSHOT.war
```

Tên artifact cụ thể chịu ảnh hưởng cấu hình project name/archive name, nên xác minh dưới `build/libs` trước khi chạy. Để làm executable JAR thay vì WAR, cấu hình Java/Boot phù hợp, bỏ `war`/`providedRuntime`, sử dụng `bootJar` và giữ Tomcat mặc định ở runtime.

**Không thay `providedRuntime` bằng `compileOnly` theo thói quen**: dependency chỉ `compileOnly` có thể biến mất khỏi test runtime classpath, làm test web tích hợp không chạy được; `providedRuntime` dành cho trường hợp external runtime cung cấp container và Boot vẫn cần tạo executable WAR.

## 9. Vì sao WAR cần SpringBootServletInitializer nhưng JAR thường không cần?

Đây là vấn đề **ai kích hoạt Spring ApplicationContext**:

```text
Executable JAR / executable WAR qua java -jar
    |
    +--> main(String[])
          |
          +--> SpringApplication.run(...)
                |
                +--> tạo ApplicationContext và embedded Servlet container


External Tomcat deploy WAR
    |
    +--> tìm Servlet WebApplicationInitializer
          |
          +--> SpringBootServletInitializer.configure(...)
                |
                +--> tạo ApplicationContext trong ServletContext có sẵn
                      |
                      +--> đăng ký DispatcherServlet/Filter beans
```

Khi container bên ngoài đã cung cấp `ServletContext` và listener HTTP, Spring không nên tự tạo một Tomcat thứ hai. Tương tự, khi chạy embedded server thì Spring Boot phải tạo container để request đi vào.

Nếu một Spring MVC app **không dùng Spring Boot**, người viết vẫn có thể tạo WAR và đăng ký `DispatcherServlet` bằng `web.xml` hoặc cấu hình Java như `AbstractAnnotationConfigDispatcherServletInitializer`. `SpringBootServletInitializer` là công cụ riêng của **Spring Boot** giúp nối mô hình WAR truyền thống với `SpringApplication`.

**Không phải mọi ứng dụng `@SpringBootApplication` đều triển khai được dưới external Servlet container chỉ bằng cách đổi đuôi `.jar` thành `.war`.** Cần thực sự tạo WAR đúng cấu trúc, đúng initializer, đúng scope container dependency và tương thích phiên bản runtime.

## 10. Tương thích Spring / Jakarta Servlet / JDK / container

Servlet container và WAR phải dùng **cùng họ API mà Spring yêu cầu**.

| Tổ hợp minh họa | Servlet API/namespace | Điều kiện chính |
| --- | --- | --- |
| Spring Boot 2.7 / Spring Framework 5.3 + Tomcat 9 | Servlet 4.0, `javax.servlet.*` | Dòng cũ dùng Java EE/`javax`. |
| Spring Boot 3.5 / Spring Framework 6.2 + Tomcat 10.1 | Servlet 6.0, `jakarta.servlet.*` | Java 17+ cho Boot 3.5; container triển khai Jakarta Servlet 6.0. |
| Spring Boot 3.5 deploy lên container Servlet 5.0+ khác | `jakarta.servlet.*` | Spring Boot 3.5 tuyên bố có thể triển khai tới Servlet 5.0+ compatible container; vẫn phải kiểm tra server/vendor/version cụ thể. |

**Tomcat 9 không phù hợp với WAR Spring 6/Boot 3** vì Tomcat 9 cung cấp `javax.servlet`, trong khi Spring 6 cần `jakarta.servlet`. Đây là thay đổi package/type ở mức biên dịch và bytecode; không thể giải quyết bằng việc chỉ nâng Java hay thêm cả hai Servlet API JAR.

**Java version tối thiểu** không chỉ do Tomcat quyết định. Spring Boot 3.5.16 yêu cầu Java 17+. Máy chạy external Tomcat phải đáp ứng **mức cao nhất** của server, application và libraries. Dự án build bằng Java 21 mà production JVM chỉ có Java 17 có thể gặp `UnsupportedClassVersionError` nếu không cấu hình compiler target phù hợp.

Các container hỗ trợ theo tài liệu Spring Boot 3.5.16 cho embedded mode gồm **Tomcat 10.1 (Servlet 6.0)**, **Jetty 12.0 (Servlet 6.0)** và **Undertow 2.3 (Servlet 6.0)**. Không suy rộng các version này sang Spring Boot 4.x mà không đọc tài liệu thế hệ mới.

## 11. Context path, port, profile và cấu hình theo môi trường

### Context path

- **Executable JAR/embedded container:** thường điều khiển bằng `server.servlet.context-path=/catalog`, cộng với các mapping ở controller.
- **WAR ngoài Tomcat:** context path thường do tên WAR, context descriptor hoặc cấu hình deployment của container quyết định. Không nên coi thuộc tính `server.servlet.context-path` là nguồn chân lý cho context path của external container.
- **Reverse proxy:** có thể xuất bản app ra `https://site.example/catalog`, trong khi container nội bộ có context khác. Cần phối hợp rewrite path, forwarded prefix và URL generation; WAR/JAR không tự giải quyết chuyện public URL.

### Port và listener

- **Embedded:** `server.port=8085` có thể đổi cổng listener của app khi bật embedded web server.
- **External:** Tomcat ngoài mở listener theo `conf/server.xml`, environment/container config hoặc tooling của instance đó; cấu hình port nằm ở tầng Tomcat, không thuộc từng WAR.
- Hai WAR trong cùng Tomcat chia sẻ HTTP listener nhưng thường có các context path khác nhau.

### Profile, environment và resource

`application.properties`/`application.yml`, Spring profiles và externalized configuration vẫn dùng được trong cả hai mode, nhưng nguồn cấu hình, environment variables, logging, filesystem và resource path do môi trường triển khai quyết định. Đừng dùng đường dẫn file tương đối như thể ứng dụng luôn được chạy từ thư mục chứa artifact.

Với WAR, JSP hay resource theo `ServletContext` có thể chịu hạn chế khác executable JAR. Tài liệu Spring Boot ghi rõ JSP **không được hỗ trợ trong executable JAR**; với Tomcat/Jetty, dùng WAR theo mode tương thích khi cần JSP. Các dự án REST trả JSON thường ít phụ thuộc JSP hơn.

## 12. Vận hành: deployment, scaling, shutdown và quan sát lỗi

### Triển khai và nâng cấp

**Executable JAR:** đưa artifact/container image mới vào một process/instance mới; dùng service manager/orchestrator hoặc script đáng tin cậy để điều khiển process. Rolling deployment thực hiện ở load balancer/orchestrator khi có nhiều instance.

**WAR trên external container:** deploy/undeploy/redeploy WAR trong instance Tomcat/Jetty theo cơ chế container; một Tomcat có thể đang phục vụ nhiều ứng dụng. Rollback cũng phải xét các dependency chia sẻ, cache và tài nguyên ngoài process.

Không nên hứa “redeploy WAR không gây gián đoạn” chỉ vì không khởi động lại Tomcat: request đang chạy, session, async jobs và resource của web application có thể bị ảnh hưởng, tùy strategy/container.

### Memory, thread, session, classloader

- Dùng nhiều WAR trong một JVM có thể tiết kiệm một phần overhead, nhưng các ứng dụng cùng cạnh tranh thread, heap, GC và native memory. Một WAR bị memory leak có thể ảnh hưởng toàn server.
- Mỗi embedded JAR thường có JVM/process riêng, giúp tách lỗi process và nâng cấp runtime độc lập; đổi lại tổng số process và mức tiêu thụ tài nguyên có thể tăng.
- HTTP session in-memory không tự chia sẻ giữa các JVM/instance. Khi scale ngang, cần đánh giá sticky sessions hoặc session store ngoài (ví dụ Spring Session) tùy yêu cầu.
- Đừng tạo thread, scheduler, connection pool hoặc singleton global không được hủy khi stop ứng dụng; WAR redeploy liên tục có thể gây classloader leak.

### Logs và health

Ở embedded mode, Spring Boot logs và lifecycle gắn trực tiếp với app process. Trong external mode, cần đọc **cả log container và log ứng dụng** (startup deployment, classloading, request mapping). Để làm readiness/liveness hoặc theo dõi metrics, nên sử dụng cơ chế health/observability phù hợp với môi trường; đừng nhầm “Tomcat process còn sống” với “tất cả WAR đang khỏe”.

## 13. Những lỗi triển khai thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra và hướng xử lý |
| --- | --- | --- |
| `java -jar app.war` báo thiếu main manifest/loader | WAR thuần chưa được Spring Boot repackaging thành executable archive | Kiểm tra Spring Boot build plugin, task/package và manifest. |
| WAR deploy nhưng endpoint 404 ở `/hello` | Context path không phải root | Thử `/catalog/hello` nếu deploy `catalog.war`; kiểm tra deployment log/context config. |
| `ClassNotFoundException: javax.servlet...` hoặc `jakarta.servlet...` | Spring/framework/library và Servlet container khác namespace/version | Đồng bộ Spring, Servlet API và container; tìm dependency cũ. |
| `NoSuchMethodError` / `LinkageError` lúc startup | Conflict giữa thư viện trong WAR và API/implementation container | Xem dependency tree, `WEB-INF/lib`, shared libs của server và version compatibility. |
| Tomcat ngoài đang nghe `:8080` dù cấu hình `server.port=9090` trong WAR | Cổng thuộc external container | Chỉnh connector/listener ở Tomcat thay vì trong WAR. |
| `Address already in use: bind` khi chạy executable JAR | Cổng embedded đã bị process khác dùng | Đổi `server.port` hoặc dừng process chiếm cổng. |
| WAR deploy không gọi `@SpringBootApplication` | Thiếu hoặc sai `SpringBootServletInitializer`/initializer discovery, gói không đúng | Kiểm tra class application, `configure`, packaging WAR và startup logs. |
| WAR startup bị `UnsupportedClassVersionError` | Production JVM thấp hơn bytecode Spring/app/dependency | Kiểm tra Java runtime của **Tomcat process** và target compiler. |
| REST chạy nhưng JSP không hiển thị trong JAR | Hạn chế JSP của executable JAR | Xem hướng dẫn Spring Boot; khi cần JSP với Tomcat/Jetty thường dùng WAR. |
| App chạy qua reverse proxy nhưng redirect sai host/HTTP | Forwarded headers và public URL chưa được cấu hình/trust đúng | Kiểm tra proxy, context path và forwarded-header strategy; không liên quan trực tiếp đuôi file artifact. |
| WAR redeploy nhiều lần tăng heap/class count | Thread/resource/classloader leak | Dừng thread executor, đóng pool/listener, xem memory/thread dump và Tomcat logs. |

### Lệnh chẩn đoán hữu ích

```bash
# Kiểm tra Java/Maven đang chạy build
java -version
mvn -version

# Đóng gói và xem những file vừa build
mvn clean package

# Xem cấu trúc archive không cần giải nén
jar tf target/deploy-demo-0.0.1-SNAPSHOT.war

# Tìm dependency Tomcat trong Maven tree
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-tomcat

# Gọi endpoint HTTP; không tự follow redirect
curl -i http://localhost:8080/hello
curl -i http://localhost:8080/catalog/hello
```

Hai lệnh `curl` cuối cùng minh họa **hai mode/contexts** khác nhau; không giả định cả hai phải trả HTTP 200 cùng lúc. Với một WAR ngoài Tomcat, nếu context không phải `/catalog` thì thay đường dẫn theo deployment thực tế.

Để kiểm tra chính xác artifact Maven đã chọn, có thể dùng `jar tf` tìm `WEB-INF/classes/`, `WEB-INF/lib/` và `WEB-INF/lib-provided/`; kiểm tra log Spring/Servlet container để biết initializer và context path đã được thiết lập hay chưa.

## 14. Khi nào nên chọn cách nào?

**Chọn executable JAR + embedded Tomcat** khi muốn một runtime thống nhất cùng artifact, container image/service độc lập, mở rộng instance linh hoạt hoặc không có yêu cầu sử dụng shared application server. Đây là đường đi phổ biến cho Spring Boot REST applications mới.

**Chọn WAR trên container ngoài** khi doanh nghiệp/hệ thống cần chuẩn triển khai WAR vào Tomcat/Jetty có sẵn, vận hành tập trung nhiều web app trong một server, hoặc có yêu cầu tích hợp Servlet deployment/JSP/classloader cụ thể. Cần ưu tiên test trên đúng container vendor và version đích.

**Chọn executable WAR** khi cần duy trì **cả hai cách** (deploy truyền thống và chạy riêng để kiểm thử/vận hành) với một artifact; kiểm chứng cả `java -jar .war` lẫn WAR deployment. Tránh giữ hai mode lâu dài nếu chỉ một mode được dùng, vì tăng số cấu hình và kịch bản phải kiểm thử.

Quyết định dựa trên tiêu chí thật: hợp đồng vận hành, isolation, quản lý JVM, yêu cầu JSP/WAR, quy trình deploy, cách scale, môi trường mạng và phiên bản Servlet container; không dựa vào giả định WAR luôn cũ còn JAR luôn mới.

## 15. Tự đánh giá kiến thức

**Câu 1.** Một executable JAR Spring Boot có dùng Servlet API không?  
**Trả lời:** Có, nếu ứng dụng là Spring Web MVC chạy trên Tomcat/Jetty/Undertow nhúng. Container nằm trong tiến trình ứng dụng nhưng vẫn triển khai Servlet API.

**Câu 2.** Vì sao khi deploy WAR cần `SpringBootServletInitializer`?  
**Trả lời:** Container ngoài đã được khởi động; initializer cung cấp cầu nối từ vòng đời Servlet deployment đến việc tạo Spring Boot ApplicationContext. Với `java -jar`, `main` làm việc khởi động.

**Câu 3.** Tại sao không để `spring-boot-starter-tomcat` ở runtime thông thường trong WAR?  
**Trả lời:** Container ngoài đã cung cấp Servlet implementation. Đánh dấu `provided`/`providedRuntime` giúp tránh đóng gói container runtime như dependency deploy thông thường; executable WAR của Boot có cơ chế `lib-provided` riêng.

**Câu 4.** Nếu WAR tên `catalog.war` và Tomcat lắng nghe `:8080`, controller map `/hello` thường được gọi tại đâu?  
**Trả lời:** Với Tomcat auto-deploy mặc định và không có cấu hình context khác: `http://localhost:8080/catalog/hello`. Context path do deployment quyết định.

**Câu 5.** Spring Boot 3.5 WAR có deploy lên Tomcat 9 được không nếu dùng Java 21?  
**Trả lời:** Không. Java 21 không sửa được bất đồng Jakarta Servlet: Tomcat 9 thuộc `javax.servlet`, Spring Boot 3.x dùng `jakarta.servlet`.

**Câu 6.** Một executable WAR chạy được bằng `java -jar` có tự chứng minh deploy lên Tomcat ngoài thành công không?  
**Trả lời:** Không. Mode ngoài có container version, context path, shared libraries và lifecycle khác; cần kiểm thử trên đúng container đích.

## 16. Nguồn tham khảo chính thức

- [Spring Boot 3.5 — Traditional Deployment](https://docs.spring.io/spring-boot/3.5/how-to/deployment/traditional-deployment.html): `SpringBootServletInitializer`, `<packaging>war</packaging>`, Maven `provided`, Gradle `providedRuntime` và executable WAR.
- [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): lựa chọn Tomcat/Jetty/Undertow và cấu hình server.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): mô hình Servlet, DispatcherServlet và giới hạn JSP.
- [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html): JDK, phiên bản Servlet container và khả năng deploy.
- [SpringBootServletInitializer API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/support/SpringBootServletInitializer.html): bridge giữa traditional WAR và SpringApplication.
- [Spring Boot 3.5 — Running Your Application](https://docs.spring.io/spring-boot/3.5/reference/using/running-your-application.html): chạy artifact và vòng đời ứng dụng.
- [Apache Tomcat — Which Version?](https://tomcat.apache.org/whichversion.html): đối chiếu Tomcat và Servlet/Jakarta EE.

**Điểm ghi nhớ:** controller Spring MVC có thể giữ nguyên khi đổi deployment mode, nhưng phải xác định rõ **ai tạo Servlet container, ai quản lý cổng/context path và classpath nào được sử dụng trong artifact so với runtime thực tế**.
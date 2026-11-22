# SpringBootServletInitializer và ứng dụng Servlet trong container bên ngoài

## 1. Mục đích và bối cảnh

Spring Boot có thể chạy theo hai mô hình web runtime khác nhau:

- **Đóng gói executable JAR/WAR:** lệnh `java -jar` gọi `main()`, Spring Boot tạo embedded Tomcat, Jetty hoặc Undertow và tự quản lý cổng HTTP.
- **Triển khai WAR vào Servlet container bên ngoài:** Tomcat hoặc application server đã chạy nhận một file `.war`, tạo `ServletContext` cho webapp rồi khởi động Spring Boot qua Servlet initialization lifecycle. Trong chế độ này, external container **không gọi phương thức `main()`**.

`SpringBootServletInitializer` là lớp hỗ trợ của Spring Boot cho **traditional WAR deployment**. Nó nối vòng đời khởi tạo `ServletContext` với `SpringApplication` để tạo `WebApplicationContext`, `DispatcherServlet` và các Servlet/Filter được đăng ký trong ứng dụng.

Bài học thuộc nhóm **Triển khai ứng dụng** của module **Spring Boot - web-runtime**, dùng Java 17+, Spring Boot 3.5.16, Spring MVC và Tomcat 10.1. Ví dụ cho phép cùng một mã nguồn vừa chạy bằng `java -jar ...war`, vừa triển khai thành `catalog.war` trong external Tomcat và so sánh HTTP paths/headers/runtime.

**Một lớp initializer không đủ để biến JAR thành WAR:** phải dùng WAR packaging, dependency scope phù hợp, Jakarta Servlet compatibility, đúng entrypoint và kiểm thử external server thật.

### Kết quả cần đạt

Sau bài học, bạn có thể giải thích:

1. Vì sao Servlet container không gọi `main()` và ai gọi `SpringBootServletInitializer.configure(...)`.
2. Vì sao `spring-boot-starter-tomcat` cần `provided` trong Maven WAR và `providedRuntime` trong Gradle.
3. Khác biệt của `WEB-INF/lib`, `WEB-INF/lib-provided` và WAR executable.
4. Context path đến từ tên WAR/container; `server.port` không thay đổi cổng Tomcat bên ngoài.
5. Cách đăng ký `ServletRegistrationBean`, `FilterRegistrationBean`, tránh trùng với `web.xml`/annotations.
6. Java/Jakarta Servlet versions, Spring Boot BOM, Spring MVC vs WebFlux và vendor exceptions.
7. Chiến lược test từ JUnit/MockMvc đến real embedded HTTP và **external WAR smoke test**.
8. Security, TLS, sessions, secrets, classloader, redeploy và health checks khi một JVM chạy nhiều WAR.

## 2. Ba loại artifact và entrypoint

| Thuộc tính | Executable JAR | Executable WAR qua `java -jar` | WAR trên container bên ngoài |
| --- | --- | --- | --- |
| File | `.jar` | Spring Boot-repackaged `.war` | Deployable `.war` |
| Entrypoint | `main()` | `main()` | Servlet initializer `onStartup` |
| HTTP server | Boot tạo embedded server | Boot tạo embedded server | Tomcat/application server tạo sẵn |
| Port | `server.port` | `server.port` | External connector (`server.xml`, platform) |
| Context path | `server.servlet.context-path` | Tương tự embedded JAR | Deployment context của WAR |
| Server dependencies | Trong JAR | Boot launcher có thể dùng `lib-provided` | Container cung cấp Servlet engine |
| Servlet API | Application runtime | Launcher/provided dependencies | Jakarta Servlet của container |
| JVM | Thường một process per app | Thường một process per app | Có thể nhiều WAR cùng JVM |
| Startup failure | Process có thể fail | Process có thể fail | WAR fail nhưng container vẫn chạy |
| Cần test | Functional + HTTP + E2E | Artifact/executable HTTP | **Container-specific WAR deployment** |

Một executable WAR là lựa chọn hữu ích khi cần cùng artifact chạy cả standalone lẫn external. Với Spring Boot build plugin và Tomcat `provided`, những dependencies của embedded servlet container được đặt trong `WEB-INF/lib-provided`. Khi chạy `java -jar`, Boot launcher có thể nạp chúng; khi external Tomcat triển khai WAR, webapp dùng những thư viện ứng dụng trong `WEB-INF/lib` và Servlet engine do server cung cấp.

**Không kết luận external deploy hoạt động chỉ từ `java -jar` chạy thành công.** Phần launcher/classloader/Servlet startup khác nhau.

### Khi nên chọn executable JAR

- Mỗi service triển khai như một process/container image riêng.
- App owner muốn tự quyết định embedded server version, flags và runtime.
- Đơn giản hóa blue/green, rolling update, rollback từng ứng dụng.
- Không có yêu cầu vận hành WAR hoặc Servlet application server sẵn có.

### Khi traditional WAR phù hợp

- Platform team quản trị Tomcat/application server tập trung.
- Có quy trình vận hành hoặc compliance chỉ chấp nhận WAR.
- Cần tích hợp legacy Servlet/JSP/JNDI hoặc ứng dụng Java EE/Jakarta EE đã tồn tại.
- Nhiều webapps được triển khai theo chính sách chung của container.

WAR không tự tạo security isolation mạnh: classloader riêng nhưng vẫn có thể dùng chung JVM heap, GC, process state và các resources của server.

## 3. SpringBootServletInitializer nằm ở đâu trong Servlet lifecycle?

Đúng tên lớp Spring Boot 3.5:

```java
org.springframework.boot.web.servlet.support.SpringBootServletInitializer
```

`SpringBootServletInitializer` implements `org.springframework.web.WebApplicationInitializer`. Spring Framework tích hợp với `ServletContainerInitializer` thông qua `SpringServletContainerInitializer`. Khi Servlet container xử lý WAR startup, nó tìm và gọi các WebApplicationInitializer phù hợp. Boot initializer tạo `SpringApplication`/`WebApplicationContext` dựa trên `SpringApplicationBuilder`.

### Sơ đồ hai đường khởi động

```text
EXECUTABLE MODE
java -jar target/servlet-war-demo-1.0.0.war
       |
       v
public static void main(String[] args)
       |
       v
SpringApplication.run(...)
       |
       v
Boot-managed embedded Tomcat
       |
       v
DispatcherServlet, Filters, application beans
       |
       v
http://localhost:8088/api/hello/Ada


EXTERNAL WAR MODE
Existing Tomcat -> deploy webapps/catalog.war
       |
       v
ServletContainerInitializer / SpringServletContainerInitializer
       |
       v
SpringBootServletInitializer.onStartup(ServletContext)
       |
       v
configure(SpringApplicationBuilder) -> SpringApplication
       |
       v
WebApplicationContext / Servlet registrations
       |
       v
http://localhost:8080/catalog/api/hello/Ada
```

Đây là luồng khái niệm; Servlet spec, container và Spring điều phối thứ tự callbacks thực tế. **`main()` không chạy khi external container deploy WAR theo cơ chế thông thường.**

### Mẫu Java tối thiểu

```java
package com.example.wardeploy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class ServletWarApplication
        extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder builder) {
        return builder.sources(ServletWarApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(ServletWarApplication.class, args);
    }
}
```

Class trên là Java hợp lệ, nhưng muốn chạy cần dependencies và `pom.xml` ở mục 9. Hai entrypoints chọn cùng `ServletWarApplication.class`.

**Không làm như sau:** trong `configure`, gọi `SpringApplication.run(...)` rồi trả builder. `configure` có trách nhiệm **chuẩn bị** builder, Boot quản lý thời điểm start; tự chạy app trong callback có thể tạo context và Servlet registrations lặp.

### Không nhất thiết luôn override `configure`

JavaDoc Boot 3.5 nói có thể override `configure` hoặc dùng initializer cũng là configuration source. Dạng explicit `builder.sources(MyApplication.class)` vẫn dễ hiểu, dễ kiểm tra và là cách được hướng dẫn rộng rãi. Nếu cần customizations dùng cho cả hai chế độ, có thể trích method chung:

```java
@SpringBootApplication
public class AlternateWarApp extends SpringBootServletInitializer {

    private static SpringApplicationBuilder customize(
            SpringApplicationBuilder b) {
        return b.sources(AlternateWarApp.class)
                .bannerMode(org.springframework.boot.Banner.Mode.OFF);
    }

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder builder) {
        return customize(builder);
    }

    public static void main(String[] args) {
        customize(new SpringApplicationBuilder()).run(args);
    }
}
```

Đây là **snippet phương án thay thế**, không thêm đồng thời vào demo. Với các cấu hình riêng môi trường (profiles, credentials, URL), ưu tiên externalized configuration và test từng đường chạy; đừng hardcode production secrets vào class.

## 4. Điều kiện tương thích của Spring Boot 3.5.16

Spring Boot 3.5.16 cần **Java 17 trở lên**, Spring Framework **6.2.19 trở lên** theo ma trận chính thức. Các embedded Servlet runtimes được hỗ trợ ở thế hệ Servlet 6.0 gồm Tomcat 10.1, Jetty 12.0 và Undertow 2.3. Tài liệu cũng cho biết có thể deploy Boot WAR vào **Servlet 5.0+ compatible container**; tuy vậy vendor-specific configuration còn phải được xác minh.

| Yếu tố | Yêu cầu/lựa chọn |
| --- | --- |
| JDK cho lab | Java 17 |
| Spring Boot | 3.5.16 qua BOM/parent |
| Servlet namespace | `jakarta.servlet.*` |
| External lab container | Tomcat 10.1 / Jakarta Servlet 6.0 |
| Servlet minimum theo Boot 3.5 | Servlet 5.0+ compatible external container |
| Web runtime trong lab | Spring MVC, Servlet |
| WAR startup | `SpringBootServletInitializer` |
| Platform test | Phải dùng đúng external server/version thực tế |

Mã Boot 3.5 đúng namespace:

```java
import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
```

Imports legacy `javax.servlet.Filter` hoặc `javax.servlet.http.HttpServlet` thuộc thời Java EE cũ, không dùng trực tiếp với Tomcat 10.1/Boot 3.5. **Tomcat 9 dùng javax Servlet 4.0**, không phải container tương thích cho Boot 3.5 WAR. Khi migrate Boot 2 sang Boot 3, cần nâng tất cả dependencies liên quan Servlet/JSP/JSTL/JAX-RS, Spring Security và server.

**Một server đáp ứng Servlet API version chưa bảo đảm mọi JSP, JNDI, WebSocket, logging, security realm hay classloader configuration đều tương thích.** Tài liệu vendor và smoke test trên đúng server là bắt buộc với ứng dụng phức tạp.

### WebFlux không phải use case mặc định của WAR này

Spring Boot 3.5 traditional deployment guide nói **Spring WebFlux server không hỗ trợ traditional WAR deployment**. MVC WAR có thể dùng `WebClient` để gọi outbound HTTP; điều đó không biến inbound runtime thành WebFlux server. Nếu muốn reactive server, chọn mô hình triển khai phù hợp Reactor Netty thay vì dùng initializer Servlet như giải pháp chung.

## 5. Maven WAR packaging: ba điểm cốt lõi

### (1) Đặt `<packaging>war</packaging>`

```xml
<packaging>war</packaging>
```

Khi không khai báo, Maven thường đóng JAR. WAR có cấu trúc cho Servlet container (`WEB-INF/classes`, `WEB-INF/lib`, descriptors nếu cần).

### (2) Giữ Spring MVC starter là application dependency

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
```

External Tomcat cung cấp **Servlet engine**, không cung cấp toàn bộ Spring MVC/Jackson/Boot application code. Không đánh dấu tất cả `starter-web` là provided.

### (3) Đánh dấu Tomcat starter là provided

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
```

Đây là cấu hình Maven được Boot 3.5 hướng dẫn cho deploy WAR ngoài. Spring Boot Maven plugin hỗ trợ repackaged executable WAR và giữ provided dependencies ở `WEB-INF/lib-provided`, nên artifact có thể chạy bằng `java -jar` nếu có `main()`.

Bố cục WAR điển hình:

```text
META-INF/
org/springframework/boot/loader/...       (Boot launcher)
WEB-INF/
  classes/
    application.properties
    com/example/wardeploy/...
  lib/
    spring-boot-...
    spring-webmvc-...
    jackson-...
  lib-provided/
    tomcat-embed-...
```

Đây là **sơ đồ**, không phải danh sách từng JAR cụ thể. Đừng thêm embedded Tomcat vừa `provided` vừa `compile` với versions khác nhau.

Kiểm tra:

```bash
mvn clean package
mvn dependency:tree -Dincludes=org.apache.tomcat.embed:*
jar tf target/servlet-war-demo-1.0.0.war
```

Xác nhận có classes và libraries đúng layer. Nếu có `NoSuchMethodError`, `ClassCastException`, `NoClassDefFoundError` tại deploy, kiểm tra BOM, dependency tree, container shared libs và duplicated modules.

## 6. Gradle: war plugin và providedRuntime

Một build Gradle Groovy DSL thay thế cho Maven:

```groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

```bash
./gradlew clean test bootWar
```

Đây là **fragment `build.gradle` độc lập về dependency configuration**, dùng với Gradle Wrapper tương thích Boot 3.5. `providedRuntime` được khuyến nghị hơn `compileOnly`, do `compileOnly` không cung cấp đầy đủ runtime dependency cho web integration tests. Với project khác, áp đúng version/plugin/Java toolchain của tổ chức.

## 7. Đường dẫn HTTP: ai sở hữu port và context?

### Khi chạy executable WAR

Ví dụ `application.properties` có:

```properties
server.port=8088
```

Chạy:

```bash
java -jar target/servlet-war-demo-1.0.0.war
```

Boot quản lý embedded Tomcat ở **8088**. Khi không đặt embedded context path, controller có URL:

```text
http://localhost:8088/api/hello/Ada
```

### Khi external Tomcat deploy WAR

Tomcat ngoài có connector **8080**. Nếu copy WAR thành `catalog.war` vào thư mục `webapps` và dùng deployment defaults, ứng dụng có context path **`/catalog`**:

```text
http://localhost:8080/catalog/api/hello/Ada
```

`server.port=8088` bên trong WAR **không đổi cổng** của external Tomcat. Ở đây Tomcat sở hữu connector, socket, TLS, thread pool cơ sở và deployed ServletContext.

`server.servlet.context-path` hữu ích cho **embedded Servlet container**, nhưng không phải cách tự đổi một context root đã được external Tomcat quyết định. Nếu deploy `ROOT.war`, container mặc định thường dùng root context. Có platform-specific context descriptor thì path có thể khác tên WAR.

### Quan sát đường dẫn thật

```java
String contextPath = request.getContextPath();
String servletPath = request.getServletPath();
```

Với `GET /api/where` trong project:

| Chế độ | `contextPath` | `servletPath` |
| --- | --- | --- |
| Embedded, root | `""` | `/api/where` |
| External `catalog.war` | `/catalog` | `/api/where` |

Filter/Servlet URL patterns được match **tương đối với ServletContext**. Nếu Filter cần bảo vệ `/api/*`, không thêm `/catalog` vào pattern, vì container đã chọn context trước.

### Khi có reverse proxy

```text
Browser: https://example.test/shop/api/hello/Ada
Proxy:   rewrite /shop -> /catalog
Tomcat:  http://tomcat.internal:8080/catalog/api/hello/Ada
MVC:     /api/hello/Ada
```

Đây chỉ là ví dụ. Proxy có thể strip/retain prefixes khác nhau; kiểm tra trực tiếp Tomcat và qua proxy, cookie Path, redirect Location, scheme/host forwarding và TLS.

## 8. Servlet, Filter, web.xml và initializer

Một traditional Boot WAR **không bắt buộc có `web.xml`** nếu dùng Java/Servlet initializer đúng. Có thể đăng ký custom Servlet/Filter qua:

- `@Bean Servlet` hoặc `ServletRegistrationBean`
- `@Bean Filter` hoặc `FilterRegistrationBean`
- `@ImportResource` nếu còn XML Spring configuration cần giữ
- `@SpringBootApplication` và Boot auto-configuration cho MVC

Snippet Servlet:

```java
@Bean
ServletRegistrationBean<LegacyPingServlet> legacy() {
    return new ServletRegistrationBean<>(
            new LegacyPingServlet(), "/legacy/*");
}
```

Snippet Filter:

```java
@Bean
FilterRegistrationBean<RequestMarkerFilter> marker() {
    FilterRegistrationBean<RequestMarkerFilter> bean =
            new FilterRegistrationBean<>(
                    new RequestMarkerFilter());
    bean.addUrlPatterns("/api/*");
    return bean;
}
```

Hai snippets dựa vào classes demo ở mục 9. Container sẽ đăng ký chúng vào webapp ServletContext, không tạo server thứ hai.

**Không double-register** cùng class/name/mapping qua `web.xml`, `@WebServlet`, `@WebFilter`, `@Component`, `@Bean` và registration beans nếu không có thiết kế rõ. Có thể gây startup failure, filter chạy hai lần hoặc route bị chiếm.

### Migrating legacy Spring MVC

Nếu ứng dụng có `AbstractDispatcherServletInitializer`, Spring XML, Servlet filters và context hierarchy:

1. Ghi lại mapping và trách nhiệm hiện tại của `web.xml`.
2. Tạo `@SpringBootApplication` trong package root có thể quét controllers/services.
3. Thêm `SpringBootServletInitializer` và source đúng.
4. Di chuyển từng Servlet/Filter/Listener sang registration beans khi phù hợp.
5. Giữ `@ImportResource` cho XML chưa chuyển được, kiểm tra parent/child contexts.
6. Chú ý Spring Security `DelegatingFilterProxy`, Session, CSRF/CORS, JSP/view resolvers.
7. Xóa trùng registrations và chạy regression tests trên external container.

Đừng xóa mọi vendor descriptor nếu server còn dùng JNDI, role mappings hoặc deployment metadata.

## 9. Dự án Maven WAR hoàn chỉnh

Mục tiêu lab: một ứng dụng Spring Boot MVC có business controller, service, Actuator, Filter và một non-MVC Servlet. Cùng WAR phải chạy ở embedded mode và external Tomcat.

### 9.1. Cấu trúc

```text
servlet-war-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/wardeploy/
    │   │   ├── ServletWarApplication.java
    │   │   ├── GreetingService.java
    │   │   ├── GreetingController.java
    │   │   └── WebRuntimeConfiguration.java
    │   └── resources/application.properties
    └── test/java/com/example/wardeploy/
        ├── GreetingServiceTest.java
        ├── GreetingMvcSliceTest.java
        └── EmbeddedWarHttpTest.java
```

Endpoints:

- `GET /api/hello/{name}`: JSON greeting, do MVC xử lý.
- `GET /api/where`: trả actual context/servlet path.
- `GET /legacy/ping`: text từ custom Servlet.
- `GET /actuator/health`: Actuator health.
- Filter đặt header `X-Demo-Filter: active` trên `/api/*`.

### 9.2. `pom.xml`

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
    <artifactId>servlet-war-demo</artifactId>
    <version>1.0.0</version>
    <packaging>war</packaging>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
            <artifactId>spring-boot-starter-tomcat</artifactId>
            <scope>provided</scope>
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

Không cần JSP, WebFlux, JPA hoặc database cho ví dụ. Tomcat `provided` và Spring Boot plugin tạo WAR có thể chạy hai chế độ.

### 9.3. `ServletWarApplication.java`

```java
package com.example.wardeploy;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class ServletWarApplication
        extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder builder) {
        return builder.sources(ServletWarApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(ServletWarApplication.class, args);
    }
}
```

Đây là class có trách nhiệm duy nhất là bootstrapping. External container dùng `configure`, executable WAR dùng `main`.

### 9.4. `GreetingService.java`

```java
package com.example.wardeploy;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public record Greeting(String message) {
    }

    public Greeting greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }
        return new Greeting("Hello, " + name + "!");
    }
}
```

`Greeting` là nested public Java record nên Jackson serialize JSON được. Business logic không phụ thuộc Servlet container hoặc HTTP port.

### 9.5. `GreetingController.java`

```java
package com.example.wardeploy;

import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class GreetingController {

    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping(
            value = "/hello/{name}",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public GreetingService.Greeting hello(
            @PathVariable String name) {
        return service.greet(name);
    }

    @GetMapping(
            value = "/where",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> where(
            HttpServletRequest request) {
        return Map.of(
                "contextPath", request.getContextPath(),
                "servletPath", request.getServletPath());
    }
}
```

`/api/where` giúp biết app thực sự được mount ở đâu. Không hardcode `/catalog` trong controller; WAR context do container chọn.

### 9.6. `WebRuntimeConfiguration.java`

```java
package com.example.wardeploy;

import java.io.IOException;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration(proxyBeanMethods = false)
public class WebRuntimeConfiguration {

    @Bean
    ServletRegistrationBean<LegacyPingServlet>
    legacyServletRegistration() {
        ServletRegistrationBean<LegacyPingServlet> bean =
                new ServletRegistrationBean<>(
                        new LegacyPingServlet(), "/legacy/*");
        bean.setName("legacyPingServlet");
        return bean;
    }

    @Bean
    FilterRegistrationBean<RequestMarkerFilter>
    markerFilterRegistration() {
        FilterRegistrationBean<RequestMarkerFilter> bean =
                new FilterRegistrationBean<>(
                        new RequestMarkerFilter());
        bean.addUrlPatterns("/api/*");
        bean.setName("requestMarkerFilter");
        bean.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        return bean;
    }
}

class LegacyPingServlet extends HttpServlet {

    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response)
            throws IOException {
        if (!"/ping".equals(request.getPathInfo())) {
            response.sendError(
                    HttpServletResponse.SC_NOT_FOUND);
            return;
        }
        response.setCharacterEncoding("UTF-8");
        response.setContentType("text/plain");
        response.getWriter().write("legacy-ok\n");
    }
}

class RequestMarkerFilter implements Filter {

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {
        ((HttpServletResponse) response)
                .setHeader("X-Demo-Filter", "active");
        chain.doFilter(request, response);
    }
}
```

File hợp lệ vì chỉ `WebRuntimeConfiguration` là public class. Hai lớp còn lại package-private. Không thêm `@Component` hoặc `@WebServlet` vào chúng: `ServletRegistrationBean`/`FilterRegistrationBean` đã sở hữu registration.

Một request `GET /catalog/legacy/ping` được external Tomcat chọn Servlet mapping `/legacy/*`, sau khi trừ context `/catalog`. Còn Filter `/api/*` hoạt động với MVC API routes.

### 9.7. `application.properties`

```properties
spring.application.name=servlet-war-demo

# Chỉ dùng cho embedded Tomcat khi java -jar.
server.port=8088

# External Tomcat quyết định context path theo deployment.
management.endpoints.web.exposure.include=health
management.endpoint.health.show-details=never
```

Trong production không dùng artifact này làm security template: POM chưa thêm Spring Security. Chỉ expose Actuator health để tiện kiểm tra, không bật env/beans/heapdump/shutdown.

## 10. Bộ test Java 17+

### 10.1. `GreetingServiceTest.java`

```java
package com.example.wardeploy;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingServiceTest {

    private final GreetingService service =
            new GreetingService();

    @Test
    void greetingIsCorrect() {
        assertEquals(
                new GreetingService.Greeting("Hello, Ada!"),
                service.greet("Ada"));
    }

    @Test
    void blankNameIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> service.greet(" "));
    }
}
```

Unit tests thuần Java, không cần Spring context/Tomcat.

### 10.2. `GreetingMvcSliceTest.java`

```java
package com.example.wardeploy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(GreetingController.class)
class GreetingMvcSliceTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    GreetingService service;

    @Test
    void mvcRoutesAndSerializes() throws Exception {
        given(service.greet("Ada")).willReturn(
                new GreetingService.Greeting("Hello, Ada!"));

        mvc.perform(get("/api/hello/Ada"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message")
                        .value("Hello, Ada!"));
    }
}
```

`@MockitoBean` dùng namespace Spring Framework 6.2. `MockMvc` kiểm tra MVC handler mapping/JSON **không mở socket**; không chứng minh WAR deploy ngoài.

### 10.3. `EmbeddedWarHttpTest.java`

```java
package com.example.wardeploy;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment =
                SpringBootTest.WebEnvironment.RANDOM_PORT)
class EmbeddedWarHttpTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate http;

    private String url(String path) {
        return "http://127.0.0.1:" + port + path;
    }

    @Test
    void embeddedServerAndFilterWork() {
        assertTrue(port > 0);
        ResponseEntity<Map> response = http.getForEntity(
                url("/api/hello/Ada"), Map.class);
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("Hello, Ada!",
                response.getBody().get("message"));
        assertEquals("active",
                response.getHeaders().getFirst("X-Demo-Filter"));
    }

    @Test
    void embeddedRootContextIsEmpty() {
        ResponseEntity<Map> response = http.getForEntity(
                url("/api/where"), Map.class);
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("",
                response.getBody().get("contextPath"));
        assertEquals("/api/where",
                response.getBody().get("servletPath"));
    }

    @Test
    void customServletIsRouted() {
        ResponseEntity<String> response = http.getForEntity(
                url("/legacy/ping"), String.class);
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("legacy-ok\n", response.getBody());
    }

    @Test
    void healthIsReachable() {
        ResponseEntity<Map> response = http.getForEntity(
                url("/actuator/health"), Map.class);
        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("UP",
                response.getBody().get("status"));
    }
}
```

Đây là live HTTP test **embedded**, không phải external WAR test. Provided Tomcat libraries nằm trên test classpath, giúp `RANDOM_PORT` hoạt động. Phải chạy một external deployment smoke test khác.

### 10.4. Lệnh build

```bash
java -version
mvn -version
mvn clean test
mvn clean package
```

`mvn package` sẽ chạy tests theo lifecycle mặc định và tạo `target/servlet-war-demo-1.0.0.war`. Nếu dependencies chưa có local, Maven cần truy cập repository. Không khẳng định stdout cố định của Surefire vì plugins/logging khác nhau.

## 11. Thử executable WAR trước

```bash
java -jar target/servlet-war-demo-1.0.0.war
```

App dùng embedded Tomcat port 8088 từ properties. Trong terminal khác:

```bash
curl -i http://127.0.0.1:8088/api/hello/Ada
curl -i http://127.0.0.1:8088/api/where
curl -i http://127.0.0.1:8088/legacy/ping
curl -i http://127.0.0.1:8088/actuator/health
```

Kỳ vọng khi healthy:

- `/api/hello/Ada`: HTTP 200, `X-Demo-Filter: active`, body `{"message":"Hello, Ada!"}`.
- `/api/where`: HTTP 200, JSON:

```json
{"contextPath":"","servletPath":"/api/where"}
```

- `/legacy/ping`: HTTP 200, text `legacy-ok` **với newline cuối**.
- `/actuator/health`: HTTP 200 và `{"status":"UP"}` khi health contributors UP.

Đây là executable mode. Nó chứng minh WAR có thể start embedded Tomcat qua Boot launcher, **chưa** chứng minh Servlet startup trên external Tomcat.

## 12. Triển khai external Tomcat 10.1

### 12.1. Đổi tên artifact theo context

```bash
cp target/servlet-war-demo-1.0.0.war target/catalog.war
```

PowerShell:

```powershell
Copy-Item target/servlet-war-demo-1.0.0.war target/catalog.war
```

Theo Tomcat defaults, `catalog.war` triển khai ở context path `/catalog`. `ROOT.war` thường dùng root context. Custom Context descriptors hoặc platform config có thể override.

### 12.2. Tomcat 10.1 trên Docker cho local lab

```bash
docker run --rm -d \
  --name war-demo-tomcat \
  -p 127.0.0.1:8080:8080 \
  tomcat:10.1-jdk17-temurin

docker cp target/catalog.war \
  war-demo-tomcat:/usr/local/tomcat/webapps/catalog.war

docker logs war-demo-tomcat --tail=80
```

PowerShell một dòng:

```powershell
docker run --rm -d --name war-demo-tomcat -p 127.0.0.1:8080:8080 tomcat:10.1-jdk17-temurin
docker cp target/catalog.war war-demo-tomcat:/usr/local/tomcat/webapps/catalog.war
docker logs war-demo-tomcat --tail=80
```

Chỉ bind cổng demo vào loopback host. Image tag minh họa; production pin digest, quét CVE và update patches. Chờ logs của Tomcat báo đã deploy WAR thành công trước khi gửi request.

### 12.3. Kiểm tra WAR tại đúng context

```bash
curl -i http://127.0.0.1:8080/catalog/api/hello/Ada
curl -i http://127.0.0.1:8080/catalog/api/where
curl -i http://127.0.0.1:8080/catalog/legacy/ping
curl -i http://127.0.0.1:8080/catalog/actuator/health
```

| URL external | HTTP khi khỏe | Nội dung kỳ vọng |
| --- | --- | --- |
| `/catalog/api/hello/Ada` | 200 | `{"message":"Hello, Ada!"}`, filter header |
| `/catalog/api/where` | 200 | Context `/catalog`, Servlet path `/api/where` |
| `/catalog/legacy/ping` | 200 | `legacy-ok` + newline |
| `/catalog/actuator/health` | 200 | `{"status":"UP"}` |
| `/api/hello/Ada` (thiếu context) | Thường 404 | Không phải route của catalog WAR |

JSON chi tiết của external `/catalog/api/where`:

```json
{"contextPath":"/catalog","servletPath":"/api/where"}
```

Đây là sự khác nhau trọng tâm với embedded WAR. URL không có `/catalog` là đường dẫn khác của Tomcat. Nếu Tomcat có ROOT webapp, có thể nó trả nội dung riêng; không suy từ một 200 bất kỳ rằng catalog route đúng.

### 12.4. Dừng lab

```bash
docker stop war-demo-tomcat
```

Vì dùng `--rm`, container bị xóa sau khi dừng. **Không dừng một external Tomcat dùng chung của tổ chức** chỉ để kết thúc lab.

## 13. Security và vận hành khi external WAR

### 13.1. HTTP/TLS connectors

Với embedded mode, Boot quản lý `server.port`, `server.ssl.*` và embedded Tomcat. Với external mode, Tomcat platform sở hữu HTTP connectors, TLS certificates và listener settings; WAR application properties **không tự thay external connector**.

Cần rà soát certificate trust/renewal, HTTPS redirects, `Forwarded`/`X-Forwarded-*` headers, request size/timeouts, compression, WebSocket, HTTP/2, Tomcat valves và ingress rewrites.

### 13.2. Cookies/session

Nhiều WAR cùng hostname có thể phát cookie `JSESSIONID`, nhưng `Path` thường theo Servlet context. Kiểm tra:

- Path `/catalog` có phù hợp redirect/login không.
- `Secure` khi ứng dụng sau HTTPS reverse proxy.
- `HttpOnly`, `SameSite`, session timeout và cookie domain.
- Session persistence khi redeploy hoặc khi load balancing nhiều nodes.
- Spring Session namespace/Redis nếu cố ý chia sẻ state.

Không tự kết luận các WAR chung JVM là chia sẻ HTTP session hay share user authentication.

### 13.3. SecurityFilterChain và Actuator

Application có Spring Security và container cũng có thể áp realm/constraints riêng. Filter order/CORS/CSRF/authorization phải được kiểm tra qua actual URL. Actuator health nằm dưới context `/catalog/actuator/health` ở ví dụ; không expose `env`, `beans`, `heapdump`, `loggers` hoặc `shutdown` public.

Nếu cần management listener ở port khác, hãy xác định **platform nào sở hữu connector** và cách security/network policy được áp dụng. Đừng mặc định cấu hình `management.server.*` dành cho standalone Boot sẽ tự mở port mới trên shared external Tomcat theo cách giống executable mode.

### 13.4. Secrets và shared JVM

Trong Tomcat chạy nhiều WAR, system properties và OS environment của process có thể áp dụng đến **mọi WAR**. Không cấu hình global `SPRING_PROFILES_ACTIVE`, credential, JNDI hoặc path secrets khiến webapp khác dùng nhầm. Ưu tiên platform-approved per-app configuration, secret manager, file ACL và audit.

### 13.5. Classloader, memory và redeploy

Mỗi webapp có ServletContext/classloader riêng nhưng cùng JVM heap/GC/system resources. Khi nhiều WAR cùng chạy:

- Tổng Hikari maximumPoolSize có thể vượt DB connection limits.
- Long-lived Threads, ThreadLocal, custom executors có thể giữ classloader cũ sau undeploy.
- JDBC drivers, schedulers, file watchers, HTTP clients và logging appenders cần shutdown.
- Memory leaks của một WAR ảnh hưởng các WAR khác.
- Server restart có blast radius rộng hơn restart một app process.

Sử dụng bean lifecycle (`@PreDestroy`, `DisposableBean`) và kiểm tra heap/metaspace/thread count qua nhiều lần redeploy. Đừng coi WAR webapp classloader là process-level security isolation.

## 14. Chiến lược kiểm thử đúng ba boundary

| Kiểu test | Câu hỏi trả lời được | Điều không chứng minh |
| --- | --- | --- |
| JUnit unit | Service Java logic đúng? | MVC/Servlet routing |
| `@WebMvcTest` + MockMvc | Handler mapping/JSON đúng? | Real socket/container |
| `@SpringBootTest(RANDOM_PORT)` | Embedded servlet server HTTP hoạt động? | External WAR classloader/startup |
| `java -jar ...war` smoke | Repackaged executable WAR hoạt động? | Tomcat external deployment |
| Deploy WAR vào Tomcat 10.1 + curl | External initializer/context/routing hoạt động? | Ingress/TLS thật nếu chưa dùng |
| Staging proxy test | Public route, cert, forwarded headers đúng? | Capacity nếu không đo tải |
| Repeated redeploy/soak | Có leaks/session issues dài hạn? | Mọi production failure modes |

**Cần external smoke test thực sự.** Đơn thuần thay `@SpringBootTest` bằng `RANDOM_PORT` vẫn test embedded Tomcat. Nếu external container không deploy WAR, HTTP server của Tomcat vẫn có thể mở cổng 8080 và phục vụ app khác; health phải gọi đúng `/catalog/actuator/health`.

Một số negative checks nên có: URL thiếu `/catalog`, `/catalog/legacy/missing`, POST method không được khai báo, filters/security không mở quá rộng, HTTPS/cookie behavior sau proxy, startup failure có log tương ứng.

## 15. Phân tích lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Cách xác minh và sửa |
| --- | --- | --- |
| Executable WAR chạy, external 404 | Thiếu initializer hoặc context path sai | Kiểm tra `SpringBootServletInitializer`, deploy logs |
| Tomcat port 8080 mở nhưng WAR fail | Container có nhiều webapps | Check đúng `/catalog/actuator/health` |
| Boot controller 404 | Component scan root sai | Đặt `@SpringBootApplication` ở common package |
| `javax.servlet.*` ClassNotFound | Legacy Servlet API | Migrate sang `jakarta.*` |
| `jakarta.servlet.*` NoClassDefFound | Container Servlet generation thiếu | Tomcat 10.1/Servlet 5+ |
| Boot 3.5 WAR trên Tomcat 9 | Namespace/generation không tương thích | Nâng Servlet container |
| `NoSuchMethodError` | Spring/Tomcat/Jackson version lệch | Boot BOM, dependency tree, shared server libs |
| Build ra JAR | Chưa có `<packaging>war</packaging>` | Sửa Maven packaging |
| Executable WAR không run | Plugin repackage/main class sai | Kiểm tra Boot Maven plugin |
| Tomcat embed jars trong `WEB-INF/lib` | Scope provided sai | Dùng `spring-boot-starter-tomcat` provided |
| `server.port=8088` nhưng external vẫn 8080 | Container sở hữu connector | Sửa Tomcat/server config |
| `/api/...` 404, `/catalog/api/...` 200 | Bỏ sót context path | Tính URL từ WAR deployment |
| Filter không chạy | Đăng ký `/catalog/api/*` thay `/api/*` | Dùng ServletContext-relative pattern |
| Startup duplicate Servlet | XML/annotations/Bean registrations trùng | Chọn một registration mechanism |
| Boot 2→3 JSP/JSTL fail | Jakarta migration chưa đủ | Nâng APIs/libs theo container |
| Health local pass, public proxy 404 | Rewrite/forwarded path sai | Test cả direct và proxy |
| Redeploy tăng heap/metaspace | Classloader/thread/resource leak | Shutdown hooks, heap/thread dumps |
| Spring Security 403 | Auth/CSRF/filter/realm khác runtime | Xem chain và headers, không tắt vô điều kiện |
| Secret/profile sang nhầm WAR | OS process vars dùng chung | Per-webapp config |
| WebFlux server deploy WAR fail | Không hỗ trợ traditional WAR WebFlux server | Chọn reactive deployment |
| Servlet container vendor khác | Vendor classloading/startup khác | Test đúng version/vendor |

### Một ngoại lệ đáng nhớ: WebLogic

Boot 3.5 traditional deployment guide yêu cầu initializer cho **WebLogic** implements `WebApplicationInitializer` **trực tiếp** dù kế thừa `SpringBootServletInitializer` đã implements. Snippet vendor-specific:

```java
@SpringBootApplication
public class WebLogicWarApp extends SpringBootServletInitializer
        implements org.springframework.web.WebApplicationInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder builder) {
        return builder.sources(WebLogicWarApp.class);
    }
}
```

Snippet cần imports và vendor-specific dependencies/config, **không** thêm cùng main class demo. WebLogic có thể cần `WEB-INF/weblogic.xml` cấu hình package preference (ví dụ `org.slf4j`); kiểm tra version compatibility và docs chính thức trước deploy.

## 16. Bài tập thực hành

**A. Bỏ initializer.** Xóa `extends SpringBootServletInitializer` nhưng vẫn giữ `main`. Dự đoán embedded executable còn chạy, external WAR không bootstrap như trước. Khôi phục sau test.

**B. Không đổi tên WAR.** Deploy `servlet-war-demo-1.0.0.war` nguyên tên rồi gọi `/catalog/...`: có thể 404. Theo Tomcat naming convention, path mặc định gắn tên WAR; điều chỉnh URL theo context thực.

**C. Thay `server.servlet.context-path`.** Đặt `/embedded` và so khi chạy `java -jar` với external `catalog.war`. Embedded route có prefix `/embedded`, external vẫn do container quyết định.

**D. Xóa scope provided.** So `jar tf` trước/sau; tìm những Tomcat jars bị đưa vào normal WAR dependencies. Khôi phục `provided`.

**E. Đổi Servlet mapping.** `/legacy/*` → `/compat/*`; MVC slice test vẫn có thể pass, nhưng embedded/external HTTP `/legacy/ping` fail.

**F. Sai Filter mapping.** Dùng `/catalog/api/*` thay `/api/*`; Filter không match như dự kiến trong context `/catalog`. Sửa về mapping tương đối với ServletContext.

**G. Thêm một WAR thứ hai.** Chạy `/catalog` và `/orders` trên cùng Tomcat. Đánh giá tổng JDBC pools, heap, log paths và rollout blast radius.

**H. Proxy rewrite.** Đưa public `/shop` tới upstream `/catalog`. Kiểm tra redirects, sessions, `Location`, HTTPS và actual HTTP response.

**I. WAR startup fail, Tomcat vẫn sống.** Làm thiếu một required property rồi quan sát logs và `/catalog/actuator/health`; tại sao `curl localhost:8080` không phải deployment health check?

**J. So Gradle/Maven.** Tạo `bootWar` với `providedRuntime`, kiểm tra lib-provided và runtime behavior so Maven WAR. Không ghép dependencies không cùng BOM generation.

## 17. Câu hỏi tự đánh giá

1. `SpringBootServletInitializer` dùng cho điều gì? — Khởi động Boot web app từ external Servlet container.
2. External Tomcat có chạy `main()`? — Không.
3. `configure` trả gì? — `SpringApplicationBuilder` đã thêm sources/customization.
4. WAR chỉ cần đổi extension từ `.jar`? — Không.
5. Maven packaging cần gì? — `<packaging>war</packaging>`.
6. Tomcat starter scope nào? — `provided`.
7. Gradle tương đương? — `war` và `providedRuntime`.
8. Vì sao có `WEB-INF/lib-provided`? — Boot executable WAR có thể dùng provided libraries.
9. Java baseline của Boot 3.5? — 17+.
10. External Tomcat phù hợp? — Tomcat 10.1/Jakarta Servlet.
11. Tomcat 9 phù hợp Boot 3.5 WAR? — Không do Servlet namespace/generation.
12. `server.port` có đổi external connector? — Không.
13. Context `/catalog` từ đâu? — WAR deployment/context configuration.
14. Filter pattern cần `/catalog` không? — Không.
15. Có cần `web.xml` không? — Không trong cấu hình Java initializer thông thường.
16. Có được double-register Servlet không? — Không nên.
17. `@SpringBootTest(RANDOM_PORT)` test external Tomcat? — Không, test embedded.
18. Cần smoke test gì? — Đúng context/health/business/Servlet/filter endpoints.
19. Các WAR chung JVM có isolation như các process? — Không.
20. WebFlux server deploy traditional WAR được không? — Không hỗ trợ theo guide Boot 3.5.

## 18. Checklist cho production

- [ ] Main class extends `SpringBootServletInitializer`, sources/package scan rõ.
- [ ] `configure` không chạy app hai lần; `main()` hỗ trợ executable khi cần.
- [ ] Maven WAR/Boot plugin hoặc Gradle war/bootWar đúng version.
- [ ] Tomcat provided/providedRuntime và không có duplicate servlet engine jars.
- [ ] Java/Jakarta/Servlet/Spring/Server versions tương thích, không còn javax legacy.
- [ ] Inspect WAR `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided`.
- [ ] Tên WAR/context path, public ingress path và Tomcat connector có tài liệu rõ.
- [ ] Servlet/Filter registrations không trùng `web.xml`/annotations.
- [ ] Actuator health đúng WAR context, endpoints nhạy cảm không public.
- [ ] TLS/mTLS, security chain, CORS/CSRF, session cookie flags và proxy config được test.
- [ ] Secrets/profiles có scope per-app, không rò qua shared JVM config.
- [ ] Tổng DB pools, threads, heap/GC của tất cả WAR nằm trong capacity budget.
- [ ] Unit, MVC slice, embedded HTTP, executable WAR và **external WAR smoke** đều được chạy đúng mục tiêu.
- [ ] Có chiến lược backup/rollback, traffic draining, redeploy và classloader leak checks.
- [ ] Không coi Tomcat port mở là bằng chứng WAR deploy thành công.
- [ ] Theo dõi server patch versions, CVEs, deployment logs và startup failure alerts.

## 19. Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Traditional Deployment](https://docs.spring.io/spring-boot/3.5/how-to/deployment/traditional-deployment.html): `SpringBootServletInitializer`, WAR packaging, Tomcat provided và WebLogic.
- [Spring Boot 3.5 — SpringBootServletInitializer JavaDoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/web/servlet/support/SpringBootServletInitializer.html): interface `WebApplicationInitializer`, `configure` và lifecycle.
- [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html): Java/Spring Framework/Servlet compatibility.
- [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): server.port và embedded runtime.
- [Spring Boot 3.5 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html): MVC, Servlet/Filter registration.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): MockMvc/RANDOM_PORT/TestRestTemplate.
- [Spring Boot 3.5 — Actuator Monitoring](https://docs.spring.io/spring-boot/3.5/reference/actuator/monitoring.html): health URL/exposure.
- [Spring Framework — WebApplicationInitializer](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/WebApplicationInitializer.html): Servlet startup integration.
- [Jakarta Servlet Specification](https://jakarta.ee/specifications/servlet/): ServletContext, filters và URL matching.
- [Apache Tomcat 10.1 — Deployer HOW-TO](https://tomcat.apache.org/tomcat-10.1-doc/deployer-howto.html): WAR deployment/context behavior.
- [Maven WAR Plugin](https://maven.apache.org/plugins/maven-war-plugin/): Maven WAR packaging.
- [Spring Boot Gradle Plugin 3.5 — Packaging](https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging.html): bootWar/providedRuntime.

**Kết luận:** `SpringBootServletInitializer` giúp **external Servlet container** khởi động Spring Boot WAR bằng Servlet lifecycle, còn `main()` dành cho executable. Một WAR đúng phải có packaging, provided dependencies, Jakarta-compatible container, Servlet/Filter registration và URL context được kiểm chứng. Hãy xây/đọc WAR, chạy tests, sau đó **deploy và gửi HTTP thật qua chính external container** trước khi xác nhận mức sẵn sàng production.
# Ứng dụng chọn sai web stack do phụ thuộc bắc cầu

> **Ngữ cảnh:** Spring Boot – **web-runtime** → **Gỡ lỗi và nâng cấp**. Bài Knowledge này tập trung vào lỗi ứng dụng đáng lẽ chạy **Spring WebFlux (REACTIVE)** nhưng khởi động **Spring MVC/Servlet (SERVLET)** vì một thư viện được đưa vào bằng **transitive dependency**. Cũng xét trường hợp MVC sử dụng `WebClient` một cách đúng đắn, và ứng dụng batch/CLI không cần web server. Ví dụ dùng **Java 17+, Spring Boot 3.3.x (bản lab 3.3.13), Maven và Gradle**. Lab dùng hai module Maven: `gateway-lib` và `reactive-app`, có POM đầy đủ, Java source, integration tests, quy trình tái hiện lỗi, loại dependency và kiểm chứng bằng HTTP server thật.

## 1. Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Phân biệt **WebApplicationType.SERVLET**, **WebApplicationType.REACTIVE** và **WebApplicationType.NONE**.
2. Nắm quy tắc Boot 3.3: nếu **Spring MVC và Spring WebFlux cùng hiện diện**, MVC **được ưu tiên** trong việc suy luận web application type.
3. Phân biệt `spring-boot-starter-web`, `spring-webmvc`, `spring-boot-starter-webflux`, `spring-webflux`, `spring-boot-starter-tomcat` và `spring-boot-starter-reactor-netty`.
4. Hiểu vì sao `WebClient` **outbound** không tự chuyển **inbound HTTP server** sang WebFlux.
5. Truy ngược dependency trực tiếp và bắc cầu bằng `mvn dependency:tree` hoặc Gradle `dependencyInsight` cho đúng runtime classpath.
6. Xác minh app thật chạy loại `ApplicationContext` nào, không chỉ nhìn startup log Tomcat/Netty.
7. Hiểu các điều kiện Boot auto-configuration như `@ConditionalOnClass` và `@ConditionalOnWebApplication`, dùng `--debug` để xem Conditions Evaluation Report.
8. Sử dụng Maven `<exclusions>` hoặc Gradle `exclude` có phạm vi hẹp, đồng thời biết limitation của các exclusions khi một library xuất hiện qua nhiều paths.
9. Viết integration test khởi động real embedded web server, **fail trước khi sửa** và **pass sau khi sửa**; thấy rõ chỉ kiểm HTTP status 200 là chưa đủ.
10. Phân biệt workaround `spring.main.web-application-type=reactive` với sửa **root cause** trong dependency graph.
11. Nhận ra sai web stack có thể kéo theo sai filters, interceptors, reactive routing, security chain, timeout, threading model và các metrics.
12. Lập runbook cho upgrade, regression tests, deployment artifact, canary/rollback và phòng ngừa thư viện dùng chung kéo một web starter không cần thiết.

## 2. Sự cố điển hình sau khi nâng cấp thư viện dùng chung

Một team phát triển reactive service dùng WebFlux, WebClient và các drivers non-blocking. Module ứng dụng chỉ khai `spring-boot-starter-webflux` và một shared client library. Sau khi cập nhật shared library, startup log đột nhiên có Tomcat, một WebFlux router không được map, hoặc một `WebFilter` không thấy tác dụng.

~~~text
reactive-app
    |
    +-- spring-boot-starter-webflux
    |       +-- spring-webflux
    |       +-- spring-boot-starter-reactor-netty
    |
    +-- gateway-lib
            +-- spring-boot-starter-web      <-- transitive dependency
                    +-- spring-webmvc
                    +-- spring-boot-starter-tomcat
~~~

Ở source `reactive-app/pom.xml` không có dependency starter-web trực tiếp, nhưng Maven/Gradle đưa nó vào **runtime classpath** qua `gateway-lib`. Khi Boot 3.3 thấy cả `spring-webmvc` và `spring-webflux`, **MVC thắng theo quy tắc mặc định**. Đây không phải lựa chọn ngẫu nhiên của Spring Boot; thuật toán sử dụng classpath indicators và các overrides cấu hình.

**Điều cần sửa:** tìm ai kéo Spring MVC vào classpath và liệu phụ thuộc đó có thật sự cần thiết. Không chỉ thêm một flag reactive vào test rồi coi đã xử lý xong: production artifact có thể vẫn chứa MVC libraries, beans và assumptions.

## 3. Phân biệt stack, web server, HTTP client và starter

| Lớp | Ví dụ | Chức năng |
|---|---|---|
| Web application type | `SERVLET` / `REACTIVE` / `NONE` | Chọn web-oriented Spring ApplicationContext |
| Servlet framework | Spring MVC, `DispatcherServlet` | Xử lý HTTP theo Servlet stack |
| Reactive framework | Spring WebFlux, `DispatcherHandler` | Reactive request handling |
| HTTP server | Tomcat, Jetty, Undertow, Reactor Netty | Engine lắng nghe TCP/HTTP |
| HTTP client | `RestClient`, `WebClient`, Java `HttpClient` | Gọi API đi **ra ngoài** |
| Starter | `spring-boot-starter-web` | Bundle dependency/auto-config ecosystem |
| Dependency scope | compile, runtime, test, provided | Classpath theo giai đoạn |
| Auto-configuration | `WebMvcAutoConfiguration`, `WebFluxAutoConfiguration` | Tạo framework beans có điều kiện |

Không đồng nhất “Tomcat chắc chắn là MVC”: Spring Boot WebFlux có thể dùng Servlet-compatible servers ở một số cấu hình. Cũng không khẳng định “Netty JAR có mặt tức app đang reactive”: Netty có thể chỉ là HTTP client connector. **Loại ApplicationContext + handler chain thực** mới cho biết inbound stack được chọn.

### Bảng suy luận theo Spring Boot 3.3

| Classpath/cấu hình | Type mặc định hoặc override | Thường thấy |
|---|---|---|
| Spring MVC hiện diện | `SERVLET` | MVC, embedded Tomcat nếu starter-web |
| WebFlux hiện diện, MVC không có | `REACTIVE` | WebFlux, Reactor Netty nếu starter-webflux |
| **Cả MVC + WebFlux** | **`SERVLET`** | MVC được ưu tiên |
| Không có indicators web phù hợp | `NONE` | Non-web context |
| Có web libs nhưng `spring.main.web-application-type=none` | `NONE` | Non-web override |
| Cả MVC + WebFlux nhưng ép `reactive` | `REACTIVE` | Cần kiểm tất cả reactive beans/security |
| Có custom `SpringApplication.setWebApplicationType` | Theo cấu hình Java | Không còn suy luận thuần classpath |

**Không dùng bảng này thay runtime inspection.** Custom ApplicationContextFactory, environment variables và programmatic overrides đều có thể thay kết quả.

## 4. Vì sao MVC được ưu tiên khi cùng có WebFlux?

Spring Boot 3.3 tài liệu chính thức nêu: thêm cả `spring-boot-starter-web` và `spring-boot-starter-webflux` sẽ tự cấu hình Spring MVC. Lý do là rất nhiều service MVC cần **WebClient reactive outbound** mà không muốn đổi inbound Servlet handlers sang reactive server.

~~~text
MVC server (đúng khi ứng dụng chủ động chọn MVC)
    Incoming HTTP -> DispatcherServlet / Servlet Filters
                         |
                         +-- @RestController
                         |
                         +-- WebClient outbound -> API B
                                     (có thể dùng!)

Reactive server (đúng khi ứng dụng chủ động chọn WebFlux)
    Incoming HTTP -> DispatcherHandler / WebFilter
                         |
                         +-- RouterFunction hoặc @RestController
                         |
                         +-- WebClient outbound -> API B
~~~

`WebClient` chỉ quyết định cách gọi **remote HTTP API**. `spring-webflux` cung cấp client API lẫn server stack, nhưng presence của client không tự thắng MVC precedence. Ngược lại, nếu một shared starter vô tình mang Spring MVC vào WebFlux service, Boot sẽ không suy ra “WebFlux vì code trả Mono”.

## 5. Các dấu hiệu thường gặp của sai web stack

- Startup log chuyển từ Reactor Netty sang Tomcat theo default. Đây là **tín hiệu** chứ chưa phải bằng chứng duy nhất.
- `ApplicationContext` thực là `AnnotationConfigServletWebServerApplicationContext` nhưng team muốn reactive context.
- `RouterFunction<ServerResponse>` được định nghĩa cho WebFlux nhưng requests không được routed như mong đợi.
- `org.springframework.web.server.WebFilter` không chạy vì inbound path là Servlet `Filter` chain.
- Security reactive `SecurityWebFilterChain` không phải filter chain thực, trong khi một Servlet `SecurityFilterChain` có thể được tạo hoặc cấu hình khác.
- Team thấy `Mono` trong controller và tưởng app reactive; Spring MVC hỗ trợ một số reactive return types nên điều đó không chứng minh server stack.
- Một HTTP route trả 200 nhưng timeout/exception handling/threading model không như reactive design.
- Sau nâng version library, dependency tree có `spring-webmvc` dù app không khai starter-web trực tiếp.
- Local IDE chạy khác executable JAR/container vì build profiles, scopes, cached artifacts hoặc env overrides.
- Một CLI/batch app tự mở port 8080 vì web indicators xuất hiện trong dependency graph.

Không kết luận mọi 404/403 là do sai stack. Filter matcher, route registration, proxy rewrite, authentication và application code cũng có thể gây 404/403. Cần **đối chiếu classpath, context, auto-config và HTTP behavior**.

## 6. Direct dependency khác transitive dependency

**Direct:** khai trực tiếp trong `reactive-app/pom.xml`.  
**Transitive:** dependency của một dependency; Maven/Gradle thường resolve vào consumer runtime theo scope/rules.

~~~text
reactive-app
  |
  +-- starter-webflux               [direct]
  |
  +-- gateway-lib                   [direct]
        |
        +-- starter-web             [transitive]
              |
              +-- spring-webmvc
              +-- Tomcat
~~~

Một client library đôi khi chỉ cần `spring-web` hoặc `RestClient` nhưng lại khai cả `spring-boot-starter-web`, vô tình quyết định inbound runtime của consumers. Đây là dấu hiệu cần review **thiết kế dependency contract** của library. Nếu library chủ đích cung cấp Servlet filters/controller auto-config, exclusion có thể phá library; nên chọn/tách module adapter thích hợp.

**Không đoán graph từ Java imports.** Một library không import `DispatcherServlet` trong source chính vẫn có thể khai starter-web trong published POM và kéo transitive classes vào app.

## 7. Chẩn đoán: thu thập bằng chứng trước khi sửa

1. Ghi expected type: `SERVLET`, `REACTIVE` hay `NONE`; vì sao? Contract, latency, thread/driver model và business requirements.
2. Xác định Spring Boot version/BOM để biết quy tắc của **đúng version**.
3. Lấy resolved **runtime dependency tree**, không chỉ xem POM trực tiếp.
4. Tìm `spring-webmvc`, `spring-webflux`, starter-web/starter-webflux, Tomcat/Netty và paths.
5. Kiểm externalized settings `spring.main.web-application-type`, env var, command line hoặc code `SpringApplication.setWebApplicationType`.
6. Quan sát actual `ApplicationContext` và startup logs.
7. Xem `Conditions Evaluation Report` để biết auto-config Servlet/Reactive nào match.
8. Test actual incoming HTTP behavior và security/filter stack; đừng chỉ dựa vào body 200.
9. So cây dependencies giữa release tốt và release lỗi sau upgrade.
10. Chọn thay đổi nhỏ nhất, có CI guard và rollback khi không đạt acceptance criteria.

**Không sửa nóng bằng cách xóa JAR trong Maven cache, xóa imports hoặc thêm `@EnableWebFlux` ngay.** Build tool sẽ resolve lại dependency; `@EnableWebFlux` thay framework configuration, không trực tiếp xóa MVC khỏi classpath.

## 8. Maven dependency:tree: tìm đường gây lỗi

Trong Maven project:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dscope=runtime
mvn dependency:tree -Dincludes=org.springframework:spring-webmvc
mvn dependency:tree -Dincludes=org.springframework:spring-webflux
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-web
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-webflux
~~~

Ví dụ cây **minh họa**, không phải output được thu từ một repository thật:

~~~text
example:reactive-app:jar:0.0.1-SNAPSHOT
+- spring-boot-starter-webflux:jar:3.3.13
|  +- spring-webflux:jar:<version-managed-by-boot>
|  \- spring-boot-starter-reactor-netty:jar:3.3.13
\- example:gateway-lib:jar:0.0.1-SNAPSHOT
   \- spring-boot-starter-web:jar:3.3.13
      +- spring-webmvc:jar:<version-managed-by-boot>
      \- spring-boot-starter-tomcat:jar:3.3.13
~~~

Đây là **sơ đồ logic**, không phải dữ liệu đầu ra nguyên văn vì Maven còn hiển thị groupId, nhiều transitive dependencies khác và versions thật. Khi điều tra, phải tìm exact **đường từ root app tới spring-webmvc** thay vì chỉ thấy một dòng `spring-webmvc`.

### Scopes cần đọc chính xác

| Scope | Runtime executable JAR thông thường | Hệ quả |
|---|---|---|
| compile | Thường có | Kéo transitive dependencies tới app |
| runtime | Có | Web indicator có thể xuất hiện dù source không import |
| test | Không | Có thể thay `@SpringBootTest` nếu test classpath khác |
| provided | Phụ thuộc packaging/external container | WAR khác Boot executable JAR |
| optional | Consumers thường không tự nhận transitive theo Maven optional semantics | Hữu ích cho feature thực sự tùy chọn |

Không dùng `testRuntimeClasspath` thay `runtimeClasspath` để kết luận production. Đồng thời nếu chỉ **test** bị sai, hãy xem test-scoped additions riêng.

## 9. Gradle dependencyInsight

Với Gradle, xem configuration của service chạy:

~~~bash
./gradlew :reactive-app:dependencies \
  --configuration runtimeClasspath

./gradlew :reactive-app:dependencyInsight \
  --dependency spring-webmvc \
  --configuration runtimeClasspath

./gradlew :reactive-app:dependencyInsight \
  --dependency spring-boot-starter-web \
  --configuration runtimeClasspath
~~~

Trên Windows, dùng `gradlew.bat`. `dependencyInsight` cho biết ai đưa module vào graph và lý do Gradle chọn version, khác với việc chỉ đọc các khai báo `implementation`.

Ví dụ **mảnh Groovy build.gradle**, giả định plugins và BOM đã được khai trong project:

~~~groovy
dependencies {
    implementation "org.springframework.boot:spring-boot-starter-webflux"

    implementation("example:gateway-lib:0.0.1-SNAPSHOT") {
        exclude group: "org.springframework.boot",
                module: "spring-boot-starter-web"
    }
}
~~~

Trong multi-module Gradle có thể dùng `implementation(project(":gateway-lib")) { exclude ... }`. Đừng copy cú pháp Groovy nguyên vào Kotlin DSL `build.gradle.kts`.

**Tránh global exclusions** khi chưa hiểu paths. Một global `configurations.configureEach { exclude ... }` có thể làm vỡ các modules/tests cần Spring MVC. Sửa đúng cạnh dependency gây nhiễu và test lại toàn runtime graph.

## 10. Spring Boot auto-configuration bị ảnh hưởng thế nào?

Một starter không phải chỉ là jar. Nó mang **transitive dependencies** vào classpath, làm thay đổi điều kiện mà Spring Boot đánh giá:

- `@ConditionalOnClass`: framework class có mặt chưa?
- `@ConditionalOnWebApplication(type=SERVLET)`: app đang dùng Servlet web type?
- `@ConditionalOnWebApplication(type=REACTIVE)`: app là Reactive web type?
- `@ConditionalOnMissingBean`: một bean đã có khiến auto-config back off?
- `@ConditionalOnProperty`: cấu hình đang enable/disable feature?

~~~text
Maven / Gradle dependency graph
       |
       v
Actual runtime classpath
       |
       v
SpringApplication: detect/override WebApplicationType
       |
       +-- SERVLET --> ServletWebServerApplicationContext
       |                WebMvcAutoConfiguration candidates
       |                DispatcherServlet, Servlet server
       |
       +-- REACTIVE --> ReactiveWebServerApplicationContext
       |                WebFluxAutoConfiguration candidates
       |                DispatcherHandler, Reactive server
       |
       +-- NONE ----> non-web ApplicationContext
       |
       v
Conditional auto-configuration + beans + properties
       |
       v
Actual listener and request/security/filter pipeline
~~~

Nếu cả MVC và WebFlux present, việc có WebFlux API trên classpath **không buộc** `WebFluxAutoConfiguration` được chọn làm inbound server infrastructure. Một `WebFlux RouterFunction` bean có thể tồn tại nhưng **không có WebFlux handler adapter/router mapping** nào xử lý nó như người viết mong đợi.

### Conditions Evaluation Report

Dùng:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
~~~

Hoặc JAR:

~~~bash
java -jar reactive-app/target/reactive-app-0.0.1-SNAPSHOT.jar --debug
~~~

Report cho thấy matched/not-matched auto-configurations, lý do về classes/beans/web type. Tìm `WebMvcAutoConfiguration`, `WebFluxAutoConfiguration`, `ServletWebServerFactoryAutoConfiguration`, `ReactiveWebServerFactoryAutoConfiguration`, `DispatcherServletAutoConfiguration` trong report thực; tên và reasons có thể thay đổi theo phiên bản.

Nếu có Actuator, `/actuator/conditions` cũng có report khi được cấu hình expose **và bảo vệ**. Không mở `management.endpoints.web.exposure.include=*` công khai chỉ để debug; report/config/beans có thể làm lộ nội bộ.

**Conditions report không phải dependency tree.** Nó giải thích *vì sao Boot cấu hình một bean*; Maven/Gradle giải thích *ai đưa JAR vào runtime*.

## 11. Quan sát ApplicationContext: phép đo quyết định

Một integration test có thể:

~~~java
// Snippet trong một @SpringBootTest:
@Autowired
ApplicationContext context;

@Test
void expectedReactiveServer() {
    assertTrue(
        context instanceof ReactiveWebServerApplicationContext);
}
~~~

Các class liên quan:

- `org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext`.
- `org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext`.
- `org.springframework.context.ApplicationContext`.

Với Boot 3.3, `AnnotationConfigReactiveWebServerApplicationContext` và `AnnotationConfigServletWebServerApplicationContext` là các concrete implementations thường gặp. **Test nên assert interface type**, không hardcode class simple name vì có thể có custom ApplicationContextFactory.

**Chỉ nhìn log “Tomcat” hoặc “Netty” là chưa đủ:** reactive web server có thể cấu hình Tomcat/Jetty, và Reactor Netty có thể chỉ làm HTTP client. Nên quan sát context **và** HTTP requests thực.

## 12. LAB hai module Maven: tái hiện lỗi bắc cầu

Cây thư mục đầy đủ:

~~~text
stack-drill/
  pom.xml
  gateway-lib/
    pom.xml
    src/main/java/example/gateway/PartnerName.java
  reactive-app/
    pom.xml
    src/main/java/example/stack/ReactiveApplication.java
    src/main/resources/application.properties
    src/test/java/example/stack/ReactiveStackTests.java
~~~

`gateway-lib` chỉ chứa class Java thuần nhưng POM cố tình khai `spring-boot-starter-web`, để minh họa lỗi thiết kế dependency của library. `reactive-app` khai `starter-webflux` và dùng class đó. Mục tiêu là chứng minh MVC được chọn **qua transitive dependency**, không phải lỗi một controller.

### 12.1. Root Maven pom.xml

Tạo `stack-drill/pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>stack-drill</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>pom</packaging>
    <modules>
        <module>gateway-lib</module>
        <module>reactive-app</module>
    </modules>
    <properties>
        <java.version>17</java.version>
    </properties>
</project>
~~~

Root là Maven aggregator/parent (`packaging=pom`), không phải executable application. Child modules kế thừa Spring Boot dependency management và Java version từ parent.

### 12.2. gateway-lib/pom.xml — dependency **cố tình không cần thiết**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>example</groupId>
        <artifactId>stack-drill</artifactId>
        <version>0.0.1-SNAPSHOT</version>
    </parent>
    <artifactId>gateway-lib</artifactId>
    <dependencies>
        <!-- Sai có chủ đích: library không cần HTTP server -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Khi consumer thêm `gateway-lib` với scope compile, starter-web đi theo transitive path, trừ khi được khai optional/excluded theo Maven resolution rules. **Đừng dùng POM “sai” này cho một thư viện production**.

### 12.3. gateway-lib/PartnerName.java

Tạo `gateway-lib/src/main/java/example/gateway/PartnerName.java`:

~~~java
package example.gateway;

public final class PartnerName {
    private PartnerName() {
    }

    public static String label() {
        return "shared";
    }
}
~~~

Không có bất kỳ import Spring MVC nào, nhưng POM lại kéo toàn bộ server stack. Đây là lý do phải xem **published POM**, không chỉ Java imports.

### 12.4. reactive-app/pom.xml — trạng thái **trước khi sửa**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>example</groupId>
        <artifactId>stack-drill</artifactId>
        <version>0.0.1-SNAPSHOT</version>
    </parent>
    <artifactId>reactive-app</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>example</groupId>
            <artifactId>gateway-lib</artifactId>
            <version>0.0.1-SNAPSHOT</version>
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

POM này phải có XML schema declaration đúng theo Maven XSD. `xsi:schemaLocation` ở trên chỉ trỏ tới XSD URL nhưng thiếu namespace pair, và cũng chưa có `xmlns:xsi`; **để tránh một POM sai về XML namespaces**, hãy dùng chính xác phần opening tag của root/`gateway-lib`: `<project xmlns="http://maven.apache.org/POM/4.0.0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">`. Nội dung bên trong vẫn đúng. Ở project thực, áp opening tag chuẩn này cho cả hai child modules.

`reactive-app` không viết starter-web, nhưng nó vẫn nhận thông qua library. Không ép `spring.main.web-application-type` trong lab vì muốn tự động phát hiện bug.

### 12.5. reactive-app/application.properties

Tạo `reactive-app/src/main/resources/application.properties`:

~~~properties
server.port=8080
server.error.include-message=never
server.error.include-stacktrace=never
~~~

Không có `spring.main.web-application-type=reactive` để tránh che regression. Khi chạy JUnit `RANDOM_PORT`, Spring Boot sẽ chọn một cổng ngẫu nhiên thay vì giữ 8080.

### 12.6. reactive-app/ReactiveApplication.java — chạy trên cả MVC lẫn WebFlux

Tạo `reactive-app/src/main/java/example/stack/ReactiveApplication.java`:

~~~java
package example.stack;

import example.gateway.PartnerName;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ApplicationContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ReactiveApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveApplication.class, args);
    }

    public record StackInfo(
            String applicationContext,
            boolean servlet,
            boolean reactive,
            String gatewayContract) {
    }

    @RestController
    static class DiagnosticController {
        private final ApplicationContext context;

        DiagnosticController(ApplicationContext context) {
            this.context = context;
        }

        @GetMapping("/stack")
        public StackInfo stack() {
            return new StackInfo(
                context.getClass().getSimpleName(),
                context instanceof ServletWebServerApplicationContext,
                context instanceof ReactiveWebServerApplicationContext,
                PartnerName.label());
        }
    }
}
~~~

**Vì sao chọn `@RestController`?** Spring MVC và WebFlux đều hỗ trợ controller annotation style. Vì vậy `GET /stack` có thể trả HTTP 200 **trong cả hai modes**; đây là chủ ý để chứng minh test “endpoint 200” **không đủ xác nhận đúng stack**.

Sau khi loại dependency MVC, output JSON tương đương:

~~~json
{
  "applicationContext": "AnnotationConfigReactiveWebServerApplicationContext",
  "servlet": false,
  "reactive": true,
  "gatewayContract": "shared"
}
~~~

Trong state lỗi trước sửa, `servlet` thường true và `reactive` false. Không hardcode exact class simple name hoặc JSON key order vào test, vì app có thể custom context implementation.

### 12.7. ReactiveStackTests.java — test có chủ đích FAIL trước sửa

Tạo `reactive-app/src/test/java/example/stack/ReactiveStackTests.java`:

~~~java
package example.stack;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.reactive.context.ReactiveWebServerApplicationContext;
import org.springframework.boot.web.servlet.context.ServletWebServerApplicationContext;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ReactiveStackTests {

    @Autowired
    ApplicationContext context;

    @LocalServerPort
    int port;

    @Test
    void inboundServerMustBeReactive() {
        assertTrue(
            context instanceof ReactiveWebServerApplicationContext,
            () -> "Expected REACTIVE, got "
                + context.getClass().getName());
        assertFalse(
            context instanceof ServletWebServerApplicationContext);
    }

    @Test
    void http200AloneDoesNotProveWebStack() throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(
                    "http://localhost:" + port + "/stack"))
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertTrue(response.body()
                .contains("\"gatewayContract\":\"shared\""));
    }
}
~~~

**Trước khi sửa:** test `inboundServerMustBeReactive` phải **FAIL** vì app chọn MVC; test GET 200 có thể **PASS**.  
**Sau khi sửa:** cả hai tests phải **PASS** vì `gateway-lib` vẫn hoạt động, `spring-webflux` còn và `spring-webmvc` đã được loại khỏi runtime.

`java.net.http.HttpClient` trong test chỉ là HTTP **client**, không quyết định Spring server type. `@SpringBootTest(RANDOM_PORT)` tạo actual TCP web server; nó không giống một pure mock MVC test.

## 13. Làm lab theo thứ tự: tái hiện, tìm graph, sửa, kiểm chứng

### 13.1. Build artifacts ban đầu

Từ thư mục `stack-drill`:

~~~bash
mvn -DskipTests install
~~~

Thao tác này compile/install root/modules vào **local Maven repository**, không thực thi JUnit methods. Nó giúp các lệnh `mvn -pl reactive-app dependency:tree` resolve `example:gateway-lib:0.0.1-SNAPSHOT` trong lab, không cần remote registry.

### 13.2. Tìm dependency bắc cầu

~~~bash
mvn -pl reactive-app dependency:tree
mvn -pl reactive-app dependency:tree \
  -Dincludes=org.springframework:spring-webmvc
mvn -pl reactive-app dependency:tree \
  -Dincludes=org.springframework.boot:spring-boot-starter-web
~~~

Kỳ vọng thấy path `reactive-app → gateway-lib → spring-boot-starter-web → spring-webmvc`. Kết quả Maven phải được đọc **từ lệnh chạy thật**; ví dụ phía trên chỉ là dự đoán dựa trên POM.

### 13.3. Chạy test đầu tiên — fail là chủ đích

~~~bash
mvn -pl reactive-app -am test
~~~

Trong context classpath sai, `ReactiveStackTests.inboundServerMustBeReactive` expected FAIL, còn HTTP GET có thể pass. Đây là minh họa bug regression: **API vẫn trả 200 nhưng application type sai**.

Nếu test không fail, xem có override web type qua environment, Maven profile, IDE args hoặc file khác. Đừng sửa assertion cho xanh.

### 13.4. Sửa đúng dependency path trong reactive-app/pom.xml

Thay **chỉ** khối dependency `gateway-lib` bằng:

~~~xml
<dependency>
    <groupId>example</groupId>
    <artifactId>gateway-lib</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <exclusions>
        <exclusion>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Đây là `<exclusions>` ở **consumer dependency path**, không xóa `gateway-lib`. `PartnerName.label()` vẫn tồn tại, nên business helper còn dùng được.

### 13.5. Chạy lại tests và dependency tree

~~~bash
mvn clean test
mvn -DskipTests install

mvn -pl reactive-app dependency:tree \
  -Dincludes=org.springframework:spring-webmvc
mvn -pl reactive-app dependency:tree \
  -Dincludes=org.springframework:spring-webflux
mvn -pl reactive-app -am package
~~~

Sau exclusion, app nên không có `spring-webmvc` trong **runtime dependency tree** theo path đó; `spring-webflux` vẫn có. Full-context test phải xác nhận reactive web ApplicationContext.

### 13.6. Chạy JAR và curl

~~~bash
java -jar reactive-app/target/reactive-app-0.0.1-SNAPSHOT.jar
~~~

Terminal khác:

~~~bash
curl -i http://localhost:8080/stack
~~~

Kỳ vọng 200 với `reactive:true` và `servlet:false`. Trước sửa, JAR thường chạy servlet/Tomcat và trả `servlet:true`. Đây là hai outcomes của **lab**, không phải lời bảo đảm mọi custom Spring Boot app tự phân loại giống vậy khi có overrides.

### 13.7. Kiểm artifact đóng gói

~~~bash
jar tf reactive-app/target/reactive-app-0.0.1-SNAPSHOT.jar
~~~

Boot executable JAR thường giữ dependencies ở `BOOT-INF/lib`. Tìm `spring-webflux` và xem liệu `spring-webmvc` có còn không. Nếu run Docker image cũ/cache tag, local tree đúng nhưng runtime image vẫn có MVC; dùng image digest/version metadata và kiểm context trong chính deployment.

## 14. Đừng loại nhầm các thư viện cần thiết

Exclusion không phải lệnh “xóa MVC ở mọi nơi”. Ví dụ:

~~~text
reactive-app
    +-- gateway-lib -> spring-boot-starter-web   [đã exclude]
    +-- other-library -> spring-webmvc           [vẫn còn!]
    +-- spring-boot-starter-webflux
~~~

Nếu `other-library` vẫn kéo MVC indicator, Boot có thể tiếp tục chọn SERVLET. Cần đọc **toàn bộ paths** và xử lý root cause. Một library thực sự dùng Servlet filters/controller config hoặc MVC classes sẽ không tự hoạt động trong WebFlux chỉ bằng cách exclude dependencies: có thể gặp `ClassNotFoundException`, `NoClassDefFoundError` hoặc auto-config features bị mất.

**Hướng bền vững cho shared library:** tách `gateway-core` (business/DTO/HTTP client), `gateway-mvc-adapter` (Servlet-specific) và `gateway-webflux-adapter` (reactive-specific) nếu cần. Core không nên ép server framework cho consumers. Maven exclusions có thể là mitigation, nhưng phải có regression tests và kế hoạch sửa upstream library.

## 15. BOM, dependencyManagement và scopes: ba bẫy hay nhầm

Spring Boot parent/BOM quản lý **versions**, không quyết định thay mọi unwanted dependency.

- POM có `spring-boot-dependencies` BOM vẫn có thể kéo cả `spring-webmvc` và `spring-webflux` nếu graph khai cả hai.
- `dependencyManagement` thường điều phối versions/scope theo Maven rules, không có nghĩa nó tự exclude starter-web.
- Version override ngẫu nhiên của Spring Framework/Reactor/Jackson có thể tạo `NoSuchMethodError` khi Boot auto-config dùng một API khác.
- Một library compile scope có thể xuất hiện ở runtime consumer dù code chỉ gọi một DTO.
- Dependency test-scoped thường không vào packaged JAR nhưng có thể ảnh hưởng test ApplicationContext.
- Gradle variant selection/runtimeClasspath khác compileClasspath; cần xem configuration thật.
- Application executable JAR và executable WAR/external container có dependency loading khác.
- `mvn dependency:analyze` có thể báo “unused” với libraries được dùng qua reflection, SPI, Boot auto-config; đừng remove mù quáng.

Giữ versions được Boot 3.3 BOM quản lý khi làm lab; với production dùng **nhánh Boot được hỗ trợ bảo mật** theo chính sách tổ chức. Đây là bài về **chẩn đoán đúng semantics Boot 3.3**, không phải lời khuyên giữ 3.3.13 mãi.

## 16. Đôi khi MVC + WebFlux cùng có mặt là đúng

Một MVC app dùng JDBC/JPA và Servlet SecurityFilterChain, nhưng muốn gọi HTTP downstream bằng `WebClient` reactive API:

~~~text
Incoming HTTP client
     |
     v
Tomcat / DispatcherServlet / MVC Controller
     |
     +-- WebClient outbound -> HTTP partner
     |
     +-- JDBC / JPA (blocking)
~~~

Spring Boot ưu tiên MVC trong trường hợp này **đúng yêu cầu**. Không nên ép REACTIVE chỉ vì dùng WebClient hoặc một vài `Mono`. Nếu không cần reactive composition, Spring Framework 6.1 còn có `RestClient` blocking API, có thể đơn giản hơn cho service MVC.

**Quy tắc phân biệt:** HTTP server nhận inbound requests là một quyết định; HTTP client phát outbound requests là quyết định khác. Không coi sự hiện diện của WebFlux client classes là lỗi trong mọi MVC app.

### Kiểm app MVC muốn giữ Servlet

~~~java
// Snippet trong @SpringBootTest của một MVC app:
assertTrue(context instanceof ServletWebServerApplicationContext);
~~~

Khi thêm WebFlux client dependency, test này nên vẫn xanh. Nếu team thật sự muốn chuyển toàn server sang WebFlux, phải thiết kế lại filters/security/routing/I/O và kiểm từng layer.

## 17. Override web-application-type: công cụ hợp lệ nhưng không thay root cause

Khi muốn ép reactive:

~~~properties
spring.main.web-application-type=reactive
~~~

Hoặc:

~~~java
// Snippet main method alternative; WebApplicationType import cần có.
SpringApplication app = new SpringApplication(ReactiveApplication.class);
app.setWebApplicationType(WebApplicationType.REACTIVE);
app.run(args);
~~~

Override này khiến Boot chọn REACTIVE context dù classpath còn MVC (khi configuration phù hợp). Nhưng:

- Không loại starter-web/Tomcat/spring-webmvc JAR khỏi artifact.
- Không tự chuyển Servlet Filter sang WebFilter.
- Không làm MVC HandlerInterceptor trở thành reactive handler filter.
- Không tự biến `SecurityFilterChain` thành `SecurityWebFilterChain`.
- Không chuyển JDBC blocking thành reactive driver.
- Có thể làm một thư viện cần Servlet ApplicationContext không hoạt động.
- Không sửa transitive dependency design của library.

**Không dùng một test override che regression:**

~~~java
// Dùng property này chỉ khi production CŨNG có property tương ứng.
// Nếu production không ép, test này che lỗi default classpath selection.
@SpringBootTest(properties =
    "spring.main.web-application-type=reactive")
class ExplicitReactiveConfigTests {
}
~~~

Nếu production chủ động override, test phải mirror deployment config và kiểm runtime đầy đủ; đồng thời vẫn review dependency graph. `@EnableWebFlux`/`@EnableWebMvc` không phải replacement cho `WebApplicationType`; chúng thay framework customization/auto-config behavior và có thể tạo vấn đề khác.

## 18. Sai stack có thể phá ranh giới web/security

| Mặt kiểm | MVC/SERVLET | WebFlux/REACTIVE |
|---|---|---|
| Dispatcher | `DispatcherServlet` | `DispatcherHandler` |
| Request filters | `jakarta.servlet.Filter` / `OncePerRequestFilter` | `WebFilter` / `WebFilterChain` |
| Security | `SecurityFilterChain` / `HttpSecurity` | `SecurityWebFilterChain` / `ServerHttpSecurity` |
| Handler intercept | `HandlerInterceptor` | WebFilter/reactive handler filters |
| Request abstraction | `HttpServletRequest` | `ServerWebExchange` |
| Test | `MockMvc` / `@WebMvcTest` | `WebTestClient` / `@WebFluxTest` |
| Async model | Servlet async, Callable/DeferredResult | Mono/Flux and reactive cancellation |
| Default server via starter | Tomcat | Reactor Netty |

Một WebFlux `WebFilter` không được gọi trong Servlet filter chain. Nếu app chạy MVC ngoài dự kiến, authentication/authorization rules ở reactive Security chain **có thể không hoạt động**; cần negative tests cho protected endpoints. Không bật `permitAll()` để sửa tạm và không tự coi HTTP 200 là bằng chứng bảo mật.

### Có Mono nghĩa là WebFlux server?

Không. MVC có thể adapt một số reactive controller return types:

~~~java
// Snippet có thể được xử lý trong MVC hoặc WebFlux:
@GetMapping("/hello")
Mono<String> hello() {
    return Mono.just("hello");
}
~~~

Kết quả trả 200 không xác định stack. Assert actual ApplicationContext, handler registration và security filter chain.

## 19. App batch/CLI chọn sai web type

Một ứng dụng `CommandLineRunner` không có HTTP endpoints có thể nhận web dependencies vì shared libraries và tự khởi web server. Dấu hiệu: process không thoát theo kỳ vọng hoặc cổng 8080 trùng với service khác.

Để khai báo app **non-web**:

~~~properties
spring.main.web-application-type=none
~~~

Khác với:

~~~properties
server.port=-1
~~~

`server.port=-1` có thể tạo **web ApplicationContext không có HTTP listener**, còn `spring.main.web-application-type=none` yêu cầu non-web context. Nên dùng NONE cho CLI/batch thực và làm sạch unnecessary dependencies.

## 20. Upgrade library làm thay đổi runtime classpath

Một câu chuyện thường gặp:

~~~text
Before upgrade:
  shared-client v1 -> spring-web / client utilities only
  reactive-app -> starter-webflux
  result -> REACTIVE

After upgrade:
  shared-client v2 -> starter-web
  reactive-app -> starter-webflux + transitive starter-web
  result -> SERVLET (default)
~~~

Các bước root-cause review:

1. So dependency trees của last-known-good và candidate.
2. Kiểm direct/transitive scopes và phiên bản Boot/BOM.
3. Xem published POM metadata/release notes của shared-client.
4. Kiểm ApplicationContext/conditions report ở **artifact đúng version**.
5. Xem có config override ở test/IDE/prod.
6. Lập regression tests context/security/HTTP.
7. Sửa shared library hoặc exclude hẹp ở consumer; rollback library version nếu cần.
8. Build lại executable JAR/image, canary và theo dõi 4xx/5xx, latency, thread/Netty metrics.
9. Viết dependency contract và guard ngăn tái xuất hiện.

Một library upgrade có thể thay đổi **class loading và auto-config** mà không sửa một dòng controller. Vì vậy review dependency graph là phần của review behavior, không chỉ license/security.

## 21. Classpath ở CI, IDE và production không giống nhau

Để tránh sai kết luận:

- Test-scope JAR không mặc nhiên được đóng vào executable Boot JAR.
- IDE/run configuration có thể thêm classpath/profiles/VM arguments.
- Một custom `SpringApplicationBuilder` hoặc environment variable có thể override type mà local test không biết.
- Maven reactor dependency resolution và version installed trong ~/.m2 có thể khác khi không dùng `-am` hoặc build bị cache.
- Gradle `runtimeClasspath` khác `testRuntimeClasspath`.
- WAR container-provided libraries có thể thay runtime graph và web server.
- Docker image tag có thể stale, vẫn chạy artifact cũ dù local POM đã sửa.
- Shaded/fat JAR có dependency layout khác executable Boot JAR thông thường.
- Library có thể đi theo **hai đường**, một exclusion không giải quyết hoàn toàn.

Kiểm ba lớp: **resolved dependency graph → packaged artifact → running ApplicationContext**. Nếu bất đồng, xác định sai ở build/cache/profile/deployment trước khi đổi code.

## 22. Runbook xử lý incident

Khi thấy startup/server type bất thường sau dependency upgrade:

1. Xác nhận lỗi và ảnh hưởng tới users, security, request routing, latency.
2. Lấy image digest, startup logs của **running pod**, active profiles.
3. Ghi intended type (SERVLET/REACTIVE/NONE) và actual ApplicationContext type.
4. In runtime dependency tree của commit/version tương ứng.
5. Tìm transitive path tới `spring-webmvc` hoặc `spring-webflux` không mong đợi.
6. Đọc Conditions Evaluation Report, externalized properties và programmatic web type overrides.
7. Kiểm real HTTP endpoints/security; nếu có lỗ hổng hoặc lỗi nghiêm trọng, rollback/cô lập theo quy trình.
8. So last-known-good vs bad release graph.
9. Chọn sửa: library POM upstream, targeted exclude, đúng module adapter, hoặc intentional override có tests.
10. Chạy JUnit full Boot integration tests, real HTTP, CORS/security, load smoke.
11. Repackage, rollout canary, monitor 5xx/latency/threads/security metrics.
12. Ghi root cause, dependency path, regression guard và người chịu trách nhiệm cleanup temporary exclusion.

Không thực hiện những thay đổi production ngoài quy trình deploy/rollback được cấp quyền. Bài lab chỉ thao tác local Maven project.

## 23. Những anti-pattern phổ biến

| Anti-pattern | Vì sao sai | Cách đúng |
|---|---|---|
| “POM chỉ có webflux, chắc là REACTIVE.” | Có transitive starter-web | Xem runtime dependency tree |
| “Có reactor-netty JAR nghĩa là server Netty.” | Có thể chỉ là HTTP client connector | Assert ApplicationContext |
| “Có Mono thì controller là WebFlux.” | MVC có reactive adapters | Kiểm DispatcherHandler vs DispatcherServlet |
| “WebClient biến MVC thành WebFlux server.” | Outbound không quyết định inbound | Tách client vs server |
| Chỉ sửa server.port | Port không quyết định web type | Sửa graph/override đúng |
| Chỉ thêm @EnableWebFlux | Không thay web type deduction | Kiểm classpath + Boot config |
| Xóa jar khỏi Maven cache | Build sẽ resolve lại | Exclusion ở dependency path |
| Exclude starter-web mà library cần MVC | Runtime ClassNotFoundException | Tách adapter/sửa library owner |
| Exclude một path nhưng MVC còn ở path khác | Exclusion không global | Recheck toàn runtime graph |
| Chỉ test HTTP 200 | Same @RestController chạy cả hai stacks | Assert reactive/servlet context |
| @WebFluxTest pass => production WebFlux | Slice không chứng minh real app type | @SpringBootTest RANDOM_PORT |
| Ép reactive trong test nhưng không ở prod | Che transitive regression | Match actual config, default-selection guard |
| BOM sẽ tự gỡ duplicate web starters | BOM quản lý versions | Dependency hygiene |
| Override mọi Spring dependencies | Dễ version skew | Dùng Boot-managed versions |
| Tắt Security để app khởi động | Che runtime mismatch, mở endpoints | Sửa Security chain đúng stack |
| CLI app đặt server.port=-1 và nghĩ là NONE | Web context vẫn có thể tồn tại | web-application-type=none |
| Chỉ xem local tree | Image có thể là artifact cũ | Verify packaged/deployed runtime |

## 24. Ma trận QA sau sửa

| Kiểm thử | Kỳ vọng reactive-only service |
|---|---|
| Context instanceof ReactiveWebServerApplicationContext | true |
| Context instanceof ServletWebServerApplicationContext | false |
| Runtime tree có spring-webflux | Có |
| Runtime tree có unwanted spring-webmvc | Không |
| HTTP GET /stack | 200 + reactive=true |
| Library business helper | `gatewayContract=shared` |
| Reactive handlers/router functions | Được mapped đúng |
| Reactive SecurityWebFilterChain | Authentication/authorization đúng |
| Servlet Filter không bị nhầm với WebFilter | Đúng |
| Error/CORS/CSRF policies | Được test qua reactive stack |
| WebClient downstream | Thực thi đúng, timeout/cancellation |
| Blocking I/O trên event loop | Không có, hoặc offload có giới hạn |
| Test classpath vs runtimeClasspath | Phân biệt |
| BOOT-INF/lib | Không còn unexpected MVC jar |
| Docker image digest | Mới, đúng commit |
| Ingress/reverse proxy | Routes/security vẫn hợp đồng |
| Latency/startup/resources | Không regression |
| Rollback | Có phương án trở về bản tốt |

Guard CI quan trọng: **test assert context type phải fail nếu một library kéo MVC trở lại**, ngay cả khi HTTP controller vẫn trả 200. Đừng “fix” test bằng cách bỏ assertion.

## 25. Bài tập tự làm

**A.** Vì sao gateway-lib chỉ có class Java thuần mà vẫn có thể đổi server stack của reactive-app? Trình bày đường transitive dependency.

**B.** Chạy Maven lab trước exclusion. So kết quả test `inboundServerMustBeReactive` và `http200AloneDoesNotProveWebStack`. Giải thích một pass/một fail.

**C.** Exclude `spring-boot-starter-web` tại consumer. Chạy dependency tree và integration tests; nêu bằng chứng app chuyển sang reactive.

**D.** Giả định other-library cũng kéo `spring-webmvc`. Exclusion trên gateway-lib còn đủ không? Thiết kế plan xử lý nhiều paths.

**E.** Bỏ exclusion, thử `spring.main.web-application-type=reactive` và so JAR dependencies. Phân biệt override config với root-cause repair.

**F.** Xây MVC app dùng WebClient outbound và assert SERVLET. Giải thích đây không phải lỗi.

**G.** Tạo CLI `CommandLineRunner` không có web endpoints, dùng `web-application-type=none` và so với `server.port=-1`.

**H.** So bản shared-client v1/v2, thiết kế CI dependency guard và lý do nên sửa shared library POM thay vì consumers đều tự exclude.

## 26. Câu hỏi ôn tập có đáp án

**1. Boot 3.3 chọn stack nào khi cả MVC và WebFlux có mặt?**  
Mặc định là **SERVLET/MVC**.

**2. WebClient có khiến incoming server chuyển sang Netty không?**  
Không. Đây là outbound client API.

**3. Một WebFlux RouterFunction không hoạt động nhưng spring-webflux hiện diện: có thể do đâu?**  
Boot chọn MVC vì `spring-webmvc` cũng có trên runtime classpath.

**4. Lệnh Maven nào tìm đường đưa spring-webmvc vào runtime?**  
`mvn dependency:tree -Dincludes=org.springframework:spring-webmvc` cùng runtime tree.

**5. Gradle dùng lệnh nào?**  
`dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath`.

**6. Một exclusion gỡ dependency khỏi mọi paths?**  
Không. Đường khác có thể kéo artifact trở lại.

**7. Chỉ thấy Tomcat startup log có chắc SERVLET?**  
Là dấu hiệu; context type quyết định, vì WebFlux có thể dùng Tomcat theo config.

**8. Có thể ép reactive bằng property nào?**  
`spring.main.web-application-type=reactive`.

**9. Property đó xóa spring-webmvc khỏi artifact không?**  
Không. Nó chỉ override application web type.

**10. `@EnableWebFlux` có thay Boot WebApplicationType không?**  
Không phải công tắc thay thế; nó ảnh hưởng framework configuration.

**11. Vì sao JUnit HTTP status 200 không đủ xác định đúng stack?**  
`@RestController` hoạt động ở cả MVC và WebFlux.

**12. Vì sao không ép reactive trong regression test nếu production không ép?**  
Vì test sẽ che classpath regression đang cần phát hiện.

**13. App MVC dùng WebClient là sai?**  
Không. Đây là use case hợp lý.

**14. BOM có tự exclude starter-web bắc cầu?**  
Không. BOM quản lý dependency versions.

**15. Servlet SecurityFilterChain thay được SecurityWebFilterChain?**  
Không. Hai stacks có filter/security abstractions khác nhau.

**16. Exclude library sai có thể gây lỗi gì?**  
`ClassNotFoundException`, missing beans/auto-config hoặc feature bị tắt.

**17. Batch app không muốn HTTP listener chọn web type gì?**  
`NONE` nếu không cần web context.

**18. `server.port=-1` có giống `web-application-type=none`?**  
Không. Một cái tắt HTTP listener, một cái chọn non-web context.

**19. Vì sao check packaged JAR/container image?**  
Vì local dependency tree có thể khác artifact thực đang triển khai.

**20. Cách bền vững để phòng tránh library client kéo Servlet server?**  
Tách core/client khỏi MVC adapter, quản lý dependency contract, thêm CI context/dependency guard.

## 27. Tài liệu chính thức

- [Spring Boot 3.3 – Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): MVC ưu tiên khi cả web/webflux present.
- [Spring Boot 3.3 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): detecting web application type và @SpringBootTest.
- [Spring Boot 3.3 – SpringApplication](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): web type/ApplicationContext/startup diagnostics.
- [Spring Boot 3.3 – Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): MVC/Servlet auto-configuration.
- [Spring Boot 3.3 – Embedded Web Servers](https://docs.spring.io/spring-boot/3.3/how-to/webserver.html): Tomcat/Netty defaults, web-application-type=none, server.port=-1.
- [Spring Boot 3.3 – Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html): conditional classpath and conditions report.
- [Spring Boot 3.3 – Calling REST Services](https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html): RestClient/WebClient outbound APIs.
- [Spring Boot 3.3 – Gradle Managing Dependencies](https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html): BOM and version compatibility.
- [Maven – Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html): transitive dependencies, exclusions/scopes.
- [Maven Dependency Plugin – dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html): dependency paths.
- [Gradle – Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): dependencyInsight and runtimeClasspath.
- [Spring Framework – Spring Web MVC](https://docs.spring.io/spring-framework/reference/web/webmvc.html): DispatcherServlet/Servlet model.
- [Spring Framework – Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): DispatcherHandler, WebFilter and reactive model.
- [Spring Security – Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): SecurityFilterChain.
- [Spring Security – Reactive WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): SecurityWebFilterChain.

**Kết luận:** Web stack phải được chứng minh bằng **resolved runtime dependencies + ApplicationContext + HTTP/security behavior**, không chỉ bằng tên Maven starter trong POM hay một controller trả Mono. Khi thư viện bắc cầu đưa MVC vào reactive app, sửa đúng dependency path, kiểm lại classpath và giữ test phát hiện regression.

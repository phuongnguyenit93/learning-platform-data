# Web server, Servlet container và khả năng tương thích khi triển khai WAR

Trong **Java Advance Compatibility Migration**, việc nâng JDK không chỉ tác động đến code của ứng dụng. Một dịch vụ Java web có thể build thành công trên Java 17, chạy ổn khi đóng gói executable JAR, nhưng lại thất bại khi đưa file **WAR** lên Tomcat, Jetty hoặc một application server bên ngoài. Nguyên nhân thường nằm ở ranh giới giữa **JDK runtime, Servlet API, web container, dependency graph, class loader và cấu hình triển khai**.

Một thay đổi đặc biệt quan trọng là việc các API Java EE chuyển từ `javax.servlet.*` sang `jakarta.servlet.*` trong các thế hệ Jakarta EE mới. Một WAR mang servlet/filter được biên dịch theo javax không tự động tương thích với container dùng jakarta, ngay cả khi cả hai cùng chạy trên JDK hiện đại. Tương tự, nếu container đang chạy JDK thấp hơn mức mà ứng dụng yêu cầu, lỗi class-file version có thể phát sinh trước khi framework khởi tạo.

Bài học giải thích các mô hình triển khai Java web, cách chọn đúng tổ hợp JDK–Servlet–container–framework, cấu hình Spring Boot WAR bằng Gradle/Maven, xử lý xung đột class loader/JNDI/TLS/session, và xây dựng quy trình kiểm chứng có khả năng rollback.

## 1. Phân biệt web server, Servlet container và application server

| Thành phần | Chức năng chính | Ví dụ |
|---|---|---|
| HTTP web server/reverse proxy | Nhận HTTP/TLS, reverse proxy, serving static files, routing | Nginx, Apache HTTP Server |
| Servlet container | Quản lý Servlet API, request/response, filters, listeners, webapp lifecycle | Tomcat, Jetty, Undertow ở cấu hình Servlet |
| Embedded Servlet container | Container được ứng dụng nạp như dependency, cùng JVM với app | Embedded Tomcat hoặc Jetty trong Spring Boot |
| Jakarta EE application server | Cung cấp Servlet và tùy profile các dịch vụ enterprise khác | WildFly, Payara, Open Liberty |
| JVM/JDK | Chạy container và application bytecode, cung cấp platform API | JDK 17, JDK 21 |

Sơ đồ thường gặp:

~~~text
Client / browser
       |
       v
Reverse proxy / ingress (nếu có)
       |
       v
Servlet container JVM
       |
       +-- HTTP connector
       +-- Servlet context
       +-- Filter chain
       +-- DispatcherServlet / custom servlet
       |
       v
Application services / repositories / messaging
~~~

Một reverse proxy không tự trở thành Servlet container. Nó có thể định tuyến tới Java process nhưng không thực thi `ServletContext` hoặc nạp Java Servlet classes.

Container chịu trách nhiệm triển khai phần hợp đồng Servlet như request/response objects, filters, listeners, sessions, dispatch, servlet mappings và webapp lifecycle. Những khả năng khác như TLS connector, JSP, WebSocket, clustered sessions, JNDI hoặc metrics còn phụ thuộc implementation và cấu hình.

**Không mặc định mọi Servlet container là Jakarta EE full application server.** Ví dụ Tomcat không tự cung cấp đầy đủ các công nghệ enterprise như một full Jakarta EE platform. Ứng dụng vẫn phải quản lý JPA, transaction integration hoặc messaging providers phù hợp.

## 2. Embedded executable JAR và external WAR

### 2.1. Executable JAR

Trong mô hình Spring Boot embedded server, application được đóng gói thành JAR chứa business classes, framework và container libraries:

~~~bash
java -jar orders-service.jar
~~~

~~~text
orders-service.jar
    |
    +-- Spring application
    +-- Dependencies
    +-- Embedded container libraries
    |
    v
Dedicated JVM
    |
    v
HTTP connector
~~~

Ưu điểm điển hình là application cùng container được version và deploy như một đơn vị; service không phụ thuộc một Tomcat server đã cài sẵn. Điều này phù hợp nhiều container/microservice deployments.

### 2.2. External WAR

Với WAR, một Servlet container có trước sẽ nạp web application:

~~~text
Tomcat / Jetty / application server
    |
    +-- JVM + container API implementation
    +-- HTTP connectors
    +-- Container-provided resources/libraries
    |
    v
orders.war
    |
    +-- WEB-INF/classes
    +-- WEB-INF/lib
    +-- Resources / descriptors
~~~

External container quản lý process, connector port, context root, webapp classloader và deployment lifecycle. Application không được tự giả định mình sở hữu toàn bộ JVM.

### 2.3. Executable WAR là trường hợp riêng

Spring Boot có thể tạo **executable WAR** có launcher, chạy bằng `java -jar orders.war` hoặc triển khai lên external Servlet container khi được cấu hình đúng. Các thư viện container được đánh dấu provided có thể nằm trong vị trí đặc thù như `WEB-INF/lib-provided` để launcher dùng khi chạy trực tiếp, không trở thành libraries của external container theo cách thông thường.

Điều này không áp dụng cho mọi WAR. Một plain Servlet WAR có thể không có `Main-Class`/launcher để chạy bằng `java -jar`.

**Quyết định triển khai JAR hay WAR là quyết định kiến trúc**, không phải việc đổi extension của artifact. Nếu chọn WAR, cần thử với đúng sản phẩm và version container dự định dùng.

## 3. Ba điều kiện tương thích quan trọng

~~~text
Application / framework
  - Java baseline
  - Servlet API types
  - Dependencies and bytecode
              |
              v
Servlet container
  - javax hoặc jakarta
  - Servlet specification level
  - Implementation / classloading
              |
              v
JDK của container process
  - Runtime class-file support
  - Java SE APIs
  - TLS/security/provider policy
~~~

Một deployment hợp lệ cần thỏa **đồng thời**:

1. JDK thực sự chạy process có thể nạp bytecode của framework, application và dependencies.
2. Servlet specification mà container triển khai tương thích với application/framework.
3. Các libraries liên quan khớp namespace và API contract.
4. Cấu hình deployment như context path, DataSource, proxy/TLS, resource loading đúng.

Ví dụ Boot 3 có Java baseline 17. Một container có khả năng chạy trên Java 11 không khiến Boot 3 WAR chạy được khi chính instance container đang sử dụng Java 11. Runtime phải đáp ứng mức tối thiểu của **mọi thành phần**.

## 4. Ranh giới javax.servlet và jakarta.servlet

Đây là khác biệt API lớn trong migration web application.

Trước, với Java EE 8 / Servlet 4:

~~~java
import javax.servlet.Filter;
import javax.servlet.http.HttpServletRequest;
~~~

Sau, với Jakarta Servlet 5 trở lên:

~~~java
import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpServletRequest;
~~~

Dù tên ngắn `Filter` giống nhau, chúng là hai kiểu khác nhau trong Java. Không thể cast `javax.servlet.Filter` thành `jakarta.servlet.Filter`. Một Servlet container cung cấp Jakarta Servlet không tự nhận một Filter implementation compiled cho javax.

| Generation | Servlet specification | Namespace |
|---|---|---|
| Java EE 8 | Servlet 4.0 | `javax.servlet.*` |
| Jakarta EE 9 | Servlet 5.0 | `jakarta.servlet.*` |
| Jakarta EE 10 | Servlet 6.0 | `jakarta.servlet.*` |
| Jakarta EE 11 | Servlet 6.1 | `jakarta.servlet.*` |

### 4.1. Không đổi mọi javax.* thành jakarta.*

Những Java SE APIs sau vẫn sử dụng namespace `javax`:

- `javax.net.ssl.*`.
- `javax.crypto.*`.
- `javax.sql.*`.
- `javax.naming.*`.
- `javax.management.*`.
- `javax.xml.parsers.*`.
- `javax.annotation.processing.*`.

Chỉ chuyển những API thực sự thuộc Jakarta Enterprise và được framework target sử dụng. Chạy tìm-thay tất cả `javax.` có thể làm hỏng source đúng của Java SE.

### 4.2. Thêm javax.servlet-api vào WAR Jakarta không phải cách sửa

Một ứng dụng Boot 3 dùng Spring Framework 6 và Jakarta Servlet có thể chứa third-party filter legacy được biên dịch cho javax. Thêm JAR `javax.servlet-api` có thể làm một số lỗi thiếu class biến mất nhưng **không làm filter đó implement Jakarta Servlet contract**. Giải pháp là nâng/rebuild/thay filter bằng bản tương thích hoặc có kế hoạch chuyển đổi được kiểm chứng.

## 5. Tomcat major versions và Servlet specification

Một số mốc tham khảo:

| Apache Tomcat | Servlet API | Namespace | Java tối thiểu của container |
|---|---|---|---|
| 9.0 | 4.0 | `javax.servlet` | Java 8 |
| 10.0 | 5.0 | `jakarta.servlet` | Java 8 |
| 10.1 | 6.0 | `jakarta.servlet` | Java 11 |
| 11.0 | 6.1 | `jakarta.servlet` | Java 17 |

Đây là các đặc trưng chính của từng dòng Tomcat; vẫn phải kiểm tra **release patch, hỗ trợ bảo mật, framework support matrix và JDK runtime thật** của deployment.

Ví dụ:

~~~text
Spring Boot 2 / Spring Framework 5
    + javax.servlet integrations
    -> Tomcat 9 là một tổ hợp điển hình.

Spring Boot 3 / Spring Framework 6
    + jakarta.servlet integrations
    -> Tomcat 10.1 là một tổ hợp điển hình.

Spring Boot 3 WAR -> Tomcat 9:
    Namespace không tương thích.
~~~

Một Tomcat version mới hơn không tự bảo đảm mọi Spring Boot 3 minor branch đều được upstream kiểm chứng tương thích. Khi chọn version, xem Servlet API level, Java baseline, supported container versions và release notes của application framework.

### 5.1. Tomcat 10 không phải “Tomcat 9 cộng một vài tính năng”

Thay đổi javax → jakarta là thay đổi tên API ở cấp binary. Mã nguồn, annotations, thư viện tích hợp, web descriptors và servlet filters cũ có thể cần migration. Không coi đó là một patch upgrade đơn giản.

## 6. Jetty, Undertow và Jakarta EE application servers

Jetty có các releases/profiles với hỗ trợ Servlet generations khác nhau; một số thế hệ mới dùng environment modules để chọn mức Jakarta/Servlet. Không suy diễn “Jetty N luôn tương đương Tomcat N”. Cần biết **release, environment profile, Java baseline và Servlet specification**.

Undertow có thể là embedded engine hoặc thành phần của application server. Trong trường hợp triển khai WAR trên WildFly hoặc một runtime khác, **support matrix của application server** quan trọng hơn tên và version Undertow riêng lẻ.

Các application servers như WildFly, Payara và Open Liberty có thể cung cấp thêm JNDI, JTA, CDI, Jakarta Persistence và messaging services tùy sản phẩm/profile. Những dịch vụ đó ảnh hưởng dependency scope và resource ownership.

Trước khi triển khai WAR, trả lời:

- Server đang triển khai javax hay jakarta Servlet API?
- Server đã được kiểm chứng với JDK nào?
- Runtime có hỗ trợ JSP/JSTL, WebSocket hoặc HTTP/2 theo yêu cầu?
- Container cung cấp JPA/transaction/validation libraries hay ứng dụng tự đóng gói?
- Classloading delegation và module isolation của server hoạt động ra sao?
- Thư viện Spring/Servlet có được phép đóng gói trong WAR không?

## 7. Java runtime thật của container

Một WAR có class-file major 61 cần JVM hỗ trợ Java 17; major 65 cần JVM hỗ trợ Java 21. Không đủ để chỉ cấu hình compiler release trong source repository.

Ví dụ:

~~~text
Build JDK: Java 21
Compiler --release: 17
WAR class files: major 61
External container JVM: Java 11
=> Runtime không đáp ứng bytecode target của WAR.
~~~

### 7.1. Kiểm tra runtime của process

~~~bash
java -version
javac -version
~~~

Những lệnh này chỉ phản ánh shell hiện tại. Container/server có thể được khởi chạy bởi systemd, Windows Service hoặc script dùng JAVA_HOME khác. Với Tomcat, công cụ như `bin/version.sh` hoặc startup logs có thể cho biết Java Home, runtime version và server version của instance.

### 7.2. Class-file version

~~~bash
javap -verbose -classpath build/classes/java/main \
  com.example.orders.OrdersApplication
~~~

Tìm `major version`. Nhưng một WAR có thể chứa nhiều dependency JAR với bytecode target khác nhau. Kiểm tra các artifact thực sự được đóng gói và nạp, không suy từ một class đại diện.

### 7.3. Compiler target không phải runtime upgrade

Gradle `options.release = 17` hoặc Maven `maven.compiler.release=17` giới hạn cú pháp, bytecode và Java SE API cho source của module được compile. Nó không tự nâng JDK của external Tomcat và không ép dependencies bên ngoài theo cùng target.

## 8. WAR packaging: cấu trúc và classpath

Một WAR thường có:

~~~text
orders.war
├── META-INF/
├── assets/
└── WEB-INF/
    ├── classes/
    │   └── com/example/orders/...
    ├── lib/
    │   ├── spring-*.jar
    │   └── application-libraries.jar
    └── web.xml  (tùy chọn)
~~~

`WEB-INF/classes` chứa compiled application classes, còn `WEB-INF/lib` chứa application libraries. External container cung cấp Servlet implementation và các services mà deployment policy quy định.

Một số lỗi thường phát sinh khi:

- Đóng gói Servlet API hoặc embedded container trùng với server.
- Đánh dấu một library quan trọng là provided nhưng server không cung cấp.
- Embedded/external dependencies cùng xuất hiện ở hai version.
- Code generation/resource loading đặt output sai vị trí.
- WAR thiếu initializer hoặc config cần thiết để bootstrap application.
- Dependency ở test/IDE classpath nhưng không nằm trong WAR.

Dùng `jar tf` để xem nội dung:

~~~bash
jar tf target/orders.war
~~~

Hoặc:

~~~bash
jar tf build/libs/orders.war
~~~

Không chỉ nhìn Maven/Gradle dependency declarations; kiểm tra cả artifact đã được phát hành và các libraries ở server level.

## 9. Spring Boot WAR: entrypoint và initializer

Một Servlet-based Spring Boot application triển khai WAR trên external container có thể mở rộng `SpringBootServletInitializer`:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class OrdersApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(OrdersApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

`configure` cho phép external Servlet container bootstrap Spring application. `main` tiếp tục phục vụ executable deployment khi được đóng gói phù hợp.

Đây là ví dụ cho **Servlet-based Spring Boot**. Đừng giả định ứng dụng reactive-only WebFlux có thể chuyển sang WAR deployment như một Spring MVC application. Kiểm tra quy tắc deployment riêng của framework/Boot release mục tiêu.

### 9.1. Component scan và bootstrap trùng

Nếu `OrdersApplication` nằm sai package hoặc dự án có nhiều `WebApplicationInitializer`/`web.xml` và Spring Boot initializer cùng hoạt động, application context có thể thiếu bean hoặc khởi động trùng. Cần xác định điểm bootstrap duy nhất và ranh giới package scanning.

## 10. Gradle tạo Spring Boot WAR

Ví dụ một Spring Boot Servlet application dùng Java 17:

~~~groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version 'REPLACE_WITH_VERIFIED_BOOT_VERSION'
    id 'io.spring.dependency-management' version 'REPLACE_WITH_COMPATIBLE_PLUGIN_VERSION'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    // External container sẽ cung cấp Servlet engine.
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Hai version là **placeholder**. Chọn bản Boot 3, Gradle wrapper và plugin version có thật và phù hợp support policy; không copy placeholders vào build production.

### 10.1. providedRuntime

`providedRuntime` là cách được Spring Boot Gradle WAR workflow dùng để chỉ container dependency sẽ được cung cấp ở external runtime. Cấu hình này có khác biệt so với đưa Tomcat starter vào `implementation` thông thường.

Với Boot executable WAR, plugin có thể đặt libraries thuộc provided runtime ở `WEB-INF/lib-provided` để tránh gây conflict khi WAR deploy vào external container.

### 10.2. Build WAR

~~~bash
./gradlew clean bootWar
~~~

Task và output path phải được kiểm tra theo plugin version/project. `bootWar` là task phổ biến do Spring Boot Gradle plugin cung cấp khi cấu hình WAR phù hợp, nhưng không mặc định mọi Gradle project có task này.

### 10.3. Nếu dùng Jetty hoặc Undertow

Không tự thay Tomcat starter bằng artifact ngẫu nhiên. Hãy dùng tổ hợp starter/container được Boot release mục tiêu hỗ trợ và xét cách cấu hình provided runtime tương ứng.

## 11. Maven tạo WAR

Ví dụ POM rút gọn nhưng có cấu trúc hoàn chỉnh:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>REPLACE_WITH_VERIFIED_BOOT_VERSION</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>orders-service</artifactId>
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

Đây là ví dụ dành cho Boot parent model, không phải bộ khai báo dependencies đầy đủ của mọi ứng dụng. Nếu dự án dùng corporate parent hoặc import BOM theo cách riêng, cần cấu hình compiler/plugin management phù hợp.

### 11.1. Scope provided

`provided` nghĩa thư viện không được coi là application runtime library đóng gói thông thường cho external container. Với embedded Tomcat trong Spring Boot WAR workflow, Maven packaging có cơ chế riêng dành cho executable WAR.

Đừng đánh dấu tùy tiện driver hoặc ORM library là provided. Nếu server không thực sự cung cấp component đúng version, runtime có thể báo `ClassNotFoundException` hoặc `NoClassDefFoundError`.

### 11.2. Build

~~~bash
mvn clean package
~~~

Kiểm tra artifact dưới `target`, WAR manifest và các libraries thực tế sau khi plugin xử lý.

## 12. web.xml, servlet registration và Jakarta descriptor

Servlet 3.0 trở đi hỗ trợ registration mechanisms không nhất thiết phải có `WEB-INF/web.xml`. Spring Boot WAR thường dựa vào initializer để bootstrap application context.

Nếu ứng dụng legacy có `web.xml`, phải kiểm tra:

- Schema và namespace của descriptor.
- Servlet/filter/listener class names.
- Mappings và thứ tự filters.
- Session configuration và security constraints.
- Context parameters.
- Error pages và welcome files.
- Container-specific descriptors.

Ví dụ descriptor cho Jakarta Servlet 6.0:

~~~xml
<web-app xmlns="https://jakarta.ee/xml/ns/jakartaee"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="https://jakarta.ee/xml/ns/jakartaee
                             https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
         version="6.0">

    <display-name>Orders Application</display-name>

</web-app>
~~~

Không tự thêm file này cho mọi Boot WAR. Nó chỉ minh họa cấu trúc descriptor nếu ứng dụng thực sự cần dùng.

### 12.1. Registration trùng

Một WAR có thể đồng thời dùng annotations, `ServletContainerInitializer`, `WebApplicationInitializer`, `web.xml` và Spring-managed registration beans. Khi migration, cấu hình trùng có thể làm Servlet/Filter chạy hai lần hoặc tạo nhiều contexts. Cần xác định owner của từng registration.

## 13. Class loader của external container

External container có thể dùng nhiều lớp class loader:

~~~text
JDK bootstrap / platform
       |
       v
Container common / shared classes
       |
       v
Web application class loader
       |
       +-- WEB-INF/classes
       +-- WEB-INF/lib/*.jar
~~~

Sơ đồ chỉ mang tính khái niệm. Thứ tự delegation thực tế phụ thuộc container, cấu hình parent-first/child-first và các ngoại lệ dành cho platform/Servlet APIs.

Những vấn đề hay gặp:

- Một class xuất hiện ở container library và WAR library với hai version.
- Type cùng tên được hai class loaders khác nhau định nghĩa.
- Servlet API bị đưa vào WAR và xung đột implementation do server cung cấp.
- Thread context class loader (TCCL) không thấy provider/resource.
- Application server dùng module layers riêng để cách ly thư viện.
- Background thread giữ class loader của WAR cũ sau undeploy.

**Java type identity không chỉ là fully qualified name, mà còn liên quan defining class loader.** Hai classes cùng tên do hai loaders khác nhau nạp có thể không tương thích.

### 13.1. Ví dụ lỗi đáng ngờ

~~~text
ClassCastException:
com.example.Plugin cannot be cast to com.example.Plugin
~~~

Trường hợp này có thể xảy ra khi `com.example.Plugin` tồn tại dưới hai defining class loaders. Cần kiểm tra JAR origin, classloader hierarchy và container modules, thay vì chỉ sửa Java inheritance.

## 14. Trùng Servlet API và version conflicts

Giả sử external Tomcat 10.1 cung cấp Jakarta Servlet 6.0 nhưng WAR đóng gói một API JAR cũ hoặc legacy `javax.servlet-api`.

Sự tồn tại của hai thư viện có thể gây:

- Class resolution không mong muốn.
- `LinkageError`, `NoSuchMethodError` hoặc `AbstractMethodError`.
- Filter/Servlet không implement đúng interface.
- Reflection lookup không phù hợp.
- Lỗi xuất hiện muộn khi request chạy vào một đường code cụ thể.

Một số container có bảo vệ class loading đối với API packages, nhưng **không nên dựa vào sự bảo vệ ngầm** như một phương án version management.

### 14.1. Không copy JAR vào server-wide lib tùy tiện

Đưa JAR vào classpath chung của Tomcat/application server có thể tác động mọi WAR triển khai chung, kể cả ứng dụng không liên quan. Những libraries do container sở hữu cần có version policy, owner và kiểm thử tương thích rõ.

### 14.2. Kiểm tra resolved graph

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jakarta.servlet \
  --configuration runtimeClasspath
~~~

Maven:

~~~bash
mvn dependency:tree
~~~

Đối chiếu dependency graph với `WEB-INF/lib` và libraries bên ngoài WAR. Chỉ nhìn source imports không đủ.

## 15. JNDI DataSource và cấu hình server-managed resources

Trong embedded Boot JAR, Spring thường tạo DataSource dựa vào properties. Khi dùng external container, team có thể chọn DataSource do container cung cấp qua JNDI.

Ví dụ Boot property:

~~~properties
spring.datasource.jndi-name=java:comp/env/jdbc/OrdersDB
~~~

Container phải khai báo resource tương ứng, cung cấp driver/connection pool và quyền truy cập cần thiết.

| Mô hình | Trách nhiệm | Rủi ro |
|---|---|---|
| Spring-managed DataSource | Ứng dụng mang driver và quản lý pool | Phải version driver/pool trong WAR |
| Container-managed JNDI DataSource | Container/platform quản lý resource | Cần config name, driver placement, credentials, pool policy |
| Full application server resource | Server có thể thêm transaction manager và các services khác | Framework integration và server module conflicts |

`javax.naming.*` vẫn là Java SE API và không chuyển thành `jakarta.naming.*`. Không thay imports sai khi đổi Servlet API.

### 15.1. Lỗi thường gặp

~~~text
javax.naming.NameNotFoundException:
Name [jdbc/OrdersDB] is not bound in this Context
~~~

Cần kiểm tra resource declaration và naming context **trong container**, không phải chỉ đổi Maven dependency.

### 15.2. Transaction management

Tomcat Servlet container không mặc định cung cấp mọi chức năng JTA của full application server. Nếu ứng dụng cần distributed transactions, xem riêng transaction manager và các Jakarta EE resources tương ứng.

## 16. Context root, connector port và đường URL

Trong embedded Boot mode, có thể dùng:

~~~properties
server.port=8080
server.servlet.context-path=/orders
~~~

Trong external WAR, connector port và context root thường do **container deployment configuration** quản lý. Context root có thể lấy từ WAR filename hoặc context descriptor.

Ví dụ:

~~~text
Embedded JAR:
  http://host:8080/orders/api/items

External WAR orders.war:
  http://host:8080/orders/api/items
~~~

Hai URL có thể giống nhau nhưng do các lớp cấu hình khác nhau tạo ra. Không sửa `server.port` rồi kỳ vọng thay được port của external Tomcat.

Các yếu tố cần rà:

- WAR context root.
- Servlet mapping.
- Spring MVC paths.
- Spring Security matchers.
- Reverse proxy path prefix/rewrite.
- Actuator endpoint base path.
- Cookie path và redirect target.

### 16.1. Forwarded headers

Nếu TLS terminate ở ingress hoặc reverse proxy, ứng dụng có thể cần biết URL gốc qua `Forwarded`/`X-Forwarded-*` headers hoặc container proxy configuration. Chỉ tin forwarded headers từ proxy được kiểm soát; không mở trust cho client tự khai báo host/protocol tùy ý.

## 17. TLS và HTTP connector compatibility

Khi đổi deployment model, nơi kết thúc TLS có thể thay đổi:

~~~text
Client
  |
  | TLS #1
  v
Ingress / reverse proxy
  |
  | HTTP hoặc TLS #2
  v
Servlet container
  |
  v
Application
~~~

Cần tách:

- **Inbound TLS** ở proxy hoặc container.
- **TLS từ proxy tới backend** nếu có.
- **Outbound TLS** từ Java application tới API/database/broker.

Mỗi kết nối có certificate, truststore/keystore và security policy riêng.

Khi nâng container/JDK, xác minh TLS versions, cipher suites, certificate chain, hostname verification, mTLS, ALPN/HTTP2, connection timeout, header limits, keep-alive, multipart/body limits và logging.

Nếu ứng dụng chạy WAR trên container nhưng lỗi HTTP 400/431 trước khi Spring controller nhận request, nguyên nhân có thể là HTTP parser/connector policy mới, không phải controller code.

## 18. Custom Servlet Filter trên Jakarta

Ví dụ một Filter dùng Jakarta Servlet:

~~~java
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import java.io.IOException;

public final class RequestAuditFilter implements Filter {

    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        // Thực hiện audit/correlation theo hợp đồng ứng dụng.
        chain.doFilter(request, response);
    }
}
~~~

Nếu application vẫn import `javax.servlet.Filter`, nó không thể hoạt động như một Jakarta Filter đúng hợp đồng.

Các hình thức registration có thể gồm `web.xml`, servlet annotations, Spring `FilterRegistrationBean` hoặc container-specific mechanism. Khi chuyển embedded JAR sang WAR, phải kiểm tra:

- Filter được đăng ký đúng một lần.
- Order giữa CORS, auth, logging, tracing, compression phù hợp.
- Request/response wrapper types thuộc đúng namespace.
- Filter có chạy khi endpoint lỗi hoặc async dispatch không.
- Unregister/cleanup thực hiện đúng khi undeploy.

## 19. Spring Security khi triển khai WAR

Spring Security thường vận hành thông qua servlet filter chain. Khi chuyển Boot 2/Security 5 sang Boot 3/Security 6 và external container, cần đồng thời cập nhật namespace, cấu hình và test policy.

Ví dụ Security 6:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
        );
        http.httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Đây chỉ là ví dụ cấu trúc, chưa mô tả authentication/CSRF/CORS cho hệ thống thực.

Rủi ro khi deployment:

- Security Filter không được đăng ký hoặc đăng ký hai lần.
- Request matchers không còn khớp context path/proxy mappings.
- Cookie/session behavior đổi.
- Redirect URL sai scheme/host.
- OAuth/SSO adapter chỉ hỗ trợ `javax.servlet`.
- Test chỉ kiểm tra happy path mà không kiểm tra endpoints phải bị cấm.

**Không xóa filter chain hoặc permit-all để “chữa” lỗi WAR startup.** Phải sửa dependencies/registration và bảo vệ nguyên tắc authorization.

## 20. Session, cookies và session replication

WAR có thể được restart/redeploy độc lập hoặc chạy nhiều nodes trên một external container cluster. Những yếu tố cần kiểm tra:

- `HttpSession` lifecycle và expiration.
- Session cookie name/domain/path.
- Secure, HttpOnly, SameSite.
- Sticky sessions / load balancer routing.
- External session store.
- Session replication format.
- Session ID rotation sau login.
- In-memory sessions trong rolling deployment.
- Thay đổi serialized object class giữa hai phiên bản.

### 20.1. Không mặc định session data cũ đọc được

Khi nâng framework, Servlet namespace hoặc container, serialized session attributes có thể không tương thích. Ví dụ một class cũ chứa `javax.servlet.*` reference hoặc thay cấu trúc sau nâng Boot 3 có thể làm session deserialization lỗi.

Cần quyết định: drain sessions, chấp nhận login lại, dùng external session store hỗ trợ hai versions hoặc có cơ chế chuyển đổi dữ liệu với tests rõ ràng.

### 20.2. Login/cookie regression

Một deployment có thể trả API 200 nhưng login redirect hoặc cookie Path sai do context root/proxy. Phải test browser flow qua ingress production-like.

## 21. JSP, JSTL và views

Legacy WAR applications có thể dùng JSP/JSTL:

- JSP engine phải tương thích container và Servlet/Jakarta release.
- JSTL libraries/tag handlers có thể cần chuyển sang Jakarta equivalents.
- Custom JSP tags dùng `javax.servlet.jsp.*` có thể không còn hợp runtime Jakarta.
- View resolver và resource paths có thể khác embedded deployment.
- JSP có giới hạn packaging khác giữa executable JAR và WAR ở một số framework releases.

Không quy mọi lỗi 404/JSP 500 cho javax/jakarta; xem logs của JSP compiler, view resolver và WAR resource layout.

Nếu project chuyển từ external WAR sang executable JAR, hãy xác minh framework có hỗ trợ JSP trong packaging mode đó, không coi hai formats thay thế hoàn toàn cho nhau.

## 22. WebSocket, async Servlet và streaming

Ngoài synchronous REST, kiểm tra:

- Jakarta WebSocket API level.
- HTTP Upgrade handshake qua proxy.
- Idle timeouts và heartbeats.
- Servlet `AsyncContext` lifecycle.
- Server-Sent Events và streaming.
- HTTP2/ALPN.
- Request buffering và backpressure.
- Load balancer sticky routing nếu service giữ connection state.

Một WebSocket integration compiled cho javax có thể không tương thích với Jakarta container. Không dùng test HTTP GET thông thường để kết luận realtime endpoints đã an toàn.

## 23. Thread pools và classloader leak khi redeploy

External container thường chạy nhiều web applications trong một JVM. Nếu một WAR tạo background threads, scheduled executors hoặc caches giữ reference tới classloader cũ, một lần redeploy có thể tạo memory leak.

Những dấu hiệu:

- Threads từ version cũ vẫn chạy.
- JDBC drivers hoặc connection pools không cleanup.
- `ThreadLocal` giữ đối tượng từ webapp cũ.
- JMX MBean registration không được gỡ.
- Timer/scheduler tiếp tục giữ classloader.
- Static references từ container-level library trỏ vào webapp classes.

Ví dụ lifecycle bean:

~~~java
import jakarta.annotation.PreDestroy;
import java.util.concurrent.ExecutorService;

public final class BackgroundJobOwner {

    private final ExecutorService executor;

    public BackgroundJobOwner(ExecutorService executor) {
        this.executor = executor;
    }

    @PreDestroy
    public void stop() {
        executor.shutdown();
    }
}
~~~

Đoạn code giả định bean sở hữu executor. Không shutdown shared/thread pool do container quản lý nếu nó không thuộc ownership của bean.

Test **deploy → undeploy → redeploy** nhiều lần trong môi trường kiểm thử nếu hệ thống dùng hot deployment, thay vì chỉ xác minh startup lần đầu.

## 24. Những third-party dependencies dễ bị bỏ sót

Một WAR có thể chứa:

- Servlet filters và SSO adapters.
- Spring MVC extensions.
- OpenAPI/Swagger UI integrations.
- Multipart/upload parsers.
- JSP/JSTL tags.
- WebSocket libraries.
- JPA/validation providers.
- Logging/tracing/metrics Servlet instrumentations.
- Application server vendor extensions.
- Java agents nạp từ startup options.
- Native/JNI libraries.
- Internal shared libraries đã compile theo javax.

Một thư viện nói “hỗ trợ Java 17” chưa chắc hỗ trợ Jakarta Servlet. Cần xem **Java baseline + Servlet namespace/version + Spring/framework major version** riêng biệt.

Nếu có thư viện legacy không còn bản Jakarta, cân nhắc nâng/thay thư viện trước. Một số migration transformers có thể biến đổi references, nhưng không nên kỳ vọng sửa được semantics, reflection strings, serialization, proprietary API và các cấu hình đặc biệt. Nếu dùng transformer, phải kiểm soát provenance, license, test evidence và kế hoạch loại bỏ.

## 25. Classloader và dependency triage

Khi gặp:

~~~text
java.lang.NoClassDefFoundError: javax/servlet/Filter
  at com.vendor.legacy.SecurityFilter...
~~~

trong WAR Boot 3 trên Tomcat 10.1, các bước điều tra:

1. Xác định JAR chứa `com.vendor.legacy.SecurityFilter`.
2. Xác nhận nó compiled cho `javax.servlet.Filter`.
3. Tra phiên bản vendor hỗ trợ Jakarta Servlet/Spring Boot 3.
4. Thay hoặc cập nhật library.
5. Xóa legacy API JAR không còn cần.
6. Rebuild WAR, xem `WEB-INF/lib`.
7. Deploy lên đúng container/JDK.
8. Kiểm tra auth/authorization behavior, không chỉ startup.

Nếu lỗi là `NoSuchMethodError` của servlet/classloader, cần xem version API nào được load thực tế. Nếu lỗi là `UnsupportedClassVersionError`, kiểm tra JVM chạy container thay vì thêm module exports.

## 26. Pipeline build và kiểm tra WAR

Một quy trình đề xuất:

~~~text
Source + pinned dependency graph
             |
             v
Build tool + compiler JDK
             |
             v
Compile, tests, static analysis
             |
             v
Build WAR
             |
             v
Inspect WAR + checksum
             |
             v
Deploy WAR to staging container/JDK
             |
             v
Startup, security, data, session tests
             |
             v
Production rollout + monitoring
~~~

Khi external container được quản lý bởi platform team, phải version cả:

- WAR artifact.
- Container release/patch.
- JDK vendor/runtime version.
- Common libraries.
- TLS proxy configuration.
- JNDI resources, credentials và pool settings.
- Context root/connector policy.
- Deployment options và environmental secrets.

Nếu chỉ lưu checksum của WAR mà không biết Tomcat/JDK/common-lib versions, việc tái hiện lỗi production có thể rất khó.

### 26.1. Stale exploded WAR

Một số container tự giải nén WAR vào thư mục ứng dụng. Trong các cách triển khai cụ thể, thư mục exploded cũ hoặc cached resources có thể làm application vẫn chạy code version trước. Đối chiếu artifact, deployment logs và directory/timestamp theo hướng dẫn container.

## 27. Test embedded không thay external WAR integration tests

Một test `@SpringBootTest` với embedded server hoặc MockMvc có giá trị cho business/web contract, nhưng **không chứng minh** WAR hoạt động trong classloader và connector của external Tomcat/Jetty.

| Test | Bằng chứng chính |
|---|---|
| Unit tests | Business logic |
| `@WebMvcTest` / MockMvc | MVC route/filter behavior trong test context |
| `@SpringBootTest` với random port | Integration với embedded server |
| External WAR staging deploy | Servlet container lifecycle, classloading, resources |
| End-to-end qua ingress/proxy | TLS, redirects, cookies, routing |
| Redeploy/restart tests | Cleanup, session/state recovery |
| Performance/failover tests | Resource limits và vận hành |

Nên dùng **chính artifact WAR dự định phát hành** để test external deployment, tránh build một WAR khác sau khi đã kiểm chứng.

## 28. Bộ kiểm thử sau deploy

Một test suite gần production cần gồm:

1. **Startup:** server và application context khởi tạo không lỗi.
2. **Deployment:** đúng WAR version/checksum và context root.
3. **Health:** readiness/liveness phản ánh dependency state.
4. **Routing:** paths, trailing slash, query parameters và HTTP methods.
5. **Serialization:** JSON/XML/date/numbers, error response contract.
6. **Validation:** invalid input được xử lý đúng.
7. **Security:** public/private paths, login, permissions, CSRF/CORS, token validation.
8. **Sessions:** cookie attributes, login, logout, restart, failover.
9. **Persistence:** JNDI/DB/pool, transactions và query correctness.
10. **Static/JSP:** resources, templates và tag libraries nếu dùng.
11. **WebSocket/async:** upgrade, disconnect/reconnect và timeout.
12. **Proxy/TLS:** forwarded host/scheme, certificate/HTTP2 nếu dùng.
13. **Resource limits:** large headers/body, multipart upload và timeouts.
14. **Metrics:** access logs, tracing, alerts và actuator/management endpoints.
15. **Redeploy:** không còn background threads/classloader leaks.
16. **Performance:** startup, throughput, p95/p99, heap, GC.
17. **Rollback:** artifact cũ hoạt động với state/schema theo kế hoạch.

Không dùng health endpoint 200 làm tiêu chí duy nhất để kết luận application đã tương thích.

## 29. Rolling deployment, data và rollback

Trong một rolling update có thể tồn tại đồng thời:

~~~text
Load balancer
  |         |
  v         v
Node A    Node B
WAR N     WAR N+1
~~~

Những điều cần xem:

- API clients có tương thích cả hai server versions không?
- Database schema có phục vụ được phiên bản cũ và mới không?
- Session replication/deserialization có tương thích không?
- Message payloads/cache keys có cần versioning không?
- Old/new nodes có cùng JDK/container khác nhau không?
- Metrics/logs có xác định được node/version bị lỗi không?
- Khi rollback, dữ liệu do version mới ghi có còn đọc được không?

**Rollback không phải chỉ copy WAR cũ về.** Nếu migration đã đổi database schema, session format hoặc shared state, runtime cũ có thể không phục hồi được dữ liệu mới.

### 29.1. Session draining

Đối với các ứng dụng dựa vào in-memory session, một rollout có thể yêu cầu sticky sessions, load balancer draining hoặc chấp nhận người dùng phải đăng nhập lại. Đây là quyết định vận hành cần được thông báo, không nên mặc định container tự giải quyết.

## 30. Security hardening khi nâng web container

Một migration an toàn cần giữ hoặc tăng mức bảo mật:

- Container/JDK security patches.
- HTTPS/TLS certificate chain và cipher policies.
- HTTP request parser constraints.
- Header/body size limits.
- Timeouts và DoS protections.
- Secure, HttpOnly và SameSite cookie policy.
- Session fixation protection.
- Spring Security authorization.
- Management/JMX/admin console access controls.
- Directory listing và default applications.
- Java serialization và deserialization trust boundaries.
- Shared libraries và native dependencies.
- Audit logs và secrets handling.

Một container cũ không còn security fixes là rủi ro dù WAR hiện vẫn chạy được. Không nên bỏ kiểm tra TLS, mở mọi request hay giảm HTTP validation chỉ để đạt compatibility.

## 31. Các mã lỗi HTTP sau thay container

| Biểu hiện | Tầng có thể gây lỗi |
|---|---|
| 400 Bad Request | HTTP parser, invalid header/path, proxy/container constraints |
| 401 Unauthorized | Authentication filter, session/token |
| 403 Forbidden | Authorization, CSRF, CORS policy |
| 404 Not Found | Context root, servlet mapping, proxy rewrite, resources |
| 413 Payload Too Large | Proxy/container request size limit |
| 431 Request Header Fields Too Large | Header size limits |
| 500 Internal Server Error | App exception, JSP, JNDI, classloading |
| 502 Bad Gateway | Proxy không kết nối được backend |
| 503 Service Unavailable | App/container không ready, ingress routing |
| 504 Gateway Timeout | Proxy/backend timeout, slow request |

Đây là hướng điều tra, không phải quy tắc tuyệt đối. Luôn xem logs của **proxy, container và Spring application** để biết request bị từ chối ở tầng nào.

Một request không xuất hiện trong application access log có thể đã bị chặn tại ingress hoặc connector, vì vậy sửa controller code sẽ không giải quyết.

## 32. Mẫu ma trận lựa chọn nền tảng

| Tiêu chí | Câu hỏi cần trả lời |
|---|---|
| JDK | Java runtime nào chạy server process? |
| Framework | Spring Boot/Spring Framework release nào đang dùng? |
| Servlet API | Version và namespace `javax`/`jakarta` nào? |
| Container | Tomcat/Jetty/Undertow/application server release và patch nào? |
| Packaging | Embedded JAR, plain WAR hay executable WAR? |
| Provided libs | Container cung cấp chính xác libraries nào? |
| Servlet initialization | `SpringBootServletInitializer`, descriptor và registrations ra sao? |
| Classloading | Parent/child loading, common libs, isolation policies? |
| Context root | Ai kiểm soát root path và rewrites? |
| JNDI/resources | DataSource, transactions và secrets do ai sở hữu? |
| TLS/network | Proxy, SNI, certificates, HTTP2, forwarded headers? |
| State | Session/cookies, serialized attributes, clustering? |
| Security | Filter chain, authn/authz, CSRF/CORS, management exposure? |
| Operations | Logs, tracing, metrics, readiness, redeploy, rollback? |

Không chỉ xác định tổ hợp chạy được về mặt kỹ thuật; cần xem cả vendor support, patching, security lifecycle và năng lực vận hành lâu dài.

## 33. Quy trình migration WAR theo các giai đoạn

### Giai đoạn A — Chụp baseline

Ghi JDK, container, framework, WAR checksum, dependency graph, context root, JNDI, proxy/TLS, sessions, servlet filters, security rules, metrics và test results.

### Giai đoạn B — Chọn đích có compatibility evidence

Chọn JDK target, Servlet generation, container branch và framework release được hỗ trợ. Đặc biệt xác định ranh giới javax → jakarta và những third-party libraries cần thay.

### Giai đoạn C — Chuyển mã nguồn và build

Nâng toolchain, servlet imports, dependencies, generated code, configuration và WAR packaging. Với Boot, khai báo `SpringBootServletInitializer` và `provided/providedRuntime` theo hướng dẫn của phiên bản đang dùng.

### Giai đoạn D — Kiểm tra artifact

Quan sát `WEB-INF/lib`, duplicate dependencies, class-file major, web descriptors và resources. Kiểm tra không nhúng secrets hoặc container implementation sai phạm vi.

### Giai đoạn E — Staging trên đúng container

Deploy WAR lên cùng JDK/container image và gần đúng network topology của production. Xác minh startup, JNDI, HTTP, security, persistence, sessions, JSP/WebSocket và tracing.

### Giai đoạn F — Stress, restart và rollback

Thử redeploy, restart, load balancer failover, session behavior, long-lived connections và performance. Thiết kế rollback dữ liệu và schema trước khi deploy production.

### Giai đoạn G — Rollout

Sử dụng canary/rolling khi phù hợp. Quan sát error rate, authentication failures, database pool, classloader warnings, CPU/heap và SLO.

### Giai đoạn H — Dọn nợ kỹ thuật

Gỡ javax API dependencies không còn cần, duplicate JARs, legacy server config và các compatibility workarounds tạm thời. Cập nhật runbook/ownership.

## 34. Checklist trước khi kết luận WAR đã tương thích

- [ ] JDK process chạy container đáp ứng Java baseline của framework và bytecode.
- [ ] Servlet API specification/namespace phù hợp container và application.
- [ ] Container branch/patch còn hỗ trợ bảo mật.
- [ ] Không trộn javax và jakarta Servlet types trong integration paths.
- [ ] Build tool/Java compiler release và Java agents được xác minh.
- [ ] WAR chứa đúng `WEB-INF/classes`, `WEB-INF/lib` và resources.
- [ ] Container implementation được đánh dấu provided hợp lý.
- [ ] Spring Boot WAR initializer/deployment descriptor đã được cấu hình đúng.
- [ ] Container shared libraries và classloader model được kiểm kê.
- [ ] Context path, proxy rewrite, forwarded scheme/host và redirects đúng.
- [ ] TLS/HTTP connector, header/body limits và timeouts đã test.
- [ ] JNDI DataSource và resource ownership đúng.
- [ ] Servlet filters và Security filter chain không bị thiếu hoặc đăng ký trùng.
- [ ] Login/session/cookie/CSRF/CORS và authorization được kiểm tra.
- [ ] JSP/JSTL/WebSocket/async flows đã test nếu dự án dùng.
- [ ] Integration tests chạy trên WAR thật trong external container.
- [ ] Undeploy/redeploy và resource cleanup được thử.
- [ ] Metrics, tracing, logs và alerts hoạt động.
- [ ] Performance và startup readiness được so sánh baseline.
- [ ] Rolling upgrade, schema/session compatibility và rollback có phương án.

Checklist hướng dẫn kỹ thuật, **không phải kết quả QA của một hệ thống cụ thể**.

## 35. Mẫu báo cáo migration

~~~yaml
warMigration:
  application: orders-service
  from:
    java: "11"
    framework: "Spring Boot 2.x"
    servletApi: "javax.servlet"
    container: "Tomcat 9.x"
  target:
    java: "17"
    framework: "Spring Boot 3.x"
    servletApi: "jakarta.servlet"
    container: "Tomcat 10.1.x"
  packaging:
    mode: war
    initializerReviewed: false
    dependenciesReviewed: false
    jarOriginsReviewed: false
  platform:
    jndiReviewed: false
    contextPathVerified: false
    proxyTlsVerified: false
    classloaderReviewed: false
  tests:
    startupPassed: false
    httpContractPassed: false
    securityPassed: false
    sessionPassed: false
    persistencePassed: false
    redeployPassed: false
    observabilityPassed: false
  rollout:
    canaryPlanned: false
    rollbackPlanned: false
  owner: platform-team
  status: under-review
~~~

Các versions và trạng thái chỉ minh họa. Trong dự án thật phải ghi exact release/patch, JDK image, artifact checksum, logs và kết quả tests thực tế trước khi đánh dấu hoàn tất.

## 36. Những sai lầm dễ gặp

**“WAR chạy trên Java 17 là đủ.”** Không đủ: Servlet API và container phải khớp framework. Boot 3 không tương thích trực tiếp với javax Servlet container chỉ vì JDK mới.

**“Tomcat 10 chỉ là Tomcat 9 mới hơn.”** Không đúng: namespace đã chuyển từ javax sang jakarta trong thế hệ Tomcat 10.

**“Thêm javax.servlet-api.jar để sửa Jakarta incompatibility.”** Không biến legacy Filter thành Jakarta Filter. Phải đổi library/API contract.

**“Test embedded JAR pass nghĩa external WAR pass.”** External container có classloader, connectors và resources khác; phải deploy WAR thật để test.

**“server.port trong application.yml quyết định port Tomcat external.”** HTTP connector thuộc container trong mô hình WAR bên ngoài.

**“provided nghĩa mọi dependency đều có sẵn ở server.”** Chỉ dùng khi runtime thực sự cung cấp dependency đó và team đã xác minh version.

**“Mọi WAR đều executable qua java -jar.”** Chỉ những WAR có launcher và packaging phù hợp mới làm được.

**“Startup thành công nghĩa chức năng ổn.”** Nhiều lỗi JNDI, repository, security matcher, JSP và WebSocket chỉ lộ khi chức năng được gọi.

**“Rollback chỉ là copy WAR cũ.”** Session data, database schema và message formats có thể đã đổi; phải có kế hoạch rollback state.

## 37. Nguyên tắc tổng kết

- **Web server, Servlet container, application server và JDK là các lớp khác nhau**, mỗi lớp có version và contract cần kiểm chứng.
- **WAR deployment phải khớp JDK + Servlet namespace/version + container + framework + dependencies.**
- **`javax.servlet` và `jakarta.servlet` không tương thích nhị phân**; thêm API JAR không thay thế migration code/library.
- **Tomcat 9 và 10.x nằm ở hai thế hệ namespace khác nhau.** Không coi đổi major version là patch.
- **Java baseline của ứng dụng có thể cao hơn Java minimum của container**; runtime phải đáp ứng tất cả.
- **Executable JAR và external WAR có classloading/configuration/lifecycle khác nhau**; cần test riêng.
- **WAR packaging và dependency scope phải tách application-owned và container-owned libraries** để tránh conflict.
- **JNDI, context root, TLS, HTTP connector và session behavior có thể do external container hoặc proxy quản lý**.
- **Filter registration, Spring Security, JSP, WebSocket và Javax/Jakarta integrations** là những điểm cần kiểm tra hành vi.
- **Redeploy, rolling upgrade và rollback có trạng thái** là phần thiết yếu của khả năng vận hành WAR.
- **Kiểm chứng phải chạy trên đúng WAR, đúng JDK/container image và network topology**, không chỉ nhìn build pass.

Trong Java Advance Compatibility Migration, triển khai WAR an toàn đòi hỏi nhiều hơn việc biên dịch mã Java với JDK mới. Nhóm cần đảm bảo **ứng dụng, Servlet API, Servlet container và JVM thuộc một tổ hợp tương thích**, kiểm soát libraries theo classloader/runtime ownership và xác minh các hợp đồng HTTP, dữ liệu, bảo mật cùng lifecycle trên môi trường thật. Khi các ranh giới này được thiết kế rõ ràng, nâng cấp nền tảng web sẽ dễ truy vết lỗi, triển khai và rollback hơn.

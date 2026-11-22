# Chuẩn bị SpringBootServletInitializer và lớp ứng dụng để triển khai WAR

## 1. Mục tiêu và bối cảnh thực tế

Ứng dụng Spring Boot thường được chạy bằng `java -jar` với **web server nhúng**. Tuy nhiên, trong môi trường doanh nghiệp, ứng dụng web có thể phải chạy trong **Servlet container bên ngoài** như Apache Tomcat do đội vận hành quản lý. Khi ấy, ứng dụng thường được đóng gói dạng **WAR (Web Application Archive)** và Spring Boot cần một cơ chế để khởi tạo ApplicationContext thông qua lifecycle của container.

Cơ chế quan trọng là `SpringBootServletInitializer`. Với một ứng dụng Spring MVC/Servlet, lớp này cho phép external container khởi động Spring Boot khi WAR được triển khai. **Đổi `.jar` thành `.war` là chưa đủ**: phải chuẩn bị đúng application class, cấu hình packaging và đặt servlet engine dependency vào scope phù hợp.

Mục tiêu học tập:

1. Phân biệt hai đường khởi động: `main(String[] args)` và `SpringBootServletInitializer.configure(SpringApplicationBuilder)`.
2. Viết một lớp Java 17+ có `@SpringBootApplication`, kế thừa `SpringBootServletInitializer`, override `configure` và vẫn chạy được bằng `java -jar`.
3. Tạo WAR bằng Maven (`<packaging>war</packaging>`, Tomcat `provided`) hoặc Gradle (plugin `war`, `providedRuntime`, task `bootWar`).
4. Kiểm tra `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided` và nhận ra đúng executable WAR.
5. Triển khai lên Tomcat tương thích, kiểm tra URL theo context root và đọc log khi deploy fail.
6. Hiểu tương thích Jakarta Servlet, Java runtime, component scan, bean registration và các bước kiểm chứng CI.

**Phiên bản minh họa:** Spring Boot 3.3.5, Java 17, Tomcat 10.1, Maven/Gradle Wrapper tương thích. Đây là một ví dụ có phạm vi version rõ ràng, không phải đề xuất dùng bản phần mềm mới nhất. Khi triển khai thực tế hãy theo ma trận hỗ trợ và chính sách nâng cấp của dự án.

## 2. Hiểu đúng hai đường khởi động

### 2.1. Khi chạy executable JAR hoặc executable WAR

~~~text
java -jar application.war
    |
    v
Spring Boot Launcher
    |
    v
Application.main(String[] args)
    |
    v
SpringApplication.run(Application.class, args)
    |
    v
Spring ApplicationContext + embedded Tomcat
    |
    v
DispatcherServlet -> Controller
~~~

Lúc này **ứng dụng tự khởi động servlet engine nhúng**. `server.port` được Spring Boot sử dụng cho embedded server, và `main` là điểm vào trực tiếp. Chỉ chạy embedded server thì không cần `SpringBootServletInitializer`.

### 2.2. Khi Tomcat bên ngoài triển khai WAR

~~~text
External Tomcat 10.1 đã chạy
    |
    v
Triển khai war-demo.war vào web application context
    |
    v
Servlet startup phát hiện WebApplicationInitializer
    |
    v
SpringBootServletInitializer.onStartup(ServletContext)
    |
    v
configure(SpringApplicationBuilder)
    |
    v
Spring ApplicationContext + đăng ký DispatcherServlet
    |
    v
HTTP /war-demo/ping -> Controller
~~~

External Tomcat có **cổng, connector, classloader và lifecycle riêng**. Khi deploy WAR, container **không phải gọi phương thức static `main`**. Thay vào đó, Spring Web dùng cơ chế `WebApplicationInitializer` để gọi initializer của ứng dụng, rồi `configure` khai báo các Spring configuration sources cần nạp.

Một executable WAR được build bằng Spring Boot plugin có thể hỗ trợ **cả hai kiểu chạy**. Điều này không có nghĩa hai luồng bootstrap hoàn toàn giống nhau: Java entry point và Servlet container callback là hai điểm vào khác nhau.

### Khi nào không áp dụng?

- **Spring MVC/Servlet:** phù hợp với lối triển khai WAR truyền thống.
- **Spring WebFlux với Reactor Netty thuần:** tài liệu Spring Boot 3.3 không hỗ trợ WAR deployment truyền thống kiểu servlet cho WebFlux. Không dùng hướng dẫn này để cố gói Netty thành ứng dụng Tomcat WAR.
- **JAR executable thông thường:** không cần WAR/initializer nếu không có yêu cầu external container.

## 3. API SpringBootServletInitializer và chữ ký configure

Trong Spring Boot 3, dùng các import:

~~~java
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;
~~~

`SpringBootServletInitializer` cung cấp một implementation của `WebApplicationInitializer`, giúp chuyển lifecycle servlet container sang việc tạo Spring Boot ApplicationContext. Các servlet, filter và registration beans được đăng ký trong context thích hợp.

Phần quan trọng nhất:

~~~java
@Override
protected SpringApplicationBuilder configure(SpringApplicationBuilder application) {
    return application.sources(WarDemoApplication.class);
}
~~~

Giải thích:

- `protected` và kiểu trả về `SpringApplicationBuilder` phải phù hợp chữ ký; `@Override` giúp compiler phát hiện sai tham số/return type.
- `application.sources(WarDemoApplication.class)` thêm class mang `@SpringBootApplication` làm **nguồn cấu hình** cho Spring khi external container gọi initializer.
- `configure` trả lại builder sau khi cấu hình, **không tự gọi `SpringApplication.run`** và cũng không trả `ApplicationContext`.
- `SpringBootServletInitializer` **không phải** Controller, Servlet hay Filter; đừng dùng `@RestController` cho initializer.
- Nếu lớp initializer đồng thời là configuration source, Spring Boot có thể có hành vi mặc định phù hợp; dù vậy, cấu hình `sources(...)` tường minh giúp tránh nhầm trong project có nhiều cấu hình.

**Không nên nhầm** package cũ của Spring Boot đời trước với `org.springframework.boot.web.servlet.support.SpringBootServletInitializer` của Boot 3. Luôn kiểm tra import khi migrate project.

## 4. Project mẫu với một application class có hai điểm khởi động

Ví dụ tạo project `war-demo`:

~~~text
war-demo/
├── pom.xml                     (chọn khi dùng Maven)
├── mvnw, mvnw.cmd, .mvn/wrapper/
├── build.gradle                (chọn khi dùng Gradle Groovy DSL)
├── settings.gradle
├── gradlew, gradlew.bat, gradle/wrapper/
└── src/
    ├── main/
    │   ├── java/com/example/war/
    │   │   ├── WarDemoApplication.java
    │   │   └── PingController.java
    │   └── resources/application.properties
    └── test/java/com/example/war/
        └── PingControllerTest.java
~~~

Sơ đồ liệt kê **hai phương án build để so sánh**, không buộc repository thật duy trì Maven và Gradle song song.

### 4.1. File src/main/java/com/example/war/WarDemoApplication.java

~~~java
package com.example.war;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class WarDemoApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder application) {
        return application.sources(WarDemoApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(WarDemoApplication.class, args);
    }
}
~~~

Đây là lớp Java **độc lập và đầy đủ**, tên file trùng với tên public class, dùng các API của Spring Boot 3. Cả hai đường khởi động dùng **cùng nguồn cấu hình `WarDemoApplication.class`**:

- **External container:** gọi `configure` thông qua initializer để tạo web application context.
- **Executable WAR:** Boot Launcher gọi `main`; `SpringApplication.run` khởi tạo Spring và embedded Tomcat.

`@SpringBootApplication` bật Spring Boot auto-configuration và component scan từ package `com.example.war`. Đảm bảo Controller/Service nằm trong package này hoặc các package con; nếu chuyển code sang một root package khác, component scan có thể không còn tìm thấy bean.

### 4.2. File src/main/java/com/example/war/PingController.java

~~~java
package com.example.war;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

Controller này đủ để kiểm chứng cả embedded và external mode. Spring MVC mapping **luôn là `/ping` trong ứng dụng**. Prefix của WAR external, ví dụ `/war-demo`, được servlet container gắn thêm vào context root.

### 4.3. File src/main/resources/application.properties

Có thể không tạo file hoặc thêm cấu hình không nhạy cảm:

~~~properties
spring.application.name=war-demo
~~~

**Không đặt mật khẩu database hay token production vào source.** Với bài thực hành, không cần khai báo `server.port` hay `server.servlet.context-path`. Khi chạy embedded mode, cổng 8080 và context root `/` thường đủ; khi deploy Tomcat ngoài, port và context root do external container quyết định.

## 5. Maven: cấu hình packaging WAR

### 5.1. POM hoàn chỉnh dùng Spring Boot Starter Parent

File `pom.xml` cho cùng ứng dụng trên:

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
    <artifactId>war-demo</artifactId>
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

Ý nghĩa:

1. `<packaging>war</packaging>` bảo Maven dùng WAR lifecycle và tạo archive WAR thay cho JAR.
2. `spring-boot-starter-web` cấp Spring MVC và các thư viện ứng dụng web.
3. `spring-boot-starter-tomcat` là dependency của Spring Web starter nhưng được **khai báo trực tiếp** với `<scope>provided</scope>` để container ngoài chịu trách nhiệm Servlet engine.
4. `spring-boot-starter-test` chỉ phục vụ test, không đưa test code vào runtime WAR.
5. `spring-boot-maven-plugin` cùng cấu hình từ Starter Parent tạo **repackaged/executable WAR**.
6. Parent quản lý các phiên bản thư viện liên quan; tránh thêm riêng bản Servlet API hay Tomcat không được kiểm chứng tương thích.

**Vì sao `provided` lại xuất hiện trong executable WAR?** Spring Boot Maven `repackage` đặt các thư viện provided của servlet container vào `WEB-INF/lib-provided` khi dùng WAR layout. External container không dùng chúng như thư viện webapp thông thường; nhưng `java -jar` có thể sử dụng chúng để chạy embedded Tomcat.

### 5.2. Dự án không kế thừa Starter Parent

Một POM có corporate parent hoặc chỉ import `spring-boot-dependencies` BOM **không tự có** đầy đủ Maven plugin management/execution từ Starter Parent. Phải bảo đảm:

- Maven War Plugin tương thích được cấu hình hoặc quản lý.
- Spring Boot Maven Plugin dùng version đồng bộ với Spring Boot project.
- Goal `repackage` được gắn vào lifecycle `package` nếu bạn muốn executable WAR.

Đoạn này là **fragment** trong `<build><plugins>` của POM đầy đủ, **không phải POM độc lập**:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <version>3.3.5</version>
    <executions>
        <execution>
            <goals>
                <goal>repackage</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Nếu đã dùng Starter Parent, **không thêm execution trùng** chỉ vì sao chép đoạn này: Parent đã có cấu hình liên quan. Với một WAR chỉ deploy được mà không cần chạy `java -jar`, Spring Boot loader không phải điều kiện tuyệt đối; bài học dùng executable WAR để kiểm thử hai cách chạy trên cùng artifact.

### 5.3. Build và xem WAR

Linux/macOS:

~~~bash
./mvnw --version
./mvnw clean verify
ls -lh target/*.war
jar tf target/war-demo-0.0.1-SNAPSHOT.war | grep '^WEB-INF/'
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd clean verify
Get-ChildItem .\target\*.war
jar tf .\target\war-demo-0.0.1-SNAPSHOT.war |
    Select-String '^WEB-INF/'
~~~

`clean verify` đi qua `package` và chạy unit tests theo cấu hình. Nếu project đổi `finalName`, module hoặc version, xác định **đúng tên WAR được tạo** thay vì dùng cứng đường dẫn ví dụ. Bản trước `repackage` có thể xuất hiện dưới dạng tệp `.original`, không phải WAR executable cuối.

## 6. Gradle: war plugin, providedRuntime và bootWar

### 6.1. Groovy DSL

File `settings.gradle`:

~~~groovy
rootProject.name = 'war-demo'
~~~

File `build.gradle` hoàn chỉnh:

~~~groovy
plugins {
    id 'java'
    id 'war'
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
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

springBoot {
    mainClass = 'com.example.war.WarDemoApplication'
}
~~~

**Giải thích:**

- `id 'war'` áp dụng Gradle War plugin; khi Spring Boot Gradle plugin nhận thấy plugin này, nó tạo task **`bootWar`**.
- `providedRuntime` là configuration dành cho servlet container đã được external runtime cung cấp; `bootWar` đặt những library này vào **`WEB-INF/lib-provided`**.
- `providedRuntime` **không giống `compileOnly`**. Theo tài liệu Spring Boot, `compileOnly` không phục vụ web integration test classpath như mong muốn.
- `springBoot.mainClass` làm rõ entry point khi chạy executable WAR; nó **không thay thế initializer** cho container ngoài.
- `useJUnitPlatform()` cho phép chạy JUnit Jupiter tests qua Gradle Test.
- `io.spring.dependency-management` hỗ trợ BOM khi kết hợp Spring Boot Gradle plugin.

Nếu project tập trung repositories ở settings và dùng `RepositoriesMode.FAIL_ON_PROJECT_REPOS`, bỏ block `repositories { mavenCentral() }` khỏi build script và dùng nguồn khai báo trong settings theo quy định dự án.

### 6.2. Kotlin DSL

File `settings.gradle.kts`:

~~~kotlin
rootProject.name = "war-demo"
~~~

File `build.gradle.kts`:

~~~kotlin
plugins {
    java
    war
    id("org.springframework.boot") version "3.3.5"
    id("io.spring.dependency-management") version "1.1.6"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    providedRuntime("org.springframework.boot:spring-boot-starter-tomcat")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}

springBoot {
    mainClass.set("com.example.war.WarDemoApplication")
}
~~~

Kotlin DSL và Groovy DSL là **hai lựa chọn thay thế**, không đặt đồng thời cả hai trong một project. Nguồn Java ở mục 4 không cần đổi. Trong multi-module build, chỉ áp dụng `war` và Boot plugin vào **module ứng dụng Servlet cần deploy**, không bật WAR packaging cho các module Java library dùng chung.

### 6.3. Chạy Gradle

Linux/macOS:

~~~bash
./gradlew --version
./gradlew clean build
./gradlew bootWar
ls -lh build/libs/*.war
jar tf build/libs/war-demo-0.0.1-SNAPSHOT.war | grep '^WEB-INF/'
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean build
.\gradlew.bat bootWar
Get-ChildItem .\build\libs\*.war
jar tf .\build\libs\war-demo-0.0.1-SNAPSHOT.war |
    Select-String '^WEB-INF/'
~~~

Task `bootWar` tạo executable WAR. Theo convention của Spring Boot Gradle plugin, task WAR thông thường có thể tạo tệp **`-plain.war`**, không có launcher giống WAR executable. Không chạy nhầm plain WAR bằng `java -jar` và kết luận initializer sai.

## 7. Kiểm tra cấu trúc WAR

Một executable Spring Boot WAR thường có cấu trúc gần như:

~~~text
war-demo-0.0.1-SNAPSHOT.war
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...         (Boot launcher)
└── WEB-INF/
    ├── classes/
    │   ├── com/example/war/WarDemoApplication.class
    │   └── com/example/war/PingController.class
    ├── lib/
    │   ├── spring-webmvc-*.jar
    │   └── ...                                 (thư viện ứng dụng)
    └── lib-provided/
        └── tomcat-embed-*.jar                  (thư viện servlet container provided)
~~~

Đây là **sơ đồ minh họa**, không phải tên chính xác từng nested JAR hay toàn bộ WAR. Dùng `jar tf` để xem file thật.

**Ba thư mục phải phân biệt:**

| Thư mục | Thành phần | Ai sử dụng? |
| --- | --- | --- |
| `WEB-INF/classes` | Class và resources đã build của ứng dụng | Spring/webapp |
| `WEB-INF/lib` | Dependency runtime ứng dụng, ví dụ Spring MVC | Webapp trong external container hoặc Boot launcher |
| `WEB-INF/lib-provided` | Embedded servlet container libraries đánh dấu provided | Spring Boot launcher khi chạy executable WAR; tránh xung đột với container ngoài |

Trong manifest của executable WAR Spring Boot 3.3 thông thường:

~~~text
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: com.example.war.WarDemoApplication
~~~

`Main-Class` ở đây là **Boot launcher**, còn `Start-Class` là application class của bạn. Không sửa `Main-Class` thành `WarDemoApplication` trong WAR đã repackage, vì có thể bỏ qua cơ chế nạp nested libraries.

### Kiểm tra manifest trên Linux/macOS

Khi máy đã cài `unzip`:

~~~bash
unzip -p target/war-demo-0.0.1-SNAPSHOT.war META-INF/MANIFEST.MF
~~~

Với Gradle, dùng `build/libs/war-demo-0.0.1-SNAPSHOT.war`. Trên máy không có unzip, công cụ `jar` từ JDK có thể giải nén manifest trong **một thư mục kiểm tra riêng** rồi mở file `META-INF/MANIFEST.MF`. Không cần chỉnh archive bằng tay.

## 8. Chạy executable WAR bằng java -jar

Với WAR do Maven `spring-boot:repackage` hoặc Gradle `bootWar` vừa tạo:

~~~bash
# Maven
java -jar target/war-demo-0.0.1-SNAPSHOT.war

# Gradle (lệnh thay thế, dùng đúng file của build bạn chọn)
java -jar build/libs/war-demo-0.0.1-SNAPSHOT.war
~~~

Spring Boot khởi chạy embedded Tomcat nhờ `WEB-INF/lib-provided`, và ứng dụng đăng ký `PingController`. Mở terminal thứ hai:

~~~bash
curl -fsS http://localhost:8080/ping
~~~

Response body kỳ vọng:

~~~text
pong
~~~

Nếu cổng 8080 bị chiếm, có thể chạy bằng cổng khác trong **embedded mode**:

~~~bash
java -jar target/war-demo-0.0.1-SNAPSHOT.war --server.port=8081
~~~

Sau đó gọi `http://localhost:8081/ping`. Tham số `--server.port` không đổi cổng connector của **Tomcat ngoài**; external server quản lý port riêng.

**Lưu ý:** nếu chỉ đóng gói WAR bằng Maven War Plugin hoặc Gradle `war` thông thường, WAR có thể **deploy được nhưng không chạy bằng `java -jar`**. Đừng đánh đồng sự tồn tại của một tệp `.war` với tính executable của Spring Boot archive.

## 9. Deploy WAR vào Apache Tomcat bên ngoài

### 9.1. Chuẩn bị môi trường

Ví dụ dùng **Tomcat 10.1.x** với Spring Boot 3.3 và Java 17:

- External Tomcat có Servlet API theo namespace **`jakarta.servlet.*`**.
- Không dùng **Tomcat 9** (thường là `javax.servlet.*`) cho WAR Spring Boot 3 theo cấu hình chuẩn.
- Container có quyền và cấu hình deploy phù hợp, được đội vận hành phê duyệt.
- Port, hostname, context path được xác định từ cấu hình Tomcat, không suy đoán từ Spring Boot `server.port`.
- WAR đã được build sạch, kiểm tra cấu trúc và không phải plain WAR/artifact cũ.
- Không thêm tuỳ tiện thư viện Spring Framework/Tomcat/Jakarta API phiên bản khác vào Tomcat global `lib` gây classloader conflicts.

### 9.2. Deploy bằng thư mục webapps khi môi trường cho phép

Ví dụ Linux, **giả định** biến môi trường `CATALINA_BASE` đã trỏ đến Tomcat instance có thể ghi:

~~~bash
# Đã chạy ./mvnw clean verify ở thư mục project
test -n "$CATALINA_BASE"
cp target/war-demo-0.0.1-SNAPSHOT.war \
   "$CATALINA_BASE/webapps/war-demo.war"
~~~

Nếu dùng Gradle, thay source bằng `build/libs/war-demo-0.0.1-SNAPSHOT.war`.

Windows PowerShell:

~~~powershell
if (-not $env:CATALINA_BASE) {
    throw "CATALINA_BASE is not set"
}
Copy-Item .\target\war-demo-0.0.1-SNAPSHOT.war "$env:CATALINA_BASE\webapps\war-demo.war"
~~~

Đây là **cách deploy minh họa**, không phải chỉ dẫn để thay đổi server production chưa được phép. Tùy cấu hình Tomcat, việc copy file có thể cần autoDeploy được bật, restart, hoặc deployment qua Manager/CI. **Có file WAR trong webapps chưa chứng minh ứng dụng đã startup thành công**; phải đọc log và gọi endpoint.

### 9.3. Kiểm tra context path

Khi Tomcat đang chạy ở `localhost:8080` và WAR được triển khai dưới tên `war-demo.war` theo quy tắc mặc định, endpoint thường là:

~~~bash
curl -fsS http://localhost:8080/war-demo/ping
~~~

Output:

~~~text
pong
~~~

PowerShell:

~~~powershell
Invoke-RestMethod -Uri "http://localhost:8080/war-demo/ping"
~~~

**Giải thích:** Controller vẫn khai báo `@GetMapping("/ping")`. Prefix `/war-demo` thuộc **context root** do external servlet container gán, thường dựa trên tên WAR hoặc cấu hình context. Nếu deploy làm `ROOT.war`, URL có thể là `/ping`. Nếu administrator dùng context path tùy chỉnh, URL thay đổi tương ứng.

Đừng thay `@GetMapping("/ping")` thành `@GetMapping("/war-demo/ping")` chỉ để chữa 404, vì sẽ vô tình nhân đôi prefix khi deploy WAR với context root.

## 10. Tách lớp ServletInitializer riêng khi cần

Cách ngắn nhất là để `WarDemoApplication extends SpringBootServletInitializer` như mục 4. Nhưng đôi khi một dự án thích để application class chỉ có main, còn initializer thuộc file khác.

**Đây là phương án thay thế, không sử dụng đồng thời với application extends ở mục 4.**

File `WarDemoApplication.java`:

~~~java
package com.example.war;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WarDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(WarDemoApplication.class, args);
    }
}
~~~

File `ServletInitializer.java`:

~~~java
package com.example.war;

import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

public class ServletInitializer extends SpringBootServletInitializer {
    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder builder) {
        return builder.sources(WarDemoApplication.class);
    }
}
~~~

Hai file cùng package tạo hai đường vào. `ServletInitializer` không cần có phương thức main; khi external container triển khai WAR, nó khởi tạo application thông qua `configure`. Nếu project đã có initializer khác, **không thêm thêm một cái vô điều kiện**: nhiều `WebApplicationInitializer` hoặc `web.xml` cùng đăng ký servlet/filter có thể gây trùng context hoặc hành vi bất ngờ.

### Khi cần tùy chỉnh SpringApplicationBuilder ở cả hai đường chạy

Các thiết lập chỉ đặt trong `configure` **không tự chạy** khi JVM gọi `main`. Nếu muốn đồng nhất banner, default properties hoặc configuration sources, tạo method dùng chung và gọi từ cả hai:

~~~java
package com.example.war;

import org.springframework.boot.Banner;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class WarDemoApplication extends SpringBootServletInitializer {
    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder builder) {
        return configureApplication(builder);
    }

    public static void main(String[] args) {
        configureApplication(new SpringApplicationBuilder()).run(args);
    }

    private static SpringApplicationBuilder configureApplication(
            SpringApplicationBuilder builder) {
        return builder.sources(WarDemoApplication.class)
                .bannerMode(Banner.Mode.OFF);
    }
}
~~~

Đây là **phương án thay thế** class ở mục 4, không chèn nguyên một public class trùng tên vào cùng file. Không hard-code password, token hoặc `profiles("production")` để ép mọi môi trường vào production.

## 11. Tương thích Java, Jakarta Servlet và classloader

### 11.1. Spring Boot 3 chuyển sang Jakarta

Spring Boot 3 dùng Spring Framework 6 và các API Servlet thuộc namespace **`jakarta.servlet`**. Tomcat 10.1 hỗ trợ dòng API Jakarta tương ứng. Tomcat 9 thuộc hệ `javax.servlet` nên **không dùng cho WAR Spring Boot 3** theo cách triển khai thông thường.

Nếu project cũ có:

~~~java
import javax.servlet.Filter;
~~~

thì đây là API kiểu cũ. Khi migrate sang Spring Boot 3 có thể cần:

~~~java
import jakarta.servlet.Filter;
~~~

Nhưng **chỉ đổi một import chưa đủ** nếu các dependency, custom servlet/filter, Spring Security hoặc JPA/validation libraries khác còn dùng Java EE namespace cũ. Cần nâng cả tập thư viện có tương thích và kiểm thử thực tế.

### 11.2. Version matrix

| Thành phần | Bản ví dụ | Vì sao cần kiểm tra? |
| --- | --- | --- |
| Java | 17 | Class file/JDK runtime phải hỗ trợ Spring Boot và Tomcat |
| Spring Boot | 3.3.5 | Đưa vào các Spring Framework/Jakarta dependencies phù hợp |
| Spring MVC | `spring-boot-starter-web` | WAR truyền thống cần servlet-based web stack |
| Tomcat bên ngoài | 10.1.x | Jakarta Servlet API và container implementation |
| Tomcat starter | `provided` / `providedRuntime` | Tránh embedded Tomcat xung đột khi deploy ngoài |
| Gradle/Maven | Wrapper phiên bản được Boot plugin hỗ trợ | Phải compile, test và build đúng WAR |

Một WAR có thể chạy bằng `java -jar` trên local nhưng **fail trên external container** vì sự khác nhau ở JDK, servlet API hoặc classloader. Build pass không thay thế thử trên đúng server version.

### 11.3. Vì sao không copy jar của container vào ứng dụng?

Thư viện của servlet engine do **Tomcat bên ngoài** quản lý. Khi ta đánh dấu Tomcat embedded là `provided` hoặc `providedRuntime`, executable WAR sẽ để nó dưới `WEB-INF/lib-provided`; external container không dùng đó như thư viện webapp thông thường. Nếu bạn lại chèn `tomcat-embed-core` vào `WEB-INF/lib`, Tomcat có thể gặp duplicate classes hoặc API conflicts.

Không đưa tùy tiện bản `javax.servlet-api` vào WAR Spring Boot 3 để “chữa” lỗi thiếu servlet class; đó thường là dấu hiệu **runtime servlet container sai hệ** hoặc transitive dependency không tương thích.

## 12. Kiểm thử Spring MVC và kiểm thử deploy WAR

### 12.1. Web MVC test bằng JUnit Jupiter

Vì POM/Gradle ví dụ có `spring-boot-starter-test`, có thể dùng một test kiểm tra endpoint mà không cần khởi động Tomcat ngoài. File `src/test/java/com/example/war/PingControllerTest.java`:

~~~java
package com.example.war;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(PingController.class)
class PingControllerTest {
    @Autowired
    private MockMvc mvc;

    @Test
    void pingReturnsPong() throws Exception {
        mvc.perform(get("/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }
}
~~~

Test biên dịch/chạy với JUnit Jupiter, Spring Boot Test và Gradle `useJUnitPlatform()` hoặc Maven Surefire version phù hợp do Parent quản lý.

**Giới hạn:** `@WebMvcTest` kiểm tra Spring MVC mapping và response, **không chứng minh** WAR deploy tới external Tomcat được. Nó không kiểm tra SpringBootServletInitializer được container gọi, classloader đúng hay context root chính xác.

### 12.2. Ma trận kiểm chứng

| Tầng | Lệnh/cách kiểm | Bằng chứng |
| --- | --- | --- |
| Compile | Maven `compile` / Gradle `compileJava` | Initializer có chữ ký hợp lệ và API Boot 3 có trên classpath |
| Test | `mvnw clean verify` / `gradlew clean build` | PingControllerTest được thực thi và pass |
| WAR structure | `jar tf` | `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided` đúng |
| Manifest | `unzip -p ... META-INF/MANIFEST.MF` | Có Boot WarLauncher, Start-Class đúng |
| Embedded smoke | `java -jar ...war` + `curl /ping` | HTTP 200, response `pong` |
| External smoke | Deploy Tomcat 10.1 + `curl /war-demo/ping` | Container deploy thành công, HTTP 200, response `pong` |
| Regression | Luồng auth/session/DB/upload/static files | Không lỗi chỉ xuất hiện dưới container ngoài |

Nếu chỉ có test JUnit pass và file WAR tồn tại, vẫn **chưa đủ kết luận deployment sẵn sàng**. Cần ít nhất một smoke test WAR chạy trên servlet container thật hoặc môi trường thử nghiệm tương ứng.

### 12.3. CI tối thiểu

Linux/bash, chọn **một** phương án:

~~~bash
# Maven
./mvnw --batch-mode --no-transfer-progress clean verify
jar tf target/war-demo-0.0.1-SNAPSHOT.war > war-entries.txt
grep -q '^WEB-INF/classes/com/example/war/WarDemoApplication.class$' war-entries.txt
grep -q '^WEB-INF/lib-provided/' war-entries.txt
~~~

~~~bash
# Gradle
./gradlew clean build
jar tf build/libs/war-demo-0.0.1-SNAPSHOT.war > war-entries.txt
grep -q '^WEB-INF/classes/com/example/war/WarDemoApplication.class$' war-entries.txt
grep -q '^WEB-INF/lib-provided/' war-entries.txt
~~~

Hai đoạn trên là lựa chọn thay thế, yêu cầu JDK `jar` và `grep`. Chúng xác minh **file trong archive**, không thay thế HTTP smoke test. Với CI nghiêm ngặt cần job chạy WAR và gửi HTTP request tới đúng endpoint, hoặc deploy lên Tomcat tương thích rồi kiểm tra. Không chọn ngẫu nhiên `-plain.war` hoặc file từ build trước.

## 13. Những lỗi phổ biến và cách điều tra

| Triệu chứng | Nguyên nhân có thể | Hành động |
| --- | --- | --- |
| Tomcat nhận WAR nhưng Spring context không khởi động | Không có initializer, initializer sai classpath, `configure` không nạp ứng dụng | Kiểm tra `WEB-INF/classes`, log Tomcat, `sources(WarDemoApplication.class)` |
| Maven/Gradle báo thiếu SpringBootServletInitializer | Import sai package, thiếu Boot dependency hoặc dùng Boot quá cũ | Xem compile classpath, import `org.springframework.boot.web.servlet.support` |
| `configure` báo lỗi `does not override` | Sai kiểu tham số/trả về/chữ ký | Dùng `protected SpringApplicationBuilder configure(SpringApplicationBuilder builder)` |
| WAR tạo ra là JAR | Maven thiếu `<packaging>war</packaging>` hoặc Gradle thiếu `war` | Xem POM/plugin và đúng module đóng gói |
| Gradle `Task 'bootWar' not found` | Chưa áp dụng WAR + Boot plugin trong module đúng | Bật plugin `war` và Spring Boot plugin, kiểm tra `gradlew tasks` |
| `java -jar file.war` báo no main manifest attribute | Chạy plain WAR, Spring Boot repackage/bootWar chưa chạy | Dùng executable WAR có WarLauncher và Start-Class |
| Có Tomcat nested ở `WEB-INF/lib` gây lỗi deployment | Servlet container dependency chưa được đánh dấu provided | Dùng Maven `provided` / Gradle `providedRuntime` |
| `ClassNotFoundException: jakarta.servlet...` | External container hoặc dependencies không tương thích Jakarta | Dùng Tomcat 10.1 cho Boot 3 và rà API/transitives |
| `ClassNotFoundException: javax.servlet...` | Thư viện cũ đòi Java EE trong project Jakarta | Migration dependencies và code sang Jakarta-compatible versions |
| Embedded mode chạy được nhưng external fail | Thiếu initializer, classloader, container/JDK/config khác | So sánh startup logs, WAR structure, Java/Tomcat version |
| External WAR trả 404 ở `/ping` | Context root `/war-demo` | Thử `/war-demo/ping` hoặc đúng context từ Tomcat |
| HTTP 404 cả khi đã có context | Controller ngoài component scan hoặc app chưa startup | Kiểm tra package, Spring log, handler mappings |
| Đặt `server.port=8081` nhưng Tomcat ngoài vẫn 8080 | Cổng của external container không do Boot quản lý | Cấu hình Tomcat connector theo quy trình vận hành |
| WAR có hai ApplicationContext hoặc Filter bị đăng ký trùng | Nhiều WebApplicationInitializer, `web.xml` và Java config chồng chéo | Chọn một initializer, rà mapping, loại đăng ký dư |
| CI build thành công nhưng production 500 | Thiếu secret/JNDI, Servlet version, session/security hoặc database khác | Tạo environment parity và integration/smoke tests |
| Test `@WebMvcTest` pass nhưng deploy fail | Test chỉ kiểm tra MVC slice, không khởi động external container | Thêm kiểm chứng deploy WAR trên Tomcat tương thích |

Khi gỡ lỗi, trước tiên ghi rõ **Java version, Spring Boot version, Tomcat version, artifact path, manifest, WAR structure và log deploy**. Không thay nhiều dependency ngẫu nhiên hoặc sửa URL endpoint mà chưa biết lỗi nằm ở startup, packaging, component scan hay context root.

## 14. Các lưu ý triển khai an toàn và bảo trì

1. **Giữ hai đường khởi động nhất quán.** Nếu `main` và `configure` dùng hai configuration sources khác nhau, ứng dụng có thể hoạt động khác giữa embedded/external. Nếu có custom settings phức tạp, chia sẻ một builder method.
2. **Chỉ một initializer rõ ràng.** Không tạo đồng thời class extends SpringBootServletInitializer và một ServletInitializer riêng trừ khi hiểu chính xác tương tác của nhiều WebApplicationInitializer.
3. **Không chôn secrets trong WAR.** Runtime config nên được external hóa bằng environment, secret manager, Java system properties hoặc cơ chế cấu hình đã được tổ chức phê duyệt.
4. **Tuân thủ Jakarta namespace.** Spring Boot 3 không tương đương runtime Tomcat 9/Servlet javax đời cũ.
5. **Đừng dùng `server.port` để điều khiển Tomcat ngoài.** Phân biệt external connector và embedded server, cũng như WAR context root và Spring MVC mapping.
6. **Đừng deploy nhầm artifact.** Gradle có thể tạo plain WAR, Maven có thể giữ nguồn `.original`; CI phải xuất bản đúng WAR đã được test.
7. **Đọc container log khi deploy.** WAR có trong webapps không đồng nghĩa nó được Tomcat startup thành công; theo dõi exceptions, deployment status và HTTP endpoint.
8. **Chú ý downtime/redeploy.** External container quản lý undeploy/reload; các background threads, JDBC drivers, scheduler, sessions và resource cleanup cần phù hợp với lifecycle.
9. **Không giả định jar và war giống nhau.** JAR dùng `BOOT-INF`, WAR dùng `WEB-INF`; hai kiểu packaging có cấu trúc classpath và manifest khác.
10. **Luôn smoke test hai chế độ nếu bạn cam kết hỗ trợ cả hai.** Không chỉ kiểm tra `mvn package` hoặc `gradlew bootWar`.

## 15. Bài thực hành có tiêu chí hoàn thành

Làm trên một branch thử nghiệm của project Spring Boot MVC có Maven hoặc Gradle Wrapper:

1. Tạo `WarDemoApplication.java` kế thừa `SpringBootServletInitializer`, override `configure` trả builder đã thêm `WarDemoApplication.class`, đồng thời giữ phương thức `main`.
2. Tạo `PingController.java` với `GET /ping` trả `pong`.
3. Chọn **Maven** (packaging WAR, Tomcat scope provided, Boot Maven Plugin) **hoặc Gradle** (war plugin, providedRuntime, bootWar).
4. Chạy `clean verify` hoặc `clean build`; kiểm tra JUnit test được phát hiện và thực thi.
5. Dùng `jar tf` xác nhận `WEB-INF/classes`, `WEB-INF/lib` và `WEB-INF/lib-provided`; kiểm tra WarLauncher/Start-Class từ manifest.
6. Chạy `java -jar` với đúng executable WAR; gọi `http://localhost:8080/ping` và xác nhận response `pong`.
7. Deploy **cùng WAR** lên Tomcat 10.1, xác định context path thực và gọi `http://localhost:8080/war-demo/ping` khi phù hợp; xác nhận `pong`.
8. So sánh hai startup paths: external Tomcat có gọi `main` không? Ai quản lý port? Ai đặt context root? Lớp nào cung cấp Spring application sources?
9. Thử lỗi có kiểm soát trong branch riêng (bỏ initializer hoặc dùng sai source), đọc lỗi trong container log, rồi **khôi phục cấu hình đúng**.
10. Ghi lại phiên bản JDK/Boot/Tomcat, tên và checksum WAR, test evidence, lệnh deploy cùng phương án rollback.

**Hoàn thành khi:** bạn có thể giải thích và chứng minh `SpringBootServletInitializer` nối lifecycle external Servlet container với Spring Boot như thế nào, tạo được WAR có cấu trúc đúng và đưa **cùng một Spring MVC endpoint** chạy được trong cả executable WAR lẫn external Tomcat.

## Tài liệu chính thức

- [Spring Boot 3.3 – Traditional Deployment](https://docs.spring.io/spring-boot/3.3/how-to/deployment/traditional-deployment.html)
- [Spring Boot 3.3 API – SpringBootServletInitializer](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/servlet/support/SpringBootServletInitializer.html)
- [Spring Boot 3.3 – Maven Plugin: Packaging](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 – Gradle Plugin: Packaging](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot 3.3 – Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html)
- [Apache Tomcat 10.1 Documentation](https://tomcat.apache.org/tomcat-10.1-doc/)
- [Gradle – War Plugin](https://docs.gradle.org/current/userguide/war_plugin.html)
- [Maven – Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)

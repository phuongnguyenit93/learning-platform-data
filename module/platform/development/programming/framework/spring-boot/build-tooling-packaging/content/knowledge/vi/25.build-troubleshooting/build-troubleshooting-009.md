# Xử lý xung đột thư viện khi đóng gói hoặc triển khai WAR

Một ứng dụng Spring Boot chạy tốt bằng IDE hoặc `java -jar` vẫn có thể lỗi khi đóng gói WAR và triển khai lên Tomcat, Jetty hay application server của doanh nghiệp. Nguyên nhân thường nằm ở **dependency graph**, **scope đóng gói**, **phiên bản Servlet API**, hoặc **classloader của container**. Các lỗi như `NoSuchMethodError`, `NoClassDefFoundError`, `ClassCastException` và cảnh báo nhiều SLF4J providers là tín hiệu cần điều tra classpath thực tế, không nên sửa bằng cách thêm JAR ngẫu nhiên vào thư mục server.

Bài này dùng **Java 17, Spring Boot 3.3.13** và một ứng dụng Spring MVC đóng gói được thành **executable WAR**. Bạn sẽ hiểu cấu trúc WAR, phân biệt `WEB-INF/lib` với `WEB-INF/lib-provided`, cấu hình Maven/Gradle đúng cho servlet container bên ngoài, tìm phiên bản thư viện bị xung đột, phân biệt `javax.servlet` với `jakarta.servlet`, kiểm tra classloader, và xử lý lỗi theo nguyên nhân. Các lệnh build, kiểm tra WAR và smoke test có thể áp dụng trực tiếp cho dự án tương tự.

## 1. “Xung đột thư viện” có nhiều dạng khác nhau

Không phải mọi lỗi runtime đều do hai JAR có cùng tên. Nên phân loại trước khi sửa:

| Dạng xung đột | Ví dụ | Nơi cần kiểm tra |
| --- | --- | --- |
| **Version conflict trong dependency graph** | Hai thư viện yêu cầu các version khác nhau của `spring-core` | Maven dependency mediation hoặc Gradle resolution |
| **Duplicate class** | Hai artifact khác coordinates cùng chứa `com.example.Helper` | Nội dung JAR/WAR, shaded JAR, thư viện vendor |
| **Container vs application library** | WAR mang embedded Tomcat trong `WEB-INF/lib` trong khi server đã cung cấp Servlet container | WAR scopes và classloader |
| **Namespace/API mismatch** | Ứng dụng dùng `jakarta.servlet` nhưng container/library cũ còn dùng `javax.servlet` | Phiên bản Spring Boot, Servlet API và container |
| **Nhiều implementation cùng vai trò** | Tomcat và Jetty cùng xuất hiện; nhiều SLF4J providers | Dependency tree và runtime classpath |
| **Classloader mismatch** | Cùng tên class được nạp bởi hai classloader khác nhau | Class loading logs, thư viện dùng chung trong server |
| **Binary incompatibility** | Compile với API mới nhưng runtime nạp JAR cũ | Phiên bản thực tế trong WAR và server |

Hai tình huống cần phân biệt rõ:

- **Version conflict**: cùng tọa độ module (group/artifact) có nhiều version được yêu cầu; build tool áp dụng quy tắc chọn một version cho configuration.
- **Duplicate class**: hai artifact khác nhau có thể cùng chứa một class. Maven/Gradle không nhất thiết coi chúng là một module conflict, nên build vẫn có thể thành công nhưng runtime nạp class ngoài dự kiến.

Một WAR có thể build xanh mà vẫn chứa dependency không phù hợp với server. Vì vậy cần kiểm tra **dependency graph và chính archive đã đóng gói**, sau đó chạy thử trên đúng loại container dự kiến triển khai.

## 2. WAR có những vùng classpath nào?

Một WAR theo Servlet specification thường có cấu trúc:

```text
war-conflict-demo.war
└── WEB-INF/
    ├── classes/              # Class và resource của ứng dụng
    ├── lib/                  # Thư viện runtime của ứng dụng
    │   ├── spring-core-*.jar
    │   ├── spring-webmvc-*.jar
    │   └── ...
    └── web.xml               # Có thể không tồn tại với Spring Boot
```

Servlet container tải ứng dụng từ `WEB-INF/classes` và các JAR trong `WEB-INF/lib`. Nó cũng có thư viện chung ở classpath của chính server. Apache Tomcat mô tả Web application classloader đọc `WEB-INF/classes`, `WEB-INF/lib` và tài nguyên do Catalina cung cấp.

Spring Boot executable WAR có thêm thư mục riêng:

```text
WEB-INF/
├── classes/
├── lib/                      # Application dependencies
└── lib-provided/             # Provided runtime dependencies cho Boot launcher
```

`WEB-INF/lib-provided` là cơ chế Spring Boot dùng để giữ các dependency được đánh dấu `provided` cho trường hợp chạy WAR bằng `java -jar`. Khi triển khai WAR lên servlet container bên ngoài, container sử dụng `WEB-INF/classes` và `WEB-INF/lib` theo cấu trúc WAR; các dependency `lib-provided` không được đưa vào classpath web application như thư viện thông thường. Nhờ vậy embedded container có thể được giữ trong executable WAR mà không cạnh tranh với container đang chạy bên ngoài.

**Đây là điểm then chốt khi xử lý xung đột:** dependency của servlet container phải được đánh dấu đúng là `provided`/`providedRuntime`. Nếu nó bị đóng gói nhầm vào `WEB-INF/lib`, ứng dụng có thể mang theo một bộ Tomcat/Servlet API riêng và va chạm với server.

## 3. Executable WAR và WAR triển khai lên container

Spring Boot hỗ trợ hai cách chạy cùng một WAR nếu cấu hình đúng:

1. **Chạy độc lập:** `java -jar war-conflict-demo-1.0.0.war`. Boot launcher dùng các dependency của ứng dụng và nhóm `lib-provided` để khởi chạy embedded server.
2. **Triển khai lên servlet container:** copy WAR vào cơ chế deploy của Tomcat/Jetty/application server. Container khởi tạo ứng dụng qua Servlet API và cung cấp server runtime của nó.

Để hỗ trợ traditional deployment, ứng dụng cần một class kế thừa `SpringBootServletInitializer` và override `configure`. Main method vẫn có thể được giữ lại để chạy độc lập:

```java
package com.example.warconflict;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class WarConflictApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(WarConflictApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(WarConflictApplication.class, args);
    }
}
```

`SpringBootServletInitializer` cho phép servlet container phát hiện và cấu hình Spring application context khi WAR được deploy. `main` dùng cho chế độ executable WAR. Không cần tự tạo hai ứng dụng Spring riêng cho hai cách khởi chạy.

**Lưu ý:** Spring WebFlux không hỗ trợ WAR deployment theo cách traditional này vì WebFlux mặc định dùng embedded Reactor Netty và không dựa vào Servlet API. Ví dụ trong bài dùng Spring MVC với `spring-boot-starter-web`.

## 4. Phiên bản Java, Spring Boot và Servlet container phải tương thích

Ví dụ này chọn Spring Boot **3.3.13**. Các yêu cầu đáng chú ý của nhánh này:

| Thành phần | Yêu cầu/phiên bản trong ví dụ |
| --- | --- |
| Java | Java 17 trở lên |
| Maven | 3.6.3 trở lên |
| Gradle | 7.5+ trong dòng 7.x hoặc 8.x |
| Spring Framework | 6.1.21 trở lên theo BOM Boot 3.3.13 |
| Servlet container | Tương thích Servlet 5.0 trở lên |
| Tomcat tham chiếu | Tomcat 10.1.x; dòng Boot 3.3 hỗ trợ Tomcat 10.1.25 trở lên |

Tomcat 10.1 triển khai Servlet 6.0 và dùng namespace Jakarta. Tomcat 9 triển khai Servlet 4.0 thuộc thế hệ Java EE cũ. **Tomcat 9 không phải container tương thích để triển khai trực tiếp WAR Spring Boot 3.3** vì khác Servlet API generation.

Trước khi build WAR, phải biết server đích đang dùng:
- Tên và version container (Tomcat, Jetty, Undertow, WebLogic, WebSphere...).
- Servlet specification version.
- JDK chạy server.
- Các thư viện dùng chung được cài ở thư mục server.
- Chính sách classloader và cấu hình delegation của container.

Không chỉ nhìn version Java. Java 17 có thể chạy nhiều server, nhưng một server dùng Servlet API cũ vẫn không đáp ứng yêu cầu của ứng dụng Boot 3.

## 5. Những dấu hiệu thường gặp khi triển khai WAR

| Lỗi/log | Nguyên nhân có thể | Hướng điều tra đầu tiên |
| --- | --- | --- |
| `NoSuchMethodError` | Class được compile theo API mới nhưng runtime nạp version cũ | Xác định JAR thực sự cung cấp class |
| `NoSuchFieldError` | Hai version của cùng thư viện không tương thích | So sánh dependency tree và WAR |
| `NoClassDefFoundError: javax/servlet/...` | Thư viện cũ cần Java EE Servlet API trong khi app dùng Jakarta | Kiểm tra dependency `javax.servlet` và container |
| `NoClassDefFoundError: jakarta/servlet/...` | Container quá cũ hoặc Jakarta API không có trong runtime | Kiểm tra Servlet version và provided scope |
| `ClassCastException: X cannot be cast to X` | Cùng tên class được nạp bởi classloader khác nhau | Kiểm tra server shared libs và app libs |
| `LinkageError` | Class/API không tương thích hoặc duplicate class | Xem class-loading log và dependency graph |
| Nhiều SLF4J providers/bindings | Nhiều logging implementation cùng có mặt | Kiểm tra SLF4J, Logback, Log4j2 |
| WAR chạy bằng `java -jar` nhưng deploy server lỗi | Embedded container trong `lib-provided` chạy tốt, container bên ngoài không tương thích hoặc cấu hình khác | Kiểm tra target server và classloader |
| Deploy thành công nhưng 404 | Context path, servlet mapping hoặc component scan sai | Kiểm tra tên WAR, controller và deployment logs |
| `UnsupportedClassVersionError` | Bytecode được compile cao hơn JDK của server | Kiểm tra Java target và JDK runtime |

Một exception là **triệu chứng**, không phải kết luận. Ví dụ `NoClassDefFoundError` có thể do thiếu JAR, scope sai, namespace sai hoặc một lỗi khởi tạo class trước đó. Hãy đọc cả nguyên nhân sâu nhất (root cause) và class nguồn được JVM nạp.

## 6. Project Spring Boot Java 17 dùng để thực hành

Cấu trúc project:

```text
war-conflict-demo/
├── pom.xml                         # Phương án Maven
├── settings.gradle                 # Phương án Gradle
├── build.gradle                    # Phương án Gradle
└── src/
    ├── main/java/com/example/warconflict/
    │   ├── WarConflictApplication.java
    │   └── DiagnosticController.java
    └── test/java/com/example/warconflict/
        └── DiagnosticControllerTest.java
```

Maven và Gradle là **hai cách build thay thế nhau**. Java source được dùng chung.

### 6.1. Main class hỗ trợ cả hai cách chạy

File `src/main/java/com/example/warconflict/WarConflictApplication.java`:

```java
package com.example.warconflict;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class WarConflictApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {
        return application.sources(WarConflictApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(WarConflictApplication.class, args);
    }
}
```

Package `com.example.warconflict` được chọn làm package gốc để component scan tìm controller trong cùng package và các package con.

### 6.2. Endpoint kiểm tra WAR

File `src/main/java/com/example/warconflict/DiagnosticController.java`:

```java
package com.example.warconflict;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DiagnosticController {

    @GetMapping("/diagnostic")
    public String diagnostic() {
        return "war-conflict-demo-ok";
    }
}
```

Khi ứng dụng hoạt động, HTTP `GET /diagnostic` trả body:

```text
war-conflict-demo-ok
```

Đây là HTTP response body, không phải toàn bộ log khởi động. Endpoint đơn giản giúp tách lỗi deploy/container khỏi lỗi nghiệp vụ phức tạp.

### 6.3. Test endpoint bằng MockMvc

File `src/test/java/com/example/warconflict/DiagnosticControllerTest.java`:

```java
package com.example.warconflict;

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
class DiagnosticControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void diagnosticEndpointReturnsExpectedBody() throws Exception {
        mockMvc.perform(get("/diagnostic"))
                .andExpect(status().isOk())
                .andExpect(content().string("war-conflict-demo-ok"));
    }
}
```

Test này kiểm tra Spring MVC mapping trong test context. Nó không thay thế smoke test trên servlet container thực tế vì container ngoài có classloader, Servlet API và cấu hình server riêng.

## 7. Maven: đóng gói WAR và đánh dấu embedded Tomcat là provided

File `pom.xml` đầy đủ:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>war-conflict-demo</artifactId>
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
```

Các điểm quan trọng:

1. `<packaging>war</packaging>` yêu cầu Maven tạo WAR.
2. `spring-boot-starter-web` cung cấp Spring MVC và starter cho embedded servlet container.
3. `spring-boot-starter-tomcat` được khai báo trực tiếp với `<scope>provided</scope>` để Maven coi Tomcat là runtime do môi trường triển khai cung cấp.
4. `spring-boot-starter-test` chỉ dùng trong test.
5. Spring Boot starter parent quản lý dependency versions và đã cấu hình execution `repackage` cho plugin. Khi dùng parent này, không cần tự thêm một execution repackage trùng lặp.

Spring Boot Maven Plugin xử lý provided dependencies của executable WAR bằng cách đặt chúng vào `WEB-INF/lib-provided`. Vì thế WAR vẫn có thể chạy bằng `java -jar`, đồng thời servlet container bên ngoài không phải lấy embedded Tomcat từ `WEB-INF/lib`.

**Không đánh dấu tất cả thư viện là provided.** Spring Framework, Jackson, logging và các thư viện nghiệp vụ vẫn cần nằm trong WAR trừ khi container thực sự cung cấp chúng theo một hợp đồng version rõ ràng. Thông thường chỉ đánh dấu embedded servlet container và API do container cung cấp.

## 8. Maven: build và kiểm tra nội dung WAR

Từ thư mục gốc:

```bash
java -version
./mvnw clean verify
```

Nếu không có Maven Wrapper, dùng Maven cài sẵn tương thích. Trên Windows PowerShell, dùng `.\mvnw.cmd clean verify`.

Artifact dự kiến:

```text
target/war-conflict-demo-1.0.0.war
```

Kiểm tra cấu trúc:

```bash
jar tf target/war-conflict-demo-1.0.0.war
```

Tìm các vùng classpath:

```bash
jar tf target/war-conflict-demo-1.0.0.war | grep '^WEB-INF/'
```

Các entry chính cần nhận diện:
- `WEB-INF/classes/com/example/warconflict/WarConflictApplication.class`.
- `WEB-INF/classes/com/example/warconflict/DiagnosticController.class`.
- `WEB-INF/lib/spring-webmvc-*.jar` và các application dependencies.
- `WEB-INF/lib-provided/tomcat-embed-core-*.jar` cùng các thư viện embedded Tomcat được đánh dấu provided.

Đây là các **nhóm entry mong đợi**, version và số lượng file cụ thể tùy dependency graph. Nếu Tomcat embedded xuất hiện trong `WEB-INF/lib` thay vì `WEB-INF/lib-provided`, kiểm tra scope trong effective POM và dependency tree.

### 8.1. Chạy executable WAR độc lập

```bash
java -jar target/war-conflict-demo-1.0.0.war
```

Terminal khác:

```bash
curl -fsS http://localhost:8080/diagnostic
```

Kết quả:

```text
war-conflict-demo-ok
```

Nếu bước này chạy nhưng deploy lên Tomcat lỗi, khả năng cao vấn đề nằm ở **container version, classloader hoặc thư viện do server cung cấp**. Nếu cả hai cách đều lỗi, kiểm tra artifact và dependency graph trước.

## 9. Gradle: dùng war plugin và providedRuntime

File `settings.gradle`:

```groovy
rootProject.name = 'war-conflict-demo'
```

File `build.gradle` đầy đủ (Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'

    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

springBoot {
    mainClass = 'com.example.warconflict.WarConflictApplication'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`war` plugin tạo configuration `providedRuntime`. Spring Boot Gradle plugin tạo task `bootWar` cho executable WAR và đưa những dependency trong `providedRuntime` vào `WEB-INF/lib-provided`.

**`providedRuntime` được ưu tiên hơn `compileOnly`** cho embedded servlet container trong trường hợp này. `compileOnly` không có dependency trên test runtime classpath, có thể làm các web integration tests thất bại. Không thêm cả Tomcat và Jetty như hai embedded server độc lập vào cùng application trừ khi đã cấu hình rõ server nào được sử dụng.

Build:

```bash
./gradlew clean test bootWar
```

Trên Windows PowerShell dùng `.\gradlew.bat clean test bootWar`.

Artifact từ task `bootWar` nằm trong `build/libs/`, ví dụ:

```text
build/libs/war-conflict-demo-1.0.0.war
```

Kiểm tra **artifact của `bootWar`**, không chọn nhầm plain WAR do task `war` thông thường tạo ra nếu thư mục có nhiều file cùng tên/classifier.

### 9.1. Kiểm tra WAR của Gradle

```bash
jar tf build/libs/war-conflict-demo-1.0.0.war | grep '^WEB-INF/'
java -jar build/libs/war-conflict-demo-1.0.0.war
```

Khi chạy bằng `java -jar`, terminal thứ hai gọi:

```bash
curl -fsS http://localhost:8080/diagnostic
```

Body mong đợi vẫn là `war-conflict-demo-ok`. Khi deploy lên container, dùng chính WAR từ `bootWar` để giữ đúng cách đóng gói executable/deployable của Spring Boot.

## 10. Maven giải quyết version conflict như thế nào?

Maven tự động thu thập cả dependency trực tiếp lẫn transitive. Khi cùng một artifact được yêu cầu ở nhiều version, Maven dùng quy tắc **nearest definition**:
- Version ở đường dẫn dependency gần project nhất được chọn.
- Nếu hai version có cùng độ sâu, khai báo xuất hiện trước được chọn.
- Một dependency khai báo version trực tiếp trong project có thể thắng version chỉ được yêu cầu ở nhánh transitive.
- `dependencyManagement` có thể kiểm soát version của dependency khi nó xuất hiện trong graph, nhưng **không tự thêm dependency vào classpath**.

Ví dụ:

```text
war-conflict-demo
├── client-a
│   └── spring-core:6.1.x
└── client-b
    └── helper
        └── spring-core:6.0.x
```

Ở ví dụ minh họa này, đường tới `spring-core:6.1.x` gần project hơn nên Maven có thể chọn version đó. Maven không tự hiểu version nào phù hợp nhất với toàn bộ Spring Boot platform; vì thế dùng BOM/parent để quản lý version đồng bộ rất quan trọng.

Một tình huống nguy hiểm là khai báo thủ công một module Spring cũ:

```xml
<dependency>
    <groupId>org.springframework</groupId>
    <artifactId>spring-webmvc</artifactId>
    <version>5.3.39</version>
</dependency>
```

Đây là ví dụ **không phù hợp** với Spring Boot 3.3 vì Boot 3.3 sử dụng Spring Framework 6.1.x và namespace Jakarta. Việc ép riêng `spring-webmvc` về 5.3 trong khi các module Spring khác theo BOM 6.1 có thể tạo binary incompatibility và trộn hai thế hệ API. Cách đúng thường là **xóa version override** và để Spring Boot BOM quản lý cả nhóm Spring.

## 11. Maven: tìm version nào đã thực sự được đóng gói

Các lệnh chẩn đoán:

```bash
./mvnw dependency:tree
./mvnw dependency:tree -Dverbose
./mvnw dependency:tree -Dincludes=org.springframework:*
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
```

Ý nghĩa:
- `dependency:tree` hiển thị dependency graph mà Maven resolve.
- `-Dverbose` giúp thấy cả node bị loại do mediation, hữu ích khi truy vết version conflict.
- `-Dincludes` lọc theo group/artifact pattern để tập trung vào Spring hoặc thư viện nghi ngờ.
- `help:effective-pom` hiển thị POM sau inheritance, profiles và dependency management.

Khi muốn tìm một JAR cụ thể:

```bash
./mvnw dependency:tree -Dverbose -Dincludes=org.springframework:spring-core
./mvnw dependency:tree -Dverbose -Dincludes=org.slf4j:*
```

Nếu dependency tree cho thấy version đã chọn đúng nhưng WAR vẫn chạy sai, hãy kiểm tra **archive và classloader**. Maven dependency tree không phản ánh những JAR được copy thủ công vào thư mục server global hoặc class được đóng gói bên trong shaded JAR khác coordinates.

### 11.1. Exclude một transitive dependency trong Maven

Khi một thư viện cũ kéo theo một dependency không mong muốn, có thể exclude trên **đường dẫn cụ thể**:

```xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>legacy-client</artifactId>
    <version>1.2.0</version>
    <exclusions>
        <exclusion>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-simple</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

`com.acme:legacy-client` là tọa độ ví dụ. Exclusion gắn với dependency khai báo ở đó; nếu một dependency khác cũng kéo `slf4j-simple` vào, artifact vẫn có thể xuất hiện qua nhánh khác. Sau khi exclude, chạy lại `dependency:tree` và test logging runtime.

**Không exclude theo cảm tính.** Nếu thư viện thật sự gọi API của artifact bị loại, app có thể build được nhưng fail với `NoClassDefFoundError` khi code path đó chạy. Phải thay bằng implementation tương thích hoặc nâng cấp thư viện gốc.

## 12. Gradle giải quyết version conflict như thế nào?

Gradle mặc định chọn version cao hơn khi một module cùng group/name được yêu cầu ở nhiều version trong cùng configuration. Quyết định thực tế còn chịu ảnh hưởng bởi:
- Platform/BOM và dependency constraints.
- Strict version constraints.
- Variant attributes/capabilities.
- Resolution rules, substitution và dependency forcing.
- Configuration đang resolve (compile, runtime, provided, test).

Ví dụ dependency trực tiếp có version cũ nhưng một thư viện khác yêu cầu version mới hơn:

```groovy
dependencies {
    implementation 'com.acme:client-a:1.0.0'
    implementation 'com.acme:client-b:1.0.0'
}
```

Nếu cả hai nhánh yêu cầu `org.example:codec` ở version khác nhau, Gradle thường chọn version cao hơn theo quy tắc conflict resolution. Tuy nhiên, version cao hơn không nhất thiết binary-compatible với tất cả consumer. Phải xem lý do lựa chọn và kiểm thử app.

Có thể yêu cầu build fail ngay khi một configuration có nhiều version được yêu cầu:

```groovy
configurations.configureEach {
    resolutionStrategy {
        failOnVersionConflict()
    }
}
```

Đây là **guardrail tùy chọn** cho dự án muốn xử lý conflict tường minh. Nó có thể khiến build fail ở những graph vốn đang được Gradle tự giải quyết; chỉ bật khi team sẵn sàng quản lý các conflict đó. Nó không phát hiện mọi trường hợp duplicate class từ hai artifact coordinates khác nhau.

## 13. Gradle: chẩn đoán bằng dependencies và dependencyInsight

Chạy từ root project:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration providedRuntime
./gradlew dependencies --configuration testRuntimeClasspath
```

Dùng `dependencyInsight` cho module nghi ngờ:

```bash
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency tomcat-embed-core --configuration providedRuntime
```

`dependencyInsight` giải thích:
- Những dependency nào yêu cầu module đó.
- Version nào được chọn.
- Version nào bị từ chối/không chọn.
- Selection reason đến từ constraint, conflict resolution hay rule.

Nếu dự án nhiều module, chạy đúng project path, ví dụ `./gradlew :webapp:dependencyInsight --dependency spring-core --configuration runtimeClasspath`. Không dùng kết quả configuration của một library module để kết luận WAR của application module có cùng classpath.

### 13.1. Exclude transitive dependency trong Gradle

Groovy DSL:

```groovy
dependencies {
    implementation('com.acme:legacy-client:1.2.0') {
        exclude group: 'org.slf4j', module: 'slf4j-simple'
    }
}
```

Kotlin DSL:

```kotlin
dependencies {
    implementation("com.acme:legacy-client:1.2.0") {
        exclude(group = "org.slf4j", module = "slf4j-simple")
    }
}
```

Hai ví dụ trên loại module khỏi nhánh dependency tương ứng. Nếu một nhánh khác vẫn kéo module đó vào, nó có thể tiếp tục xuất hiện. Luôn kiểm tra lại `runtimeClasspath`/`providedRuntime` sau thay đổi và chạy test.

## 14. BOM và dependency management: tránh tự trộn version Spring

Spring Boot starter parent hoặc BOM quản lý các version đã được căn chỉnh với nhau. Ví dụ POM ở mục 7 kế thừa `spring-boot-starter-parent` 3.3.13 nên các starter và module Spring không cần khai báo version riêng.

Nếu dùng corporate parent thay vì Boot parent, có thể import Boot BOM trong `dependencyManagement`:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.13</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Đây là **đoạn ghép vào POM hiện có**, không phải một POM hoàn chỉnh. BOM quản lý version cho dependencies được khai báo; nó không tự thêm `spring-boot-starter-web` hoặc plugin vào project.

Với Gradle, Spring Boot plugin kết hợp dependency-management plugin có thể import Boot BOM tự động. Nếu tự dùng Gradle platform, cần khai báo platform rõ ràng và nhất quán. Không vừa import nhiều BOM có version chồng lấn vừa thêm hàng loạt explicit version mà không kiểm tra selection reasons.

**Nguyên tắc:** khi nâng Spring Boot, nâng theo BOM/parent của release đó. Không nâng riêng `spring-core`, `spring-webmvc`, `spring-context` hoặc Jackson lên version tùy ý nếu chưa xác minh ma trận tương thích.

## 15. Phân biệt `provided`, `runtime` và `test` khi đóng gói WAR

Scope quyết định thư viện xuất hiện ở đâu:

| Scope/configuration | Compile code | Test runtime | Runtime ứng dụng | WAR thông thường |
| --- | --- | --- | --- | --- |
| Maven `compile` | Có | Có | Có | `WEB-INF/lib` |
| Maven `runtime` | Không cần compile | Có | Có | `WEB-INF/lib` |
| Maven `provided` | Có | Có | Do container cung cấp | Không vào `WEB-INF/lib` thông thường; Boot executable WAR đưa vào `lib-provided` |
| Maven `test` | Không | Có | Không | Không |
| Gradle `implementation` | Có | Có | Có | `WEB-INF/lib` |
| Gradle `runtimeOnly` | Không cần compile | Có | Có | `WEB-INF/lib` |
| Gradle `providedRuntime` | Phù hợp runtime provided | Có trên test runtime | Do container cung cấp khi deploy ngoài | Boot WAR đưa vào `WEB-INF/lib-provided` |
| Gradle `compileOnly` | Có | Không tự động có trên test runtime | Do môi trường cung cấp | Không đóng gói |

Với WAR triển khai lên Tomcat ngoài:
- Embedded Tomcat starter được đánh dấu `provided` (Maven) hoặc `providedRuntime` (Gradle).
- Spring MVC, Spring Context, Jackson và application libraries vẫn nằm trong WAR nếu ứng dụng cần chúng.
- Servlet container cung cấp Servlet API cho ứng dụng.
- Không đánh dấu nhầm các thư viện nghiệp vụ là provided nếu server không cung cấp chúng.

**Vì sao Gradle không dùng `compileOnly`?** Spring Boot khuyến nghị `providedRuntime` vì nó vẫn có mặt trong test runtime classpath, trong khi `compileOnly` có thể khiến web integration tests thiếu container classes.

## 16. `javax.servlet` và `jakarta.servlet` không thể thay thế cho nhau

Đây là một nguồn lỗi lớn khi nâng ứng dụng lên Spring Boot 3:

- Spring Boot 2 / Spring Framework 5 thuộc thế hệ Java EE cũ, thường dùng package `javax.servlet.*`.
- Spring Boot 3 / Spring Framework 6 chuyển sang Jakarta EE, dùng `jakarta.servlet.*`.
- Đây là **hai namespace khác nhau**. Một class implement `javax.servlet.Filter` không phải là một `jakarta.servlet.Filter`, dù tên class và phương thức có vẻ tương tự.

Ví dụ code Boot 3 phải import:

```java
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
```

Không dùng:

```java
import javax.servlet.Filter;
```

nếu class được compile cho Spring Boot 3.3/Jakarta Servlet.

Khi gặp `ClassNotFoundException: javax.servlet...` hoặc `NoClassDefFoundError: javax/servlet/...` trong app Boot 3, hãy tìm dependency cũ hoặc library vendor chưa được migrate. Thêm cả hai Servlet API vào WAR **không** biến thư viện javax thành Jakarta-compatible; cần nâng cấp hoặc thay thế library.

Nếu deploy Boot 3 WAR lên Tomcat 9, vấn đề không thể giải quyết chỉ bằng cách đổi dependency scope. Hãy dùng container hỗ trợ Servlet 5.0+ và Jakarta namespace, ví dụ Tomcat 10.1, hoặc giữ app ở generation tương thích với server nếu chưa thể nâng container.

## 17. Không đóng gói nhiều servlet container cùng lúc

Một Spring Boot web starter thường kéo theo embedded Tomcat. Nếu đồng thời thêm Jetty/Undertow hoặc một container starter khác mà không loại container còn lại, WAR có thể chứa các implementation cạnh tranh.

Ví dụ cấu hình không nên có đồng thời:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-tomcat'
    implementation 'org.springframework.boot:spring-boot-starter-jetty'
}
```

Đây là ví dụ sai có chủ đích. Hãy chọn **một** embedded container cho chế độ executable WAR, đánh dấu container đó provided nếu deploy ngoài, và bảo đảm WAR không kéo thêm implementation khác ngoài ý muốn.

Với Tomcat ngoài:
- Giữ `spring-boot-starter-tomcat` ở provided scope/configuration.
- Không thêm Tomcat embed JAR thủ công vào `WEB-INF/lib`.
- Không copy thêm Tomcat embed JAR vào thư mục shared lib của server.
- Không thêm Servlet API cũ vào WAR.

Nếu chuyển sang Jetty hoặc Undertow, cần thay đúng starter/container dependency và đối chiếu version/Servlet API tương ứng. Đừng chỉ exclude một JAR mà vẫn giữ các module khác của container cũ trong graph.

## 18. Logging conflict: nhiều SLF4J providers hoặc logging bridges

Spring Boot thường dùng Logback qua `spring-boot-starter-logging`. Nếu ứng dụng muốn chuyển sang Log4j2, cần loại starter logging mặc định theo cách Spring Boot hướng dẫn và dùng starter Log4j2 tương ứng.

Các lỗi thường gặp:
- Nhiều SLF4J providers cùng xuất hiện.
- Cả Logback và Log4j2 cùng được cấu hình làm backend.
- `slf4j-simple` hoặc `slf4j-reload4j` bị kéo vào từ một thư viện cũ.
- `commons-logging` bị đóng gói cùng các bridge không cần thiết.
- Container server có logging implementation chung xung đột với app.

Kiểm tra:

```bash
./mvnw dependency:tree -Dverbose -Dincludes=org.slf4j:*,ch.qos.logback:*,org.apache.logging.log4j:*
```

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency slf4j-simple --configuration runtimeClasspath
```

Một app nên có **một logging backend được chọn rõ ràng** và những bridge cần thiết theo stack. Đừng thêm một provider mới chỉ để che cảnh báo; việc đó có thể khiến log bị mất, ghi hai lần hoặc chọn implementation khác giữa local và container.

## 19. Classloader của servlet container và thư viện dùng chung

Build tool chỉ quyết định dependency graph trong ứng dụng. Khi WAR chạy, container còn có classpath của server:

```text
Container / parent classloader
├── Java platform classes
├── Container implementation and shared libraries
└── Web application classloader
    ├── WEB-INF/classes/
    └── WEB-INF/lib/*.jar
```

Tomcat mặc định dùng web application classloader với cơ chế ưu tiên thư viện của webapp cho phần lớn class, nhưng có các nhóm API và lớp nền phải tuân theo quy tắc delegation riêng. Các container khác có thể có chính sách khác hoặc cho cấu hình parent-first.

Thư mục server như `$CATALINA_BASE/lib` và `$CATALINA_HOME/lib` có thể cung cấp JAR dùng chung cho nhiều web applications. Nếu đặt Spring, Jackson, logging hoặc library nghiệp vụ vào đây, các WAR khác cũng có thể nhìn thấy chúng và xảy ra xung đột version/classloader.

**Khuyến nghị:**
- Giữ thư viện riêng của ứng dụng trong `WEB-INF/lib`.
- Chỉ để server cung cấp những API/runtime mà container chịu trách nhiệm (Servlet/JSP/JNDI và các thành phần được quản trị rõ).
- Tránh copy JAR ứng dụng vào shared lib để “sửa nhanh” lỗi thiếu class.
- Nếu vendor application server yêu cầu cấu hình package preference/delegation, làm theo tài liệu đúng container và kiểm tra ảnh hưởng tới các ứng dụng khác.
- Không đổi toàn server sang parent-first hoặc local-first chỉ để xử lý một WAR khi chưa đánh giá phạm vi ảnh hưởng.

Lỗi `ClassCastException: com.acme.Type cannot be cast to com.acme.Type` thường gợi ý hai class cùng tên được nạp bởi classloader khác nhau. Hai class có cùng tên đầy đủ nhưng classloader khác nhau vẫn là hai runtime types khác nhau.

## 20. Kiểm tra class nào được JVM nạp từ đâu

Khi dependency tree và WAR trông đúng nhưng server vẫn nạp nhầm class, bật Java class-loading log tạm thời.

Với Java 17:

```bash
java -Xlog:class+load=info -jar target/war-conflict-demo-1.0.0.war
```

Log có thể chỉ ra class được nạp từ JAR hoặc nguồn nào. Khi chạy trong Tomcat ngoài, thêm flag tương tự vào `CATALINA_OPTS` hoặc cấu hình JVM options của service container rồi restart server theo quy trình vận hành.

Ví dụ trên Bash:

```bash
export CATALINA_OPTS="$CATALINA_OPTS -Xlog:class+load=info"
```

Log class loading có thể rất lớn. Chỉ bật trong một lần chẩn đoán, lọc các package liên quan như `org.springframework`, `org.slf4j`, `jakarta.servlet` hoặc class gây lỗi, rồi tắt sau khi điều tra.

Một cách chẩn đoán khác là kiểm tra code source của class trong Java:

```java
private static void printClassOrigin(Class<?> type) {
    var source = type.getProtectionDomain().getCodeSource();
    String location = source == null
            ? "<container, bootstrap, or unknown source>"
            : source.getLocation().toString();

    System.out.println(type.getName()
            + " -> " + location
            + " | loader=" + type.getClassLoader());
}
```

Đây là **method chẩn đoán minh họa**, không phải file Java độc lập. Một số class của JVM/container có thể trả `null` ở `CodeSource`; khi đó cần dùng class-loading log và container diagnostics.

## 21. Quy trình xử lý conflict theo thứ tự

Khi WAR lỗi, làm lần lượt để tránh sửa nhiều dependency cùng lúc:

1. **Ghi lại môi trường lỗi:** Java, Spring Boot, Maven/Gradle, container và version, context path, JVM flags.
2. **Phân loại exception:** thiếu class, method không tương thích, duplicate provider, namespace mismatch hay classloader mismatch.
3. **Kiểm tra dependency graph:** Maven `dependency:tree -Dverbose` hoặc Gradle `dependencyInsight`.
4. **Kiểm tra scope:** container dependencies có được đánh dấu provided đúng không?
5. **Kiểm tra WAR thực tế:** xem `WEB-INF/classes`, `WEB-INF/lib` và `WEB-INF/lib-provided`.
6. **Kiểm tra container version:** Servlet specification, Jakarta namespace và JDK runtime.
7. **Kiểm tra server shared libraries:** `CATALINA_BASE/lib`, `CATALINA_HOME/lib` hoặc cơ chế tương ứng của application server.
8. **Xác định class origin:** bật class-loading logs tạm thời nếu graph chưa đủ bằng chứng.
9. **Sửa một nguyên nhân:** align BOM/version, loại duplicate, đổi scope, nâng container hoặc migrate library.
10. **Build và test lại:** unit/integration test, chạy `java -jar` và deploy lên đúng loại container.
11. **So sánh WAR mới:** xác nhận chỉ các JAR dự kiến thay đổi, không thêm thư viện ngoài ý muốn.
12. **Ghi lại thay đổi:** version được chọn, dependency bị exclude, lý do và kết quả smoke test.

Không thay hàng loạt version bằng bản mới nhất. Một upgrade có thể giải quyết `NoSuchMethodError` nhưng lại tạo API mismatch ở dependency khác.

## 22. Một số cách sửa theo tình huống

### 22.1. Hai version của Spring Framework

**Triệu chứng:** `NoSuchMethodError` trong `org.springframework` hoặc nhiều version Spring trong dependency report.

**Cách xử lý:**
- Xóa version Spring khai báo thủ công.
- Để Spring Boot BOM quản lý toàn bộ Spring modules.
- Nếu dùng corporate parent, import đúng Boot BOM.
- Kiểm tra Maven effective POM/Gradle dependencyInsight.
- Không nâng riêng `spring-core` mà giữ `spring-webmvc` hoặc `spring-context` ở version khác.

### 22.2. Embedded Tomcat bị đóng gói sai

**Triệu chứng:** WAR deploy ngoài báo lỗi Servlet/container, hoặc class được nạp từ Tomcat embed thay vì server.

**Cách xử lý:**
- Maven: đánh dấu `spring-boot-starter-tomcat` là `provided`.
- Gradle: đưa `spring-boot-starter-tomcat` vào `providedRuntime`.
- Rebuild executable WAR.
- Kiểm tra embedded Tomcat nằm trong `WEB-INF/lib-provided`, không nằm trong `WEB-INF/lib`.
- Xác minh server đích đáp ứng Servlet API của Boot.

### 22.3. Thư viện cũ dùng javax trong ứng dụng Boot 3

**Triệu chứng:** `NoClassDefFoundError: javax/servlet/...` hoặc class filter/listener không tương thích.

**Cách xử lý:**
- Xác định library nào còn import `javax.servlet`.
- Nâng lên bản hỗ trợ Jakarta hoặc thay bằng thư viện khác.
- Loại các API Java EE cũ khỏi dependency graph.
- Compile và test lại trên Servlet container Jakarta-compatible.
- Không cố thêm cả `javax.servlet-api` và `jakarta.servlet-api` vào WAR để chữa lỗi.

### 22.4. Nhiều logging providers

**Triệu chứng:** SLF4J báo nhiều providers/bindings hoặc log trùng/mất.

**Cách xử lý:**
- Xem dependency tree của `org.slf4j`, Logback và Log4j2.
- Chọn một backend.
- Exclude provider được kéo vào từ thư viện cũ ở đúng dependency path.
- Kiểm tra cả shared libraries của server nếu container có logging implementation riêng.

### 22.5. ClassCastException cùng tên class

**Triệu chứng:** `X cannot be cast to X` dù package/class name giống nhau.

**Cách xử lý:**
- Kiểm tra classloader của hai object.
- Xem class-loading log để tìm JAR/source.
- Kiểm tra JAR bị đặt ở cả server shared lib và `WEB-INF/lib`.
- Gỡ bản copy không cần thiết hoặc chỉnh cấu hình container-specific một cách có kiểm soát.
- Tránh sửa bằng cách ép cast hoặc đổi tên class nếu gốc rễ là classloader isolation.

## 23. Bảng troubleshooting nhanh

| Hiện tượng | Kiểm tra | Hướng xử lý ưu tiên |
| --- | --- | --- |
| `NoSuchMethodError` trong Spring | Version `spring-core`, `spring-web`, `spring-context` | Dùng Boot BOM đồng bộ |
| `NoClassDefFoundError: jakarta.servlet` | Servlet version của container, WAR scopes | Dùng Servlet 5.0+ container và provided config đúng |
| `NoClassDefFoundError: javax.servlet` | Dependency cũ hoặc container sai generation | Nâng library sang Jakarta hoặc dùng platform tương thích |
| Tomcat embed nằm trong `WEB-INF/lib` | POM scope/Gradle configuration | Đưa starter Tomcat vào provided/providedRuntime |
| WAR không chạy bằng `java -jar` | Thiếu Boot repackage/BootWar hoặc chọn plain WAR | Build bằng Spring Boot plugin và chọn executable artifact |
| WAR chạy độc lập nhưng deploy server fail | Container version, classloader, shared libs | Test trên container đích và kiểm tra class origin |
| `ClassCastException` cùng class name | Classloader identity | Tìm class bị nạp từ hai nguồn |
| SLF4J báo nhiều providers | Dependency tree logging | Chỉ giữ một backend/bridge stack |
| Hai version của library xuất hiện trong Maven tree | Nearest mediation, direct override, BOM | Dùng dependencyManagement và loại override sai |
| Gradle chọn version cao hơn ngoài ý muốn | DependencyInsight, constraints | Quản lý platform/constraint có lý do |
| WAR có thư viện không dùng | Runtime graph, transitive dependencies | Phân tích, loại dependency an toàn và kiểm thử |
| Deploy 404 | WAR name/context path/mapping | Kiểm tra URL theo context path thực tế |
| App không khởi tạo vì Java bytecode | JDK server thấp hơn target | Đồng bộ Java toolchain và JDK runtime |
| Container có Spring JAR trong global lib | Server shared library path | Gỡ hoặc quản trị version dùng chung theo policy |
| Build fail duplicate archive entry | Plugin/packaging resources, shaded dependencies | Xác định entry trùng, xử lý source JAR phù hợp |

## 24. Kiểm tra CI/CD cho WAR

Một pipeline nên kiểm tra nhiều lớp:

```bash
./mvnw -B clean verify
./mvnw dependency:tree -Dverbose
jar tf target/war-conflict-demo-1.0.0.war
```

Với Gradle:

```bash
./gradlew clean test bootWar
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration providedRuntime
jar tf build/libs/war-conflict-demo-1.0.0.war
```

Các kiểm tra quan trọng:
- Java/toolchain và Spring Boot plugin version đúng với policy.
- Dependency graph không có override ngoài dự kiến.
- Embedded container nằm trong provided scope/configuration.
- WAR chứa application classes và runtime dependencies cần thiết.
- Không đóng gói nhầm `javax.servlet-api` hoặc nhiều embedded containers.
- Không có nhiều SLF4J providers không chủ đích.
- Executable WAR chạy được bằng `java -jar` nếu đó là mode được hỗ trợ.
- WAR deploy được lên container cùng loại/version với production.
- Endpoint health/smoke test trả kết quả mong đợi.
- Image/Artifact được scan và lưu checksum/provenance theo chính sách.

**Không chỉ test bằng `java -jar`.** Cách chạy độc lập dùng embedded container trong `lib-provided`; container ngoài có thể có classloader, API và server configuration khác. Cần ít nhất một integration/deployment test trên container đích hoặc môi trường staging tương đương.

## 25. Checklist trước khi phát hành

- [ ] Spring Boot, Spring Framework, Java và servlet container nằm trong ma trận tương thích.
- [ ] Ứng dụng dùng `SpringBootServletInitializer` để hỗ trợ traditional WAR deployment.
- [ ] Main method được giữ nếu cần chạy executable WAR.
- [ ] Maven có `<packaging>war</packaging>` hoặc Gradle đã áp dụng `war` plugin.
- [ ] Embedded servlet container được đánh dấu `provided`/`providedRuntime`.
- [ ] Gradle dùng `providedRuntime` thay vì `compileOnly` cho container runtime cần trong test.
- [ ] WAR có `WEB-INF/classes` và các thư viện ứng dụng cần thiết trong `WEB-INF/lib`.
- [ ] Provided runtime của executable WAR nằm trong `WEB-INF/lib-provided`.
- [ ] Không đóng gói Servlet API sai thế hệ hoặc cả `javax` và `jakarta` theo cách không tương thích.
- [ ] Không có Tomcat/Jetty/Undertow cạnh tranh ngoài dự kiến.
- [ ] Spring modules và Jackson được quản lý theo Boot BOM hoặc platform đã phê duyệt.
- [ ] Dependency tree và dependencyInsight đã được kiểm tra.
- [ ] Không có logging providers trùng lặp.
- [ ] Không có application libraries bị copy thủ công vào server shared lib.
- [ ] Đã kiểm tra class-loading logs khi có lỗi runtime chưa giải thích được.
- [ ] Unit/integration tests và WAR smoke test thành công.
- [ ] Đã deploy thử trên servlet container tương đương production.
- [ ] Artifact deploy là executable/deployable WAR đúng, không nhầm plain WAR.
- [ ] Đã lưu version graph, container/JDK version và checksum artifact để rollback.

**Ghi nhớ:** Xử lý conflict WAR cần đi qua ba lớp: **dependency resolution** (version nào được chọn), **archive packaging** (JAR nào nằm trong `WEB-INF/lib` hay `lib-provided`), và **runtime classloading** (container thực sự nạp class từ đâu). Maven dùng nearest-definition mediation; Gradle mặc định chọn version cao hơn trong version conflict; cả hai vẫn cần BOM/constraints và kiểm tra archive. Với Spring Boot 3, hãy dùng Jakarta-compatible servlet container và đặt embedded server ở provided scope khi deploy WAR ra ngoài. Chỉ coi lỗi đã được xử lý khi WAR build đúng, chạy độc lập theo yêu cầu và deploy thành công trên container thực tế.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Traditional Deployment](https://docs.spring.io/spring-boot/3.3/how-to/deployment/traditional-deployment.html)
- [Spring Boot 3.3.13 — System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html)
- [Spring Boot 3.3 — Maven Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 — Gradle Plugin Packaging](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — Optional and Excluded Dependencies](https://maven.apache.org/guides/introduction/introduction-to-optional-and-excludes-dependencies)
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Gradle — Dependency Constraints and Conflict Resolution](https://docs.gradle.org/current/userguide/dependency_constraints_conflicts.html)
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Gradle — The War Plugin](https://docs.gradle.org/current/userguide/war_plugin.html)
- [Apache Tomcat 10.1 — Class Loader How-To](https://tomcat.apache.org/tomcat-10.1-doc/class-loader-howto.html)
- [Apache Tomcat 10.1 — Loader Component](https://tomcat.apache.org/tomcat-10.1-doc/config/loader.html)
- [Spring Boot 3 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide)
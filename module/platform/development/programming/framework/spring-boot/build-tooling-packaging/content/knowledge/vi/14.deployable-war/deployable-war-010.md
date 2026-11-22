# Kiểm chứng cùng một WAR ở chế độ chạy độc lập và triển khai vào servlet container

## Mục tiêu và cách tiếp cận

Một ứng dụng Spring Boot dùng Servlet có thể được phân phối dưới dạng **executable WAR**. Điều đặc biệt của loại file này là **cùng một WAR** có thể:

1. Chạy trực tiếp bằng `java -jar app.war` nhờ **Spring Boot launcher** và embedded servlet container được đóng trong archive.
2. Được **triển khai vào một servlet container ngoài** (ví dụ Apache Tomcat tương thích), nơi container tiếp nhận WAR, khởi tạo ứng dụng Spring và cung cấp Servlet runtime.

Điều này **không** có nghĩa rằng mọi WAR đều chạy được bằng `java -jar`, hay chỉ cần đổi đuôi `.jar` thành `.war`. Để kiểm chứng, phải xác minh **cấu hình build, lớp khởi tạo, cấu trúc ZIP, cách chạy, HTTP endpoint, URL/context path và chính xác cùng byte của file**.

Sau bài học, bạn sẽ biết:

- Thiết lập **Maven** hoặc **Gradle** để tạo executable WAR vừa chạy độc lập vừa deploy lên Tomcat ngoài.
- Giải thích vai trò của `SpringBootServletInitializer`, `main(String[])`, `spring-boot-starter-web` và cách đánh dấu `spring-boot-starter-tomcat` là **provided**.
- Đọc cấu trúc `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided` và Spring Boot launcher.
- Chạy **hai chế độ từ một file WAR duy nhất, không rebuild ở giữa**, kiểm tra SHA-256 và so sánh kết quả HTTP.
- Phân biệt **cổng**, **context path**, **classpath**, **phân giải property** và **vòng đời** trong hai chế độ.
- Xây dựng checklist cho CI và xử lý những lỗi như HTTP 404, thiếu initializer, trùng Servlet API hoặc chọn nhầm plain WAR.

**Bối cảnh phiên bản của ví dụ:** Spring Boot **3.3.13**, Java **17+**, Maven **3.6.3+** hoặc Gradle **8.x** tương thích, **Apache Tomcat 10.1** bên ngoài (Servlet 6.0). Đó là một tổ hợp để học và đối chiếu tài liệu, **không phải hướng dẫn tự ý nâng/hạ version** cho dự án thực tế. Spring Boot 3.3 có thể chạy với servlet container đáp ứng Servlet 5.0+ nhưng trong bài dùng Tomcat 10.1 để hạn chế khác biệt. Các thế hệ Spring Boot/Tomcat mới hơn có yêu cầu riêng. Tomcat **9** sử dụng namespace `javax.servlet` cũ, không phải đích phù hợp để chạy nguyên một ứng dụng Spring Boot 3.3 dùng `jakarta.servlet`.

## 1. "Cùng một WAR" nghĩa là gì?

Ở bài thực hành, ta tạo **một file**:

```text
dual-mode-0.0.1-SNAPSHOT.war
```

Sau đó:

```text
                        MỘT FILE WAR ĐÃ BUILD
                  (chỉ một tập byte, một SHA-256)
                                 |
                 +---------------+---------------+
                 |                               |
                 v                               v
         java -jar app.war             Copy WAR sang Tomcat ngoài
                 |                               |
           Boot WarLauncher              Tomcat WebApp Loader
                 |                               |
      embedded Tomcat khởi động       Tomcat ngoài khởi tạo webapp
                 |                               |
       GET http://...:18080/probe      GET http://...:8080/dual-mode/probe
                 |                               |
          READY|context=                  READY|context=/dual-mode
```

Hai response là **kỳ vọng của mã nguồn và cài đặt cổng/context path trong ví dụ**, không phải log từ môi trường đã được chạy. Khi triển khai thật, kiểm tra kết quả bằng lệnh `curl` hoặc test client, thay vì chỉ dựa vào sơ đồ.

**Yêu cầu "cùng một WAR":**

- Build **một lần**, dùng file ở `target/` hoặc `build/libs/` để chạy `java -jar`.
- Sau đó **copy đúng file đã kiểm tra**, không chạy thêm `package`/`bootWar` rồi lấy một file khác.
- Đổi **tên bản copy** thành `dual-mode.war` nếu muốn Tomcat dùng context path `/dual-mode`; đổi tên file **không đổi byte nội dung**.
- Tính SHA-256 của file nguồn và bản copy: **hai digest bằng nhau** chứng minh byte file không đổi qua thao tác copy.
- Giữ cấu hình runtime có chủ đích; cùng byte WAR **không có nghĩa** hai môi trường có cùng hostname, port, context path, profile, biến môi trường hoặc version Tomcat.

Để so sánh theo nghĩa chặt chẽ, nên ghi cùng một bản Java, file WAR hash, app version và thông tin external Tomcat. Không được tuyên bố hai môi trường "giống hệt" chỉ vì cùng trả HTTP 200.

## 2. Hai con đường khởi động, hai bộ trách nhiệm

### 2.1 Chạy độc lập bằng Spring Boot launcher

Khi gọi:

```bash
java -jar dual-mode-0.0.1-SNAPSHOT.war --server.port=18080
```

JVM đọc `META-INF/MANIFEST.MF` để xác định `Main-Class`, thường là `org.springframework.boot.loader.launch.WarLauncher` trong Spring Boot 3.3. Launcher nạp ứng dụng và nested libraries. `Start-Class` của Boot chỉ tới lớp `DualModeApplication` có `main(String[])`.

`SpringApplication.run(...)` tạo ApplicationContext và embedded servlet container, ở đây là Tomcat. Thư viện Tomcat có trong `WEB-INF/lib-provided` của executable WAR vẫn có thể phục vụ chế độ **embedded** qua Boot launcher. Cổng HTTP chịu ảnh hưởng của `server.port`, trong ví dụ là **18080** để tránh xung đột với Tomcat ngoài ở cổng 8080.

Khi chạy bằng `java -jar`, không cần một Tomcat cài riêng nếu archive đã mang đủ dependency, JDK và môi trường phù hợp. Nhưng **JDK bắt buộc có sẵn** hoặc phải được cung cấp bởi image/runtime.

### 2.2 Deploy vào external servlet container

Khi Tomcat ngoài triển khai một WAR:

1. Tomcat tạo **ServletContext** cho ứng dụng theo context path.
2. Container coi `WEB-INF/classes` và các thư viện hợp lệ trong `WEB-INF/lib` là webapp classpath.
3. Spring Framework phát hiện `WebApplicationInitializer`; `SpringBootServletInitializer` là cầu nối để dựng Spring context trong Servlet container ngoài.
4. Tomcat dùng connector/port của **chính nó**; ứng dụng không sở hữu embedded Tomcat thứ hai.
5. Các thư viện nằm trong `WEB-INF/lib-provided` là phần **chỉ dành cho launcher embedded**, không phải tập thư viện thông thường mà external Tomcat nạp từ `WEB-INF/lib`.

**Điểm đối lập:**

| Thành phần | `java -jar app.war` | Deploy `app.war` vào Tomcat ngoài |
| --- | --- | --- |
| Ai khởi động? | JVM → Boot `WarLauncher` → `main` | Tomcat ngoài → Servlet initialization → `SpringBootServletInitializer` |
| Servlet container | Embedded Tomcat trong runtime của WAR | Tomcat được cài/quản trị riêng |
| Cổng HTTP | `server.port`, ví dụ 18080 | Tomcat connector (ví dụ 8080); `server.port` trong app không chọn connector đó |
| Context path mặc định trong bài | Chuỗi rỗng `""` | Theo tên WAR đã triển khai, ví dụ `/dual-mode` |
| App classes | `WEB-INF/classes` do Boot loader nạp | `WEB-INF/classes` do webapp classloader nạp |
| Application libraries | `WEB-INF/lib` | `WEB-INF/lib` |
| Provided embedded server libraries | `WEB-INF/lib-provided` dùng được bởi Boot launcher | Không được nạp như thư viện webapp chuẩn |
| Entrypoint | `main(String[])` | `configure(SpringApplicationBuilder)` |
| Vòng đời khởi động/dừng | Process JVM quản lý | Servlet container quản lý deploy/redeploy/undeploy |
| Khi có nhiều webapp | Một JVM Boot app độc lập | Một Tomcat có thể phục vụ nhiều WAR với context/classloader riêng |

Không nên viết hai bộ cấu hình business logic khác nhau để "làm cho hai chế độ chạy". Hãy giữ cùng một ứng dụng Spring; nếu cần custom `SpringApplicationBuilder` phức tạp, chia logic custom thành method được gọi từ **cả `main` và `configure`** thay vì chỉ chỉnh một nhánh.

## 3. Tạo ứng dụng Spring Boot Servlet dùng cho cả hai chế độ

Ví dụ sử dụng cấu trúc:

```text
dual-mode/
├── pom.xml                 # Chọn Maven
│   hoặc build.gradle       # Chọn Gradle Groovy DSL
├── settings.gradle         # Chỉ nếu chọn Gradle
├── mvnw / mvnw.cmd         # Maven Wrapper, khi dự án có Maven
├── gradlew / gradlew.bat   # Gradle Wrapper, khi dự án có Gradle
└── src/
    ├── main/
    │   ├── java/com/example/dualmode/
    │   │   ├── DualModeApplication.java
    │   │   └── ProbeController.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/dualmode/ProbeIntegrationTest.java
```

Dự án thực tế chỉ cần **một hệ build**; sơ đồ liệt kê hai lựa chọn, không yêu cầu dùng Maven và Gradle đồng thời.

### 3.1 Lớp ứng dụng kiêm Servlet initializer

File `src/main/java/com/example/dualmode/DualModeApplication.java`:

```java
package com.example.dualmode;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class DualModeApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder builder) {
        return builder.sources(DualModeApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(DualModeApplication.class, args);
    }
}
```

Đây là lớp Java **hoàn chỉnh trong một project Spring Boot với các dependency phù hợp** và Java 17+, **không chạy bằng một lệnh `javac` trần** vì Spring Boot classes phải có trên classpath. Java package và đường dẫn file khớp nhau.

- `@SpringBootApplication` đánh dấu root configuration và component scanning ở package `com.example.dualmode`.
- `main` dùng cho executable WAR `java -jar` hoặc chạy phát triển `spring-boot:run`/`bootRun`.
- `SpringBootServletInitializer` và `configure(...)` dùng khi servlet container ngoài khởi tạo ứng dụng từ WAR. `builder.sources(...)` chỉ định đúng lớp cấu hình gốc.
- Không cần `web.xml` truyền thống cho ứng dụng Spring Boot MVC đơn giản này; Spring Framework Servlet initialization xử lý đăng ký cần thiết.
- Nếu bỏ `extends SpringBootServletInitializer` hoặc không cung cấp con đường khởi tạo Servlet thích hợp, `java -jar` có thể vẫn hoạt động nhưng deployment vào external container có thể chỉ hiện 404 hoặc không tạo ApplicationContext.

### 3.2 Controller dùng để chứng minh context path

File `src/main/java/com/example/dualmode/ProbeController.java`:

```java
package com.example.dualmode;

import jakarta.servlet.ServletContext;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {

    private final ServletContext servletContext;

    public ProbeController(ServletContext servletContext) {
        this.servletContext = servletContext;
    }

    @GetMapping(value = "/probe", produces = MediaType.TEXT_PLAIN_VALUE)
    public String probe() {
        return "READY|context=" + servletContext.getContextPath();
    }
}
```

Lớp này trả một chuỗi cố định cộng với **context path do Servlet container thực sự gán cho ứng dụng**. `ServletContext#getContextPath()` cho phép **đo** sự khác nhau giữa hai chế độ mà không cần cấu hình cờ giả định `mode=standalone` hay `mode=external`.

Trong đúng ví dụ:

- Embedded Tomcat khởi động với root context (không cấu hình `server.servlet.context-path`) → response body `READY|context=`.
- Tomcat ngoài nhận bản copy WAR tên `dual-mode.war`, triển khai ở context path `/dual-mode` nếu không có context descriptor/custom mapping ghi đè → response body `READY|context=/dual-mode`.

Đừng dùng response khác biệt để kết luận byte ứng dụng khác nhau. Trong ví dụ, controller **cùng class** chạy với hai ServletContexts khác nhau.

### 3.3 Cấu hình ứng dụng không tự quyết định port của container ngoài

File `src/main/resources/application.properties`:

```properties
spring.application.name=dual-mode
```

Cố ý **không ghi** `server.port` và `server.servlet.context-path` vào file chung. Khi thử độc lập, truyền port qua command line; khi chạy ngoài, để Tomcat cấu hình port/context. Giữ file dùng chung giúp thí nghiệm dễ phân biệt hạ tầng và logic ứng dụng.

Nếu cần cùng profile ở hai môi trường, bạn phải chủ động cấu hình cả hai. Ví dụ `--spring.profiles.active=qa` khi chạy `java -jar` và `SPRING_PROFILES_ACTIVE=qa` hoặc cấu hình tương ứng trong Tomcat khi triển khai ngoài. **Profile giống nhau chưa chắc môi trường giống nhau**: biến môi trường, secrets, Java version, Tomcat version, files và timezone vẫn có thể khác.

### 3.4 Kiểm thử ứng dụng bằng embedded server trong test

File `src/test/java/com/example/dualmode/ProbeIntegrationTest.java`:

```java
package com.example.dualmode;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ProbeIntegrationTest {

    @Autowired
    private TestRestTemplate rest;

    @Test
    void returnsRootContextInEmbeddedMode() {
        String body = rest.getForObject("/probe", String.class);
        assertThat(body).isEqualTo("READY|context=");
    }
}
```

Test dùng embedded web environment **mở random port** nên tránh va chạm cổng 8080. Nó xác nhận phần controller + ServletContext + Spring context chạy được trong chế độ nhúng; **không chứng minh bản WAR đã deploy vào Tomcat ngoài**. Phần external deployment vẫn phải được kiểm thử riêng sau khi tạo WAR.

Test này cần `spring-boot-starter-test` và bộ servlet runtime trên test classpath. Với Gradle, `providedRuntime` giữ server libraries trong runtime/test phù hợp; `compileOnly` không tương đương.

## 4. Maven: cấu hình tạo WAR vừa executable vừa deployable

### 4.1 POM có thể dùng cho ứng dụng ví dụ

Tệp `pom.xml`:

```xml
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

    <groupId>com.example</groupId>
    <artifactId>dual-mode</artifactId>
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
```

Đây là **POM hoàn chỉnh** cho phần build của ứng dụng hai lớp + test trong ví dụ, với Maven Wrapper được chuẩn bị sẵn hoặc Maven tương thích. Bạn cần có mã `src/...` như phần 3 và mạng/kho Maven để tải dependency. Không giả định dự án có Wrapper nếu chưa tạo `mvnw`/`mvnw.cmd`; nếu chưa có, dùng Maven cài sẵn hoặc tạo Wrapper có kiểm chứng.

**Ý nghĩa:**

1. `<packaging>war</packaging>` yêu cầu Maven WAR packaging.
2. `spring-boot-starter-web` cung cấp Spring MVC và những thư viện ứng dụng dùng ở cả hai chế độ.
3. `spring-boot-starter-tomcat` với `<scope>provided</scope>` biểu thị Servlet container sẽ cung cấp server runtime khi deployment bên ngoài.
4. `spring-boot-starter-parent` cấu hình `spring-boot-maven-plugin` goal `repackage` khi plugin được khai báo. Nếu chỉ **import BOM** mà không dùng parent, phải cấu hình execution `repackage` riêng.
5. Spring Boot Maven `repackage` tạo **executable WAR** và đặt các provided dependencies trong `WEB-INF/lib-provided`. Do đó Tomcat embedded vẫn dùng được lúc `java -jar`.
6. `spring-boot-starter-test` chỉ dành cho test; không cần trong executable WAR runtime.

Maven `provided` có hai tầng nghĩa cần tách biệt: Maven core không coi nó là dependency **runtime classpath thông thường**, nhưng Spring Boot `repackage` vẫn **đóng provided dependencies vào executable WAR dưới `WEB-INF/lib-provided`**. Đó là hành vi có chủ đích, không phải lỗi mà người học nên "sửa" bằng cách loại Tomcat khỏi mọi phần WAR.

### 4.2 Build bằng Maven

```bash
# Trong thư mục dự án có pom.xml và mvnw:
./mvnw clean verify

# Có thể dùng package nếu không cần chạy toàn bộ verify-phase checks:
./mvnw clean package

# Xem dependency Tomcat và phạm vi của nó:
./mvnw dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-tomcat

# Xem mô hình POM sau khi kế thừa parent/plugin config:
./mvnw help:effective-pom -Doutput=effective-pom.xml
```

**Lưu ý để thí nghiệm "cùng một WAR" chính xác:** chỉ dùng **một lần build cuối cùng** cho cả hai đường chạy; các lệnh ở trên là lựa chọn xây dựng/điều tra, không phải yêu cầu lần lượt chạy `clean verify` rồi `clean package` rồi so hai file. Thực hiện test trước, build một lần, ghi SHA-256 file thành phẩm và **không rebuild cho đến khi kiểm tra xong cả hai chế độ**.

File kỳ vọng trong cấu hình POM ở trên:

```text
target/dual-mode-0.0.1-SNAPSHOT.war              # executable Boot WAR
target/dual-mode-0.0.1-SNAPSHOT.war.original     # bản WAR trước repackage (có thể có)
```

`.war.original` là bản WAR thường được sao lưu khi Boot repackage **thay main artifact**, không phải WAR chính để chạy qua `java -jar`. Nếu plugin bị tùy biến classifier, file output có thể khác và không nhất thiết tạo `.original`. **Luôn kiểm tra file thật** thay vì chỉ dựa trên mẫu tên.

## 5. Gradle: `war` + Spring Boot `bootWar` + `providedRuntime`

### 5.1 Cấu hình Groovy DSL đầy đủ

`settings.gradle`:

```groovy
rootProject.name = 'dual-mode'
```

`build.gradle`:

```groovy
plugins {
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
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
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **cấu hình Gradle đủ cho project Java/Spring Boot của bài** (cùng mã trong phần 3), nếu có Gradle Wrapper tương thích và JDK 17. `war` Gradle plugin áp dụng Java plugin ngầm. Spring Boot plugin thấy `war` nên bổ sung task `bootWar`.

Vì sao dùng `providedRuntime` chứ không dùng `compileOnly` cho Tomcat?

- `providedRuntime` của Gradle War plugin mang dependency vào **runtime của phát triển/test**, nhưng **không đưa nó vào `WEB-INF/lib` của plain WAR** dành cho container ngoài.
- Spring Boot `bootWar` đưa các provided dependencies vào `WEB-INF/lib-provided`. Khi dùng Boot launcher bằng `java -jar`, embedded Tomcat vẫn sẵn.
- `compileOnly` chỉ phục vụ compile main; không tự có trong test runtime, không hỗ trợ hai cách chạy đúng nhu cầu của WAR. Nếu dùng `compileOnly` thay `providedRuntime`, test dạng random-port và executable WAR có thể thất bại vì thiếu server.

**Tính bắc cầu:** `providedRuntime`/`providedCompile` của Gradle War plugin có thể ảnh hưởng tới các dependency bắc cầu. Nếu một thư viện bị đánh dấu provided qua một nhánh mà cũng được kéo từ `implementation`, cần kiểm tra resolved graph và nội dung WAR thay vì khẳng định nó chắc chắn nằm trong `WEB-INF/lib`.

### 5.2 Nếu dùng Kotlin DSL

Đây là **trích đoạn `build.gradle.kts`** về những phần quan trọng, không phải toàn bộ file:

```kotlin
plugins {
    war
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    providedRuntime("org.springframework.boot:spring-boot-starter-tomcat")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
```

Với Kotlin DSL, cần thêm `group`, `version`, toolchain, repositories và `tasks.test` tương ứng. Không trộn cú pháp `providedRuntime '...'` của Groovy vào `build.gradle.kts`.

### 5.3 Lệnh build Gradle

```bash
./gradlew clean test bootWar

# Xem task khi cần:
./gradlew tasks --all

# Điều tra module Tomcat:
./gradlew dependencyInsight --dependency spring-boot-starter-tomcat \
  --configuration runtimeClasspath
```

Đường output mặc định theo tên/version ví dụ:

```text
build/libs/dual-mode-0.0.1-SNAPSHOT.war         # executable Boot WAR
build/libs/dual-mode-0.0.1-SNAPSHOT-plain.war   # WAR thường nếu task war cũng được chạy
```

**Phân biệt:** Gradle tạo `bootWar` và `war` bằng hai task khác nhau; Spring Boot dùng classifier `plain` theo convention cho WAR thường để hai task không ghi đè một tên file. Lệnh chỉ chạy `bootWar` có thể **không tạo** `-plain.war`. Trong pipeline deploy kép của bài, dùng **executable WAR do `bootWar` tạo**, không lấy một file bất kỳ khớp `*.war`.

## 6. Cấu trúc executable WAR phải kiểm tra trước khi chạy

Spring Boot executable WAR theo layout thông dụng:

```text
dual-mode-0.0.1-SNAPSHOT.war
├── META-INF/
│   └── MANIFEST.MF
├── WEB-INF/
│   ├── classes/
│   │   ├── com/example/dualmode/DualModeApplication.class
│   │   ├── com/example/dualmode/ProbeController.class
│   │   └── application.properties
│   ├── lib/
│   │   ├── spring-webmvc-...jar
│   │   ├── spring-context-...jar
│   │   └── ... các thư viện ứng dụng ...
│   └── lib-provided/
│       ├── tomcat-embed-core-...jar
│       └── ... servlet runtime được đánh dấu provided ...
└── org/springframework/boot/loader/
    └── ... WarLauncher ...
```

Đây là **cây minh họa**, tên phụ thuộc thật/manifest phụ thuộc phiên bản. Không coi các dòng `...` là file literal xuất hiện trong archive.

| Phần | Khi `java -jar` | Khi Tomcat ngoài deploy |
| --- | --- | --- |
| `WEB-INF/classes` | Class/resources của ứng dụng | Class/resources của webapp |
| `WEB-INF/lib` | Application dependency jars | Application dependency jars trong webapp classpath |
| `WEB-INF/lib-provided` | Cho phép Boot launcher dùng embedded servlet dependencies | Không nằm trong classpath `WEB-INF/lib` thông thường; tránh trùng container ngoài |
| `org/springframework/boot/loader` | Boot loader nạp và khởi động ứng dụng | Không phải Servlet application initializer của external Tomcat |
| `META-INF/MANIFEST.MF` | JVM dùng `Main-Class` | Tomcat không khởi động webapp qua `java -jar` |
| `SpringBootServletInitializer` class | Có thể tồn tại nhưng đường `main` được gọi | Được Servlet initialization sử dụng |

Không nhầm `BOOT-INF/*` của executable JAR với `WEB-INF/*` của WAR. Kiểm tra `BOOT-INF/lib` trên WAR sẽ báo thiếu dù file hoàn toàn hợp lệ.

### 6.1 Xác nhận bằng `jar tf`

Maven:

```bash
WAR="target/dual-mode-0.0.1-SNAPSHOT.war"
jar tf "$WAR"
```

Gradle:

```bash
WAR="build/libs/dual-mode-0.0.1-SNAPSHOT.war"
jar tf "$WAR"
```

Chọn **một** dòng `WAR=...` tùy hệ build. Sau đó xem những entry có liên quan:

```bash
jar tf "$WAR" | grep -E \
  '^(WEB-INF/classes/|WEB-INF/lib/|WEB-INF/lib-provided/|org/springframework/boot/loader/)'
```

Một executable WAR hợp lệ theo ví dụ cần có class trong `WEB-INF/classes` và Tomcat dependencies trong `WEB-INF/lib-provided`. Nếu chỉ thấy Tomcat trong `WEB-INF/lib`, cần kiểm tra scope `provided`/`providedRuntime`, transitivity và task đã tạo artifact.

### 6.2 Manifest: khác nhau giữa `Main-Class` và `Start-Class`

Dùng `unzip` trên macOS/Linux (nếu cài):

```bash
unzip -p "$WAR" META-INF/MANIFEST.MF
```

Với Spring Boot 3.3 executable WAR mẫu, **kỳ vọng** có dòng tương tự:

```text
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: com.example.dualmode.DualModeApplication
```

`Main-Class` dùng cho JVM/launcher; `Start-Class` chỉ tới ứng dụng. Không dùng `Start-Class` làm entrypoint trực tiếp của `java -jar`. Nếu plugin/loader version khác, tên `Main-Class` có thể khác; phải đọc manifest thật.

Chỉ có `Main-Class` chưa đủ chứng minh WAR chạy được: nó còn cần đúng runtime dependencies, class/application configuration, cổng rảnh và JDK tương thích. Tương tự, một WAR có cấu trúc web hợp lệ nhưng không có Boot launcher vẫn có thể deploy vào container ngoài, nhưng **không phải executable WAR** theo yêu cầu hai chế độ.

## 7. Quy trình kiểm chứng A – chạy độc lập với `java -jar`

Mục tiêu của bước A: chứng minh file WAR **tự khởi động embedded Tomcat** và endpoint trả nội dung mong đợi, trước khi giao chính file đó cho external Tomcat.

### 7.1 Build đúng một lần và cố định artifact

Giả sử chọn Maven:

```bash
./mvnw clean verify
WAR="target/dual-mode-0.0.1-SNAPSHOT.war"
test -f "$WAR"
jar tf "$WAR"
```

Nếu chọn Gradle:

```bash
./gradlew clean test bootWar
WAR="build/libs/dual-mode-0.0.1-SNAPSHOT.war"
test -f "$WAR"
jar tf "$WAR"
```

**Hai block là hai lựa chọn**, không chạy cả Maven lẫn Gradle để tạo "một file". Ở đây `test -f` là shell builtin kiểm tra file tồn tại, không phải Gradle/Maven `test`. Đường tên file phải thay nếu project đặt classifier `exec`, `boot`, `archiveFileName` hoặc `finalName` khác.

Ghi hash ban đầu:

```bash
sha256sum "$WAR"
```

Nếu macOS không có `sha256sum`, dùng `shasum -a 256 "$WAR"`. **Không sửa hoặc rebuild file** sau khi ghi hash. Nếu CI dùng Windows, phần 9 có lệnh PowerShell tương đương.

### 7.2 Khởi động executable WAR trên cổng 18080

Trong **terminal 1**:

```bash
java -jar "$WAR" --server.port=18080
```

Lệnh này thường chạy lâu và giữ terminal; banner/log khởi động phụ thuộc môi trường. Nếu lỗi `Address already in use`, dùng cổng rảnh khác và cập nhật URL kiểm tra. Nếu Java version không tương thích, ứng dụng có thể dừng trước khi bind port.

Khi log hoặc kiểm tra cổng xác nhận app sẵn sàng, mở **terminal 2**:

```bash
curl --fail --silent --show-error http://localhost:18080/probe
```

Response body mong đợi:

```text
READY|context=
```

Giải thích:

- `/probe` là `@GetMapping` trong `ProbeController`.
- Không đặt `server.servlet.context-path` nên `ServletContext#getContextPath()` trả chuỗi rỗng.
- `--server.port=18080` là argument được Spring Boot đọc khi khởi động **embedded** server.
- Body chính xác là một dòng ASCII không có newline do controller; cách `curl` hiển thị prompt/newline phụ thuộc terminal. **Đây không phải toàn bộ stdout của `java -jar`**.
- Test chạy `ProbeIntegrationTest` ở random port cũng chứng minh logic embedded tương tự, nhưng không thay thế việc chạy file WAR cuối.

Khi đã kiểm tra xong, **Ctrl+C** ở terminal 1 để dừng embedded application. Nếu muốn chạy đồng thời với Tomcat ngoài, vẫn được khi dùng **hai cổng khác nhau**, nhưng cho bài học tuần tự sẽ dễ thu thập log và loại trừ lỗi hơn.

### 7.3 Ghi lại bằng chứng độc lập

Nên lưu các thông tin, ví dụ:

```text
WAR path: target/dual-mode-0.0.1-SNAPSHOT.war
WAR SHA-256: (chuỗi thật do sha256sum in ra)
Launch command: java -jar ... --server.port=18080
HTTP URL: http://localhost:18080/probe
HTTP status: 200 nếu thành công
HTTP body: READY|context=
Server lifecycle: Started, rồi stopped sau khi test
```

Dấu ngoặc ở `SHA-256` là hướng dẫn người học điền **giá trị thực**, không phải digest giả. Không copy một hash từ mạng rồi coi đó là digest archive của máy mình.

## 8. Quy trình kiểm chứng B – deploy **chính file WAR đó** vào external Tomcat

Bước B dùng **bản copy của cùng WAR**, không chạy lại `package` hay `bootWar`. Đích ví dụ là **Apache Tomcat 10.1** cài sẵn. Bạn cần quyền ghi thư mục deploy và quyền chạy instance Tomcat thí nghiệm; không nên can thiệp Tomcat production để làm bài học.

### 8.1 Chuẩn bị external Tomcat đúng phiên bản

- Tomcat 10.1 hỗ trợ Jakarta Servlet 6.0, phù hợp với ứng dụng Spring Boot 3.3 dùng `jakarta.servlet`.
- Tomcat 9.x dựa trên `javax.servlet`; cố deploy trực tiếp Spring Boot 3.3 WAR vào đó thường gây lỗi API/khởi tạo. Đừng giải quyết bằng việc trộn `javax.servlet-api` và `jakarta.servlet-api` một cách ngẫu nhiên.
- Chạy Tomcat ngoài với **JDK tương thích** với bytecode ứng dụng, ở đây Java 17+.
- Tomcat ngoài có cổng connector HTTP, thường 8080 khi cấu hình mặc định. Thử kiểm tra cổng 8080 rảnh; nếu không, đổi Tomcat `conf/server.xml` tại **instance lab** thay vì đổi `server.port` trong file application.
- Tắt process hoặc deploy cũ có cùng context path để tránh Tomcat dùng phiên bản WAR khác trong thư mục đã giải nén/cached.
- Cấu hình `CATALINA_HOME` và, nếu dùng instance riêng, `CATALINA_BASE` cho đúng Tomcat. Không trộn lib của các Tomcat phiên bản khác.

### 8.2 Copy archive, không rebuild

Ví dụ **Bash/macOS/Linux**, với giả định bạn đã cấu hình biến môi trường `CATALINA_HOME` tới bản cài Tomcat 10.1 và `CATALINA_BASE` tới instance thí nghiệm (hoặc cùng đường dẫn với `CATALINA_HOME`). Sau bước 7, biến `WAR` vẫn tham chiếu file gốc:

```bash
# CATALINA_HOME và CATALINA_BASE được cấu hình từ trước.
test -f "$WAR"
test -d "$CATALINA_BASE/webapps"

# Dùng tên file dual-mode.war để Tomcat nhận context path /dual-mode.
cp "$WAR" "$CATALINA_BASE/webapps/dual-mode.war"

# Cùng byte => hai chuỗi SHA-256 phải trùng nhau.
sha256sum "$WAR" "$CATALINA_BASE/webapps/dual-mode.war"
```

Nếu hai digest **không giống nhau**, dừng thí nghiệm: có thể đã chọn nhầm artifact, bản copy bị thay đổi hoặc đường dẫn chỉ tới file khác. Không nói "cùng WAR" khi chưa xác định lý do. Nếu có symlink, auto-update hoặc pipeline copy không nguyên byte, cũng cần kiểm tra.

Bản copy được đặt tên `dual-mode.war` để nhận context path `/dual-mode` trong cách auto-deploy mặc định. **Đổi tên không thay nội dung ZIP**, nhưng Tomcat có thể dùng context path khác nếu có `context.xml`, host config, custom context descriptor hoặc `ROOT.war`.

### 8.3 Chạy Tomcat ngoài

Trong **terminal 3** (sau khi đã dừng ứng dụng embedded ở phần A nếu muốn tránh nhiễu):

```bash
"$CATALINA_HOME/bin/catalina.sh" run
```

Lệnh này chạy Tomcat foreground và in log vào terminal (đường lệnh có thể khác giữa bản cài/phân phối). Nếu Tomcat chạy như service hoặc trong container, dùng cách khởi động hợp lệ của môi trường đó; **không chạy hai Tomcat cùng một `CATALINA_BASE`**.

Quan sát Tomcat log đến khi nó hoàn thành deploy webapp; nếu có lỗi khởi tạo Spring, xem stacktrace (không chỉ nhìn dòng "Server startup"). Một Tomcat có thể khởi động thành công dù **riêng ứng dụng WAR deploy thất bại**.

Trong terminal khác:

```bash
curl --fail --silent --show-error http://localhost:8080/dual-mode/probe
```

Với Tomcat connector cổng **8080**, WAR copy tên `dual-mode.war` và không có context override, response body mong đợi:

```text
READY|context=/dual-mode
```

Nếu Tomcat dùng cổng khác, thay `8080`. Nếu WAR được triển khai tại root (ví dụ `ROOT.war`), URL có thể là `/probe` và context path có thể rỗng. Tránh diễn giải **404 tại `/probe`** trong Tomcat ngoài thành "ứng dụng hỏng" trước khi thử `/dual-mode/probe`.

### 8.4 Xác minh cùng artifact, không nhầm bản deploy

Cùng máy/container filesystem (trước/sau deploy khi file gốc và bản copy còn nguyên):

```bash
sha256sum "$WAR" "$CATALINA_BASE/webapps/dual-mode.war"
```

Nếu digest trùng, cả hai chế độ đang **được chỉ định dùng cùng byte archive**. Để tăng chắc chắn rằng Tomcat đã **nạp bản vừa copy**, đối chiếu deployment timestamp/logs, context path và dọn bản exploded/cache cũ trong môi trường lab khi có dấu hiệu stale deployment. Không xóa tùy tiện thư mục Tomcat đang phục vụ ứng dụng khác.

Đây là điểm phân biệt **artifact identity** với **runtime identity**:

- Artifact identity: SHA-256, nội dung classes và dependency của WAR.
- Runtime identity: Java/Tomcat version, port, JVM flags, profile, environment, secrets, database, native libraries, network, classloader và app server config.

Cùng WAR có thể hoạt động ở cả hai chế độ nhưng cho giá trị cấu hình/hiệu năng/log khác nhau. Bài học yêu cầu **kiểm chứng cùng WAR hoạt động**, không khẳng định mọi hành vi giữa hai môi trường tương đương tuyệt đối.

### 8.5 Đừng dùng kết quả `java -jar` thay cho external deploy test

Một WAR có thể chạy trực tiếp mà external Tomcat báo 404 hoặc lỗi startup do:

- Thiếu `SpringBootServletInitializer`.
- Servlet container ngoài không đúng phiên bản Jakarta Servlet/JDK.
- Wrong context path/host mapping.
- Trùng Servlet API/Tomcat jars trong `WEB-INF/lib`.
- Custom listener/filter hay application initialization không tương thích lifecycle ngoài.
- Spring profile/config/secret bên ngoài khác.
- WAR chạy file tên đúng nhưng Tomcat đã deploy bản cũ hoặc một context khác.

Ngược lại, một WAR thường có thể deploy vào Tomcat nhưng không chạy bằng `java -jar` vì không có Spring Boot launcher và `lib-provided`. Muốn chứng minh "hai chế độ", phải **thử cả hai**.

## 9. Windows PowerShell: kiểm thử từng chế độ và hash

Nếu bạn sử dụng Windows, cần Java 17+, Maven/Gradle Wrapper và Tomcat 10.1 cho lab. Các lệnh dưới đây giả sử bạn đã biết **đường WAR thật**; chọn một hệ build.

### 9.1 Build và chạy độc lập

Maven:

```powershell
.\mvnw.cmd clean verify
$war = "target\dual-mode-0.0.1-SNAPSHOT.war"
Get-FileHash -Algorithm SHA256 -LiteralPath $war
java -jar $war --server.port=18080
```

Gradle (một lựa chọn thay Maven, không chạy cả hai):

```powershell
.\gradlew.bat clean test bootWar
$war = "build\libs\dual-mode-0.0.1-SNAPSHOT.war"
Get-FileHash -Algorithm SHA256 -LiteralPath $war
java -jar $war --server.port=18080
```

Khi app đã sẵn sàng, mở **PowerShell khác**:

```powershell
(Invoke-WebRequest -Uri "http://localhost:18080/probe").Content
```

Kết quả kỳ vọng ở ví dụ là `READY|context=`; `Invoke-WebRequest` có thể kèm định dạng kết quả khác khi không lấy `.Content`, nên chọn rõ thuộc tính `Content`. Dừng ứng dụng standalone trước khi deploy nếu muốn thí nghiệm tuần tự.

### 9.2 Copy vào Tomcat ngoài, so hash và gọi URL mới

Giả định `$env:CATALINA_BASE` và `$env:CATALINA_HOME` đã trỏ đến Tomcat lab:

```powershell
$target = Join-Path $env:CATALINA_BASE "webapps\dual-mode.war"

Copy-Item -LiteralPath $war -Destination $target

Get-FileHash -Algorithm SHA256 -LiteralPath $war
Get-FileHash -Algorithm SHA256 -LiteralPath $target

& (Join-Path $env:CATALINA_HOME "bin\catalina.bat") run
```

Trong terminal khác, sau khi deployment kết thúc:

```powershell
(Invoke-WebRequest -Uri "http://localhost:8080/dual-mode/probe").Content
```

Kết quả kỳ vọng theo cách deploy mặc định: `READY|context=/dual-mode`. Nếu `CATALINA_HOME` chưa được cấu hình hoặc ứng dụng chạy như Windows service, dùng cách khởi động service đã được phép; không đoán đường cài Tomcat.

**Cẩn trọng thao tác:** không dùng `Copy-Item -Force` vào WAR đang được process production quản lý chỉ để thử; nên có instance lab riêng và deployment window. Với một process Tomcat thực đang chạy, cập nhật file trực tiếp có thể kích hoạt redeploy ngoài ý muốn.

## 10. Kiểm thử tự động: lớp unit/integration khác smoke test WAR

### 10.1 Các tầng kiểm thử cần phân biệt

| Loại kiểm tra | Điều nó chứng minh | Điều nó chưa chứng minh |
| --- | --- | --- |
| Java compile | `DualModeApplication`/controller hợp lệ với dependencies | WAR đóng gói đủ runtime |
| `@SpringBootTest` RANDOM_PORT | Embedded Spring/Tomcat chạy, HTTP logic đúng | Cùng executable WAR deploy ngoài được |
| `mvn package` / Gradle `bootWar` | Archive đã được tạo thành công | Archive tự chạy hoặc external deploy hoạt động |
| `jar tf`/manifest/layout | File có class và thư viện ở đúng thư mục dự kiến | Không có runtime lỗi cấu hình, port, profile |
| `java -jar` + `curl` | Executable WAR khởi động và endpoint OK trong môi trường nhúng | Servlet container ngoài cũng khởi động được |
| Tomcat deploy + `curl` | External container khởi tạo ứng dụng và endpoint OK | Cùng byte WAR nếu chưa so hash |
| SHA-256 hai file bằng nhau | Byte archive nguồn/bản copy giống nhau tại lúc kiểm tra | Hai môi trường runtime/config tương đương |

**Một kiểm thử đủ cho bài:** test HTTP ở cả hai chế độ + cùng digest WAR. Với môi trường production, còn cần security/integration/observability/reliability tests theo yêu cầu hệ thống.

### 10.2 Bash gate kiểm tra executable WAR trước deploy

Đây là **script hoàn chỉnh trong Bash** để kiểm tra cấu trúc file WAR ví dụ **Spring Boot 3.3 + Tomcat provided**. Nó không triển khai Tomcat tự động và không chạy kiểm thử HTTP; làm như vậy để tránh script tác động server ngoài mà không có môi trường lab.

```bash
#!/usr/bin/env bash
set -euo pipefail

artifact="target/dual-mode-0.0.1-SNAPSHOT.war"
if [[ ! -f "$artifact" ]]; then
    echo "FAIL: WAR artifact missing"
    exit 1
fi

entries="$(jar tf "$artifact")"

if ! grep -Fxq 'WEB-INF/classes/com/example/dualmode/DualModeApplication.class' <<< "$entries"; then
    echo "FAIL: application class missing"
    exit 1
fi

if ! grep -Fxq 'WEB-INF/classes/com/example/dualmode/ProbeController.class' <<< "$entries"; then
    echo "FAIL: controller class missing"
    exit 1
fi

if ! grep -Eq '^WEB-INF/lib-provided/tomcat-embed-core-[^/]+[.]jar$' <<< "$entries"; then
    echo "FAIL: embedded Tomcat missing from lib-provided"
    exit 1
fi

if grep -Eq '^WEB-INF/lib/tomcat-embed-core-[^/]+[.]jar$' <<< "$entries"; then
    echo "FAIL: embedded Tomcat wrongly included in WEB-INF/lib"
    exit 1
fi

if ! grep -Fq 'org/springframework/boot/loader/launch/WarLauncher.class' <<< "$entries"; then
    echo "FAIL: Spring Boot WarLauncher missing"
    exit 1
fi

echo "PASS: executable WAR layout verified"
```

Lệnh cần được sửa `artifact=...` thành `build/libs/...war` nếu dự án dùng Gradle. Với archive **đúng cấu hình ví dụ**, script in:

```text
PASS: executable WAR layout verified
```

Đây là stdout **có điều kiện** của script khi mọi assertion qua, không phải output đã được chạy trên dự án thật. Nó không kiểm tra manifest/start-class, HTTP hoặc SHA-256 và không phù hợp nếu project cố ý dùng servlet runtime khác Tomcat. Khi dùng Jetty/Undertow hay Boot loader layout khác, thay rule để phản ánh **chính sách**.

### 10.3 Một kịch bản CI có thể lặp lại

Kịch bản hợp lý với một pipeline đã chuẩn bị Tomcat lab:

1. Checkout mã và dùng Wrapper được kiểm soát.
2. Chạy unit/integration tests (bao gồm `ProbeIntegrationTest`).
3. Build **một executable WAR** bằng `package`/`bootWar`.
4. Kiểm tra `jar tf`, manifest, provided runtime và hash WAR.
5. Chạy chính WAR qua `java -jar` trên cổng thí nghiệm; đợi app ready rồi gọi `GET /probe`, assert response.
6. Dừng standalone instance; copy WAR vào Tomcat lab, so lại SHA-256.
7. Chờ Tomcat xác nhận context được deploy, gọi `GET /dual-mode/probe` và assert response.
8. Thu log/hashes/HTTP status cho cả hai, dừng undeploy và dọn tài nguyên lab có chủ đích.
9. Chỉ promote **artifact đã được kiểm tra**, không rebuild ở stage khác mà bỏ qua gate.

Dùng riêng `-plain.war`/`.war.original` hoặc deploy một bản WAR vừa rebuild sẽ làm mất luận điểm "cùng WAR". Nếu build không có reproducible archive và đầu vào timestamp động, rebuild có thể cho digest khác ngay cả khi mã không đổi; vì vậy **copy đúng một file** là cách kiểm chứng trực tiếp nhất.

### 10.4 Đừng giả định "đợi 5 giây" nghĩa Tomcat đã sẵn sàng

Startup time phụ thuộc máy, dữ liệu, mạng, schema và deployment. Một script CI nên **poll HTTP với giới hạn thời gian**, kiểm tra log khi timeout, và dừng process nếu thất bại. Ví dụ lệnh probe không làm thay đổi hệ thống:

```bash
curl --fail --silent --show-error \
     --connect-timeout 3 --max-time 10 \
     http://localhost:8080/dual-mode/probe
```

Nếu HTTP trả 200 và body đúng, mới coi endpoint đó hoạt động. Nếu 404, kiểm tra context path và deployment logs; nếu 503/500, kiểm tra stacktrace/Spring context. Một container "đang chạy" không đồng nghĩa mọi webapp bên trong đều đã sẵn sàng.

## 11. Context path: nguồn nhầm lẫn phổ biến nhất

### 11.1 Một endpoint, hai URL

Với một controller mapping `/probe`:

| Yếu tố | Standalone embedded | External Tomcat |
| --- | --- | --- |
| File chạy | `dual-mode-0.0.1-SNAPSHOT.war` | Bản copy cùng byte đặt tên `dual-mode.war` |
| Cổng | `18080` theo `--server.port` | `8080` theo Tomcat `server.xml` mặc định của lab |
| Context path | Root `""` | `/dual-mode` theo tên WAR |
| Controller mapping | `/probe` | `/probe` |
| Full URL | `http://localhost:18080/probe` | `http://localhost:8080/dual-mode/probe` |
| Response body kỳ vọng | `READY|context=` | `READY|context=/dual-mode` |

**Không thêm `/dual-mode` vào `@GetMapping` chỉ để chạy trên external Tomcat.** Mapping trong controller là đường **bên trong context**; container prefix được quản lý độc lập.

### 11.2 `ROOT.war` và context descriptor

Nếu đặt WAR thành `ROOT.war` theo quy tắc auto-deploy Tomcat mặc định, context path có thể là chuỗi rỗng, và URL external có thể thành `http://localhost:8080/probe`. Khi đó cả hai chế độ có body `READY|context=` nếu cùng root context, nhưng vẫn là hai cơ chế khởi động khác nhau.

Tomcat cho phép context mapping qua host configuration và context descriptor. Nếu đã dùng custom mapping, tên WAR không còn đủ để suy ra path; hãy đọc cấu hình/manager/logs thực tế thay vì đoán từ file name.

### 11.3 `server.servlet.context-path` không phải thay thế luôn Tomcat context

Trong chế độ embedded, `server.servlet.context-path=/api` có thể làm app chạy với context path `/api`. Trong external Tomcat, webapp context được container quản lý khi deploy. Đừng dựa vào việc sửa `server.servlet.context-path` trong `application.properties` để thay thế thao tác cấu hình external Tomcat ở mọi môi trường. Nếu muốn đổi URL khi deploy ngoài, cấu hình **context path của container/host** cho đúng.

### 11.4 Proxy và đường dẫn công khai

Khi ứng dụng đứng sau Nginx, load balancer hoặc ingress, đường dẫn public có thể còn có prefix khác; header `Forwarded`/`X-Forwarded-*` cũng tác động cách ứng dụng xây URL tuyệt đối. `ServletContext#getContextPath()` vẫn thể hiện **context của webapp bên trong container**, không luôn là prefix public mà người dùng cuối thấy. Đây là lý do probe của bài tập minh họa cơ chế container, không phải toàn bộ routing ở production.

## 12. Kiểm tra classpath: tránh trùng Tomcat và Servlet API

### 12.1 Hai thư mục library có ý nghĩa khác nhau

Một executable WAR nên đưa library ứng dụng vào `WEB-INF/lib` và embedded Tomcat vào `WEB-INF/lib-provided`. Với external container, các thư viện Tomcat bên ngoài đã cung cấp, nên không cần để Tomcat embedded trong `WEB-INF/lib`; làm vậy có thể gây xung đột classloader.

Ví dụ các đường dẫn **minh họa**:

```text
WEB-INF/lib/spring-webmvc-6.x.jar
WEB-INF/lib/jackson-databind-2.x.jar
WEB-INF/lib-provided/tomcat-embed-core-10.1.x.jar
WEB-INF/lib-provided/tomcat-embed-websocket-10.1.x.jar
```

`6.x`/`2.x`/`10.1.x` chỉ là nhãn minh họa dòng phiên bản, không phải tên file chính xác. Hãy đọc tên thực và phiên bản từ `jar tf` hoặc dependency graph.

### 12.2 Maven và Gradle giải quyết "provided" theo cách nào?

Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
```

Gradle:

```groovy
dependencies {
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
```

Hai cấu hình này phục vụ cùng mục đích bài học nhưng không phải cú pháp hoặc semantics hoàn toàn giống ở mọi classpath. Maven core `provided` không nằm trong ordinary runtime dependency classpath, còn Boot repackage có xử lý thêm. Gradle War plugin `providedRuntime` có mặt trên classpath phù hợp cho runtime/test nhưng không được đóng vào plain WAR như application dependency; Boot `bootWar` đặt nó vào `lib-provided`.

**Không dùng Gradle `compileOnly` thay `providedRuntime` cho Tomcat trong bài**, vì runtime của web integration test có thể thiếu container. **Không dùng Maven `runtime` thay `provided`** nếu đích là WAR deploy lên external Tomcat, vì có nguy cơ đưa thư viện embedded server vào `WEB-INF/lib`.

### 12.3 Tại sao test nhanh ở local chưa phát hiện mọi xung đột?

Một ứng dụng có thể chạy độc lập thành công nhờ Boot launcher chọn đúng lib trong `lib-provided`, nhưng deploy ngoài thất bại do:

- External Tomcat version/Servlet API không tương thích.
- Trộn `jakarta.servlet` và `javax.servlet`.
- Một JAR ở `WEB-INF/lib` đóng lớp server riêng khiến parent-first/delegation gặp conflict.
- Custom servlet/filter/listener config phụ thuộc embedded server lifecycle.
- Một thư viện cần thiết cho ứng dụng đã bị đánh dấu provided dù container ngoài **không cung cấp**.
- Classpath của server có library chung không tương thích với library của ứng dụng.

**Bài học thực tế:** đã thấy `java -jar` PASS cũng phải kiểm tra deploy ngoài bằng Tomcat/version thật. Ngược lại, deploy WAR OK chưa đủ chứng minh WAR có Boot launcher và `java -jar` sẽ hoạt động.

## 13. Phân biệt WAR thường, Boot executable WAR và JAR

| Loại file | Ai tạo? | Có `WEB-INF`? | Có Boot launcher? | Chạy `java -jar` mặc định? |
| --- | --- | --- | --- | --- |
| Plain WAR Gradle `war` | Gradle War task | Có | Không theo mặc định | Không phải mục đích của plain WAR |
| Plain WAR Maven trước repackage | Maven WAR Plugin | Có | Không theo mặc định | Không phải mục đích |
| Boot executable WAR | Gradle `bootWar` hoặc Maven `repackage` trên WAR | Có | Có | Có, nếu app/runtime hợp lệ |
| Boot executable JAR | Gradle `bootJar` hoặc Maven repackage trên JAR | Thường dùng `BOOT-INF`, không phải WAR layout | Có | Có |
| Plain JAR | Gradle `jar` hoặc Maven Jar Plugin | Không theo WAR layout | Không theo mặc định | Chỉ nếu manifest/classpath được cấu hình phù hợp |

Với Gradle Boot 3.3, task `war` có convention classifier `plain` khi `bootWar` được cấu hình, nên có thể có:

```text
build/libs/dual-mode-0.0.1-SNAPSHOT.war        # Boot executable
build/libs/dual-mode-0.0.1-SNAPSHOT-plain.war  # plain
```

Với Maven repackage mặc định:

```text
target/dual-mode-0.0.1-SNAPSHOT.war            # Boot executable
target/dual-mode-0.0.1-SNAPSHOT.war.original   # WAR trước repackage
```

Đừng chọn artifact bằng wildcard `*.war` khi có nhiều loại, cũng đừng lấy `.war.original` rồi mong có `WarLauncher`. Trong bài kiểm chứng "cùng WAR", **artifact phải được nhận dạng một lần và giữ nguyên**.

## 14. Những khác biệt cấu hình runtime cần xem sau khi HTTP đã PASS

### 14.1 Port, context, hostname

Embedded Spring Boot có thể điều khiển `server.port`/`server.address` và `server.servlet.context-path`. External Tomcat có connector và context mapping riêng. Khi đối chiếu:

- Port do **ai sở hữu**, app hay container?
- Context path lấy từ `server.servlet.context-path` (embedded) hay WAR deployment descriptor/tên WAR (external)?
- HTTP request thực sự tới hostname/port nào? DNS/proxy có thay đổi đường đi không?
- Nếu dùng HTTPS, TLS termination ở Boot container hay reverse proxy/Tomcat connector?

### 14.2 Profile và externalized configuration

WAR giống nhau không bắt buộc dùng cùng cấu hình. Một environment có thể cấp biến `SPRING_PROFILES_ACTIVE`, database URL, secret, logging config và Java system properties khác. Nếu hai endpoint có logic khác, đừng vội kết luận cơ chế executable/external không tương thích: trước hết so input runtime.

**Nguyên tắc kiểm chứng tốt:** chọn endpoint `/probe` tối giản không phụ thuộc database/secret; sau khi chứng minh khởi động hai chế độ, mới thêm integration tests với dịch vụ ngoài. Nhờ vậy lỗi cơ chế WAR không bị lẫn với lỗi kết nối môi trường.

### 14.3 App lifecycle và thread handling

Độc lập: dừng JVM sẽ dừng embedded server. Ngoài: Tomcat quản lý deploy, undeploy và có thể tái khởi động/reload webapp mà process Tomcat vẫn sống. Vì vậy đối với thread, scheduler, connection pool và cleanup của ứng dụng, cần kiểm tra graceful shutdown và resource release khi undeploy, không chỉ khi kill JVM.

### 14.4 Logging và classloader

Standalone Boot launcher và external Tomcat dùng cơ chế classloader khác nhau. Tomcat còn có server logs riêng và có thể có logging configuration/shared libraries khác. Đừng suy ra "WAR deploy hỏng" chỉ vì không thấy Spring log trên stdout của Tomcat; xem logs của instance và webapp. Đồng thời, tránh đặt những library mang tính container (như servlet engine implementation) vào `WEB-INF/lib` khiến classloading bị xung đột.

## 15. Chẩn đoán lỗi theo dấu hiệu, không đoán nguyên nhân

| Hiện tượng | Khả năng cần kiểm tra | Bước xác minh |
| --- | --- | --- |
| `java -jar app.war` báo `no main manifest attribute` | Dùng plain WAR hoặc Maven chưa chạy repackage | `unzip -p app.war META-INF/MANIFEST.MF`, kiểm tra task/goal |
| `java -jar` không thấy main class | `Start-Class` sai, class bị đóng sai hoặc không có `main` | Kiểm tra class trong `WEB-INF/classes` và manifest |
| Embedded run báo thiếu Tomcat classes | `providedRuntime`/provided thiếu hoặc custom packaging làm mất `lib-provided` | `jar tf`, dependency report, task `bootWar` |
| Embedded run `Address already in use` | Cổng 18080/8080 đã được dùng | Đổi `--server.port` cho embedded; kiểm tra process đang bind |
| Tomcat ngoài start OK nhưng URL trả 404 | Sai context path, app deploy fail, initializer không được gọi hoặc controller không được scan | Test `/dual-mode/probe`, logs deploy và class `SpringBootServletInitializer` |
| Tomcat ngoài lỗi `javax.servlet` / `jakarta.servlet` | Tomcat 9 cũ hoặc API bị trộn | Dùng container phù hợp Jakarta Servlet với Boot 3.3, kiểm tra JAR |
| Tomcat ngoài lỗi NoClassDefFoundError | Thư viện app bị khai báo provided dù container ngoài không cấp | Kiểm tra `WEB-INF/lib` và dependency graph |
| Tomcat ngoài có lỗi duplicate Servlet/Tomcat classes | Embedded server library nằm sai `WEB-INF/lib` | Kiểm tra `WEB-INF/lib-provided` và Maven/Gradle provided |
| WAR chạy `java -jar` OK nhưng external deploy FAIL | Container/JDK/initializer/classpath hoặc app config khác | So runtime input, logs Tomcat, Servlet compatibility |
| External deploy OK nhưng `java -jar` FAIL | Chỉ là plain WAR hoặc thiếu Boot loader/lib-provided | Kiểm tra executable WAR layout, task tạo file |
| `/probe` có body `READY|context=` ở cả hai | External deploy ở root path hoặc context mapping không phải như dự đoán | Kiểm tra tên WAR, ROOT, context descriptor, Tomcat manager |
| External `/probe` 404 nhưng `/dual-mode/probe` OK | Context prefix bị bỏ qua trong URL đầu tiên | Giữ controller mapping `/probe`, dùng URL có context |
| SHA-256 giữa hai bản khác nhau | Copy sai file, WAR bị đổi, rebuild không chủ ý | Dừng, chọn lại artifact nguồn, copy nguyên byte và hash lại |
| Tomcat log báo webapp đã deploy nhưng endpoint vẫn không chạy | Có thể servlet context không khởi tạo hoặc mapping/security lỗi | Đọc startup Spring logs và HTTP 404/401/500 cụ thể |
| Test `@SpringBootTest` PASS nhưng deploy FAIL | Test chỉ kiểm tra embedded runtime | Bổ sung external Tomcat smoke test |
| CI đã kiểm tra WAR nhưng production vẫn chạy bản khác | Pipeline rebuild/copy hoặc deploy sai artifact | Gắn SHA-256 và kiểm tra artifact thực stage deploy |
| Gradle có `-plain.war` cùng file WAR chính | `war` và `bootWar` là hai task khác nhau | Chọn output của `bootWar` cho thí nghiệm hai chế độ |
| Maven có `.war.original` | Bản trước repackage được lưu lại | Chọn `.war` executable, không chọn `.original` |
| 404 chỉ xuất hiện sau reverse proxy | Proxy path rewrite hoặc header forwarding khác | Kiểm tra URL trực tiếp Tomcat trước, sau đó ingress/proxy |

### 15.1 Ba cấp "PASS" cần tách riêng

- **Build PASS:** WAR được tạo, không chứng minh chạy được.
- **Standalone PASS:** `java -jar` và `GET /probe` thành công, không chứng minh container ngoài hoạt động.
- **External PASS + byte identity:** Tomcat deploy WAR thành công, `GET /dual-mode/probe` thành công, hash WAR gốc và bản copy trùng. Khi có cả ba, bài đã chứng minh **một executable WAR tương thích với hai cơ chế** trong môi trường kiểm tra.

Nếu external deploy chạy nhưng dùng WAR khác hash, đó **không đạt tiêu chí cùng artifact**. Nếu hai hash giống nhưng app chưa khởi động hoặc HTTP trả 500, cũng chưa đạt. Kết luận phải kết hợp bằng chứng, không chỉ có một dòng log "Deployment completed".

## 16. Thực hành từng phần: từ file WAR đến kết luận có thể lặp lại

### Phần A – Dựng project

1. Chọn Maven **hoặc** Gradle; tạo project theo ví dụ `dual-mode`.
2. Thêm `DualModeApplication` kế thừa `SpringBootServletInitializer` và `ProbeController`.
3. Đặt đúng phiên bản Spring Boot 3.3.13, Java 17 và Web starter; kiểm tra build tool/JDK tương thích.
4. Đánh dấu embedded Tomcat là `provided` (Maven) hoặc `providedRuntime` (Gradle).
5. Thêm `ProbeIntegrationTest` và chạy test.
6. Trả lời: nếu bỏ `SpringBootServletInitializer` thì cơ chế nào còn chạy, cơ chế nào có thể hỏng? Nếu dùng `compileOnly` thay `providedRuntime`, điều gì đổi ở test runtime?

### Phần B – Đóng gói và mở file

1. Build **một executable WAR** và ghi lại đường dẫn chính xác.
2. Tính SHA-256, lưu kết quả và không chạy lại build giữa hai phép thử.
3. Liệt kê `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided` bằng `jar tf`.
4. Kiểm tra manifest cho `Main-Class` và `Start-Class`.
5. Giải thích vì sao Tomcat embedded nên có trong `WEB-INF/lib-provided` thay vì `WEB-INF/lib`.
6. Nếu có `-plain.war` hoặc `.war.original`, chỉ ra đúng file nào được dùng cho hai-mode test.

### Phần C – Chạy bằng `java -jar`

1. Chạy WAR gốc với `--server.port=18080`.
2. Gọi `http://localhost:18080/probe`.
3. Xác nhận status 200 và body `READY|context=` theo ví dụ.
4. Ghi log start/stop, JDK version và SHA-256 của WAR.
5. Dừng ứng dụng sau khi đã đo.

### Phần D – External Tomcat

1. Chuẩn bị Tomcat **10.1** lab, Java 17+, cổng HTTP riêng.
2. Copy **nguyên WAR** vào `webapps/dual-mode.war` khi Tomcat lab chưa chạy hoặc theo deployment procedure phù hợp.
3. So SHA-256 bản copy với WAR nguồn; phải trùng.
4. Khởi động Tomcat, chờ ứng dụng deploy xong và xem log.
5. Gọi `http://localhost:8080/dual-mode/probe` theo cấu hình ví dụ; kiểm tra HTTP 200 và body `READY|context=/dual-mode`.
6. Ghi context path/port và Tomcat version thực tế.
7. Nếu có reverse proxy/context descriptor, điều chỉnh URL và kỳ vọng theo deployment thực thay vì sửa Java mapping bừa bãi.

### Phần E – Làm rõ các trường hợp gây nhầm lẫn

Trên nhánh lab riêng (không thực hiện trên production), lần lượt phân tích:

- Deploy bản `-plain.war`: tại sao external container **có thể** chạy mà `java -jar` lại không?
- Đổi tên `dual-mode.war` thành `ROOT.war`: path và giá trị `ServletContext#getContextPath()` thay đổi thế nào, byte WAR có đổi không?
- Chạy external Tomcat ở cổng 8181 thay vì 8080: phải sửa cấu hình nào? Vì sao `--server.port=8181` không có tác dụng lên Tomcat đã cài riêng?
- Gỡ `SpringBootServletInitializer`: embedded `java -jar` có còn có đường khởi động qua `main` không? External startup có còn được đăng ký không?
- Bỏ `providedRuntime` hoặc chuyển Tomcat sang `implementation`: thay đổi gì trong `WEB-INF/lib-provided`/`WEB-INF/lib` và rủi ro classloader ngoài?
- Rebuild WAR giữa hai lần thử: làm sao phân biệt "cùng mã" với "cùng byte artifact"?

Các thay đổi có thể làm WAR lỗi là **bài thực hành trên bản sao**. Sau khi quan sát, hoàn nguyên cấu hình trước khi xây pipeline release.

## 17. Mẫu báo cáo hai-mode deployment

Dùng mẫu sau để người khác tái hiện kết quả; các giá trị in hoa là **trường cần điền theo kết quả thật**, không phải dữ liệu quan sát đã được tạo:

```text
Tên project/module: DUAL_MODE_MODULE
Spring Boot plugin version: BOOT_VERSION
Java (build/run): JAVA_VERSION
Build system: MAVEN_OR_GRADLE
Build command: EXACT_BUILD_COMMAND
WAR origin path: EXACT_ORIGIN_WAR_PATH
WAR origin SHA-256: ACTUAL_SHA256
WAR deploy copy path: EXACT_TOMCAT_WEBAPPS_WAR_PATH
WAR deploy SHA-256: ACTUAL_SHA256
Archive layout check: PASS_OR_FAIL

Standalone command: EXACT_JAVA_JAR_COMMAND
Standalone bind port: ACTUAL_PORT
Standalone URL: ACTUAL_URL
Standalone HTTP status: ACTUAL_HTTP_STATUS
Standalone response: ACTUAL_RESPONSE

Tomcat external version: ACTUAL_TOMCAT_VERSION
Tomcat connector port: ACTUAL_CONNECTOR_PORT
External context path: ACTUAL_CONTEXT_PATH
External URL: ACTUAL_EXTERNAL_URL
External HTTP status: ACTUAL_HTTP_STATUS
External response: ACTUAL_RESPONSE

Same WAR bytes? YES_IF_SHA256_MATCH
Both boot modes successful? YES_ONLY_IF_BOTH_HTTP_CHECKS_PASS
Observed discrepancies: ACTUAL_DETAILS
```

Đừng gửi template trống làm một "báo cáo PASS". Phải ghi dữ liệu thật và giữ các log quan trọng. Nếu không có môi trường Tomcat để deploy, có thể hoàn thành phần standalone, **nhưng phải báo rõ external deployment chưa được kiểm chứng**; không suy ra kết quả từ lý thuyết.

## 18. Tài liệu chính thức để đối chiếu

- Spring Boot 3.3.13 – Traditional Deployment (Servlet initializer, Maven provided, Gradle providedRuntime): https://docs.spring.io/spring-boot/3.3/how-to/deployment/traditional-deployment.html
- Spring Boot 3.3 – Gradle Plugin, Packaging Executable Archives (`bootWar`, `WEB-INF/lib-provided`, plain WAR): https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 – Maven Plugin, Packaging Executable Archives (WAR repackage, provided, manifest/layout): https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3.13 – System Requirements (Java, Maven/Gradle, Servlet container): https://docs.spring.io/spring-boot/3.3/system-requirements.html
- Spring Boot 3.3 – Executable Jar/WAR Format: https://docs.spring.io/spring-boot/3.3/specification/executable-jar/index.html
- Apache Tomcat 10.1 – Application Deployment and Manager, Servlet specification: https://tomcat.apache.org/tomcat-10.1-doc/deployer-howto.html
- Apache Tomcat 10.1 – Context Configuration: https://tomcat.apache.org/tomcat-10.1-doc/config/context.html
- Gradle – War Plugin: https://docs.gradle.org/current/userguide/war_plugin.html
- Maven – Dependency Scope Mechanism (`provided`): https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html

**Ghi nhớ:** một executable WAR đáng tin cho hai chế độ cần có **`main` + `SpringBootServletInitializer` + phân loại embedded server là provided + layout `lib-provided`**. Việc kiểm chứng phải đi hết chuỗi **build một WAR → xem layout → chạy `java -jar` → copy nguyên byte → so SHA-256 → deploy Tomcat ngoài → gọi HTTP thực tế**. Chỉ khi **cả hai lượt chạy thành công với cùng byte WAR**, mới có thể kết luận đáp ứng đề bài.

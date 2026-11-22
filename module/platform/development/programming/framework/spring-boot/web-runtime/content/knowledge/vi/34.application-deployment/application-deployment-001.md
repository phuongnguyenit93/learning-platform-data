# Chạy executable JAR và phân biệt với triển khai WAR trong Spring Boot

## 1. Mục tiêu và bối cảnh

Spring Boot giúp đóng gói một ứng dụng Java thành file có thể triển khai. Với ứng dụng web, hai hình thức thường gặp là **executable JAR** và **WAR**. Tên phần mở rộng chưa nói hết cách chạy: một Spring Boot **executable WAR** có thể chạy bằng `java -jar` **và** được triển khai vào Servlet container ngoài, trong khi một WAR truyền thống thường chỉ triển khai vào container.

Câu hỏi bài học cần trả lời:

1. `./gradlew bootJar` tạo gì, vì sao `java -jar application.jar` khởi động được HTTP server mà không cần cài Tomcat riêng?
2. `./gradlew bootWar` khác `war`/plain WAR thế nào? Khi nào dùng `java -jar application.war`?
3. Khi triển khai WAR lên Tomcat ngoài, ai khởi động Spring, ai sở hữu HTTP port, URL context path và lifecycle?
4. Vì sao cần `SpringBootServletInitializer`, `war` plugin và `providedRuntime`?
5. Phải chọn file/thư mục, cấu hình, phiên bản Java/Jakarta Servlet và kiểm thử nào để tránh lỗi “chạy trong IDE được nhưng deploy lỗi”?

Bài tập dùng **Java 17+, Spring Boot 3.3.13, Gradle 8.x** và Spring MVC trên Tomcat. Các version chỉ nhằm giữ ví dụ tái lập được; môi trường production nên chọn dòng Spring Boot còn được hỗ trợ và cập nhật bảo mật theo chính sách tổ chức.

### Bảng quyết định nhanh

| Hình thức | Lệnh/chỗ chạy | Máy chủ web do ai cung cấp? | Thường dùng |
| --- | --- | --- | --- |
| Spring Boot **executable JAR** | `java -jar app.jar` | Embedded Tomcat/Jetty/Undertow hoặc Netty trong ứng dụng | Service độc lập, container/VM, CI/CD |
| Spring Boot **executable WAR** chạy standalone | `java -jar app.war` | Embedded Servlet container được đóng gói ở `WEB-INF/lib-provided` | Giữ đường triển khai vừa standalone vừa external WAR |
| Spring Boot **WAR deployable** | Chép/deploy WAR vào Tomcat/Jetty ngoài tương thích | Servlet container **bên ngoài** | Hạ tầng quản trị container tập trung, legacy platform |
| Plain JAR từ Gradle `jar` | Không mặc nhiên chạy bằng `java -jar` | Không mặc nhiên có HTTP server/dependencies | Thư viện hoặc archive lớp Java |
| Plain WAR từ Gradle `war` | Container ngoài | Container ngoài | WAR truyền thống; không chắc tự thực thi bằng `java -jar` |

**Kết luận trước tiên:** JAR vs WAR là *packaging và ownership của web runtime*, không phải “JAR là backend, WAR là frontend”, cũng không phải “WAR bắt buộc chạy chậm hơn”. Chi phí start, bộ nhớ và khả năng scale còn phụ thuộc cấu hình server, số service, dependencies và workload.

## 2. Executable JAR của Spring Boot là gì?

JAR là ZIP archive theo chuẩn Java. Một **plain JAR** có thể chứa class/resources, nhưng thường không gom runtime dependencies và không có Boot launcher. Spring Boot Gradle plugin có task `bootJar` tạo **repackaged executable JAR** với các dependencies bên trong theo cấu trúc riêng.

Sơ đồ của `packaging-demo.jar`:

~~~text
packaging-demo.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/...   (Spring Boot launcher)
└── BOOT-INF/
    ├── classes/
    │   ├── demo/packaging/PackagingApplication.class
    │   ├── demo/packaging/HelloController.class
    │   └── application.properties
    ├── lib/
    │   ├── spring-boot-*.jar
    │   ├── spring-webmvc-*.jar
    │   ├── tomcat-embed-*.jar
    │   └── ... các dependency runtime khác
    ├── classpath.idx                   (nếu có)
    └── layers.idx                      (nếu layered)
~~~

Spring Boot launcher biết đọc nested JARs trong `BOOT-INF/lib` và app classes trong `BOOT-INF/classes`, thiết lập classloader rồi gọi `main(String[])` của ứng dụng.

Trong **Spring Boot 3.3**, manifest thường chứa:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: demo.packaging.PackagingApplication
~~~

`Main-Class` là launcher của Spring Boot; `Start-Class` mới là class ứng dụng viết `@SpringBootApplication`. Không nhầm hai trường. Cấu trúc và tên package của launcher đã thay đổi giữa các dòng Boot cũ và mới; với Boot 3.3 dùng `org.springframework.boot.loader.launch.JarLauncher`, không sao chép tên cũ `org.springframework.boot.loader.JarLauncher` vào một manifest tùy biến.

### Vì sao chạy được bằng java -jar?

~~~text
java -jar packaging-demo.jar
    |
    v
JVM đọc META-INF/MANIFEST.MF
    |
    v
Spring Boot JarLauncher
    |
    v
BOOT-INF/classes + BOOT-INF/lib/*.jar
    |
    v
PackagingApplication.main()
    |
    v
SpringApplication.run(...)
    |
    v
ApplicationContext + embedded Tomcat
    |
    v
HTTP listener, ví dụ localhost:8080
~~~

Vì dependency `spring-boot-starter-web` mang embedded Tomcat mặc định, không cần tự cài Tomcat system service trên host. Đây là cách chạy **một process JVM độc lập**, khác việc nạp WAR vào container đã chạy sẵn.

**Fat JAR/uber JAR không có nghĩa mọi class của dependencies bị “shade” chung vào một thư mục.** Boot executable JAR giữ nhiều thư viện như **nested JARs**, có loader đặc thù. Một số công cụ dùng classpath/ZIP truyền thống không hiểu nested format; cần build/test artifact thật.

## 3. WAR và Web Application Archive

WAR cũng là ZIP-based archive, được chuẩn hóa để Servlet container nhận ứng dụng web. Với Spring MVC Servlet application, một deployable WAR thường có dạng:

~~~text
packaging-demo.war
├── META-INF/
├── org/springframework/boot/loader/...   (nếu bootWar)
└── WEB-INF/
    ├── classes/
    │   ├── demo/packaging/PackagingApplication.class
    │   └── ...
    ├── lib/
    │   ├── spring-webmvc-*.jar
    │   ├── spring-context-*.jar
    │   └── ... các app runtime dependencies
    └── lib-provided/
        ├── tomcat-embed-*.jar
        └── ... embedded container runtime dùng khi java -jar
~~~

Trong Spring Boot `bootWar`, `WEB-INF/lib-provided` là điểm đặc biệt:

- Khi chạy `java -jar packaging-demo.war`, `WarLauncher` thêm **`WEB-INF/lib` và `WEB-INF/lib-provided`** vào classpath → embedded Tomcat có sẵn.
- Khi external Tomcat triển khai WAR, Servlet container **không tải** thư viện từ `WEB-INF/lib-provided` như runtime webapp libraries → dùng Servlet engine do Tomcat ngoài cung cấp, tránh đụng hai servlet containers.
- Các dependencies thông thường trong `WEB-INF/lib` vẫn được container nạp cho ứng dụng.

Manifest của executable WAR theo Boot 3.3 thường dùng:

~~~text
Main-Class: org.springframework.boot.loader.launch.WarLauncher
Start-Class: demo.packaging.PackagingApplication
~~~

**Không phải mọi file đuôi .war đều có WarLauncher.** Plain WAR tạo bằng task `war` có thể deploy lên container nhưng `java -jar plain.war` không chạy như một app Boot standalone. Cần kiểm tra task tạo file và manifest.

## 4. Khác biệt về trách nhiệm vận hành

| Khía cạnh | Executable JAR | WAR trong external Servlet container |
| --- | --- | --- |
| Process | Mỗi app thường là một JVM/process | Một Tomcat JVM có thể chứa nhiều WAR web contexts |
| HTTP port | App embedded server đọc `server.port` | Container ngoài điều khiển connector port |
| Base context | App `server.servlet.context-path` cho embedded Servlet server | WAR filename/context config của external Tomcat |
| Startup entry | `main` → `SpringApplication.run` | Container → `SpringBootServletInitializer.onStartup` |
| Shutdown | Signal/JVM process → Spring lifecycle | Context undeploy/redeploy/container lifecycle |
| Tomcat upgrade | Đổi dependency, build/redeploy app | Upgrade Tomcat outside + tương thích mọi webapps |
| Classpath | Boot launcher và nested JARs | Container classloader + `WEB-INF/classes/lib` |
| Config | Env, args, config files, image settings | Env/app external config + container server config |
| Isolation | Mỗi instance riêng, vẫn chia host/kernel/network | Các WAR chia sẻ JVM/container, classloaders riêng nhưng có shared process risks |
| Scale | Thêm JVM/pod/VM | Nhân bản container hoặc deploy nhiều app contexts |
| Debug port clash | Trùng `server.port` trên một host | Trùng connector port, context path hoặc WAR deployment |
| JSP | Executable JAR không hỗ trợ JSP theo Boot docs | WAR với Tomcat/Jetty có thể hỗ trợ JSP |
| WebFlux Reactor Netty | JAR phù hợp | WAR traditional deployment **không được Boot hỗ trợ** cho WebFlux app |

WAR không tự bảo đảm classloader isolation hoàn toàn: container/shared JVM/logging/temp dirs/JNDI/container libraries có thể tạo coupling. JAR cũng không tự an toàn: secrets, file permissions, proxy, graceful shutdown và CVE updates vẫn cần quản lý.

## 5. Dự án A runnable: executable JAR với Spring MVC

### 5.1. Cấu trúc file

~~~text
packaging-demo/
├── settings.gradle
├── build.gradle
├── src/
│   ├── main/
│   │   ├── java/demo/packaging/
│   │   │   ├── PackagingApplication.java
│   │   │   └── HelloController.java
│   │   └── resources/application.properties
│   └── test/
│       └── java/demo/packaging/PackagingHttpTest.java
└── build/libs/                   (tạo sau build)
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'packaging-demo'
~~~

`build.gradle` (file đầy đủ để tạo executable JAR):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

// Đặt tên deterministic để các lệnh lab khớp artifact.
tasks.named('bootJar') {
    archiveFileName = 'packaging-demo.jar'
}
~~~

Giải thích:

- `java` plugin cho build Java và task `jar`.
- `org.springframework.boot` plugin cho task `bootJar`, đưa Boot loader + dependencies vào executable archive.
- `io.spring.dependency-management` dùng dependency versions do Spring Boot quản lý; không cần khai báo mỗi version Tomcat/Spring/Jackson.
- `spring-boot-starter-web` kéo Spring MVC/Jackson + embedded Tomcat.
- `spring-boot-starter-actuator` cho health endpoint nhằm kiểm thử vận hành.
- `archiveFileName` đặt artifact chính là `packaging-demo.jar` (nếu bỏ, tên thường bao gồm project name/version).
- `testImplementation` chỉ dùng khi test, không tự đóng vào production runtime.

### 5.2. Main class

`src/main/java/demo/packaging/PackagingApplication.java`:

~~~java
package demo.packaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PackagingApplication {
    public static void main(String[] args) {
        SpringApplication.run(PackagingApplication.class, args);
    }
}
~~~

`@SpringBootApplication` bật component scan từ package `demo.packaging` và auto-configuration. Starter Web có Servlet web stack nên Spring Boot khởi tạo embedded Tomcat khi chạy `main`.

### 5.3. Controller

`src/main/java/demo/packaging/HelloController.java`:

~~~java
package demo.packaging;

import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {

    @GetMapping(value = "/hello",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public String hello() {
        return "Hello from Spring Boot!";
    }

    @GetMapping("/hello/{name}")
    public Map<String, String> helloName(
            @PathVariable String name) {

        return Map.of(
                "greeting", "Hello, " + name,
                "packaging", "same-business-code");
    }
}
~~~

Cùng code controller sẽ dùng được ở embedded JAR, executable WAR và external Tomcat WAR. Logic nghiệp vụ không cần biết artifact extension, nhưng **URL base context và lifecycle** sẽ khác.

### 5.4. Properties

`src/main/resources/application.properties`:

~~~properties
# Dùng cho embedded server khi java -jar / bootRun.
server.port=8080

# Embedded mode mặc định là root context (/).
# Không đặt context-path để thấy khác biệt khi deploy external WAR.

management.endpoint.health.probes.enabled=true
~~~

Port 8080 là Boot/Tomcat embedded default phổ biến, nhưng khai báo rõ cho lab. External WAR do Tomcat connector port quản lý; `server.port=8080` trong app **không mở một Tomcat thứ hai** khi được load bởi container ngoài.

### 5.5. Build, chạy và thử bằng cURL

Yêu cầu máy có Java 17+ và Gradle wrapper phù hợp hoặc Gradle tương thích.

Linux/macOS:

~~~bash
./gradlew clean test bootJar
java -jar build/libs/packaging-demo.jar
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat clean test bootJar
java -jar .\build\libs\packaging-demo.jar
~~~

Nếu chưa có wrapper `gradlew`, cài Gradle tương thích và tạo wrapper hoặc chạy `gradle clean test bootJar`. Không phụ thuộc IDE đang mở sau khi JAR được build.

Terminal khác:

~~~bash
curl -i http://localhost:8080/hello
~~~

Response dự kiến (headers khác theo môi trường):

~~~http
HTTP/1.1 200
Content-Type: text/plain;charset=UTF-8

Hello from Spring Boot!
~~~

Spring có thể in Content-Type với charset/format khác; điều bắt buộc ở đây là HTTP 200 và body `Hello from Spring Boot!`.

~~~bash
curl -i http://localhost:8080/hello/Linh
~~~

Body JSON tương đương:

~~~json
{
  "greeting": "Hello, Linh",
  "packaging": "same-business-code"
}
~~~

Thứ tự JSON keys và whitespace không phải contract nếu không yêu cầu explicit serialization. Với Actuator:

~~~bash
curl -i http://localhost:8080/actuator/health
~~~

Dự kiến trạng thái thông thường HTTP 200 và JSON chứa `"status":"UP"` nếu hệ thống khỏe; khi dependencies không khỏe status có thể khác.

### 5.6. Đổi port khi chạy, không rebuild JAR

~~~bash
java -jar build/libs/packaging-demo.jar --server.port=9090
curl -i http://localhost:9090/hello
~~~

Hoặc qua environment variable:

~~~bash
SERVER_PORT=9090 java -jar build/libs/packaging-demo.jar
~~~

PowerShell:

~~~powershell
$env:SERVER_PORT = "9090"
java -jar .\build\libs\packaging-demo.jar
~~~

**Thứ tự lệnh cần nhớ:**

- `-Xmx512m` và `-Duser.timezone=UTC` là JVM options → đặt **trước** `-jar`.
- `--server.port=9090` là Spring application argument → đặt **sau** tên JAR.
- `--spring.profiles.active=prod` là application argument. Trong production tránh đưa raw passwords/secrets vào command-line args vì có thể lộ trong process listing/diagnostics.

Ví dụ:

~~~bash
java -Xms128m -Xmx512m -Duser.timezone=UTC \
  -jar build/libs/packaging-demo.jar \
  --server.port=9090 --spring.profiles.active=prod
~~~

Chỉ dùng profile `prod` khi config/properties phù hợp tồn tại và đã được kiểm thử; ví dụ này không yêu cầu tạo một file profile bổ sung.

## 6. Kiểm tra file JAR đã build bằng tool của JDK

Để tránh nhầm một **plain JAR** với executable Boot JAR, dùng:

~~~bash
jar tf build/libs/packaging-demo.jar
~~~

Bạn cần thấy `BOOT-INF/classes/`, `BOOT-INF/lib/`, Spring Boot launcher và `META-INF/MANIFEST.MF`. Có thể lọc output nếu có `grep`:

~~~bash
jar tf build/libs/packaging-demo.jar | grep -E 'BOOT-INF|MANIFEST|JarLauncher'
~~~

Trên PowerShell:

~~~powershell
jar tf .\build\libs\packaging-demo.jar |
    Select-String "BOOT-INF|MANIFEST|JarLauncher"
~~~

Đọc manifest bằng `unzip -p` trên Linux/macOS nếu có unzip:

~~~bash
unzip -p build/libs/packaging-demo.jar META-INF/MANIFEST.MF
~~~

Bạn thường thấy hai dòng tương đương:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: demo.packaging.PackagingApplication
~~~

Còn một plain JAR có thể xuất hiện như `packaging-demo-1.0.0-plain.jar` nếu gọi task `jar`. Nó không tự chứa `BOOT-INF/lib` và không tự có Boot launcher. Nếu chạy:

~~~bash
java -jar build/libs/packaging-demo-1.0.0-plain.jar
~~~

có thể nhận `no main manifest attribute` hoặc thiếu runtime dependencies tùy cách plugin/task được cấu hình. **Không coi mọi .jar là self-contained.** Khi CI tạo nhiều artifacts, chọn đúng file từ task `bootJar` và kiểm tra manifest.

### Tại sao java -cp không tương đương?

~~~bash
# KHÔNG phải cách khởi động chuẩn cho Boot repackaged nested JAR:
java -cp build/libs/packaging-demo.jar demo.packaging.PackagingApplication
~~~

Classpath thông thường không tự nhận các nested jars trong `BOOT-INF/lib`/classes. Dùng `java -jar` với Boot launcher hoặc một cơ chế unpack/explicit classpath đã được thiết kế; đừng “sửa” bằng cách tháo nested libraries thủ công vào JRE lib directory.

## 7. Chạy cùng code dưới dạng WAR: thay đổi quan trọng nào?

Để chuyển **project A** thành **deployable + executable WAR**, giữ nguyên `HelloController.java`, `application.properties` và test. Thực hiện **hai thay đổi**:

1. Main class mở rộng `SpringBootServletInitializer` để container ngoài khởi tạo ứng dụng.
2. Build dùng `war` plugin, `providedRuntime` cho embedded servlet runtime, task `bootWar` tạo executable WAR.

### 7.1. Main class WAR hoàn chỉnh

**Thay nội dung file** `src/main/java/demo/packaging/PackagingApplication.java` bằng:

~~~java
package demo.packaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class PackagingApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(
            SpringApplicationBuilder application) {

        return application.sources(PackagingApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(PackagingApplication.class, args);
    }
}
~~~

Giải thích chính xác:

- **Chạy executable WAR bằng `java -jar`**: JVM gọi `WarLauncher` rồi tới method `main`; `SpringApplication.run` dựng embedded Tomcat.
- **Deploy WAR lên Tomcat ngoài**: Tomcat tạo web application context, cơ chế Jakarta Servlet startup gọi `SpringBootServletInitializer.onStartup` (thông qua Spring WebApplicationInitializer), method `configure` khai báo nguồn ứng dụng; **không cần JVM thực thi `main` của ứng dụng**.
- `configure(...)` trả `application.sources(PackagingApplication.class)`, bảo đảm đúng cấu hình root.
- Extends `SpringBootServletInitializer` không có nghĩa mỗi controller phải thay đổi. Đó là adapter cho truyền thống Servlet WAR deployment.
- Nếu chỉ chạy embedded JAR, bạn **không cần** extends initializer này; Spring Boot starter Web tự tạo embedded server thông qua `SpringApplication.run`.

**Package đúng của Boot 3.3:** `org.springframework.boot.web.servlet.support.SpringBootServletInitializer`. Đừng sao chép `org.springframework.boot.web.support.SpringBootServletInitializer` từ các ví dụ Boot 1.x.

### 7.2. Gradle build.gradle thay thế, bản WAR hoàn chỉnh

Thay toàn bộ `build.gradle` bằng:

~~~groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
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
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Quan trọng: servlet engine có khi chạy standalone,
    // nhưng external Tomcat sẽ cung cấp runtime riêng.
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

tasks.named('bootWar') {
    archiveFileName = 'packaging-demo.war'
}
~~~

Đây là cú pháp `providedRuntime` của **Spring Boot Gradle 3.3**. Một vài bài viết về Boot 4.x dùng artifact `spring-boot-starter-tomcat-runtime` khác; **không trộn dependency coordinates qua major versions**.

**Điểm dễ nhầm:** `spring-boot-starter-web` vẫn là dependency của Spring MVC; không cần exclude `spring-boot-starter-tomcat` khỏi starter-web trong mẫu Gradle 3.3 trên. Khai báo trực tiếp dependency Tomcat ở configuration `providedRuntime` theo tài liệu Boot sẽ đưa các runtime libs của container vào `WEB-INF/lib-provided`.

Vì sao không dùng `compileOnly`? Theo tài liệu Spring Boot, `providedRuntime` có mặt trên test runtime classpath để integration tests có thể chạy web server; `compileOnly` đơn lẻ không có runtime dependency cho tests và không bảo đảm cách đóng gói `lib-provided`.

### 7.3. Build và xem artifacts

~~~bash
./gradlew clean test bootWar
~~~

PowerShell:

~~~powershell
.\gradlew.bat clean test bootWar
~~~

Do đã cấu hình tên artifact:

~~~text
build/libs/packaging-demo.war
~~~

Task `bootWar` tạo executable WAR. Gradle task `war` có thể tạo thêm archive plain (thường classifier `-plain`). Spring Boot Gradle plugin dùng suffix `plain` cho `war` task khi cần phân biệt với `bootWar`. **Không chọn nhầm `packaging-demo-1.0.0-plain.war` để kiểm thử `java -jar`.**

Kiểm tra:

~~~bash
jar tf build/libs/packaging-demo.war
~~~

Kỳ vọng có `WEB-INF/classes/`, `WEB-INF/lib/`, `WEB-INF/lib-provided/`, Boot loader classes và manifest. `WarLauncher` đọc các nested libs thích hợp khi chạy standalone.

## 8. Cách A của WAR: chạy executable WAR bằng java -jar

Mặc dù artifact có đuôi .war, có thể chạy standalone:

~~~bash
java -jar build/libs/packaging-demo.war
curl -i http://localhost:8080/hello
~~~

Kỳ vọng HTTP 200 và body:

~~~text
Hello from Spring Boot!
~~~

**Giải thích:** WarLauncher sử dụng embedded Tomcat từ `WEB-INF/lib-provided` khi chạy standalone; Spring Boot nhận application arguments giống JAR:

~~~bash
java -jar build/libs/packaging-demo.war --server.port=9090
curl -i http://localhost:9090/hello
~~~

Lúc này container web là một phần của ứng dụng, `server.port` có hiệu lực. Bạn không phải cài một Tomcat riêng hay copy WAR vào `webapps`. Đây là lý do “WAR luôn phải chạy trong Tomcat bên ngoài” là một kết luận **sai** với Spring Boot executable WAR.

### Giới hạn đúng

- Chỉ WAR có manifest/Boot loader và các dependencies được đóng gói hợp lệ mới chạy theo cách này. Plain WAR không tự có behavior ấy.
- Đừng chạy `java -jar` WAR và đồng thời deploy **cùng WAR lên external Tomcat** trên cùng cổng 8080 rồi nhầm tưởng hai chế độ không xung đột; đó là hai process/listeners riêng.
- Không suy rằng WAR standalone là native image hoặc container image; nó vẫn là JVM application, dùng Java runtime trên host/container.
- Nếu dùng JSP, executable WAR trên Tomcat hoặc Jetty có thể phù hợp hơn JAR (theo giới hạn JSP của Spring Boot). Nhưng phải test resolver/JSP dependencies/context path cụ thể.

## 9. Cách B của WAR: triển khai lên external Tomcat 10.1

### 9.1. Điều kiện

Spring Boot 3.3 yêu cầu **Java 17 trở lên**. Servlet container ngoài phải tương thích **Jakarta Servlet** (tài liệu Boot 3.3 cho biết Servlet 5.0+; embedded Tomcat 10.1 dùng Servlet 6.0). Với lab, dùng external **Tomcat 10.1** chạy trên Java 17.

**Tránh Tomcat 9 với Boot 3.3 Servlet WAR:** Tomcat 9 dùng `javax.servlet.*`, trong khi Spring Framework 6/Spring Boot 3 dùng `jakarta.servlet.*`. Chỉ đổi đuôi từ JAR sang WAR không sửa namespace incompatibility; có thể gặp class-not-found, failed context startup hoặc HTTP 404. Những container app server enterprise khác cần kiểm tra mức Jakarta Servlet API được hỗ trợ, classloader và versions.

### 9.2. Cách deploy thông thường

Giả sử đã cài Tomcat 10.1 và có `CATALINA_BASE`/`CATALINA_HOME` hợp lệ:

~~~text
<tomcat-home>/
├── bin/
│   ├── catalina.sh / catalina.bat
│   └── ...
├── conf/
├── logs/
└── webapps/
    └── packaging-demo.war
~~~

Dừng process standalone đang chạy cổng 8080. Copy file `build/libs/packaging-demo.war` vào thư mục deployment `webapps` của Tomcat ngoài:

~~~bash
cp build/libs/packaging-demo.war /opt/tomcat/webapps/packaging-demo.war
~~~

Đây là **đường dẫn minh họa**. Tomcat có thể được cài ở vị trí khác; môi trường corporate có thể quản trị deployment qua manager, service/container orchestration hoặc read-only image. Không copy trực tiếp vào production server nếu không có quyền/phương án rollback.

Khởi chạy Tomcat bằng cách phù hợp môi trường (ví dụ `bin/catalina.sh run` hoặc service manager). Với Tomcat connector mặc định cổng 8080 và context name lấy từ file `packaging-demo.war`:

~~~bash
curl -i http://localhost:8080/packaging-demo/hello
~~~

Body vẫn:

~~~text
Hello from Spring Boot!
~~~

**Đường dẫn khác rất quan trọng:**

- `java -jar packaging-demo.war` với embedded Tomcat root context → `/hello`.
- `packaging-demo.war` được deploy vào external Tomcat mặc định → `/packaging-demo/hello`.
- Nếu deploy thành `ROOT.war`/context path root phù hợp → `/hello`.
- Nếu container được cấu hình context khác, phải dùng URL context thực thay vì đoán theo filename.

Đây là nguyên nhân thường gặp của “JAR chạy OK nhưng WAR trả 404”: người kiểm tra gọi `/hello` thay vì `/packaging-demo/hello`. Đừng vội sửa `@GetMapping` trên controller.

### 9.3. Ai sở hữu port và context path?

Trong **standalone JAR/executable WAR**, ứng dụng sở hữu embedded server, nên:

~~~properties
server.port=8080
server.servlet.context-path=/shop
~~~

thường cho endpoint `/shop/hello`.

Trong **WAR ở external Tomcat**, Tomcat ngoài sở hữu connector port và webapp context. `server.port` trong Spring Boot **không phải nơi thay đổi Tomcat external port**; port được cấu hình ở server/container, như Tomcat `conf/server.xml` hay hệ thống quản trị tương ứng. Base context path do deployment name/context descriptor xác định, không dựa vào `server.servlet.context-path` dành cho embedded server.

Muốn thay port Tomcat ngoài, cần chỉnh cấu hình container đúng cách (hoặc mapping ở reverse proxy); muốn URL root phải deploy context root; đừng thay `server.port` rồi kỳ vọng external Tomcat mở một socket thứ hai.

### 9.4. External Tomcat Docker image minh họa

Để thực hành isolated Tomcat không cần cài server trực tiếp lên host, có thể dùng một image Tomcat 10.1/JRE17 còn được cung cấp và đã kiểm tra. Dockerfile tham khảo:

~~~dockerfile
FROM tomcat:10.1-jre17-temurin

# Container chuyên dùng cho lab, không dùng cho shared enterprise Tomcat.
RUN rm -rf /usr/local/tomcat/webapps/*

COPY build/libs/packaging-demo.war \
     /usr/local/tomcat/webapps/packaging-demo.war

EXPOSE 8080
~~~

Ví dụ build/run (đặt tên Dockerfile trên là `Dockerfile.tomcat`):

~~~bash
docker build -f Dockerfile.tomcat -t packaging-demo:external-war .
docker run --rm -p 8080:8080 packaging-demo:external-war
curl -i http://localhost:8080/packaging-demo/hello
~~~

Phải **dừng process JAR/WAR standalone trên port 8080 trước**. Registry tag, base digest, security patches và JDK/runtime cần được xác minh trong môi trường triển khai; production thường pin image digest thay cho floating tag. Đừng xóa các thư mục webapps trên một Tomcat chung của doanh nghiệp như dòng RUN trong lab này.

Một context được deploy thành `ROOT.war` sẽ ở root path; các policy session cookie, proxy, TLS và routing vẫn cần cấu hình ở container.

## 10. Trường hợp Maven: cùng nguyên tắc, khác cú pháp

Ví dụ trên dùng Gradle. Với Maven, `pom.xml` chỉ định:

~~~xml
<packaging>jar</packaging>
~~~

cho executable JAR, kết hợp Spring Boot Maven plugin `repackage`; thông thường `mvn clean package` sinh JAR chạy được bằng `java -jar target/....jar` khi plugin được cấu hình theo Boot parent hoặc explicit execution.

Để tạo WAR triển khai vào container ngoài:

~~~xml
<packaging>war</packaging>
~~~

Khi dùng `spring-boot-starter-web` cùng Tomcat, khai báo Tomcat ở scope `provided`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
~~~

Và cung cấp `SpringBootServletInitializer` như mục 7. Tùy cách cấu hình plugin, executable WAR cũng có thể được repackaged và chạy bằng `java -jar`.

**Đây là các mảnh thay đổi cấu hình Maven, không phải một `pom.xml` hoàn chỉnh**; dùng Spring Boot parent/BOM, Maven plugin và project coordinates nhất quán. Đừng kết luận đặt `<packaging>war</packaging>` là đủ: thiếu initializer hoặc provided server scope vẫn có thể lỗi khi container ngoài tải webapp.

## 11. WAR plain, WAR executable và library JAR: phân biệt bằng task

Spring Boot Gradle plugin định nghĩa:

| Task | Output điển hình | Dùng để |
| --- | --- | --- |
| `bootJar` | `app.jar` | Executable Boot JAR |
| `jar` | `app-...-plain.jar` | Plain classes/resources JAR |
| `bootWar` | `app.war` | Executable Boot WAR; deployable khi cấu hình đúng |
| `war` | `app-...-plain.war` | Plain WAR cho Servlet container |
| `bootRun` | Không tạo archive bắt buộc | Chạy app từ classes/dependencies lúc dev |
| `build` | Có thể chạy tests + assemble artifacts | CI build; cần kiểm tra artifact nào được xuất |
| `test` | Test reports/classes | Unit/integration tests trên build classpath, chưa tự test artifact deployment |

`bootWar` chỉ có khi Gradle `war` plugin được áp dụng. `bootJar` có khi `java` plugin được áp dụng cùng Spring Boot plugin; trong project có cả war plugin, cách Gradle chọn default archive/tasks có thể khác dự án JAR ban đầu. Với bài này, **gọi tường minh `bootJar` hoặc `bootWar`** và lấy đúng artifact file để tránh lẫn.

Một file `-plain.jar` không tự chạy vì thiếu Boot launcher/nested dependencies; một file `-plain.war` có thể triển khai lên Tomcat nhưng không chạy như executable WAR. Đây là lý do CI/CD không nên dùng wildcard `build/libs/*` để deploy khi có nhiều file.

### Quy tắc CI artifact

- CI job JAR: artifact chính `build/libs/packaging-demo.jar` do `bootJar` tạo.
- CI job WAR: artifact chính `build/libs/packaging-demo.war` do `bootWar` tạo.
- Chạy checksum/signature/SBOM trên **chính file sẽ deploy**, không kiểm tra `-plain` rồi deploy boot archive.
- Test chạy `java -jar` từ artifact đã tạo chứ không chỉ test `bootRun` từ classes.
- Nếu deploy external Tomcat, test `packaging-demo.war` trên container ngoài thực tế.

## 12. Kiểm chứng bằng Spring Boot integration test

Test sau dùng được cho cả project A (JAR) và project B (WAR) nếu Servlet Tomcat test dependencies được cấu hình đúng.

`src/test/java/demo/packaging/PackagingHttpTest.java`:

~~~java
package demo.packaging;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class PackagingHttpTest {

    @Autowired
    TestRestTemplate http;

    @Test
    void helloEndpointWorks() {
        ResponseEntity<String> r =
                http.getForEntity("/hello", String.class);

        assertThat(r.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(r.getBody()).isEqualTo(
                "Hello from Spring Boot!");
    }

    @Test
    void greetingEndpointHasExpectedField() {
        ResponseEntity<String> r =
                http.getForEntity("/hello/Linh", String.class);

        assertThat(r.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(r.getBody())
                .contains("Hello, Linh");
    }

    @Test
    void unknownRouteReturns404() {
        ResponseEntity<String> r =
                http.getForEntity("/not-found", String.class);

        assertThat(r.getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
    }
}
~~~

### Test này chứng minh gì?

- Boot context load được.
- Embedded Servlet server tạo HTTP port thật (random port) và controller routing chạy.
- Hai endpoints trả hợp đồng đúng, unknown path 404.

**Không chứng minh** WAR deploy lên external Tomcat được: JUnit `@SpringBootTest(RANDOM_PORT)` khởi động embedded server theo runtime classpath của tests, không khởi chạy Tomcat outside. Phải có **integration test thứ hai** triển khai WAR vào external container hoặc Dockerized Tomcat, gọi URL `/packaging-demo/hello` và kiểm tra logs/health.

Vì `providedRuntime` vẫn nằm trên test runtime classpath, test Boot WAR có thể khởi embedded Tomcat bình thường. Đây là lợi ích thực tiễn so với `compileOnly`.

## 13. Triển khai tự động: một test matrix tối thiểu

| Case | Cách chạy | Request cần thử | Điều kiểm tra |
| --- | --- | --- | --- |
| Dev classes | `./gradlew bootRun` | `GET /hello` | Logic chạy nhưng chưa chứng minh archive |
| Executable JAR | `java -jar packaging-demo.jar` | `GET /hello` | Boot launcher, nested libs, embedded port |
| Executable WAR standalone | `java -jar packaging-demo.war` | `GET /hello` | WarLauncher và lib-provided hoạt động |
| External Tomcat WAR | Deploy `packaging-demo.war` | `GET /packaging-demo/hello` | Servlet initializer, container classloader và context |
| External WAR root | Deploy `ROOT.war`/context root | `GET /hello` | Đường context đúng |
| Port override | `--server.port=9090` sau `java -jar` | `GET :9090/hello` | Spring embedded port property |
| External port override | Đổi connector Tomcat ngoài | `GET :customPort/packaging-demo/hello` | Container owns port, không phải Boot property |
| Missing resource | Wrong context path | `GET /hello` trên external non-root | 404 dự kiến, không sửa controller vội |
| Graceful stop | SIGTERM cho JVM standalone | In-flight request, new request | Stop lifecycle và LB/proxy behavior |
| Security | Hợp đồng auth thật | Authorized/unauthorized paths | Filters/servlet mapping tương đương hai modes |

Khi test external WAR, kiểm tra log startup có context deployment lỗi hay không; HTTP 404 không luôn là business controller missing route, có thể ứng dụng đã fail startup hoàn toàn.

### Chỉ đo “200” chưa đủ

Với API thực tế, nên bổ sung:
- Authentication/authorization, CSRF, CORS.
- `@ControllerAdvice` error responses và static resources.
- Session persistence/cookies.
- Large upload, streaming/SSE và WebSocket (khi dùng).
- Database connectivity/transactions và migrations.
- Proxy forwarded headers/HTTPS redirects.
- Health readiness/liveness, graceful shutdown.
- Classpath/resource loading từ nested archive.

Những lớp này có thể khác khi chạy trong app-owned embedded server và shared external Tomcat.

## 14. Khi nào nên ưu tiên executable JAR?

Executable JAR thường phù hợp nếu:
- Muốn phát hành một artifact tự chứa runtime dependencies, chạy bằng Java 17+ và quản lý port qua config.
- Mỗi service độc lập, có lifecycle/rolling deployment riêng.
- Muốn đóng gói container theo nguyên tắc **một Java process phục vụ một ứng dụng**.
- Hạ tầng Kubernetes/VM đã có reverse proxy/LB và không yêu cầu container WAR tập trung.
- Cần dễ quản lý các version Spring Boot + embedded Tomcat cùng artifact.
- Dùng Spring WebFlux chạy trên embedded Reactor Netty.
- Không có yêu cầu JSP legacy phải phụ thuộc Servlet WAR deployment.

Ưu điểm là ứng dụng tự sở hữu embedded server: nâng version container thông qua dependency/build pipeline; dễ cài instrumentation/Actuator và test gần runtime production. Nhưng phải quản lý vulnerability scan, TLS/proxy, process signals, memory, logs, health và autoscaling đúng.

JAR không có nghĩa **không cần server**: embedded Tomcat/Jetty/Undertow/Netty vẫn là HTTP server, chỉ khác nơi nó được khởi tạo và phiên bản do ai quản lý.

## 15. Khi nào triển khai WAR vào container ngoài?

WAR external deployment có ý nghĩa nếu:
- Doanh nghiệp có hạ tầng quản trị Tomcat/Jakarta Servlet container chung.
- Chính sách yêu cầu deploy WAR vào server đã được vận hành/cập nhật/patched trung tâm.
- Ứng dụng legacy JSP/Servlet/JNDI đã được thiết kế theo context/classloader của app server.
- Cần cùng một artifact WAR vừa hỗ trợ migration gradual sang standalone vừa deploy cũ.
- Tổ chức đã có quy trình quản lý WAR/version/context và rollout an toàn.

Đánh đổi:
- Web container runtime và JVM thường được cập nhật **tách** khỏi ứng dụng, cần compatibility matrix.
- Nhiều webapps cùng JVM có shared memory/GC/process risks; lỗi hoặc update container có thể tác động nhiều app.
- Root/context paths khác và đôi khi có global filters, JNDI, JVM properties ngoài app.
- Quản lý secrets, config và classloaders có thể phức tạp.
- Không phải lựa chọn mặc định phù hợp cho Spring WebFlux apps chạy Netty; Boot 3.3 traditional WAR deployment không hỗ trợ WebFlux apps.

**Không chọn WAR chỉ vì nó được gọi là “enterprise”.** Chọn theo runtime contract và yêu cầu vận hành thực tế.

## 16. Spring WebFlux và ngoại lệ WAR quan trọng

Spring WebFlux thường chạy trên Reactor Netty với dependency:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-webflux'
~~~

Nó có thể đóng gói thành executable JAR và chạy:

~~~bash
./gradlew bootJar
java -jar build/libs/your-reactive-app.jar
~~~

Tên file ví dụ phụ thuộc `archiveFileName` của dự án; code path chỉ minh họa.

**Theo Spring Boot 3.3 Traditional Deployment guide**, WAR deployment **không được hỗ trợ đối với WebFlux applications** do WebFlux không phụ thuộc trực tiếp vào Servlet API và mặc định triển khai qua embedded Reactor Netty.

Lưu ý phân biệt:
- Spring MVC servlet controllers có thể dùng reactive return types (`Mono`/`Flux`) mà vẫn chạy Servlet stack; một app như thế có thể có đường WAR hợp lệ nếu được thiết kế theo MVC.
- Spring WebFlux application thuần với Reactor Netty không được “biến thành external WAR deployable” chỉ bằng cách thêm `war` plugin và `SpringBootServletInitializer`.
- Nếu cả `starter-web` và `starter-webflux` có mặt, Boot 3.3 thường chọn MVC Servlet application (trừ khi override). Xác định actual runtime bằng tests/context type.

## 17. JSP và view rendering: giới hạn khác biệt

Spring Boot 3.3 docs nêu:

- **JSP không được hỗ trợ khi dùng executable JAR.**
- Với Tomcat hoặc Jetty, dùng WAR packaging có thể hỗ trợ JSP; executable WAR chạy `java -jar` cũng có thể phù hợp.
- Undertow không hỗ trợ JSP theo Boot guidance.

Nếu dự án đang dùng JSP dưới `WEB-INF/jsp`, chuyển thành executable JAR có thể gây lỗi view resolver dù REST endpoints vẫn hoạt động. Cần chuyển template engine (Thymeleaf, FreeMarker...) hoặc dùng WAR và test JSP compilation/resolution.

Đừng suy rằng mọi file `.html` cần WAR: Spring MVC REST APIs, static HTML/CSS/JS, template engines phổ biến vẫn hoạt động trong Boot executable JAR khi cấu trúc resources đúng.

## 18. Classpath và resources khi chạy từ archive

Trong IDE, các resources có thể nằm trên filesystem `src/main/resources`. Sau build, chúng vào `BOOT-INF/classes` (JAR) hoặc `WEB-INF/classes` (WAR).

**Mẫu portable:**

~~~java
package demo.packaging;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class ResourceReader {

    public String readClasspathResource() throws IOException {
        try (InputStream in = getClass().getResourceAsStream(
                "/example-data.txt")) {

            if (in == null) {
                throw new IOException("Classpath resource not found");
            }
            return new String(in.readAllBytes(),
                    StandardCharsets.UTF_8);
        }
    }
}
~~~

Tệp này là Java utility độc lập, **chỉ chạy có kết quả nếu** thêm `src/main/resources/example-data.txt` vào dự án và gọi method từ code. Không phải endpoint runnable tự phát sinh từ snippet.

Sử dụng `getResourceAsStream` hoặc `ClassPathResource.getInputStream()`. Tránh:

~~~java
// Sai khi coi resource packaged như file của source tree:
new java.io.File("src/main/resources/example-data.txt");

// Không an toàn với nested JAR URLs nếu đòi regular File:
new org.springframework.core.io.ClassPathResource(
        "example-data.txt").getFile();
~~~

`ClassPathResource.getFile()` yêu cầu resource là filesystem file; trong executable JAR nó có thể nằm trong ZIP/nested JAR, không có path thông thường. Phần mã `new File` cũng phụ thuộc working directory, không phải classpath. Đọc bằng stream để portable giữa `bootRun`, JAR và WAR.

### Một số hạn chế nested JARs

Các thư viện dùng `File`, quét classpath hoặc custom classloaders có thể giả định classes nằm trên filesystem. Spring Boot launcher hỗ trợ nested JARs, nhưng ứng dụng cần test những thành phần như Jersey package scanning, reflection, template/resource loading, JAXB/services khi đóng gói.

Không sửa bằng cách bung toàn bộ JAR vào thư mục system và sửa JVM classpath nếu chưa có yêu cầu. Kiểm tra `requiresUnpack`/layertools hoặc cơ chế resource loading chính thức khi library thật không hỗ trợ nested archives.

## 19. Docker hóa executable JAR

`Dockerfile` cho project JAR đã build:

~~~dockerfile
FROM eclipse-temurin:17-jre

WORKDIR /opt/app
COPY build/libs/packaging-demo.jar /opt/app/app.jar

EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/opt/app/app.jar"]
~~~

Build/run:

~~~bash
./gradlew clean test bootJar
docker build -t packaging-demo:jar .
docker run --rm -p 8080:8080 packaging-demo:jar
~~~

HTTP:

~~~bash
curl -i http://localhost:8080/hello
~~~

**Container image không đồng nghĩa executable JAR:** image chỉ là một cách phân phối runtime, có thể chứa executable JAR, executable WAR standalone hoặc external Tomcat đang deploy WAR.

Trong production:
- Pin base image digest và cập nhật CVE fixes.
- Chạy non-root khi có thể, đặt JVM memory/container limits phù hợp.
- Đưa secrets qua cơ chế quản lý riêng, không hardcode trong JAR/Dockerfile.
- Dùng exec-form ENTRYPOINT để Java nhận SIGTERM, cấu hình graceful shutdown và Pod readiness.
- Thu logs stdout/stderr bằng collector; giữ external state trong DB/volumes phù hợp.
- Dùng layered JAR/buildpacks nếu muốn tối ưu Docker cache/startup/size, không bắt buộc cho bài học JAR vs WAR.

### Layered JAR

Spring Boot Gradle `bootJar` có thể tạo `BOOT-INF/layers.idx` để mô tả application/dependency layers. Docker buildpacks hoặc layers extraction tận dụng cache khi code thay nhưng dependencies không đổi. Layering **không đổi** HTTP semantics hoặc yêu cầu JVM runtime. Không giả định JAR có layers là Docker image đã deploy; nó vẫn là archive.

## 20. Java process và vận hành ở production

Một lệnh:

~~~bash
java -Xms256m -Xmx768m -jar packaging-demo.jar \
  --spring.profiles.active=prod --server.port=8080
~~~

vẫn cần:
1. Service manager/systemd hoặc container runtime để restart khi crash.
2. Reverse proxy/TLS termination hoặc SSL/TLS listener cấu hình đúng.
3. Health endpoints/readiness và timeout phù hợp.
4. Environment configuration/secrets tách artifact immutable.
5. Log aggregation/metrics/tracing, thread/connection pools.
6. Graceful shutdown để request đang xử lý được drain.
7. File descriptor/CPU/memory limits, autoscaling và network firewall.
8. Rollback và schema/data compatibility.

Với WAR external, phần lớn **process-level** concerns do Tomcat/container operator quản lý, nhưng app vẫn chịu trách nhiệm business state, HTTP security, resilience và data correctness.

### Graceful shutdown trong embedded app

Ví dụ:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=25s
~~~

Khi Java process nhận SIGTERM, Boot có cơ hội ngừng nhận request mới và đợi in-flight requests. Với WAR trong external container, shutdown chịu lifecycle của webapp context/Servlet container ngoài, nên không giả định tính năng process-level graceful của embedded server có thể điều khiển external Tomcat connector.

Trong Kubernetes, `terminationGracePeriodSeconds` phải bao gồm thời gian preStop và application shutdown. JAR/WAR standalone dùng process signals, còn WAR external phải drain ở container/LB tương ứng, và có thể chia sẻ một server process với ứng dụng khác.

## 21. Những lỗi phổ biến và cách xác định đúng nguyên nhân

| Triệu chứng | Khả năng cao | Cách kiểm tra |
| --- | --- | --- |
| `no main manifest attribute` | Đang chạy plain JAR/WAR, không phải boot archive | `jar tf`/manifest; task `bootJar`/`bootWar` |
| `ClassNotFoundException` JarLauncher | Archive/manifest bị tạo sai, Boot version path cũ | Main-Class của Boot 3.3 là `org.springframework.boot.loader.launch.JarLauncher` |
| `ClassNotFoundException` Spring class | Đã dùng plain JAR không kèm dependencies | Deploy `bootJar`/`bootWar` thay vì `jar` |
| `Address already in use: bind` | Hai standalone processes cùng port | `server.port`, chạy mỗi app cổng khác, dừng instance cũ |
| `GET /hello` là 404 trên Tomcat external | URL thiếu `/packaging-demo` context | Gọi `/packaging-demo/hello` hoặc root context đúng |
| `server.port` không đổi port WAR external | Port do container ngoài quản lý | Sửa Tomcat connector/proxy, không app property |
| WAR deploy không khởi động | Thiếu SpringBootServletInitializer | Extends và configure sources đúng |
| `NoClassDefFoundError: jakarta/servlet/...` | Container không tương thích Jakarta Servlet, thiếu libs | Tomcat 10.1/Servlet 5.0+, Boot 3.3, Java17 |
| Lỗi `javax.servlet` khi chạy Boot 3 | Dependencies/container thuộc Java EE cũ | Loại incompatibility, nâng/migrate Jakarta |
| Embedded Tomcat xung đột external | Chưa đặt provided scope đúng | `providedRuntime`, kiểm tra `WEB-INF/lib-provided` |
| WAR chạy standalone OK, external lỗi | Chỉ có embedded test, classloader/context khác | Test thật trên external container |
| Test WAR `@SpringBootTest` thiếu server | Dùng `compileOnly` thay providedRuntime | `providedRuntime` giữ runtime trong test |
| JSP view lỗi khi executable JAR | JSP không hỗ trợ packaging này | WAR trên Tomcat/Jetty hoặc thay template |
| WebFlux WAR deploy lỗi | Boot 3.3 không hỗ trợ traditional WebFlux WAR | Executable JAR Reactor Netty |
| `FileNotFoundException` resource sau build | Dùng path `src/main/resources`/`getFile()` | Classpath stream, jar tf kiểm tra resource |
| 8080 container chạy nhưng host không truy cập | Không publish/map port, firewall | `docker run -p`, network/port config |
| HTTPS redirect URL sai | Forwarded headers/context path/proxy trust | Test proxy setup và trusted headers |
| Hai JAR tên gần giống trong build/libs | boot archive vs `-plain` artifact | Chọn explicit artifact từ task |
| WAR triển khai context mới nhưng session mất | Container redeploy, session chỉ ở RAM | Spring Session/shared store hoặc stateless |
| Upgrading external Tomcat phá app khác | Nhiều WAR chia một JVM/runtime | Compatibility matrix, staging test, rollback |
| Health UP nhưng HTTP endpoint lỗi | Health không kiểm tra toàn bộ request path | Curl/integration tests qua public routing |

Đừng sửa controller ngay khi thấy 404. Đầu tiên xác minh **process thực đang chạy, packaging file được deploy, context path, port và Tomcat logs**.

## 22. Mô hình chọn JAR/WAR trong phỏng vấn và thiết kế hệ thống

**Tình huống A — Microservice REST nhỏ, deploy Kubernetes.** Chọn executable JAR hoặc container image từ JAR. Service tự sở hữu HTTP listener, được rollout độc lập; test `bootJar`, `java -jar`, health, graceful stop và retry/idempotency.

**Tình huống B — Hệ thống quản trị có shared enterprise Tomcat và yêu cầu WAR.** Chọn deployable WAR, extends `SpringBootServletInitializer`, `providedRuntime`, container Jakarta compatible, test context path và servlet filters/JNDI/classloading. Nếu vẫn muốn chạy standalone trong CI, dùng executable WAR từ `bootWar`.

**Tình huống C — JSP legacy.** WAR phù hợp hơn JAR theo Boot JSP limitations; cân nhắc migration sang template engine hiện đại. Không giả định Undertow có JSP support.

**Tình huống D — Reactive API trên Netty.** Chọn executable JAR, không cố external WAR deployment cho WebFlux Boot 3.3.

**Tình huống E — Bắt đầu từ Spring MVC WAR cũ.** Chuyển dần sang Spring Boot WAR tương thích trước để ít thay đổi vận hành, rồi khi sẵn sàng mới chuyển sang standalone JAR và containerization. Phải test sessions, classloader, static files, external config và URLs.

### Một câu trả lời ngắn dễ nhớ

> Executable JAR mang Boot launcher + dependencies + embedded web server, chạy `java -jar`. Spring Boot executable WAR có thêm Servlet webapp layout, có thể `java -jar` hoặc deploy vào container ngoài khi cấu hình `SpringBootServletInitializer` và `providedRuntime`. External Tomcat sở hữu port/context/lifecycle, còn executable JAR/WAR standalone do chính Spring Boot quản lý server.

## 23. Checklist trước khi bàn giao artifact

- [ ] Java runtime tối thiểu Java 17 và Spring Boot/Gradle versions tương thích.
- [ ] Xác định artifact từ `bootJar` hay `bootWar`, không deploy nhầm plain archive.
- [ ] Kiểm tra manifest `Main-Class` và `Start-Class` đúng Boot 3.3.
- [ ] JAR có `BOOT-INF/classes` + `BOOT-INF/lib` và Boot launcher.
- [ ] WAR có `WEB-INF/classes`, `WEB-INF/lib`, `WEB-INF/lib-provided` nếu dùng providedRuntime.
- [ ] Main class có `public static void main` để chạy standalone.
- [ ] External WAR có `SpringBootServletInitializer.configure` và Servlet container Jakarta-compatible.
- [ ] Đã test `java -jar` trên artifact thật sau build.
- [ ] Đã test WAR trên external Tomcat thật, không chỉ `@SpringBootTest` embedded.
- [ ] URLs đúng theo root context vs WAR context name.
- [ ] Port config/SSL/proxy đúng owner: embedded server hay external Tomcat.
- [ ] Static resources/templates/JSP và classpath resource loading chạy từ packaged artifact.
- [ ] Không có `javax.servlet` legacy artifacts xung đột với Boot 3 `jakarta.servlet`.
- [ ] Sessions, security filters, CORS/CSRF, headers/redirects được kiểm tra trong hai modes.
- [ ] Đã test restart, graceful shutdown và in-flight requests.
- [ ] Artifact được ký/scanned/versioned, có checksum và rollback plan.
- [ ] Container/VM có logs, metrics, health, network, CPU/memory và secrets được quản lý.
- [ ] CI artifact path là explicit, không dùng wildcard chọn nhầm `plain`.
- [ ] Đã đọc tài liệu theo đúng Spring Boot version của dự án.

## 24. Bài tập tự kiểm tra

**1.** Spring Boot executable JAR được tạo bằng Gradle task nào?

**Đáp án:** `bootJar`, được Spring Boot Gradle plugin tạo khi dùng Java plugin. `jar` là plain JAR task, không tự đảm bảo Boot loader/dependencies.

**2.** Spring Boot executable WAR có chạy bằng `java -jar` được không?

**Đáp án:** Có, nếu tạo bằng `bootWar` và có embedded server runtime trong `WEB-INF/lib-provided`. Plain WAR thường không tự chạy được.

**3.** Ai quyết định HTTP port của WAR được triển khai vào Tomcat ngoài?

**Đáp án:** External Tomcat connector/container config, không phải `server.port` của embedded server.

**4.** `packaging-demo.war` trong Tomcat webapps ở root? URL cho `@GetMapping("/hello")` là gì?

**Đáp án:** Thông thường `/packaging-demo/hello`, vì WAR name định context. Root URL cần ROOT.war hoặc explicit root context configuration.

**5.** Vì sao cần `SpringBootServletInitializer`?

**Đáp án:** Để Servlet container ngoài khởi tạo Spring application context khi WAR được deploy, không phải JVM tự gọi method main.

**6.** `providedRuntime` có nhiệm vụ gì trong Boot Gradle WAR?

**Đáp án:** Đặt embedded servlet container runtime trong `WEB-INF/lib-provided` cho standalone execution nhưng không xung đột container ngoài; vẫn có dependency trên test runtime classpath.

**7.** `spring-boot-starter-web` có embedded Tomcat, vậy muốn WAR external có phải xóa starter-web không?

**Đáp án:** Không. Giữ starter-web và khai báo `providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'` theo Boot 3.3 guide.

**8.** Spring Boot 3.3 WAR có deploy trực tiếp lên Tomcat 9 không?

**Đáp án:** Không phù hợp: Tomcat 9 còn Java EE `javax.servlet`, Boot 3 dùng Jakarta. Dùng compatible Jakarta Servlet container, lab Tomcat 10.1 và Java 17+.

**9.** WebFlux Reactor Netty có nên đổi sang WAR external khi deploy không?

**Đáp án:** Không; Boot 3.3 không hỗ trợ traditional WAR deployment cho WebFlux apps. Dùng executable JAR và embedded Reactor Netty.

**10.** Executable JAR của Boot có phải một JAR “shade” toàn bộ classes không?

**Đáp án:** Không. Spring Boot thường dùng nested JARs trong `BOOT-INF/lib` và JarLauncher classloader.

**11.** Vì sao dùng `new File("src/main/resources/data.txt")` chạy trong IDE nhưng fail sau khi đóng gói?

**Đáp án:** Đó là path trên filesystem của source tree, không phải classpath resource trong ZIP archive. Dùng `getResourceAsStream` hoặc ClassPathResource input stream.

**12.** Đã chạy `@SpringBootTest(RANDOM_PORT)` thành công với WAR thì có cần test external Tomcat nữa không?

**Đáp án:** Có. Embedded integration test không kiểm chứng external Servlet container startup, classloader, context path hay deployment-specific filters.

**13.** JSP chạy được trong executable JAR Spring Boot 3.3 không?

**Đáp án:** Không được hỗ trợ theo Boot docs; WAR trên Tomcat/Jetty là lựa chọn phù hợp hơn nếu cần JSP.

**14.** Lỗi `no main manifest attribute` nên kiểm tra gì đầu tiên?

**Đáp án:** Kiểm tra có đang chạy `-plain.jar` hoặc `-plain.war` không; xem manifest và build bằng `bootJar`/`bootWar`.

## 25. Tài liệu chính thức

- [Spring Boot 3.3 — Traditional Deployment](https://docs.spring.io/spring-boot/3.3/how-to/deployment/traditional-deployment.html): SpringBootServletInitializer, WAR plugin, providedRuntime, giới hạn WebFlux.
- [Spring Boot 3.3 — Gradle Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html): bootJar/bootWar, plain archives, providedRuntime và lib-provided.
- [Spring Boot 3.3 — Executable Jar Format / Nested JARs](https://docs.spring.io/spring-boot/3.3/specification/executable-jar/nested-jars.html): BOOT-INF/classes, BOOT-INF/lib, WEB-INF/lib-provided.
- [Spring Boot 3.3 — Launching Executable Jars](https://docs.spring.io/spring-boot/3.3/specification/executable-jar/launching.html): JarLauncher, WarLauncher, Main-Class/Start-Class.
- [Spring Boot 3.3 — System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html): Java 17+, Servlet 5.0+, Tomcat 10.1/Jetty 12/Undertow 2.3.
- [Spring Boot 3.3 — SpringBootServletInitializer API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/servlet/support/SpringBootServletInitializer.html): onStartup/configure contract.
- [Spring Boot 3.3 — Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): embedded Servlet servers, JSP restrictions và Servlet initializer behavior.
- [Spring Boot 3.3 — Running Your Application](https://docs.spring.io/spring-boot/3.3/reference/using/running-your-application.html): bootRun/java -jar workflows.
- [Spring Boot 3.3 — Dockerfiles](https://docs.spring.io/spring-boot/3.3/reference/packaging/container-images/dockerfiles.html): executable archives trong container, layers.
- [Apache Tomcat 10.1 — Deployment](https://tomcat.apache.org/tomcat-10.1-doc/deployer-howto.html): context path và deploy WAR vào webapps.

**Ghi nhớ cuối:** JAR và WAR đều có thể là Spring Boot executable archives. `bootJar` cho app tự chạy với embedded server; `bootWar` có thể làm một artifact **hai chế độ**: `java -jar` (WarLauncher + lib-provided) hoặc triển khai lên external Tomcat (SpringBootServletInitializer + container owns port/context). Đúng artifact, đúng Java/Jakarta phiên bản, đúng URL/context path và test trên runtime thật mới quyết định deploy thành công.

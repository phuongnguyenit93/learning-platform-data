# Đối chiếu chạy từ IDE với chạy bằng công cụ build trong Spring Boot

## 1. Mục tiêu và phạm vi

Khi phát triển Spring Boot, cùng một ứng dụng có thể được khởi động theo nhiều cách:

1. Nhấn **Run/Debug** tại lớp có `public static void main(String[] args)` trong IntelliJ IDEA, Eclipse/STS hoặc VS Code.
2. Gọi **Spring Boot Maven Plugin** bằng `./mvnw spring-boot:run` (Windows: `mvnw.cmd spring-boot:run`).
3. Gọi **Spring Boot Gradle Plugin** bằng `./gradlew bootRun` (Windows: `gradlew.bat bootRun`).
4. Đóng gói bằng Maven/Gradle rồi chạy `java -jar` với executable JAR.

Ba cách đầu thường phục vụ vòng lặp phát triển; cách thứ tư giúp xác minh sản phẩm đóng gói, gần với kiểu triển khai JAR trên máy chủ hoặc trong container. Tất cả đều có thể khởi động cùng `@SpringBootApplication`, nhưng **cấu hình chạy, phiên bản Java, classpath, profile, biến môi trường, working directory và cách build trước khi chạy** có thể khác nhau.

Bài này hướng tới việc **đối chiếu hành vi và chẩn đoán sự khác biệt**, không mặc định IDE hay command line luôn đúng hơn. Mục tiêu thực tế: sau khi import dự án từ Spring Initializr, bạn có thể chạy cùng một ví dụ ở cả IDE và terminal, rồi đảm bảo ứng dụng nhận cùng input cấu hình.

## 2. Bảng so sánh toàn cảnh

| Tiêu chí | IDE chạy trực tiếp Java main | Maven `spring-boot:run` | Gradle `bootRun` | Executable JAR `java -jar` |
|---|---|---|---|---|
| Nơi ra lệnh | Run Configuration của IDE | Terminal/IDE Maven panel | Terminal/IDE Gradle panel | Terminal/container |
| Cần source đã compile? | IDE có thể tự compile hoặc delegate trước khi chạy | Maven plugin chuẩn bị class output theo lifecycle/goal | Task graph thường chạy compile/resources prerequisites | **Cần JAR đã được đóng gói trước** |
| Classpath runtime | Class/module output và libraries mà IDE xác định | Output classes/resources và dependency Maven tương ứng | `sourceSets.main.runtimeClasspath` mặc định | Nội dung và dependency được đóng gói trong executable JAR |
| Đầu ra class thường gặp | `out/...`, `target/classes` hoặc `build/classes/...` tùy IDE delegation | `target/classes` | `build/classes/java/main` và `build/resources/main` | Bên trong JAR |
| Run Configuration | Main class, module, VM options, program args, env, cwd | Goal và plugin parameters/properties | Task, `--args`, task config, env | Java/JVM options và app arguments |
| Debug | Nút Debug và breakpoints trực tiếp | Gắn remote debugger qua JVM arguments hoặc launch config | `bootRun --debug-jvm` hoặc cấu hình debug options | `java -agentlib:jdwp=... -jar ...` |
| HotSwap/restart | IDE debugger/compilation và devtools nếu có | Recompile và devtools nếu có | Recompile và devtools nếu có | Thường không hỗ trợ vòng lặp phát triển từ classpath directory |
| Phù hợp | Sửa code, đặt breakpoint, quan sát object | Xác minh hành vi qua Maven, dùng cùng plugin ở CI | Xác minh hành vi qua Gradle, dùng task thống nhất | Kiểm thử artifact được phát hành |

**Lưu ý quan trọng:** chữ “Run từ IDE” chỉ mô tả giao diện kích hoạt. Nhiều IDE có lựa chọn **delegate build/run cho Gradle hoặc Maven**. Khi bật delegation, nhấn Run trong IDE có thể thực chất gọi task/goal của build tool. Hãy xem log Run/Build và cấu hình “Build and run using…” để biết tiến trình nào đang được dùng.

## 3. Cơ chế thực thi: compiler, classpath và JVM

### 3.1. Chạy trong IDE không có nghĩa bỏ qua build

Lớp ứng dụng vẫn phải được biên dịch thành bytecode. IDE có thể:

- Tự chạy compiler nội bộ sau khi resolve dependency Maven/Gradle.
- Gọi Maven/Gradle theo cấu hình delegation để biên dịch/chạy.
- Dùng kết quả compile còn hợp lệ từ trước nếu đã được cấu hình như vậy.

Run Configuration thường nêu **main class**, **module/classpath**, **JRE/JDK**, **VM options**, **program arguments**, **environment variables** và **working directory**. Nếu project import chưa đồng bộ với `pom.xml` hoặc `build.gradle`, classpath IDE có thể **không giống** classpath build tool.

Trong IDE, việc chọn class có `main` của `@SpringBootApplication` thường tạo launch tương đương gọi Java với classpath các class và dependency:

```text
java [JVM options] -cp [classes + resources + dependency jars]
     com.example.demo.DevRunApplication [application arguments]
```

Đây là **mô hình khái niệm**, không phải command line copy được vì `[classes + resources + dependency jars]` cần được IDE xác định và escape chính xác.

### 3.2. Maven spring-boot:run dùng class output

Spring Boot Maven Plugin có goal `spring-boot:run` để compile và chạy ứng dụng **in place**, thường theo dạng exploded classes/resources và các dependency, không cần đóng gói JAR trước:

```bash
./mvnw spring-boot:run
```

Khi ứng dụng đang chạy, goal thường giữ terminal cho đến khi bạn dừng ứng dụng bằng `Ctrl+C`. Maven Wrapper bảo đảm dùng phiên bản Maven do dự án khai báo, nếu có wrapper đúng cấu hình; plugin version đến từ POM/parent.

Đối với Maven, `spring-boot:run` là **plugin goal**, khác với Maven lifecycle phase `package`. Lệnh `./mvnw spring-boot:run` không tương đương lệnh `./mvnw package`: lệnh `package` build artifact, nhưng không mặc định khởi động server. Nếu dùng project không có Spring Boot Maven Plugin hoặc plugin không resolve được, goal sẽ lỗi.

### 3.3. Gradle bootRun dùng runtimeClasspath của source set main

Spring Boot Gradle Plugin bổ sung task `bootRun` khi thích hợp với Java plugin:

```bash
./gradlew bootRun
```

`bootRun` là task loại `BootRun`, kế thừa từ `JavaExec`. Theo mặc định, task dùng **runtime classpath của source set main**, gồm class đã compile, resource và dependency runtime. Các task cần thiết như `classes`/compile/resources được Gradle sắp xếp theo task graph. `bootRun` **không yêu cầu tạo bootJar trước**.

Gradle có theo dõi task input/output và có thể bỏ qua một số task compile khi `UP-TO-DATE`. Nhưng `bootRun` là một tác vụ khởi chạy tiến trình: việc compile được bỏ qua vì up-to-date **không có nghĩa ứng dụng không được khởi động**.

Muốn chạy từ root của multi-module build, chỉ định task đúng module:

```bash
./gradlew :orders-api:bootRun
```

Ví dụ này chỉ có nghĩa nếu `settings.gradle` đã include project `:orders-api` và plugin Boot được áp dụng trong module ấy. Đừng đoán rằng task `bootRun` luôn tồn tại ở root.

### 3.4. java -jar dùng artifact đã đóng gói

Với Maven:

```bash
./mvnw clean package
java -jar target/dev-run-demo-0.1.0-SNAPSHOT.jar
```

Với Gradle:

```bash
./gradlew bootJar
java -jar build/libs/dev-run-demo-0.1.0-SNAPSHOT.jar
```

Đường dẫn JAR là ví dụ theo group/name/version của project ở phần thực hành. File thực tế phụ thuộc `finalName`, `archiveFileName`, classifier và cấu hình plugin; xem nội dung `target/` hoặc `build/libs/` để xác nhận.

**Chỉ JAR executable do Spring Boot packaging tạo đúng cách mới chạy được theo mô hình trên.** Một JAR Java library thông thường thiếu entry point hoặc dependency runtime sẽ không tự có khả năng chạy độc lập. Trong Spring Boot, Maven `spring-boot:repackage` hoặc Gradle `bootJar` đảm nhiệm đóng gói executable archive theo cấu hình.

Một JAR đã đóng gói giữ snapshot class/resource tại lúc build. Sửa source sau khi tạo JAR **không làm file JAR cũ thay đổi**. Để quan sát sửa đổi trong `java -jar`, build lại artifact rồi khởi động lại.

## 4. Ví dụ Java 17+: một ứng dụng chạy được theo ba đường

Tạo project tên `dev-run-demo` bằng Spring Initializr, chọn Java 17 (hoặc JDK hợp lệ với phiên bản Boot dùng), Maven **hoặc** Gradle và dependency **Spring Web**. Dưới đây là các file source dùng chung; chọn **một** build tool phù hợp với project của bạn.

### 4.1. Lớp ứng dụng chính

File `src/main/java/com/example/demo/DevRunApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DevRunApplication {
    public static void main(String[] args) {
        SpringApplication.run(DevRunApplication.class, args);
    }
}
```

Đây là entry point dành cho IDE, `spring-boot:run`, `bootRun` và manifest trong executable JAR. Khi chạy mã từ IDE, chọn Run/Debug trên `DevRunApplication.main`; khi chạy Maven/Gradle, plugin có thể tự xác định main class nếu dự án có một main class phù hợp.

### 4.2. Controller quan sát cấu hình

File `src/main/java/com/example/demo/ModeController.java`:

```java
package com.example.demo;

import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ModeController {
    private final Environment environment;

    public ModeController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/mode")
    public String mode() {
        return "mode=" + environment.getProperty("app.mode", "unset");
    }
}
```

Spring inject `Environment` vào constructor vì đó là bean framework cung cấp. Controller cùng package với `DevRunApplication` nên nằm trong phạm vi component scan mặc định của `@SpringBootApplication`.

File `src/main/resources/application.properties`:

```properties
spring.application.name=dev-run-demo
app.mode=base
server.port=8080
```

File `src/main/resources/application-dev.properties`:

```properties
app.mode=dev
```

Khi **không bật profile `dev`**, HTTP response body ở endpoint `GET /mode` là:

```text
mode=base
```

Khi bật `dev`, Spring Boot nạp cấu hình profile phù hợp và giá trị `app.mode=dev` từ file profile ghi đè giá trị chung, nên response body là:

```text
mode=dev
```

Đó là **response body**, không phải toàn bộ stdout của server: startup logs còn phụ thuộc phiên bản Spring Boot, logger và cấu hình môi trường. Công cụ như `curl -s` có thể không in ký tự xuống dòng sau response.

### 4.3. Gradle Groovy DSL (chọn nếu project dùng Gradle)

`settings.gradle`:

```groovy
rootProject.name = 'dev-run-demo'
```

`build.gradle`:

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
}
```

Ở đây Spring Boot và dependency management plugin cùng được áp dụng, nên BOM phiên bản tương ứng được import và starter Web không cần version riêng. Một project thực tế có thể dùng phiên bản plugin khác phù hợp với wrapper/JDK; các version trên phục vụ tính nhất quán của ví dụ.

Chạy:

```bash
./gradlew bootRun
```

Khi server thông báo sẵn sàng, trong terminal khác:

```bash
curl -s http://localhost:8080/mode
```

Response body là `mode=base`. Sau khi dừng phiên chạy bằng `Ctrl+C`, bật profile `dev` rồi chạy lại:

```bash
./gradlew bootRun --args="--spring.profiles.active=dev"
```

Response body giờ là `mode=dev`. `--args` là **application arguments** của task `bootRun`, không phải JVM options cho Gradle daemon.

### 4.4. Maven POM (chọn nếu project dùng Maven)

`pom.xml` tối giản nhưng hoàn chỉnh cho việc chạy ví dụ:

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
    <artifactId>dev-run-demo</artifactId>
    <version>0.1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

Với cấu trúc source Java ở mục 4.1–4.2 và Maven Wrapper hợp lệ, chạy:

```bash
./mvnw spring-boot:run
```

Bật profile `dev` bằng property của **Spring Boot Maven Plugin**:

```bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=dev
```

Nếu shell hoặc Maven version có cách xử lý trích dẫn khác, đặt phần `-Dspring-boot.run.profiles=dev` trong dấu ngoặc kép. Trên Windows dùng `mvnw.cmd`. Endpoint cho phản hồi tương ứng với profile, giống đường Gradle.

**Không ghép `pom.xml` và `build.gradle` chỉ để chạy cùng ví dụ.** Một repository có thể chứa cả hai build script, nhưng người học nên chọn một cơ chế build chính và hiểu nó quyết định dependency versions, compiler và classpath.

### 4.5. Chạy cùng ví dụ trực tiếp trong IDE

Sau khi **import Maven/Gradle project** trong IDE và chờ đồng bộ dependency:

1. Chọn lớp `com.example.demo.DevRunApplication`.
2. Tạo **Application/Spring Boot Run Configuration** với main class trên và đúng module.
3. Chọn JDK tương thích, ví dụ JDK 17.
4. Đặt working directory là root project chứa `pom.xml` hoặc `build.gradle` để so sánh thuận tiện.
5. Để trống program arguments để thấy `mode=base`, hoặc thêm `--spring.profiles.active=dev` để thấy `mode=dev`.
6. Nhấn **Run** hoặc **Debug**; mở `http://localhost:8080/mode`.

Tên menu của IDE và chính sách build/delegation khác nhau theo phiên bản. Thông số quan trọng là **cấu hình thực tế**, không phải tên nút.

Dự án Java ở trên yêu cầu thư viện Spring Boot trên classpath; không thể chỉ gọi `javac DevRunApplication.java` với JDK trần. Các ví dụ `java -jar` chỉ chạy khi build đã tạo executable JAR.

## 5. Ba loại tham số rất dễ đặt nhầm chỗ

### 5.1. Application arguments

Chúng được truyền vào `String[] args` và Spring Boot xử lý những option dạng `--key=value`.

**IDE:** ô Program arguments:

```text
--spring.profiles.active=dev --server.port=8081
```

**Gradle:**

```bash
./gradlew bootRun --args="--spring.profiles.active=dev --server.port=8081"
```

**Maven:** ví dụ dùng shortcut profiles; hoặc truyền command line arguments tới Spring Boot Maven Plugin:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--server.port=8081
```

**JAR:**

```bash
java -jar build/libs/dev-run-demo-0.1.0-SNAPSHOT.jar --spring.profiles.active=dev --server.port=8081
```

Đường dẫn JAR ở lệnh cuối dành cho biến thể Gradle của bài. Nếu dùng Maven, đổi thành `target/dev-run-demo-0.1.0-SNAPSHOT.jar` sau khi package. Khi đặt `server.port=8081`, dùng `http://localhost:8081/mode`; khi không đặt, ví dụ dùng 8080.

### 5.2. JVM options

JVM options như `-Xmx512m` hoặc `-Dapp.mode=dev` được **JVM của ứng dụng** xử lý, thường đứng **trước main class hoặc trước `-jar`**:

```bash
java -Xmx512m -Dapp.mode=dev -jar build/libs/dev-run-demo-0.1.0-SNAPSHOT.jar
```

Trong IDE, điền `-Xmx512m -Dapp.mode=dev` ở **VM options**, không điền vào Program arguments. Đối với Gradle `bootRun`, có thể cấu hình:

```groovy
// Đoạn thêm vào build.gradle, trong project có Spring Boot Gradle plugin.
tasks.named('bootRun') {
    jvmArgs '-Xmx512m'
    systemProperty 'app.mode', 'dev'
}
```

Nếu muốn parameterize, đọc project property bằng `findProperty` hoặc environment variable, và tránh commit secret trong build script.

Với Maven, cần dùng tham số JVM của **Spring Boot Maven Plugin**, chẳng hạn `spring-boot.run.jvmArguments`. Đừng mặc định `MAVEN_OPTS` chỉ thay đổi JVM của ứng dụng: Maven có process riêng để chạy build và plugin có thể fork process ứng dụng.

### 5.3. Environment variables

Spring Boot có thể lấy cấu hình từ OS environment variables, ví dụ `SPRING_PROFILES_ACTIVE=dev` hoặc `APP_MODE=dev` (Spring relaxed binding chuyển biến dạng underscore thành tên property thích hợp trong ngữ cảnh này).

**IDE:** cấu hình ở mục Environment variables của Run Configuration.

**Unix/Linux/macOS (chỉ áp dụng cho lần gọi này):**

```bash
SPRING_PROFILES_ACTIVE=dev ./gradlew bootRun
```

**PowerShell:**

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
.\gradlew.bat bootRun
```

Biến môi trường PowerShell ở đây tồn tại trong phiên shell cho đến khi đổi/xóa. Khi đối chiếu kết quả, phải để IDE, shell và CI nhận cùng giá trị. Với secrets, dùng cơ chế bảo mật phù hợp; tránh in credential ra log hoặc commit chúng trong `application.properties`.

### 5.4. Bảng ánh xạ tương đương theo mục đích

| Mục tiêu | IDE Run Config | Maven plugin | Gradle task | JAR |
|---|---|---|---|---|
| Bật profile dev | Program args `--spring.profiles.active=dev` | `-Dspring-boot.run.profiles=dev` | `--args="--spring.profiles.active=dev"` | `--spring.profiles.active=dev` sau JAR |
| Đổi server port | Program args `--server.port=8081` | `-Dspring-boot.run.arguments=--server.port=8081` | `--args="--server.port=8081"` | `--server.port=8081` sau JAR |
| Đặt JVM system property | VM options `-Dapp.mode=dev` | `spring-boot.run.jvmArguments` hoặc plugin system properties | `bootRun.systemProperty(...)` | `-Dapp.mode=dev` trước `-jar` |
| Đặt heap | VM options `-Xmx512m` | Plugin `jvmArguments` | `bootRun.jvmArgs(...)` | `-Xmx512m` trước `-jar` |
| Thay môi trường | Env vars | Shell env/plugin env configuration | Shell env/`bootRun.environment` | Shell env/container env |
| Debug | IDE Debug | Remote JDWP của JVM app | `bootRun --debug-jvm` | `-agentlib:jdwp=...` trước `-jar` |

**Không trộn cờ** của Maven `-Dspring-boot.run.*` với cờ Gradle `--args`. Cũng đừng đặt `-Dspring.profiles.active=dev` vào chỗ Gradle project property với giả định nó tự trở thành property của JVM ứng dụng.

## 6. Classpath và tài nguyên: nguồn gốc của nhiều khác biệt

### 6.1. Development classpath khác packaged JAR

Trong IDE/`spring-boot:run`/`bootRun`, ứng dụng thường chạy trực tiếp từ thư mục đã biên dịch và JAR dependency:

```text
IDE (tùy delegation)   out/... hoặc target/classes hoặc build/classes/...
Maven plugin           target/classes + runtime dependencies
Gradle bootRun         build/classes/java/main + build/resources/main + runtime dependencies
Packaged Boot JAR      BOOT-INF/classes + BOOT-INF/lib trong executable JAR
```

Đường dẫn là **quy ước phổ biến**, không bảo đảm cho mọi build đã tùy chỉnh. Một file tồn tại dưới `src/main/resources` không nhất thiết đã có ở output runtime nếu việc xử lý resources chưa chạy hoặc bị exclude.

Với Spring Boot, những resource như `application.properties`, template và file static thường được lấy từ classpath. Nếu IDE copy chúng đến output khác hoặc Gradle/Maven lọc resource theo rule riêng, kết quả chạy có thể khác mặc dù code Java không đổi.

### 6.2. Dependency scope cũng ảnh hưởng

- Gradle `implementation` và `runtimeOnly` góp mặt trong runtime classpath khi phù hợp; `testImplementation` chỉ dành cho test classpath.
- Maven `compile` và `runtime` scope có vai trò runtime; `test` scope thông thường không thuộc runtime classpath của ứng dụng chính.
- IDE có thể chọn module/classpath hoặc cấu hình test runtime không như mong đợi. Nếu chỉ IDE thành công nhờ một test-only dependency, hãy sửa **dependency scope** và kiểm tra bằng build tool, không thêm thư viện thủ công trong IDE.
- Các profile Maven (build profile) và Spring profile (runtime config) là **hai khái niệm khác nhau**. `-Pdev` của Maven không có nghĩa `spring.profiles.active=dev` nếu POM không kết nối chúng; `-Pdev` của Gradle là một project property và cũng không tự bật Spring profile.

### 6.3. Working directory và đường dẫn tương đối

Một file ngoài classpath được mở bằng relative path, ví dụ:

```java
Path path = Path.of("config/local-data.csv");
```

sẽ được resolve từ **working directory của JVM**, không phải vị trí file Java. IDE có thể dùng module root trong khi terminal ở repository root; Maven/Gradle plugin có default khác hoặc đã được cấu hình. Vì vậy đường dẫn file có thể hoạt động theo một cách chạy và thất bại theo cách khác.

Để đọc tài nguyên đóng gói trong JAR, nên dùng classpath resource:

```java
try (InputStream in =
        DevRunApplication.class.getResourceAsStream("/config/template.txt")) {
    if (in == null) {
        throw new IllegalStateException("Missing classpath resource");
    }
    // Đọc byte từ InputStream; không giả định tài nguyên có File path.
}
```

Đây là **snippet minh họa** cần đặt trong method có xử lý checked exception/`IOException` phù hợp và import `InputStream`. `getResourceAsStream` hoạt động với resource đóng gói vào classpath/JAR; không nhầm tài nguyên trong JAR với file trên filesystem.

## 7. Java version, compiler options và đồng bộ project

IDE có ít nhất hai cấu hình Java dễ gây nhầm:

- **JDK của IDE dùng để build/chạy project** (project SDK, module SDK, Run Configuration JRE).
- **JDK của build tool**: Maven runtime/Toolchains hoặc Gradle daemon/toolchain.

Ví dụ Gradle `java.toolchain.languageVersion = 17` chọn compiler/toolchain phù hợp cho task; JVM chạy IDE application có thể là JDK 21 nếu Run Configuration chọn 21. Maven `maven.compiler.release=17` điều khiển target compile nhưng không tự chuyển `java -jar` sang JDK 17.

Kiểm tra tại terminal:

```bash
java -version
./mvnw -version
./gradlew --version
```

Chỉ chạy lệnh tương ứng với build tool thực sự có trong project. Trong IDE, mở settings để xem JDK Gradle/Maven và JRE của Run Configuration. Dòng `java -version` trong terminal chỉ cho biết Java mà terminal dùng, không chứng minh IDE đã chọn cùng JDK.

Nếu **IDE chạy được nhưng CI compile lỗi**, kiểm tra `--release`/`sourceCompatibility`, Java Toolchains, compiler args (`-parameters`) và annotation processor. IDE compiler có thể tạo class khác Gradle/Maven compiler khi build delegation không đồng nhất. Những thư viện dùng annotation processing (ví dụ Lombok, MapStruct) đặc biệt cần plugin và processor configuration đúng trong build file thay vì chỉ bật IDE plugin.

## 8. Debug: nút IDE và remote attach

### 8.1. Debug trực tiếp

Với IDE Run Configuration đúng main class, nhấn **Debug** để khởi chạy JVM có debugger. Đặt breakpoint trong `ModeController.mode()`, gọi `GET /mode`, quan sát `Environment`/giá trị property. Đây là đường nhanh cho tác vụ sửa bug cục bộ.

### 8.2. Gradle bootRun --debug-jvm

`bootRun` là một `JavaExec` task nên hỗ trợ:

```bash
./gradlew bootRun --debug-jvm
```

Theo cấu hình mặc định Gradle JavaExec, JVM ứng dụng dừng (suspend) và chờ debugger trên cổng **5005**. Tạo Remote JVM Debug configuration trong IDE để attach tới `localhost:5005`, sau đó gọi endpoint và kiểm tra breakpoint. Cổng và suspend có thể tùy chỉnh bằng `debugOptions` của JavaExec/BootRun khi cần.

**Phân biệt hai cờ:** `--debug-jvm` của task `bootRun` nhắm tới JVM ứng dụng, còn `-Dorg.gradle.debug=true` debug **Gradle build process/daemon**, dùng để debug build logic. Chúng không tương đương. Không công khai cổng debugger ra mạng không tin cậy.

### 8.3. Debug Maven spring-boot:run

Với Maven Boot Plugin, cấu hình JDWP cho **JVM ứng dụng** qua `spring-boot.run.jvmArguments`. Một ví dụ local-only trên JVM hỗ trợ cú pháp tương ứng:

```bash
./mvnw spring-boot:run "-Dspring-boot.run.jvmArguments=-agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005"
```

JVM sẽ chờ IDE remote debugger attach. Nếu command line parser/shell của hệ điều hành dùng quy tắc trích dẫn khác, cấu hình tham số plugin trong POM hoặc Run Configuration của IDE sẽ dễ quản lý hơn. Chỉ mở debugger cục bộ khi cần và đóng sau khi test.

### 8.4. Debug executable JAR

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=y,address=127.0.0.1:5005 \
     -jar build/libs/dev-run-demo-0.1.0-SNAPSHOT.jar
```

Trên Windows nhập lệnh một dòng (không dùng dấu `\` để xuống dòng). Khi debug artifact, dùng source code đúng version/commit đã tạo JAR để breakpoint khớp line number.

## 9. Tốc độ vòng lặp sửa code: HotSwap và Spring Boot DevTools

### 9.1. HotSwap JVM

Trong phiên Debug, IDE có thể thay bytecode của một số method mà không khởi động lại JVM. Khả năng này phụ thuộc JVM, compiler, loại thay đổi và cấu hình IDE. Các thay đổi cấu trúc class, bean registration, annotations hoặc resource thường vượt quá khả năng HotSwap thông thường.

### 9.2. Spring Boot DevTools

Nếu dự án khai báo `spring-boot-devtools`, module này có thể tự động restart ứng dụng phát triển khi phát hiện **classpath output thay đổi**. Ví dụ Gradle:

```groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
```

Với Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
```

Đây là các **đoạn bổ sung** vào build đã có dependency management Spring Boot; không phải full build files. Spring Boot Gradle Plugin định nghĩa `developmentOnly` để dependency phục vụ môi trường phát triển và mặc định không đưa vào executable archive theo cấu hình plugin. Với Maven và DevTools, kiểm tra cách plugin exclude devtools khi repackaging, mặc định có xử lý để tránh đưa devtools vào sản phẩm phát hành.

Điểm cốt lõi: **DevTools theo dõi classpath, không theo dõi trực tiếp mọi file `.java` vừa sửa**. Bạn phải cập nhật output compile để cơ chế restart phát hiện:

- Eclipse/STS có thể tự build khi lưu file tùy cấu hình.
- IntelliJ IDEA có thể cần **Build Project** hoặc bật auto-build/delegation phù hợp.
- Khi chạy `bootRun` hoặc `spring-boot:run`, có thể compile lại ở terminal/IDE khác để cập nhật classpath trong lúc phiên server còn chạy.
- Với thay đổi static resources/templates, tùy cấu hình DevTools và resource location, trình duyệt có thể reload mà không restart toàn bộ context.

**Không kết luận “Run từ IDE luôn hot reload còn Gradle không”.** Cả hai có thể dùng DevTools nếu classpath runtime có module đó, output được cập nhật và launcher hỗ trợ. Packaged production JAR không được kỳ vọng tự restart từ file source địa phương như development classpath.

### 9.3. Khi nào cần dừng và chạy lại?

Nếu cập nhật bean definitions, dependency, compiler flags, build script, Java version, runtime VM options hoặc Spring profile, thường nên **dừng tiến trình cũ rồi chạy lại** để chắc chắn classpath và cấu hình mới được áp dụng. Gradle/Maven task đang chạy không tự tái đánh giá toàn bộ build script khi source được sửa.

## 10. Chọn cách chạy cho từng mục tiêu

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Đặt breakpoint và sửa code nhanh | IDE Debug trực tiếp, module/classpath chính xác |
| Reproduce bug từ CLI mà đồng đội dễ chạy lại | `./mvnw spring-boot:run` hoặc `./gradlew bootRun` bằng wrapper |
| Kiểm tra task compile, dependency, plugin theo build chính thức | Maven/Gradle Wrapper, chạy goal/task phù hợp |
| Xác minh đóng gói, JAR manifest, resource trong archive | Build `package`/`bootJar` rồi chạy `java -jar` |
| Chạy ứng dụng multi-module | Gradle `:app-module:bootRun` hoặc Maven `-pl` phù hợp sau khi xác định module |
| Kiểm chứng cấu hình profile/port/env khác nhau | Chạy từng launcher với **cùng** app args, VM args, env, cwd |
| Tái tạo hành vi CI | Dùng wrapper, JDK/toolchain và script CI gần với môi trường CI |
| Hỏi “chạy nhanh nhất?” | IDE thường tiện cho debugging; build-tool task có thể dùng cache/incremental compile; kết quả phụ thuộc project, không có tốc độ cố định |

IDE là công cụ giao diện và debugger; Maven/Gradle là nguồn định nghĩa dependency/compiler/task. Phương án hiệu quả trong đội nhóm là giữ **cấu hình build tái lập được**, rồi dùng IDE để nâng năng suất nhưng không tạo logic bí mật chỉ tồn tại trong Run Configuration cá nhân.

## 11. Thí nghiệm đối chiếu có kiểm soát

Thực hiện trên project mục 4, trong mỗi lượt chỉ chạy **một phiên ứng dụng** tại cổng 8080.

**Lượt A – IDE mặc định.** Import project, chạy `DevRunApplication`, không bật profile và gọi `http://localhost:8080/mode`. Ghi nhận body `mode=base`.

**Lượt B – Build tool mặc định.** Dừng IDE. Dùng `./gradlew bootRun` **hoặc** `./mvnw spring-boot:run`. Gọi cùng endpoint, kỳ vọng `mode=base`.

**Lượt C – Cấu hình tương đương.** Dừng lượt B. Trong IDE chọn Program arguments `--spring.profiles.active=dev` rồi chạy; response là `mode=dev`. Dừng IDE. Chạy `./gradlew bootRun --args="--spring.profiles.active=dev"` hoặc `./mvnw spring-boot:run -Dspring-boot.run.profiles=dev`; response cũng là `mode=dev`.

**Lượt D – Artifact đã đóng gói.** Dừng server. Build JAR bằng Maven `package` hoặc Gradle `bootJar`. Chạy `java -jar <đường dẫn-jar-thực-tế> --spring.profiles.active=dev` với tên file chính xác, gọi endpoint và kỳ vọng `mode=dev`.

**Lượt E – Khác biệt có chủ đích.** Chọn profile `dev` ở IDE nhưng không chọn khi chạy CLI. Kết quả `mode=dev` và `mode=base` khác nhau là **do cấu hình đầu vào**, không phải Spring Boot tự vận hành khác trong IDE.

Điều kiện để so sánh công bằng: cùng Git commit, dependency versions, JDK tương thích, source đã compile mới, các biến môi trường quan trọng, working directory, profile, JVM options và cùng cơ sở dữ liệu/dịch vụ ngoài nếu có.

## 12. Chẩn đoán khi IDE chạy được nhưng Maven/Gradle lỗi

Làm theo thứ tự từ lỗi cụ thể đến nguồn cấu hình:

### 12.1. Lỗi compile hoặc class không tìm thấy

Triệu chứng: `package ... does not exist`, `cannot find symbol`, `ClassNotFoundException`, lỗi annotation processor.

- Xem IDE đã import/sync Maven/Gradle chưa; classpath/module có đúng không?
- Kiểm tra dependency đúng scope ở `pom.xml` hoặc `build.gradle`; tránh dependency chỉ được thêm thủ công trong IDE.
- Kiểm tra JDK/toolchain, Lombok/MapStruct processor, generated sources.
- Chạy build từ wrapper để xem lỗi compiler thật; ví dụ `./gradlew compileJava` hoặc `./mvnw compile`.
- IDE chạy bản class cũ thành công không chứng minh source mới compile đúng.

### 12.2. IDE chạy được, CLI báo thiếu môi trường

Triệu chứng: không có database URL, access token hoặc cloud credentials, Spring không resolve được placeholder.

- Kiểm tra Environment variables của IDE Run Configuration.
- Kiểm tra biến shell của terminal, properties và Spring profile ở từng launcher.
- Nếu IDE có file `.env` plugin tự nạp, shell không tự nạp file đó trong mọi hệ điều hành.
- Không copy secret vào Git để “đồng bộ” hai launcher; cấu hình secret manager/env cho từng môi trường.

### 12.3. Port already in use

Triệu chứng: `Web server failed to start. Port 8080 was already in use` hoặc exception bind tương tự.

- Thường vì phiên IDE còn chạy khi bạn khởi động `bootRun`/`spring-boot:run`.
- Dừng instance cũ hoặc dùng `--server.port=8081` cho lần chạy thứ hai.
- Kiểm tra process đang chiếm cổng trước khi kill; tránh kết luận lỗi source.
- So sánh endpoint trên đúng port đã khai báo.

### 12.4. CLI chạy được, IDE không tìm thấy main class

- Kiểm tra `main(String[] args)` và annotation `@SpringBootApplication` đã nằm trong module được chọn.
- Chọn đúng Run Configuration, module classpath và project SDK.
- Reimport/sync Gradle/Maven để IDE nhận generated sources, dependencies và compiler settings mới.
- Với multi-module, chỉ module ứng dụng mới cần Spring Boot plugin/entry point phù hợp; library module không mặc nhiên có main class.

### 12.5. Một đường chạy đọc file được, đường khác báo không thấy

- Xem working directory thực tế thay vì đoán.
- Kiểm tra file đang được mở bằng filesystem relative path hay classpath resource.
- Đảm bảo `processResources` đã chạy, resource nằm ở output/JAR và không bị exclude/filter sai.
- Nếu file nằm bên ngoài JAR, truyền đường dẫn absolute/external config tường minh khi cần triển khai.

### 12.6. Phản hồi HTTP khác dù dùng cùng source

- Đối chiếu Spring profiles, `app.mode`, property source precedence, program args, system properties, environment.
- Kiểm tra dependency graph có version khác do IDE chưa sync hoặc profile build khác.
- Kiểm tra JAR có được rebuild sau lần sửa source gần nhất.
- Kiểm tra service ngoài và database dùng ở từng môi trường, không giả định tất cả lỗi do launcher.

## 13. Phân biệt những nhầm lẫn thường gặp

**“Chạy trong IDE thì không cần Maven/Gradle.”** IDE vẫn cần thông tin build để biết dependency và compiler settings. Một số IDE còn delegate Run cho build tool.

**“`bootRun` luôn tạo JAR trước khi chạy.”** Không đúng; nó chạy từ runtime classpath của source set chính, không yêu cầu `bootJar`.

**“`spring-boot:run` là lệnh đóng gói.”** Không đúng; `package`/repackage là quy trình đóng gói. `run` nhằm khởi động in place.

**“`java -jar` là cách duy nhất để chạy đúng Spring Boot.”** Spring Boot cho phép chạy từ IDE và build plugin; các đường khác nhau chủ yếu ở cách tạo classpath/tiến trình và cấu hình.

**“Bật Spring profile dev bằng `-Pdev`.”** Đây là syntax của một số build tool (Maven profile hoặc Gradle project property), không tự tương đương `--spring.profiles.active=dev`.

**“JVM options và program args đặt đâu cũng được.”** `-Xmx`, `-D` JVM option phải đến đúng tiến trình JVM và đúng vị trí; `--spring.*` là application arguments Spring Boot xử lý.

**“DevTools cứ Save là khởi động lại.”** Nó theo dõi output classpath: cần editor/IDE/build task cập nhật class/resources thực tế.

**“Run trên IDE thấy khác CLI chắc chắn vì bug compiler.”** Profile, env, cwd, port, dependency scope và class stale là nguyên nhân phổ biến hơn; hãy đối chiếu từng đầu vào.

**“`java -jar` sau khi sửa source sẽ dùng code mới.”** JAR đã đóng gói không tự cập nhật. Phải build lại và khởi động lại.

**“Debug Gradle bằng `-Dorg.gradle.debug=true` thì breakpoint vào controller.”** Cờ này nhắm vào Gradle build process. Để debug JVM ứng dụng `bootRun`, dùng `--debug-jvm` hoặc IDE Debug/remote attach đúng process.

## 14. Checklist trước khi xác nhận hai cách chạy tương đương

1. **Build source:** cùng Git commit và không còn class/JAR cũ gây nhầm lẫn.
2. **JDK:** compiler target, Java runtime và Gradle/Maven toolchain tương thích.
3. **Classpath:** dependency đúng configuration/scope; IDE sync; không vô tình mang test dependency vào main app.
4. **Entry point:** cùng `DevRunApplication` hoặc main class cấu hình rõ ràng; trong multi-module, chọn đúng app module.
5. **Application arguments:** cùng `--spring.profiles.active`, `--server.port` và các option khác.
6. **JVM options:** cùng giá trị cần thiết như `-Xmx` và `-D...` truyền tới **JVM ứng dụng**.
7. **Environment:** cùng biến cần thiết và secret source an toàn.
8. **Working directory:** đường dẫn tương đối được resolve từ vị trí mong muốn.
9. **Resources:** `application*.properties` và resource đã được copy/đóng gói đúng, không bị filter khác.
10. **Lifecycle:** biết đang chạy IDE direct, Maven goal, Gradle task hay packaged JAR; biết cách dừng và khởi động lại.
11. **Debug/restart:** chọn đúng process; không nhầm compiler cache/HotSwap/DevTools với restart trong container.
12. **Quan sát:** đo cùng HTTP endpoint, log mức phù hợp, resolved config và test result trước khi kết luận.

### Tài liệu chính thức

- [Spring Boot 3.5 — Running Your Application](https://docs.spring.io/spring-boot/3.5/reference/using/running-your-application.html)
- [Spring Boot — Running Your Application with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/running.html)
- [Spring Boot — Running Your Application with Maven](https://docs.spring.io/spring-boot/maven-plugin/run.html)
- [Spring Boot — Developer Tools and Automatic Restart](https://docs.spring.io/spring-boot/reference/using/devtools.html)
- [Gradle JavaExec — JVM debugging](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/JavaExec.html)

**Ghi nhớ:** IDE, Maven `spring-boot:run` và Gradle `bootRun` đều có thể khởi động Spring Boot trong môi trường phát triển; điều quyết định sự tương đương là **cùng main class, classpath, JDK, profile, JVM options, environment và working directory**. `java -jar` kiểm thử đúng artifact đóng gói. Khi kết quả khác nhau, đối chiếu các yếu tố này theo thứ tự trước khi sửa code.

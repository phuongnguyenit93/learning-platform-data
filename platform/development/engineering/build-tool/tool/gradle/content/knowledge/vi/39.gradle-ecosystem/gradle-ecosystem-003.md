# Spring Boot plugin: bootRun, bootJar và ranh giới với Java plugin trong Gradle

## 1. Mục tiêu và bức tranh tổng quan

Trong một dự án Java sử dụng Gradle, `org.springframework.boot` **không thay thế** plugin `java`. Gradle Java plugin cung cấp model để biên dịch Java, chạy unit tests, tạo `jar` và tổ chức source sets. Spring Boot plugin phát hiện khi Java plugin được áp dụng và cấu hình thêm các task cần thiết cho Spring Boot application: **`bootRun`** để chạy ứng dụng trên runtime classpath, **`bootJar`** để tạo executable JAR và các conventions phục vụ development/deployment.

Bài học tập trung vào các câu hỏi:
- Task nào được tạo bởi Java plugin, task nào do Spring Boot plugin tạo?
- Vì sao `./gradlew bootRun` **không cần** `bootJar` và không tạo executable archive?
- Vì sao `./gradlew bootJar` tạo một file chạy được bằng `java -jar` mà **không** khởi động process?
- Vì sao cùng một project có `jar` (plain) và `bootJar` (executable), và khi nào dùng cái nào?
- `application`, `java-library`, `war` và `io.spring.dependency-management` tích hợp với Boot plugin ra sao?
- Tại sao không nên áp Spring Boot plugin vào mọi library module?
- Cách kiểm chứng bằng Java 17, Kotlin/Groovy DSL, JUnit, HTTP request, task graph và CI.

Ví dụ được cố định ở **Spring Boot 4.1.0** và Java 17 để người học có tài liệu tham chiếu nhất quán. Theo tài liệu Spring Boot 4.x, plugin hỗ trợ Gradle **8.x từ 8.14 trở lên** hoặc **9.x**; Java 17 là baseline tối thiểu. Khi thực hành, chọn Gradle Wrapper và dependencies tương thích với đúng phiên bản Spring Boot đã được dự án phê duyệt. Đừng coi một plugin version từ bài học là lời khẳng định đó là phiên bản mới nhất tại mọi thời điểm.

## 2. So sánh các task quan trọng

| Task | Plugin tạo hoặc cấu hình | Chức năng | Kết quả |
| --- | --- | --- | --- |
| `compileJava` | Gradle `java` | Compile source Java của `main` source set. | Class files dưới `build/classes/java/main`. |
| `processResources` | Gradle `java` | Copy resources từ `src/main/resources`. | `build/resources/main`. |
| `classes` | Gradle `java` | Lifecycle gom compile/resources. | Đầu ra từ các task phụ thuộc. |
| `compileTestJava` | Gradle `java` | Compile tests. | Test classes. |
| `test` | Gradle `java` | Chạy JUnit/TestNG tests đã cấu hình. | Test results và reports. |
| `jar` | Gradle `java` | Tạo plain JAR từ main classes/resources. | Thường `...-plain.jar` khi Boot plugin điều chỉnh classifier. |
| `bootRun` | Spring Boot + Java plugin | Chạy main class của app bằng `BootRun`/`JavaExec`. | Running Java process, không cần archive. |
| `bootJar` | Spring Boot + Java plugin | Tạo executable JAR với Boot loader/nested dependencies. | Thường `...jar` không classifier. |
| `bootTestRun` | Spring Boot + Java plugin | Chạy main class thuộc test source set. | Test-classpath application launch; không thay `test`. |
| `assemble` | Gradle Java lifecycle, Boot nối dependency | Gom artifacts. | Có Boot archive khi `bootJar` được cấu hình. |
| `build` | Gradle Java lifecycle | `assemble` + `check`/tests. | Artifacts và kết quả verification. |
| `bootWar` | Spring Boot + Gradle `war` | Tạo executable WAR. | `.war` theo Boot archive format. |
| `bootBuildImage` | Spring Boot + Java plugin | Build OCI image qua Buildpacks. | Image, cần container/buildpack prerequisites. |
| `run` | Gradle `application` | Chạy main class dưới JavaExec. | Khác Boot-specific `bootRun`. |

Tên output có thể được tùy biến bằng `archiveBaseName`, `archiveVersion`, `archiveClassifier`. Nếu bạn apply mỗi Boot plugin **không có Java plugin**, đừng giả định những task phụ thuộc `main` source set như `bootJar` đã tồn tại.

### 2.1. Sơ đồ quan hệ

```text
Gradle Java plugin
   |
   +--> sourceSets.main/test
   +--> compileJava --> classes ------> jar (plain)
   |                          |
   |                          +--------> bootJar (Boot executable)
   |                                      |
   +--> assemble -------------------------+
   +--> test --> check
   +--> build (depends on assemble and check)

Spring Boot plugin reacts when Java plugin is present:
   +--> bootRun (main runtimeClasspath + JavaExec)
   +--> bootTestRun (test runtimeClasspath)
   +--> bootJar (BOOT-INF/classes + BOOT-INF/lib)
   +--> bootBuildImage (Buildpacks)
   +--> Boot-specific configurations/conventions
```

Đây là sơ đồ khái niệm, không phải output đầy đủ của Gradle `--dry-run`. Gradle có thể bổ sung `processResources`, `resolveMainClassName`, tasks từ annotation processors/plugins khác và task avoidance outcomes.

## 3. Phản ứng của Spring Boot plugin với các plugin khác

### 3.1. Plugin Boot đứng một mình

```kotlin
plugins {
    id("org.springframework.boot") version "4.1.0"
}
```

Spring Boot plugin có ít tác động nếu không có plugin Java/JVM tương thích. Nó **không tự tạo nguồn Java compilation model** đầy đủ. Theo tài liệu Spring Boot, `bootJar` được tự động đăng ký khi Gradle `java` plugin có mặt vì task cần source set `main`, compiled outputs và runtime classpath.

### 3.2. Boot kết hợp Java plugin

```kotlin
plugins {
    java
    id("org.springframework.boot") version "4.1.0"
}
```

Khi có Gradle Java plugin, Boot:
1. Tạo `BootJar` task `bootJar` để package executable archive.
2. Nối `bootJar` vào lifecycle `assemble`.
3. Cấu hình ordinary `jar` với convention classifier `plain`.
4. Đăng ký `BootRun` task `bootRun` dùng main source set.
5. Đăng ký `bootTestRun` dùng test source set.
6. Thêm `bootBuildImage` và các configurations liên quan `bootArchives`, `developmentOnly`, `testAndDevelopmentOnly` và production runtime.
7. Cung cấp conventions cho JavaCompile, như UTF-8 khi chưa có encoding và compiler `-parameters`.
8. Tích hợp với các plugin khác khi chúng được áp dụng.

**Java plugin vẫn chịu trách nhiệm** `compileJava`, `test`, ordinary `jar`. Spring Boot không có “Spring Java compiler” thay cho `javac`.

### 3.3. Boot kết hợp war plugin

Khi có `war`, Boot tạo `bootWar` và điều chỉnh ordinary `war` classifier `plain`. Một WAR có thể chạy dưới Boot launcher hoặc được deploy lên external container nếu cấu hình đúng, nhưng cần xem Servlet API/container compatibility và `providedRuntime`.

### 3.4. Boot kết hợp application plugin

Gradle `application` tạo `run`, distributions và `application.mainClass`. Boot plugin có thể dùng cấu hình main class đó và tạo Boot-specific distributions/start scripts. **`run` và `bootRun` là hai task khác**: chúng đều có thể launch Java nhưng BootRun có runtime/startup conventions của Spring Boot.

### 3.5. Boot và dependency management

Chỉ apply `org.springframework.boot` **không tự đảm bảo mọi dependency thiếu version đều resolve được**. Có hai con đường:
- Native Gradle `platform("org.springframework.boot:spring-boot-dependencies:<version>")`.
- Apply `io.spring.dependency-management`, khi đó Boot plugin tự import BOM `spring-boot-dependencies` cùng version Spring Boot.

Chọn rõ một cơ chế và dùng thống nhất. Không âm thầm trộn version constraints khác nhau từ nhiều BOM/plugins.

## 4. Lab Spring Boot 4.1.0, Java 17 và Kotlin DSL

Bài lab tạo ứng dụng HTTP nhỏ:
- `GET /hello` trả `Hello, Gradle!`.
- `GET /hello?name=Java%2017` trả `Hello, Java 17!`.
- Formatter Java có `main` dùng standard library để chạy độc lập qua `javac/java` và xác nhận stdout chính xác.
- JUnit Jupiter test kiểm tra pure Java logic.
- Chạy app qua `bootRun` hoặc executable `bootJar` + `java -jar` để so kết quả.

### 4.1. Điều kiện và cấu trúc project

Dùng JDK 17 và Gradle Wrapper 8.14+ hoặc 9.x tương thích Boot plugin. Cần Maven Central hoặc approved mirrors để tải Spring Boot dependencies và plugin. Port 18080 cần còn trống.

```text
boot-gradle-lab/
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    ├── main/java/demo/boot/
    │   ├── DemoApplication.java
    │   ├── HelloController.java
    │   └── HelloFormatter.java
    └── test/java/demo/boot/
        └── HelloFormatterTest.java
```

Wrapper files cần tạo và commit bằng Gradle installation đáng tin, không lấy từ URL bất kỳ. Nếu phải nâng Wrapper, kiểm tra Gradle/Boot/Java version compatibility và cân nhắc `distributionSha256Sum` sau khi xác minh checksum chính thức.

### 4.2. settings.gradle.kts

```kotlin
rootProject.name = "boot-gradle-lab"
```

Plugin repositories thường gồm Gradle Plugin Portal mặc định. Nếu tổ chức có mirror, cấu hình `pluginManagement.repositories` ở Settings; `repositories { mavenCentral() }` trong build script là nơi tải Java dependencies, **không phải** Gradle plugin repository.

### 4.3. build.gradle.kts hoàn chỉnh

```kotlin
plugins {
    java
    id("org.springframework.boot") version "4.1.0"
}

group = "demo.boot"
version = "1.0.0"

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    // Native Gradle BOM: manages versions of runtime dependencies.
    implementation(
        platform("org.springframework.boot:spring-boot-dependencies:4.1.0")
    )

    // JUnit also needs managed versions on test configurations.
    testImplementation(
        platform("org.springframework.boot:spring-boot-dependencies:4.1.0")
    )

    implementation("org.springframework.boot:spring-boot-starter-webmvc")

    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

springBoot {
    mainClass.set("demo.boot.DemoApplication")
}

tasks.test {
    useJUnitPlatform()
}
```

**Phân tích DSL:**
- `plugins { java }` tạo source sets/classes/test/JAR model.
- `id("org.springframework.boot")` tạo BootRun/BootJar conventions khi Java plugin hiện diện.
- `group`/`version` giúp xác định archive name và Maven coordinates khi publish.
- Java toolchain 17 chọn compiler/launcher cho Gradle Java tasks; Gradle Daemon JVM có thể là JDK khác được hỗ trợ.
- Native BOM cung cấp versions của `spring-boot-starter-webmvc`, JUnit và dependencies liên quan. `platform` là Gradle dependency constraint mechanism; nó không yêu cầu apply `io.spring.dependency-management`.
- `springBoot.mainClass` chỉ rõ Java main class để tránh discovery ambiguity.
- `useJUnitPlatform()` cần thiết khi Gradle Test chạy JUnit Jupiter tests.
- `spring-boot-starter-webmvc` là starter Spring MVC/embedded web server phù hợp Boot 4.x. Trong các bản Boot cũ, tên `spring-boot-starter-web` phổ biến hơn; không copy tên starter theo hướng dẫn cho version khác mà bỏ qua migration.

### 4.4. src/main/java/demo/boot/DemoApplication.java

```java
package demo.boot;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`@SpringBootApplication` đưa vào Spring configuration, component scanning và auto-configuration. Đặt `HelloController` cùng package `demo.boot` để component scan nhìn thấy controller.

### 4.5. src/main/java/demo/boot/HelloFormatter.java

```java
package demo.boot;

import java.util.Objects;

public final class HelloFormatter {
    private HelloFormatter() {
    }

    public static String format(String name) {
        return "Hello, " + Objects.requireNonNull(name).strip() + "!";
    }

    public static void main(String[] args) {
        System.out.println(format(" Gradle "));
    }
}
```

Đây là **Java standard-library code chạy độc lập**. Trên JDK 17:

```bash
mkdir -p manual-out
javac --release 17 -d manual-out \
  src/main/java/demo/boot/HelloFormatter.java
java -cp manual-out demo.boot.HelloFormatter
```

Stdout **chính xác**:

```text
Hello, Gradle!
```

Lệnh này chỉ compile Java helper; **không compile Spring Boot app** vì `DemoApplication.java` cần Spring dependencies. Phân biệt rõ `javac` standalone validation với Gradle JavaCompile (được cấu hình đầy đủ classpath).

### 4.6. src/main/java/demo/boot/HelloController.java

```java
package demo.boot;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    @GetMapping("/hello")
    public String hello(
        @RequestParam(name = "name", defaultValue = "Gradle")
        String name
    ) {
        return HelloFormatter.format(name);
    }
}
```

`@RestController` trả response body. `@GetMapping` định nghĩa HTTP GET path. `@RequestParam` lấy query param `name` với default `Gradle`. String trả từ controller chính xác theo formatter; Spring Boot có thể thêm HTTP headers và startup logs, nhưng HTTP body không đổi khi input cố định.

### 4.7. src/test/java/demo/boot/HelloFormatterTest.java

```java
package demo.boot;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

public class HelloFormatterTest {
    @Test
    void trimsSpaces() {
        assertEquals(
            "Hello, Gradle!",
            HelloFormatter.format(" Gradle ")
        );
    }

    @Test
    void acceptsJavaName() {
        assertEquals(
            "Hello, Java 17!",
            HelloFormatter.format("Java 17")
        );
    }
}
```

Test này không khởi tạo Spring ApplicationContext nên nhanh. Với REST API production, thêm integration tests nếu cần kiểm tra servlet routing/security/serialization. `bootRun` khởi động server thành công **không thay** cho `./gradlew test`.

## 5. Chạy bootRun và kiểm tra HTTP

Terminal thứ nhất:

```bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean test
./gradlew bootRun --args='--server.port=18080'
```

Task `bootRun` sử dụng compiled runtime classpath; nó không cần `bootJar` chạy trước. Vì ứng dụng là web server, command `bootRun` **giữ terminal** cho đến khi bạn tắt process (Ctrl+C). Điều này là expected behavior.

Terminal thứ hai:

```bash
curl -fsS "http://localhost:18080/hello"
curl -fsS "http://localhost:18080/hello?name=Java%2017"
```

**HTTP response body của từng request**:

```text
Hello, Gradle!
Hello, Java 17!
```

Đây không phải toàn bộ stdout từ `bootRun`: Spring Boot có thể ghi banner, startup logs, port, profile và framework messages. `curl` không tự chèn newline nếu response body không có newline nên chạy hai lệnh liên tiếp có thể làm hai bodies dính cùng dòng trong terminal; trong Bash bạn có thể thêm `; printf '\n'` sau mỗi lệnh để dễ xem.

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--server.port=18080"
```

Terminal thứ hai:

```powershell
(Invoke-WebRequest -Uri "http://localhost:18080/hello").Content
```

Expected body: `Hello, Gradle!`. Khi port 18080 đã được process khác chiếm dụng, Spring Boot startup có thể fail; dùng `--server.port` khác hoặc dừng process cũ.

## 6. BootRun là JavaExec: main class, args, JVM options

### 6.1. Cơ chế

`BootRun` là subclass của Gradle `JavaExec`. Nó chạy main class từ **main source set runtime classpath** (`build/classes`, `build/resources` và runtime dependencies), cho phép truyền:
- `--args` của task/`args(...)` để truyền **application program arguments**.
- `jvmArgs(...)` cho JVM options như heap.
- `systemProperty(...)` cho Java system properties của ứng dụng.
- `environment(...)` cho biến môi trường của Java child process.
- `mainClass` và Java launcher khi muốn thay default main.
- `workingDir`, `standardInput` trong trường hợp phù hợp.

Không đánh đồng `-Pprofile=dev` với `--spring.profiles.active=dev`. `-P` là **Gradle project property**; Spring application không mặc nhiên nhận nó.

### 6.2. Truyền Spring Boot CLI args

```bash
./gradlew bootRun \
  --args='--server.port=18080 --spring.profiles.active=dev'
```

`--server.port` và `--spring.profiles.active` là Spring application properties. Chúng đi đến ứng dụng qua chương trình `main(String[] args)`. Khi đóng gói bootJar, version/profile không được “ghi nhớ” từ lần bootRun vừa chạy.

### 6.3. Truyền system property qua Gradle Property

Kotlin DSL snippet **bổ sung** (đã có `org.springframework.boot`/`java`):

```kotlin
import org.springframework.boot.gradle.tasks.run.BootRun

tasks.named<BootRun>("bootRun") {
    systemProperty(
        "demo.mode",
        providers.gradleProperty("demoMode").orElse("dev").get()
    )
}
```

Chạy:

```bash
./gradlew bootRun -PdemoMode=ci
```

Lúc đó Java application JVM có `System.getProperty("demo.mode") == "ci"`. HTTP controller lab không đọc property này, nên **không khẳng định output HTTP sẽ thay đổi**. Muốn dùng property ở Spring context, phải có application configuration tương ứng.

### 6.4. JVM options khác daemon options

```kotlin
tasks.named<BootRun>("bootRun") {
    jvmArgs("-Xms128m", "-Xmx512m")
}
```

Cấu hình này áp dụng cho **Java process của bootRun**, không mặc nhiên cho Gradle daemon. Với container production, memory policies cần thiết kế theo workload và cgroups; con số trong snippet chỉ minh họa.

### 6.5. BootRun có optimizedLaunch

BootRun có thuộc tính `optimizedLaunch` giúp tối ưu startup trong development. Có thể tắt khi debug behavior:

```kotlin
import org.springframework.boot.gradle.tasks.run.BootRun

tasks.named<BootRun>("bootRun") {
    optimizedLaunch.set(false)
}
```

Không tự cho rằng tắt nó luôn nhanh hơn/đúng hơn; chỉ thay khi có lý do chẩn đoán. Với devtools, Gradle `developmentOnly` thường chứa `spring-boot-devtools` để hỗ trợ restart/reload; compile classes vẫn cần thay đổi để devtools phát hiện.

## 7. bootJar: executable JAR độc lập với task chạy app

### 7.1. Build archive

Dừng `bootRun`, rồi:

```bash
./gradlew clean bootJar
```

Với root name `boot-gradle-lab` và project version `1.0.0`, output mặc định:

```text
build/libs/boot-gradle-lab-1.0.0.jar
```

`bootJar` tự động phụ thuộc các outputs cần thiết từ Java plugin, nhưng **không chạy server**. Nó chỉ tạo file archive.

### 7.2. Chạy đúng executable JAR

```bash
java -jar build/libs/boot-gradle-lab-1.0.0.jar \
  --server.port=18080
```

Terminal thứ hai:

```bash
curl -fsS "http://localhost:18080/hello"
```

HTTP body:

```text
Hello, Gradle!
```

Đây là **smoke test của packaged artifact**, quan trọng vì nó kiểm tra classpath layout/nested dependency loading giống deployment hơn so với `bootRun`. Java runtime dùng cho `java -jar` phải tương thích bytecode và Spring Boot runtime; `java.toolchain` trong Gradle không tự thay `java` từ shell PATH.

### 7.3. Nội dung executable Boot JAR

```text
boot-gradle-lab-1.0.0.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── demo/boot/DemoApplication.class
    │   ├── demo/boot/HelloController.class
    │   └── demo/boot/HelloFormatter.class
    ├── lib/
    │   ├── spring-boot-*.jar
    │   ├── spring-webmvc-*.jar
    │   └── ...
    └── ...
```

Đây là layout khái niệm, không phải danh sách đầy đủ runtime dependencies. `BOOT-INF/classes` chứa source main compiled outputs; `BOOT-INF/lib` chứa nested JAR dependencies. Boot loader xử lý nested archive classpath khi gọi `java -jar`.

Xem nội dung:

```bash
jar tf build/libs/boot-gradle-lab-1.0.0.jar
unzip -p build/libs/boot-gradle-lab-1.0.0.jar META-INF/MANIFEST.MF
```

`jar` đi cùng JDK; `unzip` cần cài riêng trên một số OS. Manifest Boot executable thường có launcher `Main-Class` và application `Start-Class` (`demo.boot.DemoApplication`). Không hard-code tên Boot loader class giữa các Spring Boot major versions nếu không có lý do cụ thể.

### 7.4. Vì sao java -cp BootJar không giống java -jar?

Khi chạy:

```bash
java -cp build/libs/boot-gradle-lab-1.0.0.jar \
  demo.boot.DemoApplication
```

JVM standard classpath **không tự coi `BOOT-INF/classes` là JAR root** và không giải quyết nested libraries theo Boot loader. Vì vậy invocation này có thể thất bại, dù `java -jar` cùng file chạy tốt. Đây là định dạng executable Spring Boot, không phải một “plain library JAR”.

## 8. Plain JAR từ Java plugin: vì sao -plain.jar vẫn xuất hiện?

### 8.1. Hai output tasks có mục đích khác nhau

```bash
./gradlew jar bootJar
```

Kỳ vọng với defaults của lab:

```text
build/libs/boot-gradle-lab-1.0.0-plain.jar
build/libs/boot-gradle-lab-1.0.0.jar
```

`jar` đóng gói classes/resources theo Gradle Java plugin. `bootJar` đóng gói executable Boot JAR có loader + runtime dependencies. Spring Boot plugin 4.x đặt classifier `plain` trên `jar` mặc định để hai archive không ghi trùng đường dẫn.

**`jar` không bị xóa.** Một số tài liệu Spring Boot đời cũ mô tả `jar` bị disable, nhưng không áp kết luận đó cho phiên bản 4.1 đang học.

### 8.2. Vì sao plain JAR thường không chạy bằng java -jar?

```bash
java -jar build/libs/boot-gradle-lab-1.0.0-plain.jar
```

Thông thường fail vì thiếu executable manifest hoặc runtime dependencies (tùy project), không phải Gradle Java plugin sai. Plain JAR phù hợp làm classpath artifact/library, executable JAR dành cho deployment. Nếu Java plugin tự cấu hình một `Main-Class` cho plain jar nhưng không có dependencies, vẫn không tương đương nested Boot archive.

### 8.3. Thay classifier nếu có lý do

Kotlin DSL snippet:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    archiveClassifier.set("boot")
}
tasks.named<Jar>("jar") {
    archiveClassifier.set("")
}
```

Khi đó Boot JAR thường `...-boot.jar`, ordinary Java JAR là `....jar`. Chỉ thay khi CI/artifact registry/distribution contract muốn như vậy, đồng thời cập nhật paths/script/dockerfile.

Groovy snippet:

```groovy
tasks.named('bootJar') {
    archiveClassifier = 'boot'
}
tasks.named('jar') {
    archiveClassifier = ''
}
```

### 8.4. Cẩn thận khi disable jar

```kotlin
tasks.named<Jar>("jar") {
    enabled = false
}
```

Có thể phù hợp một application project chỉ cần Boot executable, nhưng `jar` có thể được dùng bởi Java component publication, plugin khác, native-image integration hoặc multi-project dependency variants. Spring Boot docs có lưu ý không disable `jar` trong một số native-image scenarios. **Không disable mọi ordinary JAR chỉ vì nhìn thấy hai artifacts.**

## 9. Ranh giới của Java, Java Library, Application và Boot plugins

### 9.1. Java plugin làm gì?

`java`:
- Định nghĩa `main` và `test` source sets.
- Cấu hình `compileJava`, `compileTestJava`, `processResources`.
- Tạo `jar`, `javadoc`, `test` và lifecycle `assemble`, `check`, `build`.
- Cung cấp `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath`.

Không có Java plugin/source model, Spring Boot plugin không thể tự biết compiled Java application classes và dependencies theo cách trên.

### 9.2. Java Library plugin làm gì khác?

`java-library` áp dụng Java plugin và bổ sung `api`/`implementation` variant separation cho **library**. Một thư viện domain có thể được gọi từ Spring Boot nhưng **không phải một Spring Boot application**. Đừng apply Boot plugin chỉ để compile Java code trong thư viện.

### 9.3. Application plugin làm gì?

`application` thêm `run`, startup scripts và distributions; `application.mainClass` là main-class contract. Khi tích hợp Boot, Spring Boot có thể dùng main class đó làm convention cho BootRun/BootJar và thêm Boot-aware distributions. Nhưng:
- `application:run` là Gradle JavaExec.
- `bootRun` là Spring Boot BootRun.
- BootRun có Boot-specific optimizedLaunch và classpath/dev conventions.
- Không cần apply `application` chỉ để có BootRun.

### 9.4. bootWar và bootBuildImage khác bootJar

`bootWar` cần `war` plugin và servlet packaging contract. `bootBuildImage` dùng Cloud Native Buildpacks/container runtime để tạo OCI image. `bootJar` tạo executable archive, **không tự tạo Docker image**. Một `java -jar` deployment và một OCI image deployment có thể dùng artifact khác nhau nhưng build pipeline phải kiểm tra chúng rõ ràng.

## 10. Dependency management và Spring Boot BOM

### 10.1. Vì sao plugin ID khác dependency version constraints?

`org.springframework.boot` là **Gradle plugin**, resolve qua `plugins {}`/plugin repositories. `spring-boot-dependencies` là **Maven BOM**, được dùng trong Java dependency resolution. Applying plugin không đồng nghĩa tự add BOM vào tất cả configurations nếu bạn không chọn cơ chế dependency management.

### 10.2. Phương án native Gradle BOM

Trong lab:

```kotlin
dependencies {
    implementation(platform(
        "org.springframework.boot:spring-boot-dependencies:4.1.0"
    ))
    testImplementation(platform(
        "org.springframework.boot:spring-boot-dependencies:4.1.0"
    ))
}
```

`platform` đưa dependency version constraints vào configuration và các configurations kế thừa. Bạn vẫn có thể khai báo `implementation("org.springframework.boot:spring-boot-starter-webmvc")` mà không cần ghi version riêng. `enforcedPlatform` là cơ chế khác, áp version mạnh hơn và có thể gây tác dụng lan truyền; không dùng tràn lan để ép mọi dependency theo BOM.

### 10.3. Phương án dependency-management plugin

Thay native BOM bằng:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "4.1.0"
}

apply(plugin = "io.spring.dependency-management")

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webmvc")
}
```

Khi `io.spring.dependency-management` được áp dụng, Boot plugin tự import BOM của đúng version Boot plugin. Cơ chế này hỗ trợ property-based managed version customization; native Gradle BOM thường nhẹ hơn. Nếu dùng cả hai, phải hiểu rõ version precedence, không chồng constraints chỉ vì thấy hai ví dụ.

### 10.4. So dependency graph thực tế

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-boot \
  --configuration runtimeClasspath
```

Không suy đoán selected dependency version từ tên starter. Với Spring Boot 4, naming/module packaging khác một số hướng dẫn Boot 3 (ví dụ starter `webmvc`); ưu tiên đúng reference cho target release.

## 11. Groovy DSL: cùng Java project, khác syntax

Để chuyển lab, giữ nguyên Java sources và Wrapper. Chọn `settings.gradle`:

```groovy
rootProject.name = 'boot-gradle-lab'
```

Thay `build.gradle.kts` bằng `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.0'
}

group = 'demo.boot'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:4.1.0'
    )
    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:4.1.0'
    )

    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

springBoot {
    mainClass = 'demo.boot.DemoApplication'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Kết quả logic giống Kotlin DSL: compile Java 17, kiểm thử JUnit, `bootRun` chạy web app và `bootJar` tạo executable archive. Không trộn Groovy `id 'java'` vào `.gradle.kts` hoặc syntax Kotlin `id("java")` vào Groovy mà không hiểu cú pháp.

## 12. Cấu hình main class và lỗi main discovery

Spring Boot có thể tự tìm một class có `public static void main(String[])` trong output main source set. Khi project có **nhiều** main methods hoặc package/class name phức tạp, nên cấu hình explicit.

Kotlin:

```kotlin
springBoot {
    mainClass.set("demo.boot.DemoApplication")
}
```

Groovy:

```groovy
springBoot {
    mainClass = 'demo.boot.DemoApplication'
}
```

Có thể cấu hình riêng từng task:

```kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar
import org.springframework.boot.gradle.tasks.run.BootRun

tasks.named<BootJar>("bootJar") {
    mainClass.set("demo.boot.DemoApplication")
}
tasks.named<BootRun>("bootRun") {
    mainClass.set("demo.boot.DemoApplication")
}
```

Đây là **cách thay thế**, không nên tùy tiện đặt ba nơi khác nhau khiến `bootRun` và `bootJar` chạy khác main classes. Với Kotlin source file top-level `main`, JVM class name có thể mang hậu tố `Kt` (trừ `@JvmName`); với Java lab là `demo.boot.DemoApplication`.

## 13. Profile, port, external configuration

### 13.1. Runtime args không phải packaging config

```bash
./gradlew bootRun \
  --args='--server.port=18080 --spring.profiles.active=dev'
```

Khi đóng gói:

```bash
./gradlew bootJar
java -jar build/libs/boot-gradle-lab-1.0.0.jar \
  --server.port=18080 \
  --spring.profiles.active=dev
```

Cùng Boot JAR có thể chạy với nhiều profiles khác nhau. Profile `dev` không tự được bake vào archive vì bạn đã chạy bootRun với profile này.

### 13.2. application.properties và Gradle properties khác nhau

`src/main/resources/application.properties` (runtime):

```properties
spring.application.name=boot-gradle-lab
server.port=8080
```

`gradle.properties` (build):
```properties
org.gradle.caching=true
```

`--server.port=18080` truyền cho app ghi đè default port 8080 theo Spring Environment property sources. `org.gradle.caching` tác động Gradle task Build Cache, không phải Spring app property.

### 13.3. Development-only dependencies

Spring Boot plugin có `developmentOnly` cho dependencies dùng khi phát triển như Devtools. Snippet khi BOM đã cấu hình:

```kotlin
dependencies {
    developmentOnly("org.springframework.boot:spring-boot-devtools")
}
```

`developmentOnly` không được đóng vào executable JAR mặc định, giúp production runtime clean hơn. Đừng nhầm việc `bootRun` có devtools với việc `java -jar` production artifact cũng có nó.

## 14. Multi-project: application và library nên có plugin scope khác nhau

Cấu trúc:

```text
repo/
├── settings.gradle.kts
├── app/
│   ├── build.gradle.kts      # Boot application
│   └── src/main/java/...     # @SpringBootApplication
└── core/
    ├── build.gradle.kts      # Plain Java library
    └── src/main/java/...     # Shared domain/DTO/utilities
```

Root Settings:

```kotlin
rootProject.name = "boot-multi"
include(":core", ":app")
```

Core build script:

```kotlin
plugins {
    `java-library`
}
java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}
```

App build script **illustrative fragment**:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "4.1.0"
}

dependencies {
    implementation(project(":core"))
    implementation(platform(
        "org.springframework.boot:spring-boot-dependencies:4.1.0"
    ))
    implementation("org.springframework.boot:spring-boot-starter-webmvc")
}
```

Fragment này chưa có repositories/main class/test configs, nên dùng full lab ở mục 4 để làm project độc lập. Điểm quan trọng: **`:core` có ordinary `jar` và không cần Boot executable**, `:app` có `bootJar`.

Nếu áp Boot vào `:core`, `:core:bootJar` có thể báo không tìm thấy main method; `jar`/variants của core cũng bị tác động không cần thiết. Tách runnable app khỏi reusable library là architecture rõ ràng hơn.

### 14.1. Root chỉ khai báo plugin version mà chưa apply

```kotlin
plugins {
    id("org.springframework.boot") version "4.1.0" apply false
}
```

Ở `:app` có thể áp plugin không lặp version theo resolved plugin setup:

```kotlin
plugins {
    java
    id("org.springframework.boot")
}
```

Không apply Boot plugin cho mọi subproject bằng `subprojects { apply(plugin="org.springframework.boot") }` chỉ để “tiện”; dễ tạo task thừa và sai archive semantics.

## 15. Publishing: plain Java component không tự biến thành Boot JAR

`maven-publish` có hai cách khai báo artifact với ý nghĩa khác nhau.

**Java component publication**:
```kotlin
publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
        }
    }
}
```

Đây là Java component/variants model, thường nhằm **ordinary JAR** và module metadata, không đảm bảo publication là executable Boot archive.

**Boot executable publication**:
```kotlin
import org.gradle.api.publish.maven.MavenPublication

plugins {
    `maven-publish`
}

publishing {
    publications {
        create<MavenPublication>("bootJava") {
            artifact(tasks.named("bootJar"))
        }
    }
}
```

Snippet Boot publication phải gắn vào **project đã có `bootJar`** do Java + Spring Boot plugins. Nó mới khai báo publication, chưa có remote repository, nên chưa upload được gì. Trên CI release, dùng scoped credentials và immutable GAV/version policy; không đưa Maven write secrets vào PR `test` jobs.

**Quan trọng:** executable Boot JAR chứa classes trong `BOOT-INF/classes`, không phù hợp làm API/library JAR cho downstream Gradle Java consumers. Muốn chia sẻ domain code, publish `:core` từ `java-library`.

## 16. bootWar, containers và native integration

### 16.1. bootWar

Khi áp `war` plugin, Spring Boot tạo `bootWar`, có `WEB-INF/classes`/`WEB-INF/lib` và `WEB-INF/lib-provided` khi cấu hình provided runtime. WAR có thể dùng cho external servlet containers trong điều kiện tương thích. Spring Boot 4 dùng Servlet 6.x ecosystem; đừng giả định Tomcat 9/Servlet 4 của ứng dụng cũ tương thích.

### 16.2. bootBuildImage

`bootBuildImage` dùng Cloud Native Buildpacks tạo OCI image. Nó cần Docker/OCI build environment, builder image và network/registry permissions tương ứng.

```bash
./gradlew bootBuildImage
```

Chỉ chạy khi đã chuẩn bị container infrastructure và security policy. `bootJar` chỉ tạo JAR, không “âm thầm” tạo Docker image. GraalVM native executable cũng là quy trình khác.

## 17. Kiểm tra thực tế bằng Gradle commands

### 17.1. Xem task list và descriptions

```bash
./gradlew tasks --all
./gradlew help --task bootRun
./gradlew help --task bootJar
./gradlew help --task jar
```

Nếu `bootRun`/`bootJar` không tồn tại, kiểm tra đúng project module, plugin ID/version, Java plugin và lỗi configuration. `:app:bootJar` là task thuộc app project, không phải `:core:bootJar`.

### 17.2. So task graph, không chạy app

```bash
./gradlew bootRun --dry-run
./gradlew bootJar --dry-run
./gradlew build --dry-run
```

`--dry-run` liệt kê task graph dự kiến, không chạy task actions, không khởi động server và không tạo Boot JAR thực. Nó giúp chứng minh `bootRun` không bắt buộc `bootJar` trước đó, và `build` có những lifecycle tasks liên quan.

### 17.3. Xem runtime dependencies

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency spring-boot \
  --configuration runtimeClasspath
```

Dùng để xem selected versions, Boot starter và transitive libraries. Nếu versionless starter fail, xem native BOM hoặc dependency management plugin. Không mặc định chọn một Spring Framework release riêng với Boot BOM mà chưa kiểm tra compatibility.

### 17.4. So bootJar và plain jar layout

```bash
./gradlew jar bootJar
jar tf build/libs/boot-gradle-lab-1.0.0.jar
jar tf build/libs/boot-gradle-lab-1.0.0-plain.jar
```

Boot archive có `BOOT-INF` và nested libs, plain archive thường chỉ có compiled class paths ở JAR root. Đó là khác biệt **đúng theo thiết kế**, không phải duplicate bug.

## 18. Troubleshooting: lỗi hay gặp và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm chứng/sửa |
| --- | --- | --- |
| `Task 'bootJar' not found` | Chưa áp Boot/Java trong đúng project. | `tasks --all`, kiểm tra `plugins {}` và `:app:bootJar`. |
| `Task 'bootRun' not found` | Plugin reaction thiếu Java source model. | Apply `java`, kiểm tra module path. |
| `compileJava` fail | Java plugin/toolchain/dependencies. | `javaToolchains`, `--stacktrace`, Java compiler errors. |
| `bootRun` không tìm main class | Main discovery ambiguous/không có main output. | `springBoot.mainClass` và `DemoApplication.main()`. |
| `bootJar` không tìm main class | Library bị apply Boot hoặc main ở test source set. | Chọn app module đúng và explicit mainClass. |
| `java -jar ...-plain.jar` fail | Plain JAR không phải executable. | Dùng `bootJar` output không classifier. |
| `java -cp <BootJar> DemoApplication` fail | `BOOT-INF/classes` không nằm ở ordinary JAR root. | Dùng `java -jar`. |
| `bootRun` giữ terminal | Server tiếp tục listen HTTP port. | Expected; Ctrl+C khi xong. |
| `Port 8080 already in use` | Port collision. | `--args='--server.port=18080'`. |
| `curl` 404 | Mapping/component scan sai. | `@GetMapping("/hello")`, package root. |
| Java 17 class chạy sai JVM | Java toolchain vs shell Java runtime khác. | `java -version` và `javaToolchains`. |
| `Could not resolve spring-boot-starter-webmvc` | Maven repo/BOM/cache/network. | Kiểm tra `repositories` và runtimeClasspath. |
| Versionless dependency không resolve | Chưa áp BOM/dependency-management. | Chọn native `platform` hoặc DM plugin. |
| Version conflict | BOM bị override sai. | `dependencyInsight` và dependency constraints. |
| JUnit tests không chạy | Thiếu JUnit engine/launcher hoặc `useJUnitPlatform`. | Kiểm tra test deps/Test task. |
| Hai JAR trong build/libs | Plain `jar` và executable `bootJar`. | Bình thường; chọn đúng artifact. |
| CI deploy nhầm -plain.jar | Archive glob/path quá rộng. | Dùng explicit bootJar file/version và checksum. |
| `jar` bị disable gây publish failure | Java variant/module artifact cần jar. | Không disable vô điều kiện. |
| `bootBuildImage` fail | Docker/registry/builder network thiếu. | Kiểm tra container environment. |
| `bootWar` không deploy | Servlet/container API mismatch. | Kiểm tra Spring Boot 4 container requirements. |
| Devtools xuất hiện production | Không phân biệt developmentOnly/runtime. | Dùng `developmentOnly`, inspect `BOOT-INF/lib`. |
| `bootRun` và `java -jar` khác profile | Runtime args/env khác. | So `--args`, Spring config, JVM flags. |
| IDE Run pass, bootRun fail | IDE dùng classpath/JVM args khác. | Delegate Gradle run, so tools. |
| Boot plugin Gradle version lỗi | Wrapper quá cũ so với Boot. | Dùng Gradle 8.14+/9.x tương thích. |

## 19. CI verification thay vì chạy bootRun vô hạn

CI không nên gọi `bootRun` trực tiếp như một blocking build step mà không quản lý process. Thường:
1. Chạy `./gradlew clean test`.
2. Chạy `./gradlew bootJar` hoặc `./gradlew build`.
3. Kiểm tra archive path/layout và checksum.
4. Tạo một smoke-test process có timeout/port được quản lý khi cần chạy `java -jar` và assert HTTP.
5. Stop process trong teardown kể cả khi test fail.

GitHub Actions example:

```yaml
name: Spring Boot Gradle verification

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - uses: gradle/actions/setup-gradle@v4

      - name: Verify versions and Java toolchains
        run: |
          java -version
          ./gradlew --version
          ./gradlew -q javaToolchains

      - name: Test and package
        run: ./gradlew --no-daemon --console=plain clean build

      - name: Check Boot archive layout
        run: |
          jar tf build/libs/boot-gradle-lab-1.0.0.jar \
            | grep -F 'BOOT-INF/classes/demo/boot/DemoApplication.class'
```

Ví dụ chỉ minh họa verify job không có secrets; `jar tf` chưa phải full smoke test. Actions `@v4` là major refs minh họa; với pipeline thực nên pin reviewed full action commit SHAs, dependency versions, Gradle Wrapper checksum và publication permissions. Không dùng `bootJar` success làm bằng chứng HTTP server chạy production nếu chưa smoke test runtime.

## 20. Các nguyên tắc lựa chọn plugin và task

1. Gradle Java plugin làm source model/compilation/tests/ordinary JAR.
2. Spring Boot plugin mở rộng Java model cho application run/packaging, không thay Gradle.
3. `bootRun` cho development runtime, `bootJar` cho executable deployment artifact.
4. `bootRun` không cần `bootJar`; `bootJar` không tự khởi động app.
5. `jar` plain không tương đương `bootJar`; phân biệt classifier và nested layout.
6. Chọn `java-library` cho core reusable code, chỉ apply Boot ở runnable app modules.
7. Không apply `application` chỉ để có `bootRun`; dùng khi cần `run`/distributions riêng.
8. Dùng native BOM `platform` hoặc dependency-management plugin nhất quán.
9. Chốt Java toolchain và Gradle Wrapper phù hợp Spring Boot version.
10. Test qua Gradle `test`/`check` và verify HTTP endpoint khi cần, không dựa vào startup logs.
11. Đừng disable ordinary `jar` khi chưa xem multi-project/publication/native-image consumers.
12. Publish executable Boot archive bằng artifact(task bootJar) khi thật sự muốn, không nhầm với Java component.
13. Dùng `--dry-run`, `tasks --all`, `dependencyInsight` và inspect JAR manifest trước khi kết luận plugin lỗi.
14. Tách runtime profile/secrets khỏi packaging; dùng environment và least-privilege CI credentials.
15. Khi migrate Boot 3 → 4, kiểm tra starter naming, Gradle/JDK compatibility, Servlet API, launcher, BOM và plugins.

## 21. Câu hỏi tự kiểm tra

1. **Ai tạo `compileJava`?** — Gradle Java plugin.
2. **Ai tạo `bootJar`?** — Spring Boot plugin khi Java plugin có mặt.
3. **`bootRun` kế thừa từ loại task nào?** — `BootRun` là subclass của `JavaExec`.
4. **`bootRun` có bắt buộc tạo Boot JAR?** — Không.
5. **`bootJar` có khởi động server?** — Không, nó tạo file executable.
6. **`java -jar` nên dùng file nào?** — Boot executable JAR, không phải plain JAR.
7. **`bootJar` chứa application classes ở đâu?** — `BOOT-INF/classes`.
8. **Runtime dependencies nằm đâu?** — `BOOT-INF/lib`.
9. **Vì sao ordinary `jar` có classifier `plain`?** — Tránh trùng file output với Boot JAR.
10. **`build` có thể tạo bootJar?** — Có, vì Boot nối task vào `assemble` khi Java plugin hiện diện.
11. **Chỉ apply Boot plugin đã có BOM management chưa?** — Cần native platform hoặc dependency-management plugin.
12. **Có cần Boot plugin ở core library module?** — Thường không.
13. **`application:run` và `bootRun` luôn giống nhau?** — Không.
14. **`bootBuildImage` có phải `bootJar`?** — Không; nó build OCI image qua Buildpacks.
15. **Java toolchain 17 có ép CLI `java` thành 17 không?** — Không.
16. **`from(components["java"])` có chắc publish bootJar không?** — Không; dùng `artifact(tasks.named("bootJar"))` khi có chủ đích.
17. **Dùng `--args` hay `-P` để truyền server.port?** — `--args='--server.port=...'` truyền Spring application args.
18. **Một service chạy qua bootRun pass đã chứng minh CI tests pass?** — Không; cần `test`/`check`.

**Kết luận:** Spring Boot plugin **xây trên** Gradle Java plugin. Java plugin cung cấp compilation, tests, source sets và ordinary JAR; Boot plugin phát hiện Java model rồi bổ sung `bootRun` để chạy application trên runtime classpath và `bootJar` để tạo executable archive với loader/nested dependencies. Khi phân biệt rõ hai trách nhiệm này, ta dễ chọn task cho local dev/CI/deployment, tránh nhầm plain vs executable JAR, cấu hình dependency management đúng và giữ library modules sạch khỏi application-specific build logic.

### Tài liệu chính thức

- [Spring Boot Gradle Plugin — Getting Started](https://docs.spring.io/spring-boot/gradle-plugin/getting-started.html): plugin `org.springframework.boot` và Java plugin integration.
- [Spring Boot Gradle Plugin — Reacting to Other Plugins](https://docs.spring.io/spring-boot/gradle-plugin/reacting.html): task/convention creation khi áp Java, War, Application, Kotlin và dependency management.
- [Spring Boot Gradle Plugin — Running with Gradle](https://docs.spring.io/spring-boot/gradle-plugin/running.html): BootRun, `--args`, JavaExec options, devtools.
- [Spring Boot Gradle Plugin — Packaging](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html): executable/plain JARs, nested archive layout, main class, layers.
- [Spring Boot Gradle Plugin — Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html): native BOM/platform, dependency-management plugin.
- [Spring Boot Gradle Plugin — Publishing](https://docs.spring.io/spring-boot/gradle-plugin/publishing.html): publish Boot executable artifact với Maven Publish.
- [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): Java/Gradle/Servlet compatibility.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): source sets, compileJava, jar, test, assemble.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): api/implementation separation và library variants.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): `run` và distributions.
- [Gradle — Platforms](https://docs.gradle.org/current/userguide/platforms.html): native BOM/constraints.
- [Gradle — Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): uniform Gradle distribution trong IDE/CI.

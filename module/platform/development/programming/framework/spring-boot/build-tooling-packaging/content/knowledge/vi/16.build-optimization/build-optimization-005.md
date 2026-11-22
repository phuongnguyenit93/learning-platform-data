# Sử dụng Configuration Cache khi các plugin tương thích trong Spring Boot và Gradle

## 1. Configuration Cache giải quyết bài toán nào?

Một dự án Spring Boot dùng Gradle thường có nhiều plugin, dependencies, cấu hình Java toolchain, kiểm thử, đóng gói `bootJar` và đôi khi nhiều module. Mỗi lần chạy `./gradlew test` hoặc `./gradlew bootJar`, Gradle phải xác định build, đọc cấu hình và dựng task graph trước khi thực thi task. Ở repository lớn, **configuration phase** có thể mất thời gian dù source không thay đổi.

**Configuration Cache** lưu lại kết quả của configuration phase: những task đã chọn, trạng thái cấu hình của chúng, dependency và dữ liệu cần thiết để thực thi. Khi lần chạy sau yêu cầu cùng tập task và input cấu hình vẫn hợp lệ, Gradle có thể **khôi phục đồ thị công việc, bỏ qua việc đánh giá lại các build scripts và plugin configuration**.

Đây **không phải** cơ chế bỏ qua unit test, compile hay scan bảo mật. Nó chỉ tránh công việc cấu hình lặp lại; các task vẫn được Gradle kiểm tra input/output và có thể chạy lại nếu source hoặc dữ liệu đầu vào thay đổi.

Mục tiêu của bài:

1. Hiểu Configuration Cache khác Build Cache, incremental compilation, daemon và trạng thái `UP-TO-DATE`.
2. Bật thử bằng `--configuration-cache`, xem log **stored → reused**, sau đó mới bật mặc định ở `gradle.properties`.
3. Kiểm tra compatibility với Spring Boot Gradle Plugin, các plugin thứ ba và custom tasks; không suy đoán việc plugin tồn tại đồng nghĩa mọi task đã tương thích.
4. Nhận diện lỗi `Project` được đọc ở execution time, các biến môi trường, script listeners, side effects và task state không thể lưu.
5. Sửa task bằng `Provider`, property rõ ràng và Gradle services; dùng `notCompatibleWithConfigurationCache` khi cần ngoại lệ có kiểm soát.
6. Đo lường lợi ích thật, áp dụng cho multi-module/CI và bảo vệ dữ liệu cache.

**Phiên bản minh họa:** Java 17, Spring Boot Gradle Plugin `3.5.16`, Gradle Wrapper `8.14.3`. Tài liệu “Gradle current” vào các thời điểm khác có thể mô tả Gradle 9.x hoặc 10.x; **không tự nâng Wrapper lên major version mới** trước khi xác nhận tương thích với Spring Boot và các plugin đang dùng.

## 2. Hiểu rõ ba pha build

```text
./gradlew test
       |
       v
INITIALIZATION
- Xác định settings.gradle và các subprojects
       |
       v
CONFIGURATION
- Áp dụng plugins
- Đọc build.gradle / build.gradle.kts
- Cấu hình tasks, dependencies và execution graph
       |
       v
EXECUTION
- compileJava, processResources, test...
- Task có thể EXECUTED / UP-TO-DATE / FROM-CACHE
```

Không có Configuration Cache, Gradle đánh giá lại cấu hình ở các invocation. Khi cache bật:

```text
Lần A: ./gradlew test --configuration-cache
    -> không có entry hợp lệ
    -> configuration chạy và snapshot task graph được lưu
    -> thực thi test graph

Lần B: ./gradlew test --configuration-cache
    -> cùng task request, input cấu hình phù hợp
    -> khôi phục configuration cache entry
    -> bỏ qua configuration phase
    -> thực thi test graph đã được khôi phục
```

Initialization vẫn có phần việc xác định build/cache entry. **Configuration phase** mới là phần chủ yếu được bỏ qua khi hit. Các task trong execution không tự biến mất: nếu `GreetingService.java` thay đổi, `compileJava` và `test` có thể cần chạy lại dù configuration cache reused.

### 2.1. Khác nhau giữa các cache

| Cơ chế | Điều được tái sử dụng | Dấu hiệu | Không nên hiểu nhầm |
|---|---|---|---|
| **Configuration Cache** | Task graph và state sau configuration | `Configuration cache entry stored/reused` | Không lưu output test/compile thay Build Cache |
| **Build Cache** | Output của task/transform đã khai báo inputs đúng | `FROM-CACHE` | Không tự bỏ qua configuration |
| **Up-to-date check** | Output hiện có khớp trạng thái input của task | `UP-TO-DATE` | Không có nghĩa configuration cache hit |
| **Incremental compile** | Chỉ biên dịch phần source bị ảnh hưởng khi compiler hỗ trợ | Task compile vẫn chạy, có thể làm ít việc hơn | Không tạo task graph cache |
| **Gradle daemon** | JVM Gradle sống lâu, giảm startup overhead | Reuse daemon | Không đồng nghĩa reuse configuration |

Hai thuộc tính độc lập:

```properties
# gradle.properties (chỉ bật ở repo sau khi đã xác minh):
org.gradle.configuration-cache=true
org.gradle.caching=true
```

Thuộc tính đầu dành cho **configuration**; thuộc tính sau dành cho **task output Build Cache**. Cả hai có thể kết hợp, nhưng mỗi cơ chế có điều kiện và chi phí riêng. `--offline` cũng không phải công tắc Configuration Cache: nó chỉ thay đổi chính sách truy cập repository.

## 3. Khi nào nên bật: kiểm tra điều kiện và plugin

Theo tài liệu chính thức, **Spring Boot Gradle Plugin 3.5** có thể sử dụng với Configuration Cache. Dòng plugin 3.5 công bố hỗ trợ Gradle **7.6.4+ trong dòng 7.x**, hoặc **8.4+ trong dòng 8.x**. Tài liệu đó **không bảo đảm** mọi tổ hợp Spring Boot 3.5 với Gradle 9.x hay mọi plugin bên thứ ba đều phù hợp.

Trước khi quyết định bật mặc định:

- Đọc phiên bản wrapper bằng `./gradlew --version` và `gradle/wrapper/gradle-wrapper.properties`.
- Xác nhận Java version và Java toolchain; phân biệt JDK chạy Gradle và JDK compiler/test.
- Kiểm kê plugin trong `settings.gradle`, `build.gradle`, từng subproject và convention plugins, gồm plugin quality/test/generate/publish/container.
- Xem tài liệu compatibility của **đúng version plugin**, không chỉ của plugin ID.
- Kiểm tra cả custom task trong `buildSrc`, `build-logic` và những đoạn `doFirst`/`doLast`.
- Thử những task **thực sự dùng trong nhóm**: `help`, `test`, `check`, `bootJar`, `bootRun`, `publish` nếu có.
- So sánh test results/artifact thực tế khi bật và tắt Configuration Cache.

Một build có thể có `help` tương thích nhưng task code generation không tương thích vì chỉ khi execution Gradle mới chạm tới `Project`/`Gradle` live object. Compatibility là thuộc tính **của build logic và task graph trong một invocation**, không phải một huy hiệu gắn vĩnh viễn lên repository.

Một số core plugin Java/Java Library đã hỗ trợ Configuration Cache tốt, nhưng điều đó **không suy ra** một plugin code generation hoặc plugin custom mà công ty tự viết đã tương thích.

## 4. Bật thử bằng command line trước khi chỉnh repository

### 4.1. Lần thử đầu tiên: help

Chạy từ thư mục root có Gradle Wrapper:

```bash
./gradlew help --configuration-cache
```

Trên Windows:

```powershell
.\gradlew.bat help --configuration-cache
```

`help` là task đầu tiên thường được Gradle khuyến nghị khi bắt đầu adoption: nó chạy configuration nhưng rất ít execution. Nếu chưa có entry hợp lệ, log có thể có dạng:

```text
Calculating task graph as no cached configuration is available for tasks: help
...
Configuration cache entry stored.
```

Chạy lại **cùng lệnh**:

```bash
./gradlew help --configuration-cache
```

Khi input phù hợp và graph tương thích, log có thể hiển thị:

```text
Reusing configuration cache.
...
Configuration cache entry reused.
```

Đó là dấu hiệu trực tiếp cache hit. Câu chữ và vị trí dòng log tùy version Gradle, nhưng **stored/reused** là điều cần quan sát. Nếu báo **discarded** hoặc link đến `configuration-cache-report.html`, chưa đạt điều kiện.

### 4.2. Thử task thật hai lần

```bash
./gradlew test --configuration-cache
./gradlew test --configuration-cache

./gradlew bootJar --configuration-cache
./gradlew bootJar --configuration-cache
```

Mỗi **task request** có thể dùng cache entry khác. `help` reuse **không bảo đảm** `bootJar` reuse ngay vì đó là graph khác. Nếu task đang `UP-TO-DATE` thì vẫn đánh giá khả năng reuse configuration bình thường; đừng chỉ dựa vào dòng `UP-TO-DATE`.

### 4.3. Bật mặc định sau khi đã qua kiểm tra

File `gradle.properties` ở root:

```properties
org.gradle.configuration-cache=true
```

Từ đó gọi `./gradlew test` hoặc `./gradlew bootJar` là đủ. Khi team commit thuộc tính này, các lệnh Gradle từ developer và CI có thể cùng dùng Configuration Cache; đó là lý do phải xác minh plugin/task trước khi bật đại trà.

Tắt riêng một invocation, ví dụ khi plugin publish đang lỗi:

```bash
./gradlew publish --no-configuration-cache
```

Lệnh này vẫn thực hiện task, chỉ bỏ qua cơ chế Configuration Cache trong lần chạy đó. Không cần xóa toàn bộ cache trên đĩa để tắt tính năng tạm thời.

**Không nên bật `org.gradle.configuration-cache.problems=warn` lâu dài**: warning mode có thể lưu/khôi phục serialized state thiếu hoặc sai trong khi build có incompatibility. Nên sửa nguyên nhân hoặc đánh dấu task cụ thể chưa tương thích.

## 5. Một Spring Boot Java 17 project có thể thực hành

Ví dụ dùng **Gradle Groovy DSL** và chọn **native Gradle platform** để import Spring Boot BOM, do đó chỉ cần Java plugin và Spring Boot Gradle Plugin. Việc dùng native BOM **không có nghĩa** các dự án đang dùng `io.spring.dependency-management` phải bỏ plugin đó ngay; hãy thử compatibility của tổ hợp plugin đang có trước khi thiết kế lại dependency management.

### 5.1. Cây thư mục

```text
cc-demo/
├── settings.gradle
├── build.gradle
├── gradle.properties
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/cc/
    │   ├── CcApplication.java
    │   └── GreetingService.java
    └── test/java/com/example/cc/
        └── GreetingServiceTest.java
```

Wrapper scripts/JAR phải được tạo từ Gradle hoặc Spring Initializr và commit đúng, **không thể chỉ tạo file rỗng có tên như sơ đồ**.

### 5.2. File settings.gradle

```groovy
rootProject.name = 'cc-demo'
```

### 5.3. File build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )
    testImplementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )

    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Giải thích:

- `java` cung cấp compiler/test tasks, `org.springframework.boot` cung cấp `bootJar`/`bootRun` khi dùng cùng Java plugin.
- `SpringBootPlugin.BOM_COORDINATES` cung cấp BOM phù hợp version Spring Boot plugin; `platform(...)` cho Gradle dependency constraints nên không cần version thủ công cho starter.
- `java.toolchain` chọn Java 17 cho compiler/test phù hợp; nếu JDK chưa được cài hoặc toolchain resolver chưa cấu hình, build có thể lỗi **trước khi xét Configuration Cache**.
- `testRuntimeOnly` chứa JUnit Platform launcher phù hợp với test dependency.
- Không có plugin `configuration-cache` vì đây là tính năng sẵn của Gradle.

`gradle/wrapper/gradle-wrapper.properties` có thể có dòng:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.14.3-bin.zip
```

Đây chỉ là trường liên quan trong file wrapper; project thật có thể có thêm checksum/timeout/path properties. Dùng Wrapper 8.x tương thích với Spring Boot 3.5 trong ví dụ; không tự đổi version sang Gradle 9+ mà chưa kiểm chứng plugin matrix.

### 5.4. Application class

File `src/main/java/com/example/cc/CcApplication.java`:

```java
package com.example.cc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CcApplication {
    public static void main(String[] args) {
        SpringApplication.run(CcApplication.class, args);
    }
}
```

Dùng `spring-boot-starter` cơ bản, không có embedded web server; khi chạy executable JAR, Spring context khởi động rồi tiến trình thường kết thúc nếu không có thread/task chạy nền.

### 5.5. Logic Java thuần

File `src/main/java/com/example/cc/GreetingService.java`:

```java
package com.example.cc;

public final class GreetingService {
    public String greet(String name) {
        return "Xin chào, " + name;
    }
}
```

### 5.6. JUnit test

File `src/test/java/com/example/cc/GreetingServiceTest.java`:

```java
package com.example.cc;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

class GreetingServiceTest {
    @Test
    void greetsByName() {
        assertEquals("Xin chào, Java",
                new GreetingService().greet("Java"));
    }
}
```

Các file Java cần classpath từ Spring Boot/JUnit do Gradle resolve; `javac` trần không thể compile `CcApplication.java` hoặc `GreetingServiceTest.java` nếu không cung cấp dependency. Source ở đây là chương trình/test có thể build qua script Gradle trên.

### 5.7. Kiểm chứng chạy build

```bash
# Baseline với cache tắt
./gradlew clean test
./gradlew bootJar

# Kiểm tra Configuration Cache:
./gradlew help --configuration-cache
./gradlew help --configuration-cache
./gradlew test --configuration-cache
./gradlew test --configuration-cache
./gradlew bootJar --configuration-cache
./gradlew bootJar --configuration-cache

# Khởi chạy artifact vừa đóng gói
java -jar build/libs/cc-demo-0.1.0-SNAPSHOT.jar
```

Tên JAR mặc định dựa trên root project name và version; nếu build đổi archive name, phải kiểm tra `build/libs` trước. `java -jar` là bước kiểm thử ứng dụng, **không** có cờ Configuration Cache, vì cache áp dụng cho Gradle build process chứ không phải runtime JVM của app.

Không có stdout cố định của `test` ngoài báo cáo mà Gradle tạo; quan sát **BUILD SUCCESSFUL**, test results và dòng cache **stored/reused**. Đừng kết luận cache hit chỉ vì task compile hiện `UP-TO-DATE`.

## 6. Dự án Kotlin DSL: cú pháp tương đương

Nếu dùng `settings.gradle.kts`:

```kotlin
rootProject.name = "cc-demo"
```

Và `build.gradle.kts`:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
}

group = "com.example"
version = "0.1.0-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation(platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    ))
    testImplementation(platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    ))

    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
```

Code Java và các lệnh `gradlew` không thay đổi. **Đừng copy cú pháp Groovy** như `id 'java'` hoặc `implementation '...'` vào file `.kts`; không cần tạo cả `build.gradle` lẫn `build.gradle.kts` trong cùng module để thử cache.

## 7. Điều kiện cache hit, miss, invalidation

Gradle tạo/kiểm tra entry theo task request và những input ảnh hưởng configuration. Các yếu tố **có thể** gây miss:

- Chạy task khác hoặc tập task/arguments khác, ví dụ `help` so với `test`, hoặc `test` so với `clean test`.
- Thay `settings.gradle(.kts)`, `build.gradle(.kts)`, `gradle.properties`, init script hoặc convention plugin code.
- Thay version plugin, Gradle Wrapper hoặc build logic classpath.
- Thay Gradle/system properties, environment variables hoặc file được build logic **đọc ở configuration time**.
- Entry không còn hợp lệ, bị xóa hoặc chưa tồn tại cho task graph đó.

Khi đọc một thuộc tính ở configuration, Gradle có thể đưa nó vào configuration fingerprint. Ví dụ nếu build script dùng `providers.gradleProperty('build.mode').get()` để chọn tasks trong configuration, đổi `-Pbuild.mode=...` có thể invalidate entry. **Không suy ra tất cả các giá trị `-P` đều gây miss**, vì còn tùy chúng có được dùng khi cấu hình hay không.

### 7.1. Sửa source có gây cache miss không?

**Không nhất thiết.** Nếu chỉ sửa một method trong `GreetingService.java` mà không thay build logic, Gradle vẫn có thể reuse configuration và chạy lại `compileJava`/`test` do inputs của task thay đổi. Đây là hành vi đúng: reuse cấu hình **không che mất source changes**.

### 7.2. Configuration Cache nằm ở đâu?

Cache cục bộ của project thường nằm trong:

```text
<root-build>/.gradle/configuration-cache/
```

Nó khác `build/` (task outputs), khác Gradle User Home cache và không phải nơi giữ Maven artifacts. `./gradlew clean` xóa outputs của build, **không được coi là lệnh xóa Configuration Cache**. Chỉ xóa chính xác thư mục cache nếu đã xác định cần chẩn đoán lỗi state, đã đóng những Gradle build còn dùng cache, và đang ở đúng checkout. Không đưa một lệnh xóa toàn bộ `.gradle` không kiểm tra vào script CI.

## 8. Những task cần thử ngoài help

| Task | Vì sao cần kiểm tra |
|---|---|
| `help` | Phát hiện nhanh lỗi configuration chung của plugin/build script |
| `test` | Test plugins, JVM args, coverage agents, custom listeners, Java toolchains |
| `check` | Ngoài test có thể kéo PMD, Checkstyle, Spotless hoặc các quality tasks |
| `bootJar` | Spring Boot packaging, manifest, custom archive configuration |
| `bootWar` | WAR plugin và providedRuntime, chỉ khi project có task |
| `bootRun` | JavaExec/BootRun, system properties, devtools/run customization |
| `publish` | Publish plugin, signing, credentials và custom upload tasks |
| `:module:integrationTest` | Custom test suites và inputs/outputs, database fixtures |

**Không chỉ kiểm tra `help`.** Một plugin có thể cấu hình thành công, nhưng khi task của nó xuất hiện trong graph mới gây Configuration Cache problem. Vì thế gọi **mỗi task thực tế hai lần**, ghi nhận lần thứ nhất stored và lần thứ hai reused, sau đó xác nhận outputs, test reports và artifact đúng.

`bootRun` có thể khởi động một server giữ terminal cho đến khi dừng; cần test với quy trình khởi động/dừng có kiểm soát, không gọi liên tiếp hai phiên ứng dụng trên cùng cổng rồi kết luận plugin lỗi vì “Port already in use”.

## 9. Anti-pattern quan trọng: dùng Project trong task action

Task action chạy **trong execution phase**. Lúc đó, đối tượng model như `Project`, `Gradle` hay `Settings` không được dùng tự do như ở configuration, vì chúng không phải dạng state an toàn để serialize/khôi phục trong Configuration Cache.

### 9.1. Ví dụ cố tình sai

Đoạn thêm vào `build.gradle` Groovy:

```groovy
tasks.register('showBad') {
    doLast {
        println 'Project = ' + project.name
    }
}
```

Chạy:

```bash
./gradlew showBad --configuration-cache
```

Gradle có thể báo lỗi liên quan:

```text
Invocation of 'Task.project' by task ':showBad'
at execution time is unsupported with the configuration cache.
```

Đây là **ví dụ gây lỗi có chủ đích**, chỉ chạy ở nhánh thử nghiệm. Không dùng nó trong build sản xuất.

### 9.2. Sửa bằng cách chụp dữ liệu đơn giản tại configuration time

```groovy
tasks.register('showName') {
    def capturedName = project.name
    doLast {
        println 'Project = ' + capturedName
    }
}
```

`capturedName` là **chuỗi**, được lấy trong phần cấu hình task; action không truy cập đối tượng `Project`. Với `rootProject.name = 'cc-demo'`, stdout do task in:

```text
Project = cc-demo
```

Có thể chạy `./gradlew showName --configuration-cache` hai lần để kiểm tra stored/reused. Với biến khác, tránh capture cả build script instance từ scope ngoài task; ghi thành local value trong task configuration hoặc dùng typed property.

## 10. Typed task + Property/Provider: phương án bền vững

### 10.1. Custom Gradle task bằng Groovy DSL

Đặt đoạn này trong `build.gradle` của project (các import có thể đặt ở đầu script); đây là **đoạn bổ sung**, không phải full build file:

```groovy
import org.gradle.api.DefaultTask
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.TaskAction

abstract class PrintMessageTask extends DefaultTask {
    @Input
    abstract Property<String> getMessage()

    @TaskAction
    void printMessage() {
        logger.lifecycle('message=' + message.get())
    }
}

tasks.register('printMessage', PrintMessageTask) {
    message.set(providers.gradleProperty('demo.message').orElse('hello'))
}
```

`Property<String>` do Gradle quản lý, `@Input` khai báo giá trị input của task, `providers.gradleProperty(...)` kết nối dữ liệu mà không cần tìm kiếm toàn bộ Gradle properties ở configuration time. `@TaskAction` không đọc `Project` live object.

Chạy:

```bash
./gradlew printMessage --configuration-cache
./gradlew printMessage --configuration-cache
./gradlew printMessage --configuration-cache -Pdemo.message=bonjour
```

Stdout từ riêng task là `message=hello` cho hai lệnh đầu và `message=bonjour` cho lệnh cuối. Vì property được nối lazy qua Provider, thay đổi giá trị có thể không bắt buộc invalidation configuration entry, nhưng task vẫn thấy giá trị mới khi chạy; kết luận cuối cùng phụ thuộc task request và các input khác của build.

### 10.2. Custom task bằng Kotlin DSL

Bản tương đương trong `build.gradle.kts`:

```kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.TaskAction

abstract class PrintMessageTask : DefaultTask() {
    @get:Input
    abstract val message: Property<String>

    @TaskAction
    fun printMessage() {
        logger.lifecycle("message=" + message.get())
    }
}

tasks.register<PrintMessageTask>("printMessage") {
    message.set(providers.gradleProperty("demo.message").orElse("hello"))
}
```

Đây là phần thay thế theo **Kotlin DSL**, không được chèn cả hai class Groovy/Kotlin vào cùng project.

### 10.3. Khi task tạo output file

Với task đọc file rồi sinh tài nguyên (manifest JSON, generated code, schema, package metadata), còn cần:

- `@InputFile` / `@InputFiles` cho source files.
- `@OutputFile` / `@OutputDirectory` cho output.
- `@Input` cho scalar settings.
- Normalization/path sensitivity nếu file input phụ thuộc đường dẫn.
- Service `FileSystemOperations` hoặc API phù hợp thay vì `project.copy` trong task action.
- Provider output task này làm input task kia để Gradle suy ra dependency.

**Configuration Cache compatibility ≠ task cacheability ≠ correctness.** Một task có thể serialize được nhưng vẫn tạo output sai nếu dùng input ẩn, đọc môi trường không khai báo hoặc ghi vào cùng file với task khác.

## 11. Các anti-pattern và cách xử lý

| Mẫu dễ gây vấn đề | Vì sao | Phương án tốt hơn |
|---|---|---|
| `doLast { project.copy { ... } }` | Dùng Project model trong execution | Inject `FileSystemOperations` vào typed task |
| `doLast { println project.version }` | Truy cập project tại task action | Chụp giá trị ở configuration hoặc lưu property typed |
| Task lưu field kiểu `Project`/`Gradle`/`Configuration` | State sống, không phù hợp serialize | Thay bằng Property, Provider, file collection hoặc injected Gradle services |
| `gradle.taskGraph.whenReady { ... }` để cấu hình muộn | Callback configuration không chạy lại như cũ khi CC hit | `tasks.named`, `configureEach`, Providers và task dependencies |
| Đọc mọi `System.getenv()` ở configuration | Rất nhiều biến trở thành input cấu hình | `providers.environmentVariable('KEY')` cho đúng biến cần |
| `"git ...".execute()` trong configuration | External process/side effect khó theo dõi | `providers.exec`/`ValueSource` hoặc truyền dữ liệu qua CI |
| Ghi file từ top-level `build.gradle` | Side effect không lặp trên cache hit | Tạo task có `@OutputFile` và `@TaskAction` |
| Task cùng ghi chung output mà không có dependency | Có race và output nondeterministic | Định nghĩa input/output và dependency graph rõ |
| Bật `problems=warn` vĩnh viễn | Cache state lỗi có thể được reuse | Sửa nguyên nhân hoặc đánh dấu task cụ thể incompatible |
| Không pin plugin/Wrapper versions | Nâng bản mới làm thay hành vi và compatibility | Pin version và kiểm thử lại từng lần nâng |
| Nghĩ task `UP-TO-DATE` là CC hit | Hai cơ chế khác nhau | Đọc log CC stored/reused |
| Chỉ kiểm tra `help` | Không thử execution logic của plugin | Chạy `test`, `bootJar`, quality/publish tasks |

### 11.1. Đọc environment variable

Không khuyến nghị đọc rồi enumerate toàn bộ environment variables trong configuration:

```groovy
// Anti-pattern minh họa:
def allEnv = System.getenv()
println allEnv.keySet()
```

Trong Gradle hiện đại, kiểu truy cập này có thể khiến nhiều env vars trở thành fingerprint, gây invalidation liên tục và rò rỉ metadata nhạy cảm. Ưu tiên lấy **một biến cần thiết** qua `providers.environmentVariable('APP_MODE')` và nối vào typed task property. Secrets chỉ được đọc khi thực sự cần và không được in ra log.

## 12. Báo cáo Configuration Cache và debug

Nếu incompatibility xảy ra, log có thể cho biết:

```text
1 problem was found storing the configuration cache.
- Task ':legacyTask' ... Invocation of 'Task.project' ...
Configuration cache entry discarded with 1 problem.
```

Một báo cáo HTML thường được tạo tại đường dẫn dạng:

```text
build/reports/configuration-cache/<hash>/configuration-cache-report.html
```

Hãy mở báo cáo và đọc nhóm problem theo **message**, **task**, stacktrace và **configuration inputs**. Nó giúp phân biệt bug do custom script, plugin bên thứ ba, Gradle API hay một input thay đổi.

Quy trình xử lý:

1. Chạy `./gradlew --version` xác định đúng Wrapper/JDK.
2. Tái hiện cùng task với `--configuration-cache --stacktrace`.
3. Mở report; xác định plugin/task và dòng script.
4. Sửa build logic hoặc nâng plugin theo changelog compatibility.
5. Kiểm tra task lần đầu **store**, lần hai **reuse**, đối chiếu output/test result.
6. Nếu plugin chưa sửa được, dùng giải pháp tạm ở mục 13 và mở issue/ghi người chịu trách nhiệm.
7. Không đánh dấu toàn project đã đạt nếu các task deploy/publish vẫn còn incompatibility chưa kiểm tra.

Lệnh:

```bash
./gradlew help --configuration-cache --stacktrace
./gradlew test --configuration-cache --info
./gradlew bootJar --configuration-cache --info
./gradlew test --no-configuration-cache
```

`--info`/`--debug` và stacktrace có thể chứa thông tin môi trường; trước khi gửi ra ngoài nhóm, lọc secrets và đường dẫn nhạy cảm.

## 13. Khi plugin chưa tương thích: mark task hoặc tắt theo invocation

Gradle hỗ trợ `Task.notCompatibleWithConfigurationCache(reason)`. Nếu build đã có task `legacyGenerate` từ plugin cũ, có thể đánh dấu **tạm thời**:

```groovy
tasks.named('legacyGenerate') {
    notCompatibleWithConfigurationCache(
        'Uses Project model at execution time; awaiting plugin update'
    )
}
```

Đây là **fragment** trong project thực sự đã có task tương ứng; nó không tạo task mới. Với Kotlin DSL:

```kotlin
tasks.named("legacyGenerate") {
    notCompatibleWithConfigurationCache(
        "Uses Project model at execution time; awaiting plugin update"
    )
}
```

Tác dụng: nếu graph chứa task đã mark incompatible, Gradle **không lưu một entry có thể reuse an toàn cho graph đó**. Những invocation khác không kéo task này vào graph vẫn có thể hưởng lợi từ Configuration Cache. Mark task không sửa được implementation, không chứng minh task an toàn để song song và cần một kế hoạch gỡ bỏ sau khi plugin được cập nhật.

Không nhầm với `--configuration-cache-problems=warn` toàn cục: warning mode là công cụ troubleshooting ngắn hạn, không phải chính sách adoption. Các phiên bản Gradle xử lý cảnh báo và task incompatible khác nhau, nhưng **không nên dựa vào warning mode để ép cache một task đã biết không tương thích**.

Khi cần bảo đảm pipeline publish không bị chặn trong lúc chờ sửa plugin:

```bash
./gradlew publish --no-configuration-cache
```

Đây là quyết định trade-off cho **invocation cụ thể**, không được xóa test, bỏ scan bảo mật hoặc âm thầm chuyển sang artifact chưa được kiểm thử.

## 14. Đo hiệu quả Configuration Cache

### 14.1. Benchmark có kiểm soát

1. Dùng cùng source commit, Gradle Wrapper, JDK/toolchain, plugin versions và môi trường.
2. Resolve dependencies trước, làm ấm daemon nếu phù hợp để tránh đánh đồng network/JVM startup với configuration time.
3. Chạy cùng task nhiều lần **không CC** làm baseline.
4. Chạy một lượt với CC để **store** rồi nhiều lượt **reuse**.
5. Ghi thời gian tổng và trạng thái task, nếu cần dùng profiling/build scan có chính sách bảo mật phù hợp.
6. Lấy median của nhiều lượt warmed, không dùng duy nhất một số “BUILD SUCCESSFUL in 0s” làm bằng chứng.
7. Phân biệt chênh lệch do compilation/test/build cache/up-to-date với phần configuration được bỏ qua.

Ví dụ:

```bash
./gradlew help --no-configuration-cache --console=plain
./gradlew help --no-configuration-cache --console=plain

./gradlew help --configuration-cache --console=plain
./gradlew help --configuration-cache --console=plain
./gradlew help --configuration-cache --console=plain
```

`help` hữu ích để thấy chi phí configuration rõ. Sau đó đo `test`/`bootJar` vì đó mới là workflow thực tế. Không nên chạy `clean` xen giữa hai lượt rồi kết luận mọi phần thời gian chênh lệch do Configuration Cache.

### 14.2. Ví dụ số liệu giả định

| Lượt đo | Trạng thái CC | Tổng thời gian giả định |
|---|---|---:|
| `help`, không CC và warmed | Off | 3,3 giây |
| `help`, CC lần đầu | Stored | 3,7 giây |
| `help`, CC lượt kế | Reused | 0,9 giây |

Đây là **số minh họa**, không phải benchmark được chạy trong repository thật. Lượt đầu có thể chậm vì Gradle phải serialize cache entry. Trên project nhỏ, tiết kiệm có thể rất ít; trên multi-module nhiều plugin, phần configuration được bỏ qua có thể đáng kể.

## 15. Multi-module: cache theo task request và plugin thực tế

Giả sử:

```text
platform/
├── settings.gradle
├── gradle.properties
├── build.gradle
├── shared-core/build.gradle
├── orders-api/build.gradle
└── batch-worker/build.gradle
```

`settings.gradle`:

```groovy
rootProject.name = 'platform'
include 'shared-core', 'orders-api', 'batch-worker'
```

Các invocation sau có task graphs khác nhau:

```bash
./gradlew help --configuration-cache
./gradlew :shared-core:test --configuration-cache
./gradlew :orders-api:bootJar --configuration-cache
./gradlew :batch-worker:test --configuration-cache
./gradlew check --configuration-cache
```

Gradle có thể lưu entry riêng cho từng request. **Module library** có thể chỉ áp dụng Java Library plugin, còn app áp dụng Spring Boot plugin. Không bật Boot plugin trong mọi module chỉ để có cache: cache áp dụng cho **Gradle build**, không phụ thuộc vào plugin Boot.

Ở build đa module, kiểm tra task dependency thật. Configuration Cache thường tạo điều kiện để task execution dùng isolation/parallelism tốt hơn, nên hai task cùng ghi một file không khai báo output hoặc ordering có thể phát sinh race. Dùng `@Input...`, `@Output...`, Providers và `dependsOn` hoặc task output wiring thay vì dựa vào thứ tự tình cờ trong log.

**Lưu ý:** `mustRunAfter` chỉ ảnh hưởng thứ tự **nếu cả hai task đã được chọn**, không khiến task kia tự tham gia graph. Khi có tài nguyên dùng chung, Gradle Shared Build Service và `usesService(...)` có thể giúp kiểm soát truy cập.

## 16. IDE, CI và bảo mật

### 16.1. IDE

Gradle tài liệu nói rõ **IDE sync/import không được tăng tốc bởi Configuration Cache**. Tuy nhiên, khi IDE delegate **task invocation** cho Gradle và cache được bật, task có thể reuse entry tương tự terminal. Đừng dùng thời gian “Sync Project” làm thước đo hiệu quả Configuration Cache.

### 16.2. CI

Nên triển khai theo từng giai đoạn:

- Developer thử trên máy với `help`, `test`, `check`, `bootJar`.
- Một CI job thử chạy cùng task hai lần trên **cùng workspace** để kiểm chứng entry stored/reused.
- So sánh artifact, test results và report khi CC bật/tắt.
- Chỉ commit `org.gradle.configuration-cache=true` khi không còn incompatibility chưa được chấp nhận ở các task chính.
- Khi nâng version Gradle/plugin, kiểm tra lại compatibility thay vì kế thừa giả định từ lần trước.

Ví dụ lệnh trên cùng CI workspace:

```bash
./gradlew --no-daemon --configuration-cache test
./gradlew --no-daemon --configuration-cache test
./gradlew --no-daemon --configuration-cache bootJar
./gradlew --no-daemon --configuration-cache bootJar
```

`--no-daemon` là lựa chọn policy cho runner, **không** phải điều kiện bật Configuration Cache. Nếu runner bị hủy sau mỗi job, cache cục bộ từ job trước **không tự tồn tại** ở job sau. Việc lưu/khôi phục cache giữa job cần thiết kế riêng và bảo vệ dữ liệu, không copy bừa `.gradle` hoặc Gradle User Home lên kho công khai.

### 16.3. Secrets

Task state và configuration fingerprints có thể chứa giá trị đọc trong configuration; không coi cache là nơi lưu credential an toàn để chia sẻ. Tránh `System.getenv('TOKEN')` tại configuration nếu không cần. Dùng Provider API, secret manager/CI variables và cơ chế credentials của Gradle; chỉ đọc secret ở task phù hợp, không in lên log. Kiểm soát quyền đối với project cache và Gradle User Home. Dù Gradle version có cơ chế mã hóa cache, **không dùng nó như thay thế cho quản lý secret**.

## 17. Lỗi phổ biến và hướng chẩn đoán

| Triệu chứng | Giải thích có thể | Hành động |
|---|---|---|
| `help` fail ngay khi bật CC | Build script/plugin configuration không tương thích | Mở CC report và sửa sớm |
| `help` hit nhưng `bootJar` fail | Task packaging hoặc custom action chỉ phát hiện khi graph chứa task đó | Kiểm tra plugin Boot và custom archive actions |
| `Task.project at execution time unsupported` | Task action đọc `Project` | Chuyển sang local value, typed task hoặc injected service |
| `Configuration cache entry discarded` | Lỗi serialization hoặc task marked incompatible | Không tuyên bố cache đã lưu; đọc lý do |
| `Calculating task graph ... cannot be reused` | Input configuration thay đổi hoặc task request khác | Đọc dòng invalidation, không xóa cache bừa |
| `UP-TO-DATE` nhưng không có `reused` | Task outputs còn mới, Configuration Cache không hit | Phân biệt hai cơ chế |
| `FROM-CACHE` nhưng config lại | Build Cache có hit, CC tắt/miss | Xem thuộc tính hai cache riêng |
| Build fail do `--configuration-cache` trên CI | Plugin/task chỉ xuất hiện ở CI, JDK/plugin version khác | So sánh plugin list, task graph, init scripts và environment |
| Cache invalidated mỗi lần CI | Đọc build number, timestamp, env hoặc file volatile lúc configuration | Chuyển sang Provider/task inputs rõ |
| `warn` chạy được nhưng kết quả lần sau sai | Incompatibility bị bỏ qua, serialized state thiếu | Tắt warning mode, sửa task |
| Multi-module xuất hiện race | Shared mutable state/file output chưa khai báo | Chuẩn hóa task isolation, output directories, dependencies |
| Artifact khác khi bật/tắt CC | Build logic phụ thuộc side effects hoặc input ẩn | Chẩn đoán correctness trước tối ưu hiệu năng |
| IDE sync không nhanh hơn | Sync không dùng CC | Đo delegated Gradle task |
| Nâng Wrapper làm nhiều task fail | Plugin chưa tương thích major Gradle mới | Pin version cũ hợp lệ, nâng từng bước |
| Xóa `build/` vẫn thấy CC hit | Cache ở `.gradle/configuration-cache`, không phải `build/` | Không coi `clean` là xóa CC |

Lệnh hỗ trợ chẩn đoán:

```bash
./gradlew --version
./gradlew help --configuration-cache --stacktrace
./gradlew test --configuration-cache --info
./gradlew bootJar --configuration-cache --info
./gradlew test --no-configuration-cache
```

Trước khi chia sẻ `--info`/`--debug` hoặc stacktrace, xem log có thể chứa URL nội bộ, path riêng hoặc secrets không.

## 18. Bài thực hành so sánh và tiêu chí hoàn thành

**A. Baseline:** chạy `./gradlew clean test` và `./gradlew bootJar` với cache tắt, kiểm tra unit test và executable JAR.

**B. Store:** chạy `./gradlew help --configuration-cache`; tìm `Configuration cache entry stored`. Nếu báo lỗi, mở HTML report để sửa.

**C. Reuse:** chạy đúng lại `help`, tìm `Reusing configuration cache` và `Configuration cache entry reused`.

**D. Task thực tế:** chạy `test` và `bootJar` **mỗi task request hai lần**, không đổi build scripts, ghi lại trạng thái.

**E. Source change:** đổi nội dung `GreetingService.greet` và expected value trong test, chạy lại `test`. Khi cần compile/test lại, Configuration Cache vẫn có thể reuse; xác nhận test mới chạy đúng.

**F. Configuration change:** đổi `version = '0.1.0-SNAPSHOT'` trong build script thành một giá trị khác, chạy `bootJar`; Gradle phải đánh giá lại configuration phù hợp và tên archive có thể thay đổi. Khôi phục giá trị sau thử nghiệm.

**G. Incompatibility:** thêm tạm task `showBad` ở mục 9 trên nhánh thử nghiệm, chạy với CC, đọc problem. Chuyển thành `showName`/`PrintMessageTask` rồi chạy hai lần để chứng minh stored/reused; không commit task lỗi.

**H. Triển khai:** kiểm tra thêm code generation, checkstyle/spotless, publish và multi-module tasks. Ghi owner, lỗi còn tồn tại, kế hoạch plugin update; chỉ sau đó bật default ở `gradle.properties` nếu workflow team đạt điều kiện.

### Checklist

- [ ] Java/Gradle Wrapper/Spring Boot plugin version được pin và có ma trận tương thích.
- [ ] `help`, `test`, `bootJar` đạt **stored → reused** khi input không đổi.
- [ ] Không dùng warning mode để che Configuration Cache problems trong CI.
- [ ] Custom task không truy cập `Project`/`Gradle` live object ở execution.
- [ ] Provider, task input/output và task dependencies được khai báo đúng.
- [ ] Test results và artifact giống nhau khi bật/tắt Configuration Cache.
- [ ] Không nhầm `UP-TO-DATE`/`FROM-CACHE` với reuse configuration.
- [ ] Các task của plugin thứ ba và subprojects quan trọng đã được thử.
- [ ] Benchmark có baseline và nhiều lượt warm, tránh nhiễu download/daemon.
- [ ] Cache/secrets ở CI có quyền truy cập phù hợp, không commit directory cache.
- [ ] Có lệnh `--no-configuration-cache` để xử lý một invocation chưa tương thích.
- [ ] Có kế hoạch xác minh lại khi nâng Wrapper hoặc plugin.

### Tài liệu chính thức

- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html)
- [Gradle — Enabling and Configuring the Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache_enabling.html)
- [Gradle — Adopting the Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache_adoption.html)
- [Gradle — Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html)
- [Gradle — Debugging the Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache_debugging.html)
- [Gradle — Supported Plugins and Status](https://docs.gradle.org/current/userguide/configuration_cache_status.html)
- [Gradle — Task API, notCompatibleWithConfigurationCache](https://docs.gradle.org/current/javadoc/org/gradle/api/Task.html)
- [Spring Boot 3.5 — Gradle Plugin](https://docs.spring.io/spring-boot/3.5/gradle-plugin/)

**Ghi nhớ:** Configuration Cache chỉ tăng tốc khi **toàn bộ plugin và task tham gia một invocation tương thích**, đồng thời configuration inputs được theo dõi chính xác. Hãy chứng minh bằng **stored → reused** và kết quả test/artifact không đổi; nếu có lỗi, sửa build logic hoặc khoanh task chưa tương thích thay vì tắt cơ chế kiểm tra bằng warning mode dài hạn.

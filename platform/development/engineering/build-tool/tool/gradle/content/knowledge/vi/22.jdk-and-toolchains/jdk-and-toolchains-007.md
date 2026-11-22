# Kiểm tra toolchain thực tế bằng `javaToolchains` và log trong Gradle

## 1. Mục tiêu: kiểm chứng JDK được dùng thật, không chỉ JDK bạn nghĩ đang dùng

Một máy phát triển có thể cài Java 8, 11, 17 và 21. Terminal chạy `java -version` báo Java 21 nhưng Gradle build vẫn biên dịch bằng JDK 17; IDE dùng JVM khác; task `test` lại được cấu hình để chạy bằng JDK 11. Đây không hẳn là lỗi: **Gradle Daemon JVM** và **Java toolchain của từng task** là những khái niệm độc lập.

Ví dụ một dự án khai báo:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Câu này thể hiện **yêu cầu** dùng Java 17 cho những tasks do Java plugin quản lý theo convention. Nó **không chứng minh** máy có JDK 17, **không chứng minh** Gradle đã chọn installation nào, và **không chứng minh** mọi plugin/task tùy chỉnh đều dùng JDK đó.

Mục tiêu bài học:

- Đọc `./gradlew -q javaToolchains` để biết Gradle **phát hiện những JDK/JRE nào**, vị trí, vendor, version và nguồn phát hiện.
- Phân biệt Java chạy ở terminal, JVM chạy Gradle client/daemon, `JavaCompiler` của `compileJava`, `JavaLauncher` của `test`/`run` và Javadoc tool.
- Dùng `--info`, `--stacktrace`, `--rerun-tasks` và task reports để tìm **công cụ thực tế được chọn** mà không đoán theo `JAVA_HOME`.
- Xây dựng một ví dụ **Java 17+ có thể compile/run/test**, in Java runtime feature và kiểm tra class-file major version.
- Phân tích auto-detection, custom paths, `fromEnv`, auto-provisioning và toolchain resolver plugins.
- Gỡ lỗi tình huống đã cấu hình Java 17 nhưng compiler/runtime/task bị sai, không tìm được JDK hoặc kết quả IDE khác terminal.
- Biết cách ghi lại bằng chứng JDK cho CI và xử lý các khác biệt do vendor, architecture, version patch.

Các ví dụ là **Gradle Kotlin DSL**, ưu tiên Gradle Wrapper. Những output có đường dẫn và version patch thay đổi theo máy sẽ được đánh dấu là **minh họa**, không coi là stdout cố định. Với Windows PowerShell dùng `.\gradlew.bat` thay cho `./gradlew`.

## 2. Có nhiều “Java version” trong cùng một build

Trước khi chạy lệnh chẩn đoán, cần xác định bạn đang tìm **JVM nào**.

| Đối tượng | Dùng làm gì? | Cách kiểm tra phù hợp |
| --- | --- | --- |
| `java -version` ở shell | JVM mà lệnh `java` từ `PATH` chọn. | `java -version`; đường dẫn executable từ `which`/`where.exe`. |
| `javac -version` ở shell | Compiler mà lệnh `javac` từ `PATH` chọn. | `javac -version`. |
| `JAVA_HOME` | Biến môi trường thường được Gradle launcher/IDE dùng để tìm Java. | `echo "$JAVA_HOME"` hoặc `$env:JAVA_HOME`. |
| Gradle launcher/daemon JVM | JVM thực thi Gradle và các build plugins. | `./gradlew --version` và Daemon JVM settings. |
| `JavaCompile.javaCompiler` | Compiler của task `compileJava` hoặc `compileTestJava`. | Toolchain configuration, `--info` và metadata của task property. |
| `Test.javaLauncher` | JVM chạy forked test processes. | `--info test`; test tự in `java.version`/`java.home`. |
| `JavaExec.javaLauncher` | JVM chạy `run` hoặc JavaExec task. | `--info run`; chương trình tự in `Runtime.version()` và `java.home`. |
| `Javadoc.javadocTool` | Tool tạo Javadoc. | Toolchain spec, task property và Javadoc task log. |
| Bytecode target | Class file version mà compiler phát hành. | `javap -verbose`, trường `major version`. |
| API compatibility | Những JDK APIs code được phép sử dụng khi compile. | `options.release`, không chỉ `targetCompatibility`. |

Có thể xảy ra:

~~~text
Terminal java:           Java 21
Gradle Daemon:           Java 21
compileJava compiler:   JDK 17
test launcher:          JDK 17
app run launcher:       JDK 17
class-file major:       61  (Java 17)
~~~

Đây là **một tình huống hợp lệ minh họa**, không phải dữ liệu được đo trên máy hiện tại. `JAVA_HOME`, PATH, Gradle Daemon và selected task toolchain có thể khác nhau. Khi debug, phải ghi rõ đang nói **version nào ở lớp nào**.

## 3. Chuẩn bị lệnh chẩn đoán trên terminal

Từ root project có Gradle Wrapper:

~~~bash
./gradlew --version
java -version
javac -version
echo "$JAVA_HOME"
command -v java
command -v javac
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat --version
java -version
javac -version
$env:JAVA_HOME
Get-Command java
Get-Command javac
~~~

`java -version` và `javac -version` thường ghi ra stderr hoặc theo định dạng riêng của vendor; không xây bài kiểm thử phụ thuộc nguyên văn những dòng này. Trên Windows có thể dùng `where.exe java` để liệt kê vị trí `java.exe` trên PATH, nhưng **vị trí trên PATH không tự chứng minh JDK mà Gradle task chọn**.

`./gradlew --version` nói bản Gradle Wrapper và JVM đang dùng cho Gradle theo cách version hiện tại hiển thị. Các phiên bản Gradle mới có thể hiện riêng **Launcher JVM** và **Daemon JVM**; phiên bản cũ có thể chỉ hiện dòng **JVM**. Cách đặt tên log thay đổi theo Gradle, nên nhìn dữ liệu version/home chứ không cố khớp một template văn bản duy nhất.

**Quan trọng:** Gradle có thể chạy trên Java 21 nhưng sử dụng compiler Java 17 nhờ toolchain. Điều này khác với một lỗi cấu hình; Gradle toolchains được thiết kế để tách **JVM chạy build logic** khỏi **JVM chạy/biên dịch code ứng dụng**.

## 4. Lệnh chính: `./gradlew -q javaToolchains`

Gradle có task **`javaToolchains`** để hiển thị Java installations mà nó phát hiện:

~~~bash
./gradlew -q javaToolchains
~~~

Windows:

~~~powershell
.\gradlew.bat -q javaToolchains
~~~

Nếu build là multi-project, có thể chạy từ root hoặc chọn target project/task khi cần. Đây là **báo cáo inventory toolchains**, không phải hành động biên dịch mã Java.

### 4.1. Đọc report từng dòng

Ví dụ **minh họa**, không phải output đo trên máy người học:

~~~text
 + Options
     | Auto-detection:     Enabled
     | Auto-download:      Enabled

 + Eclipse Temurin JDK 17.0.x
     | Location:           /opt/jdks/temurin-17
     | Language Version:   17
     | Vendor:             Eclipse Adoptium
     | Architecture:       amd64
     | Is JDK:             true
     | Detected by:        environment variable 'JDK17_HOME'

 + OpenJDK 21.0.x
     | Location:           /opt/jdks/jdk-21
     | Language Version:   21
     | Vendor:             a JDK vendor
     | Architecture:       amd64
     | Is JDK:             true
     | Detected by:        system location
~~~

Các nhãn/path/vendor cụ thể sẽ thay đổi theo hệ điều hành, bản Gradle và nhà cung cấp. Không copy nguyên bản minh họa làm bằng chứng cho CI.

| Trường | Cách hiểu đúng |
| --- | --- |
| `Auto-detection` | Gradle có đang tự dò Java installations từ nguồn được hỗ trợ hay không. |
| `Auto-download` | Cờ cho phép cơ chế tải toolchain nếu thích hợp. **Enabled không đồng nghĩa đã có resolver repository để tải.** |
| `Location` | Thư mục cài JDK/JRE mà Gradle phát hiện. |
| `Language Version` | Java major version dùng để match `JavaLanguageVersion.of(...)`. |
| `Vendor` | Thông tin vendor được Gradle trích từ runtime metadata. |
| `Architecture` | Kiến trúc CPU, hữu ích với macOS Apple Silicon, x86_64 CI, container. |
| `Is JDK` | Có phải một JDK có compiler/toolset cần thiết, không chỉ JRE. |
| `Detected by` | Nguồn phát hiện: PATH, `JAVA_HOME`, OS location, SDKMAN!, IDE, custom property... tùy máy. |

### 4.2. Inventory KHÔNG phải bằng chứng task đang dùng installation nào

Một máy có thể hiện **ba JDK 17** từ Adoptium, Microsoft và Oracle. `javaToolchains` cho biết chúng **có sẵn**, không chỉ ra `compileJava` chắc chắn đã chọn cái nào. Gradle dùng **toolchain matching** và **precedence rules** để chọn installation đáp ứng spec.

Do đó cần thêm bằng chứng:

1. **Spec** trong `build.gradle.kts`: project/task yêu cầu major/vendor/implementation nào?
2. **Report** từ `javaToolchains`: có những installations nào phù hợp?
3. **Task logs** từ `compileJava --info --rerun-tasks`: compiler thực tế của compile task.
4. **Runtime evidence** từ Java code hoặc Test tasks: JVM chạy thực.
5. **Bytecode check** qua `javap`: class target tương ứng yêu cầu hay chưa.

Chỉ chạy `javaToolchains` rồi kết luận “Gradle đang compile Java 17” là chưa đủ.

## 5. Ví dụ hoàn chỉnh Java 17: cấu hình, chạy, test, kiểm tra JDK

Bài thực hành dùng Application/Java plugins, một Java main class và một unit test JUnit 5. Lõi app không cần thư viện ngoài, nhưng **JUnit dependencies cần Maven Central** để test lần đầu.

### 5.1. Cấu trúc project

~~~text
toolchain-diagnostics-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── src/main/java/example/App.java
└── src/test/java/example/AppTest.java
~~~

Máy cần một **Gradle Wrapper tương thích JDK 17** và một JDK 17 được phát hiện hoặc một toolchain resolver repository được cấu hình để provision JDK. Gradle Wrapper phải đã tồn tại và đủ quyền chạy; ví dụ không tự sinh file Wrapper.

`settings.gradle.kts`:

~~~kotlin
rootProject.name = "toolchain-diagnostics-lab"
~~~

### 5.2. Toàn bộ `build.gradle.kts`

~~~kotlin
plugins {
    application
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    // Đồng thời kiểm soát API level và class-file target.
    options.release.set(17)
}

application {
    mainClass.set("example.App")
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
    testLogging {
        showStandardStreams = true
    }
}
~~~

Các điểm quan trọng:

- `application` apply các khả năng cần thiết của Java plugin và tạo task `run`.
- `java.toolchain.languageVersion` chọn **JDK 17 cho các Java tasks** theo convention của Java plugin, với điều kiện toolchain có thể resolve.
- `options.release.set(17)` là thêm một ràng buộc để Java compiler không vô tình compile bằng APIs mới hơn Java 17, đồng thời phát hành class-file target phù hợp. `toolchain` và `--release` làm **hai việc khác nhau**.
- `JUnit BOM` chỉ quản lý version; `junit-jupiter` và `junit-platform-launcher` mới là các dependencies thực sự cần để chạy tests.
- `testLogging.showStandardStreams` làm test output có thể xuất hiện trong Gradle logs; nó không khiến console output của build hoàn toàn bất biến.
- Không dùng `options.release` cho Groovy/Kotlin tasks như thể mọi JVM compiler đều hiểu tùy chọn `javac --release`; nếu có Kotlin/JVM plugin phải kiểm tra toolchain và JVM target riêng.

Đây là project **có thể chạy được** khi Wrapper/JDK 17 và Maven Central hoạt động. Version JUnit `5.11.4` là mốc minh họa, không phải bản mới nhất bắt buộc.

### 5.3. `src/main/java/example/App.java`

~~~java
package example;

public final class App {
    private App() {
    }

    public static String reportJavaFeature() {
        return "RUN_JAVA_FEATURE=" + Runtime.version().feature();
    }

    public static void main(String[] args) {
        System.out.println(reportJavaFeature());
        System.out.println(
            "RUN_JAVA_HOME=" + System.getProperty("java.home")
        );
    }
}
~~~

Với Java 17 launcher thực sự, **dòng stdout đầu tiên** là:

~~~text
RUN_JAVA_FEATURE=17
~~~

Dòng thứ hai bắt đầu bằng `RUN_JAVA_HOME=` rồi đến một **đường dẫn phụ thuộc máy**, ví dụ thư mục JDK 17 của CI. **Không thể khẳng định toàn bộ đường dẫn trước khi chạy thật.** `java.home` đo runtime mà chương trình đang chạy, không phải tự động là đường dẫn tới Gradle Daemon JVM hoặc compiler executable.

### 5.4. `src/test/java/example/AppTest.java`

~~~java
package example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppTest {
    @Test
    void testsRunOnJava17() {
        int feature = Runtime.version().feature();

        System.out.println("TEST_JAVA_FEATURE=" + feature);
        assertEquals(17, feature);
        assertEquals("RUN_JAVA_FEATURE=17", App.reportJavaFeature());
    }
}
~~~

Test này cố tình **kiểm tra Java runtime version thực tế trong test process**. Nó sẽ fail nếu test bị chạy bằng Java khác 17 dù code vẫn có thể compile. Vì vậy đây là bằng chứng runtime của `Test.javaLauncher`, không chỉ một cấu hình trên giấy.

### 5.5. Chạy các lệnh

~~~bash
./gradlew --version
./gradlew -q javaToolchains

# Biên dịch Java chính và test, bắt buộc chạy task mới.
./gradlew compileJava compileTestJava --rerun-tasks --info

# Chạy ứng dụng để đo Java runtime.
./gradlew -q run

# Chạy unit test và đọc Java feature của process thực.
./gradlew test --rerun-tasks --info

# Xem class-file major version sau khi compile.
javap -verbose build/classes/java/main/example/App.class
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat -q javaToolchains
.\gradlew.bat compileJava compileTestJava --rerun-tasks --info
.\gradlew.bat -q run
.\gradlew.bat test --rerun-tasks --info
javap -verbose build/classes/java/main/example/App.class
~~~

**Kết quả kỳ vọng:**

- `javaToolchains` phát hiện ít nhất một toolchain thỏa **Java 17** hoặc Gradle có thể provision được toolchain đáp ứng.
- `compileJava`/`compileTestJava` chạy bằng compiler thuộc toolchain được chọn.
- `App` in `RUN_JAVA_FEATURE=17` và dòng home path tùy máy.
- Test in `TEST_JAVA_FEATURE=17` bên trong test logs, assert pass.
- `javap -verbose` cho `major version: 61` nếu class được compile thành Java 17 bytecode.
- `BUILD SUCCESSFUL` từ Gradle nếu tất cả tasks được yêu cầu chạy thành công.

Không bịa toàn bộ `--info` transcript. Log thực tế còn có daemon, dependency resolution, cache, incremental compiler, worker API, Gradle version và test logging format.

### 5.6. Vì sao dùng `--rerun-tasks`?

Gradle có cơ chế up-to-date check và build cache. Một lần chạy `./gradlew compileJava --info` có thể chỉ báo `UP-TO-DATE` mà **không thực thi compiler**; như vậy bạn không có log mới của lần compile thực tế.

`--rerun-tasks` khiến Gradle thực hiện lại tasks được yêu cầu dù chúng có thể up-to-date. Nó **không thay đổi toolchain spec**; chỉ giúp thu bằng chứng task execution và giảm nhầm lẫn “không thấy log vì task không chạy”.

Nếu chỉ muốn **đọc inventory**, `javaToolchains` không cần `--rerun-tasks` để có output. Nếu muốn đo **test runtime**, gọi `test --rerun-tasks --info` để chắc chắn test thực thi lại.

## 6. Đọc log `--info` đúng cách

Các lệnh quan trọng nhất:

~~~bash
./gradlew compileJava --info --rerun-tasks
./gradlew compileTestJava --info --rerun-tasks
./gradlew test --info --rerun-tasks
./gradlew run --info
~~~

`--info` bật các thông báo nhiều chi tiết hơn mức mặc định, nhưng **không có một dòng text cố định cho mọi phiên bản Gradle**. Hãy tìm trong log:

- Task path, ví dụ `> Task :compileJava` hoặc `> Task :app:compileJava`.
- Thông tin **toolchain matching**, compiler, Java home, worker process/forking khi Gradle/plugin phát log.
- Tác vụ có chạy hay `UP-TO-DATE`/`FROM-CACHE`/`NO-SOURCE`.
- Thông tin test worker/Java executable khi Gradle khởi chạy forked tests.
- Dòng `RUN_JAVA_FEATURE=17` hoặc `TEST_JAVA_FEATURE=17` từ **chương trình thật**.
- Lý do failed resolution nếu không tìm được Java installation phù hợp.

Một log có thể ghi cụm tương tự `Compiling with toolchain ...` hoặc thông tin Java compiler installation, nhưng **không đảm bảo mọi lần chạy đều có đúng câu này**. Khi cần bằng chứng chính xác ở mức task, có thể đọc property `JavaCompile.javaCompiler` và `Test.javaLauncher` hoặc dùng diagnostic task ở mục 8.

### Bảng giải thích các trạng thái task

| Trạng thái | Có chứng minh task đã chạy compiler/JVM lần này? |
| --- | --- |
| `UP-TO-DATE` | **Không.** Gradle bỏ qua task vì inputs/outputs phù hợp. |
| `FROM-CACHE` | **Không.** Gradle phục hồi output từ cache, không cần chạy compiler. |
| `NO-SOURCE` | **Không.** Không có source tương ứng để compile. |
| `SKIPPED` | **Không.** Task không thực thi action do điều kiện/cấu hình. |
| `FAILED` | Có thể fail trước khi chạy compiler; phải đọc nguyên nhân. |
| Task chạy action thực tế | Có bằng chứng execution; cần thêm thông tin về toolchain được chọn. |

Đừng thấy `BUILD SUCCESSFUL` rồi kết luận đã dùng JDK 17. Một build có thể thành công với toolchain **khác yêu cầu** nếu task tùy chỉnh bỏ qua Java plugin convention, hoặc đơn giản vì task Java chưa chạy.

### `--debug` và `--stacktrace`

- `--stacktrace` hữu ích khi không resolve được toolchain/plugin hoặc task fail.
- `--info` thường đủ để biết compiler/JVM selection.
- `--debug` có thể cực dài và chứa path, credentials hoặc thông tin nhạy cảm; chỉ dùng trong môi trường kiểm soát khi log thường không đủ.
- Nếu phải chia sẻ log, **loại bỏ home path, user name, tokens, repository credentials** trước khi đưa vào ticket công khai.

## 7. Đọc JVM của Gradle khác với toolchain task

Ví dụ bạn thấy:

~~~text
java -version:                21
./gradlew --version:           Daemon JVM 21
./gradlew -q javaToolchains:   tìm thấy JDK 17 và 21
./gradlew -q run:              RUN_JAVA_FEATURE=17
~~~

Đây không phải mâu thuẫn: Gradle có thể **chạy trên Java 21 và dùng Java 17 để chạy app**.

Những điều dễ nhầm:

- `JAVA_HOME` thường ảnh hưởng Gradle launcher hoặc default JVM nếu chưa có override, **không tự ép project toolchain về cùng version**.
- `org.gradle.java.home` có thể chọn JDK cho Gradle build process/daemon, **không phải thay thế mặc định cho `java.toolchain`**.
- Gradle Daemon JVM criteria có thể được quản lý riêng bằng `gradle/gradle-daemon-jvm.properties` ở những bản Gradle hỗ trợ; nếu đã có file criteria, phải tính cả nó khi debug.
- IDE có thể chọn **Gradle JVM** trong Settings riêng và gửi build qua Gradle tooling; máy terminal và IDE có thể dùng daemon/JDK khác.
- `sourceCompatibility`/`targetCompatibility` chủ yếu điều khiển source/bytecode, **không tự chọn đúng compiler JDK installation**.

Vì vậy khi trao đổi một lỗi, đừng viết “dự án dùng Java 17” mà không nói đó là **daemon, compiler, test runtime, app runtime hay target bytecode**.

## 8. Kiểm tra task properties: `JavaCompiler` và `JavaLauncher`

Gradle cung cấp các tool providers qua `javaToolchains` service:

~~~kotlin
val java17Compiler = javaToolchains.compilerFor {
    languageVersion.set(JavaLanguageVersion.of(17))
}

val java17Launcher = javaToolchains.launcherFor {
    languageVersion.set(JavaLanguageVersion.of(17))
}
~~~

Đây là **mảnh Kotlin DSL đặt trong project có Java plugin**, không phải một file Gradle đầy đủ. Providers cho phép Gradle resolve **lazily** khi một task cần công cụ đó; không gọi `.get()` ở configuration time nếu có thể tránh, vì có thể trigger detection/provisioning sớm.

### 8.1. Task cụ thể có thể override project toolchain

Nếu muốn buộc compile bằng một compiler cụ thể:

~~~kotlin
tasks.named<JavaCompile>("compileJava") {
    javaCompiler.set(javaToolchains.compilerFor {
        languageVersion.set(JavaLanguageVersion.of(17))
    })
}
~~~

Nếu muốn chạy tests bằng Java 21 để kiểm tra tương thích runtime trên một JDK khác:

~~~kotlin
tasks.named<Test>("test") {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(21))
    })
}
~~~

Hai block là **ví dụ override riêng**, không dùng chúng trong lab Java 17 mục 5 nếu vẫn muốn test assert version 17. Ở tình huống override test sang Java 21, test `testsRunOnJava17()` sẽ **fail đúng chủ đích**, vì nó assert 17.

Nếu muốn một `JavaExec` task thử runtime khác:

~~~kotlin
tasks.register<JavaExec>("runOn21") {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(21))
    })
    classpath = sourceSets["main"].runtimeClasspath
    mainClass.set("example.App")
}
~~~

Đây là **mảnh bổ sung cho Application project có `example.App`**. Chạy `./gradlew runOn21` cần có JDK 21 phù hợp; stdout đầu là `RUN_JAVA_FEATURE=21`, trong khi bytecode vẫn có thể được tạo bởi Java 17 (class-file major 61).

### 8.2. Task diagnostic đọc selected tools của chính compile/test/run

Khi log ở mức `--info` chưa rõ, tạo một diagnostic task chuyên đọc **tool providers mà các tasks thực sự được cấu hình sử dụng**. Để tránh truy cập Project model trong task action, dùng task type có **@Nested properties**.

Các import cần đặt **đầu `build.gradle.kts`, trước block `plugins`**:

~~~kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Nested
import org.gradle.api.tasks.TaskAction
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.testing.Test
import org.gradle.api.tasks.JavaExec
import org.gradle.jvm.toolchain.JavaCompiler
import org.gradle.jvm.toolchain.JavaLauncher
~~~

**Sau** các block `plugins`/`java`/`application` của ví dụ mục 5, thêm:

~~~kotlin
abstract class ReportSelectedJavaTools : DefaultTask() {
    @get:Nested
    abstract val compiler: Property<JavaCompiler>

    @get:Nested
    abstract val testLauncher: Property<JavaLauncher>

    @get:Nested
    abstract val runLauncher: Property<JavaLauncher>

    @TaskAction
    fun report() {
        val c = compiler.get()
        val t = testLauncher.get()
        val r = runLauncher.get()

        println("COMPILE_VERSION=" + c.metadata.languageVersion.asInt())
        println("COMPILE_HOME=" + c.metadata.installationPath.asFile)
        println("TEST_VERSION=" + t.metadata.languageVersion.asInt())
        println("TEST_HOME=" + t.metadata.installationPath.asFile)
        println("RUN_VERSION=" + r.metadata.languageVersion.asInt())
        println("RUN_HOME=" + r.metadata.installationPath.asFile)
    }
}

tasks.register<ReportSelectedJavaTools>("reportSelectedJavaTools") {
    compiler.set(
        tasks.named<JavaCompile>("compileJava")
            .flatMap { it.javaCompiler }
    )
    testLauncher.set(
        tasks.named<Test>("test")
            .flatMap { it.javaLauncher }
    )
    runLauncher.set(
        tasks.named<JavaExec>("run")
            .flatMap { it.javaLauncher }
    )
}
~~~

Trong project Application/Java Gradle version hiện đại, các task properties này cung cấp toolchain provider. Lệnh:

~~~bash
./gradlew -q reportSelectedJavaTools
~~~

Nếu cả ba tasks dùng Java 17 như lab mục 5, các **dòng version** cần là:

~~~text
COMPILE_VERSION=17
TEST_VERSION=17
RUN_VERSION=17
~~~

Ngoài ra có ba dòng `COMPILE_HOME=...`, `TEST_HOME=...` và `RUN_HOME=...` với **đường dẫn phụ thuộc môi trường**. Vì task in xen kẽ version/home nên ba dòng version ở trên là **tập giá trị cần kiểm tra**, không phải một block output liên tiếp chính xác theo thứ tự in. Muốn audit đường dẫn, đọc output thực tế.

**Lưu ý:** đây là mã diagnostic nâng cao. Nó dùng task properties qua `TaskProvider.flatMap` để đọc **công cụ đã được cấu hình cho task**, không tự tạo một provider Java 17 khác rồi khẳng định các task cũng đang dùng provider ấy. Khi dự án tự thay `javaCompiler` hoặc `javaLauncher`, report phản ánh sự thay đổi đó. Task không chứng minh một action ngoài Gradle (như `Exec` chạy `java` từ PATH) cũng dùng cùng JDK.

Nếu không muốn thêm mã vào build production, đặt diagnostic task trong một init script hoặc convention plugin kiểm soát được, hoặc dùng các lệnh có sẵn `javaToolchains`, `--info` và Java runtime probe như mục 5. Không giữ code debug tạm nếu không có owner/bài kiểm thử tương ứng.

## 9. `--release` và bytecode: xác minh API target không phải JDK path

Một nhầm lẫn lớn: **đặt Java language level 17** có phải code chắc chắn chỉ dùng Java 17 APIs không?

- `java.toolchain.languageVersion = 17` chọn một **JDK 17 compiler/toolchain** cho các Java tasks.
- `sourceCompatibility = JavaVersion.VERSION_17` cho biết Java syntax compatibility, nhưng không chọn compiler JDK và không luôn hạn chế mọi JDK APIs nếu compiler mới hơn.
- `targetCompatibility = JavaVersion.VERSION_17` đặt class-file target, không tự hạn chế API sử dụng trong source.
- `options.release.set(17)` yêu cầu `javac --release 17`: vừa đặt language/bytecode level vừa giới hạn standard library APIs của release mục tiêu.

Nếu dùng JDK 21 để compile Java 11-compatible library:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(11)
}
~~~

Đây là **phương án riêng**, không phải cấu hình của lab Java 17 ở trên. `compileJava` dùng compiler JDK 21 nhưng class-file target Java 11 (`major version: 55`) và không được gọi APIs thêm mới sau Java 11 trong Java platform.

**Vì thế phải kiểm tra cả hai:**

1. `javaToolchains`/task property/`--info` → compiler thuộc JDK installation nào.
2. `javap -verbose ...` → bytecode major version ra sao.

Ví dụ class file Java 17:

~~~text
major version: 61
~~~

Bảng nhớ nhanh:

| Java release | Class-file major |
| --- | --- |
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |

`javap` từ PATH có thể thuộc JDK khác (ví dụ 21) và vẫn đọc Java 17 class file. Vì vậy `javap` chứng minh **định dạng bytecode**, không chứng minh nó đã được **biên dịch bằng một javac binary cụ thể**.

## 10. Auto-detection: Gradle tìm JDK/JRE từ đâu?

Mặc định, Gradle có thể dò các Java installations từ nhiều nguồn:

- `JAVA_HOME` và một số locations chuẩn của hệ điều hành.
- Package managers như SDKMAN!, asdf, Jabba nếu môi trường phù hợp.
- Cài đặt Java do IDE/JDK manager cung cấp.
- Gradle-managed auto-provisioned JDKs trong Gradle User Home.
- Danh sách custom paths và custom environment variables bạn khai báo.

Đọc `Detected by` trong `javaToolchains` để biết **tại sao installation xuất hiện**. Không dựa vào một `ls /usr/lib/jvm` trên Linux hoặc Windows Registry để kết luận Gradle chắc chắn đã dò được tất cả.

### 10.1. Đưa paths cụ thể cho Gradle

`gradle.properties`:

~~~properties
org.gradle.java.installations.paths=/opt/jdks/jdk-17,/opt/jdks/jdk-21
~~~

Đây là **đường dẫn ví dụ** cho môi trường Linux, phải thay bằng vị trí thực. Gradle coi chúng là **các installation candidates**, không tự tìm đệ quy bên trong mỗi thư mục. Nếu path không tồn tại, Gradle có thể bỏ qua cùng cảnh báo; không mặc nhiên tạo JDK.

Có thể dùng biến môi trường:

~~~properties
org.gradle.java.installations.fromEnv=JDK17_HOME,JDK21_HOME
~~~

Mẫu này yêu cầu bạn **đã thiết lập** hai biến môi trường trỏ tới JDK home trên máy/CI. Nó **không tự gán** JDK17_HOME/JDK21_HOME. Sau đó chạy:

~~~bash
./gradlew -q javaToolchains
~~~

Để biết Gradle có phát hiện chúng và metadata trả về gì.

**Custom paths chỉ mở rộng tập lựa chọn khi auto-detection còn bật**; chúng không mặc nhiên được ưu tiên hơn các JDK khác cùng đáp ứng spec. Quy tắc chọn toolchain thuộc matching/precedence, không phải “đường dẫn khai báo trước luôn thắng”.

### 10.2. Tắt auto-detection để điều tra

Trong `gradle.properties`:

~~~properties
org.gradle.java.installations.auto-detect=false
org.gradle.java.installations.paths=/opt/jdks/jdk-17
~~~

Hoặc dùng CLI để kiểm tra tạm:

~~~bash
./gradlew -Dorg.gradle.java.installations.auto-detect=false -q javaToolchains
~~~

Khi tắt auto-detection, Gradle vẫn có thể sử dụng những installations bạn **khai báo explicit** qua paths/fromEnv theo support của bản Gradle, cùng các nguồn phù hợp khác như JVM đang chạy Gradle. Đọc report thực tế, không giả định chỉ còn đúng một dòng.

Đừng commit `auto-detect=false` nếu tổ chức chưa có cơ chế chuẩn hóa Java homes trên mọi OS/CI: người khác có thể bị lỗi không tìm thấy JDK.

## 11. Auto-provisioning: `Auto-download: Enabled` chưa đủ

Nếu không có JDK đáp ứng yêu cầu, Gradle **có thể** tự download một JDK phù hợp, **nhưng phải có toolchain download repository/resolver được cấu hình** theo Gradle version đang dùng. Một dòng trong report:

~~~text
Auto-download: Enabled
~~~

**không chứng minh** Gradle đã có repository để tải hoặc việc tải sẽ thành công.

Những điều cần phân biệt:

1. **Auto-detection**: dò JDK/JRE đã có local.
2. **Auto-provisioning**: lấy JDK mới từ repository đã cấu hình khi không tìm được toolchain local phù hợp.
3. **Toolchain resolver plugin**: cơ chế cấu hình các repositories/resolvers để Gradle biết từ đâu download.
4. **Gradle Daemon JVM criteria**: cơ chế riêng điều khiển JVM chạy Gradle; không thể nhầm với project compile toolchain.

Một resolver phổ biến là Foojay Toolchains Plugin. Trong `settings.gradle.kts` có thể dùng plugin convention, với version được kiểm tra tại thời điểm áp dụng:

~~~kotlin
plugins {
    id("org.gradle.toolchains.foojay-resolver-convention") version "1.0.0"
}

rootProject.name = "toolchain-provisioning-demo"
~~~

Đây là **mảnh Settings để minh họa resolver**, không cần thêm vào lab nếu máy đã có JDK 17. Version `1.0.0` là mốc được tài liệu Gradle dùng làm ví dụ, không phải cam kết mới nhất. Một tổ chức có thể cấu hình resolver/repository nội bộ theo policies của mình. Việc tự tải JDK có phụ thuộc mạng, kiến trúc, repository, quyền file và điều kiện hỗ trợ vendor/version.

### Tắt auto-download khi CI bắt buộc dùng JDK cài sẵn

`gradle.properties`:

~~~properties
org.gradle.java.installations.auto-download=false
~~~

Hoặc:

~~~bash
./gradlew -Dorg.gradle.java.installations.auto-download=false -q javaToolchains
~~~

Nếu JDK 17 không có local, `compileJava` dùng Java 17 sẽ **fail resolution** thay vì tự fetch một JDK mới. Đây có thể là điều mong muốn với CI yêu cầu base image có đúng JDK đã kiểm thử.

**Lưu ý về version patch:** auto-provisioning chỉ tải JDK mới khi thiếu toolchain phù hợp; nó không bảo đảm nâng một JDK 17.0.x đã cài lên bản patch mới hơn mỗi lần chạy. Muốn kiểm soát patch/security fixes phải quản lý cài đặt JDK/container image và chính sách cập nhật.

## 12. Selection precedence: có nhiều JDK 17 thì Gradle chọn cái nào?

Gradle chọn trong **các installations phù hợp spec** và sắp thứ tự theo precedence rules. Theo tài liệu Gradle hiện hành, các tiêu chí chính gồm:

1. Installation đang chạy Gradle thường được ưu tiên nếu nó **cũng match toolchain spec**.
2. JDK được ưu tiên hơn JRE khi cả hai đáp ứng điều kiện; compiler cần JDK.
3. Vendor có thứ tự precedence đã được Gradle định nghĩa.
4. Version patch/minor mới hơn có thể được ưu tiên giữa installations cùng nhóm.
5. Path được dùng như tie-breaker để có lựa chọn ổn định.

Đây là quy tắc chọn, **không phải hợp đồng rằng Gradle luôn chọn JAVA_HOME hoặc JDK vừa được cài gần nhất**. Chính sách precedence có thể thay đổi theo Gradle version.

Ví dụ khi máy có:

~~~text
JAVA_HOME               -> Microsoft JDK 21
JDK17_HOME              -> Adoptium JDK 17.0.10
/opt/jdks/other-jdk17   -> Oracle JDK 17.0.9

Project toolchain:
  languageVersion = 17
~~~

`JAVA_HOME` là Java 21 nên **không match yêu cầu major 17** cho compiler task. Gradle chọn trong các JDK 17 hợp lệ theo vendor/version/rules, không chọn Java 21 chỉ vì JAVA_HOME trỏ vào nó.

### Chọn vendor khi cần

Trong `build.gradle.kts`:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
        vendor.set(JvmVendorSpec.ADOPTIUM)
    }
}
~~~

Đây là **phương án thêm constraint vendor**. Nếu máy chỉ có Microsoft/Oracle JDK 17 và auto-provisioning không có repository phù hợp, build có thể báo **không tìm thấy matching Java installation**. Đừng thêm vendor restriction chỉ để “đẹp log”; chỉ dùng nếu dự án thực sự yêu cầu vendor cụ thể và CI đảm bảo cài JDK đáp ứng.

### Chọn architecture

`javaToolchains` báo architecture để giúp điều tra vấn đề chạy JDK trên máy Apple Silicon, Windows ARM hay CI x86_64. Thông thường Gradle sẽ dùng toolchain phù hợp hệ điều hành/architecture hiện tại. Khi binary architecture không tương thích hoặc path trỏ sai, toolchain detection/provisioning có thể fail. Đừng copy đường dẫn macOS Java home sang Linux container.

## 13. Gradle Daemon JVM, `JAVA_HOME` và IDE settings

Khi CLI và IDE báo Java khác nhau:

### Gradle Daemon

- `./gradlew --version` phản ánh Gradle version và JVM liên quan đến launcher/daemon theo bản Gradle.
- `JAVA_HOME` có thể ảnh hưởng launcher/default JVM nếu không bị policy khác override.
- `org.gradle.java.home` trong `gradle.properties` có thể chỉ định Java home cho Gradle build process.
- **Daemon JVM criteria** trong các Gradle version hỗ trợ có thể đặt yêu cầu riêng cho JVM chạy daemon thông qua `gradle/gradle-daemon-jvm.properties`.
- Sau khi đổi JDK paths/configuration, Gradle Daemon có thể vẫn cache information cho một thời gian. Khi cần refresh có kiểm soát, có thể dừng Gradle Daemon rồi chạy lại.

Ví dụ lệnh dừng daemon (chỉ khi không làm gián đoạn build khác):

~~~bash
./gradlew --stop
./gradlew --version
./gradlew -q javaToolchains
~~~

Đừng coi việc dừng daemon là cách sửa mọi lỗi JDK. Nó làm restart build processes và có thể ảnh hưởng các Gradle builds đang chạy trên cùng máy. Trong CI/container ephemeral, cách kiểm soát image/toolchain rõ ràng thường tốt hơn việc restart liên tục.

### IntelliJ IDEA và Eclipse

IDE thường có cài đặt **Gradle JVM** riêng:

- IntelliJ IDEA: Settings/Preferences → Build, Execution, Deployment → Gradle → **Gradle JVM**.
- Eclipse/Buildship: chọn Gradle JDK phù hợp trong tùy chọn Gradle.

IDE Project SDK, language level và Gradle JVM không phải lúc nào cũng là một. Khi thấy IDE compile thành công nhưng CLI fail, so sánh:

1. Gradle Wrapper version, có dùng **wrapper** trong IDE không?
2. JVM dùng cho Gradle Daemon ở IDE và terminal.
3. Project/toolchain requirements từ `build.gradle.kts`.
4. Toolchain discovery sources/vender/architecture.
5. Có Gradle properties override từ user home/IDE/CI không?

Nếu Gradle tasks trong IDE vẫn gọi cùng Wrapper và cùng toolchain spec nhưng chạy daemon khác, compiler task vẫn có thể chọn Java 17. Điều cần so sánh là **task-selected toolchain**, không chỉ IDE Java icon.

## 14. Test runtime khác compiler: một trường hợp rất thực tế

Giả sử library phải compile bằng Java 17 nhưng cần test trên Java 21 để kiểm thử forward compatibility:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.named<Test>("test") {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(21))
    })
}
~~~

Đây là **mảnh cấu hình thay thế**, không dùng cùng test `testsRunOnJava17()` vì test đó assert Java 17. Trong cấu hình này:

- `compileJava` vẫn dùng Java 17 theo project toolchain.
- `test` khởi chạy process bằng Java 21.
- `javaToolchains` có thể báo cả JDK 17 và 21, nhưng không tự nói rằng task `test` đã override.
- Test muốn kiểm chứng `21` phải assert `Runtime.version().feature() == 21`.

Đó là lý do một **test tự in system properties** có giá trị hơn một checklist “máy đã cài Java 21”. Khi thiết lập test matrix CI với Java 17/21, hãy rõ ràng task nào dùng version nào.

### `JavaExec` task tùy chỉnh

Gradle chỉ tự nối toolchain convention đầy đủ cho các tasks do Java plugins quản lý hoặc được cấu hình đúng. Nếu bạn tạo một `Exec` task gọi string `"java"` từ PATH, nó có thể chạy bằng JVM khác:

~~~kotlin
tasks.register<Exec>("runSystemJava") {
    commandLine("java", "-version")
}
~~~

Đây là **phản ví dụ về reliability**: `Exec` gọi external process theo PATH; nó không tự tuân theo `java.toolchain.languageVersion`. Nếu cần chạy một Java main class theo toolchain, dùng `JavaExec` và `javaLauncher.set(...)` như mục 8.

## 15. Gradle 17 compiler nhưng Java 21 classpath: khi nào là lỗi?

Một số tình huống:

| Triệu chứng | Bằng chứng | Nguyên nhân/giải pháp |
| --- | --- | --- |
| `java -version` in 21, app in 17 | PATH java khác app launcher. | **Không phải lỗi** nếu toolchain 17 được cấu hình. |
| `./gradlew --version` in daemon 21, `compileJava` dùng JDK 17 | Daemon/toolchain tách biệt. | **Không phải lỗi** nếu Gradle chạy được trên 21. |
| `javaToolchains` có JDK 17 nhưng `compileJava` dùng 21 | Task override compiler, project spec thiếu hoặc plugin custom không nối toolchain. | Kiểm tra `javaCompiler` property, rules trong plugins/tasks. |
| `test` in Java 21 dù app yêu cầu Java 17 | Test `javaLauncher` có override hoặc custom test task không kế thừa. | Xem task-specific launcher, test worker logs. |
| `JavaCompile` không chạy | `UP-TO-DATE` hoặc `FROM-CACHE`. | Dùng `--rerun-tasks --info` khi cần bằng chứng execution mới. |
| `javap` cho major 65 nhưng dự án yêu cầu 17 | Bytecode phát hành Java 21. | Kiểm tra `options.release`, compiler task, stale class, jar nguồn. |
| `No matching toolchains found` | Gradle không phát hiện JDK phù hợp và không provision được. | Xem `javaToolchains`, custom paths, vendor, resolver. |
| `Is JDK: false` cho Java 17 | JRE không có compiler javac. | Cài JDK đầy đủ; đừng dùng JRE cho compile task. |
| IDE chạy được, CLI fail | Daemon/JDK/Gradle versions/repository khác. | So sánh Wrapper, Gradle JVM, `javaToolchains`. |
| CI Linux fail nhưng macOS chạy | JDK image/path/architecture/permission khác. | Cài đúng JDK trong CI hoặc resolver, tránh hard-coded paths. |
| Toolchain đã đổi nhưng log còn path cũ | Daemon cache, task cached, property override. | Xem spec/metadata, `--rerun-tasks`, dừng daemon có kiểm soát khi cần. |
| Cấu hình `targetCompatibility=17` nhưng dùng Java 21 API | Target bytecode không chặn toàn bộ API mới. | Dùng `options.release.set(17)` khi compile bằng javac mới. |
| Plugin riêng gọi `java` từ PATH | Plugin không nối `JavaToolchainService`. | Sửa plugin để dùng `JavaLauncher` provider. |

## 16. Troubleshooting: không tìm được JDK 17

Khi Gradle báo không có Java toolchain phù hợp, xử lý theo thứ tự:

1. Chạy `./gradlew -q javaToolchains` xem JDK 17 có xuất hiện không.
2. Nếu có Java 17 nhưng `Is JDK: false`, đó có thể là JRE; cần **JDK có compiler** cho `compileJava`.
3. Kiểm tra `Language Version`, `Vendor`, `Architecture` và `Detected by` có khớp spec không.
4. Đảm bảo path trỏ tới **JDK home**, không phải chỉ tới thư mục `bin` hay file `java.exe`.
5. Kiểm tra `org.gradle.java.installations.auto-detect` có bị tắt trong user/project `gradle.properties` không.
6. Nếu dùng `fromEnv`, kiểm tra biến thật sự được export vào process chạy Gradle.
7. Nếu cần auto-provisioning, kiểm tra **toolchain resolver plugin/repositories** và quyền truy cập mạng. `Auto-download Enabled` là chưa đủ.
8. Nếu dự án bắt buộc offline, cài sẵn JDK 17 trong image/container và cấu hình path thống nhất.
9. Kiểm tra bản Gradle Wrapper có hỗ trợ chạy trên JDK của daemon và API toolchains bạn dùng không.
10. Chạy `compileJava --info --stacktrace --rerun-tasks` để lấy lỗi gốc thay vì chỉ thấy summary.
11. Nếu mới cài JDK và Gradle không nhận, kiểm tra daemon cache, cân nhắc `./gradlew --stop` rồi chạy lại.
12. Không đổi yêu cầu `JavaLanguageVersion.of(17)` thành 21 chỉ để “build xanh” nếu sản phẩm có contract Java 17.

### Ví dụ xác minh custom JDK path

Trên Linux nếu JDK được cài ở `/opt/jdks/jdk-17`, có thể chạy:

~~~bash
/opt/jdks/jdk-17/bin/java -version
/opt/jdks/jdk-17/bin/javac -version
./gradlew -q javaToolchains
./gradlew compileJava --info --rerun-tasks
~~~

Đây là **đường dẫn giả định** của một môi trường thử; không phải mệnh lệnh hợp lệ trên tất cả máy. Nếu installation path sai, sửa ngay `gradle.properties` hoặc CI image provisioning trước khi chạy compile.

## 17. Quản trị logs và chứng cứ trong CI

Để dễ điều tra lỗi “works on my machine”, lưu ít nhất:

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew compileJava test --rerun-tasks --info
./gradlew -q run
~~~

Trong môi trường thực, đừng bắt mọi pipeline chạy `--rerun-tasks` liên tục vì sẽ **mất lợi ích incremental/cache** và tốn chi phí. Cách hiệu quả:

- Build thường dùng cache như bình thường.
- Một job chẩn đoán hoặc khi sự cố mới dùng `--rerun-tasks --info`.
- Ghi version và JDK home chỉ ở mức cần thiết; không tiết lộ path/username/secret khi chia sẻ ra ngoài.
- Nếu cần bằng chứng dạng máy đọc, tạo task diagnostic có các field rõ ràng (compiler/test/run languageVersion và installationPath).
- Pin Gradle Wrapper; xác định container image/JDK vendor/patch version theo chính sách.
- Đối với thư viện cần tương thích nhiều JDK, chạy test matrix cho Java 17/21 và lưu output theo từng job.
- Định kỳ kiểm tra JDK patch/security updates; Gradle toolchain version thường chỉ cố định **major** trừ khi bạn có chính sách installation/vendor chi tiết.

Không gọi một report `javaToolchains` là “bằng chứng đã compile bằng đúng JDK” nếu không chạy compile task hoặc kiểm tra task property. Đó chỉ là báo cáo **những công cụ có thể được chọn**.

## 18. Sự khác nhau giữa toolchain requirement, selected tool và runtime evidence

Một checklist ba tầng:

| Tầng | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| **Khai báo** | Build yêu cầu Java gì? | `java.toolchain`, task `javaCompiler`/`javaLauncher`, `options.release`. |
| **Lựa chọn** | Gradle chọn installation nào? | `javaToolchains` inventory + task properties/log `--info`. |
| **Thực thi** | Code/test chạy trên JVM nào, bytecode là gì? | `Runtime.version().feature()`, `java.home`, `javap -verbose`. |

Một lỗi chỉ được chẩn đoán chính xác khi biết tầng nào sai:

- Khai báo sai → sửa build script và conventions.
- Inventory sai → sửa detection/provisioning/CI image.
- Selected tool sai → xem task-specific overrides, precedence/vendor/implementation.
- Runtime khác mong đợi → xem forked JVM/JavaExec/Test configuration hoặc custom `Exec`.
- Bytecode/API target sai → kiểm tra `options.release`, stale outputs và compiler arguments.

## 19. Câu hỏi tự kiểm tra

1. **`javaToolchains` báo gì?** Danh sách Java installations Gradle phát hiện với metadata như languageVersion, vendor, path, JDK/JRE và nguồn phát hiện.
2. **Có thể kết luận `compileJava` dùng JDK 17 chỉ vì report có JDK 17 không?** Không, cần spec và selected task tool.
3. **Gradle Daemon chạy Java 21, compiler Java 17 có hợp lệ không?** Có, toolchains tách compile/runtime khỏi daemon.
4. **`JAVA_HOME` có tự quyết định compiler của mọi task không?** Không nếu có Java toolchain/task override.
5. **`--rerun-tasks` để làm gì trong chẩn đoán?** Buộc task thực thi lại để tránh chỉ thấy `UP-TO-DATE`/cache.
6. **`--info` có một dòng “Compiling with toolchain ...” bất biến không?** Không, nội dung log thay đổi theo Gradle/plugin/version.
7. **Làm sao biết test process chạy Java 17?** In `Runtime.version().feature()` trong test và/hoặc xem `Test.javaLauncher`.
8. **`javap -verbose` với major 61 chứng minh điều gì?** Class file target Java 17, **không** chứng minh đường dẫn javac đã dùng.
9. **`Auto-download Enabled` có bảo đảm Gradle tự tải JDK?** Không, cần resolver/repository phù hợp và truy cập được.
10. **`Is JDK: false` có phù hợp cho compilation không?** Thường không; JavaCompile cần JDK/compiler.
11. **`org.gradle.java.installations.paths` được Gradle dùng thế nào?** Danh sách candidates; không tự ưu tiên hơn auto-detected installations.
12. **`fromEnv=JDK17_HOME` có tự tạo biến môi trường không?** Không, biến phải được cài ở shell/CI.
13. **Vì sao phải lưu vendor và architecture?** Nhiều JDK cùng major có thể khác implementation/ABI/behavior, đặc biệt CI và plugin native.
14. **`targetCompatibility=17` có khóa API Java 17 không?** Không hoàn toàn khi compile bằng javac mới; dùng `options.release.set(17)` để giới hạn APIs.
15. **Nếu task `Exec` gọi `java` từ PATH, nó tự dùng Java toolchain không?** Không; dùng `JavaExec.javaLauncher` khi cần.
16. **Khi nào nên chạy `./gradlew --stop`?** Khi cần refresh daemon-cached JDK settings và chấp nhận ảnh hưởng đến các builds khác.
17. **CI nên bật `--rerun-tasks` trên mọi build để kiểm tra toolchain?** Không, chỉ ở job chẩn đoán vì tốn thời gian.
18. **Toolchain report có tự bảo đảm mọi plugin Kotlin/Groovy/Scala compiler dùng cùng JDK không?** Không; cần xem tasks/plugin-specific conventions.
19. **Nếu Java main in feature 17 nhưng test in 21, nguyên nhân có thể là gì?** Test `javaLauncher` được override hoặc custom test task dùng JDK khác.
20. **Bộ bằng chứng tối thiểu khi bug “wrong JDK” là gì?** Wrapper/daemon version, `javaToolchains` report, task-level compiler/launcher, runtime probe và bytecode target nếu liên quan.

## 20. Checklist thực hành cuối

- [ ] Dùng **Gradle Wrapper** để tránh phụ thuộc Gradle global.
- [ ] Kiểm tra `./gradlew --version` và phân biệt launcher/daemon JVM.
- [ ] Chạy `./gradlew -q javaToolchains` để kiểm tra detected toolchains.
- [ ] Đọc `Language Version`, `Vendor`, `Architecture`, `Location`, `Is JDK`, `Detected by`.
- [ ] Không suy rằng JDK trong inventory là JDK task đã dùng.
- [ ] Đặt `java.toolchain.languageVersion` đúng product contract.
- [ ] Nếu cần API target cũ, dùng `options.release` và kiểm tra class-file major.
- [ ] Dùng `compileJava --rerun-tasks --info` khi cần chứng minh compiler thực thi.
- [ ] Dùng `test --rerun-tasks --info` và runtime probe để chứng minh test JVM.
- [ ] Với Application/JavaExec, đo runtime bằng `Runtime.version()` và `java.home`.
- [ ] Xem task-specific `javaCompiler`/`javaLauncher` khi log chưa rõ.
- [ ] Kiểm soát `auto-detect`/`auto-download`/`fromEnv`/`paths` trong CI.
- [ ] Không tin `Auto-download Enabled` là chắc chắn có resolver.
- [ ] Khi IDE khác CLI, so sánh Gradle JVM, toolchain specs và Wrapper.
- [ ] Không công bố logs chứa credentials, user paths hoặc thông tin nhạy cảm.
- [ ] Lưu log chẩn đoán và kiểm thử trên các JDK thực sự hỗ trợ.

## Tài liệu chính thức

- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html): project/task toolchains, `javaToolchains`, detection, provisioning, precedence và custom paths.
- [Gradle — Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html): `org.gradle.java.home`, `org.gradle.java.installations.*`, Gradle JVM và properties.
- [Gradle — Gradle Daemon](https://docs.gradle.org/current/userguide/gradle_daemon.html): JVM chạy Gradle, Daemon JVM criteria và vòng đời daemon.
- [Gradle — Building Java Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): Java toolchains, compiler, `--release` và source/target compatibility.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): `--info`, `--stacktrace`, `--rerun-tasks` và `--offline`.
- [Gradle — Java Toolchain Service](https://docs.gradle.org/current/javadoc/org/gradle/jvm/toolchain/JavaToolchainService.html): `compilerFor`, `launcherFor`, `javadocToolFor`.
- [Gradle — JavaCompile Task](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.compile.JavaCompile.html): `javaCompiler`, options và task execution.
- [Gradle — Test Task](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html): `javaLauncher` và test logging.
- [Gradle — JavaExec Task](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.JavaExec.html): Java launcher và runtime classpath.
- [Gradle — Toolchain Resolver Plugins](https://docs.gradle.org/current/userguide/toolchain_plugins.html): cách cấu hình repository để tự provision JDK.

# Chọn Gradle JVM và cơ chế build, chạy test trong IDE

Một dự án Gradle có thể chạy `./gradlew test` thành công trên terminal nhưng lại báo lỗi khi mở trong IntelliJ IDEA: IDE dùng **JDK khác** để chạy Gradle, chọn compiler riêng của IDE thay vì Gradle, hoặc chạy JUnit trực tiếp thay cho `Test` task được cấu hình trong `build.gradle.kts`. Ngược lại, có khi nút Run ở IDE chạy được nhưng CI thất bại, vì IDE đã “giúp” tạo classpath/generate source/VM options mà Gradle build thực tế chưa khai báo.

Bài thuộc phần **IDE và chẩn đoán** của chủ đề *Build Tool Gradle*, tập trung vào câu hỏi **“Chọn Gradle JVM và cơ chế build, chạy test trong IDE”**. Nội dung dùng **IntelliJ IDEA** làm ví dụ chính (phù hợp với Java 17 + Gradle Kotlin DSL), rồi đối chiếu ngắn với **Eclipse Buildship** và **VS Code**. Sau bài, bạn có thể phân biệt Gradle version, Gradle Client JVM, Gradle Daemon JVM, IDE Project SDK, Java Toolchain, Test JVM và JRE của Run configuration; chọn đúng giữa Gradle builder/test runner và runner của IDE; đối chiếu stdout, test reports, task graph và xử lý các lỗi môi trường phổ biến.

Các bước IDE tham chiếu IntelliJ IDEA 2026.x và Gradle 9.x (tài liệu Gradle hiện hành 9.9.0, phát hành 07/11/2026). Giao diện có thể đổi theo edition/phiên bản; luôn ưu tiên tên tùy chọn và ý nghĩa hơn vị trí pixel trong ảnh.

## 1. Sơ đồ: trong một dự án có thể tồn tại nhiều JVM

~~~text
IntelliJ IDEA process
  ├─ IDE runtime (JetBrains Runtime)
  ├─ Project SDK / Module SDK
  │    └─ phục vụ editor, code insight, một số IDE run configs
  └─ Gradle integration (Tooling API)
       └─ Gradle Client JVM / Gradle JVM selection
            └─ Gradle Daemon JVM
                 ├─ Gradle build scripts + plugins
                 ├─ JavaCompile toolchain: javac JDK 17
                 ├─ Test task Java launcher: test worker JDK 17
                 └─ Application run task: Java launcher JDK 17

Terminal:
  JAVA_HOME / java trên PATH
       └─ ./gradlew launcher
            └─ Gradle Daemon JVM theo cấu hình build
                 ├─ JavaCompile ...
                 ├─ Test ...
                 └─ run ...
~~~

**Gradle Wrapper** lại là một yếu tố khác: nó quyết định **Gradle distribution/version**, không quyết định duy nhất Java version. Một build có thể dùng Gradle 9.9 trên **Gradle Daemon JDK 21**, nhưng vẫn compile và chạy tests trên **Java 17 toolchain**. IDE Project SDK có thể là JDK 17, JDK 21 hoặc một lựa chọn khác, nhưng task compilation thuộc Gradle sẽ dùng toolchain nếu build script khai báo đúng.

### Sáu khái niệm không được đánh đồng

| Thành phần | Ai/đâu cấu hình? | Dùng để làm gì? | Có quyết định JavaCompile khi toolchain đã set? |
| --- | --- | --- | --- |
| **IDE runtime** | IntelliJ/JBR installation | Chạy giao diện IDE và các plugin IDE | Không |
| **Project/Module SDK** | Project Structure / Gradle import model | IDE indexing, language level, IDE compiler / run configurations | Không chắc; khi build Gradle được ủy quyền, toolchain Gradle ưu tiên |
| **Gradle distribution** | `gradle-wrapper.properties` / IDE Distribution | Phiên bản Gradle engine/API/plugins | Không, đây không phải JDK |
| **Gradle Client JVM** | Shell `JAVA_HOME`/`PATH`, IDE Tooling API | Khởi động launcher/client kết nối Daemon | Không |
| **Gradle Daemon JVM** | IDE Gradle JVM, `org.gradle.java.home`, Daemon JVM criteria | Thực thi Gradle scripts và plugin code | Không khi Java toolchain riêng đã được xác định |
| **Java toolchain / Test launcher** | `java.toolchain`, `tasks.test.javaLauncher` | `javac`, Javadoc, forked Java tests/JavaExec | Có |

Một **Run configuration JRE/JDK** của IntelliJ còn là tầng thứ bảy khi bạn chọn chạy ứng dụng trực tiếp bằng IDEA, không qua Gradle `run`. Nó có thể khác JVM chạy trong `./gradlew run`.

## 2. Đặt một chuẩn so sánh: terminal dùng Wrapper

Trước khi chỉnh IDE, ở **root project** chạy:

~~~bash
java -version
./gradlew --version
./gradlew javaToolchains
./gradlew test
~~~

Windows PowerShell:

~~~powershell
java -version
.\gradlew.bat --version
.\gradlew.bat javaToolchains
.\gradlew.bat test
~~~

Ý nghĩa:

- `java -version`: JDK/JRE shell đang tìm trên `PATH`, **chưa chắc là Gradle Daemon JVM**.
- `./gradlew --version`: Gradle version và thông tin Java dùng cho launcher/daemon tùy phiên bản. Ở Gradle mới, output có thể hiển thị **Launcher JVM** và **Daemon JVM** riêng.
- `javaToolchains`: Gradle liệt kê JDKs nhận diện được và paths tương ứng, giúp kiểm tra JDK 17 có sẵn không.
- `test`: chạy **Gradle Test task** với dependency graph và task configuration thật, chuẩn tốt để đối chiếu với IDE.

**Không dùng `gradle --version` thay `./gradlew --version`** nếu mục tiêu là kiểm tra version dự án đã pin. Lệnh `gradle` trên `PATH` có thể trỏ một Gradle installation khác hoàn toàn.

Để giảm nhiễu khi so sánh, ghi nhận: Wrapper distribution URL, `JAVA_HOME` của terminal, JDK mà IDE Gradle JVM chọn, project `java.toolchain`, và runner hiện tại (`Gradle` hay `IntelliJ IDEA`).

## 3. Gradle JVM KHÁC Java Toolchain

Ví dụ trong `build.gradle.kts`:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

Gradle khi cấu hình Java tasks sẽ tìm Java 17 toolchain để compile/test/Javadoc theo plugin semantics. **Đây không phải lệnh buộc Gradle Daemon chạy bằng Java 17**. Nếu Daemon đang chạy JDK 21 nhưng Gradle hỗ trợ Java 21, `compileJava` vẫn có thể dùng `javac` JDK 17.

Ngược lại, nếu bạn chỉ thay **Gradle JVM** trong IDE thành JDK 17 mà **không khai báo Java toolchain**, project chưa có bảo đảm tất cả machines/CI sẽ compile và chạy tests bằng đúng JDK 17. Khi có nhiều Java installations, IDE/CLI khác nhau có thể tạo hành vi khác nhau.

### Quy tắc thực hành

- **Gradle JVM/Daemon JVM** phải tương thích **phiên bản Gradle Wrapper** và plugins chạy trong buildscript.
- **Java toolchain** phải phù hợp target Java API/compiler/runtime mà dự án yêu cầu.
- **IDE Project SDK** nên align với toolchain về code insight/language level khi khả thi, nhưng không thay thế cấu hình toolchain được version-control.
- **IDE runner JRE** phải được chọn riêng nếu bạn cố tình chạy `main()`/JUnit **không qua Gradle**.
- Nếu muốn phát hành bytecode dành cho Java cũ hơn JDK toolchain, dùng `options.release` để kiểm soát Java API/classfile thay vì chỉ `sourceCompatibility/targetCompatibility`.

### Chú ý Gradle 9.x

Gradle 9.0 trở lên yêu cầu **JVM 17+ cho Gradle Daemon**. Gradle Wrapper launcher và một số Tooling API clients có thể có runtime compatibility khác; xem [Gradle Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html) theo chính phiên bản Wrapper. Không suy rằng “mới hơn luôn tốt hơn”: JDK vừa phát hành có thể chưa được bản Gradle cũ hỗ trợ để **chạy Daemon**, dù đã hỗ trợ làm **toolchain**.

Ví dụ thực tế hợp lệ khi compatibility matrix cho phép:

~~~text
IDE Project SDK          = JDK 17
IDE Gradle JVM / Daemon  = JDK 21
Gradle Wrapper           = Gradle 9.9
JavaCompile toolchain    = JDK 17
Test.javaLauncher        = JDK 17
Application :run         = JDK 17
~~~

Không phải tất cả các trường phải bằng nhau, nhưng cần **giải thích vì sao khác nhau** và kiểm thử cùng các phiên bản bạn hỗ trợ.

## 4. Chọn Gradle distribution: dùng Wrapper chứ không dùng IDE cài sẵn

Trong IntelliJ IDEA, mở:

**Settings/Preferences → Build, Execution, Deployment → Build Tools → Gradle**.

Ở phần **Distribution / Use Gradle from**, ưu tiên lựa chọn **Gradle Wrapper** hoặc **`gradle-wrapper.properties` file** (tên hiển thị tùy phiên bản). Điều này để IDE dùng version ghi trong:

~~~text
gradle/wrapper/gradle-wrapper.properties
~~~

Một mẫu minh họa về nội dung thuộc tính:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.9.0-bin.zip
~~~

Đây là **mảnh properties minh họa**; không phải toàn bộ file được tạo bởi Wrapper. Các dòng chứa backslash trong URL là cách properties escape dấu hai chấm, không phải URL bắt đầu bằng `https\://` ở trình duyệt. Khi bootstrap project mới, dùng Gradle `wrapper` task tạo files đúng chuẩn thay vì tự viết JAR/sha.

Nếu dùng **Specified location** trong IDE, nó có thể dùng một Gradle khác với Wrapper của repository, gây sai API/plugin compatibility. Chỉ dùng lựa chọn này khi có lý do được tài liệu hóa (ví dụ thử upgrade/điều tra).

### Kiểm tra phiên bản trong IDE

Trong IntelliJ IDEA:
1. Mở Gradle tool window, chọn project đúng.
2. Chạy task `help` hoặc `--version` qua Gradle run configuration/IDE Gradle terminal phù hợp.
3. So với `./gradlew --version` từ terminal tại cùng root.
4. Nếu lệch, kiểm tra linked project và **Distribution**, không vội sửa `JAVA_HOME`.

**Đổi Wrapper version ≠ đổi Gradle JVM.** Một cái là Gradle engine, cái kia là Java runtime để chạy Gradle.

## 5. Cấu hình Gradle JVM trong IntelliJ IDEA

Theo tài liệu JetBrains, vào:

**Settings/Preferences → Build, Execution, Deployment → Build Tools → Gradle**.

Với **Gradle projects** có nhiều linked builds, chọn đúng project trước. Tìm trường **Gradle JVM** (hoặc Gradle JVM Criteria khi Daemon JVM toolchain support được bật).

Chọn JDK đang cài phù hợp với Gradle Wrapper; ví dụ JDK 17 để dễ đồng nhất với dự án Java 17, hoặc JDK 21 nếu Gradle version và plugins hỗ trợ và tổ chức đã chọn chuẩn JDK 21 cho build process.

Sau khi đổi:
1. Apply/OK.
2. **Reload/Sync Gradle Project** từ Gradle tool window.
3. Chạy một task nhẹ, như `help` hoặc diagnostic `showGradleRuntime` trong ví dụ.
4. Quan sát Gradle version/JVM trên console và so CLI.

**Không cho rằng IDE Project SDK = Gradle JVM** trong mọi trường hợp. JetBrains có thể dùng Project SDK làm giá trị mặc định, nhưng người dùng/Gradle JVM criteria/build properties có thể override.

### IDE Project SDK nằm ở đâu?

Thường trong **File → Project Structure → Project → SDK**. Đây là lựa chọn cho code insight và IDE project model, và có thể ảnh hưởng direct IDEA compile/run. Khi Gradle build script khai báo Java toolchain, source/target model sẽ được IDE import theo Gradle; đừng sửa IDE language level thủ công rồi tưởng đã thay đổi compiler Gradle ở CI.

### Ưu tiên xem trong settings khi chọn JVM

Ở phiên bản JetBrains hiện tại, **Gradle JVM** là lựa chọn cho JVM dùng khi IDE import và chạy tasks. **Gradle JVM Criteria** hiện khi Daemon JVM toolchain support được bật. Ngoài ra Gradle có tiêu chí daemon riêng ở `gradle/gradle-daemon-jvm.properties`. Khi cả hai cơ chế tồn tại, đừng tự suy ra chỉ từ một dropdown rằng Daemon chắc chắn chạy JVM đó; hãy quan sát actual output/daemon JVM và đọc quy tắc Gradle/IDE phiên bản đang dùng.

## 6. Daemon JVM selection: `JAVA_HOME`, `org.gradle.java.home` và criteria

Không có Daemon JVM criteria riêng, Gradle thường dùng JVM từ launcher/shell hoặc thiết lập explicit như:

~~~properties
# gradle.properties (mảnh, máy cục bộ):
org.gradle.java.home=/absolute/path/to/jdk-17
~~~

**Không commit đường dẫn tuyệt đối phụ thuộc máy** (`C:\Program Files\...` hay `/Users/...`) vào shared project `gradle.properties`. Nó có thể khiến CI/đồng đội lỗi dù JDK đã được cài ở path khác.

Ở Gradle mới, Daemon JVM criteria có thể được tạo bằng:

~~~bash
./gradlew updateDaemonJvm --jvm-version=17
~~~

Lệnh tạo/cập nhật:

~~~text
gradle/gradle-daemon-jvm.properties
~~~

với JVM version criteria và có thể có vendor/URL metadata. **Nếu file criteria đã được cung cấp**, Gradle tài liệu hóa rằng daemon criteria **ưu tiên hơn `JAVA_HOME` và `org.gradle.java.home`** để chọn Daemon. Bạn có thể commit file này theo project khi đã thống nhất và cấu hình provisioning/availability hợp lý. Nếu JDK không có sẵn và auto-provisioning chưa được cấu hình, lệnh build có thể fail thay vì tự tải.

Để kiểm tra **Daemon thực sự dùng Java nào**:

~~~bash
./gradlew --version
./gradlew showGradleRuntime
~~~

Lệnh thứ hai chỉ chạy được khi bạn đã thêm diagnostic task ở phần ví dụ. Đừng dựa vào `java -version` ngoài terminal như nguồn duy nhất.

### Gradle client và Gradle daemon

Gradle client là process do Wrapper/Tooling API khởi động; Gradle Daemon là process chạy build scripts/tasks và tái dùng state giữa invocations. Gradle có thể giữ **nhiều Daemons** nếu yêu cầu Java version/JVM args khác nhau. Vì vậy thấy nhiều Java processes không tự chứng minh có leak.

Thử:

~~~bash
./gradlew --status
./gradlew --stop
~~~

`--status` xem Daemons; `--stop` dừng daemons do phiên bản Gradle tương ứng quản lý, phù hợp khi điều tra daemon stale, nhưng **không phải bước đầu bắt buộc mỗi khi IDE Gradle Sync lỗi**. Dừng Daemon không sửa configuration sai và có thể làm lần build sau chậm hơn.

## 7. Ví dụ hoàn chỉnh: Java 17 + JUnit + Gradle Test task

Mục tiêu của ví dụ là có **một dự án tự chạy được**, và một test thể hiện sự khác biệt giữa:
- Chạy `Gradle Test task`: áp dụng `tasks.test.systemProperty`.
- Chạy **IntelliJ IDEA JUnit runner**: có thể không áp dụng system properties/filters/fork options của Gradle `Test` task khi IDE runner tự khởi động JVM.

### 7.1. Cây thư mục

~~~text
ide-gradle-jvm-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/demo/app/
    │   ├── Calculator.java
    │   └── Main.java
    └── test/java/demo/app/
        ├── CalculatorTest.java
        └── GradleTestPolicyTest.java
~~~

Yêu cầu: Gradle Wrapper tương thích Java 17 và JDK 17 đã cài/được toolchain provisioning. Maven Central cần truy cập để tải JUnit lần đầu. Cấu trúc package/path phải đúng, không bỏ Wrapper JAR khỏi VCS.

### 7.2. `settings.gradle.kts`

~~~kotlin
rootProject.name = "ide-gradle-jvm-demo"
~~~

### 7.3. `build.gradle.kts` — đầy đủ

~~~kotlin
plugins {
    application
}

group = "demo"
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
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

application {
    mainClass.set("demo.app.Main")
}

tasks.test {
    useJUnitPlatform()

    // Chính Gradle Test task truyền VM property vào forked test JVM.
    systemProperty("demo.test.mode", "gradle-runner")

    testLogging {
        events("passed", "failed", "skipped")
    }
}

// Diagnostic task: cố ý không cacheable, chỉ in Daemon runtime.
tasks.register("showGradleRuntime") {
    doLast {
        println("Daemon Java feature: " + Runtime.version().feature())
        println("Daemon Java home: " + System.getProperty("java.home"))
    }
}
~~~

**Giải thích các lựa chọn:**

- `application` tạo Java plugin và `run` task để khởi chạy main class.
- Java toolchain yêu cầu JDK 17 cho Java tasks. Nếu IDE Gradle JVM/Daemon khác JDK17 nhưng Gradle hỗ trợ, Java compiler/test worker vẫn theo toolchain khi build được cấu hình đúng.
- JUnit BOM pin version các artifacts cùng nền tảng; `junit-jupiter` và `junit-platform-launcher` đủ để Gradle phát hiện/chạy JUnit 5 tests.
- `useJUnitPlatform()` là cấu hình thuộc **Gradle Test task**.
- `systemProperty("demo.test.mode", "gradle-runner")` chỉ định **Java system property trong test worker JVM** do Gradle khởi tạo, không nhất thiết có trong JVM của IDEA JUnit runner.
- `testLogging` chỉ làm console hiển thị pass/fail/skipped events; không thay assertion.
- `showGradleRuntime` in thông tin **Gradle Daemon JVM**, không phải Java toolchain. Task này không có output file nên là diagnostic task chạy khi gọi, không nên cố cache nó.

### 7.4. `src/main/java/demo/app/Calculator.java`

~~~java
package demo.app;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int left, int right) {
        return left + right;
    }
}
~~~

### 7.5. `src/main/java/demo/app/Main.java`

~~~java
package demo.app;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(
            "2 + 3 = " + Calculator.add(2, 3)
        );
    }
}
~~~

### 7.6. `src/test/java/demo/app/CalculatorTest.java`

~~~java
package demo.app;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

public final class CalculatorTest {

    @Test
    void addsTwoIntegers() {
        assertEquals(5, Calculator.add(2, 3));
    }

    @Test
    void addsNegativeInteger() {
        assertEquals(-1, Calculator.add(2, -3));
    }
}
~~~

### 7.7. `src/test/java/demo/app/GradleTestPolicyTest.java`

~~~java
package demo.app;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

public final class GradleTestPolicyTest {

    @Test
    void receivesGradleTestConfiguration() {
        assertEquals(
            "gradle-runner",
            System.getProperty("demo.test.mode")
        );
    }
}
~~~

Bài test này là một **thử nghiệm có chủ đích**: nó yêu cầu property do **Gradle Test task** cung cấp. Trong lệnh Gradle CLI và IDE khi `Run tests using: Gradle`, property được truyền vào test worker. Nếu IDE chạy JUnit trực tiếp mà không truyền `-Ddemo.test.mode=gradle-runner`, test này có thể fail. Đó **không phải bug Java code**, mà là hai runner có contract khác nhau. Bạn có thể cấu hình VM options tương đương cho IDEA runner, nhưng với dự án phụ thuộc vào nhiều Gradle-specific test settings, dùng Gradle runner thường an toàn hơn.

### 7.8. Chạy bằng Gradle CLI

Bash:

~~~bash
./gradlew clean test
./gradlew run --quiet
./gradlew showGradleRuntime --quiet
~~~

PowerShell:

~~~powershell
.\gradlew.bat clean test
.\gradlew.bat run --quiet
.\gradlew.bat showGradleRuntime --quiet
~~~

**Stdout của Java Main**:

~~~text
2 + 3 = 5
~~~

Với Gradle `test`, **ba tests** trong hai classes phải PASS, với điều kiện dependency resolution/JDK thành công. Output console có thể hiển thị:

~~~text
CalculatorTest > addsTwoIntegers() PASSED
CalculatorTest > addsNegativeInteger() PASSED
GradleTestPolicyTest > receivesGradleTestConfiguration() PASSED
~~~

Đây là **dạng test logging minh họa**, thứ tự và formatting do Gradle/JUnit phiên bản chọn; không so sánh các dòng log byte-for-byte. `showGradleRuntime` in:

~~~text
Daemon Java feature: <actual integer>
Daemon Java home: <actual JDK path>
~~~

Hai dòng này **chỉ là mẫu có phần biến đổi**, không phải stdout cố định: feature có thể là 17, 21 hoặc một version được Gradle hỗ trợ; Java home là path máy đang dùng. Không bịa một đường dẫn Windows/macOS/CI cụ thể.

### 7.9. Chạy một test class hoặc method

~~~bash
./gradlew test --tests "demo.app.CalculatorTest"
./gradlew test --tests "demo.app.CalculatorTest.addsTwoIntegers"
./gradlew test --tests "*GradleTestPolicyTest"
~~~

Đây là Gradle **test filtering**, không phải shell invocation của IntelliJ IDEA. Khi chạy một method qua gutter với **Gradle runner**, IDE thường tạo một Gradle test run configuration tương đương với filter phù hợp.

Gradle cũng có:

~~~bash
./gradlew test --rerun-tasks
~~~

để ép thực thi tasks và bỏ up-to-date checks; dùng khi điều tra, không áp dụng mọi lần chạy vì làm mất incremental optimization. Từ Gradle 9.9, filtering đã được cải tiến cho JUnit Platform tests có cấu trúc đặc biệt, nhưng vẫn nên kiểm chứng test list/rerun theo framework bạn dùng.

### 7.10. Reports và cache outcomes

Sau `test`:

~~~text
build/reports/tests/test/index.html
build/test-results/test/TEST-demo.app.CalculatorTest.xml
build/test-results/test/TEST-demo.app.GradleTestPolicyTest.xml
~~~

Đây là **đường dẫn Gradle Test task dự kiến**. IDEA JUnit runner có cửa sổ test UI và có thể có result files riêng; nó **không mặc nhiên** ghi đúng vào `build/test-results/test` theo Gradle Test task contract.

Với lần chạy thứ hai không đổi:

~~~bash
./gradlew test
~~~

`test` có thể `UP-TO-DATE` hoặc `FROM-CACHE` (nếu cache phù hợp), nên nó **không nhất thiết rerun test methods**. Nhưng khi nhấp gutter “Run test” trong IntelliJ và dùng Gradle runner, IDE có tính năng **Run as test** để yêu cầu test run lại mặc dù Gradle task có thể otherwise up-to-date. Đừng nhầm một test task skipped với “IDE không phát hiện test”.

## 8. Import dự án trong IntelliJ IDEA đúng cách

Để IDE nhận **Gradle model**:

1. Chọn **File → Open** và trỏ tới thư mục chứa `settings.gradle.kts` (hoặc chọn file build script/Gradle project hợp lệ).
2. Chấp nhận **Load/Import as Gradle Project** khi IDE hỏi. Với untrusted project, chỉ bật execution sau khi xem nguồn build scripts, vì Gradle scripts/plugins là mã thực thi.
3. Mở **Gradle tool window**; kiểm tra thấy root project `ide-gradle-jvm-demo` và các tasks.
4. Mở Gradle settings, chọn **Distribution = Wrapper** và **Gradle JVM** phù hợp.
5. Mở **File → Project Structure** để kiểm tra Project SDK/Module SDK và language level được import.
6. **Sync/Reload Gradle Project** khi `settings.gradle.kts`, `build.gradle.kts` hoặc version catalog thay đổi.
7. Chạy `:test` và `:run` trực tiếp từ Gradle tool window làm baseline trước khi chuyển sang gutter tests.

**IntelliJ “Sync Gradle Project” không phải `./gradlew build`**. Sync import lại project structure/dependencies/source sets/task models; nó có thể đánh giá scripts và resolve dependencies, nhưng không hứa compile/test tất cả source. Muốn full verification, gọi Gradle `build`/`test` task.

### Không sửa IDE model thay cho Gradle scripts

Một lỗi phổ biến: thêm một library thủ công vào **Project Structure → Libraries** để editor hết đỏ, nhưng `./gradlew test` và CI vẫn fail vì dependency không nằm trong `dependencies { }`. Hoặc sửa IDE source root nhưng không khai báo `sourceSets`/generated sources, khiến CI không compile được.

**Source of truth** cho source sets, dependencies, test settings, compiler flags và toolchains phải là Gradle build logic version-controlled. IDE import/sync để phản ánh, không thay thế nó.

## 9. Hai lựa chọn khác nhau: Build và Test trong IntelliJ

Trong **Settings/Preferences → Build, Execution, Deployment → Build Tools → Gradle**, IntelliJ có hai lựa chọn độc lập cho linked project:

1. **Build and run using:** `Gradle` hoặc `IntelliJ IDEA`.
2. **Run tests using:** `Gradle`, `IntelliJ IDEA` hoặc `Choose per test` (tùy phiên bản).

Chúng không phải một công tắc duy nhất. Đổi builder sang IDEA **không tự động bắt buộc** đổi test runner sang IDEA; JetBrains tài liệu hóa rằng `Run tests using` vẫn có thể lựa chọn riêng.

| Build and run using | Run tests using | Điểm mạnh | Rủi ro/điều cần kiểm tra |
| --- | --- | --- | --- |
| **Gradle** | **Gradle** | Gần nhất với CI và CLI; giữ Gradle task graph, codegen, test flags, reports | Có thể cần Gradle configuration/daemon overhead |
| **IntelliJ IDEA** | **IntelliJ IDEA** | Có thể phản hồi nhanh khi chạy/debug từng test Java thuần | Bỏ qua một số Gradle build/test task configuration và transforms |
| **Gradle** | **IntelliJ IDEA** | Build theo Gradle nhưng chạy JUnit trực tiếp | Test worker options/system properties/filter của Gradle có thể không được áp dụng |
| **IntelliJ IDEA** | **Gradle** | Editor/build local nhanh nhưng tests theo Gradle | Compiler/build outputs của hai hệ thống có thể khác; nên kiểm tra generated sources |
| **Gradle** | **Choose per test** | Cho phép chọn test runner cho từng test | IDE có thể nhớ runner riêng từng test, khó so kết quả nếu không ghi nhận |

**Khuyến nghị mặc định cho dự án lớn có codegen, annotation processors, test flags, custom test suites hoặc CI quan trọng:** `Build and run using: Gradle` và `Run tests using: Gradle`. Với Java thuần nhỏ, IDEA builder/runner có thể tiện khi debug nhanh, nhưng chạy lại `./gradlew test`/`build` trước commit hoặc khi có divergence.

## 10. “Build Project” không nhất thiết tương đương Gradle `build`

Trong IntelliJ, **Build → Build Project** (thường `Ctrl+F9` trên Windows/Linux) nhằm compile project. Khi chọn delegated Gradle, JetBrains mô tả hành vi thường chỉ yêu cầu các tasks như `classes` và `testClasses`, **không tương đương full Gradle `build`** vốn bao gồm kiểm thử/packaging theo lifecycle plugin.

Ví dụ với demo:

~~~text
Build → Build Project
  -> compile classes / test classes (tùy source sets & settings)

Gradle tool window → Tasks → build → build
  -> check + assemble lifecycle
  -> test task, jar/distribution tasks theo plugin wiring
~~~

Nếu muốn **đảm bảo tests chạy**, gọi `:test` từ Gradle tool window hoặc terminal. Nếu muốn **artifact distribution**, gọi `:distZip`; một lần `Build Project` không hứa ZIP được tạo.

**IDE build success ≠ CI build success** khi hai cơ chế chọn tasks khác nhau. Luôn ghi lại đúng task name bạn đã chạy.

## 11. Khi nào chọn IntelliJ IDEA compiler thay Gradle?

IntelliJ IDEA có incremental compilation, đôi khi nhanh khi chỉ sửa vài Java source files. Điều này tiện cho vòng edit–run–debug ngắn khi Gradle build graph phức tạp. Nhưng JetBrains cũng cảnh báo IDEA compiler không hỗ trợ đầy đủ mọi xử lý của Gradle project.

Đặc biệt dễ khác nhau khi:
- Generated Java sources từ OpenAPI/Protobuf/annotation processing/plugin-specific tasks.
- Custom bytecode weaving, resource filtering hoặc packaging.
- Toolchains/compiler args/`--release`/module path khác IDE defaults.
- Gradle custom source sets hoặc feature variants.
- Kotlin Symbol Processing, mixed language build hoặc plugins cần setup trước compile.
- Test resources được tạo bởi Gradle tasks, Test workers cần system properties/environment/working directory.
- Build uses complex dependency resolution/variant-aware selection.

**Cách kiểm chứng:** chạy cùng một class/test bằng hai runner, so command line JVM, classpath, generated resources, system properties, Gradle test report và actual output. Nếu kết quả khác, đừng cố bắt CI giống IDE một cách thủ công; hãy sửa Gradle model và chọn Gradle delegation khi cần fidelity.

## 12. “Run tests using: Gradle” hoạt động thế nào?

Khi người dùng nhấp **Run/Debug Test** ở gutter/context menu, IDE tạo/ dùng một **Gradle Test run configuration** (hoặc JUnit config nếu đang chọn IDEA runner).

Với Gradle runner:
- Gradle vẫn xử lý test task/source set/classpath.
- `tasks.test { useJUnitPlatform(); systemProperty(...); jvmArgs(...); environment(...); maxParallelForks; filter ... }` được áp dụng theo Task contract.
- Test reports trong `build/reports/tests` và `build/test-results` được Gradle tạo khi task chạy.
- Gradle caching/up-to-date mechanisms có thể hoạt động.
- IDE có thể hiển thị test tree, debug, rerun failed tests và reports.

Tài liệu JetBrains lưu ý **Run as test** trong Gradle run configuration: khi test được trigger từ gutter, nó thường được đặt để **chạy lại test tasks dù chúng otherwise up-to-date** và hiển thị test results trong Run tool window. Trong khi bấm một Gradle task không có Run-as-test option có thể cho thấy `UP-TO-DATE` và không có lần chạy assertion mới.

Đừng kết luận “Gradle runner luôn chậm”: Gradle có daemon, configuration cache, build cache và task-level incremental optimizations. Đo thời gian **cold vs warm** trên project của bạn.

## 13. “Run tests using: IntelliJ IDEA” có gì khác?

Khi IDE dùng JUnit runner riêng:
- IDE trực tiếp khởi động JUnit JVM/classpath từ project model/run configuration của nó.
- Các IntelliJ **VM options**, environment variables, working directory, JRE/test runner options có hiệu lực.
- Gradle `Test` task actions, `systemProperty`, `filter`, `maxParallelForks` và các custom dependencies **không mặc nhiên** được thực thi giống chạy task Gradle.
- Một test class nhỏ có thể chạy rất nhanh và debug trực tiếp, hữu ích khi chỉ xử lý một bug trong code thuần Java.

Trong demo, `GradleTestPolicyTest` đòi `demo.test.mode=gradle-runner`. Với Gradle runner, Gradle `test` đã cấu hình property đó. Với IDEA JUnit runner chưa được cấu hình property tương đương, assertion sẽ thất bại. Bạn có thể thêm VM option trong IDEA test run config:

~~~text
-Ddemo.test.mode=gradle-runner
~~~

nhưng đây chỉ chữa **một thuộc tính**; nếu build có nhiều generated resources/Gradle test suites, cách ít sai hơn thường là dùng Gradle runner.

### Choose per test và IDE nhớ lựa chọn

Tùy phiên bản IntelliJ, `Choose per test` cho chọn Gradle hoặc JUnit runner cho từng test. JetBrains ghi rõ IDE **nhớ runner đã chọn** trong run configuration. Vì vậy bạn đổi global default rồi chạy lại một test vẫn thấy runner cũ là điều có thể xảy ra.

Cách xử lý:
1. Mở **Run/Debug Configurations** của test đó và xem type `Gradle` hay `JUnit`.
2. Chỉnh run configuration hoặc xóa temporary/saved config liên quan để IDE cho chọn lại.
3. Chạy qua **Gradle tool window** với task filter để đối chiếu.
4. Ghi nhận runner đang dùng trước khi kết luận “IDE không áp dụng setting mới”.

## 14. Cách chạy test từ IntelliJ IDEA

### Chạy toàn bộ tests như CLI

Trong **Gradle tool window**:
- Chọn root project đúng.
- Mở `Tasks → verification → test` nếu IDE nhóm tasks theo category.
- Double-click `test` hoặc tạo Gradle Run Configuration với Tasks/Arguments là `test`.

Tương đương CLI:

~~~bash
./gradlew test
~~~

### Chạy một test class

Mở `CalculatorTest.java`, click gutter icon tại class/test method, chọn **Run CalculatorTest**. Khi `Run tests using: Gradle`, IDE chọn Gradle runner và truyền test filter tương ứng.

Tương đương CLI:

~~~bash
./gradlew test --tests "demo.app.CalculatorTest"
~~~

### Chạy một test method

~~~bash
./gradlew test --tests "demo.app.CalculatorTest.addsTwoIntegers"
~~~

Trong IntelliJ, chọn gutter ở method `addsTwoIntegers`. Các parameterized/nested/dynamic tests có thể có naming/filter differences; Gradle 9.9 cải thiện việc match JUnit Platform non-method tests, nhưng không phải mọi third-party engine dùng cùng format.

### Run as test: trạng thái UP-TO-DATE

Nếu một Gradle `test` task được gọi từ Gradle tool window và đã `UP-TO-DATE`, IDE có thể không mở JUnit results mới. Khi cần thực sự chạy lại assertion:
- Dùng gutter test action (Run as test).
- Chỉnh `Run as test` trong Gradle Run Configuration nếu IDE hỗ trợ.
- Hoặc dùng `./gradlew test --rerun-tasks` để buộc Gradle tasks chạy lại (chú ý nó rerun cả dependencies, không chỉ mỗi test).

**Không dùng `clean test` như giải pháp mặc định** cho mọi lần chạy: xóa outputs làm mất tối ưu và có thể che task configuration bug.

## 15. Chạy và debug ứng dụng Java trong IDE

Với demo:

~~~bash
./gradlew run --quiet
~~~

Output chính xác:

~~~text
2 + 3 = 5
~~~

Nếu `Build and run using: Gradle`, IntelliJ run action có thể delegate việc build/run cho Gradle. Nếu chọn IDEA, IDE sẽ dùng own compiler/runtime classpath theo run configuration.

Khi chạy **Main** trực tiếp bằng IDEA, xem:
- **Main class**: `demo.app.Main`.
- **Module/classpath**: đúng source set/module.
- **JRE**: JDK17 hoặc compatible JDK.
- **Program arguments**: command line args cho `String[] args`.
- **VM options**: Java flags như `-Dapp.mode=...`.
- **Environment variables**: variables cho Java process.
- **Working directory**: đường dẫn tương đối mà ứng dụng đọc files.

Đừng nhầm các thuộc tính ở IDE Run Configuration với Gradle `application` plugin configuration. Nếu app cần một `-D` flag cả trong CI/local/IDE, nên thiết kế tập trung trong Gradle tasks hoặc một documented run profile. Gán tùy ý trong IDEA mà không ghi lại khiến `./gradlew run` không tái hiện hành vi.

### Debug Gradle build script khác Debug Java application

Có **hai loại debug**:
1. **Debug application/test JVM**: breakpoint trong `Calculator`/`Main`/JUnit classes.
2. **Debug Gradle build logic**: breakpoint trong Kotlin DSL/plugin/task configuration/action, là một process/lifecycle khác.

JetBrains có Gradle Run/Debug configuration với tùy chọn debug Gradle scripts/forked tasks. Không cho rằng breakpoint trong `build.gradle.kts` sẽ được hit chỉ vì bạn đang Debug JUnit test, hoặc breakpoint Java test sẽ hit khi bạn chỉ debug Gradle Daemon startup.

## 16. IDE Gradle Sync: có thể fail trước khi compile Java

Khi mở project, IDE chạy Gradle import/sync. Nó cần:
- JDK có thể chạy Gradle Daemon.
- Gradle Wrapper distribution có thể tải/đã cache.
- Có thể resolve plugins, repositories, dependencies cần thiết cho model.
- Build scripts/settings files hợp lệ.
- Toolchain detection/provisioning phù hợp project requirements.
- Network/proxy/certificate đúng nếu chưa cache dependencies.

Vì vậy error `Gradle project sync failed` không nhất thiết là Java syntax error. Đọc **lỗi đầu tiên trong Gradle Sync output**, không chỉ popup tổng quát.

### Một lộ trình chuẩn khi sync fail

1. Mở terminal tại **cùng root** và chạy `./gradlew help --stacktrace`.
2. Nếu CLI fail: lỗi thuộc Gradle build/plugin/repos/JDK chung, sửa tại Gradle scripts/environment.
3. Nếu CLI pass nhưng IDE fail: kiểm tra **IDE Gradle JVM**, Distribution Wrapper, offline mode, settings của linked Gradle project, proxy/env của IDE.
4. Trong IDE, **Reload/Sync Gradle Project** và xem full logs.
5. Không xóa `~/.gradle/caches`, `.idea` hoặc gradle wrappers bừa bãi khi chưa biết lỗi; các thao tác đó có thể gây downloads dài và mất cấu hình cục bộ.
6. Với untrusted repository, xem mã Gradle scripts/plugins trước khi cho IDE sync vì Gradle import **thực thi build logic**.

### Offline mode

IDE Gradle tool window có chế độ **Toggle Offline Mode**. Nếu bật mà dependency/plugin/toolchain cần tải chưa tồn tại trong cache, project sync/test có thể fail dù Internet hoạt động. Tắt offline và re-import nếu phù hợp, hoặc bảo đảm toàn bộ dependencies đã có trong cache khi workflow bắt buộc offline.

## 17. Cách kiểm chứng JDK nào thực sự dùng

Không dựa vào một dòng `java -version` trong IDE terminal. Dùng các điểm quan sát:

| Điều muốn biết | Kiểm tra |
| --- | --- |
| JDK của terminal `java` | `java -version`, `echo $JAVA_HOME` hoặc `$env:JAVA_HOME` |
| Gradle distribution | `./gradlew --version`, Wrapper properties |
| Gradle Daemon JDK | `./gradlew --version` và `showGradleRuntime` |
| Gradle discovered toolchains | `./gradlew javaToolchains` |
| Compiler target | `java.toolchain`, `options.release`, compile task args/bytecode |
| Gradle Test worker JVM | `tasks.test.javaLauncher`/toolchain, test worker output nếu cần |
| IntelliJ JUnit JVM | Test Run Configuration → JRE/VM options |
| IntelliJ application JVM | Application Run Configuration → JRE |

### Java test JVM diagnostic (mảnh tùy chọn)

Bạn có thể thêm một JUnit test riêng để in version khi chạy:

~~~java
@Test
void printsTestRuntime() {
    System.out.println(
        "Test JVM Java feature: " + Runtime.version().feature()
    );
}
~~~

Đây là **mảnh method**, cần import `org.junit.jupiter.api.Test` và đặt trong test class. Output version là **giá trị máy đang chạy**, không thể ấn định trước. Khi chạy bằng Gradle, Gradle thường capture stdout vào report (và muốn hiển thị console cần cấu hình `testLogging.showStandardStreams`).

Mảnh Gradle Kotlin DSL bổ sung:

~~~kotlin
tasks.test {
    testLogging {
        showStandardStreams = true
    }
}
~~~

Đây là **mảnh cấu hình ghép vào tasks.test block hiện có**, không thay thế `useJUnitPlatform()` và `systemProperty(...)`.

## 18. Test runtime phải được khai báo rõ trong Gradle

Một dự án khác có thể muốn compile trên JDK17 nhưng **chạy tests trên JDK21** để kiểm thử tương thích. Không nên làm bằng cách đổi IDE Gradle JVM tùy hứng.

Mảnh cấu hình Gradle Kotlin DSL cho test JavaLauncher riêng:

~~~kotlin
tasks.test {
    javaLauncher.set(
        javaToolchains.launcherFor {
            languageVersion.set(JavaLanguageVersion.of(21))
        }
    )
}
~~~

Đây là **mảnh biến thể**, không thuộc demo runnable mặc định, vì nó cần JDK21 available/provisioning. Giữ phần `useJUnitPlatform()` và test dependencies hiện có.

Theo cơ chế Gradle Java toolchains:
- `java.toolchain=17` cho Java compile tasks theo project.
- `tasks.test.javaLauncher=21` có thể dùng JDK21 fork test worker cho task này.
- `--release 17` (nếu thêm) dùng JDK toolchain compile nhưng giới hạn Java APIs/bytecode target cho compatibility.
- IDEA JUnit runner trực tiếp có JRE riêng; nó không tự bắt buộc dùng Test.javaLauncher như Gradle runner.

**Không suy rằng “IDE Gradle JVM là 21” đồng nghĩa tests chạy bằng 21**. Chỉ rõ JavaLauncher hoặc toolchain và kiểm chứng tại test worker.

## 19. JUnit 5 và test discovery trong IDE

Nếu test source tồn tại nhưng Gradle `test` báo zero tests:
1. `src/test/java` đã đúng source set?
2. Có `testImplementation("org.junit.jupiter:junit-jupiter")`?
3. Có `testRuntimeOnly("org.junit.platform:junit-platform-launcher")` phù hợp Gradle version?
4. Có `tasks.test { useJUnitPlatform() }`?
5. Test class/method có `@Test` import từ Jupiter?
6. `--tests` filter có đúng fully qualified class/method?
7. IDE có import Gradle model sau khi build script thay đổi?
8. IDE runner đang chạy Gradle hay JUnit trực tiếp?
9. Có plugin custom test suite tạo task `integrationTest` riêng không?

### Đừng giả định mọi test đều thuộc `:test`

Java `test` task là default test suite. Nếu dự án tạo custom test suites, chẳng hạn `integrationTest` qua JVM Test Suite plugin, chúng có thể có **task khác** và source sets khác. Chọn IDE run configuration đúng suite, hoặc gọi:

~~~bash
./gradlew integrationTest
~~~

**Lệnh trên là minh họa**, chỉ chạy khi build đã đăng ký task `integrationTest`. Không tự sinh task chỉ từ tên trong README.

### Parameterized/nested tests và filter

Với JUnit Jupiter, nested/parameterized tests có display names không trùng hoàn toàn tên Java method. Trong Gradle, dùng `--tests` phù hợp tên class/method mà test engine cung cấp. Nếu filter không tìm thấy tests, Gradle có thể fail với “No tests found for given includes”; không nên tắt validation chỉ để “pass xanh”.

## 20. IDE test runner và CI: chọn chuẩn phù hợp

**Khi cần tương đương CI**, ưu tiên **Gradle runner**:
- Test worker uses `Test` task JVM/classpath.
- Gradle passes test system properties/environment/JVM arguments.
- Dependencies/preprocessing tasks có thể chạy qua Gradle task graph.
- Reports và cache behavior giống Gradle CLI theo các inputs tương ứng.

**Khi debug một Java unit test nhỏ**, IDEA runner có thể nhanh và tiện:
- Fast feedback, test UI/breakpoints.
- Không cần chạy toàn bộ Gradle task graph trong một số trường hợp.
- Có thể tương tác với IDEA coverage/testing tools.

Nhưng không dùng `IntelliJ IDEA runner PASS` làm bằng chứng thay `./gradlew test PASS` trong pipeline. Khi hai runner khác nhau, task model do Gradle khai báo mới là chuẩn để kiểm tra release.

### Bảng quyết định nhanh

| Tình huống | Runner nên dùng |
| --- | --- |
| Codegen/annotation processor trước compile | Gradle build/test |
| Test cần `systemProperty`/`environment` trong Test task | Gradle |
| Custom test suite và Gradle test filters | Gradle |
| Test Java thuần, debugging method nhanh | IntelliJ IDEA có thể phù hợp |
| Có lỗi “works in IDE, fails on CI” | Chạy lại bằng Gradle CLI/IDE Gradle |
| Kiểm tra task output/cache correctness | Gradle |
| Kiểm tra IDE JUnit UI/coverage features | IntelliJ IDEA |
| Muốn test toàn bộ project trước merge | `./gradlew build`/CI equivalent |

## 21. Configuration Cache, Build Cache và IDE sync không phải một thứ

| Cơ chế | Điều được tối ưu | Hành vi liên quan IDE |
| --- | --- | --- |
| IDE indexing/caches | Symbols/navigation/editor models | Không chứng minh Gradle tasks up-to-date |
| IDE Gradle sync | Nhập model từ Gradle | Có thể resolve dependencies mà không build/test |
| Gradle Configuration Cache | Cấu hình/task graph state | IDE Gradle task invocations có thể dùng khi tương thích |
| Gradle Build Cache | Cacheable task outputs | Có thể phục hồi compile/test outputs |
| Gradle up-to-date checks | Skip task nếu inputs/outputs không đổi | Bấm Gradle task có thể báo `UP-TO-DATE` |
| IntelliJ compiler incremental state | Compile IDE modules | Không đồng nghĩa Gradle Build Cache |

Nếu vừa đổi source/build script, Gradle CI pass nhưng IDE red code:
- Reload Gradle model.
- Đảm bảo IDE chọn đúng linked project/source set.
- Kiểm tra Gradle JVM/toolchain model.
- Đợi IDE indexing hoàn tất.
- Chỉ **sau khi có bằng chứng cache IDE corrupted** mới cân nhắc invalidate IDE caches.

Không xóa Gradle dependency caches chỉ vì một type đang được IDE highlight đỏ; điều đó thường không đúng lớp lỗi.

## 22. Dùng IntelliJ Gradle Run Configuration để tái lập CLI

Thay vì dựa hoàn toàn vào gutter, tạo **Gradle Run/Debug Configuration** với:
- **Gradle project**: root/link đúng.
- **Tasks/arguments**: `test --tests "demo.app.CalculatorTest"` hoặc `run`.
- **Environment variables**: nếu build/test task thật sự cần.
- **Gradle VM options / Gradle arguments**: theo yêu cầu version IDE.
- **Run as test** khi muốn test tasks được execute lại và hiển thị results.

Lưu ý **Gradle JVM trong project settings** khác **VM options của Test worker**. Một flag `-Ddemo.test.mode=gradle-runner` truyền vào **Gradle Daemon** chưa chắc được forward tới test fork. Trong demo, đúng nơi là `tasks.test { systemProperty(...) }`.

Khi cần ghi đè test worker property từ command line, thiết kế build script để đọc Gradle project property bằng Provider và forward vào `systemProperty`, thay vì giả định `-D` của client/daemon sẽ tự xuất hiện trong forked JVM.

### Ví dụ biến thể cho Test task

~~~kotlin
tasks.test {
    val mode = providers.gradleProperty("testMode")
        .orElse("gradle-runner")
    systemProperty("demo.test.mode", mode.get())
}
~~~

Đây là **mảnh thay thế** dòng `systemProperty` cố định trong demo, không paste thêm song song. Khi đó:

~~~bash
./gradlew test -PtestMode=gradle-runner
~~~

giữ behavior. Nếu muốn task inputs/cache correctness khi Gradle project property đổi, Gradle `Test` task input properties được cấu hình từ `systemProperty`; thử thay value và kiểm chứng task reruns/outputs. Với các thiết kế phức tạp, hãy nối managed Provider/Task inputs rõ và tránh eager reads không cần thiết.

## 23. Eclipse Buildship và VS Code: nguyên tắc vẫn như nhau

### Eclipse + Buildship

Theo Gradle Toolchains docs, ở Eclipse:

**Preferences → Gradle → Gradle JDK**.

Chọn JDK tương thích Gradle Wrapper/Daemon, đồng thời để Gradle Java toolchain khai báo phiên bản compiler/test JVM. Eclipse workspace JRE/installed JREs và Gradle JDK là **các lựa chọn khác nhau**. Sync/refresh Gradle project để Buildship cập nhật classpath/source sets.

Chạy JUnit bằng Eclipse UI có thể dùng Eclipse test runner riêng, không hoàn toàn cùng semantics với `Gradle Test` task. Để đối chiếu lỗi CI, gọi Gradle task qua Gradle Tasks view/Wrapper CLI với project root đúng.

### VS Code + Gradle for Java

Extension **Gradle for Java** cung cấp Gradle Projects view, xem tasks/dependencies và chạy Gradle tasks trong VS Code. Java Test Runner/Java extension có thể chạy JUnit bằng runner của Java extension thay vì Gradle `test` task. Vì vậy:
- Khi muốn tái lập CI, chạy `./gradlew test` trong terminal hoặc chọn `test` từ Gradle Tasks view.
- Khi dùng Java Test Runner để debug nhanh, kiểm tra classpath/JRE/VM options của runner nếu kết quả khác Gradle.
- Đừng mặc định Java extension "Test Explorer PASS" đồng nghĩa Gradle `test` task đã chạy với đúng `Test` options.

IDE menus/extensions thay đổi theo phiên bản; nguyên tắc **Gradle runtime, Java toolchain, test runner và project source of truth** không đổi.

## 24. Chẩn đoán lỗi thường gặp

| Triệu chứng | Gợi ý nguyên nhân | Kiểm tra/sửa |
| --- | --- | --- |
| IntelliJ Gradle import lỗi “Unsupported class file major version” | Daemon JDK và Gradle/plugin version không tương thích | `./gradlew --version`, Gradle Compatibility Matrix, IDE Gradle JVM |
| “Gradle requires Java 17 or later” | Gradle 9.x Daemon JVM quá cũ | Chọn Gradle JVM/Daemon JDK17+ phù hợp, kiểm tra criteria |
| CLI pass, IDE sync fail | Khác Gradle JVM, offline mode, proxy, linked build | Compare IDE settings vs terminal, reload model |
| IDE pass, CLI/CI test fail | IDE JUnit runner không dùng Gradle `Test` options | Chọn Run tests using Gradle, xem `tasks.test` |
| `GradleTestPolicyTest` fail ở IDE | Thiếu `demo.test.mode` của Gradle Test task | Dùng Gradle runner hoặc cấu hình IDEA JUnit VM option |
| `Run tests using Gradle` đổi nhưng test vẫn JUnit | IDE nhớ run config cũ | Inspect/delete/recreate test run configuration |
| `Build Project` xanh nhưng `./gradlew build` đỏ | IDE chỉ compile hoặc chọn builder riêng | Chạy đúng Gradle `build`/`test` tasks |
| JUnit test 0 discovered | `useJUnitPlatform`/engine/launcher/source path sai | Gradle `test --info`, dependency setup |
| `No tests found for given includes` | `--tests` filter sai class/method/suite | Dùng FQCN/đúng test task |
| Java 17 code IDE đỏ dù Gradle compile được | IDE Project SDK/language level/model chưa sync | Project Structure + Reload Gradle |
| “No matching toolchains found” | JDK 17 không có/provisioning chưa setup | `javaToolchains`, JDK install/configuration |
| Two Gradle Daemons với Java khác | Gradle runtime/JVM args khác nhau | `./gradlew --status`, xem daemon criteria |
| Test chạy bằng JDK21 dù Gradle JVM17 | Test.javaLauncher/toolchain chọn JDK21 | Kiểm tra `tasks.test.javaLauncher` |
| `run` cho output khác IDEA Main | Run configuration JRE/args/env/working directory khác | So `./gradlew run` vs IDEA VM options |
| Test Gradle `UP-TO-DATE`, không thấy chạy assertions | Lần trước inputs/outputs không đổi | Gutter Run as test, `--rerun-tasks` khi cần |
| Gradle build classpath thiếu thư viện nhưng IDE editor thấy | Dependency chỉ thêm trong IDE model | Khai báo trong `dependencies`, sync |
| Test pass khi JUnit trực tiếp, Gradle Test fail | Gradle filter/systemProp/fork settings hoặc generated task | Đọc Test task config/reports |
| Gradle sync chậm | Network/caches/plugins/configuration task work | `--info`, wrapper, offline/proxy/cache, build scripts |
| “Could not resolve plugin” khi import | Plugin repository/network/offline | `pluginManagement.repositories`, proxy, reload |
| `Kotlin DSL script compilation error` trong IDE | Wrapper/embedded Kotlin/API version lệch | Dùng Wrapper, sync, bỏ local Gradle override |
| “Permission denied gradlew” trên Linux | Wrapper executable bit thiếu | `chmod +x gradlew` và commit mode |
| IDE build không tạo generated source | IntelliJ compiler bỏ qua Gradle generator task | Delegate build to Gradle; register generator outputs properly |
| Breakpoint trong test không hit | Debug sai process/test runner | Debug test worker/Application, không chỉ Gradle script |
| Gradle console không in println test | Gradle Test capture stdout | `testLogging.showStandardStreams=true` khi cần |
| Chỉ mở thư mục `src` thay root | Không import Gradle model | Open root có `settings.gradle.kts` |
| IntelliJ “offline mode” bật | Dependency/plugin chưa có cache | Tắt offline hoặc provision cache hợp lệ |

## 25. Quy trình xử lý lỗi IDE vs CLI từng bước

**Bước 1 — Chốt baseline:** ở project root chạy:

~~~bash
./gradlew --version
./gradlew javaToolchains
./gradlew clean test --stacktrace
~~~

Nếu CLI fail, sửa Gradle scripts/dependency/JDK trước; không đổ lỗi IDE.

**Bước 2 — Chốt Gradle version:** IDE Distribution phải là Wrapper, không phải một Gradle installation ngẫu nhiên.

**Bước 3 — Chốt JVMs:** so IDE Gradle JVM, terminal JAVA_HOME, Gradle Daemon criteria và project Java toolchain. Đừng sửa 4 thứ cùng lúc; thay một biến rồi kiểm tra.

**Bước 4 — Chốt task:** `Build Project` có thể chỉ compile; `:build`/`:test` từ Gradle tool window là phép so công bằng với CLI.

**Bước 5 — Chốt runner:** nhìn Run Configuration type Gradle hay JUnit. Chọn Gradle runner khi test cần Gradle task configuration.

**Bước 6 — Chốt environment:** debug app/tests với JRE, `-D` flags, program args, env variables, working directory và test framework options.

**Bước 7 — Chốt outputs/reports:** xem `build/reports/tests/test/index.html`, `build/test-results/test`, Java compiler outputs; IDEA JUnit report không thay Gradle report.

**Bước 8 — Chốt caches:** nếu chỉ IDE hiển thị stale model, reload Gradle trước; không xóa cache directories hàng loạt. Nếu task `UP-TO-DATE`, đó không nhất thiết là lỗi.

**Bước 9 — Regression:** chạy lại `./gradlew build`/CI equivalent sau khi chỉnh. Nếu chỉ chuyển IDEA runner để “pass”, chưa giải quyết mismatch của Gradle build.

## 26. Bài tập thực hành

### Bài A — So sánh JVM của Gradle và toolchain

1. Từ terminal: `java -version`, `./gradlew --version`, `./gradlew javaToolchains`.
2. Chạy `./gradlew showGradleRuntime --quiet`.
3. Ghi Daemon JVM feature/home và Java17 toolchain availability.
4. Trong IntelliJ, đặt Gradle JVM một JDK khác **vẫn tương thích Wrapper**, reload, chạy diagnostic task.
5. Giải thích vì sao `java.toolchain=17` của buildscript vẫn là contract cho JavaCompile ngay cả khi Daemon JDK thay đổi.

Không đổi phiên bản Java ngẫu nhiên nếu Gradle Wrapper không hỗ trợ; tham chiếu compatibility matrix.

### Bài B — So sánh hai test runners

1. Chọn **Run tests using: Gradle**.
2. Chạy `GradleTestPolicyTest.receivesGradleTestConfiguration` từ gutter.
3. Kiểm tra pass và Gradle test results.
4. Chuyển sang **Run tests using: IntelliJ IDEA**, bảo đảm run configuration được tạo lại nếu IDE nhớ runner cũ.
5. Chạy lại test khi chưa đặt JVM property; giải thích vì sao nó có thể fail do `demo.test.mode` không được Gradle Test task chuyển vào IDE JVM.
6. Thêm `-Ddemo.test.mode=gradle-runner` trong IDEA JUnit run configuration rồi so sánh kết quả.

### Bài C — Build Project không đồng nghĩa build

1. Thực hiện **Build → Build Project**.
2. Kiểm tra tasks IDE/Gradle đã chạy.
3. Chạy `./gradlew build`.
4. So sự hiện diện của test reports, JAR/distribution, và giải thích sự khác biệt về lifecycle.

### Bài D — Chạy một test

~~~bash
./gradlew test --tests "demo.app.CalculatorTest.addsTwoIntegers"
~~~

Giải thích vì sao test `addsNegativeInteger` không được chọn. Sau đó dùng gutter method và xem IDE chọn runner nào.

### Bài E — Test JVM khác Daemon JVM

Với JDK21 được cài:
1. Giữ `java.toolchain=17`.
2. Tùy biến `tasks.test.javaLauncher` thành JDK21 theo ví dụ ở phần 18.
3. Chạy `javaToolchains`/test runtime diagnostic.
4. Giải thích vì sao việc đổi IDE Gradle JVM **không thay thế** dòng cấu hình Test.javaLauncher.

## 27. Câu hỏi tự kiểm tra

**1. Gradle Wrapper pin gì?** Gradle distribution/version; không đồng nghĩa Java compiler version.

**2. IDE Project SDK có luôn là Gradle Daemon JVM không?** Không; còn Gradle JVM setting/Daemon criteria và JVM selection rules.

**3. Java toolchain=17 có bắt Daemon dùng Java17?** Không; nó cấu hình compiler/test/Javadoc toolchains theo Gradle Java plugin.

**4. Gradle 9.x yêu cầu JVM gì để chạy Daemon?** JVM17 trở lên trong dải support của đúng Gradle version.

**5. `java -version` có đủ xác định Gradle Daemon JVM?** Không; dùng `./gradlew --version`/diagnostic task và xem Daemon criteria.

**6. IDE chọn Specified Gradle installation có thể khác Wrapper không?** Có, vì override distribution nguồn từ repository.

**7. Khi thay `build.gradle.kts`, nên làm gì trong IntelliJ?** Reload/Sync Gradle Project để IDE import model mới.

**8. Build → Build Project có tự chạy JUnit tests và distribution không?** Không mặc định; thường phục vụ compilation, cần Gradle `test`/`build` cho full lifecycle.

**9. `Run tests using: IntelliJ IDEA` có áp dụng mọi cấu hình Gradle `tasks.test` không?** Không bảo đảm; JUnit runner là process/test config khác.

**10. Test policy trong demo cần JVM property nào?** `demo.test.mode=gradle-runner`, được Gradle `Test` task truyền vào worker.

**11. Chạy method qua CLI thế nào?** `./gradlew test --tests "demo.app.CalculatorTest.addsTwoIntegers"`.

**12. Vì sao IDE có thể run test lại dù Gradle task up-to-date?** IntelliJ Gradle Run-as-test option có thể ép rerun để hiển thị test results.

**13. `--rerun-tasks` là cách sửa IDE/Gradle mismatch không?** Không; nó ép task execution, không sửa runner/JVM config khác nhau.

**14. Daemon JVM criteria có thể lưu ở đâu?** `gradle/gradle-daemon-jvm.properties`, tạo bằng `updateDaemonJvm`.

**15. Khi criteria được áp dụng, `JAVA_HOME` có còn luôn quyết định Daemon?** Không; criteria có precedence theo Gradle docs.

**16. Chạy tests Gradle có thể sinh reports ở đâu?** `build/reports/tests/test` và `build/test-results/test` theo Test task defaults.

**17. Test runner khác có thể ảnh hưởng coverage/debug không?** Có; runner tích hợp khác nhau và cần so generated reports/options.

**18. Eclipse Buildship chọn Gradle JDK ở đâu?** Preferences → Gradle → Gradle JDK.

**19. VS Code Java Test Runner PASS có chứng minh Gradle `test` PASS?** Không; cần chạy Gradle task thật.

**20. Chuẩn để đối chiếu với CI là gì?** Cùng Wrapper, Gradle tasks, Java toolchain/test launcher và environment inputs.

## 28. Checklist trước khi commit hoặc hỗ trợ người khác

- [ ] Gradle project được import từ root có `settings.gradle.kts`/Wrapper.
- [ ] IDE Distribution ưu tiên Wrapper; `./gradlew --version` nhất quán với IDE.
- [ ] Gradle JVM tương thích Wrapper và plugin versions.
- [ ] Project SDK được đặt phù hợp IDE indexing/source language level.
- [ ] Gradle Client/Daemon JVM không bị nhầm với Java toolchain.
- [ ] `java.toolchain` khai báo compiler/test JDK phù hợp trong Gradle buildscript.
- [ ] Nếu dùng Daemon criteria, file `gradle-daemon-jvm.properties` và provisioning đã được review.
- [ ] Không commit absolute `org.gradle.java.home` machine-specific.
- [ ] Java toolchain JDK có sẵn (`javaToolchains`) hoặc auto-provisioning hợp lệ.
- [ ] Build and run using Gradle khi cần compiler/task graph fidelity.
- [ ] Run tests using Gradle khi cần `Test` task system properties, filters, fork settings.
- [ ] Đã xem Run Configuration type Gradle/JUnit; IDEA có thể nhớ runner theo test.
- [ ] `Build Project` không bị coi là tương đương `./gradlew build`.
- [ ] `testImplementation`, JUnit engine/launcher và `useJUnitPlatform` đầy đủ.
- [ ] Tests có assertions thực; thử ít nhất một test fail có chủ đích.
- [ ] Test reports/Gradle task outcomes được xem đúng nguồn.
- [ ] Debug Java test worker/application khác debug Gradle scripts.
- [ ] IDE Gradle sync đã cập nhật model sau thay đổi build scripts.
- [ ] IDE offline mode/proxy được kiểm tra nếu dependency resolution fail.
- [ ] Không xóa Gradle caches/IDE caches bừa bãi để che nguyên nhân.
- [ ] Đã chạy `./gradlew test`/`build` trước khi kết luận mã nguồn ổn.
- [ ] CI dùng Wrapper và JDK/toolchain tương ứng, không phụ thuộc IDE local defaults.

## 29. Tài liệu tham khảo chính thức

- [JetBrains — Gradle Settings](https://www.jetbrains.com/help/idea/gradle-settings.html): Gradle JVM, Distribution, Build and run using, Run tests using.
- [JetBrains — Gradle Projects](https://www.jetbrains.com/help/idea/work-with-gradle-projects.html): import/sync project, delegate build to IDEA, build vs project model.
- [JetBrains — Testing in Gradle](https://www.jetbrains.com/help/idea/work-with-tests-in-gradle.html): Gradle vs IDEA test runner, Choose per test, gutter tests, reports.
- [JetBrains — Gradle Run/Debug Configuration](https://www.jetbrains.com/help/idea/run-debug-gradle.html): Run as test, task/debug options.
- [JetBrains — Build Actions Overview](https://www.jetbrains.com/help/idea/build-overview.html): Build Project vs Gradle `build` lifecycle.
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html): Java compiler/test launcher, IDE Gradle JVM setup, toolchain detection.
- [Gradle — Gradle Daemon](https://docs.gradle.org/current/userguide/gradle_daemon.html): client vs daemon, Daemon JVM criteria, `updateDaemonJvm` and precedence.
- [Gradle — Build Environment](https://docs.gradle.org/current/userguide/build_environment.html): `org.gradle.java.home`, Gradle Java environment and properties.
- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): supported JVM/Gradle combinations.
- [Gradle — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): JUnit Platform, test filtering, reports.
- [Gradle — Command Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): `--tests`/`--rerun-tasks`, debugging task execution.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): distribution pinning and wrapper validation.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): configuration reuse, Gradle task execution vs cache.
- [Eclipse Buildship — Gradle Integration for Eclipse](https://github.com/eclipse-buildship/buildship): Gradle project import and task support.
- [VS Code — Gradle for Java](https://github.com/microsoft/vscode-gradle): Gradle tasks, dependency views and IDE integration.

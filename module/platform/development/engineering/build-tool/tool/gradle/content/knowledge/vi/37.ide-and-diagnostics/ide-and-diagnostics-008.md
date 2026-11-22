# Debug build logic và plugin bằng IDE trong Gradle

**Chủ đề cha:** IDE và chẩn đoán.  
**Phạm vi:** Gradle build scripts, plugin application, task configuration, custom task execution, Gradle Daemon, IntelliJ IDEA và các IDE có khả năng attach debugger JVM.

## 1. Vấn đề: vì sao breakpoint trong Java application không chặn được build script?

Khi chạy Java application, ta thường đặt breakpoint trong `Main.main()` rồi nhấn **Debug**. Nhưng Gradle không chỉ biên dịch Java: nó còn đánh giá `settings.gradle.kts`, `build.gradle.kts`, áp plugins, tạo extension, đăng ký task, resolve providers và thực thi các custom task actions.

Một số lỗi chỉ xuất hiện ở **build logic**:

- `./gradlew help` đã fail, dù không compile một dòng Java application nào.
- Một plugin trong `build-logic` tạo task với input không đúng rồi test task có kết quả sai.
- `Plugin.apply(Project)` gọi `Property.get()` quá sớm, khiến module chưa có cơ hội override default.
- `tasks.register(...)` được viết đúng nhưng plugin khác gọi `TaskProvider.get()`, khiến cấu hình eager.
- Task action ghi file sai đường dẫn, trong khi file được Gradle đánh dấu `@OutputFile`.
- `Provider.map` chỉ được evaluate khi giá trị bị yêu cầu nên breakpoint không hit ở thời điểm tưởng tượng.
- Lần đầu breakpoint `@TaskAction` hit, lần sau không hit vì task `UP-TO-DATE` hoặc `FROM-CACHE`.
- IDE dùng Gradle JVM khác terminal, nên code chạy với classpath/Gradle version/JDK khác nhau.
- TestKit tạo một nested Gradle build ở JVM khác với JUnit test process, nên bấm **Debug Test** không bắt breakpoint của plugin.
- `--debug` in rất nhiều log nhưng vẫn không mở JDWP debugger.

**Phương pháp đúng:** trước tiên xác định code chạy ở **process và pha nào**; sau đó dùng **Gradle Daemon debugger** hoặc debugger của **forked Test/Application JVM** cho đúng loại code. Với Gradle build logic, cách CLI dễ tái lập là `-Dorg.gradle.debug=true`, rồi IDE attach `localhost:5005`.

Bài này cung cấp một ví dụ hoàn chỉnh với Java 17, Gradle Kotlin DSL, một included build `build-logic`, plugin Java, extension, custom task và JUnit test. Bài cũng trình bày IntelliJ IDEA, Eclipse, VS Code, TestKit, Workers, an toàn JDWP và chẩn đoán lỗi.

## 2. Xác định đúng JVM trước khi đặt breakpoint

Một Gradle invocation có thể có nhiều JVM:

```text
Terminal / IDE
    |
    +-- Gradle Client JVM
           |
           v
       Gradle Daemon JVM
           |
           +-- settings.gradle.kts
           +-- build.gradle.kts
           +-- Plugin<Project>.apply()
           +-- Task configuration actions
           +-- @TaskAction không fork
           |
           +-- Java compiler/toolchain
           +-- Forked JUnit Test JVM
           +-- JavaExec/application JVM
           +-- Isolated worker JVM (nếu dùng processIsolation)
```

| Code muốn dừng | JVM cần debug | Cơ chế |
| --- | --- | --- |
| `settings.gradle.kts`, `build.gradle.kts` | Gradle Daemon | Gradle script debugger hoặc `org.gradle.debug` |
| `Plugin.apply(Project)` | Gradle Daemon | Remote JVM attach |
| Lambda cấu hình task | Gradle Daemon | Remote JVM attach; task phải được realized |
| `@TaskAction` chạy trong Gradle | Gradle Daemon | Remote JVM attach; task phải execute |
| JUnit `@Test` của ứng dụng | Forked Test JVM | `test --debug-jvm` hoặc IDE Debug Test |
| `Main.main()` qua `JavaExec` | Forked app JVM | JavaExec debug options / IDE app debugger |
| Build logic bên trong TestKit functional test | JVM của nested build | TestKit `withDebug(true)` hoặc debug nested JVM |
| Process-isolated Gradle Worker | JVM worker riêng | Cấu hình JDWP cho worker process |
| Java compiler/annotation processor | JVM compiler liên quan | Phụ thuộc compiler fork/toolchain, không mặc định là Daemon |

**Ba thuật ngữ khác nhau:** Client JVM khởi động Gradle CLI; Daemon JVM chạy phần lớn build logic; Java toolchain chỉ định compiler/test launcher theo Gradle task. Chúng **không bắt buộc** giống nhau.

Kiểm thông tin:

```bash
./gradlew --version
./gradlew --status
./gradlew -q javaToolchains
```

`gradlew --version` cho biết distribution và JVM information tương ứng Gradle version; `javaToolchains` liệt kê các toolchains được phát hiện. IDE có thể dùng Gradle JVM từ IDE settings, `org.gradle.java.home` hoặc Gradle Daemon JVM criteria khác với terminal `JAVA_HOME`.

**`--no-daemon` không bảo đảm không có JVM Daemon.** Gradle có thể tạo single-use Daemon nếu required JVM arguments khác client; không nên dựa vào flag này để quyết định attach process nào.

## 3. Ba pha Gradle giải thích khi nào breakpoint có cơ hội hit

```text
Initialization:
  settings.gradle.kts, pluginManagement, includeBuild
             |
             v
Configuration:
  plugins { ... } -> Plugin.apply(Project)
  extensions.create(...)
  tasks.register(...) -> TaskProvider (chưa nhất thiết realized)
  task configuration lambda (khi realized)
             |
             v
Execution:
  selected task graph
  skip / up-to-date / cache checks
  @TaskAction nếu thật sự thực thi
             |
             v
  generated file, report, compiled class
```

Một breakpoint ở `Plugin.apply()` sẽ xuất hiện khi Gradle configure project có áp plugin. Một breakpoint ở `tasks.register("x", type, task -> { ... })` **không bắt buộc** xuất hiện khi chỉ chạy `help`, vì Gradle có thể defer task realization. Một breakpoint ở `@TaskAction` chỉ hit khi task được yêu cầu và không bị `UP-TO-DATE`, `FROM-CACHE`, `SKIPPED` hoặc chưa chạy do failure trước action.

| Command | Plugin apply | Task config | Task action |
| --- | --- | --- | --- |
| `:app:help --no-configuration-cache` | Có nếu `:app` được configure | Không nhất thiết | Không |
| `:app:tasks --all` | Thường có | Có thể realize thêm tasks để hiển thị | Không |
| `:app:diagnosticReport` | Có khi configuration chạy | Có | Có nếu task cần execute |
| `:app:check` | Có | Có qua dependency | Có nếu task được gọi và cần chạy |
| `:app:classes` | Có | Không nhất thiết task report | Không |
| `:app:test` | Có | Test task, không phải luôn report task | Chỉ Test JVM; không tự chạy report |

**Thử `./gradlew help --stacktrace` trước.** Nếu `help` đã fail, ưu tiên settings/configuration/plugin. Nếu `help` pass nhưng một custom task fail, ưu tiên task configuration/action.

## 4. Project mẫu độc lập: included build chứa binary plugin

Cây thư mục:

```text
gradle-debug-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── build-logic/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/main/java/org/example/build/
│       ├── DebugInfoExtension.java
│       ├── DiagnosticReportTask.java
│       └── DiagnosticPlugin.java
└── app/
    ├── build.gradle.kts
    ├── src/main/java/example/app/Main.java
    └── src/test/java/example/app/MainTest.java
```

Yêu cầu: **JDK 17**, Gradle Wrapper chính thức tương thích Java 17, Internet/Maven mirror để resolve JUnit test dependency. Plugin code dùng `java-gradle-plugin` của Gradle core. Nếu project mới chưa có Wrapper, dùng một Gradle installation thật để chạy `gradle wrapper` một lần rồi commit các file Wrapper; không tự tạo `gradle-wrapper.jar` giả.

### 4.1. Root `settings.gradle.kts`

```kotlin
pluginManagement {
    includeBuild("build-logic")
}

rootProject.name = "gradle-debug-lab"
include(":app")
```

**Giải thích:** `pluginManagement.includeBuild` cho phép module dùng plugin ID từ included build. `build-logic` không phải là subproject `:build-logic` trong main build.

### 4.2. Root `build.gradle.kts`

```kotlin
plugins {
    base
}
```

Root chỉ áp core `base` plugin; không có diagnostic task ở root. Lúc debug, dùng full task path `:app:diagnosticReport` để tránh gọi nhầm task trong project khác.

### 4.3. `build-logic/settings.gradle.kts`

```kotlin
rootProject.name = "gradle-debug-build-logic"
```

Included build có settings độc lập. IntelliJ/Eclipse cần import/sync đúng included build để source lookup của plugin classes khớp bytecode được Gradle nạp.

### 4.4. `build-logic/build.gradle.kts`

```kotlin
plugins {
    `java-gradle-plugin`
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

gradlePlugin {
    plugins {
        create("diagnostic") {
            id = "org.example.diagnostic"
            implementationClass = "org.example.build.DiagnosticPlugin"
            displayName = "Debuggable Gradle build logic"
            description = "Small plugin with a diagnostic report task"
        }
    }
}
```

`java-gradle-plugin` cung cấp Gradle APIs và tạo plugin descriptors. Tên `implementationClass` phải khớp Java package/source. Toolchain 17 dùng compile code plugin; Gradle Daemon có thể chạy trên một JDK khác miễn compatibility hợp lệ.

### 4.5. `DebugInfoExtension.java`

File `build-logic/src/main/java/org/example/build/DebugInfoExtension.java`:

```java
package org.example.build;

import org.gradle.api.provider.Property;

public abstract class DebugInfoExtension {
    public abstract Property<String> getLabel();
}
```

Gradle có thể sinh implementation cho abstract managed property khi gọi `extensions.create`. Đây là typed DSL contract của plugin; module dùng `debugInfo { label.set("...") }`.

### 4.6. `DiagnosticReportTask.java` — breakpoint trong execution

File `build-logic/src/main/java/org/example/build/DiagnosticReportTask.java`:

```java
package org.example.build;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.gradle.api.DefaultTask;
import org.gradle.api.GradleException;
import org.gradle.api.file.RegularFileProperty;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.CacheableTask;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.OutputFile;
import org.gradle.api.tasks.TaskAction;

@CacheableTask
public abstract class DiagnosticReportTask extends DefaultTask {

    @Input
    public abstract Property<String> getLabel();

    @OutputFile
    public abstract RegularFileProperty getReportFile();

    @TaskAction
    public void writeReport() throws IOException {
        // BREAKPOINT A: bắt đầu task action.
        String label = getLabel().get().trim();

        if (label.isEmpty()) {
            throw new GradleException(
                "debugInfo.label must not be blank"
            );
        }

        Path report = getReportFile()
            .get().getAsFile().toPath();

        Files.createDirectories(report.getParent());
        Files.writeString(
            report,
            "label=" + label + "\n",
            StandardCharsets.UTF_8
        );

        getLogger().lifecycle(
            "DIAGNOSTIC_REPORT_EXECUTED label={}", label
        );
    }
}
```

Các thuộc tính có ý nghĩa:

- `@Input`: Gradle fingerprint `label` và biết thay đổi label có thể làm output khác.
- `@OutputFile`: Gradle biết file nào được tạo, có thể phát hiện missing/modified output.
- `@CacheableTask`: output có thể được build cache lưu/phục hồi nếu inputs/implementation hợp lệ.
- `@TaskAction`: code chạy khi task execution thật sự xảy ra.
- `getLabel().get()` đặt trong action, nơi concrete value đã có ý nghĩa.
- `Files.writeString` dùng UTF-8 và chỉ ghi file output đã khai báo.
- Nếu label chỉ có whitespace, task fail với thông báo chính xác trong code; đó là negative test dễ debug.

**Cẩn thận:** nếu task `UP-TO-DATE` hoặc `FROM-CACHE`, `writeReport()` không chạy và breakpoint A không hit. Dùng `--rerun-tasks --no-build-cache` khi cần quan sát action.

### 4.7. `DiagnosticPlugin.java` — breakpoints plugin và task configuration

File `build-logic/src/main/java/org/example/build/DiagnosticPlugin.java`:

```java
package org.example.build;

import org.gradle.api.Plugin;
import org.gradle.api.Project;
import org.gradle.api.tasks.TaskProvider;

public final class DiagnosticPlugin implements Plugin<Project> {

    @Override
    public void apply(Project project) {
        // BREAKPOINT B: plugin được áp vào module.
        project.getPluginManager().apply("java-library");

        DebugInfoExtension ext =
            project.getExtensions().create(
                "debugInfo", DebugInfoExtension.class
            );

        ext.getLabel().convention(project.getName());

        TaskProvider<DiagnosticReportTask> report =
            project.getTasks().register(
                "diagnosticReport",
                DiagnosticReportTask.class,
                task -> {
                    // BREAKPOINT C: lazy task configuration.
                    task.setGroup("verification");
                    task.setDescription(
                        "Write a diagnostic report for a module"
                    );

                    task.getLabel().set(ext.getLabel());
                    task.getReportFile().set(
                        project.getLayout().getBuildDirectory()
                            .file("reports/diagnostics/report.txt")
                    );

                    task.getLogger().lifecycle(
                        "CONFIGURE diagnosticReport"
                    );
                }
            );

        project.getTasks().named("check").configure(
            task -> task.dependsOn(report)
        );

        project.getLogger().lifecycle(
            "APPLY diagnostic plugin to {}", project.getPath()
        );
    }
}
```

**Ba vị trí cụ thể:**

- **Breakpoint B** dừng khi plugin được apply. Inspect `project.getPath()`, extension container và plugin application.
- **Breakpoint C** dừng khi task instance được realized. Inspect TaskProvider wiring; không bắt buộc hit trong `help`.
- **Breakpoint A** dừng trong `DiagnosticReportTask.writeReport()` khi execution thật sự diễn ra.

Code dùng `tasks.register` và `TaskProvider`, không dùng `tasks.create`/`getByName` để ép task realization sớm. `ext.getLabel().convention(project.getName())` chỉ là default, module có thể override bằng `set()`. `task.getLabel().set(ext.getLabel())` truyền **Provider**, không lấy String quá sớm; đây cũng là điểm quan trọng để debug lỗi lifecycle/order.

### 4.8. `app/build.gradle.kts`

```kotlin
plugins {
    id("org.example.diagnostic")
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    maxParallelForks = 1
}

debugInfo {
    label.set("app-team")
}
```

Module chỉ khai báo `label`. Plugin giữ logic tạo task và nối `check`. JUnit BOM version là phiên bản ví dụ được ghim, không phải tuyên bố latest. `maxParallelForks=1` làm session debug Test JVM đơn giản hơn.

### 4.9. Java application `Main.java`

File `app/src/main/java/example/app/Main.java`:

```java
package example.app;

public final class Main {
    private Main() {
    }

    public static String message() {
        return "PLUGIN_DEMO_APP";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

Đây là Java application độc lập với Gradle plugin. Breakpoint trong `Main.main()` không dừng khi chỉ chạy `./gradlew help`.

### 4.10. JUnit `MainTest.java`

File `app/src/test/java/example/app/MainTest.java`:

```java
package example.app;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

final class MainTest {

    @Test
    void applicationMessageIsStable() {
        assertEquals("PLUGIN_DEMO_APP", Main.message());
    }
}
```

Test có một assertion để forked Test JVM thật sự có code chạy. Nó không tự kiểm Gradle plugin, vì `Main.message()` không phải task action.

## 5. Chạy baseline: xác minh trước khi attach debugger

Từ root `gradle-debug-lab`:

Linux/macOS:

```bash
./gradlew --version
./gradlew :app:diagnosticReport \
  --no-configuration-cache --no-build-cache --rerun-tasks \
  --console=plain
./gradlew :app:check --no-configuration-cache --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat :app:diagnosticReport --no-configuration-cache --no-build-cache --rerun-tasks --console=plain
.\gradlew.bat :app:check --no-configuration-cache --console=plain
```

Trong một invocation có task action chạy, plugin có thể in:

```text
APPLY diagnostic plugin to :app
CONFIGURE diagnosticReport
DIAGNOSTIC_REPORT_EXECUTED label=app-team
```

Đây **chỉ là các dòng log do demo tự tạo**, không phải toàn bộ Gradle output. Dòng `CONFIGURE` có thể xuất hiện dù task action được skip; dòng `DIAGNOSTIC_REPORT_EXECUTED` chỉ được in khi action chạy.

File output `app/build/reports/diagnostics/report.txt` phải chứa chính xác:

```text
label=app-team
```

Chạy Java application sau khi biên dịch:

```bash
./gradlew :app:classes
java -cp app/build/classes/java/main example.app.Main
```

PowerShell:

```powershell
.\gradlew.bat :app:classes
java -cp app\build\classes\java\main example.app.Main
```

Stdout **của Java Main**:

```text
PLUGIN_DEMO_APP
```

Nếu muốn kiểm riêng Java17 source mà chưa chạy Gradle:

```bash
mkdir -p manual-classes
javac --release 17 -d manual-classes \
  app/src/main/java/example/app/Main.java
java -cp manual-classes example.app.Main
```

Lệnh này cũng tạo stdout `PLUGIN_DEMO_APP`. Nó **không chứng minh plugin chạy đúng**, chỉ chứng minh mã Main compile/chạy được trên JDK17.

## 6. Bật remote debugger đúng cách cho Gradle Daemon

Theo Gradle official documentation:

```bash
./gradlew :app:diagnosticReport \
  -Dorg.gradle.debug=true \
  --no-configuration-cache \
  --no-build-cache \
  --rerun-tasks \
  --console=plain
```

PowerShell:

```powershell
.\gradlew.bat :app:diagnosticReport -Dorg.gradle.debug=true --no-configuration-cache --no-build-cache --rerun-tasks --console=plain
```

Khi bật `-Dorg.gradle.debug=true`, Gradle chạy build JVM với JDWP:

- Mặc định debugger lắng nghe **port 5005**.
- Mặc định JVM **suspend** tới khi IDE attach thành công.
- Console có thể hiện thông điệp kiểu `Listening for transport dt_socket at address: 5005`.
- Việc terminal chờ là **đúng hành vi**; mở IDE remote debug configuration tới `localhost:5005`.
- Sau khi attach, resume đến điểm breakpoint B, C hoặc A.

**`--debug` không đồng nghĩa `-Dorg.gradle.debug=true`**. `--debug` chỉ tăng verbosity của logs và có thể phơi bày thông tin nhạy cảm.

### 6.1. Các flags nên hiểu chính xác

| Flag | Vai trò |
| --- | --- |
| `-Dorg.gradle.debug=true` | Mở JDWP debugger cho Gradle Daemon |
| `--no-configuration-cache` | Buộc configuration code chạy lại; giúp breakpoints trong `apply()`/build scripts |
| `--no-build-cache` | Không restore outputs từ build cache |
| `--rerun-tasks` | Buộc task actions được chọn thực thi thay vì dùng up-to-date state |
| `--stacktrace` | In exception stacktrace nếu build fail |
| `--info` | Thêm chẩn đoán task outcomes/phase/resolution |
| `--console=plain` | Dễ đọc console transcript |

`--rerun-tasks` **không đảm bảo configuration code chạy lại** khi configuration cache đang được reuse. `--no-configuration-cache` và `--rerun-tasks` giải quyết **hai tình huống khác nhau**.

### 6.2. Thay cổng 5005 khi xung đột

```bash
./gradlew :app:diagnosticReport \
  -Dorg.gradle.debug=true \
  -Dorg.gradle.debug.port=5006 \
  --no-configuration-cache --rerun-tasks
```

IDE phải attach **5006**. Gradle còn có các properties `org.gradle.debug.host`, `org.gradle.debug.server` và `org.gradle.debug.suspend` theo CLI docs. Nếu dùng:

```bash
./gradlew help \
  -Dorg.gradle.debug=true \
  -Dorg.gradle.debug.suspend=false
```

Daemon không chờ debugger. Nhưng nó có thể thực thi `Plugin.apply()` xong **trước khi bạn kịp attach**, khiến breakpoint B bị lỡ. Khi học, giữ suspend mặc định.

### 6.3. Không expose JDWP ra mạng

Với Java 9+ Gradle debug mặc định nên dùng loopback. Có tùy chọn `-Dorg.gradle.debug.host=*` để lắng nghe trên mọi network interfaces, nhưng **không dùng tùy tiện**: JDWP là giao diện debug có thể cho phép thực thi/inspect trong JVM. Trên máy shared/CI/server, dùng localhost hoặc SSH tunnel có kiểm soát.

Không commit `org.gradle.debug=true` vào shared `gradle.properties`: các build CI/IDE có thể đứng chờ debugger và timeout.

## 7. IntelliJ IDEA: đặt ba breakpoint đúng đối tượng

### 7.1. Chuẩn bị source lookup

1. Mở **root project `gradle-debug-lab`**.
2. Cho IntelliJ import bằng Gradle Wrapper, chờ **Gradle Sync** hoàn tất.
3. Mở `build-logic/src/main/java/org/example/build/DiagnosticPlugin.java` và `DiagnosticReportTask.java`.
4. Kiểm source classes được IDE xem là thuộc included build, không chỉ text files không attached.
5. Đặt:
   - **B:** dòng đầu trong `DiagnosticPlugin.apply`.
   - **C:** lambda `task -> { ... }` trong `tasks.register`.
   - **A:** dòng `String label = getLabel().get().trim();` trong `writeReport()`.
6. Kiểm **Settings → Build, Execution, Deployment → Build Tools → Gradle** để biết Gradle JVM và Wrapper đang dùng.

Nếu breakpoint bị “unverified”, ưu tiên kiểm IDE import/sync, compiled classpath, plugin ID/class mismatch thay vì thay code nghiệp vụ.

### 7.2. Tạo Remote JVM Debug configuration

Trong IntelliJ IDEA:

1. **Run → Edit Configurations**.
2. Tạo loại **Remote JVM Debug** / **Remote** với **Attach to remote JVM**.
3. **Host**: `localhost`.
4. **Port**: `5005`, trừ khi đã đổi `org.gradle.debug.port`.
5. Đặt tên `Gradle Daemon diagnostics` và lưu.
6. Mở terminal chạy `./gradlew :app:diagnosticReport -Dorg.gradle.debug=true --no-configuration-cache --no-build-cache --rerun-tasks`.
7. Khi terminal đang đợi, bấm **Debug** ở remote configuration vừa tạo.
8. Quan sát Debug tool window: frames, variables, breakpoints, stepping.

Đừng nhầm lệnh chạy **Debug Main** với **Attach Remote JVM**. `Main.main()` nằm ở application JVM; code Gradle plugin nằm trong Gradle Daemon.

### 7.3. Quan sát breakpoint B (apply)

Inspect:

- `project.getPath()`: kỳ vọng `:app`.
- `project.getName()`: `app`.
- Plugin Manager và Extensions trước/sau `extensions.create`.
- `ext.getLabel()` sau `convention(project.getName())`.
- Gradle stack trace liên quan plugin application.
- Tại sao `java-library` được apply.

**Không dùng Evaluate Expression để gọi `Configuration.resolve()` hoặc `TaskProvider.get()` vô cớ**. Những methods có thể gây side effects/force task realization và làm state mà bạn định debug bị biến đổi.

### 7.4. Quan sát breakpoint C (task configuration)

Inspect:

- `task.getPath()`: `:app:diagnosticReport`.
- `task.getLabel()` nhận Provider từ extension, không bị convert thành String quá sớm.
- `task.getReportFile()` trỏ tới build directory của module.
- Task configuration action chỉ chạy khi task được realized.
- Nếu `help` cũng làm lambda này chạy, tìm code eager gọi `tasks.all`, `getByName`, `TaskProvider.get()` hoặc một task inspection.

Breakpoints trong task configuration không chứng minh task action đã thực thi.

### 7.5. Quan sát breakpoint A (task action)

Inspect:

- `getLabel().get()` và kết quả `trim()`.
- `getReportFile().get().getAsFile()`.
- Logic ném `GradleException` khi label blank.
- Các bước tạo directory/ghi file UTF-8.
- Dòng lifecycle log in sau khi output được viết.

Nếu breakpoint action không dừng, kiểm task outcome và `--rerun-tasks`. **`UP-TO-DATE` hoặc `FROM-CACHE` không phải lỗi debugger**.

### 7.6. IntelliJ Gradle script debugging tích hợp

IntelliJ IDEA cũng có **Gradle Run/Debug Configurations** và, trong các versions hỗ trợ, tab **Gradle Debug** với tùy chọn **Debug Gradle scripts**. Breakpoints trong `build.gradle.kts` có thể được IDE quản lý trực tiếp.

Một số lối khởi chạy test từ gutter/context menu **tắt script debugging** để nhanh hơn. Nếu breakpoint trong Kotlin DSL không hit, mở Gradle run/debug configuration và kiểm phần Debug Gradle scripts.

**Không giả định** nhấn Debug lên một `Test`/`JavaExec` task trong Gradle tool window sẽ debug `Plugin.apply()`; IDE có thể ưu tiên forked JVM của task. Remote JDWP Daemon giúp phân biệt rõ ràng.

Tài liệu: [IntelliJ IDEA — Work with Gradle tasks](https://www.jetbrains.com/help/idea/work-with-gradle-tasks.html).

## 8. Eclipse, VS Code và IDE khác

### 8.1. Eclipse/Buildship

Với Eclipse có Buildship:

1. Import project dưới dạng Gradle project.
2. Nếu included build sources không xuất hiện, thêm source lookup/project import thích hợp.
3. Đặt breakpoint trong `DiagnosticPlugin.java` hoặc `DiagnosticReportTask.java`.
4. Chạy command Gradle debug từ terminal (ở phần 6).
5. Mở **Run → Debug Configurations → Remote Java Application**.
6. Đặt host `localhost`, port `5005` và project/source lookup phù hợp.
7. Bấm **Debug**, resume đến breakpoints.

Nếu IDE nói `Source not found`, vấn đề có thể là missing source attachment hoặc compiled class/version mismatch, không phải Gradle JDWP không hoạt động.

### 8.2. VS Code Java Debugger

Nếu có Java Debugger extension và project sources được import đúng, một cấu hình `.vscode/launch.json` kiểu attach có thể dùng:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "type": "java",
      "request": "attach",
      "name": "Attach Gradle Daemon",
      "hostName": "localhost",
      "port": 5005
    }
  ]
}
```

Đây là cấu hình **cho extension hỗ trợ Java debugging**, không phải một file Gradle. Chỉ tạo nó không tự động làm source lookup của plugin đúng; cần Java language/project tooling để IDE biết compiled classes.

### 8.3. Quy tắc IDE-agnostic

Mọi IDE dùng cùng logic:

- Chạy Gradle build với debugger JDWP bật.
- Biết JVM/port đang lắng nghe.
- Attach đúng process.
- Source file trùng compiled class/version.
- Breakpoint ở code path thực sự chạy.
- Không tự động debug forked process bằng Daemon debugger.

## 9. Debug một lỗi thực có kiểm soát

Trong `app/build.gradle.kts`, thay tạm:

```kotlin
debugInfo {
    label.set("   ")
}
```

Chạy:

```bash
./gradlew :app:diagnosticReport \
  -Dorg.gradle.debug=true \
  --no-configuration-cache --no-build-cache --rerun-tasks \
  --stacktrace --console=plain
```

Khi debugger hit breakpoint A, step qua:

```java
String label = getLabel().get().trim();

if (label.isEmpty()) {
    throw new GradleException(
        "debugInfo.label must not be blank"
    );
}
```

Giá trị sau `trim()` là chuỗi rỗng. Lỗi nghiệp vụ chính xác:

```text
debugInfo.label must not be blank
```

Console còn có Gradle exception banner/stacktrace, nên block trên chỉ thể hiện **thông điệp từ code demo**, không phải full build output. Task fail trước khi ghi file; nếu `report.txt` cũ còn đó, không coi nó là output mới của lượt fail.

Sau khi quan sát, khôi phục `label.set("app-team")`. Không commit lỗi giả hoặc debug instrumentation vào repo thực.

### 9.1. Sai lầm `Property.get()` quá sớm

Một anti-pattern:

```java
// KHÔNG sửa plugin thành code này:
String now = ext.getLabel().get();
task.getLabel().set(now);
```

Nếu resolve `ext.getLabel().get()` khi plugin mới apply, module chưa chắc đã chạy xong `debugInfo { label.set("app-team") }`. Plugin chỉ thấy convention `app` và bỏ qua override. Cách đúng là:

```java
task.getLabel().set(ext.getLabel());
```

Truyền Provider để Gradle quyết định lúc đọc giá trị. Debugger Evaluate Expression cũng có thể vô tình force `get()`; cần phân biệt **đọc để quan sát** với **mutate/resolve Gradle model**.

## 10. Vì sao breakpoint không hit: bốn loại skip khác nhau

### 10.1. Plugin chưa được apply

Nếu Gradle báo:

```text
Plugin [id: 'org.example.diagnostic'] was not found
```

Gradle chưa gọi `DiagnosticPlugin.apply()`. Breakpoint B không thể hit. Kiểm `settings.gradle.kts` có `pluginManagement.includeBuild("build-logic")`, plugin ID/`implementationClass` đúng, Java sources compile và Gradle resolution/IDE sync phù hợp.

### 10.2. Task chưa được realized

`tasks.register(...)` là lazy; nếu chỉ gọi `:app:help` thì breakpoint C có thể không hit. Hãy gọi đúng `:app:diagnosticReport`, không sửa plugin sang eager APIs để “cho breakpoint hit”.

### 10.3. Task up to date hoặc lấy từ cache

Nếu `diagnosticReport` đã tạo report và input không đổi, Gradle có thể báo `UP-TO-DATE`. Nếu build cache bật và có hit, nó có thể báo `FROM-CACHE`. Cả hai đều không gọi `@TaskAction`. Thử `--no-build-cache --rerun-tasks` để quan sát action trong sandbox; bỏ flags khi quay về run bình thường.

### 10.4. Configuration cache reuse

Nếu build có `--configuration-cache` và cache hit, `Plugin.apply`/build script configuration code có thể không được chạy lại. Khi cần debug configuration, dùng `--no-configuration-cache`.

**Không dùng một flag để giải quyết nhầm tầng:** `--rerun-tasks` không thay `--no-configuration-cache`, và `--no-configuration-cache` không tự buộc task action chạy nếu up to date.

## 11. Debug JUnit tests khác debug Gradle plugin

Demo có `MainTest.java`. Để debug test code:

```bash
./gradlew :app:test \
  --tests example.app.MainTest \
  --debug-jvm \
  --no-configuration-cache --no-build-cache --rerun-tasks
```

`--debug-jvm` của `Test` làm **forked test JVM** mở debugger và suspend, mặc định port5005. Attach IDE vào cổng ấy; đặt breakpoint trong `MainTest.applicationMessageIsStable()` hoặc `Main.message()`. **Đừng kỳ vọng `DiagnosticPlugin.apply` được dừng** bởi test JVM debugger.

Nếu dùng JavaExec task, JavaExec có hỗ trợ debug mode tương tự; debugger attach vào application process, không phải Gradle Daemon.

### 11.1. Vì sao không bật hai debuggers cùng port?

Nếu bật đồng thời:

```text
-Dorg.gradle.debug=true
--debug-jvm
```

Daemon và forked Test JVM có thể cùng muốn dùng JDWP listener cổng5005, dẫn tới port conflict hoặc attach nhầm process. Để debug plugin, dùng Daemon JDWP. Để debug JUnit code, dùng Test JVM debugger. Nếu cần cả hai, định nghĩa **hai port khác nhau**.

### 11.2. Test debug port tùy chỉnh bằng Kotlin DSL

Một tùy chọn bổ sung (không cần cho baseline) trong `app/build.gradle.kts`:

```kotlin
tasks.named<Test>("test") {
    debugOptions {
        enabled.set(true)
        port.set(5007)
        server.set(true)
        suspend.set(true)
    }
}
```

`JavaDebugOptions` dùng Gradle `Property` getters (`enabled`/`port`/`server`/`suspend`), nên Kotlin DSL có `set(...)`. IDE lúc này attach vào port5007 của Test process. **Không giữ debugEnabled mặc định trong CI**: test sẽ đợi IDE và job timeout. Với nhiều test forks có thể có port conflicts; giữ `maxParallelForks=1` trong một session debug đơn giản.

Nguồn: [Gradle — Testing Java and JVM projects](https://docs.gradle.org/current/userguide/java_testing.html).

## 12. Debug Gradle TestKit functional tests

Một Gradle plugin nên có functional tests bằng Gradle TestKit. Khi code test gọi `GradleRunner.build()`, Tooling API thường thực thi **nested build trong một process khác**. Vì vậy Debug JUnit test method **không mặc nhiên** dừng ở code plugin được apply trong nested build.

Gradle hỗ trợ:

- `GradleRunner.withDebug(true)`.
- System property `-Dorg.gradle.testkit.debug=true` trong JVM chạy GradleRunner.

Snippet TestKit (**chưa phải full runnable JUnit test class**; cần fixture/imports/Gradle TestKit test setup):

```java
BuildResult result = GradleRunner.create()
    .withProjectDir(testProjectDir)
    .withPluginClasspath()
    .withArguments(
        "diagnosticReport",
        "--no-build-cache",
        "--rerun-tasks"
    )
    .withDebug(true)
    .build();
```

`testProjectDir` phải chứa **consumer build fixture** apply đúng plugin ID và khai báo `debugInfo`. `withPluginClasspath()` cung cấp plugin-under-test classpath do `java-gradle-plugin` hỗ trợ. Trong IDE, Debug JUnit functional test có debug mode bật để breakpoint trong build logic được truy cập theo mechanism TestKit.

### 12.1. Checklist TestKit debugger không hit

- Có Debug JUnit **functional test**, không chỉ Run Test?
- `withDebug(true)` bật trên đúng GradleRunner instance?
- Consumer fixture apply đúng plugin ID?
- Source/compiled plugin classpath có đúng phiên bản?
- Nested build có tạo task/report hay bị `UP-TO-DATE`?
- TestKit distribution có tải được từ cache/Internet?
- Gradle version trong `withGradleVersion(...)` có tương thích plugin và JDK?
- Có multi-process/parallel tests làm breakpoint attach nhầm process?
- Có đọc lỗi trong TestKit output thay vì chỉ nhìn JUnit test wrapper?
- IDE Java source lookup có trỏ đúng `build-logic`?

**`withGradleVersion(...)` chọn Gradle distribution của TestKit nested build**, không tự chọn OS/JVM khác. Nếu lỗi chỉ xuất hiện trên Windows, cần CI Windows runner; TestKit một mình trên Linux không thay OS matrix.

Nguồn: [Gradle — Testing Build Logic with TestKit](https://docs.gradle.org/current/userguide/test_kit.html).

## 13. Debug Gradle Kotlin DSL và precompiled script plugins

Các file `*.gradle.kts` là Kotlin scripts được Gradle compile/evaluate. IntelliJ có thể đặt breakpoint trong script khi hỗ trợ Gradle script debugging; không nhất thiết cần một Java plugin class.

Snippet bổ sung trong `app/build.gradle.kts`:

```kotlin
tasks.register("scriptGreeting") {
    // Breakpoint ở configuration action.
    val text = providers.gradleProperty("message")
        .orElse("Hello from Kotlin DSL")

    doLast {
        // Breakpoint ở execution action.
        logger.lifecycle(text.get())
    }
}
```

Chạy:

```bash
./gradlew :app:scriptGreeting \
  -Dorg.gradle.debug=true \
  --no-configuration-cache --rerun-tasks
```

Breakpoint ở `tasks.register` lambda chỉ hit khi task realized; breakpoint `doLast` chỉ hit khi task action thực thi. Đừng chạy `help` rồi đợi breakpoint `doLast` dừng.

### 13.1. `buildSrc`, included build và published plugin

| Nguồn build logic | Code hiện diện ở đâu? | Điều cần kiểm để debug |
| --- | --- | --- |
| `buildSrc` | `buildSrc/src/main/...` | Gradle tự build/classpath, IDE đã import sources |
| Included `build-logic` | Build riêng được `pluginManagement.includeBuild` | Plugin ID/implementation class và composite build import đúng |
| Precompiled `*.gradle.kts` plugin | `src/main/kotlin/*.gradle.kts` | Kotlin script compiled class/source lookup tương ứng |
| Binary Java/Kotlin plugin | `Plugin<Project>`/task classes | Source + bytecode/JAR phiên bản chính xác |
| Published plugin | Maven/Plugin Portal artifact | Source JAR/source attachment khớp release version |

Một breakpoint trong plugin source version N không dừng nếu build thực tế đang dùng plugin compiled release N-1. Kiểm Gradle resolution và IDE import trước khi xóa caches ngẫu nhiên.

### 13.2. `ProjectBuilder` test khác `GradleRunner`

Một unit test dùng `ProjectBuilder` chạy plugin model gần JVM test code hơn; Debug JUnit có thể hit code plugin được gọi trực tiếp. Một functional test dùng `GradleRunner` cần hiểu TestKit nested build mode như phần 12. Không dùng unit test đơn giản làm bằng chứng rằng plugin task action chạy đúng trong một Gradle build thật.

## 14. Khi plugin dùng Worker API, breakpoint có thể ở JVM khác

`WorkerExecutor` có các isolation modes:

- `noIsolation()`: work trong Gradle process, shared context hơn.
- `classLoaderIsolation()`: work trong Gradle process nhưng classloader riêng.
- `processIsolation()`: work trong **worker JVM khác**.
- `Exec` và `JavaExec` cũng có thể tạo external/forked process.

Nếu code cần debug nằm trong **process-isolated WorkAction**, debugger attach Gradle Daemon không tự debug worker JVM. Bạn cần cấu hình worker fork's JVM debug args và attach **worker process** với port riêng, theo Worker API/Gradle version phù hợp. Không thêm `-Dorg.gradle.debug=true` rồi mặc định mọi child process sẽ thừa hưởng JDWP.

### 14.1. Lưu ý với JavaCompile

`compileJava` có thể dùng Java compiler toolchain/incremental compiler. Một annotation processor có thể chạy trong compiler context thay vì Java application JVM; debugger của `Main.main` không giúp tìm lỗi annotation processor ở compile phase. Phải kiểm compiler invocation/toolchain/fork behavior và plugin/compiler options tương ứng.

**Không đồng nhất:** Java toolchain chọn compiler JDK17 ≠ JVM chạy Gradle Daemon17. Những lựa chọn này có thể độc lập.

## 15. Quan sát Provider mà không biến debug thành side effect

Gradle `Provider`/`Property` trì hoãn việc lấy giá trị:

```java
task.getLabel().set(ext.getLabel());
```

Đây là cấu hình đúng; module có thể gọi `debugInfo { label.set("app-team") }` sau khi plugin đã apply. Nếu sửa thành:

```java
// Anti-pattern: đọc quá sớm.
String early = ext.getLabel().get();
task.getLabel().set(early);
```

module có thể chưa override convention, khiến task thấy `app` thay vì `app-team`. Đây là một bug logic, không phải debugger issue.

Trong Evaluate Expression của IDE, tránh:

- `TaskProvider.get()` nếu chưa cần realize task.
- `Configuration.resolve()` nếu không muốn dependency resolution.
- `Files.writeString(...)`, external process hoặc network call.
- `Project.afterEvaluate(...)` mutation.
- `Provider.map(...)` có side effects (bản thân pattern này cũng không nên dùng).

Ưu tiên inspect variables ở đúng call site, dùng Gradle `--info` logs và breakpoint tại `@TaskAction` nơi `Property.get()` có ý nghĩa. Nếu thêm logger để chẩn đoán, không in token/secret giá trị, và loại instrumentation sau khi fix.

## 16. Troubleshooting một breakpoint không hoạt động

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Terminal chờ mãi sau `org.gradle.debug=true` | Daemon đang suspend | Attach IDE đến đúng host/port |
| IDE báo `Connection refused` | JDWP chưa listen hoặc wrong port | Kiểm terminal/port, khởi động lại remote attach |
| Port5005 bị chiếm | JVM/debugger khác lắng nghe | `org.gradle.debug.port=5006` + đổi IDE |
| Breakpoint trong `apply` không hit | Plugin chưa apply hoặc config cache reused | Check plugin ID, `--no-configuration-cache` |
| Breakpoint task config không hit | Task chưa realized | Request đúng task path |
| Breakpoint task action không hit | Task up to date/cache/skipped | `--no-build-cache --rerun-tasks` |
| Breakpoint Java Main không hit | Attach Daemon nhưng Main chạy forked app JVM | Debug app process |
| Breakpoint JUnit không hit | Attach Daemon thay vì Test JVM | Dùng `--debug-jvm` |
| Breakpoint plugin TestKit không hit | Nested build khác JVM | `GradleRunner.withDebug(true)` |
| Source lookup không thấy class | IDE chưa import included build | Reload Gradle, kiểm source attachments |
| Breakpoint unverified | Source khác compiled bytecode | Kiểm class/JAR/build-logic version |
| Lỗi ở plugin resolution | Plugin chưa được load/apply | Kiểm settings pluginManagement, descriptors |
| `@TaskAction` vẫn không hit khi debug | Task không trong graph | Kiểm `:app:diagnosticReport`/`:app:check` |
| `--no-daemon` không giúp | Single-use daemon có thể tồn tại | Dùng đúng Gradle Daemon JDWP |
| `--debug` có log nhưng IDE không dừng | Không bật JDWP | Dùng `-Dorg.gradle.debug=true` |
| CI bị treo khi dùng debugger | `suspend=true`, không có IDE attach | Không giữ debug trong CI |
| Windows remote debugger sai host | IDE/terminal ở hai contexts | Kiểm localhost/container port forwarding |
| TestGradle/IDE Gradle khác CLI | Gradle JVM/Wrapper/toolchain khác | So `gradlew --version`, IDE Gradle settings |
| Task report cũ vẫn còn sau failed build | Fail trước write, file không bị xóa | Không coi output cũ là success |
| Debugger chỉ dừng ở phiên bản code cũ | Stale plugin compiled output | Sync/rebuild included build, kiểm classpath |

Port inspection:

```bash
lsof -nP -iTCP:5005 -sTCP:LISTEN
```

Windows PowerShell:

```powershell
Get-NetTCPConnection -LocalPort 5005 -State Listen
```

Không có output từ lệnh kiểm port có thể đơn giản vì Gradle chưa lắng nghe. Nếu remote debugger từ container/VM, dùng tunnel/forwarding an toàn; không mở port debug public.

## 17. CLI/IDE khác nhau: checklist tái lập

Khi terminal pass nhưng IDE fail:

1. IDE có mở đúng root chứa `settings.gradle.kts`?
2. Gradle import dùng Wrapper hay một distribution tùy chọn?
3. Gradle JVM từ IDE khác terminal `JAVA_HOME`?
4. Có `org.gradle.java.home`/Daemon JVM criteria override?
5. IDE có bật offline mode và thiếu JUnit cache?
6. IDE có injected init scripts hoặc tool window settings khác?
7. IDE dùng configuration cache còn CLI tắt?
8. IDE đang run JUnit qua IntelliJ runner hay Gradle runner?
9. `build-logic` đã sync và source classpaths đúng?
10. Có build script/plugin dependencies resolve khác phiên bản?
11. Có stale Gradle Daemon chạy với JVM args khác?
12. Có task name hoặc working directory khác?

Chạy Gradle Wrapper CLI cùng command trước để có baseline. Nếu CLI cũng fail, dùng `--stacktrace --info` và remote JDWP. Nếu chỉ IDE fail, ưu tiên cấu hình IDE trước khi sửa plugin.

**Build Scan** có thể hỗ trợ điều tra task graph/environment, nhưng chỉ publish khi organization policy chấp nhận dữ liệu gửi đi. Scan không thay thế interactive debugger khi cần inspect local variables.

## 18. Chạy lại không debug để xác nhận sửa lỗi

Sau khi hiểu biến/hàm gây lỗi:

1. Khôi phục `debugInfo { label.set("app-team") }`.
2. Gỡ tạm `org.gradle.debug`/`--debug-jvm` khỏi run configuration.
3. Gỡ debugOptions enabled hoặc scripts instrumenting không cần.
4. Chạy `./gradlew :app:check --stacktrace`.
5. Kiểm `app/build/reports/diagnostics/report.txt` đúng `label=app-team`.
6. Chạy lại cùng task không sửa inputs, quan sát `UP-TO-DATE` nếu task output/history vẫn hợp lệ.
7. Nếu plugin hứa hỗ trợ configuration cache, chạy `:app:check --configuration-cache` hai lần và kiểm problems report.
8. Nếu sửa plugin API, thêm unit/functional regression test cho bug.
9. Chạy tests trên JDK/Gradle versions được tổ chức hỗ trợ.
10. Review git diff để bảo đảm không commit debug port, disabled tests, hardcoded paths hoặc secrets.

**Không tắt cấu hình/bộ nhớ đệm vĩnh viễn chỉ vì debugger cần code path chạy lại.** Đó là phương tiện chẩn đoán tạm thời, không phải kiến trúc build logic.

## 19. Bài tập tự luyện

### Bài 1 — ba breakpoints

Đặt B trong `Plugin.apply`, C trong task registration lambda, A trong `@TaskAction`. Chạy `:app:help` và `:app:diagnosticReport` riêng với config cache tắt; ghi breakpoint nào hit và tại sao.

### Bài 2 — lỗi label rỗng

Thay `label.set("   ")`, chạy Daemon debugger, inspect before/after `trim()` và xác nhận `GradleException`. Khôi phục label hợp lệ.

### Bài 3 — bỏ `--rerun-tasks`

Chạy task một lần để tạo report, sau đó chạy lại với debugger không `--rerun-tasks` và ghi vì sao breakpoint action có thể không hit. Thử lại có `--rerun-tasks`.

### Bài 4 — config cache reuse

Chạy `:app:diagnosticReport --configuration-cache` hai lần; khi cache reuse, thử đặt breakpoint trong `apply()`. Chạy lại với `--no-configuration-cache`, so sánh.

### Bài 5 — debug JUnit JVM

Bật `:app:test --tests example.app.MainTest --debug-jvm`, attach IDE và dừng trong `MainTest.java`. Giải thích tại sao không phải debugger của Gradle Daemon.

### Bài 6 — TestKit

Tạo một functional test có consumer fixture; so sánh IDE Debug Test thường với `GradleRunner.withDebug(true)`. Đọc task outcome và breakpoint.

### Bài 7 — port conflicts

Chuyển Gradle debug từ 5005 sang5006, chỉnh IntelliJ remote configuration. Không mở JDWP ra network.

### Bài 8 — eager evaluation

Thử thay Provider mapping bằng `ext.getLabel().get()` quá sớm trong bản sandbox. Inspect value tại `apply` và action; sau đó sửa về `task.getLabel().set(ext.getLabel())`.

### Bài 9 — plugin classpath stale

Sửa một message string trong plugin Java source, sync/rebuild included build, debug lại. Kiểm IDE đang dừng đúng code mới và plugin ID đúng.

### Bài 10 — debug đúng phase

Tạo một lỗi trong `settings.gradle.kts`, một lỗi trong `Plugin.apply` và một lỗi ở `@TaskAction` (từng lỗi riêng). Dùng `help`, `diagnosticReport`, `--stacktrace` để phân loại theo phase trước khi attach debugger.

## 20. Câu hỏi tự kiểm tra

1. **Plugin Java của Gradle thường chạy trong JVM nào?** Gradle Daemon.
2. **Mở Daemon debugger bằng flag nào?** `-Dorg.gradle.debug=true`.
3. **Port mặc định?** 5005.
4. **Daemon có tự chờ IDE khi debug bật?** Có, mặc định suspend.
5. **`--debug` có bật JDWP không?** Không, chỉ verbose logs.
6. **Vì sao breakpoint `apply` không hit khi config cache reuse?** Configuration code không chạy lại.
7. **Tắt config cache tạm bằng gì?** `--no-configuration-cache`.
8. **Vì sao `@TaskAction` có thể không hit?** Task `UP-TO-DATE`/`FROM-CACHE`/`SKIPPED`.
9. **Buộc task action chạy để quan sát?** `--no-build-cache --rerun-tasks`.
10. **`tasks.register` có always configure task ngay không?** Không.
11. **TaskProvider.get ở configuration time có thể gây gì?** Eager task realization.
12. **JUnit test debug dùng gì?** `--debug-jvm` hoặc IDE Debug Test.
13. **Daemon debugger có mặc nhiên debug test JVM không?** Không.
14. **TestKit nested build mặc định có cùng JVM với JUnit không?** Không.
15. **TestKit debug API?** `withDebug(true)` / `org.gradle.testkit.debug=true`.
16. **Java toolchain17 có bắt Daemon dùng17 không?** Không nhất thiết.
17. **`--no-daemon` có đảm bảo JVM client không?** Không.
18. **Vì sao không bind debug host `*` tùy tiện?** Rủi ro bảo mật JDWP.
19. **Nếu plugin ID không resolve, breakpoint apply có hit không?** Không.
20. **Nếu IDE “Source not found” thì kiểm gì?** Source attachment/compiled class/version mapping.
21. **`:app:test` có tự chạy `diagnosticReport` trong demo không?** Không; `:app:check` mới dependsOn report.
22. **Debug Worker processIsolation bằng Daemon debugger đủ chưa?** Chưa, worker JVM riêng.
23. **Evaluate Expression gọi resolve() có vô hại không?** Không; có thể kích hoạt side effects.
24. **Sau debug phải chạy lại với caches bình thường không?** Có, để kiểm correctness/performance.
25. **Một bug được sửa nên có gì?** Reproduction, regression test, verified output và clean diff.

## 21. Checklist nghiệm thu

- [ ] Xác định đúng initialization/configuration/execution failure.
- [ ] Biết Gradle Wrapper version, Gradle JVM và application/test JVM.
- [ ] IDE import đúng root và included `build-logic` source.
- [ ] Breakpoint ở compiled class/version thật.
- [ ] Đã chạy đúng task path `:app:diagnosticReport`.
- [ ] Phân biệt `Plugin.apply`, lazy task config và `@TaskAction`.
- [ ] Sử dụng `org.gradle.debug=true`, không nhầm `--debug`.
- [ ] IDE attach đúng `localhost:5005` hoặc port đã đặt.
- [ ] Không expose debugger ra public network.
- [ ] Debug config phase với `--no-configuration-cache` khi cần.
- [ ] Debug action với `--no-build-cache --rerun-tasks` khi cần.
- [ ] Không tắt task checking/quality gates chỉ để breakpoint hit.
- [ ] Không gọi Provider/TaskProvider methods có side effects vô cớ.
- [ ] Dùng `--debug-jvm` cho forked test JVM, không phải plugin JVM.
- [ ] TestKit `withDebug(true)` khi debug nested functional build.
- [ ] Hiểu Worker API process isolation có JVM riêng.
- [ ] Kiểm source mapping và stale classpath nếu breakpoint unverified.
- [ ] Kiểm negative case label blank và message GradleException.
- [ ] Kiểm correct output `label=app-team` trong report.
- [ ] Khôi phục invalid labels và temporary debug flags.
- [ ] Không commit JDWP suspend port trong Gradle project properties.
- [ ] Run Gradle verification bình thường và kiểm regressions.
- [ ] Kiểm configuration cache compatibility nếu là project requirement.
- [ ] Có regression test cho lỗi được tìm thấy.

## 22. Ghi nhớ

- **Gradle build logic thường chạy trong Gradle Daemon**, không phải Java application/JUnit JVM.
- **`-Dorg.gradle.debug=true` + Remote Attach `localhost:5005`** là phương án chính, ít phụ thuộc IDE.
- **`--debug` chỉ là log level**; `--debug-jvm` nhắm test/application fork.
- **Plugin.apply thuộc configuration**, `@TaskAction thuộc execution** và có thể bị Gradle skip.
- **TaskProvider/Provider là lazy**: đừng làm thay đổi hành vi bằng `get()` sớm chỉ để quan sát.
- **Configuration cache, up-to-date checking và build cache** có thể giải thích một breakpoint không hit.
- **TestKit `withDebug(true)`** giải quyết trường hợp nested Gradle build khác test JVM.
- **Khi task fork process/worker**, cần debug đúng child JVM; Daemon debugger không tự đi theo.
- **Giữ JDWP local và tắt sau khi debug**; CI không nên bị suspend chờ IDE.
- **Chốt bằng verify outputs và regression tests**, không chỉ thấy debugger dừng.

## Tài liệu chính thức

- [Gradle — Troubleshooting Builds](https://docs.gradle.org/current/userguide/troubleshooting.html): debug build logic bằng `org.gradle.debug`, port5005, logs.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): `org.gradle.debug.host`, `port`, `suspend`, `server`.
- [Gradle — Build Environment](https://docs.gradle.org/current/userguide/build_environment.html): debug/Daemon JVM properties.
- [Gradle — Gradle Daemon](https://docs.gradle.org/current/userguide/gradle_daemon.html): client/daemon JVM và single-use daemon.
- [Gradle — Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html): initialization/configuration/execution.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `register`, `TaskProvider`, `named`, realization.
- [Gradle — Developing Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins.html): binary plugins và Gradle API.
- [Gradle — Java Gradle Plugin](https://docs.gradle.org/current/userguide/java_gradle_plugin.html): `java-gradle-plugin` and descriptors.
- [Gradle — Testing Build Logic with TestKit](https://docs.gradle.org/current/userguide/test_kit.html): `GradleRunner.withDebug(true)`.
- [Gradle — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): `--debug-jvm`, `Test.debugOptions`.
- [Gradle — Worker API](https://docs.gradle.org/current/userguide/worker_api.html): process/classloader/no-isolation.
- [Gradle — JavaDebugOptions API](https://docs.gradle.org/current/javadoc/org/gradle/process/JavaDebugOptions.html): typed debug options for forked JVMs.
- [IntelliJ IDEA — Gradle Tasks](https://www.jetbrains.com/help/idea/work-with-gradle-tasks.html): Gradle script/run/debug features.
- [IntelliJ IDEA — Run/Debug Gradle Configuration](https://www.jetbrains.com/help/idea/run-debug-gradle.html): IDE run/debug settings.
- [IntelliJ IDEA — Gradle Integration](https://www.jetbrains.com/help/idea/gradle.html): Gradle JVM and Wrapper settings.

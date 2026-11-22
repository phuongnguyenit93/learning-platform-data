# Import dự án vào IntelliJ IDEA, Eclipse hoặc VS Code trong Gradle

## 1. Mục tiêu và bối cảnh

Bài thuộc nhóm **IDE và chẩn đoán** của chủ đề **Build Tool Gradle**. Một dự án Java có thể build thành công bằng Gradle Wrapper trên command line nhưng vẫn gặp lỗi trong IDE: thiếu module, không nhận JUnit, classpath sai, Java 17 không được phát hiện, Gradle sync thất bại hoặc Java source hiển thị lỗi dù compiler Gradle đã pass. Ngược lại, IDE có thể cho phép Run Main thành công nhờ classpath do người dùng thêm thủ công trong khi CI chạy Gradle lại thất bại.

**Import Gradle project** là quá trình IDE dùng Gradle build model (Settings, plugins, subprojects, source sets, dependencies và toolchains) để tạo Java project model, mã nguồn, thư viện, Gradle tasks và run/debug configurations. Nó không đơn giản là mở một folder và cũng không chứng minh tất cả Gradle tests đều pass.

Ba cách tích hợp:

- **IntelliJ IDEA:** Có tích hợp Gradle sẵn. Mở project root, dùng Wrapper và Sync Gradle Project.
- **Eclipse:** Dùng **Buildship** để import, refresh và thực thi Gradle build.
- **Visual Studio Code (VS Code):** Dùng **Extension Pack for Java** và **Gradle for Java** để nhập model, chạy task và khám phá dependencies.

Kết quả học tập: mở đúng root Gradle, cấu hình JVM chạy Gradle khác với Java toolchain, import nhiều subprojects, chạy Java 17/JUnit, biết khi nào nên Sync/Refresh hay Build/Run, xác định nguồn lỗi CLI/IDE, quản lý generated metadata và thực hành an toàn khi mở build scripts chưa tin cậy.

## 2. Những file quan trọng trong Gradle project

Một Gradle multi-project build thông thường:

~~~text
gradle-ide-demo/
├── settings.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── core/
│   ├── build.gradle.kts
│   └── src/...
└── app/
    ├── build.gradle.kts
    └── src/...
~~~

- `settings.gradle.kts` hoặc `settings.gradle` là entrypoint để xác định tên root, modules và included builds.
- `build.gradle.kts` hoặc `build.gradle` xác định plugins, dependencies, tasks và toolchains của mỗi project.
- Bộ `gradlew`/`gradlew.bat`/`gradle/wrapper` chọn Gradle distribution theo project.
- `gradle/libs.versions.toml` có thể chứa version catalog, `gradle.lockfile` khóa dependencies khi dùng locking.
- Project `.gradle/` và `build/` chứa local execution state/outputs, không phải định nghĩa module graph.

**Gradle build scripts và Wrapper là nguồn sự thật**. Các file IDE như `.idea/`, `*.iml`, `.project`, `.classpath` và `.vscode/settings.json` phục vụ editor/workspace; thay đổi classpath ở đó không tự cập nhật Gradle model.

### 2.1. Subproject và included build không giống nhau

~~~kotlin
rootProject.name = "gradle-ide-demo"
include(":core", ":app")
~~~

cho Gradle biết hai subprojects. Trong khi đó:

~~~kotlin
pluginManagement {
    includeBuild("build-logic")
}
~~~

là cơ chế đăng ký **một included Gradle build** để cung cấp plugin, không phải một subproject có tên `:build-logic`. Nếu IDE không thấy plugin nội bộ, hãy kiểm tra root Settings và included build, không tự thay `includeBuild` bằng `include`.

## 3. IDE lấy Gradle model như thế nào?

Gradle có **Tooling API** cho phép IDE query build model, source sets, dependencies và chạy Gradle tasks. IntelliJ IDEA/Eclipse Buildship tích hợp dựa trên Tooling API; VS Code Gradle for Java có Gradle Build Server và các công cụ build Gradle liên quan.

~~~text
Open Gradle project root
       |
       v
Find Settings, Wrapper and module build files
       |
       v
Choose Gradle distribution + Gradle JVM
       |
       v
Load Gradle Tooling API / Gradle Build Server model
       |
       v
Resolve plugins, project graph and dependencies
       |
       v
Map source sets to IDE modules/Java projects
       |
       v
Editor indexing, completion, run/debug and tasks
       |
       v
User invokes :app:test / :app:run
~~~

**Sync/Refresh** cập nhật model IDE. **Build/Test/Run** thực thi Gradle tasks hoặc IDE runner. Gradle project có thể import thành công dù test code fail; cũng có thể chạy CLI thành công nhưng IDE model chưa được refresh.

## 4. Phân biệt Gradle JVM, Java toolchain và IDE JDK

| Thành phần | Vai trò | Kiểm tra ở đâu? |
| --- | --- | --- |
| Gradle Client JVM | Khởi chạy Wrapper/Gradle client | `JAVA_HOME`, PATH, IDE launcher |
| Gradle Daemon JVM | Chạy Gradle build logic, plugins và tasks | Gradle JVM trong IDE, `org.gradle.java.home`, Daemon JVM criteria |
| Java toolchain | JVM/JDK Gradle dùng để compile/test/javadoc | `java.toolchain.languageVersion` |
| Project SDK/JRE/VS Code Java runtime | Java editor và/hoặc IDE Run configuration | Project Settings/Installed JREs/Java Runtime |
| `options.release` | Java language/API/bytecode target | JavaCompile configuration |

**Gradle 9.x yêu cầu JVM 17+ để chạy Gradle Daemon.** Nếu IDE dùng JDK 11 để chạy Gradle 9.x, project có thể fail trước khi Gradle chọn Java 17 toolchain. Các version Gradle cũ có compatibility matrix khác: luôn đối chiếu **Gradle Wrapper đang dùng**, không đoán từ JDK mới nhất trên máy.

Ví dụ Gradle JVM 21 và compiler toolchain Java 17 có thể cùng tồn tại nếu Wrapper hỗ trợ; compiler dùng Java 17 và `--release 17` theo build script.

Gradle Daemon JVM criteria trong `gradle/gradle-daemon-jvm.properties`, nếu có, có precedence riêng đối với `JAVA_HOME` và `org.gradle.java.home`. Không chỉnh bừa cả ba khi bị lỗi JDK.

### 4.1. Lệnh kiểm tra môi trường

Linux/macOS:

~~~bash
java -version
javac -version
echo "$JAVA_HOME"
./gradlew --version
./gradlew -q javaToolchains
~~~

Windows PowerShell:

~~~powershell
java -version
javac -version
$env:JAVA_HOME
.\gradlew.bat --version
.\gradlew.bat -q javaToolchains
~~~

Gradle chỉ có thể tự tải toolchain khi resolver/repositories tương ứng đã được cấu hình. IDE Project SDK 17 không đồng nghĩa Gradle có thể tự động tìm JDK 17 cho tasks.

## 5. Lab hoàn chỉnh: hai module Java 17

Cùng một project cho cả ba IDE:

~~~text
gradle-ide-demo/
├── settings.gradle.kts
├── core/
│   ├── build.gradle.kts
│   └── src/main/java/demo/core/Greeter.java
├── app/
│   ├── build.gradle.kts
│   ├── src/main/java/demo/app/Main.java
│   └── src/test/java/demo/app/GreetingTest.java
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
~~~

Cần một JDK 17, Gradle Wrapper hợp lệ và Maven Central/mirror cho JUnit. Nếu mới tạo repo và chưa có Wrapper, dùng một Gradle installation tin cậy để chạy `gradle wrapper` theo version đã được team phê duyệt; kiểm tra và commit cả Wrapper scripts/JAR/properties. Trong dự án có sẵn, dùng Wrapper hiện có, không tự tải JAR từ nguồn lạ.

### 5.1. Root settings.gradle.kts

~~~kotlin
rootProject.name = "gradle-ide-demo"
include(":core", ":app")
~~~

Root không cần `build.gradle.kts` trong ví dụ này: mỗi module có build script riêng. Khi import IDE, phải chọn folder **gradle-ide-demo**, không chọn riêng `app/`.

### 5.2. core/build.gradle.kts — Java Library

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.jvm.toolchain.JavaLanguageVersion

plugins {
    `java-library`
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}
~~~

`java-library` cung cấp Java source sets, compiler/JAR tasks, `api` và `implementation` configurations. Module core không có external dependency nên không cần repository.

### 5.3. app/build.gradle.kts — Java Application + JUnit

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.jvm.toolchain.JavaLanguageVersion

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
    options.encoding = "UTF-8"
    options.release.set(17)
}

dependencies {
    implementation(project(":core"))
    testImplementation(platform("org.junit:junit-bom:5.10.2"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}

application {
    mainClass.set("demo.app.Main")
}
~~~

`implementation(project(":core"))` tạo quan hệ project-to-project và được Gradle dùng để xây dựng classpath/task dependency metadata. Không thêm core JAR thủ công ở IDE. JUnit BOM version 5.10.2 được pin chỉ làm ví dụ, không khẳng định latest; trong môi trường doanh nghiệp dùng mirror/versions theo chính sách.

### 5.4. core/src/main/java/demo/core/Greeter.java

~~~java
package demo.core;

public final class Greeter {
    private Greeter() {
    }

    public static String message(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

### 5.5. app/src/main/java/demo/app/Main.java

~~~java
package demo.app;

import demo.core.Greeter;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeter.message("Lan"));
    }
}
~~~

### 5.6. app/src/test/java/demo/app/GreetingTest.java

~~~java
package demo.app;

import demo.core.Greeter;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingTest {
    @Test
    void greetsVietnameseName() {
        assertEquals("Xin chào, Lan!", Greeter.message("Lan"));
    }
}
~~~

JUnit test chứng minh Gradle đã nhận JUnit dependencies cùng source set test và liên kết `app` với `core` đúng.

## 6. Chạy CLI trước khi import IDE

Từ root folder:

Linux/macOS:

~~~bash
./gradlew --version
./gradlew projects --console=plain
./gradlew :core:build :app:test --console=plain
./gradlew :app:run --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat projects --console=plain
.\gradlew.bat :core:build :app:test --console=plain
.\gradlew.bat :app:run --console=plain
~~~

Kết quả cần xác minh: Gradle `projects` liệt kê `:core` và `:app`; JUnit test có một method PASS; Java Main in ra **đúng một dòng**:

~~~text
Xin chào, Lan!
~~~

Đây là stdout do `demo.app.Main` in ra, **không phải toàn bộ transcript Gradle**. Task headers, timings, build cache statuses tùy Gradle version và environment.

### 6.1. Biên dịch Java 17 không dùng Gradle

Để kiểm tra riêng Java sources:

Linux/macOS:

~~~bash
mkdir -p out
javac -encoding UTF-8 --release 17 \
  -d out \
  core/src/main/java/demo/core/Greeter.java \
  app/src/main/java/demo/app/Main.java
java -cp out demo.app.Main
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -encoding UTF-8 --release 17 -d out `
  core\src\main\java\demo\core\Greeter.java `
  app\src\main\java\demo\app\Main.java
java -cp out demo.app.Main
~~~

**Stdout chính xác:** `Xin chào, Lan!`. Lưu ý khi soạn lại lệnh Windows ở trên: ký hiệu tiếp dòng của PowerShell là dấu backtick, không phải ký hiệu `; trình soạn thảo Markdown sẽ thay mỗi ký hiệu ` bằng backtick. Lệnh `javac/java` chỉ xác minh Java source, **không xác minh Gradle JUnit, Tooling API hay IDE import**.

### 6.2. CLI fail trước IDE

~~~bash
./gradlew :app:test --stacktrace --console=plain
./gradlew :app:test --info --console=plain
~~~

Nếu CLI fail do missing dependency, plugin resolution, Java compiler hoặc toolchain, sửa Gradle model trước khi invalidating IDE caches. Nếu CLI PASS nhưng IDE đỏ, chuyển sang kiểm tra IDE sync, JDK và language server.

## 7. IntelliJ IDEA: import chuẩn

IntelliJ IDEA hỗ trợ Gradle trực tiếp, **không cần chạy `gradle idea`**.

### 7.1. Các bước

1. Mở IntelliJ IDEA, chọn **Open** hoặc File → Open.
2. Chọn **root gradle-ide-demo/** có `settings.gradle.kts` và `gradlew`.
3. Nếu IDE hỏi Trust Project, chỉ trust khi source/build scripts đã được kiểm tra; import Gradle có thể chạy plugin code.
4. Nếu IDE phát hiện nhiều build configurations (Maven/Gradle/Eclipse), chọn Gradle.
5. Để IDE dùng Gradle Wrapper distribution do project xác định.
6. Chọn **Gradle JVM** tương thích với Wrapper; trong lab dùng JDK 17.
7. Chờ sync/project indexing và xem Gradle/Build tool window khi có lỗi.
8. Kiểm tra linked Gradle project có modules core/app và các tasks.

### 7.2. Thiết lập quan trọng

~~~text
Settings / Preferences
  -> Build, Execution, Deployment
  -> Build Tools
  -> Gradle
~~~

Trong IntelliJ gần đây, trường **Distribution** có lựa chọn Wrapper từ `gradle-wrapper.properties`. Một số phiên bản cũ hiển thị **Use Gradle from**. Nên tránh chọn local Gradle khác version. Kiểm tra Gradle JVM, không nhầm với Project SDK và Java toolchain.

Khi Gradle tool window không xuất hiện, dự án có thể chưa linked. Dùng **Link Gradle Project** trong Gradle tool window hoặc right-click build script để Import Gradle Project theo UI hiện tại.

### 7.3. Kiểm tra sau import

- Project tool window có core/app với Java source roots và test sources.
- `import demo.core.Greeter;` trong `Main.java` không unresolved.
- `org.junit.jupiter.api.Test` ở `GreetingTest.java` được nhận.
- Gradle tool window có `:app:run`, `:app:test` và `:core:build`.

### 7.4. Sync Gradle Project sau thay đổi

Sau khi sửa `settings.gradle.kts`, `build.gradle.kts` hoặc đổi plugin/dependencies, chạy **Sync Gradle Project** hoặc **Sync All Gradle Projects** từ Gradle tool window. IntelliJ cũng có thể auto-sync với build script changes.

**Sync** cập nhật model IDE; **Build Project** chạy Gradle hoặc internal builder tùy Settings; **Run** có thể là Java launcher hoặc Gradle delegated task. Chúng không thay nhau.

### 7.5. Chạy ứng dụng/test

Từ Gradle tool window chọn app task `run` và `test`. Hoặc trong IDE Terminal:

~~~bash
./gradlew :app:run --console=plain
./gradlew :app:test --console=plain
~~~

Java Main in `Xin chào, Lan!`; JUnit test dự kiến PASS. Right-click `Main.main` → Run có thể chạy bằng IntelliJ launcher, khác Gradle về working directory/classpath/args. Nếu cần đồng nhất CI, chọn **Build and run using Gradle** và dùng Gradle tests/delegated run.

### 7.6. Không dùng IDE-only dependency

Thêm library bằng Project Structure mà không cập nhật Gradle `dependencies` có thể bị mất ở lần reimport. Nếu `./gradlew :app:test` fail, chỉnh sửa Gradle build script trước, không chỉ thêm JAR vào IntelliJ.

### 7.7. Legacy idea plugin

Gradle có `idea` plugin sinh `.ipr/.iml`, nhưng với native IntelliJ Gradle integration không cần chạy `./gradlew idea`. Gradle 9.x còn deprecate nhiều task sinh IDE metadata. Một số dự án legacy có custom model settings cần migration riêng; không biến workflow cũ thành bước import bắt buộc cho project mới.

## 8. Eclipse IDE: Buildship

**Buildship Gradle Integration** cho phép Eclipse import Gradle project qua Gradle Tooling API. Nếu Eclipse không có Gradle Import option, kiểm tra Buildship trong Eclipse Marketplace hoặc package Java Developers được tổ chức phê duyệt.

### 8.1. Import

1. File → Import...
2. Chọn **Gradle → Existing Gradle Project**.
3. Trỏ root directory đến `gradle-ide-demo/`, không chọn chỉ `app`.
4. Chọn Gradle Wrapper distribution khi wizard cho lựa chọn.
5. Chọn Gradle JDK/Gradle User Home phù hợp.
6. Finish và chờ Gradle model/dependencies được import.
7. Kiểm tra Project Explorer, Problems, Console và Gradle Tasks/Executions view.

**General → Existing Projects into Workspace** chỉ đọc Eclipse project metadata thông thường, không bảo đảm một Buildship-linked Gradle model.

### 8.2. Gradle JDK và Java JRE

~~~text
Window -> Preferences -> Gradle -> Gradle JDK
Window -> Preferences -> Java -> Installed JREs
~~~

Đường dẫn/label có thể khác theo Eclipse version. Gradle JVM phải tương thích Wrapper và Java toolchain trong Gradle script vẫn quyết định JDK compile/test. Eclipse JDT compiler compliance/Installed JRE settings không tự thay `java.toolchain`.

### 8.3. Refresh Gradle Project

Sau khi sửa Gradle build scripts hoặc thêm module:

~~~text
Project Explorer -> right-click Gradle project
  -> Gradle -> Refresh Gradle Project
~~~

**Buildship Refresh** cập nhật Gradle model/dependencies. Eclipse **Project → Clean** chỉ tác động Eclipse builder state, không thay refresh.

### 8.4. Run/Test

Trong Gradle Tasks view hoặc Run As → Gradle Task (tùy Buildship version), chạy `:app:run`, `:app:test`, `:core:build`. Kiểm tra `Xin chào, Lan!`, test report và task success.

Eclipse **Build Automatically** có thể chỉ dùng JDT incremental builder, không nhất thiết chạy Gradle verification/code-generation tasks. Khi kiểm chứng CI hãy chạy Gradle Tasks/CLI.

### 8.5. Legacy eclipse plugin

Gradle `eclipse` plugin sinh `.project/.classpath` theo cách cũ. Buildship import hiện đại không yêu cầu `./gradlew eclipse`; những file-generation tasks của `eclipse` plugin đang bị deprecated trong Gradle 9.x. Đừng coi việc Eclipse thấy `.project` là bằng chứng Buildship import thành công.

## 9. Visual Studio Code: Extension Pack for Java + Gradle for Java

VS Code là editor, nên Gradle Java experience phụ thuộc extensions:

- **Extension Pack for Java:** Java Language Server, Project Management, Java Debugger, Java Test support.
- **Gradle for Java** (extension ID `vscjava.vscode-gradle`): Gradle project discovery, Gradle tasks explorer, dependencies và Gradle Build Server.

Theo tài liệu VS Code hiện hành, Gradle Build Server được sử dụng mặc định khi cài Gradle for Java; setting `java.gradle.buildServer.enabled` có thể bật/tắt. Extension hỗ trợ Gradle **Java projects**, không thay Android Studio cho Android Gradle projects.

### 9.1. Import

1. Cài Extensions từ nguồn tin cậy.
2. File → Open Folder...
3. Chọn **root gradle-ide-demo/** có `settings.gradle.kts` và Wrapper.
4. Chỉ chọn Trust Workspace sau khi xem xét build scripts/plugins.
5. Kiểm tra JDK runtime của Java extensions.
6. Chờ Java/Gradle model import; kiểm tra **JAVA PROJECTS** và **Gradle Tasks** view.
7. Chạy `:app:run` và `:app:test` từ Gradle tasks UI hoặc integrated Terminal.

Project discovery có thể nhận biết Wrapper scripts/build files; `gradle.nestedProjects` dành cho nested independent projects, không cần bật riêng cho `:core` và `:app` đã được Settings include.

### 9.2. Gradle Build Server setting

~~~json
{
  "java.gradle.buildServer.enabled": true
}
~~~

Đây là JSON settings fragment, chỉ cần đặt vào `.vscode/settings.json` nếu version extension hỗ trợ và có lý do chỉnh. Đừng mặc định mọi Gradle import issue do setting này: kiểm tra Output panel của Java/Gradle trước.

### 9.3. Java runtime

Dùng Command Palette → **Java: Configure Java Runtime**. Mảnh JSON sau **có placeholder**, phải thay path bằng JDK thật:

~~~json
{
  "java.configuration.runtimes": [
    {
      "name": "JavaSE-17",
      "path": "/path/to/installed/jdk-17",
      "default": true
    }
  ]
}
~~~

Setting Java extension không bảo đảm Gradle Daemon JVM giống hệt. So với `JAVA_HOME`, Wrapper và Gradle extension/Build Server logs nếu CLI khác VS Code.

### 9.4. Chạy tasks và xác minh

~~~bash
./gradlew :app:run --console=plain
./gradlew :app:test --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat :app:run --console=plain
.\gradlew.bat :app:test --console=plain
~~~

Java Main in chính xác `Xin chào, Lan!`.

### 9.5. Refresh và sửa index stale

Nếu Java import/dependencies vẫn đỏ sau sửa Gradle:

1. Lưu `settings.gradle.kts` / `build.gradle.kts`.
2. Command Palette → **Java: Import Java projects in workspace**.
3. Chờ và xem Java/Gradle Output logs.
4. Nếu cần, **Java: Clean Java Language Server Workspace** rồi reload window theo extension.
5. Kiểm tra Gradle Tasks view và CLI `./gradlew projects`.
6. Chỉ khi có evidence, sửa Gradle Build Server setting/runtime conflicts.

**Không xóa Gradle User Home `~/.gradle`** chỉ vì Java Language Server indexing stale. Java sourcePaths setting cũng không thay các Gradle source-set declarations của managed project.

## 10. Bảng đối chiếu ba IDE

| Mục | IntelliJ IDEA | Eclipse Buildship | VS Code |
| --- | --- | --- | --- |
| Import | File → Open root | File → Import → Gradle → Existing Gradle Project | File → Open Folder root |
| Gradle integration | Built-in | Buildship | Gradle for Java |
| Java tooling | IDEA project modules/indexer | Eclipse JDT | Java Language Server |
| Gradle version | Distribution = Wrapper | Wrapper distribution | Project Wrapper via extension |
| Gradle JVM | Gradle Settings | Preferences → Gradle → Gradle JDK | Java/Gradle extension JVM selection |
| Reload model | Sync Gradle Project | Gradle → Refresh Gradle Project | Java: Import Java projects in workspace |
| Tasks | Gradle tool window | Gradle Tasks | Gradle Tasks explorer |
| Code/test run | IDE runner hoặc Gradle | Eclipse runner hoặc Gradle | Java debugger hoặc Gradle |
| Index stale | Gradle sync/IDE indexer | Buildship refresh/JDT | Java language server clean |
| Source of truth | Gradle model | Gradle model | Gradle model |

Các menu có thể đổi theo IDE version, nhưng công việc import/sync/source model vẫn như nhau.

## 11. Khi nào Sync/Refresh, khi nào Build/Test?

**Sync/Refresh** khi:
- Thêm/xóa module trong `settings.gradle.kts`.
- Đổi dependencies, plugins, repositories, source sets.
- Thêm Java toolchain, test suite, convention plugin hoặc included build.
- Đổi Wrapper version, version catalog hoặc Gradle configuration.
- Checkout branch có thay đổi Gradle build scripts.

**Build/Test/Run** khi:
- Thay Java source và muốn kiểm chứng bytecode/runtime.
- Chạy annotation processing hoặc code generation.
- Kiểm tra JUnit assertions và Gradle verification.
- Chạy `:app:run`, `:app:test` hay `:core:jar`.

Một lần IDE sync thành công **không** chứng minh Java/JUnit tasks pass. Một lần Eclipse JDT Build Automatically thành công cũng không chắc Gradle plugin custom tasks đã chạy.

## 12. Chẩn đoán qua CLI trước

Các lệnh hữu ích:

~~~bash
./gradlew --version
./gradlew projects --console=plain
./gradlew :app:tasks --all --console=plain
./gradlew :app:dependencies --configuration compileClasspath --console=plain
./gradlew :app:dependencies --configuration testRuntimeClasspath --console=plain
./gradlew :app:dependencyInsight --dependency junit-jupiter --configuration testRuntimeClasspath --console=plain
./gradlew :app:test --stacktrace --console=plain
./gradlew :app:test --info --console=plain
./gradlew :app:test --dry-run --console=plain
~~~

**`--dry-run` không chạy task actions hay tests**: nó chỉ cho thấy Gradle task graph. Để chứng minh JUnit PASS, phải chạy test thật, kiểm tra Gradle Test outcome/report.

### 12.1. CLI fail và IDE fail

Khả năng là Gradle build thực sự lỗi: missing source/module, dependency resolution, compiler/JDK, plugin resolution, private repository credentials hoặc build script exception. Sửa Gradle model/source trước.

### 12.2. CLI pass nhưng IDE fail

Kiểm tra:
- IDE mở đúng root chưa?
- Gradle Wrapper distribution hay local Gradle khác?
- Gradle JVM/Daemon JVM có tương thích không?
- IDE đã Sync/Refresh sau thay đổi chưa?
- Java source set mapping và dependency classpath đã nhận chưa?
- IDE có offline mode, proxy/TLS, Gradle User Home path khác CLI?
- Java indexing/workspace state có stale?
- IDE Run/Test runner khác Gradle delegated tasks?

## 13. Lỗi module, classpath và dependency

### 13.1. Không thấy core trong IDE

CLI:

~~~bash
./gradlew projects --console=plain
~~~

Nếu không thấy `:core`, sửa `include(":core", ":app")` tại đúng root. Nếu CLI thấy nhưng IDE không thấy, mở đúng root và refresh Gradle project; không add module thủ công như thay thế Gradle import.

### 13.2. JUnit import đỏ

Kiểm tra JUnit nằm ở `app/build.gradle.kts` trong `testImplementation`, test runtime launcher, repository/mirror và `app/src/test/java`. Chạy `./gradlew :app:test` và dependency report, sau đó sync IDE. Không đưa JUnit vào production `implementation` chỉ vì Java test editor chưa refresh.

### 13.3. Project dependency `Greeter` không nhận

Kiểm tra `implementation(project(":core"))`, root include, Java package đúng `demo.core`, file path `core/src/main/java/demo/core/Greeter.java`. Nếu CLI compile pass nhưng IDE đỏ thì Gradle project model ở IDE stale, không phải library Java sai.

### 13.4. Plugin not found khác Maven JUnit not found

Gradle plugins có thể resolve qua `pluginManagement.repositories` hoặc included plugin build; Java/JUnit libraries resolve qua module `repositories`. Ví dụ plugin ID không có trong plugin repositories sẽ fail ngay configuration, dù Maven Central có tất cả JUnit dependencies. Phân loại đúng trước khi sửa.

## 14. Lỗi JVM/toolchain

Lỗi `Unsupported class file major version` hoặc Gradle Daemon không start có thể đến từ Gradle JVM IDE khác CLI. Lỗi `No matching toolchains found` cho thấy Gradle không tìm JDK target phù hợp; nó không được chữa bằng cách thay Java source.

Trình tự:
1. `./gradlew --version` xem Gradle/Daemon/JVM CLI.
2. Kiểm tra Wrapper properties version.
3. Kiểm tra Gradle JVM ở IDEA/Buildship/VS Code.
4. Xem `JAVA_HOME`, `org.gradle.java.home` và Daemon JVM criteria nếu có.
5. `./gradlew -q javaToolchains` xác nhận JDK 17 được phát hiện.
6. Đồng bộ IDE sau khi sửa đúng JVM.
7. Chạy lại `:app:compileJava` và `:app:test`.

Không nghĩ Java toolchain 17 tự cho phép Gradle 9.x chạy trên Java 11. Cũng không nghĩ Gradle Daemon JVM 21 tự buộc Java source target 21 khi `options.release.set(17)`.

## 15. Network, proxy, offline mode và Maven repositories

IDE Gradle import có thể download Wrapper distribution, plugin markers/implementations, JUnit/other Maven libraries và source attachments.

Các lỗi:

~~~text
Could not resolve all files ...
Plugin [id: ...] was not found ...
PKIX path building failed ...
Connection timed out
407 Proxy Authentication Required
401 Unauthorized / 403 Forbidden
~~~

Xử lý: kiểm tra CLI, Gradle Wrapper distribution URL, repository/mirror, pluginManagement, proxy và certificates. Nếu offline mode bật mà dependency chưa cached, phải cho phép resolve online qua nguồn tin cậy. Không tắt TLS verification hoặc checksum/dependency verification để import “cho nhanh”.

`--refresh-dependencies` có thể giúp khi Gradle metadata cache stale nhưng không nên dùng ở mọi build; nó không phải một cách sửa JVM/IDE indexing. Không thêm `mavenLocal()` bừa vì sẽ khiến local build phụ thuộc artifact chỉ tồn tại trên một máy nhưng CI không có.

## 16. Annotation processors và generated source code

Các dự án Lombok, MapStruct hoặc custom code generators có thể báo thiếu Java class trong IDE dù Gradle CLI pass:

- Khai báo annotation processors ở đúng Gradle configuration.
- Gradle tasks tạo generated sources cần output dir và dependency wiring rõ.
- Sync IDE để update generated source roots.
- IntelliJ có thể delegate build/run cho Gradle để processors chạy đúng.
- Eclipse Buildship refresh và kiểm tra JDT/APT settings khi cần.
- VS Code kiểm tra Gradle Build Server/Java Language Server mapping.
- Không copy generated code từ `build/generated` vào `src/main/java` như một workaround lâu dài.

## 17. Git, IDE files và security

Mẫu `.gitignore` cho lab (điều chỉnh theo team policy):

~~~gitignore
.gradle/
build/
core/build/
app/build/
out/
.idea/workspace.xml
*.iml
.metadata/
.vscode/*.log
~~~

Không nhất thiết ignore toàn bộ `.idea/`, `.vscode/` hoặc Eclipse `.settings/`: có team commit code style, launch configs và compiler preferences chung. Chỉ commit file đã review, không chứa machine-specific secret paths. Wrapper, Settings, build scripts và dependency locking/verification thường cần version control.

**Gradle import có thể thực thi build scripts/plugins.** Khi IDE hỏi Trust Project/Workspace Trust, cân nhắc rủi ro. Không chạy unknown Gradle repo với production credentials. Pin/verify Wrapper distribution; nếu có `distributionSha256Sum` phải dùng checksum thật. Không disable TLS, dependency verification hoặc source trust vì IDE import fail. Dùng secret store/Gradle-approved credential mechanism thay vì hard-code password.

## 18. Các lỗi điển hình và cách ưu tiên

| Hiện tượng | Nguyên nhân thường gặp | Bước đầu |
| --- | --- | --- |
| IntelliJ không có Gradle tool window | Project chưa linked | Link/import Gradle root |
| Eclipse không thấy Gradle import | Thiếu Buildship | Cài/enable Buildship đáng tin |
| VS Code là unmanaged folder | Thiếu extension hoặc mở sai root | Cài Java/Gradle extensions, Open Folder root |
| Chỉ thấy app, mất core | Mở sai thư mục hoặc Settings thiếu include | `./gradlew projects` |
| IDE Java/JUnit imports đỏ, CLI pass | Sync/index stale | Refresh model, Java language server |
| IDE và CLI đều fail | Gradle build thật bị lỗi | `--stacktrace`, build script/dependency |
| Unsupported class file | Gradle JVM không tương thích | Chọn JVM đúng Wrapper |
| No matching Java toolchain | Thiếu Java 17 JDK/resolver | Cài/cấu hình toolchain |
| Plugin not found | Plugin ID/repo/includeBuild | Kiểm tra pluginManagement |
| PKIX/407/401/403 | Cert/proxy/credentials | Sửa trusted network config |
| Offline import fail | Thiếu cached dependencies | Tắt offline khi có approved network |
| IntelliJ Run khác Gradle run | IDE launcher/classpath/JVM khác | Delegate to Gradle, so args |
| Eclipse Clean không cập nhật classpath | Cần Buildship refresh | Gradle → Refresh Gradle Project |
| VS Code vẫn đỏ sau refresh | Language Server state stale | Java: Clean Java Language Server Workspace |
| Tests pass trong IDE nhưng CI fail | IDE-only config | Xác minh Gradle `:app:test` |
| Gradle import chậm | Network, plugin, index, many modules | Đọc IDE/Gradle logs trước khi xóa caches |
| Generated classes thiếu | Annotation processing/source mapping | Gradle delegated compile + IDE sync |

Đừng dùng “Invalidate Caches” làm phản xạ đầu tiên. Phân biệt IDE indexer state, project-local Gradle history và Gradle User Home dependency cache trước khi can thiệp.

## 19. Bài tập thực hành

**Bài 1 — IntelliJ:** Import root, chọn Wrapper/JDK 17, kiểm tra Gradle tool window có core/app, chạy app run/test. Kỳ vọng dòng `Xin chào, Lan!` và JUnit PASS.

**Bài 2 — Eclipse:** File → Import → Gradle → Existing Gradle Project, chọn root, refresh khi đổi dependency, chạy Gradle task `:app:run`. Kỳ vọng tương đương CLI.

**Bài 3 — VS Code:** Cài Java Extension Pack + Gradle for Java, mở root, kiểm tra JAVA PROJECTS/Gradle Tasks, chạy app test và run. Nếu chưa thấy core, kiểm tra root Settings/Java import.

**Bài 4 — Thêm module:** Trong bản sao lab, tạo `tools/build.gradle.kts` với Java plugin và thêm `include(":tools")` vào root Settings. Chạy `./gradlew projects` rồi Sync/Refresh ba IDE. Kỳ vọng cùng nhận `:tools`.

**Bài 5 — Debug JDK mismatch:** Trong sandbox dùng Gradle 9.x, thử chọn Gradle JVM dưới Java 17 rồi đọc lỗi. Đặt lại một JDK tương thích; xác minh toolchain Java 17 vẫn dùng cho compilation.

**Bài 6 — So IDE runner và Gradle runner:** Chạy `demo.app.Main` từ Java Run configuration rồi `./gradlew :app:run`. Nếu output khác, kiểm tra working directory, JVM args, environment variables và classpath.

## 20. Câu hỏi ôn tập

**1.** Gradle Wrapper có giúp tránh cài Gradle global không? — Có, với project có Wrapper đầy đủ và distribution URL đáng tin.

**2.** Vì sao mở root thay vì app folder? — Vì root Settings chứa module graph và project dependencies.

**3.** Sync thành công đã chứng minh JUnit test PASS? — Chưa, phải chạy test thật.

**4.** IntelliJ có phải chạy `gradle idea`? — Không, có native Gradle import.

**5.** Eclipse dùng plugin nào? — Buildship.

**6.** VS Code cần extensions gì? — Extension Pack for Java và Gradle for Java.

**7.** Gradle 9.x chạy Daemon trên JVM 11 khi compile toolchain 17 được không? — Không, Daemon phải dùng JVM 17+.

**8.** Gradle JVM JDK 21 và Java toolchain 17 có thể khác nhau không? — Có, nếu Wrapper hỗ trợ.

**9.** JUnit test dependencies khai báo trong module nào? — App `testImplementation` và test runtime theo Gradle build script.

**10.** CLI PASS nhưng IntelliJ JUnit import đỏ, nên làm gì? — Sync Gradle project/JDK/indexing trước, không thêm JAR thủ công.

**11.** Eclipse Project Clean có thay Gradle Refresh không? — Không.

**12.** VS Code Java Language Server cache có phải Gradle dependency cache không? — Không.

**13.** `--dry-run` chứng minh tests PASS? — Không, task actions không được thực thi.

**14.** Java Main lab in gì? — `Xin chào, Lan!` và một newline.

**15.** Vì sao IDE-only dependency nguy hiểm? — CLI/CI và lần reimport không có thay đổi đó.

**16.** Có nên tắt TLS khi PKIX lỗi? — Không, sửa CA/proxy/repositories hợp lệ.

**17.** Gradle import unknown repo có an toàn như mở text file? — Không, build scripts/plugins có thể chạy code.

**18.** Vì sao không cần file-generation tasks của idea/eclip​se plugin? — IDE hiện đại import trực tiếp, các task sinh metadata cũ bị deprecated ở Gradle 9.x.

## 21. Checklist sau khi import

- [ ] Mở đúng root chứa Settings/Wrapper.
- [ ] Wrapper đáng tin và chọn đúng Gradle distribution.
- [ ] CLI `./gradlew --version` và `./gradlew projects` chạy được.
- [ ] Gradle Daemon JVM tương thích và Java toolchain 17 được Gradle nhận.
- [ ] IDE nhận cả `:core`/`:app`, source sets và JUnit dependencies.
- [ ] Các thao tác Sync/Refresh đã chạy sau khi đổi Gradle scripts.
- [ ] `./gradlew :app:test` PASS.
- [ ] `./gradlew :app:run` in `Xin chào, Lan!`.
- [ ] Không dùng IDE-only classpath như nguồn sự thật.
- [ ] Không dùng legacy metadata-generation tasks làm bước import mặc định.
- [ ] Không vô hiệu hóa TLS/dependency verification để chữa import.
- [ ] Khi CLI và IDE khác, đã kiểm tra runner, JVM, classpath và IDE index.
- [ ] IDE metadata được chia sẻ trong Git có chủ đích và không lộ secret.
- [ ] Cùng Gradle Wrapper có thể tái hiện kết quả trên CI.

## 22. Nguồn tài liệu chính thức

1. Gradle — Gradle in IDEs: https://docs.gradle.org/current/userguide/gradle_ides.html
2. Gradle — Third-party integration: https://docs.gradle.org/current/userguide/third_party_integration.html
3. Gradle — Tooling API: https://docs.gradle.org/current/userguide/tooling_api.html
4. Gradle — Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
5. Gradle — Compatibility matrix: https://docs.gradle.org/current/userguide/compatibility.html
6. Gradle — Java toolchains: https://docs.gradle.org/current/userguide/toolchains.html
7. Gradle — Gradle Daemon: https://docs.gradle.org/current/userguide/gradle_daemon.html
8. Gradle — Multi-project builds: https://docs.gradle.org/current/userguide/multi_project_builds.html
9. Gradle — Java plugin: https://docs.gradle.org/current/userguide/java_plugin.html
10. Gradle — IDE metadata deprecations: https://docs.gradle.org/current/userguide/upgrading_version_9.html
11. IntelliJ IDEA — Gradle integration: https://www.jetbrains.com/help/idea/gradle.html
12. IntelliJ IDEA — Gradle settings: https://www.jetbrains.com/help/idea/gradle-settings.html
13. IntelliJ IDEA — Gradle projects: https://www.jetbrains.com/help/idea/work-with-gradle-projects.html
14. Eclipse Buildship: https://projects.eclipse.org/projects/tools.buildship
15. Eclipse — Importing existing projects: https://help.eclipse.org/latest/topic/org.eclipse.platform.doc.user/tasks/tasks-importproject.htm
16. VS Code — Java build tools: https://code.visualstudio.com/docs/java/java-build
17. VS Code — Java project management: https://code.visualstudio.com/docs/java/java-project
18. VS Code Gradle for Java extension: https://marketplace.visualstudio.com/items?itemName=vscjava.vscode-gradle
19. VS Code Gradle extension source: https://github.com/microsoft/vscode-gradle

**Về phiên bản:** Tài liệu Gradle /current/ và menu IDE có thể thay đổi. Áp dụng theo Gradle Wrapper, Java toolchain và IDE/extension versions thực tế. Gradle 9.x và deprecations của metadata-generation tasks là những điểm quan trọng nhưng không có nghĩa IntelliJ hoặc Eclipse mất khả năng import Gradle.

**Kết luận:** Một project Gradle được import đúng là project mà **IDE hiển thị modules, dependencies, source sets và tasks theo Gradle model**, dùng Wrapper/JDK hợp lệ, có thể Sync/Refresh khi build scripts đổi, và tái hiện Java/JUnit behavior bằng CLI/CI.
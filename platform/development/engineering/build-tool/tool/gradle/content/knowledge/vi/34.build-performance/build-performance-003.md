# Configuration avoidance và loại bỏ công việc không cần thiết trong Gradle

## 1. Mục tiêu: build nhanh bằng cách không làm việc không cần làm

Một Gradle build có hàng trăm tasks không nhất thiết phải chậm. Vấn đề thường không nằm ở **số task được định nghĩa**, mà ở số task bị **tạo và cấu hình quá sớm**, việc **resolve dependencies** hoặc chạy I/O không cần thiết, và các **task actions** đáng lẽ được bỏ qua nhờ up-to-date checking.

Ví dụ: developer chỉ muốn xem `./gradlew help`, nhưng build script lại:

- Tạo và cấu hình 300 custom tasks ngay lập tức.
- Quét mọi thư mục source của tất cả modules.
- Resolve toàn bộ `runtimeClasspath` để in tên JARs.
- Đọc một JSON config lớn dù không có task nào cần nó.
- Gọi HTTP để tra version mới, kể cả khi chỉ chạy `clean`.
- Tự cấu hình mọi `Test`, `Javadoc`, `Jar` thông qua API eager.
- Chạy cả integration tests, packaging và publishing khi developer chỉ muốn compile.

Đó là **công việc không cần thiết** mà Gradle có cơ chế tránh được, nếu build logic được thiết kế đúng.

Bài học này tập trung hai lớp:

1. **Configuration avoidance:** không hiện thực hóa/cấu hình một task cho đến khi task đó thực sự cần thiết để lập execution graph.
2. **Work avoidance:** không thực thi việc không cần thiết nhờ task graph chính xác, inputs/outputs, `UP-TO-DATE`, `NO-SOURCE`, build cache, selective task invocation và configuration cache.

Bài sẽ giải thích các API như `tasks.register`, `TaskProvider`, `tasks.named`, `configureEach`; cách tránh `tasks.create`, `getByName` và `all { }`; đồng thời đưa ra **demo độc lập Gradle Kotlin DSL + Java 17** và cách đọc logs để kiểm chứng.

Sau khi học, bạn có thể:

- Phân biệt **task registration**, **task realization/configuration** và **task execution**.
- Giải thích tại sao `register` chưa đủ nếu code khác gọi `get()` hoặc `all { }`.
- Dùng `TaskProvider` để nối task dependencies và output Providers mà không ép cấu hình sớm.
- Cấu hình tasks hiện có bằng `named`/`configureEach` theo cách lazy.
- Tránh resolve dependencies, đọc files hoặc gọi HTTP trong configuration phase.
- Phân biệt `onlyIf`, `enabled=false`, `NO-SOURCE` và việc không đưa task vào task graph.
- Thiết kế inputs/outputs để Gradle tự bỏ qua công việc lặp lại.
- Đo hiệu năng đúng: tách configuration time, task execution time, up-to-date/cache outcomes.
- Nêu khi nào configuration cache, build cache, configuration-on-demand, compile avoidance và parallelism hữu ích.
- Kiểm bằng một baseline và thay đúng một biến, thay vì tuyên bố nhanh hơn bằng cảm giác.

**Nguyên tắc:** đừng tối ưu bằng cách “tắt đại tasks quan trọng”; hãy tạo **task graph đúng, values lazy và inputs/outputs đầy đủ**, để Gradle có thể bỏ qua công việc mà **không bỏ mất kết quả cần có**.

## 2. Ba pha Gradle và bốn vị trí có thể tiết kiệm công việc

Gradle có ba pha chính:

```text
Initialization
    |
    v
Settings / project structure
    |
    v
Configuration phase
    |--- Apply plugins
    |--- Evaluate build scripts
    |--- Register tasks and lazy configuration actions
    |--- Realize tasks needed for the requested task graph
    |
    v
Execution phase
    |--- Decide task outcomes
    |--- Perform task actions only when necessary
    |--- Reuse or restore prior outputs if allowed
    |
    v
Results / artifacts / reports
```

Trong một build lớn, có **ít nhất bốn câu hỏi hiệu năng độc lập**:

| Câu hỏi | Cơ chế phù hợp | Một dấu hiệu |
| --- | --- | --- |
| Có cần **cấu hình task này** không? | Configuration avoidance | Task không liên quan không bị realize |
| Có cần **cấu hình build này lại** không? | Configuration cache | Reused configuration cache entry |
| Task đã được chọn có cần **thực thi action** không? | Up-to-date checking, `NO-SOURCE`, `onlyIf` | `UP-TO-DATE`, `NO-SOURCE`, `SKIPPED` |
| Output task có thể lấy từ kết quả trước không? | Build cache | `FROM-CACHE` |

**Không đánh đồng:**

- Một task được **registered** chưa chắc đã được **realized**.
- Một task được **realized/configured** chưa chắc **executed**.
- Một task **không executed** có thể do `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE` hoặc `SKIPPED` — các ý nghĩa khác nhau.
- Một task **không có trong graph** không phải là task `SKIPPED`. Nó đơn giản không được yêu cầu, hoặc không có dependency nào kéo nó vào graph.
- Configuration cache tái sử dụng **configured graph**, không phải binary artifacts của build cache.
- `--parallel` có thể giảm elapsed time nhưng không phải cơ chế **loại bỏ việc**, vì cùng số lượng work có thể chạy đồng thời.

Một build tối ưu vẫn phải đúng thứ tự và hợp đồng của tasks: bỏ `test` để nhanh có thể giảm thời gian, nhưng không phải tối ưu đúng nếu gate của CI yêu cầu tests.

## 3. Đăng ký task khác với tạo task

Với Gradle Kotlin DSL, so sánh:

```kotlin
// Eager: task được tạo/cấu hình ngay khi DSL đến dòng này.
tasks.create("generateDocs") {
    group = "documentation"
    // Configuration action chạy ngay trong configuration phase.
}
```

```kotlin
// Lazy: tạo registration và cấu hình sau khi task cần được realized.
val docsTask = tasks.register("generateDocs") {
    group = "documentation"
    // Configuration action chỉ chạy khi Gradle cần task instance.
}
```

`tasks.register` trả về **`TaskProvider<Task>`**, chứ chưa trả về instance `Task`. Gradle biết task name/type và có thể tham chiếu provider trong task relationships nhưng chưa phải trả toàn bộ chi phí instantiate/configure.

**Quan sát quan trọng:** lệnh `./gradlew help` thường không cần custom `generateDocs`. Nếu task được register lazily và không có code nào ép realize, configuration action của nó không chạy. Nhưng nếu dùng `create`, action sẽ chạy dù chỉ gọi `help`.

Task **được register** không có nghĩa code trong `tasks.register("...") { ... }` không bao giờ chạy. Nó sẽ chạy khi task cần cho graph, khi một API eager yêu cầu instance, hoặc khi task bị realized bởi logic khác.

### 3.1. Registration, realization, execution là ba sự kiện

```text
BUILD SCRIPT:
tasks.register("generateDocs") { configAction }
       |
       | registration, không gọi configAction ngay
       v
TaskProvider<...>
       |
       +--- ./gradlew help ----------> chưa cần task instance
       |
       +--- ./gradlew generateDocs --> realize task, chạy configAction
                                           |
                                           v
                                      execution graph
                                           |
                                           v
                                      doLast / @TaskAction
```

Với một task có action và output, sau khi đã được realized vẫn có thể `UP-TO-DATE` và **không thực thi** action ở lần 2. Log `CONFIGURE ...` nằm ở configuration phase; log `EXECUTE ...` nằm trong task action. Bài demo sẽ in hai loại log khác nhau để thấy ranh giới này.

### 3.2. Gradle có thể realize task ngay cả khi cuối cùng task không làm việc

Task được kéo vào graph (do CLI gọi trực tiếp hoặc dependency) thường phải được realize/configure để Gradle biết inputs, outputs, predicates và task relationships. Sau đó task có thể kết thúc `NO-SOURCE` hoặc `UP-TO-DATE`.

Vì vậy **configuration avoidance không có nghĩa các tasks trong graph không bao giờ cần configuration**. Nó giúp tránh chi phí cho **tasks không cần trong invocation hiện tại**.

## 4. Bảng API: lazy nên dùng và eager cần tránh

| Mục đích | API lazy nên dùng | API eager hoặc dễ làm hỏng avoidance |
| --- | --- | --- |
| Thêm task | `tasks.register("name")` | `tasks.create("name")`, task shorthand |
| Thêm task với type | `tasks.register<MyTask>("name")` | `tasks.create("name", MyTask::class.java)` |
| Cấu hình task theo tên | `tasks.named("test").configure { ... }` | `tasks.getByName("test").apply { ... }` |
| Cấu hình mọi task của một type | `tasks.withType<Test>().configureEach { ... }` | `tasks.withType<Test>().all { ... }` |
| Cấu hình mọi task khi cần | `tasks.configureEach { ... }` | `tasks.all { ... }` |
| Tham chiếu task trong graph | `TaskProvider` | `tasks.named("x").get()` trong configuration |
| Nối outputs giữa tasks | `taskProvider.flatMap { it.outputFile }` | Hardcode file path rồi gọi `taskProvider.get()` |
| Tạo derived value | `provider.map { ... }` | `provider.get()` ngay trong `apply()`/build script |
| Cấu hình configuration theo tên | `configurations.named("runtimeClasspath")` | `configurations.getByName("runtimeClasspath")` khi không cần instance |
| Cấu hình nhiều configurations | `configurations.configureEach { ... }` | `configurations.all { ... }` |

**Lưu ý 1:** `tasks.withType<Test>()` là **một collection view lazy**, nhưng gọi `all { }` hoặc overload `withType(Test::class.java) { ... }` dạng eager có thể realize các tasks hiện có. Cách rõ ràng là `withType<Test>().configureEach { ... }`.

**Lưu ý 2:** `TaskProvider.get()` không bị cấm về cú pháp; nó là API hợp lệ khi thật sự cần instance. Nhưng trong **configuration phase**, gọi nó không cần thiết là nguyên nhân phá lazy task configuration.

**Lưu ý 3:** các versions/plugins cũ có thể còn APIs không hỗ trợ avoidance. Khi sửa shared build logic nên ưu tiên migrate từng plugin/task có bằng chứng hiệu năng, không viết lại mọi thứ mà thiếu tests.

## 5. Demo độc lập Java 17 + Gradle Kotlin DSL

Ta xây một Gradle project có:

- Một task tự tạo `generateMessage`, sử dụng managed properties, khai báo inputs/outputs.
- Một task `messageZip` chỉ cần khi packaging, lấy output của `generateMessage` theo `TaskProvider`.
- Một Java 17 source file và `runApp` để kiểm compilation/JavaExec.
- Logs `CONFIGURE ...` và `EXECUTE ...` giúp xác định task bị realized hay thực thi.
- Không có third-party dependencies, không cần Maven Central.

**Yêu cầu:** JDK 17 và một Gradle Wrapper hỗ trợ Java 17. Nếu bắt đầu từ thư mục trắng và chưa có Wrapper, cần cài Gradle tạm để tạo `gradle wrapper`, rồi dùng Wrapper để lặp lại kết quả. Không coi việc vắng Gradle Wrapper là lỗi của configuration avoidance.

### 5.1. Cấu trúc thư mục

```text
avoidance-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── data/
│   └── message.txt
├── src/main/java/demo/Main.java
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
```

Bắt đầu với **một workspace riêng** để không bị IDE, CI, formatting tools hoặc process khác sửa file khi thực nghiệm.

### 5.2. `settings.gradle.kts`

```kotlin
rootProject.name = "avoidance-lab"
```

### 5.3. File `data/message.txt`

```text
hello gradle
```

File có thể kết thúc bằng LF hoặc CRLF. Task trong demo dùng `trimEnd('\r', '\n')` để kiểm soát output text, nhưng **file bytes khác vẫn có thể làm task invalidated**. Đó là điều đúng vì Gradle fingerprint file input bytes.

### 5.4. File `src/main/java/demo/Main.java`

```java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("JAVA_17_OK");
    }
}
```

Có thể compile và chạy riêng bằng Java 17 (sau khi tạo output directory):

Linux/macOS:

```bash
mkdir -p build/manual-classes
javac --release 17 -d build/manual-classes src/main/java/demo/Main.java
java -cp build/manual-classes demo.Main
```

PowerShell:

```powershell
New-Item -ItemType Directory -Force build\manual-classes | Out-Null
javac --release 17 -d build\manual-classes src\main\java\demo\Main.java
java -cp build\manual-classes demo.Main
```

Stdout **chính xác của chương trình Java**:

```text
JAVA_17_OK
```

Lệnh `javac/java` chứng minh Java source độc lập hợp lệ; nó **không** thay thế kiểm việc Gradle tasks được cấu hình lazy.

### 5.5. Toàn bộ `build.gradle.kts`

```kotlin
import java.nio.charset.StandardCharsets
import java.util.Locale

import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.api.tasks.JavaExec
import org.gradle.api.tasks.bundling.Zip

plugins {
    java
}

group = "org.example"
version = "1.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

// Class ở build script dành cho demo. Có thể chuyển sang build-logic
// nếu dùng chung nhiều modules.
abstract class GenerateMessageTask : DefaultTask() {

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val inputText: RegularFileProperty

    @get:Input
    abstract val label: Property<String>

    @get:OutputFile
    abstract val outputText: RegularFileProperty

    @TaskAction
    fun generate() {
        val source = inputText.get().asFile
            .readText(StandardCharsets.UTF_8)
            .trimEnd('\r', '\n')

        val result =
            label.get() + ":" + source.uppercase(Locale.ROOT) + "\n"

        val file = outputText.get().asFile
        file.parentFile.mkdirs()
        file.writeText(result, StandardCharsets.UTF_8)

        logger.lifecycle("EXECUTE generateMessage")
    }
}

// 1) Task cần khi developer yêu cầu tạo file text.
val generated = tasks.register<GenerateMessageTask>("generateMessage") {
    group = "build"
    description = "Generate one reproducible text file"

    logger.lifecycle("CONFIGURE generateMessage")

    inputText.set(layout.projectDirectory.file("data/message.txt"))
    label.convention(
        providers.gradleProperty("messageLabel").orElse("MESSAGE")
    )
    outputText.set(
        layout.buildDirectory.file("generated/message.txt")
    )
}

// 2) Task chỉ dành cho packaging; không thêm vào build lifecycle.
tasks.register<Zip>("messageZip") {
    group = "distribution"
    description = "Package generated text only when requested"

    logger.lifecycle("CONFIGURE messageZip")

    archiveBaseName.set("messages")
    archiveVersion.set("1.0")
    destinationDirectory.set(layout.buildDirectory.dir("bundles"))

    // Provider nối nguồn output và producer task lazy.
    from(generated.flatMap { it.outputText }) {
        into("payload")
    }
}

// 3) JavaExec chỉ dành cho yêu cầu chạy Java app.
tasks.register<JavaExec>("runApp") {
    group = "application"
    description = "Run Java 17 application"

    logger.lifecycle("CONFIGURE runApp")

    mainClass.set("demo.Main")
    classpath = sourceSets.main.get().runtimeClasspath
}

// 4) Cấu hình task JavaCompile theo type mà không realize toàn bộ.
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
```

**Giải thích những chi tiết có ảnh hưởng hiệu năng:**

1. `plugins { java }` đăng ký nhiều Java-related tasks, nhưng không có lý do tự ép tất cả tasks được realized khi chỉ gọi `help`.
2. `GenerateMessageTask` dùng `@InputFile`, `@Input` và `@OutputFile`, để Gradle theo dõi trạng thái. Đánh dấu `@InputFile` không tự làm task cacheable; nó hỗ trợ **up-to-date checking**, và build cache đòi thêm khả năng cacheability.
3. `PathSensitivity.NONE` hợp lý vì output không chứa source filename/path, chỉ đọc nội dung.
4. `label.convention(providers.gradleProperty(...).orElse("MESSAGE"))` tạo lazy relationship; không gọi `get()` trong configuration block.
5. `logger.lifecycle("CONFIGURE ...")` nằm trong configuration action của task. Với `tasks.register`, block này **không nhất thiết chạy** trong invocation không cần task.
6. `logger.lifecycle("EXECUTE ...")` nằm trong `@TaskAction` và chỉ xuất hiện nếu action thực thi.
7. `generated` là `TaskProvider<GenerateMessageTask>`; biến tham chiếu này **không tự là task instance**.
8. `generated.flatMap { it.outputText }` mô tả output provider của producer. `Zip.from(...)` dùng nó làm input file; Gradle có thể suy ra task dependency.
9. `messageZip` **không** được nối vào `assemble` hoặc `build` ở baseline. Developer cần gọi `messageZip` trực tiếp; nhờ vậy `./gradlew compileJava` không phải đóng gói custom ZIP.
10. `runApp` chỉ được realize khi bạn gọi nó (hoặc có dependency thật tới nó). Nó sử dụng `sourceSets.main.runtimeClasspath`, không resolve một external dependency khi `help`.
11. `withType<JavaCompile>().configureEach` cài encoding khi JavaCompile task được realized, không ép mọi JavaCompile task configure ngay.
12. `get()` trong `@TaskAction` là hợp lý vì đây là thời điểm action cần giá trị thực; `get()` tại build configuration để quyết định tasks ngẫu nhiên có thể phá lazy wiring.
13. Plugin Java đã có `classes`, `jar`, `build`, `check`, `clean`; không cần tự viết lại lifecycle tasks.
14. Không có `println`, file reads hoặc network calls ở root của script trừ các cấu hình Gradle ngắn.

**Quan trọng:** Kotlin DSL có thể tự import các Gradle API phổ biến, nhưng trong ví dụ vẫn ghi imports tường minh cho task annotations/Zip/JavaExec để giảm phụ thuộc vào implicit imports. Không cần thêm `mavenCentral()` vì demo dùng Gradle core plugin và JDK.

## 6. Thực nghiệm 1: `help` không cần custom tasks

Trong thư mục `avoidance-lab`, Linux/macOS:

```bash
./gradlew help --no-configuration-cache --console=plain
```

PowerShell:

```powershell
.\gradlew.bat help --no-configuration-cache --console=plain
```

**Kỳ vọng với baseline demo không có plugin khác ép task realization:**

- Có task `:help` được thực thi hoặc nhận outcome phù hợp.
- **Không xuất hiện** `CONFIGURE generateMessage`.
- **Không xuất hiện** `CONFIGURE messageZip`.
- **Không xuất hiện** `CONFIGURE runApp`.
- **Không xuất hiện** `EXECUTE generateMessage`.
- Không xuất hiện `build/generated/message.txt` **mới được tạo bởi task**.
- Không có `messages-1.0.zip` mới được tạo bởi task.

Nếu file output cũ còn trong `build/`, đừng coi nó là bằng chứng `help` vừa tạo file. Dùng một sandbox sạch hoặc quan sát timestamps/task outcomes.

**Tại sao dùng `--no-configuration-cache`?** Nếu configuration cache được bật, Gradle có thể bỏ qua hẳn configuration phase trong lượt sau. Để nghiên cứu **task configuration avoidance**, ta tắt configuration cache trước, tránh nhập nhằng lý do không thấy log configuration.

**Không dùng `./gradlew tasks --all` làm phép đo thay thế `help`.** Task inventory/inspection có thể cần realize hoặc cấu hình thêm tasks để hiển thị chi tiết; đó là một yêu cầu khác. Mục tiêu là quan sát invocation `help` không cần các task của ứng dụng.

## 7. Thực nghiệm 2: chỉ yêu cầu `generateMessage`

Linux/macOS:

```bash
./gradlew generateMessage --no-configuration-cache \
  --no-build-cache --console=plain
cat build/generated/message.txt
```

PowerShell:

```powershell
.\gradlew.bat generateMessage --no-configuration-cache --no-build-cache --console=plain
Get-Content build\generated\message.txt
```

Các dòng được kỳ vọng có trong Gradle logs:

```text
CONFIGURE generateMessage
> Task :generateMessage
EXECUTE generateMessage
```

Đây là **trích đoạn ý nghĩa**, không cam kết thứ tự của các messages không liên quan, không phải toàn bộ console output. Đặc biệt không nên đòi task `compileJava`, `runApp` hoặc `messageZip` chạy cho yêu cầu này.

Nội dung **chính xác** của `build/generated/message.txt` (một dòng có newline cuối):

```text
MESSAGE:HELLO GRADLE
```

**Những điều quan sát được:**

- `generateMessage` đã được realize/configure vì request trực tiếp.
- Task action đọc đúng file input và property label.
- Gradle tạo một file output đã được khai báo.
- Không cần resolve Java dependencies hay compile Main.java.
- `messageZip` chưa cần thiết nên không bị cấu hình hoặc thực thi.
- Task config được giữ ngắn, còn file I/O thực sự ở `@TaskAction`.

### 7.1. Chạy lần thứ hai không đổi

```bash
./gradlew generateMessage --no-configuration-cache \
  --no-build-cache --console=plain
```

Kỳ vọng:

```text
CONFIGURE generateMessage
> Task :generateMessage UP-TO-DATE
```

Ở lần thứ hai, **configuration action vẫn chạy** vì ta chủ động tắt configuration cache và `generateMessage` là task được request. Nhưng **task action không chạy**, nên **không có** `EXECUTE generateMessage`. Đây là hai loại công việc khác nhau:

- Configuration avoidance bỏ configuration của những task **không liên quan**.
- Up-to-date checking bỏ execution action của task **có trong graph** nhưng không cần xử lý lại.

Nếu task không `UP-TO-DATE`, xem `--info` để tìm lý do: input đổi, output mất, task implementation thay đổi, việc write bị IDE can thiệp hay không có previous execution history.

### 7.2. Thay đúng một input value

```bash
./gradlew generateMessage -PmessageLabel=NOTE \
  --no-configuration-cache --no-build-cache --console=plain
cat build/generated/message.txt
```

File phải là:

```text
NOTE:HELLO GRADLE
```

Đây là một controlled change của `@Input`, không cần sửa source file. Task action cần chạy lại khi label đổi. Nếu tiếp tục chạy **cùng** `-PmessageLabel=NOTE` và không thay files, task lại thường `UP-TO-DATE`.

Bỏ flag `-PmessageLabel` sẽ quay về default `MESSAGE` và có thể kích hoạt task lại, vì input value thay đổi.

## 8. Thực nghiệm 3: `messageZip` chỉ xuất hiện khi cần

Linux/macOS:

```bash
./gradlew messageZip --no-configuration-cache \
  --no-build-cache --console=plain
```

PowerShell:

```powershell
.\gradlew.bat messageZip --no-configuration-cache --no-build-cache --console=plain
```

Vì `messageZip` khai báo:

```kotlin
from(generated.flatMap { it.outputText }) {
    into("payload")
}
```

Gradle hiểu file source của Zip đến từ task `generateMessage`. Khi `messageZip` được chọn, task producer có thể phải được realize để tạo dependency graph, và output phải có trước lúc Zip đóng gói.

Kết quả ở một workspace với input đã ổn định:

- `CONFIGURE messageZip` xuất hiện.
- `CONFIGURE generateMessage` cũng có thể xuất hiện do producer cần cho graph.
- `generateMessage` thường `UP-TO-DATE` nếu output đã hợp lệ.
- `messageZip` tạo `build/bundles/messages-1.0.zip` nếu chưa có hoặc contents/metadata đổi.
- `runApp` không cần thiết.
- Source file bên trong Zip: `payload/message.txt`.

Kiểm ZIP contents bằng một công cụ phù hợp:

```bash
unzip -l build/bundles/messages-1.0.zip
```

Hoặc nếu không có `unzip` nhưng có JDK:

```bash
jar tf build/bundles/messages-1.0.zip
```

**Kỳ vọng:** archive chứa entry `payload/message.txt`. Tên file archive theo `archiveBaseName=messages` và `archiveVersion=1.0`. `Zip` chỉ có nội dung được cấu hình; đây không phải một Application distribution có start scripts/runtime JARs.

### 8.1. Không ép producer bằng `get()`

Tránh:

```kotlin
val generatedTask = tasks.named<GenerateMessageTask>("generateMessage").get()

tasks.register<Zip>("messageZip") {
    from(generatedTask.outputText)
}
```

`get()` ở top-level buộc producer task được realized ngay cả khi chỉ chạy `help`. Lời giải đúng là **giữ `TaskProvider`**, lấy provider output qua `flatMap` và để Gradle suy dependency.

### 8.2. Không hardcode output path nếu có Provider

```kotlin
tasks.register<Zip>("messageZip") {
    from("build/generated/message.txt")
}
```

Đoạn này có thể tìm được file nếu task đã chạy, nhưng không mang thông tin **task nào tạo file**; task `messageZip` có thể đọc file cũ, thiếu hoặc báo implicit dependency validation. Dùng Provider gắn với producer output là đúng hơn và tránh hỏng khi build directory/output name thay đổi.

## 9. Thực nghiệm 4: Java code chạy mà không đóng ZIP

`src/main/java/demo/Main.java` đã được tạo. Chạy:

Linux/macOS:

```bash
./gradlew runApp --no-configuration-cache \
  --no-build-cache --console=plain
```

PowerShell:

```powershell
.\gradlew.bat runApp --no-configuration-cache --no-build-cache --console=plain
```

Expected program stdout:

```text
JAVA_17_OK
```

`runApp` là `JavaExec` task, sử dụng Java runtimeClasspath. Gradle có thể cần `compileJava` và `processResources`/`classes` outputs, nhưng **không** cần `generateMessage` hay `messageZip`.

Đây là minh họa **loại bỏ tasks không liên quan khỏi execution graph**: không tạo custom report/ZIP nếu Java application không phụ thuộc chúng.

**Chỉ gọi `./gradlew compileJava`** khi muốn compile. Gọi `./gradlew build` khi muốn cả assemble và verification. Không dùng một lifecycle task rộng cho mọi vòng lặp local nếu mục tiêu hiện tại chỉ là chạy một unit test hoặc compile một module.

## 10. Khi muốn cải tiến eager task cũ: kiểm một thay đổi một lần

Một task cũ có thể viết:

```kotlin
// CÁCH CŨ: demo phản ví dụ, không đặt cạnh tasks.register cùng tên.
tasks.create("legacyReport") {
    logger.lifecycle("CONFIGURE legacyReport")
    doLast {
        logger.lifecycle("EXECUTE legacyReport")
    }
}
```

Với `tasks.create`, cấu hình task chạy khi build script được evaluate. Vì vậy `./gradlew help --no-configuration-cache` có thể in:

```text
CONFIGURE legacyReport
```

nhưng không in `EXECUTE legacyReport`, vì task không được yêu cầu.

**Sửa đúng** bằng `tasks.register`:

```kotlin
tasks.register("legacyReport") {
    logger.lifecycle("CONFIGURE legacyReport")
    doLast {
        logger.lifecycle("EXECUTE legacyReport")
    }
}
```

Sau khi sửa, `./gradlew help --no-configuration-cache` không cần realize `legacyReport` nên thường không in cấu hình đó.

**Tính chính xác của phép thử:** dùng hai phiên bản build script **ở hai lượt riêng**, không để cả hai khai báo task cùng tên. Cần tắt configuration cache để logs phản ánh configuration hiện tại và kiểm task không bị code khác gọi `getByName` hay `all { }`.

### 10.1. Vì sao đổi `create` sang `register` có thể chưa đủ?

Giả sử project đã chuyển sang `register` nhưng vẫn có:

```kotlin
tasks.all {
    logger.lifecycle("CONFIGURE TASK " + name)
}
```

`tasks.all { ... }` là eager collection configuration action: nó có thể làm nhiều registered tasks được realized, làm mất lợi ích của `register`. Hãy chuyển sang:

```kotlin
tasks.configureEach {
    logger.lifecycle("CONFIGURE TASK " + name)
}
```

**Nhưng đừng đặt log này vào production**: nó chỉ là instrumentation trong sandbox; khi cần đo hệ thống lớn hãy dùng build profiling/scan hoặc tracing phù hợp.

## 11. `tasks.named`: cấu hình một task hiện có mà không lấy instance ngay

Với Java plugin, task `jar` đã được đăng ký. Một custom convention nên cấu hình qua:

```kotlin
import org.gradle.jvm.tasks.Jar

tasks.named<Jar>("jar") {
    archiveClassifier.set("plain")
}
```

Đây là một **mẫu riêng**, không nằm trong baseline demo vì đổi classifier sẽ đổi tên JAR artifact. Cách gọi `named<Jar>` trả provider và đăng ký configuration action lazy.

Không nên:

```kotlin
tasks.getByName("jar").apply {
    // Tìm task instance ngay tại configuration time.
}
```

Vấn đề của `getByName` là **forcing task realization**, kể cả khi người dùng chỉ chạy `help`. Còn `tasks.named("jar").configure { ... }` defer configuration action cho đến khi Jar task cần được realized.

### 11.1. Có thể cấu hình theo TaskProvider ngay khi tạo

```kotlin
val report = tasks.register("report") {
    group = "reporting"
}
report.configure {
    description = "Prepare report if requested"
}
```

`report.configure { ... }` vẫn là lazy task configuration. Nhưng việc tạo nhiều configuration actions rải rác có thể khiến code khó theo dõi; ưu tiên đặt config cạnh task registration khi hợp lý.

### 11.2. `tasks.withType<JavaCompile>().configureEach`

Một convention phổ biến:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
```

`configureEach` đăng ký action chỉ chạy cho các task JavaCompile **được realized**, trong khi:

```kotlin
tasks.withType<JavaCompile>().all {
    options.encoding = "UTF-8"
}
```

là eager và có thể khiến nhiều JavaCompile tasks hiện có được created/configured. Trong multi-project với hàng trăm tests/source sets, khác biệt có thể lớn.

### 11.3. Đừng hiểu nhầm việc gọi `withType` một mình

`tasks.withType<JavaCompile>()` tạo collection view; bản thân nó không tương đương `all { }`. Vấn đề xuất hiện khi **duyệt/eagerly query** hoặc gọi callback có semantics eager. Đọc chính xác API Gradle thay vì suy rằng chữ `withType` tự động chậm.

## 12. `TaskProvider` và quan hệ task: không phải quan hệ nào cũng kéo việc

Gradle có nhiều cách mô tả quan hệ:

| Quan hệ | Ý nghĩa | Có đưa task kia vào graph không? |
| --- | --- | --- |
| `dependsOn(other)` | Task này cần task kia hoàn tất trước | **Có**, khi task này được yêu cầu |
| `finalizedBy(other)` | Chạy finalizer sau task chính | **Có**, nếu task chính có trong graph theo quy tắc Gradle |
| `mustRunAfter(other)` | Nếu cả hai có trong graph, bắt buộc thứ tự | **Không tự thêm task kia** |
| `shouldRunAfter(other)` | Nếu cả hai có trong graph, ưu tiên thứ tự | **Không tự thêm task kia** |
| Provider-derived file dependency | Consumer cần file output của producer | **Có thể tự suy ra producer task** |
| `onlyIf { false }` | Bỏ qua action của task được chọn | **Không loại task khỏi cấu hình/graph** |

**Một nhầm lẫn đắt giá:** thêm:

```kotlin
tasks.named("compileJava") {
    dependsOn("generateAllReports")
}
```

chỉ để bảo đảm báo cáo luôn mới. Điều này khiến mọi lần compile kéo thêm reporting, có thể rất chậm và không đúng dependency của Java compilation. Nếu report không phải compile input, đừng nối vào `compileJava`.

Ngược lại, khi một task thật sự **tiêu thụ output** của task khác, cần dependency/Provider đúng; bỏ `dependsOn` để “tối ưu” có thể khiến output stale, missing file hoặc race condition.

### 12.1. Chọn task graph theo workflow

| Công việc developer muốn | Task phù hợp | Thường không cần |
| --- | --- | --- |
| Kiểm Java compile | `compileJava` | `test`, `distZip`, integration tests |
| Chạy unit tests | `test` | Maven publish hoặc deployment |
| Chạy một test class | `test --tests "...Test"` | Toàn bộ test suite khác |
| Kiểm chất lượng trước merge | `check` | Publish artifact |
| Tạo JAR | `jar` hoặc `assemble` | Remote upload |
| Tạo ZIP theo nhu cầu | `messageZip` | `runApp` |
| Publish Maven module | `publish...To...Repository` | Tasks unrelated, nếu publishing không yêu cầu chúng |
| Đọc help | `help` | Compile, package, tests, network calls |

Không coi `-x test` là giải pháp hiệu năng vĩnh viễn cho `build`. Nó có thể bỏ verification bắt buộc. Hãy tạo workflow/lifecycle tasks riêng có mục đích đúng hoặc gọi trực tiếp task cần thiết.

## 13. `onlyIf`, `enabled` và `NO-SOURCE`: bỏ qua action, không phải bỏ cấu hình

Một cách bỏ qua task action theo điều kiện là:

```kotlin
val diagnosticsRequested =
    providers.gradleProperty("runDiagnostics")
        .map { it.equals("true", ignoreCase = true) }
        .orElse(false)

tasks.register("diagnostics") {
    group = "verification"

    onlyIf("runDiagnostics=true was supplied") {
        diagnosticsRequested.get()
    }

    doLast {
        logger.lifecycle("DIAGNOSTICS EXECUTED")
    }
}
```

Đây là **mẫu bổ sung** có thể dùng riêng trong build script. Khi gọi:

```bash
./gradlew diagnostics --no-configuration-cache --console=plain
```

Task có thể báo:

```text
> Task :diagnostics SKIPPED
```

Khi gọi:

```bash
./gradlew diagnostics -PrunDiagnostics=true \
  --no-configuration-cache --console=plain
```

task action được phép chạy và in `DIAGNOSTICS EXECUTED`.

**Đừng hiểu sai:** `onlyIf` được evaluate ngay trước execution. Gradle vẫn phải biết task properties/dependencies và thường phải realize/configure task được chọn; dependencies cần thiết của task có thể đã chạy trước khi predicate của task được kiểm. Nếu mục tiêu là **không đưa một task đắt tiền vào graph**, cân nhắc conditional registration/lifecycle wiring thích hợp, thay vì thêm `onlyIf` ở cuối đường dây.

### 13.1. `enabled=false` có những giới hạn tương tự

`tasks.named("diagnostics") { enabled = false }` khiến action không chạy, thường outcome `SKIPPED`. Nhưng task vẫn tồn tại và có thể được realize. Nó cũng có thể gây downstream failures nếu task tạo output được consumer bắt buộc sử dụng. Không dùng `enabled=false` để xóa một producer khỏi graph khi output vẫn được cần.

### 13.2. `NO-SOURCE` là cơ chế khác

Với Java plugin, nếu source set không có Java file nào, `compileJava` có thể kết thúc `NO-SOURCE`. Gradle không compile vì không có sources. Đây là skip theo source inputs, không phải do `tasks.register` và cũng không có nghĩa một project với Java sources sẽ luôn được compile nhanh.

Custom tasks có `@SkipWhenEmpty` trên file inputs có thể dùng semantics tương tự khi phù hợp. Tuy nhiên nếu task cần xóa stale outputs khi input set trở nên rỗng, hãy kiểm contract/Gradle behavior thay vì áp `@SkipWhenEmpty` mù.

### 13.3. Trường hợp nên điều kiện hóa registration

Nếu feature chỉ tồn tại cho một số modules:

```kotlin
val needsApiDocs =
    providers.gradleProperty("publicApi").orNull == "true"

if (needsApiDocs) {
    tasks.register("generateApiDocs") {
        group = "documentation"
        doLast {
            logger.lifecycle("Generate API docs for this module")
        }
    }
}
```

Đây chỉ là **mẫu API quyết định registration tại configuration phase**: đọc một Gradle property nhẹ là một phép quyết định có chủ đích, không phải cùng vấn đề với đọc file lớn/network hay realize hundreds of tasks. Nhưng việc task có tồn tại hay không thay đổi theo property, nên CLI/CI phải biết contract rõ. Nếu developer cần `generateApiDocs` luôn là task có tên ổn định, có thể register luôn và dùng `onlyIf`, hoặc thiết kế convention plugin với typed extension.

**Không dùng conditional registration để che một mandatory check**: nếu CI quên `-PpublicApi=true`, task biến mất và release gate có thể bị bỏ qua. Chính sách bắt buộc phải có nguồn sự thật được quản lý.

## 14. Lazy value resolution: `Provider` và `Property`

Task configuration avoidance giải quyết task objects. Nhưng **giá trị đầu vào của task** cũng có thể tốn công để tính. Gradle Provider API giúp trì hoãn giá trị:

```kotlin
val prefixProvider =
    providers.gradleProperty("messageLabel").orElse("MESSAGE")

tasks.register<GenerateMessageTask>("generateMessage") {
    label.convention(prefixProvider)
}
```

`Property<T>` vừa là configurable holder vừa là Provider. Nó có thể nhận:

- `convention(default)`: default khi không override.
- `set(value)`: explicit value.
- `set(provider)`: giữ lazy relation.
- `map { ... }`: tạo derived Provider.
- `flatMap { ... }`: nối Provider trả về Provider.
- `orElse(...)`: fallback.
- `get()`: resolve giá trị ngay thời điểm gọi.

**Anti-pattern:**

```kotlin
val prefixValue =
    providers.gradleProperty("messageLabel")
        .orElse("MESSAGE").get()

tasks.register<GenerateMessageTask>("generateMessage") {
    label.set(prefixValue)
}
```

Không phải lỗi chức năng trong ví dụ prefix rất rẻ, nhưng nó ép đọc property khi build script được evaluate kể cả `help` không cần task. Nếu value tính từ JSON/remote metadata hoặc file system scan thì chi phí tăng rõ ràng. Giữ Provider tới task inputs giúp Gradle tự quyết định thời điểm cần.

### 14.1. Không dùng Provider transformations để gây side effects

`Provider.map { ... }` nên dùng cho biến đổi dữ liệu thuần. Đừng giấu trong đó:

- HTTP requests để upload artifacts.
- Ghi file vào `build/`.
- Chạy `git` hoặc `npm`.
- Xóa/copy thư mục.
- Xuất log chứa secrets.
- Gọi external process không được mô hình hóa như task.

Gradle có thể resolve Provider nhiều lần hoặc ở các thời điểm khác nhau; side effects khiến task graph không đáng tin và phá configuration-cache assumptions. Đặt công việc thực sự vào `@TaskAction`, exec/Worker API hoặc dedicated plugin task đúng loại.

### 14.2. Dùng typed file properties

`RegularFileProperty` và `DirectoryProperty` giúp task nhận paths được Gradle hiểu, và khi derived từ output property của task khác, mang thông tin implicit producer dependency.

```kotlin
// Mẫu đúng khi producer có @OutputFile.
from(generated.flatMap { it.outputText })
```

Không giải phẳng thành raw path string sớm rồi bỏ thông tin producer:

```kotlin
// Anti-pattern: sai khi Gradle cần producer task dependency.
from(generated.get().outputText.get().asFile)
```

Nếu task output thay tên/directory, cách Provider tự thích ứng; cách eager file get có thể ép realization và làm mất tính linh hoạt.

## 15. Bỏ việc nặng khỏi configuration phase

Những thao tác thường gặp gây chậm:

### 15.1. Resolve dependencies ngay khi cấu hình

**Không nên:**

```kotlin
// Anti-pattern: resolution xảy ra khi build script được evaluate.
val runtimeFiles = configurations.getByName("runtimeClasspath").files
println("Found " + runtimeFiles.size + " runtime files")
```

`.files`/`asPath`/`toList()`/`isEmpty()` trên Gradle FileCollection/Configuration có thể buộc resolve dependencies, kích hoạt repositories, metadata reads, downloads và I/O ngay cả khi chỉ chạy `help`.

**Hướng tốt hơn:** task nhận Gradle file collection dưới dạng declared input, rồi thực hiện việc cần thiết khi task thực sự được gọi:

```kotlin
// Ví dụ task in dependency files cho hoạt động chẩn đoán.
// Snippet đơn giản; không phải một cacheable production task.
tasks.register("printRuntimeFiles") {
    val runtimeFiles = configurations.named("runtimeClasspath")

    doLast {
        val files = runtimeFiles.get().files
        files.sortedBy { it.name }.forEach {
            logger.lifecycle(it.name)
        }
    }
}
```

**Giới hạn của snippet:** `doLast` đang truy cập configuration/project model gián tiếp ở execution time; nó là demo debug nhanh, **không** được xem là configuration-cache-compatible production pattern. Với custom task dùng lâu dài, khai báo `ConfigurableFileCollection` làm `@Classpath`/`@InputFiles` trong task type rồi cung cấp `configurations.runtimeClasspath` từ configuration phase; task action chỉ đọc task properties. Cách này vừa lazy vừa có khả năng tương thích tốt hơn.

### 15.2. Quét tất cả files khi apply plugin

```kotlin
// Anti-pattern: chạy ngay tại configuration time.
val documents = fileTree("docs").files
    .filter { it.extension == "md" }
    .map { it.readText() }
```

Một module có hàng nghìn files sẽ chịu phí ngay cả khi chỉ chạy `help`. Nếu task cần documents, chuyển FileTree làm `@InputFiles`, đọc bytes trong `@TaskAction`. Nếu chỉ muốn kiểm tra một manifest nhỏ ảnh hưởng **build configuration**, dùng Provider API và Gradle configuration-input tracking chính xác theo policy, không đọc qua global side effect.

### 15.3. Gọi HTTP, process hoặc database trong `apply()`

Tối ưu tệ:

```kotlin
// Anti-pattern: luôn gọi network trong configuration phase.
val latestVersion = java.net.URL(
    "https://example.invalid/version.json"
).readText()
```

`example.invalid` là domain tài liệu, không phải endpoint chạy thật. Đối với build reproducible, pin versions và dependency management thay vì tra “latest” trên mỗi invocation. Nếu thật sự cần download external metadata, dùng task riêng với inputs/outputs/caching và credentials policy. Không gọi network để quyết định build tasks chỉ bằng một lệnh `help`.

### 15.4. Điều kiện ở top-level không làm công việc I/O được lazy

```kotlin
// Sai khi expensiveOperation() thật sự tính dữ liệu nặng ngay:
val data = expensiveOperation()

tasks.register("report") {
    doLast {
        // data đã được tính khi cấu hình, kể cả không gọi report.
    }
}
```

Di chuyển `expensiveOperation()` vào task action **và mô hình hóa mọi input tác động đến nó**. Tránh che công việc nặng bằng helper functions chạy lúc apply plugin.

## 16. Task execution work avoidance: inputs/outputs quyết định correctness

Dù task được configure lazily, khi nó nằm trong graph Gradle vẫn cần xem có phải thực thi hay không.

Trong demo, `GenerateMessageTask` có:

- `@InputFile`: source text file.
- `@Input`: message label.
- `@OutputFile`: generated result.
- `@TaskAction`: action tạo output.

**Thí nghiệm tối thiểu:**

1. Chạy `./gradlew generateMessage --no-build-cache` lần đầu: action tạo output.
2. Chạy lại cùng lệnh không sửa gì: task `UP-TO-DATE`; action không chạy.
3. Chỉ thay `data/message.txt` từ `hello gradle` sang `hello java`: action chạy lại.
4. File output phải thành `MESSAGE:HELLO JAVA`.
5. Chạy lại không đổi: `UP-TO-DATE`.

Gradle bỏ execution nhờ **task state tracking**, không phải vì provider không được realized.

### 16.1. Outcomes quan trọng

| Outcome | Ý nghĩa |
| --- | --- |
| Không có suffix đặc biệt | Task action đã thực thi thành công |
| `UP-TO-DATE` | Inputs/outputs không đổi; action bỏ qua |
| `FROM-CACHE` | Outputs được lấy lại từ build cache |
| `NO-SOURCE` | File inputs/sources rỗng theo task rules |
| `SKIPPED` | Task actions bị predicate/flag/logic skip |
| `FAILED` | Task thất bại; không được kết luận tối ưu thành công |

**Không dùng elapsed time làm oracle duy nhất.** Một task chậm có thể do môi trường/daemon/JDK warm-up; một task nhanh có thể đang tạo stale output. Phải kiểm cả task outcomes và nội dung outputs.

### 16.2. Build cache không giống configuration cache

| | Build cache | Configuration cache |
| --- | --- | --- |
| Lưu thứ gì? | Task outputs/transform results | Configured task graph và state |
| Giúp tránh? | Thực thi task action khi có cache hit | Cấu hình lại build trên cache hit |
| Outcome dễ thấy | `FROM-CACHE` | Message configuration cache reused |
| Phụ thuộc gì? | Declared inputs, implementation, cacheability | Build scripts, settings, configuration inputs, plugin compatibility |
| Có tự thay thế task registration lazy không? | Không | Không |
| Có thể bật cùng nhau? | Có | Có |

Không bật `--configuration-cache` trong thí nghiệm đếm task configuration actions trước khi hiểu hành vi; cache hit có thể khiến mọi configuration action logs biến mất, gây cảm giác mọi tasks đều lazy dù build còn eager code.

## 17. Configuration cache: giảm lặp lại toàn bộ configuration phase

Khi build logic hỗ trợ, chạy:

```bash
./gradlew generateMessage --configuration-cache \
  --no-build-cache --console=plain
./gradlew generateMessage --configuration-cache \
  --no-build-cache --console=plain
```

Lần đầu có thể ghi configuration cache entry; lần sau, nếu không có configuration inputs thay đổi, Gradle có thể **reuse** entry. Ở cache hit, configuration code không chạy lại; vì vậy `CONFIGURE generateMessage` có thể không xuất hiện lần sau.

**Các điều kiện/giới hạn:**

- Configuration cache khác task output cache.
- Buildscript/plugin code phải tương thích; không truy cập `Project`/configuration model từ task action một cách không được hỗ trợ.
- Environment/system properties, settings/build scripts và configuration input tracking ảnh hưởng cache key/invalidation.
- Plugin có global listeners, cross-project mutation hoặc side effects có thể cần refactor.
- IDE import/sync không nhất thiết có cùng configuration-cache behavior như CLI build.
- Dynamic/changing versions có thể làm invalidation khi dependency metadata hết hạn.
- Configuration cache không chứng minh task outputs đúng nếu task bỏ sót inputs.

**Đừng bật vội `--configuration-cache-problems=warn` rồi coi build đã tương thích.** Nếu có problems, sửa plugin/task model và chạy lại theo yêu cầu version đang dùng. Chế độ warning chỉ phục vụ quá trình migration có kiểm soát.

## 18. Multi-project: tránh cấu hình chéo gây chậm toàn bộ

Giả sử:

```text
root/
├── settings.gradle.kts
├── api/build.gradle.kts
├── service/build.gradle.kts
├── cli/build.gradle.kts
└── build-logic/
```

Một anti-pattern dễ gặp ở root:

```kotlin
subprojects {
    tasks.withType<Test>().all {
        // Cấu hình ngay mọi Test task ở nhiều modules.
    }
}
```

Nó kết hợp **cross-project configuration** và **eager task configuration**. Khi developer chỉ muốn `:api:compileJava`, Gradle có thể tốn công chạm nhiều project/task không liên quan.

Hướng tốt hơn cho monorepo là **convention plugins** đặt ở included `build-logic`; modules áp đúng plugin cần. Trong plugin, dùng `tasks.withType<Test>().configureEach`/`tasks.named` và Provider-based properties.

Ví dụ module:

```kotlin
plugins {
    id("company.java-library-conventions")
}
```

Đây là **ý tưởng kiến trúc**, không phải plugin có sẵn trong Gradle; muốn chạy phải tự định nghĩa plugin ID và implementation. Mục tiêu là tránh root script biết mọi chi tiết của subprojects.

**Cẩn thận:** chỉ chuyển `subprojects { ... }` thành function khác nhưng vẫn mutate mọi project ở configuration phase thì hiệu năng và coupling chưa được giải quyết. Phải đổi **mô hình ownership**: mỗi project tự áp plugin, configuration chỉ tạo khi cần, cross-project data đi qua declared dependencies/variants.

### 18.1. Configuration-on-demand không phải configuration avoidance

Gradle có cờ incubating `--configure-on-demand` để **cấu hình các projects liên quan**, chứ không chỉ những task instances liên quan. Nó là mức granularity khác:

- Configuration avoidance: trì hoãn **task realization/configuration**.
- Configuration-on-demand: cố gắng không configure **unrelated projects**.
- Configuration cache: reuse **task graph configuration** giữa invocations.
- Build cache/up-to-date: tránh **task action execution**.

Configuration-on-demand có các giới hạn khi projects bị coupling qua `allprojects`/`subprojects` hoặc logic tham chiếu cross-project mutable state. Không bật đại trên monorepo rồi bỏ qua tests; ưu tiên tách projects và conventions đúng trước.

### 18.2. Composite build và build-logic

Một `build-logic` included build có thể được biên dịch/configure để cung cấp plugins, nhưng không có nghĩa mọi tasks thuộc build đó luôn phải chạy. Tránh các plugin `apply()` thực hiện network scans hoặc resolve configurations sớm. Module chỉ cần khai báo capability, còn plugin dùng `tasks.register` và Provider wiring để tạo work khi tương ứng được request.

## 19. Compile avoidance, incremental compilation và test selection

Không cần compile mọi module chỉ vì một module có thay đổi.

### 19.1. Java compile avoidance

Khi Java library thay đổi **method body** nhưng **public ABI** không đổi, Gradle có thể tránh recompiling downstream modules nhờ compile avoidance (tùy inputs, Java plugin/toolchain/annotation processors). Đó là tối ưu khác task registration.

Ví dụ:

```java
package example.api;

public final class Maths {
    private Maths() {}

    public static int add(int a, int b) {
        return a + b;
    }
}
```

Nếu sửa implementation `return a + b` thành `return Math.addExact(a, b)` mà method signature không đổi, consumer compile classpath ABI có thể vẫn không thay đổi đáng kể. Nếu sửa public method signature hoặc public class/interface, downstream projects có thể phải compile lại.

**Đừng tuyên bố mọi method-body change luôn được bỏ qua:** annotation processors, compiler options, constant inlining, inline/reified language semantics, ABI snapshots và dependency graph có thể tác động. Đọc task outcomes thật.

### 19.2. Java incremental compilation

Khi `compileJava` bắt buộc chạy, Gradle vẫn có thể compile chỉ những classes bị ảnh hưởng, thay vì toàn bộ source set. Đó là **incremental work bên trong một task**, khác với `compileJava UP-TO-DATE` (task action hoàn toàn không chạy).

### 19.3. Test selection

Khi cần chạy một test class:

```bash
./gradlew test --tests "example.CalculatorTest" --console=plain
```

Chỉ chạy đúng class khi dự án thực sự có `example.CalculatorTest` và test framework đã được cấu hình. Đây là ví dụ CLI selection, **không phải runnable command của avoidance-lab baseline** (baseline chưa có test source/test engine).

Đừng dùng `-x test` trong CI build release nếu quality gate bắt buộc tests. Local development workflow có thể gọi đúng `test`/`compileJava`/`check` theo nhu cầu, và CI giữ full verification trước merge/release.

## 20. Đo cấu hình task chứ không chỉ đo total build time

Muốn chứng minh optimization, cần tách:

1. **Configuration time**: script evaluation, plugin application, task realization.
2. **Task graph size**: tasks nào được chọn và dependencies.
3. **Execution time**: task actions thực thi bao lâu.
4. **Cache/up-to-date outcomes**: bao nhiêu task không phải chạy.
5. **Dependency resolution time/network**: có làm I/O không cần thiết không.
6. **End-to-end time**: thời gian developer chờ thật sự, bao gồm JVM/Daemon/warm-up.

Trong demo, hai loại log:

```text
CONFIGURE generateMessage
EXECUTE generateMessage
```

chỉ là **instrumentation kỹ thuật để quan sát**, không phải một profiler chính xác. Trong project lớn, dùng profile/Build Scan đã được tổ chức chấp thuận; Gradle docs có hướng dẫn xem task realization/configuration counts, task execution, dependency downloads và build performance.

### 20.1. Quy trình đo trước/sau hợp lý

- Pin Gradle Wrapper và Java toolchain.
- Chọn cùng command, ví dụ `./gradlew help --no-configuration-cache` để đo configuration overhead.
- Chọn task thật, ví dụ `./gradlew :api:compileJava`, để đo developer workflow.
- Warm up Daemon; chạy nhiều lần, ghi median/p95 nếu cần.
- Không trộn hai runs có Gradle caches/network trạng thái hoàn toàn khác.
- Ghi máy, OS, core count, disk, memory và daemon settings khi so hai environments.
- Đếm tasks **realized/configured**, không chỉ số task registered.
- Đọc task outcomes/Build Scan để biết execution vs cached work.
- Thay **một thứ**: `create` → `register`, `all` → `configureEach`, eager resolution → Provider.
- Chạy tests/verify outputs sau tối ưu để bảo đảm correctness.
- Nếu cải thiện không đo được, kiểm lại giả thuyết và bottleneck; đừng giữ tối ưu phức tạp vô ích.

**Không nên** so tổng thời gian của `./gradlew clean build --no-daemon` với `./gradlew help` rồi gọi chênh lệch là lợi ích của task avoidance. Hai commands làm những công việc khác nhau.

### 20.2. Dùng Gradle logging một cách có chủ đích

```bash
./gradlew help --no-configuration-cache --console=plain
./gradlew generateMessage --no-configuration-cache --info --console=plain
./gradlew messageZip --no-configuration-cache --dry-run --console=plain
```

- `--info` cho thêm lý do task không up to date và dependency resolution thông tin.
- `--dry-run` chỉ cho biết **task graph dự kiến**, không thực thi actions; có thể vẫn configure tasks cần để lập graph.
- `--console=plain` dễ lưu console output vào CI logs.
- `--scan` chỉ dùng khi build scan/upload được policy tổ chức cho phép; scans có thể chứa environment và build metadata.
- Profile/scan nên được so **cùng task request và cùng toolchain/environment**.

## 21. Khi nào `register` chưa giúp được hiệu năng?

Một project đã dùng `tasks.register` khắp nơi nhưng `./gradlew help` vẫn chậm. Hãy kiểm theo thứ tự:

1. Có `tasks.all { ... }`/`tasks.withType<T> { ... }` khiến registered tasks bị realized không?
2. Có `tasks.getByName(...)`, `TaskProvider.get()` hoặc iteration toàn bộ tasks tại configuration time?
3. Có plugin `apply()` đọc file rất lớn, gọi network hoặc spawn process?
4. Có dependency resolution qua `configuration.files`/`asPath` khi không chạy task tiêu thụ?
5. Có root `subprojects`/`allprojects` config toàn bộ multi-project?
6. Có công cụ tạo thousands of tasks dù chỉ vài tasks dùng trong workflow?
7. Có `dependsOn` quá rộng kéo tests/docs/publish vào compilation tasks?
8. Có `afterEvaluate`/task callbacks tạo side effects hoặc eager transitive realization?
9. Có mandatory plugins không tương thích với configuration cache?
10. Có một bottleneck nằm ở Java compile/test execution, không nằm ở configuration?
11. Có Gradle Daemon bị tắt hay phải download dependencies mỗi invocation?
12. Có dynamic/changing versions ép metadata refresh và invalidate cache không?

**Đừng sửa tất cả một lượt.** Chọn một bottleneck có evidence và dùng targeted refactor.

### 21.1. Eager task callback gây cascade

Giả sử:

```kotlin
val a = tasks.register("taskA")
val b = tasks.register("taskB")

tasks.all {
    dependsOn(a, b)
}
```

Mẫu này sai về thiết kế vì tự thêm dependencies rộng và dùng eager collection callback. Một task không liên quan có thể kéo `taskA`/`taskB` hoặc gây cycle tùy graph. Không sửa bằng cách thay `all` thành `configureEach` mà giữ dependency mọi task: lazy configuration có thể cải thiện chi phí nhưng **task graph vẫn sai**.

**Tách hai câu hỏi:** có cần cấu hình task? và task có thật sự phụ thuộc công việc của hai task kia không? Chỉ tạo `dependsOn` khi có business/build dependency thật.

## 22. Task lifecycle, `check` và `assemble`: chọn scope đúng

Các lifecycle tasks thường có ý nghĩa:

- `classes`: compile/process main sources/resources theo Java plugin.
- `jar`: đóng gói Java artifact.
- `assemble`: tập hợp artifacts cần tạo.
- `test`: chạy unit tests.
- `check`: verification lifecycle, bao gồm tests và checks được plugins nối vào.
- `build`: assemble + check.
- `publish`: công bố artifacts theo publishing configuration, không phải luôn cần trong local iteration.

**Một sai lầm phổ biến:** gắn một expensive static analysis task vào `compileJava.dependsOn(...)` chỉ để “đảm bảo được chạy”. Developer compile code mỗi lần sẽ mất thời gian cho static analysis, dù output của analysis không phải input của Java compilation.

Nếu analysis là **quality gate**, có thể gắn nó vào `check`, còn developer chạy `compileJava` riêng. CI chạy `check` hay `build` theo policy.

Nếu output của code generator **thực sự là input của compiler**, thì phải nối generator vào compile task bằng Provider/generated source directory, không phải loại generator để compile nhanh. **Correctness thắng tốc độ**.

### 22.1. `mustRunAfter` không phải `dependsOn`

```kotlin
tasks.named("test") {
    mustRunAfter("compileJava")
}
```

Một ordering rule như trên không tự yêu cầu `compileJava`; nó chỉ áp thứ tự khi cả hai tasks đã thuộc graph. Trong Java plugin, `test` có producer dependencies riêng; đừng thay producer dependency bằng `mustRunAfter` để giảm task count. Nếu cần outputs, phải dùng `dependsOn` hoặc input/output Provider relationship đúng.

### 22.2. `finalizedBy` cũng có thể tăng công việc

`finalizedBy(cleanupTask)` có ích cho resource cleanup, nhưng finalizer là quan hệ mạnh, có thể thêm task vào graph khi task chính được chọn. Đừng gắn một task tổng hợp reporting đắt tiền vào finalizer của mọi compile task. Đặt cleanup/report tasks nơi semantics thật sự yêu cầu.

## 23. CI và shared convention plugins

Trong monorepo, tốt nhất các modules áp **convention plugin** phù hợp, ví dụ:

```kotlin
// api/build.gradle.kts — ví dụ khi tổ chức đã tự xây plugin.
plugins {
    id("company.java-library")
}
```

Plugin `company.java-library` có thể:

- Apply Java Library plugin khi module phù hợp.
- Đặt Java toolchain convention.
- Cấu hình `Test` và `JavaCompile` lazily bằng `configureEach`.
- Register optional reporting tasks bằng `TaskProvider`.
- Nối đúng `check` và `assemble` tasks.
- Dùng managed extension để module khai báo nhu cầu, không sửa task internals.
- Định nghĩa cacheable task types với đầy đủ inputs/outputs.
- Không gọi external services/network khi apply plugin.

**Tương thích:** `company.java-library` là plugin doanh nghiệp giả định, không tồn tại trong Gradle core. Nó cần code ở included build, `buildSrc` hoặc published plugin artifact.

Một CI workflow đúng:

```text
Pull request
   |
   +--- Gradle Wrapper / JDK setup
   |
   +--- Quick compile/test workflow
   |      (task graph được chọn chính xác)
   |
   +--- Full check / static analysis job
   |      (không bỏ quality gate)
   |
   +--- Build cache + configuration cache nếu tương thích
   |
   +--- Merge gate pass
   |
   +--- Release job: package / publish khi được phép
```

Tách **fast feedback** và **release verification** theo job/task scope, không để `onlyIf` trên một task quality-critical được developer thay đổi tùy ý. Nếu CI bắt buộc chạy security scans, chỉ một script `-x securityScan` để tiết kiệm thời gian là vi phạm policy.

## 24. Các lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân có thể | Chẩn đoán/khắc phục |
| --- | --- | --- |
| `help` in hàng trăm `CONFIGURE ...` | `tasks.create`, `all { }`, `getByName` | Chuyển sang `register`, `named`, `configureEach` |
| Đã dùng `register` nhưng vẫn configure mọi task | Một plugin khác eager iterate/tasks query | Kiểm `all`, `withType(...) { }`, `TaskProvider.get` |
| `:api:compileJava` kéo cả docs/ZIP | `dependsOn` rộng/sai | Chỉ nối actual inputs/producers; dành reporting cho `check` |
| `messageZip` không tạo được file source | Hardcode output path, thiếu producer dependency | Dùng `generated.flatMap { it.outputText }` |
| Task generator chạy ở `help` | Đọc file/HTTP ở root script hoặc plugin apply | Dời I/O vào declared task action |
| `register` block không in log khi gọi `help` | Task chưa được realized | Đúng configuration avoidance |
| `register` block có log khi gọi task | Task đã được realized vì nằm trong graph | Hành vi đúng |
| `generateMessage` action không chạy lần 2 | `UP-TO-DATE` | Kiểm file output vẫn đúng |
| `messageZip` chạy sau sửa input | Generated output/archive bytes đổi | Expected invalidation, không phải failure |
| `generateMessage` vẫn chạy mọi lần | Inputs/outputs thiếu hoặc external process đổi file | Xem `--info`, output fingerprints |
| `generateMessage FROM-CACHE` | Cache hit khi có cacheable task/output | Không phải `UP-TO-DATE` |
| `onlyIf=false` vẫn làm build configure | Predicate là execution skip | Không dùng nó thay registration avoidance |
| `onlyIf=false` nhưng dependency đã chạy | Dependencies trong graph trước task predicate | Cân nhắc task graph không kéo dependency khi không cần |
| `task.enabled=false` nhưng consumer thiếu output | Đã tắt producer cần thiết | Không disable producer khi downstream cần nó |
| `compileJava NO-SOURCE` | Không có Java files trong source set | Bình thường nếu module không có Java source |
| `build` chạy lâu nhưng `test` không đổi | Test task action/inputs, test forks hoặc overhead | Đọc Task outcomes và profile; kiểm chính sách tests |
| `runtimeClasspath.files` làm help chậm | Dependency resolution ở configuration phase | Giữ configuration/FileCollection lazy, resolve khi task cần |
| `Provider.get()` quá sớm | Force value resolution/realization | Dùng Provider mapping và task properties |
| `afterEvaluate` gây mutation too late | Trì hoãn logic theo lifecycle sai | Dùng `pluginManager.withPlugin`, task providers |
| `subprojects` config quá nhiều modules | Cross-project configuration/coupling | Convention plugins và module-local configuration |
| Configuration cache không reuse | Build scripts/env/config inputs đổi hoặc plugin không tương thích | Đọc Gradle problems report, sửa hidden config inputs |
| Config cache reused nhưng task thực thi | Outputs/input task changed | Hai cơ chế khác nhau, không mâu thuẫn |
| `--dry-run` cho ít tasks nhưng build vẫn chậm | Configuration logic/IO vẫn xảy ra; dry-run không đo execution | Kiểm profile và configuration time |
| `--parallel` làm thời gian không cải thiện | CPU/I/O bottleneck, dependency graph tuần tự | Profile critical path, task parallel safety |
| Build nhanh nhưng bỏ tests | Dùng `-x test` hoặc skip quality gates | Khôi phục correctness và workflow phù hợp |
| Cache hit từ máy khác tạo output sai | Hidden inputs, non-deterministic custom task | Sửa @Input/@Output, tắt caching tới khi đúng |
| CI chậm hơn máy local | Daemon/cold cache/network/JDK khác | So cùng environment, warm/cold states và worker counts |
| Task `jar` vẫn configure khi chạy `jar` | Task được yêu cầu | Configuration avoidance không bỏ task cần thiết |
| Duplicate task registration error | Đăng ký cùng tên hai lần | Dùng `named` để cấu hình task có sẵn |
| Không thấy `messageZip` sau `build` | Custom Zip chưa nối lifecycle | Gọi trực tiếp hoặc nối đúng `assemble` khi release cần |

## 25. Kịch bản kiểm thử ngắn để áp dụng cho một build thật

Đừng tối ưu vì “thấy Gradle nhiều tasks”. Áp dụng lần lượt:

**Bước 1 — ghi baseline:**

```bash
./gradlew --version
./gradlew help --no-configuration-cache --console=plain
./gradlew compileJava --no-configuration-cache --console=plain
```

Ghi Gradle/JDK versions, thời gian và task outcomes. Nếu có build scans được policy cho phép, ghi configuration time/task realization counts.

**Bước 2 — xác định eager APIs:**

Tìm trong build scripts/convention plugins: `tasks.create`, `tasks.all`, `getByName`, `TaskProvider.get`, `withType<T> { ... }` và file collection eager methods. Một hit không tự là bug; đánh giá có thật sự ép realization/IO ở đúng workflow đang chậm không.

**Bước 3 — thay nhỏ:**

```kotlin
// Trước:
tasks.create("report") { /* config */ }

// Sau:
tasks.register("report") { /* config */ }
```

Đảm bảo không có một dòng khác lấy task instance bằng `get()`.

**Bước 4 — test output correctness:**

Chạy đúng task report, kiểm output/result. Nếu nó là producer, kiểm consumer task đã có implicit/explicit dependency đúng.

**Bước 5 — so kết quả:**

Chạy lại `help` với configuration cache tắt, so xem config action của report còn chạy không. Sau đó chạy report lần 1/lần 2, xem `UP-TO-DATE` và output nội dung.

**Bước 6 — kiểm một thay đổi input:**

Đổi một file/property, chạy lại, output cập nhật đúng. Không tối ưu theo kiểu làm tasks không chạy ngay cả khi input thay đổi.

**Bước 7 — áp dụng trên CI:**

Chạy full tests, integration checks, release packaging theo policy. Nếu chỉ local `help` nhanh hơn nhưng build release bị thiếu artifacts, thay đổi chưa đạt yêu cầu.

**Bước 8 — tiếp tục với bottleneck khác:**

Chỉ sau khi baseline tốt, kiểm configuration cache, dependency resolution, cross-project configuration, remote caches, Java compile avoidance và test selection. Mỗi tối ưu cần một phép đo độc lập.

## 26. Bài tập tự luyện

### Bài 1 — phân biệt config và execution logs

Chạy `help`, `generateMessage` và `messageZip` với `--no-configuration-cache`. Ghi lại task nào in `CONFIGURE`, task nào in `EXECUTE` và vì sao.

**Kết quả mong đợi:** `help` không cần custom tasks; `generateMessage` realize/execute producer; `messageZip` cần producer output nhưng không cần `runApp`.

### Bài 2 — tạo một eager task rồi refactor

Tạo task `legacyReport` bằng `tasks.create`; xác nhận `help` in `CONFIGURE legacyReport`. Thay nó bằng `tasks.register` và chạy `help` lại. Không để cả hai definitions cùng tên.

### Bài 3 — phá avoidance bằng `all { }`

Thêm `tasks.all { logger.lifecycle("EAGER " + name) }` trong bản thử nghiệm, gọi `help` và quan sát log. Thay bằng `tasks.configureEach { ... }`. Chỉ làm trong sandbox vì in logs của tất cả tasks làm output dài và có thể ảnh hưởng performance measurements.

### Bài 4 — dùng `get()` sai chỗ

Tạm thêm `generated.get()` sau `tasks.register` ở root script. Chạy `help`, thấy generator bị realized dù không cần. Xóa dòng đó và giữ TaskProvider.

### Bài 5 — thử `onlyIf` khác configuration avoidance

Thêm snippet `diagnostics` ở phần 13. Gọi không có flag `runDiagnostics`, xem `SKIPPED`. Giải thích vì sao task vẫn phải có mặt trong graph và có thể được cấu hình.

### Bài 6 — Up-to-date và input change

Chạy `generateMessage` hai lần với `--no-build-cache`; lần thứ hai `UP-TO-DATE`. Sửa `data/message.txt` sang `hello java`; chạy lại và xác nhận `MESSAGE:HELLO JAVA`. Không dùng `clean` giữa hai baseline.

### Bài 7 — Java task isolation

Chạy `runApp` và kiểm `JAVA_17_OK`. Quan sát không có `EXECUTE generateMessage`. Sau đó chạy `messageZip` và kiểm ZIP được tạo. Đề bài là chọn task scope đúng, không ép một task phụ thuộc task không cần.

### Bài 8 — mở rộng sang multi-project

Thêm `:api` và `:service`, tạo shared convention plugin thay cho root `subprojects { tasks.all { ... } }`. Kiểm `:api:compileJava` không realize unrelated `:service:test` nếu không có cross-project dependency thật.

### Bài 9 — đo trước/sau với configuration cache

Sau khi đã kiểm lazy task behavior với `--no-configuration-cache`, thử hai lần `--configuration-cache`. Ghi cache reused vs configuration actions. Nếu Gradle báo problems, sửa hoặc giới hạn claim; không coi cache hit thay thế correctness tests.

### Bài 10 — tìm chi phí dependency resolution

Trong sandbox, thêm một anti-pattern đọc `configurations.runtimeClasspath.files` tại top-level, quan sát `help` chậm hoặc có dependency resolution. Chuyển sang task type khai báo `ConfigurableFileCollection` và chỉ resolve khi task được request. Không ép tải dependencies thật từ remote nếu bạn đang ở offline CI.

## 27. Câu hỏi tự kiểm tra

1. **`tasks.register` khác `tasks.create` ở đâu?** `register` giữ task lazily; `create` eager tạo/cấu hình task.
2. **`TaskProvider` là task instance chưa?** Chưa. Nó là handle đến một task được đăng ký.
3. **`TaskProvider.get()` ở configuration time có tác động gì?** Có thể force realization, phá avoidance.
4. **`tasks.named` khác `getByName` thế nào?** `named` lấy lazy provider; `getByName` lấy instance eager.
5. **`withType<T>().configureEach` khác `withType<T>().all` thế nào?** `configureEach` defer action tới task realized; `all` có semantics eager.
6. **Task không được thực thi nhưng có thể được cấu hình không?** Có, khi nằm trong graph rồi up-to-date/skipped.
7. **`onlyIf=false` có bỏ task khỏi graph không?** Không; nó bỏ qua action trước execution.
8. **`mustRunAfter` có đưa task kia vào graph không?** Không, chỉ điều khiển thứ tự nếu cả hai được chọn.
9. **`dependsOn` có kéo task dependency vào graph không?** Có, khi task dependent được yêu cầu.
10. **Vì sao dùng output Provider của task khác?** Giữ lazy value và implicit producer dependency.
11. **`@InputFile`/`@OutputFile` giúp gì?** Cho Gradle theo dõi state, tránh action thừa và kiểm correctness.
12. **`UP-TO-DATE` có giống `FROM-CACHE` không?** Không; một dùng state hiện có, một phục hồi output từ cache.
13. **`configuration cache reused` có chứng minh task `UP-TO-DATE` không?** Không; hai cơ chế khác nhau.
14. **`NO-SOURCE` nghĩa là gì?** Task không có source files cần xử lý theo semantics của task.
15. **Đọc `runtimeClasspath.files` trong configuration phase có vấn đề gì?** Có thể force dependency resolution/IO khi không cần.
16. **Gọi HTTP trong plugin `apply()` có tốt cho `help` không?** Không; đó là chi phí luôn xảy ra.
17. **Thêm `-x test` vào release CI là tối ưu hợp lệ?** Không nếu CI cần tests.
18. **`runApp` nên phụ thuộc `messageZip`?** Không trong demo, vì chạy Java không cần ZIP.
19. **Java method-body change có luôn buộc compile downstream module?** Không; Gradle có thể dùng compile avoidance khi ABI không đổi.
20. **Tại sao nên đo tasks realized mà không chỉ tasks registered?** Registration rẻ; chi phí đến từ creation/configuration.
21. **Dùng `--dry-run` đo execution speed được không?** Không; không chạy task actions.
22. **Root `subprojects { ... }` luôn sai?** Không phải mọi đoạn đều sai, nhưng cross-project coupling/eager config làm giảm khả năng tối ưu; convention plugin thường phù hợp hơn.
23. **Nếu `help` không in `CONFIGURE generateMessage` có đủ chứng minh toàn bộ build nhanh?** Không, chỉ chứng minh một task không bị realized trong invocation đó.
24. **Khi nào một task nên ở `check` thay vì `compileJava`?** Khi nó là quality/verification gate, không phải compile input.
25. **Thế nào là tối ưu đúng?** Giảm work thực tế mà không thay đổi correctness và contracts của tasks/outputs.

## 28. Checklist trước khi chốt hiệu năng build

- [ ] Đo baseline với Gradle/JDK versions và commands nhất quán.
- [ ] Không dùng `--configuration-cache` khi thử riêng task configuration avoidance.
- [ ] Chuyển task creation mới sang `tasks.register`/`register<T>`.
- [ ] Cấu hình tasks hiện có bằng `tasks.named`.
- [ ] Dùng `withType<T>().configureEach` thay các eager collection callbacks.
- [ ] Không gọi `TaskProvider.get()` trong configuration nếu không cần.
- [ ] Dùng Provider/Property để nối values và task outputs lazy.
- [ ] File đầu ra do producer được tiêu thụ qua Provider thay hardcoded path.
- [ ] Không resolve Gradle configurations tại top-level nếu task chưa cần.
- [ ] Không quét files, gọi HTTP hay spawn process trong plugin `apply()`.
- [ ] Task actions nằm ở execution phase, không ẩn side effects trong provider map.
- [ ] Inputs/outputs của custom tasks chính xác để `UP-TO-DATE` hoạt động.
- [ ] Chọn task CLI phù hợp workflow, không gọi `build` cho mọi thao tác.
- [ ] Không thêm `dependsOn` quá rộng kéo docs/tests/publish vào compile.
- [ ] Không dùng `onlyIf`/`enabled=false` để che dependency graph sai.
- [ ] Không bỏ quality gates chỉ để có thời gian chạy đẹp.
- [ ] Với multi-project, cân nhắc convention plugins thay cross-project mutation.
- [ ] Chỉ bật configuration-on-demand khi đã kiểm correctness và compatibility.
- [ ] Test configuration cache riêng với plugins/tasks tương thích.
- [ ] Phân biệt `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE`, `SKIPPED` và executed.
- [ ] Thử controlled input change, xác nhận outputs cập nhật đúng.
- [ ] Kiểm build artifact/ABI/test correctness sau khi refactor.
- [ ] Ghi performance wins theo cùng workload/host, không dựa cảm giác.
- [ ] Nếu CI deploy/release, giữ full verification/signing/publishing policy.
- [ ] Có task graph/performance evidence để reviewer hiểu lý do thay đổi.

## 29. Ghi nhớ

- **`tasks.register` và `TaskProvider` tránh tạo/configure task chưa cần**, khác `tasks.create` và `getByName`.
- **`tasks.named`, `configureEach` giữ cấu hình lazy**, còn `all { }` và eager iterations có thể phá tránh cấu hình.
- **`TaskProvider.get()` không phải cách nối task**: dùng provider trực tiếp trong `dependsOn`/file inputs.
- **Configuration avoidance không bảo đảm task action bị skip**; task được chọn có thể chạy, `UP-TO-DATE` hoặc `FROM-CACHE`.
- **`onlyIf` và `enabled=false` bỏ execution**, không loại bỏ task registration/configuration hay mọi dependency work.
- **`Provider`/`Property` trì hoãn giá trị đầu vào**, còn `@Input`/`@Output` cho phép Gradle tránh chạy lại.
- **Không làm expensive I/O ở configuration phase** — đặc biệt dependency resolution, filesystem scans, HTTP và process execution.
- **Không thêm dependencies vào task graph khi không có quan hệ thật**, không tối ưu bằng cách bỏ kiểm thử bắt buộc.
- **Configuration cache, build cache, compile avoidance, parallelism** giải quyết những bottlenecks khác nhau; cần đo và kiểm riêng.
- **Build đúng trước, nhanh sau**: mọi tối ưu phải giữ output correctness, Gradle task relationships và CI quality gates.

## Tài liệu chính thức

- [Gradle — Avoiding Unnecessary Task Configuration](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): registration, realization, `TaskProvider`, `named`, `configureEach`, lazy/eager APIs, migration pitfalls.
- [Gradle — Configuring Tasks Lazily](https://docs.gradle.org/current/userguide/lazy_configuration.html): `Provider`, `Property`, `convention`, `map`/`flatMap`, task output wiring.
- [Gradle — Best Practices for Performance](https://docs.gradle.org/current/userguide/best_practices_performance.html): tránh công việc nặng trong configuration phase, configuration cache.
- [Gradle — Improving Performance](https://docs.gradle.org/current/userguide/performance.html): profiling, cache, build scans, dependency resolution, compilation optimizations, Java projects.
- [Gradle — Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html): avoiding eager Gradle file collection/dependency queries, correct task inputs/outputs.
- [Gradle — Writing Tasks](https://docs.gradle.org/current/userguide/writing_tasks.html): task registration, task work and lifecycle task distinctions.
- [Gradle — Controlling Task Execution](https://docs.gradle.org/current/userguide/controlling_task_execution.html): `dependsOn`, ordering rules, `finalizedBy`, `onlyIf`, disabled tasks, exclusions.
- [Gradle — Incremental Builds and Build Caching](https://docs.gradle.org/current/userguide/gradle_optimizations.html): `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE`, `SKIPPED` outcomes.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): configuration-model reuse, lifecycle, serialization and task compatibility.
- [Gradle — Configuration-on-Demand](https://docs.gradle.org/current/userguide/configuration_on_demand.html): incubating multi-project selective configuration.
- [Gradle — Sharing Build Logic](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html): convention plugins thay cross-project configuration.
- [Gradle — CLI Performance Options](https://docs.gradle.org/current/userguide/command_line_interface.html): `--build-cache`, `--no-build-cache`, `--configuration-cache`, `--configure-on-demand`, `--dry-run`, `--info`.

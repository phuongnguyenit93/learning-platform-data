# Bật Configuration Cache và đọc báo cáo không tương thích trong Gradle

## 1. Mục tiêu và bối cảnh

Đây là bài Knowledge trong nhóm **Các lớp cache** của chủ đề **Build Tool Gradle**. Khi dự án có nhiều module, Gradle không chỉ mất thời gian biên dịch Java, chạy test hoặc đóng gói JAR, mà còn cần cấu hình projects, plugins, tasks, dependencies và task graph. Nếu build scripts/phần cấu hình không đổi, lặp lại toàn bộ configuration phase có thể là công việc thừa.

**Configuration Cache** giúp Gradle lưu lại **kết quả cấu hình cho một tập task requests** cùng các dữ liệu đầu vào của giai đoạn configuration. Ở lượt sau nếu entry còn hợp lệ, Gradle **khôi phục configured task graph** và thực thi các task cần thiết, thay vì đánh giá lại build scripts như trước. Cơ chế này khác **Build Cache** (lưu task outputs) và **up-to-date checks** (kiểm tra đã có outputs hợp lệ).

Bài này giải quyết hai kỹ năng bắt buộc: **bật Configuration Cache đúng cách** và **đọc HTML problems report để xử lý các lỗi không tương thích**, thay vì chỉ thêm một flag rồi bỏ qua warnings.

Sau bài học bạn sẽ biết:

- Bật/tắt cache theo invocation và bật mặc định với `gradle.properties`.
- Quan sát lần đầu `Configuration cache entry stored` và lượt sau `Configuration cache entry reused`.
- Phân biệt cache reuse với `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE`.
- Xác định file `.gradle/configuration-cache` và báo cáo `configuration-cache-report.html`.
- Đọc report theo **Grouped by message**, **Grouped by task** và **Inputs**.
- Hiểu vì sao `Task.project`/`Project`/`Gradle`/`Settings` không được dùng tùy ý trong task actions.
- Sửa custom tasks bằng `Property<T>`, `RegularFileProperty`, Providers, lazy wiring và typed task actions.
- Phân biệt configuration input và task input; xử lý invalidation do Gradle properties, environment và external processes.
- Hiểu `--configuration-cache-problems=warn`, `problems=fail` và `notCompatibleWithConfigurationCache`.
- Áp dụng từng bước cho Gradle Kotlin DSL + Java 17, plugin nội bộ, multi-module và CI.
- Kiểm tra các nguy cơ serialization, secrets, mã hóa cache và lỗi của plugin bên thứ ba.

**Chú ý:** Một build `BUILD SUCCESSFUL` khi tắt Configuration Cache không có nghĩa nó tương thích khi cache được bật. Bật cache có thể phơi bày những lỗi tồn tại từ trước trong thiết kế build logic.

## 2. Phân biệt các lớp cache

| Lớp/cơ chế | Trạng thái hoặc nơi dữ liệu được lưu | Tác dụng |
| --- | --- | --- |
| Up-to-date checks | Local task execution history và output snapshots | Không chạy task action nếu đầu vào/đầu ra còn hợp lệ |
| Build Cache | Local/remote cached task outputs | Khôi phục đầu ra tương ứng với cache key |
| **Configuration Cache** | `.gradle/configuration-cache` | Tái sử dụng configured task graph và task state |
| Dependency Cache | Gradle user home module cache | Tái sử dụng JAR/POM/dependency metadata đã tải |
| Gradle Daemon/JIT | JVM process và warm-up | Giảm thời gian khởi động, tối ưu JVM execution |

Những trạng thái dễ nhầm:

- `UP-TO-DATE`: task không chạy action vì input/output state hợp lệ.
- `FROM-CACHE`: task có output được lấy từ Build Cache.
- `Configuration cache entry reused`: Gradle lấy lại cấu hình/task graph từ cache.
- `NO-SOURCE`: task xử lý source files nhưng không có source phù hợp.
- `SKIPPED`: task bỏ qua vì điều kiện hoặc cơ chế skip riêng.

**Không suy luận:** Configuration Cache reused **không** có nghĩa task `compileJava` phải `UP-TO-DATE`. Nếu Java source thay đổi, task có thể chạy bình thường trên một task graph vừa được khôi phục.

## 3. Configuration Cache nằm ở đâu trong vòng đời build?

Gradle có các giai đoạn:

~~~text
Initialization
   - đọc Settings, cấu trúc modules và included builds
          |
          v
Configuration
   - apply plugins
   - đánh giá build scripts
   - tạo/cấu hình task graph cho request
          |
          v
Execution
   - kiểm tra task inputs/outputs
   - chạy tasks, dùng up-to-date / build cache nếu phù hợp
~~~

Khi bật Configuration Cache:

~~~text
Lượt 1: Không có entry hợp lệ
  -> configuration bình thường
  -> serialize configured graph/state
  -> lưu entry và fingerprint configuration inputs
  -> chạy tasks

Lượt 2: Entry hợp lệ
  -> kiểm tra configuration inputs
  -> deserialize configured graph/state
  -> chạy tasks cần thiết, bỏ phần lớn configuration work
~~~

Hai loại dữ liệu chính:

1. **Cache entry**: tập scheduled tasks và state đủ để chạy chúng, bao gồm các reachable fields/Providers/file collections/build-service references.
2. **Configuration input fingerprint**: build scripts, Settings, applied plugin code, Gradle/system/environment properties hoặc files ảnh hưởng kết quả cấu hình theo APIs được theo dõi.

Task fields có thể được serialize dù một property mang annotation `@Internal`. Annotation `@Internal` của task input/output model **không phải** lệnh “đừng serialize field này vào Configuration Cache”.

## 4. Bật cache cho một lệnh

Tại root dự án có Gradle Wrapper tin cậy:

Linux/macOS:

~~~bash
./gradlew help --configuration-cache --console=plain
./gradlew help --configuration-cache --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat help --configuration-cache --console=plain
.\gradlew.bat help --configuration-cache --console=plain
~~~

Lượt đầu khi entry chưa có và code tương thích có thể thấy:

~~~text
Calculating task graph as no cached configuration is available for tasks: help
...
Configuration cache entry stored.
~~~

Lượt sau cùng task request, Gradle version và các configuration inputs:

~~~text
Reusing configuration cache.
...
Configuration cache entry reused.
~~~

Các đoạn trên là **thông điệp đại diện**, không phải transcript console cam kết trên mọi bản Gradle. Nếu có incompatibilities, mặc định build sẽ fail và entry có thể bị discard.

### 4.1. Vì sao bắt đầu bằng help?

`help` có task graph nhỏ. Nó giúp phát hiện lỗi plugin/build-script configuration cơ bản trước khi chạy tasks nặng. Nhưng **help pass chưa đủ**: các task thực tế `test`, `check`, `assemble` hoặc `publish` có thể đưa vào graph những custom task types không tương thích.

### 4.2. Bật cache cho một task thực tế

~~~bash
./gradlew :library:test --configuration-cache --console=plain
./gradlew :library:test --configuration-cache --console=plain
~~~

Đổi `:library` thành module thật. Chạy lại đúng request hai lần để có cơ hội kiểm chứng **store** rồi **reuse**; đừng đổi flags, environment hoặc build script giữa hai lượt.

### 4.3. Tạm tắt cache

~~~bash
./gradlew :library:test --no-configuration-cache --console=plain
~~~

Lệnh trên hữu ích cho việc so sánh hoặc cô lập lỗi, không phải một cách sửa build logic không tương thích.

## 5. Bật mặc định với gradle.properties

Trong **root `gradle.properties`**:

~~~properties
org.gradle.configuration-cache=true
org.gradle.configuration-cache.problems=fail
~~~

Khi đó:

~~~bash
./gradlew :library:test --console=plain
~~~

có thể dùng Configuration Cache mà không cần `--configuration-cache` ở mỗi lệnh. `problems=fail` là default của Gradle hiện hành; viết rõ ra giúp teams không lẫn với hướng dẫn cũ dùng `warn` vĩnh viễn.

**Lộ trình khuyến nghị:** Thử flag cho vài workflows trước, sửa hết incompatibilities, kiểm tra reuse và kết quả task, rồi mới commit `org.gradle.configuration-cache=true` cho cả team.

### 5.1. Flag CLI và project property không đồng nghĩa Build Cache

~~~properties
org.gradle.configuration-cache=true
org.gradle.caching=true
~~~

Đây là **hai property khác nhau**. Dòng đầu bật configuration caching; dòng sau bật Build Cache. Có thể bật riêng. Không thêm `org.gradle.caching=true` chỉ để mong Configuration Cache hoạt động.

### 5.2. Khi nào không nên bật toàn repo ngay?

Nếu repository có build logic legacy với nhiều tasks chưa compatible, bật toàn team sẽ khiến nhiều developers bị lỗi khó hiểu. Nên adopt từng task graph/module, có issue owner rõ, sau đó mới bật default cùng CI regression tests.

## 6. Lab: Gradle Kotlin DSL + Java 17, không cần dependency ngoài

Bài lab tạo một task ghi file UTF-8, rồi dùng Java 17 đọc đúng output. Nó cho thấy **configuration cache reuse** và **task up-to-date** là hai sự kiện riêng.

Cấu trúc:

~~~text
configuration-cache-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── src/main/java/demo/GreetingPrinter.java
├── gradlew
├── gradlew.bat
└── gradle/wrapper/...
~~~

Cần Gradle Wrapper hợp lệ và JDK 17. Nếu mới tạo folder trống, phải khởi tạo Wrapper theo quy trình tin cậy; không dùng Wrapper JAR không rõ nguồn. Lab không cần tải JUnit hay Commons Lang.

### 6.1. settings.gradle.kts

~~~kotlin
rootProject.name = "configuration-cache-demo"
~~~

### 6.2. build.gradle.kts hoàn chỉnh

~~~kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction

plugins {
    base
}

abstract class GenerateGreeting : DefaultTask() {

    @get:Input
    abstract val person: Property<String>

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val message = "Xin chào, ${person.get()}!\n"

        val file = outputFile.get().asFile
        file.parentFile.mkdirs()
        file.writeText(message, Charsets.UTF_8)

        logger.lifecycle("Generated: ${file.name}")
    }
}

tasks.register<GenerateGreeting>("generateGreeting") {
    group = "demo"
    description = "Tạo greeting theo Gradle property person."

    person.set(
        providers.gradleProperty("person")
            .orElse("Lan")
    )

    outputFile.set(
        layout.buildDirectory.file("generated/greeting.txt")
    )
}
~~~

Mã dùng Gradle Kotlin DSL hợp lệ, một custom task type có managed properties. Task action:

- Đọc `person` và `outputFile` đã được cấu hình.
- Không gọi `project`, `gradle`, `settings` tại execution time.
- Không giữ `Project` hoặc `Gradle` trong task fields.
- Không tạo side effect ở configuration time.
- Ghi một output file đã khai báo và deterministic theo `person`.
- Dùng `tasks.register` để đăng ký task lazy.
- Không đọc random/time/environment trực tiếp trong task action.

`@get:Input` và `@get:OutputFile` chủ yếu phục vụ task up-to-date/snapshot model, nhưng việc dùng managed properties và không chạm live model trong action cũng thuận lợi cho Configuration Cache.

`plugins { base }` cung cấp task `clean`/base conventions; nó không tự compile Java source. Mục tiêu của lab là custom Gradle task, còn Java sẽ được chạy bằng `javac/java` bên ngoài Gradle.

### 6.3. Java 17 source chạy độc lập

**src/main/java/demo/GreetingPrinter.java**

~~~java
package demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class GreetingPrinter {
    private GreetingPrinter() {
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Cần đúng một đường dẫn đến file greeting"
            );
        }

        String result = Files.readString(
            Path.of(args[0]),
            StandardCharsets.UTF_8
        );

        System.out.print(result);
    }
}
~~~

Java 17 program đọc đúng UTF-8 text file của task và in nguyên văn. `print`, không phải `println`, vì task đã ghi newline LF.

### 6.4. Lần đầu chạy Gradle

~~~bash
./gradlew generateGreeting --configuration-cache --console=plain
~~~

Dòng action khi task thực thi:

~~~text
Generated: greeting.txt
~~~

File `build/generated/greeting.txt` chứa:

~~~text
Xin chào, Lan!
~~~

Nếu không có issues, Gradle có thể báo `Configuration cache entry stored.`.

### 6.5. Lần thứ hai

~~~bash
./gradlew generateGreeting --configuration-cache --console=plain
~~~

Nếu entry hợp lệ và task output còn nguyên, các trạng thái có thể là:

~~~text
Reusing configuration cache.
> Task :generateGreeting UP-TO-DATE
Configuration cache entry reused.
~~~

Đây chỉ là đoạn thể hiện **ý nghĩa**, không khẳng định thứ tự log cố định. `UP-TO-DATE` là task snapshot status; `entry reused` là configuration cache status. Task action không chạy lại nên thông điệp `Generated: greeting.txt` sẽ không xuất hiện trong lần thứ hai khi task up-to-date.

### 6.6. Dùng javac/java để kiểm chứng

Linux/macOS:

~~~bash
mkdir -p out
javac -encoding UTF-8 --release 17 \
  -d out src/main/java/demo/GreetingPrinter.java
java -cp out demo.GreetingPrinter build/generated/greeting.txt
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -encoding UTF-8 --release 17 -d out src\main\java\demo\GreetingPrinter.java
java -cp out demo.GreetingPrinter build\generated\greeting.txt
~~~

**Stdout chính xác:**

~~~text
Xin chào, Lan!
~~~

Java program xác minh output bytes/Unicode. Để xác minh Configuration Cache, **phải đọc Gradle log**, không chỉ nhìn Java stdout.

### 6.7. Đổi task input

~~~bash
./gradlew generateGreeting \
  -Pperson=Mai \
  --configuration-cache \
  --console=plain
~~~

File output thành:

~~~text
Xin chào, Mai!
~~~

`person` là task `@Input` nên output cần đổi. Việc configuration cache reuse hay invalidate khi giá trị đổi phụ thuộc Provider wiring/Gradle semantics; **không suy luận chỉ từ việc task phải thực thi lại**. Trên Gradle hiện hành, lazy Provider được nối vào task property có thể giúp thay value mà không buộc cấu hình lại toàn bộ task graph.

### 6.8. Thử clean

~~~bash
./gradlew clean generateGreeting --configuration-cache --console=plain
~~~

`clean` xóa generated output trong build directory, task `generateGreeting` phải tạo lại. Configuration Cache có thể tái sử dụng task graph cho request **`clean generateGreeting`** nếu đã có entry đúng task set; entry này khác request chỉ `generateGreeting`.

### 6.9. Thử --no-build-cache

~~~bash
./gradlew generateGreeting \
  --configuration-cache \
  --no-build-cache \
  --console=plain
~~~

Build Cache bị tắt, nhưng Configuration Cache vẫn có thể reuse và task vẫn có thể UP-TO-DATE. Đây là một phép kiểm tra trực tiếp hai lớp cache độc lập.

## 7. Configuration Cache được lưu ở đâu?

Gradle lưu project-local state ở root build:

~~~text
.gradle/configuration-cache/
~~~

Không commit thư mục này vào repository; nó có thể chứa task state và configuration input fingerprints, kể cả dữ liệu nhạy cảm nếu plugin/task state đã giữ credentials.

Thông thường Gradle tự invalidate entry khi configuration inputs thay đổi; không cần xóa cache hằng ngày.

### 7.1. Không nhầm với Build Cache và outputs

~~~text
.gradle/configuration-cache/          Configured task graph/state
build/generated/greeting.txt           Output của custom task trong lab
GRADLE_USER_HOME/caches/...            Downloaded dependency/cache state
build/reports/configuration-cache/...  HTML problems report khi có issues
~~~

Thư mục `.gradle/configuration-cache` không phải chỗ người dùng nên ghi file output tùy ý. Output task nên dùng `layout.buildDirectory`/declared output property.

## 8. Lỗi có chủ đích: `Task.project` trong execution phase

Một đoạn Gradle Kotlin DSL legacy:

~~~kotlin
tasks.register("badProjectAccess") {
    doLast {
        logger.lifecycle("Project: ${project.name}")
    }
}
~~~

Đây là **mảnh code sai để thực hành**, không dán vào lab chính nếu đang xác nhận cache pass. `project` được truy cập trong task action, tại execution time. Với Configuration Cache, Gradle không cho task chạy dựa vào live `Project` model theo cách này.

Trong một bản sao lab, thêm task trên vào `build.gradle.kts`, chạy:

~~~bash
./gradlew badProjectAccess \
  --configuration-cache \
  --stacktrace \
  --console=plain
~~~

Có thể xuất hiện thông báo dạng:

~~~text
Invocation of 'Task.project' by task ':badProjectAccess'
at execution time is unsupported with the configuration cache.
~~~

**Đây là message minh họa, không phải lời hứa console nguyên văn.** Gradle có thể báo problem tại thời điểm serialize hoặc execute tùy version/cấu trúc action.

Điều cần làm: mở link HTML report mà Gradle in, xem task `:badProjectAccess`, message tương ứng và stack trace. Không khắc phục bằng cách chỉ thêm `@Internal` lên Project reference.

## 9. Sửa task sai bằng managed property

Nếu task cần `project.name`, lấy giá trị khi configuration rồi truyền qua `Property<String>`:

~~~kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.TaskAction

abstract class PrintProjectName : DefaultTask() {
    @get:Input
    abstract val projectNameText: Property<String>

    @TaskAction
    fun printIt() {
        logger.lifecycle(
            "Project: ${projectNameText.get()}"
        )
    }
}

tasks.register<PrintProjectName>("printProjectName") {
    projectNameText.set(project.name)
}
~~~

Đây là **một mảnh mở rộng build.gradle.kts**, dùng các imports ở đầu file. Có thể thêm vào lab ở phần 6, nhưng tránh khai báo trùng imports/classes và không để `badProjectAccess` trong quality gate bình thường.

Chạy:

~~~bash
./gradlew printProjectName --configuration-cache --console=plain
~~~

Dòng task log:

~~~text
Project: configuration-cache-demo
~~~

Mô hình đúng:

- `project.name` được đọc **lúc cấu hình**.
- Action chỉ đọc managed `Property<String>`, không tham chiếu `Project`.
- String input được khai báo rõ.
- Task log console không có output file nên **không mặc định up-to-date**, nhưng configuration cache **vẫn có thể reuse task graph**. Điều đó chứng minh task output caching và configuration caching độc lập.

### 9.1. Script local variable có thể đơn giản hơn

Đối với một task `doLast` nhỏ, có thể capture một local scalar trong task configuration block:

~~~kotlin
tasks.register("printProjectNameSimple") {
    val stableProjectName = project.name

    doLast {
        logger.lifecycle(
            "Project: $stableProjectName"
        )
    }
}
~~~

Nó không capture live `Project` trong action, chỉ giữ một `String`. Với logic phức tạp, typed task và managed properties cho validation/reuse tốt hơn.

### 9.2. Không capture top-level Kotlin DSL script state

Một sai lầm ít rõ hơn:

~~~kotlin
val generatedFile = layout.buildDirectory.file("demo.txt")

tasks.register("badGeneratedTask") {
    outputs.file(generatedFile)
    doLast {
        generatedFile.get().asFile.writeText("Ready\n")
    }
}
~~~

Trong Kotlin DSL, top-level `val` có thể trở thành property của compiled script class; closure trong `doLast` capture **script object** không serializable. Cách sửa cho ad-hoc task là tạo local reference bên trong task configuration block:

~~~kotlin
val generatedFile = layout.buildDirectory.file("demo.txt")

tasks.register("generateFileSafely") {
    val output = generatedFile
    outputs.file(output)

    doLast {
        val file = output.get().asFile
        file.parentFile.mkdirs()
        file.writeText("Ready\n", Charsets.UTF_8)
    }
}
~~~

Mảnh này minh họa tránh capture script object; một typed task với `RegularFileProperty` còn rõ ràng hơn và phù hợp khi reusable.

## 10. Đọc báo cáo `configuration-cache-report.html`

Khi gặp issues, Gradle thường in link:

~~~text
See the complete report at
file:///.../build/reports/configuration-cache/.../configuration-cache-report.html
~~~

Đường dẫn report thường dưới:

~~~text
build/reports/configuration-cache/<hash>/configuration-cache-report.html
~~~

Một số Gradle releases có **thêm tầng hash/thư mục**. Vì vậy **dùng đường dẫn chính xác trong console** là nguồn tin cậy nhất, đừng hard-code depth/hash rồi nghĩ file bị mất.

### 10.1. Quy trình đọc report

1. Mở HTML link do Gradle in trên đúng máy chạy build, hoặc tải CI job artifact nếu chạy remote.
2. Xem **tổng số Configuration Cache problems** và kết luận entry `stored`, `reused` hay `discarded`.
3. Chuyển sang **Grouped by message**: những lỗi giống nhau từ nhiều tasks/plugin classes được gom lại.
4. Chuyển sang **Grouped by task**: xác định task paths nào (`:app:bundle`, `:lib:test`, `:badProjectAccess`) bị ảnh hưởng.
5. Mở rộng tree để xem **task type, field/property, nested object graph, method** gây serialization hoặc execution-time access.
6. Đọc file path và line number/stack trace nếu report có.
7. Theo link đến **Configuration Cache requirements** cho problem đó.
8. Mở tab **Inputs** nếu có, để xem configuration inputs đã được theo dõi.
9. Sửa nguyên nhân trong source plugin/build script, không sửa file cache đã được serialize bằng tay.
10. Chạy lại cùng task request và xác minh entry được lưu **không còn problems**.
11. Chạy lần hai để thấy cache reused; kiểm thử kết quả build/test bình thường.

### 10.2. Grouped by message để tìm lỗi lặp

Nếu 15 tasks cùng báo `Task.project at execution time`, thường một shared convention plugin hoặc task base class gây vấn đề. Sửa **một nguồn** có thể xóa nhiều entries.

### 10.3. Grouped by task để tìm owner

Nếu chỉ `:service:package` bị lỗi, vào task đó để xem source type, field của task và closure/action. Tránh sửa ngẫu nhiên `:core:compileJava` hoặc toàn bộ build.

### 10.4. Inputs tab không phải danh sách `@Input` của task

Configuration inputs quyết định khi nào **task graph phải cấu hình lại**. Task `@Input` quyết định khi nào **task action phải chạy lại**. Ví dụ:

- Sửa `settings.gradle.kts` có thể khiến configuration cache miss.
- Sửa `src/main/java/Foo.java` có thể khiến `compileJava` chạy nhưng configuration cache reuse.
- Sửa file mà custom script đọc ở **configuration phase** có thể invalidate entry.
- Đổi Provider task input được đọc **lúc execution** có thể chỉ rerun task, không buộc đánh giá lại configuration scripts.

Phân biệt hai bộ inputs là kỹ năng quan trọng nhất khi xem report và task logs.

### 10.5. Không nhầm với Problems API report

Gradle còn có báo cáo tổng quát `build/reports/problems-report.html`. Báo cáo này không thay cho **Configuration Cache HTML report**. Khi problem có liên quan cache serialization, ưu tiên link có `configuration-cache-report.html`.

## 11. Dấu hiệu trong console và cách hiểu

| Dòng console (minh họa) | Diễn giải |
| --- | --- |
| `Calculating task graph as no cached configuration is available...` | Lần này không có entry phù hợp, phải cấu hình |
| `Configuration cache entry stored.` | Graph/state được lưu; chưa chứng minh reuse đã diễn ra |
| `Reusing configuration cache.` | Bắt đầu khôi phục entry hợp lệ |
| `Configuration cache entry reused.` | Graph/state đã được reuse |
| `Configuration cache entry discarded with N problems.` | Entry không được giữ do vấn đề tương thích |
| `cannot be reused because ... has changed` | Input cấu hình thay đổi và entry không còn hợp lệ |
| `> Task :compileJava UP-TO-DATE` | Task action không chạy; không phản ánh riêng Config Cache |
| `> Task :compileJava FROM-CACHE` | Build Cache cung cấp output; không phản ánh riêng Config Cache |

Nếu Gradle chỉ ghi `BUILD SUCCESSFUL`, vẫn phải xem cache status để kết luận cache có hit không. Một build hoàn toàn đúng có thể cần cấu hình lại vì build scripts thay đổi; cache miss không phải lúc nào cũng là lỗi.

## 12. Configuration Cache problems phổ biến

| Nhóm vấn đề | Mẫu sai | Cách sửa |
| --- | --- | --- |
| Execution-time model access | `project.name`, `project.copy`, `project.file` trong TaskAction | Đọc dữ liệu khi configuration; truyền vào managed props; dùng injected FileSystemOperations |
| Non-serializable fields | Task giữ `Project`, `Gradle`, `Settings`, `Thread`, `ClassLoader` | Loại reference, dùng Provider/BuildService phù hợp |
| Kotlin DSL script capture | `doLast` dùng top-level script `val` trực tiếp | Capture local scalar/provider trong task config hoặc dùng typed task |
| Task-to-task reference | Action lấy task khác qua `TaskProvider.get()` rồi đọc state trực tiếp | Nối output Provider sang input Property |
| External process trong config | `ProcessBuilder`/`Runtime.exec` trực tiếp lúc cấu hình | `providers.exec`, `ValueSource` hoặc task execution |
| Configuration-time file writes | Top-level `writeText(...)` | Chuyển sang TaskAction và declare @OutputFile |
| Unstable config inputs | Time, PID, per-run env value dùng để tạo graph | Stable properties/Providers, giảm configuration work |
| Unsupported listeners | Legacy build listener callbacks | Nâng plugin, dùng supported BuildService/BuildEventsListenerRegistry |
| Plugin version incompatibility | Plugin chạm Project ở execution | Update plugin hoặc sửa source + TestKit |
| Secrets captured in state | Đọc token sớm, ghi vào field | Credentials API, lazy Provider, bảo vệ cache key/storage |

Đừng coi việc thêm `@Input`/`@OutputFile` là đủ để sửa mọi lỗi: những annotations đó mô hình hóa **task snapshots**, còn Configuration Cache có ràng buộc **serialization và execution-time isolation** khác.

## 13. System properties và environment variables: cách đúng hiện hành

Đọc trực tiếp environment/system property trong **configuration phase** bằng Java/Groovy/Kotlin APIs thường được Gradle hiện hành **theo dõi như configuration input** thông qua instrumentation. Ví dụ:

~~~kotlin
val region = System.getenv("DEPLOY_REGION") ?: "dev"
~~~

là một read **eager**: đổi `DEPLOY_REGION` có thể làm Configuration Cache entry invalid và chạy lại configuration scripts. Không nên gọi đây là “luôn không được theo dõi”, vì trên Gradle hiện hành Gradle có hỗ trợ tracking direct env reads.

Cách tốt hơn khi giá trị chỉ phục vụ task execution là lazy Provider:

~~~kotlin
val regionProvider = providers.environmentVariable("DEPLOY_REGION")
    .orElse("dev")

val modeProvider = providers.systemProperty("demo.mode")
    .orElse("normal")
~~~

Sau đó wire Provider tới `Property<String>` của typed task:

~~~kotlin
tasks.register<RegionTask>("processRegion") {
    region.set(regionProvider)
    mode.set(modeProvider)
}
~~~

**Đây là mảnh minh họa**, `RegionTask`, `region`, `mode` cần được khai báo trong custom task type. Giá trị Provider được đọc khi cần; nếu chỉ phục vụ task input, đổi value có thể rerun task mà không buộc cấu hình lại toàn graph.

### 13.1. Provider API và phase matters

- `.get()` ngay top-level có thể biến value thành **configuration input**.
- Provider được giữ lazy và gắn vào task property có thể thành **task input**.
- Task action đọc từ managed property thay vì hỏi `System.getenv` rồi làm output phụ thuộc một input không khai báo.
- Nếu dùng credential/secret, tránh resolve sớm và log ra giá trị.

Không kỳ vọng một cache hit với task có output sai là thành công: first priority luôn là **build correctness**.

### 13.2. File contents tương tự

Thay vì:

~~~kotlin
val template = file("template.txt").readText()
~~~

ở configuration phase, có thể dùng:

~~~kotlin
val templateText = providers.fileContents(
    layout.projectDirectory.file("template.txt")
).asText
~~~

rồi wire vào task property. Direct file reads trong configuration phase có thể được Gradle instrument và track, nhưng sẽ invalidate **cả configuration** khi file đổi. Provider lazy hữu ích nếu thay file chỉ nên làm task chạy lại.

## 14. External processes trong configuration phase

Một anti-pattern điển hình:

~~~kotlin
val sha = ProcessBuilder(
    "git", "rev-parse", "--short", "HEAD"
).start().inputStream.bufferedReader().readText().trim()
~~~

Nếu đoạn này chạy trong configuration phase bằng API không được hỗ trợ, Gradle có thể báo problem hoặc giá trị không được theo dõi đúng trên cache hit. Đừng coi output của lệnh bên ngoài là configuration input mặc định chỉ vì Gradle đã nhìn thấy một chuỗi.

Cách phù hợp khi cần một command output Provider:

~~~kotlin
val gitSha = providers.exec {
    commandLine("git", "rev-parse", "--short", "HEAD")
}.standardOutput.asText.map { it.trim() }
~~~

Đây là mảnh Provider (chưa tự tạo task), cần executable `git` trên PATH và một Git repository. Nếu Provider được query ở configuration phase, Gradle có thể chạy external command ở mỗi lượt để kiểm tra input có đổi; nếu query lazy trong task property, scope tracking có thể khác.

Trong use case release, có thể truyền immutable CI SHA bằng:

~~~bash
./gradlew assemble -PgitSha=abc123
~~~

và dùng `providers.gradleProperty("gitSha")` để tránh lạm dụng process calls trong build scripts.

## 15. Không ghi file tại configuration time

Sai khi một build script tạo output trực tiếp:

~~~kotlin
val file = layout.buildDirectory.file("generated/status.txt")
    .get().asFile
file.parentFile.mkdirs()
file.writeText("READY\n")
~~~

Với Configuration Cache hit, build script có thể **không chạy** nên generated file có thể không được cập nhật, dù task graph vẫn hợp lệ. File output phải thuộc **task action**.

Mảnh typed task có declared output:

~~~kotlin
abstract class GenerateStatus : DefaultTask() {
    @get:OutputFile
    abstract val statusFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val target = statusFile.get().asFile
        target.parentFile.mkdirs()
        target.writeText("READY\n", Charsets.UTF_8)
    }
}

tasks.register<GenerateStatus>("generateStatus") {
    statusFile.set(
        layout.buildDirectory.file("generated/status.txt")
    )
}
~~~

Đây là phần mở rộng dùng imports đã nêu trong lab, không phải file Gradle hoàn chỉnh độc lập. Với cùng input/output, Gradle còn có thể áp up-to-date checks an toàn.

## 16. `--configuration-cache-problems=warn` và rủi ro

Mặc định:

~~~text
--configuration-cache-problems=fail
~~~

Gradle báo incompatible state, fail build và discard entry tương ứng. Để điều tra **tạm thời**, có thể:

~~~bash
./gradlew help \
  --configuration-cache \
  --configuration-cache-problems=warn \
  --console=plain
~~~

Tùy chọn tương đương trong `gradle.properties`:

~~~properties
org.gradle.configuration-cache.problems=warn
~~~

**Không nên giữ `warn` lâu dài**. Theo tài liệu Gradle hiện hành, warning mode có thể lưu cache entries dù đã có problems; khi reuse, serialized task state có thể không đầy đủ, dẫn đến output sai hoặc lỗi khó hiểu. Nó cũng không chữa các compilation/runtime failures khác.

Nếu chỉ một legacy task chưa sửa được, hãy dùng cơ chế opt-out có chọn lọc thay vì bật warn cho toàn repository.

## 17. Đánh dấu task chưa tương thích một cách có kiểm soát

Ví dụ một legacy task đã tồn tại:

~~~kotlin
tasks.named("legacyCheck") {
    notCompatibleWithConfigurationCache(
        "Task cũ truy cập Gradle model trong execution phase"
    )
}
~~~

Đây là **mảnh cấu hình**, chỉ dùng khi `legacyCheck` đã được đăng ký. Cơ chế này giúp Gradle không reuse entry sai khi invocation chứa task không tương thích. Theo Gradle hiện hành, nếu task được đánh dấu incompatible nằm trong graph, cache entry của invocation đó có thể bị **discard** sau build.

Khác biệt:

- **problems=fail**: chặn incompatibility; dùng mặc định.
- **problems=warn**: cho phép cảnh báo nhưng có nguy cơ store/reuse state không an toàn.
- **notCompatibleWithConfigurationCache(...)**: ghi nhận **task cụ thể** cần migration và tránh dùng cache entry không tương thích cho invocation chứa task ấy.

Không dùng `notCompatible...` để vô hiệu hóa toàn bộ tasks chỉ nhằm loại warnings. Ghi lý do, owner, issue để sửa và version plugin cần nâng.

### 17.1. Task publish có cần opt-out không?

Không mặc định. Task upload/publish có side effects nên **không phù hợp output Build Cache** như một pure transformation task, nhưng **vẫn có thể tương thích Configuration Cache** nếu được viết bằng Gradle APIs đúng. Đừng đánh đồng “not cacheable output” và “not Configuration Cache compatible”.

## 18. Khi cache miss liên tục: đọc Inputs và lý do invalidation

Nếu cứ chạy cùng command nhưng Gradle in:

~~~text
Calculating task graph as configuration cache cannot be reused because ...
~~~

mỗi lần, cần xem input nào thay:

1. `settings.gradle.kts`/`build.gradle.kts`/init script thay đổi.
2. Convention plugin được biên dịch lại vì source/dependencies đổi.
3. Một `System.getenv` cấu hình đọc biến PID/BUILD_NUMBER khác liên tục.
4. Build script đọc Git state/time và đưa nó vào task graph.
5. Configuration file được sinh lại ở mỗi invocation.
6. Command-line task names, arguments hay settings khác.
7. CI runner không giữ `.gradle/configuration-cache`.
8. Plugin hoặc task marked incompatible khiến entry không được giữ.

**Cách điều tra:**

~~~bash
./gradlew help --configuration-cache --info --console=plain
~~~

Đọc dòng cache invalidation và HTML report **Inputs** nếu được tạo. Chọn một input biến động; xem nó thực sự quyết định task graph hay chỉ quyết định nội dung task output. Với trường hợp sau, nên chuyển sang lazy task input Provider. Không dùng wildcard ignore tất cả inputs chỉ để tăng tỷ lệ hit.

## 19. Configuration Cache compatibility trong multi-module

Một root build có modules:

~~~text
:core
:api
:service
:integrationTest
~~~

`./gradlew help --configuration-cache` có thể pass, nhưng `./gradlew :service:test --configuration-cache` kéo thêm Test task, code generation và plugins. Một plugin custom có thể giữ `Project` trong task action chỉ được phát hiện khi task ấy nằm trong selected graph.

Quy trình:

1. Chọn developer hot paths (`:service:test`, `:service:run`).
2. Bật cache riêng trên từng request.
3. Chạy hai lần; xác nhận stored/reused.
4. Nếu fail, xem task path trong report.
5. Nâng third-party plugin hoặc sửa internal task.
6. Thử lại cùng Gradle Wrapper/JDK.
7. Mở rộng sang `check`, `assemble`, packaging/integration tests.
8. Duy trì CI gate với default `problems=fail`.

Không tự động chạy deploy/release production task chỉ để “test Configuration Cache”; nên dùng sandbox/staging hoặc fixture nếu task có side effects.

## 20. Third-party plugins và nguồn lỗi

Nếu report chỉ vào task type thuộc plugin ngoài:

- Xem plugin ID/version, Gradle Wrapper version, JDK requirements.
- Kiểm tra release notes/changelog về Configuration Cache support.
- Cập nhật plugin trong compatibility range dự án cho phép.
- Nếu chưa có fix, tạo minimal reproducible build và báo issue với maintainer.
- Nếu là plugin nội bộ trong `build-logic`, sửa task `@TaskAction`, Providers, FileSystemOperations/ExecOperations injection.
- Viết Gradle TestKit functional test để bắt incompatibilities sau khi sửa.

**Lưu ý:** Plugin version mới nhất không luôn phù hợp với Gradle Wrapper/JDK cũ. Tránh “nâng hết lên latest” nếu chưa có compatibility matrix.

### 20.1. Sử dụng Gradle TestKit

Một plugin fixture có thể dùng:

~~~java
BuildResult first = GradleRunner.create()
        .withProjectDir(testProjectDir.toFile())
        .withArguments("generateGreeting", "--configuration-cache")
        .withPluginClasspath()
        .build();

BuildResult second = GradleRunner.create()
        .withProjectDir(testProjectDir.toFile())
        .withArguments("generateGreeting", "--configuration-cache")
        .withPluginClasspath()
        .build();
~~~

Đây **chỉ là mảnh Java test**, không phải class độc lập: cần imports, Gradle TestKit/JUnit dependencies và fixture chứa plugin implementation. Ngoài kiểm tra build success, assert task outcomes và console/cache status phù hợp. Functional tests đặc biệt quan trọng vì compatibility là behavior của build graph thật, không chỉ của helper method.

## 21. Secrets và mã hóa Configuration Cache

Configuration Cache serialize reachable task state. Nếu một token/password được resolve sớm và lưu vào field, nó **có thể nằm trong cache entry**, dù task field không được annotate `@Input`.

Gradle hiện hành **mã hóa Configuration Cache trên disk** bằng key thường được quản lý dưới `GRADLE_USER_HOME`. Mã hóa giảm nguy cơ lộ dữ liệu nhưng không có nghĩa có thể chia sẻ cache công khai.

Khuyến nghị:

1. Không hard-code access tokens vào source hoặc Gradle scripts.
2. Dùng Gradle Credentials API khi cấu hình Maven/HTTP repositories.
3. Dùng Gradle user-home `gradle.properties` với quyền truy cập hạn chế để lưu secrets theo policy.
4. Dùng `providers.environmentVariable(...)` để wire runtime secret lazily thay vì `.get()` ngay trong build script.
5. Không log secrets và không lưu chúng trong public CI job artifacts.
6. Hạn chế quyền truy cập cả `.gradle/configuration-cache` và encryption key trong `GRADLE_USER_HOME`.
7. Không upload/cache directory cho người dùng hoặc môi trường không cùng trust boundary.

### 21.1. `GRADLE_ENCRYPTION_KEY`

Trong CI/shared environments, Gradle có thể dùng `GRADLE_ENCRYPTION_KEY` chứa Base64 AES key để decrypt/reuse entry giữa các agents. Key phải ổn định và được bảo vệ đúng secret store; nếu key đổi, cache cũ có thể không reuse được.

**Không in key ra terminal log**, không commit vào Git và không gửi key cho những build không tin cậy.

### 21.2. Bảo mật khác correctness

Encryption không chứng minh plugin code là an toàn; nó không thay dependency verification, signature checks hay security scanning. Configuration Cache tập trung vào build performance/correctness của task graph, không phải bảo vệ chống mã độc.

## 22. Configuration Cache trong CI và IDE

### 22.1. CI ephemeral

Nếu runner mới mỗi job, `.gradle/configuration-cache` không được giữ nên **miss là bình thường**. CI vẫn hữu ích để phát hiện incompatible tasks/plugin updates; cache hits chỉ có nếu thiết lập persisting/restoring cache và encryption key an toàn.

Không bật `--configuration-cache-problems=warn` trên CI chỉ để giữ green status. CI nên thất bại khi có regression về compatibility.

### 22.2. IDE task run khác project sync

IDE có thể delegate task execution cho Gradle và được hưởng Configuration Cache khi cấu hình bật. Nhưng IDE project import/sync không nhận lợi ích giống chạy Gradle tasks. Không dùng thời gian project sync đơn lẻ để đánh giá hiệu quả của Configuration Cache.

### 22.3. Benchmark đúng

So sánh cùng Gradle Wrapper/JDK/daemon state, module/task requests, dependency cache, Build Cache và workspace inputs. Ghi separately:

- Cache entry stored hay reused.
- Task outcomes UP-TO-DATE/FROM-CACHE/executed.
- Configuration duration và total build duration.
- Cùng build/cache warm-up state.
- Số lượng problems/cache invalidations.

Đừng quy toàn bộ speedup từ lượt 1 tải Maven dependencies sang lượt 2 vào Configuration Cache.

## 23. Strict mode, read-only mode và tùy chọn nâng cao

Một số Gradle versions hiện hành có **strict preview**:

~~~kotlin
// settings.gradle.kts — chỉ khi Gradle Wrapper hỗ trợ:
enableFeaturePreview("STABLE_CONFIGURATION_CACHE")
~~~

Nó tăng validation/warnings cho một số APIs cũ, chẳng hạn listeners, để chuẩn bị cho behavior tương lai. **Không bật mù quáng trên Gradle Wrapper cũ**.

Tùy chọn read-only có thể được hỗ trợ:

~~~bash
./gradlew help \
  --configuration-cache \
  -Dorg.gradle.configuration-cache.read-only=true
~~~

Read-only chỉ nên dùng khi có cache restore strategy rõ, không dùng cho compatibility QA: khi cache miss nó có thể bỏ công đoạn serialize, khiến execution-time problems chưa được phát hiện.

Tùy chọn parallel storing ở một số versions:

~~~bash
./gradlew help \
  --configuration-cache \
  -Dorg.gradle.configuration-cache.parallel=true
~~~

Đây là tùy chọn incubating; có thể phơi bày races trong build logic chưa thread-safe. Chỉ thử sau khi chế độ thường chạy ổn.

Có thể giới hạn số problems trong session chẩn đoán:

~~~bash
./gradlew help \
  --configuration-cache \
  --configuration-cache-problems=warn \
  -Dorg.gradle.configuration-cache.max-problems=5
~~~

Đây không phải policy để bỏ qua errors, mà chỉ phục vụ thu thập và phân loại issues khi cần.

## 24. Xóa Configuration Cache khi nào?

Thông thường Gradle tự invalidate entry; **không cần xóa hằng ngày**. Chỉ xóa cache khi nghi corrupt state, muốn cold-run để debug, hoặc theo yêu cầu release notes.

Thư mục cần nhắm:

~~~text
<root-build>/.gradle/configuration-cache/
~~~

Linux/macOS, sau khi kiểm tra đang ở đúng project root:

~~~bash
rm -rf .gradle/configuration-cache
~~~

PowerShell:

~~~powershell
Remove-Item -LiteralPath .gradle\configuration-cache -Recurse -Force
~~~

Chỉ xóa project-local Config Cache directory; không xóa toàn bộ `~/.gradle`/`GRADLE_USER_HOME` tùy tiện. Thao tác xóa chỉ reset state, **không sửa source code** gây incompatibility, nên chạy lại vẫn có thể fail.

## 25. Phân biệt các loại lỗi liên quan

| Tình huống | Đọc ở đâu? | Hành động |
| --- | --- | --- |
| `Task.project at execution time` | Configuration Cache HTML report | Sửa typed task/Provider wiring |
| Cache entry discarded | Config Cache report/console | Sửa incompatibilities |
| Cache entry miss liên tục | Console invalidation reason + Inputs | Tìm unstable configuration input |
| `compileJava` `UP-TO-DATE` hay không | Task status/`--info` | Kiểm tra inputs/outputs |
| `FROM-CACHE` | Build Cache report/log | Kiểm tra task cacheable/cache key |
| JUnit test failed | Test report | Sửa logic/test |
| Deprecated Gradle API warning | General Gradle log/Problems API | Lập kế hoạch nâng API |
| `build/reports/problems-report.html` | Problems API report | Tách khỏi Config Cache report |
| CI key/cache unavailable | CI caches/secrets logs (được bảo vệ) | Kiểm tra cache persistence/encryption key |

Báo cáo `problems-report.html` khác với `configuration-cache-report.html`. Đừng đổ mọi Gradle warning cho Configuration Cache.

## 26. Lộ trình adoption cho một team

1. Pin Gradle Wrapper và JDK; xác nhận baseline `help`, `test`, `check`.
2. Chạy `help --configuration-cache` trên module/root phù hợp.
3. Chạy representative developer task, ví dụ `:service:test`.
4. Nếu failure, mở HTML report và phân loại Grouped by message/task.
5. Loại bỏ Project/Gradle model access trong task actions.
6. Thay task fields bằng managed Properties/Providers.
7. Chuyển configuration-time file writes/process calls sang APIs được hỗ trợ.
8. Sửa untracked/unstable config inputs.
9. Nâng third-party plugins hoặc tạo issue minimal repro.
10. Tạm opt-out task legacy riêng khi chưa thể sửa; không giữ `warn` lâu dài.
11. Chạy lại cùng request hai lần để xác minh stored/reused.
12. Kiểm tra output/task/test behavior sau refactor.
13. Dùng Gradle TestKit cho internal plugin regression tests.
14. Chỉ sau khi pass mới bật project-wide property.
15. CI dùng default `problems=fail` và lưu report khi fail.
16. Bảo vệ cache directory và encryption key.
17. Khi nâng Gradle, chạy compatibility matrix/QA lại.
18. Theo dõi tốc độ và cache hit/miss bằng số liệu thực, không bằng suy đoán.

## 27. Bài tập và đáp án

**Câu 1.** Bật Configuration Cache cho một lệnh thế nào?

**Đáp án:** `./gradlew test --configuration-cache`.

**Câu 2.** Property để bật mặc định?

**Đáp án:** `org.gradle.configuration-cache=true` trong `gradle.properties`.

**Câu 3.** `entry stored` có đồng nghĩa cache hit?

**Đáp án:** Không. Nó có nghĩa entry đã được lưu; cần chạy lại cùng task request để có cơ hội reuse.

**Câu 4.** Configuration Cache reused có khiến `compileJava` tự UP-TO-DATE?

**Đáp án:** Không. Task inputs/outputs có thể đổi và compiler vẫn chạy.

**Câu 5.** Cache report file có tên gì?

**Đáp án:** `configuration-cache-report.html`, đường dẫn chính xác Gradle in trong console, thường dưới `build/reports/configuration-cache/.../`.

**Câu 6.** Grouped by message khác Grouped by task?

**Đáp án:** Grouped by message gom lỗi giống nhau; Grouped by task giúp tìm task paths/fields và owner của lỗi.

**Câu 7.** Vì sao `doLast { logger.lifecycle(project.name) }` không tốt?

**Đáp án:** Task action truy cập live Project model tại execution time, không phù hợp Configuration Cache; hãy truyền String qua task property hoặc capture local scalar từ configuration.

**Câu 8.** `@Input` có tự làm task CC-compatible không?

**Đáp án:** Không. Configuration Cache còn serialize reachable task state và cấm dùng một số Gradle model objects trong task actions.

**Câu 9.** `@Internal` có loại field khỏi Configuration Cache serialization không?

**Đáp án:** Không; @Internal chỉ liên quan task input/output fingerprinting, không phải một cơ chế exclude all reachable state.

**Câu 10.** `System.getenv` trực tiếp trong configuration luôn không được Gradle theo dõi?

**Đáp án:** Không. Gradle hiện hành có tracking cho direct environment reads khi cấu hình, nhưng nó là **eager configuration input**, khiến entry invalid nếu giá trị đổi; lazy Provider task input thường phù hợp hơn.

**Câu 11.** Khi nào nên dùng `notCompatibleWithConfigurationCache`?

**Đáp án:** Cho task legacy cụ thể cần thời gian sửa; giúp tránh reuse state không tương thích và ghi lại lý do.

**Câu 12.** Vì sao không giữ `--configuration-cache-problems=warn` lâu dài?

**Đáp án:** Entry có problems có thể được lưu/reuse với state không đầy đủ và gây kết quả sai hoặc lỗi khó chẩn đoán.

**Câu 13.** `--no-build-cache` có tắt Configuration Cache không?

**Đáp án:** Không. Hai cơ chế độc lập.

**Câu 14.** Vì sao `clean generateGreeting` không có cùng task request với `generateGreeting`?

**Đáp án:** Task graph khác vì có thêm clean; cache entry có thể được lưu riêng.

**Câu 15.** Java `GreetingPrinter` in gì với default person Lan?

**Đáp án:** `Xin chào, Lan!` kèm một newline.

**Câu 16.** Đổi `-Pperson=Mai` sẽ tạo output gì?

**Đáp án:** File `build/generated/greeting.txt` chứa `Xin chào, Mai!`.

**Câu 17.** CI ephemeral cache miss có nghĩa plugin hỏng?

**Đáp án:** Không. Có thể đơn giản không restore cache state hoặc encryption key.

**Câu 18.** Vì sao không viết generated file tại top-level build.gradle.kts?

**Đáp án:** Trên cache hit build script có thể không được chạy, làm file vắng/stale; phải tạo output trong TaskAction đã khai báo.

**Câu 19.** Xóa `.gradle/configuration-cache` có sửa lỗi Project reference trong task action không?

**Đáp án:** Không. Nó chỉ xóa entry; source logic vẫn sai và có thể fail lại.

**Câu 20.** `GRADLE_ENCRYPTION_KEY` dùng làm gì?

**Đáp án:** Cung cấp key cho Configuration Cache encryption/reuse trong shared environments theo supported Gradle configuration; phải giữ bí mật và nhất quán.

**Câu 21.** `providers.exec` có phải lúc nào cũng chạy đúng một lần?

**Đáp án:** Không. Provider được query ở configuration phase có thể được đánh giá khi Gradle kiểm tra config inputs ở các builds sau; đừng giả định external command sẽ không chạy khi cache hit.

**Câu 22.** `help --configuration-cache` pass có đủ chứng minh task publish plugin tương thích không?

**Đáp án:** Không. Phải thử representative task graph; `help` không nhất thiết kéo custom tasks vào graph.

## 28. Checklist ngắn khi đọc một report mới

- Tìm `See the complete report at file:///.../configuration-cache-report.html`.
- Xem entry `stored`, `reused`, `discarded` và số problems.
- Lọc Grouped by message để tìm lỗi lặp.
- Lọc Grouped by task để tìm owner và task type.
- Mở object graph/stack trace đến field/method gây problem.
- Xem Inputs tab nếu cache invalid nhiều lần.
- Xác định lỗi thuộc task action, non-serializable field, plugin, external process hay untracked input.
- Sửa nguồn và chạy lại **cùng task request**.
- Xác minh entry stored/reused **không có problems**.
- Xác minh task outputs, Java/test behavior không đổi.
- Không dùng `warn` để che lỗi.
- Không trộn `UP-TO-DATE` với Config Cache reuse.
- Không commit cache directory hoặc secrets.

## 29. Tài liệu chính thức

1. Gradle — Configuration Cache: https://docs.gradle.org/current/userguide/configuration_cache.html
2. Gradle — Enabling and Configuring: https://docs.gradle.org/current/userguide/configuration_cache_enabling.html
3. Gradle — Adopting the Configuration Cache: https://docs.gradle.org/current/userguide/configuration_cache_adoption.html
4. Gradle — Debugging and Troubleshooting: https://docs.gradle.org/current/userguide/configuration_cache_debugging.html
5. Gradle — Configuration Cache Requirements: https://docs.gradle.org/current/userguide/configuration_cache_requirements.html
6. Gradle — Configuration Cache Status: https://docs.gradle.org/current/userguide/configuration_cache_status.html
7. Gradle — Build Cache: https://docs.gradle.org/current/userguide/build_cache.html
8. Gradle — Build Environment: https://docs.gradle.org/current/userguide/build_environment.html
9. Gradle — Directory Layout and Caches: https://docs.gradle.org/current/userguide/directory_layout.html
10. Gradle — Command-Line Interface: https://docs.gradle.org/current/userguide/command_line_interface.html
11. Gradle — Gradle TestKit: https://docs.gradle.org/current/userguide/test_kit.html
12. Gradle — Properties and Providers: https://docs.gradle.org/current/userguide/properties_providers.html
13. Gradle — Custom Task Development: https://docs.gradle.org/current/userguide/implementing_custom_tasks.html

**Lưu ý phiên bản:** Các URL `/current/` phản ánh tài liệu Gradle hiện hành, không bảo đảm mọi tùy chọn incubating/strict mode có mặt trên Gradle Wrapper cũ. Đoạn console/HTML path chỉ mang tính minh họa và có thể thay đổi. Khi làm việc thực tế, luôn dùng **Wrapper version cố định, report link thật và representative tasks** để đánh giá compatibility.

**Kết luận:** Bật `--configuration-cache` chỉ là bước đầu. Điều quan trọng là **đọc report, loại bỏ live Gradle model access trong task execution, model data qua managed properties và kiểm thử reuse cùng build correctness**. Configuration Cache giúp tăng tốc configuration phase, nhưng chỉ hữu ích bền vững khi build logic an toàn và kết quả không sai lệch trên cache hit.
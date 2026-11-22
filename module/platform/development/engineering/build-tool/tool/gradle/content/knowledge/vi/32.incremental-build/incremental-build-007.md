# Phân biệt thay đổi cần chạy lại toàn bộ với thay đổi có thể xử lý tăng dần trong Gradle

## 1. Vì sao bài toán này quan trọng?

Trong một dự án Java, việc thay đổi một file không đồng nghĩa phải build lại toàn bộ repository. Nếu chỉ thay một resource, có thể không cần compile lại Java. Nếu chỉ sửa implementation của một method mà giữ nguyên public ABI, module phụ thuộc có thể không cần biên dịch lại. Với một task chuyển đổi hàng nghìn file, nếu chỉ một file đổi, ta có thể muốn **chỉ xử lý file đó**.

Tuy nhiên, cũng có những thay đổi **không thể cập nhật an toàn chỉ từ phần khác biệt nhỏ**. Khi thuật toán xử lý đổi, tham số chung đổi, outputs cũ bị xóa/sửa, hoặc Gradle không còn lịch sử của lượt trước, task có thể phải xử lý **tất cả inputs**. Nếu dữ liệu sinh ra phụ thuộc đồng thời vào nhiều files, xử lý riêng từng file thậm chí có thể tạo output sai.

Chìa khóa là phân biệt ba cấp độ:

1. **Task có chạy không?** Gradle kiểm tra inputs/outputs; nếu không đổi có thể bỏ qua task (`UP-TO-DATE`).
2. **Nếu task chạy, chạy toàn bộ hay tăng dần?** Custom task có thể nhận `InputChanges`, từ đó chỉ xử lý files `ADDED`, `MODIFIED`, `REMOVED` nếu history đủ tin cậy.
3. **Nếu một Java compile task chạy, class nào cần compile lại?** Gradle Java incremental compiler và compile avoidance có cơ chế riêng dựa trên class dependencies và public ABI.

Bài học tập trung vào quyết định đúng **“khi nào bắt buộc xử lý lại toàn bộ và khi nào chỉ cần xử lý phần thay đổi”**. “Toàn bộ” ở đây thường là **tất cả inputs của một task**, không mặc định nghĩa toàn bộ modules, toàn bộ Gradle build hoặc mọi tests.

## 2. Bốn trạng thái cần nhận diện trước

| Trạng thái/khái niệm | Task action có thực thi? | Công việc với inputs | Cần hiểu |
| --- | --- | --- | --- |
| `UP-TO-DATE` | Không | Không xử lý | Inputs/outputs và history được xem là không thay đổi |
| `FROM-CACHE` | Không chạy task action | Khôi phục outputs cache | Có kết quả cache hợp lệ với cache key |
| **Incremental execution** | Có | Chỉ inputs thay đổi | Task có incremental action và history so sánh hợp lệ |
| **Non-incremental/full execution** | Có | Xử lý tất cả inputs liên quan | Không thể tin vào delta/previous outputs |
| `NO-SOURCE` | Không (tùy task) | Không có source phù hợp | Ví dụ JavaCompile không có source |
| `SKIPPED` | Không (theo điều kiện) | Không xử lý | Có thể do `onlyIf`/cơ chế skip, không đồng nghĩa UP-TO-DATE |
| `FAILED` | Có thể đã chạy một phần | Công việc không hoàn tất | Build failed; state sau lỗi cần đánh giá lại |

**Đừng nhầm:**

- `UP-TO-DATE` **khác** “task chạy tăng dần”. UP-TO-DATE nghĩa là action **không chạy**.
- `FROM-CACHE` **khác** incremental processing. Gradle lấy outputs đã có, action **không chạy**.
- “Non-incremental” **không mặc định** là Gradle chạy lại tất cả tasks của cả build. Nó có thể chỉ là một task cần làm lại toàn bộ các file input.
- “Task được thực thi” **không đủ** để suy nó có xử lý mọi file không. Cần biết task có `InputChanges` và nhánh `isIncremental` nào được dùng.
- `clean build` là **một lệnh yêu cầu xóa outputs rồi build**, khác cơ chế tự động so sánh input/output của Gradle.

### 2.1. Một sơ đồ quyết định

~~~text
Task được yêu cầu trong task graph
                |
                v
Có đủ input/output model, history/cache để kiểm tra?
                |
                +-- Không / outputs invalid --> task phải execute
                |                                  |
                |                                  v
                |                         InputChanges.isIncremental?
                |                            |             |
                |                          false          true
                |                            |             |
                |                            v             v
                |                     Xử lý toàn bộ   Chỉ changed inputs
                |
                +-- Có
                    |
                    +-- Inputs+outputs unchanged --> UP-TO-DATE
                    |
                    +-- Cache key hit, có thể restore --> FROM-CACHE
                    |
                    +-- Có thay đổi --> task execute
                                         |
                                         +--> incremental nếu có lịch sử & đủ điều kiện
                                         +--> full nếu không
~~~

Đây là sơ đồ khái niệm. Gradle có nhiều điều kiện bổ sung như task validation, cacheability, các điều kiện skip, error state, file system snapshots và build cache; quyết định cụ thể phải quan sát `--info`/task report.

## 3. Hai nghĩa khác nhau của từ “incremental”

Gradle dùng “incremental” ở ít nhất hai bối cảnh:

**A. Incremental build / up-to-date checking:** bỏ qua **cả task** khi inputs và outputs không đổi. Một task có `@Input`/`@OutputFile` đầy đủ, không có `InputChanges`, vẫn có thể là `UP-TO-DATE` ở lượt sau.

**B. Incremental task execution:** khi task **phải chạy** nhưng chỉ vài input files đổi, task action nhận `InputChanges` và xử lý từng sự kiện `ADDED`/`MODIFIED`/`REMOVED`. Để có khả năng này, custom task cần khai báo đúng incremental input file property và action hỗ trợ delta.

Ví dụ:

~~~text
Lượt 1: A.txt, B.txt có sẵn
   -> task chưa có history
   -> FULL: xử lý A và B

Lượt 2: không sửa gì
   -> UP-TO-DATE
   -> task action không chạy

Lượt 3: sửa A.txt
   -> INCREMENTAL: xử lý chỉ A

Lượt 4: xóa B.txt
   -> INCREMENTAL: xóa output ứng với B

Lượt 5: đổi tham số chung 'prefix'
   -> FULL: xử lý A (và files còn lại) với thuật toán mới

Lượt 6: không sửa gì
   -> UP-TO-DATE
~~~

**C. Incremental Java compilation** lại là tối ưu riêng của `JavaCompile`: nó phân tích quan hệ giữa source/classes và ABI, quyết định class files nào cần compile lại. Đây không phải đồng nghĩa mỗi `.java` sửa thì compiler chỉ compile đúng một file; những classes bị ảnh hưởng về type, constant hoặc annotation processing cũng có thể cần xử lý.

## 4. Cơ sở quyết định: task inputs, outputs và lịch sử

Gradle ghi nhận **task inputs** (dữ liệu ảnh hưởng kết quả) và **task outputs** (kết quả được tạo). Các thông tin này cho phép Gradle nhận biết thay đổi sau những lượt chạy thành công.

| Loại | Ví dụ | Mô hình hóa |
| --- | --- | --- |
| Input scalar | prefix, format, optimization flag | `@Input Property<String>` |
| File input đơn | schema.json, template.txt | `@InputFile RegularFileProperty` |
| Directory input | Tập *.txt để chuyển đổi | `@InputDirectory DirectoryProperty` |
| Tập file inputs | sources, classpath | `@InputFiles ConfigurableFileCollection` |
| Output file | generated.txt | `@OutputFile RegularFileProperty` |
| Output directory | build/normalized | `@OutputDirectory DirectoryProperty` |
| Tài nguyên không tham gia output | Log level mang tính trình bày | `@Internal` hoặc `@Console` khi thực sự phù hợp |
| Classpath | compiler/plugin libraries | `@Classpath`/`@CompileClasspath` theo semantics |
| File normalization | relative path/content cần coi là giống | `@PathSensitive(PathSensitivity.RELATIVE)` |

Nếu tác vụ tạo output từ `prefix` nhưng không khai báo `prefix` là input, Gradle có thể coi output cũ là hợp lệ khi giá trị prefix đổi. Ngược lại, nếu đưa timestamp/random/log-level không ảnh hưởng output vào `@Input`, task có thể bị rerun không cần thiết.

**Nguyên tắc:** mọi yếu tố **có thể làm thay đổi nội dung/ý nghĩa output** phải được khai báo, còn điều không ảnh hưởng kết quả không nên làm invalidation một cách tùy tiện.

### 4.1. Không nên giả định Gradle đọc mọi file trên máy

Gradle chỉ có thể so sánh những inputs được **task/model khai báo**. Một `@TaskAction` tự đọc `System.getenv`, Git working tree, network response hoặc một file ngoài property mà không khai báo sẽ tạo **hidden input**. Khi hidden input đổi, Gradle có thể vẫn báo UP-TO-DATE hoặc trả cache sai.

### 4.2. Ít nhất một output để skip theo up-to-date checks

Một task chỉ in console, gửi email hoặc gọi external API không có output artifact tin cậy thường vẫn chạy khi được yêu cầu. Gradle chỉ có thể bỏ qua work an toàn khi có outputs/state được mô hình hóa đúng. Đừng tạo một “flag file” giả để che side effect; file đó không chứng minh API đã được gọi thành công hoặc external state còn đúng.

## 5. Những trường hợp chỉ cần xử lý tăng dần

Với custom task biến đổi mỗi input file thành một output file tương ứng, xử lý delta là hợp lý **nếu kết quả của một file không phụ thuộc các file khác**.

Ví dụ:

- Sửa `a.txt`, `b.txt` và `c.txt` không đổi: chỉ build lại `a.txt` output.
- Thêm `d.txt`: chỉ tạo output ứng với `d.txt`.
- Xóa `b.txt`: phải xóa output từng được sinh từ `b.txt` để tránh artifact stale.
- Đổi tên một file: thường tương đương REMOVED đường cũ + ADDED đường mới; phải cập nhật mapping.
- Sửa file mà nội dung normalized không đổi nhưng fingerprint file input đổi: task có thể vẫn chạy; đó là hợp đồng input semantics.
- Files thay đổi ở một thư mục con nhưng giữ relative paths: task chỉ xử lý affected files nếu path normalization đúng.

Điều kiện an toàn:

1. File input được khai báo `@Incremental` hoặc `@SkipWhenEmpty` trên property phù hợp.
2. Action nhận một tham số `InputChanges` và truy vấn `getFileChanges(...)`.
3. File output từng input có thể xác định từ relative path của input.
4. Khi nhận REMOVED, task biết file output nào phải xóa.
5. Các tham số chung khác vẫn giữ nguyên (hoặc task có logic đặc biệt được thiết kế để xử lý thay đổi đó chính xác).
6. Outputs trước đó còn hợp lệ và Gradle có lịch sử tương thích.
7. Không có hidden inputs hoặc side effects làm incremental assumption sai.

Nếu một output là **báo cáo tổng hợp của tất cả input files**, việc xử lý chỉ `a.txt` có thể không đủ: cần cập nhật/recompute phần aggregate liên quan, hoặc full recompute nếu không lưu cấu trúc state để điều chỉnh incremental an toàn.

## 6. Những trường hợp cần chạy lại toàn bộ input của task

Tài liệu Gradle mô tả các trường hợp phổ biến làm `InputChanges.isIncremental` là `false`:

| Tình huống | Vì sao không tin được delta? | Hành vi thường gặp |
| --- | --- | --- |
| Lần chạy đầu, chưa có history | Không có baseline so sánh | Báo tất cả files là `ADDED` |
| Thay Gradle version, không tái dùng task execution history | Format/semantics state khác | Full task processing |
| Chạy `--rerun-tasks` | Người dùng yêu cầu bypass up-to-date | Full, tất cả file inputs báo ADDED |
| Scalar `@Input` thay đổi | Không biết scalar ảnh hưởng file outputs nào | Full, dù files không đổi |
| File input không annotate `@Incremental` thay đổi | Không thể yêu cầu delta cho property ấy | Full |
| Output file bị xóa/sửa ngoài Gradle | Output trước không còn đáng tin | Full |
| `upToDateWhen` điều kiện trả `false` | Task bị ép out-of-date | Full theo Gradle incremental semantics |
| Task implementation/action/version thay đổi | Logic cũ có thể không tạo cùng output | Task invalidation, thường xử lý lại toàn bộ |
| `clean` xóa output/history liên quan | Không còn outputs để cập nhật | Lần chạy sau thường full |
| Task trước failed hoặc state không hợp lệ | Không có baseline hoàn chỉnh đáng tin | Full/khôi phục theo Gradle engine |

**“Full” ở đây không có nghĩa** các project không liên quan phải recompile hoặc tests khác cũng chạy. Task generator có thể full trên 100 file, còn task JavaCompile ở module khác vẫn UP-TO-DATE.

### 6.1. Khi full, getFileChanges trả gì?

Nếu `isIncremental == false`, Gradle sẽ báo **mọi input file của incremental property** như `ChangeType.ADDED` cho task action. Điều này cho phép cùng code path tái tạo đầy đủ output. Gradle cũng xử lý loại bỏ previous outputs trước khi non-incremental task action chạy theo cơ chế được tài liệu hóa.

Vì vậy **không** tự tưởng rằng “FULL” trả về `MODIFIED` cho tất cả files, hoặc mỗi file cũ đều phát `REMOVED`. Với Gradle input change API, non-incremental processing biểu diễn tất cả current inputs như ADDED.

### 6.2. Không tự xóa output directory ở mỗi lượt

Nếu task action luôn xóa toàn bộ output directory ngay cả khi `isIncremental == true`, các files không đổi sẽ mất output nhưng không được tái tạo vì task chỉ nhận changed files. Đó là một bug rất nguy hiểm.

Trong incremental branch:

- ADDED/MODIFIED → ghi/tạo lại output tương ứng.
- REMOVED → xóa output tương ứng.
- Unchanged → giữ output cũ.

Trong full branch, Gradle đã có cơ chế invalidation/cleanup; task có thể tái tạo toàn bộ outputs. Không áp dụng cleanup tổng quát phá trạng thái incremental.

## 7. Demo chạy được: Java 17 + custom Gradle task xử lý *.txt tăng dần

Ta xây một project nhỏ:

- `inputs/a.txt` và `inputs/b.txt` là hai input files.
- Custom task `normalizeTexts` chuyển text thành chữ hoa bằng `Locale.ROOT` và thêm `prefix`.
- Mỗi input `name.txt` được map sang `build/normalized/name.txt`.
- `@Incremental` + `InputChanges` giúp phân biệt full và incremental execution.
- Java app `demo.Main` đọc `build/normalized/a.txt` và in kết quả.
- Application plugin tạo `run`; task `run` phụ thuộc `normalizeTexts` để output có trước.

**Không dùng random, thời gian hệ thống hoặc external services.** Vì vậy có thể kiểm tra chuẩn xác.

### 7.1. Điều kiện

- JDK **17+** hoặc toolchain Java 17 có thể provision theo policy dự án.
- Gradle Wrapper phù hợp JDK/Gradle version, đặt ở root cùng `settings.gradle.kts`.
- Một thư mục dự án có thể ghi outputs trong `build/`.
- Không cần Docker, database, Plugin Portal hay Maven Central để build source chính (Application plugin được Gradle cung cấp).
- Dùng Kotlin DSL `build.gradle.kts`; không dùng chung `build.gradle` Groovy cho cùng demo.

### 7.2. Cấu trúc

~~~text
incremental-text-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── inputs/
│   ├── a.txt
│   └── b.txt
├── src/main/java/demo/Main.java
└── build/                      (Gradle tạo)
    └── normalized/
        ├── a.txt
        └── b.txt
~~~

Wrapper scripts/JAR là files thật của Gradle Wrapper; không tự tạo file giả. `build/` không nên được commit. Input directory `inputs/` phải tồn tại vì task dùng `@InputDirectory` bắt buộc.

### 7.3. settings.gradle.kts

~~~kotlin
rootProject.name = "incremental-text-demo"
~~~

### 7.4. Tạo hai input files

**File `inputs/a.txt`:**

~~~text
one
~~~

**File `inputs/b.txt`:**

~~~text
two
~~~

Trong demo, hai files được lưu bằng UTF-8, mỗi file một dòng chữ ASCII thường. Có thể có ký tự newline cuối; Java app ở phần dưới gọi `stripTrailing()` để stdout ổn định. Không nhầm nội dung text file với syntax Markdown.

### 7.5. Toàn bộ build.gradle.kts

~~~kotlin
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.util.Locale

import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Incremental
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.work.ChangeType
import org.gradle.work.FileType
import org.gradle.work.InputChanges

plugins {
    application
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.Main")
}

@CacheableTask
abstract class NormalizeTextTask : DefaultTask() {
    @get:Incremental
    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val inputDir: DirectoryProperty

    @get:OutputDirectory
    abstract val outputDir: DirectoryProperty

    @get:Input
    abstract val prefix: Property<String>

    @TaskAction
    fun normalize(changes: InputChanges) {
        val root = outputDir.get().asFile.toPath()
            .toAbsolutePath().normalize()
        val marker = prefix.get()

        // Ở lần full, Gradle báo toàn bộ input files là ADDED.
        logger.lifecycle(
            "MODE: " +
                if (changes.isIncremental) "INCREMENTAL" else "FULL"
        )

        Files.createDirectories(root)

        for (change in changes.getFileChanges(inputDir)) {
            if (change.fileType == FileType.DIRECTORY) {
                continue
            }

            val relative = change.normalizedPath
            val target = root.resolve(relative).normalize()
            require(target.startsWith(root)) {
                "Input path escapes output directory: " + relative
            }

            when (change.changeType) {
                ChangeType.REMOVED -> {
                    Files.deleteIfExists(target)
                    logger.lifecycle("REMOVED: " + relative)
                }
                ChangeType.ADDED, ChangeType.MODIFIED -> {
                    Files.createDirectories(target.parent)

                    val text = Files.readString(
                        change.file.toPath(),
                        StandardCharsets.UTF_8
                    )
                    val output = marker + text.uppercase(Locale.ROOT)

                    Files.writeString(
                        target,
                        output,
                        StandardCharsets.UTF_8
                    )
                    logger.lifecycle(
                        change.changeType.name + ": " + relative
                    )
                }
            }
        }
    }
}

val normalizeTexts = tasks.register<NormalizeTextTask>(
    "normalizeTexts"
) {
    group = "generation"
    description = "Normalize only changed input text files"

    inputDir.set(layout.projectDirectory.dir("inputs"))
    outputDir.set(layout.buildDirectory.dir("normalized"))
    prefix.convention(
        providers.gradleProperty("normalizePrefix").orElse("NORM: ")
    )
}

// Application 'run' thực thi Java Main, vốn đọc output đã sinh.
// Main không import task type; prerequisite cần khai báo tại build graph.
tasks.named("run") {
    dependsOn(normalizeTexts)
}
~~~

**Chú ý về cú pháp:** Đây là một file Kotlin DSL độc lập. Các annotations đặt trên **getter** bằng `@get:...`. `InputChanges` phải đến từ `org.gradle.work`; `ChangeType`/`FileType` cũng từ package này. `@CacheableTask` thuộc `org.gradle.api.tasks`. `application` tạo task `run` và `clean` thông qua Application/Base/Java plugins.

### 7.6. Java source Main.java

**File `src/main/java/demo/Main.java`:**

~~~java
package demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws IOException {
        Path path = args.length == 0
                ? Path.of("build", "normalized", "a.txt")
                : Path.of(args[0]);

        String result = Files.readString(
                path, StandardCharsets.UTF_8
        ).stripTrailing();

        System.out.println(result);
    }
}
~~~

Java 17 `Files.readString` và `stripTrailing` được hỗ trợ. `Main` chỉ đọc file output, không tự build. Khi chạy qua Gradle `run`, task dependency đảm bảo `normalizeTexts` chạy/khôi phục output trước; khi chạy `javac/java` trực tiếp, người dùng cần đảm bảo file đã có.

**Stdout chính xác cho file `a.txt` gốc với prefix mặc định:**

~~~text
NORM: ONE
~~~

Đó là **stdout của Java Main**, không phải toàn bộ Gradle console bao gồm task statuses.

### 7.7. Chạy Gradle và quan sát hai output files

Linux/macOS:

~~~bash
./gradlew normalizeTexts --no-build-cache --console=plain
./gradlew -q run --no-build-cache
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat normalizeTexts --no-build-cache --console=plain
.\gradlew.bat -q run --no-build-cache
~~~

Sau một lượt full đầu tiên, nội dung dự kiến:

**`build/normalized/a.txt`:**

~~~text
NORM: ONE
~~~

**`build/normalized/b.txt`:**

~~~text
NORM: TWO
~~~

**Java Main in:**

~~~text
NORM: ONE
~~~

Task logs ở lần full đầu có các sự kiện `MODE: FULL`, `ADDED: a.txt`, `ADDED: b.txt`, nhưng **thứ tự events không phải contract bất biến**. Nếu task đã có history từ lượt build trước thì có thể không là FULL; dùng `clean` khi cần tái hiện first run ở workspace demo.

### 7.8. Chạy trực tiếp Java 17 bằng javac/java

Đầu tiên chạy `normalizeTexts` để có output. Sau đó từ root:

Linux/macOS:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
    -d out src/main/java/demo/Main.java
java -cp out demo.Main
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out src\main\java\demo\Main.java
java -cp out demo.Main
~~~

**Stdout chính xác khi file đầu vào chưa đổi:**

~~~text
NORM: ONE
~~~

Lệnh `javac/java` chỉ kiểm chứng Java app và file output đã có. Nó **không chạy custom Gradle task, không đo InputChanges và không kích hoạt incremental build**. File `out/` là local compilation output do javac tự tạo.

## 8. Giải thích chi tiết task Kotlin DSL

### 8.1. @InputDirectory + @Incremental

~~~kotlin
@get:Incremental
@get:InputDirectory
@get:PathSensitive(PathSensitivity.RELATIVE)
abstract val inputDir: DirectoryProperty
~~~

`@InputDirectory` cho Gradle biết thư mục có file inputs. `@Incremental` cho phép truy vấn delta của property đó qua `getFileChanges(inputDir)`. `PathSensitivity.RELATIVE` coi relative path trong input root là yếu tố nhận diện — file `sub/a.txt` khác `a.txt` — nhưng không bắt buộc absolute directory path giống nhau giữa workspaces.

Đừng dùng `PathSensitivity.NONE` khi file name/relative path quyết định output path, vì file rename và file identity có thể khó mô hình hóa chính xác. Với `NONE`, Gradle có thể biểu diễn một thay đổi thành cặp `ADDED` + `REMOVED` thay vì `MODIFIED`.

### 8.2. @OutputDirectory

~~~kotlin
@get:OutputDirectory
abstract val outputDir: DirectoryProperty
~~~

Đây là directory task sở hữu. Nó nên ở dưới `layout.buildDirectory` để Gradle quản lý output và tránh ghi vào source tree. Không có task thứ hai ghi đè cùng directory khi muốn giữ incremental/cache đúng.

### 8.3. Scalar @Input

~~~kotlin
@get:Input
abstract val prefix: Property<String>
~~~

Prefix ảnh hưởng **mọi file output**. Khi prefix đổi, Gradle không thể kết luận chỉ file nào chịu ảnh hưởng, nên báo non-incremental. Tất cả current input files được xem như ADDED để task tạo lại đầy đủ outputs.

### 8.4. @TaskAction InputChanges

~~~kotlin
@TaskAction
fun normalize(changes: InputChanges) {
    // ...
}
~~~

Task có action nhận một `InputChanges`; Gradle cung cấp instance khi execute. Muốn truy vấn delta, **ít nhất một file input property** cần annotate `@Incremental` hoặc `@SkipWhenEmpty`. Một task chỉ có `@Input` scalar và không có incremental file input không thể lấy file changes một cách hợp lệ.

### 8.5. isIncremental

~~~kotlin
if (changes.isIncremental) {
    logger.lifecycle("Incremental file processing is possible")
} else {
    logger.lifecycle("Must process all current files")
}
~~~

`isIncremental` **không** nói kết quả task đúng/sai; nó chỉ mô tả Gradle có đủ thông tin để xác định tập input files thay đổi hay không. Task author chịu trách nhiệm xử lý các sự kiện đúng.

### 8.6. getFileChanges(inputDir)

Trong demo:

~~~kotlin
for (change in changes.getFileChanges(inputDir)) {
    val relative = change.normalizedPath
    // change.changeType thuộc ADDED/MODIFIED/REMOVED
}
~~~

`FileChange` cho biết file, changeType, fileType và normalizedPath. Directory events được bỏ qua nếu task chỉ chuyển đổi contents của files. Với REMOVED, `change.file` có thể không còn tồn tại nên **không đọc nội dung của nó**; dùng `normalizedPath` để tìm output cũ.

### 8.7. An toàn của normalizedPath

Task map input relative path sang output cùng relative path. `target.startsWith(root)` sau `normalize` là kiểm tra phòng vệ để tránh một path thoát output root. Trong demo, Gradle normalizedPath đã có semantics theo `PathSensitivity.RELATIVE`, nhưng với custom task chạy trên inputs không tin cậy, luôn rõ ràng về đường dẫn, symlinks và filesystem security.

### 8.8. Tại sao dùng Locale.ROOT và UTF-8?

`text.uppercase(Locale.ROOT)` tránh kết quả phụ thuộc default Locale máy; `Files.readString/writeString(..., UTF_8)` tránh default charset. Như vậy output là hàm xác định của declared file bytes + `prefix` trong phạm vi demo. Nếu xử lý binary files/encoding khác, task cần mô hình hóa input encoding như một `@Input` riêng.

## 9. Thí nghiệm 1: lần đầu chạy phải xử lý toàn bộ

Trong một checkout mới, chưa có history/output:

~~~bash
./gradlew normalizeTexts --no-build-cache --console=plain
~~~

Những dòng quan trọng dự kiến:

~~~text
MODE: FULL
ADDED: a.txt
ADDED: b.txt
~~~

Nếu thứ tự `b.txt` và `a.txt` đảo, không phải lỗi: API trả Iterable theo cơ chế engine, không cam kết thứ tự để tạo business semantics. Nếu đã chạy demo trước đó, có thể thấy `UP-TO-DATE`; lúc này để tái hiện full ở môi trường demo:

~~~bash
./gradlew clean normalizeTexts --no-build-cache --console=plain
~~~

`clean` xóa directory build theo Base plugin, nên output cần tạo lại. Lệnh `clean` là lựa chọn **để thí nghiệm**, không phải khuyến nghị luôn chạy clean trước mọi build.

### 9.1. “FULL” không có nghĩa scan mọi file trên máy

Gradle chỉ báo các current files thuộc `inputDir` đã khai báo cho task. Nó không tự chuyển đổi toàn bộ `src/main/java`, không tải lại mọi dependencies và không tự chạy root `test` nếu task graph không yêu cầu.

## 10. Thí nghiệm 2: không đổi gì thì task UP-TO-DATE

Chạy liên tiếp:

~~~bash
./gradlew normalizeTexts --no-build-cache --console=plain
./gradlew normalizeTexts --no-build-cache --console=plain
~~~

Nếu inputs/outputs nguyên vẹn và no external invalidation, lượt thứ hai có thể hiện:

~~~text
> Task :normalizeTexts UP-TO-DATE
~~~

Lúc này **không** có dòng `MODE: INCREMENTAL` hay `MODE: FULL` vì task action không được gọi. Đây là tối ưu tránh thực hiện công việc, không phải incremental file processing.

Nếu `normalizeTexts` vẫn chạy dù không đổi, kiểm tra phần input/output model, hidden inputs, validation, file timestamps/content, output directory bị task khác sửa, hoặc môi trường/plugin version. Đừng ngay lập tức tắt build cache: `--no-build-cache` **không tắt up-to-date checks**.

## 11. Thí nghiệm 3: sửa một file thì chỉ xử lý file đó

Giữ `b.txt` nguyên, sửa `inputs/a.txt` từ `one` thành `one updated`. Trên Linux/macOS:

~~~bash
printf "one updated\n" > inputs/a.txt
./gradlew normalizeTexts --no-build-cache --console=plain
~~~

Trên Windows PowerShell, bạn có thể sửa file bằng editor hoặc tạo ASCII text không BOM:

~~~powershell
[System.IO.File]::WriteAllText(
    "inputs/a.txt",
    "one updated" + [Environment]::NewLine,
    (New-Object System.Text.UTF8Encoding($false))
)
.\gradlew.bat normalizeTexts --no-build-cache --console=plain
~~~

**Dòng log quan trọng dự kiến:**

~~~text
MODE: INCREMENTAL
MODIFIED: a.txt
~~~

`b.txt` không đổi nên không cần ghi lại output `build/normalized/b.txt`. Nội dung output của a sẽ là:

~~~text
NORM: ONE UPDATED
~~~

Đây là **incremental execution**, không phải UP-TO-DATE vì action thực sự chạy. Nếu Gradle không có prior history hợp lệ hoặc output bị tác động ngoài, thay vì INCREMENTAL nó sẽ vào FULL — cần xác minh lịch sử trước khi kết luận plugin/task sai.

### 11.1. File thay đổi nhưng task có thể không phải compile lại Java

`normalizeTexts` có input riêng; sửa `inputs/a.txt` không tự làm `compileJava` chạy lại vì JavaCompile source path là `src/main/java` trong demo. Chỉ khi một task/compile source set được cấu hình phụ thuộc generated output và input đó được mô hình hóa như dependency, mới có lý do để downstream task làm thêm việc.

## 12. Thí nghiệm 4: thêm file mới

Tạo `inputs/c.txt` có nội dung `three`, vẫn giữ a/b:

Linux/macOS:

~~~bash
printf "three\n" > inputs/c.txt
./gradlew normalizeTexts --no-build-cache --console=plain
~~~

Windows PowerShell:

~~~powershell
[System.IO.File]::WriteAllText(
    "inputs/c.txt",
    "three" + [Environment]::NewLine,
    (New-Object System.Text.UTF8Encoding($false))
)
.\gradlew.bat normalizeTexts --no-build-cache --console=plain
~~~

**Dòng quan trọng:**

~~~text
MODE: INCREMENTAL
ADDED: c.txt
~~~

Output mới dự kiến:

~~~text
build/normalized/c.txt -> NORM: THREE
~~~

Các output của a/b được giữ nguyên. Nếu output cũ của c vô tình tồn tại từ một lần chạy khác, task vẫn ghi nội dung đúng cho c; nhưng nhiều tasks cùng sở hữu output directory là anti-pattern cần loại bỏ.

## 13. Thí nghiệm 5: xóa input thì phải xóa output tương ứng

Giả sử b còn tồn tại và đã có output `build/normalized/b.txt`. Xóa `inputs/b.txt`:

Linux/macOS:

~~~bash
rm inputs/b.txt
./gradlew normalizeTexts --no-build-cache --console=plain
~~~

Windows PowerShell:

~~~powershell
Remove-Item -LiteralPath "inputs/b.txt"
.\gradlew.bat normalizeTexts --no-build-cache --console=plain
~~~

**Dòng quan trọng dự kiến:**

~~~text
MODE: INCREMENTAL
REMOVED: b.txt
~~~

Task gọi `Files.deleteIfExists` trên `build/normalized/b.txt`; vì thế file b output không còn, tránh việc downstream consumer đọc artifact stale.

### 13.1. Bug phổ biến: chỉ xử lý ADDED và MODIFIED

Một task action viết:

~~~kotlin
if (change.changeType != ChangeType.REMOVED) {
    // regenerate output
}
~~~

nhưng **không có nhánh xóa output** sẽ để các files đã xóa nguồn tiếp tục tồn tại trong build directory. Đó là lỗi correctness, ngay cả khi Gradle báo task thành công và incremental logs trông hợp lý.

### 13.2. Rename thường là remove + add

Đổi `a.txt` thành `renamed.txt` có thể xuất hiện thành cặp REMOVED `a.txt` và ADDED `renamed.txt`. Code cần xóa output cũ và tạo output mới. Với `PathSensitivity.RELATIVE`, relative path quyết định vị trí output, nên rename là thay đổi có ý nghĩa.

## 14. Thí nghiệm 6: đổi scalar input thì phải xử lý toàn bộ

Trong demo, `prefix` là `@Input Property<String>`. Giả sử sau các thí nghiệm trên có current files a và c. Chạy:

~~~bash
./gradlew normalizeTexts \
    -PnormalizePrefix=ALT: \
    --no-build-cache --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat normalizeTexts -PnormalizePrefix=ALT: --no-build-cache --console=plain
~~~

`-PnormalizePrefix=ALT:` là một project property CLI được cấp cho `prefix.convention(...)` khi user không set trực tiếp `prefix` khác.

**Kết quả đáng chú ý:**

~~~text
MODE: FULL
ADDED: a.txt
ADDED: c.txt
~~~

Mọi output phải được tạo lại với prefix mới, ví dụ `ALT:ONE UPDATED` và `ALT:THREE` (không có khoảng trắng sau dấu `:` vì CLI value chính xác là `ALT:`). `b.txt` đã xóa sẽ không được xuất hiện lại.

### 14.1. Vì sao không incremental dù file bytes không đổi?

Gradle không biết một scalar `@Input` thay đổi sẽ ảnh hưởng file nào. Đối với task demo nó ảnh hưởng **mọi output file**. Xử lý delta dựa trên file changes sẽ cho kết quả sai. Vì vậy Gradle chọn non-incremental. Đây là quyết định an toàn: **đừng cố “tiết kiệm” bằng cách bỏ qua non-file input invalidation**.

### 14.2. Task author có thể tối ưu thêm không?

Một custom task rất phức tạp có thể tự thiết kế mapping/state để cập nhật từng phần theo những non-file inputs, nhưng phải **chứng minh correctness** và khai báo các inputs/outputs cho Gradle. Không được giả lập `isIncremental=true` bằng tay hoặc sửa Gradle history. Với bài toán nhỏ, full rebuild là lựa chọn đáng tin.

## 15. Thí nghiệm 7: output bị xóa hoặc sửa thì phải làm lại

Sau một lượt thành công, thử **chỉ trong workspace demo** xóa:

~~~bash
rm build/normalized/a.txt
./gradlew normalizeTexts --no-build-cache --console=plain
~~~

Trên Windows:

~~~powershell
Remove-Item -LiteralPath "build/normalized/a.txt"
.\gradlew.bat normalizeTexts --no-build-cache --console=plain
~~~

Khi output file không còn, Gradle không thể xem các outputs cũ là baseline đáng tin, nên có thể chọn full:

~~~text
MODE: FULL
ADDED: a.txt
ADDED: c.txt
~~~

Nếu có Build Cache enabled và cache key khớp, Gradle có thể **restore output từ cache** thay vì chạy action; vì bài dùng `--no-build-cache` nên dễ quan sát full execution hơn.

**Không làm thí nghiệm này trên production/shared output directory**. Task output directory cần một owner. Nếu một task khác ghi đè `build/normalized/a.txt`, hai tasks có overlapping outputs và khả năng cache/incremental không đáng tin.

## 16. Thí nghiệm 8: --rerun-tasks buộc full processing

Chạy:

~~~bash
./gradlew normalizeTexts --rerun-tasks --no-build-cache --console=plain
~~~

Ngay cả khi file inputs không đổi, `--rerun-tasks` yêu cầu Gradle bypass up-to-date checks. Với custom incremental task, tài liệu Gradle nêu đây là một trường hợp **non-incremental**, nên `InputChanges.isIncremental` là false và mọi current input file được báo ADDED.

Đừng nhầm:

- `--rerun-tasks` = force task execution, không đồng nghĩa “chỉ xử lý những files đã thay đổi”.
- `--refresh-dependencies` = refresh dependency resolution metadata/artifacts, không phải switch incremental input changes.
- `--no-build-cache` = không lấy/đẩy task outputs qua Build Cache, **không** vô hiệu hóa up-to-date checks/incremental task logic.
- `--configuration-cache` = cache kết quả configuration phase, không quyết định file nào của task phải xử lý.
- `clean` = xóa build outputs theo task; nó có thể khiến lượt kế tiếp không có baseline.
- `--continue` = tiếp tục các tasks đủ điều kiện sau failure, không tự retry file changed.

### 16.1. Nếu chỉ muốn refresh một task

Gọi fully qualified task path:

~~~bash
./gradlew :normalizeTexts --rerun-tasks --no-build-cache
~~~

trong single-project demo. Trong multi-project build, `--rerun-tasks` áp dụng tới những tasks được điều phối bởi invocation theo task graph, không phải chỉ một file hoặc method. Với task phức tạp, để giảm phạm vi, gọi đúng module/task và giữ graph nhỏ.

## 17. Bảng quyết định tổng hợp

| Thay đổi kể từ lượt thành công trước | Task action? | Kỳ vọng trong demo khi cache off |
| --- | --- | --- |
| Không có thay đổi | Không | `UP-TO-DATE` |
| Chỉ nội dung `inputs/a.txt` đổi | Có | `INCREMENTAL`, `MODIFIED a.txt` |
| Thêm `inputs/c.txt` | Có | `INCREMENTAL`, `ADDED c.txt` |
| Xóa `inputs/b.txt` | Có | `INCREMENTAL`, `REMOVED b.txt` |
| Rename `a.txt` → `new.txt` | Có | `INCREMENTAL`, thường REMOVED + ADDED |
| Thay `normalizePrefix` | Có | `FULL`, mọi current inputs ADDED |
| Xóa/sửa file dưới `build/normalized` | Có | `FULL` (trừ cache restoration) |
| Lần chạy đầu trên checkout sạch | Có | `FULL`, tất cả input files ADDED |
| Chạy với `--rerun-tasks` | Có | `FULL` |
| Chuyển Gradle version khiến history không reuse | Có | Thường `FULL` |
| Nguồn Java `Main.java` sửa nhưng inputs/*.txt không đổi | Không cần cho normalizeTexts | normalizeTexts có thể UP-TO-DATE; compileJava chạy theo Java input |
| Một input ẩn ngoài annotations đổi | Không thể dự đoán an toàn | Task có thể bị skip/cache sai — lỗi mô hình hóa |
| Dùng Build Cache có hit | Không | `FROM-CACHE`, files được restore |

**Điều kiện của bảng:** đã có baseline hợp lệ, một task owner cho output, `--no-build-cache` khi quan sát file events và không có thay đổi khác trong project/Gradle version/configuration. Đây là expected semantics, không thay thế log của môi trường thật.

## 18. Incremental Java compilation: không đơn giản là “một file đổi, một file compile”

Gradle Java plugin có incremental Java compilation mặc định. Nó phân tích quan hệ classes/types và những thay đổi có thể ảnh hưởng downstream code.

Ví dụ có ba files:

~~~text
src/main/java/demo/
├── Money.java
├── Invoice.java
└── Main.java
~~~

`Invoice` dùng type `Money`, `Main` dùng `Invoice`. Nếu chỉ sửa thân phương thức của `Money`, compiler có thể không phải recompile toàn bộ classes khác nếu public ABI không đổi. Nếu đổi public type/method signature, classes phụ thuộc có thể bị ảnh hưởng.

### 18.1. Ví dụ Java 17 về ABI và implementation

**Money.java:**

~~~java
package demo;

public final class Money {
    public static int add(int a, int b) {
        return a + b;
    }
}
~~~

**Invoice.java:**

~~~java
package demo;

public final class Invoice {
    public static int amount() {
        return Money.add(2, 3);
    }
}
~~~

**Main.java cho thí nghiệm độc lập này:**

~~~java
package demo;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Amount=" + Invoice.amount());
    }
}
~~~

**Bộ ba files là một thí nghiệm độc lập thay thế Java Main của demo chuyển text ở mục 7.6**, không được copy đè vào cùng dự án rồi mong cả hai demos cùng chạy. Chạy bằng JDK 17:

~~~bash
mkdir -p out-abi
javac --release 17 -encoding UTF-8 \
    -d out-abi \
    src/main/java/demo/Money.java \
    src/main/java/demo/Invoice.java \
    src/main/java/demo/Main.java
java -cp out-abi demo.Main
~~~

Dòng stdout chính xác:

~~~text
Amount=5
~~~

### 18.2. Đổi implementation

Thay thân `Money.add` từ:

~~~java
return a + b;
~~~

sang:

~~~java
return Math.addExact(a, b);
~~~

Đối với input 2 và 3, behavior vẫn là 5; public method signature không đổi. Gradle có thể chỉ recompile affected class, còn consumers không cần recompile nếu ABI không đổi. Lưu ý behavior với overflow đã thay đổi nên **tests vẫn quan trọng**: compile avoidance không chứng minh tương đương về ngữ nghĩa.

### 18.3. Đổi public API

Đổi:

~~~java
public static int add(int a, int b)
~~~

thành:

~~~java
public static long add(long a, long b)
~~~

có thể ảnh hưởng source/binary signatures của consumers. Các classes tham chiếu API này có thể cần recompile, và code có thể bị lỗi nếu gán `long` vào `int`. Đây là ví dụ **cần mở rộng tập classes ảnh hưởng**, không thể xem là thay đổi nội bộ hoàn toàn.

### 18.4. Khi JavaCompile phải recompile rộng hơn

Gradle có thể phải recompile nhiều classes hoặc toàn bộ source set khi:

- Public ABI thay đổi và tác động lan rộng.
- Annotation processor không hỗ trợ incremental processing.
- Một số annotation retention hoặc generated code có semantics ảnh hưởng nhiều classes.
- Non-source compiler input/resource thay đổi, classpath/processor path thay đổi theo cách yêu cầu invalidation.
- Source structure/processor không được model đầy đủ.
- Constant inlining hoặc compiler-plugin behavior làm dependency analysis rộng hơn.
- Compile failure trước đó khiến incremental history không đáng tin.
- Dùng tùy chỉnh executable/javaHome/compiler settings làm mất một số optimization.

**Không kết luận “mỗi sửa trong method body = đúng một class compile” trên mọi toolchain.** Compiler quyết định tập impacted classes từ dữ liệu phân tích, chứ không từ số files Git báo thay đổi.

## 19. Compilation avoidance và multi-project builds

Xét:

~~~text
:app ---> :library
~~~

`:app` khai báo:

~~~kotlin
dependencies {
    implementation(project(":library"))
}
~~~

Nếu chỉ sửa private implementation của `:library` và giữ public ABI, Gradle có thể xác định `:app:compileJava` vẫn UP-TO-DATE, vì compile classpath ABI mà app quan tâm không đổi. Tuy nhiên, `:app:test` vẫn có thể cần chạy theo runtime changes nếu dependencies/inputs của test task đã đổi.

Nếu `:library` sửa public method signature/class/interface, downstream compile có thể phải chạy lại. Đây là **compilation avoidance**, khác với custom task `InputChanges` của demo.

### 19.1. java-library api vs implementation

Trong library module:

~~~kotlin
plugins {
    `java-library`
}

dependencies {
    implementation("org.example:internal-engine:1.0")
    api("org.example:public-contract:1.0")
}
~~~

Đây là **snippet cấu trúc**, coordinates `org.example:*` chỉ minh họa, không phải một thư viện được bảo đảm tồn tại. `api` dependencies lộ trong compile API của consumers; `implementation` là details nội bộ, không làm phình compile classpath consumers không cần thiết.

Không dùng `api` cho mọi dependency “cho chắc” vì nó tăng coupling và có thể làm compile avoidance kém hiệu quả. Nhưng nếu public method expose type của thư viện khác, `api` là cần thiết cho consumers.

### 19.2. Cái gì thay đổi lúc runtime không giống cái gì thay đổi lúc compile

Một implementation change của library có thể giữ ABI nhưng vẫn thay behavior. Do đó:

- `:app:compileJava` có thể skip.
- `:app:test` có thể cần chạy nếu test runtime classpath changed.
- Tổ chức vẫn phải chạy integration/contract tests phù hợp.
- Với critical security changes, không chỉ nhìn compile task UP-TO-DATE rồi bỏ tests.

## 20. Annotation processing: isolating và aggregating

Annotation processors có thể sinh code khi JavaCompile chạy. Gradle phân biệt hai mô hình:

**Isolating processor:** output gắn với một input annotated element và các dependencies bị hạn chế theo contract. Khi một element đổi, có thể regenerate output tương ứng.

**Aggregating processor:** một output có thể phụ thuộc vào **tập annotated elements**, ví dụ registry/index tổng hợp. Khi một element đổi, processor có thể cần xét rộng hơn và generate lại aggregate output.

**Non-incremental processor:** nếu processor không công bố contract incremental hoặc vi phạm giới hạn, Gradle có thể phải recompile tất cả classes liên quan.

Tài liệu Gradle hỗ trợ descriptor:

~~~text
META-INF/gradle/incremental.annotation.processors
~~~

với ví dụ:

~~~text
org.example.IsolatingProcessor,isolating
org.example.RegistryProcessor,aggregating
~~~

Các class names trên **chỉ minh họa định dạng**, không phải processors có sẵn trong demo. Processor thực tế phải tuân Gradle incremental annotation processing contract; không chỉ viết descriptor là trở thành incremental an toàn.

### 20.1. Giới hạn quan trọng

- Processor nên dùng `Filer` để tạo source/resource files cho Gradle biết provenance.
- Files output không được tự ghi vào arbitrary locations ngoài compiler model.
- Processor đọc thêm config files/resources phải khai báo các inputs liên quan cho compile task.
- Annotation retention đặc thù có thể vô hiệu hóa incremental processing.
- Compiler tool options/classpath phải được mô hình hóa chính xác.
- Có thể xem `--info` để phát hiện processor nào làm full recompilation.

### 20.2. Khi aggregate output làm per-file update sai

Giả sử task tạo `registry.txt` liệt kê tất cả *.txt. Thêm hoặc xóa một input làm aggregate result đổi. Nếu chỉ ghi file output ứng với input mới mà không cập nhật registry, artifact không còn đúng. Cần rebuild registry từ current inputs hoặc duy trì incremental index có thể cập nhật an toàn. **Ranh giới quyết định là quan hệ đầu vào–đầu ra, không phải chỉ số lượng files đổi.**

## 21. @Incremental, @SkipWhenEmpty và @PathSensitive khác nhau

| Annotation | Vai trò | Lưu ý |
| --- | --- | --- |
| `@Incremental` | Đánh dấu file input property hỗ trợ delta | Cho phép `getFileChanges` |
| `@SkipWhenEmpty` | Input file collection/directory rỗng có thể khiến task skip | Cũng hỗ trợ query file changes trong incremental task |
| `@InputDirectory` | Task có directory input | Cần property typed/phù hợp |
| `@InputFiles` | Task có nhiều files inputs | Không tự incremental nếu không khai báo delta |
| `@PathSensitive(RELATIVE)` | So sánh paths theo relative path | Phù hợp khi path tương đối quyết định output |
| `@PathSensitive(NAME_ONLY)` | Chỉ file name là quan trọng | Có thể collision nếu hai directories có cùng name |
| `@PathSensitive(NONE)` | Chỉ nội dung là quan trọng | Không phù hợp nếu rename/path ảnh hưởng output |
| `@PathSensitive(ABSOLUTE)` | Absolute path có ý nghĩa | Giảm relocation/cache reuse giữa machines |
| `@Classpath` | File collection theo classpath semantics | Phù hợp khi thứ tự/library metadata quyết định |
| `@CompileClasspath` | Sensitivity theo compile ABI | Không dùng cho arbitrary text files |
| `@OutputDirectory` | Directory task thực sự tạo | Không tự mang incremental logic |

**Quan trọng:** `@Incremental` **không tự viết incremental algorithm**. Task action phải xử lý đúng ADDED/MODIFIED/REMOVED, non-incremental fallback và output cleanup.

### 21.1. Khi dùng @SkipWhenEmpty

Task chuyển một thư mục inputs có thể không nên chạy nếu không có files. `@SkipWhenEmpty` kết hợp file input property giúp Gradle skip thích hợp và thường báo NO-SOURCE. Nhưng phải kiểm tra semantics outputs cũ khi nguồn trở nên rỗng: task của bạn không được để artifact stale mà downstream còn tiêu thụ.

Trong demo chọn `@Incremental` để việc chuyển đổi của input files được minh họa nhất quán; không bắt buộc thêm `@SkipWhenEmpty` khi mục tiêu là xem task action xử lý một directory rỗng.

## 22. Build Cache: có cache hit thì không cần incremental action

Một task có thể được gắn `@CacheableTask` nếu:

- Kết quả là hàm xác định của declared inputs, tool implementation/classpath.
- Outputs đã được khai báo đầy đủ.
- Không có hidden side effects bắt buộc phải thực hiện mỗi lần.
- Không ghi secrets vào outputs/cache hoặc đọc biến môi trường không khai báo.
- Input normalization/caching phù hợp giữa các workspaces.

Trong demo, `NormalizeTextTask` deterministic với `prefix`, input files, UTF-8 và Locale.ROOT, nên có `@CacheableTask`.

### 22.1. Kịch bản có Build Cache

~~~bash
./gradlew normalizeTexts --build-cache --console=plain
./gradlew clean normalizeTexts --build-cache --console=plain
~~~

Nếu build cache có kết quả trùng cache key, lượt sau có thể hiện `FROM-CACHE` thay vì execute FULL. Không đảm bảo hit trong mọi môi trường: cache state, Gradle version, task implementation, metadata, relocatability và previous build history đều quan trọng.

**Không được hiểu sai:** `FROM-CACHE` nghĩa là task action không chạy; Gradle khôi phục outputs đã được tính trước. Nó không có dòng `MODE: INCREMENTAL`/`MODE: FULL` từ action.

### 22.2. --no-build-cache dùng khi muốn quan sát thay đổi trực tiếp

Nếu mục tiêu là học `InputChanges`, thêm `--no-build-cache` giúp tránh một cache hit bỏ qua toàn bộ action. Nhưng cờ này **không tắt up-to-date checks**. Muốn chắc action chạy dù unchanged, cần `--rerun-tasks`; khi đó task thường non-incremental.

### 22.3. Không dùng Build Cache để chữa input modelling

Nếu plugin đọc untracked file và từ cache trả output cũ, lỗi nằm ở contract task, không phải “Gradle cache hỏng” một cách mặc định. Hãy bổ sung annotations cho files/parameters và xác định output ownership trước khi khuyến nghị xóa cache toàn cục.

## 23. Configuration Cache và dependency cache khác hoàn toàn

Ba loại tối ưu dễ bị trộn:

| Cơ chế | Cache cái gì? | Quyết định có phải chạy full file processing? |
| --- | --- | --- |
| Configuration Cache | Task graph/build configuration | Không trực tiếp; giảm configuration work |
| Build Cache | Outputs của tasks dựa trên input fingerprints | Có cache hit thì action không chạy |
| Dependency Cache | Thư viện/metadata từ repositories | Tránh network/re-download; không tự chọn file delta |

Lệnh:

~~~bash
./gradlew normalizeTexts --configuration-cache --no-build-cache
~~~

có thể dùng Configuration Cache nhưng task vẫn được lựa chọn UP-TO-DATE, INCREMENTAL hoặc FULL theo inputs/outputs/history. Configuration Cache compatible tasks nên dùng typed properties và tránh execution-time Project access. Demo task action không gọi `project`.

**Nếu task action trực tiếp hỏi `Project`/`extensions` trong execution phase**, có thể gây lỗi Configuration Cache hoặc không theo dõi input đúng. Nối `Provider` vào task properties trong configuration phase, rồi action đọc task property values.

## 24. Task graph: không chạy toàn bộ repository nếu chỉ một task out-of-date

Một Gradle build là DAG của tasks. Gradle chọn tasks theo command và dependencies. Khi một task input đổi, Gradle không cần chạy mọi task không liên quan.

Giả sử:

~~~text
:lib:compileJava ---> :app:compileJava ---> :app:test
        |
        +---> :lib:test
:docs:renderDocs    (không liên quan)
~~~

Sửa source trong `:docs` không mặc nhiên làm `:app:compileJava` hoặc `:lib:test` chạy lại nếu graph/inputs độc lập. Nhưng khi gọi root `build` và nhiều modules được chọn, Gradle vẫn cần đánh giá tasks thuộc requested graph; chúng có thể UP-TO-DATE/FROM-CACHE.

Đặc biệt:

- `dependsOn` giúp Gradle schedule producer tasks nhưng không có nghĩa producer action luôn chạy.
- Nếu producer UP-TO-DATE, consumer vẫn có thể cần chạy do input khác.
- Khi một task thay output, downstream consumers có thể bị invalidated theo fingerprints/caching behavior.
- `mustRunAfter` chỉ ordering nếu cả hai tasks trong graph, không schedule task còn thiếu.
- `--dry-run` cho task graph nhưng không tính output content sau khi execution; không dùng nó để chứng minh incremental processing.

### 24.1. Task dependencies nên dựa vào data flow

Nếu một compile task tiêu thụ generated source, nối output của generator qua TaskProvider/SourceDirectorySet thay vì hardcode `build/generated/...`. Bằng cách này Gradle biết producer nào phải chạy và output file nào là input. Nếu chỉ copy đường dẫn String và thêm `mustRunAfter`, output stale hoặc lỗi build sạch có thể xảy ra.

## 25. Anti-patterns làm incremental builds sai

### Anti-pattern 1 — Không khai báo input quan trọng

~~~kotlin
tasks.register("bad") {
    outputs.file(layout.buildDirectory.file("result.txt"))
    doLast {
        // Doc mot file 'config.txt' khong khai bao la input.
    }
}
~~~

Đây là **snippet anti-pattern**, không phải task runnable hoàn chỉnh. Nếu `config.txt` đổi mà Gradle không biết, task có thể bị skip sai.

### Anti-pattern 2 — Luôn xóa output trong incremental action

~~~kotlin
// SAI neu chay moi lan, ke ca incremental:
outputDir.get().asFile.deleteRecursively()
~~~

Nếu Gradle chỉ báo input a thay đổi, các outputs b/c biến mất và không được regenerate. Không tự xóa mọi output trong incremental branch.

### Anti-pattern 3 — Không xử lý REMOVED

Nếu input b bị xóa, output b tồn tại mãi; Gradle có thể vẫn báo build thành công nhưng artifact sai. Dùng `change.normalizedPath` để xác định output cần xóa.

### Anti-pattern 4 — Chỉ dùng File.lastModified hoặc kiểm tra timestamp

Dựa vào modification time thủ công có thể sai khi timestamp resolution khác, source được checkout/copied với metadata khác hoặc input bytes thay đổi nhưng timestamp giữ nguyên. Gradle file snapshotting/normalization đã có cơ chế so sánh; dùng `InputChanges` thay vì tự viết detector sơ sài.

### Anti-pattern 5 — @CacheableTask cho việc không deterministic

Task dùng `Instant.now()`, random hoặc HTTP response nhưng không khai báo nguồn đó là input có thể trả cache không hợp lệ. Nếu kết quả thật sự non-deterministic, đừng đánh dấu cacheable/UP-TO-DATE một cách giả tạo.

### Anti-pattern 6 — Hai tasks ghi cùng output directory

Overlapping outputs làm ownership nhập nhằng; parallel execution, invalidation và cache đều có nguy cơ sai. Dành riêng output directory cho từng task hoặc dùng một producer tổng hợp có contract rõ ràng.

### Anti-pattern 7 — Chạy clean build mọi lần như “giải pháp”

`./gradlew clean build` khiến nhiều outputs phải tái tạo, giảm lợi ích incremental/cache. Chỉ clean khi cần tái tạo trạng thái sạch, chẩn đoán hoặc policy CI rõ, không phải mặc định để tránh hiểu task inputs.

### Anti-pattern 8 — Dùng --rerun-tasks để kiểm tra incremental

`--rerun-tasks` khiến `InputChanges.isIncremental` thành false trong ví dụ, không quan sát được xử lý delta. Muốn xem incremental, hãy chạy task thành công một lần, sau đó **chỉ sửa một file** và gọi task bình thường (có thể thêm `--no-build-cache`).

### Anti-pattern 9 — Dùng gradle -q rồi tưởng task không chạy

`--quiet/-q` thay log visibility, không tắt work. Trong demo, `logger.lifecycle` bị ẩn ở mức QUIET; muốn xem `MODE` và ADDED/MODIFIED/REMOVED, dùng `--console=plain` không `-q`.

### Anti-pattern 10 — Dùng @PathSensitive.NONE khi output phụ thuộc tên file

Nếu `a.txt` và `b.txt` tạo outputs riêng theo relative path, path là input quan trọng. `NONE` có thể làm normalization/rename semantics không phù hợp; dùng `RELATIVE`.

### Anti-pattern 11 — Trả về sai file input property cho getFileChanges

`InputChanges.getFileChanges(...)` cần chính file input property được annotate `@Incremental`/`@SkipWhenEmpty`. Đừng tạo một file collection mới mỗi lần getter được gọi hoặc truy vấn property không được Gradle theo dõi.

### Anti-pattern 12 — Bỏ qua lỗi task input validation

Task property annotations sai, thiếu @Input/@Output, unsupported annotations hoặc overlapping outputs có thể vô hiệu hóa UP-TO-DATE, Build Cache và incremental optimizations. Hãy đọc Gradle task validation messages thay vì chỉ thêm `--rerun-tasks`.

## 26. Troubleshooting từng triệu chứng

| Triệu chứng | Nguyên nhân thường gặp | Việc nên làm |
| --- | --- | --- |
| Task không đổi vẫn chạy | Output/input model thiếu, output bị sửa, validation issue | `--info`, kiểm tra properties và files |
| Lượt sau không in MODE | Task UP-TO-DATE hoặc FROM-CACHE | Xem task outcome; đó là hành vi đúng |
| Sửa một file mà MODE FULL | Scalar input đổi, output bị tác động, history mất | So prefix, output, Gradle version và flags |
| Sửa một file mà không có event | Input không thuộc declared directory, path khác, build cache hit | Kiểm tra `inputDir`/cache outcome |
| Xóa input nhưng output cũ còn | Task thiếu REMOVED cleanup | Cập nhật logic xóa mapping output |
| Gradle báo missing input directory | `inputs/` chưa tạo hoặc sai path | Tạo directory/file đúng |
| Thay `-PnormalizePrefix` không có tác dụng | Explicit property set override convention hoặc input chưa nối | Kiểm tra `prefix.convention` và input model |
| Java Main báo NoSuchFileException | Chưa chạy normalize, wrong working directory, output bị xóa | Chạy Gradle `run` hoặc producer trước |
| Task `run` in NORM cũ | normalizeTexts không phải dependency hoặc output bị stale | `tasks.named("run").dependsOn(normalizeTexts)` |
| `--rerun-tasks` luôn FULL | Đúng semantics | Dùng delta file change để test incremental |
| `clean build` mất nhiều thời gian | Output/history bị xóa | Dùng `build` thông thường khi không cần clean |
| FROM-CACHE dù output bị xóa | Build Cache có cache hit hợp lệ | Nếu cần xem action, dùng `--no-build-cache` |
| `compileJava` recompile nhiều | API change, annotation processor, inputs/classpath changed | `--info`, kiểm tra ABI/processor |
| Project phụ thuộc không compile lại | ABI không đổi, compilation avoidance | Đúng nếu API giữ, vẫn cần tests |
| Tests không chạy mà CI báo green | `NO-SOURCE`, `SKIPPED` hoặc tests chưa được schedule | Kiểm tra task outcome và test report |
| Incremental output thiếu files | Action xóa toàn dir hoặc có overlapping outputs | Sửa ownership/logic incremental |
| Task xử lý tiếng Việt sai | Charset/locale mặc định hoặc normalization không phù hợp | Ghi rõ UTF-8 và Locale |
| Cross-machine cache miss | Absolute path sensitivity, toolchain/classpath khác | Xem path normalization và cache keys |
| Configuration Cache báo lỗi | Execution-time Project access hoặc capture state | Dùng providers/typed properties |
| Up-to-date sai sau khi file cấu hình đổi | Hidden input không declare | Khai báo `@InputFile`/`@Input` phù hợp |

### 26.1. Quy trình debug bảy bước

1. Xác định task nào **thực sự bị out-of-date**; không chỉ đọc “BUILD FAILED”.
2. Chạy task với `--info --console=plain`, quan sát lý do task chạy/skipped.
3. Bật `--no-build-cache` khi cần xem task action, nhưng đừng mặc định xóa tất cả cache.
4. Kiểm tra task inputs: file collections/directories, scalar properties, classpaths, normalization.
5. Kiểm tra outputs: file paths, ownership, có task/process khác sửa không.
6. Nếu custom incremental task, log `isIncremental` và changed files trong test environment.
7. Sửa input/output contract trước; chạy lại clean baseline, rồi mutate một biến một lần để xác minh delta.

## 27. Java compile, tests và generated code: quyết định theo dependency

### 27.1. Sửa Java method body

Một thay đổi implementation giữ ABI có thể khiến chỉ module sở hữu recompile các classes bị ảnh hưởng; module consumer không cần compile lại. Nhưng tests cần xác nhận behavior và có thể chạy lại vì runtime classpath changed.

### 27.2. Đổi public signature

Các classes sử dụng API phải được compile lại; nếu chữ ký không tương thích, javac báo lỗi. Đừng dùng `--rerun-tasks` làm giải pháp cho compile errors; sửa source/dependencies.

### 27.3. Đổi resource file

`processResources` có thể làm lại phần resource cần thiết; `compileJava` không tự bị invalidated chỉ vì một resource không phải input của compiler. Nhưng `test`/packaging tasks tiêu thụ resources có thể bị ảnh hưởng.

### 27.4. Generated Java source

Nếu một task tạo Java sources, hãy khai báo output directory và nối nó tới `sourceSets.main.java.srcDir(taskProvider)` hoặc một cơ chế provider tương đương. Gradle biết producer cần thực hiện trước compile; chỉ chép path String có thể gây stale outputs.

### 27.5. Tests

Gradle Test task cũng dùng task-level up-to-date/cache model; nếu code/classpath/test config thay đổi, test task có thể rerun. Không phải mọi framework tự chạy **chỉ những test methods thay đổi** chỉ vì build incremental. Phạm vi test execution phụ thuộc Gradle Test task, test engine, filtering, test distribution và plugin phù hợp.

### 27.6. Annotation processor

Nếu processor aggregating/non-incremental, thay một source file có thể ảnh hưởng nhiều generated files và làm full recompilation. Không nên gỡ processor khỏi task để “tăng tốc” mà bỏ mất correctness. Hãy dùng processor hỗ trợ incremental contract, khai báo resource inputs và kiểm tra logs.

## 28. Khi nào nên chọn incremental algorithm cho custom task?

Không phải mọi task đều nên sử dụng `InputChanges`. Hãy đánh giá:

| Câu hỏi | Nếu câu trả lời là Có | Hướng thiết kế |
| --- | --- | --- |
| Mỗi input file tạo một output độc lập? | Có | Incremental 1:1 transformer phù hợp |
| Xóa input có output mapping rõ? | Có | REMOVED → delete matching output |
| Output aggregate của mọi files? | Có | Full recompute hoặc incremental index/state có chứng minh |
| Scalar config ảnh hưởng mọi output? | Có | Full khi config đổi |
| Task chạy external tool không hỗ trợ changed files? | Có | Full tool invocation hoặc tool adapter có contract |
| Inputs/outputs không deterministic? | Có | Ưu tiên correctness, không cache bừa |
| File change detection rất đắt so với task work? | Có | Incremental algorithm có thể không đáng |
| Rủi ro output stale cao? | Có | Tập trung vào validation/clean baseline tests |
| Task chỉ copy files? | Có | Ưu tiên Gradle built-in `Copy`/`Sync` trước custom implementation |
| Task compile Java? | Có | Dùng `JavaCompile`/toolchain sẵn, đừng tự viết incremental compiler |
| Input files ít, task rất nhanh? | Có | Full recompute có thể đơn giản và đáng tin hơn |

**Tối ưu đúng chỗ:** ưu tiên existing Gradle tasks/plugins đã có incremental support, rồi mới viết `InputChanges` custom task khi có bằng chứng performance và output correctness rõ.

## 29. Kiểm thử một custom incremental task đúng cách

Một test chỉ chạy task một lần và kiểm tra output **không đủ**. Phải kiểm thử **chuỗi trạng thái**:

1. Workspace sạch → FULL, mọi current files tạo output.
2. Không thay đổi → UP-TO-DATE.
3. Sửa một file → INCREMENTAL, chỉ output tương ứng cập nhật.
4. Thêm file → INCREMENTAL ADDED.
5. Xóa file → INCREMENTAL REMOVED, output cũ biến mất.
6. Rename file → output cũ biến mất, output tên mới xuất hiện.
7. Đổi scalar input → FULL, mọi outputs có tham số mới.
8. Xóa/sửa một output bên ngoài → FULL hoặc cache restoration, output đúng.
9. Force `--rerun-tasks` → FULL.
10. Với Build Cache on/off → artifacts trùng nội dung.
11. Chạy ở clean checkout khác → results tương đương (nếu task thiết kế relocatable).
12. Chạy Unicode/input nested folders → encoding/path đúng.
13. Task được gọi từ pipeline chung → không xung đột outputs với task khác.
14. Configuration Cache → không execution-time project access.
15. Không có inputs/source → được xử lý theo policy đã định, không để stale output.

### 29.1. TestKit khi xây plugin

Nếu custom task thuộc binary plugin, Gradle TestKit `GradleRunner` có thể chạy sample build trong temp directory, chỉnh một file mỗi lượt rồi assert task outcomes, file contents và deletion. Không cần chỉ dựa vào console text; file content + task outcome đáng tin hơn.

**Lưu ý:** TestKit tests chạy Gradle builds, do đó cần Gradle distribution, correct plugin classpath, JDK và temp project đúng. Nếu muốn assert exact event count/order, hãy thiết kế logs ổn định hoặc ghi test-visible trace riêng có contract; đừng giả định thứ tự `FileChange` events bất biến.

## 30. Bài tập thực hành và đáp án

**Câu 1.** `UP-TO-DATE` có nghĩa task đã chạy và chỉ xử lý vài files?  
**Đáp án:** không. Task action không chạy.

**Câu 2.** `FROM-CACHE` có gọi `@TaskAction` không?  
**Đáp án:** không. Gradle restore outputs được cache.

**Câu 3.** Sửa duy nhất `inputs/a.txt`, vẫn có history/output hợp lệ; mode nào trong demo?  
**Đáp án:** INCREMENTAL, event MODIFIED của a.

**Câu 4.** Xóa input b nhưng output b vẫn còn. Task đang thiếu gì?  
**Đáp án:** nhánh REMOVED xóa output tương ứng.

**Câu 5.** Thêm file c; cần xử lý a và b lại không?  
**Đáp án:** không trong transformer độc lập 1:1 và history hợp lệ; chỉ c.

**Câu 6.** Sửa `prefix` nhưng không đổi file bytes. Mode nào?  
**Đáp án:** FULL, vì scalar `@Input` có thể ảnh hưởng mọi outputs.

**Câu 7.** `InputChanges.isIncremental` false thì getFileChanges báo các file hiện tại là loại gì?  
**Đáp án:** ADDED.

**Câu 8.** Thay Gradle version khiến history không reuse; có thể incremental không?  
**Đáp án:** không nếu Gradle không còn baseline hợp lệ; full.

**Câu 9.** Xóa `build/normalized/a.txt` rồi gọi task bình thường, làm gì?  
**Đáp án:** Gradle thấy output invalid; full hoặc restore cache nếu có hit.

**Câu 10.** `--rerun-tasks` có giúp chỉ chạy modified files?  
**Đáp án:** không. Nó ép task rerun non-incrementally.

**Câu 11.** `--no-build-cache` có tắt UP-TO-DATE không?  
**Đáp án:** không, chỉ tắt Build Cache.

**Câu 12.** `--configuration-cache` có thay thế incremental processing không?  
**Đáp án:** không, nó cache configuration/task graph.

**Câu 13.** `@Incremental` đặt trên `String` có phù hợp không?  
**Đáp án:** không; nó dành cho file input properties đúng kiểu, dùng `@Input` cho scalar.

**Câu 14.** Tại sao demo dùng `PathSensitivity.RELATIVE`?  
**Đáp án:** relative path quyết định output mapping, còn absolute workspace path không cần là input.

**Câu 15.** Vì sao không xóa toàn bộ outputDir trong incremental branch?  
**Đáp án:** vì unchanged inputs không được phát events để regenerate.

**Câu 16.** Task có `@OutputDirectory` mà không có `InputChanges` có thể UP-TO-DATE không?  
**Đáp án:** có, nếu khai báo inputs/outputs đúng và Gradle có history.

**Câu 17.** Một task chỉ log stdout, không tạo outputs, có thể @CacheableTask như file producer không?  
**Đáp án:** thường không; console side effect không phải output cacheable artifact.

**Câu 18.** Java Main demo gốc in gì với a.txt là one và prefix NORM?  
**Đáp án:** `NORM: ONE`.

**Câu 19.** Lệnh Java 17 thuần trong demo có chạy Gradle custom task không?  
**Đáp án:** không; nó đọc output đã tạo sẵn.

**Câu 20.** Đổi thân `Money.add` mà giữ public signature có buộc mọi consumers recompile không?  
**Đáp án:** không nhất thiết; compile avoidance có thể skip, nhưng tests vẫn cần.

**Câu 21.** Đổi public return type của library method có ảnh hưởng downstream compile không?  
**Đáp án:** có thể; ABI changed và consumers bị ảnh hưởng.

**Câu 22.** Resource file đổi có tự buộc mọi Java sources recompile không?  
**Đáp án:** không mặc định; phụ thuộc task inputs và compiler/processor configuration.

**Câu 23.** Non-incremental annotation processor có thể làm JavaCompile recompile rộng hơn không?  
**Đáp án:** có.

**Câu 24.** Một processor aggregating sinh một registry cho mọi annotated classes; thay một class có thể cần cập nhật gì?  
**Đáp án:** aggregate registry output và tập elements liên quan, không chỉ file một class.

**Câu 25.** File input `config.txt` được task đọc nhưng không annotate; vì sao nguy hiểm?  
**Đáp án:** Gradle không biết nó ảnh hưởng outputs, có thể skip/cache sai.

**Câu 26.** Task bỗng FULL dù chỉ một file đổi. Nên xem gì trước?  
**Đáp án:** `--info`, scalar inputs, output tampering, history, Gradle version và flags.

**Câu 27.** `--dry-run` có thể chứng minh task sẽ xử lý MODIFIED a.txt không?  
**Đáp án:** không; nó không execute task action và không tạo output.

**Câu 28.** Với transform nhiều files rất ít và xử lý cực nhanh, nhất thiết viết custom incremental task?  
**Đáp án:** không; full deterministic processing hoặc built-in Copy/Sync có thể đơn giản hơn.

**Câu 29.** Hai tasks ghi cùng output directory là vấn đề gì?  
**Đáp án:** overlapping outputs, có thể phá cache/up-to-date/incremental correctness.

**Câu 30.** `PathSensitivity.NONE` có luôn phù hợp khi rename source file?  
**Đáp án:** không nếu path/name ảnh hưởng output identity; chọn normalization theo semantics.

**Câu 31.** `@SkipWhenEmpty` có giống `@Incremental` hoàn toàn không?  
**Đáp án:** không; nó thêm empty-input skip semantics, dù cả hai có thể hỗ trợ getFileChanges.

**Câu 32.** Xóa một file output và bật `--build-cache`, có chắc thấy MODE FULL không?  
**Đáp án:** không; Gradle có thể restore FROM-CACHE.

**Câu 33.** Thay `-PnormalizePrefix=ALT:`, Java Main sẽ in gì nếu a.txt là one updated?  
**Đáp án:** `ALT:ONE UPDATED`.

**Câu 34.** Thay input a.txt từ one sang one updated, b không đổi. b output có nên viết lại?  
**Đáp án:** không trong incremental mode hợp lệ.

**Câu 35.** Một task tạo summary của tất cả inputs có thể chỉ cập nhật mỗi file output riêng không?  
**Đáp án:** không nếu summary aggregate phụ thuộc tập files; cần cập nhật aggregate hoặc full recompute.

**Câu 36.** Compilation avoidance có nghĩa Java test suite chắc chắn không cần chạy?  
**Đáp án:** không; implementation/runtime behavior có thể đổi dù ABI không đổi.

## 31. Checklist trước khi tin một incremental build

- [ ] Đã phân biệt UP-TO-DATE, FROM-CACHE, INCREMENTAL và FULL?
- [ ] “Full” đang nói về một task hay cả project graph đã được xác định?
- [ ] Input scalar, file/directory, classpath và outputs được khai báo đầy đủ?
- [ ] Không có hidden config/environment/network inputs ảnh hưởng kết quả?
- [ ] Custom task có `@Incremental`/`@SkipWhenEmpty` đúng file property?
- [ ] `@TaskAction` nhận `InputChanges` và dùng `getFileChanges` đúng property?
- [ ] Task xử lý đủ ADDED, MODIFIED và REMOVED?
- [ ] Non-incremental branch có tái tạo mọi current outputs?
- [ ] Incremental branch không xóa output của unchanged inputs?
- [ ] `PathSensitivity` phù hợp filename/path semantics?
- [ ] Outputs có một task owner, không overlapping?
- [ ] Prefix/format/tool versions được khai báo scalar inputs phù hợp?
- [ ] Không đánh dấu task non-deterministic `@CacheableTask` bừa bãi?
- [ ] Đã hiểu `--no-build-cache` không tắt UP-TO-DATE?
- [ ] Không dùng `--rerun-tasks` làm phép kiểm thử incremental delta?
- [ ] Thực hiện baseline → không đổi → sửa một file → add/remove/rename?
- [ ] Đã thử đổi scalar input và xóa/sửa output để xác nhận full fallback?
- [ ] Có phân biệt JavaCompile incremental với generic custom task?
- [ ] Có xem public ABI, annotation processor và runtime behavior?
- [ ] Test/check tasks vẫn được chọn đúng quality gate dù compile skipped?
- [ ] Task graph và data flow có khai báo producer/consumer dependencies?
- [ ] Incremental output content được assert, không chỉ xem build success?
- [ ] Đã kiểm tra task validation warnings và `--info`?
- [ ] Không xóa toàn bộ Gradle User Home chỉ vì một task rerun?
- [ ] Có kiểm tra clean workspace/CI, JDK/Gradle Wrapper tương thích?
- [ ] Có tests chứng minh incremental outputs đúng sau deletion và parameter changes?

## 32. Tài liệu chính thức

- [Gradle — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html): task inputs, outputs, up-to-date checking, annotations và validation.
- [Gradle — Advanced Tasks / Incremental Tasks](https://docs.gradle.org/current/userguide/custom_tasks.html): `InputChanges`, `@Incremental`, full fallback và `ADDED`/`MODIFIED`/`REMOVED`.
- [Gradle — InputChanges API](https://docs.gradle.org/current/javadoc/org/gradle/work/InputChanges.html): `isIncremental`, `getFileChanges` và semantics.
- [Gradle — Incremental Annotation](https://docs.gradle.org/current/javadoc/org/gradle/work/Incremental.html): khai báo incremental file input.
- [Gradle — Implementing Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html): task types, annotated inputs/outputs, `@TaskAction`.
- [Gradle — Optimizing Builds](https://docs.gradle.org/current/userguide/gradle_optimizations.html): UP-TO-DATE, FROM-CACHE, SKIPPED và incremental builds.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): incremental Java compilation, compilation avoidance và annotation processing.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): ABI và `api`/`implementation` scope.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): cache keys và task outputs.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): configuration phase optimization, khác task execution.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `tasks.register` và lazy task references.
- [Gradle — Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html): file input/output properties, built-in Copy/Sync tasks.
- [Gradle — Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html): task input/output model và tránh hidden/overlapping outputs.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): `--rerun-tasks`, `--no-build-cache` và diagnostic flags.
- [Gradle — Performance](https://docs.gradle.org/current/userguide/performance.html): build optimization strategies và incremental compilation.

**Kết luận:** Muốn quyết định xử lý một phần hay toàn bộ, trước hết phải xác định **task có chạy hay không**. Nếu không đổi, Gradle có thể bỏ qua task (`UP-TO-DATE`) hoặc lấy outputs từ cache (`FROM-CACHE`). Nếu cần execute, một custom task có `@Incremental` + `InputChanges` có thể xử lý **chỉ ADDED/MODIFIED/REMOVED files** khi history và outputs còn đáng tin. Nhưng khi không có baseline, `@Input` scalar đổi, output bị can thiệp, `--rerun-tasks` hoặc những điều kiện invalidation khác, task phải **xử lý tất cả current inputs**. Với JavaCompile, Gradle dùng thêm class dependency/ABI analysis để giảm phạm vi recompilation. **Tối ưu đúng nhất là tối ưu không làm sai kết quả:** khai báo inputs/outputs chính xác, xóa stale outputs khi input bị remove, luôn có full fallback và kiểm thử cả các tình huống thay đổi lẫn trạng thái cache.
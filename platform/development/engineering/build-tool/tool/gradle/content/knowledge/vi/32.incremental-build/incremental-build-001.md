# Up-to-date check và mô hình đầu vào, đầu ra trong Gradle

## 1. Bối cảnh: vì sao Gradle không cần chạy lại mọi task?

Trong chủ đề **Build tăng dần** của **Build Tool Gradle**, một tối ưu hóa cốt lõi là tránh làm lại công việc đã có kết quả hợp lệ. Khi sửa một dòng Java source, ta muốn Gradle chỉ chạy những tasks bị ảnh hưởng, không biên dịch lại vô điều kiện, chạy lại mọi tool và tạo lại mọi báo cáo. Gradle thực hiện điều đó nhờ **mô hình đầu vào (inputs), đầu ra (outputs) và task implementation**.

Ví dụ, task `compileJava` nhận source files, classpath và compiler options làm đầu vào, rồi tạo `.class` files làm đầu ra. Nếu đầu vào và đầu ra đã được ghi nhận ở lần chạy thành công trước vẫn phù hợp, Gradle có thể **bỏ qua task action** và đánh dấu task `UP-TO-DATE`. Đây là **up-to-date check**—một phần của cơ chế incremental build, hoạt động theo mặc định cho những task có metadata thích hợp.

Bài này tập trung vào cách **khai báo đúng task inputs/outputs, cách Gradle xác định up-to-date, cách kiểm tra hành vi thực tế và vì sao một task có thể chạy lại**. Mô hình này áp dụng cho Java compilation, resource processing, code generation, report generation và custom tasks.

Sau bài học, bạn có thể:

1. Phân biệt task **đang up-to-date** với task chạy, `NO-SOURCE`, `SKIPPED` và `FROM-CACHE`.
2. Giải thích task fingerprints và lịch sử đầu vào/đầu ra (input/output snapshots).
3. Khai báo `@Input`, `@InputFile`, `@InputFiles`, `@InputDirectory`, `@OutputFile`, `@OutputDirectory` và các modifiers liên quan.
4. Dùng `Property<T>`, `RegularFileProperty`, `DirectoryProperty`, `ConfigurableFileCollection` và Providers.
5. Chọn `@PathSensitive(PathSensitivity.NONE/RELATIVE/NAME_ONLY/ABSOLUTE)` có chủ đích.
6. Viết Gradle Kotlin DSL custom task tạo file thật từ template, chạy hai lần và quan sát `UP-TO-DATE`.
7. Nối một task sản xuất file với task tiêu thụ bằng `TaskProvider.flatMap` để Gradle suy ra task dependency.
8. Thử sửa input, đổi scalar property, xóa output, cưỡng chế chạy bằng `--rerun-tasks` và đối chiếu kết quả.
9. Phân biệt **up-to-date check**, **Build Cache**, **Configuration Cache** và **incremental task action dùng `InputChanges`**.
10. Chẩn đoán vì sao một task luôn chạy, cache không hit hoặc up-to-date sai; thiết kế output ownership và CI diagnostics.

**Thông điệp quan trọng:** Gradle không đoán hết input/output cho custom tasks. Task author phải khai báo **mọi giá trị và file thật sự ảnh hưởng output**. Thiếu input có thể làm Gradle bỏ qua một task khi nó đáng ra phải chạy lại—rủi ro về tính đúng đắn, không chỉ hiệu năng.

## 2. Các thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa chính | Ví dụ |
| --- | --- | --- |
| Task action | Mã thực thi công việc ở execution phase | `@TaskAction fun generate()` |
| Input property | Giá trị ảnh hưởng output | Tên người nhận, compiler flags |
| Input file/directory | Nội dung file hoặc tree ảnh hưởng output | Java sources, template |
| Output file/directory | Artifact task chịu trách nhiệm tạo/sửa | `.class`, report, generated text |
| Input fingerprint | Dấu vân tay đầu vào đã được chuẩn hóa để so sánh | Property value + file content/path |
| Output fingerprint | Dấu vân tay output của lần task chạy thành công | Report file bytes |
| Task history | Trạng thái đã ghi nhận từ execution trước | Dùng để quyết định up-to-date |
| `UP-TO-DATE` | Task action được bỏ qua vì kết quả đang hợp lệ theo metadata | `:renderGreeting UP-TO-DATE` |
| `FROM-CACHE` | Task lấy output từ Build Cache thay vì chạy action | Cache hit sau `clean` |
| `NO-SOURCE` | Task hỗ trợ source files thấy không có source phù hợp | `processResources NO-SOURCE` |
| `SKIPPED` | Task bị bỏ qua do điều kiện/được disable hoặc skip rule | `onlyIf { false }` |
| Incremental task action | Task chạy nhưng chỉ xử lý file changes thay vì toàn bộ | `InputChanges.getFileChanges()` |
| Build Cache | Cơ chế tái sử dụng task outputs theo cache key | Local/remote build cache |
| Configuration Cache | Lưu state cấu hình/task graph để giảm configuration phase | `--configuration-cache` |

**Không đồng nghĩa:** `UP-TO-DATE` ≠ `FROM-CACHE` ≠ task `NO-SOURCE`. Cả ba đều có thể tránh task action theo những lý do khác nhau.

### 2.1. Up-to-date là bỏ qua **cả task action**

Nếu đầu vào, đầu ra và các yếu tố liên quan đủ ổn định, Gradle không gọi `@TaskAction`/`doLast` nữa. Vì vậy `println` nằm trong action **không xuất hiện ở lần `UP-TO-DATE`**; điều này là bình thường.

### 2.2. Incremental action là vẫn chạy task nhưng làm ít hơn

Khi **có input file thay đổi**, task không còn up-to-date, nhưng một custom task được viết để nhận `InputChanges` có thể chỉ xử lý file `ADDED`/`MODIFIED` và xóa output ứng với file `REMOVED`. Task vẫn xuất hiện là đã thực thi, chỉ workload giảm. Đây là một cấp tối ưu cao hơn nhưng phức tạp hơn.

## 3. Mô hình và điều kiện cơ bản của up-to-date check

Giả sử task đọc file `template.txt` và property `person`, tạo `greeting.txt`:

~~~text
Inputs:
  template.txt (nội dung)
  person="Lan" (scalar)
  task implementation (logic liên quan)
         |
         v
 Task renderGreeting
         |
         v
Output:
  build/generated/greeting.txt
~~~

Lượt đầu:

1. Gradle xác định task nằm trong task graph và cần thực hiện.
2. Gradle thu thập snapshot/fingerprint của những inputs được khai báo.
3. Task action đọc template và property, ghi output.
4. Sau khi task hoàn thành thành công, Gradle ghi nhận output snapshot và task execution history.

Lượt tiếp theo với cùng cấu hình:

1. Gradle tạo/đối chiếu fingerprints theo metadata task và các file properties.
2. Nếu inputs tương ứng không thay đổi, outputs vẫn hợp lệ, task implementation có thể tái sử dụng, task có lịch sử đủ và không có điều kiện buộc chạy, task được đánh dấu `UP-TO-DATE`.
3. Task action không chạy lại. Gradle vẫn có thể thực hiện configuration phase nếu không dùng Configuration Cache.

Các thành phần Gradle có thể xem xét gồm declared property values, file contents/normalized paths, task implementation code và output contents. Không nên tự giản lược thành “nếu ngày sửa file không đổi thì bỏ qua”; Gradle có snapshot/cache/fingerprint mechanics riêng.

Theo tài liệu Gradle, khi metadata file `lastModified` và `size` giữ nguyên, Gradle có thể dùng lại fingerprint trước đó thay vì băm lại bytes; do đó những cách sửa file rồi cố tình khôi phục cả hai thuộc tính này có thể làm thay đổi nội dung khó được phát hiện. Trong build thực tế, tránh những công cụ can thiệp file timestamp/size theo cách phá vỡ cơ chế phát hiện thay đổi.

### 3.1. Phải có output được khai báo

Một task có action nhưng **không khai báo output** thông thường không có cơ sở để Gradle sử dụng kết quả output trước đó như một up-to-date task; action có thể chạy mỗi lần nó được yêu cầu. Không cố làm task có side effects bất định (gửi email, publish release, gọi API mutate dữ liệu) trông như deterministic output task để lấy `UP-TO-DATE`.

### 3.2. Inputs nào cần khai báo?

Một input phải khai báo khi **đổi nó có thể làm output khác**. Ví dụ:

- Source file/template bytes.
- `person`, `language`, `format`, `minify`, compiler options.
- Classpath/compiler/tool version nếu ảnh hưởng output.
- Môi trường cần cho deterministic transformation khi thật sự ảnh hưởng output.
- Pattern/encoding/line ending policy nếu ảnh hưởng generated bytes.

Không tự động đưa mọi thứ thành input: mức RAM tối đa cấp cho compiler có thể ảnh hưởng hiệu năng nhưng không nhất thiết ảnh hưởng `.class` bytes; fingerprint những giá trị không liên quan làm task chạy lại không cần thiết.

### 3.3. Outputs nào phải khai báo?

Mọi file/directory mà task **chịu trách nhiệm tạo/sửa và cần tái sử dụng** phải được mô hình hóa. Nếu task tạo `report.html` nhưng không khai báo nó, Gradle có thể coi công việc đã up-to-date dù file report bị xóa. Nếu task tạo nhiều outputs nhưng chỉ khai báo một file, Gradle không thể quản lý output còn lại đúng.

## 4. Hai cách khai báo inputs/outputs

Gradle hỗ trợ hai hướng:

1. **Annotated task type**: viết class kế thừa `DefaultTask`, chú thích getters/properties bằng annotations. Khuyến nghị cho code dùng lại, validation rõ ràng, có khả năng mở rộng.
2. **Ad-hoc task inputs/outputs**: dùng `inputs.property(...)`, `inputs.file(...)`, `outputs.file(...)`, `outputs.dir(...)` trong task configuration. Hữu ích cho task nhỏ nhưng dễ bỏ sót metadata nếu logic phức tạp.

Ví dụ ad-hoc (độc lập với bài lab chính):

~~~kotlin
val textProvider = providers.gradleProperty("sampleText")
    .orElse("Hello")

val outputProvider = layout.buildDirectory.file("demo/message.txt")

tasks.register("writeMessage") {
    inputs.property("text", textProvider)
    outputs.file(outputProvider)

    doLast {
        val target = outputProvider.get().asFile
        target.parentFile.mkdirs()
        target.writeText(textProvider.get() + "\n", Charsets.UTF_8)
    }
}
~~~

Với task này, đổi `-PsampleText=...` sẽ đổi input fingerprint. Nếu `outputProvider` tồn tại, task action deterministic và không có yếu tố ngoài chưa khai báo, lần tiếp theo có thể `UP-TO-DATE`.

**Lưu ý:** Đây là mảnh Kotlin DSL đặt trực tiếp trong `build.gradle.kts`; nó có thể dùng để minh họa nhưng với task lớn, annotated task type và Gradle managed properties thường dễ validate và kiểm thử hơn. Không dùng `inputs.property("x", someSecret)` rồi ghi secret vào Build Cache/logs nếu dữ liệu đó không an toàn để lưu.

## 5. Annotations quan trọng: bảng tra cứu

| Annotation | Áp dụng cho | Ý nghĩa |
| --- | --- | --- |
| `@Input` | Scalar/value/Provider property | Giá trị ảnh hưởng output |
| `@InputFile` | Một input file | Theo dõi file path/content theo normalization |
| `@InputFiles` | Tập các file | Theo dõi collection và contents |
| `@InputDirectory` | Một input directory | Theo dõi thư mục và contents dưới nó |
| `@OutputFile` | Một output file | File do task tạo |
| `@OutputFiles` | Tập output files | Nhiều files do task tạo |
| `@OutputDirectory` | Một output directory | Task sở hữu contents của thư mục |
| `@OutputDirectories` | Tập output directories | Nhiều output folders |
| `@Nested` | Bean có annotated properties bên trong | Đệ quy khai báo metadata input |
| `@Internal` | Property chỉ dùng cho nội bộ, không tham gia fingerprint | Loại khỏi up-to-date inputs |
| `@Optional` | Modifier cho input/output không bắt buộc | Property/file có thể vắng |
| `@PathSensitive` | Modifier cho file inputs | Chọn phần path tham gia fingerprint |
| `@Classpath` | Classpath file inputs | Normalization thích hợp cho classpath/archive contents |
| `@CompileClasspath` | Compile classpath | Normalization tối ưu cho compile semantics |
| `@SkipWhenEmpty` | Input files/dir modifier | Bỏ qua task khi nguồn được đánh dấu rỗng |
| `@IgnoreEmptyDirectories` | Input file/dir modifier | Không coi thư mục trống là khác biệt khi hợp lệ |
| `@NormalizeLineEndings` | File input modifier | Chuẩn hóa LF/CRLF để giảm thay đổi giả trong use case phù hợp |
| `@Incremental` | Input file/dir modifier | Cho phép nhận thay đổi từng file qua `InputChanges` |
| `@LocalState` | File/dir local mutable state | Không coi là portable cached output |
| `@Destroys` | File/dir task xóa | Khai báo side effect để Gradle điều phối phù hợp |
| `@Console` | Property phục vụ console | Không tính fingerprint thông thường |

Đối với Kotlin task source, đặt annotation trên **getter** bằng `@get:Input`, `@get:OutputFile`, v.v. Với Java task type, annotation gắn trên abstract getter `getX()`, không phải setter.

### 5.1. Vì sao không dùng @Input cho file path?

Nếu property là `RegularFileProperty` hoặc `File` được dùng để đọc contents, hãy khai báo `@InputFile` (kèm path normalization). `@Input` dành cho giá trị/scalar, và Gradle task validation có thể cảnh báo/lỗi khi dùng annotation không phù hợp cho file-type property. Nếu chỉ quan tâm một **chuỗi đường dẫn như dữ liệu** chứ không đọc bytes, đó là mô hình khác; đừng đánh đồng.

### 5.2. Vì sao @Internal cần thận trọng?

Ví dụ `logger`, intermediate calculation hoàn toàn suy ra từ inputs có thể là internal. Nhưng nếu property thực sự ảnh hưởng generated output mà bị đánh dấu `@Internal`, Gradle sẽ không theo dõi nó; task có nguy cơ **up-to-date sai**.

### 5.3. Optional input không có nghĩa mọi output đều được phép thiếu

`@Optional` cho phép property không được cung cấp/nguồn vắng khi mô hình task cho phép. Task action **phải tự xử lý** trường hợp vắng đó (`orNull`, `isPresent`, null checks), không được `.get()` mù quáng. Nếu một output đã được khai báo và task thành công, sự biến mất/thay đổi output thường khiến task không còn up-to-date; không nên dựa vào `@Optional` để lờ đi generated output bắt buộc.

## 6. Managed properties và Providers

Các kiểu Gradle khuyến nghị:

- `Property<String>`: một scalar như tên người, mode, charset name.
- `RegularFileProperty`: một file do Gradle quản lý location qua `Provider<RegularFile>`.
- `DirectoryProperty`: một directory có thể set từ `layout.projectDirectory.dir(...)` hoặc `layout.buildDirectory.dir(...)`.
- `ConfigurableFileCollection`: nhiều files hoặc outputs từ tasks/dependencies.
- `ListProperty<T>`/`MapProperty<K,V>`: tập values khi thích hợp.

Dùng `abstract val` trong Kotlin DSL task class:

~~~kotlin
abstract class ExampleTask : DefaultTask() {
    @get:Input
    abstract val greetingName: Property<String>

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val templateFile: RegularFileProperty

    @get:OutputFile
    abstract val generatedFile: RegularFileProperty
}
~~~

Đây là **mảnh minh họa properties**, chưa có `@TaskAction` nên không độc lập thành chương trình sinh file. Bài lab ở phần sau bổ sung action và registration đầy đủ.

### 6.1. Provider-based wiring

Không nên thực hiện `someProvider.get()` ngay trong configuration phase chỉ để tạo đường dẫn. Hãy set property từ provider:

~~~kotlin
generatedFile.set(
    layout.buildDirectory.file("generated/greeting.txt")
)
~~~

Vì `layout.buildDirectory.file(...)` là Provider, nó theo được thay đổi build directory trước khi provider được resolve.

Với task producer/consumer, dùng `TaskProvider.flatMap` thay vì đọc file output rồi `.get()` sớm. Điều này có thể mang **task dependency metadata** từ producer tới input property của consumer.

### 6.2. `convention` khác `set`

~~~kotlin
greetingName.convention("Lan")
~~~

đặt default có thể bị module override, còn:

~~~kotlin
greetingName.set("Lan")
~~~

là cấu hình giá trị trực tiếp. Khi viết plugin dùng chung, `convention` thường phù hợp cho defaults, trong khi build script của một task cụ thể có thể dùng `set` có chủ ý.

### 6.3. Path phải thuộc đúng loại

`@InputFile` -> `RegularFileProperty` cho file. `@InputDirectory` -> `DirectoryProperty` cho directory. `@InputFiles` -> `ConfigurableFileCollection` hoặc collection/provider files được Gradle hiểu. Đừng `@InputDirectory` vào một file hoặc dùng `@OutputFile` trên thư mục.

## 7. Ví dụ hoàn chỉnh: task tạo greeting từ template

Chúng ta viết custom task ở `build.gradle.kts` mà **không cần buildSrc hoặc plugin ngoài**, sau đó tạo một Java 17 program để đọc kết quả. Ví dụ tập trung vào mô hình inputs/outputs, không dùng JavaExec phức tạp khiến khó xác định nguồn `UP-TO-DATE`.

### 7.1. Cấu trúc thư mục

~~~text
gradle-incremental-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── templates/
│   └── greeting.txt
├── src/
│   └── main/
│       └── java/
│           └── demo/
│               └── GreetingReader.java
├── gradlew
├── gradlew.bat
└── gradle/wrapper/
    ├── gradle-wrapper.jar
    └── gradle-wrapper.properties
~~~

Giả định có JDK 17, Gradle Wrapper được tin cậy và một Gradle version hỗ trợ Kotlin DSL custom task types. `GreetingReader` dùng JDK API nên không cần Maven Central.

### 7.2. settings.gradle.kts

~~~kotlin
rootProject.name = "gradle-incremental-demo"
~~~

### 7.3. templates/greeting.txt

Tạo file UTF-8 với nội dung **đúng một dòng**:

~~~text
Xin chào, {{person}}!
~~~

Có thể kết thúc file bằng LF (một newline). Task sẽ bỏ newline cuối của template rồi tự thêm một newline ổn định vào output.

### 7.4. build.gradle.kts đầy đủ

~~~kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.provider.Property
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

abstract class RenderGreeting : DefaultTask() {

    @get:Input
    abstract val person: Property<String>

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val templateFile: RegularFileProperty

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun render() {
        val template = templateFile.get().asFile
            .readText(Charsets.UTF_8)
            .trimEnd('\r', '\n')

        val greeting = template.replace(
            "{{person}}",
            person.get()
        )

        val target = outputFile.get().asFile
        target.parentFile.mkdirs()
        target.writeText(greeting + "\n", Charsets.UTF_8)

        logger.lifecycle("Rendered: ${target.name}")
    }
}

abstract class CopyGreeting : DefaultTask() {

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val sourceFile: RegularFileProperty

    @get:OutputFile
    abstract val destinationFile: RegularFileProperty

    @TaskAction
    fun copyGreeting() {
        val source = sourceFile.get().asFile
        val target = destinationFile.get().asFile

        target.parentFile.mkdirs()
        source.copyTo(target, overwrite = true)

        logger.lifecycle("Copied: ${target.name}")
    }
}

val renderGreeting = tasks.register<RenderGreeting>(
    "renderGreeting"
) {
    group = "demo"
    description = "Tạo greeting.txt từ template và person."

    person.set(
        providers.gradleProperty("greetingPerson")
            .orElse("Lan")
    )

    templateFile.set(
        layout.projectDirectory.file("templates/greeting.txt")
    )

    outputFile.set(
        layout.buildDirectory.file("generated/greeting.txt")
    )
}

tasks.register<CopyGreeting>("copyGreeting") {
    group = "demo"
    description = "Sao chép greeting từ output của renderGreeting."

    // Provider mang dependency metadata từ producer task.
    sourceFile.set(
        renderGreeting.flatMap { it.outputFile }
    )

    destinationFile.set(
        layout.buildDirectory.file("reports/greeting-copy.txt")
    )
}
~~~

**Đây là file Kotlin DSL hoàn chỉnh** cho hai custom tasks. Chúng không cần `plugins { java }`, bởi Gradle core đã có APIs `DefaultTask`/Providers/TaskAction. `@get:` đặt annotations lên Kotlin property getters đúng như Gradle task-property validation cần.

Điểm cần nắm:

1. `person` là scalar `@Input`, ảnh hưởng chuỗi output.
2. `templateFile` là `@InputFile`, cần đọc bytes; `PathSensitivity.NONE` nói rằng **vị trí file không ảnh hưởng kết quả**, chỉ nội dung liên quan. Điều này đúng vì output không in tên file hoặc vị trí template.
3. `outputFile` là `@OutputFile`, cho Gradle biết file kết quả nằm ở đâu.
4. `@TaskAction` chỉ đọc declared inputs, tạo parent directory, ghi vào declared output.
5. Nội dung output ổn định: file UTF-8, newline LF được task thêm, không phụ thuộc current time/randomness.
6. Task không ghi vào `src` hay file template; generated artifacts nằm dưới `layout.buildDirectory`.
7. `tasks.register` và `TaskProvider.flatMap` duy trì lazy configuration.
8. `CopyGreeting` lấy output của `RenderGreeting` làm input thông qua Provider, nhờ đó Gradle có thể suy ra task dependency.
9. `logger.lifecycle` giúp nhận biết action thật sự được chạy. Ở lần `UP-TO-DATE`, thông điệp action không xuất hiện.
10. Các tasks này **chưa được đánh dấu `@CacheableTask`**: up-to-date check và Build Cache là hai quyết định độc lập. Không nên tuyên bố một custom task luôn được Build Cache cache chỉ vì có annotations input/output.

### 7.5. Vì sao copy task không cần dependsOn tường minh?

Cấu hình:

~~~kotlin
sourceFile.set(
    renderGreeting.flatMap { it.outputFile }
)
~~~

mang thông tin producer task qua provider. Gradle biết phải chạy `renderGreeting` trước khi `copyGreeting` tiêu thụ output. `dependsOn(renderGreeting)` có thể được thêm tường minh khi có lý do nhưng trong trường hợp này **không cần** nếu Provider giữ đúng task origin metadata.

Không làm như sau:

~~~kotlin
sourceFile.set(
    layout.buildDirectory.file("generated/greeting.txt")
)
~~~

nếu bạn muốn Gradle **tự suy ra producer task** chỉ từ file path. Một path trùng với output của task khác không tự biểu đạt nguồn gốc và task dependency đầy đủ. Cần wiring qua provider của producer hoặc dùng `dependsOn` có chủ ý.

## 8. Chạy task và quan sát UP-TO-DATE

Lần đầu:

Linux/macOS:

~~~bash
./gradlew renderGreeting --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat renderGreeting --console=plain
~~~

Nếu inputs hợp lệ và chưa có task history/output, task action chạy và in thông điệp:

~~~text
Rendered: greeting.txt
~~~

Sau khi chạy, file `build/generated/greeting.txt` có **nội dung chính xác**:

~~~text
Xin chào, Lan!
~~~

Chạy lần thứ hai, không sửa input hoặc output:

~~~bash
./gradlew renderGreeting --console=plain
~~~

Dòng trạng thái task dự kiến:

~~~text
> Task :renderGreeting UP-TO-DATE
~~~

Thông điệp `Rendered: greeting.txt` **không xuất hiện do action không chạy lại**. Phần `BUILD SUCCESSFUL in ...`, tiến độ và logs khác tùy Gradle version, daemon/cache và console mode; ở đây chỉ nêu các dòng có ý nghĩa.

### 8.1. Chạy chuỗi producer -> consumer

~~~bash
./gradlew copyGreeting --console=plain
~~~

Nếu cả hai tasks chưa chạy, Gradle thực thi `renderGreeting` rồi `copyGreeting` theo dependency suy ra. Output thứ hai nằm tại:

~~~text
build/reports/greeting-copy.txt
~~~

và có cùng bytes:

~~~text
Xin chào, Lan!
~~~

Chạy lại:

~~~bash
./gradlew copyGreeting --console=plain
~~~

Khi outputs/inputs chưa đổi, cả `renderGreeting` và `copyGreeting` thường được đánh dấu `UP-TO-DATE`.

### 8.2. Điều kiện để nhìn thấy UP-TO-DATE

Không chạy `clean`, `--rerun-tasks` hoặc sửa template giữa hai invocation. Cần dùng cùng Gradle build/task history tương thích và không để chương trình khác chạm vào output file. Nếu môi trường chạy ephemeral, history có thể không tồn tại và task sẽ chạy lại hoặc lấy kết quả từ Build Cache nếu được cho phép.

## 9. Java 17 đọc output của task

Để kiểm chứng nội dung generated file bằng một Java program chạy được, tạo:

**src/main/java/demo/GreetingReader.java**

~~~java
package demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class GreetingReader {
    private GreetingReader() {
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Cần đúng một đường dẫn tệp greeting"
            );
        }

        String greeting = Files.readString(
            Path.of(args[0]),
            StandardCharsets.UTF_8
        );

        System.out.print(greeting);
    }
}
~~~

Từ root project, sau khi chạy `renderGreeting`:

Linux/macOS:

~~~bash
mkdir -p out
javac -encoding UTF-8 --release 17 \
  -d out src/main/java/demo/GreetingReader.java
java -cp out demo.GreetingReader build/generated/greeting.txt
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -encoding UTF-8 --release 17 -d out src\main\java\demo\GreetingReader.java
java -cp out demo.GreetingReader build\generated\greeting.txt
~~~

**Stdout chính xác** là một dòng, với newline từ file:

~~~text
Xin chào, Lan!
~~~

Đây là code JDK 17 độc lập, không dùng Maven dependencies. `javac` ở đây chứng minh Java source và generated output đúng; **up-to-date behavior phải xác minh bằng Gradle invocation**, không suy ra từ Java application stdout.

### 9.1. Vì sao không đưa JavaReader làm output task?

Java `GreetingReader.class` được `javac` bên ngoài tạo trong `out/`, không phải output của `renderGreeting`. Để mô hình hóa việc biên dịch Java qua Gradle, áp Java plugin (`compileJava`/`classes`) hoặc tạo task có inputs/outputs được khai báo. Không coi mọi file vừa xuất hiện trên filesystem là artifact do Gradle tự theo dõi.

## 10. Thử nghiệm thay đổi inputs, outputs và quan sát

### 10.1. Thay đổi scalar property

Lệnh:

~~~bash
./gradlew renderGreeting \
  -PgreetingPerson=Mai \
  --console=plain
~~~

Bởi `person` là `@Input`, `Lan -> Mai` làm fingerprint thay đổi, task cần chạy lại. File sau task:

~~~text
Xin chào, Mai!
~~~

Chạy đúng lệnh với cùng `-PgreetingPerson=Mai` lần nữa, task có thể `UP-TO-DATE`.

**Quan trọng:** Nếu sau đó chạy **không có** `-PgreetingPerson=Mai`, property trở về default `Lan`, fingerprint lại đổi và task có thể chạy lại. Một task không “nhớ” giá trị từ lệnh trước như biến trạng thái của ứng dụng; nó lấy property theo từng build invocation.

### 10.2. Thay nội dung input file

Sửa `templates/greeting.txt` thành:

~~~text
Kính chào {{person}}.
~~~

Sau đó:

~~~bash
./gradlew renderGreeting --console=plain
~~~

Với default person `Lan`, file output:

~~~text
Kính chào Lan.
~~~

Đó là ví dụ cho `@InputFile`: Gradle nhận biết nội dung input đã đổi và không giữ kết quả cũ. Nếu dùng `-PgreetingPerson=Mai`, output sẽ là `Kính chào Mai.`.

### 10.3. Xóa file output

Sau một lượt task thành công:

Linux/macOS:

~~~bash
rm build/generated/greeting.txt
./gradlew renderGreeting --console=plain
~~~

Windows PowerShell:

~~~powershell
Remove-Item build\generated\greeting.txt
.\gradlew.bat renderGreeting --console=plain
~~~

Output không còn phù hợp snapshot đã lưu, nên Gradle phải tạo lại (hoặc phục hồi từ Build Cache nếu task cacheable/cache có kết quả; ở ví dụ task custom chưa opt-in Build Cache nên task action được chạy). Không gọi đây là `UP-TO-DATE`.

### 10.4. Sửa output bằng tay

Nếu ai đó sửa `build/generated/greeting.txt` sau khi task đã chạy, fingerprint của output có thể không khớp history. Gradle thường chạy lại task để khôi phục kết quả do task sở hữu.

**Tuy nhiên:** Điều này không bảo đảm phát hiện trong trường hợp công cụ độc hại cố tình thay nội dung mà giữ nguyên file size/mtime theo cơ chế Gradle file hashing optimization. Đừng dùng output snapshot như security-integrity check chống kẻ tấn công; nó phục vụ build correctness/performance.

### 10.5. Xóa output directory bằng clean

~~~bash
./gradlew clean renderGreeting --console=plain
~~~

Bài lab **không apply Java/Base plugin để có task `clean` mặc định** nên lệnh trên **không hợp lệ với cấu hình tối thiểu của phần 7**. Nếu muốn thực hành `clean`, hãy bổ sung core `base` plugin vào `build.gradle.kts`:

~~~kotlin
plugins {
    base
}
~~~

Sau đó `clean` dọn build directory theo conventions và `renderGreeting` phải tạo lại output. Nếu task được đánh dấu cacheable và có cache hit, status có thể `FROM-CACHE` thay vì chạy action. Trong ví dụ đang dùng, custom task không mặc định Build Cache cacheable.

**Quy tắc học được:** Đừng giả định mọi Gradle project không áp plugin nào cũng có `clean`. Task `clean` được Base/Java và các plugins cung cấp, không tự tồn tại trong một build hoàn toàn tối giản.

### 10.6. Buộc thực thi với --rerun-tasks

~~~bash
./gradlew renderGreeting --rerun-tasks --console=plain
~~~

`--rerun-tasks` buộc tasks thực thi lại bất chấp trạng thái up-to-date và bỏ cơ chế phục hồi output từ Build Cache trong lượt forced rerun. Dùng để chẩn đoán lỗi stale outputs, không dùng thường xuyên trong CI nếu muốn tận dụng incremental build.

### 10.7. Tắt Build Cache nhưng giữ up-to-date checks

~~~bash
./gradlew renderGreeting --no-build-cache --console=plain
~~~

`--no-build-cache` tắt **Build Cache reuse** trong invocation, nhưng task vẫn có thể `UP-TO-DATE` dựa trên local execution history. Đây là phép thử giúp phân biệt hai cơ chế.

## 11. @PathSensitive và input normalization

Một file có thể giữ nguyên bytes nhưng đổi vị trí. Gradle cần biết **file path có ảnh hưởng output không**.

| PathSensitivity | Phần path tham gia fingerprint | Sử dụng phù hợp |
| --- | --- | --- |
| `NONE` | Bỏ qua path, xét file content | Single template mà output không in filename |
| `RELATIVE` | Tương quan với root của declared input tree | Source tree, file collection cần giữ cấu trúc |
| `NAME_ONLY` | Chỉ filename, bỏ qua parent dirs | Khi chỉ tên file quan trọng |
| `ABSOLUTE` | Full absolute path | Chỉ khi absolute path thực sự ảnh hưởng output; kém relocatable |

Với task `RenderGreeting`, `@PathSensitive(PathSensitivity.NONE)` là hợp lý vì output không dùng location hay filename của template. Nếu chuyển `templates/greeting.txt` sang path khác với cùng bytes và task property trỏ file mới, `NONE` cho phép Gradle coi content tương đương nếu các inputs khác không đổi.

Nếu task xử lý toàn bộ source tree theo relative paths, thường dùng `RELATIVE`, vì tên và cấu trúc folder cần để tạo outputs đúng. Nên tránh `ABSOLUTE` khi không cần, nhất là nếu dùng remote Build Cache giữa máy developer/CI có root directories khác nhau.

### 11.1. Path sensitivity khác file content normalization

`@PathSensitive` quyết định normalized path. `@NormalizeLineEndings` giúp bỏ khác biệt CRLF/LF của text inputs khi thay đổi line endings không ảnh hưởng output semantics. Nhưng nếu task tạo output **giữ nguyên bytes** từ input file, line ending thay đổi **có thể ảnh hưởng output**, khi đó không nên normalize line endings.

### 11.2. @Classpath và @CompileClasspath

Classpath chứa JARs, classes directories và metadata đặc thù. Dùng `@Classpath`/`@CompileClasspath` cho file properties biểu diễn classpath, thay vì dùng `@InputFiles @PathSensitive(ABSOLUTE)` một cách máy móc.

- `@Classpath`: Gradle dùng classpath-aware normalization, xử lý archive contents và classpath order theo semantics phù hợp.
- `@CompileClasspath`: tối ưu fingerprint cho compile-time semantics, có thể bỏ qua một số thay đổi không ảnh hưởng public ABI tùy Gradle implementation.

Không sử dụng `@CompileClasspath` cho input mà task thực sự cần **runtime implementation bytes** hoặc nội dung bất kỳ không phải compile classpath, vì có thể bỏ qua thay đổi đáng lẽ ảnh hưởng output.

### 11.3. Default PathSensitivity có thể không relocatable

Nếu file property không khai báo path normalization, nhiều use cases mặc định coi absolute path, có thể gây cache miss khi workspace path khác. Gradle task author nên chọn một normalization rõ ràng phù hợp với output, thay vì dựa vào defaults và khẳng định task luôn dùng được remote cache.

## 12. @InputFiles và @InputDirectory cho tập nguồn

Một task quét nhiều file có thể khai báo:

~~~kotlin
abstract class ScanSources : DefaultTask() {
    @get:InputFiles
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val sourceFiles: ConfigurableFileCollection

    @get:OutputFile
    abstract val reportFile: RegularFileProperty
}
~~~

Đây là mảnh **task model**, chưa có `@TaskAction` nên không dùng riêng để tạo báo cáo. `@InputFiles` dành cho collection; Gradle sẽ fingerprint các file theo normalization đã chọn.

Với một input directory:

~~~kotlin
abstract class RenderDirectory : DefaultTask() {
    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val inputDir: DirectoryProperty

    @get:OutputDirectory
    abstract val outputDir: DirectoryProperty
}
~~~

`@InputDirectory` có ý nghĩa về **cây thư mục**, `@OutputDirectory` biểu thị task sở hữu những outputs nằm trong thư mục đó. Nếu task thực tế chỉ tạo một file cụ thể, `@OutputFile` thường tốt hơn output directory quá rộng.

### 12.1. Empty directories

File trees có thể chứa thư mục trống. Trong một task không quan tâm sự tồn tại của thư mục trống, `@IgnoreEmptyDirectories` giúp tránh invalidation không cần thiết khi chỉ thay đổi empty folder structure. Nhưng nếu output phải tạo những thư mục trống tương ứng với input, **không nên** ignore chúng.

### 12.2. SkipWhenEmpty

Khi task không có source files và không nên làm gì, `@SkipWhenEmpty` là modifier thích hợp cho input file collection/directory. Gradle có thể đánh dấu task `NO-SOURCE` và xử lý stale outputs theo semantics của task đó.

Ví dụ snippet:

~~~kotlin
@get:InputFiles
@get:SkipWhenEmpty
@get:PathSensitive(PathSensitivity.RELATIVE)
abstract val sourceFiles: ConfigurableFileCollection
~~~

`@SkipWhenEmpty` phải gắn đúng file input property. Nếu không có bất kỳ source nào nhưng task vẫn cần tạo một manifest rỗng, **không** dùng SkipWhenEmpty: output rỗng là một kết quả có chủ đích, task vẫn phải chạy.

### 12.3. Optional

Ví dụ một input template bổ sung không bắt buộc:

~~~kotlin
@get:Optional
@get:InputFile
@get:PathSensitive(PathSensitivity.NONE)
abstract val optionalHeader: RegularFileProperty
~~~

Task action:

~~~kotlin
val header = optionalHeader.orNull?.asFile
    ?.readText(Charsets.UTF_8)
    .orEmpty()
~~~

Đây là **hai mảnh cấu hình minh họa**; muốn chạy cần định nghĩa lớp task, output và action đầy đủ. `@Optional` có nghĩa property có thể vắng, không tự giải quyết lỗi khi task `.get()` vào property chưa được set.

## 13. Outputs phải có ownership rõ ràng

Một anti-pattern phổ biến là hai tasks cùng khai báo hoặc cùng ghi vào `build/generated/` mà không phân chia ownership:

~~~text
generateA -> build/generated/data.txt
generateB -> build/generated/data.txt
~~~

Khi outputs overlap, Gradle khó xác định snapshot/cache correctness và có thể cảnh báo implicit dependency hoặc không cache task hợp lệ. Nếu hai tasks dùng chung output file, phải xem lại thiết kế: thường chỉ có **một producer** cho một file, các consumers đọc file ấy thông qua provider.

Khuyến nghị:

- Mỗi task tạo output file/directory riêng.
- Với nhiều files tạo bởi một task, dùng một output directory riêng chỉ thuộc task đó.
- Không để task phụ ghi vào output file do task khác sở hữu.
- Không ghi generated files trực tiếp vào `src/main/java` trừ khi có quy trình kiểm soát cực kỳ rõ.
- Không dùng `build/` toàn bộ làm `@OutputDirectory` cho nhiều tasks.
- Cần `@LocalState` cho state local không portable, `@Destroys` khi task xóa outputs có chủ đích.
- Khi task xóa một output của producer, kế hoạch task graph phải được thể hiện đúng để tránh race/unsafe ordering.
- Không biến file log/báo cáo tạo ở path ngoài declared outputs thành side effects bị ẩn.

### 13.1. Một task không được đọc output của task khác chỉ bằng path trần

Nếu `copyGreeting` dùng:

~~~kotlin
sourceFile.set(
    layout.buildDirectory.file("generated/greeting.txt")
)
~~~

Gradle có thể biết file location nhưng **không biết producer là renderGreeting**. Điều cần làm là:

~~~kotlin
sourceFile.set(
    renderGreeting.flatMap { it.outputFile }
)
~~~

để task dependency metadata được truyền cùng Provider. Điều này góp phần đảm bảo output input được tạo trước khi consumer chạy và tránh implicit dependency validation warnings.

### 13.2. DependsOn và MustRunAfter không giống nhau

`dependsOn(renderGreeting)` yêu cầu task dependency và làm producer được đưa vào graph. `mustRunAfter(renderGreeting)` chỉ là ordering constraint khi cả hai đã có trong graph, **không tự thêm** producer vào graph. Với dữ liệu producer->consumer, Provider wiring thường diễn đạt dependency tự nhiên hơn; `mustRunAfter` không thay được source file producer relationship.

## 14. Task luôn chạy lại: vì sao?

Nếu custom task không bao giờ thấy `UP-TO-DATE`, hãy kiểm tra:

1. Nó có **output** được khai báo không?
2. Output file có thực sự được tạo ở đúng location không?
3. File output có bị task khác sửa/xóa giữa builds không?
4. Task có input không ổn định như `Instant.now()`, random UUID hoặc timestamp không?
5. Task `@TaskAction` có tạo kết quả khác với cùng declared inputs không?
6. Task có đọc một env var hoặc file không được khai báo khiến output đổi ngầm không?
7. PathSensitivity đang là ABSOLUTE khi CI workspace thay đổi hay không?
8. Có chạy `--rerun-tasks`, `clean`, `outputs.upToDateWhen { false }` hoặc `outputs.cacheIf` policy đặc biệt không?
9. Có task implementation code/plugin classpath thay đổi không?
10. Có cache/task history tồn tại từ invocation trước không, hay mọi CI job dùng workspace hoàn toàn mới?
11. Task có `onlyIf` hoặc skip conditions làm status khác không?
12. Output/input đang là symbolic link, network filesystem hay path ngoài project với thay đổi đặc biệt không?

Để chẩn đoán:

~~~bash
./gradlew renderGreeting --info --console=plain
~~~

Gradle có thể in lý do kiểu `Task ':renderGreeting' is not up-to-date because: ...`. Format/lời giải thích cụ thể thay đổi theo Gradle version; đọc thông báo thực tế chứ không đoán.

### 14.1. `--info` và `--debug`

`--info` thường đủ để xem execution reasons. `--debug` rất verbose và có thể đưa nhiều details từ environment/logs vào output; cẩn trọng khi đưa CI logs công khai, đặc biệt khi builds có credentials.

### 14.2. Lỗi nghiêm trọng: thiếu input làm up-to-date sai

Giả sử action đọc `System.getenv("GREETING_STYLE")` rồi thay đổi output, nhưng task chỉ khai báo template/person. Nếu biến môi trường đổi, Gradle không nhất thiết biết kết quả khác; task có thể bị đánh dấu `UP-TO-DATE` **sai**.

Giải pháp: thêm property `@Input val style: Property<String>` và cấu hình từ `providers.environmentVariable("GREETING_STYLE").orElse("default")`. Task action chỉ dùng property đã model, không đọc environment trực tiếp theo cách ẩn.

Nếu property là secret, cần thiết kế security/caching riêng, tránh lưu plain secret trong logs/cache khi không cần.

### 14.3. Input không ảnh hưởng output làm task chạy lại thừa

Một task chỉ copy nội dung file nhưng khai báo `sessionId` ngẫu nhiên làm @Input sẽ phải chạy lại mỗi lần, giảm hiệu năng. Task author phải phân biệt operational parameter (ví dụ maximum heap) với semantic input có thể làm output khác.

## 15. Build Cache khác Up-to-date Check

**Up-to-date check:** so sánh với history/outputs đã có ở build workspace hiện tại. Task chưa chạy action mà output và fingerprints vẫn hợp lệ -> `UP-TO-DATE`.

**Build Cache:** lưu một artifact/task output theo cache key khi task **cacheable** và cache được bật. Sau `clean` hoặc trên workspace khác, Gradle có thể tải lại output từ local/remote cache -> `FROM-CACHE`, không chạy task action.

| Tình huống | Có thể thấy |
| --- | --- |
| Chạy lại task không đổi input/output | `UP-TO-DATE` |
| Xóa output, task cacheable, có cache entry | `FROM-CACHE` |
| Xóa output, task không cacheable | Task action chạy |
| Workspace mới, cacheable task có remote cache hit | `FROM-CACHE` |
| Task without outputs | Thường execute nếu action được yêu cầu |
| Đổi task input value | Không up-to-date; có thể chạy hoặc cache hit cho key đó |
| `--rerun-tasks` | Bỏ qua up-to-date/cache reuse theo forced rerun |
| `--no-build-cache` | Không lấy output từ Build Cache, vẫn có thể `UP-TO-DATE` |

### 15.1. Custom task có cần @CacheableTask?

Với các task type do chính bạn viết, caching **không nên được giả định tự bật** chỉ vì có input/output annotations. Nếu task deterministic, outputs khai báo đủ và không có side effects không thể cache, có thể opt-in bằng `@CacheableTask` hoặc cấu hình caching policy tương ứng.

Ví dụ annotation:

~~~kotlin
@CacheableTask
abstract class StableReportTask : DefaultTask() {
    @get:Input
    abstract val reportTitle: Property<String>

    @get:OutputFile
    abstract val reportFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val f = reportFile.get().asFile
        f.parentFile.mkdirs()
        f.writeText(reportTitle.get() + "\n", Charsets.UTF_8)
    }
}
~~~

Đây là **một class task đầy đủ về ý tưởng**, cần import các Gradle APIs và registration riêng khi đưa vào build. Chỉ áp `@CacheableTask` sau khi bạn xác minh task không phụ thuộc undeclared inputs, không ghi vào output ngoài declared outputs, không chứa current timestamp/randomness, và kết quả có thể được dùng lại an toàn ở môi trường khác.

### 15.2. `@CacheableTask` có tự tạo remote cache không?

Không. Nó đánh dấu task có thể cache output theo điều kiện; vẫn cần Build Cache được bật/cấu hình và cache entry phù hợp. Remote cache cần backend, permissions và trust policy. `@CacheableTask` không cho phép một task có side-effect như publish/upload mutating release được chạy hoặc skip tùy ý.

### 15.3. Relocatability và path normalization

Nếu output chỉ phụ thuộc file contents và relative path, `PathSensitivity.NONE/RELATIVE` giúp output cache dùng lại giữa `C:\work\repo` và `/home/ci/work/repo` khi các điều kiện khác tương đương. Nếu task nhúng absolute path vào output, normalization `NONE` có thể gây **cache hit sai**. Phải model absolute path như input khi nó thực sự ảnh hưởng output.

## 16. Configuration Cache khác cả hai

Configuration Cache tối ưu **configuration phase**: lưu task graph/configured task state và phục hồi khi các configuration inputs không đổi. Nó **không quyết định** một task output đã up-to-date và cũng không thay thế Build Cache.

Ví dụ:

~~~bash
./gradlew renderGreeting --configuration-cache --console=plain
./gradlew renderGreeting --configuration-cache --console=plain
~~~

Lần sau có thể reuse configuration cache entry nhưng task còn được xét up-to-date độc lập. Có thể đồng thời thấy configuration cache reused và `UP-TO-DATE` ở task. Ngược lại configuration cache miss không có nghĩa task phải rerun nếu outputs không đổi.

### 16.1. Vì sao task action không nên truy cập Project?

Configuration Cache cần task state serializable và execution phase tách khỏi live Gradle model. Tránh dùng `project.file(...)`, `project.findProperty(...)`, `project.tasks...` trong `@TaskAction`. Thay bằng managed properties và Providers được cấu hình ở configuration phase.

Task `RenderGreeting` ở phần 7 chỉ đọc `person`, `templateFile`, `outputFile` và `logger` trong action, không giữ `Project`. Đây là thiết kế thuận lợi hơn cho configuration cache.

### 16.2. Nếu configuration cache fail

Chạy:

~~~bash
./gradlew renderGreeting --configuration-cache --stacktrace
~~~

Đọc configuration-cache problems report để xem đoạn nào giữ `Project` hoặc unsupported state. Không tắt Configuration Cache rồi coi up-to-date model đã được sửa—đó là hai vấn đề độc lập.

## 17. Incremental task action: khi đã cần xử lý từng file

Up-to-date task có thể skip toàn bộ work nếu **không gì đổi**. Nhưng nếu chỉ một file trong 1000 files thay đổi, một task thường vẫn chạy action và có thể scan lại tất cả 1000 nếu implementation làm vậy.

Gradle có API `InputChanges`, cho phép task nhận thông tin những files:

- `ADDED`: mới xuất hiện trong input set.
- `MODIFIED`: content/metadata có ảnh hưởng đến fingerprint thay đổi.
- `REMOVED`: file không còn trong input set.

Khi dùng incremental task action, task được annotate file input với `@Incremental` hoặc `@SkipWhenEmpty`, và action nhận tham số `InputChanges`. **Không đồng nhất** `UP-TO-DATE` với `InputChanges.isIncremental`: up-to-date là task không chạy; incremental là cách task chạy hiệu quả khi cần.

### 17.1. Task type ví dụ xử lý input dir

Mảnh dưới đây là **một class task hợp lệ về API** nhưng cần đặt vào `build.gradle.kts` có imports/registration và cấu hình file dir thực tế:

~~~kotlin
abstract class MirrorTextFiles : DefaultTask() {
    @get:Incremental
    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val sourceDir: DirectoryProperty

    @get:OutputDirectory
    abstract val targetDir: DirectoryProperty

    @TaskAction
    fun mirror(changes: InputChanges) {
        val outRoot = targetDir.get().asFile.toPath()

        for (change in changes.getFileChanges(sourceDir)) {
            if (change.fileType == FileType.DIRECTORY) continue

            val target = outRoot.resolve(
                change.normalizedPath
            ).toFile()

            if (change.changeType == ChangeType.REMOVED) {
                target.delete()
            } else {
                target.parentFile.mkdirs()
                target.writeText(
                    change.file.readText(Charsets.UTF_8),
                    Charsets.UTF_8
                )
            }
        }
    }
}
~~~

Mã minh họa **giữ nguyên bytes về mặt text được đọc/ghi UTF-8**, nhưng với một tool chuyển đổi thật cần xử lý symlinks, file types, encoding, output cleanup và errors. Đây là mẫu về `InputChanges`/file change handling, không phải một file `build.gradle.kts` runnable độc lập vì chưa có imports/registration.

### 17.2. Khi nào isIncremental false?

`changes.isIncremental` có thể là `false` nếu:

- Chưa có history từ execution trước.
- Input property không phải incremental đã thay đổi.
- Task implementation/Gradle version làm state cũ không dùng được.
- Output file đã bị xóa/sửa so với history.
- Forced `--rerun-tasks`.
- `outputs.upToDateWhen` hoặc điều kiện liên quan buộc execution non-incremental.

Khi non-incremental, Gradle có thể trả tất cả input files như `ADDED`, task phải sẵn sàng xử lý lại toàn bộ và đảm bảo stale outputs được xử lý đúng.

### 17.3. Xử lý file REMOVED

Nếu một input file bị xóa, incremental task **phải xóa output tương ứng** (nếu semantic là one input file -> one output file). Bỏ qua `REMOVED` sẽ để stale outputs tồn tại, và các consumers có thể đọc kết quả không còn hợp lệ.

### 17.4. Một task chỉ nên có một incremental action

Theo Gradle docs, một task chỉ có thể có một incremental task action nhận `InputChanges`. Không chia logic thành nhiều `@TaskAction` cùng nhận `InputChanges` và kỳ vọng Gradle hợp nhất events tự động.

### 17.5. Khi nào không cần InputChanges?

Đối với task tạo **một file report duy nhất** từ một template đơn, `@InputFile` + `@OutputFile` đã đủ: nếu không đổi, skip; nếu đổi, regenerate toàn bộ file nhỏ. Không tăng độ phức tạp bằng InputChanges nếu nó không giảm đáng kể work.

## 18. Gradle tự khai báo inputs/outputs cho built-in tasks

Built-in tasks của Java plugin như `JavaCompile`, `ProcessResources`, `Jar`, `Test` có metadata riêng, nên bạn không cần tự annotate chúng để có up-to-date checks.

Ví dụ (project đã apply Java plugin):

~~~bash
./gradlew compileJava --console=plain
./gradlew compileJava --console=plain
~~~

Nếu source/options/classpath/output không đổi và history hợp lệ, Gradle thường hiển thị:

~~~text
> Task :compileJava UP-TO-DATE
~~~

Nếu không có Java source, `compileJava` có thể `NO-SOURCE`, không nên cố biến nó thành `UP-TO-DATE`. Nếu chỉ sửa `src/test/java`, `compileJava` có thể tiếp tục up-to-date trong khi `compileTestJava`/`test` cần chạy.

### 18.1. JavaCompile inputs

Đối với Java compilation, output bytes có thể phụ thuộc:

- Source files.
- Compile classpath và ABI của dependency classes.
- Compiler implementation/JDK/toolchain, compiler flags.
- Annotation processors và options.
- Target/source compatibility/`--release`.
- Generated sources/config liên quan.

Không tự tạo một ad-hoc wrapper task với chỉ `inputs.files("src/main/java")` và bỏ qua classpath/flags rồi kỳ vọng incremental compilation đúng như built-in `JavaCompile`.

### 18.2. Test inputs

`Test` task có compiled test classes, runtime classpath, JVM arguments, framework configuration và những properties đã được model. Nhưng nếu test **đọc dữ liệu bên ngoài** không được khai báo (filesystem/network/current time), kết quả có thể nondeterministic; up-to-date/caching với Test không thay thế việc thiết kế tests đáng tin.

### 18.3. Jar outputs

`Jar` là producer file `.jar` thường được `assemble` tiêu thụ. Java classes/resources dependencies được nối qua Gradle task provider/file collection metadata. Đó là lý do wiring bằng Providers và task outputs quan trọng hơn việc tự `dependsOn` lung tung.

## 19. Task state: đọc Gradle output đúng cách

Một bảng trạng thái:

| Gradle console state | Diễn giải | Task action? |
| --- | --- | --- |
| `UP-TO-DATE` | Fingerprints/history hợp lệ | Không |
| `FROM-CACHE` | Khôi phục output từ Build Cache | Không |
| `NO-SOURCE` | Task source-aware không có source phù hợp | Không |
| `SKIPPED` | Conditions/disabled/skip logic | Không |
| Không suffix đặc biệt | Task có thể đã chạy bình thường | Thường có |
| `FAILED` | Task có lỗi | Có thể đã chạy một phần |
| `:task` với `--dry-run` | Chỉ mô phỏng graph | Không có task action |

Không nên coi mọi suffix là “cached”. Khi benchmark, tách rõ:

1. **Configuration time**.
2. **Task execution time**.
3. **Cache restoration/download time**.
4. **Dependency resolution time**.
5. **I/O wait/network**.

`UP-TO-DATE` giúp tránh action, nhưng Gradle vẫn phải xác định task state; một task có hàng triệu input files vẫn có thể tốn thời gian snapshotting nếu mô hình chưa tối ưu.

### 19.1. `--console=plain` hữu ích cho CI

~~~bash
./gradlew renderGreeting --info --console=plain
~~~

Nó giúp logs ổn định hơn trong CI so với rich terminal, nhưng không cam kết output hoàn toàn đồng nhất giữa Gradle versions.

### 19.2. `--offline` là chuyện khác

`--offline` hạn chế dependency resolution network, không buộc Gradle tasks `UP-TO-DATE`. Một build offline vẫn có thể chạy task actions hoặc fail nếu dependencies chưa cached.

## 20. Mẫu lỗi thiết kế và hệ quả

| Thiết kế sai | Hệ quả | Cách sửa |
| --- | --- | --- |
| Task đọc template nhưng không `@InputFile` | Đổi template vẫn có thể `UP-TO-DATE` sai | Thêm file input với normalization đúng |
| Task đọc env var trong action, không khai báo | Env thay đổi không invalid task | Cấu hình `@Input Property<String>` từ Provider |
| Task tạo report nhưng không `@OutputFile` | Không thể up-to-date đúng theo output | Khai báo output file |
| Task khai báo output nhưng không tạo file | Task có thể chạy lại hoặc validation/state bất thường | Ghi output đúng path hoặc điều chỉnh mô hình |
| Hai tasks ghi một output file | Output overlap, race/implicit dependency/cache issue | Mỗi output một producer |
| Output directory quá rộng | Ownership mơ hồ, cache bị vô hiệu | Chia folder output cho task |
| Dùng @Input cho File để theo dõi bytes | Task validation sai/miss tracking | Dùng @InputFile/@InputFiles |
| Không chọn PathSensitivity | Absolute-path cache misses khi workspace khác | Chọn NONE/RELATIVE theo semantics |
| Chọn NONE dù output chứa filename | Up-to-date/cache hit sai khi rename | Dùng RELATIVE/NAME_ONLY phù hợp |
| Chọn NormalizeLineEndings cho raw copy | CRLF -> LF có thể bị bỏ qua dù bytes output khác | Không normalize khi byte changes quan trọng |
| Dùng `@Internal` cho semantic input | False UP-TO-DATE | Đổi thành @Input hoặc @InputFile |
| Dùng now/random làm input mỗi lần | Task luôn chạy | Loại nondeterminism hoặc chọn semantics rõ |
| Dùng `@CacheableTask` cho side-effect publish | Remote action bị skip sai | Không cache tasks có side effects |
| Gọi `get()` trong configuration sớm | Eager resolution, mất lazy wiring | Giữ Provider/flatMap |
| Dùng `mustRunAfter` thay dependency | Producer không chắc có trong graph | `dependsOn` hoặc Provider origin |
| Quên xử lý REMOVED trong incremental task | Stale generated files | Xóa output tương ứng |
| Coi config cache hit là up-to-date | Hiểu sai state | Quan sát task suffix riêng |
| Coi `--dry-run` là test pass | Actions chưa chạy | Chạy tests/task thật |
| `--rerun-tasks` trong mọi CI build | Mất lợi ích incremental/cache | Chỉ dùng khi chẩn đoán |
| Build script ghi file tại configuration time | Outputs không theo task execution | Di chuyển I/O vào @TaskAction |
| Đọc output khi producer chưa có dependency | Implicit dependency validation | Wire TaskProvider.flatMap |

## 21. Debug bằng cách thay một thứ tại một thời điểm

Một bài thực hành có thể làm tuần tự:

1. **Chạy lần đầu** `./gradlew renderGreeting`: task action chạy, tạo `greeting.txt`.
2. **Chạy lần hai** cùng inputs: tìm `UP-TO-DATE`, action không in `Rendered`.
3. **Đổi `-PgreetingPerson=Mai`**: scalar @Input đổi, task chạy, output `Xin chào, Mai!`.
4. **Chạy lại với cùng property**: có thể `UP-TO-DATE`.
5. **Đổi nội dung `templates/greeting.txt`**: @InputFile đổi, task chạy.
6. **Xóa `build/generated/greeting.txt`**: output missing, task tạo lại.
7. **Chạy `copyGreeting`**: Gradle tự chạy render trước nếu cần, copy output.
8. **Chạy lại `copyGreeting`**: cả hai tasks có thể `UP-TO-DATE`.
9. **Dùng `--rerun-tasks`**: action lại in log dù inputs/outputs không đổi.
10. **Chạy Java17 GreetingReader**: đọc output mới, kiểm chứng bytes/Unicode.
11. **Chạy `--configuration-cache`**: xem cache state độc lập với up-to-date.
12. **Nếu bổ sung @CacheableTask** và Build Cache, thử `FROM-CACHE` sau clean trong môi trường có entry.

Ghi lại trạng thái task và thay đổi files cho từng lượt. Không thay đồng thời template, property, output và Gradle version khi mục tiêu là phân biệt nguyên nhân khiến task chạy lại.

### 21.1. Bảng expected behavior

| Tác động | Input fingerprint | Output fingerprint | Kết quả thường thấy |
| --- | --- | --- | --- |
| Chạy đầu tiên | Chưa có history | Chưa có | Execute |
| Chạy lại nguyên trạng | Không đổi | Không đổi | `UP-TO-DATE` |
| Đổi `person` | Đổi | Có thể còn cũ | Execute hoặc cache hit nếu cacheable |
| Đổi nội dung template | Đổi | Có thể còn cũ | Execute |
| Đổi output bytes | Không đổi | Đổi | Execute/restore |
| Xóa output | Không đổi | Missing | Execute/restore |
| Xóa build folder | Có thể giữ input | Missing | Execute hoặc `FROM-CACHE` |
| Đổi task code | Task implementation thay đổi | Chưa biết | Execute hoặc recompute cache key |
| Chỉ chạy `--no-build-cache` | Không đổi | Không đổi | Có thể `UP-TO-DATE` |
| Chạy `--rerun-tasks` | Không đổi | Không đổi | Execute |
| InputFiles rỗng và SkipWhenEmpty | Rỗng | Tùy model | `NO-SOURCE` |
| Chỉ đổi settings không liên quan | Inputs/output không đổi | Không đổi | Có thể `UP-TO-DATE` |

Không xem bảng này là cam kết output status tuyệt đối: Gradle có thể có additional task validation, history invalidation hoặc caching policy.

## 22. Các tình huống khó: timestamp, symlink và môi trường

### 22.1. Timestamp và file size không đủ làm nguồn sự thật

Gradle dùng nội dung và metadata để nhận diện file inputs/outputs, nhưng để tối ưu fingerprinting nó có thể reuse hash khi `lastModified` và size không đổi. Nếu script khác thay bytes rồi đặt lại cùng timestamp/size, nó có thể làm Gradle bỏ lỡ thay đổi. Đây là lý do không biến input snapshot thành một cryptographic monitoring/security mechanism.

### 22.2. Symbolic links

Symlinks có thể khiến path normalization/snapshotting có behavior khác nhau giữa platforms, và Gradle docs có những ràng buộc cho symlink handling. Nếu task theo dõi files qua symlinks, test trên hệ điều hành/FS thực tế, tránh giả định rename symlink luôn tương đương đổi content.

### 22.3. Environment-specific paths

Nếu task output ghi absolute workspace path vào file, `PathSensitivity.NONE` cho input file **không đủ** để đảm bảo relocatability. Absolute path phải được model nếu ảnh hưởng output, hoặc thiết kế output không nhúng machine-specific data.

### 22.4. Encoding

Task `RenderGreeting` sử dụng UTF-8 rõ ràng và ghi newline LF. Nếu task thật lấy encoding từ user configuration, encoding name cũng là semantic input và cần fingerprint. Không dựa vào default platform charset nếu muốn output reproducible giữa Windows/Linux.

### 22.5. Timestamps trong generated files

Generated report chứa `LocalDateTime.now()` sẽ khác mỗi lần task chạy. Nếu timestamp là một phần yêu cầu nghiệp vụ, task cần mô hình thời gian/epoch input hoặc tắt caching/up-to-date theo policy thay vì giả tạo deterministic behavior.

### 22.6. Network và external APIs

Task gọi API lấy dữ liệu thay đổi theo server nhưng không khai báo snapshot/captured response sẽ khó có up-to-date correctness. Tách task download/resolve inputs ra thành artifact file có metadata rõ, hoặc định nghĩa task luôn execute nếu side effect/time-sensitive; không giả định Gradle biết nội dung server từ URL string.

## 23. Tối ưu inputs/outputs trong multi-project build

Trong một repo có `:core`, `:api`, `:app`:

- `:core:compileJava` tạo class files.
- `:api:compileJava` đọc `:core` API/compile classpath.
- `:app:compileJava` đọc API artifacts/dependencies được khai báo.
- `:app:jar` cần outputs từ tasks compile/resources của chính app.

Nếu sửa implementation nội bộ của `:core` mà public ABI không đổi, incremental compilation và compile-classpath normalization có thể giúp hạn chế recompilation trong consumers. Nhưng không khẳng định mọi thay đổi implementation đều được bỏ qua: annotation processors, constant inlining, Gradle/JDK settings và dependency semantics có thể ảnh hưởng kết quả.

### 23.1. Kotlin DSL Provider wiring

Dùng output provider từ task producer cho input consumer thay vì gọi `tasks.getByName(...).outputs.files.singleFile` sớm. Provider chain giữ thông tin producer task và giúp Gradle lập task graph đúng.

### 23.2. Không dùng file path trùng nhau như quan hệ dependency

Nếu module A tạo `build/generated/data.json` và module B đọc file đúng path đó nhưng không khai báo origin task, Gradle không thể suy đoán chính xác task dependency chỉ từ tên đường dẫn. Điều này đặc biệt dễ gây lỗi khi bật `--parallel`.

### 23.3. Outputs và remote cache

Để outputs có thể cache giữa CI agents, cần stable inputs, path normalization phù hợp, không nhúng machine-specific data hoặc secrets và không tạo output trùng lặp ngoài task. Remote Build Cache nên dùng trust/access policy rõ, không tải artifacts từ nguồn không đáng tin rồi thực thi như code.

## 24. Các câu hỏi thường gặp

### 24.1. Up-to-date check có tự bật không?

Có cho những tasks đủ metadata; Gradle hỗ trợ incremental build mặc định. Không có một flag bắt buộc kiểu `--enable-up-to-date`, nhưng task author cần khai báo inputs/outputs chính xác.

### 24.2. Có phải mọi task đều UP-TO-DATE ở lần thứ hai?

Không. Task có thể không có output, có side effects, input động, output bị sửa/xóa, `NO-SOURCE` hoặc có điều kiện buộc chạy lại. Kết quả phụ thuộc task type và build history.

### 24.3. Task đã dùng @InputFile thì còn cần @OutputFile không?

Có, nếu mục tiêu là lưu/kết luận output hợp lệ để skip. Input chỉ cho biết nguồn dữ liệu; Gradle còn cần biết task tạo ra thứ gì và kiểm tra trạng thái output.

### 24.4. @InputFile và @InputFiles khác nhau thế nào?

`@InputFile` dùng cho **một** file, thường với `RegularFileProperty`; `@InputFiles` dùng cho collection `ConfigurableFileCollection` hoặc file tree. Cả hai có thể dùng path normalization.

### 24.5. InputDirectory có bao gồm cả file trong thư mục?

Gradle theo dõi nội dung tree của directory input theo snapshot semantics. Nhưng nếu task chỉ quan tâm subset, khai báo một file collection cụ thể tốt hơn so với đưa toàn bộ thư mục khổng lồ vào inputs không cần thiết.

### 24.6. OutputDirectory có tự tạo thư mục không?

Không nên dựa vào annotation để tạo directory. Task action phải tạo directory/file khi cần (như `target.parentFile.mkdirs()`), hoặc dùng API task phù hợp có behavior tạo output riêng.

### 24.7. `doLast` có tự được theo dõi như output không?

Gradle có thể xét task implementation/action code, nhưng `doLast` không tự khai báo file mà action đọc/ghi. Ad-hoc task vẫn phải dùng `inputs.*` và `outputs.*` chính xác.

### 24.8. Sửa file build.gradle.kts có luôn khiến mọi tasks chạy lại?

Không. Thay đổi cấu hình có thể buộc reconfiguration, nhưng những tasks có input/output/implementation không đổi vẫn có thể up-to-date. Nếu thay chính task action/config ảnh hưởng fingerprint, task có thể rerun.

### 24.9. Task up-to-date có nghĩa code đúng không?

Không. Nó chỉ là kết luận theo **những inputs/outputs đã được model** và history. Nếu thiếu metadata, task có thể skip sai. Tests/validation/security review là trách nhiệm khác.

### 24.10. `clean` có cần cho build hằng ngày?

Thường không. Chạy `clean` luôn phá output state trong `build/`, làm mất lợi ích up-to-date (dù Build Cache có thể phục hồi). Dùng `clean` khi cần điều tra stale outputs, trước release policy đặc biệt hoặc để verify reproducibility.

### 24.11. Vì sao `FROM-CACHE` xuất hiện sau clean?

Vì task cacheable có kết quả output tương ứng trong Build Cache. Không phải local output còn trên disk, và không nên nhầm với `UP-TO-DATE`.

### 24.12. Configuration Cache được reuse thì task có thể chạy không?

Có. Configuration cache reuse chỉ tránh configuration phase. Nếu một task input thay đổi, execution action vẫn có thể chạy.

### 24.13. Có nên gắn @CacheableTask vào mọi task?

Không. Task phải deterministic, side-effect free ngoài declared outputs, đủ inputs và có outputs thích hợp. Publish, deploy, gửi thông báo hay các tác vụ time-sensitive không nên được cache chỉ để nhanh.

### 24.14. Vì sao @PathSensitive.NONE có thể nguy hiểm?

Nếu output phụ thuộc vào tên/đường dẫn input nhưng normalization bỏ qua path, Gradle có thể coi hai input locations tương đương dù output semantics khác. Dùng RELATIVE/NAME_ONLY/ABSOLUTE theo đúng use case.

### 24.15. @Optional và @SkipWhenEmpty có cùng ý nghĩa không?

Không. Optional cho phép một property/file vắng; SkipWhenEmpty nói task không cần thực hiện khi nguồn file set rỗng theo semantics. Không dùng thay nhau.

### 24.16. `InputChanges` có bắt buộc để thấy UP-TO-DATE không?

Không. @Input/@Output đủ để Gradle skip toàn task khi unchanged. InputChanges chỉ cần khi muốn xử lý **một phần** input files thay vì toàn bộ khi task phải chạy.

### 24.17. Có dùng Gradle TestKit để kiểm thử custom task không?

Có. Một functional test có thể chạy build fixture hai lần, assert task outcome `SUCCESS` rồi `UP_TO_DATE`, thay input và assert chạy lại, xóa output rồi assert recomputation. Điều này có giá trị hơn chỉ test helper method.

## 25. Gợi ý functional testing bằng Gradle TestKit

Trong project phát triển Gradle plugin thật (đã có `java-gradle-plugin`/TestKit classpath), có thể viết Java 17/JUnit functional test tương tự:

~~~java
BuildResult first = GradleRunner.create()
        .withProjectDir(projectDir.toFile())
        .withArguments("renderGreeting")
        .withPluginClasspath()
        .build();

BuildResult second = GradleRunner.create()
        .withProjectDir(projectDir.toFile())
        .withArguments("renderGreeting")
        .withPluginClasspath()
        .build();

assertEquals(
    TaskOutcome.UP_TO_DATE,
    second.task(":renderGreeting").getOutcome()
);
~~~

**Đây là mảnh test**, không phải một class Java độc lập để compile: cần imports, TestKit/Gradle plugin fixture setup và file task definition trong temporary project. Nó minh họa cách assert **behavior** thay vì parse logs; `TaskOutcome.UP_TO_DATE` là trạng thái enum thích hợp.

Ở test đầy đủ cần thêm các tình huống:

1. First run tạo output hợp lệ.
2. Second run `UP_TO_DATE`.
3. Đổi scalar input -> task `SUCCESS`, output đổi.
4. Đổi file input -> task `SUCCESS`, output đổi.
5. Xóa output -> task action chạy hoặc cache restore theo policy.
6. Kiểm tra `copyGreeting` được chạy đúng thứ tự khi chỉ yêu cầu consumer task.
7. Test trên cả Windows và Linux nếu handling paths/line endings quan trọng.
8. Test cacheability riêng nếu task được annotate `@CacheableTask`.

Không test `BUILD SUCCESSFUL` text rồi cho rằng task đã up-to-date: task có thể chạy lại và build vẫn successful.

## 26. Checklist code review cho custom tasks

1. Task có một mục tiêu rõ ràng, output ownership rõ.
2. Mọi property **ảnh hưởng output** đều khai báo `@Input` hoặc file input tương ứng.
3. Không khai báo quá nhiều inputs không ảnh hưởng output.
4. File input có `PathSensitivity` phù hợp với semantics output.
5. Classpath dùng `@Classpath`/`@CompileClasspath` nếu thích hợp.
6. Optional/empty file inputs được model chính xác.
7. Output file/directory được khai báo và action tạo đúng nơi.
8. Không có output overlaps giữa tasks.
9. Task action không tự đọc `Project`/env/network ẩn, dùng managed properties/Providers.
10. Tách configuration và execution phases.
11. Dùng `tasks.register`/`tasks.named`/`configureEach` thay eager APIs.
12. Nối producer output với consumer input qua `TaskProvider.flatMap`.
13. Output deterministic với cùng declared inputs; tránh random/timestamp không model.
14. Nếu @CacheableTask, kiểm tra cache security/relocatability và không side effects.
15. Nếu InputChanges, xử lý ADDED/MODIFIED/REMOVED và non-incremental fallback.
16. Quan sát output states bằng `--info`, không tự suy luận từ số giây build.
17. Thử second run unchanged, changed input, deleted output.
18. Nếu unit/functional test, assert `TaskOutcome.UP_TO_DATE` thay vì chỉ `BUILD SUCCESSFUL`.
19. Tách up-to-date check khỏi Build Cache/Configuration Cache.
20. Tránh `clean` mỗi lượt nếu không cần; tận dụng incremental build.
21. Khi nâng Gradle Wrapper, kiểm tra task validation, caching và execution history behavior.
22. Không giả vờ một task mutating remote state là pure output task.
23. Các artifact generated nên nằm dưới `layout.buildDirectory`, không bên trong source tree.
24. Kiểm tra encoding, newline, path normalization trên CI/OS mục tiêu.
25. Bảo vệ build cache/repository permissions và secrets.

## 27. Bài tập củng cố và đáp án

**Câu 1.** Task đọc `config.json` rồi tạo report, nhưng chỉ annotate report với `@OutputFile`. Nếu đổi `config.json` thì sao?

**Đáp án:** Gradle có thể coi task vẫn `UP-TO-DATE` sai vì input chưa được khai báo. Cần `@InputFile` cho config file với path normalization phù hợp.

**Câu 2.** Task có `@InputFile` và `@OutputFile`; chạy hai lần không đổi, lượt thứ hai thường thế nào?

**Đáp án:** `UP-TO-DATE` nếu history hợp lệ, output vẫn khớp và không có yếu tố buộc chạy khác.

**Câu 3.** `@Input` khác `@InputFile` ở đâu?

**Đáp án:** `@Input` cho property values, `@InputFile` cho một file content/location theo file fingerprinting. Không dùng bừa với RegularFileProperty.

**Câu 4.** Vì sao `TaskProvider.flatMap { it.outputFile }` quan trọng?

**Đáp án:** Nó cho consumer input tham chiếu đúng producer output provider và mang metadata để Gradle tự suy ra task dependency.

**Câu 5.** Dùng `mustRunAfter(producer)` có đảm bảo producer được thực thi khi chỉ gọi consumer task không?

**Đáp án:** Không, nó chỉ ràng buộc thứ tự khi producer đã có trong graph. Dùng dependsOn hoặc Provider origin.

**Câu 6.** Hai runs chỉ khác `-PgreetingPerson=Mai` cần invalid task không?

**Đáp án:** Có, nếu `person` là declared `@Input` và giá trị thay đổi.

**Câu 7.** Nếu xóa generated file nhưng inputs không đổi thì task còn UP-TO-DATE không?

**Đáp án:** Thông thường không; Gradle cần tạo/khôi phục output, có thể action chạy hoặc cache restore.

**Câu 8.** `UP-TO-DATE` khác `FROM-CACHE` thế nào?

**Đáp án:** UP-TO-DATE dựa vào output/history còn hợp lệ tại workspace; FROM-CACHE lấy outputs từ Build Cache khi task cacheable.

**Câu 9.** `--no-build-cache` có tắt up-to-date check không?

**Đáp án:** Không, hai cơ chế độc lập.

**Câu 10.** Configuration Cache được reuse thì task action có chắc bị skip không?

**Đáp án:** Không. Cache đó chỉ tối ưu configuration, task vẫn được xét inputs/outputs.

**Câu 11.** `@InputChanges` có cần thiết cho single template -> single report không?

**Đáp án:** Thường không. Có thể regenerate toàn bộ report khi template đổi; khi không đổi up-to-date check đã skip.

**Câu 12.** Khi incremental input file bị xóa, task nên làm gì?

**Đáp án:** Xử lý `ChangeType.REMOVED` và xóa output tương ứng, tránh stale outputs.

**Câu 13.** Khi input directory có 1000 files, @InputDirectory có nghĩa task chỉ process 1 modified file tự động không?

**Đáp án:** Không. Gradle biết task invalid, nhưng muốn task action làm ít hơn thì phải tự triển khai `InputChanges` hoặc tối ưu processing.

**Câu 14.** `@PathSensitive(NONE)` phù hợp khi nào?

**Đáp án:** Khi vị trí/filename input không ảnh hưởng output, chỉ file content ảnh hưởng.

**Câu 15.** Vì sao task không nên dùng `LocalDateTime.now()` trong output mà vẫn gắn @CacheableTask?

**Đáp án:** Cùng declared inputs có thể sinh bytes khác theo thời gian; task nondeterministic, cache/up-to-date có thể sai nếu thời gian không được model.

**Câu 16.** Task không có output có thể được Gradle skip up-to-date giống task tạo file không?

**Đáp án:** Thông thường không. Task cần output để Gradle đánh giá khả năng tái sử dụng công việc theo cơ chế up-to-date.

**Câu 17.** Dùng `outputs.upToDateWhen { false }` có giúp task cache hit nhiều hơn không?

**Đáp án:** Không. Nó buộc Gradle không coi output up-to-date; không phải một kỹ thuật tăng caching.

**Câu 18.** Java 17 `GreetingReader` in gì khi file generated từ default person `Lan`?

**Đáp án:** Một dòng `Xin chào, Lan!`.

**Câu 19.** Nếu task có @Optional input thiếu, action `.get()` sẽ thế nào?

**Đáp án:** Vẫn có thể lỗi nếu property absent; task action phải kiểm tra `orNull`/`isPresent`.

**Câu 20.** Build Cache trên CI mới có thể giúp như thế nào nếu task history không có?

**Đáp án:** Với cacheable task và cache key/entry phù hợp, Gradle có thể khôi phục output `FROM-CACHE` dù workspace chưa có history.

## 28. Sơ đồ tổng kết

~~~text
                 Configuration phase
  settings/build scripts + tasks/register/providers
                         |
                         v
                  Task graph ready
                         |
                         v
                    Execution phase
                         |
                   Task selected
                         |
                         v
         Declared input/output snapshots
                         |
                         v
              Are outputs up-to-date?
                   /           \
                YES             NO
                |                |
                v                v
           UP-TO-DATE        Is task cacheable,
            skip action      is Build Cache hit?
                                /     \
                              YES      NO
                               |        |
                               v        v
                          FROM-CACHE   Run @TaskAction
                          restore      (full or incremental
                          outputs       with InputChanges)
                                            |
                                            v
                                   Record new fingerprints
                                            |
                                            v
                                        Downstream
                                       consumer tasks
~~~

Nhìn vào sơ đồ:

- Đánh dấu `UP-TO-DATE` nghĩa action không chạy và không cần restore from cache.
- `FROM-CACHE` nghĩa outputs được phục hồi từ kết quả cache có cùng key, không chạy action.
- Nếu task action chạy, có thể full hoặc incremental dựa trên file changes và task implementation.
- Nếu task không có outputs, không được kỳ vọng áp dụng chính sơ đồ cache/up-to-date như file-generating task.
- Configuration Cache, nếu bật, ở một nhánh tối ưu khác của configuration phase.

## 29. Tài liệu chính thức và tham khảo

1. Gradle — Incremental build: https://docs.gradle.org/current/userguide/incremental_build.html
2. Gradle — Incremental builds and build caching basics: https://docs.gradle.org/current/userguide/gradle_optimizations.html
3. Gradle — Implementing Custom Tasks: https://docs.gradle.org/current/userguide/implementing_custom_tasks.html
4. Gradle — Advanced Tasks / Incremental tasks: https://docs.gradle.org/current/userguide/custom_tasks.html
5. Gradle — Best Practices for Tasks: https://docs.gradle.org/current/userguide/best_practices_tasks.html
6. Gradle — Creating and Registering Tasks: https://docs.gradle.org/current/userguide/writing_tasks.html
7. Gradle — Lazy Configuration: https://docs.gradle.org/current/userguide/lazy_configuration.html
8. Gradle — Build Cache Concepts: https://docs.gradle.org/current/userguide/build_cache_concepts.html
9. Gradle — Task Output Caching: https://docs.gradle.org/current/userguide/build_cache.html
10. Gradle — Configuration Cache: https://docs.gradle.org/current/userguide/configuration_cache.html
11. Gradle — Configuration Cache Requirements: https://docs.gradle.org/current/userguide/configuration_cache_requirements.html
12. Gradle — Task Input/Output annotations API: https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/package-summary.html
13. Gradle — PathSensitive annotation: https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/PathSensitive.html
14. Gradle — InputChanges API: https://docs.gradle.org/current/javadoc/org/gradle/work/InputChanges.html
15. Gradle — Viewing and Debugging Dependencies: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
16. Gradle — Gradle TestKit: https://docs.gradle.org/current/userguide/test_kit.html

**Lưu ý về phiên bản:** Link `/current/` phản ánh tài liệu Gradle hiện hành. Với repository cụ thể, hãy đối chiếu phiên bản **Gradle Wrapper**, Java toolchain và Gradle task/plugin APIs trước khi sao chép ví dụ. `UP-TO-DATE`, `FROM-CACHE`, `NO-SOURCE`, `SKIPPED` là những trạng thái thật có điều kiện, không phải các lời hứa rằng mọi lượt chạy sẽ cho đúng status giống nhau.

**Kết luận:** Mô hình input/output chính xác là **nền tảng của cả tính đúng đắn và hiệu năng incremental build**. Một task được thiết kế tốt khai báo đủ semantic inputs, chỉ sở hữu outputs của mình, dùng Providers để kết nối với producers, xử lý mọi thay đổi được báo cáo và kiểm tra behavior qua nhiều lượt build. Lúc đó Gradle mới có thể an toàn quyết định khi nào cần chạy action và khi nào có thể tái sử dụng kết quả.
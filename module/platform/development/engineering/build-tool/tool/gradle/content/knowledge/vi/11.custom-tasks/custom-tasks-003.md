# Khai báo đầu vào bằng @Input, @InputFile, @InputFiles và @InputDirectory trong Gradle

## 1. Mục tiêu bài học

Khi tự viết một **custom task** trong Gradle, chỉ đặt code vào `@TaskAction` là chưa đủ để Gradle biết **dữ liệu nào quyết định kết quả**. Ví dụ một task tạo báo cáo phụ thuộc vào tên báo cáo, một file cấu hình, một tập file nội dung và một thư mục tài nguyên. Nếu không khai báo bốn nguồn này thành **task inputs**, Gradle khó phát hiện thay đổi, kiểm tra tính hợp lệ, tái sử dụng kết quả và suy ra dependency với task tạo dữ liệu đầu vào.

Bốn annotation quan trọng trong bài là:

- `@Input`: một **giá trị** ảnh hưởng đến kết quả, chẳng hạn chuỗi, số, Boolean hoặc kiểu dữ liệu có thể lưu dấu vết phù hợp.
- `@InputFile`: **một file** đầu vào.
- `@InputFiles`: **tập file/thư mục** đầu vào.
- `@InputDirectory`: **một thư mục** đầu vào.

Sau bài này, bạn có thể viết custom task Kotlin DSL dùng cả bốn annotation, chạy được bằng Gradle Wrapper, giải thích up-to-date check, chọn kiểu Property thích hợp, xử lý file/thư mục thiếu, hiểu `@PathSensitive`, `@Optional`, `@SkipWhenEmpty`, và tránh những lỗi phổ biến khi nối đầu ra task này vào đầu vào task khác.

Bài thuộc nhóm **Task tùy chỉnh** trong Build Tool Gradle. Các ví dụ ưu tiên Gradle Kotlin DSL trên Gradle 8.x/9.x và cách viết task dùng **Gradle Provider API**; nguyên tắc cũng áp dụng cho task class Java/Groovy nếu đặt annotation ở getter tương ứng.

## 2. Task input là gì và vì sao phải khai báo?

Một task thường có quan hệ:

~~~text
Giá trị cấu hình ──┐
File đầu vào ──────┤
Tập file ──────────┼──> @TaskAction ──> File/thư mục đầu ra
Thư mục đầu vào ───┘
~~~

Gradle dùng metadata của **inputs** và **outputs** để:

1. **Fingerprint** những dữ liệu liên quan trước khi task chạy.
2. Đối chiếu với lần build trước để xem task có thể được đánh dấu `UP-TO-DATE` không.
3. Kiểm tra input bắt buộc có giá trị, đúng loại file/thư mục và có tồn tại không.
4. Khi đầu vào nối với đầu ra do một task khác tạo, **suy ra task dependency**.
5. Hỗ trợ build cache khi task đáp ứng yêu cầu về tính tái lập và caching.
6. Theo dõi file input trong continuous build và một số công cụ phân tích build.

**Khai báo đủ** các đầu vào thật sự ảnh hưởng đến đầu ra. Nếu bỏ sót, Gradle có thể coi task là `UP-TO-DATE` dù kết quả cần thay đổi. Nếu khai báo quá nhiều dữ liệu không ảnh hưởng đến kết quả, task có thể chạy lại không cần thiết.

Một task chỉ khai báo đầu vào nhưng **không có đầu ra được Gradle nhận diện** thường không đủ để tận dụng up-to-date check theo cách thông thường. Khi task tạo file/thư mục, hãy khai báo `@OutputFile` hoặc `@OutputDirectory` tương ứng.

## 3. Bảng phân biệt bốn annotation

| Annotation | Dữ liệu đại diện | Kiểu Property nên dùng trong Kotlin DSL | Gradle kiểm tra/ghi dấu vết |
| --- | --- | --- | --- |
| `@Input` | Giá trị: String, Int, Boolean, enum, một số collection/value types phù hợp | `Property<String>`, `Property<Boolean>`, `ListProperty<T>`, `MapProperty<K,V>` | Giá trị cấu hình ảnh hưởng đến kết quả |
| `@InputFile` | Một file cụ thể | `RegularFileProperty` | Sự tồn tại, loại file, nội dung và path theo normalizer |
| `@InputFiles` | Nhiều file hoặc thư mục | `ConfigurableFileCollection` | Tập file và nội dung theo file normalization |
| `@InputDirectory` | Một thư mục | `DirectoryProperty` | Sự tồn tại của thư mục và nội dung bên trong |

Những kiểu như `Property`, `RegularFileProperty`, `DirectoryProperty`, `ConfigurableFileCollection` được Gradle quản lý để hỗ trợ **lazy configuration**. Đối với task Kotlin, annotation thường đặt trên **getter** bằng cú pháp `@get:Input`, `@get:InputFile`, v.v.

Các kiểu dữ liệu cũng phải đúng ngữ nghĩa:

- Một `String` chứa `"fixtures/config.txt"` vẫn là **giá trị chuỗi** nếu đánh dấu `@Input`; nó không tự khiến Gradle fingerprint nội dung file tại path đó.
- Một `RegularFileProperty` phải được đánh dấu `@InputFile` nếu nó là file đầu vào, không dùng `@Input` để giả vờ file chỉ là giá trị.
- `@InputDirectory` đòi hỏi **directory**; dùng đường dẫn trỏ đến file sẽ gây lỗi validation.
- `@InputFiles` cho phép một collection rỗng nếu không áp dụng thêm quy tắc skip; muốn bỏ qua task khi không có nguồn, xem `@SkipWhenEmpty` ở phần sau.

## 4. Mẫu khai báo custom task Kotlin DSL

Dạng skeleton theo Gradle API:

~~~kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.OutputFile

abstract class ExampleTask : DefaultTask() {
    @get:Input
    abstract val mode: Property<String>

    @get:InputFile
    abstract val configFile: RegularFileProperty

    @get:InputFiles
    abstract val sourceFiles: ConfigurableFileCollection

    @get:InputDirectory
    abstract val assetsDir: DirectoryProperty

    @get:OutputFile
    abstract val outputFile: RegularFileProperty
}
~~~

Đây là **skeleton mô tả các Property**, chưa có `@TaskAction` hay đăng ký task nên không tự tạo kết quả. `@OutputFile` xuất hiện để hoàn chỉnh quan hệ inputs → output; trọng tâm bài vẫn là bốn annotation đầu vào.

Với Kotlin, `@get:Input` đặt annotation lên getter của property (vị trí Gradle dùng để đọc metadata). Với Java/Groovy task class, annotation thường đặt trên phương thức getter `getMode()`, `getConfigFile()`, v.v.

## 5. Thực hành hoàn chỉnh: một task sử dụng cả bốn loại input

Ví dụ sau tạo file báo cáo từ bốn nguồn:

1. `title` là chuỗi `@Input`.
2. `templateFile` là file `@InputFile`.
3. `fragments` là tập file `@InputFiles`.
4. `assetsDir` là thư mục `@InputDirectory`.

Task ghi **một output file** để có thể quan sát thay đổi và up-to-date check.

### 5.1. Chuẩn bị thư mục và các file đầu vào

Giả sử dự án Kotlin DSL đã có Gradle Wrapper (`gradlew`, `gradlew.bat`, `gradle/wrapper/...`). Tạo cấu trúc:

~~~text
input-annotations-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── fixtures/
│   ├── template.txt
│   ├── snippets/
│   │   ├── a.txt
│   │   └── b.txt
│   └── assets/
│       └── icon.txt
├── gradlew
├── gradlew.bat
└── gradle/
    └── wrapper/...
~~~

Ghi nội dung từng file như sau:

**fixtures/template.txt**

~~~text
Header
~~~

**fixtures/snippets/a.txt**

~~~text
Alpha
~~~

**fixtures/snippets/b.txt**

~~~text
Beta
~~~

**fixtures/assets/icon.txt**

~~~text
ICON
~~~

File `fixtures/assets/icon.txt` ở đây là file text minh họa cho nội dung tài nguyên; không cần ảnh thật. Có thể tạo các thư mục và file bằng IDE/editor hoặc công cụ terminal phù hợp. Hãy để `fixtures/assets` tồn tại, vì đây là `@InputDirectory` bắt buộc.

### 5.2. settings.gradle.kts

~~~kotlin
rootProject.name = "input-annotations-demo"
~~~

### 5.3. build.gradle.kts — chương trình đầy đủ

~~~kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

plugins {
    base
}

abstract class BuildSampleReport : DefaultTask() {
    // Giá trị cấu hình ảnh hưởng kết quả.
    @get:Input
    abstract val title: Property<String>

    // Một file; chỉ nội dung file quan trọng.
    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val templateFile: RegularFileProperty

    // Nhiều file trong thư mục snippets.
    @get:InputFiles
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val fragments: ConfigurableFileCollection

    // Một thư mục tài nguyên.
    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val assetsDir: DirectoryProperty

    @get:OutputFile
    abstract val reportFile: RegularFileProperty

    @TaskAction
    fun buildReport() {
        val templateText = templateFile.get().asFile
            .readText(Charsets.UTF_8).trim()

        // Sắp xếp để output ổn định, không phụ thuộc
        // thứ tự duyệt collection/file system.
        val fragmentText = fragments.files
            .sortedBy { it.name }
            .joinToString("|") { file ->
                "${file.name}:${file.readText(Charsets.UTF_8).trim()}"
            }

        val assetsRoot = assetsDir.get().asFile
        val assetText = assetsRoot.walkTopDown()
            .filter { it.isFile }
            .map { file ->
                val relativePath = file.relativeTo(assetsRoot)
                    .path.replace('\\', '/')
                "$relativePath:${file.readText(Charsets.UTF_8).trim()}"
            }
            .toList()
            .sorted()
            .joinToString("|")

        val report = listOf(
            "title=${title.get()}",
            "template=$templateText",
            "fragments=$fragmentText",
            "assets=$assetText"
        ).joinToString("\n", postfix = "\n")

        val target = reportFile.get().asFile
        target.parentFile.mkdirs()
        target.writeText(report, Charsets.UTF_8)
        println("Created demo-report.txt")
    }
}

tasks.register<BuildSampleReport>("buildReport") {
    title.convention(
        providers.gradleProperty("reportTitle").orElse("Demo")
    )
    templateFile.set(
        layout.projectDirectory.file("fixtures/template.txt")
    )
    fragments.from(
        fileTree("fixtures/snippets") {
            include("*.txt")
        }
    )
    assetsDir.set(
        layout.projectDirectory.dir("fixtures/assets")
    )
    reportFile.set(
        layout.buildDirectory.file("reports/demo-report.txt")
    )
}
~~~

**Vì sao ví dụ dùng `.get()` trong `@TaskAction`?** Các Property được cấu hình theo cách lazy, nhưng khi task action thực sự chạy, việc lấy giá trị để đọc và ghi file là hợp lý. Tránh gọi `.get()` từ sớm trong cấu hình chỉ để chuyển sang chuỗi path/File.

**Vì sao có `@PathSensitive`?** Gradle cần biết phần nào của đường dẫn file có ảnh hưởng tới kết quả. Ví dụ đọc *nội dung* template mà không in tên/path của nó nên chọn `NONE`; các tài nguyên có tên/đường dẫn tương đối trong báo cáo nên chọn `RELATIVE`. Phần 8 giải thích các mức này.

**Vì sao sắp xếp file?** `@InputFiles` không xem thứ tự các phần tử collection là phần quyết định fingerprint theo cách một classpath có thứ tự. Nếu task tạo output phụ thuộc vào thứ tự duyệt file ngẫu nhiên, build có thể không tái lập. Trong ví dụ, sắp xếp các phần tử và đường dẫn giúp output ổn định.

### 5.4. Chạy task trên macOS/Linux

~~~bash
./gradlew -q buildReport
cat build/reports/demo-report.txt
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat -q buildReport
Get-Content .\build\reports\demo-report.txt
~~~

**Dòng do task in khi action thực sự chạy lần đầu:**

~~~text
Created demo-report.txt
~~~

**Nội dung chính xác của file build/reports/demo-report.txt với fixtures trên:**

~~~text
title=Demo
template=Header
fragments=a.txt:Alpha|b.txt:Beta
assets=icon.txt:ICON
~~~

Nếu chạy cùng task lần thứ hai mà không đổi input/output, Gradle có thể đánh dấu `UP-TO-DATE` và không thực hiện `@TaskAction` nên dòng `Created demo-report.txt` không xuất hiện. Đó là hành vi mong đợi, không phải lỗi.

### 5.5. Thay đổi giá trị @Input

macOS/Linux:

~~~bash
./gradlew -q buildReport -PreportTitle=Release
~~~

PowerShell:

~~~powershell
.\gradlew.bat -q buildReport -PreportTitle=Release
~~~

File báo cáo có dòng đầu:

~~~text
title=Release
~~~

Các dòng sau giữ nguyên nếu các input file/thư mục không đổi. Vì `title` là `@Input`, Gradle nhận biết khác biệt với lần chạy trước và có thể chạy lại task.

### 5.6. Thay đổi các input file/thư mục

Đổi `fixtures/template.txt` thành `New Header`, Gradle thấy nội dung của **@InputFile** thay đổi. Sửa `fixtures/snippets/a.txt`, Gradle thấy một phần của **@InputFiles** thay đổi. Thêm/sửa `fixtures/assets/new.txt`, Gradle thấy nội dung **@InputDirectory** thay đổi.

Chạy:

~~~bash
./gradlew buildReport --info --console=plain
~~~

Log `--info` có thể nêu lý do task không còn up-to-date. Output file phản ánh các thay đổi do task action đọc. `--info` hữu ích để phân biệt *đầu vào đổi* với *task luôn chạy vì chưa có output/khai báo không đúng*.

## 6. @Input: giá trị cấu hình

`@Input` nói rằng **giá trị** của property ảnh hưởng đến kết quả task. Ví dụ:

~~~kotlin
@get:Input
abstract val title: Property<String>
~~~

Có thể gán:

~~~kotlin
title.set("Báo cáo tháng")
~~~

Hoặc cung cấp giá trị mặc định/CLI:

~~~kotlin
title.convention(
    providers.gradleProperty("reportTitle").orElse("Demo")
)
~~~

`Property<T>` hữu ích vì có thể lấy giá trị từ Provider mà không cần tự đọc môi trường trong task action. Với một property bắt buộc chưa được gán giá trị, Gradle sẽ báo lỗi validation hoặc task không thể lấy giá trị khi chạy.

Những dữ liệu phù hợp với `@Input` gồm:

- Chuỗi tên, chế độ xử lý, mã phiên bản, tên môi trường.
- Số lượng/ngưỡng xử lý (`Property<Int>`), cờ bật/tắt (`Property<Boolean>`).
- Enum hoặc giá trị có cấu trúc được Gradle hỗ trợ cho input snapshots.
- `ListProperty` hoặc `MapProperty` có các phần tử kiểu phù hợp; cần xét việc thứ tự/dữ liệu nào ảnh hưởng kết quả.

**Không dùng @Input cho `File` chỉ vì path của file là String.** Ví dụ:

~~~kotlin
// Anti-pattern: chỉ snapshot chuỗi path, không theo dõi
// nội dung của file tại path đó.
@get:Input
abstract val configPath: Property<String>
~~~

Nếu action lấy chuỗi này để mở file, việc đổi nội dung file mà không đổi chuỗi path có thể không được coi là thay đổi @Input. Hãy dùng `@InputFile RegularFileProperty` nếu chính nội dung file là đầu vào.

### 6.1. Chuỗi "true" từ -P vẫn là chuỗi

Ví dụ:

~~~kotlin
val enabled = providers.gradleProperty("reportEnabled")
    .map { it.toBooleanStrictOrNull() ?: false }
    .orElse(false)
~~~

Đây là một Provider<Boolean> có thể dùng làm nguồn cho `Property<Boolean>` (với task class khai báo `@Input`). Nếu giá trị sai cần được báo lỗi thay vì mặc định false, phải xác thực riêng.

Không kiểm tra Boolean bằng cách chỉ hỏi một chuỗi có rỗng hay không. Các chuỗi `"false"` và `"true"` đều có nội dung.

## 7. @InputFile: đúng một file

Khai báo:

~~~kotlin
@get:InputFile
@get:PathSensitive(PathSensitivity.NONE)
abstract val templateFile: RegularFileProperty
~~~

Trong cấu hình:

~~~kotlin
templateFile.set(
    layout.projectDirectory.file("fixtures/template.txt")
)
~~~

Ý nghĩa:

1. Gradle biết task cần **một file**.
2. File phải tồn tại và là file, không phải directory (nếu không có quy tắc optional thích hợp).
3. Nội dung và các khía cạnh đường dẫn được cấu hình sẽ tham gia fingerprint.
4. Nếu output của task khác được nối trực tiếp vào `templateFile`, Gradle có thể suy ra dependency producer → consumer.

**Không dùng `@InputDirectory`** nếu path trỏ đến một file. Không dùng `@Input` cho path String khi cần theo dõi nội dung.

### 7.1. Path chỉ đến file không tồn tại

Nếu `templateFile` trỏ tới `fixtures/missing.txt`, Gradle thường báo **input file does not exist** trước khi action xử lý. Đây là lỗi validation có ích: task nói rằng file bắt buộc nhưng file chưa được cung cấp.

Nếu một file **có thể vắng mặt hợp lệ**, xem `@Optional` ở mục 10 và xử lý nhánh không có file trong action. Không dùng `try/catch` để che đi thiếu đầu vào bắt buộc.

## 8. @InputFiles: tập file hoặc thư mục

Khai báo:

~~~kotlin
@get:InputFiles
@get:PathSensitive(PathSensitivity.RELATIVE)
abstract val fragments: ConfigurableFileCollection
~~~

Trong cấu hình:

~~~kotlin
fragments.from(
    fileTree("fixtures/snippets") {
        include("*.txt")
    }
)
~~~

Tập này chứa các file `.txt` trực tiếp trong `fixtures/snippets` theo mẫu ví dụ. Bạn cũng có thể:

~~~kotlin
fragments.from(
    layout.projectDirectory.file("fixtures/a.txt"),
    layout.projectDirectory.file("fixtures/b.txt")
)
~~~

**Chỉ là các mẫu thay thế cho cách gán input trong task ở mục 5**, không yêu cầu dùng đồng thời. `from(...)` có thể nhận nhiều nguồn và Gradle sẽ hợp nhất theo cơ chế FileCollection.

`@InputFiles` khác `@InputFile` ở chỗ nó dùng collection. Không nên cố nhét nhiều đường dẫn vào một `RegularFileProperty` hay đánh dấu một collection là `@InputFile`.

### 8.1. Tập file rỗng thì sao?

Nếu `fragments` rỗng mà chỉ có `@InputFiles` và **không** có `@SkipWhenEmpty`, Gradle vẫn có thể chạy task với tập file rỗng. Trong ví dụ, `fragmentText` khi đó là chuỗi rỗng và output có dòng:

~~~text
fragments=
~~~

Nếu chức năng của task chỉ có ý nghĩa khi có file nguồn, hãy dùng thêm **`@SkipWhenEmpty`** để Gradle có thể skip task với trạng thái `NO-SOURCE` khi những input liên quan rỗng.

### 8.2. Thứ tự collection và kết quả task

Theo Gradle, **thứ tự các phần tử của `@InputFiles` thông thường không được tính là thay đổi của input snapshot**. Vì vậy nếu thuật toán của task coi thứ tự là có ý nghĩa, cần khai báo một input bổ sung biểu diễn thứ tự, hoặc chọn API/annotation phù hợp bản chất dữ liệu.

**Không thay bừa bằng `@Classpath` chỉ để “có thứ tự”**: `@Classpath` có cơ chế normalization riêng cho Java classpath. Với file text thông thường, tập file được duyệt/sắp xếp ổn định như ví dụ là cách dễ hiểu hơn.

## 9. @InputDirectory: nguyên một thư mục đầu vào

Khai báo:

~~~kotlin
@get:InputDirectory
@get:PathSensitive(PathSensitivity.RELATIVE)
abstract val assetsDir: DirectoryProperty
~~~

Gán:

~~~kotlin
assetsDir.set(
    layout.projectDirectory.dir("fixtures/assets")
)
~~~

Gradle coi thư mục này là input và fingerprint nội dung bên trong. `@InputDirectory` có ràng buộc **phải là directory**, nếu đường dẫn tương ứng là file thường sẽ báo validation error.

Trong task mẫu, action duyệt `assetsDir` rồi ghi đường dẫn tương đối và nội dung mỗi file. Vì output có sử dụng **cấu trúc đường dẫn bên trong thư mục**, chọn `PathSensitivity.RELATIVE` là hợp lý.

`@InputDirectory` là **một directory đầu vào**, khác `@InputFiles` vốn mô tả một hoặc nhiều đường dẫn/collection. Muốn lấy nhiều thư mục đầu vào, thường cân nhắc `@InputFiles` với FileCollection phù hợp và đặt normalizer đúng. Không tự biến danh sách thư mục thành một DirectoryProperty.

### 9.1. Có cần liệt kê mọi file con bằng @InputFile?

Không. `@InputDirectory` đã nói Gradle theo dõi cả cây nội dung bên trong thư mục. Với task nhận **một root directory có cấu trúc quan trọng**, đây thường là mô hình rõ ràng. Nếu task chỉ xử lý một tập con được lọc theo pattern, `@InputFiles` với FileTree có thể phù hợp hơn.

### 9.2. Khi chỉ muốn bỏ qua thay đổi thư mục rỗng

Gradle còn có `@IgnoreEmptyDirectories` cho input file/directory phù hợp để không coi khác biệt do thư mục rỗng là thay đổi có ý nghĩa. Chỉ dùng nếu kết quả task **không phụ thuộc** vào sự tồn tại/tên của các thư mục rỗng.

Ví dụ modifier:

~~~kotlin
@get:InputDirectory
@get:PathSensitive(PathSensitivity.RELATIVE)
@get:IgnoreEmptyDirectories
abstract val assetsDir: DirectoryProperty
~~~

Đây là **mảnh khai báo thay thế** cho property `assetsDir` trong task class, cần import `org.gradle.api.tasks.IgnoreEmptyDirectories`.

## 10. PathSensitivity: Gradle so sánh phần nào của đường dẫn?

Gradle fingerprint file đầu vào bằng **nội dung** cùng với thông tin đường dẫn theo normalizer. Với file-based inputs, nên chọn mức nhạy path rõ ràng để tránh task chạy lại chỉ vì chuyển workspace hoặc, ngược lại, bỏ qua thay đổi path có ý nghĩa.

| Giá trị | Phần path được coi là quan trọng | Tình huống |
| --- | --- | --- |
| `PathSensitivity.ABSOLUTE` | Đường dẫn tuyệt đối | Chỉ dùng nếu thực sự ảnh hưởng kết quả; thường kém khả năng tái sử dụng cache giữa máy |
| `PathSensitivity.RELATIVE` | Đường dẫn tương đối với root input | Tốt khi cấu trúc thư mục/tên file tương đối quan trọng |
| `PathSensitivity.NAME_ONLY` | Tên file | Ít dùng, khi tên file có ý nghĩa nhưng đường dẫn cha không ảnh hưởng |
| `PathSensitivity.NONE` | Bỏ qua path, xét nội dung | Tốt cho một file input mà tên/vị trí không ảnh hưởng output |

Ví dụ:

~~~kotlin
@get:InputFile
@get:PathSensitive(PathSensitivity.NONE)
abstract val configFile: RegularFileProperty
~~~

Task chỉ đọc nội dung config để tạo output, không nhúng tên file vào output. Vì vậy chuyển file sang một vị trí khác nhưng giữ nội dung có thể không cần chạy lại chỉ vì path đổi.

Với input directory:

~~~kotlin
@get:InputDirectory
@get:PathSensitive(PathSensitivity.RELATIVE)
abstract val sourcesDir: DirectoryProperty
~~~

Nếu task tạo output theo cấu trúc thư mục con, đổi tên/đường dẫn tương đối có thể làm kết quả thay đổi; Gradle phải thấy điều đó.

**Không dùng `NONE` nếu action có đọc hoặc xuất tên/path file.** Ví dụ code tạo report từ `file.name` thì tên file là một phần của ý nghĩa dữ liệu; bỏ qua path có thể tạo cache/up-to-date check sai. Trong ví dụ chính, `fragments` xuất tên file và `assetsDir` xuất đường dẫn tương đối nên dùng RELATIVE.

### 10.1. @Optional cho input có thể vắng mặt

`@Optional` là **modifier**, không thay thế một trong bốn annotation chính. Có thể viết:

~~~kotlin
@get:InputFile
@get:Optional
@get:PathSensitive(PathSensitivity.NONE)
abstract val optionalConfig: RegularFileProperty
~~~

Nếu không gán giá trị thì action phải xử lý an toàn:

~~~kotlin
val optionalFile = optionalConfig.orNull?.asFile
if (optionalFile != null && optionalFile.isFile) {
    println(optionalFile.readText(Charsets.UTF_8))
}
~~~

Hai đoạn trên là **mảnh khai báo và xử lý bổ sung**, cần import `org.gradle.api.tasks.Optional` và được đặt vào custom task class/action thích hợp. Không phải script chạy độc lập.

`@Optional` dùng khi việc vắng input là hợp lệ theo nghiệp vụ. Nếu task thực sự cần file để làm việc, hãy giữ input bắt buộc và để Gradle báo lỗi rõ ràng. Đối với file path đã cấu hình nhưng không tồn tại, đừng giả định action có thể đọc được nó chỉ vì có `@Optional`; code vẫn phải kiểm tra trước khi dùng.

### 10.2. @SkipWhenEmpty cho task kiểu xử lý nguồn

Khi task có ý nghĩa duy nhất nếu có source files, có thể kết hợp:

~~~kotlin
@get:InputFiles
@get:SkipWhenEmpty
@get:PathSensitive(PathSensitivity.RELATIVE)
abstract val sourceFiles: ConfigurableFileCollection
~~~

Modifier này cho phép Gradle skip action khi các input được đánh dấu `@SkipWhenEmpty` không có nguồn xử lý; thường thấy trạng thái `NO-SOURCE`. Nếu có nhiều input có modifier, Gradle xét các nguồn được đánh dấu theo quy tắc của nó. Không dùng modifier này với `@Input` giá trị chuỗi chỉ để thay việc kiểm tra Boolean.

Khi sử dụng `@SkipWhenEmpty`, có thể kết hợp cơ chế incremental file changes (`@Incremental`, `InputChanges`) nếu task hỗ trợ xử lý thay đổi từng file. Đó là cơ chế nâng cao **khác với chỉ kiểm tra UP-TO-DATE**; phần 14 phân biệt thêm.

### 10.3. @NormalizeLineEndings

Khi input là các file văn bản và hệ điều hành có thể đổi `CRLF` ↔ `LF` mà ý nghĩa nội dung không đổi, Gradle hỗ trợ `@NormalizeLineEndings` ở các loại input được hỗ trợ như `@InputFiles` và `@InputDirectory`. Chỉ dùng nếu task thật sự coi hai kiểu xuống dòng là tương đương.

Nếu task của bạn xuất nguyên byte hoặc cần giữ line endings trong output, **không nên normalize** những thay đổi ấy, vì chúng có thể ảnh hưởng kết quả.

## 11. Giữ Provider để Gradle suy ra dependency với task producer

Bốn annotation nói về input của **một task**, nhưng nhiều input được sinh ra từ task khác. Thay vì chép đường dẫn output của producer thành chuỗi, hãy nối thông qua `TaskProvider` và `Property`.

Ví dụ bổ sung, giả định task consumer có:

~~~kotlin
@get:InputFile
@get:PathSensitive(PathSensitivity.NONE)
abstract val templateFile: RegularFileProperty
~~~

Một producer có thể khai báo:

~~~kotlin
abstract class GenerateTemplate : DefaultTask() {
    @get:OutputFile
    abstract val generatedFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val output = generatedFile.get().asFile
        output.parentFile.mkdirs()
        output.writeText("Generated Header\n", Charsets.UTF_8)
    }
}
~~~

Đăng ký producer:

~~~kotlin
val generateTemplate = tasks.register<GenerateTemplate>(
    "generateTemplate"
) {
    generatedFile.set(
        layout.buildDirectory.file("generated/template.txt")
    )
}
~~~

Và trong cấu hình consumer (task `buildReport` của ví dụ chính), **thay thế** lệnh gán `templateFile` từ fixtures bằng:

~~~kotlin
templateFile.set(
    generateTemplate.flatMap { it.generatedFile }
)
~~~

Các mảnh ví dụ này cần đặt vào cùng build.gradle.kts với `BuildSampleReport` đã định nghĩa ở mục 5, và chỉ dùng **một** nguồn gán cho `templateFile`. Nếu triển khai theo cách đó, chạy riêng `./gradlew buildReport` có thể tự kéo theo `generateTemplate`: Gradle hiểu producer output là input của consumer.

Ở đây:

- `@OutputFile` trên producer đánh dấu file kết quả chính thức.
- `generateTemplate` có kiểu `TaskProvider<GenerateTemplate>`.
- `flatMap { it.generatedFile }` lấy Provider của output file mà **giữ metadata task sinh ra file**.
- `templateFile.set(...)` nối Provider đầu ra với input file.
- Gradle có thể suy ra task dependency; không cần thêm `dependsOn("generateTemplate")` cho đúng mối nối này.

**Lưu ý:** Chỉ cùng trỏ vào một path thô là **không đủ**:

~~~kotlin
// Không chuyển được thông tin ai là producer.
templateFile.set(
    layout.buildDirectory.file("generated/template.txt")
)
~~~

Nếu consumer chạy khi producer chưa tạo file, input có thể thiếu. Nếu hai task cùng chạy nhưng không có dependency đúng, Gradle còn có thể báo lỗi **implicit dependency** hoặc các vấn đề khi chạy song song.

### 11.1. Cách nối nhiều file

Nếu producer có `@OutputDirectory DirectoryProperty`, còn consumer có `@InputFiles ConfigurableFileCollection`, thường dùng:

~~~kotlin
sourceFiles.from(
    generateSources.flatMap { it.outputDirectory }
)
~~~

Đây là **mảnh minh họa API**: giả định `generateSources` là TaskProvider của class có property `outputDirectory`. Phải khai báo producer thực tế và output property tương ứng trước khi đưa vào build script.

Với `ConfigurableFileCollection`, phương thức `from(...)` nhận nhiều nguồn/Provider. Nó giúp mô hình hóa một tập file mà không cần gọi `.get()` sớm.

## 12. Cách khai báo input ở runtime API thay cho annotation

Không phải task nào cũng cần một class riêng. Với **ad-hoc task** đăng ký trong build script, Gradle hỗ trợ runtime API:

~~~kotlin
tasks.register("adHocReport") {
    val input = layout.projectDirectory.file("fixtures/template.txt")
    val output = layout.buildDirectory.file("reports/ad-hoc.txt")

    inputs.property("mode", "demo")
    inputs.file(input)
        .withPropertyName("template")
        .withPathSensitivity(PathSensitivity.NONE)
    outputs.file(output)

    doLast {
        val target = output.get().asFile
        target.parentFile.mkdirs()
        target.writeText(
            input.asFile.readText(Charsets.UTF_8),
            Charsets.UTF_8
        )
        println("Ad-hoc report created")
    }
}
~~~

Đây là **task bổ sung vào build.gradle.kts đã import `PathSensitivity` ở mục 5** và sử dụng file fixture `fixtures/template.txt` đã có. Khi chạy lần đầu:

~~~bash
./gradlew -q adHocReport
~~~

Dòng task in ra:

~~~text
Ad-hoc report created
~~~

Ánh xạ ý tưởng:

- `inputs.property(...)` tương tự `@Input`.
- `inputs.file(...)` tương tự `@InputFile`.
- `inputs.files(...)` tương tự `@InputFiles`.
- `inputs.dir(...)` tương tự `@InputDirectory`.
- `outputs.file(...)` tương tự `@OutputFile`.

Khi task nhiều property hoặc được sử dụng ở nhiều project, **custom task class với annotation** thường dễ bảo trì hơn ad-hoc task. Tránh cấu hình input/output trong `doLast`: chúng phải được Gradle biết **trước khi quyết định có cần thực thi action không**.

## 13. Up-to-date check, build cache và thay đổi đầu vào

Giả sử lần đầu `buildReport` tạo `build/reports/demo-report.txt`. Gradle có thể lưu snapshot của:

- `title` từ `@Input`.
- Nội dung `templateFile` từ `@InputFile`.
- Các file được `fragments` cung cấp từ `@InputFiles`.
- Cấu trúc và nội dung của `assetsDir` từ `@InputDirectory`.
- Output report được `@OutputFile` khai báo.

Ở lần chạy tiếp theo:

| Thay đổi | Kết quả dự kiến |
| --- | --- |
| Không đổi input/output và task implementation | Có thể `UP-TO-DATE`, không chạy action |
| Đổi `-PreportTitle` | `@Input` thay đổi, task cần tạo lại output |
| Sửa nội dung template.txt | `@InputFile` thay đổi |
| Thêm/sửa/xóa file trong snippets | `@InputFiles` snapshot thay đổi |
| Thêm/sửa/xóa file trong assets | `@InputDirectory` snapshot thay đổi theo normalization |
| Xóa file report output | Output thiếu, Gradle cần xử lý lại |
| Chỉ đổi vị trí template nhưng giữ nội dung, `PathSensitivity.NONE` | Path đổi có thể không làm input snapshot thay đổi |
| Đổi tên một file được task đưa tên vào output, `PathSensitivity.RELATIVE` | Đường dẫn tương đối thay đổi, Gradle có thể phát hiện |

**Phân biệt hai loại tối ưu hóa:**

- `UP-TO-DATE`: kiểm tra trạng thái input/output của lần build hiện tại với lịch sử tại workspace.
- `FROM-CACHE`: khôi phục kết quả từ **build cache** nếu task đã được đánh dấu cacheable và các điều kiện của cache được đáp ứng.

Custom task có `@Input` và `@OutputFile` **không đương nhiên được cache kết quả giữa máy**. Task muốn dùng build cache cần thiết kế deterministic, khai báo đầy đủ input/output, và có thể cần `@CacheableTask`/cấu hình caching phù hợp. Không nên thêm `@CacheableTask` cho task có output phụ thuộc thời gian hiện tại, mạng không được khai báo hoặc random không kiểm soát.

## 14. @InputFiles khác incremental file processing

Một điểm dễ nhầm: Gradle nói task “incremental build” khi nó biết có thể bỏ qua task không thay đổi. Nhưng **xử lý tăng dần từng file** là một cơ chế nâng cao hơn.

Với `@InputFiles` thông thường:

1. Nếu bất kỳ file liên quan đổi, task có thể chạy lại.
2. Bản thân task có thể **xử lý toàn bộ tập file** một lần nữa.
3. Annotation không tự cung cấp danh sách “file nào vừa được thêm/sửa/xóa” vào action.

Nếu muốn chỉ xử lý file thay đổi, task có thể dùng `@Incremental` trên file input được hỗ trợ và thêm `InputChanges` vào `@TaskAction`. Gradle cung cấp `getFileChanges(...)` để biết các thay đổi có thể xử lý, đồng thời có thể báo lần chạy là **non-incremental** trong một số tình huống.

Ví dụ chữ ký API (không phải class chạy độc lập):

~~~kotlin
@get:InputFiles
@get:Incremental
@get:PathSensitive(PathSensitivity.RELATIVE)
abstract val sourceFiles: ConfigurableFileCollection

@TaskAction
fun update(changes: InputChanges) {
    if (!changes.isIncremental) {
        // Tái tạo toàn bộ output theo nhu cầu.
    }
    for (change in changes.getFileChanges(sourceFiles)) {
        // Xử lý ADDED, MODIFIED, REMOVED.
    }
}
~~~

Cần import `org.gradle.api.tasks.Incremental` và `org.gradle.work.InputChanges`. Một implementation hoàn chỉnh còn phải cập nhật hoặc xóa output tương ứng và bảo đảm tính đúng khi mọi thứ chạy lại. **Không** sử dụng mảnh trên thay thế task ví dụ nếu chưa thiết kế thuật toán incremental đúng.

## 15. Các lỗi thường gặp và cách sửa

| Dấu hiệu | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| File đổi nhưng task vẫn `UP-TO-DATE` | Đường dẫn file chỉ được đánh dấu `@Input` kiểu String hoặc file không được khai báo | Dùng `@InputFile` hoặc `@InputFiles` thực sự |
| `Input file ... does not exist` | Property bắt buộc chưa có file, producer chưa chạy, sai path | Kiểm tra path, task tạo file và Provider dependency |
| `Expected an input file but found directory` | Dùng `@InputFile` cho directory | Đổi sang `@InputDirectory` hoặc chỉ ra file đúng |
| `Expected an input directory but found file` | Dùng `@InputDirectory` cho file | Đổi sang `@InputFile` |
| Tập file rỗng nhưng task vẫn chạy | `@InputFiles` không tự skip khi rỗng | Dùng `@SkipWhenEmpty` nếu đúng nghiệp vụ |
| Chuyển repository sang máy khác khiến task phải chạy lại | Path normalization quá nhạy, thường dùng ABSOLUTE | Dùng NONE/RELATIVE khi path tuyệt đối không ảnh hưởng output |
| Đổi tên file làm output đổi nhưng Gradle không phát hiện | Dùng `PathSensitivity.NONE` trong khi action đọc tên/path | Chọn RELATIVE hoặc NAME_ONLY đúng dữ liệu |
| `Missing normalization annotation` | File input chưa có normalizer cần thiết cho caching/validation | Thêm `@PathSensitive` hoặc classpath annotation phù hợp |
| Truyền file bằng `.get().asFile` sớm | Mất lazy behavior và có thể mất producer metadata | Giữ Provider cho đến task action |
| Task A sinh file, task B đọc nhưng chạy không theo thứ tự | Dùng raw path, không nối output→input | Dùng TaskProvider.flatMap hoặc dependsOn đúng nghĩa |
| Output thay đổi theo thứ tự filesystem | Action duyệt tập file không ổn định | Sắp xếp input trước khi tạo output |
| Output đổi mà Gradle không biết | Task không khai báo output đúng hoặc output bị ghi ngoài vùng khai báo | Khai báo `@OutputFile`/`@OutputDirectory` chính xác |
| Configuration Cache báo lỗi ở action | Code task action truy cập Project/Script state không được hỗ trợ | Đưa dữ liệu vào Property trong configuration, action chỉ đọc input riêng |
| Một property bị báo không có annotation | Gradle thấy getter task property chưa phân loại | Thêm annotation đúng hoặc `@Internal` nếu không phải input/output |
| Thêm annotation lên field Kotlin nhưng Gradle vẫn không thấy | Chưa dùng đúng annotation target của Kotlin | Dùng `@get:Input`, `@get:InputFile`, ... trên abstract property |
| Dùng @Input cho secret và in log | Lộ cấu hình nhạy cảm trong CI/log/build metadata | Dùng cơ chế quản lý secret và tránh xuất giá trị |

**Cách nghĩ khi sửa lỗi:** trước tiên hỏi “dữ liệu này có ảnh hưởng output không?”, tiếp theo hỏi “đó là giá trị, file, tập file hay thư mục?”, cuối cùng hỏi “Gradle có giữ được thông tin nguồn gốc và normalization phù hợp không?”.

## 16. Checklist thiết kế một custom task mới

1. Liệt kê những **giá trị cấu hình** ảnh hưởng kết quả và khai báo bằng `@Input`.
2. Liệt kê **file đơn** và khai báo bằng `@InputFile RegularFileProperty`.
3. Liệt kê **tập file** và khai báo bằng `@InputFiles ConfigurableFileCollection`.
4. Liệt kê **thư mục đầu vào** và khai báo bằng `@InputDirectory DirectoryProperty`.
5. Chọn `@PathSensitive` phù hợp với **cách action thực sự dùng tên/path**.
6. Nếu một đầu vào có thể vắng mặt hợp lệ, cân nhắc `@Optional`; nếu tập source rỗng khiến task không có việc, cân nhắc `@SkipWhenEmpty`.
7. Khai báo output bằng `@OutputFile`/`@OutputDirectory` và giữ output riêng cho từng task khi khả thi.
8. Gán bằng `set(...)`, `convention(...)`, `from(...)` với Provider/TaskProvider; hạn chế gọi `get()` lúc cấu hình.
9. Trong `@TaskAction`, chỉ đọc property của **chính task**, tạo output đúng nơi đã khai báo và bảo đảm kết quả deterministic.
10. Chạy task ít nhất hai lần, sau đó thay đổi lần lượt một loại input để xem hành vi up-to-date/validation.
11. Dùng `--info` khi cần lý giải tại sao Gradle chạy lại hay skip task.
12. Với input do task khác tạo, nối đúng output Provider để Gradle có thể suy ra dependency.

## 17. Bài tập tự kiểm tra

**Câu 1.** Task chỉ nhận `Property<String> environmentName`. Dùng annotation gì?

**Đáp án:** `@Input`, vì đây là một giá trị cấu hình.

**Câu 2.** Task đọc nội dung `config.yml` nhưng property chỉ là String `"config.yml"` được đánh dấu `@Input`. Có đủ không?

**Đáp án:** Không. Gradle chỉ thấy chuỗi path; nên dùng `@InputFile RegularFileProperty` để theo dõi nội dung file.

**Câu 3.** Task cần tập file `.txt` trong thư mục docs. Nên dùng gì?

**Đáp án:** `@InputFiles` với `ConfigurableFileCollection` hoặc FileTree được gán qua `from(...)`. Nếu muốn theo dõi toàn bộ một thư mục như một input duy nhất, `@InputDirectory` cũng có thể phù hợp tùy logic.

**Câu 4.** Một task nhận `fixtures/assets` và cần biết tên các file con. Có nên đặt `@PathSensitive(NONE)` không?

**Đáp án:** Không. Tên/đường dẫn tương đối ảnh hưởng kết quả; nên dùng `RELATIVE`.

**Câu 5.** Chạy task lần thứ hai mà không có dòng println trong action, có nghĩa custom task không tồn tại?

**Đáp án:** Không. Task có thể được Gradle đánh dấu `UP-TO-DATE` và skip action vì inputs/outputs không đổi.

**Câu 6.** Producer có outputFile được đánh dấu `@OutputFile`; consumer có inputFile được đánh dấu `@InputFile`. Làm sao nối để Gradle tự thêm producer vào graph?

**Đáp án:** Dùng `consumer.inputFile.set(producer.flatMap { it.outputFile })`, trong đó producer là TaskProvider phù hợp.

**Câu 7.** Source file collection rỗng nhưng vẫn muốn task kết thúc `NO-SOURCE`. Cần thêm gì?

**Đáp án:** `@SkipWhenEmpty` với annotation file input phù hợp và định nghĩa đúng nguồn task.

**Câu 8.** `@InputFiles` có tự làm task xử lý đúng mỗi file vừa thay đổi không?

**Đáp án:** Không. Cần cơ chế `@Incremental`/`InputChanges` và triển khai thuật toán cập nhật output đúng.

## 18. Kết luận thực hành

Bốn annotation mô tả **bốn kiểu dữ liệu khác nhau**:

~~~text
@Input          -> giá trị
@InputFile      -> một file
@InputFiles     -> một collection file/directory
@InputDirectory -> một thư mục
~~~

Hãy chọn annotation theo **dữ liệu task thực sự sử dụng**. Với file và directory, `@PathSensitive` xác định thành phần đường dẫn nào ảnh hưởng snapshot; với nguồn có thể thiếu hoặc rỗng, `@Optional` và `@SkipWhenEmpty` diễn tả đúng điều kiện chạy. Kết hợp Property/Provider và khai báo output đúng giúp Gradle thực hiện validation, tính up-to-date, hỗ trợ caching và suy ra dependency giữa các task.

## 19. Tài liệu chính thức

- Gradle – Implementing Custom Tasks: https://docs.gradle.org/current/userguide/implementing_custom_tasks.html
- Gradle – Incremental Build (Task Inputs and Outputs): https://docs.gradle.org/current/userguide/incremental_build.html
- Gradle – Best Practices for Tasks: https://docs.gradle.org/current/userguide/best_practices_tasks.html
- Gradle – Lazy Configuration / Provider API: https://docs.gradle.org/current/userguide/lazy_configuration.html
- Gradle – Validation Problems: https://docs.gradle.org/current/userguide/validation_problems.html
- Gradle – Configuration Cache Requirements: https://docs.gradle.org/current/userguide/configuration_cache_requirements.html
- Gradle – IncrementalTaskInputs / InputChanges concepts: https://docs.gradle.org/current/userguide/custom_tasks.html

Các URL `current` trỏ đến tài liệu của phiên bản Gradle hiện hành. Khi dùng trong repository thực tế, đối chiếu **phiên bản Gradle Wrapper** và tài liệu đi kèm vì API, cảnh báo validation và yêu cầu cache có thể thay đổi giữa các phiên bản.
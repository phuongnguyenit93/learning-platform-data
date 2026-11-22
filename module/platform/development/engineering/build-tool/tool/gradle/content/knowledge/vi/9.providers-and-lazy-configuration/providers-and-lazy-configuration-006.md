# Liên kết đầu ra task với đầu vào task khác để suy ra dependency trong Gradle

## 1. Mục tiêu bài học

Trong một Gradle build, task tạo ra dữ liệu (producer) thường được nối với task sử dụng dữ liệu đó (consumer). Ví dụ: sinh mã nguồn rồi biên dịch, tạo tài liệu rồi đóng gói, tạo JAR rồi sao chép sang thư mục phân phối.

Cách khai báo tốt là **nối đầu ra của producer trực tiếp vào đầu vào của consumer bằng Provider/Property**, để Gradle hiểu cả *dữ liệu nào được dùng* và *task nào cần chạy trước*. Khi mối nối mang thông tin producer, Gradle có thể **suy ra task dependency**; consumer không phải tự liệt kê `dependsOn(producer)` cho từng nguồn dữ liệu.

Sau bài học, bạn có thể:

1. Phân biệt đường dẫn file với Provider mang **thông tin task tạo file**.
2. Khai báo đầu ra bằng `@OutputFile`/`@OutputDirectory`, đầu vào bằng `@InputFile`/`@InputFiles`/`@InputDirectory`.
3. Kết nối `TaskProvider.flatMap { it.outputFile }` đến `RegularFileProperty.set(...)`.
4. Quan sát `generateNote` tự xuất hiện khi chỉ yêu cầu `readNote`.
5. Dùng `map` và `flatMap` đúng kiểu, giữ tính lazy và cấu hình tránh realize task sớm.
6. Nhận biết trường hợp Gradle **không suy ra dependency** khi dùng path thô hoặc cắt đứt chuỗi Provider.
7. Hiểu ảnh hưởng đến task graph, `--dry-run`, `UP-TO-DATE`, build cache, Configuration Cache và chạy song song.
8. Biết khi nào cần `dependsOn`, `builtBy` hoặc một quan hệ khác.

Đây là bài về **Provider và cấu hình lười** (lazy configuration) trong Gradle. Mục tiêu là khai báo quan hệ dữ liệu đúng ngay trong build logic, không tự điều khiển thứ tự bằng mã chạy tay trong task action.

## 2. Bản chất của inferred task dependency

Giả sử có hai task:

- `generateNote`: tạo `build/generated/note.txt`.
- `readNote`: đọc chính file đó để in nội dung.

Quan hệ công việc cần có là:

~~~text
Task generateNote
  @OutputFile outputFile
        |
        | Provider<RegularFile>, gắn với producer generateNote
        v
Task readNote
  @InputFile inputFile
        |
        v
  @TaskAction đọc file
~~~

Gradle biết rằng `readNote` cần kết quả do `generateNote` tạo. Khi chỉ yêu cầu `readNote`, Gradle có thể tự đưa `generateNote` vào task graph.

**Inferred dependency** là dependency Gradle suy ra từ việc kết nối **đầu ra do task khác sản xuất** với **đầu vào của task tiêu thụ**, nếu thông tin producer còn được giữ trong Provider/FileCollection. Nó có tác dụng tương tự một quan hệ công việc bắt buộc: producer được xét trước consumer.

Để suy ra đúng, cần đủ ba ý:

1. **Producer công bố đầu ra** với metadata đúng (`@OutputFile`, `@OutputDirectory`, hoặc `outputs.file/dir`).
2. **Consumer công bố đầu vào** tương ứng (`@InputFile`, `@InputFiles`, `inputs.file/files`, v.v.).
3. **Mối nối giữ nguồn gốc task**, chẳng hạn consumer nhận `TaskProvider.flatMap { it.outputFile }`, hoặc một `ConfigurableFileCollection` nhận `TaskProvider`.

Chỉ biết **hai task có đề cập cùng một đường dẫn file** không đủ để tạo quan hệ bền vững: một chuỗi như `"build/generated/note.txt"` chỉ nói file ở đâu, không nói *ai tạo ra nó*.

### 2.1. Task graph và dữ liệu là hai khía cạnh khác nhau

Khi viết:

~~~kotlin
tasks.named("readNote") {
    dependsOn("generateNote")
}
~~~

bạn nói “hãy chạy task generateNote trước readNote”. Nhưng chỉ riêng câu lệnh này **chưa mô tả readNote tiêu thụ file nào**. Nếu sau đó producer đổi vị trí output, consumer vẫn có thể đọc path cũ.

Khi nối trực tiếp Provider của đầu ra vào Property của đầu vào, cấu hình ghi rõ:

~~~text
consumer.inputFile = producer.outputFile
~~~

Gradle nhận được **đường dẫn dữ liệu, dependency và metadata đầu vào/đầu ra** trong một mối quan hệ. Đây là cách ưu tiên khi task tiêu thụ artifact/file thực sự do task khác tạo.

### 2.2. Suy ra dependency khác mustRunAfter

`mustRunAfter(producer)` chỉ giới hạn thứ tự **nếu cả hai task đã có trong graph**; lệnh chỉ gọi consumer không tự bổ sung producer. `shouldRunAfter` còn chỉ là ưu tiên mềm. Nếu consumer cần dữ liệu của producer, dùng quan hệ dữ liệu/`dependsOn`, không dùng các cờ ordering để thay thế dependency.

## 3. Bốn kiểu API nền tảng

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `Provider<T>` | Trình cung cấp giá trị kiểu T, đánh giá khi cần | `providers.gradleProperty("message")` |
| `Property<T>` | Provider có thể được gán/định nghĩa convention | `message.set(provider)` |
| `RegularFileProperty` | Property tham chiếu một file qua `RegularFile`; dùng cho output/input một file | `outputFile.set(layout.buildDirectory.file("..."))` |
| `DirectoryProperty` | Property tham chiếu một thư mục | `outputDirectory.set(layout.buildDirectory.dir("..."))` |
| `ConfigurableFileCollection` | Tập file/file tree có thể nhận nhiều nguồn, gồm task hoặc Provider | `inputFiles.from(producer)` |
| `TaskProvider<T>` | Tham chiếu lazy đến task kiểu T | `tasks.register<GenerateNote>("generateNote")` |

`Provider` giữ lại **công thức lấy giá trị** và có thể giữ metadata nguồn gốc task. `Property.set(provider)` nối consumer với Provider nguồn thay vì chốt một giá trị quá sớm.

Các kiểu `RegularFileProperty`, `DirectoryProperty`, `ConfigurableFileCollection` còn giúp Gradle xác định file input/output chính xác. Chúng không chỉ là cách viết đẹp cho `java.io.File`.

### 3.1. `map` hay `flatMap`?

- Dùng **`map`** khi từ một giá trị T muốn tạo ra một giá trị U thông thường. Ví dụ: `Provider<RegularFile>.map { it.asFile.name }` tạo `Provider<String>`.
- Dùng **`flatMap`** khi lambda trả lại **một Provider khác**. Ví dụ `TaskProvider<GenerateNote>.flatMap { it.outputFile }` biến thành `Provider<RegularFile>` nhưng vẫn liên hệ với task tạo ra file.

Ví dụ đúng:

~~~kotlin
val producer: TaskProvider<GenerateNote> =
    tasks.register<GenerateNote>("generateNote")

val producedFile: Provider<RegularFile> =
    producer.flatMap { it.outputFile }
~~~

Đây là **đoạn minh họa kiểu**, chưa phải build script độc lập: task class `GenerateNote` phải có `outputFile` tương ứng.

Trong build thật, bạn thường không cần khai báo biến `producedFile` riêng; có thể dùng thẳng `inputFile.set(producer.flatMap { it.outputFile })`.

**Không gọi `.get()` trong bước cấu hình chỉ để lấy một path** nếu có thể giữ Provider. `get()` ép đánh giá ngay, có thể realize task sớm hoặc làm mất mối liên hệ được Gradle dùng để suy ra dependency khi người viết chuyển giá trị thành `File`/chuỗi thô.

## 4. Ví dụ chạy được: producer tạo file, consumer đọc file

Đây là bài thực hành trọng tâm. Không cần Java source hoặc plugin bên ngoài. Dùng một Gradle Wrapper hợp lệ và Kotlin DSL trên phiên bản Gradle hỗ trợ các API trình bày dưới đây (Gradle 8.x/9.x).

Cấu trúc:

~~~text
task-wiring-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
└── gradle/
    └── wrapper/
        ├── gradle-wrapper.properties
        └── gradle-wrapper.jar
~~~

Nếu chưa có Wrapper, tạo từ một bản cài Gradle đã được dự án chấp thuận rồi commit bộ file Wrapper theo quy trình thông thường.

### 4.1. settings.gradle.kts

~~~kotlin
rootProject.name = "task-wiring-demo"
~~~

### 4.2. build.gradle.kts — toàn bộ chương trình

~~~kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

plugins {
    base
}

// Producer: nhận một chuỗi, ghi ra một file.
abstract class GenerateNote : DefaultTask() {
    @get:Input
    abstract val message: Property<String>

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val file = outputFile.get().asFile
        file.parentFile.mkdirs()
        file.writeText(message.get() + "\n", Charsets.UTF_8)
        println("GENERATE:" + file.name)
    }
}

// Consumer: đọc file producer đã tạo.
abstract class ReadNote : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val inputFile: RegularFileProperty

    @TaskAction
    fun read() {
        val text = inputFile.get().asFile
            .readText(Charsets.UTF_8)
            .trimEnd()
        println("CONSUME:" + text)
    }
}

// TaskProvider giữ producer ở dạng lazy.
val generateNote = tasks.register<GenerateNote>("generateNote") {
    message.set(
        providers.gradleProperty("noteText")
            .orElse("Xin chao Gradle")
    )
    outputFile.set(layout.buildDirectory.file("generated/note.txt"))
}

// Không khai báo dependsOn.
// Đầu vào consumer nhận Provider của đầu ra producer.
tasks.register<ReadNote>("readNote") {
    inputFile.set(generateNote.flatMap { it.outputFile })
}
~~~

**Điểm cần đọc kỹ:** dòng cuối `inputFile.set(generateNote.flatMap { it.outputFile })` là điểm **nối producer → consumer**. Nó vừa cung cấp vị trí file, vừa giữ mối liên hệ với `generateNote`. Từ đó Gradle có thể đưa producer vào kế hoạch khi người dùng yêu cầu consumer.

Trong hai task class:

- `@get:Input` khai báo `message` là input có ảnh hưởng đến nội dung file sinh.
- `@get:OutputFile` khai báo file mà producer tạo, qua `RegularFileProperty`.
- `@get:InputFile` khai báo file consumer cần, qua `RegularFileProperty`.
- `@get:PathSensitive(PathSensitivity.NONE)` nêu rõ việc xử lý file chỉ quan tâm nội dung, không dùng tên/path file để quyết định kết quả.
- `@TaskAction` định nghĩa phần công việc thật của task.
- `layout.buildDirectory.file(...)` tạo Provider cho file trong thư mục build thay vì tự nối chuỗi path.
- `providers.gradleProperty("noteText").orElse(...)` là nguồn cấu hình lazy; có thể ghi đè bằng `-PnoteText=...`.

Đặc biệt: `file.writeText(...)` và `inputFile.get().asFile.readText(...)` ở **task action**. Ở thời điểm đó Gradle đã lập lịch producer chạy trước consumer. Việc dùng `.get()` ở đây là đúng mục đích vì task cần giá trị file cụ thể để đọc/ghi.

### 4.3. Chạy lần đầu

macOS/Linux:

~~~bash
./gradlew -q clean readNote
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat -q clean readNote
~~~

`base` plugin cung cấp task `clean`, giúp loại kết quả của lần chạy trước khi minh họa. Hai dòng do các task trong ví dụ in ra:

~~~text
GENERATE:note.txt
CONSUME:Xin chao Gradle
~~~

Gradle tự chạy `generateNote` **dù lệnh CLI chỉ nêu `readNote`** (ngoài `clean`). Nếu bỏ mối nối provider trong consumer, không thể dựa vào riêng tên path để chắc chắn producer có trong graph.

### 4.4. Quan sát task graph mà chưa chạy task action

~~~bash
./gradlew readNote --dry-run --console=plain
~~~

Output của Gradle thường có các dòng tương đương:

~~~text
:generateNote SKIPPED
:readNote SKIPPED
~~~

Trong `--dry-run`, action không chạy thật; chữ `SKIPPED` trong mô phỏng không có nghĩa task lỗi hay input bị thiếu. Điểm quan trọng là **`:generateNote` có trong graph và được xếp trước `:readNote`**, dù bạn không gọi `generateNote` trong CLI.

Lệnh dùng PowerShell:

~~~powershell
.\gradlew.bat readNote --dry-run --console=plain
~~~

### 4.5. Đổi input, quan sát producer làm lại công việc

~~~bash
./gradlew -q readNote -PnoteText="Hello build"
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat -q readNote '-PnoteText=Hello build'
~~~

Dòng do task in ra khi nội dung đổi so với lần build gần nhất:

~~~text
GENERATE:note.txt
CONSUME:Hello build
~~~

Do `message` được khai báo là `@Input`, Gradle biết input thay đổi và chạy lại producer. Vì producer khai báo `@OutputFile`, Gradle cũng có thể kiểm tra output ở lần tiếp theo và đánh dấu `UP-TO-DATE` khi phù hợp.

Với lần chạy thứ hai **cùng noteText**, producer có thể không in dòng `GENERATE` vì đã `UP-TO-DATE`; consumer của ví dụ này không khai báo output nên action của nó thường vẫn được chạy. Điều đó không làm thay đổi dependency trong graph.

## 5. Phân tích dòng nối quan trọng nhất

~~~kotlin
val generateNote = tasks.register<GenerateNote>("generateNote") {
    outputFile.set(layout.buildDirectory.file("generated/note.txt"))
}

tasks.register<ReadNote>("readNote") {
    inputFile.set(generateNote.flatMap { it.outputFile })
}
~~~

Đoạn trên là **phần trích từ ví dụ đầy đủ ở mục 4**, không chạy độc lập nếu thiếu hai task class.

Diễn giải theo thứ tự:

1. `tasks.register<GenerateNote>` đăng ký producer theo cách lazy; kết quả là `TaskProvider<GenerateNote>`.
2. Producer có `outputFile: RegularFileProperty` được gắn `@OutputFile`, báo cho Gradle đây là output chính thức của task.
3. `generateNote.flatMap { it.outputFile }` tạo Provider của file mà **vẫn giữ provenance** (thông tin được tạo bởi `generateNote`).
4. `ReadNote.inputFile.set(...)` nối Provider đó với `@InputFile`.
5. Khi cần `readNote`, Gradle thấy đầu vào cần file từ producer và xây dựng graph có `generateNote` trước `readNote`.

Cách mô hình hóa này xử lý **cả đường dẫn và thứ tự**. Nếu đổi output:

~~~kotlin
outputFile.set(layout.buildDirectory.file("reports/generated-note.txt"))
~~~

consumer vẫn nhận đúng file mới qua Provider, không phải sửa thủ công path ở hai nơi.

### 5.1. Vì sao @OutputFile và @InputFile quan trọng?

Annotation là mô tả dữ liệu chính thức để Gradle:

- Xác định kiểu path dự kiến (file hay directory).
- Thực hiện validation khi input thiếu hoặc output sai loại.
- Theo dõi input/output để xét `UP-TO-DATE`.
- Hỗ trợ build cache khi task/thiết lập phù hợp.
- Kiểm tra các quan hệ producer–consumer và phát hiện dependency bị thiếu.

Với một input file bắt buộc, nếu đến lượt consumer mà file không tồn tại, Gradle có thể báo validation error trước khi vào task action. Không nên coi lỗi này chỉ là `FileNotFoundException` thông thường rồi dùng `try/catch` để che đi.

### 5.2. Vì sao tránh đọc file trong phần cấu hình?

Đoạn sai về ý tưởng:

~~~kotlin
// Minh họa lỗi, không chạy với project demo.
val noteTextNow = generateNote.get()
    .outputFile.get().asFile.readText()
~~~

Tại thời điểm cấu hình, producer chưa chạy. `readText()` có thể thất bại vì file chưa có; việc gọi `.get()` còn ép realize/lấy giá trị sớm.

Tương tự, nếu lấy `File` từ producer rồi đưa path trần sang consumer, Gradle có thể mất metadata rằng file phải do task nào tạo. Với dữ liệu công việc, **giữ Provider đến tận khi action cần giá trị** là cách an toàn hơn.

## 6. Cách nối sai và tác động thực tế

### 6.1. Sai: consumer chỉ cầm cùng một path

Với `ReadNote` của ví dụ mục 4, nếu viết:

~~~kotlin
tasks.register<ReadNote>("readNoteWithoutLink") {
    // Chỉ là Provider cho vị trí file,
    // không gắn với TaskProvider tạo ra file.
    inputFile.set(layout.buildDirectory.file("generated/note.txt"))
}
~~~

Consumer biết path, nhưng path này không nói task `generateNote` là producer. Khi chỉ gọi `readNoteWithoutLink`, Gradle không có cơ sở từ mối nối đó để tự bổ sung `generateNote`; nếu file chưa được tạo, validation của `@InputFile` có thể báo thiếu file.

Ngay cả khi file đang tồn tại do build cũ, `readNoteWithoutLink` vẫn không biểu diễn đúng dependency của lần build mới. Nếu hai task được chạy đồng thời theo các nhánh khác mà thiếu quan hệ dữ liệu, build có thể bị race condition hoặc Gradle báo lỗi **implicit dependency**.

**Cách sửa:** truyền `generateNote.flatMap { it.outputFile }` thay vì tạo một Provider độc lập từ cùng chuỗi path.

### 6.2. Sai: lấy `File` từ producer quá sớm

Một ví dụ thường thấy trong build logic cũ:

~~~kotlin
// Minh họa điều không nên làm:
val rawFile = generateNote.get().outputFile.get().asFile

tasks.register<ReadNote>("readRawFile") {
    inputFile.set(rawFile)
}
~~~

`rawFile` là `java.io.File`: nó giữ đường dẫn nhưng không giữ đầy đủ metadata của TaskProvider. Việc gọi `generateNote.get()` còn realize task trong configuration và làm giảm lợi ích configuration avoidance.

**Cách sửa:** giữ mối nối lazy:

~~~kotlin
tasks.register<ReadNote>("readViaProvider") {
    inputFile.set(generateNote.flatMap { it.outputFile })
}
~~~

### 6.3. Sai: bao task output trong Provider độc lập

~~~kotlin
// Ví dụ phản diện, chỉ để giải thích:
val disconnected = providers.provider {
    generateNote.get().outputFile.get()
}
~~~

`providers.provider { ... }` có thể trì hoãn việc tính **giá trị**, nhưng Provider này không tự mang metadata rằng `generateNote` tạo ra file. Không phải mọi Provider lazy đều suy ra task dependency.

**Cách sửa:** lấy Provider trực tiếp từ TaskProvider bằng `flatMap`, hoặc một API FileCollection có gắn task producer.

### 6.4. Sai: dùng mustRunAfter thay dependency

~~~kotlin
tasks.named("readNote") {
    mustRunAfter("generateNote")
}
~~~

Nếu chỉ chạy `readNote`, ràng buộc này **không làm generateNote được chọn**. Với consumer cần file producer tạo, đây không phải giải pháp đủ.

Nếu đã dùng mối nối output→input, Gradle tự tạo dependency và không cần thêm mustRunAfter cho cùng quan hệ đó.

## 7. Dùng @OutputDirectory và @InputFiles khi có nhiều file

Một task có thể sinh cả thư mục tài liệu, còn consumer cần dùng tất cả file trong thư mục. Khi đó:

- Producer khai báo `@OutputDirectory` với `DirectoryProperty`.
- Consumer khai báo `@InputFiles` với `ConfigurableFileCollection`, hoặc `@InputDirectory` với `DirectoryProperty` nếu tiêu thụ cả một directory như một input.
- Producer/consumer được nối qua Provider hoặc TaskProvider.

**Mẫu cho code task class** (đây là mảnh minh họa bổ sung, không phải một build.gradle.kts chạy độc lập):

~~~kotlin
abstract class GenerateDocs : DefaultTask() {
    @get:OutputDirectory
    abstract val docsDir: DirectoryProperty

    @TaskAction
    fun run() {
        val folder = docsDir.get().asFile
        folder.mkdirs()
        folder.resolve("index.txt").writeText("Documentation\n")
    }
}

abstract class PackageDocs : DefaultTask() {
    @get:InputFiles
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val sources: ConfigurableFileCollection

    @TaskAction
    fun run() {
        println("Source files: " + sources.files.size)
    }
}

val generateDocs = tasks.register<GenerateDocs>("generateDocs") {
    docsDir.set(layout.buildDirectory.dir("generated/docs"))
}

tasks.register<PackageDocs>("packageDocs") {
    sources.from(generateDocs.flatMap { it.docsDir })
}
~~~

Các type cần import từ `org.gradle.api`, `org.gradle.api.file` và `org.gradle.api.tasks`, tương tự ví dụ chính. Trong một script Kotlin DSL đầy đủ, sử dụng các import:

~~~kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
~~~

Ở mối nối `sources.from(generateDocs.flatMap { it.docsDir })`, Gradle có thể giữ metadata của producer và đưa `generateDocs` vào graph của `packageDocs`.

**Chú ý tính đúng của bài toán:** `PackageDocs` ở ví dụ chỉ quan sát số file chứ chưa tạo archive. Nếu muốn có artifact thật, nên dùng task kiểu `Zip` hoặc `Copy` có input/output rõ ràng thay vì tự ghi chung vào một thư mục không được khai báo.

### 7.1. Dùng TaskProvider trực tiếp với Copy/Zip

Nhiều API Gradle như `CopySpec.from(...)` có thể nhận một task/provider của task và chuyển thành FileCollection dựa trên **output của task đó**.

Ví dụ một dự án áp dụng plugin Java:

~~~kotlin
plugins {
    java
}

val jarProducer = tasks.named<Jar>("jar")

tasks.register<Copy>("stageJar") {
    from(jarProducer.flatMap { it.archiveFile })
    into(layout.buildDirectory.dir("distribution"))
}
~~~

Khi chạy `./gradlew stageJar`, Gradle có thể đưa `jar` vào graph vì `from(...)` nhận output Provider của Jar. Cách này vẫn hoạt động nếu file JAR được đổi tên hoặc thư mục đích của `jar` thay đổi trong cấu hình.

Một biến thể được nhiều API FileCollection/CopySpec hỗ trợ là `from(jarProducer)` để dùng toàn bộ task outputs. Tuy nhiên, nếu task có nhiều output mà consumer chỉ cần một artifact, hãy ưu tiên **Provider đầu ra cụ thể** (`archiveFile`) cho rõ ý nghĩa.

Lệnh để xem graph:

~~~bash
./gradlew stageJar --dry-run --console=plain
~~~

Do Java plugin có thể kéo thêm `classes`, `compileJava`, `processResources` vào đường dependency của `jar`, task graph thực tế có thể nhiều hơn chỉ hai task `jar` và `stageJar`. Không suy luận tất cả đều chạy action; task không có source có thể là `NO-SOURCE`.

### 7.2. Tránh dùng chung một output directory cho nhiều producer

Hai task độc lập cùng ghi vào `build/generated` có thể gây chồng lấn khi Gradle fingerprint output, chạy song song hoặc làm sạch build. Hãy gán mỗi task một output file/directory rõ ràng, ví dụ `build/generated/generatorA` và `build/generated/generatorB`.

Đường dẫn output riêng giúp Gradle biết ai sở hữu dữ liệu và quyết định trạng thái UP-TO-DATE chính xác hơn. Nếu consumer cần kết quả từ nhiều producer, hãy thêm nhiều Provider vào `ConfigurableFileCollection`.

## 8. Mối quan hệ với map, flatMap và giá trị dẫn xuất

### 8.1. map biến đổi giá trị nhưng vẫn lazy

Ví dụ:

~~~kotlin
val producedName: Provider<String> =
    generateNote.flatMap { it.outputFile }
        .map { it.asFile.name }
~~~

`flatMap` lấy output Provider từ task, `map` biến `RegularFile` thành tên file dạng String. Chuỗi Provider vẫn có thể giữ thông tin dependency trong những cách kết nối đúng. Nhưng **chỉ một String tên file** không phải là đầu vào file để Gradle xác thực nội dung; muốn tiêu thụ file, hãy ưu tiên gán trực tiếp `RegularFileProperty`.

### 8.2. Khi consumer cần nội dung file như @Input

Trong những tình huống đặc biệt, consumer có thể khai báo đầu vào dạng `Property<String>` và nhận nội dung tính từ file producer:

~~~kotlin
// Đoạn minh họa: consumer có inputContent: Property<String>.
inputContent.set(
    generateNote.flatMap { it.outputFile }
        .map { file -> file.asFile.readText(Charsets.UTF_8) }
)
~~~

Mối nối này trì hoãn đọc file cho đến khi Provider được giải quyết và vẫn giữ dependency producer. Tuy nhiên, nếu thực sự cần xử lý **file** chứ không phải chuỗi đã đọc, `@InputFile RegularFileProperty` là thiết kế trực quan và dễ kiểm tra hơn.

Không đặt `readText()` trực tiếp trong configuration hoặc trong lambda `TaskProvider.map { it.outputFile.get().asFile.readText() }`; nó có thể đọc quá sớm, khi producer chưa tạo output.

### 8.3. Output được annotate trực tiếp sẽ dễ theo dõi hơn

Gradle khuyến nghị output do task công bố bằng một **abstract Property** được annotate trực tiếp:

~~~kotlin
@get:OutputFile
abstract val outputFile: RegularFileProperty
~~~

Một getter chỉ trả `Provider<RegularFile>` **được tạo bằng `map` từ thuộc tính khác** có thể gây mất thông tin task dependency nếu dùng sai. Đừng đánh đồng một Provider dẫn xuất tùy ý với property output đã được task khai báo chính thức.

Đối với code task mới, dùng `RegularFileProperty` hoặc `DirectoryProperty` có annotation input/output rõ ràng là lựa chọn mạnh hơn việc viết getter suy diễn tự do hoặc đóng gói output qua closure độc lập.

## 9. Khi nào cần dependsOn hoặc builtBy?

**Ưu tiên nối output→input** khi consumer thật sự tiêu thụ dữ liệu do producer tạo. Tuy nhiên không phải mọi dependency đều biểu diễn bằng file:

- **Task lifecycle/aggregate**: `checkAll` gọi nhiều task kiểm tra; không có file input chung cần khai báo. `dependsOn(...)` là cách hợp lý.
- **Task chuẩn bị môi trường**: một task thiết lập điều kiện thực thi ngoài hệ thống file output có thể cần dependency rõ ràng nếu không có provider dữ liệu.
- **API/plugin cũ không công bố output bằng Provider đúng kiểu**: có thể cần phụ thuộc tường minh, hoặc sửa plugin để hỗ trợ proper task outputs.
- **FileCollection được xây dựng từ nguồn đặc thù**: có thể dùng `builtBy(taskProvider)` để gắn nguồn producer khi phù hợp.

Ví dụ cho lifecycle task:

~~~kotlin
val docs = tasks.register("verifyDocs") {
    doLast { println("docs checked") }
}
val tests = tasks.register("verifyTests") {
    doLast { println("tests checked") }
}

tasks.register("verifyAll") {
    dependsOn(docs, tests)
}
~~~

Ở đây `verifyAll` chỉ tập hợp công việc, không có file output chung; `dependsOn` mô tả chính xác ý định. Ví dụ không cố khẳng định `verifyDocs` và `verifyTests` có thứ tự với nhau, vì chúng là hai dependency độc lập.

### 9.1. builtBy gắn producer vào FileCollection

Trong API Gradle, `ConfigurableFileCollection.builtBy(...)` có thể khai báo task cần xây dựng collection. Ví dụ ý tưởng:

~~~kotlin
val generatedFiles = objects.fileCollection()
generatedFiles.from(layout.buildDirectory.file("generated/note.txt"))
generatedFiles.builtBy(generateNote)
~~~

Đây là **mảnh cấu hình bổ sung**, giả định biến `generateNote` tồn tại như ở mục 4. Khi một task dùng `generatedFiles` làm input theo API phù hợp, collection mang quan hệ builtBy của producer.

Cách này cần dùng cẩn thận vì người viết đang duy trì riêng **file path** và **task tạo ra nó**. Nếu có thể, truyền trực tiếp `generateNote.flatMap { it.outputFile }` rõ nghĩa hơn và ít nguy cơ hai thông tin bị lệch nhau.

### 9.2. Không nhầm producer dependency với ordering

| Nhu cầu | Công cụ phù hợp | Có kéo task vào graph? |
| --- | --- | --- |
| Consumer cần output producer | Provider output → input; inferred dependency | Có |
| Task tổng hợp phải chạy nhiều task con | `dependsOn` | Có |
| Chỉ cần A trước B nếu cả hai được chọn | `mustRunAfter` | Không |
| Chỉ ưu tiên A trước B khi khả thi | `shouldRunAfter` | Không |
| Cần chạy cleanup sau một task | `finalizedBy` | Có, theo quy tắc finalizer |

Chọn quan hệ theo **bản chất công việc**; không dùng ordering mềm để chữa thiếu input/output dependency.

## 10. Vì sao cách nối này giúp incremental build và build cache?

Khi Gradle biết input/output của task, nó có thể tính fingerprint và xác định một task có cần chạy action lần nữa không.

Ở ví dụ `GenerateNote`:

- `message: Property<String>` là `@Input`: đổi `-PnoteText=...` có thể khiến producer chạy lại.
- `outputFile: RegularFileProperty` là `@OutputFile`: Gradle theo dõi file đầu ra.
- Nếu input và output không đổi từ lần build trước, producer có thể **UP-TO-DATE**.
- Nếu output bị xóa, Gradle có thể tạo lại khi producer được yêu cầu như dependency của consumer.
- Nếu project định nghĩa task cacheable và đã cấu hình build cache hợp lệ, Gradle còn có thể **FROM-CACHE** khi khôi phục output.

**Có trong graph không đồng nghĩa action chắc chắn chạy.** Một producer vẫn là dependency bắt buộc dù lần này không cần chạy action vì output đã hợp lệ.

Cũng cần phân biệt:

- **UP-TO-DATE:** Gradle thấy kết quả task ở môi trường hiện tại phù hợp input/output đã biết.
- **FROM-CACHE:** Gradle có thể khôi phục kết quả task từ build cache nếu task cacheable và cache có entry hợp lệ.
- **NO-SOURCE:** task có loại input nguồn nhưng không có file nguồn phù hợp để xử lý.
- **SKIPPED:** task action bị bỏ qua vì điều kiện hoặc dry-run.

Ví dụ hai task chính minh họa **suy ra dependency và kiểm tra up-to-date**; không mặc định rằng custom task được lưu vào build cache chỉ nhờ có annotation đầu vào/đầu ra. Muốn cacheable có thể cần `@CacheableTask` và đáp ứng yêu cầu xác định đầu ra/khả năng tái lập.

## 11. Tương thích với Configuration Cache

**Configuration Cache** lưu lại kết quả cấu hình có thể tái sử dụng giữa các lần chạy phù hợp. Cơ chế Provider và TaskProvider giúp việc khai báo task tránh đọc trạng thái dự án quá sớm và chuẩn bị tốt hơn cho cache.

Với ví dụ mục 4:

~~~kotlin
tasks.register<ReadNote>("readNote") {
    inputFile.set(generateNote.flatMap { it.outputFile })
}
~~~

Consumer action chỉ đọc `inputFile` **của chính nó**, không cần truy cập trực tiếp `Project` hoặc TaskProvider của producer trong action. Cấu trúc này phù hợp với cách Gradle hướng dẫn khi viết task có Configuration Cache.

Cách cần tránh:

~~~kotlin
// Anti-pattern: chỉ minh họa, không đưa vào script ví dụ.
tasks.register("unsafeConsumer") {
    doLast {
        val file = generateNote.get().outputFile.get().asFile
        println(file.readText())
    }
}
~~~

Action giữ tham chiếu đến TaskProvider bên ngoài rồi lấy property của một task khác khi thực thi. Đây là kiểu truy cập không phù hợp yêu cầu Configuration Cache và có thể khiến Gradle không serialize được task state.

**Cách đúng:** declare input trên consumer, nối Provider ở cấu hình, rồi chỉ đọc input của chính consumer trong action.

Có thể thử:

~~~bash
./gradlew readNote --configuration-cache
./gradlew readNote --configuration-cache
~~~

Khi môi trường và build logic tương thích, lần sau Gradle có thể **reuse configuration cache**. Tuy nhiên, hai lần chạy vẫn có thể khác về tình trạng UP-TO-DATE của task; đừng dùng việc một action không in output để kết luận cache có hoạt động hay không. Kiểm tra thông báo Configuration Cache riêng.

## 12. Multi-project build và các task của plugin

Trong multi-project build, producer và consumer có thể thuộc hai module. Bài toán vẫn tương tự: consumer cần **Provider của output được producer công bố**, không chỉ một chuỗi path sang thư mục build của module khác.

Ví dụ ý tưởng:

~~~text
:generator:generateSources
          |
          | @OutputDirectory / DirectoryProperty
          v
:app:compileGenerated
          |
          | @InputFiles
          v
      biên dịch
~~~

Cấu hình chính xác phụ thuộc cách plugin xây dựng task/source set và cách các project trao đổi artifacts. Không nên dựa vào `project(":generator").buildDir` hoặc tự nối `"../generator/build/..."` rồi hy vọng task graph sẽ tự hiểu ai là producer.

Với quan hệ **giữa các project**, đặc biệt khi một module cung cấp thư viện cho module khác, Gradle còn có cơ chế **project dependencies**, configurations và outgoing variants. Chúng thường phù hợp hơn việc truy cập trực tiếp task path của project khác. Trường hợp đơn giản cùng project thì nối TaskProvider như mục 4 là đủ.

## 13. Kiểm tra task graph và validation khi gặp lỗi

### 13.1. Thực hiện lệnh nào?

Chạy bằng Gradle Wrapper trong đúng project:

~~~bash
./gradlew readNote --dry-run --console=plain
./gradlew readNote --info --console=plain
./gradlew help --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat readNote --dry-run --console=plain
.\gradlew.bat readNote --info --console=plain
.\gradlew.bat help --console=plain
~~~

- `--dry-run`: xem task nào được lập lịch và thứ tự ràng buộc, không chạy task action.
- `--info`: xem thêm thông tin về vì sao task chạy, bị skip hoặc UP-TO-DATE.
- `help`: kiểm tra script có cấu hình/biên dịch thành công hay không, nhưng không chứng minh mối nối dữ liệu đã đúng.

Lưu ý `--dry-run` vẫn có thể chạy logic cấu hình cần thiết. Đừng viết side effect trong configuration và cho rằng dry-run tuyệt đối không ảnh hưởng môi trường.

### 13.2. Một checklist chẩn đoán

1. Producer có **định nghĩa output chính thức** với annotation/runtime API không?
2. Output là `RegularFileProperty`/`DirectoryProperty` hay chỉ là một chuỗi/path thô?
3. Consumer có **input tương ứng** và kiểu chính xác không?
4. Mối nối dùng `producer.flatMap { it.outputProperty }` hoặc FileCollection có provenance không?
5. Có dùng `get()`, `asFile`, `absolutePath` quá sớm khiến task metadata bị mất không?
6. Có dùng `providers.provider { ... }` độc lập, không gắn producer không?
7. Task producer có mặt khi chạy **chỉ consumer** qua `--dry-run` không?
8. Nếu producer có trong graph nhưng action không chạy, trạng thái có phải `UP-TO-DATE` hoặc `FROM-CACHE` không?
9. Nếu consumer báo input file không tồn tại, output producer có đúng đường dẫn và thực sự được tạo không?
10. Nếu chạy song song bị lỗi, có nhiều task ghi chung một output path hay mối nối bị đứt không?

### 13.3. Gradle báo lỗi implicit dependency

Một tình huống điển hình: consumer đọc file vốn do producer tạo, nhưng cấu hình chỉ truyền `File` hoặc path không có metadata producer. Gradle có thể cảnh báo hoặc báo lỗi validation kiểu **implicit dependencies between tasks**, nhất là khi cả hai task cùng nằm trong graph nhưng không có quan hệ đúng.

Bước sửa:

1. Thay đầu vào path thô bằng output Provider được annotate trực tiếp: `producer.flatMap { it.outputFile }`.
2. Nếu API consumer chấp nhận TaskProvider/FileCollection, thử truyền producer một cách trực tiếp có nghĩa theo API đó.
3. Nếu task/plugin cũ không hỗ trợ đường nối, khai báo dependency rõ ràng và bảo đảm consumer đọc đúng output; cân nhắc cải tiến plugin để công bố output property.

Không chỉ thêm `mustRunAfter` và coi lỗi đã giải quyết: nó không kéo producer vào graph khi consumer được yêu cầu độc lập.

## 14. Bảng so sánh nhanh: tốt, kém và chỉ dùng khi cần

| Cách nối | Có mang thông tin producer? | Khuyến nghị |
| --- | --- | --- |
| `inputFile.set(producer.flatMap { it.outputFile })` | Có, khi output property được khai báo đúng | **Ưu tiên cho một file** |
| `sources.from(producer.flatMap { it.outputDir })` | Có, với output directory đúng | **Ưu tiên cho nhiều file** |
| `from(tasks.named<Jar>("jar").flatMap { it.archiveFile })` | Có | Tốt cho task Copy/Zip cần một artifact |
| `from(taskProvider)` trong API hỗ trợ task outputs | Có, theo cơ chế FileCollection của API | Tốt khi muốn toàn bộ outputs |
| `inputFile.set(layout.buildDirectory.file("..."))` | Không biết task nào tạo file | Chỉ dùng nếu file là input độc lập, không cần producer |
| `inputFile.set(producer.get().outputFile.get().asFile)` | Có nguy cơ mất dependency và realize sớm | Tránh |
| `providers.provider { producer.get().outputFile.get() }` | Không tự mang provenance của producer | Tránh cho task wiring |
| `consumer.dependsOn(producer)` | Có, theo quan hệ công việc tường minh | Dùng khi không thể biểu diễn bằng input/output hoặc làm lifecycle |
| `consumer.mustRunAfter(producer)` | Không bổ sung producer vào graph | Chỉ dùng nếu không cần kéo task vào graph |

**Nguyên tắc thiết kế:** khai báo *dữ liệu* trước, để Gradle suy ra *thứ tự*. Viết phụ thuộc tường minh khi bản chất công việc không có đầu ra dữ liệu có thể mô hình hóa.

## 15. Bài tập tự kiểm tra

### Bài 1: Chỉ chạy consumer

Với ví dụ hoàn chỉnh ở mục 4, chạy:

~~~bash
./gradlew -q clean readNote
~~~

Hỏi: có cần ghi `dependsOn("generateNote")` trong `readNote` không?

**Đáp án:** Không. `inputFile.set(generateNote.flatMap { it.outputFile })` đã nối đầu ra producer vào đầu vào consumer; Gradle suy ra dependency.

### Bài 2: Bỏ kết nối

Thay dòng mối nối trong `readNote`:

~~~kotlin
inputFile.set(layout.buildDirectory.file("generated/note.txt"))
~~~

Hỏi: có chắc chỉ chạy readNote sẽ tạo note.txt mới khi file chưa tồn tại?

**Đáp án:** Không. Provider này chỉ mô tả path. Nếu task generateNote không ở graph, input bắt buộc có thể bị validation lỗi vì file chưa có.

### Bài 3: Dùng map hay flatMap?

TaskProvider của producer có output `RegularFileProperty`, cần lấy Provider file. Viết gì?

**Đáp án:** `producer.flatMap { it.outputFile }`, vì `it.outputFile` đã là một Provider/Property. Nếu từ Provider file muốn lấy chuỗi tên file, dùng `.map { it.asFile.name }`.

### Bài 4: Producer UP-TO-DATE

Chạy hai lần cùng nội dung input. Lần hai không thấy dòng “GENERATE”. Hỏi có phải inferred dependency biến mất?

**Đáp án:** Không. Producer có thể vẫn trong graph nhưng action không chạy do UP-TO-DATE. Dùng `--dry-run` hoặc log task để phân biệt đồ thị với trạng thái thực thi.

### Bài 5: Hai task đọc/ghi cùng path nhưng không nối Provider

Một producer và consumer đều dùng chuỗi `"build/generated/data.txt"`; khi chạy cả hai ngẫu nhiên thành công. Hỏi vì sao vẫn có rủi ro?

**Đáp án:** Chỉ trùng path không khai báo dependency. Khi chạy consumer một mình hoặc thay đổi lập lịch song song, producer có thể chưa chạy; Gradle còn có thể phát hiện **implicit dependency validation**. Cần nối đúng output Provider hoặc khai báo dependency có ý nghĩa.

### Bài 6: Khi nào cần dependsOn?

Task `verifyAll` chỉ nhóm `lint`, `unitTest`, `integrationTest`, không đọc file của các task đó. Hỏi dùng gì?

**Đáp án:** `dependsOn(...)` là thích hợp với lifecycle/aggregate task. Không nên chế tạo ra một input file giả chỉ để tránh dependsOn.

## 16. Những điều quan trọng khi áp dụng trong dự án thật

- **Khai báo output đúng bản chất:** output file dùng `@OutputFile`, output directory dùng `@OutputDirectory`; tránh mọi task cùng sở hữu một thư mục lớn nếu có thể tách riêng.
- **Khai báo input chính xác:** input file dùng `@InputFile`/`@InputFiles`, dữ liệu cấu hình ảnh hưởng kết quả dùng `@Input`.
- **Giữ Provider chain:** dùng `set`, `from`, `flatMap`, `map` đúng kiểu; trì hoãn `.get()` tới task action khi cần thực hiện I/O.
- **Không đọc Project hoặc TaskProvider khác trong action:** nối dữ liệu từ lúc cấu hình để task chỉ làm việc với input của chính nó; điều này hỗ trợ Configuration Cache.
- **Không phụ thuộc vào thứ tự quan sát tình cờ:** hai task không có ràng buộc vẫn có thể thay đổi thứ tự hoặc chạy song song.
- **Không giả định task trong graph nhất định chạy action:** cần xét UP-TO-DATE, NO-SOURCE, FROM-CACHE, SKIPPED.
- **Không dùng path cứng cho output task khác:** nếu producer thay tên/path artifact, consumer nên tự theo qua Provider.
- **Kiểm tra bằng Wrapper và dry-run:** bảo đảm producer thật sự xuất hiện khi chỉ yêu cầu consumer.
- **Không dùng secrets trong output demo/log:** khi cần dữ liệu nhạy cảm, dùng cơ chế secret thích hợp, không in property values vào log.

Khi thiết kế task mới, câu hỏi hữu ích là: **“Consumer này thực sự cần dữ liệu gì, và ai sở hữu output đó?”** Nếu có thể diễn đạt bằng Property của producer và consumer, Gradle sẽ có nhiều thông tin hơn để lập lịch, kiểm tra hợp lệ và tối ưu build.

## 17. Tài liệu chính thức

1. Gradle – Incremental Build, mục *Inferred task dependencies* và *Input/Output validation*: https://docs.gradle.org/current/userguide/incremental_build.html
2. Gradle – Best Practices for Tasks, mục *Wire lazy task outputs using map and flatMap*: https://docs.gradle.org/current/userguide/best_practices_tasks.html
3. Gradle – Lazy Configuration, Provider API: https://docs.gradle.org/current/userguide/lazy_configuration.html
4. Gradle – Validation Problems, mục *Implicit dependencies between tasks*: https://docs.gradle.org/current/userguide/validation_problems.html
5. Gradle – Configuration Cache Requirements: https://docs.gradle.org/current/userguide/configuration_cache_requirements.html
6. Gradle – Controlling Task Execution: https://docs.gradle.org/current/userguide/controlling_task_execution.html
7. Gradle Provider API: https://docs.gradle.org/current/javadoc/org/gradle/api/provider/Provider.html

Những trang `current` luôn theo phiên bản tài liệu hiện hành. Khi một repository sử dụng Gradle Wrapper phiên bản cụ thể, cần đối chiếu tài liệu đúng phiên bản Wrapper và plugin của repository. Các quy tắc cơ bản về khai báo input/output và giữ task producer metadata vẫn là nền tảng để tránh implicit dependency bị thiếu.
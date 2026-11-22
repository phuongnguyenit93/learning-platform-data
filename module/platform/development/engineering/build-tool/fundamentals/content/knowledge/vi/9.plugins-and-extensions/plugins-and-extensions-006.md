# Tạo bước tự động hóa nhỏ với đầu vào, đầu ra và lỗi rõ ràng

Build tool không chỉ biên dịch mã nguồn và chạy test. Ta còn có thể mở rộng quy trình build bằng những bước tự động hóa nhỏ, chẳng hạn sinh file cấu hình, kiểm tra tài nguyên, tạo chỉ mục tài liệu, chuyển đổi dữ liệu, tạo mã nguồn hoặc tổng hợp báo cáo. Một bước nhỏ được thiết kế tốt giúp nhóm thực hiện công việc lặp lại bằng cùng một lệnh trên máy cá nhân và CI.

Điều quan trọng nhất khi tạo bước tự động hóa là xác định rõ **đầu vào**, **đầu ra** và **cách báo lỗi**. Build tool cần biết công việc đọc dữ liệu nào, tạo ra file nào và phải dừng ra sao khi dữ liệu không hợp lệ. Những thông tin này giúp bước build dễ sử dụng, dễ chẩn đoán, có thể chạy lại an toàn và có thể tham gia vào quy trình incremental build khi phù hợp.

Bài học sử dụng một ví dụ xuyên suốt: tạo file chỉ mục Markdown từ các tài liệu trong `src/docs`, rồi ghi kết quả vào `build/generated/docs/index.md`. Ví dụ tập trung vào Gradle custom task vì Gradle có mô hình input/output tường minh. Cuối bài sẽ liên hệ cách tổ chức tương tự với Maven plugin goal và Ant target.

## 1. Khi nào cần tạo bước tự động hóa riêng?

Hãy cân nhắc tạo một bước build khi công việc:

- được lặp lại trong nhiều lần build;
- cần chạy theo cùng một quy tắc trên máy phát triển và CI;
- tạo ra file hoặc dữ liệu mà bước build khác sẽ sử dụng;
- cần kiểm tra điều kiện trước khi đóng gói hoặc phát hành;
- có thể được mô tả bằng đầu vào và đầu ra xác định;
- không phù hợp để thực hiện thủ công trong IDE hoặc terminal mỗi lần.

Ví dụ thực tế:

| Công việc | Đầu vào | Đầu ra hoặc kết quả |
|---|---|---|
| Tạo chỉ mục tài liệu | Các file Markdown và tiêu đề | Một file `index.md` tổng hợp |
| Kiểm tra file cấu hình | `application.properties` và quy tắc bắt buộc | Báo build thành công hoặc lỗi có vị trí rõ ràng |
| Sinh mã nguồn | Schema, template và phiên bản generator | Thư mục mã Java được sinh |
| Tạo manifest | Danh sách artifact và phiên bản phát hành | File manifest có thể đóng gói |
| Kiểm tra license | Dependency graph và chính sách license | Báo cáo hoặc lỗi nếu có dependency không được phép |
| Chuẩn bị resource | Ảnh, file dịch và cấu hình | Resource đã chuyển đổi trong thư mục build |

Không phải mọi lệnh tiện ích đều cần trở thành build task. Nếu một công việc chỉ được thực hiện một lần hoặc không liên quan đến kết quả build, một script riêng có thể đơn giản hơn. Khi công việc trở thành một phần của quy trình chuẩn, cần được gọi lặp lại và có đầu ra được task khác tiêu thụ, tích hợp vào build tool thường hữu ích hơn.

## 2. Thiết kế hợp đồng trước khi viết mã

Một bước tự động hóa nên có hợp đồng ngắn gọn, có thể mô tả bằng bảng.

Với ví dụ tạo chỉ mục tài liệu:

| Thành phần | Quy ước |
|---|---|
| Tên công việc | `generateDocsIndex` |
| Mục đích | Tạo một trang chỉ mục từ các file Markdown |
| Đầu vào file | Các file `*.md` trong `src/docs` |
| Đầu vào giá trị | Tiêu đề trang, ví dụ `Project documentation` |
| Đầu ra | `build/generated/docs/index.md` |
| Định dạng | UTF-8, thứ tự tài liệu theo đường dẫn tương đối |
| Điều kiện lỗi | Thư mục nguồn không tồn tại, không có Markdown, tiêu đề rỗng hoặc không đọc/ghi được file |
| Điều kiện thành công | Tạo đầy đủ file chỉ mục ở đúng vị trí |

Hợp đồng trả lời ba nhóm câu hỏi:

1. **Input:** task cần đọc những gì và giá trị nào có thể làm thay đổi kết quả?
2. **Output:** task tạo hoặc cập nhật file nào, ở đâu, theo định dạng nào?
3. **Failure:** điều kiện nào làm task thất bại, thông báo lỗi cần giúp người dùng biết phải sửa gì?

Ngoài ra, cần xác định quan hệ với các bước khác. Nếu task tạo file mà một task đóng gói sẽ sử dụng, build graph phải biết task đóng gói cần chờ output đó.

### 2.1. Đầu vào phải đầy đủ

Đầu vào không chỉ là file. Nó có thể gồm:

- file hoặc thư mục;
- chuỗi, số, boolean và danh sách tùy chọn;
- phiên bản công cụ hoặc schema;
- classpath và dependency;
- biến môi trường nếu chúng thực sự ảnh hưởng kết quả;
- cấu hình và template được đọc trong lúc thực thi.

Nếu tiêu đề trang thay đổi thì nội dung chỉ mục thay đổi, do đó tiêu đề phải được khai báo là input. Nếu task sử dụng phiên bản generator để sinh mã, phiên bản đó cũng ảnh hưởng output và cần được phản ánh trong hợp đồng.

Không nên âm thầm đọc dữ liệu ngoài hợp đồng, chẳng hạn file trong thư mục home, biến môi trường không được khai báo, thời gian hệ thống hoặc nội dung tải từ API. Build tool sẽ không thể xác định chính xác khi nào kết quả cũ cần được tạo lại nếu một yếu tố ảnh hưởng kết quả bị giấu đi.

### 2.2. Đầu ra cần có vị trí riêng

Đặt file được sinh trong thư mục build, ví dụ:

```text
project/
├── src/
│   └── docs/
│       ├── intro.md
│       └── setup.md
└── build/
    └── generated/
        └── docs/
            └── index.md
```

Thư mục `build/` chứa kết quả có thể tạo lại. Khi chạy clean, công cụ có thể xóa output rồi sinh lại từ source. Không nên ghi file sinh tự động cạnh file nguồn nếu không có lý do đặc biệt, vì file cũ có thể bị commit nhầm hoặc che giấu lỗi thiếu bước generate.

Một output nên có một task sở hữu. Nếu hai task cùng ghi một file, kết quả có thể phụ thuộc thứ tự thực thi hoặc bị ghi đè khi build chạy song song.

### 2.3. Lỗi cần có hành động sửa rõ ràng

Thông báo lỗi tốt nên nêu:

- công việc nào thất bại;
- file hoặc giá trị nào có vấn đề;
- vì sao dữ liệu không hợp lệ hoặc thao tác không thực hiện được;
- người dùng nên kiểm tra hoặc sửa điều gì.

Ví dụ, `Build failed` không đủ thông tin. `Cannot generate docs index: source directory 'src/docs' does not exist. Create the directory and add at least one Markdown file.` giúp người dùng biết chính xác cần làm gì.

Không nên bắt lỗi rồi bỏ qua. Nếu task không tạo được output nhưng build vẫn báo thành công, bước đóng gói phía sau có thể tạo artifact thiếu dữ liệu.

## 3. Chọn điểm mở rộng phù hợp

Mỗi build tool có cách mở rộng riêng.

| Công cụ | Điểm mở rộng thường dùng | Vai trò |
|---|---|---|
| Gradle | Custom task và plugin | Định nghĩa công việc, input/output, dependency và cách thực thi |
| Maven | Plugin goal (Mojo) | Bổ sung công việc và gắn nó vào lifecycle phase hoặc gọi trực tiếp |
| Ant | Target và task | Ghép các thao tác thành quy trình có tên và khai báo thứ tự |

Với một automation nhỏ trong dự án Gradle, có thể bắt đầu bằng custom task. Nếu nhiều dự án cần dùng lại cùng task và cấu hình, nên đóng gói thành plugin hoặc convention plugin. Với Maven, công việc có thể được triển khai thành plugin goal. Với Ant, thường bắt đầu từ target sử dụng các task có sẵn; nếu logic phức tạp hoặc được dùng lại nhiều nơi, có thể viết custom Ant task.

## 4. Ví dụ chính: tạo chỉ mục Markdown bằng Gradle

Ta sẽ tạo task `generateDocsIndex` với các quy tắc:

- đọc tất cả file Markdown trong `src/docs`;
- sắp xếp file theo đường dẫn tương đối để kết quả ổn định;
- ghi tiêu đề và nội dung từng tài liệu vào một file chỉ mục;
- sử dụng UTF-8;
- báo lỗi nếu thư mục không tồn tại, không có file Markdown hoặc tiêu đề rỗng;
- ghi output qua file tạm rồi thay thế file đích sau khi hoàn tất, giảm nguy cơ để lại file dở dang.

### 4.1. Tạo task type

Trong dự án dùng Kotlin DSL, đặt task type trong file `buildSrc/src/main/kotlin/GenerateDocsIndex.kt`. `buildSrc` là build logic được Gradle biên dịch và đưa vào classpath của build chính. Với dự án lớn hoặc nhiều build dùng chung logic, có thể chuyển task sang convention plugin trong included build `build-logic`.

```kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.GradleException
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.Internal
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import java.io.IOException
import java.nio.charset.StandardCharsets
import java.nio.file.AtomicMoveNotSupportedException
import java.nio.file.Files
import java.nio.file.StandardCopyOption

@CacheableTask
abstract class GenerateDocsIndex : DefaultTask() {

    @get:Internal
    abstract val projectDirectory: DirectoryProperty

    @get:Input
    abstract val sourceDirectory: Property<String>

    @get:InputFiles
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val markdownFiles: ConfigurableFileCollection

    @get:Input
    abstract val pageTitle: Property<String>

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val sourceRoot = projectDirectory.get()
            .dir(sourceDirectory.get())
            .asFile

        if (!sourceRoot.isDirectory) {
            throw GradleException(
                "Cannot generate docs index: source directory " +
                    "'${sourceRoot}' does not exist. Create it and add Markdown files."
            )
        }

        val title = pageTitle.get().trim()
        if (title.isEmpty()) {
            throw GradleException(
                "Cannot generate docs index: pageTitle must not be blank. " +
                    "Set the docsTitle Gradle property or configure pageTitle."
            )
        }

        val files = markdownFiles.files
            .filter { it.isFile && it.extension.equals("md", ignoreCase = true) }
            .sortedBy { it.relativeTo(sourceRoot).invariantSeparatorsPath }

        if (files.isEmpty()) {
            throw GradleException(
                "Cannot generate docs index: no Markdown files were found in " +
                    "'${sourceRoot}'. Add at least one .md file."
            )
        }

        val content = try {
            buildString {
                append("# ").append(title).append('\n')
                files.forEach { file ->
                    val relativePath = file.relativeTo(sourceRoot)
                        .invariantSeparatorsPath
                    append("\n## ").append(relativePath).append('\n')
                    append(Files.readString(file.toPath(), StandardCharsets.UTF_8))
                    append('\n')
                }
            }
        } catch (ex: IOException) {
            throw GradleException(
                "Cannot read a Markdown input while generating docs index: ${ex.message}",
                ex
            )
        }

        val destination = outputFile.get().asFile
        val parent = destination.parentFile
            ?: throw GradleException("Output file has no parent directory: $destination")

        try {
            Files.createDirectories(parent.toPath())
            val temporaryFile = Files.createTempFile(
                parent.toPath(),
                "${destination.name}.",
                ".tmp"
            )

            try {
                Files.writeString(temporaryFile, content, StandardCharsets.UTF_8)
                try {
                    Files.move(
                        temporaryFile,
                        destination.toPath(),
                        StandardCopyOption.ATOMIC_MOVE,
                        StandardCopyOption.REPLACE_EXISTING
                    )
                } catch (ex: AtomicMoveNotSupportedException) {
                    Files.move(
                        temporaryFile,
                        destination.toPath(),
                        StandardCopyOption.REPLACE_EXISTING
                    )
                }
            } finally {
                Files.deleteIfExists(temporaryFile)
            }
        } catch (ex: IOException) {
            throw GradleException(
                "Cannot write docs index to '${destination}': ${ex.message}",
                ex
            )
        }
    }
}
```

Đoạn mã cho thấy từng phần của hợp đồng:

- `sourceDirectory` là đường dẫn tương đối đến thư mục nguồn. Nó được khai báo bằng `@Input` vì vị trí thư mục được dùng để xác định các đường dẫn tương đối trong output.
- `markdownFiles` là tập file đầu vào. `@InputFiles` và `@PathSensitive(RELATIVE)` cho Gradle theo dõi nội dung file cùng đường dẫn tương đối.
- `pageTitle` là giá trị đầu vào. Thay tiêu đề sẽ làm thay đổi kết quả.
- `outputFile` là file do task tạo. `@OutputFile` giúp Gradle theo dõi sự tồn tại và trạng thái của output.
- `@CacheableTask` cho phép Gradle sử dụng build cache khi task thực sự có tính xác định và mọi đầu vào ảnh hưởng kết quả đều được khai báo.

Task sắp xếp danh sách file trước khi tạo nội dung, nhờ đó kết quả không phụ thuộc vào thứ tự file hệ thống trả về. File được đọc và ghi bằng UTF-8. Nếu không đọc được đầu vào hoặc không ghi được output, task ném `GradleException` kèm thông tin giúp tìm nguyên nhân.

Việc ghi qua file tạm giúp output đích chỉ được thay thế sau khi nội dung đã được tạo và ghi xong. Nếu filesystem không hỗ trợ thao tác đổi tên nguyên tử, code dùng phương án thay thế thông thường. Đây là biện pháp giảm rủi ro file dở dang; nó không thay thế backup hoặc xử lý lỗi ở cấp hệ thống lưu trữ.

Ví dụ này dùng `Files.readString` và `Files.writeString`, nên build logic cần được biên dịch và chạy bằng Java 11 trở lên. Thuộc tính `projectDirectory` được đánh dấu `@Internal` và gán khi đăng ký task để action không truy cập trực tiếp vào đối tượng `Project` trong lúc thực thi. Đường dẫn tương đối cùng tập file thực tế vẫn được khai báo riêng làm input.

### 4.2. Đăng ký task trong `build.gradle.kts`

Trong file `build.gradle.kts` của project:

```kotlin
val docsDirectory = layout.projectDirectory.dir("src/docs")

tasks.register<GenerateDocsIndex>("generateDocsIndex") {
    projectDirectory.set(layout.projectDirectory)
    sourceDirectory.set("src/docs")
    markdownFiles.from(
        fileTree(docsDirectory) {
            include("**/*.md")
        }
    )
    pageTitle.set(
        providers.gradleProperty("docsTitle")
            .orElse("Project documentation")
    )
    outputFile.set(
        layout.buildDirectory.file("generated/docs/index.md")
    )
}
```

Ở đây:

- `fileTree` chọn các file Markdown bên trong `src/docs`;
- `docsTitle` có thể được truyền từ dòng lệnh hoặc dùng giá trị mặc định;
- output luôn nằm dưới `build/generated/docs`;
- các giá trị được gán qua provider/property để Gradle quản lý cấu hình task.

Task type được đặt trong `buildSrc`, vì vậy build chính có thể tham chiếu `GenerateDocsIndex` khi đăng ký task. Dự án `buildSrc` cần được cấu hình để biên dịch Kotlin DSL, thường dùng plugin `kotlin-dsl` trong `buildSrc/build.gradle.kts`:

```kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
}
```

### 4.3. Chạy task

Trên macOS/Linux:

```bash
./gradlew generateDocsIndex
```

Trên Windows:

```powershell
.\gradlew.bat generateDocsIndex
```

Muốn thay tiêu đề:

```bash
./gradlew generateDocsIndex -PdocsTitle="Product documentation"
```

Kết quả nằm tại:

```text
build/generated/docs/index.md
```

Task chỉ tạo file chỉ mục. Nếu file đó cần được đóng gói vào JAR hoặc một archive khác, cần nối output với task tiêu thụ hoặc đăng ký nó như resource đầu vào của bước đóng gói.

## 5. Hiểu cách task báo lỗi

Task nên phân biệt lỗi đầu vào, lỗi dữ liệu và lỗi hệ thống.

| Loại lỗi | Ví dụ | Thông báo nên cung cấp |
|---|---|---|
| Thiếu đầu vào | `src/docs` không tồn tại | Đường dẫn bị thiếu và cách tạo thư mục |
| Không có dữ liệu | Không tìm thấy file `.md` | Thư mục đã tìm và loại file được yêu cầu |
| Giá trị không hợp lệ | Tiêu đề rỗng | Tên thuộc tính và cách truyền giá trị hợp lệ |
| Dữ liệu không đọc được | File không có quyền đọc hoặc encoding không hợp lệ | Đường dẫn file và nguyên nhân I/O |
| Không ghi được output | Thư mục đích không có quyền ghi hoặc ổ đĩa gặp lỗi | Đường dẫn output và lỗi hệ thống |
| Lỗi logic | File có cấu trúc không được hỗ trợ | File và vị trí dữ liệu nếu có thể xác định |

### 5.1. Không dùng log thay cho lỗi

`logger.warn()` hoặc `logger.error()` chỉ ghi thông tin. Nếu task bắt buộc phải tạo output mà không làm được, nó cần ném exception để build tool đánh dấu task thất bại. Nếu chỉ ghi log rồi kết thúc bình thường, task phía sau có thể tiếp tục với file thiếu hoặc file cũ.

Có thể ghi log thông tin khi công việc hoàn tất, ví dụ số file đã xử lý và đường dẫn output. Nhưng trạng thái thất bại phải được truyền qua exception hoặc cơ chế lỗi tương ứng của build tool.

### 5.2. Không bắt lỗi quá rộng rồi bỏ qua

Mẫu không nên dùng:

```kotlin
try {
    generateIndex()
} catch (ex: Exception) {
    logger.warn("Could not generate index", ex)
}
```

Đoạn mã này biến lỗi thành cảnh báo và có thể khiến build báo thành công dù output không hợp lệ. Chỉ bắt những loại exception mà task có thể xử lý hoặc bổ sung ngữ cảnh rồi ném lại lỗi. Với lỗi không thể khôi phục, hãy dừng build.

### 5.3. Phân biệt lỗi người dùng và lỗi lập trình

Lỗi như thiếu thư mục nguồn hoặc tiêu đề rỗng là lỗi cấu hình/đầu vào mà người dùng có thể sửa. Lỗi như `NullPointerException` do task tự viết sai là lỗi implementation. Thông báo nên giữ stack trace khi cần để người phát triển plugin chẩn đoán, nhưng không nên buộc người dùng đọc stack trace mới biết file đầu vào nào bị thiếu.

## 6. Đảm bảo task chạy lại đúng lúc

Gradle theo dõi input và output đã khai báo để quyết định task có cần thực thi hay không. Với task ví dụ:

| Thay đổi | Hành vi mong đợi |
|---|---|
| Sửa nội dung một file Markdown | Task cần chạy lại |
| Thêm file Markdown | Task cần chạy lại |
| Xóa file Markdown | Task cần chạy lại để loại nội dung cũ |
| Thay đổi `docsTitle` | Task cần chạy lại |
| Xóa file output | Task cần tạo lại output |
| Sửa file Java không liên quan | Task thường có thể được đánh dấu up-to-date |

Có thể dùng các lệnh sau để quan sát hành vi:

```bash
# Chạy task và xem log chi tiết
./gradlew generateDocsIndex --info

# Yêu cầu task thực thi lại cho mục đích chẩn đoán
./gradlew generateDocsIndex --rerun-tasks

# Xem task dự kiến chạy mà không thực thi action
./gradlew generateDocsIndex --dry-run
```

`--rerun-tasks` hữu ích khi kiểm tra implementation, nhưng không nên dùng như cách khắc phục lâu dài cho một hợp đồng input/output sai. `--dry-run` giúp xem task graph, không xác nhận nội dung output được tạo đúng.

### 6.1. Vì sao task cần tính xác định?

Với cùng tập input, task nên tạo cùng output. Tránh đưa timestamp hiện tại, số ngẫu nhiên không có seed, đường dẫn tuyệt đối của máy phát triển hoặc dữ liệu tải trực tiếp từ Internet vào output nếu các yếu tố đó không được quản lý.

Nếu output phụ thuộc vào biến môi trường, hãy khai báo giá trị đó như một input. Nếu output phụ thuộc phiên bản formatter hoặc generator, phiên bản đó cũng phải là một input. Nếu không thể mô tả đầy đủ dữ liệu ảnh hưởng kết quả, không nên bật cache cho task.

### 6.2. Khi nào không nên bật cache?

Không phải mọi task đều phù hợp với `@CacheableTask`. Cần cân nhắc khi task:

- gửi request hoặc cập nhật hệ thống bên ngoài;
- gửi thông báo hoặc tạo side effect cần xảy ra ở mỗi lần gọi;
- đọc dữ liệu thay đổi từ mạng mà không có snapshot được quản lý;
- phụ thuộc trạng thái máy hoặc secret không được mô tả;
- tạo output không xác định.

Với task tạo file thuần túy như ví dụ, cache có thể phù hợp nếu hợp đồng đầy đủ và implementation xác định. Với task publish artifact lên repository, hành động publish thường nên được tách khỏi task tạo artifact và quản lý riêng.

## 7. Nối output với bước build tiếp theo

Một task tạo file chỉ hữu ích khi bước sau biết cách sử dụng nó. Ví dụ, muốn đóng gói chỉ mục vào ZIP, có thể khai báo:

```kotlin
val generateDocsIndex = tasks.named<GenerateDocsIndex>("generateDocsIndex")

tasks.register<Zip>("packageDocsIndex") {
    from(generateDocsIndex.flatMap { it.outputFile })
    archiveFileName.set("docs-index.zip")
    destinationDirectory.set(layout.buildDirectory.dir("distributions"))
}
```

`from(generateDocsIndex.flatMap { it.outputFile })` truyền output provider từ task tạo sang task đóng gói. Gradle có thể suy ra task tạo phải chạy trước task đóng gói.

Nếu chỉ viết một đường dẫn file cứng trong `from(...)` mà không nối nó với task tạo, Gradle có thể không biết file đó cần được tạo bởi task nào. Build có thể chạy trên máy đã có file cũ nhưng thất bại trong clean build hoặc CI.

Với generated source/resource, cần đăng ký thư mục output vào source set hoặc resource set phù hợp. Với artifact cuối, cần nối output với packaging hoặc publishing task. Không nên giả định file nằm trong `build/` là tự động được đóng gói.

## 8. Cách làm tương tự trong Maven

Trong Maven, một bước tự động hóa riêng thường được triển khai thành plugin goal (Mojo). Goal có thể nhận tham số qua `@Parameter`, dùng `MavenProject` để truy cập thông tin project, tạo file trong `${project.build.directory}` và ném `MojoExecutionException` khi không thể hoàn thành công việc.

Ví dụ cấu trúc một Mojo:

```java
@Mojo(
    name = "generate-index",
    defaultPhase = LifecyclePhase.GENERATE_RESOURCES,
    threadSafe = true
)
public class GenerateIndexMojo extends AbstractMojo {

    @Parameter(defaultValue = "${project.basedir}/src/docs", required = true)
    private File sourceDirectory;

    @Parameter(
        defaultValue = "${project.build.directory}/generated/docs/index.md",
        required = true
    )
    private File outputFile;

    @Parameter(defaultValue = "${project.name}", readonly = true)
    private String pageTitle;

    @Override
    public void execute() throws MojoExecutionException {
        if (!sourceDirectory.isDirectory()) {
            throw new MojoExecutionException(
                "Documentation directory does not exist: " + sourceDirectory
            );
        }

        // Read the declared inputs, generate the index, and write outputFile.
        // Wrap I/O failures in MojoExecutionException with the relevant path.
    }
}
```

Đây là khung cấu trúc; phần đọc file và tạo nội dung cần được triển khai theo hợp đồng của plugin. `defaultPhase` cho biết phase mặc định mà goal có thể được gắn vào. Nó không tự mô tả đầy đủ input/output hoặc bảo đảm file được đóng gói.

Trong POM của project sử dụng plugin:

```xml
<plugin>
    <groupId>com.example.build</groupId>
    <artifactId>docs-index-maven-plugin</artifactId>
    <version>1.0.0</version>
    <executions>
        <execution>
            <id>generate-docs-index</id>
            <phase>generate-resources</phase>
            <goals>
                <goal>generate-index</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <sourceDirectory>${project.basedir}/src/docs</sourceDirectory>
        <outputFile>${project.build.directory}/generated/docs/index.md</outputFile>
        <pageTitle>${project.name}</pageTitle>
    </configuration>
</plugin>
```

Nếu file được sinh ra là resource cần đóng gói, plugin phải đăng ký thư mục resource đó với Maven project hoặc dùng cơ chế plugin phù hợp để các phase sau nhận biết. Chỉ ghi file vào `target/` không tự động làm file đó được đưa vào JAR/WAR.

Lỗi đầu vào hoặc I/O cần được chuyển thành `MojoExecutionException` với thông tin cụ thể. Không nên chỉ log cảnh báo rồi kết thúc bình thường nếu output là bắt buộc.

## 9. Cách làm tương tự trong Ant

Với Ant, có thể bắt đầu bằng target sử dụng các task có sẵn:

```xml
<project name="docs-build" default="generate-index">
    <property name="docs.src" location="src/docs" />
    <property name="docs.output.dir" location="build/generated/docs" />
    <property name="docs.output" location="${docs.output.dir}/index.md" />

    <target name="validate-docs-input">
        <available file="${docs.src}" type="dir" property="docs.dir.exists" />
        <fail unless="docs.dir.exists"
              message="Documentation directory is missing: ${docs.src}" />
    </target>

    <target name="generate-index" depends="validate-docs-input">
        <mkdir dir="${docs.output.dir}" />
        <concat destfile="${docs.output}" encoding="UTF-8">
            <header>Project documentation&#10;</header>
            <fileset dir="${docs.src}" includes="**/*.md" />
        </concat>
    </target>
</project>
```

Target `validate-docs-input` kiểm tra thư mục nguồn và dùng task `fail` để dừng build với thông báo rõ ràng nếu thiếu thư mục. Target `generate-index` phụ thuộc target kiểm tra, tạo thư mục output rồi nối nội dung các file Markdown.

Đây là ví dụ tối giản. Với yêu cầu đầu ra có thứ tự ổn định, kiểm tra trường hợp không có file Markdown, xử lý encoding nghiêm ngặt hoặc ghi file tạm rồi thay thế, có thể cần custom Ant task hoặc script chuyên biệt. Ant target `depends` mô tả thứ tự thực thi; người viết build file chịu trách nhiệm xác định input/output và logic kiểm tra output cũ.

## 10. So sánh cách báo lỗi và mở rộng

| Công cụ | Cách báo lỗi thường dùng | Cách nối với build tiếp theo |
|---|---|---|
| Gradle | Ném `GradleException` hoặc exception phù hợp; task thất bại và build báo lỗi | Task dependency, provider input/output, source set hoặc resource set |
| Maven | Ném `MojoExecutionException` cho lỗi thực thi; dùng lỗi cấu hình phù hợp cho tham số không hợp lệ | Gắn goal vào lifecycle phase, đăng ký generated source/resource hoặc công bố artifact |
| Ant | Task `fail`, exception từ task hoặc script/task trả lỗi | Target `depends`, property/path và output được task sau tham chiếu |

Điểm chung là lỗi bắt buộc phải được truyền về build tool. Nếu task không tạo được output nhưng build vẫn tiếp tục như thành công, artifact sau cùng có thể không đáng tin cậy.

## 11. Kiểm tra bước tự động hóa sau khi viết

Một task nhỏ vẫn cần được thử trong các điều kiện thực tế. Hãy kiểm tra hành vi đầu vào, đầu ra và lỗi theo từng trường hợp.

| Tình huống | Kết quả mong đợi |
|---|---|
| Thư mục nguồn tồn tại và có Markdown hợp lệ | Task tạo output ở đúng đường dẫn |
| Thay đổi nội dung một file nguồn | Task chạy lại và output phản ánh nội dung mới |
| Thêm file Markdown | File mới xuất hiện trong chỉ mục |
| Xóa file Markdown | Nội dung tương ứng biến mất sau lần chạy lại |
| Thư mục nguồn không tồn tại | Build thất bại với đường dẫn và hướng xử lý rõ ràng |
| Không có file Markdown | Build thất bại theo hợp đồng đã chọn |
| Tiêu đề rỗng | Build thất bại và nêu thuộc tính cần sửa |
| Không có quyền ghi output | Build thất bại và nêu đường dẫn output |
| Chạy task lần thứ hai khi không có thay đổi | Gradle có thể đánh dấu up-to-date hoặc dùng cache nếu điều kiện phù hợp |
| Chạy clean rồi chạy lại | Output được tạo lại từ source |

Các lệnh Gradle hữu ích:

```bash
# Chạy task
./gradlew generateDocsIndex

# Xem log chi tiết
./gradlew generateDocsIndex --info

# Chạy lại task để kiểm tra action
./gradlew generateDocsIndex --rerun-tasks

# Xóa output rồi tạo lại
./gradlew clean generateDocsIndex
```

Không cần chạy task trong mọi tình huống bằng `--rerun-tasks`. Hãy kiểm tra cả trạng thái up-to-date để biết hợp đồng input/output hoạt động như dự kiến. Khi task không chạy lại sau khi thay đổi dữ liệu ảnh hưởng kết quả, hãy kiểm tra thuộc tính input trước khi tìm cách ép task chạy.

## 12. Những lỗi thiết kế thường gặp

### 12.1. Đầu vào bị giấu

Task đọc file cấu hình trong thư mục home nhưng không khai báo. Khi file thay đổi, build tool không biết kết quả cần được tạo lại.

**Cách xử lý:** đưa file hoặc giá trị cấu hình vào input. Nếu đó là trạng thái máy cá nhân, cân nhắc loại bỏ sự phụ thuộc hoặc truyền giá trị qua cấu hình được quản lý.

### 12.2. Đầu vào khai báo quá rộng

Task chỉ cần file Markdown nhưng lại theo dõi toàn bộ repository. Mỗi lần sửa mã Java, task tài liệu cũng chạy lại.

**Cách xử lý:** thu hẹp file collection hoặc thư mục input theo đúng dữ liệu task sử dụng.

### 12.3. Output nằm trong thư mục nguồn

File sinh tự động được ghi cạnh file do lập trình viên quản lý. Output cũ có thể bị commit nhầm và khó phân biệt với source.

**Cách xử lý:** đặt output trong `build/` hoặc `target/` và khai báo nơi sở hữu rõ ràng.

### 12.4. Chỉ log lỗi rồi tiếp tục

Task không tạo được file nhưng chỉ ghi warning. Build tiếp tục và task đóng gói có thể lấy file cũ.

**Cách xử lý:** ném exception khi không thể hoàn thành công việc bắt buộc. Chỉ dùng warning cho tình huống thực sự có thể tiếp tục an toàn.

### 12.5. Output ghi dở khi có lỗi

Task ghi trực tiếp lên file đích rồi gặp lỗi giữa chừng. File đích bị cắt hoặc chỉ chứa một phần dữ liệu.

**Cách xử lý:** tạo nội dung trước, ghi vào file tạm và thay thế output sau khi ghi hoàn tất.

### 12.6. Hai task cùng ghi một file

Build song song làm một task ghi đè output của task khác.

**Cách xử lý:** mỗi output chỉ có một task sở hữu. Nếu cần biến đổi nhiều lần, dùng output trung gian riêng cho từng bước.

### 12.7. Bật cache khi task có side effect

Task publish hoặc gửi thông báo bị đánh dấu cacheable. Lần sau build tool dùng lại trạng thái cũ và bỏ qua hành động cần thực hiện.

**Cách xử lý:** tách phần tạo artifact có thể cache khỏi hành động publish/deploy. Chỉ cache task tạo output xác định và không có side effect cần lặp lại.

## 13. Đưa logic dùng chung thành plugin

Một custom task đặt trực tiếp trong build logic phù hợp khi chỉ một project cần dùng. Khi nhiều module hoặc nhiều repository cần cùng một quy tắc, nên đóng gói logic thành plugin.

Plugin có thể:

- đăng ký task với tên và kiểu rõ ràng;
- cung cấp extension để người dùng cấu hình input, output và tùy chọn;
- áp dụng convention chung cho nhiều project;
- kết nối task với lifecycle hoặc task graph phù hợp;
- quản lý phiên bản và kiểm thử build logic tập trung.

Ví dụ, thay vì mỗi module tự viết:

```kotlin
tasks.register<GenerateDocsIndex>("generateDocsIndex") {
    sourceDirectory.set("src/docs")
    // Configure inputs and output.
}
```

ta có thể tạo convention plugin tên `com.example.docs-index` để đăng ký task và áp dụng quy ước mặc định. Mỗi module chỉ cần cấu hình những giá trị khác biệt.

Không nên tạo plugin quá sớm cho một đoạn script rất nhỏ chỉ được dùng một lần. Bắt đầu từ task có hợp đồng rõ, sau đó tách thành plugin khi cần tái sử dụng, kiểm soát phiên bản hoặc chia sẻ giữa các project.

## 14. Quy trình thực hiện một automation nhỏ

Khi nhận yêu cầu tự động hóa, có thể đi theo thứ tự:

1. **Mô tả mục đích:** task tạo ra giá trị gì và bước nào sẽ sử dụng kết quả?
2. **Xác định input:** file, thư mục, tham số, dependency và môi trường nào ảnh hưởng kết quả?
3. **Xác định output:** file hoặc thư mục nào được tạo, ai sở hữu và có thể xóa/tạo lại không?
4. **Xác định lỗi:** đầu vào bắt buộc, trường hợp rỗng, lỗi đọc/ghi và điều kiện dừng build.
5. **Chọn extension point:** Gradle task, Maven plugin goal hay Ant target/task.
6. **Viết implementation:** xử lý dữ liệu theo thứ tự ổn định và ghi output an toàn.
7. **Kết nối build graph:** bảo đảm task tiêu thụ output chờ task tạo output.
8. **Quyết định incremental/cache:** chỉ bật khi input/output đầy đủ và công việc có thể tái sử dụng an toàn.
9. **Thử trường hợp thành công và thất bại:** kiểm tra file thiếu, dữ liệu rỗng, quyền đọc/ghi và thay đổi đầu vào.
10. **Thử clean build:** xác nhận toàn bộ output được tạo lại từ source được quản lý.

## 15. Câu hỏi tự kiểm tra

1. Khi nào nên đưa một script thành bước build tự động?
2. Vì sao cần xác định input và output trước khi viết task?
3. Một tham số cấu hình như tiêu đề có thể ảnh hưởng đến output như thế nào?
4. Vì sao file được sinh nên nằm trong thư mục build?
5. Thông báo lỗi tốt cần cung cấp những thông tin gì?
6. Vì sao task không nên chỉ ghi log rồi kết thúc khi output bắt buộc chưa được tạo?
7. Gradle dùng annotation nào để khai báo input files và output file?
8. `@CacheableTask` đòi hỏi task đáp ứng điều kiện gì?
9. Vì sao nên ghi output qua file tạm khi công việc có thể thất bại giữa chừng?
10. Làm thế nào nối output provider của task tạo với task đóng gói?
11. Maven plugin goal khác Gradle task ở cách tích hợp lifecycle và khai báo input/output ra sao?
12. Ant target `depends` mô tả điều gì?
13. Khi nào nên tách custom task thành plugin dùng chung?
14. Vì sao task publish thường cần được tách khỏi task tạo artifact có thể cache?

Khi trả lời được các câu hỏi này, bạn có thể bắt đầu từ một automation nhỏ nhưng có cấu trúc rõ ràng: input được khai báo, output có chủ sở hữu, lỗi được truyền về build tool và task được nối đúng vào quy trình. Đây là nền tảng để mở rộng build logic mà vẫn giữ build dễ hiểu và đáng tin cậy.

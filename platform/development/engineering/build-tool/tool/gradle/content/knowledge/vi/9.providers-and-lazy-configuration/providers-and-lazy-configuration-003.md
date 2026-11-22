# RegularFileProperty, DirectoryProperty và collection properties trong Gradle

Trong Gradle, một task không chỉ cần biết “đường dẫn nào” hoặc “danh sách gì”; nó cần biết **giá trị đó đến từ đâu, khi nào sẵn sàng, có thể thay đổi trong giai đoạn cấu hình hay không và có thuộc đầu vào/đầu ra của task hay không**. Đó là lý do Gradle cung cấp hệ thống *managed properties* và `Provider`.

Ba nhóm thường gặp trong Gradle Kotlin DSL:

- `RegularFileProperty`: lưu **vị trí một tệp thông thường** như `config.json`, `report.txt`, một file kết quả sinh ra.
- `DirectoryProperty`: lưu **vị trí một thư mục** như thư mục dữ liệu đầu vào hoặc thư mục output.
- `ListProperty<T>`, `SetProperty<T>`, `MapProperty<K, V>`: lưu **danh sách/tập hợp/bảng ánh xạ các giá trị** theo cơ chế lazy của Gradle.

Bài học này giải thích các kiểu trên từ nguyên lý đến cách khai báo, cấu hình, nối output task này vào input task khác, xử lý giá trị chưa có, kiểm tra up-to-date và lỗi thực tế.

## 1. Tại sao không chỉ dùng File, List hay Map của Kotlin?

Giả sử bạn khai báo một đường dẫn output ngay trong `build.gradle.kts`:

```kotlin
val path = file("build/reports/summary.txt")
```

`path` là một `java.io.File` thông thường. Nó xác định **một vị trí** trên hệ thống tệp tại lúc biểu thức được đánh giá; bản thân `File` không chứa metadata “task nào tạo file này”. Nếu tính hoặc sử dụng sai thời điểm, build script dễ liên kết task bằng đường dẫn cứng, tự thêm `dependsOn` không đầy đủ và khó thay đổi `buildDirectory` từ nơi khác.

Gradle có thể biểu diễn cùng ý định bằng:

```kotlin
val reportLocation = layout.buildDirectory.file("reports/summary.txt")
```

Ở đây `reportLocation` có kiểu **`Provider<RegularFile>`**: đó là một giá trị vị trí file có thể được tính theo `layout.buildDirectory`. Nếu đặt nó vào `RegularFileProperty` của task và khai báo `@OutputFile`, Gradle biết đây là output của task. Task tiêu thụ output qua provider của task tạo ra có thể được Gradle suy ra dependency thích hợp.

**Cần phân biệt ba lớp:**

| Lớp | Kiểu ví dụ | Ý nghĩa |
| --- | --- | --- |
| Giá trị thông thường | `File`, `List<String>`, `Map<String,String>` | Dữ liệu/đường dẫn đã có; không tự mang cơ chế lazy hoặc task dependency |
| Giá trị vị trí do Gradle mô hình hóa | `RegularFile`, `Directory` | Mô tả vị trí file/thư mục; `.asFile` cho `java.io.File` khi cần |
| Provider và thuộc tính managed | `Provider<RegularFile>`, `RegularFileProperty`, `DirectoryProperty`, `ListProperty<String>` | Cách cung cấp, thay đổi hoặc kết nối giá trị có quản lý trong quá trình cấu hình build |

**“File property” không phải nội dung file.** Nó giữ vị trí file. **“Directory property” không phải thư mục đã được tạo.** Nó giữ vị trí thư mục; việc tồn tại/thay đổi thư mục phụ thuộc task và hệ thống file.

## 2. `Provider<T>` và `Property<T>`: nền tảng chung

`Provider<T>` đại diện cho một giá trị có thể được tính sau hoặc chưa có. `Property<T>` vừa cung cấp giá trị theo giao diện provider, vừa có thể được **cấu hình** bằng `set(...)`, `convention(...)` và các cơ chế Gradle cho phép.

Trong Kotlin DSL, một task tự định nghĩa có thể khai báo:

```kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input

abstract class PrintMessage : DefaultTask() {
    @get:Input
    abstract val message: Property<String>
}
```

Gradle tạo implementation cho getter `abstract val` và cấp một thuộc tính được quản lý; bạn không phải tự xây `Property`. Cách viết này đặc biệt phù hợp cho custom task hoặc extension do Gradle quản lý.

Các thao tác thường gặp:

| Thao tác | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `set(value)` | Gán giá trị rõ ràng cho property | Thay thế giá trị trước đó |
| `set(provider)` | Nối property tới giá trị do provider cung cấp | Giữ quan hệ lazy thay vì đọc ngay |
| `convention(value/provider)` | Đặt mặc định khi chưa có giá trị được set | Build script/người dùng có thể override |
| `get()` | Đọc giá trị và yêu cầu phải có giá trị | Có thể ném lỗi nếu absent; tránh gọi sớm |
| `getOrNull()` / Kotlin `orNull` | Đọc giá trị hoặc trả `null` khi absent | Đây vẫn là thao tác truy xuất |
| `isPresent` | Hỏi provider có giá trị hay không | Không có nghĩa file trên đĩa đã tồn tại |
| `map { ... }` | Biến đổi giá trị do provider cung cấp | Phù hợp cho hàm chuyển đổi thuần |
| `flatMap { ... }` | Chọn một provider khác từ giá trị gốc | Thường dùng lấy output property từ task provider |
| `finalizeValue()` | Khóa giá trị sau khi được chốt | Chỉ áp dụng khi đã có chủ đích cấu hình |

**`convention` không giống `set`.** Ví dụ:

```kotlin
// Trong closure cấu hình của một task có message: Property<String>
message.convention("hello")
message.set("hello from user")
```

Kết quả của `message.get()` là `"hello from user"`. Nếu bỏ `set`, kết quả là `"hello"`. Không nên gọi `get()` trong lúc đặt mặc định chỉ để biến provider thành giá trị thường: điều đó có thể gây tính toán sớm hoặc làm mất thông tin dependency.

Hệ thống này gắn với **Configuration** và **Execution**: cấu hình task nối các provider khi build được cấu hình; task action đọc giá trị ở thời điểm sử dụng. Đây không phải cơ chế “chạy background” hay tự theo dõi thay đổi file theo thời gian thực.

## 3. `RegularFileProperty`: một vị trí tệp được cấu hình lười

API `org.gradle.api.file.RegularFileProperty` là managed property cho vị trí **một file**, thường dùng với:

- `@InputFile`: task cần đọc một file.
- `@OutputFile`: task tạo một file.
- `@Optional` kết hợp input annotation: file đầu vào có thể không được cấu hình.
- `@PathSensitive(...)`: nói với Gradle phần nào của đường dẫn input quan trọng khi theo dõi thay đổi.

Trong custom task Kotlin:

```kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.OutputFile

abstract class WriteReport : DefaultTask() {
    @get:OutputFile
    abstract val reportFile: RegularFileProperty
}
```

Đây mới là **khai báo thuộc tính**, chưa có task action viết file. Khi đăng ký task, có thể cấu hình:

```kotlin
tasks.register<WriteReport>("writeReport") {
    reportFile.set(layout.buildDirectory.file("reports/summary.txt"))
}
```

Các câu lệnh trên là **mảnh ghép minh họa** để hiểu khai báo/cấu hình; một ví dụ độc lập có `@TaskAction` được trình bày đầy đủ ở mục 8.

### Ba kiểu dễ nhầm trong biểu thức

```kotlin
val futureFile: Provider<RegularFile> =
    layout.buildDirectory.file("reports/summary.txt")

// Trong closure cấu hình task có reportFile: RegularFileProperty
reportFile.set(futureFile)

// Khi thực sự cần truy cập đường dẫn bằng java.io.File:
val javaFile: File = reportFile.get().asFile
```

- `layout.buildDirectory` là **`DirectoryProperty`** của `ProjectLayout`.
- `layout.buildDirectory.file("reports/summary.txt")` trả **`Provider<RegularFile>`**.
- `reportFile` là **`RegularFileProperty`** (vừa cấu hình được vừa đọc được).
- `reportFile.get()` trả **`RegularFile`** (giá trị vị trí).
- `reportFile.get().asFile` trả **`java.io.File`**. Bạn có thể dùng `readText`/`writeText` trong task action, nhưng việc có `File` không đảm bảo file hiện đã tồn tại.

Cũng có thể viết `reportFile.asFile.get()` để lấy `File`. Dạng `asFile` của managed property trả một provider của `java.io.File` và vẫn giữ đường đi lazy cho tới lúc gọi `get()`.

**Tại sao dùng `layout.buildDirectory`?** Thư mục build có thể được nhóm đổi cấu hình, và output sẽ đi theo cấu hình đó. Tránh ghim đường dẫn cứng `"build/..."` ở mọi task, đặc biệt trong multi-project build.

### Không có file khi cấu hình không có nghĩa là lỗi

```kotlin
val output = layout.buildDirectory.file("reports/output.txt")
```

Có thể cấu hình `output` dù file chưa được tạo. File chỉ cần tồn tại **sau task tạo ra nó**. Nếu đây là input của task, Gradle có thể kiểm tra file tại thời điểm task thực thi. Đối với output, task action có trách nhiệm tạo nội dung file ở vị trí đã khai báo.

## 4. `DirectoryProperty`: một vị trí thư mục

API `org.gradle.api.file.DirectoryProperty` biểu diễn vị trí **một thư mục**. Nó thường gắn với:

| Annotation | Ý định |
| --- | --- |
| `@InputDirectory` | Task đọc nội dung từ một thư mục đầu vào |
| `@OutputDirectory` | Task tạo tệp/thư mục dưới một thư mục output |
| `@Optional` + `@InputDirectory` | Thư mục đầu vào có thể vắng mặt như một input tùy chọn; task phải tự xử lý absent |
| `@PathSensitive` + input annotation | Chọn cách nhận dạng path khi theo dõi thay đổi input |

Ví dụ khai báo:

```kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.OutputDirectory

abstract class ProcessDirectory : DefaultTask() {
    @get:InputDirectory
    abstract val sourceDirectory: DirectoryProperty

    @get:OutputDirectory
    abstract val destinationDirectory: DirectoryProperty
}
```

Đây là định nghĩa model; để chạy được, task cần có action xử lý nội dung và bạn phải cấu hình hai thuộc tính.

Ví dụ cấu hình **trong task được đăng ký**:

```kotlin
sourceDirectory.set(layout.projectDirectory.dir("docs"))
destinationDirectory.set(layout.buildDirectory.dir("processed-docs"))
```

- `layout.projectDirectory` là `Directory` đại diện cho thư mục project hiện tại.
- `layout.projectDirectory.dir("docs")` là **`Directory`** con, được tính từ đường dẫn project.
- `layout.buildDirectory.dir("processed-docs")` trả **`Provider<Directory>`** vì thư mục build là cấu hình có thể thay đổi.
- `destinationDirectory.get().asFile` cho `File` khi task action cần tạo tệp con.

### Tạo file con từ DirectoryProperty

```kotlin
// Trong closure cấu hình task có destinationDirectory: DirectoryProperty
val outputFileProvider: Provider<RegularFile> =
    destinationDirectory.file("summary.txt")

val outputSubDirProvider: Provider<Directory> =
    destinationDirectory.dir("assets")
```

Lưu ý `destinationDirectory.file(...)` và `.dir(...)` trả **provider của vị trí con**, không tự tạo file hoặc thư mục. Có thể nối provider file con đó vào input/output của task khác nếu quan hệ task và annotation được khai báo rõ.

### Đường dẫn tương đối và ranh giới project

Trong multi-project build, `layout.projectDirectory` thuộc **project hiện tại**. Nếu task khai báo ở `:app`, đường dẫn `layout.projectDirectory.dir("src")` thường trỏ tới `app/src`, không phải root `src`. Tránh giả định current working directory của tiến trình luôn là root project.

Với đường dẫn đầu vào cố định theo project, dùng `layout.projectDirectory.file("...")` hoặc `.dir("...")`. Với đầu ra build, dùng `layout.buildDirectory.file("...")` hoặc `.dir("...")`. Không nối chuỗi absolute path theo hệ điều hành rồi dùng `File("relative/path")` trong task action nếu không xác định đúng base.

## 5. Điểm giống và khác của hai file-system properties

| Tiêu chí | RegularFileProperty | DirectoryProperty |
| --- | --- | --- |
| Giá trị khi `get()` | `RegularFile` | `Directory` |
| Cấu hình `set(...)` | Nhận vị trí file/provider file phù hợp | Nhận vị trí directory/provider directory phù hợp |
| Ví dụ nguồn | `layout.projectDirectory.file("config/app.yml")` | `layout.projectDirectory.dir("src/main/resources")` |
| Ví dụ output | `layout.buildDirectory.file("reports/report.txt")` | `layout.buildDirectory.dir("generated")` |
| Input annotation | `@InputFile` | `@InputDirectory` |
| Output annotation | `@OutputFile` | `@OutputDirectory` |
| Truy cập bằng Java API | `get().asFile` | `get().asFile` |
| Lấy đường dẫn con | Không phải nhiệm vụ của một file riêng lẻ | `file("child.txt")` hoặc `dir("child")` |

Một file input không nên annotate `@Input` như một scalar string nếu thực chất nó là đường dẫn/nội dung file cần theo dõi. `@InputFile` cho Gradle biết phải fingerprint dữ liệu file theo mô hình input của task. Tương tự, `@OutputDirectory` cho biết tập kết quả được task quản lý nằm dưới một thư mục.

**Chỉ khai báo location không tự biến task thành incremental hay cacheable.** Gradle còn cần phân loại input/output chính xác, logic action ổn định, và đối với reuse từ build cache thì tuân thủ quy định cacheability.

## 6. Collection properties: ListProperty, SetProperty, MapProperty

Gradle cung cấp các kiểu đặc biệt thay vì chỉ dùng `Property<List<T>>` hay `Property<Map<K,V>>`:

| Kiểu | Giá trị khi `get()` | Cách dùng phù hợp |
| --- | --- | --- |
| `ListProperty<T>` | `List<T>` | Danh sách có thứ tự, cho phép phần tử trùng |
| `SetProperty<T>` | `Set<T>` | Tập phần tử duy nhất; tránh phụ thuộc thứ tự tùy ý |
| `MapProperty<K,V>` | `Map<K,V>` | Bảng ánh xạ key → value |

Các property này cho phép nhiều lớp cấu hình đóng góp từng phần tử mà không phải đọc, sửa rồi gán lại cả collection. Điều đó có ích trong convention plugin, build script của từng module và plugin bổ sung.

### Khai báo trong custom task

```kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.provider.ListProperty
import org.gradle.api.provider.MapProperty
import org.gradle.api.provider.SetProperty
import org.gradle.api.tasks.Input

abstract class ReportOptions : DefaultTask() {
    @get:Input
    abstract val modules: ListProperty<String>

    @get:Input
    abstract val tags: SetProperty<String>

    @get:Input
    abstract val labels: MapProperty<String, String>
}
```

Khi task có action sử dụng ba property, `@Input` giúp Gradle theo dõi **các giá trị cấu hình** này khi tính trạng thái up-to-date. Đối với tập **các file**, hãy cân nhắc `ConfigurableFileCollection` và `@InputFiles` thay vì `ListProperty<String>` chứa đường dẫn.

### Set, convention và bổ sung từng phần

Đoạn sau đây giả định đang ở closure cấu hình của task có ba thuộc tính như trên:

```kotlin
modules.convention(listOf("api", "core"))
modules.add("web")
modules.addAll(listOf("worker", "batch"))

tags.convention(setOf("stable"))
tags.add("verified")
tags.add("stable")

labels.convention(mapOf("owner" to "platform"))
labels.put("language", "vi")
labels.put("stage", "qa")
```

Ý nghĩa:

- `modules`: danh sách giữ **thứ tự** các giá trị, phù hợp khi việc sắp xếp module có ý nghĩa.
- `tags`: tập hợp chỉ giữ **một** giá trị `"stable"`, dù thêm trùng.
- `labels`: map chứa các cặp key-value, `put` cho phép thêm hoặc thay một key.
- `convention` cung cấp dữ liệu mặc định; `add`/`addAll`/`put` cho phép đóng góp theo cơ chế collection property, thay vì `get()` rồi mutate một bản Kotlin list/map.

Các kiểu Gradle này **không phải** `MutableList`/`MutableMap` của Kotlin. Gọi `modules.get().add("x")` là sai cách; giá trị trả về không nên được sửa trực tiếp. Hãy gọi `modules.add("x")` trên property ở giai đoạn cấu hình.

### `set` khác `add`, `put`

```kotlin
modules.set(listOf("cli", "server"))      // Thay toàn bộ list
modules.add("desktop")                  // Bổ sung một mục
tags.set(setOf("release"))              // Thay toàn bộ set
labels.put("owner", "docs")             // Thay value của một key
labels.set(mapOf("mode" to "strict"))    // Thay toàn bộ map
```

Khi một plugin đặt convention và build script đặt explicit `set`, giá trị explicit được ưu tiên. Khi cần **tạo danh sách rỗng có chủ đích**, các collection property cũng có phương thức `empty()`; đừng nhầm giá trị **rỗng** với provider **absent**.

### Lấy một giá trị từ MapProperty

```kotlin
// Giả sử labels: MapProperty<String, String>
val stageProvider = labels.getting("stage")
val stageOrDefault = stageProvider.orElse("dev")
```

`getting(key)` trả về **provider của giá trị cho key**, giúp giữ tính lazy khi truy xuất từng mục. Khác với `labels.get()["stage"]` là đọc **toàn bộ map** ngay rồi tra khóa, `labels.getting("stage")` có thể được truyền tiếp vào property khác. Nếu key không có giá trị, provider có thể absent và `orElse` chỉ định mặc định.

## 7. Property collection cũng có thể nhận Provider

Thay vì biến input thành chuỗi ngay trong Configuration, bạn có thể nối provider:

```kotlin
// Trong closure có modules: ListProperty<String>
modules.add(providers.gradleProperty("extraModule").orElse("docs"))
```

Nếu CLI có `-PextraModule=api`, phần tử được góp vào list là `api`. Nếu không có, dùng `docs`. Lúc cấu hình, Gradle nhận **provider**; giá trị được giải quyết khi thực sự cần.

Ví dụ mapping giá trị:

```kotlin
val raw = providers.gradleProperty("modules").orElse("app,lib")
val parsed = raw.map { csv ->
    csv.split(',')
        .map { it.trim() }
        .filter { it.isNotEmpty() }
}

modules.set(parsed)
```

Ở đây `parsed` là **`Provider<List<String>>`**, nên `modules.set(parsed)` nhận toàn bộ danh sách theo cơ chế lazy. Phân biệt:

- `modules.set(parsed)`: thay cả danh sách bằng list từ provider.
- `modules.add(providerOfOneString)`: thêm **một phần tử**.
- `modules.addAll(providerOfList)`: thêm **nhiều phần tử** từ provider list.

Đối với map:

```kotlin
labels.put("branch", providers.gradleProperty("branch").orElse("local"))
```

Nếu provider chỉ có giá trị tùy theo môi trường, dùng `orElse`/`getOrElse` hợp lý; đừng gọi `get()` trên provider có thể absent rồi để lỗi mơ hồ.

**Không in hoặc chuyển credential thật thành `MapProperty` `@Input` rồi log ra output.** Với secret cần thiết, dùng nguồn credential phù hợp và tuân thủ chính sách xử lý dữ liệu, vì input fingerprints, task logs và cache có những cân nhắc riêng.

## 8. Ví dụ hoàn chỉnh: tạo manifest rồi xử lý output qua Provider

Ví dụ này có **hai custom task types**. Task đầu tạo một file `manifest.txt`, dùng cả `ListProperty`, `SetProperty`, `MapProperty` và `RegularFileProperty`. Task sau nhận file đó thông qua **`RegularFileProperty` đầu vào** và tạo một thư mục `DirectoryProperty` output.

Trong project Gradle Kotlin DSL có Wrapper, tạo tệp `settings.gradle.kts`:

```kotlin
rootProject.name = "managed-properties-demo"
```

Tạo **toàn bộ** tệp `build.gradle.kts`:

```kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.ListProperty
import org.gradle.api.provider.MapProperty
import org.gradle.api.provider.SetProperty
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

abstract class GenerateManifest : DefaultTask() {
    @get:Input
    abstract val modules: ListProperty<String>

    @get:Input
    abstract val tags: SetProperty<String>

    @get:Input
    abstract val labels: MapProperty<String, String>

    @get:OutputFile
    abstract val manifestFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val destination = manifestFile.get().asFile
        destination.parentFile.mkdirs()

        val text = listOf(
            "modules=" + modules.get().joinToString(","),
            "tags=" + tags.get().sorted().joinToString(","),
            "labels=" + labels.get().toSortedMap().entries
                .joinToString(",") { "${it.key}:${it.value}" }
        ).joinToString("\n") + "\n"

        destination.writeText(text, Charsets.UTF_8)
        println("Created: ${destination.name}")
    }
}

abstract class CopyManifest : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val sourceFile: RegularFileProperty

    @get:OutputDirectory
    abstract val destinationDirectory: DirectoryProperty

    @TaskAction
    fun copy() {
        val source = sourceFile.get().asFile
        val targetDir = destinationDirectory.get().asFile
        targetDir.mkdirs()
        targetDir.resolve(source.name)
            .writeText(source.readText(Charsets.UTF_8), Charsets.UTF_8)

        val firstLine = source.useLines { it.first() }
        println("Copied: ${source.name}")
        println("First line: $firstLine")
    }
}

val generateManifest = tasks.register<GenerateManifest>("generateManifest") {
    modules.convention(listOf("api", "worker"))
    modules.add("web")

    tags.convention(setOf("stable"))
    tags.add("verified")

    labels.convention(mapOf("format" to "text"))
    labels.put("lang", "vi")

    manifestFile.set(layout.buildDirectory.file("generated/manifest.txt"))
}

tasks.register<CopyManifest>("copyManifest") {
    // Không cần dependsOn thủ công: nối trực tiếp output task tạo file.
    sourceFile.set(generateManifest.flatMap { it.manifestFile })

    destinationDirectory.set(layout.buildDirectory.dir("processed"))
}
```

Chạy lệnh từ root của project (Linux/macOS):

```bash
./gradlew copyManifest --no-configuration-cache --console=plain -q
```

Tương đương Windows PowerShell:

```powershell
.\gradlew.bat copyManifest --no-configuration-cache --console=plain -q
```

Trong **lần chạy đầu** khi chưa có output, không có build logic khác chèn thêm console output và tasks được thực thi, các dòng do hai task actions in ra là:

```text
Created: manifest.txt
Copied: manifest.txt
First line: modules=api,worker,web
```

Gradle tạo hai đầu ra:

```text
build/
├── generated/
│   └── manifest.txt
└── processed/
    └── manifest.txt
```

Nội dung cả hai file là:

```text
modules=api,worker,web
tags=stable,verified
labels=format:text,lang:vi
```

**Phân tích từng bước:**

1. `tasks.register<GenerateManifest>` đăng ký task theo cơ chế tránh cấu hình sớm. Trong closure, `convention` đặt mặc định cho collections và `add`/`put` góp thêm giá trị.
2. `manifestFile.set(layout.buildDirectory.file(...))` đặt file output bằng một `Provider<RegularFile>`.
3. `generateManifest` là `TaskProvider<GenerateManifest>`, chưa phải một task đã bắt buộc chạy.
4. `generateManifest.flatMap { it.manifestFile }` trả provider cho output file của task tạo. Đặt provider này vào `sourceFile` giữ thông tin **producer task**.
5. Khi yêu cầu `copyManifest`, Gradle hiểu file input được sản xuất bởi `generateManifest`, nên sắp xếp task tạo file **trước** task copy. Đây là **implicit task dependency** có ý nghĩa, không cần tự `dependsOn("generateManifest")`.
6. `@Input` theo dõi ba collection values; `@OutputFile` ghi nhận manifest; `@InputFile` + `@PathSensitive` mô tả file tiêu thụ; `@OutputDirectory` mô tả thư mục chứa bản sao.
7. Trong `@TaskAction`, mới gọi `get().asFile` và dùng API `writeText`/`readText`/tạo directory.
8. Nếu chạy lặp lại mà inputs/outputs không đổi, Gradle có thể đánh dấu task là **UP-TO-DATE** và **không in** các dòng từ task actions. Đây là kết quả đúng, không phải thiếu output.

Ví dụ viết task types trực tiếp trong build script để dễ học. Với build lớn, nên đặt types trong convention plugin hoặc `build-logic`/`buildSrc` phù hợp để dễ test và reuse.

### Vì sao không đặt cả hai task trỏ đến cùng một path?

Nếu `copyManifest` tự gọi `file("build/generated/manifest.txt")` rồi thêm `dependsOn`, Gradle chỉ biết hai thông tin rời rạc. Khi file output đổi tên hoặc thư mục build đổi, các đường dẫn dễ lệch nhau. Kết nối qua `generateManifest.flatMap { it.manifestFile }` dùng **source of truth là output property của task tạo** và duy trì quan hệ dependency.

## 9. Đọc một thư mục đầu vào từ task tạo thư mục

Giả sử một task sinh ra thư mục output có property `generatedDirectory: DirectoryProperty`, còn task tiếp theo cần đọc cả thư mục. Pattern trong closure cấu hình task tiêu thụ là:

```kotlin
// producer: TaskProvider<Producer> với generatedDirectory: DirectoryProperty
// consumer: task có sourceDirectory: DirectoryProperty được gắn @InputDirectory
sourceDirectory.set(producer.flatMap { it.generatedDirectory })
```

Đây là **mẫu mã minh họa**, không phải file có thể chạy độc lập vì hai task types chưa được định nghĩa ở đây. Nó cho thấy `DirectoryProperty` cũng tham gia implicit task dependency như `RegularFileProperty`.

Nếu chỉ tiêu thụ **một file** do producer tạo trong thư mục, tốt nhất producer khai báo chính xác `@OutputFile` của file đó. Chỉ dùng `sourceDirectory.set(producer.flatMap { it.generatedDirectory })` khi mục đích của consumer thực sự là xử lý **toàn bộ directory**. Không đọc một thư mục khổng lồ khi task chỉ cần một file.

Đối với nhiều file input độc lập, ưu tiên `ConfigurableFileCollection` với `@InputFiles` hoặc `@Classpath` khi đó là classpath, để Gradle theo dõi đúng các file và task producers.

## 10. Chọn annotation cho đúng ý nghĩa

Các managed properties tự mô tả được kiểu, nhưng **Gradle vẫn cần annotation** ở custom task để phân loại input/output.

| Thuộc tính task | Annotation thường dùng | Gradle theo dõi |
| --- | --- | --- |
| `Property<String>` | `@Input` | Một giá trị cấu hình |
| `ListProperty<String>` | `@Input` | Nội dung list |
| `SetProperty<String>` | `@Input` | Các giá trị trong set |
| `MapProperty<String,String>` | `@Input` | Các cặp trong map |
| `RegularFileProperty` đầu vào | `@InputFile` | File đầu vào |
| `DirectoryProperty` đầu vào | `@InputDirectory` | Thư mục đầu vào |
| `RegularFileProperty` đầu ra | `@OutputFile` | File do task tạo |
| `DirectoryProperty` đầu ra | `@OutputDirectory` | Thư mục do task tạo |
| `ConfigurableFileCollection` đầu vào | `@InputFiles` hoặc `@Classpath` | Nhiều file/classpath |
| Input có thể vắng mặt | `@Optional` + annotation đầu vào | Cho phép giá trị optional, task tự xử lý |

Kotlin dùng **`@get:...`** cho các getter abstract properties, ví dụ `@get:InputFile`, `@get:OutputDirectory`.

Với `@InputFile`/`@InputDirectory`, nên xem xét `@PathSensitive(PathSensitivity.RELATIVE)` hoặc `NAME_ONLY`/`NONE` tùy ý nghĩa. `RELATIVE` thường thích hợp khi đường dẫn tương đối của input quan trọng để phát hiện thay đổi; `ABSOLUTE` có thể khiến build kém relocatable. Chọn sai path sensitivity có thể làm up-to-date check thiếu hoặc thừa invalidation.

**Output properties không phải input properties.** Đừng đánh dấu một file chỉ dùng để ghi là `@InputFile` khi nó chưa tồn tại; Gradle có thể kiểm tra thiếu input và báo lỗi. Đừng annotate một `MapProperty<String,String>` như `@OutputFiles`: đó là các giá trị cấu hình, không phải tập output files.

## 11. Giá trị optional: absent, empty và file chưa tồn tại

Ba trạng thái dưới đây khác nhau:

| Trạng thái | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Provider/property **absent** | Chưa `set`, không `convention`; đọc `orNull` trả null | Chưa có giá trị cấu hình |
| Collection **rỗng nhưng present** | `modules.empty()` hoặc `modules.set(emptyList())` | Có giá trị hợp lệ là danh sách rỗng |
| File location **present nhưng file chưa tồn tại** | `outputFile.set(layout.buildDirectory.file("new.txt"))` | Đã biết vị trí; nội dung sẽ được task tạo sau |

Điều này rất quan trọng: `isPresent` ở `RegularFileProperty` cho biết **property có vị trí được cấu hình**, chứ không kiểm tra `File.exists()`. Với input thực sự tùy chọn, ví dụ:

```kotlin
@get:Optional
@get:InputFile
abstract val optionalConfig: RegularFileProperty
```

Trong `@TaskAction`, xử lý:

```kotlin
val config: File? = optionalConfig.orNull?.asFile
if (config != null) {
    // Chỉ đọc nếu đây là input đã được cấu hình và hợp lệ
}
```

Đây là **mảnh ghép trong custom task**, không phải một đoạn độc lập. `@Optional` cho phép property **không có giá trị**; nó **không tự coi một đường dẫn đã được cấu hình nhưng không tồn tại là hợp lệ**. Nếu muốn task bỏ qua khi input files rỗng, `@SkipWhenEmpty` là khái niệm khác, áp dụng cho các loại file inputs tương thích.

Trong Kotlin, `getOrNull()`, `orNull`, `isPresent` và `getOrElse(default)` là các cách đọc provider; nên chọn mặc định theo nghiệp vụ, không chỉ để làm build vượt qua lỗi “chưa có cấu hình bắt buộc”.

## 12. Up-to-date, build cache và Configuration Cache

Hai loại cache và kiểm tra up-to-date có phạm vi khác nhau:

- **Up-to-date checks**: dựa trên inputs/outputs của task để quyết định có cần chạy action hay không trong một build cụ thể.
- **Build Cache**: có thể lưu/tái sử dụng output của các task đủ điều kiện cache. Chỉ `@OutputFile` hoặc `@OutputDirectory` **không tự đảm bảo** task được cache.
- **Configuration Cache**: lưu cấu hình và task graph để tránh phải đánh giá lại settings/build scripts ở lần build tương thích tiếp theo.

Managed properties giúp Gradle mô hình hóa input/output; chúng **không** làm một task trở nên pure, deterministic hay cacheable một cách tự động. Custom task muốn cache tốt còn phải khai báo đúng mọi input, không phụ thuộc vào dữ liệu ẩn và tạo output tái lập.

### Tránh sử dụng Project từ task action

Pattern không khuyến nghị:

```kotlin
tasks.register("badAction") {
    doLast {
        val output = project.file("build/report.txt")
        output.writeText("hello")
    }
}
```

Action này truy cập `Project` khi Execution, có thể vi phạm yêu cầu của Configuration Cache. Hơn nữa, output chưa được khai báo bằng `@OutputFile` hoặc `outputs.file(...)` nên Gradle không có mô hình đầu ra đầy đủ.

Cách tốt hơn: định nghĩa task type có `RegularFileProperty`, khai báo `@OutputFile` và cấu hình bằng `layout.buildDirectory.file(...)` như ví dụ ở mục 8. Khi action chạy, nó chỉ dùng property đã được quản lý.

### Không đọc provider quá sớm

```kotlin
// Không khuyến nghị: ép thành File trong lúc configuration
val outputPath = layout.buildDirectory.file("results/log.txt").get().asFile
```

Cách trên làm mất ý nghĩa lazy của phép truy cập tại chỗ đó và gắn sớm vị trí output. Nếu cần truyền cho task, viết:

```kotlin
// Trong closure có property outputFile: RegularFileProperty
outputFile.set(layout.buildDirectory.file("results/log.txt"))
```

Đọc `outputFile.get().asFile` **bên trong task action** khi thực sự cần tương tác với file.

### Provider không đồng nghĩa Gradle tự chạy một task

Đoạn `layout.buildDirectory.file("results/log.txt")` chỉ là provider cho **vị trí** file; Gradle không thể tự biết task nào sẽ tạo file đó nếu không liên kết producer. Muốn suy ra dependency, hãy nối consumer tới **provider của output property trên producer task** (và khai báo input/output thích hợp), không chỉ truyền hai path giống nhau.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `No value has been specified for property ...` | `Property` bắt buộc chưa set/convention | Khai báo input/output ở nơi đăng ký task; kiểm tra provider absent |
| `input file does not exist` | Dùng `@InputFile` nhưng file chưa có; producer chưa được nối hoặc source path sai | Nối đúng `producer.flatMap { it.outputFile }`; kiểm tra file nguồn và annotation |
| Một đường dẫn output đã cấu hình nhưng `isPresent` true dù file không tồn tại | Nhầm trạng thái property với trạng thái filesystem | Kiểm tra output sau task; đừng dùng `isPresent` để kiểm tra disk |
| `get()` ném exception trong Configuration | Đọc quá sớm hoặc provider không có giá trị | Truyền provider sang property khác; dùng `convention`/`orElse` khi có mặc định hợp lý |
| Thay `buildDirectory` mà output task không theo | Ghép path cứng hoặc gọi `.get()` sớm | Dùng `layout.buildDirectory.file/dir` và giữ provider |
| Consumer chạy trước producer hoặc báo thiếu input | Chỉ dùng đường dẫn giống nhau, chưa truyền output property của task | Dùng `producer.flatMap { it.outputFile }` để giữ dependency |
| Có nhiều file nhưng dùng `RegularFileProperty` | Kiểu chỉ biểu diễn **một** file | Dùng `ConfigurableFileCollection`/`@InputFiles` |
| Muốn thêm mục vào list nhưng `get().add(...)` lỗi | Đang sửa list kết quả, không sửa managed property | Dùng `ListProperty.add` hoặc `addAll` |
| Trùng lặp biến mất khỏi SetProperty | Set chỉ giữ phần tử duy nhất | Chọn `ListProperty` nếu trùng có ý nghĩa |
| Đọc map thiếu key rồi gọi `get()` | Provider của key absent | Dùng `getting(key).orElse(default)` hoặc báo lỗi cấu hình có chủ đích |
| Thay list bằng `set` và mất đóng góp của plugin | `set` thay toàn bộ collection | Dùng `convention`, `add`/`addAll` cho composition theo nhu cầu |
| Gradle bỏ qua task ở lần chạy thứ hai | Inputs/outputs không đổi, task `UP-TO-DATE` | Đây thường là tối ưu hợp lệ; đổi input hoặc kiểm tra output |
| File output được ghi nhưng build cache không dùng | Output annotation không tự làm task cacheable | Xem chính sách cacheability và kiểm tra task có deterministic/relocatable không |
| Configuration Cache thất bại khi action truy cập `project` | Task action giữ object không phù hợp ở execution | Đưa dữ liệu cần dùng vào managed task properties |
| `@OutputDirectory` và `@OutputFile` cùng quản lý một cây output lồng nhau | Khai báo output chồng lấn gây mơ hồ ownership | Thiết kế mỗi task sở hữu output riêng; tránh tasks cùng ghi một vị trí |
| Build trên Windows khác Linux | Dùng path separator/absolute path cố định | Dùng `layout.projectDirectory`, `layout.buildDirectory`, `RegularFile`/`Directory` |

## 14. Lưu ý thiết kế trong dự án nhiều module

Trong multi-project Gradle build, `layout.buildDirectory` và `layout.projectDirectory` thuộc **Project nơi script/task được cấu hình**. Khi `:app` cần output của `:library`, không nên tự đoán `"../library/build/..."`; hãy dùng một provider sản xuất bởi task phù hợp, plugin convention, hoặc mechanism hỗ trợ chia sẻ artifacts giữa projects.

Tùy bối cảnh, output có thể được công bố qua **outgoing configuration** và consumed như một **project dependency**. Đây là lựa chọn tốt hơn cho ranh giới giữa nhiều project so với truy cập trực tiếp task internals của project khác. Ví dụ nội bộ ở mục 8 chỉ minh họa **producer và consumer trong cùng project**, nơi việc nối TaskProvider với task property là rõ ràng.

Nếu plugin dùng chung cần đặt mặc định output:

```kotlin
// Trong cấu hình task có outputDirectory: DirectoryProperty
outputDirectory.convention(layout.buildDirectory.dir("generated/my-plugin"))
```

Build script của consumer có thể `set` một vị trí khác nếu API cho phép. Khi muốn plugin và build script cùng góp nhiều mục, chọn `ListProperty`/`SetProperty`/`MapProperty` thay cho `Property<List<...>>` opaque.

Khi task tạo ra nhiều file dưới cùng một output directory, dùng `@OutputDirectory` nếu **toàn bộ thư mục là output được task sở hữu**. Khi task chỉ tạo một file, `@OutputFile` mô tả chính xác hơn; tránh đánh dấu thư mục `build/` chung của nhiều task là output riêng của một task.

## 15. Câu hỏi và bài tập tự kiểm tra

**Câu 1.** `layout.buildDirectory.file("a.txt")` trả `RegularFileProperty` hay `Provider<RegularFile>`?

**Đáp:** Trả `Provider<RegularFile>`. Bản thân `layout.buildDirectory` là `DirectoryProperty`. Có thể `set` provider này vào `RegularFileProperty` của task.

**Câu 2.** `RegularFileProperty.isPresent` trả `true` có đảm bảo file đã nằm trên ổ đĩa không?

**Đáp:** Không. Nó phản ánh vị trí được cấu hình/có giá trị, không phản ánh file tồn tại.

**Câu 3.** Task tạo `report.txt`; task khác đọc file đó. Cách nào giúp Gradle tự biết dependency?

**Đáp:** Task tạo khai báo `@OutputFile abstract val reportFile: RegularFileProperty`, task đọc khai báo `@InputFile abstract val sourceFile: RegularFileProperty`, và cấu hình `sourceFile.set(producer.flatMap { it.reportFile })`.

**Câu 4.** Khác biệt giữa `ListProperty.add("x")` và `ListProperty.set(listOf("x"))`?

**Đáp:** `add` góp thêm một mục vào tập giá trị hiện tại; `set` thay thế toàn bộ list bằng một giá trị rõ ràng. Dùng `convention` để cung cấp mặc định có thể override.

**Câu 5.** Dùng `SetProperty<String>` hay `ListProperty<String>` khi thứ tự lặp và phần tử trùng đều có ý nghĩa?

**Đáp:** `ListProperty<String>`, vì set loại bỏ phần tử trùng. Nếu thứ tự không là hợp đồng nghiệp vụ, vẫn nên sắp xếp rõ trước khi ghi output để build deterministic.

**Câu 6.** `MapProperty<String,String>.getting("mode")` khác `map.get()["mode"]` ở đâu?

**Đáp:** `getting("mode")` trả `Provider<String>` cho giá trị key; `get()["mode"]` đọc map ngay rồi tra cứu và cho kết quả Kotlin có thể null. Có thể nối `getting` vào một managed property khác.

**Câu 7.** Một task chỉ cần duy nhất file `config.yml`. Nên dùng `@InputDirectory` trên thư mục `config/` hay `@InputFile` trên file cụ thể?

**Đáp:** Nếu thật sự chỉ đọc file đó, dùng `@InputFile RegularFileProperty` và path sensitivity phù hợp để input chính xác, tránh tracking thừa cả directory.

**Câu 8.** Task action ghi vào `layout.buildDirectory.file("x.txt")` có được khuyến nghị không?

**Đáp:** Không nên truy cập `ProjectLayout` qua `project` từ action. Hãy cấu hình một `@OutputFile RegularFileProperty` trước, action chỉ đọc `outputFile.get().asFile`. Cách này dễ hỗ trợ Configuration Cache và khai báo output rõ.

**Câu 9.** Đặt `@OutputDirectory` có nghĩa Gradle tự đảm bảo build cache hoạt động không?

**Đáp:** Không. Property chỉ mô tả output. Build cache có các điều kiện riêng về cacheability, inputs, tính tái lập và an toàn của task implementation.

## 16. Nguồn tham khảo chính thức

- [Gradle — Properties and Providers](https://docs.gradle.org/current/userguide/properties_providers.html): managed properties, Provider/Property và các loại giá trị Gradle quản lý.
- [Gradle — Implementing Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html): kiểu property task, `@InputFile`, `@InputDirectory`, `@OutputFile`, `@OutputDirectory` và `@TaskAction`.
- [Gradle — Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html): wiring input/output, collection property types và cách thiết kế task.
- [Gradle — Working With Files](https://docs.gradle.org/current/userguide/working_with_files.html): file providers, project layout, paths, Copy/Sync và output directories.
- [Gradle — Lazy Configuration](https://docs.gradle.org/current/userguide/lazy_configuration.html): cách nối, biến đổi và truy xuất providers.
- [Gradle — Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html): giới hạn khi task actions truy cập `Project` và dữ liệu không thích hợp.
- [Gradle API — RegularFileProperty](https://docs.gradle.org/current/javadoc/org/gradle/api/file/RegularFileProperty.html), [DirectoryProperty](https://docs.gradle.org/current/javadoc/org/gradle/api/file/DirectoryProperty.html), [ListProperty](https://docs.gradle.org/current/javadoc/org/gradle/api/provider/ListProperty.html), [SetProperty](https://docs.gradle.org/current/javadoc/org/gradle/api/provider/SetProperty.html), [MapProperty](https://docs.gradle.org/current/javadoc/org/gradle/api/provider/MapProperty.html): API và hành vi từng kiểu.

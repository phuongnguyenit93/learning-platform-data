# Phân biệt `@Internal`, `@Optional` và dữ liệu cần theo dõi trong Gradle Custom Task

## 1. Vấn đề: khai báo đúng để Gradle biết lúc nào phải chạy task

Khi viết một **custom task** trong Gradle, phần khó không chỉ nằm ở mã của `@TaskAction`. Quan trọng hơn là diễn tả chính xác **input nào quyết định kết quả**, **output nào được tạo**, và **giá trị nào chỉ hỗ trợ vận hành mà không làm kết quả thay đổi**. Những khai báo này chi phối up-to-date checking, Build Cache và tính chính xác khi task được dùng bởi task khác.

Hai annotation thường bị nhầm:

- **`@Internal`**: property bị **loại khỏi việc theo dõi input/output** của Gradle. Thay đổi property này tự nó không khiến task bị xem là out-of-date; property cũng không bị kiểm tra presence. Chỉ dùng khi property thực sự không quyết định output hay kết quả cần theo dõi.
- **`@Optional`**: modifier cho một property **vẫn là input hoặc output**, nhưng cho phép property **không có giá trị**. Khi có giá trị, Gradle vẫn kiểm tra/ghi nhận nó. Nó phải đi kèm `@Input`, `@InputFile`, `@OutputFile` hoặc annotation hợp lệ khác.

**Không được kết hợp `@Internal` và `@Optional` trên cùng getter.** Gradle coi điều này là lỗi validation: internal đã được xem là không bắt buộc, còn optional phải đi với annotation input/output thật sự.

Ví dụ: `diagnosticLabel` chỉ in ra log → có thể `@Internal`; `header` nếu có sẽ xuất hiện trong file báo cáo → `@Optional` + `@Input`; `templateFile` nếu có được đọc để sinh nội dung → `@Optional` + `@InputFile` và path normalization; file báo cáo được tạo → `@OutputFile`.

Bài học tập trung vào **task tùy chỉnh**, áp dụng cho `build.gradle.kts` và các task type Kotlin/Java, với ví dụ Kotlin DSL đầy đủ. Bạn cần có Gradle Wrapper tương thích với phiên bản Gradle đang dùng. Nếu build script chạy bằng Kotlin DSL, các annotation trên Gradle managed properties thường đặt ở **getter** với tiền tố `@get:`.

## 2. Task lifecycle và cơ chế dữ liệu được theo dõi

Gradle thường tiến hành initialization → configuration → execution. Ở configuration, plugin và build script tạo mô hình task, kết nối `Property<T>`, `Provider<T>`, file input/output và dependency; ở execution, Gradle xác định task nào cần action và chạy khi cần.

~~~text
Custom Task
├── Tracked inputs
│   ├── @Input / @InputFile / @InputFiles / @InputDirectory
│   ├── @Classpath / @CompileClasspath / @Nested ...
│   └── @Optional + một annotation input hợp lệ
├── Outputs
│   ├── @OutputFile / @OutputDirectory ...
│   └── @Optional + output annotation (khi thật sự tùy chọn)
├── Not tracked
│   └── @Internal: metadata không được xét cho fingerprint
└── @TaskAction: thực thi nếu task không bị bỏ qua
~~~

Nếu task từng chạy với cùng input và các output cần thiết vẫn hợp lệ, Gradle có thể dùng **`UP-TO-DATE`** để không chạy action. Nếu có Build Cache phù hợp và task đủ điều kiện cache, Gradle có thể sử dụng output cache với trạng thái **`FROM-CACHE`**. Ngược lại, nếu một input quan trọng không được khai báo, Gradle có thể **bỏ qua sai** và để lại output cũ.

Hai khái niệm khác nhau:

- **Up-to-date checking**: Gradle so sánh dấu vân tay inputs/outputs của task hiện tại với trạng thái đã biết, nhằm tránh chạy lại khi không cần.
- **Build Cache**: Gradle có thể lưu/khôi phục output dựa trên input và implementation của task đủ điều kiện. `@CacheableTask` cho phép opt-in cho custom task nhưng **không tự khiến một task sai mô hình trở nên đúng**.

Các annotation như `@Internal` và `@Optional` là một phần **hợp đồng dữ liệu**; chúng không trực tiếp tạo file, không chạy mã task, không thay thế dependency giữa các task.

## 3. `@Internal`: không theo dõi, không kiểm tra bắt buộc có giá trị

Gradle API quy định `@Internal` gắn trên getter của task property và cho biết property **không được xét cho up-to-date checking**. Nếu chỉ thay property internal, Gradle không có lý do từ property đó để chạy task lại. Việc `@Internal` ngầm được coi là optional **không đồng nghĩa** với `@Optional` ở một input đã được theo dõi.

Những trường hợp thường phù hợp:

- Nhãn log, thông tin hiển thị tiến độ, chú thích chẩn đoán **không được viết vào output** và không thay đổi các tác động cần quản lý.
- Một getter **dẫn xuất** hoàn toàn từ các property `@Input` khác đã được theo dõi đầy đủ; nếu tiếp tục đánh dấu như input, bạn có thể đếm dữ liệu hai lần.
- Metadata dùng để tổ chức cấu hình nội bộ nhưng không quyết định cách sinh artifact.
- Dữ liệu hỗ trợ không phải input/output và không cần Gradle validation presence; cân nhắc các annotation chuyên biệt như `@Console` hay `@LocalState` nếu phù hợp hơn.

**Không dùng `@Internal` để che input thực:** tên package, template file, language level, cờ bật/tắt tính năng, phiên bản schema, đường dẫn ảnh hưởng artifact, cấu hình serialization hoặc metadata được nhúng vào file đều phải được mô hình hóa bằng input/output thích hợp.

Ví dụ anti-pattern:

~~~kotlin
abstract class WrongGenerate : DefaultTask() {
    // Sai: mode làm khác nội dung file nhưng bị giấu khỏi tracking.
    @get:Internal
    abstract val mode: Property<String>

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val file = outputFile.get().asFile
        file.parentFile.mkdirs()
        file.writeText("mode=" + mode.get(), Charsets.UTF_8)
    }
}
~~~

Đây là **đoạn minh họa sai mô hình** (cần import type/annotation để biên dịch), không phải hướng dẫn nên dùng. Nếu `mode` đổi nhưng output cũ còn nguyên, Gradle có thể coi task là `UP-TO-DATE`. Sửa bằng `@get:Input` cho `mode`. Đừng bật `--rerun-tasks` để che lỗi: ép chạy chỉ giải quyết một lần, không sửa cách Gradle nhận biết input.

### Bí mật và dịch vụ bên ngoài

Một secret có thể nhạy cảm nhưng **không vì vậy tự động là `@Internal`**. Nếu secret thực sự ảnh hưởng output, bỏ qua nó làm hỏng cache key. Nếu task gửi HTTP, publish artifact, cập nhật database hay gửi email, đây có thể là side effect không phù hợp với Build Cache; thiết kế task/credentials và khả năng cache cần đánh giá riêng. Không dùng `@Internal` cho mọi token để tuyên bố build deterministic. Với task có side effect bên ngoài, xem `@DisableCachingByDefault`, API credentials của Gradle và quy định an toàn của dự án.

## 4. `@Optional`: được vắng mặt, nhưng giá trị vẫn có ý nghĩa

`@Optional` là modifier annotation: chỉ có `@Optional` mà không có annotation input/output tương ứng là **validation error**. Nó có thể đi với `@Input`, `@InputFile`, `@InputDirectory`, `@InputFiles`, `@Nested` hoặc các annotation output được hỗ trợ, tùy Gradle API.

~~~kotlin
@get:Input
@get:Optional
abstract val header: Property<String>

@get:InputFile
@get:Optional
@get:PathSensitive(PathSensitivity.NONE)
abstract val templateFile: RegularFileProperty
~~~

Hai khai báo trên là **mảnh class** cần được đặt trong một custom task có import phù hợp; không phải file đầy đủ. Trong trường hợp đầu:

- `header` **unset/absent** là hợp lệ.
- Khi `header` present, giá trị là tracked input. Đổi từ absent → present, present → absent hoặc đổi nội dung có thể khiến output cần tạo lại.
- `header.get()` **không trở nên an toàn** khi property absent. Nếu không set, `get()` có thể ném lỗi; dùng `orNull`/`getOrElse(...)` hoặc kiểm tra `isPresent` trong action.

Trong trường hợp file input:

- `templateFile` absent là hợp lệ.
- Nếu có provider trỏ tới một **file tồn tại**, Gradle theo dõi nội dung/path theo normalization.
- Nếu người dùng đã cung cấp đường dẫn nhưng file **không tồn tại**, `@Optional` không có nghĩa Gradle bỏ qua validation. Đừng đồng nhất “property absent” với “file path được set nhưng file không tồn tại”.

`@Optional` không có nghĩa task sẽ tự động **SKIPPED** khi thiếu input. Nó chỉ điều chỉnh việc property có bắt buộc phải được cung cấp không. Nếu muốn bỏ task khi tập source file rỗng, xem `@SkipWhenEmpty` với annotation file input tương ứng. Nếu muốn task vẫn chạy và tạo output mặc định, chính `@TaskAction` phải xử lý trạng thái absent.

### Bảng so sánh nhanh

| Annotation | Tracked khi có giá trị? | Chấp nhận absent? | Tác dụng chính |
| --- | --- | --- | --- |
| `@Input` | Có | Không mặc định | Theo dõi giá trị như String/Boolean/Number. |
| `@Input` + `@Optional` | Có | Có | Một giá trị input có thể unset. |
| `@InputFile` + `@PathSensitive` | Có | Không mặc định | Theo dõi file bắt buộc. |
| `@InputFile` + `@Optional` + `@PathSensitive` | Có | Có, nếu property unset | File input tùy chọn vẫn được theo dõi khi present. |
| `@OutputFile` | Quản lý output | Không mặc định | Task tạo một file output. |
| `@OutputFile` + `@Optional` | Quản lý output khi được khai báo | Có | Output chỉ tạo trong một số trường hợp hợp lệ. |
| `@Internal` | **Không** | Mặc nhiên không bị yêu cầu presence | Không phải input/output được Gradle theo dõi. |
| `@Internal` + `@Optional` | **Sai** | Không áp dụng | Validation error, không dùng. |

## 5. Ví dụ hoàn chỉnh: một task gồm cả ba loại property

Tạo project Gradle có Wrapper. `settings.gradle.kts`:

~~~kotlin
rootProject.name = "tracking-lab"
~~~

Toàn bộ `build.gradle.kts` độc lập:

~~~kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.Internal
import org.gradle.api.tasks.Optional
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction

@CacheableTask
abstract class GenerateGreeting : DefaultTask() {

    // Input bắt buộc, luôn ảnh hưởng nội dung.
    @get:Input
    abstract val recipientName: Property<String>

    // Input tùy chọn: absent hợp lệ, present được theo dõi.
    @get:Input
    @get:Optional
    abstract val salutation: Property<String>

    // Chỉ đổi log của action, không đổi output file.
    @get:Internal
    abstract val diagnosticTag: Property<String>

    // Artifact do task sở hữu.
    @get:OutputFile
    abstract val reportFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val name = recipientName.get()
        val prefix = salutation.orNull
        val message = if (prefix == null) {
            "Xin chào, " + name + "!"
        } else {
            "Xin chào, " + prefix + " " + name + "!"
        }

        val file = reportFile.get().asFile
        file.parentFile.mkdirs()
        file.writeText(message + "\n", Charsets.UTF_8)

        logger.lifecycle(
            "Generated " + file.name +
                " [diagnostic=" + diagnosticTag.get() + "]"
        )
    }
}

tasks.register<GenerateGreeting>("generateGreeting") {
    recipientName.set(
        providers.gradleProperty("recipient").orElse("An")
    )

    // Khi không có -Psalutation, provider vẫn absent.
    salutation.set(providers.gradleProperty("salutation"))

    diagnosticTag.convention(
        providers.gradleProperty("diagnosticTag").orElse("local")
    )

    reportFile.set(layout.buildDirectory.file("generated/greeting.txt"))
}
~~~

**Giải thích thiết kế:**

1. `recipientName` là input cần để tạo output; `@Input` bảo đảm thay đổi tên sẽ được theo dõi. `orElse("An")` cung cấp default nên nó không absent.
2. `salutation` không có default: absence là một trạng thái có ý nghĩa. Khi user truyền `-Psalutation=Anh` thì output thay đổi; annotation `@Optional + @Input` giúp theo dõi đúng cả trạng thái absent/present.
3. `diagnosticTag` chỉ được dùng cho `logger.lifecycle`, không chèn vào file. Có thể `@Internal`. Nếu task `UP-TO-DATE`, action không chạy và log “Generated ...” cũng không xuất hiện; đó là hành vi hợp lý.
4. `reportFile` là `@OutputFile`, nên Gradle biết file được tạo. Action ghi file ở execution, không ghi ở configuration.
5. `@CacheableTask` cho phép cache với điều kiện input/output và logic deterministic. Nó không tự xác nhận rằng một annotation `@Internal` là đúng; trách nhiệm đó thuộc tác giả task.
6. `Provider` từ `providers.gradleProperty(...)` được nối vào các Gradle managed properties; không cần đọc bằng `get()` ở configuration. Action chỉ đọc giá trị task khi execution.

### Thực hành thay đổi từng property

~~~bash
# Lần đầu: output từ input mặc định
./gradlew generateGreeting --no-build-cache --console=plain

# Không đổi input và output
./gradlew generateGreeting --no-build-cache --console=plain

# Chỉ đổi diagnosticTag
./gradlew generateGreeting -PdiagnosticTag=ci --no-build-cache --console=plain

# Đổi input bắt buộc
./gradlew generateGreeting -Precipient=Binh --no-build-cache --console=plain

# Cung cấp input tùy chọn
./gradlew generateGreeting -Precipient=Binh -Psalutation=Anh --no-build-cache --console=plain

# Bỏ input tùy chọn
./gradlew generateGreeting -Precipient=Binh --no-build-cache --console=plain
~~~

Nội dung `build/generated/greeting.txt` (mỗi trường hợp kèm một newline):

| Trường hợp | Nội dung file |
| --- | --- |
| Mặc định | `Xin chào, An!` |
| Chỉ đổi `-PdiagnosticTag=ci` | Vẫn là `Xin chào, An!`; action có thể bị bỏ qua. |
| `-Precipient=Binh` | `Xin chào, Binh!` |
| `-Precipient=Binh -Psalutation=Anh` | `Xin chào, Anh Binh!` |
| `-Precipient=Binh` (bỏ `salutation` lần nữa) | `Xin chào, Binh!` |

Lần không đổi input thường hiển thị `UP-TO-DATE` khi output còn đúng. Đổi `diagnosticTag` không đổi fingerprint nên cũng có thể `UP-TO-DATE`. Đổi `recipient` hoặc `salutation` khiến input khác, task cần tạo output mới hoặc dùng một entry Build Cache phù hợp khi bật cache. Không kỳ vọng có stdout chính xác ngoài action vì Gradle version, log và cache status khác nhau.

**Thí nghiệm quan trọng:** nếu sửa action để viết thêm `diagnosticTag.get()` vào **nội dung file** nhưng vẫn giữ `@Internal`, hành vi up-to-date có thể sai. Khi đó đổi annotation của tag thành `@Input` hoặc sửa action để tag chỉ phục vụ log. Cách xác nhận đúng là quan sát **nội dung artifact**, không chỉ build báo `BUILD SUCCESSFUL`.

## 6. Ví dụ hoàn chỉnh: `@Optional @InputFile` và lỗi nhầm absent với missing file

Đây là **ví dụ `build.gradle.kts` thay thế độc lập** cho mục 5 (không dán hai ví dụ vào một file với các import không đúng vị trí). Task đọc template file nếu người dùng cung cấp, ngược lại tạo văn bản mặc định.

~~~kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.Optional
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

@CacheableTask
abstract class GenerateBanner : DefaultTask() {

    @get:InputFile
    @get:Optional
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val templateFile: RegularFileProperty

    @get:OutputFile
    abstract val bannerFile: RegularFileProperty

    @TaskAction
    fun write() {
        val input = templateFile.orNull?.asFile
        val banner = if (input == null) {
            "DEFAULT BANNER"
        } else {
            input.readText(Charsets.UTF_8).trimEnd()
        }

        val target = bannerFile.get().asFile
        target.parentFile.mkdirs()
        target.writeText(banner + "\n", Charsets.UTF_8)
    }
}

tasks.register<GenerateBanner>("generateBanner") {
    templateFile.set(
        providers.gradleProperty("templatePath").map {
            layout.projectDirectory.file(it)
        }
    )
    bannerFile.set(layout.buildDirectory.file("generated/banner.txt"))
}
~~~

Chạy:

~~~bash
# Không truyền templatePath: property absent, task hợp lệ
./gradlew generateBanner --no-build-cache

# Tạo input file trên Linux/macOS
printf 'HELLO TEAM\n' > banner-source.txt

# Dùng file input, nội dung được theo dõi
./gradlew generateBanner -PtemplatePath=banner-source.txt --no-build-cache

# Nếu sửa nội dung banner-source.txt, chạy lại sẽ cần xét input mới
./gradlew generateBanner -PtemplatePath=banner-source.txt --no-build-cache
~~~

Trên Windows PowerShell, dùng:

~~~powershell
Set-Content -LiteralPath banner-source.txt -Value "HELLO TEAM"
.\gradlew.bat generateBanner -PtemplatePath=banner-source.txt --no-build-cache
~~~

Nếu không truyền `templatePath`, `build/generated/banner.txt` chứa `DEFAULT BANNER` và newline. Nếu có `banner-source.txt` chứa `HELLO TEAM`, output chứa `HELLO TEAM` và newline. Sửa nội dung file input sẽ thay fingerprint và task cần cập nhật artifact.

Nếu truyền:

~~~bash
./gradlew generateBanner -PtemplatePath=khong-co.txt
~~~

thì `templateFile` **đã có giá trị là một đường dẫn**, nhưng file không tồn tại. Gradle có thể báo lỗi validation input file. `@Optional` chỉ cho phép **property không được set**, không cho phép đường dẫn đã set nhưng sai trở thành input hợp lệ. Không nên âm thầm coi mọi đường dẫn sai là “không có template”, vì điều đó che lỗi cấu hình thật.

### Vai trò của `@PathSensitive`

Trong ví dụ, task chỉ dùng **nội dung** template; không ghi tên file/path vào output. Vì vậy `@PathSensitive(PathSensitivity.NONE)` là phù hợp: thay vị trí file nhưng giữ cùng nội dung có thể không đổi fingerprint của input này. Nếu task ghi tên/path vào báo cáo, phải chọn normalization theo phần đường dẫn thực sự ảnh hưởng output. Với input directory, `PathSensitivity.RELATIVE` thường đúng hơn để giữ cấu trúc đường dẫn tương đối nhưng tránh phụ thuộc đường dẫn gốc khác nhau giữa máy.

## 7. Dữ liệu nào cần tracking, dữ liệu nào không?

Áp dụng câu hỏi thực hành:

> Khi chỉ thay **một property**, giữ mọi thứ khác giống nhau, **artifact hoặc kết quả có thể thay đổi không?**

Nếu có, bạn phải theo dõi nó theo loại dữ liệu thích hợp (hoặc thông qua một input khác đã biểu diễn đầy đủ). Nếu không và nó chỉ phục vụ log/metadata nội bộ, `@Internal` có thể phù hợp.

| Dữ liệu task sử dụng | Có cần theo dõi? | Cách mô hình hóa |
| --- | --- | --- |
| Tên class/package được sinh | Có | `@Input Property<String>`. |
| Chế độ debug làm file có thêm thông tin | Có | `@Input Property<Boolean>`. |
| Cờ chỉ thay đổi dòng log khi action chạy | Không nhất thiết | `@Internal`, nếu không thay output. |
| Text tùy chọn được nối vào báo cáo | Có nếu present | `@Input @Optional Property<String>`. |
| File cấu hình JSON được parse để sinh mã | Có | `@InputFile` + normalization; `@Optional` chỉ khi nghiệp vụ cho phép thiếu. |
| Thư mục source resources | Có | `@InputDirectory` + `@PathSensitive`. |
| Danh sách source/template files | Có | `@InputFiles` + normalization. |
| Java compile classpath | Có | `@Classpath` hoặc `@CompileClasspath` tùy ý nghĩa. |
| File/dir task tạo | Khai báo output | `@OutputFile` / `@OutputDirectory`. |
| Getter chỉ dẫn xuất từ hai tracked inputs khác | Có thể không cần theo dõi thêm | `@Internal` nếu mọi nguồn ảnh hưởng đã được tracked. |
| Task output của producer được consumer dùng | Có, cùng dependency | Nối output `Provider` của producer vào `@InputFile` của consumer. |
| Biến môi trường ảnh hưởng file sinh ra | Có | Nối `providers.environmentVariable(...)` vào `@Input`. |
| Token gọi dịch vụ ngoài, task ghi trạng thái server | Cần thiết kế riêng | Xem tính cacheable và quản lý credentials; không bỏ qua side effect bằng `@Internal`. |

**Nguồn gián tiếp vẫn là input.** Nếu task đọc file trực tiếp bằng `File.readText()` trong action mà không khai báo input, Gradle không tự suy ra nó phải so sánh nội dung. Nếu task gọi network API trong action và response thay đổi output mà không được khai báo/ổn định hóa, Build Cache có thể đưa artifact không đúng. Phải làm dữ liệu đầu vào đủ rõ hoặc không cache task khi không thể bảo đảm tính tái tạo.

### Getter dẫn xuất

Giả sử có `firstName` và `lastName` đã `@Input`. Getter `fullName` chỉ nối hai giá trị và được dùng trong action; nếu nó **hoàn toàn** phụ thuộc hai input được theo dõi, có thể `@Internal` vì không đưa thêm thông tin độc lập. Nhưng nếu getter đó còn đọc file cấu hình bên ngoài hoặc biến môi trường chưa được khai báo, `@Internal` sẽ giấu một input thật. “Đã được tính từ input khác” chỉ là lý do hợp lệ khi sự phụ thuộc **đầy đủ và xác định**.

## 8. File inputs, normalization và độ tin cậy của Build Cache

Với file input, annotation không chỉ cho Gradle biết **file nào**, mà còn phải xác định **phần đường dẫn nào có ý nghĩa**.

~~~kotlin
@get:InputFile
@get:PathSensitive(PathSensitivity.NONE)
abstract val template: RegularFileProperty

@get:InputDirectory
@get:PathSensitive(PathSensitivity.RELATIVE)
abstract val assets: DirectoryProperty
~~~

Các dòng trên là **mảnh khai báo**, cần import type/annotation thích hợp trong task class.

- `PathSensitivity.NONE`: phù hợp khi task quan tâm **chỉ nội dung một file**, không quan tâm vị trí/tên của nó.
- `PathSensitivity.RELATIVE`: phù hợp với thư mục có cấu trúc tương đối quan trọng nhưng không muốn đường dẫn tuyệt đối của project ảnh hưởng cache key.
- `PathSensitivity.NAME_ONLY`: chỉ xét tên file (và nội dung), hợp lý trong một số trường hợp hiếm hơn.
- `PathSensitivity.ABSOLUTE`: xét cả đường dẫn tuyệt đối; có thể làm giảm khả năng tái sử dụng Build Cache giữa máy/thư mục khác nhau.

Dùng `@Classpath` hoặc `@CompileClasspath` khi input thực sự là Java classpath; chúng có quy tắc normalization riêng. Với input text mà hai kiểu newline Windows/Unix không thay đổi kết quả, có thể xem `@NormalizeLineEndings` với những file input type được hỗ trợ. **Không normalize quá mức**: nếu action ghi chính xác tên file hoặc newline vào output, các phần ấy là input cần được tính.

Task `@CacheableTask` không tự bảo đảm cache an toàn. Cần input/output đầy đủ, logic deterministic, không ghi side effect ngoài output khai báo, và phù hợp với môi trường build. Với task deploy/publish gửi dữ liệu ra bên ngoài, thường không nên cache theo cách của task sinh file.

## 9. `@Nested`, `@SkipWhenEmpty` và các annotation dễ nhầm

### `@Nested`: một object chứa các input khác

Khi cấu hình task là object gồm nhiều thuộc tính, có thể dùng `@Nested`. Gradle đi vào các getter của object con và phân tích annotation của chúng.

~~~kotlin
// Phác thảo class: cần các imports và task action khi sử dụng thực tế.
abstract class ReportOptions {
    @get:Input
    abstract val strict: Property<Boolean>

    @get:Input
    @get:Optional
    abstract val profile: Property<String>

    @get:Internal
    abstract val displayLabel: Property<String>
}

abstract class ReportTask : DefaultTask() {
    @get:Nested
    abstract val options: ReportOptions

    @get:OutputFile
    abstract val reportFile: RegularFileProperty
}
~~~

`@Nested` không có nghĩa mọi field tự được theo dõi. Phải annotate từng getter bên trong đúng theo nghĩa input/metadata. Nếu nested bean thật sự có thể vắng mặt, `@Optional + @Nested` là một khả năng được Gradle hỗ trợ; tránh đánh dấu cả bean `@Internal` nếu trong đó có input nghiệp vụ.

### `@SkipWhenEmpty` khác `@Optional`

Giả sử task xử lý một tập file đầu vào. Khi không có file nào, bạn có thể muốn **skip task** thay vì chạy action với danh sách rỗng. Gradle cung cấp `@SkipWhenEmpty` cho một số loại file input. `@Optional` chỉ cho biết property có thể absent, **không tự yêu cầu task skip**. Đừng dùng hai annotation thay thế cho nhau.

### `@LocalState` khác output

Tệp cache cục bộ tạm dùng trong task không phải artifact để downstream sử dụng. `@LocalState` mô tả local state có lifecycle riêng, không phải `@OutputFile` cacheable thông thường. Đánh dấu output thật là local state có thể làm Gradle không khôi phục đúng artifact khi dùng Build Cache.

### `@Console` và `@Internal`

Với cấu hình chỉ thay đổi cách in ra console, Gradle có `@Console` trong bộ annotation task. Nó diễn tả semantics chuyên biệt hơn trong một số trường hợp. Nhưng với property thật sự ảnh hưởng file output, phải chọn `@Input`; không lấy lý do “chỉ dùng ở UI” khi hành vi action đã thay đổi artifact.

## 10. Producer–consumer: khai báo dependency chưa đủ nếu không theo dõi file

Giả sử task A sinh `schema.json`, task B đọc file đó và sinh Java source. Chỉ viết `B.dependsOn(A)` xác định **thứ tự chạy**; nếu B không khai báo `schema.json` là input, Gradle vẫn không biết B cần chạy lại khi nội dung schema thay đổi.

Mô hình đúng:

1. Task A khai báo `@OutputFile RegularFileProperty` cho `schema.json`.
2. Task B khai báo `@InputFile RegularFileProperty` (kèm normalization) cho schema.
3. Nối property input của B với output provider của A. Gradle có thể mang theo thông tin task dependency qua provider và chọn thứ tự hợp lý.
4. Nếu cơ chế dùng provider không truyền đủ dependency information, thêm `dependsOn` tường minh; nhưng **không thay thế** annotation input.
5. Task B chỉ đọc schema khi `@TaskAction` chạy, sau khi Gradle giải quyết producer, validate input và xác định trạng thái task.

Tương tự, một file output có ý nghĩa cho downstream không thể gắn `@Internal` chỉ vì đó là “file nội bộ của team”. **Internal trong Gradle là “không tracked”**, không phải “không public”. Để build chạy song song an toàn, tránh nhiều task tự ý ghi cùng đường dẫn nếu không khai báo ownership/điều phối thích hợp.

## 11. Chẩn đoán và kiểm thử task tracking

Trên bản mã `GenerateGreeting` ở mục 5:

~~~bash
# Chạy lần đầu để tạo artifact
./gradlew generateGreeting --no-build-cache --console=plain

# Không đổi input: kiểm tra trạng thái
./gradlew generateGreeting --no-build-cache --info --console=plain

# Chỉ đổi internal: thường không cần tạo lại file
./gradlew generateGreeting -PdiagnosticTag=ci --no-build-cache --console=plain

# Đổi tracked input: phải phản ánh vào file
./gradlew generateGreeting -Precipient=Binh --no-build-cache --console=plain

# Đổi optional absent -> present
./gradlew generateGreeting -Precipient=Binh -Psalutation=Anh --no-build-cache --console=plain

# Ép task action chạy để so sánh hành vi
./gradlew generateGreeting -Precipient=Binh -Psalutation=Anh --rerun-tasks --console=plain
~~~

Cách quan sát:

- Xem status `UP-TO-DATE`/`FROM-CACHE`/`SKIPPED` trong log. Khi `UP-TO-DATE`, `@TaskAction` không chạy, nên dòng `Generated ...` của ví dụ không xuất hiện.
- Xem **nội dung thực** của `build/generated/greeting.txt` sau mỗi lệnh, không dựa vào log “BUILD SUCCESSFUL” để kết luận.
- Dùng `--info` để biết vì sao Gradle xét task đã cũ: input thay đổi, output không tồn tại hoặc nguyên nhân khác.
- Dùng `--no-build-cache` khi muốn phân biệt logic up-to-date với việc restore output từ Build Cache; `--build-cache` khi kiểm tra tái sử dụng cache. `--rerun-tasks` phục vụ việc buộc chạy lại để so sánh output, không phải giải pháp khi input annotation sai.
- Với Configuration Cache, tập trung bảo đảm task action không truy cập Project model ở execution; typed properties giúp làm việc này. **Configuration Cache và Build Cache khác nhau**: một cái lưu kết quả cấu hình, một cái lưu output task.
- Khi cần kiểm thử cache giữa các máy, copy project sang path khác, kiểm tra tính relocatable của input paths và so sánh artifact, không chỉ một dòng `FROM-CACHE`.

### Cách review một property

Đặt ba câu hỏi:

1. Nếu thay giá trị property, artifact có thể đổi không? **Có → tracked input**.
2. Nếu property **vắng mặt**, task có hành vi hợp lệ không? **Có → `@Optional` + annotation chính** (hoặc thiết lập convention/default khi có giá trị mặc định).
3. Nếu property chỉ hỗ trợ log hoặc là dẫn xuất đã theo dõi, liệu Gradle cần nó trong fingerprint không? **Không → `@Internal` có thể hợp lý**.

Sau đó kiểm tra xem action có đọc thêm file/biến môi trường/network ngoài những gì task model khai báo không.

## 12. Các lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Task bị `UP-TO-DATE` dù template đổi | File không được tracked, bị `@Internal` hoặc action tự đọc file ngoài input. | `@InputFile`/`@InputFiles` và normalization đúng, test khi sửa file. |
| Thay nhãn log khiến task chạy lại | Nhãn được đánh dấu `@Input` dù không ảnh hưởng output. | Cân nhắc `@Internal` nếu action không đưa nhãn vào artifact. |
| `@Optional` đã dùng mà vẫn báo missing input file | Property có path được set nhưng file không tồn tại. | Phân biệt provider absent với file path sai; nếu optional, chỉ set khi thật sự có input hợp lệ. |
| `@Optional` dùng một mình báo validation error | Thiếu annotation input/output chính. | Kết hợp với `@Input`, `@InputFile`, `@Nested` hoặc annotation được hỗ trợ. |
| `@Internal` + `@Optional` báo validation error | Hai annotation trái semantics. | Với untracked property chỉ dùng `@Internal`; với tracked optional input dùng `@Input + @Optional`. |
| `optionalInput.get()` ném exception | Task action chưa xử lý absent. | `orNull`/`getOrElse` hoặc `isPresent` trước khi đọc. |
| `@Input` gắn trên `File` khiến Gradle báo unsupported type | Input file cần file annotation. | Chọn `@InputFile`/`@InputFiles`/`@InputDirectory`, không cố ép đường dẫn thành string để né kiểm tra. |
| Thiếu input path normalization | File input annotation không phản ánh path sensitivity. | Dùng `@PathSensitive`, `@Classpath` hoặc API normalization phù hợp. |
| Task luôn chạy dù inputs không đổi | Output chưa khai báo, output bị thay, input biến động hoặc task không hỗ trợ up-to-date như dự kiến. | Khai báo output, dùng `--info` và kiểm tra mtime/nội dung. |
| Build Cache trả artifact không đúng | Input quan trọng đã bị `@Internal` hoặc bỏ quên. | Truy dấu mọi dữ liệu action đọc, khai báo tracked input đầy đủ, test khi đổi từng input. |
| Task B không chạy lại dù A đã tạo file mới | B thiếu tracked input hoặc không nối đúng provider. | `@InputFile` cho consumer, `@OutputFile` cho producer, liên kết qua provider và dependency. |
| Chạy cache giữa máy không tận dụng lại được | Input file tính đường dẫn tuyệt đối không cần thiết. | Dùng `PathSensitivity.NONE`/`RELATIVE` phù hợp với thuật toán task. |
| Chỉ khai báo `@Input` mà không có output, kỳ vọng `UP-TO-DATE` | Gradle thiếu artifact cần kiểm tra hoặc task có side effect. | Khai báo output thực nếu có; nếu chỉ side effect, thiết kế task không cache theo đúng nghiệp vụ. |

## 13. Checklist triển khai

- [ ] Mọi property mà thay đổi có thể khiến output thay đổi được mô tả như input.
- [ ] Mọi file/thư mục tạo ra được khai báo như output.
- [ ] `@Internal` chỉ dùng cho property không ảnh hưởng output; không dùng để giấu lỗi validation.
- [ ] `@Optional` chỉ dùng khi absence là hợp lệ và luôn kết hợp annotation được hỗ trợ.
- [ ] Không có property nào gắn cả `@Internal` và `@Optional`.
- [ ] Task action xử lý absent, không gọi `get()` vô điều kiện trên optional input.
- [ ] Không xem file path đã set nhưng file không tồn tại là một optional property hợp lệ.
- [ ] File input có path normalization đúng semantics (NONE/RELATIVE hoặc loại chuyên dụng).
- [ ] Input/output của các task producer–consumer được nối bằng providers/dependencies đúng.
- [ ] Không có file, biến môi trường, network response ảnh hưởng output mà nằm ngoài task model.
- [ ] Task được kiểm tra với input không đổi, tracked input thay đổi, internal-only thay đổi và optional absent/present.
- [ ] Với task cacheable, kiểm tra output thực tế và tính tái tạo, không chỉ các dòng status.

## 14. Câu hỏi tự kiểm tra

1. **`@Internal` làm gì?** Loại property khỏi up-to-date checking, không yêu cầu presence. Nó không tương đương input tùy chọn đã được theo dõi.
2. **`@Optional` có khiến Gradle bỏ qua thay đổi của property không?** Không. Khi present, giá trị/đường dẫn vẫn được xử lý theo annotation input/output.
3. **Gắn `@Optional` một mình có hợp lệ?** Không. Nó là modifier phải dùng cùng annotation hỗ trợ.
4. **Có thể kết hợp `@Internal` và `@Optional` không?** Không; đây là lỗi validation.
5. **Một `@Optional @InputFile` trỏ tới file không tồn tại có tự động hợp lệ không?** Không. Một property đã present với file path invalid khác một property absent.
6. **Task dùng nhãn log không thay output, có thể `@Internal` không?** Có, miễn là action không dùng nhãn ấy để tạo artifact hoặc hành vi cần theo dõi.
7. **Task dùng nội dung YAML để sinh code, gắn YAML input là `@Internal` có đúng không?** Sai. Phải khai báo file input và normalization.
8. **Vì sao cần `@PathSensitive`?** Để Gradle fingerprint phần đường dẫn thực sự có ý nghĩa, tăng tính đúng và khả năng tái sử dụng cache.
9. **`@CacheableTask` có sửa một task thiếu input không?** Không. Nó chỉ cho phép dùng Build Cache trong điều kiện thích hợp.
10. **Nếu task chỉ có `@Input` nhưng không có output thực, có chắc `UP-TO-DATE` ở lần sau?** Không. Không có output để quản lý, task action thường vẫn phải chạy nếu được yêu cầu.
11. **`dependsOn` đã đủ cho dữ liệu producer–consumer?** Chưa. Consumer còn cần khai báo file đọc như tracked input, nếu không up-to-date checking có thể sai.
12. **`@SkipWhenEmpty` và `@Optional` có cùng nghĩa không?** Không. Một cái có thể skip khi tập file trống, cái kia cho phép property vắng mặt.

## Tài liệu chính thức

- [Gradle: Implementing Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html) — task inputs/outputs, `@TaskAction`, annotation và cơ chế lazy properties.
- [Gradle: Incremental Build](https://docs.gradle.org/current/userguide/incremental_builds.html) — up-to-date checking, input tracking, validation, incremental execution.
- [Gradle: Build Cache](https://docs.gradle.org/current/userguide/build_cache.html) — cache keys, cacheable tasks, normalization và giới hạn khi dùng cache.
- [Gradle Javadoc: `@Internal`](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/Internal.html) — ý nghĩa không theo dõi, presence và không kết hợp `@Optional`.
- [Gradle Kotlin DSL: `@Optional`](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.api.tasks/-optional/index.html) — modifier annotation, danh sách annotation kết hợp và validation.
- [Gradle: Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html) — path sensitivity và thiết kế task có cache hiệu quả.

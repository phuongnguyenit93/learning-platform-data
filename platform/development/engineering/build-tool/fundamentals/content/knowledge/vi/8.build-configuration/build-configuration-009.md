# Tránh tác dụng phụ và công việc nặng trong giai đoạn cấu hình

Một lần chạy Gradle trải qua các giai đoạn khác nhau trước khi task action thực sự được thực thi. Trong giai đoạn cấu hình (configuration phase), Gradle đọc settings và build script, áp dụng plugin, tạo mô hình project, đăng ký và cấu hình task, rồi xác định task graph cho yêu cầu hiện tại. Sau đó, ở giai đoạn thực thi (execution phase), Gradle mới chạy action của những task được chọn.

Nếu build script thực hiện tải dữ liệu, quét hàng nghìn tệp, chạy tiến trình bên ngoài hoặc ghi tệp ngay trong lúc cấu hình, những công việc đó có thể xảy ra ngay cả khi task liên quan không được yêu cầu. Điều này làm build chậm, tạo ra thay đổi khó dự đoán và cản trở việc sử dụng configuration cache.

Nguyên tắc quan trọng là: **giai đoạn cấu hình dùng để mô tả công việc; task action dùng để thực hiện công việc**. Hãy giữ cấu hình nhẹ, khai báo đầu vào và đầu ra rõ ràng, sử dụng API lazy của Gradle, rồi chuyển các thao tác tốn thời gian hoặc có tác dụng phụ vào task phù hợp.

## 1. Phân biệt các giai đoạn của một lần chạy Gradle

Một lần chạy Gradle thường có ba giai đoạn chính:

1. **Initialization**: Gradle đọc settings, xác định root project, các subproject và included build cần tham gia.
2. **Configuration**: Gradle đánh giá build script, áp dụng plugin, tạo và cấu hình mô hình task, rồi xác định graph cho các task được yêu cầu.
3. **Execution**: Gradle thực thi các task action trong graph theo quan hệ phụ thuộc và thứ tự hợp lệ.

Có thể hình dung luồng xử lý như sau:

~~~text
Lệnh ./gradlew build
        |
        v
Initialization
  - Đọc settings.gradle(.kts)
  - Xác định các project
        |
        v
Configuration
  - Đánh giá build.gradle(.kts)
  - Áp dụng plugin
  - Đăng ký và cấu hình task
  - Tạo task graph
        |
        v
Execution
  - Kiểm tra đầu vào/đầu ra
  - Chạy task action cần thiết
  - Ghi kết quả build
~~~

Build script được đánh giá trong giai đoạn cấu hình. Vì thế, một câu lệnh Kotlin hoặc Groovy đặt trực tiếp ở cấp cao nhất của build script có thể chạy mỗi lần Gradle cần cấu hình build, kể cả khi task mà người viết định phục vụ không nằm trong task graph.

Ví dụ:

~~~kotlin
println("Configuring project")

tasks.register("hello") {
    doLast {
        println("Executing hello")
    }
}
~~~

Khi chạy một task khác trong project, dòng **Configuring project** vẫn có thể xuất hiện vì nó nằm ở cấp cấu hình. Dòng **Executing hello** chỉ xuất hiện khi task **hello** được chọn và action của nó được thực thi.

Cần phân biệt việc Gradle tạo hoặc cấu hình một task với việc task đó thực hiện công việc. Đăng ký task trong configuration là bình thường; chạy chương trình, tải tệp hoặc ghi kết quả trong configuration mới là điều cần tránh.

## 2. Tác dụng phụ trong giai đoạn cấu hình là gì?

Tác dụng phụ (side effect) là thay đổi hoặc hoạt động bên ngoài mô hình cấu hình mà build script tạo ra. Một số ví dụ:

- Ghi, xóa, đổi tên hoặc sửa tệp trong source tree.
- Gọi HTTP API, truy vấn cơ sở dữ liệu hoặc tải metadata từ máy chủ.
- Khởi chạy chương trình bên ngoài, gọi shell hoặc thực hiện lệnh hệ điều hành.
- Quét một cây thư mục lớn rồi đọc toàn bộ nội dung tệp.
- Tạo kết nối mạng, mở socket, khởi động thread hoặc giữ tài nguyên lâu dài.
- Thay đổi biến môi trường, thuộc tính hệ thống hoặc trạng thái dùng chung giữa các project.
- Thực hiện phép tính nặng hoặc phân tích dữ liệu lớn dù task liên quan chưa được yêu cầu.

Không phải mọi thao tác đọc đều có hại. Đọc một thuộc tính Gradle hoặc tạo một Provider thường rất nhẹ. Vấn đề nằm ở việc thực hiện công việc tốn thời gian hoặc thay đổi trạng thái ngay khi Gradle đang cấu hình project, thay vì để công việc đó thuộc về task có đầu vào, đầu ra và thời điểm thực thi rõ ràng.

Ví dụ không nên đặt ở cấp cao nhất của build script:

~~~kotlin
// Không nên: ghi tệp ngay trong configuration.
file("build-info.txt").writeText("Build started")

// Không nên: đọc toàn bộ danh sách tệp ngay trong configuration.
val allReports = fileTree("reports").files

// Không nên: chạy chương trình bên ngoài ngay trong configuration.
exec {
    commandLine("python", "scripts/generate.py")
}
~~~

Các câu lệnh trên không được gắn với một task action. Chúng có thể chạy chỉ vì Gradle đang cấu hình project, kể cả khi người dùng chỉ muốn xem task hoặc chạy một tác vụ không liên quan.

## 3. Vì sao công việc nặng trong configuration gây hại?

### Làm chậm cả những lệnh không cần công việc đó

Giả sử dự án có một đoạn build script quét 20.000 tệp để tạo báo cáo, nhưng báo cáo chỉ cần khi chạy task **generateReport**. Nếu đoạn quét nằm ở cấp cao nhất, lệnh **help**, **tasks** hoặc **test** vẫn có thể phải trả chi phí quét tệp khi cấu hình project.

Nếu chuyển việc quét vào task, Gradle chỉ cần xử lý nó khi task được chọn và cần thực hiện.

### Làm giảm hiệu quả của configuration cache

Configuration cache lưu kết quả cấu hình để Gradle có thể tái sử dụng trong lần chạy phù hợp tiếp theo. Nếu build script phụ thuộc vào trạng thái bên ngoài không được khai báo hoặc thực hiện các tác dụng phụ không phù hợp, Gradle khó bảo đảm kết quả cấu hình có thể được tái sử dụng an toàn.

### Tạo hành vi khó dự đoán

Một build script ghi tệp hoặc gọi dịch vụ bên ngoài trong lúc cấu hình có thể tạo ra kết quả khác nhau giữa máy phát triển, CI và các lần chạy liên tiếp. Công việc cũng có thể xảy ra nhiều lần khi Gradle cấu hình nhiều project.

### Làm khó việc song song và cô lập project

Trạng thái dùng chung có thể khiến các project phụ thuộc vào thứ tự cấu hình hoặc làm các build song song can thiệp lẫn nhau. Khi build cần hỗ trợ configuration cache hoặc các cơ chế cô lập project, việc truy cập trạng thái tùy tiện càng dễ trở thành vấn đề.

### Làm sai lệch việc đo thời gian

Nếu một thao tác nặng nằm trong configuration, thời gian cấu hình sẽ tăng lên dù task action rất nhanh. Người phát triển có thể tưởng rằng task chậm, trong khi nguyên nhân thực tế là build script đã làm quá nhiều việc trước khi task bắt đầu.

## 4. Chuyển công việc vào task execution

Cách xử lý phổ biến là khai báo task trong giai đoạn cấu hình, nhưng chỉ thực hiện thao tác khi task được chạy.

Ví dụ, muốn gọi một script để tạo tài liệu. Không chạy script trực tiếp trong build script:

~~~kotlin
// Không nên: script chạy ngay khi cấu hình project.
exec {
    commandLine("python", "scripts/generate_docs.py")
}
~~~

Hãy đăng ký một task:

~~~kotlin
tasks.register<Exec>("generateDocs") {
    workingDir(layout.projectDirectory)
    commandLine(
        "python",
        "scripts/generate_docs.py",
        "docs",
        "build/generated/docs"
    )
    inputs.dir("docs")
    outputs.dir(layout.buildDirectory.dir("generated/docs"))
}
~~~

Khi Gradle cấu hình project, nó chỉ đăng ký task và mô tả lệnh cần chạy. Tiến trình Python chỉ được khởi chạy nếu **generateDocs** được chọn trong task graph và Gradle quyết định thực thi task đó.

Khi cần tạo tài liệu:

~~~bash
./gradlew generateDocs
~~~

Nếu chạy một task không liên quan, chẳng hạn:

~~~bash
./gradlew help
~~~

thì Gradle không cần thực hiện script tạo tài liệu.

Trong ví dụ, **inputs.dir** và **outputs.dir** mô tả dữ liệu task đọc và kết quả task tạo. Việc khai báo này giúp Gradle theo dõi công việc tốt hơn và có cơ sở để kiểm tra tính cập nhật. Với tác vụ thực tế, hãy khai báo đầy đủ mọi đầu vào và đầu ra có ảnh hưởng đến kết quả.

Task kiểu **Exec** phù hợp khi cần gọi công cụ bên ngoài. Nếu cần logic Java hoặc Kotlin phức tạp, hãy tạo task type riêng và đặt phần xử lý trong phương thức được đánh dấu **@TaskAction**. Tránh gọi hàm xử lý nặng trực tiếp trong build script.

## 5. Dùng task lazy thay vì tạo và cấu hình mọi task ngay lập tức

Gradle cung cấp API lazy để trì hoãn việc tạo và cấu hình task cho đến khi cần. Đây là một trong những cách quan trọng nhất để giảm công việc trong giai đoạn cấu hình.

### Đăng ký task bằng tasks.register

Không nên tạo task ngay nếu chưa có lý do cần realization tức thì:

~~~kotlin
// Eager: task được tạo ngay.
tasks.create("makeReport") {
    doLast {
        println("Report generated")
    }
}
~~~

Dùng API lazy:

~~~kotlin
// Lazy: đăng ký provider; task được tạo khi cần.
val makeReport = tasks.register("makeReport") {
    doLast {
        println("Report generated")
    }
}
~~~

**tasks.register** trả về một **TaskProvider**. Gradle có thể biết task tồn tại mà chưa phải tạo đối tượng task và chạy toàn bộ cấu hình của nó ngay lập tức.

Việc đăng ký task vẫn diễn ra trong configuration phase, nhưng phần cấu hình task được trì hoãn cho đến khi task được yêu cầu hoặc được truy cập theo cách cần realization.

### Tham chiếu task bằng tasks.named

Nếu muốn cấu hình một task đã được plugin đăng ký, ưu tiên **tasks.named**:

~~~kotlin
tasks.named<Jar>("jar") {
    archiveFileName.set("application.jar")
}
~~~

Cách này lấy một provider của task có tên **jar** và thêm cấu hình theo cơ chế lazy.

Tránh gọi **tasks.getByName** chỉ để cấu hình task nếu không cần realization ngay:

~~~kotlin
// Có thể khiến task được realize sớm.
tasks.getByName("jar") {
    // ...
}
~~~

### Cấu hình nhóm task bằng configureEach

Nếu muốn áp dụng cấu hình cho mọi task thuộc một loại, dùng **configureEach**:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
~~~

Cách viết eager thường gặp:

~~~kotlin
tasks.withType<JavaCompile>().all {
    options.encoding = "UTF-8"
}
~~~

**configureEach** trì hoãn việc áp dụng cấu hình cho đến khi từng task được realize. Điều này giúp Gradle tránh cấu hình các task không bao giờ được sử dụng trong lần build.

| API | Cách hoạt động | Khuyến nghị |
|---|---|---|
| **tasks.register** | Đăng ký task theo cơ chế lazy | Ưu tiên khi tạo task mới |
| **tasks.named** | Lấy provider của task đã đăng ký | Ưu tiên khi cấu hình một task cụ thể |
| **tasks.withType(...).configureEach** | Cấu hình lazy các task cùng loại | Ưu tiên khi áp dụng quy tắc theo loại |
| **tasks.create** | Tạo task ngay | Tránh nếu không cần realization tức thì |
| **tasks.getByName** | Lấy task bằng cách realize task | Tránh khi chỉ cần tham chiếu lazy |
| **tasks.withType(...).all** | Áp dụng action theo cách eager | Ưu tiên thay bằng configureEach |

Tên API có thể khác cú pháp giữa Kotlin DSL và Groovy DSL, nhưng nguyên tắc giống nhau. Trong Groovy DSL, có thể viết:

~~~groovy
tasks.register('makeReport') {
    doLast {
        println 'Report generated'
    }
}

tasks.named('jar') {
    archiveFileName = 'application.jar'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}
~~~

## 6. Tránh đọc dữ liệu Provider quá sớm

Gradle có Provider API để biểu diễn một giá trị có thể được xác định sau. Provider giúp giữ dữ liệu ở dạng lazy và nối các giá trị với thuộc tính của task mà không cần tính toán ngay trong configuration.

Ví dụ, lấy phiên bản từ Gradle property:

~~~kotlin
val releaseVersion = providers
    .gradleProperty("releaseVersion")
    .orElse("1.0.0")

tasks.named<Jar>("jar") {
    archiveVersion.set(releaseVersion)
}
~~~

Có thể cung cấp giá trị khi chạy:

~~~bash
./gradlew jar -PreleaseVersion=2.4.0
~~~

Ở đây, task nhận một Provider làm nguồn cho thuộc tính phiên bản. Không cần tự đọc tệp cấu hình hoặc truy vấn dịch vụ bên ngoài ngay khi build script được đánh giá.

Một lỗi thường gặp là gọi **get()** quá sớm:

~~~kotlin
// Có thể buộc Provider phải được phân giải ngay trong configuration.
val version = providers.gradleProperty("releaseVersion")
    .orElse("1.0.0")
    .get()

tasks.named<Jar>("jar") {
    archiveVersion.set(version)
}
~~~

Nếu giá trị có thể được truyền trực tiếp cho thuộc tính nhận Provider, hãy giữ nó ở dạng Provider thay vì lấy giá trị bằng **get()** trong lúc cấu hình.

Một số nguồn Provider thường dùng:

- **providers.gradleProperty("name")**: đọc Gradle property.
- **providers.environmentVariable("NAME")**: đọc biến môi trường.
- **layout.projectDirectory**: tham chiếu đến thư mục project.
- **layout.buildDirectory**: tham chiếu đến thư mục build.
- **Provider.map** và **Provider.flatMap**: biến đổi hoặc nối các giá trị lazy.

Ví dụ kết hợp property và đường dẫn đầu ra:

~~~kotlin
val reportName = providers
    .gradleProperty("reportName")
    .orElse("summary.txt")

val reportFile = layout.buildDirectory.file(reportName)

tasks.register("showReportLocation") {
    doLast {
        println(reportFile.get().asFile.absolutePath)
    }
}
~~~

Provider của đường dẫn được tạo trong configuration; giá trị được lấy trong task action. Trong task type chuyên biệt, nên dùng các thuộc tính Gradle như **RegularFileProperty**, **DirectoryProperty** và **Property<T>** để mô hình hóa dữ liệu đầu vào, đầu ra và tham số.

Không phải mọi lời gọi **get()** đều tự động là lỗi. Một số giá trị tĩnh, nhẹ cần được biết trong configuration. Tuy nhiên, nếu Provider có thể kích hoạt việc đọc tệp, gọi công cụ hoặc tính toán đáng kể, hãy tránh phân giải nó sớm và thiết kế để Gradle chỉ cần giá trị khi thực sự cần.

## 7. Không quét và đọc toàn bộ tệp khi cấu hình

Một dự án lớn có thể chứa hàng nghìn tệp. Nếu build script gọi **.files** rồi duyệt toàn bộ danh sách ở cấp cao nhất, việc liệt kê tệp sẽ diễn ra trong configuration.

Ví dụ không nên dùng:

~~~kotlin
val reportFiles = fileTree("reports") {
    include("**/*.xml")
}.files

tasks.register("packageReports") {
    doLast {
        reportFiles.forEach {
            println(it.name)
        }
    }
}
~~~

Danh sách **reportFiles** đã được lấy trước khi task chạy. Vì vậy, kể cả khi **packageReports** không được chọn, Gradle vẫn phải xử lý việc liệt kê tệp lúc cấu hình.

Nếu mục tiêu là đóng gói các tệp báo cáo, hãy dùng task type phù hợp và giữ file collection ở dạng lazy:

~~~kotlin
tasks.register<Zip>("packageReports") {
    from(fileTree("reports") {
        include("**/*.xml")
    })
    archiveFileName.set("reports.zip")
    destinationDirectory.set(layout.buildDirectory.dir("archives"))
}
~~~

Task **Zip** khai báo thư mục nguồn và nơi ghi tệp ZIP. Gradle có thể theo dõi đầu vào, đầu ra và chỉ thực hiện đóng gói khi task được yêu cầu.

Khi viết task type riêng, hãy đọc danh sách tệp bên trong **@TaskAction**, sau khi task đã bước vào execution. Đồng thời khai báo tập tệp đó bằng **@InputFiles** hoặc thuộc tính đầu vào thích hợp để Gradle có thể snapshot dữ liệu và xác định khi nào task cần chạy lại.

## 8. Không gọi mạng hoặc dịch vụ ngoài trong configuration

Một build script đôi khi cần phiên bản mới nhất của thư viện, metadata phát hành hoặc thông tin từ API. Nếu gọi mạng ngay trong lúc cấu hình, mọi lệnh Gradle có thể phải chờ mạng và phụ thuộc vào trạng thái dịch vụ bên ngoài.

Ví dụ không nên:

~~~kotlin
// Minh họa thao tác không nên thực hiện ở cấp cấu hình.
val remoteMetadata = java.net.URL("https://repo.example.org/metadata").readText()

tasks.register("publishMetadata") {
    doLast {
        println(remoteMetadata)
    }
}
~~~

Dù task **publishMetadata** chưa được chọn, lời gọi **readText()** vẫn xảy ra khi build script được đánh giá.

Có thể chuyển việc tải hoặc truy vấn vào một task riêng. Task đó cần khai báo:

- Tham số hoặc URL nguồn như một input.
- Phiên bản, checksum hoặc định danh dữ liệu để kết quả có thể tái lập.
- Tệp hoặc thư mục đầu ra mà task tạo.
- Chính sách lỗi, timeout và xác thực phù hợp.
- Cơ chế tránh tải lại khi dữ liệu đầu vào không thay đổi.

Nếu dữ liệu từ xa được dùng để quyết định cấu hình hoặc lựa chọn dependency, hãy cân nhắc cơ chế dependency resolution và metadata của Gradle thay vì tự viết HTTP request ở build script. Gradle có các cơ chế quản lý repository, module metadata và dependency version dành cho mục đích này.

Đối với dữ liệu bên ngoài không ổn định, không nên giả định rằng một URL luôn trả về cùng nội dung. Hãy dùng phiên bản cụ thể hoặc checksum để kết quả build có thể kiểm soát. Không đặt thông tin bí mật như token truy cập trực tiếp trong build script hoặc log.

## 9. Tránh chạy tiến trình và lệnh hệ điều hành khi cấu hình

Các lệnh như **git**, **python**, **node**, **curl**, compiler hoặc shell script thường là công việc thực thi, không phải cấu hình. Gọi chúng trực tiếp ở cấp cao nhất của build script khiến mỗi lần configuration có thể tạo một tiến trình mới.

Nếu chỉ cần đọc một giá trị đơn giản từ Gradle property hoặc biến môi trường, hãy dùng Provider API. Nếu cần chạy công cụ để tạo đầu ra, hãy mô hình hóa nó bằng task, chẳng hạn **Exec**, hoặc task type riêng.

Ví dụ:

~~~kotlin
tasks.register<Exec>("compileSchema") {
    workingDir(layout.projectDirectory)
    commandLine(
        "python",
        "scripts/compile_schema.py",
        "schema",
        "build/generated/schema"
    )
    inputs.dir("schema")
    outputs.dir(layout.buildDirectory.dir("generated/schema"))
}
~~~

Lệnh Python chỉ chạy khi task **compileSchema** được thực thi. Các đường dẫn nguồn và đích cũng được mô tả để Gradle có thể theo dõi.

Không dùng **doLast** như một cách để giấu mọi công việc mà không khai báo đầu vào và đầu ra. Task có thể chạy đúng thời điểm nhưng vẫn khó kiểm tra tính cập nhật, không thể tái sử dụng đầu ra và không tận dụng tốt build cache. Với công việc tạo tệp, hãy khai báo inputs/outputs hoặc dùng task type có thuộc tính tương ứng.

## 10. Dùng task type với đầu vào và đầu ra rõ ràng

Khi logic xử lý không phù hợp với một task tích hợp sẵn như **Copy**, **Zip** hoặc **Exec**, hãy tạo task type riêng. Task type nên biểu diễn dữ liệu bằng các property của Gradle và chỉ xử lý dữ liệu trong task action.

Ví dụ minh họa bằng Kotlin:

~~~kotlin
abstract class GenerateFileList : DefaultTask() {
    @get:InputFiles
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val sourceFiles: ConfigurableFileCollection

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val names = sourceFiles.files
            .filter { it.isFile }
            .map { it.name }
            .sorted()

        val target = outputFile.get().asFile
        target.parentFile.mkdirs()
        target.writeText(names.joinToString(System.lineSeparator()))
    }
}

tasks.register<GenerateFileList>("generateFileList") {
    sourceFiles.from(fileTree("src") {
        include("**/*.java")
    })
    outputFile.set(layout.buildDirectory.file("reports/source-files.txt"))
}
~~~

Các điểm cần chú ý:

- **@InputFiles** khai báo các tệp mà task đọc.
- **@PathSensitive(PathSensitivity.RELATIVE)** xác định cách đường dẫn đầu vào tham gia fingerprint của task.
- **@OutputFile** khai báo tệp mà task tạo.
- **@TaskAction** đánh dấu phương thức chạy trong execution phase.
- **sourceFiles.files** chỉ được truy cập trong task action, nên việc lấy danh sách tệp phục vụ xử lý diễn ra khi task thực sự được thực thi.
- **outputFile** là một RegularFileProperty do Gradle quản lý, thay vì một đường dẫn được tính và ghi ngay trong build script.

Ví dụ này tập trung vào việc phân chia thời điểm cấu hình và thực thi. Nếu muốn bật build cache cho task tùy chỉnh, chỉ thêm **@CacheableTask** khi đầu ra hoàn toàn được xác định bởi các input đã khai báo, tác vụ có kết quả xác định và không tạo tác dụng phụ bên ngoài. Nếu task phụ thuộc vào thời gian hiện tại, trạng thái mạng hoặc dữ liệu không được khai báo, cần thiết kế lại inputs hoặc không đánh dấu task cacheable.

Trong dự án thực tế, task type thường được đặt trong convention plugin hoặc plugin riêng để build script của từng module chỉ còn phần khai báo dữ liệu và kết nối task.

## 11. Hạn chế cấu hình hàng loạt trên toàn bộ project

Các khối cấu hình rộng như **allprojects**, **subprojects** hoặc vòng lặp truy cập task của nhiều project có thể khiến build script khó hiểu và tạo thêm công việc cấu hình không cần thiết.

Ví dụ:

~~~kotlin
subprojects {
    tasks.all {
        // Áp dụng cấu hình ngay cho nhiều task.
    }
}
~~~

Cách này có thể tạo quan hệ phụ thuộc cấu hình giữa các project, làm cho một thay đổi nhỏ ảnh hưởng đến nhiều module và gây khó khăn cho configuration cache hoặc cấu hình song song.

Một cách tổ chức tốt hơn là đưa quy tắc chung vào convention plugin rồi áp dụng plugin đó cho những project cần thiết. Ví dụ, plugin quy ước có thể thiết lập encoding cho Java compile task:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
~~~

Sau đó mỗi module áp dụng convention plugin phù hợp. Cách này giữ cấu hình gần với project sở hữu task, giảm việc truy cập chéo và giúp quy tắc build dễ tái sử dụng.

Không phải mọi cấu hình đa project đều sai. Một số dự án cần cấu hình chung ở root project. Tuy nhiên, hãy tránh duyệt và realize toàn bộ task chỉ để thay đổi một thuộc tính đơn giản; dùng plugin, lazy API và Provider để giới hạn phạm vi công việc.

## 12. Dùng configuration cache đúng mục đích

Configuration cache lưu kết quả của giai đoạn cấu hình và task graph cho một lần gọi Gradle phù hợp. Khi lần chạy tiếp theo có cùng yêu cầu và các điều kiện đầu vào liên quan không thay đổi, Gradle có thể tái sử dụng kết quả đó và bỏ qua phần lớn công việc cấu hình.

Bật configuration cache bằng:

~~~bash
./gradlew build --configuration-cache
~~~

Chạy lại cùng lệnh:

~~~bash
./gradlew build --configuration-cache
~~~

Ở lần chạy sau, nếu Gradle có thể tái sử dụng entry phù hợp, output sẽ cho biết configuration cache được dùng lại. Lần đầu thường phải cấu hình và lưu entry, nên chưa chắc nhanh hơn. Lợi ích thường rõ hơn ở các lần chạy lặp lại.

Configuration cache khuyến khích build script có cấu trúc rõ ràng và tránh tác dụng phụ trong configuration. Một số mẫu cũ có thể không tương thích vì giữ tham chiếu đến **Project**, truy cập model ngoài phạm vi được phép hoặc phụ thuộc vào trạng thái không được khai báo. Gradle sẽ báo vấn đề khi cố lưu hoặc tái sử dụng configuration cache; hãy sửa theo hướng task action nhận dữ liệu qua property hoặc dịch vụ được hỗ trợ.

Configuration cache không thay thế việc khai báo task inputs và outputs. Nó lưu kết quả cấu hình, còn Gradle vẫn cần xác định task có phải chạy lại hay có thể dùng đầu ra hiện có.

### Phân biệt configuration cache và build cache

| Cơ chế | Lưu gì? | Có thể tránh công việc nào? |
|---|---|---|
| Configuration cache | Kết quả cấu hình và task graph cho yêu cầu phù hợp | Đánh giá lại build script và cấu hình project trong lần chạy có thể tái sử dụng |
| Build cache | Đầu ra của các task có thể cache | Thực thi lại action của task khi tìm được đầu ra phù hợp |
| Up-to-date checking | Trạng thái đầu vào/đầu ra của task trong workspace | Chạy lại action khi đầu vào không thay đổi và đầu ra còn hợp lệ |

Một build có thể tái sử dụng configuration cache nhưng vẫn phải chạy một số task. Ngược lại, task có thể **UP-TO-DATE** hoặc lấy đầu ra từ build cache trong khi configuration vẫn phải diễn ra.

Vì vậy, bật build cache không giải quyết được build script đang tải dữ liệu hoặc quét tệp ngay trong configuration. Muốn giảm thời gian cấu hình, cần giảm công việc ở configuration và thiết kế build tương thích với configuration cache.

## 13. Đo thời gian để xác định configuration có đang quá nặng không

Trước khi tối ưu, hãy đo thời gian để biết phần nào đang chiếm chi phí. Có thể dùng Gradle profiler tích hợp qua tùy chọn **--profile**:

~~~bash
./gradlew build --profile
~~~

Gradle tạo báo cáo profile trong thư mục báo cáo của build, thường nằm dưới **build/reports/profile/**. Báo cáo có thể giúp quan sát thời gian cấu hình và thời gian thực thi task.

Có thể so sánh hai lần chạy:

1. Lần đầu chạy build với **--profile** để xem chi phí cấu hình ban đầu.
2. Lần tiếp theo dùng **--configuration-cache** để quan sát khả năng tái sử dụng cấu hình.
3. Thử chạy một task nhỏ như **help** hoặc **tasks** để nhận biết liệu configuration có quá nặng ngay cả khi không thực hiện công việc build chính.
4. Dùng **--info** khi cần thêm thông tin về task và quyết định thực thi.

Ví dụ:

~~~bash
./gradlew help --profile
./gradlew build --configuration-cache --profile
~~~

Khi phân tích báo cáo, hãy tách biệt thời gian cấu hình, thời gian task thực thi và thời gian chờ tiến trình bên ngoài. Nếu **help** cũng mất nhiều thời gian, nguyên nhân có thể nằm trong cấu hình build, plugin hoặc script cấp project. Nếu chỉ một task cụ thể chậm, hãy kiểm tra task action, đầu vào và công cụ mà task gọi.

Không nên tối ưu dựa trên một lần chạy đơn lẻ. Thời gian còn chịu ảnh hưởng bởi daemon, cache, ổ đĩa, mạng và trạng thái máy. Hãy so sánh nhiều lần chạy trong điều kiện tương tự và ghi rõ configuration cache đang được dùng hay chưa.

## 14. Những mẫu nên tránh và cách thay thế

| Mẫu dễ gây vấn đề | Vì sao không nên | Hướng thay thế |
|---|---|---|
| Gọi **file.writeText()** ở cấp cao nhất | Ghi tệp trong configuration, kể cả khi task liên quan không chạy | Đưa thao tác ghi vào task action và khai báo output |
| Gọi **exec { ... }** ở cấp project | Khởi chạy tiến trình trong configuration | Đăng ký **Exec** task hoặc task type riêng |
| Gọi HTTP hoặc đọc metadata từ mạng ở cấp cao nhất | Mọi lần cấu hình có thể phải chờ mạng và nhận kết quả thay đổi | Dùng dependency resolution hoặc task có input/output rõ ràng |
| Gọi **fileTree(...).files** sớm | Liệt kê tệp ngay trong configuration | Giữ FileCollection/FileTree lazy và truy cập dữ liệu trong task action |
| Dùng **tasks.create** cho mọi task | Realize task sớm | Dùng **tasks.register** |
| Dùng **tasks.getByName** chỉ để cấu hình | Có thể buộc task realize ngay | Dùng **tasks.named** |
| Dùng **tasks.withType(...).all** | Áp dụng cấu hình eager cho task cùng loại | Dùng **configureEach** |
| Dùng **afterEvaluate** để trì hoãn công việc nặng | Công việc vẫn nằm trong configuration và phụ thuộc thứ tự đánh giá | Dùng Provider, plugin callback phù hợp hoặc task action |
| Giữ trạng thái mutable dùng chung giữa các project | Tạo phụ thuộc ngầm và khó cô lập | Truyền dữ liệu qua property, task input hoặc Build Service phù hợp |

**afterEvaluate** không phải giải pháp chung cho công việc cấu hình nặng. Nó chỉ trì hoãn một đoạn cấu hình đến cuối quá trình đánh giá project; đoạn code vẫn thuộc configuration phase và vẫn có thể gây tác dụng phụ hoặc làm configuration cache khó tái sử dụng.

## 15. Quy trình chuyển một đoạn build script nặng sang thiết kế phù hợp

Khi phát hiện build script có công việc nặng, hãy xử lý theo các bước:

**Bước 1: Xác định thời điểm đoạn code chạy**

Kiểm tra đoạn code nằm ở cấp cao nhất của build script, trong callback cấu hình task hay bên trong task action. Một lời gọi nằm trong callback cấu hình vẫn có thể chạy trong configuration phase.

**Bước 2: Xác định công việc thực sự cần làm**

Ví dụ: quét tệp, tạo báo cáo, tải schema, gọi compiler hoặc xuất bản artifact. Xác định dữ liệu nào được đọc và kết quả nào được tạo.

**Bước 3: Tạo task đại diện cho công việc**

Dùng task tích hợp sẵn như **Copy**, **Zip**, **JavaCompile**, **Exec** nếu phù hợp. Nếu logic riêng phức tạp, tạo task type.

**Bước 4: Khai báo inputs và outputs**

Mọi dữ liệu ảnh hưởng đến kết quả cần được mô hình hóa thành task input. Tệp hoặc thư mục được tạo cần được khai báo thành output. Điều này giúp Gradle kiểm tra tính cập nhật và hỗ trợ cache khi task đáp ứng các điều kiện tương ứng.

**Bước 5: Đăng ký task theo cơ chế lazy**

Dùng **tasks.register**, cấu hình task khác bằng **tasks.named**, và áp dụng quy tắc theo loại bằng **configureEach**. Truyền Provider vào các thuộc tính thay vì lấy giá trị sớm.

**Bước 6: Chỉ nối task vào graph khi cần**

Dùng dependency như **dependsOn** hoặc kết nối đầu ra task với đầu vào của task tiếp theo. Không đưa công việc vào mọi build nếu chỉ một quy trình cụ thể cần nó.

**Bước 7: Kiểm tra configuration cache và đo lại**

Chạy build với **--configuration-cache**, quan sát việc lưu và tái sử dụng entry, rồi so sánh thời gian cấu hình trước và sau. Nếu Gradle báo vấn đề configuration cache, xử lý nguyên nhân ở cách truy cập trạng thái hoặc thiết kế task.

## 16. Ví dụ tổng hợp: từ build script làm quá nhiều việc đến task lazy

Giả sử dự án cần gom các tệp XML trong thư mục **reports/** thành một tệp ZIP.

Cách viết không phù hợp:

~~~kotlin
// Việc liệt kê tệp diễn ra trong configuration.
val reportFiles = fileTree("reports").matching {
    include("**/*.xml")
}.files

// Task được tạo ngay.
tasks.create("archiveReports") {
    doLast {
        reportFiles.forEach {
            println("Including " + it.name)
        }
    }
}
~~~

Đoạn này có hai vấn đề: danh sách tệp được materialize trước khi biết task có cần chạy hay không, và task được tạo ngay khi cấu hình.

Cách viết lazy hơn:

~~~kotlin
tasks.register<Zip>("archiveReports") {
    from(fileTree("reports") {
        include("**/*.xml")
    })
    archiveFileName.set("reports.zip")
    destinationDirectory.set(layout.buildDirectory.dir("archives"))
}
~~~

Với cách này:

- Gradle chỉ đăng ký task trong configuration.
- File tree được giữ trong cấu hình của task, không cần lấy toàn bộ danh sách bằng **.files** ở cấp project.
- Task khai báo nguồn và đích để Gradle theo dõi.
- Việc tạo ZIP chỉ xảy ra khi task được chọn và cần thực thi.

Chạy task:

~~~bash
./gradlew archiveReports
~~~

Nếu chạy:

~~~bash
./gradlew help
~~~

thì Gradle không cần thực hiện việc tạo ZIP. Task có thể chưa được realize và task action không chạy.

Đây là mô hình nên hướng tới: build script mô tả task và dữ liệu; Gradle quyết định thời điểm thực thi dựa trên task graph; task chịu trách nhiệm thực hiện công việc có đầu vào và đầu ra cụ thể.

## 17. Những nguyên tắc cần nhớ

- Giữ initialization và configuration nhẹ; tránh tải dữ liệu, gọi tiến trình, ghi tệp hoặc quét dữ liệu lớn ở cấp cao nhất của build script.
- Đăng ký task bằng **tasks.register**, cấu hình task bằng **tasks.named**, và dùng **configureEach** cho nhóm task.
- Giữ Provider ở dạng lazy; chỉ lấy giá trị khi thực sự cần.
- Chuyển công việc nặng vào task action hoặc task type riêng.
- Khai báo đầy đủ task inputs và outputs để Gradle theo dõi dữ liệu, kiểm tra tính cập nhật và hỗ trợ cache.
- Dùng task type tích hợp sẵn như **Copy**, **Zip** hoặc **Exec** khi phù hợp.
- Tránh dùng **afterEvaluate** để che giấu công việc vẫn thuộc configuration phase.
- Hạn chế truy cập chéo project và trạng thái mutable dùng chung; ưu tiên convention plugin và property tường minh.
- Dùng **--profile** để đo thời gian và **--configuration-cache** để kiểm tra khả năng tái sử dụng cấu hình.
- Phân biệt configuration cache với build cache: một cơ chế tái sử dụng kết quả cấu hình, cơ chế còn lại tái sử dụng đầu ra task.

Khi build script chỉ mô tả cấu hình và task, còn các thao tác tốn thời gian được thực hiện trong đúng task với inputs/outputs rõ ràng, Gradle có thể lựa chọn công việc chính xác hơn, giảm thời gian cấu hình cho các lệnh không liên quan và tái sử dụng kết quả cấu hình hiệu quả hơn.

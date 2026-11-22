# Tránh tác vụ không cần thiết và đầu vào quá rộng

Gradle có thể build nhanh khi chỉ thực hiện những công việc cần thiết và mỗi task chỉ theo dõi đúng dữ liệu có ảnh hưởng tới kết quả. Một build chậm thường không chỉ do compiler hoặc test chạy lâu; nó còn có thể cấu hình quá nhiều project, tạo task sớm, quét hàng nghìn file không liên quan, đưa cả thư mục gốc vào input, hoặc buộc một task phụ thuộc vào toàn bộ lifecycle task của module khác.

Hai nguyên tắc quan trọng là **chỉ đưa công việc cần thiết vào task graph** và **khai báo đầu vào đủ chính xác nhưng không rộng hơn mức cần thiết**. Khi task graph nhỏ và input/output rõ ràng, Gradle có thể tránh tạo task không dùng tới, bỏ qua task không đổi, xử lý incremental và tái sử dụng build cache an toàn hơn.

Bài học này tập trung vào cách thiết kế build script và custom task để giảm công việc thừa mà vẫn giữ dependency chính xác.

## 1. Hiệu năng build bắt đầu từ phạm vi công việc

Một Gradle invocation thường trải qua các giai đoạn:

1. Khởi tạo build và đọc settings.
2. Cấu hình project và plugin cần thiết.
3. Tạo task graph từ các task được yêu cầu và dependency của chúng.
4. Thực thi các task theo quan hệ prerequisite và giới hạn worker.

Một build có thể tốn thời gian ở nhiều nơi:

- Configuration phase cấu hình quá nhiều project hoặc chạy logic nặng.
- Task graph kéo theo những task không cần cho mục tiêu hiện tại.
- Task thực thi dù input không thay đổi.
- Task quét thư mục lớn hoặc xử lý file không liên quan.
- Task custom không khai báo input/output đúng nên Gradle không thể bỏ qua hoặc tái sử dụng kết quả.
- Task phụ thuộc vào lifecycle task như build hoặc check dù chỉ cần một file output nhỏ.

~~~mermaid
flowchart TD
    A[Gradle invocation] --> B[Configuration]
    B --> C[Task graph]
    C --> D[Task execution]
    D --> E[Outputs]
    B --> F[Unneeded project configuration]
    C --> G[Unneeded task dependencies]
    D --> H[Unnecessary file processing]
    D --> I[Task reruns caused by broad inputs]
~~~

Muốn tối ưu, cần xác định giai đoạn đang tạo công việc thừa. Chỉ tăng số worker hoặc bật parallel execution không giải quyết được một task graph quá rộng hay input không chính xác.

## 2. Chỉ đăng ký task khi cần: configuration avoidance

Gradle cung cấp API lazy để đăng ký và cấu hình task. Task chỉ được cấu hình sâu khi Gradle cần sử dụng nó.

Ưu tiên:

- tasks.register(...) thay cho tasks.create(...).
- tasks.named(...) để tham chiếu task đã biết.
- tasks.withType(...).configureEach { } để áp dụng cấu hình theo kiểu task một cách lazy.

Ví dụ Kotlin DSL:

~~~kotlin
tasks.register("generateDocs") {
    group = "documentation"
    description = "Generates project documentation."
    doLast {
        println("Generating documentation")
    }
}
~~~

Ví dụ Groovy DSL:

~~~groovy
tasks.register('generateDocs') {
    group = 'documentation'
    description = 'Generates project documentation'
    doLast {
        println 'Generating documentation'
    }
}
~~~

Các API eager như tasks.create, tasks.getByName, tasks.all hoặc một số cách truy cập task ngay lập tức có thể khiến task được tạo/cấu hình sớm hơn cần thiết. Trong build lớn, lặp lại hành vi eager ở nhiều project làm configuration phase tốn thời gian.

Ví dụ nên tránh:

~~~kotlin
tasks.create("generateDocs") {
    // Task được tạo ngay khi đoạn cấu hình chạy.
}

tasks.getByName("test") {
    // Truy cập task ngay lập tức có thể khiến task được realize.
}
~~~

Cách lazy tương ứng:

~~~kotlin
tasks.register("generateDocs") {
    // Đăng ký task; cấu hình được trì hoãn.
}

tasks.named("test") {
    // Cấu hình task theo tên qua provider.
}
~~~

Đăng ký task không có nghĩa task sẽ chạy. Task chỉ được thực thi nếu được yêu cầu trực tiếp hoặc được đưa vào graph bởi dependency/finalizer/order logic thích hợp.

## 3. Dùng configureEach thay cho cấu hình eager hàng loạt

Khi cần áp dụng cấu hình cho mọi task thuộc một type, dùng configureEach:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(21)
}
~~~

Groovy DSL:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 21
}
~~~

configureEach đăng ký hành động cấu hình lazy cho những task phù hợp. Cách này phù hợp với plugin hoặc convention plugin cần áp dụng cùng quy tắc cho task được tạo sau đó.

Tránh duyệt toàn bộ task để cấu hình ngay:

~~~groovy
tasks.withType(JavaCompile).all {
    options.encoding = 'UTF-8'
}
~~~

Trong build lớn, các thao tác eager có thể làm nhiều task được realize chỉ vì một đoạn cấu hình chung. Ưu tiên API lazy và chỉ truy cập task khi thực sự cần.

## 4. Không thực hiện công việc nặng trong configuration phase

Configuration phase nên mô tả build: plugin, dependency, task, input/output và quan hệ giữa chúng. Không nên dùng giai đoạn này để chạy công việc mà chỉ một task cụ thể mới cần.

Ví dụ không tốt:

~~~groovy
def schemaText = new URL('https://example.com/schema.json').text

tasks.register('generateClient') {
    doLast {
        file("$buildDir/generated/Client.java").text = schemaText
    }
}
~~~

Chỉ cần cấu hình build, Gradle đã truy cập mạng. Ngay cả khi người dùng chỉ chạy task không liên quan, request vẫn có thể diễn ra.

Cách tốt hơn là đưa việc lấy dữ liệu vào một task riêng với input/output rõ ràng, hoặc chuẩn bị file đầu vào trước build:

~~~kotlin
abstract class GenerateClient : DefaultTask() {
    @get:InputFile
    abstract val schemaFile: RegularFileProperty

    @get:OutputDirectory
    abstract val outputDirectory: DirectoryProperty

    @TaskAction
    fun generate() {
        val schema = schemaFile.get().asFile
        val outputDir = outputDirectory.get().asFile
        outputDir.mkdirs()
        // Đọc schema và sinh source vào outputDir.
    }
}

tasks.register<GenerateClient>("generateClient") {
    schemaFile.set(layout.projectDirectory.file("schema/api.json"))
    outputDirectory.set(layout.buildDirectory.dir("generated/client"))
}
~~~

Task chỉ thực hiện generator khi được yêu cầu. Configuration phase không cần tải hoặc xử lý schema.

Tránh các thao tác nặng trong afterEvaluate, khối cấu hình root hoặc plugin apply nếu chúng không cần thiết. afterEvaluate cũng làm logic khó dự đoán hơn và có thể cản trở configuration avoidance.

## 5. Task graph chỉ nên chứa prerequisite thực sự

Task graph được tạo từ task người dùng yêu cầu và các quan hệ dependency. Nếu task A cần output của task B, hãy khai báo quan hệ producer/consumer chính xác.

Không nên phụ thuộc vào lifecycle task rộng nếu chỉ cần một output nhỏ.

Ví dụ quá rộng:

~~~kotlin
tasks.register("collectApi") {
    dependsOn(":api:build")
}
~~~

build thường kéo theo compile, test, check, assemble và các công việc khác. Nếu task chỉ cần JAR của module api, phụ thuộc vào build có thể chạy nhiều việc không liên quan.

Hãy phụ thuộc vào output cụ thể của task producer:

~~~kotlin
val apiJar = project(":api").tasks.named<Jar>("jar")

tasks.register<Copy>("collectApi") {
    from(apiJar.flatMap { it.archiveFile })
    into(layout.buildDirectory.dir("collected-api"))
}
~~~

Provider output của task JAR được dùng làm input cho task Copy. Gradle có thể suy ra quan hệ producer/consumer từ provider đó và lên lịch task tạo JAR trước task Copy.

Nếu task thực sự cần kiểm thử của module api, hãy khai báo dependency tới task test phù hợp. Không cần kéo cả build chỉ để bảo đảm một bước cụ thể đã chạy.

### Chọn task theo mục tiêu

| Mục tiêu | Task thường phù hợp | Quan hệ nên dùng |
|---|---|---|
| Biên dịch Java của module | compileJava | Project dependency/compile classpath |
| Tạo resource output | processResources | Input resource của source set |
| Tạo JAR | jar | Output của source set và resource tasks |
| Chạy unit test | test | Test runtime/compile dependencies |
| Kiểm tra chất lượng theo lifecycle | check | Các verification task đã gắn với check |
| Tạo artifact và các bước build liên quan | assemble hoặc build tùy mục tiêu | Lifecycle task khi thực sự cần |

Đừng thay một dependency dữ liệu bằng ordering rule. Nếu consumer cần output của producer, dùng input/output provider hoặc dependency rõ ràng.

## 6. Phân biệt dependsOn với ordering rule

Các quan hệ task có ý nghĩa khác nhau:

| Cơ chế | Đưa task prerequisite vào graph? | Dùng khi |
|---|---|---|
| dependsOn | Có | Task hiện tại cần task kia hoàn tất |
| mustRunAfter | Không | Cả hai task đã được chọn và cần thứ tự bắt buộc |
| shouldRunAfter | Không | Muốn gợi ý thứ tự khi có thể |
| finalizedBy | Có, qua finalizer | Cần dọn dẹp hoặc thu thập dữ liệu sau task |

Ví dụ:

~~~kotlin
tasks.named("integrationTest") {
    mustRunAfter(tasks.named("test"))
}
~~~

Cấu hình này không làm test tự chạy khi người dùng chỉ yêu cầu integrationTest.

Nếu integration test cần một task chuẩn bị môi trường, khai báo dependency thực sự:

~~~kotlin
tasks.named("integrationTest") {
    dependsOn("startTestEnvironment")
    finalizedBy("stopTestEnvironment")
}
~~~

Không thêm dependsOn("build") chỉ để ép thứ tự. Hãy xác định đúng task prerequisite.

## 7. Tránh quét toàn bộ project directory làm input

Một lỗi thường gặp trong custom task là dùng toàn bộ project directory làm input:

~~~kotlin
tasks.register("indexProject") {
    inputs.dir(projectDir)
}
~~~

Hoặc:

~~~groovy
tasks.register('indexProject') {
    inputs.files(fileTree(projectDir))
}
~~~

Project directory có thể chứa:

- .git
- .gradle
- build
- out
- node_modules
- IDE metadata
- log và file tạm
- generated output
- tài liệu hoặc tài nguyên không liên quan đến task

Khi bất kỳ file nào thay đổi, task có thể bị coi là out-of-date. Tệ hơn, nếu task đọc cả output của chính nó, có thể tạo vòng lặp input/output hoặc làm cache key biến động.

Thay vào đó, chọn đúng thư mục và pattern:

~~~kotlin
tasks.register("indexJavaSources") {
    inputs.files(
        fileTree("src/main/java") {
            include("**/*.java")
            exclude("**/generated/**")
        }
    )
}
~~~

Nếu task cần cả resources:

~~~kotlin
val sourceInputs = files(
    fileTree("src/main/java") {
        include("**/*.java")
    },
    fileTree("src/main/resources") {
        include("**/*.yml", "**/*.properties", "**/*.xml")
    }
)
~~~

Chỉ thêm các loại file mà task thực sự đọc. Một task xử lý Java source không nên bị đánh dấu out-of-date chỉ vì README hoặc ảnh trong thư mục tài liệu thay đổi.

## 8. Thu hẹp fileTree bằng include và exclude

fileTree cho phép mô tả tập file theo pattern. Dùng include để chọn chính xác loại dữ liệu cần thiết và exclude để loại file không liên quan.

Ví dụ:

~~~kotlin
val schemaFiles = fileTree("src/main/schema") {
    include("**/*.json")
    include("**/*.yaml")
    exclude("**/draft/**")
    exclude("**/generated/**")
}
~~~

Groovy DSL:

~~~groovy
def schemaFiles = fileTree('src/main/schema') {
    include '**/*.json'
    include '**/*.yaml'
    exclude '**/draft/**'
    exclude '**/generated/**'
}
~~~

Không nên chỉ dùng exclude cho một thư mục root rộng nếu có thể chọn đúng source root ngay từ đầu. Input tốt thường bắt đầu từ thư mục nhỏ nhất có chứa dữ liệu task cần.

Nếu task xử lý một file cấu hình duy nhất, dùng InputFile thay vì InputFiles trỏ tới cả cây thư mục.

Nếu task cần nhiều file trong một thư mục chuyên biệt, dùng InputFiles hoặc InputDirectory tùy yêu cầu. Việc chọn annotation phù hợp giúp Gradle xác định rõ loại input và cách theo dõi nó.

## 9. Tránh đưa build output vào input của chính task

Một input directory không nên chứa output directory của cùng task hoặc output của task khác không liên quan.

Ví dụ nguy hiểm:

~~~kotlin
tasks.register("scanEverything") {
    inputs.dir(projectDir)
    outputs.dir(layout.buildDirectory.dir("scan-result"))
}
~~~

Khi task chạy, output được tạo trong build/, nhưng build/ cũng nằm bên trong projectDir. Lần sau, task có thể đọc chính output cũ của mình như input. Mỗi lần chạy lại có thể tạo thêm dữ liệu hoặc làm input snapshot thay đổi.

Thiết kế tốt hơn:

~~~kotlin
abstract class ScanSources : DefaultTask() {
    @get:InputFiles
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val sourceFiles: ConfigurableFileCollection

    @get:OutputDirectory
    abstract val reportDirectory: DirectoryProperty

    @TaskAction
    fun scan() {
        val outputDir = reportDirectory.get().asFile
        outputDir.mkdirs()
        // Chỉ quét sourceFiles và ghi report vào outputDir.
    }
}

tasks.register<ScanSources>("scanSources") {
    sourceFiles.from(fileTree("src/main/java") {
        include("**/*.java")
    })
    reportDirectory.set(layout.buildDirectory.dir("reports/source-scan"))
}
~~~

Input và output nằm ở hai vùng tách biệt. Task không đọc lại report do chính nó tạo.

## 10. Khai báo input theo loại dữ liệu

Custom task nên mô tả input bằng property có kiểu thay vì dùng đường dẫn global hoặc truy cập file tùy tiện trong action.

Các annotation thường gặp:

| Annotation | Ý nghĩa |
|---|---|
| Input | Giá trị scalar hoặc property ảnh hưởng output |
| InputFile | Một file đầu vào |
| InputFiles | Tập file đầu vào |
| InputDirectory | Thư mục đầu vào |
| OutputFile | Một file được task tạo |
| OutputFiles | Tập file output |
| OutputDirectory | Thư mục output |
| Classpath | File collection được xem xét theo ngữ nghĩa classpath |
| CompileClasspath | Classpath đầu vào với snapshot phù hợp cho compile classpath |
| Nested | Object chứa các property input/output lồng nhau |
| Internal | Property không tham gia kiểm tra up-to-date/cache key |

Ví dụ task đọc một file cấu hình:

~~~kotlin
abstract class GenerateCatalog : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val catalogFile: RegularFileProperty

    @get:Input
    abstract val includeDeprecated: Property<Boolean>

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val input = catalogFile.get().asFile
        val output = outputFile.get().asFile
        output.parentFile.mkdirs()

        val content = input.readText()
        val result = if (includeDeprecated.get()) {
            content
        } else {
            content.lineSequence()
                .filterNot { it.contains("deprecated: true") }
                .joinToString("\n")
        }
        output.writeText(result)
    }
}

tasks.register<GenerateCatalog>("generateCatalog") {
    catalogFile.set(layout.projectDirectory.file("catalog/catalog.yml"))
    includeDeprecated.set(false)
    outputFile.set(layout.buildDirectory.file("generated/catalog.yml"))
}
~~~

Gradle có thể theo dõi file cấu hình và boolean property. Khi một input thay đổi, task có lý do để chạy lại. Khi không đổi và output hợp lệ, task có thể được bỏ qua.

## 11. Path sensitivity và input không phụ thuộc đường dẫn tuyệt đối

Với file input, đường dẫn có thể tham gia vào việc xác định trạng thái task. Nếu nội dung giống nhau nhưng workspace ở đường dẫn khác, absolute path có thể khiến snapshot khác nhau không cần thiết.

PathSensitive(PathSensitivity.RELATIVE) nói rằng task quan tâm tới đường dẫn tương đối trong input root thay vì toàn bộ đường dẫn tuyệt đối của máy.

~~~kotlin
@get:InputFiles
@get:PathSensitive(PathSensitivity.RELATIVE)
abstract val sourceFiles: ConfigurableFileCollection
~~~

Các lựa chọn path sensitivity cần phản ánh hành vi thực tế:

- ABSOLUTE: dùng khi đường dẫn tuyệt đối thực sự ảnh hưởng kết quả.
- RELATIVE: phù hợp khi cấu trúc tương đối của file quan trọng, còn workspace root không quan trọng.
- NAME_ONLY: chỉ tên file ảnh hưởng kết quả.
- NONE: nội dung file được theo dõi nhưng đường dẫn không ảnh hưởng kết quả.

Không chọn NONE hoặc NAME_ONLY chỉ để làm cache hit nhiều hơn nếu task thực sự phụ thuộc đường dẫn hoặc cấu trúc thư mục. Khai báo sai có thể khiến Gradle tái sử dụng output không đúng.

## 12. Dùng SkipWhenEmpty và Incremental khi phù hợp

Một task xử lý tập file có thể không cần chạy khi tập input rỗng. Gradle cung cấp SkipWhenEmpty cho một số file input property.

Ví dụ:

~~~kotlin
abstract class ProcessSchemas : DefaultTask() {
    @get:InputFiles
    @get:SkipWhenEmpty
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val schemas: ConfigurableFileCollection

    @get:OutputDirectory
    abstract val outputDirectory: DirectoryProperty

    @TaskAction
    fun process() {
        // Xử lý các schema hiện có.
    }
}
~~~

Khi input rỗng, task có thể được đánh dấu NO-SOURCE và action không cần chạy. Dùng annotation này khi không có input thật sự nghĩa là không có công việc.

Incremental kết hợp InputChanges cho phép task xử lý phần input đã thêm, sửa hoặc xóa thay vì xử lý lại toàn bộ tập file:

~~~kotlin
abstract class IndexSources : DefaultTask() {
    @get:Incremental
    @get:InputFiles
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val sources: ConfigurableFileCollection

    @get:OutputDirectory
    abstract val outputDirectory: DirectoryProperty

    @TaskAction
    fun index(changes: InputChanges) {
        val outputDir = outputDirectory.get().asFile
        outputDir.mkdirs()

        changes.getFileChanges(sources).forEach { change ->
            when (change.changeType) {
                ChangeType.ADDED,
                ChangeType.MODIFIED -> {
                    // Index file change.file.
                }
                ChangeType.REMOVED -> {
                    // Xóa index tương ứng với file đã bị xóa.
                }
            }
        }
    }
}
~~~

Task incremental phải xử lý đầy đủ cả ADDED, MODIFIED và REMOVED. Nếu chỉ xử lý file mới/sửa mà bỏ qua file bị xóa, output cũ có thể còn sót. Ngoài ra, incremental task cần có chiến lược khôi phục output khi Gradle không thể dùng incremental state và phải thực hiện lại toàn bộ.

Không thêm Incremental nếu task không thể xử lý thay đổi chính xác. Xử lý toàn bộ input có thể chậm hơn nhưng đơn giản và đúng; chỉ tối ưu incremental khi khối lượng công việc đáng kể và logic được thiết kế phù hợp.

## 13. Không khai báo input rộng để “cho chắc”

Đưa thêm nhiều file vào input không làm task chính xác hơn nếu task không đọc chúng. Ngược lại, input quá rộng làm task chạy lại khi thay đổi không liên quan.

Ví dụ task chỉ đọc file OpenAPI nhưng lại khai báo cả src:

~~~groovy
tasks.register('generateApi') {
    inputs.dir('src')
}
~~~

Thay đổi một file Java không liên quan cũng có thể làm task bị coi là out-of-date.

Nên khai báo đúng file:

~~~groovy
tasks.register('generateApi') {
    inputs.file('api/openapi.yml')
}
~~~

Với custom task, ưu tiên property typed như RegularFileProperty, DirectoryProperty và ConfigurableFileCollection. Chúng giúp người đọc hiểu task tiêu thụ gì và giúp Gradle theo dõi dữ liệu rõ hơn.

Tương tự, không nên khai báo cả thư mục root là InputDirectory nếu task chỉ cần một thư mục con. Thu hẹp input giúp giảm filesystem snapshot, giảm công việc hashing và giảm số lần task chạy lại.

## 14. Tránh task chạy vì một file không liên quan thay đổi

Giả sử task tạo tài liệu API từ api/openapi.yml. Nếu input là cả project directory, thay đổi README, ảnh, file test hoặc output JAR đều có thể làm task chạy lại.

Thiết kế tốt:

~~~kotlin
abstract class GenerateApiDocs : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val specification: RegularFileProperty

    @get:OutputDirectory
    abstract val destination: DirectoryProperty

    @TaskAction
    fun generate() {
        // Generator đọc specification và ghi vào destination.
    }
}

tasks.register<GenerateApiDocs>("generateApiDocs") {
    specification.set(layout.projectDirectory.file("api/openapi.yml"))
    destination.set(layout.buildDirectory.dir("generated/api-docs"))
}
~~~

Task chỉ cần chạy lại khi OpenAPI specification hoặc cấu hình input khác của nó thay đổi. File README không liên quan sẽ không làm task bị invalid.

Nếu generator cần thêm version của generator hoặc option, hãy khai báo chúng thành Input hoặc tool classpath phù hợp. Không đọc version từ executable trong PATH mà không đưa version đó vào build model.

## 15. Tránh dependency lên toàn bộ project hoặc lifecycle task

Trong multi-project build, các task lifecycle như build, check và assemble gom nhiều task. Chúng tiện cho mục tiêu tổng thể nhưng có thể quá rộng cho một bước chuyên biệt.

Ví dụ không nên dùng nếu chỉ cần compile output:

~~~groovy
tasks.register('verifyGeneratedApi') {
    dependsOn(':api:build')
}
~~~

Task build có thể kéo theo test, verification và packaging. Nếu task kiểm tra chỉ cần source/class output, hãy nối nó với output cụ thể của producer hoặc task compile tương ứng.

Ví dụ phụ thuộc vào output của task compile:

~~~kotlin
val compileApi = project(":api").tasks.named<JavaCompile>("compileJava")

tasks.register("inspectApiClasses") {
    inputs.files(compileApi.map { it.destinationDirectory })
}
~~~

Trong custom task thực tế, nên dùng typed property để nhận output directory/file provider. Khi task producer được tham chiếu qua provider output, Gradle có thể suy ra dependency mà không cần thêm một dependsOn rộng.

Đồng thời, tránh cấu hình root script theo kiểu mọi subproject đều áp dụng mọi plugin hoặc đăng ký mọi task dù không sử dụng. Hãy để project opt-in qua convention plugin phù hợp.

## 16. Chỉ cấu hình project cần thiết

Build lớn có thể có hàng chục hoặc hàng trăm project. Một số thao tác root-level có thể làm toàn bộ project được cấu hình dù invocation chỉ cần một module.

Tránh truy cập tất cả project eagerly chỉ để tìm một task:

~~~groovy
subprojects.each { subproject ->
    subproject.tasks.getByName('jar') {
        // Cấu hình eagerly từng project.
    }
}
~~~

Ưu tiên convention plugin áp dụng tại project cần dùng hoặc API lazy phù hợp. Ví dụ, module library áp dụng convention plugin library; module documentation không cần tạo task Java compile.

Cũng tránh gọi evaluationDependsOn chỉ để ép project evaluation order. Configuration order không phải task execution order và thường che giấu dependency model chưa rõ.

Khi build chỉ cần :app:compileJava, không nên buộc mọi module không liên quan chạy task compile hoặc test.

## 17. Tách task nhỏ theo trách nhiệm

Một task làm quá nhiều việc thường có input rộng và khó cache:

- Đọc source Java.
- Đọc schema.
- Gọi service từ xa.
- Sinh source.
- Copy resources.
- Tạo archive.
- Gửi artifact lên server.

Nếu mọi bước nằm trong một task, bất kỳ input nào thay đổi cũng có thể buộc toàn bộ quy trình chạy lại. Khó xác định bước nào có thể tái sử dụng kết quả.

Tách theo trách nhiệm:

~~~mermaid
flowchart LR
    A[Schema file] --> B[Generate sources]
    B --> C[Compile Java]
    D[Static assets] --> E[Copy resources]
    C --> F[Package JAR]
    E --> F
    F --> G[Publish artifact]
~~~

Khi schema không đổi nhưng resource thay đổi, task generator có thể vẫn up-to-date; resource task chạy lại và archive được tạo lại. Khi chỉ metadata publication thay đổi, không cần chạy lại generator/compiler nếu graph và input được mô tả chính xác.

Tách task không có nghĩa chia mọi dòng code thành một task riêng. Task cần đại diện cho một bước có output, input và vòng đời có ý nghĩa.

## 18. Đăng ký task lazy và nối provider output

Provider API giúp nối task producer với consumer mà không cần lấy giá trị output quá sớm.

Ví dụ task tạo file báo cáo:

~~~kotlin
abstract class GenerateReport : DefaultTask() {
    @get:OutputFile
    abstract val reportFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val output = reportFile.get().asFile
        output.parentFile.mkdirs()
        output.writeText("report")
    }
}

val reportTask = tasks.register<GenerateReport>("generateReport") {
    reportFile.set(layout.buildDirectory.file("reports/result.txt"))
}
~~~

Task khác tiêu thụ file đó:

~~~kotlin
tasks.register<Copy>("archiveReport") {
    from(reportTask.flatMap { it.reportFile })
    into(layout.buildDirectory.dir("archive"))
}
~~~

flatMap lấy provider của output file. Gradle biết file này được tạo bởi generateReport, do đó có thể đưa producer vào task graph trước archiveReport.

Cách này rõ hơn việc hard-code đường dẫn output rồi thêm dependsOn("generateReport") ở nhiều nơi. Nếu output provider được khai báo đúng, quan hệ producer/consumer được thể hiện ngay tại nơi dữ liệu được truyền.

Không gọi get() của provider trong configuration phase nếu chưa cần giá trị. Truy cập eager có thể buộc Gradle resolve hoặc realize dữ liệu sớm hơn cần thiết.

## 19. Không dùng onlyIf để thay thế task graph chính xác

onlyIf cho phép bỏ qua action của task theo điều kiện:

~~~kotlin
tasks.register("publishDocs") {
    onlyIf {
        providers.gradleProperty("publishDocs").orNull == "true"
    }
    doLast {
        // Publish documentation.
    }
}
~~~

Task vẫn có thể được đăng ký và xuất hiện trong graph, dù action bị skip. Nếu task có prerequisite, những prerequisite đó vẫn có thể được đưa vào graph và chạy.

Vì vậy, nếu một công việc hoàn toàn không cần trong invocation hiện tại, hãy tránh yêu cầu task đó hoặc tránh thêm dependency tới nó. onlyIf phù hợp khi task thuộc graph nhưng action chỉ nên chạy khi điều kiện runtime được thỏa mãn.

Không dùng onlyIf như cách che một dependency rộng không cần thiết. Ví dụ task publish bị skip nhưng vẫn phụ thuộc vào build có thể khiến compile/test chạy dù không publish gì.

## 20. Up-to-date checks và output khai báo đầy đủ

Gradle có thể bỏ qua task nếu input không đổi và output được theo dõi vẫn hợp lệ. Điều này dựa vào khai báo task.

Task chỉ khai báo input mà không khai báo output thường không có đủ thông tin để Gradle biết kết quả nào cần được giữ lại và khi nào task có thể up-to-date.

Ví dụ:

~~~kotlin
abstract class GenerateIndex : DefaultTask() {
    @get:InputFiles
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val sourceFiles: ConfigurableFileCollection

    @get:OutputFile
    abstract val indexFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val output = indexFile.get().asFile
        output.parentFile.mkdirs()
        output.writeText(
            sourceFiles.files.map { it.name }.sorted().joinToString("\n")
        )
    }
}

tasks.register<GenerateIndex>("generateIndex") {
    sourceFiles.from(fileTree("src/main/java") {
        include("**/*.java")
    })
    indexFile.set(layout.buildDirectory.file("indexes/java-sources.txt"))
}
~~~

Khi source file thay đổi, task chạy lại. Khi source không đổi và output còn hợp lệ, task có thể được đánh dấu UP-TO-DATE.

Không khai báo output giả chỉ để ép Gradle skip task. Output phải là sản phẩm thực sự của action và cần được cập nhật đúng khi input thay đổi.

## 21. Build cache cần input chính xác

Task có thể được đánh dấu CacheableTask nếu output của nó có thể tái sử dụng an toàn dựa trên input đã khai báo và action có tính xác định.

~~~kotlin
@CacheableTask
abstract class NormalizeConfig : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val sourceFile: RegularFileProperty

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun normalize() {
        val lines = sourceFile.get().asFile.readLines()
        val normalized = lines.map { it.trimEnd() }.joinToString("\n")
        val output = outputFile.get().asFile
        output.parentFile.mkdirs()
        output.writeText(normalized)
    }
}
~~~

Không đánh dấu cacheable nếu task phụ thuộc vào thời gian, random, trạng thái máy, network hoặc dữ liệu không được khai báo. Nếu output không thể tái sử dụng an toàn, không bật caching cho task đó.

Input quá rộng cũng làm giảm cache hit: một file không liên quan thay đổi sẽ đổi cache key và buộc task chạy lại hoặc cache miss. Input quá hẹp lại nguy hiểm hơn vì Gradle có thể tái sử dụng output cũ dù dữ liệu thật sự ảnh hưởng kết quả đã đổi.

Mục tiêu là input **đầy đủ và tối thiểu**: có mọi dữ liệu ảnh hưởng output, không có dữ liệu không liên quan.

## 22. File collection nên dùng đúng phạm vi

Các collection như sourceSets.main.allSource, sourceSets.main.output hoặc configurations.runtimeClasspath có thể tiện, nhưng cũng có thể rộng hơn task cần.

Ví dụ task chỉ phân tích Java source không cần toàn bộ output/resource/runtime classpath:

~~~kotlin
val mainJava = sourceSets.main.get().allJava

tasks.register("countJavaFiles") {
    inputs.files(mainJava)
}
~~~

allJava tập trung vào Java source của source set. Nếu task cần resources, thêm chúng một cách tường minh.

Nếu task chỉ cần API classpath để compile hoặc phân tích type, dùng classpath phù hợp thay vì toàn bộ runtime configuration khi không cần runtime-only dependency.

Ví dụ, compile task của Java Plugin đã quản lý compile classpath. Custom task phân tích bytecode có thể cần một classpath riêng được khai báo rõ; đừng đưa toàn bộ repository hoặc tất cả JAR trong cache vào input.

Cần hiểu ý nghĩa của collection được dùng:

- allSource: source files của source set, có thể gồm nhiều loại.
- allJava: Java source files.
- output: compiled classes và resources của source set.
- compileClasspath: dependency cần cho compile.
- runtimeClasspath: dependency cần cho runtime.

Chọn collection theo dữ liệu task thực sự đọc.

## 23. Tránh fileTree quá rộng trong task kiểm tra hoặc đóng gói

Một số task tự viết quét tất cả file để tìm resource hoặc đóng gói output. Nếu không giới hạn, chúng có thể đưa vào archive file tạm, report hoặc file do chính task sinh ra.

Ví dụ nên giới hạn:

~~~kotlin
tasks.register<Zip>("packageTemplates") {
    from(fileTree("src/main/templates") {
        include("**/*.html")
        include("**/*.css")
        exclude("**/draft/**")
    })
    archiveFileName.set("templates.zip")
    destinationDirectory.set(layout.buildDirectory.dir("distributions"))
}
~~~

Không dùng from(projectDir) cho archive trừ khi thật sự muốn đóng gói toàn bộ project. Thư mục project có thể chứa build output, .git, IDE files, secret local và file tạm.

Với task copy/sync, chỉ chọn source directory chuyên biệt và output directory riêng. Nếu cần destination phản ánh chính xác tập input, Sync có thể xóa file thừa trong destination; hãy bảo đảm task sở hữu thư mục đó trước khi dùng.

## 24. Không tạo task cho mọi project nếu chỉ một số project cần

Plugin dùng chung đôi khi đăng ký task cho tất cả subproject dù chỉ một loại project cần chức năng đó. Điều này tăng số task và configuration work.

Có thể dùng convention plugin theo loại project để opt-in:

~~~kotlin
// Trong build script của module cần tài liệu
plugins {
    id("com.example.documentation-conventions")
}
~~~

Thay vì root script đăng ký task cho mọi project:

~~~groovy
subprojects {
    tasks.register('generateDocs') {
        // Mọi project đều nhận task dù có thể không cần.
    }
}
~~~

Nếu plugin cần tạo task dựa trên plugin khác, có thể phản ứng khi plugin được áp dụng:

~~~kotlin
pluginManager.withPlugin("java") {
    tasks.register("analyzeJavaSources") {
        // Chỉ đăng ký khi Java Plugin được áp dụng.
    }
}
~~~

Cách này giúp module không phải project Java không nhận task phân tích Java. Cũng nên giữ task registration lazy và không thực hiện quét file trong callback cấu hình.

## 25. Đo đúng trước khi tối ưu

Không phải task nào chạy cũng là task thừa. Một build cần compile source đã thay đổi, chạy test cần thiết và tạo artifact mục tiêu. Tối ưu dựa trên bằng chứng sẽ tránh làm mất kiểm tra quan trọng.

Các cách quan sát:

~~~bash
./gradlew :app:build --profile
./gradlew :app:build --scan
./gradlew :app:tasks --all
./gradlew :app:build --dry-run
./gradlew help --info
~~~

- --profile tạo báo cáo hiệu năng build cục bộ.
- --scan tạo Build Scan nếu môi trường và chính sách cho phép.
- tasks --all liệt kê task có sẵn.
- --dry-run hiển thị task graph dự kiến mà không thực thi task action.
- --info cung cấp thêm thông tin về task được thực thi hoặc bỏ qua.

Khi đo, ghi lại invocation cụ thể, project path, task được yêu cầu và trạng thái task. So sánh trước/sau bằng cùng môi trường, cùng commit và cùng cache conditions.

Không tối ưu chỉ vì thấy một task trong graph. Hãy xác định nó được yêu cầu bởi dependency nào và có thực sự cần cho kết quả hay không.

## 26. Quy trình thu hẹp task graph và inputs

Khi build chậm, có thể tiến hành theo thứ tự:

1. **Xác định mục tiêu:** người dùng cần compile module, chạy test, tạo JAR hay chạy toàn bộ verification?
2. **Quan sát task graph:** dùng --dry-run và task path đầy đủ để biết task nào được chọn.
3. **Tìm dependency rộng:** kiểm tra dependsOn("build"), root lifecycle task và task dependency không cần thiết.
4. **Kiểm tra configuration phase:** tìm task eager, project traversal, afterEvaluate và công việc nặng khi cấu hình.
5. **Kiểm kê task inputs:** xác định file, directory, classpath, environment và property thực sự ảnh hưởng output.
6. **Thu hẹp file collection:** dùng source root cụ thể, include, exclude và path sensitivity phù hợp.
7. **Khai báo output:** bảo đảm task có output thật và tách biệt với input.
8. **Tận dụng provider:** nối output producer với input consumer để Gradle suy ra dependency chính xác.
9. **Xem up-to-date/cache:** xác định vì sao task chạy lại hoặc không thể cache.
10. **Đo lại:** so sánh task graph, task outcome và thời gian sau thay đổi.

Thay đổi từng nhóm một để có thể biết cải tiến đến từ đâu. Không bỏ test hoặc verification cần thiết chỉ để giảm thời gian build.

## 27. Ví dụ tổng hợp: task phân tích source với input tối thiểu

Giả sử module cần tạo danh sách Java source cho một công cụ kiểm tra. Task không cần đọc README, resources, test output hoặc dependency runtime.

~~~kotlin
abstract class ListJavaSources : DefaultTask() {
    @get:InputFiles
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val javaSources: ConfigurableFileCollection

    @get:OutputFile
    abstract val listingFile: RegularFileProperty

    @TaskAction
    fun writeListing() {
        val files = javaSources.files
            .map { it.invariantSeparatorsPath }
            .sorted()

        val output = listingFile.get().asFile
        output.parentFile.mkdirs()
        output.writeText(files.joinToString("\n"))
    }
}

val mainJavaSources = sourceSets.named("main").map { it.allJava }

val listJavaSources = tasks.register<ListJavaSources>("listJavaSources") {
    javaSources.from(mainJavaSources)
    listingFile.set(layout.buildDirectory.file("reports/java-sources.txt"))
}
~~~

Task được đăng ký lazy, chỉ nhận Java source của source set main, dùng đường dẫn tương đối cho snapshot và ghi một output file dưới build/.

Nếu công cụ tiếp theo cần file listing, nối provider output:

~~~kotlin
tasks.register("consumeJavaSourceList") {
    inputs.file(listJavaSources.flatMap { it.listingFile })
    doLast {
        // Đọc file listing khi task thực sự chạy.
    }
}
~~~

Gradle có thể suy ra task listJavaSources là producer của input file. Không cần phụ thuộc vào build hoặc quét toàn bộ project.

## 28. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| Đăng ký task nghĩa là task sẽ chạy | Task chỉ chạy khi được yêu cầu hoặc được đưa vào graph bởi quan hệ phù hợp. |
| tasks.register tự động làm build nhanh dù task graph vẫn rộng | Lazy registration giúp tránh realize task không dùng; dependency graph vẫn cần được thiết kế đúng. |
| mustRunAfter khiến prerequisite chạy | Nó chỉ sắp xếp task đã có trong graph, không thêm task vào graph. |
| dependsOn("build") là cách an toàn để chắc chắn output tồn tại | Nó có thể kéo theo test, check và nhiều công việc không cần thiết; phụ thuộc output/task cụ thể. |
| Đưa cả project directory vào input giúp task chính xác hơn | Nó làm input quá rộng, gây rerun và cache miss khi file không liên quan đổi. |
| Input càng rộng thì cache càng an toàn | Input cần đầy đủ nhưng tối thiểu; dữ liệu không liên quan làm cache key thay đổi vô ích. |
| Không khai báo output vẫn có thể tận dụng up-to-date checks như task chuẩn | Task cần mô tả output thực tế để Gradle quản lý trạng thái và cache đúng. |
| onlyIf loại task khỏi task graph | Task vẫn có thể ở trong graph; action bị skip và prerequisite vẫn có thể chạy. |
| --parallel sửa được task graph quá rộng | Parallel chỉ chạy đồng thời những task độc lập; nó không loại bỏ công việc thừa. |
| Có thể dùng Incremental mà không xử lý file bị xóa | Task incremental phải xử lý cả ADDED, MODIFIED và REMOVED. |
| Tắt cache là làm task hermetic | Tắt cache không loại bỏ input ẩn hoặc network access. |
| Dùng fileTree ở project root luôn tiện và an toàn | Có thể vô tình quét .git, build, cache, IDE files và output của chính task. |

## 29. Nguyên tắc cần ghi nhớ

Build hiệu quả cần task graph vừa đủ và input/output chính xác. Dùng register, named và configureEach để trì hoãn việc tạo/cấu hình task; tránh công việc nặng trong configuration phase; không phụ thuộc lifecycle task rộng nếu chỉ cần một output cụ thể; dùng Provider API để nối producer với consumer.

Với custom task, khai báo đúng file, directory, classpath và property thực sự ảnh hưởng kết quả. Thu hẹp fileTree bằng source root, include/exclude và path sensitivity phù hợp; không đọc output của chính task như input; khai báo output riêng để Gradle hỗ trợ up-to-date và build cache. Chỉ dùng incremental processing khi xử lý chính xác cả file thêm, sửa và xóa.

Đo task graph và trạng thái task trước khi tối ưu. Mục tiêu không phải bỏ qua công việc cần thiết, mà là để Gradle chỉ thực hiện đúng công việc cần cho kết quả được yêu cầu, và chỉ chạy lại khi dữ liệu ảnh hưởng kết quả thực sự thay đổi.

